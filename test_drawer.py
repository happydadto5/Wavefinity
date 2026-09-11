import tempfile
import unittest
from pathlib import Path

from organizer_drawer import (
    auto_layout,
    drawer_report,
    generate_spacers,
    plan_spacers,
)
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


class SpacerTests(unittest.TestCase):
    def test_edges_get_shims_and_empty_cells_get_spacer_bins(self):
        bins = [_bin("B1", 16, 16, 40)]
        layout = _layout(4 * 8 + 1 + 5.0, 3 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
        plan = plan_spacers(layout["drawers"][0], bins, {"fill": "all", "height": 20})
        self.assertEqual([s["side"] for s in plan["shims"]], ["right"])
        self.assertAlmostEqual(plan["shims"][0]["w"], 5.0 - 0.375, places=3)
        covered = sum(c["w"] * c["d"] for c in plan["cells"])
        self.assertEqual(covered, 4 * 3 - 4)

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
