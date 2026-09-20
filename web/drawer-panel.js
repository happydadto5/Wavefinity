"use strict";

// Drawer layout mode - the left panel and switching in and out of the mode.
//
// Order follows the rest of the app: what the drawer *is* first (its size and
// fit), then the big action (Auto layout) with its options under it, then what
// is left over (space, spacers, connectors), then the inventory you work from,
// and the save controls pinned at the bottom.

const DP = {
  built: false,
  signatures: {},
  open: new Set(),        // bin ids whose details are expanded
  filter: { text: "", show: "all", sort: "height" },
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

DP.build = () => {
  if (DP.built) return;
  DP.built = true;
  $("#drawer-panel").innerHTML = `
    <section class="dl-card" aria-label="Drawer">
      <div class="dl-drawer-row">
        <label id="dl-drawer-label-row"><span id="dl-drawer-label">Drawer</span><select id="dl-drawer"></select></label>
        <button type="button" id="dl-drawer-add" class="button secondary dl-small" title="Add another drawer; it shares this inventory">+ Drawer</button>
      </div>
      <div class="field-grid three">
        <label>Width <span class="unit">mm</span><input id="dl-width" type="number" min="16" step="1" title="Inside, left to right"></label>
        <label>Depth <span class="unit">mm</span><input id="dl-depth" type="number" min="16" step="1" title="Inside, front to back"></label>
        <label>Max height <span class="unit">mm</span><input id="dl-height" type="number" min="6" step="1" title="The tallest bin or stack that fits: the inside height, less whatever the drawer above needs to close"></label>
      </div>
      <div id="dl-canonical-row" class="dl-canonical-row" hidden>
        <span class="dl-note">Name and size come from this Space.</span>
        <button type="button" id="dl-edit-drawer" class="button secondary dl-small">Edit drawer</button>
      </div>
      <p id="dl-grid-note" class="dl-note"></p>
      <details class="dl-details" id="dl-fit-details">
        <summary>Drawer settings</summary>
        <div class="field-grid two">
          <label id="dl-name-row">Name<input id="dl-name" type="text" maxlength="40"></label>
          <label>Fit clearance <span class="unit">mm</span><input id="dl-clearance" type="number" min="0.6" step="0.1" title="Total slack per axis so the bins drop in. At least 0.6 mm for the wave crests."></label>
          <label>Grid sits<select id="dl-anchor"><option value="front-left">Against front-left corner</option><option value="center">Centred</option></select></label>
          <label>Width direction<select id="dl-axis"><option value="x">Width left ↔ right</option><option value="y">Width front ↔ back</option></select></label>
          <label>Snap to<select id="dl-snap" title="The wave repeats every 4 mm, so bins may also sit half a unit along from each other"><option value="8">8 mm - whole units</option><option value="4">4 mm - half units</option></select></label>
        </div>
        <p class="dl-note">Bins never turn sideways on their own: a quarter-turned bin's waves clash with its neighbours. <em>Width direction</em> turns every bin in this drawer together, which is safe.</p>
        <button type="button" id="dl-drawer-delete" class="button danger dl-small">Delete this drawer</button>
      </details>
    </section>

    <section class="control-section open dl-section" aria-label="Auto layout">
      <div class="section-heading no-toggle"><span>Auto layout</span></div>
      <div class="section-body">
        <button type="button" id="dl-auto" class="button primary wide dl-auto-button">Auto layout</button>
        <div class="dl-options">
          <label>Arrange<select id="dl-auto-mode">
            <option value="rearrange">Everything not locked</option>
            <option value="fill">Only new bins, around the rest</option>
          </select></label>
          <label>Tall bins<select id="dl-auto-height">
            <option value="strict">Always behind shorter ones</option>
            <option value="prefer">Behind shorter ones if they can</option>
            <option value="ignore">Anywhere</option>
          </select></label>
          <label>Height check<select id="dl-auto-reach" title="Which bins in front count when keeping short bins out of sight">
            <option value="column">Anything in front of it</option>
            <option value="adjacent">Only the bin right in front</option>
          </select></label>
          <label class="checkbox-row" title="Snap stackable bins of the same size into stacks, as tall as the drawer takes"><span>Stack stackable bins</span><input id="dl-auto-stack" type="checkbox"></label>
          <label class="checkbox-row"><span>Keep locked bins in place</span><input id="dl-auto-locked" type="checkbox"></label>
          <label class="checkbox-row"><span>Include spacers</span><input id="dl-auto-spacers" type="checkbox"></label>
        </div>
        <div id="dl-candidates"></div>
      </div>
    </section>

    <section class="control-section open dl-section" aria-label="Spacers and connectors">
      <div class="section-heading no-toggle"><span>Spacers &amp; connectors</span></div>
      <div class="section-body">
        <div id="dl-stats" class="dl-stats"></div>
        <div class="field-grid two">
          <label class="checkbox-row" style="grid-column: 1 / -1" title="Build serpentine springs into the edge spacers to absorb real-world tolerance"><span>Flexible fit (recommended)</span><input id="dl-sp-flexible" type="checkbox" checked></label>
          <label>Height <span class="unit">mm</span><input id="dl-sp-height" type="number" min="6" step="1" title="How tall the spacers are"></label>
        </div>
        <div class="dl-action-grid">
          <button type="button" id="dl-sp-plan" class="button secondary" title="Find candidate spacers for the gaps against the back and right walls">Plan / Update Spacers</button>
          <button type="button" id="dl-sp-generate" class="button secondary" title="Generate the selected spacer candidates">Generate Selected Spacers</button>
          <button type="button" id="dl-connectors" class="button secondary" title="Save a file for every connector this layout needs, with how many to print">Make connectors</button>
          <button type="button" id="dl-base-trim" class="button secondary" title="Create a Base Trim around one filled rectangular block of bins">Make Base Trim</button>
          <button type="button" id="dl-sp-print" class="button secondary" title="Choose which spacers to print">Print Spacers…</button>
          <button type="button" id="dl-print" class="button secondary" title="Open this drawer's spacers and connectors together in Bambu Studio">Print Drawer (All)</button>
        </div>
      </div>
    </section>

    <section class="control-section open dl-section" aria-label="Inventory">
      <div class="section-heading no-toggle"><span>Inventory</span><span id="dl-inv-count" class="count-badge"></span></div>
      <div class="section-body">
        <div id="dl-todo"></div>
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
        <div id="dl-inv-list" class="dl-inv-list"></div>
        <label class="checkbox-row dl-new-printed" title="Off: a newly generated bin starts at Qty 0 until you mark it printed. On: it counts as one printed copy straight away."><span>New bins count as printed</span><input id="dl-new-printed" type="checkbox"></label>
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
          <div class="button-row"><button type="button" id="dl-add" class="button secondary">Add to inventory</button></div>
        </details>
      </div>
    </section>

    <section class="dl-savebar" aria-label="Saving">
      <div id="dl-space-info-block" class="space-info-card b4b-card" hidden style="margin-bottom: 16px;">
        <h3 class="b4b-card-title">Space Info</h3>
        <div class="space-info-details">
          <strong id="dl-space-info-name"></strong>
          <div id="dl-space-info-type"></div>
          <div id="dl-space-info-size" class="muted"></div>
        </div>
        <div class="button-row" style="margin-top: 8px;">
          <button id="dl-space-info-edit" class="button secondary" type="button">Edit</button>
          <button id="dl-space-info-show" class="button secondary" type="button">Show Folder</button>
          <button id="dl-space-info-new-space" class="button secondary" type="button" hidden>New Space</button>
        </div>
      </div>
      <label class="checkbox-row" title="New bins start with the bin settings from the last bin generated or printed in this Space. Interior parts and names start fresh."><span>Keep bin defaults</span><input id="dl-keep-bin-defaults" type="checkbox"></label>
      <div class="dl-save-row">
        <label class="checkbox-row" title="Save the layout to the inventory file after every change"><span>Auto-save</span><input id="dl-autosave" type="checkbox"></label>
        <span id="dl-save-status" class="dl-save-status" role="status"></span>
        <button type="button" id="dl-map" class="button secondary dl-small" title="Print a map of this drawer and where each bin goes (Ctrl+P)">Print map</button>
        <button type="button" id="dl-save" class="button primary dl-small" hidden>Save layout</button>
      </div>
    </section>`;
  DP.wire();
  // The dl-space-info-* buttons above did not exist at startup, when
  // SP.wire() wired the normal "space-info" prefix - wire only this
  // Drawer-panel prefix now that it exists, so neither button gets a
  // duplicate listener.
  if (typeof wireInfoButtons === "function") wireInfoButtons("dl-space-info");
  DV.buildOverlay();
  if (state.runtime.hosted) {
    ["#dl-sp-plan", "#dl-sp-generate", "#dl-sp-print", "#dl-connectors"].forEach(selector => {
      const button = $(selector);
      if (button) {
        button.disabled = true;
        button.title = "Use the normal designer to generate downloadable files in hosted Wavefinity.";
      }
    });
  }
};

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
  drawerField("#dl-clearance", "clearance", positive(drawerHardClearance()));
  drawerField("#dl-name", "name", raw => raw.trim() || null);
  drawerField("#dl-anchor", "anchor", raw => raw);
  drawerField("#dl-axis", "bin_axis", raw => raw);
  $("#dl-snap").addEventListener("change", event => {
    const snap = Number(event.target.value) === 4 ? 4 : 8;
    let moved = 0;
    DL.change(() => {
      const drawer = DL.drawer();
      drawer.snap = snap;
      // Back to whole units: anything sitting half a unit along snaps to the
      // nearest whole one (the report flags any overlap that makes).
      if (snap === 8) drawer.placements.filter(DL.onGrid).forEach(p => {
        const gx = Math.round(p.gx), gy = Math.round(p.gy);
        if (gx !== p.gx || gy !== p.gy) moved += 1;
        Object.assign(p, { gx, gy });
      });
    });
    if (moved) toast(`${dlPlural(moved, "bin")} moved onto whole 8 mm units.`);
  });

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
  $("#dl-drawer-delete").addEventListener("click", () => {
    const drawer = DL.drawer();
    if (DL.layout.drawers.length < 2) return;
    if (!confirm(`Delete ${drawer.name}? Its bins go back to the inventory list.`)) return;
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

  setting("#dl-new-printed", null, "new_bins_printed", node => node.checked);
  $("#dl-auto").addEventListener("click", () => DL.runAuto());
  $("#dl-edit-drawer").addEventListener("click", () => SP.editSpace());
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
  $('.canvas-wrap[data-canvas="drawer"]').addEventListener("click", event => {
    if (event.target.closest("#dl-design-spot")) DP.designSpot();
  });
  
  
    $("#dl-sp-plan").addEventListener("click", () => DL.planSpacers());
  $("#dl-sp-generate").addEventListener("click", () => DL.generateSelectedSpacers());
  $("#dl-sp-print").addEventListener("click", () => DP.openSpacerPrintDialog());
  $("#spacer-print-cancel").addEventListener("click", () => $("#spacer-print-dialog").close());
  $("#spacer-print-dialog").addEventListener("click", event => {
    if (event.target === $("#spacer-print-dialog")) $("#spacer-print-dialog").close();
  });
  $("#spacer-print-confirm").addEventListener("click", () => DP.confirmSpacerPrint());
  $("#dl-connectors").addEventListener("click", () => DL.makeConnectors());
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
  $("#dl-todo").addEventListener("click", event => {
    const one = DL.bin(event.target.closest("[data-printed]")?.dataset.printed);
    if (one) DL.markPrinted(one);
  });

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
    const field = event.target.dataset.field;
    const id = event.target.closest("[data-bin]")?.dataset.bin;
    if (!field || !id) return;
    const text = field === "name" || field === "stack";
    DL.editBins({ bin_updates: [{ id, [field]: text ? event.target.value : dlNum(event.target.value, 0) }] });
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
    };
    if (!(bin.x > 0 && bin.y > 0 && bin.z > 0)) { toast("Enter the bin's X, Y and physical height in mm.", true); return; }
    if (await DL.editBins({ new_bins: [bin] })) {
      $("#dl-add-name").value = "";
      toast(`Added ${bin.name || `${fmt(bin.x)} × ${fmt(bin.y)}`} to the inventory.`);
    }
  });

  $("#dl-autosave").addEventListener("change", event => {
    DL.layout.settings.autosave = event.target.checked;
    DL.dirty = true;
    if (event.target.checked) DL.save(); else DL.emit();
  });
  $("#dl-keep-bin-defaults").addEventListener("change", event => {
    SP.setKeepBinDefaults(event.target.checked);
  });
  $("#dl-save").addEventListener("click", () => DL.save());
};

