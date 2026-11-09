"""The one lid handle: a square-post knob with a diamond head.

Every lid that offers a handle (ordinary bins with resting, snap or hinged
lids) builds it here, from the parameters below, so a tweak to one number or
to the shape changes them all.

The knob is a square post, a head that flares out at 45 degrees to its widest
square ring, then tapers back at 45 degrees to a small flat top.  The head is
turned 45 degrees against the post, so it reads as a diamond from above.  The
widest ring is reached by a flare whose rise equals its outward reach, so every
downward slope is at most 45 degrees and the knob prints without supports.

The label keep-out rectangle, the reported handle height and the closed-height
envelope are all read from the mesh's bounds, so no separate formula can drift
away from what is printed.  The handle is built with its lid-top plane at
``z = 0`` and its lowest point ``LID_HANDLE_ROOT_EMBED`` below that plane, so
the root overlaps real lid material by a positive margin before the union.
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

LID_KNOB_SCALE = {"small": 0.12, "medium": 0.18, "large": 0.24}   # head width, of the free span
LID_KNOB_HEAD_LIMITS = (6.0, 14.0)           # widest head ring, side to side of the square
LID_KNOB_POST_RATIO = 0.4                    # post side, of the head width
LID_KNOB_POST_MIN = 3.0                      # smallest post side
LID_KNOB_POST_HEIGHT = 3.0                   # straight square post under the head
LID_KNOB_TOP_RATIO = 0.3                     # flat top side, of the head width
LID_KNOB_HEAD_TURN = 45.0                    # head turned this many degrees against the post

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


def _square(side: float, z: float, turn_deg: float) -> list[tuple[float, float, float]]:
    half = side / 2.0
    c = math.cos(math.radians(turn_deg))
    s = math.sin(math.radians(turn_deg))
    return [(x * c - y * s, x * s + y * c, z)
            for x, y in ((-half, -half), (half, -half), (half, half), (-half, half))]


def _solid(vertices: list, faces: list) -> trimesh.Trimesh:
    mesh = trimesh.Trimesh(vertices=np.asarray(vertices, float),
                           faces=np.asarray(faces, int), process=False)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


def _frustum(bottom: list, top: list) -> trimesh.Trimesh:
    """Loft between two squares turned the same way (corners line up)."""
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7)]
    for k in range(4):
        k2 = (k + 1) % 4
        faces += [(k, k2, 4 + k2), (k, 4 + k2, 4 + k)]
    return _solid(bottom + top, faces)


def _turned_loft(bottom: list, top: list) -> trimesh.Trimesh:
    """Loft between two squares turned 45 degrees to each other.

    Each top corner sits over the middle of a bottom edge, so the sides are
    triangles: one on each bottom edge peaking at a top corner, one on each top
    edge dropping to a bottom corner.
    """
    faces = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7)]
    for k in range(4):
        k2 = (k + 1) % 4
        faces.append((k, k2, 4 + k))
        faces.append((4 + k2, 4 + k, k2))
    return _solid(bottom + top, faces)


def _knob_mesh(head: float) -> trimesh.Trimesh:
    """The knob for a head ring ``head`` mm wide (a square side), lid top at z = 0."""
    from organizer_geometry import union

    post = max(head * LID_KNOB_POST_RATIO, LID_KNOB_POST_MIN)
    top = head * LID_KNOB_TOP_RATIO
    turn = LID_KNOB_HEAD_TURN
    post_top = LID_KNOB_POST_HEIGHT
    # The ring corner reaches head/sqrt(2) from the axis (the head is turned 45
    # degrees against the post); the flare rises one mm per mm of reach beyond
    # the post's flat, so its slope is exactly 45 degrees at the worst point.
    reach = head * math.sqrt(2.0) / 2.0 - post / 2.0
    ring_z = post_top + reach
    top_z = ring_z + (head - top) / 2.0              # 45-degree taper back to the top
    stem = trimesh.creation.box(extents=(post, post, post_top + LID_HANDLE_ROOT_EMBED))
    stem.apply_translation((0.0, 0.0, (post_top - LID_HANDLE_ROOT_EMBED) / 2.0))
    flare = _turned_loft(_square(post, post_top, 0.0), _square(head, ring_z, turn))
    cap = _frustum(_square(head, ring_z, turn), _square(top, top_z, turn))
    return union([stem, flare, cap])


@lru_cache(maxsize=256)
def _resolved(outer_bounds: tuple[float, float, float, float],
              handle_type: str, size: str, position: str) -> trimesh.Trimesh:
    min_x, min_y, max_x, max_y = outer_bounds
    span_x = max_x - min_x - 2.0 * LID_HANDLE_EDGE_MARGIN
    span_y = max_y - min_y - 2.0 * LID_HANDLE_EDGE_MARGIN
    advice = "choose a smaller handle size or a larger lid/bin"
    free = min(span_x, span_y)
    if free <= 0.0:
        raise ValueError(f"the knob handle does not fit this lid; {advice}")
    cx, cy = _position_offset(position, span_x, span_y)
    head = _clamp(free * LID_KNOB_SCALE[size], LID_KNOB_HEAD_LIMITS)
    footprint = head * math.sqrt(2.0)                # the turned head's widest reach, corner to corner
    if footprint > free + _EPS:
        raise ValueError(
            f"a {size} knob needs about {footprint:.0f} mm of flat lid but only "
            f"{free:.1f} mm is free; {advice}"
        )
    mesh = _knob_mesh(head)
    mesh.apply_translation((cx, cy, 0.0))
    return mesh


def resolve_lid_handle(outer_bounds, handle_type: str, size: str, position: str) -> trimesh.Trimesh:
    """The knob mesh, lid-top plane at ``z = 0`` (a fresh copy each call).

    ``handle_type`` is accepted for callers that still carry it; there is one
    handle, so every value builds the knob.
    """
    key = tuple(round(float(v), 6) for v in outer_bounds)
    return _resolved(key, "knob", size, position).copy()


def handle_height(mesh: trimesh.Trimesh) -> float:
    """Height above the lid top, from the mesh itself."""
    return float(mesh.bounds[1][2])


def handle_keepout(mesh: trimesh.Trimesh) -> tuple[float, float, float, float]:
    """XY rectangle labels stay out of: the real envelope plus a safety margin."""
    (x0, y0, _z0), (x1, y1, _z1) = mesh.bounds
    m = LID_HANDLE_KEEPOUT_MARGIN
    return float(x0 - m), float(y0 - m), float(x1 + m), float(y1 + m)
