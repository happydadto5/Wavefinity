"""Cross-feature footprint dispatch and layout validation."""

from __future__ import annotations

import math
from typing import Iterable

from dataclasses import replace

from organizer_engine import (
    GRID_PITCH,
    MAX_BOX_SIZE,
    MIN_BOX_SIZE,
    WAVE_AMPLITUDE,
    BoxSpec,
    flat_cavity_polygon,
    wavy_cavity_polygon,
    wall_depth_for,
)

from ._bore import (
    HEX_BIT_CLEARANCE,
    HEX_BIT_FLATS,
    WALL_HUG_FLAG,
    WALL_JOIN_FLAG,
    WALL_ONLY_FOOT,
    _is_hex_bit,
    bore_envelope_zone,
    bore_tool_clearance_zone,
    bore_xy_size_mode,
    is_walls_only,
    is_wavy_style,
    normalize_bore_style,
)
from ._core import MIN_FEATURE_GAP, Feature, Zone, _fit_count
from ._cradle import _cradle_end_margin, _cradle_offset, cradle_min_footprint
from ._divider import DIVIDER_CHAMFER, _divider_cross_centres, divider_grid_counts
from ._pocket import POCKET_CHAMFER
from ._registry import FEATURE_BUILDERS, resolved_options
from ._text import TEXT_KIND, TEXT_ZONE_EPSILON, _text_footprint, is_text


def _bore_style(one: Feature) -> str:
    return normalize_bore_style(one.options.get("bore_style"), one.options.get("wall_style"))


