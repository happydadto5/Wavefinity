"""B4B body, lid, skirt and stacking geometry."""

from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon
from organizer_engine import (
    CORNER_INSET,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    LIFT_GRABBER_RIM_CLEARANCE,
    WAVE_AMPLITUDE,
    BoxSpec,
    _lift_grabber_bulge_mesh,
    _place_lift_grabber,
)
from organizer_geometry import (
    _extrude_polygon,
    difference,
    intersection as _intersection,
    union,
)
from .._constants import (
    B4B_STACK_RECESS_DEPTH,
    B4B_STACK_BOSS_DIAMETER,
    B4B_STACK_FEMALE_RADIAL_CLEARANCE,
    B4B_STACK_SOCKET_DEPTH,
    B4B_STACK_SOCKET_INTERFERENCE,
    B4B_STACK_INSET_FRACTION,
    B4B_STACK_INSET_MIN,
    B4B_LID_SKIRT_WALL,
    B4B_LID_SEAT_CLEARANCE,
    B4B_LID_SKIRT_LAP,
    B4B_LID_SKIRT_MIN_LAP,
    B4B_STACK_BOSS_CHAMFER,
)
from .._layout import (
    B4BLayout,
    b4b_layout,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z,
    b4b_rim_z_from_eff,
)
from .._plans import b4b_hardware_plan

from ._cutters import _weld
from ._handle import _handle_body_parts, _lid_rear_relief_cutter
from ._hinges import (
    _hinge_body_parts,
    _hinge_lid_parts,
    _latch_body_parts,
    _latch_lid_parts,
)


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
    """Female locator recesses cut into the Storage Box underside.

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


# --------------------------------------------------------------------------- #
# lift grabbers (B4B inner mating wall)
# --------------------------------------------------------------------------- #
_B4B_GRABBER_WALL_PAIRS = {"+x": "left/right", "-x": "left/right",
                           "+y": "front/back", "-y": "front/back"}


def _b4b_wall_face_table(
    layout: "B4BLayout",
) -> dict[str, tuple[str, float, float, tuple[float, float]]]:
    """Storage Box inner-mating-wall faces, in the same shape as the ordinary bin's
    ``organizer_engine._wall_face_table`` - grabbers must root against the
    authoritative child-facing wall, never the outer case polygon."""
    return {
        "+x": ("y", layout.inner_half_y, layout.inner_half_x, (-1.0, 0.0)),
        "-x": ("y", layout.inner_half_y, -layout.inner_half_x, (1.0, 0.0)),
        "+y": ("x", layout.inner_half_x, layout.inner_half_y, (0.0, -1.0)),
        "-y": ("x", layout.inner_half_x, -layout.inner_half_y, (0.0, 1.0)),
    }


def validate_b4b_lift_grabbers(box: BoxSpec) -> None:
    """Lift grabbers are incompatible with Storage Box.

    They would protrude inward into the exact child-bin field B4B promises
    stays usable edge-to-edge, so B4B refuses to generate with them enabled
    rather than shrinking that field or moving child bins around them."""
    grabbers = box.lift_grabbers
    if not grabbers.enabled:
        return
    raise ValueError(
        "Inside Grip is not available on Storage Box because they would "
        "protrude into the child-bin field."
    )


def validate_b4b_side_openings(box: BoxSpec) -> None:
    """Side Openings are for ordinary bins only, never Storage Box."""
    if not box.side_openings.enabled:
        return
    raise ValueError("Side Openings are not available on Storage Box.")


def make_b4b_lift_grabbers(box: BoxSpec) -> list[trimesh.Trimesh]:
    """Small support-free internal finger ledges on the Storage Box's inner mating
    wall, near the top of the case."""
    grabbers = box.lift_grabbers
    if not grabbers.enabled:
        return []
    validate_b4b_lift_grabbers(box)
    eff = b4b_effective_box(box)
    layout = b4b_layout(eff)
    dims = grabbers.dimensions
    rim_z = b4b_rim_z_from_eff(eff)
    bottom_z = rim_z - LIFT_GRABBER_RIM_CLEARANCE - dims.height
    # See organizer_engine.make_lift_grabbers: a straight, non-wavy grabber
    # needs its hidden root to reach past the wave's full amplitude, not
    # just the ordinary small safety margin, to reliably find solid B4B
    # wall material at every point along its width.
    embed = min(WAVE_AMPLITUDE + LOCK_EMBED, eff.wall_depth - LOCK_SAFE_SKIN)
    local = _lift_grabber_bulge_mesh(dims, embed)
    faces = _b4b_wall_face_table(layout)
    return [
        _place_lift_grabber(local, run_axis, face, inward, bottom_z)
        for wall in grabbers.walls
        for run_axis, _wave_half, face, inward in [faces[wall]]
    ]


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
    hardware.extend(make_b4b_lift_grabbers(box))
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
        raise RuntimeError("Storage Box lid locating skirt collapsed inside the body wall")
    if not isinstance(outer, Polygon) or not isinstance(inner, Polygon):
        raise RuntimeError("Storage Box lid locating skirt must remain a single polygon")
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
        raise ValueError("this Storage Box has no lid")
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
    if skirt_h >= B4B_LID_SKIRT_MIN_LAP:
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
