"""Base Trim owned-output lifecycle: saved-file manifest, currentness and safe replacement.

A Surface Space's Base Trim files are recorded in the Space's existing
``.wavefinity.json -> structural_outputs.base_trim`` manifest (committed through
``organizer_spaces.commit_structural_output``). Nothing here reads or writes an
Inventory, and Base Trim geometry stays in ``organizer_base_trim``.

Currentness states (read-only to compute):

* ``current``            - signature matches and every owned file has its saved hash;
* ``missing``            - no manifest (a legacy Surface's files are untracked, never
                           guessed current), or an owned file is absent;
* ``needs_update``       - the Surface, trim, name or printer bed no longer matches;
* ``externally_changed`` - an owned filename exists but its bytes no longer match.

Files are only ever replaced or removed when the prior manifest proves Wavefinity
made them (same filename and same hash); an unowned or changed same-name file is
never overwritten or deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from organizer_app import clean_label
from organizer_base_trim import (
    base_trim_from_design,
    base_trim_output_plan,
    base_trim_summary,
    generate_base_trim_files,
)
from organizer_inventory import normalise_space_definition
from organizer_printer_profile import normalise_printer_profile
from organizer_product_rules import SURFACE_TRIM_HEIGHTS
from organizer_space_outputs import BASE_TRIM, base_trim_design, structural_kind

BASE_TRIM_OUTPUT_KEY = "base_trim"
BASE_TRIM_MANIFEST_SCHEMA = 1
# Bump only when Base Trim geometry/output changes in a way old files must not
# be trusted as current; deliberately independent of the metadata version.
BASE_TRIM_OUTPUT_VERSION = 1
BASE_TRIM_DEBRIS_PREFIX = ".wavefinity-basetrim-"
# Held for a whole local save so debris sweeping never touches a live transaction.
_TRANSACTION_LOCK = threading.RLock()


class BaseTrimOwnershipError(ValueError):
    """A same-name file exists that Wavefinity cannot prove it owns."""


def _definition(space: Any) -> dict[str, Any]:
    definition = normalise_space_definition(space, allow_legacy=True) if isinstance(space, dict) else None
    if definition is None or structural_kind(definition) != BASE_TRIM:
        raise ValueError("Only a Surface Space has a Base Trim to save or print.")
    return definition


def _safe_name(filename: Any) -> str:
    if (not isinstance(filename, str) or Path(filename).name != filename
            or filename in (".", "..") or not filename.lower().endswith(".3mf")):
        raise ValueError("Invalid Base Trim filename")
    return filename


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_trim_signature(space: dict[str, Any], printer_profile: dict[str, Any]) -> str:
    """Deterministic structural identity of the Base Trim output for this printer."""
    definition = _definition(space)
    profile = normalise_printer_profile(printer_profile)
    trim = SURFACE_TRIM_HEIGHTS[definition["trim_size"]]
    state = {
        "output_version": BASE_TRIM_OUTPUT_VERSION,
        "field_mm": [definition["x"], definition["y"]],
        "trim_size": definition["trim_size"],
        "height_mm": trim, "width_mm": trim,
        "name": clean_label(definition["name"]),
        "bed_mm": [profile["x_mm"], profile["y_mm"]],
    }
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def base_trim_plan(space: dict[str, Any], printer_profile: dict[str, Any]) -> dict[str, Any]:
    """Current-printer piece plan and the exact owned filenames, with no geometry.

    Raises ``ValueError`` (a plain fit reason) when the trim cannot be planned
    for this printer.
    """
    definition = _definition(space)
    profile = normalise_printer_profile(printer_profile)
    design = base_trim_design(definition, bed_x_mm=profile["x_mm"], bed_y_mm=profile["y_mm"])
    spec = base_trim_from_design(design)
    pieces = base_trim_output_plan(spec, design["part_name"])
    return {
        "signature": base_trim_signature(definition, profile),
        "output_version": BASE_TRIM_OUTPUT_VERSION,
        "printer": {"x_mm": profile["x_mm"], "y_mm": profile["y_mm"]},
        "pieces": pieces,
        "filenames": [one["filename"] for one in pieces],
        "piece_count": len(pieces),
        "summary": base_trim_summary(spec),
        "design": design,
        "spec": spec,
    }


def public_plan(plan: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in plan.items() if key not in ("design", "spec")}


def _valid_pieces(manifest: Any) -> list[dict[str, Any]] | None:
    if not isinstance(manifest, dict) or manifest.get("schema") != BASE_TRIM_MANIFEST_SCHEMA:
        return None
    rows = manifest.get("pieces")
    if not isinstance(rows, list) or not rows:
        return None
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("filename"), str)
                or not isinstance(item.get("sha256"), str)):
            return None
    return rows


def base_trim_status(
    space: dict[str, Any], manifest: Any, folder: Path, printer_profile: dict[str, Any],
    *, space_id: str | None = None, plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only currentness of the saved Base Trim for this Space and printer."""
    plan = plan or base_trim_plan(space, printer_profile)
    result: dict[str, Any] = {"status": "missing", "piece_count": plan["piece_count"],
                              "changed": [], "absent": []}
    rows = _valid_pieces(manifest)
    if rows is None or (space_id and manifest.get("space_id") != space_id):
        return result
    if manifest.get("signature") != plan["signature"] \
            or [one["filename"] for one in rows] != plan["filenames"]:
        return {**result, "status": "needs_update"}
    for item in rows:
        try:
            path = Path(folder) / _safe_name(item["filename"])
            if not path.is_file():
                result["absent"].append(item["filename"])
            elif file_sha256(path) != item["sha256"]:
                result["changed"].append(item["filename"])
        except (OSError, ValueError):
            result["changed"].append(str(item.get("filename")))
    if result["changed"]:
        return {**result, "status": "externally_changed"}
    if result["absent"]:
        return result
    return {**result, "status": "current"}


