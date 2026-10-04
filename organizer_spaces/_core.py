"""Space storage helpers: metadata files, identity, registry and folder state."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
from typing import Any
import uuid
from organizer_inventory import (
    INVENTORY_FILENAME,
    legacy_layout_space,
    load_inventory,
    normalise_space_definition,
    normalise_storage_box,
)
from organizer_product_rules import SURFACE_TRIM_HEIGHTS, surface_maximums
import organizer_storage
from organizer_storage_drawers import (
    normalise_storage_drawers_definition,
    reset_storage_drawers_definition,
    storage_drawers_definition_problem,
    storage_drawers_recent_summary,
)


MAX_RECENT = 8
METADATA_FILE = ".wavefinity.json"
LEGACY_METADATA_FILE = ".wavefinity-space.json"
SPACE_ID_REQUIRED_VERSION = 5
RESUME_REQUIRED_VERSION = 8
METADATA_VERSION = 9
SPACE_SETUP_VERSION = 1
SUPPORTED_METADATA_VERSIONS = {2, 3, 4, 5, 6, 7, 8, 9}
_UNSET = object()


class FolderMetadataError(ValueError):
    """The folder contains metadata that must not be guessed at or replaced."""


class DuplicateSpaceError(ValueError):
    """Two distinct folders carry the same Space identity."""


DUPLICATE_MESSAGE = (
    "This folder is a copy of an existing Wavefinity Space and has the same Space identity. "
    "The existing Space was left unchanged."
)

_INVALID_SPACE_FOLDER_CHARS = set('<>:"/\\|?*')
_RESERVED_SPACE_FOLDER_NAMES = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

_DUPLICATE_SPACE_NAME_MESSAGE = (
    "That Space name is already in use. "
    "Space names can't be reused. Choose a different name."
)
_SPACE_CREATE_LOCK = threading.RLock()
# Guards the complete read/preserve/write transaction of a folder's
# .wavefinity.json (including the temp-file replace) so resume/defaults/
# rename/version-upgrade writes from concurrent requests cannot clobber one
# another's fields.
_METADATA_WRITE_LOCK = threading.RLock()

# Fix 058 K: first-run local Space storage location. The default Space
# hierarchy stays ``<space parent>/Wavefinity/<Space Name>`` with Documents as
# the default parent; ``space_parent`` is the one explicit preference key that
# overrides just the parent, never the ``Wavefinity`` child folder name.
SPACE_PARENT_PREFERENCE_KEY = "space_parent"
# Fix 083: a relocation in progress (so a restart can resolve it to exactly one
# root) and an old root left behind after a verified copy (reported, never
# deleted on a guess).
STORAGE_RELOCATION_KEY = "storage_relocation"
STORAGE_LEFTOVER_KEY = "storage_leftover_root"


def _usable_directory(raw: Any) -> Path | None:
    if not raw:
        return None
    try:
        candidate = Path(str(raw)).expanduser()
        return candidate.resolve() if candidate.is_dir() else None
    except OSError:
        return None


def saved_parent_unavailable(prefs: dict[str, Any]) -> bool:
    """An explicit saved parent exists but is no longer usable."""
    raw = prefs.get(SPACE_PARENT_PREFERENCE_KEY)
    return bool(raw) and _usable_directory(raw) is None


def _storage_plan(prefs: dict[str, Any], raw_parent: Any, current_root: Path) -> dict[str, Any]:
    """Validate a proposed new parent before anything is changed."""
    if not raw_parent:
        raise ValueError("Choose a folder for Wavefinity's Space storage.")
    parent = _usable_directory(raw_parent)
    if parent is None:
        raise ValueError("That folder could not be found. Choose an existing folder.")
    root = parent / "Wavefinity"
    same = organizer_storage.same_path(current_root, root)
    source_exists = not saved_parent_unavailable(prefs) and current_root.is_dir()
    if (
        source_exists and not same
        and (organizer_storage.is_within(root, current_root)
             or organizer_storage.is_within(current_root, root))
    ):
        raise ValueError(
            "Choose a location outside your current Wavefinity folder "
            "(not inside it, and not a folder that contains it)."
        )
    return {
        "parent": str(parent),
        "root": str(root),
        "current_root": str(current_root),
        "source_exists": source_exists,
        "same": same,
        "conflict": not same and organizer_storage.destination_conflict(root),
    }


def _forget_root_pointers(prefs: dict[str, Any], old_root: Path) -> None:
    """Drop every profile pointer into ``old_root`` (shortcuts only - no data is touched).

    Used when the user keeps old data where it is: nothing under the old root
    may be resumed or listed as if it were current.
    """
    within = organizer_storage.is_within
    registry = _space_registry(prefs)
    dropped = {sid for sid, entry in registry.items() if within(entry.get("folder"), old_root)}
    if "space_registry" in prefs:
        prefs["space_registry"] = {sid: e for sid, e in registry.items() if sid not in dropped}
    if _space_id(prefs.get("active_space_id")) in dropped:
        prefs["active_space_id"] = None
    if within(prefs.get("output"), old_root):
        prefs.pop("output", None)
        prefs["active_space_id"] = None
    for key in ("recent_folders", "recent_spaces"):
        saved = prefs.get(key)
        if isinstance(saved, list):
            prefs[key] = [
                one for one in saved
                if not (isinstance(one, dict) and within(one.get("folder"), old_root))
            ]

def _space_folder_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValueError("Give the Space a name.")
    if len(name) > 80:
        raise ValueError("Space names must be 80 characters or fewer.")
    if (
        name in {".", ".."}
        or name.endswith((" ", "."))
        or any(ord(ch) < 32 or ch in _INVALID_SPACE_FOLDER_CHARS for ch in name)
        or name.split(".", 1)[0].casefold() in _RESERVED_SPACE_FOLDER_NAMES
    ):
        raise ValueError(
            'Space names cannot use Windows folder characters < > : " / \\ | ? *, '
            "end in a space or period, or use a reserved Windows device name."
        )
    return name

def _new_space_target(root: Path, raw_name: Any) -> Path:
    name = _space_folder_name(raw_name)
    with _SPACE_CREATE_LOCK:
        root.mkdir(parents=True, exist_ok=True)
        folded = name.casefold()
        if any(child.name.casefold() == folded for child in root.iterdir()):
            raise ValueError(_DUPLICATE_SPACE_NAME_MESSAGE)
        target = root / name
        try:
            target.mkdir()
        except FileExistsError as error:
            raise ValueError(_DUPLICATE_SPACE_NAME_MESSAGE) from error
    return target.resolve()

def _cleanup_failed_auto_space(target: Path) -> None:
    # Only remove files this create path itself owns. Never recursively delete
    # a directory that acquired any other content.
    for filename in (INVENTORY_FILENAME, METADATA_FILE):
        try:
            (target / filename).unlink(missing_ok=True)
        except OSError:
            pass
    try:
        target.rmdir()  # succeeds only when now empty
    except OSError:
        pass


def _space_id(raw: Any) -> str | None:
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _same(a: Any, b: Any) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def _json_file(path: Path, *, strict: bool = False) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError) as error:
        if strict:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            ) from error
        return None
    if not isinstance(data, dict):
        if strict:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            )
        return None
    return data


def _space(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("kind") not in {"drawer", "box", "surface", "portable", "pegboard", "storage_drawers"}:
        return None
    if raw.get("kind") == "storage_drawers":
        try:
            return normalise_storage_drawers_definition(raw)
        except (TypeError, ValueError):
            return None
    if raw.get("kind") == "pegboard":
        try:
            return normalise_space_definition(raw)
        except (TypeError, ValueError):
            return None
    try:
        size = [float(raw[axis]) for axis in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in size):
        return None
    res = {
        "kind": raw["kind"],
        "name": str(raw.get("name") or "").strip()[:80],
        "x": size[0], "y": size[1], "z": size[2],
    }
    if raw.get("kind") == "surface":
        trim_size = str(raw.get("trim_size") or "").strip().lower()
        expected = SURFACE_TRIM_HEIGHTS.get(trim_size)
        if expected is not None and math.isclose(size[2], expected, abs_tol=1e-6):
            res["trim_size"] = trim_size
            # Fix 095: preserve the durable maximum; seed a missing/damaged one
            # in memory from the current finished footprint (never growing it).
            res["max_x_mm"], res["max_y_mm"] = surface_maximums(
                raw, size[0], size[1], trim_size, strict=False)
    if raw.get("kind") in {"portable", "box"}:
        # A legacy Storage Box Space with no block reads the established
        # defaults; it needs no migration.
        try:
            res["storage_box"] = normalise_storage_box(raw.get("storage_box"))
        except ValueError:
            return None
    return res


def _repairable_cabinet(raw: Any) -> dict[str, Any] | None:
    """A typed Storage Drawers Space whose *known* cabinet settings are damaged.

    Returns the in-memory repaired copy (never written by classification), or
    None when ``raw`` is not a Storage Drawers Space at all.
    """
    if not isinstance(raw, dict) or raw.get("kind") != "storage_drawers":
        return None
    try:
        return reset_storage_drawers_definition(raw)
    except (TypeError, ValueError):
        return None


def _cabinet_recovery(folder: Path) -> dict[str, str] | None:
    """The plain-language reason a typed cabinet's stored settings are damaged."""
    metadata = _json_file(folder / METADATA_FILE)
    if not isinstance(metadata, dict) or metadata.get("folder_mode") != "space":
        return None
    raw = metadata.get("space")
    if not isinstance(raw, dict) or raw.get("kind") != "storage_drawers":
        return None
    problem = storage_drawers_definition_problem(raw)
    return {"message": problem} if problem else None


