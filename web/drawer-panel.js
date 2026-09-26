"use strict";

// Drawer layout mode - the left panel and switching in and out of the mode.
//
// Sidebar order: what the Space *is* (legacy multi-drawer card only), then the
// Inventory you work from - the primary Space control, one row per bin - then
// Surface Fill and the collapsed Spacers section, with saving pinned at the
// bottom. Space-level actions live in the Space header, never here.

const DP = {
  built: false,
  signatures: {},
  open: new Set(),        // bin ids whose details are expanded
  filter: { text: "", show: "all", sort: "height" },
  filtersBySpace: new Map(),
  printSelected: new Set(), // general ordinary-bin selection, keyed by durable row ID
};

try {
  const saved = JSON.parse(localStorage.getItem("wavefinity-drawer-filter") || "{}");
  if (["height", "size", "name", "newest"].includes(saved.sort)) DP.filter.sort = saved.sort;
} catch (_error) {}
DP.filterSpace = null;
DP.syncFilterSpace = () => {
  const id = state.activeSpace?.id || state.activeSpace?.name || null;
  if (id === DP.filterSpace) return;
  if (DP.filterSpace) DP.filtersBySpace.set(DP.filterSpace, DP.filter.show);
  DP.filterSpace = id;
  DP.filter.show = DP.filtersBySpace.get(id) || "all";
  DP.filter.text = "";
  DP.signatures.inventory = null;
};

const dlNum = (value, fallback = null) => {
  const parsed = Number(String(value ?? "").trim());
  return Number.isFinite(parsed) ? parsed : fallback;
};
const dlPlural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const dlSet = (selector, value, prop = "value") => {
  const node = $(selector);
  if (node && document.activeElement !== node && node[prop] !== value) node[prop] = value;
};
const dlChanged = (name, value) => {
  if (DP.signatures[name] === value) return false;
  DP.signatures[name] = value;
  return true;
};
const STACK_OPTIONS = `<option value="none">Not stackable</option><option value="lid">Snap-on lid</option><option value="direct">Direct snap</option>`;

DP.singleTypedSpace = () => state.folderMode === "space"
  && Boolean(state.activeSpace)
  && Boolean(DL.layout)
  && DL.layout.drawers.length === 1;

DP.extraSpaceText = () => {
  if (!DP.singleTypedSpace() || state.activeSpace?.kind !== "drawer") return "";
  const drawer = DL.drawer();
  if (!drawer) return "";
  const grid = DL.grid(drawer);
  if (!grid) return "";
  const wall = DL.slack(drawer) / 2;
  return [["left", grid.gapLeft], ["right", grid.gapRight], ["front", grid.gapFront], ["back", grid.gapBack]]
    .map(([side, gap]) => [side, gap - wall])
    .filter(([, play]) => Number.isFinite(play) && play >= 0.1)
    .map(([side, play]) => `${play.toFixed(1)} mm (${side})`)
    .join(", ");
};

DP.build = () => {
  if (DP.built) return;
  DP.built = true;
  $("#drawer-panel").innerHTML = `
    <section id="dl-space-details-card" class="dl-card" aria-label="Space">
      <div class="dl-drawer-row">
        <label id="dl-drawer-label-row"><span id="dl-drawer-label">Drawer</span><select id="dl-drawer"></select></label>
        <button type="button" id="dl-drawer-add" class="button secondary dl-small" title="Add another drawer; it shares this inventory">+ Drawer</button>
      </div>
      <div id="dl-drawer-size-card" class="field-grid three dl-drawer-size">
        <label>Width <span class="unit">mm</span><input id="dl-width" type="number" min="16" step="1" title="Inside, left to right"></label>
        <label>Depth <span class="unit">mm</span><input id="dl-depth" type="number" min="16" step="1" title="Inside, front to back"></label>
        <label>Max height <span class="unit">mm</span><input id="dl-height" type="number" min="6" step="1" title="The tallest bin or stack that fits: the inside height, less whatever the drawer above needs to close"></label>
      </div>
      <p id="dl-grid-note" class="dl-note"></p>
      <details class="dl-details" id="dl-fit-details" hidden>
        <summary>Drawer details</summary>
        <div class="field-grid two">
          <label id="dl-name-row">Name<input id="dl-name" type="text" maxlength="40"></label>
        </div>
        <button type="button" id="dl-drawer-delete" class="button danger dl-small">Delete this drawer</button>
      </details>
    </section>

    <section class="control-section open dl-section" aria-label="Inventory">
      <div class="section-body">
        <div id="dl-stats" class="dl-stats"></div>
        <button type="button" id="dl-new-bin" class="button primary">New Bin</button>
        <div class="dl-inv-tools">
          <label class="dl-search-label"><span>Search</span><input id="dl-inv-search" type="search" placeholder="Name or size" aria-label="Search the inventory"></label>
          <label>Filter<select id="dl-inv-show" aria-label="Filter bins">
            <option value="all">Everything</option>
            <option value="in_design">In Design</option>
            <option value="saved">Saved</option>
            <option value="printed">Printed</option>
            <option value="unplaced">Unplaced</option>
            <option value="placed">Placed</option>
            <option value="unprinted">Not printed</option>
            <option value="stackable">Stackable</option>
          </select></label>
          <label>Sort<select id="dl-inv-sort" aria-label="Sort bins">
            <option value="height">Tallest first</option>
            <option value="size">Biggest first</option>
            <option value="name">Name</option>
            <option value="newest">Newest first</option>
          </select></label>
        </div>
        <div id="dl-batch-tools" class="dl-batch-tools">
          <div class="dl-batch-row">
            <button type="button" id="dl-batch-select-needed" class="button secondary dl-small">Select all not printed</button>
            <button type="button" id="dl-batch-select-all" class="button secondary dl-small">Select all</button>
            <button type="button" id="dl-batch-clear" class="button secondary dl-small">Clear selection</button>
            <button type="button" id="dl-batch-delete" class="button danger dl-small" disabled>Delete</button>
            <span id="dl-batch-summary" class="dl-batch-summary" role="status"></span>
          </div>
          <div class="dl-batch-actions">
            <button type="button" id="dl-batch-save" class="button secondary">Save Selected</button>
            <button type="button" id="dl-batch-print" class="button secondary">Print Selected to Bambu Studio</button>
          </div>
        </div>
        <div id="dl-inv-list" class="dl-inv-list"></div>
      </div>
    </section>

    <section id="dl-surface-fill" class="control-section open dl-section" aria-label="Fill Empty Space" hidden>
      <div class="section-heading no-toggle"><span>Fill Empty Space</span></div>
      <div class="section-body">
        <p class="dl-note">Turn free Surface cells into ordinary editable bins.</p>
        <label class="checkbox-row"><span>Ask for missing Object height</span><input id="dl-surface-ask-height" type="checkbox" checked></label>
        <div class="dl-action-grid">
          <button type="button" id="dl-fill-plan" class="button secondary">Plan / Update Fill Bins</button>
          <button type="button" id="dl-fill-create" class="button secondary">Create Selected Fill Bins</button>
        </div>
        <div id="dl-fill-candidates"></div>
      </div>
    </section>

    <details id="dl-spacers" class="dl-section dl-spacers" aria-label="Spacers">
      <summary>Spacers</summary>
      <div class="section-body">
        <div class="field-grid two">
          <label>Spacer type<select id="dl-sp-type"><option value="rigid">Rigid</option><option value="flexible">Flexible</option></select></label>
          <label>Height <span class="unit">mm</span><input id="dl-sp-height" type="number" min="6" step="1" title="How tall the spacers are"></label>
        </div>
        <div class="dl-action-grid">
          <button type="button" id="dl-sp-plan" class="button secondary" title="Find candidate spacers for the gaps against the back and right walls">Create Spacers</button>
          <button type="button" id="dl-sp-generate" class="button secondary" title="Save the selected spacer candidates">Save Selected Spacers</button>
          <button type="button" id="dl-sp-print" class="button secondary" title="Choose which spacers to print">Print Spacers…</button>
        </div>
      </div>
    </details>

    <section class="dl-savebar" aria-label="Saving">
      <div class="dl-save-row">
        <span id="dl-save-status" class="dl-save-status" role="status"></span>
      </div>
    </section>`;
  DV.buildOverlay();
  DP.wire();
  // Hosted capability (Fix 019 Item 3) is recalculated on every render in
  // DP.renderStats() below, not only here - this first pass just avoids a
  // flash of enabled buttons before the first render.
  if (state.runtime.hosted) {
    ["#dl-sp-plan", "#dl-sp-generate", "#dl-sp-print"].forEach(selector => {
      const button = $(selector);
      if (button) {
        button.disabled = true;
        button.title = DP.HOSTED_UNSUPPORTED_TOOLTIP;
      }
    });
  }
};

