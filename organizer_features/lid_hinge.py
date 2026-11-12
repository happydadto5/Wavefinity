"""Flip lid: a full-width piano hinge in the bin's back-top corner.

Five or more round barrels (bin at both ends and the middle, lid between, a
bin+lid pair added as the width grows) take turns along one straight axis on a
strand of 1.75 mm filament, in a 2.3 mm bore. Every knuckle stays inside the
bin's own wavy back face and below the lid's top, so the closed bin is no
deeper and no taller, and it still nests against its neighbours. The axis sits
low enough that the lid plate runs unbroken over the swing circle; the lid
gives up only the strip behind the pin and the swing room itself. The pin bore
runs out through one side face, so the filament is pushed in from that end only:
the bore is closed by a ``HINGE_END_CAP`` wall at the other, measured from the
side face where the bore really meets it (a rounded back corner leaves the face
well inside the nominal span). The lid opens to ``HINGE_STOP_ANGLE`` on its
stop; the bin's back top is relieved by the lid plate's swept envelope so
nothing fouls on the way.

Sections are drawn in the hinge's corner frame: ``u`` forward from the back
plane (the deepest trough of the back face over the hinge) and ``v`` down from
the lid top. The axis sits ``half`` (the barrel radius) in from the back plane
and ``axis_v`` down from the top.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import trimesh
from shapely.affinity import rotate, translate
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from organizer_geometry import (
    _extrude_polygon, _extrude_yz_profile, difference, intersection, union,
)

HINGE_PIN_DIAMETER = 1.75
HINGE_BORE_DIAMETER = 2.3         # round bore for the 1.75 mm filament (0.275 mm radial clearance)
HINGE_BORE_RADIUS = HINGE_BORE_DIAMETER / 2.0
HINGE_PIN_CLEARANCE = HINGE_BORE_RADIUS - HINGE_PIN_DIAMETER / 2.0
HINGE_BARREL_RADIUS = 2.0         # fixed: the hinge's outside size does not follow the bore
HINGE_BARREL_WALL = HINGE_BARREL_RADIUS - HINGE_BORE_RADIUS   # 0.85: two 0.4 mm perimeters
HINGE_SWING_GAP = 0.3             # radial running gap round a swinging knuckle
HINGE_AXIAL_GAP = 0.3             # between neighbouring knuckles
HINGE_ROOF = 0.8                  # lid left over the swing circle (two top skins)
HINGE_STOP_ANGLE = 110.0          # the lid rests open here, on a flat stop
HINGE_KNUCKLE_TARGET = 10.0
HINGE_KNUCKLE_MIN = 3.0
HINGE_MIN_KNUCKLES = 5            # bin, lid, bin, lid, bin
HINGE_HALF = HINGE_BARREL_RADIUS  # axis offset from the back plane
_SEGMENTS = 48
HINGE_BEVEL_ANGLE = 45.0          # underside bevel, degrees up from the print plane
HINGE_END_CAP = 2.0               # solid cap closing the bore at the hinge's first end,
                                  # measured from the side face as it really stands there
HINGE_END_CAP_MIN = 1.0           # least cap a narrow first knuckle may leave
HINGE_RELIEF_GAP = 0.2            # clearance left round the lid plate's swept envelope
HINGE_RELIEF_STEP = 2.0           # degrees between the swept plate sections


@dataclass(frozen=True)
class LidHinge:
    axis_y: float
    axis_z: float
    axis_depth: float            # axis below the rim (negative when above it)
    rim: float
    rise: float
    span_half: float
    back_y: float
    top_z: float
    half: float
    axis_v: float
    swing_radius: float
    inner_u: float               # deepest reach of the back wall's inside face
    knuckles: tuple              # (x0, x1); even index = bin, odd index = lid
    plate_back_y: float          # lid plate stays whole in front of this
    plug_back_y: float
    open_angle_deg: float
    strip_mm: float              # how far the hinge reaches past the inside face
    seat_depth: float
    bore_x0: float = 0.0         # where the blind bore starts: end cap past the real side face

    def yz(self, u: float, v: float) -> tuple[float, float]:
        return self.back_y - u, self.top_z - v

    def stop_plane_v(self, u: float) -> float:
        """The plane the lid's back face lies on at the stop angle."""
        a = math.radians(self.open_angle_deg)
        return self.axis_v + (self.half + math.cos(a) * (u - self.half)) / math.sin(a)


