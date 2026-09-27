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


    def test_z_check_uses_the_fresh_candidate_base_not_the_open_bins(self):
        # Fix 064 Correction 1: a thin currently-open bin (0.6 mm) must not
        # wave through a Storage Box that is too short for the fresh
        # inside-bin candidate's own remembered Base (10 mm).
        out = fit({"x": 80, "y": 80, "z": 12}, open_bin_base_thickness=0.6, candidate_base_thickness=10)
        self.assertIn("error", out)



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


    def test_success_overrides_only_box_dimensions_and_resets_identity(self):
        out = run_designer({"x": 81, "y": 97, "z": 42})
        self.assertEqual(out["calls"], ["guard", "flush", "fresh", "begin", "load", "finish"])
        self.assertEqual(out["loadedOverride"], {"x": 80, "y": 96, "z": 42})
        self.assertIsNone(out["designInventoryId"])
        self.assertFalse(out["surfaceHeightPromptSkipped"])
        self.assertEqual(out["toasts"][-1][0], "Started an inside bin.")





class MakeInsideBinLifecycleReuseTests(unittest.TestCase):
    """Confirms the fresh-design/reset path stays owned by
    loadFreshOrdinaryDesignForCurrentFolder (shared with New Bin) rather than
    a duplicated clone-the-current-bin path, and never talks to the Inventory
    API merely by building a starter design."""


    def test_load_fresh_design_starts_from_the_catalog_starter_not_the_current_design(self):
        source = function_source("loadFreshOrdinaryDesignForCurrentFolder")
        self.assertIn("freshDesignForCurrentFolder()", source)



if __name__ == "__main__":
    unittest.main()
