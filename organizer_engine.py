"""Parametric geometry engine for the wavy-wall drawer organizer system.

All dimensions are millimetres.  This module is the single source of truth for
the browser app, command-line tools, fit sampler, and automated tests.

Design summary
--------------
* Boxes tile on a plain ``x`` by ``y`` grid.  Their solid outline is smaller
  than that pitch by ``WAVE_MATING_GAP`` so neighbouring wavy walls interlock
  with a constant gap.
* The wave is a fixed-pitch sine: ``WAVE_LENGTH`` mm per full cycle (out and
  back) and ``WAVE_AMPLITUDE`` mm of deviation each way.  It runs at full
  amplitude the whole length of every wall, straight into the corners; there
  is no corner blend.  Corners are a short chamfer rounded to
  ``CORNER_FILLET``.
* One connector: the **side connector**, a staple that drops over the seam
  between two boxes.  There is no corner connector.
* Each wall carries small chamfered **lock bumps** on its interior face; the
  connector arms have matching notches so the clip locks in.  Every bump and
  notch face is chamfered at 45 degrees or shallower, so both parts print
  without supports.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Iterable

import lib3mf
import numpy as np
import trimesh
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.affinity import rotate as rotate_polygon, translate as translate_polygon
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from shapely.ops import unary_union


# --------------------------------------------------------------------------- #
# wave and box constants
# --------------------------------------------------------------------------- #
WAVE_LENGTH = 4.0        # one full cycle: 2 mm out, 2 mm back
WAVE_AMPLITUDE = 0.4     # deviation each way (0.8 mm peak to peak)
WAVE_MATING_GAP = 0.25   # gap left between two neighbouring walls
SAMPLES_PER_MM = 16

# Box X and Y must be whole multiples of this.
#
# The wave is anchored at each wall's centre, which makes every wall symmetric
# and every box the same whichever way round you turn it.  The price is that a
# box's centre must land on the wave lattice.  Pack boxes edge to edge and a
# box of size S has its centre half a size in from its edge, so sizes must be
# multiples of 2 * WAVE_LENGTH for every centre to land on a multiple of
# WAVE_LENGTH.  Once they do, ``cos(2*pi*(y - centre)/WAVE_LENGTH)`` collapses
# to ``cos(2*pi*y/WAVE_LENGTH)``: the wave stops depending on which box it
# belongs to and becomes one global function of position.  Any two walls that
# meet then nest, whatever the two boxes measure.
#
# Off-grid sizes still tile with their own clones, but collide the moment they
# meet a box of a different size, so they are rejected.
GRID_PITCH = 2.0 * WAVE_LENGTH   # 8.0
MIN_BOX_SIZE = GRID_PITCH        # 8.0 - one grid step
BASE_UNIT = GRID_PITCH           # one unit is one grid step, so sizes are whole
                                 # numbers of units: 1, 2, 3 ... = 8, 16, 24 mm

# A wall shorter than a connector plus its corner insets simply cannot take one,
# and a wall too short to seat a lock bump clear of both corners gets none.  Both
# are per-wall facts, not reasons to reject the box: a 1-unit-wide bin is a
# perfectly good filler that joins on its long sides only.  ``make_side_connector``
# says so plainly if you ask for a connector that will not fit.

DEFAULT_WALL = 0.8
DEFAULT_CORNER_FILLET = 0.6   # rounding applied where two wavy walls meet
CORNER_INSET = 1.0            # walls stop this far short of the nominal corner
# Locked in after the physical tolerance print: these are no longer tuning
# knobs, they are the connector's specification.
LOCKED_TOLERANCE = 0.02       # chosen from the printed 5-clip fit plate
LOCKED_CONNECTOR_HEIGHT = 9.6
LOCKED_CONNECTOR_LENGTH = 12.0

# The smallest box that can take a connector on both sides.  A 1-unit side is
# still legal - it just joins on its long sides only.
MIN_JOINABLE_SIZE = (
    math.ceil(
        (2.0 * (LOCKED_CONNECTOR_LENGTH / 2.0 + CORNER_INSET) + WAVE_MATING_GAP - 1e-9)
        / GRID_PITCH
    )
    * GRID_PITCH
)

DEFAULT_CONNECTOR_HEIGHT = LOCKED_CONNECTOR_HEIGHT
DEFAULT_CAP_THICKNESS = 1.2
DEFAULT_ARM_THICKNESS = 1.0   # two 0.5 mm perimeters
DEFAULT_SIDE_LENGTH = LOCKED_CONNECTOR_LENGTH

# --------------------------------------------------------------------------- #
# lock detent: chamfered bumps inside the wall, notches in the connector arms
# --------------------------------------------------------------------------- #
LOCK_PROTRUSION = 0.35    # how far a bump stands proud of the interior face
LOCK_FLAT = 0.30          # straight band between the two chamfers
LOCK_CHAMFER = 0.35       # 45 degree rise of each chamfer (== protrusion)
LOCK_RUN = 1.2            # length of one bump along the wall
LOCK_SPACING = WAVE_LENGTH / 2.0   # a bump on every extremum, crest and trough
LOCK_CORNER_CLEAR = 2.0   # keep bumps this far short of the wall's tangent, so
                          # the bumps on two walls cannot meet at their corner
LOCK_TOP_BELOW_RIM = 4.0  # top of the upper chamfer, measured down from the rim
LOCK_EMBED = 0.60         # bump/notch roots sink this far into their own wall
LOCK_NOTCH_CLEARANCE = 0.12

# --------------------------------------------------------------------------- #
# floor label: text sunk into the inside floor.  The box gets a pocket and the
# label is the solid that fills it flush, exported as its own object so Bambu
# Studio can print it in a second colour
# --------------------------------------------------------------------------- #
TEXT_CAP_HEIGHT_IDEAL = 10.0   # letter height we want
TEXT_CAP_HEIGHT_MIN = 7.0      # letter height we will shrink to, but no further
TEXT_DEPTH = 0.4               # how deep the label is sunk into the floor,
                               # leaving DEFAULT_WALL - TEXT_DEPTH beneath it
TEXT_MARGIN = 1.0              # clear space between the label and the cavity wall
TEXT_FONT_FAMILY = "DejaVu Sans"
TEXT_FONT_WEIGHT = "bold"

# A rim label is deliberately a fixed physical feature rather than an
# automatically-scaled floor label.  The 7 mm ledge leaves one millimetre of
# breathing room either side of the requested 5 mm letters.  Its underside
# rises 7 mm over the same 7 mm run: exactly 45 degrees and printable without
# support.
TOP_LABEL_LEDGE_DEPTH = 7.0
TOP_LABEL_CAP_HEIGHT = 5.0
TOP_LABEL_MARGIN = 1.0
SCOOP_HEIGHT_FRACTION = 0.5
SCOOP_FLOOR_TOLERANCE = 0.4   # a scoop lower than this counts as flat floor
SCOOP_CURVE_SEGMENTS = 32



@dataclass(frozen=True)
class BoxSpec:
    x: float = MIN_JOINABLE_SIZE
    y: float = MIN_JOINABLE_SIZE
    z: float = 40.0
    wall: float = DEFAULT_WALL
    corner_fillet: float = DEFAULT_CORNER_FILLET
    flat_inside: float = 0.0   # mm of flat-walled band rising from the floor

    def __post_init__(self) -> None:
        values = {
            "X": self.x, "Y": self.y, "Z": self.z,
            "wall": self.wall, "corner fillet": self.corner_fillet,
        }
        for name, value in values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if self.z <= self.wall:
            raise ValueError("box Z must be greater than the wall/floor thickness")
        for name, value in (("X", self.x), ("Y", self.y)):
            if value < MIN_BOX_SIZE - 1e-9:
                raise ValueError(
                    f"box {name} must be at least {MIN_BOX_SIZE:.0f} mm"
                )
            units = value / GRID_PITCH
            if abs(units - round(units)) > 1e-6:
                nearest = max(round(units), MIN_BOX_SIZE / GRID_PITCH)
                raise ValueError(
                    f"box {name} must be a whole multiple of the {GRID_PITCH:.0f} mm "
                    f"grid so boxes of different sizes still interlock; "
                    f"{value:g} mm is not - try {nearest * GRID_PITCH:.0f} mm"
                )
        if not 0.0 <= self.flat_inside <= 1.0:
            raise ValueError("flat inside must be between 0 and 1 mm")
        if self.flat_inside > 0.0 and self.wall + self.flat_inside >= self.z:
            raise ValueError("box is too shallow for a flat-walled band")
        if self.wall_depth * 2.0 >= min(self.x, self.y) - WAVE_MATING_GAP:
            raise ValueError("wall thickness leaves no cavity")

    @property
    def half_x(self) -> float:
        return self.x / 2.0 - WAVE_MATING_GAP / 2.0

    @property
    def half_y(self) -> float:
        return self.y / 2.0 - WAVE_MATING_GAP / 2.0

    @property
    def units(self) -> tuple[int, int]:
        """Size in whole units, e.g. ``(2, 6)`` for 16 x 48 mm.

        One unit is one grid step, so every legal size is a whole number of
        units and no decimals are needed.
        """
        return round(self.x / BASE_UNIT), round(self.y / BASE_UNIT)

    @property
    def grid_steps(self) -> tuple[int, int]:
        """Size in whole ``GRID_PITCH`` units, e.g. ``(3, 9)`` for 24 x 72 mm."""
        return round(self.x / GRID_PITCH), round(self.y / GRID_PITCH)

    @property
    def footprint(self) -> tuple[float, float]:
        """What the box occupies on the drawer grid - its nominal X and Y."""
        return self.x, self.y

    @property
    def outside_extent(self) -> tuple[float, float]:
        """Real outside size, crest to crest, which the wave pushes past the
        grid footprint by one amplitude each side."""
        span = 2.0 * WAVE_AMPLITUDE - WAVE_MATING_GAP
        return self.x + span, self.y + span

    @property
    def usable_inside(self) -> tuple[float, float]:
        """Largest axis-aligned rectangle that fits the cavity.

        Both faces of a wall carry the same wave, so the cavity is a channel of
        constant width that weaves from side to side.  A straight-sided object
        has to clear the wave's full swing, which costs one amplitude at each
        end on top of the two walls.
        """
        clear_x = 2.0 * (self.half_x - self.wall_depth) - 2.0 * WAVE_AMPLITUDE
        clear_y = 2.0 * (self.half_y - self.wall_depth) - 2.0 * WAVE_AMPLITUDE
        return clear_x, clear_y

    @property
    def wall_depth(self) -> float:
        """Wall thickness measured along the axis, not along the surface normal.

        Shifting the outline by this much keeps the true perpendicular wall at
        or above ``wall`` everywhere on the wave.
        """
        return self.wall * math.sqrt(1.0 + max_wave_slope() ** 2)


@dataclass(frozen=True)
class ConnectorSpec:
    tolerance: float = LOCKED_TOLERANCE
    height: float = DEFAULT_CONNECTOR_HEIGHT
    cap_thickness: float = DEFAULT_CAP_THICKNESS
    arm_thickness: float = DEFAULT_ARM_THICKNESS

    def __post_init__(self) -> None:
        values = {
            "tolerance": self.tolerance, "height": self.height,
            "cap thickness": self.cap_thickness, "arm thickness": self.arm_thickness,
        }
        for name, value in values.items():
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite")
        if self.tolerance < 0 or self.tolerance > 1.0:
            raise ValueError("tolerance must be between 0.0 and 1.0 mm")
        if self.cap_thickness <= 0:
            raise ValueError("cap thickness must be positive")
        if self.height <= self.cap_thickness:
            raise ValueError("connector height must exceed its cap thickness")
        if self.arm_thickness <= LOCK_PROTRUSION + LOCK_NOTCH_CLEARANCE + 0.3:
            raise ValueError("arm thickness leaves too little material at the notch")

    @property
    def arm_depth(self) -> float:
        """How far the arms reach below the underside of the cap."""
        return self.height - self.cap_thickness


# --------------------------------------------------------------------------- #
# the wave
# --------------------------------------------------------------------------- #
def max_wave_slope() -> float:
    return WAVE_AMPLITUDE * 2.0 * math.pi / WAVE_LENGTH


def wave_value(coordinate: float) -> float:
    """Fixed-pitch wave, measured from the centre of the wall it runs along.

    The wave is **odd** about the wall centre - it leaves it at zero and comes
    back inverted - and that is what lets a box be turned round.  Spin a box
    180 degrees and its +X wall lands where its -X wall was; an odd wave means
    the two carry the same shape, so the turned box still nests with its
    neighbours.  An even wave would put a crest against a crest instead.

    Because the phase depends only on the distance from the wall centre, two
    boxes interlock exactly when their centres are a whole number of cycles
    apart along that wall.  ``GRID_PITCH`` guarantees it.
    """
    return WAVE_AMPLITUDE * math.sin(2.0 * math.pi * coordinate / WAVE_LENGTH)


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
) -> list[tuple[float, float]]:
    """Counter-clockwise outline: four wavy walls joined by corner chords.

    ``half_*`` place the faces; ``tangent_*`` say where the walls stop short of
    the nominal corner and always come from the outer profile, so an inner
    outline stays exactly parallel to the outer one.  ``points_per_cycle``
    overrides the sampling with a *density* rather than a fixed total, so a
    long wall and a short one on the same box come out equally smooth - the
    preview uses this to get a coarse ring it can draw quickly without a
    fixed point budget starving whichever pair of walls is longer.
    """
    if points_per_cycle is None:
        count_x = _sample_count(2.0 * tangent_x)
        count_y = _sample_count(2.0 * tangent_y)
    else:
        count_x = max(4, round(points_per_cycle * 2.0 * tangent_x / WAVE_LENGTH))
        count_y = max(4, round(points_per_cycle * 2.0 * tangent_y / WAVE_LENGTH))
    xs = np.linspace(-tangent_x, tangent_x, count_x)
    ys = np.linspace(-tangent_y, tangent_y, count_y)
    points: list[tuple[float, float]] = []
    points += [(float(s), -half_y + wave_value(float(s))) for s in xs]
    points += [(half_x + wave_value(float(s)), float(s)) for s in ys]
    points += [(float(s), half_y + wave_value(float(s))) for s in xs[::-1]]
    points += [(-half_x + wave_value(float(s)), float(s)) for s in ys[::-1]]
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


def preview_rings(
    spec: BoxSpec, points_per_cycle: float = 7.0
) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Coarse outer and cavity rings for drawing, matched point for point.

    Both come from the same walk of the same walls, so ring[i] on one is
    directly opposite ring[i] on the other and the two can be stitched into
    quads without any searching.  The corner fillet is left off: at preview
    size it is smaller than a pixel. ``points_per_cycle`` is a density, not a
    per-wall total, so the short and long pair of walls on a non-square box
    read equally smooth instead of the longer pair coming out faceted.
    """
    tangent_x = spec.half_x - CORNER_INSET
    tangent_y = spec.half_y - CORNER_INSET
    depth = spec.wall_depth
    outer = _wall_points(spec.half_x, spec.half_y, tangent_x, tangent_y, points_per_cycle)
    cavity = _wall_points(
        spec.half_x - depth, spec.half_y - depth, tangent_x, tangent_y, points_per_cycle
    )
    return outer, cavity


