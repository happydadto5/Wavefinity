"""Wavefinity engine constants and spec dataclasses (BoxSpec, ConnectorSpec, lid/stack/B4B/edge/side-opening specs)."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from organizer_pegboard import PegboardMountSpec


# --------------------------------------------------------------------------- #
# wave and box constants
# --------------------------------------------------------------------------- #
WAVE_LENGTH = 4.0        # one full cycle: 2 mm out, 2 mm back
WAVE_AMPLITUDE = 0.4     # deviation each way (0.8 mm peak to peak)
WAVE_MATING_GAP = 0.25   # gap left between two neighbouring walls
SAMPLES_PER_MM = 16

# Box X and Y must be whole multiples of this.
#
# The wave is anchored at each wall's centre, which makes every wall symmetric
# and every box the same whichever way round you turn it.  The price is that a
# box's centre must land on the wave lattice.  Pack boxes edge to edge and a
# box of size S has its centre half a size in from its edge, so sizes must be
# multiples of 2 * WAVE_LENGTH for every centre to land on a multiple of
# WAVE_LENGTH.  Once they do, ``cos(2*pi*(y - centre)/WAVE_LENGTH)`` collapses
# to ``cos(2*pi*y/WAVE_LENGTH)``: the wave stops depending on which box it
# belongs to and becomes one global function of position.  Any two walls that
# meet then nest, whatever the two boxes measure.
#
# Off-grid sizes still tile with their own clones, but collide the moment they
# meet a box of a different size, so they are rejected.
GRID_PITCH = 2.0 * WAVE_LENGTH   # 8.0
MIN_BOX_SIZE = GRID_PITCH        # 8.0 - one grid step
MAX_BOX_SIZE = 350.0             # public-service resource ceiling for X and Y
BASE_UNIT = GRID_PITCH           # one unit is one grid step, so sizes are whole
                                 # numbers of units: 1, 2, 3 ... = 8, 16, 24 mm

# A wall shorter than a connector plus its corner insets simply cannot take one,
# and a wall too short to seat a lock bump clear of both corners gets none.  Both
# are per-wall facts, not reasons to reject the box: a 1-unit-wide bin is a
# perfectly good filler that joins on its long sides only.  ``make_side_connector``
# says so plainly if you ask for a connector that will not fit.

DEFAULT_WALL = 0.8
MIN_WALL = 0.2
MAX_WALL = 2.4
WALL_STEP = 0.2
# The wall thicknesses a *new* design may be given, and what each one is for.
# Exact extrusion width is slicer-dependent, so offering 0.5/1.0/1.5 as well
# only recreates a long list of choices that print identically; these six are
# the ones that mean something different on a 0.4 mm nozzle.
#
# ``MIN_WALL``/``WALL_STEP`` stay as the *validation* floor and quantum, so a
# saved design carrying 0.6 or 1.4 still loads and regenerates unchanged - the
# UI simply shows it as a legacy value until the user picks a current preset.
WALL_PRESETS = (
    (0.4, "Very thin / prototype"),
    (0.8, "Default"),
    (1.2, "Strong"),
    (1.6, "Heavy"),
    (2.0, "Extra heavy"),
    (2.4, "Maximum"),
)
B4B_MATERIAL_PRESETS = (
    (0.8, "Super thin / light duty"),
    (1.2, "Thin"),
    (1.6, "Standard"),
    (2.0, "Strong"),
    (2.4, "Extra strong / maximum"),
)
B4B_WALL_PRESETS = B4B_MATERIAL_PRESETS
B4B_BASE_PRESETS = B4B_MATERIAL_PRESETS
B4B_DEFAULT_WALL = 1.6
B4B_DEFAULT_BASE = 1.6
DEFAULT_BASE_THICKNESS = 0.8
# Base thickness presets, same reasoning as WALL_PRESETS: a short list of
# choices that print differently, not a free numeric field.  A design saved
# with any other base value still loads and regenerates unchanged; the UI
# shows it as a legacy value until the user picks a current preset.  Modes
# that need more than the maximum preset here (stacking, B4B) add their own
# required value dynamically rather than widening this list.
BASE_PRESETS = (
    (0.4, "Very thin"),
    (0.6, "Good"),
    (0.8, "Default"),
    (1.0, "Extra Heavy"),
    (1.2, "Maximum"),
)
DEFAULT_CORNER_FILLET = 0.6   # rounding applied where two wavy walls meet
CORNER_INSET = 1.0            # walls stop this far short of the nominal corner
# Locked in after the physical tolerance print: these are no longer tuning
# knobs, they are the connector's specification.
LOCKED_TOLERANCE = 0.02       # chosen from the printed 5-clip fit plate
LOCKED_CONNECTOR_HEIGHT = 9.6
LOCKED_CONNECTOR_LENGTH = 12.0

# The smallest box that can take a connector on both sides.  A 1-unit side is
# still legal - it just joins on its long sides only.
MIN_JOINABLE_SIZE = (
    math.ceil(
        (2.0 * (LOCKED_CONNECTOR_LENGTH / 2.0 + CORNER_INSET) + WAVE_MATING_GAP - 1e-9)
        / GRID_PITCH
    )
    * GRID_PITCH
)

# Corner connectors: hanging arms start half a pitch from the junction so they
# clear the perpendicular walls; only the cap bridges the junction itself.
CORNER_CONNECTOR_ARM_START = GRID_PITCH / 2.0
CORNER_CONNECTOR_END = GRID_PITCH - CORNER_INSET
DEFAULT_CONNECTOR_HEIGHT = LOCKED_CONNECTOR_HEIGHT
DEFAULT_CAP_THICKNESS = 1.2
DEFAULT_ARM_THICKNESS = 1.0   # two 0.5 mm perimeters
DEFAULT_SIDE_LENGTH = LOCKED_CONNECTOR_LENGTH

# Different-height connector.  Over the shorter bin the arm has to span the
# height difference with no wall beside it - the shorter bin's wall simply is
# not there yet - so a plain 1.0 mm arm is an unbraced blade with the lock
# notches hanging off its end, and it just flexes off the bumps.  Past a small
# drop the arm over that gap is fattened into a web and the whole part is made
# longer, both ramping in with the drop so the unbraced span stays stiff and
# still prints as a clean vertical taper with the cap down.
#
# The channel between the arms is one constant width, because it is cut to hold
# two mated walls.  Over the drop it holds *one*: the shorter bin's wall has not
# started yet, so half that channel is empty air and the clip has nothing to
# bear against for the whole span.  The web therefore does two separate jobs,
# and they must not be traded off against each other:
#
# * Reach back across the seam until it runs on the taller bin's outer face.
#   That is a fixed distance set by the seam - the same whatever the drop is -
#   so it is deliberately not scaled by ``differing_drop_fraction``.
# * Grow outward, into the space the absent wall would have filled, for
#   stiffness.  That part does scale with the drop.
DIFFERING_MIN_DROP = 2.0        # <= one bump pitch: plain extension, no web
DIFFERING_FULL_DROP = 30.0      # web and length maxed here (a 50 -> 20 mm pair)
DIFFERING_WEB_THICKNESS = 3.0   # widest the unbraced span is grown to
DIFFERING_LENGTH_GAIN = 0.5     # + this fraction of length at the full drop
DIFFERING_WEB_TAPER = 6.0       # ramp back to a plain arm before it enters the bin
DIFFERING_WEB_RUN_CLEARANCE = 0.15  # running gap to the taller bin's outer face.
                                # Looser than the arms' 0.02: this face guides
                                # for the whole drop, not 8 mm, so it has to
                                # slide rather than grip.


def differing_drop_fraction(drop: float) -> float:
    """0 below ``DIFFERING_MIN_DROP``, ramping to 1 at ``DIFFERING_FULL_DROP``."""
    if drop <= DIFFERING_MIN_DROP:
        return 0.0
    span = DIFFERING_FULL_DROP - DIFFERING_MIN_DROP
    return max(0.0, min(1.0, (drop - DIFFERING_MIN_DROP) / span))


def differing_web_reach(box: "BoxSpec", connector: "ConnectorSpec") -> float:
    """How far the web reaches inward, past the plain arm's inner face.

    Enough to cross the half of the channel the missing wall would have filled
    and stop ``DIFFERING_WEB_RUN_CLEARANCE`` short of the taller bin's outer
    face.  A property of the seam, so it is the same at every drop - which is
    exactly why it must not be scaled by ``differing_drop_fraction``.
    """
    inner_hw = box.wall_depth + WAVE_MATING_GAP / 2.0 + connector.tolerance
    return max(
        0.0, inner_hw + WAVE_MATING_GAP / 2.0 - DIFFERING_WEB_RUN_CLEARANCE
    )


def differing_connector_plan(
    connector: "ConnectorSpec", base_length: float, height_a: float, height_b: float,
    box: "BoxSpec | None" = None,
) -> dict[str, float | str | bool | None]:
    """Every dimension a different-height connector self-adjusts, in one place.

    ``make_side_connector`` and the UI both read this so the numbers a person is
    shown are exactly the ones the part is built to.  With equal rims it just
    reports the plain part.

    Pass ``box`` to get the true web thickness.  The web is never thinner than
    the inward reach allows, so at small drops it is thicker than the
    drop-scaled target on its own would suggest; without ``box`` the seam is
    unknown and only that target can be reported.
    """
    drop = abs(height_a - height_b)
    fraction = differing_drop_fraction(drop)
    arm_thickness = connector.arm_thickness
    webbed = fraction > 0.0
    grow = (DIFFERING_WEB_THICKNESS - arm_thickness) * fraction if webbed else 0.0
    if webbed and box is not None:
        grow = max(grow, differing_web_reach(box, connector))
    return {
        "drop_mm": drop,
        "drop_fraction": fraction,
        "base_length_mm": base_length,
        "length_mm": base_length * (1.0 + DIFFERING_LENGTH_GAIN * fraction),
        "arm_thickness_mm": arm_thickness,
        "web_thickness_mm": arm_thickness + grow,
        "printed_height_mm": connector.height + drop,
        "shorter_bin": None if height_a == height_b else (
            "A" if height_a < height_b else "B"
        ),
        "webbed": webbed,
    }

# --------------------------------------------------------------------------- #
# lock detent: chamfered bumps inside the wall, notches in the connector arms
# --------------------------------------------------------------------------- #
LOCK_PROTRUSION = 0.35    # how far a bump stands proud of the interior face
LOCK_FLAT = 0.30          # straight band between the two chamfers
LOCK_CHAMFER = 0.35       # 45 degree rise of each chamfer (== protrusion)
LOCK_RUN = 1.2            # length of one bump along the wall
LOCK_SPACING = WAVE_LENGTH / 2.0   # a bump on every extremum, crest and trough
LOCK_CORNER_CLEAR = 2.0   # keep bumps this far short of the wall's tangent, so
                          # the bumps on two walls cannot meet at their corner
LOCK_TOP_BELOW_RIM = 4.0  # top of the upper chamfer, measured down from the rim
LOCK_EMBED = 0.60         # bump/notch roots sink this far into their own wall
LOCK_SAFE_SKIN = 0.05     # keep additive bump roots inside the mating surface
LOCK_NOTCH_CLEARANCE = 0.12


def connector_arm_thickness_floor() -> float:
    """Arm thickness must be strictly greater than this (single authority)."""
    return LOCK_PROTRUSION + LOCK_NOTCH_CLEARANCE + 0.3

# --------------------------------------------------------------------------- #
# floor label: text sunk into the inside floor.  The box gets a pocket and the
# label is the solid that fills it flush, exported as its own object so Bambu
# Studio can print it in a second colour
# --------------------------------------------------------------------------- #
TEXT_CAP_HEIGHT_IDEAL = 15.0   # letter height starts here and scales down to fit
TEXT_CAP_HEIGHT_MIN = 5.0      # legacy auto-placement search threshold
TEXT_CAP_HEIGHT_FLOOR = 5.0    # recommendation threshold for Text editor consent
TEXT_DEPTH = 0.4               # how deep the label is sunk into the floor,
                               # leaving DEFAULT_BASE_THICKNESS - TEXT_DEPTH beneath it
# Fix 058 Correction 1, C1.4D: Edge Mount's own label text-depth default is
# deeper than the floor-label TEXT_DEPTH above. This is deliberately a
# separate constant - it must never change the global TEXT_DEPTH used by
# other label/text systems (floor labels, lid labels, ...). Only a new/
# missing Edge Mount value uses it; an explicit saved 0.4 mm stays 0.4 mm.
EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM = 0.6
TEXT_MIN_BACKING = 0.2         # minimum solid material a recessed label must leave behind it
TEXT_MARGIN = 1.0              # clear space between the label and the cavity wall
TEXT_FONT_FAMILY = "DejaVu Sans"
TEXT_FONT_WEIGHT = "bold"

# A rim label targets 5 mm letters, then scales down only when the selected
# shelf is too short. Its 7 mm ledge leaves one millimetre of breathing room
# either side, and the underside rises 7 mm over the same run: exactly 45
# degrees and printable without support.
TOP_LABEL_LEDGE_DEPTH = 7.0
TOP_LABEL_CAP_HEIGHT = 5.0
TOP_LABEL_CAP_HEIGHT_WARNING = 4.0
TOP_LABEL_MARGIN = 1.0
# Both stack modes and the stack lid enter the bin mouth by 3 mm. Keep the
# shelf just below that plug with a 0.4 mm gap, so it stays near the rim while
# still leaving room to close or stack the bin.
TOP_LABEL_RIM_CLEARANCE = 3.4
SCOOP_HEIGHT_FRACTION = 0.6
SCOOP_FLOOR_TOLERANCE = 0.4   # a scoop lower than this counts as flat floor
SCOOP_CURVE_SEGMENTS = 32



# --------------------------------------------------------------------------- #
# B4B (Bin for Bins) - a container mode, not an interior feature.  All of its
# tuning lives in ``organizer_b4b.py``; this dataclass is only the saved intent.
# --------------------------------------------------------------------------- #
B4B_LID_HEADROOM_CHOICES = (0.5, 1.0, 2.0)   # UI: Lid snugness (Tight/Standard/Loose)
# Latch count and latch strength are both derived from the case now - the count
# from one authoritative width threshold, the geometry from the automatically
# selected screw family.  Both tuples survive only so an older saved design
# still parses; neither is offered as a new choice.
B4B_LATCH_COUNTS = ("auto", "1", "2")
B4B_LATCH_STRENGTHS = ("lightweight", "standard")
B4B_LABEL_LOCATIONS = ("none", "top", "front")
# Cosmetic style of the removable front label only; meaningless for the top
# label or when there is no label at all.
B4B_FRONT_LABEL_STYLES = ("flat", "wavy")
# Saved-design schema version for B4B intent.  Bumped when the meaning of a
# field changes rather than inferred from dimensions: v2 moved the carrying
# handle from a lid-top arch to a folding front bail, so a v1 ``handle: true``
# is an *intent* that must be re-validated against the new eligibility rules
# instead of being trusted.
B4B_SCHEMA_VERSION = 2


# ``lid`` remains accepted only as a legacy in-memory/import value. New saved
# designs keep vertical stacking (``direct``) separate from their LidSpec.
STACK_MODES = ("none", "lid", "direct")


@dataclass(frozen=True)
class StackSpec:
    """How a bin joins the bin above and below it.

    ``none``   - an ordinary open bin.
    ``lid``    - a snap-in lid closes the bin and its top face becomes the seat
                 the next bin sits in.  The lid is printed as its own part.
    ``direct`` - no lid: the next bin's stepped base snaps straight into this
                 bin's mouth.

    Serialised as ``box.stack``; inert on ``none`` so an ordinary bin is
    untouched.
    """

    mode: str = "none"

    def __post_init__(self) -> None:
        if self.mode not in STACK_MODES:
            raise ValueError(
                f"stacking mode must be one of {', '.join(STACK_MODES)}"
            )

    @property
    def enabled(self) -> bool:
        return self.mode != "none"


LID_THICKNESSES = ("thin", "medium", "thick")
LID_LABEL_STYLES = ("flush", "raised")
LID_LABEL_ORIENTATIONS = ("horizontal", "vertical")
LID_HANDLE_TYPES = ("knob", "pull")
LID_HANDLE_SIZES = ("small", "medium", "large")
LID_HANDLE_POSITIONS = ("left", "right", "front", "back", "middle")
# Removable-lid plug clearance per side. Only the lid's own bottom plug uses
# this; the direct stack foot and a stackable lid's top recess keep STACK_FIT.
LID_FITS = ("tight", "standard", "loose")
LID_FIT_MM = {"tight": 0.15, "standard": 0.25, "loose": 0.35}
LID_FIT_NAMES = {"tight": "Tight", "standard": "Standard", "loose": "Loose"}
# Lid label relief (Inlay depth / Raised height), same presets as Text.
LID_LABEL_RELIEFS = (0.2, 0.4, 0.6, 0.8)
LID_LABEL_RELIEF_NAMES = {0.2: "Thin", 0.4: "Default", 0.6: "Thick", 0.8: "Thickest"}
LID_LABEL_LEGACY_INLAY_MM = 0.4
LID_LABEL_LEGACY_RAISED_MM = 0.6


@dataclass(frozen=True)
class LidSpec:
    """Ordinary-bin lid intent. Storage Box owns its separate lid system."""

    enabled: bool = False
    stackable: bool = False
    thickness: str = "thin"
    label_enabled: bool = False
    label_style: str = "flush"
    label_orientation: str = "horizontal"
    label_text: str = ""
    division_labels: tuple[str, ...] = ()
    handle_type: str = "knob"
    handle_size: str = "medium"
    handle_position: str = "middle"
    fit: str = "standard"
    # None is the legacy "no saved value" signal: an old inlaid label was
    # 0.4 mm and an old raised label 0.6 mm. Canonical saves always write it.
    label_depth_mm: float | None = None

    def __post_init__(self) -> None:
        choices = (
            (self.fit, LID_FITS, "lid fit"),
            (self.thickness, LID_THICKNESSES, "lid thickness"),
            (self.label_style, LID_LABEL_STYLES, "lid label style"),
            (self.label_orientation, LID_LABEL_ORIENTATIONS, "lid label orientation"),
            (self.handle_type, LID_HANDLE_TYPES, "lid handle type"),
            (self.handle_size, LID_HANDLE_SIZES, "lid handle size"),
            (self.handle_position, LID_HANDLE_POSITIONS, "lid handle position"),
        )
        for value, allowed, name in choices:
            if value not in allowed:
                raise ValueError(f"{name} must be one of {', '.join(allowed)}")
        if self.label_depth_mm is not None and not any(
            math.isclose(float(self.label_depth_mm), preset, abs_tol=1e-9)
            for preset in LID_LABEL_RELIEFS
        ):
            raise ValueError(
                "lid label depth must be one of "
                + ", ".join(f"{preset:g}" for preset in LID_LABEL_RELIEFS) + " mm"
            )
        if self.stackable and not self.enabled:
            raise ValueError("a stackable lid must be enabled")
        if self.stackable and self.label_style == "raised" and self.label_enabled:
            raise ValueError("a stackable lid cannot use raised lettering")


def lid_fit_mm(box: "BoxSpec") -> float:
    """Sliding clearance per side of the removable lid's bottom plug."""
    return LID_FIT_MM[lid_spec(box).fit]


