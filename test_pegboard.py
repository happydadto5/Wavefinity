from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from organizer_app import Layout, design_from_dict, design_to_dict, generate_organizer_files
from organizer_drawer import drawer_report
from organizer_engine import BoxSpec
from organizer_inventory import configure_space, load_inventory
from organizer_pegboard import (
    PegboardMountSpec,
    apply_pegboard_mount_structure,
    make_board_adapters,
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

    def test_hosted_space_creation_keeps_board_fields(self) -> None:
        made = create_space_text_payload({
            "inventory_text": "", "inventory_title": "Wall", "name": "Wall",
            "kind": "pegboard", "x": 320, "y": 240, "z": 350,
            "pegboard_standard": "skadis", "pegboard_size_mode": "holes",
            "pegboard_holes_x": 8, "pegboard_holes_y": 12,
        })
        self.assertEqual(made["layout"]["space"]["pegboard_standard"], "skadis")
        self.assertIn('"boundary": "pegboard"', made["inventory_text"])


class PegboardMountTests(unittest.TestCase):
    def test_design_round_trip_keeps_mount_choices(self) -> None:
        box = BoxSpec(160, 64, 80, pegboard=PegboardMountSpec(True, "standard", 3, 2))
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
        layout = receiver_layout(160, 80, PegboardMountSpec(True, "standard", 3, 2))
        xs = sorted({one["x"] for one in layout["receivers"]})
        self.assertEqual(xs, [-67.3, -16.5, 59.7])
        self.assertEqual(layout["resolved_y"], 2)
        self.assertGreater(layout["minimum_height_mm"], 22)

    def test_invalid_manual_count_or_short_bin_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Cleat Count X"):
            receiver_layout(80, 40, PegboardMountSpec(True, "standard", 6, 1))
        with self.assertRaisesRegex(ValueError, "does not fit"):
            receiver_layout(80, 20, PegboardMountSpec(True, "standard", 1, 2))

    def test_ribs_only_bridge_large_unsupported_gaps(self) -> None:
        narrow = receiver_layout(64, 40, PegboardMountSpec(True, "standard", 2, 1))
        wide = receiver_layout(160, 40, PegboardMountSpec(True, "standard", 2, 1))
        self.assertEqual(narrow["ribs"], [])
        self.assertTrue(wide["ribs"])

    def test_receiver_and_both_adapter_families_are_printable_meshes(self) -> None:
        for standard in ("standard", "skadis"):
            box = BoxSpec(96, 64, 64, pegboard=PegboardMountSpec(True, standard, 2, 2))
            body = __import__("trimesh").creation.box((box.x, box.y, box.z))
            mounted = apply_pegboard_mount_structure(box, body)
            self.assertGreater(mounted.volume, body.volume)
            # The rear support must not grow beyond the side mating envelope.
            self.assertAlmostEqual(float(mounted.bounds[0][0]), float(body.bounds[0][0]))
            self.assertAlmostEqual(float(mounted.bounds[1][0]), float(body.bounds[1][0]))
            adapters = make_board_adapters(box)
            self.assertEqual(len(adapters), 4)
            self.assertTrue(all(mesh.is_watertight for _, mesh in adapters))
            self.assertEqual(len({round(float(mesh.centroid[0]), 3) for _, mesh in adapters}), 4)

    def test_generation_writes_bin_and_separate_adapter_plate(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            box = BoxSpec(32, 32, 32, pegboard=PegboardMountSpec(True, "standard", 1, 1))
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
            "id": "B1", "name": "Fasteners", "x": 48, "y": 48, "z": 40,
            "qty": 1, "stack": "none", "pegboard_standard": "standard",
            "cleat_x": "auto", "cleat_y": "auto",
        }

    def test_layout_exposes_footprint_and_exact_mounts(self) -> None:
        layout = pegboard_layout_for_bin(self.bin, "standard")
        self.assertEqual((layout["cells_x"], layout["cells_y"]), (2, 2))
        self.assertEqual(layout["mount_offsets"], [[0.0, 0], [0.0, 1]])
        payload = pegboard_layouts_payload({"standard": "standard", "bins": [self.bin]})
        self.assertEqual(payload["layouts"]["B1"]["mount_offsets"], [[0.0, 0], [0.0, 1]])

    def test_report_rejects_unsnapped_outside_overlap_and_wrong_standard(self) -> None:
        other = {**self.bin, "id": "B2", "pegboard_standard": "skadis"}
        self.drawer["placements"] = [
            {"bin": "B1", "copy": 0, "gx": 0.5, "gy": 0},
            {"bin": "B1", "copy": 1, "gx": 9, "gy": 9},
            {"bin": "B2", "copy": 0, "gx": 0, "gy": 0},
        ]
        report = drawer_report(self.drawer, [self.bin, other])
        kinds = {problem["type"] for problem in report["problems"]}
        self.assertTrue({"outside", "mount"}.issubset(kinds))

    def test_ordinary_inventory_bin_without_receiver_is_incompatible(self) -> None:
        ordinary = {**self.bin, "pegboard_standard": ""}
        layout = pegboard_layout_for_bin(ordinary, "standard")
        self.assertFalse(layout["compatible"])

    def test_report_returns_selected_mount_positions(self) -> None:
        self.drawer["placements"] = [{"bin": "B1", "copy": 0, "gx": 2, "gy": 3}]
        report = drawer_report(self.drawer, [self.bin])
        self.assertFalse(report["problems"])
        self.assertEqual(report["mounts"], [
            {"gx": 2, "gy": 3, "key": "B1:0"},
            {"gx": 2, "gy": 4, "key": "B1:0"},
        ])


class PegboardBrowserContractTests(unittest.TestCase):
    def test_setup_mount_controls_and_board_view_are_wired(self) -> None:
        root = Path(__file__).parent
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        spaces = (root / "web" / "spaces.js").read_text(encoding="utf-8")
        app = (root / "web" / "app.js").read_text(encoding="utf-8")
        model = (root / "web" / "drawer-model.js").read_text(encoding="utf-8")
        view = (root / "web" / "drawer-view.js").read_text(encoding="utf-8")
        self.assertIn('id="space-fields-pegboard"', html)
        self.assertIn('id="pegboard-cleat-x"', html)
        self.assertIn('id="pegboard-cleat-y"', html)
        self.assertIn("SP.resolvePegboard", spaces)
        self.assertIn("syncPegboardMountForm", app)
        self.assertIn("DL.refreshPegboardLayouts", model)
        self.assertIn("DV.paintPegboardScene", view)


if __name__ == "__main__":
    unittest.main()
