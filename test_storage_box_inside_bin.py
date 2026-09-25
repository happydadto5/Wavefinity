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
    # state.design is the CURRENTLY OPEN bin - deliberately given a different
    # base_thickness than the candidate in tests below, so a test that reads
    # the wrong one (Fix 064 Correction 1) is caught.
    "const state = { catalog: { base_unit: 8, max_box_size: 350, min_height_above_base_mm: 5 }, design: { box: { base_thickness: 0.6 } } };",
    function_source("normalizeBinDimension"),
    function_source("insideBinFitForStorageBox"),
])


def fit(space, base_unit=8, max_box_size=350, base_thickness=0.6, candidate_base_thickness=None, open_bin_base_thickness=0.6):
    candidate_base = base_thickness if candidate_base_thickness is None else candidate_base_thickness
    out = node_run(FIT_PRELUDE + js("""
state.catalog.base_unit = __UNIT__;
state.catalog.max_box_size = __MAX__;
state.design.box.base_thickness = __OPEN_BASE__;
const candidate = { box: { base_thickness: __CANDIDATE_BASE__ } };
const out = insideBinFitForStorageBox(__SPACE__, candidate);
process.stdout.write(JSON.stringify(out));
""", UNIT=base_unit, MAX=max_box_size, OPEN_BASE=open_bin_base_thickness, CANDIDATE_BASE=candidate_base, SPACE=space))
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

    def test_z_check_uses_the_fresh_candidate_base_not_the_open_bins(self):
        # Fix 064 Correction 1: a thin currently-open bin (0.6 mm) must not
        # wave through a Storage Box that is too short for the fresh
        # inside-bin candidate's own remembered Base (10 mm).
        out = fit({"x": 80, "y": 80, "z": 12}, open_bin_base_thickness=0.6, candidate_base_thickness=10)
        self.assertIn("error", out)

    def test_z_check_does_not_over_reject_using_the_open_bins_base(self):
        # And the inverse: a thick currently-open bin (10 mm) must not
        # reject a height that is legal for the thinner fresh candidate
        # (0.6 mm) that will actually be installed.
        out = fit({"x": 80, "y": 80, "z": 12}, open_bin_base_thickness=10, candidate_base_thickness=0.6)
        self.assertNotIn("error", out)
        self.assertEqual(out["z"], 12)


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
    # The remembered reusable Space preference for the fresh candidate's own
    # Base thickness - deliberately independent of state.design (the bin
    # currently open), which is what Fix 064 Correction 1 requires callers
    # to stop reading for this decision.
    "let candidateBaseThickness = 0.6;",
    "function freshDesignForCurrentFolder() { calls.push('fresh'); return { box: { base_thickness: candidateBaseThickness } }; }",
    "let loadedOverride = null; async function loadFreshOrdinaryDesignForCurrentFolder(overrideBox) { calls.push('load'); loadedOverride = overrideBox; }",
    # state.design is the CURRENTLY OPEN bin, with its own (different) Base
    # thickness, so a regression that reads it instead of the candidate is caught.
    "const state = { catalog: { base_unit: 8, max_box_size: 350, min_height_above_base_mm: 5 }, design: { box: { base_thickness: 99 } }, activeSpace: null, designInventoryId: 'B3', surfaceHeightPromptSkipped: true };",
    function_source("normalizeBinDimension"),
    function_source("insideBinFitForStorageBox"),
    function_source("designerMakeInsideBin"),
])


def run_designer(space, candidate_base_thickness=0.6, **overrides):
    setup = "\n".join(f"{key} = {json.dumps(value)};" for key, value in overrides.items())
    out = node_run(DESIGNER_PRELUDE + js("""
state.activeSpace = __SPACE__;
candidateBaseThickness = __CANDIDATE_BASE__;
""" + setup + """
designerMakeInsideBin().then(() => {
  process.stdout.write(JSON.stringify({
    calls, toasts, loadedOverride,
    designInventoryId: state.designInventoryId,
    surfaceHeightPromptSkipped: state.surfaceHeightPromptSkipped,
  }));
});
""", SPACE=space, CANDIDATE_BASE=candidate_base_thickness))
    return out


class DesignerMakeInsideBinTests(unittest.TestCase):
    def test_pending_autosave_flush_failure_cancels_without_touching_design(self):
        out = run_designer({"x": 80, "y": 80, "z": 42}, flushResult=False)
        self.assertEqual(out["calls"], ["guard", "flush"])
        self.assertIsNone(out["loadedOverride"])

    def test_too_small_space_cancels_before_any_mutation(self):
        out = run_designer({"x": 4, "y": 80, "z": 42})
        self.assertEqual(out["calls"], ["guard", "flush", "fresh"])
        self.assertTrue(out["toasts"][0][1])  # error flag
        self.assertIsNone(out["loadedOverride"])

    def test_success_overrides_only_box_dimensions_and_resets_identity(self):
        out = run_designer({"x": 81, "y": 97, "z": 42})
        self.assertEqual(out["calls"], ["guard", "flush", "fresh", "begin", "load", "finish"])
        self.assertEqual(out["loadedOverride"], {"x": 80, "y": 96, "z": 42})
        self.assertIsNone(out["designInventoryId"])
        self.assertFalse(out["surfaceHeightPromptSkipped"])
        self.assertEqual(out["toasts"][-1][0], "Started an inside bin.")

    def test_begin_mutation_busy_guard_cancels_before_loading(self):
        out = run_designer({"x": 80, "y": 80, "z": 42}, mutationResult=False)
        self.assertEqual(out["calls"], ["guard", "flush", "fresh", "begin"])
        self.assertIsNone(out["loadedOverride"])

    def test_z_validation_uses_the_fresh_candidates_base_not_the_open_bins(self):
        # Fix 064 Correction 1 regression: state.design.box.base_thickness is
        # 99 in this harness (a value that would reject nearly everything),
        # so a pass here proves the fit used the fresh candidate's Base (10),
        # not the currently open bin's.
        out = run_designer({"x": 80, "y": 80, "z": 15}, candidate_base_thickness=10)
        self.assertEqual(out["calls"], ["guard", "flush", "fresh", "begin", "load", "finish"])
        self.assertEqual(out["loadedOverride"], {"x": 80, "y": 80, "z": 15})

    def test_z_validation_rejects_using_the_fresh_candidates_base(self):
        out = run_designer({"x": 80, "y": 80, "z": 12}, candidate_base_thickness=10)
        self.assertEqual(out["calls"], ["guard", "flush", "fresh"])
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
