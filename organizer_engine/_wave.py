"""Wavefinity engine wavy-wall outlines, lock bumps and wall tables."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.affinity import translate as translate_polygon
from shapely.geometry import MultiPolygon, Polygon
from organizer_geometry import _sweep_profile, translated

from ._specs import (
    WAVE_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    SAMPLES_PER_MM,
    DEFAULT_WALL,
    DEFAULT_CORNER_FILLET,
    CORNER_INSET,
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
)


def nested_clearance() -> float:
    """The real air gap between two mated walls, measured perpendicular.

    ``WAVE_MATING_GAP`` is the gap measured *across* the seam, but the walls
    lean, so the shortest distance between them is shorter than that by the
    wave's own slope.  This is the number a slicer sees, and it is the same for
    every pair of bins that mate, whatever sizes they are.
    """
    return WAVE_MATING_GAP / math.sqrt(1.0 + max_wave_slope() ** 2)


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
    phase_x: float = 0.0,
    phase_y: float = 0.0,
) -> list[tuple[float, float]]:
    """Counter-clockwise outline: four wavy walls joined by corner chords.

    ``half_*`` place the faces; ``tangent_*`` say where the walls stop short of
    the nominal corner and always come from the outer profile, so an inner
    outline stays exactly parallel to the outer one.  ``points_per_cycle``
    overrides the sampling with a *density* rather than a fixed total, so a
    long wall and a short one on the same box come out equally smooth - the
    preview uses this to get a coarse ring it can draw quickly without a
    fixed point budget starving whichever pair of walls is longer.

    ``phase_x``/``phase_y`` shift the wave sampled on the front/back walls
    (which run along X) and the left/right walls (which run along Y)
    respectively.  A normal, validly grid-sized ``BoxSpec`` always leaves
    these at 0: its own centre is guaranteed to land on the global 4 mm wave
    lattice (``GRID_PITCH``/``BASE_UNIT`` are chosen exactly so this holds),
    so evaluating the wave in this shape's own local frame already equals
    the shared global wave. A caller whose real placement centre will NOT be
    on that lattice - a spacer sized to a genuine, non-8-mm-multiple free
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
    xs = np.linspace(-tangent_x, tangent_x, count_x)
    ys = np.linspace(-tangent_y, tangent_y, count_y)
    points: list[tuple[float, float]] = []
    points += [(float(s), -half_y + wave_value(float(s) + phase_x)) for s in xs]
    points += [(half_x + wave_value(float(s) + phase_y), float(s)) for s in ys]
    points += [(float(s), half_y + wave_value(float(s) + phase_x)) for s in xs[::-1]]
    points += [(-half_x + wave_value(float(s) + phase_y), float(s)) for s in ys[::-1]]
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


def wavy_rect_outer(
    half_x: float, half_y: float, corner_fillet: float = DEFAULT_CORNER_FILLET,
    phase_x: float = 0.0, phase_y: float = 0.0,
) -> Polygon:
    """The same wavy outline ``wavy_outer_polygon`` builds, from raw half-
    extents instead of a ``BoxSpec`` - so a caller whose x/y is not the 8 mm
    grid size a normal bin's ``BoxSpec`` requires (a spacer filler) can still
    build the identical, correctly-phased wave.

    A normal ``BoxSpec``'s own centre always lands on the global wave
    lattice, so its local wave already equals the shared global one and
    ``phase_x``/``phase_y`` stay 0. A shape whose real placement centre will
    NOT land on that lattice - a spacer sized to a genuine non-8-mm-multiple
    free region - must pass its centre's own offset from the lattice (see
    ``_wall_points``) so the wave still matches a neighbour's along every
    seam once it is actually placed.
    """
    tx, ty = half_x - CORNER_INSET, half_y - CORNER_INSET
    polygon = Polygon(_wall_points(half_x, half_y, tx, ty, phase_x=phase_x, phase_y=phase_y))
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("wavy box outline is not a valid single polygon")
    return _rounded(polygon, corner_fillet)


def wavy_outer_polygon(spec: BoxSpec) -> Polygon:
    return wavy_rect_outer(spec.half_x, spec.half_y, spec.corner_fillet)


def wavy_rect_cavity(
    half_x: float, half_y: float, wall_depth: float,
    corner_fillet: float = DEFAULT_CORNER_FILLET, wall: float = DEFAULT_WALL,
    phase_x: float = 0.0, phase_y: float = 0.0,
) -> Polygon:
    """The same interior outline ``wavy_cavity_polygon`` builds - the outer
    walls shifted straight in by ``wall_depth`` - from raw half-extents. See
    ``wavy_rect_outer`` for why this needs no 8 mm-grid-sized ``BoxSpec``,
    and for what ``phase_x``/``phase_y`` correct for."""
    tx, ty = half_x - CORNER_INSET, half_y - CORNER_INSET
    polygon = Polygon(_wall_points(half_x - wall_depth, half_y - wall_depth, tx, ty, phase_x=phase_x, phase_y=phase_y))
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise RuntimeError("wavy cavity outline is not a valid single polygon")
    return _rounded(polygon, max(0.2, corner_fillet - wall))


