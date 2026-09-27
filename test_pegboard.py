from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from organizer_app import Layout, design_from_dict, design_to_dict, generate_organizer_files
from organizer_drawer import drawer_report
from organizer_engine import BoxSpec
from organizer_inventory import configure_space, load_inventory
from organizer_pegboard import (
    PegboardMountSpec,
    PEGBOARD_PROJECTION,
    _adapter_body_profile,
    _receiver_guide_profile,
    adapter_print_transform,
    apply_pegboard_mount_structure,
    make_board_adapter,
    make_board_adapters,
    pegboard_catalog,
    pegboard_layout_for_bin,
    receiver_layout,
    resolve_pegboard_size,
)
from wavefinity_web import create_space_text_payload, pegboard_layouts_payload


class PegboardSizeTests(unittest.TestCase):
    def test_physical_size_derives_grid_and_residual_border(self) -> None:
        made = resolve_pegboard_size("standard", "physical", width_mm=510, height_mm=310)
        self.assertEqual((made["holes_x"], made["holes_y"]), (20, 12))
        self.assertEqual((made["residual_x_mm"], made["residual_y_mm"]), (2.0, 5.2))

    def test_hole_count_derives_skadis_size(self) -> None:
        made = resolve_pegboard_size("skadis", "holes", holes_x=8, holes_y=12)
        self.assertEqual((made["width_mm"], made["height_mm"]), (320.0, 240.0))

    def test_space_round_trip_keeps_board_rules(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            configure_space(folder, raw_def={
                "name": "Tool wall", "kind": "pegboard", "x": 500, "y": 300,
                "pegboard_standard": "skadis", "pegboard_size_mode": "physical",
            })
            loaded = load_inventory(folder)
            space = loaded["layout"]["space"]
            drawer = loaded["layout"]["drawers"][0]
            self.assertEqual(space["pegboard_standard"], "skadis")
            self.assertEqual(drawer["boundary"], "pegboard")
            self.assertEqual(drawer["pegboard_holes_x"], 12)
            self.assertEqual(drawer["pegboard_holes_y"], 15)



class PegboardMountTests(unittest.TestCase):
    def test_design_round_trip_keeps_mount_choices(self) -> None:
        box = BoxSpec(160, 64, 112, pegboard=PegboardMountSpec(True, "standard", 3, 2))
        saved = design_to_dict(box, Layout())
        loaded, *_ = design_from_dict(saved)
        self.assertEqual(loaded.pegboard, box.pegboard)

    def test_storage_box_and_pegboard_mount_are_rejected(self) -> None:
        data = design_to_dict(BoxSpec(32, 32, 32), Layout())
        data["box"]["pegboard"] = {"enabled": True, "standard": "standard"}
        data["box"]["b4b"] = {"enabled": True, "lid": True}
        with self.assertRaisesRegex(ValueError, "ordinary bins"):
            design_from_dict(data)

    def test_manual_counts_are_grid_aligned_and_side_biased(self) -> None:
        layout = receiver_layout(160, 112, PegboardMountSpec(True, "standard", 3, 2))
        xs = sorted({one["x"] for one in layout["receivers"]})
        self.assertEqual(xs, [-67.3, -16.5, 59.7])
        self.assertEqual(layout["resolved_y"], 2)
        self.assertGreater(layout["minimum_height_mm"], 22)

    def test_invalid_manual_count_or_short_bin_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cleat Count X"):
            receiver_layout(80, 48, PegboardMountSpec(True, "standard", 6, 1))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            receiver_layout(80, 20, PegboardMountSpec(True, "standard", 1, 2))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            receiver_layout(48, 40, PegboardMountSpec(True, "standard", 1, 1))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            receiver_layout(48, 96, PegboardMountSpec(True, "standard", 1, 2))
        self.assertLessEqual(
            receiver_layout(48, 48, PegboardMountSpec(True, "standard", 1, 1))["minimum_height_mm"], 48,
        )
        self.assertEqual(receiver_layout(48, 96, PegboardMountSpec(True, "standard"))["resolved_y"], 1)
        self.assertEqual(receiver_layout(80, 40, PegboardMountSpec(True, "skadis"))["resolved_x"], 1)

    def test_standard_adapter_stays_hidden_at_minimum_height(self) -> None:
        height = 48
        receiver = receiver_layout(48, height, PegboardMountSpec(True, "standard", 1, 1))["receivers"][0]
        adapter = make_board_adapter("standard")
        placed_z = adapter.bounds[:, 2] + receiver["z"] - 42.4
        self.assertGreaterEqual(float(placed_z[0]), 0)
        self.assertLessEqual(float(placed_z[1]), height)

    def test_ribs_cover_outer_and_inner_spans_only_when_needed(self) -> None:
        narrow_single = receiver_layout(48, 48, PegboardMountSpec(True, "standard", 1, 1))
        wide_single = receiver_layout(160, 48, PegboardMountSpec(True, "standard", 1, 1))
        multi = receiver_layout(80, 48, PegboardMountSpec(True, "standard", 2, 1))
        self.assertEqual(narrow_single["ribs"], [])
        self.assertGreaterEqual(len(wide_single["ribs"]), 2)
        self.assertEqual(multi["ribs"], [])
        self.assertTrue(all(abs(x) < 160 / 2 - 2 for x in wide_single["ribs"]))
        self.assertEqual(wide_single["contact_plane_y"], PEGBOARD_PROJECTION)
        contact_edges = sorted(
            [(-160 / 2 + 3, -160 / 2 + 3), (160 / 2 - 3, 160 / 2 - 3)]
            + [(one["x"] - 7, one["x"] + 7) for one in wide_single["receivers"]]
            + [(x - 1, x + 1) for x in wide_single["ribs"]]
        )
        self.assertTrue(all(right[0] - left[1] <= 40 for left, right in zip(contact_edges, contact_edges[1:])))

    def test_body_itself_is_sloped_cleat_and_receiver_starts_at_45_degrees(self) -> None:
        for standard, center in (("standard", 42.4), ("skadis", 8.0)):
            profile = _adapter_body_profile(center)
            self.assertEqual(profile[0][0], 0)
            self.assertEqual(profile[1][0], PEGBOARD_PROJECTION)
            self.assertAlmostEqual(profile[3][1] - profile[2][1], PEGBOARD_PROJECTION)
            self.assertAlmostEqual(float(make_board_adapter(standard).bounds[1][1]), PEGBOARD_PROJECTION)
        guide = _receiver_guide_profile(20.0, 38.1)
        self.assertAlmostEqual(guide[1][1] - guide[0][1], guide[1][0] - guide[0][0])
        self.assertEqual(guide[2][1], guide[3][1])

    def test_print_transform_points_board_pegs_up(self) -> None:
        direction = adapter_print_transform() @ np.array([0.0, -1.0, 0.0, 0.0])
        np.testing.assert_allclose(direction[:3], [0.0, 0.0, 1.0], atol=1e-9)
        for standard in ("standard", "skadis"):
            box = BoxSpec(64, 64, 112, pegboard=PegboardMountSpec(True, standard, 1, 1))
            adapter = make_board_adapters(box)[0][1]
            self.assertAlmostEqual(float(adapter.bounds[0][2]), 0)
            self.assertGreater(float(adapter.bounds[1][2]), PEGBOARD_PROJECTION + 2)



    def test_generation_writes_bin_and_separate_adapter_plate(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            box = BoxSpec(32, 32, 48, pegboard=PegboardMountSpec(True, "standard", 1, 1))
            made = generate_organizer_files(box, Layout(), Path(root), part_name="Fasteners")
            self.assertTrue(Path(made["box"]["output"]).is_file())
            self.assertTrue(Path(made["pegboard_adapters"]["output"]).is_file())
            self.assertEqual(made["pegboard_adapters"]["count"], 1)


class PegboardPlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.drawer = {
            "id": "d1", "name": "Wall", "width": 254, "depth": 254, "height": 350,
            "boundary": "pegboard", "pegboard_standard": "standard",
            "pegboard_holes_x": 10, "pegboard_holes_y": 10,
            "pegboard_residual_x": 0, "pegboard_residual_y": 0,
            "clearance": 0, "anchor": "front-left", "bin_axis": "x", "snap": 8,
            "placements": [],
        }
        self.bin = {
            "id": "B1", "name": "Fasteners", "x": 48, "y": 48, "z": 48,
            "qty": 1, "stack": "none", "pegboard_standard": "standard",
            "cleat_x": "auto", "cleat_y": "auto",
        }







if __name__ == "__main__":
    unittest.main()
