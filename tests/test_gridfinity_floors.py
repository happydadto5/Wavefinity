"""Story 2974 only: shared receiving floors and removable-plate records."""
import unittest
from dataclasses import replace

import numpy as np
import trimesh

from organizer_engine import B4BSpec, BoxSpec
from organizer_features.gridfinity import (
    PROFILES, EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM, container_floor_record,
    foot_solid, minimum_floor_build, socket_cutter, socket_surface_z,
)
from organizer_geometry import difference, intersection, translated
from organizer_b4b._geometry._body import make_b4b_body
from organizer_b4b._layout import b4b_layout
from organizer_b4b._outputs import b4b_summary
from organizer_inventory._space import normalise_space_definition, normalise_storage_box
from organizer_storage.drawers import (
    normalise_storage_drawers_definition, storage_drawers_defaults,
    storage_drawers_projection,
)
from organizer_storage.drawer_geometry import _make_datum, _datum_components


def box_spec(grid, nx, ny, mode="floor", lift=None):
    pitch = PROFILES[grid]["pitch"]
    return BoxSpec(x=nx*pitch, y=ny*pitch, z=35, wall=1.6,
                   base_thickness=minimum_floor_build(grid) if mode == "floor" else 1.6,
                   standard_base=False, standard_walls=False,
                   b4b=B4BSpec(enabled=True, secure_lid=False, edge_bevel="none",
                               grid=grid, built_in_grid=mode, seated_lift_mm=lift))


def cabinet(grid, nx, ny, mode="floor", lift=None):
    pitch = PROFILES[grid]["pitch"]
    block = storage_drawers_defaults(1)
    block.update(grid=grid, built_in_grid=mode, seated_lift_mm=lift,
                 drawer_handles=False,
                 drawer_base_mm=minimum_floor_build(grid) if mode == "floor" else 1.6)
    return normalise_storage_drawers_definition(dict(
        name="Floor case", kind="storage_drawers", grid=grid, built_in_grid=mode,
        x=nx*pitch, y=ny*pitch, storage_drawers=block))


def drawer_body(space):
    datum = _make_datum(space)
    definitions, _ = _datum_components(space, datum)
    maker = next(one[3] for one in definitions if one[0].startswith("drawer:"))
    mesh, _ = maker()
    centre = (datum.outer_x/2, datum.field_y/2)
    return mesh, datum.floors[0], centre


