"""Structural cabinet output planning and manifest-owned file replacement."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from organizer_app import clean_label
from organizer_engine import export_mesh, export_text_body_3mf, validate_3mf
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import normalise_storage_drawers_definition
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan

STRUCTURAL_OUTPUT_KEY = "storage_drawers"
STRUCTURAL_GENERATOR_VERSION = 1


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
        filename = _filename(plan.space["name"], component.display_name)
        _safe_path(Path(output_dir), filename)
        components.append({"key": component.key, "filename": filename,
                           "bounds_xyz": list(component.bounds_xyz), **fit})
    return {"signature": structural_signature(plan.space), "generator_version": STRUCTURAL_GENERATOR_VERSION,
            "components": components, "fits_printer": all(one["fits"] for one in components),
            "first_fit_error": next((one["reason"] for one in components if not one["fits"]), None)}


def structural_status(space: dict, stored_manifest: dict | None, output_dir: Path) -> dict:
    if not stored_manifest or not isinstance(stored_manifest, dict) or not stored_manifest.get("components"):
        return {"status": "need_save"}
    if stored_manifest.get("signature") != structural_signature(space):
        return {"status": "need_update"}
    try:
        files = [_safe_path(Path(output_dir), item["filename"]) for item in stored_manifest["components"]]
    except (KeyError, TypeError, ValueError):
        return {"status": "need_save"}
    return {"status": "saved" if all(path.is_file() for path in files) else "need_save"}


def materialize_storage_drawers(space: dict, output_dir: Path, printer_profile: dict,
                                previous_manifest: dict | None) -> dict:
    folder = Path(output_dir)
    dry = structural_manifest_plan(space, folder, printer_profile)
    if not dry["fits_printer"]:
        raise ValueError(dry["first_fit_error"] or "Cabinet does not fit printer")
    previous = {}
    for item in (previous_manifest or {}).get("components", []):
        if not isinstance(item, dict) or not isinstance(item.get("sha256"), str):
            raise ValueError("Previous cabinet manifest is invalid")
        path = _safe_path(folder, item.get("filename", ""))
        if path.name in previous:
            raise ValueError("Previous cabinet manifest has duplicate filenames")
        previous[path.name] = item
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
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            raise ValueError(f"{component.display_name}: {fit['reason']}")
    temporary = {}
    backups = {}
    installed = []
    warnings = list(plan.warnings)
    try:
        for component, item in zip(plan.components, dry["components"]):
            fd, name = tempfile.mkstemp(prefix=".wavefinity-cabinet-", suffix=".3mf", dir=folder)
            os.close(fd)
            temp = Path(name)
            temporary[item["filename"]] = temp
            if component.mesh is None:
                raise RuntimeError(f"Missing mesh for {component.display_name}")
            if component.object_groups:
                export_text_body_3mf(component.mesh, component.object_groups, temp,
                                     component.display_name)
                validate_3mf(temp, 1 + len(component.object_groups),
                             multipart=tuple(name for name, _mesh in component.object_groups))
            else:
                export_mesh(component.mesh, temp, component.display_name)
                validate_3mf(temp, 1)
        for name in desired:
            final = _safe_path(folder, name)
            if final.exists():
                fd, backup_name = tempfile.mkstemp(prefix=".wavefinity-cabinet-backup-", suffix=".3mf", dir=folder)
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
                                    "size": _safe_path(folder, item["filename"]).stat().st_size}
                                   for item in dry["components"]]}
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
    except Exception:
        for name in reversed(installed):
            final = _safe_path(folder, name)
            if final.exists():
                final.unlink()
        for name, backup in backups.items():
            if backup.exists():
                os.replace(backup, _safe_path(folder, name))
        raise
    finally:
        for path in [*temporary.values(), *backups.values()]:
            if path.exists():
                path.unlink()