def lid_label_relief_mm(spec: LidSpec) -> float:
    """Resolved Inlay depth / Raised height, honouring legacy missing values."""
    if spec.label_depth_mm is not None:
        return float(spec.label_depth_mm)
    return (LID_LABEL_LEGACY_RAISED_MM if spec.label_style == "raised"
            else LID_LABEL_LEGACY_INLAY_MM)


def lid_spec(box: "BoxSpec") -> LidSpec:
    spec = getattr(box, "lid", None) or LidSpec()
    # Compatibility for callers that still construct StackSpec(mode="lid")
    # directly. Serialization migrates this to a real LidSpec.
    if getattr(getattr(box, "stack", None), "mode", "none") == "lid" and not spec.enabled:
        return LidSpec(enabled=True, stackable=True)
    return spec


def lid_enabled(box: "BoxSpec") -> bool:
    return lid_spec(box).enabled


def lid_stackable(box: "BoxSpec") -> bool:
    spec = lid_spec(box)
    return spec.enabled and spec.stackable


def lid_has_handle(box: "BoxSpec") -> bool:
    spec = lid_spec(box)
    return spec.enabled and not spec.stackable


def direct_stack_enabled(box: "BoxSpec") -> bool:
    return getattr(getattr(box, "stack", None), "mode", "none") == "direct"


