"""Spaces: each save folder is one space - a drawer, or a box (a Bin for Bins
case whose inside is the space) - with its own inventory file.  A folder can
instead be marked *no inventory*: bins are saved there and nothing is tracked.

The space itself (name, kind, inside size) lives in the inventory file's layout
block (see organizer_inventory.create_space).  The recent-spaces list and the
no-inventory folders live in the app's preferences, since a no-inventory
folder has no file of its own to hold that choice.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from organizer_inventory import create_space, load_inventory

MAX_RECENT = 8


def _same(a: Any, b: Any) -> bool:
    return os.path.normcase(os.path.normpath(str(a))) == os.path.normcase(os.path.normpath(str(b)))


def describe(folder: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    """What the welcome screen needs to know about one folder."""
    data = load_inventory(folder)
    layout = data["layout"] if isinstance(data["layout"], dict) else {}
    space = layout.get("space") if isinstance(layout.get("space"), dict) else None
    return {
        "folder": str(folder),
        "folder_name": folder.name,
        "missing": not folder.is_dir(),
        "exists": bool(data["exists"]),
        "space": space,
        "no_inventory": any(_same(folder, one) for one in prefs.get("no_inventory_folders") or []),
    }


def _recent_entry(info: dict[str, Any]) -> dict[str, Any]:
    space = info["space"] or {}
    return {
        "folder": info["folder"],
        "name": space.get("name") or info["folder_name"],
        "kind": "none" if info["no_inventory"] else space.get("kind") or "drawer",
        "size": [space["x"], space["y"], space["z"]] if space else None,
    }


def space_routes(
    default_output: Path,
    load_preferences: Callable[[], dict[str, Any]],
    save_preferences: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Callable[[dict], dict]]:
    """POST handlers for the browser service, keyed by path."""

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def recent(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {**one, "missing": not Path(one["folder"]).is_dir()}
            for one in prefs.get("recent_spaces") or []
            if isinstance(one, dict) and one.get("folder")
        ]

    def reply(target: Path | None) -> dict[str, Any]:
        prefs = load_preferences()
        return {"space": describe(target, prefs) if target else None, "recent": recent(prefs)}

    def remember(target: Path, no_inventory: bool | None = None) -> None:
        """Make the folder the save location and put it first in the recent list."""
        update: dict[str, Any] = {"output": str(target)}
        if no_inventory is not None:
            marked = [one for one in load_preferences().get("no_inventory_folders") or [] if not _same(one, target)]
            update["no_inventory_folders"] = marked + ([str(target)] if no_inventory else [])
        prefs = save_preferences(update)
        others = [
            one for one in prefs.get("recent_spaces") or []
            if isinstance(one, dict) and not _same(one.get("folder"), target)
        ]
        save_preferences({"recent_spaces": [_recent_entry(describe(target, prefs)), *others][:MAX_RECENT]})

    def inspect(payload):
        return reply(folder(payload))

    def create(payload):
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        create_space(
            target, name=payload.get("name"), kind=payload.get("kind"),
            x=payload.get("x"), y=payload.get("y"), z=payload.get("z"),
        )
        remember(target, no_inventory=False)
        return reply(target)

    def no_inventory(payload):
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        remember(target, no_inventory=True)
        return reply(target)

    def open_space(payload):
        target = folder(payload)
        remember(target)
        return reply(target)

    def forget(payload):
        target = folder(payload)
        prefs = load_preferences()
        save_preferences({"recent_spaces": [
            one for one in prefs.get("recent_spaces") or []
            if isinstance(one, dict) and not _same(one.get("folder"), target)
        ]})
        return reply(None)

    return {
        "/api/space/inspect": inspect,
        "/api/space/create": create,
        "/api/space/no-inventory": no_inventory,
        "/api/space/open": open_space,
        "/api/space/forget": forget,
    }
