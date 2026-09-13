"""Optional Space planning layered on ordinary Wavefinity save folders.

Every selected folder gets ``.wavefinity.json``. ``folder_mode=design`` is
the default and keeps no inventory. ``folder_mode=space`` adds one physical
drawer or box plus the existing inventory/layout file. Legacy markers remain
readable and are migrated additively.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Callable

from organizer_inventory import create_space, load_inventory

MAX_RECENT = 8
METADATA_FILE = ".wavefinity.json"
LEGACY_METADATA_FILE = ".wavefinity-space.json"
METADATA_VERSION = 2


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
    if not isinstance(raw, dict) or raw.get("kind") not in {"drawer", "box"}:
        return None
    try:
        size = [float(raw[axis]) for axis in ("x", "y", "z")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in size):
        return None
    return {
        "kind": raw["kind"],
        "name": str(raw.get("name") or "").strip()[:80],
        "x": size[0], "y": size[1], "z": size[2],
    }


def _folder_state(folder: Path, prefs: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    inventory = load_inventory(folder)
    layout = inventory["layout"] if isinstance(inventory["layout"], dict) else {}
    inventory_space = _space(layout.get("space"))
    if inventory_space:
        return "space", inventory_space

    metadata_path = folder / METADATA_FILE
    metadata = _json_file(metadata_path, strict=metadata_path.exists())
    if metadata is not None:
        version = metadata.get("version")
        if isinstance(version, (int, float)) and version > METADATA_VERSION:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata from a newer version. The file was left unchanged."
            )
        if version != METADATA_VERSION:
            raise FolderMetadataError(
                "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
            )
        if metadata.get("folder_mode") == "design":
            return "design", None
        if metadata.get("folder_mode") == "space":
            metadata_space = _space(metadata.get("space"))
            if metadata_space:
                return "space", metadata_space
            raise FolderMetadataError(
                "This folder's Space information is incomplete or damaged. Nothing was changed."
            )
        raise FolderMetadataError(
            "This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )

    legacy_path = folder / LEGACY_METADATA_FILE
    legacy = _json_file(legacy_path, strict=legacy_path.exists())
    if legacy is not None:
        legacy_space = _space(legacy)
        if legacy_space:
            return "space", legacy_space
        if legacy.get("kind") == "none":
            return "design", None
        raise FolderMetadataError(
            "This folder contains legacy Wavefinity metadata that this version cannot safely read. The file was left unchanged."
        )
    if any(_same(folder, one) for one in prefs.get("no_inventory_folders") or []):
        return "design", None
    return "design", None


def _write_metadata(folder: Path, mode: str, space: dict[str, Any] | None = None) -> None:
    payload: dict[str, Any] = {"version": METADATA_VERSION, "folder_mode": mode}
    if mode == "space" and space:
        payload["space"] = space
    target = folder / METADATA_FILE
    temp = folder / f"{METADATA_FILE}.tmp"
    temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temp.replace(target)


def _migrate_metadata(folder: Path, mode: str, space: dict[str, Any] | None = None) -> None:
    """Only rewrite absent or positively recognized current metadata."""
    target = folder / METADATA_FILE
    if target.exists():
        try:
            metadata = _json_file(target, strict=True)
            if metadata.get("version") != METADATA_VERSION:
                return
            if metadata.get("folder_mode") not in {"design", "space"}:
                return
            if metadata.get("folder_mode") == "space" and not _space(metadata.get("space")):
                return
        except FolderMetadataError:
            return
    _write_metadata(folder, mode, space)


def folder_mode(folder: Path, prefs: dict[str, Any]) -> str:
    """Inventory authority for local generation."""
    return _folder_state(folder, prefs)[0]


def describe(folder: Path, prefs: dict[str, Any], *, migrate: bool = False) -> dict[str, Any]:
    """Describe a save folder without confusing it with its optional Space."""
    mode, space = _folder_state(folder, prefs)
    if migrate and folder.is_dir():
        try:
            inventory = load_inventory(folder)
            layout = inventory["layout"] if isinstance(inventory["layout"], dict) else {}
            if mode == "space" and space and not _space(layout.get("space")):
                create_space(folder, **space)
            _migrate_metadata(folder, mode, space)
        except OSError:
            pass
    inventory_exists = bool(load_inventory(folder)["exists"])
    return {
        "folder": str(folder),
        "folder_name": folder.name,
        "missing": not folder.is_dir(),
        "folder_mode": mode,
        "space": space,
        # Compatibility for a page loaded before the folder-mode API shipped.
        "exists": inventory_exists,
        "no_inventory": mode == "design",
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "folder": info["folder"],
        "name": space.get("name") or info["folder_name"],
        "folder_mode": info["folder_mode"],
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
        return [
            _recent_entry(describe(Path(one["folder"]), prefs))
            for one in saved
            if isinstance(one, dict) and one.get("folder")
        ]

    def reply(target: Path | None) -> dict[str, Any]:
        prefs = load_preferences()
        info = describe(target, prefs, migrate=True) if target else None
        return {
            "folder": info,
            "space": info,
            "recent": recent(prefs),
        }

    def remember(target: Path) -> None:
        prefs = save_preferences({"output": str(target)})
        info = describe(target, prefs, migrate=True)
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
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        mode, space = _folder_state(target, load_preferences())
        _migrate_metadata(target, mode, space)
        remember(target)
        return reply(target)

    def create(payload):
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        mode, existing_space = _folder_state(target, load_preferences())
        if mode == "space":
            raise ValueError(f"this folder already holds the space {(existing_space or {}).get('name')!r}")
        result = create_space(
            target, name=payload.get("name"), kind=payload.get("kind"),
            x=payload.get("x"), y=payload.get("y"), z=payload.get("z"),
        )
        space = result["layout"]["space"]
        _write_metadata(target, "space", space)
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
        "/api/folder/use": use_folder,
        "/api/space/create": create,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": use_folder,
        "/api/space/forget": forget,
    }
