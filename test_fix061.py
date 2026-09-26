"""Fix 061: generated-file lifecycle (F6), coherent batch Save/Print (F7), and the
browser-state / catalog contracts for the settings-organization fixes (F1-F5)."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import organizer_drawer
from organizer_drawer import print_inventory_bins, save_inventory_bins
from organizer_inventory import (
    change_design_status,
    load_inventory,
    save_design_source,
    save_inventory,
)
from test_space_preferences import APP_JS, function_source, node_run

ROOT = Path(__file__).resolve().parent
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


class BatchSaveAndPrintTests(BatchFixture):
    def test_ten_in_design_rows_save_once_and_never_touch_the_slicer(self):
        ids = self.make_rows(10)
        result = self.save(ids)
        self.assertNotIn("partial", result)
        self.assertEqual(len(self.generated), 10)
        rows = self.rows()
        for row_id in ids:
            self.assertEqual((rows[row_id]["status"], rows[row_id]["qty"]), ("saved", 0))
            self.assertTrue(rows[row_id]["file"].endswith(".3mf"))
        self.assertEqual(self.launched, [])
        # Saving again with no design change reuses every file.
        again = self.save(ids)
        self.assertEqual(len(self.generated), 10)
        self.assertEqual(again["reused_rows"], ids)
        self.assertEqual(again["generated_rows"], [])

    def test_print_ten_directly_from_in_design_generates_then_opens_once(self):
        ids = self.make_rows(10)
        result = self.print(ids)
        self.assertNotIn("partial", result)
        self.assertEqual(len(self.generated), 10)
        self.assertEqual(len(self.launched), 1)
        self.assertEqual(len(self.launched[0]), 10)
        self.assertEqual({one["status"] for one in self.rows().values()}, {"printed"})

    def test_a_mix_of_in_design_saved_and_printed_generates_only_what_is_missing(self):
        ids = self.make_rows(10)
        self.save(ids[4:7])                      # 3 Saved
        self.print(ids[7:])                      # 3 Printed
        self.generated.clear()
        self.launched.clear()
        self.save(ids)
        self.assertEqual(len(self.generated), 4)
        rows = self.rows()
        self.assertEqual([rows[one]["status"] for one in ids],
                         ["saved"] * 7 + ["printed"] * 3)
        self.print(ids)
        self.assertEqual(len(self.generated), 4)  # nothing regenerated for Print
        self.assertEqual(len(self.launched[0]), 10)
        self.assertEqual({one["status"] for one in self.rows().values()}, {"printed"})

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

    def test_batch_save_partial_failure_reports_unfinished_rows(self):
        ids = self.make_rows(4)
        self.fail_on = "Bin 3"
        result = self.save(ids)
        self.assertEqual((result["partial"], result["partial_stage"]), (True, "generate"))
        self.assertEqual(result["saved_rows"], ids[:2])
        self.assertEqual(result["unfinished"], ids[2:])
        self.assertIn("Bin 3", result["error"])

    def test_connector_failure_after_saving_bins_keeps_them_and_skips_bambu(self):
        ids = self.make_rows(3)
        save_inventory(self.folder, layout={"version": 1, "active": "d1", "drawers": [{
            "id": "d1", "name": "Drawer 1", "width": 200, "depth": 120, "height": 60,
            "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "placements": []}]})
        with mock.patch("organizer_drawer.generate_connectors", side_effect=RuntimeError("no connectors")):
            result = self.print(ids, connectors=True)
            saved = self.save(ids, connectors=True)
        self.assertEqual((result["partial"], result["partial_stage"]), (True, "connectors"))
        self.assertEqual(saved["partial_stage"], "connectors")
        self.assertEqual(self.launched, [])
        self.assertEqual({one["status"] for one in self.rows().values()}, {"saved"})

    def test_bambu_launch_failure_leaves_prepared_rows_saved_and_qty_zero(self):
        ids = self.make_rows(5)

        def boom(_slicer, _files):
            raise RuntimeError("no slicer")

        result = self.print(ids, launch=boom)
        self.assertEqual((result["partial"], result["partial_stage"]), (True, "slicer"))
        self.assertEqual(result["selection"], {one: 1 for one in ids})
        self.assertEqual({(one["status"], one["qty"]) for one in self.rows().values()}, {("saved", 0)})

    def test_status_write_failure_is_reported_as_opened_but_not_recorded(self):
        ids = self.make_rows(2)
        with mock.patch("organizer_drawer.mark_printed_rows", side_effect=ValueError("disk full")):
            result = self.print(ids)
        self.assertEqual(result["partial_stage"], "status")
        self.assertIn("opened, but the printed status could not be recorded", result["error"])
        self.assertEqual(len(self.launched), 1)
        self.assertEqual({one["status"] for one in self.rows().values()}, {"saved"})

    def test_multi_file_rows_are_tracked_and_handed_off_completely(self):
        (ids) = self.make_rows(1, prefix="Kit")
        self.extra_files["Kit 1"] = ["Kit 1.3mf", "Kit 1 insert.3mf", "Kit 1 lid.3mf"]
        self.print(ids)
        self.assertEqual(self.rows()[ids[0]]["file"], "Kit 1.3mf, Kit 1 insert.3mf, Kit 1 lid.3mf")
        self.assertEqual(self.launched[0], ["Kit 1.3mf", "Kit 1 insert.3mf", "Kit 1 lid.3mf"])

    def test_retries_never_create_duplicate_rows_or_design_sources(self):
        ids = self.make_rows(3)
        for _ in range(3):
            self.save(ids)
            self.print(ids)
        inv = load_inventory(self.folder)
        self.assertEqual(sorted(one["id"] for one in inv["bins"]), sorted(ids))
        self.assertEqual(sorted(inv["layout"]["design_specs"]), sorted(ids))

    def test_another_space_is_never_touched(self):
        ids = self.make_rows(2)
        other = self.folder / "Other Space"
        other.mkdir()
        other_ids = [save_design_source(other, design=design("Other"), record=record("Other"))["row_id"]]
        self.save(ids)
        self.assertEqual({one["status"] for one in load_inventory(other)["bins"]}, {"in_design"})
        self.assertFalse(list(other.glob("*.3mf")))
        self.assertEqual(other_ids, ["B1"])

    def test_save_rejects_rows_that_cannot_be_made_before_writing_anything(self):
        ids = self.make_rows(2)
        save_inventory(self.folder, new_bins=[{"kind": "manual", "x": 16, "y": 16, "z": 20, "name": "Hand"}])
        with self.assertRaises(ValueError):
            self.save([*ids, "B3"])
        with self.assertRaises(ValueError):
            self.save([])
        self.assertEqual(self.generated, [])


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

    def test_first_edit_of_a_generated_row_flags_it_once_and_keeps_the_old_file(self):
        row_id = self.saved_row()
        first = self.edit(row_id)
        self.assertTrue(first["files_became_stale"])
        row = self.rows()[row_id]
        self.assertEqual((row["status"], row["file"], row["qty"]), ("in_design", "", 0))
        self.assertTrue((self.folder / "Widget.3mf").is_file())
        self.assertEqual(first["layout"]["stale_files"], {row_id: ["Widget.3mf"]})
        second = self.edit(row_id, z=26)
        self.assertFalse(second["files_became_stale"])
        self.assertEqual(second["layout"]["stale_files"], {row_id: ["Widget.3mf"]})

    def test_a_row_that_never_had_files_is_never_flagged(self):
        row_id = save_design_source(self.folder, design=design("Fresh"), record=record("Fresh"))["row_id"]
        result = self.edit(row_id, "Fresh")
        self.assertFalse(result["files_became_stale"])
        self.assertNotIn("stale_files", result["layout"])

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

    def test_a_same_name_replacement_is_not_deleted_as_superseded(self):
        row_id = self.saved_row()
        self.edit(row_id)
        (self.folder / "Widget.3mf").write_bytes(b"regenerated")
        change_design_status(self.folder, row_id, "saved", "Widget.3mf")
        self.assertEqual((self.folder / "Widget.3mf").read_bytes(), b"regenerated")

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

    def test_a_comma_containing_file_owned_by_another_row_is_protected(self):
        row_id = self.saved_row("A, B")                  # owns "A, B.3mf"
        self.assertTrue((self.folder / "A, B.3mf").is_file())
        self.other_row_owning("A, B.3mf")
        self.edit(row_id, "A, B")
        self.refresh_to(row_id)
        self.assertTrue((self.folder / "A, B.3mf").is_file())

    def test_every_real_member_of_a_multi_file_set_with_a_comma_is_protected(self):
        row_id = self.saved_row("A, B")
        (self.folder / "C.3mf").write_bytes(b"c")
        self.other_row_owning("A, B.3mf, C.3mf")
        self.edit(row_id, "A, B")
        self.refresh_to(row_id)
        self.assertTrue((self.folder / "A, B.3mf").is_file())
        self.assertTrue((self.folder / "C.3mf").is_file())

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

    def test_a_row_with_a_broken_file_cell_still_protects_its_possible_files(self):
        row_id = self.saved_row("A, B")
        other = save_design_source(self.folder, design=design("Broken"), record=record("Broken"))["row_id"]
        change_design_status(self.folder, other, "printed", "A, B.3mf, Missing.3mf")
        self.edit(row_id, "A, B")
        self.refresh_to(row_id)
        self.assertTrue((self.folder / "A, B.3mf").is_file())

    def test_tracked_only_cleanup_still_removes_a_genuinely_unshared_old_file(self):
        row_id = self.saved_row("A, B")
        self.other_row_owning("Other.3mf")
        self.edit(row_id, "A, B")
        self.refresh_to(row_id)
        self.assertFalse((self.folder / "A, B.3mf").exists())

    def test_a_failed_refresh_keeps_the_old_files_and_the_row_non_current(self):
        row_id = self.saved_row()
        self.edit(row_id)
        self.fail_on = "Widget"
        result = self.save([row_id])
        self.assertEqual(result["partial_stage"], "generate")
        row = self.rows()[row_id]
        self.assertEqual((row["status"], row["file"]), ("in_design", ""))
        self.assertTrue((self.folder / "Widget.3mf").is_file())
        self.assertEqual(load_inventory(self.folder)["layout"]["stale_files"], {row_id: ["Widget.3mf"]})
        # ...and a later retry can still retire the old file.
        self.fail_on = None

        def renamed(output_dir, spec):
            path = Path(output_dir) / "Widget rev2.3mf"
            path.write_bytes(b"new")
            return [path]

        save_inventory_bins(self.folder, [row_id], False, renamed)
        self.assertFalse((self.folder / "Widget.3mf").exists())

    def test_stale_current_files_can_never_be_printed_as_the_new_design(self):
        row_id = self.saved_row()
        self.edit(row_id)
        result = self.print([row_id])
        self.assertNotIn("partial", result)
        self.assertEqual(self.generated, ["Widget"])          # regenerated, not the stale file
        self.assertEqual(self.rows()[row_id]["status"], "printed")

    def test_client_layout_saves_cannot_erase_stale_tracking(self):
        row_id = self.saved_row()
        self.edit(row_id)
        inv = load_inventory(self.folder)
        layout = json.loads(json.dumps(inv["layout"]))
        layout.pop("stale_files", None)
        save_inventory(self.folder, layout=layout)
        self.assertEqual(load_inventory(self.folder)["layout"]["stale_files"], {row_id: ["Widget.3mf"]})


class CatalogContractTests(unittest.TestCase):
    def test_cradle_floor_gap_is_not_an_editor_field_but_is_still_tolerated(self):
        import wavefinity_web
        catalog = wavefinity_web.catalog_payload()
        cradle = next(one for one in catalog["parts"] if one["kind"] == "cradle")
        self.assertNotIn("floor_gap", [one["key"] for one in cradle["fields"]])
        self.assertIn("floor_gap", [one["key"] for one in cradle["options"]])

    def test_a_legacy_floor_gap_does_not_change_the_height_estimate(self):
        import organizer_app
        from organizer_inserts import CRADLE_FLOOR_GAP, Item, Zone
        box = organizer_app.BoxSpec(88.0, 40.0, 30.0)
        item = Item.simple("rod", 40.0, 10.0)
        plain = organizer_app.Feature("cradle", Zone(-40, -10, 40, 10), item)
        legacy = organizer_app.Feature("cradle", Zone(-40, -10, 40, 10), item, options={"floor_gap": 9.0})
        base = box.base_thickness
        self.assertEqual(organizer_app._feature_height(box, plain, base), base + CRADLE_FLOOR_GAP + item.widest / 2.0)
        self.assertEqual(organizer_app._feature_height(box, legacy, base), organizer_app._feature_height(box, plain, base))


class BrowserStateTests(unittest.TestCase):
    def test_photo_nest_push_out_survives_unrelated_edits(self):
        prelude = "\n".join(function_source(name) for name in (
            "applyNestAccessOptions", "setNestPushOut", "nestFingerAccessVisible"))
        out = node_run(prelude + """
