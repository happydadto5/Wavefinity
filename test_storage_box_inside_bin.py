"""Fix 064: Storage Box "Make Inside Bin" Space Action."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from test_space_preferences import APP_JS, SPACES_JS, block, function_source, js, node_run

ROOT = Path(__file__).resolve().parent
INDEX_HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

FIT_PRELUDE = "\n".join([
    "const number = (v, f = 0) => { const n = Number(v); return Number.isFinite(n) ? n : f; };",
    "const isSurfaceBinDesign = () => false;",
    "const state = { catalog: { base_unit: 8, max_box_size: 350, min_height_above_base_mm: 5 }, design: { box: { base_thickness: 0.6 } } };",
    function_source("normalizeBinDimension"),
    function_source("insideBinFitForStorageBox"),
])


def fit(space, base_unit=8, max_box_size=350, base_thickness=0.6):
    out = node_run(FIT_PRELUDE + js("""
state.catalog.base_unit = __UNIT__;
state.catalog.max_box_size = __MAX__;
state.design.box.base_thickness = __BASE__;
const out = insideBinFitForStorageBox(__SPACE__);
process.stdout.write(JSON.stringify(out));
""", UNIT=base_unit, MAX=max_box_size, BASE=base_thickness, SPACE=space))
    return out


class InsideBinFitTests(unittest.TestCase):
    def test_rounds_down_to_whole_units(self):
        # 81 x 97 x 42 usable interior at an 8 mm unit -> 80 x 96 x 42.
        out = fit({"x": 81, "y": 97, "z": 42})
        self.assertEqual(out, {"x": 80, "y": 96, "z": 42})

    def test_respects_catalog_max_box_size(self):
        out = fit({"x": 200, "y": 200, "z": 42}, max_box_size=96)
        self.assertEqual(out["x"], 96)
        self.assertEqual(out["y"], 96)

    def test_axis_smaller_than_one_unit_is_rejected(self):
        out = fit({"x": 7, "y": 97, "z": 42})
        self.assertIn("error", out)
        out = fit({"x": 80, "y": 7, "z": 42})
        self.assertIn("error", out)

    def test_space_shorter_than_legal_bin_minimum_is_rejected(self):
        # base_thickness 0.6 + min_height_above_base_mm 5 -> the legal floor
        # is 6 mm (ceil(5.6)); a 4 mm usable height cannot hold that.
        out = fit({"x": 80, "y": 80, "z": 4})
        self.assertIn("error", out)

    def test_exact_legal_minimum_height_is_accepted(self):
        out = fit({"x": 80, "y": 80, "z": 6})
        self.assertNotIn("error", out)
        self.assertEqual(out["z"], 6)


DESIGNER_PRELUDE = "\n".join([
    "const clone = v => JSON.parse(JSON.stringify(v));",
    "const number = (v, f = 0) => { const n = Number(v); return Number.isFinite(n) ? n : f; };",
    "const isSurfaceBinDesign = () => false;",
    "const calls = [];",
    "const toasts = []; const toast = (...a) => toasts.push(a);",
    "let guardResult = true; async function guardDraftSwitch() { calls.push('guard'); return guardResult; }",
    "let flushResult = true; async function flushSpaceDesignAutosave() { calls.push('flush'); return flushResult; }",
    "let mutationResult = true; function beginDesignMutation() { calls.push('begin'); return mutationResult; }",
    "function finishDesignMutation() { calls.push('finish'); }",
    "let loadedOverride = null; async function loadFreshOrdinaryDesignForCurrentFolder(overrideBox) { calls.push('load'); loadedOverride = overrideBox; }",
    "const state = { catalog: { base_unit: 8, max_box_size: 350, min_height_above_base_mm: 5 }, design: { box: { base_thickness: 0.6 } }, activeSpace: null, designInventoryId: 'B3', surfaceHeightPromptSkipped: true };",
    function_source("normalizeBinDimension"),
    function_source("insideBinFitForStorageBox"),
    function_source("designerMakeInsideBin"),
])


def run_designer(space, **overrides):
    setup = "\n".join(f"{key} = {json.dumps(value)};" for key, value in overrides.items())
    out = node_run(DESIGNER_PRELUDE + js("""