def _wall_only_physical_zone(box: BoxSpec, one: Feature, base_z: float) -> Zone:
    """The Wall Only footprint, foot included, counted exactly once - taken from
    the shared Bore envelope so old shell-sized and new foot-sized zones agree."""
    from ._bore import bore_envelope_zone
    physical = bore_envelope_zone(box, one, base_z)
    if physical is not None:
        return physical
    return Zone(one.zone.x0 - WALL_ONLY_FOOT, one.zone.y0 - WALL_ONLY_FOOT,
                one.zone.x1 + WALL_ONLY_FOOT, one.zone.y1 + WALL_ONLY_FOOT)


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
    if one.kind == "bore" and one.options.get(WALL_JOIN_FLAG):
        # A Bore that may join the bin wall blends into it through the wall's
        # wavy inner face - at most this far past its own zone.
        reach = box.wall_depth + 2.0 * WAVE_AMPLITUDE
        if one.options.get(WALL_HUG_FLAG):
            # A Walls Only Bore whose bin is sized around it also bridges the
            # (under one grid step) gap to the wall, so it may reach the wall.
            whole = Zone.whole(box)
            return Zone(whole.x0 - reach, whole.y0 - reach, whole.x1 + reach, whole.y1 + reach)
        return Zone(one.zone.x0 - reach, one.zone.y0 - reach,
                    one.zone.x1 + reach, one.zone.y1 + reach)
    if one.kind == "bore" and is_walls_only(_bore_style(one)):
        return _wall_only_physical_zone(box, one, base_z)
    if one.kind != "divider":
        return one.zone
    zone = one.zone
    if one.full_span:
        # Reach is bounded by the actual inward cavity, whose wave crests can
        # extend past the nominal half-size with very thin custom walls.
        cavity_bounds = [wavy_cavity_polygon(box).bounds]
        if box.flat_inside > 0.0:
            cavity_bounds.append(flat_cavity_polygon(box).bounds)
        zone = Zone(
            min(bounds[0] for bounds in cavity_bounds),
            min(bounds[1] for bounds in cavity_bounds),
            max(bounds[2] for bounds in cavity_bounds),
            max(bounds[3] for bounds in cavity_bounds),
        )
    options = resolved_options(box, one, base_z)
    thickness = options.get("thickness", 0.0)
    angle = options.get("angle", 0.0)
    lean = abs(options["height"] * math.tan(math.radians(angle))) if angle else 0.0
    chamfer = DIVIDER_CHAMFER
    # Margin each individual wall may reach past its own centre line. With
    # more than one (see build_divider), every centre sits strictly inside
    # the zone's own cross span, so widening that span by this margin on
    # each side always covers every wall - not the tightest possible bound,
    # but a safe one that does not need each wall's exact position redone
    # here too.
    wavy = options.get("wall_style") == "wavy"
    margin = (wall_depth_for(thickness) if wavy else thickness) / 2.0 + lean + chamfer
    if wavy:
        margin += WAVE_AMPLITUDE
    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        # A grid divider has walls on both axes, so it reaches past its zone
        # on both.
        zone = Zone(zone.x0 - margin, zone.y0 - margin,
                    zone.x1 + margin, zone.y1 + margin)
    elif one.along == "x":
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
    wavy = options.get("wall_style") == "wavy"
    margin = (wall_depth_for(thickness) if wavy else thickness) / 2.0 + lean + DIVIDER_CHAMFER
    if wavy:
        margin += WAVE_AMPLITUDE
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
        from ._bore import bore_direction, bore_minimum_pitches, wall_only_envelope
        style = normalize_bore_style(options.get("bore_style"))
        if style != "base_straight":
            # Both Walls Only styles and Base - Wavy Walls stand upright and are
            # sized by the wavy/straight sleeves' outer envelope.
            env = wall_only_envelope(
                item.profile, held, wall,
                "wavy" if is_wavy_style(style) else "straight",
                foot=is_walls_only(style))
            raw_c, raw_r = one.options.get("columns"), one.options.get("rows")
            columns = max(1, int(round(float(raw_c)))) if raw_c is not None else 1
            rows = max(1, int(round(float(raw_r)))) if raw_r is not None else 1
            return (env["span_x"] + (columns - 1) * env["pitch_x"],
                    env["span_y"] + (rows - 1) * env["pitch_y"])
        angle = float(options.get("angle", 0.0))
        lean_axis, _ = bore_direction(one)
        pitch_x, pitch_y = bore_minimum_pitches(item.profile, held, wall, angle, lean_axis)
        reach = (float(options["depth"]) * math.sin(math.radians(angle))
                 if angle > 0.0 else 0.0)
        raw_c, raw_r = one.options.get("columns"), one.options.get("rows")
        columns = max(1, int(round(float(raw_c)))) if raw_c is not None else 1
        rows = max(1, int(round(float(raw_r)))) if raw_r is not None else 1
        width = columns * pitch_x + (reach if lean_axis == "x" else 0.0)
        depth = rows * pitch_y + (reach if lean_axis == "y" else 0.0)
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
        wave = WAVE_AMPLITUDE if options.get("wall_style") == "wavy" else 0.0
        run = one.zone.width if one.along == "x" else one.zone.depth
        if one.count is not None:
            count = one.count
        else:
            across_now = one.zone.depth if one.along == "x" else one.zone.width
            count = max(1, int((across_now - 2.0 * (wall + wave) - thickness / cos_a) // pitch) + 1)
        across = (count - 1) * pitch + thickness / cos_a + 2.0 * (wall + wave)
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
    if one.kind == "bore" and is_walls_only(_bore_style(one)):
        return _wall_only_physical_zone(box, one, base_z)
    build = _FOOTPRINT_BUILDERS.get(one.kind)
    if build is None:
        return one.zone
    try:
        return build(box, one, base_z) or one.zone
    except Exception:
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
        # A Walls Only Bore whose bin is sized around it is judged on its real
        # outer envelope: its zone is that envelope rounded up to the editor
        # grid, and may overhang by less.
        judged = one.zone
        if (mode == "fused" and one.kind == "bore"
                and is_walls_only(_bore_style(one))
                and bore_xy_size_mode(one.options, _bore_style(one)) == "bin_to_bore"):
            judged = bore_envelope_zone(box, one, base_z) or one.zone
        if (judged.x0 < whole.x0 - 1e-6 or judged.x1 > whole.x1 + 1e-6
                or judged.y0 < whole.y0 - 1e-6 or judged.y1 > whole.y1 + 1e-6):
            raise ValueError(
                f"a {one.kind} reaches outside the bin: its zone is "
                f"{one.zone.width:.1f} x {one.zone.depth:.1f} mm at "
                f"({one.zone.x0:.1f}, {one.zone.y0:.1f}) but the bin gives "
                f"{whole.width:.1f} x {whole.depth:.1f} mm"
            )
        # A bore block may fit while the cylinder it holds intersects a side
        # wall above it. Project the cylinder's axis to infinity; only the
        # mouth-to-rim section can meet the finite-height bin wall.
        tool_path = bore_tool_clearance_zone(box, one, base_z) if one.kind == "bore" else None
        if tool_path is not None and (
            tool_path.x0 < whole.x0 - 1e-6 or tool_path.x1 > whole.x1 + 1e-6
            or tool_path.y0 < whole.y0 - 1e-6 or tool_path.y1 > whole.y1 + 1e-6
        ):
            raise ValueError(
                "an angled bore's tool reaches the side of the bin; "
                "grow the bin or reduce its angle"
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


def bore_bin_minimum(
    box: BoxSpec, features: Iterable[Feature], base_z: float = 0.0,
    mode: str = "fused",
) -> tuple[float, float] | None:
    """Smallest legal bin ``(x, y)`` whose usable floor holds every Bore that
    sizes the bin around itself (Auto size bin to bore).

    Each such Bore is measured by its true physical footprint (every row and
    column, wave and foot included), kept exactly where it was placed, and the
    bin - stepping on the normal 8 mm grid, exactly like any bin size - is the
    smallest whose usable inside contains it. ``None`` when no Bore sizes the
    bin (none present, or a removable-insert layout). The browser uses this
    cheap answer to decide when the (exact) fit search needs to run.
    """
    if mode != "fused":
        return None
    need_x = need_y = 0.0
    found = False
    for one in features:
        if one.kind != "bore" or one.item is None:
            continue
        style = _bore_style(one)
        if bore_xy_size_mode(one.options, style) != "bin_to_bore":
            continue
        try:
            size = feature_min_footprint(box, one, base_z)
        except (ValueError, KeyError, TypeError):
            size = None
        if size is None:
            continue
        if not is_walls_only(style):
            # A Base is its own zone (which the browser holds at the minimum), so
            # the bin must hold the zone, not just the bare minimum.
            size = (max(size[0], one.zone.width), max(size[1], one.zone.depth))
        found = True
        cx, cy = one.zone.centre
        if is_walls_only(style):
            cx = cy = 0.0        # a bin-sized Walls Only Bore is centred in the bin
        need_x = max(need_x, 2.0 * (abs(cx) + size[0] / 2.0))
        need_y = max(need_y, 2.0 * (abs(cy) + size[1] / 2.0))
    if not found:
        return None

    def smallest(axis: str, need: float) -> float | None:
        size = MIN_BOX_SIZE
        while size <= MAX_BOX_SIZE + 1e-9:
            try:
                trial = replace(box, **{axis: float(size)})
            except ValueError:
                size += GRID_PITCH
                continue
            inside = trial.usable_inside[0 if axis == "x" else 1]
            if inside >= need - 1e-6:
                return float(size)
            size += GRID_PITCH
        return None

    x, y = smallest("x", need_x), smallest("y", need_y)
    if x is None or y is None:
        raise ValueError(
            "a Bore needs a bin larger than Wavefinity's maximum "
            f"{MAX_BOX_SIZE:g} mm; use fewer or smaller holes"
        )
    return x, y
