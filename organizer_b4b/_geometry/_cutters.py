"""B4B shared profiles, cutters and solids."""

from __future__ import annotations

import trimesh
from shapely.geometry import Point, Polygon
from shapely.affinity import translate as translate_polygon
from organizer_engine import WAVE_AMPLITUDE, BoxSpec
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
)
from .._constants import (
    B4B_SUPPORT_FREE_FLAT,
    B4B_RUNNING_GAP,
    HardwareProfile,
    B4B_LID_ROOT_BITE,
    B4B_LID_ROOT_REACH,
)
from .._layout import B4BLayout, b4b_layout, b4b_effective_box, b4b_rim_z_from_eff
from .._plans import B4BHandlePlan


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
