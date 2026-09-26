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
// spacer (x/y/w/d mm). One ordinary Inventory row is one placement identity: it
// is placed at most once, and a row with no placement is *unplaced* (it shows
// in the staging rail). Only spacers, being repeated filler parts, may be
// placed several times.
//
// Uses the page's global helpers from app.js: $, $$, api, toast, clone, fmt,
// debounce, escapeHtml and state.output.

const DL = {
  UNIT: 8,
  stackSteps: { lid: 1, direct: 3, b4b: 2 },   // replaced by the server's values on load
  active: false,
  loaded: false,
  loadPromise: null,
  loadEpoch: 0,
  exists: false,
  output: null,
  file: "",
  bins: [],
  layout: null,
  warnings: [],
  selected: null,        // placement key "B3:0"
  selectedRow: null,     // Inventory row id the user last picked (placed or staged)
  report: null,
  reportTicket: 0,
  spacerPlan: null,
  spacerSelected: new Set(),
  spacerPlanSignature: null,
  fillPlan: null,
  fillSelected: new Set(),
  fillSignature: null,
  busy: "",              // "spacers" | "fill" | "print" | ... while a request runs
  busyTicket: 0,
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
  pegboardRefreshError: "",
};

DL.on = fn => DL.listeners.push(fn);
DL.emit = () => DL.listeners.forEach(fn => fn());

// ------------------------------------------------------------------ layout

DL.defaultSettings = () => ({
  autosave: true,
  spacers: { flexible: true, height: 15 },
  surface: { ask_object_height: true },
  // Fix 061 F6: per-Space choice to refresh a bin's saved files after an edit
  // without asking. Default Ask.
  auto_update_changed_files: false,
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
  delete layout.settings.auto;             // retired: there is no Auto layout
  delete layout.settings.show_empty;      // the empty-cell grid is always visible
  layout.settings.spacers = { ...defaults.spacers, ...(layout.settings.spacers || {}) };
  layout.settings.surface = { ...defaults.surface, ...(layout.settings.surface || {}) };
  // Fix 034 K1: autosave has no user-off path any more; a legacy
  // autosave:false layout normalises to the always-on runtime value.
  layout.settings.autosave = true;
  layout.settings.auto_update_changed_files = layout.settings.auto_update_changed_files === true;
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
    one.placements.forEach(p => { delete p.locked; }); // retired: there is no Lock
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
  DL.singlePlacements(layout);
  return layout;
};

// One ordinary Inventory row is one placement. A legacy or test layout that
// carries several copies of a row keeps one deterministically - the lowest
// copy number, then the earliest drawer and position - and renumbers it copy 0.
// Whatever was stacked on a dropped placement closes the gap. Spacers are
// exempt (repeated filler parts) and so is any placement whose row is not
// known yet. Returns how many placements were dropped.
DL.singlePlacements = layout => {
  const groups = new Map();
  layout.drawers.forEach((drawer, drawerIndex) => drawer.placements.forEach((placement, index) => {
    const one = DL.bin(placement.bin);
    if (!one || DL.isSpacer(one)) return;
    if (!groups.has(placement.bin)) groups.set(placement.bin, []);
    groups.get(placement.bin).push({ drawer, drawerIndex, index, placement });
  }));
  const dropped = new Set();
  const renamed = new Map();
  for (const entries of groups.values()) {
    entries.sort((a, b) => (a.placement.copy ?? 0) - (b.placement.copy ?? 0)
      || a.drawerIndex - b.drawerIndex || a.index - b.index);
    const [keeper, ...extras] = entries;
    if (keeper.placement.copy !== undefined && (keeper.placement.copy ?? 0) !== 0) {
      renamed.set(DL.key(keeper.placement), `${keeper.placement.bin}:0`);
    }
    extras.forEach(extra => dropped.add(extra.placement));
  }
  if (!dropped.size && !renamed.size) return 0;
  for (const drawer of layout.drawers) {
    for (const gone of drawer.placements.filter(p => dropped.has(p))) DL.detach(drawer, gone);
  }
  layout.drawers.forEach(drawer => {
    drawer.placements = drawer.placements.filter(p => !dropped.has(p));
  });
  for (const drawer of layout.drawers) {
    for (const p of drawer.placements) {
      if (renamed.has(p.on)) p.on = renamed.get(p.on);
    }
  }
  for (const drawer of layout.drawers) {
    for (const p of drawer.placements) {
      if (renamed.has(DL.key(p))) p.copy = 0;
    }
  }
  return dropped.size;
};

// Drop placements whose bin row is gone (a bin stacked on one takes its
// place), any placement listed twice, and any extra placement of an ordinary
// row.
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
  return removed + DL.singlePlacements(DL.layout);
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
DL.onGrid = p => p.gx !== undefined && p.on === undefined;
// A free-placed edge-facing spacer: x/y/w/d/side in mm instead of a grid cell.
DL.isEdgePlacement = p => p.gx === undefined && p.on === undefined;
DL.isPegboard = (drawer = DL.drawer()) => drawer?.boundary === "pegboard";
DL.isSurface = () => DL.layout?.space?.kind === "surface";
DL.planningMap = () => DL.report?.planning_heights || {};
DL.rowPlanning = one => DL.planningMap()[one?.id] || one?.planning || null;
DL.effectiveHeight = one => Number(DL.rowPlanning(one)?.effective_mm ?? DL.partHeight(one));
DL.stackPlanningHeight = layers => Math.max(0, ...layers.map(layer => layer.z0 + DL.effectiveHeight(layer.bin)));

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
    plan_h: DL.isSurface() ? DL.stackPlanningHeight(layers) : top,
  };
});

