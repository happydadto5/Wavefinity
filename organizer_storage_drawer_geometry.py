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
from organizer_geometry import _extrude_polygon, _extrude_yz_profile, _loft_cavity, difference, translated, union
from organizer_inserts import Feature, Zone, text_fitted
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import normalise_storage_drawers_definition, storage_drawers_unit_counts

SD_JOINT_CLEARANCE_MM = 0.20
SD_JOINT_LAND_MIN_MM = 4.0
SD_REAR_CROSS_MIN_WIDTH_MM = 14.0
SD_FRONT_SHOULDER_MM = 1.6
SD_FRONT_REVEAL_MM = 0.6
SD_RAIL_LEDGE_MM = 2.4
SD_RAIL_CAPTURE_MM = 1.6
SD_RAIL_LEADIN_MM = 3.0
# Drawer catch: a low symmetric bump the drawer's rear wing rides over. The wing
# only has to climb SD_CATCH_OVERLAP_MM - less than the smallest fit's vertical
# play - so Tight, Standard and Loose all push in and pull out straight.
SD_CATCH_OVERLAP_MM = 0.25
SD_CATCH_LENGTH_MM = 8.0
SD_TOP_DETENT_COUNT = 2
# A low, ramped bump at the seated end of each top dovetail. The mating
# pocket relieves it only at the seated position; removal is a firm hand slide.
SD_TOP_DETENT_BUMP_MM = 0.4
SD_TOP_DETENT_INTERFERENCE_MM = 0.2
SD_TOP_DETENT_LENGTH_MM = 6.0
SD_REAR_PANEL_INSET_MM = 0.1
# The plate ribs stop short of the side panel's top/bottom face: the panel bar
SD_KEYHOLE_SHANK_MM = 5.2
SD_KEYHOLE_HEAD_MM = 10.0
SD_KEYHOLE_CAPTURE_TRAVEL_MM = 7.0
SD_KEYHOLE_REINFORCEMENT_MM = 4.0
SD_KEYHOLE_EDGE_MARGIN_MM = 4.0
SD_KEYHOLE_ROW_SEPARATION_MM = 16.0
SD_KEYHOLE_DRAWER_CLEARANCE_MM = 0.5
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
    usable_heights_mm: tuple[float, ...]
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
    usable_heights: tuple[float, ...]
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


def _wall_mount_plan(block: dict, datum: _Datum) -> dict | None:
    if block["wall_mounting"] == "off":
        return None
    if block["wall_mounting"] != "keyholes":
        raise ValueError("Wall mounting must be Off or Keyholes")
    count = int(block["wall_mount_keyholes_per_drawer"])
    if count not in (2, 4):
        raise ValueError("Keyholes per drawer level must be 2 or 4")

    rear_lo = datum.track_reach + SD_REAR_PANEL_INSET_MM
    rear_hi = datum.outer_x - datum.track_reach - SD_REAR_PANEL_INSET_MM
    head_r = SD_KEYHOLE_HEAD_MM / 2.0
    shank_r = SD_KEYHOLE_SHANK_MM / 2.0
    left = rear_lo + head_r + SD_KEYHOLE_EDGE_MARGIN_MM
    right = rear_hi - head_r - SD_KEYHOLE_EDGE_MARGIN_MM
    if right - left < SD_KEYHOLE_HEAD_MM + 2.0 * SD_KEYHOLE_EDGE_MARGIN_MM:
        raise ValueError(
            "This cabinet is too narrow for safe wall-mount keyholes. "
            "Increase X size or turn Wall mounting Off."
        )
    if datum.rear - SD_KEYHOLE_REINFORCEMENT_MM < datum.field_y + SD_KEYHOLE_DRAWER_CLEARANCE_MM:
        raise ValueError(
            "Wall-mount reinforcement would enter drawer travel. "
            "Increase cabinet depth or turn Wall mounting Off."
        )

    holes = []
    bridge_rows = []
    for ordinal, (z0, z1) in enumerate(zip(datum.fascia_bottoms, datum.fascia_tops), 1):
        low = z0 + head_r + SD_KEYHOLE_EDGE_MARGIN_MM
        high = z1 - (
            SD_KEYHOLE_CAPTURE_TRAVEL_MM + shank_r + SD_KEYHOLE_EDGE_MARGIN_MM
        )
        if high < low:
            raise ValueError(
                f"Drawer {ordinal} is too short for wall-mount keyholes. "
                "Increase its height or turn Wall mounting Off."
            )
        if count == 2:
            rows = ((low + high) / 2.0,)
        else:
            if high - low < SD_KEYHOLE_ROW_SEPARATION_MM:
                raise ValueError(
                    f"Drawer {ordinal} is too short for 4 keyholes. "
                    "Use 2 keyholes or increase its height."
                )
            rows = (low, high)
        for z in rows:
            bridge_rows.append(z)
            holes.extend(((left, z), (right, z)))
    return {"holes": tuple(holes), "bridge_rows": tuple(bridge_rows)}


