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
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from organizer_engine import BoxSpec, MIN_HEIGHT_ABOVE_BASE
from organizer_engine._specs import GRID_PITCHES, grid_label, lid_enabled, vertical_stack_enabled
from organizer_geometry import (
    _extrude_polygon,
    _loft_cavity,
    difference,
    intersection,
    translated,
    union,
)

# --------------------------------------------------------------------------- #
# Magnet pattern reference: Gridfinity Builder specification
# https://gridfinity-docs.securedev.codes/reference/specification.html
# profiles
# --------------------------------------------------------------------------- #
FOOT_HEIGHT = 4.75        # visible foot: z 0 to here, then the full-width shell
FLOOR_SKIN = 1.0          # floor left above the foot's top
MIN_GRID_BASE = FOOT_HEIGHT + FLOOR_SKIN   # 5.75
BODY_CORNER_RADIUS = 3.75
PERIMETER_GAP = 0.5
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
        raise ValueError(f"{grid_label(grid)} is not a Gridfinity grid") from None


# --------------------------------------------------------------------------- #
# stacking rim (female receiving profile) - Story 2970, spec section 1-2
# --------------------------------------------------------------------------- #
HEIGHT_UNIT = 7.0          # one Gridfinity height unit, foot bottom to nominal rim
RIM_OVERSHOOT = 0.5        # the cutter's mouth continues this far above the lip top
RIM_UNDERCUT = 0.1         # the lip solid and its cutter reach this far below the datum
# A cutter band never leaves less than this much wall at the outside face, so a
# narrow pitch cannot cut through its own bin (42 mm keeps 0.6, so is untouched).
RIM_MIN_WALL = 0.4

# 42 mm: the specification's table exactly, as (height ABOVE the nominal rim,
# opening width, corner radius): narrowest at the datum, widest at the lip top,
# so a foot nests its full depth. The theoretical tip is 4.4 high at 41.5 / R3.75;
# this reference trims 0.6 from it, so the lip ends at 3.8 above the rim.
RIM_TIP_THEORETICAL = (4.4, 41.5, 3.75)
RIM_TIP_TRIM = 0.6
_RIM_42 = ((0.0, 36.3, 1.15), (0.7, 37.7, 1.85), (2.5, 37.7, 1.85), (3.8, 40.3, 3.15))
# 21 mm: not a scaled 42. Each band is that pitch's own foot band (z, radius from
# RADIUS_SCHEDULE on the +/-6.5 corner centres) grown by a per-side clearance:
# 0.25 in the lower and straight bands, 0.35 at the top band (z 4.75).
_RIM_21_CLEARANCE = {0.0: 0.25, 0.8: 0.25, 2.6: 0.25, FOOT_HEIGHT: 0.35}


def _derived_rim_bands(grid: str, clearance: dict[float, float]) -> tuple:
    half = _profile(grid)["foot_half"]
    return tuple(
        (z, round(2.0 * (half + radius + clearance[z]), 9), round(radius + clearance[z], 9))
        for z, radius in _profile(grid)["radii"]
    )


RIM_PROFILES = {
    "gridfinity": _RIM_42,
    "gridfinity_half": _derived_rim_bands("gridfinity_half", _RIM_21_CLEARANCE),
}


def _rim_bands(grid: str) -> tuple:
    _profile(grid)
    return RIM_PROFILES[grid]


def rim_depth(grid: str) -> float:
    """How far the receiving lip stands above the nominal rim (the 7 mm-unit height)."""
    return _rim_bands(grid)[-1][0]


def _seat_descent(grid: str) -> float:
    """How far a foot sinks past the nominal datum before its chamfer lands.

    The rim opening is wider than the foot's bottom by the chamfer clearance; the
    foot's first band flares at a constant rate, so the descent follows from the
    profile data alone (42 mm: (36.3 - 35.6) / 2 = 0.35).
    """
    profile = _profile(grid)
    (z0, r0), (z1, r1) = profile["radii"][:2]
    flare = 2.0 * (r1 - r0) / (z1 - z0)           # foot width gained per mm of z
    bottom = 2.0 * (profile["foot_half"] + r0)    # foot width at z = 0
    return round((_rim_bands(grid)[0][1] - bottom) / flare, 9)