const results = {};
// Any unrelated edit (Tool thickness, clearance, count, auto-size) leaves Push Out alone.
for (const changed of ["option:tool_thickness", "option:clearance", "nest-count", "option:auto_size", "option:cavity_depth"]) {
  const options = { lift_assist: "push_out", finger_position: "sides" };
  // The visible Finger access select cannot represent push_out and reads "auto".
  applyNestAccessOptions(options, changed, key => ({ "option:lift_assist": "auto", "option:finger_position": "both" })[key]);
  results[changed] = options;
}
results.hidden = nestFingerAccessVisible("raised_wall", "push_out");
results.shownAuto = nestFingerAccessVisible("raised_wall", "auto");
results.shownRecessed = nestFingerAccessVisible("recessed", "auto");
const off = {}; setNestPushOut(off, true); results.on = off.lift_assist;
setNestPushOut(off, false); results.off = off.lift_assist;
// Custom Finger access writes location only from its own controls.
const custom = { lift_assist: "finger_grasp" };
applyNestAccessOptions(custom, "option:finger_position", key => key === "option:finger_position" ? "top_bottom" : "auto");
results.custom = custom;
const choose = { lift_assist: "auto" };
applyNestAccessOptions(choose, "option:lift_assist", key => key === "option:lift_assist" ? "finger_grasp" : undefined);
results.choose = choose;
process.stdout.write(JSON.stringify(results));
""")
        for changed in ("option:tool_thickness", "option:clearance", "nest-count", "option:auto_size", "option:cavity_depth"):
            self.assertEqual(out[changed], {"lift_assist": "push_out", "finger_position": "sides"}, changed)
        self.assertFalse(out["hidden"])
        self.assertTrue(out["shownAuto"])
        self.assertTrue(out["shownRecessed"])
        self.assertEqual((out["on"], out["off"]), ("push_out", "auto"))
        self.assertEqual(out["custom"], {"lift_assist": "finger_grasp", "finger_position": "top_bottom"})
        self.assertEqual(out["choose"], {"lift_assist": "finger_grasp"})

    def test_photo_nest_switching_to_recessed_still_clears_push_out(self):
        self.assertRegex(
            APP_JS,
            r'changed === "option:holder_style" && one\.options\.holder_style === "recessed"\s*'
            r'&& one\.options\.lift_assist === "push_out"\)\s*\{\s*one\.options\.lift_assist = "auto"')

    def test_photo_nest_editor_reads_owner_first(self):
        start = APP_JS.index("function renderNestFields(")
        body = APP_JS[start:APP_JS.index("\n}\n", start)]
        order = [body.index(f'editor-group-label">{label}<') for label in ("Holder", "Access", "Fit", "Bin")]
        self.assertEqual(order, sorted(order))
        self.assertLess(body.index("Nest type"), body.index('"Tool thickness"'))
        self.assertIn("nestFingerAccessVisible(holderStyle, assist)", body)

    def test_bore_style_and_sizing_mode_helpers(self):
        out = node_run(
            function_source("normalizeBoreStyle") + function_source("boreStyleOf")
            + function_source("boreXyMode") + function_source("boreHeightMode") + """
