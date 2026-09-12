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
    _extrude_xz_profile,
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
B4B_LID_SKIN = 1.6              # passive lid top plate thickness
# A secure lid's hinge tabs and latch ears root into this plate, so it is the
# whole load path for peel and bending on a carried case.  It is thicker than
# the passive plate for that reason alone; every secure lid datum reads it
# through :func:`b4b_lid_skin`, never the passive constant.
B4B_SECURE_LID_SKIN = 2.4
B4B_LID_SKIRT_WALL = 2.0       # locating skirt wall thickness
# Lateral clearance, skirt outer face to the cavity mouth it drops into.  One
# printed running fit per side - loose enough to drop in without forcing, tight
# enough that the closed lid does not rattle on the spigot.
B4B_LID_SEAT_CLEARANCE = 0.15
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
# The screw head bears straight on printed plastic with no washer, so every
# head-bearing boss must leave real material outboard of the head footprint,
# not merely clear it.  This is that margin, and it is what sizes
# ``B4B_HW_BOSS_RADIUS`` - the head clearance is never a dead declaration.
B4B_M3_HEAD_EDGE_MARGIN = 0.7
B4B_SCREW_LENGTHS = (12, 16, 20, 25, 30)   # allowed kit lengths, mm
B4B_M3_MAX_PROTRUSION = 6.0

# --- support-free integrated hardware -------------------------------------- #
# Every integrated hinge/latch barrel has its axis on world X and prints
# horizontally: the body upright, the lid flipped 180 degrees about X.  A full
# round barrel therefore always presents a lower arc steeper than the
# support-free limit, whichever way up it goes, so B4B uses a faceted section
# instead: vertical faces at +/-Y, a flat at +Z and -Z, and 45-degree facets
# between them.  The profile is symmetric in Z, so the same helper is correct
# for the upright body and the flipped lid.
#
# ``B4B_SUPPORT_FREE_FLAT`` is the half-width of those flats as a fraction of
# the nominal radius.  The -Z flat is the only horizontal face, and it is a
# short bridge between two 45-degree facets - never wider than
# ``B4B_SUPPORT_FREE_BRIDGE_MAX``.
B4B_SUPPORT_FREE_FLAT = 0.35
B4B_SUPPORT_FREE_BRIDGE_MAX = 3.0
# radial extent of that section at its thinnest (on a 45-degree facet) and at
# its widest (a facet join), as multiples of the nominal radius
_SUPPORT_FREE_INSCRIBED = (1.0 + B4B_SUPPORT_FREE_FLAT) / math.sqrt(2.0)
_SUPPORT_FREE_CIRCUM = math.sqrt(1.0 + B4B_SUPPORT_FREE_FLAT ** 2)

# One boss size for every M3 pivot: derived so even the section's thinnest
# radial direction still leaves ``B4B_M3_HEAD_EDGE_MARGIN`` outboard of the
# head.  Hinge knuckles, latch pivot ears and catch receivers all use it.
B4B_HW_BOSS_RADIUS = (
    B4B_M3_HEAD_CLEAR / 2.0 + B4B_M3_HEAD_EDGE_MARGIN
) / _SUPPORT_FREE_INSCRIBED

# --- hardware reinforcement ------------------------------------------------ #
# Hinge and latch loads must not run through a sub-millimetre overlap with a
# user-selected wall.  Each hardware group sits on its own exterior root web
# that starts at the inner mating face, crosses the whole local wall band and
# grows outward; these dimensions are deliberately independent of ``wall``.
B4B_HW_ROOT_MIN_THICKNESS = 3.0   # local wall + web at a root, at any wall
B4B_HW_PAD_MARGIN_X = 2.0         # web beyond the fitting envelope, each end
B4B_HW_PAD_HEIGHT = 10.0          # how far the web runs down the wall
B4B_HW_CLEARANCE = 0.6            # static gap, body fitting to lid fitting
B4B_HINGE_WEB = 1.6               # hinge web outboard of the outer wall face

# Lid-side roots: the fitting grows out of the plate through an arm that is
# part of its own section, not a block tacked on afterwards.
B4B_LID_ROOT_BITE = 1.0           # how far the arm overlaps the fitting
B4B_LID_ROOT_REACH = 4.0          # run into the plate, away from its edge
B4B_LID_FITTING_DROP = 1.6        # how far a lid fitting hangs below the plate

# Every hardware section is filleted where it meets the plate or the root web
# it grows from: a square internal corner is where a printed bracket cracks
# off.  Derived from the fitting itself so it tracks the hardware, and capped
# so the arc can never eat the drop below the plate or crowd the M3 bore.
B4B_HW_FILLET = 1.2

# Print-bed layout: parts are packed in a row, none overlapping.
B4B_PRINT_PART_GAP = 8.0

# Stacking boss self-locating lead-in (a real printed taper, not a claim).
B4B_STACK_BOSS_CHAMFER = 0.6

# Hinges (exactly two, rear wall)
B4B_HINGE_COUNT = 2
B4B_HINGE_WIDTH_FRACTION = 0.16
# The running gap between every pair of printed parts that must move against
# each other - hinge knuckles, and the latch lever against its receiver ears.
# 0.20 mm was a boolean gap, not a printed one: at FDM tolerances the two faces
# fuse and the joint has to be broken free.
B4B_HINGE_AXIAL_GAP = 0.35
# The hinge is three axial segments; the outer (far) one is the printed
# thread-forming lug.  Rather than hard-coding a width and hoping the lug lands
# clear of B4B_M3_THREAD_ENGAGE_MIN, the minimum width is *derived* from a lug
# thickness that carries real margin over that floor.
B4B_HINGE_LUG_TARGET = 3.8
B4B_HINGE_WIDTH_MIN = math.ceil(
    2.0 * 3.0 * (B4B_HINGE_LUG_TARGET + B4B_HINGE_AXIAL_GAP)
) / 2.0                          # 12.5 mm -> a 3.82 mm lug
B4B_HINGE_WIDTH_MAX = 24.0
B4B_HINGE_CLEAR_KEEPOUT = 1.0    # extra gap from a wall's corner tangent
B4B_HINGE_CENTRE_GAP = 4.0       # clear run between the two hinge root webs