def _rear_keyhole_cutter(x: float, z: float, datum: _Datum) -> trimesh.Trimesh:
    y0 = datum.rear - SD_KEYHOLE_REINFORCEMENT_MM - 0.2
    y1 = datum.rear + 0.2
    depth = y1 - y0

    def cylinder(radius: float, centre_z: float) -> trimesh.Trimesh:
        mesh = trimesh.creation.cylinder(radius=radius, height=depth, sections=48)
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, (1, 0, 0)))
        mesh.apply_translation((x, (y0 + y1) / 2.0, centre_z))
        return mesh

    head = cylinder(SD_KEYHOLE_HEAD_MM / 2.0, z)
    slot = _box(
        x - SD_KEYHOLE_SHANK_MM / 2.0, y0, z,
        x + SD_KEYHOLE_SHANK_MM / 2.0, y1,
        z + SD_KEYHOLE_CAPTURE_TRAVEL_MM,
    )
    capture = cylinder(
        SD_KEYHOLE_SHANK_MM / 2.0,
        z + SD_KEYHOLE_CAPTURE_TRAVEL_MM,
    )
    return union([head, slot, capture])


def _wall_mount_reinforcement(
    plan: dict | None, datum: _Datum, *, cross: bool,
) -> list[trimesh.Trimesh]:
    if plan is None:
        return []
    head_r = SD_KEYHOLE_HEAD_MM / 2.0
    shank_r = SD_KEYHOLE_SHANK_MM / 2.0
    rear_lo = datum.track_reach + SD_REAR_PANEL_INSET_MM
    rear_hi = datum.outer_x - datum.track_reach - SD_REAR_PANEL_INSET_MM
    y0 = datum.rear - SD_KEYHOLE_REINFORCEMENT_MM
    pieces = []
    for x, z in plan["holes"]:
        pieces.append(_box(
            x - head_r - SD_KEYHOLE_EDGE_MARGIN_MM, y0,
            z - head_r - SD_KEYHOLE_EDGE_MARGIN_MM,
            x + head_r + SD_KEYHOLE_EDGE_MARGIN_MM, datum.rear,
            z + SD_KEYHOLE_CAPTURE_TRAVEL_MM + shank_r + SD_KEYHOLE_EDGE_MARGIN_MM,
        ))
    if cross:
        half = (SD_KEYHOLE_HEAD_MM + 2.0 * SD_KEYHOLE_EDGE_MARGIN_MM) / 2.0
        for z in sorted(set(plan["bridge_rows"])):
            pieces.append(_box(
                rear_lo, y0, z - half,
                rear_hi, datum.rear,
                z + SD_KEYHOLE_CAPTURE_TRAVEL_MM + shank_r + SD_KEYHOLE_EDGE_MARGIN_MM,
            ))
    return pieces