const BORE_STYLES = [["base_straight", "a"], ["base_wavy", "b"], ["walls_straight", "c"], ["walls_wavy", "d"]];
const BORE_LEGACY_STYLES = { full_base: "base_straight", wavy_base: "base_wavy" };
const boreWallsOnly = style => style === "walls_straight" || style === "walls_wavy";
const state = { draftResolvedOptions: {} };
const of = options => ({ options });
process.stdout.write(JSON.stringify({
  legacy: [normalizeBoreStyle("full_base"), normalizeBoreStyle("wavy_base"),
    normalizeBoreStyle("wall_only", "straight"), normalizeBoreStyle("wall_only", "wavy"),
    normalizeBoreStyle(undefined), normalizeBoreStyle("walls_straight")],
  baseXy: boreXyMode(of({ bore_style: "base_straight" })),
  wallsXy: boreXyMode(of({ bore_style: "walls_wavy" })),
  wallsBoreToBin: boreXyMode(of({ bore_style: "walls_wavy", xy_size_mode: "bore_to_bin" })),
  wallsManual: boreXyMode(of({ bore_style: "walls_straight", xy_size_mode: "manual" })),
  baseBinToBore: boreXyMode(of({ bore_style: "base_wavy", xy_size_mode: "bin_to_bore" })),
  height: [boreHeightMode(of({})), boreHeightMode(of({ height_size_mode: "bore_to_bin" })),
    boreHeightMode(of({ height_size_mode: "bogus" }))],
}));
""")
        self.assertEqual(out["legacy"], ["base_straight", "base_wavy", "walls_straight",
                                         "walls_wavy", "base_straight", "walls_straight"])
        self.assertEqual(out["baseXy"], "manual")
        self.assertEqual(out["wallsXy"], "bin_to_bore")        # Walls Only defaults to bin-to-bore
        self.assertEqual(out["wallsBoreToBin"], "bin_to_bore")  # not offered for Walls Only
        self.assertEqual(out["wallsManual"], "manual")          # an explicit mode is kept
        self.assertEqual(out["baseBinToBore"], "bin_to_bore")
        self.assertEqual(out["height"], ["manual", "bore_to_bin", "manual"])

    def test_apply_bore_sizing_drops_retired_state_and_owns_bore_to_bin(self):
        out = node_run(
            function_source("normalizeBoreStyle") + function_source("boreStyleOf")
            + function_source("boreXyMode") + function_source("boreHeightMode")
            + function_source("applyBoreSizing") + """