def _back_face(cavity: Polygon, xs: list[float]) -> list[float]:
    """Back face extrema of the actual sampled wall path, including its ends."""
    _, min_y, _, max_y = cavity.bounds
    ys = [float(LineString([(x, min_y - 1.0), (x, max_y + 1.0)])
                .intersection(cavity).bounds[3]) for x in xs]
    # A sample beyond a narrower polygon's own width misses it (NaN): skip it.
    return [y for y in ys if math.isfinite(y)]


def hinge_layout(
    cavity: Polygon, rim: float, rise: float, seat_depth: float = 0.0,
    plug_depth: float = 3.0, floor_z: float = 0.0, outer: Polygon | None = None,
) -> LidHinge:
    """Resolve the corner axis, the knuckle run and the plate/plug limits.

    The axis sits one barrel radius in from the back plane, so the barrels are
    tangent to it. It sits low enough that the swing circle (barrel plus
    running gap) leaves ``HINGE_ROOF`` of lid over it; a stacking lid has its
    seat recessed into the top, so there the axis drops by the seat depth as
    well and the recess floor leaves the same roof over the swing circle.
    """
    if outer is None:
        outer = cavity
    r = HINGE_BARREL_RADIUS
    top = rim + rise
    swing = r + HINGE_SWING_GAP
    axis_v = seat_depth + HINGE_ROOF + swing
    min_x, _, max_x, _ = outer.bounds
    xs = list(np.linspace(min_x * 0.9, max_x * 0.9, 721))
    back_y = min(_back_face(outer, xs))
    inner_y = min(_back_face(cavity, xs))
    inner_u = back_y - inner_y
    a = math.radians(HINGE_BEVEL_ANGLE)
    # The bevel roots lowest where the wall's inside face is shallowest.
    near_u = max(0.0, back_y - max(_back_face(cavity, xs)))
    reach = (axis_v + r * math.cos(a)
             + max(0.0, r + r * math.sin(a) - near_u) * math.tan(a))
    if top - reach - 1.0 <= floor_z or rim - (axis_v + swing - rise) <= floor_z + 1.0:
        raise ValueError("This bin is too short for a Hinged lid — make it taller, or set Lid to No lid.")

    total = max_x - min_x
    # Anchored on five (bin at both ends and the middle, lid between); a
    # bin+lid pair joins as the width grows, keeping knuckles near the target.
    pairs = int(math.floor(((total + HINGE_AXIAL_GAP)
                            / (HINGE_KNUCKLE_TARGET + HINGE_AXIAL_GAP) - 1.0) / 2.0 + 0.5))
    count = max(HINGE_MIN_KNUCKLES, 2 * pairs + 1)
    length = (total - (count - 1) * HINGE_AXIAL_GAP) / count
    while length < HINGE_KNUCKLE_MIN and count > HINGE_MIN_KNUCKLES:
        count -= 2
        length = (total - (count - 1) * HINGE_AXIAL_GAP) / count
    if length < HINGE_KNUCKLE_MIN:
        raise ValueError("This bin is too narrow for a Hinged lid — make it wider, or set Lid to No lid.")
    knuckles = tuple((min_x + i * (length + HINGE_AXIAL_GAP),
                      min_x + i * (length + HINGE_AXIAL_GAP) + length)
                     for i in range(count))
    axis_y = back_y - r
    axis_z = top - axis_v
    # The side face the bore meets is not at ``min_x``: the back corner is
    # rounded, so at the axis the face stands well inside the span.  Take the
    # face at its most inward across the bore's height and put the cap past it.
    bore_ys = np.linspace(axis_y - HINGE_BORE_RADIUS, axis_y + HINGE_BORE_RADIUS, 9)
    face_x = _side_face_x(outer, [float(y) for y in bore_ys], min_x)
    bore_x0 = face_x + HINGE_END_CAP
    first_end = knuckles[0][1]
    if bore_x0 > first_end - 0.4:
        bore_x0 = first_end - 0.4      # stay inside the first bin knuckle
    if bore_x0 - face_x < HINGE_END_CAP_MIN:
        raise ValueError("This bin is too narrow for a Hinged lid — make it wider, or set Lid to No lid.")
    return LidHinge(
        axis_y=axis_y, axis_z=axis_z, axis_depth=rim - axis_z, rim=rim, rise=rise,
        span_half=total / 2.0, back_y=back_y, top_z=top, half=r, axis_v=axis_v,
        swing_radius=swing, inner_u=inner_u, knuckles=knuckles,
        plate_back_y=back_y - (r + swing),
        plug_back_y=back_y - (2.0 * r + HINGE_SWING_GAP),
        open_angle_deg=HINGE_STOP_ANGLE,
        strip_mm=max(0.0, 2.0 * r - inner_u), seat_depth=seat_depth,
        bore_x0=bore_x0,
    )


