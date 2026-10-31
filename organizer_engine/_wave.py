"""Wavefinity engine wavy-wall outlines, lock bumps and wall tables."""

from __future__ import annotations

import math
from functools import lru_cache
import numpy as np
import trimesh
from shapely.affinity import translate as translate_polygon
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from organizer_geometry import _sweep_profile, translated

from ._specs import (
    WAVE_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    SAMPLES_PER_MM,
    DEFAULT_WALL,
    DEFAULT_CORNER_FILLET,
    CORNER_INSET,
    CORNER_TIP_RADIUS,
    T_JUNCTION_CLEARANCE,
    LOCK_PROTRUSION,
    LOCK_FLAT,
    LOCK_CHAMFER,
    LOCK_RUN,
    LOCK_SPACING,
    LOCK_CORNER_CLEAR,
    LOCK_TOP_BELOW_RIM,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    LOCK_NOTCH_CLEARANCE,
    BoxSpec,
    max_wave_slope,
    wall_depth_for,
)


def nested_clearance() -> float:
    """Conservative normal clearance from the arc wave's maximum slope.

    ``WAVE_MATING_GAP`` is measured across the seam. The maximum tangent
    slope gives a lower bound on separation, including partial seams.
    """
    return WAVE_MATING_GAP / math.sqrt(1.0 + max_wave_slope() ** 2)


def wave_value(coordinate: float) -> float:
    """Odd, periodic wave made from alternating tangent circular arcs.

    Each half-cycle is a circular segment through zero, its extremum and zero.
    Adjacent segments share a tangent at zero; the radius is fixed by the
    quarter-cycle chord and amplitude. Coordinates use the global grid phase.
    """
    quarter = WAVE_LENGTH / 4.0
    radius = (quarter * quarter + WAVE_AMPLITUDE ** 2) / (2.0 * WAVE_AMPLITUDE)
    phase = coordinate % WAVE_LENGTH
    sign = 1.0 if phase < 2.0 * quarter else -1.0
    local = phase % (2.0 * quarter) - quarter
    return sign * (math.sqrt(max(0.0, radius * radius - local * local))
                   - (radius - WAVE_AMPLITUDE))


def wave_slope(coordinate: float) -> float:
    """Derivative of :func:`wave_value`, from the same arc construction."""
    quarter = WAVE_LENGTH / 4.0
    radius = (quarter * quarter + WAVE_AMPLITUDE ** 2) / (2.0 * WAVE_AMPLITUDE)
    phase = coordinate % WAVE_LENGTH
    sign = 1.0 if phase < 2.0 * quarter else -1.0
    local = phase % (2.0 * quarter) - quarter
    return -sign * local / math.sqrt(max(1e-12, radius * radius - local * local))


def wall_wave_value(coordinate: float, run_axis: str) -> float:
    """Global seam displacement; the signed X/Y pair survives quarter-turns."""
    return wave_value(coordinate) * (-1.0 if run_axis == "x" else 1.0)


def wall_wave_slope(coordinate: float, run_axis: str) -> float:
    return wave_slope(coordinate) * (-1.0 if run_axis == "x" else 1.0)


def wave_cycles(straight_length: float) -> float:
    return straight_length / WAVE_LENGTH


def lock_positions(reach: float) -> list[float]:
    """Centres of the lock bumps on one wall, measured from the wall centre.

    One bump on **every** wave extremum the wall is long enough to carry -
    crests as well as troughs, so every half cycle.  Three reasons:

    * An extremum is where the wall runs parallel to the axis, so the bump
      stands proud by a predictable amount.
    * Because every box centre lands on a multiple of ``WAVE_LENGTH``, these
      positions form a single lattice shared by every box in the drawer,
      whatever the box measures.  Filling the whole lattice is what lets a
      connector engage **both** neighbours wherever it is placed, even when the
      two boxes are different sizes.
    * Filling *every* extremum rather than every other one is what makes the
      connector reversible.  The notches under a connector are then evenly
      spaced about its centre, so it drops on either way round.
    """
    limit = reach - LOCK_RUN / 2.0
    return lock_lattice(-limit, limit)


def lock_lattice(low: float, high: float) -> list[float]:
    """Every lock lattice point between ``low`` and ``high``.

    The lattice is the set of wave extrema: odd multiples of ``WAVE_LENGTH/4``
    from the wall centre, which is every half cycle.  Coordinates are along the
    wall, measured from its midpoint.
    """
    positions: list[float] = []
    index = math.ceil(low / LOCK_SPACING - 0.5 - 1e-9)
    while True:
        offset = (index + 0.5) * LOCK_SPACING
        if offset > high + 1e-9:
            break
        if offset >= low - 1e-9:
            positions.append(round(offset, 6))
        index += 1
    return positions