def vertical_stack_enabled(box: "BoxSpec") -> bool:
    return direct_stack_enabled(box) or lid_stackable(box)


@dataclass(frozen=True)
class B4BSpec:
    """User-facing Storage Box settings.  Serialised as ``box.b4b``; harmless defaults
    when ``enabled`` is ``False`` so an ordinary bin is untouched."""

    enabled: bool = False
    lid: bool = True
    secure_lid: bool = True
    latch_count: str = "auto"          # legacy only; derived from case width
    latch_strength: str = "standard"   # legacy only; derived from screw family
    lid_headroom_mm: float = 1.0       # UI: Lid snugness
    label_enabled: bool = False
    label_text: str = ""
    label_location: str = "top"        # none | top | front
    front_label_style: str = "flat"    # flat | wavy; meaningful only when
                                        # label_location == "front"
    stacking: bool = False
    handle: bool = False               # folding U/bail on the body front wall
    version: int = B4B_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.latch_count not in B4B_LATCH_COUNTS:
            raise ValueError(
                f"latch count must be one of {', '.join(B4B_LATCH_COUNTS)}"
            )
        if self.latch_strength not in B4B_LATCH_STRENGTHS:
            raise ValueError(
                f"latch strength must be one of {', '.join(B4B_LATCH_STRENGTHS)}"
            )
        if self.label_location not in B4B_LABEL_LOCATIONS:
            raise ValueError(
                f"label location must be one of {', '.join(B4B_LABEL_LOCATIONS)}"
            )
        if self.front_label_style not in B4B_FRONT_LABEL_STYLES:
            raise ValueError(
                "front label style must be one of "
                f"{', '.join(B4B_FRONT_LABEL_STYLES)}"
            )
        if not math.isfinite(self.lid_headroom_mm) or self.lid_headroom_mm <= 0:
            raise ValueError("lid snugness (headroom) must be a positive number")
        if not any(
            math.isclose(self.lid_headroom_mm, choice, abs_tol=1e-6)
            for choice in B4B_LID_HEADROOM_CHOICES
        ):
            allowed = ", ".join(f"{c:g}" for c in B4B_LID_HEADROOM_CHOICES)
            raise ValueError(f"lid snugness must be one of {allowed} mm")

    def normalised(self) -> "B4BSpec":
        """Return the coherent Storage Box configuration used by geometry.

        Enabled B4B designs always have a lid. Older no-lid files reopen as a
        Lid Only design; dependent hardware and stacking settings stay off.
        Label location is a stored preference, not a request for geometry
        while the label text is blank.

        The carrying handle is a folding bail on the *body* front wall, so it
        no longer competes with stacking for the lid top and the two may be
        selected together.  It does still require a secure lid: a handle is a
        promise that the case can be picked up and carried, and a passive lid
        would simply fall off.  Whether the case is actually big enough to
        carry one is geometry, answered by ``b4b_handle_eligibility``, not
        something this dataclass can decide.
        """
        legacy_lid = bool(self.lid)
        lid = True if self.enabled else legacy_lid
        secure = bool(self.secure_lid) and legacy_lid
        stacking = bool(self.stacking) and legacy_lid
        handle = bool(self.handle) and secure
        # Latch count is user-configurable (Auto/1/2); strength is still
        # derived from the case, not an override.
        latch_count = self.latch_count
        latch_strength = self.latch_strength
        return B4BSpec(
            enabled=self.enabled,
            lid=lid,
            secure_lid=secure,
            latch_count=latch_count,
            latch_strength=latch_strength,
            lid_headroom_mm=self.lid_headroom_mm,
            label_enabled=self.label_enabled,
            label_text=self.label_text,
            label_location=self.label_location,
            front_label_style=self.front_label_style,
            stacking=stacking,
            handle=handle,
            version=B4B_SCHEMA_VERSION,
        )


