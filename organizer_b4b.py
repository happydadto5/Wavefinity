"""B4B (Bin for Bins) - a Wavefinity carrying-case mode.

For B4B, ``BoxSpec.x/y`` are the requested child-bin field dimensions.  The
authoritative inner mating wall is built around that exact field and the case
wall grows outward from it.  The physical case footprint is therefore derived
and intentionally does not promise ordinary external Wavefinity interlock.

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
from shapely.geometry import Point, Polygon
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
    wave_value,
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
# B4B wall corner treatment.  The child-compatible wavy faces are never
# buffered; only their corner joins receive this small printable rounding.
B4B_WALL_CORNER_FILLET = 0.6

# Effective base / stacking
B4B_MIN_FLOOR_SKIN = 0.8        # printable floor left under a stack recess
B4B_STACK_RECESS_DEPTH = 2.0    # female recess depth == male boss height
B4B_STACK_BOSS_DIAMETER = 5.0
B4B_STACK_FEMALE_RADIAL_CLEARANCE = 0.25
B4B_STACK_SOCKET_DEPTH = 1.6
B4B_STACK_SOCKET_INTERFERENCE = 0.08
B4B_STACK_INSET_FRACTION = 0.16  # locator centre inset from each outer edge
B4B_STACK_INSET_MIN = 4.0
B4B_STACK_MIN_FOOTPRINT_UNITS = 3  # smallest box that still gets four locators

# Lid
B4B_LID_SKIN = 1.6              # lid top plate thickness
B4B_LID_SKIRT_WALL = 2.0       # locating skirt wall thickness
B4B_LID_SEAT_CLEARANCE = 0.30  # lateral clearance, skirt inner face to body
B4B_LID_SKIRT_LAP = 4.0        # how far the skirt laps down past the body rim
# A latched lid needs a printable body wall below its latch pad, independent
# of the selected latch strength.
B4B_LATCHED_MIN_HEIGHT = 16.0

# M3 hardware (no nuts, no inserts)
B4B_M3_NOMINAL = 3.0
B4B_M3_CLEAR_BORE = 3.4        # rotating knuckle / pivot clearance hole
B4B_M3_PILOT = 2.6            # thread-forming terminal pilot
B4B_M3_THREAD_ENGAGE_MIN = 3.0
B4B_M3_HEAD_CLEAR = 6.0
B4B_SCREW_LENGTHS = (12, 16, 20, 25, 30)   # allowed kit lengths, mm
B4B_M3_MAX_PROTRUSION = 6.0
B4B_M3_HEAD_SEAT = 0.0        # head bears directly on the near ear face

# Print-bed layout: parts are packed in a row, none overlapping.
B4B_PRINT_PART_GAP = 8.0

# Stacking boss self-locating lead-in (a real printed taper, not a claim).
B4B_STACK_BOSS_CHAMFER = 0.6

# Hinges (exactly two, rear wall)
B4B_HINGE_COUNT = 2
B4B_HINGE_WIDTH_FRACTION = 0.16
# Each of the three knuckle segments is (hinge_width/3 - axial_gap) wide, and
# the outer (far) segment is the printed thread-forming lug.  The minimum is set
# so that lug is never thinner than B4B_M3_THREAD_ENGAGE_MIN:
#   (12/3) - 0.35 = 3.65 mm >= 3.0 mm.
B4B_HINGE_WIDTH_MIN = 10.0
B4B_HINGE_WIDTH_MAX = 24.0
B4B_HINGE_KNUCKLE_RADIUS = 3.1   # encloses the clear bore with a printable wall
B4B_HINGE_AXIAL_GAP = 0.20       # running gap between body and lid knuckles
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

# Minimum requested child-field widths.  Hardware reinforcement grows outward;
# it may grow the child field only when the hardware genuinely needs more span.
B4B_SECURE_MIN_FIELD_X = 3 * GRID_PITCH
B4B_TWO_LATCH_MIN_FIELD_X = 5 * GRID_PITCH

_EPS = 1e-6


# --------------------------------------------------------------------------- #
# child-field semantics + derived physical case
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BLayout:
    """One source of truth for every derived B4B plan-view datum."""

    target_child_x: float
    target_child_y: float
    inner_half_x: float
    inner_half_y: float
    outer_half_x: float
    outer_half_y: float
    inner_mating_polygon: Polygon
    outer_structural_polygon: Polygon
    case_bounds: tuple[float, float, float, float]

    @property
    def case_size(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.case_bounds
        return x1 - x0, y1 - y0

    def front_wall_y(self, x: float) -> float:
        return -self.outer_half_y + wave_value(x)

    def rear_wall_y(self, x: float) -> float:
        return self.outer_half_y + wave_value(x)


@lru_cache(maxsize=64)
def b4b_layout(box: BoxSpec) -> B4BLayout:
    """Resolve the exact child field and its outward-built case wall."""
    eff = b4b_effective_box(box)
    inner_half_x = eff.x / 2.0 + WAVE_MATING_GAP / 2.0
    inner_half_y = eff.y / 2.0 + WAVE_MATING_GAP / 2.0
    inner_tx = inner_half_x - CORNER_INSET
    inner_ty = inner_half_y - CORNER_INSET
    inner = Polygon(_wall_points(inner_half_x, inner_half_y, inner_tx, inner_ty))
    if not inner.is_valid:
        inner = inner.buffer(0)
    if not isinstance(inner, Polygon) or not inner.is_valid:
        raise RuntimeError("B4B inner mating outline is not a valid single polygon")
    inner = _rounded(inner, B4B_WALL_CORNER_FILLET)

    outer_half_x = inner_half_x + eff.wall_depth
    outer_half_y = inner_half_y + eff.wall_depth
    outer_tx = outer_half_x - CORNER_INSET
    outer_ty = outer_half_y - CORNER_INSET
    outer = Polygon(_wall_points(outer_half_x, outer_half_y, outer_tx, outer_ty))
    if not outer.is_valid:
        outer = outer.buffer(0)
    if not isinstance(outer, Polygon) or not outer.is_valid:
        raise RuntimeError("B4B outer structural outline is not a valid single polygon")
    outer = _rounded(outer, B4B_WALL_CORNER_FILLET)
    if not outer.buffer(_EPS).contains(inner):
        raise RuntimeError("B4B outward wall does not contain its inner mating face")
    return B4BLayout(
        target_child_x=eff.x,
        target_child_y=eff.y,
        inner_half_x=inner_half_x,
        inner_half_y=inner_half_y,
        outer_half_x=outer_half_x,
        outer_half_y=outer_half_y,
        inner_mating_polygon=inner,
        outer_structural_polygon=outer,
        case_bounds=tuple(float(v) for v in outer.bounds),
    )


def b4b_capacity_units(box: BoxSpec) -> tuple[int, int]:
    """Exact requested child-field units after any visible auto-growth."""
    eff = b4b_effective_box(box)
    return round(eff.x / GRID_PITCH), round(eff.y / GRID_PITCH)


def b4b_capacity_mm(box: BoxSpec) -> tuple[float, float]:
    eff = b4b_effective_box(box)
    return eff.x, eff.y


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

    Identical to the user's child-field request except for genuinely required
    hardware/stacking growth and any stacking base
    reinforcement.  Easy Clean and the flat-inside band are forced off because
    they alter the floor/perimeter the child bins must seat on.
    """
    b4b = box.b4b.normalised()
    x, y, z = box.x, box.y, box.z

    # Secure-lid hardware needs enough requested field width for two compact
    # rear hinges.  The exterior reinforcement itself grows outward.
    if b4b.secure_lid:
        while x < B4B_SECURE_MIN_FIELD_X - _EPS:
            x += GRID_PITCH
        if b4b.latch_count == "2":
            while x < B4B_TWO_LATCH_MIN_FIELD_X - _EPS:
                x += GRID_PITCH
        z = max(z, B4B_LATCHED_MIN_HEIGHT)

    # Stacking needs a footprint wide enough that the four corner locators do
    # not run into each other (see _stack_locator_centres): enforce the minimum
    # so B4B_STACK_MIN_FOOTPRINT_UNITS is a live constraint, not a comment.
    if b4b.stacking and b4b.lid:
        floor = B4B_STACK_MIN_FOOTPRINT_UNITS * GRID_PITCH
        x = max(x, floor)
        y = max(y, floor)

    base_thickness = b4b_effective_base_thickness(box)
    return replace(
        box,
        x=x,
        y=y,
        z=z,
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
        and math.isclose(eff.z, box.z)
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
# authoritative inner mating wall
# --------------------------------------------------------------------------- #
def b4b_mating_polygon(box: BoxSpec) -> Polygon:
    """Inward-facing wave the child field's perimeter bins mate to.

    Built with the *same* ``wave_value`` phase/amplitude/wavelength as every
    Wavefinity wall (via :func:`_wall_points`), not a Shapely buffer of the
    child field - a perpendicular buffer would break the phase relationship.
    Baseline half-extent per axis is ``C*G/2 + gap/2``, exactly one axis gap
    outside a child field whose perimeter wall baseline is ``C*G/2 - gap/2``.
    """
    return b4b_layout(box).inner_mating_polygon


def b4b_outer_polygon(box: BoxSpec) -> Polygon:
    return b4b_layout(box).outer_structural_polygon


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
    catch_screw_length_mm: int
    catch_axis_y: float
    catch_axis_z: float
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
                f"{self.latch_count_resolved} x M3x{self.latch_screw_length_mm} latch pivots"
            )
            lines.append(
                f"{self.latch_count_resolved} x M3x{self.catch_screw_length_mm} catch pins"
            )
        lines.append("No nuts")
        return lines


