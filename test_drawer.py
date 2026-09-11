import tempfile
import unittest
from pathlib import Path

from organizer_drawer import (
    auto_layout,
    drawer_report,
    generate_spacers,
    plan_spacers,
    spacer_frame,
)
from organizer_engine import BoxSpec, wavy_cavity_polygon, wavy_outer_polygon
from organizer_inventory import append_bin, inventory_path, load_inventory, save_inventory

LEGACY = """# My Drawer Bins

| Date | File | X (mm) | Y (mm) | Z (mm) | Label | Interior Part(s) |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-07 07:30 | Box 56 x 32 x 50 Dental Floss.3mf | 56 | 32 | 50 | - | Pocket |
| 2026-09-08 06:47 | Box 80 x 72 x 30 090826064706.3mf | 80 | 72 | 30 | - | Bore |
"""


def _bin(ident, x, y, z, qty=1, kind="bin"):
    return {"id": ident, "x": x, "y": y, "z": z, "qty": qty, "kind": kind, "name": ""}


def _layout(width, depth, height=60, placements=()):
    return {"version": 1, "active": "d1", "drawers": [{
        "id": "d1", "name": "Drawer 1", "width": width, "depth": depth, "height": height,
        "clearance": 1.0, "anchor": "front-left", "bin_axis": "x",
        "keepouts": [], "placements": list(placements),
    }]}


class InventoryFileTests(unittest.TestCase):
    def test_a_legacy_log_upgrades_and_keeps_its_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "My Drawer"
            folder.mkdir()
            inventory_path(folder).write_text(LEGACY, encoding="utf-8")
            loaded = load_inventory(folder)
            self.assertEqual([b["id"] for b in loaded["bins"]], ["B1", "B2"])
            self.assertEqual([b["name"] for b in loaded["bins"]], ["Dental Floss", ""])
            self.assertEqual({b["qty"] for b in loaded["bins"]}, {1})

            layout = _layout(200, 120, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
            save_inventory(folder, layout=layout, bin_updates=[{"id": "B1", "qty": 2}])
            append_bin(folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20, name="Nuts")
            text = inventory_path(folder).read_text(encoding="utf-8")
            self.assertIn("| ID | Date | Kind | Name |", text)
            self.assertTrue(inventory_path(folder).with_name("My Drawer bins.md.bak").is_file())
            again = load_inventory(folder)
            self.assertEqual([b["id"] for b in again["bins"]], ["B1", "B2", "B3"])
            self.assertEqual(again["bins"][0]["qty"], 2)
            self.assertEqual(again["layout"]["drawers"][0]["placements"][0]["bin"], "B1")


class AutoLayoutTests(unittest.TestCase):
    def test_everything_fits_without_overlap_and_tall_bins_stand_behind(self):
        bins = [_bin("B1", 16, 16, 50, qty=3), _bin("B2", 32, 16, 20, qty=2), _bin("B3", 16, 32, 35)]
        layout = _layout(8 * 8 + 1, 6 * 8 + 1)
        result = auto_layout(layout, bins)
        best = result["candidates"][0]
        self.assertEqual(best["stats"]["placed"], 6)
        self.assertEqual(best["stats"]["height_issues"], 0)
        layout["drawers"][0]["placements"] = best["placements"]
        report = drawer_report(layout["drawers"][0], bins)
        self.assertEqual([p for p in report["problems"] if p["type"] != "height"], [])
        self.assertEqual(report["height_issues"], 0)


class StackTests(unittest.TestCase):
    def test_stackable_bins_snap_into_stacks_as_tall_as_the_drawer_takes(self):
        bins = [
            {**_bin("B1", 16, 16, 30, qty=3), "stack": "direct"},
            _bin("B2", 16, 16, 20),
        ]
        layout = _layout(4 * 8 + 1, 4 * 8 + 1, height=60)
        best = auto_layout(layout, bins)["candidates"][0]
        stacked = [p for p in best["placements"] if "on" in p]
        self.assertEqual(len(stacked), 1)      # 30 + (30 - 3) = 57 <= 60; a third would not fit
        self.assertEqual(best["stats"]["placed"], 4)
        layout["drawers"][0]["placements"] = best["placements"]
        report = drawer_report(layout["drawers"][0], bins)
        self.assertEqual(report["stacks"], 1)
        self.assertEqual([p for p in report["problems"] if p["type"] != "height"], [])

    def test_a_bin_not_printed_to_stack_is_flagged_on_a_stack(self):
        bins = [{**_bin("B1", 16, 16, 30), "stack": "lid"}, _bin("B2", 16, 16, 20)]
        layout = _layout(4 * 8 + 1, 4 * 8 + 1, placements=[
            {"bin": "B1", "copy": 0, "gx": 0, "gy": 0}, {"bin": "B2", "copy": 0, "on": "B1:0"},
        ])
        report = drawer_report(layout["drawers"][0], bins)
        self.assertTrue(any(p["type"] == "stack" for p in report["problems"]))


class SpacerTests(unittest.TestCase):
    def test_edges_get_wavy_shims_and_empty_cells_get_spacers(self):
        bins = [_bin("B1", 16, 16, 40)]
        layout = _layout(4 * 8 + 1 + 5.0, 3 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
        plan = plan_spacers(layout["drawers"][0], bins, {"fill": "all"})
        self.assertEqual(plan["height"], 15)
        self.assertEqual([s["side"] for s in plan["shims"]], ["right"])
        shim = plan["shims"][0]
        # flat against the drawer wall; wave crests reach just past the grid edge (32.5)
        self.assertAlmostEqual(shim["x"] + shim["w"], 37.5, places=6)
        self.assertTrue(32.1 < shim["x"] < 32.5, shim["x"])
        covered = sum(c["w"] * c["d"] for c in plan["cells"])
        self.assertEqual(covered, 4 * 3 - 4)

    def test_an_x_spacer_is_an_open_braced_frame_with_a_bins_outline(self):
        spec = BoxSpec(48, 32, 15)
        mesh = spacer_frame(48, 32, 15)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[1][2] - mesh.bounds[0][2], 15, places=3)
        ring = wavy_outer_polygon(spec).area - wavy_cavity_polygon(spec).area
        self.assertGreater(mesh.volume, ring * 15)                          # wall plus braces
        self.assertLess(mesh.volume, wavy_outer_polygon(spec).area * 15 * 0.35)  # open, no floor

    def test_generated_shims_join_the_inventory_and_the_drawer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Shop"
            append_bin(folder, file="Box 16 x 16 x 40.3mf", x=16, y=16, z=40)
            layout = _layout(2 * 8 + 1 + 4.0, 2 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
            made = generate_spacers(folder, layout, "d1", {"fill": "edges", "height": 12})
            self.assertEqual(len(made["generated"]), 1)
            self.assertTrue((folder / made["generated"][0]).is_file())
            shim = next(b for b in made["bins"] if b["kind"] == "shim")
            placements = made["layout"]["drawers"][0]["placements"]
            self.assertTrue(any(p["bin"] == shim["id"] and p["side"] == "right" for p in placements))


if __name__ == "__main__":
    unittest.main()