def _side_face_x(outer: Polygon, ys: list[float], default: float) -> float:
    """The first-end side face at its most inward over the heights ``ys``."""
    min_x, _, max_x, _ = outer.bounds
    faces = []
    for y in ys:
        hit = LineString([(min_x - 1.0, y), (max_x + 1.0, y)]).intersection(outer)
        if not hit.is_empty:
            faces.append(float(hit.bounds[0]))
    return max(faces) if faces else default


# --------------------------------------------------------------------------- #
# sections
# --------------------------------------------------------------------------- #
def _uv(h: LidHinge, pts) -> Polygon:
    return orient(Polygon([h.yz(u, v) for u, v in pts]), 1.0)


def _barrel(h: LidHinge, radius: float | None = None) -> Polygon:
    """The round barrel about the axis (or a circle of ``radius`` about it)."""
    r = h.half if radius is None else radius
    return Point(h.axis_y, h.axis_z).buffer(r, quad_segs=_SEGMENTS)


def _swing(h: LidHinge) -> Polygon:
    return _barrel(h, h.swing_radius)


def _bevel_tangent(h: LidHinge) -> tuple[float, float]:
    """Where the bevel leaves the barrel's front underside."""
    a = math.radians(HINGE_BEVEL_ANGLE)
    return h.half + h.half * math.sin(a), h.axis_v + h.half * math.cos(a)


def _bin_knuckle_section(h: LidHinge) -> Polygon:
    """The barrel on a bevel that leaves the back wall below the hinge.

    The bevel runs tangent to the barrel's front underside and falls back at
    ``HINGE_BEVEL_ANGLE`` off the print plane until it meets the wall's inside
    run, wherever that run lies, so every downward-facing surface is steeper
    than or equal to 45 degrees and the knuckle prints upright without support. Behind the
    wall the section fills back to the wavy outside face (the caller clips to
    that face), so nothing but the wall itself sits under the bevel."""
    r, va = h.half, h.axis_v
    tu, tv = _bevel_tangent(h)
    foot = (-1.5, tv + (tu + 1.5) * math.tan(math.radians(HINGE_BEVEL_ANGLE)))
    bevel = _uv(h, [(r, va), (tu, tv), foot, (-1.5, va)])
    return _barrel(h).union(bevel)


def _lid_knuckle_section(h: LidHinge) -> Polygon:
    """The barrel plus a square heel from the axis up to the lid top, clipped
    at the lid top plane so the top is one flat face flush with the lid top.
    The heel's back face is the lid's stop face; it lies a barrel radius behind
    the axis, so at the stop angle it is tangent to the barrel's circle."""
    heel = _uv(h, [(0.0, 0.0), (h.half, 0.0), (h.half, h.axis_v), (0.0, h.axis_v)])
    below_top = _uv(h, [(-5.0, 0.0), (8.0 * h.half, 0.0),
                        (8.0 * h.half, 8.0 * h.half + h.axis_v), (-5.0, 8.0 * h.half + h.axis_v)])
    return _barrel(h).union(heel).intersection(below_top)


