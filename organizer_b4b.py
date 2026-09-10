"""B4B (Bin for Bins) - a Wavefinity container mode.

A B4B is an ordinary Wavefinity bin whose interior is reserved for a field of
child Wavefinity bins.  Its outer X/Y stay exactly on the 8 mm lattice so it
still shares the global wave phase with every other bin; a lower internal
*mating rail* presents the same authoritative wave one mating gap outside the
child field, so perimeter child bins interlock with the B4B exactly as they
would with a neighbouring bin.

This module owns every B4B tuning constant and every B4B geometry builder.  It
imports engine primitives; nothing in the engine imports it, so there is no
cycle.  ``organizer_app`` drives generation through :func:`generate_b4b_files`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
import math

import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.affinity import translate as translate_polygon

from organizer_engine import (
    CORNER_INSET,
    GRID_PITCH,
    TEXT_CAP_HEIGHT_MIN,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    B4BSpec,
    BoxSpec,
    _rounded,
    _wall_points,
    max_wave_slope,
    text_outline,
    text_prism,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import (
    _extrude_polygon,
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    translated,
    union,
)

# --------------------------------------------------------------------------- #
# tuning constants - centralised, conservative first-print defaults
# --------------------------------------------------------------------------- #
# Interlock rail
B4B_RAIL_HEIGHT = 4.0            # rail height above the internal floor top
B4B_RAIL_CORNER_FILLET = 0.6

# Effective base / stacking
B4B_MIN_FLOOR_SKIN = 0.8        # printable floor left under a stack recess
B4B_STACK_RECESS_DEPTH = 2.0    # female recess depth == male boss height
B4B_STACK_BOSS_DIAMETER = 5.0
B4B_STACK_FEMALE_RADIAL_CLEARANCE = 0.25
B4B_STACK_INSET_FRACTION = 0.16  # locator centre inset from each outer edge
B4B_STACK_INSET_MIN = 4.0
B4B_STACK_MIN_FOOTPRINT_UNITS = 3  # smallest box that still gets four locators

# Lid
B4B_LID_SKIN = 1.6              # lid top plate thickness
B4B_LID_SKIRT_WALL = 2.0       # locating skirt wall thickness
B4B_LID_SEAT_CLEARANCE = 0.30  # lateral clearance, skirt inner face to body
B4B_LID_SKIRT_LAP = 4.0        # how far the skirt laps down past the body rim

# M3 hardware (no nuts, no inserts)
B4B_M3_NOMINAL = 3.0
B4B_M3_CLEAR_BORE = 3.4        # rotating knuckle / pivot clearance hole
B4B_M3_PILOT = 2.6            # thread-forming terminal pilot
B4B_M3_THREAD_ENGAGE_MIN = 3.0
B4B_M3_HEAD_CLEAR = 6.0
B4B_SCREW_LENGTHS = (12, 16, 20, 25, 30)   # allowed kit lengths, mm
B4B_M3_MAX_PROTRUSION = 6.0

# Hinges (exactly two, rear wall)
B4B_HINGE_COUNT = 2
B4B_HINGE_WIDTH_FRACTION = 0.16
B4B_HINGE_WIDTH_MIN = 10.0
B4B_HINGE_WIDTH_MAX = 24.0
B4B_HINGE_KNUCKLE_RADIUS = 3.1   # encloses the clear bore with a printable wall
B4B_HINGE_AXIAL_GAP = 0.35       # running gap between body and lid knuckles
B4B_HINGE_CLEAR_KEEPOUT = 1.0    # extra gap from a wall's corner tangent

# Latches (secure lid only)
B4B_LATCH_WIDTH_FRACTION = 0.14
B4B_LATCH_WIDTH_MIN = 12.0
B4B_LATCH_WIDTH_MAX = 22.0
B4B_LATCH_MUTUAL_CLEARANCE = 6.0
B4B_LATCH_PROFILES = {
    "lightweight": {
        "lever_thickness": 3.0,
        "hook_depth": 1.8,
        "catch_thickness": 2.4,
        "pad_wall": 2.0,
        "pad_height": 8.0,
        "detent": 0.25,
    },
    "standard": {
        "lever_thickness": 4.2,
        "hook_depth": 3.0,
        "catch_thickness": 3.6,
        "pad_wall": 3.2,
        "pad_height": 11.0,
        "detent": 0.45,
    },
}

# Minimum outer X for a secure lid: two printable hinge assemblies plus corner
# keep-outs, quantised up to a whole grid unit.
B4B_SECURE_MIN_X = (
    math.ceil(
        (2.0 * B4B_HINGE_WIDTH_MIN + 4.0 * CORNER_INSET + WAVE_MATING_GAP - 1e-9)
        / GRID_PITCH
    )
    * GRID_PITCH
)
# Minimum outer X to force two latches.
B4B_TWO_LATCH_MIN_X = (
    math.ceil(
        (2.0 * B4B_LATCH_WIDTH_MIN + 3.0 * B4B_LATCH_MUTUAL_CLEARANCE - 1e-9)
        / GRID_PITCH
    )
    * GRID_PITCH
)

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# capacity + effective box
# --------------------------------------------------------------------------- #
def _axis_capacity(axis_mm: float, wall_depth: float) -> int:
    """Whole child units that fit one outer axis - the paper formula.

    ``C = floor(N - 2*(gap + D)/G)`` with ``N`` the outer axis in whole units
    and ``D`` the axis-depth-equivalent wall.  Not hard-coded to ``N - 1`` so a
    future wall or wave change stays valid.
    """
    n = round(axis_mm / GRID_PITCH)
    slack = 2.0 * (WAVE_MATING_GAP + wall_depth) / GRID_PITCH
    return int(math.floor(n - slack + _EPS))


def b4b_capacity_units(box: BoxSpec) -> tuple[int, int]:
    """``(units_x, units_y)`` of child Wavefinity footprint the B4B holds.

    Computed on the *effective* box, so any auto-grow for hardware or a 1-unit
    minimum is already reflected.
    """
    eff = b4b_effective_box(box)
    return (
        _axis_capacity(eff.x, eff.wall_depth),
        _axis_capacity(eff.y, eff.wall_depth),
    )


def b4b_capacity_mm(box: BoxSpec) -> tuple[float, float]:
    """Nominal child field in mm: ``capacity_units * GRID_PITCH`` per axis."""
    cx, cy = b4b_capacity_units(box)
    return cx * GRID_PITCH, cy * GRID_PITCH


def b4b_effective_base_thickness(box: BoxSpec) -> float:
    """Base thickness B4B geometry actually uses.

    ``max(requested, stack_recess_depth + min_floor_skin)`` when stacking is on,
    otherwise the requested value.  Never redefines the normal Standard Base.
    """
    b4b = box.b4b.normalised()
    requested = box.base_thickness
    if b4b.stacking and b4b.lid:
        return max(requested, B4B_STACK_RECESS_DEPTH + B4B_MIN_FLOOR_SKIN)
    return requested


def b4b_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec every B4B builder uses.

    Identical to the user's box except for auto-grown X/Y (1-unit minimum,
    secure-lid hardware, forced two latches) and any stacking base
    reinforcement.  Easy Clean and the flat-inside band are forced off because
    they alter the floor/perimeter the child bins must seat on.
    """
    b4b = box.b4b.normalised()
    x, y = box.x, box.y

    # 1-unit interior minimum on both axes.
    guard = 0
    while _axis_capacity(x, box.wall_depth) < 1 and guard < 64:
        x += GRID_PITCH
        guard += 1
    guard = 0
    while _axis_capacity(y, box.wall_depth) < 1 and guard < 64:
        y += GRID_PITCH
        guard += 1

    # Secure-lid hardware needs a minimum outer X.
    if b4b.secure_lid:
        while x < B4B_SECURE_MIN_X - _EPS:
            x += GRID_PITCH
        if b4b.latch_count == "2":
            while x < B4B_TWO_LATCH_MIN_X - _EPS:
                x += GRID_PITCH

    base_thickness = b4b_effective_base_thickness(box)
    return replace(
        box,
        x=x,
        y=y,
        base_thickness=base_thickness,
        easy_clean=False,
        easy_clean_style="bevel",
        flat_inside=0.0,
        b4b=b4b,
    )


