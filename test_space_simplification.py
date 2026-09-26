"""Space simplification regressions (Fix 048C): one row = one placement, staging,
Inventory as the Space control, and the retired planning-engine concepts gone.

The browser modules run under Node against small stubs (no DOM, no server), the
same way the other browser-state regressions here do.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"


def _read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


HARNESS = r"""
const vm = require("vm"), fs = require("fs");
const web = process.argv[1];
const els = {};
const makeEl = () => ({
  innerHTML: "", textContent: "", value: "", checked: false, disabled: false, hidden: false,
  dataset: {}, style: {}, title: "", open: false, className: "",
  classList: { toggle() {}, add() {}, remove() {}, contains() { return false; } },
  addEventListener() {}, querySelector() { return null; }, querySelectorAll() { return []; },
  contains() { return false; }, closest() { return null; }, matches() { return false; },
  setAttribute() {}, getContext() { return null; }, insertAdjacentHTML() {}, scrollIntoView() {},
});
const known = ["#dl-inv-list", "#dl-inv-show", "#dl-inv-sort", "#dl-inv-count", "#dl-batch-tools",
  "#dl-batch-summary", "#dl-batch-connectors", "#dl-batch-delete", "#dl-batch-clear", "#dl-batch-print", "#dl-batch-save", "#dl-refresh-saved", "#dl-staging",
  "#dl-empty-state", "#dl-stats", "#dl-save-status"];
