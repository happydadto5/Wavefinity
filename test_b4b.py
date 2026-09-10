"""Focused tests for B4B (Bin for Bins)."""

import math
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import Polygon

from organizer_engine import (
    GRID_PITCH,
    WAVE_MATING_GAP,
    B4BSpec,
    BoxSpec,
    nested_clearance,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_inserts import Feature, Layout, Zone
from organizer_app import (
    b4b_filename,
    design_from_dict,
    design_to_dict,
    generate_organizer_files,
)
import organizer_b4b as b4b


CASE_WALLS = [0.4, 0.8, 1.2, 1.6, 2.0]


class B4BSpecTests(unittest.TestCase):
    def test_defaults_inert_on_ordinary_box(self):
        self.assertFalse(BoxSpec().b4b.enabled)
        self.assertEqual(BoxSpec(), BoxSpec())
        # positional construction unaffected by the new trailing field
        self.assertEqual(BoxSpec(64, 48, 40).units, (8, 6))

    def test_enum_and_snugness_validation(self):
        for bad in ("latch_count", "latch_strength", "label_location"):
            with self.assertRaises(ValueError):
                B4BSpec(**{bad: "nope"})
        with self.assertRaises(ValueError):
            B4BSpec(lid_headroom_mm=1.5)
        for good in (0.5, 1.0, 2.0):
            self.assertEqual(B4BSpec(lid_headroom_mm=good).lid_headroom_mm, good)

    def test_normalised_drops_dependents_when_lid_off(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top", latch_count="2",
        ).normalised()
        self.assertFalse(n.secure_lid)
        self.assertFalse(n.stacking)
        self.assertEqual(n.label_location, "none")
        self.assertEqual(n.latch_count, "auto")


class B4BCapacityTests(unittest.TestCase):
    def test_formula_matches_implementation(self):
        for wall in CASE_WALLS:
            for ux in (2, 4, 6, 8, 10):
                for uy in (2, 6, 10):
                    box = BoxSpec(
                        x=ux * GRID_PITCH, y=uy * GRID_PITCH, z=40, wall=wall,
                        b4b=B4BSpec(enabled=True, secure_lid=False, lid=False),
                    )
                    eff = b4b.b4b_effective_box(box)
                    cx, cy = b4b.b4b_capacity_units(box)
                    d = eff.wall_depth
                    for axis, cap in ((eff.x, cx), (eff.y, cy)):
                        n = round(axis / GRID_PITCH)
                        want = math.floor(n - 2 * (WAVE_MATING_GAP + d) / GRID_PITCH + 1e-6)
                        self.assertEqual(cap, want)
                        self.assertGreaterEqual(cap, 1)

    def test_standard_wall_yields_outer_units_minus_one(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertEqual(b4b.b4b_capacity_units(box), (7, 5))
        self.assertEqual(b4b.b4b_capacity_mm(box), (56.0, 40.0))

    def test_capacity_uses_wall_depth_not_raw_wall(self):
        # a thicker wall reduces capacity via wall_depth, per the paper formula
        thin = b4b.b4b_capacity_units(
            BoxSpec(x=96, y=96, z=40, wall=0.4, b4b=B4BSpec(enabled=True, lid=False))
        )
        thick = b4b.b4b_capacity_units(
            BoxSpec(x=96, y=96, z=40, wall=2.0, b4b=B4BSpec(enabled=True, lid=False))
        )
        self.assertLessEqual(thick[0], thin[0])

    def test_auto_grow_tiny_box_for_one_unit_and_hinges(self):
        box = BoxSpec(x=16, y=16, z=24, b4b=B4BSpec(enabled=True))
        eff = b4b.b4b_effective_box(box)
        self.assertGreaterEqual(eff.x, b4b.B4B_SECURE_MIN_X)
        self.assertTrue(b4b.b4b_grew(box))
        cx, cy = b4b.b4b_capacity_units(box)
        self.assertGreaterEqual(min(cx, cy), 1)

    def test_stacking_reinforces_base_only_when_on(self):
        plain = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True))
        stack = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True, stacking=True))
        self.assertEqual(b4b.b4b_effective_base_thickness(plain), plain.base_thickness)
        self.assertGreaterEqual(
            b4b.b4b_effective_base_thickness(stack),
            b4b.B4B_STACK_RECESS_DEPTH + b4b.B4B_MIN_FLOOR_SKIN,
        )


