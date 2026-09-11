"use strict";

// Drawer layout mode - the left panel and switching in and out of the mode.
//
// Order follows the rest of the app: what the drawer *is* first (its size and
// fit), then the big action (Auto layout) with its options under it, then what
// is left over (space and spacers), then the inventory you work from, and the
// save controls pinned at the bottom.

const DP = {
  built: false,
  signatures: {},
  open: new Set(),        // bin ids whose details are expanded
  filter: { text: "", show: "printed", sort: "height" },
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

DP.build = () => {
  if (DP.built) return;
  DP.built = true;
  $("#drawer-panel").innerHTML = `
    <section class="dl-card" aria-label="Drawer">
      <div class="dl-drawer-row">
        <label>Drawer<select id="dl-drawer"></select></label>
        <button type="button" id="dl-drawer-add" class="button secondary dl-small" title="Add another drawer; it shares this inventory">+ Drawer</button>
      </div>
      <div class="field-grid three">
        <label>Width <span class="unit">mm</span><input id="dl-width" type="number" min="16" step="1" title="Inside, left to right"></label>
        <label>Depth <span class="unit">mm</span><input id="dl-depth" type="number" min="16" step="1" title="Inside, front to back"></label>
        <label>Height <span class="unit">mm</span><input id="dl-height" type="number" min="6" step="1" title="Inside, floor to where the drawer above closes"></label>
      </div>
      <p id="dl-grid-note" class="dl-note"></p>
      <details class="dl-details" id="dl-fit-details">
        <summary>Drawer settings</summary>
        <div class="field-grid two">
          <label>Name<input id="dl-name" type="text" maxlength="40"></label>
          <label>Fit clearance <span class="unit">mm</span><input id="dl-clearance" type="number" min="0.6" step="0.1" title="Total slack per axis so the bins drop in. At least 0.6 mm for the wave crests."></label>
          <label>Grid sits<select id="dl-anchor"><option value="front-left">Against front-left corner</option><option value="center">Centred</option></select></label>
          <label>Bin width (X) runs<select id="dl-axis"><option value="x">Left ↔ right</option><option value="y">Front ↔ back</option></select></label>
        </div>
        <p class="dl-note">Bins never turn sideways on their own: a quarter-turned bin's waves clash with its neighbours. <em>Bin width runs</em> turns every bin in this drawer together, which is safe.</p>
        <div class="dl-subhead"><strong>Keep-out zones</strong><button type="button" id="dl-keepout-add" class="dl-link">+ Add</button></div>
        <p class="dl-note">Slide rails, screw heads, a rounded corner - anywhere bins must not go. Measured in mm from the inside front-left corner.</p>
        <div id="dl-keepouts"></div>
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
          <label class="checkbox-row"><span>Keep locked bins in place</span><input id="dl-auto-locked" type="checkbox"></label>
          <label class="checkbox-row"><span>Include spacer bins</span><input id="dl-auto-spacers" type="checkbox"></label>
        </div>
        <div id="dl-candidates"></div>
      </div>
    </section>

    <section class="control-section open dl-section" aria-label="Space and spacers">
      <div class="section-heading no-toggle"><span>Space &amp; spacers</span></div>
      <div class="section-body">
        <div id="dl-stats" class="dl-stats"></div>
        <div class="field-grid three">
          <label>Fill<select id="dl-sp-fill">
            <option value="all">Edges + empty cells</option>
            <option value="edges">Edge strips only</option>
            <option value="cells">Empty cells only</option>
          </select></label>
          <label>Height <span class="unit">mm</span><input id="dl-sp-height" type="number" min="6" step="1"></label>
          <label>Longest piece <span class="unit">mm</span><input id="dl-sp-max" type="number" min="16" step="1" title="Split anything longer so it fits your print bed"></label>
        </div>
        <div class="button-row equal">
          <button type="button" id="dl-sp-make" class="button secondary" title="Save spacer files to the save location, add them to the inventory and place them">Make spacers</button>
          <button type="button" id="dl-sp-remove" class="button secondary" title="Take this drawer's spacers out (they stay in the inventory)">Take spacers out</button>
        </div>
      </div>
    </section>

    <section class="control-section open dl-section" aria-label="Inventory">
      <div class="section-heading no-toggle"><span>Inventory</span><span id="dl-inv-count" class="count-badge"></span></div>
      <div class="section-body">
        <div class="dl-inv-tools">
          <input id="dl-inv-search" type="search" placeholder="Search name or size" aria-label="Search the inventory">
          <select id="dl-inv-show" aria-label="Which bins to list">
            <option value="printed">Printed</option>
            <option value="unplaced">Not placed yet</option>
            <option value="placed">Placed</option>
            <option value="unprinted">Not printed (Qty 0)</option>
            <option value="all">Everything</option>
          </select>
          <select id="dl-inv-sort" aria-label="Sort the inventory">
            <option value="height">Tallest first</option>
            <option value="size">Biggest first</option>
            <option value="name">Name</option>
            <option value="newest">Newest first</option>
          </select>
        </div>
        <div id="dl-inv-list" class="dl-inv-list"></div>
        <details class="dl-details" id="dl-add-details">
          <summary>+ Add a bin by hand</summary>
          <p class="dl-note">For bins printed before logging, or elsewhere. Sizes round up to whole 8 mm units in a drawer.</p>
          <div class="field-grid two"><label>Name<input id="dl-add-name" type="text" maxlength="80" placeholder="e.g. Hex keys"></label>
            <label>Qty printed<input id="dl-add-qty" type="number" min="0" step="1" value="1"></label></div>
          <div class="field-grid three">
            <label>X <span class="unit">mm</span><input id="dl-add-x" type="number" min="1" step="8" value="32"></label>
            <label>Y <span class="unit">mm</span><input id="dl-add-y" type="number" min="1" step="8" value="48"></label>
            <label>Z <span class="unit">mm</span><input id="dl-add-z" type="number" min="1" step="1" value="40"></label>
          </div>
          <div class="button-row"><button type="button" id="dl-add" class="button secondary">Add to inventory</button></div>
        </details>
      </div>
    </section>

    <section class="dl-savebar" aria-label="Saving">
      <button type="button" id="dl-file" class="dl-file-button" title="Change the save location - each folder has its own inventory"></button>
      <div class="dl-save-row">
        <label class="checkbox-row" title="Save the layout to the inventory file after every change"><span>Auto-save</span><input id="dl-autosave" type="checkbox"></label>
        <span id="dl-save-status" class="dl-save-status" role="status"></span>
        <button type="button" id="dl-open-file" class="button secondary dl-small" title="Open the inventory file">Open file</button>
        <button type="button" id="dl-save" class="button primary dl-small">Save layout</button>
      </div>
    </section>`;
  DP.wire();
  DV.buildOverlay();
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
  drawerField("#dl-clearance", "clearance", positive(0.55));
  drawerField("#dl-name", "name", raw => raw.trim() || null);
  drawerField("#dl-anchor", "anchor", raw => raw);
  drawerField("#dl-axis", "bin_axis", raw => raw);

  $("#dl-drawer").addEventListener("change", event => {
    DL.change(() => { DL.layout.active = event.target.value; }, { history: false });
    DL.selected = null;
    DL.candidates = [];
    DV.fit();
    DL.emit();
  });
  $("#dl-drawer-add").addEventListener("click", () => {
    const current = DL.drawer();
    const added = DL.defaultDrawer(`Drawer ${DL.layout.drawers.length + 1}`, current);
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
  $("#dl-keepout-add").addEventListener("click", () => DL.change(() => {
    DL.drawer().keepouts.push({ x: 0, y: 0, w: 16, d: 16 });
  }));
  $("#dl-keepouts").addEventListener("change", event => {
    const row = event.target.closest("[data-keepout]");
    const value = dlNum(event.target.value);
    if (!row || value === null) return;
    DL.change(() => { DL.drawer().keepouts[Number(row.dataset.keepout)][event.target.dataset.k] = Math.max(0, value); });
  });
  $("#dl-keepouts").addEventListener("click", event => {
    const row = event.target.closest("[data-remove]")?.closest("[data-keepout]");
    if (row) DL.change(() => { DL.drawer().keepouts.splice(Number(row.dataset.keepout), 1); });
  });

  const setting = (selector, group, key, read) => $(selector).addEventListener("change", event => {
    DL.change(() => { DL.layout.settings[group][key] = read(event.target); }, { history: false });
  });
  setting("#dl-auto-mode", "auto", "mode", node => node.value);
  setting("#dl-auto-height", "auto", "height_rule", node => node.value);
  setting("#dl-auto-locked", "auto", "keep_locked", node => node.checked);
  setting("#dl-auto-spacers", "auto", "include_spacers", node => node.checked);
  setting("#dl-sp-fill", "spacers", "fill", node => node.value);
  setting("#dl-sp-height", "spacers", "height", node => Math.max(6, dlNum(node.value, 20)));
  setting("#dl-sp-max", "spacers", "max_length", node => Math.max(16, dlNum(node.value, 250)));
  $("#dl-auto").addEventListener("click", () => DL.runAuto());
  $("#dl-candidates").addEventListener("click", event => {
    const card = event.target.closest("[data-candidate]");
    if (card) DL.applyCandidate(Number(card.dataset.candidate));
  });
  $("#dl-stats").addEventListener("click", event => {
    if (event.target.closest("#dl-design-spot")) DP.designSpot();
  });
  $("#dl-sp-make").addEventListener("click", () => DL.makeSpacers());
  $("#dl-sp-remove").addEventListener("click", () => DL.removeSpacers());

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
    if (event.target.closest("button, input, .dl-bin-details")) return;
    const one = DL.bin(event.target.closest("[data-bin]")?.dataset.bin);
    if (one) DL.quickPlace(one);
  });
  list.addEventListener("change", event => {
    const field = event.target.dataset.field;
    const id = event.target.closest("[data-bin]")?.dataset.bin;
    if (!field || !id) return;
    DL.editBins({ bin_updates: [{ id, [field]: field === "name" ? event.target.value : dlNum(event.target.value, 0) }] });
  });
  list.addEventListener("dragstart", event => {
    const one = DL.bin(event.target.closest?.("[data-bin]")?.dataset.bin);
    if (!one) return;
    DV.dragBin = one;
    event.dataTransfer.setData("text/plain", one.id);
    event.dataTransfer.effectAllowed = "copy";
  });
  list.addEventListener("dragend", () => { DV.dragBin = null; DV.drop = null; DV.render(); });

  $("#dl-add").addEventListener("click", async () => {
    const bin = {
      name: $("#dl-add-name").value.trim(),
      qty: Math.max(0, Math.round(dlNum($("#dl-add-qty").value, 1))),
      x: dlNum($("#dl-add-x").value, 0), y: dlNum($("#dl-add-y").value, 0), z: dlNum($("#dl-add-z").value, 0),
      kind: "manual",
    };
    if (!(bin.x > 0 && bin.y > 0 && bin.z > 0)) { toast("Enter the bin's X, Y and Z in mm.", true); return; }
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
  $("#dl-save").addEventListener("click", () => DL.save());
  $("#dl-open-file").addEventListener("click", async () => {
    try {
      if (!DL.exists) await DL.save();
      await api("/api/show-log", { output: DL.output ?? DL.folder() });
    } catch (error) {
      toast(error.message, true);
    }
  });
  $("#dl-file").addEventListener("click", () => DP.changeFolder());
};

DP.onInventoryClick = event => {
  const row = event.target.closest("[data-bin]");
  const one = row && DL.bin(row.dataset.bin);
  if (!one) return;
  const action = event.target.closest("[data-act]")?.dataset.act;
  if (action === "place") DL.quickPlace(one);
  else if (action === "more") {
    if (DP.open.has(one.id)) DP.open.delete(one.id); else DP.open.add(one.id);
    DP.renderInventory(true);
  } else if (action === "qty+") DL.editBins({ bin_updates: [{ id: one.id, qty: one.qty + 1 }] });
  else if (action === "qty-") DP.lowerQty(one);
  else if (action === "delete") {
    if (confirm(`Delete ${DL.label(one)} from the inventory? Its placed copies come out of every drawer. (To keep the record, set Qty to 0 instead.)`)) {
      DP.open.delete(one.id);
      DL.editBins({ delete_ids: [one.id] });
    }
  } else if (!action && !event.target.closest(".dl-bin-details")) {
    const placed = DL.drawer().placements.find(p => p.bin === one.id);
    DL.selected = placed ? DL.key(placed) : null;
    DL.emit();
  }
};

// Printing one fewer should take the unplaced copy away, not a placed one:
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
    const wasSelected = DL.selected === DL.key(top);
    DL.change(() => { top.copy = free; }, { history: false });
    if (wasSelected) DL.selected = DL.key(top);
  }
  DL.editBins({ bin_updates: [{ id: one.id, qty: next }] });
};

DP.changeFolder = async () => {
  if (DL.dirty) await DL.save();
  await selectOutputFolder();
  if (state.output !== DL.output) {
    DL.layout = null;
    DL.dirty = false;
    DL.candidates = [];
    DP.signatures = {};
    try { await DL.load(); } catch (error) { toast(error.message, true, 7000); }
  }
};

// Send the largest empty spot to the bin editor as a new bin's size.
DP.designSpot = () => {
  const spot = DL.report?.largest;
  if (!spot) return;
  if (typeof b4bEnabled === "function" && b4bEnabled()) { toast("Set Bin type to Single bin first, then try again.", true); return; }
  const drawer = DL.drawer();
  const [x, y] = drawer.bin_axis === "y" ? [spot.d_mm, spot.w_mm] : [spot.w_mm, spot.d_mm];
  activatePreviewView("3d");
  const previous = clone(state.design);
  state.design.box.x = x;
  state.design.box.y = y;
  if (state.design.box.z > drawer.height) state.design.box.z = Math.floor(drawer.height);
  syncForm();
  state.binResizePending = true;
  state.canGenerate = false;
  updateGenerateAvailability();
  changedDesign(previous);
  toast(`Bin set to ${fmt(x)} × ${fmt(y)} mm to fill the gap in ${drawer.name}. Keep it ${fmt(drawer.height)} mm tall or less.`, false, 6000);
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
  DP.renderInventory();
  DP.renderSave();
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
    select.value = drawer.id;
  }
  dlSet("#dl-width", fmt(drawer.width));
  dlSet("#dl-depth", fmt(drawer.depth));
  dlSet("#dl-height", fmt(drawer.height));
  dlSet("#dl-name", drawer.name);
  dlSet("#dl-clearance", fmt(drawer.clearance));
  dlSet("#dl-anchor", drawer.anchor);
  dlSet("#dl-axis", drawer.bin_axis);
  $("#dl-drawer-delete").disabled = DL.layout.drawers.length < 2;
  const grid = DL.grid(drawer);
  const wall = Math.max(0.55, drawer.clearance) / 2;
  const edges = [["left", grid.gapLeft], ["right", grid.gapRight], ["front", grid.gapFront], ["back", grid.gapBack]]
    .map(([side, gap]) => [side, gap - wall]).filter(([, play]) => play >= 0.1)
    .map(([side, play]) => `${side} ${play.toFixed(1)} mm`);
  $("#dl-grid-note").textContent = `Grid ${grid.cols} × ${grid.rows} units (${grid.cols * 8} × ${grid.rows * 8} mm). `
    + (edges.length ? `Left over at the edges: ${edges.join(", ")}.` : "No spare strip at the edges.");
  const zones = JSON.stringify([drawer.id, drawer.keepouts]);
  if (dlChanged("keepouts", zones) && !$("#dl-keepouts").contains(document.activeElement)) {
    $("#dl-keepouts").innerHTML = drawer.keepouts.map((zone, index) => `
      <div class="dl-keepout" data-keepout="${index}">
        ${["x", "y", "w", "d"].map(k => `<label>${{ x: "From left", y: "From front", w: "Width", d: "Depth" }[k]}<input type="number" min="0" step="1" data-k="${k}" value="${fmt(zone[k])}"></label>`).join("")}
        <button type="button" data-remove title="Remove this keep-out zone" aria-label="Remove">✕</button>
      </div>`).join("");
  }
};