SEAT_DESCENT = {grid: _seat_descent(grid) for grid in PROFILES}


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
    return pitch * nx - PERIMETER_GAP, pitch * ny - PERIMETER_GAP


def effective_base(spec: BoxSpec, grid: str) -> float:
    """Cavity floor height: grid bins need room for the foot plus its skin."""
    if grid == "wavefinity":
        return spec.base_thickness
    return max(spec.base_thickness, MIN_GRID_BASE)


def side_opening_limits(spec: BoxSpec, grid: str) -> dict[str, float]:
    """Protected zones from this pitch's actual foot, floor and rim profiles."""
    profile = _profile(grid)
    return {"floor_z": effective_base(spec, grid),
            "corner_radius": profile["radii"][-1][1],
            "rim_depth": rim_depth(grid)}


def gridfinity_base_minimum(grid: str) -> float:
    return MIN_GRID_BASE if grid in PROFILES else 0.0


def nominal_height_units(spec: BoxSpec, grid: str) -> float:
    """Height in 7 mm units, foot bottom to rim, foot included."""
    _profile(grid)
    return spec.z / HEIGHT_UNIT


def exterior_height(spec: BoxSpec, grid: str) -> float:
    """Actual exterior height: for a grid design spec.z is foot bottom to rim top."""
    _profile(grid)
    return spec.z


def interior_depth(spec: BoxSpec, grid: str) -> float:
    """Usable cavity depth above the effective floor."""
    return spec.z - effective_base(spec, grid)


def assembled_stack_height(lower: BoxSpec, upper: BoxSpec, grid: str) -> float:
    """Two stacked grid bins: both nominal heights less the descent the lip allows.

    Each bin's height is foot bottom to nominal rim; the lip stands above that
    and is not counted, because the upper foot nests inside it.
    """
    _profile(grid)
    return lower.z + upper.z - SEAT_DESCENT[grid]


def assembled_lid_stack_height(lower: BoxSpec, upper: BoxSpec, grid: str) -> float:
    """Closed lower bin plus upper bin, seated in the lid's receiving lip.

    ``lower.z`` is the lidded total, whose top is the lip top. The foot enters
    the lip and bears on the plate, so it sinks the whole lip height and no
    further (the plate is solid below the datum).
    """
    _profile(grid)
    return lower.z + upper.z - rim_depth(grid)


def minimum_height_units(grid: str, stackable: bool, floor: float | None = None) -> int:
    """Fewest whole units a bin may be: 2 (14 mm). The stacking lip stands above the
    typed height, so Stackable adds no height requirement of its own.

    ``floor`` is kept for callers that pass it.
    """
    _profile(grid)
    return 2


def gridfinity_short_bin_message(grid: str) -> str:
    return f"A {grid_label(grid)} bin must be at least 14 mm tall (2 height units)."


