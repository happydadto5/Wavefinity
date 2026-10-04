"""B4B handle geometry."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import Polygon
from organizer_engine import WAVE_AMPLITUDE, BoxSpec
from organizer_geometry import (
    _extrude_polygon,
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    union,
)
from .._constants import (
    B4B_RUNNING_GAP,
    B4B_HEAD_RECESS_DEPTH,
    B4B_HW_RELIEF_CLEARANCE,
    B4B_HW_FILLET,
    B4B_HANDLE_EYE_OVERLAP,
    B4B_HANDLE_STOP_FACE,
    B4B_HANDLE_DETENT_RAMP,
    B4B_HANDLE_EDGE_CHAMFER,
    B4B_HANDLE_EDGE_STEPS,
)
from .._layout import (
    b4b_layout,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z_from_eff,
)
from .._plans import B4BHardwarePlan, _ear_wall_anchor_y, B4BHandlePlan, b4b_handle_plan

from ._cutters import (
    support_free_profile_yz,
    _round_bore,
    _weld,
    _filleted,
    _cavity_prism,
    _handle_fork_positions,
    _root_profile_yz,
    _root_taper_prism,
    _relief_cutter,
    _pivot_section,
    _head_recess_cutter,
    _ear_solid,
    _gusset,
)


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