LIFT_GRABBER_SIZES = ("small", "medium", "large", "xl")
LIFT_GRABBER_LOCATIONS = ("sides", "front_back", "both")
# How far below the rim the grabber's top sits.  Clears ordinary connector
# lock geometry (top ``LOCK_TOP_BELOW_RIM`` = 4 mm below rim), the rim label
# ledge, stack snap/groove geometry, and a B4B lid skirt.
LIFT_GRABBER_RIM_CLEARANCE = 8.0
LIFT_GRABBER_FLOOR_CLEARANCE = 2.0     # required gap above the effective floor
LIFT_GRABBER_WALL_MARGIN = 4.0         # extra along-wall room beyond the width
# A grabber's hidden root has to actually bite into real wall material, not
# just clear the wave amplitude on paper.  On a very thin wall the embed
# formula in ``make_lift_grabbers`` caps out at (or near) the wave amplitude
# itself, leaving next to nothing behind it - this is the least real bite a
# grabber is allowed to root into.
LIFT_GRABBER_MIN_ROOT_BITE = 0.2


@dataclass(frozen=True)
class LiftGrabberDimensions:
    """One size preset: along-wall width, inward projection, total height."""

    width: float
    projection: float
    height: float


LIFT_GRABBER_DIMENSIONS: dict[str, LiftGrabberDimensions] = {
    "small":  LiftGrabberDimensions(10.0, 1.5, 5.0),
    "medium": LiftGrabberDimensions(15.0, 2.0, 7.0),
    "large":  LiftGrabberDimensions(20.0, 2.7, 9.0),
    "xl":     LiftGrabberDimensions(26.0, 3.5, 11.0),
}


