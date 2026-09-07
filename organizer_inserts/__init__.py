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




from ._post import build_post, post_defaults
from ._cradle import CRADLE_ALTERNATE_END_MARGIN, CRADLE_ALTERNATE_END_MARGIN_MAX, CRADLE_FLOOR_GAP, CRADLE_MIN_FLOOR_GAP, CRADLE_RIB_FRACTION, CRADLE_RIB_MAX, CRADLE_RUN_OFFSET_MAX, MAX_NOTCH_FRACTION, RIB_THICKNESS, _cradle_end_margin, _cradle_offset, _cradle_rib_thickness, _cradle_wall, build_cradle, cradle_defaults, cradle_min_footprint
from ._divider import BOTTOM_CROSSBAR_CHAMFER, BOTTOM_CROSSBAR_THICKNESS, BOTTOM_EMBED, BOTTOM_SLOPE_MAX, DIVIDER_CHAMFER, MAX_DIVIDER_ANGLE, MIN_WEDGE_EDGE, _divider_cross_centres, _divider_support_bottoms, _divider_wall, build_divider, divider_defaults
from ._nest import NEST_ASSISTS, NEST_CHAMFER, NEST_FINGER_POSITIONS, NEST_FINGER_WIDTH, NEST_PUSH_AREA, NEST_PUSH_DEPTH, NEST_PUSH_POSITIONS, NEST_TOP_ROUND, build_nest, fitted_nest_feature, nest_contour_polygon, nest_defaults, nest_required_zone, nest_smoothed_contour
from ._pocket import POCKET_CHAMFER, POCKET_FLOOR, build_pocket, pocket_defaults
from ._bore import BORE_MAX_TILT, BORE_MOUTH_CHAMFER, BORE_TILTED_WALL, BORE_WALL, HEX_BIT_CLEARANCE, HEX_BIT_FLATS, HEX_BIT_HOLD, HEX_BIT_LENGTH, HEX_BIT_LONG_LENGTH, HEX_BIT_SHORT_LENGTH, _is_hex_bit, build_bore, bore_defaults
from ._scoop import build_scoop, scoop_defaults, scoop_zone
from ._slot import build_slot, slot_defaults
from ._text import NON_NUMERIC_OPTIONS, TEXT_KIND, TEXT_ZONE_EPSILON, _oriented_text, _text_footprint, auto_grow_text_feature, build_text, is_text, option_value, text_defaults, text_depth, text_fitted, text_is_raised, text_of, text_placed_outline
from ._steps import build_steps, steps_defaults




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
