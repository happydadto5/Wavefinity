"""Gridfinity bin bases - a compatible 42 mm foot and an independent 21 mm foot.

Both profiles live here as data (Story 2967, ``gridfinity-stage1-spec.md``
sections 1-2), plus the body builder that turns a ``BoxSpec`` into a flat-walled
shell standing on per-cell feet.  The two pitches share the radius schedule but
not the corner-centre spacing, which is what makes 21 mm an independent profile
and not a scaled copy of 42 mm.

Everything below the foot's visible top (z = 4.75) is the separate per-cell
foot sections only; the full-width shell starts at that plane and never lower,
so it cannot fill the under-foot gutters of a multi-cell bin.
"""

from __future__ import annotations

import math
from dataclasses import replace

import numpy as np
import trimesh
from shapely.geometry import Polygon

from organizer_engine import BoxSpec, MIN_HEIGHT_ABOVE_BASE
from organizer_engine._specs import GRID_PITCHES
from organizer_geometry import (
    _extrude_polygon,
    _loft_cavity,
    difference,
    translated,
    union,
)

# --------------------------------------------------------------------------- #
# profiles
# --------------------------------------------------------------------------- #
FOOT_HEIGHT = 4.75        # visible foot: z 0 to here, then the full-width shell
FLOOR_SKIN = 1.0          # floor left above the foot's top
MIN_GRID_BASE = FOOT_HEIGHT + FLOOR_SKIN   # 5.75
BODY_CORNER_RADIUS = 3.75
# The foot's last section is repeated this far into the shell so the foot/shell
# union is a positive-volume overlap, never a face-only contact. It is not an
# exposed continuation of the foot.
FOOT_CAP = 0.10
ARC_SEGMENTS = 16         # per 90 degree corner
_MIN_CAVITY_RADIUS = 0.2  # floor for the cavity corner radius on thick walls

# (z, corner radius): the same schedule for both pitches.
RADIUS_SCHEDULE = ((0.0, 0.8), (0.8, 1.6), (2.6, 1.6), (FOOT_HEIGHT, BODY_CORNER_RADIUS))

PROFILES = {
    "gridfinity": {
        "pitch": GRID_PITCHES["gridfinity"],
        "foot_half": 17.0,        # corner-centre half-square
        "radii": RADIUS_SCHEDULE,
        # Baseplate socket opening widths by z. The foot seats at ``seat_z``:
        # the 0.35 vertical relief below it is part of the cutter. The last
        # point continues the 45 degree chamfer 0.1 mm past the 5 mm plate so
        # neighbouring cells overlap in volume instead of touching on an edge.
        "seat_z": 0.35,
        "socket": ((0.0, 36.3), (0.35, 36.3), (1.05, 37.7), (2.85, 37.7),
                   (5.0, 42.0), (5.1, 42.2)),
    },
    "gridfinity_half": {
        "pitch": GRID_PITCHES["gridfinity_half"],
        "foot_half": 6.5,
        "radii": RADIUS_SCHEDULE,
        # Pocket radii 0.8 -> 1.85 / 1.85 / 1.85 -> 4.1 over z -0.25 / 0.8 /
        # 2.6 / 4.75 on the same +/-6.5 centres, as widths. The foot seats at 0.
        "seat_z": 0.0,
        "socket": ((-0.25, 14.6), (0.8, 16.7), (2.6, 16.7), (FOOT_HEIGHT, 21.2)),
    },
}


def _profile(grid: str) -> dict:
    try:
        return PROFILES[grid]
    except KeyError:
        raise ValueError(f"{grid!r} is not a Gridfinity grid") from None


def cell_counts(spec: BoxSpec, grid: str) -> tuple[int, int]:
    """Whole cells along X and Y."""
    pitch = _profile(grid)["pitch"]
    counts = (round(spec.x / pitch), round(spec.y / pitch))
    if min(counts) < 1:
        raise ValueError(
            f"a {spec.x:g} x {spec.y:g} mm bin is smaller than one {pitch:g} mm "
            "Gridfinity cell"
        )
    return counts


