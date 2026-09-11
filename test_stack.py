"""Focused tests for stackable bins."""

import unittest

from organizer_engine import (
    BoxSpec,
    StackSpec,
    intersection_volume,
    make_box,
    wavy_cavity_polygon,
)
from organizer_inserts import Layout
from organizer_app import design_from_dict, design_to_dict
import organizer_stack as st


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
    def test_closed_height_is_always_what_was_asked(self):
        # The whole promise: turning stacking on never changes how tall the
        # finished bin is.  In lid mode the lid plate is taken out of the body
        # to pay for itself.
        for mode in ("lid", "direct"):
            for (x, y, z) in SIZES:
                with self.subTest(mode=mode, size=(x, y, z)):
                    box = BoxSpec(x=x, y=y, z=z, stack=StackSpec(mode=mode))
                    self.assertAlmostEqual(st.stack_closed_height(box), z, places=6)

    def test_lid_mode_shortens_the_body_direct_does_not(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        self.assertAlmostEqual(
            st.stack_effective_box(box).z, 40 - st.STACK_LID_SKIN, places=6
        )
        direct = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="direct"))
        self.assertAlmostEqual(st.stack_effective_box(direct).z, 40, places=6)

    def test_pitch_is_shorter_than_the_bin_by_its_engagement(self):
        for mode in ("lid", "direct"):
            box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode=mode))
            self.assertAlmostEqual(
                st.stack_pitch(box),
                st.stack_closed_height(box) - st.stack_step_depth(box),
                places=6,
            )
            self.assertLess(st.stack_pitch(box), box.z)


class StackAutoSettingsTests(unittest.TestCase):
    def test_thin_wall_is_raised_for_the_snap_groove(self):
        box = BoxSpec(x=48, y=32, z=40, wall=0.8, stack=StackSpec(mode="direct"))
        self.assertAlmostEqual(st.stack_effective_box(box).wall, st.STACK_MIN_WALL)
        self.assertTrue(st.stack_grew(box))

    def test_a_thick_enough_wall_is_left_alone(self):
        box = BoxSpec(x=48, y=32, z=40, wall=1.6, stack=StackSpec(mode="direct"))
        self.assertAlmostEqual(st.stack_effective_box(box).wall, 1.6)

    def test_floor_grows_to_contain_the_stepped_base(self):
        # The step is cut out of the floor plate - a plug that fits the mouth
        # above has no wall left by definition - so the floor has to be deeper
        # than the step or the cut would sever the walls from the base.
        for mode in ("lid", "direct"):
            with self.subTest(mode=mode):
                box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode=mode))
                eff = st.stack_effective_box(box)
                self.assertGreaterEqual(
                    eff.base_thickness,
                    st.stack_step_depth(box) + st.STACK_MIN_FLOOR_SKIN - 1e-9,
                )


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

    def test_lid_seats_clean_but_still_has_to_click_past_the_bead(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        body = make_box(st.stack_effective_box(box))
        lid = st.make_stack_lid(box)
        # seated: the bead is in the groove, so nothing is interfering
        self.assertLess(intersection_volume(body, lid) / 1000.0, 0.02)
        # part way in: the bead is still riding the wall - that is the snap
        mid = lid.copy()
        mid.apply_translation((0.0, 0.0, 0.9))
        self.assertGreater(intersection_volume(body, mid) / 1000.0, 0.005)

    def test_a_bin_stacks_on_the_closed_lid_without_fouling_it(self):
        box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode="lid"))
        body = make_box(st.stack_effective_box(box))
        lid = st.make_stack_lid(box)
        upper = body.copy()
        upper.apply_translation((0.0, 0.0, st.stack_pitch(box)))
        self.assertLess(intersection_volume(upper, lid) / 1000.0, 0.25)
        self.assertLess(intersection_volume(upper, body) / 1000.0, 0.02)


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
                box = BoxSpec(x=48, y=32, z=40, stack=StackSpec(mode=mode))
                data = design_to_dict(box, Layout((), "fused"))
                self.assertEqual(data["version"], 4)
                back, *_ = design_from_dict(data)
                self.assertEqual(back.stack.mode, mode)

    def test_an_ordinary_bin_carries_no_stack_block(self):
        data = design_to_dict(BoxSpec(x=48, y=32, z=40), Layout((), "fused"))
        self.assertEqual(data["version"], 1)
        self.assertNotIn("stack", data["box"])
        back, *_ = design_from_dict(data)
        self.assertFalse(back.stack.enabled)


if __name__ == "__main__":
    unittest.main()