const BORE_STYLES = [["base_straight", "a"], ["base_wavy", "b"], ["walls_straight", "c"], ["walls_wavy", "d"]];
const BORE_LEGACY_STYLES = { full_base: "base_straight", wavy_base: "base_wavy" };
const boreWallsOnly = style => style === "walls_straight" || style === "walls_wavy";
const binInsideExtent = () => [40, 30];
const state = { draftResolvedOptions: {}, pinnedZone: { width: true, depth: true },
  design: { box: {} } };
const legacy = { kind: "bore", zone: [-5, -5, 5, 5], options: {
  bore_style: "wavy_base", auto_base: true, auto_height: true, auto_grid: true,
  wall_style: "straight", wall: 2, height: 9, angle: 30, angle_towards: "left" } };
applyBoreSizing(legacy);
const fill = { kind: "bore", zone: [-5, -5, 5, 5], options: {
  bore_style: "base_straight", xy_size_mode: "bore_to_bin", height_size_mode: "bore_to_bin", height: 9 } };
const filled = applyBoreSizing(fill);
const walls = { kind: "bore", zone: [-5, -5, 5, 5], options: {
  bore_style: "walls_wavy", xy_size_mode: "bore_to_bin", wall: 1.2, angle: 20 } };
const wallsFilled = applyBoreSizing(walls);
process.stdout.write(JSON.stringify({ legacy, fill, filled, walls, wallsFilled, pinned: state.pinnedZone }));
""")
        legacy = out["legacy"]["options"]
        self.assertEqual(legacy["bore_style"], "base_wavy")
        for retired in ("auto_base", "auto_height", "auto_grid", "wall_style", "wall",
                        "angle", "angle_towards"):
            self.assertNotIn(retired, legacy)
        self.assertEqual((legacy["xy_size_mode"], legacy["height_size_mode"]), ("manual", "manual"))
        self.assertEqual(out["legacy"]["zone"], [-5, -5, 5, 5])   # no hidden fill
        self.assertTrue(out["filled"])
        self.assertEqual(out["fill"]["zone"], [-20, -15, 20, 15])
        self.assertNotIn("height", out["fill"]["options"])        # hidden manual height never wins
        # Walls Only never offers bore-to-bin: it falls back to its default mode.
        self.assertFalse(out["wallsFilled"])
        self.assertEqual(out["walls"]["options"]["xy_size_mode"], "bin_to_bore")
        self.assertEqual(out["walls"]["options"]["wall"], 1.2)
        self.assertNotIn("angle", out["walls"]["options"])

    STALE_PRELUDE = r"""