def _sliding_dovetail(center_x, y0, y1, root_z, direction, land, *, female=False, bed_x=None, left=True):
    """Half dovetail: the outer flank reaches the side panel's print bed."""
    head = land
    neck = 0.70 * head
    length = 0.55 * land
    outer = (center_x-head/2 if left else center_x+head/2) if bed_x is None else bed_x
    inner_neck = center_x+neck/2 if left else center_x-neck/2
    inner_head = center_x+head/2 if left else center_x-head/2
    section = orient(Polygon([
        (outer, root_z), (inner_neck, root_z),
        (inner_head, root_z+direction*length),
        (outer, root_z+direction*length),
    ]), 1.0)
    if female:
        section = section.buffer(SD_JOINT_CLEARANCE_MM, join_style=2)
    else:
        z1 = root_z-direction*0.25
        section = unary_union([section, shape_box(min(outer,inner_neck), min(root_z,z1),
                                                  max(outer,inner_neck), max(root_z,z1))])
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
    fronts = tuple(_front_plan(block, outer_x - 2*panel - 2*SD_FRONT_REVEAL_MM, row, i) for i, row in enumerate(block["drawers"], 1))
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
    lift = max(0.0, rib_top + SD_LOW_RAIL_CLEAR_MM + SD_RAIL_LEDGE_MM + fit)
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
    # Fix 096 B5: physical bin clearance is measured from each flat drawer
    # floor to the underside of the structure above it. The pitch already
    # contains drawer_base + fit, so after removing the structure thickness
    # the real usable height is the requested clear height plus fit.
    usable_heights = tuple(row["height_mm"] + fit for row in block["drawers"])
    # The lower sliding dovetail reaches down to the base plate's top face.
    side_bottom_z = min(base,
                        *(floor-block["drawer_base_mm"]-SD_RAIL_LEDGE_MM-fit for floor in floors))
    lowest_z = min(0.0, side_bottom_z)
    fascia_bottoms = tuple(floor - block["drawer_base_mm"] + SD_FRONT_REVEAL_MM for floor in floors)
    fascia_tops = tuple(floor - block["drawer_base_mm"] + pitch - SD_FRONT_REVEAL_MM for floor, pitch in zip(floors, pitches))
    return _Datum(x, y, panel, joint_land, track_reach, drawer_wall, block["drawer_base_mm"], fit,
                  SD_RAIL_LEDGE_MM, front, projection, rear, body_depth, outer_x, outer_y,
                  base, top, pitches, floors, usable_heights, fascia_bottoms, fascia_tops, fronts,
                  side_bottom_z, lowest_z,
                  base + lift + sum(pitches) + top, frame)


def storage_drawers_usable_heights(space: dict) -> tuple[float, ...]:
    """Physical floor-to-ceiling clearance for each drawer, in descriptor order."""
    canonical = normalise_storage_drawers_definition(space)
    return _make_datum(canonical).usable_heights


def _horizontal_pull(width, height, size):
    """Horizontal ledge with a 45-degree underside in drawer print orientation."""
    span, projection = {"small": (20.0, 4.0), "medium": (32.0, 6.0), "large": (48.0, 8.0)}[size]
    if span + 8.0 > width:
        raise _PullFit("Pull needs a wider fascia")
    if projection + 3.0 > height:
        raise _PullFit("Pull needs a taller fascia")
    profile = Polygon([
        (0.0, -0.2), (0.0, 0.0), (projection, projection),
        (projection+1.0, projection), (projection+1.0, -0.2),
    ])
    # Local Y is fascia height, local Z is forward projection. The production
    # drawer transform below makes the sloped underside rise one mm per mm.
    return _extrude_yz_profile(profile, span)


