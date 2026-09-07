"""Holders that go inside a bin.

The idea here is to describe **the object being stored**, not the holder. An
``Item`` is a list of ``Segment``s - a length and a diameter each - so a plain
glue stick is one segment and a hex driver is two, shaft then handle. From that
one description the builders work out the geometry for either posture: lying in
a cradle, or standing in a bore. A cradle keeps it simple and treats the item
as one plain cylinder - its overall length, at its widest diameter - so all it
ever needs is a length and a diameter.

Adding a new kind of holder means writing one function and registering it with
``@feature``. Nothing else in the module needs to know about it, and removing a
holder is deleting its function.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

import trimesh
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box as shapely_box
from shapely import affinity
from shapely.ops import unary_union

from organizer_engine import (
    BoxSpec,
    SCOOP_CURVE_SEGMENTS,
    SCOOP_HEIGHT_FRACTION,
    TEXT_CAP_HEIGHT_FLOOR,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    _rounded,
    difference,
    flat_cavity_polygon,
    intersection,
    label_placement,
    text_outline,
    text_prism,
    union,
    wavy_cavity_polygon,
)

from ._core import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    EDITOR_SNAP,
    INSERT_CLEARANCE,
    ITEM_CLEARANCE,
    LAYOUT_MODES,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    _fit_count,
    _item_dict,
    _need_item,
    cartridge_zone,
    connector_keep_out,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    load_layout,
    moved_feature,
    resized_feature,
    save_layout,
    snap_value,
    snapped_zone,
)
from ._registry import (
    Builder,
    Defaults,
    FEATURE_BUILDERS,
    FEATURE_DEFAULTS,
    defaults,
    feature,
    resolved_options,
)

# --- how much room to leave ---------------------------------------------------

RIB_THICKNESS = 1.6        # four perimeters at 0.4 - the thinnest a cradle wall may be
CRADLE_RIB_FRACTION = 0.25 # a cradle wall is this much of the tool's diameter, so it scales with the tool
CRADLE_RIB_MAX = 6.0       # but never thicker than this, however fat the tool
CRADLE_FLOOR_GAP = 2.0     # gap under the widest part of a lying object
CRADLE_MIN_FLOOR_GAP = 0.4 # thinnest bottom floor under a cradle trough
CRADLE_ALTERNATE_END_MARGIN = 0.10  # default floor left at each run-axis end
CRADLE_ALTERNATE_END_MARGIN_MAX = 0.45  # keep a real middle so troughs still cross
CRADLE_RUN_OFFSET_MAX = 1.0  # +/-100%: a trough edge reaches its zone wall
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
MAX_DIVIDER_ANGLE = 45.0   # steepest lean an FDM overhang prints support-free
MIN_WEDGE_EDGE = 0.4       # thinnest a wedge's tapered top may print
DIVIDER_CHAMFER = 1.0      # 45-degree foot flare where a divider meets the floor
BOTTOM_SLOPE_MAX = 75.0    # steepest tool-slot slope; the ramp itself is solid or
                           #   45-degree-tapered, so this is a usability cap, not a
                           #   print limit (the rise-past-the-bin check is the real one)
BOTTOM_EMBED = 0.4         # sink slope solids this far into the floor for a clean union
BOTTOM_CROSSBAR_THICKNESS = 2.4  # run-axis width of one printable support crossbar
BOTTOM_CROSSBAR_CHAMFER = 1.0    # 45-degree gusset where a crossbar meets the floor
NEST_CHAMFER = 2.0         # substantial 45-degree outside foot on a Photo Nest wall
NEST_TOP_ROUND = 1.0       # gentle round-over on both edges of the wall top
NEST_FINGER_WIDTH = 25.4   # one-inch-wide rounded finger opening
NEST_PUSH_AREA = 30.0      # percent of the outline occupied by the low press area
NEST_PUSH_DEPTH = 4.0      # how far the press end travels before reaching the floor
NEST_ASSISTS = {"none", "finger_grasp", "push_out"}
NEST_FINGER_POSITIONS = {"sides", "top_bottom", "both"}
NEST_PUSH_POSITIONS = {"left", "right", "top", "bottom"}

# A cradle notch is a half circle: any deeper and the object cannot be dropped
# in, because the opening would be narrower than the object.
MAX_NOTCH_FRACTION = 0.5


def scoop_zone(
    box: BoxSpec,
    one: "Feature",
    base_z: float,
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Zone:
    """The scoop is always full-width and starts at the front wall."""
    bounds = layout_zone(box, mode)
    try:
        depth_percent = float(one.options.get("depth", 60.0))
    except (TypeError, ValueError):
        depth_percent = 60.0
    height = (box.z - base_z) * depth_percent / 100.0
    run = min(max(height, snap), bounds.depth / 2.0)
    return snapped_zone(
        Zone(bounds.x0, bounds.y0, bounds.x1, bounds.y0 + run),
        box, mode, snap,
    )


from ._post import build_post, post_defaults
from ._pocket import POCKET_CHAMFER, POCKET_FLOOR, build_pocket, pocket_defaults


# --- cradles ------------------------------------------------------------------


def _cradle_end_margin(one: "Feature") -> float:
    """Alternate-ends clearance kept at each run-axis end, as a fraction of the
    run.

    Stored as a percent in ``options['end_margin']`` - the editor's "% from
    ends" field, which only appears once Alternate ends is on. Missing, blank or
    unparseable falls back to the historic 10%. Clamped to
    ``CRADLE_ALTERNATE_END_MARGIN_MAX`` so the two end margins can never eat the
    whole run.
    """
    raw = one.options.get("end_margin")
    if raw is None or raw == "":
        return CRADLE_ALTERNATE_END_MARGIN
    try:
        fraction = float(raw) / 100.0
    except (TypeError, ValueError):
        return CRADLE_ALTERNATE_END_MARGIN
    if not math.isfinite(fraction):
        return CRADLE_ALTERNATE_END_MARGIN
    return min(max(fraction, 0.0), CRADLE_ALTERNATE_END_MARGIN_MAX)


def _cradle_offset(one: "Feature") -> float:
    """Run-axis slide of a non-alternating cradle, as a signed fraction of the
    slack between the tool and its zone ends.

    Stored as a percent in ``options['run_offset']`` - the editor's "Offset from
    center" field. 0 (or missing / blank / unparseable) keeps the trough
    centred; +100 slides it until its end meets one zone wall, -100 the other
    way. Ignored while ``alternate_ends`` is on.
    """
    raw = one.options.get("run_offset")
    if raw is None or raw == "":
        return 0.0
    try:
        fraction = float(raw) / 100.0
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(fraction):
        return 0.0
    return min(max(fraction, -CRADLE_RUN_OFFSET_MAX), CRADLE_RUN_OFFSET_MAX)


def _cradle_wall(held: float) -> float:
    """The trough wall sized to the tool it carries.

    A thin driver shaft gets the thinnest printable wall; a fat handle gets a
    proportionally chunkier one, capped so a big tool does not grow a slab.
    Not a user setting - there is nothing to tune here that the tool diameter
    does not already decide. Split half to each side of the channel.
    """
    return min(max(held * CRADLE_RIB_FRACTION, RIB_THICKNESS), CRADLE_RIB_MAX)


# kept for callers that still import the old name (organizer_app, tests)
_cradle_rib_thickness = _cradle_wall


@defaults("cradle")
def cradle_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    return {
        "rib_thickness": _cradle_wall(item.widest),
        # 0 = neighbouring side walls fully overlap, so the joint is no
        # thicker than either exposed outer side. Raising it first separates
        # those overlapping walls, then opens a real gap.
        "spacing": 0.0,
        "floor_gap": CRADLE_FLOOR_GAP,
        # The editor's one "% from end / Offset from center" field writes to
        # whichever of these matches the Alternate ends state; the other keeps
        # its own last value. Percentages.
        "end_margin": CRADLE_ALTERNATE_END_MARGIN * 100.0,
        "run_offset": 0.0,
    }


@feature("cradle")
def build_cradle(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """Half-round troughs holding a tool lying along X or Y.

    Each tool beds into a block the length of the tool with a half-cylinder
    channel cut the whole way along its top - the entire tool, shaft and
    handle, in one continuous channel rather than balancing on two ribs. The
    channel's mouth sits on the block's top face, so the tool drops straight
    in and no layer overhangs the one below it.

    ``spacing`` sets how a row of troughs relates:

    * ``0`` - neighbours join into **one continuous body**. Their facing side
      walls fully overlap, so the joint is no thicker than an exposed side.
    * up to half a wall thickness - still one body, while the shared joint
      widens from one side-wall thickness to two.
    * beyond that - each trough is its **own** solid, with the remaining
      ``spacing`` opening as clear air between them.

    ``alternate_ends`` places every second trough near the opposite end of the
    run axis, leaving ``options['end_margin']`` percent (default ten) of that
    axis clear at each end. With ``alternate_ends`` off, ``options['run_offset']``
    percent slides every trough together along the run - signed, 0 centres them,
    +/-100 pushes a trough edge to a zone wall.
    """
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    along = spec_feature.along
    options = resolved_options(box, spec_feature, base_z)
    if along not in {"x", "y"}:
        raise ValueError("cradle orientation must be 'x' or 'y'")

    wall = options["rib_thickness"]
    spacing = options["spacing"]
    floor_gap = options["floor_gap"]
    if not math.isfinite(spacing) or spacing < 0.0:
        raise ValueError("cradle spacing must be zero or greater")

    length = item.length
    # A cradle is an open half-circle the tool simply drops into, so it takes
    # the tool at its true diameter - no fit slack, nothing to tune.
    held = item.widest
    radius = held / 2.0
    axis_z = base_z + floor_gap + held / 2.0
    trough_height = axis_z - base_z
    if floor_gap < CRADLE_MIN_FLOOR_GAP:
        raise ValueError(
            f"{item.name}: a {item.widest:g} mm tool needs at least "
            f"{CRADLE_MIN_FLOOR_GAP:g} mm of clearance under it to leave material below"
        )

    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width

    # A trough's wall is split half to each side. At zero spacing its facing
    # halves occupy the same space: the middle joint is one side-wall thick,
    # exactly matching either exposed outside edge rather than becoming 2x.
    side_wall = wall / 2.0
    body = held + wall            # one trough, wall split to either side
    pitch = held + side_wall + spacing
    count = spec_feature.count
    if count is None:
        count = _fit_count(across, pitch, body)
    if count < 1:
        raise ValueError(
            f"no room for {item.name}: {across:.1f} mm across needs at least "
            f"{body:.1f} mm"
        )
    used = (count - 1) * pitch + body
    if used > across + 1e-9:
        raise ValueError(
            f"{count} x {item.name} needs {used:.1f} mm across but the zone "
            f"gives {across:.1f} mm"
        )

    alternating = bool(spec_feature.alternate_ends) and count > 1
    end_margin = _cradle_end_margin(spec_feature)
    minimum_alternate_run = length / (1.0 - 2.0 * end_margin)
    if alternating and run + 1e-9 < minimum_alternate_run:
        raise ValueError(
            f"{item.name} is {length:g} mm long, alternating ends need room "
            f"for {end_margin:.0%} end clearance, but its zone only runs "
            f"{run:.1f} mm along {along}"
        )
    if not alternating and length > run + 1e-9:
        raise ValueError(
            f"{item.name} is {length:g} mm long but its zone only runs "
            f"{run:.1f} mm along {along}"
        )

    centre_along, centre_across = zone.centre
    if along != "x":
        centre_along, centre_across = centre_across, centre_along
    first = centre_across - (count - 1) * pitch / 2.0
    seats = [first + index * pitch for index in range(count)]

    # A non-alternating row can be slid bodily along the run; the slide is a
    # fraction of the slack between the tool and the zone ends, so it can never
    # push a trough past a wall.
    offset_shift = (
        0.0 if alternating
        else _cradle_offset(spec_feature) * max(0.0, (run - length) / 2.0)
    )

    def _channel(seat: float, shift: float) -> trimesh.Trimesh:
        cut = trimesh.creation.cylinder(
            radius=radius, height=length + 2.0, sections=48
        )
        cut.apply_transform(
            trimesh.transformations.rotation_matrix(
                math.pi / 2.0, (0, 1, 0) if along == "x" else (1, 0, 0)
            )
        )
        cut.apply_translation(
            (centre_along + shift, seat, axis_z) if along == "x"
            else (seat, centre_along + shift, axis_z)
        )
        return cut

    def _body(block_seat: float, block_across: float,
              channel_seats: list[float], shift: float) -> trimesh.Trimesh:
        block = trimesh.creation.box(
            extents=(
                length if along == "x" else block_across,
                block_across if along == "x" else length,
                trough_height,
            )
        )
        block.apply_translation(
            (centre_along + shift, block_seat, base_z + trough_height / 2.0)
            if along == "x"
            else (block_seat, centre_along + shift, base_z + trough_height / 2.0)
        )
        cuts = [_channel(seat, shift) for seat in channel_seats]
        return difference(
            [block, union(cuts) if len(cuts) > 1 else cuts[0]]
        )

    # Neighbours whose blocks touch or overlap (spacing up to one side wall)
    # come out as one continuous body; wider spacing splits them apart.
    if count > 1 and not alternating and spacing <= side_wall + 1e-9:
        return [_body(centre_across, used, seats, offset_shift)]

    solids: list[trimesh.Trimesh] = []
    alternate_shift = (
        (run - length) / 2.0 - end_margin * run
        if alternating else 0.0
    )
    for index, seat in enumerate(seats):
        shift = (
            (alternate_shift if index % 2 else -alternate_shift)
            if alternating else offset_shift
        )
        solids.append(_body(seat, body, [seat], shift))
    return solids


def cradle_min_footprint(one: Feature) -> tuple[float, float]:
    """The smallest ``(width, depth)`` a cradle needs for its tool, count and
    spacing - regardless of what its zone has been clamped to. Mirrors the
    sizing in :func:`build_cradle`; used to grow a bin to fit its contents.
    """
    item = _need_item(one)
    wall = _cradle_wall(item.widest)
    try:
        spacing = float(one.options.get("spacing", 0.0))
    except (TypeError, ValueError) as error:
        raise ValueError("cradle spacing must be zero or greater") from error
    if not math.isfinite(spacing) or spacing < 0.0:
        raise ValueError("cradle spacing must be zero or greater")
    count = one.count or 1
    length = item.length
    alternating = bool(one.alternate_ends) and count > 1
    run = math.ceil(
        length / (1.0 - 2.0 * _cradle_end_margin(one))
        if alternating else length
    )
    body = item.widest + wall
    pitch = item.widest + wall / 2.0 + spacing
    across = math.ceil((count - 1) * pitch + body)
    return (float(run), float(across)) if one.along == "x" else (float(across), float(run))


# --- photo nests --------------------------------------------------------------


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


# --- bores --------------------------------------------------------------------


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


@feature("bore")
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
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
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))

    sections = _hole_sides(item.profile)
    hole_radius = held / 2.0 / (math.cos(math.pi / sections) if sections < 8 else 1.0)
    over = max(2.0, held)                    # stub above the top face for a clean mouth
    chamfer = min(BORE_MOUTH_CHAMFER, depth / 3.0, wall / 3.0)
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = -reach / 2.0

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


# --- plain shapes -------------------------------------------------------------


@defaults("divider")
def divider_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    zone = one.zone
    along = one.along
    count = one.count or 1
    span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
    return {
        "thickness": RIB_THICKNESS,
        "height": connector_keep_out(box) - base_z,
        "angle": 0.0,
        # Fence-post spacing: this many equal gaps fill the zone's cross
        # axis, including from each end divider to its side of the zone -
        # so at count == 1 it lands the one divider exactly on the zone's
        # own centre. An explicit value overrides this and is used as-is
        # (see build_divider), which only stays centred if it happens to
        # equal this same auto value.
        "spacing": span / (count + 1),
        # Sloped tool-slot bottoms - see _divider_support_bottoms. A zero
        # angle adds nothing, so an older design with none of these keys
        # keeps exactly the geometry it always had.
        "bottom_angle": 0.0,
        "reverse_bottom": 0,
        "alternate_bottom": 0,
        "minimal_bottom": 0,
        "bottom_supports": 3,
    }


def _divider_cross_centres(zone: Zone, along: str, count: int, spacing: float) -> list[float]:
    """``count`` positions, ``spacing`` apart, starting ``spacing`` in from
    the zone's low edge on its cross axis - the same fence-post arrangement
    ``divider_defaults`` sizes ``spacing`` to fill exactly, so the auto case
    is centred; an explicit spacing is simply used as the gap and may leave
    the group off-centre or short of the far edge.
    """
    low = zone.y0 if along == "x" else zone.x0
    return [low + (index + 1) * spacing for index in range(count)]


@feature("divider")
def build_divider(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """One or more evenly spaced parallel walls subdividing the bin."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    thickness = options["thickness"]
    height = options["height"]
    angle = options.get("angle", 0.0)
    if thickness <= 0.0 or height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("divider thickness and height must fit inside the bin")
    along = spec_feature.along
    count = spec_feature.count or 1
    if count < 1:
        raise ValueError("divider count must be positive or automatic")
    spacing = options["spacing"]
    if spacing <= 0.0:
        raise ValueError("divider spacing must be positive")
    if count > 1:
        lean = height * math.tan(math.radians(angle)) if angle else 0.0
        needed_gap = thickness + 2.0 * abs(lean)
        if spacing < needed_gap:
            raise ValueError(
                f"{count} dividers {spacing:.1f} mm apart need at least "
                f"{needed_gap:.1f} mm between centres - increase spacing, "
                "reduce thickness, or reduce the angle"
            )
    span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
    needed_span = spacing * (count + 1)
    if needed_span > span + 1e-9:
        raise ValueError(
            f"{count} dividers {spacing:.1f} mm apart need {needed_span:.1f} mm "
            f"across but the zone gives {span:.1f} mm"
        )
    centres = _divider_cross_centres(zone, along, count, spacing)
    solids: list[trimesh.Trimesh] = []
    for cross_centre in centres:
        shift = cross_centre - (zone.centre[1] if along == "x" else zone.centre[0])
        one_zone = (
            Zone(zone.x0, zone.y0 + shift, zone.x1, zone.y1 + shift) if along == "x"
            else Zone(zone.x0 + shift, zone.y0, zone.x1 + shift, zone.y1)
        )
        one = replace(spec_feature, zone=one_zone)
        if angle != 0.0 and one.full_span:
            solids.extend(_full_span_leaning_divider(box, one, thickness, height, angle, base_z))
        elif one.full_span:
            solids.extend(_full_span_divider(box, along, cross_centre, thickness, base_z, height))
        else:
            solids.extend(_divider_wall(box, one, thickness, height, angle, base_z))
    bottom_angle = float(options.get("bottom_angle", 0.0) or 0.0)
    if bottom_angle:
        raw_supports = options.get("bottom_supports", 3)
        supports = (int(round(float(raw_supports)))
                    if raw_supports not in (None, "") else 3)
        solids.extend(_divider_support_bottoms(
            box, zone, along, centres, height, base_z, bottom_angle,
            _option_flag(options.get("reverse_bottom")),
            _option_flag(options.get("alternate_bottom")),
            _option_flag(options.get("minimal_bottom")),
            supports, spec_feature.full_span,
        ))
    return solids


