"""Storage Box (B4B) mechanics and design validation."""

from __future__ import annotations

import math
import numpy as np
import trimesh
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
    B4B_RUNNING_GAP,
    B4B_HANDLE_STOP_FACE,
    B4B_HANDLE_DETENT_RAMP,
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


def _triangle_distances(a, b):
    """Exact triangle-pair distances, including edge crossings and piercings."""
    best = np.full(len(a), np.inf)
    for i in range(3):
        q = trimesh.triangles.closest_point(b, a[:, i])
        best = np.minimum(best, np.sum((q - a[:, i]) ** 2, axis=1))
        q = trimesh.triangles.closest_point(a, b[:, i])
        best = np.minimum(best, np.sum((q - b[:, i]) ** 2, axis=1))
    for i in range(3):
        p, u = a[:, i], a[:, (i + 1) % 3] - a[:, i]
        for j in range(3):
            q, v = b[:, j], b[:, (j + 1) % 3] - b[:, j]
            w = p - q
            uu = np.einsum('ij,ij->i', u, u)
            vv = np.einsum('ij,ij->i', v, v)
            uv = np.einsum('ij,ij->i', u, v)
            uw = np.einsum('ij,ij->i', u, w)
            vw = np.einsum('ij,ij->i', v, w)
            den = uu * vv - uv * uv
            nonparallel = den > 1e-20
            t = np.divide(uv * vw - vv * uw, den,
                          out=np.zeros_like(den), where=nonparallel)
            r = np.divide(uu * vw - uv * uw, den,
                          out=np.zeros_like(den), where=nonparallel)
            interior = nonparallel & (t >= 0) & (t <= 1) & (r >= 0) & (r <= 1)
            d = np.sum((w + t[:, None] * u - r[:, None] * v) ** 2, axis=1)
            best = np.minimum(best, np.where(interior, d, np.inf))
            # Boundary minima of the segment pair.
            for end in (p, p + u):
                f = np.clip(np.divide(np.einsum('ij,ij->i', end - q, v), vv,
                                     out=np.zeros_like(vv), where=vv > 1e-20), 0, 1)
                best = np.minimum(best, np.sum((end - q - f[:, None] * v) ** 2, axis=1))
            for end in (q, q + v):
                f = np.clip(np.divide(np.einsum('ij,ij->i', end - p, u), uu,
                                     out=np.zeros_like(uu), where=uu > 1e-20), 0, 1)
                best = np.minimum(best, np.sum((end - p - f[:, None] * u) ** 2, axis=1))
        # An edge may pierce a triangle without meeting any of its edges.
        for tri, origin, direction in ((b, p, u),
                                       (a, b[:, i], b[:, (i + 1) % 3] - b[:, i])):
            e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
            h = np.cross(direction, e2)
            det = np.einsum('ij,ij->i', e1, h)
            inv = np.divide(1.0, det, out=np.zeros_like(det), where=abs(det) > 1e-14)
            offset = origin - tri[:, 0]
            bary_u = inv * np.einsum('ij,ij->i', offset, h)
            cross = np.cross(offset, e1)
            bary_v = inv * np.einsum('ij,ij->i', direction, cross)
            along = inv * np.einsum('ij,ij->i', e2, cross)
            hit = ((abs(det) > 1e-14) & (bary_u >= 0) & (bary_v >= 0)
                   & (bary_u + bary_v <= 1) & (along >= 0) & (along <= 1))
            best[hit] = 0.0
    return np.sqrt(best)


