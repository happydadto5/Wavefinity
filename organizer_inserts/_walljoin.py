"""Shared wall-join geometry: fuse a feature's footprint into the bin wall.

Extracted from ``organizer_inserts/_bore/_walls.py``. The tab builder samples
the wall wave so the blend follows wavy walls, extends ``JOIN_BAND`` into the
wall material, and never comes within ``JOIN_SKIN`` of the exterior.
"""

from __future__ import annotations

import math

import numpy as np
import shapely
import trimesh
from shapely.geometry import LineString, Polygon, box as shapely_box

from organizer_engine import (
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    BoxSpec,
    wave_value,
    wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon

from ._core import Zone
from ._bore._consts import (
    BORE_WALL,
    HUG_REACH,
    JOIN_BAND,
    JOIN_SKIN,
    JOIN_TOUCH,
    WAVE_SAMPLES_PER_CYCLE,
)


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


def _footprint_from_solids(solids) -> "Polygon":
    """Exact plan-view footprint of trimesh solids: union of projected faces.

    Every triangle of every solid is projected to XY and the projected
    triangles are unioned. For a closed solid the projection of its surface
    is the projection of its volume, so this is the exact plan footprint -
    concavities included. (A convex hull would claim XY material where none
    exists and invent wall contact.) Degenerate projections (vertical faces
    collapsing to lines) are skipped via a shoelace-area epsilon; dropping
    a zero-area projection loses nothing because neighbouring faces cover
    the same region.
    """
    from shapely import polygons
    from shapely.ops import unary_union
    batches = []
    for s in solids:
        tris = np.asarray(s.triangles, dtype=float)
        if tris.shape[0] == 0:
            continue
        xy = tris[:, :, :2]
        x0, y0 = xy[:, 0, 0], xy[:, 0, 1]
        x1, y1 = xy[:, 1, 0], xy[:, 1, 1]
        x2, y2 = xy[:, 2, 0], xy[:, 2, 1]
        twice_area = abs(
            x0 * (y1 - y2) + x1 * (y2 - y0) + x2 * (y0 - y1))
        kept = xy[twice_area >= 2e-12]
        if len(kept):
            batches.append(polygons(kept))
    if not batches:
        return Polygon()
    return unary_union(np.concatenate(batches))


def _joined_sides(box, material, kind, along, hug=False) -> tuple:
    """Side names whose wall the plan-view ``material`` actually reaches.

    Single source of truth for the kind-specific side restrictions, shared
    by tab generation (this fixlet) and the layout reach allowance (Fused
    Walls 4) so the two can never disagree. A side counts as reached when
    the material's gap to that wall is within reach (``HUG_REACH`` in hug
    mode, ``JOIN_TOUCH`` otherwise) - the same test ``_join_tabs`` uses
    before generating a tab. Scoops only fuse on their full-height side
    ("front" for along="x", "left" for along="y"); steps only on their high
    end ("back" for along="x", "right" for along="y"); every other kind may
    join any side it reaches. Empty material reaches nothing.
    """
    reachable = HUG_REACH if hug else JOIN_TOUCH
    if material.is_empty:
        return ()
    whole = Zone.whole(box)
    x0, y0, x1, y1 = material.bounds
    gaps = {
        "right": whole.x1 - x1,
        "left": x0 - whole.x0,
        "back": whole.y1 - y1,
        "front": y0 - whole.y0,
    }
    if kind == "scoop":
        allowed = ("front",) if along == "x" else ("left",)
    elif kind == "steps":
        allowed = ("back",) if along == "x" else ("right",)
    else:
        allowed = ("right", "left", "back", "front")
    return tuple(
        side for side in allowed if gaps[side] <= reachable + 1e-9
    )


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
    sides: tuple = ("right", "left", "back", "front"),
) -> list[Polygon]:
    """Blends that carry ``material`` straight into any bin wall it reaches.

    ``material`` is the feature's plan-view footprint and ``keep_clear`` the area
    that must stay open (every hole and its wavy wall). Each side of the usable
    floor that the material touches gets a tab running from ``fill`` inside the
    wall out through the bin's wavy inner face, so the feature fuses into the
    wall instead of stopping a hair short of it. The ``sides`` tuple restricts
    which walls get tabs (default all four) - e.g. a scoop only fuses into its
    front wall, where the ramp meets it at full height. Tabs never come within
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
    # NOTE: named ``side_defs`` (not ``sides``) so it does not shadow the
    # ``sides`` parameter above. Each entry is (side name, gap, band, make).
    side_defs = (
        ("right", whole.x1 - x1,
         lambda d: shapely_box(whole.x1 - d - JOIN_BAND, -big, whole.x1 + big, big),
         lambda b, d: shapely_box(whole.x1 - d - fill, b[1], whole.x1 + reach, b[3])),
        ("left", x0 - whole.x0,
         lambda d: shapely_box(-big, -big, whole.x0 + d + JOIN_BAND, big),
         lambda b, d: shapely_box(whole.x0 - reach, b[1], whole.x0 + d + fill, b[3])),
        ("back", whole.y1 - y1,
         lambda d: shapely_box(-big, whole.y1 - d - JOIN_BAND, big, whole.y1 + big),
         lambda b, d: shapely_box(b[0], whole.y1 - d - fill, b[2], whole.y1 + reach)),
        ("front", y0 - whole.y0,
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
                if side not in sides:
                    continue
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
    for side_name, gap, band, make in side_defs:
        if side_name not in sides:
            continue
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
