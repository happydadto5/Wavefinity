"""Storage Drawers schema and placement-preserving layout plans."""
from __future__ import annotations
from organizer_engine._specs import GRID_PITCHES, grid_label, validate_grid, validate_built_in_grid, retain_space_grid

import copy
import math
import uuid

from organizer_engine import BASE_UNIT
from organizer_engine.product_rules import DRAWER_LAYER_MAX_USABLE_HEIGHT_MM, ORDINARY_BIN_MIN_HEIGHT_MM, STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM, STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM

STORAGE_DRAWERS_KIND = "storage_drawers"
STORAGE_DRAWERS_DEFAULT_FIELD_MM = (210.0, 119.0)
STORAGE_DRAWERS_MIN_UNITS = 6
STORAGE_DRAWERS_MAX_UNITS = 250
STORAGE_DRAWERS_MIN_DRAWERS = 1
STORAGE_DRAWERS_MAX_DRAWERS = 32
STORAGE_DRAWER_FIT_CHOICES = (0.30, 0.40, 0.60)
STORAGE_DRAWER_FIT_DEFAULT = 0.40
STORAGE_DRAWER_FRAME_WIDTH_CHOICES = (10.0, 14.0, 18.0)
STORAGE_DRAWER_FRAME_WIDTH_DEFAULT = 14.0
STORAGE_DRAWER_LABEL_LIMIT = 80
# The visible usable height (stored clear height + the cabinet's current fit)
# of a Storage Drawers drawer must fit the drawer layer's 2000 mm usable-height
# ceiling. Single authority: DRAWER_LAYER_MAX_USABLE_HEIGHT_MM in
# organizer_engine.product_rules. Backend validation compares height_mm + the
# cabinet's *current* fit against this cap; the frontend quotes the same visible
# maximum.
STORAGE_DRAWER_MAX_USABLE_HEIGHT_MM = DRAWER_LAYER_MAX_USABLE_HEIGHT_MM
STORAGE_DRAWER_MATERIAL_MIN_MM = 0.4
STORAGE_DRAWER_MATERIAL_MAX_MM = 4.0
# Fix 1101 (Opus H4): drawer walls carry the wavy-rect cavity whose crest
# stands 0.524 mm proud of the nominal wall plane — a 0.8 mm wall is 0.28 mm
# at the crests and the 0.4 mm floor breaks through. Drawer walls need
# >= 1.4 mm (0.524 + ~2 extrusion widths). Cabinet/base/top keep 0.4 mm.
STORAGE_DRAWER_DRAWER_WALL_MIN_MM = 1.4
STORAGE_DRAWER_MATERIAL_DEFAULT_MM = 1.6
_MATERIAL_KEYS = ("cabinet_wall_mm", "cabinet_base_mm", "cabinet_top_mm", "drawer_wall_mm", "drawer_base_mm")
_MATERIAL_TITLES = {
    "cabinet_wall_mm": "Cabinet wall thickness", "cabinet_base_mm": "Cabinet base thickness",
    "cabinet_top_mm": "Cabinet top thickness", "drawer_wall_mm": "Drawer wall thickness",
    "drawer_base_mm": "Drawer base thickness",
}
_TOGGLE_TITLES = {
    "drawer_handles": "Handles", "stacking": "Stacking",
    "unit_label_enabled": "Unit label", "drawer_labels_enabled": "Drawer labels",
}


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


def _usable_drawer_height(height, fit):
    """Usable height (stored clear height + the cabinet's current fit) must fit
    the drawer layer's DRAWER_LAYER_MAX_USABLE_HEIGHT_MM ceiling. The error quotes the visible
    usable height, never a derived clear-height cap. Uses the same raw
    comparison as normalise_drawer's downstream check, so the boundary agrees
    exactly (1999.4 + 0.6 == 2000.0 is accepted; 1999.5 + 0.6 raises)."""
    if height + fit > DRAWER_LAYER_MAX_USABLE_HEIGHT_MM:
        raise ValueError(f"Drawer usable height must be at most {DRAWER_LAYER_MAX_USABLE_HEIGHT_MM:g} mm")
    return height


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


def new_drawer_descriptor(height_mm: float | None = None, fit_mm: float | None = None) -> dict:
    if height_mm is None:
        height = STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM - STORAGE_DRAWER_FIT_DEFAULT
    else:
        fit = _choice(fit_mm, STORAGE_DRAWER_FIT_CHOICES, "drawer fit") if fit_mm is not None else STORAGE_DRAWER_FIT_DEFAULT
        height = _usable_drawer_height(_number(height_mm, "Drawer height", ORDINARY_BIN_MIN_HEIGHT_MM), fit)
    return {"id": str(uuid.uuid4()), "height_mm": height, "label_text": ""}


