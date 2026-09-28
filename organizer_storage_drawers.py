"""Storage Drawers schema and placement-preserving layout plans."""
from __future__ import annotations

import copy
import math
import uuid

from organizer_engine import BASE_UNIT, B4B_MATERIAL_PRESETS, B4B_DEFAULT_WALL, B4B_DEFAULT_BASE
from organizer_product_rules import ORDINARY_BIN_MIN_HEIGHT_MM, STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM

STORAGE_DRAWERS_KIND = "storage_drawers"
STORAGE_DRAWERS_MIN_UNITS = 6
STORAGE_DRAWERS_MAX_UNITS = 250
STORAGE_DRAWERS_MIN_DRAWERS = 1
STORAGE_DRAWERS_MAX_DRAWERS = 32
STORAGE_DRAWER_FIT_CHOICES = (0.30, 0.40, 0.60)
STORAGE_DRAWER_FIT_DEFAULT = 0.40
STORAGE_DRAWER_FRAME_WIDTH_CHOICES = (10.0, 14.0, 18.0)
STORAGE_DRAWER_FRAME_WIDTH_DEFAULT = 14.0
STORAGE_DRAWER_LABEL_LIMIT = 80
STORAGE_DRAWER_MATERIAL_MIN_MM = 0.4
STORAGE_DRAWER_MATERIAL_MAX_MM = 4.0
STORAGE_DRAWER_MATERIAL_DEFAULT_MM = 1.6
_MATERIAL_KEYS = ("cabinet_wall_mm", "cabinet_base_mm", "cabinet_top_mm", "drawer_wall_mm", "drawer_base_mm")


