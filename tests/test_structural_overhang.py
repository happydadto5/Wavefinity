"""Targeted manufacture proof in the exact production print orientations.

This checks design intent, not slicer or physical-print certification. The
3 mm bridge allowance is shared with Storage Box and requires support at
both ends; an equally small one-sided floating ledge is not a bridge.
"""
import unittest

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from organizer_b4b import B4B_SUPPORT_FREE_BRIDGE_MAX
from organizer_printer_profile import orient_mesh
from organizer_storage_drawers import prepare_new_storage_drawers_definition
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan


def section_xy(mesh, z):
    section = mesh.section(plane_origin=(0, 0, z), plane_normal=(0, 0, 1))
    if section is None:
        return Polygon()
    # XOR closed rings: internal holes must not count as supporting material.
    area = Polygon()
    for ring in section.discrete:
        if len(ring) >= 4:
            area = area.symmetric_difference(Polygon(ring[:, :2]).buffer(0))
    return area


def bridged(region, support):
    rect = np.asarray(region.minimum_rotated_rectangle.exterior.coords)[:4]
    edges = np.roll(rect, -1, axis=0) - rect
    shortest = int(np.argmin(np.linalg.norm(edges, axis=1)))
    span = float(np.linalg.norm(edges[shortest]))
    if span > B4B_SUPPORT_FREE_BRIDGE_MAX + 1e-3:
        return False
    # The short axis connects the two LONG sides. Both must meet existing
    # supporting material, including a 0.2 mm layer's permitted 45-degree grow.
    long = (shortest + 1) % 4
    opposite = (long + 2) % 4
    contacts = [LineString([rect[i], rect[(i+1) % 4]]).buffer(0.02).intersection(support).length
                for i in (long, opposite)]
    return all(length > 0.01 for length in contacts)


def unsupported_faces(mesh, layer=0.2):
    """Return face IDs with unsupported material steeper than a 45° underside."""
    failures = []
    bed = float(mesh.bounds[0, 2])
    sections = {}
    for face_id in np.flatnonzero(mesh.face_normals[:, 2] < -np.sqrt(0.5) - 1e-5):
        triangle = mesh.triangles[face_id]
        # Bed-facing triangles are supported by the build plate.
        if float(triangle[:, 2].max()) <= bed + 1e-5:
            continue
        z = float(triangle[:, 2].mean())
        key = round(z - min(layer, (z-bed)/2), 5)
        if key not in sections:
            sections[key] = section_xy(mesh, key).buffer(z-key + 1e-4)
        support = sections[key]
        footprint = Polygon(triangle[:, :2]).buffer(0)
        missing = footprint.difference(support)
        if missing.is_empty or missing.area < 1e-4:
            continue
        regions = list(missing.geoms) if hasattr(missing, "geoms") else [missing]
        if any(region.area > 1e-4 and not bridged(region, support) for region in regions):
            failures.append(int(face_id))
    return failures


class StructuralOverhangTests(unittest.TestCase):
    def test_bridge_allowance_does_not_accept_a_floating_cantilever(self):
        support = unary_union([Polygon([(0,0),(.2,0),(.2,10),(0,10)]),
                               Polygon([(2.8,0),(3,0),(3,10),(2.8,10)])])
        bridge = Polygon([(.2,0),(2.8,0),(2.8,10),(.2,10)])
        self.assertTrue(bridged(bridge, support))
        self.assertFalse(bridged(bridge, Polygon([(0,0),(.2,0),(.2,10),(0,10)])))

    def test_drawer_components_grow_from_the_bed_in_production_orientation(self):
        for style, rear, keyholes, fit, base in [
            ("full", "solid", "keyholes", .3, .4),
            ("open", "cross", "keyholes", .6, 1.6),
            ("full", "cross", "off", .4, 4.0),
        ]:
            space = prepare_new_storage_drawers_definition({
                "kind": "storage_drawers", "name": "Print proof", "x": 96, "y": 96,
                "storage_drawers": {"drawers": [{"height_mm": 40}],
                    "cabinet_style": style, "rear_support": rear, "wall_mounting": keyholes,
                    "drawer_fit_mm": fit, "drawer_base_mm": base},
            })
            plan = resolve_storage_drawers_plan(space)
            for part in plan.components:
                with self.subTest(style=style, rear=rear, fit=fit, base=base, part=part.key):
                    printed = orient_mesh(part.mesh, part.allowed_orientations[0], flip_up=part.flip_up)
                    self.assertTrue(printed.is_watertight)
                    self.assertEqual(unsupported_faces(printed), [], part.display_name)


if __name__ == "__main__":
    unittest.main()