def b4b_grew(box: BoxSpec) -> bool:
    """Whether the effective box differs from what the user entered."""
    eff = b4b_effective_box(box)
    return not (
        math.isclose(eff.x, box.x)
        and math.isclose(eff.y, box.y)
        and math.isclose(eff.base_thickness, box.base_thickness)
    )


def b4b_max_child_height(box: BoxSpec) -> float:
    """Tallest child bin that fits under a closed lid.

    A child rests on the effective B4B floor; the lid underside sits
    ``lid_headroom_mm`` above a child whose nominal height equals the entered
    ``box.z``.  So the promised maximum child height is simply ``box.z`` - the
    headroom is realised above it by the lid riser, never by shrinking this.
    """
    return b4b_effective_box(box).z


# --------------------------------------------------------------------------- #
# mating rail
# --------------------------------------------------------------------------- #
def b4b_mating_polygon(box: BoxSpec) -> Polygon:
    """Inward-facing wave the child field's perimeter bins mate to.

    Built with the *same* ``wave_value`` phase/amplitude/wavelength as every
    Wavefinity wall (via :func:`_wall_points`), not a Shapely buffer of the
    child field - a perpendicular buffer would break the phase relationship.
    Baseline half-extent per axis is ``C*G/2 + gap/2``, exactly one axis gap
    outside a child field whose perimeter wall baseline is ``C*G/2 - gap/2``.
    """
    eff = b4b_effective_box(box)
    cx, cy = _axis_capacity(eff.x, eff.wall_depth), _axis_capacity(eff.y, eff.wall_depth)
    if cx < 1 or cy < 1:
        raise ValueError("B4B interior is smaller than one child unit")
    half_x = cx * GRID_PITCH / 2.0 + WAVE_MATING_GAP / 2.0
    half_y = cy * GRID_PITCH / 2.0 + WAVE_MATING_GAP / 2.0
    tx = half_x - CORNER_INSET
    ty = half_y - CORNER_INSET
    polygon = Polygon(_wall_points(half_x, half_y, tx, ty))
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("B4B mating outline is not a valid single polygon")
    return _rounded(polygon, B4B_RAIL_CORNER_FILLET)


def b4b_rail_ring_polygon(box: BoxSpec) -> Polygon:
    """Plan-view material of the lower mating rail: the ring between the normal
    cavity outline and the mating outline."""
    eff = b4b_effective_box(box)
    cavity = wavy_cavity_polygon(eff)
    mating = b4b_mating_polygon(box)
    if not cavity.buffer(_EPS).contains(mating):
        raise ValueError(
            "B4B mating rail would not fit inside the main cavity for this "
            "size/wall; grow the box or reduce the wall"
        )
    ring = cavity.difference(mating)
    if ring.is_empty or ring.area <= 0.0:
        raise ValueError("B4B mating rail ring is empty")
    return ring


# --------------------------------------------------------------------------- #
# hardware plan
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BHardwarePlan:
    """Every hinge/latch dimension, resolved once.  Preview, export, BOM and
    validation all read this so they cannot disagree."""

    hinge_count: int
    hinge_centers_x: tuple[float, ...]
    hinge_width: float
    hinge_screw_length_mm: int
    hinge_axis_y: float
    hinge_axis_z: float
    latch_count_resolved: int
    latch_centers_x: tuple[float, ...]
    latch_width: float
    latch_screw_length_mm: int
    strength_profile: dict
    nuts: int = 0

    def screw_bom(self) -> list[str]:
        lines: list[str] = []
        if self.hinge_count:
            lines.append(
                f"{self.hinge_count} x M3x{self.hinge_screw_length_mm} hinge pins"
            )
        if self.latch_count_resolved:
            lines.append(
                f"{self.latch_count_resolved} x M3x{self.latch_screw_length_mm} latch pins"
            )
        lines.append("No nuts")
        return lines


