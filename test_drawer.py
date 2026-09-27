import re
import tempfile
import threading
import unittest
import json
from pathlib import Path
from unittest import mock

from shapely import affinity

import organizer_drawer
from organizer_drawer import (
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
    storage_box_defaults,
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
            self.assertEqual({b["qty"] for b in loaded["bins"]}, {0})
            self.assertEqual({b["status"] for b in loaded["bins"]}, {"saved"})

            layout = _layout(200, 120, placements=[{"bin": "B1", "copy": 0, "gx": 0, "gy": 0}])
            save_inventory(folder, layout=layout, bin_updates=[{"id": "B1", "qty": 2}])
            append_bin(folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20, name="Nuts")
            text = inventory_path(folder).read_text(encoding="utf-8")
            self.assertIn("| ID | Date | Kind | Name |", text)
            self.assertTrue(inventory_path(folder).with_name("Wavefinity bins.md.bak").is_file())
            again = load_inventory(folder)
            self.assertEqual([b["id"] for b in again["bins"]], ["B1", "B2", "B3"])
            self.assertEqual(again["bins"][0]["qty"], 1)
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
            self.assertEqual(made["folder"]["space"], {
                "name": "Screw box", "kind": "portable", "x": 96.0, "y": 48.0, "z": 40.0,
                "storage_box": storage_box_defaults(),
            })
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


class AutoLayoutRemovalTests(unittest.TestCase):

    def test_manual_placements_still_report_fit_overlap_and_height(self):
        bins = [_bin("B1", 16, 16, 50), _bin("B2", 32, 16, 20)]
        layout = _layout(8 * 8 + 1, 6 * 8 + 1, placements=[
            {"bin": "B1", "copy": 0, "gx": 0, "gy": 0}, {"bin": "B2", "copy": 0, "gx": 2, "gy": 0},
        ])
        report = drawer_report(layout["drawers"][0], bins)
        self.assertEqual([p for p in report["problems"] if p["type"] != "height"], [])
        overlap = _layout(8 * 8 + 1, 6 * 8 + 1, placements=[
            {"bin": "B1", "copy": 0, "gx": 0, "gy": 0}, {"bin": "B2", "copy": 0, "gx": 1, "gy": 0},
        ])
        report = drawer_report(overlap["drawers"][0], bins)
        self.assertTrue(any(p["type"] == "overlap" for p in report["problems"]))



class StackTests(unittest.TestCase):
    def test_a_manual_stack_of_same_size_stackable_bins_reports_one_stack(self):
        bins = [
            {**_bin("B1", 16, 16, 30), "stack": "direct"},
            {**_bin("B2", 16, 16, 30), "stack": "direct"},
        ]
        layout = _layout(4 * 8 + 1, 4 * 8 + 1, height=100, placements=[
            {"bin": "B1", "copy": 0, "gx": 0, "gy": 0}, {"bin": "B2", "copy": 0, "on": "B1:0"},
        ])
        report = drawer_report(layout["drawers"][0], bins)
        self.assertEqual(report["stacks"], 1)
        self.assertEqual([p for p in report["problems"] if p["type"] != "height"], [])



class SpacerTests(unittest.TestCase):



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


    def test_an_already_explicit_boundary_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case2"
            self._write_space(folder, "box", drawer_extra={"boundary": "wall"})
            loaded = load_inventory(folder)
            self.assertEqual(loaded["layout"]["drawers"][0]["boundary"], "wall")



class StorageBoxFilenameTests(unittest.TestCase):
    def test_new_and_legacy_file_names_both_infer_the_part_name(self):
        from organizer_inventory import infer_name
        self.assertEqual(infer_name("Storage Box 64x48x40 - Fasteners.3mf"), "Fasteners")
        self.assertEqual(infer_name("B4B 64x48x40 - Fasteners.3mf"), "Fasteners")


class DesignSourceTests(unittest.TestCase):
    """One canonical Inventory row and design source per editable bin."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "Space"
        self.folder.mkdir()

    def _design(self, name="Bin"):
        return {"version": 1, "box": {"x": 16.0, "y": 16.0, "z": 20.0}, "part_name": name}

    def _record(self, name="Bin", **extra):
        return {"kind": "bin", "name": name, "x": 16.0, "y": 16.0, "z": 20.0, "stack": "none", **extra}

    def test_old_inventory_without_specs_still_loads(self):
        append_bin(self.folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20, name="Nuts")
        loaded = load_inventory(self.folder)
        self.assertEqual(loaded["layout"], None)
        from organizer_inventory import design_specs
        self.assertEqual(design_specs(loaded["layout"]), {})

    def test_row_and_spec_survive_write_and_read(self):
        from organizer_inventory import save_design_source, design_specs
        design = self._design("Fasteners")
        result = save_design_source(self.folder, design=design, record=self._record("Fasteners"))
        row_id = result["row_id"]
        self.assertEqual(result["bins"][0]["id"], row_id)
        self.assertEqual(result["bins"][0]["file"], "")
        self.assertEqual(result["bins"][0]["qty"], 0)

        reloaded = load_inventory(self.folder)
        self.assertEqual(design_specs(reloaded["layout"]).get(row_id), design)

    def test_reference_only_source_edit_keeps_generated_file_local_and_browser_text(self):
        from organizer_inventory import (save_design_source, save_design_source_text,
                                         change_design_status, load_inventory, render_inventory)
        original = self._design("Tools")
        original["layout"] = {"features": [{"kind": "post", "zone": [-4, -4, 4, 4]}]}
        first = save_design_source(self.folder, design=original, record=self._record("Tools"))
        row_id = first["row_id"]
        (self.folder / "Tools.3mf").write_bytes(b"existing output")
        change_design_status(self.folder, row_id, "printed", "Tools.3mf")
        edited = json.loads(json.dumps(original))
        edited["layout"]["features"][0]["reference_object"] = {"width": 3, "depth": 4, "height": 5}
        local = save_design_source(self.folder, design=edited, record=self._record("Tools"), row_id=row_id)
        self.assertFalse(local["files_became_stale"])
        self.assertEqual((local["bins"][0]["file"], local["bins"][0]["status"], local["bins"][0]["qty"]),
                         ("Tools.3mf", "printed", 1))
        self.assertEqual(local["layout"]["design_specs"][row_id], edited)
        self.assertFalse(local["layout"].get("stale_files"))
        text = render_inventory("Wavefinity", load_inventory(self.folder)["bins"], local["layout"])
        removed = json.loads(json.dumps(original))
        browser = save_design_source_text(text, design=removed, record=self._record("Tools"),
                                          row_id=row_id, available_filenames=["Tools.3mf"])
        self.assertFalse(browser["files_became_stale"])
        self.assertEqual(browser["bins"][0]["file"], "Tools.3mf")
        self.assertEqual(browser["layout"]["design_specs"][row_id], removed)
        printable = json.loads(json.dumps(edited))
        printable["part_name"] = "Different"
        stale = save_design_source_text(browser["inventory_text"], design=printable,
                                        record=self._record("Different"), row_id=row_id,
                                        available_filenames=["Tools.3mf"])
        self.assertTrue(stale["files_became_stale"])
        self.assertEqual(stale["bins"][0]["file"], "")

    def test_deleting_a_row_prunes_its_spec(self):
        from organizer_inventory import save_design_source, design_specs
        result = save_design_source(self.folder, design=self._design(), record=self._record())
        row_id = result["row_id"]
        save_inventory(self.folder, delete_ids=[row_id])
        after = load_inventory(self.folder)
        self.assertEqual(design_specs(after["layout"]), {})

    def test_multi_delete_removes_rows_sources_placements_and_owned_files(self):
        from organizer_inventory import save_design_source, design_specs, change_design_status
        first = save_design_source(self.folder, design=self._design("One"), record=self._record("One"))
        second = save_design_source(self.folder, design=self._design("Two"), record=self._record("Two"))
        third = save_design_source(self.folder, design=self._design("Three"), record=self._record("Three"))
        ids = [first["row_id"], second["row_id"]]
        for name, row_id in zip(("One.3mf", "Two.3mf"), ids):
            (self.folder / name).write_bytes(b"existing print file")
            change_design_status(self.folder, row_id, "saved", name)
        current = load_inventory(self.folder)
        layout = {**current["layout"], **_layout(100, 100, placements=[
            {"bin": ids[0], "copy": 0, "gx": 0, "gy": 0},
            {"bin": third["row_id"], "copy": 0, "gx": 2, "gy": 0},
        ])}
        save_inventory(self.folder, layout=layout)
        after = save_inventory(self.folder, delete_ids=ids)
        self.assertEqual([one["id"] for one in after["bins"]], [third["row_id"]])
        self.assertEqual(set(design_specs(after["layout"])), {third["row_id"]})
        self.assertEqual([one["bin"] for one in after["layout"]["drawers"][0]["placements"]],
                         [third["row_id"]])
        self.assertFalse((self.folder / "One.3mf").exists())
        self.assertFalse((self.folder / "Two.3mf").exists())

    def test_stale_layout_save_cannot_replace_newer_design_source(self):
        from organizer_inventory import save_design_source, design_specs
        first = save_design_source(self.folder, design=self._design("A"), record=self._record("A"))
        old_layout = first["layout"]
        row_id = first["row_id"]
        save_design_source(self.folder, design=self._design("B"), record=self._record("B"), row_id=row_id)
        save_inventory(self.folder, layout=old_layout)
        self.assertEqual(design_specs(load_inventory(self.folder)["layout"])[row_id]["part_name"], "B")


    def test_save_to_space_identity_transaction_cases(self):
        """Identical saves preserve status; real edits reset the same row."""
        from organizer_inventory import save_design_source, design_specs

        # Unchanged design already bound to the same row: saving again is
        # idempotent - same row id, no duplicate created.
        first = save_design_source(self.folder, design=self._design("A"), record=self._record("A"))
        row_id = first["row_id"]
        again = save_design_source(
            self.folder, design=self._design("A"), record=self._record("A"), row_id=row_id,
        )
        self.assertEqual(again["row_id"], row_id)
        self.assertEqual(len(again["bins"]), 1)

        # Loaded same-Space Qty-0 row, edited: updates that source in place
        # and clears a stale generated File if the caller says the geometry
        # changed (record.clear_file).
        save_design_source(self.folder, design=self._design(), record={
            **{k: v for k, v in self._record("Renamed").items()}, "clear_file": True,
        }, row_id=row_id)
        edited = load_inventory(self.folder)
        edited_row = next(one for one in edited["bins"] if one["id"] == row_id)
        self.assertEqual(edited_row["name"], "Renamed")
        self.assertEqual(edited_row["file"], "")
        self.assertEqual(len(edited["bins"]), 1)
        self.assertEqual(design_specs(edited["layout"])[row_id]["part_name"], "Bin")

        # A printed bin remains this same physical/logical row when edited.
        from organizer_inventory import change_design_status
        change_design_status(self.folder, row_id, "printed", "A.3mf")
        unchanged = save_design_source(
            self.folder, design=self._design(), record=self._record("Renamed"), row_id=row_id,
        )
        self.assertEqual(unchanged["row_id"], row_id)
        self.assertEqual(unchanged["bins"][0]["status"], "printed")
        self.assertEqual(unchanged["bins"][0]["file"], "A.3mf")
        edited_again = save_design_source(
            self.folder, design=self._design("Forked"), record=self._record("Forked"), row_id=row_id,
        )
        self.assertEqual(edited_again["row_id"], row_id)
        self.assertEqual(len(edited_again["bins"]), 1)
        self.assertEqual(edited_again["bins"][0]["status"], "in_design")
        self.assertEqual(edited_again["bins"][0]["qty"], 0)
        self.assertEqual(edited_again["bins"][0]["file"], "")
        specs = design_specs(edited_again["layout"])
        self.assertIn(row_id, specs)




    def test_local_and_hosted_design_source_routes_match(self):
        from wavefinity_web import default_design
        design = default_design()
        design["part_name"] = "Popper"
        local = drawer_routes(threading.Lock(), self.folder)
        hosted = drawer_routes(threading.Lock(), self.folder, hosted=True)
        a = local["/api/drawer/design-source/save"]({"output": str(self.folder), "design": design})
        b = hosted["/api/drawer/design-source/save"]({"inventory_text": "", "design": design})
        self.assertEqual(a["bins"], b["bins"])
        self.assertEqual(a["design"], b["design"])
        for route, payload in ((local, {"output": str(self.folder)}),
                               (hosted, {"inventory_text": b["inventory_text"]})):
            source = a if route is local else b
            duplicate = route["/api/drawer/design-source/duplicate"]({
                **payload, "row_id": source["row_id"],
            })
            self.assertEqual(duplicate["design"]["part_name"], "Popper (2)")
            saved = route["/api/drawer/design-source/status"]({
                **payload,
                **({"inventory_text": duplicate["inventory_text"]} if route is hosted else {}),
                "row_id": duplicate["row_id"], "action": "saved", "file": "Popper (2).3mf",
            })
            row = next(one for one in saved["bins"] if one["id"] == duplicate["row_id"])
            self.assertEqual((row["status"], row["qty"]), ("saved", 0))

    def test_hosted_edit_tracks_proven_old_files_for_later_delete(self):
        hosted = drawer_routes(threading.Lock(), self.folder, hosted=True)
        create = hosted["/api/drawer/design-source/save"]({
            "inventory_text": "", "design": self._design("One")})
        row_id = create["row_id"]
        saved = hosted["/api/drawer/design-source/status"]({
            "inventory_text": create["inventory_text"], "row_id": row_id,
            "action": "saved", "file": "Old, name.3mf, Second.3mf"})
        survivor = hosted["/api/drawer/design-source/save"]({
            "inventory_text": saved["inventory_text"], "design": self._design("Survivor")})
        survivor_saved = hosted["/api/drawer/design-source/status"]({
            "inventory_text": survivor["inventory_text"], "row_id": survivor["row_id"],
            "action": "saved", "file": "Old, name.3mf"})
        names = ["Old, name.3mf", "Second.3mf", "Unrelated.3mf"]
        edited = hosted["/api/drawer/design-source/save"]({
            "inventory_text": survivor_saved["inventory_text"], "row_id": row_id,
            "design": self._design("One edited"), "available_filenames": names})
        self.assertEqual(edited["bins"][0]["file"], "")
        self.assertEqual(edited["layout"]["stale_files"][row_id], names[:2])
        self.assertEqual(load_inventory_text(edited["inventory_text"])["layout"]["stale_files"][row_id], names[:2])
        saved_again = hosted["/api/drawer/design-source/status"]({
            "inventory_text": edited["inventory_text"], "row_id": row_id,
            "action": "saved", "file": "Third.3mf"})
        names.append("Third.3mf")
        edited_again = hosted["/api/drawer/design-source/save"]({
            "inventory_text": saved_again["inventory_text"], "row_id": row_id,
            "design": self._design("One edited twice"), "available_filenames": names})
        self.assertEqual(edited_again["layout"]["stale_files"][row_id],
                         ["Old, name.3mf", "Second.3mf", "Third.3mf"])
        deleted = hosted["/api/drawer/save"]({
            "inventory_text": edited_again["inventory_text"], "delete_ids": [row_id],
            "available_filenames": names})
        self.assertEqual(deleted["cleanup_files"], ["Second.3mf", "Third.3mf"])
        self.assertEqual([row["id"] for row in deleted["bins"]], [survivor["row_id"]])
        self.assertNotIn("stale_files", deleted["layout"])

    def test_hosted_edit_never_guesses_ambiguous_missing_or_unsafe_old_files(self):
        hosted = drawer_routes(threading.Lock(), self.folder, hosted=True)
        cases = [
            ("A.3mf, B.3mf, C.3mf", ["A.3mf", "B.3mf", "C.3mf", "A.3mf, B.3mf", "B.3mf, C.3mf"]),
            ("Missing.3mf", []),
            ("../Unsafe.3mf", ["Unsafe.3mf"]),
        ]
        for index, (file_text, names) in enumerate(cases):
            with self.subTest(file=file_text):
                created = hosted["/api/drawer/design-source/save"]({
                    "inventory_text": "", "design": self._design(f"Case {index}")})
                row_id = created["row_id"]
                saved = hosted["/api/drawer/design-source/status"]({
                    "inventory_text": created["inventory_text"], "row_id": row_id,
                    "action": "saved", "file": file_text})
                edited = hosted["/api/drawer/design-source/save"]({
                    "inventory_text": saved["inventory_text"], "row_id": row_id,
                    "design": self._design(f"Edited {index}"), "available_filenames": names})
                self.assertEqual(edited["bins"][0]["file"], "")
                self.assertFalse(edited["layout"].get("stale_files", {}).get(row_id))


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
            self.assertEqual(made["folder"]["space"]["name"], "Kitchen Drawer")

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

    def test_selected_row_prints_once_without_changing_placements(self):
        self.add("A", "A.3mf", qty=1)
        self.place(*({"bin": "B1", "copy": c, "gx": c * 2, "gy": 0} for c in range(3)))
        result = self.run_print({"B1": 2})
        self.assertEqual(self.launched[0], [self.folder.resolve() / "A.3mf"])
        self.assertEqual(result["bins"][0]["qty"], 1)
        copies = sorted(p["copy"] for p in result["layout"]["drawers"][0]["placements"])
        self.assertEqual(copies, [0, 1, 2])
        self.assertEqual(result["bin_copies"], 1)








    def test_changed_source_during_slicer_handoff_is_not_marked_printed(self):
        from organizer_inventory import save_design_source, change_design_status
        design = {"version": 1, "box": {"x": 16, "y": 16, "z": 20}, "part_name": "A"}
        record = {"kind": "bin", "name": "A", "x": 16, "y": 16, "z": 20, "stack": "none"}
        created = save_design_source(self.folder, design=design, record=record)
        row_id = created["row_id"]
        (self.folder / "A.3mf").write_bytes(b"3mf")
        change_design_status(self.folder, row_id, "saved", "A.3mf")

        def changed_while_opening(_slicer, _files):
            save_design_source(self.folder, design={**design, "part_name": "B"},
                               record={**record, "name": "B"}, row_id=row_id)

        # Fix 061 F7.5: "opened but not recorded" is a structured partial that
        # carries the refreshed Inventory, never a success and never Printed.
        result = self.run_print({row_id: 1}, launch=changed_while_opening)
        self.assertTrue(result["partial"])
        self.assertEqual(result["partial_stage"], "status")
        self.assertIn("Bambu Studio opened", result["error"])
        row = load_inventory(self.folder)["bins"][0]
        self.assertEqual((row["id"], row["status"], row["file"]), (row_id, "in_design", ""))

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

        result = self.run_print({"B1": 1}, launch=boom)
        self.assertTrue(result["partial"])
        self.assertEqual(inventory_path(self.folder).read_text(encoding="utf-8"), before)











if __name__ == "__main__":
    unittest.main()