def _sample_count(span: float) -> int:
    return max(9, int(round(span * SAMPLES_PER_MM)) + 1)


# --------------------------------------------------------------------------- #
# profiles
# --------------------------------------------------------------------------- #
def _wall_points(
    half_x: float,
    half_y: float,
    tangent_x: float,
    tangent_y: float,
    points_per_cycle: float | None = None,
    phase_x: float = 0.0,
    phase_y: float = 0.0,
) -> list[tuple[float, float]]:
    """Counter-clockwise outline: four wavy walls joined by corner chords.

    ``half_*`` place the faces; ``tangent_*`` give the requested wall ends,
    normally from the outer profile. Each run is capped at the innermost
    possible face of its neighbouring walls, so a reduced cavity cannot
    overhang those walls and cross its own corner chords. The surviving
    wall runs keep exactly the same wave and phase. ``points_per_cycle``
    overrides the sampling with a *density* rather than a fixed total, so a
    long wall and a short one on the same box come out equally smooth - the
    preview uses this to get a coarse ring it can draw quickly without a
    fixed point budget starving whichever pair of walls is longer.

    ``phase_x``/``phase_y`` shift the wave sampled on the front/back walls
    (which run along X) and the left/right walls (which run along Y)
    respectively.  A normal, validly grid-sized ``BoxSpec`` always leaves
    these at 0: its own centre is guaranteed to land on the global 3.5 mm wave
    lattice (``GRID_PITCH``/``BASE_UNIT`` are chosen exactly so this holds),
    so evaluating the wave in this shape's own local frame already equals
    the shared global wave. A caller whose real placement centre will NOT be
    on that lattice - a spacer sized to a genuine, non-7-mm-multiple free
    region - passes the centre's own offset from the lattice here instead,
    so the wave this shape shows once actually placed still matches its
    neighbours' along every seam (see ``organizer_drawer.spacer_frame``).
    """
    if points_per_cycle is None:
        count_x = _sample_count(2.0 * tangent_x)
        count_y = _sample_count(2.0 * tangent_y)
    else:
        count_x = max(4, round(points_per_cycle * 2.0 * tangent_x / WAVE_LENGTH))
        count_y = max(4, round(points_per_cycle * 2.0 * tangent_y / WAVE_LENGTH))
    # Keep counts based on the requested tangents: preview outer/cavity rings
    # must still match point for point even when their corner runs differ.
    # The amplitude bound works for every phase, including off-grid spacers.
    # Wall strips and the rectangles containing their corner chords then
    # have disjoint interiors, preventing corner self-intersections.
    tangent_x = min(tangent_x, max(0.0, half_x - WAVE_AMPLITUDE))
    tangent_y = min(tangent_y, max(0.0, half_y - WAVE_AMPLITUDE))
    xs = np.linspace(-tangent_x, tangent_x, count_x)
    ys = np.linspace(-tangent_y, tangent_y, count_y)
    points: list[tuple[float, float]] = []
    points += [(float(s), -half_y + wall_wave_value(float(s) + phase_x, "x")) for s in xs]
    points += [(half_x + wall_wave_value(float(s) + phase_y, "y"), float(s)) for s in ys]
    points += [(float(s), half_y + wall_wave_value(float(s) + phase_x, "x")) for s in xs[::-1]]
    points += [(-half_x + wall_wave_value(float(s) + phase_y, "y"), float(s)) for s in ys[::-1]]
    return points


def _rounded(polygon: Polygon, radius: float) -> Polygon:
    """Round convex corners to ``radius`` without touching the wave.

    A morphological opening rounds any convex corner sharper than ``radius``.
    The wave's own crests are far blunter than that, so they survive untouched.
    """
    if radius <= 0:
        return polygon
    result = polygon.buffer(-radius, join_style=1, quad_segs=32)
    result = result.buffer(radius, join_style=1, quad_segs=32)
    if isinstance(result, MultiPolygon):
        result = max(result.geoms, key=lambda item: item.area)
    if not isinstance(result, Polygon) or not result.is_valid:
        raise RuntimeError("corner rounding did not produce a valid outline")
    return result