DL.placedCount = id => DL.layout.drawers.reduce(
  (sum, drawer) => sum + drawer.placements.filter(p => p.bin === id).length, 0);
DL.isPlaced = id => DL.placedCount(id) > 0;

// Ordinary rows are the placeable, stageable bins; spacers are filler parts
// planned from the Spacers section.
DL.isOrdinary = one => Boolean(one) && !DL.isSpacer(one);
DL.binNumbers = () => new Map(DL.bins.filter(DL.isOrdinary).map((one, index) => [one.id, index + 1]));
DL.binNumber = one => DL.binNumbers().get(one?.id);
DL.binNumberLabel = one => {
  const number = DL.isOrdinary(one) ? DL.binNumber(one) : null;
  return number ? `Bin ${number}` : "";
};

// The staging rail's membership, derived and never persisted: every ordinary
// Inventory row with no placement, in Inventory order.
DL.stagedBins = () => DL.bins.filter(one => DL.isOrdinary(one) && !DL.isPlaced(one.id));

// The one lifecycle label a row shows.
DL.statusLabel = one => one?.status === "printed" ? "Printed" : one?.status === "saved" ? "Saved" : "In Space";

// Bulk printing: a generated bin/B4B row (one with a file, or with a
// canonical design source that Save can resolve on demand) can be sent to the
// slicer. A row not yet Printed is still to print; each selected row is
// sent exactly once.
DL.printEligible = one =>
  Boolean(one) &&
  ["bin", "b4b"].includes(one.kind) &&
  (Boolean(String(one.file || "").trim()) ||
   Boolean(DL.layout?.design_specs?.[one.id]));

DL.printNeeded = one => (DL.printEligible(one) && one.status !== "printed" ? 1 : 0);

// Batch Save: an eligible row whose current design has no current files yet.
DL.saveNeeded = one => (DL.printEligible(one) && !String(one.file || "").trim() ? 1 : 0);

DL.printCount = one => {
  return DL.printEligible(one) ? 1 : 0;
};

DL.drawersHolding = id => DL.layout.drawers
  .filter(drawer => drawer.placements.some(p => p.bin === id)).map(drawer => drawer.name);

// A spacer is a repeated filler part: its next placement takes the first free
// copy number. (Ordinary rows are always copy 0.)
DL.nextSpacerCopy = one => {
  const used = new Set();
  DL.layout.drawers.forEach(drawer => drawer.placements.forEach(p => { if (p.bin === one.id) used.add(p.copy ?? 0); }));
  let copy = 0;
  while (used.has(copy)) copy += 1;
  return copy;
};

// Picking an Inventory row - from the list, the staging rail or the canvas.
// A placed row highlights its placement; an unplaced row highlights staging.
DL.selectRow = id => {
  DL.selectedRow = id || null;
  const found = id ? DL.drawer().placements.find(p => p.bin === id)
    || DL.layout.drawers.flatMap(drawer => drawer.placements).find(p => p.bin === id) : null;
  DL.selected = found ? DL.key(found) : null;
  DL.emit();
};