# Latches (secure lid only)
B4B_LATCH_WIDTH_FRACTION = 0.14
B4B_LATCH_WIDTH_MIN = 12.0
B4B_LATCH_WIDTH_MAX = 22.0
B4B_LATCH_MUTUAL_CLEARANCE = 6.0
B4B_LATCH_DRAW_MIN = 6.5         # shallowest useful draw below the lid seat
B4B_LATCH_BODY_CLEARANCE = 0.8   # running gap, swinging lever to the body
B4B_LATCH_PROFILES = {
    # lever_thickness  - where the pivot sits relative to the hook
    # hook_depth       - how far the hook wraps the catch pin
    # catch_thickness  - exterior receiver web behind the catch boss
    # pad_wall         - printed ear thickness each side of the lever
    # pad_height       - how far below the lid seat the catch pin sits
    # detent           - snap interference at the hook mouth
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

# Carrying handle: a printed arch bolted flat to the lid top with two M3
# screws, the same kit and the same no-nut, thread-forming fixing every other
# B4B fitting uses.  A handled lid is made thick enough to *be* the
# thread-forming lug, so nothing hangs below it into the child bins headroom
# and nothing stands above it to spoil the flat face the lid prints on.
B4B_HANDLE_LID_SKIN = B4B_HINGE_LUG_TARGET
B4B_HANDLE_EDGE_INSET = 3.0        # feet stay this far in from the lid edge
B4B_HANDLE_SPAN_MAX = 160.0        # a grip wider than this helps nobody
B4B_HANDLE_MIN_OPENING = 14.0      # narrower than this is not a handle
B4B_HANDLE_UPRIGHT_FRACTION = 0.10
B4B_HANDLE_UPRIGHT_MIN = 5.0
B4B_HANDLE_UPRIGHT_MAX = 10.0
B4B_HANDLE_DEPTH_FRACTION = 0.16   # across Y
B4B_HANDLE_DEPTH_MIN = 12.0
B4B_HANDLE_DEPTH_MAX = 22.0
B4B_HANDLE_FOOT_WALL = 2.2         # material each side of the screw in a foot
B4B_HANDLE_FOOT_MIN = 6.0
B4B_HANDLE_SCREW_SLACK = 0.2       # how far the screw may pass the plate
# A hand is a hand whatever the case measures, so the grip is clamped to a
# comfortable band rather than scaled freely.
B4B_HANDLE_GRIP_CLEAR_MIN = 24.0
B4B_HANDLE_GRIP_CLEAR_MAX = 34.0
B4B_HANDLE_GRIP_MIN = 7.0
B4B_HANDLE_GRIP_MAX = 12.0
B4B_HANDLE_FILLET = 1.6

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


def _hinge_width_for_case(case_x: float) -> float:
    return min(
        B4B_HINGE_WIDTH_MAX,
        max(B4B_HINGE_WIDTH_MIN, B4B_HINGE_WIDTH_FRACTION * case_x),
    )


def _hinge_pad_half_width(hinge_width: float) -> float:
    """Half the reinforced hinge envelope: the knuckle span plus its root web."""
    return hinge_width / 2.0 + B4B_HW_PAD_MARGIN_X


def _reinforced_hinges_fit(child_x: float, wall_depth: float) -> bool:
    """Whether two *reinforced* rear hinges fit the case a child field of
    ``child_x`` produces, honouring both keep-outs.

    Deliberately a pure function of the requested field and the wall: it runs
    inside :func:`b4b_effective_box`, which every layout/plan call depends on,
    so it must not reach back through :func:`b4b_layout`.
    """
    outer_half_x = child_x / 2.0 + WAVE_MATING_GAP / 2.0 + wall_depth
    case_x = 2.0 * (outer_half_x + WAVE_AMPLITUDE)
    pad_half = _hinge_pad_half_width(_hinge_width_for_case(case_x))
    room = outer_half_x - CORNER_INSET - B4B_HINGE_CLEAR_KEEPOUT
    return room + _EPS >= 2.0 * pad_half + B4B_HINGE_CENTRE_GAP / 2.0


def _handle_arch(case_x: float) -> tuple[float, float]:
    """(upright thickness, foot length) for a handle on a case this wide."""
    upright = min(
        B4B_HANDLE_UPRIGHT_MAX,
        max(B4B_HANDLE_UPRIGHT_MIN, B4B_HANDLE_UPRIGHT_FRACTION * case_x),
    )
    return upright, max(
        upright + 4.0, B4B_M3_CLEAR_BORE + 2.0 * B4B_HANDLE_FOOT_WALL
    )


def _handle_span(case_x: float) -> float:
    """Screw-centre span of the handle a case this wide can carry.

    The feet stand as far apart as the lid allows, so the hand opening is as
    large as the case can give it.
    """
    _upright, foot = _handle_arch(case_x)
    reach = case_x / 2.0 - CORNER_INSET - B4B_HANDLE_EDGE_INSET
    return min(B4B_HANDLE_SPAN_MAX, 2.0 * (reach - foot / 2.0))


def _handle_fits(child_x: float, wall_depth: float) -> bool:
    """Whether a case built on this child field leaves a usable hand opening.

    Like :func:`_reinforced_hinges_fit` this is a pure function of the request
    and the wall, because it runs inside :func:`b4b_effective_box`.  It takes
    the pessimistic case width - the wave only ever makes the real one wider -
    so it never promises a handle the geometry cannot then build.
    """
    case_x = 2.0 * (child_x / 2.0 + WAVE_MATING_GAP / 2.0 + wall_depth)
    _upright, foot = _handle_arch(case_x)
    return _handle_span(case_x) + _EPS >= foot + B4B_HANDLE_MIN_OPENING


def b4b_secure_min_field_x(wall: float = 0.8) -> float:
    """Smallest requested child-field X a secure lid can be built on.

    Derived by fit from the real reinforced hardware rather than kept as a
    magic constant that can drift away from the geometry it is meant to
    guarantee: grow by one grid step until two hinge root webs sit clear of
    both the corner tangent keep-out and each other.
    """
    wall_depth = BoxSpec(wall=wall).wall_depth
    x = GRID_PITCH
    while not _reinforced_hinges_fit(x, wall_depth):
        x += GRID_PITCH
    return x


def b4b_lid_skin_from_eff(eff: BoxSpec) -> float:
    """Authoritative lid top-plate thickness.

    A secure lid carries its hinge and latch roots in this plate, so it is
    thicker than a passive one, and a handled lid is thicker again: the plate
    is what the handle screws thread into, and it carries the whole weight of
    the case.  Every lid datum - plate, top Z, hinge axis, latch pivot,
    stacking socket roof, label pocket, envelope summary - reads this one
    helper so they can never drift apart.
    """
    b4b = eff.b4b.normalised()
    if b4b.handle:
        return B4B_HANDLE_LID_SKIN
    return B4B_SECURE_LID_SKIN if b4b.secure_lid else B4B_LID_SKIN


def b4b_lid_skin(box: BoxSpec) -> float:
    return b4b_lid_skin_from_eff(b4b_effective_box(box))


def b4b_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec every B4B builder uses.

    Identical to the user's child-field request except for genuinely required
    hardware/stacking growth and any stacking base
    reinforcement.  Easy Clean and the flat-inside band are forced off because
    they alter the floor/perimeter the child bins must seat on.
    """
    b4b = box.b4b.normalised()
    x, y, z = box.x, box.y, box.z

    # Secure-lid hardware needs enough requested field width for two *reinforced*
    # rear hinges that clear the corner tangents and each other.  The webs
    # themselves grow outward; only a genuine fit failure grows the child field.
    if b4b.secure_lid:
        while not _reinforced_hinges_fit(x, box.wall_depth):
            x += GRID_PITCH
        z = max(z, B4B_LATCHED_MIN_HEIGHT)

    # A handle needs its two feet far enough apart to get a hand between them.
    # Grow rather than refuse, the same way a latched lid grows a short box.
    if b4b.handle:
        while not _handle_fits(x, box.wall_depth):
            x += GRID_PITCH

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
    # every head-bearing boss on the case is this one derived size
    boss_radius: float = 0.0
    fillet_radius: float = 0.0
    # rear hinge root web
    hinge_web: float = 0.0
    hinge_pad_width: float = 0.0
    hinge_pad_face_y: float = 0.0
    hinge_pad_top_z: float = 0.0
    hinge_lug_thickness: float = 0.0
    # front latch / catch receiver
    latch_web: float = 0.0
    latch_pad_width: float = 0.0
    latch_pad_face_y: float = 0.0
    latch_pad_top_z: float = 0.0
    latch_pad_bottom_z: float = 0.0
    catch_root_z: float = 0.0
    catch_ear_thickness: float = 0.0
    lever_width: float = 0.0
    hook_outer_r: float = 0.0
    pivot_axis_y: float = 0.0
    pivot_axis_z: float = 0.0
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
    mirroring the geometry built by :func:`_hinge_body_parts`.

    ``B4B_HINGE_WIDTH_MIN`` is derived so the lug this returns always clears
    ``B4B_HINGE_LUG_TARGET``, not merely ``B4B_M3_THREAD_ENGAGE_MIN``."""
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


def _wall_extreme_y(
    layout: B4BLayout, x0: float, x1: float, outward_sign: float
) -> float:
    """Outermost Y the named wall reaches anywhere across ``[x0, x1]``.

    Hardware roots are flat slabs across a run of a wavy wall, so they have to
    be referenced to the wall's crest over that whole run, not to the wave value
    at one sample point.
    """
    steps = max(9, int(abs(x1 - x0) * 4.0) + 1)
    xs = np.linspace(x0, x1, steps)
    if outward_sign > 0.0:
        return max(layout.rear_wall_y(float(v)) for v in xs)
    return min(layout.front_wall_y(float(v)) for v in xs)


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
    skin = b4b_lid_skin_from_eff(eff)
    underside_z = b4b_lid_underside_z_from_eff(eff)
    boss_r = B4B_HW_BOSS_RADIUS
    boss_out = boss_r * _SUPPORT_FREE_CIRCUM      # widest radial reach of the
                                                  # support-free boss section
    fillet = min(
        B4B_HW_FILLET, 0.5 * B4B_LID_FITTING_DROP, 0.25 * boss_r
    )

    # ---- hinges: two, symmetric, clear of the corners and of each other ----
    hinge_width = _hinge_width_for_case(case_x)
    pad_half = _hinge_pad_half_width(hinge_width)
    hinge_pad_width = 2.0 * pad_half
    # b4b_effective_box has already grown the field until both keep-outs can be
    # met, so this window is never empty; clamp anyway rather than trust it.
    centre_min = pad_half + B4B_HINGE_CENTRE_GAP / 2.0
    centre_max = layout.outer_half_x - CORNER_INSET - B4B_HINGE_CLEAR_KEEPOUT - pad_half
    centre = min(max(eff.x / 4.0, centre_min), max(centre_max, centre_min))
    hinge_centers_x = (-centre, centre)

    hinge_web = max(B4B_HINGE_WEB, B4B_HW_ROOT_MIN_THICKNESS - eff.wall_depth)
    rear_crest = max(
        _wall_extreme_y(layout, cx - pad_half, cx + pad_half, +1.0)
        for cx in hinge_centers_x
    )
    hinge_pad_face_y = rear_crest + hinge_web
    hinge_axis_y = rear_crest + boss_r + 0.45
    # The barrel's flat +Z facet is exactly flush with the broad lid top plane,
    # so on the flipped lid it prints straight onto the bed.
    hinge_axis_z = underside_z + skin - boss_r
    # The root web has to stay clear of the lid-side knuckle it interleaves
    # with; the gussets carry the load from the web up to the barrels.
    hinge_pad_top_z = min(
        eff.z + 0.35,
        underside_z - 1.0,
        hinge_axis_z - boss_out - B4B_HW_CLEARANCE,
    )
    h_span, h_lug = _hinge_screw_stack(hinge_width)
    hinge_screw = _screw_for_stack(h_span, h_lug, "hinge")

    # ---- latches: front, count derived from the available span ----
    latch_width = min(
        B4B_LATCH_WIDTH_MAX,
        max(B4B_LATCH_WIDTH_MIN, B4B_LATCH_WIDTH_FRACTION * case_x),
    )
    lever_w = latch_width - 2.0 * B4B_HINGE_AXIAL_GAP
    catch_ear_t = max(profile["pad_wall"], B4B_M3_THREAD_ENGAGE_MIN + 1.0)
    latch_pad_width = latch_width + 2.0 * catch_ear_t + 2.0 * B4B_HW_PAD_MARGIN_X
    # Two latches only when two *reinforced* receivers fit clear of each other
    # and of the corners - the bare lever width is not the envelope any more.
    span = _front_span(box)
    half_pad = latch_pad_width / 2.0
    centre_min = half_pad + B4B_LATCH_MUTUAL_CLEARANCE / 2.0
    centre_max = span / 2.0 - half_pad - B4B_LATCH_MUTUAL_CLEARANCE / 2.0
    if centre_max + _EPS >= centre_min:
        resolved = 2
        centre_l = min(max(span / 6.0, centre_min), centre_max)
        latch_centers_x = (-centre_l, centre_l)
    else:
        resolved = 1
        latch_centers_x = (0.0,)
    # ``catch_thickness`` is the exterior receiver web behind the catch boss -
    # the one dimension that makes Standard a structurally stronger receiver
    # than Lightweight rather than just a differently placed one.
    latch_web = max(
        profile["catch_thickness"], B4B_HW_ROOT_MIN_THICKNESS - eff.wall_depth
    )
    front_crest = min(
        _wall_extreme_y(
            layout, cx - latch_pad_width / 2.0, cx + latch_pad_width / 2.0, -1.0
        )
        for cx in latch_centers_x
    )
    latch_pad_face_y = front_crest - latch_web
    latch_pad_top_z = min(eff.z + 0.35, underside_z - 1.0)

    hook_outer_r = B4B_M3_NOMINAL / 2.0 + 0.35 + max(1.4, profile["hook_depth"] * 0.6)
    # The hook swings in front of the receiver web, never against it.
    catch_axis_y = latch_pad_face_y - hook_outer_r - B4B_LATCH_BODY_CLEARANCE
    pivot_axis_y = catch_axis_y - (
        hook_outer_r - profile["lever_thickness"] / 2.0 + 0.5
    )
    pivot_axis_z = underside_z + skin - boss_r
    # The lid pivot ear and the body catch ear interleave in X, so the catch
    # must hang far enough below the pivot boss that the two never meet.
    clear_draw = eff.z - (pivot_axis_z - 2.0 * boss_out - B4B_HW_CLEARANCE)
    draw = max(B4B_LATCH_DRAW_MIN, profile["pad_height"] * 0.8, clear_draw)
    catch_axis_z = eff.z - draw
    latch_pad_bottom_z = _pad_bottom_z(
        latch_pad_top_z, abs(latch_pad_face_y), layout.outer_half_y
    )
    # Where the receiver bracket meets the web.  The catch boss hangs below
    # the web, so the bracket's underside runs down and outward to it: the root
    # must sit at least one horizontal run *above* the boss for that plane to
    # stay at 45 degrees and print with no support.
    catch_run = 0.8 + hook_outer_r + B4B_LATCH_BODY_CLEARANCE
    catch_root_z = max(
        catch_axis_z - 0.5 * boss_r + catch_run, latch_pad_bottom_z + 1.0
    )
    if catch_root_z > latch_pad_top_z - 0.5:
        raise ValueError(
            "the latch receiver cannot reach its root web without overhanging; "
            "use a taller B4B or the lightweight latch"
        )

    l_span, l_lug = _latch_screw_stack(latch_width, profile["pad_wall"])
    latch_screw = _screw_for_stack(l_span, l_lug, "latch")
    catch_span = catch_ear_t + lever_w + 2.0 * B4B_HINGE_AXIAL_GAP
    catch_screw = _screw_for_stack(catch_span, catch_ear_t, "catch")

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
        boss_radius=boss_r,
        fillet_radius=fillet,
        hinge_web=hinge_web,
        hinge_pad_width=hinge_pad_width,
        hinge_pad_face_y=hinge_pad_face_y,
        hinge_pad_top_z=hinge_pad_top_z,
        hinge_lug_thickness=h_lug,
        latch_web=latch_web,
        latch_pad_width=latch_pad_width,
        latch_pad_face_y=latch_pad_face_y,
        latch_pad_top_z=latch_pad_top_z,
        latch_pad_bottom_z=latch_pad_bottom_z,
        catch_root_z=catch_root_z,
        catch_ear_thickness=catch_ear_t,
        lever_width=lever_w,
        hook_outer_r=hook_outer_r,
        pivot_axis_y=pivot_axis_y,
        pivot_axis_z=pivot_axis_z,
    )


