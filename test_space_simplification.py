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
from space_source import spaces_source

from test_space_preferences import node_run

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
        self.assertIn("Generated files owned only by this bin", out["seen"][0])
        self.assertNotIn("Dragging", out["seen"][0])
        self.assertNotIn("file stays", out["seen"][0])
        self.assertEqual(out["seen"][1], {"delete_ids": ["B1"]})

    def test_cancel_and_bulk_delete_copy(self):
        out = run_node(r"""
setLayout([bin("B1"), bin("B2")]);
DP.printSelected = new Set(["B1", "B2"]);
const messages = [];
ctx.appConfirmAction = async options => { messages.push(options.message); return false; };
await DP.deleteRow(DL.bin("B1"));
await DP.deleteSelected();
out.messages = messages;
out.calls = calls;
""")
        self.assertEqual(len(out["messages"]), 2)
        self.assertIn("Generated files owned only by these bins", out["messages"][1])
        self.assertFalse(any(call.get("path") == "/api/drawer/save" for call in out["calls"]))

    def test_open_designer_row_clears_identity_only_after_delete_succeeds(self):
        out = run_node(r"""
setLayout([bin("B1")]);
ctx.state.designInventoryId = "B1";
ctx.state.design = { box: {} };
DL.selectedRow = "B1";
DP.printSelected.add("B1");
const modes = [];
DP.setMode = mode => modes.push(mode);
DL.editBins = async () => false;
await DP.deleteRow(DL.bin("B1"));
out.failed = { identity: ctx.state.designInventoryId,
  selected: DP.printSelected.has("B1"), mode: [...modes] };
DL.editBins = async () => true;
await DP.deleteRow(DL.bin("B1"));
out.saved = { identity: ctx.state.designInventoryId,
  selected: DP.printSelected.has("B1"), mode: [...modes] };
""")
        self.assertEqual(out["failed"], {"identity": "B1", "selected": True, "mode": []})
        self.assertEqual(out["saved"], {"identity": None, "selected": False,
                                        "mode": ["space"]})

    def test_hosted_delete_writes_inventory_then_removes_exact_files_and_reports_failure(self):
        source = spaces_source(WEB)
        request = source[source.index("SP.writeHostedFileSet = async"):source.index("// Fix 034 F1", source.index("SP.inventoryRequest = async"))]
        script = r"""
const events = [], oldFolder = { handle: {}, name: "Old" }, newFolder = { handle: {}, name: "New" };
const state = { browserFolder: oldFolder, activeSpace: { name: "Old" } };
const DL = { spaceContextCurrent: () => true,
  staleSpaceError: () => Object.assign(new Error("stale"), { code: "STALE_SPACE_CONTEXT" }) };
const SP = { _inventoryWriteChain: Promise.resolve(), readInventoryFor: async () => "before" };
const WFFileSystem = {
  listFilenames: async () => ["Owned.3mf", "Other.3mf"],
  writeText: async (_handle, _name, text) => { events.push(["write", text]); },
  removeFile: async (_handle, name) => { events.push(["remove", name]); throw new Error("locked"); },
};
const INVENTORY_FILENAME = "Wavefinity bins.md";
const api = async (_path, payload) => {
  events.push(["api", payload.available_filenames]);
  return { inventory_text: "after", cleanup_files: ["Owned.3mf"] };
};
""" + request + r"""
(async () => {
  const result = await SP.inventoryRequest("/api/drawer/save", { delete_ids: ["B1"] }, { context: {} });
  const first = { events: [...events], failed: result.cleanup_failed };
  events.length = 0;
  WFFileSystem.writeText = async () => { events.push(["write"]); state.browserFolder = newFolder; };
  try { await SP.inventoryRequest("/api/drawer/save", { delete_ids: ["B1"] }, { context: {} }); }
  catch (error) { events.push(["error", error.code]); }
  process.stdout.write(JSON.stringify({ first, switched: events }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        out = node_run(script)
        self.assertEqual(out["first"]["events"], [
            ["api", ["Owned.3mf", "Other.3mf"]], ["write", "after"], ["remove", "Owned.3mf"]])
        self.assertEqual(out["first"]["failed"], ["Owned.3mf"])
        self.assertEqual(out["switched"], [
            ["api", ["Owned.3mf", "Other.3mf"]], ["write"], ["error", "STALE_SPACE_CONTEXT"]])

    def test_hosted_edit_snapshots_before_api_and_edit_then_delete_removes_old_file(self):
        source = spaces_source(WEB)
        request = source[source.index("SP.writeHostedFileSet = async"):source.index("// Fix 034 F1", source.index("SP.inventoryRequest = async"))]
        script = r"""