state.activeSpace = __SPACE__;
""" + setup + """
designerMakeInsideBin().then(() => {
  process.stdout.write(JSON.stringify({
    calls, toasts, loadedOverride,
    designInventoryId: state.designInventoryId,
    surfaceHeightPromptSkipped: state.surfaceHeightPromptSkipped,
  }));
});
""", SPACE=space))
    return out


class DesignerMakeInsideBinTests(unittest.TestCase):
    def test_pending_autosave_flush_failure_cancels_without_touching_design(self):
        out = run_designer({"x": 80, "y": 80, "z": 42}, flushResult=False)
        self.assertEqual(out["calls"], ["guard", "flush"])
        self.assertIsNone(out["loadedOverride"])

    def test_too_small_space_cancels_before_any_mutation(self):
        out = run_designer({"x": 4, "y": 80, "z": 42})
        self.assertEqual(out["calls"], ["guard", "flush"])
        self.assertTrue(out["toasts"][0][1])  # error flag
        self.assertIsNone(out["loadedOverride"])

    def test_success_overrides_only_box_dimensions_and_resets_identity(self):
        out = run_designer({"x": 81, "y": 97, "z": 42})
        self.assertEqual(out["calls"], ["guard", "flush", "begin", "load", "finish"])
        self.assertEqual(out["loadedOverride"], {"x": 80, "y": 96, "z": 42})
        self.assertIsNone(out["designInventoryId"])
        self.assertFalse(out["surfaceHeightPromptSkipped"])
        self.assertEqual(out["toasts"][-1][0], "Started an inside bin.")

    def test_begin_mutation_busy_guard_cancels_before_loading(self):
        out = run_designer({"x": 80, "y": 80, "z": 42}, mutationResult=False)
        self.assertEqual(out["calls"], ["guard", "flush", "begin"])
        self.assertIsNone(out["loadedOverride"])


class MakeInsideBinLifecycleReuseTests(unittest.TestCase):
    """Confirms the fresh-design/reset path stays owned by
    loadFreshOrdinaryDesignForCurrentFolder (shared with New Bin) rather than
    a duplicated clone-the-current-bin path, and never talks to the Inventory
    API merely by building a starter design."""

    def test_load_fresh_design_never_calls_the_inventory_api(self):
        source = function_source("loadFreshOrdinaryDesignForCurrentFolder")
        self.assertNotIn("inventoryCall", source)
        self.assertNotIn("design-source", source)

    def test_load_fresh_design_starts_from_the_catalog_starter_not_the_current_design(self):
        source = function_source("loadFreshOrdinaryDesignForCurrentFolder")
        self.assertIn("freshDesignForCurrentFolder()", source)

    def test_make_inside_bin_builds_on_the_new_bin_starter_not_a_clone(self):
        source = function_source("designerMakeInsideBin")
        self.assertIn("loadFreshOrdinaryDesignForCurrentFolder(", source)
        self.assertNotIn("visibleDesignSnapshot", source)


class MakeInsideBinWiringTests(unittest.TestCase):
    def test_button_present_and_hidden_by_default(self):
        self.assertIn('id="space-make-inside-bin"', INDEX_HTML)
        start = INDEX_HTML.index('id="space-make-inside-bin"')
        tag = INDEX_HTML[INDEX_HTML.rindex("<button", 0, start):INDEX_HTML.index(">", start) + 1]
        self.assertIn("hidden", tag)

    def test_button_placed_alongside_storage_box_structural_actions(self):
        block_html = block('id="space-structural"', "</div>\n            </div>", INDEX_HTML)
        self.assertIn('id="space-structural-save"', block_html)
        self.assertIn('id="space-make-inside-bin"', block_html)

    def test_visible_only_for_storage_box_kind(self):
        source = block("SP.renderStructuralActions = () => {", "\n};", SPACES_JS)
        self.assertIn('kind !== "storage_box"', source)

    def test_wired_to_the_app_owned_designer_action(self):
        source = SPACES_JS[SPACES_JS.index("const wireInfoButtons"):SPACES_JS.index("\n};", SPACES_JS.index("const wireInfoButtons"))]
        self.assertIn('"space-make-inside-bin"', source)
        self.assertIn("designerMakeInsideBin", source)

    def test_storage_box_structural_kind_covers_portable_and_legacy_box(self):
        source = block("SP.structuralKind = () => {", "\n};", SPACES_JS)
        self.assertIn('"portable"', source)
        self.assertIn('"box"', source)


if __name__ == "__main__":
    unittest.main()