# --------------------------------------------------------------------------- #
# carrying handle
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BHandlePlan:
    """Every carrying-handle dimension, resolved once.

    The handle is a printed arch bolted flat to the lid top with two M3 screws,
    the same kit and the same no-nut, thread-forming fixing every other B4B
    fitting uses.  Its span and depth follow the case; the hand opening does
    not, because a hand is a hand whatever the case measures.
    """

    span: float                 # between the two screw centres
    centers_x: tuple[float, float]
    foot_length: float
    foot_height: float
    upright: float
    depth: float                # across Y
    grip_clear: float           # clear height under the grip
    grip_thickness: float
    fillet: float
    top_z: float                # lid top: the handle stands on it
    screw_length_mm: int

    @property
    def height(self) -> float:
        """How far the finished handle stands above the lid top."""
        return self.foot_height + self.grip_clear + self.grip_thickness


def b4b_handle_plan(box: BoxSpec) -> B4BHandlePlan | None:
    """Resolve the handle, or ``None`` when this design has none.

    Raises with an actionable message when a handle is asked for on a case too
    narrow to carry one, rather than quietly leaving it off a design that says
    it has one.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.handle:
        return None
    layout = b4b_layout(box)
    case_x, case_y = layout.case_size
    skin = b4b_lid_skin_from_eff(eff)

    upright, foot_length = _handle_arch(case_x)
    span = _handle_span(case_x)
    if span < foot_length + B4B_HANDLE_MIN_OPENING:
        raise ValueError(
            f"a {case_x:.0f} mm wide case is too narrow for a carrying handle; "
            f"turn the handle off or use a wider B4B"
        )
    depth = min(
        B4B_HANDLE_DEPTH_MAX,
        max(B4B_HANDLE_DEPTH_MIN, B4B_HANDLE_DEPTH_FRACTION * case_y),
    )
    depth = min(depth, max(6.0, case_y - 2.0 * B4B_HANDLE_EDGE_INSET))
    opening = span - upright
    grip_clear = min(
        B4B_HANDLE_GRIP_CLEAR_MAX,
        max(B4B_HANDLE_GRIP_CLEAR_MIN, 0.3 * opening),
    )
    grip_thickness = min(
        B4B_HANDLE_GRIP_MAX, max(B4B_HANDLE_GRIP_MIN, 0.09 * span)
    )
    # The plate itself is the thread-forming lug, so the foot is sized to use
    # up the rest of the shortest kit screw and leave nothing poking through.
    foot_height = max(
        B4B_HANDLE_FOOT_MIN, B4B_SCREW_LENGTHS[0] - skin - B4B_HANDLE_SCREW_SLACK
    )
    screw = _screw_for_stack(foot_height, skin, "handle")
    fillet = min(
        B4B_HANDLE_FILLET,
        0.3 * min(grip_thickness, upright, foot_height),
    )
    return B4BHandlePlan(
        span=span,
        centers_x=(-span / 2.0, span / 2.0),
        foot_length=foot_length,
        foot_height=foot_height,
        upright=upright,
        depth=depth,
        grip_clear=grip_clear,
        grip_thickness=grip_thickness,
        fillet=fillet,
        top_z=b4b_lid_underside_z_from_eff(eff) + skin,
        screw_length_mm=screw,
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


def b4b_rim_z_from_eff(eff: BoxSpec) -> float:
    """Z of the body's top rim.

    The rim *is* the lid seat: the wall rises to the lid underside datum so the
    lid plate lands flat on a full-perimeter rim.  A wall that stopped at
    ``eff.z`` would leave the lid floating on its hardware, with the locating
    skirt as the only thing bridging the gap - and no room inside the footprint
    for that skirt to bridge it without driving into the wall.
    """
    if eff.b4b.lid:
        return b4b_lid_underside_z_from_eff(eff)
    return eff.z


def b4b_rim_z(box: BoxSpec) -> float:
    return b4b_rim_z_from_eff(b4b_effective_box(box))


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

    rim_z = b4b_rim_z_from_eff(eff)
    envelope = _extrude_polygon(layout.outer_structural_polygon, rim_z)
    cavity = _extrude_polygon(
        layout.inner_mating_polygon, rim_z - floor_z + 1.0
    )
    cavity.apply_translation((0.0, 0.0, floor_z))
    body = difference([envelope, cavity])

    # One n-way union, not one call per fitting: each separate boolean would
    # re-walk the whole wavy case.
    hardware: list[trimesh.Trimesh] = []
    if plan.hinge_count:
        hardware.extend(_hinge_body_parts(box, plan))
    if plan.latch_count_resolved:
        hardware.extend(_latch_body_parts(box, plan))
    if hardware:
        body = union([body, *hardware])

    if eff.b4b.stacking and eff.b4b.lid:
        body = difference([body, *_stack_recesses(box)])

    return _weld(body)


# --------------------------------------------------------------------------- #
# lid
# --------------------------------------------------------------------------- #
def _skirt_polygons(eff: BoxSpec) -> tuple[Polygon, Polygon]:
    """(outer, inner) plan outlines of the locating spigot.

    The spigot drops into the cavity mouth, so it is measured from the *inner
    mating* face, not the outer one.  Measuring it from the outer face put its
    outer 0.65 mm inside the wall band itself, which is solid body - the lid
    then could not close at all, and past ~112 mm of case the resulting overlap
    tripped the validator and B4B stopped generating entirely.

    Keeping it inside the mating face also leaves the lid footprint exactly the
    body footprint, so B4Bs still sit side by side on the 8 mm lattice.
    """
    clr = B4B_LID_SEAT_CLEARANCE
    layout = b4b_layout(eff)
    outer = layout.inner_mating_polygon.buffer(-clr)
    inner = outer.buffer(-B4B_LID_SKIRT_WALL)
    if outer.is_empty or inner.is_empty:
        raise RuntimeError("B4B lid locating skirt collapsed inside the body wall")
    if not isinstance(outer, Polygon) or not isinstance(inner, Polygon):
        raise RuntimeError("B4B lid locating skirt must remain a single polygon")
    return outer, inner


def _skirt_lap(eff: BoxSpec) -> float:
    """How far the spigot may hang below the rim.

    It drops into the cavity mouth, where the tallest child bin is waiting, so
    the lap is capped by the headroom actually above that child - never by
    ``B4B_LID_SKIRT_LAP`` alone.
    """
    clearance_above_child = b4b_rim_z_from_eff(eff) - (eff.base_thickness + eff.z)
    return max(0.0, min(B4B_LID_SKIRT_LAP, clearance_above_child - B4B_LID_SEAT_CLEARANCE))


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

    # The plate sits *on* the rim - it must not reach below the underside datum,
    # because the wall now rises to exactly that datum and any dip would bury
    # the plate edge in solid body around the whole perimeter.
    skin = b4b_lid_skin_from_eff(eff)
    plate = _extrude_polygon(layout.outer_structural_polygon, skin)
    plate.apply_translation((0.0, 0.0, underside_z))

    lid = plate
    skirt_h = _skirt_lap(eff)
    if skirt_h >= 0.4:
        skirt_ring = outer.difference(inner)
        skirt_bottom = underside_z - skirt_h
        skirt = _extrude_polygon(skirt_ring, skirt_h)
        skirt.apply_translation((0.0, 0.0, skirt_bottom))
        # Keep the locating spigot to the two X-side walls only: the front
        # carries latches and the rear carries hinges, and a spigot dropping
        # past the rim there would clash with that hardware.  The side runs are
        # wavy, so they still locate the lid on both axes without a snap.
        case_x, _case_y = layout.case_size
        side_clip = trimesh.creation.box(
            extents=(case_x * 4.0,
                     2.0 * (layout.outer_half_y - CORNER_INSET - 2.0),
                     skirt_h + 20.0)
        )
        side_clip.apply_translation((0.0, 0.0, skirt_bottom + skirt_h / 2.0))
        skirt = _intersection([skirt, side_clip])
        lid = union([plate, skirt])

    hardware: list[trimesh.Trimesh] = []
    if plan.hinge_count:
        hardware.extend(_hinge_lid_parts(box, plan))
    if plan.latch_count_resolved:
        hardware.extend(_latch_lid_parts(box, plan))
    if hardware:
        lid = union([lid, *hardware])

    handle = b4b_handle_plan(box)
    if handle is not None:
        lid = difference([lid, *_handle_lid_bores(handle, skin)])

    if eff.b4b.stacking:
        lid = difference([lid, *_stack_lid_sockets(box)])

    return _weld(lid)


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
    top_z = b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff)
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
    top_z = b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff)
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
    """A round solid whose axis is world X, centred on the origin.

    Only correct for the separately printed latch lever, which is posed with
    that axis standing on the bed.  Anything that stays horizontal in print
    must use the support-free primitives below instead.
    """
    return _extrude_yz_profile(_round_profile_yz(radius), length)


def support_free_profile_yz(radius: float) -> Polygon:
    """Section of a horizontal X-axis boss that prints without support.

    Vertical faces at +/-Y, a flat at +Z and -Z, and 45-degree facets joining
    them.  Symmetric in Z, so the same section is right for the upright body
    and the lid printed upside down: whichever way up it goes, the only
    horizontal down-facing face is the short flat, bounded by
    ``B4B_SUPPORT_FREE_BRIDGE_MAX``, and every other down-facing facet is at
    exactly 45 degrees.
    """
    h = B4B_SUPPORT_FREE_FLAT * radius
    return Polygon([
        (radius, -h), (radius, h), (h, radius), (-h, radius),
        (-radius, h), (-radius, -h), (-h, -radius), (h, -radius),
    ])


def _support_free_boss(radius: float, length: float) -> trimesh.Trimesh:
    return _extrude_yz_profile(support_free_profile_yz(radius), length)


def support_free_bore_profile_yz(radius: float, roof_sign: float) -> Polygon:
    """Teardrop section for a horizontal X-axis bore.

    A round horizontal hole has an unsupported roof; this replaces it with two
    45-degree facets meeting at a ridge, so the bore closes itself.
    ``roof_sign`` is the *print-up* direction in assembly space: +1 for the
    body, which prints upright, and -1 for the lid, which is rolled 180 degrees
    about X so its assembly -Z faces the nozzle.  The inscribed diameter is
    untouched, so a clearance bore still passes the screw and a pilot still has
    full-depth material to thread-form into.
    """
    # Built as one clean ring rather than a Boolean union of a disc and a
    # triangle: a union leaves near-duplicate points at the tangents, and the
    # slivers they make do not extrude to a solid volume.
    start = math.pi * 0.75                      # the +Y tangent point
    sweep = math.pi * 1.5                       # the 270 degrees below the roof
    points = [
        (radius * math.cos(a), roof_sign * radius * math.sin(a))
        for a in np.linspace(start, start + sweep, 48)
    ]
    points.append((0.0, roof_sign * radius * math.sqrt(2.0)))
    if roof_sign < 0.0:
        points.reverse()
    tear = Polygon(points)
    if not tear.is_valid:
        raise RuntimeError("support-free bore section did not resolve")
    return tear


def _support_free_bore(
    radius: float, length: float, roof_sign: float
) -> trimesh.Trimesh:
    return _extrude_yz_profile(
        support_free_bore_profile_yz(radius, roof_sign), length
    )


def _hinge_seg(plan: B4BHardwarePlan) -> float:
    return plan.hinge_width / 3.0


def _knuckle(cx: float, axis_y: float, axis_z: float, width: float,
             radius: float) -> trimesh.Trimesh:
    k = _support_free_boss(radius, width)
    k.apply_translation((cx, axis_y, axis_z))
    return k


# --------------------------------------------------------------------------- #
# hardware root reinforcement
# --------------------------------------------------------------------------- #
def _pad_bottom_z(pad_top_z: float, face_u: float, outer_half: float) -> float:
    """Bottom of a root web's outward face.

    The web's underside is one continuous 45-degree plane running from that
    bottom edge back down into the wall, so the bottom may not sit so low that
    the taper leaves the case before it reaches solid wall.
    """
    reach = face_u - (outer_half - WAVE_AMPLITUDE)
    return max(pad_top_z - B4B_HW_PAD_HEIGHT, min(reach, pad_top_z - 2.0))


def _weld(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Collapse boolean noise so a finished part survives the 3MF writer.

    Where a 45-degree root taper grazes the wave, the boolean engine leaves the
    odd pair of vertices a micron apart.  They are harmless in memory, but the
    exporter merges on rounded coordinates, and merging one of those pairs
    tears the solid into two components and fails mesh validation.  Merge them
    here, on our own terms, and drop the degenerate triangles that fall out -
    never at the cost of a mesh that was watertight before.
    """
    before = mesh.is_watertight
    welded = mesh.copy()
    welded.merge_vertices(digits_vertex=5)
    welded.update_faces(welded.nondegenerate_faces(height=1e-6))
    welded.update_faces(welded.unique_faces())
    welded.remove_unreferenced_vertices()
    if before and not welded.is_watertight:
        return mesh
    return welded


