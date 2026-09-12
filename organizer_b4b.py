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
# The one place this expression is written.  The UI reads it from the catalog
# rather than duplicating the arithmetic, and the geometry below reads this
# name rather than the two constants, so the two can never drift apart.
B4B_STACK_MIN_BASE = B4B_STACK_RECESS_DEPTH + B4B_MIN_FLOOR_SKIN
B4B_STACK_BOSS_DIAMETER = 5.0
B4B_STACK_FEMALE_RADIAL_CLEARANCE = 0.25
B4B_STACK_SOCKET_DEPTH = 1.6
B4B_STACK_SOCKET_INTERFERENCE = 0.08
B4B_STACK_INSET_FRACTION = 0.16  # locator centre inset from each outer edge
B4B_STACK_INSET_MIN = 4.0

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

# --- support-free integrated hardware -------------------------------------- #
# Every integrated hinge/latch/handle barrel has its axis on world X and prints
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

# --- automatic hardware profiles ------------------------------------------- #
# Hardware size is never a user setting.  One family is selected for the whole
# case by :func:`b4b_hardware_family` and every hinge, latch, catch and handle
# pivot is proportioned from the profile it resolves to.  Ordinary socket-head
# metric screws from a common assortment kit; no nuts, no inserts, no shoulder
# screws, no specialty hinge pins.
#
# The running gap between any two printed parts that must move against each
# other.  0.20 mm was a boolean gap, not a printed one: at FDM tolerances the
# two faces fuse and the joint has to be broken free.
B4B_RUNNING_GAP = 0.30
# Maximum screw tail past the far face of its thread-forming lug.  The exact
# stacks below are designed to produce zero tail; this is the acceptance limit.
B4B_SCREW_MAX_TAIL = 0.5


@dataclass(frozen=True)
class HardwareProfile:
    """One metric screw family and every B4B dimension derived from it.

    Exact first-build values.  Only the three physical-calibration fields -
    ``pilot``, ``clear_bore`` and the detent interferences held elsewhere - are
    expected to move after test prints, and they move here, once, for every
    fitting at the same time.
    """

    name: str
    nominal: float
    clear_bore: float          # rotating / through member
    pilot: float               # printed thread-forming terminal lug
    engage_min: float          # minimum real thread bite
    head_diameter: float       # maximum physical socket-head outside diameter
    head_bearing_min: float    # minimum solid material around that head
    lengths: tuple[int, ...]   # permitted standard kit lengths, mm
    pivot_radius: float        # ordinary hinge knuckle / latch pivot ear
    catch_radius: float        # body catch ear - carries no rotation
    bore_shell: float          # minimum printed shell around the clearance bore
    # exact axial stacks (outboard screw head -> case centre)
    near_ear: float
    mid_member: float          # lid centre ear / latch lever / catch span
    far_lug: float
    # latch
    latch_draw: float          # pivot axis down to catch axis
    pivot_standoff: float      # lid latch pivot axis, outward of front crest
    catch_standoff: float      # body catch axis, outward of front crest
    hinge_standoff: float      # hinge axis, outward of rear crest
    strap_thickness: float
    hook_wall: float
    hook_mouth: float
    hook_lead_in: float
    lip_out: float
    lip_length: float
    lever_fillet: float
    # roots
    hinge_root_width: float
    hinge_root_height: float
    hinge_root_depth: float    # inner mating face -> outer reinforcement
    latch_root_width: float
    latch_root_height: float
    latch_root_depth: float

    @property
    def group_width(self) -> float:
        """Total axial width of a pivot stack."""
        return (
            self.near_ear + self.mid_member + self.far_lug
            + 2.0 * B4B_RUNNING_GAP
        )

    @property
    def clear_span(self) -> float:
        """Clearance-bored stack the screw crosses before its lug."""
        return self.near_ear + self.mid_member + 2.0 * B4B_RUNNING_GAP

    @property
    def catch_inner_radius(self) -> float:
        """Hook bore that rides on the catch screw shank."""
        return self.nominal / 2.0 + 0.25

    @property
    def hook_outer_radius(self) -> float:
        return self.catch_inner_radius + self.hook_wall

    def bore_radius(self, terminal: bool) -> float:
        return (self.pilot if terminal else self.clear_bore) / 2.0

    @property
    def head_bearing_margin(self) -> float:
        """Actual head-bearing material on the uniform outer barrels."""
        radius = min(self.pivot_radius, self.catch_radius)
        return radius * _SUPPORT_FREE_INSCRIBED - self.head_diameter / 2.0

    @property
    def required_uniform_radius(self) -> float:
        """Smallest uniform ear radius that protects both bore and screw head."""
        return max(
            self.clear_bore / 2.0 + self.bore_shell,
            (self.head_diameter / 2.0 + self.head_bearing_min)
            / _SUPPORT_FREE_INSCRIBED,
        )


B4B_HW_M2 = HardwareProfile(
    name="M2",
    nominal=2.0,
    clear_bore=2.3,
    pilot=1.7,
    engage_min=2.4,
    head_diameter=4.0,
    head_bearing_min=0.2,
    lengths=(6, 8, 10, 12, 16),
    pivot_radius=2.4,
    catch_radius=2.4,
    bore_shell=1.2,
    near_ear=2.2,
    mid_member=2.6,
    far_lug=2.6,
    latch_draw=9.0,
    pivot_standoff=2.85,
    catch_standoff=2.6,
    hinge_standoff=2.75,
    strap_thickness=2.0,
    hook_wall=1.4,
    hook_mouth=1.8,
    hook_lead_in=0.6,
    lip_out=1.2,
    lip_length=2.5,
    lever_fillet=0.8,
    hinge_root_width=11.0,
    hinge_root_height=8.0,
    hinge_root_depth=2.6,
    latch_root_width=10.8,
    latch_root_height=9.0,
    latch_root_depth=2.6,
)
B4B_HW_M3 = HardwareProfile(
    name="M3",
    nominal=3.0,
    clear_bore=3.4,
    pilot=2.6,
    engage_min=3.0,
    head_diameter=5.7,
    head_bearing_min=0.2,
    lengths=(6, 8, 10, 12, 16, 20),
    pivot_radius=3.2,
    catch_radius=3.2,
    bore_shell=1.3,
    near_ear=2.8,
    mid_member=3.2,
    far_lug=3.4,
    latch_draw=10.5,
    pivot_standoff=3.45,
    catch_standoff=3.1,
    hinge_standoff=3.35,
    strap_thickness=2.4,
    hook_wall=1.6,
    hook_mouth=2.8,
    hook_lead_in=0.8,
    lip_out=1.5,
    lip_length=3.0,
    lever_fillet=1.0,
    hinge_root_width=13.6,
    hinge_root_height=10.0,
    hinge_root_depth=3.0,
    latch_root_width=13.4,
    latch_root_height=11.0,
    latch_root_depth=3.0,
)

# --- deterministic family selection ---------------------------------------- #
# One rule in one helper, so preview, export, validation and BOM cannot
# disagree.  A handled case is intentionally all-M3 rather than M2 hinges and
# latches with M3 handle pivots: one kit, one driver, one BOM line.
B4B_HW_M2_MAX_FIELD_XY = 96.0
B4B_HW_M2_MAX_FIELD_Z = 64.0

# --- minimum case ---------------------------------------------------------- #
# A B4B is a carrying case, not a bin with hardware bolted on.  Below this the
# hardware would be the product, so B4B is refused rather than grown.
B4B_MIN_FIELD_XY = 48.0
# A secure lid still needs a printable body wall below its catch receiver.
B4B_LATCHED_MIN_HEIGHT = 16.0
# B4B wall floor and default.  A repeatedly opened, latched, hinged and carried
# case is the wrong place for a two-line wall; 1.2 mm is roughly three lines on
# a nominal 0.4 mm nozzle.  The child field stays authoritative, so the extra
# material grows outward and costs no capacity.
B4B_MIN_WALL = 1.2

# --- hardware reinforcement ------------------------------------------------ #
# Hinge, latch and handle loads must not run through a sub-millimetre overlap
# with the user's wall.  Each group sits on its own exterior root that starts
# at the inner mating face, crosses the whole local wall band and grows
# outward to the profile's ``*_root_depth``.
B4B_HW_CLEARANCE = 0.6            # static gap, body fitting to lid fitting
# A root is two tapered buttresses under its two ears, not a slab: the moving
# member (latch lever, handle bail) nests in the relief between them.  This is
# the running gap left around that member when the relief is cut.
B4B_HW_RELIEF_CLEARANCE = 0.5

# Lid-side roots: the fitting grows out of the plate through an arm that is
# part of its own section, not a block tacked on afterwards.
B4B_LID_ROOT_BITE = 1.0           # how far the arm overlaps the fitting
B4B_LID_ROOT_REACH = 4.0          # run into the plate, away from its edge
B4B_LID_FITTING_DROP = 1.6        # how far a lid fitting hangs below the plate

# Every hardware section is filleted where it meets the plate or the root it
# grows from: a square internal corner is where a printed bracket cracks off.
B4B_HW_FILLET = 1.0

# Print-bed layout: parts are packed in a row, none overlapping.
B4B_PRINT_PART_GAP = 8.0

# Stacking boss self-locating lead-in (a real printed taper, not a claim).
B4B_STACK_BOSS_CHAMFER = 0.6

# --- rear hinges (exactly two on every secure lid) ------------------------- #
B4B_HINGE_COUNT = 2
# Lid opening requirement.  This is a case lid, not a fold-flat box.
B4B_LID_OPEN_ANGLE = 120.0
B4B_SWEEP_STEP_DEG = 5.0
# Hinge centres are nominally +/- child_x/4, pulled inward only far enough to
# keep this much root clear of the wall's corner tangent.
B4B_ROOT_CORNER_CLEARANCE = 2.0
B4B_HINGE_CENTRE_GAP = 4.0       # clear run between the two hinge roots
# Rear lid relief is the first response to a sweep collision; only if this much
# is not enough may the axis move rearward at all.
B4B_LID_RELIEF_MAX = 1.2
B4B_HINGE_AXIS_STEP = 0.05       # quantum for any forced rearward move
# Review ceilings on the actual uniform pivot envelope.
B4B_HINGE_MAX_PROJECTION = {"M2": 5.75, "M3": 7.0}

# --- front latches --------------------------------------------------------- #
# Deterministic count from one authoritative threshold, never "however many
# old-style pads happened to fit".
B4B_LATCH_TWO_ABOVE_FIELD_X = 96.0
B4B_LATCH_RELEASE_ANGLE = 25.0   # hook must be off the pin by here
B4B_LATCH_OPEN_ANGLE = 75.0      # full sampled swing
B4B_LATCH_DETENT = 0.20          # hook-mouth interference against the pin
B4B_LATCH_MAX_PROJECTION = {"M2": 6.0, "M3": 9.0}

# --- folding front handle -------------------------------------------------- #
# A U/bail on the *body* front wall.  The lid carries no handle load at all, so
# the carry force goes straight into the case shell instead of through the lid,
# the latches and the rear hinges - and the lid top stays free for stacking.
B4B_HANDLE_PROFILE = B4B_HW_M3     # handle hardware is M3 only
B4B_HANDLE_GRIP_MIN = 72.0         # below this it is not an adult handle
B4B_HANDLE_GRIP_MAX = 95.0         # a hand does not benefit from more
B4B_HANDLE_GRIP_FRACTION = 0.75    # of the child field width, then clamped
B4B_HANDLE_BAND = 6.5              # in-plane band width of the lower U
B4B_HANDLE_EYE_BAND = 5.4          # tapered band at the pivot eye
# The fork's own axial stack.  It is NOT the hinge/latch stack: the rotating
# member here is the 5.4 mm handle eye, not a 3.2 mm lid ear, so the fork is
# 12.0 mm wide and its near ear is 2.6 mm.  Reusing the hinge stack put the
# eye straight through both ears.
B4B_HANDLE_NEAR_EAR = 2.6
B4B_HANDLE_FAR_LUG = 3.4
B4B_HANDLE_FORK_WIDTH = (
    B4B_HANDLE_NEAR_EAR + B4B_HANDLE_EYE_BAND + B4B_HANDLE_FAR_LUG
    + 2.0 * B4B_RUNNING_GAP
)
B4B_HANDLE_FORK_CLEAR_SPAN = (
    B4B_HANDLE_NEAR_EAR + B4B_HANDLE_EYE_BAND + 2.0 * B4B_RUNNING_GAP
)
B4B_HANDLE_TAPER_RUN = 8.0         # vertical run of that taper
B4B_HANDLE_EYE_RADIUS = 2.9
B4B_HANDLE_THICKNESS = 2.0 * B4B_HANDLE_EYE_RADIUS   # 5.8 front-to-back
B4B_HANDLE_CORNER_RADIUS = 7.5     # lower U centreline radius
B4B_HANDLE_DROP = 29.0             # preferred pivot axis to grip centre
B4B_HANDLE_DROP_MIN = 26.0
B4B_HANDLE_WALL_CLEAR = 0.6        # folded running gap to the wall crest
B4B_HANDLE_BOTTOM_MARGIN = 4.0     # clear run above the case bottom
B4B_HANDLE_RIM_DROP = 8.0          # pivot axis below the rim/lid-seat datum
B4B_HANDLE_STOP_ANGLE = 95.0       # deployed carry stop
B4B_HANDLE_STOP_FACE = 2.5         # minimum Y/Z contact length at the stop
B4B_HANDLE_DETENT = 0.20           # stow detent interference
B4B_HANDLE_DETENT_BUMP = 0.35      # body bump height
B4B_HANDLE_DETENT_RAMP = 0.5
B4B_HANDLE_MAX_PROJECTION = 7.25   # folded hardware envelope
# Softening on the exposed perimeter edge.  The opposite face stays perfectly
# flat: it is the bail's print bed.
B4B_HANDLE_EDGE_CHAMFER = 1.0
B4B_HANDLE_EDGE_STEPS = 4
B4B_HANDLE_FORK_ROOT_WIDTH = 16.0
B4B_HANDLE_ROOT_ABOVE = 6.0        # root reach above the pivot centre
B4B_HANDLE_ROOT_BELOW = 12.0       # and below it
B4B_HANDLE_ROOT_DEPTH = 3.0        # inner mating face -> outer reinforcement

