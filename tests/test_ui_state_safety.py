"""Focused, non-browser checks for Fix 071B state and preview transport."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from dataclasses import replace
from organizer_engine import BoxSpec, SideOpeningSpec, StackSpec, SIDE_OPENING_WIDTHS
from organizer_features.side_openings import (
    SIDE_OPENING_CORNER_MARGIN_MM, side_opening_allowed_sizes, validate_side_openings,
)
from space_source import app_source, spaces_source
from tests.test_space_preferences import function_source
from tests.test_wavefinity_web import _fix21_photo_design
from wavefinity_web import default_design, default_feature_payload, duplicate_feature_payload, preview_payload


ROOT = Path(__file__).resolve().parent.parent
APP = app_source(ROOT / "web")
PANEL = (ROOT / "web" / "drawer-panel.js").read_text(encoding="utf-8")


def node_json(source: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required")
    result = subprocess.run([node, "-e", source], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class BrowserStateLogicTests(unittest.TestCase):
    def test_undo_redo_removed_everywhere(self):
        # Fix 1137: no undo/redo anywhere - the designer history and the
        # Space-layout history are both gone, with their buttons, shortcuts,
        # history options and sync plumbing.
        for dead in ("designerHistory", "designerFuture",
                     "designerHistoryRestoring", "designerHistorySnapshot(",
                     "clearDesignerHistory(", "updateDesignerHistoryButtons(",
                     "noteCommittedDesignChange(", "restoreDesignerHistory(",
                     "designerUndo", "designerRedo", "pendingDesignHistory",
                     "#designer-undo", "#designer-redo",
                     "#designer-history-actions", "designer-history-actions"):
            self.assertNotIn(dead, APP)
        # Every app module is scanned individually - no undo/redo remnant can
        # hide in another web/app/*.js file. The scan set must explicitly
        # include 01-runtime-state.js and 02-lifecycle-ai-help.js.
        app_files = sorted((ROOT / "web" / "app").glob("*.js"))
        app_names = {one.name for one in app_files}
        self.assertIn("01-runtime-state.js", app_names)
        self.assertIn("02-lifecycle-ai-help.js", app_names)
        space_dead = ("DL.history", "DL.future", "DL.restore", "DL.undo",
                      "DL.redo", "DP.syncHistory", "#undo-design",
                      "#redo-design", "{ history:", "history: false")
        for one in app_files:
            text = one.read_text(encoding="utf-8")
            for dead in space_dead:
                with self.subTest(file=one.name, dead=dead):
                    self.assertNotIn(dead, text)
        spaces = spaces_source(ROOT / "web")
        panel = (ROOT / "web" / "drawer-panel.js").read_text(encoding="utf-8")
        model = (ROOT / "web" / "drawer-model.js").read_text(encoding="utf-8")
        view = (ROOT / "web" / "drawer-view.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for dead in space_dead:
            self.assertNotIn(dead, spaces)
            self.assertNotIn(dead, panel)
            self.assertNotIn(dead, model)
            self.assertNotIn(dead, view)
        for dead in ("#undo-design", "#redo-design", "#designer-undo",
                     "#designer-redo", "designer-history-actions"):
            self.assertNotIn(dead, html)
        # The one surviving pre-edit snapshot is the modifier-conflict
        # guard's, not undo history.
        self.assertIn("pendingPreEditDesign", APP)

    def test_delete_confirm_cannot_be_skipped(self):
        # Fix 1137 round 2 (GPT G2M-0451 HOLD): the Delete confirmation lives
        # at the #active-option-delete click choke point in
        # 06-form-sync-controls.js, ahead of all three dispatch branches
        # (dataset.kind -> removeModifier, dataset.index -> deleteSupportAt,
        # no-dataset -> deleteCurrentPart). This executes the REAL handler
        # from the file with a mocked confirm and proves no branch can delete
        # without the user confirming.
        source = (ROOT / "web" / "app" / "06-form-sync-controls.js").read_text(encoding="utf-8")
        anchor = '"#active-option-delete")?.addEventListener("click", '
        self.assertEqual(source.count(anchor), 1,
                         "the delete choke point must be wired exactly once")
        start = source.index(anchor) + len(anchor)
        end = source.index("\n  });", start) + 4  # keep the arrow function closing brace
        handler_src = source[start:end].strip()
        self.assertIn("confirm(", handler_src)
        script = r"""
