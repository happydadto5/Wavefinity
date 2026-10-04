"""Nest finger/push access points and access plans."""

from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from ._base import (
    NEST_CUSTOM_WIDTH_MIN,
    NEST_CUSTOM_WIDTH_MAX,
    _line_coordinates,
    _min_rotated_rect_axes,
    _automatic_finger_width_for,
)


# --- the one authoritative Nest access planner --------------------------------
#
# Works entirely in local tool coordinates, before editor rotation and
# placement. Raised Wall notches, Recessed scoops, required-footprint sizing
# and the 2D preview all resolve access through this one search.

@dataclass(frozen=True)
class AccessPoint:
    position: tuple[float, float]
    tangent: tuple[float, float]
    normal: tuple[float, float]     # outward, away from the polygon's interior
    chord: float                    # local straight-line safety margin achieved


@dataclass(frozen=True)
class NestAccessPlan:
    style: str                      # "finger_grasp" | "none"
    width: float
    points: tuple[AccessPoint, ...]
    footprint: Polygon              # union of local access circles, for sizing/preview
    warning: str | None


def _sample_at(polygon: Polygon, s: float) -> np.ndarray:
    length = polygon.exterior.length
    point = polygon.exterior.interpolate(s % length)
    return np.array([point.x, point.y])


def _validate_access_point(
    polygon: Polygon, s: float, width: float, origin: np.ndarray,
) -> AccessPoint | None:
    """One candidate boundary location: sample the exterior a half-width
    either side and require the straight chord between them to be at least
    70% of the requested opening, so a sharp or narrow spot is rejected."""
    a = _sample_at(polygon, s - width / 2.0)
    b = _sample_at(polygon, s + width / 2.0)
    chord_vec = b - a
    chord = float(np.linalg.norm(chord_vec))
    if chord < 0.70 * width or chord < 1e-6:
        return None
    tangent = chord_vec / chord
    normal = np.array([tangent[1], -tangent[0]])
    centre = _sample_at(polygon, s)
    if np.dot(normal, centre - origin) < 0.0:
        normal = -normal
    return AccessPoint(
        (float(centre[0]), float(centre[1])),
        (float(tangent[0]), float(tangent[1])),
        (float(normal[0]), float(normal[1])),
        chord,
    )


def _segment_through_point(
    polygon: Polygon, line: LineString, near: Point,
) -> tuple[np.ndarray, np.ndarray] | None:
    """The one chord of ``line`` clipped to the polygon interior that actually
    passes through ``near`` - the segment a candidate axis line forms across
    the lobe containing the outline's own representative point."""
    clipped = line.intersection(polygon)
    if clipped.is_empty:
        return None
    segments = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
    best, best_distance = None, None
    for segment in segments:
        if not hasattr(segment, "coords") or len(segment.coords) < 2:
            continue
        distance = segment.distance(near)
        if best_distance is None or distance < best_distance:
            best_distance, best = distance, segment
    if best is None:
        return None
    coords = list(best.coords)
    return np.array(coords[0]), np.array(coords[-1])


def _axis_pair(
    polygon: Polygon, direction: np.ndarray, representative: Point, width: float,
) -> tuple[AccessPoint, AccessPoint] | None:
    """Both ends of the candidate line's chord through the representative
    point, only if both independently pass the local-chord safety check."""
    min_x, min_y, max_x, max_y = polygon.bounds
    reach = math.hypot(max_x - min_x, max_y - min_y) + 10.0
    origin = np.array([representative.x, representative.y])
    line = LineString([origin - direction * reach, origin + direction * reach])
    ends = _segment_through_point(polygon, line, representative)
    if ends is None:
        return None
    points: list[AccessPoint] = []
    for end in ends:
        s = polygon.exterior.project(Point(end))
        point = _validate_access_point(polygon, s, width, origin)
        if point is None:
            return None
        points.append(point)
    return points[0], points[1]


def _single_axis_points(
    polygon: Polygon, direction: np.ndarray, representative: Point, width: float,
) -> list[AccessPoint]:
    """Whichever end(s) of the candidate line's chord individually validate -
    used for an explicit Custom side/end request, where using only the valid
    one is preferred over rejecting the whole Nest."""
    min_x, min_y, max_x, max_y = polygon.bounds
    reach = math.hypot(max_x - min_x, max_y - min_y) + 10.0
    origin = np.array([representative.x, representative.y])
    line = LineString([origin - direction * reach, origin + direction * reach])
    ends = _segment_through_point(polygon, line, representative)
    if ends is None:
        return []
    found = []
    for end in ends:
        s = polygon.exterior.project(Point(end))
        point = _validate_access_point(polygon, s, width, origin)
        if point is not None:
            found.append(point)
    return found


