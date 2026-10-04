"""Storage Box and Space definition normalising and configuration."""

from __future__ import annotations

import copy
import math
from typing import Any
from organizer_engine import (
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    B4B_FRONT_LABEL_STYLES,
    B4B_LABEL_LOCATIONS,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
    B4B_LID_HEADROOM_CHOICES,
    BASE_UNIT,
    MIN_HEIGHT_ABOVE_BASE,
)
from organizer_product_rules import (
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    SURFACE_TRIM_HEIGHTS,
    surface_maximums,
)
from organizer_pegboard import normalise_pegboard_space
from organizer_storage_drawers import (
    normalise_storage_drawers_definition,
    plan_add_drawer,
    plan_delete_drawer,
    plan_reconfigure,
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


def storage_box_defaults() -> dict[str, Any]:
    """The established B4B/Storage Box settings a new or legacy Space starts from."""
    return {
        "secure_lid": True,
        "latch_count": "auto",
        "latch_strength": "standard",
        "lid_headroom_mm": 1.0,
        "label_enabled": False,
        "label_text": "",
        "label_location": "top",
        "front_label_style": "flat",
        "stacking": False,
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


def _storage_box_material(raw: Any, name: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"storage box {name} must be a number in mm")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"storage box {name} must be a number in mm") from error
    if not math.isfinite(value) or not (
        STORAGE_BOX_MIN_MATERIAL_MM <= value <= STORAGE_BOX_MAX_MATERIAL_MM
    ):
        raise ValueError(
            f"storage box {name} must be between {STORAGE_BOX_MIN_MATERIAL_MM:g} "
            f"and {STORAGE_BOX_MAX_MATERIAL_MM:g} mm"
        )
    return value


def normalise_storage_box(raw: Any) -> dict[str, Any]:
    """A complete, validated ``space.storage_box`` block.

    Missing keys read the established defaults, so a legacy Storage Box Space
    with no block behaves exactly like a new one with default settings. The
    block never carries redundant ``enabled``/``lid`` flags: a Storage Box Space
    is always a B4B case with a lid.
    """
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("storage box settings must be an object")
    merged = {**storage_box_defaults(), **{
        key: value for key, value in raw.items() if key in storage_box_defaults()
    }}
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
    return {
        "secure_lid": _storage_box_flag(merged["secure_lid"], "secure lid"),
        "latch_count": _storage_box_choice(merged["latch_count"], B4B_LATCH_COUNTS, "latch count"),
        "latch_strength": _storage_box_choice(merged["latch_strength"], B4B_LATCH_STRENGTHS, "latch strength"),
        "lid_headroom_mm": match,
        "label_enabled": _storage_box_flag(merged["label_enabled"], "label"),
        "label_text": label_text,
        "label_location": _storage_box_choice(merged["label_location"], B4B_LABEL_LOCATIONS, "label location"),
        "front_label_style": _storage_box_choice(merged["front_label_style"], B4B_FRONT_LABEL_STYLES, "front label style"),
        "stacking": _storage_box_flag(merged["stacking"], "stacking"),
        "handle": _storage_box_flag(merged["handle"], "handle"),
        "wall_mm": _storage_box_material(merged["wall_mm"], "wall thickness"),
        "base_mm": _storage_box_material(merged["base_mm"], "base thickness"),
    }


def normalise_space_definition(raw: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
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

    if kind == "pegboard":
        resolved = normalise_pegboard_space(raw)
        return {"name": name, "kind": kind, **resolved}

    if kind == "storage_drawers":
        # Strict re-normalisation of a saved/edited cabinet; Create prepares
        # fresh drawer IDs once beforehand (see configure_space).
        return normalise_storage_drawers_definition({**raw, "name": name})

    x, y, z = (_number(raw.get(axis)) for axis in ("x", "y", "z"))
    if min(x, y, z) <= 0:
        raise ValueError("a space needs its inside X, Y and Z in mm")

    if kind == "drawer":
        minimum_xy = BASE_UNIT + DRAWER_HARD_CLEARANCE_MM
        if x + 1e-9 < minimum_xy or y + 1e-9 < minimum_xy:
            raise ValueError(
                f"a drawer space needs at least {minimum_xy:g} mm width and depth"
            )
        if z + 1e-9 < ORDINARY_BIN_MIN_HEIGHT_MM:
            raise ValueError(
                f"a drawer space needs at least {ORDINARY_BIN_MIN_HEIGHT_MM:g} mm usable height"
            )

    elif kind == "portable":
        if x + 1e-9 < B4B_MIN_FIELD_XY or y + 1e-9 < B4B_MIN_FIELD_XY:
            raise ValueError(
                f"a storage box needs at least {B4B_MIN_FIELD_XY:g} mm in X and Y"
            )
        if z + 1e-9 < B4B_LATCHED_MIN_HEIGHT:
            raise ValueError(
                f"a storage box needs at least {B4B_LATCHED_MIN_HEIGHT:g} mm usable height"
            )
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

    result = {"name": name, "kind": kind, "x": x, "y": y, "z": z}
    if kind == "surface":
        result["trim_size"] = trim_size
        # Fix 095: the user's maximum finished outside rectangle is durable
        # authority beside the resolved field. A missing value is seeded from
        # the current finished footprint, so it can never enlarge the Space.
        result["max_x_mm"], result["max_y_mm"] = surface_maximums(
            raw, x, y, trim_size, strict=True)
    if kind == "portable":
        result["storage_box"] = normalise_storage_box(raw.get("storage_box"))
    return result

def _setup_space_layout(layout: dict[str, Any], space_def: dict[str, Any]) -> None:
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
        if int(row.get("qty") or 0) > 0:
            metadata["surface_base_mode"] = "custom"
            continue
        box = source.get("box")
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


def _configured_space_definition(
    raw_def: dict[str, Any], layout: dict[str, Any], mode: str, allow_legacy: bool,
) -> dict[str, Any]:
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
    """Fix 095: validate a Surface edit against the *proposed* Surface before any
    write. The single local/hosted rule; a refusal changes nothing and never
    unplaces, moves or clamps a bin."""
    if mode != "update" or space_def.get("kind") != "surface" or not isinstance(layout.get("drawers"), list):
        return
    if not any(isinstance(one, dict) and one.get("placements") for one in layout["drawers"]):
        return
    from organizer_drawer import surface_reconfigure_problem  # organizer_drawer imports this module

    proposed = copy.deepcopy(layout)
    proposed_bins = copy.deepcopy(bins)
    _setup_space_layout(proposed, space_def)
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


