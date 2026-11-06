"""B4B hinge and latch parts."""

from __future__ import annotations

import trimesh
from shapely.geometry import Point, Polygon
from organizer_engine import BoxSpec
from organizer_geometry import (
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    union,
)
from organizer_engine import WAVE_AMPLITUDE
from shapely.affinity import translate as translate_polygon
from .._constants import (
    B4B_SUPPORT_FREE_FLAT,
    B4B_RUNNING_GAP,
    B4B_HW_RELIEF_CLEARANCE,
    B4B_LID_FITTING_DROP,
)
from .._layout import (
    b4b_layout,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z_from_eff,
    b4b_lid_underside_z,
)
from .._plans import (
    B4BHardwarePlan,
    _ear_wall_anchor_y,
    _wall_extreme_y,
    b4b_hardware_plan,
)

from ._cutters import (
    support_free_profile_yz,
    _filleted,
    _cavity_prism,
    _lid_root_profile,
    _stack_positions,
    _root_profile_yz,
    _root_taper_prism,
    _relief_cutter,
    _pivot_section,
    _ear_solid,
    _gusset,
)


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
        # The fitting hangs B4B_LID_FITTING_DROP below the seat plane and the
        # wall is solid up to that plane, so the drop may only start outboard of
        # the wall crest over the knuckle's own width: clear by the running gap
        # plus the root fillet, which fills back toward the wall.
        crest = _wall_extreme_y(
            layout, mid_x - profile.mid_member / 2.0,
            mid_x + profile.mid_member / 2.0, 1.0,
        )
        root_y = crest + B4B_RUNNING_GAP + plan.fillet_radius
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
        # The fillet where the pivot meets the plate underside bleeds back over
        # the wall band: keep everything below the seat plane outboard of the
        # crest.
        keep_out = Polygon([
            (crest - 10.0, underside_z - 10.0),
            (crest + B4B_RUNNING_GAP, underside_z - 10.0),
            (crest + B4B_RUNNING_GAP, underside_z),
            (crest - 10.0, underside_z),
        ])
        section = section.difference(keep_out)
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
# rear piano hinge (Hinge type: Piano): case and lid knuckles take turns on a
# filament pin behind the back wall.  Nothing is cut from the case: the child
# field is untouched, and the hinge stands out behind the back instead.
# --------------------------------------------------------------------------- #
def _piano_section(points) -> Polygon:
    from shapely.geometry.polygon import orient
    return orient(Polygon(points).buffer(0), 1.0)


def _piano_prism(section: Polygon, x0: float, x1: float) -> trimesh.Trimesh:
    from shapely.geometry.polygon import orient
    # circle/polygon unions leave near-duplicate points that break extrusion
    section = orient(section.simplify(1e-3).buffer(0), 1.0)
    solid = _extrude_yz_profile(section, x1 - x0)
    solid.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    return solid


def _piano_octagon(p) -> Polygon:
    return translate_polygon(support_free_profile_yz(p.half), p.axis_y, p.axis_z)


def _piano_swing(p) -> Polygon:
    return Point(p.axis_y, p.axis_z).buffer(p.swing_radius, quad_segs=48)


def _piano_keeper(box: BoxSpec, p) -> trimesh.Trimesh:
    """The case's own outline plus the strip behind its back, across the
    hinge's span: the hinge may stand out behind, never past the sides."""
    from organizer_geometry import _extrude_polygon

    x0, x1 = p.span
    behind = Polygon([(x0, p.back_y - 0.05), (x1, p.back_y - 0.05),
                      (x1, p.back_y + 4.0 * p.half + 10.0),
                      (x0, p.back_y + 4.0 * p.half + 10.0)])
    outline = b4b_layout(box).outer_structural_polygon.union(behind)
    depth = p.top_z + 1.0
    keeper = _extrude_polygon(outline, depth)
    keeper.apply_translation((0.0, 0.0, -0.5))
    return keeper