def _manifest(plan: dict[str, Any], space_id: str | None, files: dict[str, Path]) -> dict[str, Any]:
    return {
        "schema": BASE_TRIM_MANIFEST_SCHEMA,
        "output_version": BASE_TRIM_OUTPUT_VERSION,
        "space_id": space_id,
        "signature": plan["signature"],
        "printer": plan["printer"],
        "piece_count": plan["piece_count"],
        "pieces": [
            {"number": one["number"], "label": one["label"], "filename": one["filename"],
             "sha256": file_sha256(files[one["filename"]]),
             "size": files[one["filename"]].stat().st_size}
            for one in plan["pieces"]
        ],
    }


def _generate_into(plan: dict[str, Any], directory: Path) -> dict[str, Path]:
    """Generate the complete piece set into ``directory`` with the exact planned names."""
    generate_base_trim_files(plan["spec"], directory, plan["design"]["part_name"], auto_timestamp=False)
    made = {path.name: path for path in Path(directory).iterdir() if path.is_file()}
    if sorted(made) != sorted(plan["filenames"]):
        raise RuntimeError("Base Trim generation did not make the planned pieces. Nothing was changed.")
    return {name: made[name] for name in plan["filenames"]}


def export_base_trim(
    space: dict[str, Any], output_dir: Path, printer_profile: dict[str, Any], space_id: str | None,
) -> dict[str, Any]:
    """Hosted export: generate every piece into a temporary workspace and return the
    manifest for those exact bytes. The browser folder owns the final write."""
    plan = base_trim_plan(space, printer_profile)
    files = _generate_into(plan, Path(output_dir))
    return {"files": list(files.values()), "manifest": _manifest(plan, space_id, files),
            "plan": public_plan(plan)}


