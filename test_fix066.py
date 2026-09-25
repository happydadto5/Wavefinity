from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import organizer_app
from organizer_app import BoxSpec, Layout
from organizer_edge_mount import EdgeMountSpec
from organizer_engine import LidSpec
from test_fix061 import BatchFixture, design, record
from organizer_inventory import change_design_status, load_inventory, save_design_source
from test_space_preferences import function_source, node_run


def box(label_type="separate", side="front", label=True, lid=False, holes=False):
    return BoxSpec(
        48.0, 56.0, 40.0,
        edge_mount=EdgeMountSpec(
            side=side, label_enabled=label, label_text="A" if label else "",
            label_type=label_type, holes_enabled=holes,
        ),
        lid=LidSpec(enabled=True) if lid else LidSpec(),
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
        def d(label_type="separate", side="front", rim="", pos="back", lid=False):
            return {"label": rim, "label_position": pos,
                    "box": {"edge_mount": {"label_enabled": True, "label_type": label_type, "side": side},
                            "lid": {"enabled": lid}}}
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
        ])
        self.assertEqual(out, [
            "edge-mount-separate:rim-label:front", None, "edge-mount-separate:rim-label:back",
            "edge-mount-separate:lid", None, "edge-mount-separate:lid",
            "edge-mount-separate:rim-label:front", None,
        ])


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