def _piano_bore(p) -> trimesh.Trimesh:
    """Straight bore, open at both ends for the filament."""
    x0, x1 = p.span
    return _piano_prism(Point(p.axis_y, p.axis_z).buffer(p.bore_radius, quad_segs=32),
                        x0 - 2.0, x1 + 2.0)


def _piano_body_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Case knuckles, each on a web down to the back wall, and the stop
    ledges under the lid knuckles.  Trimmed off the child field."""
    p = plan.piano
    eff = b4b_effective_box(box)
    r, f = p.half, B4B_SUPPORT_FREE_FLAT * p.half
    ay, az = p.axis_y, p.axis_z
    y_in = p.back_y - (eff.wall_depth + 2.0 * WAVE_AMPLITUDE + 0.5)
    # The web stays below the lid seat (and the axis), so the lid plate's
    # swing never meets it.  Its underside carries on the knuckle's lower rear
    # 45-degree facet forward and down into the wall: printable upright.
    top = min(p.rim_z, az)
    low = az + (y_in - ay) - (1.0 + B4B_SUPPORT_FREE_FLAT) * r
    web = _piano_section([(y_in, top), (y_in, low), (ay + r, az - f), (ay + r, top)])
    knuckle = _piano_octagon(p).union(web)
    # Stop ledge: top face on the stop plane, underside rising backward at 45
    # degrees out of the wall, clear of the lid knuckle's swing.
    back = ay + r
    z_back = p.stop_z(back)
    ledge = _piano_section([
        (y_in, p.stop_z(y_in)), (back, z_back), (back, z_back - 1.5),
        (y_in, z_back - 1.5 - (back - y_in)),
    ]).difference(_piano_swing(p))
    solids = []
    for i, (x0, x1) in enumerate(p.knuckles):
        solids.append(_piano_prism(knuckle if i % 2 == 0 else ledge, x0, x1))
    parts = _intersection([union(solids), _piano_keeper(box, p)])
    return [difference([parts, _cavity_prism(box), _piano_bore(p)])]


def _piano_lid_parts(box: BoxSpec, plan: B4BHardwarePlan) -> list[trimesh.Trimesh]:
    """Lid knuckles: the octagon, an arm out of the plate, and a square heel
    whose back face lands on the stop ledge."""
    p = plan.piano
    r = p.half
    ay, az = p.axis_y, p.axis_z
    arm = _piano_section([(p.back_y - 1.0, p.rim_z), (ay, p.rim_z),
                          (ay, p.top_z), (p.back_y - 1.0, p.top_z)])
    heel = _piano_section([(ay, az), (ay + r, az), (ay + r, p.top_z), (ay, p.top_z)])
    section = _piano_octagon(p).union(arm).union(heel)
    solids = [_piano_prism(section, x0, x1)
              for i, (x0, x1) in enumerate(p.knuckles) if i % 2 == 1]
    parts = _intersection([union(solids), _piano_keeper(box, p)])
    return [difference([parts, _piano_bore(p)])]


def make_b4b_hinge_pin(box: BoxSpec) -> trimesh.Trimesh | None:
    """The filament pin as installed, for previews."""
    plan = b4b_hardware_plan(box)
    p = plan.piano
    if p is None:
        return None
    from .._constants import B4B_PIANO_PIN_DIAMETER
    x0, x1 = p.span
    return _piano_prism(Point(p.axis_y, p.axis_z).buffer(B4B_PIANO_PIN_DIAMETER / 2.0, quad_segs=32),
                        x0 + 0.2, x1 - 0.2)


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
            # Same rule as the rear knuckle: the drop starts outboard of the
            # front wall crest over this ear's width, never inside the wall.
            crest = _wall_extreme_y(
                layout, ex - thickness / 2.0, ex + thickness / 2.0, -1.0
            )
            root_y = crest - B4B_RUNNING_GAP - plan.fillet_radius
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
            section = section.difference(Polygon([
                (crest + 10.0, underside_z - 10.0),
                (crest - B4B_RUNNING_GAP, underside_z - 10.0),
                (crest - B4B_RUNNING_GAP, underside_z),
                (crest + 10.0, underside_z),
            ]))
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