def _pick_screw(span_mm: float) -> int:
    """Smallest allowed M3 length that spans ``span_mm`` plus minimum thread
    engagement without excessive protrusion."""
    required = span_mm + B4B_M3_THREAD_ENGAGE_MIN
    for length in B4B_SCREW_LENGTHS:
        if length + _EPS >= required and length - span_mm <= B4B_M3_MAX_PROTRUSION + _EPS:
            return length
    # Nothing fits cleanly: fall back to the longest allowed and let validation
    # report the along-axis geometry needs trimming.
    return B4B_SCREW_LENGTHS[-1]


def _front_span(eff: BoxSpec) -> float:
    """Usable straight run of the front wall between corner tangents."""
    return 2.0 * (eff.half_x - CORNER_INSET)


def b4b_hardware_plan(box: BoxSpec) -> B4BHardwarePlan:
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    profile = B4B_LATCH_PROFILES[b4b.latch_strength]

    if not b4b.secure_lid:
        return B4BHardwarePlan(
            hinge_count=0,
            hinge_centers_x=(),
            hinge_width=0.0,
            hinge_screw_length_mm=0,
            hinge_axis_y=0.0,
            hinge_axis_z=0.0,
            latch_count_resolved=0,
            latch_centers_x=(),
            latch_width=0.0,
            latch_screw_length_mm=0,
            strength_profile=profile,
        )

    # Hinges: two, symmetric, near the quarter points, clamped to corner keep-outs.
    hinge_width = min(
        B4B_HINGE_WIDTH_MAX,
        max(B4B_HINGE_WIDTH_MIN, B4B_HINGE_WIDTH_FRACTION * eff.x),
    )
    limit = eff.half_x - CORNER_INSET - B4B_HINGE_CLEAR_KEEPOUT - hinge_width / 2.0
    centre = min(max(eff.x / 4.0, hinge_width / 2.0 + 1.0), max(limit, 1.0))
    hinge_centers_x = (-centre, centre)
    hinge_axis_y = eff.half_y + WAVE_AMPLITUDE + B4B_HINGE_KNUCKLE_RADIUS + 0.6
    # axis at the lid-underside height, just behind the rear wall: the lid swings
    # back clear of the wavy wall without a tall, fragile tower.
    hinge_axis_z = b4b_lid_underside_z(box)
    hinge_screw = _pick_screw(hinge_width)

    # Latches: front, 1 / 2 / Auto.
    latch_width = min(
        B4B_LATCH_WIDTH_MAX,
        max(B4B_LATCH_WIDTH_MIN, B4B_LATCH_WIDTH_FRACTION * eff.x),
    )
    span = _front_span(eff)
    two_fit = (2.0 * latch_width + 3.0 * B4B_LATCH_MUTUAL_CLEARANCE) <= span + _EPS
    if b4b.latch_count == "1":
        resolved = 1
    elif b4b.latch_count == "2":
        resolved = 2
    else:
        resolved = 2 if two_fit else 1
    if resolved == 1:
        latch_centers_x = (0.0,)
    else:
        third = span / 6.0
        latch_centers_x = (-third, third)
    latch_screw = _pick_screw(latch_width)

    return B4BHardwarePlan(
        hinge_count=B4B_HINGE_COUNT,
        hinge_centers_x=hinge_centers_x,
        hinge_width=hinge_width,
        hinge_screw_length_mm=hinge_screw,
        hinge_axis_y=hinge_axis_y,
        hinge_axis_z=hinge_axis_z,
        latch_count_resolved=resolved,
        latch_centers_x=latch_centers_x,
        latch_width=latch_width,
        latch_screw_length_mm=latch_screw,
        strength_profile=profile,
    )


# --------------------------------------------------------------------------- #
# lid datums
# --------------------------------------------------------------------------- #
def b4b_internal_floor_z(box: BoxSpec) -> float:
    return b4b_effective_box(box).base_thickness


def b4b_lid_underside_z_from_eff(eff: BoxSpec) -> float:
    return eff.base_thickness + eff.z + eff.b4b.lid_headroom_mm


def b4b_lid_underside_z(box: BoxSpec) -> float:
    """Z of the lid underside over the child field, from the B4B bottom datum.

    ``effective_floor_z + box.z + lid_headroom_mm`` - a child of nominal height
    ``box.z`` resting on the floor then has ``lid_headroom_mm`` clearance.
    """
    return b4b_lid_underside_z_from_eff(b4b_effective_box(box))


# --------------------------------------------------------------------------- #
# body
# --------------------------------------------------------------------------- #
def _stack_locator_centres(eff: BoxSpec) -> list[tuple[float, float]]:
    inset_x = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * eff.x)
    inset_y = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * eff.y)
    hx = eff.x / 2.0 - inset_x
    hy = eff.y / 2.0 - inset_y
    return [(-hx, -hy), (hx, -hy), (-hx, hy), (hx, hy)]


def _stack_recesses(box: BoxSpec) -> list[trimesh.Trimesh]:
    eff = b4b_effective_box(box)
    female_r = B4B_STACK_BOSS_DIAMETER / 2.0 + B4B_STACK_FEMALE_RADIAL_CLEARANCE
    solids: list[trimesh.Trimesh] = []
    for cx, cy in _stack_locator_centres(eff):
        cyl = trimesh.creation.cylinder(
            radius=female_r, height=B4B_STACK_RECESS_DEPTH + 0.2, sections=48
        )
        cyl.apply_translation((cx, cy, (B4B_STACK_RECESS_DEPTH + 0.2) / 2.0 - 0.1))
        solids.append(cyl)
    return solids