def normalize_gridfinity_settings(box: BoxSpec, grid: str) -> BoxSpec:
    """Raise a grid design's base to the foot's minimum and enforce its height
    rules; wavefinity is untouched."""
    if grid == "wavefinity":
        return box
    _profile(grid)
    units = box.z / HEIGHT_UNIT
    stackable = vertical_stack_enabled(box)
    floor = effective_base(box, grid)
    needed = minimum_height_units(grid, stackable, floor)
    if lid_enabled(box):
        from organizer_features.stack import validate_grid_lid
        validate_grid_lid(box, grid)
        needed = max(2, needed)

    def too_short() -> ValueError:
        why = (
            "Gridfinity lid minimum: a lidded bin needs at least 2 height units"
            if lid_enabled(box) else "a bin is at least two height units"
        )
        return ValueError(
            f"a {grid_label(grid)} bin's Z must be at least {needed} height unit"
            f"{'s' if needed != 1 else ''} ({needed * HEIGHT_UNIT:g} mm): {why}; "
            f"{box.z:g} mm is too short"
        )

    if units < 2.0 - 1e-9:
        raise ValueError(gridfinity_short_bin_message(grid))
    if abs(units - round(units)) > 1e-9:
        below = math.floor(units) * HEIGHT_UNIT
        raise ValueError(
            f"a {grid_label(grid)} bin's Z must be a whole number of {HEIGHT_UNIT:g} mm height "
            f"units; {box.z:g} mm is {units:.3g} units - use {below:g} mm or "
            f"{below + HEIGHT_UNIT:g} mm"
        )
    if round(units) < needed:
        raise too_short()
    if box.base_thickness < MIN_GRID_BASE:
        return replace(box, base_thickness=MIN_GRID_BASE, standard_base=False)
    return box


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


def _footed_centres(spec: BoxSpec, grid: str) -> list[tuple[float, float]]:
    """Cells that carry a foot: every cell, or only the corner cells."""
    centres = _cell_centres(spec, grid)
    if not spec.corner_feet:
        return centres
    xs, ys = [c[0] for c in centres], [c[1] for c in centres]
    return [(x, y) for x, y in centres if x in (min(xs), max(xs)) and y in (min(ys), max(ys))]


def _foot_sections(grid: str) -> list[tuple[float, float]]:
    """The foot's radius schedule plus the 0.10 mm cap that overlaps the shell."""
    sections = list(_profile(grid)["radii"])
    sections.append((FOOT_HEIGHT + FOOT_CAP, sections[-1][1]))
    return sections


def foot_solid(spec: BoxSpec, grid: str) -> trimesh.Trimesh:
    """Every footed cell's foot, z 0 to 4.75, plus the 0.10 mm cap above it.

    The cap repeats the final section so the later union with the shell
    overlaps in volume; the foot's visible profile ends at z = 4.75. With
    Corner feet only the corner cells are footed.
    """
    profile = _profile(grid)
    sections = _foot_sections(grid)
    centres = _footed_centres(spec, grid)
    cells = [
        _lofted_cell(centre, profile["foot_half"], sections)
        for centre in centres
    ]
    feet = cells[0] if len(cells) == 1 else union(cells)
    if spec.magnet_holes == "6x2":
        if grid != "gridfinity":
            raise ValueError("Magnet holes require 42 mm Gridfinity")
        # Unconfirmed starting dimensions; Andrew's recorded fit print is the
        # only confirmation. Cap depth to preserve at least FLOOR_SKIN.
        depth = min(2.4, FOOT_HEIGHT - FLOOR_SKIN)
        cutters = []
        for x, y in centres:
            for dx in (-13.0, 13.0):
                for dy in (-13.0, 13.0):
                    cutter = trimesh.creation.cylinder(radius=3.25, height=depth + 0.1, sections=64)
                    cutters.append(translated(cutter, (x + dx, y + dy, (depth - 0.1) / 2)))
        feet = difference([feet, *cutters])
    return feet


def _single_volume(mesh: trimesh.Trimesh, what: str) -> None:
    if not (mesh.is_watertight and mesh.is_volume):
        raise RuntimeError(f"{what} is not a watertight solid")
    if len(mesh.split(only_watertight=False)) != 1:
        raise RuntimeError(f"{what} did not leave one connected printable solid")


def _polygons(shape) -> list[Polygon]:
    """The non-empty polygons of any shapely result."""
    parts = getattr(shape, "geoms", [shape])
    return [part for part in parts if part.geom_type == "Polygon" and not part.is_empty]