@dataclass(frozen=True)
class LiftGrabberSpec:
    """Optional small internal finger ledges near the top of a bin, so it can
    be lifted when neighbouring bins block the outside walls.  Default off;
    inert for every existing design."""

    enabled: bool = False
    size: str = "medium"
    location: str = "sides"

    def __post_init__(self) -> None:
        if self.size not in LIFT_GRABBER_SIZES:
            raise ValueError(
                f"Inside Handle size must be one of {', '.join(LIFT_GRABBER_SIZES)}"
            )
        if self.location not in LIFT_GRABBER_LOCATIONS:
            raise ValueError(
                "Inside Handle location must be one of "
                f"{', '.join(LIFT_GRABBER_LOCATIONS)}"
            )

    @property
    def dimensions(self) -> LiftGrabberDimensions:
        return LIFT_GRABBER_DIMENSIONS[self.size]

    @property
    def walls(self) -> tuple[str, ...]:
        """Interior wall names this configuration grows a grabber on."""
        if self.location == "sides":
            return ("+x", "-x")
        if self.location == "front_back":
            return ("+y", "-y")
        return ("+x", "-x", "+y", "-y")

    @property
    def size_label(self) -> str:
        return "XL" if self.size == "xl" else self.size.capitalize()


MIN_HEIGHT_ABOVE_BASE = 5.0    # Z must clear the base by at least this, to fit the lock bump