def _handle_contact_faces(triangles, plan, *, moving):
    """Name only complete triangles on the two specific mating surface pairs.

    A face crossing a contact boundary is deliberately not exempt. Neither an
    angle nor a whole moving/fixed part is ever excluded from clearance.
    """
    tags = np.zeros(len(triangles), dtype=int)
    tol = 2e-5
    for index, cx in enumerate(plan.centers_x, 1):
        x = triangles[:, :, 0] - cx
        y = triangles[:, :, 1] - plan.axis_y
        z = triangles[:, :, 2] - plan.axis_z
        axial = np.all(abs(x) <= plan.eye_band / 2.0 + tol, axis=1)
        if moving:
            ang = math.radians(plan.stop_angle)
            radial = y * math.cos(ang) + z * math.sin(ang)
            tangent = -y * math.sin(ang) + z * math.cos(ang)
            mask = axial & np.all((radial >= plan.eye_radius - 0.6 - tol)
                    & (abs(tangent) <= B4B_HANDLE_STOP_FACE / 2.0 + tol), axis=1)
        else:
            wall_y = triangles[:, :, 1] - plan.front_crest
            mask = axial & np.all((wall_y >= -tol) & (wall_y <= 1.2 + tol)
                    & (abs(z) <= B4B_HANDLE_STOP_FACE / 2.0 + tol), axis=1)
            # Only exposed pad faces, never wall triangles inside its volume.
            on_face = np.all(abs(wall_y) <= tol, axis=1)
            on_face |= np.all(abs(abs(z) - B4B_HANDLE_STOP_FACE / 2.0) <= tol, axis=1)
            on_face |= np.all(np.isclose(abs(x), plan.eye_band / 2.0, atol=tol, rtol=0.0), axis=1)
            mask &= on_face
        tags[mask] = index
    for index, cx in enumerate(plan.detent_centers_x, 3):
        if moving:
            # Pocket floor plus its entry rim form one detent contact
            # surface. Include the bump's ramp footprint, so the unchanged
            # elastic snap can ride onto/off that rim at any swing angle.
            stand = plan.wall_clear + plan.detent_bump
            radius = max(2.0 * B4B_HANDLE_DETENT_RAMP, stand + B4B_HANDLE_DETENT_RAMP)
            reach = radius + B4B_RUNNING_GAP
            delta = triangles - [cx, plan.axis_y, plan.detent_pocket_z]
            patch = np.all((abs(delta[:, :, 0]) <= reach + tol)
                           & (abs(delta[:, :, 2]) <= reach + tol)
                           & (delta[:, :, 1] >= plan.thickness / 2.0 - 0.01), axis=1)
            # Include cut pocket walls/floor as well as the outer entry rim.
            depth = max(0.05, plan.detent_bump - plan.detent_interference)
            centre = np.array([cx, plan.axis_y + plan.eye_radius, plan.detent_pocket_z])
            half = np.array([plan.band * 0.35, depth, 1.5])
            d = abs(triangles - centre)
            pocket = np.all(d <= half + tol, axis=(1, 2))
            tags[patch | pocket] = index
        else:
            stand = plan.wall_clear + plan.detent_bump
            radius = max(2.0 * B4B_HANDLE_DETENT_RAMP, stand + B4B_HANDLE_DETENT_RAMP)
            centre = np.array([cx, plan.front_crest, plan.detent_z])
            bump = trimesh.creation.icosphere(subdivisions=2, radius=radius)
            bump.apply_scale((1.0, stand / radius, 1.0))
            bump.apply_translation(centre)
            lo, hi = bump.bounds
            local = np.flatnonzero(np.all(triangles.max(axis=1) >= lo - tol, axis=1)
                                   & np.all(triangles.min(axis=1) <= hi + tol, axis=1))
            # Boolean cuts add vertices *within* the flat icosphere facets.
            # Comparing ellipsoid radii would misclassify those real faces.
            for start in range(0, len(local), 128):
                ids = local[start:start + 128]
                points = np.concatenate((triangles[ids], triangles[ids].mean(axis=1)[:, None]), axis=1)
                _, distances, _ = trimesh.proximity.closest_point_naive(bump, points.reshape(-1, 3))
                tags[ids[np.all(distances.reshape(-1, 4) <= tol, axis=1)]] = index

    return tags


def _split_detent_surfaces(triangles, plan):
    """Split large arm triangles at the local detent-patch boundary.

    Classification must not depend on the boolean engine's triangulation of
    an otherwise flat arm face, nor exempt the rest of that face.
    """
    stand = plan.wall_clear + plan.detent_bump
    radius = max(2.0 * B4B_HANDLE_DETENT_RAMP, stand + B4B_HANDLE_DETENT_RAMP)
    reach = radius + B4B_RUNNING_GAP
    result = list(triangles)
    for cx in plan.detent_centers_x:
        limits = ((0, cx - reach), (0, cx + reach),
                  (2, plan.detent_pocket_z - reach), (2, plan.detent_pocket_z + reach),
                  (1, plan.axis_y + plan.thickness / 2.0 - 0.01))
        output = []
        for triangle in result:
            lo, hi = triangle.min(axis=0), triangle.max(axis=0)
            if (hi[0] < cx - reach or lo[0] > cx + reach
                    or hi[2] < plan.detent_pocket_z - reach
                    or lo[2] > plan.detent_pocket_z + reach):
                output.append(triangle)
                continue
            polygons = [list(triangle)]
            for axis, value in limits:
                divided = []
                for poly in polygons:
                    if min(v[axis] for v in poly) >= value or max(v[axis] for v in poly) <= value:
                        divided.append(poly)
                        continue
                    sides = [[], []]
                    for v, w in zip(poly, poly[1:] + poly[:1]):
                        side = int(v[axis] >= value)
                        sides[side].append(v)
                        if (v[axis] < value < w[axis]) or (w[axis] < value < v[axis]):
                            point = v + (w - v) * ((value - v[axis]) / (w[axis] - v[axis]))
                            sides[0].append(point)
                            sides[1].append(point)
                        elif v[axis] == value:
                            sides[1 - side].append(v)
                    divided.extend(side for side in sides if len(side) >= 3)
                polygons = divided
            for poly in polygons:
                for i in range(1, len(poly) - 1):
                    tri = np.asarray([poly[0], poly[i], poly[i + 1]])
                    if np.linalg.norm(np.cross(tri[1] - tri[0], tri[2] - tri[0])) > 1e-12:
                        output.append(tri)
        result = output
    return np.asarray(result)