def _filleted(profile: Polygon, radius: float) -> Polygon:
    """Round every re-entrant corner of a hardware section to ``radius``.

    A morphological *closing* - dilate then erode - adds material in internal
    corners and leaves external ones exactly as drawn, which is what a fillet
    is.  Sharp internal corners are where a printed bracket cracks off its
    wall, so every hardware section is filleted against the plate or the root
    web it grows out of, not merely unioned onto it.

    The arc it leaves is tangent to both faces, so its slope never leaves the
    range between them: filleting two faces that are each at least 45 degrees
    can never introduce a shallower overhang.
    """
    if radius <= 0.0:
        return profile
    closed = profile.buffer(radius, join_style=1, quad_segs=12).buffer(
        -radius, join_style=1, quad_segs=12
    )
    if closed.is_empty or not isinstance(closed, Polygon) or not closed.is_valid:
        return profile
    return closed


def _cavity_prism(
    box: BoxSpec, x0: float | None = None, x1: float | None = None
) -> trimesh.Trimesh:
    """The child-field cavity, as a cutter.

    Root webs are built reaching well inside the case and then trimmed on this,
    so they meet the authoritative inner mating face exactly at every point of
    the wave without ever stealing child-bin volume.

    A hardware group only ever needs the slice of cavity behind its own span, so
    callers pass that X window: the full cavity is a wavy prism of some sixteen
    thousand triangles, and cutting four root webs against all of it is most of
    the time a B4B preview takes to build.
    """
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    floor_z = eff.base_thickness
    top = b4b_rim_z_from_eff(eff) + 40.0
    outline = layout.inner_mating_polygon
    if x0 is not None and x1 is not None:
        reach = layout.outer_half_y + 10.0
        window = Polygon([(x0, -reach), (x1, -reach), (x1, reach), (x0, reach)])
        outline = outline.intersection(window)
        if outline.is_empty:
            raise RuntimeError("a B4B hardware group sits outside the case")
        if not isinstance(outline, Polygon):
            outline = max(outline.geoms, key=lambda part: part.area)
    cavity = _extrude_polygon(outline, top - floor_z)
    cavity.apply_translation((0.0, 0.0, floor_z))
    return cavity