@dataclass(frozen=True)
class EdgeMountSpec:
    """Optional modifier that lets an ordinary bin mount vertically to the
    outside face of a cart, table, shelf or workbench.  Default off; inert
    for every existing design.  Geometry, validation and planning live in
    ``organizer_edge_mount.py`` - this is only the saved shape of the data."""

    side: str = "front"

    label_enabled: bool = False
    label_text: str = ""
    label_type: str = "separate"          # "separate" | "integrated"
    label_projection_mm: float = 50.0
    label_length_mode: str = "full"       # "full" | "text"
    label_thickness_mm: float = 2.0
    label_raised: bool = False
    label_text_depth_mm: float = EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM
    label_flip: bool = False
    # Separate-label clips stand proud of the wavy wall. Permanent ribs keep
    # the bin plumb against its mounting surface; None means Auto spacing.
    standoff_ribs_enabled: bool = True
    standoff_rib_count: int | None = None

    holes_enabled: bool = False
    hole_count: int = 2
    hole_orientation: str = "horizontal"  # "horizontal" | "vertical"
    screw_diameter_mm: float = 4.0
    access_diameter_mm: float | None = None
    top_offset_mm: float = 12.7
    hole_spacing_mm: float | None = None

    def __post_init__(self) -> None:
        # Fix 058 Correction 1, C1.4C: a Separate Part label is exported and
        # rotated for its print orientation with the text face down, so
        # Raised text is not a valid manufacturing state for it. Normalize
        # here - not only in the browser - so a legacy saved design or any
        # non-UI/programmatic path cannot bypass the invariant by
        # constructing label_type="separate" with label_raised=True.
        if self.label_type == "separate" and self.label_raised:
            object.__setattr__(self, "label_raised", False)

    @property
    def active(self) -> bool:
        return self.label_enabled or self.holes_enabled


SIDE_OPENING_SHAPES = ("curved", "square")
SIDE_OPENING_SIZES = ("small", "medium", "large", "xl")
SIDE_OPENING_WIDTHS = {
    "small": 8.0,
    "medium": 10.0,
    "large": 15.0,
    "xl": 20.0,
}
SIDE_OPENING_SIDES = ("front", "back", "left", "right")