DP.renderAuto = () => {
  const auto = DL.layout.settings.auto;
  dlSet("#dl-auto-mode", auto.mode);
  dlSet("#dl-auto-height", auto.height_rule);
  dlSet("#dl-auto-locked", Boolean(auto.keep_locked), "checked");
  dlSet("#dl-auto-spacers", Boolean(auto.include_spacers), "checked");
  const button = $("#dl-auto");
  button.disabled = Boolean(DL.busy);
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
        <small>${c.stats.placed} of ${c.stats.wanted} bins · ${c.stats.fill}% full</small>
        <small>${c.stats.height_issues ? `${dlPlural(c.stats.height_issues, "height clash", "height clashes")}` : "Tall bins at the back"} · ${dlPlural(c.stats.connectors, "connector")}</small>
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
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#f1ebdf";
  ctx.fillRect(ox, oy, drawer.width * s, drawer.depth * s);
  for (const p of candidate.placements) {
    const one = DL.bin(p.bin);
    if (!one) continue;
    let x0, y0, w, d;
    if (p.gx !== undefined) {
      const [uw, ud] = DL.units(one, drawer);
      x0 = grid.ox + p.gx * 8; y0 = grid.oy + p.gy * 8; w = uw * 8; d = ud * 8;
    } else { x0 = p.x; y0 = p.y; w = p.w; d = p.d; }
    ctx.fillStyle = DV.binColor(one, range).top;
    ctx.strokeStyle = "rgba(23,37,45,.45)";
    const rect = [ox + x0 * s, oy + (drawer.depth - y0 - d) * s, w * s, d * s];
    ctx.fillRect(...rect);
    ctx.strokeRect(...rect);
  }
};

