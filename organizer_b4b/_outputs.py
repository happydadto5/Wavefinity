"""Storage Box (B4B) summary, print-object planning and exported parts."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from organizer_engine import GRID_PITCH, BoxSpec
from organizer_geometry import translated

from ._constants import (
    B4B_STACK_RECESS_DEPTH,
    B4B_LID_SKIRT_MIN_LAP,
    B4B_PRINT_PART_GAP,
)
from ._layout import (
    b4b_layout,
    b4b_capacity_units,
    b4b_capacity_mm,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_grew,
    b4b_max_child_height,
    b4b_lid_underside_z,
)
from ._plans import b4b_hardware_plan, b4b_handle_eligibility, b4b_handle_plan
from ._geometry import (
    _skirt_lap,
    make_b4b_lid,
    _stack_pegs,
    make_b4b_latches,
    make_b4b_handle,
)
from ._labels import (
    _apply_top_label,
    b4b_front_label_eligibility,
    b4b_front_label_geometry,
)
from ._compose import b4b_body_with_features
from ._validation import validate_b4b_design


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def b4b_summary(box: BoxSpec) -> dict:
    """Numeric + formatted readout for the preview API, generation result and
    logging.  Numeric fields are authoritative; strings are convenience."""
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    cx, cy = b4b_capacity_units(box)
    mx, my = b4b_capacity_mm(box)
    plan = b4b_hardware_plan(box)
    layout = b4b_layout(box)
    case_x, case_y = layout.case_size
    lid_outer = layout.outer_structural_polygon
    min_x, min_y, max_x, max_y = (
        min(layout.case_bounds[0], lid_outer.bounds[0]),
        min(layout.case_bounds[1], lid_outer.bounds[1]),
        max(layout.case_bounds[2], lid_outer.bounds[2]),
        max(layout.case_bounds[3], lid_outer.bounds[3]),
    )
    top_z = (
        b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff) if b4b.lid else eff.z
    )
    if b4b.secure_lid:
        # Measured off the authoritative reinforced envelopes, so the quoted
        # assembled size cannot understate the printed hardware.
        hardware_radius = plan.profile.pivot_radius
        for centres, width in (
            (plan.hinge_centers_x, plan.hinge_root_width),
            (plan.latch_centers_x, plan.latch_root_width),
        ):
            min_x = min(min_x, min(c - width / 2.0 for c in centres))
            max_x = max(max_x, max(c + width / 2.0 for c in centres))
        min_y = min(min_y, plan.pivot_axis_y - hardware_radius)
        max_y = max(max_y, plan.hinge_axis_y + hardware_radius)
        top_z = max(top_z, plan.hinge_axis_z + plan.profile.pivot_radius)
    # The readout has to survive a design the geometry would refuse, because
    # reporting *why* the handle cannot be fitted is most of its job: raising
    # here would leave the UI with no summary at all and therefore nothing to
    # explain itself with.
    handle_ok, handle_why = b4b_handle_eligibility(box)
    handle = b4b_handle_plan(box) if (b4b.handle and handle_ok) else None
    if handle is not None:
        # The bail folds against the front wall, so it costs depth, not height:
        # a handled case still stacks.
        min_y = min(min_y, handle.axis_y - handle.eye_radius)
        min_x = min(min_x, handle.centers_x[0] - handle.root_width / 2.0)
        max_x = max(max_x, handle.centers_x[1] + handle.root_width / 2.0)
    if b4b.stacking:
        top_z += B4B_STACK_RECESS_DEPTH
    summary: dict = {
        "field_mm": [eff.x, eff.y, eff.z],
        "field_units": [round(eff.x / GRID_PITCH), round(eff.y / GRID_PITCH)],
        "outer_mm": [round(case_x, 3), round(case_y, 3), eff.z],
        "case_outer_mm": [round(case_x, 3), round(case_y, 3), eff.z],
        "assembled_envelope_mm": [
            round(max_x - min_x, 3), round(max_y - min_y, 3), round(top_z, 3)
        ],
        "assembled_bounds_mm": [
            round(min_x, 3), round(min_y, 3), round(max_x, 3), round(max_y, 3)
        ],
        "print_objects_mm": b4b_print_object_bounds(box),
        "base_thickened": b4b_grew(box),
        "capacity_units": [cx, cy],
        "capacity_mm": [round(mx, 2), round(my, 2)],
        "max_child_height_mm": round(b4b_max_child_height(box), 2),
        "effective_base_thickness_mm": round(eff.base_thickness, 3),
        "lid": b4b.lid,
        "secure_lid": b4b.secure_lid,
        "lid_headroom_mm": b4b.lid_headroom_mm,
        "stacking": b4b.stacking,
        "handle": handle is not None,
        "handle_requested": b4b.handle,
        "label_location": b4b.label_location if b4b.label_text.strip() else "none",
        "label_text": b4b.label_text,
        "capacity_text": (
            f"Inside capacity: {mx:g} x {my:g} mm - {cx} x {cy} units"
        ),
        "max_child_height_text": f"Maximum bin height: {b4b_max_child_height(box):g} mm",
    }
    if b4b.secure_lid:
        fam = plan.profile.name
        summary["latch_count"] = plan.latch_count_resolved
        summary["hardware_family"] = fam
        summary["hardware"] = {
            "family": fam,
            "hinge_screw": f"{fam}x{plan.hinge_screw_length_mm}",
            "hinge_qty": plan.hinge_count,
            "latch_screw": f"{fam}x{plan.latch_screw_length_mm}",
            "latch_qty": plan.latch_count_resolved,
            "catch_screw": f"{fam}x{plan.catch_screw_length_mm}",
            "catch_qty": plan.latch_count_resolved,
            "nuts": 0,
        }
        summary["hardware_bom"] = plan.screw_bom()
        # Authoritative regression metrics: a bulkier redesign shows up here
        # rather than only in somebody's eye.
        summary["metrics"] = {
            "hinge_projection_mm": round(plan.hinge_projection, 3),
            "hinge_group_width_mm": round(plan.hinge_width, 3),
            "hinge_root_width_mm": round(plan.hinge_root_width, 3),
            "latch_projection_mm": round(plan.latch_projection, 3),
            "latch_root_width_mm": round(plan.latch_root_width, 3),
            "lid_rear_relief_mm": round(plan.lid_rear_relief, 3),
            "head_bearing_margin_mm": round(plan.profile.head_bearing_margin, 3),
        }
    else:
        summary["latch_count"] = 0
        summary["hardware_family"] = plan.profile.name
        summary["hardware"] = {"nuts": 0}
        summary["hardware_bom"] = []
        summary["metrics"] = {}
    if handle is not None:
        fam = handle.profile.name
        summary["hardware"]["handle_screw"] = f"{fam}x{handle.screw_length_mm}"
        summary["hardware"]["handle_qty"] = 2
        summary["metrics"].update({
            "handle_pivot_span_mm": round(handle.pivot_span, 3),
            "handle_clear_grip_mm": round(handle.clear_grip, 3),
            "handle_drop_mm": round(handle.drop, 3),
            "handle_band_mm": round(handle.band, 3),
            "handle_thickness_mm": round(handle.thickness, 3),
            "handle_projection_mm": round(handle.projection, 3),
            "handle_root_width_mm": round(handle.root_width, 3),
            "handle_stop_angle_deg": handle.stop_angle,
        })
        bom = summary["hardware_bom"]
        line = f"2 x {fam}x{handle.screw_length_mm} handle pivots"
        # keep "No nuts" last, as the reassurance it is
        bom.insert(max(0, len(bom) - 1) if bom else 0, line)
        if not bom or bom[-1] != "No nuts":
            bom.append("No nuts")
    summary["handle_available"] = handle_ok
    summary["handle_blocked_reason"] = handle_why
    label_ok, label_why = b4b_front_label_eligibility(box)
    summary["front_label_available"] = label_ok
    summary["front_label_blocked_reason"] = label_why
    return summary


# --------------------------------------------------------------------------- #
# print orientation + generation parts
# --------------------------------------------------------------------------- #
def _print_pose(mesh: trimesh.Trimesh, kind: str) -> trimesh.Trimesh:
    """Assembly-space -> a support-minimising *orientation* only.

    No drop-to-plate and no recentring happen here: that is done once per print
    object in :func:`_pack_print_objects`, so parts that must stay registered
    (the lid and its top inlay) keep their exact relative coordinates.
    """
    m = mesh.copy()
    if kind == "latch":
        # lay the lever on its broad face: the hook profile is extruded along
        # local X, so that axis (not Y) must roll onto the bed's Z.
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (0.0, 1.0, 0.0))
        )
    elif kind == "lid":
        # broad, flat top face on the bed; skirt and hardware build upward
        m.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi, (1.0, 0.0, 0.0))
        )
    elif kind == "handle":
        # Lay the bail on its broad face.  The U outline runs across local Y,
        # so that axis rolls onto the bed's Z, the lower radii become plain 2D
        # outline geometry and only the small round pivot bores stay horizontal.
        # The roll is negative so the
        # wall-facing side lands on the bed and the softened exposed edge
        # finishes upward.
        m.apply_transform(
            trimesh.transformations.rotation_matrix(-math.pi / 2.0, (1.0, 0.0, 0.0))
        )
    elif kind == "label":
        # The plate's readable (-Y) face carries the text pocket and its back
        # is +Y.  Rolling -90 degrees about X sends back (+Y) to -Z (down, on
        # the bed) and the text face to +Z (up), so the label prints flat on
        # its back with the lettering facing upward.
        m.apply_transform(
            trimesh.transformations.rotation_matrix(-math.pi / 2.0, (1.0, 0.0, 0.0))
        )
    return m


def _pack_print_objects(
    objects: list[tuple[str, list[tuple[str, trimesh.Trimesh]]]]
) -> list[tuple[str, list[tuple[str, trimesh.Trimesh]]]]:
    """Lay independent print objects out in a row on the build plane.

    Each object is its own Bambu top-level object.  Its named meshes share one
    rigid transform (the lid + top-label inlay and front-label plate + text
    stay registered).  Objects are packed left to right along +X with
    ``B4B_PRINT_PART_GAP`` between them, each centred on Y=0 and dropped so its
    lowest point sits on z=0.  No two objects overlap.
    """
    packed: list[tuple[str, list[tuple[str, trimesh.Trimesh]]]] = []
    x_cursor = 0.0
    for object_name, parts in objects:
        meshes = [m for _n, m in parts]
        mins = np.min([m.bounds[0] for m in meshes], axis=0)
        maxs = np.max([m.bounds[1] for m in meshes], axis=0)
        offset = (
            x_cursor - float(mins[0]),
            -0.5 * float(mins[1] + maxs[1]),
            -float(mins[2]),
        )
        packed_parts: list[tuple[str, trimesh.Trimesh]] = []
        for name, mesh in parts:
            mesh.apply_translation(offset)
            packed_parts.append((name, mesh))
        packed.append((object_name, packed_parts))
        x_cursor += float(maxs[0] - mins[0]) + B4B_PRINT_PART_GAP
    return packed


def _once(make):
    cache: list = []

    def get():
        if not cache:
            cache.append(make())
        return cache[0]
    return get


# Body and Lid are the only print objects whose real meshes are expensive (tens
# of seconds); their fit bounds come from the same plan numbers the summary uses.
_PLAN_BOUNDED_OBJECTS = frozenset({"Storage Box Body", "Storage Box Lid"})


def _print_object_plan(box: BoxSpec, features=()):
    """The one owner of which top-level print objects exist, their names, the
    pose each is exported in and how to build it.

    Returns ``[(object_name, pose_kind, make)]`` where ``make()`` gives the
    object's ``[(part_name, assembly-space mesh)]``.  Export
    (:func:`b4b_build_print_objects`) and the printer-fit bounds
    (:func:`b4b_print_object_bounds`) both read this list, so the objects
    checked for fit are exactly the objects exported.
    """
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    plan: list = []

    plan.append(("Storage Box Body", "body", lambda: [
        ("Storage Box Body", b4b_body_with_features(box, features=features))]))

    if b4b.lid:
        def lid_parts():
            lid = make_b4b_lid(box)
            top_inlay = None
            if b4b.label_location == "top" and b4b.label_text.strip():
                lid, top_inlay = _apply_top_label(box, lid)
            parts = [("Storage Box Lid", lid)]
            if top_inlay is not None:
                parts.append(("Storage Box Top Label", top_inlay))
            return parts
        plan.append(("Storage Box Lid", "lid", lid_parts))

    if b4b_handle_plan(box) is not None:
        plan.append(("Storage Box Handle", "handle", lambda: [
            ("Storage Box Handle", make_b4b_handle(box))]))

    if b4b.secure_lid:
        levers = _once(lambda: make_b4b_latches(box))
        for i in range(len(levers())):
            name = f"Storage Box Latch {i + 1}"
            plan.append((name, "latch", lambda i=i, name=name: [(name, levers()[i])]))

    if b4b.stacking:
        pegs = _once(lambda: _stack_pegs(box))
        for i in range(len(pegs())):
            name = f"Storage Box Stacking Peg {i + 1}"
            plan.append((name, "peg", lambda i=i, name=name: [(name, pegs()[i])]))

    if b4b.label_location == "front" and b4b.label_text.strip():
        def label_parts():
            _frame, plate, text, centre = b4b_front_label_geometry(box)
            # Rotated together so the plate and its lettering stay registered:
            # printed flat on its back, text facing up.
            return [("Storage Box Front Label Plate", translated(plate, centre)),
                    ("Storage Box Front Label Text", translated(text, centre))]
        plan.append(("Storage Box Front Label", "label", label_parts))
    return plan


def b4b_print_object_bounds(box: BoxSpec) -> list[dict]:
    """Print-pose ``[x, y, z]`` bounds of every object export would emit.

    Handle, latches, pegs and the front label are measured on their real
    meshes in their real :func:`_print_pose` (all cheap).  Body and Lid use
    plan-derived bounds that never understate the real meshes, because
    building them costs tens of seconds.  Rotating a pose about Z or X by 180
    degrees keeps extents, so assembly-space plan numbers are print-pose
    numbers for those two.
    """
    eff = b4b_effective_box(box)
    b4b = eff.b4b
    layout = b4b_layout(box)
    lid_outer = layout.outer_structural_polygon
    min_x, min_y, max_x, max_y = (
        min(layout.case_bounds[0], lid_outer.bounds[0]), min(layout.case_bounds[1], lid_outer.bounds[1]),
        max(layout.case_bounds[2], lid_outer.bounds[2]), max(layout.case_bounds[3], lid_outer.bounds[3]),
    )
    underside = b4b_lid_underside_z(box)
    body_z = underside if b4b.lid else eff.z
    lid_top = underside + b4b_lid_skin_from_eff(eff)
    if b4b.secure_lid:
        hw = b4b_hardware_plan(box)
        for centres, width in ((hw.hinge_centers_x, hw.hinge_root_width),
                               (hw.latch_centers_x, hw.latch_root_width)):
            min_x = min(min_x, min(c - width / 2.0 for c in centres))
            max_x = max(max_x, max(c + width / 2.0 for c in centres))
        min_y = min(min_y, hw.pivot_axis_y - hw.profile.pivot_radius)
        max_y = max(max_y, hw.hinge_axis_y + hw.profile.pivot_radius)
        hinge_top = hw.hinge_axis_z + hw.profile.pivot_radius
        body_z = max(body_z, hinge_top)
        lid_top = max(lid_top, hinge_top)
    lid_xy = [max_x - min_x, max_y - min_y]
    # The body also carries the bail's pivot forks, which reach one pivot
    # radius past the pivot axis.
    handle = b4b_handle_plan(box)
    body_min_x, body_max_x, body_min_y = min_x, max_x, min_y
    if handle is not None:
        body_min_y = min(body_min_y, handle.axis_y - handle.profile.pivot_radius)
        body_min_x = min(body_min_x, handle.centers_x[0] - handle.root_width / 2.0)
        body_max_x = max(body_max_x, handle.centers_x[1] + handle.root_width / 2.0)
    body_xy = [body_max_x - body_min_x, max_y - body_min_y]
    rows = []
    for name, kind, make in _print_object_plan(box):
        if name == "Storage Box Body":
            bounds = [*body_xy, body_z]
        elif name == "Storage Box Lid":
            lap = _skirt_lap(eff)
            lid_z = lid_top - underside + (lap if lap >= B4B_LID_SKIRT_MIN_LAP else 0.0)
            if b4b.secure_lid:
                # The hinge knuckles and latch ears hang a full pivot diameter.
                lid_z = max(lid_z, 2.0 * hw.profile.pivot_radius)
            bounds = [*lid_xy, lid_z]
        else:
            try:
                meshes = [_print_pose(mesh, kind) for _part, mesh in make()]
            except ValueError:
                # A design the geometry refuses (the summary must still render,
                # and export will say why): that object has no fit to report.
                continue
            low = np.min([m.bounds[0] for m in meshes], axis=0)
            high = np.max([m.bounds[1] for m in meshes], axis=0)
            bounds = [float(v) for v in high - low]
        rows.append({"name": name, "bounds_mm": [round(float(v), 3) for v in bounds]})
    return rows


def b4b_build_print_objects(
    box: BoxSpec,
    features=(),
) -> list[tuple[str, list[tuple[str, trimesh.Trimesh]]]]:
    """Storage Box top-level print objects, named, oriented and packed on the bed.

    Multi-part objects retain their required registration: the lid and its
    flush top-label inlay, or the front-label plate and text.  Every other
    object has one independently movable mesh.  Screws are never emitted.
    Which objects exist comes from :func:`_print_object_plan`.
    """
    validate_b4b_design(
        box,
        layout_feature_kinds=tuple(one.kind for one in features),
        deep=True,
    )
    objects = [
        (object_name, [(part, _print_pose(mesh, kind)) for part, mesh in make()])
        for object_name, kind, make in _print_object_plan(box, features)
    ]
    return _pack_print_objects(objects)


def b4b_build_parts(box: BoxSpec, features=()) -> list[tuple[str, trimesh.Trimesh]]:
    """Compatibility view of :func:`b4b_build_print_objects` as flat parts."""
    return [
        part
        for _object_name, parts in b4b_build_print_objects(box, features=features)
        for part in parts
    ]