def make_b4b_body(box: BoxSpec) -> trimesh.Trimesh:
    """The B4B body: normal Wavefinity outer shell (no Easy Clean, no flat
    band, no interior lock bumps) unioned with the lower mating rail, hinge
    towers and latch pads, less any stack recesses."""
    eff = b4b_effective_box(box)
    floor_z = eff.base_thickness
    plan = b4b_hardware_plan(box)

    envelope = _extrude_polygon(wavy_outer_polygon(eff), eff.z)
    cavity = _extrude_polygon(
        wavy_cavity_polygon(eff), eff.z - floor_z + 1.0
    )
    cavity.apply_translation((0.0, 0.0, floor_z))
    shell = difference([envelope, cavity])

    # start the rail just inside the floor so the union is a single solid, not
    # two shells meeting face to face
    rail = _extrude_polygon(b4b_rail_ring_polygon(box), B4B_RAIL_HEIGHT + 0.6)
    rail.apply_translation((0.0, 0.0, floor_z - 0.6))
    body = union([shell, rail])

    if plan.hinge_count:
        for tower in _hinge_body_parts(box, plan):
            body = union([body, tower])
    if plan.latch_count_resolved:
        for pad in _latch_body_parts(box, plan):
            body = union([body, pad])

    if eff.b4b.stacking and eff.b4b.lid:
        body = difference([body, *_stack_recesses(box)])

    body.remove_unreferenced_vertices()
    body.merge_vertices()
    return body


# --------------------------------------------------------------------------- #
# lid
# --------------------------------------------------------------------------- #
def _skirt_polygons(eff: BoxSpec) -> tuple[Polygon, Polygon]:
    """(outer, inner) plan outlines of the locating skirt.

    Inner face follows the body outer wave offset straight out by the seat
    clearance - a constant-gap wavy channel, the same phase trick the rail
    uses - so the lid locates without a press fit."""
    clr = B4B_LID_SEAT_CLEARANCE
    tx = eff.half_x - CORNER_INSET
    ty = eff.half_y - CORNER_INSET
    inner = Polygon(_wall_points(eff.half_x + clr, eff.half_y + clr, tx, ty))
    outer = Polygon(
        _wall_points(
            eff.half_x + clr + B4B_LID_SKIRT_WALL,
            eff.half_y + clr + B4B_LID_SKIRT_WALL,
            tx, ty,
        )
    )
    inner = _rounded(inner, B4B_RAIL_CORNER_FILLET)
    outer = _rounded(outer, B4B_RAIL_CORNER_FILLET)
    return outer, inner