@dataclass(frozen=True)
class SideOpeningSpec:
    """Optional bin-level finger-access cutouts through selected walls.

    Not an interior part - it modifies the bin body itself, like
    ``LidSpec``.  Default off; inert for every existing design.  Geometry,
    validation and cutter generation live in ``organizer_side_openings.py`` -
    this is only the saved shape of the data."""

    enabled: bool = False
    shape: str = "curved"
    sides: tuple[str, ...] = ()
    size: str = "medium"
    # Fix 034 H: inset_v2 semantics - 0 means the opening reaches that edge
    # (floor for bottom, rim for top); a higher percentage pulls it inward.
    from_bottom_percent: float = 0.0
    from_top_percent: float = 0.0

    def __post_init__(self) -> None:
        if self.shape not in SIDE_OPENING_SHAPES:
            raise ValueError(
                f"side opening shape must be one of {', '.join(SIDE_OPENING_SHAPES)}"
            )
        if self.size not in SIDE_OPENING_SIZES:
            raise ValueError(
                f"side opening size must be one of {', '.join(SIDE_OPENING_SIZES)}"
            )
        seen: set[str] = set()
        for side in self.sides:
            if side not in SIDE_OPENING_SIDES:
                raise ValueError(
                    f"side opening side must be one of {', '.join(SIDE_OPENING_SIDES)}"
                )
            if side in seen:
                raise ValueError(f"side opening side '{side}' is duplicated")
            seen.add(side)
        for name, value in (
            ("from bottom", self.from_bottom_percent),
            ("from top", self.from_top_percent),
        ):
            if not math.isfinite(value) or not (0.0 <= value <= 100.0):
                raise ValueError(f"side opening {name} must be between 0 and 100 percent")
        if self.from_bottom_percent + self.from_top_percent >= 100.0:
            raise ValueError("side opening top must be above its bottom")
        if self.enabled and not self.sides:
            raise ValueError("side openings are enabled but no sides are selected")

    @property
    def width_mm(self) -> float:
        return SIDE_OPENING_WIDTHS[self.size]


@dataclass(frozen=True)
class BoxSpec:
    x: float = MIN_JOINABLE_SIZE
    y: float = MIN_JOINABLE_SIZE
    z: float = 40.0
    wall: float = DEFAULT_WALL
    corner_fillet: float = DEFAULT_CORNER_FILLET
    flat_inside: float = 0.0   # mm of flat-walled band rising from the floor
    base_thickness: float = DEFAULT_BASE_THICKNESS
    standard_base: bool = True
    # UI/save-state intent only. ``wall`` remains the authoritative geometry
    # value so existing positional callers and CLI custom walls keep working.
    standard_walls: bool = True
    # B4B (Bin for Bins) container settings.  Trailing ``default_factory`` field
    # so every existing positional ``BoxSpec(...)`` call is unaffected and an
    # ordinary bin carries a disabled, inert B4BSpec.
    b4b: B4BSpec = field(default_factory=B4BSpec)
    # Stacking, same reasoning: trailing and inert unless switched on.
    stack: StackSpec = field(default_factory=StackSpec)
    # Internal lift grabbers, same reasoning: trailing and inert unless
    # switched on. Available to every bin type, not just B4B.
    lift_grabbers: LiftGrabberSpec = field(default_factory=LiftGrabberSpec)
    lid: LidSpec = field(default_factory=LidSpec)
    # Edge Mount modifier (projecting label + screw mounting), same reasoning:
    # trailing and inert unless switched on.
    edge_mount: EdgeMountSpec = field(default_factory=EdgeMountSpec)
    # Side Openings modifier (finger-access wall cutouts), same reasoning:
    # trailing and inert unless switched on. Last so every older positional
    # BoxSpec call keeps its meaning.
    side_openings: SideOpeningSpec = field(default_factory=SideOpeningSpec)
    # Pegboard Space mounting. Inert for every ordinary/legacy design.
    pegboard: PegboardMountSpec = field(default_factory=PegboardMountSpec)

    def __post_init__(self) -> None:
        values = {
            "X": self.x, "Y": self.y, "Z": self.z,
            "wall": self.wall, "corner fillet": self.corner_fillet,
            "base thickness": self.base_thickness,
        }
        for name, value in values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if not MIN_WALL <= self.wall <= MAX_WALL:
            raise ValueError(
                f"wall thickness must be between {MIN_WALL:g} and {MAX_WALL:g} mm"
            )
        if not 0.0 <= self.flat_inside <= 1.0:
            raise ValueError("flat inside must be between 0 and 1 mm")
        if self.flat_inside > 0.0 and self.base_thickness + self.flat_inside >= self.z:
            raise ValueError("box is too shallow for a flat-walled band")
        if self.base_thickness < TEXT_DEPTH:
            raise ValueError(
                f"base thickness must be at least {TEXT_DEPTH:g} mm"
            )
        if self.z < self.base_thickness + MIN_HEIGHT_ABOVE_BASE:
            raise ValueError(
                f"box Z must be at least {self.base_thickness + MIN_HEIGHT_ABOVE_BASE:g} mm "
                "to fit the lock bump"
            )
        for name, value in (("X", self.x), ("Y", self.y)):
            if value < MIN_BOX_SIZE - 1e-9:
                raise ValueError(
                    f"box {name} must be at least {MIN_BOX_SIZE:.0f} mm"
                )
            if value > MAX_BOX_SIZE + 1e-9:
                raise ValueError(
                    f"box {name} must be {MAX_BOX_SIZE:.0f} mm or smaller"
                )
            units = value / GRID_PITCH
            if abs(units - round(units)) > 1e-6:
                nearest = max(round(units), MIN_BOX_SIZE / GRID_PITCH)
                raise ValueError(
                    f"box {name} must be a whole multiple of the {GRID_PITCH:.0f} mm "
                    f"grid so boxes of different sizes still interlock; "
                    f"{value:g} mm is not - try {nearest * GRID_PITCH:.0f} mm"
                )
        if self.wall_depth * 2.0 >= min(self.x, self.y) - WAVE_MATING_GAP - 2.0 * WAVE_AMPLITUDE:
            raise ValueError("wall thickness leaves no cavity")

    @property
    def half_x(self) -> float:
        return self.x / 2.0 - WAVE_MATING_GAP / 2.0

    @property
    def half_y(self) -> float:
        return self.y / 2.0 - WAVE_MATING_GAP / 2.0

    @property
    def units(self) -> tuple[int, int]:
        """Size in whole units, e.g. ``(2, 6)`` for 16 x 48 mm.

        One unit is one grid step, so every legal size is a whole number of
        units and no decimals are needed.
        """
        return round(self.x / BASE_UNIT), round(self.y / BASE_UNIT)

    @property
    def grid_steps(self) -> tuple[int, int]:
        """Size in whole ``GRID_PITCH`` units, e.g. ``(3, 9)`` for 24 x 72 mm."""
        return round(self.x / GRID_PITCH), round(self.y / GRID_PITCH)

    @property
    def footprint(self) -> tuple[float, float]:
        """What the box occupies on the drawer grid - its nominal X and Y."""
        return self.x, self.y

    @property
    def outside_extent(self) -> tuple[float, float]:
        """Real outside size, crest to crest, which the wave pushes past the
        grid footprint by one amplitude each side."""
        span = 2.0 * WAVE_AMPLITUDE - WAVE_MATING_GAP
        return self.x + span, self.y + span

    @property
    def usable_inside(self) -> tuple[float, float]:
        """Largest axis-aligned rectangle that fits the cavity.

        Both faces of a wall carry the same wave, so the cavity is a channel of
        constant width that weaves from side to side.  A straight-sided object
        has to clear the wave's full swing, which costs one amplitude at each
        end on top of the two walls.
        """
        clear_x = 2.0 * (self.half_x - self.wall_depth) - 2.0 * WAVE_AMPLITUDE
        clear_y = 2.0 * (self.half_y - self.wall_depth) - 2.0 * WAVE_AMPLITUDE
        return clear_x, clear_y

    @property
    def usable_opening(self) -> tuple[float, float]:
        """The user-facing "Inside" size: ``usable_inside`` minus room the lock
        bumps' upper-band protrusion takes back on each side.

        Fused floor features may still use the full ``usable_inside`` area
        below the bump band; this is only what the general opening promises.
        """
        x, y = self.usable_inside
        return (
            max(0.0, x - 2.0 * LOCK_PROTRUSION),
            max(0.0, y - 2.0 * LOCK_PROTRUSION),
        )

    @property
    def wall_depth(self) -> float:
        """Wall thickness measured along the axis, not along the surface normal.

        Shifting the outline by this much keeps the true perpendicular wall at
        or above ``wall`` everywhere on the wave.
        """
        return wall_depth_for(self.wall)