def storage_drawers_field_defaults(grid: str = "wavefinity") -> tuple[float, float]:
    pitch = GRID_PITCHES[validate_grid(grid)]
    return tuple(max(1, math.floor(value / pitch + 0.5)) * pitch
                 for value in STORAGE_DRAWERS_DEFAULT_FIELD_MM)


def storage_drawers_default_usable_height(grid: str = "wavefinity") -> float:
    if validate_grid(grid) == "wavefinity":
        return STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
    from organizer_features.gridfinity import HEIGHT_UNIT
    return max(1, math.floor(STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM / HEIGHT_UNIT + 0.5)) * HEIGHT_UNIT


def storage_drawers_defaults(drawer_count: int = 3, grid: str = "wavefinity", built_in_grid: str = "floor") -> dict:
    if isinstance(drawer_count, bool) or not isinstance(drawer_count, int) or not 1 <= drawer_count <= STORAGE_DRAWERS_MAX_DRAWERS:
        raise ValueError(f"Number of drawers must be {STORAGE_DRAWERS_MIN_DRAWERS}–{STORAGE_DRAWERS_MAX_DRAWERS}")
    grid = validate_grid(grid)
    mode = validate_built_in_grid(built_in_grid) if grid != "wavefinity" else "floor"
    base = STORAGE_DRAWER_MATERIAL_DEFAULT_MM
    if grid != "wavefinity" and mode == "floor":
        from organizer_features.gridfinity import minimum_floor_build
        base = minimum_floor_build(grid)
    height = storage_drawers_default_usable_height(grid) - STORAGE_DRAWER_FIT_DEFAULT
    return {
        "grid": grid, "built_in_grid": mode,
        "seated_lift_mm": None,
        "drawers": [new_drawer_descriptor(height, STORAGE_DRAWER_FIT_DEFAULT) for _ in range(drawer_count)],
        "cabinet_style": "full", "rear_support": "cross", "open_frame_width_mm": 14.0,
        "wall_mounting": "off", "wall_mount_keyholes_per_drawer": 2,
        "drawer_fit_mm": 0.40, "drawer_handles": True, "drawer_handle_size": "auto",
        "stacking": False, "unit_label_enabled": False, "unit_label_text": "",
        "drawer_labels_enabled": False, "drawer_label_style": "inlaid",
        "cabinet_wall_mm": STORAGE_DRAWER_MATERIAL_DEFAULT_MM, "cabinet_base_mm": STORAGE_DRAWER_MATERIAL_DEFAULT_MM,
        "cabinet_top_mm": STORAGE_DRAWER_MATERIAL_DEFAULT_MM,
        "drawer_wall_mm": STORAGE_DRAWER_MATERIAL_DEFAULT_MM, "drawer_base_mm": base,
    }


