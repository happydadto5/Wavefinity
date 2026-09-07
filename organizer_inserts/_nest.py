"""Photo Nest feature defaults and geometry."""
from __future__ import annotations
import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.ops import unary_union
from organizer_engine import BoxSpec, _extrude_polygon, _extrude_xz_profile, _extrude_yz_profile, difference, union
from ._core import Feature, Zone
from ._registry import defaults, feature, resolved_options
NEST_CHAMFER = 2.0
NEST_TOP_ROUND = 1.0
NEST_FINGER_WIDTH = 25.4
NEST_PUSH_AREA = 30.0
NEST_PUSH_DEPTH = 4.0
NEST_ASSISTS = {"none", "finger_grasp", "push_out"}
NEST_FINGER_POSITIONS = {"sides", "top_bottom", "both"}
NEST_PUSH_POSITIONS = {"left", "right", "top", "bottom"}
def _softened_outline(outline: Polygon, smoothing: float) -> Polygon:
    """Round off inward and outward details smaller than ``smoothing`` mm.

    A close (fill notches) then an open (shave nubs); either can be skipped if
    it would collapse the shape. Applied in the outline's own local scale,
    before any resize/rotation, so a fixed millimetre value reads the same
    however the nest is later scaled.
    """
    if not math.isfinite(smoothing) or smoothing < 0.0:
        raise ValueError("Soften outline must be zero or greater")
    if smoothing <= 0.0:
        return outline
    closed = outline.buffer(smoothing, join_style="round").buffer(
        -smoothing, join_style="round"
    )
    opened = closed.buffer(-smoothing, join_style="round").buffer(
        smoothing, join_style="round"
    )
    if not opened.is_empty and opened.area > 1e-6:
        return opened
    return outline


def nest_smoothed_contour(one: Feature) -> tuple[tuple[float, float], ...]:
    """The stored outline with the Soften-outline pass applied, still in the
    feature's own local millimetres - before resize, rotation and placement -
    so the 2D layout can draw exactly the silhouette the part will get."""
    if not one.contour:
        raise ValueError("upload a part photo before generating a Photo Nest")
    poly = _softened_outline(
        Polygon(one.contour), float(one.options.get("smoothing", 0.0))
    )
    return tuple(
        (round(float(x), 3), round(float(y), 3))
        for x, y in list(poly.exterior.coords)[:-1]
    )


def _nest_local_polygon(one: Feature, include_clearance: bool = False) -> Polygon:
    """The resized Photo Nest outline before editor rotation and placement."""
    if not one.contour:
        raise ValueError("upload a part photo before generating a Photo Nest")
    outline = _softened_outline(
        Polygon(one.contour), float(one.options.get("smoothing", 0.0))
    )
    outline = affinity.scale(outline, xfact=one.scale, yfact=one.scale, origin=(0, 0))
    if include_clearance:
        clearance = float(one.options.get("clearance", 0.6))
        if not math.isfinite(clearance) or clearance < 0.0:
            raise ValueError("Clearance must be zero or greater")
        outline = outline.buffer(clearance, join_style="round")
    return outline


def nest_contour_polygon(one: Feature, include_clearance: bool = False) -> Polygon:
    """The photo outline after proportional resize, rotation and placement."""
    outline = _nest_local_polygon(one, include_clearance)
    outline = affinity.rotate(outline, one.rotation, origin=(0, 0), use_radians=False)
    cx, cy = one.zone.centre
    return affinity.translate(outline, xoff=cx, yoff=cy)


def nest_required_zone(one: Feature) -> Zone:
    """Tight axis-aligned footprint enclosing the cutter wall and its foot."""
    cavity = nest_contour_polygon(one, include_clearance=True)
    rim = float(one.options.get("rim", 3.0))
    if not math.isfinite(rim) or rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    outer = cavity.buffer(rim, join_style="round").buffer(NEST_CHAMFER, join_style="round")
    min_x, min_y, max_x, max_y = outer.bounds
    return Zone(float(min_x), float(min_y), float(max_x), float(max_y))


def fitted_nest_feature(one: Feature, centre: tuple[float, float] | None = None) -> Feature:
    """Recompute a Photo Nest zone after contour or fit changes."""
    if centre is None:
        centre = one.zone.centre
    cx, cy = centre
    local = replace(one, zone=Zone(-0.5, -0.5, 0.5, 0.5))
    needed = nest_required_zone(local)
    return replace(one, zone=Zone(
        cx - needed.width / 2.0, cy - needed.depth / 2.0,
        cx + needed.width / 2.0, cy + needed.depth / 2.0,
    ))


