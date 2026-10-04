"""Bore hole grid and centres."""

from __future__ import annotations

import math
from organizer_engine import BoxSpec
from .._core import Feature, _fit_count, _need_item
from .._registry import resolved_options

from ._consts import (
    HEX_BIT_FLATS,
    HEX_BIT_CLEARANCE,
    BORE_MOUTH_CHAMFER,
    BORE_MAX_TILT,
    bore_direction,
    normalize_bore_style,
    is_walls_only,
    BORE_STYLES,
)
from ._walls import _is_hex_bit, _hole_sides, bore_minimum_pitches
from ._settings import _wall_only_grid


def _bore_grid(box: BoxSpec, spec_feature: Feature, base_z: float) -> dict:
    """Resolve and validate a bore's grid once, for both the mesh builder and
    the preview's lean indicator. Raises the same errors ``build_bore`` used to
    raise inline, so nothing about validation changes."""
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)

    if _is_hex_bit(item.profile):
        held = HEX_BIT_FLATS + HEX_BIT_CLEARANCE
    else:
        held = item.held(item.widest)
    depth = options["depth"]
    wall = options["wall"]
    height = options["height"]
    angle = options.get("angle", 0.0)
    style = normalize_bore_style(options.get("bore_style"))
    if style not in BORE_STYLES:
        raise ValueError(f"bore style must be one of {', '.join(BORE_STYLES)}")
    if is_walls_only(style):
        # Fix 078: how far the held object can insert downward from the Bore
        # mouth before it hits its stop. A legacy Bore with no explicit value
        # keeps the through-to-floor form (effective depth = full height).
        raw_walls_depth = options.get("walls_depth")
        walls_depth = height if raw_walls_depth in (None, "") else float(raw_walls_depth)
        if not math.isfinite(walls_depth) or walls_depth <= 0.0 or walls_depth > height + 1e-9:
            raise ValueError(
                f"{item.name}: Bore Depth must be positive and no more than its height"
            )
        return _wall_only_grid(
            item, zone, spec_feature, held, wall, height, angle, style,
            (box, base_z), options, depth=walls_depth,
        )
    # A cavity as deep as the Bore is tall is valid: it reaches the normal
    # Bore/base Z, so the ordinary bin floor stays its bottom.
    if depth <= 0.0 or height <= 0.0 or wall <= 0.0 or depth > height + 1e-9:
        raise ValueError(
            f"{item.name}: bore depth must be positive and no more than its "
            "height, and height and wall must be positive"
        )
    if style == "base_wavy":
        return _wall_only_grid(
            item, zone, spec_feature, held, wall, height, angle, style,
            (box, base_z), options, depth=depth,
        )
    if not math.isfinite(angle) or not (-1e-9 <= angle <= BORE_MAX_TILT + 1e-9):
        raise ValueError(
            f"bore lean angle must be between 0 and {BORE_MAX_TILT:g} degrees off vertical"
        )

    # Every hole leans the same way by the same amount, tilting about its own
    # mouth on the flat top face. The pitch on the lean axis grows by
    # 1 / cos(angle), preserving the wall between the parallel holes.
    tilted = angle > 1e-9
    lean = math.radians(angle) if tilted else 0.0
    lean_axis, lean_sign = bore_direction(spec_feature)
    reach = depth * math.sin(lean)           # sideways travel of the hole bottom
    drop = depth * math.cos(lean)            # how far the bottom sits below the mouth
    pitch_x, pitch_y = bore_minimum_pitches(item.profile, held, wall, angle, lean_axis)
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width - (reach if lean_axis == "x" else 0.0), pitch_x, pitch_x
    )
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth - (reach if lean_axis == "y" else 0.0), pitch_y, pitch_y
    )
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {item.name}: zone is too small for a bore")

    # An angled blind hole needs the block tall enough to keep its bottom
    # buried. Grow the auto height to suit; a hand-set height that is too
    # short is an error rather than a silent breakthrough.
    if tilted:
        need_height = drop + 2.0
        if spec_feature.options.get("height") is not None:
            if height < need_height - 1e-6:
                raise ValueError(
                    f"an angled bore needs at least {need_height:.1f} mm of height "
                    f"but {height:.1f} mm is set"
                )
        else:
            height = max(height, need_height)

    needed_x = columns * pitch_x + (reach if lean_axis == "x" else 0.0)
    needed_y = rows * pitch_y + (reach if lean_axis == "y" else 0.0)
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )

    # Keep holes on their minimum printable pitch. Extra Base material remains
    # a centred outer margin; only Wall changes the gap between holes.

    centre_x, centre_y = zone.centre
    sections = _hole_sides(item.profile)
    hole_radius = held / 2.0 / (math.cos(math.pi / sections) if sections < 8 else 1.0)
    over = max(2.0, held)                    # stub above the top face for a clean mouth
    chamfer = min(BORE_MOUTH_CHAMFER, depth / 3.0, wall / 3.0)
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = lean_sign * reach / 2.0
    return {
        "item": item, "zone": zone, "held": held, "depth": depth, "wall": wall,
        "height": height, "angle": angle, "tilted": tilted, "lean": lean,
        "lean_axis": lean_axis, "lean_sign": lean_sign, "reach": reach, "drop": drop,
        "lean_shift": lean_shift, "pitch": min(pitch_x, pitch_y), "pitch_x": pitch_x,
        "pitch_y": pitch_y, "columns": columns,
        "rows": rows, "centre_x": centre_x, "centre_y": centre_y,
        "sections": sections, "hole_radius": hole_radius, "over": over,
        "chamfer": chamfer, "bore_style": style,
    }


def _bore_hole_centres(grid: dict, count: int | None):
    """(x, y) mouth centres for every hole in a resolved grid, in order."""
    columns, rows = grid["columns"], grid["rows"]
    pitch_x, pitch_y = grid["pitch_x"], grid["pitch_y"]
    centre_x, centre_y = grid["centre_x"], grid["centre_y"]
    lean_axis, lean_shift = grid["lean_axis"], grid["lean_shift"]
    made = 0
    for row in range(rows):
        for column in range(columns):
            if count is not None and made >= count:
                return
            x = centre_x + (column - (columns - 1) / 2.0) * pitch_x
            y = centre_y + (row - (rows - 1) / 2.0) * pitch_y
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift
            yield x, y
            made += 1
