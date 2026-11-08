"use strict";

// Story 2671 - one workspace for the open Space (Debate 2670 design).
//
// This layer changes where the existing forms live and how they are reached,
// never what they contain. It drives the machinery that already exists:
//   Space selected      -> DP.selectMode("space")      layout settings + bins list
//   container selected  -> DP.openStructuralTarget()   Storage Box / Drawers form
//   bin selected        -> DP.openInventoryRow(id)     the bin form
// A hierarchy replaces the Bins/Spaces tabs, and while a bin or container is
// open its Space stays visible beside it. The classic screens are untouched
// behind the "Temp only Roll back" button; both read and write the same files.

const WS = {
  printing: false,
  resume: null, // what was open when Print Space began, restored on Done
  signature: "",
};
const WS_PREF_KEY = "wavefinity-interface";

WS.enabled = () => {
  try { return localStorage.getItem(WS_PREF_KEY) !== "classic"; }
  catch (_error) { return true; }
};

WS.setEnabled = async on => {
  try { localStorage.setItem(WS_PREF_KEY, on ? "workspace" : "classic"); }
  catch (_error) { toast("Your choice could not be remembered in this browser.", true); }
  if (!on && WS.printing) await WS.endPrint();
  WS.sync();
};

WS.open = () => Boolean(typeof DL !== "undefined" && DL.active && DL.layout && state.folderMode === "space");

// What the inspector is showing right now.
WS.subject = () => {
  if (!WS.open()) return { kind: "none" };
  if (DP.mode === "space") return { kind: "space" };
  const target = DP.getDesignTarget();
  if (target.kind === "structural") return { kind: "container" };
  if (target.kind === "bin" && target.rowId && DL.bin(target.rowId)) return { kind: "bin", id: target.rowId };
  return { kind: "newbin" };
};

WS.containerName = () => {
  const kind = DP.structuralPreviewTargetKindFor(state.activeSpace);
  return kind === "storage_drawers" ? "Storage Drawers" : kind === "base_trim" ? "Base Trim" : kind ? "Storage Box" : "";
};

WS.binName = one => (one ? DL.label(one) : "New bin");

const wsEsc = value => escapeHtml(String(value ?? ""));

// ------------------------------------------------------------------ tree

// Space > container or drawers > bins. Each node: { kind, id, level, label, note, current }.
WS.tree = () => {
  const subject = WS.subject();
  const space = state.activeSpace || {};
  const nodes = [];
  const bins = (DL.bins || []).filter(DL.isOrdinary);
  const add = (kind, id, level, label, extra = {}) => nodes.push({ kind, id, level, label, ...extra });
  add("space", null, 1, space.name || "Space", { current: subject.kind === "space" });
  const binNode = (one, level) => add("bin", one.id, level, WS.binName(one), {
    current: subject.kind === "bin" && subject.id === one.id,
    editable: DP.editableSourceFor(one),
  });
  const newBinNode = level => {
    if (subject.kind === "newbin") add("newbin", null, level, "New bin", { current: true });
  };
  const structural = DP.structuralPreviewTargetKindFor(space);
  if (DL.isStorageDrawers()) {
    if (structural) add("container", null, 2, WS.containerName(), { current: subject.kind === "container" });
    const placedAnywhere = new Set();
    DL.layout.drawers.forEach((drawer, index) => {
      const here = (drawer.placements || []).map(p => DL.bin(p.bin)).filter(one => one && DL.isOrdinary(one));
      here.forEach(one => placedAnywhere.add(one.id));
      const activeDrawer = drawer.id === DL.layout.active;
      // The drawer rule, shown instead of discovered by error.
      let note = here.length ? `${here.length} ${here.length === 1 ? "bin" : "bins"}` : "empty";
      if (activeDrawer && SP.drawerBinContents() === "full_interior") note = "one full interior bin";
      add("drawer", drawer.id, 2, drawer.name || `Drawer ${index + 1}`, { note, active: activeDrawer });
      // A bin sits once in the list even if stacked or repeated.
      [...new Map(here.map(one => [one.id, one])).values()].forEach(one => binNode(one, 3));
      if (activeDrawer) newBinNode(3);
    });
    const loose = bins.filter(one => !placedAnywhere.has(one.id));
    if (loose.length) {
      add("group", null, 2, "Not in a drawer yet");
      loose.forEach(one => binNode(one, 3));
    }
    return nodes;
  }
  if (structural === "box") {
    const contents = SP.storageBoxBinContents();
    const note = contents === "full_interior" ? "one full interior bin"
      : contents === "empty" ? "holds one full interior bin or several bins" : `${bins.length} ${bins.length === 1 ? "bin" : "bins"}`;
    add("container", null, 2, WS.containerName(), { current: subject.kind === "container", note });
    bins.forEach(one => binNode(one, 3));
    newBinNode(3);
    return nodes;
  }
  if (structural) add("container", null, 2, WS.containerName(), { current: subject.kind === "container" });
  const drawers = DL.layout.drawers || [];
  if (drawers.length > 1) {
    drawers.forEach((drawer, index) => {
      add("drawer", drawer.id, 2, drawer.name || `Drawer ${index + 1}`, { active: drawer.id === DL.layout.active });
      const here = (drawer.placements || []).map(p => DL.bin(p.bin)).filter(one => one && DL.isOrdinary(one));
      [...new Map(here.map(one => [one.id, one])).values()].forEach(one => binNode(one, 3));
    });
    const placed = new Set(drawers.flatMap(drawer => (drawer.placements || []).map(p => p.bin)));
    const loose = bins.filter(one => !placed.has(one.id));
    if (loose.length) {
      add("group", null, 2, "Not placed yet");
      loose.forEach(one => binNode(one, 3));
    }
    newBinNode(2);
    return nodes;
  }
  bins.forEach(one => binNode(one, 2));
  newBinNode(2);
  return nodes;
};

