"""Canonical design entry policy shared by desktop and browser environments."""
from __future__ import annotations

import copy
import json
from typing import Any
from organizer_app_impl._design_io import MODULE_MARKER_KEY, MODULE_MARKER_MM
from ._designs._preview import validate_design_payload

OLD_MODULE_NOTICE = (
    "This design was built on the retired 8 mm module; the current app uses the "
    "7 mm module. It will not be changed. Close it and start a new design on the "
    "current standard."
)


def read_inventory_snapshot(payload: dict, *, source: bool = False) -> tuple[dict, dict | None]:
    """Read saved folder text supplied by the browser's folder adapter.

    A Space object in a request is never ownership evidence. B09 supplies the
    saved inventory text (and, when present, metadata text) read from its handle.
    No paths are opened and no files are migrated or written here.
    """
    from organizer_inventory._rows import parse_inventory, owned_design_grid
    prefix = "source_" if source else ""
    text_key = prefix + "inventory_text"
    expected = payload.get(prefix + "space_id")
    metadata_text = payload.get(prefix + "space_metadata_text")
    if text_key not in payload:
        if source or expected or payload.get(prefix + "output") or metadata_text:
            raise ValueError("The saved Space records are missing.")
        return {"bins": [], "layout": None}, None
    current = parse_inventory(str(payload[text_key] or ""))
    layout = current.get("layout") or {}
    stored = layout.get("space")
    if expected and expected != layout.get("space_id"):
        raise ValueError("The saved Space ownership could not be verified.")
    if metadata_text:
        from organizer_spaces._core import _space
        metadata = json.loads(metadata_text)
        if not isinstance(metadata, dict) or metadata.get("folder_mode") != "space":
            raise ValueError("The saved Space definition could not be read.")
        canonical = _space(metadata.get("space"))
        if canonical is None:
            raise ValueError("The saved Space definition could not be read.")
        if isinstance(stored, dict) and owned_design_grid({}, stored) != owned_design_grid({}, canonical):
            raise ValueError("The saved Space records disagree about its grid.")
        if metadata.get("space_id") != layout.get("space_id"):
            raise ValueError("The saved Space ownership could not be verified.")
        stored = canonical
        current = {**current, "layout": {**layout, "space": stored}}
    return current, stored


def checked_entry_payload(payload: dict[str, Any], *, read_inventory) -> dict[str, Any]:
    from organizer_inventory._rows import checked_design_entry, design_specs
    if "source_space" in payload:
        raise ValueError("Name the saved source records instead of claiming a source Space.")
    current, destination = read_inventory(payload)
    if isinstance(payload.get("space"), dict) and payload["space"].get("kind") and destination is None:
        raise ValueError("The destination Space's saved records are missing.")
    source = None
    row_id = str(payload.get("source_row_id") or "") or None
    if any(key in payload for key in ("source_output", "source_inventory_text", "source_space_id")):
        source, _source_space = read_inventory(payload, source=True)
        if not row_id:
            raise ValueError("Name the saved source bin before copying it from a Space.")
    elif row_id:
        source = current
    if source is not None and row_id:
        standin = next((one for one in source.get("bins", []) if one.get("id") == row_id and one.get("kind") == "standin"), None)
        if standin is not None:
            # A stand-in has no design: only its own pitch's grid is held to the
            # destination Space, by the same authority as a real bin's design.
            checked_design_entry({"grid": standin["grid"]}, destination)
            return dict(payload)
        raw_source = design_specs(source.get("layout")).get(row_id)
        if not isinstance(raw_source, dict):
            raise ValueError("The saved source bin could not be verified.")
        checked_design_entry(raw_source, destination, source=source, row_id=row_id)
    request = dict(payload)
    for key in ("design", "resume_design"):
        raw = request.get(key)
        if isinstance(raw, dict) and raw.get("design_kind") != "base_trim":
            # Saved reads stamp verified ownership. Unowned files with no grid
            # remain legacy Wavefinity designs at every entry boundary.
            request[key] = checked_design_entry(raw, destination, source=source, row_id=row_id)
    if "new_bin_specs" in request:
        request["new_bin_specs"] = [
            checked_design_entry(raw, destination, source=source, row_id=row_id)
            if isinstance(raw, dict) else raw for raw in request["new_bin_specs"] or ()]
    proposed = request.get("layout")
    if isinstance(proposed, dict):
        from organizer_engine._specs import retain_space_grid
        proposed = copy.deepcopy(proposed)
        if isinstance(destination, dict):
            proposed["space"] = retain_space_grid(proposed.get("space") or destination, destination)
        existing = design_specs(current.get("layout"))
        for key, raw in design_specs(proposed).items():
            if key not in existing and isinstance(raw, dict):
                proposed["design_specs"][key] = checked_design_entry(raw, destination, source=source, row_id=row_id)
        request["layout"] = proposed
    return request


def validate_design_open_guard(payload: dict[str, Any], *, read_inventory) -> dict[str, Any]:
    """Every editor entry validates its raw saved design here (Story 2265).

    A saved record (the shape design_to_dict writes) without the 7 mm marker is
    refused with a notice and never handed to the editor or rewritten. Fresh
    in-editor designs and non-record payloads pass through unchanged.
    """
    payload = checked_entry_payload(payload, read_inventory=read_inventory)
    raw = payload.get("design") if isinstance(payload, dict) else None
    if (
        isinstance(raw, dict)
        and raw.get("design_kind") != "base_trim"
        and isinstance(raw.get("version"), int)
        and isinstance(raw.get("box"), dict)
        and isinstance(raw.get("layout"), dict)
        and raw.get(MODULE_MARKER_KEY) != MODULE_MARKER_MM
    ):
        raise ValueError(OLD_MODULE_NOTICE)
    return validate_design_payload(payload)
