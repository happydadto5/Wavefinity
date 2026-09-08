"""Divider feature defaults and geometry."""
from __future__ import annotations
import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from organizer_engine import (
    BoxSpec, WAVE_AMPLITUDE, _extrude_polygon, _extrude_xz_profile,
    _extrude_yz_profile, _rounded, flat_cavity_polygon, intersection,
    text_outline, text_prism, union, wavy_cavity_polygon,
)
from ._core import Feature, Zone, connector_keep_out
from ._registry import defaults, feature, resolved_options
MAX_DIVIDER_ANGLE = 45.0
MIN_WEDGE_EDGE = 0.4
DIVIDER_CHAMFER = 1.0
BOTTOM_SLOPE_MAX = 75.0
BOTTOM_EMBED = 0.4
BOTTOM_CROSSBAR_THICKNESS = 2.4
BOTTOM_CROSSBAR_CHAMFER = 1.0
RIB_THICKNESS = 1.6
DIVISION_TEXT_DEPTH = 0.6
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
        "slope_base": 0,
        "reverse_bottom": 0,
        "alternate_bottom": 0,
        "minimal_bottom": 0,
        "bottom_supports": 3,
        "label_divisions": 0,
        "division_level": "base",
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
    div_texts = divider_division_texts(box, spec_feature, base_z)
    for _text_label, text_solid, _raised in div_texts:
        solids.append(text_solid)
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


def divider_division_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """(label, text_solid, raised) for each division label on a divider."""
    options = spec_feature.options or {}
    if not _option_flag(options.get("label_divisions")):
        return []
    raw_labels = options.get("division_labels")
    if not raw_labels:
        return []
    if isinstance(raw_labels, str):
        import json
        try:
            labels = json.loads(raw_labels)
        except Exception:
            labels = [s.strip() for s in raw_labels.split(",") if s.strip()]
    elif isinstance(raw_labels, (list, tuple)):
        labels = list(raw_labels)
    else:
        return []

    zone = spec_feature.zone
    along = spec_feature.along
    count = spec_feature.count or 1
    thickness = float(options.get("thickness", RIB_THICKNESS) or RIB_THICKNESS)
    height = float(options.get("height", connector_keep_out(box) - base_z) or (connector_keep_out(box) - base_z))
    spacing = float(options.get("spacing", 0.0) or 0.0)
    if spacing <= 0.0:
        span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
        spacing = span / (count + 1)

    centres = _divider_cross_centres(zone, along, count, spacing)
    slots = _bottom_slot_bounds(zone, along, centres)
    level = str(options.get("division_level", "base")).strip().lower()
    # A rim label rides at the divider top, which already sits right at the
    # connector keep-out height. Standing it proud there makes it poke past
    # that line and foul a connector seating against a wall-touching divider,
    # so drop a rim label by its own depth and sit its top flush with the
    # divider crest instead.
    z = (base_z + height - DIVISION_TEXT_DEPTH) if level == "rim" else base_z

    results = []
    for idx, (slot_low, slot_high) in enumerate(slots):
        if idx >= len(labels):
            break
        text = str(labels[idx] or "").strip()
        if not text:
            continue
        inner_low = slot_low + (0.0 if idx == 0 else thickness / 2.0)
        inner_high = slot_high - (0.0 if idx == len(slots) - 1 else thickness / 2.0)
        slot_across = max(1.0, inner_high - inner_low)
        slot_run = max(1.0, (zone.x1 - zone.x0) if along == "x" else (zone.y1 - zone.y0))

        try:
            probe = text_outline(text, 10.0)
        except Exception:
            continue
        bx0, by0, bx1, by1 = probe.bounds
        pw, ph = bx1 - bx0, by1 - by0
        if pw <= 0 or ph <= 0:
            continue
        avail_run = max(0.5, slot_run - 2.0)
        avail_across = max(0.5, slot_across - 1.0)
        cap_by_across = avail_across
        cap_by_run = avail_run / (pw / 10.0)
        cap = max(2.5, min(cap_by_across, cap_by_run))

        try:
            outline = text_outline(text, cap)
        except Exception:
            continue

        if along == "y":
            outline = affinity.rotate(outline, 90.0, origin=(0.0, 0.0), use_radians=False)

        cx = (zone.x0 + zone.x1) / 2.0 if along == "x" else (inner_low + inner_high) / 2.0
        cy = (inner_low + inner_high) / 2.0 if along == "x" else (zone.y0 + zone.y1) / 2.0
        outline = affinity.translate(outline, xoff=cx, yoff=cy)

        try:
            solid = text_prism(outline, z, depth=DIVISION_TEXT_DEPTH, raised=True)
            results.append((text, solid, True))
        except Exception:
            continue

    return results


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