known.forEach(sel => { els[sel] = makeEl(); });
els["#dl-staging"].querySelector = sel => (els["#dl-staging"]._kids ||= {})[sel] ||= makeEl();
const toasts = [];
const calls = [];
const ctx = {
  console, Math, JSON, Number, String, Set, Map, Object, Array, Promise, Date, CSS: { escape: v => v },
  setTimeout: () => 0, clearTimeout() {},
  $: sel => els[sel] || null, $$: () => [],
  document: { activeElement: null, querySelector: () => null },
  localStorage: { getItem: () => null, setItem() {} },
  window: { addEventListener() {}, devicePixelRatio: 1 },
  requestAnimationFrame: f => f(), ResizeObserver: class { observe() {} }, MutationObserver: class { observe() {} },
  debounce: f => f, clone: v => JSON.parse(JSON.stringify(v)),
  fmt: v => (Math.round(Number(v) * 100) / 100).toString(),
  escapeHtml: v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
  toast: (message, isError) => toasts.push({ message, isError: Boolean(isError) }),
  api: async (path, body) => { calls.push({ path, body }); return {}; },
  state: { runtime: { hosted: false }, slicer: { available: true }, activeSpaceId: "S1", output: "C:/x", catalog: {} },
  drawerHardClearance: () => 2, appConfirmAction: async () => true, number: (v, f) => (Number.isFinite(Number(v)) ? Number(v) : f),
  normalizeBinDimension: (a, v) => Number(v), flushSpaceDesignAutosave: async () => { calls.push({ path: "flush" }); return true; },
  designerEditInventoryRow: id => calls.push({ path: "edit", id }), activatePreviewView: () => {}, DP_HOOK: null,
};
vm.createContext(ctx);
const load = (file, exports) => vm.runInContext(fs.readFileSync(web + "/" + file, "utf8") + `;this.${exports} = ${exports};`, ctx);
load("drawer-model.js", "DL");
load("drawer-view.js", "DV");
load("drawer-panel.js", "DP");
const { DL, DV, DP } = ctx;
DL.emit = () => {};
const bin = (id, o = {}) => ({ id, kind: "bin", name: id, x: 16, y: 16, z: 30, qty: 0, status: "in_design", stack: "none", file: "", ...o });
const drawer = (placements = []) => ({ id: "d1", name: "Drawer", width: 200, depth: 200, height: 60, boundary: "wall", placements });
const setLayout = (bins, placements = [], extra = {}) => {
  DL.bins = bins; DL.loaded = true; DL.active = true;
  DL.normaliseLayout({ version: 1, active: "d1", drawers: [drawer(placements)], design_specs: {}, ...extra });
};
const out = {};
"""


def run_node(body: str) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for this browser-state regression")
    script = (HARNESS + "\n(async () => {\n" + body + "\nprocess.stdout.write(JSON.stringify(out));\n})()"
              ".catch(error => { console.error(error && error.stack || error); process.exit(1); });")
    done = subprocess.run([node, "-e", script, str(WEB)], capture_output=True, text=True,
                          timeout=60, encoding="utf-8")
    if done.returncode != 0:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


class PlacementModelTests(unittest.TestCase):
    def test_ordinary_row_is_one_placement_and_legacy_copies_normalise_deterministically(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2"), bin("B3", { kind: "spacer", boundary: "" })], [
  { bin: "B1", copy: 2, gx: 4, gy: 0, locked: true },
  { bin: "B1", copy: 0, gx: 0, gy: 0 },
  { bin: "B1", copy: 1, gx: 8, gy: 0 },
  { bin: "B2", copy: 3, gx: 2, gy: 6 },
  { bin: "B2", copy: 1, on: "B1:2" },
  { bin: "B3", copy: 0, gx: 20, gy: 20 },
  { bin: "B3", copy: 1, gx: 22, gy: 20 },
]);
out.placements = DL.layout.drawers[0].placements.map(p => ({ ...p }));
out.autoGone = !("auto" in DL.layout.settings);
out.noLocked = DL.layout.drawers[0].placements.every(p => !("locked" in p));
// Same input again -> same result (deterministic).
const first = JSON.stringify(DL.layout.drawers[0].placements);
setLayout([bin("B1"), bin("B2"), bin("B3", { kind: "spacer", boundary: "" })], [
  { bin: "B1", copy: 2, gx: 4, gy: 0, locked: true },
  { bin: "B1", copy: 0, gx: 0, gy: 0 },
  { bin: "B1", copy: 1, gx: 8, gy: 0 },
  { bin: "B2", copy: 3, gx: 2, gy: 6 },
  { bin: "B2", copy: 1, on: "B1:2" },
  { bin: "B3", copy: 0, gx: 20, gy: 20 },
  { bin: "B3", copy: 1, gx: 22, gy: 20 },
]);
out.same = first === JSON.stringify(DL.layout.drawers[0].placements);
""")
        placements = out["placements"]
        b1 = [p for p in placements if p["bin"] == "B1"]
        b2 = [p for p in placements if p["bin"] == "B2"]
        b3 = [p for p in placements if p["bin"] == "B3"]
        self.assertEqual(len(b1), 1)
        self.assertEqual((b1[0]["copy"], b1[0]["gx"]), (0, 0))       # lowest copy wins, renumbered 0
        self.assertEqual(len(b2), 1)
        self.assertEqual(b2[0]["copy"], 0)
        self.assertEqual(len(b3), 2)                                    # spacers are exempt
        self.assertEqual(sorted(p["copy"] for p in b3), [0, 1])
        self.assertTrue(out["autoGone"])
        self.assertTrue(out["noLocked"])
        self.assertTrue(out["same"])

    def test_a_stack_closes_up_when_a_duplicate_placement_is_dropped(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2")], [
  { bin: "B1", copy: 0, gx: 0, gy: 0 },
  { bin: "B1", copy: 1, gx: 6, gy: 0 },
  { bin: "B2", copy: 0, on: "B1:1" },
]);
out.placements = DL.layout.drawers[0].placements.map(p => ({ ...p }));
""")
        by_bin = {p["bin"]: p for p in out["placements"]}
        self.assertEqual(len(out["placements"]), 2)
        self.assertEqual((by_bin["B2"]["gx"], by_bin["B2"]["gy"]), (6, 0))
        self.assertNotIn("on", by_bin["B2"])

    def test_staging_is_derived_from_unplaced_ordinary_rows_in_inventory_order(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2"), bin("B3", { kind: "spacer" }), bin("B4"), bin("B5", { kind: "manual" })],
  [{ bin: "B2", copy: 0, gx: 0, gy: 0 }]);
out.staged = DL.stagedBins().map(one => one.id);
DL.placeAt(DL.bin("B4"), { gx: 3, gy: 3 });
out.afterPlace = DL.stagedBins().map(one => one.id);
out.persisted = JSON.stringify(DL.layout).includes("staged");
out.negative = DL.layout.drawers[0].placements.some(p => p.gx < 0 || p.gy < 0);
""")
        self.assertEqual(out["staged"], ["B1", "B4", "B5"])
        self.assertEqual(out["afterPlace"], ["B1", "B5"])
        self.assertFalse(out["persisted"])
        self.assertFalse(out["negative"])

    def test_a_staged_row_places_once_and_never_twice(self):
        out = run_node(r"""
setLayout([bin("B1")]);
out.first = DL.placeAt(DL.bin("B1"), { gx: 0, gy: 0 });
out.second = DL.placeAt(DL.bin("B1"), { gx: 5, gy: 5 });
out.count = DL.layout.drawers[0].placements.length;
out.copy = DL.layout.drawers[0].placements[0].copy;
out.noLocked = !("locked" in DL.layout.drawers[0].placements[0]);
out.selectedRow = DL.selectedRow;
out.refusal = toasts.map(t => t.message);
""")
        self.assertTrue(out["first"])
        self.assertFalse(out["second"])
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["copy"], 0)
        self.assertTrue(out["noLocked"])
        self.assertEqual(out["selectedRow"], "B1")
        self.assertTrue(any("already placed" in message for message in out["refusal"]))

    def test_manual_fit_and_stacking_still_validate(self):
        out = run_node(r"""
setLayout([bin("B1", { stack: "direct", z: 20 }), bin("B2", { stack: "direct", z: 20 }), bin("B3", { x: 32, y: 32 })],
  [{ bin: "B1", copy: 0, gx: 0, gy: 0 }]);
out.overlap = DL.placeAt(DL.bin("B3"), { gx: 1, gy: 1 });
out.outside = DL.placeAt(DL.bin("B3"), { gx: 99, gy: 0 });
const target = DL.items()[0];
out.stacked = DL.placeAt(DL.bin("B2"), { target });
out.stackedOn = DL.layout.drawers[0].placements.find(p => p.bin === "B2").on;
out.fits = DL.fitsAt(DL.drawer(), [DL.bin("B3")], 4, 4).ok;
""")
        self.assertFalse(out["overlap"])
        self.assertFalse(out["outside"])
        self.assertTrue(out["stacked"])
        self.assertEqual(out["stackedOn"], "B1:0")
        self.assertTrue(out["fits"])

    def test_dragging_out_unplaces_without_deleting_the_row(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2", { stack: "direct" }), bin("B3", { stack: "direct" })], [
  { bin: "B1", copy: 0, gx: 0, gy: 0 },
  { bin: "B2", copy: 0, gx: 4, gy: 0 },
  { bin: "B3", copy: 0, on: "B2:0" },
]);
DL.selectPlacement("B2:0");
const taken = DL.takeOut("B2:0");
out.taken = taken;
out.rows = DL.bins.map(one => one.id);
out.placed = DL.layout.drawers[0].placements.map(p => p.bin);
out.staged = DL.stagedBins().map(one => one.id);
out.selected = DL.selected;
""")
        self.assertEqual(out["taken"], 2)
        self.assertEqual(out["rows"], ["B1", "B2", "B3"])
        self.assertEqual(out["placed"], ["B1"])
        self.assertEqual(out["staged"], ["B2", "B3"])
        self.assertIsNone(out["selected"])

    def test_move_and_detach_carry_no_lock_field(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2")], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }]);
DL.moveTo("B1:0", { gx: 6, gy: 0 });
out.moved = { ...DL.layout.drawers[0].placements[0] };
DL.removePlacement("B1:0");
out.left = DL.layout.drawers[0].placements.length;
""")
        self.assertEqual((out["moved"]["gx"], out["moved"]["gy"]), (6, 0))
        self.assertNotIn("locked", out["moved"])
        self.assertEqual(out["left"], 0)

    def test_print_need_comes_from_status_not_qty_or_placement(self):
        out = run_node(r"""
setLayout([bin("B1", { file: "a.3mf", status: "saved" }), bin("B2", { file: "b.3mf", status: "printed", qty: 1 }),
           bin("B3", { status: "in_design" })], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }]);
DL.layout.design_specs = { B3: { box: {} } };
out.needed = DL.bins.map(one => DL.printNeeded(one));
out.count = DL.bins.map(one => DL.printCount(one));
out.labels = DL.bins.map(one => DL.statusLabel(one));
""")
        self.assertEqual(out["needed"], [1, 0, 1])
        self.assertEqual(out["count"], [1, 1, 1])
        self.assertEqual(out["labels"], ["Saved", "Printed", "In Design"])

    def test_selection_is_bidirectional_between_canvas_rows_and_staging(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2")], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }]);
DL.selectPlacement("B1:0");
out.fromCanvas = [DL.selectedRow, DL.selected];
DL.selectRow("B2");
out.stagedRow = [DL.selectedRow, DL.selected];
DL.selectRow("B1");
out.placedRow = [DL.selectedRow, DL.selected];
DL.selectPlacement(null);
out.cleared = [DL.selectedRow, DL.selected];
""")
        self.assertEqual(out["fromCanvas"], ["B1", "B1:0"])
        self.assertEqual(out["stagedRow"], ["B2", None])
        self.assertEqual(out["placedRow"], ["B1", "B1:0"])
        self.assertEqual(out["cleared"], [None, None])

    def test_spacer_repeated_counts_still_work(self):
        out = run_node(r"""
setLayout([bin("S1", { kind: "spacer", boundary: "", qty: 1, name: "Rigid Spacer", file: "s.3mf" })], [
  { bin: "S1", copy: 0, gx: 0, gy: 0 }, { bin: "S1", copy: 1, gx: 2, gy: 0 }, { bin: "S1", copy: 2, gx: 4, gy: 0 },
]);
const groups = DL.spacerPrintGroups();
out.qty = groups[0].qty; out.printed = groups[0].printed; out.toPrint = groups[0].toPrint;
DL.placeAt(DL.bin("S1"), { gx: 6, gy: 0 });
out.spacerCopies = DL.layout.drawers[0].placements.map(p => p.copy);
out.staged = DL.stagedBins().length;
""")
        self.assertEqual((out["qty"], out["printed"], out["toPrint"]), (3, 1, 2))
        self.assertEqual(out["spacerCopies"], [0, 1, 2, 3])
        self.assertEqual(out["staged"], 0)


class SurfaceFillTests(unittest.TestCase):
    def test_fill_settles_the_designer_autosave_and_aborts_when_it_fails(self):
        out = run_node(r"""
ctx.state.activeSpaceId = "S1";
setLayout([bin("B1")]);
DL.layout.space = { kind: "surface" };
DL.inventoryCall = async (path) => { calls.push({ path }); return { candidates: [{ id: "c1", gx: 0, gy: 0, w: 1, d: 1, x_mm: 8, y_mm: 8 }], signature: "sig" }; };
DL.save = async () => { calls.push({ path: "save" }); return true; };
await DL.planSurfaceFill();
out.ok = calls.map(c => c.path);
calls.length = 0;
ctx.flushSpaceDesignAutosave = async () => { calls.push({ path: "flush-fail" }); return false; };
await DL.planSurfaceFill();
out.failed = calls.map(c => c.path);
""")
        self.assertEqual(out["ok"][:2], ["flush", "save"])
        self.assertIn("/api/drawer/surface-fill", out["ok"])
        self.assertEqual(out["failed"], ["flush-fail"])
        model = _read("drawer-model.js")
        self.assertNotIn("Current design", model)
        self.assertIn("flushSpaceDesignAutosave", model[model.index("DL.planSurfaceFill"):model.index("DL.toggleFillCandidate")])


class InventoryRowRenderingTests(unittest.TestCase):
    def test_ordinary_rows_show_status_and_actions_but_no_qty_or_planned_math(self):
        out = run_node(r"""
const specs = { B1: { box: {} }, B2: { box: {} }, B3: { box: {} } };
setLayout([bin("B1", { status: "in_design" }), bin("B2", { status: "saved", file: "b.3mf" }),
           bin("B3", { status: "printed", qty: 1, file: "c.3mf" }), bin("M1", { kind: "manual", status: "printed", qty: 1 })],
  [{ bin: "B2", copy: 0, gx: 0, gy: 0 }], { design_specs: specs });
DP.printSelected = new Set(["B1"]);
DP.renderInventory(true);
out.html = els["#dl-inv-list"].innerHTML;
out.clearDisabled = els["#dl-batch-clear"].disabled;
DP.printSelected = new Set();
DP.renderBatch();
out.clearDisabledWhenEmpty = els["#dl-batch-clear"].disabled;
""")
        html = out["html"]
        rows = re.split(r'(?=<div class="dl-bin )', html)[1:]
        self.assertEqual(len(rows), 4)
        for row in rows:
            labels = [label for label in ("In Design", "Saved", "Printed") if f"{label}</small>" in row]
            self.assertEqual(len(labels), 1, row)
            self.assertTrue("Placed" in row or "Unplaced" in row)
        for retired in ("data-act=\"qty", "dl-qty", "dl-placed", "planned", "needed", "Qty", "placed copies"):
            self.assertNotIn(retired, html)
        first = rows[0]
        for action in ("Edit", "Duplicate", "Mark Printed", "Delete"):
            self.assertIn(f">{action}<", first)
        self.assertIn(">Mark Not Printed<", rows[2])
        self.assertNotIn(">Mark Printed<", rows[2])
        self.assertNotIn(">Edit<", rows[3])                # a hand-added row has no design source
        self.assertIn('data-print-select="B1"', html)
        self.assertFalse(out["clearDisabled"])
        self.assertTrue(out["clearDisabledWhenEmpty"])

    def test_only_unplaced_ordinary_rows_are_draggable_and_actions_use_the_status_owner(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2")], [{ bin: "B2", copy: 0, gx: 0, gy: 0 }], { design_specs: { B1: {}, B2: {} } });
DP.renderInventory(true);
out.html = els["#dl-inv-list"].innerHTML;
const calls2 = [];
DL.setBinPrinted = async (one, printed) => { calls2.push([one.id, printed]); return true; };
DL.printSelectedBins = (selection, includeConnectors) => calls2.push(["print", selection, includeConnectors]);
const event = act => ({ target: { closest: sel => sel === "[data-bin]" ? { dataset: { bin: "B1" } } : sel === "[data-act]" ? { dataset: { act } } : null } });
await DP.onInventoryClick(event("printed"));
await DP.onInventoryClick(event("not-printed"));
await DP.onInventoryClick(event("print"));
await DP.onInventoryClick(event("edit"));
out.actions = calls2;
out.calls = calls;
""")
        rows = re.split(r'(?=<div class="dl-bin )', out["html"])[1:]
        self.assertIn('draggable="true"', rows[0])
        self.assertIn('draggable="false"', rows[1])
        self.assertEqual(out["actions"][:2], [["B1", True], ["B1", False]])
        self.assertEqual(out["actions"][2], ["print", {"B1": 1}, False])   # each row exactly once
        self.assertTrue(any(call.get("path") == "edit" for call in out["calls"]))

    def test_duplicate_stays_in_space_adopts_the_returned_inventory_and_stages_the_new_row(self):
        out = run_node(r"""
setLayout([bin("B1", { name: "Tray" })], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }], { design_specs: { B1: { box: {} } } });
DL.inventoryCall = async (path, payload) => {
  calls.push({ path, payload });
  return { row_id: "B2", bins: [...DL.bins, bin("B2", { name: "Tray (2)", status: "in_design" })],
           layout: { design_specs: { B1: { box: {} }, B2: { box: {} } } } };
};
await DP.duplicateRow(DL.bin("B1"));
out.staged = DL.stagedBins().map(one => [one.id, one.name, one.status]);
out.placements = DL.layout.drawers[0].placements.length;
out.selectedRow = DL.selectedRow;
out.path = calls.map(c => c.path);
""")
        self.assertEqual(out["staged"], [["B2", "Tray (2)", "in_design"]])
        self.assertEqual(out["placements"], 1)
        self.assertEqual(out["selectedRow"], "B2")
        self.assertIn("/api/drawer/design-source/duplicate", out["path"])

    def test_delete_confirms_and_removes_through_the_inventory_owner(self):
        out = run_node(r"""
setLayout([bin("B1")], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }], { design_specs: { B1: {} } });
const seen = [];
DL.editBins = async changes => { seen.push(changes); return true; };
ctx.appConfirmAction = async options => { seen.push(options.message); return true; };
await DP.deleteRow(DL.bin("B1"));
out.seen = seen;
""")
        self.assertIn("placement is removed too", out["seen"][0])
        self.assertEqual(out["seen"][1], {"delete_ids": ["B1"]})