def _option_flag(value: object) -> bool:
    """A yes/no option however it arrived - real bool, or a browser string."""
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "off"}
    return bool(value)


def _bottom_slot_bounds(
    zone: Zone, along: str, centres: Iterable[float],
) -> list[tuple[float, float]]:
    """The N+1 tool slots a divider's N wall centres cut its zone into.

    Boundaries are the wall centres plus the zone's own two cross-axis edges
    (see the task's "slot boundaries from the divider centers and the divider
    zone's two cross-axis boundaries"), ordered low to high so ``Alternate
    slopes`` can walk them in a stable order.
    """
    if along == "x":
        edges = sorted([zone.y0, *centres, zone.y1])
    else:
        edges = sorted([zone.x0, *centres, zone.x1])
    return [(edges[index], edges[index + 1]) for index in range(len(edges) - 1)]


def _bottom_plane_z(r: float, r0: float, r1: float, rise: float,
                    base_z: float, reverse: bool) -> float:
    """Height of the theoretical sloped plane at run coordinate ``r``.

    Low end at ``base_z`` (the existing support surface); the high end
    ``rise`` above it, toward +run unless ``reverse`` flips it toward -run.
    """
    frac = (r - r0) / (r1 - r0)
    return base_z + (1.0 - frac if reverse else frac) * rise


