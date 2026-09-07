"""Bore feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh

from organizer_engine import BoxSpec, difference, union

from ._core import Feature, _fit_count, _need_item
from ._registry import defaults, feature, resolved_options

BORE_WALL = 1.6            # material around a bore
HEX_BIT_FLATS = 6.35      # 1/4" hex driver bit, measured across the flats
HEX_BIT_SHORT_LENGTH = 25.0  # a nominal 1" insert bit
HEX_BIT_LONG_LENGTH = 38.0   # a nominal 1.5" power bit
HEX_BIT_CLEARANCE = 0.25  # snug in the hex hole but still slides in and out freely
# Hole depth per hex-bit type: holds roughly half the bit so it stands well proud
# and stays easy to pinch out.
HEX_BIT_HOLD = {"hex_bit_short": 12.0, "hex_bit_long": 16.0}
HEX_BIT_LENGTH = {
    "hex_bit_short": HEX_BIT_SHORT_LENGTH,
    "hex_bit_long": HEX_BIT_LONG_LENGTH,
}
BORE_MOUTH_CHAMFER = 0.6  # 45-degree lead-in at each hole mouth
BORE_MAX_TILT = 45.0      # steepest lean off vertical a blind-hole roof still prints
BORE_TILTED_WALL = 3.0    # thicker default wall once a bore is leaned

def _is_hex_bit(profile: str) -> bool:
    return profile in HEX_BIT_HOLD


def _hole_sides(profile: str) -> int:
    """Polygon sides for a bore hole of this profile - round is a fine circle,
    a hex bit is a six-sided socket."""
    return {
        "round": 48, "hex": 6, "square": 4,
        "hex_bit_short": 6, "hex_bit_long": 6,
    }[profile]


@defaults("bore")
def bore_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    if _is_hex_bit(item.profile):
        hole = min(HEX_BIT_HOLD[item.profile], box.z - base_z - 2.0)
        held = HEX_BIT_FLATS + HEX_BIT_CLEARANCE
    else:
        hole = min(item.length * 0.4, box.z - base_z - 2.0)
        held = item.held(item.widest)
    try:
        tilted = abs(float(one.options.get("angle", 0.0) or 0.0)) > 1e-9
    except (TypeError, ValueError):
        tilted = False
    default_wall = BORE_TILTED_WALL if tilted else BORE_WALL
    wall = float(one.options.get("wall", default_wall))
    pitch = held + wall
    cols = _fit_count(one.zone.width, pitch, held + wall)
    rows = _fit_count(one.zone.depth, pitch, held + wall)
    if one.count is not None:
        cols = min(cols, one.count)
        rows = max(1, math.ceil(one.count / max(cols, 1)))
    return {
        "depth": hole,
        # A leaned bore takes a thicker wall by default so the extra material
        # between slanting holes still prints; an explicit Wall overrides it.
        "wall": default_wall,
        "height": one.options.get("depth", hole) + 2.0,
        "columns": float(max(1, cols)),
        "rows": float(max(1, rows)),
        # 0 is straight up; a positive angle leans the holes off vertical so
        # tubes rest at a slant. Any grid may lean.
        "angle": 0.0,
    }


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
    if depth <= 0.0 or height <= 0.0 or wall <= 0.0 or depth >= height:
        raise ValueError(
            f"{item.name}: bore depth must be below its positive height and wall"
        )
    if not math.isfinite(angle) or not (-1e-9 <= angle <= BORE_MAX_TILT + 1e-9):
        raise ValueError(
            f"bore lean angle must be between 0 and {BORE_MAX_TILT:g} degrees off vertical"
        )

    pitch = held + wall
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width, pitch, held + wall
    )
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth, pitch, held + wall
    )
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {item.name}: zone is too small for a bore")

    # Every hole leans the same way by the same amount, so the whole block
    # just shifts along the lean axis - rows and columns keep their pitch and
    # any grid may lean. The zone only needs the extra sideways ``reach``.
    tilted = angle > 1e-9
    lean = math.radians(angle) if tilted else 0.0
    lean_axis = spec_feature.along           # 'x' or 'y'
    reach = depth * math.sin(lean)           # sideways travel of the hole bottom
    drop = depth * math.cos(lean)            # how far the bottom sits below the mouth

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

    needed_x = (columns - 1) * pitch + held + wall + (reach if lean_axis == "x" else 0.0)
    needed_y = (rows - 1) * pitch + held + wall + (reach if lean_axis == "y" else 0.0)
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )

    centre_x, centre_y = zone.centre
    sections = _hole_sides(item.profile)
    hole_radius = held / 2.0 / (math.cos(math.pi / sections) if sections < 8 else 1.0)
    over = max(2.0, held)                    # stub above the top face for a clean mouth
    chamfer = min(BORE_MOUTH_CHAMFER, depth / 3.0, wall / 3.0)
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = -reach / 2.0
    return {
        "item": item, "zone": zone, "held": held, "depth": depth, "wall": wall,
        "height": height, "angle": angle, "tilted": tilted, "lean": lean,
        "lean_axis": lean_axis, "reach": reach, "drop": drop,
        "lean_shift": lean_shift, "pitch": pitch, "columns": columns,
        "rows": rows, "centre_x": centre_x, "centre_y": centre_y,
        "sections": sections, "hole_radius": hole_radius, "over": over,
        "chamfer": chamfer,
    }


def _bore_hole_centres(grid: dict, count: int | None):
    """(x, y) mouth centres for every hole in a resolved grid, in order."""
    columns, rows, pitch = grid["columns"], grid["rows"], grid["pitch"]
    centre_x, centre_y = grid["centre_x"], grid["centre_y"]
    lean_axis, lean_shift = grid["lean_axis"], grid["lean_shift"]
    made = 0
    for row in range(rows):
        for column in range(columns):
            if count is not None and made >= count:
                return
            x = centre_x + (column - (columns - 1) / 2.0) * pitch
            y = centre_y + (row - (rows - 1) / 2.0) * pitch
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift
            yield x, y
            made += 1


def bore_hole_axes(
    box: BoxSpec, spec_feature: Feature, base_z: float
) -> list[tuple[tuple[float, float, float], ...]]:
    """Centre-line polylines for a leaned bore's holes, in world coordinates:
    ``(bottom, mouth, tip)`` where ``tip`` is a short stub above the mouth that
    carries the preview arrow. Empty for an upright grid - nothing to point out.
    """
    grid = _bore_grid(box, spec_feature, base_z)
    if not grid["tilted"]:
        return []
    lean, lean_axis = grid["lean"], grid["lean_axis"]
    depth, height, held = grid["depth"], grid["height"], grid["held"]
    stub = max(10.0, held)
    # Unit vector up the hole and out of the block - opposite the way the buried
    # bottom shifts. Mirrors the hole rotation in ``build_bore``.
    if lean_axis == "x":
        up = (-math.sin(lean), 0.0, math.cos(lean))
    else:
        up = (0.0, -math.sin(lean), math.cos(lean))
    mouth_z = base_z + height
    axes = []
    for x, y in _bore_hole_centres(grid, spec_feature.count):
        mouth = (x, y, mouth_z)
        bottom = (x - up[0] * depth, y - up[1] * depth, mouth_z - up[2] * depth)
        tip = (x + up[0] * stub, y + up[1] * stub, mouth_z + up[2] * stub)
        axes.append((bottom, mouth, tip))
    return axes


@feature("bore")
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
    grid = _bore_grid(box, spec_feature, base_z)
    zone = grid["zone"]
    held = grid["held"]
    depth = grid["depth"]
    wall = grid["wall"]
    height = grid["height"]
    tilted = grid["tilted"]
    lean = grid["lean"]
    lean_axis = grid["lean_axis"]
    pitch = grid["pitch"]
    columns = grid["columns"]
    rows = grid["rows"]
    centre_x = grid["centre_x"]
    centre_y = grid["centre_y"]

    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))

    sections = grid["sections"]
    hole_radius = grid["hole_radius"]
    over = grid["over"]                      # stub above the top face for a clean mouth
    chamfer = grid["chamfer"]
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = grid["lean_shift"]

    holes = []
    made = 0
    for row in range(rows):
        for column in range(columns):
            if spec_feature.count is not None and made >= spec_feature.count:
                break
            x = centre_x + (column - (columns - 1) / 2.0) * pitch
            y = centre_y + (row - (rows - 1) / 2.0) * pitch
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift

            shaft = trimesh.creation.cylinder(
                radius=hole_radius, height=depth + over, sections=sections,
            )
            shaft.apply_translation((0.0, 0.0, (over - depth) / 2.0))
            parts = [shaft]
            if chamfer > 1e-6:
                mouth = trimesh.creation.revolve(
                    [
                        (0.0, -chamfer),
                        (hole_radius, -chamfer),
                        (hole_radius + chamfer, 0.0),
                        (0.0, 0.0),
                    ],
                    sections=sections,
                )
                parts.append(mouth)
            hole = union(parts) if len(parts) > 1 else parts[0]

            if tilted:
                # Lean toward the far (high) end of the run axis: +x for a row
                # running along x, +y for one along y.
                axis = (0.0, 1.0, 0.0) if lean_axis == "x" else (1.0, 0.0, 0.0)
                sign = -1.0 if lean_axis == "x" else 1.0
                hole.apply_transform(
                    trimesh.transformations.rotation_matrix(sign * lean, axis)
                )
            hole.apply_translation((x, y, base_z + height))
            holes.append(hole)
            made += 1
    return [difference([block, union(holes)])]