def nominal_extent(spec: BoxSpec, grid: str) -> tuple[float, float]:
    """Whole-bin XY: one 0.5 mm perimeter gap in total, not per cell."""
    pitch = _profile(grid)["pitch"]
    nx, ny = cell_counts(spec, grid)
    return pitch * nx - 0.5, pitch * ny - 0.5


def effective_base(spec: BoxSpec, grid: str) -> float:
    """Cavity floor height: grid bins need room for the foot plus its skin."""
    if grid == "wavefinity":
        return spec.base_thickness
    return max(spec.base_thickness, MIN_GRID_BASE)


def gridfinity_base_minimum(grid: str) -> float:
    return MIN_GRID_BASE if grid in PROFILES else 0.0


def normalize_gridfinity_settings(box: BoxSpec, grid: str) -> BoxSpec:
    """Raise a grid design's base to the foot's minimum; wavefinity is untouched."""
    if grid == "wavefinity":
        return box
    _profile(grid)
    if box.base_thickness >= MIN_GRID_BASE:
        return box
    return replace(box, base_thickness=MIN_GRID_BASE, standard_base=False)


# --------------------------------------------------------------------------- #
# outlines
# --------------------------------------------------------------------------- #
def _ring(
    centre: tuple[float, float], half_x: float, half_y: float, radius: float,
) -> np.ndarray:
    """Counter-clockwise rounded rectangle: corner centres at ``centre`` +/-
    (``half_x``, ``half_y``), corners of ``radius``.

    Corner centres are formed the same way for every caller, so concentric
    outlines (the foot's top section and the shell) share bit-identical
    vertices.
    """
    points: list[tuple[float, float]] = []
    for sx, sy, start in ((1.0, 1.0, 0.0), (-1.0, 1.0, 90.0),
                          (-1.0, -1.0, 180.0), (1.0, -1.0, 270.0)):
        corner_x = centre[0] + sx * half_x
        corner_y = centre[1] + sy * half_y
        for step in range(ARC_SEGMENTS + 1):
            angle = math.radians(start + 90.0 * step / ARC_SEGMENTS)
            points.append((
                corner_x + radius * math.cos(angle),
                corner_y + radius * math.sin(angle),
            ))
    return np.asarray(points, dtype=float)


def _radius_at(grid: str, z: float) -> float:
    schedule = _profile(grid)["radii"]
    if z <= schedule[0][0]:
        return schedule[0][1]
    for (z0, r0), (z1, r1) in zip(schedule, schedule[1:]):
        if z <= z1:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return schedule[-1][1]


def foot_polygon(grid: str, z: float) -> Polygon:
    """One cell's foot cross-section at height ``z``, centred on the cell."""
    half = _profile(grid)["foot_half"]
    return Polygon(_ring((0.0, 0.0), half, half, _radius_at(grid, z)))


def flat_outer_polygon(spec: BoxSpec, grid: str) -> Polygon:
    """The flat full-height outline at the nominal extent, corner radius 3.75."""
    ext_x, ext_y = nominal_extent(spec, grid)
    return Polygon(_ring(
        (0.0, 0.0), ext_x / 2.0 - BODY_CORNER_RADIUS, ext_y / 2.0 - BODY_CORNER_RADIUS,
        BODY_CORNER_RADIUS,
    ))


def flat_cavity_polygon(spec: BoxSpec, grid: str) -> Polygon:
    """The nominal extent inset by the wall on every side."""
    ext_x, ext_y = nominal_extent(spec, grid)
    radius = max(BODY_CORNER_RADIUS - spec.wall, _MIN_CAVITY_RADIUS)
    half_x = ext_x / 2.0 - spec.wall - radius
    half_y = ext_y / 2.0 - spec.wall - radius
    if half_x <= 1e-6 or half_y <= 1e-6:
        raise ValueError("box is too small for its wall thickness")
    return Polygon(_ring((0.0, 0.0), half_x, half_y, radius))


