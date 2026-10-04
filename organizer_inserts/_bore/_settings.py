"""Bore defaults, mode normalising and envelope zone."""

from __future__ import annotations

import math
from dataclasses import replace
from organizer_engine import BoxSpec
from .._core import (
    Feature,
    Zone,
    _fit_count,
    _need_item,
    connector_keep_out,
    feature_touches_wall,
    layout_zone,
)
from .._registry import defaults, resolved_options

from ._consts import (
    BORE_WALL,
    HEX_BIT_FLATS,
    HEX_BIT_CLEARANCE,
    HEX_BIT_HOLD,
    BORE_TILTED_WALL,
    normalize_bore_style,
    is_walls_only,
    is_wavy_style,
    bore_xy_size_mode,
    bore_height_size_mode,
    UPRIGHT_STYLES,
    ENVELOPE_STYLES,
)
from ._walls import _is_hex_bit, wall_only_envelope, _access_top_limit


@defaults("bore")
def bore_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    height_mode = bore_height_size_mode(one.options)
    if _is_hex_bit(item.profile):
        hole = min(HEX_BIT_HOLD[item.profile], box.z - base_z - 2.0)
    else:
        hole = min(item.length * 0.4, box.z - base_z - 2.0)
    style = normalize_bore_style(one.options.get("bore_style"))
    walls_only = is_walls_only(style)
    try:
        angle = max(0.0, float(one.options.get("angle", 0.0) or 0.0))
    except (TypeError, ValueError):
        angle = 0.0
    upright = style in UPRIGHT_STYLES
    if upright:
        angle = 0.0      # only Base - Straight Walls may lean
    tilted = angle > 1e-9
    default_wall = box.wall if upright else BORE_TILTED_WALL if tilted else BORE_WALL
    try:
        depth = float(one.options.get("depth", hole))
    except (TypeError, ValueError):
        depth = hole
    if height_mode == "bore_to_bin":
        # Fix 034 G1: the height must be one that is actually legal - a
        # wall-touching Bore is capped at the connector keep-out exactly like a
        # manual height would be. Fix 068: an Edge Mount screwdriver-access
        # passage crosses the interior, so the top also stays clear of it.
        top_limit = box.z - base_z
        if feature_touches_wall(box, one):
            top_limit = min(top_limit, connector_keep_out(box) - base_z)
        access_top = _access_top_limit(box)
        limited_by_access = access_top is not None and access_top - base_z < top_limit
        if limited_by_access:
            top_limit = access_top - base_z
        if walls_only:
            minimum_height = hole + 2.0
        elif tilted:
            minimum_height = depth * math.cos(math.radians(angle)) + 2.0
        else:
            minimum_height = depth
        if top_limit + 1e-6 < minimum_height:
            reason = ("the Edge Mount screwdriver access hole leaves too little room"
                      if limited_by_access else
                      "the connector keep-out leaves too little room")
            raise ValueError(
                f"Auto Height cannot fit a legal Bore here - {reason}; "
                "make the bin taller or move the Bore away from the wall"
            )
        resolved_height = top_limit
    elif walls_only:
        resolved_height = hole + 2.0
    else:
        resolved_height = one.options.get("depth", hole) + 2.0
    # Fix 078: a legacy Walls Only Bore with no explicit Depth shows and keeps
    # its real through-to-floor insertion depth, not a hidden stale number -
    # that is whatever Height actually resolves to, explicit or default.
    try:
        explicit_height = (float(one.options["height"])
                            if one.options.get("height") not in (None, "") else None)
    except (TypeError, ValueError):
        explicit_height = None
    walls_depth_default = explicit_height if explicit_height is not None else resolved_height
    return {
        "depth": hole,
        # A leaned bore takes a thicker wall by default so the extra material
        # between slanting holes still prints; an explicit Wall overrides it.
        "wall": default_wall,
        "height": resolved_height,
        "walls_depth": walls_depth_default,
        # X/Y counts are always explicit: a new Bore is one hole, and quantities
        # grow the footprint (and, in a bin-sizing mode, the bin) from there.
        "columns": 1.0,
        "rows": 1.0,
        # 0 is straight up; a positive angle leans the holes off vertical so
        # tubes rest at a slant. Only Base - Straight Walls may lean.
        "angle": 0.0,
        "bore_style": style,
        "xy_size_mode": bore_xy_size_mode(one.options, style),
        "height_size_mode": height_mode,
    }