@dataclass(frozen=True)
class ConnectorSpec:
    tolerance: float = LOCKED_TOLERANCE
    height: float = DEFAULT_CONNECTOR_HEIGHT
    cap_thickness: float = DEFAULT_CAP_THICKNESS
    arm_thickness: float = DEFAULT_ARM_THICKNESS

    def __post_init__(self) -> None:
        values = {
            "tolerance": self.tolerance, "height": self.height,
            "cap thickness": self.cap_thickness, "arm thickness": self.arm_thickness,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.tolerance < 0 or self.tolerance > 1.0:
            raise ValueError("tolerance must be between 0.0 and 1.0 mm")
        if self.cap_thickness <= 0:
            raise ValueError("cap thickness must be positive")
        if self.height <= self.cap_thickness:
            raise ValueError("connector height must exceed its cap thickness")
        if self.arm_thickness <= connector_arm_thickness_floor():
            raise ValueError("arm thickness leaves too little material at the notch")

    @property
    def arm_depth(self) -> float:
        """How far the arms reach below the underside of the cap."""
        return self.height - self.cap_thickness


# --------------------------------------------------------------------------- #
# the wave
# --------------------------------------------------------------------------- #
def max_wave_slope() -> float:
    return WAVE_AMPLITUDE * 2.0 * math.pi / WAVE_LENGTH


def wall_depth_for(wall: float) -> float:
    """``BoxSpec.wall_depth``'s formula, standalone.

    Lets a caller that builds wavy geometry without a full ``BoxSpec`` -
    a spacer filler, whose x/y need not be the 8 mm-grid size a normal bin's
    ``BoxSpec`` requires - use the exact same wall-thickness math.
    """
    return wall * math.sqrt(1.0 + max_wave_slope() ** 2)
