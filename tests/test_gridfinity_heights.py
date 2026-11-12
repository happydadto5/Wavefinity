"""Story 2970 (Gridfinity Stage 1, S1-04): height model and the optional stacking rim.

Targeted reproduction checks: Stackable carries the receiving rim and Not
Stackable does not, on both pitches, 1x1 and 2x3; the height numbers are the
model's own; the minimum legal heights are refused at normalization.
"""

from dataclasses import replace
import unittest

import numpy as np
import trimesh

from organizer_app_impl._design_io import design_from_dict, design_to_dict
from organizer_engine import BoxSpec
from organizer_engine._boxes import make_box
from organizer_engine._specs import StackSpec
from organizer_features import gridfinity as gf
from organizer_geometry import difference, intersection, translated
from organizer_inserts import Layout

PITCHES = ("gridfinity", "gridfinity_half")
SIZES = {
    "gridfinity": ((42.0, 42.0), (84.0, 126.0)),
    "gridfinity_half": ((21.0, 21.0), (42.0, 63.0)),
}
STACKED = StackSpec(mode="direct")


def spec(grid, size, z=42.0, stackable=False, **changes):
    box = BoxSpec(
        x=size[0], y=size[1], z=z, stack=STACKED if stackable else StackSpec(), **changes)
    return gf.normalize_gridfinity_settings(box, grid)


def volume(mesh):
    if not len(mesh.faces):
        return 0.0
    with np.errstate(all="ignore"):      # a sliver intersection can be zero-volume
        result = float(mesh.volume)
    return result if np.isfinite(result) else 0.0


def overlap(a, b):
    return volume(intersection([a, b]))


def cell_width(mesh, z, centre, pitch):
    segments = trimesh.intersections.mesh_plane(mesh, (0.0, 0.0, 1.0), (0.0, 0.0, z))
    points = segments.reshape(-1, 3)
    near = points[(abs(points[:, 0] - centre[0]) < pitch / 2)
                  & (abs(points[:, 1] - centre[1]) < pitch / 2)]
    return float(np.ptp(near[:, 0]))


class HeightModelTests(unittest.TestCase):
    def test_known_specs_report_the_models_numbers(self):
        box = spec("gridfinity", (42.0, 42.0), z=42.0)
        self.assertEqual(gf.nominal_height_units(box, "gridfinity"), 6.0)
        self.assertEqual(gf.exterior_height(box, "gridfinity"), 42.0)
        self.assertEqual(gf.interior_depth(box, "gridfinity"), 42.0 - 5.75)
        tall = spec("gridfinity", (42.0, 42.0), z=56.0)
        self.assertEqual(gf.nominal_height_units(tall, "gridfinity"), 8.0)
        # a thicker base moves the floor, and with it the interior depth
        thick = spec("gridfinity", (42.0, 42.0), z=42.0, base_thickness=7.0)
        self.assertEqual(gf.interior_depth(thick, "gridfinity"), 35.0)
        # two stacked bins: both exteriors less the seat descent (0.35 at 42 mm)
        self.assertAlmostEqual(gf.SEAT_DESCENT["gridfinity"], 0.35, places=9)
        self.assertAlmostEqual(gf.assembled_stack_height(box, tall, "gridfinity"), 97.65, places=9)
        self.assertAlmostEqual(gf.assembled_stack_height(tall, box, "gridfinity"), 97.65, places=9)
        small = spec("gridfinity_half", (21.0, 21.0), z=42.0)
        self.assertAlmostEqual(gf.SEAT_DESCENT["gridfinity_half"], 0.25, places=9)
        self.assertAlmostEqual(gf.assembled_stack_height(small, small, "gridfinity_half"), 83.75, places=9)
        with self.assertRaises(ValueError):
            gf.nominal_height_units(box, "wavefinity")

    def test_minimum_legal_heights(self):
        for grid in PITCHES:
            self.assertEqual(gf.minimum_height_units(grid, stackable=False), 1)
            self.assertEqual(gf.minimum_height_units(grid, stackable=True), 2)
        # floor + rim: 11 + 3.8 = 14.8 mm needs 3 units, not 2
        self.assertEqual(gf.minimum_height_units("gridfinity", True, floor=11.0), 3)
        # exactly 14 mm (10.2 + 3.8) still fits in 2 units
        self.assertEqual(gf.minimum_height_units("gridfinity", True, floor=10.2), 2)

    def test_profile_data_per_pitch(self):
        self.assertEqual(gf.RIM_PROFILES["gridfinity"], (
            (0.0, 36.3, 1.15), (0.7, 37.7, 1.85), (2.5, 37.7, 1.85), (3.8, 40.3, 3.15)))
        self.assertEqual(gf.rim_depth("gridfinity"), 3.8)
        self.assertEqual(gf.RIM_TIP_THEORETICAL, (4.4, 41.5, 3.75))
        self.assertAlmostEqual(gf.RIM_TIP_THEORETICAL[0] - gf.RIM_TIP_TRIM, gf.rim_depth("gridfinity"))
        small = gf.RIM_PROFILES["gridfinity_half"]
        # the 21 mm rim is its own foot (14.6 / 16.2 / 20.5) plus clearance, not a scaled 42
        for (z, width, radius), clearance in zip(small, (0.25, 0.25, 0.25, 0.35)):
            self.assertAlmostEqual(width, gf.foot_polygon("gridfinity_half", z).bounds[2] * 2 + 2 * clearance, places=6)
            self.assertAlmostEqual(width / 2.0 - radius, 6.5, places=6)    # the +/-6.5 centres
        self.assertNotAlmostEqual(small[0][1] * 2, gf.RIM_PROFILES["gridfinity"][0][1])
        self.assertEqual(gf.rim_depth("gridfinity_half"), 4.75)


