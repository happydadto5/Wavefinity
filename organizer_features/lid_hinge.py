"""Interior filament hinge with a fixed, flush back rail.

A square joint above a buried pivot jams immediately. Instead the fixed rail
has a circular nose concentric with the pin and the plate a matching concave
edge. Lid knuckles connect to the plate underneath this nose. Axial slots in
the rail clear those links and end at the open stop, below its continuous top.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import trimesh
from shapely.geometry import LineString, Point, Polygon, box as shapely_box

from organizer_geometry import (
    _extrude_polygon, _extrude_yz_profile, difference, intersection, union,
)

HINGE_PIN_DIAMETER = 1.75
HINGE_PIN_CLEARANCE = 0.2
HINGE_BORE_RADIUS = HINGE_PIN_DIAMETER / 2.0 + HINGE_PIN_CLEARANCE
HINGE_BARREL_WALL = 0.9
HINGE_BARREL_RADIUS = HINGE_BORE_RADIUS + HINGE_BARREL_WALL
HINGE_SWING_GAP = 0.3
HINGE_AXIAL_GAP = 0.3
HINGE_STACK_CLEARANCE = 0.1
HINGE_STOP_ANGLE = 105.0
HINGE_LINK_THICKNESS = 0.6
HINGE_LINK_SKIN = 0.6
HINGE_EMBED = 0.4
HINGE_KNUCKLE_TARGET = 10.0
HINGE_KNUCKLE_MIN = 3.0
HINGE_END_INSET = 3.0
HINGE_FACE_FLATNESS = 1.0
_SEGMENTS = 48


@dataclass(frozen=True)
class LidHinge:
    axis_y: float
    axis_z: float
    axis_depth: float
    rim: float
    rise: float
    span_half: float
    face_front: float
    face_rear: float
    knuckles: tuple
    plate_back_y: float          # top edge; the actual mating edge is circular
    plug_back_y: float
    open_angle_deg: float
    strip_mm: float
    rail_radius: float
    seat_depth: float


def _back_face(cavity: Polygon, xs: list[float]) -> list[float]:
    """Back face extrema of the actual sampled wall path, including its ends."""
    _, min_y, _, max_y = cavity.bounds
    return [float(LineString([(x, min_y - 1.0), (x, max_y + 1.0)])
                  .intersection(cavity).bounds[3]) for x in xs]


def _circle(y: float, z: float, radius: float) -> Polygon:
    return Point(y, z).buffer(radius, quad_segs=_SEGMENTS)


def hinge_layout(
    cavity: Polygon, rim: float, rise: float, seat_depth: float = 0.0,
    plug_depth: float = 3.0, floor_z: float = 0.0,
) -> LidHinge:
    """Resolve the concentric joint, wave setback and open stop.

    Lower the axis as needed for a printable roof above the barrel clearance.
    For top height H above the axis and opening a, radius > H/cos(a/2)
    ensures plate material outside the nose is above the rail whenever it
    swings behind the axis. This computes the shallowest circular nose for
    that angle, rather than guessing a shelf depth.
    """
    depth = max(0.0, HINGE_BARREL_RADIUS + HINGE_SWING_GAP
                + HINGE_LINK_SKIN - rise + seat_depth)
    height = rise + depth
    radius = max(height / math.cos(math.radians(HINGE_STOP_ANGLE / 2.0)) + 0.1,
                 plug_depth + HINGE_SWING_GAP,
                 HINGE_BARREL_RADIUS + HINGE_LINK_SKIN)
    stop = math.radians(HINGE_STOP_ANGLE - 90.0)
    slot_top = (radius * math.sin(stop)
                + HINGE_LINK_THICKNESS / 2.0 * math.cos(stop))
    if height - seat_depth - slot_top < HINGE_LINK_SKIN:
        # Keep a roof below the stacking seat without raising the closed top.
        minimum = ((HINGE_LINK_SKIN + seat_depth + HINGE_LINK_THICKNESS / 2.0
                    * math.cos(stop) + 0.1 * math.sin(stop))
                   / (1.0 - math.sin(stop) / math.cos(math.radians(HINGE_STOP_ANGLE / 2.0))))
        depth = max(depth, minimum - rise)
        height = rise + depth
        radius = max(radius, height / math.cos(math.radians(HINGE_STOP_ANGLE / 2.0)) + 0.1)

    if rim - depth - radius - HINGE_SWING_GAP - HINGE_LINK_SKIN <= floor_z:
        raise ValueError("this bin is too short for a flip lid - increase height or turn Flip lid off")

    min_x, _, max_x, _ = cavity.bounds
    span = min(max_x, -min_x) - HINGE_END_INSET
    faces: list[float] = []
    while span * 2.0 >= HINGE_KNUCKLE_MIN * 3.0 + 2.0 * HINGE_AXIAL_GAP:
        xs = sorted({-span, span, *(float(x) for x, _ in cavity.exterior.coords
                                    if -span < x < span)})
        faces = _back_face(cavity, xs)
        if max(faces) - min(faces) <= HINGE_FACE_FLATNESS:
            break
        span -= 1.0
        faces = []
    if not faces:
        raise ValueError("this bin is too narrow for a flip lid - widen it or turn Flip lid off")
    front, rear = min(faces), max(faces)
    count = max(3, int((2.0 * span + HINGE_AXIAL_GAP)
                       // (HINGE_KNUCKLE_TARGET + HINGE_AXIAL_GAP)))
    if count % 2 == 0:
        count -= 1
    length = (2.0 * span - (count - 1) * HINGE_AXIAL_GAP) / count
    if length < HINGE_KNUCKLE_MIN:
        raise ValueError("this bin is too narrow for a flip lid - widen it or turn Flip lid off")
    knuckles = tuple((-span + i * (length + HINGE_AXIAL_GAP),
                      -span + i * (length + HINGE_AXIAL_GAP) + length)
                     for i in range(count))
    axis_y = front - HINGE_BARREL_RADIUS - HINGE_SWING_GAP
    top_back = axis_y - math.sqrt((radius + HINGE_SWING_GAP) ** 2 - height ** 2)
    plug_back = axis_y - radius - HINGE_SWING_GAP - HINGE_LINK_SKIN
    return LidHinge(axis_y, rim - depth, depth, rim, rise, span, front, rear,
                    knuckles, top_back, plug_back, HINGE_STOP_ANGLE,
                    front - plug_back, radius, seat_depth)


def _knuckle_solid(profile: Polygon, x0: float, x1: float) -> trimesh.Trimesh:
    solid = _extrude_yz_profile(profile, x1 - x0)
    solid.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    return solid


def plate_hinge_cutter(hinge: LidHinge, half_x: float) -> trimesh.Trimesh:
    """Round the plate edge, removing the whole fixed back strip as well."""
    y, z = hinge.axis_y, hinge.axis_z
    radius = hinge.rail_radius + HINGE_SWING_GAP
    profile = _circle(y, z, radius).union(shapely_box(
        y, z - radius - 1.0, hinge.face_rear + radius + 1.0, z + radius + 1.0,
    ))
    return _knuckle_solid(profile, -half_x - 1.0, half_x + 1.0)


def lid_hinge_parts(hinge: LidHinge) -> list[trimesh.Trimesh]:
    """Barrel -> downward link -> outer quarter-ring -> moving plate.

    Routing the link beneath the nose retains a flush rail top even at lid
    knuckles. No bridge crosses its top skin or the stacking recess floor.
    """
    y, z = hinge.axis_y, hinge.axis_z
    inner = hinge.rail_radius + HINGE_SWING_GAP
    outer = inner + HINGE_LINK_SKIN
    top = hinge.rim + hinge.rise - hinge.seat_depth - HINGE_STACK_CLEARANCE
    ring = _circle(y, z, outer).difference(_circle(y, z, inner)).intersection(
        shapely_box(y - outer - 1.0, z - outer - 1.0, y, top))
    link = shapely_box(y - HINGE_LINK_THICKNESS / 2.0, z - outer,
                       y + HINGE_LINK_THICKNESS / 2.0, z)
    profile = _circle(y, z, HINGE_BARREL_RADIUS).union(link).union(ring).difference(
        _circle(y, z, HINGE_BORE_RADIUS))
    return [_knuckle_solid(profile, x0, x1)
            for i, (x0, x1) in enumerate(hinge.knuckles) if i % 2 == 0]


def body_hinge_parts(
    hinge: LidHinge, cavity: Polygon, outer: Polygon, floor_z: float,
) -> list[trimesh.Trimesh]:
    """Fixed wavy-backed rail, alternating bores, and 105 degree stops.

    Below the rim, clip inside the wall with just an embed for fusion. Above
    it, follow the exact lid outside path. Never cut original wall material.
    The caller cuts the same stacking seat into rail and plate.
    """
    y, z = hinge.axis_y, hinge.axis_z
    radius = hinge.rail_radius
    top = hinge.rim + hinge.rise
    wall_y = outer.bounds[3] + 1.0
    profile = _circle(y, z, radius).union(Polygon([
        (y, z - radius), (wall_y, z - radius - (wall_y - y)),
        (wall_y, top), (y, top),
    ])).intersection(shapely_box(y - radius - 1.0, floor_z, wall_y + 1.0, top))
    rail = _knuckle_solid(profile, outer.bounds[0] - 1.0, outer.bounds[2] + 1.0)
    lower = _extrude_polygon(cavity.buffer(HINGE_EMBED), hinge.rim - floor_z)
    lower.apply_translation((0.0, 0.0, floor_z))
    upper = _extrude_polygon(outer, hinge.rise)
    upper.apply_translation((0.0, 0.0, hinge.rim))
    rail = intersection([rail, union([lower, upper])])

    # Half-plane ceiling: the link meets this face at exactly 105 degrees.
    # The remaining slot has running clearance. The core frees the lid barrel.
    stop = math.radians(hinge.open_angle_deg - 90.0)
    front = y - radius - 1.0
    right = y + HINGE_LINK_THICKNESS / 2.0 + HINGE_SWING_GAP

    def ceiling(at_y: float) -> float:
        return z - (at_y - y) * math.tan(stop) + HINGE_LINK_THICKNESS / (2.0 * math.cos(stop))

    slot = Polygon([(front, z - radius - 1.0), (right, z - radius - 1.0),
                    (right, ceiling(right)), (front, ceiling(front))]).union(
                        _circle(y, z, HINGE_BARREL_RADIUS + HINGE_SWING_GAP))
    cutters = [_knuckle_solid(_circle(y, z, HINGE_BORE_RADIUS),
                              outer.bounds[0] - 1.0, outer.bounds[2] + 1.0)]
    # End slots expose the channel from inside for threading flexible filament.
    # They do not drill either side wall.
    slots = [(outer.bounds[0] - 1.0, -hinge.span_half),
             (hinge.span_half, outer.bounds[2] + 1.0)]
    slots.extend((x0 - HINGE_AXIAL_GAP, x1 + HINGE_AXIAL_GAP)
                 for i, (x0, x1) in enumerate(hinge.knuckles) if i % 2 == 0)
    cutters.extend(_knuckle_solid(slot, x0, x1) for x0, x1 in slots)
    return [difference([rail, *cutters])]