class StagingRailRenderingTests(unittest.TestCase):
    def test_rail_lists_unplaced_bins_and_updates_when_a_bin_is_placed(self):
        out = run_node(r"""
setLayout([bin("B1", { name: "Alpha" }), bin("B2", { name: "Beta" })]);
DV.renderStaging();
const list = els["#dl-staging"]._kids[".dl-staging-list"];
out.before = list.innerHTML;
out.count = els["#dl-staging"]._kids[".dl-staging-count"].textContent;
DL.placeAt(DL.bin("B1"), { gx: 0, gy: 0 });
DV.renderStaging();
out.after = list.innerHTML;
out.countAfter = els["#dl-staging"]._kids[".dl-staging-count"].textContent;
""")
        self.assertIn('data-staged-bin="B1"', out["before"])
        self.assertIn('data-staged-bin="B2"', out["before"])
        self.assertEqual(out["count"], "2")
        self.assertNotIn('data-staged-bin="B1"', out["after"])
        self.assertIn('data-staged-bin="B2"', out["after"])
        self.assertEqual(out["countAfter"], "1")


class ManualAddRemovalTests(unittest.TestCase):
    def test_manual_add_creation_ui_and_wiring_are_gone(self):
        panel = _read("drawer-panel.js")
        view = _read("drawer-view.js")
        app = _read("app.js")
        for name in ("Add a bin by hand", "Add an existing bin", "dl-add", "focusManualAdd",
                     "wireManualDimension", 'data-empty-act="add"', 'act === "add"', "by hand below"):
            self.assertNotIn(name, panel + view, name)
        self.assertNotIn("baseThickness", panel + app)
        self.assertNotIn("Add a bin by hand", app)
        self.assertIn('data-empty-act="design"', view)

    def test_a_legacy_manual_row_still_loads_stages_places_and_is_manageable(self):
        out = run_node(r"""
setLayout([bin("M1", { kind: "manual", name: "Old tray", qty: 1, status: "printed" })]);
out.staged = DL.stagedBins().map(one => one.id);
out.placed = DL.placeAt(DL.bin("M1"), { gx: 2, gy: 2 });
out.after = DL.stagedBins().length;
DL.selectPlacement("M1:0");
DL.takeOut("M1:0");
out.unplaced = DL.stagedBins().map(one => one.id);
DP.renderInventory(true);
out.html = els["#dl-inv-list"].innerHTML;
""")
        self.assertEqual(out["staged"], ["M1"])
        self.assertTrue(out["placed"])
        self.assertEqual(out["after"], 0)
        self.assertEqual(out["unplaced"], ["M1"])
        html = out["html"]
        self.assertIn("Added by hand", html)
        self.assertIn(">Mark Not Printed<", html)
        self.assertIn(">Delete<", html)
        self.assertNotIn(">Edit<", html)


