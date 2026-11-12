"""Run the pinned ordinary-bin engine using a double-precision WASM bridge.

Unrelated eager exports (labels/3MF) are bypassed with namespace packages.
"""
import json
import sys
import types
import traceback
sys.path.insert(0, '/poc')
import numpy as np
import shapely
import trimesh
from js import pocEarcut

for name in ('organizer_engine', 'organizer_features'):
    package = types.ModuleType(name)
    package.__path__ = ['/poc/' + name]
    sys.modules[name] = package


def triangulate_float64(vertices, ring_end_indices):
    # Earcut JS accepts IEEE-754 doubles, with the same ring ordering as mapbox.
    return np.asarray(json.loads(pocEarcut(
        json.dumps(vertices.tolist()), json.dumps(ring_end_indices.tolist()))), dtype=np.uint32)


earcut_module = types.ModuleType('mapbox_earcut')
earcut_module.triangulate_float64 = triangulate_float64
sys.modules['mapbox_earcut'] = earcut_module

from js import pocSolid, pocMesh

class Mesh64:
    def __init__(self, vert_properties, tri_verts):
        self.vert_properties = vert_properties
        self.tri_verts = tri_verts

class Manifold:
    def __init__(self, mesh=None, solid=None):
        self.solid = solid if solid is not None else pocSolid(
            json.dumps(mesh.vert_properties.ravel().tolist()),
            json.dumps(mesh.tri_verts.ravel().tolist()))
    def __add__(self, other):
        return Manifold(solid=self.solid.add(other.solid))
    def __sub__(self, other):
        return Manifold(solid=self.solid.sub(other.solid))
    def __xor__(self, other):
        return Manifold(solid=self.solid.intersect(other.solid))
    def to_mesh64(self):
        data = json.loads(pocMesh(self.solid))
        return Mesh64(np.asarray(data['vertices'], dtype=np.float64).reshape(-1, 3),
                      np.asarray(data['faces'], dtype=np.uint64).reshape(-1, 3))
    def __del__(self):
        if hasattr(self, 'solid'):
            self.solid.delete()

manifold_module = types.ModuleType('manifold3d')
manifold_module.Mesh64 = Mesh64
manifold_module.Manifold = Manifold
sys.modules['manifold3d'] = manifold_module

from organizer_engine._specs import BoxSpec
from organizer_engine._boxes import make_box
from organizer_engine._wave import (
    nested_clearance, wave_value, wavy_outer_polygon, wavy_cavity_polygon,
)
from organizer_geometry import _extrude_polygon
from shapely.affinity import translate
from shapely.geometry import Polygon, LineString
reference = json.loads(poc_reference_json)


def poc_versions():
    return json.dumps({'python': sys.version, 'numpy': np.__version__,
                      'shapely': shapely.__version__, 'geos': shapely.geos_version_string,
                      'trimesh': trimesh.__version__})


def poc_build():
    result = {'poc_success': False, 'stl_generated': False}
    try:
        spec = BoxSpec(**reference['spec'])
        outer, cavity = wavy_outer_polygon(spec), wavy_cavity_polygon(spec)
        envelope = _extrude_polygon(outer, spec.z)
        cut = _extrude_polygon(cavity, spec.z - spec.base_thickness + 1)
        cut.apply_translation((0, 0, spec.base_thickness))
        outer_error = outer.hausdorff_distance(Polygon(reference['outer_xy']))
        cavity_error = cavity.hausdorff_distance(Polygon(reference['cavity_xy']))
        wave_error = max(abs(wave_value(y) - v) for y, v in reference['wave_samples'])
        neighbor = translate(outer, xoff=42)
        gaps = []
        for y in np.linspace(-18, 18, 145):
            line = LineString([(-30, y), (70, y)])
            gaps.append(neighbor.intersection(line).bounds[0] - outer.intersection(line).bounds[2])
        result['partial_geometry'] = {
            'outer_hausdorff_mm': outer_error, 'cavity_hausdorff_mm': cavity_error,
            'wave_max_error_mm': wave_error,
            'profiles_match': max(outer_error, cavity_error, wave_error) <= reference['tolerances']['profile_hausdorff_mm'],
            'envelope_watertight': bool(envelope.is_watertight),
            'envelope_is_volume': bool(envelope.is_volume),
            'cavity_watertight': bool(cut.is_watertight), 'cavity_is_volume': bool(cut.is_volume),
            'envelope_bounds_mm': envelope.bounds.tolist(),
            'envelope_volume_mm3': float(envelope.volume),
            'nominal_seam_mm': 0.25, 'sample_seam_min_mm': min(gaps), 'sample_seam_max_mm': max(gaps),
            'seam_matches': max(abs(g - 0.25) for g in gaps) <= reference['tolerances']['seam_mm'],
            'normal_clearance_lower_bound_mm': nested_clearance(),
            'note': 'Profiles and separate prisms only. These do not prove a finished shell or lock-bump parity.',
        }
        mesh = make_box(spec)
        result['mesh'] = {'watertight': bool(mesh.is_watertight), 'winding': bool(mesh.is_winding_consistent),
                          'volume': float(mesh.volume), 'bounds': mesh.bounds.tolist(),
                          'components': len(mesh.split()), 'triangles': len(mesh.faces)}
        result['poc_success'] = bool(mesh.is_volume and result['partial_geometry']['profiles_match'] and
             result['partial_geometry']['seam_matches'] and result['mesh']['components'] == 1 and
             np.max(np.abs(mesh.bounds - np.asarray(reference['bounds_mm']))) <= reference['tolerances']['bounds_mm'] and
             abs(mesh.volume / reference['volume_mm3'] - 1) <= reference['tolerances']['relative_volume'])
        if result['poc_success']:
            import base64
            result['stl_base64'] = base64.b64encode(mesh.export(file_type='stl')).decode()
            result['stl_generated'] = True

    except Exception as error:
        result['poc_success'] = False
        result['failure'] = str(error)
        result['traceback'] = traceback.format_exc()
    return json.dumps(result)