def _validate_handle_clearance(bail, body, plan):
    """Surface-pair clearance over the entire rest-to-stop interval.

    Triangle distances catch grazing, unlike volume. Midpoint checks use a
    rotational displacement bound to certify the intervals between poses;
    uncertain intervals subdivide rather than silently skipping a short rub.
    """
    fixed = np.asarray(body.triangles)
    source = _split_detent_surfaces(np.asarray(bail.triangles), plan)
    moving_tags = _handle_contact_faces(source, plan, moving=True)
    fixed_tags = _handle_contact_faces(fixed, plan, moving=False)
    low, high = fixed.min(axis=1), fixed.max(axis=1)

    def tree(ids):
        lo, hi = low[ids].min(axis=0), high[ids].max(axis=0)
        if len(ids) <= 24:
            return lo, hi, ids, None
        axis = int(np.argmax(hi - lo))
        ids = ids[np.argsort((low[ids, axis] + high[ids, axis]))]
        mid = len(ids) // 2
        return lo, hi, tree(ids[:mid]), tree(ids[mid:])

    root = tree(np.arange(len(fixed)))

    def candidates(node, lo, hi):
        if np.any(node[1] < lo) or np.any(node[0] > hi):
            return []
        if node[3] is None:
            ids = node[2]
            return ids[np.all(high[ids] >= lo, axis=1) & np.all(low[ids] <= hi, axis=1)].tolist()
        return candidates(node[2], lo, hi) + candidates(node[3], lo, hi)

    radii = np.linalg.norm(source[:, :, 1:] - [plan.axis_y, plan.axis_z], axis=2).max(axis=1)
    gap = B4B_RUNNING_GAP

    def certify(left, right):
        angle = (left + right) / 2.0
        half = math.radians((right - left) / 2.0)
        moved = source.copy()
        yz = source[:, :, 1:] - [plan.axis_y, plan.axis_z]
        c, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        moved[:, :, 1] = yz[:, :, 0] * c - yz[:, :, 1] * sn + plan.axis_y
        moved[:, :, 2] = yz[:, :, 0] * sn + yz[:, :, 1] * c + plan.axis_z
        unresolved = False
        for i, triangle in enumerate(moved):
            motion = 2.0 * radii[i] * math.sin(half / 2.0)
            need = gap + motion
            ids = np.asarray(candidates(root, triangle.min(axis=0) - need,
                                        triangle.max(axis=0) + need), dtype=int)
            if not len(ids):
                continue
            # X never changes in this rotation. An axial running gap is an
            # exact certificate even when the generic motion bound is loose.
            xgap = np.maximum(low[ids, 0] - triangle[:, 0].max(),
                              triangle[:, 0].min() - high[ids, 0])
            keep = xgap < gap - 2e-5
            if moving_tags[i]:
                keep &= fixed_tags[ids] != moving_tags[i]
            ids = ids[keep]
            if not len(ids):
                continue
            distances = _triangle_distances(np.repeat(triangle[None], len(ids), axis=0), fixed[ids])
            minimum = float(distances.min())
            if minimum < gap - 2e-5:
                raise ValueError(f"the handle has only {minimum:.3f} mm clearance at {angle:.4f} degrees "
                                 f"(needs {gap:.2f} mm); its ends must not graze the case")
            if minimum < need:
                unresolved = True
        if unresolved:
            if right - left < 0.0001:
                raise ValueError("could not certify the handle's running clearance between swing poses")
            mid = (left + right) / 2.0
            certify(left, mid)
            certify(mid, right)

    # Include both endpoints, and the leaning/deploying interval above zero.
    certify(-plan.stop_angle, -plan.stop_angle)
    certify(plan.rest_angle, plan.rest_angle)
    boundaries = [-plan.stop_angle, *np.arange(-90.0, plan.rest_angle, 5.0), plan.rest_angle]
    boundaries = sorted(set(boundaries))
    for left, right in zip(boundaries, boundaries[1:]):
        certify(left, right)


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
        _validate_handle_clearance(bail, body, handle)
        angles = tuple(-a for a in _sweep_angles(handle.stop_angle))
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
        # The screw head bears on the flat outer face, so this margin is
        # measured from the physical head diameter around the uncut barrel.
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
        if len(plan.hinge_centers_x) == 2:
            # _root_centres forces a minimum separation even when it no longer
            # fits, so bound the gap by the corner-clear span the two roots
            # actually have; a narrow box then fails here, plainly.
            corner_clear = (
                layout.outer_half_x - CORNER_INSET - B4B_ROOT_CORNER_CLEARANCE
            )
            gap = min(
                2.0 * min(abs(c) for c in plan.hinge_centers_x)
                - plan.hinge_root_width,
                2.0 * (corner_clear - plan.hinge_root_width),
            )
            if gap + _EPS < B4B_HINGE_CENTRE_GAP:
                raise ValueError(
                    f"the two hinge roots are only {gap:.2f} mm apart "
                    f"(need {B4B_HINGE_CENTRE_GAP:.1f} mm)"
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