def _support_ribs(spec: BoxSpec, grid: str):
    """Wavy built-in support lines for a grid bin, one wall thick."""
    profile = _profile(grid)
    nx, ny = cell_counts(spec, grid)
    return wavy_support_lines(
        nx * profile["pitch"] / 2, ny * profile["pitch"] / 2, spec.wall,
    )


def wavy_support_lines(extent_x: float, extent_y: float, thickness: float):
    """Wavy built-in support lines in both directions over +/- the extents.

    The same global phase is used for every parallel line. The pitch of the
    waves is two support spacings; the lines continue through cell boundaries.
    """
    spacing, amplitude, step = 21.0, 6.0, 1.0
    lines = []
    for axis_extent, along_extent, swap in ((extent_x, extent_y, False), (extent_y, extent_x, True)):
        count = math.ceil(2 * axis_extent / spacing)
        for index in range(count + 1):
            offset = -axis_extent + index * spacing
            samples = math.ceil((2 * along_extent + 8) / step)
            points = []
            for n in range(samples + 1):
                along = -along_extent - 4 + n * (2 * along_extent + 8) / samples
                across = offset + amplitude * math.sin(2 * math.pi * along / 42.0)
                points.append((along, across) if swap else (across, along))
            lines.append(LineString(points).buffer(thickness / 2, cap_style=2, join_style=1))
    return unary_union(lines)


def _base_cutters_and_supports(spec: BoxSpec, grid: str):
    """Voids that lighten the base, and the built-in supports that print it.

    Hollow base opens every footed cell (and any base band above the feet),
    leaving the wavy ribs and magnet pads standing so the floor skin prints
    over them without slicer supports. Corner feet leaves the other cells
    with no foot; their floor is carried by the same ribs, trimmed to the
    standard foot outline at every height so they drop into a baseplate
    socket exactly as a foot would and never meet the plate's ridges.
    """
    profile = _profile(grid)
    half = profile["foot_half"]
    top = effective_base(spec, grid) - FLOOR_SKIN
    ribs = _support_ribs(spec, grid)
    footed = _footed_centres(spec, grid)
    open_cells = [centre for centre in _cell_centres(spec, grid) if centre not in footed]

    cutters = []
    if spec.hollow_base:
        kept = [ribs]
        if spec.magnet_holes == "6x2":
            for x, y in footed:
                for dx in (-13.0, 13.0):
                    for dy in (-13.0, 13.0):
                        kept.append(Point(x + dx, y + dy).buffer(3.25 + spec.wall, resolution=16))
        kept_meshes = [
            translated(_extrude_polygon(part, top + 0.2), (0, 0, -0.1))
            for part in _polygons(unary_union(kept))
        ]
        voids = []
        for centre in footed:
            rings, heights = [], []
            sections = [(-0.1, profile["radii"][0][1]), *profile["radii"]]
            if top > FOOT_HEIGHT:
                sections.append((FOOT_HEIGHT + min(0.05, top - FOOT_HEIGHT), profile["radii"][-1][1]))
            for z, radius in sections:
                inner_radius = max(0.01, radius - spec.wall)
                inner_half = half + radius - spec.wall - inner_radius
                if inner_half <= 0:
                    rings = []
                    break
                rings.append(_ring(centre, inner_half, inner_half, inner_radius))
                heights.append(z)
            # A foot no rib crosses stays solid: nothing would carry its floor.
            if rings and Polygon(rings[0]).intersects(ribs):
                voids.append(_loft_cavity(rings, heights))
        if top > FOOT_HEIGHT:
            # Inside the walls only, so the outer wall still joins every foot.
            band = _extrude_polygon(flat_cavity_polygon(spec, grid), top - FOOT_HEIGHT)
            voids.append(translated(band, (0, 0, FOOT_HEIGHT)))
        # Removing the kept footprint from each void makes each line fuse into
        # the unchanged profile and floor, without projecting into the sockets.
        cutters = [difference([void, *kept_meshes]) for void in voids]
        cutters = [cutter for cutter in cutters if len(cutter.vertices)]

    supports = []
    if open_cells:
        sections = _foot_sections(grid)
        height = sections[-1][0]
        rib_meshes = [
            translated(_extrude_polygon(part, height + 0.2), (0, 0, -0.1))
            for part in _polygons(ribs.intersection(flat_outer_polygon(spec, grid)))
        ]
        envelopes = [_lofted_cell(centre, half, sections) for centre in open_cells]
        if rib_meshes:
            trimmed = intersection([
                rib_meshes[0] if len(rib_meshes) == 1 else union(rib_meshes),
                envelopes[0] if len(envelopes) == 1 else union(envelopes),
            ])
            if len(trimmed.vertices):
                supports.append(trimmed)
    return cutters, supports