DP.renderStats = () => {
  const box = $("#dl-stats");
  const spacers = DL.layout.settings.spacers;
  dlSet("#dl-sp-fill", spacers.fill);
  dlSet("#dl-sp-height", fmt(spacers.height));
  dlSet("#dl-sp-max", fmt(spacers.max_length));
  const making = DL.busy === "spacers";
  $("#dl-sp-make").disabled = Boolean(DL.busy);
  $("#dl-sp-make").textContent = making ? "Making spacers…" : "Make spacers";
  $("#dl-sp-remove").disabled = !DL.drawer().placements.some(p => DL.isSpacer(DL.bin(p.bin)));
  const report = DL.report;
  const warnings = DL.warnings.map(text => `<p class="dl-note dl-warning">${escapeHtml(text)}</p>`).join("");
  if (!report) { box.innerHTML = warnings || `<p class="dl-note">Measuring…</p>`; return; }
  const drawer = DL.drawer();
  const wall = Math.max(0.55, drawer.clearance) / 2;
  const shimmed = new Set(drawer.placements.filter(p => p.side).map(p => p.side));
  const edges = ["left", "right", "front", "back"]
    .map(side => [side, report.grid[`gap_${side}`] - wall])
    .filter(([, play]) => play >= 0.1)
    .map(([side, play]) => `${side} ${play.toFixed(1)} mm${shimmed.has(side) ? " (shimmed)" : ""}`);
  const mixed = report.connectors.filter(c => c.heights[0] !== c.heights[1]);
  const same = report.connectors.filter(c => c.heights[0] === c.heights[1]).reduce((sum, c) => sum + c.count, 0);
  const spot = report.largest;
  const [spotX, spotY] = spot && drawer.bin_axis === "y" ? [spot.d_mm, spot.w_mm] : [spot?.w_mm, spot?.d_mm];
  const problems = report.problems;
  box.innerHTML = `
    <div class="dl-stat"><span>Filled</span><div><strong>${report.fill}%</strong> <small>${report.cells.used} of ${report.cells.total} cells</small>
      <div class="dl-meter"><span></span></div></div></div>
    <div class="dl-stat"><span>Empty</span><div>${report.cells.free ? `${report.free_mm2.toLocaleString()} mm² of grid (${dlPlural(report.cells.free, "cell")})` : "No empty grid cells"}
      <small>${edges.length ? `Edges: ${edges.join(", ")}` : "No spare strip at the edges"}</small></div></div>
    ${spot ? `<div class="dl-stat"><span>Largest gap</span><div>${fmt(spotX)} × ${fmt(spotY)} mm <small>as a bin's X × Y</small>
      <button type="button" id="dl-design-spot" class="dl-link" title="Open the bin editor with this size">Design a bin for it</button></div></div>` : ""}
    <div class="dl-stat"><span>Connectors</span><div>${report.connector_total ? `${report.connector_total} <small>${same} same-height${mixed.length ? `; mixed: ${mixed.map(c => `${fmt(c.heights[0])}→${fmt(c.heights[1])} ×${c.count}`).join(", ")}` : ""}</small>` : "None yet - bins need shared walls of 16 mm or more"}</div></div>
    ${problems.length ? `<ul class="dl-problems">${problems.slice(0, 8).map(p => `<li class="${p.type === "height" ? "height" : ""}">${escapeHtml(p.message)}</li>`).join("")}${problems.length > 8 ? `<li>…and ${problems.length - 8} more</li>` : ""}</ul>` : ""}
    ${warnings}`;
  const meter = $(".dl-meter span", box);
  if (meter) meter.style.width = `${Math.min(100, report.fill)}%`;
};