def _bin_cut_section(h: LidHinge) -> Polygon:
    """What a lid knuckle needs cleared from the bin: its swing circle, the
    heel's path behind the pin down to the stop plane, and the wall top in
    front of the pin down to the bottom of the swing circle (no feather edge)."""
    r = h.half
    behind = _uv(h, [(-5.0, -5.0), (r, -5.0), (r, h.stop_plane_v(r)),
                     (-5.0, h.stop_plane_v(-5.0))])
    cut = _swing(h).union(behind)
    reach = h.inner_u + 0.5
    if reach > r + 0.05:
        cut = cut.union(_uv(h, [(r, -5.0), (reach, -5.0),
                                (reach, h.axis_v + h.swing_radius),
                                (r, h.axis_v + h.swing_radius)]))
    return cut


def _stop_section(h: LidHinge) -> Polygon:
    """The ledge the lid heel lands on at the stop angle: top face on the stop
    plane, underside rising forward at 45 degrees out of the wall."""
    r = h.half
    v_front = h.stop_plane_v(r)
    ledge = _uv(h, [(-1.5, h.stop_plane_v(-1.5)), (r, v_front), (r, v_front + 1.0),
                    (-1.5, v_front + 1.0 + r + 1.5)])
    return ledge.difference(_swing(h))


def _relief_section(h: LidHinge) -> Polygon:
    """What the bin gives up behind the pin, over each bin knuckle, so the lid
    plate can swing to the stop.

    Over a bin knuckle the plate keeps its full thickness just outside the
    swing circle, and that edge sweeps back through the wall's top and the
    wavy back face as the lid opens.  The envelope is the plate (from the
    swing circle outward, a few millimetres is all that can reach the bin)
    turned about the axis from closed to ``open_angle_deg``, grown by
    ``HINGE_RELIEF_GAP`` and kept to the part behind the pin.  It never comes
    nearer the axis than the swing circle less the gap, so the barrel stays."""
    plate = box(0.0, h.axis_v - h.rise, 6.0, h.axis_v).difference(
        Point(0.0, 0.0).buffer(h.swing_radius, quad_segs=16))
    steps = int(math.ceil(h.open_angle_deg / HINGE_RELIEF_STEP))
    angles = [min(h.open_angle_deg, i * HINGE_RELIEF_STEP) for i in range(steps + 1)]
    swept = unary_union([rotate(plate, a, origin=(0.0, 0.0)) for a in angles])
    swept = swept.buffer(HINGE_RELIEF_GAP, quad_segs=8)
    behind = box(-20.0, -20.0, 0.0, 20.0)
    swept = swept.intersection(behind)
    if swept.is_empty:
        return Polygon()
    # (p, q) -> (u, v): forward of the axis, up from the axis.
    polys = [swept] if isinstance(swept, Polygon) else list(swept.geoms)
    return unary_union([
        _uv(h, [(h.half + p, h.axis_v - q) for p, q in poly.exterior.coords[:-1]])
        for poly in polys if isinstance(poly, Polygon) and not poly.is_empty
    ])


def _lid_notch_section(h: LidHinge) -> Polygon:
    """What the lid gives up over each bin knuckle: the swing circle and the
    strip behind the pin. The lid plate stays whole over the circle (the axis
    is set so ``HINGE_ROOF`` of it is left), so no thin lip is cut."""
    return _swing(h).union(_behind_section(h))


def _behind_section(h: LidHinge) -> Polygon:
    r = h.half
    return _uv(h, [(-5.0, -5.0), (r, -5.0), (r, 8.0 * r), (-5.0, 8.0 * r)])


def _x_prism(section: Polygon, x0: float, x1: float) -> trimesh.Trimesh:
    # Drop the near-duplicate points a circle/polygon union leaves behind;
    # they make the extrusion non-manifold.
    section = orient(section.simplify(1e-3).buffer(0), 1.0)
    solid = _extrude_yz_profile(section, x1 - x0)
    solid.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    return solid


def _keeper(h: LidHinge, outer: Polygon) -> trimesh.Trimesh:
    """Nothing may stand outside the bin's own wavy outline or above the top."""
    depth = h.axis_v + 4.0 * h.half + 4.0
    keep = _extrude_polygon(outer, depth)
    keep.apply_translation((0.0, 0.0, h.top_z - depth))
    return keep