def wavy_outer_polygon(spec: BoxSpec) -> Polygon:
    tx, ty = spec.half_x - CORNER_INSET, spec.half_y - CORNER_INSET
    polygon = Polygon(_wall_points(spec.half_x, spec.half_y, tx, ty))
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("wavy box outline is not a valid single polygon")
    return _rounded(polygon, spec.corner_fillet)


def wavy_cavity_polygon(spec: BoxSpec) -> Polygon:
    """Interior outline: the outer walls shifted straight in by ``wall_depth``."""
    depth = spec.wall_depth
    tx, ty = spec.half_x - CORNER_INSET, spec.half_y - CORNER_INSET
    polygon = Polygon(
        _wall_points(spec.half_x - depth, spec.half_y - depth, tx, ty)
    )
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("wavy cavity outline is not a valid single polygon")
    return _rounded(polygon, max(0.2, spec.corner_fillet - spec.wall))


# --------------------------------------------------------------------------- #
# mesh helpers
# --------------------------------------------------------------------------- #
def translated(mesh: trimesh.Trimesh, xyz: tuple[float, float, float]) -> trimesh.Trimesh:
    result = mesh.copy()
    result.apply_translation(xyz)
    return result


def union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    result = trimesh.boolean.union(meshes, engine="manifold")
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def difference(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    result = trimesh.boolean.difference(meshes, engine="manifold")
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def intersection(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    result = trimesh.boolean.intersection(meshes, engine="manifold")
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def _extrude_polygon(polygon: Polygon, height: float) -> trimesh.Trimesh:
    return trimesh.creation.extrude_polygon(polygon, height, engine="earcut")


def _extrude_yz_profile(profile: Polygon, width: float) -> trimesh.Trimesh:
    """Extrude a Y/Z section across world X."""
    solid = _extrude_polygon(profile, width)
    solid.apply_transform(np.asarray([
        [0.0, 0.0, 1.0, -width / 2.0],
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]))
    return solid


def _extrude_xz_profile(profile: Polygon, width: float) -> trimesh.Trimesh:
    """Extrude an X/Z section across world Y - the ``_extrude_yz_profile`` mirror
    for a shape that runs the other direction."""
    solid = _extrude_polygon(profile, width)
    solid.apply_transform(np.asarray([
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, -width / 2.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]))
    return solid


def _sweep_profile(
    path: list[tuple[float, float]],
    lateral: tuple[float, float],
    profile_tz: list[tuple[float, float]],
) -> trimesh.Trimesh:
    """Sweep a closed ``(t, z)`` profile along a planar path.

    ``lateral`` is the unit X/Y direction the profile's ``t`` axis points along;
    its ``z`` axis is world Z.  Returns a watertight prism with flat end caps.
    """
    lateral_x, lateral_y = lateral
    rings, loop = len(path), len(profile_tz)
    vertices = [
        (base_x + lateral_x * t, base_y + lateral_y * t, z)
        for base_x, base_y in path
        for t, z in profile_tz
    ]
    faces: list[tuple[int, int, int]] = []
    for ring in range(rings - 1):
        a, b = ring * loop, (ring + 1) * loop
        for j in range(loop):
            jn = (j + 1) % loop
            faces.append((a + j, a + jn, b + jn))
            faces.append((a + j, b + jn, b + j))
    for j in range(1, loop - 1):
        faces.append((0, j, j + 1))
    last = (rings - 1) * loop
    for j in range(1, loop - 1):
        faces.append((last, last + j + 1, last + j))

    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        process=True,
    )
    mesh.merge_vertices()
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise RuntimeError("swept lock profile is not a clean solid")
    return mesh


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


def _lock_profile(protrusion: float, clearance: float = 0.0) -> list[tuple[float, float]]:
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
        (-LOCK_EMBED, low - LOCK_EMBED),
        (reach, flat_bottom),
        (reach, flat_top),
        (-LOCK_EMBED, high + LOCK_EMBED),
    ]


