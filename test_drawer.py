import re
import tempfile
import threading
import unittest
import json
from pathlib import Path
from unittest import mock

from shapely import affinity

from organizer_drawer import (
    auto_layout,
    drawer_grid,
    drawer_report,
    drawer_routes,
    generate_spacers,
    inventory_row_files,
    normalise_drawer,
    plan_spacers,
    print_inventory_bins,
    print_spacers_and_connectors,
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
    configure_space,
    configure_space_text,
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
        "placements": list(placements),
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
            # A brand-new typed Space never accepts the legacy "box" kind
            # directly - that only ever arrives via migration - so a new
            # mating-boundary case is created as "portable".
            made = routes["/api/space/create"]({"output": str(folder), "name": "Screw box", "kind": "portable", "x": 96, "y": 48, "z": 40})
            self.assertEqual(made["folder"]["space"], {"name": "Screw box", "kind": "portable", "x": 96.0, "y": 48.0, "z": 40.0})
            self.assertEqual(made["folder"]["folder_mode"], "space")
            self.assertTrue((folder / ".wavefinity.json").is_file())
            self.assertEqual(made["recent"][0]["name"], "Screw box")
            drawer = load_inventory(folder)["layout"]["drawers"][0]
            self.assertEqual((drawer["name"], drawer["width"], drawer["depth"], drawer["height"]), ("Screw box", 96.0, 48.0, 40.0))
            append_bin(folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20)
            self.assertTrue(inventory_path(folder).read_text(encoding="utf-8").startswith("# Screw box Bins"))
            with self.assertRaises(ValueError):
                configure_space(folder, raw_def={"name": "Again", "kind": "drawer", "x": 1, "y": 1, "z": 1})

            plain = Path(tmp) / "Loose"
            # A never-created folder needs the explicit "no Space type"
            # choice, which also creates it - /api/folder/use only opens a
            # folder that already exists and has completed setup.
            done = routes["/api/space/use-untyped"]({"output": str(plain)})
            self.assertEqual(done["folder"]["folder_mode"], "design")
            self.assertEqual([one["folder_mode"] for one in done["recent"]], ["space", "design"])

    def test_browser_inventory_text_uses_the_same_parser_and_writer(self):
        made = configure_space_text(
            "", title="Top Drawer",
            raw_def={"name": "Top Drawer", "kind": "drawer", "x": 420, "y": 350, "z": 65},
        )
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
            # A never-before-seen folder always needs_setup=True; the "no
            # Space type" choice is the explicit /api/space/use-untyped
            # route - /api/folder/use only opens an already-settled folder.
            result = routes["/api/space/use-untyped"]({"output": str(folder)})
            self.assertEqual(result["folder"]["folder_mode"], "design")
            self.assertTrue(result["folder"]["inventory"])
            written = json.loads((folder / ".wavefinity.json").read_text())
            self.assertEqual(written["folder_mode"], "design")
            self.assertTrue(written["inventory"])
            # Inventory is enabled, but the file itself is only created lazily,
            # the first time there is something to log.
            self.assertFalse(inventory_path(folder).exists())
            # Now that setup is complete, reopening it is the plain open route.
            self.assertEqual(
                routes["/api/folder/use"]({"output": str(folder)})["folder"]["folder_mode"], "design",
            )

    def test_old_design_metadata_migrates_to_inventory_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "OldDesign"
            folder.mkdir()
            (folder / ".wavefinity.json").write_text('{"version":2,"folder_mode":"design"}', encoding="utf-8")
            routes, _prefs = self.routes(tmp)
            # A v2 design marker still needs its one-time setup pass.
            result = routes["/api/space/use-untyped"]({"output": str(folder)})
            self.assertEqual(result["folder"]["folder_mode"], "design")
            self.assertTrue(result["folder"]["inventory"])
            self.assertTrue(json.loads((folder / ".wavefinity.json").read_text())["inventory"])

    def test_inventory_can_be_turned_off_and_back_on_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Bench"
            routes, _prefs = self.routes(tmp)
            routes["/api/space/use-untyped"]({"output": str(folder)})

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
            routes, _prefs = self.routes(tmp)
            # The real production path for a genuinely new typed Space:
            # /api/space/create writes current metadata and remembers it.
            routes["/api/space/create"]({"output": str(folder), "name": "X", "kind": "drawer", "x": 40, "y": 40, "z": 40})
            with self.assertRaises(ValueError):
                routes["/api/folder/inventory"]({"output": str(folder), "inventory": False})

    def test_legacy_space_and_design_markers_migrate_additively(self):
        with tempfile.TemporaryDirectory() as tmp:
            routes, prefs = self.routes(tmp)
            drawer = Path(tmp) / "Drawer"
            drawer.mkdir()
            legacy_space = {"name": "Tools", "kind": "drawer", "x": 120, "y": 80, "z": 40}
            (drawer / ".wavefinity-space.json").write_text(json.dumps(legacy_space), encoding="utf-8")

            # A legacy typed Space is only ever a candidate: it needs the
            # explicit migration pass (/api/space/configure), never an
            # automatic promotion from merely opening the folder.
            inspected = routes["/api/space/inspect"]({"output": str(drawer)})["folder"]
            self.assertEqual(inspected["folder_mode"], "space")
            self.assertEqual(inspected["space_source"], "legacy_metadata")
            self.assertTrue(inspected["needs_setup"])
            result = routes["/api/space/configure"]({
                "output": str(drawer), "name": "Tools", "kind": "drawer", "x": 120, "y": 80, "z": 40,
            })
            self.assertEqual(result["folder"]["folder_mode"], "space")
            self.assertEqual(result["folder"]["space"]["x"], 120.0)
            self.assertEqual(json.loads((drawer / ".wavefinity.json").read_text())["space"]["name"], "Tools")

            plain = Path(tmp) / "Plain"
            plain.mkdir()
            (plain / ".wavefinity-space.json").write_text('{"kind":"none"}', encoding="utf-8")
            self.assertEqual(
                routes["/api/space/use-untyped"]({"output": str(plain)})["folder"]["folder_mode"], "design",
            )

            preferred = Path(tmp) / "Preferred"
            preferred.mkdir()
            prefs["no_inventory_folders"] = [str(preferred)]
            preferred_result = routes["/api/space/use-untyped"]({"output": str(preferred)})["folder"]
            self.assertEqual(preferred_result["folder_mode"], "design")
            self.assertFalse(preferred_result["inventory"])

    def test_inventory_layout_space_needs_explicit_migration_over_contrary_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Drawer"
            folder.mkdir()
            configure_space(folder, raw_def={"name": "Hardware", "kind": "drawer", "x": 100, "y": 80, "z": 40})
            inventory_before = inventory_path(folder).read_bytes()
            (folder / ".wavefinity.json").write_text('{"version":2,"folder_mode":"design"}', encoding="utf-8")
            (folder / ".wavefinity-space.json").write_text('{"kind":"none"}', encoding="utf-8")
            routes, _prefs = self.routes(tmp)

            # Merely inspecting the folder never rewrites the inventory, and
            # an inventory-only candidate is never silently authoritative -
            # it still needs the explicit migration pass, even though it is
            # the only real Space information the folder has.
            inspected = routes["/api/space/inspect"]({"output": str(folder)})["folder"]
            self.assertEqual(inspected["folder_mode"], "space")
            self.assertEqual(inspected["space"]["name"], "Hardware")
            self.assertEqual(inspected["space_source"], "inventory_layout")
            self.assertTrue(inspected["needs_setup"])
            self.assertEqual(inventory_path(folder).read_bytes(), inventory_before)

            result = routes["/api/space/configure"]({
                "output": str(folder), "name": "Hardware", "kind": "drawer", "x": 100, "y": 80, "z": 40,
            })["folder"]
            self.assertEqual(result["folder_mode"], "space")
            self.assertEqual(result["space"]["name"], "Hardware")
            self.assertEqual(json.loads((folder / ".wavefinity.json").read_text())["folder_mode"], "space")

    def test_legacy_box_space_migrates_to_portable_over_a_stale_current_design_marker(self):
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
            inspected = routes["/api/space/inspect"]({"output": str(folder)})["folder"]
            self.assertEqual(inspected["folder_mode"], "space")
            self.assertEqual(inspected["space"], {"name": "Screws", "kind": "box", "x": 96.0, "y": 48.0, "z": 40.0})
            self.assertEqual(inspected["space_source"], "legacy_metadata")
            self.assertTrue(inspected["needs_setup"])

            # The explicit migration pass always persists legacy "box" as
            # "portable" - that mapping is enforced by configure_space()
            # itself, never left to the caller.
            result = routes["/api/space/configure"]({
                "output": str(folder), "name": "Screws", "kind": "box", "x": 96, "y": 48, "z": 40,
            })["folder"]
            self.assertEqual(result["folder_mode"], "space")
            self.assertEqual(result["space"], {"name": "Screws", "kind": "portable", "x": 96.0, "y": 48.0, "z": 40.0})
            self.assertTrue(result["inventory"])
            written = json.loads((folder / ".wavefinity.json").read_text())
            self.assertEqual(written["folder_mode"], "space")
            self.assertTrue(written["inventory"])
            self.assertEqual(written["space"]["kind"], "portable")

    def test_legacy_space_migration_requires_inventory_even_with_a_stale_opt_out(self):
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
            inspected = routes["/api/space/inspect"]({"output": str(folder)})["folder"]
            self.assertEqual(inspected["folder_mode"], "space")
            self.assertEqual(inspected["space"]["kind"], "drawer")
            self.assertEqual(inspected["space_source"], "legacy_metadata")

            result = routes["/api/space/configure"]({
                "output": str(folder), "name": "Bits", "kind": "drawer", "x": 120, "y": 80, "z": 40,
            })["folder"]
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
            result = routes["/api/space/use-untyped"]({"output": str(folder)})["folder"]
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

            # "good" is brand new, so its first open is the explicit
            # "no Space type" choice - /api/folder/use only opens a folder
            # whose setup is already complete.
            result = routes["/api/space/use-untyped"]({"output": str(good)})
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
    def test_edges_get_spacer_candidates_for_every_exposed_side(self):
        # The unified edge-spacer design plans one short, deterministic
        # contact-width candidate per exposed wall segment - never a full
        # tiled "cover the whole run" set, and never an interior grid-cell
        # filler (that older "X spacer" concept no longer exists).
        bins = [_bin("B1", 16, 16, 40)]
        layout = _layout(4 * 8 + 1 + 5.0, 3 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
        plan = plan_spacers(layout["drawers"][0], bins, {"fill": "all"})
        self.assertEqual(plan["height"], 15)
        sides = sorted(c["placements"][0]["side"] for c in plan["candidates"])
        self.assertEqual(sides, ["back", "right"])
        # A single simple component gets both its exposed sides auto-selected.
        self.assertEqual({c["id"] for c in plan["selected"]}, {c["id"] for c in plan["candidates"]})
        right = next(c["placements"][0] for c in plan["candidates"] if c["placements"][0]["side"] == "right")
        # flat against the drawer wall; wave crests reach just past the grid edge.
        self.assertAlmostEqual(right["x"] + right["w"], 37.5, places=6)
        self.assertTrue(16.1 < right["x"] < 16.6, right["x"])

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

    def test_edge_spacer_plans_correctly_on_a_non_8mm_run_with_a_4mm_snap_drawer(self):
        # 23 rows of 4 mm = 92 mm - not a multiple of 8, so BoxSpec (8 mm
        # grid only) can't be built at exactly this length; spacer planning
        # must still produce sane, in-bounds geometry for the odd run
        # instead of failing or silently rounding to the nearest 8 mm.
        # (The candidate itself is now a short, fixed contact-width piece,
        # never a set of pieces tiled across the whole run - see
        # SPACER_CONTACT_TARGET / _make_candidate.)
        raw_drawer = {
            "id": "d1", "name": "Drawer 1", "width": 100.0, "depth": 93.0, "height": 60,
            "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "snap": 4,
            "placements": [{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}],
        }
        bins = [_bin("B1", 16, 16, 40)]
        grid = drawer_grid(normalise_drawer(raw_drawer))
        run_mm = grid["rows"] * grid["step"]
        self.assertNotEqual(run_mm % 8, 0, "test setup should exercise a non-8mm run")
        plan = plan_spacers(raw_drawer, bins, {"fill": "edges"})
        right = next(
            c["placements"][0] for c in plan["candidates"] if c["placements"][0]["side"] == "right"
        )
        self.assertGreater(right["w"], 0)
        self.assertGreater(right["d"], 0)
        # The candidate sits inside the drawer, clear of the bin and the wall.
        self.assertGreaterEqual(right["y"], grid["oy"])
        self.assertLessEqual(right["y"] + right["d"], grid["oy"] + run_mm)

    def test_edge_spacer_mesh_is_a_watertight_flexure(self):
        # spacer_frame() (an "open braced frame" mesh) no longer exists -
        # generate_spacers() now always extrudes a serpentine-flexure
        # polygon. This checks that primitive still produces valid,
        # printable solid geometry at the requested height.
        from organizer_drawer import _serpentine_flexure
        from organizer_geometry import _extrude_polygon

        poly = _serpentine_flexure(48, 32, "right", flexible=True)
        mesh = _extrude_polygon(poly, 15)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[1][2] - mesh.bounds[0][2], 15, places=3)

    def test_generated_edge_spacers_join_the_inventory_and_the_drawer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Shop"
            append_bin(folder, file="Box 16 x 16 x 40.3mf", x=16, y=16, z=40)
            layout = _layout(2 * 8 + 1 + 4.0, 2 * 8 + 1, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
            routes = drawer_routes(threading.RLock(), folder)
            planned = routes["/api/drawer/spacers"]({
                "output": str(folder), "layout": layout, "drawer_id": "d1",
                "options": {"fill": "edges", "height": 12},
            })
            selected_ids = [c["id"] for c in planned["candidates"]]
            self.assertTrue(selected_ids)
            made = routes["/api/drawer/spacers/generate"]({
                "output": str(folder), "layout": layout, "drawer_id": "d1",
                "options": {"fill": "edges", "height": 12}, "selected": selected_ids,
            })
            self.assertEqual(len(made["generated"]), len(selected_ids))
            for gen in made["generated"]:
                self.assertTrue((folder / gen["file"]).is_file())
            # One unified kind - an edge-facing spacer is told apart only by
            # its "edge" boundary tag, never a separate "shim" kind.
            edges = [b for b in made["bins"] if b["kind"] == "spacer" and b.get("boundary") == "edge"]
            self.assertTrue(edges)
            placements = made["layout"]["drawers"][0]["placements"]
            self.assertTrue(any(p["bin"] == edges[0]["id"] for p in placements))

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
    def test_a_portable_space_keeps_its_exact_grid_capacity(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case"
            # "portable" is the current mating-boundary kind; legacy "box"
            # only ever arrives through migration, never a new Space - see
            # normalise_space_definition()'s box -> portable mapping.
            made = configure_space(folder, raw_def={"name": "Screw box", "kind": "portable", "x": 96, "y": 48, "z": 40})
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
                "clearance": 0.0 if kind == "box" else 1.0, "placements": [],
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
                "clearance": 0.0, "placements": [],
            }],
        }
        text = render_inventory("Case", [], layout)
        loaded = load_inventory_text(text, title="Case")
        self.assertEqual(loaded["layout"]["drawers"][0]["boundary"], "mating")