WS.crumb = nodes => {
  const current = nodes.find(one => one.current);
  if (!current) return [];
  const path = [current];
  let level = current.level;
  for (let i = nodes.indexOf(current) - 1; i >= 0 && level > 1; i -= 1) {
    if (nodes[i].level < level) { path.unshift(nodes[i]); level = nodes[i].level; }
  }
  return path;
};

WS.renderNoSpace = () => {
  const name = ($("#part-name")?.value || "").trim() || "New bin";
  return `
    <ol class="ws-tree" role="tree" aria-label="Project">
      <li class="ws-node" data-level="1" role="treeitem" aria-level="1" aria-selected="false"><span class="ws-label">No Space</span></li>
      <li class="ws-node current" data-level="2" role="treeitem" aria-level="2" aria-selected="true"><span class="ws-label">${wsEsc(name)}</span></li>
    </ol>
    <div class="ws-actions"><button type="button" class="button secondary dl-small" data-ws-act="make-space">Create a Space…</button></div>`;
};

WS.renderPrintBar = () => {
  const hosted = Boolean(state.runtime.hosted);
  const picked = [...DP.printSelected].map(id => DL.bin(id)).filter(one => DL.printEligible(one));
  const noSlicer = !state.slicer || !state.slicer.available;
  const busy = Boolean(DL.busy);
  const n = picked.length;
  return `
    <div class="ws-printbar" role="group" aria-label="Print Space">
      <span class="ws-printcount" role="status">${n === 0 ? "Tick the bins to print" : `${n} ${n === 1 ? "bin" : "bins"} ticked`}</span>
      <div class="ws-actions">
        <button type="button" class="button secondary dl-small" data-ws-act="pick-all">Tick all</button>
        <button type="button" class="button secondary dl-small" data-ws-act="pick-none"${DP.printSelected.size ? "" : " disabled"}>Clear</button>
      </div>
      <div class="ws-actions">
        ${hosted ? "" : `<button type="button" class="button primary dl-small" data-ws-act="print-picked"${!n || noSlicer || busy ? " disabled" : ""}${noSlicer ? ' title="A slicer is needed to print. Open Printer Settings… to choose one."' : ""}>Print Selected</button>`}
        <button type="button" class="button secondary dl-small" data-ws-act="export-picked"${!n || busy ? " disabled" : ""}>Export Selected</button>
        <button type="button" class="button secondary dl-small" data-ws-act="done">Done</button>
      </div>
    </div>`;
};