// Fix 019 Item 3: the hosted backend rejects /api/drawer/spacers,
// /api/drawer/spacers/generate, /api/drawer/print-spacers and
// /api/drawer/print outright, so the remaining spacer actions stay unavailable in hosted mode
// on every render, not just once at build time.
DP.HOSTED_UNSUPPORTED_TOOLTIP = "Hosted Wavefinity uses the normal Design save-to-folder workflow instead of local Space spacer/slicer operations.";

// ------------------------------------------------------------------ wiring

DP.wire = () => {
  const drawerField = (selector, key, parse) => $(selector).addEventListener("change", event => {
    const value = parse(event.target.value);
    if (value === null) { event.target.value = DL.drawer()[key]; toast("Enter a positive number.", true); return; }
    DL.change(() => { DL.drawer()[key] = value; });
  });
  const positive = min => raw => { const n = dlNum(raw); return n !== null && n >= min ? n : null; };
  drawerField("#dl-width", "width", positive(8));
  drawerField("#dl-depth", "depth", positive(8));
  drawerField("#dl-height", "height", positive(1));
  drawerField("#dl-name", "name", raw => raw.trim() || null);
  $("#dl-drawer").addEventListener("change", event => {
    DL.change(() => { DL.layout.active = event.target.value; }, { history: false });
    DL.selected = null;
    DL.selectedRow = null;
    DV.fit();
    DL.emit();
  });
  $("#dl-drawer-add").addEventListener("click", () => {
    const added = DL.defaultDrawer(`Drawer ${DL.layout.drawers.length + 1}`, DL.drawer());
    DL.change(() => { DL.layout.drawers.push(added); DL.layout.active = added.id; });
    $("#dl-fit-details").open = true;
    DL.emit();
    $("#dl-name").focus();
  });
  $("#dl-drawer-delete").addEventListener("click", async () => {
    const drawer = DL.drawer();
    if (DL.layout.drawers.length < 2) return;
    const ok = await appConfirmAction({
      title: "Delete this drawer?",
      message: `Delete ${drawer.name}? Its bins go back to the inventory list.`,
      actionLabel: "Delete Drawer",
      danger: true,
    });
    if (!ok) return;
    DL.change(() => {
      DL.layout.drawers = DL.layout.drawers.filter(one => one !== drawer);
      DL.layout.active = DL.layout.drawers[0].id;
    });
  });
  const setting = (selector, group, key, read) => $(selector).addEventListener("change", event => {
    DL.change(() => {
      const target = group ? DL.layout.settings[group] : DL.layout.settings;
      target[key] = read(event.target);
    }, { history: false });
  });
  setting("#dl-sp-type", "spacers", "flexible", node => node.value === "flexible");
  setting("#dl-sp-height", "spacers", "height", node => Math.max(6, dlNum(node.value, 15)));
  $("#dl-surface-ask-height").addEventListener("change", async event => {
    DL.change(() => { DL.layout.settings.surface.ask_object_height = event.target.checked; }, { history: false });
    await DL.save();
  });
  $("#dl-fill-plan").addEventListener("click", () => DL.planSurfaceFill());
  $("#dl-fill-create").addEventListener("click", () => DL.createSelectedFillBins());
  $("#dl-fill-candidates").addEventListener("change", event => {
    const id = event.target.dataset.fillCandidate;
    if (id) DL.toggleFillCandidate(id);
  });

  $("#dl-batch-select-needed").addEventListener("click", () => DP.selectAllNotPrinted());
  $("#dl-batch-select-all").addEventListener("click", () => DP.selectAllPrintable());
  $("#dl-batch-clear").addEventListener("click", () => DP.clearPrintSelection());
  $("#dl-batch-delete").addEventListener("click", () => DP.deleteSelected());
  $("#dl-batch-save").addEventListener("click", () =>
    DL.saveSelectedBins(DP.batchSaveIds(), true));
  $("#dl-batch-print").addEventListener("click", () =>
    DL.printSelectedBins(DP.printSelectionPayload(), true));
  // Empty-state buttons (canvas overlay and Inventory list) share these.
  const emptyAction = event => {
    const act = event.target.closest("[data-empty-act]")?.dataset.emptyAct;
    if (act === "design") DP.designFirstBin();
  };
  $("#dl-inv-list").addEventListener("click", emptyAction);
  $("#dl-new-bin").addEventListener("click", () => DP.newBinFromSpace());
  $('.canvas-wrap[data-canvas="drawer"]').addEventListener("click", emptyAction);

  $("#dl-sp-plan").addEventListener("click", () => DL.planSpacers());
  $("#dl-sp-generate").addEventListener("click", () => DL.generateSelectedSpacers());
  $("#dl-sp-print").addEventListener("click", () => DP.openSpacerPrintDialog());
  $("#spacer-print-cancel").addEventListener("click", () => $("#spacer-print-dialog").close());
  $("#spacer-print-dialog").addEventListener("click", event => {
    if (event.target === $("#spacer-print-dialog")) $("#spacer-print-dialog").close();
  });
  $("#spacer-print-confirm").addEventListener("click", () => DP.confirmSpacerPrint());
  const filterChanged = () => {
    DP.renderInventory();
  };
  $("#dl-inv-search").addEventListener("input", event => { DP.filter.text = event.target.value; filterChanged(); });
  $("#dl-inv-show").addEventListener("change", event => { DP.filter.show = event.target.value; DP.filtersBySpace.set(DP.filterSpace, DP.filter.show); filterChanged(); });
  $("#dl-inv-sort").addEventListener("change", event => {
    DP.filter.sort = event.target.value;
    try { localStorage.setItem("wavefinity-drawer-filter", JSON.stringify({ sort: DP.filter.sort })); } catch (_error) {}
    filterChanged();
  });

  const list = $("#dl-inv-list");
  list.addEventListener("click", event => DP.onInventoryClick(event));
  list.addEventListener("change", event => {
    const printId = event.target.dataset.printSelect;
    if (printId) {
      if (event.target.checked) DP.printSelected.add(printId); else DP.printSelected.delete(printId);
      event.target.closest("[data-bin]")?.classList.toggle("print-selected", event.target.checked);
      DP.renderBatch();
      return;
    }
    const field = event.target.dataset.field;
    const id = event.target.closest("[data-bin]")?.dataset.bin;
    if (!field || !id) return;
    const text = field === "name" || field === "stack";
    DL.editBins({ bin_updates: [{ id, [field]: text ? event.target.value
      : field === "object_height_mm" && !event.target.value.trim() ? null
        : dlNum(event.target.value, 0) }] });
  });
  list.addEventListener("keydown", event => {
    if (!["Enter", " "].includes(event.key) || event.target.closest("button, input, select, a, textarea, .dl-bin-details")) return;
    const row = event.target.closest(".dl-bin[data-bin]");
    if (!row) return;
    event.preventDefault();
    DL.selectRow(row.dataset.bin);
  });
  list.addEventListener("dragstart", event => {
    DP.draggingRow = true;
    const one = DL.bin(event.target.closest?.("[data-bin]")?.dataset.bin);
    if (!one) return;
    DV.dragBin = one;
    event.dataTransfer.setData("text/plain", one.id);
    event.dataTransfer.effectAllowed = "move";
  });
  list.addEventListener("dragend", () => { DV.dragBin = null; DV.drop = null; DV.render(); DP.draggingRow = false; DP.suppressRowClickUntil = Date.now() + 400; });
};

