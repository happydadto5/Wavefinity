"""Run unmodified pinned ordinary-bin sources in Pyodide, fail at Mesh64.

Only unrelated eager exports (labels/3MF) are bypassed with namespace packages.
Neither the geometry implementation nor its precision rule is replaced.
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

BOOLEAN_ERROR = (
    'FLOAT64_BOOLEAN_UNAVAILABLE: canonical organizer_geometry._boolean requires '
    'manifold3d.Mesh64 and to_mesh64(); Pyodide 0.28.3 has no manifold3d package; '
    'manifold-3d@3.5.0 exposes Float32Array Mesh, not Mesh64. '
    'No float32 fallback was used.'
)


def missing_mesh64(*args, **kwargs):
    raise RuntimeError(BOOLEAN_ERROR)


# Import sentinel, not a substitute geometry engine. The first real boolean
# fails at the exact unavailable constructor in the authoritative source.
manifold_module = types.ModuleType('manifold3d')
manifold_module.Mesh64 = missing_mesh64
manifold_module.Manifold = missing_mesh64
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
    result = {'poc_success': False, 'stl_generated': False,
              'full_mesh_comparison': 'Unavailable: first float64 boolean cannot run.',
              'connector': 'Not investigated: ordinary bin has not succeeded.'}
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
        make_box(spec)  # Actual canonical path, not a precomputed mesh replay.
        raise RuntimeError('Unexpected Mesh64 availability: requalify bridge before claiming parity')
    except Exception as error:
        result['failure'] = str(error)
        result['traceback'] = traceback.format_exc()
    return json.dumps(result)
