"""Storage Box (B4B) mechanics and design validation."""

from __future__ import annotations

import math
from organizer_engine import CORNER_INSET, GRID_PITCH, BoxSpec

from ._constants import (
    B4B_STACK_SOCKET_DEPTH,
    B4B_STACK_SOCKET_MIN_SKIN,
    B4B_LID_SKIRT_MIN_LAP,
    B4B_SUPPORT_FREE_FLAT,
    B4B_SUPPORT_FREE_BRIDGE_MAX,
    B4B_SCREW_MAX_TAIL,
    B4B_LID_OPEN_ANGLE,
    B4B_ROOT_CORNER_CLEARANCE,
    B4B_HINGE_CENTRE_GAP,
    B4B_HINGE_MAX_PROJECTION,
    B4B_LATCH_RELEASE_ANGLE,
    B4B_LATCH_OPEN_ANGLE,
    B4B_LATCH_DETENT,
    B4B_LATCH_MAX_PROJECTION,
    B4B_HANDLE_GRIP_ABS_MIN,
    B4B_HANDLE_MAX_PROJECTION,
    B4B_FRONT_ROOT_SEPARATION,
    _EPS,
)
from ._layout import (
    b4b_layout,
    b4b_capacity_units,
    b4b_required_min_wall,
    b4b_min_field,
    b4b_secure_min_height,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
)
from ._plans import (
    B4BHardwarePlan,
    _root_outward,
    _sweep_angles,
    b4b_hardware_plan,
    b4b_handle_eligibility,
    b4b_handle_plan,
)
from ._geometry import (
    validate_b4b_lift_grabbers,
    validate_b4b_side_openings,
    _skirt_lap,
    make_b4b_lid,
    make_b4b_latches,
    make_b4b_handle,
    _sweep_intersection_cc,
)
from ._labels import _apply_top_label
from ._compose import b4b_body_with_features


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
            handle.fork_clear_span,
            handle.far_lug,
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
        raise ValueError("Storage Box body did not generate as a watertight solid")
    lid = None
    if b4b.lid:
        lid = make_b4b_lid(box)
        if b4b.label_location == "top" and b4b.label_text.strip():
            lid, _inlay = _apply_top_label(box, lid)
        if not lid.is_watertight or lid.volume <= 0.0:
            raise ValueError("Storage Box lid did not generate as a watertight solid")

    # 3. the handle: one solid, stowed clear of the wall, and swept to its stop.
    if handle is not None:
        bail = make_b4b_handle(box)
        if bail is None or not bail.is_watertight or bail.volume <= 0.0:
            raise ValueError("the Storage Box handle did not generate as a watertight solid")
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
                f"the hook depth or use a larger Storage Box"
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
    layout_feature_kinds: tuple[str, ...] = (),
    layout_mode: str = "fused",
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
        raise ValueError("validate_b4b_design called on a non-Storage Box design")
    b4b = raw.normalised()
    unsupported = [kind for kind in layout_feature_kinds if kind != "divider"]
    if unsupported:
        raise ValueError(
            "Storage Box supports Dividers only in Parts & options; "
            "remove the other interior parts first."
        )
    if len(layout_feature_kinds) > 1:
        raise ValueError("Storage Box supports one Divider layout.")
    if layout_mode != "fused":
        raise ValueError("a Storage Box layout mode must be 'fused'")
    if flat_inside:
        raise ValueError("the flat-inside band is incompatible with Storage Box")

    min_x, min_y = b4b_min_field(box)
    if box.x + _EPS < min_x or box.y + _EPS < min_y:
        raise ValueError(
            f"a Storage Box child field is at least {min_x:g} x {min_y:g} mm "
            f"({round(min_x / GRID_PITCH)}U x {round(min_y / GRID_PITCH)}U); "
            f"{box.x:g} x {box.y:g} mm is too small to carry the hardware"
        )
    min_wall = b4b_required_min_wall(box)
    if box.wall + _EPS < min_wall:
        raise ValueError(
            f"a Storage Box wall is at least {min_wall:g} mm - this design is set "
            f"to {box.wall:g} mm; raise the wall before regenerating"
        )
    min_height = b4b_secure_min_height()
    if b4b.secure_lid and box.z + _EPS < min_height:
        raise ValueError(
            f"a latched Storage Box lid needs at least {min_height:g} mm of bin "
            f"height; this design is {box.z:g} mm - use Lid Only or a taller "
            f"Storage Box"
        )

    if b4b.lid and b4b.stacking:
        eff = b4b_effective_box(box)
        lid_skin = b4b_lid_skin_from_eff(eff)
        remaining = lid_skin - B4B_STACK_SOCKET_DEPTH
        if remaining + _EPS < B4B_STACK_SOCKET_MIN_SKIN:
            raise ValueError(
                f"the Storage Box lid skin ({lid_skin:g} mm) leaves only "
                f"{remaining:.2f} mm beneath the {B4B_STACK_SOCKET_DEPTH:g} mm "
                f"stacking socket (need {B4B_STACK_SOCKET_MIN_SKIN:g} mm)"
            )

    if b4b.lid and not b4b.secure_lid:
        eff = b4b_effective_box(box)
        lap = _skirt_lap(eff)
        if lap + _EPS < B4B_LID_SKIRT_MIN_LAP:
            raise ValueError(
                f"this Lid Only Storage Box only has {lap:.2f} mm of locating skirt "
                f"lap (need {B4B_LID_SKIRT_MIN_LAP:g} mm); the lid would sit "
                "as a loose, unlocated flat plate - raise the bin height or "
                "loosen the lid snugness"
            )

    cx, cy = b4b_capacity_units(box)
    if cx < 1 or cy < 1:
        raise ValueError("Storage Box interior is smaller than one child unit")

    layout = b4b_layout(box)
    wall = layout.outer_structural_polygon.difference(layout.inner_mating_polygon)
    if wall.is_empty or wall.area <= 0.0:
        raise ValueError("Storage Box outward structural wall is empty")

    validate_b4b_lift_grabbers(box)
    validate_b4b_side_openings(box)
    if box.edge_mount.active:
        raise ValueError("Edge Mount is not available on Storage Box.")

    if b4b.handle:
        eligible, reason = b4b_handle_eligibility(box)
        if not eligible:
            raise ValueError(
                f"this Storage Box cannot carry a handle: {reason.rstrip('.')}"
            )
        handle = b4b_handle_plan(box)
        if handle is None:
            raise ValueError("the handle did not resolve for this Storage Box")
        if handle.screw_length_mm not in handle.profile.lengths:
            raise ValueError(
                "the handle screw did not resolve to an allowed "
                f"{handle.profile.name} length"
            )
        if handle.clear_grip + _EPS < B4B_HANDLE_GRIP_ABS_MIN:
            raise ValueError(
                f"the handle gives only {handle.clear_grip:.1f} mm of clear "
                f"grip (need {B4B_HANDLE_GRIP_ABS_MIN:g} mm)"
            )
        if handle.drop + _EPS < handle.min_drop:
            raise ValueError(
                f"the handle drops only {handle.drop:.1f} mm below its pivots "
                f"(need {handle.min_drop:.1f} mm for fingers)"
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
        if plan.hinge_count not in (1, 2):
            raise ValueError(
                f"a secure Storage Box lid must resolve to one or two hinges; "
                f"got {plan.hinge_count}"
            )
        if len(plan.hinge_centers_x) != plan.hinge_count:
            raise ValueError(
                f"Storage Box hinge plan is inconsistent: hinge_count={plan.hinge_count}, "
                f"but {len(plan.hinge_centers_x)} hinge centers were generated"
            )
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
                    f"corner keep-out; this Storage Box is too narrow for its hardware"
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
                        f"this Storage Box is too wide for a centred bail and its "
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