def _pad_profile(
    box: BoxSpec, *, outward_sign: float, face_y: float, pad_top_z: float
) -> Polygon:
    """Y/Z section of the exterior root web under one hardware group.

    Starts well inside the inner mating face - the caller trims it there on the
    cavity - crosses the whole local wall band whatever ``wall`` the user chose,
    and grows outward to the fitting, so hinge torque and latch pull enter a
    dedicated structural zone instead of a fraction of a millimetre of Boolean
    overlap with a thin wall.  The underside is a single 45-degree taper back
    into the wall, so the body still prints upright with no support.
    """
    layout = b4b_layout(box)
    # an outward coordinate, so front and rear share one construction
    face_u = abs(face_y)
    deep_u = layout.inner_half_y - WAVE_AMPLITUDE - 1.0
    bottom_u_z = _pad_bottom_z(pad_top_z, face_u, layout.outer_half_y)
    run = face_u - deep_u
    profile = Polygon([
        (outward_sign * deep_u, pad_top_z),
        (outward_sign * face_u, pad_top_z),
        (outward_sign * face_u, bottom_u_z),
        (outward_sign * deep_u, bottom_u_z - run),
    ])
    lo_y, hi_y = sorted((outward_sign * deep_u, outward_sign * face_u))
    profile = profile.intersection(
        Polygon([
            (lo_y - 1.0, 0.0), (hi_y + 1.0, 0.0),
            (hi_y + 1.0, pad_top_z), (lo_y - 1.0, pad_top_z),
        ])
    )
    if profile.is_empty or not isinstance(profile, Polygon):
        raise RuntimeError("a B4B hardware root web collapsed")
    return profile


def _pad_end_chamfers(
    *,
    x_centre: float,
    half_width: float,
    face_y: float,
    outward_sign: float,
    web: float,
    z_top: float,
) -> list[trimesh.Trimesh]:
    """Cutters that taper a root web back into the wall at both ends.

    A rib that stops square on a wall concentrates peel right at its end face.
    Each end is chamfered at 45 degrees in plan, from the web face back to the
    wall crest, so the reinforcement fades out instead of stopping dead.  The
    run is capped by the margin the web carries beyond its fitting, so a thick
    web on a thin wall can never chamfer into the knuckles it supports.
    """
    run = min(web, B4B_HW_PAD_MARGIN_X - 0.3)
    if run <= 0.05:
        return []
    face_u = abs(face_y)
    big = 200.0
    cutters: list[trimesh.Trimesh] = []
    for sx in (-1.0, 1.0):
        x_end = x_centre + sx * half_width
        # the cut line, in (x, outward) space, through (x_end - sx*run, face)
        # and (x_end, face - run); everything beyond it goes
        corners_u = (face_u - run - big, face_u + big)
        pts = []
        for u in corners_u:
            pts.append((x_end + sx * (face_u - run - u), outward_sign * u))
        for u in reversed(corners_u):
            pts.append((x_end + sx * (face_u - run - u + 2.0 * big), outward_sign * u))
        cutter = _extrude_polygon(Polygon(pts), z_top + 20.0)
        cutter.apply_translation((0.0, 0.0, -10.0))
        cutters.append(cutter)
    return cutters


