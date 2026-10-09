"""Bore reference meshes, hole axes and the main bore builder."""

from __future__ import annotations

import math
import trimesh
from shapely.geometry import Point, box as shapely_box
from shapely.ops import unary_union
from organizer_engine import BoxSpec
from organizer_geometry import difference, union
from .._core import Feature, Zone, _need_item
from .._registry import OptionDefinition, SIDE_CHOICES, feature

from ._consts import (
    BORE_ITEM_PROFILES,
    BORE_MAX_TILT,
    is_walls_only,
    FLOOR_OVERTRAVEL,
    WALL_JOIN_FLAG,
    WALL_HUG_FLAG,
    JOIN_BAND,
)
from ._walls import _hole_sides, _axis_square, _join_tabs, _tab_meshes
from ._grid import _bore_grid, _bore_hole_centres
from ._shapes import _build_wall_only_bore, _build_wavy_base_bore


def bore_reference_meshes(box: BoxSpec, one: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """Physical stored items seated at the resolved hole stops, preview only."""
    grid = _bore_grid(box, one, base_z)
    item = _need_item(one)
    sides = _hole_sides(item.profile)
    axis = (0.0, 1.0, 0.0) if grid["lean_axis"] == "x" else (1.0, 0.0, 0.0)
    sign = grid["lean_sign"] if grid["lean_axis"] == "x" else -grid["lean_sign"]
    rotation = trimesh.transformations.rotation_matrix(sign * grid["lean"], axis)
    meshes = []
    for x, y in _bore_hole_centres(grid, one.count):
        run = -grid["depth"]
        for segment in item.segments:
            # Polygon diameters are measured across flats, like their Bore
            # holes. Clearance is deliberately absent from this physical mesh.
            radius = segment.diameter / 2.0
            if sides < 8:
                radius /= math.cos(math.pi / sides)
            mesh = trimesh.creation.cylinder(radius=radius, height=segment.length, sections=sides)
            if _axis_square(item.profile):
                mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 4.0, (0, 0, 1)))
            mesh.apply_translation((0, 0, run + segment.length / 2.0))
            mesh.apply_transform(rotation)
            mesh.apply_translation((x, y, base_z + grid["height"]))
            meshes.append(mesh)
            run += segment.length
    return meshes


def bore_reference_top(box: BoxSpec, one: Feature, base_z: float) -> float:
    """Highest world point of the same physical meshes drawn in Preview."""
    return max(float(mesh.bounds[1][2]) for mesh in bore_reference_meshes(box, one, base_z))


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
    lean, lean_axis, lean_sign = grid["lean"], grid["lean_axis"], grid["lean_sign"]
    depth, held = grid["depth"], grid["held"]
    height = grid["height"]
    stub = max(10.0, held)
    # Unit vector up the hole and out of the block - opposite the way the buried
    # bottom shifts. Mirrors the per-hole tilt in ``build_bore``; the block
    # itself never rotates, so these points need no further transform.
    if lean_axis == "x":
        up = (lean_sign * math.sin(lean), 0.0, math.cos(lean))
    else:
        up = (0.0, lean_sign * math.sin(lean), math.cos(lean))
    mouth_z = base_z + height
    axes = []
    for x, y in _bore_hole_centres(grid, spec_feature.count):
        mouth = (x, y, mouth_z)
        bottom = (x - up[0] * depth, y - up[1] * depth, mouth_z - up[2] * depth)
        tip = (x + up[0] * stub, y + up[1] * stub, mouth_z + up[2] * stub)
        axes.append((bottom, mouth, tip))
    return axes


