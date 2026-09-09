"""Shared, feature-neutral mesh construction helpers."""

from __future__ import annotations

import numpy as np
import trimesh
from shapely.geometry import Polygon


def translated(
    mesh: trimesh.Trimesh, xyz: tuple[float, float, float]
) -> trimesh.Trimesh:
    result = mesh.copy()
    result.apply_translation(xyz)
    return result


def _cleaned(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Clean boolean leftovers without breaking a previously watertight mesh."""
    was_watertight = mesh.is_watertight
    cleaned = mesh.copy()
    cleaned.remove_unreferenced_vertices()
    cleaned.merge_vertices()
    if was_watertight and not cleaned.is_watertight:
        return mesh
    return cleaned


def union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return _cleaned(trimesh.boolean.union(meshes, engine="manifold"))


def difference(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return _cleaned(trimesh.boolean.difference(meshes, engine="manifold"))


def intersection(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return _cleaned(trimesh.boolean.intersection(meshes, engine="manifold"))


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
    """Extrude an X/Z section across world Y."""
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
    """Sweep a closed ``(t, z)`` profile along a planar path."""
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
        for index in range(loop):
            next_index = (index + 1) % loop
            faces.append((a + index, a + next_index, b + next_index))
            faces.append((a + index, b + next_index, b + index))
    for index in range(1, loop - 1):
        faces.append((0, index, index + 1))
    last = (rings - 1) * loop
    for index in range(1, loop - 1):
        faces.append((last, last + index + 1, last + index))

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
        raise RuntimeError("swept profile is not a clean solid")
    return mesh


def _resampled_ring(polygon: Polygon, count: int) -> np.ndarray:
    """Return a counter-clockwise, evenly spaced exterior ring."""
    boundary = polygon.exterior
    ring = np.asarray([
        boundary.interpolate(boundary.length * index / count).coords[0]
        for index in range(count)
    ], dtype=float)
    if not polygon.exterior.is_ccw:
        ring = ring[::-1]
    return ring


def _align_ring(reference: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Rotate a same-sized ring so equivalent perimeter points line up."""
    start = int(np.argmin(np.sum((ring - reference[0]) ** 2, axis=1)))
    return np.roll(ring, -start, axis=0)


def _loft_cavity(rings: list[np.ndarray], heights: list[float]) -> trimesh.Trimesh:
    """Create one closed solid through matching horizontal rings."""
    if len(rings) != len(heights) or len(rings) < 2:
        raise ValueError("a loft needs at least two matching rings")
    count = len(rings[0])
    if any(len(ring) != count for ring in rings):
        raise ValueError("loft rings must have matching point counts")

    vertices = [
        (float(x), float(y), height)
        for ring, height in zip(rings, heights)
        for x, y in ring
    ]
    faces: list[tuple[int, int, int]] = []
    for level in range(len(rings) - 1):
        low, high = level * count, (level + 1) * count
        for index in range(count):
            next_index = (index + 1) % count
            faces.append((low + index, low + next_index, high + next_index))
            faces.append((low + index, high + next_index, high + index))

    for ring, height, reverse in (
        (rings[0], heights[0], True), (rings[-1], heights[-1], False)
    ):
        cap = Polygon(ring)
        cap_vertices, cap_faces = trimesh.creation.triangulate_polygon(
            cap, engine="earcut"
        )
        offset = len(vertices)
        vertices.extend((float(x), float(y), height) for x, y in cap_vertices)
        for face in cap_faces:
            triangle = tuple(offset + int(index) for index in face)
            faces.append(triangle[::-1] if reverse else triangle)

    mesh = trimesh.Trimesh(
        vertices=np.asarray(vertices, dtype=float),
        faces=np.asarray(faces, dtype=np.int64),
        process=True,
    )
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise RuntimeError("lofted solid is not clean")
    return mesh
