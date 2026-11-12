"""Story 2972's bounded editor parsing, payload and generation check."""
import json
from pathlib import Path
import subprocess
import unittest

from organizer_app_impl._design_io import design_from_dict, design_to_dict
from organizer_engine import BoxSpec, make_box
from organizer_inserts import Layout
from wavefinity_web_impl._ai import grid_editor_catalog
import wavefinity_web as web


ROOT = Path(__file__).resolve().parents[1]


class GridfinityEditorChecks(unittest.TestCase):
    def test_editor_parsing_and_commits(self):
        script = r'''
const fs = require("fs"), vm = require("vm"), assert = require("assert/strict");
const catalog = JSON.parse(fs.readFileSync(0, "utf8"));
const nodes = {};
function node() { return { value: "", after() {}, setAttribute() {}, removeAttribute() {},
  toggleAttribute() {}, setCustomValidity(message) { this.error = message; } }; }
const context = vm.createContext({ console, structuredClone, state: { catalog, activeSpace: null },
  debounce: fn => fn, fmt: String, number: (v, f) => Number.isFinite(Number(v)) ? Number(v) : f,
  clone: structuredClone, b4bEnabled: () => false, baseTrimEnabled: () => false,
  isSurfaceBinDesign: () => false, roundUpHalfMm: v => Math.ceil(v * 2) / 2,
  $: selector => nodes[selector] ||= node(),
  document: { getElementById: id => nodes[id] ||= node(), createElement: node },
});
for (const file of ["05-surface-trim-form.js", "06-form-sync-controls.js",
                    "09-draft-sizing-helpers.js", "10-draft-update-commit.js"])
  vm.runInContext(fs.readFileSync(`web/app/${file}`, "utf8"), context);
vm.runInContext(`
  syncBinPrinterWarning = () => {};
  updateGenerateAvailability = () => {};
  changedDesign = () => {};
  markBinAxisManual = () => {};
  syncLidForm = () => {};
`, context);
context.assert = assert;
vm.runInContext(`
for (const grid of state.catalog.grids) {
  state.design = { grid: grid.value, box: { x: 42, y: 42, z: 42, base_thickness: 0.8 } };
  const pitch = grid.pitch_mm;
  for (const text of ["6", "6u"]) assert.equal(parseHorizontalDimension(text).mm, 6 * pitch);
  assert.equal(parseHorizontalDimension(String(pitch)).mm, pitch);
  assert.equal(parseHorizontalDimension("1.5u").reason, "whole_cells");
  assert.equal(parseHorizontalDimension("6mm").mm ?? null, pitch === 7 ? 7 : null);
  assert.equal(parseHorizontalDimension(String(pitch + 2) + "mm").mm, pitch);
  assert.equal(parseHorizontalDimension("1000mm").reason, "range");
  assert.equal(parseHorizontalDimension("0").reason, "positive_number");
  assert.equal(parseHorizontalDimension("-6u").reason, "positive_number");
  assert.equal(parseVerticalDimension("6").mm, grid.value === "wavefinity" ? 6 : 42);
  if (grid.value !== "wavefinity") {
    assert.equal(parseVerticalDimension("6u").mm, 42);
    assert.equal(parseVerticalDimension("1.5u").reason, "whole_cells");
    assert.equal(parseVerticalDimension("1u").reason, "range");
  }
  bindBinSizeFields();
  $("#x-size").value = "6u";
  state.binSizeFields.x.edited = true;
  assert.equal(readBinSizeField("x"), 42); // an unrelated form read cannot parse typing
  assert.equal(commitBinDimension("x"), true);
  assert.equal(state.design.box.x, 6 * pitch);
  assert.equal($("#x-size").value, String(6 * pitch) + "mm");
  const before = JSON.stringify(state.design);
  $("#x-size").value = "1.5u";
  state.binSizeFields.x.edited = true;
  assert.equal(commitBinDimension("x"), false);
  assert.equal(JSON.stringify(state.design), before);
  assert.match($("#x-size").error, /whole number/);
}
state.design = { box: { x: 49, y: 42, z: 42, base_thickness: 0.8 } };
bindBinSizeFields();
const selector = { value: "gridfinity" };
commitBinGrid({ target: selector });
assert.equal(selector.value, "wavefinity");
assert.equal(state.design.box.x, 49);
assert.equal(state.design.grid, undefined);
state.design.box.x = 42;
selector.value = "gridfinity";
commitBinGrid({ target: selector });
assert.equal(state.design.grid, "gridfinity");
assert.equal(state.design.box.x, 42);
`, context);
console.log("Both pitches: parsing, commit-only reads, refusal and grid switching passed.");
'''
        result = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True,
            input=json.dumps({"grids": grid_editor_catalog(), "max_box_size": 350,
                              "base_unit": 7, "min_height_above_base_mm": 5}),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_roundtrip_and_existing_generation_path(self):
        legacy = design_to_dict(BoxSpec(x=42, y=42, z=40), Layout())
        legacy.pop("grid")
        restored = design_to_dict(*design_from_dict(json.loads(json.dumps(legacy))))
        self.assertEqual(restored.pop("grid"), "wavefinity")
        self.assertEqual(restored, legacy)
        for grid, pitch in (("gridfinity_half", 21), ("gridfinity", 42)):
            raw = design_to_dict(BoxSpec(x=6*pitch, y=pitch, z=42), Layout())
            raw["grid"] = grid
            saved = design_to_dict(*design_from_dict(raw))
            reloaded = design_from_dict(json.loads(json.dumps(saved)))
            self.assertEqual(reloaded[1].design_grid, grid)
            self.assertEqual(design_to_dict(*reloaded), saved)
            mesh = make_box(reloaded[0], grid=reloaded[1].design_grid)
            self.assertTrue(mesh.is_volume)
            self.assertAlmostEqual(mesh.bounds[1, 0] - mesh.bounds[0, 0], 6*pitch - 0.5)
            manifest = web.ai_capability_manifest(grid)
            controls = manifest["bin_controls"]
            self.assertEqual(controls["base_unit_mm"], pitch)
            self.assertFalse(controls["active_grid"]["side_connectors"])
            stacking = next(row for row in manifest["box_modifiers"] if row["kind"] == "lid_stacking")
            self.assertNotIn("lid_with_handle", stacking["example"])
            self.assertNotIn("hinged", [row["value"] for row in stacking["rules"]["grid"]["lid_choices"]])


if __name__ == "__main__":
    unittest.main()