# --------------------------------------------------------------------------- #
# clearance-envelope corners (Story 2425)
# --------------------------------------------------------------------------- #
# Each wall run ends CORNER_INSET short of the nominal corner. Continuing both
# runs' own wave functions through the corner gives the farthest tangent-
# continuous reach the neighbours' unchanged walls allow: the continuations are
# the walls themselves, so they keep the seam's offset to every receiving wall.
# They cross near the nominal corner; a fillet tangent to both, at the tip
# radius, rejoins each run exactly. When a fillet cannot fit or a clearance
# fails, the radius grows (the tip sets back) and the fit repeats.
_CORNER_SIGNS = ((1.0, -1.0), (1.0, 1.0), (-1.0, 1.0), (-1.0, -1.0))
_CORNER_REACH = 1.0                 # continued waves run this far past the corner
_CORNER_STEP = 1.0 / 64.0           # sampling pitch of a continued wave
_CORNER_SCAN = 0.04                 # coarse pitch used to bracket the fillet
_CORNER_RADIUS_STEPS = (1.0, 1.5, 2.25, 3.4, 5.0)   # x CORNER_TIP_RADIUS
_CORNER_ARC_STEP = math.radians(5.0)
_CORNER_RECEIVER_SPAN = 3.0
# T_JUNCTION_CLEARANCE is the rounded form of the unchanged wall's own bound
# (nested_clearance); the slack covers that rounding and polyline sampling.
_CLEARANCE_SLACK = 1e-3


def _wave_phase(coordinate: float) -> float:
    return round(coordinate % WAVE_LENGTH, 9)


def _corner_point(axis: str, argument: float, sign: float, t: float):
    """Point ``t`` along a run, from its end at ``t = 0`` through the corner.

    Corner-relative; ``argument`` is the wave argument of the nominal corner.
    """
    along = sign * (t - CORNER_INSET)
    value = wall_wave_value(argument + along, axis)
    return (along, value) if axis == "x" else (value, along)


def _corner_normal(axis: str, argument: float, sign: float, cross: float, t: float):
    """Unit normal of that run pointing into the bin's material."""
    along = sign * (t - CORNER_INSET)
    slope = wall_wave_slope(argument + along, axis)
    scale = -cross / math.sqrt(1.0 + slope * slope)
    return (-slope * scale, scale) if axis == "x" else (scale, -slope * scale)


def _distinct(points) -> tuple:
    kept: list = []
    for point in points:
        if not kept or math.hypot(point[0] - kept[-1][0], point[1] - kept[-1][1]) > 1e-9:
            kept.append((float(point[0]), float(point[1])))
    return tuple(kept)


@lru_cache(maxsize=256)
def _corner_paths(corner: int, arg_x: float, arg_y: float) -> tuple:
    """Finished transitions of one corner, tip radius growing along the tuple.

    Corner ``corner`` is the ``_wall_points`` order (0 = lower right, counter-
    clockwise); coordinates are relative to its nominal corner. ``arg_x`` /
    ``arg_y`` are the wave arguments there on the X-running and Y-running
    walls. Every path starts at the arriving run's end and finishes at the
    departing run's start, both on the unchanged wave, with a shared tangent
    at each. An entry is ``None`` where no fillet of that radius fits.
    """
    sx, sy = _CORNER_SIGNS[corner]
    first, second = ("x", "y") if corner % 2 == 0 else ("y", "x")
    argument = {"x": arg_x, "y": arg_y}
    sign = {"x": sx, "y": sy}
    cross = {"x": sy, "y": sx}
    span = CORNER_INSET + _CORNER_REACH
    ts = [float(t) for t in np.linspace(0.0, span, int(math.ceil(span / _CORNER_STEP)) + 1)]

    def point(axis, t):
        return _corner_point(axis, argument[axis], sign[axis], t)

    def normal(axis, t):
        return _corner_normal(axis, argument[axis], sign[axis], cross[axis], t)

    out_curve = [point(second, t) for t in ts]
    out_line = LineString(out_curve)
    out_steps = np.diff(np.asarray(out_curve), axis=0)
    out_length = np.concatenate(([0.0], np.cumsum(np.hypot(out_steps[:, 0], out_steps[:, 1]))))

    def centre(t, radius):
        x, y = point(first, t)
        nx, ny = normal(first, t)
        return x + radius * nx, y + radius * ny

    def gap(t, radius):
        return out_line.distance(Point(*centre(t, radius))) - radius

    def fillet(radius):
        # Slide a circle of this radius along the arriving wall's inside until
        # it also touches the departing wall's continuation: the first contact
        # is the tangent fillet. Touching at the run end already means the
        # fillet would have to begin on the wall itself, so it does not fit.
        if gap(0.0, radius) <= 0.0:
            return None
        low = 0.0
        high = None
        for t in np.linspace(0.0, span, int(span / _CORNER_SCAN) + 1)[1:]:
            if gap(float(t), radius) <= 0.0:
                high = float(t)
                break
            low = float(t)
        if high is None:
            return None
        for _ in range(40):
            middle = 0.5 * (low + high)
            if gap(middle, radius) > 0.0:
                low = middle
            else:
                high = middle
        t_root = 0.5 * (low + high)
        cx, cy = centre(t_root, radius)
        start = point(first, t_root)
        along_out = out_line.project(Point(cx, cy))
        end = out_line.interpolate(along_out).coords[0]
        if abs(math.hypot(end[0] - cx, end[1] - cy) - radius) > 1e-4:
            return None
        angle = math.atan2(start[1] - cy, start[0] - cx)
        sweep = (math.atan2(end[1] - cy, end[0] - cx) - angle) % (2.0 * math.pi)
        if not 0.0 < sweep < math.pi:
            return None
        count = max(3, int(math.ceil(sweep / _CORNER_ARC_STEP)))
        arc = [
            (cx + radius * math.cos(angle + sweep * index / count),
             cy + radius * math.sin(angle + sweep * index / count))
            for index in range(1, count)
        ]
        head = [point(first, t) for t in ts if t < t_root - 1e-9]
        tail = [out_curve[index] for index in range(len(out_curve) - 1, -1, -1)
                if out_length[index] < along_out - 1e-9]
        return _distinct(head + [start] + arc + [tuple(end)] + tail)

    return tuple(fillet(CORNER_TIP_RADIUS * factor) for factor in _CORNER_RADIUS_STEPS)