const calls = [];
const confirmMessages = [];
let confirmResult = true;
const titleEl = { textContent: "Wall Divider" };
const $ = (sel) => sel === "#active-option-title" ? titleEl : null;
const state = { draft: null };
const confirm = (msg) => { confirmMessages.push(msg); return confirmResult; };
const removeModifier = async (kind) => { calls.push("removeModifier:" + kind); };
const deleteSupportAt = async (index) => { calls.push("deleteSupportAt:" + index); };
const deleteCurrentPart = async () => { calls.push("deleteCurrentPart"); };
const handler = __HANDLER__;
(async () => {
  const out = {};
  const cases = [
    ["kind", { kind: "wall_opening" }, "removeModifier:wall_opening"],
    ["index", { index: "3" }, "deleteSupportAt:3"],
    ["no-dataset", {}, "deleteCurrentPart"],
  ];
  for (const [name, dataset, expected] of cases) {
    for (const accepted of [false, true]) {
      calls.length = 0;
      confirmMessages.length = 0;
      confirmResult = accepted;
      await handler({ currentTarget: { dataset } });
      const tag = name + (accepted ? "_accepted" : "_cancelled");
      out[tag + "_calls"] = calls.slice();
      out[tag + "_confirms"] = confirmMessages.slice();
    }
  }
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__HANDLER__", "(" + handler_src + ")")
        data = node_json(script)
        for branch, expected in (("kind", "removeModifier:wall_opening"),
                                 ("index", "deleteSupportAt:3"),
                                 ("no-dataset", "deleteCurrentPart")):
            # The prompt fires exactly once per click, naming the item...
            self.assertEqual(len(data[branch + "_cancelled_confirms"]), 1, branch)
            self.assertIn("Wall Divider", data[branch + "_cancelled_confirms"][0], branch)
            self.assertIn("cannot be undone", data[branch + "_cancelled_confirms"][0], branch)
            # ...and cancelling dispatches NOTHING on any branch.
            self.assertEqual(data[branch + "_cancelled_calls"], [], branch)
            # Accepting dispatches exactly the right branch, once.
            self.assertEqual(len(data[branch + "_accepted_confirms"]), 1, branch)
            self.assertEqual(data[branch + "_accepted_calls"], [expected], branch)

    def test_starter_preview_flag_clears_only_on_real_change(self):
        # Fix 1137 round 3 (GPT G2M-0452 DISPUTE): Change A8b restores the
        # spaceStarterPreviewPending clearing on a real pre-preview design
        # change inside the debounced commit in 06-form-sync-controls.js.
        # This executes the REAL debounced commit path plus the REAL
        # first-preview persistence branch from 11-parts-preview-requests.js
        # and proves: (1) a same-design commit keeps the flag pending,
        # (2) a real pre-preview edit clears it, (3) that edit survives
        # first-preview persistence - the autosave is queued and cleanDesign
        # is NOT re-snapshotted over the edit. The converse is asserted too:
        # with the flag still pending, the first preview re-snapshots the
        # baseline and queues no autosave - the panel's data-loss path.
        controls = (ROOT / "web" / "app" / "06-form-sync-controls.js").read_text(encoding="utf-8")
        start = controls.index("let pendingPreEditDesign = null;")
        end = controls.index("}, 280);", start) + len("}, 280);")
        commit_block = controls[start:end]
        self.assertIn("state.spaceStarterPreviewPending = false;", commit_block,
                      "Change A8b guard must be present in the debounced commit")
        ch_start = controls.index("function changedDesign(previousDesign = null) {")
        ch_end = controls.index("\n}", ch_start) + len("\n}")
        changed_fn = controls[ch_start:ch_end]
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const debounce = (fn) => fn;  // the debounced commit runs synchronously here
const state = {
  design: { box: { x: 16, y: 16, z: 60, wall: 2 }, layout: { features: [] } },
  cleanDesign: null,
  spaceStarterPreviewPending: true,
  designMutationBusy: false,
  canGenerate: true,
  draft: null,
  binResizePending: false,
  binFootprintResizePending: false,
};
const applyLiveFormWithModifierConflictGuard = () => true;
const maybeWarnSpaceWallMismatch = () => {};
const reflowDraftToBin = () => {};
const refreshDraft = () => {};
const refreshPreview = () => {};
const enforceBinMinimumSoon = () => {};
const noteLidThicknessEdit = () => {};
const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
__COMMIT_BLOCK__
__CHANGED_FN__
const out = {};
// 1. A same-design commit keeps the starter-preview flag pending.
applyChangedDesign();
out.sameDesignKeepsPending = state.spaceStarterPreviewPending === true;
// 2. A real pre-preview edit clears the flag.
state.spaceStarterPreviewPending = true;
const pristineStarter = clone(state.design);
state.cleanDesign = clone(state.design);  // loadFreshOrdinaryDesignForCurrentFolder baseline
const preEdit = clone(state.design);
state.design.box.x = 24;  // the user edits the size before the first preview
changedDesign(preEdit);   // pre-edit snapshot, then the debounced commit lands
out.realEditClears = state.spaceStarterPreviewPending === false;
// 3. The edit survives first-preview persistence: flag cleared, so the
// first preview queues an autosave instead of re-snapshotting the baseline.
__FIRST_PREVIEW_BRANCH__
out.editPersisted = autosaves.length === 1 && autosaves[0].box.x === 24;
out.baselineUntouched = state.cleanDesign.box.x === 16;
// Converse - the data-loss path: flag still pending at first preview
// re-snapshots the edited design as the baseline and queues no autosave.
state.spaceStarterPreviewPending = true;
state.cleanDesign = clone(pristineStarter);
autosaves.length = 0;
__FIRST_PREVIEW_BRANCH__
out.staleFlagLosesEdit = state.cleanDesign.box.x === 24 && autosaves.length === 0;
process.stdout.write(JSON.stringify(out));
""".replace("__COMMIT_BLOCK__", commit_block)
        script = script.replace("__CHANGED_FN__", changed_fn)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["sameDesignKeepsPending"],
                        "a same-design commit must keep the starter-preview flag pending")
        self.assertTrue(data["realEditClears"],
                        "a real pre-preview edit must clear the starter-preview flag")
        self.assertTrue(data["editPersisted"],
                        "the real edit must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the edited design")
        self.assertTrue(data["staleFlagLosesEdit"],
                        "flag still pending at first preview is the data-loss path "
                        "(baseline overwritten, no autosave)")

    def test_starter_preview_flag_clears_on_mode_switch(self):
        # Fix 1137 round 4 (GPT ruling, Issue #11 comment 6128748893): the
        # #mode-select handler in 03-history-utils-catalog.js commits the
        # converted design directly - it never passes through the A8b
        # debounced commit - so Change A7b clears the starter-preview flag
        # in the handler itself, after state.design is replaced and before
        # refreshPreview() can adopt the preview. This executes the REAL
        # change handler extracted from the file, wired to the REAL
        # commitVisibleDraft from 10-draft-update-commit.js (with no draft
        # open it returns without committing, exactly as in the app).
        commit_src = (ROOT / "web" / "app" / "10-draft-update-commit.js").read_text(encoding="utf-8")
        cvd_start = commit_src.index("async function commitVisibleDraft(")
        cvd_end = commit_src.index("\n// True when the open draft holds work", cvd_start)
        commit_fn = commit_src[cvd_start:cvd_end].strip()
        catalog = (ROOT / "web" / "app" / "03-history-utils-catalog.js").read_text(encoding="utf-8")
        anchor = 'modes.addEventListener("change", '
        self.assertEqual(catalog.count(anchor), 1,
                         "the mode-select handler must be wired exactly once")
        start = catalog.index(anchor) + len(anchor)
        end = catalog.index("\n  });", start) + 4  # keep the arrow function closing brace
        handler_src = catalog[start:end].strip()
        self.assertIn("state.spaceStarterPreviewPending = false;", handler_src,
                      "Change A7b must clear the starter-preview flag in the handler")
        self.assertLess(handler_src.index("state.design = result.design;"),
                        handler_src.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the converted design lands")
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const INSIDE_HANDLES_REMOVABLE_MESSAGE = "stub";
const state = {
  design: { box: { x: 16 }, layout: { mode: "fused", features: [] } },
  cleanDesign: null,
  selected: null,
  draft: null,
  draftRequest: 0,
  referenceEditPending: false,
  spaceStarterPreviewPending: true,
};
const modes = { value: "fused" };
const insideHandlesActive = () => false;
const beginDesignMutation = () => true;
const finishDesignMutation = () => {};
const isBlankTextDraft = () => false;
const draftCommitIndex = () => 0;
const allowSmallTextEdit = async () => {};
const invalidatePendingPreview = () => {};
const seedPartNameFromText = () => {};
const typedSpaceOrdinaryBin = () => false;
const renderDraftFields = () => {};
const renderPlaced = () => {};
const updateSelectionButtons = () => {};
__COMMIT_FN__
const api = async (url, payload) => {
  if (url !== "/api/layout/mode") throw new Error("unexpected api " + url);
  const converted = clone(payload.design);
  converted.layout.mode = payload.mode;
  converted.convertedByModeApi = true;
  return { design: converted };
};
const syncForm = () => {};
const selectedFeature = async () => true;
const clearDraftSelection = () => {};
const refreshPreview = () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
const toast = () => {};
const handler = __HANDLER__;
(async () => {
  const out = {};
  // Re-selecting the current mode returns before any commit: the flag
  // stays pending - the clear fires only on a real change.
  modes.value = "fused";
  await handler();
  out.sameModeKeepsPending = state.spaceStarterPreviewPending === true;
  // A real switch commits the converted design and clears the flag
  // BEFORE refreshPreview() can adopt the preview.
  state.cleanDesign = clone(state.design);
  modes.value = "separate";
  await handler();
  out.switchClears = state.spaceStarterPreviewPending === false;
  out.designConverted = state.design.layout.mode === "separate"
    && state.design.convertedByModeApi === true;
  out.refreshSawClearedFlag = refreshSawPending.length > 0
    && refreshSawPending.every((v) => v === false);
  // The edit survives first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1 && autosaves[0].layout.mode === "separate";
  out.baselineUntouched = state.cleanDesign.layout.mode === "fused";
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__HANDLER__", "(" + handler_src + ")")
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        script = script.replace("__COMMIT_FN__", commit_fn)
        data = node_json(script)
        self.assertTrue(data["sameModeKeepsPending"],
                        "re-selecting the current mode must keep the starter-preview flag pending")
        self.assertTrue(data["switchClears"],
                        "a real mode switch must clear the starter-preview flag")
        self.assertTrue(data["designConverted"],
                        "the handler must commit the converted design")
        self.assertTrue(data["refreshSawClearedFlag"],
                        "refreshPreview must run only after the flag is cleared")
        self.assertTrue(data["editPersisted"],
                        "the mode switch must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the converted design")

    def test_starter_preview_flag_clears_on_modifier_add(self):
        # Fix 1137 round 4 (GPT ruling, Issue #11 comment 6128748893): the
        # addModifier palette action in 07-kind-pickers-bore-math.js commits
        # a new modifier directly and calls refreshPreview() itself, so
        # Changes A21 (edge-mount branch) and A22 (generic branch) clear the
        # starter-preview flag at the commit point. This executes the REAL
        # addModifier for both branches - through the REAL draft-switch
        # guard machinery from 10-draft-update-commit.js, not a pass-through
        # stub - plus both refusal paths (Inside Grip in the wrong mode, and
        # Side Openings with no eligible wall): no mutation committed -> the
        # flag must stay pending.
        kinds = (ROOT / "web" / "app" / "07-kind-pickers-bore-math.js").read_text(encoding="utf-8")
        start = kinds.index("async function addModifier(kind) {")
        end = kinds.index("\nasync function removeModifier", start)
        add_src = kinds[start:end].strip()
        self.assertEqual(add_src.count("state.spaceStarterPreviewPending = false;"), 2,
                         "Changes A21 and A22 must each clear the starter-preview flag")
        clear_lit = "state.spaceStarterPreviewPending = false;"
        first_clear = add_src.index(clear_lit)
        second_clear = add_src.index(clear_lit, first_clear + 1)
        self.assertLess(add_src.index("state.design.box.edge_mount = {"), first_clear,
                        "the A21 clear must come after the Edge Mount assignment")
        self.assertLess(first_clear, add_src.index("await refreshPreview();"),
                        "the A21 clear must land before the edge-mount branch's refreshPreview()")
        self.assertLess(add_src.index("clampSideOpeningTopForLid(state.design, true);"), second_clear,
                        "the A22 clear must come after the generic branch chain's mutations")
        self.assertLess(second_clear, add_src.index("refreshPreview();", second_clear),
                        "the A22 clear must land before the generic branch's refreshPreview()")
        commit_src = (ROOT / "web" / "app" / "10-draft-update-commit.js").read_text(encoding="utf-8")
        cvd_start = commit_src.index("async function commitVisibleDraft(")
        cvd_end = commit_src.index("\n// True when the open draft holds work", cvd_start)
        commit_fn = commit_src[cvd_start:cvd_end].strip()
        dns_start = commit_src.index("function draftNeedsSaving() {")
        dns_end = commit_src.index('\n// Gate every "switch to a different interior part" path', dns_start)
        needs_fn = commit_src[dns_start:dns_end].strip()
        gds_start = commit_src.index("async function guardDraftSwitch(")
        gds_end = commit_src.index("\n// A transition owns the preview after saving the old draft", gds_start)
        guard_fn = commit_src[gds_start:gds_end].strip()
        dds_start = commit_src.index("async function deferredDraftSwitch() {")
        dds_end = commit_src.index("\nasync function withDeferredDraftSwitch", dds_start)
        deferred_fn = commit_src[dds_start:dds_end].strip()
        wds_start = commit_src.index("async function withDeferredDraftSwitch(")
        wds_end = commit_src.index('\n// The "discard this change?" dialog', wds_start)
        with_fn = commit_src[wds_start:wds_end].strip()
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const number = (v, fallback) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};
const EDGE_MOUNT_DEFAULTS = { label_type: "none" };
const SIDE_OPENING_DEFAULTS = { enabled: false, sides: [] };
const SIDE_OPENING_SIDE_IDS = ["left", "right"];
const B4B_PARTS_ONLY_DIVIDER_MESSAGE = "stub";
const INSIDE_HANDLES_REMOVABLE_MESSAGE = "stub";
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { mode: "separate", features: [] } },
  cleanDesign: null,
  catalog: { edge_mount: { max_projection_mm: 200, min_projection_mm: 5 } },
  draft: null,
  draftTouched: false,
  draftRequest: 0,
  draftAutoCommit: false,
  referenceEditPending: false,
  selected: null,
  spaceStarterPreviewPending: true,
};
const b4bEnabled = () => false;
let fullPreviewStarts = 0;
const isBlankTextDraft = () => false;
const draftCommitIndex = () => 0;
const allowSmallTextEdit = async () => {};
const invalidatePendingPreview = () => {};
const seedPartNameFromText = () => {};
const typedSpaceOrdinaryBin = () => false;
const renderDraftFields = () => {};
const updateSelectionButtons = () => {};
const promptDraftConflict = async () => false;
__NEEDS_FN__
__COMMIT_FN__
__GUARD_FN__
__DEFERRED_FN__
__WITH_FN__
const spaceModifierDefaults = () => ({});
let eligibleSideIds = ["left", "right"];
const sideOpeningEligibleSide = (side) => eligibleSideIds.includes(side);
const clampSideOpeningTopForLid = () => {};
const syncForm = () => {};
const openModifier = async () => {};
const refreshPreview = () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
const toast = () => {};
__ADD_MODIFIER__
(async () => {
  const out = {};
  // Refusal path: Inside Grip requires Fused mode - no mutation is
  // committed, so the flag must stay pending.
  await addModifier("inside_handles");
  out.refusalKeepsPending = state.spaceStarterPreviewPending === true;
  // Refusal path 2: Side Openings with no eligible wall - the generic
  // branch chain refuses before any mutation commits, so the flag must
  // stay pending (this leg fails if the A22 clear moves above the chain).
  eligibleSideIds = [];
  await addModifier("side_openings");
  out.noWallKeepsPending = state.spaceStarterPreviewPending === true;
  out.noWallNoCommit = !("side_openings" in state.design.box);
  eligibleSideIds = ["left", "right"];
  state.design.layout.mode = "fused";
  // A21: the edge-mount branch commits a new Edge Mount and clears the
  // flag before openModifier/refreshPreview run.
  state.cleanDesign = clone(state.design);
  refreshSawPending.length = 0;
  await addModifier("edge_mount");
  out.edgeMountClears = state.spaceStarterPreviewPending === false;
  out.edgeMountCommitted = Boolean(state.design.box.edge_mount);
  out.edgeMountRefreshSawCleared = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  // A22: the generic branch (Side Openings) commits and clears the same
  // way, before its own refreshPreview().
  state.spaceStarterPreviewPending = true;
  refreshSawPending.length = 0;
  await addModifier("side_openings");
  out.sideOpeningsClears = state.spaceStarterPreviewPending === false;
  out.sideOpeningsCommitted = state.design.box.side_openings?.enabled === true;
  out.refreshSawClearedFlag = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  // The edits survive first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1
    && autosaves[0].box.side_openings.enabled === true;
  out.baselineUntouched = !("side_openings" in state.cleanDesign.box)
    && !("edge_mount" in state.cleanDesign.box);
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__ADD_MODIFIER__", add_src)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        script = script.replace("__NEEDS_FN__", needs_fn)
        script = script.replace("__COMMIT_FN__", commit_fn)
        script = script.replace("__GUARD_FN__", guard_fn)
        script = script.replace("__DEFERRED_FN__", deferred_fn)
        script = script.replace("__WITH_FN__", with_fn)
        data = node_json(script)
        self.assertTrue(data["refusalKeepsPending"],
                        "a refused modifier add must keep the starter-preview flag pending")
        self.assertTrue(data["noWallKeepsPending"],
                        "a no-eligible-wall Side Openings refusal must keep the starter-preview flag pending")
        self.assertTrue(data["noWallNoCommit"],
                        "a no-eligible-wall Side Openings refusal must not commit the modifier")
        self.assertTrue(data["edgeMountClears"],
                        "the edge-mount add (A21) must clear the starter-preview flag")
        self.assertTrue(data["edgeMountCommitted"],
                        "the edge-mount add must commit the new Edge Mount")
        self.assertTrue(data["edgeMountRefreshSawCleared"],
                        "refreshPreview must run only after the A21 clear (moving the clear "
                        "below await refreshPreview() must fail this test)")
        self.assertTrue(data["sideOpeningsClears"],
                        "the generic modifier add (A22) must clear the starter-preview flag")
        self.assertTrue(data["sideOpeningsCommitted"],
                        "the generic modifier add must commit the modifier")
        self.assertTrue(data["refreshSawClearedFlag"],
                        "refreshPreview must run only after the flag is cleared")
        self.assertTrue(data["editPersisted"],
                        "the modifier add must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the edited design")

    def test_starter_preview_flag_clears_on_kind_apply_and_grow(self):
        # Fix 1137 round 4 (GPT ruling, Issue #11 comment 6128748893): the
        # kind/grow flows in 07-kind-pickers-bore-math.js commit directly -
        # growBinForNewCradle adopts the expanded design (Change A26) and
        # selectKind's apply step commits the applied design (Change A27) -
        # so both clear the starter-preview flag at their commit points.
        # This executes the REAL growBinForNewCradle and the REAL selectKind
        # apply fragment; a blocked grow commits nothing and must leave the
        # flag pending.
        kinds = (ROOT / "web" / "app" / "07-kind-pickers-bore-math.js").read_text(encoding="utf-8")
        grow_start = kinds.index("async function growBinForNewCradle(request) {")
        grow_end = kinds.index("\nasync function selectKind", grow_start)
        grow_src = kinds[grow_start:grow_end].strip()
        self.assertEqual(grow_src.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A26 must clear the starter-preview flag exactly once")
        self.assertLess(grow_src.index("state.design = trial.design;"),
                        grow_src.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the expanded design is adopted")
        sel_start = kinds.index("async function selectKind(kind, reset = false) {")
        self.assertEqual(kinds.count("state.design = applyResult.design;"), 1,
                         "the selectKind apply step must be anchored exactly once")
        frag_start = kinds.index("state.design = applyResult.design;", sel_start)
        frag_end = (kinds.index("state.selected = applyResult.selected;", frag_start)
                    + len("state.selected = applyResult.selected;"))
        apply_fragment = kinds[frag_start:frag_end]
        self.assertEqual(apply_fragment.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A27 must clear the starter-preview flag exactly once in the apply step")
        self.assertLess(apply_fragment.index("state.design = applyResult.design;"),
                        apply_fragment.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the applied design lands")
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { features: [] } },
  cleanDesign: null,
  draft: { kind: "cradle", options: {} },
  kindRequest: 1,
  designInventoryId: "inv-1",
  activeSpace: "space-1",
  selected: null,
  spaceStarterPreviewPending: true,
};
let violation = null;
const sizeCradleToItem = () => {};
const api = async (url) => {
  if (url !== "/api/layout/expand") throw new Error("unexpected api " + url);
  const grown = clone(state.design);
  grown.box = { ...grown.box, x: 120 };
  grown.layout = { ...grown.layout, features: [...grown.layout.features, clone(state.draft)] };
  return { design: grown, box: grown.box };
};
const aiSpaceViolation = () => violation;
const $ = () => ({ textContent: "", classList: { add() {}, remove() {} } });
const renderDraftFields = () => {};
const renderPlaced = () => {};
const updateSelectionButtons = () => {};
const syncForm = () => {};
const flashField = () => {};
const fmt = (v) => String(v);
const toast = () => {};
const friendlyError = (e) => String((e && e.message) || e);
__GROW_FN__
(async () => {
  const out = {};
  // Blocked grow: the Space rules reject the trial design, nothing is
  // committed, and the flag stays pending.
  violation = "too big";
  const blocked = await growBinForNewCradle(state.kindRequest);
  out.blockedKeepsPending = blocked === "blocked" && state.spaceStarterPreviewPending === true;
  out.blockedKeepsDesign = state.design.box.x === 100;
  // Adopted grow: the expanded design lands and the flag clears.
  violation = null;
  state.cleanDesign = clone(state.design);
  const adopted = await growBinForNewCradle(state.kindRequest);
  out.growAdopted = adopted === "adopted";
  out.growClears = state.spaceStarterPreviewPending === false;
  out.growCommitted = state.design.box.x === 120 && state.design.layout.features.length === 1;
  // A27: the selectKind apply fragment commits the applied design and
  // clears the flag the same way.
  state.spaceStarterPreviewPending = true;
  const applyResult = {
    design: { box: { x: 120, y: 80, z: 60 }, layout: { features: [{ kind: "cradle" }] }, appliedMarker: true },
    selected: 0,
  };
  const seedPartNameFromText = () => {};
  __APPLY_FRAGMENT__
  out.applyClears = state.spaceStarterPreviewPending === false;
  out.applyCommitted = state.design.appliedMarker === true && state.selected === 0;
  // The edit survives first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1 && autosaves[0].appliedMarker === true;
  out.baselineUntouched = state.cleanDesign.box.x === 100;
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__GROW_FN__", grow_src)
        script = script.replace("__APPLY_FRAGMENT__", apply_fragment)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["blockedKeepsPending"],
                        "a blocked grow must keep the starter-preview flag pending")
        self.assertTrue(data["blockedKeepsDesign"],
                        "a blocked grow must not commit the trial design")
        self.assertTrue(data["growAdopted"],
                        "the grow must adopt the expanded design")
        self.assertTrue(data["growClears"],
                        "an adopted grow (A26) must clear the starter-preview flag")
        self.assertTrue(data["growCommitted"],
                        "the grow must commit the expanded design with the new feature")
        self.assertTrue(data["applyClears"],
                        "the selectKind apply step (A27) must clear the starter-preview flag")
        self.assertTrue(data["applyCommitted"],
                        "the selectKind apply step must commit the applied design")
        self.assertTrue(data["editPersisted"],
                        "the applied edit must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the edited design")
    def test_starter_preview_flag_clears_on_draft_commit_paths(self):
        # Fix 1137 round 4 revision (panel Tracer + Breaker HOLD): Change
        # A17b is a sixth site in the same invariant - commitVisibleDraft in
        # 10-draft-update-commit.js commits a pending draft directly, and
        # pre-fix its own noteCommittedDesignChange cleared the flag at the
        # commit point. Two paths reach a preview refresh through it with
        # the flag still pending if the clear is missing: (1) the A7b catch
        # path - the #mode-select handler commits a pending draft, the mode
        # API throws, and the catch fires refreshPreview(); (2) the
        # draft-switch guard's finish() - deferredDraftSwitch commits a
        # pending draft, downstream exits early without reaching the
        # A22/A27 clears, and finish() fires refreshPreview(). This executes
        # the REAL commitVisibleDraft, draftNeedsSaving, guardDraftSwitch
        # and deferredDraftSwitch, plus the REAL #mode-select handler for
        # the catch path.
        commit_src = (ROOT / "web" / "app" / "10-draft-update-commit.js").read_text(encoding="utf-8")
        cvd_start = commit_src.index("async function commitVisibleDraft(")
        cvd_end = commit_src.index("\n// True when the open draft holds work", cvd_start)
        commit_fn = commit_src[cvd_start:cvd_end].strip()
        self.assertEqual(commit_fn.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A17b must clear the starter-preview flag exactly once in commitVisibleDraft")
        self.assertIn("if (previousDesign && JSON.stringify(previousDesign) !== JSON.stringify(state.design)) {",
                      commit_fn,
                      "Change A17b's clear must keep the A8b real-change guard")
        self.assertLess(commit_fn.index("state.design = committed.design;"),
                        commit_fn.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the committed design lands")
        self.assertLess(commit_fn.index("state.spaceStarterPreviewPending = false;"),
                        commit_fn.index("state.draftIsNew = false;"),
                        "the flag must clear at the commit point, not after the commit epilogue")
        dns_start = commit_src.index("function draftNeedsSaving() {")
        dns_end = commit_src.index('\n// Gate every "switch to a different interior part" path', dns_start)
        needs_fn = commit_src[dns_start:dns_end].strip()
        gds_start = commit_src.index("async function guardDraftSwitch(")
        gds_end = commit_src.index("\n// A transition owns the preview after saving the old draft", gds_start)
        guard_fn = commit_src[gds_start:gds_end].strip()
        dds_start = commit_src.index("async function deferredDraftSwitch() {")
        dds_end = commit_src.index("\nasync function withDeferredDraftSwitch", dds_start)
        deferred_fn = commit_src[dds_start:dds_end].strip()
        catalog = (ROOT / "web" / "app" / "03-history-utils-catalog.js").read_text(encoding="utf-8")
        anchor = 'modes.addEventListener("change", '
        self.assertEqual(catalog.count(anchor), 1,
                         "the mode-select handler must be wired exactly once")
        h_start = catalog.index(anchor) + len(anchor)
        h_end = catalog.index("\n  });", h_start) + 4
        handler_src = catalog[h_start:h_end].strip()
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const INSIDE_HANDLES_REMOVABLE_MESSAGE = "stub";
let fullPreviewStarts = 0;
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused", features: [{ kind: "cradle", options: { w: 10 } }] } },
  cleanDesign: null,
  draft: null,
  draftIsNew: true,
  draftTouched: true,
  draftRequest: 0,
  draftSourceIndex: 0,
  draftResolvedOptions: {},
  selected: null,
  referenceEditPending: false,
  smallTextApprovedDraftRequest: 0,
  spaceStarterPreviewPending: true,
};
const modes = { value: "fused" };
const isBlankTextDraft = () => false;
const draftCommitIndex = () => 0;
const allowSmallTextEdit = async () => {};
const invalidatePendingPreview = () => {};
const seedPartNameFromText = () => {};
const typedSpaceOrdinaryBin = () => false;
const renderDraftFields = () => {};
const renderPlaced = () => {};
const updateSelectionButtons = () => {};
const syncForm = () => {};
const promptDraftConflict = async () => false;
const insideHandlesActive = () => false;
const beginDesignMutation = () => true;
const finishDesignMutation = () => {};
const selectedFeature = async () => true;
const clearDraftSelection = () => {};
const toast = () => {};
const refreshPreview = () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
let modeApiThrows = false;
const api = async (url, payload) => {
  if (url === "/api/feature/apply") {
    const applied = clone(state.design);
    applied.layout.features[0] = clone(payload.feature);
    return { design: applied, selected: 0, warnings: [] };
  }
  if (url === "/api/layout/mode") {
    if (modeApiThrows) throw new Error("mode api failed");
    const converted = clone(payload.design);
    converted.layout.mode = payload.mode;
    converted.convertedByModeApi = true;
    return { design: converted };
  }
  throw new Error("unexpected api " + url);
};
__NEEDS_FN__
__COMMIT_FN__
__GUARD_FN__
__DEFERRED_FN__
const handler = __HANDLER__;
(async () => {
  const out = {};
  const changedDraft = (w) => ({ kind: "cradle", options: { w } });
  // 1. Direct commit: a real pending change commits and A17b clears.
  state.draft = changedDraft(20);
  const direct = await commitVisibleDraft({ previewAfterCommit: false });
  out.directCommits = direct === true;
  out.directClears = state.spaceStarterPreviewPending === false;
  out.directApplied = state.design.layout.features[0].options.w === 20;
  // 2. No-change commit: the draft matches the saved feature, nothing
  // commits, and the flag stays pending.
  state.spaceStarterPreviewPending = true;
  state.draft = clone(state.design.layout.features[0]);
  const noop = await commitVisibleDraft({ previewAfterCommit: false });
  out.noopReturnsFalse = noop === false;
  out.noopKeepsPending = state.spaceStarterPreviewPending === true;
  // 3. A7b catch path: the handler commits a pending draft, the mode API
  // throws, and the catch's refreshPreview() must see the cleared flag.
  state.draft = changedDraft(30);
  modeApiThrows = true;
  refreshSawPending.length = 0;
  modes.value = "separate";
  await handler();
  out.catchCommittedDraft = state.design.layout.features[0].options.w === 30;
  out.catchNotConverted = state.design.convertedByModeApi !== true
    && state.design.layout.mode === "fused";
  out.catchRefreshSawCleared = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  out.catchFlagCleared = state.spaceStarterPreviewPending === false;
  // 4. Guard-finally path: deferredDraftSwitch commits a pending draft;
  // the downstream work exits early (never claims the draft), so the
  // guard's finish() fires the refresh - it must see the cleared flag,
  // and the committed edit must persist at first preview.
  state.spaceStarterPreviewPending = true;
  state.cleanDesign = clone(state.design);
  state.draft = changedDraft(40);
  refreshSawPending.length = 0;
  const guard = await deferredDraftSwitch();
  out.guardCommitted = guard.proceed === true && guard.committed === true;
  guard.finish();
  out.finishRefreshSawCleared = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.guardEditPersisted = autosaves.length === 1
    && autosaves[0].layout.features[0].options.w === 40;
  out.guardBaselineUntouched = state.cleanDesign.layout.features[0].options.w === 30;
  // 5. Guard no-change control: nothing to save -> no commit, finish()
  // fires no refresh, and the flag stays pending.
  state.spaceStarterPreviewPending = true;
  state.draft = clone(state.design.layout.features[0]);
  refreshSawPending.length = 0;
  const guard2 = await deferredDraftSwitch();
  guard2.finish();
  out.guardNoopNoRefresh = guard2.committed === false && refreshSawPending.length === 0;
  out.guardNoopKeepsPending = state.spaceStarterPreviewPending === true;
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__NEEDS_FN__", needs_fn)
        script = script.replace("__COMMIT_FN__", commit_fn)
        script = script.replace("__GUARD_FN__", guard_fn)
        script = script.replace("__DEFERRED_FN__", deferred_fn)
        script = script.replace("__HANDLER__", "(" + handler_src + ")")
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["directCommits"],
                        "commitVisibleDraft must commit a real pending change")
        self.assertTrue(data["directClears"],
                        "a real commitVisibleDraft commit (A17b) must clear the starter-preview flag")
        self.assertTrue(data["directApplied"],
                        "commitVisibleDraft must land the draft in the design")
        self.assertTrue(data["noopReturnsFalse"],
                        "a no-change commitVisibleDraft must return false")
        self.assertTrue(data["noopKeepsPending"],
                        "a no-change commit must keep the starter-preview flag pending")
        self.assertTrue(data["catchCommittedDraft"],
                        "the mode handler must commit the pending draft first")
        self.assertTrue(data["catchNotConverted"],
                        "a throwing mode API must leave the design unconverted")
        self.assertTrue(data["catchRefreshSawCleared"],
                        "the A7b catch refreshPreview must run only after the A17b clear")
        self.assertTrue(data["catchFlagCleared"],
                        "the A7b catch path must end with the starter-preview flag cleared")
        self.assertTrue(data["guardCommitted"],
                        "deferredDraftSwitch must commit a pending draft")
        self.assertTrue(data["finishRefreshSawCleared"],
                        "the guard finish() refreshPreview must run only after the A17b clear")
        self.assertTrue(data["guardEditPersisted"],
                        "the guard-committed edit must reach the autosave queue on first preview")
        self.assertTrue(data["guardBaselineUntouched"],
                        "cleanDesign must stay the pre-guard design, not the committed edit")
        self.assertTrue(data["guardNoopNoRefresh"],
                        "a no-change guard must not fire a finish() refresh")
        self.assertTrue(data["guardNoopKeepsPending"],
                        "a no-change guard must keep the starter-preview flag pending")

    def test_starter_preview_flag_clears_on_auto_commit(self):
        # Fix 1137 round 4 final revision (panel Tracer HOLD): Change A16b
        # is a seventh site in the same invariant - autoCommitDraft in
        # 10-draft-update-commit.js is the auto-save commit for an armed
        # draft, and pre-fix its own noteCommittedDesignChange cleared the
        # flag at the commit point. The blank-Text route reaches it as the
        # FIRST change in the starter-preview window: selectKind arms the
        # draft (draftAutoCommit) but its apply block skips a blank Text
        # draft (the Fix 082 H carve-out), so the Label sits uncommitted
        # with the flag pending until the user types - then refreshDraft
        # commits it through autoCommitDraft and its trailing
        # refreshPreview() adopts the preview. This executes the REAL
        # refreshDraft and the REAL autoCommitDraft (with the REAL
        # draftCommitIndex and isBlankTextDraft), plus the no-change leg:
        # a draft already identical to the placed feature commits nothing
        # and the flag must stay pending.
        commit_src = (ROOT / "web" / "app" / "10-draft-update-commit.js").read_text(encoding="utf-8")
        rd_start = commit_src.index("async function refreshDraft() {")
        rd_end = commit_src.index("\n// Anything that is only a size", rd_start)
        refresh_fn = commit_src[rd_start:rd_end].strip()
        ac_start = commit_src.index("async function autoCommitDraft(request) {")
        ac_end = commit_src.index("\nasync function commitVisibleDraft(", ac_start)
        auto_fn = commit_src[ac_start:ac_end].strip()
        self.assertEqual(auto_fn.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A16b must clear the starter-preview flag exactly once in autoCommitDraft")
        self.assertIn("if (previousDesign && JSON.stringify(previousDesign) !== JSON.stringify(state.design)) {",
                      auto_fn,
                      "Change A16b's clear must keep the A8b real-change guard")
        self.assertLess(auto_fn.index("state.design = result.design;"),
                        auto_fn.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the applied design lands")
        self.assertLess(auto_fn.index("state.spaceStarterPreviewPending = false;"),
                        auto_fn.index("state.draftIsNew = false;"),
                        "the flag must clear at the commit point, not after the commit epilogue")
        ci_start = commit_src.index("function draftCommitIndex() {")
        ci_end = commit_src.index("\n// Saves the draft into the design", ci_start)
        index_fn = commit_src[ci_start:ci_end].strip()
        state_src = (ROOT / "web" / "app" / "01-runtime-state.js").read_text(encoding="utf-8")
        bt_start = state_src.index("function isBlankTextDraft(feature) {")
        bt_end = state_src.index("\n// Consent belongs to this edit", bt_start)
        blank_fn = state_src[bt_start:bt_end].strip()
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const applyCalls = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const previewClientId = "test-client";
const statusEl = { textContent: "", classList: { add() {}, remove() {} } };
const $ = (sel) => (sel === "#draft-status" ? statusEl : null);
const number = (v, fallback) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};
const fmt = (v) => String(v);
const flashField = () => {};
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused", features: [] } },
  cleanDesign: null,
  draft: null,
  draftIsNew: true,
  draftTouched: false,
  draftRequest: 0,
  draftAutoCommit: true,
  draftSourceIndex: null,
  draftStartingText: "",
  selected: null,
  fitError: false,
  autoGrowingBin: false,
  boreAngleGrowthPending: false,
  spaceStarterPreviewPending: true,
};
const applyBoreSizing = () => {};
const bumpBoreEpoch = () => {};
const updateReferenceAddAvailability = () => {};
const allowSmallTextEdit = async () => true;
const partInfo = () => ({ kind: state.draft.kind, fields: [], flags: {} });
const sizeBoreToGrid = () => {};
const seedPartNameFromText = () => {};
const renderPlaced = () => {};
const updateSelectionButtons = () => {};
const syncForm = () => {};
const toast = () => {};
const friendlyError = (e) => String((e && e.message) || e);
const autoExpandBin = async () => {};
const flushBoreReconcile = () => {};
const updateAutoExpandButton = () => {};
const reconcileBoreBin = async () => false;
const maybePromptSurfaceObjectHeight = async () => {};
const refreshPreview = async () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
const api = async (url, payload) => {
  if (url === "/api/feature/draft") {
    const feature = clone(payload.feature);
    if (feature.kind === "text") feature.options = { ...feature.options, cap_height: 15 };
    return { feature, resolved_options: {} };
  }
  if (url === "/api/feature/apply") {
    applyCalls.push(url);
    const applied = clone(payload.design);
    if (payload.index === null || payload.index === undefined) {
      applied.layout.features.push(clone(payload.feature));
      return { design: applied, selected: applied.layout.features.length - 1, warnings: [] };
    }
    applied.layout.features[payload.index] = clone(payload.feature);
    return { design: applied, selected: payload.index, warnings: [] };
  }
  throw new Error("unexpected api " + url);
};
__BLANK_FN__
__INDEX_FN__
__AUTO_FN__
__REFRESH_FN__
(async () => {
  const out = {};
  // Blank-Text route, part 1: selectKind armed this Label draft but its
  // apply block skipped it (blank Text, Fix 082 H), so refreshDraft's
  // blank carve-out fires - no commit, flag stays pending.
  state.cleanDesign = clone(state.design);
  state.draft = { kind: "text", zone: [-16, -4, 16, 4], options: { text: "" } };
  await refreshDraft();
  out.blankNoCommit = applyCalls.length === 0 && state.draftIsNew === true;
  out.blankKeepsPending = state.spaceStarterPreviewPending === true;
  // Part 2: the user types the lettering. refreshDraft now commits the
  // draft through autoCommitDraft; Change A16b clears the flag at the
  // commit point, so refreshDraft's trailing refreshPreview() - the
  // adoption step - runs only after the clear.
  state.draft.options.text = "M3";
  await refreshDraft();
  out.typedCommitted = applyCalls.length === 1 && state.draftIsNew === false;
  out.typedClears = state.spaceStarterPreviewPending === false;
  out.refreshSawSequence = refreshSawPending.slice();
  out.committedText = state.design.layout.features[0]?.options?.text;
  // The edit survives first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1
    && autosaves[0].layout.features[0].options.text === "M3";
  out.baselineUntouched = state.cleanDesign.layout.features.length === 0;
  // No-change leg: the draft is already identical to the placed feature,
  // so autoCommitDraft returns without committing - no apply call, and
  // the flag stays pending through refreshDraft's trailing refresh.
  state.design = { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused",
    features: [{ kind: "post", zone: [0, 0, 2, 2], options: {} }] } };
  state.draft = clone(state.design.layout.features[0]);
  state.draftIsNew = false;
  state.draftSourceIndex = 0;
  state.selected = 0;
  state.spaceStarterPreviewPending = true;
  applyCalls.length = 0;
  refreshSawPending.length = 0;
  await refreshDraft();
  out.noChangeNoApply = applyCalls.length === 0;
  out.noChangeKeepsPending = state.spaceStarterPreviewPending === true
    && refreshSawPending.length === 1 && refreshSawPending[0] === true;
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__BLANK_FN__", blank_fn)
        script = script.replace("__INDEX_FN__", index_fn)
        script = script.replace("__AUTO_FN__", auto_fn)
        script = script.replace("__REFRESH_FN__", refresh_fn)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["blankNoCommit"],
                        "a blank Text draft must stay uncommitted (Fix 082 H carve-out)")
        self.assertTrue(data["blankKeepsPending"],
                        "a blank Text draft must keep the starter-preview flag pending")
        self.assertTrue(data["typedCommitted"],
                        "typing into the armed Text draft must commit it via autoCommitDraft")
        self.assertTrue(data["typedClears"],
                        "the autoCommitDraft commit (A16b) must clear the starter-preview flag")
        self.assertEqual(data["refreshSawSequence"], [True, False],
                         "refreshPreview must see the flag pending for the blank draft and "
                         "cleared after the auto-commit (the adoption step)")
        self.assertEqual(data["committedText"], "M3",
                         "the typed lettering must land in the design")
        self.assertTrue(data["editPersisted"],
                        "the auto-committed edit must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the edited design")
        self.assertTrue(data["noChangeNoApply"],
                        "a no-change auto-commit must not call the apply route")
        self.assertTrue(data["noChangeKeepsPending"],
                        "a no-change auto-commit must keep the starter-preview flag pending")

    def test_starter_preview_flag_clears_on_nest_photo(self):
        # Fix 1137 round 4 final revision 2 (panel Tracer HOLD): Change A20b
        # is an eighth site in the same invariant - finishPhotoNestIfReady
        # in 09-draft-sizing-helpers.js is the sole designed first committer
        # of a new Photo Nest: selectKind never commits a nest draft (its
        # apply block is gated kind !== "nest" and draftAutoCommit is false
        # for nests), the trace only sets state.nestTraceResult, and
        # entering Tool thickness fires this function directly. Pre-fix its
        # own noteCommittedDesignChange cleared the flag at the commit
        # point; Change A20 deletes that call. This executes the REAL
        # finishPhotoNestIfReady (with the REAL _nestMeasuredThickness)
        # through the trace/thickness route, plus both keeps-pending legs:
        # no completed trace yet, and a trace with no measured Tool
        # thickness, must each commit nothing and keep the flag pending.
        helpers = (ROOT / "web" / "app" / "09-draft-sizing-helpers.js").read_text(encoding="utf-8")
        fn_start = helpers.index("async function finishPhotoNestIfReady() {")
        fn_end = helpers.index("\nasync function acceptNestPaperCorners()", fn_start)
        nest_fn = helpers[fn_start:fn_end].strip()
        self.assertEqual(nest_fn.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A20b must clear the starter-preview flag exactly once in finishPhotoNestIfReady")
        self.assertIn("if (previousDesign && JSON.stringify(previousDesign) !== JSON.stringify(state.design)) {",
                      nest_fn,
                      "Change A20b's clear must keep the A8b real-change guard")
        self.assertLess(nest_fn.index("state.design = result.design;"),
                        nest_fn.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the nest design lands")
        self.assertLess(nest_fn.index("state.spaceStarterPreviewPending = false;"),
                        nest_fn.index("await refreshPreview();"),
                        "the flag must clear before the site's own refreshPreview() adoption")
        th_start = helpers.index("function _nestMeasuredThickness(options) {")
        th_end = helpers.index("\nasync function uploadNestPhoto(event) {", th_start)
        thickness_fn = helpers[th_start:th_end].strip()
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const photoCalls = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const number = (v, fallback) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};
const fmt = (v) => String(v);
const statusEl = { textContent: "", classList: { add() {}, remove() {} } };
const tabEl = { click() {} };
const $ = (sel) => (sel === "#draft-status" ? statusEl : tabEl);
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused", features: [] } },
  cleanDesign: null,
  draft: null,
  selected: null,
  draftKind: null,
  draftAutoCommit: false,
  drafts: null,
  nestTraceResult: null,
  nestAcceptedCenterMm: null,
  spaceStarterPreviewPending: true,
};
const beginDesignMutation = () => true;
const finishDesignMutation = () => {};
const draftCommitIndex = () => null;
const setNestPhotoReference = () => {};
const syncForm = () => {};
const renderDraftFields = () => {};
const setLayoutOrientation = () => {};
const toast = () => {};
const friendlyError = (e) => String((e && e.message) || e);
const refreshPreview = async () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
const api = async (url, payload) => {
  if (url !== "/api/nest/photo") throw new Error("unexpected api " + url);
  photoCalls.push(url);
  const committed = clone(payload.design);
  committed.layout.features.push({
    kind: "nest",
    zone: [0, 0, 10, 8],
    options: { ...(payload.options || {}), contour: payload.contour },
  });
  return { design: committed, selected: committed.layout.features.length - 1, warnings: [] };
};
__THICKNESS_FN__
__NEST_FN__
(async () => {
  const out = {};
  state.cleanDesign = clone(state.design);
  state.draft = { kind: "nest", options: {} };
  // No completed trace yet: finalization does nothing - no commit, and
  // the flag stays pending.
  await finishPhotoNestIfReady();
  out.noTraceNoCommit = photoCalls.length === 0;
  out.noTraceKeepsPending = state.spaceStarterPreviewPending === true;
  // Trace done but no Tool thickness measured: still nothing commits.
  state.nestTraceResult = {
    contour: [[0, 0], [10, 0], [10, 8], [0, 8]],
    reference: { bounds: [0, 0, 10, 8] },
    outline: { width: 50, depth: 40 },
    trace_center_mm: [25, 20],
  };
  await finishPhotoNestIfReady();
  out.noThicknessNoCommit = photoCalls.length === 0;
  out.noThicknessKeepsPending = state.spaceStarterPreviewPending === true;
  // Tool thickness entered (the draft-field route fires this function
  // directly): finishPhotoNestIfReady commits the nest design itself,
  // and Change A20b clears the flag at the commit point, before its own
  // refreshPreview() adoption runs.
  state.draft.options.tool_thickness = 6;
  await finishPhotoNestIfReady();
  out.photoCommitted = photoCalls.length === 1
    && state.design.layout.features.length === 1
    && state.design.layout.features[0].kind === "nest";
  out.photoClears = state.spaceStarterPreviewPending === false;
  out.refreshSawClearedFlag = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  // The edit survives first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1
    && autosaves[0].layout.features[0].kind === "nest";
  out.baselineUntouched = state.cleanDesign.layout.features.length === 0;
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__THICKNESS_FN__", thickness_fn)
        script = script.replace("__NEST_FN__", nest_fn)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["noTraceNoCommit"],
                        "with no completed trace, nest finalization must not call the photo route")
        self.assertTrue(data["noTraceKeepsPending"],
                        "with no completed trace, the starter-preview flag must stay pending")
        self.assertTrue(data["noThicknessNoCommit"],
                        "with no measured Tool thickness, nest finalization must not commit")
        self.assertTrue(data["noThicknessKeepsPending"],
                        "with no measured Tool thickness, the starter-preview flag must stay pending")
        self.assertTrue(data["photoCommitted"],
                        "trace + thickness must commit the nest design via finishPhotoNestIfReady")
        self.assertTrue(data["photoClears"],
                        "the finishPhotoNestIfReady commit (A20b) must clear the starter-preview flag")
        self.assertTrue(data["refreshSawClearedFlag"],
                        "refreshPreview must run only after the flag is cleared")
        self.assertTrue(data["editPersisted"],
                        "the committed nest must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the nest design")

    def test_starter_preview_flag_clears_on_auto_expand(self):
        # Fix 1137 round 4 final revision 2 (panel Tracer HOLD): Change
        # A15b is a ninth site in the same invariant - autoExpandBin in
        # 11-parts-preview-requests.js is designed to commit a
        # never-committed draft: it folds the open draft into the design
        # sent to /api/layout/expand, replaces state.design, and runs its
        # own refreshPreview(). It is reachable as the FIRST change in the
        # starter-preview window from the selectKind apply-failure state
        # (the draft stays new and uncommitted) via the Grow-bin button or
        # refreshDraft's outgrow-error catch. Pre-fix, its
        # `if (changed) noteCommittedDesignChange(...)` cleared the flag at
        # the commit point; Change A15 deletes that call. This executes
        # the REAL autoExpandBin (with the REAL draftCommitIndex) on the
        # apply-failure route, plus the unchanged leg: when the server
        # reports no change, the flag must stay pending - the restored
        # clear keeps the site's own `changed` condition and the A8b
        # real-change guard, exactly the pre-fix clear condition.
        preview_src = (ROOT / "web" / "app" / "11-parts-preview-requests.js").read_text(encoding="utf-8")
        ex_start = preview_src.index("async function autoExpandBin(")
        ex_end = preview_src.index("\n// A manually reduced bin never leaves existing parts invalid.", ex_start)
        expand_fn = preview_src[ex_start:ex_end].strip()
        self.assertEqual(expand_fn.count("state.spaceStarterPreviewPending = false;"), 1,
                         "Change A15b must clear the starter-preview flag exactly once in autoExpandBin")
        self.assertIn("if (changed && previousDesign && JSON.stringify(previousDesign) !== JSON.stringify(state.design)) {",
                      expand_fn,
                      "Change A15b's clear must keep the site's `changed` condition and the A8b real-change guard")
        self.assertLess(expand_fn.index("state.design = result.design;"),
                        expand_fn.index("state.spaceStarterPreviewPending = false;"),
                        "the flag must clear after the expanded design lands")
        self.assertLess(expand_fn.index("state.spaceStarterPreviewPending = false;"),
                        expand_fn.index("state.fitError = false;"),
                        "the flag must clear at the commit point, beside the design assignment")
        commit_src = (ROOT / "web" / "app" / "10-draft-update-commit.js").read_text(encoding="utf-8")
        ci_start = commit_src.index("function draftCommitIndex() {")
        ci_end = commit_src.index("\n// Saves the draft into the design", ci_start)
        index_fn = commit_src[ci_start:ci_end].strip()
        br_start = preview_src.index("if (state.spaceStarterPreviewPending) {")
        br_end = (preview_src.index("} else queueSpaceDesignAutosave();", br_start)
                  + len("} else queueSpaceDesignAutosave();"))
        first_preview_branch = preview_src[br_start:br_end]
        script = r"""
const autosaves = [];
const refreshSawPending = [];
const expandCalls = [];
const clone = (v) => JSON.parse(JSON.stringify(v));
const fmt = (v) => String(v);
const $ = () => ({ disabled: false });
const state = {
  design: { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused", features: [] } },
  cleanDesign: null,
  draft: null,
  draftIsNew: true,
  draftSourceIndex: null,
  selected: null,
  fitError: true,
  spaceStarterPreviewPending: true,
};
const beginDesignMutation = () => true;
const finishDesignMutation = () => {};
const toast = () => {};
const flashField = () => {};
const clearDraftSelection = () => { state.draft = null; };
const syncForm = () => {};
const updateAutoExpandButton = () => {};
const renderDraftFields = () => {};
const updateSelectionButtons = () => {};
const refreshPreview = async () => { refreshSawPending.push(state.spaceStarterPreviewPending); };
let expandMode = "grow";
const api = async (url, payload) => {
  if (url !== "/api/layout/expand") throw new Error("unexpected api " + url);
  expandCalls.push(url);
  if (expandMode === "grow") {
    const grown = clone(payload.design);
    grown.box = { ...grown.box, x: 140 };
    return { design: grown, changed: true, grew: true, box: { x: 140, y: 80 } };
  }
  return { design: clone(payload.design), changed: false, grew: false, box: { x: 100, y: 80 } };
};
__INDEX_FN__
__EXPAND_FN__
(async () => {
  const out = {};
  state.cleanDesign = clone(state.design);
  // Apply-failure state: selectKind's apply was rejected (the part does
  // not fit), so this Post draft is still new and never committed. The
  // Grow-bin button folds it in and commits the expanded design itself.
  state.draft = { kind: "post", zone: [0, 0, 30, 2], options: {} };
  const status = await autoExpandBin({});
  out.growDone = status === "done" && expandCalls.length === 1;
  out.draftFoldedIn = state.design.layout.features.length === 1
    && state.design.layout.features[0].kind === "post";
  out.boxGrew = state.design.box.x === 140;
  out.growClears = state.spaceStarterPreviewPending === false;
  out.refreshSawClearedFlag = refreshSawPending.length === 1 && refreshSawPending[0] === false;
  // The edit survives first-preview persistence (the real branch from
  // 11-parts-preview-requests.js): autosave queued, baseline untouched.
  const queueSpaceDesignAutosave = () => { autosaves.push(clone(state.design)); };
  __FIRST_PREVIEW_BRANCH__
  out.editPersisted = autosaves.length === 1
    && autosaves[0].layout.features.length === 1;
  out.baselineUntouched = state.cleanDesign.layout.features.length === 0
    && state.cleanDesign.box.x === 100;
  // Unchanged leg: a fresh starter window, an uncommitted draft, and the
  // server reports the parts already fit (changed === false) - the
  // pre-fix clear was gated on `changed`, so the flag stays pending.
  state.design = { box: { x: 100, y: 80, z: 60 }, layout: { mode: "fused", features: [] } };
  state.draft = { kind: "post", zone: [0, 0, 2, 2], options: {} };
  state.draftIsNew = true;
  state.selected = null;
  state.spaceStarterPreviewPending = true;
  refreshSawPending.length = 0;
  expandMode = "unchanged";
  await autoExpandBin({});
  out.unchangedKeepsPending = state.spaceStarterPreviewPending === true
    && refreshSawPending.length === 1 && refreshSawPending[0] === true;
  process.stdout.write(JSON.stringify(out));
})();
""".replace("__INDEX_FN__", index_fn)
        script = script.replace("__EXPAND_FN__", expand_fn)
        script = script.replace("__FIRST_PREVIEW_BRANCH__", first_preview_branch)
        data = node_json(script)
        self.assertTrue(data["growDone"],
                        "the Grow-bin route must run autoExpandBin to completion")
        self.assertTrue(data["draftFoldedIn"],
                        "autoExpandBin must fold the uncommitted draft into the committed design")
        self.assertTrue(data["boxGrew"],
                        "the expanded design must land as state.design")
        self.assertTrue(data["growClears"],
                        "the autoExpandBin commit (A15b) must clear the starter-preview flag")
        self.assertTrue(data["refreshSawClearedFlag"],
                        "refreshPreview must run only after the flag is cleared")
        self.assertTrue(data["editPersisted"],
                        "the expanded design must reach the autosave queue on first preview")
        self.assertTrue(data["baselineUntouched"],
                        "cleanDesign must stay the pristine starter, not the expanded design")
        self.assertTrue(data["unchangedKeepsPending"],
                        "an expand the server reports unchanged must keep the starter-preview flag pending")



    def test_surface_height_label_resets_without_reload(self):
        source = function_source("syncSurfaceControls", APP)
        script = r"""
const state={shown:true,design:{layout:{},box:{base_thickness:0.6}},
 activeSpace:{trim_size:'medium'}};
const nodes={};
const $=selector=>nodes[selector]??=( {hidden:false,textContent:'',value:'',checked:false} );
const isSurfaceBinDesign=()=>state.shown,surfaceTrimHeight=()=>7.5;
const surfaceStackingBlocked=()=>false,fmt=String;
const document={activeElement:null};
__SOURCE__
const labels=[];
for(const shown of [true,false,true]){
 state.shown=shown;syncSurfaceControls();labels.push($('#z-size-label').textContent);
}
process.stdout.write(JSON.stringify(labels));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), ["Bin height", "Height", "Bin height"])

    def test_nudge_success_failure_and_stale_response_without_undo_snapshot(self):
        # Fix 1137 rework (Change A58): Change A10b removes commitNudge's
        # noteCommittedDesignChange call - the undo snapshot it fed is
        # deleted - so this test no longer counts committed changes, and
        # the starter-preview flag is asserted UNTOUCHED by the nudge
        # commit (the flag lifecycle belongs to the A8b/A16b/A17b commit
        # paths; a nudge edits an already-placed feature).
        source = APP[APP.index("const commitNudge = debounce("):
                     APP.index("}, 200);", APP.index("const commitNudge = debounce(")) + len("}, 200);")]
        handler = function_source("handleLayoutArrowKeys", APP)
        self.assertIn("if (!pendingNudgeDraft)", handler)
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v)),debounce=fn=>fn;
const original={kind:'post',zone:[0,0,2,2]};
let pendingNudgeDraft=clone(original),resolveApi,rejectApi;
const state={draftRequest:1,selected:0,draft:{kind:'post',zone:[1,0,3,2]},
 design:{layout:{features:[clone(original)]}},spaceStarterPreviewPending:true};
