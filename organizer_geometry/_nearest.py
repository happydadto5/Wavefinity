"""Fast nearest-point-on-a-line for the preview (never used by print/export)."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree


def closest_points_on_line(boundary: LineString, points: np.ndarray) -> np.ndarray:
    """The nearest point on the closed ``boundary`` for every row of ``points``.

    Same answer as ``boundary.interpolate(boundary.project(Point(p)))`` one
    point at a time, but a spatial index finds each nearest segment instead of
    testing every segment for every point. A point with more than one
    distinct, equally near answer (the centre of a concave crest) is settled by
    the original call, so ties break exactly as they always did.
    """
    ring = np.asarray(boundary.coords)
    starts, ends = ring[:-1], ring[1:]
    run_all = ends - starts
    length_sq_all = np.einsum("ij,ij->i", run_all, run_all)
    tree = STRtree(shapely.linestrings(np.stack([starts, ends], axis=1)))
    where = shapely.points(points)
    (found_input, found_segment), nearest = tree.query_nearest(
        where, all_matches=False, return_distance=True,
    )
    segment = np.zeros(len(points), dtype=int)
    segment[found_input] = found_segment
    best = np.zeros(len(points))
    best[found_input] = nearest

    def foot(point_index, segment_index):
        a = starts[segment_index]
        run = run_all[segment_index]
        length_sq = length_sq_all[segment_index]
        along = np.einsum("ij,ij->i", points[point_index] - a, run)
        t = np.clip(np.divide(along, length_sq, out=np.zeros_like(along),
                              where=length_sq > 0.0), 0.0, 1.0)
        return a + t[:, None] * run

    every = np.arange(len(points))
    closest = foot(every, segment)
    # Every segment about as near as the nearest: more than one place to land?
    near_input, near_segment = tree.query(where, predicate="dwithin", distance=best + 1e-11)
    landing = foot(near_input, near_segment)
    low = np.full((len(points), 2), np.inf)
    high = np.full((len(points), 2), -np.inf)
    np.minimum.at(low, near_input, landing)
    np.maximum.at(high, near_input, landing)
    ambiguous = np.flatnonzero(np.any(high - low > 1e-9, axis=1))
    if len(ambiguous):
        first = np.full(len(points), len(starts))
        last = np.full(len(points), -1)
        np.minimum.at(first, near_input, near_segment)
        np.maximum.at(last, near_input, near_segment)
    for index in ambiguous:
        # Only the segments in play: GEOS breaks the tie among them in line
        # order, so projecting onto just that stretch lands exactly where the
        # whole-boundary call would, without testing the other thousands.
        lo, hi = int(first[index]), int(last[index])
        stretch = boundary if hi - lo > 512 else LineString(ring[lo:hi + 2])
        closest[index] = stretch.interpolate(
            stretch.project(Point(points[index]))
        ).coords[0]
    return closest
