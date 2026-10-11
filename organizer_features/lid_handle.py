"""Ordinary-lid handles: a rounded Knob and an arched Pull.

One resolver builds the actual handle mesh for a lid.  The label keep-out
rectangle, the reported handle height and the closed-height envelope are all
read from that same mesh's bounds, so no separate formula can drift away from
what is printed.

The handle is built with its lid-top plane at ``z = 0`` and its lowest point
``LID_HANDLE_ROOT_EMBED`` below that plane, so every root overlaps real lid
material by a positive margin before the union.  Both forms are support
conscious when the lid prints plug-down: nothing undercuts, the Knob is a dome
that blends into the lid through a concave fillet, and the Pull is a round
section swept over a half-ellipse with vertical legs that flare into the lid.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
import trimesh

LID_HANDLE_EDGE_MARGIN = 5.0
LID_HANDLE_ROOT_EMBED = 0.8
LID_HANDLE_KEEPOUT_MARGIN = 1.0
LID_HANDLE_OFFSET = 0.28          # centre offset of Left/Right/Front/Back, of the span

LID_KNOB_SCALE = {"small": 0.12, "medium": 0.18, "large": 0.24}
LID_KNOB_DIAMETER_LIMITS = (6.0, 28.0)      # printable / grippable envelope
LID_KNOB_HEIGHT_RATIO = 0.55
LID_KNOB_HEIGHT_LIMITS = (4.0, 16.0)
LID_KNOB_BLEND_MAX = 1.5                     # base fillet radius

LID_PULL_SCALE = {"small": 0.30, "medium": 0.45, "large": 0.60}
LID_PULL_CLEARANCE = {"small": 6.0, "medium": 8.0, "large": 10.0}
LID_PULL_WIDTH_LIMITS = (12.0, 70.0)
LID_PULL_TUBE_RADIUS = {"small": 1.6, "medium": 2.0, "large": 2.4}
LID_PULL_FOOT_FLARE = 0.5                    # extra root radius, of the tube radius
LID_PULL_THICKNESS = 3.0                     # tube diameter budget in the height

_SECTIONS = 48
_EPS = 1e-6


def _clamp(value: float, limits: tuple[float, float]) -> float:
    return max(limits[0], min(limits[1], value))


def _position_offset(position: str, span_x: float, span_y: float) -> tuple[float, float]:
    ox = max(0.0, span_x * LID_HANDLE_OFFSET)
    oy = max(0.0, span_y * LID_HANDLE_OFFSET)
    return {
        "left": (-ox, 0.0), "right": (ox, 0.0),
        "front": (0.0, -oy), "back": (0.0, oy),
        "middle": (0.0, 0.0),
    }[position]


def _close_solid(vertices: list, faces: list) -> trimesh.Trimesh:
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, float),
                           faces=np.asarray(faces, int), process=False)
    mesh.merge_vertices()
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _revolved_knob(diameter: float, height: float) -> trimesh.Trimesh:
    """A dome grip that flares into the lid through a concave fillet."""
    radius = diameter / 2.0
    blend = min(LID_KNOB_BLEND_MAX, height * 0.3)
    # (r, z) profile, bottom centre to top centre.
    profile = [(0.0, -LID_HANDLE_ROOT_EMBED),
               (radius + blend, -LID_HANDLE_ROOT_EMBED),
               (radius + blend, 0.0)]
    steps = 8
    for i in range(1, steps + 1):                       # concave fillet, tangent-ish blend
        theta = -math.pi / 2.0 - (math.pi / 2.0) * i / steps
        profile.append((radius + blend + blend * math.cos(theta), blend + blend * math.sin(theta)))
    rise = height - blend
    steps = 16
    for i in range(1, steps):                           # convex dome, horizontal at the crown
        phi = (math.pi / 2.0) * i / steps
        profile.append((radius * math.cos(phi), blend + rise * math.sin(phi)))
    profile.append((0.0, height))
    vertices: list = []
    faces: list = []
    rings: list[list[int]] = []
    bottom = len(vertices)
    vertices.append((0.0, 0.0, profile[0][1]))
    for r, z in profile[1:-1]:
        ring = []
        for k in range(_SECTIONS):
            a = 2.0 * math.pi * k / _SECTIONS
            ring.append(len(vertices))
            vertices.append((r * math.cos(a), r * math.sin(a), z))
        rings.append(ring)
    top = len(vertices)
    vertices.append((0.0, 0.0, profile[-1][1]))
    for k in range(_SECTIONS):
        k2 = (k + 1) % _SECTIONS
        faces.append((bottom, rings[0][k2], rings[0][k]))
        faces.append((top, rings[-1][k], rings[-1][k2]))
    for a, b in zip(rings, rings[1:]):
        for k in range(_SECTIONS):
            k2 = (k + 1) % _SECTIONS
            faces.append((a[k], a[k2], b[k]))
            faces.append((a[k2], b[k2], b[k]))
    return _close_solid(vertices, faces)


def _swept_arch(half_width: float, top_height: float, radius: float) -> trimesh.Trimesh:
    """A round section swept over a half-ellipse; legs flare into the lid."""
    foot = radius * (1.0 + LID_PULL_FOOT_FLARE)
    leg = half_width - foot                              # centre-line half span
    crown = top_height - radius                          # centre-line height of the crown
    path: list[tuple[float, float]] = [(leg, -LID_HANDLE_ROOT_EMBED), (leg, 0.0)]
    n = 40
    for i in range(1, n):
        t = math.pi * i / n
        path.append((leg * math.cos(t), crown * math.sin(t)))
    path.extend([(-leg, 0.0), (-leg, -LID_HANDLE_ROOT_EMBED)])
    pts = np.asarray(path, float)
    tangents = np.gradient(pts, axis=0)
    tangents /= np.maximum(np.linalg.norm(tangents, axis=1, keepdims=True), _EPS)
    normals = np.c_[-tangents[:, 1], tangents[:, 0]]     # in the (u, z) plane
    flare_height = radius * 2.5
    vertices: list = []
    faces: list = []
    rings: list[list[int]] = []
    for (u, z), nrm in zip(pts, normals):
        # The root radius eases from the flared foot to the plain section.
        ease = max(0.0, min(1.0, z / flare_height)) if z > 0.0 else 0.0
        smooth = ease * ease * (3.0 - 2.0 * ease)
        r = foot + (radius - foot) * smooth
        ring = []
        for k in range(_SECTIONS):
            a = 2.0 * math.pi * k / _SECTIONS
            cu = r * math.cos(a) * nrm[0]
            cz = r * math.cos(a) * nrm[1]
            cv = r * math.sin(a)
            ring.append(len(vertices))
            vertices.append((u + cu, cv, z + cz))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(_SECTIONS):
            k2 = (k + 1) % _SECTIONS
            faces.append((a[k], a[k2], b[k]))
            faces.append((a[k2], b[k2], b[k]))
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        centre = len(vertices)
        vertices.append(tuple(np.mean(np.asarray(vertices)[ring], axis=0)))
        for k in range(_SECTIONS):
            k2 = (k + 1) % _SECTIONS
            faces.append((centre, ring[k2], ring[k]) if flip else (centre, ring[k], ring[k2]))
    return _close_solid(vertices, faces)


@lru_cache(maxsize=256)
def _resolved(outer_bounds: tuple[float, float, float, float],
              handle_type: str, size: str, position: str) -> trimesh.Trimesh:
    min_x, min_y, max_x, max_y = outer_bounds
    span_x = max_x - min_x - 2.0 * LID_HANDLE_EDGE_MARGIN
    span_y = max_y - min_y - 2.0 * LID_HANDLE_EDGE_MARGIN
    label = "Knob" if handle_type == "knob" else "Pull"
    advice = "choose a smaller handle size or a larger lid/bin"
    if min(span_x, span_y) <= 0.0:
        raise ValueError(f"the {label} handle does not fit this lid; {advice}")
    cx, cy = _position_offset(position, span_x, span_y)
    if handle_type == "knob":
        diameter = _clamp(min(span_x, span_y) * LID_KNOB_SCALE[size], LID_KNOB_DIAMETER_LIMITS)
        if diameter > min(span_x, span_y) + _EPS:
            raise ValueError(
                f"a {size} Knob needs about {diameter:.0f} mm of flat lid but only "
                f"{min(span_x, span_y):.1f} mm is free; {advice}"
            )
        height = _clamp(diameter * LID_KNOB_HEIGHT_RATIO, LID_KNOB_HEIGHT_LIMITS)
        mesh = _revolved_knob(diameter, height)
        mesh.apply_translation((cx, cy, 0.0))
        return mesh
    run_x = position in ("front", "back") or (position == "middle" and span_x >= span_y)
    available = span_x if run_x else span_y
    cross = span_y if run_x else span_x
    width = _clamp(available * LID_PULL_SCALE[size], LID_PULL_WIDTH_LIMITS)
    radius = LID_PULL_TUBE_RADIUS[size]
    foot = radius * (1.0 + LID_PULL_FOOT_FLARE)
    if width > available + _EPS or 2.0 * foot > cross + _EPS:
        raise ValueError(
            f"a {size} Pull needs about {width:.0f} x {2.0 * foot:.0f} mm of flat lid but "
            f"only {available:.1f} x {cross:.1f} mm is free; {advice}"
        )
    clearance = min(LID_PULL_CLEARANCE[size], max(4.0, min(span_x, span_y) * 0.28))
    top = clearance + LID_PULL_THICKNESS
    mesh = _swept_arch(width / 2.0, top, radius)
    if not run_x:                                        # run along Y instead of X
        mesh.vertices = mesh.vertices[:, [1, 0, 2]]
        mesh.invert()
    mesh.apply_translation((cx, cy, 0.0))
    return mesh


def resolve_lid_handle(outer_bounds, handle_type: str, size: str, position: str) -> trimesh.Trimesh:
    """The handle mesh, lid-top plane at ``z = 0`` (a fresh copy each call)."""
    key = tuple(round(float(v), 6) for v in outer_bounds)
    return _resolved(key, handle_type, size, position).copy()


def handle_height(mesh: trimesh.Trimesh) -> float:
    """Height above the lid top, from the mesh itself."""
    return float(mesh.bounds[1][2])


def handle_keepout(mesh: trimesh.Trimesh) -> tuple[float, float, float, float]:
    """XY rectangle labels stay out of: the real envelope plus a safety margin."""
    (x0, y0, _z0), (x1, y1, _z1) = mesh.bounds
    m = LID_HANDLE_KEEPOUT_MARGIN
    return float(x0 - m), float(y0 - m), float(x1 + m), float(y1 + m)
