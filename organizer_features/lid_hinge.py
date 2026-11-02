"""Flip lid: a back-edge interior hinge pinned with a strand of filament.

One resolver owns every fit answer of the hinge, so the lid plate, the lid plug,
the stacking recess and the bin all read the same numbers instead of guessing
at the form: where the pin axis sits, how far the lid plate stops short of it,
how much interior strip the knuckles take, and where the lid comes to rest.

Section view, ``u`` toward the back wall and ``w`` up from the pin axis::

    lid plate ------------+   +---- lid knuckle (barrel + bridge)
                          |   |
         rim  ============|===|=====+  back wall, top at the rim
                          (pin)     |
              bin knuckle (lower half-barrel on a 45 degree web)

* The pin axis runs along X, in the cavity just in front of the back wall, at
  rim height (a little below it when a stacking recess needs the room).  A
  1.75 mm filament strand is the only non-printed part.
* Knuckles alternate along the axis, lid first and last.  Lid knuckles are full
  barrels hung from a bridge off the lid plate; bin knuckles are lower
  half-barrels on a web that grows out of the wall, every one of them below the
  rim.  Their bores are one straight channel sized for the strand plus
  printable clearance.
* The wall is wavy and only a few tenths of a millimetre thick at the bore's
  radius, so the swing never enters it: the axis is set back from the nearest
  point of the back face by the whole swing envelope.  That setback, plus the
  barrel, is the interior strip the hinge takes - the bin's walls, base and
  outside dimensions are untouched.
* Nothing of the lid extends behind the axis except the barrels, because a
  plate behind a hinge axis would swing down into whatever it rests on.  The
  plate therefore ends ``plate_back_y`` and the knuckles carry the lid's back
  edge; the lid plug stops ``plug_back_y``.  The back wall's own rim stays
  open to the air.
* Opened, the lid swings back until its upper rear corner lands on the bin
  knuckle web: ``open_angle_deg``, past vertical, so it stays open by itself
  and the opening is clear.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.geometry import LineString, Point, Polygon, box as shapely_box

from organizer_geometry import _extrude_polygon, _extrude_yz_profile, intersection, union

# --------------------------------------------------------------------------- #
# the pin and its channel
# --------------------------------------------------------------------------- #
HINGE_PIN_DIAMETER = 1.75        # standard filament, the only non-printed part
HINGE_PIN_CLEARANCE = 0.2        # per side, so the strand turns freely as printed
HINGE_BORE_RADIUS = HINGE_PIN_DIAMETER / 2.0 + HINGE_PIN_CLEARANCE
HINGE_BARREL_WALL = 0.9          # material around the bore (two perimeters)
HINGE_BARREL_RADIUS = HINGE_BORE_RADIUS + HINGE_BARREL_WALL

# --------------------------------------------------------------------------- #
# fits
# --------------------------------------------------------------------------- #
HINGE_SWING_GAP = 0.3            # between anything that turns and anything that does not
HINGE_AXIAL_GAP = 0.3            # between neighbouring knuckles along the pin
HINGE_SEAT_GAP = 0.2             # bin knuckle top, below the rim the lid plate rests at
HINGE_STACK_CLEARANCE = 0.1      # hinge top, below the floor of a stacking recess
HINGE_PIN_END_CLEAR = 0.3        # lid plate edge, clear of the strand's channel
HINGE_STOP_ANGLE = 105.0         # the lid opens at least this far
HINGE_STOP_MARGIN = 0.4          # bin web left under the corner that lands on it
HINGE_BRIDGE_OVERLAP = 0.6       # bridge buried in the lid plate
HINGE_MIN_BRIDGE = 0.6           # thinnest bridge from plate to barrel
HINGE_EMBED = 0.4                # bin web buried in the back wall
HINGE_WEB_REACH = 0.8            # web runs past the rearmost point of the back face

# --------------------------------------------------------------------------- #
# layout along the wall
# --------------------------------------------------------------------------- #
HINGE_KNUCKLE_TARGET = 10.0      # preferred knuckle length
HINGE_KNUCKLE_MIN = 3.0          # shortest knuckle that still holds
HINGE_END_INSET = 3.0            # span stops this far inside the cavity's extent
HINGE_FACE_FLATNESS = 1.0        # a straight wavy run: peak to peak of the wave is 0.8

_SEGMENTS = 24
_SAMPLES_PER_MM = 3         # along the back face: ten per wave cycle


@dataclass(frozen=True)
class LidHinge:
    """Resolved hinge: every y/z is absolute, x runs along the pin."""

    axis_y: float
    axis_z: float
    axis_depth: float            # how far the axis sits below the rim (>= 0)
    rim: float
    rise: float
    span_half: float             # knuckles fill x in [-span_half, +span_half]
    face_front: float            # nearest point of the cavity's back face
    face_rear: float             # farthest point of it, over the span
    knuckles: tuple              # (x0, x1) of each knuckle, even index = lid
    plate_back_y: float          # the lid plate stops here
    plug_back_y: float           # the lid plug stops here
    open_angle_deg: float        # where the opened lid comes to rest
    strip_mm: float              # interior room taken, from the back face forward


def _back_face(cavity: Polygon, xs: np.ndarray) -> list[float]:
    """Y of the cavity's back face at each x (its farthest point there)."""
    _, min_y, _, max_y = cavity.bounds
    faces: list[float] = []
    for x in xs:
        hit = LineString([(float(x), min_y - 1.0), (float(x), max_y + 1.0)]).intersection(cavity)
        if hit.is_empty:
            raise ValueError("this bin is too small for a flip lid hinge")
        faces.append(float(hit.bounds[3]))
    return faces


