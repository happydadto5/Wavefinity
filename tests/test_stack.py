"""Focused tests for stackable bins."""

from pathlib import Path
import unittest

import numpy as np

from organizer_engine import (
    B4BSpec,
    BoxSpec,
    LidSpec,
    StackSpec,
    intersection_volume,
    make_box,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_inserts import Layout
from organizer_app import design_from_dict, design_to_dict, inventory_bin_record
import organizer_features.stack as st
from wavefinity_web import catalog_payload, connector_payload


SIZES = [(48, 32, 40), (16, 16, 24), (96, 64, 60), (24, 24, 16)]


class StackSpecTests(unittest.TestCase):
    def test_mode_validation(self):
        with self.assertRaises(ValueError):
            StackSpec(mode="sideways")
        for mode in ("none", "lid", "direct"):
            self.assertEqual(StackSpec(mode=mode).mode, mode)


class LidStackRimTests(unittest.TestCase):
    def test_rim_outer_footprint_is_bin_outline_and_seat_unchanged(self):
        box = BoxSpec(48, 32, 40, lid=LidSpec(enabled=True, stack_rim=True))
        eff = st.stack_effective_box(box)
        self.assertTrue(st.lid_receives_stack(eff))
        outer = wavy_outer_polygon(eff)
        inner = st._plug_polygon(eff).buffer(st.STACK_FIT)
        rim = st._lid_stack_rim(eff)
        # Rim is extruded to STACK_SEAT_DEPTH + 0.2 over the ring footprint.
        footprint_area = rim.volume / (st.STACK_SEAT_DEPTH + 0.2)
        self.assertAlmostEqual(footprint_area, outer.area - inner.area, delta=0.05)
        self.assertTrue(np.allclose(rim.bounds[:, :2].ravel(), outer.bounds, atol=0.05))


if __name__ == "__main__":
    unittest.main()
