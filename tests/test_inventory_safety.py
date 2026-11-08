"""Fix 061: generated-file lifecycle (F6), coherent batch Save/Print (F7), and the
browser-state / catalog contracts for the settings-organization fixes (F1-F5)."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from unittest import mock

import organizer_drawer
from organizer_drawer import print_inventory_bins, save_inventory_bins
from organizer_inventory import (
    configure_space,
    change_design_status,
    storage_drawers_mutate,
    load_inventory,
    save_design_source,
    save_inventory,
)
from tests.test_space_preferences import APP_JS, function_source, node_run

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DRAWER_MODEL_JS = (WEB / "drawer-model.js").read_text(encoding="utf-8")
DRAWER_PANEL_JS = (WEB / "drawer-panel.js").read_text(encoding="utf-8")
INDEX_HTML = (WEB / "index.html").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def design(name: str, z: int = 20) -> dict:
    return {"version": 1, "box": {"x": 16, "y": 16, "z": z}, "part_name": name}


def record(name: str, z: int = 20) -> dict:
    return {"kind": "bin", "name": name, "x": 16, "y": 16, "z": z, "stack": "none"}


class BatchFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.slicer = self.folder / "bambu-studio.exe"
        self.slicer.write_bytes(b"")
        self.launched: list[list[str]] = []
        self.generated: list[str] = []
        self.fail_on: str | None = None
        self.extra_files: dict[str, list[str]] = {}
        # The printer-fit check reads real 3MF geometry; these fixtures are stub files.
        fit = patch("organizer_drawer.print_file_fit_issues", return_value=[])
        fit.start()
        self.addCleanup(fit.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def make_rows(self, count: int, prefix: str = "Bin") -> list[str]:
        ids = []
        for number in range(1, count + 1):
            saved = save_design_source(
                self.folder, design=design(f"{prefix} {number}"), record=record(f"{prefix} {number}"))
            ids.append(saved["row_id"])
        return ids

    def gen(self, output_dir, spec):
        name = spec["part_name"]
        if self.fail_on == name:
            raise RuntimeError("generator exploded")
        self.generated.append(name)
        names = self.extra_files.get(name) or [f"{name}.3mf"]
        paths = []
        for one in names:
            path = Path(output_dir) / one
            path.write_bytes(b"3mf")
            paths.append(path)
        return paths

    def launch(self, _slicer, files):
        self.launched.append([Path(one).name for one in files])

    def rows(self):
        return {one["id"]: one for one in load_inventory(self.folder)["bins"]}

    def save(self, ids, connectors=False):
        return save_inventory_bins(self.folder, ids, connectors, self.gen)

    def print(self, ids, connectors=False, launch=None):
        inv = load_inventory(self.folder)
        return print_inventory_bins(
            self.folder, inv["layout"], inv["bins"], {one: 1 for one in ids}, connectors,
            lambda _p: self.slicer, launch or self.launch, None, self.gen)


class DeleteSafetyTests(BatchFixture):
    def saved_for_delete(self, name: str, file_text: str | None = None) -> str:
        row_id = save_design_source(self.folder, design=design(name), record=record(name))["row_id"]
        if file_text:
            change_design_status(self.folder, row_id, "saved", file_text)
        return row_id

    def test_single_delete_cleans_current_and_stale_after_inventory_write(self):
        current = self.folder / "Current.3mf"
        stale = self.folder / "Old.3mf"
        current.write_bytes(b"x")
        stale.write_bytes(b"x")
        row_id = self.saved_for_delete("One", current.name)
        stale_id = self.saved_for_delete("Old", stale.name)
        save_design_source(self.folder, design=design("Old edited"), record=record("Old edited"), row_id=stale_id)
        layout = {**load_inventory(self.folder)["layout"], "drawers": [
            {"id": "d1", "placements": [{"bin": row_id, "copy": 0, "gx": 0, "gy": 0}]}]}
        save_inventory(self.folder, layout=layout)
        first = save_inventory(self.folder, delete_ids=[row_id])
        self.assertEqual(first["layout"]["drawers"][0]["placements"], [])
        self.assertFalse(current.exists())
        self.assertTrue(stale.exists())
        after = save_inventory(self.folder, delete_ids=[stale_id])
        self.assertEqual(after["bins"], [])
        self.assertEqual(after["layout"].get("design_specs"), {})
        self.assertNotIn("stale_files", after["layout"])
        self.assertFalse(stale.exists())

    def test_shared_ambiguous_and_unsafe_files_survive_delete(self):
        shared = self.folder / "Shared.3mf"
        shared.write_bytes(b"x")
        owner = self.saved_for_delete("Owner", shared.name)
        self.saved_for_delete("Survivor", shared.name)
        save_inventory(self.folder, delete_ids=[owner])
        self.assertTrue(shared.exists())

        for name in ("A.3mf", "B.3mf", "C.3mf", "A.3mf, B.3mf", "B.3mf, C.3mf"):
            (self.folder / name).write_bytes(b"x")
        ambiguous = self.saved_for_delete("Ambiguous", "A.3mf, B.3mf, C.3mf")
        save_inventory(self.folder, delete_ids=[ambiguous])
        self.assertTrue(all((self.folder / name).exists() for name in
                            ("A.3mf", "B.3mf", "C.3mf", "A.3mf, B.3mf", "B.3mf, C.3mf")))
        unsafe = self.saved_for_delete("Unsafe", "../Shared.3mf")
        save_inventory(self.folder, delete_ids=[unsafe])
        self.assertTrue(shared.exists())
        subdir = self.folder / "subdir"
        subdir.mkdir()
        (subdir / "Nested.3mf").write_bytes(b"x")
        (self.folder / "Shared.txt").write_bytes(b"x")
        for value in ("subdir/Nested.3mf", "Shared.txt"):
            save_inventory(self.folder, delete_ids=[self.saved_for_delete(value, value)])
        self.assertTrue((subdir / "Nested.3mf").exists())
        self.assertTrue((self.folder / "Shared.txt").exists())

    def test_missing_row_and_write_failure_leave_files_untouched(self):
        path = self.folder / "Own.3mf"
        path.write_bytes(b"x")
        row_id = self.saved_for_delete("Own", path.name)
        with self.assertRaises(ValueError):
            save_inventory(self.folder, delete_ids=[row_id, "B999"])
        self.assertTrue(path.exists())
        with mock.patch("organizer_inventory._write", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                save_inventory(self.folder, delete_ids=[row_id])
        self.assertTrue(path.exists())
        self.assertIn(row_id, self.rows())
        path.unlink()
        result = save_inventory(self.folder, delete_ids=[row_id])
        self.assertNotIn(row_id, {row["id"] for row in result["bins"]})

    def test_unlink_failure_commits_inventory_and_reports_partial_cleanup(self):
        path = self.folder / "Own.3mf"
        path.write_bytes(b"x")
        row_id = self.saved_for_delete("Own", path.name)
        original_unlink = Path.unlink
        def fail_owned(file, *args, **kwargs):
            if file == path:
                raise PermissionError("locked")
            return original_unlink(file, *args, **kwargs)
        with mock.patch.object(Path, "unlink", fail_owned):
            result = save_inventory(self.folder, delete_ids=[row_id])
        self.assertEqual(result["cleanup_failed"], [path.name])
        self.assertNotIn(row_id, self.rows())
        self.assertTrue(path.exists())

    def test_hosted_delete_authorizes_only_snapshot_owned_names(self):
        from organizer_inventory import save_inventory_text, render_inventory
        rows = [
            {"id": "B1", "file": "Owned.3mf", "kind": "bin", "name": "One", "x": 16, "y": 16, "z": 20, "qty": 0},
            {"id": "B2", "file": "Shared.3mf", "kind": "bin", "name": "Two", "x": 16, "y": 16, "z": 20, "qty": 0},
        ]
        text = render_inventory("Space", rows, {"design_specs": {"B1": {}, "B2": {}}})
        result = save_inventory_text(text, delete_ids=["B1"],
                                     available_filenames=["Owned.3mf", "Shared.3mf", "Other.3mf"])
        self.assertEqual(result["cleanup_files"], ["Owned.3mf"])
        self.assertEqual([row["id"] for row in result["bins"]], ["B2"])


class BatchSaveAndPrintTests(BatchFixture):



    def test_generation_failure_keeps_earlier_bins_saved_and_does_not_launch(self):
        ids = self.make_rows(10)
        self.fail_on = "Bin 6"
        result = self.print(ids)
        self.assertTrue(result["partial"])
        self.assertEqual(result["partial_stage"], "generate")
        self.assertEqual(result["failed_row"]["id"], ids[5])
        self.assertEqual(result["saved_rows"], ids[:5])
        self.assertEqual(result["unfinished"], ids[5:])
        self.assertEqual(self.launched, [])
        rows = {one["id"]: one for one in result["bins"]}          # refreshed payload
        self.assertEqual([rows[one]["status"] for one in ids], ["saved"] * 5 + ["in_design"] * 5)
        self.assertEqual({rows[one]["qty"] for one in ids}, {0})
        # Retry after the cause is fixed does not regenerate the five successes.
        self.fail_on = None
        self.generated.clear()
        retry = self.print(ids)
        self.assertNotIn("partial", retry)
        self.assertEqual(len(self.generated), 5)
        self.assertEqual(len(self.launched[0]), 10)










class StaleFileLifecycleTests(BatchFixture):
    def saved_row(self, name="Widget", printed=False):
        row_id = save_design_source(self.folder, design=design(name), record=record(name))["row_id"]
        (self.folder / f"{name}.3mf").write_bytes(b"old")
        change_design_status(self.folder, row_id, "saved", f"{name}.3mf")
        if printed:
            change_design_status(self.folder, row_id, "mark_printed")
        return row_id

    def edit(self, row_id, name="Widget", z=24):
        return save_design_source(
            self.folder, design=design(name, z), record=record(name, z), row_id=row_id)



    def test_refresh_replaces_the_files_and_removes_only_tracked_superseded_ones(self):
        row_id = self.saved_row(printed=True)
        (self.folder / "Unrelated.3mf").write_bytes(b"x")
        self.edit(row_id)
        (self.folder / "Widget v2.3mf").write_bytes(b"new")
        result = change_design_status(self.folder, row_id, "saved", "Widget v2.3mf")
        row = {one["id"]: one for one in result["bins"]}[row_id]
        self.assertEqual((row["status"], row["qty"], row["file"]), ("saved", 0, "Widget v2.3mf"))
        self.assertFalse((self.folder / "Widget.3mf").exists())
        self.assertTrue((self.folder / "Widget v2.3mf").is_file())
        self.assertTrue((self.folder / "Unrelated.3mf").is_file())
        self.assertNotIn("stale_files", result["layout"])


    def test_a_file_another_row_still_references_is_never_deleted(self):
        row_id = self.saved_row()
        other = save_design_source(self.folder, design=design("Twin"), record=record("Twin"))["row_id"]
        change_design_status(self.folder, other, "saved", "Widget.3mf")
        self.edit(row_id)
        (self.folder / "Widget v2.3mf").write_bytes(b"new")
        change_design_status(self.folder, row_id, "saved", "Widget v2.3mf")
        self.assertTrue((self.folder / "Widget.3mf").is_file())

    def refresh_to(self, row_id, new_name="Widget v2.3mf"):
        (self.folder / new_name).write_bytes(b"new")
        return change_design_status(self.folder, row_id, "saved", new_name)

    def other_row_owning(self, file_text, name="Other"):
        other = save_design_source(self.folder, design=design(name), record=record(name))["row_id"]
        change_design_status(self.folder, other, "saved", file_text)
        return other



    def test_an_ambiguous_or_unresolvable_other_row_cell_never_causes_deletion(self):
        row_id = self.saved_row("A")                      # owns A.3mf
        # Ambiguous: this cell reads two different ways against the real files.
        for name in ("C.3mf", "B.3mf, C.3mf", "A.3mf, B.3mf"):
            (self.folder / name).write_bytes(b"x")
        other = self.other_row_owning("A.3mf, B.3mf, C.3mf")
        from organizer_drawer import inventory_row_files
        with self.assertRaisesRegex(ValueError, "more than one way"):
            inventory_row_files(self.folder, self.rows()[other])
        self.edit(row_id, "A")
        self.refresh_to(row_id, "A v2.3mf")
        self.assertTrue((self.folder / "A.3mf").is_file())




    def test_stale_current_files_can_never_be_printed_as_the_new_design(self):
        row_id = self.saved_row()
        self.edit(row_id)
        result = self.print([row_id])
        self.assertNotIn("partial", result)
        self.assertEqual(self.generated, ["Widget"])          # regenerated, not the stale file
        self.assertEqual(self.rows()[row_id]["status"], "printed")



if __name__ == "__main__":
    unittest.main(verbosity=2)
