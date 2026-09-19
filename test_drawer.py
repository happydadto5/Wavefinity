import re
import tempfile
import unittest
import json
from pathlib import Path

from shapely import affinity

from organizer_drawer import (
    auto_layout,
    drawer_grid,
    drawer_report,
    generate_spacers,
    normalise_drawer,
    plan_spacers,
    spacer_frame,
    wavy_rect_outer,
)
from organizer_engine import (
    BoxSpec,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    nested_clearance,
    placed_outline,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_inventory import (
    append_bin,
    create_space,
    create_space_text,
    inventory_path,
    load_inventory,
    load_inventory_text,
    render_inventory,
    save_inventory,
    save_inventory_text,
)
from organizer_spaces import FolderMetadataError, space_routes

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
            self.assertTrue(inventory_path(folder).with_name("Wavefinity bins.md.bak").is_file())
            again = load_inventory(folder)
            self.assertEqual([b["id"] for b in again["bins"]], ["B1", "B2", "B3"])
            self.assertEqual(again["bins"][0]["qty"], 2)
            self.assertEqual(again["layout"]["drawers"][0]["placements"][0]["bin"], "B1")

    def test_a_new_space_starts_its_inventory_and_is_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Garage"
            prefs = {}
            routes = space_routes(Path(tmp), lambda: dict(prefs), lambda update: prefs.update(update) or dict(prefs))
            made = routes["/api/space/create"]({"output": str(folder), "name": "Screw box", "kind": "box", "x": 96, "y": 48, "z": 40})
            self.assertEqual(made["folder"]["space"], {"name": "Screw box", "kind": "box", "x": 96.0, "y": 48.0, "z": 40.0})
            self.assertEqual(made["folder"]["folder_mode"], "space")
            self.assertTrue((folder / ".wavefinity.json").is_file())
            self.assertEqual(made["recent"][0]["name"], "Screw box")
            drawer = load_inventory(folder)["layout"]["drawers"][0]
            self.assertEqual((drawer["name"], drawer["width"], drawer["depth"], drawer["height"]), ("Screw box", 96.0, 48.0, 40.0))
            append_bin(folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20)
            self.assertTrue(inventory_path(folder).read_text(encoding="utf-8").startswith("# Screw box Bins"))
            with self.assertRaises(ValueError):
                create_space(folder, name="Again", kind="drawer", x=1, y=1, z=1)

            plain = Path(tmp) / "Loose"
            done = routes["/api/folder/use"]({"output": str(plain)})
            self.assertEqual(done["folder"]["folder_mode"], "design")
            self.assertEqual([one["folder_mode"] for one in done["recent"]], ["design", "space"])

    def test_browser_inventory_text_uses_the_same_parser_and_writer(self):
        made = create_space_text("", title="Top Drawer", name="Top Drawer", kind="drawer", x=420, y=350, z=65)
        saved = save_inventory_text(made["inventory_text"], title="Top Drawer", new_bins=[{
            "name": "Bits", "x": 32, "y": 48, "z": 30, "qty": 0,
        }])
        loaded = load_inventory_text(saved["inventory_text"], title="Top Drawer")
        self.assertEqual(loaded["layout"]["space"]["name"], "Top Drawer")
        self.assertEqual(loaded["bins"][0]["name"], "Bits")


class FolderMigrationTests(unittest.TestCase):
    @staticmethod
    def routes(tmp, prefs=None):
        prefs = {} if prefs is None else prefs
        routes = space_routes(Path(tmp), lambda: dict(prefs), lambda update: prefs.update(update) or dict(prefs))
        return routes, prefs

    def test_empty_folder_becomes_design_with_inventory_on_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Designs"
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})
            self.assertEqual(result["folder"]["folder_mode"], "design")
            self.assertTrue(result["folder"]["inventory"])
            written = json.loads((folder / ".wavefinity.json").read_text())
            self.assertEqual(written["folder_mode"], "design")
            self.assertTrue(written["inventory"])
            # Inventory is enabled, but the file itself is only created lazily,
            # the first time there is something to log.
            self.assertFalse(inventory_path(folder).exists())

    def test_old_design_metadata_migrates_to_inventory_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "OldDesign"
            folder.mkdir()
            (folder / ".wavefinity.json").write_text('{"version":2,"folder_mode":"design"}', encoding="utf-8")
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})
            self.assertEqual(result["folder"]["folder_mode"], "design")
            self.assertTrue(result["folder"]["inventory"])
            self.assertTrue(json.loads((folder / ".wavefinity.json").read_text())["inventory"])

    def test_inventory_can_be_turned_off_and_back_on_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Bench"
            routes, _prefs = self.routes(tmp)
            routes["/api/folder/use"]({"output": str(folder)})

            off = routes["/api/folder/inventory"]({"output": str(folder), "inventory": False})
            self.assertFalse(off["folder"]["inventory"])
            self.assertFalse(json.loads((folder / ".wavefinity.json").read_text())["inventory"])
            # Reopening the folder preserves the opt-out.
            self.assertFalse(routes["/api/folder/use"]({"output": str(folder)})["folder"]["inventory"])

            on = routes["/api/folder/inventory"]({"output": str(folder), "inventory": True})
            self.assertTrue(on["folder"]["inventory"])

    def test_space_requires_inventory_and_rejects_turning_it_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Drawer2"
            folder.mkdir()
            create_space(folder, name="X", kind="drawer", x=40, y=40, z=40)
            routes, _prefs = self.routes(tmp)
            routes["/api/folder/use"]({"output": str(folder)})
            with self.assertRaises(ValueError):
                routes["/api/folder/inventory"]({"output": str(folder), "inventory": False})

    def test_legacy_space_and_design_markers_migrate_additively(self):
        with tempfile.TemporaryDirectory() as tmp:
            routes, prefs = self.routes(tmp)
            drawer = Path(tmp) / "Drawer"
            drawer.mkdir()
            legacy_space = {"name": "Tools", "kind": "drawer", "x": 120, "y": 80, "z": 40}
            (drawer / ".wavefinity-space.json").write_text(json.dumps(legacy_space), encoding="utf-8")
            result = routes["/api/folder/use"]({"output": str(drawer)})
            self.assertEqual(result["folder"]["folder_mode"], "space")
            self.assertEqual(result["folder"]["space"]["x"], 120.0)
            self.assertEqual(json.loads((drawer / ".wavefinity.json").read_text())["space"]["name"], "Tools")

            plain = Path(tmp) / "Plain"
            plain.mkdir()
            (plain / ".wavefinity-space.json").write_text('{"kind":"none"}', encoding="utf-8")
            self.assertEqual(routes["/api/folder/use"]({"output": str(plain)})["folder"]["folder_mode"], "design")

            preferred = Path(tmp) / "Preferred"
            preferred.mkdir()
            prefs["no_inventory_folders"] = [str(preferred)]
            preferred_result = routes["/api/folder/use"]({"output": str(preferred)})["folder"]
            self.assertEqual(preferred_result["folder_mode"], "design")
            self.assertFalse(preferred_result["inventory"])

    def test_inventory_space_beats_safe_contrary_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Drawer"
            folder.mkdir()
            create_space(folder, name="Hardware", kind="drawer", x=100, y=80, z=40)
            inventory_before = inventory_path(folder).read_bytes()
            (folder / ".wavefinity.json").write_text('{"version":2,"folder_mode":"design"}', encoding="utf-8")
            (folder / ".wavefinity-space.json").write_text('{"kind":"none"}', encoding="utf-8")
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})
            self.assertEqual(result["folder"]["folder_mode"], "space")
            self.assertEqual(result["folder"]["space"]["name"], "Hardware")
            self.assertEqual(inventory_path(folder).read_bytes(), inventory_before)
            self.assertEqual(json.loads((folder / ".wavefinity.json").read_text())["folder_mode"], "space")

    def test_legacy_box_space_beats_a_stale_current_design_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Garage"
            folder.mkdir()
            # A current "design" marker is not a positive Space identity and
            # must not hide a genuine legacy Box recorded alongside it.
            (folder / ".wavefinity.json").write_text('{"version":2,"folder_mode":"design"}', encoding="utf-8")
            (folder / ".wavefinity-space.json").write_text(
                json.dumps({"name": "Screws", "kind": "box", "x": 96, "y": 48, "z": 40}), encoding="utf-8",
            )
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})["folder"]
            self.assertEqual(result["folder_mode"], "space")
            self.assertEqual(result["space"], {"name": "Screws", "kind": "box", "x": 96.0, "y": 48.0, "z": 40.0})
            self.assertTrue(result["inventory"])
            written = json.loads((folder / ".wavefinity.json").read_text())
            self.assertEqual(written["folder_mode"], "space")
            self.assertTrue(written["inventory"])
            self.assertEqual(written["space"]["kind"], "box")

    def test_legacy_space_beats_a_stale_design_marker_even_with_inventory_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Bench"
            folder.mkdir()
            (folder / ".wavefinity.json").write_text(
                '{"version":2,"folder_mode":"design","inventory":false}', encoding="utf-8",
            )
            (folder / ".wavefinity-space.json").write_text(
                json.dumps({"name": "Bits", "kind": "drawer", "x": 120, "y": 80, "z": 40}), encoding="utf-8",
            )
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})["folder"]
            self.assertEqual(result["folder_mode"], "space")
            self.assertEqual(result["space"]["kind"], "drawer")
            # Space always requires inventory, overriding the stale opt-out.
            self.assertTrue(result["inventory"])

    def test_current_design_wins_over_legacy_none_and_keeps_its_own_inventory_choice(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Plain2"
            folder.mkdir()
            (folder / ".wavefinity.json").write_text(
                '{"version":2,"folder_mode":"design","inventory":false}', encoding="utf-8",
            )
            (folder / ".wavefinity-space.json").write_text('{"kind":"none"}', encoding="utf-8")
            routes, _prefs = self.routes(tmp)
            result = routes["/api/folder/use"]({"output": str(folder)})["folder"]
            self.assertEqual(result["folder_mode"], "design")
            self.assertFalse(result["inventory"])

    def test_damaged_or_unsupported_metadata_is_never_rewritten(self):
        cases = {
            "bad-json": "{broken",
            "future": '{"version":99,"folder_mode":"space","space":{"kind":"drawer","x":1,"y":1,"z":1}}',
            "bad-mode": '{"version":2,"folder_mode":"something_future"}',
            "bad-space": '{"version":2,"folder_mode":"space","space":{"kind":"drawer","x":1,"y":1}}',
            "infinite-space": '{"version":2,"folder_mode":"space","space":{"kind":"drawer","x":1e999,"y":1,"z":1}}',
        }
        with tempfile.TemporaryDirectory() as tmp:
            routes, _prefs = self.routes(tmp)
            for name, content in cases.items():
                with self.subTest(name=name):
                    folder = Path(tmp) / name
                    folder.mkdir()
                    metadata = folder / ".wavefinity.json"
                    metadata.write_text(content, encoding="utf-8")
                    before = metadata.read_bytes()
                    with self.assertRaises(FolderMetadataError):
                        routes["/api/folder/use"]({"output": str(folder)})
                    self.assertEqual(metadata.read_bytes(), before)

    def test_bad_recent_folder_is_isolated_and_does_not_replace_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "Good"
            bad = Path(tmp) / "Bad"
            bad.mkdir()
            metadata = bad / ".wavefinity.json"
            metadata.write_text('{"version":99,"folder_mode":"design"}', encoding="utf-8")
            before = metadata.read_bytes()
            prefs = {
                "output": str(Path(tmp) / "Original"),
                "recent_folders": [{"folder": str(bad), "name": "Broken folder"}],
            }
            routes, prefs = self.routes(tmp, prefs)

            result = routes["/api/folder/use"]({"output": str(good)})
            broken = next(one for one in result["recent"] if one["folder"] == str(bad))
            self.assertTrue(broken["invalid"])
            self.assertEqual(result["folder"]["folder"], str(good.resolve()))
            self.assertEqual(metadata.read_bytes(), before)

            saved_output = prefs["output"]
            with self.assertRaises(FolderMetadataError):
                routes["/api/space/open"]({"output": str(bad)})
            self.assertEqual(prefs["output"], saved_output)
            self.assertEqual(metadata.read_bytes(), before)

            result = routes["/api/space/forget"]({"output": str(bad)})
            self.assertFalse(any(one["folder"] == str(bad) for one in result["recent"]))
            self.assertEqual(metadata.read_bytes(), before)


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
        layout = _layout(4 * 8 + 1, 4 * 8 + 1, height=63)
        best = auto_layout(layout, bins)["candidates"][0]
        stacked = [p for p in best["placements"] if "on" in p]
        self.assertEqual(len(stacked), 1)      # 33 mm envelope + one 30 mm module; a third would not fit
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
    def test_edges_get_wavy_flat_backed_spacers_and_empty_cells_get_x_spacers(self):
        bins = [_bin("B1", 16, 16, 40)]
        layout = _layout(4 * 8 + 1 + 5.0, 3 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
        plan = plan_spacers(layout["drawers"][0], bins, {"fill": "all"})
        self.assertEqual(plan["height"], 15)
        self.assertEqual([s["side"] for s in plan["edges"]], ["right"])
        edge = plan["edges"][0]
        # flat against the drawer wall; wave crests reach just past the grid edge (32.5)
        self.assertAlmostEqual(edge["x"] + edge["w"], 37.5, places=6)
        self.assertTrue(32.1 < edge["x"] < 32.5, edge["x"])
        covered = sum(c["w"] * c["d"] for c in plan["cells"])
        self.assertEqual(covered, 4 * 3 - 4)

    def test_a_non_8mm_interior_spacer_carries_the_global_wave_phase(self):
        # A normal bin's own centre always lands on the global wave lattice
        # (its size is always a whole 8 mm unit). A spacer whose size is
        # "4 mod 8" on a 4 mm-snap drawer does NOT get that for free: its
        # grid corner is lattice-aligned, but corner + size/2 is not, so its
        # wave is half a cycle out of phase unless corrected - crest against
        # trough instead of matched. This checks the corrected geometry
        # actually mates with a real neighbouring bin: same clearance a
        # same-wall-sharing pair of ordinary bins would show, not a collision.
        z = 20.0
        bin_spec = BoxSpec(16, 16, z)
        bin_centre = (8.0, 8.0)  # bin occupies grid x in [0, 16], y in [0, 16]
        bin_outline = placed_outline(bin_spec, bin_centre)

        # A spacer immediately to the left, sharing the vertical seam at
        # x = 0: grid x in [-16, 0], y in [0, 4]. Its Y size (4 mm) is what
        # governs its left/right-wall phase, since those walls run along Y.
        sx, sy = 16.0, 4.0
        spacer_centre = (-8.0, 2.0)
        half_x, half_y = sx / 2.0 - WAVE_MATING_GAP / 2.0, sy / 2.0 - WAVE_MATING_GAP / 2.0
        phase_x, phase_y = (sx / 2.0) % WAVE_LENGTH, (sy / 2.0) % WAVE_LENGTH
        self.assertAlmostEqual(phase_y, 2.0, places=6, msg="test setup should exercise a half-cycle correction")

        corrected = affinity.translate(wavy_rect_outer(half_x, half_y, phase_x=phase_x, phase_y=phase_y), *spacer_centre)
        self.assertTrue(corrected.intersection(bin_outline).is_empty)
        self.assertAlmostEqual(corrected.distance(bin_outline), nested_clearance(), places=3)

        # The uncorrected (phase 0) geometry is the bug this guards against:
        # it should actually collide with the neighbouring bin.
        uncorrected = affinity.translate(wavy_rect_outer(half_x, half_y), *spacer_centre)
        self.assertGreater(uncorrected.intersection(bin_outline).area, 0.01)

    def test_edge_spacer_covers_a_non_8mm_run_on_a_4mm_snap_drawer(self):
        # 23 rows of 4 mm = 92 mm - not a multiple of 8, so BoxSpec (8 mm
        # grid only) can't be built at exactly this length; the piece must
        # still cover the real run, not round down to 88 mm.
        raw_drawer = {
            "id": "d1", "name": "Drawer 1", "width": 100.0, "depth": 93.0, "height": 60,
            "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "snap": 4,
            "keepouts": [], "placements": [{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}],
        }
        bins = [_bin("B1", 16, 16, 40)]
        grid = drawer_grid(normalise_drawer(raw_drawer))
        run_mm = grid["rows"] * grid["step"]
        self.assertNotEqual(run_mm % 8, 0, "test setup should exercise a non-8mm run")
        plan = plan_spacers(raw_drawer, bins, {"fill": "edges"})
        right = sorted((e for e in plan["edges"] if e["side"] == "right"), key=lambda e: e["y"])
        self.assertTrue(right)
        self.assertAlmostEqual(right[0]["y"], grid["oy"], places=6)
        self.assertAlmostEqual(right[-1]["y"] + right[-1]["d"], grid["oy"] + run_mm, places=6)
        for a, b in zip(right, right[1:]):
            self.assertAlmostEqual(a["y"] + a["d"], b["y"], places=6)

    def test_an_x_spacer_is_an_open_braced_frame_with_a_bins_outline(self):
        spec = BoxSpec(48, 32, 15)
        mesh = spacer_frame(48, 32, 15)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[1][2] - mesh.bounds[0][2], 15, places=3)
        ring = wavy_outer_polygon(spec).area - wavy_cavity_polygon(spec).area
        self.assertGreater(mesh.volume, ring * 15)                          # wall plus braces
        self.assertLess(mesh.volume, wavy_outer_polygon(spec).area * 15 * 0.35)  # open, no floor

    def test_generated_edge_spacers_join_the_inventory_and_the_drawer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Shop"
            append_bin(folder, file="Box 16 x 16 x 40.3mf", x=16, y=16, z=40)
            layout = _layout(2 * 8 + 1 + 4.0, 2 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
            made = generate_spacers(folder, layout, "d1", {"fill": "edges", "height": 12})
            self.assertEqual(len(made["generated"]), 1)
            self.assertTrue((folder / made["generated"][0]).is_file())
            # One unified kind - an edge-facing spacer is told apart only by
            # its "edge" boundary tag, never a separate "shim" kind.
            edge = next(b for b in made["bins"] if b["kind"] == "spacer" and b.get("boundary") == "edge")
            placements = made["layout"]["drawers"][0]["placements"]
            self.assertTrue(any(p["bin"] == edge["id"] and p["side"] == "right" for p in placements))

    def test_legacy_shim_rows_load_as_spacers_and_never_resave_as_shim(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Old Shop"
            folder.mkdir(parents=True)
            path = inventory_path(folder)
            path.write_text(
                "# Old Shop Bins\n\n"
                "| ID | Date | Kind | Name | X (mm) | Y (mm) | Z (mm) | Stack | Wall (mm) | Qty | File | Label | Interior Part(s) |\n"
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
                "| B1 | 2024-01-01 00:00 | shim | Edge shim | 16 | 250 | 15 | | | 1 | Shim 16 x 250 x 15.3mf | | Edge shim, wavy on the bin side |\n",
                encoding="utf-8",
            )
            loaded = load_inventory(folder)
            legacy = loaded["bins"][0]
            self.assertEqual(legacy["kind"], "spacer")
            self.assertEqual(legacy["boundary"], "edge")
            self.assertEqual((legacy["x"], legacy["y"], legacy["z"]), (16, 250, 15))
            # Any save (even one touching an unrelated row) normalises it.
            # Its historical name/file text is free-form data describing a
            # real file already on disk and is left alone; only the Kind
            # column - the thing that made it a second data model - changes.
            saved = save_inventory(folder, bin_updates=[{"id": "B1", "qty": 1}])
            self.assertEqual(saved["bins"][0]["kind"], "spacer")
            self.assertEqual(saved["bins"][0]["boundary"], "edge")
            kind_column = re.search(r"\|\s*shim\s*\|", path.read_text(encoding="utf-8"), re.I)
            self.assertIsNone(kind_column, "a Kind cell still literally says shim")


class BoundaryTests(unittest.TestCase):
    def test_a_box_space_keeps_its_exact_grid_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case"
            made = create_space(folder, name="Screw box", kind="box", x=96, y=48, z=40)
            drawer = made["layout"]["drawers"][0]
            self.assertEqual(drawer["boundary"], "mating")
            grid = drawer_grid(normalise_drawer(drawer))
            # A hard-wall drawer of this exact size would lose a column to the
            # crest clearance; a B4B/Box mating boundary must not.
            self.assertEqual((grid["cols"], grid["rows"]), (12, 6))
            self.assertEqual(grid["gap_left"] + grid["gap_right"], 0)

    def test_a_plain_drawer_still_gets_hard_wall_clearance(self):
        drawer = normalise_drawer({"width": 96, "depth": 48, "height": 40, "clearance": 0})
        self.assertEqual(drawer["boundary"], "wall")
        grid = drawer_grid(drawer)
        self.assertLess(grid["cols"], 12)

    @staticmethod
    def _write_space(folder, kind, drawer_extra=None):
        folder.mkdir(parents=True, exist_ok=True)
        layout = {
            "version": 1, "active": "d1",
            "space": {"kind": kind, "name": folder.name, "x": 96, "y": 48, "z": 40},
            "drawers": [{
                "id": "d1", "name": folder.name, "width": 96, "depth": 48, "height": 40,
                "clearance": 0.0 if kind == "box" else 1.0, "keepouts": [], "placements": [],
                **(drawer_extra or {}),
            }],
        }
        inventory_path(folder).write_text(render_inventory(folder.name, [], layout), encoding="utf-8")

    def test_an_existing_box_space_missing_boundary_migrates_to_mating_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case"
            self._write_space(folder, "box")
            loaded = load_inventory(folder)
            drawer = loaded["layout"]["drawers"][0]
            self.assertEqual(drawer["boundary"], "mating")
            # And it keeps its exact interior capacity once migrated.
            grid = drawer_grid(normalise_drawer(drawer))
            self.assertEqual((grid["cols"], grid["rows"]), (12, 6))

    def test_an_existing_plain_drawer_space_missing_boundary_migrates_to_wall_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Drawer"
            self._write_space(folder, "drawer")
            loaded = load_inventory(folder)
            self.assertEqual(loaded["layout"]["drawers"][0]["boundary"], "wall")

    def test_an_already_explicit_boundary_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case2"
            self._write_space(folder, "box", drawer_extra={"boundary": "wall"})
            loaded = load_inventory(folder)
            self.assertEqual(loaded["layout"]["drawers"][0]["boundary"], "wall")

    def test_hosted_browser_text_migrates_an_existing_box_space_too(self):
        layout = {
            "version": 1, "active": "d1",
            "space": {"kind": "box", "name": "Case", "x": 96, "y": 48, "z": 40},
            "drawers": [{
                "id": "d1", "name": "Case", "width": 96, "depth": 48, "height": 40,
                "clearance": 0.0, "keepouts": [], "placements": [],
            }],
        }
        text = render_inventory("Case", [], layout)
        loaded = load_inventory_text(text, title="Case")
        self.assertEqual(loaded["layout"]["drawers"][0]["boundary"], "mating")


class OpenSpaceTests(unittest.TestCase):
    def test_two_distinct_openings_are_reported_largest_first(self):
        # A drawer with one bin in the middle leaves two separate gaps, one
        # each side - not a bounding box around both, and not the same gap
        # reported twice.
        bins = [_bin("B1", 16, 24, 20)]
        layout = _layout(6 * 8 + 1, 3 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 2, "gy": 0}])
        report = drawer_report(layout["drawers"][0], bins)
        opens = report["opens"]
        self.assertEqual(len(opens), 2)
        self.assertGreaterEqual(opens[0]["w"] * opens[0]["d"], opens[1]["w"] * opens[1]["d"])
        left, right = opens[0], opens[1]
        if left["gx"] > right["gx"]:
            left, right = right, left
        self.assertLessEqual(left["gx"] + left["w"], right["gx"])
        self.assertEqual(left["w_mm"], left["w"] * 8)

    def test_a_full_drawer_reports_no_open_space(self):
        bins = [_bin("B1", 16, 16, 20)]
        layout = _layout(2 * 8 + 1, 2 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
        report = drawer_report(layout["drawers"][0], bins)
        self.assertEqual(report["opens"], [])

    def test_a_sub_bin_width_sliver_is_not_offered_as_an_open_space(self):
        # A 3x4-cell (4 mm snap) grid with a 2x4-cell bin in it leaves a
        # genuine 1x4-cell (4 x 16 mm) strip - real free area, but narrower
        # than the smallest normal bin (one 8 mm unit) in every direction.
        bins = [_bin("B1", 8, 16, 20)]
        drawer = {
            "id": "d1", "name": "Drawer 1", "width": 14.0, "depth": 18.0, "height": 40,
            "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "snap": 4,
            "keepouts": [], "placements": [{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}],
        }
        report = drawer_report(drawer, bins)
        self.assertGreater(report["cells"]["free"], 0)
        self.assertEqual(report["opens"], [])


if __name__ == "__main__":
    unittest.main()
