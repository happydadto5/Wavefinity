"""Space setup layered on ordinary Wavefinity save folders.

Every selected folder gets ``.wavefinity.json``. Inventory and Space are
independent: ``inventory`` (default ``true``) is whether generated bins/B4Bs
are logged to ``Wavefinity bins.md``, and ``folder_mode`` is ``design`` or
``space`` depending on whether the folder also represents one physical
Drawer, Surface, or Portable Storage case. A Space may also keep its own
sanitized bin-default snapshot. ``folder_mode=space`` always implies
``inventory=true`` - a Space cannot operate without the inventory its layout
depends on. Legacy markers (an old ``design`` marker with no ``inventory``
field, the historical ``no_inventory_folders`` preference,
``.wavefinity-space.json``, and the legacy ``box`` kind) remain readable and
are migrated additively.

A typed Space's permanent identity is ``space_id``, a UUID stored at the top
level of its ``.wavefinity.json`` - never its path, folder name or display
name. The per-user profile keeps a ``space_registry`` (id -> name, kind, last
known folder, last_seen) as an index only; the folder stays authoritative.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Callable
import uuid

from organizer_inventory import (
    configure_space, legacy_layout_space, load_inventory, resolve_inventory_path,
)
from organizer_product_rules import SURFACE_TRIM_HEIGHTS

MAX_RECENT = 8
METADATA_FILE = ".wavefinity.json"
LEGACY_METADATA_FILE = ".wavefinity-space.json"
METADATA_VERSION = 5
SPACE_SETUP_VERSION = 1
SUPPORTED_METADATA_VERSIONS = {2, 3, 4, 5}
_UNSET = object()


class FolderMetadataError(ValueError):
    """The folder contains metadata that must not be guessed at or replaced."""


class DuplicateSpaceError(ValueError):
    """Two distinct folders carry the same Space identity."""


DUPLICATE_MESSAGE = (
    "This folder is a copy of an existing Wavefinity Space and has the same Space identity. "
    "The existing Space was left unchanged."
)


def _space_id(raw: Any) -> str | None:
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None


def _new_space_id() -> str:
    return str(uuid.uuid4())


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
    if not isinstance(raw, dict) or raw.get("kind") not in {"drawer", "box", "surface", "portable"}:
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
    return res


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
) -> tuple[bool, dict[str, Any] | None]:
    if version == 2:
        return True, None
    keep = metadata.get("keep_bin_defaults", True)
    defaults = metadata.get("bin_defaults")
    if not isinstance(keep, bool) or (defaults is not None and not isinstance(defaults, dict)):
        raise FolderMetadataError(
            "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )
    return keep, defaults


def _folder_state(
    folder: Path, prefs: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, bool, bool, dict[str, Any] | None, bool]:
    inventory = load_inventory(folder)
    layout = inventory["layout"] if isinstance(inventory["layout"], dict) else {}
    explicit_space = _space(layout.get("space"))
    metadata_path = folder / METADATA_FILE
    metadata = _json_file(metadata_path, strict=metadata_path.exists())
    design_result = None
    metadata_defaults = (True, None)
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
            if metadata_space:
                metadata_defaults = _metadata_space_defaults(metadata, int(version))
                if int(version) >= METADATA_VERSION and _space_id(metadata.get("space_id")) is None:
                    raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
                chosen_space = explicit_space or metadata_space
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
                return "space", chosen_space, True, *metadata_defaults, space_needs_setup
            raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
        if metadata.get("folder_mode") == "design":
            explicit = _explicit_inventory(metadata)
            enabled = explicit if explicit is not None else _default_inventory(folder, prefs)
            design_result = ("design", None, enabled, False, None, needs_setup)
        else:
            raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")

    if explicit_space:
        return "space", explicit_space, True, True, None, True

    legacy_path = folder / LEGACY_METADATA_FILE
    legacy = _json_file(legacy_path, strict=legacy_path.exists())
    if legacy is not None:
        legacy_space = _space(legacy)
        if legacy_space:
            return "space", legacy_space, True, True, None, True
        if legacy.get("kind") != "none":
            raise FolderMetadataError("This folder contains legacy Wavefinity metadata that this version cannot safely read. The file was left unchanged.")

    if design_result is not None:
        return design_result
    if legacy is not None:
        return "design", None, _default_inventory(folder, prefs), False, None, True

    inferred_space = _space(legacy_layout_space(layout))
    if inferred_space:
        return "space", inferred_space, True, True, None, True
    return "design", None, _default_inventory(folder, prefs), False, None, True


def _write_metadata(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
    *, keep_bin_defaults: Any = _UNSET, bin_defaults: Any = _UNSET,
) -> None:
    payload: dict[str, Any] = {
        "version": METADATA_VERSION,
        "setup_version": SPACE_SETUP_VERSION,
        "folder_mode": mode,
    }
    if mode == "space" and space:
        payload["space_id"] = _new_space_id()
        payload["inventory"] = True
        payload["space"] = space
        saved_keep = True
        saved_defaults = None
        target = folder / METADATA_FILE
        if target.exists():
            current = _json_file(target, strict=True)
            version = current.get("version")
            if isinstance(version, (int, float)) and version > METADATA_VERSION:
                raise FolderMetadataError("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.")
            if version not in SUPPORTED_METADATA_VERSIONS or current.get("folder_mode") not in {"design", "space"}:
                raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")
            if current.get("folder_mode") == "space":
                saved_keep, saved_defaults = _metadata_space_defaults(current, int(version))
                # The one choke point that keeps a Space's identity: an
                # existing valid ID is always preserved. Only pre-v5 metadata
                # may gain one; damaged v5 must never be re-identified.
                current_id = _space_id(current.get("space_id"))
                if current_id is not None:
                    payload["space_id"] = current_id
                elif int(version) >= METADATA_VERSION:
                    raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
        resolved_keep = saved_keep if keep_bin_defaults is _UNSET else bool(keep_bin_defaults)
        resolved_defaults = saved_defaults if bin_defaults is _UNSET else bin_defaults
        if resolved_defaults is not None and not isinstance(resolved_defaults, dict):
            raise ValueError("bin defaults must be an object or null")
        payload["keep_bin_defaults"] = resolved_keep
        payload["bin_defaults"] = resolved_defaults
    else:
        payload["inventory"] = bool(inventory)
    target = folder / METADATA_FILE
    temp = folder / f"{METADATA_FILE}.tmp"
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def _unused_migrate(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
) -> None:
    """Only rewrite metadata that does not already, positively, say what this
    resolves to - so a stale/incomplete record (a "design" marker a legacy
    Space has just outranked, or old "design" metadata silent about
    inventory) migrates once, deterministically, and an already-correct file
    is left untouched."""
    target = folder / METADATA_FILE
    if target.exists():
        try:
            metadata = _json_file(target, strict=True)
            if metadata.get("version") not in (2, METADATA_VERSION):
                return
            if metadata.get("folder_mode") not in {"design", "space"}:
                return
            if metadata.get("folder_mode") == "space" and not _space(metadata.get("space")):
                return
            if metadata.get("version") == 2:
                pass
            elif mode == "space":
                if metadata.get("folder_mode") == "space" and _space(metadata.get("space")) == space:
                    return
                # else: stored "design" (or a differing space) - a legacy
                # identity just took over, fall through and rewrite it.
            elif metadata.get("folder_mode") == "design" and _explicit_inventory(metadata) is not None:
                return
        except FolderMetadataError:
            return
    _write_metadata(folder, mode, space, inventory)


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
    return _space_id(metadata.get("space_id")), isinstance(version, (int, float)) and version < METADATA_VERSION


def folder_mode(folder: Path, prefs: dict[str, Any]) -> str:
    """Space status for a folder - independent of whether inventory is kept."""
    return _folder_state(folder, prefs)[0]


def inventory_enabled(folder: Path, prefs: dict[str, Any]) -> bool:
    """Inventory authority for local generation - independent of Space status."""
    return _folder_state(folder, prefs)[2]


def describe(folder: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    mode, space, inventory, keep_bin_defaults, bin_defaults, needs_setup = _folder_state(folder, prefs)
    space_id, needs_identity = _identity_state(folder, mode, needs_setup)
    if mode == "space" and needs_setup:
        # A Space still needing setup may carry a valid ID (e.g. legacy box).
        metadata = _json_file(folder / METADATA_FILE)
        space_id = _space_id((metadata or {}).get("space_id"))
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
        "needs_setup": needs_setup,
        "needs_identity_migration": needs_identity,
        "exists": wavefinity_exists,
        "no_inventory": not inventory,
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "folder": info["folder"],
        "name": space.get("name") or info["folder_name"],
        "folder_mode": info["folder_mode"],
        "space_id": info.get("space_id"),
        "inventory": info["inventory"],
        "kind": space.get("kind"),
        "size": [space["x"], space["y"], space["z"]] if space else None,
        "missing": info["missing"],
    }


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


def _registered_space_entry(info: dict[str, Any], last_seen: str) -> dict[str, Any]:
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


def prepare_folder_for_open(target: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    """The narrow technical-maintenance step of opening a folder.

    Read-only classification first; a folder that still needs Fix-004 setup is
    returned untouched. Otherwise: duplicate-copy check, unambiguous inventory
    filename migration, then v4 -> v5 metadata (typed Spaces gain/keep their
    ID). It never changes kind, name, dimensions, inventory choice or layout,
    and never touches the profile registry - the caller does that last.
    """
    info = describe(target, prefs)
    if info["needs_setup"]:
        return info
    typed = info["folder_mode"] == "space"
    if typed and info["space_id"]:
        _check_not_duplicate(info["space_id"], target, prefs)
    if info["inventory"]:
        resolve_inventory_path(target, migrate=True)
    if typed and info["needs_identity_migration"]:
        _write_metadata(
            target, "space", info["space"], True,
            keep_bin_defaults=info["keep_bin_defaults"], bin_defaults=info["bin_defaults"],
        )
    elif not typed and (_metadata_version(target) or METADATA_VERSION) < METADATA_VERSION \
            and (target / METADATA_FILE).exists():
        _write_metadata(target, "design", None, info["inventory"])
    else:
        return info
    info = describe(target, prefs)
    if typed and not info["space_id"]:
        raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
    return info


def space_routes(
    default_output: Path,
    load_preferences: Callable[[], dict[str, Any]],
    save_preferences: Callable[[dict[str, Any]], dict[str, Any]],
    mutate_preferences: Callable[[Callable[[dict[str, Any]], Any]], dict[str, Any]] | None = None,
) -> dict[str, Callable[[dict], dict]]:
    """Local-folder handlers. Hosted folders remain owned by the browser.

    ``mutate_preferences`` is the atomic read-modify-write the app supplies;
    without it a plain load/save pair stands in.
    """
    if mutate_preferences is None:
        def mutate_preferences(mutator):
            prefs = load_preferences()
            result = mutator(prefs)
            return save_preferences(result if isinstance(result, dict) else prefs)

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def path_recents(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        saved = prefs.get("recent_folders")
        if not isinstance(saved, list):
            saved = prefs.get("recent_spaces") or []
        return [one for one in saved if isinstance(one, dict) and one.get("folder")]

    def recent(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        registry = _space_registry(prefs)
        saved = path_recents(prefs)
        active = _space_id(prefs.get("active_space_id"))
        absorbed: dict[str, dict[str, Any]] = {}
        repairs: dict[str, dict[str, Any]] = {}

        # Legacy path-based entries that already carry an ID move into the
        # registry; ones without an ID stay shortcuts until upgraded.
        kept_paths = []
        for one in saved:
            try:
                info = describe(Path(one["folder"]), prefs)
            except ValueError:
                kept_paths.append(one)
                continue
            sid = info["space_id"]
            if info["folder_mode"] == "space" and sid:
                if sid not in registry:
                    registry[sid] = absorbed[sid] = _registered_space_entry(
                        info, one.get("last_seen") or _utc_now(),
                    )
            else:
                kept_paths.append(one)

        items: list[tuple[str | None, dict[str, Any]]] = []
        for sid, entry in list(registry.items()):
            stamp = entry.get("last_seen")
            recorded = Path(str(entry.get("folder") or ""))
            base = {
                "folder": str(recorded), "name": entry.get("name") or recorded.name,
                "folder_mode": "space", "space_id": sid,
                "kind": entry.get("kind"), "size": None,
            }
            try:
                found = _resolve_registered(sid, entry)
            except DuplicateSpaceError as error:
                items.append((stamp, {**base, "missing": False, "invalid": True, "conflict": True, "error": str(error)}))
                continue
            if found is None:
                items.append((stamp, {**base, "missing": True}))
                continue
            try:
                info = describe(found, prefs)
            except ValueError:
                items.append((stamp, {**base, "folder": str(found), "missing": False, "invalid": True}))
                continue
            # Folder metadata wins over the cached name/kind/path.
            fresh = {
                key: value for key, value in _registered_space_entry(info, "").items()
                if key != "last_seen" and value
            }
            if any(entry.get(key) != value for key, value in fresh.items()):
                repairs[sid] = fresh
            items.append((stamp, _recent_entry(info)))

        if repairs or absorbed:
            def apply(current: dict[str, Any]) -> None:
                reg = _space_registry(current)
                for sid, entry in absorbed.items():
                    reg.setdefault(sid, entry)
                for sid, fresh in repairs.items():
                    if sid in reg:
                        reg[sid] = {**reg[sid], **fresh}
                        if sid == active and _space_id(current.get("active_space_id")) == sid:
                            current["output"] = fresh["folder"]
                current["space_registry"] = reg
                if absorbed:
                    current["recent_folders"] = [
                        one for one in path_recents(current)
                        if not any(_same(one.get("folder"), e["folder"]) for e in absorbed.values())
                    ]
            mutate_preferences(apply)

        for one in kept_paths:
            target = Path(one["folder"])
            try:
                entry = _recent_entry(describe(target, prefs))
            except ValueError:
                entry = {
                    "folder": str(target),
                    "name": one.get("name") or target.name,
                    "folder_mode": one.get("folder_mode"),
                    "space_id": None,
                    "kind": one.get("kind"),
                    "size": one.get("size"),
                    "missing": not target.is_dir(),
                    "invalid": True,
                }
            items.append((one.get("last_seen"), entry))

        # Newest first; legacy entries with no timestamp keep their order.
        stamped = sorted((x for x in items if x[0]), key=lambda x: x[0], reverse=True)
        plain = [x for x in items if not x[0]]
        return [entry for _stamp, entry in [*stamped, *plain]][:MAX_RECENT]

    def reply(target: Path | None) -> dict[str, Any]:
        prefs = load_preferences()
        info = describe(target, prefs) if target else None
        return {
            "folder": info,
            "space": info,
            "recent": recent(prefs),
        }

    def remember_prepared(target: Path, info: dict[str, Any]) -> None:
        """Advance the profile last: only after folder maintenance succeeded."""
        stamp = _utc_now()
        typed = info["folder_mode"] == "space"
        space_id = info["space_id"]
        if typed and not space_id:
            raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")

        def apply(prefs: dict[str, Any]) -> None:
            others = [
                one for one in path_recents(prefs) if not _same(one.get("folder"), target)
            ]
            prefs["output"] = str(target)
            if typed:
                registry = _space_registry(prefs)
                registry[space_id] = _registered_space_entry(info, stamp)
                prefs["space_registry"] = registry
                prefs["active_space_id"] = space_id
                prefs["recent_folders"] = others[:MAX_RECENT]
            else:
                prefs["active_space_id"] = None
                prefs["recent_folders"] = [
                    {**_recent_entry(info), "last_seen": stamp}, *others,
                ][:MAX_RECENT]

        mutate_preferences(apply)

    def remember(target: Path) -> dict[str, Any]:
        info = prepare_folder_for_open(target, load_preferences())
        if info["needs_setup"]:
            raise ValueError("this folder must complete Space setup before it can be opened")
        remember_prepared(target, info)
        return info

    def startup(_payload):
        prefs = load_preferences()
        target: Path | None = None
        space_id = _space_id(prefs.get("active_space_id"))
        if space_id:
            entry = _space_registry(prefs).get(space_id)
            try:
                target = _resolve_registered(space_id, entry) if entry else None
            except DuplicateSpaceError:
                target = None
            if target is not None and not _same(target, (entry or {}).get("folder") or ""):
                def repair(current: dict[str, Any]) -> None:
                    registry = _space_registry(current)
                    if space_id in registry:
                        registry[space_id]["folder"] = str(target)
                        current["space_registry"] = registry
                        current["output"] = str(target)
                mutate_preferences(repair)
        elif prefs.get("output"):
            target = Path(str(prefs["output"])).expanduser()
        if target is None or not target.is_dir():
            return {"folder": None, "space": None, "recent": recent(load_preferences())}
        target = target.resolve()
        info = describe(target, prefs)
        if not info["needs_setup"]:
            info = prepare_folder_for_open(target, prefs)
            if not info["needs_setup"]:
                remember_prepared(target, info)
        return {"folder": info, "space": info, "recent": recent(load_preferences())}

    def inspect(payload):
        return reply(folder(payload))

    def use_folder(payload):
        # The explicit "use this folder without a Space type" choice. May
        # write v5/setup_version-1 Design metadata, but must never demote a
        # folder already classified as a Space - fully configured *or* still
        # needing its one-time setup pass. A Space that needs setup must go
        # through the explicit migration/setup flow instead, never straight
        # to Design - see Fix 004 Correction 8.B. Opening/remembering a
        # folder without changing it is /api/space/open (open_folder) /
        # /api/folder/use, not this.
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        mode, space, inventory, _keep, _defaults, needs_setup = _folder_state(target, load_preferences())
        if mode == "space":
            raise ValueError(f"this folder already holds the space {(space or {}).get('name')!r}")
        if needs_setup or mode != "design":
            _write_metadata(target, "design", None, inventory)
        remember(target)
        return reply(target)

    def configure(payload):
        # A genuinely new typed Space: collision-protected, refuses a folder
        # that already holds a configured typed Space. Never accepts legacy
        # "box" - that only ever comes from the Configure Existing/migration
        # path below - see Fix 004 Correction 7.H. A new Space always gets a
        # brand-new ID; the caller can never supply one.
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        raw_def = {"name": payload.get("name"), "kind": payload.get("kind"), "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]

        result = configure_space(target, raw_def=raw_def, mode="create")
        space = result["layout"]["space"]
        _write_metadata(target, "space", space, keep_bin_defaults=True)
        remember(target)
        return reply(target)

    def configure_migrate(payload):
        # The user's explicit Configure Existing / migration choice for an
        # already-selected folder: a v2/v3/legacy/inventory-derived Space, or
        # a plain design/inventory folder. Never rejected merely because
        # layout.space already exists - configure_space(mode="update")
        # replaces the Space definition in place and preserves everything
        # else (inventory rows, quantities, placements, drawers, generated
        # parts). Existing keep_bin_defaults/bin_defaults are preserved
        # rather than reset. allow_legacy=True lets this path read a legacy
        # "box" kind during migration, but the actual persisted kind is
        # whatever the setup form chose (always "portable", never a new
        # "box" - see Fix 004 Correction 7.H).
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("save folder not found")
        _mode, _space, inventory, keep, defaults, _needs_setup = _folder_state(target, load_preferences())
        raw_def = {"name": payload.get("name"), "kind": payload.get("kind"), "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]

        result = configure_space(target, raw_def=raw_def, mode="update", allow_legacy=True)
        space = result["layout"]["space"]
        _write_metadata(target, "space", space, inventory, keep_bin_defaults=keep, bin_defaults=defaults)
        remember(target)
        return reply(target)

    def update(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("save folder not found")
        mode, existing_space, inventory, keep, defaults, needs_setup = _folder_state(target, load_preferences())
        if mode != "space":
            raise ValueError("not a typed space")

        raw_def = {"name": payload.get("name"), "kind": existing_space["kind"], "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]

        result = configure_space(target, raw_def=raw_def, mode="update")
        space = result["layout"]["space"]
        _write_metadata(target, "space", space, keep_bin_defaults=keep, bin_defaults=defaults)
        remember(target)
        return reply(target)

    def set_inventory(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        prefs = load_preferences()
        mode, space, _current, keep, defaults, _needs_setup = _folder_state(target, prefs)
        inventory = bool(payload.get("inventory", True))
        if mode == "space" and not inventory:
            raise ValueError("Space planning needs this folder's inventory turned on.")
        _write_metadata(target, mode, space, inventory, keep_bin_defaults=keep, bin_defaults=defaults)
        # Keep the legacy preference in step, in case anything still reads it.
        kept = [
            one for one in (prefs.get("no_inventory_folders") or [])
            if not _same(one, target)
        ]
        if not inventory:
            kept.append(str(target))
        save_preferences({"no_inventory_folders": kept})
        remember(target)
        return reply(target)

    def set_bin_defaults(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        mode, space, inventory, keep, defaults, _needs_setup = _folder_state(target, load_preferences())
        if mode != "space":
            raise ValueError("bin defaults belong to a Space folder")
        new_keep = bool(payload["keep_bin_defaults"]) if "keep_bin_defaults" in payload else keep
        new_defaults = payload.get("bin_defaults") if "bin_defaults" in payload else defaults
        if new_defaults is not None and not isinstance(new_defaults, dict):
            raise ValueError("bin defaults must be an object or null")
        _write_metadata(
            target, mode, space, inventory,
            keep_bin_defaults=new_keep, bin_defaults=new_defaults,
        )
        remember(target)
        return reply(target)

    def open_folder(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        remember(target)
        return reply(target)

    def forget(payload):
        # Removes only the profile shortcut; the folder, its metadata, its
        # inventory and its Space ID are never touched.
        space_id = _space_id(payload.get("space_id"))
        target = folder(payload) if payload.get("output") else None

        def apply(prefs: dict[str, Any]) -> None:
            if space_id:
                registry = _space_registry(prefs)
                if registry.pop(space_id, None) is not None:
                    prefs["space_registry"] = registry
                if _space_id(prefs.get("active_space_id")) == space_id:
                    prefs["active_space_id"] = None
            elif target is not None:
                registry = _space_registry(prefs)
                for key, entry in list(registry.items()):
                    if _same(entry.get("folder") or "", target):
                        del registry[key]
                        if _space_id(prefs.get("active_space_id")) == key:
                            prefs["active_space_id"] = None
                if "space_registry" in prefs:
                    prefs["space_registry"] = registry
            if target is not None:
                prefs["recent_folders"] = [
                    one for one in path_recents(prefs)
                    if not _same(one.get("folder"), target)
                ]

        mutate_preferences(apply)
        return reply(None)

    return {
        "/api/space/inspect": inspect,
        # Local startup: resolves the active Space by ID, not just a path.
        "/api/space/startup": startup,
        # Open/remember only - never changes mode or rewrites metadata
        # beyond the technical identity/inventory upgrades in remember().
        "/api/folder/use": open_folder,
        # The explicit "use without a Space type" choice - may write.
        "/api/space/use-untyped": use_folder,
        "/api/space/create": configure,
        "/api/space/configure": configure_migrate,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
    }