def _extrude_bottom(
    profile: Polygon, along: str, cross_lo: float, cross_hi: float,
) -> trimesh.Trimesh:
    """Extrude a ``(run, z)`` profile across one slot's cross-axis span.

    The shape varies along the run, so - unlike a divider wall, whose section
    is constant along its length - the profile is the run/z plane and the
    extrusion is across the slot width.
    """
    width = cross_hi - cross_lo
    centre = (cross_lo + cross_hi) / 2.0
    if along == "x":
        solid = _extrude_xz_profile(profile, width)
        solid.apply_translation((0.0, centre, 0.0))
    else:
        solid = _extrude_yz_profile(profile, width)
        solid.apply_translation((centre, 0.0, 0.0))
    return solid


def _divider_support_bottoms(
    box: BoxSpec, zone: Zone, along: str, centres: list[float], height: float,
    base_z: float, angle: float, reverse: bool, alternate: bool,
    minimal: bool, supports: int, full_span: bool = False,
) -> list[trimesh.Trimesh]:
    """Sloped support under each tool slot so a tool rests tilted, not flat.

    ``angle`` is signed: positive rises along the divider/tool direction - +X
    (to the right) for a divider that runs along x, +Y (to the back) along y -
    and negative rises the other way, toward the left or front. ``reverse``
    flips that whole pattern once more (kept for older saved designs that set
    it as a separate flag); ``alternate`` flips every second slot, ordered
    across the divider zone. A full bottom is one continuous wedge per slot;
    ``minimal`` replaces it with ``supports`` evenly spaced crossbars and uses
    materially less plastic.

    A crossbar hangs off the walls at the height it carries the tool, never
    reaching the floor. Its underside is an inverted V: a 45-degree corbel
    grows inward from the wall on each side of the slot until the two meet at
    a central ridge, and a full bar rides the slope on top of that ridge. The
    whole underside is at 45 degrees and the top faces up, so it prints with
    no support. Where the corbels have no room to meet before the floor - a
    wide slot, or a crossbar down near the low end of the slope - or the slot
    has no wall to hang from (an open end of a divider set into bare floor,
    never a ``full_span`` divider, which has the bin's own side walls), it
    falls back to a floor-standing stem with 45-degree gusset feet. The normal
    bin or insert floor is untouched; this is only the material above it.
    Solids sink ``BOTTOM_EMBED`` into the floor (or into a wall) for a clean
    union.
    """
    if not math.isfinite(angle) or abs(angle) > BOTTOM_SLOPE_MAX:
        raise ValueError(
            f"the slope must be within {BOTTOM_SLOPE_MAX:g} degrees either way; "
            "reduce the slope"
        )
    if angle == 0.0:
        return []
    # A negative slope just points the rise the other way - same wedge,
    # mirrored - so fold its sign into ``reverse`` and work with a magnitude.
    reverse = bool(reverse) ^ (angle < 0.0)
    angle = abs(angle)
    if minimal and supports < 1:
        raise ValueError("number of crossbars must be a positive whole number")
    run = zone.width if along == "x" else zone.depth
    r0, r1 = (zone.x0, zone.x1) if along == "x" else (zone.y0, zone.y1)
    rise = run * math.tan(math.radians(angle))
    if rise > height + 1e-6 or base_z + rise > box.z + 1e-6:
        raise ValueError(
            "the bottom slope's high end rises past the divider height or the "
            "bin: reduce the bottom slope, shorten the run, or increase the "
            "bin height"
        )
    half_t = BOTTOM_CROSSBAR_THICKNESS / 2.0
    bar_min = 0.8                  # thinnest the "full bar" above the ridge may be
    edge_lo, edge_hi = (zone.y0, zone.y1) if along == "x" else (zone.x0, zone.x1)
    wall_line = box.half_y if along == "x" else box.half_x
    solids: list[trimesh.Trimesh] = []
    for index, (c_lo, c_hi) in enumerate(_bottom_slot_bounds(zone, along, centres)):
        flip = reverse ^ (alternate and index % 2 == 1)
        if not minimal:
            if not flip:
                pts = [(r0, base_z - BOTTOM_EMBED), (r1, base_z - BOTTOM_EMBED),
                       (r1, base_z + rise), (r0, base_z)]
            else:
                pts = [(r0, base_z - BOTTOM_EMBED), (r1, base_z - BOTTOM_EMBED),
                       (r1, base_z), (r0, base_z + rise)]
            solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
            continue
        # Which side of this slot has a wall to hang a crossbar from. A
        # full-span divider always does on both sides (its own wall, and the
        # bin's); a bare-floor divider's outermost slot has an open end.
        lo_is_edge = math.isclose(c_lo, edge_lo, abs_tol=1e-6)
        hi_is_edge = math.isclose(c_hi, edge_hi, abs_tol=1e-6)
        floating = full_span or (not lo_is_edge and not hi_is_edge)
        # Weld a floating crossbar into the bin's side wall where the slot ends
        # at the zone edge instead of at a divider wall.
        span_lo = -wall_line if (lo_is_edge and full_span) else c_lo
        span_hi = wall_line if (hi_is_edge and full_span) else c_hi
        span_mid = (span_lo + span_hi) / 2.0
        half_span = (span_hi - span_lo) / 2.0
        for step in range(supports):
            centre = r0 + (step + 1) * run / (supports + 1)
            z_left = _bottom_plane_z(centre - half_t, r0, r1, rise, base_z, flip)
            z_right = _bottom_plane_z(centre + half_t, r0, r1, rise, base_z, flip)
            low = min(z_left, z_right)
            # A floating crossbar is a 45-degree corbel growing inward from the
            # wall on each side of the slot; the two meet at a central ridge and
            # a full bar rides the slope on top of it. Its whole underside is at
            # 45 degrees so it prints support-free, and it never reaches the
            # floor. That needs head-room: the corbels climb half the slot's
            # width to meet. Where there isn't room - a wide slot, or a crossbar
            # down near the low end of the slope - fall back to the old
            # floor-standing stem, which prints fine on its own gusset feet.
            z_ridge = low - bar_min
            z_base = z_ridge - half_span
            if not (floating and z_base >= base_z - BOTTOM_EMBED - 1e-9):
                top_left = max(z_left, base_z + 0.2)
                top_right = max(z_right, base_z + 0.2)
                # 45-degree gusset feet, never taller than the stem they brace.
                chamfer = max(0.0, min(BOTTOM_CROSSBAR_CHAMFER,
                                       top_left - base_z - 0.1,
                                       top_right - base_z - 0.1))
                pts = [
                    (centre - half_t - chamfer, base_z - BOTTOM_EMBED),
                    (centre + half_t + chamfer, base_z - BOTTOM_EMBED),
                    (centre + half_t, base_z + chamfer),
                    (centre + half_t, top_right),
                    (centre - half_t, top_left),
                    (centre - half_t, base_z + chamfer),
                ]
                solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
                continue
            # Inverted-V underside spanning wall to wall, capped by the slope.
            z_ceiling = max(z_left, z_right) + 5.0
            v_profile = Polygon([
                (span_lo, z_base), (span_mid, z_ridge), (span_hi, z_base),
                (span_hi, z_ceiling), (span_lo, z_ceiling),
            ])
            cap_profile = Polygon([
                (centre - half_t, z_base - 5.0), (centre + half_t, z_base - 5.0),
                (centre + half_t, z_right), (centre - half_t, z_left),
            ])
            if along == "x":
                under = _extrude_yz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                under.apply_translation((centre, 0.0, 0.0))
                cap = _extrude_xz_profile(cap_profile, span_hi - span_lo)
                cap.apply_translation((0.0, span_mid, 0.0))
            else:
                under = _extrude_xz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                under.apply_translation((0.0, centre, 0.0))
                cap = _extrude_yz_profile(cap_profile, span_hi - span_lo)
                cap.apply_translation((span_mid, 0.0, 0.0))
            bar = intersection([under, cap])
            if bar.faces.shape[0] == 0:
                continue
            solids.append(bar)
    return solids


