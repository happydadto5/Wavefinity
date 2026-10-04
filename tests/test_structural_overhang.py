"""Targeted manufacture proof in the exact production print orientations.

This checks design intent, not slicer or physical-print certification. The
3 mm bridge allowance is shared with Storage Box and requires support at
both ends; an equally small one-sided floating ledge is not a bridge.
"""
import dataclasses
import unittest
from unittest import mock

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from organizer_b4b import B4B_SUPPORT_FREE_BRIDGE_MAX
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import prepare_new_storage_drawers_definition
import organizer_storage_drawer_geometry as geometry
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan
from organizer_storage_drawer_outputs import _oriented_parts

BED_DEFAULT = {"x_mm": 256.0, "y_mm": 256.0, "z_mm": 256.0}


def cabinet(style, rear, keyholes, fit, base):
    return prepare_new_storage_drawers_definition({
        "kind": "storage_drawers", "name": "Print proof", "x": 96, "y": 96,
        "storage_drawers": {"drawers": [{"height_mm": 40}],
            "cabinet_style": style, "rear_support": rear, "wall_mounting": keyholes,
            "drawer_fit_mm": fit, "drawer_base_mm": base},
    })


def production_print(part, bed):
    """The exported body, oriented exactly as Save Cabinet does: the orientation
    comes from component_fit(), then the production transform with flip_up.
    Returns (None, "") when production would refuse the part on this bed."""
    fit = component_fit(part.bounds_xyz, part.allowed_orientations, normalise_printer_profile(bed))
    if not fit["fits"]:
        return None, ""
    body, _groups = _oriented_parts(part, fit["orientation"])
    return body, fit["orientation"]


def section_xy(mesh, z):
    """Material cross-section at height z (even-odd fill), without scipy."""
    from trimesh.intersections import mesh_plane
    from shapely.geometry import Point
    from shapely.ops import polygonize
    segments = mesh_plane(mesh, plane_normal=(0, 0, 1), plane_origin=(0, 0, z))
    if segments is None or len(segments) == 0:
        return Polygon()
    segments = np.round(segments[:, :, :2], 5)
    segments = segments[np.any(segments[:, 0] != segments[:, 1], axis=1)]
    cells = list(polygonize(unary_union([LineString(seg) for seg in segments])))
    a, b = segments[:, 0], segments[:, 1]
    filled = []
    for cell in cells:
        px, py = cell.representative_point().coords[0]
        crosses = (a[:, 1] > py) != (b[:, 1] > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            x_at = a[:, 0] + (py - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
        if int(np.count_nonzero(crosses & (x_at > px))) % 2 == 1:
            filled.append(cell)
    return unary_union(filled)


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

    def test_detector_flags_wide_shelves_and_accepts_ramps_and_short_bridges(self):
        import trimesh
        def box(x0, y0, z0, x1, y1, z1):
            mesh = trimesh.creation.box(extents=(x1-x0, y1-y0, z1-z0))
            mesh.apply_translation(((x0+x1)/2, (y0+y1)/2, (z0+z1)/2))
            return mesh
        # A stem with a 6 mm cantilevered shelf: unsupported downward face.
        shelf = trimesh.util.concatenate([box(0, 0, 0, 10, 10, 10), box(10, 0, 5, 16, 10, 7)])
        self.assertTrue(unsupported_faces(shelf))
        # The same ledge with a 45-degree underside is self-supporting.
        profile = Polygon([(10, 5), (16, 11), (16, 12), (10, 12)])
        ramp = trimesh.creation.extrude_polygon(profile, 10)
        ramp.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
        ramped = trimesh.util.concatenate([box(0, 0, 0, 10, 10, 12), ramp])
        self.assertEqual(unsupported_faces(ramped), [])
        # A 2.5 mm roof between two posts is a permitted short bridge.
        bridge = trimesh.util.concatenate([box(0, 0, 0, 2, 10, 10), box(4.5, 0, 0, 6.5, 10, 10),
                                           box(2, 0, 8, 4.5, 10, 10)])
        self.assertEqual(unsupported_faces(bridge), [])

    def test_drawer_components_grow_from_the_bed_in_production_orientation(self):
        chosen_non_first = set()
        for style, rear, keyholes, fit, base, bed in [
            ("full", "solid", "keyholes", .3, .4, BED_DEFAULT),
            ("open", "cross", "keyholes", .6, 1.6, BED_DEFAULT),
            ("full", "cross", "off", .4, 4.0, BED_DEFAULT),
            # Narrow beds make production pick a non-first orientation.
            ("full", "cross", "off", .4, .8, {"x_mm": 112.0, "y_mm": 256.0, "z_mm": 256.0}),
            ("full", "cross", "off", .4, .8, {"x_mm": 256.0, "y_mm": 100.0, "z_mm": 256.0}),
            ("full", "cross", "off", .4, .8, {"x_mm": 256.0, "y_mm": 256.0, "z_mm": 40.0}),
        ]:
            plan = resolve_storage_drawers_plan(cabinet(style, rear, keyholes, fit, base))
            for part in plan.components:
                with self.subTest(style=style, rear=rear, fit=fit, base=base, bed=bed, part=part.key):
                    printed, orientation = production_print(part, bed)
                    if printed is None:
                        continue  # production would refuse this part on this bed
                    if orientation != part.allowed_orientations[0]:
                        chosen_non_first.add(orientation)
                    self.assertTrue(printed.is_watertight)
                    self.assertEqual(unsupported_faces(printed), [], part.display_name)
        self.assertTrue(chosen_non_first, "no case exercised a non-first orientation")

    def test_original_rear_orientation_is_rejected(self):
        """Fix 114 3B regression: the rear used to print without flip_up."""
        part = next(p for p in resolve_storage_drawers_plan(cabinet("full", "solid", "keyholes", .3, .4)).components
                    if p.key == "rear_solid")
        self.assertTrue(part.flip_up)
        printed, _orientation = production_print(part, BED_DEFAULT)
        self.assertEqual(unsupported_faces(printed), [])
        original, _orientation = production_print(dataclasses.replace(part, flip_up=False), BED_DEFAULT)
        self.assertTrue(unsupported_faces(original))

    def test_original_full_dovetail_is_rejected(self):
        """Fix 114 3D regression: both flanks of the side dovetails were angled."""
        def original(center_x, y0, y1, root_z, direction, land, *, female=False, **_ignored):
            head, neck, length = land, 0.70 * land, 0.55 * land
            section = Polygon([(center_x-neck/2, root_z), (center_x+neck/2, root_z),
                               (center_x+head/2, root_z+direction*length),
                               (center_x-head/2, root_z+direction*length)])
            if female:
                section = section.buffer(geometry.SD_JOINT_CLEARANCE_MM, join_style=2)
            else:
                z1 = root_z - direction * 0.25
                section = unary_union([section, geometry.shape_box(center_x-neck/2, min(root_z, z1),
                                                                  center_x+neck/2, max(root_z, z1))])
            solid = geometry._extrude_polygon(section, y1 - y0)
            solid.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, y0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
            return solid
        space = cabinet("full", "solid", "off", .4, .8)
        repaired = next(p for p in resolve_storage_drawers_plan(space).components if p.key == "side_left")
        self.assertEqual(unsupported_faces(production_print(repaired, BED_DEFAULT)[0]), [])
        with mock.patch.object(geometry, "_sliding_dovetail", original):
            old = next(p for p in resolve_storage_drawers_plan(space).components if p.key == "side_left")
        self.assertTrue(unsupported_faces(production_print(old, BED_DEFAULT)[0]))


if __name__ == "__main__":
    unittest.main()