def _corner_receivers(corner: int, arg_x: float, arg_y: float) -> tuple:
    """Unchanged receiving walls one mating gap outside a corner, as regions.

    A neighbour's wall is this bin's own wall curve, displaced by the mating
    gap, and it continues past the corner (the T junction where a corner faces
    the middle of an uninterrupted wall). The region beyond each curve holds
    whatever that neighbour is, so staying clear of it covers any neighbour
    size. Both wall directions and, through ``corner``, every quarter-turn
    and wave lean are covered.
    """
    sx, sy = _CORNER_SIGNS[corner]
    gap = WAVE_MATING_GAP
    far = gap + 2.0
    span = _CORNER_RECEIVER_SPAN
    steps = [float(s) for s in np.linspace(-span, span, int(round(2.0 * span / _CORNER_STEP)) + 1)]
    along_x = [(s, sy * gap + wall_wave_value(arg_x + s, "x")) for s in steps]
    along_y = [(sx * gap + wall_wave_value(arg_y + s, "y"), s) for s in steps]
    return (
        Polygon(along_x + [(span, sy * far), (-span, sy * far)]),
        Polygon(along_y + [(sx * far, span), (sx * far, -span)]),
    )


def _opposing_corner(corner: int, arg_x: float, arg_y: float):
    """Farthest-reaching finished corner of the bin diagonally across the seam.

    Four bins meeting at a point: the diagonal neighbour's nearest corner sits
    one mating gap away on each axis. Taking its largest-reach transition makes
    the check independent of how far that bin has to retreat itself.
    """
    sx, sy = _CORNER_SIGNS[corner]
    gap = WAVE_MATING_GAP
    paths = _corner_paths(
        (corner + 2) % 4, _wave_phase(arg_x + sx * gap), _wave_phase(arg_y + sy * gap),
    )
    for path in paths:
        if path is not None:
            return [(x + sx * gap, y + sy * gap) for x, y in path]
    return None


@lru_cache(maxsize=256)
def _corner_ladder(corner: int, arg_x: float, arg_y: float) -> tuple:
    """``_corner_paths`` entries that stay inside the clearance envelope."""
    limit = T_JUNCTION_CLEARANCE - _CLEARANCE_SLACK
    obstacles = list(_corner_receivers(corner, arg_x, arg_y))
    opposing = _opposing_corner(corner, arg_x, arg_y)
    if opposing is not None and len(opposing) > 1:
        obstacles.append(LineString(opposing))
    ladder = []
    for path in _corner_paths(corner, arg_x, arg_y):
        keep = path is not None and len(path) > 2
        if keep:
            line = LineString(path)
            keep = all(line.distance(obstacle) >= limit for obstacle in obstacles)
        ladder.append(path if keep else None)
    return tuple(ladder)


def _clearance_outline(
    points: list[tuple[float, float]], half_x: float, half_y: float,
    tx: float, ty: float, phase_x: float, phase_y: float,
) -> Polygon | None:
    """Wall runs (as ``_wall_points`` sampled them) joined by finished corners.

    The corners of one bin share a ladder rung, so a retreat is symmetric;
    ``None`` when no rung clears every corner, leaving the caller on the
    opened baseline outline.
    """
    count_x = _sample_count(2.0 * tx)
    count_y = _sample_count(2.0 * ty)
    cuts = (0, count_x, count_x + count_y, 2 * count_x + count_y, 2 * count_x + 2 * count_y)
    if len(points) != cuts[-1]:
        return None
    runs = [points[a:b] for a, b in zip(cuts[:-1], cuts[1:])]
    for rung in range(len(_CORNER_RADIUS_STEPS)):
        ring: list[tuple[float, float]] = []
        for corner, (sx, sy) in enumerate(_CORNER_SIGNS):
            path = _corner_ladder(
                corner,
                _wave_phase(sx * half_x + phase_x),
                _wave_phase(sy * half_y + phase_y),
            )[rung]
            if path is None:
                break
            ring += runs[corner]
            ring += [(sx * half_x + x, sy * half_y + y) for x, y in path[1:-1]]
        else:
            outline = Polygon(ring)
            if outline.is_valid:
                return outline
    return None