# --- front interactions ---------------------------------------------------- #
B4B_FRONT_ROOT_SEPARATION = 1.0    # visible normal wall between root regions
B4B_LABEL_KEEPOUT = 1.0            # label clearance around moving hardware

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

    ``max(requested, B4B_STACK_MIN_BASE)`` when stacking is on, otherwise the
    requested value.  Never redefines the normal Standard Base.
    """
    b4b = box.b4b.normalised()
    requested = box.base_thickness
    if b4b.stacking and b4b.lid:
        return max(requested, B4B_STACK_MIN_BASE)
    return requested


def b4b_hardware_family(box: BoxSpec) -> HardwareProfile:
    """The one hardware family this whole case uses.

    Deterministic and consulted from a single place, so the preview, the
    exported geometry, the validation report and the BOM can never disagree
    about which kit the user needs.  A handled case is all-M3 on purpose: one
    driver, one bag of screws, one BOM line, rather than M2 hinges and latches
    with M3 handle pivots.
    """
    b4b = box.b4b.normalised()
    if b4b.handle:
        return B4B_HW_M3
    if (
        box.x <= B4B_HW_M2_MAX_FIELD_XY + _EPS
        and box.y <= B4B_HW_M2_MAX_FIELD_XY + _EPS
        and box.z <= B4B_HW_M2_MAX_FIELD_Z + _EPS
    ):
        return B4B_HW_M2
    return B4B_HW_M3


def b4b_required_min_wall(box: BoxSpec) -> float:
    """The wall a mode *requires*, never a reduction of a thicker choice.

    One helper so the promotion rule lives in a single place: B4B and the
    stacking load paths need real material, an ordinary non-stacking bin does
    not, and nothing here may ever push a user's thicker wall back down.
    """
    if box.b4b.enabled:
        return B4B_MIN_WALL
    stack = getattr(box, "stack", None)
    if stack is not None and getattr(stack, "mode", "none") != "none":
        return B4B_MIN_WALL
    return 0.0


def b4b_min_field(box: BoxSpec) -> tuple[float, float]:
    """Smallest child field B4B will build, per axis.

    A flat product rule, not a hardware-fit search: below this the hinges,
    latches and handle would *be* the product.  B4B is refused rather than
    grown, so the entered field always survives into the geometry.
    """
    return B4B_MIN_FIELD_XY, B4B_MIN_FIELD_XY


def b4b_secure_min_height() -> float:
    """Smallest entered child height a secure lid is offered on."""
    return B4B_LATCHED_MIN_HEIGHT


def _usable_front_span(layout: "B4BLayout") -> float:
    """Straight run of the front wall between the two corner tangents."""
    return 2.0 * (layout.outer_half_x - CORNER_INSET)


def _root_centres(
    layout: "B4BLayout", nominal: float, root_width: float, count: int
) -> tuple[float, ...]:
    """Symmetric hardware centres at ``+/- nominal``, pulled *inward* only.

    Hardware never shifts outward and never breaks symmetry: the only reason a
    centre moves at all is to keep its root clear of the wall's corner tangent.
    """
    if count == 1:
        return (0.0,)
    limit = (
        layout.outer_half_x - CORNER_INSET
        - B4B_ROOT_CORNER_CLEARANCE - root_width / 2.0
    )
    centre = min(nominal, limit)
    if centre <= root_width / 2.0 + B4B_HINGE_CENTRE_GAP / 2.0:
        centre = root_width / 2.0 + B4B_HINGE_CENTRE_GAP / 2.0
    return (-centre, centre)


def b4b_handle_grip_target(child_x: float) -> float:
    """Clear grip this case *wants*, before asking whether it fits.

    A hand is a hand whatever the case measures, so the grip follows the case
    only between an adult minimum and an ergonomic cap; past the cap a larger
    B4B keeps the same grip instead of spreading the bail to the corners.
    """
    return min(
        B4B_HANDLE_GRIP_MAX,
        max(B4B_HANDLE_GRIP_MIN, B4B_HANDLE_GRIP_FRACTION * child_x),
    )


def b4b_handle_width_fit(box: BoxSpec) -> tuple[bool, float, float]:
    """``(fits, required_pivot_span, max_pivot_span)`` for the front bail.

    Pure geometry against the real front wall, not a hard-coded width rule: the
    two pivot forks each need half their axial envelope plus a corner keep-out,
    and what is left has to span the target clear grip plus one band width.
    """
    layout = b4b_layout(box)
    max_pivot_span = _usable_front_span(layout) - 2.0 * (
        B4B_HANDLE_FORK_WIDTH / 2.0 + B4B_ROOT_CORNER_CLEARANCE
    )
    required = b4b_handle_grip_target(b4b_effective_box(box).x) + B4B_HANDLE_BAND
    return max_pivot_span + _EPS >= required, required, max_pivot_span


def b4b_lid_skin_from_eff(eff: BoxSpec) -> float:
    """Authoritative lid top-plate thickness.

    A secure lid carries its hinge and latch roots in this plate, so it is
    thicker than a passive one.  The handle is no longer part of this decision:
    it mounts to the body front wall and puts no load into the lid at all, so
    a handled lid is exactly a secure lid.  Every lid datum - plate, top Z,
    hinge axis, latch pivot, stacking socket roof, label pocket, envelope
    summary - reads this one helper so they cannot drift apart.
    """
    b4b = eff.b4b.normalised()
    return B4B_SECURE_LID_SKIN if b4b.secure_lid else B4B_LID_SKIN


def b4b_lid_skin(box: BoxSpec) -> float:
    return b4b_lid_skin_from_eff(b4b_effective_box(box))


def b4b_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec every B4B builder uses.

    An effective-*material* normaliser, not a dimension mutator.  The entered
    child field is authoritative and survives untouched: X, Y and Z are never
    grown to make a hinge, a latch or a handle fit.  A field that cannot carry
    the hardware is reported by validation and gated in the UI instead.

    The only thing that still moves is base thickness, and only far enough to
    leave a printable floor skin under a stacking recess - which changes no
    child dimension.  Easy Clean and the flat-inside band are forced off
    because they alter the floor and perimeter the child bins seat on.
    """
    b4b = box.b4b.normalised()
    return replace(
        box,
        base_thickness=b4b_effective_base_thickness(box),
        easy_clean=False,
        easy_clean_style="bevel",
        flat_inside=0.0,
        b4b=b4b,
    )


def b4b_grew(box: BoxSpec) -> bool:
    """Whether anything about the effective box differs from the request.

    The child field is authoritative and is never touched, so the only thing
    this can still report is the stacking base: a recessed underside needs a
    printable floor skin beneath it.  That changes no child dimension and no
    capacity, and it is reported as what it is rather than as the box having
    been resized.
    """
    eff = b4b_effective_box(box)
    if not (
        math.isclose(eff.x, box.x)
        and math.isclose(eff.y, box.y)
        and math.isclose(eff.z, box.z)
    ):
        raise RuntimeError(
            "B4B changed the requested child field - the effective box must "
            "never resize X, Y or Z"
        )
    return not math.isclose(eff.base_thickness, box.base_thickness)


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
    """Every hinge/latch dimension, resolved once from one hardware profile.

    Preview, export, BOM and validation all read this, so they cannot disagree
    about which family the case uses or where a pivot sits.
    """

    profile: HardwareProfile
    hinge_count: int
    hinge_centers_x: tuple[float, ...]
    hinge_width: float
    hinge_screw_length_mm: int
    hinge_axis_y: float
    hinge_axis_z: float
    hinge_rear_crest: float
    hinge_root_width: float
    hinge_root_top_z: float
    hinge_root_face_y: float
    lid_rear_relief: float
    latch_count_resolved: int
    latch_centers_x: tuple[float, ...]
    latch_screw_length_mm: int
    catch_screw_length_mm: int
    pivot_axis_y: float
    pivot_axis_z: float
    catch_axis_y: float
    catch_axis_z: float
    latch_front_crest: float
    latch_root_width: float
    latch_root_top_z: float
    latch_root_face_y: float
    fillet_radius: float = 0.0

    # -- derived reporting ------------------------------------------------- #
    @property
    def family(self) -> str:
        return self.profile.name

    @property
    def hinge_projection(self) -> float:
        """Rear projection of the uniform pivot envelope past the wall crest.

        Measured along Y, which is the direction the projection is in.  The
        support-free section has a *vertical face* at each Y extreme, so it
        reaches exactly its nominal radius there; ``_SUPPORT_FREE_CIRCUM``
        describes the diagonal to a facet join and would overstate this by
        about 6%.
        """
        return (
            self.hinge_axis_y - self.hinge_rear_crest + self.profile.pivot_radius
        )

    @property
    def latch_projection(self) -> float:
        """Closed front projection: the lever's pivot end is the outermost
        normal feature, and the hook sits inboard of it by design."""
        return (
            self.latch_front_crest - self.pivot_axis_y + self.profile.pivot_radius
        )

    def screw_bom(self) -> list[str]:
        lines: list[str] = []
        fam = self.profile.name
        if self.hinge_count:
            lines.append(
                f"{self.hinge_count} x {fam}x{self.hinge_screw_length_mm} hinge pins"
            )
        if self.latch_count_resolved:
            lines.append(
                f"{self.latch_count_resolved} x {fam}x{self.latch_screw_length_mm} "
                f"latch pivots"
            )
            lines.append(
                f"{self.latch_count_resolved} x {fam}x{self.catch_screw_length_mm} "
                f"catch pins"
            )
        lines.append("No nuts")
        return lines


def _screw_for_stack(
    profile: HardwareProfile, clear_span_mm: float, lug_thickness_mm: float, what: str
) -> int:
    """Authoritative kit-screw choice for one pivot.

    The screw enters at the head-bearing face, crosses ``clear_span_mm`` of
    clearance-bored material (ears and running gaps), then thread-forms into a
    terminal lug ``lug_thickness_mm`` thick.  Returns the shortest permitted
    length for the family that reaches the minimum engagement without leaving
    more than ``B4B_SCREW_MAX_TAIL`` past the far face.

    The exact stacks in the profiles are designed so the answer is a zero-tail
    screw - M2x8, M3x10, M3x12 for the handle.  This still *derives* that
    rather than hard-coding it, so a later change to an ear thickness cannot
    silently leave the BOM wrong.

    Real thread engagement can never exceed the lug, so a lug thinner than the
    family minimum is a geometry bug and is rejected here rather than papered
    over with a longer screw.
    """
    if lug_thickness_mm + _EPS < profile.engage_min:
        raise ValueError(
            f"the {what} terminal lug is only {lug_thickness_mm:.2f} mm thick - "
            f"less than the {profile.engage_min:.1f} mm minimum {profile.name} "
            f"thread engagement; widen the hardware"
        )
    for length in profile.lengths:
        beyond = length - clear_span_mm
        if beyond + _EPS < profile.engage_min:
            continue
        if beyond - lug_thickness_mm <= B4B_SCREW_MAX_TAIL + _EPS:
            return length
        break
    allowed = ", ".join(f"{profile.name}x{n}" for n in profile.lengths)
    raise ValueError(
        f"no kit screw ({allowed}) fits the {what} pivot: a "
        f"{clear_span_mm:.2f} mm clearance stack into a {lug_thickness_mm:.2f} mm "
        f"lug needs at least {profile.engage_min:.1f} mm of thread with no more "
        f"than {B4B_SCREW_MAX_TAIL:.1f} mm of tail"
    )


def _front_span(box: BoxSpec) -> float:
    """Usable straight run of the front wall between corner tangents."""
    return _usable_front_span(b4b_layout(box))


def _wall_extreme_y(
    layout: B4BLayout, x0: float, x1: float, outward_sign: float
) -> float:
    """Outermost Y the named wall reaches anywhere across ``[x0, x1]``.

    Hardware roots sit across a run of a wavy wall, so they have to be
    referenced to the wall's crest over that whole run, not to the wave value
    at one sample point.
    """
    steps = max(9, int(abs(x1 - x0) * 4.0) + 1)
    xs = np.linspace(x0, x1, steps)
    if outward_sign > 0.0:
        return max(layout.rear_wall_y(float(v)) for v in xs)
    return min(layout.front_wall_y(float(v)) for v in xs)


