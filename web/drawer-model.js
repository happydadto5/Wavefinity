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
  savePromise: null,     // Fix 019 correction C1.1: the in-flight serialized save chain, if any
  saveState: "idle",     // idle | saving | saved | error
  savedAt: null,
  saveError: "",
  history: [],
  future: [],
  listeners: [],
  pegboardLayouts: {},
};

// The design being edited, shown in Space before it has been generated. It
// lives only here: never in DL.bins, the layout, autosave, Qty or To print.
//   { key, bin, error }  where bin is a planning record from
//   /api/design/inventory-preview (the same envelope a generated row gets).
DL.working = null;
DL.workingTicket = 0;

DL.on = fn => DL.listeners.push(fn);
DL.emit = () => DL.listeners.forEach(fn => fn());

// ------------------------------------------------------------------ layout

DL.defaultSettings = () => ({
  autosave: true,
  show_empty: true,
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
  boundary: from?.boundary ?? "wall",
  // Not user choices: one 8 mm grid, width left-right, grid against the
  // front-left corner, and the product-rule wall allowance.
  ...DL.canonicalLayoutRules(from?.boundary ?? "wall"),
  placements: [],
});

// The single placement grid, orientation, origin and wall allowance every
// Space layout uses. A real drawer wall needs the catalog's hard-wall
// allowance for the outermost wave crests; a Storage Box's own mating
// boundary is already the interlocking surface and needs none.
DL.canonicalLayoutRules = boundary => ({
  clearance: boundary === "mating" || boundary === "pegboard" ? 0 : drawerHardClearance(),
  anchor: "front-left",
  bin_axis: "x",
  snap: 8,
});

