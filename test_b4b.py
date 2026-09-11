"""Focused tests for B4B (Bin for Bins)."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon

from organizer_engine import (
    GRID_PITCH,
    WAVE_MATING_GAP,
    B4BSpec,
    BoxSpec,
    nested_clearance,
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

    def test_legacy_nolid_normalises_to_lid_only(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top", latch_count="2",
        ).normalised()
        self.assertTrue(n.lid)
        self.assertFalse(n.secure_lid)
        self.assertFalse(n.stacking)
        self.assertEqual(n.label_location, "top")
        self.assertEqual(n.latch_count, "auto")


class B4BCapacityTests(unittest.TestCase):
    def test_selected_dimensions_are_exact_child_field(self):
        for wall in CASE_WALLS:
            for ux in (2, 4, 6, 8, 10):
                for uy in (2, 6, 10):
                    box = BoxSpec(
                        x=ux * GRID_PITCH, y=uy * GRID_PITCH, z=40, wall=wall,
                        b4b=B4BSpec(enabled=True, secure_lid=False, lid=False),
                    )
                    self.assertEqual(b4b.b4b_capacity_units(box), (ux, uy))
                    self.assertEqual(
                        b4b.b4b_capacity_mm(box),
                        (ux * GRID_PITCH, uy * GRID_PITCH),
                    )

    def test_32_by_48_means_four_by_six_child_field(self):
        box = BoxSpec(x=32, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertEqual(b4b.b4b_capacity_units(box), (4, 6))
        self.assertEqual(b4b.b4b_capacity_mm(box), (32, 48))

    def test_wall_thickness_changes_case_outside_not_capacity(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        thin = b4b.b4b_layout(BoxSpec(
            x=64, y=48, z=40, wall=0.4, b4b=B4BSpec(enabled=True)
        ))
        thick = b4b.b4b_layout(BoxSpec(
            x=64, y=48, z=40, wall=2.0, b4b=B4BSpec(enabled=True)
        ))
        self.assertEqual(b4b.b4b_capacity_units(box), (8, 6))
        self.assertGreater(thick.case_size[0], thin.case_size[0])
        self.assertGreater(thick.case_size[1], thin.case_size[1])

    def test_auto_grow_tiny_box_for_one_unit_and_hinges(self):
        box = BoxSpec(x=16, y=16, z=24, b4b=B4BSpec(enabled=True))
        eff = b4b.b4b_effective_box(box)
        self.assertGreaterEqual(eff.x, b4b.B4B_SECURE_MIN_FIELD_X)
        self.assertTrue(b4b.b4b_grew(box))
        cx, cy = b4b.b4b_capacity_units(box)
        self.assertGreaterEqual(min(cx, cy), 1)

    def test_latched_lid_grows_to_printable_minimum_height(self):
        latched = BoxSpec(x=64, y=48, z=12, b4b=B4BSpec(enabled=True))
        lid_only = BoxSpec(
            x=64, y=48, z=12, b4b=B4BSpec(enabled=True, secure_lid=False),
        )
        self.assertEqual(b4b.b4b_effective_box(latched).z, b4b.B4B_LATCHED_MIN_HEIGHT)
        self.assertEqual(b4b.b4b_effective_box(lid_only).z, 12)

    def test_stacking_reinforces_base_only_when_on(self):
        plain = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True))
        stack = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True, stacking=True))
        self.assertEqual(b4b.b4b_effective_base_thickness(plain), plain.base_thickness)
        self.assertGreaterEqual(
            b4b.b4b_effective_base_thickness(stack),
            b4b.B4B_STACK_RECESS_DEPTH + b4b.B4B_MIN_FLOOR_SKIN,
        )


class B4BWallTests(unittest.TestCase):
    def test_outer_wall_is_derived_outward_from_inner_mating_face(self):
        for wall in CASE_WALLS:
            box = BoxSpec(x=80, y=64, z=40, wall=wall, b4b=B4BSpec(enabled=True))
            layout = b4b.b4b_layout(box)
            self.assertTrue(
                layout.outer_structural_polygon.buffer(1e-6).contains(
                    layout.inner_mating_polygon
                )
            )
            self.assertGreater(
                layout.outer_structural_polygon.difference(
                    layout.inner_mating_polygon
                ).area,
                1.0,
            )

    def test_perimeter_child_field_mates_at_the_wavefinity_gap(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        cx, cy = b4b.b4b_capacity_units(box)
        child_field = BoxSpec(x=cx * GRID_PITCH, y=cy * GRID_PITCH, z=20)
        child_outer = wavy_outer_polygon(child_field)
        mating = b4b.b4b_mating_polygon(box)
        # the child field's outer wave sits inside the mating outline, sharing
        # phase - it barely pokes past it only where corner rounding differs
        self.assertLess(child_outer.difference(mating).area, 1.0)
        # boundary-to-boundary separation is the ordinary Wavefinity mating gap
        gap = child_outer.exterior.distance(mating.exterior)
        self.assertGreater(gap, nested_clearance() - 0.05)
        self.assertLess(gap, WAVE_MATING_GAP + 0.05)

    def test_body_has_flat_floor_and_full_height_perimeter_wall(self):
        box = BoxSpec(x=32, y=48, z=30, base_thickness=0.8,
                      b4b=B4BSpec(enabled=True, secure_lid=False))
        body = b4b.make_b4b_body(box)
        layout = b4b.b4b_layout(box)
        self.assertAlmostEqual(body.bounds[0][2], 0.0, places=5)
        # The cavity begins at one flat Z plane; the perimeter is structural
        # wall all the way up rather than a short raised floor ring.
        wall_band = layout.outer_structural_polygon.difference(
            layout.inner_mating_polygon
        )
        p = wall_band.representative_point()
        self.assertTrue(body.contains([[p.x, p.y, box.z - 1.0]])[0])


class B4BHardwareTests(unittest.TestCase):
    def test_two_symmetric_hinges_standard_screw(self):
        plan = b4b.b4b_hardware_plan(BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True)))
        self.assertEqual(plan.hinge_count, 2)
        self.assertAlmostEqual(plan.hinge_centers_x[0], -plan.hinge_centers_x[1])
        self.assertIn(plan.hinge_screw_length_mm, b4b.B4B_SCREW_LENGTHS)
        self.assertIn(plan.latch_screw_length_mm, b4b.B4B_SCREW_LENGTHS)
        self.assertIn(plan.catch_screw_length_mm, b4b.B4B_SCREW_LENGTHS)

    def test_hinges_are_flush_and_body_gussets_stay_near_top(self):
        box = BoxSpec(x=32, y=48, z=30, base_thickness=0.8,
                      b4b=B4BSpec(enabled=True))
        plan = b4b.b4b_hardware_plan(box)
        lid_top = b4b.b4b_lid_underside_z(box) + b4b.B4B_LID_SKIN
        self.assertLessEqual(
            plan.hinge_axis_z + b4b.B4B_HINGE_KNUCKLE_RADIUS,
            lid_top + 1e-6,
        )
        for part in b4b._hinge_body_parts(box, plan):
            self.assertGreater(part.bounds[0][2], box.z - 8.1)

    def test_body_latch_is_compact_cross_pin_receiver(self):
        box = BoxSpec(x=32, y=48, z=30, base_thickness=0.8,
                      b4b=B4BSpec(enabled=True))
        plan = b4b.b4b_hardware_plan(box)
        ears = b4b._latch_body_parts(box, plan)
        self.assertEqual(len(ears), 2 * plan.latch_count_resolved)
        self.assertTrue(all(ear.bounds[0][2] > box.z - 8.1 for ear in ears))
        self.assertLess(
            b4b.b4b_layout(box).case_bounds[1] - min(e.bounds[0][1] for e in ears),
            9.0,
        )

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

    def test_blank_label_preference_creates_no_label_parts(self):
        for location in ("top", "front"):
            with self.subTest(location=location):
                box = BoxSpec(
                    x=64, y=48, z=40,
                    b4b=B4BSpec(enabled=True, label_location=location),
                )
                names = [name for name, _mesh in b4b.b4b_build_parts(box)]
                self.assertFalse(any("Label" in name for name in names))
                self.assertEqual(b4b.b4b_summary(box)["label_location"], "none")

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
        lid = b4b.make_b4b_lid(box)
        lid_top = b4b.b4b_lid_underside_z(box) + b4b.B4B_LID_SKIN
        self.assertLessEqual(lid.bounds[1][2], lid_top + 1e-5)
        names = [name for name, _mesh in b4b.b4b_build_parts(box)]
        self.assertEqual(sum(name.startswith("B4B Stacking Peg") for name in names), 4)

    def test_latch_lever_prints_flat_on_its_broad_face(self):
        # The lever's hook profile is a broad, flat extrusion end-cap; printed
        # it must rest on that whole face (no support under a curved edge).
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True, secure_lid=True))
        names_and_meshes = b4b.b4b_build_parts(box)
        levers = [mesh for name, mesh in names_and_meshes if "Latch" in name]
        self.assertTrue(levers)
        for lever in levers:
            zmin = lever.bounds[0][2]
            on_plate = np.all(np.isclose(lever.vertices[lever.faces][:, :, 2], zmin, atol=1e-3), axis=1)
            bottom_faces = lever.faces[on_plate]
            v = lever.vertices[bottom_faces]
            area = 0.5 * np.linalg.norm(
                np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1
            ).sum()
            self.assertGreater(area, 20.0)


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

    def test_legacy_nolid_normalisation_keeps_lid_only(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top",
        ).normalised()
        self.assertTrue(n.lid)
        self.assertEqual(n.label_location, "top")
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
        self.assertTrue(box.b4b.lid)
        self.assertFalse(box.b4b.secure_lid)
        self.assertFalse(box.b4b.stacking)
        self.assertEqual(box.b4b.label_location, "top")


class B4BSerializationTests(unittest.TestCase):
    def test_v3_roundtrip_retains_every_option_and_field_size(self):
        box = BoxSpec(
            x=64, y=48, z=40,
            b4b=B4BSpec(
                enabled=True, lid=True, secure_lid=True, latch_count="2",
                latch_strength="lightweight", lid_headroom_mm=2.0,
                label_text="Fasteners", label_location="front", stacking=True,
            ),
        )
        data = design_to_dict(box, Layout((), "fused"))
        self.assertEqual(data["version"], 3)
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
        self.assertEqual(design_to_dict(box, Layout((), "fused"))["version"], 3)

    def test_v2_physical_dimensions_migrate_to_old_child_capacity(self):
        data = {
            "version": 2,
            "box": {
                "x": 64, "y": 48, "z": 40, "wall": 0.8,
                "b4b": {"enabled": True, "secure_lid": False},
            },
            "layout": {"mode": "fused", "features": []},
        }
        back, *_ = design_from_dict(data)
        self.assertEqual((back.x, back.y), (56, 40))
        self.assertEqual(b4b.b4b_capacity_units(back), (7, 5))


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
            self.assertIn("B4B 8x6 units", log)

    def test_filename_distinct_from_ordinary_bin(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertNotIn("Box 64", b4b_filename(box))
        self.assertTrue(b4b_filename(box).startswith("B4B "))

    def test_passive_and_legacy_nolid_object_sets(self):
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
            self.assertEqual(nolid["object_names"], ["B4B Body", "B4B Lid"])


if __name__ == "__main__":
    unittest.main()
