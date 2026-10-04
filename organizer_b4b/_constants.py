"""Storage Box (B4B) tuning constants and hardware profiles."""

from __future__ import annotations

from dataclasses import dataclass
import math


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
B4B_STACK_SOCKET_MIN_SKIN = 0.8  # printable lid skin left beneath a stacking socket
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
B4B_LID_SKIRT_MIN_LAP = 0.30   # smallest lap that still counts as a locating skirt
# A latched lid needs a printable body wall below its latch pad, independent
# of the selected latch strength - see organizer_product_rules.B4B_LATCHED_MIN_HEIGHT.

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

# Shallow socket-head counterbore in the head-side (near) ear of every screw
# stack.  The head sits in the bottom ~0.5 mm of this pocket rather than
# bearing fully proud on the bare clearance bore, so it positively locates
# and cannot wander against the bore edge - without disappearing into the
# ear or reviving the old one-sided head-bearing boss.
B4B_HEAD_POCKET_DIAMETRAL_CLEARANCE = 0.20
B4B_HEAD_RECESS_DEPTH = 0.50


@dataclass(frozen=True)
class HardwareProfile:
    """One metric screw family and every Storage Box dimension derived from it.

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
        """Clearance-bored stack the screw crosses before its lug.

        The head seats ``B4B_HEAD_RECESS_DEPTH`` inside the near ear's outer
        face rather than on it, so the screw starts that much further into
        the stack and this many fewer millimetres of clearance-bored material
        remain between the head and the terminal lug.
        """
        return (
            self.near_ear - B4B_HEAD_RECESS_DEPTH
            + self.mid_member + 2.0 * B4B_RUNNING_GAP
        )

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
    def head_pocket_diameter(self) -> float:
        """Printed counterbore diameter - the physical head plus running clearance."""
        return self.head_diameter + B4B_HEAD_POCKET_DIAMETRAL_CLEARANCE

    @property
    def head_pocket_radius(self) -> float:
        return self.head_pocket_diameter / 2.0

    @property
    def head_bearing_margin(self) -> float:
        """Actual head-bearing material on the uniform outer barrels.

        Measured against the head *pocket*, not the bare head: the pocket is
        what actually gets cut into the barrel's near ear.
        """
        radius = min(self.pivot_radius, self.catch_radius)
        return radius * _SUPPORT_FREE_INSCRIBED - self.head_pocket_diameter / 2.0

    @property
    def required_uniform_radius(self) -> float:
        """Smallest uniform ear radius that protects both bore and head pocket."""
        return max(
            self.clear_bore / 2.0 + self.bore_shell,
            (self.head_pocket_diameter / 2.0 + self.head_bearing_min)
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
    pivot_radius=2.45,
    catch_radius=2.45,
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
    pivot_radius=3.32,
    catch_radius=3.32,
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
# disagree.  Compact B4Bs through 120 x 120 x 64 use M2; larger B4Bs use M3.
# One family is used across hinges, latches and handle, so handle on or off
# does not change the family: one kit, one driver and one BOM line per case.
B4B_HW_M2_MAX_FIELD_XY = 120.0
B4B_HW_M2_MAX_FIELD_Z = 64.0

# --- minimum case ---------------------------------------------------------- #
# A B4B is a carrying case, not a bin with hardware bolted on.  Below this the
# hardware would be the product, so B4B is refused rather than grown.
# See organizer_product_rules for B4B_MIN_FIELD_XY / B4B_LATCHED_MIN_HEIGHT.
# B4B wall floor and default. 0.8 mm is the deliberate Super thin / light duty
# option; 1.6 mm is the default/recommended Storage Box wall. The child field
# stays authoritative, so the extra material grows outward and costs no capacity.
B4B_MIN_WALL = 0.8

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

# --- rear hinges (one or two based on overall lid span) --------------------- #
B4B_HINGE_TWO_ABOVE_SPAN = 160.0
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
#
# The handle is NOT a fixed adult-size fitting bolted onto every case.  Every
# in-plane dimension below is resolved once per case, from the child-field X,
# by :func:`b4b_handle_dimensions` into a :class:`HandleDimensions`, and every
# builder consumes that resolved object - never these raw constants directly -
# so a small B4B gets a small handle on small (M2) hardware and a large B4B
# gets a full-size handle on M3, with nothing hard-coded in between.
#
# Linear scale ramp: child-field X at or below the low end gives the smallest
# handle, at or above the high end gives the largest, ordinary lerp in between.
B4B_HANDLE_SCALE_X_MIN = 96.0
B4B_HANDLE_SCALE_X_MAX = 200.0

# Visible in-plane band width of the lower U grip/arms.
B4B_HANDLE_BAND_MIN = 4.5
B4B_HANDLE_BAND_MAX = 8.0
# Front-to-back arm thickness.  Deliberately not equal to the band: a compact
# handle stays a slim ~4 mm deep even though its visible band is wider.
B4B_HANDLE_THICKNESS_MIN = 4.0
B4B_HANDLE_THICKNESS_MAX = 6.0

# Clear grip (open space between the two arms), as a fraction of child-field X
# between an absolute floor and ceiling.  No fixed 72 mm adult-hand minimum:
# a small case gets a small, honestly-scaled handle instead.
B4B_HANDLE_GRIP_FRACTION = 0.58
B4B_HANDLE_GRIP_ABS_MIN = 36.0
B4B_HANDLE_GRIP_ABS_MAX = 105.0

# Lower-U centreline corner radius, proportional to the band rather than fixed.
B4B_HANDLE_CORNER_FRACTION = 1.20
B4B_HANDLE_CORNER_MIN = 5.0
B4B_HANDLE_CORNER_MAX = 9.0

# Pivot axis to grip centreline, proportional to child-field X.
B4B_HANDLE_DROP_FRACTION = 0.22
B4B_HANDLE_DROP_ABS_MIN = 18.0
B4B_HANDLE_DROP_ABS_MAX = 36.0
# Minimum actual drop a handle is eligible on - proportional to the resolved
# band rather than one fixed number, since a compact handle's arms are
# themselves shorter.
B4B_HANDLE_MIN_DROP_FLOOR = 16.0
B4B_HANDLE_MIN_DROP_BAND_FACTOR = 3.0

# Radial plastic shell kept around the pivot clearance bore.  The eye is sized
# from this and the resolved hardware family's own bore, not from a fixed
# outer radius, so it may legitimately bulge past the arm's own thickness -
# that is intentional: the eye's job is to close completely around the bore.
B4B_HANDLE_EYE_RADIAL_SHELL = 1.20
# Minimum vertical overlap between an arm and its pivot eye once unioned, so
# the eye visibly grows out of the arm instead of merely touching it.
B4B_HANDLE_EYE_OVERLAP = 2.0

# Vertical run over which each arm tapers from the full band down to the eye
# band, proportional to the resolved band.
B4B_HANDLE_TAPER_RUN_FACTOR = 1.5
B4B_HANDLE_TAPER_RUN_MIN = 6.0
B4B_HANDLE_TAPER_RUN_MAX = 10.0

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

# --- front interactions ---------------------------------------------------- #
B4B_FRONT_ROOT_SEPARATION = 1.0    # visible normal wall between root regions
B4B_LABEL_KEEPOUT = 1.0            # label clearance around moving hardware

_EPS = 1e-6