DL.normaliseLayout = raw => {
  const layout = raw && typeof raw === "object" ? clone(raw) : {};
  const defaults = DL.defaultSettings();
  layout.version = 1;
  layout.settings = { ...defaults, ...(layout.settings || {}) };
  delete layout.settings.new_bins_printed; // retired: generating always means Qty 0
  layout.settings.auto = { ...defaults.auto, ...(layout.settings.auto || {}) };
  layout.settings.spacers = { ...defaults.spacers, ...(layout.settings.spacers || {}) };
  // Fix 034 K1: autosave has no user-off path any more; a legacy
  // autosave:false layout normalises to the always-on runtime value.
  layout.settings.autosave = true;
  layout.drawers = Array.isArray(layout.drawers)
    ? layout.drawers.filter(one => one && typeof one === "object") : [];
  DL.layout = layout;
  if (!layout.drawers.length) layout.drawers.push(DL.defaultDrawer("Drawer 1"));
  layout.drawers.forEach((one, index) => {
    const base = DL.defaultDrawer(`Drawer ${index + 1}`);
    for (const key of Object.keys(base)) if (one[key] === undefined || one[key] === null) one[key] = base[key];
    delete one.keepouts; // the old Keep-out Zone feature is gone
    one.placements = (Array.isArray(one.placements) ? one.placements : [])
      .filter(p => p && typeof p === "object" && p.bin);
    // Legacy 4 mm layouts go onto the one 8 mm grid: bins sitting half a unit
    // along snap to the nearest whole unit (the report flags any overlap that
    // makes). Legacy axis, anchor and clearance settings are no longer
    // choices, so they are put back to the canonical rules.
    if (Number(one.snap) === 4) one.placements.filter(DL.onGrid).forEach(p => {
      p.gx = Math.round(p.gx);
      p.gy = Math.round(p.gy);
    });
    Object.assign(one, DL.canonicalLayoutRules(one.boundary));
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
// The user-facing Wavefinity unit is always 8 mm - see the "8 mm size grid"
// section of README.md. The one place this conversion belongs.
DL.mmToUnits = mm => fmt(mm / 8);
DL.isSpacer = one => one?.kind === "spacer";
DL.stackable = one => Boolean(one) && (one.stack === "lid" || one.stack === "direct" || one.stack === "b4b");
DL.stackName = mode => ({ lid: "Snap-on lid", direct: "Direct snap", b4b: "Storage Box stacking" })[mode] || "Not stackable";
DL.isPlanned = p => (p.copy ?? 0) >= (Number(DL.bin(p.bin)?.qty) || 0);
DL.onGrid = p => p.gx !== undefined && p.on === undefined;
// A free-placed edge-facing spacer: x/y/w/d/side in mm instead of a grid cell.
DL.isEdgePlacement = p => p.gx === undefined && p.on === undefined;
DL.isPegboard = (drawer = DL.drawer()) => drawer?.boundary === "pegboard";

// The wall allowance is a product rule (see DL.canonicalLayoutRules), not a
// per-drawer setting.
DL.slack = drawer => DL.canonicalLayoutRules(drawer.boundary).clearance;
DL.grid = (drawer = DL.drawer()) => {
  if (DL.isPegboard(drawer)) {
    const standard = state.catalog?.pegboard_rules?.standards?.find(row => row.id === drawer.pegboard_standard);
    const stepX = Number(standard?.pitch_x_mm || 25.4);
    const stepY = Number(standard?.pitch_y_mm || 25.4);
    const cols = Number(drawer.pegboard_holes_x || Math.floor(drawer.width / stepX));
    const rows = Number(drawer.pegboard_holes_y || Math.floor(drawer.depth / stepY));
    const ox = Number(drawer.pegboard_residual_x || 0) / 2;
    const oy = Number(drawer.pegboard_residual_y || 0) / 2;
    return { step: stepX, stepX, stepY, perUnit: 1, cols, rows, ox, oy,
      gapLeft: ox, gapRight: drawer.width - ox - cols * stepX,
      gapFront: oy, gapBack: drawer.depth - oy - rows * stepY };
  }
  const step = 8;
  const slack = DL.slack(drawer);
  const usableX = drawer.width - slack;
  const usableY = drawer.depth - slack;
  const cols = Math.max(0, Math.floor(usableX / step + 1e-6));
  const rows = Math.max(0, Math.floor(usableY / step + 1e-6));
  const ox = slack / 2;
  const oy = slack / 2;
  return {
    step, stepX: step, stepY: step, perUnit: DL.UNIT / step, cols, rows, ox, oy,
    gapLeft: ox, gapRight: drawer.width - ox - cols * step,
    gapFront: oy, gapBack: drawer.depth - oy - rows * step,
  };
};

// Footprint in grid cells, as the bin stands in this drawer.
DL.cells = (one, drawer = DL.drawer()) => {
  const grid = DL.grid(drawer);
  if (DL.isPegboard(drawer)) {
    const layout = DL.pegboardLayouts[one.id] || one.pegboard_layout;
    if (layout && !layout.error) return [layout.cells_x, layout.cells_y];
  }
  const cx = Math.max(1, Math.ceil(one.x / grid.stepX - 1e-6));
  const cy = Math.max(1, Math.ceil((DL.isPegboard(drawer) ? one.z : one.y) / grid.stepY - 1e-6));
  return [cx, cy];
};
DL.toCell = (units, drawer = DL.drawer()) => DL.isPegboard(drawer) ? Math.round(Number(units)) : Math.round(Number(units) * DL.grid(drawer).perUnit);
DL.toUnits = (cell, drawer = DL.drawer()) => DL.isPegboard(drawer) ? cell : cell / DL.grid(drawer).perUnit;

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
// Bulk printing: a generated bin/B4B row (one with a file, or with a
// canonical design source that Generate can resolve on demand) can be sent
// to the slicer. Needed = planned copies not yet printed, or one copy for a
// Qty 0 row that is not placed; an explicit pick of a satisfied row reprints one.
DL.printEligible = one =>
  Boolean(one) &&
  ["bin", "b4b"].includes(one.kind) &&
  (Boolean(String(one.file || "").trim()) ||
   Boolean(DL.layout?.design_specs?.[one.id]));

DL.printNeeded = one => {
  if (!DL.printEligible(one)) return 0;
  const planned = DL.plannedCount(one.id);
  if (planned > 0) return planned;
  return Number(one.qty) <= 0 ? 1 : 0;
};

DL.printCount = one => {
  const needed = DL.printNeeded(one);
  return needed > 0 ? needed : (DL.printEligible(one) ? 1 : 0);
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

// Can these bins (bottom first) stand as a footprint with its front-left cell
// at (gx, gy)? `ignore` holds keys being moved. Used live while dragging, so
// it answers in plain words.
DL.fitsAt = (drawer, bins, gx, gy, ignore = new Set()) => {
  const grid = DL.grid(drawer);
  const [w, d] = DL.cells(bins[0], drawer);
  const height = DL.stackHeight(bins);
  if (!DL.isPegboard(drawer) && height > drawer.height + 1e-6) return { ok: false, reason: `That is ${fmt(height)} mm tall - more than this drawer's ${fmt(drawer.height)} mm.` };
  if (gx < 0 || gy < 0 || gx + w > grid.cols || gy + d > grid.rows) return { ok: false, reason: DL.isPegboard(drawer) ? "That would stick out of the pegboard." : "That would stick out of the drawer." };
  if (DL.isPegboard(drawer)) {
    const layout = DL.pegboardLayouts[bins[0].id] || bins[0].pegboard_layout;
    if (!layout || layout.error) return { ok: false, reason: layout?.error || "Mount layout is still loading." };
    if (!layout.compatible) return { ok: false, reason: bins[0].pegboard_standard ? "This bin was generated for another pegboard standard." : "This bin has no pegboard receiver." };
    if (drawer.pegboard_standard === "skadis" && gy % 2) return { ok: false, reason: "SKÅDIS bins start on an aligned slot row." };
    if ((layout.mount_offsets || []).some(([mx, my]) => gx + mx < 0 || gx + mx >= grid.cols - 0.5 + 1e-9 || gy + my < 0 || gy + my >= grid.rows)) {
      return { ok: false, reason: "The bin cannot reach enough valid board openings there." };
    }
    const occupied = new Set();
    for (const item of DL.items(drawer)) {
      if (item.keys.every(key => ignore.has(key))) continue;
      const other = DL.pegboardLayouts[item.bins[0].id];
      for (const [mx, my] of other?.mount_offsets || []) occupied.add(`${item.gx + mx},${item.gy + my}`);
    }
    for (const [mx, my] of layout.mount_offsets || []) {
      const hole = `${gx + mx},${gy + my}`;
      if (occupied.has(hole)) return { ok: false, reason: "That mounting position is already in use." };
      occupied.add(hole);
    }
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
  if (DL.isPegboard(drawer)) return { ok: false, reason: "Pegboard bins mount directly to the board and cannot be stacked here." };
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

// A typed one-drawer Space owns its drawer's name and size. Space Edit calls
// this to copy them into the loaded layout through the normal change path
// (dirty, report, autosave); no undo entry, and nothing happens if unchanged.
DL.syncSingleDrawerFromSpace = space => {
  if (!DL.layout || !space || !["drawer", "pegboard"].includes(space.kind) || DL.layout.drawers.length !== 1) return false;
  return DL.change(() => {
    const drawer = DL.drawer();
    drawer.name = space.name;
    drawer.width = space.x;
    drawer.depth = space.y;
    drawer.height = space.z;
    if (space.kind === "pegboard") Object.assign(drawer, {
      boundary: "pegboard", pegboard_standard: space.pegboard_standard,
      pegboard_holes_x: space.pegboard_holes_x, pegboard_holes_y: space.pegboard_holes_y,
      pegboard_residual_x: space.pegboard_residual_x, pegboard_residual_y: space.pegboard_residual_y,
    });
  }, { history: false });
};

DL.afterChange = () => {
  DL.dirty = true;
  DL.clearSpacerPlan();
  DL.emit();
  DL.requestReport();
  DL.saveSoon();
};

// A fingerprint of everything a spacer plan is derived from: the active
// drawer (placements, dimensions, settings) and every bin's
// size-relevant fields. Kept for reference; DL.clearSpacerPlan() below is
// the actual invalidation mechanism (proactive, not signature-compared) -
// see Fix 004 Correction 6.I.
DL.spacerSignature = () => JSON.stringify([
  DL.layout.active, DL.drawer(),
  DL.bins.map(one => [one.id, one.kind, one.x, one.y, one.z, one.stack]),
]);

// Stale spacer proposals must never survive a layout/inventory change that
// could invalidate them (placements, dimensions, settings, the
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

DL.refreshPegboardLayouts = async () => {
  const drawer = DL.layout && DL.drawer();
  if (!DL.isPegboard(drawer)) { DL.pegboardLayouts = {}; return; }
  const bins = [...DL.bins];
  if (DL.working?.bin) bins.push(DL.working.bin);
  const result = await api("/api/pegboard/layouts", {
    standard: drawer.pegboard_standard,
    bins,
  });
  DL.pegboardLayouts = result.layouts || {};
};

// Re-read the current design and, if it is pending inventory, its planning
// envelope from the server. Cheap when the design has not changed.
DL.refreshWorking = async () => {
  const design = typeof workingDesignForSpace === "function" ? workingDesignForSpace() : null;
  if (!design) {
    if (DL.working) { DL.working = null; DL.emit(); }
    return;
  }
  const key = JSON.stringify(design);
  if (DL.working?.key === key) return;
  const context = DL.workingContext();
  const ticket = ++DL.workingTicket;
  try {
    const { bin } = await api("/api/design/inventory-preview", { design });
    if (ticket !== DL.workingTicket || context !== DL.workingContext()) return;
    DL.working = {
      key,
      bin: {
        ...bin, id: "__current__", qty: 0, working: true,
        name: (design.part_name || "").trim(),
      },
    };
    await DL.refreshPegboardLayouts();
  } catch (error) {
    if (ticket !== DL.workingTicket || context !== DL.workingContext()) return;
    DL.working = { key, error: error.message };
  }
  DL.emit();
};

// First legal floor spot for the working design in the active drawer, or the
// plain reason it does not fit. Memoised on what it depends on.
DL.workingFit = () => {
  const working = DL.working;
  if (!working) return null;
  if (working.error) return { ok: false, reason: working.error };
  const drawer = DL.drawer();
  const stamp = JSON.stringify([working.key, drawer.id, drawer.width, drawer.depth, drawer.height,
    drawer.placements]);
  const spot = working.position;
  if (spot && spot.space === DL.workingContext() && spot.drawer === drawer.id) {
    if (DL.fitsAt(drawer, [working.bin], spot.gx, spot.gy).ok) return { ok: true, gx: spot.gx, gy: spot.gy };
  }
  if (spot) working.position = null;
  if (working.fitStamp === stamp) return working.fit;
  const grid = DL.grid(drawer);
  const [w, d] = DL.cells(working.bin, drawer);
  let fit = { ok: false, reason: "" };
  if (!Number.isFinite(w) || !Number.isFinite(d) || w > grid.cols || d > grid.rows) {
    fit.reason = "That is bigger than this Space.";
  } else {
    search:
    for (let gy = 0; gy + d <= grid.rows; gy += 1) {
      for (let gx = 0; gx + w <= grid.cols; gx += 1) {
        const test = DL.fitsAt(drawer, [working.bin], gx, gy);
        if (test.ok) { fit = { ok: true, gx, gy }; break search; }
        if (!fit.reason) fit.reason = test.reason;
      }
    }
  }
  working.fitStamp = stamp;
  working.fit = fit;
  return fit;
};

// Which Space the Current design is standing in (drawer ids repeat across Spaces).
DL.workingContext = () => state.activeSpaceId || DL.folder();

// Session-only: remember where the Current design was dragged. Never a placement.
DL.moveWorkingTo = (gx, gy) => {
  const working = DL.working;
  if (!working?.bin || working.error) return false;
  const drawer = DL.drawer();
  if (!DL.fitsAt(drawer, [working.bin], gx, gy).ok) return false;
  working.position = { space: DL.workingContext(), drawer: drawer.id, gx, gy };
  working.fitStamp = null;
  DL.emit();
  return true;
};

DL.load = async () => {
  const output = DL.folder();
  const data = await DL.inventoryCall("/api/drawer/load", {}, { write: false });
  const sameFolder = DL.output === output;
  DL.output = output;
  DL.exists = data.exists;
  if (!sameFolder && typeof DP !== "undefined") DP.printSelected = new Set();
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
  await DL.refreshPegboardLayouts();
  DL.emit();
  DL.requestReport();
  DL.refreshWorking();
};

// Resolves true once the layout is actually persisted, false on failure -
// callers that need to know whether it is safe to proceed with something
// that depends on that (e.g. switching Spaces - see SP.leaveDrawerLayoutSafely
// in spaces.js, Fix 019 Item 2) must check the return value rather than
// assume success. UI error handling (toast + saveState/saveError) is
// unchanged either way.
//
// Serialization (Fix 019 correction C1.1): DL.save() never hands out an
// optimistic `true` to a caller that arrives while a save is already in
// flight. Instead every caller awaits the SAME promise chain - either the
// request already running, or (if the layout changes again before that
// request finishes) one more queued, serialized request sent right after
// it. DL.saving stays true for the whole chain, and the real, final result
// (success or failure) is what every waiting caller receives. This is a
// small internal loop driven by DL.savePromise/DL.saveAgain, not polling.
DL.save = () => {
  DL.saveSoon.cancel();
  if (!DL.layout) return Promise.resolve(true);
  if (DL.savePromise) {
    // A save is already in flight. Ask for one more serialized save of
    // whatever the layout looks like when that request finishes, and wait
    // on the exact same promise everyone else is waiting on - never an
    // early, optimistic `true`.
    DL.saveAgain = true;
    return DL.savePromise;
  }
  DL.savePromise = DL._runSaveChain().finally(() => {
    DL.savePromise = null;
  });
  return DL.savePromise;
};

// Runs one or more serialized "/api/drawer/save" requests back to back
// until the layout stops changing underneath it, and resolves once that
// chain is genuinely finished. Only DL.save() should call this.
DL._runSaveChain = async () => {
  DL.saving = true;
  let ok = true;
  do {
    DL.saveAgain = false;
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
      ok = true;
    } catch (error) {
      ok = false;
      DL.saveState = "error";
      DL.saveError = error.message;
      toast(`Layout not saved: ${error.message}`, true, 6000);
    }
    // Only chain another serialized save when the previous one actually
    // succeeded and something asked for one more in the meantime. A
    // failure ends the chain immediately so every waiting caller (e.g. a
    // Space-switch safe-leave check) gets `false` and can abort - it must
    // not silently retry and let a caller think the switch is still safe.
  } while (ok && DL.saveAgain);
  DL.saving = false;
  DL.emit();
  return ok;
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
// away - they are the inventory, not the layout. The layout always rides
// along too (Fix 034 K1: no autosave-off path any more).
DL.editBins = async changes => {
  const payload = { ...changes, layout: DL.layout };
  try {
    const data = await DL.inventoryCall("/api/drawer/save", payload);
    DL.adopt(data);
    await DL.refreshPegboardLayouts();
    DL.exists = true;
    // Bin sizes/kinds may have just changed underneath any spacer proposal.
    DL.clearSpacerPlan();
    const removed = DL.prune();
    if (removed) {
      toast(`${removed} placed cop${removed === 1 ? "y" : "ies"} taken out of the drawers.`);
      DL.afterChange();
    } else {
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
  if (DL.isPegboard()) { toast("Place pegboard bins on the visible mount grid.", true); return; }
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
  if (DL.isPegboard(drawer)) {
    const grid = DL.grid(drawer);
    const [w, d] = DL.cells(one, drawer);
    for (let gy = 0; gy + d <= grid.rows; gy += 1) {
      for (let gx = 0; gx + w <= grid.cols; gx += 1) {
        if (DL.fitsAt(drawer, [one], gx, gy).ok) { DL.placeAt(one, { gx, gy }); return; }
      }
    }
    toast(`No mountable space remains for ${DL.label(one)}.`, true);
    return;
  }
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
  let connectorLines = [];
  try {
    const connectors = await DL.saveConnectorFiles();
    if (connectors.lines.length) connectorLines = ["Connector files saved:", ...connectors.lines, ...connectors.notes];
  } catch (error) {
    connectorLines = [`Connector files could not be saved: ${error.message}`];
  }
  toast([bits.join(", ") || "Nothing to fill", ...(result.notes || []), ...connectorLines].join("\n"), false, 9000);
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
  // The launch already repeats each file once per copy.
  const lines = Object.entries(result.counts || {}).map(([file, copyCount]) => `${copyCount} × ${file}`);
  toast(["Opened in Bambu Studio", ...lines].join("\n"), false, 9000);
});

DL.removeSpacers = () => DL.change(() => {
  const drawer = DL.drawer();
  drawer.placements = drawer.placements.filter(p => !DL.isSpacer(DL.bin(p.bin)));
});

// Saves a file for every connector the layout needs. Connectors are part of
// generating spacers, not a separate Space setting.
DL.saveConnectorFiles = async () => {
  const result = await api("/api/drawer/connectors", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
  });
  return {
    lines: (result.connectors || []).map(one => `Print ${one.count} × ${one.file}`),
    notes: result.notes || [],
  };
};

// selection: { [bin id]: copies }. The server re-reads the saved inventory, so
// the layout is saved first; Qty and planned copies change there only after
// the slicer opened successfully.
DL.printSelectedBins = (selection, includeConnectors) => DL.busyWith("print-bins", async () => {
  if (state.runtime.hosted) {
    toast("Bulk printing to a local slicer is available in local Wavefinity.", true);
    return;
  }
  if (!state.slicer || !state.slicer.available) {
    toast("Bambu Studio was not found. Locate it with Change slicer in the bin view.", true, 7000);
    return;
  }
  const chosen = Object.fromEntries(Object.entries(selection || {}).filter(([, count]) => count > 0));
  if (!Object.keys(chosen).length) return;
  if (!(await DL.save())) return;
  const result = await DL.inventoryCall("/api/drawer/print-bins", {
    selection: chosen,
    include_connectors: Boolean(includeConnectors),
    slicer_path: state.slicer?.path || null,
  });
  DL.adopt(result);
  if (result.layout) {
    const selected = DL.selected;
    DL.normaliseLayout(result.layout);
    DL.selected = selected && DL.findPlacement(selected) ? selected : null;
  }
  DL.dirty = false;
  DL.saveState = "saved";
  DL.savedAt = new Date();
  DP.resetPrintSelection();
  DL.emit();
  DL.requestReport();
  const project = result.project ? String(result.project).split(/[\\/]/).pop() : "";
  toast([
    "Opened one Bambu project",
    `${result.bin_copies} bin ${result.bin_copies === 1 ? "copy" : "copies"}`,
    ...(result.connector_copies ? [`${result.connector_copies} connector ${result.connector_copies === 1 ? "copy" : "copies"}`] : []),
    ...(project ? [project] : []),
    ...(result.notes || []),
  ].join("\n"), false, 10000);
});

DL.printDrawer = () => DL.busyWith("print", async () => {
  const result = await api("/api/drawer/print", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins,
    drawer_id: DL.layout.active, slicer_path: state.slicer?.path || null,
  });
  const lines = Object.entries(result.counts || {}).map(([file, count]) => `${count} × ${file}`);
  toast(["Opened in Bambu Studio", ...lines, ...(result.notes || [])].join("\n"), false, 10000);
});
