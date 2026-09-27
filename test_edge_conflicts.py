from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import organizer_app
from organizer_app import BoxSpec, Layout, StackSpec
from organizer_edge_mount import EdgeMountSpec
from organizer_engine import LidSpec
from test_inventory_safety import BatchFixture, design, record
from organizer_inventory import change_design_status, load_inventory, save_design_source
from test_space_preferences import function_source, node_run


def box(label_type="separate", side="front", label=True, lid=False, holes=False, direct=False):
    return BoxSpec(
        48.0, 56.0, 40.0,
        edge_mount=EdgeMountSpec(
            side=side, label_enabled=label, label_text="A" if label else "",
            label_type=label_type, holes_enabled=holes,
        ),
        lid=LidSpec(enabled=True) if lid else LidSpec(),
        stack=StackSpec(mode="direct") if direct else StackSpec(),
    )


class EdgeMountLabelConflictTests(unittest.TestCase):
    def preview(self, spec, label="", location="back"):
        return organizer_app.preview_geometry(spec, label, (), "fused", location, False)

    def generate(self, spec, label="", location="back"):
        with tempfile.TemporaryDirectory() as directory:
            return organizer_app.generate_organizer_files(
                spec, Layout((), "fused"), Path(directory), label=label, label_location=location)

    def test_same_wall_rim_label_rejected_in_preview_and_generation(self):
        spec = box(side="front")
        with self.assertRaisesRegex(ValueError, "same Front wall"):
            self.preview(spec, "Rim", "front")
        with self.assertRaisesRegex(ValueError, "same Front wall"):
            self.generate(spec, "Rim", "front")


    def test_lid_with_separate_rejected_but_integrated_and_screws_allowed(self):
        with self.assertRaisesRegex(ValueError, "with a lid"):
            self.preview(box(lid=True))
        with self.assertRaisesRegex(ValueError, "with a lid"):
            self.generate(box(lid=True))
        organizer_app.validate_edge_mount_label_conflicts(box(label_type="integrated", lid=True), "", "back")
        organizer_app.validate_edge_mount_label_conflicts(box(label=False, holes=True, lid=True), "Rim", "front")

    def test_saved_label_type_is_not_rewritten(self):
        spec = box(lid=True)
        with self.assertRaises(ValueError):
            self.preview(spec)
        self.assertEqual(spec.edge_mount.label_type, "separate")

    def test_direct_stack_with_separate_rejected_but_integrated_and_screws_allowed(self):
        spec = box(direct=True)
        with self.assertRaisesRegex(ValueError, "direct Stackable Bin"):
            self.preview(spec)
        with self.assertRaisesRegex(ValueError, "direct Stackable Bin"):
            self.generate(spec)
        self.assertEqual(spec.stack.mode, "direct")
        organizer_app.validate_edge_mount_label_conflicts(
            box(label_type="integrated", direct=True), "", "back")
        organizer_app.validate_edge_mount_label_conflicts(
            box(label=False, holes=True, direct=True), "", "back")

    def test_saved_direct_stack_separate_label_round_trips_then_rejects(self):
        original = box(direct=True)
        saved = organizer_app.design_to_dict(original, Layout())
        loaded, *_ = organizer_app.design_from_dict(saved)
        self.assertTrue(loaded.edge_mount.label_enabled)
        self.assertEqual(loaded.edge_mount.label_type, "separate")
        self.assertEqual(loaded.stack.mode, "direct")
        with self.assertRaisesRegex(ValueError, "direct Stackable Bin"):
            self.preview(loaded)
        with self.assertRaisesRegex(ValueError, "direct Stackable Bin"):
            self.generate(loaded)






if __name__ == "__main__":
    unittest.main()