def _bore(h: LidHinge) -> trimesh.Trimesh:
    """Straight bore, blind at the first end behind a ``HINGE_END_CAP`` wall
    (measured from the real side face) and open at the other side face for
    the filament."""
    x0, x1 = h.bore_x0, h.span_half
    bore = _x_prism(Point(h.axis_y, h.axis_z).buffer(HINGE_BORE_RADIUS, quad_segs=32),
                    x0, x1 + 2.0)
    return bore


def _bins(h: LidHinge):
    return [k for i, k in enumerate(h.knuckles) if i % 2 == 0]


def _lids(h: LidHinge):
    return [k for i, k in enumerate(h.knuckles) if i % 2 == 1]


# --------------------------------------------------------------------------- #
# parts
# --------------------------------------------------------------------------- #
def plate_hinge_cutter(hinge: LidHinge, half_x: float) -> trimesh.Trimesh:
    """Clear the plate behind the pin all along the hinge, and the swing room
    over every bin knuckle."""
    g = HINGE_AXIAL_GAP / 2.0
    cuts = [_x_prism(_behind_section(hinge), -half_x - 3.0, half_x + 3.0)]
    notch = _lid_notch_section(hinge)
    cuts += [_x_prism(notch, x0 - g, x1 + g) for x0, x1 in _bins(hinge)]
    return union(cuts)


def lid_hinge_parts(hinge: LidHinge, outer: Polygon | None = None) -> list[trimesh.Trimesh]:
    """Lid knuckles (round barrel + stop heel), bored for the pin."""
    section = _lid_knuckle_section(hinge)
    knuckles = union([_x_prism(section, x0, x1) for x0, x1 in _lids(hinge)])
    if outer is not None:
        knuckles = intersection([knuckles, _keeper(hinge, outer)])
    return [difference([knuckles, _bore(hinge)])]


def body_hinge_cutters(hinge: LidHinge) -> list[trimesh.Trimesh]:
    """Cut from the bin: the lid knuckles' running room, the relief the lid
    plate's sweep needs over each bin knuckle, and the pin bore, which is
    capped at its first end and runs out through the other side wall."""
    g = HINGE_AXIAL_GAP / 2.0
    section = _bin_cut_section(hinge)
    cuts = [_x_prism(section, x0 - g, x1 + g) for x0, x1 in _lids(hinge)]
    cuts += _relief_prisms(hinge)
    return [union(cuts), _bore(hinge)]


def _relief_prisms(hinge: LidHinge) -> list[trimesh.Trimesh]:
    """The plate-sweep relief over every bin knuckle (empty when none is needed)."""
    relief = _relief_section(hinge)
    if relief.is_empty:
        return []
    g = HINGE_AXIAL_GAP / 2.0
    return [_x_prism(relief, x0 - g, x1 + g) for x0, x1 in _bins(hinge)]


def body_hinge_parts(
    hinge: LidHinge, cavity: Polygon, outer: Polygon, floor_z: float,
) -> list[trimesh.Trimesh]:
    """Uncut bin knuckles and stops, to join before the body hinge cuts."""
    section = _bin_knuckle_section(hinge)
    # Draw the wall-root overlap before extrusion instead of unioning a
    # translated copy of an already clipped, relieved and bored rail.
    section = section.union(translate(section, yoff=-0.05))
    solids = [_x_prism(section, x0, x1) for x0, x1 in _bins(hinge)]
    stop = _stop_section(hinge)
    if not stop.is_empty:
        stop = stop.union(translate(stop, yoff=-0.05))
        solids += [_x_prism(stop, x0, x1) for x0, x1 in _lids(hinge)]
    parts = intersection([union(solids), _keeper(hinge, outer)])
    # The caller cuts the swing relief and blind bore once in the joined bin.
    return [parts]


# --------------------------------------------------------------------------- #
# Gridfinity envelope assessment (Story 3009)
# --------------------------------------------------------------------------- #
# The per-cell external allowance of a Gridfinity bin: 42 x count - 0.5 on the
# 42 pitch (41.5 for one cell), and the 20.5 mm body of the 21 pitch
# (gridfinity-stage1-spec.md sections 1 and 2). The rest of the pitch is the
# 0.25 mm-per-side gap a neighbouring bin stands in.
GRID_HINGE_ALLOWANCE = {"gridfinity": (42.0, 41.5), "gridfinity_half": (21.0, 20.5)}
GRID_HINGE_LABELS = {"gridfinity": "Gridfinity 42 mm", "gridfinity_half": "Gridfinity half 21 mm"}


