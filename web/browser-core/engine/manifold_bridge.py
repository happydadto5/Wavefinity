"""Install the double-precision bridge before importing canonical geometry.

The worker supplies callbacks around the local JS Earcut and MeshGL64 modules:
make_solid(flat_vertices_json, flat_faces_json) -> embind Solid,
read_mesh(Solid) -> JSON {vertices: flat doubles, faces: flat integers},
earcut(vertices_json, cumulative_ring_ends_json) -> JSON triangle indices.
No namespace-package bypasses, dimension restrictions, or float32 fallback.
"""
import importlib.machinery
import json
import sys
import types

import numpy as np


def install(make_solid, read_mesh, earcut, check_capacity):
    """Register native API replacements; check_capacity raises on worker limits.

    B03 supplies the combined allocated Pyodide+Manifold heap check, called
    before and after each operation. This cannot predict a single boolean's
    transient growth; allocation failures must also reach the worker error path.
    """
    if 'organizer_geometry' in sys.modules:
        raise RuntimeError('Install MeshGL64 before importing organizer_geometry')
    if not all(callable(value) for value in (make_solid, read_mesh, earcut, check_capacity)):
        raise TypeError('MeshGL64 requires geometry, Earcut and capacity callbacks')

    def coordinates(value):
        result = np.asarray(value, dtype=np.float64)
        if result.ndim != 2 or result.shape[1] != 3 or not np.isfinite(result).all():
            raise ValueError('MeshGL64 vertices must be finite Nx3 float64 coordinates')
        return result

    def indices(value, vertex_count):
        result = np.asarray(value)
        if (result.ndim != 2 or result.shape[1] != 3
                or not np.issubdtype(result.dtype, np.integer)
                or (result.size and (result.min() < 0 or result.max() >= vertex_count
                                     or result.max() > np.iinfo(np.uint32).max))):
            raise ValueError('MeshGL64 faces must be Nx3 valid uint32 vertex indices')
        return result.astype(np.uint32, copy=False)

    class Mesh64:
        def __init__(self, vert_properties, tri_verts):
            self.vert_properties = coordinates(vert_properties)
            self.tri_verts = indices(tri_verts, len(self.vert_properties))

    class Mesh:
        """Float32 twin of Mesh64, as in the real manifold3d API."""

        def __init__(self, vert_properties, tri_verts):
            self.vert_properties = coordinates(vert_properties).astype(np.float32)
            self.tri_verts = indices(tri_verts, len(self.vert_properties))

    class Manifold:
        def __init__(self, mesh=None, *, _solid=None):
            self.solid = _solid
            try:
                check_capacity()
                if _solid is None:
                    if isinstance(mesh, Mesh):
                        mesh = Mesh64(mesh.vert_properties.astype(np.float64), mesh.tri_verts)
                    if not isinstance(mesh, Mesh64):
                        raise TypeError('Manifold requires Mesh or Mesh64')
                    self.solid = make_solid(
                        json.dumps(mesh.vert_properties.ravel().tolist(), allow_nan=False),
                        json.dumps(mesh.tri_verts.ravel().tolist()))
                check_capacity()
            except Exception:
                self.close()
                raise

        def _boolean(self, other, operation):
            if self.solid is None or other.solid is None:
                raise RuntimeError('MeshGL64 solid is closed')
            check_capacity()
            return Manifold(_solid=getattr(self.solid, operation)(other.solid))

        def __add__(self, other):
            return self._boolean(other, 'add')

        def __sub__(self, other):
            return self._boolean(other, 'sub')

        def __xor__(self, other):
            return self._boolean(other, 'intersect')

        def to_mesh64(self):
            if self.solid is None:
                raise RuntimeError('MeshGL64 solid is closed')
            check_capacity()
            data = json.loads(read_mesh(self.solid))
            mesh = Mesh64(np.asarray(data['vertices'], dtype=np.float64).reshape(-1, 3),
                          np.asarray(data['faces'], dtype=np.int64).reshape(-1, 3))
            check_capacity()
            return mesh

        def to_mesh(self):
            mesh64 = self.to_mesh64()
            return Mesh(mesh64.vert_properties.astype(np.float32),
                        mesh64.tri_verts.astype(np.uint32))

        def close(self):
            solid, self.solid = self.solid, None
            if solid is not None:
                solid.delete()

        def __del__(self):
            self.close()

    def triangulate_float64(vertices, ring_end_indices):
        vertices = np.asarray(vertices, dtype=np.float64)
        ends = np.asarray(ring_end_indices)
        if (vertices.ndim != 2 or vertices.shape[1] != 2 or not np.isfinite(vertices).all()
                or ends.ndim != 1 or not np.issubdtype(ends.dtype, np.integer)
                or not ends.size or ends[0] <= 0 or ends[-1] != len(vertices)
                or np.any(np.diff(ends.astype(np.int64)) <= 0)):
            raise ValueError('Earcut requires finite Nx2 float64 vertices and cumulative ring ends')
        check_capacity()
        result = json.loads(earcut(json.dumps(vertices.tolist(), allow_nan=False),
                                   json.dumps(ends.tolist())))
        if not result:
            raise ValueError('Earcut produced no triangles')
        faces = indices(np.asarray(result).reshape(-1, 3), len(vertices))
        check_capacity()
        return faces.ravel()

    manifold = types.ModuleType('manifold3d')
    manifold.__spec__ = importlib.machinery.ModuleSpec('manifold3d', None)
    manifold.Mesh, manifold.Mesh64, manifold.Manifold = Mesh, Mesh64, Manifold
    manifold.__version__ = '3.5.0-meshgl64'
    triangulation = types.ModuleType('mapbox_earcut')
    triangulation.__spec__ = importlib.machinery.ModuleSpec('mapbox_earcut', None)
    triangulation.triangulate_float64 = triangulate_float64
    sys.modules['manifold3d'] = manifold
    sys.modules['mapbox_earcut'] = triangulation