def _circle(y: float, z: float, radius: float) -> Polygon:
    return Point(y, z).buffer(radius, quad_segs=_SEGMENTS)


def hinge_layout(
    cavity: Polygon, rim: float, rise: float, seat_depth: float = 0.0,
) -> LidHinge:
    """Place the hinge for a bin whose cavity outline is ``cavity``.

    ``rise`` is the lid plate thickness above the rim.  ``seat_depth`` is the
    depth of the stacking recess cut into the lid top (0 for a plain lid): the
    hinge stays below the recess floor so a bin still seats on it.
    """
    barrel = HINGE_BARREL_RADIUS
    top_limit = rise - (seat_depth + HINGE_STACK_CLEARANCE if seat_depth > 0.0 else 0.0)
    depth = max(0.0, barrel - top_limit)            # axis below the rim
    if barrel - depth < HINGE_MIN_BRIDGE:
        raise ValueError("this lid is too thin to carry a hinge - choose a thicker lid")

    min_x, _, max_x, _ = cavity.bounds
    span = min(max_x, -min_x) - HINGE_END_INSET
    faces: list[float] = []
    while span * 2.0 >= HINGE_KNUCKLE_MIN * 3.0 + 2.0 * HINGE_AXIAL_GAP:
        xs = np.linspace(-span, span, max(9, int(span * 2.0 * _SAMPLES_PER_MM) + 1))
        faces = _back_face(cavity, xs)
        if max(faces) - min(faces) <= HINGE_FACE_FLATNESS:
            break
        span -= 1.0
        faces = []
    if not faces:
        raise ValueError(
            "this bin is too narrow for a flip lid hinge - widen it or turn Flip lid off"
        )
    front, rear = min(faces), max(faces)

    # Knuckles alternate lid / bin / lid ... along the pin, lid at both ends.
    length = 2.0 * span
    count = int((length + HINGE_AXIAL_GAP) // (HINGE_KNUCKLE_TARGET + HINGE_AXIAL_GAP))
    if count % 2 == 0:
        count -= 1
    count = max(3, count)
    knuckle = (length - (count - 1) * HINGE_AXIAL_GAP) / count
    if knuckle < HINGE_KNUCKLE_MIN:
        raise ValueError(
            "this bin is too narrow for a flip lid hinge - widen it or turn Flip lid off"
        )
    knuckles = tuple(
        (-span + index * (knuckle + HINGE_AXIAL_GAP),
         -span + index * (knuckle + HINGE_AXIAL_GAP) + knuckle)
        for index in range(count)
    )

    # Where the lid plate ends and where the opened lid lands (all relative to
    # the axis: ``back`` is how far in front of it the plate stops).
    corner = depth + rise                            # plate's upper rear corner
    seat = depth - HINGE_SEAT_GAP                    # bin knuckle top
    stop = math.radians(HINGE_STOP_ANGLE)
    back = max(HINGE_BORE_RADIUS + HINGE_PIN_END_CLEAR,
               (seat - corner * math.cos(stop)) / math.sin(stop))
    open_angle = (math.pi - math.asin(seat / math.hypot(back, corner))
                  - math.atan2(corner, back))
    landing = -back * math.cos(open_angle) + corner * math.sin(open_angle)
    standoff = max(barrel + HINGE_SWING_GAP,
                   landing + HINGE_STOP_MARGIN,
                   math.hypot(back, corner) + HINGE_SWING_GAP)

    axis_y = front - standoff
    return LidHinge(
        axis_y=axis_y,
        axis_z=rim - depth,
        axis_depth=depth,
        rim=rim,
        rise=rise,
        span_half=span,
        face_front=front,
        face_rear=rear,
        knuckles=knuckles,
        plate_back_y=axis_y - back,
        plug_back_y=axis_y - (barrel + HINGE_SWING_GAP),
        open_angle_deg=math.degrees(open_angle),
        strip_mm=standoff + barrel + HINGE_SWING_GAP,
    )


def _knuckle_solid(profile: Polygon, x0: float, x1: float) -> trimesh.Trimesh:
    solid = _extrude_yz_profile(profile, x1 - x0)
    solid.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    return solid


def lid_hinge_parts(hinge: LidHinge) -> list[trimesh.Trimesh]:
    """The lid's knuckles: a full barrel on a bridge off the plate's back edge."""
    y, z = hinge.axis_y, hinge.axis_z
    bridge = shapely_box(
        hinge.plate_back_y - HINGE_BRIDGE_OVERLAP, hinge.rim, y, z + HINGE_BARREL_RADIUS,
    )
    profile = _circle(y, z, HINGE_BARREL_RADIUS).union(bridge).difference(
        _circle(y, z, HINGE_BORE_RADIUS)
    )
    return [_knuckle_solid(profile, x0, x1)
            for index, (x0, x1) in enumerate(hinge.knuckles) if index % 2 == 0]


def body_hinge_parts(
    hinge: LidHinge, cavity: Polygon, floor_z: float,
) -> list[trimesh.Trimesh]:
    """The bin's knuckles: lower half-barrels on a 45 degree web off the wall.

    Everything sits below the rim.  The web is trimmed to the cavity grown by a
    sliver of wall, so it fuses to the wall and can never reach its outside.
    """
    y, z = hinge.axis_y, hinge.axis_z
    top = hinge.rim - HINGE_SEAT_GAP
    wall_y = hinge.face_rear + HINGE_WEB_REACH
    barrel = HINGE_BARREL_RADIUS
    barrel_part = _circle(y, z, barrel).intersection(
        shapely_box(y - barrel - 1.0, z - barrel - 1.0, y + barrel + 1.0, top)
    )
    # The tangent from the barrel's 225 degree point runs at 45 degrees, so the
    # whole underside of knuckle and web prints without support.
    tangent = (y - barrel * math.sqrt(0.5), z - barrel * math.sqrt(0.5))
    ring = [
        tangent,
        (wall_y, tangent[1] - (wall_y - tangent[0])),
        (wall_y, top),
        (y, top),
    ]
    if z < top:
        ring.append((y, z))
    profile = barrel_part.union(Polygon(ring)).difference(_circle(y, z, HINGE_BORE_RADIUS))
    solids = [_knuckle_solid(profile, x0, x1)
              for index, (x0, x1) in enumerate(hinge.knuckles) if index % 2 == 1]
    limit = _extrude_polygon(cavity.buffer(HINGE_EMBED), hinge.rim - floor_z)
    limit.apply_translation((0.0, 0.0, floor_z))
    return [intersection([union(solids) if len(solids) > 1 else solids[0], limit])]