def _local_wall_crest_for_ear(
    layout: B4BLayout, x_centre: float, ear_thickness: float, outward_sign: float
) -> float:
    """Wall crest over one ear's true axial width, not its whole root span."""
    half = ear_thickness / 2.0
    return _wall_extreme_y(layout, x_centre - half, x_centre + half, outward_sign)


def _ear_wall_anchor_y(
    layout: B4BLayout, x_centre: float, ear_thickness: float,
    outward_sign: float, wall_depth: float,
) -> float:
    """Anchor a gusset inside its local structural wall band.

    The cavity trim remains authoritative. This deliberate bite therefore
    gives every ear a real wall load path without spending child-bin capacity.
    """
    crest = _local_wall_crest_for_ear(
        layout, x_centre, ear_thickness, outward_sign
    )
    bite = min(0.7, 0.5 * wall_depth)
    return crest - outward_sign * bite


def _root_outward(profile_depth: float, wall_depth: float) -> float:
    """How far a root's outer face stands beyond the local wall crest.

    The profile states a *total* structural depth measured from the inner
    mating face, so the reinforcement is whatever that target has left over
    after the user's wall - and it grows outward only, never into the field.
    """
    return max(0.0, profile_depth - wall_depth)


def _lid_rear_section(
    layout: B4BLayout, underside_z: float, skin: float, relief: float
) -> Polygon:
    """Y/Z outline of the lid's rear edge band, with its relief chamfer.

    Only the plate matters for the opening sweep: the lid's own hinge ear is
    centred on the axis and therefore cannot move relative to the body.
    """
    crest = layout.outer_half_y + WAVE_AMPLITUDE
    inner = -crest
    top = underside_z + skin
    if relief <= 0.0:
        return Polygon([
            (inner, underside_z), (crest, underside_z),
            (crest, top), (inner, top),
        ])
    # a 45-degree support-free relief taken off the rear-bottom corner
    r = min(relief, skin - 0.4)
    return Polygon([
        (inner, underside_z), (crest - r, underside_z),
        (crest, underside_z + r), (crest, top), (inner, top),
    ])


def _body_rear_section(
    layout: B4BLayout, rim_z: float, root_face_y: float, root_top_z: float,
    root_bottom_z: float,
) -> Polygon:
    """Y/Z outline of everything on the body the opening lid could strike."""
    crest = layout.outer_half_y + WAVE_AMPLITUDE
    shell = Polygon([
        (-crest - 10.0, 0.0), (crest, 0.0), (crest, rim_z), (-crest - 10.0, rim_z),
    ])
    if root_face_y <= crest + _EPS or root_top_z <= root_bottom_z:
        return shell
    rib = Polygon([
        (crest, root_bottom_z), (root_face_y, root_bottom_z),
        (root_face_y, root_top_z), (crest, root_top_z),
    ])
    merged = shell.union(rib)
    return merged if isinstance(merged, Polygon) else shell


def _sweep_clear_2d(
    moving: Polygon, fixed: Polygon, axis_y: float, axis_z: float,
    angles_deg: tuple[float, ...],
) -> bool:
    """Whether ``moving`` clears ``fixed`` at every sampled opening angle.

    A cheap plan-space proof used to *place* the hinge axis.  The full
    mesh-level sweep in :func:`_validate_b4b_mechanics` still runs at
    generation time; this only has to be right enough to choose a datum.
    """
    from shapely.affinity import rotate as rotate_polygon

    for deg in angles_deg:
        if deg == 0.0:
            continue
        turned = rotate_polygon(
            moving, -deg, origin=(axis_y, axis_z), use_radians=False
        )
        if turned.intersection(fixed).area > 1e-4:
            return False
    return True


def _sweep_angles(limit: float, step: float = B4B_SWEEP_STEP_DEG) -> tuple[float, ...]:
    """``0, step, 2*step, ... limit`` inclusive of both ends."""
    n = int(math.ceil(limit / step))
    out = [min(i * step, limit) for i in range(n + 1)]
    if abs(out[-1] - limit) > _EPS:
        out.append(limit)
    return tuple(out)


def _solve_hinge_axis(
    layout: B4BLayout, profile: HardwareProfile, *, rear_crest: float,
    underside_z: float, skin: float, axis_z: float, root_face_y: float,
    root_top_z: float, root_bottom_z: float,
) -> tuple[float, float]:
    """``(axis_y, rear_lid_relief)`` for a collision-free 120-degree opening.

    Relief first, axis movement last: a small support-free chamfer on the rear
    lid edge is always preferable to pushing the whole hinge further behind the
    case, which is what made the old hardware look like a backpack.  The axis
    only moves if the full permitted relief is still not enough, and then by
    the smallest quantised step that clears the sweep.
    """
    angles = _sweep_angles(B4B_LID_OPEN_ANGLE)
    axis_y = rear_crest + profile.hinge_standoff
    body = _body_rear_section(
        layout, underside_z, root_face_y, root_top_z, root_bottom_z
    )
    relief = 0.0
    while relief <= B4B_LID_RELIEF_MAX + _EPS:
        lid = _lid_rear_section(layout, underside_z, skin, relief)
        if _sweep_clear_2d(lid, body, axis_y, axis_z, angles):
            return axis_y, relief
        relief += 0.2
    relief = B4B_LID_RELIEF_MAX
    lid = _lid_rear_section(layout, underside_z, skin, relief)
    limit = rear_crest + profile.hinge_standoff + 4.0
    while axis_y <= limit:
        if _sweep_clear_2d(lid, body, axis_y, axis_z, angles):
            return axis_y, relief
        axis_y += B4B_HINGE_AXIS_STEP
    raise ValueError(
        "the B4B lid cannot be opened to "
        f"{B4B_LID_OPEN_ANGLE:g} degrees without striking the body; the rear "
        "hinge geometry needs design review"
    )


def _inactive_plan(profile: HardwareProfile) -> B4BHardwarePlan:
    return B4BHardwarePlan(
        profile=profile,
        hinge_count=0,
        hinge_centers_x=(),
        hinge_width=0.0,
        hinge_screw_length_mm=0,
        hinge_axis_y=0.0,
        hinge_axis_z=0.0,
        hinge_rear_crest=0.0,
        hinge_root_width=0.0,
        hinge_root_top_z=0.0,
        hinge_root_face_y=0.0,
        lid_rear_relief=0.0,
        latch_count_resolved=0,
        latch_centers_x=(),
        latch_screw_length_mm=0,
        catch_screw_length_mm=0,
        pivot_axis_y=0.0,
        pivot_axis_z=0.0,
        catch_axis_y=0.0,
        catch_axis_z=0.0,
        latch_front_crest=0.0,
        latch_root_width=0.0,
        latch_root_top_z=0.0,
        latch_root_face_y=0.0,
    )


def b4b_hardware_plan(box: BoxSpec) -> B4BHardwarePlan:
    eff = b4b_effective_box(box)
    profile = b4b_hardware_family(eff)
    if not eff.b4b.secure_lid:
        return _inactive_plan(profile)

    layout = b4b_layout(box)
    skin = b4b_lid_skin_from_eff(eff)
    underside_z = b4b_lid_underside_z_from_eff(eff)
    lid_top_z = underside_z + skin
    fillet = min(B4B_HW_FILLET, 0.5 * B4B_LID_FITTING_DROP, 0.3 * profile.pivot_radius)
    wall_depth = eff.wall_depth

    # ---- rear hinges: exactly two, nominally at +/- child_x/4 -------------- #
    hinge_centers_x = _root_centres(
        layout, eff.x / 4.0, profile.hinge_root_width, B4B_HINGE_COUNT
    )
    hinge_half = profile.hinge_root_width / 2.0
    rear_crest = max(
        _wall_extreme_y(layout, cx - hinge_half, cx + hinge_half, +1.0)
        for cx in hinge_centers_x
    )
    hinge_root_out = _root_outward(profile.hinge_root_depth, wall_depth)
    hinge_root_face_y = rear_crest + hinge_root_out
    # The axis sits at the lid plate band so the knuckle's upper flat lands on
    # the bed when the lid is printed upside down.
    hinge_axis_z = lid_top_z - profile.pivot_radius
    # The root has to stop short of wherever the lid-side knuckle reaches back
    # over it, or the closed lid would rest on its own reinforcement.
    inboard = max(0.0, profile.hinge_standoff - hinge_root_out)
    reach_down = math.sqrt(
        max(0.0, profile.pivot_radius ** 2 - inboard ** 2)
    )
    hinge_root_top_z = min(
        underside_z - 1.0, hinge_axis_z - reach_down - B4B_HW_CLEARANCE
    )
    hinge_root_bottom_z = max(1.0, hinge_root_top_z - profile.hinge_root_height)
    hinge_axis_y, lid_relief = _solve_hinge_axis(
        layout, profile,
        rear_crest=rear_crest,
        underside_z=underside_z,
        skin=skin,
        axis_z=hinge_axis_z,
        root_face_y=hinge_root_face_y,
        root_top_z=hinge_root_top_z,
        root_bottom_z=hinge_root_bottom_z,
    )
    hinge_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "hinge"
    )

    # ---- front latches: user override, else one authoritative width threshold #
    if eff.b4b.latch_count == "1":
        latch_count = 1
    elif eff.b4b.latch_count == "2":
        latch_count = 2
    else:
        latch_count = 1 if eff.x <= B4B_LATCH_TWO_ABOVE_FIELD_X + _EPS else 2
    latch_centers_x = _root_centres(
        layout, eff.x / 6.0, profile.latch_root_width, latch_count
    )
    latch_half = profile.latch_root_width / 2.0
    front_crest = min(
        _wall_extreme_y(layout, cx - latch_half, cx + latch_half, -1.0)
        for cx in latch_centers_x
    )
    pivot_axis_z = lid_top_z - profile.pivot_radius
    catch_axis_z = pivot_axis_z - profile.latch_draw
    pivot_axis_y = front_crest - profile.pivot_standoff
    catch_axis_y = front_crest - profile.catch_standoff
    latch_root_out = _root_outward(profile.latch_root_depth, wall_depth)
    latch_root_face_y = front_crest - latch_root_out
    # Same rule as the hinge: the root stops below the lid's pivot ear so the
    # lever swings on running clearance instead of rubbing its own receiver.
    pivot_inboard = max(0.0, profile.pivot_standoff - latch_root_out)
    pivot_down = math.sqrt(
        max(0.0, profile.pivot_radius ** 2 - pivot_inboard ** 2)
    )
    latch_root_top_z = min(
        underside_z - 1.0, pivot_axis_z - pivot_down - B4B_HW_CLEARANCE
    )
    if latch_root_top_z - profile.latch_root_height < 0.5:
        raise ValueError(
            f"a {eff.z:g} mm B4B is too short for a secure lid: the latch "
            f"receiver needs {profile.latch_root_height:.0f} mm of front wall "
            f"below the lid seam; use at least "
            f"{B4B_LATCHED_MIN_HEIGHT:g} mm of bin height"
        )
    latch_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "latch pivot"
    )
    catch_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "catch"
    )

    return B4BHardwarePlan(
        profile=profile,
        hinge_count=B4B_HINGE_COUNT,
        hinge_centers_x=hinge_centers_x,
        hinge_width=profile.group_width,
        hinge_screw_length_mm=hinge_screw,
        hinge_axis_y=hinge_axis_y,
        hinge_axis_z=hinge_axis_z,
        hinge_rear_crest=rear_crest,
        hinge_root_width=profile.hinge_root_width,
        hinge_root_top_z=hinge_root_top_z,
        hinge_root_face_y=hinge_root_face_y,
        lid_rear_relief=lid_relief,
        latch_count_resolved=latch_count,
        latch_centers_x=latch_centers_x,
        latch_screw_length_mm=latch_screw,
        catch_screw_length_mm=catch_screw,
        pivot_axis_y=pivot_axis_y,
        pivot_axis_z=pivot_axis_z,
        catch_axis_y=catch_axis_y,
        catch_axis_z=catch_axis_z,
        latch_front_crest=front_crest,
        latch_root_width=profile.latch_root_width,
        latch_root_top_z=latch_root_top_z,
        latch_root_face_y=latch_root_face_y,
        fillet_radius=fillet,
    )


# --------------------------------------------------------------------------- #
# folding front handle
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BHandlePlan:
    """Every folding-bail dimension, resolved once.

    The handle is a single printed U pivoted on two forks that grow out of the
    *body* front wall.  The lid carries none of its load, so a carried case
    hangs from the shell rather than from the lid, the latches and the rear
    hinges - and the lid top stays clear for stacking.
    """

    profile: HardwareProfile
    pivot_span: float          # between the two screw centres
    centers_x: tuple[float, float]
    clear_grip: float          # between the inner faces of the two arms
    drop: float                # pivot axis to grip centreline
    band: float                # in-plane band width of the lower U
    eye_band: float            # tapered band at the pivot eye
    thickness: float           # front-to-back, folded
    eye_radius: float
    corner_radius: float
    axis_y: float
    axis_z: float
    front_crest: float
    wall_clear: float
    stop_angle: float
    detent_interference: float
    detent_bump: float
    detent_centers_x: tuple[float, float]
    detent_z: float
    root_width: float
    root_face_y: float
    root_top_z: float
    root_bottom_z: float
    screw_length_mm: int

    @property
    def projection(self) -> float:
        """Folded projection past the front wall crest, at the handle eye.

        Measured along Y like every other projection: the support-free section
        presents a vertical face at its Y extremes, so it reaches its nominal
        radius and no further.
        """
        return self.front_crest - self.axis_y + self.eye_radius

    @property
    def eye_projection(self) -> float:
        return self.front_crest - self.axis_y + self.eye_radius

    @property
    def grip_z(self) -> float:
        return self.axis_z - self.drop