class GridfinityFloors(unittest.TestCase):
    def assert_single_solid(self, mesh):
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_volume)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)

    def assert_no_hit(self, a, b):
        hit = intersection([a, b])
        if len(hit.faces):
            # Manifold may return coplanar contact triangles with zero volume.
            # Do not ask trimesh for a centre of mass for a zero-volume contact.
            volume = abs(np.einsum("ij,ij->i", hit.triangles[:, 0],
                         np.cross(hit.triangles[:, 1], hit.triangles[:, 2])).sum() / 6)
            self.assertLess(volume, 1e-6)

    def test_builtin_fields_and_standalone_seating(self):
        for grid, profile in PROFILES.items():
            for nx, ny in ((1, 1), (2, 3)):
                with self.subTest(grid=grid, cells=(nx, ny)):
                    spec = box_spec(grid, nx, ny)
                    feet = foot_solid(spec, grid)
                    surface = socket_surface_z(grid)
                    # Independent standalone plate: retain the pitch's own relief.
                    plate = trimesh.creation.box(extents=(spec.x+4, spec.y+4, surface+1))
                    plate.apply_translation((0, 0, (surface-1)/2))
                    plate = difference([plate, socket_cutter(grid, nx, ny)])
                    self.assert_no_hit(plate, translated(feet, (0, 0, profile["seat_z"])))
                    containers = [(make_b4b_body(spec), spec.base_thickness, (0, 0)),
                                  drawer_body(cabinet(grid, nx, ny))]
                    for mesh, floor, (cx, cy) in containers:
                        self.assert_single_solid(mesh)
                        foot_bottom = floor - surface + profile["seat_z"]
                        self.assert_no_hit(mesh, translated(feet, (cx, cy, foot_bottom)))
                        # The receiving void itself must be present below the floor.
                        void = translated(socket_cutter(grid, nx, ny), (cx, cy, floor-surface))
                        self.assert_no_hit(mesh, void)
                        # The pocket did not pierce the exterior base.
                        skin = trimesh.creation.box(extents=(spec.x-1, spec.y-1, 0.4))
                        skin.apply_translation((cx, cy, floor-spec.base_thickness+0.2))
                        self.assertAlmostEqual(intersection([mesh, skin]).volume, skin.volume, places=5)

    def test_external_plate_fits_flat_cavity(self):
        clearance = EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM
        self.assertTrue(0.25 <= clearance <= 0.5)
        for grid in PROFILES:
            for nx, ny in ((1, 1), (2, 3)):
                with self.subTest(grid=grid, cells=(nx, ny)):
                    spec = box_spec(grid, nx, ny, "none")
                    record = container_floor_record(grid, "none", spec.x, spec.y)
                    self.assertEqual(record["nominal_grid_mm"], [spec.x, spec.y])
                    self.assertEqual(record["physical_cavity_mm"], [spec.x+2*clearance, spec.y+2*clearance])
                    self.assertEqual(record["external_plate_clearance_status"], "provisional")
                    self.assertIsNone(record["floor_grid"])
                    inner = b4b_layout(spec).inner_mating_polygon.bounds
                    np.testing.assert_allclose(inner, [-spec.x/2-clearance, -spec.y/2-clearance,
                                                       spec.x/2+clearance, spec.y/2+clearance])
                    for mesh, floor, (cx, cy) in [(make_b4b_body(spec), spec.base_thickness, (0, 0)),
                                                  drawer_body(cabinet(grid, nx, ny, "none"))]:
                        self.assert_single_solid(mesh)
                        plate = trimesh.creation.box(extents=(spec.x, spec.y, 5))
                        plate.apply_translation((cx, cy, floor+2.5))
                        self.assert_no_hit(mesh, plate)
                        # Flat material immediately below every part of the nominal area.
                        slab = trimesh.creation.box(extents=(spec.x, spec.y, 0.2))
                        slab.apply_translation((cx, cy, floor-0.1))
                        self.assertAlmostEqual(intersection([mesh, slab]).volume, slab.volume, places=5)

    def test_records_lift_and_roundtrip(self):
        from organizer_outputs.space import storage_box_design
        from organizer_app_impl._design_io import design_from_dict, design_to_dict
        from organizer_spaces._core import _space
        for grid in PROFILES:
            for lift in (None, 0.0, 4.25):
                with self.subTest(grid=grid, lift=lift):
                    spec = box_spec(grid, 2, 3, "none", lift)
                    raw = dict(name="Plate case", kind="portable", grid=grid, built_in_grid="none",
                               x=spec.x, y=spec.y, z=spec.z,
                               storage_box=dict(secure_lid=False, seated_lift_mm=lift))
                    saved = normalise_space_definition(raw)
                    for record in (saved, saved["storage_box"], _space(saved)):
                        self.assertEqual(record["seated_lift_mm"], lift)
                        self.assertEqual(record["seated_lift_status"], "unverified" if lift is None else "measured")
                        self.assertFalse(record["height_fit_verified"])
                        self.assertNotEqual(record["nominal_grid_mm"], record["physical_cavity_mm"])
                    design = storage_box_design(saved)
                    self.assertEqual(design["grid"], grid)
                    opened = design_from_dict(design)
                    self.assertEqual(opened[1].design_grid, grid)
                    self.assertEqual(opened[0].b4b, spec.b4b)
                    self.assertEqual(design_to_dict(opened[0], opened[1])["box"]["b4b"]["seated_lift_mm"], lift)
                    summary = b4b_summary(opened[0])
                    self.assertIsNone(summary["max_child_height_mm"])
                    self.assertIn("unverified", summary["max_child_height_text"])
                    drawers = cabinet(grid, 2, 3, "none", lift)
                    from organizer_storage.drawers import reset_storage_drawers_definition
                    self.assertEqual(reset_storage_drawers_definition(drawers)["seated_lift_mm"], lift)
                    projected = storage_drawers_projection(drawers)[0]
                    self.assertEqual(projected["seated_lift_mm"], lift)
                    self.assertEqual(projected["physical_cavity_mm"], saved["physical_cavity_mm"])

    def test_thin_floors_refuse_named_minimum(self):
        for grid in PROFILES:
            with self.subTest(grid=grid):
                spec = box_spec(grid, 2, 3)
                with self.assertRaisesRegex(ValueError, "minimum floor build: 5.8 mm"):
                    make_b4b_body(replace(spec, base_thickness=1.6))
                with self.assertRaisesRegex(ValueError, "minimum floor build: 5.8 mm"):
                    normalise_storage_box(dict(grid=grid, base_mm=1.6))
                with self.assertRaisesRegex(ValueError, "minimum floor build: 8.3 mm"):
                    normalise_storage_box(dict(grid=grid, base_mm=5.8, stacking=True))
                raw = cabinet(grid, 2, 3)
                raw["storage_drawers"]["drawer_base_mm"] = 1.6
                with self.assertRaisesRegex(ValueError, "minimum floor build: 5.8 mm"):
                    normalise_storage_drawers_definition(raw)
        for invalid in (True, -1, float("nan"), "5"):
            with self.assertRaises(ValueError):
                container_floor_record("gridfinity", "none", 42, 42, invalid)

    def test_wavefinity_floor_and_stacking_recess_remain(self):
        # Legacy settings take the existing Wavefinity branch: flat child field,
        # with the original 2.5 mm recess below an unchanged effective floor.
        spec = BoxSpec(x=84, y=126, z=35, wall=1.6, base_thickness=3.3,
                       b4b=B4BSpec(enabled=True, secure_lid=False, stacking=True, edge_bevel="none"))
        mesh = make_b4b_body(spec)
        self.assert_single_solid(mesh)
        slab = trimesh.creation.box(extents=(70, 110, 0.2))
        slab.apply_translation((0, 0, spec.base_thickness-0.1))
        self.assertAlmostEqual(intersection([mesh, slab]).volume, slab.volume, places=5)
        self.assertEqual(normalise_storage_box(None)["grid"], "wavefinity")
        self.assertIsNone(normalise_storage_box(None)["seated_lift_mm"])


if __name__ == "__main__":
    unittest.main()
