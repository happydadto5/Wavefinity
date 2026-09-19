"use strict";

// Drawer layout mode - data model, saving and undo.
//
// The inventory file ('Wavefinity bins.md' in the save location) is the single
// source of truth: bin rows come from it, and the layout (drawers, where each
// copy sits, settings) is saved back into it. Bin rows are edited on the
// server by id, so a bin generated while this view is open is never lost.
//
// A placement is on the grid (gx/gy in 8 mm units, halves allowed on a 4 mm
// drawer), stacked (`on` names the placement below), or a free edge-facing
// spacer (x/y/w/d mm). A copy numbered past its bin's printed Qty is *planned*.
//
// Uses the page's global helpers from app.js: $, $$, api, toast, clone, fmt,
// debounce, escapeHtml and state.output.

const DL = {
  UNIT: 8,
  stackSteps: { lid: 1, direct: 3, b4b: 2 },   // replaced by the server's values on load
  active: false,
  loaded: false,
  exists: false,
  output: null,
  file: "",
  bins: [],
  layout: null,
  warnings: [],
  selected: null,        // placement key "B3:0"
  report: null,
  reportTicket: 0,
  candidates: [],
  candidateIndex: -1,
  skipped: [],
  autoNotes: [],
  spacerPlan: null,
  spacerSelected: new Set(),
  spacerPlanSignature: null,
  busy: "",              // "auto" | "spacers" | "connectors" | "print" while a request runs
  dirty: false,
  saving: false,
  saveAgain: false,
  saveState: "idle",     // idle | saving | saved | error
  savedAt: null,
  saveError: "",
  history: [],
  future: [],
  listeners: [],
};

DL.on = fn => DL.listeners.push(fn);
DL.emit = () => DL.listeners.forEach(fn => fn());

// ------------------------------------------------------------------ layout

DL.defaultSettings = () => ({
  autosave: true,
  show_empty: true,
  // Generating is not printing: new bins arrive at Qty 0 unless this is on.
  new_bins_printed: false,
  auto: {
    mode: "rearrange", height_rule: "strict", height_reach: "column",
    keep_locked: true, include_spacers: false, stack_bins: true,
  },
  spacers: { flexible: true, height: 15 },
});

DL.newDrawerId = () => {
  const taken = new Set((DL.layout?.drawers || []).map(one => one.id));
  let n = 1;
  while (taken.has(`d${n}`)) n += 1;
  return `d${n}`;
};

DL.defaultDrawer = (name, from = null) => ({
  id: DL.newDrawerId(),
  name,
  width: from?.width ?? 400,
  depth: from?.depth ?? 300,
  height: from?.height ?? 60,
  clearance: from?.clearance ?? 1,
  anchor: from?.anchor ?? "front-left",
  bin_axis: from?.bin_axis ?? "x",
  snap: from?.snap ?? 8,
  boundary: from?.boundary ?? "wall",
  keepouts: [],
  placements: [],
});

DL.normaliseLayout = raw => {
  const layout = raw && typeof raw === "object" ? clone(raw) : {};
  const defaults = DL.defaultSettings();
  layout.version = 1;
  layout.settings = { ...defaults, ...(layout.settings || {}) };
  layout.settings.auto = { ...defaults.auto, ...(layout.settings.auto || {}) };
  layout.settings.spacers = { ...defaults.spacers, ...(layout.settings.spacers || {}) };
  layout.drawers = Array.isArray(layout.drawers)
    ? layout.drawers.filter(one => one && typeof one === "object") : [];
  DL.layout = layout;
  if (!layout.drawers.length) layout.drawers.push(DL.defaultDrawer("Drawer 1"));
  layout.drawers.forEach((one, index) => {
    const base = DL.defaultDrawer(`Drawer ${index + 1}`);
    for (const key of Object.keys(base)) if (one[key] === undefined || one[key] === null) one[key] = base[key];
    if (!Array.isArray(one.keepouts)) one.keepouts = [];
    one.placements = (Array.isArray(one.placements) ? one.placements : [])
      .filter(p => p && typeof p === "object" && p.bin);
  });
  if (!layout.drawers.some(one => one.id === layout.active)) layout.active = layout.drawers[0].id;
  return layout;
};

