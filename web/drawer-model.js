"use strict";

// Drawer layout mode - data model, saving and undo.
//
// The inventory file ('<folder> bins.md' in the save location) is the single
// source of truth: bin rows come from it, and the layout (drawers, where each
// printed copy sits, settings) is saved back into it. Bin rows are edited on
// the server by id, so a bin generated while this view is open is never lost.
//
// Uses the page's global helpers from app.js: $, $$, api, toast, clone, fmt,
// debounce, escapeHtml and state.output.

const DL = {
  UNIT: 8,
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
  busy: "",              // "auto" | "spacers" while a request runs
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
  auto: { mode: "rearrange", height_rule: "strict", keep_locked: true, include_spacers: false },
  spacers: { fill: "all", height: 20, max_length: 250 },
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

// Drop placements whose bin is gone, whose copy was never printed, or that
// repeat a copy already placed somewhere else.
DL.prune = () => {
  const qty = new Map(DL.bins.map(one => [one.id, Number(one.qty) || 0]));
  const seen = new Set();
  let removed = 0;
  for (const drawer of DL.layout.drawers) {
    const kept = drawer.placements.filter(p => {
      const key = DL.key(p);
      if ((p.copy ?? 0) >= (qty.get(p.bin) ?? 0) || seen.has(key)) return false;
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
DL.isSpacer = one => one?.kind === "spacer" || one?.kind === "shim";

DL.units = (one, drawer = DL.drawer()) => {
  const ux = Math.max(1, Math.ceil(one.x / DL.UNIT - 1e-6));
  const uy = Math.max(1, Math.ceil(one.y / DL.UNIT - 1e-6));
  return drawer.bin_axis === "y" ? [uy, ux] : [ux, uy];
};

// Mirrors organizer_drawer.drawer_grid: clearance is total slack per axis,
// half at each wall; the grid sits front-left or centred.
DL.grid = (drawer = DL.drawer()) => {
  const slack = Math.max(0.55, Number(drawer.clearance) || 0);
  const usableX = drawer.width - slack;
  const usableY = drawer.depth - slack;
  const cols = Math.max(0, Math.floor(usableX / DL.UNIT + 1e-6));
  const rows = Math.max(0, Math.floor(usableY / DL.UNIT + 1e-6));
  const centre = drawer.anchor === "center";
  const ox = slack / 2 + (centre ? (usableX - cols * DL.UNIT) / 2 : 0);
  const oy = slack / 2 + (centre ? (usableY - rows * DL.UNIT) / 2 : 0);
  return {
    cols, rows, ox, oy,
    gapLeft: ox, gapRight: drawer.width - ox - cols * DL.UNIT,
    gapFront: oy, gapBack: drawer.depth - oy - rows * DL.UNIT,
  };
};

DL.placedCount = id => DL.layout.drawers.reduce(
  (sum, drawer) => sum + drawer.placements.filter(p => p.bin === id).length, 0);

DL.drawersHolding = id => DL.layout.drawers
  .filter(drawer => drawer.placements.some(p => p.bin === id)).map(drawer => drawer.name);

DL.nextFreeCopy = one => {
  const used = new Set();
  DL.layout.drawers.forEach(drawer => drawer.placements.forEach(p => { if (p.bin === one.id) used.add(p.copy ?? 0); }));
  for (let copy = 0; copy < (Number(one.qty) || 0); copy += 1) if (!used.has(copy)) return copy;
  return null;
};

DL.findPlacement = key => {
  for (const drawer of DL.layout.drawers) {
    const placement = drawer.placements.find(p => DL.key(p) === key);
    if (placement) return { drawer, placement };
  }
  return null;
};

DL.gridItems = (drawer = DL.drawer()) => drawer.placements
  .filter(p => p.gx !== undefined)
  .map(p => {
    const one = DL.bin(p.bin);
    if (!one) return null;
    const [w, d] = DL.units(one, drawer);
    return { key: DL.key(p), p, bin: one, gx: p.gx, gy: p.gy, w, d, h: Number(one.z) };
  })
  .filter(Boolean);

DL.blockedCells = (drawer = DL.drawer(), grid = DL.grid(drawer)) => {
  const cells = new Set();
  for (const zone of drawer.keepouts || []) {
    const c0 = Math.max(0, Math.floor((zone.x - grid.ox) / DL.UNIT + 1e-6));
    const r0 = Math.max(0, Math.floor((zone.y - grid.oy) / DL.UNIT + 1e-6));
    const c1 = Math.min(grid.cols, Math.ceil((zone.x + zone.w - grid.ox) / DL.UNIT - 1e-6));
    const r1 = Math.min(grid.rows, Math.ceil((zone.y + zone.d - grid.oy) / DL.UNIT - 1e-6));
    for (let r = r0; r < r1; r += 1) for (let c = c0; c < c1; c += 1) cells.add(`${c},${r}`);
  }
  return cells;
};

// Can this bin stand with its front-left cell at (gx, gy)? Used live while
// dragging, so it answers in plain words.
DL.fitsAt = (drawer, one, gx, gy, ignoreKey = null) => {
  const grid = DL.grid(drawer);
  const [w, d] = DL.units(one, drawer);
  if (one.z > drawer.height + 1e-6) return { ok: false, reason: `${DL.label(one)} is ${fmt(one.z)} mm tall - taller than this drawer (${fmt(drawer.height)} mm).` };
  if (gx < 0 || gy < 0 || gx + w > grid.cols || gy + d > grid.rows) return { ok: false, reason: "That would stick out of the drawer." };
  const blocked = DL.blockedCells(drawer, grid);
  for (let r = gy; r < gy + d; r += 1) for (let c = gx; c < gx + w; c += 1) {
    if (blocked.has(`${c},${r}`)) return { ok: false, reason: "That spot is a keep-out zone." };
  }
  for (const item of DL.gridItems(drawer)) {
    if (item.key === ignoreKey) continue;
    if (gx < item.gx + item.w && item.gx < gx + w && gy < item.gy + item.d && item.gy < gy + d) {
      return { ok: false, reason: `That overlaps ${DL.label(item.bin)}.` };
    }
  }
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
  DL.saveState = DL.layout.settings.autosave ? DL.saveState : "idle";
  DL.emit();
  DL.requestReport();
  if (DL.layout.settings.autosave) DL.saveSoon();
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

// ------------------------------------------------------------------ server

DL.folder = () => state.output || "";

DL.load = async () => {
  const output = DL.folder();
  const data = await api("/api/drawer/load", { output });
  const sameFolder = DL.output === output;
  DL.output = output;
  DL.file = data.file;
  DL.exists = data.exists;
  DL.bins = data.bins || [];
  DL.warnings = data.warnings || [];
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
    const data = await api("/api/drawer/save", { output: DL.output ?? DL.folder(), layout: DL.layout });
    DL.bins = data.bins || DL.bins;
    DL.file = data.file;
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
DL.saveSoon = debounce(() => DL.save(), 700);

// Bin rows (Qty, name, sizes, hand-added bins) always save straight away -
// they are the inventory, not the layout. The layout rides along only when
// auto-save is on.
DL.editBins = async changes => {
  const payload = { output: DL.output ?? DL.folder(), ...changes };
  if (DL.layout.settings.autosave) payload.layout = DL.layout;
  try {
    const data = await api("/api/drawer/save", payload);
    DL.bins = data.bins || [];
    DL.file = data.file;
    DL.exists = true;
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

DL.requestReport = debounce(async () => {
  if (!DL.active || !DL.layout) return;
  const ticket = ++DL.reportTicket;
  try {
    const report = await api("/api/drawer/report", {
      layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
    });
    if (ticket === DL.reportTicket) { DL.report = report; DL.emit(); }
  } catch (error) {
    if (ticket === DL.reportTicket) { DL.report = null; DL.emit(); }
  }
}, 120);

// ------------------------------------------------------------------ actions

DL.runAuto = async () => {
  DL.busy = "auto";
  DL.emit();
  try {
    const result = await api("/api/drawer/auto", {
      layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
      options: DL.layout.settings.auto,
    });
    DL.candidates = result.candidates || [];
    DL.skipped = result.skipped || [];
    DL.autoNotes = result.notes || [];
    if (DL.candidates.length) DL.applyCandidate(0);
    else toast("Nothing to arrange - every printed bin is placed or locked.");
  } catch (error) {
    toast(error.message, true, 6000);
  } finally {
    DL.busy = "";
    DL.emit();
  }
};

DL.applyCandidate = index => {
  const candidate = DL.candidates[index];
  if (!candidate) return;
  DL.change(() => { DL.drawer().placements = clone(candidate.placements); });
  DL.candidateIndex = index;
  DL.emit();
};

DL.placeAt = (one, gx, gy) => {
  const copy = DL.nextFreeCopy(one);
  if (copy === null) { toast(`Every printed ${DL.label(one)} is already placed. Raise its Qty if you printed more.`); return false; }
  const fit = DL.fitsAt(DL.drawer(), one, gx, gy);
  if (!fit.ok) { toast(fit.reason, true); return false; }
  const placement = { bin: one.id, copy, gx, gy, locked: false };
  DL.change(() => DL.drawer().placements.push(placement));
  DL.selected = DL.key(placement);
  DL.emit();
  return true;
};

// Drop one bin into the best free spot, using the same packer as Auto layout.
DL.quickPlace = async one => {
  const copy = DL.nextFreeCopy(one);
  if (copy === null) { toast(`Every printed ${DL.label(one)} is already placed. Raise its Qty if you printed more.`); return; }
  const drawer = DL.drawer();
  if (one.z > drawer.height + 1e-6) { toast(`${DL.label(one)} is ${fmt(one.z)} mm tall - taller than this drawer.`, true); return; }
  const ask = async rule => {
    const result = await api("/api/drawer/auto", {
      layout: DL.layout, bins: DL.bins, drawer_id: drawer.id,
      options: { ...DL.layout.settings.auto, mode: "fill", height_rule: rule, only: [{ bin: one.id, copy }] },
    });
    return (result.candidates?.[0]?.placements || []).find(p => p.bin === one.id && p.copy === copy);
  };
  try {
    const rule = DL.layout.settings.auto.height_rule;
    let placement = await ask(rule);
    if (!placement && rule === "strict") {
      placement = await ask("prefer");
      if (placement) toast("No free spot keeps taller bins behind it, so it went where it fits.");
    }
    if (!placement) { toast(`No room left for ${DL.label(one)} in ${drawer.name}.`, true); return; }
    DL.change(() => drawer.placements.push(placement));
    DL.selected = DL.key(placement);
    DL.emit();
  } catch (error) {
    toast(error.message, true);
  }
};

DL.move = (key, gx, gy) => DL.change(() => {
  const found = DL.findPlacement(key);
  if (found) Object.assign(found.placement, { gx, gy });
});

DL.removePlacement = key => {
  DL.change(() => {
    const found = DL.findPlacement(key);
    if (found) found.drawer.placements = found.drawer.placements.filter(p => p !== found.placement);
  });
  if (DL.selected === key) DL.selected = null;
  DL.emit();
};

DL.toggleLock = key => DL.change(() => {
  const found = DL.findPlacement(key);
  if (found && found.placement.gx !== undefined) found.placement.locked = !found.placement.locked;
});

DL.makeSpacers = async () => {
  DL.busy = "spacers";
  DL.emit();
  const before = DL.snapshot();
  try {
    const result = await api("/api/drawer/spacers", {
      output: DL.output ?? DL.folder(), layout: DL.layout,
      drawer_id: DL.layout.active, options: DL.layout.settings.spacers,
    });
    DL.bins = result.bins || DL.bins;
    DL.normaliseLayout(result.layout);
    if (DL.snapshot() !== before) {
      DL.history.push(before);
      DL.future = [];
    }
    DL.dirty = false;
    DL.saveState = "saved";
    DL.savedAt = new Date();
    const made = result.generated?.length || 0;
    const bits = [];
    if (result.placed) bits.push(`${result.placed} spacer${result.placed === 1 ? "" : "s"} placed`);
    if (made) bits.push(`${made} new file${made === 1 ? "" : "s"} saved`);
    if (result.reused) bits.push(`${result.reused} reused from the inventory`);
    toast([bits.join(", ") || "Nothing to fill", ...(result.notes || [])].join("\n"), false, 6000);
    DL.emit();
    DL.requestReport();
  } catch (error) {
    toast(error.message, true, 7000);
  } finally {
    DL.busy = "";
    DL.emit();
  }
};

DL.removeSpacers = () => DL.change(() => {
  const drawer = DL.drawer();
  drawer.placements = drawer.placements.filter(p => !DL.isSpacer(DL.bin(p.bin)));
});