def preview_rings(
    spec: BoxSpec, points_per_cycle: float = 7.0
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Matched preview rings; project each outer point onto the built cavity.

    Projection also suppresses folded crests, keeping the preview tied to the
    printable offset rather than drawing the old axis-shifted wall.
    """
    # Draw the finished printable outline, keeping its smooth wall samples.
    outer = list(wavy_outer_polygon(spec).exterior.coords)[:-1]
    boundary = wavy_cavity_polygon(spec).exterior
    cavity = [
        tuple(boundary.interpolate(boundary.project(Point(point))).coords[0])
        for point in outer
    ]
    return outer, cavity


@lru_cache(maxsize=128)
def wavy_rect_outer(
    half_x: float, half_y: float, corner_fillet: float = DEFAULT_CORNER_FILLET,
    phase_x: float = 0.0, phase_y: float = 0.0,
) -> Polygon:
    """The same wavy outline ``wavy_outer_polygon`` builds, from raw half-
    extents instead of a ``BoxSpec`` - so a caller whose x/y is not the 7 mm
    grid size a normal bin's ``BoxSpec`` requires (a spacer filler) can still
    build the identical, correctly-phased wave.

    A normal ``BoxSpec``'s own centre always lands on the global wave
    lattice, so its local wave already equals the shared global one and
    ``phase_x``/``phase_y`` stay 0. A shape whose real placement centre will
    NOT land on that lattice - a spacer sized to a genuine non-7-mm-multiple
    free region - must pass its centre's own offset from the lattice (see
    ``_wall_points``) so the wave still matches a neighbour's along every
    seam once it is actually placed.

    Story 2425: at the default corner fillet the corners are the clearance-
    envelope construction above. ``_rounded``'s 0.6 mm opening is still applied
    to the run-and-chord outline first; it stays the outline whenever no
    corner rung fits the envelope, and for any other corner fillet setting.
    The finished outline is the one outline every consumer receives, and the
    cavity erodes it unchanged.
    """
    tx, ty = half_x - CORNER_INSET, half_y - CORNER_INSET
    points = _wall_points(half_x, half_y, tx, ty, phase_x=phase_x, phase_y=phase_y)
    polygon = Polygon(points)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("wavy box outline is not a valid single polygon")
    opened = _rounded(polygon, corner_fillet)
    if abs(corner_fillet - DEFAULT_CORNER_FILLET) < 1e-9 and tx > 0.0 and ty > 0.0:
        finished = _clearance_outline(points, half_x, half_y, tx, ty, phase_x, phase_y)
        # A finished corner only ever reaches outward of the chord it replaces.
        if finished is not None and finished.buffer(0.01).contains(opened):
            return finished
    return opened


def wavy_outer_polygon(spec: BoxSpec) -> Polygon:
    return wavy_rect_outer(spec.half_x, spec.half_y, spec.corner_fillet)


@lru_cache(maxsize=128)
def wavy_rect_cavity(
    half_x: float, half_y: float, wall_depth: float,
    corner_fillet: float = DEFAULT_CORNER_FILLET, wall: float = DEFAULT_WALL,
    phase_x: float = 0.0, phase_y: float = 0.0,
) -> Polygon:
    """Constant-distance erosion of the *built* outer outline by ``wall``.

    Round joins retain the distance invariant at concave vertices. GEOS
    discards folds when a thick offset passes a crest's centre of curvature;
    those crests have extra material, never less than the declared wall.
    ``wall_depth`` remains a compatibility/fit-envelope argument only.
    """
    outer = wavy_rect_outer(half_x, half_y, corner_fillet, phase_x, phase_y)
    polygon = outer.buffer(-wall, join_style=1, quad_segs=64) if wall else outer
    if not isinstance(polygon, Polygon) or polygon.is_empty or not polygon.is_valid:
        raise RuntimeError("wavy cavity erosion did not produce a valid single polygon")
    return polygon


def wavy_cavity_polygon(spec: BoxSpec) -> Polygon:
    """Interior outline, eroded by the declared perpendicular wall thickness."""
    return wavy_rect_cavity(spec.half_x, spec.half_y, spec.wall_depth, spec.corner_fillet, spec.wall)


def _wall_face_values(
    cavity: Polygon, coordinates, run_axis: str, side: float,
) -> np.ndarray:
    """Sample one built cavity face, including its suppressed crest segments.

    ``side`` selects the positive or negative wall. Intersecting the actual
    polygon edges makes this the shared face definition for every attachment.
    """
    vertices = np.asarray(cavity.exterior.coords)
    along = 1 if run_axis == "y" else 0
    across = 1 - along
    starts, ends = vertices[:-1], vertices[1:]
    delta = ends[:, along] - starts[:, along]
    values = []
    for coordinate in coordinates:
        mask = ((np.minimum(starts[:, along], ends[:, along]) <= coordinate)
                & (np.maximum(starts[:, along], ends[:, along]) >= coordinate)
                & (np.abs(delta) > 1e-12))
        if not np.any(mask):
            raise ValueError("wall attachment extends beyond the built cavity")
        fraction = (coordinate - starts[mask, along]) / delta[mask]
        hits = starts[mask, across] + fraction * (ends[mask, across] - starts[mask, across])
        values.append(float(np.max(hits) if side > 0 else np.min(hits)))
    return np.asarray(values)


def _wall_face_path(cavity: Polygon, coordinates, run_axis: str, side: float):
    """A face path with every polygon breakpoint retained between its ends."""
    coordinates = np.asarray(coordinates, dtype=float)
    along = 1 if run_axis == "y" else 0
    vertices = np.asarray(cavity.exterior.coords)[:, along]
    inside = vertices[(vertices > coordinates[0]) & (vertices < coordinates[-1])]
    samples = np.unique(np.concatenate((coordinates, inside)))
    # Opposite faces can contribute numerically coincident breakpoints. Avoid
    # zero-area sweep faces after trimesh merges their vertices.
    samples = samples[np.r_[True, np.diff(samples) > 1e-7]]
    faces = _wall_face_values(cavity, samples, run_axis, side)
    return [(float(f), float(s)) if run_axis == "y" else (float(s), float(f))
            for s, f in zip(samples, faces)]


@lru_cache(maxsize=64)
def _periodic_wall_face(wall_depth: float, run_axis: str, side: float):
    """One period of the built face, away from the corner transitions.

    Ordinary grid bins have the same 1/16 mm outer sampling lattice. This
    reference outline uses that lattice too; only its central period is kept,
    so connectors also follow the wall when their cap spans a bin corner.
    """
    half = 4.0 * WAVE_LENGTH - WAVE_MATING_GAP / 2.0
    wall = wall_depth / wall_depth_for(1.0)
    cavity = wavy_rect_cavity(half, half, wall_depth, wall=wall)
    path = np.asarray(_wall_face_path(
        cavity, [-WAVE_LENGTH / 2.0, WAVE_LENGTH / 2.0], run_axis, side,
    ))
    along = 1 if run_axis == "y" else 0
    return path[:, along], path[:, 1 - along] - side * half


def _wall_face_offset(
    coordinates, run_axis: str, side: float, wall_depth: float,
) -> np.ndarray:
    """Built interior face relative to its nominal outer wall axis."""
    samples, faces = _periodic_wall_face(wall_depth, run_axis, side)
    phase = (np.asarray(coordinates, dtype=float) + WAVE_LENGTH / 2.0) % WAVE_LENGTH - WAVE_LENGTH / 2.0
    return np.interp(phase, samples, faces)


def _lock_embed(path, outer: Polygon) -> float:
    """Reserve safe exterior skin using the actual local wall, not its envelope."""
    thickness = outer.boundary.distance(LineString(path))
    return max(0.0, min(LOCK_EMBED, thickness - LOCK_SAFE_SKIN))


def placed_outline(
    spec: BoxSpec, centre: tuple[float, float] = (0.0, 0.0)
) -> Polygon:
    """``spec``'s outer outline, moved to a centre on the drawer grid.

    A legal box spans a whole number of ``GRID_PITCH`` cells, so wherever it
    sits in a packed drawer its centre lands on a multiple of ``WAVE_LENGTH`` -
    half a grid step.  That is the whole reason mixed sizes tile.  The wave's
    phase depends only on the distance from the wall's own centre, so two walls
    a whole number of cycles apart carry the identical curve and nest; anything
    else puts a crest against a crest.  An off-lattice centre is refused here
    rather than quietly measured, because the clearance it reported would be a
    number nothing can be built to.
    """
    cx, cy = float(centre[0]), float(centre[1])
    for name, value in (("X", cx), ("Y", cy)):
        cycles = value / WAVE_LENGTH
        if abs(cycles - round(cycles)) > 1e-6:
            raise ValueError(
                f"a bin centre has to land on the {WAVE_LENGTH:g} mm wave lattice "
                f"so its walls share phase with its neighbours'; centre {name} = "
                f"{value:g} mm does not - try {round(cycles) * WAVE_LENGTH:g} mm"
            )
    return translate_polygon(wavy_outer_polygon(spec), cx, cy)


def mating_clearance(
    a: BoxSpec,
    a_centre: tuple[float, float],
    b: BoxSpec,
    b_centre: tuple[float, float],
) -> float:
    """Smallest gap between two bins standing side by side on the grid.

    Two bins that share a wall measure ``nested_clearance()`` whatever their
    sizes, because that wall is one global wave and the two outlines are the
    same curve offset by ``WAVE_MATING_GAP``.  Two that meet only at a corner
    measure more: a finished corner is the two wall waves continued to a
    rounded tip, never past the unchanged receiving wall's own offset, so a
    corner never measures less than the wall seam.  The corners are
    transitions between the four rotationally matching wall runs rather than
    a separate mating phase.

    Raises if the two outlines actually intersect.  A collision is a fault in
    the sizes or the placement, not a clearance worth reporting.
    """
    first = placed_outline(a, a_centre)
    second = placed_outline(b, b_centre)
    overlap = first.intersection(second)
    if not overlap.is_empty:
        raise ValueError(
            f"a {a.x:g} x {a.y:g} bin at {a_centre} and a {b.x:g} x {b.y:g} bin at "
            f"{b_centre} collide over {overlap.area:.4f} mm2; they cannot both "
            f"stand on the grid as placed"
        )
    return first.distance(second)


# --------------------------------------------------------------------------- #
# lock bumps
# --------------------------------------------------------------------------- #
def lock_z_levels(rim_z: float) -> tuple[float, float, float, float]:
    """``(bottom, flat_bottom, flat_top, top)`` of a bump below ``rim_z``."""
    top = rim_z - LOCK_TOP_BELOW_RIM
    flat_top = top - LOCK_CHAMFER
    flat_bottom = flat_top - LOCK_FLAT
    bottom = flat_bottom - LOCK_CHAMFER
    return bottom, flat_bottom, flat_top, top


def _lock_profile(
    protrusion: float,
    clearance: float = 0.0,
    embed: float = LOCK_EMBED,
) -> list[tuple[float, float]]:
    """Chamfered section, ``t`` growing away from the face it sits on.

    Both chamfers run at exactly 45 degrees from the buried root right out to
    the tip, so the section has no horizontal face at all: it prints without
    support in either orientation, and it never lands a face coincident with
    the wall it grows from.  The ``t < 0`` root is inside that wall.
    """
    bottom, _, _, top = lock_z_levels(0.0)
    low, high = bottom - clearance, top + clearance
    reach = protrusion + clearance
    flat_bottom, flat_top = low + reach, high - reach
    if flat_top <= flat_bottom:
        raise ValueError("lock chamfers overlap; reduce the protrusion or clearance")
    return [
        (-embed, low - embed),
        (reach, flat_bottom),
        (reach, flat_top),
        (-embed, high + embed),
    ]


def _rect_wall_lock_paths(
    half_x: float, half_y: float, wall_depth: float,
    phase_x: float = 0.0, phase_y: float = 0.0,
    *, wall: float | None = None, corner_fillet: float = DEFAULT_CORNER_FILLET,
) -> list[tuple[list[tuple[float, float]], tuple[float, float]]]:
    """Lock paths on the built cavity, retaining the global extremum lattice."""
    if wall is None:
        wall = wall_depth / wall_depth_for(1.0)
    cavity = wavy_rect_cavity(
        half_x, half_y, wall_depth, corner_fillet, wall, phase_x, phase_y,
    )
    walls = (
        ("y", half_y, 1.0, (-1.0, 0.0), phase_y),
        ("y", half_y, -1.0, (1.0, 0.0), phase_y),
        ("x", half_x, 1.0, (0.0, -1.0), phase_x),
        ("x", half_x, -1.0, (0.0, 1.0), phase_x),
    )
    paths = []
    for run_axis, wave_half, side, inward, phase in walls:
        limit = wave_half - CORNER_INSET - LOCK_CORNER_CLEAR - LOCK_RUN / 2.0
        for base_centre in lock_lattice(-limit + phase, limit + phase):
            centre = base_centre - phase
            ss = np.linspace(centre - LOCK_RUN / 2.0, centre + LOCK_RUN / 2.0, _sample_count(LOCK_RUN))
            paths.append((_wall_face_path(cavity, ss, run_axis, side), inward))
    return paths


def _wall_lock_paths(
    spec: BoxSpec,
) -> list[tuple[list[tuple[float, float]], tuple[float, float]]]:
    return _rect_wall_lock_paths(
        spec.half_x, spec.half_y, spec.wall_depth,
        wall=spec.wall, corner_fillet=spec.corner_fillet,
    )


def make_wall_lock_bumps_raw(
    half_x: float, half_y: float, wall_depth: float, z: float,
    phase_x: float = 0.0, phase_y: float = 0.0,
    *, wall: float | None = None, corner_fillet: float = DEFAULT_CORNER_FILLET,
) -> list[trimesh.Trimesh]:
    """Bumps on the eroded face, with roots limited by real local thickness."""
    outer = wavy_rect_outer(half_x, half_y, corner_fillet, phase_x, phase_y)
    bumps = []
    for path, inward in _rect_wall_lock_paths(
        half_x, half_y, wall_depth, phase_x, phase_y,
        wall=wall, corner_fillet=corner_fillet,
    ):
        profile = _lock_profile(LOCK_PROTRUSION, embed=_lock_embed(path, outer))
        bumps.append(translated(_sweep_profile(path, inward, profile), (0.0, 0.0, z)))
    return bumps


def make_wall_lock_bumps(spec: BoxSpec) -> list[trimesh.Trimesh]:
    """Small chamfered bumps standing proud of each wall's built interior face."""
    return make_wall_lock_bumps_raw(
        spec.half_x, spec.half_y, spec.wall_depth, spec.z,
        wall=spec.wall, corner_fillet=spec.corner_fillet,
    )