// ------------------------------------------------------------ bulk print

DP.prunePrintSelection = () => {
  DP.printSelected = new Set(
    [...DP.printSelected].filter(id => DL.isOrdinary(DL.bin(id))));
};

DP.selectAllNotPrinted = () => {
  DP.printSelected = new Set(
    DL.bins.filter(one => DL.isOrdinary(one) && one.status !== "printed").map(one => one.id));
  DP.renderInventory(true);
};

DP.selectAllPrintable = () => {
  DP.printSelected = new Set(
    DL.bins.filter(DL.isOrdinary).map(one => one.id));
  DP.renderInventory(true);
};

DP.clearPrintSelection = () => {
  DP.printSelected.clear();
  DP.renderInventory(true);
};

// The one batch scope both buttons share. With rows ticked, Save and Print act
// on exactly those rows. With nothing ticked they become whole-Space quick
// actions: Save covers every bin still without current files, Print every bin
// not yet Printed.
DP.batchScope = () => {
  const picked = [...DP.printSelected].map(id => DL.bin(id)).filter(one => DL.printEligible(one));
  if (DP.printSelected.size) return { subset: true, save: picked, print: picked, picked };
  const eligible = DL.bins.filter(one => DL.printEligible(one));
  return {
    subset: false, picked: [], eligible,
    save: eligible.filter(one => DL.saveNeeded(one)),
    print: eligible.filter(one => DL.printNeeded(one)),
  };
};

DP.batchSaveIds = () => DP.batchScope().save.map(one => one.id);

DP.printSelectionPayload = () => Object.fromEntries(
  DP.batchScope().print.map(one => [one.id, DL.printCount(one)]));

DP.renderBatch = () => {
  const hosted = Boolean(state.runtime.hosted);
  const tools = $("#dl-batch-tools");
  if (!tools) return;
  $("#dl-batch-save").hidden = hosted;
  $("#dl-batch-print").hidden = hosted;
  const scope = DP.batchScope();
  const connectorNote = hosted ? "" : " · Space connectors included";
  const needFiles = scope.subset ? scope.picked.filter(one => DL.saveNeeded(one)).length : scope.save.length;
  let summary;
  if (scope.subset) {
    summary = `${dlPlural(DP.printSelected.size, "bin")} selected · ${scope.picked.length} eligible for Save/Print · ${needFiles} need${needFiles === 1 ? "s" : ""} new files${connectorNote}`;
  } else if (!scope.eligible.length) {
    summary = "No designs to save or print yet.";
  } else summary = "";
  const summaryNode = $("#dl-batch-summary");
  summaryNode.textContent = summary;
  summaryNode.hidden = !summary;
  $("#dl-batch-clear").disabled = !DP.printSelected.size;
  $("#dl-batch-delete").disabled = !DP.printSelected.size || Boolean(DL.busy);
  if (hosted) return;
  const noSlicer = !state.slicer || !state.slicer.available;
  const busy = Boolean(DL.busy);

  const save = $("#dl-batch-save");
  const saveCount = scope.subset ? scope.picked.length : scope.save.length;
  save.textContent = DL.busy === "save-bins" ? "Saving files…"
    : scope.subset ? `Save Selected (${saveCount})` : `Save All Needed (${saveCount})`;
  save.disabled = busy || (scope.subset ? needFiles === 0 : scope.save.length === 0);
  save.title = save.disabled && !busy
    ? (scope.subset ? "Every selected bin already has current files." : "Every bin already has current files.")
    : "Make the print files without opening Bambu Studio.";

  const button = $("#dl-batch-print");
  const printCount = scope.print.length;
  button.classList.toggle("primary", printCount >= 2);
  button.classList.toggle("secondary", printCount < 2);
  button.textContent = DL.busy === "print-bins" ? "Opening Bambu Studio…"
    : scope.subset ? `Print Selected to Bambu Studio (${printCount})` : `Print All Not Printed (${printCount})`;
  button.disabled = !printCount || noSlicer || busy;
  button.title = noSlicer ? "Bambu Studio was not found. Locate it with Change slicer in the bin view."
    : !printCount ? "Every bin has already been printed." : "Make any missing files, then open them in Bambu Studio.";
};