const timers = [];
const setTimeout = (fn) => { timers.push(fn); return timers.length; };
let spaceAutosaveTimer = null; let isGenerating = false;
const state = { runtime: { hosted: false }, designMutationBusy: false, folderMode: "space",
  activeSpaceId: "A", output: "/A" };
const spaces = {
  A: { rows: { B1: { id: "B1", kind: "bin", file: "" }, B3: { id: "B3", kind: "bin", file: "Old.3mf" } },
       settings: { auto_update_changed_files: false }, specs: { B1: {}, B3: {} } },
  B: { rows: { B1: { id: "B1", kind: "bin", file: "" } },
       settings: { auto_update_changed_files: false }, specs: { B1: {} } },
};
let active = "A";
const log = { asked: [], generated: [], saves: [], api: [], status: [] };
const DL = {
  loadEpoch: 1, busy: "", listeners: [],
  on(fn) { this.listeners.push(fn); },
  folder: () => state.output,
  spaceContext() { return { epoch: this.loadEpoch, output: state.output, spaceId: state.activeSpaceId || null }; },
  spaceContextCurrent(c) { return Boolean(c) && c.epoch === this.loadEpoch && c.output === state.output && c.spaceId === (state.activeSpaceId || null); },
  staleSpaceError() { const e = new Error("stale"); e.code = "STALE_SPACE_CONTEXT"; return e; },
  isStaleSpaceError: e => e?.code === "STALE_SPACE_CONTEXT",
  requireSpaceContext(c) { if (!this.spaceContextCurrent(c)) throw this.staleSpaceError(); },
  bin: id => spaces[active].rows[id],
  label: row => row.id,
  get layout() { return { settings: spaces[active].settings, design_specs: spaces[active].specs }; },
  change(fn) { fn(); },
  async save() { log.saves.push(active); return true; },
  busyWith: async (what, work) => work(DL.spaceContext()),
  async inventoryCall(path, payload) { log.status.push([active, payload.row_id]); return {}; },
  adopt() {}, emit() {},
};
function switchTo(id) {
  active = id; state.activeSpaceId = id; state.output = "/" + id; DL.loadEpoch += 1;
  DL.listeners.forEach(fn => fn());
}
const typedSpaceOrdinaryBin = () => true;
const clone = v => JSON.parse(JSON.stringify(v));
const toast = () => {};
async function flushSpaceDesignAutosave() { if (hooks.duringFlush) hooks.duringFlush(); return true; }
async function api() { log.api.push(active); return {}; }
async function saveGeneratedFiles() { return ["Made.3mf"]; }
const hooks = {};
let answer = { choice: "primary", checked: false, during: null };
async function appConfirm(options) {
  log.asked.push([active, options.title]);
  if (answer.during) answer.during();
  appConfirm.checked = answer.checked;
  return answer.choice;
}
"""

    def stale_source(self):
        start = APP_JS.index("// Fix 061 F6: rows whose saved files just went stale")
        return (APP_JS[start:APP_JS.index("function queueSpaceDesignAutosave()", start)]
                + "\n" + function_source("designerGenerateInventoryRow"))

    def run_stale(self, body):
        return node_run(self.STALE_PRELUDE + self.stale_source() + "\n(async () => {\nconst out = {};\n"
                        + body + "\nprocess.stdout.write(JSON.stringify(out));\n})();")

    def test_stale_file_refresh_asks_once_then_follows_the_space_preference(self):
        out = self.run_stale("""