@defaults("nest")
def nest_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, object]:
    return {
        "clearance": 0.6,
        "depth": min(8.0, max(1.0, box.z - base_z)),
        "rim": 3.0,
        "smoothing": 0.0,
        "lift_assist": "finger_grasp",
        "finger_position": "sides",
        "finger_width": NEST_FINGER_WIDTH,
        "push_position": "right",
        "push_area": NEST_PUSH_AREA,
        "push_depth": NEST_PUSH_DEPTH,
    }


def _nest_transform_mesh(mesh: trimesh.Trimesh, one: Feature) -> trimesh.Trimesh:
    """Rotate a local nest detail with its outline, then place it in the layout."""
    if one.rotation:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(one.rotation), (0.0, 0.0, 1.0)
        ))
    cx, cy = one.zone.centre
    mesh.apply_translation((cx, cy, 0.0))
    return mesh


def _line_coordinates(geometry, axis: int) -> list[float]:
    """Coordinates from any Shapely line/boundary intersection."""
    if geometry.is_empty:
        return []
    if hasattr(geometry, "geoms"):
        values: list[float] = []
        for part in geometry.geoms:
            values.extend(_line_coordinates(part, axis))
        return values
    if hasattr(geometry, "coords"):
        return [float(point[axis]) for point in geometry.coords]
    return []


def _nest_finger_cutters(
    one: Feature, opening: Polygon, wall_height: float, width: float,
    position: str, base_z: float, rim: float,
) -> list[trimesh.Trimesh]:
    """Rounded U-shaped notches through chosen sides of the local nest wall."""
    min_x, min_y, max_x, max_y = opening.bounds
    inside = opening.representative_point()
    reach = rim + NEST_CHAMFER + 3.0
    radius = width / 2.0
    cutters: list[trimesh.Trimesh] = []

    if position in {"sides", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (min_x - reach, inside.y), (max_x + reach, inside.y)
        ]))
        xs = _line_coordinates(crossing, 0)
        if len(xs) < 2:
            raise ValueError("Finger grasps could not find both sides of this outline")
        profile = Point(float(inside.y), base_z + wall_height).buffer(radius, quad_segs=32)
        for boundary, direction in ((min(xs), -1.0), (max(xs), 1.0)):
            start = boundary + direction * (rim + NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_yz_profile(profile, abs(end - start))
            cutter.apply_translation(((start + end) / 2.0, 0.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))

    if position in {"top_bottom", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (inside.x, min_y - reach), (inside.x, max_y + reach)
        ]))
        ys = _line_coordinates(crossing, 1)
        if len(ys) < 2:
            raise ValueError("Finger grasps could not find both ends of this outline")
        profile = Point(float(inside.x), base_z + wall_height).buffer(radius, quad_segs=32)
        for boundary, direction in ((min(ys), -1.0), (max(ys), 1.0)):
            start = boundary + direction * (rim + NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_xz_profile(profile, abs(end - start))
            cutter.apply_translation((0.0, (start + end) / 2.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))
    return cutters


def _nest_rounded_wall(
    opening: Polygon, rim: float, height: float, base_z: float,
) -> trimesh.Trimesh:
    """One nest wall with a 2 mm outside foot and a softly rounded top."""
    outer = opening.buffer(rim, join_style="round")
    top_round = min(NEST_TOP_ROUND, rim * 0.4, height * 0.25)
    straight_height = height - top_round
    outside: list[trimesh.Trimesh] = []

    straight = _extrude_polygon(outer, straight_height)
    straight.apply_translation((0.0, 0.0, base_z))
    outside.append(straight)

    # A full 2 mm-high, 45-degree outside flare, independent of retrieval style.
    chamfer_steps = 8
    layer = NEST_CHAMFER / chamfer_steps
    for index in range(chamfer_steps):
        grow = NEST_CHAMFER - index * layer
        disk = _extrude_polygon(outer.buffer(grow, join_style="round"), layer)
        disk.apply_translation((0.0, 0.0, base_z + index * layer))
        outside.append(disk)

    # A fine layered quarter-round eases both top edges into a broad crown.
    inside: list[trimesh.Trimesh] = []
    bore = _extrude_polygon(opening, height + 2.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    inside.append(bore)
    top_steps = 8
    layer = top_round / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer
        inset = top_round - math.sqrt(max(0.0, top_round ** 2 - rise ** 2))
        top_outer = outer.buffer(-inset, join_style="round")
        top_inner = opening.buffer(inset, join_style="round")
        if top_outer.is_empty or top_inner.is_empty or not top_outer.contains(top_inner):
            raise ValueError("Outline wall is too thin for its rounded top")
        disk = _extrude_polygon(top_outer, layer)
        disk.apply_translation((0.0, 0.0, base_z + straight_height + index * layer))
        outside.append(disk)
        cut = _extrude_polygon(top_inner, layer + 0.02)
        cut.apply_translation((
            0.0, 0.0, base_z + straight_height + index * layer - 0.01
        ))
        inside.append(cut)
    return difference([union(outside), union(inside)])


def _nest_push_support(
    one: Feature, opening: Polygon, position: str, area: float,
    depth: float, base_z: float,
) -> trimesh.Trimesh:
    """Raised tool-shaped deck, leaving one selected end low for push-to-lift."""
    min_x, min_y, max_x, max_y = opening.bounds
    fraction = area / 100.0
    if position == "left":
        support = opening.intersection(shapely_box(
            min_x + (max_x - min_x) * fraction, min_y - 1.0,
            max_x + 1.0, max_y + 1.0,
        ))
    elif position == "right":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x - (max_x - min_x) * fraction, max_y + 1.0,
        ))
    elif position == "bottom":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y + (max_y - min_y) * fraction,
            max_x + 1.0, max_y + 1.0,
        ))
    else:  # top
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x + 1.0, max_y - (max_y - min_y) * fraction,
        ))
    if support.is_empty or support.area < opening.area * 0.5:
        raise ValueError("Push area leaves too little of the tool supported")
    deck = _extrude_polygon(support, depth)
    deck.apply_translation((0.0, 0.0, base_z))
    return _nest_transform_mesh(deck, one)


