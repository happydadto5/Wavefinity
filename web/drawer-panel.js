"use strict";

// Drawer layout mode - the left panel and switching in and out of the mode.
//
// Sidebar order follows the rest of the app: what the drawer *is* first (its
// size and fit), then spacers, then the inventory you work from, with saving
// pinned at the bottom. Auto layout lives on the preview.

const DP = {
  built: false,
  signatures: {},
  open: new Set(),        // bin ids whose details are expanded
  filter: { text: "", show: "all", sort: "height" },
  printSelected: new Set(), // bin ids picked for the bulk print (session only)
  includeSpaceConnectors: true,
};

try { Object.assign(DP.filter, JSON.parse(localStorage.getItem("wavefinity-drawer-filter") || "{}"), { text: "" }); } catch (_error) {}

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
        <summary>Advanced Settings</summary>
        <div class="field-grid two">
          <label id="dl-name-row">Name<input id="dl-name" type="text" maxlength="40"></label>
        </div>
        <button type="button" id="dl-drawer-delete" class="button danger dl-small">Delete this drawer</button>
      </details>
    </section>

    <section class="control-section open dl-section" aria-label="Spacers">
      <div class="section-heading no-toggle"><span>Spacers</span></div>
      <div class="section-body">
        <div id="dl-stats" class="dl-stats"></div>
        <div class="field-grid two">
          <label class="checkbox-row grid-span-all" title="Build serpentine springs into the edge spacers to absorb real-world tolerance"><span>Flexible fit (recommended)</span><input id="dl-sp-flexible" type="checkbox" checked></label>
          <label>Height <span class="unit">mm</span><input id="dl-sp-height" type="number" min="6" step="1" title="How tall the spacers are"></label>
        </div>
        <div class="dl-action-grid">
          <button type="button" id="dl-sp-plan" class="button secondary" title="Find candidate spacers for the gaps against the back and right walls">Plan / Update Spacers</button>
          <button type="button" id="dl-sp-generate" class="button secondary" title="Generate the selected spacer candidates">Generate Selected Spacers</button>
          <button type="button" id="dl-base-trim" class="button secondary" title="Create a Base Trim around one filled rectangular block of bins">Make Base Trim</button>
          <button type="button" id="dl-sp-print" class="button secondary" title="Choose which spacers to print">Print Spacers…</button>
          <button type="button" id="dl-print" class="button secondary" title="Open this Space's spacers and the connectors they need together in Bambu Studio">Print Spacers + Connectors</button>
        </div>
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

    <section class="control-section open dl-section" aria-label="Inventory">
      <div class="section-heading no-toggle"><span>Inventory</span><span id="dl-inv-count" class="count-badge"></span></div>
      <div class="section-body">
        <div class="dl-inv-tools">
          <input id="dl-inv-search" type="search" placeholder="Search name or size" aria-label="Search the inventory">
          <select id="dl-inv-show" aria-label="Which bins to list">
            <option value="all">Everything</option>
            <option value="printed">Printed</option>
            <option value="unplaced">Not placed yet</option>
            <option value="placed">Placed</option>
            <option value="unprinted">Not printed</option>
            <option value="stackable">Stackable</option>
          </select>
          <select id="dl-inv-sort" aria-label="Sort the inventory">
            <option value="height">Tallest first</option>
            <option value="size">Biggest first</option>
            <option value="name">Name</option>
            <option value="newest">Newest first</option>
          </select>
        </div>
        <div id="dl-batch-tools" class="dl-batch-tools">
          <div class="dl-batch-row">
            <button type="button" id="dl-batch-select-needed" class="button secondary dl-small">Select all not printed</button>
            <button type="button" id="dl-batch-select-all" class="button secondary dl-small">Select all</button>
            <button type="button" id="dl-batch-clear" class="button secondary dl-small">Clear selection</button>
            <span id="dl-batch-summary" class="dl-batch-summary" role="status"></span>
          </div>
          <label class="checkbox-row dl-batch-connectors"><span>Include Space Connectors</span><input id="dl-batch-connectors" type="checkbox" checked></label>
          <button type="button" id="dl-batch-print" class="button secondary wide">Print Selected to Bambu Studio</button>
        </div>
        <div id="dl-inv-list" class="dl-inv-list"></div>
        <details class="dl-details" id="dl-add-details">
          <summary>+ Add a bin by hand</summary>
          <p class="dl-note">For bins printed before logging, or elsewhere. Width, length and height snap to the same sizes a designed bin uses.</p>
          <div class="field-grid three"><label>Name<input id="dl-add-name" type="text" maxlength="80" placeholder="e.g. Hex keys"></label>
            <label>Qty printed<input id="dl-add-qty" type="number" min="0" step="1" value="1"></label>
            <label>Stacking<select id="dl-add-stack">${STACK_OPTIONS}</select></label></div>
          <div class="field-grid three">
            <label>Width <span class="unit">mm</span><input id="dl-add-x" type="text" inputmode="numeric" value="32"></label>
            <label>Length <span class="unit">mm</span><input id="dl-add-y" type="text" inputmode="numeric" value="48"></label>
            <label>Physical height <span class="unit">mm</span><input id="dl-add-z" type="text" inputmode="numeric" value="40" title="Full printed height including lid/stacking foot"></label>
          </div>
          <label id="dl-add-object-row" hidden>Object height <span class="unit">mm</span><input id="dl-add-object-height" type="number" min="0.1" step="0.1" placeholder="Not set"></label>
          <div class="button-row"><button type="button" id="dl-add" class="button secondary">Add to inventory</button></div>
        </details>
      </div>
    </section>

    <section class="dl-savebar" aria-label="Saving">
      <div class="dl-save-row">
        <span id="dl-save-status" class="dl-save-status" role="status"></span>
        <button type="button" id="dl-map" class="button secondary dl-small" title="Print a map of this Space and where each bin goes (Ctrl+P)">Print map</button>
      </div>
    </section>`;
  DV.buildOverlay();
  DP.wire();
  // Hosted capability (Fix 019 Item 3) is recalculated on every render in
  // DP.renderStats() below, not only here - this first pass just avoids a
  // flash of enabled buttons before the first render.
  if (state.runtime.hosted) {
    ["#dl-sp-plan", "#dl-sp-generate", "#dl-sp-print", "#dl-print"].forEach(selector => {
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
// /api/drawer/print outright, so these four stay unavailable in hosted mode
// on every render, not just once at build time.
DP.HOSTED_UNSUPPORTED_TOOLTIP = "Hosted Wavefinity uses the normal Design generator and download-to-folder workflow instead of local Space spacer/slicer operations.";

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
    DL.candidates = [];
    DV.fit();
    DL.emit();
  });
  $("#dl-drawer-add").addEventListener("click", () => {
    const added = DL.defaultDrawer(`Drawer ${DL.layout.drawers.length + 1}`, DL.drawer());
    DL.change(() => { DL.layout.drawers.push(added); DL.layout.active = added.id; });
    DL.candidates = [];
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
  setting("#dl-auto-mode", "auto", "mode", node => node.value);
  setting("#dl-auto-height", "auto", "height_rule", node => node.value);
  setting("#dl-auto-reach", "auto", "height_reach", node => node.value);
  setting("#dl-auto-stack", "auto", "stack_bins", node => node.checked);
  setting("#dl-auto-locked", "auto", "keep_locked", node => node.checked);
  setting("#dl-auto-spacers", "auto", "include_spacers", node => node.checked);
  setting("#dl-sp-flexible", "spacers", "flexible", node => node.checked);
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
  $("#dl-batch-connectors").addEventListener("change", event => {
    DP.includeSpaceConnectors = event.target.checked;
    DP.renderBatch();
  });
  $("#dl-batch-print").addEventListener("click", () =>
    DL.printSelectedBins(DP.printSelectionPayload(), DP.includeSpaceConnectors));
  $("#dl-auto").addEventListener("click", () => DL.runAuto());
  // Empty-state buttons (canvas overlay and Inventory list) share these.
  const emptyAction = event => {
    const act = event.target.closest("[data-empty-act]")?.dataset.emptyAct;
    if (act === "design") DP.designFirstBin();
    else if (act === "add") DP.focusManualAdd();
    else if (act === "edge") DP.finishEdge();
    else if (act === "start-bin") DP.startBinNow();
  };
  $("#dl-inv-list").addEventListener("click", emptyAction);
  $('.canvas-wrap[data-canvas="drawer"]').addEventListener("click", emptyAction);
  $("#dl-candidates").addEventListener("click", event => {
    const card = event.target.closest("[data-candidate]");
    if (card) DL.applyCandidate(Number(card.dataset.candidate));
  });

    $("#dl-sp-plan").addEventListener("click", () => DL.planSpacers());
  $("#dl-sp-generate").addEventListener("click", () => DL.generateSelectedSpacers());
  $("#dl-sp-print").addEventListener("click", () => DP.openSpacerPrintDialog());
  $("#spacer-print-cancel").addEventListener("click", () => $("#spacer-print-dialog").close());
  $("#spacer-print-dialog").addEventListener("click", event => {
    if (event.target === $("#spacer-print-dialog")) $("#spacer-print-dialog").close();
  });
  $("#spacer-print-confirm").addEventListener("click", () => DP.confirmSpacerPrint());
  $("#dl-base-trim").addEventListener("click", async () => {
    const source = DL.baseTrimSource();
    if (!source.ok) {
      toast(source.message, true, 6500);
      return;
    }
    await startBaseTrimFromSpace(source);
  });
  $("#dl-print").addEventListener("click", () => DL.printDrawer());
  $("#dl-map").addEventListener("click", () => DV.printMap());
  const filterChanged = () => {
    try { localStorage.setItem("wavefinity-drawer-filter", JSON.stringify(DP.filter)); } catch (_error) {}
    DP.renderInventory();
  };
  $("#dl-inv-search").addEventListener("input", event => { DP.filter.text = event.target.value; filterChanged(); });
  $("#dl-inv-show").addEventListener("change", event => { DP.filter.show = event.target.value; filterChanged(); });
  $("#dl-inv-sort").addEventListener("change", event => { DP.filter.sort = event.target.value; filterChanged(); });

  const list = $("#dl-inv-list");
  list.addEventListener("click", event => DP.onInventoryClick(event));
  list.addEventListener("dblclick", event => {
    if (event.target.closest("button, input, select, .dl-bin-details")) return;
    const one = DL.bin(event.target.closest("[data-bin]")?.dataset.bin);
    if (one) DL.quickPlace(one);
  });
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
  list.addEventListener("dragstart", event => {
    const one = DL.bin(event.target.closest?.("[data-bin]")?.dataset.bin);
    if (!one) return;
    DV.dragBin = one;
    event.dataTransfer.setData("text/plain", one.id);
    event.dataTransfer.effectAllowed = "copy";
  });
  list.addEventListener("dragend", () => { DV.dragBin = null; DV.drop = null; DV.render(); });

  // Width and Length consume the exact same authoritative rule the normal
  // design form's Width/Length ultimately clamp to - normalizeBinDimension,
  // from app.js - including its maximum, not just the minimum-unit snapping
  // snapToUnit alone gives. A hand-added bin can then never land on a size
  // (including too large) a designed bin never could.
  const wireManualDimension = (selector, axis) => {
    const input = $(selector);
    const normalize = value => normalizeBinDimension(axis, value, value);
    input.addEventListener("blur", () => {
      input.value = String(normalize(number(input.value, state.catalog.base_unit)));
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") { input.blur(); return; }
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      const unit = state.catalog.base_unit;
      const delta = event.key === "ArrowUp" ? unit : -unit;
      input.value = String(normalize(number(input.value, unit) + delta));
      input.select();
    });
    input.addEventListener("wheel", event => {
      event.preventDefault();
      const unit = state.catalog.base_unit;
      const current = number(input.value, unit);
      const delta = event.deltaY < 0 ? unit : -unit;
      const next = normalize(current + delta);
      if (next === current && delta < 0) return;
      input.value = String(next);
    }, { passive: false });
  };
  wireManualDimension("#dl-add-x", "x");
  wireManualDimension("#dl-add-y", "y");

  // Physical height is the full printed height (including any lid/stacking
  // foot); stored/normal-bin Z is the module contribution alone. Convert to
  // module, apply the exact same floor normal Height uses
  // (normalizeBinDimension("z", ...)), then convert back - so the field
  // itself visibly corrects on blur/arrow/wheel instead of only silently
  // changing what gets saved when Add is clicked.
  (() => {
    const input = $("#dl-add-z");
    const engagement = () => DL.stackSteps[$("#dl-add-stack").value] ?? 0;
    const normalize = physical => normalizeBinDimension(
      "z", physical - engagement(), physical - engagement(),
      { baseThickness: state.catalog?.base_rules?.default_mm },
    ) + engagement();
    input.addEventListener("blur", () => {
      input.value = String(normalize(number(input.value, engagement() + 1)));
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") { input.blur(); return; }
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      event.preventDefault();
      const delta = event.key === "ArrowUp" ? 1 : -1;
      input.value = String(normalize(number(input.value, engagement() + 1) + delta));
      input.select();
    });
    input.addEventListener("wheel", event => {
      event.preventDefault();
      const current = number(input.value, engagement() + 1);
      const delta = event.deltaY < 0 ? 1 : -1;
      const next = normalize(current + delta);
      if (next === current && delta < 0) return;
      input.value = String(next);
    }, { passive: false });
  })();

  $("#dl-add").addEventListener("click", async () => {
    const stack = $("#dl-add-stack").value;
    const physicalZ = dlNum($("#dl-add-z").value, 0);
    const engagement = DL.stackSteps[stack] ?? 0;
    // Height floors the same way the normal design form's Height does (see
    // normalizeBinDimension in app.js), using the catalog's default base
    // thickness since a hand-added bin has no design of its own to read one
    // from. physicalZ of 0/blank stays 0 so the missing-height check below
    // still fires instead of silently floating up to the minimum.
    const moduleZ = physicalZ > 0
      ? normalizeBinDimension("z", physicalZ - engagement, physicalZ - engagement,
          { baseThickness: state.catalog?.base_rules?.default_mm })
      : 0;
    const bin = {
      name: $("#dl-add-name").value.trim(),
      qty: Math.max(0, Math.round(dlNum($("#dl-add-qty").value, 1))),
      x: dlNum($("#dl-add-x").value, 0), y: dlNum($("#dl-add-y").value, 0), z: moduleZ,
      stack,
      kind: "manual",
      object_height_mm: DL.isSurface() && $("#dl-add-object-height").value.trim()
        ? dlNum($("#dl-add-object-height").value, 0) : null,
    };
    if (!(bin.x > 0 && bin.y > 0 && bin.z > 0)) { toast("Enter the bin's X, Y and physical height in mm.", true); return; }
    if (await DL.editBins({ new_bins: [bin] })) {
      $("#dl-add-name").value = "";
      $("#dl-add-object-height").value = "";
      toast(`Added ${bin.name || `${fmt(bin.x)} × ${fmt(bin.y)}`} to the inventory.`);
    }
  });

};

// ------------------------------------------------------------ bulk print

DP.prunePrintSelection = () => {
  DP.printSelected = new Set(
    [...DP.printSelected].filter(id => DL.printEligible(DL.bin(id))));
};

DP.resetPrintSelection = () => {
  DP.printSelected = new Set();
  DP.renderInventory(true);
};

DP.selectAllNotPrinted = () => {
  DP.printSelected = new Set(
    DL.bins.filter(one => DL.printNeeded(one) > 0).map(one => one.id));
  DP.renderInventory(true);
};

DP.selectAllPrintable = () => {
  DP.printSelected = new Set(
    DL.bins.filter(one => DL.printEligible(one)).map(one => one.id));
  DP.renderInventory(true);
};

DP.clearPrintSelection = () => {
  DP.printSelected.clear();
  DP.renderInventory(true);
};

DP.printSelectionPayload = () => Object.fromEntries(
  [...DP.printSelected]
    .map(id => DL.bin(id))
    .filter(one => DL.printEligible(one))
    .map(one => [one.id, DL.printCount(one)]));

DP.renderBatch = () => {
  const hosted = Boolean(state.runtime.hosted);
  const tools = $("#dl-batch-tools");
  if (!tools) return;
  tools.hidden = hosted;
  if (hosted) return;
  const rows = [...DP.printSelected].map(id => DL.bin(id)).filter(one => DL.printEligible(one));
  const copies = rows.reduce((sum, one) => sum + DL.printCount(one), 0);
  $("#dl-batch-summary").textContent = rows.length
    ? `${dlPlural(rows.length, "design")} · ${dlPlural(copies, "bin copy", "bin copies")}${DP.includeSpaceConnectors ? " · Space connectors included" : ""}`
    : "";
  dlSet("#dl-batch-connectors", DP.includeSpaceConnectors, "checked");
  const noSlicer = !state.slicer || !state.slicer.available;
  const button = $("#dl-batch-print");
  button.classList.toggle("primary", rows.length >= 2);
  button.classList.toggle("secondary", rows.length < 2);
  button.disabled = !rows.length || noSlicer || Boolean(DL.busy);
  button.title = noSlicer ? "Bambu Studio was not found. Locate it with Change slicer in the bin view." : "";
  button.textContent = DL.busy === "print-bins" ? "Opening Bambu Studio…" : "Print Selected to Bambu Studio";
};

DP.onInventoryClick = async event => {
  if (event.target.closest(".dl-print-select, .dl-print-placeholder")) return;
  const row = event.target.closest("[data-bin]");
  const one = row && DL.bin(row.dataset.bin);
  if (!one) return;
  const action = event.target.closest("[data-act]")?.dataset.act;
  if (action === "more") {
    if (DP.open.has(one.id)) DP.open.delete(one.id); else DP.open.add(one.id);
    DP.renderInventory(true);
  } else if (action === "qty+") DL.editBins({ bin_updates: [{ id: one.id, qty: one.qty + 1 }] });
  else if (action === "qty-") DP.lowerQty(one);
  else if (action === "edit") designerEditInventoryRow(one.id);
  else if (action === "printed") DL.markPrinted(one);
  else if (action === "print") DL.printSelectedBins({ [one.id]: DL.printCount(one) }, false);
  else if (action === "generate") designerGenerateInventoryRow(one.id);
  else if (action === "delete") {
    const placed = DL.placedCount(one.id);
    const ok = await appConfirmAction({
      title: "Remove this bin from inventory?",
      message: `Remove ${DL.label(one)} from the inventory?${placed ? ` Its ${dlPlural(placed, "placed copy", "placed copies")} are removed from the saved layout.` : ""} The print file stays in the folder.`,
      actionLabel: "Remove Bin",
      danger: true,
    });
    if (ok) {
      DP.open.delete(one.id);
      DL.editBins({ delete_ids: [one.id] });
    }
  } else if (!action && !event.target.closest(".dl-bin-details")) {
    const placed = DL.drawer().placements.find(p => p.bin === one.id);
    DL.selected = placed ? DL.key(placed) : null;
    DL.emit();
  }
};

// Printing one fewer should turn an unplaced copy away, not a placed one:
// renumber the top copy into a free slot first.
DP.lowerQty = async one => {
  if (one.qty <= 0) return;
  const next = one.qty - 1;
  const placements = DL.layout.drawers.flatMap(drawer => drawer.placements.filter(p => p.bin === one.id));
  const used = new Set(placements.map(p => p.copy ?? 0));
  const top = placements.find(p => (p.copy ?? 0) === next);
  let free = null;
  for (let copy = 0; copy < next; copy += 1) if (!used.has(copy)) { free = copy; break; }
  if (top && free !== null) {
    const oldKey = DL.key(top);
    const stagedLayout = clone(DL.layout);
    const stagedTop = stagedLayout.drawers.flatMap(drawer => drawer.placements)
      .find(p => DL.key(p) === oldKey);
    stagedTop.copy = free;
    stagedLayout.drawers.forEach(drawer => drawer.placements.forEach(p => {
      if (p.on === oldKey) p.on = DL.key(stagedTop);
    }));
    return DL.editBins({ bin_updates: [{ id: one.id, qty: next }], layout: stagedLayout }, {
      commitLayout: true,
      selected: DL.selected === oldKey ? DL.key(stagedTop) : DL.selected,
    });
  }
  return DL.editBins({ bin_updates: [{ id: one.id, qty: next }] });
};

// The one "go design a bin" jump used by both empty states.
DP.designFirstBin = () => {
  if (typeof markWorkingDesignPending === "function") markWorkingDesignPending();
  DP.setMode("design");
  activatePreviewView("3d");
};

// Surface first run: reopen the direct Base Trim edge design (never the
// arranged-bin source, which cannot exist for an empty Surface).
DP.finishEdge = async () => {
  if (state.activeSpace?.kind !== "surface") return;
  state.surfaceEdgeHandled = false;
  DP.setMode("design");
  await SP.designSurface(state.activeSpace);
};

// Deliberately skip the edge and begin the first bin.
DP.startBinNow = async () => {
  state.surfaceEdgeHandled = true;
  DP.setMode("design");
  await loadFreshOrdinaryDesignForCurrentFolder();
};

// Open the existing manual-add section and put the cursor in it.
DP.focusManualAdd = () => {
  const details = $("#dl-add-details");
  details.open = true;
  details.scrollIntoView({ block: "nearest" });
  $("#dl-add-name").focus();
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
    const count = $("#dl-inv-count");
    if (count) count.textContent = "";
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
  dlSet("#dl-show-empty", Boolean(DL.layout.settings.show_empty), "checked");
  DP.renderDrawer();
  DP.renderAuto();
  DP.renderStats();
  DP.renderSurfaceFill();
  DP.renderInventory();
  DP.renderSave();
  DV.renderEmptyState();
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
  const autoSection = $("#dl-auto-panel");
  const spacerSection = document.querySelector('#drawer-panel [aria-label="Spacers"]');
  const detailsCard = $("#dl-space-details-card");
  if (detailsCard) detailsCard.hidden = DP.singleTypedSpace();
  if (autoSection) autoSection.hidden = pegboard;
  if (spacerSection) spacerSection.hidden = pegboard || surface;
  $("#dl-surface-fill").hidden = !surface;
  $("#dl-add-object-row").hidden = !surface;
  $("#dl-height").closest("label").hidden = surface;
  if ($("#dl-add-details")) $("#dl-add-details").hidden = pegboard;
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

DP.renderAuto = () => {
  const auto = DL.layout.settings.auto;
  dlSet("#dl-auto-mode", auto.mode);
  dlSet("#dl-auto-height", auto.height_rule);
  dlSet("#dl-auto-reach", auto.height_reach);
  dlSet("#dl-auto-stack", Boolean(auto.stack_bins), "checked");
  dlSet("#dl-auto-locked", Boolean(auto.keep_locked), "checked");
  dlSet("#dl-auto-spacers", Boolean(auto.include_spacers), "checked");
  const button = $("#dl-auto");
  const noBins = DL.loaded && !DL.bins.length;
  button.disabled = Boolean(DL.busy) || noBins;
  button.title = noBins ? "Add or design a bin first." : "";
  button.textContent = DL.busy === "auto" ? "Arranging…" : "Auto layout";
  const box = $("#dl-candidates");
  const signature = JSON.stringify([DL.candidates.map(c => c.id), DL.candidateIndex, DL.skipped, DL.autoNotes, DL.layout.active]);
  if (!dlChanged("candidates", signature)) return;
  if (!DL.candidates.length) { box.innerHTML = ""; return; }
  const active = DL.candidates[DL.candidateIndex] || null;
  const names = list => list.map(u => {
    const one = DL.bin(u.bin);
    return `${escapeHtml(one ? DL.label(one) : u.bin)} (${escapeHtml(u.reason)})`;
  }).join(", ");
  box.innerHTML = `
    <p class="dl-note">Pick an arrangement - click to try it, or click another to switch.</p>
    <div class="dl-candidates">${DL.candidates.map((c, index) => `
      <button type="button" class="dl-candidate${index === DL.candidateIndex ? " active" : ""}" data-candidate="${index}" title="${escapeHtml(c.description)}">
        <canvas width="264" height="152" data-thumb="${index}"></canvas>
        <strong>${escapeHtml(c.name)}${index === 0 ? " · best" : ""}</strong>
        <small>${c.stats.placed} of ${c.stats.wanted} bins${c.stats.stacks ? ` · ${dlPlural(c.stats.stacks, "stack")}` : ""}</small>
        <small>${c.stats.height_issues ? dlPlural(c.stats.height_issues, "height clash", "height clashes") : "Tall bins at the back"}</small>
      </button>`).join("")}</div>
    ${active?.unplaced.length ? `<p class="dl-unfit">Auto layout did not place: ${names(active.unplaced)}</p>` : ""}
    ${DL.skipped.length ? `<p class="dl-unfit">Left out: ${names(DL.skipped)}</p>` : ""}
    ${DL.autoNotes.map(note => `<p class="dl-note">${escapeHtml(note)}</p>`).join("")}`;
  DL.candidates.forEach((candidate, index) => DP.drawThumb($(`[data-thumb="${index}"]`, box), candidate));
};

DP.drawThumb = (canvas, candidate) => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const ctx = canvas.getContext("2d");
  const pad = 6;
  const s = Math.min((canvas.width - 2 * pad) / drawer.width, (canvas.height - 2 * pad) / drawer.depth);
  const ox = (canvas.width - drawer.width * s) / 2;
  const oy = (canvas.height - drawer.depth * s) / 2;
  const range = DV.heightRange();
  const stacked = new Set(candidate.placements.filter(p => p.on !== undefined).map(p => p.on));
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f1ebdf";
  ctx.fillRect(ox, oy, drawer.width * s, drawer.depth * s);
  for (const p of candidate.placements) {
    const one = DL.bin(p.bin);
    if (!one || p.on !== undefined) continue;
    let x0, y0, w, d;
    if (p.gx !== undefined) {
      const [cw, cd] = DL.cells(one, drawer);
      x0 = grid.ox + p.gx * DL.UNIT; y0 = grid.oy + p.gy * DL.UNIT; w = cw * grid.step; d = cd * grid.step;
    } else { x0 = p.x; y0 = p.y; w = p.w; d = p.d; }
    ctx.fillStyle = DV.binColor(one, range).top;
    ctx.strokeStyle = stacked.has(DL.key(p)) ? "#146c70" : "rgba(23,37,45,.45)";
    const rect = [ox + x0 * s, oy + (drawer.depth - y0 - d) * s, w * s, d * s];
    ctx.fillRect(...rect);
    ctx.strokeRect(...rect);
  }
};

DP.renderStats = () => {
  const box = $("#dl-stats");
  const spacers = DL.layout.settings.spacers;
  dlSet("#dl-sp-flexible", Boolean(spacers.flexible), "checked");
  dlSet("#dl-sp-height", fmt(spacers.height));

  const busy = Boolean(DL.busy);
  const hosted = Boolean(state.runtime.hosted);
  const label = (id, idle, working, what) => { const node = $(id); node.disabled = busy; node.textContent = DL.busy === what ? working : idle; };
  label("#dl-sp-plan", "Plan / Update Spacers", "Planning…", "spacers");
  label("#dl-sp-generate", "Generate Selected Spacers", "Generating…", "spacers");
  const typedSpace = state.folderMode === "space" && Boolean(state.activeSpace);
  const baseTrim = $("#dl-base-trim");
  if (baseTrim) baseTrim.hidden = typedSpace && state.activeSpace.kind !== "surface";
  label("#dl-base-trim", "Make Base Trim", "Making Base Trim…", "base_trim");
  const printAll = $("#dl-print");
  if (printAll) printAll.disabled = busy;
  // Nothing placed yet: these have nothing to work on, so say why instead of
  // letting the click end in an error.
  const nothingPlaced = DL.loaded && !DL.drawer().placements.length;
  ["#dl-sp-plan", "#dl-sp-generate"].forEach(selector => {
    const node = $(selector);
    if (!nothingPlaced) return;
    node.disabled = true;
    node.title = "Place a bin in the Space first.";
  });
  // Fix 019 Item 4: Generate Selected Spacers must never be an enabled
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
      genNode.title = "Generate the selected spacer candidates";
    }
  }
  const hasPlacedSpacers = DL.drawer().placements.some(
    placement => DL.isSpacer(DL.bin(placement.bin))
  );
  const spacerPrint = $("#dl-sp-print");
  if (spacerPrint) spacerPrint.hidden = !hasPlacedSpacers;
  label("#dl-sp-print", "Print Spacers", "Printing…", "print");
  if (spacerPrint) spacerPrint.disabled = busy || !hasPlacedSpacers;

  // Hosted: these four always stay unavailable, on every render - see
  // DP.HOSTED_UNSUPPORTED_TOOLTIP (Fix 019 Item 3).
  if (hosted) {
    ["#dl-sp-plan", "#dl-sp-generate", "#dl-sp-print", "#dl-print"].forEach(selector => {
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
    const placed = DL.placedCount(one.id);
    if (show === "printed" && one.qty <= 0) return false;
    if (show === "unplaced" && !(one.qty > placed - DL.plannedCount(one.id))) return false;
    if (show === "placed" && !placed) return false;
    if (show === "unprinted" && one.qty > 0 && DL.printNeeded(one) <= 0) return false;
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
  // Spacers sink below real bins whatever the sort.
  return list.sort((a, b) => Number(DL.isSpacer(a)) - Number(DL.isSpacer(b)) || sorters[DP.filter.sort](a, b));
};

// The "Current design" row: session only, so no Qty controls, no remove, no
// drag. It just shows the size and lets you go back to the design.
DP.workingRow = () => {
  const working = DL.working;
  if (!working || working.error) {
    return working?.error ? `<div class="dl-bin dl-working"><span class="dl-bin-main"><strong>Current design</strong>
      <small>${escapeHtml(working.error)}</small></span></div>` : "";
  }
  const one = working.bin;
  const drawer = DL.drawer();
  const [w, d] = DL.cells(one, drawer);
  const units = value => fmt(value * DL.grid(drawer).step / DL.UNIT);
  const fit = DL.workingFit();
  const title = one.name ? `Current design · ${one.name}` : "Current design";
  return `<div class="dl-bin dl-working" data-working="1" title="Not generated yet - only shown so you can plan around it">
    <span class="dl-print-placeholder" aria-hidden="true"></span>
    <span class="dl-swatch dl-working-swatch">${fmt(one.z)}</span>
    <span class="dl-bin-main">
      <strong>${escapeHtml(title)}</strong>
      <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${units(w)}×${units(d)} units</small>
      ${DL.isSurface() ? `<small>${one.object_height_mm == null ? "Object height not set" : `Object height ${fmt(one.object_height_mm)} mm · ${one.planning?.estimated ? "~" : ""}${fmt(one.planning?.effective_mm ?? one.z)} mm installed planning${one.planning?.estimated ? " (estimated)" : ""}`}</small>` : ""}
      <small class="dl-flags">${fit?.ok ? "Not generated yet" : "Does not fit this Space yet"}</small>
    </span>
    <button type="button" class="button secondary dl-small" data-empty-act="design">Edit design</button>
  </div>`;
};

DP.renderInventory = (force = false) => {
  const drawer = DL.drawer();
  const list = $("#dl-inv-list");
  dlSet("#dl-inv-show", DP.filter.show);
  dlSet("#dl-inv-sort", DP.filter.sort);
  DP.prunePrintSelection();
  DP.renderBatch();
  const printed = DL.bins.reduce((sum, one) => sum + (one.qty > 0 ? one.qty : 0), 0);
  $("#dl-inv-count").textContent = `${dlPlural(DL.bins.length, "design")} · ${printed} printed`;
  const selectedBin = DL.selected ? DL.findPlacement(DL.selected)?.placement.bin : null;
  const counts = DL.bins.map(one => [DL.placedCount(one.id), DL.plannedCount(one.id)]);
  const signature = JSON.stringify([DL.bins, counts, Object.keys(DL.layout.design_specs || {}), DL.report?.planning_heights,
    Boolean(state.runtime.hosted), Boolean(state.slicer?.available),
    DP.filter, [...DP.open], selectedBin, drawer.id, drawer.height, [...DP.printSelected],
    DL.working ? [DL.working.key, DL.working.error || "", DL.workingFit()] : null]);
  if (!dlChanged("inventory", signature) && !force) return;
  if (list.contains(document.activeElement) && document.activeElement.matches("input, select") && !force) return;
  const bins = DP.filteredBins();
  const workingRow = DP.workingRow();
  if (!DL.bins.length) {
    list.innerHTML = workingRow || `<div class="dl-empty">${DL.loaded
      ? `No bins in this Space inventory yet.<br><button type="button" class="button primary dl-small" data-empty-act="design">Design first bin</button><br>Or add one by hand below.`
      : "Loading the inventory…"}</div>`;
    return;
  }
  if (!bins.length) { list.innerHTML = `<div class="dl-empty">No bins match.</div>`; return; }
  const range = DV.heightRange();
  const kinds = { b4b: "Storage Box", manual: "Added by hand" };
  const kindLabel = one => one.kind === "spacer" ? (one.boundary === "edge" ? "Edge spacer" : "X spacer") : kinds[one.kind];
  list.innerHTML = workingRow + bins.map(one => {
    const placed = DL.placedCount(one.id);
    const planned = DL.plannedCount(one.id);
    const [w, d] = DL.cells(one, drawer);
    const units = value => fmt(value * DL.grid(drawer).step / DL.UNIT);
    const tooTall = !DL.isSurface() && one.z > drawer.height + 1e-6;
    const plan = DL.rowPlanning(one);
    const planningText = DL.isSurface()
      ? one.object_height_mm == null ? "Object height not set"
        : `Object height ${fmt(one.object_height_mm)} mm · Installed planning ${plan?.estimated ? "~" : ""}${fmt(plan?.effective_mm ?? one.z)} mm${plan?.estimated ? " (estimated)" : ""}`
      : "";
    const freePrinted = one.qty - (placed - planned);
    const canPlace = !tooTall && !(one.kind === "spacer" && one.boundary === "edge");
    const color = DV.binColor(one, range);
    const flags = [
      DL.stackable(one) ? DL.stackName(one.stack) : "", kindLabel(one),
      tooTall ? `Taller than ${drawer.name}` : "", one.qty <= 0 ? "Not printed" : "",
    ].filter(Boolean);
    const holding = DL.drawersHolding(one.id);
    const classes = [
      one.id === selectedBin ? "selected" : "", freePrinted <= 0 && one.qty > 0 ? "all-placed" : "",
      one.qty <= 0 ? "unprinted" : "", tooTall ? "too-tall" : "",
    ].filter(Boolean).join(" ");
    const open = DP.open.has(one.id);
    const eligible = DL.printEligible(one);
    const spec = DL.layout?.design_specs?.[one.id];
    const designSource = ["bin", "b4b"].includes(one.kind) && Boolean(spec);
    const printable = eligible && !state.runtime.hosted && Boolean(state.slicer?.available);
    const quantityTracked = ["bin", "b4b", "manual"].includes(one.kind);
    const needed = DL.printNeeded(one);
    const printFlag = needed > 0 ? `${needed} needed` : "";
    const picked = eligible && DP.printSelected.has(one.id);
    return `
      <div class="dl-bin ${classes}${picked ? " print-selected" : ""}" data-bin="${escapeHtml(one.id)}" draggable="${canPlace}" title="${canPlace ? "Drag into the Space, or double-click to place" : ""}">
        ${eligible
          ? `<input type="checkbox" class="dl-print-select" data-print-select="${escapeHtml(one.id)}" aria-label="Select ${escapeHtml(DL.label(one))} for printing"${picked ? " checked" : ""}>`
          : `<span class="dl-print-placeholder" aria-hidden="true"></span>`}
        <span class="dl-swatch" data-top="${color.top}" data-ink="${color.ink}" title="${DL.stackable(one) ? `${fmt(one.z)} mm stack module; ${fmt(DL.partHeight(one))} mm detached` : `${fmt(one.z)} mm tall`}">${fmt(one.z)}${DL.stackable(one) ? "<i>⇅</i>" : ""}</span>
        <span class="dl-bin-main">
          <strong>${escapeHtml(DL.label(one))}</strong>
          <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${units(w)}×${units(d)} units</small>
          ${planningText ? `<small>${escapeHtml(planningText)}</small>` : ""}
          ${flags.length || printFlag ? `<small class="dl-flags">${escapeHtml([...flags, printFlag].filter(Boolean).join(" · "))}</small>` : ""}
        </span>
        <span class="dl-placed" title="${holding.length ? `In ${escapeHtml(holding.join(", "))}` : "Not placed"}">${placed - planned}/${one.qty}<small>${planned ? `+${planned} planned` : "placed"}</small></span>
        <span class="dl-qty" title="How many you have printed">
          <button type="button" data-act="qty-" ${one.qty <= 0 ? "disabled" : ""} aria-label="One fewer printed">−</button>
          <span>${one.qty}</span>
          <button type="button" data-act="qty+" aria-label="One more printed">+</button>
        </span>
        <button type="button" class="dl-more" data-act="more" aria-expanded="${open}" title="Details">${open ? "▴" : "▾"}</button>
        <button type="button" class="dl-remove" data-act="delete" title="Remove from the inventory" aria-label="Remove ${escapeHtml(DL.label(one))} from the inventory">✕</button>
        ${designSource || quantityTracked || printable ? `<div class="dl-row-actions">
          ${designSource ? `<button type="button" class="button secondary dl-small" data-act="edit">Edit</button>` : ""}
          ${quantityTracked ? `<button type="button" class="button secondary dl-small" data-act="printed">Mark Printed</button>` : ""}
          ${printable ? `<button type="button" class="button secondary dl-small" data-act="print">Print</button>` : ""}
          ${designSource ? `<button type="button" class="button secondary dl-small" data-act="generate">Generate</button>` : ""}
        </div>` : ""}
      </div>
      ${open ? `<div class="dl-bin-details" data-bin="${escapeHtml(one.id)}">
        <div class="field-grid three">
          <label>Name<input type="text" data-field="name" maxlength="80" value="${escapeHtml(one.name)}" placeholder="Shows the size when blank"></label>
          <label>Qty printed<input type="number" data-field="qty" min="0" step="1" value="${one.qty}"></label>
          <label>Stacking<select data-field="stack">${STACK_OPTIONS.replace(`value="${one.stack}"`, `value="${one.stack}" selected`)}</select></label>
        </div>
        ${DL.isSurface() ? `<label>Object height <span class="unit">mm</span><input type="number" data-field="object_height_mm" min="0.1" step="0.1" value="${one.object_height_mm ?? ""}" placeholder="Not set"></label>` : ""}
        <div class="field-grid three">
          <label>Width <span class="unit">mm</span><input type="number" data-field="x" min="1" step="8" value="${fmt(one.x)}"></label>
          <label>Length <span class="unit">mm</span><input type="number" data-field="y" min="1" step="8" value="${fmt(one.y)}"></label>
          <label>Height <span class="unit">mm</span><input type="number" data-field="z" min="1" step="1" value="${fmt(one.z)}" title="${DL.stackable(one) ? "Stack module height" : "Finished height"}"></label>
        </div>
        <p>${DL.stackable(one) ? `Adds ${fmt(DL.pitch(one))} mm to a stack; detached height is ${fmt(DL.partHeight(one))} mm including its interlock.<br>` : ""}${one.file ? `File: ${escapeHtml(one.file)}<br>` : ""}${one.label ? `Label: ${escapeHtml(one.label)}<br>` : ""}${one.interior ? `Inside: ${escapeHtml(one.interior)}<br>` : ""}${escapeHtml(one.id)}${one.date ? ` · logged ${escapeHtml(one.date)}` : ""}</p>
        <div class="button-row">
          <button type="button" class="button danger dl-small" data-act="delete">Remove from inventory</button>
        </div>
      </div>` : ""}`;
  }).join("");
  // The page's security policy refuses inline style attributes, so colours
  // go on through the DOM instead.
  $$(".dl-swatch", list).forEach(node => {
    node.style.background = node.dataset.top;
    node.style.color = node.dataset.ink;
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

DP.mode = "space";

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

// Fix 034 A: switching to Space always shows the exact current working bin -
// refresh it before the Space canvas activates, so a stale/no-longer-current
// design is never shown. Switching alone never creates a placement or an
// Inventory row.
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
  if (mode !== "space" && mode !== "design") return;
  if (DP.mode === "design" && mode === "space" &&
      typeof flushVisibleDesignEditsBeforeModeSwitch === "function" &&
      !(await flushVisibleDesignEditsBeforeModeSwitch())) {
    return;
  }
  if (mode === "space" && typeof workingDesignForSpace === "function" && workingDesignForSpace() &&
      typeof maybePromptSurfaceObjectHeight === "function" && !(await maybePromptSurfaceObjectHeight())) return;
  DP.setMode(mode);
  if (mode === "space") {
    if (!(await DP.ensureInventoryLoaded())) return;
    if (DL.pegboardRefreshError) {
      await DL.refreshWorking({ refreshPegboard: false });
      await DL.retryPegboardLayouts();
    } else {
      await DL.refreshWorking();
    }
    if (!DL.active || DP.mode !== "space") return;
    activatePreviewView("drawer");
    DP.update();
  } else if ($('.view-tab[data-view="drawer"]')?.classList.contains("active")) {
    activatePreviewView("3d");
  }
};

// Open the Space workspace. Starts in Design mode when there is a current
// design to work on, otherwise Space mode.
DP.enter = async (preferredMode, inventoryLoaded = false) => {
  if (DL.active) {
    if (preferredMode === "space" || preferredMode === "design") DP.setMode(preferredMode);
    if (!DL.loaded) await DP.ensureInventoryLoaded();
    return;
  }
  DL.active = true;
  DP.mode = preferredMode === "space" || preferredMode === "design"
    ? preferredMode
    : (typeof workingDesignForSpace === "function" && workingDesignForSpace() ? "design" : "space");
  DP.build();
  DP.applyMode();
  DP.update();
  // inventoryLoaded is a hint from the caller; DL.loaded is authoritative.
  if (!DL.loaded) await DP.ensureInventoryLoaded();
};

// Close the Space workspace (the folder is no longer this Space).
DP.leave = () => {
  if (!DL.active) return;
  DL.active = false;
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
  // Showing the Space preview opens the workspace; hiding it does not close it.
  new MutationObserver(() => {
    if (wrap.classList.contains("active") && (!DL.active || !DL.loaded)) DP.enter("space");
  }).observe(wrap, { attributes: true, attributeFilter: ["class"] });
  window.addEventListener("beforeunload", event => {
    if (DL.dirty && DL.layout && !DL.layout.settings.autosave) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