WS.render = () => {
  const host = $("#ws-hierarchy");
  if (!host) return;
  const on = WS.enabled();
  host.hidden = !on;
  if (!on) { WS.signature = ""; return; }
  let html;
  if (!WS.open()) {
    html = WS.renderNoSpace();
  } else {
    const nodes = WS.tree();
    const crumb = WS.crumb(nodes);
    const current = nodes.find(one => one.current);
    const rule = nodes.some(one => one.kind === "drawer")
      ? '<p class="ws-rule">A drawer holds one full interior bin or several bins, never both.</p>' : "";
    const rows = nodes.map(one => {
      if (one.kind === "group") return `<li class="ws-group" data-level="${one.level}" role="presentation">${wsEsc(one.label)}</li>`;
      const tick = WS.printing && one.kind === "bin"
        ? `<input type="checkbox" class="ws-tick" data-ws-tick="${wsEsc(one.id)}" aria-label="Print ${wsEsc(one.label)}"${DP.printSelected.has(one.id) ? " checked" : ""}${DL.printEligible(DL.bin(one.id)) ? "" : " disabled"}>` : "";
      const note = one.note ? `<span class="ws-note">${wsEsc(one.note)}</span>` : "";
      const cls = ["ws-node", one.current ? "current" : "", one.active ? "active-drawer" : "", one.editable === false ? "view-only" : ""].filter(Boolean).join(" ");
      return `<li class="${cls}" data-level="${one.level}" role="treeitem" aria-level="${one.level}" aria-selected="${one.current ? "true" : "false"}">${tick}<button type="button" class="ws-label" data-ws-kind="${one.kind}" data-ws-id="${wsEsc(one.id)}"${one.current ? ' aria-current="true"' : ""}>${wsEsc(one.label)}</button>${note}</li>`;
    }).join("");
    const where = current
      ? `<nav class="ws-crumb" aria-label="Where this sits">${crumb.map((one, i) => i === crumb.length - 1
        ? `<strong>${wsEsc(one.label)}</strong>`
        : one.kind === "group" ? `<span>${wsEsc(one.label)}</span>`
        : `<button type="button" class="ws-crumb-link" data-ws-kind="${one.kind}" data-ws-id="${wsEsc(one.id)}">${wsEsc(one.label)}</button>`).join('<span aria-hidden="true"> › </span>')}</nav>`
      : "";
    html = `${where}<ol class="ws-tree" role="tree" aria-label="Space contents">${rows}</ol>${rule}${WS.printing ? WS.renderPrintBar() : ""}`;
  }
  if (html !== WS.signature) {
    // Rebuilding would drop keyboard focus; put it back on the same item.
    const focused = document.activeElement?.closest?.("#ws-hierarchy") ? document.activeElement : null;
    const key = focused ? (focused.dataset.wsKind ? `[data-ws-kind="${focused.dataset.wsKind}"][data-ws-id="${CSS.escape(focused.dataset.wsId || "")}"]`
      : focused.dataset.wsTick ? `[data-ws-tick="${CSS.escape(focused.dataset.wsTick)}"]`
      : focused.dataset.wsAct ? `[data-ws-act="${focused.dataset.wsAct}"]` : null) : null;
    host.innerHTML = html;
    WS.signature = html;
    if (key) host.querySelector(key)?.focus();
  }
};

// ------------------------------------------------------------------ selecting

WS.busy = false;
WS.select = async (kind, id) => {
  if (WS.busy || !WS.open()) return false;
  WS.busy = true;
  try {
    if (kind === "space") return await DP.selectMode("space");
    if (kind === "drawer") {
      if (DL.isStorageDrawers()) await SP.cabinetCallbacks().setActiveDrawer(id);
      else {
        DL.change(() => { DL.layout.active = id; });
        DL.selected = null; DL.selectedRow = null; DV.fit(); DL.emit();
      }
      return DP.mode === "space" ? true : await DP.selectMode("space");
    }
    if (kind === "container") {
      if (DP.mode !== "design" && !(await DP.selectMode("design"))) return false;
      return await DP.openStructuralTarget();
    }
    if (kind === "bin") {
      const one = DL.bin(id);
      if (!one) return false;
      if (!DP.editableSourceFor(one)) { DL.selectRow(id); return false; }
      return await DP.openInventoryRow(id);
    }
    return false;
  } finally {
    WS.busy = false;
    WS.sync();
  }
};