DP.onInventoryClick = async event => {
  if (event.target.closest(".dl-print-select") || DP.draggingRow || Date.now() < (DP.suppressRowClickUntil || 0)) return;
  const row = event.target.closest("[data-bin]");
  const one = row && DL.bin(row.dataset.bin);
  if (!one) return;
  const action = event.target.closest("[data-act]")?.dataset.act;
  if (action === "more") {
    if (DP.open.has(one.id)) DP.open.delete(one.id); else DP.open.add(one.id);
    DP.renderInventory(true);
  } else if (action === "duplicate") DP.duplicateRow(one);
  else if (action === "print") DL.printSelectedBins({ [one.id]: DL.printCount(one) }, false);
  else if (action === "printed") DL.markPrinted(one);
  else if (action === "not-printed") DL.markNotPrinted(one);
  else if (action === "edit") DP.openInventoryRow(one.id);
  else if (action === "delete") DP.deleteRow(one);
  else if (!action && !event.target.closest("button, input, select, a, textarea, .dl-bin-details")) {
    DL.selectRow(one.id);
  }
};

// Commit the row/canvas selection only after Designer accepted the switch.
// Mouse and keyboard activation share this single success boundary.
DP.openInventoryRow = async id => {
  if (!(await designerEditInventoryRow(id))) return false;
  DL.selectRow(id);
  DP.setMode("design");
  return true;
};

// Duplicate a design-source row through the accepted atomic owner. The new
// row is In Design and unplaced, so it appears in the staging rail; the user
// stays in Space.
DP.duplicateRow = async one => {
  if (typeof flushSpaceDesignAutosave === "function" && !(await flushSpaceDesignAutosave())) return;
  const context = DL.spaceContext();
  try {
    const data = await DL.inventoryCall("/api/drawer/design-source/duplicate", { row_id: one.id }, { context });
    DL.adopt(data);
    DL.selectedRow = data.row_id;
    DL.selected = null;
    DL.emit();
    DL.requestReport();
    toast(`Duplicated as ${DL.label(DL.bin(data.row_id) || one)}. It is waiting in Unplaced bins.`);
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(`Could not duplicate bin: ${error.message}`, true, 6000);
  }
};

// Every Delete button carries its row ID; never delete a stale selection.
DP.deleteRow = async one => {
  const context = DL.spaceContext();
  const placed = DL.placedCount(one.id);
  const ok = await appConfirmAction({
    title: "Delete this bin?",
    message: `Delete ${DL.label(one)} from Inventory?${placed ? " It is placed in this Space; its placement is removed too." : ""} Dragging a bin off the Space only unplaces it. The print file stays in the folder.`,
    actionLabel: "Delete Bin",
    danger: true,
  });
  if (!ok || !DL.spaceContextCurrent(context)) return;
  if (one.id === state.designInventoryId && !(await flushSpaceDesignAutosave())) return;
  if (!DL.spaceContextCurrent(context)) return;
  const wasDesign = one.id === state.designInventoryId;
  DP.open.delete(one.id);
  DP.printSelected.delete(one.id);
  if (DL.selectedRow === one.id) DL.selectedRow = null;
  if (!(await DL.editBins({ delete_ids: [one.id] }, { context }))) return;
  if (wasDesign) {
    state.designInventoryId = null;
    state.cleanDesign = clone(state.design);
    if (typeof discardStaleFileRefreshRows === "function") discardStaleFileRefreshRows([one.id]);
    DP.setMode("space");
    activatePreviewView("drawer");
  }
};

DP.deleteSelected = async () => {
  DP.prunePrintSelection();
  const ids = [...DP.printSelected];
  if (!ids.length) return;
  const context = DL.spaceContext();
  const placed = ids.filter(id => DL.placedCount(id)).length;
  const ok = await appConfirmAction({
    title: `Delete ${dlPlural(ids.length, "bin")}?`,
    message: `Delete all ${ids.length} selected bins, including any hidden by Search or Filter?${placed ? ` ${placed} placed bin${placed === 1 ? "" : "s"} will also be removed from this Space.` : ""} Generated files stay in the folder.`,
    actionLabel: `Delete ${ids.length} bins`, danger: true,
  });
  if (!ok || !DL.spaceContextCurrent(context)) return;
  if (ids.includes(state.designInventoryId) && !(await flushSpaceDesignAutosave())) return;
  if (!DL.spaceContextCurrent(context)) return;
  const removed = await DL.editBins({ delete_ids: ids }, { context });
  if (!removed) return;
  ids.forEach(id => { DP.open.delete(id); DP.printSelected.delete(id); });
  if (ids.includes(DL.selectedRow)) DL.selectedRow = null;
  if (ids.includes(state.designInventoryId)) {
    clearTimeout(spaceAutosaveTimer);
    spaceAutosaveTimer = null;
    state.designInventoryId = null;
    state.cleanDesign = clone(state.design);
    if (typeof discardStaleFileRefreshRows === "function") discardStaleFileRefreshRows(ids);
    DP.setMode("space");
    activatePreviewView("drawer");
  }
  DP.renderInventory(true);
};

// The one "go design a bin" jump used by both empty states.
DP.designFirstBin = () => {
  DP.newBinFromSpace();
};
DP.newBinFromSpace = async () => {
  DP.showPendingMode("design");
  try {
    if (!(await designerNewBin())) return false;
    DP.setMode("design");
    return true;
  } finally { DP.showPendingMode(null); }
};

// A normal typed one-drawer Space: name and size are owned by the Space.
DP.isCanonicalDrawer = () => state.folderMode === "space" && ["drawer", "pegboard"].includes(state.activeSpace?.kind)
  && DL.layout.drawers.length === 1;

// Opens the grouped selection dialog before anything is sent to the slicer -
// clicking Print Spacers… must never silently print every unprinted row.
DP.openSpacerPrintDialog = () => {
  const groups = DL.spacerPrintGroups();
  if (!groups.length) { toast("No spacers placed in this Space yet.", true); return; }
  DP.spacerPrintGroups = groups;
  const container = $("#spacer-print-table-container");
  container.innerHTML = `
    <table class="spacer-print-table">
      <thead><tr><th></th><th>Size</th><th>Flexible/Rigid</th><th>Qty in Space</th><th>Printed</th><th>Qty to print</th></tr></thead>
      <tbody>${groups.map((g, index) => `
        <tr data-group="${index}">
          <td><input type="checkbox" data-sp-check ${g.toPrint > 0 ? "checked" : ""}></td>
          <td>${fmt(g.bin.x)} × ${fmt(g.bin.y)} mm</td>
          <td>${g.bin.name.includes("Rigid") ? "Rigid" : "Flexible"}</td>
          <td>${g.qty}</td>
          <td>${g.printed}</td>
          <td><input type="number" data-sp-qty min="1" max="${g.qty}" value="${Math.max(1, g.toPrint || g.qty)}" ${g.toPrint > 0 ? "" : "disabled"}></td>
        </tr>`).join("")}</tbody>
    </table>`;
  $$("[data-sp-check]", container).forEach(box => box.addEventListener("change", event => {
    const qtyInput = event.target.closest("tr").querySelector("[data-sp-qty]");
    qtyInput.disabled = !event.target.checked;
  }));
  $("#spacer-print-dialog").showModal();
};