def wall_lock_receivers(
    spec: BoxSpec, wall: str, low: float, high: float,
) -> list[trimesh.Trimesh]:
    """Notch cutters that receive one wall's ordinary lock bumps.

    ``wall`` is ``"+x"``, ``"-x"``, ``"+y"`` or ``"-y"``; ``low``/``high`` are
    coordinates along that wall from its centre. A cutter is returned for every
    bump on the wall that reaches into that span at all - including one only
    partly covered, since a solid part ending on a bump would foul it. Each
    cutter is the bump's own swept section grown by ``LOCK_NOTCH_CLEARANCE``
    (the same profile connectors are notched with), placed at the same
    positions and rim height as the bump, so a part cut with them seats over
    the bumps without touching and still catches on their chamfers.
    """
    run_axis, wave_half, _face, inward = _wall_face_table(spec)[wall]
    side = 1.0 if wall.startswith("+") else -1.0
    cavity = wavy_cavity_polygon(spec)
    outer = wavy_outer_polygon(spec)
    cutters: list[trimesh.Trimesh] = []
    for centre in lock_positions(wave_half - CORNER_INSET - LOCK_CORNER_CLEAR):
        lo, hi = centre - LOCK_RUN / 2.0, centre + LOCK_RUN / 2.0
        if hi < low or lo > high:
            continue
        ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
        path = _wall_face_path(cavity, ss, run_axis, side)
        profile = _lock_profile(
            LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE, embed=_lock_embed(path, outer),
        )
        cutters.append(translated(_sweep_profile(path, inward, profile), (0.0, 0.0, spec.z)))
    return cutters