def normalize_bore_modes(
    box: BoxSpec, one: Feature, base_z: float, mode: str = "fused",
) -> Feature:
    """Make a Bore's persisted style and sizing modes authoritative.

    Testing-era style words and the retired ``wall_style`` / ``auto_base`` /
    ``auto_height`` / ``auto_grid`` state are translated or dropped one way, so
    no hidden Auto behaviour survives. Base Width / Length ``bore_to_bin`` takes
    the current usable layout area, Height ``bore_to_bin`` drops its manual
    number (defaults then derive it from the current bin), Walls Only takes its
    default sizing mode, and the wall thickness Base styles hide is dropped.
    Anything that is not a Bore is returned untouched.
    """
    if one.kind != "bore":
        return one
    options = dict(one.options)
    zone = one.zone
    style = normalize_bore_style(options.get("bore_style"), options.get("wall_style"))
    for retired in ("auto_base", "auto_height", "auto_grid", "wall_style"):
        options.pop(retired, None)
    options["bore_style"] = style
    options["xy_size_mode"] = bore_xy_size_mode(options, style)
    options["height_size_mode"] = bore_height_size_mode(options)
    if style in UPRIGHT_STYLES:
        options.pop("angle", None)
        options.pop("angle_towards", None)
    if not is_walls_only(style):
        options.pop("wall", None)
    if options["height_size_mode"] == "bore_to_bin":
        options.pop("height", None)
    if options["xy_size_mode"] == "bore_to_bin" and not is_walls_only(style):
        zone = layout_zone(box, mode)
    elif (options["xy_size_mode"] == "bin_to_bore" and is_walls_only(style)
            and mode == "fused" and any(abs(c) > 1e-9 for c in one.zone.centre)):
        # Walls Only sizing the bin around itself is centred in the usable floor
        # (a nudge is undone), so the smallest grid-sized bin supports it on all
        # four sides within the grid-rounding allowance.
        half_w, half_d = one.zone.width / 2.0, one.zone.depth / 2.0
        zone = Zone(-half_w, -half_d, half_w, half_d)
    if zone is one.zone and options == one.options:
        return one
    return replace(one, zone=zone, options=options)


def _envelope_counts(
    env: dict, zone, spec_feature: Feature, options: dict, name: str,
) -> tuple[int, int]:
    """Whole-number columns/rows of an envelope-sized (upright) Bore grid."""
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width, env["pitch_x"], env["zone_span_x"])
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth, env["pitch_y"], env["zone_span_y"])
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {name}: zone is too small for a bore")
    return columns, rows


def _wall_only_grid(
    item, zone, spec_feature: Feature, held: float, wall: float, height: float,
    angle: float, style: str, where: tuple[BoxSpec, float], options: dict,
    depth: float = 0.0,
) -> dict:
    """Grid for an upright Bore (either Walls Only style or Base - Wavy Walls).

    A Walls Only footprint is the sleeves' outer envelope; Base - Wavy Walls is a
    block of the feature's own zone that the wavy hole grid must fit inside."""
    _, base_z = where
    if height <= 0.0 or wall <= 0.0:
        raise ValueError(f"{item.name}: bore height and wall must be positive")
    if not math.isfinite(angle) or abs(angle) > 1e-9:
        label = "Walls Only" if is_walls_only(style) else "Base - Wavy Walls"
        raise ValueError(f"a {label} bore stands upright; its angle must be 0")
    wall_style = "wavy" if is_wavy_style(style) else "straight"
    env = wall_only_envelope(item.profile, held, wall, wall_style,
                             foot=is_walls_only(style))
    columns, rows = _envelope_counts(env, zone, spec_feature, options, item.name)
    # The stored zone may predate foot-aware sizing (shell only); accept it.
    needed_x = env["zone_span_x"] + (columns - 1) * env["pitch_x"]
    needed_y = env["zone_span_y"] + (rows - 1) * env["pitch_y"]
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )
    centre_x, centre_y = zone.centre
    return {
        "item": item, "zone": zone, "held": held, "depth": depth, "wall": wall,
        "height": height, "angle": 0.0, "tilted": False, "lean": 0.0,
        "lean_axis": "x", "lean_sign": 1.0, "reach": 0.0, "drop": 0.0,
        "lean_shift": 0.0, "pitch": min(env["pitch_x"], env["pitch_y"]),
        "pitch_x": env["pitch_x"], "pitch_y": env["pitch_y"],
        "columns": columns, "rows": rows, "centre_x": centre_x, "centre_y": centre_y,
        "bore_style": style, "wall_style": wall_style, "base_z": base_z,
        "needed_x": needed_x, "needed_y": needed_y, "envelope": env,
    }


def bore_envelope_zone(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """Physical footprint of a Walls Only Bore, centred on its zone - the
    smallest rectangle holding every sleeve. ``None`` for any other holder (or
    one that cannot resolve yet)."""
    if one.kind != "bore" or one.item is None:
        return None
    try:
        options = resolved_options(box, one, base_z)
        style = normalize_bore_style(options.get("bore_style"))
        if style not in ENVELOPE_STYLES:
            return None
        item = one.item
        held = (HEX_BIT_FLATS + HEX_BIT_CLEARANCE
                if _is_hex_bit(item.profile) else item.held(item.widest))
        env = wall_only_envelope(item.profile, held, float(options["wall"]),
                                 "wavy" if is_wavy_style(style) else "straight", foot=True)
        columns, rows = _envelope_counts(env, one.zone, one, options, item.name)
    except (ValueError, KeyError, TypeError):
        return None
    need_x = env["span_x"] + (columns - 1) * env["pitch_x"]
    need_y = env["span_y"] + (rows - 1) * env["pitch_y"]
    cx, cy = one.zone.centre
    return Zone(cx - need_x / 2.0, cy - need_y / 2.0, cx + need_x / 2.0, cy + need_y / 2.0)
