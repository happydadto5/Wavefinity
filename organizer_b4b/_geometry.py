"""Storage Box (B4B) geometry builders: body, lid, hinge, latch and handle meshes."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.affinity import translate as translate_polygon
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
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    union,
)

from ._constants import (
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
    B4B_SUPPORT_FREE_FLAT,
    B4B_RUNNING_GAP,
    B4B_HEAD_RECESS_DEPTH,
    HardwareProfile,
    B4B_HW_RELIEF_CLEARANCE,
    B4B_LID_ROOT_BITE,
    B4B_LID_ROOT_REACH,
    B4B_LID_FITTING_DROP,
    B4B_HW_FILLET,
    B4B_STACK_BOSS_CHAMFER,
    B4B_HANDLE_EYE_OVERLAP,
    B4B_HANDLE_STOP_FACE,
    B4B_HANDLE_DETENT_RAMP,
    B4B_HANDLE_EDGE_CHAMFER,
    B4B_HANDLE_EDGE_STEPS,
)
from ._layout import (
    B4BLayout,
    b4b_layout,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z_from_eff,
    b4b_lid_underside_z,
    b4b_rim_z_from_eff,
)
from ._plans import (
    B4BHardwarePlan,
    _ear_wall_anchor_y,
    b4b_hardware_plan,
    B4BHandlePlan,
    b4b_handle_plan,
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
            raise RuntimeError("a Storage Box hardware group sits outside the case")
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


def _handle_fork_positions(
    plan: "B4BHandlePlan", centre_x: float
) -> tuple[float, float]:
    """``(near_ear_x, far_lug_x)`` for one handle fork.

    Unlike a hinge or latch stack, this is laid out about the *eye* rather than
    about the group centre: ``centre_x`` is the pivot axis, the eye sits on it,
    and the two ears stand off it by one running gap each.  The near (head)
    ear is outboard and the thread-forming lug faces the case centre, so both
    screws go in from the sides and the middle of the case stays clean.  Reads
    the resolved plan's own pivot stack rather than a fixed M3 global, so a
    compact M2 handle gets its compact fork spacing.
    """
    out = 1.0 if centre_x >= 0.0 else -1.0
    inner = plan.eye_band / 2.0 + B4B_RUNNING_GAP
    near = centre_x + out * (inner + plan.near_ear / 2.0)
    far = centre_x - out * (inner + plan.far_lug / 2.0)
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
        raise RuntimeError("a Storage Box hardware root collapsed")
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


def _head_recess_cutter(
    *, radius: float, depth: float, x_centre: float, thickness: float,
    axis_y: float, axis_z: float, side: int,
) -> trimesh.Trimesh:
    """The shallow cylindrical socket-head counterbore for one ear's outer face.

    ``side`` is +1 to open through the ear's +X face, -1 for its -X face.  The
    shoulder sits exactly ``depth`` inside that face; a small overcut beyond
    the face keeps the boolean from leaving a whisker-thin web there.

    This is a standalone cutter, not something folded into one ear's own
    extrusion, precisely so a caller can subtract it from a FINISHED hardware
    group after every root/ear union - a root deliberately built to overlap
    and reinforce its ear can otherwise refill a pocket cut only inside that
    ear's own solid.
    """
    s = float(side)
    overcut = 0.1
    face_x = x_centre + s * thickness / 2.0
    pocket_x = face_x - s * (depth - overcut) / 2.0
    cutter = _round_bore(radius, depth + overcut)
    cutter.apply_translation((pocket_x, axis_y, axis_z))
    return cutter


def _ear_solid(
    *, section: Polygon, thickness: float, x_centre: float,
    bore_r: float, axis_y: float, axis_z: float,
    head_recess_r: float | None = None,
    head_recess_depth: float = 0.0,
    head_recess_side: int = 0,
) -> trimesh.Trimesh:
    """One printed ear with a uniform outer barrel and a round screw bore.

    When ``head_recess_side`` is +/-1, a shallow cylindrical counterbore is
    also cut into that outer face (+1 = the +X face, -1 = the -X face) so a
    socket-head screw seats slightly recessed instead of bearing on the bare
    clearance bore.  This is only safe when nothing is unioned onto this ear
    afterward - a caller whose root deliberately overlaps the ear must instead
    cut :func:`_head_recess_cutter` from the finished, unioned group.
    """
    ear = _extrude_yz_profile(section, thickness)
    ear.apply_translation((x_centre, 0.0, 0.0))
    bore = _round_bore(bore_r, thickness + 3.0)
    bore.apply_translation((x_centre, axis_y, axis_z))
    cutters = [bore]
    if head_recess_side and head_recess_r is not None and head_recess_depth > 0.0:
        cutters.append(_head_recess_cutter(
            radius=head_recess_r, depth=head_recess_depth,
            x_centre=x_centre, thickness=thickness,
            axis_y=axis_y, axis_z=axis_z, side=head_recess_side,
        ))
    return difference([ear, *cutters])


def _gusset(
    *, root_y: float, root_z: float, top_z: float, axis_y: float, axis_z: float,
    radius: float, outward_sign: float,
) -> Polygon:
    """Support-free Y/Z web carrying a body-mounted pivot barrel into its root.

    The web reaches the outboard endpoint of the barrel's complete lower flat
    and guarantees an underside slope of at least 45 degrees.
    """
    h = B4B_SUPPORT_FREE_FLAT * radius

    # Outboard endpoint of the barrel's lowest horizontal flat.
    support_y = axis_y + outward_sign * h
    support_z = axis_z - radius

    # Ensure the underside from root to barrel rises at >= 45 degrees.
    run = abs(support_y - root_y)
    printable_root_z = min(root_z, support_z - run)

    return Polygon([
        (root_y, printable_root_z),
        (root_y, top_z),
        (axis_y, axis_z + 0.5 * radius),
        (support_y, support_z),
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
        # The outboard screw-head side, matching _stack_positions's own "out"
        # convention: only that (non-terminal) ear gets the head pocket.
        out_x = 1.0 if cx >= 0.0 else -1.0
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
                    outward_sign=1.0,
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
        # Cut the near ear's head pocket from the FINISHED, unioned group, not
        # just from that one ear's own solid: the root is built to overlap and
        # reinforce the ear, and a root that still fills the pocket's Y/Z
        # region at this X would refill a hole cut only inside the ear.
        head_cut = _head_recess_cutter(
            radius=profile.head_pocket_radius,
            depth=B4B_HEAD_RECESS_DEPTH,
            x_centre=near_x,
            thickness=profile.near_ear,
            axis_y=plan.hinge_axis_y,
            axis_z=plan.hinge_axis_z,
            side=int(out_x),
        )
        parts.append(difference([solid, cavity, head_cut]))
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
        out_x = 1.0 if cx >= 0.0 else -1.0
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
                    outward_sign=-1.0,
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
        # Same reasoning as the rear hinge: the catch root is built to overlap
        # its own ears, so the near ear's head pocket is only authoritative
        # once it is cut from the fully unioned receiver.
        head_cut = _head_recess_cutter(
            radius=profile.head_pocket_radius,
            depth=B4B_HEAD_RECESS_DEPTH,
            x_centre=near_x,
            thickness=profile.near_ear,
            axis_y=plan.catch_axis_y,
            axis_z=plan.catch_axis_z,
            side=int(out_x),
        )
        parts.append(difference([solid, cavity, relief, head_cut]))
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
        out_x = 1.0 if cx >= 0.0 else -1.0
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
                    head_recess_r=None if terminal else profile.head_pocket_radius,
                    head_recess_depth=0.0 if terminal else B4B_HEAD_RECESS_DEPTH,
                    head_recess_side=0 if terminal else int(out_x),
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
        raise RuntimeError("the Storage Box latch strap outline did not resolve")
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
    """The U's centreline path, arms plus a real radiused lower corner.

    Each arm's tip runs ``B4B_HANDLE_EYE_OVERLAP`` past the pivot axis rather
    than stopping exactly on it, so the arm and the pivot eye - unioned onto
    it separately in :func:`make_b4b_handle` - genuinely overlap in 3D
    instead of merely touching tangent-to-tangent.
    """
    from shapely.geometry import LineString

    half = plan.pivot_span / 2.0
    grip_z = plan.grip_z
    r = plan.corner_radius
    tip_z = plan.axis_z + B4B_HANDLE_EYE_OVERLAP
    pts = [(-half, tip_z), (-half, grip_z + r)]
    steps = 12
    for i in range(steps + 1):
        a = math.pi + (math.pi / 2.0) * (i / steps)
        pts.append((-half + r + r * math.cos(a), grip_z + r + r * math.sin(a)))
    pts.append((half - r, grip_z))
    for i in range(steps + 1):
        a = -math.pi / 2.0 + (math.pi / 2.0) * (i / steps)
        pts.append((half - r + r * math.cos(a), grip_z + r + r * math.sin(a)))
    pts.append((half, tip_z))
    return LineString(pts)


def b4b_handle_outline(plan: B4BHandlePlan) -> Polygon:
    """X/Z outline of the U's grip/arms: straight arms, broad lower radii,
    straight grip.

    Cross-section is constant through grip and arms and only tapers, near its
    top, from the full band down to the eye band - it stops/tapers *into* the
    pivot zone rather than trying to be the pivot eye itself.  The complete,
    closed eye solid is unioned on separately in :func:`make_b4b_handle`, so
    this outline is never responsible for the round bore's surrounding
    plastic and can never clip it.
    """
    band = plan.band / 2.0
    outline = _handle_centreline(plan).buffer(
        band, cap_style=2, join_style=1, quad_segs=24
    )
    if not isinstance(outline, Polygon) or not outline.is_valid:
        raise RuntimeError("the Storage Box handle outline did not resolve")
    # Taper the band down to the eye width over the top run, so the resolved
    # pivot stack fits without thinning the part a hand actually holds.  The
    # taper is symmetric about each arm's own centreline - narrowing only the
    # outer edges would leave the inner face full width and drive the arm
    # straight into the fork's thread-forming lug.
    half = plan.pivot_span / 2.0
    eye = plan.eye_band / 2.0
    tip_z = plan.axis_z + B4B_HANDLE_EYE_OVERLAP
    z_hi = tip_z + 0.5
    z_lo = plan.axis_z - plan.taper_run
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

    One flat-printed U.  The grip/arms are extruded from the outline through
    the handle thickness; at each pivot a *complete*, separately-built closed
    eye - the same support-free section every other B4B barrel uses - is
    unioned onto the arm with real 3D overlap.  The round clearance bore is
    only cut once every solid (arms, eyes, carry-stop heels) is unioned into
    one piece, so the bore can never be clipped down to a partial C-shape by
    an earlier intersection - it is always subtracted from finished plastic
    that already fully surrounds it.
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

    eyes: list[trimesh.Trimesh] = []
    stops: list[trimesh.Trimesh] = []
    bores: list[trimesh.Trimesh] = []
    pockets: list[trimesh.Trimesh] = []
    heel_r = plan.eye_radius + plan.wall_clear
    for cx in plan.centers_x:
        eye = _extrude_yz_profile(
            support_free_profile_yz(plan.eye_radius), plan.eye_band
        )
        eye.apply_translation((cx, plan.axis_y, plan.axis_z))
        eyes.append(eye)
        stops.append(_handle_stop_heel(plan, cx, heel_r))
        bore = _round_bore(plan.profile.clear_bore / 2.0, plan.eye_band + 2.0)
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
    handle = union([slab, *eyes, *stops])
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
        near_x, far_x = _handle_fork_positions(plan, cx)
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
            group_width=plan.fork_width,
            outward_sign=-1.0,
            crest_y=plan.front_crest,
            face_y=plan.root_face_y,
            z_lo=0.0,
            z_hi=plan.root_top_z,
        )
        solid = _intersection([root, keeper])
        out_x = 1.0 if cx >= 0.0 else -1.0
        for ex, thickness, terminal in (
            (near_x, plan.near_ear, False),
            (far_x, plan.far_lug, True),
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
                    outward_sign=-1.0,
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
            z_ramp_bottom=plan.axis_z - plan.taper_run,
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
        # The fork's root deliberately overlaps its own ears for strength (and
        # spans well above and below the pivot axis - see the resolved plan's
        # own root_above/root_below), so the near ear's head pocket is only
        # authoritative once it is cut from the finished fork, root and heel
        # pad together.
        head_cut = _head_recess_cutter(
            radius=profile.head_pocket_radius,
            depth=B4B_HEAD_RECESS_DEPTH,
            x_centre=near_x,
            thickness=plan.near_ear,
            axis_y=plan.axis_y,
            axis_z=plan.axis_z,
            side=int(out_x),
        )
        parts.append(difference([union([solid, pad]), head_cut]))
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
                f"({exc}); the Storage Box mechanics could not be validated"
            ) from exc
    return worst