DP.confirmSpacerPrint = () => {
  const dialog = $("#spacer-print-dialog");
  const selection = {};
  $$("tr[data-group]", $("#spacer-print-table-container")).forEach(row => {
    const group = DP.spacerPrintGroups[Number(row.dataset.group)];
    const checked = row.querySelector("[data-sp-check]").checked;
    const qty = dlNum(row.querySelector("[data-sp-qty]").value, 0);
    if (checked && qty > 0) selection[group.bin.id] = qty;
  });
  dialog.close();
  if (Object.keys(selection).length) DL.printSelectedSpacers(selection);
};

// ------------------------------------------------------------------ rendering

DP.update = () => {
  if (!DL.active || !DP.built) return;
  DP.syncHistory();
  const panel = $("#drawer-panel");
  if (panel) panel.inert = !DL.layout;
  if (!DL.layout) {
    const list = $("#dl-inv-list");
    if (list) list.innerHTML = '<p class="dl-note">Inventory unavailable. Select Space to retry loading.</p>';
    const stats = $("#dl-stats");
    if (stats) stats.textContent = "";
    const overlay = $("#dl-empty-state");
    if (overlay) {
      overlay.hidden = false;
      overlay.dataset.state = "unavailable";
      overlay.innerHTML = "<strong>Inventory unavailable</strong><p>Select Space to retry loading.</p>";
    }
    const canvas = $("#drawer-canvas");
    if (canvas) canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  DP.renderDrawer();
  DP.renderStats();
  DP.renderSurfaceFill();
  DP.renderInventory();
  DP.renderSave();
  DV.renderEmptyState();
  DV.renderStaging();
  DV.render();
};

DP.syncHistory = () => {
  if (!DP.spaceEditing()) return;
  const undo = $("#undo-design");
  const redo = $("#redo-design");
  if (undo) undo.disabled = !DL.history.length;
  if (redo) redo.disabled = !DL.future.length;
};

DP.renderDrawer = () => {
  const drawer = DL.drawer();
  const pegboard = DL.isPegboard(drawer);
  const surface = DL.isSurface();
  const spacerSection = $("#dl-spacers");
  const detailsCard = $("#dl-space-details-card");
  if (detailsCard) detailsCard.hidden = DP.singleTypedSpace();
  if (spacerSection) spacerSection.hidden = pegboard || surface;
  $("#dl-surface-fill").hidden = !surface;
  $("#dl-height").closest("label").hidden = surface;
  const select = $("#dl-drawer");
  if (dlChanged("drawers", JSON.stringify(DL.layout.drawers.map(one => [one.id, one.name])) + DL.layout.active)) {
    select.innerHTML = DL.layout.drawers.map(one =>
      `<option value="${escapeHtml(one.id)}">${escapeHtml(one.name)}</option>`).join("");
    select.value = DL.layout.active;
  }
  
  // Hide drawer selector if only one drawer in a typed Space.
  const isTypedSpace = state.folderMode === "space" && state.activeSpace;
  const row = select.closest(".dl-drawer-row");
  if (row) {
    if (isTypedSpace && DL.layout.drawers.length === 1) row.style.display = "none";
    else row.style.display = "";
  }
  const addBtn = $("#dl-drawer-add");
  if (addBtn) addBtn.style.display = isTypedSpace ? "none" : "";
  // A typed Space keeps one physical drawer; a preserved selector with more
  // than one only ever holds legacy/previous drawers carried over from
  // before this folder became a typed Space - label it clearly rather than
  // showing an ordinary unlabeled "Drawer" selector - see Fix 004
  // Correction 10.C. Never renamed here: only the selector's own label.
  const drawerLabel = $("#dl-drawer-label");
  if (drawerLabel) {
    const legacyMultiDrawer = isTypedSpace && DL.layout.drawers.length > 1;
    drawerLabel.textContent = legacyMultiDrawer ? "Previous spaces" : (pegboard ? "Pegboard" : "Drawer");
    const labelRow = $("#dl-drawer-label-row");
    if (labelRow) labelRow.title = legacyMultiDrawer
      ? "Legacy drawers from before this folder became this Space. This Space keeps one physical drawer; new drawers can't be added here."
      : "";
  }

  // A typed one-drawer Space owns its name and size (shown, and edited, in
  // the Space header), so only legacy multi-drawer Spaces keep these here.
  const canonical = DP.isCanonicalDrawer();
  $("#dl-fit-details").hidden = canonical;
  $$(".dl-drawer-size", $("#drawer-panel")).forEach(node => { node.hidden = canonical; });

  dlSet("#dl-width", fmt(drawer.width));
  dlSet("#dl-depth", fmt(drawer.depth));
  dlSet("#dl-height", fmt(drawer.height));
  dlSet("#dl-name", drawer.name);
  $("#dl-drawer-delete").disabled = DL.layout.drawers.length < 2;
  const grid = DL.grid(drawer);
  if (pegboard) {
    const standard = state.catalog?.pegboard_rules?.standards?.find(row => row.id === drawer.pegboard_standard);
    $("#dl-grid-note").textContent = `${standard?.name || "Pegboard"}: ${grid.cols} × ${grid.rows} mount positions (${fmt(grid.cols * grid.stepX)} × ${fmt(grid.rows * grid.stepY)} mm usable). Drag bins onto visible holes or slots; yellow dots show their exact mounts.`;
    return;
  }
  const wall = DL.slack(drawer) / 2;
  const edges = [["left", grid.gapLeft], ["right", grid.gapRight], ["front", grid.gapFront], ["back", grid.gapBack]]
    .map(([side, gap]) => [side, gap - wall]).filter(([, play]) => play >= 0.1)
    .map(([side, play]) => `${side} ${play.toFixed(1)} mm`);
  const units = value => fmt(value * grid.step / DL.UNIT);
  $("#dl-grid-note").textContent = `Grid ${units(grid.cols)} × ${units(grid.rows)} units (${fmt(grid.cols * grid.step)} × ${fmt(grid.rows * grid.step)} mm). `
    + (edges.length ? `Left over at the edges: ${edges.join(", ")}.` : "No spare strip at the edges.");
};

DP.renderSurfaceFill = () => {
  if (!DL.isSurface()) return;
  dlSet("#dl-surface-ask-height", Boolean(DL.layout.settings.surface.ask_object_height), "checked");
  const busy = Boolean(DL.busy);
  $("#dl-fill-plan").disabled = busy;
  $("#dl-fill-plan").textContent = DL.busy === "fill" ? "Working…" : "Plan / Update Fill Bins";
  $("#dl-fill-create").disabled = busy || !DL.fillPlan || !DL.fillSelected.size;
  const signature = JSON.stringify([DL.fillPlan, [...DL.fillSelected]]);
  if (!dlChanged("surface-fill", signature)) return;
  $("#dl-fill-candidates").innerHTML = !DL.fillPlan ? ""
    : DL.fillPlan.length ? `<p class="dl-note">${DL.fillPlan.length} bins fit. Select the ones to create.</p>`
      + DL.fillPlan.map(one => `<label class="checkbox-row"><span>${fmt(one.x_mm)} × ${fmt(one.y_mm)} mm · cell ${one.gx + 1}, ${one.gy + 1}</span>`
        + `<input type="checkbox" data-fill-candidate="${escapeHtml(one.id)}"${DL.fillSelected.has(one.id) ? " checked" : ""}></label>`).join("")
      : '<p class="dl-note">No empty Surface cells remain.</p>';
};

DP.renderStats = () => {
  const box = $("#dl-stats");
  const spacers = DL.layout.settings.spacers;
  dlSet("#dl-sp-type", spacers.flexible ? "flexible" : "rigid");
  dlSet("#dl-sp-height", fmt(spacers.height));

  const busy = Boolean(DL.busy);
  const hosted = Boolean(state.runtime.hosted);
  const label = (id, idle, working, what) => { const node = $(id); node.disabled = busy; node.textContent = DL.busy === what ? working : idle; };
  label("#dl-sp-plan", "Create Spacers", "Planning…", "spacers");
  label("#dl-sp-generate", "Save Selected Spacers", "Saving…", "spacers");
  // Nothing placed yet: these have nothing to work on, so say why instead of
  // letting the click end in an error.
  const nothingPlaced = DL.loaded && !DL.drawer().placements.length;
  ["#dl-sp-plan", "#dl-sp-generate"].forEach(selector => {
    const node = $(selector);
    if (!nothingPlaced) return;
    node.disabled = true;
    node.title = "Place a bin in the Space first.";
  });
  // Fix 019 Item 4: Save Selected Spacers must never be an enabled
  // silent no-op. DL.generateSelectedSpacers() already returns immediately
  // with nothing selected/no plan, but the button must not invite that -
  // it needs a current plan (DL.clearSpacerPlan() proactively nulls
  // DL.spacerPlan the moment anything invalidates it, so its mere presence
  // already means "current") AND at least one selected candidate.
  const genNode = $("#dl-sp-generate");
  if (genNode && !hosted && !nothingPlaced) {
    const hasPlan = Boolean(DL.spacerPlan);
    const hasSelection = hasPlan && DL.spacerSelected && DL.spacerSelected.size > 0;
    if (!hasPlan) {
      genNode.disabled = true;
      genNode.title = "Plan spacers first.";
    } else if (!hasSelection) {
      genNode.disabled = true;
      genNode.title = "Select at least one planned spacer.";
    } else {
      genNode.disabled = busy;
      genNode.title = "Save the selected spacer candidates";
    }
  }
  const hasPlacedSpacers = DL.drawer().placements.some(
    placement => DL.isSpacer(DL.bin(placement.bin))
  );
  const spacerPrint = $("#dl-sp-print");
  if (spacerPrint) spacerPrint.hidden = !hasPlacedSpacers;
  label("#dl-sp-print", "Print Spacers", "Printing…", "print");
  if (spacerPrint) spacerPrint.disabled = busy || !hasPlacedSpacers;

  // Hosted: spacer generation and slicer actions stay unavailable on every render - see
  // DP.HOSTED_UNSUPPORTED_TOOLTIP (Fix 019 Item 3).
  if (hosted) {
    ["#dl-sp-plan", "#dl-sp-generate", "#dl-sp-print"].forEach(selector => {
      const node = $(selector);
      if (!node) return;
      node.disabled = true;
      node.title = DP.HOSTED_UNSUPPORTED_TOOLTIP;
    });
  }

  const report = DL.report;
  const warnings = [...DL.warnings, ...(DL.pegboardRefreshError
    ? [`Pegboard placement data could not be refreshed. ${DL.pegboardRefreshError}`]
    : [])].map(text => `<p class="dl-note dl-warning">${escapeHtml(text)}</p>`).join("");
  if (!report) { box.innerHTML = warnings || `<p class="dl-note">Measuring…</p>`; return; }
  // Only actionable problems and warnings stay in this panel.
  const problems = report.problems;
  box.innerHTML = `
    ${problems.length ? `<ul class="dl-problems">${problems.slice(0, 8).map(p => `<li class="${p.type === "height" ? "height" : ""}">${escapeHtml(p.message)}</li>`).join("")}${problems.length > 8 ? `<li>…and ${problems.length - 8} more</li>` : ""}</ul>` : ""}
    ${warnings}`;
};

DP.filteredBins = () => {
  const text = DP.filter.text.trim().toLowerCase();
  const show = DP.filter.show;
  const list = DL.bins.filter(one => {
    if (DL.isSpacer(one)) return false;
    const placed = DL.placedCount(one.id);
    if (show === "in_design" && one.status !== "in_design") return false;
    if (show === "saved" && one.status !== "saved") return false;
    if (show === "printed" && one.status !== "printed") return false;
    if (show === "unplaced" && placed) return false;
    if (show === "placed" && !placed) return false;
    if (show === "unprinted" && one.status === "printed") return false;
    if (show === "stackable" && !DL.stackable(one)) return false;
    if (!text) return true;
    return `${one.name} ${fmt(one.x)}x${fmt(one.y)}x${fmt(one.z)} ${fmt(one.x)} × ${fmt(one.y)} ${one.file} ${one.label} ${one.interior} ${one.kind} ${one.stack}`
      .toLowerCase().includes(text);
  });
  const sorters = {
    height: (a, b) => (DL.isSurface() ? DL.effectiveHeight(b) - DL.effectiveHeight(a) : b.z - a.z)
      || b.x * b.y - a.x * a.y,
    size: (a, b) => b.x * b.y - a.x * a.y || b.z - a.z,
    name: (a, b) => DL.label(a).localeCompare(DL.label(b), undefined, { numeric: true }),
    newest: (a, b) => Number(b.id.slice(1)) - Number(a.id.slice(1)),
  };
  return [...list.sort(sorters[DP.filter.sort] || sorters.height), ...DL.bins.filter(DL.isSpacer)];
};

DP.renderInventory = (force = false) => {
  DP.syncFilterSpace();
  const drawer = DL.drawer();
  const list = $("#dl-inv-list");
  dlSet("#dl-inv-show", DP.filter.show);
  dlSet("#dl-inv-sort", DP.filter.sort);
  DP.prunePrintSelection();
  DP.renderBatch();
  const selectedRow = DL.selectedRow && DL.bin(DL.selectedRow) ? DL.selectedRow : null;
  const counts = DL.bins.map(one => [one.id, DL.placedCount(one.id)]);
  const signature = JSON.stringify([DL.bins, counts, Object.keys(DL.layout.design_specs || {}), DL.report?.planning_heights,
    Boolean(state.runtime.hosted), Boolean(state.slicer?.available),
    DP.filter, [...DP.open], selectedRow, drawer.id, drawer.height, [...DP.printSelected]]);
  if (!dlChanged("inventory", signature) && !force) return;
  if (list.contains(document.activeElement) && document.activeElement.matches("input, select") && !force) return;
  const bins = DP.filteredBins();
  if (!DL.bins.length) {
    list.innerHTML = `<div class="dl-empty">${DL.loaded
      ? `No bins in this Space inventory yet.<br><button type="button" class="button primary dl-small" data-empty-act="design">Design first bin</button>`
      : "Loading the inventory…"}</div>`;
    return;
  }
  if (!bins.length) { list.innerHTML = `<div class="dl-empty">No bins match.</div>`; return; }
  const range = DV.heightRange();
  const kinds = { b4b: "Storage Box", manual: "Added by hand" };
  const kindLabel = one => one.kind === "spacer" ? (one.boundary === "edge" ? "Edge spacer" : "X spacer") : kinds[one.kind];
  list.innerHTML = bins.map(one => {
    const placed = DL.placedCount(one.id);
    const [w, d] = DL.cells(one, drawer);
    const units = value => fmt(value * DL.grid(drawer).step / DL.UNIT);
    const tooTall = !DL.isSurface() && one.z > drawer.height + 1e-6;
    const plan = DL.rowPlanning(one);
    const planningText = DL.isSurface()
      ? one.object_height_mm == null ? "Object height not set"
        : `Object height ${fmt(one.object_height_mm)} mm · Installed planning ${plan?.estimated ? "~" : ""}${fmt(plan?.effective_mm ?? one.z)} mm${plan?.estimated ? " (estimated)" : ""}`
      : "";
    const spacer = DL.isSpacer(one);
    const canPlace = !tooTall && !(spacer && one.boundary === "edge") && (spacer || !placed);
    const color = DV.binColor(one, range);
    const flags = [
      DL.stackable(one) ? DL.stackName(one.stack) : "", kindLabel(one),
      tooTall ? `Taller than ${drawer.name}` : "",
    ].filter(Boolean);
    const classes = [one.id === selectedRow ? "selected" : "", tooTall ? "too-tall" : "",
      spacer ? "spacer-row" : "", one.status === "printed" ? "printed" : ""].filter(Boolean).join(" ");
    const open = DP.open.has(one.id);
    const eligible = DL.printEligible(one);
    const spec = DL.layout?.design_specs?.[one.id];
    const designSource = ["bin", "b4b"].includes(one.kind) && Boolean(spec);
    // A Storage Box case saved by an older version is not a Designer object.
    const editable = designSource && !(typeof isStructuralDesign === "function" && isStructuralDesign(spec));
    const printable = eligible && !state.runtime.hosted && Boolean(state.slicer?.available);
    const statusTracked = !spacer && ["bin", "b4b", "manual"].includes(one.kind);
    const printed = one.status === "printed";
    const picked = !spacer && DP.printSelected.has(one.id);
    const swatch = `<span class="dl-swatch" data-top="${color.top}" data-ink="${color.ink}" title="${fmt(one.z)} mm tall">${DL.badgeLabel(one)}</span>`;
    const check = !spacer
      ? `<input type="checkbox" class="dl-print-select" data-print-select="${escapeHtml(one.id)}" aria-label="Select ${escapeHtml(DL.binNumberLabel(one))} ${escapeHtml(DL.label(one))}"${picked ? " checked" : ""}>`
      : `<span class="dl-print-placeholder" aria-hidden="true"></span>`;
    const lifecycle = spacer
      ? `<small>${dlPlural(placed, "placement")} · ${one.qty} printed</small>`
      : `<small class="dl-status">${placed ? "Placed" : "Unplaced"} · ${DL.statusLabel(one)}</small>`;
    const actions = spacer ? "" : `<div class="dl-row-actions">
          ${editable ? `<button type="button" class="button secondary dl-small" data-act="edit">Edit</button>` : ""}
          <button type="button" class="button danger dl-small" data-act="delete">Delete</button>
          ${designSource ? `<button type="button" class="button secondary dl-small" data-act="duplicate">Duplicate</button>` : ""}
          ${printable ? `<button type="button" class="button secondary dl-small" data-act="print">Print</button>` : ""}
          ${statusTracked ? (printed
            ? `<button type="button" class="button secondary dl-small" data-act="not-printed">Mark Not Printed</button>`
            : `<button type="button" class="button secondary dl-small" data-act="printed">Mark Printed</button>`) : ""}
        </div>`;
    return `
      <div class="dl-bin ${classes}${picked ? " print-selected" : ""}" data-bin="${escapeHtml(one.id)}" data-editable="${editable}" tabindex="0" role="button" aria-label="Select ${escapeHtml(DL.label(one))}" draggable="${canPlace}" title="Select this item${canPlace ? " or drag it into Space" : ""}">
        ${check}
        ${swatch}
        <span class="dl-bin-main">
          <strong>${escapeHtml(DL.label(one))}</strong>
          <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${units(w)}×${units(d)} units</small>
          ${planningText ? `<small>${escapeHtml(planningText)}</small>` : ""}
          ${lifecycle}
          ${flags.length ? `<small class="dl-flags">${escapeHtml(flags.join(" · "))}</small>` : ""}
        </span>
        <button type="button" class="dl-more" data-act="more" aria-expanded="${open}" title="Details">${open ? "▴" : "▾"}</button>
        ${spacer ? `<button type="button" class="dl-remove" data-act="delete" title="Delete" aria-label="Delete ${escapeHtml(DL.label(one))}">✕</button>` : ""}
        ${actions}
      </div>
      ${open ? `<div class="dl-bin-details" data-bin="${escapeHtml(one.id)}">
        <div class="dl-group"><span class="dl-group-label">Bin</span>
          <div class="field-grid two">
            <label>Name<input type="text" data-field="name" maxlength="80" value="${escapeHtml(one.name)}" placeholder="Shows the size when blank"></label>
            <label>Stacking<select data-field="stack">${STACK_OPTIONS.replace(`value="${one.stack}"`, `value="${one.stack}" selected`)}</select></label>
          </div>
        </div>
        ${DL.isSurface() ? `<div class="dl-group"><span class="dl-group-label">Planning</span>
          <label>Object height <span class="unit">mm</span><input type="number" data-field="object_height_mm" min="0.1" step="0.1" value="${one.object_height_mm ?? ""}" placeholder="Not set"></label>
        </div>` : ""}
        <div class="dl-group"><span class="dl-group-label">Size</span>
          <div class="field-grid three">
            <label>Width <span class="unit">mm</span><input type="number" data-field="x" min="1" step="8" value="${fmt(one.x)}"></label>
            <label>Length <span class="unit">mm</span><input type="number" data-field="y" min="1" step="8" value="${fmt(one.y)}"></label>
            <label>Height <span class="unit">mm</span><input type="number" data-field="z" min="1" step="1" value="${fmt(one.z)}" title="${DL.stackable(one) ? "Stack module height" : "Finished height"}"></label>
          </div>
        </div>
        <p>${DL.stackable(one) ? `Adds ${fmt(DL.pitch(one))} mm to a stack; detached height is ${fmt(DL.partHeight(one))} mm including its interlock.<br>` : ""}${one.file ? `File: ${escapeHtml(one.file)}<br>` : ""}${one.label ? `Label: ${escapeHtml(one.label)}<br>` : ""}${one.interior ? `Inside: ${escapeHtml(one.interior)}<br>` : ""}${escapeHtml(one.id)}${one.date ? ` · logged ${escapeHtml(one.date)}` : ""}</p>
      </div>` : ""}`;
  }).join("");
  // The page's security policy refuses inline style attributes, so colours
  // go on through the DOM instead.
  $$(".dl-swatch", list).forEach(node => {
    node.style.background = node.dataset.top;
    node.style.color = node.dataset.ink;
  });
  $$(".dl-bin-details[data-bin]", list).forEach(details => {
    if (DL.layout?.design_specs?.[details.dataset.bin]) {
      $$("[data-field]", details).forEach(field => { field.disabled = true; });
    }
  });
};

// Fix 034 K1: status only - autosave has no off state and no manual Save
// button, so there is no Unsaved-changes/manual-Save branch here any more.
DP.renderSave = () => {
  const status = $("#dl-save-status");
  let text = "";
  let tone = "";
  if (DL.saveState === "saving") text = "Saving…";
  else if (DL.saveState === "error") { text = "Not saved"; tone = "error"; }
  else if (DL.savedAt && DL.saveState === "saved") text = `Saved ${DL.savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  else if (!DL.exists) text = "Inventory starts with the first bin";
  else text = "Saves as you go";
  status.textContent = text;
  status.className = `dl-save-status ${tone}`;
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) SP.renderSpaceInfo();
};

// ------------------------------------------------------------------ mode
//
// Three separate things, each with one owner:
//   - the Space workspace being open (DL.active): the layout is loaded and the
//     Space header shows. It ends only when the folder stops being this Space;
//   - which preview canvas is showing (3D, 2D or Space): the view tabs own it;
//   - which editor owns the left panel (DP.mode): "space" for the layout
//     tools, "design" for the current bin or Storage Box.
// Preview and editor controls synchronize through their owners below.

DP.mode = "design";
DP.modeRequest = 0;
DP.showPendingMode = mode => {
  $$("[data-space-mode]").forEach(button => button.classList.toggle("pending", mode === button.dataset.spaceMode));
  const busy = $("#space-mode-busy");
  if (busy) busy.hidden = !mode;
};

// The layout tools own the left panel (keys, Undo/Redo and the header
// buttons act on the layout only then).
DP.spaceEditing = () => DL.active && DP.mode === "space";

DP.applyMode = () => {
  const open = DL.active;
  const space = DP.spaceEditing();
  document.body.classList.toggle("space-workspace", open);
  // Hides the bin editor's own chrome while the layout tools are showing.
  document.body.classList.toggle("drawer-mode", space);
  $("#drawer-panel").hidden = !space;
  $(".view-tabs").hidden = space;
  $$("[data-space-mode]").forEach(button => {
    const on = button.dataset.spaceMode === DP.mode;
    button.classList.toggle("active", on);
    button.setAttribute("aria-selected", String(on));
    button.setAttribute("aria-pressed", String(on));
    button.tabIndex = on ? 0 : -1;
  });
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) SP.renderSpaceInfo();
  if (typeof updateHistoryButtons === "function") updateHistoryButtons();
};

DP.setMode = mode => {
  if (!DL.active || (mode !== "space" && mode !== "design") || DP.mode === mode) return;
  DP.mode = mode;
  DP.applyMode();
  if (mode === "space") DP.update();
};

// Switching to Space first settles the Designer's autosave, so Inventory is
// authoritative before the Space canvas activates. Switching alone never
// creates a placement or an Inventory row.
DP.ensureInventoryLoaded = async (message = "Could not read the inventory") => {
  if (DL.loaded) return true;
  try {
    await DL.ensureLoaded();
    return true;
  } catch (error) {
    toast(`${message}: ${error.message}`, true, 7000);
    DP.update();
    return false;
  }
};

DP.selectMode = async mode => {
  if (mode !== "space" && mode !== "design") return false;
  if (mode === "space" && (state.folderMode !== "space" || !state.activeSpace)) {
    SP.offerSpacePlanning();
    return false;
  }
  const request = ++DP.modeRequest;
  DP.showPendingMode(mode);
  try {
    if (DP.mode === "design" && mode === "space") {
      if (typeof flushVisibleDesignEditsBeforeModeSwitch === "function" &&
          !(await flushVisibleDesignEditsBeforeModeSwitch())) return false;
      if (typeof flushSpaceDesignAutosave === "function" &&
          !(await flushSpaceDesignAutosave())) return false;
    }
    if (request !== DP.modeRequest) return false;
    if (mode === "space") {
      if (!(await DP.ensureInventoryLoaded()) || request !== DP.modeRequest) return false;
      if (DL.pegboardRefreshError) await DL.retryPegboardLayouts();
      if (request !== DP.modeRequest) return false;
      if (!DL.active) { DL.active = true; DP.build(); DP.applyMode(); }
    }
    DP.setMode(mode);
    activatePreviewView(mode === "space" ? "drawer" : "3d");
    if (mode === "space") DP.update();
    return true;
  } finally {
    if (request === DP.modeRequest) DP.showPendingMode(null);
  }
};

// Open the Space workspace. Starts in Space mode unless a caller asks for Design.
DP.enter = async (preferredMode, inventoryLoaded = false) => {
  if (DL.active) {
    if (preferredMode === "space" || preferredMode === "design") return DP.selectMode(preferredMode);
    return DL.loaded || DP.ensureInventoryLoaded();
  }
  if (!inventoryLoaded && !(await DP.ensureInventoryLoaded())) return false;
  DL.active = true;
  DP.mode = preferredMode === "design" ? "design" : "space";
  DP.build();
  DP.applyMode();
  DP.update();
  // inventoryLoaded is a hint from the caller; DL.loaded is authoritative.
  if (DP.mode === "space") activatePreviewView("drawer");
  return true;
};

// Close the Space workspace (the folder is no longer this Space).
DP.leave = () => {
  if (!DL.active) return;
  DL.active = false;
  DP.modeRequest += 1;
  DP.mode = "design";
  DP.showPendingMode(null);
  if (typeof SP !== "undefined" && SP.cancelInlineEdit) SP.cancelInlineEdit();
  DP.applyMode();
  DV.drag = null;
  DV.pan = null;
  if (DL.dirty) DL.save();
  // The Space canvas has nothing to show any more.
  if ($('.canvas-wrap[data-canvas="drawer"]')?.classList.contains("active")) activatePreviewView("3d");
};

(() => {
  const wrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (!wrap) return;
  DV.wire();
  DL.on(DP.update);
  $$("[data-space-mode]").forEach(button => button.addEventListener("click", () => DP.selectMode(button.dataset.spaceMode)));
  window.addEventListener("beforeunload", event => {
    if (DL.dirty && DL.layout && !DL.layout.settings.autosave) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