def _screw_for_stack(clear_span_mm: float, lug_thickness_mm: float, what: str) -> int:
    """Authoritative kit-screw choice for a pivot: the screw enters at the
    head-bearing face, crosses ``clear_span_mm`` of clearance-bored material
    (ears/knuckles + running gaps), then thread-forms into a terminal lug of
    ``lug_thickness_mm``.

    Returns the smallest ``B4B_SCREW_LENGTHS`` entry that gives at least
    ``B4B_M3_THREAD_ENGAGE_MIN`` of thread bite without exceeding
    ``B4B_M3_MAX_PROTRUSION`` past the far face of the lug.  Raises with an
    actionable message when the kit has no such screw - never a silent
    over-long fallback that validation cannot see.

    Real thread engagement can never exceed the physical lug thickness, so a
    lug thinner than the minimum is a constant/geometry bug and is rejected
    here rather than papered over by a long screw.
    """
    if lug_thickness_mm + _EPS < B4B_M3_THREAD_ENGAGE_MIN:
        raise ValueError(
            f"the {what} terminal lug is only {lug_thickness_mm:.2f} mm thick - "
            f"less than the {B4B_M3_THREAD_ENGAGE_MIN:.1f} mm minimum thread "
            f"engagement; widen the hardware"
        )
    need_min = clear_span_mm + B4B_M3_THREAD_ENGAGE_MIN
    for length in B4B_SCREW_LENGTHS:
        if length + _EPS < need_min:
            continue
        protrusion = length - clear_span_mm - lug_thickness_mm
        if protrusion <= B4B_M3_MAX_PROTRUSION + _EPS:
            return length
    allowed = ", ".join(f"M3x{n}" for n in B4B_SCREW_LENGTHS)
    raise ValueError(
        f"no kit screw ({allowed}) spans the {what} pivot: needs "
        f"{need_min:.1f} mm for {B4B_M3_THREAD_ENGAGE_MIN:.1f} mm of thread "
        f"engagement across a {clear_span_mm:.1f} mm clearance stack; "
        f"adjust the hardware profile or the B4B size"
    )


def _latch_lug_thickness(ear_thickness: float) -> float:
    """Terminal (far) latch-ear thickness: the profile pad wall, but never less
    than enough for the minimum M3 thread engagement plus a printable skin."""
    return max(ear_thickness, B4B_M3_THREAD_ENGAGE_MIN + 1.0)


def _hinge_screw_stack(hinge_width: float) -> tuple[float, float]:
    """(clearance span, terminal-lug thickness) for a three-knuckle hinge pin,
    mirroring the geometry built by :func:`_hinge_body_parts`."""
    seg = hinge_width / 3.0
    kw = seg - B4B_HINGE_AXIAL_GAP
    clear_span = 2.0 * kw + 2.0 * B4B_HINGE_AXIAL_GAP   # near knuckle + gap + centre + gap
    return clear_span, kw


def _latch_screw_stack(latch_width: float, ear_thickness: float) -> tuple[float, float]:
    """(clearance span, terminal-lug thickness) for a latch pivot pin,
    mirroring the ears in :func:`_latch_lid_parts` and the lever in
    :func:`make_b4b_latches`.  The head bears on the near-ear outer face; the
    clearance stack is near ear + running gap + lever + running gap; the screw
    then thread-forms into the far lug.
    """
    clear_span = ear_thickness + latch_width + 2.0 * B4B_HINGE_AXIAL_GAP
    return clear_span, _latch_lug_thickness(ear_thickness)


