"""Storage Box and Space definition normalising and configuration."""

from __future__ import annotations

import copy
import math
from organizer_engine._specs import (
    GRID_PITCHES, cross_grid_message, grid_label, retain_space_grid, validate_built_in_grid, validate_grid,
)
from typing import Any
from organizer_engine import (
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    B4B_FRONT_LABEL_STYLES,
    B4B_LABEL_SIZES,
    B4B_LABEL_LOCATIONS,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
    B4B_LID_HEADROOM_CHOICES,
    BASE_UNIT,
    MIN_HEIGHT_ABOVE_BASE,
)
from organizer_engine._specs import B4B_LATCH_TWO_ABOVE_FIELD_X, B4B_EDGE_BEVELS, B4B_LATCH_TIGHTNESS, B4B_HINGE_COUNTS, B4B_HINGE_TYPES
from organizer_engine.product_rules import (
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    SURFACE_TRIM_HEIGHTS,
    surface_maximums,
)
from organizer_features.pegboard import normalise_pegboard_space
from organizer_storage.drawers import (
    normalise_storage_drawers_definition,
    plan_add_drawer,
    plan_delete_drawer,
    plan_reconfigure,
    retain_storage_drawers_fields,
    prepare_new_storage_drawers_definition,
    reconcile_storage_drawers_layout,
    reset_storage_drawers_definition,
)

from ._rows import (
    INVENTORY_LOCK,
    SPACE_KINDS,
    LEGACY_SPACE_KINDS,
    _number,
    parse_inventory,
    render_inventory,
    design_specs,
)
from ._merge import _text_payload