const ctxA = DL.spaceContext();
answer = { choice: "cancel", checked: false };
queueStaleFileRefresh(ctxA, "B1"); await settleStaleFileRefresh();
out.notNow = { asked: log.asked.length, api: log.api.length, auto: spaces.A.settings.auto_update_changed_files };
// Not now leaves it dropped: no ghost prompt on later settles.
await settleStaleFileRefresh(); out.afterNotNow = log.asked.length;
// Update + checkbox: regenerates and turns the Space preference on.
answer = { choice: "primary", checked: true };
queueStaleFileRefresh(ctxA, "B1"); await settleStaleFileRefresh();
out.update = { asked: log.asked.length, api: log.api.length, auto: spaces.A.settings.auto_update_changed_files, saves: log.saves.length };
// Automatic mode: no dialog at all.
queueStaleFileRefresh(ctxA, "B1"); await settleStaleFileRefresh();
out.automatic = { asked: log.asked.length, api: log.api.length };
// A row that is already current again (or gone) is skipped.
queueStaleFileRefresh(ctxA, "B3"); queueStaleFileRefresh(ctxA, "B9"); await settleStaleFileRefresh();
out.skipped = log.api.length;
// While the Designer is busy nothing runs and a retry is scheduled.
state.designMutationBusy = true; timers.length = 0;
queueStaleFileRefresh(ctxA, "B1"); const before = log.api.length; await settleStaleFileRefresh();
out.busy = { ran: log.api.length - before, retry: timers.length > 0 };
// A pending autosave (rapid edits) is respected: still nothing generated yet.
state.designMutationBusy = false; spaceAutosaveTimer = 7;
await settleStaleFileRefresh(); out.pending = log.api.length - before;
// Once the edits settle, exactly one regeneration of the queued row happens.
spaceAutosaveTimer = null; await settleStaleFileRefresh(); out.settled = log.api.length - before;
""")
        self.assertEqual(out["notNow"], {"asked": 1, "api": 0, "auto": False})
        self.assertEqual(out["afterNotNow"], 1)
        self.assertEqual(out["update"], {"asked": 2, "api": 1, "auto": True, "saves": 1})
        self.assertEqual(out["automatic"], {"asked": 2, "api": 2})
        self.assertEqual(out["skipped"], 2)
        self.assertEqual(out["busy"], {"ran": 0, "retry": True})
        self.assertEqual(out["pending"], 0)
        self.assertEqual(out["settled"], 1)

    def test_a_queued_refresh_never_resolves_through_another_space(self):
        # Space A and Space B both have a row B1.
        out = self.run_stale("""
const ctxA = DL.spaceContext();
queueStaleFileRefresh(ctxA, "B1");
switchTo("B");
await settleStaleFileRefresh();
out.inB = { asked: log.asked.length, api: log.api.length, bAuto: spaces.B.settings.auto_update_changed_files, saves: log.saves.length };
out.stillQueued = staleFileRefreshQueue.size;
""")
        self.assertEqual(out["inB"], {"asked": 0, "api": 0, "bAuto": False, "saves": 0})
        self.assertEqual(out["stillQueued"], 1)

    def test_a_modal_answer_after_a_space_switch_is_not_applied_to_the_new_space(self):
        out = self.run_stale("""
const ctxA = DL.spaceContext();
answer = { choice: "primary", checked: true, during: () => switchTo("B") };
queueStaleFileRefresh(ctxA, "B1");
await settleStaleFileRefresh();
out.update = { api: log.api.length, saves: log.saves.length, bAuto: spaces.B.settings.auto_update_changed_files,
  aAuto: spaces.A.settings.auto_update_changed_files, requeued: staleFileRefreshQueue.size, askedIn: log.asked.map(x => x[0]) };
