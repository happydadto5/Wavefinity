"""Focused tests for stackable bins."""

from pathlib import Path
import unittest

from organizer_engine import (
    B4BSpec,
    BoxSpec,
    LidSpec,
    StackSpec,
    intersection_volume,
    make_box,
    wavy_cavity_polygon,
)
from organizer_inserts import Layout
from organizer_app import design_from_dict, design_to_dict, inventory_bin_record
import organizer_stack as st
from wavefinity_web import catalog_payload, connector_payload


SIZES = [(48, 32, 40), (16, 16, 24), (96, 64, 60), (24, 24, 16)]


class StackSpecTests(unittest.TestCase):
    def test_defaults_inert(self):
        self.assertFalse(BoxSpec().stack.enabled)
        self.assertEqual(BoxSpec(64, 48, 40).units, (8, 6))

    def test_mode_validation(self):
        with self.assertRaises(ValueError):
            StackSpec(mode="sideways")
        for mode in ("none", "lid", "direct"):
            self.assertEqual(StackSpec(mode=mode).mode, mode)


class StackHeightTests(unittest.TestCase):
    def test_requested_height_is_the_exact_stack_pitch(self):
        for mode in ("lid", "direct"):
            for (x, y, z) in SIZES:
                with self.subTest(mode=mode, size=(x, y, z)):
                    box = BoxSpec(x=x, y=y, z=z, stack=StackSpec(mode=mode))
                    self.assertAlmostEqual(st.stack_module_height(box), z, places=6)
                    self.assertAlmostEqual(st.stack_pitch(box), z, places=6)
                    self.assertAlmostEqual(
                        st.stack_closed_height(box), z + st.stack_step_depth(box), places=6,
                    )

    def test_body_and_lid_share_one_module_datum(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        self.assertAlmostEqual(
            st.stack_effective_box(box).z + st.stack_lid_rise(box),
            40 + st.STACK_SEAT_DEPTH,
            places=6,
        )
        direct = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="direct"))
        self.assertAlmostEqual(
            st.stack_effective_box(direct).z, 40 + st.STACK_PLUG_DEPTH, places=6,
        )



class StackAutoSettingsTests(unittest.TestCase):

    def test_user_values_above_stack_minimums_are_preserved(self):
        for mode in ("lid", "direct"):
            with self.subTest(mode=mode):
                minimum = st.stack_base_minimum(
                    BoxSpec(wall=1.6, standard_walls=False, stack=StackSpec(mode=mode))
                )
                box = BoxSpec(
                    x=48, y=32, z=40, wall=1.6, base_thickness=minimum + 0.7,
                    standard_walls=False, standard_base=False, stack=StackSpec(mode=mode),
                )
                legal = st.normalize_stack_settings(box)
                self.assertEqual(legal.wall, 1.6)
                self.assertEqual(legal.base_thickness, minimum + 0.7)



class StackGeometryTests(unittest.TestCase):
    def test_parts_are_single_watertight_solids(self):
        for mode in ("lid", "direct"):
            for (x, y, z) in SIZES:
                with self.subTest(mode=mode, size=(x, y, z)):
                    box = BoxSpec(x=x, y=y, z=z, stack=StackSpec(mode=mode))
                    body = make_box(st.stack_effective_box(box))
                    self.assertTrue(body.is_watertight)
                    self.assertEqual(len(body.split(only_watertight=False)), 1)
                    if mode == "lid":
                        lid = st.make_stack_lid(box)
                        self.assertTrue(lid.is_watertight)
                        self.assertEqual(len(lid.split(only_watertight=False)), 1)

    def test_stepped_base_fits_the_mouth_it_plugs_into(self):
        for mode in ("lid", "direct"):
            for (x, y, z) in SIZES:
                with self.subTest(mode=mode, size=(x, y, z)):
                    eff = st.stack_effective_box(
                        BoxSpec(x=x, y=y, z=z, stack=StackSpec(mode=mode))
                    )
                    plug = st._plug_polygon(eff)
                    mouth = wavy_cavity_polygon(eff)
                    self.assertTrue(mouth.buffer(1e-9).contains(plug))
                    self.assertGreater(
                        plug.exterior.distance(mouth.exterior), 0.1
                    )

    def test_lid_seats_clicks_lightly_and_stays_support_free(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        body = make_box(st.stack_effective_box(box))
        lid = st.make_stack_lid(box)
        # seated: the points are in their notches, so nothing is interfering
        self.assertLess(intersection_volume(body, lid) / 1000.0, 0.02)
        # part way in: the points are still riding the wall - that is the snap
        mid = lid.copy()
        mid.apply_translation((0.0, 0.0, 0.9))
        interference = intersection_volume(body, mid) / 1000.0
        self.assertGreater(interference, 0.0001)
        self.assertLess(interference, 0.005)

        # Both bump and notch reuse the connector's support-free 45-degree form.
        for protrusion, clearance in (
            (st.STACK_FIT + st.LID_LOCK_INTERFERENCE, 0.0),
            (st.LID_LOCK_INTERFERENCE, st.LID_LOCK_CLEARANCE),
        ):
            profile = st._lid_lock_profile(protrusion, 0.0, clearance)
            for (t0, z0), (t1, z1) in zip(profile, profile[1:]):
                self.assertGreaterEqual(abs(z1 - z0) + 1e-9, abs(t1 - t0))

    def test_a_bin_stacks_on_the_closed_lid_without_fouling_it(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        body = make_box(st.stack_effective_box(box))
        lid = st.make_stack_lid(box)
        upper = body.copy()
        upper.apply_translation((0.0, 0.0, st.stack_pitch(box)))
        self.assertLess(intersection_volume(upper, lid) / 1000.0, 0.25)
        self.assertLess(intersection_volume(upper, body) / 1000.0, 0.02)

    def test_direct_bins_seat_cleanly_and_click_during_insertion(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="direct"))
        body = make_box(st.stack_effective_box(box))
        upper = body.copy()
        upper.apply_translation((0.0, 0.0, st.stack_pitch(box)))
        self.assertLess(intersection_volume(body, upper) / 1000.0, 0.03)
        partial = upper.copy()
        partial.apply_translation((0.0, 0.0, 0.9))
        self.assertGreater(intersection_volume(body, partial) / 1000.0, 0.005)

    def test_direct_snap_and_groove_share_the_same_seated_z(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="direct"))
        eff = st.stack_effective_box(box)
        lower_peak = eff.z - st.STACK_BEAD_DROP
        upper_peak = st.stack_pitch(box) + st.stack_step_depth(box) - st.STACK_BEAD_DROP
        self.assertAlmostEqual(lower_peak, upper_peak, places=6)