const api=()=>new Promise((resolve,reject)=>{resolveApi=resolve;rejectApi=reject});
const toast=()=>{},renderDraftFields=()=>{},refreshDraft=async()=>{},renderLayout2D=()=>{};
const renderPlaced=()=>{},updateSelectionButtons=()=>{};
__SOURCE__
(async()=>{
 const success=commitNudge(1);
 resolveApi({design:{layout:{features:[clone(state.draft)]}},selected:0});
 await success;
 const afterSuccess={zone:state.draft.zone,pending:pendingNudgeDraft,
  starter:state.spaceStarterPreviewPending};
 state.draftRequest=2;state.draft={kind:'post',zone:[2,0,4,2]};
 pendingNudgeDraft=clone(original);
 const failure=commitNudge(2);rejectApi(Error('rejected'));await failure;
 const afterFailure={zone:state.draft.zone,pending:pendingNudgeDraft};
 state.draftRequest=3;state.draft={kind:'post',zone:[3,0,5,2]};
 pendingNudgeDraft=clone(original);
 const stale=commitNudge(3);
 state.draftRequest=4;state.draft={kind:'post',zone:[4,0,6,2]};
 resolveApi({design:{layout:{features:[{kind:'post',zone:[99,0,101,2]}]}},selected:0});
 await stale;
 process.stdout.write(JSON.stringify({afterSuccess,afterFailure,
  afterStale:{zone:state.draft.zone,pending:pendingNudgeDraft}}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "afterSuccess": {"zone": [1, 0, 3, 2], "pending": None,
                             "starter": True},
            "afterFailure": {"zone": [0, 0, 2, 2], "pending": None},
            "afterStale": {"zone": [4, 0, 6, 2], "pending": {"kind": "post", "zone": [0, 0, 2, 2]}},
        })



    def test_bore_ceiling_warning_stays_at_design_level_and_clears(self):
        source = function_source("updateBoreCeilingWarning", APP)
        script = r"""
const element={hidden:true,textContent:''};
const fmt=v=>String(Math.round(Number(v)*100)/100);
const $=selector=>selector==='#bore-ceiling-warning' ? element : null;
__SOURCE__
updateBoreCeilingWarning({top_mm:72,cap_mm:64,space_kind:'drawer'});
const whileEditingAnotherBore={hidden:element.hidden,text:element.textContent};
updateBoreCeilingWarning(null);
process.stdout.write(JSON.stringify({whileEditingAnotherBore,afterCorrection:{hidden:element.hidden,text:element.textContent}}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "whileEditingAnotherBore": {"hidden": False,
                "text": "Object reaches 72 mm; this Drawer is 64 mm high. The object may not fit when closed."},
            "afterCorrection": {"hidden": True, "text": ""},
        })
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        self.assertLess(html.index('id="bore-ceiling-warning"'), html.index('class="canvas-wrap'))
        self.assertNotIn("data-bore-ceiling-warning", APP)


    def test_measured_item_preview_group_follows_interior_visibility_and_framing(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("classifyOrdinaryFace", "previewAabbWithoutMeasured", "currentPreviewPasses"))
        script = r"""
const state={binVisible:true,interiorVisible:true,xrayOn:false};
const b4bEnabled=()=>false,baseTrimEnabled=()=>false;
const buffers={allAabb:{min:[-5,-5,0],max:[5,5,100]},groups:{
 bin:{aabb:{min:[-5,-5,0],max:[5,5,30]}},
 interior:{aabb:{min:[-3,-3,1],max:[3,3,25]}},
 measured:{aabb:{min:[-2,-2,1],max:[2,2,100]}}}};
__SOURCE__
const shown=currentPreviewPasses(buffers);
state.interiorVisible=false;
const hidden=currentPreviewPasses(buffers);
process.stdout.write(JSON.stringify({group:classifyOrdinaryFace({kind:'measured_item'}),
 shown:shown.passes,shownZ:shown.aabb.max[2],hidden:hidden.passes,hiddenZ:hidden.aabb.max[2]}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "group": "measured",
            "shown": [{"group": "bin", "alpha": 1}, {"group": "interior", "alpha": 1},
                      {"group": "measured", "alpha": .3}], "shownZ": 100,
            "hidden": [{"group": "bin", "alpha": 1}], "hiddenZ": 30,
        })

    def test_modifier_immediate_save_flushes_edge_grip_and_opening(self):
        # Fix 1137 rework (Change A58): Change A24 renames the snapshot
        # flushModifierForm reads (pendingDesignHistory ->
        # pendingPreEditDesign, Changes A8/A9) and removes its
        # noteCommittedDesignChange call, so this harness declares the
        # renamed snapshot and no longer counts committed changes. The
        # failure-case expectation below (closed: False when the save
        # fails) is not met by the shipped code - it fails identically on
        # pristine product main and is carved out in the Acceptance
        # criteria as a pre-existing, unrelated failure.
        source = "\n".join(function_source(name, APP) for name in
                           ("flushModifierForm", "saveModifierPart"))
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v));
const cases=[['edge_mount','label_text','Last label'],
 ['inside_grip','size','large'],['side_openings','shape','square']];
