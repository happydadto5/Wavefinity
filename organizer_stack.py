"""Stackable bins - a snap-in lid, or bins that snap straight into each other.

Two modes, one shared interlock:

``lid``     the bin is closed by its own printed lid.  The lid plugs into the
            bin mouth and snaps into a groove just under the rim; its top face
            is recessed, and that recess is the seat the next bin's stepped
            base drops into.
``direct``  no lid at all - the next bin's stepped base plugs straight into
            this bin's mouth and snaps into the same groove.

Both modes step the bottom of the bin inward so it plugs into whatever is
below, and both cut the same groove under the rim.  The groove is what needs
material: a thin 0.8 mm wall has nothing left after it, so stacking raises the
wall to :data:`STACK_MIN_WALL` on its own rather than printing a snap that
splits on the first click.

The height the user types is the *stack pitch* - what one bin adds to a
stack - so switching stacking on never changes how tall the finished thing is.
In ``lid`` mode the lid's own plate is taken out of the bin body to pay for it.
"""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from organizer_engine import (
    BoxSpec,
    StackSpec,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, difference, union

# --------------------------------------------------------------------------- #
# tuning - conservative first-print values
# --------------------------------------------------------------------------- #
# The plate has to stay thicker than the seat cut into it, or the recess floor
# lands exactly on the plug's top face and the lid unions as two loose pieces
# instead of one - and the bin above would be standing on nothing.
STACK_LID_SKIN = 2.0      # lid plate above the rim; paid for out of the body
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
STACK_MIN_FLOOR_SKIN = 0.8   # floor left under the stepped base
# A groove this deep needs wall behind it.  0.8 mm would leave 0.45 mm, which
# splits; 1.2 mm leaves 0.85 mm, which holds.
STACK_MIN_WALL = 1.2

_EPS = 1e-6


def stack_spec(box: BoxSpec) -> StackSpec:
    return getattr(box, "stack", None) or StackSpec()


def stack_enabled(box: BoxSpec) -> bool:
    return stack_spec(box).enabled


def stack_lid_rise(box: BoxSpec) -> float:
    """How much taller a closed bin is than its own body."""
    return STACK_LID_SKIN if stack_spec(box).mode == "lid" else 0.0


def stack_step_depth(box: BoxSpec) -> float:
    """How far the bin's own stepped base drops into whatever is below it.

    In lid mode it only has to locate in the lid's recess.  In direct mode it
    is the snap itself, so it reaches far enough to put the bead clear of the
    rim edge it clicks under.
    """
    return STACK_PLUG_DEPTH if stack_spec(box).mode == "direct" else STACK_SEAT_DEPTH


def stack_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec the body and its interior parts are actually built from.

    Identical to what the user asked for except where stacking genuinely
    requires otherwise: a wall thick enough to hold a snap groove, a floor
    thick enough to contain the stepped base (the step is cut out of the floor
    plate - a plug that fits the mouth above has no wall left by definition),
    and, in lid mode, a body shortened by the lid plate so the closed bin still
    measures the height that was typed.
    """
    from dataclasses import replace

    spec = stack_spec(box)
    if not spec.enabled:
        return box
    wall = max(box.wall, STACK_MIN_WALL)
    floor = max(box.base_thickness, stack_step_depth(box) + STACK_MIN_FLOOR_SKIN)
    z = box.z - stack_lid_rise(box)
    return replace(
        box, wall=wall, z=z, base_thickness=floor,
        standard_walls=False, standard_base=False,
    )


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


def _bead_band(eff: BoxSpec) -> Polygon:
    """Plan ring of the snap bead.

    It bites back into the plug rather than sitting tangent on its face: a ring
    that only touches the plug along a surface unions into a second loose
    component instead of one solid.
    """
    plug = _plug_polygon(eff)
    band = plug.buffer(STACK_FIT + STACK_SNAP).difference(plug.buffer(-STACK_BEAD))
    if band.is_empty:
        raise ValueError("this bin is too small for a stacking bead")
    return band


def _groove_band(eff: BoxSpec) -> Polygon:
    """Plan ring the snap groove is cut out of, just inside the wall."""
    outer = wavy_cavity_polygon(eff).buffer(STACK_BEAD)
    inner = wavy_cavity_polygon(eff)
    ring = outer.difference(inner)
    if ring.is_empty:
        raise ValueError("this bin's wall is too thin for a stacking groove")
    return ring


# --------------------------------------------------------------------------- #
# body features
# --------------------------------------------------------------------------- #
def stack_body_cutters(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Solids subtracted from the bin body: the base step and the snap groove.

    ``eff`` must already be the effective box - these are cut at its rim.
    """
    if not stack_enabled(eff):
        return []
    cutters: list[trimesh.Trimesh] = []
    step = stack_step_depth(eff)

    # Base step: shave the outside of the bottom `step` mm back to the plug
    # outline so the bin drops into whatever is below it.  The floor is sized
    # to contain this, so the walls above it are never undercut.
    shell = _extrude_polygon(wavy_outer_polygon(eff), step + 1.0)
    shell.apply_translation((0.0, 0.0, -1.0))
    keep = _extrude_polygon(_plug_polygon(eff), step + 2.0)
    keep.apply_translation((0.0, 0.0, -1.5))
    cutters.append(difference([shell, keep]))

    # Snap groove under the rim, on the inside face.
    groove = _extrude_polygon(_groove_band(eff), STACK_BEAD * 2.0)
    groove.apply_translation((0.0, 0.0, eff.z - STACK_BEAD_DROP - STACK_BEAD))
    cutters.append(groove)
    return cutters


def stack_body_adders(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """The bead on the stepped base that clicks into the groove below."""
    if stack_spec(eff).mode != "direct":
        return []
    bead = _extrude_polygon(_bead_band(eff), STACK_BEAD * 2.0)
    # Measured from the step's own bottom face, mirroring the groove's distance
    # below the rim it clicks under.
    bead.apply_translation((
        0.0, 0.0,
        stack_step_depth(eff) - STACK_BEAD_DROP - STACK_BEAD,
    ))
    return [bead]


# --------------------------------------------------------------------------- #
# the lid
# --------------------------------------------------------------------------- #
def make_stack_lid(box: BoxSpec) -> trimesh.Trimesh:
    """The snap-in lid, in assembly space (closed, sitting on the bin)."""
    eff = stack_effective_box(box)
    if stack_spec(eff).mode != "lid":
        raise ValueError("this bin has no stacking lid")

    rim = eff.z
    plate = _extrude_polygon(wavy_outer_polygon(eff), STACK_LID_SKIN)
    plate.apply_translation((0.0, 0.0, rim))

    plug = _extrude_polygon(_plug_polygon(eff), STACK_PLUG_DEPTH)
    plug.apply_translation((0.0, 0.0, rim - STACK_PLUG_DEPTH))

    bead = _extrude_polygon(_bead_band(eff), STACK_BEAD * 2.0)
    bead.apply_translation((0.0, 0.0, rim - STACK_BEAD_DROP - STACK_BEAD))

    lid = union([plate, plug, bead])

    # The seat: a recess in the top face the next bin's stepped base drops into,
    # exactly as deep as that step is tall, so the bin above lands on the lid's
    # full face and one bin of stack is exactly the height that was typed.
    seat = _extrude_polygon(
        _plug_polygon(eff).buffer(STACK_FIT), STACK_SEAT_DEPTH + 1.0
    )
    seat.apply_translation((0.0, 0.0, rim + STACK_LID_SKIN - STACK_SEAT_DEPTH))
    lid = difference([lid, seat])
    lid.remove_unreferenced_vertices()
    lid.merge_vertices()
    return lid


def stack_closed_height(box: BoxSpec) -> float:
    """Height of the finished bin - body plus its lid.  Always what was typed."""
    return stack_effective_box(box).z + stack_lid_rise(box)


def stack_pitch(box: BoxSpec) -> float:
    """Height one more bin adds to a stack.

    Less than the bin's own height by however far its base sinks into the bin
    below it - the engagement that makes the stack a stack.
    """
    return stack_closed_height(box) - stack_step_depth(box)


def stack_summary(box: BoxSpec) -> dict:
    """Readout for the preview panel and the generation result."""
    spec = stack_spec(box)
    eff = stack_effective_box(box)
    parts = ["Bin"] + (["Lid"] if spec.mode == "lid" else [])
    return {
        "mode": spec.mode,
        "enabled": spec.enabled,
        "closed_height_mm": round(stack_closed_height(box), 3),
        "pitch_mm": round(stack_pitch(box), 3),
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
    if not spec.enabled:
        return
    if getattr(getattr(box, "b4b", None), "enabled", False):
        raise ValueError(
            "a Bin for Bins already stacks on its own - turn B4B stacking on "
            "instead"
        )
    # Checked against the request, before the effective box is built: below
    # this the shortened body fails BoxSpec's own lock-bump minimum, and the
    # user would get told about lock bumps on a bin they never made short.
    floor = stack_step_depth(box) + STACK_MIN_FLOOR_SKIN
    minimum = floor + 5.0 + stack_lid_rise(box)
    if box.z < minimum - _EPS:
        raise ValueError(
            f"a stackable bin needs at least {minimum:g} mm of height - "
            f"the snap and its floor take up the bottom {floor:g} mm"
        )
    eff = stack_effective_box(box)
    _plug_polygon(eff)
    _groove_band(eff)