def _wall_lock_paths(
    spec: BoxSpec,
) -> list[tuple[list[tuple[float, float]], tuple[float, float]]]:
    """Bump centre-lines on the interior face of all four walls, plus the
    inward direction each bump grows in."""
    depth = spec.wall_depth
    walls = (
        ("y", spec.half_y, spec.half_x - depth, (-1.0, 0.0)),   # +X wall
        ("y", spec.half_y, -(spec.half_x - depth), (1.0, 0.0)),  # -X wall
        ("x", spec.half_x, spec.half_y - depth, (0.0, -1.0)),    # +Y wall
        ("x", spec.half_x, -(spec.half_y - depth), (0.0, 1.0)),  # -Y wall
    )
    paths: list[tuple[list[tuple[float, float]], tuple[float, float]]] = []
    for run_axis, wave_half, face, inward in walls:
        for centre in lock_positions(wave_half - CORNER_INSET - LOCK_CORNER_CLEAR):
            lo, hi = centre - LOCK_RUN / 2.0, centre + LOCK_RUN / 2.0
            ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
            if run_axis == "y":
                path = [(face + wave_value(float(s)), float(s)) for s in ss]
            else:
                path = [(float(s), face + wave_value(float(s))) for s in ss]
            paths.append((path, inward))
    return paths


def make_wall_lock_bumps(spec: BoxSpec) -> list[trimesh.Trimesh]:
    """Small chamfered bumps standing proud of each wall's interior face."""
    profile = _lock_profile(LOCK_PROTRUSION)
    return [
        translated(_sweep_profile(path, inward, profile), (0.0, 0.0, spec.z))
        for path, inward in _wall_lock_paths(spec)
    ]


# --------------------------------------------------------------------------- #
# parts
# --------------------------------------------------------------------------- #
def flat_cavity_polygon(spec: BoxSpec) -> Polygon:
    """Straight-sided cavity profile for the flat band at the bottom.

    Sized to the innermost the wavy cavity ever reaches, so the band adds
    material against the wall and never cuts into it.  It is exactly the
    rectangle ``usable_inside`` reports, which is why turning the band on does
    not change how much straight-sided room the box has.
    """
    half_x = spec.half_x - spec.wall_depth - WAVE_AMPLITUDE
    half_y = spec.half_y - spec.wall_depth - WAVE_AMPLITUDE
    if half_x <= 0.0 or half_y <= 0.0:
        raise ValueError("box is too small for a flat-walled band")
    return _rounded(
        shapely_box(-half_x, -half_y, half_x, half_y),
        max(0.2, spec.corner_fillet - spec.wall),
    )


