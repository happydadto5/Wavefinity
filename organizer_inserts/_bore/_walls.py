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


# Wall-join geometry lives in the shared module now; re-exported here so
# existing ``from ._walls import _join_tabs`` call sites keep working.
from .._walljoin import (
    _join_tabs,
    _polygons,
    _ring_points,
    _tab_meshes,
    _web_is_clean,
    _web_polygon,
    WEB_COINCIDENCE_TOL,
    WEB_WIDTH_NUDGES,)


def _access_top_limit(box: BoxSpec) -> float | None:
    """Highest absolute Z an auto-sized Bore top may reach under Edge Mount's
    screwdriver-access passage, or ``None`` when there is no such passage."""
    from organizer_edge_mount import edge_mount_access_lowest_z
    try:
        lowest = edge_mount_access_lowest_z(box)
    except ValueError:
        return None      # an invalid Edge Mount is reported by the bin itself
    return None if lowest is None else lowest - ACCESS_CUTTER_CLEARANCE