def _boundary_fallback_pair(
    polygon: Polygon, width: float, representative: Point,
) -> tuple[AccessPoint, AccessPoint] | None:
    """Sample the whole exterior at ~5 mm steps for an irregular outline the
    centre-line search could not pair, and score the candidate pairs."""
    length = polygon.exterior.length
    count = max(8, int(length // 5.0))
    origin = np.array([representative.x, representative.y])
    samples: list[AccessPoint] = []
    for index in range(count):
        point = _validate_access_point(polygon, length * index / count, width, origin)
        if point is not None:
            samples.append(point)
    best_pair, best_score = None, None
    opposite_limit = math.cos(math.radians(150.0))  # within ~30 deg of opposite
    for i, a in enumerate(samples):
        for b in samples[i + 1:]:
            cos_angle = float(np.dot(np.array(a.normal), np.array(b.normal)))
            if cos_angle > opposite_limit:
                continue
            pa, pb = np.array(a.position), np.array(b.position)
            if float(np.linalg.norm(pb - pa)) < width:
                continue
            # A cheap stand-in for "resulting Nest bounding area": the two
            # points' own bounding box, without recomputing the whole footprint.
            proxy_area = abs(pa[0] - pb[0]) * abs(pa[1] - pb[1])
            centre_distance = float(np.linalg.norm((pa + pb) / 2.0 - origin))
            score = (proxy_area, centre_distance, -min(a.chord, b.chord))
            if best_score is None or score < best_score:
                best_score, best_pair = score, (a, b)
    return best_pair


def resolve_nest_access_plan(
    polygon: Polygon, mode: str, locations: str = "sides", width: float | None = None,
) -> NestAccessPlan:
    """The one authoritative access search: Automatic, Off, or Custom, all in
    the tool's own local coordinates. Never raises for a difficult outline -
    it falls back to a single location, then to none, always with a warning."""
    mode = mode if mode in {"auto", "off", "custom"} else "auto"
    if mode == "off":
        return NestAccessPlan("none", 0.0, (), Polygon(), None)

    representative = polygon.representative_point()
    short_dir, long_dir, _short_span, _long_span = _min_rotated_rect_axes(polygon)

    if mode == "custom":
        resolved_width = min(NEST_CUSTOM_WIDTH_MAX, max(
            NEST_CUSTOM_WIDTH_MIN,
            float(width) if width else _automatic_finger_width_for(polygon),
        ))
        wanted = {
            "sides": (short_dir,), "top_bottom": (long_dir,), "both": (short_dir, long_dir),
        }.get(locations, (short_dir,))
        points: list[AccessPoint] = []
        requested = 0
        for direction in wanted:
            requested += 2
            points.extend(_single_axis_points(polygon, direction, representative, resolved_width))
        if not points:
            return NestAccessPlan(
                "none", resolved_width, (), Polygon(),
                "No safe finger opening location was found for the requested sides; "
                "generated without one.",
            )
        warning = (
            "Some requested finger openings did not fit safely on this outline "
            "and were skipped." if len(points) < requested else None
        )
        footprint = unary_union([
            Point(p.position).buffer(resolved_width / 2.0, quad_segs=32) for p in points
        ])
        return NestAccessPlan("finger_grasp", resolved_width, tuple(points), footprint, warning)

    # Automatic: try the short axis, the long axis, then 15-degree increments,
    # in that order, then an irregular-shape fallback, then a single location.
    resolved_width = _automatic_finger_width_for(polygon)
    candidates = [short_dir, long_dir]
    for degrees in range(0, 180, 15):
        radians = math.radians(degrees)
        direction = np.array([math.cos(radians), math.sin(radians)])
        if any(abs(float(np.dot(direction, existing))) > 0.999 for existing in candidates):
            continue
        candidates.append(direction)

    for direction in candidates:
        pair = _axis_pair(polygon, direction, representative, resolved_width)
        if pair is not None:
            footprint = unary_union([
                Point(pair[0].position).buffer(resolved_width / 2.0, quad_segs=32),
                Point(pair[1].position).buffer(resolved_width / 2.0, quad_segs=32),
            ])
            return NestAccessPlan("finger_grasp", resolved_width, pair, footprint, None)

    fallback = _boundary_fallback_pair(polygon, resolved_width, representative)
    if fallback is not None:
        footprint = unary_union([
            Point(fallback[0].position).buffer(resolved_width / 2.0, quad_segs=32),
            Point(fallback[1].position).buffer(resolved_width / 2.0, quad_segs=32),
        ])
        return NestAccessPlan("finger_grasp", resolved_width, fallback, footprint, None)

    length = polygon.exterior.length
    origin = np.array([representative.x, representative.y])
    steps = max(8, int(length // 5.0))
    best_single, best_chord = None, -1.0
    for index in range(steps):
        point = _validate_access_point(polygon, length * index / steps, resolved_width, origin)
        if point is not None and point.chord > best_chord:
            best_single, best_chord = point, point.chord
    if best_single is not None:
        footprint = Point(best_single.position).buffer(resolved_width / 2.0, quad_segs=32)
        return NestAccessPlan(
            "finger_grasp", resolved_width, (best_single,), footprint,
            "Only one finger opening could be placed safely on this outline.",
        )
    return NestAccessPlan(
        "none", resolved_width, (), Polygon(),
        "No safe finger-opening location was found on this outline; generated without one.",
    )


def _legacy_finger_positions(opening: Polygon, position: str) -> list[tuple[float, float]]:
    """The old fixed local-axis crossing placement, preview-only re-creation
    (no tangent/normal, no cutter geometry) so a legacy design's 2D indicator
    still shows roughly where its notches actually fall."""
    min_x, min_y, max_x, max_y = opening.bounds
    inside = opening.representative_point()
    reach = max(max_x - min_x, max_y - min_y) + 10.0
    points: list[tuple[float, float]] = []
    if position in {"sides", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (min_x - reach, inside.y), (max_x + reach, inside.y)
        ]))
        xs = _line_coordinates(crossing, 0)
        if len(xs) >= 2:
            points.append((min(xs), float(inside.y)))
            points.append((max(xs), float(inside.y)))
    if position in {"top_bottom", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (inside.x, min_y - reach), (inside.x, max_y + reach)
        ]))
        ys = _line_coordinates(crossing, 1)
        if len(ys) >= 2:
            points.append((float(inside.x), min(ys)))
            points.append((float(inside.x), max(ys)))
    return points