def _divider_wall(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """A straight or leaning divider, up to ``MAX_DIVIDER_ANGLE`` off vertical.

    A thin wall sheared over bodily at an angle is an unsupported FDM
    overhang with no more material at its base than anywhere else along its
    height - exactly the shape that snaps off under the sideways load of
    whatever is leaning against it. The default instead builds a wedge: the
    top keeps the asked-for ``thickness`` and leans over by ``lean``, while
    the base widens on the trailing side to a vertical face, so the wall is
    thickest right where that load actually bears - at the floor - and
    slims to the asked-for thickness at the top, the shape a physical gusset
    or bracket would use. ``wedge=False`` gets the plain sheared wall
    instead: uniform thickness throughout, for the rare case that is
    genuinely wanted.

    Every divider - wedge, straight or plain vertical - also gets a
    ``DIVIDER_CHAMFER`` 45-degree foot where it meets the floor: the two
    long faces flare out by that much at ``base_z`` and taper back to the
    wall's own line by ``DIVIDER_CHAMFER`` above it. It is a pure addition
    below the wall's nominal profile, not a substitute for any of it, so
    the lean and thickness above that point are exactly what was asked for.
    """
    if not math.isfinite(angle) or abs(angle) > MAX_DIVIDER_ANGLE:
        raise ValueError(
            f"a divider's angle must be within {MAX_DIVIDER_ANGLE:g} degrees of vertical"
        )
    if height <= DIVIDER_CHAMFER:
        raise ValueError(
            f"a divider must stand taller than its {DIVIDER_CHAMFER:g} mm base chamfer"
        )
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
    along = spec_feature.along
    cross_centre = centre_y if along == "x" else centre_x
    lean = height * math.tan(math.radians(angle))
    half_t = thickness / 2.0
    base_low, base_high = cross_centre - half_t, cross_centre + half_t
    if thickness < MIN_WEDGE_EDGE:
        raise ValueError(
            f"a divider must be at least {MIN_WEDGE_EDGE:g} mm thick"
        )
    if spec_feature.wedge:
        # The top slab keeps the asked-for thickness but leans over by
        # ``lean``; the base holds one face vertical and widens on the
        # trailing side to meet it, so the wedge is thick at the floor.
        top_low, top_high = base_low + lean, base_high + lean
        if lean >= 0.0:
            base_high = top_high
        else:
            base_low = top_low
    else:
        top_low, top_high = base_low + lean, base_high + lean
    # Where the wall's own (un-chamfered) line would sit at chamfer height -
    # the chamfer's inner edge lands exactly here, so the taper above it is
    # untouched.
    frac = DIVIDER_CHAMFER / height
    chamfer_low = base_low + frac * (top_low - base_low)
    chamfer_high = base_high + frac * (top_high - base_high)
    chamfer_z = base_z + DIVIDER_CHAMFER
    profile = Polygon([
        (base_low - DIVIDER_CHAMFER, base_z), (base_high + DIVIDER_CHAMFER, base_z),
        (chamfer_high, chamfer_z), (top_high, base_z + height),
        (top_low, base_z + height), (chamfer_low, chamfer_z),
    ])
    if not profile.is_valid:
        raise ValueError("that divider angle and thickness do not form a valid wall")
    run = zone.width if along == "x" else zone.depth
    if along == "x":
        wall = _extrude_yz_profile(profile, run)
        wall.apply_translation((centre_x, 0.0, 0.0))
    else:
        wall = _extrude_xz_profile(profile, run)
        wall.apply_translation((0.0, centre_y, 0.0))
    return [wall]


def _full_span_leaning_divider(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """A leaning divider that also reaches the box's true wavy wall.

    Full span and a lean each bend one of the same assumption in a
    different place: a full-span divider's run-axis reach is the wave, not
    the safe rectangle; a leaning divider's cross-axis position shifts with
    height instead of staying put. Together, the divider's own end face is
    no longer flat, or even the same shape at every height, so the 2D
    polygon-clip the plain full-span divider uses no longer applies on its
    own. This instead builds the oversized leaning wedge as a real 3D solid
    - exactly what ``_divider_wall`` already builds (base chamfer included),
    just wider - and intersects it against the box's actual interior
    volume, the same boolean a standalone insert is already trimmed to its
    footprint with.
    """
    along = spec_feature.along
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
    oversized_zone = (
        Zone(centre_x - half_run, zone.y0, centre_x + half_run, zone.y1)
        if along == "x" else
        Zone(zone.x0, centre_y - half_run, zone.x1, centre_y + half_run)
    )
    wedge = _divider_wall(
        box, replace(spec_feature, zone=oversized_zone), thickness, height,
        angle, base_z,
    )[0]

    z0, z1 = base_z, base_z + height
    flat_top = box.base_thickness + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        band = _extrude_polygon(flat_cavity_polygon(box), min(z1, flat_top) - z0)
        band.apply_translation((0.0, 0.0, z0))
        pieces.append(intersection([wedge, band]))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        above = _extrude_polygon(wavy_cavity_polygon(box), z1 - wavy_z0)
        above.apply_translation((0.0, 0.0, wavy_z0))
        pieces.append(intersection([wedge, above]))
    if not pieces or any(len(piece.faces) == 0 for piece in pieces):
        raise ValueError("no room for a leaning full-width divider at this position")
    return pieces


def _trimmed_prism(strip: Polygon, cavity: Polygon, z0: float, z1: float) -> trimesh.Trimesh:
    """``strip`` cut back to wherever ``cavity`` actually allows it, then extruded."""
    trimmed = strip.intersection(cavity)
    if trimmed.is_empty:
        raise ValueError("no room for a full-width divider at this position")
    if isinstance(trimmed, MultiPolygon):
        trimmed = max(trimmed.geoms, key=lambda item: item.area)
    prism = _extrude_polygon(trimmed, z1 - z0)
    prism.apply_translation((0.0, 0.0, z0))
    return prism


def _full_span_divider(
    box: BoxSpec, along: str, cross_centre: float, thickness: float,
    base_z: float, height: float,
) -> list[trimesh.Trimesh]:
    """A divider that runs edge to edge, hugging the box's true interior wall.

    A straight rib sized to the safe usable rectangle - the only rectangle
    guaranteed to clear the wave at *every* position - still leaves the
    wave's own swing as a gap at most positions, because that rectangle is
    pulled in by a full amplitude just to stay valid everywhere. A divider
    only has to be right at its own position, so instead it is built
    oversized and trimmed back against the box's real interior outline: the
    flat, straight-sided band near the floor if the box has one, the wavy
    profile above it - exactly the same outlines the wall itself is built
    from, so the two can never disagree.
    """
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    half_thick = thickness / 2.0
    strip = (
        shapely_box(-half_run, cross_centre - half_thick, half_run, cross_centre + half_thick)
        if along == "x" else
        shapely_box(cross_centre - half_thick, -half_run, cross_centre + half_thick, half_run)
    )
    z0, z1 = base_z, base_z + height
    flat_top = box.base_thickness + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        pieces.append(_trimmed_prism(strip, flat_cavity_polygon(box), z0, min(z1, flat_top)))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        pieces.append(_trimmed_prism(strip, wavy_cavity_polygon(box), wavy_z0, z1))
    if not pieces:
        raise ValueError("divider height leaves nothing to build")
    return pieces


# --- slots -------------------------------------------------------------------


@defaults("slot")
def slot_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    hole = min(14.0, max(2.0, box.z - base_z - 4.0))
    height = one.options.get("depth", hole) + 2.0
    return {
        "depth": hole,
        "thickness": 4.0,
        "wall": 1.6,
        "angle": 20.0,
        "height": height,
    }


@feature("slot")
def build_slot(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of angled, backward-leaning slots for bits, cards, and tools."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    depth = options["depth"]
    thickness = options["thickness"]
    wall = options["wall"]
    angle = options.get("angle", 20.0)
    height = options["height"]

    if (depth <= 0.0 or thickness <= 0.0 or wall <= 0.0 or height <= 0.0
            or depth >= height or abs(angle) > 45.0):
        raise ValueError("slot depth, thickness, wall and height must be positive, "
                         "depth must be less than height, and angle <= 45°")
    if base_z + height > box.z + 1e-9:
        raise ValueError("slot height must fit inside the bin")

    along = spec_feature.along
    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width

    if 2.0 * wall >= run or 2.0 * wall >= across:
        raise ValueError("zone is too small for a slot rack with the given wall thickness")

    slot_len = run - 2.0 * wall
    rad = math.radians(angle)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    pitch = (thickness + wall) / cos_a
    count = spec_feature.count
    if count is None:
        count = max(1, int((across - 2.0 * wall - thickness / cos_a) // pitch) + 1)
    if count < 1:
        raise ValueError(f"no room for slot rack: {across:.1f} mm across needs at least {pitch + 2.0 * wall:.1f} mm")

    used_across = (count - 1) * pitch + (thickness / cos_a) + 2.0 * wall
    if used_across > across + 1e-9:
        raise ValueError(f"{count} slots need {used_across:.1f} mm across but zone gives {across:.1f} mm")

    centre_x, centre_y = zone.centre
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))

    cutter_len = (depth + 4.0) / cos_a
    d_mid = cutter_len / 2.0 - 2.0
    top_z = base_z + height
    cut_mid_z = top_z - d_mid * cos_a
    cut_shift = -d_mid * sin_a

    centre_cross = centre_y if along == "x" else centre_x
    first = centre_cross - ((count - 1) * pitch) / 2.0
    cutters = []

    for i in range(count):
        c_cross = first + i * pitch
        c = trimesh.creation.box(extents=(
            slot_len if along == "x" else thickness,
            thickness if along == "x" else slot_len,
            cutter_len,
        ))
        rot_axis = (1, 0, 0) if along == "x" else (0, 1, 0)
        c.apply_transform(trimesh.transformations.rotation_matrix(rad, rot_axis))
        if along == "x":
            c.apply_translation((centre_x, c_cross + cut_shift, cut_mid_z))
        else:
            c.apply_translation((c_cross + cut_shift, centre_y, cut_mid_z))
        cutters.append(c)

    return [difference([block, union(cutters) if len(cutters) > 1 else cutters[0]])]


# --- steps -------------------------------------------------------------------


@defaults("steps")
def steps_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {
        "height": min(16.0, max(4.0, box.z - base_z - 2.0)),
        "lip": 1.0,
    }


@feature("steps")
def build_steps(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A stepped stadium-riser platform stepping up across the zone."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    lip = max(0.0, float(options.get("lip", 1.0)))
    count = spec_feature.count or int(options.get("count", 3))

    if count < 1:
        raise ValueError("steps count must be at least 1")
    if height <= 0.0 or base_z + height + lip > box.z + 1e-9:
        raise ValueError("steps height must fit inside the bin")

    along = spec_feature.along
    if along == "x":
        span = zone.depth
        width = zone.width
        u0, u1 = zone.y0, zone.y1
    else:
        span = zone.width
        width = zone.depth
        u0, u1 = zone.x0, zone.x1

    step_run = span / count
    step_rise = height / count

    pts = [(u0, base_z)]
    for i in range(count):
        u_start = u0 + i * step_run
        u_end = u0 + (i + 1) * step_run
        z_tread = base_z + (i + 1) * step_rise

        if lip > 0.0:
            pts.append((u_start, z_tread + lip))
            lip_run = min(lip, step_run * 0.25)
            pts.append((u_start + lip_run, z_tread))
            pts.append((u_end, z_tread))
        else:
            pts.append((u_start, z_tread))
            pts.append((u_end, z_tread))

    pts.append((u1, base_z))

    poly = Polygon(pts)
    if not poly.is_valid:
        raise ValueError("invalid step profile generated")

    if along == "x":
        solid = _extrude_yz_profile(poly, width)
        solid.apply_translation((zone.centre[0], 0.0, 0.0))
    else:
        solid = _extrude_xz_profile(poly, width)
        solid.apply_translation((0.0, zone.centre[1], 0.0))

    return [solid]


# --- scoop -------------------------------------------------------------------


@defaults("scoop")
def scoop_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {
        "depth": SCOOP_HEIGHT_FRACTION * 100.0,
    }


@feature("scoop")
def build_scoop(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A full-zone curved retrieval ramp rising up the wall."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    if "depth" in spec_feature.options:
        depth_percent = float(options["depth"])
        if depth_percent <= 0.0 or depth_percent > 100.0:
            raise ValueError("scoop depth must be between 1 and 100 percent")
        height = (box.z - base_z) * depth_percent / 100.0
    else:
        # Keep older saved interior scoops usable. New designs use depth (%).
        height = float(options.get("height", (box.z - base_z) * SCOOP_HEIGHT_FRACTION))
    if height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("scoop height must fit inside the bin")

    along = spec_feature.along
    floor_z = base_z
    centre_z = floor_z + height

    if along == "x":
        wall_y = zone.y0
        run = zone.depth
        inner_y = zone.y1
        curve = [
            (
                inner_y - run * math.cos(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
                centre_z + height * math.sin(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
            )
            for i in range(SCOOP_CURVE_SEGMENTS + 1)
        ]
        profile = Polygon([
            (inner_y, floor_z),
            (wall_y, floor_z),
            (wall_y, centre_z),
            *curve[1:-1],
        ])
        if not profile.is_valid:
            raise ValueError("invalid scoop profile generated")
        solid = _extrude_yz_profile(profile, zone.width)
        solid.apply_translation((zone.centre[0], 0.0, 0.0))
    else:
        wall_x = zone.x0
        run = zone.width
        inner_x = zone.x1
        curve = [
            (
                inner_x - run * math.cos(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
                centre_z + height * math.sin(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
            )
            for i in range(SCOOP_CURVE_SEGMENTS + 1)
        ]
        profile = Polygon([
            (inner_x, floor_z),
            (wall_x, floor_z),
            (wall_x, centre_z),
            *curve[1:-1],
        ])
        if not profile.is_valid:
            raise ValueError("invalid scoop profile generated")
        solid = _extrude_xz_profile(profile, zone.depth)
        solid.apply_translation((0.0, zone.centre[1], 0.0))

    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return [solid]


# --- text --------------------------------------------------------------------
#
# Lettering is an interior part like any other: it owns a zone, it is dragged,
# resized and turned in the same editor, and it keeps its neighbours out of its
# own floor.  What makes it different is only how it is assembled - a recessed
# text is subtracted from the body it sits in rather than added to it, and
# either way it stays its own object in the 3MF so a slicer can give it its own
# filament.  ``build_features`` therefore builds it (so its errors surface with
# every other feature's) but leaves it out of the additive union; the exporter
# collects it through ``build_texts``.

TEXT_KIND = "text"
TEXT_ZONE_EPSILON = 0.01     # glyph bounds land exactly on the zone; see _feature_reach

# Every other holder's options are numbers, and the browser layer converts
# them as such. Text brought the first that are not: what it says, and two
# yes/no choices. Naming them here keeps that conversion honest instead of
# letting it guess from the value it happens to receive.
NON_NUMERIC_OPTIONS = {
    "text": "string", "auto": "flag", "raised": "flag", "level": "string",
    "lift_assist": "string", "finger_position": "string",
    "push_position": "string",
    # A divider's sloped-bottom yes/no choices - kept flags so a browser or
    # API round-trip does not turn them into 0.0 / 1.0 floats.
    "reverse_bottom": "flag", "alternate_bottom": "flag", "minimal_bottom": "flag",
}


def option_value(key: str, value: object) -> object:
    """One option as its declared type, or a float like every other one."""
    kind = NON_NUMERIC_OPTIONS.get(key)
    if kind == "string":
        return str(value)
    if kind == "flag":
        if isinstance(value, str):
            return value.strip().lower() not in {"", "false", "0", "no", "off"}
        return bool(value)
    return float(value)


def is_text(one: Feature) -> bool:
    return one.kind == TEXT_KIND


def text_of(one: Feature) -> str:
    """The lettering a text feature carries, stripped."""
    return str(one.options.get("text", "") or "").strip()


def _oriented_text(label: str, cap_height: float, quarter_turns: int):
    """``label`` at ``cap_height``, turned in 90-degree steps, centred on origin."""
    outline = text_outline(label, cap_height)
    turns = int(quarter_turns) % 4
    if turns:
        outline = affinity.rotate(outline, 90.0 * turns, origin=(0.0, 0.0),
                                  use_radians=False)
    minx, miny, maxx, maxy = outline.bounds
    return affinity.translate(outline, xoff=-(minx + maxx) / 2.0,
                              yoff=-(miny + maxy) / 2.0)


def text_fitted(one: Feature) -> tuple[float, object]:
    """``(cap height, outline centred on the origin)`` fitted into the zone.

    The zone is what the editor drags and resizes, so it is authoritative: a
    blank ``cap_height`` fills it, and a hand-set one is honoured but never
    allowed to overflow it.  That is what makes dragging a corner scale the
    lettering, exactly the way resizing any other interior part scales it.
    """
    label = text_of(one)
    if not label:
        raise ValueError("this text part has no text; type what it should say")
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    probe = _oriented_text(label, TEXT_CAP_HEIGHT_IDEAL, turns)
    bx0, by0, bx1, by1 = probe.bounds
    width, height = bx1 - bx0, by1 - by0
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"'{label}' has no printable outline")
    zone = one.zone
    fits = TEXT_CAP_HEIGHT_IDEAL * min(zone.width / width, zone.depth / height)
    if fits < TEXT_CAP_HEIGHT_FLOOR - 1e-9:
        needed_x = width * TEXT_CAP_HEIGHT_FLOOR / TEXT_CAP_HEIGHT_IDEAL
        needed_y = height * TEXT_CAP_HEIGHT_FLOOR / TEXT_CAP_HEIGHT_IDEAL
        raise ValueError(
            f"'{label}' will not fit its box: at the {TEXT_CAP_HEIGHT_FLOOR:g} mm "
            f"minimum letter height it needs {needed_x:.1f} x {needed_y:.1f} mm "
            f"and the box is {zone.width:.1f} x {zone.depth:.1f} mm. Make it "
            f"bigger, turn it, or use shorter text"
        )
    wanted = one.options.get("cap_height")
    cap = min(float(wanted), fits) if wanted else fits
    cap = max(cap, TEXT_CAP_HEIGHT_FLOOR)
    return cap, _oriented_text(label, cap, turns)


def text_placed_outline(one: Feature):
    """A text feature's real 2D ink, centred in its zone."""
    _cap, outline = text_fitted(one)
    centre_x, centre_y = one.zone.centre
    return affinity.translate(outline, xoff=centre_x, yoff=centre_y)


def text_is_raised(one: Feature) -> bool:
    return bool(one.options.get("raised", False))


def text_depth(one: Feature) -> float:
    depth = one.options.get("depth")
    return TEXT_DEPTH if depth in (None, "") else float(depth)


@defaults(TEXT_KIND)
def text_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    """Resolved numbers the editor shows in its own fields.

    ``cap_height`` reports what the zone currently produces, so the field can
    sit blank and still read ``auto (8.5)`` rather than empty.
    """
    resolved: dict[str, float] = {
        "depth": TEXT_DEPTH,
        "quarter_turns": 0,
        "raised": 0,
        "auto": 0,
    }
    if one.options.get("level") == "rim":
        return resolved
    try:
        resolved["cap_height"] = round(text_fitted(one)[0], 3)
    except ValueError:
        resolved["cap_height"] = TEXT_CAP_HEIGHT_IDEAL
    return resolved


@feature(TEXT_KIND)
def build_text(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """The lettering solid, sunk into (or standing on) the surface at ``base_z``.

    Recessed - the default - it occupies the depth immediately below the floor
    it sits in, so the exporter subtracts it and the finished floor stays flat
    with the letters as an inlay.
    """
    if spec_feature.options.get("level") == "rim":
        return []
    outline = text_placed_outline(spec_feature)
    depth = text_depth(spec_feature)
    raised = text_is_raised(spec_feature)
    if depth <= 0.0:
        raise ValueError("text depth must be positive")
    if not raised and depth > base_z + 1e-9:
        raise ValueError(
            f"sunk text {depth:g} mm deep needs {depth:g} mm of floor beneath it; "
            f"this one has {base_z:.2f} mm. Make it shallower, thicken the base, "
            f"or set it to stand proud instead"
        )
    if raised and base_z + depth > box.z + 1e-9:
        raise ValueError("raised text must stay inside the bin")
    return [text_prism(outline, base_z, depth, raised)]


def _text_footprint(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """The floor the lettering really covers - its ink, not its whole box.

    Text is usually a different shape from the rectangle it was dragged out to,
    so judging neighbours on the ink lets a label sit close beside a holder
    without the empty corners of its box pushing them apart.
    """
    if one.options.get("level") == "rim":
        return None
    outline = text_placed_outline(one)
    bx0, by0, bx1, by1 = outline.bounds
    if bx1 <= bx0 or by1 <= by0:
        return None
    return Zone(bx0, by0, bx1, by1)


def text_min_footprint(
    box: BoxSpec, one: Feature, base_z: float = 0.0
) -> tuple[float, float] | None:
    """The smallest ``(width, depth)`` mm needed to fit the text without squeezing."""
    label = text_of(one)
    if not label:
        return None
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    try:
        probe = _oriented_text(label, TEXT_CAP_HEIGHT_IDEAL, turns)
    except (ValueError, ZeroDivisionError):
        return None
    bx0, by0, bx1, by1 = probe.bounds
    text_w, text_h = bx1 - bx0, by1 - by0
    if text_w <= 0.0 or text_h <= 0.0:
        return None
    wanted = one.options.get("cap_height")
    target_cap = float(wanted) if wanted else TEXT_CAP_HEIGHT_IDEAL
    if turns % 2 == 0:
        cap_by_depth = TEXT_CAP_HEIGHT_IDEAL * (one.zone.depth / text_h)
        effective_cap = min(target_cap, max(TEXT_CAP_HEIGHT_FLOOR, cap_by_depth))
        needed_w = text_w * (effective_cap / TEXT_CAP_HEIGHT_IDEAL)
        needed_d = max(one.zone.depth, text_h * (effective_cap / TEXT_CAP_HEIGHT_IDEAL))
        return (math.ceil(needed_w), math.ceil(needed_d))
    else:
        cap_by_width = TEXT_CAP_HEIGHT_IDEAL * (one.zone.width / text_w)
        effective_cap = min(target_cap, max(TEXT_CAP_HEIGHT_FLOOR, cap_by_width))
        needed_w = max(one.zone.width, text_w * (effective_cap / TEXT_CAP_HEIGHT_IDEAL))
        needed_d = text_h * (effective_cap / TEXT_CAP_HEIGHT_IDEAL)
        return (math.ceil(needed_w), math.ceil(needed_d))


def auto_grow_text_feature(
    one: Feature, box: BoxSpec, mode: str = "fused"
) -> Feature:
    """Auto grow text part footprint if it needs more room and can fit inside the bin."""
    if not is_text(one):
        return one
    size = text_min_footprint(box, one)
    if size is None:
        return one
    bounds = layout_zone(box, mode)
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    if turns % 2 == 0:
        needed_w = size[0]
        max_fit_w = bounds.width
        grow_w = min(needed_w, max_fit_w)
        if grow_w > one.zone.width:
            cx = one.zone.centre[0]
            cx = min(max(cx, bounds.x0 + grow_w / 2.0), bounds.x1 - grow_w / 2.0)
            new_zone = Zone(cx - grow_w / 2.0, one.zone.y0, cx + grow_w / 2.0, one.zone.y1)
            return replace(one, zone=snapped_zone(new_zone, box, mode))
    else:
        needed_d = size[1]
        max_fit_d = bounds.depth
        grow_d = min(needed_d, max_fit_d)
        if grow_d > one.zone.depth:
            cy = one.zone.centre[1]
            cy = min(max(cy, bounds.y0 + grow_d / 2.0), bounds.y1 - grow_d / 2.0)
            new_zone = Zone(one.zone.x0, cy - grow_d / 2.0, one.zone.x1, cy + grow_d / 2.0)
            return replace(one, zone=snapped_zone(new_zone, box, mode))
    return one


# --- putting an insert together ----------------------------------------------


def _feature_reach(box: BoxSpec, one: Feature, base_z: float) -> Zone:
    """How far a feature's own built geometry may legitimately extend.

    For an ordinary feature this is simply its stored zone - the builder is
    never allowed to produce anything bigger than what the editor placed. A
    divider is built from its own ``thickness`` option on the cross axis,
    not from the zone's stored footprint there (see ``build_divider``), so
    the two can disagree - typing a thicker wall than the zone happened to
    be does not, on its own, mean anything is actually wrong. The reach
    widens on the cross axis to whichever is bigger. Two more deliberate
    divider exceptions stack on top (see ``build_divider``): full-span
    reaches past its stored zone along its run axis, all the way to the
    box's true wavy wall, so its reach widens there to the box's own
    physical envelope - the one bound nothing can legitimately cross; a
    leaning divider reaches further still on the cross axis, by however far
    its own lean carries it.
    """
    if one.kind == "nest" and one.contour:
        # Shapely/earcut round-tripping can move a boundary by sub-micron
        # amounts; keep the editor's fitted footprint authoritative.
        epsilon = 0.01
        return Zone(one.zone.x0 - epsilon, one.zone.y0 - epsilon,
                    one.zone.x1 + epsilon, one.zone.y1 + epsilon)
    if one.kind == "pocket":
        epsilon = POCKET_CHAMFER + 0.01
        return Zone(one.zone.x0 - epsilon, one.zone.y0 - epsilon,
                    one.zone.x1 + epsilon, one.zone.y1 + epsilon)
    if is_text(one):
        # Lettering is fitted to fill its zone, so its bounds land exactly on
        # it; leave room for the rounding that puts them there.
        return Zone(one.zone.x0 - TEXT_ZONE_EPSILON, one.zone.y0 - TEXT_ZONE_EPSILON,
                    one.zone.x1 + TEXT_ZONE_EPSILON, one.zone.y1 + TEXT_ZONE_EPSILON)
    if one.kind != "divider":
        return one.zone
    zone = one.zone
    if one.full_span:
        # Reaches the box's true walls on the run axis always, and on the
        # cross axis too once minimal crossbars weld into the bin's side
        # walls (see _divider_support_bottoms).
        zone = Zone(-box.half_x, -box.half_y, box.half_x, box.half_y)
    options = resolved_options(box, one, base_z)
    thickness = options.get("thickness", 0.0)
    angle = options.get("angle", 0.0)
    lean = abs(options["height"] * math.tan(math.radians(angle))) if angle else 0.0
    # The base chamfer comes from _divider_wall, used by every divider except
    # a straight (non-leaning) full-span one, which is built by a separate,
    # simpler clip-and-extrude path with no chamfer (see build_divider).
    chamfer = 0.0 if (one.full_span and angle == 0.0) else DIVIDER_CHAMFER
    # Margin each individual wall may reach past its own centre line. With
    # more than one (see build_divider), every centre sits strictly inside
    # the zone's own cross span, so widening that span by this margin on
    # each side always covers every wall - not the tightest possible bound,
    # but a safe one that does not need each wall's exact position redone
    # here too.
    margin = thickness / 2.0 + lean + chamfer
    if one.along == "x":
        zone = Zone(zone.x0, zone.y0 - margin, zone.x1, zone.y1 + margin)
    else:
        zone = Zone(zone.x0 - margin, zone.y0, zone.x1 + margin, zone.y1)
    return zone


def _cradle_footprint(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """The floor a cradle's troughs really cover - see ``build_cradle``.

    The run axis carries the tool's own length, not the zone's: a shorter tool
    in a longer zone leaves real, usable floor at the ends, wherever
    ``run_offset`` has slid it (or, alternating, between the two extremes the
    ``end_margin`` allows). The cross axis carries the row the count and
    spacing actually build.
    """
    item = one.item
    if item is None:
        return None
    options = resolved_options(box, one, base_z)
    wall = options["rib_thickness"]
    spacing = max(0.0, float(options["spacing"]))
    held, length = item.widest, item.length
    body = held + wall
    pitch = held + wall / 2.0 + spacing
    zone, along = one.zone, one.along
    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width
    count = one.count if one.count is not None else _fit_count(across, pitch, body)
    if count < 1:
        return None
    centre_along, centre_across = zone.centre
    if along != "x":
        centre_along, centre_across = centre_across, centre_along
    if one.alternate_ends and count > 1:
        # Both extremes of the alternating swing, as one span.
        swing = max(0.0, (run - length) / 2.0 - _cradle_end_margin(one) * run)
        run_span, run_centre = length + 2.0 * swing, centre_along
    else:
        slide = _cradle_offset(one) * max(0.0, (run - length) / 2.0)
        run_span, run_centre = length, centre_along + slide
    run_span = min(run, run_span)
    across_span = min(across, (count - 1) * pitch + body)
    if along == "x":
        return Zone(run_centre - run_span / 2.0, centre_across - across_span / 2.0,
                    run_centre + run_span / 2.0, centre_across + across_span / 2.0)
    return Zone(centre_across - across_span / 2.0, run_centre - run_span / 2.0,
                centre_across + across_span / 2.0, run_centre + run_span / 2.0)


def _post_footprint(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """The floor a row of pegs really covers - see ``build_post``. A peg is as
    wide as its diameter however big a zone it was given."""
    options = resolved_options(box, one, base_z)
    diameter, spacing = options["diameter"], options["spacing"]
    zone = one.zone
    available = zone.width if one.along == "x" else zone.depth
    count = (one.count if one.count is not None
             else _fit_count(available, diameter + spacing, diameter))
    if count < 1:
        return None
    used = count * diameter + (count - 1) * spacing
    centre_x, centre_y = zone.centre
    run = min(zone.width if one.along == "x" else zone.depth, used)
    across = min(zone.depth if one.along == "x" else zone.width, diameter)
    if one.along == "x":
        return Zone(centre_x - run / 2.0, centre_y - across / 2.0,
                    centre_x + run / 2.0, centre_y + across / 2.0)
    return Zone(centre_x - across / 2.0, centre_y - run / 2.0,
                centre_x + across / 2.0, centre_y + run / 2.0)


def _divider_footprint(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """The floor a divider's walls really cover - see ``build_divider``.

    Unlike :func:`_feature_reach`, which widens the whole zone by one wall's
    margin because it only needs a safe upper bound, this bounds the walls
    where they actually stand: the fence-post centres, each grown by half a
    thickness plus its lean and base chamfer. The zone's cross axis is
    otherwise open floor, so a two-wall divider drawn across a wide zone no
    longer claims the compartments it merely separates.
    """
    zone = one.zone
    options = resolved_options(box, one, base_z)
    thickness = options.get("thickness", 0.0)
    angle = options.get("angle", 0.0)
    spacing = options["spacing"]
    count = one.count or 1
    if thickness <= 0.0 or spacing <= 0.0 or count < 1:
        return None
    lean = abs(options["height"] * math.tan(math.radians(angle))) if angle else 0.0
    chamfer = 0.0 if (one.full_span and angle == 0.0) else DIVIDER_CHAMFER
    margin = thickness / 2.0 + lean + chamfer
    centres = _divider_cross_centres(zone, one.along, count, spacing)
    low, high = min(centres) - margin, max(centres) + margin
    # A sloped bottom fills the whole zone cross span between the walls, not
    # just the strip the walls stand on, so it does claim those compartments.
    if float(options.get("bottom_angle", 0.0) or 0.0) != 0.0:
        if one.along == "x":
            low, high = min(low, zone.y0), max(high, zone.y1)
        else:
            low, high = min(low, zone.x0), max(high, zone.x1)
    # Full span runs to the box's true wavy wall, past the flat rectangle.
    if one.along == "x":
        x0, x1 = (-box.half_x, box.half_x) if one.full_span else (zone.x0, zone.x1)
        return Zone(x0, low, x1, high)
    y0, y1 = (-box.half_y, box.half_y) if one.full_span else (zone.y0, zone.y1)
    return Zone(low, y0, high, y1)


_FOOTPRINT_BUILDERS = {
    "cradle": _cradle_footprint,
    "post": _post_footprint,
    "divider": _divider_footprint,
    TEXT_KIND: _text_footprint,
}


def feature_min_footprint(
    box: BoxSpec, one: Feature, base_z: float = 0.0,
) -> tuple[float, float] | None:
    """The smallest ``(width, depth)`` mm a feature needs for everything it
    builds - its hole grid, its row of pegs, its bank of slots, its tool.

    ``None`` for kinds with no such natural size (pocket, steps, photo nest,
    divider, text): "fit this part to its contents" means nothing for them.

    Unlike :func:`feature_footprint`, this is never clamped to the current
    zone - it is the size the editor's "fit to contents" button resizes the
    zone *to*, growing it when the zone was drawn too small.
    """
    kind = one.kind

    if kind == "cradle":
        return cradle_min_footprint(one) if one.item is not None else None

    if kind == "bore":
        item = one.item
        if item is None:
            return None
        options = resolved_options(box, one, base_z)
        held = (HEX_BIT_FLATS + HEX_BIT_CLEARANCE
                if _is_hex_bit(item.profile) else item.held(item.widest))
        wall = float(options["wall"])
        pitch = held + wall
        raw_c, raw_r = one.options.get("columns"), one.options.get("rows")
        columns = (max(1, int(round(float(raw_c)))) if raw_c is not None
                   else max(1, _fit_count(one.zone.width, pitch, held + wall)))
        rows = (max(1, int(round(float(raw_r)))) if raw_r is not None
                else max(1, _fit_count(one.zone.depth, pitch, held + wall)))
        angle = float(options.get("angle", 0.0))
        reach = (float(options["depth"]) * math.sin(math.radians(angle))
                 if angle > 0.0 else 0.0)
        width = columns * pitch + (reach if one.along == "x" else 0.0)
        depth = rows * pitch + (reach if one.along == "y" else 0.0)
        return (width, depth)

    if kind == "post":
        options = resolved_options(box, one, base_z)
        diameter, spacing = float(options["diameter"]), float(options["spacing"])
        run = one.zone.width if one.along == "x" else one.zone.depth
        count = (one.count if one.count is not None
                 else max(1, _fit_count(run, diameter + spacing, diameter)))
        used = count * diameter + (count - 1) * spacing
        return (used, diameter) if one.along == "x" else (diameter, used)

    if kind == "slot":
        options = resolved_options(box, one, base_z)
        thickness, wall = float(options["thickness"]), float(options["wall"])
        cos_a = math.cos(math.radians(float(options.get("angle", 20.0))))
        pitch = (thickness + wall) / cos_a
        run = one.zone.width if one.along == "x" else one.zone.depth
        if one.count is not None:
            count = one.count
        else:
            across_now = one.zone.depth if one.along == "x" else one.zone.width
            count = max(1, int((across_now - 2.0 * wall - thickness / cos_a) // pitch) + 1)
        across = (count - 1) * pitch + thickness / cos_a + 2.0 * wall
        return (run, across) if one.along == "x" else (across, run)

    return None


def feature_footprint(box: BoxSpec, one: Feature, base_z: float = 0.0) -> Zone:
    """The floor a feature's built geometry actually covers.

    A zone is the rectangle the editor gives a support to live in - what you
    drag and resize - and for a bore, pocket or photo nest the built part fills
    it exactly. A cradle, post or divider deliberately fills less: the trough
    is only as long as its tool, a peg only as wide as its diameter, a wall
    only as thick as its thickness. Fused to the bin floor, the remainder is
    ordinary open floor another support can stand on, so neighbour spacing is
    judged on this rather than on the zone (see :func:`check_layout`).

    Never raises: anything it cannot work out - a cradle with no item yet,
    options that will not resolve - falls back to the zone, which is what the
    caller would have used anyway.
    """
    build = _FOOTPRINT_BUILDERS.get(one.kind)
    if build is None:
        return one.zone
    try:
        return build(box, one, base_z) or one.zone
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        return one.zone


def occupied_zones(
    box: BoxSpec, features: Iterable[Feature], base_z: float = 0.0,
    mode: str = "fused",
) -> list[Zone]:
    """What each feature keeps other features (and bin customizations) out of.

    Only a fused layout judges this on the real footprint. A removable insert
    prints on a base plate spanning the whole bin floor, so its supports are
    one interchangeable tile and each keeps its whole zone; cartridge mode
    needs whole 8 mm cells for the same reason.
    """
    return [
        feature_footprint(box, one, base_z) if mode == "fused" else one.zone
        for one in features
    ]


def check_layout(
    box: BoxSpec, features: Iterable[Feature], bounds: Zone | None = None,
    base_z: float = 0.0, mode: str = "fused",
) -> None:
    """Catch the mistakes that produce quietly wrong parts."""
    features = list(features)
    whole = bounds or Zone.whole(box)
    for one in features:
        if one.kind not in FEATURE_BUILDERS:
            raise ValueError(
                f"unknown holder {one.kind!r}; have "
                f"{', '.join(sorted(FEATURE_BUILDERS))}"
            )
        if (one.zone.x0 < whole.x0 - 1e-6 or one.zone.x1 > whole.x1 + 1e-6
                or one.zone.y0 < whole.y0 - 1e-6 or one.zone.y1 > whole.y1 + 1e-6):
            raise ValueError(
                f"a {one.kind} reaches outside the bin: its zone is "
                f"{one.zone.width:.1f} x {one.zone.depth:.1f} mm at "
                f"({one.zone.x0:.1f}, {one.zone.y0:.1f}) but the bin gives "
                f"{whole.width:.1f} x {whole.depth:.1f} mm"
            )
    # Zones may legitimately overlap once the parts inside them do not, so
    # neighbours are judged on the floor each one actually covers.
    occupied = occupied_zones(box, features, base_z, mode)
    for index, one in enumerate(features):
        for offset, other in enumerate(features[index + 1:], index + 1):
            if occupied[index].overlaps(occupied[offset], MIN_FEATURE_GAP):
                raise ValueError(
                    f"a {one.kind} and a {other.kind} overlap; leave at least "
                    f"{MIN_FEATURE_GAP:g} mm between features"
                )


def build_features(
    box: BoxSpec, features: Iterable[Feature], base_z: float,
    bounds: Zone | None = None, mode: str = "fused",
    include_text: bool = False,
) -> list[trimesh.Trimesh]:
    """Every holder's solids, ready to be added to the body.

    Text is built too - so a bad one reports its error alongside every other
    feature's - but left out of the returned solids unless ``include_text`` is
    set, because a recessed text has to be subtracted from the body rather
    than added to it. The exporter collects it through :func:`build_texts`;
    the preview asks for it here so it can draw it in place.
    """
    features = list(features)
    check_layout(box, features, bounds, base_z, mode)
    solids: list[trimesh.Trimesh] = []
    for one in features:
        made = FEATURE_BUILDERS[one.kind](box, one, base_z)
        reach = _feature_reach(box, one, base_z)
        for solid in made:
            if (
                solid.bounds[0][0] < reach.x0 - 1e-5
                or solid.bounds[1][0] > reach.x1 + 1e-5
                or solid.bounds[0][1] < reach.y0 - 1e-5
                or solid.bounds[1][1] > reach.y1 + 1e-5
            ):
                raise ValueError(
                    f"a {one.kind} exceeds its layout zone; reduce its size "
                    "or thickness option"
                )
        whole = Zone.whole(box)
        touches_wall = (
            one.zone.x0 <= whole.x0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.x1 >= whole.x1 - CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y0 <= whole.y0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y1 >= whole.y1 - CONNECTOR_EDGE_KEEP_OUT
        )
        if touches_wall and not (one.kind == "nest" and one.contour) and any(
            solid.bounds[1][2] > connector_keep_out(box) + 1e-6 for solid in made
        ):
            raise ValueError(
                f"a {one.kind} touching the wall must stay below "
                f"{connector_keep_out(box):.1f} mm so a connector can seat"
            )
        if is_text(one) and not include_text:
            continue
        solids.extend(made)
    return solids


def build_texts(
    box: BoxSpec, features: Iterable[Feature], base_z: float,
    limit: Polygon | None = None,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """``(what it says, its solid, whether it stands proud)`` for each text part.

    The caller subtracts every recessed solid from the body to cut its pocket,
    leaves the raised ones alone, and writes all of them as their own objects.

    ``limit`` is the surface the lettering has to stay on - a removable
    insert's plate is pulled in from the wall, so text that would hang over
    its edge is refused here rather than quietly clipped mid-letter the way
    trimming a holder to the same outline safely can be.
    """
    made: list[tuple[str, trimesh.Trimesh, bool]] = []
    for one in features:
        if not is_text(one) or one.options.get("level") == "rim":
            continue
        if limit is not None and not limit.covers(text_placed_outline(one)):
            raise ValueError(
                f"the text '{text_of(one)}' hangs over the edge of the insert "
                "plate; move it further from the wall"
            )
        made.append((text_of(one), build_text(box, one, base_z)[0],
                     text_is_raised(one)))
    return made


def resolve_text_features(
    box: BoxSpec,
    features: Iterable[Feature],
    reserved: Iterable[Polygon] = (),
    base_z: float = 0.0,
    mode: str = "fused",
) -> tuple[Feature, ...]:
    """Give every ``auto`` text part the best spot left on the floor.

    This is the "blank config just works" case the plain floor label always
    had: stay centred if you can, otherwise move beside whatever is in the
    way, then turn, then shrink. Everything else keeps the zone it was
    dragged to. Never raises - a text that cannot be placed keeps the zone it
    already had, so the ordinary validation reports it in the usual way.
    """
    features = tuple(features)
    auto = [
        index for index, one in enumerate(features)
        if is_text(one) and one.options.get("auto") and one.options.get("level") != "rim"
    ]
    if not auto:
        return features
    resolved = list(features)
    # Each auto text has to dodge the others too, so they are placed one at a
    # time and every one already placed becomes an obstacle for the next.
    obstacles = [polygon for polygon in reserved if not polygon.is_empty]
    obstacles += [
        feature_footprint(box, one, base_z).polygon
        for index, one in enumerate(features)
        if index not in auto
    ]
    for index in auto:
        one = resolved[index]
        label = text_of(one)
        if not label:
            continue
        try:
            placement = label_placement(box, label, obstacles)
            outline = _oriented_text(label, placement.cap_height,
                                     placement.quarter_turns)
            bx0, by0, bx1, by1 = outline.bounds
            zone = Zone(bx0 + placement.x, by0 + placement.y,
                        bx1 + placement.x, by1 + placement.y)
        except (ValueError, ZeroDivisionError):
            obstacles.append(one.zone.polygon)
            continue
        options = dict(one.options)
        options["quarter_turns"] = placement.quarter_turns
        # The zone is now exactly the ink, so re-fitting into it lands back on
        # the cap height the search chose; leave the field free to say so.
        options.pop("cap_height", None)
        if mode == "cartridge":
            # A cartridge layout only accepts whole 8 mm cells and the ink
            # never lands on one, so grow the zone *outward* to the cells
            # around it - snapping to the nearest would cut the lettering off.
            # Pin the height the search chose so the bigger box does not
            # quietly enlarge the lettering to fill it either.
            cells = cartridge_zone(box)
            low_x = cells.x0 + math.floor((zone.x0 - cells.x0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            low_y = cells.y0 + math.floor((zone.y0 - cells.y0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            high_x = cells.x0 + math.ceil((zone.x1 - cells.x0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            high_y = cells.y0 + math.ceil((zone.y1 - cells.y0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            if (low_x < cells.x0 - 1e-9 or low_y < cells.y0 - 1e-9
                    or high_x > cells.x1 + 1e-9 or high_y > cells.y1 + 1e-9):
                obstacles.append(one.zone.polygon)
                continue
            zone = Zone(low_x, low_y, high_x, high_y)
            options["cap_height"] = placement.cap_height
        resolved[index] = replace(one, zone=zone, options=options)
        obstacles.append(zone.polygon)
    return tuple(resolved)


def insert_footprint(box: BoxSpec, mode: str = "separate") -> Polygon:
    """The floor outline of a standalone insert.

    A removable insert follows the box's real cavity, including its waves, and
    is offset inward by ``INSERT_CLEARANCE`` so it can still slide in and out.
    A box with a flat lower wall band uses that lower profile because the plate
    sits inside the band.  Cartridge inserts retain their reusable rectangular
    cell footprint.
    """
    if mode == "separate":
        cavity = (
            flat_cavity_polygon(box)
            if box.flat_inside > 0.0
            else wavy_cavity_polygon(box)
        )
        footprint = cavity.buffer(-INSERT_CLEARANCE)
        if not isinstance(footprint, Polygon) or footprint.is_empty:
            raise ValueError("this bin is too small for a removable insert")
        return footprint
    bounds = layout_zone(box, mode)
    return _rounded(
        shapely_box(
            bounds.x0 + INSERT_CLEARANCE, bounds.y0 + INSERT_CLEARANCE,
            bounds.x1 - INSERT_CLEARANCE, bounds.y1 - INSERT_CLEARANCE,
        ),
        1.0,
    )


def make_insert_plate(box: BoxSpec, mode: str = "separate") -> trimesh.Trimesh:
    """The bare base plate of a standalone insert, sitting on z = 0."""
    return _extrude_polygon(insert_footprint(box, mode), BASE_PLATE)


def make_fitted_insert(
    box: BoxSpec, features: Iterable[Feature]
) -> trimesh.Trimesh:
    """A standalone insert that drops into this bin.

    It gets its own base plate and is pulled in by ``INSERT_CLEARANCE`` all
    round so it actually goes in, which is the cost of being able to lift it
    out and swap it.
    """
    footprint = insert_footprint(box, "separate")
    plate = _extrude_polygon(footprint, BASE_PLATE)
    # Validate and size holders at their installed height, then lower them by
    # the bin floor thickness so the removable insert still exports on z=0.
    parts = build_features(
        box, features, BASE_PLATE + box.base_thickness, mode="separate"
    )
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.base_thickness))
    body = union([plate] + parts) if parts else plate
    # A holder is built to its zone, which may run right out to the usable
    # rectangle - fine when fused to the box, but a standalone insert has to
    # clear the wall to go in at all. Trimming the assembled solid to the
    # plate's own footprint keeps that true for every holder, including any
    # added later.
    limit = _extrude_polygon(footprint, box.z * 2.0)
    return intersection([body, limit])


def make_cartridge_insert(
    box: BoxSpec, features: Iterable[Feature]
) -> trimesh.Trimesh:
    """Standalone insert on the optional centred 8 mm cartridge footprint."""
    bounds = cartridge_zone(box)
    footprint = insert_footprint(box, "cartridge")
    plate = _extrude_polygon(footprint, BASE_PLATE)
    parts = build_features(
        box, features, BASE_PLATE + box.base_thickness, bounds, "cartridge"
    )
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.base_thickness))
    body = union([plate] + parts) if parts else plate
    limit = _extrude_polygon(footprint, box.z * 2.0)
    return intersection([body, limit])


def make_fused_box(
    box: BoxSpec, features: Iterable[Feature], box_mesh: trimesh.Trimesh
) -> trimesh.Trimesh:
    """The bin with its holders grown straight out of the floor."""
    parts = build_features(box, features, box.base_thickness)
    if not parts:
        return box_mesh
    return union([box_mesh, *parts])


def apply_texts(
    body: trimesh.Trimesh,
    texts: Iterable[tuple[str, trimesh.Trimesh, bool]],
) -> trimesh.Trimesh:
    """Cut every recessed text's pocket out of ``body``.

    A raised text stands on the surface and takes nothing away, so it is left
    alone here and simply written as its own object beside the body.
    """
    sunk = [mesh for _label, mesh, raised in texts if not raised]
    if not sunk:
        return body
    pocketed = difference([body, union(sunk) if len(sunk) > 1 else sunk[0]])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed


def insert_report(name: str, features: Iterable[Feature], mesh: trimesh.Trimesh) -> dict:
    features = list(features)
    return {
        "name": name,
        "features": len(features),
        "kinds": sorted({f.kind for f in features}),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "watertight": bool(mesh.is_watertight),
    }


# --- a starter library --------------------------------------------------------
#
# Measured nominal sizes. Extend freely; nothing here is special.

LIBRARY: dict[str, Item] = {
    "pencil": Item.simple("Pencil", 175.0, 7.5),
    "sharpie": Item.simple("Sharpie", 140.0, 14.0),
    "glue_stick": Item.simple("Glue stick", 100.0, 11.0),
    "hex_driver": Item(
        "Hex driver", (Segment(50.0, 6.0), Segment(30.0, 18.0))
    ),
    "screwdriver": Item(
        "Screwdriver", (Segment(90.0, 5.0), Segment(80.0, 22.0))
    ),
    "deburr_tool": Item("Deburring tool", (Segment(40.0, 6.0), Segment(60.0, 12.0))),
    "tweezers": Item.simple("Tweezers", 120.0, 8.0),
    "nozzle": Item.simple("Printer nozzle", 13.0, 6.0),
}
