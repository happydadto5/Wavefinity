"""Space setup layered on ordinary Wavefinity save folders.

Every selected folder gets ``.wavefinity.json``. Inventory and Space are
independent: ``inventory`` (default ``true``) is whether generated bins/B4Bs
are logged to ``<folder name> bins.md``, and ``folder_mode`` is ``design`` or
``space`` depending on whether the folder also represents one physical
Drawer, Surface, or Portable Storage case. A Space may also keep its own
sanitized bin-default snapshot. ``folder_mode=space`` always implies
``inventory=true`` - a Space cannot operate without the inventory its layout
depends on. Legacy markers (an old ``design`` marker with no ``inventory``
field, the historical ``no_inventory_folders`` preference,
``.wavefinity-space.json``, and the legacy ``box`` kind) remain readable and
are migrated additively.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from organizer_inventory import configure_space, legacy_layout_space, load_inventory
from organizer_product_rules import (
    SURFACE_TRIM_HEIGHTS,
    surface_trim_key_for_height,
)

MAX_RECENT = 8
METADATA_FILE = ".wavefinity.json"
LEGACY_METADATA_FILE = ".wavefinity-space.json"
METADATA_VERSION = 4
SPACE_SETUP_VERSION = 1
_UNSET = object()


class FolderMetadataError(ValueError):
    """The folder contains metadata that must not be guessed at or replaced."""


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
        needs_setup = version != METADATA_VERSION or setup_version != SPACE_SETUP_VERSION
        if isinstance(version, (int, float)) and version > METADATA_VERSION:
            raise FolderMetadataError("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.")
        if version not in (2, 3, METADATA_VERSION):
            raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")
        if metadata.get("folder_mode") == "space":
            metadata_space = _space(metadata.get("space"))
            if metadata_space:
                metadata_defaults = _metadata_space_defaults(metadata, int(version))
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
        "inventory": True if mode == "space" else bool(inventory),
    }
    if mode == "space" and space:
        payload["space"] = space
        saved_keep = True
        saved_defaults = None
        target = folder / METADATA_FILE
        if target.exists():
            current = _json_file(target, strict=True)
            version = current.get("version")
            if isinstance(version, (int, float)) and version > METADATA_VERSION:
                raise FolderMetadataError("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.")
            if version not in (2, 3, METADATA_VERSION) or current.get("folder_mode") not in {"design", "space"}:
                raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")
            if current.get("folder_mode") == "space":
                saved_keep, saved_defaults = _metadata_space_defaults(current, int(version))
        resolved_keep = saved_keep if keep_bin_defaults is _UNSET else bool(keep_bin_defaults)
        resolved_defaults = saved_defaults if bin_defaults is _UNSET else bin_defaults
        if resolved_defaults is not None and not isinstance(resolved_defaults, dict):
            raise ValueError("bin defaults must be an object or null")
        payload["keep_bin_defaults"] = resolved_keep
        payload["bin_defaults"] = resolved_defaults
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


def folder_mode(folder: Path, prefs: dict[str, Any]) -> str:
    """Space status for a folder - independent of whether inventory is kept."""
    return _folder_state(folder, prefs)[0]


def inventory_enabled(folder: Path, prefs: dict[str, Any]) -> bool:
    """Inventory authority for local generation - independent of Space status."""
    return _folder_state(folder, prefs)[2]


def describe(folder: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    mode, space, inventory, keep_bin_defaults, bin_defaults, needs_setup = _folder_state(folder, prefs)
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
        "inventory": inventory,
        "keep_bin_defaults": keep_bin_defaults,
        "bin_defaults": bin_defaults,
        "needs_setup": needs_setup,
        "exists": wavefinity_exists,
        "no_inventory": not inventory,
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "folder": info["folder"],
        "name": space.get("name") or info["folder_name"],
        "folder_mode": info["folder_mode"],
        "inventory": info["inventory"],
        "kind": space.get("kind"),
        "size": [space["x"], space["y"], space["z"]] if space else None,
        "missing": info["missing"],
    }


def space_routes(
    default_output: Path,
    load_preferences: Callable[[], dict[str, Any]],
    save_preferences: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Callable[[dict], dict]]:
    """Local-folder handlers. Hosted folders remain owned by the browser."""

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def recent(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        saved = prefs.get("recent_folders")
        if not isinstance(saved, list):
            saved = prefs.get("recent_spaces") or []
        entries = []
        for one in saved:
            if not isinstance(one, dict) or not one.get("folder"):
                continue
            target = Path(one["folder"])
            try:
                entries.append(_recent_entry(describe(target, prefs)))
            except FolderMetadataError:
                entries.append({
                    "folder": str(target),
                    "name": one.get("name") or target.name,
                    "folder_mode": one.get("folder_mode"),
                    "kind": one.get("kind"),
                    "size": one.get("size"),
                    "missing": not target.is_dir(),
                    "invalid": True,
                })
        return entries

    def reply(target: Path | None) -> dict[str, Any]:
        prefs = load_preferences()
        info = describe(target, prefs) if target else None
        return {
            "folder": info,
            "space": info,
            "recent": recent(prefs),
        }

    def remember(target: Path) -> None:
        prefs = load_preferences()
        info = describe(target, prefs)
        prefs = save_preferences({"output": str(target)})
        saved = prefs.get("recent_folders")
        if not isinstance(saved, list):
            saved = prefs.get("recent_spaces") or []
        others = [
            one for one in saved
            if isinstance(one, dict) and not _same(one.get("folder"), target)
        ]
        save_preferences({"recent_folders": [_recent_entry(info), *others][:MAX_RECENT]})


    def inspect(payload):
        return reply(folder(payload))

    def use_folder(payload):
        # The explicit "use this folder without a Space type" choice. May
        # write v4/setup_version-1 Design metadata, but must never demote a
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
        # path below - see Fix 004 Correction 7.H.
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
        target = folder(payload)
        prefs = load_preferences()
        saved = prefs.get("recent_folders")
        if not isinstance(saved, list):
            saved = prefs.get("recent_spaces") or []
        save_preferences({"recent_folders": [
            one for one in saved
            if isinstance(one, dict) and not _same(one.get("folder"), target)
        ]})
        return reply(None)

    return {
        "/api/space/inspect": inspect,
        # Open/remember only - never changes mode or rewrites metadata.
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