def _number(value, title, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{title} must be a number")
    value = float(value)
    if not math.isfinite(value) or (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{title} is out of range")
    return value


def _choice(value, choices, title):
    if value not in choices:
        raise ValueError(f"Choose a valid {title}")
    return value


def _label(value, title):
    if not isinstance(value, str):
        raise ValueError(f"{title} must be text")
    value = value.strip()
    if len(value) > STORAGE_DRAWER_LABEL_LIMIT:
        raise ValueError(f"{title} is too long")
    return value


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError("Drawer ID is missing or invalid")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise ValueError("Drawer ID is missing or invalid") from None
    if str(parsed) != value:
        raise ValueError("Drawer ID is missing or invalid")
    return value


def new_drawer_descriptor(height_mm: float | None = None) -> dict:
    height = STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM if height_mm is None else _number(height_mm, "Drawer height", ORDINARY_BIN_MIN_HEIGHT_MM)
    return {"id": str(uuid.uuid4()), "height_mm": height, "label_text": ""}


def storage_drawers_defaults(drawer_count: int = 3) -> dict:
    if isinstance(drawer_count, bool) or not isinstance(drawer_count, int) or not 1 <= drawer_count <= STORAGE_DRAWERS_MAX_DRAWERS:
        raise ValueError("Number of drawers must be 1–32")
    return {
        "drawers": [new_drawer_descriptor() for _ in range(drawer_count)],
        "cabinet_style": "full", "rear_support": "cross", "open_frame_width_mm": 14.0,
        "drawer_fit_mm": 0.40, "drawer_handles": True, "drawer_handle_size": "auto",
        "stacking": False, "unit_label_enabled": False, "unit_label_text": "",
        "drawer_labels_enabled": False, "drawer_label_style": "inlaid",
        "cabinet_wall_mm": B4B_DEFAULT_WALL, "cabinet_base_mm": B4B_DEFAULT_BASE,
        "cabinet_top_mm": STORAGE_DRAWER_MATERIAL_DEFAULT_MM,
        "drawer_wall_mm": B4B_DEFAULT_WALL, "drawer_base_mm": B4B_DEFAULT_BASE,
    }


def normalise_storage_drawers_block(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Storage Drawers settings must be an object")
    defaults = storage_drawers_defaults(1)
    rows = raw.get("drawers")
    if not isinstance(rows, list) or not 1 <= len(rows) <= STORAGE_DRAWERS_MAX_DRAWERS:
        raise ValueError("Number of drawers must be 1–32")
    seen = set()
    drawers = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Drawer must be an object")
        drawer_id = _uuid(row.get("id"))
        if drawer_id in seen:
            raise ValueError("Duplicate drawer ID")
        seen.add(drawer_id)
        drawers.append({"id": drawer_id, "height_mm": _number(row.get("height_mm"), "Drawer height", ORDINARY_BIN_MIN_HEIGHT_MM), "label_text": _label(row.get("label_text", ""), "Drawer label")})
    result = {"drawers": drawers}
    result["cabinet_style"] = _choice(raw.get("cabinet_style", defaults["cabinet_style"]), ("full", "open"), "cabinet style")
    result["rear_support"] = _choice(raw.get("rear_support", defaults["rear_support"]), ("cross", "solid"), "rear support")
    result["open_frame_width_mm"] = _choice(raw.get("open_frame_width_mm", defaults["open_frame_width_mm"]), STORAGE_DRAWER_FRAME_WIDTH_CHOICES, "frame width")
    result["drawer_fit_mm"] = _choice(raw.get("drawer_fit_mm", defaults["drawer_fit_mm"]), STORAGE_DRAWER_FIT_CHOICES, "drawer fit")
    for key in ("drawer_handles", "stacking", "unit_label_enabled", "drawer_labels_enabled"):
        value = raw.get(key, defaults[key])
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be on or off")
        result[key] = value
    result["drawer_handle_size"] = _choice(raw.get("drawer_handle_size", defaults["drawer_handle_size"]), ("auto", "small", "medium", "large"), "handle size")
    result["unit_label_text"] = _label(raw.get("unit_label_text", ""), "Unit label")
    if result["unit_label_enabled"] and not result["unit_label_text"]:
        raise ValueError("Enter unit label text")
    result["drawer_label_style"] = _choice(raw.get("drawer_label_style", "inlaid"), ("inlaid", "raised"), "drawer label style")
    for key in _MATERIAL_KEYS:
        result[key] = _number(raw.get(key, defaults[key]), key, STORAGE_DRAWER_MATERIAL_MIN_MM, STORAGE_DRAWER_MATERIAL_MAX_MM)
    return result


def prepare_new_storage_drawers_definition(raw: dict) -> dict:
    prepared = copy.deepcopy(raw)
    block = prepared.get("storage_drawers")
    if not isinstance(block, dict) or not isinstance(block.get("drawers"), list):
        raise ValueError("Storage Drawers settings are missing")
    for row in block["drawers"]:
        if not isinstance(row, dict):
            raise ValueError("Drawer must be an object")
        if "id" not in row:
            row["id"] = str(uuid.uuid4())
    return normalise_storage_drawers_definition(prepared)


def normalise_storage_drawers_definition(raw: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("kind") != STORAGE_DRAWERS_KIND:
        raise ValueError("Expected a Storage Drawers Space")
    result = copy.deepcopy(raw)
    result["name"] = _label(raw.get("name", ""), "Space name")
    if not result["name"]:
        raise ValueError("Enter a Space name")
    for axis in ("x", "y"):
        mm = _number(raw.get(axis), f"Space {axis}")
        units = mm / BASE_UNIT
        if not math.isclose(units, round(units), abs_tol=1e-8) or not STORAGE_DRAWERS_MIN_UNITS <= round(units) <= STORAGE_DRAWERS_MAX_UNITS:
            raise ValueError(f"Space {axis} must be 6–250 whole units")
        result[axis] = round(units) * BASE_UNIT
    result["storage_drawers"] = normalise_storage_drawers_block(raw.get("storage_drawers"))
    result["z"] = storage_drawers_compatibility_z(result["storage_drawers"])
    return result


def storage_drawers_compatibility_z(block: dict) -> float:
    return sum(row["height_mm"] for row in block["drawers"])


def storage_drawers_unit_counts(space: dict) -> tuple[int, int]:
    canonical = normalise_storage_drawers_definition(space)
    return int(canonical["x"] / BASE_UNIT), int(canonical["y"] / BASE_UNIT)


def storage_drawers_active_limits(space: dict, drawer_id: str | None) -> dict:
    canonical = normalise_storage_drawers_definition(space)
    rows = canonical["storage_drawers"]["drawers"]
    row = next((one for one in rows if one["id"] == drawer_id), rows[0])
    return {"x": canonical["x"], "y": canonical["y"], "z": row["height_mm"], "drawer_id": row["id"]}


def storage_drawers_recent_summary(space: dict) -> str:
    canonical = normalise_storage_drawers_definition(space)
    x, y = storage_drawers_unit_counts(canonical)
    return f"{len(canonical['storage_drawers']['drawers'])} drawers · {x} × {y} units"


def storage_drawers_projection(space: dict) -> list[dict]:
    canonical = normalise_storage_drawers_definition(space)
    return [{"id": row["id"], "name": f"Drawer {i}", "width": canonical["x"], "depth": canonical["y"], "height": row["height_mm"], "clearance": 0.0, "boundary": "mating", "placements": []} for i, row in enumerate(canonical["storage_drawers"]["drawers"], 1)]


def reconcile_storage_drawers_layout(layout: dict, space: dict) -> dict:
    canonical = normalise_storage_drawers_definition(space)
    if not isinstance(layout, dict):
        raise ValueError("Layout must be an object")
    result = copy.deepcopy(layout)
    existing = result.get("drawers", [])
    if not isinstance(existing, list):
        raise ValueError("Layout drawers must be a list")
    indexed = {}
    for row in existing:
        if not isinstance(row, dict):
            raise ValueError("Layout drawer must be an object")
        drawer_id = _uuid(row.get("id"))
        if drawer_id in indexed:
            raise ValueError("Duplicate layout drawer ID")
        indexed[drawer_id] = row
    projected = storage_drawers_projection(canonical)
    wanted = {row["id"] for row in projected}
    for old_id, row in indexed.items():
        if old_id not in wanted and row.get("placements"):
            raise ValueError("A removed drawer still holds bins; recover it before continuing")
    seen_bins = set()
    for row in projected:
        old = indexed.get(row["id"], {})
        placements = old.get("placements", [])
        if not isinstance(placements, list):
            raise ValueError("Drawer placements must be a list")
        for placement in placements:
            if not isinstance(placement, dict):
                raise ValueError("Invalid drawer placement")
            bin_id = placement.get("bin")
            if bin_id and bin_id in seen_bins:
                raise ValueError("An ordinary row is placed in more than one drawer")
            if bin_id:
                seen_bins.add(bin_id)
        row.update({key: copy.deepcopy(value) for key, value in old.items() if key not in row})
        row["placements"] = copy.deepcopy(placements)
    result["drawers"] = projected
    result["active"] = result.get("active") if result.get("active") in wanted else projected[0]["id"]
    result["space"] = canonical
    return result


def plan_add_drawer(space: dict, layout: dict) -> tuple[dict, dict, str]:
    canonical = normalise_storage_drawers_definition(space)
    current = reconcile_storage_drawers_layout(layout, canonical)
    rows = canonical["storage_drawers"]["drawers"]
    if len(rows) >= STORAGE_DRAWERS_MAX_DRAWERS:
        raise ValueError("Storage Drawers supports at most 32 drawers")
    added = new_drawer_descriptor(rows[-1]["height_mm"] if rows else None)
    rows.append(added)
    canonical["z"] = storage_drawers_compatibility_z(canonical["storage_drawers"])
    updated = reconcile_storage_drawers_layout(current, canonical)
    updated["active"] = added["id"]
    return canonical, updated, added["id"]


def plan_delete_drawer(space: dict, layout: dict, drawer_id: str) -> tuple[dict, dict, str]:
    canonical = normalise_storage_drawers_definition(space)
    current = reconcile_storage_drawers_layout(layout, canonical)
    rows = canonical["storage_drawers"]["drawers"]
    if len(rows) == 1:
        raise ValueError("Keep at least one drawer")
    index = next((i for i, row in enumerate(rows) if row["id"] == drawer_id), None)
    if index is None:
        raise ValueError("Drawer does not exist")
    if current["drawers"][index]["placements"]:
        raise ValueError(f"Empty Drawer {index + 1} before deleting it.")
    del rows[index]
    canonical["z"] = storage_drawers_compatibility_z(canonical["storage_drawers"])
    updated = reconcile_storage_drawers_layout(current, canonical)
    if current["active"] == drawer_id:
        updated["active"] = rows[min(index, len(rows) - 1)]["id"]
    return canonical, updated, updated["active"]


def plan_reconfigure(space: dict, layout: dict, proposed_space: dict, bins: list[dict]) -> tuple[dict, dict]:
    current = reconcile_storage_drawers_layout(layout, space)
    proposed = normalise_storage_drawers_definition(proposed_space)
    old_ids = [row["id"] for row in current["space"]["storage_drawers"]["drawers"]]
    new_ids = [row["id"] for row in proposed["storage_drawers"]["drawers"]]
    if old_ids != new_ids:
        raise ValueError("Use Add Drawer or Delete Drawer to change drawer identities")
    updated = reconcile_storage_drawers_layout(current, proposed)
    from organizer_drawer import drawer_report
    for i, drawer in enumerate(updated["drawers"], 1):
        if drawer["placements"]:
            problems = drawer_report(drawer, bins, layout=updated).get("problems", [])
            if problems:
                raise ValueError(f"Drawer {i}: {problems[0].get('message', 'placements no longer fit')}")
    return proposed, updated


def drawer_holding_bin(layout: dict, row_id: str) -> str | None:
    for drawer in layout.get("drawers", []):
        if any(row.get("bin") == row_id for row in drawer.get("placements", [])):
            return drawer.get("id")
    return None
