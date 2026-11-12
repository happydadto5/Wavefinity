"""Story 2971: only the two Gridfinity lid interfaces and their height rules."""

from dataclasses import replace
import unittest

import numpy as np

from organizer_engine import BoxSpec, LidSpec, StackSpec, make_box
from organizer_features import gridfinity as gf
from organizer_features import stack as st
from organizer_geometry import difference, intersection, translated
from organizer_inserts._walljoin import BUILD_GRID, build_grid


def overlap(a, b):
    mesh = intersection([a, b])
    if not len(mesh.faces):
        return 0.0
    with np.errstate(all="ignore"):
        volume = float(mesh.volume)
    return abs(volume) if np.isfinite(volume) else 0.0


class GridfinityLidTests(unittest.TestCase):
    def assert_single_volume(self, mesh):
        self.assertTrue(mesh.is_volume)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)

    def test_lid_closes_and_receives_same_footprint_in_both_orders(self):
        for grid, pitch in (("gridfinity", 42), ("gridfinity_half", 21)):
            for nx, ny in ((1, 1), (2, 3)):
                with self.subTest(grid=grid, cells=(nx, ny)), build_grid(grid):
                    bins = []
                    for z in (42.0, 56.0):
                        box = gf.normalize_gridfinity_settings(BoxSpec(
                            x=nx*pitch, y=ny*pitch, z=z,
                            stack=StackSpec(mode="direct"),
                            lid=LidSpec(enabled=True, stack_rim=True),
                        ), grid)
                        st.validate_stack_design(box)
                        eff = st.stack_effective_box(box)
                        body = make_box(eff, grid=grid)
                        lid, labels = st.make_lid_parts(box)
                        self.assertEqual(labels, [])
                        self.assert_single_volume(body)
                        self.assert_single_volume(lid)
                        self.assertAlmostEqual(st.stack_lid_rise(box), 1.2 + gf.rim_depth(grid))
                        self.assertAlmostEqual(max(body.bounds[1, 2], lid.bounds[1, 2]), z)
                        self.assertAlmostEqual(body.bounds[0, 2], 0.0)
                        self.assertAlmostEqual(body.bounds[1, 2], z - st.stack_lid_rise(box))
                        self.assertLess(overlap(body, lid), 1e-5)
                        # The same physical lid also clears an open receiving rim.
                        rimmed = difference([gf.gridfinity_body(eff, grid), gf.rim_cutter(eff, grid)])
                        self.assertLess(overlap(rimmed, lid), 1e-5)
                        # No socket cut reaches into the solid plate.
                        plate = gf.flat_outer_polygon(eff, grid)
                        from organizer_geometry import _extrude_polygon
                        plate_mesh = translated(_extrude_polygon(plate, 1.2), (0, 0, eff.z))
                        self.assertAlmostEqual(overlap(lid, plate_mesh), plate_mesh.volume, places=4)
                        bins.append((box, body, lid))
                    for lower, upper in (bins, bins[::-1]):
                        low_box, low_body, low_lid = lower
                        up_box, up_body, up_lid = upper
                        height = gf.assembled_lid_stack_height(low_box, up_box, grid)
                        offset = height - up_box.z
                        self.assertAlmostEqual(offset, low_box.z - gf.SEAT_DESCENT[grid])
                        self.assertAlmostEqual(st.stack_pitch(up_box), up_box.z - gf.SEAT_DESCENT[grid])
                        raised_body = translated(up_body, (0, 0, offset))
                        raised_lid = translated(up_lid, (0, 0, offset))
                        self.assertAlmostEqual(raised_lid.bounds[1, 2], height)
                        self.assertLess(overlap(low_lid, raised_body), 1e-5)
                        self.assertLess(overlap(low_body, raised_body), 1e-5)
                        self.assertLess(overlap(low_lid, raised_lid), 1e-5)

                    plain = replace(bins[0][0], lid=LidSpec(enabled=True))
                    plain_eff = st.stack_effective_box(plain)
                    plain_body = make_box(plain_eff, grid=grid)
                    plain_lid, _ = st.make_lid_parts(plain)
                    self.assert_single_volume(plain_body)
                    self.assert_single_volume(plain_lid)
                    self.assertAlmostEqual(st.stack_lid_rise(plain), 1.2)
                    self.assertAlmostEqual(plain_lid.bounds[1, 2], plain.z)
                    self.assertLess(overlap(plain_body, plain_lid), 1e-5)

    def test_one_unit_lid_is_refused_by_named_rule(self):
        for grid, pitch in (("gridfinity", 42), ("gridfinity_half", 21)):
            with self.subTest(grid=grid):
                raw = BoxSpec(x=pitch, y=pitch, z=7, lid=LidSpec(enabled=True))
                with self.assertRaisesRegex(ValueError, "Gridfinity lid minimum"):
                    gf.normalize_gridfinity_settings(raw, grid)

    def test_grid_lid_variants_stay_out_of_scope(self):
        for option in ("flip_enabled", "handle_enabled", "label_enabled"):
            with self.subTest(option=option):
                raw = BoxSpec(x=42, y=42, z=42, lid=LidSpec(enabled=True, **{option: True}))
                with self.assertRaisesRegex(ValueError, "Gridfinity Stage 1"):
                    gf.normalize_gridfinity_settings(raw, "gridfinity")

    def test_wavefinity_seat_accounting_and_context_default_are_unchanged(self):
        self.assertEqual(BUILD_GRID.get(), "wavefinity")
        for receiving in (False, True):
            box = BoxSpec(x=42, y=42, z=42, lid=LidSpec(enabled=True, stack_rim=receiving))
            self.assertEqual(st.stack_lid_rise(box), 1.2 + (st.STACK_SEAT_DEPTH if receiving else 0))
            self.assertEqual(st.stack_effective_box(box).z, box.z - st.stack_lid_rise(box))
        with build_grid("gridfinity_half"):
            self.assertEqual(st.stack_lid_rise(box), 1.2 + gf.rim_depth("gridfinity_half"))
        self.assertEqual(st.stack_lid_rise(box), 1.2 + st.STACK_SEAT_DEPTH)


if __name__ == "__main__":
    unittest.main()
