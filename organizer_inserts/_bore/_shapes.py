"""Bore wall-only and wavy-base builders."""

from __future__ import annotations

import math

import trimesh
from shapely.affinity import translate
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import unary_union
from organizer_engine import BoxSpec
from organizer_geometry import _extrude_polygon, difference, union

from ._consts import WALL_ONLY_FOOT, FLOOR_OVERTRAVEL, JOIN_BAND
from ._walls import _wall_only_ring, _union
from .._walljoin import _join_tabs, _polygons, _tab_meshes
from ._grid import _bore_hole_centres


# Overlay-noise cleanup for the wavy-base cavity (Fix 1073). A neighbour's
# ring biting into a hole's wavy cavity is a near-tangent intersection of two
# identical sine-displaced outlines, so the shapely overlay can emit a
# zero-area sliver, or a duplicate vertex (a 1e-16 edge) that earcut
# triangulates into a non-watertight solid — which manifold then rejects with
# "Not all meshes are volumes!". Both artifacts are far below any printable
# feature, so they are removed, not worked around per profile.
_CAVITY_SLIVER_AREA = 1e-4  # mm^2; cavity pieces smaller than this are dropped
_CAVITY_DEDUP_TOL = 1e-9    # mm; merges only float-noise duplicate vertices


def _deduped_ring(coords):
    """Drop consecutive vertices closer than _CAVITY_DEDUP_TOL."""
    pts = [(float(x), float(y)) for x, y in coords]
    kept = []
    for pt in pts:
        if not kept or math.hypot(pt[0] - kept[-1][0], pt[1] - kept[-1][1]) > _CAVITY_DEDUP_TOL:
            kept.append(pt)
    if len(kept) > 1 and math.hypot(kept[0][0] - kept[-1][0],
                                   kept[0][1] - kept[-1][1]) <= _CAVITY_DEDUP_TOL:
        kept.pop()
    return kept


def _deduped_polygon(piece):
    """Rebuild a cavity piece without float-noise duplicate vertices."""
    exterior = _deduped_ring(piece.exterior.coords)
    holes = [_deduped_ring(ring.coords) for ring in piece.interiors]
    return Polygon(exterior, [hole for hole in holes if len(hole) >= 3])


def _clean_cavity(cavity):
    """Drop overlay slivers and collapse duplicate vertices.

    Returns a Polygon/MultiPolygon safe to extrude and to pass as
    keep-clear geometry to _join_tabs.
    """
    pieces = [_deduped_polygon(piece) for piece in _polygons(cavity)
              if piece.area >= _CAVITY_SLIVER_AREA]
    return unary_union(pieces) if pieces else cavity


