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
from test_fix061 import BatchFixture, design, record
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

    def test_different_wall_or_integrated_same_wall_allowed(self):
        self.preview(box(side="front"), "Rim", "back")
        self.preview(box(label_type="integrated", side="front"), "Rim", "front")

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


class EdgeMountBrowserConflictTests(unittest.TestCase):
    def run_js(self, cases):
        prelude = "\n".join(function_source(name) for name in (
            "rimLabelSideForDesign", "modifierConflicts", "newModifierConflict", "insideGripWalls", "sideOpeningState"))
        return node_run("""
const SIDE_OPENING_SIDE_IDS = ["front", "back", "left", "right"];
const SIDE_OPENING_DEFAULTS = {};
const MODIFIER_SIDE_TO_WALL = {front: "-y", back: "+y", left: "-x", right: "+x"};
const MODIFIER_OPPOSITE_SIDE = {front: "back", back: "front", left: "right", right: "left"};
const MODIFIER_SIDE_LABEL = {front: "Front", back: "Back", left: "Left", right: "Right"};
const state = {catalog: {}};
const number = (v, d = 0) => Number.isFinite(Number(v)) ? Number(v) : d;
""" + prelude + f"""
const cases = {json.dumps(cases)};
process.stdout.write(JSON.stringify(cases.map(([prev, next]) => {{
  const c = newModifierConflict(prev, next); return c && c.key; }})));
""")

    def test_conflict_parity(self):
        def d(label_type="separate", side="front", rim="", pos="back", lid=False, direct=False,
              label=True, holes=False):
            return {"label": rim, "label_position": pos,
                    "box": {"edge_mount": {"label_enabled": label, "holes_enabled": holes,
                                             "label_type": label_type, "side": side},
                            "lid": {"enabled": lid},
                            "stack": {"mode": "direct"} if direct else {}}}
        base = d()
        out = self.run_js([
            [base, d(rim="X", pos="front")],
            [base, d(rim="X", pos="back")],
            [base, d(rim="X", pos="top", side="back")],
            [base, d(lid=True)],
            [d(label_type="integrated", lid=True), d(label_type="integrated", lid=True)],
            [d(label_type="integrated", lid=True), d(lid=True)],
            [d(rim="X", pos="front", label_type="integrated"), d(rim="X", pos="front")],
            [d(rim="X", pos="front"), d(rim="X", pos="front", side="back")],
            [d(), d(direct=True)],
            [d(label_type="integrated"), d(label_type="integrated", direct=True)],
            [d(label=False, holes=True), d(label=False, holes=True, direct=True)],
            [d(direct=True), d()],
            [d(label_type="integrated", direct=True), d(direct=True)],
            [d(label=False, direct=True), d(direct=True)],
        ])
        self.assertEqual(out, [
            "edge-mount-separate:rim-label:front", None, "edge-mount-separate:rim-label:back",
            "edge-mount-separate:lid", None, "edge-mount-separate:lid",
            "edge-mount-separate:rim-label:front", None,
            "edge-mount-separate:direct-stack", None, None, None,
            "edge-mount-separate:direct-stack", "edge-mount-separate:direct-stack",
        ])

    def test_lid_configuration_change_uses_conflict_guard(self):
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index('["#lid-configuration", "#lid-thickness"')
        end = source.index('  $("#lid-label-text")', start)
        handler = source[start:end]
        self.assertIn('const previous = clone(state.design);', handler)
        self.assertIn('readStackForm(state.design);', handler)
        self.assertIn('changedDesign(previous);', handler)

        label_start = source.index('$("#edge-mount-label-mode")?.addEventListener("change"')
        label_end = source.index('$("#edge-mount-holes-enabled")?.addEventListener("change"', label_start)
        label_handler = source[label_start:label_end]
        self.assertIn('syncEdgeMountEditorVisibility();', label_handler)
        self.assertIn('changedDesign();', label_handler)


class CurrentDocumentationTests(unittest.TestCase):
    def test_readme_records_current_holder_divider_and_side_opening_contracts(self):
        readme = (Path(__file__).resolve().parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("Slot Rack: angled slots", readme)
        self.assertIn("Tiered riser shelves", readme)
        self.assertNotIn('There is no separate "slot" kind', readme)
        self.assertIn("full-span - also gets a 1 mm, 45-degree strengthening chamfer", readme)
        self.assertNotIn("full-span divider does not get one yet", readme)
        self.assertIn("**% from bottom** - defaults to 0%", readme)
        self.assertIn("**% from top** - defaults to 0%", readme)


class CommaFileStaleTests(BatchFixture):
    def test_ambiguous_comma_cell_never_deletes_unrelated_file(self):
        (self.folder / "Nuts.3mf").write_bytes(b"other")
        row_id = save_design_source(self.folder, design=design("W"), record=record("W"))["row_id"]
        (self.folder / "W.3mf").write_bytes(b"old")
        change_design_status(self.folder, row_id, "saved", "W.3mf")
        # Persist an ambiguous File cell: comma-named file plus a missing one.
        path = Path(load_inventory(self.folder)["file"])
        path.write_text(path.read_text(encoding="utf-8").replace(
            "W.3mf", "Box Bolts, Nuts.3mf, Missing.3mf"), encoding="utf-8")
        self.assertEqual(self.rows()[row_id]["file"], "Box Bolts, Nuts.3mf, Missing.3mf")
        edited = save_design_source(
            self.folder, design=design("W", 24), record=record("W", 24), row_id=row_id)
        stale = edited["layout"].get("stale_files", {}).get(row_id, [])
        self.assertNotIn("Nuts.3mf", stale)
        self.assertEqual(stale, [])
        (self.folder / "W v2.3mf").write_bytes(b"new")
        result = change_design_status(self.folder, row_id, "saved", "W v2.3mf")
        self.assertTrue((self.folder / "Nuts.3mf").is_file())
        self.assertTrue((self.folder / "W v2.3mf").is_file())
        self.assertNotIn(row_id, result["layout"].get("stale_files", {}))


if __name__ == "__main__":
    unittest.main()
