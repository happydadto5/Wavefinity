"""Cradle feature defaults and geometry."""
from __future__ import annotations
import math
import trimesh
from organizer_engine import BoxSpec, difference, union
from ._core import Feature, _fit_count, _need_item
from ._registry import defaults, feature, resolved_options
RIB_THICKNESS = 1.6
CRADLE_RIB_FRACTION = 0.25
CRADLE_RIB_MAX = 6.0
CRADLE_FLOOR_GAP = 2.0
CRADLE_MIN_FLOOR_GAP = 0.4
CRADLE_ALTERNATE_END_MARGIN = 0.10
CRADLE_ALTERNATE_END_MARGIN_MAX = 0.45
CRADLE_RUN_OFFSET_MAX = 1.0
MAX_NOTCH_FRACTION = 0.5

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
    # The trough always begins 2 mm above the base. This is deliberately not
    # a user setting, including for older saved designs that stored a value.
    floor_gap = CRADLE_FLOOR_GAP
    if not math.isfinite(spacing) or spacing < 0.0:
        raise ValueError("cradle spacing must be zero or greater")

    length = item.length
    # A cradle is an open half-circle the tool simply drops into, so it takes
    # the tool at its true diameter - no fit slack, nothing to tune.
    held = item.widest
    radius = held / 2.0
    axis_z = base_z + floor_gap + held / 2.0
    trough_height = axis_z - base_z
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
    body = item.widest + wall
    pitch = item.widest + wall / 2.0 + spacing
    if one.count is None:
        across_now = one.zone.depth if one.along == "x" else one.zone.width
        count = max(1, _fit_count(across_now, pitch, body))
    else:
        count = max(1, int(round(one.count)))
    length = item.length
    alternating = bool(one.alternate_ends) and count > 1
    run = math.ceil(
        length / (1.0 - 2.0 * _cradle_end_margin(one))
        if alternating else length
    )
    across = math.ceil((count - 1) * pitch + body)
    return (float(run), float(across)) if one.along == "x" else (float(across), float(run))