def bore_tool_clearance_zone(
    box: BoxSpec, spec_feature: Feature, base_z: float,
) -> "Zone | None":
    """Tool envelope from each bore mouth to the bin rim.

    The tool is an infinite cylinder on its bore axis.  A bin side exists only
    below the rim, and that part of a straight ray is bounded by its mouth and
    rim endpoints.  The returned rectangle includes the held-tool radius.
    """
    # Avoid making the bore geometry module depend on layout validation at
    # import time.
    from .._core import Zone

    grid = _bore_grid(box, spec_feature, base_z)
    if not grid["tilted"]:
        return None
    rise_to_rim = box.z - (base_z + grid["height"])
    if rise_to_rim <= 1e-9:
        return None

    outward = rise_to_rim * math.tan(grid["lean"])
    radius = grid["held"] / 2.0
    xs: list[float] = []
    ys: list[float] = []
    for x, y in _bore_hole_centres(grid, spec_feature.count):
        rim_x = x + grid["lean_sign"] * outward if grid["lean_axis"] == "x" else x
        rim_y = y + grid["lean_sign"] * outward if grid["lean_axis"] == "y" else y
        xs.extend((x - radius, x + radius, rim_x - radius, rim_x + radius))
        ys.extend((y - radius, y + radius, rim_y - radius, rim_y + radius))
    return Zone(min(xs), min(ys), max(xs), max(ys))