// A click on a bin in the visual layout. Returns true when the workspace took it.
DP.onLayoutClick = key => {
  if (!WS.enabled() || !WS.open()) return false;
  const found = DL.findPlacement(key);
  const one = found && DL.bin(found.placement.bin);
  if (!one || !DL.isOrdinary(one)) return false;
  if (WS.printing) {
    if (!DL.printEligible(one)) return true;
    if (DP.printSelected.has(one.id)) DP.printSelected.delete(one.id); else DP.printSelected.add(one.id);
    DP.renderInventory(true);
    WS.sync();
    return true;
  }
  DL.selectRow(one.id);
  WS.select("bin", one.id);
  return true;
};

// While a bin or container is open, the Space beside it is for looking and picking.
DP.layoutViewOnly = () => document.body.classList.contains("ws-split");

// A tick on every ticked bin in the layout while printing a Space.
DP.paintPrintMark = (ctx, bin, cx, cy, span) => {
  if (!WS.printing || !DP.printSelected.has(bin.id)) return;
  const r = Math.max(7, Math.min(13, span * 0.22));
  ctx.save();
  ctx.beginPath(); ctx.arc(cx, cy - r * 1.6, r, 0, Math.PI * 2);
  ctx.fillStyle = "#146c70"; ctx.fill();
  ctx.strokeStyle = "#fff"; ctx.lineWidth = Math.max(2, r * 0.22);
  ctx.beginPath(); ctx.moveTo(cx - r * 0.5, cy - r * 1.6); ctx.lineTo(cx - r * 0.1, cy - r * 1.25); ctx.lineTo(cx + r * 0.55, cy - r * 2.0);
  ctx.stroke();
  ctx.restore();
};

// ------------------------------------------------------------------ printing

WS.printBinTarget = () => {
  const subject = WS.subject();
  if (subject.kind === "container") {
    const kind = DP.structuralPreviewTargetKindFor(state.activeSpace);
    return kind === "storage_drawers" ? document.querySelector(".sd-print") : $("#space-structural-print");
  }
  if (subject.kind === "bin" || subject.kind === "newbin" || subject.kind === "none") return $("#print-individual-bin");
  return null;
};

WS.printBin = () => {
  const subject = WS.subject();
  const target = WS.printBinTarget();
  if (!target || target.disabled) return;
  if (subject.kind === "container") { target.click(); return; }
  // The same Print / Export choice the bin's own buttons give.
  chooseIndividualBinPrint($("#print-individual-bin"));
  const dialog = $("#individual-bin-print-dialog");
  dialog.querySelector('[value="export"]').hidden = false;
  dialog.querySelector('[value="print"]').hidden = Boolean(state.runtime.hosted);
  $("#individual-bin-print-message").textContent = "Choose what to include. Print sends it to the slicer; Export creates a file.";
};

WS.startPrint = async () => {
  if (WS.printing || !WS.open() || WS.busy) return;
  const subject = WS.subject();
  WS.resume = subject.kind === "space" ? null : subject;
  if (subject.kind !== "space" && !(await DP.selectMode("space"))) { WS.resume = null; return; }
  WS.printing = true;
  WS.sync();
};

WS.endPrint = async () => {
  if (!WS.printing) return;
  WS.printing = false;
  const back = WS.resume;
  WS.resume = null;
  DP.printSelected.clear();
  DP.renderInventory(true);
  WS.sync();
  if (back?.kind === "bin" && DL.bin(back.id)) await WS.select("bin", back.id);
  else if (back?.kind === "container") await WS.select("container");
  DV.render();
};

WS.pickedBins = () => [...DP.printSelected].map(id => DL.bin(id)).filter(one => DL.printEligible(one));

// ------------------------------------------------------------------ sync