def gridfinity_body(spec: BoxSpec, grid: str) -> trimesh.Trimesh:
    """The bin shell: flat walls from z 4.75 up, per-cell feet below, one solid."""
    from organizer_features.side_openings import validate_side_openings
    validate_side_openings(spec, grid)
    if spec.edge_mount.active:
        raise ValueError("Edge Mount is unavailable on Gridfinity: it projects beyond the cell envelope.")
    floor = effective_base(spec, grid)
    if spec.z < floor + MIN_HEIGHT_ABOVE_BASE:
        raise ValueError(
            f"a {grid_label(grid)} bin needs Z of at least {floor + MIN_HEIGHT_ABOVE_BASE:g} mm "
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
    if spec.hollow_base or spec.corner_feet:
        cutters, supports = _base_cutters_and_supports(spec, grid)
        if cutters:
            fused = difference([fused, *cutters])
        if supports:
            fused = union([fused, *supports])
    body = difference([fused, cavity])
    _single_volume(body, "the Gridfinity body")
    return body


def rim_cutter(spec: BoxSpec, grid: str) -> trimesh.Trimesh:
    """The stacking lip's receiving void, opening at the nominal rim (``spec.z``).

    One loft per cell at pitch spacing: narrowest at the rim, widening upward
    through ``rim_depth`` of lip, then straight above it. Bands are the table in
    ``RIM_PROFILES``, narrowed only where a pitch's outer wall would otherwise
    fall under ``RIM_MIN_WALL``.
    """
    _profile(grid)
    return rim_socket_cutter(spec, grid, spec.z)


def rim_lip(spec: BoxSpec, grid: str, datum_z: float) -> trimesh.Trimesh:
    """The perimeter lip: material standing on ``datum_z`` for ``rim_depth``.

    The outline is the bin's outer shape less the whole-footprint mouth (no
    crossbars between cells); its inside is the receiving profile, narrow at the
    datum and wide at the top. It reaches ``RIM_UNDERCUT`` below the datum so the
    union with the wall below overlaps in volume.
    """
    depth = rim_depth(grid)
    ring = _extrude_polygon(
        flat_outer_polygon(spec, grid).difference(rim_mouth_polygon(spec, grid)),
        depth + RIM_UNDERCUT,
    )
    ring = translated(ring, (0.0, 0.0, datum_z - RIM_UNDERCUT))
    return difference([ring, rim_socket_cutter(spec, grid, datum_z)])


def rim_lip_support(spec: BoxSpec, grid: str, datum_z: float) -> trimesh.Trimesh | None:
    """A 45 degree fillet under the lip, so a bin's lip prints without supports.

    The lip's foot is wider than the wall it stands on, which would leave a
    flat ledge hanging inside the mouth. This fills below that ledge from the
    wall's inside face (at the bottom) to the lip's narrowest opening (at the
    lip's underside). None when the wall is already as wide as the lip.
    """
    profile = _profile(grid)
    nx, ny = cell_counts(spec, grid)
    ext_x, ext_y = nominal_extent(spec, grid)
    cavity_radius = max(BODY_CORNER_RADIUS - spec.wall, _MIN_CAVITY_RADIUS)
    cavity = (ext_x / 2.0 - spec.wall - cavity_radius,
              ext_y / 2.0 - spec.wall - cavity_radius, cavity_radius)
    mouth_radius = _rim_bands(grid)[0][1] / 2.0 - profile["foot_half"]
    mouth = (profile["foot_half"] + (nx - 1) * profile["pitch"] / 2.0,
             profile["foot_half"] + (ny - 1) * profile["pitch"] / 2.0, mouth_radius)
    reach = max(cavity[0] + cavity[2] - mouth[0] - mouth[2],
                cavity[1] + cavity[2] - mouth[1] - mouth[2])
    if reach <= 1e-6:
        return None
    top = datum_z - RIM_UNDERCUT
    bottom = top - reach

    def ring_at(t: float) -> np.ndarray:
        half_x, half_y, radius = (c + t * (m - c) for c, m in zip(cavity, mouth))
        return _ring((0.0, 0.0), half_x, half_y, radius)

    # The sloped face runs 0.1 mm past both ends so no cut face is coplanar.
    over = 0.1 / reach
    cutter = _loft_cavity([ring_at(-over), ring_at(1.0 + over)], [bottom - 0.1, top + 0.1])
    block = _extrude_polygon(flat_outer_polygon(spec, grid), reach + 0.05)
    return difference([translated(block, (0.0, 0.0, bottom)), cutter])


def rim_mouth_polygon(spec: BoxSpec, grid: str) -> Polygon:
    """Whole-footprint outline inside the rim's narrowest receiving band."""
    profile = _profile(grid)
    nx, ny = cell_counts(spec, grid)
    radius = _rim_bands(grid)[0][1] / 2.0 - profile["foot_half"]
    return Polygon(_ring(
        (0.0, 0.0),
        profile["foot_half"] + (nx - 1) * profile["pitch"] / 2.0,
        profile["foot_half"] + (ny - 1) * profile["pitch"] / 2.0,
        radius,
    ))


def rim_socket_cutter(spec: BoxSpec, grid: str, opening_z: float) -> trimesh.Trimesh:
    """Rim-profile void, right way up, opening at ``opening_z``: a body's nominal
    rim or a lid's plate top.

    Band z is height above ``opening_z``. The cutter starts ``RIM_UNDERCUT``
    below it at the narrowest width, so it never leaves a coplanar face.
    """
    profile = _profile(grid)
    bands = _rim_bands(grid)
    half = profile["foot_half"]
    widest = profile["pitch"] - 0.5 - 2.0 * RIM_MIN_WALL
    sections = [
        (opening_z + height, min(width, widest) / 2.0 - half)
        for height, width, _radius in bands
    ]
    sections.insert(0, (opening_z - RIM_UNDERCUT, sections[0][1]))
    sections.append((sections[-1][0] + RIM_OVERSHOOT, sections[-1][1]))
    cells = [_lofted_cell(centre, half, sections) for centre in _cell_centres(spec, grid)]
    return cells[0] if len(cells) == 1 else union(cells)


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


# Container floors (Story 2974). PROVISIONAL until Stage 1 fit prints settle it.
EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM = 0.35
CONTAINER_FLOOR_SKIN_MM = 0.8


def socket_surface_z(grid: str) -> float:
    """Standalone plate surface; the 42 mm cutter has 0.1 mm overshoot."""
    return 5.0 if _profile(grid)["pitch"] == 42.0 else FOOT_HEIGHT


def floor_pocket_depth(grid: str) -> float:
    return socket_surface_z(grid) - _profile(grid)["socket"][0][0]


def minimum_floor_build(grid: str, underside_depth: float = 0.0) -> float:
    """Pocket depth plus printable skin above any underside construction."""
    return floor_pocket_depth(grid) + CONTAINER_FLOOR_SKIN_MM + underside_depth


def validate_floor_build(grid: str, thickness: float, underside_depth: float = 0.0) -> None:
    minimum = minimum_floor_build(grid, underside_depth)
    if not math.isfinite(thickness) or thickness + 1e-9 < minimum:
        raise ValueError(
            f"Gridfinity minimum floor build: {minimum:g} mm for {grid_label(grid)} "
            f"({floor_pocket_depth(grid):g} mm pocket + "
            f"{CONTAINER_FLOOR_SKIN_MM:g} mm floor skin + "
            f"{underside_depth:g} mm underside recess); got {thickness:g} mm"
        )


def floor_cell_counts(grid: str, x: float, y: float) -> tuple[int, int]:
    pitch = _profile(grid)["pitch"]
    counts = tuple(round(value / pitch) for value in (x, y))
    if any(count < 1 or not math.isclose(value, count * pitch, abs_tol=1e-8)
           for value, count in zip((x, y), counts)):
        raise ValueError(f"Gridfinity floor area must use whole {pitch:g} mm cells")
    return counts


def floor_pocket_cutter(grid: str, nx: int, ny: int, floor_z: float) -> trimesh.Trimesh:
    """Shared socket field, with the plate's surface at the container floor.

    Translation preserves every pitch's own seat and relief. The 21 mm mouth
    ends at its surface, so extend only its last section above the cavity cut
    to avoid a coplanar boolean seam; no receiving band is changed.
    """
    cutter = socket_cutter(grid, nx, ny)
    if grid == "gridfinity_half":
        profile = _profile(grid)
        half, pitch = profile["foot_half"], profile["pitch"]
        z, width = profile["socket"][-1]
        caps = [_lofted_cell(
            ((i - (nx - 1) / 2) * pitch, (j - (ny - 1) / 2) * pitch), half,
            [(z - 0.001, width / 2 - half), (z + 0.1, width / 2 - half)],
        ) for i in range(nx) for j in range(ny)]
        cutter = union([cutter, *caps])
    return translated(cutter, (0, 0, floor_z - socket_surface_z(grid)))


def measured_seated_lift(value: object = None) -> float | None:
    """Foot-bottom lift measured on the external plate, never plate thickness.

    None means explicitly unverified. Zero is a valid recorded measurement.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("External plate seated lift must be a measured number in mm or unverified")
    if not math.isfinite(value) or value < 0:
        raise ValueError("External plate seated lift must be finite and non-negative")
    return float(value)


def container_floor_record(grid: str, built_in_grid: str, x: float, y: float,
                           seated_lift_mm: object = None) -> dict:
    """Nominal layout area and actual rectangular cavity are distinct datums.

    Space grid remains the pitch identity. Existing schema spells no built-in
    grid as built_in_grid='none'; floor_grid=None records that flat floor.
    Height *fit* is left unverified for Story 2973 even when lift is measured.
    """
    if grid not in PROFILES:
        return {}
    floor_cell_counts(grid, x, y)
    external = built_in_grid == "none"
    lift = measured_seated_lift(seated_lift_mm)
    clearance = EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM if external else 0.0
    return {
        "floor_grid": None if external else grid,
        "floor_mode": "external_plate" if external else "built_in",
        "nominal_grid_mm": [x, y],
        "physical_cavity_mm": [x + 2 * clearance, y + 2 * clearance],
        "external_plate_clearance_per_side_mm": clearance,
        "external_plate_clearance_status": "provisional" if external else "not_applicable",
        "seated_lift_mm": lift,
        "seated_lift_status": ("measured" if lift is not None else "unverified") if external else "not_applicable",
        "height_fit_verified": False,
    }


def container_cavity_polygon(grid: str, built_in_grid: str, x: float, y: float) -> Polygon:
    from shapely.geometry import box
    cx, cy = container_floor_record(grid, built_in_grid, x, y)["physical_cavity_mm"]
    return box(-cx / 2, -cy / 2, cx / 2, cy / 2)