@feature(
    "bore", title="Bore", display="Bore — upright tools",
    description="Small pockets for your stuff of various sizes/shapes.",
    capabilities=("size", "along", "item"),
    item_profiles=BORE_ITEM_PROFILES,
    options=(
        OptionDefinition("Style", "bore_style", "base_straight", "enum", choices=(
            ("base_straight", "Base - Straight"), ("base_wavy", "Base - Wavy Walls"),
            ("walls_straight", "Walls Only - Straight"), ("walls_wavy", "Walls Only - Wavy")),
            note="Walls Only and Base - Wavy Walls stand upright, so their angle must be 0"),
        OptionDefinition("Height", "height", "", minimum=0.1, note="mm; blank = worked out from the bin"),
        OptionDefinition("Hole depth", "depth", "", minimum=0.1, note="mm; Base styles only; no more than the height"),
        OptionDefinition("Depth", "walls_depth", "", minimum=0.1,
            note="mm; Walls Only styles only - how far the held object inserts from the Bore mouth before its stop; "
                 "blank = through to the normal bin floor (legacy Walls Only default), never more than the height"),
        OptionDefinition("Wall", "wall", "1.6", minimum=0.1, note="mm wall around each hole"),
        OptionDefinition("X quantity", "columns", "", "integer", minimum=1, note="whole number; blank = as many as fit"),
        OptionDefinition("Y quantity", "rows", "", "integer", minimum=1, note="whole number; blank = as many as fit"),
        OptionDefinition("Angle °", "angle", "0", minimum=0.0, maximum=BORE_MAX_TILT,
            note="degrees off vertical (0 = upright); the Designer's \"Bore angle\" field shows 90 minus this "
                 "value (so displayed 90 = upright = 0 here, displayed 20 = the steepest lean = 70 here); "
                 "only Base - Straight may lean"),
        OptionDefinition("Angle towards", "angle_towards", "back", "enum", False, choices=SIDE_CHOICES,
            note="direction of a new lean; defaults Back or opposite the one rim Text; old saved Bores without this key retain their Feature.along fallback"),
        OptionDefinition("Width / Length sizing", "xy_size_mode", "manual", "enum", False, choices=(
            ("manual", "Manual"), ("bore_to_bin", "Bore to bin"), ("bin_to_bore", "Bin to bore")),
            note="Walls Only styles allow only manual or bin_to_bore"),
        OptionDefinition("Height sizing", "height_size_mode", "manual", "enum", False, choices=(
            ("manual", "Manual"), ("bore_to_bin", "Bore to bin"), ("bin_to_bore", "Bin to bore"))),
    ), order=30,
)
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
    grid = _bore_grid(box, spec_feature, base_z)
    join = bool(spec_feature.options.get(WALL_JOIN_FLAG))
    if is_walls_only(grid.get("bore_style")):
        hug = (join and bool(spec_feature.options.get(WALL_HUG_FLAG)))
        return [_build_wall_only_bore(grid, spec_feature.count, box, join, hug)]
    if grid.get("bore_style") == "base_wavy":
        return [_build_wavy_base_bore(grid, spec_feature.count, box, join)]
    zone = grid["zone"]
    held = grid["held"]
    depth = grid["depth"]
    wall = grid["wall"]
    height = grid["height"]
    tilted = grid["tilted"]
    lean = grid["lean"]
    lean_axis = grid["lean_axis"]
    lean_sign = grid["lean_sign"]
    reach = grid["reach"]
    pitch_x = grid["pitch_x"]
    pitch_y = grid["pitch_y"]
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
    hole_centres = []
    made = 0
    for row in range(rows):
        for column in range(columns):
            if spec_feature.count is not None and made >= spec_feature.count:
                break
            x = centre_x + (column - (columns - 1) / 2.0) * pitch_x
            y = centre_y + (row - (rows - 1) / 2.0) * pitch_y
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift
            hole_centres.append((x, y))

            # A cavity as deep as the Bore is tall reaches the bin floor; a hair
            # of overtravel keeps that boolean clean (never changes stored depth).
            floor = FLOOR_OVERTRAVEL if (not tilted and depth >= height - 1e-9) else 0.0
            shaft = trimesh.creation.cylinder(
                radius=hole_radius, height=depth + over + floor, sections=sections,
            )
            if _axis_square(grid["item"].profile):
                shaft.apply_transform(
                    trimesh.transformations.rotation_matrix(math.pi / 4.0, (0.0, 0.0, 1.0))
                )
            shaft.apply_translation((0.0, 0.0, (over - depth - floor) / 2.0))
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
                if _axis_square(grid["item"].profile):
                    mouth.apply_transform(
                        trimesh.transformations.rotation_matrix(
                            math.pi / 4.0, (0.0, 0.0, 1.0)
                        )
                    )
                parts.append(mouth)
            hole = union(parts) if len(parts) > 1 else parts[0]

            if tilted:
                # Rotate the hole toward the selected compass direction.
                axis = (0.0, 1.0, 0.0) if lean_axis == "x" else (1.0, 0.0, 0.0)
                sign = lean_sign if lean_axis == "x" else -lean_sign
                hole.apply_transform(
                    trimesh.transformations.rotation_matrix(sign * lean, axis)
                )
            hole.apply_translation((x, y, base_z + height))
            holes.append(hole)
            made += 1
    # The block stays an upright rectangular prism - flat top and bottom, plumb
    # sides. Only the holes lean inside it (each was tilted about its own mouth
    # above), and the zone was widened by ``reach`` to keep the leaning bottoms
    # buried. The whole block is never rotated.
    result = difference([block, union(holes)])
    if join and box is not None:
        # Fix 078: a fused Base - Straight Walls Bore that touches the bin
        # wall now follows the real interior cavity contour on every touched
        # side, the same wall-join web the wavy styles already use. The
        # keep-clear circle at each hole's mouth and leaned bottom is a safe
        # over-approximation of its tilted footprint, so a join web can never
        # graze into a cavity.
        footprint = shapely_box(
            centre_x - zone.width / 2.0, centre_y - zone.depth / 2.0,
            centre_x + zone.width / 2.0, centre_y + zone.depth / 2.0,
        )
        keep_clear_circles = []
        tilt_sign = lean_sign if lean_axis == "x" else -lean_sign
        for x, y in hole_centres:
            keep_clear_circles.append(Point(x, y).buffer(hole_radius, quad_segs=16))
            if tilted:
                bx = x + (tilt_sign * reach if lean_axis == "x" else 0.0)
                by = y + (tilt_sign * reach if lean_axis == "y" else 0.0)
                keep_clear_circles.append(Point(bx, by).buffer(hole_radius, quad_segs=16))
        keep_clear = unary_union(keep_clear_circles)
        tabs = _tab_meshes(
            _join_tabs(box, footprint, keep_clear, JOIN_BAND, wavy=False, web_width=wall),
            height, base_z,
        )
        if tabs:
            result = union([result] + tabs)
    return [result]