DP.filteredBins = drawer => {
  const text = DP.filter.text.trim().toLowerCase();
  const show = DP.filter.show;
  const list = DL.bins.filter(one => {
    const placed = DL.placedCount(one.id);
    if (show === "printed" && one.qty <= 0) return false;
    if (show === "unplaced" && !(one.qty > placed)) return false;
    if (show === "placed" && !placed) return false;
    if (show === "unprinted" && one.qty > 0) return false;
    if (!text) return true;
    return `${one.name} ${fmt(one.x)}x${fmt(one.y)}x${fmt(one.z)} ${fmt(one.x)} × ${fmt(one.y)} ${one.file} ${one.label} ${one.interior} ${one.kind}`
      .toLowerCase().includes(text);
  });
  const sorters = {
    height: (a, b) => b.z - a.z || b.x * b.y - a.x * a.y,
    size: (a, b) => b.x * b.y - a.x * a.y || b.z - a.z,
    name: (a, b) => DL.label(a).localeCompare(DL.label(b), undefined, { numeric: true }),
    newest: (a, b) => Number(b.id.slice(1)) - Number(a.id.slice(1)),
  };
  // Spacers and shims sink below real bins whatever the sort.
  return list.sort((a, b) => Number(DL.isSpacer(a)) - Number(DL.isSpacer(b)) || sorters[DP.filter.sort](a, b));
};