# --------------------------------------------------------------------------- #
# lift grabbers
# --------------------------------------------------------------------------- #
_LIFT_GRABBER_WALL_LABELS = {
    "+x": "right", "-x": "left", "+y": "back", "-y": "front",
}


def _wall_face_table(
    spec: BoxSpec,
) -> dict[str, tuple[str, float, float, tuple[float, float]]]:
    """Built face anchor for flat attachments, plus wall metadata.

    Flat grabbers retain their existing root depth. Limit their anchor by the
    actual exterior's inward envelope so rebasing the face cannot expose a
    root. Curved locks use ``_wall_face_path`` throughout their whole span.
    """
    cavity = wavy_cavity_polygon(spec)
    outer = wavy_outer_polygon(spec)
    root = min(WAVE_AMPLITUDE + LOCK_EMBED, spec.wall_depth - WAVE_AMPLITUDE - LOCK_SAFE_SKIN)

    def anchor(axis: str, side: float) -> float:
        face = side * float(_wall_face_values(cavity, [0.0], axis, side)[0])
        exterior = side * _wall_face_values(
            outer, [-WAVE_LENGTH / 4.0, WAVE_LENGTH / 4.0], axis, side,
        )
        return side * min(face, float(np.min(exterior)) - LOCK_SAFE_SKIN - root)

    return {
        name: (axis, reach, anchor(axis, side), inward)
        for name, axis, reach, side, inward in (
            ("+x", "y", spec.half_y, 1.0, (-1.0, 0.0)),
            ("-x", "y", spec.half_y, -1.0, (1.0, 0.0)),
            ("+y", "x", spec.half_x, 1.0, (0.0, -1.0)),
            ("-y", "x", spec.half_x, -1.0, (0.0, 1.0)),
        )
    }