def make_box(spec: BoxSpec) -> trimesh.Trimesh:
    envelope = _extrude_polygon(wavy_outer_polygon(spec), spec.z)
    if spec.flat_inside > 0.0:
        # The cavity is two stacked prisms: a straight-sided one sitting on the
        # floor, and the wavy one above it.  What that leaves behind is a band
        # of wall with flat faces for the first flat_inside mm, which is the
        # point - the wave carries on unchanged above it.
        band = _extrude_polygon(flat_cavity_polygon(spec), spec.flat_inside)
        band.apply_translation((0.0, 0.0, spec.wall))
        above = _extrude_polygon(
            wavy_cavity_polygon(spec),
            spec.z - spec.wall - spec.flat_inside + 1.0,
        )
        above.apply_translation((0.0, 0.0, spec.wall + spec.flat_inside))
        cavity = union([band, above])
    else:
        cavity = _extrude_polygon(
            wavy_cavity_polygon(spec), spec.z - spec.wall + 1.0
        )
        cavity.apply_translation((0.0, 0.0, spec.wall))
    shell = difference([envelope, cavity])
    bumps = make_wall_lock_bumps(spec)
    result = union([shell, *bumps]) if bumps else shell
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def connector_half_widths(box: BoxSpec, connector: ConnectorSpec) -> tuple[float, float]:
    """``(inner, outer)`` half widths of the connector corridor, measured from
    the seam centre-line."""
    inner = box.wall_depth + WAVE_MATING_GAP / 2.0 + connector.tolerance
    return inner, inner + connector.arm_thickness


def connector_fits(
    box: BoxSpec,
    along_axis: str = "y",
    length: float = DEFAULT_SIDE_LENGTH,
    position: float = 0.0,
) -> bool:
    """Whether a connector of this length seats on that wall at all."""
    wave_half = box.half_x if along_axis.lower() == "x" else box.half_y
    return abs(position) + length / 2.0 <= wave_half - CORNER_INSET


def joinable_sides(
    box: BoxSpec, length: float = DEFAULT_SIDE_LENGTH
) -> tuple[bool, bool]:
    """``(x_walls, y_walls)`` - whether each pair of walls can take a connector.

    A wall running along X is the one whose length is the box's X dimension.
    """
    return connector_fits(box, "x", length), connector_fits(box, "y", length)


def make_side_connector(
    box: BoxSpec,
    connector: ConnectorSpec,
    along_axis: str = "y",
    position: float = 0.0,
    length: float = DEFAULT_SIDE_LENGTH,
) -> trimesh.Trimesh:
    axis = along_axis.lower()
    if axis not in {"x", "y"}:
        raise ValueError("along_axis must be 'x' or 'y'")
    if length <= 0:
        raise ValueError("side connector length must be positive")
    wave_half = box.half_x if axis == "x" else box.half_y
    if abs(position) + length / 2.0 > wave_half - CORNER_INSET:
        shortest = 2.0 * (length / 2.0 + CORNER_INSET) + WAVE_MATING_GAP
        raise ValueError(
            f"a {length:g} mm connector does not fit between this wall's corners: "
            f"that wall runs {2.0 * (wave_half - CORNER_INSET):.2f} mm and needs "
            f"{length:g}. A wall this short joins nothing - use the box's other "
            f"side, or make this one at least {shortest:.2f} mm"
        )
    # The band sits on the floor and the arms hang from the rim, so on any
    # normal bin they are nowhere near each other.  On a very shallow one they
    # meet, and it is worth saying so plainly rather than letting the fit check
    # report a bare collision volume.
    band_top = box.wall + box.flat_inside
    arm_bottom = box.z - connector.arm_depth
    if box.flat_inside > 0.0 and arm_bottom < band_top:
        room = box.z - connector.arm_depth - box.wall
        raise ValueError(
            f"the flat band reaches {band_top:.2f} mm up but the connector's arms "
            f"hang down to {arm_bottom:.2f} mm, so they would collide. On a "
            f"{box.z:g} mm box the band can be at most {max(room, 0.0):.2f} mm, or "
            f"make the box at least {box.wall + box.flat_inside + connector.arm_depth:.2f} mm tall"
        )

    step = WAVE_LENGTH / 2.0
    steps = position / step
    if abs(steps - round(steps)) > 1e-6:
        raise ValueError(
            f"connector position must be a whole multiple of {step:g} mm - half a "
            f"wave - so one connector part fits every seam and drops on either way "
            f"round; {position:g} mm is not - try {round(steps) * step:g} mm"
        )

    inner_hw, outer_hw = connector_half_widths(box, connector)
    samples = np.linspace(-length / 2.0, length / 2.0, _sample_count(length))
    cavity_samples = np.linspace(
        -length / 2.0 - 0.5, length / 2.0 + 0.5, _sample_count(length + 1.0)
    )

    def corridor(half_width: float, coordinates: np.ndarray) -> Polygon:
        low = high = [wave_value(position + float(v)) for v in coordinates]
        if axis == "y":
            near = [(o - half_width, float(v)) for v, o in zip(coordinates, low)]
            far = [
                (o + half_width, float(v))
                for v, o in zip(coordinates[::-1], high[::-1])
            ]
        else:
            near = [(float(v), o - half_width) for v, o in zip(coordinates, low)]
            far = [
                (float(v), o + half_width)
                for v, o in zip(coordinates[::-1], high[::-1])
            ]
        polygon = Polygon(near + far)
        if not polygon.is_valid:
            raise RuntimeError("side-connector corridor is not a valid polygon")
        return polygon

    body = _extrude_polygon(corridor(outer_hw, samples), connector.height)
    channel = _extrude_polygon(corridor(inner_hw, cavity_samples), connector.arm_depth)
    result = difference([body, channel])

    notches = _arm_notches(box, connector, axis, position, length, inner_hw)
    if notches:
        result = difference([result, *notches])
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def _arm_notches(
    box: BoxSpec,
    connector: ConnectorSpec,
    axis: str,
    position: float,
    length: float,
    inner_hw: float,
) -> list[trimesh.Trimesh]:
    """Recesses in both arms that receive the walls' lock bumps.

    The connector is modelled with its cap on top, so the arms hang from
    ``arm_depth`` down to 0 and the notches sit at the same distance below the
    rim as the bumps do.

    A notch is cut at **every** lattice point under the connector, not only at
    the ones the box it was generated for happens to carry.  The neighbour
    across the seam may be a different size, and a missing notch would foul its
    bump; a notch with no bump behind it costs nothing.
    """
    profile = _lock_profile(LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE)
    # Any bump that reaches under the connector at all needs a notch, including
    # one only half covered at an end - otherwise the solid arm end fouls it.
    span = length / 2.0 + LOCK_RUN / 2.0
    notches: list[trimesh.Trimesh] = []
    for centre in lock_lattice(position - span, position + span):
        local = centre - position
        lo, hi = local - LOCK_RUN / 2.0, local + LOCK_RUN / 2.0
        ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
        offsets = [wave_value(position + float(s)) for s in ss]
        for sign in (1.0, -1.0):
            # The arm's wall-facing face is its inner one; the notch is cut from
            # there outward into the arm, matching the bump that pokes in.
            if axis == "y":
                path = [(o + sign * inner_hw, float(s)) for s, o in zip(ss, offsets)]
                lateral = (sign, 0.0)
            else:
                path = [(float(s), o + sign * inner_hw) for s, o in zip(ss, offsets)]
                lateral = (0.0, sign)
            notches.append(
                translated(
                    _sweep_profile(path, lateral, profile),
                    (0.0, 0.0, connector.arm_depth),
                )
            )
    return notches


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# floor label
# --------------------------------------------------------------------------- #
def _font() -> FontProperties:
    return FontProperties(family=TEXT_FONT_FAMILY, weight=TEXT_FONT_WEIGHT)


def _cap_ratio() -> float:
    """Cap height per unit of font size, for this font.

    ``TextPath`` takes a font size, but a letter's height is what matters here,
    so every size is expressed as a cap height and converted through this.
    """
    reference = TextPath((0.0, 0.0), "X", size=100.0, prop=_font())
    bounds = reference.get_extents()
    return (bounds.y1 - bounds.y0) / 100.0


