"""Optional Space planning layered on ordinary Wavefinity save folders.

Every selected folder gets ``.wavefinity.json``. Inventory and Space are
independent: ``inventory`` (default ``true``) is whether generated bins/B4Bs
are logged to ``<folder name> bins.md``, and ``folder_mode`` is ``design`` or
``space`` depending on whether the folder also represents one physical
drawer or box. A Space may also keep its own sanitized bin-default snapshot.
``folder_mode=space`` always implies ``inventory=true`` - a Space cannot
operate without the inventory its layout depends on. Legacy
markers (an old ``design`` marker with no ``inventory`` field, the historical
``no_inventory_folders`` preference, ``.wavefinity-space.json``) remain
readable and are migrated additively.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from organizer_inventory import create_space, update_space, legacy_layout_space, load_inventory

MAX_RECENT = 8
METADATA_FILE = ".wavefinity.json"
LEGACY_METADATA_FILE = ".wavefinity-space.json"
METADATA_VERSION = 4
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
    if not isinstance(raw, dict) or raw.get("kind") not in {"drawer", "surface", "portable", "box"}:
        return None
    try:
        size = [float(raw[axis]) for axis in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in size):
        return None
    return {
        "/api/space/inspect": inspect,
        "/api/space/use-untyped": use_untyped,
        "/api/space/configure": configure,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/create": create,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
    }


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
    """Returns folder mode, Space, inventory, Keep Defaults, and its snapshot.
    Inventory and Space are independent except that Space always requires
    inventory on.

    Precedence, most authoritative first:

    1. an explicit ``layout.space``;
    2. current ``.wavefinity.json`` recording ``folder_mode: "space"``;
    3. legacy ``.wavefinity-space.json`` recording a Drawer/Box Space;
    4. current ``.wavefinity.json`` recording ``folder_mode: "design"``
       (defines the Design state and its inventory setting);
    5. legacy ``.wavefinity-space.json`` recording ``kind: "none"`` (Design);
    6. ``legacy_layout_space`` - a lossy reconstruction from the drawer layout
       alone that can only ever guess "drawer" (there is no Box concept for
       it to recover).

    A current ``design`` marker is not a positive Space identity and must
    never hide a genuine legacy Space, so both metadata files are read and
    validated before the classification is decided - the current file is
    never allowed to short-circuit past a legacy one that outranks it.
    """
    inventory = load_inventory(folder)
    layout = inventory["layout"] if isinstance(inventory["layout"], dict) else {}
    explicit_space = _space(layout.get("space"))
    metadata_path = folder / METADATA_FILE
    metadata = _json_file(metadata_path, strict=metadata_path.exists())
    design_result: tuple[str, None, bool, bool, None] | None = None
    metadata_defaults = (True, None)
    if metadata is not None:
        version = metadata.get("version")
        if isinstance(version, (int, float)) and version > METADATA_VERSION:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata from a newer version. The file was left unchanged."
            )
        if version not in (2, METADATA_VERSION):
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            )
        if metadata.get("folder_mode") == "space":
            metadata_space = _space(metadata.get("space"))
            if metadata_space:
                metadata_defaults = _metadata_space_defaults(metadata, int(version))
                if explicit_space:
                    return "space", explicit_space, True, *metadata_defaults, False
                return "space", metadata_space, True, *metadata_defaults, metadata.get("setup_version") != 1
            raise FolderMetadataError(
                "This folder's Space information is incomplete or damaged. Nothing was changed."
            )
        if metadata.get("folder_mode") == "design":
            explicit = _explicit_inventory(metadata)
            enabled = explicit if explicit is not None else _default_inventory(folder, prefs)
            design_result = ("design", None, enabled, False, None, metadata.get("setup_version") != 1)
        else:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            )

    if explicit_space:
        return "space", explicit_space, True, True, None, False

    legacy_path = folder / LEGACY_METADATA_FILE
    legacy = _json_file(legacy_path, strict=legacy_path.exists())
    if legacy is not None:
        legacy_space = _space(legacy)
        if legacy_space:
            # Outranks a stale/absent current "design" marker, but current
            # "space" metadata already returned above and never reaches here.
            return "space", legacy_space, True, True, None, True
        if legacy.get("kind") != "none":
            raise FolderMetadataError(
                "This folder contains legacy Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            )
        # legacy "kind: none" is just Design - the current metadata's own
        # design result (if any) still wins so its inventory choice survives.

    if design_result is not None:
        return design_result
    if legacy is not None:
        # legacy was read above and, having reached here, was "kind: none".
        return "design", None, _default_inventory(folder, prefs), False, None, True

    # No authoritative Space identity anywhere - only now fall back to a
    # lossy reconstruction from the drawer layout alone, which can only ever
    # infer "drawer" (there is no historical way to recover "box" from it).
    inferred_space = _space(legacy_layout_space(layout))
    if inferred_space:
        return "space", inferred_space, True, True, None, True
    return "design", None, _default_inventory(folder, prefs), False, None, True


def _write_metadata(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
    *, keep_bin_defaults: Any = _UNSET, bin_defaults: Any = _UNSET,
    setup_version: int = 1,
) -> None:
    payload: dict[str, Any] = {
        "version": METADATA_VERSION,
        "setup_version": setup_version,
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
                raise FolderMetadataError(
                    "This folder contains Wavefinity metadata from a newer version. The file was left unchanged."
                )
            if version not in (2, METADATA_VERSION) or current.get("folder_mode") not in {"design", "space"}:
                raise FolderMetadataError(
                    "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
                )
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


def _migrate_metadata(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
) -> None:
    # No silent auto-migrations on load/inspect anymore
    pass



def folder_mode(folder: Path, prefs: dict[str, Any]) -> str:
    """Space status for a folder - independent of whether inventory is kept."""
    return _folder_state(folder, prefs)[0]


def inventory_enabled(folder: Path, prefs: dict[str, Any]) -> bool:
    """Inventory authority for local generation - independent of Space status."""
    return _folder_state(folder, prefs)[2]


def describe(folder: Path, prefs: dict[str, Any], *, migrate: bool = False) -> dict[str, Any]:
    """Describe a save folder without confusing it with its optional Space."""
    mode, space, inventory, keep_bin_defaults, bin_defaults, needs_setup = _folder_state(folder, prefs)
    inventory_exists = bool(load_inventory(folder)["exists"])
    return {
        "/api/space/inspect": inspect,
        "/api/space/use-untyped": use_untyped,
        "/api/space/configure": configure,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/create": create,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "/api/space/inspect": inspect,
        "/api/space/use-untyped": use_untyped,
        "/api/space/configure": configure,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/create": create,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
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
        info = describe(target, prefs, migrate=True) if target else None
        return {
        "/api/space/inspect": inspect,
        "/api/space/use-untyped": use_untyped,
        "/api/space/configure": configure,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/create": create,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
    }