def b4b_handle_min_width(box: BoxSpec) -> float:
    """Smallest child X (mm), rounded up to a whole mm, that lets this B4B's
    front wall carry a handle.

    Binary search over the real front-wall fit check rather than a
    hard-coded width rule, so it tracks wall thickness, latch layout, and
    every other geometry input the same way ``b4b_handle_width_fit`` does.
    """
    lo, hi = 1.0, max(box.x, B4B_HANDLE_GRIP_MIN)
    while not b4b_handle_width_fit(replace(box, x=hi))[0]:
        hi *= 2.0
        if hi > 5000.0:
            break
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if b4b_handle_width_fit(replace(box, x=mid))[0]:
            hi = mid
        else:
            lo = mid
    return math.ceil(hi - 1e-6)


def b4b_handle_eligibility(box: BoxSpec) -> tuple[bool, str]:
    """``(eligible, reason)`` - why this case can or cannot carry a bail.

    Derived from the actual front wall every time, never from a remembered
    width rule, and it never asks for the case to grow: a B4B that cannot take
    a handle is still a perfectly good B4B.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.secure_lid:
        return False, "Handle requires a secure lid."
    fits, required, available = b4b_handle_width_fit(box)
    if not fits:
        min_width = b4b_handle_min_width(box)
        return False, f"Minimum size must be {min_width:g} mm wide."
    axis_z = b4b_rim_z_from_eff(eff) - B4B_HANDLE_RIM_DROP
    available_drop = axis_z - B4B_HANDLE_BOTTOM_MARGIN - B4B_HANDLE_BAND / 2.0
    if min(B4B_HANDLE_DROP, available_drop) + _EPS < B4B_HANDLE_DROP_MIN:
        return False, "Handle needs more front-wall height."
    return True, ""


def b4b_handle_plan(box: BoxSpec) -> B4BHandlePlan | None:
    """Resolve the bail, or ``None`` when this design has none.

    Raises with an actionable message when a handle is asked for on a case that
    cannot carry one, rather than quietly leaving it off a design that says it
    has one.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.handle:
        return None
    eligible, reason = b4b_handle_eligibility(box)
    if not eligible:
        raise ValueError(
            f"this B4B cannot take a carrying handle: {reason.rstrip('.')}; "
            f"turn the handle off, or use a wider or taller B4B"
        )

    layout = b4b_layout(box)
    profile = B4B_HANDLE_PROFILE
    clear_grip = b4b_handle_grip_target(eff.x)
    pivot_span = clear_grip + B4B_HANDLE_BAND
    half = pivot_span / 2.0

    fork_half = B4B_HANDLE_FORK_WIDTH / 2.0
    front_crest = min(
        _wall_extreme_y(layout, -half - fork_half, half + fork_half, -1.0),
        _wall_extreme_y(layout, -half, half, -1.0),
    )
    axis_y = front_crest - (B4B_HANDLE_EYE_RADIUS + B4B_HANDLE_WALL_CLEAR)
    axis_z = b4b_rim_z_from_eff(eff) - B4B_HANDLE_RIM_DROP
    available_drop = axis_z - B4B_HANDLE_BOTTOM_MARGIN - B4B_HANDLE_BAND / 2.0
    drop = min(B4B_HANDLE_DROP, available_drop)

    root_out = _root_outward(B4B_HANDLE_ROOT_DEPTH, eff.wall_depth)
    root_face_y = front_crest - root_out
    root_top_z = axis_z + B4B_HANDLE_ROOT_ABOVE
    root_bottom_z = max(1.0, axis_z - B4B_HANDLE_ROOT_BELOW)

    # Stow detents sit near the lower corners of the folded U, where the arms
    # are long enough to flex over them at a light finger force.
    detent_z = axis_z - drop + B4B_HANDLE_CORNER_RADIUS
    detent_cx = half - B4B_HANDLE_BAND / 2.0

    screw = _screw_for_stack(
        profile, B4B_HANDLE_FORK_CLEAR_SPAN, B4B_HANDLE_FAR_LUG, "handle pivot"
    )
    return B4BHandlePlan(
        profile=profile,
        pivot_span=pivot_span,
        centers_x=(-half, half),
        clear_grip=clear_grip,
        drop=drop,
        band=B4B_HANDLE_BAND,
        eye_band=B4B_HANDLE_EYE_BAND,
        thickness=B4B_HANDLE_THICKNESS,
        eye_radius=B4B_HANDLE_EYE_RADIUS,
        corner_radius=B4B_HANDLE_CORNER_RADIUS,
        axis_y=axis_y,
        axis_z=axis_z,
        front_crest=front_crest,
        wall_clear=B4B_HANDLE_WALL_CLEAR,
        stop_angle=B4B_HANDLE_STOP_ANGLE,
        detent_interference=B4B_HANDLE_DETENT,
        detent_bump=B4B_HANDLE_DETENT_BUMP,
        detent_centers_x=(-detent_cx, detent_cx),
        detent_z=detent_z,
        root_width=B4B_HANDLE_FORK_ROOT_WIDTH,
        root_face_y=root_face_y,
        root_top_z=root_top_z,
        root_bottom_z=root_bottom_z,
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
    # The handle is body hardware now: its forks grow out of the front wall, so
    # a carried case hangs from the shell rather than from the lid, the latches
    # and the rear hinges.
    hardware.extend(_handle_body_parts(box))
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

    if plan.lid_rear_relief > 0.0:
        lid = difference([lid, _lid_rear_relief_cutter(box, plan)])

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


def _round_bore(radius: float, length: float) -> trimesh.Trimesh:
    """True circular X-axis bore for small bridged M2/M3 hardware holes."""
    return _extrude_yz_profile(Point(0.0, 0.0).buffer(radius, quad_segs=32), length)


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


def _handle_fork_positions(centre_x: float) -> tuple[float, float]:
    """``(near_ear_x, far_lug_x)`` for one handle fork.

    Unlike a hinge or latch stack, this is laid out about the *eye* rather than
    about the group centre: ``centre_x`` is the pivot axis, the eye sits on it,
    and the two ears stand off it by one running gap each.  The near (head)
    ear is outboard and the thread-forming lug faces the case centre, so both
    screws go in from the sides and the middle of the case stays clean.
    """
    out = 1.0 if centre_x >= 0.0 else -1.0
    inner = B4B_HANDLE_EYE_BAND / 2.0 + B4B_RUNNING_GAP
    near = centre_x + out * (inner + B4B_HANDLE_NEAR_EAR / 2.0)
    far = centre_x - out * (inner + B4B_HANDLE_FAR_LUG / 2.0)
    return near, far


def _stack_positions(
    centre_x: float, profile: HardwareProfile
) -> tuple[float, float, float]:
    """``(near_ear_x, mid_member_x, far_lug_x)`` centres for one pivot stack.

    The stack is laid out from the *outboard* screw-head side toward the case
    centre, so on a symmetric pair both heads face outward and both
    thread-forming lugs face in.  One driver, both sides, and the visual centre
    of the case stays clean.
    """
    out = 1.0 if centre_x >= 0.0 else -1.0
    half = profile.group_width / 2.0
    near = centre_x + out * (half - profile.near_ear / 2.0)
    mid = centre_x + out * (
        half - profile.near_ear - B4B_RUNNING_GAP - profile.mid_member / 2.0
    )
    far = centre_x - out * (half - profile.far_lug / 2.0)
    return near, mid, far


def _root_profile_yz(
    box: BoxSpec, *, outward_sign: float, face_y: float, top_z: float, height: float
) -> Polygon:
    """Y/Z section of the exterior root under one hardware group.

    Starts well inside the inner mating face - the caller trims it there on the
    cavity - crosses the whole local wall band whatever wall the user chose,
    and grows outward to the profile's structural depth, so hinge torque, latch
    pull and carry load enter a dedicated zone instead of a fraction of a
    millimetre of Boolean overlap with a thin wall.  The underside is a single
    45-degree taper back into the wall, so the body still prints upright with
    no support.
    """
    layout = b4b_layout(box)
    face_u = abs(face_y)
    deep_u = layout.inner_half_y - WAVE_AMPLITUDE - 1.0
    bottom_u_z = max(0.6, top_z - height)
    run = face_u - deep_u
    s = outward_sign
    profile = Polygon([
        (s * deep_u, top_z),
        (s * face_u, top_z),
        (s * face_u, bottom_u_z),
        (s * deep_u, bottom_u_z - run),
    ])
    lo_y, hi_y = sorted((s * deep_u, s * face_u))
    profile = profile.intersection(
        Polygon([
            (lo_y - 1.0, 0.0), (hi_y + 1.0, 0.0),
            (hi_y + 1.0, top_z), (lo_y - 1.0, top_z),
        ])
    )
    if profile.is_empty or not isinstance(profile, Polygon):
        raise RuntimeError("a B4B hardware root collapsed")
    return profile


def _root_taper_prism(
    *, centre_x: float, root_width: float, group_width: float,
    outward_sign: float, crest_y: float, face_y: float, z_lo: float, z_hi: float,
) -> trimesh.Trimesh:
    """Plan-view keeper that fades a root from its wall contact to its pivot.

    The root is full ``root_width`` where it meets the wall and narrows to the
    pivot group's own width at its outer face.  A rib that stops square on a
    wall concentrates peel right at its end face; this is the taper that lets
    the reinforcement fade out instead of stopping dead, and it is what keeps
    the finished hardware from reading as a rectangular pad bolted on.
    """
    rw = root_width / 2.0
    gw = group_width / 2.0
    deep = crest_y - outward_sign * 40.0
    pts = [
        (centre_x - rw, deep), (centre_x + rw, deep),
        (centre_x + rw, crest_y), (centre_x + gw, face_y),
        (centre_x - gw, face_y), (centre_x - rw, crest_y),
    ]
    prism = _extrude_polygon(Polygon(pts), z_hi - z_lo + 2.0)
    prism.apply_translation((0.0, 0.0, z_lo - 1.0))
    return prism


def _relief_cutter(
    *, centre_x: float, half_top: float, half_bottom: float, z_top: float,
    z_ramp_top: float, z_ramp_bottom: float, z_bottom: float, crest_y: float,
    face_y: float, outward_sign: float,
) -> trimesh.Trimesh:
    """The running slot a moving member nests in, cut through a root.

    A hardware root is two tapered buttresses under its two ears, never a slab
    across the full wall contact: the latch strap and the folded handle bail
    both swing in the space between the ears, and a root that bridged them
    would foul the very part it is supposed to carry.

    The slot follows the moving member's own taper rather than stepping: the
    bail's arms widen from the eye band to the full grip band as they descend,
    so the buttresses flare apart over exactly that run and never leave either
    an unsupported ledge or a shoulder for an arm to catch on.
    """
    pts = [
        (-half_bottom, z_bottom), (half_bottom, z_bottom),
        (half_bottom, z_ramp_bottom),
        (half_top, z_ramp_top),
        (half_top, z_top),
        (-half_top, z_top),
        (-half_top, z_ramp_top),
        (-half_bottom, z_ramp_bottom),
    ]
    depth = abs(face_y - crest_y) + 6.0
    cutter = _extrude_xz_profile(Polygon(pts), depth)
    # the helper centres its extrusion on Y=0, so slide the slot so it starts at
    # the wall crest and runs outward past the root's face
    cutter.apply_translation(
        (centre_x, crest_y + outward_sign * depth / 2.0, 0.0)
    )
    return cutter


def _pivot_section(
    profile: HardwareProfile, radius: float, axis_y: float, axis_z: float
) -> Polygon:
    return translate_polygon(support_free_profile_yz(radius), axis_y, axis_z)


def _ear_solid(
    *, section: Polygon, thickness: float, x_centre: float,
    bore_r: float, axis_y: float, axis_z: float,
) -> trimesh.Trimesh:
    """One printed ear with a uniform outer barrel and a round screw bore."""
    ear = _extrude_yz_profile(section, thickness)
    ear.apply_translation((x_centre, 0.0, 0.0))
    bore = _round_bore(bore_r, thickness + 3.0)
    bore.apply_translation((x_centre, axis_y, axis_z))
    return difference([ear, bore])


def _gusset(
    *, root_y: float, root_z: float, top_z: float, axis_y: float, axis_z: float,
    radius: float,
) -> Polygon:
    """Y/Z web carrying a pivot barrel down onto its root.

    The underside is one plane no shallower than 45 degrees and it starts
    inside the root rather than on the wall skin, so the body still prints
    upright with nothing hanging in air.
    """
    return Polygon([
        (root_y, root_z),
        (root_y, top_z),
        (axis_y, axis_z + 0.5 * radius),
        (axis_y, axis_z - 0.5 * radius),
    ])


def _hinge_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """One compact rear hinge per centre: two body ears on a tapered root."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    profile = plan.profile
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        near_x, _mid_x, far_x = _stack_positions(cx, profile)
        half = plan.hinge_root_width / 2.0 + 1.0
        cavity = _cavity_prism(box, cx - half, cx + half)
        root_prof = _root_profile_yz(
            box,
            outward_sign=1.0,
            face_y=plan.hinge_root_face_y,
            top_z=plan.hinge_root_top_z,
            height=profile.hinge_root_height,
        )
        root = _extrude_yz_profile(root_prof, plan.hinge_root_width)
        root.apply_translation((cx, 0.0, 0.0))
        keeper = _root_taper_prism(
            centre_x=cx,
            root_width=plan.hinge_root_width,
            group_width=profile.group_width,
            outward_sign=1.0,
            crest_y=plan.hinge_rear_crest,
            face_y=plan.hinge_root_face_y,
            z_lo=0.0,
            z_hi=plan.hinge_root_top_z,
        )
        solid = _intersection([root, keeper])
        bottom_z = max(0.6, plan.hinge_root_top_z - profile.hinge_root_height)
        for ex, thickness, terminal in (
            (near_x, profile.near_ear, False),
            (far_x, profile.far_lug, True),
        ):
            section = _filleted(
                _gusset(
                    root_y=_ear_wall_anchor_y(
                        layout, ex, thickness, 1.0, eff.wall_depth
                    ),
                    root_z=min(plan.hinge_root_top_z - 1.0, bottom_z + 1.0),
                    top_z=plan.hinge_root_top_z,
                    axis_y=plan.hinge_axis_y,
                    axis_z=plan.hinge_axis_z,
                    radius=profile.pivot_radius,
                )
                .union(
                    _pivot_section(
                        profile, profile.pivot_radius,
                        plan.hinge_axis_y, plan.hinge_axis_z,
                    )
                )
                .union(root_prof),
                plan.fillet_radius,
            )
            solid = union([
                solid,
                _ear_solid(
                    section=section,
                    thickness=thickness,
                    x_centre=ex,
                    bore_r=profile.bore_radius(terminal),
                    axis_y=plan.hinge_axis_y,
                    axis_z=plan.hinge_axis_z,
                ),
            ])
        parts.append(difference([solid, cavity]))
    return parts


def _hinge_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """The centre ear per hinge: one compact knuckle close to the rear lid edge,
    carried into the plate on a shallow arm rather than an oversized tab."""
    eff = b4b_effective_box(box)
    underside_z = b4b_lid_underside_z(box)
    skin = b4b_lid_skin_from_eff(eff)
    layout = b4b_layout(box)
    profile = plan.profile
    r = profile.pivot_radius
    z_hi = underside_z + skin
    parts: list[trimesh.Trimesh] = []
    for cx in plan.hinge_centers_x:
        _near_x, mid_x, _far_x = _stack_positions(cx, profile)
        root_y = layout.rear_wall_y(mid_x) - 0.4
        tab = Polygon([
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
        section = _filleted(
            tab.union(
                _pivot_section(profile, r, plan.hinge_axis_y, plan.hinge_axis_z)
            ).union(arm),
            plan.fillet_radius,
        )
        parts.append(
            _ear_solid(
                section=section,
                thickness=profile.mid_member,
                x_centre=mid_x,
                bore_r=profile.clear_bore / 2.0,
                axis_y=plan.hinge_axis_y,
                axis_z=plan.hinge_axis_z,
            )
        )
    return parts


# --------------------------------------------------------------------------- #
# front latch: a thin folding strap pivoted on the lid, hooking a metal catch
# screw carried in compact body ears.  The screw shank is the wear surface.
# --------------------------------------------------------------------------- #
def _latch_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """One compact catch receiver per latch: two ears on a tapered root, with
    the lever's running slot relieved between them."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    profile = plan.profile
    parts: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        near_x, _mid_x, far_x = _stack_positions(cx, profile)
        half = plan.latch_root_width / 2.0 + 1.0
        cavity = _cavity_prism(box, cx - half, cx + half)
        root_prof = _root_profile_yz(
            box,
            outward_sign=-1.0,
            face_y=plan.latch_root_face_y,
            top_z=plan.latch_root_top_z,
            height=profile.latch_root_height,
        )
        root = _extrude_yz_profile(root_prof, plan.latch_root_width)
        root.apply_translation((cx, 0.0, 0.0))
        keeper = _root_taper_prism(
            centre_x=cx,
            root_width=plan.latch_root_width,
            group_width=profile.group_width,
            outward_sign=-1.0,
            crest_y=plan.latch_front_crest,
            face_y=plan.latch_root_face_y,
            z_lo=0.0,
            z_hi=plan.latch_root_top_z,
        )
        solid = _intersection([root, keeper])
        bottom_z = max(0.6, plan.latch_root_top_z - profile.latch_root_height)
        for ex, thickness, terminal in (
            (near_x, profile.near_ear, False),
            (far_x, profile.far_lug, True),
        ):
            section = _filleted(
                _gusset(
                    root_y=_ear_wall_anchor_y(
                        layout, ex, thickness, -1.0, eff.wall_depth
                    ),
                    root_z=min(plan.latch_root_top_z - 1.0, bottom_z + 1.0),
                    top_z=plan.latch_root_top_z,
                    axis_y=plan.catch_axis_y,
                    axis_z=plan.catch_axis_z,
                    radius=profile.catch_radius,
                )
                .union(
                    _pivot_section(
                        profile, profile.catch_radius,
                        plan.catch_axis_y, plan.catch_axis_z,
                    )
                )
                .union(root_prof),
                plan.fillet_radius,
            )
            solid = union([
                solid,
                _ear_solid(
                    section=section,
                    thickness=thickness,
                    x_centre=ex,
                    bore_r=profile.bore_radius(terminal),
                    axis_y=plan.catch_axis_y,
                    axis_z=plan.catch_axis_z,
                ),
            ])
        relief_half = (
            profile.mid_member / 2.0 + B4B_RUNNING_GAP + B4B_HW_RELIEF_CLEARANCE
        )
        relief = _relief_cutter(
            centre_x=cx,
            half_top=relief_half,
            half_bottom=relief_half,
            z_top=plan.latch_root_top_z + 1.0,
            z_ramp_top=bottom_z,
            z_ramp_bottom=bottom_z,
            z_bottom=bottom_z - 1.0,
            crest_y=plan.latch_front_crest,
            face_y=plan.latch_root_face_y,
            outward_sign=-1.0,
        )
        parts.append(difference([solid, cavity, relief]))
    return parts


def _latch_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Two compact pivot ears per latch at the front lid edge, with the lever
    between them, rooted into the plate on a shallow tapered arm."""
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    profile = plan.profile
    skin = b4b_lid_skin_from_eff(eff)
    underside_z = b4b_lid_underside_z_from_eff(eff)
    top = underside_z + skin
    r = profile.pivot_radius
    parts: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        near_x, _mid_x, far_x = _stack_positions(cx, profile)
        for ex, thickness, terminal in (
            (near_x, profile.near_ear, False),
            (far_x, profile.far_lug, True),
        ):
            root_y = layout.front_wall_y(ex) + 0.4
            arm_profile = Polygon([
                (root_y, underside_z - B4B_LID_FITTING_DROP),
                (root_y, top),
                (plan.pivot_axis_y, top),
                (plan.pivot_axis_y - r, plan.pivot_axis_z),
                (plan.pivot_axis_y, plan.pivot_axis_z - r),
            ])
            arm = _lid_root_profile(
                layout,
                outward_sign=-1.0,
                fitting_inner_y=root_y,
                underside_z=underside_z,
                skin=skin,
            )
            section = _filleted(
                arm_profile.union(
                    _pivot_section(profile, r, plan.pivot_axis_y, plan.pivot_axis_z)
                ).union(arm),
                plan.fillet_radius,
            )
            parts.append(
                _ear_solid(
                    section=section,
                    thickness=thickness,
                    x_centre=ex,
                    bore_r=profile.bore_radius(terminal),
                    axis_y=plan.pivot_axis_y,
                    axis_z=plan.pivot_axis_z,
                )
            )
    return parts


def b4b_latch_lever_profile(plan: B4BHardwarePlan) -> Polygon:
    """Y/Z outline of one folding latch strap, in the closed pose.

    A thin strap, not the old convex hull of two large discs: a compact rounded
    pivot end, a flat body, an integrated hook around the catch screw and a
    modest finger lip at the lower edge.  The mouth is sized so the pin snaps
    through a real interference and the jaws root in filleted corners rather
    than square ones.
    """
    from shapely.geometry import LineString

    profile = plan.profile
    pivot = (plan.pivot_axis_y, plan.pivot_axis_z)
    catch = (plan.catch_axis_y, plan.catch_axis_z)
    hook_r = profile.hook_outer_radius
    inner_r = profile.catch_inner_radius

    strap = LineString([pivot, catch]).buffer(
        profile.strap_thickness / 2.0, cap_style=2, join_style=1, quad_segs=16
    )
    body = (
        Point(*pivot).buffer(profile.pivot_radius, quad_segs=32)
        .union(strap)
        .union(Point(*catch).buffer(hook_r, quad_segs=32))
    )

    # finger lip: a short flange below the hook, standing proud of the strap so
    # a fingertip can find it, but kept inside the hook's own radius so it never
    # sets the closed projection
    lip_out_y = plan.catch_axis_y - (profile.strap_thickness / 2.0 + profile.lip_out)
    lip_in_y = plan.catch_axis_y + profile.strap_thickness / 2.0
    lip_top = plan.catch_axis_z - hook_r * 0.5
    lip_bottom = plan.catch_axis_z - hook_r - profile.lip_length
    lo_y, hi_y = sorted((lip_out_y, lip_in_y))
    body = body.union(
        Polygon([
            (lo_y, lip_bottom), (hi_y, lip_bottom),
            (hi_y, lip_top), (lo_y, lip_top),
        ])
    )

    # the mouth opens toward the case, so closing rotation guides the hook onto
    # the pin and ordinary lid load pulls the upper jaw down onto it
    mouth = profile.hook_mouth / 2.0
    lead = mouth + profile.hook_lead_in
    reach = hook_r * 2.5
    opening = Polygon([
        (plan.catch_axis_y, plan.catch_axis_z - mouth),
        (plan.catch_axis_y + reach, plan.catch_axis_z - lead),
        (plan.catch_axis_y + reach, plan.catch_axis_z + lead),
        (plan.catch_axis_y, plan.catch_axis_z + mouth),
    ])
    body = body.difference(
        Point(*catch).buffer(inner_r, quad_segs=32).union(opening)
    )
    if not isinstance(body, Polygon) or not body.is_valid:
        raise RuntimeError("the B4B latch strap outline did not resolve")
    # the jaws root at the mouth in two square internal corners, and that is
    # exactly where a hook snapped over a pin cracks
    body = _filleted(body, min(profile.lever_fillet, 0.4 * mouth))
    return body.difference(
        Point(*pivot).buffer(profile.clear_bore / 2.0, quad_segs=32)
    )


def make_b4b_latches(box: BoxSpec) -> list[trimesh.Trimesh]:
    """The folding straps, one per resolved latch, in assembly space (closed).
    Each is exported as its own printable object, flat on a broad face."""
    plan = b4b_hardware_plan(box)
    if not plan.latch_count_resolved:
        return []
    outline = b4b_latch_lever_profile(plan)
    levers: list[trimesh.Trimesh] = []
    for cx in plan.latch_centers_x:
        # The strap is the stack's middle member, so it sits where the stack
        # puts it - not on the group centre.  Centring it on the group left it
        # touching the far lug on one side and 0.6 mm clear on the other.
        _near_x, mid_x, _far_x = _stack_positions(cx, plan.profile)
        lever = _extrude_yz_profile(outline, plan.profile.mid_member)
        lever.apply_translation((mid_x, 0.0, 0.0))
        levers.append(lever)
    return levers


# --------------------------------------------------------------------------- #
# folding front handle
# --------------------------------------------------------------------------- #
def _softened_slab(
    outline: Polygon, thickness: float, chamfer: float, up: float
) -> trimesh.Trimesh:
    """The bail's section, with its exposed perimeter edge broken back.

    A carried part should not present a square extruded edge to the hand.  The
    softening is applied to one face only so the other stays a broad flat
    printing surface, and it is built as short 45-degree treads rather than a
    single draft so every face remains either vertical or flat - nothing here
    may introduce a down-facing overhang.
    """
    steps = max(1, B4B_HANDLE_EDGE_STEPS)
    lo, hi = -thickness / 2.0, thickness / 2.0
    layers = [_extrude_polygon(outline, thickness - chamfer)]
    layers[0].apply_translation((0.0, 0.0, lo if up > 0 else lo + chamfer))
    for i in range(1, steps + 1):
        inset = chamfer * i / steps
        ring = outline.buffer(-inset, join_style=1, quad_segs=12)
        if ring.is_empty or not isinstance(ring, Polygon):
            break
        tread = chamfer / steps
        base = (hi - chamfer + (i - 1) * tread) if up > 0 else (lo + chamfer - i * tread)
        layer = _extrude_polygon(ring, tread + 1e-3)
        layer.apply_translation((0.0, 0.0, base))
        layers.append(layer)
    solid = union(layers) if len(layers) > 1 else layers[0]
    # the stack was built in X/Y/Z; roll it so the outline lands on X/Z and the
    # thickness runs across Y, the way the bail sits on the case
    solid.apply_transform(np.asarray([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]))
    return solid


def _handle_centreline(plan: B4BHandlePlan):
    """The U's centreline path, arms plus a real radiused lower corner."""
    from shapely.geometry import LineString

    half = plan.pivot_span / 2.0
    grip_z = plan.grip_z
    r = plan.corner_radius
    pts = [(-half, plan.axis_z), (-half, grip_z + r)]
    steps = 12
    for i in range(steps + 1):
        a = math.pi + (math.pi / 2.0) * (i / steps)
        pts.append((-half + r + r * math.cos(a), grip_z + r + r * math.sin(a)))
    pts.append((half - r, grip_z))
    for i in range(steps + 1):
        a = -math.pi / 2.0 + (math.pi / 2.0) * (i / steps)
        pts.append((half - r + r * math.cos(a), grip_z + r + r * math.sin(a)))
    pts.append((half, plan.axis_z))
    return LineString(pts)


def b4b_handle_outline(plan: B4BHandlePlan) -> Polygon:
    """X/Z outline of the bail: straight arms, broad lower radii, straight grip.

    Cross-section is constant through grip and arms and thickens only locally
    at the pivot eyes, which is what keeps a printed bail looking like one
    clean piece instead of two bosses joined by a strip.
    """
    band = plan.band / 2.0
    outline = _handle_centreline(plan).buffer(
        band, cap_style=2, join_style=1, quad_segs=24
    )
    if not isinstance(outline, Polygon) or not outline.is_valid:
        raise RuntimeError("the B4B handle outline did not resolve")
    # Taper the band down to the eye width over the top run, so a compact M3
    # pivot stack fits without thinning the part a hand actually holds.  The
    # taper is symmetric about each arm's own centreline - narrowing only the
    # outer edges would leave the inner face full width and drive the arm
    # straight into the fork's thread-forming lug.
    half = plan.pivot_span / 2.0
    eye = plan.eye_band / 2.0
    z_hi = plan.axis_z + plan.eye_radius + 2.0
    z_lo = plan.axis_z - B4B_HANDLE_TAPER_RUN
    keeper = Polygon([
        (-half - band, -1e4), (half + band, -1e4),
        (half + band, z_lo), (-half - band, z_lo),
    ])
    for cx in plan.centers_x:
        keeper = keeper.union(Polygon([
            (cx - band, z_lo), (cx + band, z_lo),
            (cx + eye, plan.axis_z), (cx + eye, z_hi),
            (cx - eye, z_hi), (cx - eye, plan.axis_z),
        ]))
    trimmed = outline.intersection(keeper)
    if isinstance(trimmed, Polygon) and trimmed.is_valid and not trimmed.is_empty:
        outline = trimmed
    return outline


def make_b4b_handle(box: BoxSpec) -> trimesh.Trimesh | None:
    """The folding bail, in assembly space, shown stowed against the front wall.

    One flat-printed U.  The outline is extruded through the handle thickness,
    the two pivot eyes are capped with the same support-free section every other
    B4B barrel uses, and the carry-stop heels stand proud of them.
    """
    plan = b4b_handle_plan(box)
    if plan is None:
        return None
    outline = b4b_handle_outline(plan)
    # The bail prints with its wall-facing side on the bed, so the exposed side
    # is the one that gets the edge softening.
    slab = _softened_slab(
        outline, plan.thickness, B4B_HANDLE_EDGE_CHAMFER, up=-1.0
    )
    slab.apply_translation((0.0, plan.axis_y, 0.0))

    # above the axis the part is the pivot eye, so keep only what lies inside
    # the support-free barrel section; below it the arms run straight down
    barrel = _extrude_yz_profile(
        support_free_profile_yz(plan.eye_radius), plan.pivot_span + 4.0 * plan.band
    )
    barrel.apply_translation((0.0, plan.axis_y, plan.axis_z))
    lower = trimesh.creation.box(
        extents=(
            plan.pivot_span + 6.0 * plan.band,
            plan.thickness + 4.0,
            2.0 * plan.axis_z,
        )
    )
    lower.apply_translation((0.0, plan.axis_y, 0.0))
    handle = _intersection([slab, union([barrel, lower])])

    stops: list[trimesh.Trimesh] = []
    bores: list[trimesh.Trimesh] = []
    pockets: list[trimesh.Trimesh] = []
    heel_r = plan.eye_radius + plan.wall_clear
    for cx in plan.centers_x:
        stops.append(_handle_stop_heel(plan, cx, heel_r))
        bore = _round_bore(plan.profile.clear_bore / 2.0, plan.eye_band + 4.0)
        bore.apply_translation((cx, plan.axis_y, plan.axis_z))
        bores.append(bore)
    for cx in plan.detent_centers_x:
        depth = max(0.05, plan.detent_bump - plan.detent_interference)
        pocket = trimesh.creation.box(
            extents=(plan.band * 0.7, 2.0 * depth, 3.0)
        )
        pocket.apply_translation(
            (cx, plan.axis_y + plan.eye_radius, plan.detent_z)
        )
        pockets.append(pocket)
    handle = union([handle, *stops])
    return _weld(difference([handle, *bores, *pockets]))


def _handle_stop_heel(
    plan: B4BHandlePlan, cx: float, heel_r: float
) -> trimesh.Trimesh:
    """A broad printed heel at one pivot, sized to land flat on its body stop.

    The stop has to load real plastic faces: never the screw head, never the
    thread, and never a knife edge.  The heel stands just proud of the eye and
    is carried right across the eye's axial width, so the contact patch is the
    whole face rather than a corner.
    """
    tang = B4B_HANDLE_STOP_FACE / 2.0
    ang = math.radians(plan.stop_angle)
    # at stow the heel points nearly straight up; the deployed stop angle is
    # what brings its flat face round onto the body pad
    cy, cz = math.cos(ang), math.sin(ang)
    ny, nz = -math.sin(ang), math.cos(ang)
    base = plan.eye_radius - 0.6
    pts = [
        (plan.axis_y + base * cy + tang * ny, plan.axis_z + base * cz + tang * nz),
        (plan.axis_y + base * cy - tang * ny, plan.axis_z + base * cz - tang * nz),
        (plan.axis_y + heel_r * cy - tang * ny, plan.axis_z + heel_r * cz - tang * nz),
        (plan.axis_y + heel_r * cy + tang * ny, plan.axis_z + heel_r * cz + tang * nz),
    ]
    heel = _extrude_yz_profile(Polygon(pts), plan.eye_band)
    heel.apply_translation((cx, 0.0, 0.0))
    return heel


def _handle_body_parts(box: BoxSpec) -> list[trimesh.Trimesh]:
    """The two body pivot forks, their roots, the carry stops and the stow
    detents - all on the front wall, none of it on the lid."""
    plan = b4b_handle_plan(box)
    if plan is None:
        return []
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    profile = plan.profile
    parts: list[trimesh.Trimesh] = []
    for cx in plan.centers_x:
        near_x, far_x = _handle_fork_positions(cx)
        half = plan.root_width / 2.0 + 1.0
        cavity = _cavity_prism(box, cx - half, cx + half)
        height = plan.root_top_z - plan.root_bottom_z
        root_prof = _root_profile_yz(
            box,
            outward_sign=-1.0,
            face_y=plan.root_face_y,
            top_z=plan.root_top_z,
            height=height,
        )
        root = _extrude_yz_profile(root_prof, plan.root_width)
        root.apply_translation((cx, 0.0, 0.0))
        keeper = _root_taper_prism(
            centre_x=cx,
            root_width=plan.root_width,
            group_width=profile.group_width,
            outward_sign=-1.0,
            crest_y=plan.front_crest,
            face_y=plan.root_face_y,
            z_lo=0.0,
            z_hi=plan.root_top_z,
        )
        solid = _intersection([root, keeper])
        for ex, thickness, terminal in (
            (near_x, B4B_HANDLE_NEAR_EAR, False),
            (far_x, B4B_HANDLE_FAR_LUG, True),
        ):
            section = _filleted(
                _gusset(
                    root_y=_ear_wall_anchor_y(
                        layout, ex, thickness, -1.0, eff.wall_depth
                    ),
                    root_z=plan.root_bottom_z + 1.0,
                    top_z=plan.root_top_z,
                    axis_y=plan.axis_y,
                    axis_z=plan.axis_z,
                    radius=profile.pivot_radius,
                )
                .union(
                    _pivot_section(
                        profile, profile.pivot_radius, plan.axis_y, plan.axis_z
                    )
                )
                .union(root_prof),
                B4B_HW_FILLET,
            )
            solid = union([
                solid,
                _ear_solid(
                    section=section,
                    thickness=thickness,
                    x_centre=ex,
                    bore_r=profile.bore_radius(terminal),
                    axis_y=plan.axis_y,
                    axis_z=plan.axis_z,
                ),
            ])
        # the bail nests between the ears, so the root is two buttresses with a
        # running slot between them, never a slab across the whole wall contact
        relief = _relief_cutter(
            centre_x=cx,
            half_top=plan.eye_band / 2.0 + B4B_RUNNING_GAP,
            half_bottom=plan.band / 2.0 + B4B_HW_RELIEF_CLEARANCE,
            z_top=plan.root_top_z + 2.0,
            z_ramp_top=plan.axis_z,
            z_ramp_bottom=plan.axis_z - B4B_HANDLE_TAPER_RUN,
            z_bottom=plan.root_bottom_z - 2.0,
            crest_y=plan.front_crest,
            face_y=plan.root_face_y,
            outward_sign=-1.0,
        )
        solid = difference([solid, cavity, relief])
        # The flat the deployed heel lands on.  At the stop angle the heel
        # has swung round to point straight at the wall, so the pad sits level
        # with the pivot axis - and it only fills the wave's troughs back to
        # the local crest, so it costs no projection at all.
        pad = trimesh.creation.box(
            extents=(plan.eye_band, 1.2, B4B_HANDLE_STOP_FACE)
        )
        pad.apply_translation((cx, plan.front_crest + 0.6, plan.axis_z))
        parts.append(union([solid, pad]))
    for cx in plan.detent_centers_x:
        # Radius comes from the ramp requirement, not from taste: the bump has
        # to rise its full height over at least this much run so the arm rides
        # on a slope shallower than 45 degrees instead of hitting a step.
        stand = plan.wall_clear + plan.detent_bump
        radius = max(2.0 * B4B_HANDLE_DETENT_RAMP, stand + B4B_HANDLE_DETENT_RAMP)
        bump = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        bump.apply_scale((1.0, stand / radius, 1.0))
        bump.apply_translation((cx, plan.front_crest, plan.detent_z))
        parts.append(bump)
    return parts


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def _lid_rear_relief_cutter(
    box: BoxSpec, plan: B4BHardwarePlan
) -> trimesh.Trimesh:
    """The 45-degree relief taken off the rear lid edge when the sweep needs it.

    Relief is always the first answer to an opening collision: shaving a
    fraction of a millimetre off an edge nobody sees is better than pushing the
    whole hinge further behind the case, which is what makes a slim box look
    like it is wearing a backpack.
    """
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    underside_z = b4b_lid_underside_z_from_eff(eff)
    r = min(plan.lid_rear_relief, b4b_lid_skin_from_eff(eff) - 0.4)
    crest = layout.outer_half_y + WAVE_AMPLITUDE + 2.0
    profile = Polygon([
        (crest - r, underside_z - 0.01),
        (crest + 4.0, underside_z - 0.01),
        (crest + 4.0, underside_z + r),
        (crest, underside_z + r),
    ])
    case_x, _case_y = layout.case_size
    return _extrude_yz_profile(profile, case_x + 40.0)


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


# Boolean/intersection numerical noise only.  Physical clearance is positive by
# construction everywhere; this allowance exists because mesh booleans on a
# wavy case leave slivers, never to give a real clash somewhere to hide.
B4B_NOISE_CC = 0.05
# The only interference a stowed bail may show is its two stow detents.  This
# is an *absolute* ceiling on that, checked alongside the swept comparison:
# a baseline comparison on its own cannot see a rotation-invariant clash,
# because an eye buried in its own fork overlaps by the same amount at every
# angle and therefore never looks like motion adding interference.
B4B_HANDLE_STOWED_CEIL_CC = 0.02


def _validate_b4b_mechanics(box: BoxSpec) -> None:
    """Sampled moving-part and thread-retention checks - run at generation time,
    not on every keystroke.  Deterministic (fixed sample angles); not a full
    rigid-body simulator."""
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    plan = b4b_hardware_plan(box)
    profile = plan.profile

    # 1. every screw path: real thread engagement and no exposed tail.
    # Physical engagement is min(screw beyond the clearance stack, lug
    # thickness) - a screw longer than the lug threads only as far as the lug.
    paths: list[tuple[str, float, float, int]] = []
    if b4b.secure_lid:
        paths += [
            ("hinge", profile.clear_span, profile.far_lug,
             plan.hinge_screw_length_mm),
            ("latch pivot", profile.clear_span, profile.far_lug,
             plan.latch_screw_length_mm),
            ("catch", profile.clear_span, profile.far_lug,
             plan.catch_screw_length_mm),
        ]
    handle = b4b_handle_plan(box)
    if handle is not None:
        paths.append((
            "handle pivot",
            B4B_HANDLE_FORK_CLEAR_SPAN,
            B4B_HANDLE_FAR_LUG,
            handle.screw_length_mm,
        ))
    for what, span, lug, screw in paths:
        fam = handle.profile if what == "handle pivot" else profile
        beyond = screw - span
        engage = min(beyond, lug)
        if engage < fam.engage_min - _EPS:
            raise ValueError(
                f"the {what} screw threads only {engage:.2f} mm into its "
                f"{lug:.2f} mm lug (need {fam.engage_min:.1f} mm)"
            )
        tail = beyond - lug
        if tail > B4B_SCREW_MAX_TAIL + _EPS:
            raise ValueError(
                f"the {what} screw leaves a {tail:.2f} mm tail past its lug "
                f"(limit {B4B_SCREW_MAX_TAIL:.1f} mm)"
            )

    # 2. actual generated solids are watertight single volumes.
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

    # 3. the handle: one solid, stowed clear of the wall, and swept to its stop.
    if handle is not None:
        bail = make_b4b_handle(box)
        if bail is None or not bail.is_watertight or bail.volume <= 0.0:
            raise ValueError("the B4B handle did not generate as a watertight solid")
        # Deploying swings the bail's grip away from the wall, which about
        # world +X is the negative rotation - the same handedness the lid and
        # the latch straps open on.
        angles = tuple(
            -a for a in _sweep_angles(90.0) + (handle.stop_angle,) if a > 0.0
        )
        worst = _sweep_intersection_cc(
            bail, body, handle.axis_y, handle.axis_z, angles_deg=angles
        )
        stowed = _sweep_intersection_cc(
            bail, body, handle.axis_y, handle.axis_z, angles_deg=(0.0,)
        )
        if stowed > B4B_HANDLE_STOWED_CEIL_CC:
            raise ValueError(
                f"the stowed handle interferes with the case by "
                f"{stowed:.3f} cc (allowance "
                f"{B4B_HANDLE_STOWED_CEIL_CC:.2f} cc for the stow detents "
                f"alone); the bail must fold onto clearance, not into its forks"
            )
        if worst > stowed + B4B_NOISE_CC:
            raise ValueError(
                f"the carrying handle strikes the case while folding out "
                f"(overlap {worst:.3f} cc vs {stowed:.3f} cc stowed); the "
                f"pivot forks or the carry stop need design review"
            )
        if lid is not None:
            lid_hit = _sweep_intersection_cc(
                bail, lid, handle.axis_y, handle.axis_z, angles_deg=angles
            )
            if lid_hit > B4B_NOISE_CC:
                raise ValueError(
                    f"the carrying handle fouls the lid ({lid_hit:.3f} cc); the "
                    f"handle must clear the lid seam through its whole sweep"
                )

    if not b4b.secure_lid:
        return

    # 4. latch rotation about its pivot.  Opening swings the strap's lower end
    # away from the case and up, which about world +X is the negative rotation.
    # What must hold is (a) the closed pose touches only at the intended
    # detent, (b) the hook is off the pin by the release angle, and (c) nothing
    # rubs after that.
    for lever in make_b4b_latches(box):
        closed = _sweep_intersection_cc(
            lever, body, plan.pivot_axis_y, plan.pivot_axis_z, angles_deg=(0.0,)
        )
        if closed > B4B_NOISE_CC:
            raise ValueError(
                f"a latch strap touches the body's catch receiver when closed "
                f"(overlap {closed:.3f} cc, allowance {B4B_NOISE_CC:.2f} cc); "
                f"it must swing on clearance, not rub"
            )
        released = tuple(
            -a for a in _sweep_angles(B4B_LATCH_OPEN_ANGLE)
            if a + _EPS >= B4B_LATCH_RELEASE_ANGLE
        )
        worst = _sweep_intersection_cc(
            lever, body, plan.pivot_axis_y, plan.pivot_axis_z,
            angles_deg=released,
        )
        if worst > closed + B4B_NOISE_CC:
            raise ValueError(
                f"a latch strap does not swing clear of the body once released "
                f"(overlap {worst:.3f} cc vs {closed:.3f} cc closed); reduce "
                f"the hook depth or use a larger B4B"
            )

    # 5. the hook is geometrically off the pin by the release angle.
    _validate_latch_release(plan)

    # 6. lid opening sweep about the hinge axis, every 5 degrees to 120.
    if lid is not None:
        closed = _sweep_intersection_cc(
            lid, body, plan.hinge_axis_y, plan.hinge_axis_z, angles_deg=(0.0,)
        )
        if closed > B4B_NOISE_CC:
            raise ValueError(
                f"the closed lid binds against the body "
                f"(overlap {closed:.3f} cc, allowance {B4B_NOISE_CC:.2f} cc); "
                f"it must seat on its rim, not jam on its hardware"
            )
        angles = tuple(-a for a in _sweep_angles(B4B_LID_OPEN_ANGLE) if a > 0.0)
        worst = _sweep_intersection_cc(
            lid, body, plan.hinge_axis_y, plan.hinge_axis_z, angles_deg=angles
        )
        if worst > closed + B4B_NOISE_CC:
            raise ValueError(
                f"the lid collides with the body while opening to "
                f"{B4B_LID_OPEN_ANGLE:g} degrees (overlap {worst:.3f} cc vs "
                f"{closed:.3f} cc closed); check the hinge placement"
            )


def _validate_latch_release(plan: B4BHardwarePlan) -> None:
    """The hook must actually be off the pin by the release angle.

    A rigid hook on a rigid pin is a two-circle problem, so this is solved
    exactly rather than sampled: at the release angle the hook bore's centre
    must have moved far enough that the pin is outside the captured bore.
    """
    profile = plan.profile
    dy = plan.catch_axis_y - plan.pivot_axis_y
    dz = plan.catch_axis_z - plan.pivot_axis_z
    ang = math.radians(-B4B_LATCH_RELEASE_ANGLE)
    moved_y = dy * math.cos(ang) - dz * math.sin(ang)
    moved_z = dy * math.sin(ang) + dz * math.cos(ang)
    travel = math.hypot(moved_y - dy, moved_z - dz)
    need = profile.catch_inner_radius + profile.nominal / 2.0
    if travel + _EPS < need:
        raise ValueError(
            f"the latch hook is still on its pin at "
            f"{B4B_LATCH_RELEASE_ANGLE:g} degrees open (travelled "
            f"{travel:.2f} mm, needs {need:.2f} mm); increase the latch draw"
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

    Nothing here grows the design.  A field, a height or a wall that cannot
    carry the hardware is reported as exactly that, so the UI can gate the
    option instead of silently handing back a different box than the one the
    user asked for.  ``deep=True`` additionally runs the sampled moving-part
    and thread checks; it builds meshes, so preview callers leave it off.
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

    min_x, min_y = b4b_min_field(box)
    if box.x + _EPS < min_x or box.y + _EPS < min_y:
        raise ValueError(
            f"a B4B child field is at least {min_x:g} x {min_y:g} mm "
            f"({round(min_x / GRID_PITCH)}U x {round(min_y / GRID_PITCH)}U); "
            f"{box.x:g} x {box.y:g} mm is too small to carry the hardware"
        )
    min_wall = b4b_required_min_wall(box)
    if box.wall + _EPS < min_wall:
        raise ValueError(
            f"a B4B wall is at least {min_wall:g} mm - this design is set "
            f"to {box.wall:g} mm; raise the wall before regenerating"
        )
    min_height = b4b_secure_min_height()
    if b4b.secure_lid and box.z + _EPS < min_height:
        raise ValueError(
            f"a latched B4B lid needs at least {min_height:g} mm of bin "
            f"height; this design is {box.z:g} mm - use Lid Only or a taller "
            f"B4B"
        )

    cx, cy = b4b_capacity_units(box)
    if cx < 1 or cy < 1:
        raise ValueError("B4B interior is smaller than one child unit")

    layout = b4b_layout(box)
    wall = layout.outer_structural_polygon.difference(layout.inner_mating_polygon)
    if wall.is_empty or wall.area <= 0.0:
        raise ValueError("B4B outward structural wall is empty")

    if b4b.handle:
        eligible, reason = b4b_handle_eligibility(box)
        if not eligible:
            raise ValueError(
                f"this B4B cannot carry a handle: {reason.rstrip('.')}"
            )
        handle = b4b_handle_plan(box)
        if handle is None:
            raise ValueError("the handle did not resolve for this B4B")
        if handle.screw_length_mm not in handle.profile.lengths:
            raise ValueError(
                "the handle screw did not resolve to an allowed "
                f"{handle.profile.name} length"
            )
        if handle.clear_grip + _EPS < B4B_HANDLE_GRIP_MIN:
            raise ValueError(
                f"the handle gives only {handle.clear_grip:.1f} mm of clear "
                f"grip (need {B4B_HANDLE_GRIP_MIN:g} mm)"
            )
        if handle.drop + _EPS < B4B_HANDLE_DROP_MIN:
            raise ValueError(
                f"the handle drops only {handle.drop:.1f} mm below its pivots "
                f"(need {B4B_HANDLE_DROP_MIN:g} mm for fingers)"
            )
        if handle.projection > B4B_HANDLE_MAX_PROJECTION + _EPS:
            raise ValueError(
                f"the folded handle stands {handle.projection:.2f} mm off the "
                f"front wall (review ceiling {B4B_HANDLE_MAX_PROJECTION:g} mm)"
            )

    if b4b.secure_lid:
        eff = b4b_effective_box(box)
        plan = b4b_hardware_plan(box)
        profile = plan.profile
        if plan.hinge_count != B4B_HINGE_COUNT:
            raise ValueError("a secure B4B lid needs exactly two hinges")
        # --- printability and structure, not merely "it resolved to a number"
        if profile.head_bearing_margin + _EPS < profile.head_bearing_min:
            raise ValueError(
                f"a {profile.name} head has only {profile.head_bearing_margin:.2f} mm "
                f"of bearing on the uniform barrel (need "
                f"{profile.head_bearing_min:.2f} mm)"
            )
        if min(profile.pivot_radius, profile.catch_radius) + _EPS < profile.required_uniform_radius:
            raise ValueError(
                f"the {profile.name} uniform barrel is too small for its bore "
                "shell or screw-head bearing"
            )
        bridge = 2.0 * B4B_SUPPORT_FREE_FLAT * max(
            profile.pivot_radius, profile.catch_radius
        )
        if bridge > B4B_SUPPORT_FREE_BRIDGE_MAX + _EPS:
            raise ValueError(
                f"the largest support-free hardware barrel would bridge {bridge:.2f} mm "
                f"unsupported (limit {B4B_SUPPORT_FREE_BRIDGE_MAX:.1f} mm)"
            )
        for what, centres, width in (
            ("hinge", plan.hinge_centers_x, plan.hinge_root_width),
            ("latch", plan.latch_centers_x, plan.latch_root_width),
        ):
            reach = max(abs(c) for c in centres) + width / 2.0
            limit = layout.outer_half_x - CORNER_INSET - B4B_ROOT_CORNER_CLEARANCE
            if reach > limit + _EPS:
                raise ValueError(
                    f"a {what} root reaches {reach - limit:.2f} mm into the "
                    f"corner keep-out; this B4B is too narrow for its hardware"
                )
        if len(plan.hinge_centers_x) == 2:
            gap = (
                2.0 * min(abs(c) for c in plan.hinge_centers_x)
                - plan.hinge_root_width
            )
            if gap + _EPS < B4B_HINGE_CENTRE_GAP:
                raise ValueError(
                    f"the two hinge roots are only {gap:.2f} mm apart "
                    f"(need {B4B_HINGE_CENTRE_GAP:.1f} mm)"
                )
        for what, target in (
            ("hinge", profile.hinge_root_depth),
            ("latch", profile.latch_root_depth),
        ):
            if eff.wall_depth > target + _EPS:
                continue
            if _root_outward(target, eff.wall_depth) <= 0.0:
                raise ValueError(
                    f"the {what} root adds no reinforcement over a "
                    f"{eff.wall:g} mm wall; hardware strength must not follow "
                    f"the wall setting"
                )
        ceiling = B4B_HINGE_MAX_PROJECTION[profile.name]
        if plan.hinge_projection > ceiling + _EPS:
            raise ValueError(
                f"the rear hinge stands {plan.hinge_projection:.2f} mm off the "
                f"wall (review ceiling {ceiling:g} mm); it would read as "
                f"hardware bolted on rather than grown from the case"
            )
        ceiling = B4B_LATCH_MAX_PROJECTION[profile.name]
        if plan.latch_projection > ceiling + _EPS:
            raise ValueError(
                f"the closed latch stands {plan.latch_projection:.2f} mm off "
                f"the front wall (review ceiling {ceiling:g} mm)"
            )
        for what, length in (
            ("hinge", plan.hinge_screw_length_mm),
            ("latch pivot", plan.latch_screw_length_mm),
            ("catch", plan.catch_screw_length_mm),
        ):
            if length not in profile.lengths:
                raise ValueError(
                    f"the {what} screw did not resolve to an allowed "
                    f"{profile.name} length"
                )
        # The two front mechanisms must stay visually and physically distinct.
        # They live at different heights *and* different X, so a real clash
        # needs both envelopes to overlap - comparing one axis alone would
        # condemn every handled case, since the latch always sits above the
        # pivots and that is exactly the intended arrangement.
        if b4b.handle:
            handle = b4b_handle_plan(box)
            if handle is not None:
                latch_lo = plan.latch_root_top_z - profile.latch_root_height
                z_gap = max(
                    latch_lo - handle.root_top_z,
                    handle.root_bottom_z - plan.latch_root_top_z,
                )
                x_gap = min(
                    abs(lc - hc) - (plan.latch_root_width + handle.root_width) / 2.0
                    for lc in plan.latch_centers_x
                    for hc in handle.centers_x
                )
                if max(z_gap, x_gap) + _EPS < B4B_FRONT_ROOT_SEPARATION:
                    raise ValueError(
                        f"the latch and handle roots would merge into one "
                        f"bracket on the front wall (closest approach "
                        f"{max(z_gap, x_gap):.2f} mm, need "
                        f"{B4B_FRONT_ROOT_SEPARATION:g} mm of clear wall); "
                        f"this B4B is too wide for a centred bail and its "
                        f"latches at once"
                    )
        detent = profile.nominal - profile.hook_mouth
        if abs(detent - B4B_LATCH_DETENT) > 0.05 + _EPS:
            raise ValueError(
                f"the {profile.name} hook mouth gives {detent:.2f} mm of pin "
                f"interference, away from the {B4B_LATCH_DETENT:.2f} mm detent "
                f"the latch is tuned around (band 0.15-0.25 mm)"
            )
        _validate_latch_release(plan)

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
        hardware_radius = plan.profile.pivot_radius
        for centres, width in (
            (plan.hinge_centers_x, plan.hinge_root_width),
            (plan.latch_centers_x, plan.latch_root_width),
        ):
            min_x = min(min_x, min(c - width / 2.0 for c in centres))
            max_x = max(max_x, max(c + width / 2.0 for c in centres))
        min_y = min(min_y, plan.pivot_axis_y - hardware_radius)
        max_y = max(max_y, plan.hinge_axis_y + hardware_radius)
        top_z = max(top_z, plan.hinge_axis_z + plan.profile.pivot_radius)
    # The readout has to survive a design the geometry would refuse, because
    # reporting *why* the handle cannot be fitted is most of its job: raising
    # here would leave the UI with no summary at all and therefore nothing to
    # explain itself with.
    handle_ok, handle_why = b4b_handle_eligibility(box)
    handle = b4b_handle_plan(box) if (b4b.handle and handle_ok) else None
    if handle is not None:
        # The bail folds against the front wall, so it costs depth, not height:
        # a handled case still stacks.
        min_y = min(min_y, handle.axis_y - handle.eye_radius)
        min_x = min(min_x, handle.centers_x[0] - handle.root_width / 2.0)
        max_x = max(max_x, handle.centers_x[1] + handle.root_width / 2.0)
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
        "base_thickened": b4b_grew(box),
        "capacity_units": [cx, cy],
        "capacity_mm": [round(mx, 2), round(my, 2)],
        "max_child_height_mm": round(b4b_max_child_height(box), 2),
        "effective_base_thickness_mm": round(eff.base_thickness, 3),
        "lid": b4b.lid,
        "secure_lid": b4b.secure_lid,
        "lid_headroom_mm": b4b.lid_headroom_mm,
        "stacking": b4b.stacking,
        "handle": handle is not None,
        "handle_requested": b4b.handle,
        "label_location": b4b.label_location if b4b.label_text.strip() else "none",
        "label_text": b4b.label_text,
        "capacity_text": (
            f"Inside capacity: {mx:g} x {my:g} mm - {cx} x {cy} units"
        ),
        "max_child_height_text": f"Maximum bin height: {b4b_max_child_height(box):g} mm",
    }
    if b4b.secure_lid:
        fam = plan.profile.name
        summary["latch_count"] = plan.latch_count_resolved
        summary["hardware_family"] = fam
        summary["hardware"] = {
            "family": fam,
            "hinge_screw": f"{fam}x{plan.hinge_screw_length_mm}",
            "hinge_qty": plan.hinge_count,
            "latch_screw": f"{fam}x{plan.latch_screw_length_mm}",
            "latch_qty": plan.latch_count_resolved,
            "catch_screw": f"{fam}x{plan.catch_screw_length_mm}",
            "catch_qty": plan.latch_count_resolved,
            "nuts": 0,
        }
        summary["hardware_bom"] = plan.screw_bom()
        # Authoritative regression metrics: a bulkier redesign shows up here
        # rather than only in somebody's eye.
        summary["metrics"] = {
            "hinge_projection_mm": round(plan.hinge_projection, 3),
            "hinge_group_width_mm": round(plan.hinge_width, 3),
            "hinge_root_width_mm": round(plan.hinge_root_width, 3),
            "latch_projection_mm": round(plan.latch_projection, 3),
            "latch_root_width_mm": round(plan.latch_root_width, 3),
            "lid_rear_relief_mm": round(plan.lid_rear_relief, 3),
            "head_bearing_margin_mm": round(plan.profile.head_bearing_margin, 3),
        }
    else:
        summary["latch_count"] = 0
        summary["hardware_family"] = plan.profile.name
        summary["hardware"] = {"nuts": 0}
        summary["hardware_bom"] = []
        summary["metrics"] = {}
    if handle is not None:
        fam = handle.profile.name
        summary["hardware"]["handle_screw"] = f"{fam}x{handle.screw_length_mm}"
        summary["hardware"]["handle_qty"] = 2
        summary["metrics"].update({
            "handle_pivot_span_mm": round(handle.pivot_span, 3),
            "handle_clear_grip_mm": round(handle.clear_grip, 3),
            "handle_drop_mm": round(handle.drop, 3),
            "handle_band_mm": round(handle.band, 3),
            "handle_thickness_mm": round(handle.thickness, 3),
            "handle_projection_mm": round(handle.projection, 3),
            "handle_root_width_mm": round(handle.root_width, 3),
            "handle_stop_angle_deg": handle.stop_angle,
        })
        bom = summary["hardware_bom"]
        line = f"2 x {fam}x{handle.screw_length_mm} handle pivots"
        # keep "No nuts" last, as the reassurance it is
        bom.insert(max(0, len(bom) - 1) if bom else 0, line)
        if not bom or bom[-1] != "No nuts":
            bom.append("No nuts")
    summary["handle_available"] = handle_ok
    summary["handle_blocked_reason"] = handle_why
    label_ok, label_why = b4b_front_label_eligibility(box)
    summary["front_label_available"] = label_ok
    summary["front_label_blocked_reason"] = label_why
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
    geometry.extend(_mesh_preview_geometry(body, "b4b_body", owner="base"))
    if eff.b4b.label_location == "front" and eff.b4b.label_text.strip():
        # Plugs into the body's front channel frame - a base part.
        geometry.extend(
            _mesh_preview_geometry(
                make_b4b_front_label_plate(box), "b4b_label", owner="base"
            )
        )
    if eff.b4b.lid:
        lid = make_b4b_lid(box)
        if eff.b4b.label_location == "top" and eff.b4b.label_text.strip():
            lid, inlay = _apply_top_label(box, lid)
            # Fused into the lid mesh itself - a lid part.
            geometry.extend(_mesh_preview_geometry(inlay, "b4b_label", owner="lid"))
        geometry.extend(_mesh_preview_geometry(lid, "b4b_lid", owner="lid"))
    handle = make_b4b_handle(box)
    if handle is not None:
        # Folds against the front wall - body-mounted hardware.
        geometry.extend(_mesh_preview_geometry(handle, "b4b_handle", owner="base"))
    if eff.b4b.secure_lid:
        for lever in make_b4b_latches(box):
            # Lid-mounted moving parts.
            geometry.extend(_mesh_preview_geometry(lever, "b4b_latch", owner="lid"))
    if eff.b4b.stacking:
        for peg in _stack_pegs(box):
            # Locating pegs stand proud of the lid's own top surface.
            geometry.extend(_mesh_preview_geometry(peg, "b4b_stack", owner="lid"))
    return tuple(geometry)


def b4b_preview_parts(box: BoxSpec) -> list[tuple[list, str, tuple, int, str]]:
    """Preview geometry in the ``preview_geometry`` tuple format:
    ``(points, kind, normal, layer, owner)``, where ``owner`` is ``"base"`` or
    ``"lid"``.  Dimensionally true; microdetail such as thread pilots is
    omitted."""
    return list(_b4b_preview_geometry(box))


def b4b_preview_meshes(box: BoxSpec) -> list[dict]:
    """Compact GPU-ready preview transport: one entry per (kind, owner,
    layer) group, carrying flat ``positions``/``normals`` arrays instead of
    one JSON object per triangle.

    A B4B case routinely runs past 100k triangles, where serialising and
    parsing ``b4b_preview_parts``'s one-dict-per-face format is itself most
    of the preview's load cost - repeating ``kind``/``normal``/``layer``/
    ``owner`` on every triangle instead of once per group. ``normals`` holds
    one normal per triangle (not per vertex): every B4B preview face is
    mesh-derived and already a flat-shaded triangle, so the three corners in
    ``positions`` at index ``9*i .. 9*i+9`` all share ``normals[3*i .. 3*i+3]``
    and the browser expands it per vertex when building its GPU buffer.
    """
    groups: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    for points, kind, normal, layer, owner in _b4b_preview_geometry(box):
        bucket = groups.setdefault((kind, owner, layer), {"positions": [], "normals": []})
        for corner in points:
            bucket["positions"].extend(corner)
        bucket["normals"].extend(normal)
    return [
        {
            "kind": kind, "owner": owner, "layer": layer,
            "positions": bucket["positions"], "normals": bucket["normals"],
        }
        for (kind, owner, layer), bucket in groups.items()
    ]


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
    boss (all four, not one row) plus a margin.

    Hinge knuckles and latch ears sit outboard at the rim, below the top plate,
    and the carrying handle now folds against the front wall rather than
    straddling the lid, so the bosses are the only real keep-outs left."""
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


def b4b_front_label_fit(box: BoxSpec) -> tuple[bool, float, float, float]:
    """``(fits, frame_w, top_z, bottom_z)`` for the slide-in front label
    channel, computed against the same real front-wall geometry
    ``b4b_front_label_geometry`` builds from, so the UI's eligibility check
    and the actual build can never disagree.
    """
    eff = b4b_effective_box(box)
    plan = b4b_hardware_plan(box)
    layout = b4b_layout(box)
    span = _front_span(box)

    frame_w = span - 4.0
    # vertical band: below the latch pads (or below the rim if passive)
    if plan.latch_count_resolved:
        receiver_r = plan.profile.catch_radius
        # clear of the catch ears and of the root's 45-degree underside taper
        top_z = min(
            plan.catch_axis_z - receiver_r - B4B_LABEL_KEEPOUT,
            plan.latch_root_top_z - plan.profile.latch_root_height
            - B4B_LABEL_KEEPOUT,
        )
    else:
        top_z = eff.z - 4.0
    handle = b4b_handle_plan(box)
    if handle is not None:
        # The folded U frames the label rather than covering it: the readable
        # area is the clear opening between the arms, under the pivot forks.
        frame_w = min(frame_w, handle.clear_grip - 2.0 * B4B_LABEL_KEEPOUT)
        top_z = min(
            top_z,
            handle.root_bottom_z - B4B_LABEL_KEEPOUT,
        )
    bottom_z = top_z - B4B_FRONT_LABEL_HEIGHT
    return frame_w >= 30.0 and bottom_z >= 3.0, frame_w, top_z, bottom_z


def b4b_front_label_eligibility(box: BoxSpec) -> tuple[bool, str]:
    """``(eligible, reason)`` - whether this case's front wall can carry a
    slide-in label, mirroring ``b4b_handle_eligibility``'s shape so the UI
    can gate both controls the same way."""
    fits, _frame_w, _top_z, _bottom_z = b4b_front_label_fit(box)
    if fits:
        return True, ""
    return False, "Not enough size for a front label."


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
    fits, frame_w, top_z, bottom_z = b4b_front_label_fit(box)
    height = B4B_FRONT_LABEL_HEIGHT
    if not fits:
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
        # Lay the bail on its broad face.  The U outline runs across local Y,
        # so that axis rolls onto the bed's Z, the lower radii become plain 2D
        # outline geometry and only the small round pivot bores stay horizontal.
        # The roll is negative so the
        # wall-facing side lands on the bed and the softened exposed edge
        # finishes upward.
        m.apply_transform(
            trimesh.transformations.rotation_matrix(-math.pi / 2.0, (1.0, 0.0, 0.0))
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