def legacy_layout_space(layout: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recover a Space's identity from a pre-``layout.space`` drawer layout.

    Older inventories held drawers, an active drawer and placements without
    the newer top-level ``space`` block. That is still a real Space: derive
    one from its drawer (the active one when there is a choice), so the
    folder is recognized without losing or re-entering anything.
    """
    if not isinstance(layout, dict):
        return None
    drawers = layout.get("drawers")
    if not isinstance(drawers, list) or not drawers:
        return None
    active_id = layout.get("active")
    chosen = next(
        (one for one in drawers if isinstance(one, dict) and one.get("id") == active_id),
        None,
    ) or next((one for one in drawers if isinstance(one, dict)), None)
    if not isinstance(chosen, dict):
        return None
    try:
        size = [float(chosen[axis]) for axis in ("width", "depth", "height")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in size):
        return None
    name = str(chosen.get("name") or "").strip()[:80] or "Drawer"
    return {"kind": "drawer", "name": name, "x": size[0], "y": size[1], "z": size[2]}



STORAGE_BOX_LABEL_LIMIT = 80
STORAGE_BOX_MIN_MATERIAL_MM = 0.4
STORAGE_BOX_MAX_MATERIAL_MM = 4.0
FLOOR_CHOICE_NAMES = {"floor": "Floor", "none": "None"}


def nearest_whole_cell_field(grid: str, x: Any, y: Any, minimum_mm: float = 0.0) -> tuple[float, float]:
    """The nearest legal whole-cell field at a pitch for the dimensions entered.

    Nearest positive whole cells per axis (halves round up), never fewer cells
    than the box's minimum field needs. No dimension is invented: the result is
    only ever the entered size moved to the nearest legal cell count.
    """
    pitch = GRID_PITCHES[validate_grid(grid)]
    floor_cells = max(1, math.ceil(float(minimum_mm) / pitch - 1e-9))
    return tuple(  # type: ignore[return-value]
        max(floor_cells, math.floor(float(value) / pitch + 0.5)) * pitch for value in (x, y))


def storage_box_defaults() -> dict[str, Any]:
    """The established B4B/Storage Box settings a new or legacy Space starts from."""
    return {
        "grid": "wavefinity", "built_in_grid": "floor",
        "seated_lift_mm": None,
        "secure_lid": True,
        "latch_count": "1",
        "hinge_count": "2",
        "hinge_type": "screw",
        "latch_strength": "standard",
        "lid_headroom_mm": 1.0,
        "latch_tightness": "default",
        "edge_bevel": "default",
        "label_enabled": False,
        "label_text": "",
        "label_location": "top",
        "front_label_style": "flat",
        "label_size": "default",
        "stacking": False,
        "grid_stacking": False,
        "handle": False,
        "wall_mm": B4B_DEFAULT_WALL,
        "base_mm": B4B_DEFAULT_BASE,
    }


def _storage_box_flag(raw: Any, name: str) -> bool:
    if not isinstance(raw, bool):
        raise ValueError(f"storage box {name} must be true or false")
    return raw


def _storage_box_choice(raw: Any, choices: tuple[str, ...], name: str) -> str:
    value = str(raw).strip().lower()
    if value not in choices:
        raise ValueError(f"storage box {name} must be one of {', '.join(choices)}")
    return value


def _storage_box_material(raw: Any, name: str, maximum: float = STORAGE_BOX_MAX_MATERIAL_MM) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"storage box {name} must be a number in mm")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"storage box {name} must be a number in mm") from error
    if not math.isfinite(value) or not (
        STORAGE_BOX_MIN_MATERIAL_MM <= value <= maximum
    ):
        raise ValueError(
            f"storage box {name} must be between {STORAGE_BOX_MIN_MATERIAL_MM:g} "
            f"and {maximum:g} mm"
        )
    return value


def normalise_storage_box(raw: Any, width_mm: Any = None, depth_mm: Any = None) -> dict[str, Any]:
    """A complete, validated ``space.storage_box`` block.

    Missing keys read the established defaults, so a legacy Storage Box Space
    with no block behaves exactly like a new one with default settings. The
    block never carries redundant ``enabled``/``lid`` flags: a Storage Box Space
    is always a B4B case with a lid.

    A legacy stored latch count of ``"auto"`` resolves in memory to the count
    the box supports by its width (``width_mm``): 2 only over the engine's
    threshold, else 1. Nothing is written back here.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("storage box settings must be an object")
    merged = {**storage_box_defaults(), "edge_bevel": "none", **{
        key: value for key, value in raw.items() if key in storage_box_defaults()
    }}
    if str(merged["latch_count"]).strip().lower() == "auto":
        try:
            wide = float(width_mm) > B4B_LATCH_TWO_ABOVE_FIELD_X
        except (TypeError, ValueError):
            wide = False
        merged["latch_count"] = "2" if wide else "1"
    headroom = merged["lid_headroom_mm"]
    if isinstance(headroom, bool):
        raise ValueError("storage box lid snugness must be a number in mm")
    try:
        headroom = float(headroom)
    except (TypeError, ValueError) as error:
        raise ValueError("storage box lid snugness must be a number in mm") from error
    match = next(
        (choice for choice in B4B_LID_HEADROOM_CHOICES if math.isclose(headroom, choice, abs_tol=1e-6)),
        None,
    )
    if match is None:
        allowed = ", ".join(f"{choice:g}" for choice in B4B_LID_HEADROOM_CHOICES)
        raise ValueError(f"storage box lid snugness must be one of {allowed} mm")
    label_text = str(merged["label_text"] or "").strip()
    if len(label_text) > STORAGE_BOX_LABEL_LIMIT:
        raise ValueError(f"storage box label text is at most {STORAGE_BOX_LABEL_LIMIT} characters")
    from organizer_features.gridfinity import (
        PROFILES, container_floor_record, floor_pocket_depth, measured_seated_lift,
        minimum_floor_build, validate_floor_build,
    )
    from organizer_b4b._constants import B4B_STACK_RECESS_DEPTH
    grid = validate_grid(merged["grid"])
    mode = validate_built_in_grid(merged["built_in_grid"])
    underside = B4B_STACK_RECESS_DEPTH if merged["stacking"] else 0.0
    if grid in PROFILES and mode == "floor" and "base_mm" not in raw:
        # A Floor box that was not given a base starts from the thinnest base
        # that can hold its raised socket grid (derived, never guessed). An
        # explicit base below it is still refused by validate_floor_build.
        merged["base_mm"] = minimum_floor_build(grid, underside)
    maximum = STORAGE_BOX_MAX_MATERIAL_MM
    if grid in PROFILES and mode == "floor":
        maximum += floor_pocket_depth(grid) + underside
    base = _storage_box_material(merged["base_mm"], "base thickness", maximum)
    if grid in PROFILES and mode == "floor":
        validate_floor_build(grid, base, underside)
    result = {
        "secure_lid": _storage_box_flag(merged["secure_lid"], "secure lid"),
        "grid": validate_grid(merged["grid"]),
        "built_in_grid": validate_built_in_grid(merged["built_in_grid"]),
        "latch_count": _storage_box_choice(merged["latch_count"], B4B_LATCH_COUNTS, "latch count"),
        "hinge_count": _storage_box_choice(merged["hinge_count"], B4B_HINGE_COUNTS, "hinge count"),
        "hinge_type": _storage_box_choice(merged["hinge_type"], B4B_HINGE_TYPES, "hinge type"),
        "latch_strength": _storage_box_choice(merged["latch_strength"], B4B_LATCH_STRENGTHS, "latch strength"),
        "lid_headroom_mm": match,
        "latch_tightness": _storage_box_choice(merged["latch_tightness"], B4B_LATCH_TIGHTNESS, "latch tightness"),
        "edge_bevel": _storage_box_choice(merged["edge_bevel"], B4B_EDGE_BEVELS, "edge bevel"),
        "label_enabled": _storage_box_flag(merged["label_enabled"], "label"),
        "label_text": label_text,
        "label_location": _storage_box_choice(merged["label_location"], B4B_LABEL_LOCATIONS, "label location"),
        "front_label_style": _storage_box_choice(merged["front_label_style"], B4B_FRONT_LABEL_STYLES, "front label style"),
        "label_size": _storage_box_choice(merged["label_size"], B4B_LABEL_SIZES, "label size"),
        "stacking": _storage_box_flag(merged["stacking"], "stacking"),
        "grid_stacking": _storage_box_flag(merged["grid_stacking"], "grid stacking"),
        "handle": _storage_box_flag(merged["handle"], "handle"),
        "wall_mm": _storage_box_material(merged["wall_mm"], "wall thickness"),
        "base_mm": base,
        "seated_lift_mm": measured_seated_lift(merged["seated_lift_mm"]),
    }
    from .stacking import validate_grid_stacking
    validate_grid_stacking(result, width_mm, depth_mm)
    if width_mm is not None and depth_mm is not None:
        result.update(container_floor_record(grid, mode, width_mm, depth_mm, result["seated_lift_mm"]))
    return result


def normalise_space_definition(raw: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    grid = validate_grid(raw.get("grid", "wavefinity"))
    name = str(raw.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("a space needs a name")
    kind = str(raw.get("kind") or "")
    if kind not in SPACE_KINDS and not (allow_legacy and kind in LEGACY_SPACE_KINDS):
        raise ValueError(f"a space is one of {', '.join(SPACE_KINDS)}")
    if kind in LEGACY_SPACE_KINDS:
        # Legacy box is read for migration only - this function persists,
        # so the migration wizard's own box -> Portable mapping is enforced
        # here too, not left to every caller to remember - see Fix 004
        # Correction 8.D.
        kind = "portable"

    if kind not in {"drawer", "portable", "storage_drawers"} and grid != "wavefinity":
        raise ValueError(f"{kind} spaces only support the Wavefinity grid")

    if kind == "pegboard":
        resolved = normalise_pegboard_space(raw)
        return {"name": name, "kind": kind, **resolved, "grid": grid}

    if kind == "storage_drawers":
        # Strict re-normalisation of a saved/edited cabinet; Create prepares
        # fresh drawer IDs once beforehand (see configure_space).
        return normalise_storage_drawers_definition({**raw, "name": name})

    x, y, z = (_number(raw.get(axis)) for axis in ("x", "y", "z"))
    if min(x, y, z) <= 0:
        raise ValueError("a space needs its inside X, Y and Z in mm")

    if kind == "drawer":
        minimum_xy = BASE_UNIT + DRAWER_HARD_CLEARANCE_MM
        if grid != "wavefinity":
            # A Gridfinity drawer keeps its real size and no wall allowance:
            # it needs room for one whole cell at its pitch.
            minimum_xy = GRID_PITCHES[grid]
        if x + 1e-9 < minimum_xy or y + 1e-9 < minimum_xy:
            raise ValueError(
                f"a drawer space needs at least {minimum_xy:g} mm width and depth"
            )
        if z + 1e-9 < ORDINARY_BIN_MIN_HEIGHT_MM:
            raise ValueError(
                f"a drawer space needs at least {ORDINARY_BIN_MIN_HEIGHT_MM:g} mm usable height"
            )

    elif kind == "portable":
        minimum_xy = B4B_MIN_FIELD_XY
        if grid != "wavefinity" and (raw.get("storage_box") or {}).get("secure_lid") is False:
            minimum_xy = GRID_PITCHES[grid]
        if grid != "wavefinity":
            # Gridfinity field: whole cells at the pitch, never fewer than the
            # minimum field. The nearest legal field is named so the entry can
            # be corrected, never guessed.
            pitch = GRID_PITCHES[grid]
            nearest = nearest_whole_cell_field(grid, x, y, minimum_xy)
            if not all(math.isclose(value, wanted, abs_tol=1e-6)
                       for value, wanted in zip((x, y), nearest)):
                raise ValueError(
                    f"a {grid_label(grid)} Storage Box field is whole {pitch:g} mm cells; "
                    f"the nearest legal field is {nearest[0]:g} x {nearest[1]:g} mm"
                )
        if x + 1e-9 < minimum_xy or y + 1e-9 < minimum_xy:
            raise ValueError(
                f"a storage box needs at least {minimum_xy:g} mm in X and Y"
            )
        if z + 1e-9 < B4B_LATCHED_MIN_HEIGHT:
            raise ValueError(
                f"a storage box needs at least {B4B_LATCHED_MIN_HEIGHT:g} mm usable height"
            )
        if grid == "wavefinity":
            for axis_name, value in (("X", x), ("Y", y)):
                units = value / BASE_UNIT
                if not math.isclose(units, round(units), abs_tol=1e-6):
                    raise ValueError(
                        f"storage box {axis_name} must be a whole Wavefinity unit"
                    )

    elif kind == "surface":
        for axis_name, value in (("X", x), ("Y", y)):
            units = value / BASE_UNIT
            if units < 1 or not math.isclose(units, round(units), abs_tol=1e-6):
                raise ValueError(
                    f"surface {axis_name} must be a positive whole Wavefinity unit"
                )

        trim_size = str(raw.get("trim_size") or "").strip().lower()
        expected_z = SURFACE_TRIM_HEIGHTS.get(trim_size)
        if expected_z is None:
            raise ValueError("surface trim size must be small, medium, or large")
        if not math.isclose(z, expected_z, abs_tol=1e-6):
            raise ValueError(
                f"surface trim size {trim_size!r} requires Z={expected_z:g} mm"
            )

    result = {"name": name, "kind": kind, "x": x, "y": y, "z": z, "grid": grid}
    if kind == "drawer" and grid != "wavefinity":
        from organizer_features.gridfinity import measured_seated_lift
        result["seated_lift_mm"] = measured_seated_lift(raw.get("seated_lift_mm"))
    if kind == "surface":
        result["trim_size"] = trim_size
        # Fix 095: the user's maximum finished outside rectangle is durable
        # authority beside the resolved field. A missing value is seeded from
        # the current finished footprint, so it can never enlarge the Space.
        result["max_x_mm"], result["max_y_mm"] = surface_maximums(
            raw, x, y, trim_size, strict=True)
    if kind == "portable":
        settings = dict(raw.get("storage_box") or {})
        if "grid" in settings and validate_grid(settings["grid"]) != grid:
            raise ValueError("Storage Box grid must match its Space grid.")
        settings["grid"] = grid
        if "built_in_grid" in raw:
            settings["built_in_grid"] = raw["built_in_grid"]
        if grid == "wavefinity":
            # A floor choice is meaningless on the Wavefinity grid: cleared to
            # the neutral default, never recorded on the Space.
            settings["built_in_grid"] = "floor"
            settings["seated_lift_mm"] = None
        result["storage_box"] = normalise_storage_box(settings, x, y)
        if grid != "wavefinity":
            result["built_in_grid"] = result["storage_box"]["built_in_grid"]
            from organizer_features.gridfinity import container_floor_record
            result.update(container_floor_record(grid, result["built_in_grid"], x, y,
                                                result["storage_box"]["seated_lift_mm"]))
    return result

def _setup_space_layout(layout: dict[str, Any], space_def: dict[str, Any]) -> None:
    from ._rows import owned_design_grid
    destination_grid = validate_grid(space_def.get("grid", "wavefinity"))
    for spec in design_specs(layout).values():
        if isinstance(spec, dict):
            existing_grid = owned_design_grid(spec, layout.get("space"))
            if existing_grid != destination_grid:
                raise ValueError(cross_grid_message(existing_grid, destination_grid, "An existing bin"))
    layout["version"] = 1
    layout["space"] = space_def

    kind = space_def["kind"]
    if kind == "storage_drawers":
        reconciled = reconcile_storage_drawers_layout(layout, space_def)
        layout.clear()
        layout.update(reconciled)
        layout["version"] = 1
        return
    x, y, z = space_def["x"], space_def["y"], space_def["z"]

    drawers = layout.setdefault("drawers", [])
    active_id = layout.get("active")
    primary = next(
        (
            drawer for drawer in drawers
            if isinstance(drawer, dict) and drawer.get("id") == active_id
        ),
        None,
    )

    if primary is None and drawers:
        primary = next(
            (drawer for drawer in drawers if isinstance(drawer, dict)),
            None,
        )

    if primary is None:
        primary = {
            "id": "d1",
            "placements": [],
        }
        drawers.append(primary)

    layout["active"] = primary["id"]

    if kind == "drawer":
        boundary = "wall"
        try:
            previous_clearance = float(primary.get("clearance", DRAWER_HARD_CLEARANCE_MM))
        except (TypeError, ValueError):
            previous_clearance = DRAWER_HARD_CLEARANCE_MM
        clearance = max(DRAWER_HARD_CLEARANCE_MM, previous_clearance)
        if space_def["grid"] != "wavefinity":
            clearance = 0.0   # real dimensions: the whole-cell field starts at the front-left wall
    elif kind == "pegboard":
        boundary = "pegboard"
        clearance = 0.0
    else:
        boundary = "mating"
        clearance = 0.0

    primary["name"] = space_def["name"]
    primary["width"] = x
    primary["depth"] = y
    primary["height"] = z
    primary["clearance"] = clearance
    primary["boundary"] = boundary
    if kind == "drawer" and space_def["grid"] != "wavefinity":
        primary["grid"] = space_def["grid"]
    else:
        primary.pop("grid", None)
    if kind == "portable" and space_def["grid"] != "wavefinity":
        # The box's own pitch is the layout's cell: Gridfinity placement snaps
        # to its cells, read through the same drawer fields a Plain Drawer uses.
        from organizer_features.gridfinity import container_floor_record
        primary["grid"] = space_def["grid"]
        primary.update(container_floor_record(space_def["grid"], space_def["built_in_grid"], x, y,
                                               space_def["storage_box"]["seated_lift_mm"]))
    if kind == "pegboard":
        primary["pegboard_standard"] = space_def["pegboard_standard"]
        primary["pegboard_holes_x"] = space_def["pegboard_holes_x"]
        primary["pegboard_holes_y"] = space_def["pegboard_holes_y"]
        primary["pegboard_residual_x"] = space_def["pegboard_residual_x"]
        primary["pegboard_residual_y"] = space_def["pegboard_residual_y"]


def _reconcile_surface_bases(bins: list[dict[str, Any]], layout: dict[str, Any],
                             edge: float) -> None:
    """Keep unprinted Auto platforms on the Surface edge in this transaction."""
    rows = {one["id"]: one for one in bins}
    for row_id, source in design_specs(layout).items():
        row = rows.get(row_id)
        if row is None or not isinstance(source, dict):
            continue
        metadata = source.get("layout")
        if not isinstance(metadata, dict) or metadata.get("surface_base_mode") != "edge":
            continue
        box = source.get("box")
        if isinstance(box, dict) and math.isclose(float(box["base_thickness"]), edge, abs_tol=1e-9):
            continue  # Renaming or resizing X/Y never changes Inventory rows.
        if int(row.get("qty") or 0) > 0:
            metadata["surface_base_mode"] = "custom"
            continue
        if not isinstance(box, dict):
            continue
        old_base, old_z = float(box["base_thickness"]), float(box["z"])
        headroom = max(MIN_HEIGHT_ABOVE_BASE, old_z - old_base)
        box["base_thickness"] = edge
        box["standard_base"] = False
        box["z"] = edge + headroom
        row["z"] = box["z"]
        if not math.isclose(edge, old_base, abs_tol=1e-9):
            row["file"] = ""


def _carry_storage_box(raw_def: dict[str, Any], layout: dict[str, Any], mode: str) -> dict[str, Any]:
    """An update that does not send Storage Box settings keeps the saved ones."""
    if mode != "update" or "storage_box" in raw_def:
        return raw_def
    existing = layout.get("space") if isinstance(layout, dict) else None
    if isinstance(existing, dict) and isinstance(existing.get("storage_box"), dict):
        return {**raw_def, "storage_box": existing["storage_box"]}
    return raw_def


def _refuse_floor_change(proposed: dict[str, Any], existing: dict[str, Any]) -> None:
    """A Storage Box's floor (Floor / None) is fixed at creation, like its grid.

    Only the portable (Storage Box) kind is judged here; the Storage Drawers
    path owns its own floor rules. A Wavefinity box has no floor choice.
    """
    if existing.get("kind") not in ("portable", "box") or proposed.get("kind") not in ("portable", "box"):
        return
    grid = validate_grid(existing.get("grid", "wavefinity"))
    if grid == "wavefinity":
        return
    saved = existing.get("built_in_grid")
    if saved is None and isinstance(existing.get("storage_box"), dict):
        saved = existing["storage_box"].get("built_in_grid")
    saved = validate_built_in_grid(saved if saved is not None else "floor")
    box = proposed.get("storage_box")
    for wanted in (proposed.get("built_in_grid"), box.get("built_in_grid") if isinstance(box, dict) else None):
        if wanted is not None and validate_built_in_grid(wanted) != saved:
            raise ValueError(
                f"A Storage Box's floor is immutable: this Space was created with the "
                f"{FLOOR_CHOICE_NAMES[saved]} floor and cannot become {FLOOR_CHOICE_NAMES[wanted]}. "
                "Create a new Space for another floor. Nothing was changed.")


def _configured_space_definition(
    raw_def: dict[str, Any], layout: dict[str, Any], mode: str, allow_legacy: bool,
) -> dict[str, Any]:
    existing = layout.get("space")
    if isinstance(existing, dict):
        raw_def = retain_space_grid(raw_def, existing)
        if mode == "update":
            _refuse_floor_change(raw_def, existing)
            if raw_def.get("kind") == "drawer" and "seated_lift_mm" not in raw_def:
                raw_def = {**raw_def, "seated_lift_mm": existing.get("seated_lift_mm")}
    if raw_def.get("kind") == "storage_drawers":
        if mode == "update":
            raise ValueError("Edit a Storage Drawers Space from its cabinet editor.")
        raw_def = prepare_new_storage_drawers_definition({
            **raw_def, "name": str(raw_def.get("name") or "").strip()[:80],
        })
    return normalise_space_definition(
        _carry_storage_box(raw_def, layout, mode), allow_legacy=allow_legacy)


def _refuse_stranding_surface_change(
    bins: list[dict[str, Any]], layout: dict[str, Any], space_def: dict[str, Any], mode: str,
) -> None:
    """Validate a Space edit against the proposed layout before any
    write. The single local/hosted rule; a refusal changes nothing and never
    unplaces, moves or clamps a bin."""
    if mode != "update" or not isinstance(layout.get("drawers"), list):
        return
    if not any(isinstance(one, dict) and one.get("placements") for one in layout["drawers"]):
        return
    from organizer_drawer import surface_reconfigure_problem  # organizer_drawer imports this module

    proposed = copy.deepcopy(layout)
    proposed_bins = copy.deepcopy(bins)
    _setup_space_layout(proposed, space_def)
    if space_def["kind"] == "surface":
        _reconcile_surface_bases(proposed_bins, proposed, space_def["z"])
    problem = surface_reconfigure_problem(bins, layout, proposed_bins, proposed)
    if problem:
        raise ValueError(problem)


def _plan_cabinet_mutation(
    current: dict[str, Any], operation: str, drawer_id: Any, proposed: Any, space: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one 084A cabinet planner against the current layout. Pure."""
    layout = current["layout"] if isinstance(current["layout"], dict) else {}
    base = space if isinstance(space, dict) else layout.get("space")
    if not isinstance(base, dict) or base.get("kind") != "storage_drawers":
        raise ValueError("This folder does not hold a Storage Drawers Space.")
    persisted = layout.get("space")
    if isinstance(persisted, dict):
        base = retain_storage_drawers_fields(base, persisted)
    if isinstance(proposed, dict):
        proposed = retain_storage_drawers_fields(proposed, base)
    if operation == "reset":
        # Damaged cabinet settings: rebuild only the cabinet definition, then
        # reconcile the layout by stable drawer ID. A repaired-away drawer that
        # still holds bins is refused by the reconcile - bins are never dropped.
        canonical = reset_storage_drawers_definition(proposed if isinstance(proposed, dict) else base)
        return canonical, reconcile_storage_drawers_layout(layout, canonical)
    if operation == "add":
        canonical, updated, _added = plan_add_drawer(base, layout)
    elif operation == "delete":
        canonical, updated, _next = plan_delete_drawer(base, layout, str(drawer_id or ""))
    elif operation == "reconfigure":
        if not isinstance(proposed, dict):
            raise ValueError("Storage Drawers settings are missing.")
        canonical, updated = plan_reconfigure(base, layout, proposed, current["bins"])
    else:
        raise ValueError("Unknown cabinet change.")
    return canonical, updated


def storage_drawers_mutate_text(
    text: str, *, title: str, operation: str, drawer_id: Any = None, proposed: Any = None,
    space: Any = None,
) -> dict[str, Any]:
    """The browser-folder twin: pure with respect to the user's files."""
    with INVENTORY_LOCK:
        current = parse_inventory(str(text or ""))
        canonical, updated = _plan_cabinet_mutation(current, operation, drawer_id, proposed, space)
        rendered = render_inventory(str(title or canonical["name"]), current["bins"], updated)
        return {**_text_payload(rendered, str(title or canonical["name"]), parse_inventory(rendered)),
                "space": canonical}


def configure_space_text(
    text: str, *, title: str, raw_def: dict[str, Any], mode: str = "create", allow_legacy: bool = False
) -> dict[str, Any]:
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        layout = current["layout"] if isinstance(current["layout"], dict) else {}
        if mode == "create" and isinstance(layout.get("space"), dict):
            raise ValueError(f"this folder already holds the space {layout['space'].get('name')!r}")
        space_def = _configured_space_definition(raw_def, layout, mode, allow_legacy)
        _refuse_stranding_surface_change(current["bins"], layout, space_def, mode)
        _setup_space_layout(layout, space_def)
        if mode == "update" and space_def["kind"] == "surface":
            _reconcile_surface_bases(current["bins"], layout, space_def["z"])
        rendered = render_inventory(str(title or space_def["name"]), current["bins"], layout)
        return _text_payload(rendered, str(title or space_def["name"]), parse_inventory(rendered))