def make_b4b_lid(box: BoxSpec) -> trimesh.Trimesh:
    """Lid as it sits on the assembled box (assembly-space, not print-space).

    Passive: a clearance-fit locating skirt plus the top plate, raised to the
    headroom datum.  Secure: adds the lid-side hinge knuckles and latch pivot
    ears.  No snap or friction feature either way.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.lid:
        raise ValueError("this B4B has no lid")
    plan = b4b_hardware_plan(box)

    underside_z = b4b_lid_underside_z(box)
    outer, inner = _skirt_polygons(eff)

    # the plate reaches a little below the underside datum so it fuses into the
    # skirt, hinge tabs and latch ears as one connected solid
    plate = _extrude_polygon(outer, B4B_LID_SKIN + 0.8)
    plate.apply_translation((0.0, 0.0, underside_z - 0.8))

    skirt_ring = outer.difference(inner)
    skirt_top = underside_z
    skirt_bottom = eff.z - B4B_LID_SKIRT_LAP
    skirt_h = skirt_top - skirt_bottom
    skirt = _extrude_polygon(skirt_ring, skirt_h)
    skirt.apply_translation((0.0, 0.0, skirt_bottom))
    # Keep the locating skirt to the two X-side walls only: the front carries
    # latches and the rear carries hinges, and a skirt lapping down past the rim
    # there would clash with that hardware.  The side runs are wavy, so they
    # still locate the lid on both axes without a snap.
    side_clip = trimesh.creation.box(
        extents=(eff.x * 4.0,
                 2.0 * (eff.half_y - CORNER_INSET - 2.0),
                 skirt_h + 20.0)
    )
    side_clip.apply_translation((0.0, 0.0, skirt_bottom + skirt_h / 2.0))
    skirt = _intersection([skirt, side_clip])

    lid = union([plate, skirt])

    if plan.hinge_count:
        for knuckle in _hinge_lid_parts(box, plan):
            lid = union([lid, knuckle])
    if plan.latch_count_resolved:
        for ear in _latch_lid_parts(box, plan):
            lid = union([lid, ear])

    if eff.b4b.stacking:
        for boss in _stack_bosses(box):
            lid = union([lid, boss])

    lid.remove_unreferenced_vertices()
    lid.merge_vertices()
    return lid


def _stack_bosses(box: BoxSpec) -> list[trimesh.Trimesh]:
    eff = b4b_effective_box(box)
    top_z = b4b_lid_underside_z(box) + B4B_LID_SKIN
    solids: list[trimesh.Trimesh] = []
    for cx, cy in _stack_locator_centres(eff):
        cyl = trimesh.creation.cylinder(
            radius=B4B_STACK_BOSS_DIAMETER / 2.0,
            height=B4B_STACK_RECESS_DEPTH,
            sections=48,
        )
        # slight top chamfer so it self-locates without a snap
        cyl.apply_translation((cx, cy, top_z + B4B_STACK_RECESS_DEPTH / 2.0))
        solids.append(cyl)
    return solids


# --------------------------------------------------------------------------- #
# hinge geometry (integrated knuckles + teardrop M3 bore)
# --------------------------------------------------------------------------- #
def _teardrop_profile_yz(radius: float) -> Polygon:
    """A printable horizontal-hole section: the lower ~270 deg of a circle
    closed by an upward roof to an apex, drawn in a (y, z) plane."""
    pts = [
        (radius * math.cos(a), radius * math.sin(a))
        for a in np.linspace(math.radians(135.0), math.radians(405.0), 60)
    ]
    pts.append((0.0, radius * 1.7))
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def _round_profile_yz(radius: float) -> Polygon:
    return Polygon(
        [
            (radius * math.cos(a), radius * math.sin(a))
            for a in np.linspace(0.0, 2.0 * math.pi, 60, endpoint=False)
        ]
    )


def _x_cylinder(radius: float, length: float, teardrop: bool = True) -> trimesh.Trimesh:
    """A bore/knuckle solid whose axis is world X, centred on the origin."""
    prof = _teardrop_profile_yz(radius) if teardrop else _round_profile_yz(radius)
    return _extrude_yz_profile(prof, length)


def _hinge_seg(plan: B4BHardwarePlan) -> float:
    return plan.hinge_width / 3.0


def _knuckle(cx: float, axis_y: float, axis_z: float, width: float,
             radius: float) -> trimesh.Trimesh:
    k = _x_cylinder(radius, width, teardrop=False)
    k.apply_translation((cx, axis_y, axis_z))
    return k


def _hinge_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two rear towers per hinge (the outer thirds of a three-knuckle hinge):
    a local thickening of the rear wall carried up to the pin axis, plus the
    round knuckle.  The near tower takes a clearance bore, the far one a pilot
    so the M3 threads in with no nut.  Integrated into the body."""
    eff = b4b_effective_box(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = B4B_HINGE_KNUCKLE_RADIUS
    y0 = eff.half_y - eff.wall_depth
    y1 = plan.hinge_axis_y + r
    z1 = plan.hinge_axis_z
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        for side, bore_r, bore_len_frac in (
            (-1.0, B4B_M3_CLEAR_BORE / 2.0, 1.4),   # near: clearance, over-long
            (+1.0, B4B_M3_PILOT / 2.0, 1.0),        # far: pilot, contained
        ):
            kx = cx + side * seg
            block = trimesh.creation.box(extents=(kw, y1 - y0, z1))
            block.apply_translation((kx, (y0 + y1) / 2.0, z1 / 2.0))
            tower = union([block, _knuckle(kx, plan.hinge_axis_y, plan.hinge_axis_z, kw, r)])
            bore = _x_cylinder(bore_r, seg * bore_len_frac + 1.0)
            bx = kx if side > 0 else kx - 0.5
            bore.apply_translation((bx, plan.hinge_axis_y, plan.hinge_axis_z))
            parts.append(difference([tower, bore]))
    return parts


def _hinge_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """The centre knuckle per hinge, hanging from the lid rear edge to the pin
    axis and bored for clearance.  Distinct solid sharing the pin with the two
    body towers."""
    eff = b4b_effective_box(box)
    underside_z = b4b_lid_underside_z(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = B4B_HINGE_KNUCKLE_RADIUS
    y_back = eff.half_y + WAVE_AMPLITUDE
    z_hi = underside_z + B4B_LID_SKIN
    z_lo = min(plan.hinge_axis_z - r, underside_z - 0.8)
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        block = trimesh.creation.box(
            extents=(kw, plan.hinge_axis_y - y_back + r, z_hi - z_lo)
        )
        block.apply_translation(
            (cx, (y_back + plan.hinge_axis_y + r) / 2.0, (z_hi + z_lo) / 2.0)
        )
        tab = union([block, _knuckle(cx, plan.hinge_axis_y, plan.hinge_axis_z, kw, r)])
        bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, kw + 1.0)
        bore.apply_translation((cx, plan.hinge_axis_y, plan.hinge_axis_z))
        parts.append(difference([tab, bore]))
    return parts


# --------------------------------------------------------------------------- #
# latch geometry (rotating printed hook on an M3 pivot, reinforced catch)
#
# Coordinate scheme, all latches on the front (-Y) wall, per latch centre cx:
#   y_wall   body front outer crest
#   catch pad stands off the wall; a catch lip projects forward with a flat
#     underside at z_catch for positive engagement
#   the pivot axis sits forward of the lip, just below the lid underside; two
#     lid ears hang to it and the separate lever hooks back under the lip.
# --------------------------------------------------------------------------- #
def _latch_frame(eff: BoxSpec, plan: B4BHardwarePlan) -> dict:
    prof = plan.strength_profile
    underside_z = b4b_lid_underside_z_from_eff(eff)
    y_wall = -(eff.half_y + WAVE_AMPLITUDE)
    pad_out = prof["pad_wall"]
    lip_front = y_wall - pad_out - prof["hook_depth"] - 1.0
    return {
        "prof": prof,
        "y_wall": y_wall,
        "pad_out": pad_out,
        "lip_front": lip_front,
        "z_catch": eff.z - prof["catch_thickness"],
        "axis_y": lip_front - 2.5,
        "axis_z": underside_z - 1.0,
        "underside_z": underside_z,
        "ear_t": prof["pad_wall"],
    }


def _latch_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """A reinforced catch pad + forward catch lip on the front exterior."""
    eff = b4b_effective_box(box)
    f = _latch_frame(eff, plan)
    prof = f["prof"]
    parts: list[trimesh.Trimesh] = []
    pad_w = plan.latch_width + 2.0 * prof["pad_wall"]
    pad_y0 = f["y_wall"] - f["pad_out"]
    pad_y1 = f["y_wall"] + 2.0
    for cx in plan.latch_centers_x:
        pad = trimesh.creation.box(
            extents=(pad_w, pad_y1 - pad_y0, prof["pad_height"])
        )
        pad.apply_translation(
            (cx, (pad_y0 + pad_y1) / 2.0, eff.z - prof["pad_height"] / 2.0)
        )
        lip = trimesh.creation.box(
            extents=(plan.latch_width, pad_y0 - f["lip_front"], prof["catch_thickness"])
        )
        lip.apply_translation(
            (cx, (pad_y0 + f["lip_front"]) / 2.0, eff.z - prof["catch_thickness"] / 2.0)
        )
        parts.append(union([pad, lip]))
    return parts


def _latch_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two pivot ears per latch, hanging from the lid front to the pivot axis."""
    eff = b4b_effective_box(box)
    f = _latch_frame(eff, plan)
    parts: list[trimesh.Trimesh] = []
    ear_t = f["ear_t"]
    top = f["underside_z"] + B4B_LID_SKIN
    z0 = f["axis_z"] - 3.0
    y0 = f["axis_y"] - 2.0
    y1 = f["y_wall"] - f["pad_out"] + 1.0   # reach back to just past the pad face
    for cx in plan.latch_centers_x:
        for sign in (-1.0, 1.0):
            ex = cx + sign * (plan.latch_width / 2.0 + B4B_HINGE_AXIAL_GAP + ear_t / 2.0)
            ear = trimesh.creation.box(extents=(ear_t, y1 - y0, top - z0))
            ear.apply_translation((ex, (y0 + y1) / 2.0, (z0 + top) / 2.0))
            bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, ear_t + 1.0)
            bore.apply_translation((ex, f["axis_y"], f["axis_z"]))
            parts.append(difference([ear, bore]))
    return parts


def make_b4b_latches(box: BoxSpec) -> list[trimesh.Trimesh]:
    """The rotating hook levers, one per resolved latch, in assembly space
    (closed).  Each is exported as its own printable object."""
    eff = b4b_effective_box(box)
    plan = b4b_hardware_plan(box)
    if not plan.latch_count_resolved:
        return []
    f = _latch_frame(eff, plan)
    prof = f["prof"]
    lever_w = plan.latch_width - 2.0 * B4B_HINGE_AXIAL_GAP
    levers: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        arm_top = f["axis_z"] + prof["lever_thickness"] / 2.0
        arm_bottom = f["z_catch"] - prof["catch_thickness"] - 1.0
        arm = trimesh.creation.box(
            extents=(lever_w, prof["lever_thickness"], arm_top - arm_bottom)
        )
        arm.apply_translation(
            (cx, f["axis_y"], (arm_top + arm_bottom) / 2.0)
        )
        boss = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0 + 1.6, lever_w, teardrop=False)
        boss.apply_translation((cx, f["axis_y"], f["axis_z"]))
        bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, lever_w + 4.0)
        bore.apply_translation((cx, f["axis_y"], f["axis_z"]))
        # hook tooth: from the arm back face toward the body, under the lip
        tooth_y0 = f["axis_y"] + prof["lever_thickness"] / 2.0 - 0.4
        tooth_y1 = f["lip_front"] + prof["hook_depth"]
        tooth = trimesh.creation.box(
            extents=(lever_w, tooth_y1 - tooth_y0, prof["catch_thickness"])
        )
        tooth.apply_translation(
            (cx, (tooth_y0 + tooth_y1) / 2.0, f["z_catch"] - prof["catch_thickness"] / 2.0)
        )
        lever = union([arm, boss, tooth])
        lever = difference([lever, bore])
        levers.append(lever)
    return levers


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_b4b_design(
    box: BoxSpec,
    *,
    layout_feature_count: int = 0,
    layout_mode: str = "fused",
    easy_clean: bool = False,
    flat_inside: float = 0.0,
) -> None:
    """Deterministic, actionable checks.  Raises ``ValueError`` on the first
    problem; never swallows a geometry error behind a generic message.

    Runs on the normalised spec - the same one the geometry is built from - so
    it validates the design as it will actually be produced.
    """
    b4b = box.b4b.normalised()
    if not b4b.enabled:
        raise ValueError("validate_b4b_design called on a non-B4B design")
    if layout_feature_count:
        raise ValueError(
            "a B4B interior is reserved for child bins - remove the "
            f"{layout_feature_count} interior part(s) first"
        )
    if layout_mode != "fused":
        raise ValueError("a B4B layout mode must be 'fused'")
    if easy_clean:
        raise ValueError("Easy Clean is incompatible with B4B")
    if flat_inside:
        raise ValueError("the flat-inside band is incompatible with B4B")
    if b4b.label_location == "top" and not b4b.lid:
        raise ValueError("a top label needs the lid enabled")
    if b4b.stacking and not b4b.lid:
        raise ValueError("stacking needs the lid enabled")
    if b4b.secure_lid and not b4b.lid:
        raise ValueError("a secure lid needs the lid enabled")

    cx, cy = b4b_capacity_units(box)
    if cx < 1 or cy < 1:
        raise ValueError("B4B interior is smaller than one child unit even after auto-grow")

    # mating polygon strictly inside the cavity (raises with an actionable message)
    b4b_rail_ring_polygon(box)

    if b4b.secure_lid:
        plan = b4b_hardware_plan(box)
        if plan.hinge_count != 2:
            raise ValueError("a secure B4B lid needs exactly two hinges")
        if plan.hinge_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("hinge pin length did not resolve to an allowed M3 length")
        if plan.latch_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("latch pin length did not resolve to an allowed M3 length")
        if b4b.latch_count == "2" and plan.latch_count_resolved != 2:
            raise ValueError("two latches were requested but do not fit this width")


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def b4b_summary(box: BoxSpec) -> dict:
    """Numeric + formatted readout for the preview API, generation result and
    logging.  Numeric fields are authoritative; strings are convenience."""
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    cx, cy = b4b_capacity_units(box)
    mx, my = b4b_capacity_mm(box)
    plan = b4b_hardware_plan(box)
    summary: dict = {
        "outer_mm": [eff.x, eff.y, eff.z],
        "outer_units": [round(eff.x / GRID_PITCH), round(eff.y / GRID_PITCH)],
        "grew": b4b_grew(box),
        "capacity_units": [cx, cy],
        "capacity_mm": [round(mx, 2), round(my, 2)],
        "max_child_height_mm": round(b4b_max_child_height(box), 2),
        "effective_base_thickness_mm": round(eff.base_thickness, 3),
        "lid": b4b.lid,
        "secure_lid": b4b.secure_lid,
        "lid_headroom_mm": b4b.lid_headroom_mm,
        "stacking": b4b.stacking,
        "label_location": b4b.label_location,
        "label_text": b4b.label_text,
        "capacity_text": (
            f"Fits bins totaling {cx} x {cy} units ({mx:g} x {my:g} mm)"
        ),
        "max_child_height_text": f"Maximum bin height: {b4b_max_child_height(box):g} mm",
    }
    if b4b.secure_lid:
        summary["latch_count"] = plan.latch_count_resolved
        summary["latch_strength"] = b4b.latch_strength
        summary["hardware"] = {
            "hinge_screw": f"M3x{plan.hinge_screw_length_mm}",
            "hinge_qty": plan.hinge_count,
            "latch_screw": f"M3x{plan.latch_screw_length_mm}",
            "latch_qty": plan.latch_count_resolved,
            "nuts": 0,
        }
        summary["hardware_bom"] = plan.screw_bom()
    else:
        summary["latch_count"] = 0
        summary["hardware"] = {"nuts": 0}
        summary["hardware_bom"] = []
    return summary


@lru_cache(maxsize=32)
def _b4b_preview_geometry(box: BoxSpec) -> tuple:
    """Cached: identical B4B designs reuse the same preview mesh walk instead of
    re-running the booleans on every keystroke."""
    from organizer_app import _mesh_preview_geometry  # local: avoid import cycle

    geometry: list = []
    eff = b4b_effective_box(box)
    body = make_b4b_body(box)
    geometry.extend(_mesh_preview_geometry(body, "b4b_rail"))
    if eff.b4b.label_location == "front":
        geometry.extend(
            _mesh_preview_geometry(make_b4b_front_label_plate(box), "b4b_label")
        )
    if eff.b4b.lid:
        lid = make_b4b_lid(box)
        if eff.b4b.label_location == "top" and eff.b4b.label_text.strip():
            lid, _inlay = _apply_top_label(box, lid)
        geometry.extend(_mesh_preview_geometry(lid, "b4b_lid"))
    if eff.b4b.secure_lid:
        for lever in make_b4b_latches(box):
            geometry.extend(_mesh_preview_geometry(lever, "b4b_latch"))
    return tuple(geometry)


def b4b_preview_parts(box: BoxSpec) -> list[tuple[list, str, tuple, int]]:
    """Preview geometry in the ``preview_geometry`` tuple format:
    ``(points, kind, normal, layer)``.  Dimensionally true; microdetail such as
    thread pilots is omitted."""
    return list(_b4b_preview_geometry(box))


# --------------------------------------------------------------------------- #
# labels
# --------------------------------------------------------------------------- #
B4B_TOP_LABEL_CAP_IDEAL = 8.0
B4B_TOP_LABEL_MARGIN = 2.5
B4B_FRONT_LABEL_HEIGHT = 16.0
B4B_FRONT_LABEL_PLATE_T = 1.4
B4B_FRONT_LABEL_CLEAR = 0.35
B4B_FRONT_LABEL_CAP_IDEAL = 6.0


def _fit_text_outline(text: str, avail_w: float, avail_h: float, ideal_cap: float):
    """Largest ``text_outline`` that fits ``avail_w`` x ``avail_h``, scaling the
    cap height down toward the readable minimum.  Raises a clear error if even
    the minimum will not fit."""
    text = text.strip()
    if not text:
        raise ValueError("label text is empty")
    cap = ideal_cap
    while cap >= TEXT_CAP_HEIGHT_MIN - 1e-6:
        outline = text_outline(text, cap)
        minx, miny, maxx, maxy = outline.bounds
        if (maxx - minx) <= avail_w and (maxy - miny) <= avail_h:
            return outline
        cap -= 0.5
    raise ValueError(
        f"the label '{text}' does not fit the available "
        f"{avail_w:.0f} x {avail_h:.0f} mm area even at the minimum size"
    )


def b4b_top_label_outline(box: BoxSpec):
    """Placed outline for the lid-top label: centred in X, ~one third back from
    the front (front is -Y), clear of stacking bosses."""
    eff = b4b_effective_box(box)
    if not eff.b4b.lid:
        raise ValueError("a top label needs the lid enabled")
    # The label lives on the lid, which spans the full outer footprint - not the
    # child field - so it has the whole lid width to work with.
    avail_w = eff.x - 2.0 * B4B_TOP_LABEL_MARGIN
    avail_h = eff.y / 3.0
    label_cy = -eff.y / 6.0
    if eff.b4b.stacking:
        # keep clear of the two rear locator bosses
        centres = _stack_locator_centres(eff)
        rear_y = min(c[1] for c in centres if c[1] > 0)
        avail_h = min(avail_h, (rear_y - B4B_STACK_BOSS_DIAMETER / 2.0 - 2.0) - label_cy)
        avail_h = max(avail_h, 4.0)
    outline = _fit_text_outline(
        eff.b4b.label_text, avail_w, avail_h, B4B_TOP_LABEL_CAP_IDEAL
    )
    return translate_polygon(outline, 0.0, label_cy)


def _apply_top_label(box: BoxSpec, lid: trimesh.Trimesh):
    """Sink the top label flush into the lid; return ``(lid, inlay)`` where the
    inlay is a separate object that fills the pocket."""
    outline = b4b_top_label_outline(box)
    top_z = b4b_lid_underside_z(box) + B4B_LID_SKIN
    pocket = text_prism(outline, top_z, depth=TEXT_DEPTH)
    inlay = text_prism(outline, top_z, depth=TEXT_DEPTH)
    return difference([lid, pocket]), inlay


def b4b_front_label_geometry(box: BoxSpec):
    """``(frame_solid, plate_solid, plate_centre_xyz)`` for the slide-in front
    label.  The frame is unioned into the body; the plate is a separate part
    that slides in from the +X end against an end stop, with a finger notch at
    the -X end.  It sits in the clear band below the latch pads and never
    consumes the child-bin interior.
    """
    eff = b4b_effective_box(box)
    plan = b4b_hardware_plan(box)
    y_wall = -(eff.half_y + WAVE_AMPLITUDE)
    span = _front_span(eff)

    frame_w = span - 4.0
    # vertical band: below the latch pads (or below the rim if passive)
    if plan.latch_count_resolved:
        clear_below = plan.strength_profile["pad_height"] + 2.0
    else:
        clear_below = 4.0
    top_z = eff.z - clear_below
    height = B4B_FRONT_LABEL_HEIGHT
    bottom_z = top_z - height
    if frame_w < 30.0 or bottom_z < 3.0:
        raise ValueError(
            "not enough clear front-wall area for a slide-in label; use a top "
            "label, a shorter box, or turn latches off"
        )

    rail = 1.6                       # channel lip that captures the plate
    channel_t = B4B_FRONT_LABEL_PLATE_T + 2.0 * B4B_FRONT_LABEL_CLEAR
    depth = channel_t + 1.4          # + back wall
    endstop = 2.0

    outer = trimesh.creation.box(extents=(frame_w, depth, height))
    outer.apply_translation((0.0, y_wall - depth / 2.0, (top_z + bottom_z) / 2.0))
    # hollow the channel, open on the +X face, closed by an end stop on -X...
    # actually: end stop on +X far side, slide in from -X (finger) - keep it
    # symmetrical and simple: channel open on -X, stop on +X.
    slot = trimesh.creation.box(
        extents=(frame_w, channel_t, height - 2.0 * rail)
    )
    slot.apply_translation(
        (-endstop,
         y_wall - depth + 1.4 + channel_t / 2.0,
         (top_z + bottom_z) / 2.0)
    )
    frame = difference([outer, slot])

    plate_w = frame_w - endstop - 2.0 * B4B_FRONT_LABEL_CLEAR
    plate_h = height - 2.0 * rail - 2.0 * B4B_FRONT_LABEL_CLEAR
    plate = trimesh.creation.box(
        extents=(plate_w, B4B_FRONT_LABEL_PLATE_T, plate_h)
    )
    # finger notch on the -X insertion edge so it pulls out without tools
    notch = trimesh.creation.box(
        extents=(4.0, B4B_FRONT_LABEL_PLATE_T + 2.0, plate_h * 0.5)
    )
    notch.apply_translation((-plate_w / 2.0 + 1.0, 0.0, 0.0))
    plate = difference([plate, notch])
    if eff.b4b.label_text.strip():
        outline = _fit_text_outline(
            eff.b4b.label_text, plate_w - 8.0, plate_h - 2.0, B4B_FRONT_LABEL_CAP_IDEAL
        )
        engrave = text_prism(outline, B4B_FRONT_LABEL_PLATE_T / 2.0, depth=TEXT_DEPTH)
        engrave.apply_transform(
            trimesh.transformations.rotation_matrix(-math.pi / 2.0, (1.0, 0.0, 0.0))
        )
        engrave.apply_translation(
            (0.0, B4B_FRONT_LABEL_PLATE_T / 2.0 - TEXT_DEPTH / 2.0, 0.0)
        )
        plate = difference([plate, engrave])

    plate_centre = (
        -endstop / 2.0,
        y_wall - depth + 1.4 + B4B_FRONT_LABEL_CLEAR + B4B_FRONT_LABEL_PLATE_T / 2.0,
        (top_z + bottom_z) / 2.0,
    )
    return frame, plate, plate_centre


def make_b4b_front_label_plate(box: BoxSpec) -> trimesh.Trimesh:
    """The slide-in plate alone, positioned in assembly space."""
    _frame, plate, centre = b4b_front_label_geometry(box)
    return translated(plate, centre)


# --------------------------------------------------------------------------- #
# print orientation + generation parts
# --------------------------------------------------------------------------- #
def _to_print_orientation(mesh: trimesh.Trimesh, kind: str) -> trimesh.Trimesh:
    """Assembly-space -> a support-minimising print pose, then dropped to z=0.

    Assembly and print transforms are kept separate: mating coordinates are
    never damaged to make a part lie flat.
    """
    m = mesh.copy()
    if kind == "lid":
        # print outer-face up: keeps the top-label surface and the stacking
        # bosses on the upward face; the short skirt and knuckle tabs point down
        # and take a little support or a brim
        pass
    elif kind == "latch":
        # lay the lever on its broad face
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
        )
    # kind == "body" / "plate": already a good pose
    m.apply_translation((0.0, 0.0, -float(m.bounds[0][2])))
    # recentre X/Y on the origin for a tidy plate
    c = m.bounds.mean(axis=0)
    m.apply_translation((-c[0], -c[1], 0.0))
    return m


def b4b_build_parts(box: BoxSpec) -> list[tuple[str, trimesh.Trimesh]]:
    """Every printable B4B object, named, in print orientation.  Screws are
    never emitted as geometry."""
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    validate_b4b_design(box)

    parts: list[tuple[str, trimesh.Trimesh]] = []
    body = make_b4b_body(box)
    front_inlay = None
    if b4b.label_location == "front":
        frame, _plate, _c = b4b_front_label_geometry(box)
        body = union([body, frame])
    parts.append(("B4B Body", _to_print_orientation(body, "body")))

    if b4b.lid:
        lid = make_b4b_lid(box)
        top_inlay = None
        if b4b.label_location == "top" and b4b.label_text.strip():
            lid, top_inlay = _apply_top_label(box, lid)
        parts.append(("B4B Lid", _to_print_orientation(lid, "lid")))
        if top_inlay is not None:
            parts.append(
                ("B4B Top Label", _to_print_orientation(top_inlay, "lid"))
            )

    if b4b.secure_lid:
        for i, lever in enumerate(make_b4b_latches(box), start=1):
            parts.append((f"B4B Latch {i}", _to_print_orientation(lever, "latch")))

    if b4b.label_location == "front":
        _frame, plate, centre = b4b_front_label_geometry(box)
        parts.append(
            ("B4B Front Label", _to_print_orientation(translated(plate, centre), "plate"))
        )
    return parts
