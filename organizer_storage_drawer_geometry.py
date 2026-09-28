"""Physical Storage Drawers cabinet, using one field and rail datum."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import Polygon, box as shape_box

from organizer_b4b import (B4B_STACK_RECESS_DEPTH, B4B_MIN_FLOOR_SKIN,
                           B4B_STACK_SOCKET_DEPTH, B4B_STACK_SOCKET_MIN_SKIN,
                           B4B_STACK_BOSS_DIAMETER, B4B_STACK_FEMALE_RADIAL_CLEARANCE,
                           B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION)
from organizer_engine import BASE_UNIT, wavy_rect_cavity, text_outline
from organizer_geometry import _extrude_polygon, difference, translated, union
from organizer_lid_handle import resolve_lid_handle
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import normalise_storage_drawers_definition, storage_drawers_unit_counts

SD_JOINT_CLEARANCE_MM = 0.20
SD_JOINT_LAND_MIN_MM = 4.0
SD_REAR_CROSS_MIN_WIDTH_MM = 14.0
SD_FRONT_SHOULDER_MM = 1.6
SD_RAIL_LEDGE_MM = 2.4
SD_RAIL_CAPTURE_MM = 1.6
SD_RAIL_LEADIN_MM = 3.0
SD_STOP_LIFT_DEG = 7.5
SD_TOP_DETENT_COUNT = 2


@dataclass(frozen=True)
class StorageDrawerComponent:
    key: str
    display_name: str
    mesh: trimesh.Trimesh | None
    object_groups: tuple | None
    bounds_xyz: tuple[float, float, float]
    allowed_orientations: tuple[str, ...]


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
    side: float
    drawer_wall: float
    drawer_base: float
    fit: float
    rail_ledge: float
    front: float
    front_projection: float
    rear: float
    outer_x: float
    outer_y: float
    base: float
    top: float
    pitches: tuple[float, ...]
    floors: tuple[float, ...]
    outer_z: float
    frame: float


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


def _stop_ramp(x0, x1, y0, y1, z0):
    rise = math.tan(math.radians(SD_STOP_LIFT_DEG)) * (y1-y0)
    wedge = _extrude_polygon(Polygon([(y0,z0), (y1,z0), (y1,z0+rise)]), x1-x0)
    wedge.apply_transform(np.array([[0,0,1,x0],[1,0,0,0],[0,1,0,0],[0,0,0,1]], float))
    return wedge


def _bounds(mesh):
    return tuple(float(v) for v in mesh.extents)


def _label_outline(text, width, height):
    """Use the canonical Wavefinity cap-height outline and minimum readable size."""
    outline = text_outline(text, min(8.0, height * 0.45))
    x0, y0, x1, y1 = outline.bounds
    scale = min(1.0, width / (x1-x0), height / (y1-y0))
    if min(8.0, height * 0.45) * scale < 5.0:
        raise ValueError("Label needs more room; shorten the text or enlarge the cabinet")
    from shapely import affinity
    return affinity.scale(outline, xfact=scale, yfact=scale, origin="center")


def _lettering(text, width, height, depth, *, vertical=False):
    outline = _label_outline(text, width, height)
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
    side = max(block["cabinet_wall_mm"], SD_JOINT_LAND_MIN_MM)
    fit = block["drawer_fit_mm"]
    drawer_wall = block["drawer_wall_mm"]
    runner = SD_RAIL_LEDGE_MM + SD_RAIL_CAPTURE_MM
    x = space["x"]
    y = space["y"]
    # Each outside dimension is derived once, including rail and moving-face fit.
    outer_x = x + 2 * (drawer_wall + runner + fit + side)
    front = -(drawer_wall + SD_FRONT_SHOULDER_MM)
    rear = y + drawer_wall + fit + side
    projection = max((_handle(block, x, row["height_mm"], i)[0].bounds[1][2]
                      for i, row in enumerate(block["drawers"], 1) if block["drawer_handles"]), default=0.0)
    outer_y = rear - front + projection
    base = max(block["cabinet_base_mm"], B4B_STACK_RECESS_DEPTH + B4B_MIN_FLOOR_SKIN) if block["stacking"] else block["cabinet_base_mm"]
    top = max(block["cabinet_top_mm"], B4B_STACK_SOCKET_DEPTH + B4B_STACK_SOCKET_MIN_SKIN) if block["stacking"] else block["cabinet_top_mm"]
    reveal = SD_RAIL_CAPTURE_MM + fit
    pitches = tuple(row["height_mm"] + block["drawer_base_mm"] + reveal for row in block["drawers"])
    # Descriptor order is top to bottom; physical floor positions ascend upward.
    floors = []
    cursor = base
    for pitch in reversed(pitches):
        floors.append(cursor + block["drawer_base_mm"])
        cursor += pitch
    floors.reverse()
    frame = max(block["open_frame_width_mm"], side + runner + fit)
    return _Datum(x, y, side, drawer_wall, block["drawer_base_mm"], fit,
                  SD_RAIL_LEDGE_MM, front, projection, rear, outer_x, outer_y, base, top,
                  pitches, tuple(floors), base + sum(pitches) + top, frame)


def _handle(block, width, height, ordinal):
    if not block["drawer_handles"]:
        return None, ""
    sizes = ("large", "medium", "small") if block["drawer_handle_size"] == "auto" else (block["drawer_handle_size"],)
    for size in sizes:
        try:
            # Reuse the proven pull profile, rotated from lid top onto fascia.
            pull = resolve_lid_handle((-width/2+5, -height/2+5, width/2-5, height/2-5), "pull", size, "middle")
            depth = float(pull.extents[2])
            if depth + 8 > height:
                raise ValueError("Pull and label space cannot fit")
            return pull, size
        except ValueError:
            continue
    raise ValueError(f"Drawer {ordinal}: Pull does not fit; choose a smaller handle or taller drawer")


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
    if block["unit_label_enabled"]:
        _label_outline(block["unit_label_text"], datum.outer_x-2*datum.side-8,
                       datum.outer_y-2*datum.side-8)

    def add(key, name, bounds, make, orientations=("flat", "bed_90")):
        pieces.append((key, name, bounds, make, orientations))

    # Base/top use longitudinal female tracks. Male panel tongues slide rear/front.
    def plate(z0, thickness, top=False):
        solid = _box(0, datum.front, z0, datum.outer_x, datum.rear, z0+thickness)
        cutters = []
        track_w = SD_JOINT_LAND_MIN_MM + SD_JOINT_CLEARANCE_MM
        for x0 in (SD_JOINT_CLEARANCE_MM, datum.outer_x-track_w-SD_JOINT_CLEARANCE_MM):
            cutters.append(_box(x0, datum.front+SD_FRONT_SHOULDER_MM, z0+(0 if top else thickness/2), x0+track_w, datum.rear, z0+(thickness/2 if top else thickness)))
        if not top:
            rear_t = block["cabinet_wall_mm"]
            cutters.append(_box(datum.side-SD_JOINT_CLEARANCE_MM,
                                datum.rear-rear_t-SD_JOINT_CLEARANCE_MM, z0+thickness/2,
                                datum.outer_x-datum.side+SD_JOINT_CLEARANCE_MM,
                                datum.rear+SD_JOINT_CLEARANCE_MM, z0+thickness))
        if block["stacking"]:
            inset_x = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_x)
            inset_y = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_y)
            radius = B4B_STACK_BOSS_DIAMETER/2 + B4B_STACK_FEMALE_RADIAL_CLEARANCE
            depth = B4B_STACK_SOCKET_DEPTH if top else B4B_STACK_RECESS_DEPTH
            for x in (inset_x, datum.outer_x-inset_x):
                for y in (datum.front+inset_y, datum.rear-inset_y):
                    cut = trimesh.creation.cylinder(radius=radius, height=depth+0.2, sections=48)
                    cut.apply_translation((x, y, z0+thickness-depth/2+0.1 if top else z0+depth/2-0.1))
                    cutters.append(cut)
        label_group = ()
        if top and block["unit_label_enabled"]:
            label = _lettering(block["unit_label_text"], datum.outer_x-2*datum.side-8,
                               datum.outer_y-2*datum.side-8, min(0.5, thickness/3))
            label.apply_translation((datum.outer_x/2, (datum.front+datum.rear)/2, z0+thickness-min(0.5, thickness/3)))
            cutters.append(label)
            label_group = (("Unit label", label),)
        return difference([solid, *cutters]), label_group
    add("cabinet_base", "Cabinet Base", (datum.outer_x, datum.outer_y, datum.base), lambda: plate(0, datum.base))
    add("cabinet_top", "Cabinet Top", (datum.outer_x, datum.outer_y, datum.top), lambda: plate(datum.outer_z-datum.top, datum.top, True))

    # Sides contain rail ledges, capture lips, rear keyways and two front detents.
    for left in (True, False):
        key = ("side_" if block["cabinet_style"] == "full" else "frame_") + ("left" if left else "right")
        name = ("Left" if left else "Right") + (" Side" if block["cabinet_style"] == "full" else " Frame")
        def side_mesh(left=left):
            x0 = 0 if left else datum.outer_x-datum.side
            bars = []
            if block["cabinet_style"] == "full":
                bars.append(_box(x0, datum.front, datum.base/2, x0+datum.side, datum.rear, datum.outer_z-datum.top/2))
            else:
                for y0, y1 in ((datum.front, datum.front+datum.frame), (datum.rear-datum.frame, datum.rear)):
                    bars.append(_box(x0, y0, datum.base/2, x0+datum.side, y1, datum.outer_z-datum.top/2))
                for floor in datum.floors:
                    bars.append(_box(x0, datum.front, floor-SD_RAIL_LEDGE_MM-datum.fit, x0+datum.side, datum.rear, floor+datum.frame/2))
            inner = x0+datum.side if left else x0
            for floor in datum.floors:
                a, b = (inner-0.2, inner+datum.rail_ledge) if left else (inner-datum.rail_ledge, inner+0.2)
                bars.append(_box(a, datum.front+SD_RAIL_LEADIN_MM, floor-SD_RAIL_LEDGE_MM-datum.fit, b, datum.rear-datum.side, floor-datum.fit))
                # Capture lip and rear lift-release stop use the same fit gap.
                bars.append(_box(a, datum.front+SD_RAIL_LEADIN_MM, floor+SD_RAIL_CAPTURE_MM+datum.fit, b, datum.rear-datum.side, floor+2*SD_RAIL_CAPTURE_MM+datum.fit))
                bars.append(_stop_ramp(a, b, datum.rear-datum.side-10.0,
                                       datum.rear-datum.side,
                                       floor+2*SD_RAIL_CAPTURE_MM+datum.fit-0.2))
            tongue_x = x0+(datum.side-SD_JOINT_LAND_MIN_MM)/2
            bars.append(_box(tongue_x, datum.front+SD_FRONT_SHOULDER_MM, datum.base/2, tongue_x+SD_JOINT_LAND_MIN_MM, datum.rear-datum.side, datum.base))
            bars.append(_box(tongue_x, datum.front, datum.outer_z-datum.top-0.2, tongue_x+SD_JOINT_LAND_MIN_MM, datum.rear-SD_FRONT_SHOULDER_MM, datum.outer_z-datum.top/2))
            # Cantilever catches are integral and accessible from front with top drawer removed.
            bars.append(_box(inner-0.4 if left else inner-1.2, datum.front+datum.frame/2, datum.outer_z-datum.top-SD_RAIL_CAPTURE_MM, inner+1.2 if left else inner+0.4, datum.front+datum.frame, datum.outer_z-datum.top/2))
            solid = union(bars)
            # A half-depth rear keyway accepts the vertically dropped rear panel.
            slot_x0 = inner-datum.side/2 if left else inner
            slot_x1 = inner if left else inner+datum.side/2
            slot = _box(slot_x0, datum.rear-block["cabinet_wall_mm"]-SD_JOINT_CLEARANCE_MM,
                        datum.base+SD_JOINT_LAND_MIN_MM, slot_x1,
                        datum.rear+SD_JOINT_CLEARANCE_MM,
                        datum.outer_z-datum.top-SD_JOINT_LAND_MIN_MM)
            return difference([solid, slot])
        add(key, name, (datum.side+datum.rail_ledge, datum.outer_y, datum.outer_z), side_mesh,
            ("side_x", "side_y"))

    # Rear is entirely behind the closed drawer clearance datum.
    rear_t = block["cabinet_wall_mm"]
    def rear_keys():
        tabs = []
        for x0 in (datum.side-rear_t/2, datum.outer_x-datum.side-rear_t/2):
            tabs.append(_box(x0, datum.rear-rear_t, datum.base+SD_JOINT_LAND_MIN_MM,
                             x0+rear_t, datum.rear, datum.outer_z-datum.top-SD_JOINT_LAND_MIN_MM))
        tabs.append(_box(datum.side, datum.rear-rear_t, datum.base/2,
                         datum.outer_x-datum.side, datum.rear, datum.base+SD_JOINT_LAND_MIN_MM))
        return tabs
    if block["rear_support"] == "solid":
        def rear_mesh():
            panel = _box(datum.side, datum.rear-rear_t, datum.base,
                         datum.outer_x-datum.side, datum.rear, datum.outer_z-datum.top)
            return union([panel, *rear_keys()])
        add("rear_solid", "Rear Solid Back", (datum.outer_x-2*datum.side, rear_t, datum.outer_z-datum.base-datum.top), rear_mesh, ("side_y",))
    else:
        def rear_mesh():
            width = max(SD_REAR_CROSS_MIN_WIDTH_MM, SD_JOINT_LAND_MIN_MM)
            # Two crossing diagonal bands as one printable component.
            from shapely.geometry import LineString
            lo, hi = datum.side, datum.outer_x-datum.side
            zlo, zhi = datum.base, datum.outer_z-datum.top
            a = LineString([(lo, zlo), (hi, zhi)]).buffer(width/2, cap_style=2)
            b = LineString([(lo, zhi), (hi, zlo)]).buffer(width/2, cap_style=2)
            poly = a.union(b).intersection(shape_box(lo, zlo, hi, zhi))
            mesh = _extrude_polygon(poly, rear_t)
            mesh.apply_transform(np.array([[1,0,0,0],[0,0,1,datum.rear-rear_t],[0,1,0,0],[0,0,0,1]], float))
            mesh.invert()
            return union([mesh, *rear_keys()])
        add("rear_cross", "Rear Cross Brace", (datum.outer_x-2*datum.side, rear_t, datum.outer_z-datum.base-datum.top), rear_mesh, ("side_y",))

    # A drawer's promised floor is the interior reference plane. Base grows down.
    for ordinal, (row, floor, pitch) in enumerate(zip(block["drawers"], datum.floors, datum.pitches), 1):
        height = row["height_mm"]
        pull, handle_size = _handle(block, datum.field_x, height, ordinal)
        if block["drawer_labels_enabled"] and row["label_text"] and height < (20 if pull else 10):
            raise ValueError(f"Drawer {ordinal}: label and Pull need a taller drawer")
        if block["drawer_labels_enabled"] and row["label_text"]:
            try:
                _label_outline(row["label_text"], datum.field_x-12,
                               max(5.0, height * (0.35 if pull else 0.6)))
            except ValueError as error:
                raise ValueError(f"Drawer {ordinal}: {error}") from error
        def drawer_mesh(row=row, floor=floor, height=height, pull=pull):
            x0 = (datum.outer_x-datum.field_x)/2
            y0 = 0
            outer = _box(x0-datum.drawer_wall, y0-datum.drawer_wall, floor-datum.drawer_base,
                         x0+datum.field_x+datum.drawer_wall, y0+datum.field_y+datum.drawer_wall, floor+height)
            # The interior uses the same mating wave outline as ordinary bin surfaces.
            cavity = wavy_rect_cavity(datum.field_x/2, datum.field_y/2, 0.0, wall=0.0)
            cut = _extrude_polygon(cavity, height+0.1)
            cut.apply_translation((x0+datum.field_x/2, datum.field_y/2, floor))
            body = difference([outer, cut])
            fascia = _box(datum.side+datum.fit, datum.front, floor-datum.drawer_base,
                          datum.outer_x-datum.side-datum.fit, datum.front+SD_FRONT_SHOULDER_MM+0.2, floor+height)
            runners = []
            for left in (True, False):
                x = x0-datum.drawer_wall if left else x0+datum.field_x+datum.drawer_wall
                a, b = (x-SD_RAIL_LEDGE_MM, x+0.4) if left else (x-0.4, x+SD_RAIL_LEDGE_MM)
                runners.append(_runner(a, b, datum.front+SD_RAIL_LEADIN_MM,
                                       datum.field_y, floor))
            solids = [body, fascia, *runners]
            label_group = ()
            if block["drawer_labels_enabled"] and row["label_text"]:
                raised = block["drawer_label_style"] == "raised"
                text = _lettering(row["label_text"], datum.field_x-12,
                                  max(5.0, height * (0.35 if pull else 0.6)), 0.4, vertical=True)
                text.apply_translation((datum.outer_x/2, datum.front+(0 if raised else 0.4),
                                        floor+height*(0.35 if pull else 0.5)))
                if not raised:
                    fascia = difference([fascia, text])
                    solids[1] = fascia
                label_group = (("Drawer label", text),)
            if pull is not None:
                h = pull.copy()
                # Lid Z becomes forward -Y; former Y becomes fascia height.
                h.apply_transform(np.array([[1,0,0,datum.outer_x/2], [0,0,-1,datum.front], [0,1,0,floor+height-8], [0,0,0,1]], float))
                solids.append(h)
            return union(solids), label_group
        name = f"Drawer {ordinal}"
        add(f"drawer:{row['id']}", name,
            (datum.outer_x-2*datum.side-2*datum.fit,
             datum.field_y+datum.drawer_wall-datum.front+(pull.bounds[1][2] if pull is not None else 0),
             height+datum.drawer_base), drawer_mesh)

    if block["stacking"]:
        inset_x = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_x)
        inset_y = max(B4B_STACK_INSET_MIN, B4B_STACK_INSET_FRACTION * datum.outer_y)
        for i, (x, y) in enumerate(((inset_x,inset_y),(datum.outer_x-inset_x,inset_y),
                                    (inset_x,datum.outer_y-inset_y),(datum.outer_x-inset_x,datum.outer_y-inset_y)), 1):
            def peg_mesh(x=x,y=y):
                peg = trimesh.creation.cylinder(radius=B4B_STACK_BOSS_DIAMETER/2,
                    height=B4B_STACK_RECESS_DEPTH+B4B_STACK_SOCKET_DEPTH, sections=48)
                peg.apply_translation((x,y,(B4B_STACK_RECESS_DEPTH+B4B_STACK_SOCKET_DEPTH)/2))
                return peg
            diameter = B4B_STACK_BOSS_DIAMETER
            add(f"stack_peg:{i}", f"Stack Peg {i}", (diameter,diameter,B4B_STACK_RECESS_DEPTH+B4B_STACK_SOCKET_DEPTH), peg_mesh)
    return pieces, warnings


def resolve_storage_drawers_plan(space: dict, *, build_meshes: bool = True) -> StorageDrawersPlan:
    canonical = normalise_storage_drawers_definition(space)
    datum = _make_datum(canonical)
    definitions, warnings = _datum_components(canonical, datum)
    components = []
    for key, name, bounds, maker, orientations in definitions:
        built = maker() if build_meshes else None
        mesh, groups = built if isinstance(built, tuple) else (built, ())
        actual = trimesh.util.concatenate([mesh, *(part for _label, part in groups)]) if groups else mesh
        components.append(StorageDrawerComponent(key, name, mesh, tuple(groups),
                                                 _bounds(actual) if actual is not None else tuple(float(v) for v in bounds), orientations))
    return StorageDrawersPlan(canonical, (datum.outer_x, datum.outer_y, datum.outer_z),
                              datum.base, datum.top, datum.frame, datum.pitches,
                              tuple(components), tuple(warnings))


def storage_drawers_summary(space: dict, printer_profile: dict | None = None) -> dict:
    plan = resolve_storage_drawers_plan(space, build_meshes=False)
    profile = normalise_printer_profile(printer_profile or {"x_mm":256.0,"y_mm":256.0,"z_mm":256.0})
    fits = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        fits.append({"key": component.key, "name": component.display_name,
                     "bounds_xyz": list(component.bounds_xyz), **fit})
    ux, uy = storage_drawers_unit_counts(plan.space)
    return {"outside_xyz": list(plan.outside_xyz), "field_units": [ux, uy],
            "field_mm": [plan.space["x"], plan.space["y"]],
            "drawer_count": len(plan.drawer_pitches_mm),
            "drawers": [{"id": row["id"], "name": f"Drawer {i}", "height_mm": row["height_mm"], "pitch_mm": plan.drawer_pitches_mm[i-1]}
                        for i, row in enumerate(plan.space["storage_drawers"]["drawers"], 1)],
            "effective_material": {"base_mm": plan.effective_base_mm, "top_mm": plan.effective_top_mm,
                                   "frame_width_mm": plan.resolved_frame_width_mm},
            "components": fits, "fits_printer": all(one["fits"] for one in fits),
            "first_fit_error": next((one["reason"] for one in fits if not one["fits"]), None),
            "warnings": list(plan.warnings)}