def normalise_storage_drawers_block(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Storage Drawers settings must be an object")
    grid = validate_grid(raw.get("grid", "wavefinity"))
    if grid != "wavefinity" and "built_in_grid" not in raw:
        raise ValueError("Choose Floor or None for a Gridfinity cabinet.")
    mode = validate_built_in_grid(raw["built_in_grid"]) if grid != "wavefinity" else "floor"
    defaults = storage_drawers_defaults(1, grid, mode)
    rows = raw.get("drawers")
    if not isinstance(rows, list) or not 1 <= len(rows) <= STORAGE_DRAWERS_MAX_DRAWERS:
        raise ValueError("Number of drawers must be 1–32")
    seen = set()
    drawers = []
    fit = _choice(raw.get("drawer_fit_mm", defaults["drawer_fit_mm"]), STORAGE_DRAWER_FIT_CHOICES, "drawer fit")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Drawer must be an object")
        drawer_id = _uuid(row.get("id"))
        if drawer_id in seen:
            raise ValueError("Duplicate drawer ID")
        seen.add(drawer_id)
        height = _number(row.get("height_mm"), "Drawer height", ORDINARY_BIN_MIN_HEIGHT_MM)
        # Story 2763: usable height must be at least the ordinary-bin minimum.
        if height + fit < STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM:
            raise ValueError(f"Drawer usable height must be at least {STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM:g} mm")
        drawers.append({"id": drawer_id, "height_mm": _usable_drawer_height(height, fit), "label_text": _label(row.get("label_text", ""), "Drawer label")})
    result = {"drawers": drawers, "grid": grid, "built_in_grid": mode}
    result["cabinet_style"] = _choice(raw.get("cabinet_style", defaults["cabinet_style"]), ("full", "open"), "cabinet style")
    result["rear_support"] = _choice(raw.get("rear_support", defaults["rear_support"]), ("cross", "solid"), "rear support")
    result["wall_mounting"] = _choice(raw.get("wall_mounting", defaults["wall_mounting"]), ("off", "keyholes"), "wall mounting")
    result["wall_mount_keyholes_per_drawer"] = _choice(raw.get("wall_mount_keyholes_per_drawer", defaults["wall_mount_keyholes_per_drawer"]), (2, 4), "keyholes per drawer level")
    result["open_frame_width_mm"] = _choice(raw.get("open_frame_width_mm", defaults["open_frame_width_mm"]), STORAGE_DRAWER_FRAME_WIDTH_CHOICES, "frame width")
    result["drawer_fit_mm"] = fit
    for key in ("drawer_handles", "stacking", "unit_label_enabled", "drawer_labels_enabled"):
        value = raw.get(key, defaults[key])
        if not isinstance(value, bool):
            raise ValueError(f"{_TOGGLE_TITLES[key]} must be on or off")
        result[key] = value
    result["drawer_handle_size"] = _choice(raw.get("drawer_handle_size", defaults["drawer_handle_size"]), ("auto", "small", "medium", "large"), "handle size")
    result["unit_label_text"] = _label(raw.get("unit_label_text", ""), "Unit label")
    if result["unit_label_enabled"] and not result["unit_label_text"]:
        raise ValueError("Enter unit label text")
    result["drawer_label_style"] = _choice(raw.get("drawer_label_style", "inlaid"), ("inlaid", "raised"), "drawer label style")
    from organizer_features.gridfinity import PROFILES, floor_pocket_depth, measured_seated_lift, validate_floor_build
    pocket_floor = result["grid"] in PROFILES and result["built_in_grid"] == "floor"
    for key in _MATERIAL_KEYS:
        floor = STORAGE_DRAWER_DRAWER_WALL_MIN_MM if key == "drawer_wall_mm" else STORAGE_DRAWER_MATERIAL_MIN_MM
        maximum = STORAGE_DRAWER_MATERIAL_MAX_MM
        if pocket_floor and key == "drawer_base_mm":
            maximum += floor_pocket_depth(result["grid"])
        result[key] = _number(raw.get(key, defaults[key]), _MATERIAL_TITLES[key], floor, maximum)
    if pocket_floor:
        validate_floor_build(result["grid"], result["drawer_base_mm"])
    result["seated_lift_mm"] = measured_seated_lift(raw.get("seated_lift_mm")) if grid != "wavefinity" else None
    return result


def prepare_new_storage_drawers_definition(raw: dict) -> dict:
    prepared = copy.deepcopy(raw)
    grid = validate_grid(prepared.get("grid"))
    for axis, value in zip(("x", "y"), storage_drawers_field_defaults(grid)):
        prepared.setdefault(axis, value)
    block = prepared.get("storage_drawers")
    if not isinstance(block, dict) or not isinstance(block.get("drawers"), list):
        raise ValueError("Storage Drawers settings are missing")
    fit = _choice(block.get("drawer_fit_mm", STORAGE_DRAWER_FIT_DEFAULT), STORAGE_DRAWER_FIT_CHOICES, "drawer fit")
    for row in block["drawers"]:
        if not isinstance(row, dict):
            raise ValueError("Drawer must be an object")
        if "id" not in row:
            row["id"] = str(uuid.uuid4())
        row.setdefault("height_mm", storage_drawers_default_usable_height(grid) - fit)
    return normalise_storage_drawers_definition(prepared)


def normalise_storage_drawers_definition(raw: dict) -> dict:
    if not isinstance(raw, dict) or raw.get("kind") != STORAGE_DRAWERS_KIND:
        raise ValueError("Expected a Storage Drawers Space")
    result = copy.deepcopy(raw)
    result["grid"] = validate_grid(raw.get("grid", "wavefinity"))
    settings = dict(raw.get("storage_drawers") or {})
    if "grid" in settings and validate_grid(settings["grid"]) != result["grid"]:
        raise ValueError("Storage Drawers grid must match its Space grid.")
    if result["grid"] != "wavefinity":
        if "built_in_grid" not in raw and "built_in_grid" not in settings:
            raise ValueError("Choose Floor or None for a Gridfinity cabinet.")
        result["built_in_grid"] = validate_built_in_grid(raw.get("built_in_grid", settings.get("built_in_grid")))
        if "built_in_grid" in settings and validate_built_in_grid(settings["built_in_grid"]) != result["built_in_grid"]:
            raise ValueError("Storage Drawers floor must match its Space floor.")
    else:
        result["built_in_grid"] = "floor"
        # Discard Gridfinity-only derived fields when reading a legacy cabinet.
        for key in ("floor_grid", "floor_mode", "nominal_grid_mm", "physical_cavity_mm",
                    "external_plate_clearance_per_side_mm", "external_plate_clearance_status",
                    "seated_lift_mm", "seated_lift_status", "height_fit_verified"):
            result.pop(key, None)
    result["name"] = _label(raw.get("name", ""), "Space name")
    if not result["name"]:
        raise ValueError("Enter a Space name")
    for axis in ("x", "y"):
        mm = _number(raw.get(axis), f"Space {axis}")
        units = mm / BASE_UNIT
        minimum_units = GRID_PITCHES[result["grid"]] / BASE_UNIT if result["grid"] != "wavefinity" else STORAGE_DRAWERS_MIN_UNITS
        if not math.isclose(units, round(units), abs_tol=1e-8) or not minimum_units <= round(units) <= STORAGE_DRAWERS_MAX_UNITS:
            if result["grid"] != "wavefinity":
                raise ValueError(f"Space {axis} needs at least one {GRID_PITCHES[result['grid']]:g} mm cell")
            raise ValueError(f"Space {axis} must be 6–250 whole units")
        result[axis] = round(units) * BASE_UNIT
    settings.update(grid=result["grid"], built_in_grid=result["built_in_grid"])
    if "seated_lift_mm" not in settings and "seated_lift_mm" in raw:
        settings["seated_lift_mm"] = raw["seated_lift_mm"]
    result["storage_drawers"] = normalise_storage_drawers_block(settings)
    from organizer_features.gridfinity import container_floor_record
    record = container_floor_record(result["grid"], result["built_in_grid"], result["x"], result["y"],
                                    result["storage_drawers"]["seated_lift_mm"])
    result.update(record)
    result["storage_drawers"].update(record)
    result["z"] = storage_drawers_compatibility_z(result["storage_drawers"])
    return result


def storage_drawers_definition_problem(raw: object) -> str | None:
    """Why a raw Storage Drawers Space fails the canonical normalizer, or None."""
    try:
        normalise_storage_drawers_definition(raw)
    except (TypeError, ValueError) as error:
        return str(error) or "Cabinet settings are invalid"
    return None


def _attempt(check, *args):
    """A validated value, or None when this one setting is unusable."""
    try:
        return check(*args)
    except (TypeError, ValueError):
        return None


def reset_storage_drawers_definition(raw: object) -> dict:
    """A valid current Storage Drawers Space rebuilt from what can still be trusted.

    Only the cabinet definition is repaired. Drawer repair is field-local: a usable
    drawer UUID is always kept, a damaged height or label takes its default alone,
    and a new UUID is minted only for a missing, invalid, or duplicate ID.
    Every other invalid setting takes its default.
    """
    source = raw if isinstance(raw, dict) else {}
    base = {key: copy.deepcopy(value) for key, value in source.items() if key != "storage_drawers"}
    base["kind"] = STORAGE_DRAWERS_KIND
    name = _attempt(_label, source.get("name", ""), "Space name")
    base["name"] = name or "Storage Drawers"
    grid = validate_grid(source.get("grid", "wavefinity"))
    pitch = GRID_PITCHES[grid]
    for axis in ("x", "y"):
        mm = _attempt(_number, source.get(axis), f"Space {axis}")
        units = None if mm is None else mm / BASE_UNIT
        minimum_units = STORAGE_DRAWERS_MIN_UNITS if grid == "wavefinity" else pitch / BASE_UNIT
        valid = (units is not None and math.isclose(units, round(units), abs_tol=1e-8)
                 and minimum_units <= round(units) <= STORAGE_DRAWERS_MAX_UNITS)
        base[axis] = (round(units) if valid else STORAGE_DRAWERS_MIN_UNITS) * BASE_UNIT
        if grid != "wavefinity":
            base[axis] = max(1, math.floor(base[axis] / pitch + 0.5)) * pitch
    block_in = source.get("storage_drawers")
    block_in = block_in if isinstance(block_in, dict) else {}
    from organizer_features.gridfinity import PROFILES, floor_pocket_depth, measured_seated_lift, minimum_floor_build
    mode = validate_built_in_grid(source.get("built_in_grid", block_in.get("built_in_grid", "floor"))) if grid != "wavefinity" else "floor"
    defaults = storage_drawers_defaults(1, grid, mode)
    block = {"grid": grid, "built_in_grid": mode,
             "seated_lift_mm": _attempt(measured_seated_lift, block_in.get("seated_lift_mm", base.get("seated_lift_mm")))}
    for key, choices in (("cabinet_style", ("full", "open")), ("rear_support", ("cross", "solid")),
                         ("wall_mounting", ("off", "keyholes")),
                         ("wall_mount_keyholes_per_drawer", (2, 4)),
                         ("open_frame_width_mm", STORAGE_DRAWER_FRAME_WIDTH_CHOICES),
                         ("drawer_fit_mm", STORAGE_DRAWER_FIT_CHOICES),
                         ("drawer_handle_size", ("auto", "small", "medium", "large")),
                         ("drawer_label_style", ("inlaid", "raised"))):
        value = block_in.get(key, defaults.get(key, "inlaid"))
        block[key] = value if _attempt(_choice, value, choices, key) is not None else defaults.get(key, "inlaid")
    for key in _TOGGLE_TITLES:
        value = block_in.get(key, defaults[key])
        block[key] = value if isinstance(value, bool) else defaults[key]
    text = _attempt(_label, block_in.get("unit_label_text", ""), "Unit label")
    block["unit_label_text"] = text or ""
    if block["unit_label_enabled"] and not block["unit_label_text"]:
        block["unit_label_enabled"] = False
    for key in _MATERIAL_KEYS:
        floor = STORAGE_DRAWER_DRAWER_WALL_MIN_MM if key == "drawer_wall_mm" else STORAGE_DRAWER_MATERIAL_MIN_MM
        maximum = STORAGE_DRAWER_MATERIAL_MAX_MM
        if grid in PROFILES and mode == "floor" and key == "drawer_base_mm":
            maximum += floor_pocket_depth(grid)
        value = _attempt(_number, block_in.get(key, defaults[key]), key,
                         floor, maximum)
        block[key] = defaults[key] if value is None else value
        if grid in PROFILES and mode == "floor" and key == "drawer_base_mm":
            block[key] = max(block[key], minimum_floor_build(grid))
    rows = block_in.get("drawers")
    kept, seen = [], set()
    for row in (rows if isinstance(rows, list) else [])[:STORAGE_DRAWERS_MAX_DRAWERS]:
        source = row if isinstance(row, dict) else {}
        drawer_id = _attempt(_uuid, source.get("id"))
        if not drawer_id or drawer_id in seen:
            drawer_id = new_drawer_descriptor()["id"]
        seen.add(drawer_id)

        height = _attempt(
            _number, source.get("height_mm"), "Drawer height",
            ORDINARY_BIN_MIN_HEIGHT_MM,
        )
        if height is None or _attempt(_usable_drawer_height, height, block["drawer_fit_mm"]) is None:
            height = storage_drawers_default_usable_height(grid) - block["drawer_fit_mm"]
        elif height + block["drawer_fit_mm"] < STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM:
            height = STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM - block["drawer_fit_mm"]

        label = _attempt(_label, source.get("label_text", ""), "Drawer label")
        if label is None:
            label = ""

        kept.append({
            "id": drawer_id,
            "height_mm": height,
            "label_text": label,
        })
    if not kept:
        kept = [new_drawer_descriptor(storage_drawers_default_usable_height(grid) - block["drawer_fit_mm"], block["drawer_fit_mm"]) for _ in range(3)]
    block["drawers"] = kept
    base["storage_drawers"] = block
    return normalise_storage_drawers_definition(base)


def storage_drawers_compatibility_z(block: dict) -> float:
    return sum(row["height_mm"] for row in block["drawers"])


def storage_drawers_unit_counts(space: dict) -> tuple[int, int]:
    canonical = normalise_storage_drawers_definition(space)
    pitch = GRID_PITCHES[canonical["grid"]]
    return round(canonical["x"] / pitch), round(canonical["y"] / pitch)


def storage_drawers_active_limits(space: dict, drawer_id: str | None) -> dict:
    canonical = normalise_storage_drawers_definition(space)
    rows = canonical["storage_drawers"]["drawers"]
    index = next((i for i, one in enumerate(rows) if one["id"] == drawer_id), 0)
    # Local import avoids the storage_drawers <-> geometry module import cycle.
    from organizer_storage.drawer_geometry import storage_drawers_usable_heights
    usable = storage_drawers_usable_heights(canonical)
    row = rows[index]
    return {"x": canonical["x"], "y": canonical["y"], "z": usable[index], "drawer_id": row["id"], "grid": canonical["grid"], "built_in_grid": canonical["built_in_grid"], "seated_lift_mm": canonical["storage_drawers"]["seated_lift_mm"]}


def storage_drawers_recent_summary(space: dict) -> str:
    canonical = normalise_storage_drawers_definition(space)
    x, y = storage_drawers_unit_counts(canonical)
    drawer_total = len(canonical["storage_drawers"]["drawers"])
    unit = "units" if canonical["grid"] == "wavefinity" else f"{grid_label(canonical['grid'])} cells"
    return f"{drawer_total} {'drawer' if drawer_total == 1 else 'drawers'} · {x} × {y} {unit}"


def storage_drawers_projection(space: dict) -> list[dict]:
    canonical = normalise_storage_drawers_definition(space)
    from organizer_storage.drawer_geometry import storage_drawers_usable_heights
    usable = storage_drawers_usable_heights(canonical)
    from organizer_features.gridfinity import container_floor_record
    record = container_floor_record(canonical["grid"], canonical["built_in_grid"], canonical["x"], canonical["y"],
                                    canonical["storage_drawers"]["seated_lift_mm"])
    return [{"id": row["id"], "name": f"Drawer {i}", "width": canonical["x"], "depth": canonical["y"], "height": usable[i-1], "clearance": 0.0, "boundary": "mating", "placements": [], **({"grid": canonical["grid"]} if canonical["grid"] != "wavefinity" else {}), **record} for i, row in enumerate(canonical["storage_drawers"]["drawers"], 1)]


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
        raise ValueError(f"Maximum {STORAGE_DRAWERS_MAX_DRAWERS} drawers")
    added = new_drawer_descriptor(rows[-1]["height_mm"] if rows else None, canonical["storage_drawers"]["drawer_fit_mm"])
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


def retain_storage_drawers_fields(proposed: dict, existing: dict) -> dict:
    """Cabinet-only creation choices; all mutation paths use the persisted record."""
    result = retain_space_grid(proposed, existing)
    grid = result["grid"]
    wanted_block = result.get("storage_drawers")
    wanted_block = wanted_block if isinstance(wanted_block, dict) else {}
    if "grid" in wanted_block:
        retain_space_grid({"grid": wanted_block["grid"]}, existing)
    block = existing.get("storage_drawers")
    block = block if isinstance(block, dict) else {}
    saved = existing.get("built_in_grid", block.get("built_in_grid", "floor"))
    if grid != "wavefinity":
        saved = validate_built_in_grid(saved)
        for wanted in (result.get("built_in_grid"), wanted_block.get("built_in_grid")):
            if wanted is not None and validate_built_in_grid(wanted) != saved:
                raise ValueError(f"A Storage Drawers floor is immutable: {saved} cannot become {wanted}. Create a new Space for another floor.")
        result["built_in_grid"] = saved
    return result


def plan_reconfigure(space: dict, layout: dict, proposed_space: dict, bins: list[dict]) -> tuple[dict, dict]:
    current = reconcile_storage_drawers_layout(layout, space)
    proposed = normalise_storage_drawers_definition(retain_storage_drawers_fields(proposed_space, current["space"]))
    old_ids = [row["id"] for row in current["space"]["storage_drawers"]["drawers"]]
    new_ids = [row["id"] for row in proposed["storage_drawers"]["drawers"]]
    if old_ids != new_ids:
        raise ValueError("Use Add Drawer or Delete Drawer to change drawer identities")
    updated = reconcile_storage_drawers_layout(current, proposed)
    from organizer_drawer import surface_reconfigure_problem
    problem = surface_reconfigure_problem(bins, current, bins, updated)
    if problem:
        raise ValueError(problem)
    return proposed, updated


def drawer_holding_bin(layout: dict, row_id: str) -> str | None:
    for drawer in layout.get("drawers", []):
        if any(row.get("bin") == row_id for row in drawer.get("placements", [])):
            return drawer.get("id")
    return None