// "Not now" answered after the switch stays dropped (no ghost prompt on return).
switchTo("A"); staleFileRefreshQueue.clear();
answer = { choice: "cancel", checked: false, during: () => switchTo("B") };
queueStaleFileRefresh(DL.spaceContext(), "B1");
await settleStaleFileRefresh();
out.notNow = { requeued: staleFileRefreshQueue.size, api: log.api.length };
""")
        self.assertEqual(out["update"], {"api": 0, "saves": 0, "bAuto": False, "aAuto": False,
                                         "requeued": 1, "askedIn": ["A"]})
        self.assertEqual(out["notNow"], {"requeued": 0, "api": 0})

    def test_automatic_mode_in_one_space_never_regenerates_in_another(self):
        out = self.run_stale("""
spaces.A.settings.auto_update_changed_files = true;
const ctxA = DL.spaceContext();
queueStaleFileRefresh(ctxA, "B1");
switchTo("B");
await settleStaleFileRefresh();
out.settle = { api: log.api.length, asked: log.asked.length, status: log.status.length };
// Even calling the generator directly with A's context cannot cross into B.
await designerGenerateInventoryRow("B1", ctxA);
out.direct = { api: log.api.length, status: log.status.length };
// ...nor if the switch happens while the Designer flush is awaited.
switchTo("A"); const ctxA2 = DL.spaceContext();
hooks.duringFlush = () => switchTo("B");
await designerGenerateInventoryRow("B1", ctxA2);
out.duringFlush = { api: log.api.length, status: log.status.length };
""")
        self.assertEqual(out["settle"], {"api": 0, "asked": 0, "status": 0})
        self.assertEqual(out["direct"], {"api": 0, "status": 0})
        self.assertEqual(out["duringFlush"], {"api": 0, "status": 0})

    def test_returning_to_the_original_space_resumes_the_pending_entry_once(self):
        out = self.run_stale("""
const ctxA = DL.spaceContext();
answer = { choice: "cancel", checked: false };
queueStaleFileRefresh(ctxA, "B1");
switchTo("B");
await settleStaleFileRefresh(); out.whileAway = log.asked.length;
timers.length = 0;
switchTo("A");                                 // the watcher schedules the resume
out.scheduled = timers.length > 0;
await settleStaleFileRefresh();                // asks once in A, user says Not now
out.onReturn = log.asked.map(x => x[0]);
await settleStaleFileRefresh(); out.noGhost = log.asked.length;
out.queue = staleFileRefreshQueue.size;
""")
        self.assertEqual(out["whileAway"], 0)
        self.assertTrue(out["scheduled"])
        self.assertEqual(out["onReturn"], ["A"])
        self.assertEqual(out["noGhost"], 1)
        self.assertEqual(out["queue"], 0)

    def test_batch_scope_switches_between_whole_space_and_subset(self):
        start = DRAWER_PANEL_JS.index("DP.batchScope = () => {")
        source = DRAWER_PANEL_JS[start:DRAWER_PANEL_JS.index("DP.renderBatch = () => {")]
        out = node_run("""
const rows = [
  { id: "B1", kind: "bin", file: "", status: "in_design" },
  { id: "B2", kind: "bin", file: "b2.3mf", status: "saved" },
  { id: "B3", kind: "bin", file: "b3.3mf", status: "printed" },
  { id: "B4", kind: "manual", file: "", status: "in_design" },
];
const DL = { bins: rows, layout: { design_specs: { B1: {}, B2: {}, B3: {} } },
  bin: id => rows.find(r => r.id === id),
  printEligible: one => Boolean(one) && ["bin", "b4b"].includes(one.kind) && (Boolean(String(one.file || "").trim()) || Boolean(DL.layout.design_specs[one.id])),
  printNeeded: one => (DL.printEligible(one) && one.status !== "printed" ? 1 : 0),
  saveNeeded: one => (DL.printEligible(one) && !String(one.file || "").trim() ? 1 : 0),
  printCount: one => (DL.printEligible(one) ? 1 : 0) };