def _build_wall_only_bore(
    grid: dict, count: int | None, box: BoxSpec | None = None, join: bool = False,
    hug: bool = False,
) -> trimesh.Trimesh:
    """Perimeter sleeves rising from the base; no raised rectangular block.

    ``grid["depth"]`` is the resolved Walls Only insertion depth (Fix 078):
    the open cavity only occupies the top ``depth`` of the sleeve, and the
    local body below that stays material, forming a support-free pedestal
    down to the floor. At ``depth == height`` this is exactly the legacy
    through-to-floor geometry, including its clean-cut overtravel below the
    real floor.
    """
    profile = grid["item"].profile
    outer, inner, clear = _wall_only_ring(
        profile, grid["held"], grid["wall"], grid["wall_style"])
    height, base_z = grid["height"], grid["base_z"]
    walls_depth = min(max(grid.get("depth") or height, 0.0), height)
    through_floor = walls_depth >= height - 1e-9
    cavity_bottom = -1.0 if through_floor else (height - walls_depth)
    cavity_height = (height + 2.0) if through_floor else (walls_depth + 1.0)
    # Cut the inner wall out of the outer body with a boolean; that is sturdier
    # than triangulating a ring with a hole.
    bore = _extrude_polygon(inner, cavity_height)
    bore.apply_translation((0.0, 0.0, cavity_bottom))
    foot_layers = []
    layers = 5
    for index in range(layers):
        reach = WALL_ONLY_FOOT * (layers - index) / layers
        layer = _extrude_polygon(outer.buffer(reach, join_style="round"),
                                 WALL_ONLY_FOOT / layers + 1e-4)
        layer.apply_translation((0.0, 0.0, index * WALL_ONLY_FOOT / layers))
        foot_layers.append(layer)
    sleeve = difference([_union([_extrude_polygon(outer, height), *foot_layers]), bore])
    # The wider "keep clear" re-cut (below) shares the same cavity range, so a
    # wall-join blend or a neighbour's sleeve can never re-close the open top
    # cavity, but never drills through the new pedestal either.
    opening = _extrude_polygon(clear, cavity_height)
    opening.apply_translation((0.0, 0.0, cavity_bottom))
    sleeves, openings = [], []
    centres = list(_bore_hole_centres(grid, count))
    for x, y in centres:
        one = sleeve.copy()
        one.apply_translation((x, y, base_z))
        sleeves.append(one)
        cut = opening.copy()
        cut.apply_translation((x, y, base_z))
        openings.append(cut)
    tabs: list[trimesh.Trimesh] = []
    if join and box is not None:
        # The base foot is physical material too, so it counts toward reaching a wall.
        physical = outer.buffer(WALL_ONLY_FOOT, join_style="round")
        material = unary_union([translate(physical, x, y) for x, y in centres])
        keep_clear = unary_union([translate(inner, x, y) for x, y in centres])
        # Every outline the finished sleeve is built from, so a web edge never
        # grazes one of their vertices.
        outlines = tuple(
            unary_union([translate(outer.buffer(WALL_ONLY_FOOT * (layers - index) / layers,
                                                join_style="round") if index < layers else outer, x, y)
                         for x, y in centres])
            for index in range(layers + 1))
        tabs = _tab_meshes(
            _join_tabs(box, material, keep_clear, JOIN_BAND, hug,
                       web_width=grid["wall"], wavy=grid["wall_style"] == "wavy",
                       avoid=outlines),
            height, base_z)
    if len(sleeves) == 1 and not tabs:
        return sleeves[0]
    # Touching sleeves merge for strength; every opening is then cut again so a
    # neighbour's wall (or a wall-joining blend) can never close it.
    merged = _union(sleeves + tabs)
    return difference([merged, _union(openings)])


def _build_wavy_base_bore(
    grid: dict, count: int | None, box: BoxSpec | None = None, join: bool = False,
) -> trimesh.Trimesh:
    """A solid raised Base whose holes have Wall Only's wavy walls.

    Like Base - Straight Walls, the block is the feature's own zone (Width /
    Length and centre); the wavy hole grid is centred inside it.
    """
    outer, inner, clear = _wall_only_ring(
        grid["item"].profile, grid["held"], grid["wall"], "wavy")
    ring = outer.difference(inner)
    height, depth, base_z = grid["height"], grid["depth"], grid["base_z"]
    centres = list(_bore_hole_centres(grid, count))
    cx, cy = grid["centre_x"], grid["centre_y"]
    zone = grid["zone"]
    half_x, half_y = zone.width / 2.0, zone.depth / 2.0
    # A neighbour's wall may reach into this hole's wavy cavity, so it is kept;
    # only the requested clear opening is then re-opened in full.
    walls = unary_union([translate(ring, x, y) for x, y in centres])
    cavity = unary_union([translate(inner, x, y) for x, y in centres]).difference(walls)
    cavity = cavity.union(unary_union([translate(clear, x, y) for x, y in centres]))
    # Fix 1073: clean overlay noise before extrusion (and before the cavity
    # is reused as keep-clear geometry for wall joining below).
    cavity = _clean_cavity(cavity)
    body = trimesh.creation.box(extents=(2.0 * half_x, 2.0 * half_y, height))
    body.apply_translation((cx, cy, base_z + height / 2.0))
    # A cavity as deep as the Bore is tall reaches the normal bin floor; a hair
    # of overtravel keeps that boolean clean without touching the stored depth.
    over = FLOOR_OVERTRAVEL if depth >= height - 1e-9 else 0.0
    cuts = []
    for piece in _polygons(cavity):
        mesh = _extrude_polygon(piece, depth + 1.0 + over)
        mesh.apply_translation((0.0, 0.0, base_z + height - depth - over))
        cuts.append(mesh)
    result = difference([body, _union(cuts)])
    if join and box is not None:
        footprint = shapely_box(cx - half_x, cy - half_y, cx + half_x, cy + half_y)
        tabs = _tab_meshes(_join_tabs(box, footprint, cavity, 0.0), height, base_z)
        if tabs:
            result = union([result] + tabs)
    return result