class StackValidationTests(unittest.TestCase):
    def test_b4b_and_bin_stacking_are_not_both_offered(self):
        from organizer_engine import B4BSpec

        box = BoxSpec(
            x=64, y=48, z=40,
            b4b=B4BSpec(enabled=True), stack=StackSpec(mode="lid"),
        )
        with self.assertRaises(ValueError):
            st.validate_stack_design(box)

    def test_too_short_to_stack_is_rejected_with_a_height(self):
        box = BoxSpec(x=48, y=32, z=7, stack=StackSpec(mode="lid"))
        with self.assertRaises(ValueError) as caught:
            st.validate_stack_design(box)
        self.assertIn("mm of height", str(caught.exception))
        # and the smallest height it names really does build
        ok = BoxSpec(x=48, y=32, z=9, stack=StackSpec(mode="lid"))
        st.validate_stack_design(ok)
        self.assertTrue(make_box(st.stack_effective_box(ok)).is_watertight)


class StackSerializationTests(unittest.TestCase):
    def test_round_trip_and_version(self):
        for mode in ("lid", "direct"):
            with self.subTest(mode=mode):
                box = BoxSpec(
                    x=48, y=32, z=40,
                    stack=StackSpec(mode="direct" if mode == "direct" else "none"),
                    lid=LidSpec(enabled=True, stackable=True) if mode == "lid" else LidSpec(),
                )
                data = design_to_dict(box, Layout((), "fused"))
                # An ordinary lid writes version 7; direct stacking stays 6.
                self.assertEqual(data["version"], 7 if mode == "lid" else 6)
                self.assertFalse(data["box"]["standard_walls"])
                self.assertFalse(data["box"]["standard_base"])
                self.assertGreaterEqual(data["box"]["wall"], st.STACK_MIN_WALL)
                self.assertGreaterEqual(
                    data["box"]["base_thickness"], st.stack_base_minimum(box),
                )
                back, *_ = design_from_dict(data)
                self.assertEqual(back.stack.mode, "direct" if mode == "direct" else "none")
                self.assertEqual(back.lid.stackable, mode == "lid")




class LidContractTests(unittest.TestCase):


    def test_legacy_stack_lid_migrates_to_lid_spec(self):
        old = design_to_dict(BoxSpec(x=48, y=32, z=40), Layout())
        old["version"] = 5
        old["box"]["stack"] = {"mode": "lid"}
        box, *_ = design_from_dict(old)
        self.assertEqual(box.stack.mode, "none")
        self.assertTrue(box.lid.enabled)
        self.assertTrue(box.lid.stackable)
        saved = design_to_dict(box, Layout())
        self.assertNotIn("stack", saved["box"])
        self.assertTrue(saved["box"]["lid"]["stackable"])



    def test_lid_disables_side_connectors(self):
        design = design_to_dict(
            BoxSpec(x=48, y=32, z=40, lid=LidSpec(enabled=True)), Layout(),
        )
        with self.assertRaisesRegex(ValueError, "unavailable.*lid"):
            connector_payload({"design": design})



if __name__ == "__main__":
    unittest.main()