def _explicit_inventory(metadata: dict[str, Any] | None) -> bool | None:
    """A metadata file's own recorded choice, or None if it never said."""
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("inventory")
    return value if isinstance(value, bool) else None


def _default_inventory(folder: Path, prefs: dict[str, Any]) -> bool:
    """New folders, and old ones that never explicitly opted out, keep inventory."""
    if any(_same(folder, one) for one in prefs.get("no_inventory_folders") or []):
        return False
    return True


def _metadata_space_defaults(
    metadata: dict[str, Any], version: int,
) -> tuple[bool, dict[str, Any] | None, dict[str, Any]]:
    if version == 2:
        return True, None, {}
    keep = metadata.get("keep_bin_defaults", True)
    defaults = metadata.get("bin_defaults")
    part_defaults = metadata.get("part_defaults", {}) if version <= 5 else metadata.get("part_defaults")
    if (not isinstance(keep, bool)
            or (defaults is not None and not isinstance(defaults, dict))
            or not isinstance(part_defaults, dict)):
        raise FolderMetadataError(
            "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )
    return keep, defaults, part_defaults


def _metadata_resume(
    metadata: dict[str, Any], version: int,
) -> tuple[dict[str, Any] | None, bool]:
    """A typed Space's exact resume checkpoint, or (None, False) pre-v8.

    Kept separate from `_metadata_space_defaults()` so the existing
    nine-value `_folder_state()` tuple does not need to grow across many
    unrelated callers - `describe()` calls this directly instead.
    """
    if version < RESUME_REQUIRED_VERSION:
        return None, False
    design = metadata.get("resume_design")
    # A missing/explicit-null resume_design normalizes to null, but a v8
    # typed Space must carry a literal boolean resume_pending - a missing
    # field is malformed metadata, not a silent "not pending" - see Fix 032
    # Correction 1.
    pending = metadata.get("resume_pending", _UNSET)
    if design is not None and not isinstance(design, dict):
        raise FolderMetadataError(
            "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )
    if pending is _UNSET or not isinstance(pending, bool):
        raise FolderMetadataError(
            "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )
    return design, (pending if design is not None else False)


def _folder_state(
    folder: Path, prefs: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any] | None,
    bool,
    bool,
    dict[str, Any] | None,
    dict[str, Any],
    bool,
    str | None,
    dict[str, Any] | None,
]:
    """Classify a folder, and say where its typed-Space authority came from.

    The appended values are (8) `space_source` - the authority behind a typed
    result, one of "metadata", "legacy_metadata", "inventory_layout",
    "inventory_inferred" or None - and (9) `setup_prefill_space`, a read-only
    inventory/layout candidate that may prefill a matching setup card. A prefill
    candidate is suggestion-only: it is never the active `space`.
    """
    inventory = load_inventory(folder)
    layout = inventory["layout"] if isinstance(inventory["layout"], dict) else {}
    explicit_space = _space(layout.get("space"))
    # One read of the inventory/layout candidate, reused by every branch.
    inferred_space = _space(legacy_layout_space(layout))
    setup_prefill_space = explicit_space or inferred_space
    metadata_path = folder / METADATA_FILE
    metadata = _json_file(metadata_path, strict=metadata_path.exists())
    design_result = None
    metadata_defaults = (True, None, {})
    if metadata is not None:
        version = metadata.get("version")
        setup_version = metadata.get("setup_version")
        if isinstance(version, (int, float)) and version > METADATA_VERSION:
            raise FolderMetadataError("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.")
        if version not in SUPPORTED_METADATA_VERSIONS:
            raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")
        # v4 is already onboarded: it needs an identity migration, not setup.
        needs_setup = int(version) < 4 or setup_version != SPACE_SETUP_VERSION
        if metadata.get("folder_mode") == "space":
            metadata_space = _space(metadata.get("space"))
            damaged_cabinet = False
            if not metadata_space:
                # Damaged known cabinet settings keep the Space's identity and
                # its Inventory; the caller shows the recovery state.
                metadata_space = _repairable_cabinet(metadata.get("space"))
                damaged_cabinet = metadata_space is not None
            if metadata_space:
                metadata_defaults = _metadata_space_defaults(metadata, int(version))
                # Schema-validate the resume checkpoint here too, even though
                # the nine-value tuple below does not carry it - describe()
                # reads it again through the same helper to expose it.
                _metadata_resume(metadata, int(version))
                if int(version) >= SPACE_ID_REQUIRED_VERSION and _space_id(metadata.get("space_id")) is None:
                    raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
                chosen_space = metadata_space if damaged_cabinet else (explicit_space or metadata_space)
                # A stored legacy "box" identity always requires the
                # explicit migration/setup pass, even inside an otherwise
                # fully-valid v4 + setup_version-1 metadata file left over
                # from an earlier incomplete Fix 004 build - see Fix 004
                # Correction 8.D. A Surface missing its validated trim_size
                # is likewise recoverable migration input, not a corrupt
                # file - see Fix 004 Correction 11.A4.
                surface_needs_setup = (
                    chosen_space.get("kind") == "surface"
                    and "trim_size" not in chosen_space
                )
                space_needs_setup = (
                    needs_setup
                    or chosen_space.get("kind") == "box"
                    or surface_needs_setup
                )
                # Current typed metadata. Even if explicit layout.space supplies
                # the latest values, the authority to be a typed Space came
                # from current metadata.
                return "space", chosen_space, True, *metadata_defaults, space_needs_setup, "metadata", None
            raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
        if metadata.get("folder_mode") == "design":
            explicit = _explicit_inventory(metadata)
            enabled = explicit if explicit is not None else _default_inventory(folder, prefs)
            design_result = (
                "design", None, enabled, False, None, {}, needs_setup,
                None, setup_prefill_space,
            )
            # Completed current Design metadata is authoritative. Old inventory
            # layout.space may be a prefill, but cannot silently convert the
            # folder back into a typed Space.
            if not needs_setup:
                return design_result
        else:
            raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")

    if explicit_space:
        return "space", explicit_space, True, True, None, {}, True, "inventory_layout", None

    legacy_path = folder / LEGACY_METADATA_FILE
    legacy = _json_file(legacy_path, strict=legacy_path.exists())
    if legacy is not None:
        legacy_space = _space(legacy)
        if legacy_space:
            return "space", legacy_space, True, True, None, {}, True, "legacy_metadata", None
        if legacy.get("kind") != "none":
            raise FolderMetadataError("This folder contains legacy Wavefinity metadata that this version cannot safely read. The file was left unchanged.")

    if design_result is not None:
        return design_result

    if legacy is not None:
        return (
            "design", None, _default_inventory(folder, prefs),
            False, None, {}, True, None, setup_prefill_space,
        )

    if inferred_space:
        return (
            "space", inferred_space, True, True, None, {}, True,
            "inventory_inferred", None,
        )

    return (
        "design", None, _default_inventory(folder, prefs),
        False, None, {}, True, None, None,
    )


def _identity_state(folder: Path, mode: str, needs_setup: bool) -> tuple[str | None, bool]:
    """(space_id, needs_identity_migration) for a folder already classified.

    Only current-metadata typed Spaces have an ID. A configured v4 typed Space
    needs an identity migration - never another setup pass.
    """
    if mode != "space" or needs_setup:
        return None, False
    metadata = _json_file(folder / METADATA_FILE)
    if not metadata or metadata.get("folder_mode") != "space":
        return None, False
    version = metadata.get("version")
    return (_space_id(metadata.get("space_id")),
            isinstance(version, (int, float)) and version < SPACE_ID_REQUIRED_VERSION)


def folder_mode(folder: Path, prefs: dict[str, Any]) -> str:
    """Space status for a folder - independent of whether inventory is kept."""
    return _folder_state(folder, prefs)[0]


def inventory_enabled(folder: Path, prefs: dict[str, Any]) -> bool:
    """Inventory authority for local generation - independent of Space status."""
    return _folder_state(folder, prefs)[2]


def describe(folder: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    (mode, space, inventory, keep_bin_defaults, bin_defaults, part_defaults,
     needs_setup, space_source, setup_prefill_space) = _folder_state(folder, prefs)
    space_id, needs_identity = _identity_state(folder, mode, needs_setup)
    if mode == "space" and needs_setup:
        # A Space still needing setup may carry a valid ID (e.g. legacy box).
        metadata = _json_file(folder / METADATA_FILE)
        space_id = _space_id((metadata or {}).get("space_id"))
    # An exact resume checkpoint only ever comes from current v8+ typed-Space
    # metadata; a legacy/inferred Space or one still needing setup has none.
    resume_design: dict[str, Any] | None = None
    resume_pending = False
    if mode == "space" and space_source == "metadata" and not needs_setup:
        metadata_now = _json_file(folder / METADATA_FILE)
        resume_version = (metadata_now or {}).get("version")
        if isinstance(resume_version, (int, float)) and not isinstance(resume_version, bool):
            resume_design, resume_pending = _metadata_resume(metadata_now, int(resume_version))
    # Any existing Wavefinity trace - inventory, current metadata, or legacy
    # metadata - not just the inventory file, or a folder with metadata but
    # no inventory yet is wrongly treated as brand new and skips the
    # explicit Configure-vs-Choose-Another confirmation - matches hosted
    # SP.inspectHosted()'s exists flag - see Fix 004 Correction 8.C.
    wavefinity_exists = (
        bool(load_inventory(folder)["exists"])
        or (folder / METADATA_FILE).exists()
        or (folder / LEGACY_METADATA_FILE).exists()
    )
    return {
        "folder": str(folder),
        "folder_name": folder.name,
        "missing": not folder.is_dir(),
        "folder_mode": mode,
        "space": space,
        "space_id": space_id if mode == "space" else None,
        "inventory": inventory,
        "keep_bin_defaults": keep_bin_defaults,
        "bin_defaults": bin_defaults,
        "part_defaults": part_defaults,
        "needs_setup": needs_setup,
        "needs_identity_migration": needs_identity,
        "space_source": space_source,
        "setup_prefill_space": setup_prefill_space,
        "resume_design": resume_design,
        "resume_pending": resume_pending,
        "exists": wavefinity_exists,
        "no_inventory": not inventory,
        "cabinet_recovery": _cabinet_recovery(folder) if mode == "space" and not needs_setup else None,
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    cabinet = space.get("kind") == "storage_drawers"
    entry = {
        "folder": info["folder"],
        "name": space.get("name") or info["folder_name"],
        "folder_mode": info["folder_mode"],
        "space_id": info.get("space_id"),
        "inventory": info["inventory"],
        "kind": space.get("kind"),
        # A cabinet's top-level z is only a compatibility total, never a height.
        "size": None if cabinet or not space else [space["x"], space["y"], space["z"]],
        "missing": info["missing"],
    }
    if cabinet:
        entry["summary_text"] = f"{storage_drawers_recent_summary(space)} each"
    return entry


# ------------------------------------------------- Space registry (profile)


def _space_registry(prefs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    saved = prefs.get("space_registry")
    if not isinstance(saved, dict):
        return {}
    return {
        key: dict(value) for key, value in saved.items()
        if _space_id(key) == key and isinstance(value, dict)
    }


def _read_folder_id(folder: Path) -> str | None:
    """The Space ID a folder's own metadata carries, without raising."""
    data = _json_file(folder / METADATA_FILE)
    if data and data.get("folder_mode") == "space":
        return _space_id(data.get("space_id"))
    return None


def _registered_space_entry(info: dict[str, Any], last_seen: str | None) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "name": space.get("name") or info["folder_name"],
        "kind": space.get("kind"),
        "folder": info["folder"],
        "last_seen": last_seen,
    }


def _recover_registered_space(space_id: str, recorded_folder: Any) -> Path | None:
    """Find a renamed Space among its old folder's siblings by exact ID only.

    Never searches beyond the one parent directory.
    """
    if not recorded_folder:
        return None
    parent = Path(str(recorded_folder)).parent
    try:
        children = [one for one in parent.iterdir() if one.is_dir()]
    except OSError:
        return None
    matches = [one for one in children if _read_folder_id(one) == space_id]
    if len(matches) > 1:
        raise DuplicateSpaceError(
            "More than one folder claims the same Wavefinity Space identity. "
            "Use Open Existing Space to choose the right one."
        )
    return matches[0] if matches else None


def _resolve_registered(space_id: str, entry: dict[str, Any]) -> Path | None:
    """The registered Space's current folder: recorded path if it still holds
    that ID, else same-parent recovery. None if it cannot be found."""
    recorded = entry.get("folder")
    if not recorded:
        return None
    folder = Path(str(recorded))
    if folder.is_dir() and _read_folder_id(folder) == space_id:
        return folder
    return _recover_registered_space(space_id, recorded)


def _check_not_duplicate(space_id: str, target: Path, prefs: dict[str, Any]) -> None:
    entry = _space_registry(prefs).get(space_id)
    old = str((entry or {}).get("folder") or "")
    if (
        old and not _same(old, target)
        and Path(old).is_dir() and _read_folder_id(Path(old)) == space_id
    ):
        raise DuplicateSpaceError(DUPLICATE_MESSAGE)


def _metadata_version(folder: Path) -> int | None:
    data = _json_file(folder / METADATA_FILE)
    version = (data or {}).get("version")
    return int(version) if isinstance(version, (int, float)) and not isinstance(version, bool) else None


def _output_is_forgotten_typed_space(target: Path, prefs: dict[str, Any]) -> bool:
    """A current v5 typed Space whose ID is no longer registered was Forgotten;
    a restart must not silently re-register it from the saved output path."""
    info = describe(target, prefs)
    if info["folder_mode"] != "space" or not info["space_id"]:
        return False
    if _metadata_version(target) != METADATA_VERSION:
        return False
    return info["space_id"] not in _space_registry(prefs)


def structural_output_manifest(folder: Path, key: str) -> dict[str, Any] | None:
    """A materialized structural-output manifest from a folder's metadata."""
    data = _json_file(Path(folder) / METADATA_FILE)
    outputs = (data or {}).get("structural_outputs")
    value = outputs.get(key) if isinstance(outputs, dict) else None
    return value if isinstance(value, dict) else None