const events = [], folder = { handle: {}, name: "Space" }, next = { handle: {}, name: "Next" };
const state = { browserFolder: folder, activeSpace: { name: "Space" } };
const DL = { spaceContextCurrent: () => true,
  staleSpaceError: () => Object.assign(new Error("stale"), { code: "STALE_SPACE_CONTEXT" }) };
let text = "generated";
const SP = { _inventoryWriteChain: Promise.resolve(), readInventoryFor: async () => {
  events.push("read"); return text;
} };
const WFFileSystem = {
  listFilenames: async () => { events.push("list"); return ["Old.3mf", "Unrelated.3mf"]; },
  writeText: async (_handle, _name, value) => { events.push(["write", value]); text = value; },
  removeFile: async (_handle, name) => { events.push(["remove", name]); },
};
const INVENTORY_FILENAME = "Wavefinity bins.md";
const api = async (path, payload) => {
  events.push(["api", path, payload.inventory_text, payload.available_filenames]);
  return path === "/api/drawer/design-source/save" ? { inventory_text: "edited" }
    : { inventory_text: "deleted", cleanup_files: ["Old.3mf"] };
};
""" + request + r"""
(async () => {
  await SP.inventoryRequest("/api/drawer/design-source/save", {
    row_id: "B1", available_filenames: ["Spoofed.3mf"] }, { context: {} });
  await SP.inventoryRequest("/api/drawer/save", { delete_ids: ["B1"] }, { context: {} });
  const lifecycle = [...events];
  events.length = 0;
  WFFileSystem.listFilenames = async () => { events.push("list"); state.browserFolder = next; return ["Old.3mf"]; };
  try { await SP.inventoryRequest("/api/drawer/design-source/save", { row_id: "B1" }, { context: {} }); }
  catch (error) { events.push(["error", error.code]); }
  const switchedDuringList = [...events];
  events.length = 0; state.browserFolder = folder;
  SP.readInventoryFor = async () => { events.push("read"); state.browserFolder = next; return text; };
  try { await SP.inventoryRequest("/api/drawer/design-source/save", { row_id: "B1" }, { context: {} }); }
  catch (error) { events.push(["error", error.code]); }
  process.stdout.write(JSON.stringify({ lifecycle, switchedDuringList, switchedBeforeList: events }));
})().catch(error => { console.error(error); process.exit(1); });
"""
        out = node_run(script)
        self.assertEqual(out["lifecycle"], [
            "read", "list", ["api", "/api/drawer/design-source/save", "generated", ["Old.3mf", "Unrelated.3mf"]],
            ["write", "edited"], "read", "list",
            ["api", "/api/drawer/save", "edited", ["Old.3mf", "Unrelated.3mf"]],
            ["write", "deleted"], ["remove", "Old.3mf"]])
        self.assertEqual(out["switchedDuringList"], ["read", "list", ["error", "STALE_SPACE_CONTEXT"]])
        self.assertEqual(out["switchedBeforeList"], ["read", ["error", "STALE_SPACE_CONTEXT"]])


class ManualAddRemovalTests(unittest.TestCase):

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
const source = [...fs.readdirSync(process.argv[1] + "/spaces").filter(f => f.endsWith(".js")).sort().map(f => fs.readFileSync(process.argv[1] + "/spaces/" + f, "utf8")), fs.readFileSync(process.argv[1] + "/spaces.js", "utf8")].join("\n");
// Fix 112 split the Space code: the leave-editor guard now lives in an earlier module.
const leave = source.match(/SP\.confirmLeaveStructuralEditor = async \(\) => \{[\s\S]*?\n\};/)[0];
const slice = leave + "\n" + source.slice(source.indexOf("SP.structuralKind = "), source.indexOf("SP.renderSpaceInfo = "));
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



if __name__ == "__main__":
    unittest.main()