@feature("nest")
def build_nest(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A finished wall that traces one photographed outline.

    The wall stands straight up from ``base_z`` with the part's own footprint
    for the opening. It has a reinforced outside foot and rounded top, then
    receives either rounded finger openings or a raised push-to-lift floor.
    """
    options = resolved_options(box, spec_feature, base_z)
    clearance = options["clearance"]
    depth = options["depth"]
    rim = options["rim"]
    smoothing = options["smoothing"]
    assist = str(options["lift_assist"])
    finger_position = str(options["finger_position"])
    finger_width = float(options["finger_width"])
    push_position = str(options["push_position"])
    push_area = float(options["push_area"])
    push_depth = float(options["push_depth"])
    if not all(math.isfinite(value) for value in (
        clearance, depth, rim, smoothing, finger_width, push_area, push_depth
    )):
        raise ValueError("Photo Nest measurements must be finite")
    if clearance < 0.0:
        raise ValueError("Clearance must be zero or greater")
    if rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    if smoothing < 0.0:
        raise ValueError("Soften outline must be zero or greater")
    if assist not in NEST_ASSISTS:
        raise ValueError("Lift assist must be None, Finger grasp, or Push Out")
    if finger_position not in NEST_FINGER_POSITIONS:
        raise ValueError("Finger grasp locations must be Sides, Top/bottom, or Both")
    if finger_width < 12.0 or finger_width > 40.0:
        raise ValueError("Finger opening width must be between 12 and 40 mm")
    if push_position not in NEST_PUSH_POSITIONS:
        raise ValueError("Push position must be left, right, top, or bottom")
    if push_area < 15.0 or push_area > 40.0:
        raise ValueError("Push area must be between 15% and 40%")
    if push_depth < 2.0 or push_depth > 8.0:
        raise ValueError("Push depth must be between 2 and 8 mm")
    available = box.z - base_z
    wall_height = depth + (push_depth if assist == "push_out" else 0.0)
    if depth <= 0.0 or wall_height > available + 1e-9:
        raise ValueError(
            f"Wall height {wall_height:g} mm must be between 0 and {available:.1f} mm "
            f"above the printable floor"
        )
    fitted = fitted_nest_feature(spec_feature)
    if (abs(fitted.zone.width - spec_feature.zone.width) > 1e-4
            or abs(fitted.zone.depth - spec_feature.zone.depth) > 1e-4):
        raise ValueError("Photo Nest footprint is stale; update the outline or measurements")

    local_opening = _nest_local_polygon(spec_feature, include_clearance=True)
    world_opening = nest_contour_polygon(spec_feature, include_clearance=True)
    wall = _nest_rounded_wall(world_opening, rim, wall_height, base_z)

    if assist == "finger_grasp":
        cutters = _nest_finger_cutters(
            spec_feature, local_opening, wall_height, finger_width,
            finger_position, base_z, rim,
        )
        wall = difference([wall, union(cutters)])
    elif assist == "push_out":
        deck = _nest_push_support(
            spec_feature, local_opening, push_position, push_area,
            push_depth, base_z,
        )
        wall = union([wall, deck])
    return [wall]