class NormalizationTests(unittest.TestCase):
    def test_non_whole_unit_z_is_refused_with_the_rule_named(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                x, y = SIZES[grid][0]
                with self.assertRaisesRegex(ValueError, "whole number of 7 mm height units"):
                    gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=40.0), grid)

    def test_sub_minimum_plain_z_is_refused(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                x, y = SIZES[grid][0]
                with self.assertRaisesRegex(ValueError, "at least 1 height unit"):
                    gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=6.0), grid)
                self.assertEqual(gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=14.0), grid).z, 14.0)

    def test_sub_minimum_stackable_z_is_refused(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                x, y = SIZES[grid][0]
                with self.assertRaisesRegex(ValueError, "at least 2 height units"):
                    gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=7.0, stack=STACKED), grid)
                ok = gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=14.0, stack=STACKED), grid)
                self.assertEqual(ok.z, 14.0)

    def test_design_io_refuses_through_both_normalization_points(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                x, y = SIZES[grid][0]
                raw = BoxSpec(x=x, y=y, z=40.0)
                with self.assertRaisesRegex(ValueError, "whole number of 7 mm"):
                    design_to_dict(raw, replace(Layout(), design_grid=grid))
                saved = design_to_dict(raw, Layout())
                saved["grid"] = grid
                with self.assertRaisesRegex(ValueError, "whole number of 7 mm"):
                    design_from_dict(saved)
        # wavefinity keeps its free Z
        raw = BoxSpec(x=42.0, y=42.0, z=40.0)
        self.assertIs(gf.normalize_gridfinity_settings(raw, "wavefinity"), raw)
        self.assertEqual(design_from_dict(design_to_dict(raw, Layout()))[0].z, 40.0)


class StackingRimTests(unittest.TestCase):
    def test_rim_is_present_exactly_when_stackable_and_every_body_is_one_solid(self):
        for grid in PITCHES:
            for size in SIZES[grid]:
                with self.subTest(grid=grid, size=size):
                    plain_box = spec(grid, size)
                    stack_box = spec(grid, size, stackable=True)
                    plain = make_box(plain_box, grid=grid)
                    stack = make_box(stack_box, grid=grid)
                    for mesh in (plain, stack):
                        self.assertTrue(mesh.is_watertight and mesh.is_volume)
                        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                        self.assertAlmostEqual(float(mesh.bounds[1][2]), 42.0, delta=1e-9)
                    cutter = gf.rim_cutter(stack_box, grid)
                    self.assertTrue(cutter.is_watertight and cutter.is_volume)
                    # Not Stackable: the plain flat top, so the cutter would still bite it
                    self.assertGreater(overlap(plain, cutter), 1e-3)
                    # Stackable: the rim is cut, so nothing of the body is left in the void
                    self.assertLess(overlap(stack, cutter), 1e-6)
                    self.assertAlmostEqual(
                        volume(plain) - volume(stack), overlap(plain, cutter), delta=1e-3)
                    # the cutter spans exactly the profile depth below the rim
                    self.assertAlmostEqual(float(cutter.bounds[0][2]), 42.0 - gf.rim_depth(grid), delta=1e-9)

    def test_rim_cutter_follows_the_profile_table_per_cell(self):
        for grid in PITCHES:
            box = spec(grid, SIZES[grid][1], stackable=True)
            cutter = gf.rim_cutter(box, grid)
            pitch = gf.PROFILES[grid]["pitch"]
            centre = gf._cell_centres(box, grid)[0]
            top = box.z
            widest = pitch - 0.5 - 2.0 * gf.RIM_MIN_WALL
            for depth, width, _radius in gf.RIM_PROFILES[grid][:-1]:
                with self.subTest(grid=grid, depth=depth):
                    # sample just inside the band so a vertex plane never is the section
                    z = top - depth - (1e-4 if depth == 0.0 else 0.0)
                    self.assertAlmostEqual(cell_width(cutter, z, centre, pitch), min(width, widest), delta=0.01)
            self.assertEqual(len(gf._cell_centres(box, grid)), 6)

    def test_upper_foot_seats_in_the_rim_with_zero_intersection_in_both_orders(self):
        for grid in PITCHES:
            pitch = gf.PROFILES[grid]["pitch"]
            descent = gf.SEAT_DESCENT[grid]
            for size in SIZES[grid]:
                for lower_z, upper_z in ((28.0, 42.0), (42.0, 28.0)):
                    with self.subTest(grid=grid, size=size, lower=lower_z, upper=upper_z):
                        lower_box = spec(grid, size, z=lower_z, stackable=True)
                        upper_box = spec(grid, size, z=upper_z, stackable=True)
                        lower = make_box(lower_box, grid=grid)
                        cutter = gf.rim_cutter(lower_box, grid)
                        feet = gf.foot_solid(upper_box, grid)
                        stack = gf.assembled_stack_height(lower_box, upper_box, grid)
                        self.assertAlmostEqual(stack, lower_z + upper_z - descent, places=9)
                        # the upper bin's origin sits at stack - its own height
                        seated = translated(feet, (0.0, 0.0, stack - upper_z))
                        self.assertAlmostEqual(float(seated.bounds[0][2]), lower_z - descent, delta=1e-9)
                        self.assertLess(overlap(seated, lower), 1e-6)
                        # below the rim plane the foot lies wholly inside the receiving void
                        below = trimesh.creation.box(
                            extents=(400.0, 400.0, 20.0),
                            transform=trimesh.transformations.translation_matrix((0.0, 0.0, lower_z - 10.0)))
                        in_mouth = intersection([seated, below])
                        self.assertGreater(volume(in_mouth), 0.0)
                        self.assertLess(volume(difference([in_mouth, cutter])), 1e-3)
                        # a foot stood on the datum clears the opening by the chamfer
                        # clearance; sunk by the descent its chamfer lands on the edge
                        centre = gf._cell_centres(lower_box, grid)[0]
                        opening = cell_width(cutter, lower_z - 1e-4, centre, pitch)
                        datum = translated(feet, (0.0, 0.0, lower_z))
                        clearance = (opening - cell_width(datum, lower_z + 1e-4, centre, pitch)) / 2.0
                        self.assertAlmostEqual(clearance, descent, delta=0.01)
                        landed = cell_width(seated, lower_z - 1e-4, centre, pitch)
                        self.assertAlmostEqual(landed, opening, delta=0.01)

    def test_wavefinity_stacking_is_unchanged(self):
        from organizer_features.stack import normalize_stack_settings
        box = normalize_stack_settings(BoxSpec(x=42.0, y=42.0, z=40.0, stack=STACKED))
        self.assertIs(gf.normalize_gridfinity_settings(box, "wavefinity"), box)
        plain = make_box(box)
        explicit = make_box(box, grid="wavefinity")
        self.assertAlmostEqual(volume(plain), volume(explicit), delta=1e-6)
        self.assertTrue(explicit.is_watertight and explicit.is_volume)


if __name__ == "__main__":
    unittest.main()