def _hinge_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """One reinforced rear hinge per centre: a root web through the full wall
    band, two filleted gussets rising from it, and the two support-free body
    knuckles."""
    eff = b4b_effective_box(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = plan.boss_radius
    fillet = plan.fillet_radius
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        half = plan.hinge_pad_width / 2.0 + 1.0
        cavity = _cavity_prism(box, cx - half, cx + half)
        pad_prof = _pad_profile(
            box,
            outward_sign=1.0,
            face_y=plan.hinge_pad_face_y,
            pad_top_z=plan.hinge_pad_top_z,
        )
        pad = _extrude_yz_profile(pad_prof, plan.hinge_pad_width)
        pad.apply_translation((cx, 0.0, 0.0))
        solid = pad
        bores: list[trimesh.Trimesh] = []
        for side, bore_r in (
            (-1.0, B4B_M3_CLEAR_BORE / 2.0),   # near: head bears here
            (1.0, B4B_M3_PILOT / 2.0),         # far: thread-forming lug
        ):
            kx = cx + side * seg
            root_y = plan.hinge_pad_face_y - 0.8      # bite into the web
            touch_y = plan.hinge_axis_y
            run = touch_y - root_y
            touch_lo_z = plan.hinge_axis_z - 0.5 * r
            # the gusset underside is one plane no shallower than 45 degrees,
            # and it starts inside the root web rather than on the wall skin
            root_z = min(plan.hinge_pad_top_z - 1.5, touch_lo_z - run)
            gusset_profile = Polygon([
                (root_y, root_z),
                (root_y, eff.z + 0.35),
                (touch_y, plan.hinge_axis_z + 0.5 * r),
                (touch_y, touch_lo_z),
            ])
            # Fillet the gusset against the web and the barrel as one section:
            # the knuckle load crosses those two internal corners, and a square
            # corner there is where the fitting would crack off the case.
            tower = _filleted(
                gusset_profile.union(
                    translate_polygon(
                        support_free_profile_yz(r),
                        plan.hinge_axis_y,
                        plan.hinge_axis_z,
                    )
                ).union(pad_prof),
                fillet,
            )
            knuckle = _extrude_yz_profile(tower, kw)
            knuckle.apply_translation((kx, 0.0, 0.0))
            solid = union([solid, knuckle])
            # the body prints upright, so its bore roof faces assembly +Z
            bore = _support_free_bore(bore_r, kw + 2.0, 1.0)
            bore.apply_translation((kx, plan.hinge_axis_y, plan.hinge_axis_z))
            bores.append(bore)
        chamfers = _pad_end_chamfers(
            x_centre=cx,
            half_width=plan.hinge_pad_width / 2.0,
            face_y=plan.hinge_pad_face_y,
            outward_sign=1.0,
            web=plan.hinge_web,
            z_top=plan.hinge_pad_top_z,
        )
        parts.append(difference([solid, cavity, *chamfers, *bores]))
    return parts


def _lid_root_profile(
    layout: B4BLayout,
    *,
    outward_sign: float,
    fitting_inner_y: float,
    underside_z: float,
    skin: float,
) -> Polygon:
    """Y/Z section of the arm that carries a lid fitting into the top plate.

    The fitting itself stands outboard of the case, so on its own it lands
    beside the plate rather than in it.  This arm reaches back under the plate,
    inside the plate own Z band, and is unioned into the fitting section before
    filleting - so the fitting grows out of the plate through a rounded root
    instead of being tacked onto its edge by a connectivity block.
    """
    reach = outward_sign * (
        layout.outer_half_y - WAVE_AMPLITUDE - 1.0 - B4B_LID_ROOT_REACH
    )
    bite = fitting_inner_y + outward_sign * B4B_LID_ROOT_BITE
    lo, hi = sorted((reach, bite))
    return Polygon([
        (lo, underside_z), (hi, underside_z),
        (hi, underside_z + skin), (lo, underside_z + skin),
    ])


def _hinge_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """The centre knuckle per hinge: barrel, the tab that drops to it, and the
    filleted arm that roots the whole fitting into the lid plate."""
    eff = b4b_effective_box(box)
    underside_z = b4b_lid_underside_z(box)
    skin = b4b_lid_skin_from_eff(eff)
    layout = b4b_layout(box)
    seg = _hinge_seg(plan)
    kw = seg - B4B_HINGE_AXIAL_GAP
    r = plan.boss_radius
    z_hi = underside_z + skin
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        lid_back = (
            layout.rear_wall_y(cx) + B4B_LID_SEAT_CLEARANCE
            + B4B_LID_SKIRT_WALL
        )
        # never inboard of the body root web: the two must not touch anywhere
        root_y = max(lid_back - 0.5, plan.hinge_pad_face_y + B4B_HW_CLEARANCE)
        tab_profile = Polygon([
            (root_y, underside_z - B4B_LID_FITTING_DROP),
            (root_y, z_hi),
            (plan.hinge_axis_y, z_hi),
            (plan.hinge_axis_y + r, plan.hinge_axis_z),
            (plan.hinge_axis_y, plan.hinge_axis_z - r),
        ])
        arm = _lid_root_profile(
            layout,
            outward_sign=1.0,
            fitting_inner_y=root_y,
            underside_z=underside_z,
            skin=skin,
        )
        barrel = translate_polygon(
            support_free_profile_yz(r), plan.hinge_axis_y, plan.hinge_axis_z
        )
        section = _filleted(
            tab_profile.union(barrel).union(arm), plan.fillet_radius
        )
        # Exactly the knuckle width, never wider: outboard of the plate edge
        # this Z band is the body barrel interleaved on the same pin, so a
        # root that spread sideways there would jam the closed lid.
        tab = _extrude_yz_profile(section, kw)
        tab.apply_translation((cx, 0.0, 0.0))
        # the lid prints rolled 180 degrees about X, so its bore roof is -Z
        bore = _support_free_bore(B4B_M3_CLEAR_BORE / 2.0, kw + 1.0, -1.0)
        bore.apply_translation((cx, plan.hinge_axis_y, plan.hinge_axis_z))
        parts.append(difference([tab, bore]))
    return parts


# --------------------------------------------------------------------------- #
# latch geometry: lid lever on an M3 pivot, engaging a second M3 cross-pin in
# compact body receiver ears.  All roots follow the derived local front wall.
# --------------------------------------------------------------------------- #
def _latch_frame(eff: BoxSpec, plan: B4BHardwarePlan) -> dict:
    """Thin reader over the hardware plan.

    Every latch datum is resolved once in :func:`b4b_hardware_plan`; nothing
    here recomputes one, so the lever, the receiver, the sweep check and the
    summary cannot disagree about where the pivot is.
    """
    return {
        "prof": plan.strength_profile,
        "axis_y": plan.pivot_axis_y,
        "axis_z": plan.pivot_axis_z,
        "catch_axis_y": plan.catch_axis_y,
        "catch_axis_z": plan.catch_axis_z,
        "hook_outer_r": plan.hook_outer_r,
        "underside_z": b4b_lid_underside_z_from_eff(eff),
        "ear_t": plan.strength_profile["pad_wall"],
        "boss_r": plan.boss_radius,
    }


def _latch_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """One reinforced front receiver per latch: the catch-pin ears standing on
    an exterior web whose thickness is the profile catch_thickness."""
    eff = b4b_effective_box(box)
    boss_r = plan.boss_radius
    ear_t = plan.catch_ear_thickness
    fillet = plan.fillet_radius
    parts: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        half = plan.latch_pad_width / 2.0 + 1.0
        cavity = _cavity_prism(box, cx - half, cx + half)
        pad_prof = _pad_profile(
            box,
            outward_sign=-1.0,
            face_y=plan.latch_pad_face_y,
            pad_top_z=plan.latch_pad_top_z,
        )
        pad = _extrude_yz_profile(pad_prof, plan.latch_pad_width)
        pad.apply_translation((cx, 0.0, 0.0))
        solid = pad
        inner_face = plan.lever_width / 2.0 + B4B_HINGE_AXIAL_GAP
        bores: list[trimesh.Trimesh] = []
        for side, bore_r in (
            (-1.0, B4B_M3_CLEAR_BORE / 2.0),   # near: head bears here
            (1.0, B4B_M3_PILOT / 2.0),         # far: thread-forming lug
        ):
            ex = cx + side * (inner_face + ear_t / 2.0)
            root_y = plan.latch_pad_face_y + 0.8       # bite into the web
            touch_y = plan.catch_axis_y
            touch_lo_z = plan.catch_axis_z - 0.5 * boss_r
            root_z = plan.catch_root_z
            support_profile = Polygon([
                (root_y, root_z),
                (root_y, eff.z + 0.35),
                (touch_y, plan.catch_axis_z + 0.5 * boss_r),
                (touch_y, touch_lo_z),
            ])
            ear = _filleted(
                support_profile.union(
                    translate_polygon(
                        support_free_profile_yz(boss_r),
                        plan.catch_axis_y,
                        plan.catch_axis_z,
                    )
                ).union(pad_prof),
                fillet,
            )
            solid = union([
                solid,
                translated(_extrude_yz_profile(ear, ear_t), (ex, 0.0, 0.0)),
            ])
            bore = _support_free_bore(bore_r, ear_t + 2.0, 1.0)
            bore.apply_translation((ex, plan.catch_axis_y, plan.catch_axis_z))
            bores.append(bore)
        chamfers = _pad_end_chamfers(
            x_centre=cx,
            half_width=plan.latch_pad_width / 2.0,
            face_y=plan.latch_pad_face_y,
            outward_sign=-1.0,
            web=plan.latch_web,
            z_top=plan.latch_pad_top_z,
        )
        parts.append(difference([solid, cavity, *chamfers, *bores]))
    return parts


def _latch_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two pivot ears per latch, rooted into the lid plate through a filleted
    arm rather than hung off its edge."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    f = _latch_frame(eff, plan)
    parts: list[trimesh.Trimesh] = []
    ear_t = f["ear_t"]
    lug_t = _latch_lug_thickness(ear_t)   # far ear is a real thread-forming lug
    skin = b4b_lid_skin_from_eff(eff)
    top = f["underside_z"] + skin
    boss_r = plan.boss_radius
    for cx in plan.latch_centers_x:
        inner_face = plan.latch_width / 2.0 + B4B_HINGE_AXIAL_GAP
        for side, thickness, bore_r in (
            (-1.0, ear_t, B4B_M3_CLEAR_BORE / 2.0),
            (1.0, lug_t, B4B_M3_PILOT / 2.0),
        ):
            ex = cx + side * (inner_face + thickness / 2.0)
            wall_root = (
                layout.front_wall_y(ex) - B4B_LID_SEAT_CLEARANCE
                - B4B_LID_SKIRT_WALL + 0.5
            )
            # stand clear of the body receiver web: the arm, not a near miss
            # against the case, is what ties this ear to the plate
            root_y = min(wall_root, plan.latch_pad_face_y - B4B_HW_CLEARANCE)
            profile = Polygon([
                (root_y, f["underside_z"] - B4B_LID_FITTING_DROP),
                (root_y, top),
                (f["axis_y"] - boss_r, top),
                (f["axis_y"] - boss_r, f["axis_z"] - boss_r),
                (f["axis_y"] + 0.5 * boss_r, f["axis_z"] - boss_r),
            ])
            arm = _lid_root_profile(
                layout,
                outward_sign=-1.0,
                fitting_inner_y=root_y,
                underside_z=f["underside_z"],
                skin=skin,
            )
            boss = translate_polygon(
                support_free_profile_yz(boss_r), f["axis_y"], f["axis_z"]
            )
            section = _filleted(
                profile.union(boss).union(arm), plan.fillet_radius
            )
            # Exactly the ear thickness: the lever swings in the slot beside
            # it and the body catch ear interleaves on the other side, so a
            # wider root here would rub one of them.
            ear = _extrude_yz_profile(section, thickness)
            ear.apply_translation((ex, 0.0, 0.0))
            # the lid prints rolled 180 degrees about X, so its bore roof is -Z
            bore = _support_free_bore(bore_r, thickness + 2.0, -1.0)
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
    lever_w = plan.lever_width
    levers: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        # the lever prints on its broad face, so round sections here are right
        pivot_r = plan.boss_radius
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
        # The mouth is what the pin snaps through, so its width *is* the snap
        # force.  Size it off the profile's detent so "lightweight" and
        # "standard" actually differ: a fixed fraction of the bore gave both
        # the same 0.41 mm interference no matter which strength was chosen.
        mouth_half = max(0.4, (B4B_M3_NOMINAL - prof["detent"]) / 2.0)
        opening = Polygon([
            (f["catch_axis_y"], f["catch_axis_z"] - mouth_half),
            (f["catch_axis_y"] + hook_outer_r * 2.5, f["catch_axis_z"] - mouth_half),
            (f["catch_axis_y"] + hook_outer_r * 2.5, f["catch_axis_z"] + mouth_half),
            (f["catch_axis_y"], f["catch_axis_z"] + mouth_half),
        ])
        profile = profile.difference(hook_bore.union(opening))
        # The two jaws root at the mouth in a pair of square internal corners,
        # and that is exactly where a hook snapped over a pin cracks.  Fillet
        # them; the radius is taken off the mouth so it can never close it.
        profile = _filleted(profile, min(plan.fillet_radius, 0.4 * mouth_half))
        lever = _extrude_yz_profile(profile, lever_w)
        lever.apply_translation((cx, 0.0, 0.0))
        bore = _x_cylinder(B4B_M3_CLEAR_BORE / 2.0, lever_w + 4.0)
        bore.apply_translation((cx, f["axis_y"], f["axis_z"]))
        lever = difference([lever, bore])
        levers.append(lever)
    return levers


def _handle_lid_bores(plan: B4BHandlePlan, skin: float) -> list[trimesh.Trimesh]:
    """Pilot holes through the lid plate for the handle screws.

    The plate is the thread-forming lug - a handled lid is made thick enough to
    be one (see :func:`b4b_lid_skin_from_eff`), so nothing hangs below it into
    the child bins' headroom and nothing stands above it to spoil the flat face
    the lid prints on.  The holes are on the print axis, so they need no
    teardrop of their own.
    """
    bores: list[trimesh.Trimesh] = []
    for cx in plan.centers_x:
        bore = trimesh.creation.cylinder(
            radius=B4B_M3_PILOT / 2.0, height=skin + 2.0, sections=32
        )
        bore.apply_translation((cx, 0.0, plan.top_z - skin / 2.0))
        bores.append(bore)
    return bores


def make_b4b_handle(box: BoxSpec) -> trimesh.Trimesh | None:
    """The carrying handle, in assembly space, standing on the lid top.

    One extruded arch: feet, uprights and a grip bar, filleted inside and
    rounded outside.  It prints on its broad face, so every wall of that
    silhouette stands square to the bed and none of it needs support; only the
    two screw holes run horizontally in that pose, and those are teardropped.
    """
    plan = b4b_handle_plan(box)
    if plan is None:
        return None
    half = plan.span / 2.0
    foot = plan.foot_length / 2.0
    post = plan.upright / 2.0
    z1 = plan.foot_height
    z2 = z1 + plan.grip_clear
    z3 = z2 + plan.grip_thickness

    def rect(x0: float, z0: float, x1: float, z_top: float) -> Polygon:
        return Polygon([(x0, z0), (x1, z0), (x1, z_top), (x0, z_top)])

    profile = (
        rect(-half - foot, 0.0, -half + foot, z1)
        .union(rect(half - foot, 0.0, half + foot, z1))
        .union(rect(-half - post, z1, -half + post, z2))
        .union(rect(half - post, z1, half + post, z2))
        .union(rect(-half - post, z2, half + post, z3))
    )
    if not isinstance(profile, Polygon) or not profile.is_valid:
        raise RuntimeError("the B4B handle outline did not resolve")
    # Fillet where the uprights meet the feet and the grip - the two corners a
    # carried case loads - then round the outside so there are no sharp edges
    # in the hand.
    profile = _rounded(_filleted(profile, plan.fillet), plan.fillet)

    handle = _extrude_xz_profile(profile, plan.depth)
    handle.apply_translation((0.0, 0.0, plan.top_z))
    bores: list[trimesh.Trimesh] = []
    for cx in plan.centers_x:
        # Printed on its side, this hole lies horizontal with assembly +Y
        # facing the nozzle, so it is roofed that way.  The section is the same
        # teardrop the case hardware uses; here its two axes read as X and Y.
        bore = _extrude_polygon(
            support_free_bore_profile_yz(B4B_M3_CLEAR_BORE / 2.0, 1.0),
            plan.foot_height + 2.0,
        )
        bore.apply_translation((cx, 0.0, plan.top_z - 1.0))
        bores.append(bore)
    return _weld(difference([handle, *bores]))


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
                plan.catch_ear_thickness + plan.lever_width
                + 2.0 * B4B_HINGE_AXIAL_GAP,
                plan.catch_ear_thickness,
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

    # A bolted-on handle is static, so it needs no sweep - only proof that it
    # generates as one solid and stands *on* the lid rather than into it.
    if lid is not None:
        handle = make_b4b_handle(box)
        if handle is not None:
            from organizer_engine import intersection_volume

            if not handle.is_watertight or handle.volume <= 0.0:
                raise ValueError("the B4B handle did not generate as a watertight solid")
            overlap = intersection_volume(handle, lid) / 1000.0
            if overlap > 0.05:
                raise ValueError(
                    f"the handle cuts into the lid rather than bolting to it "
                    f"(overlap {overlap:.3f} cc)"
                )

    if not b4b.secure_lid:
        return

    # Tolerances (cc).  These are geometry/boolean-noise bounds, NOT room for a
    # real mechanical clash: the assembled closed state has a small, expected
    # overlap (interleaved hinge knuckles, seated skirt, the latch detent
    # ridge), and what the sweep must show is that motion does not add
    # interference beyond boolean noise on top of that baseline.
    NOISE_CC = 0.05                       # motion may not add more than this
    # The lever swings on real printed running clearance - B4B_LATCH_BODY_CLEARANCE
    # across the receiver web and B4B_HINGE_AXIAL_GAP against the catch ears - so
    # it must not touch the body at all when closed, only boolean noise.
    LATCH_CLOSED_CEIL_CC = 0.05
    # Same standard for the lid: the knuckles interleave on running gaps and
    # the spigot drops into a clearance fit, so a closed lid rests on its rim
    # and touches nothing else.
    LID_CLOSED_CEIL_CC = 0.05

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
                f"a latch lever touches the body's catch receiver when closed "
                f"(overlap {closed:.3f} cc, allowance {LATCH_CLOSED_CEIL_CC:.2f} cc); "
                f"it must swing on clearance, not rub"
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
                f"the closed lid binds against the body "
                f"(overlap {closed:.3f} cc, allowance {LID_CLOSED_CEIL_CC:.2f} cc); "
                f"it must seat on its rim, not jam on its hardware"
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

    if b4b.handle:
        handle = b4b_handle_plan(box)
        if handle is None:
            raise ValueError("the handle did not resolve for this B4B")
        if handle.screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("handle screw length did not resolve to an allowed M3 length")
        if handle.span < handle.foot_length + B4B_HANDLE_MIN_OPENING:
            raise ValueError("the handle has no usable hand opening on this B4B")

    if b4b.secure_lid:
        eff = b4b_effective_box(box)
        plan = b4b_hardware_plan(box)
        if plan.hinge_count != 2:
            raise ValueError("a secure B4B lid needs exactly two hinges")
        # --- printability and structure, not just "it resolved to a number" ---
        bearing = plan.boss_radius * _SUPPORT_FREE_INSCRIBED
        need_bearing = B4B_M3_HEAD_CLEAR / 2.0 + B4B_M3_HEAD_EDGE_MARGIN
        if bearing + _EPS < need_bearing:
            raise ValueError(
                f"an M3 head bears on only {bearing:.2f} mm of boss (need "
                f"{need_bearing:.2f} mm: {B4B_M3_HEAD_CLEAR:.1f} mm head plus "
                f"{B4B_M3_HEAD_EDGE_MARGIN:.1f} mm of edge margin)"
            )
        bridge = 2.0 * B4B_SUPPORT_FREE_FLAT * plan.boss_radius
        if bridge > B4B_SUPPORT_FREE_BRIDGE_MAX + _EPS:
            raise ValueError(
                f"the support-free boss section would bridge {bridge:.2f} mm "
                f"unsupported (limit {B4B_SUPPORT_FREE_BRIDGE_MAX:.1f} mm)"
            )
        if plan.hinge_lug_thickness + _EPS < B4B_HINGE_LUG_TARGET:
            raise ValueError(
                f"the hinge thread-forming lug is {plan.hinge_lug_thickness:.2f} mm, "
                f"below the {B4B_HINGE_LUG_TARGET:.1f} mm safety target"
            )
        pad_half = plan.hinge_pad_width / 2.0
        reach = max(abs(cx) for cx in plan.hinge_centers_x) + pad_half
        corner_limit = (
            layout.outer_half_x - CORNER_INSET - B4B_HINGE_CLEAR_KEEPOUT
        )
        if reach > corner_limit + _EPS:
            raise ValueError(
                f"a reinforced hinge reaches {reach - corner_limit:.2f} mm into "
                f"the rear corner keep-out; grow the B4B"
            )
        centre_gap = 2.0 * min(abs(cx) for cx in plan.hinge_centers_x) - plan.hinge_pad_width
        if centre_gap + _EPS < B4B_HINGE_CENTRE_GAP:
            raise ValueError(
                f"the two hinge root webs are only {centre_gap:.2f} mm apart "
                f"(need {B4B_HINGE_CENTRE_GAP:.1f} mm)"
            )
        for what, web in (("hinge", plan.hinge_web), ("latch", plan.latch_web)):
            root_t = eff.wall_depth + web
            if root_t + _EPS < B4B_HW_ROOT_MIN_THICKNESS:
                raise ValueError(
                    f"the {what} root is only {root_t:.2f} mm thick (need "
                    f"{B4B_HW_ROOT_MIN_THICKNESS:.1f} mm); hardware strength "
                    f"must not follow the wall setting"
                )
        if plan.hinge_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("hinge pin length did not resolve to an allowed M3 length")
        if plan.latch_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("latch pin length did not resolve to an allowed M3 length")
        if plan.catch_screw_length_mm not in B4B_SCREW_LENGTHS:
            raise ValueError("catch pin length did not resolve to an allowed M3 length")

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
    top_z = (
        b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff) if b4b.lid else eff.z
    )
    if b4b.secure_lid:
        # Measured off the authoritative reinforced envelopes, so the quoted
        # assembled size cannot understate the printed hardware.
        boss_out = plan.boss_radius * _SUPPORT_FREE_CIRCUM
        hinge_min_x = min(cx - plan.hinge_pad_width / 2.0 for cx in plan.hinge_centers_x)
        hinge_max_x = max(cx + plan.hinge_pad_width / 2.0 for cx in plan.hinge_centers_x)
        latch_min_x = min(cx - plan.latch_pad_width / 2.0 for cx in plan.latch_centers_x)
        latch_max_x = max(cx + plan.latch_pad_width / 2.0 for cx in plan.latch_centers_x)
        min_x = min(min_x, hinge_min_x, latch_min_x)
        max_x = max(max_x, hinge_max_x, latch_max_x)
        min_y = min(min_y, plan.pivot_axis_y - boss_out)
        max_y = max(max_y, plan.hinge_axis_y + boss_out)
        top_z = max(top_z, plan.hinge_axis_z + plan.boss_radius)
    handle = b4b_handle_plan(box)
    if handle is not None:
        top_z = max(top_z, handle.top_z + handle.height)
        min_x = min(min_x, handle.centers_x[0] - handle.foot_length / 2.0)
        max_x = max(max_x, handle.centers_x[1] + handle.foot_length / 2.0)
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
        "handle": handle is not None,
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
    if handle is not None:
        summary["hardware"]["handle_screw"] = f"M3x{handle.screw_length_mm}"
        summary["hardware"]["handle_qty"] = 2
        bom = summary["hardware_bom"]
        line = f"2 x M3x{handle.screw_length_mm} handle screws"
        # keep "No nuts" last, as the reassurance it is
        bom.insert(max(0, len(bom) - 1) if bom else 0, line)
        if not bom or bom[-1] != "No nuts":
            bom.append("No nuts")
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
        body = _weld(union([body, frame]))
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
            lid, inlay = _apply_top_label(box, lid)
            geometry.extend(_mesh_preview_geometry(inlay, "b4b_label"))
        geometry.extend(_mesh_preview_geometry(lid, "b4b_lid"))
    handle = make_b4b_handle(box)
    if handle is not None:
        geometry.extend(_mesh_preview_geometry(handle, "b4b_handle"))
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
    keepouts: list[Polygon] = []
    if eff.b4b.stacking and eff.b4b.lid:
        r = (
            B4B_STACK_BOSS_DIAMETER / 2.0
            + B4B_STACK_FEMALE_RADIAL_CLEARANCE
            + B4B_TOP_LABEL_MARGIN
        )
        keepouts.extend(
            Point(cx, cy).buffer(r, quad_segs=24)
            for cx, cy in _stack_locator_centres(eff)
        )
    handle = b4b_handle_plan(eff)
    if handle is not None:
        hx = handle.foot_length / 2.0 + B4B_TOP_LABEL_MARGIN
        hy = handle.depth / 2.0 + B4B_TOP_LABEL_MARGIN
        for cx in handle.centers_x:
            keepouts.append(Polygon([
                (cx - hx, -hy), (cx + hx, -hy), (cx + hx, hy), (cx - hx, hy),
            ]))
    return keepouts


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
    handle = b4b_handle_plan(eff)
    if handle is not None:
        # The handle straddles the middle of the lid, so the label takes the
        # clear strip in front of it rather than shrinking to nothing under it.
        front = -case_y / 2.0 + B4B_TOP_LABEL_MARGIN
        back = -handle.depth / 2.0 - B4B_TOP_LABEL_MARGIN
        avail_h = back - front
        label_cy = (front + back) / 2.0
        if avail_h < TEXT_CAP_HEIGHT_MIN:
            raise ValueError(
                "there is no clear space on the lid for a top label beside the "
                "handle; use a front label, or turn the handle off"
            )
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
    top_z = b4b_lid_underside_z(box) + b4b_lid_skin(box)
    pocket = text_prism(outline, top_z, depth=TEXT_DEPTH)
    inlay = text_prism(outline, top_z, depth=TEXT_DEPTH)
    return _weld(difference([lid, pocket])), inlay


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
        receiver_r = plan.boss_radius * _SUPPORT_FREE_CIRCUM
        # clear of both the catch boss and the receiver web's 45-degree taper
        top_z = min(
            plan.catch_axis_z - receiver_r - 2.0,
            plan.latch_pad_bottom_z - plan.latch_web - 1.0,
        )
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
    elif kind == "handle":
        # lay the arch on its broad face: its silhouette is extruded along
        # local Y, so that axis rolls onto the bed's Z and every wall of the
        # arch stands square to the bed
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
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

    handle = make_b4b_handle(box)
    if handle is not None:
        groups.append([("B4B Handle", _print_pose(handle, "handle"))])

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