def _cosmetic_side_shell(cavity, x0, datum, floor, height):
    """Existing mating waves thicken only the cosmetic side wall strips.

    The first/last 8 mm in Y, the runner/catch band and the rim stay straight.
    Matching rings ramp from the existing wall at >=45 degrees. The cavity
    is subtracted afterwards, retaining the exact interior wave and phase.
    """
    z0 = floor + 2*SD_RAIL_CAPTURE_MM + datum.fit
    z1 = floor + height - 2.0
    ramp = 0.8
    if z1-z0 <= 2*ramp or datum.field_y <= 16.0:
        return None
    from shapely.affinity import translate
    profile = translate(cavity.buffer(datum.drawer_wall, join_style=2),
                        xoff=x0+datum.field_x/2, yoff=datum.field_y/2)
    profile = profile.intersection(shape_box(x0-datum.drawer_wall-1.0, 8.0,
                                             x0+datum.field_x+datum.drawer_wall+1.0,
                                             datum.field_y-8.0))
    upper = np.asarray(orient(profile, 1.0).exterior.coords[:-1], float)
    lower = upper.copy()
    lower[:, 0] = np.clip(lower[:, 0], x0-datum.drawer_wall, x0+datum.field_x+datum.drawer_wall)
    # No correspondence is re-sampled: displacement is bounded by the 0.8 mm
    # ramp, and each vertex keeps its Y and the same canonical wave phase.
    if np.max(np.abs(upper-lower)) > ramp:
        raise ValueError("Cosmetic wall ramp exceeds the supported slope")
    return _loft_cavity([lower, upper, upper, lower], [z0, z0+ramp, z1-ramp, z1])