// Picking a placement on the canvas selects its Inventory row too.
DL.selectPlacement = key => {
  const found = key ? DL.findPlacement(key) : null;
  DL.selected = found ? key : null;
  DL.selectedRow = found ? found.placement.bin : null;
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
  if (DL.isPegboard(drawer) && DL.pegboardRefreshError) {
    return { ok: false, reason: "Pegboard placement data is unavailable. Select Space again to retry the refresh." };
  }
  const grid = DL.grid(drawer);
  const [w, d] = DL.cells(bins[0], drawer);
  const height = DL.stackHeight(bins);
  if (!DL.isPegboard(drawer) && !DL.isSurface() && height > drawer.height + 1e-6) return { ok: false, reason: `That is ${fmt(height)} mm tall - more than this Space's ${fmt(drawer.height)} mm.` };
  if (gx < 0 || gy < 0 || gx + w > grid.cols || gy + d > grid.rows) return { ok: false, reason: DL.isPegboard(drawer) ? "That would stick out of the pegboard." : "That would stick out of the Space." };
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
  if (!DL.isSurface() && height > drawer.height + 1e-6) return { ok: false, reason: `The stack would be ${fmt(height)} mm tall - more than this Space's ${fmt(drawer.height)} mm.` };
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
// active drawer, a placement change, or the bin inventory itself).
// Toggling a candidate's own checkbox must not call this.
DL.clearSpacerPlan = ({ preserveFill = false } = {}) => {
  DL.spacerPlan = null;
  DL.spacerSelected = new Set();
  DL.spacerPlanSignature = null;
  if (!preserveFill) {
    DL.fillPlan = null;
    DL.fillSelected = new Set();
    DL.fillSignature = null;
  }
};

DL.restore = redo => {
  const from = redo ? DL.future : DL.history;
  const to = redo ? DL.history : DL.future;
  if (!from.length) return;
  to.push(DL.snapshot());
  DL.layout = DL.normaliseLayout(JSON.parse(from.pop()));
  DL.prune();
  if (DL.selected && !DL.findPlacement(DL.selected)) DL.selected = null;
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
    else Object.assign(above, { gx: placement.gx, gy: placement.gy });
  }
};

// ------------------------------------------------------------------ server

DL.folder = () => state.output || "";

DL.spaceContext = () => ({
  epoch: DL.loadEpoch,
  output: DL.folder(),
  spaceId: state.activeSpaceId || null,
});

DL.spaceContextCurrent = context =>
  Boolean(context) &&
  context.epoch === DL.loadEpoch &&
  context.output === DL.folder() &&
  context.spaceId === (state.activeSpaceId || null);

DL.staleSpaceError = () => {
  const error = new Error("This action belongs to the Space you just left.");
  error.code = "STALE_SPACE_CONTEXT";
  return error;
};

DL.isStaleSpaceError = error => error?.code === "STALE_SPACE_CONTEXT";

DL.requireSpaceContext = context => {
  if (!DL.spaceContextCurrent(context)) throw DL.staleSpaceError();
};

DL.inventoryCall = async (path, payload = {}, options = {}) => {
  const { context = DL.spaceContext(), ...requestOptions } = options;
  DL.requireSpaceContext(context);
  const data = state.runtime.hosted
    ? await SP.inventoryRequest(path, payload, requestOptions)
    : await api(path, { output: DL.output ?? DL.folder(), ...payload });
  DL.requireSpaceContext(context);
  return data;
};

DL.adopt = data => {
  DL.bins = data.bins || DL.bins;
  DL.file = data.file || DL.file;
  if (data.stack_steps) DL.stackSteps = data.stack_steps;
  if (DL.layout && data.layout && Object.hasOwn(data.layout, "design_specs")) {
    DL.layout.design_specs = clone(data.layout.design_specs || {});
  }
};

