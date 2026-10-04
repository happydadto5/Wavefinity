"""Bore wall-only envelope, rings and join tabs."""

from __future__ import annotations

import math
import trimesh
import numpy as np
import shapely
from shapely.geometry import LineString, Polygon, box as shapely_box
from organizer_engine import (
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    BoxSpec,
    wall_depth_for,
    wave_value,
    wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, union
from .._core import Zone

from ._consts import (
    BORE_WALL,
    HEX_BIT_HOLD,
    WALL_ONLY_FOOT,
    ACCESS_CUTTER_CLEARANCE,
    JOIN_TOUCH,
    JOIN_BAND,
    JOIN_SKIN,
    HUG_REACH,
    WAVE_NOISE_FLOOR,
    WAVE_SAMPLES_PER_CYCLE,
)


def _is_hex_bit(profile: str) -> bool:
    return profile in HEX_BIT_HOLD


def _hole_sides(profile: str) -> int:
    """Polygon sides for a bore hole of this profile - round is a fine circle,
    a hex bit is a six-sided socket."""
    return {
        "round": 48, "hex": 6, "square": 4, "square_axis": 4,
        "hex_bit_short": 6, "hex_bit_long": 6,
    }[profile]


def _axis_square(profile: str) -> bool:
    return profile == "square_axis"


def bore_minimum_pitches(
    profile: str, held: float, wall: float, angle: float, lean_axis: str,
) -> tuple[float, float]:
    """Smallest X/Y centre pitches that retain the requested wall thickness."""
    sides = _hole_sides(profile)
    if _axis_square(profile):
        cross_pitch = held + wall
    else:
        radius = held / 2.0 / (math.cos(math.pi / sides) if sides < 8 else 1.0)
        cross_pitch = 2.0 * radius + wall
    lean_pitch = cross_pitch / math.cos(math.radians(angle)) if angle > 1e-9 else cross_pitch
    return (lean_pitch, cross_pitch) if lean_axis == "x" else (cross_pitch, lean_pitch)


def _wall_only_shell_reach(wall: float, wall_style: str) -> float:
    """How far a Wall Only sleeve reaches past its clear opening, per side.

    A wavy inner wall runs from 0 to ``2 * WAVE_AMPLITUDE`` outward of the
    clear profile; the outer face adds Wavefinity's wall depth on top.
    """
    if wall_style == "wavy":
        return 2.0 * WAVE_AMPLITUDE + wall_depth_for(wall) + WAVE_NOISE_FLOOR
    return wall


def _round_clear_sides(held: float, wall_style: str) -> int:
    """Sides of the polygon that stands in for a round clear opening."""
    if wall_style == "wavy":
        cycles = max(1, round(math.pi * held / WAVE_LENGTH))
        return max(256, WAVE_SAMPLES_PER_CYCLE * cycles)
    return 256


def _clear_spans(profile: str, held: float, wall_style: str) -> tuple[float, float]:
    """X/Y span of one upright clear opening - exactly what the builder cuts.

    A round opening is a polygon circumscribing the requested circle, so its
    span is a hair over ``held``.
    """
    if profile == "round":
        span = held / math.cos(math.pi / _round_clear_sides(held, wall_style))
        return span, span
    if _axis_square(profile):
        return held, held
    sides = _hole_sides(profile)
    radius = held / 2.0 / math.cos(math.pi / sides)
    if sides == 4:                      # diamond: corners on both axes
        return 2.0 * radius, 2.0 * radius
    return 2.0 * radius, held           # hex: corners on X, flats on Y


def wall_only_envelope(
    profile: str, held: float, wall: float, wall_style: str,
    foot: bool = False,
) -> dict[str, float]:
    """Shared Wall Only spacing/size numbers (backend build, layout, Auto Grid).

    Pitch keeps today's "clear opening + requested web" rule at upright angle;
    the physical one-hole span is the clear span plus the shell on both sides.
    ``foot`` (Wall Only only, never Wavy Base) also adds the base strengthening
    foot, WALL_ONLY_FOOT, on each outside side; pitch is unchanged.
    """
    pitch_x, pitch_y = bore_minimum_pitches(profile, held, wall, 0.0, "x")
    clear_x, clear_y = _clear_spans(profile, held, wall_style)
    reach = _wall_only_shell_reach(wall, wall_style)
    extra = 2.0 * WALL_ONLY_FOOT if foot else 0.0
    return {
        "pitch_x": pitch_x, "pitch_y": pitch_y,
        "clear_x": clear_x, "clear_y": clear_y, "reach": reach,
        "span_x": clear_x + 2.0 * reach + extra,
        "span_y": clear_y + 2.0 * reach + extra,
        # Pre-Fix-065 stored zones were sized to the shell alone; the foot was
        # allowed past them. Zone acceptance / Auto Grid fit keep honouring that.
        "zone_span_x": clear_x + 2.0 * reach, "zone_span_y": clear_y + 2.0 * reach,
    }


def _clear_profile_points(profile: str, held: float, wall_style: str) -> list[tuple[float, float]]:
    """Counter-clockwise outline of one upright clear opening.

    Round openings are a fine polygon circumscribing the true circle so the
    opening is never smaller than requested.
    """
    if profile == "round":
        sides = _round_clear_sides(held, wall_style)
        radius = held / 2.0 / math.cos(math.pi / sides)
        return [
            (radius * math.cos(2.0 * math.pi * i / sides),
             radius * math.sin(2.0 * math.pi * i / sides))
            for i in range(sides)
        ]
    if _axis_square(profile):
        half = held / 2.0
        return [(half, half), (-half, half), (-half, -half), (half, -half)]
    sides = _hole_sides(profile)
    radius = held / 2.0 / math.cos(math.pi / sides)
    return [
        (radius * math.cos(2.0 * math.pi * i / sides),
         radius * math.sin(2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def _wavy_outline(
    clear: list[tuple[float, float]], thickness: float,
) -> list[tuple[float, float]]:
    """Displace the clear outline outward by a whole-cycle sine.

    Each edge is walked by arc length and pushed along its own outward normal by
    ``WAVE_AMPLITUDE * (1 + sin(phase)) + thickness``. The
    displacement is never negative, so the outline never enters the clear
    profile; at corners the neighbouring displaced edge ends simply join.
    """
    count = len(clear)
    edges = [(clear[i], clear[(i + 1) % count]) for i in range(count)]
    lengths = [math.dist(a, b) for a, b in edges]
    perimeter = sum(lengths)
    cycles = max(1, round(perimeter / WAVE_LENGTH))
    step = WAVE_LENGTH / WAVE_SAMPLES_PER_CYCLE
    points: list[tuple[float, float]] = []
    travelled = 0.0
    for (a, b), length in zip(edges, lengths):
        nx, ny = (b[1] - a[1]) / length, -(b[0] - a[0]) / length   # CCW: outward is right
        pieces = max(1, math.ceil(length / step))
        for k in range(pieces + 1):
            t = k / pieces
            s = travelled + t * length
            push = (thickness + WAVE_NOISE_FLOOR
                    + WAVE_AMPLITUDE * (1.0 + math.sin(2.0 * math.pi * cycles * s / perimeter)))
            points.append((a[0] + (b[0] - a[0]) * t + nx * push,
                           a[1] + (b[1] - a[1]) * t + ny * push))
        travelled += length
    return points


def _wall_only_ring(
    profile: str, held: float, wall: float, wall_style: str,
) -> tuple[Polygon, Polygon, Polygon]:
    """(outer, inner, clear) outlines of one upright Wall Only sleeve at 0, 0.

    ``inner`` is the sleeve's bore wall, which hugs or waves outward of the
    ``clear`` opening the user asked for.
    """
    outline = _clear_profile_points(profile, held, wall_style)
    clear = Polygon(outline)
    if wall_style == "wavy":
        inner = Polygon(_wavy_outline(outline, 0.0))
        outer = Polygon(_wavy_outline(outline, wall_depth_for(wall)))
    else:
        inner = clear
        outer = clear.buffer(wall, join_style="round")
    if (not outer.is_valid or not inner.is_valid or not outer.contains(inner)
            or not inner.buffer(1e-7).contains(clear)):
        raise ValueError("bore wall profile could not be built; try another wall or shape")
    return outer, inner, clear


def _union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return meshes[0] if len(meshes) == 1 else union(meshes)


def _polygons(shape) -> list[Polygon]:
    """The area pieces of a shapely result, ignoring stray lines and points."""
    if shape.is_empty:
        return []
    if isinstance(shape, Polygon):
        return [shape]
    return [piece for piece in getattr(shape, "geoms", ())
            if isinstance(piece, Polygon) and not piece.is_empty]


WEB_COINCIDENCE_TOL = 2e-3
WEB_WIDTH_NUDGES = (0.0, 0.007, -0.007, 0.019, -0.019, 0.041, -0.041)


def _ring_points(shape) -> np.ndarray:
    points = []
    for piece in _polygons(shape):
        for ring in (piece.exterior, *piece.interiors):
            points.append(np.asarray(ring.coords)[:, :2])
    return np.vstack(points) if points else np.empty((0, 2))


def _web_is_clean(web, *shapes) -> bool:
    """No web edge grazes a neighbouring vertex closely enough to leave a sliver.

    A web side that passes a hair (under a couple of microns) from a sleeve
    vertex makes a boolean union with sub-micron faces that export rounding
    can turn into a broken solid.
    """
    edge = web.boundary.buffer(WEB_COINCIDENCE_TOL)
    for shape in shapes:
        points = _ring_points(shape)
        if len(points) and shapely.contains_xy(edge, points[:, 0], points[:, 1]).any():
            return False
        lines = shape.boundary.buffer(WEB_COINCIDENCE_TOL)
        corners = _ring_points(web)
        if len(corners) and shapely.contains_xy(lines, corners[:, 0], corners[:, 1]).any():
            return False
    return True


def _web_polygon(points, width: float, avoid, limit, keep_clear) -> list[Polygon]:
    """A slender web along ``points``; ``width`` is nudged only to avoid slivers."""
    chosen: list[Polygon] = []
    for nudge in WEB_WIDTH_NUDGES:
        web = LineString(points).buffer(max(0.4, width + nudge) / 2.0, cap_style=2, join_style=2)
        web = web.difference(keep_clear).intersection(limit)
        chosen = [part for part in _polygons(web) if part.area > 1e-6]
        if all(_web_is_clean(part, *avoid) for part in chosen):
            break
    return chosen


def _join_tabs(
    box: BoxSpec, material, keep_clear, fill: float, hug: bool = False,
    web_width: float = BORE_WALL, wavy: bool = False, avoid: tuple = (),
) -> list[Polygon]:
    """Blends that carry ``material`` straight into any bin wall it reaches.

    ``material`` is the Bore's plan-view footprint and ``keep_clear`` the area
    that must stay open (every hole and its wavy wall). Each side of the usable
    floor that the material touches gets a tab running from ``fill`` inside the
    wall out through the bin's wavy inner face, so the sleeve fuses into the
    wall instead of stopping a hair short of it. Tabs never come within
    ``JOIN_SKIN`` of the bin's outside face, so the exterior stays as it was.

    ``hug`` (a Walls Only Bore whose bin is sized around it) also bridges a gap
    of up to one grid step: the bin can only grow in whole steps, so the sleeves
    are carried the rest of the way to the wall on every side.
    """
    whole = Zone.whole(box)
    limit = wavy_outer_polygon(box).buffer(-JOIN_SKIN)
    reach = box.wall_depth + 2.0 * WAVE_AMPLITUDE
    x0, y0, x1, y1 = material.bounds
    big = 1.0e3
    reachable = HUG_REACH if hug else JOIN_TOUCH
    sides = (
        (whole.x1 - x1,
         lambda d: shapely_box(whole.x1 - d - JOIN_BAND, -big, whole.x1 + big, big),
         lambda b, d: shapely_box(whole.x1 - d - fill, b[1], whole.x1 + reach, b[3])),
        (x0 - whole.x0,
         lambda d: shapely_box(-big, -big, whole.x0 + d + JOIN_BAND, big),
         lambda b, d: shapely_box(whole.x0 - reach, b[1], whole.x0 + d + fill, b[3])),
        (whole.y1 - y1,
         lambda d: shapely_box(-big, whole.y1 - d - JOIN_BAND, big, whole.y1 + big),
         lambda b, d: shapely_box(b[0], whole.y1 - d - fill, b[2], whole.y1 + reach)),
        (y0 - whole.y0,
         lambda d: shapely_box(-big, -big, big, whole.y0 + d + JOIN_BAND),
         lambda b, d: shapely_box(b[0], whole.y0 - reach, b[2], whole.y0 + d + fill)),
    )
    tabs: list[Polygon] = []
    if hug:
        # One narrow gap bridge per reachable wall and connected sleeve
        # cluster. Material already meeting the wall keeps the old local weld.
        for cluster in _polygons(material):
            x0, y0, x1, y1 = cluster.bounds
            walls = (
                (whole.x1 - x1, "right"), (x0 - whole.x0, "left"),
                (whole.y1 - y1, "back"), (y0 - whole.y0, "front"),
            )
            for gap, side in walls:
                if gap <= JOIN_TOUCH or gap > HUG_REACH + 1e-9:
                    continue
                if side in ("right", "left"):
                    edge = x1 if side == "right" else x0
                    segment = cluster.intersection(shapely_box(
                        edge - 0.01, y0 - 0.01, edge + 0.01, y1 + 0.01))
                    anchor = segment.representative_point().y if not segment.is_empty else cluster.representative_point().y
                    direction = 1 if side == "right" else -1
                    start = edge - direction * fill
                    end = (whole.x1 if direction > 0 else whole.x0) + direction * reach
                    # A straight web is one plain rectangle; only a wavy one is sampled.
                    steps = max(2, math.ceil(abs(end - start) / (WAVE_LENGTH / WAVE_SAMPLES_PER_CYCLE))) if wavy else 1
                    points = [(start + (end - start) * i / steps,
                               anchor + (wave_value(start + (end - start) * i / steps) - wave_value(start)) if wavy else anchor)
                              for i in range(steps + 1)]
                else:
                    edge = y1 if side == "back" else y0
                    segment = cluster.intersection(shapely_box(
                        x0 - 0.01, edge - 0.01, x1 + 0.01, edge + 0.01))
                    anchor = segment.representative_point().x if not segment.is_empty else cluster.representative_point().x
                    direction = 1 if side == "back" else -1
                    start = edge - direction * fill
                    end = (whole.y1 if direction > 0 else whole.y0) + direction * reach
                    steps = max(2, math.ceil(abs(end - start) / (WAVE_LENGTH / WAVE_SAMPLES_PER_CYCLE))) if wavy else 1
                    points = [(anchor + (wave_value(start + (end - start) * i / steps) - wave_value(start)) if wavy else anchor,
                               start + (end - start) * i / steps)
                              for i in range(steps + 1)]
                tabs.extend(_web_polygon(points, web_width, (material, keep_clear, limit, *avoid), limit, keep_clear))
    for gap, band, make in sides:
        if gap > reachable + 1e-9:
            continue
        if hug and gap > JOIN_TOUCH:
            continue
        span = gap if gap > JOIN_TOUCH else 0.0
        for piece in _polygons(material.intersection(band(span))):
            tab = make(piece.bounds, span).difference(keep_clear).intersection(limit)
            tabs.extend(part for part in _polygons(tab) if part.area > 1e-6)
    return tabs


def _tab_meshes(
    tabs: list[Polygon], height: float, base_z: float,
) -> list[trimesh.Trimesh]:
    meshes = []
    for tab in tabs:
        mesh = _extrude_polygon(tab, height)
        mesh.apply_translation((0.0, 0.0, base_z))
        meshes.append(mesh)
    return meshes


def _access_top_limit(box: BoxSpec) -> float | None:
    """Highest absolute Z an auto-sized Bore top may reach under Edge Mount's
    screwdriver-access passage, or ``None`` when there is no such passage."""
    from organizer_edge_mount import edge_mount_access_lowest_z
    try:
        lowest = edge_mount_access_lowest_z(box)
    except ValueError:
        return None      # an invalid Edge Mount is reported by the bin itself
    return None if lowest is None else lowest - ACCESS_CUTTER_CLEARANCE