def _front_span(box: BoxSpec) -> float:
    """Usable straight run of the front wall between corner tangents."""
    layout = b4b_layout(box)
    return 2.0 * (layout.outer_half_x - CORNER_INSET)


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
            catch_screw_length_mm=0,
            catch_axis_y=0.0,
            catch_axis_z=0.0,
            strength_profile=profile,
        )

    layout = b4b_layout(box)
    case_x, _case_y = layout.case_size
    # Hinges: two, symmetric, near the quarter points, clamped to corner keep-outs.
    hinge_width = min(
        B4B_HINGE_WIDTH_MAX,
        max(B4B_HINGE_WIDTH_MIN, B4B_HINGE_WIDTH_FRACTION * case_x),
    )
    limit = layout.outer_half_x - CORNER_INSET - hinge_width / 2.0
    centre = min(max(eff.x / 4.0, hinge_width / 2.0), max(limit, hinge_width / 2.0))
    hinge_centers_x = (-centre, centre)
    rear_faces = [
        layout.rear_wall_y(cx + dx)
        for cx in hinge_centers_x
        for dx in (-hinge_width / 2.0, 0.0, hinge_width / 2.0)
    ]
    hinge_axis_y = max(rear_faces) + B4B_HINGE_KNUCKLE_RADIUS + 0.45
    # The round barrel is exactly flush with the broad lid top plane.
    hinge_axis_z = (
        b4b_lid_underside_z(box) + B4B_LID_SKIN - B4B_HINGE_KNUCKLE_RADIUS
    )
    h_span, h_lug = _hinge_screw_stack(hinge_width)
    hinge_screw = _screw_for_stack(h_span, h_lug, "hinge")

    # Latches: front, 1 / 2 / Auto.
    latch_width = min(
        B4B_LATCH_WIDTH_MAX,
        max(B4B_LATCH_WIDTH_MIN, B4B_LATCH_WIDTH_FRACTION * case_x),
    )
    span = _front_span(box)
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
    l_span, l_lug = _latch_screw_stack(latch_width, profile["pad_wall"])
    latch_screw = _screw_for_stack(l_span, l_lug, "latch")
    lever_w = latch_width - 2.0 * B4B_HINGE_AXIAL_GAP
    catch_ear_t = max(profile["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0)
    catch_span = catch_ear_t + lever_w + 2.0 * B4B_HINGE_AXIAL_GAP
    catch_screw = _screw_for_stack(catch_span, catch_ear_t, "catch")
    front_faces = [
        layout.front_wall_y(cx + dx)
        for cx in latch_centers_x
        for dx in (-latch_width / 2.0, 0.0, latch_width / 2.0)
    ]
    hook_outer_r = B4B_M3_NOMINAL / 2.0 + 0.35 + 1.6
    catch_axis_y = min(front_faces) - hook_outer_r - 0.45
    catch_axis_z = eff.z - max(6.5, profile["pad_height"] * 0.65)

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
        catch_screw_length_mm=catch_screw,
        catch_axis_y=catch_axis_y,
        catch_axis_z=catch_axis_z,
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
    """Female locator recesses cut into the B4B underside.

    The cutter's upper face terminates at *exactly* ``B4B_STACK_RECESS_DEPTH``;
    all boolean overshoot is below the exterior bottom (z=0).  So the finished
    recess floor sits at z = ``B4B_STACK_RECESS_DEPTH`` and the remaining floor
    skin is exactly ``eff.base_thickness - B4B_STACK_RECESS_DEPTH``.
    """
    eff = b4b_effective_box(box)
    female_r = B4B_STACK_BOSS_DIAMETER / 2.0 + B4B_STACK_FEMALE_RADIAL_CLEARANCE
    overshoot = 0.5
    height = B4B_STACK_RECESS_DEPTH + overshoot
    solids: list[trimesh.Trimesh] = []
    for cx, cy in _stack_locator_centres(eff):
        cyl = trimesh.creation.cylinder(radius=female_r, height=height, sections=48)
        cyl.apply_translation((cx, cy, B4B_STACK_RECESS_DEPTH - height / 2.0))
        solids.append(cyl)
    return solids


def make_b4b_body(box: BoxSpec) -> trimesh.Trimesh:
    """Flat-floor child field inside a wall grown outward from its mating face."""
    eff = b4b_effective_box(box)
    floor_z = eff.base_thickness
    plan = b4b_hardware_plan(box)
    layout = b4b_layout(box)

    envelope = _extrude_polygon(layout.outer_structural_polygon, eff.z)
    cavity = _extrude_polygon(
        layout.inner_mating_polygon, eff.z - floor_z + 1.0
    )
    cavity.apply_translation((0.0, 0.0, floor_z))
    body = difference([envelope, cavity])

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

    The skirt hangs underneath the lid and sits inside the body wall.  Both
    faces are therefore inset from the body's outer structural outline; this
    keeps the locating feature from enlarging the lid footprint."""
    clr = B4B_LID_SEAT_CLEARANCE
    layout = b4b_layout(eff)
    outer = layout.outer_structural_polygon.buffer(-clr)
    inner = outer.buffer(-B4B_LID_SKIRT_WALL)
    if outer.is_empty or inner.is_empty:
        raise RuntimeError("B4B lid locating skirt collapsed inside the body wall")
    if not isinstance(outer, Polygon) or not isinstance(inner, Polygon):
        raise RuntimeError("B4B lid locating skirt must remain a single polygon")
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
    layout = b4b_layout(eff)

    # the plate reaches a little below the underside datum so it fuses into the
    # skirt, hinge tabs and latch ears as one connected solid
    plate = _extrude_polygon(layout.outer_structural_polygon, B4B_LID_SKIN + 0.8)
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
    case_x, _case_y = layout.case_size
    side_clip = trimesh.creation.box(
        extents=(case_x * 4.0,
                 2.0 * (layout.outer_half_y - CORNER_INSET - 2.0),
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
        lid = difference([lid, *_stack_lid_sockets(box)])

    lid.remove_unreferenced_vertices()
    lid.merge_vertices()
    return lid


def _chamfered_boss(radius: float, height: float, chamfer: float) -> trimesh.Trimesh:
    """A cylinder with a conical lead-in on its free (top) end, built by
    revolving an ``(r, z)`` profile.  The taper is what lets a stack self-centre
    into the female recess without a snap."""
    chamfer = max(0.0, min(chamfer, radius - 0.5, height - 0.4))
    profile = np.array([
        [0.0, 0.0],
        [radius, 0.0],
        [radius, height - chamfer],
        [radius - chamfer, height],
        [0.0, height],
    ])
    boss = trimesh.creation.revolve(profile, sections=48)
    if not boss.is_volume:
        boss = trimesh.creation.cylinder(radius=radius, height=height, sections=48)
        boss.apply_translation((0.0, 0.0, height / 2.0))
    return boss


def _stack_lid_sockets(box: BoxSpec) -> list[trimesh.Trimesh]:
    eff = b4b_effective_box(box)
    top_z = b4b_lid_underside_z(box) + B4B_LID_SKIN
    radius = B4B_STACK_BOSS_DIAMETER / 2.0 - B4B_STACK_SOCKET_INTERFERENCE
    solids: list[trimesh.Trimesh] = []
    for cx, cy in _stack_locator_centres(eff):
        cutter = trimesh.creation.cylinder(
            radius=radius, height=B4B_STACK_SOCKET_DEPTH + 0.5, sections=48
        )
        cutter.apply_translation(
            (cx, cy, top_z - B4B_STACK_SOCKET_DEPTH / 2.0 + 0.25)
        )
        solids.append(cutter)
    return solids


def _stack_pegs(box: BoxSpec) -> list[trimesh.Trimesh]:
    """Four separately printed pegs, shown installed in assembly-space preview."""
    eff = b4b_effective_box(box)
    top_z = b4b_lid_underside_z(box) + B4B_LID_SKIN
    total_h = B4B_STACK_SOCKET_DEPTH + B4B_STACK_RECESS_DEPTH
    solids: list[trimesh.Trimesh] = []
    for cx, cy in _stack_locator_centres(eff):
        peg = _chamfered_boss(
            B4B_STACK_BOSS_DIAMETER / 2.0,
            total_h,
            B4B_STACK_BOSS_CHAMFER,
        )
        peg.apply_translation((cx, cy, top_z - B4B_STACK_SOCKET_DEPTH))
        solids.append(peg)
    return solids


# --------------------------------------------------------------------------- #
# hinge geometry (integrated knuckles + clean round M3 bore)
# --------------------------------------------------------------------------- #
def _round_profile_yz(radius: float) -> Polygon:
    return Polygon(
        [
            (radius * math.cos(a), radius * math.sin(a))
            for a in np.linspace(0.0, 2.0 * math.pi, 60, endpoint=False)
        ]
    )


def _x_cylinder(radius: float, length: float) -> trimesh.Trimesh:
    """A bore/knuckle solid whose axis is world X, centred on the origin."""
    return _extrude_yz_profile(_round_profile_yz(radius), length)


def _hinge_seg(plan: B4BHardwarePlan) -> float:
    return plan.hinge_width / 3.0


def _knuckle(cx: float, axis_y: float, axis_z: float, width: float,
             radius: float) -> trimesh.Trimesh:
    k = _x_cylinder(radius, width)
    k.apply_translation((cx, axis_y, axis_z))
    return k


def _hinge_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Compact upper-wall rear knuckles on >=45-degree printable gussets."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = B4B_HINGE_KNUCKLE_RADIUS
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        for side, bore_r, bore_len_frac in (
            (-1.0, B4B_M3_CLEAR_BORE / 2.0, 1.4),   # near: clearance, over-long
            (+1.0, B4B_M3_PILOT / 2.0, 1.0),        # far: pilot, contained
        ):
            kx = cx + side * seg
            wall_y = layout.rear_wall_y(kx)
            root_y = wall_y - min(0.6, eff.wall_depth * 0.55)
            lower_touch_y = plan.hinge_axis_y - 0.65 * r
            outward_run = max(0.1, lower_touch_y - root_y)
            root_z = max(
                eff.z - 7.0,
                plan.hinge_axis_z - r - outward_run / math.tan(math.radians(50.0)),
            )
            gusset_profile = Polygon([
                (root_y, root_z),
                (root_y, eff.z + 0.35),
                (plan.hinge_axis_y + r, plan.hinge_axis_z + 0.45 * r),
                (plan.hinge_axis_y + 0.35 * r, plan.hinge_axis_z - 0.75 * r),
                (lower_touch_y, plan.hinge_axis_z - r),
            ])
            gusset = _extrude_yz_profile(gusset_profile, kw)
            gusset.apply_translation((kx, 0.0, 0.0))
            tower = union([
                gusset,
                _knuckle(kx, plan.hinge_axis_y, plan.hinge_axis_z, kw, r),
            ])
            bore = _x_cylinder(bore_r, seg * bore_len_frac + 1.0)
            bx = kx if side > 0 else kx - 0.5
            bore.apply_translation((bx, plan.hinge_axis_y, plan.hinge_axis_z))
            parts.append(difference([tower, bore]))
    return parts


def _hinge_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """The centre knuckle per hinge, hanging from the lid rear edge to the pin
    axis and bored for clearance.  Distinct solid sharing the pin with the two
    body towers."""
    underside_z = b4b_lid_underside_z(box)
    layout = b4b_layout(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = B4B_HINGE_KNUCKLE_RADIUS
    z_hi = underside_z + B4B_LID_SKIN
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        lid_back = (
            layout.rear_wall_y(cx) + B4B_LID_SEAT_CLEARANCE
            + B4B_LID_SKIRT_WALL
        )
        root_y = lid_back - 0.5
        tab_profile = Polygon([
            (root_y, underside_z - 0.8),
            (root_y, z_hi),
            (plan.hinge_axis_y, z_hi),
            (plan.hinge_axis_y + r, plan.hinge_axis_z),
            (plan.hinge_axis_y, plan.hinge_axis_z - r),
        ])
        tab_bridge = _extrude_yz_profile(tab_profile, kw)
        tab_bridge.apply_translation((cx, 0.0, 0.0))
        tab = union([
            tab_bridge,
            _knuckle(cx, plan.hinge_axis_y, plan.hinge_axis_z, kw, r),
        ])
        bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, kw + 1.0)
        bore.apply_translation((cx, plan.hinge_axis_y, plan.hinge_axis_z))
        parts.append(difference([tab, bore]))
    return parts


# --------------------------------------------------------------------------- #
# latch geometry: lid lever on an M3 pivot, engaging a second M3 cross-pin in
# compact body receiver ears.  All roots follow the derived local front wall.
# --------------------------------------------------------------------------- #
def _latch_frame(eff: BoxSpec, plan: B4BHardwarePlan) -> dict:
    prof = plan.strength_profile
    underside_z = b4b_lid_underside_z_from_eff(eff)
    hook_outer_r = B4B_M3_NOMINAL / 2.0 + 0.35 + max(1.4, prof["hook_depth"] * 0.6)
    pivot_r = B4B_M3_CLEAR_BORE / 2.0 + 1.6
    axis_y = plan.catch_axis_y - (
        hook_outer_r - prof["lever_thickness"] / 2.0 + 0.5
    )
    return {
        "prof": prof,
        "axis_y": axis_y,
        "axis_z": underside_z + B4B_LID_SKIN - pivot_r,
        "catch_axis_y": plan.catch_axis_y,
        "catch_axis_z": plan.catch_axis_z,
        "hook_outer_r": hook_outer_r,
        "underside_z": underside_z,
        "ear_t": prof["pad_wall"],
    }


def _latch_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two small upper-wall ears carrying the metal M3 catch cross-pin."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    f = _latch_frame(eff, plan)
    prof = f["prof"]
    parts: list[trimesh.Trimesh] = []
    lever_w = plan.latch_width - 2.0 * B4B_HINGE_AXIAL_GAP
    ear_t = max(prof["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0)
    boss_r = B4B_M3_CLEAR_BORE / 2.0 + 1.6
    for cx in plan.latch_centers_x:
        inner_face = lever_w / 2.0 + B4B_HINGE_AXIAL_GAP
        for side, bore_r, width in (
            (-1.0, B4B_M3_CLEAR_BORE / 2.0, ear_t),
            (+1.0, B4B_M3_PILOT / 2.0, ear_t),
        ):
            ex = cx + side * (inner_face + width / 2.0)
            wall_y = layout.front_wall_y(ex)
            root_y = wall_y + min(0.6, eff.wall_depth * 0.55)
            root_z = max(
                eff.z - 8.0,
                plan.catch_axis_z - boss_r
                - (root_y - plan.catch_axis_y) / math.tan(math.radians(50.0)),
            )
            support_profile = Polygon([
                (root_y, eff.z + 0.25),
                (root_y, root_z),
                (plan.catch_axis_y + 0.65 * boss_r, plan.catch_axis_z - boss_r),
                (plan.catch_axis_y - boss_r, plan.catch_axis_z - 0.45 * boss_r),
                (plan.catch_axis_y - boss_r, plan.catch_axis_z + boss_r),
            ])
            support = _extrude_yz_profile(support_profile, width)
            support.apply_translation((ex, 0.0, 0.0))
            boss = _knuckle(
                ex, plan.catch_axis_y, plan.catch_axis_z, width, boss_r
            )
            ear = union([support, boss])
            bore = _x_cylinder(bore_r, width + 2.0)
            bore.apply_translation((ex, plan.catch_axis_y, plan.catch_axis_z))
            parts.append(difference([ear, bore]))
    return parts


def _latch_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two pivot ears per latch, hanging from the lid front to the pivot axis."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    f = _latch_frame(eff, plan)
    parts: list[trimesh.Trimesh] = []
    ear_t = f["ear_t"]
    lug_t = _latch_lug_thickness(ear_t)   # far ear is a real thread-forming lug
    top = f["underside_z"] + B4B_LID_SKIN
    boss_r = B4B_M3_CLEAR_BORE / 2.0 + 1.6
    for cx in plan.latch_centers_x:
        inner_face = plan.latch_width / 2.0 + B4B_HINGE_AXIAL_GAP
        # -X ear: head bearing + clearance bore, runs right through.
        near_t = ear_t
        near_x = cx - (inner_face + near_t / 2.0)
        near_wall = (
            layout.front_wall_y(near_x) - B4B_LID_SEAT_CLEARANCE
            - B4B_LID_SKIRT_WALL
        )
        near_profile = Polygon([
            (near_wall + 0.5, f["underside_z"] - 0.8),
            (near_wall + 0.5, top),
            (f["axis_y"] - boss_r, top),
            (f["axis_y"] - boss_r, f["axis_z"] - boss_r),
            (f["axis_y"] + 0.5 * boss_r, f["axis_z"] - boss_r),
        ])
        near = _extrude_yz_profile(near_profile, near_t)
        near.apply_translation((near_x, 0.0, 0.0))
        near = union([near, _knuckle(near_x, f["axis_y"], f["axis_z"], near_t, boss_r)])
        near_bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, near_t + 2.0)
        near_bore.apply_translation((near_x, f["axis_y"], f["axis_z"]))
        parts.append(difference([near, near_bore]))
        # +X ear: terminal thread-forming lug, always at least the minimum
        # thread engagement thick; pilot bored right through so the screw
        # self-retains with no nut.
        far_x = cx + inner_face + lug_t / 2.0
        far_wall = (
            layout.front_wall_y(far_x) - B4B_LID_SEAT_CLEARANCE
            - B4B_LID_SKIRT_WALL
        )
        far_profile = Polygon([
            (far_wall + 0.5, f["underside_z"] - 0.8),
            (far_wall + 0.5, top),
            (f["axis_y"] - boss_r, top),
            (f["axis_y"] - boss_r, f["axis_z"] - boss_r),
            (f["axis_y"] + 0.5 * boss_r, f["axis_z"] - boss_r),
        ])
        far = _extrude_yz_profile(far_profile, lug_t)
        far.apply_translation((far_x, 0.0, 0.0))
        far = union([far, _knuckle(far_x, f["axis_y"], f["axis_z"], lug_t, boss_r)])
        pilot = _x_cylinder(B4B_M3_PILOT / 2.0, lug_t + 2.0)
        pilot.apply_translation((far_x, f["axis_y"], f["axis_z"]))
        parts.append(difference([far, pilot]))
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
        pivot_r = B4B_M3_CLEAR_BORE / 2.0 + 1.6
        hook_inner_r = B4B_M3_NOMINAL / 2.0 + 0.35
        hook_outer_r = f["hook_outer_r"]
        pivot_disc = Point(f["axis_y"], f["axis_z"]).buffer(pivot_r, quad_segs=24)
        hook_disc = Point(f["catch_axis_y"], f["catch_axis_z"]).buffer(
            hook_outer_r, quad_segs=24
        )
        profile = pivot_disc.union(hook_disc).convex_hull
        hook_bore = Point(f["catch_axis_y"], f["catch_axis_z"]).buffer(
            hook_inner_r, quad_segs=24
        )
        opening = Polygon([
            (f["catch_axis_y"], f["catch_axis_z"] - hook_inner_r * 0.7),
            (f["catch_axis_y"] + hook_outer_r * 2.5, f["catch_axis_z"] - hook_inner_r * 0.7),
            (f["catch_axis_y"] + hook_outer_r * 2.5, f["catch_axis_z"] + hook_inner_r * 0.7),
            (f["catch_axis_y"], f["catch_axis_z"] + hook_inner_r * 0.7),
        ])
        profile = profile.difference(hook_bore.union(opening))
        lever = _extrude_yz_profile(profile, lever_w)
        lever.apply_translation((cx, 0.0, 0.0))
        bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, lever_w + 4.0)
        bore.apply_translation((cx, f["axis_y"], f["axis_z"]))
        lever = difference([lever, bore])
        levers.append(lever)
    return levers


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _sweep_intersection_cc(
    moving: trimesh.Trimesh,
    fixed: trimesh.Trimesh,
    axis_y: float,
    axis_z: float,
    angles_deg: tuple[float, ...],
) -> float:
    """Largest overlap volume (cc) between ``moving`` (rotated about the world-X
    line through ``(axis_y, axis_z)`` by each angle) and ``fixed``.

    A pose whose intersection cannot be computed is NOT treated as zero overlap
    (that would be fail-open): the whole check raises so the caller reports an
    unverifiable design rather than a false all-clear.
    """
    from organizer_engine import intersection_volume

    worst = 0.0
    for deg in angles_deg:
        m = moving.copy()
        m.apply_translation((0.0, -axis_y, -axis_z))
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.radians(deg), (1.0, 0.0, 0.0))
        )
        m.apply_translation((0.0, axis_y, axis_z))
        try:
            worst = max(worst, intersection_volume(m, fixed) / 1000.0)
        except Exception as exc:
            raise ValueError(
                f"could not verify the swept clearance at {deg:g} deg "
                f"({exc}); the B4B mechanics could not be validated"
            ) from exc
    return worst


def _validate_b4b_mechanics(box: BoxSpec) -> None:
    """Sampled moving-part and thread-retention checks - run at generation time,
    not on every keystroke.  Deterministic (fixed sample angles); not a full
    rigid-body simulator."""
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    plan = b4b_hardware_plan(box)

    # 1-2. printed terminal-lug thread engagement + screw protrusion.
    # Physical engagement is min(screw beyond the clearance stack, lug thickness)
    # - a screw longer than the lug threads only as far as the lug is thick.
    if b4b.secure_lid:
        for what, (span, lug), screw in (
            ("hinge", _hinge_screw_stack(plan.hinge_width), plan.hinge_screw_length_mm),
            ("latch", _latch_screw_stack(plan.latch_width, plan.strength_profile["pad_wall"]),
             plan.latch_screw_length_mm),
            ("catch", (
                max(plan.strength_profile["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0)
                + plan.latch_width - 2.0 * B4B_HINGE_AXIAL_GAP
                + 2.0 * B4B_HINGE_AXIAL_GAP,
                max(plan.strength_profile["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0),
            ), plan.catch_screw_length_mm),
        ):
            beyond_stack = screw - span
            engage = min(beyond_stack, lug)
            if engage < B4B_M3_THREAD_ENGAGE_MIN - _EPS:
                raise ValueError(
                    f"{what} pin threads only {engage:.2f} mm into its "
                    f"{lug:.2f} mm lug (need {B4B_M3_THREAD_ENGAGE_MIN:.1f} mm)"
                )
            protrusion = beyond_stack - lug
            if protrusion > B4B_M3_MAX_PROTRUSION + _EPS:
                raise ValueError(
                    f"{what} pin protrudes {protrusion:.1f} mm past its lug "
                    f"(limit {B4B_M3_MAX_PROTRUSION:.1f} mm)"
                )

    # 11. actual generated solids are watertight single volumes.
    body = b4b_body_with_features(box)
    if not body.is_watertight or body.volume <= 0.0:
        raise ValueError("B4B body did not generate as a watertight solid")
    lid = None
    if b4b.lid:
        lid = make_b4b_lid(box)
        if b4b.label_location == "top" and b4b.label_text.strip():
            lid, _inlay = _apply_top_label(box, lid)
        if not lid.is_watertight or lid.volume <= 0.0:
            raise ValueError("B4B lid did not generate as a watertight solid")

    if not b4b.secure_lid:
        return

    # Tolerances (cc).  These are geometry/boolean-noise bounds, NOT room for a
    # real mechanical clash: the assembled closed state has a small, expected
    # overlap (interleaved hinge knuckles, seated skirt, the latch detent
    # ridge), and what the sweep must show is that motion does not add
    # interference beyond boolean noise on top of that baseline.
    NOISE_CC = 0.05                       # motion may not add more than this
    LATCH_CLOSED_CEIL_CC = 0.10          # detent ridge + faceting, nothing more
    LID_CLOSED_CEIL_CC = 0.35            # knuckle interleave + skirt seat

    # 3-4. latch rotation about its pivot (the front-label frame is already
    # unioned into `body`).  A rigid rotating hook necessarily grazes the lip
    # through the release band, which is therefore not sampled; what must hold
    # is (a) the closed pose only touches at the detent, and (b) once past
    # release the lever is fully clear.  Opening is the -X-handed rotation.
    f = _latch_frame(eff, plan)
    for lever in make_b4b_latches(box):
        closed = _sweep_intersection_cc(
            lever, body, f["axis_y"], f["axis_z"], angles_deg=(0.0,)
        )
        if closed > LATCH_CLOSED_CEIL_CC:
            raise ValueError(
                f"a latch lever statically interferes with the body when closed "
                f"(overlap {closed:.3f} cc, allowance {LATCH_CLOSED_CEIL_CC:.2f} cc)"
            )
        open_worst = _sweep_intersection_cc(
            lever, body, f["axis_y"], f["axis_z"], angles_deg=(-45.0, -60.0, -75.0)
        )
        if open_worst > closed + NOISE_CC:
            raise ValueError(
                f"a latch lever does not swing clear of the body when open "
                f"(overlap {open_worst:.3f} cc vs {closed:.3f} cc closed); "
                f"reduce the hook depth or grow the B4B"
            )

    # 5-6. lid opening sweep about the hinge axis through the usable range.  A
    # clean rotation with no snap feature: motion must not add interference
    # beyond noise on top of the seated-closed baseline.
    if lid is not None:
        closed = _sweep_intersection_cc(
            lid, body, plan.hinge_axis_y, plan.hinge_axis_z, angles_deg=(0.0,)
        )
        if closed > LID_CLOSED_CEIL_CC:
            raise ValueError(
                f"the closed lid statically interferes with the body "
                f"(overlap {closed:.3f} cc, allowance {LID_CLOSED_CEIL_CC:.2f} cc)"
            )
        open_worst = _sweep_intersection_cc(
            lid, body, plan.hinge_axis_y, plan.hinge_axis_z,
            angles_deg=(-15.0, -35.0, -60.0, -85.0, -100.0),
        )
        if open_worst > closed + NOISE_CC:
            raise ValueError(
                f"the lid collides with the body while opening "
                f"(overlap {open_worst:.3f} cc vs {closed:.3f} cc closed); "
                f"check the hinge placement"
            )


def validate_b4b_design(
    box: BoxSpec,
    *,
    layout_feature_count: int = 0,
    layout_mode: str = "fused",
    easy_clean: bool = False,
    flat_inside: float = 0.0,
    deep: bool = False,
) -> None:
    """Deterministic, actionable checks.  Raises ``ValueError`` on the first
    problem; never swallows a geometry error behind a generic message.

    Older no-lid files are normalized to Lid Only for the editable B4B model.
    The remaining checks run on that normalized spec - the same one the
    geometry is built from. ``deep=True`` additionally runs the
    sampled moving-part and thread checks (:func:`_validate_b4b_mechanics`); it
    builds meshes, so callers on the preview hot path leave it off.
    """
    raw = box.b4b
    if not raw.enabled:
        raise ValueError("validate_b4b_design called on a non-B4B design")
    b4b = raw.normalised()
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

    cx, cy = b4b_capacity_units(box)
    if cx < 1 or cy < 1:
        raise ValueError("B4B interior is smaller than one child unit even after auto-grow")

    layout = b4b_layout(box)
    wall = layout.outer_structural_polygon.difference(layout.inner_mating_polygon)
    if wall.is_empty or wall.area <= 0.0:
        raise ValueError("B4B outward structural wall is empty")

    if b4b.secure_lid:
        plan = b4b_hardware_plan(box)
        if plan.hinge_count != 2:
            raise ValueError("a secure B4B lid needs exactly two hinges")
        if plan.hinge_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("hinge pin length did not resolve to an allowed M3 length")
        if plan.latch_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("latch pin length did not resolve to an allowed M3 length")
        if plan.catch_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("catch pin length did not resolve to an allowed M3 length")
        if b4b.latch_count == "2" and plan.latch_count_resolved != 2:
            raise ValueError("two latches were requested but do not fit this width")

    if deep:
        _validate_b4b_mechanics(box)


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
    layout = b4b_layout(box)
    case_x, case_y = layout.case_size
    lid_outer = layout.outer_structural_polygon
    min_x, min_y, max_x, max_y = (
        min(layout.case_bounds[0], lid_outer.bounds[0]),
        min(layout.case_bounds[1], lid_outer.bounds[1]),
        max(layout.case_bounds[2], lid_outer.bounds[2]),
        max(layout.case_bounds[3], lid_outer.bounds[3]),
    )
    top_z = b4b_lid_underside_z(box) + B4B_LID_SKIN if b4b.lid else eff.z
    if b4b.secure_lid:
        f = _latch_frame(eff, plan)
        hinge_min_x = min(cx - plan.hinge_width / 2.0 for cx in plan.hinge_centers_x)
        hinge_max_x = max(cx + plan.hinge_width / 2.0 for cx in plan.hinge_centers_x)
        ear_t = max(plan.strength_profile["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0)
        latch_min_x = min(cx - plan.latch_width / 2.0 - ear_t for cx in plan.latch_centers_x)
        latch_max_x = max(cx + plan.latch_width / 2.0 + ear_t for cx in plan.latch_centers_x)
        min_x = min(min_x, hinge_min_x, latch_min_x)
        max_x = max(max_x, hinge_max_x, latch_max_x)
        min_y = min(min_y, f["axis_y"] - (B4B_M3_CLEAR_BORE / 2.0 + 1.6))
        max_y = max(max_y, plan.hinge_axis_y + B4B_HINGE_KNUCKLE_RADIUS)
        top_z = max(top_z, plan.hinge_axis_z + B4B_HINGE_KNUCKLE_RADIUS)
    if b4b.stacking:
        top_z += B4B_STACK_RECESS_DEPTH
    summary: dict = {
        "field_mm": [eff.x, eff.y, eff.z],
        "field_units": [round(eff.x / GRID_PITCH), round(eff.y / GRID_PITCH)],
        "outer_mm": [round(case_x, 3), round(case_y, 3), eff.z],
        "case_outer_mm": [round(case_x, 3), round(case_y, 3), eff.z],
        "assembled_envelope_mm": [
            round(max_x - min_x, 3), round(max_y - min_y, 3), round(top_z, 3)
        ],
        "grew": b4b_grew(box),
        "capacity_units": [cx, cy],
        "capacity_mm": [round(mx, 2), round(my, 2)],
        "max_child_height_mm": round(b4b_max_child_height(box), 2),
        "effective_base_thickness_mm": round(eff.base_thickness, 3),
        "lid": b4b.lid,
        "secure_lid": b4b.secure_lid,
        "lid_headroom_mm": b4b.lid_headroom_mm,
        "stacking": b4b.stacking,
        "label_location": b4b.label_location if b4b.label_text.strip() else "none",
        "label_text": b4b.label_text,
        "capacity_text": (
            f"Inside capacity: {mx:g} x {my:g} mm - {cx} x {cy} units"
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
            "catch_screw": f"M3x{plan.catch_screw_length_mm}",
            "catch_qty": plan.latch_count_resolved,
            "nuts": 0,
        }
        summary["hardware_bom"] = plan.screw_bom()
    else:
        summary["latch_count"] = 0
        summary["hardware"] = {"nuts": 0}
        summary["hardware_bom"] = []
    return summary


def b4b_body_with_features(box: BoxSpec) -> trimesh.Trimesh:
    """The B4B body exactly as it will print: flat floor + wall + hardware, plus the
    slide-in front-label channel frame when that label is selected.

    Preview and export both go through here so they can never disagree about
    whether the frame is present.
    """
    body = make_b4b_body(box)
    b4b = b4b_effective_box(box).b4b
    if b4b.label_location == "front" and b4b.label_text.strip():
        frame, _plate, _centre = b4b_front_label_geometry(box)
        body = union([body, frame])
        body.remove_unreferenced_vertices()
        body.merge_vertices()
    return body


@lru_cache(maxsize=32)
def _b4b_preview_geometry(box: BoxSpec) -> tuple:
    """Cached: identical B4B designs reuse the same preview mesh walk instead of
    re-running the booleans on every keystroke."""
    from organizer_app import _mesh_preview_geometry  # local: avoid import cycle

    geometry: list = []
    eff = b4b_effective_box(box)
    body = b4b_body_with_features(box)
    geometry.extend(_mesh_preview_geometry(body, "b4b_body"))
    if eff.b4b.label_location == "front" and eff.b4b.label_text.strip():
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
    if eff.b4b.stacking:
        for peg in _stack_pegs(box):
            geometry.extend(_mesh_preview_geometry(peg, "b4b_stack"))
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


def _top_surface_keepouts(eff: BoxSpec) -> list[Polygon]:
    """Plan-view regions on the lid top the label must avoid: every stacking
    boss (all four, not one row) plus a margin.  Hinge knuckles and latch ears
    sit outboard at the rim, below the top plate, so they do not intrude on the
    central label band; the bosses are the real keep-outs."""
    if not (eff.b4b.stacking and eff.b4b.lid):
        return []
    r = B4B_STACK_BOSS_DIAMETER / 2.0 + B4B_STACK_FEMALE_RADIAL_CLEARANCE + B4B_TOP_LABEL_MARGIN
    return [Point(cx, cy).buffer(r, quad_segs=24) for cx, cy in _stack_locator_centres(eff)]


def b4b_top_label_outline(box: BoxSpec):
    """Placed outline for the lid-top label: centred in X, ~one third back from
    the front (front is -Y), fitted inside a rectangle that clears every
    stacking boss keep-out."""
    eff = b4b_effective_box(box)
    if not eff.b4b.lid:
        raise ValueError("a top label needs the lid enabled")
    # The label lives on the derived lid footprint, not the child field.
    case_x, case_y = b4b_layout(box).case_size
    avail_w = case_x - 2.0 * B4B_TOP_LABEL_MARGIN
    avail_h = case_y / 3.0
    label_cy = -case_y / 6.0
    keepouts = _top_surface_keepouts(eff)

    def clear_rect(w: float, h: float) -> bool:
        rect = Polygon([
            (-w / 2.0, label_cy - h / 2.0), (w / 2.0, label_cy - h / 2.0),
            (w / 2.0, label_cy + h / 2.0), (-w / 2.0, label_cy + h / 2.0),
        ])
        return not any(rect.intersects(k) for k in keepouts)

    # Shrink height first (label band is wide and short), then width, until the
    # placed rectangle clears every boss.
    for _ in range(40):
        if clear_rect(avail_w, avail_h):
            break
        if avail_h > 4.0:
            avail_h = max(4.0, avail_h - 1.0)
        elif avail_w > 10.0:
            avail_w -= 2.0
        else:
            raise ValueError(
                "the top label cannot be placed clear of the stacking bosses; "
                "shorten the label, disable stacking, or use a larger B4B"
            )
    outline = _fit_text_outline(
        eff.b4b.label_text, avail_w, avail_h, B4B_TOP_LABEL_CAP_IDEAL
    )
    placed = translate_polygon(outline, 0.0, label_cy)
    # Hard guarantee: the pocket is never cut through a boss.
    for k in keepouts:
        if placed.intersects(k):
            raise ValueError(
                "the top label overlaps a stacking boss keep-out; shorten the "
                "label or disable stacking"
            )
    return placed


def _apply_top_label(box: BoxSpec, lid: trimesh.Trimesh):
    """Sink the top label flush into the lid; return ``(lid, inlay)`` where the
    inlay is a separate object that fills the pocket.  ``b4b_top_label_outline``
    has already proven the outline clears every stacking boss."""
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
    layout = b4b_layout(box)
    y_wall = min(layout.front_wall_y(x) for x in plan.latch_centers_x or (0.0,))
    span = _front_span(box)

    frame_w = span - 4.0
    # vertical band: below the latch pads (or below the rim if passive)
    if plan.latch_count_resolved:
        receiver_r = B4B_M3_CLEAR_BORE / 2.0 + 1.6
        top_z = plan.catch_axis_z - receiver_r - 2.0
    else:
        top_z = eff.z - 4.0
    height = B4B_FRONT_LABEL_HEIGHT
    bottom_z = top_z - height
    if frame_w < 30.0 or bottom_z < 3.0:
        raise ValueError(
            "not enough clear front-wall area for a slide-in label; use a top "
            "label, a taller box, or turn latches off"
        )

    rail = 1.6                       # channel lip that captures the plate
    channel_t = B4B_FRONT_LABEL_PLATE_T + 2.0 * B4B_FRONT_LABEL_CLEAR
    depth = channel_t + 1.4          # + back wall
    endstop = 2.0
    # Embed the frame block a little into the front wall so union() fuses it
    # into the body as one connected solid (never just a face-to-face touch).
    embed = min(0.8, max(0.3, eff.wall_depth * 0.5))

    outer = trimesh.creation.box(extents=(frame_w, depth + embed, height))
    outer.apply_translation(
        (0.0, y_wall - depth / 2.0 + embed / 2.0, (top_z + bottom_z) / 2.0)
    )
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
        # Explicit datums.  The plate is centred on the origin, so its readable
        # (-Y) face is at y = -PLATE_T/2.  The engraving cutter must start on
        # that face and bite inward (+Y) by TEXT_DEPTH, with a small overlap so
        # the boolean always removes material.
        front_face_y = -B4B_FRONT_LABEL_PLATE_T / 2.0
        overlap = 0.1
        engrave = text_prism(outline, top_z=0.0, depth=TEXT_DEPTH)  # z in [-TEXT_DEPTH, 0]
        # +90 deg about X: extrude axis (-Z) -> +Y, glyph height (+Y) -> +Z upright
        engrave.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
        )
        centre = engrave.bounds.mean(axis=0)
        engrave.apply_translation((-centre[0], 0.0, -centre[2]))   # centre on the plate face
        y_min = float(engrave.bounds[0][1])
        engrave.apply_translation((0.0, (front_face_y - overlap) - y_min, 0.0))
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
def _print_pose(mesh: trimesh.Trimesh, kind: str) -> trimesh.Trimesh:
    """Assembly-space -> a support-minimising *orientation* only.

    No drop-to-plate and no recentring happen here: that is done once per print
    group in :func:`_pack_print_groups`, so parts that must stay registered
    (the lid and its top inlay) keep their exact relative coordinates.
    """
    m = mesh.copy()
    if kind == "latch":
        # lay the lever on its broad face: the hook profile is extruded along
        # local X, so that axis (not Y) must roll onto the bed's Z.
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (0.0, 1.0, 0.0))
        )
    elif kind == "lid":
        # broad, flat top face on the bed; skirt and hardware build upward
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi, (1.0, 0.0, 0.0))
        )
    return m


def _pack_print_groups(
    groups: list[list[tuple[str, trimesh.Trimesh]]]
) -> list[tuple[str, trimesh.Trimesh]]:
    """Lay independent print groups out in a row on the build plane.

    Each *group* is a list of named meshes that share one rigid transform (the
    lid + its top-label inlay are one group, so the inlay stays registered in
    the lid pocket).  Groups are packed left to right along +X with
    ``B4B_PRINT_PART_GAP`` between them, each centred on Y=0 and dropped so its
    lowest point sits on z=0.  No two groups overlap.
    """
    packed: list[tuple[str, trimesh.Trimesh]] = []
    x_cursor = 0.0
    for group in groups:
        meshes = [m for _n, m in group]
        mins = np.min([m.bounds[0] for m in meshes], axis=0)
        maxs = np.max([m.bounds[1] for m in meshes], axis=0)
        offset = (
            x_cursor - float(mins[0]),
            -0.5 * float(mins[1] + maxs[1]),
            -float(mins[2]),
        )
        for name, mesh in group:
            mesh.apply_translation(offset)
            packed.append((name, mesh))
        x_cursor += float(maxs[0] - mins[0]) + B4B_PRINT_PART_GAP
    return packed


def b4b_build_parts(box: BoxSpec) -> list[tuple[str, trimesh.Trimesh]]:
    """Every printable B4B object, named, oriented and packed on the build
    plane so nothing overlaps.  Screws are never emitted as geometry.

    The lid and its flush top-label inlay are treated as one print group: the
    same transform is applied to both, so the inlay stays exactly registered in
    the lid pocket in the exported 3MF.
    """
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    validate_b4b_design(box, deep=True)

    groups: list[list[tuple[str, trimesh.Trimesh]]] = []

    body = b4b_body_with_features(box)
    groups.append([("B4B Body", _print_pose(body, "body"))])

    if b4b.lid:
        lid = make_b4b_lid(box)
        top_inlay = None
        if b4b.label_location == "top" and b4b.label_text.strip():
            lid, top_inlay = _apply_top_label(box, lid)
        lid_group = [("B4B Lid", _print_pose(lid, "lid"))]
        if top_inlay is not None:
            lid_group.append(("B4B Top Label", _print_pose(top_inlay, "lid")))
        groups.append(lid_group)

    if b4b.secure_lid:
        for i, lever in enumerate(make_b4b_latches(box), start=1):
            groups.append([(f"B4B Latch {i}", _print_pose(lever, "latch"))])

    if b4b.stacking:
        for i, peg in enumerate(_stack_pegs(box), start=1):
            groups.append([(f"B4B Stacking Peg {i}", _print_pose(peg, "peg"))])

    if b4b.label_location == "front" and b4b.label_text.strip():
        _frame, plate, centre = b4b_front_label_geometry(box)
        groups.append(
            [("B4B Front Label", _print_pose(translated(plate, centre), "plate"))]
        )

    return _pack_print_groups(groups)