// Drop placements whose bin row is gone (a bin stacked on one takes its
// place) and any copy placed twice. Planned copies stay.
DL.prune = () => {
  const known = new Set(DL.bins.map(one => one.id));
  const seen = new Set();
  let removed = 0;
  for (const drawer of DL.layout.drawers) {
    for (const gone of drawer.placements.filter(p => !known.has(p.bin))) DL.detach(drawer, gone);
    const kept = drawer.placements.filter(p => {
      const key = DL.key(p);
      if (!known.has(p.bin) || seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    removed += drawer.placements.length - kept.length;
    drawer.placements = kept;
  }
  return removed;
};

// ------------------------------------------------------------------ lookups

DL.drawer = () => DL.layout.drawers.find(one => one.id === DL.layout.active) || DL.layout.drawers[0];
DL.bin = id => DL.bins.find(one => one.id === id);
DL.key = p => `${p.bin}:${p.copy ?? 0}`;
DL.label = one => one.name || `${fmt(one.x)} × ${fmt(one.y)}`;
DL.sizeText = one => `${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm`;
// The user-facing Wavefinity unit is always 8 mm, independent of a drawer's
// own internal grid snap (4 or 8 mm) - see the "8 mm size grid" section of
// README.md. The one place this conversion belongs.
DL.mmToUnits = mm => fmt(mm / 8);
DL.isSpacer = one => one?.kind === "spacer";
DL.stackable = one => Boolean(one) && (one.stack === "lid" || one.stack === "direct" || one.stack === "b4b");
DL.stackName = mode => ({ lid: "Snap-on lid", direct: "Direct snap", b4b: "B4B stacking" })[mode] || "Not stackable";
DL.isPlanned = p => (p.copy ?? 0) >= (Number(DL.bin(p.bin)?.qty) || 0);
DL.onGrid = p => p.gx !== undefined && p.on === undefined;
// A free-placed edge-facing spacer: x/y/w/d/side in mm instead of a grid cell.
DL.isEdgePlacement = p => p.gx === undefined && p.on === undefined;

// A B4B/Box's own mating boundary is already the correct interlocking
// surface (see organizer_drawer.normalise_drawer) and needs no extra
// hard-wall slack; only a real drawer wall floors clearance at the
// catalog's drawer_rules.hard_wall_clearance_mm.
DL.grid = (drawer = DL.drawer()) => {
  const step = Number(drawer.snap) === 4 ? 4 : 8;
  const slack = drawer.boundary === "mating"
    ? Math.max(0, Number(drawer.clearance) || 0)
    : Math.max(drawerHardClearance(), Number(drawer.clearance) || 0);
  const usableX = drawer.width - slack;
  const usableY = drawer.depth - slack;
  const cols = Math.max(0, Math.floor(usableX / step + 1e-6));
  const rows = Math.max(0, Math.floor(usableY / step + 1e-6));
  const centre = drawer.anchor === "center";
  const ox = slack / 2 + (centre ? (usableX - cols * step) / 2 : 0);
  const oy = slack / 2 + (centre ? (usableY - rows * step) / 2 : 0);
  return {
    step, perUnit: DL.UNIT / step, cols, rows, ox, oy,
    gapLeft: ox, gapRight: drawer.width - ox - cols * step,
    gapFront: oy, gapBack: drawer.depth - oy - rows * step,
  };
};

// Footprint in grid cells, as the bin stands in this drawer.
DL.cells = (one, drawer = DL.drawer()) => {
  const step = DL.grid(drawer).step;
  const cx = Math.max(1, Math.ceil(one.x / step - 1e-6));
  const cy = Math.max(1, Math.ceil(one.y / step - 1e-6));
  return drawer.bin_axis === "y" ? [cy, cx] : [cx, cy];
};
DL.toCell = (units, drawer = DL.drawer()) => Math.round(Number(units) * DL.grid(drawer).perUnit);
DL.toUnits = (cell, drawer = DL.drawer()) => cell / DL.grid(drawer).perUnit;

// Inventory Z is the seating-datum module height. The top interlock remains
// exposed on the physical envelope of the first/detached part.
DL.pitch = one => one.stack === "b4b" ? Number(one.z) - (DL.stackSteps.b4b ?? 0) : Number(one.z);
DL.partHeight = one => one.stack === "b4b" ? Number(one.z) : Number(one.z) + (DL.stackSteps[one.stack] ?? 0);
DL.stackHeight = bins => bins.reduce((sum, one, index) => sum + (index ? DL.pitch(one) : DL.partHeight(one)), 0);

// Why `upper` cannot snap onto `lower`, or "" if it can.
DL.stackRefusal = (upper, lower) => {
  if (!DL.stackable(upper)) return `${DL.label(upper)} was not printed to stack.`;
  if (!DL.stackable(lower)) return `${DL.label(lower)} was not printed to stack.`;
  if (upper.stack !== lower.stack) return `A ${DL.stackName(upper.stack).toLowerCase()} bin cannot snap onto a ${DL.stackName(lower.stack).toLowerCase()} bin.`;
  if (Math.abs(upper.x - lower.x) > 0.05 || Math.abs(upper.y - lower.y) > 0.05) return "Only bins of the same size snap onto each other.";
  return "";
};

// The drawer's grid placements as stacks, bottom first.
DL.chains = (drawer = DL.drawer()) => {
  const placed = drawer.placements.filter(p => DL.bin(p.bin));
  const above = new Map();
  placed.forEach(p => { if (p.on !== undefined && !above.has(p.on)) above.set(p.on, p); });
  return placed.filter(DL.onGrid).map(base => {
    const chain = [base];
    const seen = new Set([DL.key(base)]);
    while (above.has(DL.key(chain[chain.length - 1]))) {
      const next = above.get(DL.key(chain[chain.length - 1]));
      if (seen.has(DL.key(next))) break;
      seen.add(DL.key(next));
      chain.push(next);
    }
    return chain;
  });
};

DL.stackOf = (key, drawer = DL.drawer()) => DL.chains(drawer).find(chain => chain.some(p => DL.key(p) === key)) || null;

// One footprint: a single bin or a stack, with each layer's height band.
DL.items = (drawer = DL.drawer()) => DL.chains(drawer).map(chain => {
  const bins = chain.map(p => DL.bin(p.bin));
  const [w, d] = DL.cells(bins[0], drawer);
  let top = 0;
  const layers = chain.map((p, index) => {
    const one = bins[index];
    const bottom = index ? top - (DL.stackSteps[one.stack] ?? 0) : 0;
    top = bottom + DL.partHeight(one);
    return { p, bin: one, key: DL.key(p), z0: bottom, z1: top };
  });
  return {
    key: DL.key(chain[0]), keys: layers.map(layer => layer.key), chain, bins, layers,
    gx: DL.toCell(chain[0].gx, drawer), gy: DL.toCell(chain[0].gy, drawer), w, d, h: top,
  };
});

// One authoritative Space-to-Base-Trim calculation. Stacks are already one
// DL.items() footprint; free edge spacers never enter DL.items().
DL.baseTrimSource = () => {
  if (!DL.loaded || !DL.layout) {
    return { ok: false, message: "Open a Space and arrange bins first." };
  }
  const drawer = DL.drawer();
  const items = DL.items(drawer).filter(item => !DL.isSpacer(item.bins[0]));
  if (!items.length) {
    return { ok: false, message: "There are no arranged bins in the active Space." };
  }
  const minX = Math.min(...items.map(item => item.gx));
  const minY = Math.min(...items.map(item => item.gy));
  const maxX = Math.max(...items.map(item => item.gx + item.w));
  const maxY = Math.max(...items.map(item => item.gy + item.d));
  const occupied = new Set();
  items.forEach(item => {
    for (let x = item.gx; x < item.gx + item.w; x += 1) {
      for (let y = item.gy; y < item.gy + item.d; y += 1) occupied.add(`${x},${y}`);
    }
  });
  if (occupied.size !== (maxX - minX) * (maxY - minY)) {
    return {
      ok: false,
      message: "Base Trim auto-size needs one filled rectangular block of bins. Rearrange the bins into a rectangle or set the Base Trim size manually.",
    };
  }
  const step = DL.grid(drawer).step;
  const fieldX = (maxX - minX) * step;
  const fieldY = (maxY - minY) * step;
  if (Math.abs(fieldX / DL.UNIT - Math.round(fieldX / DL.UNIT)) > 1e-9 ||
      Math.abs(fieldY / DL.UNIT - Math.round(fieldY / DL.UNIT)) > 1e-9) {
    return {
      ok: false,
      message: "The arranged block does not end on whole Wavefinity units. Arrange it as a whole-unit rectangle or size the Base Trim manually.",
    };
  }
  return {
    ok: true,
    field_x_mm: fieldX,
    field_y_mm: fieldY,
    units_x: Math.round(fieldX / DL.UNIT),
    units_y: Math.round(fieldY / DL.UNIT),
    items: items.map(item => ({
      x: (item.gx - minX) * step,
      y: (item.gy - minY) * step,
      w: item.w * step,
      d: item.d * step,
      label: DL.label(item.bins[0]),
    })),
  };
};

DL.placedCount = id => DL.layout.drawers.reduce(
  (sum, drawer) => sum + drawer.placements.filter(p => p.bin === id).length, 0);
DL.plannedCount = id => {
  const one = DL.bin(id);
  return DL.layout.drawers.reduce((sum, drawer) =>
    sum + drawer.placements.filter(p => p.bin === id && (p.copy ?? 0) >= (Number(one?.qty) || 0)).length, 0);
};
DL.drawersHolding = id => DL.layout.drawers
  .filter(drawer => drawer.placements.some(p => p.bin === id)).map(drawer => drawer.name);

// The next copy to place: a printed one not yet in a drawer, else (when
// allowed) a planned one numbered past the printed Qty.
DL.nextCopy = (one, allowPlanned = true) => {
  const used = new Set();
  DL.layout.drawers.forEach(drawer => drawer.placements.forEach(p => { if (p.bin === one.id) used.add(p.copy ?? 0); }));
  const printed = Number(one.qty) || 0;
  for (let copy = 0; copy < printed; copy += 1) if (!used.has(copy)) return copy;
  if (!allowPlanned) return null;
  let copy = printed;
  while (used.has(copy)) copy += 1;
  return copy;
};

DL.findPlacement = key => {
  for (const drawer of DL.layout.drawers) {
    const placement = drawer.placements.find(p => DL.key(p) === key);
    if (placement) return { drawer, placement };
  }
  return null;
};

DL.blockedCells = (drawer = DL.drawer(), grid = DL.grid(drawer)) => {
  const cells = new Set();
  for (const zone of drawer.keepouts || []) {
    const c0 = Math.max(0, Math.floor((zone.x - grid.ox) / grid.step + 1e-6));
    const r0 = Math.max(0, Math.floor((zone.y - grid.oy) / grid.step + 1e-6));
    const c1 = Math.min(grid.cols, Math.ceil((zone.x + zone.w - grid.ox) / grid.step - 1e-6));
    const r1 = Math.min(grid.rows, Math.ceil((zone.y + zone.d - grid.oy) / grid.step - 1e-6));
    for (let r = r0; r < r1; r += 1) for (let c = c0; c < c1; c += 1) cells.add(`${c},${r}`);
  }
  return cells;
};

// Can these bins (bottom first) stand as a footprint with its front-left cell
// at (gx, gy)? `ignore` holds keys being moved. Used live while dragging, so
// it answers in plain words.
DL.fitsAt = (drawer, bins, gx, gy, ignore = new Set()) => {
  const grid = DL.grid(drawer);
  const [w, d] = DL.cells(bins[0], drawer);
  const height = DL.stackHeight(bins);
  if (height > drawer.height + 1e-6) return { ok: false, reason: `That is ${fmt(height)} mm tall - more than this drawer's ${fmt(drawer.height)} mm.` };
  if (gx < 0 || gy < 0 || gx + w > grid.cols || gy + d > grid.rows) return { ok: false, reason: "That would stick out of the drawer." };
  const blocked = DL.blockedCells(drawer, grid);
  for (let r = gy; r < gy + d; r += 1) for (let c = gx; c < gx + w; c += 1) {
    if (blocked.has(`${c},${r}`)) return { ok: false, reason: "That spot is a keep-out zone." };
  }
  for (const item of DL.items(drawer)) {
    if (item.keys.every(key => ignore.has(key))) continue;
    if (gx < item.gx + item.w && item.gx < gx + w && gy < item.gy + item.d && item.gy < gy + d) {
      return { ok: false, reason: `That overlaps ${DL.label(item.bins[0])}.` };
    }
  }
  return { ok: true, reason: "" };
};

// Can these bins snap onto the top of this stack?
DL.fitsOn = (drawer, bins, target) => {
  const lower = target.bins[target.bins.length - 1];
  const refusal = DL.stackRefusal(bins[0], lower);
  if (refusal) return { ok: false, reason: refusal };
  const height = target.h - (DL.stackSteps[bins[0].stack] ?? 0) + DL.stackHeight(bins);
  if (height > drawer.height + 1e-6) return { ok: false, reason: `The stack would be ${fmt(height)} mm tall - more than this drawer's ${fmt(drawer.height)} mm.` };
  return { ok: true, reason: "" };
};

// ------------------------------------------------------------------ changes and undo

DL.snapshot = () => JSON.stringify(DL.layout);

DL.change = (mutate, { history = true } = {}) => {
  const before = DL.snapshot();
  mutate();
  if (DL.snapshot() === before) return false;
  if (history) {
    DL.history.push(before);
    if (DL.history.length > 60) DL.history.shift();
    DL.future = [];
  }
  DL.candidateIndex = -1;
  DL.afterChange();
  return true;
};

DL.afterChange = () => {
  DL.dirty = true;
  DL.clearSpacerPlan();
  if (!DL.layout.settings.autosave) DL.saveState = "idle";
  DL.emit();
  DL.requestReport();
  if (DL.layout.settings.autosave) DL.saveSoon();
};

// A fingerprint of everything a spacer plan is derived from: the active
// drawer (placements, dimensions, keepouts, settings) and every bin's
// size-relevant fields. Kept for reference; DL.clearSpacerPlan() below is
// the actual invalidation mechanism (proactive, not signature-compared) -
// see Fix 004 Correction 6.I.
DL.spacerSignature = () => JSON.stringify([
  DL.layout.active, DL.drawer(),
  DL.bins.map(one => [one.id, one.kind, one.x, one.y, one.z, one.stack]),
]);

// Stale spacer proposals must never survive a layout/inventory change that
// could invalidate them (placements, dimensions, keepouts, settings, the
// active drawer, an auto-layout arrangement, or the bin inventory itself).
// Toggling a candidate's own checkbox must not call this.
DL.clearSpacerPlan = () => {
  DL.spacerPlan = null;
  DL.spacerSelected = new Set();
  DL.spacerPlanSignature = null;
};

DL.restore = redo => {
  const from = redo ? DL.future : DL.history;
  const to = redo ? DL.history : DL.future;
  if (!from.length) return;
  to.push(DL.snapshot());
  DL.layout = DL.normaliseLayout(JSON.parse(from.pop()));
  DL.prune();
  if (DL.selected && !DL.findPlacement(DL.selected)) DL.selected = null;
  DL.candidateIndex = -1;
  DL.afterChange();
};
DL.undo = () => DL.restore(false);
DL.redo = () => DL.restore(true);

// Lift a placement out of wherever it is; whatever stood on it closes the gap.
DL.detach = (drawer, placement) => {
  const above = drawer.placements.find(p => p.on === DL.key(placement));
  if (above) {
    delete above.on;
    if (placement.on !== undefined) above.on = placement.on;
    else Object.assign(above, { gx: placement.gx, gy: placement.gy, locked: Boolean(placement.locked) });
  }
};

// ------------------------------------------------------------------ server

DL.folder = () => state.output || "";

DL.inventoryCall = (path, payload = {}, options = {}) => state.runtime.hosted
  ? SP.inventoryRequest(path, payload, options)
  : api(path, { output: DL.output ?? DL.folder(), ...payload });

DL.adopt = data => {
  DL.bins = data.bins || DL.bins;
  DL.file = data.file || DL.file;
  if (data.stack_steps) DL.stackSteps = data.stack_steps;
};

DL.load = async () => {
  const output = DL.folder();
  const data = await DL.inventoryCall("/api/drawer/load", {}, { write: false });
  const sameFolder = DL.output === output;
  DL.output = output;
  DL.exists = data.exists;
  DL.warnings = data.warnings || [];
  DL.adopt(data);
  // Unsaved edits (auto-save off) survive a trip to the 3D view; anything
  // else is re-read so bins generated meanwhile show up placed as saved.
  if (!(sameFolder && DL.dirty && DL.layout)) {
    DL.normaliseLayout(data.layout);
    DL.history = [];
    DL.future = [];
    DL.dirty = false;
    DL.candidates = [];
    DL.selected = null;
    DL.saveState = "idle";
  }
  DL.prune();
  DL.loaded = true;
  DL.emit();
  DL.requestReport();
};

DL.save = async () => {
  DL.saveSoon.cancel();
  if (!DL.layout) return;
  if (DL.saving) { DL.saveAgain = true; return; }
  DL.saving = true;
  DL.saveState = "saving";
  DL.emit();
  const sent = DL.snapshot();
  try {
    const data = await DL.inventoryCall("/api/drawer/save", { layout: DL.layout });
    DL.adopt(data);
    DL.exists = true;
    if (DL.snapshot() === sent) DL.dirty = false;
    DL.saveState = "saved";
    DL.savedAt = new Date();
  } catch (error) {
    DL.saveState = "error";
    DL.saveError = error.message;
    toast(`Layout not saved: ${error.message}`, true, 6000);
  } finally {
    DL.saving = false;
    DL.emit();
    if (DL.saveAgain) { DL.saveAgain = false; DL.save(); }
  }
};
// Don't write on every keystroke: wait for a lull, then hold off saving again
// until at least AUTOSAVE_MIN_INTERVAL has passed since the last save.
const AUTOSAVE_MIN_INTERVAL = 5 * 60 * 1000;
let dlSaveTimer = null;
DL.saveSoon = () => {
  if (dlSaveTimer) return;
  const elapsed = DL.savedAt ? Date.now() - DL.savedAt.getTime() : Infinity;
  const wait = Math.max(700, AUTOSAVE_MIN_INTERVAL - elapsed);
  dlSaveTimer = setTimeout(() => { dlSaveTimer = null; if (DL.dirty) DL.save(); }, wait);
};
DL.saveSoon.cancel = () => { clearTimeout(dlSaveTimer); dlSaveTimer = null; };

// Bin rows (Qty, name, sizes, stacking, hand-added bins) always save straight
// away - they are the inventory, not the layout. The layout rides along only
// when auto-save is on.
DL.editBins = async changes => {
  const payload = { ...changes };
  if (DL.layout.settings.autosave) payload.layout = DL.layout;
  try {
    const data = await DL.inventoryCall("/api/drawer/save", payload);
    DL.adopt(data);
    DL.exists = true;
    // Bin sizes/kinds may have just changed underneath any spacer proposal.
    DL.clearSpacerPlan();
    const removed = DL.prune();
    if (removed) {
      toast(`${removed} placed cop${removed === 1 ? "y" : "ies"} taken out of the drawers.`);
      DL.afterChange();
    } else if (payload.layout) {
      DL.dirty = false;
      DL.saveState = "saved";
      DL.savedAt = new Date();
    }
    DL.emit();
    DL.requestReport();
    return true;
  } catch (error) {
    toast(error.message, true, 6000);
    return false;
  }
};

// Planned copies of a bin become printed ones: renumber them to follow the
// printed Qty, then raise it by that many.
DL.markPrinted = async one => {
  const printed = Number(one.qty) || 0;
  const planned = DL.layout.drawers.flatMap(drawer => drawer.placements)
    .filter(p => p.bin === one.id && (p.copy ?? 0) >= printed)
    .sort((a, b) => (a.copy ?? 0) - (b.copy ?? 0));
  const count = Math.max(1, planned.length);
  if (planned.length) {
    const rename = new Map();
    DL.change(() => {
      planned.forEach((p, index) => { rename.set(DL.key(p), `${one.id}:${printed + index}`); p.copy = printed + index; });
      DL.layout.drawers.forEach(drawer => drawer.placements.forEach(p => { if (rename.has(p.on)) p.on = rename.get(p.on); }));
    }, { history: false });
    if (rename.has(DL.selected)) DL.selected = rename.get(DL.selected);
  }
  await DL.editBins({ bin_updates: [{ id: one.id, qty: printed + count }] });
};

DL.requestReport = debounce(async () => {
  if (!DL.active || !DL.layout) return;
  const ticket = ++DL.reportTicket;
  try {
    const report = await api("/api/drawer/report", {
      layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
      height_reach: DL.layout.settings.auto.height_reach,
    });
    if (ticket === DL.reportTicket) { DL.report = report; DL.emit(); }
  } catch (_error) {
    if (ticket === DL.reportTicket) { DL.report = null; DL.emit(); }
  }
}, 120);

DL.busyWith = async (what, work) => {
  DL.busy = what;
  DL.emit();
  try {
    return await work();
  } catch (error) {
    toast(error.message, true, 7000);
    return null;
  } finally {
    DL.busy = "";
    DL.emit();
  }
};

// ------------------------------------------------------------------ actions

DL.runAuto = () => DL.busyWith("auto", async () => {
  const result = await api("/api/drawer/auto", {
    layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
    options: DL.layout.settings.auto,
  });
  DL.candidates = result.candidates || [];
  DL.skipped = result.skipped || [];
  DL.autoNotes = result.notes || [];
  if (DL.candidates.length) DL.applyCandidate(0);
  else toast("Nothing to arrange - every bin is placed or locked.");
});

DL.applyCandidate = index => {
  const candidate = DL.candidates[index];
  if (!candidate) return;
  DL.change(() => { DL.drawer().placements = clone(candidate.placements); });
  DL.candidateIndex = index;
  DL.emit();
};

// Put one copy of a bin at a grid cell, or on top of a stack (`target` is a
// DL.items() entry). Uses a planned copy when every printed one is placed.
DL.placeAt = (one, where) => {
  const copy = DL.nextCopy(one);
  const drawer = DL.drawer();
  const fit = where.target ? DL.fitsOn(drawer, [one], where.target) : DL.fitsAt(drawer, [one], where.gx, where.gy);
  if (!fit.ok) { toast(fit.reason, true); return false; }
  const placement = where.target
    ? { bin: one.id, copy, on: where.target.keys[where.target.keys.length - 1] }
    : { bin: one.id, copy, gx: DL.toUnits(where.gx, drawer), gy: DL.toUnits(where.gy, drawer), locked: false };
  DL.change(() => drawer.placements.push(placement));
  DL.selected = DL.key(placement);
  if (DL.isPlanned(placement)) toast(`Placed as planned - every printed ${DL.label(one)} is already in a drawer. Mark it printed once it is.`);
  DL.emit();
  return true;
};

// Drop one bin into the best free spot, using the same packer as Auto layout.
DL.quickPlace = one => DL.busyWith("", async () => {
  const drawer = DL.drawer();
  if (one.z > drawer.height + 1e-6) { toast(`${DL.label(one)} is ${fmt(one.z)} mm tall - taller than this drawer.`, true); return; }
  const copy = DL.nextCopy(one);
  const ask = async rule => {
    const result = await api("/api/drawer/auto", {
      layout: DL.layout, bins: DL.bins, drawer_id: drawer.id,
      options: { ...DL.layout.settings.auto, mode: "fill", stack_bins: false, height_rule: rule, only: [{ bin: one.id, copy }] },
    });
    return (result.candidates?.[0]?.placements || []).find(p => p.bin === one.id && p.copy === copy);
  };
  const rule = DL.layout.settings.auto.height_rule;
  let placement = await ask(rule);
  if (!placement && rule === "strict") {
    placement = await ask("prefer");
    if (placement) toast("No free spot keeps taller bins behind it, so it went where it fits.");
  }
  if (!placement) {
    // No floor left: try the top of a stack it can snap onto.
    const target = DL.items(drawer).find(item => DL.fitsOn(drawer, [one], item).ok);
    if (target) { DL.placeAt(one, { target }); return; }
    toast(`No room left for ${DL.label(one)} in ${drawer.name}.`, true);
    return;
  }
  DL.change(() => drawer.placements.push(placement));
  DL.selected = DL.key(placement);
  if (DL.isPlanned(placement)) toast(`Placed as planned - mark ${DL.label(one)} printed once it is.`);
});

// Move a placement, and everything stacked on it, to a cell or onto a stack.
DL.moveTo = (key, where) => DL.change(() => {
  const found = DL.findPlacement(key);
  if (!found) return;
  const { drawer, placement } = found;
  const locked = DL.onGrid(placement) && Boolean(placement.locked);
  // Whatever stood on the moved bin comes with it; the bin it stood on is
  // left with nothing on top.
  delete placement.on; delete placement.gx; delete placement.gy; delete placement.locked;
  if (where.target) placement.on = where.target.keys[where.target.keys.length - 1];
  else Object.assign(placement, { gx: DL.toUnits(where.gx, drawer), gy: DL.toUnits(where.gy, drawer), locked });
});

// Take a bin and everything stacked on it out of the drawer.
DL.takeOut = key => {
  const chain = DL.stackOf(key);
  const drop = new Set(chain ? chain.slice(chain.findIndex(p => DL.key(p) === key)).map(DL.key) : [key]);
  DL.change(() => {
    const drawer = DL.drawer();
    drawer.placements = drawer.placements.filter(p => !drop.has(DL.key(p)));
  });
  if (drop.has(DL.selected)) DL.selected = null;
  DL.emit();
  return drop.size;
};

DL.removePlacement = key => {
  DL.change(() => {
    const found = DL.findPlacement(key);
    if (!found) return;
    DL.detach(found.drawer, found.placement);
    found.drawer.placements = found.drawer.placements.filter(p => p !== found.placement);
  });
  if (DL.selected === key) DL.selected = null;
  DL.emit();
};

DL.toggleLock = key => DL.change(() => {
  const chain = DL.stackOf(key);
  if (chain) chain[0].locked = !chain[0].locked;
});

DL.planSpacers = () => DL.busyWith("spacers", async () => {
  const result = await api("/api/drawer/spacers", {
    output: DL.output ?? DL.folder(), layout: DL.layout,
    drawer_id: DL.layout.active, options: DL.layout.settings.spacers,
  });
  DL.spacerPlan = result.candidates || [];
  DL.spacerSelected = new Set((result.selected || []).map(c => c.id));
  DL.spacerPlanSignature = DL.spacerSignature();
  DL.emit();
});

DL.toggleSpacerCandidate = id => {
  if (!DL.spacerPlan) return;
  if (DL.spacerSelected.has(id)) DL.spacerSelected.delete(id);
  else DL.spacerSelected.add(id);
  DL.emit();
};

DL.generateSelectedSpacers = () => DL.busyWith("spacers", async () => {
  if (!DL.spacerPlan) return;
  const before = DL.snapshot();
  const result = await api("/api/drawer/spacers/generate", {
    output: DL.output ?? DL.folder(), layout: DL.layout,
    drawer_id: DL.layout.active, selected: Array.from(DL.spacerSelected),
    options: DL.layout.settings.spacers,
  });
  DL.adopt(result);
  DL.normaliseLayout(result.layout);
  if (DL.snapshot() !== before) { DL.history.push(before); DL.future = []; }
  DL.spacerPlan = null;
  DL.spacerSelected = new Set();
  DL.dirty = false;
  DL.saveState = "saved";
  DL.savedAt = new Date();
  
  const made = result.generated?.length || 0;
  const bits = [];
  if (result.placed) bits.push(`${result.placed} spacer${result.placed === 1 ? "" : "s"} placed`);
  if (made) bits.push(`${made} new file${made === 1 ? "" : "s"} saved`);
  if (result.reused) bits.push(`${result.reused} reused from the inventory`);
  toast([bits.join(", ") || "Nothing to fill", ...(result.notes || [])].join("\n"), false, 7000);
  DL.requestReport();
});

// Spacers are free, edge-facing placements (no gx) - DL.items()/DL.chains()
// only cover the grid, so groups are built straight from the active
// drawer's placements instead. Two inventory rows can share identical
// geometry (same file/size) - a group carries every member row, not just
// one representative, and aggregates quantity/printed across all of them -
// see Fix 004 Correction 6.L.
DL.spacerPrintGroups = () => {
  const groups = new Map();

  DL.drawer().placements.forEach(placement => {
    const bin = DL.bin(placement.bin);
    if (!DL.isSpacer(bin)) return;

    const key = `${bin.file}|${bin.x}|${bin.y}|${bin.z}`;
    if (!groups.has(key)) {
      groups.set(key, { bin, entries: [] });
    }
    groups.get(key).entries.push({ bin, placement });
  });

  return Array.from(groups.values()).map(group => {
    const members = Array.from(
      new Map(group.entries.map(entry => [entry.bin.id, entry.bin])).values()
    );
    const printedEntries = group.entries.filter(
      entry => (entry.placement.copy ?? 0) < (Number(entry.bin.qty) || 0)
    );
    const unprintedEntries = group.entries.filter(
      entry => (entry.placement.copy ?? 0) >= (Number(entry.bin.qty) || 0)
    );

    return {
      bin: group.bin,
      members,
      entries: group.entries,
      unprintedEntries,
      qty: group.entries.length,
      printed: printedEntries.length,
      toPrint: unprintedEntries.length,
    };
  });
};

// This reorders only planned copy indices so the selected active-drawer
// copies become the next contiguous printed copies. Other planned copies
// stay planned.
DL.promoteSpacerCopies = (group, requestedCount) => {
  let remaining = Math.min(
    Number(requestedCount) || 0,
    group.unprintedEntries.length,
  );
  const updates = [];

  for (const member of group.members) {
    if (remaining <= 0) break;

    const currentQty = Number(member.qty) || 0;
    const selected = group.unprintedEntries
      .filter(entry => entry.bin.id === member.id)
      .sort((a, b) =>
        (a.placement.copy ?? 0) - (b.placement.copy ?? 0)
      )
      .slice(0, remaining)
      .map(entry => entry.placement);

    if (!selected.length) continue;

    const allPlanned = DL.layout.drawers
      .flatMap(drawer => drawer.placements)
      .filter(
        placement =>
          placement.bin === member.id
          && (placement.copy ?? 0) >= currentQty
      )
      .sort((a, b) => (a.copy ?? 0) - (b.copy ?? 0));

    const selectedSet = new Set(selected);
    const ordered = [
      ...selected,
      ...allPlanned.filter(placement => !selectedSet.has(placement)),
    ];
    const snapshots = ordered.map(placement => ({
      placement,
      oldKey: DL.key(placement),
    }));
    const rename = new Map();

    snapshots.forEach(({ placement, oldKey }, index) => {
      placement.copy = currentQty + index;
      rename.set(oldKey, DL.key(placement));
    });

    DL.layout.drawers.forEach(drawer => {
      drawer.placements.forEach(placement => {
        if (rename.has(placement.on)) placement.on = rename.get(placement.on);
      });
    });

    updates.push({
      id: member.id,
      qty: currentQty + selected.length,
    });
    remaining -= selected.length;
  }

  return updates;
};

// selection: { [group's representative bin id]: requested copy count }, as
// built by DP.confirmSpacerPrint() from DL.spacerPrintGroups(). One real
// file is sent per group; any newly-printed logical copies are then spread
// across that group's own previously-unprinted member rows, and reprints
// never increase the logical quantity in the drawer.
DL.printSelectedSpacers = (selection) => DL.busyWith("print", async () => {
  if (Object.keys(selection).length === 0) return;
  const result = await api("/api/drawer/print-spacers", {
    output: DL.output ?? DL.folder(),
    selection: selection,
    slicer_path: state.slicer?.path || null,
  });

  const groups = DL.spacerPrintGroups();
  const updates = [];

  for (const [id, count] of Object.entries(selection)) {
    if (!(count > 0)) continue;
    const group = groups.find(
      candidate => candidate.members.some(member => member.id === id)
    );
    if (!group) continue;
    updates.push(...DL.promoteSpacerCopies(group, count));
  }

  if (updates.length > 0) {
    await DL.editBins({
      bin_updates: updates,
      layout: DL.layout,
    });
  }
  // launch_slicer opens the files but does not itself set Bambu Studio's
  // per-object copy count - tell the user what to set it to.
  const lines = Object.entries(result.counts || {}).map(([file, copyCount]) => `${copyCount} × ${file}`);
  toast(["Opened in Bambu Studio - set copies to:", ...lines].join("\n"), false, 9000);
});

DL.removeSpacers = () => DL.change(() => {
  const drawer = DL.drawer();
  drawer.placements = drawer.placements.filter(p => !DL.isSpacer(DL.bin(p.bin)));
});

DL.makeConnectors = () => DL.busyWith("connectors", async () => {
  const result = await api("/api/drawer/connectors", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
  });
  const lines = (result.connectors || []).map(one => `Print ${one.count} × ${one.file}`);
  toast([lines.length ? "Connector files saved:" : "No connectors needed yet.", ...lines, ...(result.notes || [])].join("\n"), false, 9000);
});

DL.printDrawer = () => DL.busyWith("print", async () => {
  const result = await api("/api/drawer/print", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins,
    drawer_id: DL.layout.active, slicer_path: state.slicer?.path || null,
  });
  const lines = Object.entries(result.counts || {}).map(([file, count]) => `${count} × ${file}`);
  toast(["Opened in Bambu Studio - set copies to:", ...lines, ...(result.notes || [])].join("\n"), false, 10000);
});