class StorageBoxFilenameTests(unittest.TestCase):
    def test_new_and_legacy_file_names_both_infer_the_part_name(self):
        from organizer_inventory import infer_name
        self.assertEqual(infer_name("Storage Box 64x48x40 - Fasteners.3mf"), "Fasteners")
        self.assertEqual(infer_name("B4B 64x48x40 - Fasteners.3mf"), "Fasteners")


class KeepOutRemovalTests(unittest.TestCase):
    def test_a_stray_old_keepouts_key_is_dropped(self):
        drawer = normalise_drawer({
            "id": "d1", "width": 100.0, "depth": 93.0, "height": 60,
            "keepouts": [{"x": 0, "y": 0, "w": 16, "d": 16}], "placements": [],
        })
        self.assertNotIn("keepouts", drawer)


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
            "placements": [{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}],
        }
        report = drawer_report(drawer, bins)
        self.assertGreater(report["cells"]["free"], 0)
        self.assertEqual(report["opens"], [])


class AutoSpaceFolderTests(unittest.TestCase):
    def test_auto_space_creation_and_duplicate_name_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            space_root = Path(tmp) / "Documents" / "Wavefinity"
            prefs = {}
            routes = space_routes(
                Path(tmp),
                lambda: dict(prefs),
                lambda update: prefs.update(update) or dict(prefs),
                space_root=space_root,
            )
            made = routes["/api/space/create"]({
                "name": "Kitchen Drawer",
                "kind": "drawer",
                "x": 400,
                "y": 300,
                "z": 60,
            })
            target = space_root / "Kitchen Drawer"
            self.assertTrue(target.is_dir())
            self.assertTrue((target / "Wavefinity bins.md").is_file())
            self.assertTrue((target / ".wavefinity.json").is_file())
            self.assertEqual(made["folder"]["name"], "Kitchen Drawer")

            # Duplicate name check (case-insensitive)
            with self.assertRaises(ValueError) as ctx:
                routes["/api/space/create"]({
                    "name": "kitchen drawer",
                    "kind": "drawer",
                    "x": 400,
                    "y": 300,
                    "z": 60,
                })
            self.assertEqual(
                str(ctx.exception),
                "That Space name is already in use. "
                "Space names can't be reused. Choose a different name.",
            )

    def test_auto_space_cleanup_on_validation_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            space_root = Path(tmp) / "Documents" / "Wavefinity"
            prefs = {}
            routes = space_routes(
                Path(tmp),
                lambda: dict(prefs),
                lambda update: prefs.update(update) or dict(prefs),
                space_root=space_root,
            )
            with self.assertRaises(ValueError):
                routes["/api/space/create"]({
                    "name": "Invalid Drawer",
                    "kind": "drawer",
                    "x": 0,
                    "y": 0,
                    "z": 0,
                })
            self.assertFalse((space_root / "Invalid Drawer").exists())


class BulkPrintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.slicer = self.folder / "bambu-studio.exe"
        self.slicer.write_bytes(b"")
        self.launched = []

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, files, qty=None, **extra):
        for one in files.split(", "):
            (self.folder / one).write_bytes(b"3mf")
        append_bin(self.folder, file=files, x=16, y=16, z=20, name=name, qty=qty, **extra)

    def launch(self, slicer, files):
        self.launched.append(list(files))
        return None

    def run_print(self, selection, layout=None, include=False, launch=None):
        inv = load_inventory(self.folder)
        return print_inventory_bins(
            self.folder, layout or inv["layout"], inv["bins"], selection, include,
            lambda _path: self.slicer, launch or self.launch,
        )

    def place(self, *placements):
        save_inventory(self.folder, layout=_layout(200, 120, placements=list(placements)))

    def test_generation_defaults_to_qty_zero_even_with_legacy_setting(self):
        self.add("A", "A.3mf")
        save_inventory(self.folder, layout={
            **_layout(200, 120), "settings": {"new_bins_printed": True}})
        append_bin(self.folder, file="B.3mf", x=16, y=16, z=20, name="B")
        append_bin(self.folder, file="C.3mf", x=16, y=16, z=20, name="C", qty=1)
        qty = {b["name"]: b["qty"] for b in load_inventory(self.folder)["bins"]}
        self.assertEqual(qty, {"A": 0, "B": 0, "C": 1})

    def test_missing_planned_copies_are_sent_and_qty_advances(self):
        self.add("A", "A.3mf", qty=1)
        self.place(*({"bin": "B1", "copy": c, "gx": c * 2, "gy": 0} for c in range(3)))
        result = self.run_print({"B1": 2})
        self.assertEqual(self.launched[0], [self.folder.resolve() / "A.3mf"] * 2)
        self.assertEqual(result["bins"][0]["qty"], 3)
        copies = sorted(p["copy"] for p in result["layout"]["drawers"][0]["placements"])
        self.assertEqual(copies, [0, 1, 2])
        self.assertEqual(result["bin_copies"], 2)

    def test_partial_selection_keeps_rest_planned_and_stack_refs_follow(self):
        self.add("A", "A.3mf", qty=1)
        self.place(
            {"bin": "B1", "copy": 0, "gx": 0, "gy": 0},
            {"bin": "B1", "copy": 3, "gx": 2, "gy": 0},
            {"bin": "B1", "copy": 5, "gx": 4, "gy": 0, "on": "B1:3"},
            {"bin": "B1", "copy": 6, "gx": 6, "gy": 0},
        )
        result = self.run_print({"B1": 2})
        placements = {(p["copy"]): p for p in result["layout"]["drawers"][0]["placements"]}
        self.assertEqual(result["bins"][0]["qty"], 3)
        self.assertEqual(sorted(placements), [0, 1, 2, 6])
        self.assertEqual(placements[2].get("on"), "B1:1")

    def test_unplaced_qty_zero_sends_one(self):
        self.add("A", "A.3mf")
        result = self.run_print({"B1": 1})
        self.assertEqual(result["bins"][0]["qty"], 1)

    def test_multi_file_row_expands_every_file_per_copy(self):
        self.add("A", "A.3mf, A insert.3mf, A lid.3mf")
        self.run_print({"B1": 2})
        names = [p.name for p in self.launched[0]]
        self.assertEqual(names, ["A.3mf", "A insert.3mf", "A lid.3mf"] * 2)

    def test_connectors_aggregate_once_across_drawers(self):
        self.add("A", "A.3mf")
        inv = load_inventory(self.folder)
        layout = {**_layout(200, 120), "drawers": [
            {**_layout(200, 120)["drawers"][0], "id": "d1"},
            {**_layout(200, 120)["drawers"][0], "id": "d2"},
        ]}
        (self.folder / "Conn.3mf").write_bytes(b"3mf")
        calls = []

        def fake_connectors(out, lay, bins, drawer_id=None):
            calls.append(drawer_id)
            return {"connectors": [{"file": "Conn.3mf", "count": 2}], "notes": ["n"]}

        with mock.patch("organizer_drawer.generate_connectors", fake_connectors):
            result = print_inventory_bins(
                self.folder, layout, inv["bins"], {"B1": 1}, True,
                lambda _p: self.slicer, self.launch)
        self.assertEqual(calls, ["d1", "d2"])
        self.assertEqual(result["connector_counts"], {"Conn.3mf": 4})
        self.assertEqual(result["notes"], ["n"])
        self.assertEqual([p.name for p in self.launched[0]].count("Conn.3mf"), 4)

    def test_connectors_off_generates_nothing(self):
        self.add("A", "A.3mf")
        with mock.patch("organizer_drawer.generate_connectors") as gen:
            self.run_print({"B1": 1}, include=False)
        gen.assert_not_called()

    def test_rejects_non_bin_rows_and_no_file_rows(self):
        self.add("A", "A.3mf")
        save_inventory(self.folder, new_bins=[
            {"kind": "manual", "x": 16, "y": 16, "z": 20, "name": "Hand"},
            {"kind": "spacer", "x": 16, "y": 16, "z": 20, "name": "Sp", "file": "S.3mf"},
        ])
        with self.assertRaises(ValueError):
            self.run_print({"B2": 1})
        with self.assertRaises(ValueError):
            self.run_print({"B3": 1})
        self.assertEqual(self.launched, [])

    def test_missing_and_traversal_files_rejected_before_launch(self):
        self.add("A", "A.3mf")
        (self.folder / "A.3mf").unlink()
        with self.assertRaises(ValueError):
            self.run_print({"B1": 1})
        inv = load_inventory(self.folder)
        bad = dict(inv["bins"][0], file="../evil.3mf")
        with self.assertRaises(ValueError):
            inventory_row_files(self.folder, bad)
        self.assertEqual(self.launched, [])

    def test_launch_failure_leaves_inventory_and_layout_unchanged(self):
        self.add("A", "A.3mf", qty=1)
        self.place({"bin": "B1", "copy": 0, "gx": 0, "gy": 0}, {"bin": "B1", "copy": 1, "gx": 2, "gy": 0})
        before = inventory_path(self.folder).read_text(encoding="utf-8")

        def boom(_slicer, _files):
            raise RuntimeError("no slicer")

        with self.assertRaises(RuntimeError):
            self.run_print({"B1": 1}, launch=boom)
        self.assertEqual(inventory_path(self.folder).read_text(encoding="utf-8"), before)

    def test_file_names_containing_commas(self):
        (self.folder / "Box Bolts, Nuts.3mf").write_bytes(b"3mf")
        append_bin(self.folder, file="Box Bolts, Nuts.3mf", x=16, y=16, z=20, name="Bolts")
        one = load_inventory(self.folder)["bins"][0]
        self.assertEqual([p.name for p in inventory_row_files(self.folder, one)], ["Box Bolts, Nuts.3mf"])
        (self.folder / "Insert, A.3mf").write_bytes(b"3mf")
        (self.folder / "Lid.3mf").write_bytes(b"3mf")
        row = dict(one, file="Box Bolts, Nuts.3mf, Insert, A.3mf, Lid.3mf")
        self.assertEqual(
            [p.name for p in inventory_row_files(self.folder, row)],
            ["Box Bolts, Nuts.3mf", "Insert, A.3mf", "Lid.3mf"])
        self.run_print({"B1": 1})
        self.assertEqual([p.name for p in self.launched[0]], ["Box Bolts, Nuts.3mf"])

    def test_ambiguous_file_list_rejected(self):
        for name in ("A.3mf", "C.3mf", "B.3mf, C.3mf", "A.3mf, B.3mf"):
            (self.folder / name).write_bytes(b"3mf")
        row = {"id": "B1", "name": "X", "file": "A.3mf, B.3mf, C.3mf"}
        with self.assertRaises(ValueError) as ctx:
            inventory_row_files(self.folder, row)
        self.assertIn("more than one way", str(ctx.exception))
        (self.folder / "A.3mf, B.3mf, C.3mf").write_bytes(b"3mf")
        self.assertEqual(len(inventory_row_files(self.folder, row)), 1)

    def test_traversal_and_missing_still_rejected_with_commas(self):
        self.add("A", "A.3mf")
        one = load_inventory(self.folder)["bins"][0]
        for bad in ("A.3mf, ../evil.3mf", "A.3mf, nope.3mf", "C:/evil.3mf"):
            with self.assertRaises(ValueError):
                inventory_row_files(self.folder, dict(one, file=bad))

    def test_invalid_copy_counts_rejected_without_side_effects(self):
        self.add("A", "A.3mf")
        before = inventory_path(self.folder).read_text(encoding="utf-8")
        for bad in (0, -1, 1.5, 1.0, True, "1.5", "-1", "abc", ""):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.run_print({"B1": bad})
        self.assertEqual(self.launched, [])
        self.assertEqual(inventory_path(self.folder).read_text(encoding="utf-8"), before)
        self.assertEqual(self.run_print({"B1": "2"})["bins"][0]["qty"], 2)
        self.assertEqual(self.run_print({"B1": 1})["bins"][0]["qty"], 3)

    def test_route_is_registered_and_hosted_rejects(self):
        routes = drawer_routes(threading.Lock(), self.folder, lambda _p: self.slicer, self.launch)
        self.assertIn("/api/drawer/print-bins", routes)
        hosted = drawer_routes(threading.Lock(), self.folder, None, None, hosted=True)
        with self.assertRaises(ValueError):
            hosted["/api/drawer/print-bins"]({"selection": {"B1": 1}})
        self.add("A", "A.3mf")
        result = routes["/api/drawer/print-bins"](
            {"output": str(self.folder), "selection": {"B1": 1}, "include_connectors": False})
        self.assertEqual(result["bins"][0]["qty"], 1)
        self.assertIn("stack_steps", result)

    def test_spacer_and_connector_print_repeats_files_by_count(self):
        self.add("A", "A.3mf")
        (self.folder / "Conn.3mf").write_bytes(b"3mf")
        inv = load_inventory(self.folder)
        with mock.patch("organizer_drawer.generate_connectors",
                        lambda *a, **k: {"connectors": [{"file": "Conn.3mf", "count": 3}], "notes": []}):
            print_spacers_and_connectors(
                self.folder, _layout(200, 120), inv["bins"], None,
                lambda _p: self.slicer, self.launch)
        self.assertEqual([p.name for p in self.launched[0]], ["Conn.3mf"] * 3)


if __name__ == "__main__":
    unittest.main()