DP.renderInventory = (force = false) => {
  const drawer = DL.drawer();
  const list = $("#dl-inv-list");
  dlSet("#dl-inv-show", DP.filter.show);
  dlSet("#dl-inv-sort", DP.filter.sort);
  const printed = DL.bins.reduce((sum, one) => sum + (one.qty > 0 ? one.qty : 0), 0);
  $("#dl-inv-count").textContent = `${dlPlural(DL.bins.length, "design")} · ${printed} printed`;
  const selectedBin = DL.selected ? DL.findPlacement(DL.selected)?.placement.bin : null;
  const counts = DL.bins.map(one => DL.placedCount(one.id));
  const signature = JSON.stringify([DL.bins, counts, DP.filter, [...DP.open], selectedBin, drawer.id, drawer.height, drawer.bin_axis]);
  if (!dlChanged("inventory", signature) && !force) return;
  if (list.contains(document.activeElement) && document.activeElement.matches("input") && !force) return;
  const bins = DP.filteredBins(drawer);
  if (!DL.bins.length) {
    list.innerHTML = `<div class="dl-empty">${DL.loaded
      ? "No bins in this folder's inventory yet.<br>Generate a bin with <strong>Keep log</strong> on, or add one by hand below."
      : "Loading the inventory…"}</div>`;
    return;
  }
  if (!bins.length) { list.innerHTML = `<div class="dl-empty">No bins match.</div>`; return; }
  const range = DV.heightRange();
  const kinds = { b4b: "B4B case", spacer: "Spacer", shim: "Edge shim", manual: "Added by hand" };
  list.innerHTML = bins.map(one => {
    const placed = DL.placedCount(one.id);
    const [w, d] = DL.units(one, drawer);
    const tooTall = one.z > drawer.height + 1e-6;
    const free = one.qty - placed;
    const canPlace = free > 0 && !tooTall && one.kind !== "shim";
    const color = DV.binColor(one, range);
    const flags = [kinds[one.kind], tooTall ? `Taller than ${drawer.name}` : "", one.qty <= 0 ? "Not printed" : ""].filter(Boolean);
    const holding = DL.drawersHolding(one.id);
    const classes = [
      one.id === selectedBin ? "selected" : "", free <= 0 && one.qty > 0 ? "all-placed" : "",
      one.qty <= 0 ? "unprinted" : "", tooTall ? "too-tall" : "",
    ].filter(Boolean).join(" ");
    const open = DP.open.has(one.id);
    return `
      <div class="dl-bin ${classes}" data-bin="${escapeHtml(one.id)}" draggable="${canPlace}" title="${canPlace ? "Drag into the drawer, or double-click to place" : ""}">
        <span class="dl-swatch" data-top="${color.top}" data-ink="${color.ink}" title="${fmt(one.z)} mm tall">${fmt(one.z)}</span>
        <span class="dl-bin-main">
          <strong>${escapeHtml(DL.label(one))}</strong>
          <small>${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm · ${w}×${d} units</small>
          ${flags.length ? `<small class="dl-flags">${escapeHtml(flags.join(" · "))}</small>` : ""}
        </span>
        <span class="dl-placed" title="${holding.length ? `In ${escapeHtml(holding.join(", "))}` : "Not in a drawer"}">${placed}/${one.qty}<small>placed</small></span>
        <span class="dl-qty" title="How many you have printed">
          <button type="button" data-act="qty-" ${one.qty <= 0 ? "disabled" : ""} aria-label="One fewer printed">−</button>
          <span>${one.qty}</span>
          <button type="button" data-act="qty+" aria-label="One more printed">+</button>
        </span>
        <button type="button" class="dl-place" data-act="place" ${canPlace ? "" : "disabled"} title="Put one in the best free spot">Place</button>
        <button type="button" class="dl-more" data-act="more" aria-expanded="${open}" title="Details">${open ? "▴" : "▾"}</button>
      </div>
      ${open ? `<div class="dl-bin-details" data-bin="${escapeHtml(one.id)}">
        <div class="field-grid two">
          <label>Name<input type="text" data-field="name" maxlength="80" value="${escapeHtml(one.name)}" placeholder="Shows the size when blank"></label>
          <label>Qty printed<input type="number" data-field="qty" min="0" step="1" value="${one.qty}"></label>
        </div>
        <div class="field-grid three">
          <label>X <span class="unit">mm</span><input type="number" data-field="x" min="1" step="8" value="${fmt(one.x)}"></label>
          <label>Y <span class="unit">mm</span><input type="number" data-field="y" min="1" step="8" value="${fmt(one.y)}"></label>
          <label>Z <span class="unit">mm</span><input type="number" data-field="z" min="1" step="1" value="${fmt(one.z)}"></label>
        </div>
        <p>${one.file ? `File: ${escapeHtml(one.file)}<br>` : ""}${one.label ? `Label: ${escapeHtml(one.label)}<br>` : ""}${one.interior ? `Inside: ${escapeHtml(one.interior)}<br>` : ""}${escapeHtml(one.id)}${one.date ? ` · logged ${escapeHtml(one.date)}` : ""}</p>
        <button type="button" class="button danger dl-small" data-act="delete">Delete from inventory</button>
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
  dlSet("#dl-autosave", Boolean(settings.autosave), "checked");
  const file = $("#dl-file");
  const name = (DL.file || "").split(/[\\/]/).pop();
  file.textContent = name ? `📁 ${name}` : "📁 Choose a save location";
  file.title = `${DL.file || ""}\nClick to change the save location - each folder has its own inventory.`;
  const status = $("#dl-save-status");
  let text = "";
  let tone = "";
  if (DL.saveState === "saving") text = "Saving…";
  else if (DL.saveState === "error") { text = "Not saved"; tone = "error"; }
  else if (DL.dirty && !settings.autosave) { text = "Unsaved changes"; tone = "dirty"; }
  else if (DL.savedAt && DL.saveState === "saved") text = `Saved ${DL.savedAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`;
  else if (!DL.exists) text = "No inventory file yet";
  else text = settings.autosave ? "Saves as you go" : "Up to date";
  status.textContent = text;
  status.className = `dl-save-status ${tone}`;
  $("#dl-save").disabled = DL.saving || (!DL.dirty && DL.saveState !== "error");
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