class HostedStructuralPrintTests(unittest.TestCase):
    SCRIPT = r"""
const fs = require("fs");
const source = fs.readFileSync(process.argv[1] + "/spaces.js", "utf8");
const slice = source.slice(source.indexOf("SP.structuralKind = "), source.indexOf("SP.renderSpaceInfo = "));
const calls = [], toasts = [], els = {};
const el = () => ({ hidden: false, disabled: false, textContent: "", title: "", value: "256" });
["space-structural", "space-structural-save", "space-structural-print", "space-structural-bed",
 "space-structural-bed-x", "space-structural-bed-y"].forEach(id => { els[id] = el(); });
const run = async (hosted) => {
  calls.length = 0; toasts.length = 0;
  const state = { folderMode: "space", activeSpace: { kind: "portable", name: "Case", x: 96, y: 96, z: 40 },
    runtime: { hosted }, browserFolder: { name: "f" }, output: "C:/x", slicer: { available: true, name: "Bambu Studio" } };
  const SP = { renderSpaceInfo() {} };
  const DL = { spaceContext: () => ({}), requireSpaceContext() {}, isStaleSpaceError: () => false };
  const api = async (path, body) => { calls.push(path); return { output: "C:/x", files: [] }; };
  const saveGeneratedFiles = async () => ["a.3mf"];
  const toast = (m, e) => toasts.push(m);
  const document = { getElementById: id => els[id] || null };
  const clone = v => JSON.parse(JSON.stringify(v));
  const fn = new Function("SP", "state", "DL", "api", "saveGeneratedFiles", "toast", "document", "clone",
    slice + "; return SP;");
  const sp = fn(SP, state, DL, api, saveGeneratedFiles, toast, document, clone);
  sp.renderStructuralActions();
  const view = { disabled: els["space-structural-print"].disabled, title: els["space-structural-print"].title,
    label: els["space-structural-print"].textContent, saveDisabled: els["space-structural-save"].disabled };
  await sp.runStructural("print");
  const afterPrint = [...calls];
  await sp.runStructural("save");
  return { view, afterPrint, afterSave: [...calls], toasts: [...toasts] };
};
(async () => {
  process.stdout.write(JSON.stringify({ hosted: await run(true), local: await run(false) }));
})();
"""

    def test_hosted_print_is_disabled_and_local_print_still_hands_off_to_the_slicer(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required")
        done = subprocess.run([node, "-e", self.SCRIPT, str(WEB)], capture_output=True, text=True,
                              timeout=60, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        hosted, local = out["hosted"], out["local"]
        self.assertTrue(hosted["view"]["disabled"])
        self.assertFalse(hosted["view"]["saveDisabled"])
        self.assertEqual(hosted["view"]["label"], "Print Storage Box")
        self.assertIn("local Wavefinity", hosted["view"]["title"])
        self.assertEqual(hosted["afterPrint"], [])                       # Print never calls generate/save
        self.assertEqual(hosted["afterSave"], ["/api/space/structural-generate"])
        self.assertFalse(local["view"]["disabled"])
        self.assertEqual(local["afterPrint"], ["/api/space/structural-print"])

    def test_source_keeps_print_and_save_separate(self):
        spaces = _read("spaces.js")
        run = spaces[spaces.index("SP.runStructural = "):spaces.index("SP.saveStructural = ")]
        self.assertIn('mode === "print" && hosted', run)
        self.assertNotIn("&& !hosted;", run)


class RetiredConceptSourceTests(unittest.TestCase):
    def test_current_design_shadow_owner_is_gone(self):
        combined = "\n".join(_read(name) for name in ("app.js", "drawer-model.js", "drawer-panel.js", "drawer-view.js", "spaces.js"))
        for name in ("DL.working", "workingTicket", "refreshWorking", "workingFit", "workingContext",
                     "moveWorkingTo", "workingRow", "workingDesignForSpace", "markWorkingDesignPending",
                     "markWorkingDesignReconciled", "workingPending", "workingGeneratedKey"):
            self.assertNotIn(name, combined, name)

    def test_auto_layout_is_removed_not_hidden(self):
        combined = "\n".join(_read(name) for name in ("app.js", "drawer-model.js", "drawer-panel.js", "drawer-view.js"))
        html = _read("index.html")
        for name in ("runAuto", "applyCandidate", "quickPlace", "/api/drawer/auto", "dl-auto", "dl-candidates",
                     "DL.candidates", "candidateIndex", "keep_locked", "height_reach"):
            self.assertNotIn(name, combined, name)
        for name in ("dl-auto", "Auto layout", "Auto Layout"):
            self.assertNotIn(name, html, name)
        panel = _read("drawer-panel.js")
        self.assertNotIn('addEventListener("dblclick"', panel)
        self.assertNotIn("Auto layout", _read("drawer-view.js"))
        self.assertNotIn("Auto", _read("drawer.css").replace("autosave", ""))

    def test_lock_is_removed_everywhere_in_the_space_ui(self):
        combined = "\n".join(_read(name) for name in ("drawer-model.js", "drawer-panel.js", "drawer-view.js"))
        # Legacy `locked` input is only ever stripped, on normalization.
        stripped = "\n".join(line for line in combined.splitlines() if "retired: there is no Lock" not in line)
        for name in ("toggleLock", "🔒", "Unlock", "L locks", 'key === "l"', "drag.locked", ".locked",
                     "keep_locked", "placement.locked"):
            self.assertNotIn(name, stripped, name)
        self.assertIn("delete p.locked", combined)

    def test_print_map_and_the_selected_bin_card_are_removed(self):
        combined = "\n".join(_read(name) for name in ("app.js", "drawer-panel.js", "drawer-view.js"))
        css = _read("drawer.css")
        for name in ("printMap", "planImage", "renderSelection", "dl-selection", "dl-print-sheet",
                     "dl-printing", "Print map", 'key === "p"'):
            self.assertNotIn(name, combined, name)
            self.assertNotIn(name, css, name)
        self.assertNotIn("dl-map", _read("drawer-panel.js"))

    def test_designer_has_no_design_a_selector_or_type_switch(self):
        html = _read("index.html")
        app = _read("app.js")
        for name in ('id="bin-type"', "Design a:", "bin-type-base-trim", 'value="b4b"', 'value="base-trim"',
                     'id="b4b-panel"', 'id="base-trim-panel"', "base-trim-auto-size", "cross-type-warning"):
            self.assertNotIn(name, html, name)
        for name in ("changeBinType", "toggleB4B", "startBaseTrimFromSpace", "autoSizeBaseTrimFromSpace",
                     "syncBaseTrimOption", "binTypeFromDesign", '"#bin-type"', "makeBaseTrimDesign",
                     "crossTypeCheck"):
            self.assertNotIn(name, app, name)
        spaces = _read("spaces.js")
        for name in ("crossTypeCheck", "designPortable", "designSurface", "makeBaseTrimDesign", "toggleB4B"):
            self.assertNotIn(name, spaces, name)

    def test_the_designer_refuses_storage_box_and_base_trim_designs(self):
        app = _read("app.js")
        self.assertIn("function isStructuralDesign(design)", app)
        opened = app[app.index("async function openDesign(event)"):app.index("async function newDesign()")]
        self.assertIn("isStructuralDesign(result.design)", opened)
        edit = app[app.index("async function designerEditInventoryRow"):app.index("async function designerInstallInventorySpec")]
        self.assertIn("isStructuralDesign(spec)", edit)
        spaces = _read("spaces.js")
        self.assertIn("resumeIsStructural", spaces)

    def test_standalone_and_space_designer_still_start_ordinary_bins(self):
        spaces = _read("spaces.js")
        starter = spaces[spaces.index("SP.installSpaceStarterDesign = "):spaces.index("SP.initializeDesignForActiveSpace = ")]
        self.assertIn("freshDesignForCurrentFolder()", starter)
        self.assertNotIn("b4b", starter.lower())
        self.assertNotIn("trim", starter.lower())
        create = spaces[spaces.index("SP.create = "):spaces.index("SP.resetDesignSession")]
        self.assertIn("await loadFreshOrdinaryDesignForCurrentFolder();", create)

    def test_user_facing_portable_storage_wording_is_gone(self):
        for name in ("index.html", "spaces.js", "drawer-view.js", "drawer-panel.js", "app.js"):
            self.assertNotIn("Portable Storage", _read(name), name)
        spaces = _read("spaces.js")
        self.assertIn('label: "Storage Box"', spaces)
        self.assertNotIn("Pegboard Space</h3>", _read("index.html"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Portable Storage", readme)

    def test_spacers_render_below_inventory_and_are_collapsed_by_default(self):
        panel = _read("drawer-panel.js")
        self.assertLess(panel.index('aria-label="Inventory"'), panel.index('id="dl-spacers"'))
        details = re.search(r'<details id="dl-spacers"[^>]*>', panel).group(0)
        self.assertNotIn(" open", details)
        self.assertIn("Save Selected Spacers", panel)
        self.assertNotIn("Generate Selected Spacers", panel)
        self.assertNotIn("dl-base-trim", panel)
        self.assertNotIn("Make Base Trim", panel)

    def test_documentation_and_tutorial_describe_the_current_product_only(self):
        html = _read("index.html")
        tutorial = html[html.index('id="space-tutorial"'):html.index('id="space-form"')]
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in (tutorial, readme):
            for phrase in ("Save to Space", "Load from Space", "Current design pseudo", "planned copies",
                           "Auto layout", "Auto Layout", "Print map", "Portable Storage", "Qty 0"):
                self.assertNotIn(phrase, text, phrase)
        self.assertIn("Unplaced bins", tutorial)
        self.assertIn("Space header", tutorial)
        self.assertNotIn("Generate", tutorial)


class SpaceActionsMarkupTests(unittest.TestCase):
    def test_space_actions_group_and_labels(self):
        html = _read("index.html")
        head = html[html.index('id="space-actions"'):html.index('id="space-head-edit-host"')]
        for label in ("Space controls", ">Open Space…<", ">Edit Space<", ">Show Folder<", ">New Space<"):
            self.assertIn(label, head)
        for control in ("space-structural-save", "space-structural-print"):
            self.assertIn(control, head)
        self.assertNotIn("Next step", html)

    def test_structural_actions_are_space_owned_never_inventory(self):
        spaces = _read("spaces.js")
        panel = _read("drawer-panel.js")
        for text in ("Save Storage Box", "Save Base Trim", "Print Base Trim"):
            self.assertNotIn(text, panel)
        self.assertIn("/api/space/structural-generate", spaces)
        self.assertIn("/api/space/structural-print", spaces)
        run = spaces[spaces.index("SP.runStructural = "):spaces.index("SP.saveStructural = ")]
        self.assertIn("DL.requireSpaceContext(context)", run)
        self.assertNotIn("addInventoryBin", run)
        self.assertNotIn("/api/drawer/", run)
        render = spaces[spaces.index("SP.renderStructuralActions = "):spaces.index("SP.renderSpaceInfo = ")]
        self.assertIn("Save ${label}", render)
        self.assertIn("Print ${label}", render)

    def test_the_four_space_types_are_named_for_users(self):
        spaces = _read("spaces.js")
        kinds = spaces[spaces.index("const SP_KINDS = {"):spaces.index("const FOLDER_METADATA")]
        labels = re.findall(r'label: "([^"]+)"', kinds)
        self.assertEqual(sorted(set(labels)), ["Drawer", "Pegboard", "Storage Box", "Surface"])


if __name__ == "__main__":
    unittest.main()
