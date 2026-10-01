"""Physical Storage Drawers cabinet, using one field and rail datum."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import Polygon, box as shape_box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from organizer_b4b import (B4B_STACK_RECESS_DEPTH, B4B_MIN_FLOOR_SKIN,
                           B4B_STACK_SOCKET_DEPTH, B4B_STACK_SOCKET_MIN_SKIN,
                           B4B_STACK_BOSS_DIAMETER, B4B_STACK_FEMALE_RADIAL_CLEARANCE,
                           B4B_STACK_SOCKET_INTERFERENCE, B4B_STACK_BOSS_CHAMFER,
                           B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION)
from organizer_engine import WAVE_MATING_GAP, wavy_rect_cavity
from organizer_geometry import _extrude_polygon, difference, translated, union
from organizer_inserts import Feature, Zone, text_fitted
from organizer_lid_handle import resolve_lid_handle, handle_keepout, LID_HANDLE_EDGE_MARGIN
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import normalise_storage_drawers_definition, storage_drawers_unit_counts

SD_JOINT_CLEARANCE_MM = 0.20
SD_JOINT_LAND_MIN_MM = 4.0
SD_REAR_CROSS_MIN_WIDTH_MM = 14.0
SD_FRONT_SHOULDER_MM = 1.6
SD_RAIL_LEDGE_MM = 2.4
SD_RAIL_CAPTURE_MM = 1.6
SD_RAIL_LEADIN_MM = 3.0
# Drawer catch: a low symmetric bump the drawer's rear wing rides over. The wing
# only has to climb SD_CATCH_OVERLAP_MM - less than the smallest fit's vertical
# play - so Tight, Standard and Loose all push in and pull out straight.
SD_CATCH_OVERLAP_MM = 0.25
SD_CATCH_LENGTH_MM = 8.0
SD_TOP_DETENT_COUNT = 2
# Top retention: a spring arm on each side with a catch nose, and a lip in the
# Top's channel. The arm is 1.2 mm thick in its bending direction and 16 mm long,
# so the ~0.7 mm release travel stays well inside a safe elastic strain.
SD_DETENT_ARM_OFFSET_MM = 0.1
SD_DETENT_ARM_W_MM = 1.2
SD_DETENT_ARM_L_MM = 16.0
SD_DETENT_ARM_T_MM = 1.0
SD_DETENT_ENGAGE_MM = 0.5
SD_DETENT_NOSE_L_MM = 3.0
SD_DETENT_LIP_L_MM = 2.0
SD_DETENT_LIP_GAP_MM = 0.2
SD_DETENT_CHANNEL_CLEAR_MM = 0.3
SD_DETENT_RIB_WALL_MM = 1.2
SD_REAR_PANEL_INSET_MM = 0.1
# The plate ribs stop short of the side panel's top/bottom face: the panel bar
# stands 0.25 mm past the dovetail root, plus 0.3 mm of clearance.
SD_RIB_SEAT_GAP_MM = 0.55
SD_LOW_RAIL_CLEAR_MM = 0.3


@dataclass(frozen=True)
class StorageDrawerComponent:
    key: str
    display_name: str
    mesh: trimesh.Trimesh | None
    object_groups: tuple | None
    bounds_xyz: tuple[float, float, float]
    allowed_orientations: tuple[str, ...]
    flip_up: bool = False


@dataclass(frozen=True)
class StorageDrawersPlan:
    space: dict
    outside_xyz: tuple[float, float, float]
    effective_base_mm: float
    effective_top_mm: float
    resolved_frame_width_mm: float
    drawer_pitches_mm: tuple[float, ...]
    components: tuple[StorageDrawerComponent, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _Datum:
    field_x: float
    field_y: float
    panel: float
    joint_land: float
    track_reach: float
    drawer_wall: float
    drawer_base: float
    fit: float
    rail_ledge: float
    front: float
    front_projection: float
    rear: float
    body_depth: float
    outer_x: float
    outer_y: float
    base: float
    top: float
    pitches: tuple[float, ...]
    floors: tuple[float, ...]
    fascia_bottoms: tuple[float, ...]
    fascia_tops: tuple[float, ...]
    fronts: tuple[_FrontPlan, ...]
    side_bottom_z: float
    lowest_z: float
    outer_z: float
    frame: float


@dataclass(frozen=True)
class _FrontPlan:
    pull: trimesh.Trimesh | None
    pull_size: str
    pull_center_z: float
    label_outline: object | None
    label_center_z: float
    front_projection: float


def _box(x0, y0, z0, x1, y1, z1):
    mesh = trimesh.creation.box(extents=(x1-x0, y1-y0, z1-z0))
    mesh.apply_translation(((x0+x1)/2, (y0+y1)/2, (z0+z1)/2))
    return mesh


def _runner(x0, x1, y0, y1, z0):
    lead = SD_RAIL_LEADIN_MM
    chamfer = min(0.6, (x1-x0)/4)
    profile = Polygon([(x0+chamfer,y0), (x1-chamfer,y0),
                       (x1,y0+lead), (x1,y1), (x0,y1), (x0,y0+lead)])
    return translated(_extrude_polygon(profile, SD_RAIL_CAPTURE_MM), (0,0,z0))


def _catch_bump(x0, x1, y0, y1, z0, height):
    """A symmetric ridge: gentle slope both ways, so the drawer never has to lift."""
    ridge = orient(Polygon([(y0, z0), (y1, z0), ((y0 + y1) / 2, z0 + height)]), 1.0)
    wedge = _extrude_polygon(ridge, x1 - x0)
    wedge.apply_transform(np.array([[0,0,1,x0],[1,0,0,0],[0,1,0,0],[0,0,0,1]], float))
    return wedge


def _sliding_dovetail(center_x, y0, y1, root_z, direction, land, *, female=False):
    """Local Base Trim proportions; prism axis is the assembly slide (Y)."""
    head = land
    neck = 0.70 * head
    length = 0.55 * land
    section = Polygon([
        (center_x-neck/2, root_z), (center_x+neck/2, root_z),
        (center_x+head/2, root_z+direction*length),
        (center_x-head/2, root_z+direction*length),
    ])
    if female:
        section = section.buffer(SD_JOINT_CLEARANCE_MM, join_style=2)
    else:
        z1 = root_z-direction*0.25
        section = unary_union([section, shape_box(center_x-neck/2, min(root_z,z1),
                                                  center_x+neck/2, max(root_z,z1))])
    solid = _extrude_polygon(section, y1-y0)
    # This swap has determinant -1; trimesh already restores the winding.
    solid.apply_transform(np.array([[1,0,0,0],[0,0,1,y0],[0,1,0,0],[0,0,0,1]], float))
    return solid


def _stack_centres(datum):
    ix = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_x)
    iy = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.body_depth)
    return ((ix, datum.front+iy), (datum.outer_x-ix, datum.front+iy),
            (ix, datum.rear-iy), (datum.outer_x-ix, datum.rear-iy))


def _chamfered_stack_peg():
    radius = B4B_STACK_BOSS_DIAMETER/2
    height = B4B_STACK_RECESS_DEPTH+B4B_STACK_SOCKET_DEPTH
    chamfer = min(B4B_STACK_BOSS_CHAMFER, radius-0.5, height-0.4)
    profile = np.array([[0,0],[radius,0],[radius,height-chamfer],
                        [radius-chamfer,height],[0,height]], float)
    return trimesh.creation.revolve(profile, sections=48)


def _bounds(mesh):
    return tuple(float(v) for v in mesh.extents)


def _fitted_label(text, zone):
    """The ordinary Text feature owns whole-mm cap-height and font fitting."""
    _cap_height, outline = text_fitted(Feature("text", zone, options={"text": text}))
    return outline


def _lettering(outline, depth, *, vertical=False):
    polygons = list(outline.geoms) if hasattr(outline, "geoms") else [outline]
    mesh = trimesh.util.concatenate([_extrude_polygon(one, depth) for one in polygons])
    cx = (mesh.bounds[0][0] + mesh.bounds[1][0]) / 2
    cy = (mesh.bounds[0][1] + mesh.bounds[1][1]) / 2
    mesh.apply_translation((-cx, -cy, 0))
    if vertical:
        mesh.apply_transform(np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]], float))
    return mesh


def _make_datum(space):
    block = space["storage_drawers"]
    panel = block["cabinet_wall_mm"]
    joint_land = max(panel, SD_JOINT_LAND_MIN_MM)
    fit = block["drawer_fit_mm"]
    drawer_wall = block["drawer_wall_mm"]
    runner = SD_RAIL_LEDGE_MM + SD_RAIL_CAPTURE_MM
    x = space["x"]
    y = space["y"]
    # Global X includes local rail/joint lands; broad panels retain selected wall.
    track_reach = joint_land + 2 * 0.8
    outer_x = x + 2 * (drawer_wall + runner + fit + track_reach)
    front = -(drawer_wall + SD_FRONT_SHOULDER_MM)
    rear = y + drawer_wall + fit + track_reach
    body_depth = rear - front
    fronts = tuple(_front_plan(block, x, row, i) for i, row in enumerate(block["drawers"], 1))
    projection = max(one.front_projection for one in fronts)
    outer_y = body_depth + projection
    base = max(block["cabinet_base_mm"], B4B_STACK_RECESS_DEPTH + B4B_MIN_FLOOR_SKIN) if block["stacking"] else block["cabinet_base_mm"]
    top = max(block["cabinet_top_mm"], B4B_STACK_SOCKET_DEPTH + B4B_STACK_SOCKET_MIN_SKIN) if block["stacking"] else block["cabinet_top_mm"]
    # Rail capture is behind the fascia. Only the selected fit is visible.
    pitches = tuple(row["height_mm"] + block["drawer_base_mm"] + fit for row in block["drawers"])
    # Descriptor order is top to bottom; physical floor positions ascend upward.
    floors = []
    # The lowest rail's underside must clear the base plate and its ribs; a thin
    # drawer base would otherwise let the rail dip into them.
    rib_top = 0.55*joint_land - SD_RIB_SEAT_GAP_MM
    lift = max(0.0, rib_top + SD_LOW_RAIL_CLEAR_MM + SD_RAIL_LEDGE_MM + fit - block["drawer_base_mm"])
    cursor = base + lift
    for pitch in reversed(pitches):
        floors.append(cursor + block["drawer_base_mm"])
        cursor += pitch
    floors.reverse()
    # Full derives its internal frame/track support width from structure alone,
    # so a hidden Open selection can never move Full geometry. Only Open lets the
    # selected width promote upward.
    structural_frame = track_reach + runner + fit
    frame = (max(block["open_frame_width_mm"], structural_frame)
             if block["cabinet_style"] == "open" else structural_frame)
    floors = tuple(floors)
    # The lower sliding dovetail reaches down to the base plate's top face.
    side_bottom_z = min(base,
                        *(floor-SD_RAIL_LEDGE_MM-fit for floor in floors))
    lowest_z = min(0.0, side_bottom_z)
    fascia_bottoms = tuple(floor - block["drawer_base_mm"] for floor in floors)
    fascia_tops = tuple(floor + row["height_mm"] for floor, row in zip(floors, block["drawers"]))
    return _Datum(x, y, panel, joint_land, track_reach, drawer_wall, block["drawer_base_mm"], fit,
                  SD_RAIL_LEDGE_MM, front, projection, rear, body_depth, outer_x, outer_y,
                  base, top, pitches, floors, fascia_bottoms, fascia_tops, fronts,
                  side_bottom_z, lowest_z,
                  base + lift + sum(pitches) + top, frame)


def _front_plan(block, width, row, ordinal):
    height = row["height_mm"] + block["drawer_base_mm"]
    has_label = block["drawer_labels_enabled"] and bool(row["label_text"])
    handles = block["drawer_handles"]
    choice = block["drawer_handle_size"]
    sizes = ("large", "medium", "small") if choice == "auto" else (choice,)
    if not handles:
        sizes = (None,)
    pull_failed = label_failed = pull_too_narrow = False
    for size in sizes:
        try:
            try:
                pull = (resolve_lid_handle((-width/2, -height/2, width/2, height/2),
                                           "pull", size, "middle") if size else None)
            except ValueError as error:
                raise _PullFit(str(error)) from error
            if pull is not None:
                kx0, ky0, kx1, ky1 = handle_keepout(pull)
                if kx0 < -width/2 or kx1 > width/2:
                    raise _PullFit("Pull needs a wider fascia")
                pull_z = height - LID_HANDLE_EDGE_MARGIN - ky1
                if pull_z + ky0 < LID_HANDLE_EDGE_MARGIN:
                    raise _PullFit("Pull needs a taller fascia")
                label_top = pull_z + ky0 - 1.0
            else:
                pull_z = 0.0
                label_top = height - 2.0
            label_outline = None
            label_center = 0.0
            if has_label:
                label_bottom = 2.0
                if label_top <= label_bottom:
                    raise _LabelFit("Pull and label need more height")
                try:
                    label_outline = _fitted_label(row["label_text"],
                        Zone(-width/2+4, label_bottom, width/2-4, label_top))
                except ValueError as error:
                    raise _LabelFit(str(error)) from error
                label_center = (label_bottom + label_top) / 2.0
            projection = max(float(pull.bounds[1][2]) if pull is not None else 0.0,
                             0.4 if has_label and block["drawer_label_style"] == "raised" else 0.0)
            return _FrontPlan(pull, size or "", pull_z, label_outline,
                              label_center, projection)
        except _PullFit as error:
            pull_failed = True
            pull_too_narrow = (str(error) == "Pull needs a wider fascia")
        except _LabelFit:
            label_failed = True
    raise ValueError(_front_plan_message(ordinal, choice, handles, pull_failed, label_failed, has_label, pull_too_narrow))


class _PullFit(ValueError):
    """The chosen pull cannot fit this fascia."""


class _LabelFit(ValueError):
    """The drawer label cannot fit beside the pull."""


def _front_plan_message(ordinal, choice, handles, pull_failed, label_failed, has_label, pull_too_narrow):
    """Direct guidance that matches the actual settings - never suggests Auto
    when Auto is already selected, and blames the label only when it contributed."""
    name = f"Drawer {ordinal}"
    if not handles:
        return f"{name}'s label does not fit. Shorten the label or increase its height."
    if label_failed and not pull_failed:
        fixes = ["increase its height", "shorten the label"]
        if choice == "auto":
            fixes.append("turn Handles off")
        else:
            if choice != "small":
                fixes.append("choose a smaller pull or Auto")
            fixes.append("turn Handles off")
        return f"{name}'s pull and label do not both fit. " + _join_fixes(fixes)
    if pull_too_narrow:
        if choice == "auto":
            return f"{name} is too narrow for a pull. Increase its width or turn Handles off."
        fixes = ["increase its width"]
        if choice != "small":
            fixes.append("choose a smaller pull or Auto")
        fixes.append("turn Handles off")
        if label_failed and has_label:
            fixes.insert(1, "shorten the label")
        return f"{name} is too narrow for the {choice} pull. " + _join_fixes(fixes)
    if choice == "auto":
        return f"{name} is too short for a pull. Increase its height or turn Handles off."
    fixes = ["increase its height"]
    if choice != "small":
        fixes.append("choose a smaller pull or Auto")
    fixes.append("turn Handles off")
    if label_failed and has_label:
        fixes.insert(1, "shorten the label")
    return f"{name} is too short for the {choice} pull. " + _join_fixes(fixes)


def _join_fixes(fixes):
    if len(fixes) == 1:
        return fixes[0][0].upper() + fixes[0][1:] + "."
    head = ", ".join(fixes[:-1])
    return head[0].upper() + head[1:] + ", or " + fixes[-1] + "."


def _datum_components(space, datum):
    block = space["storage_drawers"]
    pieces = []
    warnings = []
    if block["cabinet_style"] == "open" and datum.frame > block["open_frame_width_mm"]:
        warnings.append(f"Open frame width promoted to {datum.frame:g} mm for rail and joint strength")
    if datum.base > block["cabinet_base_mm"]:
        warnings.append(f"Cabinet base promoted to {datum.base:g} mm for stacking")
    if datum.top > block["cabinet_top_mm"]:
        warnings.append(f"Cabinet top promoted to {datum.top:g} mm for stacking")
    unit_outline = None
    if block["unit_label_enabled"]:
        margin_x = datum.track_reach + 4.0
        margin_y = 4.0
        if block["stacking"]:
            ix = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_x)
            iy = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.body_depth)
            socket_clear = B4B_STACK_BOSS_DIAMETER/2 + B4B_STACK_FEMALE_RADIAL_CLEARANCE + 2.0
            margin_x = max(margin_x, ix + socket_clear)
            margin_y = max(margin_y, iy + socket_clear)
        unit_outline = _fitted_label(block["unit_label_text"],
            Zone(-datum.outer_x/2+margin_x, -datum.body_depth/2+margin_y,
                 datum.outer_x/2-margin_x, datum.body_depth/2-margin_y))

    def add(key, name, bounds, make, orientations=("flat", "bed_90"), flip_up=False):
        pieces.append((key, name, bounds, make, orientations, flip_up))

    # Broad plate skin stays selected; local ribs hold the sliding dovetails.
    def plate(z0, thickness, top=False):
        length = 0.55 * datum.joint_land
        plate_body = _box(0, datum.front, z0, datum.outer_x, datum.rear, z0+thickness)
        ribs = []
        cutters = []
        lips = []
        root_z = z0-length if top else z0+thickness+length
        direction = 1 if top else -1
        for left in (True, False):
            x0 = 0 if left else datum.outer_x-datum.track_reach
            panel_x0 = 0.0 if left else datum.outer_x-datum.panel
            center = x0+datum.track_reach/2
            ribs.append(_box(x0, datum.front,
                             z0-length+SD_RIB_SEAT_GAP_MM if top else z0+thickness-0.1,
                             x0+datum.track_reach, datum.rear,
                             z0+0.1 if top else z0+thickness+length-SD_RIB_SEAT_GAP_MM))
            y0, y1 = ((datum.front-0.2, datum.rear-SD_FRONT_SHOULDER_MM)
                      if top else (datum.front+SD_FRONT_SHOULDER_MM, datum.rear+0.2))
            cutters.append(_sliding_dovetail(center, y0, y1, root_z,
                                              direction, datum.joint_land, female=True))
            if top:
                inner = datum.track_reach if left else datum.outer_x-datum.track_reach
                sign = 1 if left else -1
                def xr(a, b):
                    return sorted((inner+sign*a, inner+sign*b))
                fy0 = datum.front+datum.frame/2
                fy1 = fy0+SD_DETENT_ARM_L_MM
                arm_out = SD_DETENT_ARM_OFFSET_MM+SD_DETENT_ARM_W_MM
                wall_d = arm_out+SD_DETENT_ENGAGE_MM+SD_DETENT_CHANNEL_CLEAR_MM
                # Reinforcing rib beside the channel: full-height walls, 1.2 mm
                # thick, joined to the plate above. It stops short of the rear
                # panel, and the channel below is cut clear of it entirely.
                px0, px1 = xr(-0.2, wall_d+SD_DETENT_RIB_WALL_MM)
                ribs.append(_box(px0, fy0+2.2, root_z-0.6,
                                 px1, fy1+0.5, root_z+2.4))
                # The channel opens through the Top's front edge, so the whole
                # arm, its root and the catch nose travel in clear space
                # from first contact to final seating - never through the rib.
                cx0, cx1 = sorted((panel_x0-0.2 if left else panel_x0+datum.panel+0.2,
                                    inner+sign*wall_d))
                cutters.append(_box(cx0, datum.front-0.2, root_z+0.2,
                                    cx1, fy1+0.2, root_z+0.4+SD_DETENT_ARM_T_MM+0.2))
                # The nose's flat face rides just behind this lip once seated.
                nose_y0 = fy1-SD_DETENT_NOSE_L_MM
                lip_y1 = nose_y0-SD_DETENT_LIP_GAP_MM
                lx0, lx1 = xr(arm_out+SD_DETENT_LIP_GAP_MM, wall_d+0.2)
                lips.append(_box(lx0, lip_y1-SD_DETENT_LIP_L_MM, root_z+0.1,
                                 lx1, lip_y1, root_z+0.5+SD_DETENT_ARM_T_MM+0.1))
        if not top:
            rear_t = block["cabinet_wall_mm"]
            cutters.append(_box(datum.track_reach-SD_JOINT_CLEARANCE_MM,
                                datum.rear-rear_t-SD_JOINT_CLEARANCE_MM, z0+thickness/2,
                                datum.outer_x-datum.track_reach+SD_JOINT_CLEARANCE_MM,
                                datum.rear+SD_JOINT_CLEARANCE_MM, z0+thickness))
        if block["stacking"]:
            radius = B4B_STACK_BOSS_DIAMETER/2 + (B4B_STACK_FEMALE_RADIAL_CLEARANCE if not top else -B4B_STACK_SOCKET_INTERFERENCE)
            depth = B4B_STACK_SOCKET_DEPTH if top else B4B_STACK_RECESS_DEPTH
            for x, y in _stack_centres(datum):
                cut = trimesh.creation.cylinder(radius=radius, height=depth+0.2, sections=48)
                cut.apply_translation((x, y, z0+thickness-depth/2+0.1 if top else z0+depth/2-0.1))
                cutters.append(cut)
        label_group = ()
        if top and unit_outline is not None:
            label = _lettering(unit_outline, min(0.5, thickness/3))
            label.apply_translation((datum.outer_x/2, (datum.front+datum.rear)/2, z0+thickness-min(0.5, thickness/3)))
            cutters.append(label)
            label_group = (("Unit label", label),)
        body = difference([union([plate_body, *ribs]), *cutters])
        if lips:
            body = union([body, *lips])
        return body, label_group
    rib_height = 0.55 * datum.joint_land - SD_RIB_SEAT_GAP_MM
    add("cabinet_base", "Cabinet Base", (datum.outer_x, datum.body_depth, datum.base+rib_height), lambda: plate(0, datum.base))
    # The Top's arm-channel reinforcing rib hangs 0.6 mm lower than its track ribs.
    top_depth = datum.top + 0.55 * datum.joint_land + 0.6
    add("cabinet_top", "Cabinet Top", (datum.outer_x, datum.body_depth, top_depth), lambda: plate(datum.outer_z-datum.top, datum.top, True), flip_up=True)

    # Sides contain rail ledges, capture lips, rear keyways and two front detents.
    for left in (True, False):
        key = ("side_" if block["cabinet_style"] == "full" else "frame_") + ("left" if left else "right")
        name = ("Left" if left else "Right") + (" Side" if block["cabinet_style"] == "full" else " Frame")
        def side_mesh(left=left):
            x0 = 0 if left else datum.outer_x-datum.track_reach
            panel_x0 = 0 if left else datum.outer_x-datum.panel
            top_root = datum.outer_z-datum.top-0.55*datum.joint_land
            base_root = datum.base+0.55*datum.joint_land
            bars = []
            if block["cabinet_style"] == "full":
                bars.append(_box(panel_x0, datum.front, base_root-0.25,
                                 panel_x0+datum.panel, datum.rear, top_root+0.25))
            else:
                for y0, y1 in ((datum.front, datum.front+datum.frame), (datum.rear-datum.frame, datum.rear)):
                    bars.append(_box(panel_x0, y0, base_root-0.25,
                                     panel_x0+datum.panel, y1, top_root+0.25))
                for floor in datum.floors:
                    bars.append(_box(panel_x0, datum.front, floor-SD_RAIL_LEDGE_MM-datum.fit,
                                     panel_x0+datum.panel, datum.rear, floor+datum.frame/2))
            inner = x0+datum.track_reach if left else x0
            for floor in datum.floors:
                # Bounded reinforcement links the thin broad panel to rail root.
                # The band stops exactly at the rail face (the ledge boxes below
                # overlap it), so the rear panel's edge passes it without contact.
                root_x0, root_x1 = (panel_x0, inner) if left else (inner, panel_x0+datum.panel)
                bars.append(_box(root_x0, datum.front, floor-SD_RAIL_LEDGE_MM-datum.fit,
                                 root_x1, datum.rear, floor+2*SD_RAIL_CAPTURE_MM+datum.fit))
                a, b = (inner-0.2, inner+datum.rail_ledge) if left else (inner-datum.rail_ledge, inner+0.2)
                bars.append(_box(a, datum.front+SD_RAIL_LEADIN_MM, floor-SD_RAIL_LEDGE_MM-datum.fit,
                                 b, datum.rear-datum.track_reach, floor-datum.fit))
                # C-01: closed-position stop. A lug rising from the rear end
                # of the lower rail ledge, in the ledge's own x-footprint
                # (a, b). Its front face is exactly at the drawer runner's
                # rear plane (datum.field_y) at flush, so the drawer cannot
                # travel behind the fascia plane. Its depth is drawer_wall +
                # fit (positive at every material/fit); the runner, web and
                # wing end at that same plane, proving 0.0 mm over-travel for
                # Tight/Standard/Loose and both cabinet styles.
                bars.append(_box(a, datum.field_y,
                                 floor-SD_RAIL_LEDGE_MM-datum.fit,
                                 b, datum.rear-datum.track_reach,
                                 floor+SD_RAIL_CAPTURE_MM))
                bars.append(_box(a, datum.front+SD_RAIL_LEADIN_MM,
                                 floor+SD_RAIL_CAPTURE_MM+datum.fit, b,
                                 datum.rear-datum.track_reach, floor+2*SD_RAIL_CAPTURE_MM+datum.fit))
                field_left = (datum.outer_x-datum.field_x)/2
                body_edge = (field_left-datum.drawer_wall if left else
                             field_left+datum.field_x+datum.drawer_wall)
                stop_x0, stop_x1 = ((body_edge-1.4+datum.fit, body_edge-0.2)
                                    if left else (body_edge+0.2, body_edge+1.4-datum.fit))
                stop_y0 = datum.front+SD_RAIL_LEADIN_MM+12.0
                stop_y1 = stop_y0+SD_CATCH_LENGTH_MM
                root_x0, root_x1 = ((inner-0.2, stop_x1) if left else (stop_x0, inner+0.2))
                bars.append(_box(root_x0, stop_y0, floor-SD_RAIL_LEDGE_MM-datum.fit,
                                 root_x1, stop_y1, floor-0.25-datum.fit))
                # The drawer wing's underside is at floor-0.5; the bump peaks only
                # SD_CATCH_OVERLAP_MM above it, and slopes both ways.
                bump_base = floor-0.5-datum.fit
                bars.append(_catch_bump(stop_x0, stop_x1, stop_y0, stop_y1, bump_base,
                                        datum.fit+SD_CATCH_OVERLAP_MM))
            center = x0+datum.track_reach/2
            bars.append(_sliding_dovetail(center, datum.front+SD_FRONT_SHOULDER_MM,
                                          datum.rear, base_root, -1, datum.joint_land))
            bars.append(_sliding_dovetail(center, datum.front,
                                          datum.rear-SD_FRONT_SHOULDER_MM,
                                          top_root, 1, datum.joint_land))
            # Each spring arm has a reinforced root, a long free length and a
            # catch nose: ramp on the rear side, flat catch face on the front side.
            detent_y0 = datum.front+datum.frame/2
            detent_y1 = detent_y0+SD_DETENT_ARM_L_MM
            detent_z = top_root+0.4
            direction = 1 if left else -1
            def fx(distance):
                return inner+direction*distance
            arm_a = SD_DETENT_ARM_OFFSET_MM
            arm_out = arm_a+SD_DETENT_ARM_W_MM
            spans = (panel_x0, panel_x0+datum.panel, fx(-0.6), fx(arm_out))
            bars.append(_box(min(spans), detent_y0, detent_z,
                             max(spans), detent_y0+2.0, detent_z+SD_DETENT_ARM_T_MM))
            bars.append(_box(min(fx(arm_a), fx(arm_out)), detent_y0+1.8, detent_z,
                             max(fx(arm_a), fx(arm_out)), detent_y1, detent_z+SD_DETENT_ARM_T_MM))
            nose_y0 = detent_y1-SD_DETENT_NOSE_L_MM
            nose_profile = orient(Polygon([
                (fx(arm_out-0.2), nose_y0), (fx(arm_out+SD_DETENT_ENGAGE_MM), nose_y0),
                (fx(arm_out+SD_DETENT_ENGAGE_MM), nose_y0+0.4), (fx(arm_out), detent_y1),
                (fx(arm_out-0.2), detent_y1)]), 1.0)
            bars.append(translated(_extrude_polygon(nose_profile, SD_DETENT_ARM_T_MM), (0,0,detent_z)))
            # Rear key land is local to the vertical drop-in groove.
            rear_root_x0, rear_root_x1 = (panel_x0, inner) if left else (inner, panel_x0+datum.panel)
            bars.append(_box(rear_root_x0, datum.rear-datum.frame, base_root,
                             rear_root_x1, datum.rear, top_root))
            solid = union(bars)
            # The drop-in groove is open through the side's top edge: nothing
            # caps it, and the rear panel's body edge sits clear of the land.
            rear_half = block["cabinet_wall_mm"]/2
            slot_x0 = inner-rear_half-SD_JOINT_CLEARANCE_MM
            slot_x1 = inner+rear_half+SD_JOINT_CLEARANCE_MM
            slot = _box(slot_x0, datum.rear-block["cabinet_wall_mm"]-SD_JOINT_CLEARANCE_MM,
                        datum.base+SD_JOINT_LAND_MIN_MM-SD_JOINT_CLEARANCE_MM, slot_x1,
                        datum.rear+SD_JOINT_CLEARANCE_MM,
                        datum.outer_z-datum.top+1.0)
            return difference([solid, slot])
        side_reach = (datum.track_reach + SD_RAIL_CAPTURE_MM + datum.fit
                      + SD_RAIL_LEDGE_MM - 0.2)
        add(key, name, (side_reach, datum.body_depth,
                        datum.outer_z-datum.top-datum.side_bottom_z),
            side_mesh, ("broad_yz", "broad_yz_90"), flip_up=not left)

    # Rear is entirely behind the closed drawer clearance datum.
    rear_t = block["cabinet_wall_mm"]
    # Body edges sit a hair inside the side rail faces; only the tabs enter the grooves.
    rear_lo = datum.track_reach+SD_REAR_PANEL_INSET_MM
    rear_hi = datum.outer_x-datum.track_reach-SD_REAR_PANEL_INSET_MM
    def rear_keys():
        tabs = []
        for x0 in (datum.track_reach-rear_t/2, datum.outer_x-datum.track_reach-rear_t/2):
            tabs.append(_box(x0, datum.rear-rear_t, datum.base+SD_JOINT_LAND_MIN_MM,
                             x0+rear_t, datum.rear, datum.outer_z-datum.top-SD_JOINT_LAND_MIN_MM))
        tabs.append(_box(rear_lo, datum.rear-rear_t, datum.base/2,
                         rear_hi, datum.rear, datum.base+SD_JOINT_LAND_MIN_MM))
        return tabs
    if block["rear_support"] == "solid":
        def rear_mesh():
            panel = _box(rear_lo, datum.rear-rear_t, datum.base,
                         rear_hi, datum.rear, datum.outer_z-datum.top)
            return union([panel, *rear_keys()])
        add("rear_solid", "Rear Solid Back",
            (datum.outer_x-2*datum.track_reach+rear_t, rear_t,
             datum.outer_z-datum.top-datum.base/2), rear_mesh,
            ("broad_xz", "broad_xz_90"))
    else:
        def rear_mesh():
            width = max(SD_REAR_CROSS_MIN_WIDTH_MM, SD_JOINT_LAND_MIN_MM)
            # Two crossing diagonal bands as one printable component.
            from shapely.geometry import LineString
            lo, hi = rear_lo, rear_hi
            zlo, zhi = datum.base, datum.outer_z-datum.top
            a = LineString([(lo, zlo), (hi, zhi)]).buffer(width/2, cap_style=2)
            b = LineString([(lo, zhi), (hi, zlo)]).buffer(width/2, cap_style=2)
            poly = a.union(b).intersection(shape_box(lo, zlo, hi, zhi))
            # The clip repeats the box corners; a doubled vertex leaves the
            # extrusion non-watertight, so the outline is cleaned first.
            poly = poly.simplify(1e-6)
            mesh = _extrude_polygon(poly, rear_t)
            mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,datum.rear-rear_t],[0,1,0,0],[0,0,0,1]], float))
            return union([mesh, *rear_keys()])
        add("rear_cross", "Rear Cross Brace",
            (datum.outer_x-2*datum.track_reach+rear_t, rear_t,
             datum.outer_z-datum.top-datum.base/2), rear_mesh,
            ("broad_xz", "broad_xz_90"))

    # A drawer's promised floor is the interior reference plane. Base grows down.
    for ordinal, (row, floor, pitch, fascia_bottom, fascia_top, front_plan) in enumerate(
        zip(block["drawers"], datum.floors, datum.pitches,
            datum.fascia_bottoms, datum.fascia_tops, datum.fronts), 1):
        height = row["height_mm"]
        def drawer_mesh(row=row, floor=floor, height=height,
                        fascia_bottom=fascia_bottom, fascia_top=fascia_top,
                        front_plan=front_plan):
            x0 = (datum.outer_x-datum.field_x)/2
            y0 = 0
            outer = _box(x0-datum.drawer_wall, y0-datum.drawer_wall, floor-datum.drawer_base,
                         x0+datum.field_x+datum.drawer_wall, y0+datum.field_y+datum.drawer_wall, floor+height)
            # The interior uses the same mating wave outline as ordinary bin surfaces.
            # Nominal wall sits at field/2 + WAVE_MATING_GAP/2, the canonical
            # mating datum shared with Storage Box / base trim: half the
            # 0.25 mm seam gap belongs to the wall side. The outer box and
            # grid-space bin layout are unchanged; its boundary clearance is
            # nested_clearance() (0.2117 mm nominal) rather than half of it.
            cavity = wavy_rect_cavity(datum.field_x/2 + WAVE_MATING_GAP/2,
                                      datum.field_y/2 + WAVE_MATING_GAP/2,
                                      0.0, wall=0.0)
            cut = _extrude_polygon(cavity, height+0.1)
            cut.apply_translation((x0+datum.field_x/2, datum.field_y/2, floor))
            body = difference([outer, cut])
            fascia = _box(datum.track_reach+datum.fit, datum.front, fascia_bottom,
                          datum.outer_x-datum.track_reach-datum.fit,
                          datum.front+SD_FRONT_SHOULDER_MM+0.2, fascia_top)
            runners = []
            for left in (True, False):
                x = x0-datum.drawer_wall if left else x0+datum.field_x+datum.drawer_wall
                a, b = (x-SD_RAIL_LEDGE_MM, x+0.4) if left else (x-0.4, x+SD_RAIL_LEDGE_MM)
                # V-02: the fit setting sets running clearance, never bearing.
                # Uncompensated bearing is 0.8-fit per side (0.20 mm at Loose);
                # extend the runner bar toward the rail so engagement never
                # drops below the proven Standard value of 0.40 mm per side:
                # Tight/Standard/Loose are 0.50/0.40/0.40, with vertical
                # clearances still exactly datum.fit.
                _bearing_makeup = max(0.0, datum.fit - 0.40)
                main_a, main_b = ((a-_bearing_makeup, a+1.0) if left
                                  else (b-1.0, b+_bearing_makeup))
                runners.append(_runner(main_a, main_b, datum.front+SD_RAIL_LEADIN_MM,
                                       datum.field_y, floor))
                # A narrow upper web ties the support rail to the drawer wall
                # while clearing the guide stop below it.
                wall_overlap = x+0.25 if left else x-0.25
                runners.append(_box(min(main_a, wall_overlap), datum.front+SD_RAIL_LEADIN_MM,
                                    floor+1.0, max(main_b, wall_overlap), datum.field_y,
                                    floor+SD_RAIL_CAPTURE_MM))
                # The rear wing catches the guide stop; a relief precedes it.
                wing_a, wing_b = (a+0.8, b) if left else (a, b-0.8)
                runners.append(_box(wing_a, datum.field_y-3.0, floor-0.5,
                                    wing_b, datum.field_y, floor+0.5))
            solids = [body, fascia, *runners]
            label_group = ()
            if front_plan.label_outline is not None:
                raised = block["drawer_label_style"] == "raised"
                text = _lettering(front_plan.label_outline, 0.4, vertical=True)
                text.apply_translation((datum.outer_x/2, datum.front+(0 if raised else 0.4),
                                        fascia_bottom+front_plan.label_center_z))
                if not raised:
                    fascia = difference([fascia, text])
                    solids[1] = fascia
                label_group = (("Drawer label", text),)
            if front_plan.pull is not None:
                h = front_plan.pull.copy()
                # Lid Z becomes forward -Y; former Y becomes fascia height.
                h.apply_transform(np.array([[1,0,0,datum.outer_x/2], [0,0,-1,datum.front],
                                            [0,1,0,fascia_bottom+front_plan.pull_center_z],
                                            [0,0,0,1]], float))
                solids.append(h)
            return union(solids), label_group
        name = f"Drawer {ordinal}"
        add(f"drawer:{row['id']}", name,
            (datum.outer_x-2*datum.track_reach-2*datum.fit,
             datum.field_y+datum.drawer_wall-datum.front+front_plan.front_projection,
             max(height+datum.drawer_base, height+0.5)), drawer_mesh)

    if block["stacking"]:
        for i, (x, y) in enumerate(_stack_centres(datum), 1):
            def peg_mesh(x=x,y=y):
                peg = _chamfered_stack_peg()
                peg.apply_translation((x, y, datum.outer_z-B4B_STACK_SOCKET_DEPTH))
                return peg
            diameter = B4B_STACK_BOSS_DIAMETER
            add(f"stack_peg:{i}", f"Stack Peg {i}", (diameter,diameter,B4B_STACK_RECESS_DEPTH+B4B_STACK_SOCKET_DEPTH), peg_mesh)
    return pieces, warnings


def resolve_storage_drawers_plan(space: dict, *, build_meshes: bool = True) -> StorageDrawersPlan:
    canonical = normalise_storage_drawers_definition(space)
    datum = _make_datum(canonical)
    definitions, warnings = _datum_components(canonical, datum)
    components = []
    for key, name, bounds, maker, orientations, flip_up in definitions:
        built = maker() if build_meshes else None
        mesh, groups = built if isinstance(built, tuple) else (built, ())
        actual = trimesh.util.concatenate([mesh, *(part for _label, part in groups)]) if groups else mesh
        components.append(StorageDrawerComponent(key, name, mesh, tuple(groups),
                                                 _bounds(actual) if actual is not None else tuple(float(v) for v in bounds),
                                                 orientations, flip_up))
    stack_projection = B4B_STACK_RECESS_DEPTH if canonical["storage_drawers"]["stacking"] else 0.0
    return StorageDrawersPlan(canonical, (datum.outer_x, datum.outer_y,
                                         datum.outer_z-datum.lowest_z+stack_projection),
                              datum.base, datum.top, datum.frame, datum.pitches,
                              tuple(components), tuple(warnings))


_FIT_ADVICE = {
    "cabinet_base": "reduce the X or Y size",
    "cabinet_top": "reduce the X or Y size",
    "side": "reduce the Y depth, the number of drawers or their heights",
    "frame": "reduce the Y depth, the number of drawers or their heights",
    "rear": "reduce the X size, the number of drawers or their heights",
    "drawer": "reduce that drawer's X or Y size or its height",
    "stack_peg": "check the printer build volume",
}


def _fit_advice(key: str) -> str:
    for name, text in _FIT_ADVICE.items():
        if key.startswith(name):
            return f"Try to {text}, or change Printer Settings."
    return "Reduce the cabinet size or change Printer Settings."


def _fit_message(name: str, key: str, bounds, profile: dict) -> str:
    size = " × ".join(f"{v:.1f}" for v in bounds)
    bed = f"{profile['x_mm']:g} × {profile['y_mm']:g} × {profile['z_mm']:g}"
    return (f"{name} is {size} mm and does not fit the {bed} mm printer in any orientation. "
            + _fit_advice(key))


def storage_drawers_summary(space: dict, printer_profile: dict | None = None) -> dict:
    plan = resolve_storage_drawers_plan(space, build_meshes=False)
    profile = normalise_printer_profile(printer_profile or {"x_mm":256.0,"y_mm":256.0,"z_mm":256.0})
    fits = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            fit = {**fit, "reason": _fit_message(component.display_name, component.key,
                                                 component.bounds_xyz, profile)}
        fits.append({"key": component.key, "name": component.display_name,
                     "bounds_xyz": list(component.bounds_xyz), **fit})
    ux, uy = storage_drawers_unit_counts(plan.space)
    block = plan.space["storage_drawers"]
    first_bad = next((one for one in fits if not one["fits"]), None)
    return {"outside_xyz": list(plan.outside_xyz), "field_units": [ux, uy],
            "field_mm": [plan.space["x"], plan.space["y"]],
            "drawer_count": len(plan.drawer_pitches_mm),
            "cabinet_style": block["cabinet_style"],
            "printer_mm": [profile["x_mm"], profile["y_mm"], profile["z_mm"]],
            "drawers": [{"id": row["id"], "name": f"Drawer {i}", "height_mm": row["height_mm"], "pitch_mm": plan.drawer_pitches_mm[i-1]}
                        for i, row in enumerate(block["drawers"], 1)],
            "effective_material": {"base_mm": plan.effective_base_mm, "top_mm": plan.effective_top_mm,
                                   "frame_width_mm": plan.resolved_frame_width_mm if block["cabinet_style"] == "open" else None},
            "components": fits, "fits_printer": first_bad is None,
            "first_fit_error": first_bad["reason"] if first_bad else None,
            "first_fit_part": first_bad["name"] if first_bad else None,
            "warnings": list(plan.warnings)}