def text_outline(label: str, cap_height: float) -> Polygon | MultiPolygon:
    """Filled outline of ``label``, centred on the origin, letters ``cap_height`` tall.

    Glyph contours arrive as a flat list of rings with no nesting information,
    so a ring's depth - how many larger rings enclose it - decides whether it is
    a shell or a hole.  That is what keeps the middle of an O open.
    """
    if not label.strip():
        raise ValueError("label is empty")
    if cap_height <= 0:
        raise ValueError("cap height must be positive")

    path = TextPath(
        (0.0, 0.0), label, size=cap_height / _cap_ratio(), prop=_font()
    )
    rings = []
    for ring in path.to_polygons():
        if len(ring) < 3:
            continue
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.area <= 0:
            continue
        rings.append(polygon)
    if not rings:
        raise ValueError(f"'{label}' has no printable outline")

    rings.sort(key=lambda item: item.area, reverse=True)
    shells, holes = [], []
    for index, ring in enumerate(rings):
        probe = ring.representative_point()
        depth = sum(1 for bigger in rings[:index] if bigger.contains(probe))
        (holes if depth % 2 else shells).append(ring)

    filled = unary_union(shells)
    if holes:
        filled = filled.difference(unary_union(holes))
    if filled.is_empty:
        raise ValueError(f"'{label}' has no printable outline")

    minx, miny, maxx, maxy = filled.bounds
    return translate_polygon(
        filled, xoff=-(minx + maxx) / 2.0, yoff=-(miny + maxy) / 2.0
    )


def top_label_zone(box: BoxSpec) -> Polygon:
    """Floor-plan area reserved by the rear rim-label ledge."""
    inside_x, inside_y = box.usable_inside
    if inside_y < TOP_LABEL_LEDGE_DEPTH - 1e-9:
        raise ValueError(
            f"a top label needs at least {TOP_LABEL_LEDGE_DEPTH:g} mm of usable "
            f"bin depth; this bin has {inside_y:.1f} mm"
        )
    wall_y = inside_y / 2.0
    return shapely_box(
        -inside_x / 2.0,
        wall_y - TOP_LABEL_LEDGE_DEPTH,
        inside_x / 2.0,
        wall_y,
    )


def top_label_outline(box: BoxSpec, label: str) -> Polygon | MultiPolygon:
    """Fixed 5 mm text, centred on the 7 mm rear ledge."""
    if box.z < TOP_LABEL_LEDGE_DEPTH - 1e-9:
        raise ValueError(
            f"a top label needs a bin at least {TOP_LABEL_LEDGE_DEPTH:g} mm tall "
            "for its 45-degree ledge"
        )
    top_label_zone(box)
    outline = text_outline(label, TOP_LABEL_CAP_HEIGHT)
    minx, miny, maxx, maxy = outline.bounds
    inside_x, _inside_y = box.usable_inside
    room_x = inside_x - 2.0 * TOP_LABEL_MARGIN
    room_y = TOP_LABEL_LEDGE_DEPTH - 2.0 * TOP_LABEL_MARGIN
    width, height = maxx - minx, maxy - miny
    if width > room_x + 1e-9 or height > TOP_LABEL_LEDGE_DEPTH + 1e-9:
        raise ValueError(
            f"'{label}' will not fit on the top label ledge: fixed "
            f"{TOP_LABEL_CAP_HEIGHT:g} mm letters need {width:.1f} x {height:.1f} mm "
            f"and the ledge gives {room_x:.1f} x {room_y:.1f} mm. Use a shorter "
            "label or a wider box"
        )
    inside_x, inside_y = box.usable_inside
    return translate_polygon(
        outline, yoff=inside_y / 2.0 - TOP_LABEL_LEDGE_DEPTH / 2.0
    )


def make_top_label_ledge(box: BoxSpec) -> trimesh.Trimesh:
    """Rear label shelf with a 45-degree self-supporting underside.

    The shelf runs the full interior width so it meets the left and right
    walls flush.  It is cut across the whole outer envelope and then trimmed
    back to the wavy side walls, which leaves no gap at either end.
    """
    _inside_x, inside_y = box.usable_inside
    wall_y = inside_y / 2.0
    inner_y = wall_y - TOP_LABEL_LEDGE_DEPTH
    envelope_polygon = wavy_outer_polygon(box)
    minx, _miny, maxx, rear_y = envelope_polygon.bounds
    low_z = box.z - TOP_LABEL_LEDGE_DEPTH
    profile = Polygon([
        (inner_y, box.z),
        (rear_y, box.z),
        (rear_y, low_z),
        (wall_y, low_z),
    ])
    ledge = _extrude_yz_profile(profile, maxx - minx)
    # Trim the ends back to just inside the wavy side walls.  Cutting a hair
    # shy of the real wall surface keeps the shelf buried in wall material -
    # it merges with the body cleanly instead of leaving coincident faces.
    trim = _extrude_polygon(envelope_polygon.buffer(-0.1), box.z + 2.0)
    trim.apply_translation((0.0, 0.0, -1.0))
    ledge = intersection([ledge, trim])
    ledge.remove_unreferenced_vertices()
    ledge.merge_vertices()
    return ledge


def make_top_label(box: BoxSpec, label: str) -> trimesh.Trimesh:
    """The separate-colour inlay that finishes flush with the rim."""
    outline = top_label_outline(box, label)
    pieces = list(outline.geoms) if isinstance(outline, MultiPolygon) else [outline]
    solid = union([_extrude_polygon(piece, TEXT_DEPTH) for piece in pieces])
    solid.apply_translation((0.0, 0.0, box.z - TEXT_DEPTH))
    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return solid