class B4BRailTests(unittest.TestCase):
    def test_outer_polygon_identical_to_ordinary_box(self):
        plain = BoxSpec(x=64, y=48, z=40)
        b = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertAlmostEqual(
            wavy_outer_polygon(plain).symmetric_difference(
                wavy_outer_polygon(b4b.b4b_effective_box(b))
            ).area,
            0.0,
            places=6,
        )

    def test_mating_polygon_inside_cavity_all_walls(self):
        from organizer_engine import wavy_cavity_polygon

        for wall in CASE_WALLS:
            box = BoxSpec(x=80, y=64, z=40, wall=wall, b4b=B4BSpec(enabled=True))
            eff = b4b.b4b_effective_box(box)
            self.assertTrue(
                wavy_cavity_polygon(eff).buffer(1e-6).contains(
                    b4b.b4b_mating_polygon(box)
                )
            )

    def test_perimeter_child_field_mates_at_the_wavefinity_gap(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        cx, cy = b4b.b4b_capacity_units(box)
        child_field = BoxSpec(x=cx * GRID_PITCH, y=cy * GRID_PITCH, z=20)
        child_outer = wavy_outer_polygon(child_field)
        mating = b4b.b4b_mating_polygon(box)
        ring = b4b.b4b_rail_ring_polygon(box)
        # the child field's outer wave sits inside the mating outline, sharing
        # phase - it barely pokes past it only where corner rounding differs
        self.assertLess(child_outer.difference(mating).area, 1.0)
        # and it does not bite into the rail material
        self.assertLess(child_outer.intersection(ring).area, 1.0)
        # boundary-to-boundary separation is the ordinary Wavefinity mating gap
        gap = child_outer.exterior.distance(mating.exterior)
        self.assertGreater(gap, nested_clearance() - 0.05)
        self.assertLess(gap, WAVE_MATING_GAP + 0.05)

    def test_rail_ring_is_real_material(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertGreater(b4b.b4b_rail_ring_polygon(box).area, 50.0)


class B4BHardwareTests(unittest.TestCase):
    def test_two_symmetric_hinges_standard_screw(self):
        plan = b4b.b4b_hardware_plan(BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True)))
        self.assertEqual(plan.hinge_count, 2)
        self.assertAlmostEqual(plan.hinge_centers_x[0], -plan.hinge_centers_x[1])
        self.assertIn(plan.hinge_screw_length_mm, b4b.B4B_SCREW_LENGTHS)
        self.assertIn(plan.latch_screw_length_mm, b4b.B4B_SCREW_LENGTHS)

    def test_latch_auto_one_when_narrow_two_when_wide(self):
        narrow = b4b.b4b_hardware_plan(
            BoxSpec(x=32, y=48, z=40, b4b=B4BSpec(enabled=True))
        )
        wide = b4b.b4b_hardware_plan(
            BoxSpec(x=96, y=48, z=40, b4b=B4BSpec(enabled=True))
        )
        self.assertEqual(narrow.latch_count_resolved, 1)
        self.assertEqual(wide.latch_count_resolved, 2)

    def test_explicit_latches_positions(self):
        one = b4b.b4b_hardware_plan(
            BoxSpec(x=96, y=48, z=40, b4b=B4BSpec(enabled=True, latch_count="1"))
        )
        two = b4b.b4b_hardware_plan(
            BoxSpec(x=96, y=48, z=40, b4b=B4BSpec(enabled=True, latch_count="2"))
        )
        self.assertEqual(one.latch_centers_x, (0.0,))
        self.assertEqual(len(two.latch_centers_x), 2)
        self.assertAlmostEqual(two.latch_centers_x[0], -two.latch_centers_x[1])

    def test_strength_profiles_differ_structurally(self):
        light = b4b.B4B_LATCH_PROFILES["lightweight"]
        std = b4b.B4B_LATCH_PROFILES["standard"]
        self.assertGreater(std["hook_depth"], light["hook_depth"])
        self.assertGreater(std["pad_wall"], light["pad_wall"])


class B4BLidHeadroomTests(unittest.TestCase):
    def test_lid_underside_tracks_snugness(self):
        for snug in (0.5, 1.0, 2.0):
            box = BoxSpec(
                x=64, y=48, z=40,
                b4b=B4BSpec(enabled=True, lid_headroom_mm=snug),
            )
            eff = b4b.b4b_effective_box(box)
            self.assertAlmostEqual(
                b4b.b4b_lid_underside_z(box),
                eff.base_thickness + eff.z + snug,
            )
            self.assertEqual(b4b.b4b_max_child_height(box), eff.z)


class B4BGeometryTests(unittest.TestCase):
    CASES = {
        "case1_secure": B4BSpec(enabled=True, label_text="M3 HARDWARE", label_location="top"),
        "case3_passive": B4BSpec(enabled=True, secure_lid=False),
        "case4_nolid": B4BSpec(enabled=True, lid=False),
        "case5_stacking": B4BSpec(enabled=True, stacking=True),
    }

    def test_parts_watertight_single_component(self):
        for name, spec in self.CASES.items():
            with self.subTest(name):
                box = BoxSpec(x=80, y=64, z=40, b4b=spec)
                for pname, mesh in b4b.b4b_build_parts(box):
                    self.assertTrue(mesh.is_watertight, f"{name}/{pname} not watertight")
                    self.assertGreater(mesh.volume, 0.0)
                    if "Label" not in pname:
                        self.assertEqual(
                            len(mesh.split(only_watertight=False)), 1,
                            f"{name}/{pname} is multi-component",
                        )

    def test_body_and_lid_barely_touch_when_closed(self):
        from organizer_engine import intersection_volume

        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        body = b4b.make_b4b_body(box)
        lid = b4b.make_b4b_lid(box)
        self.assertLess(intersection_volume(body, lid) / 1000.0, 0.25)

    def test_passive_lid_has_no_hardware(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True, secure_lid=False))
        names = [n for n, _ in b4b.b4b_build_parts(box)]
        self.assertEqual(names, ["B4B Body", "B4B Lid"])

    def test_stacking_has_four_symmetric_locators(self):
        box = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True, stacking=True))
        eff = b4b.b4b_effective_box(box)
        centres = b4b._stack_locator_centres(eff)
        self.assertEqual(len(centres), 4)
        xs = sorted({round(abs(c[0]), 3) for c in centres})
        ys = sorted({round(abs(c[1]), 3) for c in centres})
        self.assertEqual(len(xs), 1)
        self.assertEqual(len(ys), 1)
        # recess does not pierce the effective base
        skin = eff.base_thickness - b4b.B4B_STACK_RECESS_DEPTH
        self.assertGreaterEqual(skin, b4b.B4B_MIN_FLOOR_SKIN - 1e-6)