DP.onInventoryClick = event => {
  const row = event.target.closest("[data-bin]");
  const one = row && DL.bin(row.dataset.bin);
  if (!one) return;
  const action = event.target.closest("[data-act]")?.dataset.act;
  if (action === "more") {
    if (DP.open.has(one.id)) DP.open.delete(one.id); else DP.open.add(one.id);
    DP.renderInventory(true);
  } else if (action === "qty+") DL.editBins({ bin_updates: [{ id: one.id, qty: one.qty + 1 }] });
  else if (action === "qty-") DP.lowerQty(one);
  else if (action === "printed") DL.markPrinted(one);
  else if (action === "delete") {
    const placed = DL.placedCount(one.id);
    if (confirm(`Remove ${DL.label(one)} from the inventory?${placed ? ` Its ${dlPlural(placed, "placed copy", "placed copies")} come out of every drawer.` : ""} The print file stays in the folder.`)) {
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
DP.lowerQty = one => {
  if (one.qty <= 0) return;
  const next = one.qty - 1;
  const placements = DL.layout.drawers.flatMap(drawer => drawer.placements.filter(p => p.bin === one.id));
  const used = new Set(placements.map(p => p.copy ?? 0));
  const top = placements.find(p => (p.copy ?? 0) === next);
  let free = null;
  for (let copy = 0; copy < next; copy += 1) if (!used.has(copy)) { free = copy; break; }
  if (top && free !== null) {
    const oldKey = DL.key(top);
    DL.change(() => {
      top.copy = free;
      DL.layout.drawers.forEach(drawer => drawer.placements.forEach(p => { if (p.on === oldKey) p.on = DL.key(top); }));
    }, { history: false });
    if (DL.selected === oldKey) DL.selected = DL.key(top);
  }
  DL.editBins({ bin_updates: [{ id: one.id, qty: next }] });
};

// The one "go design a bin" jump used by both empty states.
DP.designFirstBin = () => activatePreviewView("3d");

// Surface first run: reopen the direct Base Trim edge design (never the
// arranged-bin source, which cannot exist for an empty Surface).
DP.finishEdge = async () => {
  if (state.activeSpace?.kind !== "surface") return;
  state.surfaceEdgeHandled = false;
  await SP.designSurface(state.activeSpace);
};

// Deliberately skip the edge and begin the first bin.
DP.startBinNow = async () => {
  state.surfaceEdgeHandled = true;
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
DP.isCanonicalDrawer = () => state.folderMode === "space" && state.activeSpace?.kind === "drawer"
  && DL.layout.drawers.length === 1;

// Send the largest empty spot to the bin editor as a new bin's size.
DP.designSpot = () => {
  const spot = DL.report?.opens?.[0];
  if (!spot) return;
  if (typeof b4bEnabled === "function" && b4bEnabled()) { toast("Set Bin type to Single bin first, then try again.", true); return; }
  const drawer = DL.drawer();
  const round8 = mm => Math.max(8, Math.floor(mm / 8) * 8);
  const [x, y] = drawer.bin_axis === "y" ? [round8(spot.d_mm), round8(spot.w_mm)] : [round8(spot.w_mm), round8(spot.d_mm)];
  activatePreviewView("3d");
  const previous = clone(state.design);
  state.design.box.x = x;
  state.design.box.y = y;
  const mode = stackMode();
  const engagement = DL.stackSteps[mode] ?? 0;
  const maxModuleHeight = drawer.height - engagement;
  if (maxModuleHeight <= 0) {
    toast(`This gap is too short: the ${fmt(engagement)} mm stacking foot alone is taller than ${drawer.name}'s ${fmt(drawer.height)} mm height. Switch to a single bin (no stacking) or pick a taller drawer.`, true, 8000);
    return;
  }
  let heightNote = `Keep it ${fmt(drawer.height)} mm tall or less.`;
  if (state.design.box.z > maxModuleHeight) state.design.box.z = Math.floor(maxModuleHeight);
  if (engagement > 0) {
    heightNote = `Keep module height at ${fmt(Math.floor(maxModuleHeight))} mm or less so the ${fmt(engagement)} mm stacking foot fits within this drawer's ${fmt(drawer.height)} mm height.`;
  }
  syncForm();
  state.binResizePending = true;
  state.canGenerate = false;
  updateGenerateAvailability();
  changedDesign(previous);
  toast(`Bin set to ${fmt(x)} × ${fmt(y)} mm to fill the gap in ${drawer.name}. ${heightNote}`, false, 6000);
};

// Opens the grouped selection dialog before anything is sent to the slicer -
// clicking Print Spacers… must never silently print every unprinted row.
DP.openSpacerPrintDialog = () => {
  const groups = DL.spacerPrintGroups();
  if (!groups.length) { toast("No spacers placed in this drawer yet.", true); return; }
  DP.spacerPrintGroups = groups;
  const container = $("#spacer-print-table-container");
  container.innerHTML = `
    <table class="spacer-print-table">
      <thead><tr><th></th><th>Size</th><th>Flexible/Rigid</th><th>Qty in drawer</th><th>Printed</th><th>Qty to print</th></tr></thead>
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
  if (!DL.layout) return;
  dlSet("#dl-show-empty", Boolean(DL.layout.settings.show_empty), "checked");
  DP.renderDrawer();
  DP.renderAuto();
  DP.renderStats();
  DP.renderOpenSpaces();
  DP.renderTodo();
  DP.renderInventory();
  DP.renderSave();
  DV.renderEmptyState();
  DV.render();
};

DP.syncHistory = () => {
  const undo = $("#undo-design");
  const redo = $("#redo-design");
  if (undo) undo.disabled = !DL.history.length;
  if (redo) redo.disabled = !DL.future.length;
};

DP.renderDrawer = () => {
  const drawer = DL.drawer();
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
    drawerLabel.textContent = legacyMultiDrawer ? "Previous drawers" : "Drawer";
    const labelRow = $("#dl-drawer-label-row");
    if (labelRow) labelRow.title = legacyMultiDrawer
      ? "Legacy drawers from before this folder became this Space. This Space keeps one physical drawer; new drawers can't be added here."
      : "";
  }

  const canonical = DP.isCanonicalDrawer();
  ["#dl-width", "#dl-depth", "#dl-height"].forEach(selector => { $(selector).disabled = canonical; });
  $("#dl-name-row").hidden = canonical;
  $("#dl-canonical-row").hidden = !canonical;

  dlSet("#dl-width", fmt(drawer.width));
  dlSet("#dl-depth", fmt(drawer.depth));
  dlSet("#dl-height", fmt(drawer.height));
  dlSet("#dl-name", drawer.name);
  dlSet("#dl-clearance", fmt(drawer.clearance));
  dlSet("#dl-anchor", drawer.anchor);
  dlSet("#dl-axis", drawer.bin_axis);
  dlSet("#dl-snap", String(Number(drawer.snap) === 4 ? 4 : 8));
  $("#dl-drawer-delete").disabled = DL.layout.drawers.length < 2;
  const grid = DL.grid(drawer);
  const wall = (drawer.boundary === "mating" ? Math.max(0, drawer.clearance) : Math.max(drawerHardClearance(), drawer.clearance)) / 2;
  const edges = [["left", grid.gapLeft], ["right", grid.gapRight], ["front", grid.gapFront], ["back", grid.gapBack]]
    .map(([side, gap]) => [side, gap - wall]).filter(([, play]) => play >= 0.1)
    .map(([side, play]) => `${side} ${play.toFixed(1)} mm`);
  const units = value => fmt(value * grid.step / DL.UNIT);
  $("#dl-grid-note").textContent = `Grid ${units(grid.cols)} × ${units(grid.rows)} units (${fmt(grid.cols * grid.step)} × ${fmt(grid.rows * grid.step)} mm). `
    + (edges.length ? `Left over at the edges: ${edges.join(", ")}.` : "No spare strip at the edges.");
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
    <p class="dl-note">Pick an arrangement - click to try it; Undo goes back.</p>
    <div class="dl-candidates">${DL.candidates.map((c, index) => `
      <button type="button" class="dl-candidate${index === DL.candidateIndex ? " active" : ""}" data-candidate="${index}" title="${escapeHtml(c.description)}">
        <canvas width="264" height="152" data-thumb="${index}"></canvas>
        <strong>${escapeHtml(c.name)}${index === 0 ? " · best" : ""}</strong>
        <small>${c.stats.placed} of ${c.stats.wanted} bins${c.stats.stacks ? ` · ${dlPlural(c.stats.stacks, "stack")}` : ""}</small>
        <small>${c.stats.height_issues ? dlPlural(c.stats.height_issues, "height clash", "height clashes") : "Tall bins at the back"}</small>
      </button>`).join("")}</div>
    ${active?.unplaced.length ? `<p class="dl-unfit">Didn't fit: ${names(active.unplaced)}</p>` : ""}
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
  const label = (id, idle, working, what) => { const node = $(id); node.disabled = busy; node.textContent = DL.busy === what ? working : idle; };
  label("#dl-sp-plan", "Plan / Update Spacers", "Planning…", "spacers");
  label("#dl-sp-generate", "Generate Selected Spacers", "Generating…", "spacers");
  label("#dl-connectors", "Make connectors", "Making connectors…", "connectors");
  label("#dl-base-trim", "Make Base Trim", "Making Base Trim…", "base_trim");
  // Nothing placed yet: these have nothing to work on, so say why instead of
  // letting the click end in an error.
  const nothingPlaced = DL.loaded && !DL.drawer().placements.length;
  ["#dl-sp-plan", "#dl-sp-generate", "#dl-connectors"].forEach(selector => {
    const node = $(selector);
    if (!nothingPlaced) return;
    node.disabled = true;
    node.title = "Place a bin in the drawer first.";
  });
  const hasPlacedSpacers = DL.drawer().placements.some(
    placement => DL.isSpacer(DL.bin(placement.bin))
  );
  const spacerPrint = $("#dl-sp-print");
  if (spacerPrint) spacerPrint.hidden = !hasPlacedSpacers;
  label("#dl-sp-print", "Print Spacers", "Printing…", "print");
  if (spacerPrint) spacerPrint.disabled = busy || !hasPlacedSpacers;

  const report = DL.report;
  const warnings = DL.warnings.map(text => `<p class="dl-note dl-warning">${escapeHtml(text)}</p>`).join("");
  if (!report) { box.innerHTML = warnings || `<p class="dl-note">Measuring…</p>`; return; }
  // Fill/empty/largest-gap/connector-count summaries used to live here; they
  // were numbers nobody acted on. The two live open-space rectangles now show
  // on the drawer view itself (DP.renderOpenSpaces), next to the layout they
  // describe. Only actionable problems and warnings stay in this panel.
  const problems = report.problems;
  box.innerHTML = `
    ${problems.length ? `<ul class="dl-problems">${problems.slice(0, 8).map(p => `<li class="${p.type === "height" ? "height" : ""}">${escapeHtml(p.message)}</li>`).join("")}${problems.length > 8 ? `<li>…and ${problems.length - 8} more</li>` : ""}</ul>` : ""}
    ${warnings}`;
};

// The one or two biggest genuine bin-placement openings, shown right on the
// drawer view (see the matching dashed outlines in DV.render) instead of as
// a left-panel statistic. Always both mm and the user-facing 8 mm unit.
DP.renderOpenSpaces = () => {
  const box = $("#dl-open-spaces");
  if (!box) return;
  const opens = DL.report?.opens;
  if (!opens) { box.innerHTML = ""; return; }
  if (!opens.length) { box.innerHTML = `<p class="dl-note">No open space left for another bin.</p>`; return; }
  const drawer = DL.drawer();
  box.innerHTML = opens.map((spot, index) => {
    const [wMm, dMm] = drawer.bin_axis === "y" ? [spot.d_mm, spot.w_mm] : [spot.w_mm, spot.d_mm];
    return `<div class="dl-open-spot">
      <span>${index === 0 ? "Largest open space" : "Next open space"}</span>
      <div>${fmt(wMm)} × ${fmt(dMm)} mm<small>${DL.mmToUnits(wMm)} × ${DL.mmToUnits(dMm)} units</small></div>
      ${index === 0 ? `<button type="button" id="dl-design-spot" class="dl-link" title="Open the bin editor with this size">Design a Storage Box</button>` : ""}
    </div>`;
  }).join("");
};

// Bins placed before they were printed, across every drawer: the print list.
DP.renderTodo = () => {
  const box = $("#dl-todo");
  const todo = DL.bins.map(one => [one, DL.plannedCount(one.id)]).filter(([, count]) => count > 0);
  if (!dlChanged("todo", JSON.stringify(todo.map(([one, count]) => [one.id, count, one.name, one.qty])))) return;
  box.innerHTML = todo.length ? `
    <div class="dl-todo">
      <strong>To print</strong> <small>placed in a drawer before they were printed</small>
      <ul>${todo.map(([one, count]) => `<li><span>${count} × ${escapeHtml(DL.label(one))} <small>${escapeHtml(DL.sizeText(one))}</small></span>
        <button type="button" class="dl-link" data-printed="${escapeHtml(one.id)}" title="Raise its printed Qty by ${count}">Mark printed</button></li>`).join("")}</ul>
    </div>` : "";
};

DP.filteredBins = () => {
  const text = DP.filter.text.trim().toLowerCase();
  const show = DP.filter.show;
  const list = DL.bins.filter(one => {
    const placed = DL.placedCount(one.id);
    if (show === "printed" && one.qty <= 0) return false;
    if (show === "unplaced" && !(one.qty > placed - DL.plannedCount(one.id))) return false;
    if (show === "placed" && !placed) return false;
    if (show === "unprinted" && one.qty > 0) return false;
    if (show === "stackable" && !DL.stackable(one)) return false;
    if (!text) return true;
    return `${one.name} ${fmt(one.x)}x${fmt(one.y)}x${fmt(one.z)} ${fmt(one.x)} × ${fmt(one.y)} ${one.file} ${one.label} ${one.interior} ${one.kind} ${one.stack}`
      .toLowerCase().includes(text);
  });
  const sorters = {
    height: (a, b) => b.z - a.z || b.x * b.y - a.x * a.y,
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
    <span class="dl-swatch dl-working-swatch">${fmt(one.z)}</span>
    <span class="dl-bin-main">
      <strong>${escapeHtml(title)}</strong>
      <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${units(w)}×${units(d)} units</small>
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
  dlSet("#dl-new-printed", Boolean(DL.layout.settings.new_bins_printed), "checked");
  const printed = DL.bins.reduce((sum, one) => sum + (one.qty > 0 ? one.qty : 0), 0);
  $("#dl-inv-count").textContent = `${dlPlural(DL.bins.length, "design")} · ${printed} printed`;
  const selectedBin = DL.selected ? DL.findPlacement(DL.selected)?.placement.bin : null;
  const counts = DL.bins.map(one => [DL.placedCount(one.id), DL.plannedCount(one.id)]);
  const signature = JSON.stringify([DL.bins, counts, DP.filter, [...DP.open], selectedBin, drawer.id, drawer.height, drawer.bin_axis, drawer.snap,
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
    const tooTall = one.z > drawer.height + 1e-6;
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
    return `
      <div class="dl-bin ${classes}" data-bin="${escapeHtml(one.id)}" draggable="${canPlace}" title="${canPlace ? "Drag into the drawer, or double-click to place" : ""}">
        <span class="dl-swatch" data-top="${color.top}" data-ink="${color.ink}" title="${DL.stackable(one) ? `${fmt(one.z)} mm stack module; ${fmt(DL.partHeight(one))} mm detached` : `${fmt(one.z)} mm tall`}">${fmt(one.z)}${DL.stackable(one) ? "<i>⇅</i>" : ""}</span>
        <span class="dl-bin-main">
          <strong>${escapeHtml(DL.label(one))}</strong>
          <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${units(w)}×${units(d)} units</small>
          ${flags.length ? `<small class="dl-flags">${escapeHtml(flags.join(" · "))}</small>` : ""}
        </span>
        <span class="dl-placed" title="${holding.length ? `In ${escapeHtml(holding.join(", "))}` : "Not in a drawer"}">${placed - planned}/${one.qty}<small>${planned ? `+${planned} planned` : "placed"}</small></span>
        <span class="dl-qty" title="How many you have printed">
          <button type="button" data-act="qty-" ${one.qty <= 0 ? "disabled" : ""} aria-label="One fewer printed">−</button>
          <span>${one.qty}</span>
          <button type="button" data-act="qty+" aria-label="One more printed">+</button>
        </span>
        <button type="button" class="dl-more" data-act="more" aria-expanded="${open}" title="Details">${open ? "▴" : "▾"}</button>
        <button type="button" class="dl-remove" data-act="delete" title="Remove from the inventory" aria-label="Remove ${escapeHtml(DL.label(one))} from the inventory">✕</button>
      </div>
      ${open ? `<div class="dl-bin-details" data-bin="${escapeHtml(one.id)}">
        <div class="field-grid three">
          <label>Name<input type="text" data-field="name" maxlength="80" value="${escapeHtml(one.name)}" placeholder="Shows the size when blank"></label>
          <label>Qty printed<input type="number" data-field="qty" min="0" step="1" value="${one.qty}"></label>
          <label>Stacking<select data-field="stack">${STACK_OPTIONS.replace(`value="${one.stack}"`, `value="${one.stack}" selected`)}</select></label>
        </div>
        <div class="field-grid three">
          <label>Width <span class="unit">mm</span><input type="number" data-field="x" min="1" step="8" value="${fmt(one.x)}"></label>
          <label>Length <span class="unit">mm</span><input type="number" data-field="y" min="1" step="8" value="${fmt(one.y)}"></label>
          <label>Height <span class="unit">mm</span><input type="number" data-field="z" min="1" step="1" value="${fmt(one.z)}" title="${DL.stackable(one) ? "Stack module height" : "Finished height"}"></label>
        </div>
        <p>${DL.stackable(one) ? `Adds ${fmt(DL.pitch(one))} mm to a stack; detached height is ${fmt(DL.partHeight(one))} mm including its interlock.<br>` : ""}${one.file ? `File: ${escapeHtml(one.file)}<br>` : ""}${one.label ? `Label: ${escapeHtml(one.label)}<br>` : ""}${one.interior ? `Inside: ${escapeHtml(one.interior)}<br>` : ""}${escapeHtml(one.id)}${one.date ? ` · logged ${escapeHtml(one.date)}` : ""}</p>
        <div class="button-row">
          ${planned ? `<button type="button" class="button secondary dl-small" data-act="printed">Mark ${planned} printed</button>` : ""}
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

DP.renderSave = () => {
  const settings = DL.layout.settings;
  dlSet("#dl-keep-bin-defaults", Boolean(state.keepBinDefaults), "checked");
  dlSet("#dl-autosave", Boolean(settings.autosave), "checked");
  const status = $("#dl-save-status");
  let text = "";
  let tone = "";
  if (DL.saveState === "saving") text = "Saving…";
  else if (DL.saveState === "error") { text = "Not saved"; tone = "error"; }
  else if (DL.dirty && !settings.autosave) { text = "Unsaved changes"; tone = "dirty"; }
  else if (DL.savedAt && DL.saveState === "saved") text = `Saved ${DL.savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  else if (!DL.exists) text = "Inventory starts with the first bin";
  else text = settings.autosave ? "Saves as you go" : "Up to date";
  status.textContent = text;
  status.className = `dl-save-status ${tone}`;
  const save = $("#dl-save");
  save.hidden = Boolean(settings.autosave);
  save.disabled = DL.saving || (!DL.dirty && DL.saveState !== "error");
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) SP.renderSpaceInfo();
};

// ------------------------------------------------------------------ mode

DP.enter = async () => {
  DL.active = true;
  document.body.classList.add("drawer-mode");
  $("#drawer-panel").hidden = false;
  DP.build();
  DP.update();
  try {
    await DL.load();
  } catch (error) {
    toast(`Could not read the inventory: ${error.message}`, true, 7000);
  }
};

DP.leave = () => {
  DL.active = false;
  document.body.classList.remove("drawer-mode");
  $("#drawer-panel").hidden = true;
  DV.drag = null;
  DV.pan = null;
  if (typeof updateHistoryButtons === "function") updateHistoryButtons();
  if (DL.dirty && DL.layout?.settings.autosave) DL.save();
};

(() => {
  const wrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (!wrap) return;
  DV.wire();
  DL.on(DP.update);
  new MutationObserver(() => {
    const on = wrap.classList.contains("active");
    if (on && !DL.active) DP.enter();
    else if (!on && DL.active) DP.leave();
  }).observe(wrap, { attributes: true, attributeFilter: ["class"] });
  window.addEventListener("beforeunload", event => {
    if (DL.dirty && DL.layout && !DL.layout.settings.autosave) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
})();