def wavy_cavity_polygon(spec: BoxSpec) -> Polygon:
    """Interior outline: the outer walls shifted straight in by ``wall_depth``."""
    return wavy_rect_cavity(spec.half_x, spec.half_y, spec.wall_depth, spec.corner_fillet, spec.wall)


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
    measure more: a corner chord cuts *inward* from the wave envelope, so a
    corner can only ever add clearance.  That is why the corner flats - which
    the odd wave makes longer on one diagonal than on the other - are a
    cosmetic asymmetry and never a mating problem.

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
) -> list[tuple[list[tuple[float, float]], tuple[float, float]]]:
    """Bump centre-lines on the interior face of all four walls, plus the
    inward direction each bump grows in - from raw half-extents. See
    ``wavy_rect_outer`` for why this needs no 8 mm-grid-sized ``BoxSpec``,
    and for what ``phase_x``/``phase_y`` correct for: the bump lattice sits
    on the same wave extrema the wall surface does, so it needs the same
    shift, applied to both the wave itself and the lattice positions it
    hangs bumps from.
    """
    walls = (
        ("y", half_y, half_x - wall_depth, (-1.0, 0.0), phase_y),   # +X wall
        ("y", half_y, -(half_x - wall_depth), (1.0, 0.0), phase_y),  # -X wall
        ("x", half_x, half_y - wall_depth, (0.0, -1.0), phase_x),    # +Y wall
        ("x", half_x, -(half_y - wall_depth), (0.0, 1.0), phase_x),  # -Y wall
    )
    paths: list[tuple[list[tuple[float, float]], tuple[float, float]]] = []
    for run_axis, wave_half, face, inward, phase in walls:
        for base_centre in lock_positions(wave_half - CORNER_INSET - LOCK_CORNER_CLEAR):
            centre = base_centre - phase
            lo, hi = centre - LOCK_RUN / 2.0, centre + LOCK_RUN / 2.0
            ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
            if run_axis == "y":
                path = [(face + wave_value(float(s) + phase), float(s)) for s in ss]
            else:
                path = [(float(s), face + wave_value(float(s) + phase)) for s in ss]
            paths.append((path, inward))
    return paths


def _wall_lock_paths(
    spec: BoxSpec,
) -> list[tuple[list[tuple[float, float]], tuple[float, float]]]:
    return _rect_wall_lock_paths(spec.half_x, spec.half_y, spec.wall_depth)


def make_wall_lock_bumps_raw(
    half_x: float, half_y: float, wall_depth: float, z: float,
    phase_x: float = 0.0, phase_y: float = 0.0,
) -> list[trimesh.Trimesh]:
    """Small chamfered bumps standing proud of each wall's interior face -
    from raw half-extents. See ``wavy_rect_outer`` for why this needs no
    8 mm-grid-sized ``BoxSpec``, and for what ``phase_x``/``phase_y`` correct
    for."""
    embed = min(LOCK_EMBED, wall_depth - LOCK_SAFE_SKIN)
    profile = _lock_profile(LOCK_PROTRUSION, embed=embed)
    return [
        translated(_sweep_profile(path, inward, profile), (0.0, 0.0, z))
        for path, inward in _rect_wall_lock_paths(half_x, half_y, wall_depth, phase_x=phase_x, phase_y=phase_y)
    ]


def make_wall_lock_bumps(spec: BoxSpec) -> list[trimesh.Trimesh]:
    """Small chamfered bumps standing proud of each wall's interior face."""
    return make_wall_lock_bumps_raw(spec.half_x, spec.half_y, spec.wall_depth, spec.z)


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
    run_axis, wave_half, face, inward = _wall_face_table(spec)[wall]
    embed = min(LOCK_EMBED, spec.wall_depth - LOCK_SAFE_SKIN)
    profile = _lock_profile(LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE, embed=embed)
    cutters: list[trimesh.Trimesh] = []
    for centre in lock_positions(wave_half - CORNER_INSET - LOCK_CORNER_CLEAR):
        lo, hi = centre - LOCK_RUN / 2.0, centre + LOCK_RUN / 2.0
        if hi < low or lo > high:
            continue
        ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
        if run_axis == "y":
            path = [(face + wave_value(float(t)), float(t)) for t in ss]
        else:
            path = [(float(t), face + wave_value(float(t))) for t in ss]
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
    """Interior wall faces keyed by name: ``(run axis, half-reach along the
    wall, face position on the perpendicular axis, inward unit vector)``."""
    depth = spec.wall_depth
    return {
        "+x": ("y", spec.half_y, spec.half_x - depth, (-1.0, 0.0)),
        "-x": ("y", spec.half_y, -(spec.half_x - depth), (1.0, 0.0)),
        "+y": ("x", spec.half_x, spec.half_y - depth, (0.0, -1.0)),
        "-y": ("x", spec.half_x, -(spec.half_y - depth), (0.0, 1.0)),
    }