def make_top_labelled_box(
    box: BoxSpec,
    label: str,
    body: trimesh.Trimesh | None = None,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Add the rim shelf and return its pocketed body plus flush text inlay."""
    with_ledge = union([
        make_box(box) if body is None else body,
        make_top_label_ledge(box),
    ])
    inlay = make_top_label(box, label)
    pocketed = difference([with_ledge, inlay])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed, inlay


def _scoop_bounds(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float, float]:
    if floor_bounds is None:
        inside_x, inside_y = box.usable_inside
        return -inside_x / 2.0, -inside_y / 2.0, inside_x / 2.0, inside_y / 2.0
    x0, y0, x1, y1 = floor_bounds
    if not all(math.isfinite(value) for value in floor_bounds) or x1 <= x0 or y1 <= y0:
        raise ValueError("scoop floor bounds must have positive finite width and depth")
    return x0, y0, x1, y1


def scoop_dimensions(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float]:
    """Return the scoop's vertical rise and front-to-back run."""
    _x0, y0, _x1, y1 = _scoop_bounds(box, floor_bounds)
    height = (box.z - box.wall) * SCOOP_HEIGHT_FRACTION
    # Normal bins get a circular quarter curve.  Very shallow floor plans keep
    # the requested half-wall rise with an elliptical curve that still leaves
    # usable floor in front of it.
    run = min(height, (y1 - y0) * 0.5)
    if height <= 0.0 or run <= 0.0:
        raise ValueError("this box is too small for a scoop")
    return height, run


def scoop_floor_zone(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> Polygon:
    """Floor-plan strip occupied by the front scoop."""
    x0, y0, x1, _y1 = _scoop_bounds(box, floor_bounds)
    _height, run = scoop_dimensions(box, floor_bounds)
    return shapely_box(x0, y0, x1, y0 + run)


def scoop_keep_out(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
    tolerance: float = SCOOP_FLOOR_TOLERANCE,
) -> Polygon:
    """The part of the scoop strip a support genuinely cannot stand on.

    The curve meets the floor tangentially, so its innermost millimetres are
    only microns proud of it - on a 40 mm bin the scoop is 0.03 mm high one
    millimetre in.  Reserving the whole run as if it were a wall rejected
    supports that in fact sit flat, so the strip stops where the curve has
    risen ``tolerance`` above the floor.  The profile is
    ``rise = height * (1 - cos(phi))`` at ``run * sin(phi)`` in from that
    meeting point, which inverts to the offset below.
    """
    x0, y0, x1, _y1 = _scoop_bounds(box, floor_bounds)
    height, run = scoop_dimensions(box, floor_bounds)
    inner = y0 + run
    if tolerance > 0.0:
        gained = min(1.0, max(0.0, tolerance / height))
        inner -= run * math.sin(math.acos(1.0 - gained))
    return shapely_box(x0, y0, x1, max(y0 + min(run, 0.5), inner))


def make_scoop(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> trimesh.Trimesh:
    """Full-width curved retrieval ramp rising halfway up the front wall.

    The concave face looks back into the bin, so a part can be swept forward
    and lifted out over the low front lip.
    """
    x0, wall_y, x1, _y1 = _scoop_bounds(box, floor_bounds)
    height, run = scoop_dimensions(box, floor_bounds)
    inner_y = wall_y + run
    floor_z = box.wall
    centre_z = floor_z + height
    curve = [
        (
            inner_y - run * math.cos(theta),
            centre_z + height * math.sin(theta),
        )
        for theta in np.linspace(0.0, -math.pi / 2.0, SCOOP_CURVE_SEGMENTS + 1)
    ]
    profile = Polygon([
        (inner_y, floor_z),
        (wall_y, floor_z),
        (wall_y, centre_z),
        *curve[1:-1],
    ])
    scoop = _extrude_yz_profile(profile, x1 - x0)
    scoop.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    scoop.remove_unreferenced_vertices()
    scoop.merge_vertices()
    return scoop


@dataclass(frozen=True)
class LabelPlacement:
    cap_height: float
    rotated: bool
    x: float = 0.0
    y: float = 0.0


def _label_candidates(
    room: Polygon, occupied: tuple[Polygon, ...], width: float, height: float
) -> Iterable[tuple[float, float]]:
    """Useful positions beside obstacle edges, then a complete 1 mm fallback."""
    minx, miny, maxx, maxy = room.bounds
    low_x, high_x = minx + width / 2.0, maxx - width / 2.0
    low_y, high_y = miny + height / 2.0, maxy - height / 2.0
    if low_x > high_x + 1e-9 or low_y > high_y + 1e-9:
        return

    xs = {0.0, low_x, high_x}
    ys = {0.0, low_y, high_y}
    for obstacle in occupied:
        ox0, oy0, ox1, oy1 = obstacle.bounds
        xs.update((ox0 - width / 2.0, ox1 + width / 2.0, (ox0 + ox1) / 2.0))
        ys.update((oy0 - height / 2.0, oy1 + height / 2.0, (oy0 + oy1) / 2.0))
    xs = {min(max(value, low_x), high_x) for value in xs}
    ys = {min(max(value, low_y), high_y) for value in ys}
    candidates = {(x, y) for x in xs for y in ys}
    ordered = sorted(
        candidates,
        key=lambda point: (point[0] ** 2 + point[1] ** 2,
                           abs(point[1]), abs(point[0]), point[1], point[0]),
    )
    yield from ordered

    # Obstacles can make a useful location unrelated to another edge (for
    # example a narrow corridor). Cover the remaining floor at the editor's
    # one-millimetre resolution. Typical bins are only a few thousand points.
    x = math.ceil(low_x)
    while x <= high_x + 1e-9:
        y = math.ceil(low_y)
        while y <= high_y + 1e-9:
            candidate = (float(x), float(y))
            if candidate not in candidates:
                yield candidate
            y += 1
        x += 1


def label_placement(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
) -> LabelPlacement:
    """Largest legal label position, automatically moved around insert zones."""
    inside_x, inside_y = box.usable_inside
    room_x = inside_x - 2.0 * TEXT_MARGIN
    room_y = inside_y - 2.0 * TEXT_MARGIN
    if room_x <= 0 or room_y <= 0:
        raise ValueError("this box has no floor area to label")

    room = shapely_box(-room_x / 2.0, -room_y / 2.0,
                       room_x / 2.0, room_y / 2.0)
    obstacles = tuple(
        polygon.buffer(TEXT_MARGIN, join_style="mitre")
        for polygon in occupied if not polygon.is_empty
    )

    ideal = text_outline(label, TEXT_CAP_HEIGHT_IDEAL)
    minx, miny, maxx, maxy = ideal.bounds
    ideal_width, ideal_height = maxx - minx, maxy - miny

    for rotated in (False, True):
        across, up = ((ideal_height, ideal_width) if rotated
                      else (ideal_width, ideal_height))
        max_cap = min(TEXT_CAP_HEIGHT_IDEAL,
                      TEXT_CAP_HEIGHT_IDEAL * room_x / across,
                      TEXT_CAP_HEIGHT_IDEAL * room_y / up)
        if max_cap < TEXT_CAP_HEIGHT_MIN - 1e-9:
            continue
        if not obstacles:
            return LabelPlacement(max_cap, rotated)

        # Quarter-millimetre cap steps are visually continuous while keeping a
        # live editor responsive. Always test the exact minimum as the last try.
        caps = []
        cap = max_cap
        while cap >= TEXT_CAP_HEIGHT_MIN - 1e-9:
            caps.append(max(cap, TEXT_CAP_HEIGHT_MIN))
            cap -= 0.25
        if not caps or caps[-1] > TEXT_CAP_HEIGHT_MIN + 1e-9:
            caps.append(TEXT_CAP_HEIGHT_MIN)
        for cap in caps:
            outline = text_outline(label, cap)
            if rotated:
                outline = rotate_polygon(outline, 90.0, origin=(0.0, 0.0),
                                         use_radians=False)
            bx0, by0, bx1, by1 = outline.bounds
            width, height = bx1 - bx0, by1 - by0
            footprint = shapely_box(-width / 2.0, -height / 2.0,
                                    width / 2.0, height / 2.0)
            for x, y in _label_candidates(room, obstacles, width, height):
                placed = translate_polygon(footprint, xoff=x, yoff=y)
                if room.covers(placed) and all(not placed.intersects(o) for o in obstacles):
                    return LabelPlacement(cap, rotated, x, y)

    longest = max(room_x, room_y)
    needed = ideal_width * (TEXT_CAP_HEIGHT_MIN / TEXT_CAP_HEIGHT_IDEAL)
    obstacle_note = " around the insert features" if obstacles else ""
    raise ValueError(
        f"'{label}' will not fit on this floor{obstacle_note} either way round: it needs "
        f"{needed:.1f} mm at the {TEXT_CAP_HEIGHT_MIN:.0f} mm minimum letter "
        f"height and the floor gives {longest:.1f} mm. Use a shorter label or "
        f"a bigger box"
    )


def label_layout(box: BoxSpec, label: str) -> tuple[float, bool]:
    """Backward-compatible size/orientation result for an unobstructed floor."""
    placement = label_placement(box, label)
    return placement.cap_height, placement.rotated


def placed_label_outline(
    box: BoxSpec, label: str, occupied: Iterable[Polygon] = ()
) -> Polygon | MultiPolygon:
    """The label's final 2D shape, turned and moved clear of insert features."""
    placement = label_placement(box, label, occupied)
    outline = text_outline(label, placement.cap_height)
    if placement.rotated:
        outline = rotate_polygon(outline, 90.0, origin=(0.0, 0.0), use_radians=False)
        minx, miny, maxx, maxy = outline.bounds
        outline = translate_polygon(
            outline, xoff=-(minx + maxx) / 2.0, yoff=-(miny + maxy) / 2.0
        )
    return translate_polygon(outline, xoff=placement.x, yoff=placement.y)


def make_floor_label(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
    top_z: float | None = None,
) -> trimesh.Trimesh:
    """The solid that fills the label pocket, flush with the floor.

    It sits in the top ``TEXT_DEPTH`` of the floor rather than standing on it,
    so the finished floor is flat and the lettering is an inlay.  It is a
    separate object in the 3MF so a slicer can give it its own filament.
    """
    outline = placed_label_outline(box, label, occupied)
    pieces = list(outline.geoms) if isinstance(outline, MultiPolygon) else [outline]
    solid = union([_extrude_polygon(piece, TEXT_DEPTH) for piece in pieces])
    top_z = box.wall if top_z is None else top_z
    if top_z < TEXT_DEPTH:
        raise ValueError(f"label depth {TEXT_DEPTH:g} mm exceeds its floor thickness")
    solid.apply_translation((0.0, 0.0, top_z - TEXT_DEPTH))
    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return solid


def make_labelled_box(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
    body: trimesh.Trimesh | None = None,
    top_z: float | None = None,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """``(box with the label pocket cut, the solid that fills it)``.

    The two share faces and nothing else, which is exactly what a slicer wants
    from a two-material part.
    """
    inlay = make_floor_label(box, label, occupied, top_z)
    pocketed = difference([make_box(box) if body is None else body, inlay])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed, inlay


def label_report(
    box: BoxSpec, label: str, occupied: Iterable[Polygon] = ()
) -> dict[str, object]:
    placement = label_placement(box, label, occupied)
    outline = text_outline(label, placement.cap_height)
    minx, miny, maxx, maxy = outline.bounds
    across, up = maxx - minx, maxy - miny
    if placement.rotated:
        across, up = up, across
    return {
        "label": label,
        "cap_height_mm": round(placement.cap_height, 3),
        "rotated": placement.rotated,
        "position_mm": [round(placement.x, 3), round(placement.y, 3)],
        "footprint_mm": [round(across, 3), round(up, 3)],
        "depth_mm": TEXT_DEPTH,
    }


def top_label_report(box: BoxSpec, label: str) -> dict[str, object]:
    outline = top_label_outline(box, label)
    minx, miny, maxx, maxy = outline.bounds
    return {
        "label": label,
        "position": "top",
        "cap_height_mm": TOP_LABEL_CAP_HEIGHT,
        "rotated": False,
        "footprint_mm": [round(maxx - minx, 3), round(maxy - miny, 3)],
        "ledge_depth_mm": TOP_LABEL_LEDGE_DEPTH,
        "ledge_underside_degrees": 45.0,
        "depth_mm": TEXT_DEPTH,
    }


def mesh_report(name: str, mesh: trimesh.Trimesh) -> dict[str, object]:
    report = {
        "name": name,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "positive_volume": bool(mesh.volume > 0),
        "components": len(mesh.split(only_watertight=False)),
        "bounds_mm": np.round(mesh.bounds, 3).tolist(),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "triangles": int(len(mesh.faces)),
    }
    if not all(
        (
            report["watertight"], report["winding_consistent"],
            report["positive_volume"], report["components"] == 1,
        )
    ):
        raise RuntimeError(f"{name} failed mesh validation: {report}")
    return report


def mesh_fingerprint(mesh: trimesh.Trimesh) -> str:
    return hashlib.sha256(mesh.export(file_type="stl")).hexdigest().upper()


def intersection_volume(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    overlap = trimesh.boolean.intersection([a, b], engine="manifold")
    if overlap is None or len(overlap.faces) == 0:
        return 0.0
    triangles = overlap.triangles
    signed = np.einsum(
        "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    )
    return float(abs(signed.sum()) / 6.0)


def installed_boxes(
    box: BoxSpec, along_axis: str = "y"
) -> list[trimesh.Trimesh]:
    mesh = make_box(box)
    if along_axis.lower() == "y":
        return [
            translated(mesh, (-box.x / 2.0, 0.0, 0.0)),
            translated(mesh, (box.x / 2.0, 0.0, 0.0)),
        ]
    return [
        translated(mesh, (0.0, -box.y / 2.0, 0.0)),
        translated(mesh, (0.0, box.y / 2.0, 0.0)),
    ]


def seat_transform(box: BoxSpec, connector: ConnectorSpec, position: float, axis: str):
    z = box.z - connector.arm_depth
    return (position, 0.0, z) if axis == "x" else (0.0, position, z)


def validate_side_fit(
    box: BoxSpec,
    connector: ConnectorSpec,
    clip: trimesh.Trimesh,
    along_axis: str = "y",
    position: float = 0.0,
) -> float:
    """Overlap of the seated connector with the two boxes it joins."""
    axis = along_axis.lower()
    boxes = installed_boxes(box, axis)
    seated = translated(clip, seat_transform(box, connector, position, axis))
    overlap = sum(intersection_volume(seated, item) for item in boxes)
    if overlap > 0.01:
        raise RuntimeError(
            f"side connector collides with installed boxes: {overlap:.6f} mm^3"
        )
    return overlap


def measure_lock(
    box: BoxSpec,
    connector: ConnectorSpec,
    along_axis: str = "y",
    position: float = 0.0,
    lifts: tuple[float, ...] = (0.0, 0.5, 1.5),
) -> dict[str, float]:
    """Seated clearance, and the interference met while lifting the clip out.

    A seated clip is free; raising it drives the arm notches onto the bumps,
    which is the lock.  Also reports what a notch-less arm would hit, proving
    the bumps stand in the arm's path at all.
    """
    axis = along_axis.lower()
    boxes = installed_boxes(box, axis)
    clip = make_side_connector(box, connector, axis, position)
    base = seat_transform(box, connector, position, axis)

    result: dict[str, float] = {}
    for lift in lifts:
        placed = translated(clip, (base[0], base[1], base[2] + lift))
        result[f"lift_{lift:.1f}_mm3"] = round(
            sum(intersection_volume(placed, item) for item in boxes), 6
        )

    inner_hw, outer_hw = connector_half_widths(box, connector)
    samples = np.linspace(-DEFAULT_SIDE_LENGTH / 2.0, DEFAULT_SIDE_LENGTH / 2.0, 5)
    plain_body = _extrude_polygon(
        _plain_corridor(box, axis, position, samples, outer_hw), connector.height
    )
    plain_channel = _extrude_polygon(
        _plain_corridor(box, axis, position, samples, inner_hw), connector.arm_depth
    )
    plain = translated(difference([plain_body, plain_channel]), base)
    result["no_notch_mm3"] = round(
        sum(intersection_volume(plain, item) for item in boxes), 6
    )
    result["protrusion_mm"] = LOCK_PROTRUSION
    return result


def _plain_corridor(
    box: BoxSpec, axis: str, position: float, samples: np.ndarray, half_width: float
) -> Polygon:
    wave_half = box.half_x if axis == "x" else box.half_y
    dense = np.linspace(
        samples[0], samples[-1], _sample_count(float(samples[-1] - samples[0]))
    )
    offsets = [wave_value(position + float(v)) for v in dense]
    if axis == "y":
        near = [(o - half_width, float(v)) for v, o in zip(dense, offsets)]
        far = [
            (o + half_width, float(v))
            for v, o in zip(dense[::-1], offsets[::-1])
        ]
    else:
        near = [(float(v), o - half_width) for v, o in zip(dense, offsets)]
        far = [
            (float(v), o + half_width)
            for v, o in zip(dense[::-1], offsets[::-1])
        ]
    return Polygon(near + far)


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #
def export_bambu_compatible_3mf(scene: trimesh.Scene, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    generic = scene.export(file_type="3mf")
    if not isinstance(generic, bytes):
        raise RuntimeError("intermediate 3MF export did not return binary data")
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(False)
    reader.ReadFromBuffer(generic)
    writer = model.QueryWriter("3mf")
    writer.SetStrictModeActive(True)
    writer.WriteToFile(str(output.resolve()))
    if writer.GetWarningCount() != 0:
        raise RuntimeError(f"strict 3MF writer reported {writer.GetWarningCount()} warnings")


def label_mesh_report(name: str, mesh: trimesh.Trimesh) -> dict[str, object]:
    """Like ``mesh_report`` but a label is legitimately several solids - one per
    disconnected letter - so the single-component rule does not apply."""
    report = {
        "name": name,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "positive_volume": bool(mesh.volume > 0),
        "components": len(mesh.split(only_watertight=False)),
        "bounds_mm": np.round(mesh.bounds, 3).tolist(),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "triangles": int(len(mesh.faces)),
    }
    if not all(
        (report["watertight"], report["winding_consistent"], report["positive_volume"])
    ):
        raise RuntimeError(f"{name} failed mesh validation: {report}")
    return report


def export_labelled_box(
    box_mesh: trimesh.Trimesh,
    label_mesh: trimesh.Trimesh,
    output: Path,
    box_name: str = "box",
    label_name: str = "label",
) -> None:
    """Write a pocketed body and its sunk label as two objects in one 3MF.

    Keeping them separate is the point: load the file in Bambu Studio, answer
    yes to "load as a single object with multiple parts", and the label can be
    given its own filament.
    """
    mesh_report(box_name, box_mesh)
    label_mesh_report(label_name, label_mesh)
    if intersection_volume(box_mesh, label_mesh) > 0.01:
        raise RuntimeError(
            "the label overlaps the box instead of filling its pocket"
        )
    scene = trimesh.Scene()
    scene.units = "mm"
    scene.add_geometry(box_mesh, node_name=box_name, geom_name=box_name)
    scene.add_geometry(label_mesh, node_name=label_name, geom_name=label_name)
    export_bambu_compatible_3mf(scene, output)


def export_mesh(mesh: trimesh.Trimesh, output: Path, name: str) -> None:
    mesh_report(name, mesh)
    suffix = output.suffix.lower()
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".stl":
        mesh.export(output, file_type="stl")
        return
    if suffix == ".3mf":
        scene = trimesh.Scene()
        scene.units = "mm"
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        export_bambu_compatible_3mf(scene, output)
        return
    raise ValueError("output filename must end in .stl or .3mf")


def validate_3mf(
    path: Path,
    expected_objects: int,
    multipart: tuple[str, ...] = (),
) -> dict[str, object]:
    """Names listed in ``multipart`` may be several solids - a label is one per
    letter - so they get the relaxed check."""
    scene = trimesh.load(path, force="scene")
    if len(scene.geometry) != expected_objects:
        raise RuntimeError(
            f"3MF contains {len(scene.geometry)} objects instead of {expected_objects}"
        )
    for name, geometry in scene.geometry.items():
        if name in multipart:
            label_mesh_report(name, geometry)
        else:
            mesh_report(name, geometry)
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(path.resolve()))
    if reader.GetWarningCount() != 0:
        raise RuntimeError(f"strict 3MF reader reported {reader.GetWarningCount()} warnings")
    if model.GetObjects().Count() != expected_objects:
        raise RuntimeError("strict 3MF object count does not match")
    if model.GetBuildItems().Count() != expected_objects:
        raise RuntimeError("strict 3MF build-item count does not match")
    return {
        "objects": expected_objects,
        "names": sorted(scene.geometry.keys()),
        "bounds_mm": np.round(scene.bounds, 3).tolist(),
        "warnings": 0,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
    }


# --------------------------------------------------------------------------- #
# sampler
# --------------------------------------------------------------------------- #
def make_sampler_scene(
    sizes: tuple[tuple[float, float], ...] = (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ),
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
) -> trimesh.Scene:
    """Assembly sample: one box per requested size, plus a row of connectors.

    The connector is a single locked part now, so the row is simply ``clips``
    copies of it rather than a tolerance sweep.
    """
    if clips < 1:
        raise ValueError("the sample needs at least one connector")
    scene = trimesh.Scene()
    scene.units = "mm"
    gap = 6.0

    boxes = []
    for size_x, size_y in sizes:
        spec = BoxSpec(
            x=size_x, y=size_y, z=height, wall=wall, flat_inside=flat_inside
        )
        mesh = make_box(spec)
        mesh_report(f"sample box {size_x:g}x{size_y:g}", mesh)
        boxes.append((spec, mesh))

    cursor = 0.0
    depth = max(float(m.extents[1]) for _, m in boxes)
    for spec, mesh in boxes:
        centre = mesh.bounds.mean(axis=0)
        width = float(mesh.extents[0])
        placed = translated(
            mesh,
            (cursor + width / 2.0 - centre[0], -centre[1], -mesh.bounds[0][2]),
        )
        ux, uy = spec.units
        name = f"box_{ux:g}x{uy:g}_{spec.x:g}x{spec.y:g}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
        cursor += width + gap
    total_width = cursor - gap

    clip = make_side_connector(
        BoxSpec(flat_inside=flat_inside), connector, "y", 0.0, side_length
    )
    mesh_report("sample connector", clip)
    validate_side_fit(BoxSpec(flat_inside=flat_inside), connector, clip, "y")
    cell = float(clip.extents[0]) + 6.0
    row_y = -depth / 2.0 - gap - float(clip.extents[1]) / 2.0
    for index in range(clips):
        centre = clip.bounds.mean(axis=0)
        target = total_width / 2.0 + (index - (clips - 1) / 2.0) * cell
        placed = translated(
            clip,
            (target - centre[0], row_y - centre[1], -clip.bounds[0][2]),
        )
        name = f"connector_{index + 1}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
    return scene


def generate_sampler(
    output: Path,
    sizes: tuple[tuple[float, float], ...] | None = None,
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "height": height, "wall": wall, "connector": connector,
        "clips": clips, "side_length": side_length, "flat_inside": flat_inside,
    }
    if sizes is not None:
        kwargs["sizes"] = sizes
    scene = make_sampler_scene(**kwargs)
    export_bambu_compatible_3mf(scene, output)
    report = validate_3mf(output, len(scene.geometry))
    report["boxes"] = [f"{sx:g}x{sy:g}" for sx, sy in (sizes or (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ))]
    report["connectors"] = clips
    report["tolerance_mm"] = connector.tolerance
    report["connector_height_mm"] = connector.height
    report["connector_length_mm"] = side_length
    report["wave_length_mm"] = WAVE_LENGTH
    report["wave_amplitude_mm"] = WAVE_AMPLITUDE
    report["grid_pitch_mm"] = GRID_PITCH
    return report