DL.refreshPegboardLayouts = async () => {
  const drawer = DL.layout && DL.drawer();
  if (!DL.isPegboard(drawer)) { DL.pegboardLayouts = {}; return; }
  const epoch = DL.loadEpoch;
  const result = await api("/api/pegboard/layouts", {
    standard: drawer.pegboard_standard,
    bins: [...DL.bins],
  });
  if (epoch !== DL.loadEpoch) return;
  DL.pegboardLayouts = result.layouts || {};
};

// Derived geometry failure cannot undo a successful Inventory write or load.
DL.refreshPegboardLayoutsSafe = async warningPrefix => {
  const epoch = DL.loadEpoch;
  try {
    await DL.refreshPegboardLayouts();
    if (epoch !== DL.loadEpoch) return false;
    DL.pegboardRefreshError = "";
    DL.emit();
    return true;
  } catch (error) {
    if (epoch !== DL.loadEpoch) return false;
    DL.pegboardLayouts = {};
    DL.pegboardRefreshError = String(error?.message || error);
    DL.emit();
    if (warningPrefix) toast(`${warningPrefix} ${DL.pegboardRefreshError}`, true, 7000);
    return false;
  }
};
DL.refreshPegboardLayoutsAfterWrite = () => DL.refreshPegboardLayoutsSafe(
  "Inventory saved, but pegboard placement data could not be refreshed.");
DL.refreshPegboardLayoutsAfterLoad = () => DL.refreshPegboardLayoutsSafe(
  "Inventory loaded, but pegboard placement data could not be refreshed.");
DL.retryPegboardLayouts = () => DL.refreshPegboardLayoutsSafe(
  "Pegboard placement data could not be refreshed.");

DL.load = async () => {
  const output = DL.folder();
  const epoch = DL.loadEpoch;
  const data = await DL.inventoryCall("/api/drawer/load", {}, { write: false });
  if (epoch !== DL.loadEpoch || output !== DL.folder()) {
    throw new Error("This Space changed while its inventory was loading.");
  }
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
    DL.selected = null;
    DL.selectedRow = null;
    DL.saveState = "idle";
  }
  DL.prune();
  DL.loaded = true;
  DL.emit();
  DL.requestReport();
  await DL.refreshPegboardLayoutsAfterLoad();
  if (epoch !== DL.loadEpoch) throw new Error("This Space changed while its inventory was loading.");
};