def _cell_centres(spec: BoxSpec, grid: str) -> list[tuple[float, float]]:
    pitch = _profile(grid)["pitch"]
    nx, ny = cell_counts(spec, grid)
    return [
        ((i - (nx - 1) / 2.0) * pitch, (j - (ny - 1) / 2.0) * pitch)
        for i in range(nx) for j in range(ny)
    ]


# --------------------------------------------------------------------------- #
# solids
# --------------------------------------------------------------------------- #
def _lofted_cell(
    centre: tuple[float, float], half: float, sections: list[tuple[float, float]],
) -> trimesh.Trimesh:
    rings = [_ring(centre, half, half, radius) for _z, radius in sections]
    return _loft_cavity(rings, [z for z, _radius in sections])


def foot_solid(spec: BoxSpec, grid: str) -> trimesh.Trimesh:
    """Every cell's foot, z 0 to 4.75, plus the 0.10 mm cap above it.

    The cap repeats the final section so the later union with the shell
    overlaps in volume; the foot's visible profile ends at z = 4.75.
    """
    profile = _profile(grid)
    sections = list(profile["radii"])
    sections.append((FOOT_HEIGHT + FOOT_CAP, sections[-1][1]))
    cells = [
        _lofted_cell(centre, profile["foot_half"], sections)
        for centre in _cell_centres(spec, grid)
    ]
    return cells[0] if len(cells) == 1 else union(cells)


def _single_volume(mesh: trimesh.Trimesh, what: str) -> None:
    if not (mesh.is_watertight and mesh.is_volume):
        raise RuntimeError(f"{what} is not a watertight solid")
    if len(mesh.split(only_watertight=False)) != 1:
        raise RuntimeError(f"{what} did not leave one connected printable solid")


def gridfinity_body(spec: BoxSpec, grid: str) -> trimesh.Trimesh:
    """The bin shell: flat walls from z 4.75 up, per-cell feet below, one solid."""
    floor = effective_base(spec, grid)
    if spec.z < floor + MIN_HEIGHT_ABOVE_BASE:
        raise ValueError(
            f"a {grid} bin needs Z of at least {floor + MIN_HEIGHT_ABOVE_BASE:g} mm "
            f"({floor:g} mm for the feet and floor)"
        )
    # Never from z = 0: a full-width shell down there would bury the foot.
    shell = _extrude_polygon(flat_outer_polygon(spec, grid), spec.z - FOOT_HEIGHT)
    shell = translated(shell, (0.0, 0.0, FOOT_HEIGHT))
    feet = foot_solid(spec, grid)
    cavity = _extrude_polygon(flat_cavity_polygon(spec, grid), spec.z - floor + 1.0)
    cavity = translated(cavity, (0.0, 0.0, floor))
    fused = union([shell, feet])
    _single_volume(fused, "the foot and shell union")
    body = difference([fused, cavity])
    _single_volume(body, "the Gridfinity body")
    return body


def socket_cutter(grid: str, nx: int, ny: int) -> trimesh.Trimesh:
    """The baseplate socket solid for ``nx`` x ``ny`` cells at the pitch.

    Not wired to any product surface yet: it serves fit tests and the later
    baseplate stories. Its z is the profile's own (the 42 mm foot seats at
    ``seat_z`` 0.35; the 21 mm pocket starts 0.25 below the plate).
    """
    profile = _profile(grid)
    pitch, half = profile["pitch"], profile["foot_half"]
    sections = [(z, width / 2.0 - half) for z, width in profile["socket"]]
    cells = [
        _lofted_cell(
            ((i - (nx - 1) / 2.0) * pitch, (j - (ny - 1) / 2.0) * pitch), half, sections,
        )
        for i in range(nx) for j in range(ny)
    ]
    return cells[0] if len(cells) == 1 else union(cells)
