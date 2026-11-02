"""Ordinary-lid handles: a Knob (grippable Mushroom or low Dome) and an arched Pull.

One resolver builds the actual handle mesh for a lid.  The label keep-out
rectangle, the reported handle height and the closed-height envelope are all
read from that same mesh's bounds, so no separate formula can drift away from
what is printed.

The handle is built with its lid-top plane at ``z = 0`` and its lowest point
``LID_HANDLE_ROOT_EMBED`` below that plane, so every root overlaps real lid
material by a positive margin before the union.  Both forms are support
conscious when the lid prints plug-down: nothing undercuts, the Dome knob blends
into the lid through a concave fillet, the Mushroom knob is a stem under a cap
whose underside flares out at no more than 45 degrees from vertical, and the Pull is a teardrop
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

LID_MUSHROOM_DIAMETER_LIMITS = (6.0, 24.0)   # cap; keeps the height inside LID_KNOB_HEIGHT_LIMITS
LID_MUSHROOM_STEM_RATIO = 1.0 / 3.0          # stem diameter, of the cap diameter
LID_MUSHROOM_STEM_MIN_RADIUS = 1.5
LID_MUSHROOM_STEM_HEIGHT = 3.0               # finger room under the cap
LID_MUSHROOM_FLARE_RUN = 1.1                 # flare height per mm of flare reach (< 45 degrees)
LID_MUSHROOM_RIM = 1.2                       # vertical cap edge
LID_MUSHROOM_CROWN_RATIO = 0.09              # domed top rise, of the cap diameter

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
    return _revolve(profile)


def _mushroom_stem_radius(diameter: float) -> float:
    return max(diameter / 2.0 * LID_MUSHROOM_STEM_RATIO, LID_MUSHROOM_STEM_MIN_RADIUS)


def _revolved_mushroom(diameter: float) -> trimesh.Trimesh:
    """A stem under a wider cap; the cap underside flares out gradually.

    The underside rises 1.1 mm for every mm it reaches outward (under 45
    degrees from vertical), so it prints without supports, and fingers can
    get under the cap around the stem.
    """
    radius = diameter / 2.0
    stem = _mushroom_stem_radius(diameter)
    blend = min(1.0, LID_MUSHROOM_STEM_HEIGHT * 0.3)
    stem_top = LID_MUSHROOM_STEM_HEIGHT
    flare_top = stem_top + (radius - stem) * LID_MUSHROOM_FLARE_RUN
    rim_top = flare_top + LID_MUSHROOM_RIM
    crown = diameter * LID_MUSHROOM_CROWN_RATIO
    profile = [(0.0, -LID_HANDLE_ROOT_EMBED),
               (stem + blend, -LID_HANDLE_ROOT_EMBED),
               (stem + blend, 0.0)]
    steps = 8
    for i in range(1, steps + 1):                       # concave fillet into the lid
        theta = -math.pi / 2.0 - (math.pi / 2.0) * i / steps
        profile.append((stem + blend + blend * math.cos(theta), blend + blend * math.sin(theta)))
    profile.append((stem, stem_top))
    profile.append((radius, flare_top))                 # straight, gradual underside
    profile.append((radius, rim_top))
    steps = 12
    for i in range(1, steps):                           # gently domed top
        phi = (math.pi / 2.0) * i / steps
        profile.append((radius * math.cos(phi), rim_top + crown * math.sin(phi)))
    profile.append((0.0, rim_top + crown))
    return _revolve(profile)


def _revolve(profile: list) -> trimesh.Trimesh:
    """Revolve an (r, z) profile, bottom centre to top centre, into a closed solid."""
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
    """A teardrop section swept over a half-ellipse; legs flare into the lid."""
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
            ca = math.cos(a)
            sa = math.sin(a)
            # Support-facing half of the ring in world coordinates: the
            # outward radial offset is ca * nrm in (u, z), so it points
            # physically downward exactly when ca * nrm[1] < 0. At the
            # arch crown nrm == [0, -1], hence ca > 0 is the underside
            # there (the previous `ca < 0` test selected the topside).
            # Along the vertical legs nrm[1] == 0, so no half is selected
            # and the legs stay round (vertical walls need no support).
            if ca * nrm[1] < 0.0:
                # Teardrop underside: 45-degree V instead of round
                # (support-free). apex puts the V point at the ring's
                # lowest world-z point for either path direction.
                apex = -math.copysign(1.0, nrm[1])
                w = apex * (1.0 - abs(sa))
                cu = w * r * nrm[0]
                cz = w * r * nrm[1]
            else:
                cu = r * ca * nrm[0]
                cz = r * ca * nrm[1]
            cv = r * sa
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
              handle_type: str, size: str, position: str,
              knob_shape: str = "mushroom") -> trimesh.Trimesh:
    min_x, min_y, max_x, max_y = outer_bounds
    span_x = max_x - min_x - 2.0 * LID_HANDLE_EDGE_MARGIN
    span_y = max_y - min_y - 2.0 * LID_HANDLE_EDGE_MARGIN
    if handle_type == "knob":
        label = "Mushroom knob" if knob_shape == "mushroom" else "Dome knob"
    else:
        label = "Pull"
    advice = "choose a smaller handle size or a larger lid/bin"
    if min(span_x, span_y) <= 0.0:
        raise ValueError(f"the {label} handle does not fit this lid; {advice}")
    cx, cy = _position_offset(position, span_x, span_y)
    if handle_type == "knob":
        mushroom = knob_shape == "mushroom"
        diameter = _clamp(min(span_x, span_y) * LID_KNOB_SCALE[size],
                          LID_MUSHROOM_DIAMETER_LIMITS if mushroom else LID_KNOB_DIAMETER_LIMITS)
        if diameter > min(span_x, span_y) + _EPS:
            raise ValueError(
                f"a {size} {label} needs about {diameter:.0f} mm of flat lid but only "
                f"{min(span_x, span_y):.1f} mm is free; {advice}"
            )
        if mushroom:
            mesh = _revolved_mushroom(diameter)
        else:
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


def resolve_lid_handle(outer_bounds, handle_type: str, size: str, position: str,
                       knob_shape: str = "mushroom") -> trimesh.Trimesh:
    """The handle mesh, lid-top plane at ``z = 0`` (a fresh copy each call)."""
    key = tuple(round(float(v), 6) for v in outer_bounds)
    return _resolved(key, handle_type, size, position, knob_shape).copy()


def handle_height(mesh: trimesh.Trimesh) -> float:
    """Height above the lid top, from the mesh itself."""
    return float(mesh.bounds[1][2])


def handle_keepout(mesh: trimesh.Trimesh) -> tuple[float, float, float, float]:
    """XY rectangle labels stay out of: the real envelope plus a safety margin."""
    (x0, y0, _z0), (x1, y1, _z1) = mesh.bounds
    m = LID_HANDLE_KEEPOUT_MARGIN
    return float(x0 - m), float(y0 - m), float(x1 + m), float(y1 + m)