// Initial entry/retry calls share one load. Explicit DL.load() callers still
// force a fresh read after generation or other authoritative changes.
DL.ensureLoaded = () => {
  if (DL.loaded) return Promise.resolve(true);
  if (DL.loadPromise) return DL.loadPromise;
  const promise = DL.load()
    .then(() => true)
    .finally(() => { if (DL.loadPromise === promise) DL.loadPromise = null; });
  DL.loadPromise = promise;
  return DL.loadPromise;
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
    const context = DL.spaceContext();
    try {
      const data = await DL.inventoryCall("/api/drawer/save", { layout: DL.layout }, { context });
      DL.adopt(data);
      DL.exists = true;
      if (DL.snapshot() === sent) DL.dirty = false;
      DL.saveState = "saved";
      DL.savedAt = new Date();
      ok = true;
    } catch (error) {
      ok = false;
      if (!DL.isStaleSpaceError(error)) {
        DL.saveState = "error";
        DL.saveError = error.message;
        toast(`Layout not saved: ${error.message}`, true, 6000);
      }
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
DL.editBins = async (changes, {
  commitLayout = false,
  selected = DL.selected,
  customFailure = false,
  context = DL.spaceContext(),
} = {}) => {
  if (!DL.spaceContextCurrent(context)) return false;
  const payload = {
    ...changes,
    layout: Object.hasOwn(changes, "layout") ? changes.layout : DL.layout,
  };
  const heightOnly = !changes.layout && !changes.new_bins?.length && !changes.delete_ids?.length &&
    changes.bin_updates?.length > 0 && changes.bin_updates.every(update =>
      Object.keys(update).every(key => key === "id" || key === "object_height_mm"));
  try {
    DL.requireSpaceContext(context);
    const data = await DL.inventoryCall("/api/drawer/save", payload, { context });
    DL.adopt(data);
    if (commitLayout) DL.normaliseLayout(data.layout || payload.layout);
    DL.exists = true;
    // Bin sizes/kinds may have just changed underneath any spacer proposal.
    DL.clearSpacerPlan({ preserveFill: heightOnly });
    const removed = DL.prune();
    if (commitLayout) DL.selected = selected && DL.findPlacement(selected) ? selected : null;
    if (removed) {
      toast(`${removed} placement${removed === 1 ? "" : "s"} removed from the saved layout.`);
      DL.afterChange();
    } else {
      DL.dirty = false;
      DL.saveState = "saved";
      DL.savedAt = new Date();
    }
    DL.emit();
  } catch (error) {
    if (DL.isStaleSpaceError(error)) return false;
    DL.saveState = "error";
    DL.saveError = error.message;
    DL.emit();
    if (!customFailure) toast(error.message, true, 6000);
    return false;
  }
  await DL.refreshPegboardLayoutsAfterWrite();
  if (!DL.spaceContextCurrent(context)) return false;
  DL.requestReport();
  return true;
};

DL.setBinPrinted = async (one, printed) => {
  if (DL.layout?.design_specs?.[one.id]) {
    const context = DL.spaceContext();
    try {
      let action = printed ? "mark_printed" : "mark_not_printed";
      if (!printed && one.file && state.runtime.hosted) {
        const names = new Set(await WFFileSystem.listFilenames(state.browserFolder.handle));
        DL.requireSpaceContext(context);
        const pieces = String(one.file).split(", ");
        const existsFrom = start => start === pieces.length ||
          pieces.some((_, end) => end >= start && names.has(pieces.slice(start, end + 1).join(", ")) &&
            existsFrom(end + 1));
        if (!existsFrom(0)) action = "in_design";
      }
      const data = await DL.inventoryCall("/api/drawer/design-source/status", {
        row_id: one.id, action,
      }, { context });
      DL.adopt(data);
      DL.emit();
      DL.requestReport();
      return true;
    } catch (error) {
      if (!DL.isStaleSpaceError(error)) toast(error.message, true, 6000);
      return false;
    }
  }
  return DL.editBins({ bin_updates: [{ id: one.id, qty: printed ? 1 : 0 }] });
};
DL.markPrinted = one => DL.setBinPrinted(one, true);
DL.markNotPrinted = one => DL.setBinPrinted(one, false);

DL.requestReport = debounce(async () => {
  if (!DL.active || !DL.layout) return;
  const ticket = ++DL.reportTicket;
  try {
    const report = await api("/api/drawer/report", {
      layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
    });
    if (ticket === DL.reportTicket) { DL.report = report; DL.emit(); }
  } catch (_error) {
    if (ticket === DL.reportTicket) { DL.report = null; DL.emit(); }
  }
}, 120);

DL.busyWith = async (what, work) => {
  const context = DL.spaceContext();
  const ticket = ++DL.busyTicket;
  DL.busy = what;
  DL.emit();
  try {
    return await work(context);
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 7000);
    return null;
  } finally {
    if (ticket === DL.busyTicket && DL.spaceContextCurrent(context)) {
      DL.busy = "";
      DL.emit();
    }
  }
};

// ------------------------------------------------------------------ actions

// Put one bin at a grid cell, or on top of a stack (`target` is a DL.items()
// entry). An ordinary row is placed once; a spacer takes its next copy number.
DL.placeAt = (one, where) => {
  if (DL.isOrdinary(one) && DL.isPlaced(one.id)) {
    toast(`${DL.label(one)} is already placed in a Space.`, true);
    return false;
  }
  const copy = DL.isSpacer(one) ? DL.nextSpacerCopy(one) : 0;
  const drawer = DL.drawer();
  const fit = where.target ? DL.fitsOn(drawer, [one], where.target) : DL.fitsAt(drawer, [one], where.gx, where.gy);
  if (!fit.ok) { toast(fit.reason, true); return false; }
  const placement = where.target
    ? { bin: one.id, copy, on: where.target.keys[where.target.keys.length - 1] }
    : { bin: one.id, copy, gx: DL.toUnits(where.gx, drawer), gy: DL.toUnits(where.gy, drawer) };
  DL.change(() => drawer.placements.push(placement));
  DL.selected = DL.key(placement);
  DL.selectedRow = one.id;
  DL.emit();
  return true;
};

DL.planSurfaceFill = () => DL.busyWith("fill", async context => {
  if (!DL.isSurface()) return;
  // The Designer's autosave is the boundary: settle it before Fill reads the
  // authoritative Inventory and layout.
  if (typeof flushSpaceDesignAutosave === "function" && !(await flushSpaceDesignAutosave())) return;
  DL.requireSpaceContext(context);
  if (!(await DL.save())) return;
  DL.requireSpaceContext(context);
  const result = await DL.inventoryCall("/api/drawer/surface-fill", {}, { context, write: false });
  DL.fillPlan = result.candidates || [];
  DL.fillSelected = new Set(DL.fillPlan.map(one => one.id));
  DL.fillSignature = result.signature;
  DL.emit();
});

DL.toggleFillCandidate = id => {
  if (!DL.fillPlan) return;
  if (DL.fillSelected.has(id)) DL.fillSelected.delete(id);
  else DL.fillSelected.add(id);
  DL.emit();
};

DL.createSelectedFillBins = () => DL.busyWith("fill", async context => {
  if (!DL.isSurface() || !DL.fillPlan || !DL.fillSelected.size) return;
  if (typeof flushSpaceDesignAutosave === "function" && !(await flushSpaceDesignAutosave())) return;
  DL.requireSpaceContext(context);
  const before = DL.snapshot();
  const result = await DL.inventoryCall("/api/drawer/surface-fill/create", {
    signature: DL.fillSignature, selected: [...DL.fillSelected],
  }, { context });
  DL.adopt(result);
  DL.normaliseLayout(result.layout);
  if (DL.snapshot() !== before) { DL.history.push(before); DL.future = []; }
  DL.fillPlan = null;
  DL.fillSelected = new Set();
  DL.fillSignature = null;
  DL.dirty = false;
  DL.saveState = "saved";
  DL.savedAt = new Date();
  DL.requestReport();
  DL.emit();
  toast(`${result.created?.length || 0} fill bins added to Surface.`);
});

// Move a placement, and everything stacked on it, to a cell or onto a stack.
DL.moveTo = (key, where) => DL.change(() => {
  const found = DL.findPlacement(key);
  if (!found) return;
  const { drawer, placement } = found;
  // Whatever stood on the moved bin comes with it; the bin it stood on is
  // left with nothing on top.
  delete placement.on; delete placement.gx; delete placement.gy;
  if (where.target) placement.on = where.target.keys[where.target.keys.length - 1];
  else Object.assign(placement, { gx: DL.toUnits(where.gx, drawer), gy: DL.toUnits(where.gy, drawer) });
});

// Take a bin and everything stacked on it out of the Space. They are only
// unplaced: each row stays in Inventory and returns to the staging rail.
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

DL.planSpacers = () => DL.busyWith("spacers", async context => {
  const result = await api("/api/drawer/spacers", {
    output: DL.output ?? DL.folder(), layout: DL.layout,
    drawer_id: DL.layout.active, options: DL.layout.settings.spacers,
  });
  DL.requireSpaceContext(context);
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

DL.generateSelectedSpacers = () => DL.busyWith("spacers", async context => {
  if (!DL.spacerPlan) return;
  const before = DL.snapshot();
  const result = await api("/api/drawer/spacers/generate", {
    output: DL.output ?? DL.folder(), layout: DL.layout,
    drawer_id: DL.layout.active, selected: Array.from(DL.spacerSelected),
    options: DL.layout.settings.spacers,
  });
  if (!DL.spaceContextCurrent(context)) {
    toast("Spacer saving finished in the Space you left. The current Space was not changed.");
    return;
  }
  DL.adopt(result);
  DL.normaliseLayout(result.layout);
  if (DL.snapshot() !== before) { DL.history.push(before); DL.future = []; }
  DL.spacerPlan = null;
  DL.spacerSelected = new Set();
  DL.dirty = false;
  DL.saveState = "saved";
  DL.savedAt = new Date();
  DL.emit(); // show newly saved or reused spacer rows before connector work
  const made = result.generated?.length || 0;
  const bits = [];
  if (result.placed) bits.push(`${result.placed} spacer${result.placed === 1 ? "" : "s"} placed`);
  if (made) bits.push(`${made} new file${made === 1 ? "" : "s"} saved`);
  if (result.reused) bits.push(`${result.reused} reused from the inventory`);
  let connectorLines = [];
  try {
    const connectors = await DL.saveConnectorFiles(context);
    if (connectors.lines.length) connectorLines = ["Connector files saved:", ...connectors.lines, ...connectors.notes];
  } catch (error) {
    if (!DL.spaceContextCurrent(context)) {
      toast("Spacer saving finished in the Space you left. The current Space was not changed.");
      return;
    }
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
DL.spacerPrintGroups = (layout = DL.layout) => {
  const groups = new Map();

  const drawer = layout.drawers.find(one => one.id === layout.active) || layout.drawers[0];
  drawer.placements.forEach(placement => {
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

// Spacer-specific count semantics (accepted; spacers are repeated filler
// parts): a spacer copy numbered past its row's printed Qty is still to print.
// This reorders only those to-print copy indices so the selected active-drawer
// copies become the next contiguous printed copies.
DL.promoteSpacerCopies = (group, requestedCount, layout = DL.layout) => {
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

    const allPlanned = layout.drawers
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

    layout.drawers.forEach(drawer => {
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
DL.printSelectedSpacers = (selection) => DL.busyWith("print", async context => {
  if (Object.keys(selection).length === 0) return;
  const result = await api("/api/drawer/print-spacers", {
    output: DL.output ?? DL.folder(),
    selection: selection,
    slicer_path: state.slicer?.path || null,
  });
  if (!DL.spaceContextCurrent(context)) {
    toast("Bambu Studio opened for the Space you left, but Wavefinity did not mark those spacer counts printed. Reopen that Space and correct Qty if you print.");
    return;
  }

  const stagedLayout = clone(DL.layout);
  const selectedPlacement = stagedLayout.drawers.flatMap(drawer => drawer.placements)
    .find(placement => DL.key(placement) === DL.selected);
  const groups = DL.spacerPrintGroups(stagedLayout);
  const updates = [];

  for (const [id, count] of Object.entries(selection)) {
    if (!(count > 0)) continue;
    const group = groups.find(
      candidate => candidate.members.some(member => member.id === id)
    );
    if (!group) continue;
    updates.push(...DL.promoteSpacerCopies(group, count, stagedLayout));
  }

  if (updates.length > 0) {
    const saved = await DL.editBins({
      bin_updates: updates,
      layout: stagedLayout,
    }, {
      commitLayout: true,
      selected: selectedPlacement ? DL.key(selectedPlacement) : DL.selected,
      customFailure: true,
      context,
    });
    if (!DL.spaceContextCurrent(context)) {
      toast("Bambu Studio opened for the Space you left. Check that Space's Qty before printing; the current Space was not changed.");
      return;
    }
    if (!saved) {
      toast("Bambu Studio opened, but Wavefinity could not save the printed counts. Nothing was marked printed in Wavefinity; correct Qty manually if you print.", true, 10000);
      return;
    }
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
// saving spacers, not a separate Space setting.
DL.saveConnectorFiles = async (context = DL.spaceContext()) => {
  DL.requireSpaceContext(context);
  const result = await api("/api/drawer/connectors", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins, drawer_id: DL.layout.active,
  });
  DL.requireSpaceContext(context);
  return {
    lines: (result.connectors || []).map(one => `Print ${one.count} × ${one.file}`),
    notes: result.notes || [],
  };
};

// A batch Save/Print answer always carries the refreshed Inventory, even when
// only part of the work finished, so the browser matches what is on disk.
DL.adoptBatchResult = result => {
  DL.adopt(result);
  if (result.layout) {
    const selected = DL.selected;
    DL.normaliseLayout(result.layout);
    DL.selected = selected && DL.findPlacement(selected) ? selected : null;
  }
  DL.dirty = false;
  DL.saveState = "saved";
  DL.savedAt = new Date();
};

// Shared start of a batch Save/Print: flush the visible Designer, then the
// Space layout, so the server prepares the latest saved designs.
DL.prepareBatch = async selection => {
  if (typeof flushSpaceDesignAutosave === "function" &&
      !(await flushSpaceDesignAutosave({ materialize: selection.includes(state.designInventoryId) }))) return false;
  if (state.runtime.hosted) {
    toast("Bulk saving and printing are available in local Wavefinity.", true);
    return false;
  }
  return true;
};

// Batch Save: make the chosen bins' files current (only rows without current
// files are generated) and never open Bambu Studio or change Printed status.
DL.saveSelectedBins = (rowIds, includeConnectors) => DL.busyWith("save-bins", async context => {
  if (!(await DL.prepareBatch(rowIds || []))) return;
  const chosen = [...new Set(rowIds || [])];
  if (!chosen.length) return;
  if (!(await DL.save())) return;
  DL.requireSpaceContext(context);
  let result;
  try {
    result = await DL.inventoryCall("/api/drawer/save-bins", {
      selection: chosen,
      include_connectors: Boolean(includeConnectors),
    }, { context });
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) throw error;
    toast("Files were saved for the Space you left. The current Space was not changed.");
    return;
  }
  DL.adoptBatchResult(result);
  if (result.partial) {
    // Selection remains the user's general Inventory selection across output.
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    toast(result.error || "Not every file could be saved.", true, 10000);
    return;
  }
  DP.renderInventory(true);
  DL.emit();
  DL.requestReport();
  const made = (result.generated_rows || []).length;
  const kept = (result.reused_rows || []).length;
  toast([
    `Saved ${chosen.length} bin${chosen.length === 1 ? "" : "s"}`,
    ...(made ? [`${made} new`] : []),
    ...(kept ? [`${kept} already had current files`] : []),
    ...(result.connector_copies ? [`${result.connector_copies} connector ${result.connector_copies === 1 ? "copy" : "copies"}`] : []),
    ...(result.notes || []),
  ].join("\n"), false, 8000);
});

// The server re-reads saved Inventory; each selected row opens once in Bambu.
DL.printSelectedBins = (selection, includeConnectors) => DL.busyWith("print-bins", async context => {
  if (!(await DL.prepareBatch(Object.keys(selection || {})))) return;
  if (!state.slicer || !state.slicer.available) {
    toast("Bambu Studio was not found. Locate it with Change slicer in the bin view.", true, 7000);
    return;
  }
  const chosen = Object.fromEntries(Object.entries(selection || {}).filter(([, count]) => count > 0));
  if (!Object.keys(chosen).length) return;
  if (!(await DL.save())) return;
  DL.requireSpaceContext(context);
  let result;
  try {
    result = await DL.inventoryCall("/api/drawer/print-bins", {
      selection: chosen,
      include_connectors: Boolean(includeConnectors),
      slicer_path: state.slicer?.path || null,
    }, { context });
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) throw error;
    toast("Bambu Studio opened for the Space you left. The current Space was not changed.");
    return;
  }
  DL.adoptBatchResult(result);
  // Anything that stopped before a recorded handoff leaves the rows Saved, not
  // Printed. Keep the print selection so Retry is one click, and never show
  // the success toast.
  if (result.partial) {
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    const recorded = result.partial_stage === "status" ? "" : "\nNo bins were marked Printed.";
    toast(`${result.error || "Bambu Studio did not open."}${recorded}`, true, 10000);
    return;
  }
  DP.renderInventory(true);
  DL.emit();
  DL.requestReport();
  toast([
    "Opened in Bambu Studio",
    `${result.bin_copies} bin ${result.bin_copies === 1 ? "copy" : "copies"}`,
    ...(result.connector_copies ? [`${result.connector_copies} connector ${result.connector_copies === 1 ? "copy" : "copies"}`] : []),
    ...(result.notes || []),
  ].join("\n"), false, 10000);
});

DL.printDrawer = () => DL.busyWith("print", async context => {
  const result = await api("/api/drawer/print", {
    output: DL.output ?? DL.folder(), layout: DL.layout, bins: DL.bins,
    drawer_id: DL.layout.active, slicer_path: state.slicer?.path || null,
  });
  if (!DL.spaceContextCurrent(context)) {
    toast("Bambu Studio opened for the Space you left. The current Space was not changed.");
    return;
  }
  const lines = Object.entries(result.counts || {}).map(([file, count]) => `${count} × ${file}`);
  if (result.partial) {
    toast([result.error || "Bambu Studio did not open.", "Connector files were prepared and kept.", ...lines, ...(result.notes || [])].join("\n"), true, 10000);
    return;
  }
  toast(["Opened in Bambu Studio", ...lines, ...(result.notes || [])].join("\n"), false, 10000);
});