def _front_plan(block, width, row, ordinal):
    height = row["height_mm"] + block["drawer_base_mm"] + block["drawer_fit_mm"] - 2*SD_FRONT_REVEAL_MM
    has_label = block["drawer_labels_enabled"] and bool(row["label_text"])
    handles = block["drawer_handles"]
    choice = block["drawer_handle_size"]
    sizes = ("large", "medium", "small", "scoop", None) if choice == "auto" else (choice,)
    if not handles:
        sizes = (None,)
    pull_failed = label_failed = pull_too_narrow = False
    for size in sizes:
        try:
            try:
                pull = _horizontal_pull(width, height, size) if size not in (None, "scoop") else None
                if size == "scoop" and (width < 20 or height < 4):
                    raise _PullFit("Pull needs a wider fascia")
            except ValueError as error:
                raise _PullFit(str(error)) from error
            if pull is not None:
                pull_bottom = float(pull.bounds[0][1])
                pull_top = float(pull.bounds[1][1])
                pull_z = height - 1.0 - pull_top
                label_top = pull_z + pull_bottom - 1.0
            else:
                pull_z = 0.0
                label_top = height - (4.0 if size == "scoop" else 2.0)
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
    for ordinal, front in enumerate(datum.fronts, 1):
        if block["drawer_handles"] and front.pull_size in ("scoop", ""):
            treatment = "a finger scoop" if front.pull_size == "scoop" else "no pull"
            warnings.append(f"Drawer {ordinal}: Auto uses {treatment}; a horizontal pull needs more face height or width")
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
        root_z = z0-length if top else z0+thickness+length
        direction = 1 if top else -1
        for left in (True, False):
            x0 = 0 if left else datum.outer_x-datum.track_reach
            panel_x0 = 0.0 if left else datum.outer_x-datum.panel
            center = x0+datum.track_reach/2
            ribs.append(_box(x0, datum.front+SD_RAIL_LEADIN_MM if top else datum.front,
                             z0-length+SD_RIB_SEAT_GAP_MM if top else z0+thickness-0.1,
                             x0+datum.track_reach, datum.rear,
                             z0+0.1 if top else z0+thickness+length-SD_RIB_SEAT_GAP_MM))
            y0, y1 = ((datum.front-0.2, datum.rear-SD_FRONT_SHOULDER_MM)
                      if top else (datum.front+SD_FRONT_SHOULDER_MM, datum.rear+0.2))
            cutters.append(_sliding_dovetail(center, y0, y1, root_z,
                                              direction, datum.joint_land, female=True,
                                              bed_x=0.0 if left else datum.outer_x, left=left))
            if top:
                end = datum.rear-SD_FRONT_SHOULDER_MM-2.0
                # A relieved pocket at the seated bump position. The normal
                # dovetail roof gives the bump 0.2 mm push-through interference.
                pocket_top = SD_TOP_DETENT_BUMP_MM + SD_JOINT_CLEARANCE_MM - SD_TOP_DETENT_INTERFERENCE_MM
                bed_x = 0.0 if left else datum.outer_x
                inner_head = center+datum.joint_land/2 if left else center-datum.joint_land/2
                cutters.append(_catch_bump(min(bed_x, inner_head)-SD_JOINT_CLEARANCE_MM,
                                           max(bed_x, inner_head)+SD_JOINT_CLEARANCE_MM,
                                           end-SD_TOP_DETENT_LENGTH_MM-SD_JOINT_CLEARANCE_MM,
                                           end+SD_JOINT_CLEARANCE_MM, z0, pocket_top))
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
        return body, label_group
    rib_height = 0.55 * datum.joint_land - SD_RIB_SEAT_GAP_MM
    add("cabinet_base", "Cabinet Base", (datum.outer_x, datum.body_depth, datum.base+rib_height), lambda: plate(0, datum.base))
    top_depth = datum.top + 0.55 * datum.joint_land
    add("cabinet_top", "Cabinet Top", (datum.outer_x, datum.body_depth, top_depth), lambda: plate(datum.outer_z-datum.top, datum.top, True), flip_up=True)

    # Sides contain rail ledges, capture lips, rear keyways and top detents.
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
                for interior_floor in datum.floors:
                    floor = interior_floor - datum.drawer_base
                    bars.append(_box(panel_x0, datum.front, floor-SD_RAIL_LEDGE_MM-datum.fit,
                                     panel_x0+datum.panel, datum.rear, floor+datum.frame/2))
            inner = x0+datum.track_reach if left else x0
            for interior_floor in datum.floors:
                floor = interior_floor - datum.drawer_base
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
                                 root_x1, stop_y1, floor+0.25-datum.fit))
                # Wing and runner both start on the drawer's print-bed plane.
                # The catch rises only 0.25 mm above it, less than every fit.
                bump_base = floor-datum.fit
                bars.append(_catch_bump(stop_x0, stop_x1, stop_y0, stop_y1, bump_base,
                                        datum.fit+SD_CATCH_OVERLAP_MM))
            center = x0+datum.track_reach/2
            bars.append(_sliding_dovetail(center, datum.front+SD_FRONT_SHOULDER_MM,
                                          datum.rear, base_root, -1, datum.joint_land,
                                          bed_x=0.0 if left else datum.outer_x, left=left))
            bars.append(_sliding_dovetail(center, datum.front+SD_RAIL_LEADIN_MM,
                                          datum.rear-SD_FRONT_SHOULDER_MM,
                                          top_root, 1, datum.joint_land,
                                          bed_x=0.0 if left else datum.outer_x, left=left))
            end = datum.rear-SD_FRONT_SHOULDER_MM-2.0
            bed_x = 0.0 if left else datum.outer_x
            inner_head = center+datum.joint_land/2 if left else center-datum.joint_land/2
            bars.append(_catch_bump(min(bed_x, inner_head), max(bed_x, inner_head),
                                    end-SD_TOP_DETENT_LENGTH_MM, end,
                                    top_root+0.55*datum.joint_land-0.05,
                                    SD_TOP_DETENT_BUMP_MM+0.05))
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
    wall_mount = _wall_mount_plan(block, datum)
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
            body = union([
                panel, *rear_keys(),
                *_wall_mount_reinforcement(wall_mount, datum, cross=False),
            ])
            if wall_mount is not None:
                body = difference([
                    body,
                    *(_rear_keyhole_cutter(x, z, datum) for x, z in wall_mount["holes"]),
                ])
            return body
        add("rear_solid", "Rear Solid Back",
            (datum.outer_x-2*datum.track_reach+rear_t, max(rear_t, SD_KEYHOLE_REINFORCEMENT_MM) if wall_mount else rear_t,
             datum.outer_z-datum.top-datum.base/2), rear_mesh,
            ("broad_xz", "broad_xz_90"), flip_up=True)
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
            body = union([
                mesh, *rear_keys(),
                *_wall_mount_reinforcement(wall_mount, datum, cross=True),
            ])
            if wall_mount is not None:
                body = difference([
                    body,
                    *(_rear_keyhole_cutter(x, z, datum) for x, z in wall_mount["holes"]),
                ])
            return body
        add("rear_cross", "Rear Cross Brace",
            (datum.outer_x-2*datum.track_reach+rear_t, max(rear_t, SD_KEYHOLE_REINFORCEMENT_MM) if wall_mount else rear_t,
             datum.outer_z-datum.top-datum.base/2), rear_mesh,
            ("broad_xz", "broad_xz_90"), flip_up=True)

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
            cosmetic = _cosmetic_side_shell(cavity, x0, datum, floor, height)
            body = difference([union([outer, cosmetic]) if cosmetic is not None else outer, cut])
            fascia_width = datum.outer_x-2*datum.panel-2*SD_FRONT_REVEAL_MM
            # The visible bottom edge has the same 0.6 mm reveal as the other
            # edges. A 45-degree root behind it grows from the drawer bed.
            fascia_profile = Polygon([
                (datum.front+SD_FRONT_REVEAL_MM, floor-datum.drawer_base),
                (datum.front+SD_FRONT_SHOULDER_MM+0.2, floor-datum.drawer_base),
                (datum.front+SD_FRONT_SHOULDER_MM+0.2, fascia_top),
                (datum.front, fascia_top), (datum.front, fascia_bottom),
            ])
            fascia = translated(_extrude_yz_profile(fascia_profile, fascia_width), (datum.outer_x/2, 0, 0))
            if front_plan.pull_size == "scoop":
                scoop = trimesh.creation.cylinder(radius=3.0, height=SD_FRONT_SHOULDER_MM+1.0, sections=32)
                scoop.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, (1,0,0)))
                scoop.apply_translation((datum.outer_x/2, datum.front+SD_FRONT_SHOULDER_MM/2, fascia_top+0.5))
                fascia = difference([fascia, scoop])
            runners = []
            runner_z = floor - datum.drawer_base
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
                                       datum.field_y, runner_z))
                # A narrow upper web ties the support rail to the drawer wall
                # while clearing the guide stop below it.
                wall_overlap = x+0.25 if left else x-0.25
                runners.append(_box(min(main_a, wall_overlap), datum.front+SD_RAIL_LEADIN_MM,
                                    runner_z+1.0, max(main_b, wall_overlap), datum.field_y,
                                    runner_z+SD_RAIL_CAPTURE_MM))
                # The rear wing catches the guide stop; a relief precedes it.
                wing_a, wing_b = (a+0.8, b) if left else (a, b-0.8)
                runners.append(_box(wing_a, datum.field_y-3.0, runner_z,
                                    wing_b, datum.field_y, runner_z+1.0))
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
            (datum.outer_x-2*datum.panel-2*SD_FRONT_REVEAL_MM,
             datum.field_y+datum.drawer_wall-datum.front+front_plan.front_projection,
             height+datum.drawer_base), drawer_mesh)

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
                              datum.usable_heights, tuple(components), tuple(warnings))


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
            "drawers": [{"id": row["id"], "name": f"Drawer {i}",
                         "height_mm": row["height_mm"],
                         "usable_height_mm": plan.usable_heights_mm[i-1],
                         "pitch_mm": plan.drawer_pitches_mm[i-1]}
                        for i, row in enumerate(block["drawers"], 1)],
            "effective_material": {"base_mm": plan.effective_base_mm, "top_mm": plan.effective_top_mm,
                                   "frame_width_mm": plan.resolved_frame_width_mm if block["cabinet_style"] == "open" else None},
            "components": fits, "fits_printer": first_bad is None,
            "first_fit_error": first_bad["reason"] if first_bad else None,
            "first_fit_part": first_bad["name"] if first_bad else None,
            "warnings": list(plan.warnings)}