def sweep_base_trim_debris(folder: Path) -> None:
    """Remove orphan staging/backup entries of an interrupted earlier save."""
    folder = Path(folder)
    if not folder.is_dir() or not _TRANSACTION_LOCK.acquire(blocking=False):
        return
    try:
        for entry in folder.iterdir():
            if not entry.name.startswith(BASE_TRIM_DEBRIS_PREFIX) or entry.is_symlink():
                continue
            try:
                if entry.is_dir():
                    shutil.rmtree(entry)
                elif entry.is_file():
                    entry.unlink()
            except OSError:
                pass
    finally:
        _TRANSACTION_LOCK.release()


def owned_by_previous(folder: Path, previous_manifest: Any, space_id: str | None) -> dict[str, str]:
    """``{filename: sha256}`` a prior valid manifest proves Wavefinity made.

    The one local ownership gate: a manifest proves ownership only when it is valid
    AND belongs to this Space. A missing current ``space_id``, a missing manifest
    ``space_id`` or a different one proves nothing, so a copied or stale manifest
    from another Space can never authorize a replacement or a stale-file cleanup.
    """
    rows = _valid_pieces(previous_manifest)
    if rows is None or not space_id or previous_manifest.get("space_id") != space_id:
        return {}
    owned: dict[str, str] = {}
    for item in rows or []:
        owned[_safe_name(item["filename"])] = item["sha256"]
    return owned


def materialize_base_trim(
    space: dict[str, Any], folder: Path, printer_profile: dict[str, Any], previous_manifest: Any,
    *, space_id: str | None, commit: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Write the complete Base Trim and commit its manifest, or change nothing.

    Every piece is generated into a staging directory inside ``folder`` first. A
    same-name file is replaced only when the prior manifest proves it is ours and
    unchanged; anything else stops with the outside file left intact. The manifest
    is committed only after every final file is in place, while the pre-attempt
    backups still exist, so a failed commit puts every file back. An unowned
    same-name file is never replaced or adopted, even when its bytes happen to
    equal the new output.
    """
    folder = Path(folder)
    with _TRANSACTION_LOCK:
        sweep_base_trim_debris(folder)
        plan = base_trim_plan(space, printer_profile)
        owned = owned_by_previous(folder, previous_manifest, space_id)
        desired = plan["filenames"]
        for name in desired:
            _safe_name(name)
        folder.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=BASE_TRIM_DEBRIS_PREFIX, dir=folder))
        backups: dict[str, Path] = {}
        installed: list[str] = []
        committed = False
        try:
            staged = _generate_into(plan, staging)
            manifest = _manifest(plan, space_id, staged)
            for name in desired:
                final = folder / name
                if final.exists() and (name not in owned or file_sha256(final) != owned[name]):
                    raise BaseTrimOwnershipError(
                        f"{name} is already in this folder and was not made by this Base Trim, or it was "
                        "changed outside Wavefinity. Rename or move it, then save again. Nothing was changed."
                    )
            for name in desired:
                final = folder / name
                if final.exists():
                    backup = staging / (BASE_TRIM_DEBRIS_PREFIX + "backup-" + name)
                    os.replace(final, backup)
                    backups[name] = backup
                os.replace(staged[name], final)
                installed.append(name)
            for item in manifest["pieces"]:
                if file_sha256(folder / item["filename"]) != item["sha256"]:
                    raise RuntimeError(f"{item['filename']} did not save correctly. Nothing was changed.")
            commit(manifest)
            committed = True
        except Exception:
            for name in reversed(installed):
                try:
                    (folder / name).unlink()
                except OSError:
                    pass
            for name, backup in backups.items():
                if backup.exists():
                    os.replace(backup, folder / name)
            raise
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        warnings: list[str] = []
        if committed:
            for name, digest in owned.items():
                if name in desired:
                    continue
                stale = folder / name
                if not stale.exists():
                    continue
                try:
                    if file_sha256(stale) == digest:
                        stale.unlink()
                    else:
                        warnings.append(f"{name} changed outside Wavefinity; left in place without Base Trim ownership")
                except OSError:
                    warnings.append(f"Could not remove old Base Trim file {name}; remove it manually")
        return {"files": [folder / name for name in desired], "manifest": manifest,
                "plan": public_plan(plan), "warnings": warnings}
