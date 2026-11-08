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
import organizer_features.stack as st
from wavefinity_web import catalog_payload, connector_payload


SIZES = [(48, 32, 40), (16, 16, 24), (96, 64, 60), (24, 24, 16)]


class StackSpecTests(unittest.TestCase):
    def test_mode_validation(self):
        with self.assertRaises(ValueError):
            StackSpec(mode="sideways")
        for mode in ("none", "lid", "direct"):
            self.assertEqual(StackSpec(mode=mode).mode, mode)


if __name__ == "__main__":
    unittest.main()