const seen=[];
let state,pendingPreEditDesign,visible,debounced,fail;
const beginDesignMutation=()=>true,finishDesignMutation=()=>{};
const cancelChangedDesignDebounce=()=>{debounced=false};
const applyLiveFormWithModifierConflictGuard=()=>{
 state.design.box[state.modifierEditing][visible.key]=visible.value;return true;
};
const api=async()=>{if(fail)throw Error('validation failed');return {design:clone(state.design)}};
const clearDraftSelection=()=>{state.modifierEditing=null},renderPlaced=()=>{},refreshPreview=async()=>{};
const toast=()=>{};
__SOURCE__
(async()=>{
 for(const [kind,key,value] of cases){
  state={modifierEditing:kind,design:{box:{[kind]:{[key]:'old',label_enabled:true}}},canGenerate:true};
  pendingPreEditDesign=clone(state.design);visible={key,value};debounced=true;fail=false;
  await saveModifierPart();
  seen.push({kind,value:state.design.box[kind][key],debounced,closed:state.modifierEditing===null});
 }
 state={modifierEditing:'inside_grip',design:{box:{inside_grip:{size:'old'}}},canGenerate:true};
 pendingPreEditDesign=clone(state.design);visible={key:'size',value:'medium'};debounced=true;fail=true;
 await saveModifierPart();
 seen.push({kind:'failed',value:state.design.box.inside_grip.size,closed:state.modifierEditing===null});
 process.stdout.write(JSON.stringify(seen));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        result = node_json(script)
        for actual, expected in zip(result[:3], ("Last label", "large", "square")):
            self.assertEqual(actual["value"], expected)
            self.assertFalse(actual["debounced"])
            self.assertTrue(actual["closed"])
        self.assertEqual(result[3], {"kind": "failed", "value": "medium", "closed": False})

    def test_space_canvas_switch_remembers_design_view_and_uses_space_renderer(self):
        source = function_source("activatePreviewView", APP) + "\n" + function_source("preferredDesignView", APP)
        script = r"""
const events=[],state={folderMode:'space',runtime:{hosted:false},lastDesignView:'3d'};
const make=()=>({active:false,classList:{toggle(_name,on){this.active=on},
  remove(){},add(){}},setAttribute(){},tabIndex:0,offsetWidth:1});
const tabs={'2d':make(),'3d':make()},wraps={'2d':make(),'3d':make(),drawer:make()};
const $=s=>s.startsWith('.view-tab')?tabs[s.match(/data-view="([^"]+)/)[1]]:
  s.startsWith('.canvas-wrap')?wraps[s.match(/data-canvas="([^"]+)/)[1]]:null;
const $$=s=>s==='.view-tab'?Object.values(tabs):Object.values(wraps);
const updatePreviewHelp=()=>{},updateDividerEditBreadcrumb=()=>{},updateNudgeUI=()=>{};
const requestAnimationFrame=fn=>fn(),renderPreview3D=()=>events.push('3d'),
  renderLayout2D=()=>events.push('2d'),DV={render:()=>events.push('space')};
__SOURCE__
activatePreviewView('2d');activatePreviewView('drawer');
const inSpace={remembered:preferredDesignView(),canvases:Object.fromEntries(Object.entries(wraps).map(([k,v])=>[k,v.classList.active]))};
activatePreviewView(preferredDesignView());
process.stdout.write(JSON.stringify({inSpace,after:Object.fromEntries(Object.entries(wraps).map(([k,v])=>[k,v.classList.active])),events}));
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out["inSpace"], {"remembered": "2d", "canvases": {"2d": False, "3d": False, "drawer": True}})
        self.assertEqual(out["after"], {"2d": True, "3d": False, "drawer": False})
        self.assertEqual(out["events"], ["2d", "space", "2d"])

    def test_ai_candidate_name_keeps_free_suffix_and_renumbers_collisions(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("aiTypedSpaceActive", "aiResolveCandidateName"))
        script = r"""
const state={folderMode:'space',designInventoryId:'B1'};
const DL={active:true,layout:{},bins:[{id:'B1',name:'Lipstick'},{id:'B2',name:'Other'}]};
__SOURCE__
const resolve=(name,excludeCurrent)=>aiResolveCandidateName(name,{excludeCurrent});
const freeSuffix=resolve(' Lipstick (2) ',false);
const firstCollision=resolve('lipstick',false);
DL.bins.push({id:'B3',name:'LIPSTICK (2)'});
const suffixCollision=resolve('Lipstick (2)',false);
const modifyingOwn=resolve('Lipstick',true);
const newAgainstOwn=resolve('Lipstick',false);
process.stdout.write(JSON.stringify({freeSuffix,firstCollision,suffixCollision,modifyingOwn,newAgainstOwn}));
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {
            "freeSuffix": "Lipstick (2)", "firstCollision": "lipstick (2)",
            "suffixCollision": "Lipstick (3)", "modifyingOwn": "Lipstick",
            "newAgainstOwn": "Lipstick (3)",
        })

    def test_ai_recent_descriptions_save_only_per_space_and_failure_is_nonblocking(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("aiTypedSpaceActive", "aiRecordRecentDescription"))
        script = r"""
const warnings=[],state={folderMode:'space'};
const DL={active:true,layout:{settings:{ai_design_recent_descriptions:[]}},
  change:fn=>{fn();return true},save:async()=>DL.saveOk};
const aiRenderRecentDescriptions=()=>{},toast=m=>warnings.push(m);
__SOURCE__
(async()=>{
  DL.saveOk=true;
  for(let i=0;i<11;i++)await aiRecordRecentDescription(' Object '+i+' ');
  await aiRecordRecentDescription('object 5');
  const recent=[...DL.layout.settings.ai_design_recent_descriptions];
  DL.saveOk=false;await aiRecordRecentDescription('unsaved description');
  state.folderMode='design';await aiRecordRecentDescription('outside Space');
  process.stdout.write(JSON.stringify({recent,current:DL.layout.settings.ai_design_recent_descriptions,
    warnings}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(len(out["recent"]), 10)
        self.assertEqual(out["recent"][0], "object 5")
        self.assertNotIn("Object 0", out["recent"])
        self.assertEqual(out["current"][0], "unsaved description")
        self.assertNotIn("outside Space", out["current"])
        self.assertEqual(len(out["warnings"]), 1)

    def test_bore_angle_proves_growth_before_mutating_and_cancel_keeps_draft(self):
        source = function_source("commitBoreAngleChange", APP)
        script = r"""
const clone=v=>JSON.parse(JSON.stringify(v)),events=[];
const state={design:{box:{x:32,y:32},layout:{features:[{kind:'bore'}]}},
  draft:{kind:'bore',zone:[-8,-8,8,8],options:{angle:0}},boreEpoch:0};
const input={dataset:{draft:'option:angle'},value:'80'};
let targetX=40,accepted=false,spaceError=null;
const number=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f,fmt=v=>String(v);
const draftCommitIndex=()=>0,boreXyMode=()=> 'manual',
  boreDefaultAngleDirection=()=> 'back';
const sizeBoreToGrid=(candidate,{syncFields})=>{
  events.push('size-candidate:'+syncFields);
  candidate.zone=[-12,-8,12,8];
};
const api=async(_path,body)=>{events.push('probe:'+body.design.layout.features[0].options.angle);
  events.push('zone:'+body.design.layout.features[0].zone.join(','));
  return{design:{...body.design,box:{...body.design.box,x:targetX}},box:{x:targetX,y:32}}};
const aiSpaceViolation=()=>spaceError;
const appConfirmAction=async()=>{events.push('confirm');return accepted};
const updateDraftFromFields=()=>{events.push('mutate');state.draft.options.angle=10;state.boreEpoch++};
const refreshDraftSoon={cancel:()=>events.push('cancel-refresh')};
const autoExpandBin=async()=>{events.push('grow');return 'done'};
const renderDraftFields=()=>{},renderPlaced=()=>{},refreshPreview=async()=>{},
  toast=message=>events.push('toast:'+message);
__SOURCE__
const run=async()=>{events.length=0;state.draft.options.angle=0;state.boreEpoch=0;input.value='80';
 await commitBoreAngleChange({currentTarget:input});
 return{angle:state.draft.options.angle,value:input.value,events:[...events]}};
(async()=>{
 const cancel=await run();accepted=true;
 const grow=await run();targetX=32;
 const fit=await run();targetX=40;spaceError='too large';
 const impossible=await run();
 process.stdout.write(JSON.stringify({cancel,grow,fit,impossible}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual((out["cancel"]["angle"], out["cancel"]["value"]), (0, "90"))
        lead = ["size-candidate:false", "probe:10", "zone:-12,-8,12,8"]
        self.assertEqual(out["cancel"]["events"], lead + ["confirm"])
        self.assertEqual(out["grow"]["events"], lead + ["confirm", "mutate", "cancel-refresh", "grow"])
        self.assertEqual(out["fit"]["events"], lead + ["mutate"])
        self.assertEqual(out["impossible"]["angle"], 0)
        self.assertNotIn("confirm", out["impossible"]["events"])

    def test_same_selected_preview_pick_rechecks_generation_before_2d(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("selectedFeature", "selectFromPreview"))
        script = r"""
const design={layout:{features:[{kind:'post'}]}},space={id:'S'},events=[];
const state={design,activeSpace:space,designInventoryId:'B1',previewRequest:4,selected:0};
const DP={mode:'design'},$=()=>({textContent:'',classList:{add(){},remove(){}}});
const activatePreviewView=v=>events.push(v),renderLayout2D=()=>events.push('layout');
const localStorage={getItem:()=>null};
__SOURCE__
(async()=>{
  const rejected=await selectedFeature(0,false,()=>false);
  Promise.resolve().then(()=>state.previewRequest++);
  await selectFromPreview({type:'saved',index:0},
    {design,space,source:'B1',preview:4});
  process.stdout.write(JSON.stringify({rejected,events,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"rejected": False, "events": [], "selected": 0})




    def test_compact_mesh_pick_is_frontmost_and_respects_base_lid_visibility(self):
        names = ["pointInPolygon", "pickTriangleDepth", "previewPickDepth", "clickedPreviewMesh"]
        source = "\n".join(function_source(name, APP) for name in names)
        script = r"""
const tri=z=>[0,0,z,10,0,z,0,10,z];
const divider={positions:tri(1),normals:[0,0,1],owner:'base'};
const cover={positions:tri(2),normals:[0,0,1],owner:'base'};
const state={preview:{meshes:[divider],pick_meshes:[{mesh_index:0,pick:{type:'saved',index:0}}]},
  previewPickMeshContext:{camera:{},project:p=>[p[0],p[1]],visibleGroups:new Set(['base'])}};
const cameraVector=()=>[0,0,1],iso=p=>p,dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
__SOURCE__
const picked=clickedPreviewMesh([2,2])?.pick;
state.preview.meshes.push(cover);
const occluded=clickedPreviewMesh([2,2])?.pick;
state.previewPickMeshContext.visibleGroups=new Set(['lid']);
const hidden=clickedPreviewMesh([2,2]);
process.stdout.write(JSON.stringify({picked,occluded,hidden}));
""".replace("__SOURCE__", source)
        out = node_json(script)
        self.assertEqual(out, {"picked": {"type": "saved", "index": 0}, "occluded": None, "hidden": None})


    def test_delayed_preview_pick_rejects_new_preview_generation(self):
        source = function_source("selectedFeature", APP)
        script = r"""
const design={layout:{features:[{kind:'post',zone:[0,0,8,8]}]}}, space={id:'S'};
const state={design,activeSpace:space,designInventoryId:'B1',previewRequest:7,
  selected:null,draft:{kind:'post'},partZoneLocks:{}};
let release; const deferredDraftSwitch=()=>new Promise(resolve=>release=resolve);
const $=()=>({hidden:false}),$$=()=>[];
const clone=v=>JSON.parse(JSON.stringify(v));
const resetNestPhotoSession=()=>{},flushModifierForm=()=>true;
const cancelPendingDraftWork=()=>{},updateNudgeUI=()=>{},AUTO_FOOTPRINT_KINDS=new Set();
const updateInteriorModeVisibility=()=>{},partInfo=()=>({}),syncDraftEditorIdentity=()=>{};
const renderDraftFields=()=>{},renderPlaced=()=>{},updateSelectionButtons=()=>{};
const refreshDraft=()=>{},renderLayout2D=()=>{};
__SOURCE__
(async()=>{
  const oldGeneration=state.previewRequest;
  const pending=selectedFeature(0,false,()=>state.previewRequest===oldGeneration);
  state.previewRequest++;
  release({proceed:true,committed:false,finish:()=>{}});
  const accepted=await pending;
  process.stdout.write(JSON.stringify({accepted,selected:state.selected}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__SOURCE__", source)
        self.assertEqual(node_json(script), {"accepted": False, "selected": None})






    def test_side_opening_browser_size_filter_matches_python_validator(self):
        source = "\n".join(function_source(name, APP) for name in
                           ("sideOpeningSideSpan", "sideOpeningVerticalFits", "sideOpeningAllowedSizes"))
        cases = [
            ("curved", 0.0, 0.0, False, 32.0),
            ("square", 35.0, 0.0, False, 32.0),
            ("curved", 10.0, 25.0, True, 32.0),
            ("square", 35.0, 25.0, True, 32.0),
            ("curved", 40.0, 35.0, True, 20.0),
        ]
        designs = []
        for shape, bottom, top, bridged, height in cases:
            designs.append({"box": {
                "x": 48.0, "y": 40.0, "z": height, "base_thickness": 0.6,
                "stack": {"enabled": bridged},
                "side_openings": {"enabled": True, "sides": ["front", "right"],
                                  "shape": shape, "size": "small",
                                  "from_bottom_percent": bottom, "from_top_percent": top},
            }})
        catalog = {"side_openings": {"corner_margin_mm": SIDE_OPENING_CORNER_MARGIN_MM,
                                      "sizes": [{"value": key, "width_mm": value}
                                                for key, value in SIDE_OPENING_WIDTHS.items()]}}
        script = r"""
const designs=__DESIGNS__,state={catalog:__CATALOG__};
const number=(v,f=0)=>Number.isFinite(Number(v))?Number(v):f;
const sideOpeningState=d=>d.box.side_openings;
__SOURCE__
process.stdout.write(JSON.stringify(designs.map(d=>sideOpeningAllowedSizes(d))));
""".replace("__DESIGNS__", json.dumps(designs)).replace("__CATALOG__", json.dumps(catalog)).replace("__SOURCE__", source)
        offered = node_json(script)
        for design, js_allowed in zip(designs, offered):
            data = design["box"]
            so = data["side_openings"]
            box = BoxSpec(data["x"], data["y"], data["z"],
                          stack=StackSpec(mode="direct" if data["stack"]["enabled"] else "none"))
            spec = SideOpeningSpec(enabled=True, sides=tuple(so["sides"]),
                                   shape=so["shape"], size="small",
                                   from_bottom_percent=so["from_bottom_percent"],
                                   from_top_percent=so["from_top_percent"])
            expected = side_opening_allowed_sizes(box, spec)
            self.assertEqual(js_allowed, list(expected), so)
            for size in SIDE_OPENING_WIDTHS:
                candidate = replace(box, side_openings=replace(spec, size=size))
                if size in expected:
                    validate_side_openings(candidate)
                else:
                    with self.assertRaises(ValueError, msg=(so, size)):
                        validate_side_openings(candidate)

    def test_ai_help_envelope_session_and_space_rules(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiParseEnvelope", "aiCheckSession", "aiSpaceViolation",
            "pegboardProductMinimums"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        schema = re.search(r'const AI_SCHEMA = "([^"]+)"', APP).group(1)
        script = r"""
__ERROR__
const AI_SCHEMA='__SCHEMA__',number=(v,f=0)=>{const n=Number(v);return Number.isFinite(n)?n:f},fmt=v=>String(v);
let draft=false,key='K1',space={kind:'drawer',x:80,y:80,z:50};
const state={folderMode:'space',get activeSpace(){return space},catalog:{base_unit:8}};
const draftNeedsSaving=()=>draft,edgeMountActive=d=>Boolean(d.box.edge_mount?.active);
const isStructuralDesign=d=>Boolean(d.box.b4b?.enabled),drawerSpaceCapacity=mm=>Math.floor(mm/8);
const aiContextKey=()=>key;
__FUNCTIONS__
const ok={schema:AI_SCHEMA,request_id:'R',context_fingerprint:'F',assumptions:[],design:{box:{x:16}}};
const text=v=>JSON.stringify(v);
const fail=fn=>{try{fn();return null}catch(e){return e.stale?'stale':e.message}};
const parsed=[
  aiParseEnvelope(text(ok)).request_id,
  aiParseEnvelope('```json\n'+text(ok)+'\n```').request_id,
  fail(()=>aiParseEnvelope('Here you go: '+text(ok))),
  fail(()=>aiParseEnvelope(text(ok)+text(ok))),
  fail(()=>aiParseEnvelope('```json\n```json\n'+text(ok)+'\n```\n```')),
  fail(()=>aiParseEnvelope(text({...ok,schema:'v2'}))),
  fail(()=>aiParseEnvelope(text({...ok,assumptions:undefined}))),
  fail(()=>aiParseEnvelope(text({...ok,design:[]}))),
];
const session={request_id:'R',context_fingerprint:'F',contextKey:'K1'};
const sessions=[fail(()=>aiCheckSession(ok,session)),fail(()=>aiCheckSession(ok,null)),
  fail(()=>aiCheckSession({...ok,request_id:'OLD'},session)),
  fail(()=>{key='K2';aiCheckSession(ok,session)})];
const base={box:{x:32,y:32,z:40,pegboard:{enabled:true,standard:'standard',cleat_x:'auto'}}};
space={kind:'drawer',x:80,y:80,z:50};const plain={box:{x:32,y:32,z:40}};
const rules=[aiSpaceViolation({box:{x:72,y:72,z:50}},plain),aiSpaceViolation({box:{x:88,y:72,z:50}},plain),
  aiSpaceViolation({box:{x:72,y:72,z:60}},plain),
  aiSpaceViolation({box:{x:16,y:16,z:40,b4b:{enabled:true}}},plain)];
space={kind:'pegboard',x:200,y:200,z:100,pegboard_standard:'standard'};
rules.push(aiSpaceViolation({box:{x:32,y:32,z:60,pegboard:base.box.pegboard}},base),
  aiSpaceViolation({box:{x:32,y:32,z:60}},base),
  aiSpaceViolation({box:{x:32,y:32,z:60,pegboard:{...base.box.pegboard,cleat_x:'3'}}},base),
  aiSpaceViolation({box:{x:32,y:32,z:40,pegboard:base.box.pegboard}},base));
space={kind:'pegboard',x:200,y:200,z:100,pegboard_standard:'skadis'};
const sk={box:{pegboard:{enabled:true,standard:'skadis'}}};
rules.push(aiSpaceViolation({box:{x:64,y:32,z:60,pegboard:sk.box.pegboard}},sk),
  aiSpaceViolation({box:{x:48,y:32,z:60,pegboard:sk.box.pegboard}},sk));
process.stdout.write(JSON.stringify({parsed,sessions,rules}));
""".replace("__ERROR__", error_class).replace("__SCHEMA__", schema).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["parsed"][:2], ["R", "R"])
        self.assertTrue(all(out["parsed"][2:]))
        self.assertEqual(out["sessions"][0], None)
        self.assertEqual(out["sessions"][1:], ["stale", "stale", "stale"])
        self.assertIsNone(out["rules"][0])
        self.assertTrue(all(out["rules"][1:4]))
        self.assertIsNone(out["rules"][4])
        self.assertTrue(all(out["rules"][5:8]))  # missing mount, changed cleat, Standard below 48 mm tall
        self.assertIsNone(out["rules"][8])
        self.assertTrue(out["rules"][9])  # SKÅDIS below 56 mm wide

    def test_ai_help_explicit_adoption_preserves_or_creates_identity_without_rebuild(self):
        source = "\n".join(function_source(name, APP) for name in (
            "aiIdentityKey", "aiSpaceContext", "aiTypedSpaceActive", "aiResolveCandidateName",
            "aiInstallCandidate", "aiProveCandidate", "aiCheckSession"))
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        script = r"""
__ERROR__
const clone=v=>JSON.parse(JSON.stringify(v)),events=[],previewClientId='C';
const old={part_name:'Lipstick',box:{x:16},marker:'old',layout:{features:[]}},
  proven={part_name:'Lipstick',marker:'ai',box:{x:32},layout:{features:[]}};
const state={folderMode:'space',activeSpace:{kind:'drawer',x:80,y:80,z:50},activeSpaceId:'S',
  designInventoryId:'B1',design:old,cleanDesign:old,previewRequest:0};
const DL={active:true,layout:{},bins:[{id:'B1',name:'Lipstick'},{id:'B2',name:'Lipstick (2)'}]};
const aiHelp={generation:0};let fullPreviewStarts=0,unsaved=false,confirmed=true,next={problems:[]};
const aiContextKey=()=>'K',aiSetStatus=()=>{},typedSpaceOrdinaryBin=()=>true;
const withDeferredDraftSwitch=action=>action({}),beginDesignMutation=()=>true,finishDesignMutation=()=>{};
const resetNestPhotoSession=()=>{},bindLidMemoryForDesign=()=>{},syncForm=()=>{},clearDraftSelection=()=>{};
const DP={setMode:()=>{}},activatePreviewView=()=>{},freshDesignForCurrentFolder=()=>({marker:'starter'});
const flushSpaceDesignAutosave=async()=>{events.push('flush');return true};
const designHasChanges=()=>unsaved,appConfirmAction=async()=>confirmed;
const invalidatePendingPreview=()=>{state.previewRequest+=1;events.push('invalidate')};
const adoptPreviewResult=r=>{state.preview=r;state.design=r.design;events.push('adopt')};
const persistSpaceDesignSource=async(_c,force)=>{events.push('persist:'+force)};
const refreshPreview=()=>events.push('REBUILD');
const aiSpaceViolation=()=>null;
const api=async path=>{events.push('api:'+path);return next};
__FUNCTIONS__
const candidate=()=>({design:clone(proven),preview:{design:clone(proven),fits:true}});
const session=()=>({request_id:'R',context_fingerprint:'F',baseline:old,
  contextKey:JSON.stringify({identity:aiIdentityKey()})});
(async()=>{
  const run=async mode=>{
    events.length=0;state.design=clone(old);state.designInventoryId='B1';
    const ok=await aiInstallCandidate(candidate(),session(),mode);
    return {ok,marker:state.design.marker,id:state.designInventoryId,name:state.design.part_name,events:[...events],
      previews:fullPreviewStarts,clean:state.cleanDesign.marker};
  };
  const reuse=await run('modify'), fresh=await run('new');
  unsaved=true;confirmed=false;state.activeSpace=state.activeSpace;
  const noSpace=(state.folderMode='design',state.activeSpace=null,state.activeSpaceId=null,
    await (async()=>{events.length=0;state.design=clone(old);const ok=await aiInstallCandidate(candidate(),
      {request_id:'R',context_fingerprint:'F',baseline:old,contextKey:JSON.stringify({identity:aiIdentityKey()})},'new');
      return {ok,marker:state.design.marker,events:[...events]}})());
  state.folderMode='space';state.activeSpace={kind:'drawer',x:80,y:80,z:50};state.activeSpaceId='S';
  state.design=clone(old);events.length=0;next={problems:['post: does not fit'],design:proven};
  let refusal=null;
  try{await aiProveCandidate({design:{},request_id:'R',context_fingerprint:'F'},{...session(),contextKey:'K'})}
  catch(e){refusal=e.message}
  const stale=await(async()=>{state.design=clone(old);const bound=session();state.activeSpaceId='OTHER';
    try{await aiInstallCandidate(candidate(),bound,'modify');return null}catch(e){return e.stale}})();
  process.stdout.write(JSON.stringify({reuse,fresh,noSpace,refusal,marker:state.design.marker,stale}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__ERROR__", error_class).replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual((out["reuse"]["previews"], out["fresh"]["previews"]), (1, 2))  # one owner claim each
        # Modify keeps its row and nonblank name; New uses the first free suffix.
        self.assertEqual((out["reuse"]["ok"], out["reuse"]["marker"], out["reuse"]["id"]), (True, "ai", "B1"))
        self.assertEqual(out["reuse"]["name"], "Lipstick")
        self.assertEqual(out["reuse"]["events"], ["invalidate", "adopt", "persist:true"])
        # Remembered Space defaults follow ordinary edit rules: a reused bin keeps its own
        # clean baseline; a new AI bin starts from the unedited starter, never the candidate.
        self.assertEqual((out["reuse"]["clean"], out["fresh"]["clean"]), ("old", "starter"))
        # Meaningful bin: saved first, then the AI result is a brand-new bin.
        self.assertEqual((out["fresh"]["ok"], out["fresh"]["marker"], out["fresh"]["id"]), (True, "ai", None))
        self.assertEqual(out["fresh"]["name"], "Lipstick (3)")
        self.assertEqual(out["fresh"]["events"], ["flush", "invalidate", "adopt", "persist:true"])
        for one in (out["reuse"], out["fresh"]):
            self.assertNotIn("REBUILD", one["events"])
        # Declining the Design-folder discard prompt changes nothing.
        self.assertEqual(out["noSpace"], {"ok": False, "marker": "old", "events": []})
        # A candidate with problems is refused before any state or preview owner is touched.
        self.assertIn("could not build", out["refusal"])
        self.assertEqual(out["marker"], "old")
        # A different Space at install time is stale, never applied.
        self.assertTrue(out["stale"])

    def test_ai_help_prompt_covers_committed_draft_and_only_answer_defects_are_repairable(self):
        error_class = APP[APP.index("class AiHelpError"):APP.index("\n}\n", APP.index("class AiHelpError")) + 3]
        source = "\n".join(function_source(name, APP) for name in (
            "aiGeneratePrompt", "aiProcessResponse", "aiProveCandidate", "aiParseEnvelope", "aiCheckSession",
            "friendlyError"))
        schema = re.search(r'const AI_SCHEMA = "([^"]+)"', APP).group(1)
        script = r"""
__ERROR__
const AI_SCHEMA='__SCHEMA__',clone=v=>JSON.parse(JSON.stringify(v)),previewClientId='C';
const statuses=[],sent=[],events=[];let refuse=false,answer='',mode='';
const state={design:{part_name:'',layout:{features:[]}}};
const aiHelp={session:null,busy:false,generation:0,failure:null,generatedFor:null};
const $=selector=>({value:selector==='#ai-help-description'?'A tray':answer,close:()=>events.push('close')});
const aiSetBusy=b=>{aiHelp.busy=b},aiUpdateGenerateAvailability=()=>{},
  aiSetStatus=(m,o={})=>statuses.push({m,repair:Boolean(o.repair)});
const aiShowPrompt=()=>{},toast=()=>{},isStructuralDesign=()=>false,aiCompositionEmpty=d=>!d.layout.features.length;
const aiSpaceContext=()=>null,aiExistingBinNames=()=>['Existing'],aiRecordRecentDescription=()=>{},
  aiContextKey=()=>'K',visibleDesignSnapshot=()=>clone(state.design);
const designTargetIsStructural=()=>false;
const withDeferredDraftSwitch=async(action,refused)=>{
  events.push('guard');if(refuse)return refused;
  state.design.layout.features.push({kind:'post'});events.push('committed');return action({});};
const api=async(path,body)=>{
  if(path==='/api/ai/prompt'){sent.push(clone(body));return{request_id:'R',context_fingerprint:'F',prompt:'P'};}
  if(mode==='400')throw Object.assign(new Error('bad design'),{status:400});
  if(mode==='500')throw Object.assign(new Error('boom'),{status:500});
  if(mode==='network')throw new TypeError('Failed to fetch');
  return{problems:[],design:{},preview:{}};};
const aiSpaceViolation=()=>null;
let installError=null,installResult=true;
const aiInstallCandidate=async()=>{if(installError)throw installError;return installResult;};
__FUNCTIONS__
const envelope=JSON.stringify({schema:AI_SCHEMA,request_id:'R',context_fingerprint:'F',assumptions:[],design:{box:{}}});
(async()=>{
  await aiGeneratePrompt();
  const prompt={features:sent[0].design.layout.features.length,order:[...events],session:Boolean(aiHelp.session),
    names:sent[0].design.part_name,existing:sent[0].existing_names,generatedFor:aiHelp.generatedFor};
  events.length=0;refuse=true;aiHelp.session=null;await aiGeneratePrompt();
  const refused={session:aiHelp.session,last:statuses.at(-1).m};refuse=false;
  await aiGeneratePrompt();
  const run=async(label,setup)=>{mode='';await aiGeneratePrompt();events.length=0;statuses.length=0;
    aiHelp.failure=null;installError=null;installResult=true;
    answer=envelope;setup();await aiProcessResponse('modify');
    const last=statuses.at(-1);return{label,repair:last.repair,failure:Boolean(aiHelp.failure),
      session:Boolean(aiHelp.session),generatedFor:aiHelp.generatedFor,closed:events.includes('close')};};
  const out=[];
  out.push(await run('junk',()=>{answer='not json';}));
  out.push(await run('ok',()=>{}));
  out.push(await run('rejected',()=>{mode='400';}));
  out.push(await run('service',()=>{mode='500';}));
  out.push(await run('network',()=>{mode='network';}));
  out.push(await run('applyFailed',()=>{installError=new AiHelpError('x',{operational:true,applied:true});}));
  out.push(await run('unexpected',()=>{installError=new Error('kaboom');}));
  out.push(await run('stale',()=>{installError=new AiHelpError('old',{stale:true});}));
  process.stdout.write(JSON.stringify({prompt,refused,out}));
})().catch(e=>{console.error(e);process.exit(1)});
""".replace("__ERROR__", error_class).replace("__SCHEMA__", schema).replace("__FUNCTIONS__", source)
        out = node_json(script)
        # The prompt is written from the design AFTER a meaningful draft was committed.
        self.assertEqual(out["prompt"], {"features": 1, "order": ["guard", "committed"],
                                          "session": True, "names": "", "existing": ["Existing"],
                                          "generatedFor": "A tray"})
        self.assertEqual(out["refused"]["session"], None)
        self.assertIn("Finish or discard", out["refused"]["last"])
        by = {one["label"]: one for one in out["out"]}
        # Only a defect in the answer itself is handed back to the AI.
        for label in ("junk", "rejected"):
            self.assertEqual((by[label]["repair"], by[label]["failure"]), (True, True), label)
        for label in ("service", "network", "applyFailed", "unexpected", "stale"):
            self.assertEqual((by[label]["repair"], by[label]["failure"]), (False, False), label)
        self.assertFalse(by["applyFailed"]["session"])  # applied: the old prompt is spent
        self.assertIsNone(by["stale"]["generatedFor"])  # same description can regenerate
        self.assertTrue(by["ok"]["closed"])

    def test_ai_help_context_key_covers_bin_name_and_draft(self):
        source = "\n".join(function_source(name, APP) for name in ("aiContextKey", "aiIdentityKey", "aiSpaceContext"))
        script = r"""
const state={folderMode:'space',activeSpaceId:'S',designInventoryId:'B1',activeSpace:{kind:'drawer',x:80,y:80,z:50}};
let design={part_name:'Tray',box:{x:16}},draft=null;
const visibleDesignSnapshot=()=>JSON.parse(JSON.stringify(design)),isStructuralDesign=()=>false;
const draftNeedsSaving=()=>Boolean(draft);state.draft=null;
const pegboardProductMinimums=()=>({x:0,z:48});
__FUNCTIONS__
const keys=[aiContextKey()];
design={part_name:'Renamed',box:{x:16}};keys.push(aiContextKey());
design={part_name:'Tray',box:{x:24}};keys.push(aiContextKey());
design={part_name:'Tray',box:{x:16}};draft=true;state.draft={kind:'post'};keys.push(aiContextKey());
draft=null;state.draft=null;state.designInventoryId='B2';keys.push(aiContextKey());
process.stdout.write(JSON.stringify({distinct:new Set(keys).size}));
""".replace("__FUNCTIONS__", source)
        out = node_json(script)
        self.assertEqual(out["distinct"], 5)  # name, size, open draft and bin identity each change the key

    def test_ai_help_ui_is_wired_without_a_provider_and_dictation_is_optional(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        actions = html[html.index('id="bin-actions"'):html.index('id="stack-note"')]
        self.assertIn('id="designer-duplicate"', actions)
        # Fix 081 B: AI Design now lives in the same Bin Actions group as
        # New Bin / Duplicate Bin, not inside the Options section.
        self.assertIn('id="ai-help-open"', actions)
        self.assertRegex(html, r'<button[^>]*id="ai-help-dictate"[^>]*\shidden')
        # Product name is "AI Design"; internal ai-help-* IDs are implementation detail only.
        dialog = html[html.index('id="ai-help-dialog"'):html.index('</dialog>', html.index('id="ai-help-dialog"'))]
        self.assertIn("AI Design", html[html.index('id="ai-help-open"'):html.index("</button>", html.index('id="ai-help-open"'))])
        self.assertIn(">AI Design<", dialog)
        self.assertNotIn("AI Help", dialog)
        section = APP[APP.index("// ------------------------------------------------------------ AI Help (Fix 073)"):
                      APP.index("// New Bin (B1)")]
        self.assertNotIn("fetch(", section)
        self.assertEqual(sorted(set(re.findall(r'api\("(/[^"]+)"', section))),
                         ["/api/ai/candidate", "/api/ai/prompt", "/api/ai/repair-prompt"])
        script = "\n".join([function_source("aiSpeechRecognitionClass", APP), r"""
const none=aiSpeechRecognitionClass({}),moz=aiSpeechRecognitionClass({SpeechRecognition:'A'}),
  webkit=aiSpeechRecognitionClass({webkitSpeechRecognition:'B'});
process.stdout.write(JSON.stringify({none,moz,webkit}));"""])
        self.assertEqual(node_json(script), {"none": None, "moz": "A", "webkit": "B"})



if __name__ == "__main__":
    unittest.main()
