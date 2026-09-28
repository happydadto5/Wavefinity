"""Structural cabinet output planning and manifest-owned file replacement."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

import numpy as np
import trimesh

from organizer_app import clean_label
from organizer_engine import export_mesh, export_text_body_3mf, validate_3mf
from organizer_printer_profile import component_fit, normalise_printer_profile, orientation_transform
from organizer_storage_drawers import normalise_storage_drawers_definition
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan

STRUCTURAL_OUTPUT_KEY = "storage_drawers"
# Version 2: real printable meshes, exported in the orientation the fit check chose.
STRUCTURAL_GENERATOR_VERSION = 2
# The exact app-owned namespace for temp files and rollback backups in a Space folder.
CABINET_DEBRIS_PREFIX = ".wavefinity-cabinet-"
# Held for a whole local save (stage, install, manifest commit, cleanup) so debris
# sweeping can never remove files an active transaction still owns.
_TRANSACTION_LOCK = threading.RLock()


def effective_structural_state(space: dict) -> dict:
    canonical = normalise_storage_drawers_definition(space)
    block = canonical["storage_drawers"]
    plan = resolve_storage_drawers_plan(canonical, build_meshes=False)
    state = {
        "version": STRUCTURAL_GENERATOR_VERSION, "name": canonical["name"],
        "field": [canonical["x"], canonical["y"]],
        "drawers": [{"id": row["id"], "height_mm": row["height_mm"],
                     **({"label_text": row["label_text"]} if block["drawer_labels_enabled"] and row["label_text"] else {})}
                    for row in block["drawers"]],
        "cabinet_style": block["cabinet_style"], "rear_support": block["rear_support"],
        "drawer_fit_mm": block["drawer_fit_mm"], "drawer_handles": block["drawer_handles"],
        "stacking": block["stacking"], "unit_label_enabled": block["unit_label_enabled"],
        "drawer_labels_enabled": block["drawer_labels_enabled"],
        "material": {key: block[key] for key in ("cabinet_wall_mm", "cabinet_base_mm", "cabinet_top_mm", "drawer_wall_mm", "drawer_base_mm")},
        "effective_base_mm": plan.effective_base_mm, "effective_top_mm": plan.effective_top_mm,
    }
    # Only Open geometry depends on the frame width. Full stays independent of a
    # hidden Open selection, in geometry and in this freshness signature.
    if block["cabinet_style"] == "open":
        state["open_frame_width_mm"] = block["open_frame_width_mm"]
        state["resolved_frame_width_mm"] = plan.resolved_frame_width_mm
    if block["drawer_handles"]:
        state["drawer_handle_size"] = block["drawer_handle_size"]
    if block["unit_label_enabled"]:
        state["unit_label_text"] = block["unit_label_text"]
    if block["drawer_labels_enabled"]:
        state["drawer_label_style"] = block["drawer_label_style"]
    return state


def structural_signature(space: dict) -> str:
    encoded = json.dumps(effective_structural_state(space), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _filename(space_name: str, component_name: str) -> str:
    safe = clean_label(space_name)
    if not safe:
        raise ValueError("Space name does not make a valid filename")
    return f"{safe} - {component_name}.3mf"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(folder: Path, filename: str) -> Path:
    if Path(filename).name != filename or filename in (".", "..") or not filename.lower().endswith(".3mf"):
        raise ValueError("Invalid cabinet component filename")
    return folder / filename


def structural_manifest_plan(space: dict, output_dir: Path, printer_profile: dict) -> dict:
    plan = resolve_storage_drawers_plan(space, build_meshes=False)
    profile = normalise_printer_profile(printer_profile)
    components = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            fit = {**fit, "reason": f"{component.display_name}: {fit['reason']}"}
        filename = _filename(plan.space["name"], component.display_name)
        _safe_path(Path(output_dir), filename)
        components.append({"key": component.key, "filename": filename,
                           "bounds_xyz": list(component.bounds_xyz), **fit})
    return {"signature": structural_signature(plan.space), "generator_version": STRUCTURAL_GENERATOR_VERSION,
            "components": components, "fits_printer": all(one["fits"] for one in components),
            "first_fit_error": next((one["reason"] for one in components if not one["fits"]), None)}


def _valid_manifest_components(manifest) -> list | None:
    """The manifest's component rows if it has the right shape, else None."""
    if not isinstance(manifest, dict):
        return None
    rows = manifest.get("components")
    if not isinstance(rows, list) or not rows:
        return None
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("filename"), str)
                or not isinstance(item.get("sha256"), str) or not isinstance(item.get("key"), str)):
            return None
    return rows