@dataclass(frozen=True)
class GridHingeAssessment:
    grid: str
    pitch_mm: float
    allowance_mm: float           # one cell's external width
    gap_mm: float                 # clear room behind the back plane (neighbour gap)
    knuckle_mm: float             # knuckle length the five-knuckle run leaves
    swing_overrun_mm: float       # open-swing reach behind the back plane, at or below the lid top
    supported: bool
    reason: str                   # plain language; why it is, or is not, offered


def _swing_overrun(lid_length: float) -> float:
    """How far behind the back plane the swinging plate reaches at or below the
    lid-top plane, closed to ``HINGE_STOP_ANGLE``.

    Same frame and construction as ``_relief_section``: the axis is the origin,
    the lid top is ``axis_v`` above it, the plate starts at the swing circle and
    runs ``lid_length`` forward, and the back plane lies ``HINGE_HALF`` behind
    the axis. The plate is taken at the thickest lid (1.6 mm), the worst case. Anything
    above the lid-top plane is clear of a neighbour of the same height, so it
    is clipped away here (a neighbour's lid or stack above it is not assessed).
    """
    swing = HINGE_BARREL_RADIUS + HINGE_SWING_GAP
    axis_v = HINGE_ROOF + swing
    plate = box(swing, axis_v - 1.6, swing + lid_length, axis_v)   # thickest lid, 1.6 mm
    steps = int(math.ceil(HINGE_STOP_ANGLE / HINGE_RELIEF_STEP))
    angles = [min(HINGE_STOP_ANGLE, i * HINGE_RELIEF_STEP) for i in range(steps + 1)]
    swept = unary_union([rotate(plate, a, origin=(0.0, 0.0)) for a in angles])
    swept = swept.intersection(box(-1000.0, -1000.0, 1000.0, axis_v))
    if swept.is_empty:
        return 0.0
    return max(0.0, -swept.bounds[0] - HINGE_HALF)


def assess_gridfinity_hinge(grid: str) -> GridHingeAssessment:
    """Whether the filament-pin hinged lid fits one cell of a Gridfinity pitch.

    Nominal geometry only: nothing here is a printed fit. A pitch is supported
    only if the five-knuckle run is long enough and the open swing stays inside
    the neighbour gap; otherwise it is recorded unsupported, never reshaped.
    """
    if grid not in GRID_HINGE_ALLOWANCE:
        raise ValueError(f"{grid!r} is not a Gridfinity grid")
    pitch, allowance = GRID_HINGE_ALLOWANCE[grid]
    gap = (pitch - allowance) / 2.0
    knuckle = (allowance - (HINGE_MIN_KNUCKLES - 1) * HINGE_AXIAL_GAP) / HINGE_MIN_KNUCKLES
    lid_length = allowance - (HINGE_HALF + HINGE_BARREL_RADIUS + HINGE_SWING_GAP)
    overrun = _swing_overrun(lid_length)
    label = GRID_HINGE_LABELS[grid]
    if knuckle < HINGE_KNUCKLE_MIN:
        ok, reason = False, (
            f"A Hinged lid is not available on {label} bins: the {allowance:g} mm bin leaves "
            f"knuckles of {knuckle:.1f} mm, under the {HINGE_KNUCKLE_MIN:g} mm the hinge needs.")
    elif overrun > gap + 1e-9:
        ok, reason = False, (
            f"A Hinged lid is not available on {label} bins: its open swing reaches "
            f"{overrun:.1f} mm behind the {allowance:g} mm bin, and only {gap:g} mm is clear "
            f"before the next bin. Use Lid or Lid for stacking.")
    else:
        ok, reason = True, (
            f"Hinged lid swing stays within the {gap:g} mm gap on {label} (nominal, unverified by a print).")
    return GridHingeAssessment(grid, pitch, allowance, gap, knuckle, overrun, ok, reason)
