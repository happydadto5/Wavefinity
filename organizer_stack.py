"""Stackable bins - a snap-in lid, or bins that snap straight into each other.

Two same-mode interfaces:

``lid``     the bin is closed by its own printed lid.  The lid plugs into the
            bin mouth and snaps into a groove just under the rim; its top face
            is recessed, and that recess is the seat the next bin's stepped
            base drops into.
``direct``  no lid at all - the next bin's stepped base plugs straight into
            this bin's mouth and snaps into the same groove.

Both modes step the bottom of the bin inward, but their 1 mm and 3 mm feet are
not interchangeable.  Lid bins stack on lid bins and direct bins stack on
direct bins.  Direct stacking keeps its segmented mouth snap.  Lid retention
uses separate, lighter lock-bump-style points near the rim.

The height the user types is the *stack module height* - the distance between
the seating datums of consecutive bins.  The interlocking foot extends the
detached part's physical envelope by its engagement depth, so a 50 mm module
adds exactly 50 mm to a stack while honestly reporting a taller detached part.
In ``lid`` mode the lid contribution remains inside that module height.
"""

from __future__ import annotations

import math
from dataclasses import replace

import trimesh
from shapely.geometry import Polygon, box as shapely_box

from organizer_engine import (
    BoxSpec,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_WALL,
    LOCK_RUN,
    MIN_HEIGHT_ABOVE_BASE,
    StackSpec,
    TEXT_DEPTH,
    _lock_profile,
    direct_stack_enabled,
    lid_enabled,
    lid_has_handle,
    lid_spec,
    lid_stackable,
    text_outline,
    text_prism,
    vertical_stack_enabled,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import (
    _align_ring,
    _extrude_polygon,
    _loft_cavity,
    _resampled_ring,
    difference,
    intersection,
    union,
)

# --------------------------------------------------------------------------- #
# tuning - conservative first-print values
# --------------------------------------------------------------------------- #
# The plate has to stay thicker than the seat cut into it, or the recess floor
# lands exactly on the plug's top face and the lid unions as two loose pieces
# instead of one - and the bin above would be standing on nothing.
STACK_LID_SKIN = 2.0      # minimum lid rise above the rim
STACK_SEAT_DEPTH = 1.0    # lid mode: base step height == lid top recess depth
STACK_PLUG_DEPTH = 3.0    # how far a plug reaches into the mouth it snaps into
# The click itself: how far the bead stands past the mouth face it has to
# squeeze through.  Derive the bead from this rather than the other way round -
# sizing the bead off the groove left only 0.1 mm of interference, which is a
# detent you cannot feel, not a snap that holds a stack together.
STACK_SNAP = 0.30         # bead protrusion past the mouth face
STACK_BEAD = 0.40         # groove depth: the snap plus seating clearance
STACK_BEAD_DROP = 1.5     # bead centre below the rim it snaps under
STACK_FIT = 0.25          # clearance per side on every sliding face
STACK_LID_RIM_SEAT_WIDTH = 0.6      # flat bearing shoulder on the lid underside
STACK_LID_RIM_SEAT_THICKNESS = 0.4  # its thickness, uses half the min stacking wall
STACK_MIN_FLOOR_SKIN = 0.8   # floor left under the stepped base
# A groove this deep needs wall behind it.  0.8 mm would leave 0.45 mm, which
# splits; 1.2 mm leaves 0.85 mm, which holds.
STACK_MIN_WALL = 1.2
STACK_SNAP_RAMP = STACK_FIT + STACK_SNAP
STACK_SNAP_RELEASE = STACK_BEAD
STACK_PROFILE_POINTS = 192
STACK_DETENT_MAX_LENGTH = 14.0
STACK_DETENT_GAP = 6.0
STACK_CORNER_CLEARANCE = 3.0

# Lid retention borrows the side connector's printable lock profile, but not
# its physical lock points.  These snaps sit above the connector locks and at
# wall centres, between their half-wave lattice positions.  Their 0.12 mm
# interference is intentionally much lighter than the connector's 0.35 mm.
LID_LOCK_INTERFERENCE = 0.12
LID_LOCK_CLEARANCE = 0.08
LID_LOCK_DROP = 1.5
LID_LOCK_EMBED = 0.20
LID_FOUR_SNAP_MIN_SPAN = 40.0
LID_THICKNESS_EXTRA = {"thin": 0.0, "medium": 0.8, "thick": 1.6}
LID_LABEL_RAISE = 0.6
LID_LABEL_MARGIN = 2.0
LID_LABEL_MIN_CAP = 2.5
LID_HANDLE_EDGE_MARGIN = 5.0
LID_KNOB_SCALE = {"small": 0.12, "medium": 0.18, "large": 0.24}
LID_KNOB_DIAMETER_LIMITS = (6.0, 28.0)
LID_KNOB_HEIGHT_RATIO = 0.55
LID_KNOB_HEIGHT_LIMITS = (4.0, 16.0)
LID_PULL_SCALE = {"small": 0.30, "medium": 0.45, "large": 0.60}
LID_PULL_CLEARANCE = {"small": 6.0, "medium": 8.0, "large": 10.0}
LID_PULL_WIDTH_LIMITS = (12.0, 70.0)
LID_PULL_BAR_DEPTH = 4.0
LID_PULL_BAR_THICKNESS = 3.0

_EPS = 1e-6
_PROFILE_EPS = 0.02


def stack_spec(box: BoxSpec) -> StackSpec:
    return getattr(box, "stack", None) or StackSpec()


def stack_enabled(box: BoxSpec) -> bool:
    return vertical_stack_enabled(box)


def stack_lid_rise(box: BoxSpec) -> float:
    """How far the lid rises above the body rim.

    A thick custom body wall moves the mouth farther from the outside face.
    The lid grows vertically when needed so its plug-to-plate flare remains at
    45 degrees or shallower when printed plug-down.
    """
    if not lid_enabled(box):
        return 0.0
    wall_box = replace(
        box, wall=max(box.wall, STACK_MIN_WALL), standard_walls=False,
    )
    extra = LID_THICKNESS_EXTRA[lid_spec(box).thickness]
    requirements = [
        STACK_LID_SKIN + extra,
        stack_foot_flare_height(wall_box),
        STACK_LID_RIM_SEAT_THICKNESS + _lid_outer_flare_height(wall_box),
    ]
    if lid_stackable(box):
        requirements.append(STACK_SEAT_DEPTH + STACK_MIN_FLOOR_SKIN + extra)
    return max(requirements)


def stack_step_depth(box: BoxSpec) -> float:
    """How far the bin's own stepped base drops into whatever is below it.

    In lid mode it only has to locate in the lid's recess.  In direct mode it
    is the snap itself, so it reaches far enough to put the bead clear of the
    rim edge it clicks under.
    """
    if direct_stack_enabled(box):
        return STACK_PLUG_DEPTH
    return STACK_SEAT_DEPTH if lid_stackable(box) else 0.0


def stack_base_minimum(box: BoxSpec) -> float:
    """Visible/saved base thickness required by the selected stack foot.

    The foot's flare has to finish entirely inside solid base material before
    the vertical cavity wall begins, or the floor/wall corner intersects the
    taper before the outside has returned to full wall thickness.
    """
    if not vertical_stack_enabled(box):
        return DEFAULT_BASE_THICKNESS
    wall_box = replace(
        box, wall=max(box.wall, STACK_MIN_WALL), standard_walls=False,
    )
    flare = stack_foot_flare_height(wall_box)
    return stack_step_depth(box) + max(STACK_MIN_FLOOR_SKIN, flare)


def normalize_stack_settings(box: BoxSpec) -> BoxSpec:
    """Return legal, user-visible wall/base settings for stacking.

    The browser writes these values itself.  This remains the backend safety
    net for old files, API callers and command-line construction.
    """
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return box
    changes = {
        "wall": max(box.wall, STACK_MIN_WALL),
        "standard_walls": False,
    }
    if vertical_stack_enabled(box):
        changes.update(
            base_thickness=max(box.base_thickness, stack_base_minimum(box)),
            standard_base=False,
        )
    return replace(box, **changes)


def stack_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec the body and its interior parts are actually built from.

    Settings are normalized defensively, then the body is made taller by its
    engagement depth.  Consecutive bodies are placed one requested module
    height apart, so the foot overlaps without falsifying the pitch.
    """
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return box
    normalized = normalize_stack_settings(box)
    if not vertical_stack_enabled(box):
        return normalized
    body_z = box.z + stack_step_depth(box) - stack_lid_rise(normalized)
    return replace(normalized, z=body_z)


def stack_grew(box: BoxSpec) -> bool:
    """Whether stacking had to change what the user entered."""
    eff = stack_effective_box(box)
    return not (
        math.isclose(eff.wall, box.wall)
        and math.isclose(eff.z, box.z)
        and math.isclose(eff.base_thickness, box.base_thickness)
    )


# --------------------------------------------------------------------------- #
# shared outlines
# --------------------------------------------------------------------------- #
def _plug_polygon(eff: BoxSpec) -> Polygon:
    """Outline of anything that plugs into the bin mouth.

    One outline serves the bin's own stepped base, the lid's plug and the lid's
    top recess, so a base always fits a recess and a plug always fits a mouth.
    """
    plug = wavy_cavity_polygon(eff).buffer(-STACK_FIT)
    if plug.is_empty or not isinstance(plug, Polygon):
        raise ValueError(
            "this bin is too small to stack - widen it or turn stacking off"
        )
    return plug


def _groove_band(eff: BoxSpec) -> Polygon:
    """Plan ring the snap groove is cut out of, just inside the wall."""
    outer = wavy_cavity_polygon(eff).buffer(STACK_BEAD)
    inner = wavy_cavity_polygon(eff)
    ring = outer.difference(inner)
    if ring.is_empty:
        raise ValueError("this bin's wall is too thin for a stacking groove")
    return ring


def _profile_loft(polygons: list[Polygon], heights: list[float]) -> trimesh.Trimesh:
    """Loft matched wavy outlines into one watertight support-free profile."""
    reference = _resampled_ring(polygons[0], STACK_PROFILE_POINTS)
    rings = [reference]
    rings.extend(
        _align_ring(reference, _resampled_ring(one, STACK_PROFILE_POINTS))
        for one in polygons[1:]
    )
    return _loft_cavity(rings, heights)


def _outline_run(inner: Polygon, outer: Polygon) -> float:
    """Maximum XY growth between two nested outlines."""
    return float(inner.exterior.hausdorff_distance(outer.exterior))


def stack_foot_flare_height(eff: BoxSpec) -> float:
    """Vertical run needed for a <=45 degree foot/lid flare."""
    run = _outline_run(_plug_polygon(eff), wavy_outer_polygon(eff))
    return math.ceil((run + _EPS) * 100.0) / 100.0


def _lid_rim_seat_outline(eff: BoxSpec) -> Polygon:
    """Flat bearing shoulder on the lid underside that lands on the wall top.

    Sized off the cavity, not the (already inset) plug, so it reaches out to
    the wall regardless of the plug's own running clearance.
    """
    cavity = wavy_cavity_polygon(eff)
    outer = wavy_outer_polygon(eff)
    seat = cavity.buffer(STACK_LID_RIM_SEAT_WIDTH).intersection(outer)
    if seat.is_empty or not isinstance(seat, Polygon):
        raise ValueError("this bin is too small for the stacking lid rim seat")
    return seat


def _lid_outer_flare_height(eff: BoxSpec) -> float:
    """Vertical run needed for the <=45 degree flare above the rim seat."""
    run = _outline_run(_lid_rim_seat_outline(eff), wavy_outer_polygon(eff))
    return math.ceil((run + _EPS) * 100.0) / 100.0


def _detent_intervals(lo: float, hi: float) -> list[tuple[float, float]]:
    """One short detent on a small side, two on a longer side."""
    span = hi - lo
    margin = min(STACK_CORNER_CLEARANCE, span * 0.2)
    usable = span - 2.0 * margin
    if usable <= 0.0:
        return []
    if usable >= 2.0 * STACK_DETENT_MAX_LENGTH + STACK_DETENT_GAP:
        length = min(STACK_DETENT_MAX_LENGTH, (usable - STACK_DETENT_GAP) / 2.0)
        return [
            (lo + margin, lo + margin + length),
            (hi - margin - length, hi - margin),
        ]
    length = min(STACK_DETENT_MAX_LENGTH, usable)
    centre = (lo + hi) / 2.0
    return [(centre - length / 2.0, centre + length / 2.0)]


def _detent_masks(eff: BoxSpec) -> list[Polygon]:
    """Symmetric side masks that keep snap material away from corners."""
    plug = _plug_polygon(eff)
    outer = wavy_outer_polygon(eff)
    min_x, min_y, max_x, max_y = plug.bounds
    out_min_x, out_min_y, out_max_x, out_max_y = outer.bounds
    overlap = 1.0
    pad = STACK_FIT + STACK_SNAP + 0.5
    masks: list[Polygon] = []
    for x0, x1 in _detent_intervals(min_x, max_x):
        masks.append(shapely_box(x0, max_y - overlap, x1, out_max_y + pad))
        masks.append(shapely_box(x0, out_min_y - pad, x1, min_y + overlap))
    for y0, y1 in _detent_intervals(min_y, max_y):
        masks.append(shapely_box(max_x - overlap, y0, out_max_x + pad, y1))
        masks.append(shapely_box(out_min_x - pad, y0, min_x + overlap, y1))
    return masks


def _segmented_profile(
    solid: trimesh.Trimesh, eff: BoxSpec, z0: float, z1: float,
) -> list[trimesh.Trimesh]:
    pieces: list[trimesh.Trimesh] = []
    for polygon in _detent_masks(eff):
        mask = _extrude_polygon(polygon, z1 - z0 + 2.0 * _PROFILE_EPS)
        mask.apply_translation((0.0, 0.0, z0 - _PROFILE_EPS))
        piece = intersection([solid, mask])
        if len(piece.faces):
            pieces.append(piece)
    return pieces


def _snap_beads(eff: BoxSpec, plug_top: float) -> list[trimesh.Trimesh]:
    """Segmented beads with a printable insertion ramp and supported release."""
    plug = _plug_polygon(eff)
    peak = plug_top - STACK_BEAD_DROP
    bottom = peak - STACK_SNAP_RAMP
    top = peak + STACK_SNAP_RELEASE
    bead = _profile_loft(
        [plug, plug.buffer(STACK_FIT + STACK_SNAP), plug],
        [bottom, peak, top],
    )
    return _segmented_profile(bead, eff, bottom, top)


def _snap_grooves(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Complementary segmented groove with a <=45 degree printable ceiling."""
    cavity = wavy_cavity_polygon(eff)
    peak = eff.z - STACK_BEAD_DROP
    bottom = peak - STACK_SNAP_RAMP
    top = peak + STACK_SNAP_RELEASE
    groove = _profile_loft(
        [cavity, cavity.buffer(STACK_BEAD), cavity],
        [bottom, peak, top],
    )
    return _segmented_profile(groove, eff, bottom, top)


def _lid_lock_masks(eff: BoxSpec) -> list[Polygon]:
    """Two centred points on small lids, one per side on larger lids."""
    plug = _plug_polygon(eff)
    outer = wavy_outer_polygon(eff)
    min_x, min_y, max_x, max_y = plug.bounds
    out_min_x, out_min_y, out_max_x, out_max_y = outer.bounds
    half_run = LOCK_RUN / 2.0
    overlap = 1.0
    pad = STACK_FIT + LID_LOCK_INTERFERENCE + LID_LOCK_CLEARANCE + 0.5

    horizontal = [
        shapely_box(-half_run, max_y - overlap, half_run, out_max_y + pad),
        shapely_box(-half_run, out_min_y - pad, half_run, min_y + overlap),
    ]
    vertical = [
        shapely_box(max_x - overlap, -half_run, out_max_x + pad, half_run),
        shapely_box(out_min_x - pad, -half_run, min_x + overlap, half_run),
    ]
    if max(eff.x, eff.y) >= LID_FOUR_SNAP_MIN_SPAN:
        return [*horizontal, *vertical]
    return horizontal if eff.x >= eff.y else vertical


def _lid_lock_profile(
    protrusion: float, rim: float, clearance: float = 0.0,
) -> list[tuple[float, float]]:
    """The connector lock's 45-degree profile moved to the lid snap height."""
    profile = _lock_profile(
        protrusion, clearance=clearance, embed=LID_LOCK_EMBED,
    )
    flat_centre = (profile[1][1] + profile[2][1]) / 2.0
    shift = rim - LID_LOCK_DROP - flat_centre
    return [(t, z + shift) for t, z in profile]


def _clip_lid_locks(
    solid: trimesh.Trimesh,
    eff: BoxSpec,
    profile: list[tuple[float, float]],
) -> list[trimesh.Trimesh]:
    z0 = min(z for _, z in profile)
    z1 = max(z for _, z in profile)
    pieces: list[trimesh.Trimesh] = []
    for polygon in _lid_lock_masks(eff):
        mask = _extrude_polygon(polygon, z1 - z0 + 2.0 * _PROFILE_EPS)
        mask.apply_translation((0.0, 0.0, z0 - _PROFILE_EPS))
        piece = intersection([solid, mask])
        if len(piece.faces):
            pieces.append(piece)
    return pieces


def _lid_lock_bumps(eff: BoxSpec, rim: float) -> list[trimesh.Trimesh]:
    """Small discrete bumps on the lid plug."""
    profile = _lid_lock_profile(
        STACK_FIT + LID_LOCK_INTERFERENCE, rim,
    )
    plug = _plug_polygon(eff)
    solid = _profile_loft(
        [plug.buffer(t) for t, _ in profile],
        [z for _, z in profile],
    )
    return _clip_lid_locks(solid, eff, profile)


def _lid_lock_notches(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Matching discrete recesses in the body wall."""
    profile = _lid_lock_profile(
        LID_LOCK_INTERFERENCE,
        eff.z,
        clearance=LID_LOCK_CLEARANCE,
    )
    cavity = wavy_cavity_polygon(eff)
    solid = _profile_loft(
        [cavity.buffer(t) for t, _ in profile],
        [z for _, z in profile],
    )
    return _clip_lid_locks(solid, eff, profile)


# --------------------------------------------------------------------------- #
# body features
# --------------------------------------------------------------------------- #
def stack_body_cutters(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Solids subtracted from the bin body: base step and retention recesses.

    ``eff`` must already be the effective box - these are cut at its rim.
    """
    if not vertical_stack_enabled(eff) and not lid_enabled(eff):
        return []
    cutters: list[trimesh.Trimesh] = []
    if vertical_stack_enabled(eff):
        step = stack_step_depth(eff)
        # The insertion zone stays completely inside the receiver.  Only above
        # its seating datum does the outside grow back to full size.
        outer = wavy_outer_polygon(eff)
        plug = _plug_polygon(eff)
        flare = stack_foot_flare_height(eff)
        shell = _extrude_polygon(outer, step + flare + 2.0 * _PROFILE_EPS)
        shell.apply_translation((0.0, 0.0, -_PROFILE_EPS))
        keep = _profile_loft(
            [plug, plug, outer, outer],
            [-2.0 * _PROFILE_EPS, step, step + flare, step + flare + 2.0 * _PROFILE_EPS],
        )
        cutters.append(difference([shell, keep]))

    if lid_enabled(eff):
        cutters.extend(_lid_lock_notches(eff))
    elif direct_stack_enabled(eff):
        cutters.extend(_snap_grooves(eff))
    return cutters


def stack_body_adders(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """The bead on the stepped base that clicks into the groove below."""
    if not direct_stack_enabled(eff):
        return []
    return _snap_beads(eff, stack_step_depth(eff))


# --------------------------------------------------------------------------- #
# the lid
# --------------------------------------------------------------------------- #
def _clamp(value: float, limits: tuple[float, float]) -> float:
    return max(limits[0], min(limits[1], value))


def _handle_centre(box: BoxSpec, span_x: float, span_y: float) -> tuple[float, float]:
    position = lid_spec(box).handle_position
    offset_x = max(0.0, span_x * 0.28)
    offset_y = max(0.0, span_y * 0.28)
    return {
        "left": (-offset_x, 0.0), "right": (offset_x, 0.0),
        "front": (0.0, -offset_y), "back": (0.0, offset_y),
        "middle": (0.0, 0.0),
    }[position]


def _lid_handle(box: BoxSpec, top_z: float, outer: Polygon) -> trimesh.Trimesh:
    spec = lid_spec(box)
    min_x, min_y, max_x, max_y = outer.bounds
    span_x = max(1.0, max_x - min_x - 2.0 * LID_HANDLE_EDGE_MARGIN)
    span_y = max(1.0, max_y - min_y - 2.0 * LID_HANDLE_EDGE_MARGIN)
    cx, cy = _handle_centre(box, span_x, span_y)
    if spec.handle_type == "knob":
        diameter = _clamp(
            min(span_x, span_y) * LID_KNOB_SCALE[spec.handle_size],
            LID_KNOB_DIAMETER_LIMITS,
        )
        height = _clamp(
            diameter * LID_KNOB_HEIGHT_RATIO, LID_KNOB_HEIGHT_LIMITS,
        )
        knob = trimesh.creation.cone(
            radius=diameter / 2.0, height=height, sections=48,
        )
        knob.apply_translation((cx, cy, top_z))
        return knob

    position = spec.handle_position
    run_x = position in ("front", "back") or (
        position == "middle" and span_x >= span_y
    )
    available = span_x if run_x else span_y
    width = _clamp(
        available * LID_PULL_SCALE[spec.handle_size], LID_PULL_WIDTH_LIMITS,
    )
    width = min(width, max(LID_PULL_WIDTH_LIMITS[0], available))
    clearance = min(
        LID_PULL_CLEARANCE[spec.handle_size], max(4.0, min(span_x, span_y) * 0.28),
    )
    post_height = clearance + LID_PULL_BAR_THICKNESS
    post_size = LID_PULL_BAR_DEPTH
    bar_extents = (
        (width, LID_PULL_BAR_DEPTH, LID_PULL_BAR_THICKNESS)
        if run_x else
        (LID_PULL_BAR_DEPTH, width, LID_PULL_BAR_THICKNESS)
    )
    bar = trimesh.creation.box(extents=bar_extents)
    bar.apply_translation((cx, cy, top_z + clearance + LID_PULL_BAR_THICKNESS / 2.0))
    supports = []
    for sign in (-1.0, 1.0):
        px = cx + (sign * (width - post_size) / 2.0 if run_x else 0.0)
        py = cy + (0.0 if run_x else sign * (width - post_size) / 2.0)
        support = trimesh.creation.cone(
            radius=post_size / 2.0, height=post_height, sections=24,
        )
        support.apply_translation((px, py, top_z))
        supports.append(support)
    return union([bar, *supports])


def _lid_text_parts(
    box: BoxSpec,
    top_z: float,
    regions: list[tuple[str, tuple[float, float, float, float]]],
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    spec = lid_spec(box)
    if not spec.label_enabled:
        return []
    raised = spec.label_style == "raised"
    if raised and spec.stackable:
        raise ValueError("raised lettering cannot be used on a stackable lid")
    parts: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, (x0, y0, x1, y1) in regions:
        text = str(text or "").strip()
        if not text:
            continue
        avail_x = max(0.0, x1 - x0 - 2.0 * LID_LABEL_MARGIN)
        avail_y = max(0.0, y1 - y0 - 2.0 * LID_LABEL_MARGIN)
        probe = text_outline(text, 10.0)
        if spec.label_orientation == "vertical":
            from shapely import affinity
            probe = affinity.rotate(probe, 90.0, origin=(0.0, 0.0))
        bx0, by0, bx1, by1 = probe.bounds
        scale = min(avail_x / max(bx1 - bx0, _EPS), avail_y / max(by1 - by0, _EPS))
        cap = min(15.0, 10.0 * scale)
        if cap < LID_LABEL_MIN_CAP:
            raise ValueError(f"lid label '{text}' cannot fit this compartment")
        outline = text_outline(text, cap)
        from shapely import affinity
        if spec.label_orientation == "vertical":
            outline = affinity.rotate(outline, 90.0, origin=(0.0, 0.0))
        outline = affinity.translate(outline, xoff=(x0 + x1) / 2.0, yoff=(y0 + y1) / 2.0)
        depth = LID_LABEL_RAISE if raised else TEXT_DEPTH
        parts.append((text, text_prism(outline, top_z, depth=depth, raised=raised), raised))
    return parts


def make_lid_parts(
    box: BoxSpec,
    label_regions: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> tuple[trimesh.Trimesh, list[tuple[str, trimesh.Trimesh, bool]]]:
    """Build an ordinary-bin lid and its optional separate label objects."""
    eff = stack_effective_box(box)
    if not lid_enabled(eff):
        raise ValueError("this bin has no lid")

    rim = eff.z
    rise = stack_lid_rise(eff)
    plug_outline = _plug_polygon(eff)
    outer = wavy_outer_polygon(eff)

    # The lid has two independent jobs: a flat rim shoulder that carries the
    # vertical stack load straight into the body wall, and (below, unioned in
    # separately) a plug with its own running clearance.  The shoulder must
    # never tighten or wedge that plug - it lives entirely above the rim.
    rim_seat_outline = _lid_rim_seat_outline(eff)
    outer_flare = _lid_outer_flare_height(eff)
    rim_seat = _extrude_polygon(rim_seat_outline, STACK_LID_RIM_SEAT_THICKNESS)
    rim_seat.apply_translation((0.0, 0.0, rim))

    flare_start = rim + STACK_LID_RIM_SEAT_THICKNESS
    flare_end = flare_start + outer_flare
    flare = _profile_loft(
        [rim_seat_outline, outer], [flare_start, flare_end],
    )
    plate_parts = [rim_seat, flare]
    if rim + rise > flare_end + _EPS:
        cap = _extrude_polygon(outer, rim + rise - flare_end)
        cap.apply_translation((0.0, 0.0, flare_end))
        plate_parts.append(cap)

    plug = _extrude_polygon(plug_outline, STACK_PLUG_DEPTH)
    plug.apply_translation((0.0, 0.0, rim - STACK_PLUG_DEPTH))

    lid = union([*plate_parts, plug, *_lid_lock_bumps(eff, rim)])

    if lid_stackable(eff):
        # Recess accepting the next stackable-lid bin's stepped base.
        seat = _extrude_polygon(
            plug_outline.buffer(STACK_FIT), STACK_SEAT_DEPTH + 1.0
        )
        seat.apply_translation((0.0, 0.0, rim + rise - STACK_SEAT_DEPTH))
        lid = difference([lid, seat])
    elif lid_has_handle(eff):
        lid = union([lid, _lid_handle(eff, rim + rise, outer)])

    regions = label_regions or []
    if lid_spec(eff).label_enabled and not regions:
        safe = plug_outline if lid_stackable(eff) else outer
        regions = [(lid_spec(eff).label_text, tuple(float(v) for v in safe.bounds))]
    labels = _lid_text_parts(eff, rim + rise, regions)
    sunk = [mesh for _text, mesh, raised in labels if not raised]
    if sunk:
        lid = difference([lid, union(sunk) if len(sunk) > 1 else sunk[0]])
    lid.remove_unreferenced_vertices()
    return lid, labels


def make_stack_lid(box: BoxSpec) -> trimesh.Trimesh:
    """Compatibility wrapper for the former stack-lid-only builder."""
    return make_lid_parts(box)[0]


def stack_closed_height(box: BoxSpec) -> float:
    """Detached physical envelope, including the interlocking foot depth."""
    return stack_effective_box(box).z + stack_lid_rise(box)


def stack_module_height(box: BoxSpec) -> float:
    """Requested contribution between consecutive stack seating datums."""
    return box.z


def stack_pitch(box: BoxSpec) -> float:
    """Height one more bin adds to a stack: exactly the requested module."""
    return stack_module_height(box)


def stack_summary(box: BoxSpec) -> dict:
    """Readout for the preview panel and the generation result."""
    spec = stack_spec(box)
    eff = stack_effective_box(box)
    parts = ["Bin"] + (["Lid"] if lid_enabled(box) else [])
    return {
        "mode": "lid" if lid_stackable(box) else spec.mode,
        "enabled": vertical_stack_enabled(box),
        "module_height_mm": round(stack_module_height(box), 3),
        "closed_height_mm": round(stack_closed_height(box), 3),
        "pitch_mm": round(stack_pitch(box), 3),
        "engagement_mm": round(stack_step_depth(box), 3),
        "body_z_mm": round(eff.z, 3),
        "lid_rise_mm": round(stack_lid_rise(box), 3),
        "wall_mm": round(eff.wall, 3),
        "wall_raised": eff.wall > box.wall + _EPS,
        "base_mm": round(eff.base_thickness, 3),
        "base_raised": eff.base_thickness > box.base_thickness + _EPS,
        "parts": parts,
    }


def validate_stack_design(box: BoxSpec) -> None:
    """Actionable checks, raised before anything is built."""
    spec = stack_spec(box)
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return
    if getattr(getattr(box, "b4b", None), "enabled", False):
        raise ValueError(
            "a Bin for Bins already stacks on its own - turn B4B stacking on "
            "instead"
        )
    # Checked against the request, before the effective box is built: below
    # this the shortened body fails BoxSpec's own lock-bump minimum, and the
    # user would get told about lock bumps on a bin they never made short.
    if vertical_stack_enabled(box):
        floor = stack_base_minimum(box)
        step = stack_step_depth(box)
        minimum = (floor - step) + MIN_HEIGHT_ABOVE_BASE + stack_lid_rise(box)
        if box.z < minimum - _EPS:
            raise ValueError(
                f"a stackable bin needs at least {minimum:g} mm of height - "
                f"the snap and its floor take up the bottom {floor:g} mm"
            )
    eff = stack_effective_box(box)
    if lid_enabled(box):
        if lid_stackable(box) and stack_lid_rise(eff) - STACK_SEAT_DEPTH < STACK_MIN_FLOOR_SKIN - _EPS:
            raise ValueError("the stacking lid does not leave enough material under its seat")
        bump_profile = _lid_lock_profile(
            STACK_FIT + LID_LOCK_INTERFERENCE, eff.z,
        )
        if min(z for _, z in bump_profile) < eff.z - STACK_PLUG_DEPTH - _EPS:
            raise ValueError("the stacking lid plug is too short for its lock points")
    elif direct_stack_enabled(box):
        _groove_band(eff)
    _plug_polygon(eff)