def structural_status(space: dict, stored_manifest: dict | None, output_dir: Path,
                      printer_profile: dict | None = None) -> dict:
    """Saved only when signature, shape, filenames and every file's SHA-256 agree."""
    rows = _valid_manifest_components(stored_manifest)
    if rows is None:
        return {"status": "need_save"}
    if stored_manifest.get("signature") != structural_signature(space):
        return {"status": "need_update"}
    try:
        files = [_safe_path(Path(output_dir), item["filename"]) for item in rows]
    except (TypeError, ValueError):
        return {"status": "need_save"}
    for path, item in zip(files, rows):
        try:
            if not path.is_file() or _hash(path) != item["sha256"]:
                return {"status": "need_save"}
        except OSError:
            return {"status": "need_save"}
    if printer_profile is not None:
        # Files exported for another printer orientation are stale, not saved.
        wanted = {one["key"]: one for one in structural_manifest_plan(space, Path(output_dir), printer_profile)["components"]}
        for item in rows:
            now = wanted.get(item["key"])
            if now is None or not now["fits"] or item.get("orientation") != now["orientation"]:
                return {"status": "need_update"}
    return {"status": "saved"}


def sweep_cabinet_debris(folder: Path) -> list[str]:
    """Remove orphan app-owned temp/backup files from one Space folder.

    Only ``.wavefinity-cabinet-*.3mf`` regular files directly inside the folder;
    skipped entirely while any save transaction is active.
    """
    folder = Path(folder)
    if not folder.is_dir() or not _TRANSACTION_LOCK.acquire(blocking=False):
        return []
    removed: list[str] = []
    try:
        for entry in folder.iterdir():
            name = entry.name
            if (name.startswith(CABINET_DEBRIS_PREFIX) and name.lower().endswith(".3mf")
                    and entry.is_file() and not entry.is_symlink()):
                try:
                    entry.unlink()
                    removed.append(name)
                except OSError:
                    pass
    finally:
        _TRANSACTION_LOCK.release()
    return removed


def _previous_owned(folder: Path, previous_manifest) -> dict[str, dict]:
    if previous_manifest is None:
        return {}
    rows = previous_manifest.get("components") if isinstance(previous_manifest, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Previous cabinet manifest is invalid")
    previous: dict[str, dict] = {}
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("filename"), str)):
            raise ValueError("Previous cabinet manifest is invalid")
        path = _safe_path(folder, item["filename"])
        if path.name in previous:
            raise ValueError("Previous cabinet manifest has duplicate filenames")
        previous[path.name] = item
    return previous


def _oriented_parts(component, orientation: str):
    """Body and every object-group mesh rotated together (never mirrored) and
    moved to the print-bed origin."""
    transform = orientation_transform(orientation, flip_up=component.flip_up)
    body = component.mesh.copy()
    body.apply_transform(transform)
    groups = []
    for label, mesh in component.object_groups or ():
        copy = mesh.copy()
        copy.apply_transform(transform)
        groups.append((label, copy))
    low = np.min([one.bounds[0] for one in (body, *(mesh for _label, mesh in groups))], axis=0)
    body.apply_translation(-low)
    for _label, mesh in groups:
        mesh.apply_translation(-low)
    return body, tuple(groups)


def _check_exported_fit(path: Path, profile: dict, name: str) -> None:
    """The written file itself must fit the printer as exported."""
    extents = trimesh.load(path, force="scene").extents
    bed = (profile["x_mm"], profile["y_mm"], profile["z_mm"])
    if any(float(size) > limit + 1e-6 for size, limit in zip(extents, bed)):
        raise RuntimeError(f"{name}: the exported file does not fit the printer profile")