WS.sync = () => {
  const on = WS.enabled();
  const open = WS.open();
  const subject = WS.subject();
  const body = document.body;
  body.classList.toggle("ws-on", on);
  body.classList.toggle("ws-open", on && open);
  body.classList.toggle("ws-printing", on && WS.printing);
  for (const kind of ["space", "container", "bin", "newbin", "none"]) {
    body.classList.toggle(`ws-subject-${kind}`, on && subject.kind === kind);
  }
  const drawerWrap = $('.canvas-wrap[data-canvas="drawer"]');
  const split = on && open && DP.mode === "design" && drawerWrap && !drawerWrap.classList.contains("active");
  if (body.classList.contains("ws-split") !== Boolean(split)) {
    body.classList.toggle("ws-split", Boolean(split));
    requestAnimationFrame(() => { if (typeof DV !== "undefined") DV.render(); });
  }
  const tools = $("#ws-header-tools");
  if (tools) tools.hidden = !on;
  const toggle = $("#ws-ui-toggle");
  if (toggle) toggle.textContent = on ? "Temp only Roll back" : "Back to the new UI";
  if (on) {
    const printBin = $("#ws-print-bin");
    const target = WS.printBinTarget();
    printBin.disabled = !target || target.disabled || Boolean(DL?.busy);
    printBin.title = subject.kind === "space"
      ? "Open a bin or the container to print it. Print Space prints several bins."
      : subject.kind === "container" ? `Print the ${WS.containerName()}` : "Print this bin";
    const printSpace = $("#ws-print-space");
    printSpace.disabled = !open || WS.printing;
    printSpace.title = open ? "Choose which bins to print" : "Create or open a Space to print several bins";
    printSpace.classList.toggle("active", WS.printing);
    WS.render();
  }
};

// ------------------------------------------------------------------ wiring

(() => {
  const host = $("#ws-hierarchy");
  if (!host) return;
  host.addEventListener("click", event => {
    const act = event.target.closest("[data-ws-act]")?.dataset.wsAct;
    if (act === "make-space") { SP.offerSpacePlanning(); return; }
    if (act === "pick-all") { DP.selectAllPrintable(); WS.sync(); return; }
    if (act === "pick-none") { DP.clearPrintSelection(); WS.sync(); return; }
    if (act === "done") { WS.endPrint(); return; }
    if (act === "print-picked") {
      DL.printSelectedBins(Object.fromEntries(WS.pickedBins().map(one => [one.id, DL.printCount(one)])), true);
      return;
    }
    if (act === "export-picked") { DL.saveSelectedBins(WS.pickedBins().map(one => one.id), true); return; }
    const pick = event.target.closest("[data-ws-kind]");
    if (!pick) return;
    if (WS.printing && pick.dataset.wsKind === "bin") {
      // While printing, a bin row ticks or unticks; it does not open.
      const id = pick.dataset.wsId;
      if (!DL.printEligible(DL.bin(id))) return;
      if (DP.printSelected.has(id)) DP.printSelected.delete(id); else DP.printSelected.add(id);
      DP.renderInventory(true);
      WS.sync();
      return;
    }
    if (WS.printing && pick.dataset.wsKind !== "bin") return;
    WS.select(pick.dataset.wsKind, pick.dataset.wsId || null);
  });
  host.addEventListener("change", event => {
    const id = event.target.dataset.wsTick;
    if (!id) return;
    if (event.target.checked) DP.printSelected.add(id); else DP.printSelected.delete(id);
    DP.renderInventory(true);
    WS.sync();
  });

  $("#ws-print-bin").addEventListener("click", () => WS.printBin());
  $("#ws-print-space").addEventListener("click", () => WS.startPrint());
  $("#ws-ui-toggle").addEventListener("click", () => WS.setEnabled(!WS.enabled()));
  $("#part-name")?.addEventListener("input", () => WS.sync());

  // Every owner that changes what is open reports through one of these.
  for (const name of ["applyMode", "setMode", "setDesignTarget", "clearDesignTarget", "refreshDesignBinNav"]) {
    const original = DP[name];
    DP[name] = (...args) => {
      const result = original(...args);
      WS.sync();
      return result;
    };
  }
  DL.on(WS.sync);
  const drawerWrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (drawerWrap) new MutationObserver(WS.sync).observe(drawerWrap, { attributes: true, attributeFilter: ["class"] });
  if (drawerWrap && window.ResizeObserver) new ResizeObserver(() => DV.render()).observe(drawerWrap);
  WS.sync();
})();
