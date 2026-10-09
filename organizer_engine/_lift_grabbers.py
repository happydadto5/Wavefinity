"""Wavefinity engine lift-grabber geometry and validation."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import Polygon, box as shapely_box

from ._specs import (
    WAVE_AMPLITUDE,
    CORNER_INSET,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    LIFT_GRABBER_RIM_CLEARANCE,
    LIFT_GRABBER_FLOOR_CLEARANCE,
    LIFT_GRABBER_WALL_MARGIN,
    LIFT_GRABBER_MIN_ROOT_BITE,
    LiftGrabberDimensions,
    BoxSpec,
    max_wave_slope,
)
from ._wave import _LIFT_GRABBER_WALL_LABELS, _wall_face_table


def _lift_grabber_height_curve(z: float, dims: LiftGrabberDimensions) -> float:
    """Inward reach at height ``z`` (0 at the grabber's own bottom): 0 at
    ``z = 0``, ``dims.projection`` at the vertical midpoint, 0 again at
    ``z = dims.height`` - tangent-flat (zero slope) at both ends, so the
    bulge blends into the wall with no ramp or step anywhere."""
    return dims.projection * math.sin(math.pi * z / dims.height) ** 2


def _lift_grabber_profile(
    dims: LiftGrabberDimensions, embed: float
) -> list[tuple[float, float]]:
    """Smooth bulge section, ``t`` growing away from the wall's flat,
    non-wavy face, ``z`` relative to the grabber's own bottom (0.0).

    A small rounded rise molded into the wall - not a wedge, ramp, ledge, or
    hook.  Sampled from ``_lift_grabber_height_curve``, which is
    tangent-flat at both ``z = 0`` and ``z = dims.height``: the exposed
    shape reaches its full inward projection only at the vertical midpoint
    and eases smoothly back to flush with the wall at top and bottom, never
    presenting a ramp, ledge, or undercut.  The loop closes through a small
    embedded root behind the wall face - see ``make_lift_grabbers`` for why
    that root must reach deeper than a grabber that simply followed the
    wavy wall would need.
    """
    samples = 16
    bulge = [
        (_lift_grabber_height_curve(float(z), dims), float(z))
        for z in np.linspace(0.0, dims.height, samples)
    ]
    return [(-embed, 0.0), *bulge, (-embed, dims.height)]


def _lift_grabber_width_ease(s: float, half_width: float, cap_radius: float) -> float:
    """1.0 through the middle of the wall span, easing smoothly to 0.0 over
    the last ``cap_radius`` mm at either end.

    This is what keeps the grabber from looking like a rectangular plate
    when viewed from the front: its left/right ends blend gently into the
    flat wall (a capsule footprint) instead of stopping abruptly."""
    edge_dist = half_width - abs(s)
    if edge_dist >= cap_radius:
        return 1.0
    if edge_dist <= 0.0:
        return 0.0
    return math.sin(math.pi / 2.0 * (edge_dist / cap_radius)) ** 2


def _lift_grabber_bulge_mesh(
    dims: LiftGrabberDimensions, embed: float
) -> trimesh.Trimesh:
    """The grabber's local solid, built directly rather than swept: ``s``
    runs along the wall in ``[-width/2, width/2]``, ``t`` is the inward
    reach from the wall's flat, non-wavy face, ``z`` is vertical in
    ``[0, height]``.

    The exposed (outer) surface is ``_lift_grabber_height_curve(z)`` scaled
    by ``_lift_grabber_width_ease(s)``, so the bulge tapers smoothly to zero
    on all four sides - top, bottom, and both ends - reading as a small
    rounded lump rather than a plate.  The embedded (inner/root) surface is
    a plain flat plane at ``t = -embed`` across the whole footprint,
    independent of the visible taper, so the root stays reliably deep for
    the union with the real wavy wall regardless of where along the width
    it lands - see ``make_lift_grabbers``.

    Built once per size in this local frame and placed against each
    concrete wall by ``_place_lift_grabber`` - shared unchanged between
    ordinary bins and B4B.
    """
    half_width = dims.width / 2.0
    cap_radius = min(dims.width / 4.0, 3.0)
    ns, nz = 20, 16
    ss = np.linspace(-half_width, half_width, ns)
    zs = np.linspace(0.0, dims.height, nz)

    outer = np.empty((ns, nz, 3))
    inner = np.empty((ns, nz, 3))
    for i, s in enumerate(ss):
        ease = _lift_grabber_width_ease(float(s), half_width, cap_radius)
        for j, z in enumerate(zs):
            reach = _lift_grabber_height_curve(float(z), dims) * ease
            outer[i, j] = (s, reach, z)
            inner[i, j] = (s, -embed, z)

    def idx(surface: int, i: int, j: int) -> int:
        return surface * ns * nz + i * nz + j

    vertices = np.concatenate([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    faces: list[tuple[int, int, int]] = []

    def quad(a: int, b: int, c: int, d: int) -> None:
        faces.append((a, b, c))
        faces.append((a, c, d))

    for i in range(ns - 1):
        for j in range(nz - 1):
            quad(idx(0, i, j), idx(0, i + 1, j), idx(0, i + 1, j + 1), idx(0, i, j + 1))
            quad(idx(1, i, j), idx(1, i, j + 1), idx(1, i + 1, j + 1), idx(1, i + 1, j))
    for j in range(nz - 1):
        quad(idx(0, 0, j), idx(0, 0, j + 1), idx(1, 0, j + 1), idx(1, 0, j))
        quad(idx(0, ns - 1, j), idx(1, ns - 1, j), idx(1, ns - 1, j + 1), idx(0, ns - 1, j + 1))
    for i in range(ns - 1):
        quad(idx(0, i, 0), idx(1, i, 0), idx(1, i + 1, 0), idx(0, i + 1, 0))
        quad(idx(0, i, nz - 1), idx(0, i + 1, nz - 1), idx(1, i + 1, nz - 1), idx(1, i, nz - 1))

    mesh = trimesh.Trimesh(
        vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=True,
    )
    mesh.merge_vertices()
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise RuntimeError("Inside Handle geometry is not a clean solid")
    return mesh


def _place_lift_grabber(
    local: trimesh.Trimesh, run_axis: str, face: float,
    inward: tuple[float, float], bottom_z: float,
) -> trimesh.Trimesh:
    """Map a local ``(s, t, z)`` grabber solid onto one concrete, always
    axis-aligned wall (walls only ever run along world X or Y - never
    diagonally - so this is a plain axis remap, not an arbitrary rotation).
    """
    inward_x, inward_y = inward
    if run_axis == "y":
        matrix = np.array([
            [0.0, inward_x, 0.0, face],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, bottom_z],
            [0.0, 0.0, 0.0, 1.0],
        ])
    else:
        matrix = np.array([
            [1.0, 0.0, 0.0, 0.0],
            [0.0, inward_y, 0.0, face],
            [0.0, 0.0, 1.0, bottom_z],
            [0.0, 0.0, 0.0, 1.0],
        ])
    result = local.copy()
    result.apply_transform(matrix)
    # A "-x"/"-y" wall's mapping mirrors the local frame (inward_x/y == +1),
    # which flips the transformed mesh's effective winding; restore it so
    # every placed grabber is consistently outward-facing for the union.
    if result.volume < 0:
        result.invert()
    return result


def _lift_grabber_embed_depth(spec: BoxSpec) -> float:
    """Maximum hidden root depth for a flat-faced lift grabber, measured
    inward-negative from the nominal cavity face (see ``make_lift_grabbers``).

    The grabber is anchored to that nominal face rather than following the
    wave, but the exterior wall carries the same wave and can swing inward by
    ``WAVE_AMPLITUDE`` at a trough - that amplitude has to be reserved ahead
    of ``LOCK_SAFE_SKIN`` so a flat root can never break through the exterior
    skin, on top of the ``WAVE_AMPLITUDE`` already reserved so the root
    reaches past the cavity's own wave.  Shared by :func:`validate_lift_grabbers`
    and :func:`make_lift_grabbers` so the two can never drift apart.
    """
    max_for_exterior_skin = spec.wall_depth - WAVE_AMPLITUDE - LOCK_SAFE_SKIN
    return min(WAVE_AMPLITUDE + LOCK_EMBED, max_for_exterior_skin)


def lift_grabber_min_wall() -> float:
    """Smallest wall thickness whose root bite meets ``LIFT_GRABBER_MIN_ROOT_BITE``.

    The browser reads this to auto-promote the wall preset when lift grabbers
    are switched on over a wall that would otherwise fail
    :func:`validate_lift_grabbers` - never forcing every grabber design to one
    fixed preset, and never touching a legacy wall that already clears it.

    A flat root sits between two wavy boundaries, so the wall needs room for
    both: the cavity's wave amplitude, the real required root bite, the
    exterior wave's amplitude, and the exterior safety skin.
    """
    wall_depth = 2.0 * WAVE_AMPLITUDE + LIFT_GRABBER_MIN_ROOT_BITE + LOCK_SAFE_SKIN
    return wall_depth / math.sqrt(1.0 + max_wave_slope() ** 2)


def validate_lift_grabbers(box: BoxSpec) -> None:
    """Check an ordinary bin's lift grabber settings fit this box.

    B4B bins are validated separately, against the B4B inner mating wall and
    lid skirt (see ``organizer_b4b.validate_b4b_lift_grabbers``).
    """
    grabbers = box.lift_grabbers
    if not grabbers.enabled:
        return
    if getattr(getattr(box, "b4b", None), "enabled", False):
        return
    dims = grabbers.dimensions
    embed = _lift_grabber_embed_depth(box)
    root_bite = embed - WAVE_AMPLITUDE
    if root_bite < LIFT_GRABBER_MIN_ROOT_BITE - 1e-9:
        raise ValueError(
            f"this wall is too thin for Inside Grip to root into "
            f"({root_bite:.2f} mm of bite; {LIFT_GRABBER_MIN_ROOT_BITE:g} mm "
            "needed). Choose a thicker wall."
        )
    faces = _wall_face_table(box)
    needed = dims.width + LIFT_GRABBER_WALL_MARGIN
    checked_pairs: set[str] = set()
    for wall in grabbers.walls:
        pair = "left/right" if wall in ("+x", "-x") else "front/back"
        if pair in checked_pairs:
            continue
        _run_axis, wave_half, _face, _inward = faces[wall]
        available = 2.0 * (wave_half - CORNER_INSET)
        if available < needed:
            checked_pairs.add(pair)
            raise ValueError(
                f"{grabbers.size_label} Inside Grip does not fit on "
                f"this bin's {pair} walls. Choose a smaller size, a "
                "different location, or make the bin larger."
            )
    bottom_z = box.z - LIFT_GRABBER_RIM_CLEARANCE - dims.height
    if bottom_z < box.base_thickness + LIFT_GRABBER_FLOOR_CLEARANCE:
        raise ValueError(
            f"{grabbers.size_label} Inside Grip requires a taller bin."
        )


def make_lift_grabbers(spec: BoxSpec, rim_z: float | None = None) -> list[trimesh.Trimesh]:
    """Small support-free internal finger ledges near the top of the bin.

    ``rim_z`` lets callers with an effective body (e.g. stacking) place the
    grabbers below the *actual* physical rim rather than ``spec.z``.
    """
    grabbers = spec.lift_grabbers
    if not grabbers.enabled:
        return []
    validate_lift_grabbers(spec)
    dims = grabbers.dimensions
    rim = spec.z if rim_z is None else rim_z
    bottom_z = rim - LIFT_GRABBER_RIM_CLEARANCE - dims.height
    # The straight grabber root has two independent constraints: it must
    # reach outward past the cavity's full wave amplitude so it stays fused
    # to real wall material across its entire width, and it must stop
    # inward of the exterior wave's worst-case trough by LOCK_SAFE_SKIN.
    # _lift_grabber_embed_depth() owns that calculation.
    embed = _lift_grabber_embed_depth(spec)
    local = _lift_grabber_bulge_mesh(dims, embed)
    faces = _wall_face_table(spec)
    return [
        _place_lift_grabber(local, run_axis, face, inward, bottom_z)
        for wall in grabbers.walls
        for run_axis, _wave_half, face, inward in [faces[wall]]
    ]


def lift_grabber_keep_outs(box: BoxSpec) -> list[tuple[str, Polygon]]:
    """Conservative floor-plan keep-outs, one per active grabber wall.

    Reserves the whole 2D column under each grabber (along-wall width plus
    1 mm, inward reach plus 1 mm) rather than doing per-height collision
    testing against interior parts.
    """
    return [(name, polygon) for name, polygon, _z0, _z1
            in lift_grabber_collision_volumes(box)]


def lift_grabber_collision_volumes(
    box: BoxSpec,
) -> list[tuple[str, Polygon, float, float]]:
    """Physical XY and Z volume reserved by each active Inside Handle."""
    grabbers = box.lift_grabbers
    if not grabbers.enabled:
        return []
    dims = grabbers.dimensions
    half_width = (dims.width + 1.0) / 2.0
    reach = dims.projection + 1.0
    top_z = box.z - LIFT_GRABBER_RIM_CLEARANCE
    bottom_z = top_z - dims.height
    faces = _wall_face_table(box)
    volumes: list[tuple[str, Polygon, float, float]] = []
    for wall in grabbers.walls:
        run_axis, _wave_half, face, inward = faces[wall]
        inward_x, inward_y = inward
        if run_axis == "y":
            x0, x1 = sorted((face, face + inward_x * reach))
            y0, y1 = -half_width, half_width
        else:
            x0, x1 = -half_width, half_width
            y0, y1 = sorted((face, face + inward_y * reach))
        name = f"inside handle ({_LIFT_GRABBER_WALL_LABELS[wall]})"
        volumes.append((name, shapely_box(x0, y0, x1, y1), bottom_z, top_z))
    return volumes


def lift_grabber_summary(box: BoxSpec) -> dict | None:
    """Readout for the preview panel and generation result; ``None`` when off."""
    grabbers = box.lift_grabbers
    if not grabbers.enabled:
        return None
    location_labels = {
        "sides": "sides", "front_back": "front/back", "both": "both",
    }
    return {
        "size": grabbers.size,
        "location": grabbers.location,
        "label": f"{grabbers.size_label} — {location_labels[grabbers.location]}",
    }