def materialize_storage_drawers(space: dict, output_dir: Path, printer_profile: dict,
                                previous_manifest: dict | None, *, commit=None) -> dict:
    """Write every cabinet file as one transaction.

    ``commit(manifest)`` (local saves) records the manifest in the Space metadata
    while the pre-attempt backups still exist. If staging, installation or the
    commit fails, every installed file is removed and every replaced owned file
    is put back exactly as it was. Backups and obsolete owned files are cleaned
    only after the commit succeeded.
    """
    with _TRANSACTION_LOCK:
        return _materialize(space, Path(output_dir), printer_profile, previous_manifest, commit)


def _materialize(space, folder, printer_profile, previous_manifest, commit) -> dict:
    dry = structural_manifest_plan(space, folder, printer_profile)
    if not dry["fits_printer"]:
        raise ValueError(dry["first_fit_error"] or "Cabinet does not fit printer")
    previous = _previous_owned(folder, previous_manifest)
    desired = [item["filename"] for item in dry["components"]]
    if len(desired) != len(set(desired)):
        raise ValueError("Cabinet component filenames collide")
    for name in desired:
        path = _safe_path(folder, name)
        if path.exists() and (name not in previous or _hash(path) != previous[name]["sha256"]):
            raise ValueError(f"{name} changed outside Wavefinity; rename or move it before updating the cabinet.")
    # All output is staged on the final filesystem before any owned target changes.
    folder.mkdir(parents=True, exist_ok=True)
    plan = resolve_storage_drawers_plan(space, build_meshes=True)
    profile = normalise_printer_profile(printer_profile)
    fits = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            raise ValueError(f"{component.display_name}: {fit['reason']}")
        fits.append(fit)
    temporary: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    installed: list[str] = []
    warnings = list(plan.warnings)
    committed = False
    try:
        for component, item, fit in zip(plan.components, dry["components"], fits):
            fd, name = tempfile.mkstemp(prefix=CABINET_DEBRIS_PREFIX, suffix=".3mf", dir=folder)
            os.close(fd)
            temp = Path(name)
            temporary[item["filename"]] = temp
            if component.mesh is None:
                raise RuntimeError(f"Missing mesh for {component.display_name}")
            body, groups = _oriented_parts(component, fit["orientation"])
            if groups:
                export_text_body_3mf(body, groups, temp, component.display_name)
                validate_3mf(temp, 1 + len(groups), multipart=tuple(label for label, _mesh in groups))
            else:
                export_mesh(body, temp, component.display_name)
                validate_3mf(temp, 1)
            _check_exported_fit(temp, profile, component.display_name)
        for name in desired:
            final = _safe_path(folder, name)
            if final.exists():
                fd, backup_name = tempfile.mkstemp(prefix=CABINET_DEBRIS_PREFIX + "backup-", suffix=".3mf", dir=folder)
                os.close(fd)
                backup = Path(backup_name)
                backup.unlink()
                os.replace(final, backup)
                backups[name] = backup
            os.replace(temporary[name], final)
            installed.append(name)
        manifest = {"signature": dry["signature"], "generator_version": STRUCTURAL_GENERATOR_VERSION,
                    "components": [{"key": item["key"], "filename": item["filename"],
                                    "sha256": _hash(_safe_path(folder, item["filename"])),
                                    "size": _safe_path(folder, item["filename"]).stat().st_size,
                                    "orientation": fit["orientation"]}
                                   for item, fit in zip(dry["components"], fits)]}
        if commit is not None:
            # The backups still exist here; a failed commit rolls everything back.
            commit(manifest)
        committed = True
    except Exception:
        for name in reversed(installed):
            final = _safe_path(folder, name)
            if final.exists():
                final.unlink()
        for name, backup in list(backups.items()):
            if backup.exists():
                os.replace(backup, _safe_path(folder, name))
            del backups[name]
        raise
    finally:
        for path in [*temporary.values(), *backups.values()]:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
    if committed:
        for name, old in previous.items():
            if name in desired:
                continue
            stale = _safe_path(folder, name)
            if stale.exists():
                if _hash(stale) == old["sha256"]:
                    try:
                        stale.unlink()
                    except OSError:
                        warnings.append(f"Could not remove old cabinet file {name}; remove it manually")
                else:
                    warnings.append(f"{name} changed outside Wavefinity; left in place without cabinet ownership")
    return {"files": [_safe_path(folder, name) for name in desired], "manifest": manifest, "warnings": warnings}