const DP = { printSelected: new Set() };
""" + source + """
const ids = list => list.map(one => one.id);
const out = {};
let scope = DP.batchScope();
out.none = { subset: scope.subset, save: ids(scope.save), print: ids(scope.print), payload: DP.printSelectionPayload() };
DP.printSelected = new Set(["B3", "B1", "B4"]);
scope = DP.batchScope();
out.subset = { subset: scope.subset, save: ids(scope.save), print: ids(scope.print), saveIds: DP.batchSaveIds(), payload: DP.printSelectionPayload() };
process.stdout.write(JSON.stringify(out));
""")
        self.assertEqual(out["none"], {"subset": False, "save": ["B1"], "print": ["B1", "B2"],
                                       "payload": {"B1": 1, "B2": 1}})
        self.assertEqual(out["subset"], {"subset": True, "save": ["B3", "B1"], "print": ["B3", "B1"],
                                         "saveIds": ["B3", "B1"], "payload": {"B3": 1, "B1": 1}})


class StaticContractTests(unittest.TestCase):
    def test_bulk_success_wording_no_longer_claims_a_bambu_project(self):
        self.assertNotIn("Opened one Bambu project", DRAWER_MODEL_JS)
        self.assertNotIn("result.project", DRAWER_MODEL_JS)
        self.assertIn('"Opened in Bambu Studio"', DRAWER_MODEL_JS)
        self.assertIn("bin_copies", DRAWER_MODEL_JS)
        self.assertIn("connector_copies", DRAWER_MODEL_JS)
        self.assertNotIn("in one project", INDEX_HTML)

    def test_inventory_batch_controls_and_edit_shortcut(self):
        for text in ('id="dl-batch-save"', 'id="dl-batch-print"', 'id="dl-batch-connectors"'):
            self.assertIn(text, DRAWER_PANEL_JS)
        for label in ("Save All Needed (", "Print All Not Printed (", "Save Selected (",
                      "Print Selected to Bambu Studio ("):
            self.assertIn(label, DRAWER_PANEL_JS)
        # One visible Edit action on the row itself (not inside the details
        # disclosure), routed through the existing Designer edit path.
        row = DRAWER_PANEL_JS[DRAWER_PANEL_JS.index("const actions = spacer"):]
        row = row[:row.index("</div>`;")]
        self.assertIn('data-act="edit"', row)
        self.assertIn("editable ?", row)
        self.assertIn('else if (action === "edit") designerEditInventoryRow(one.id);', DRAWER_PANEL_JS)
        self.assertEqual(APP_JS.count("async function designerEditInventoryRow("), 1)
        self.assertIn("<summary>Drawer details</summary>", DRAWER_PANEL_JS)
        self.assertNotIn("Advanced Settings", DRAWER_PANEL_JS)
        for label in ("Bin", "Planning", "Size"):
            self.assertIn(f'dl-group-label">{label}<', DRAWER_PANEL_JS)

    def test_settings_groups_on_the_ten_surfaces(self):
        css = (WEB / "styles.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.thickness-grabber-row \{[^}]*repeat\(2, 1fr\)")
        for label in ("Base", "Planning"):
            self.assertIn(f'setting-group-label">{label}<', INDEX_HTML)
        self.assertIn("Planning only — does not change the bin.", INDEX_HTML)
        for label in ("Opening", "Vertical position", "Walls"):
            self.assertIn(f'setting-group-label">{label}<', INDEX_HTML)
        for label in ("Tool", "Post", "Steps size", "Bottom", "Division labels", "Text", "Placement", "Footprint"):
            self.assertIn(f'editorGroup("{label}"', APP_JS) if label not in ("Bottom", "Division labels") \
                else self.assertIn(f'editor-group-label">{label}<', APP_JS)
        # Post shows the physical part before its repeat layout; Steps keeps
        # Height / Lip with Width / Depth.
        self.assertIn('editorGroup("Post", `<div class="draft-triple">${bodyHtml}</div>`) + repeatsHtml', APP_JS)
        self.assertIn('editorGroup("Steps size", `<div class="pair">${stepsSizeHtml}${bodyHtml}</div>`) + repeatsHtml', APP_JS)
        self.assertIn('cradleToolHtml = editorGroup("Tool"', APP_JS)

    def test_readme_current_contract_matches_the_accepted_ui(self):
        for stale in ("Customize your bin", "Label your bin", "Standard walls?", "Auto-save* (on by default)",
                      "beside *Save Location*", "under *Advanced Settings*"):
            self.assertNotIn(stale, README)
        self.assertNotIn("Add interior part** finds", README)
        for current in ("Parts & options", "Space layout autosave is always on", "Bin Name",
                        "Save All Needed", "auto_update_changed_files", "Drawer details"):
            self.assertIn(current, README)
        self.assertIn("Bambu", README)

    def test_stale_file_hooks_are_wired_into_the_one_autosave_path(self):
        self.assertIn("data.files_became_stale", APP_JS)
        self.assertIn("scheduleStaleFileRefresh();", APP_JS)
        self.assertIn("await designerGenerateInventoryRow(entry.rowId, context);", APP_JS)
        self.assertIn("queueStaleFileRefresh(context, data.row_id);", APP_JS)
        self.assertIn("auto_update_changed_files: false", DRAWER_MODEL_JS)
        self.assertIn('id="app-confirm-check"', INDEX_HTML)
        self.assertIn('id="dl-refresh-saved"', DRAWER_PANEL_JS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