class B4BValidationTests(unittest.TestCase):
    def test_rejects_interior_features(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, layout_feature_count=1)

    def test_rejects_incompatible_settings(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, layout_mode="separate")
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, easy_clean=True)
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, flat_inside=0.5)

    def test_normalisation_enforces_lid_dependencies(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top",
        ).normalised()
        self.assertEqual(n.label_location, "none")
        self.assertFalse(n.secure_lid)
        self.assertFalse(n.stacking)

    def test_design_from_dict_normalises_incompatible_json(self):
        # hand-crafted JSON bypassing the UI still loads as a coherent design
        data = {
            "version": 2,
            "box": {
                "x": 64, "y": 48, "z": 40, "wall": 0.8,
                "b4b": {"enabled": True, "lid": False, "secure_lid": True,
                        "stacking": True, "label_location": "top"},
            },
            "layout": {"mode": "fused", "features": []},
        }
        box, *_ = design_from_dict(data)
        self.assertFalse(box.b4b.secure_lid)
        self.assertFalse(box.b4b.stacking)
        self.assertEqual(box.b4b.label_location, "none")


class B4BSerializationTests(unittest.TestCase):
    def test_v2_roundtrip_retains_every_option(self):
        box = BoxSpec(
            x=64, y=48, z=40,
            b4b=B4BSpec(
                enabled=True, lid=True, secure_lid=True, latch_count="2",
                latch_strength="lightweight", lid_headroom_mm=2.0,
                label_text="Fasteners", label_location="front", stacking=True,
            ),
        )
        data = design_to_dict(box, Layout((), "fused"))
        self.assertEqual(data["version"], 2)
        back, layout, *_ = design_from_dict(data)
        self.assertEqual(back.b4b, box.b4b)
        self.assertEqual(len(layout.features), 0)
        self.assertEqual(layout.mode, "fused")

    def test_v1_without_b4b_loads_disabled(self):
        data = design_to_dict(BoxSpec(x=16, y=48, z=40), Layout((), "fused"))
        self.assertEqual(data["version"], 1)
        self.assertNotIn("b4b", data["box"])
        back, *_ = design_from_dict(data)
        self.assertFalse(back.b4b.enabled)

    def test_enabling_b4b_bumps_version(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertEqual(design_to_dict(box, Layout((), "fused"))["version"], 2)


class B4BGenerationTests(unittest.TestCase):
    def test_case1_generates_full_object_set(self):
        box = BoxSpec(
            x=64, y=48, z=40,
            b4b=B4BSpec(enabled=True, label_text="M3 HARDWARE", label_location="top"),
        )
        with tempfile.TemporaryDirectory() as d:
            res = generate_organizer_files(
                box, Layout((), "fused"), Path(d), part_name="Fasteners",
                keep_log=True,
            )
            self.assertEqual(res["mode"], "b4b")
            self.assertEqual(
                res["object_names"],
                ["B4B Body", "B4B Lid", "B4B Top Label", "B4B Latch 1", "B4B Latch 2"],
            )
            out = Path(res["output"])
            self.assertTrue(out.is_file())
            self.assertTrue(out.name.startswith("B4B 64x48x40"))
            log = Path(res["log_file"]).read_text()
            self.assertIn("B4B 7x5 units", log)

    def test_filename_distinct_from_ordinary_bin(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertNotIn("Box 64", b4b_filename(box))
        self.assertTrue(b4b_filename(box).startswith("B4B "))

    def test_passive_and_nolid_object_sets(self):
        with tempfile.TemporaryDirectory() as d:
            passive = generate_organizer_files(
                BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True, secure_lid=False)),
                Layout((), "fused"), Path(d),
            )
            self.assertEqual(passive["object_names"], ["B4B Body", "B4B Lid"])
            nolid = generate_organizer_files(
                BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True, lid=False)),
                Layout((), "fused"), Path(d), part_name="nolid",
            )
            self.assertEqual(nolid["object_names"], ["B4B Body"])


if __name__ == "__main__":
    unittest.main()
