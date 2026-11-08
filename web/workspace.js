"use strict";

// Story 2674 - one place, one focus (Debate 2673 design; replaces the 2671 split view).
//
// Exactly one full-width task is on screen. This layer changes where the existing
// forms live and how they are reached, never what they contain. It drives the
// machinery that already exists:
//   Space Overview / Print Space -> DP.selectMode("space"), the Space canvas, view only
//   Space Settings               -> DP.selectMode("space") + SP.editSpace() (the inline edit)
//   Container editor             -> DP.openStructuralTarget()   Storage Box / Drawers / Surface
//   Bin editor                   -> DP.openInventoryRow(id)     the bin form
// Picker, Overview, Print Space and My Bins are drawn in #ws-stage; the three
// editors are the existing sidebar + preview with a slim line (#ws-stage) above.
// The classic screens are untouched behind the "Temp only Roll back" button.

const WS = {
  task: "picker", // picker | overview | settings | container | bin | print | mybins
  sel: null, // Overview selection: { kind: "bin", id } | { kind: "container" }
  memory: null, // what the Overview looked like when it was left
  printPick: new Set(),
  printContainer: false,
  busy: false,
  message: "",
  landing: null,
  placeSeen: "",
  signature: "",
  rendered: "",
};
const WS_PREF_KEY = "wavefinity-interface";
const WS_FULL = ["picker", "print", "mybins"]; // tasks drawn entirely in the stage

WS.enabled = () => {
  try { return localStorage.getItem(WS_PREF_KEY) !== "classic"; }
  catch (_error) { return true; }
};

WS.open = () => Boolean(typeof DL !== "undefined" && DL.active && DL.layout && state.folderMode === "space");

const wsEsc = value => escapeHtml(String(value ?? ""));

// ------------------------------------------------------------------ places

WS.placeKey = () => (WS.open() ? `space:${state.activeSpaceId || state.activeSpace?.name}`
  : state.folderMode === "space" ? "space-pending" : "loose");

WS.placeName = () => (WS.open() ? state.activeSpace?.name || "Space" : state.folderMode === "space" ? "" : "My Bins");

// The one container a Space owns, in the words of its Edit button.
WS.containerKind = () => SP.structuralKind();
WS.containerEdit = () => ({ storage_box: "Edit storage box", storage_drawers: "Edit drawer", base_trim: "Edit surface" })[WS.containerKind()] || "";
WS.containerName = () => ({ storage_box: "Storage box", storage_drawers: "Drawers", base_trim: "Surface" })[WS.containerKind()] || "";

WS.looseName = () => ($("#part-name")?.value || "").trim() || "New bin";

WS.binLabel = id => {
  const one = id && DL.bin(id);
  return one ? DL.label(one) : WS.looseName();
};

// ------------------------------------------------------------------ items

// Container first, then bins (grouped by drawer when a Space has several).
WS.items = () => {
  const items = [];
  const add = (kind, id, label, extra = {}) => items.push({ kind, id, label, ...extra });
  if (WS.containerKind()) add("container", "container", WS.containerName());
  const bins = (DL.bins || []).filter(DL.isOrdinary);
  const binItem = one => add("bin", one.id, DL.label(one), {
    note: [`${fmt(one.x)} × ${fmt(one.y)} mm`, DL.statusLabel(one)].join(" · "),
    editable: DP.editableSourceFor(one),
    printable: DL.printEligible(one),
  });
  const drawers = DL.layout.drawers || [];
  if (DL.isStorageDrawers() || drawers.length > 1) {
    const placed = new Set();
    drawers.forEach((drawer, index) => {
      const here = [...new Map((drawer.placements || []).map(p => DL.bin(p.bin))
        .filter(one => one && DL.isOrdinary(one)).map(one => [one.id, one])).values()];
      here.forEach(one => placed.add(one.id));
      add("group", null, drawer.name || `Drawer ${index + 1}`);
      here.forEach(binItem);
    });
    const loose = bins.filter(one => !placed.has(one.id));
    if (loose.length) { add("group", null, "Not placed yet"); loose.forEach(binItem); }
  } else {
    bins.forEach(binItem);
  }
  return items;
};

WS.hasCanvas = () => WS.open() && state.activeSpace?.kind !== "portable" && state.activeSpace?.kind !== "box";

// ------------------------------------------------------------------ stage html

WS.spaceRows = () => {
  const rows = [];
  const here = state.folderMode === "space" && state.activeSpace;
  if (here) {
    rows.push({ src: "current", name: state.activeSpace.name, kind: state.activeSpace.kind, current: true,
      meta: state.activeSpace.kind === "storage_drawers" ? SP.storageDrawersSummaryText(state.activeSpace) : SP.sizeText([state.activeSpace.x, state.activeSpace.y, state.activeSpace.z]) });
  }
  const seen = new Set(here ? [String(state.activeSpace.name).toLowerCase()] : []);
  const add = (src, index, one) => {
    const key = String(one.name || "").toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ src, index, name: one.name, kind: one.kind, invalid: Boolean(one.invalid || one.missing || one.conflict),
      meta: one.invalid ? one.error || "unavailable" : one.summary_text || SP.sizeText(one.size) });
  };
  if (state.runtime.hosted) {
    SP.recent.forEach((one, index) => { if (one.folder_mode === "space") add("recent", index, one); });
  } else {
    SP.otherSpaces.forEach((one, index) => add("other", index, one));
    SP.recent.forEach((one, index) => { if (one.folder_mode === "space") add("recent", index, one); });
  }
  return rows;
};

WS.renderPicker = () => {
  const rows = WS.spaceRows();
  const cards = rows.map(one => {
    const kind = SP_KINDS[one.kind];
    return `<li><button type="button" class="ws-card${one.current ? " current" : ""}" data-ws-act="open-space" data-src="${one.src}" data-index="${one.index ?? ""}"${one.invalid ? " disabled" : ""}>
      <span class="ws-card-icon" aria-hidden="true">${SP.compactKindIcon(one.kind)}</span>
      <span class="ws-card-text"><strong>${wsEsc(one.name)}</strong><small>${wsEsc([kind?.label, one.meta].filter(Boolean).join(" · "))}</small></span>
      ${one.current ? '<em class="ws-card-tag">open now</em>' : ""}</button></li>`;
  }).join("");
  const choice = (kind, title, text, img) => `<button type="button" class="ws-choice" data-ws-act="new-space" data-kind="${kind}">
      ${img ? `<img src="/images/${img}" alt="" width="120" height="90" decoding="async">` : '<span class="ws-choice-blank" aria-hidden="true">—</span>'}
      <strong>${title}</strong><small>${text}</small></button>`;
  return `<div class="ws-page">
    <h2>What are you organizing?</h2>
    ${WS.message ? `<p class="field-error" role="alert">${wsEsc(WS.message)}</p>` : ""}
    <h3 class="ws-section">Open</h3>
    <ul class="ws-cards">${cards}
      <li><button type="button" class="ws-card${state.folderMode !== "space" ? " current" : ""}" data-ws-act="my-bins">
        <span class="ws-card-icon" aria-hidden="true">📦</span>
        <span class="ws-card-text"><strong>My Bins</strong><small>Bins that are not in a Space</small></span></button></li>
    </ul>
    <p class="ws-links"><button type="button" class="link-button" data-ws-act="open-folder">Open a Space folder…</button>${state.runtime.hosted ? "" : ' <button type="button" class="link-button" data-ws-act="storage">Change Wavefinity folder…</button>'}</p>
    <h3 class="ws-section">Start something new</h3>
    <div class="ws-choices">
      ${choice("portable", "Storage box", "A carrying case for your bins.", "B4B.png")}
      ${choice("storage_drawers", "Drawers", "Print a new cabinet with drawers.", "StorageDrawers.png")}
      ${choice("surface", "Edge / surface", "A countertop, shelf, or vanity.", "Vanity.png")}
      ${choice("none", "No Space", "Design one bin on its own.", "")}
    </div>
    <p class="ws-links">Other kinds of Space:
      <button type="button" class="link-button" data-ws-act="new-space" data-kind="drawer">An existing drawer</button> ·
      <button type="button" class="link-button" data-ws-act="new-space" data-kind="pegboard">A pegboard</button></p>
  </div>`;
};

WS.itemRows = (items, { ticks = false } = {}) => items.map(one => {
  if (one.kind === "group") return `<li class="ws-group" role="presentation">${wsEsc(one.label)}</li>`;
  const picked = WS.sel && WS.sel.kind === one.kind && (one.kind === "container" || WS.sel.id === one.id);
  const note = one.note ? `<span class="ws-note">${wsEsc(one.note)}</span>` : "";
  if (ticks) {
    const on = one.kind === "container" ? WS.printContainer : WS.printPick.has(one.id);
    const off = one.kind === "bin" && !one.printable;
    return `<li class="ws-item"><label><input type="checkbox" data-ws-tick="${wsEsc(one.id)}"${on ? " checked" : ""}${off ? " disabled" : ""}>
      <span class="ws-label">${wsEsc(one.label)}</span>${note}</label></li>`;
  }
  return `<li class="ws-item${picked ? " selected" : ""}${one.kind === "container" ? " container" : ""}"><button type="button" class="ws-label" data-ws-pick="${one.kind}" data-id="${wsEsc(one.id)}" aria-pressed="${picked ? "true" : "false"}">${wsEsc(one.label)}</button>${note}</li>`;
}).join("");

WS.selectionBar = items => {
  if (!WS.sel) return '<div class="ws-selbar empty" role="status">Click a bin or the container to select it.</div>';
  if (WS.sel.kind === "container") {
    return `<div class="ws-selbar" role="group" aria-label="Selected: ${wsEsc(WS.containerName())}"><strong>${wsEsc(WS.containerName())}</strong>
      <button type="button" class="button secondary dl-small" data-ws-act="sel-edit">Edit</button>
      <button type="button" class="button secondary dl-small" data-ws-act="sel-print">Print</button></div>`;
  }
  const one = items.find(item => item.kind === "bin" && item.id === WS.sel.id);
  if (!one) return '<div class="ws-selbar empty" role="status">Click a bin or the container to select it.</div>';
  return `<div class="ws-selbar" role="group" aria-label="Selected: ${wsEsc(one.label)}"><strong>${wsEsc(one.label)}</strong>
    <button type="button" class="button secondary dl-small" data-ws-act="sel-edit"${one.editable ? "" : ' disabled title="This bin has no editable design."'}>Edit</button>
    <button type="button" class="button secondary dl-small" data-ws-act="sel-print"${one.printable ? "" : " disabled"}>Print</button>
    <button type="button" class="button secondary dl-small" data-ws-act="sel-dup"${one.editable ? "" : " disabled"}>Duplicate</button>
    <button type="button" class="button danger dl-small" data-ws-act="sel-del">Delete</button></div>`;
};

WS.renderOverview = () => {
  const items = WS.items();
  const edit = WS.containerEdit();
  return `<div class="ws-page ws-overview">
    <div class="ws-toprow" role="group" aria-label="Space actions">
      <button type="button" class="button secondary dl-small" data-ws-act="edit-space">Edit space</button>
      ${edit ? `<button type="button" class="button secondary dl-small" data-ws-act="edit-container">${edit}</button>` : ""}
      <button type="button" class="button secondary dl-small" data-ws-act="print-space">Print Space</button>
      <button type="button" class="button primary dl-small" data-ws-act="new-bin">New Bin</button>
    </div>
    ${WS.selectionBar(items)}
    <ul class="ws-items" aria-label="Contents of ${wsEsc(WS.placeName())}">${items.length ? WS.itemRows(items) : '<li class="ws-empty">Nothing here yet. Choose New Bin to add the first bin.</li>'}</ul>
  </div>`;
};

WS.renderMyBins = () => {
  const name = WS.looseName();
  const picked = Boolean(WS.sel);
  return `<div class="ws-page ws-overview">
    <h2>My Bins</h2>
    <div class="ws-toprow" role="group" aria-label="My Bins actions">
      <button type="button" class="button primary dl-small" data-ws-act="new-bin">New Bin</button>
    </div>
    ${picked ? `<div class="ws-selbar" role="group" aria-label="Selected: ${wsEsc(name)}"><strong>${wsEsc(name)}</strong>
      <button type="button" class="button secondary dl-small" data-ws-act="sel-edit">Edit</button>
      <button type="button" class="button secondary dl-small" data-ws-act="sel-print">Print</button></div>`
      : '<div class="ws-selbar empty" role="status">Click a bin to select it.</div>'}
    <ul class="ws-items" aria-label="Bins that are not in a Space"><li class="ws-item${picked ? " selected" : ""}"><button type="button" class="ws-label" data-ws-pick="bin" data-id="" aria-pressed="${picked}">${wsEsc(name)}</button><span class="ws-note">on this screen now</span></li></ul>
  </div>`;
};

WS.pickedIds = () => [...WS.printPick].filter(id => DL.printEligible(DL.bin(id)));

WS.renderPrint = () => {
  const items = WS.items();
  const hosted = Boolean(state.runtime.hosted);
  const noSlicer = !state.slicer || !state.slicer.available;
  const n = WS.pickedIds().length + (WS.printContainer ? 1 : 0);
  const none = n === 0 || DL.busy;
  return `<div class="ws-page ws-print">
    <h2>Print Space</h2>
    <p class="ws-printcount" role="status">${n === 0 ? "Tick what to print." : `${n} ${n === 1 ? "item" : "items"} ticked`}</p>
    <div class="ws-toprow" role="group" aria-label="Print Space">
      ${hosted ? "" : `<button type="button" class="button primary dl-small" data-ws-act="print-picked"${none || noSlicer ? " disabled" : ""}${noSlicer ? ' title="A slicer is needed to print. Open Printer Settings… to choose one."' : ""}>Print Selected</button>`}
      <button type="button" class="button secondary dl-small" data-ws-act="export-picked"${none ? " disabled" : ""}>Export Selected</button>
      <button type="button" class="button secondary dl-small" data-ws-act="pick-all">Tick all</button>
      <button type="button" class="button secondary dl-small" data-ws-act="pick-none">Clear</button>
      <button type="button" class="button secondary dl-small" data-ws-act="done">Done</button>
    </div>
    <ul class="ws-items" aria-label="Items to print">${WS.itemRows(items, { ticks: true })}</ul>
  </div>`;
};

// The slim line above an editor: always one obvious way back.
WS.renderBar = () => {
  const back = `<button type="button" class="button secondary dl-small" data-ws-act="back">← Back to ${wsEsc(WS.placeName() || "Spaces")}</button>`;
  if (WS.task === "bin") {
    const place = WS.placeName();
    const id = state.designInventoryId;
    const rows = WS.open() ? DP.designNavEditableRows() : [];
    return `<div class="ws-bar" role="group" aria-label="Bin editor">${back}
      <nav class="ws-trail" aria-label="Where you are">${wsEsc(place)} › <strong>${wsEsc(WS.binLabel(id))}</strong></nav>
      ${rows.length > 1 ? `<label class="ws-switch">Bin <select data-ws-switch aria-label="Switch to another bin">${rows.map(one => `<option value="${wsEsc(one.id)}"${one.id === id ? " selected" : ""}>${wsEsc(DL.label(one))}</option>`).join("")}</select></label>` : ""}</div>`;
  }
  if (WS.task === "container") {
    return `<div class="ws-bar" role="group" aria-label="${wsEsc(WS.containerName())} editor">${back}
      <nav class="ws-trail" aria-label="Where you are">${wsEsc(WS.placeName())} › <strong>${wsEsc(WS.containerName())}</strong></nav></div>`;
  }
  const edit = WS.containerEdit();
  const sized = ["storage_box", "storage_drawers"].includes(WS.containerKind());
  return `<div class="ws-bar" role="group" aria-label="Space settings">${back}
    <nav class="ws-trail" aria-label="Where you are">${wsEsc(WS.placeName())} › <strong>Space settings</strong></nav>
    ${sized ? `<span class="ws-linknote">Its size and construction are set in <button type="button" class="link-button" data-ws-act="edit-container">${edit}</button>.</span>` : ""}</div>`;
};

WS.render = () => {
  const stage = $("#ws-stage");
  if (!stage) return;
  const on = WS.enabled();
  stage.hidden = !on;
  if (!on) { WS.signature = ""; return; }
  const needsSpace = ["overview", "print"].includes(WS.task) && !WS.open();
  const html = needsSpace ? '<div class="ws-page"><p role="status">Opening…</p></div>'
    : WS.task === "picker" ? WS.renderPicker()
    : WS.task === "overview" ? WS.renderOverview()
    : WS.task === "mybins" ? WS.renderMyBins()
    : WS.task === "print" ? WS.renderPrint()
    : WS.renderBar();
  if (html === WS.signature) return;
  const top = WS.rendered === WS.task ? stage.scrollTop : 0;
  const focused = document.activeElement?.closest?.("#ws-stage") ? document.activeElement : null;
  const key = focused ? (focused.dataset.wsAct ? `[data-ws-act="${focused.dataset.wsAct}"]`
    : focused.dataset.wsPick ? `[data-ws-pick="${focused.dataset.wsPick}"][data-id="${CSS.escape(focused.dataset.id || "")}"]`
    : focused.dataset.wsTick ? `[data-ws-tick="${CSS.escape(focused.dataset.wsTick)}"]` : null) : null;
  stage.innerHTML = html;
  WS.signature = html;
  WS.rendered = WS.task;
  stage.scrollTop = top;
  if (key) stage.querySelector(key)?.focus();
};

// ------------------------------------------------------------------ navigation

WS.remember = () => {
  WS.memory = {
    sel: WS.sel,
    view: DV?.view ? { ...DV.view } : null,
    scroll: $("#ws-stage")?.scrollTop || 0,
  };
};

WS.restore = () => {
  const memory = WS.memory;
  WS.memory = null;
  if (!memory) return;
  WS.sel = memory.sel;
  if (memory.sel?.kind === "bin" && !DL.bin(memory.sel.id)) WS.sel = null;
  if (memory.view && DV?.view) { Object.assign(DV.view, memory.view); }
  if (WS.sel?.kind === "bin") DL.selectRow(WS.sel.id);
  requestAnimationFrame(() => {
    if (typeof DV !== "undefined") DV.render();
    const stage = $("#ws-stage");
    if (stage) stage.scrollTop = memory.scroll;
  });
};

// Leaving Space Settings saves what was typed (it autosaves as it always did) - no prompt.
WS.closeSettings = async () => {
  if (!SP.editing) return true;
  if (!(await SP.flushSetupAutosave())) {
    toast("Fix the highlighted Space setting first - it could not be saved yet.", true, 6000);
    return false;
  }
  SP.cancelInlineEdit();
  return true;
};

WS.flushBin = async () => {
  if (WS.task === "bin" && WS.open() && typeof flushSpaceDesignAutosave === "function") {
    return flushSpaceDesignAutosave({ deferDraftPreview: true });
  }
  return true;
};

WS.go = async (task, arg = null) => {
  if (WS.busy) return false;
  WS.busy = true;
  try { return await WS.transition(task, arg); }
  catch (error) { toast(friendlyError(error), true, 6000); return false; }
  finally { WS.busy = false; WS.sync(); }
};

WS.toSpaceMode = async () => (DP.mode === "space" || await DP.selectMode("space"));

WS.transition = async (task, arg) => {
  const from = WS.task;
  if (task === "picker") {
    if (!(await WS.closeSettings()) || !(await WS.flushBin())) return false;
    SP.close?.();
    WS.task = "picker";
    WS.message = arg || "";
    SP.refreshOtherSpaces?.().then(() => WS.sync());
    return true;
  }
  if (task === "mybins") {
    WS.task = "mybins";
    WS.sel = null;
    return true;
  }
  if (!WS.open() && task !== "bin") return false;
  if (from === "settings" && task !== "settings" && !(await WS.closeSettings())) return false;
  if (task === "overview") {
    if (!(await WS.toSpaceMode())) return false;
    WS.task = "overview";
    WS.restore();
    return true;
  }
  if (task === "settings") {
    if (!(await WS.toSpaceMode())) return false;
    if (from === "overview") WS.remember();
    SP.editSpace();
    WS.task = "settings";
    return true;
  }
  if (task === "print") {
    if (!(await WS.toSpaceMode())) return false;
    if (from === "overview") WS.remember();
    WS.printPick = new Set();
    WS.printContainer = false;
    WS.task = "print";
    return true;
  }
  if (task === "container") {
    if (from === "overview") WS.remember();
    if (DP.mode !== "design" && !(await DP.selectMode("design"))) return false;
    if (!(await DP.openStructuralTarget())) return false;
    WS.task = "container";
    return true;
  }
  if (task === "bin") {
    if (!WS.open()) {
      if (state.folderMode === "space") return false;
      WS.task = "bin"; // a loose bin is already on screen
      return true;
    }
    if (from === "overview") WS.remember();
    const ok = arg ? await DP.openInventoryRow(arg) : await DP.newBinFromSpace();
    if (!ok) return false;
    WS.task = "bin";
    return true;
  }
  return false;
};

WS.back = () => {
  if (!WS.open()) return WS.go("mybins");
  return WS.go("overview");
};

// A place just changed (a Space opened, created or left): land on its Overview.
WS.arrive = () => {
  WS.memory = null;
  WS.sel = null;
  WS.printPick = new Set();
  WS.printContainer = false;
  if (WS.open()) {
    WS.task = "overview";
    WS.settle(0);
  } else if (state.folderMode !== "space") {
    WS.task = WS.landing || "mybins";
    WS.landing = null;
  }
};

// Opening a Space can leave the panel in Design (a structural Space, or a lone bin);
// once its own flow has finished, put it on the Overview.
WS.settle = tries => {
  setTimeout(() => {
    if (WS.task !== "overview" || !WS.open()) return;
    if (WS.busy || SP.busy) { if (tries < 60) WS.settle(tries + 1); return; }
    if (DP.mode !== "space") WS.go("overview");
  }, 150);
};

// Coming back from Classic: show the task that matches what is actually open.
WS.reconcile = () => {
  if (WS.open()) {
    WS.task = DP.mode === "space" ? "overview" : state.designTarget?.kind === "structural" ? "container" : "bin";
  } else {
    WS.task = state.folderMode === "space" ? "picker" : "mybins";
  }
  WS.sel = null;
  WS.memory = null;
  WS.placeSeen = WS.placeKey();
};

WS.setEnabled = async on => {
  if (!on && !(await WS.closeSettings())) return;
  try { localStorage.setItem(WS_PREF_KEY, on ? "workspace" : "classic"); }
  catch (_error) { toast("Your choice could not be remembered in this browser.", true); }
  if (on) WS.reconcile();
  WS.sync();
};

// ------------------------------------------------------------------ actions

WS.openSpaceRow = button => {
  const src = button.dataset.src;
  const index = Number(button.dataset.index);
  if (src === "current") return WS.go("overview");
  if (src === "other") {
    const one = SP.otherSpaces[index];
    if (one) SP.run(() => SP.afterPick(one.folder));
    return null;
  }
  const one = SP.recent[index];
  if (one) SP.run(() => SP.afterPick(state.runtime.hosted ? { handle: one.handle, name: one.folder_name || one.name } : one.folder));
  return null;
};

WS.newSpace = async kind => {
  if (kind === "none") return WS.enterLoose("bin");
  if (state.runtime.hosted && !window.WFFileSystem?.supportsDirectoryPicker()) {
    SP.showFolderAccessNeeded("unsupported");
    return;
  }
  // Same rule as the type cards: a repeat-size template only prefills its own type.
  const candidate = SP.setupPrefillSpace;
  const candidateKind = candidate?.kind === "box" ? "portable" : candidate?.kind;
  if (kind === "storage_drawers" && SP.configureData) return;
  SP.showSetup(kind, candidateKind === kind ? candidate : null);
};

// My Bins / No Space: leave any Space and land on the loose bins.
WS.enterLoose = async landing => {
  if (WS.busy) return;
  if (state.folderMode === "space") {
    WS.landing = landing;
    await SP.startNoSpace();
    if (state.folderMode === "space") { WS.landing = null; return; }
    WS.task = landing;
    WS.sel = null;
    WS.sync();
    return;
  }
  if (landing === "bin") {
    if (!(await designerNewBin())) return;
    WS.go("bin");
  } else {
    WS.go("mybins");
  }
};

WS.select = async sel => {
  WS.sel = sel;
  if (WS.open()) {
    if (sel.kind === "bin") {
      const one = DL.bin(sel.id);
      if (one) await DP.activateInventoryRow(one);
    } else {
      DL.selected = null; DL.selectedRow = null; DL.emit();
    }
  }
  WS.sync();
};

WS.editSelected = () => {
  if (!WS.open()) return WS.go("bin");
  if (WS.sel?.kind === "container") return WS.go("container");
  if (WS.sel?.kind === "bin") return WS.go("bin", WS.sel.id);
  return null;
};

// A bin's own button, the same as the row's Print: a single bin through the existing flow.
WS.printSelected = event => {
  if (!WS.open()) return WS.printOpenBin();
  if (WS.sel?.kind === "container") return WS.printContainerNow(event);
  const one = WS.sel && DL.bin(WS.sel.id);
  if (one) DL.printSelectedBins({ [one.id]: DL.printCount(one) }, false);
  return null;
};

WS.printContainerNow = event => {
  if (WS.containerKind() === "storage_drawers") return SP.printCabinetAndBins(event);
  return SP.printStructural(event);
};

// The same Print / Export choice the open bin's own buttons give. The bin
// editor has one Print Bin button (the form's); the slim bar no longer carries
// a second copy whose enabled state could drift from it.
WS.printOpenBin = () => {
  const target = $("#print-individual-bin");
  if (!target || target.disabled) return;
  chooseIndividualBinPrint(target);
  const dialog = $("#individual-bin-print-dialog");
  dialog.querySelector('[value="export"]').hidden = false;
  dialog.querySelector('[value="print"]').hidden = Boolean(state.runtime.hosted);
  $("#individual-bin-print-message").textContent = "Choose what to include. Print sends it to the slicer; Export creates a file.";
};

WS.printPicked = async event => {
  let ids = WS.pickedIds();
  // The cabinet's own print already includes the bins placed in its drawers.
  if (WS.printContainer && WS.containerKind() === "storage_drawers") ids = ids.filter(id => !DL.placedCount(id));
  if (ids.length) await DL.printSelectedBins(Object.fromEntries(ids.map(id => [id, DL.printCount(DL.bin(id))])), true);
  if (WS.printContainer) await WS.printContainerNow(event);
};

WS.exportPicked = async () => {
  const ids = WS.pickedIds();
  if (ids.length) await DL.saveSelectedBins(ids, true);
  if (WS.printContainer) {
    if (WS.containerKind() === "storage_drawers") await SP.runCabinetStructural("save");
    else await SP.saveStructural();
  }
};

WS.pickAll = () => {
  WS.printPick = new Set((DL.bins || []).filter(one => DL.isOrdinary(one) && DL.printEligible(one)).map(one => one.id));
  WS.printContainer = Boolean(WS.containerKind());
  WS.sync();
};

WS.onAction = async (act, button, event) => {
  switch (act) {
    case "open-space": return WS.openSpaceRow(button);
    case "my-bins": return WS.enterLoose("mybins");
    case "open-folder": return SP.run(SP.openExisting);
    case "storage": return SP.changeStorageParent();
    case "new-space": return WS.newSpace(button.dataset.kind);
    case "edit-space": return WS.go("settings");
    case "edit-container": return WS.go("container");
    case "print-space": return WS.go("print");
    case "new-bin": return WS.newBin();
    case "sel-edit": return WS.editSelected();
    case "sel-print": return WS.printSelected(event);
    case "sel-dup": { const one = WS.sel && DL.bin(WS.sel.id); if (one) await DP.duplicateRow(one); return null; }
    case "sel-del": {
      const one = WS.sel && DL.bin(WS.sel.id);
      if (!one) return null;
      await DP.deleteRow(one);
      if (!DL.bin(one.id)) WS.sel = null;
      WS.sync();
      return null;
    }
    case "back": return WS.back();
    case "print-bin": return WS.printOpenBin();
    case "print-picked": return WS.printPicked(event);
    case "export-picked": return WS.exportPicked();
    case "pick-all": return WS.pickAll();
    case "pick-none": WS.printPick = new Set(); WS.printContainer = false; WS.sync(); return null;
    case "done": return WS.go("overview");
    default: return null;
  }
};

WS.newBin = async () => {
  if (WS.open()) return WS.go("bin", null);
  if (!(await designerNewBin())) return false;
  return WS.go("bin");
};

// ------------------------------------------------------------------ sync

WS.sync = () => {
  const on = WS.enabled();
  const body = document.body;
  const frame = $("#ws-frame");
  const roll = $("#ws-ui-toggle");
  if (frame) frame.hidden = !on;
  // One Roll back button: it lives in the frame here, and in the header in Classic.
  const slot = $("#ws-roll-slot");
  const home = $(".header-actions");
  if (roll && slot && home) {
    if (on && roll.parentElement !== slot) slot.appendChild(roll);
    if (!on && roll.parentElement !== home) home.insertBefore(roll, $("#suggestions-open"));
    roll.textContent = on ? "Temp only Roll back" : "Back to the new UI";
  }
  if (!on) {
    [...body.classList].filter(name => name.startsWith("ws-")).forEach(name => body.classList.remove(name));
    WS.render();
    WS.measure();
    return;
  }
  const key = WS.placeKey();
  if (key !== WS.placeSeen) {
    const first = WS.placeSeen === "";
    WS.placeSeen = key;
    if (!first && key !== "space-pending") WS.arrive();
  }
  // A task that needs an open Space falls back when that Space is gone.
  if (["overview", "settings", "container", "print"].includes(WS.task) && !WS.open() && state.folderMode !== "space") {
    WS.task = "mybins";
  }
  const full = WS_FULL.includes(WS.task) || (WS.task === "overview" && !WS.hasCanvas());
  body.classList.add("ws-on");
  for (const name of ["picker", "overview", "settings", "container", "bin", "print", "mybins"]) {
    body.classList.toggle(`ws-task-${name}`, WS.task === name);
  }
  body.classList.toggle("ws-full", full);
  const place = $("#ws-place");
  if (place) place.textContent = WS.placeName();
  const newBin = $("#ws-new-bin");
  if (newBin) newBin.hidden = WS.task === "picker" || (!WS.open() && state.folderMode === "space");
  WS.render();
  WS.measure();
};

WS.measure = () => {
  const root = document.documentElement.style;
  const frame = $("#ws-frame");
  const stage = $("#ws-stage");
  if (!WS.enabled() || !frame) { root.setProperty("--ws-chrome", "0px"); return; }
  const frameHeight = frame.offsetHeight;
  root.setProperty("--ws-frame", `${frameHeight}px`);
  const full = document.body.classList.contains("ws-full");
  root.setProperty("--ws-chrome", `${frameHeight + (full || !stage ? 0 : stage.offsetHeight)}px`);
};

// ------------------------------------------------------------------ hooks into the existing code

// Overview: a click on a bin in the layout selects it; it never navigates.
DP.onLayoutClick = key => {
  if (!WS.enabled() || WS.task !== "overview" || !WS.open()) return false;
  const found = DL.findPlacement(key);
  const one = found && DL.bin(found.placement.bin);
  if (!one || !DL.isOrdinary(one)) return false;
  WS.select({ kind: "bin", id: one.id });
  return true;
};
// The layout is for looking and picking in the Overview; placing happens in Space settings.
DP.layoutViewOnly = () => WS.enabled() && WS.task === "overview";

// The welcome / type-card dialogs become the Picker; opening a Space lands on its Overview.
const wsOriginal = {
  showHome: SP.showHome,
  showTypeCards: SP.showTypeCards,
  showResume: SP.showResume,
  openPreferred: SP.openTypedSpacePreferredView,
};
SP.showHome = (message = null) => {
  if (!WS.enabled()) return wsOriginal.showHome(message);
  SP.close();
  WS.go("picker", message);
  return null;
};
SP.showTypeCards = () => {
  if (!WS.enabled()) return wsOriginal.showTypeCards();
  SP.close();
  WS.go("picker");
  return null;
};
SP.showResume = info => {
  if (!WS.enabled()) return wsOriginal.showResume(info);
  SP.resume = info;
  SP.run(SP.confirmResume);
  return null;
};
SP.openTypedSpacePreferredView = async () => {
  if (!WS.enabled()) return wsOriginal.openPreferred();
  try {
    if (!(await DL.ensureLoaded())) return false;
  } catch (error) {
    toast(`Could not read this Space's inventory: ${error.message}`, true, 7000);
    return false;
  }
  if (!(await DP.enter("space", true))) return false;
  WS.arrive();
  WS.sync();
  return true;
};

// ------------------------------------------------------------------ wiring

(() => {
  const stage = $("#ws-stage");
  if (!stage) return;
  stage.addEventListener("click", event => {
    const pick = event.target.closest("[data-ws-pick]");
    if (pick) {
      if (WS.busy) return;
      WS.select(pick.dataset.wsPick === "container" ? { kind: "container" } : { kind: "bin", id: pick.dataset.id || null });
      return;
    }
    const button = event.target.closest("[data-ws-act]");
    if (button && !button.disabled) WS.onAction(button.dataset.wsAct, button, event);
  });
  stage.addEventListener("change", event => {
    const tick = event.target.dataset.wsTick;
    if (tick) {
      if (tick === "container") WS.printContainer = event.target.checked;
      else if (event.target.checked) WS.printPick.add(tick); else WS.printPick.delete(tick);
      WS.sync();
      return;
    }
    if (event.target.matches("[data-ws-switch]") && event.target.value) WS.go("bin", event.target.value);
  });

  // Settle any Space Settings edit first (WS.go saves it), then start the picker clean.
  const startPicker = async () => { if (await WS.go("picker")) SP.clearSetupContext(); };
  $("#ws-spaces").addEventListener("click", startPicker);
  $("#ws-ui-toggle").addEventListener("click", () => WS.setEnabled(!WS.enabled()));
  const menu = $("#ws-new-menu");
  const toggle = $("#ws-new");
  const closeMenu = () => { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); };
  toggle.addEventListener("click", event => {
    event.stopPropagation();
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  });
  document.addEventListener("click", event => { if (!menu.hidden && !menu.contains(event.target)) closeMenu(); });
  $("#ws-new-bin").addEventListener("click", () => { closeMenu(); WS.newBin(); });
  $("#ws-new-space").addEventListener("click", () => { closeMenu(); startPicker(); });
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
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(() => { WS.measure(); if (typeof DV !== "undefined") DV.render(); });
    observer.observe(stage);
    observer.observe($("#ws-frame"));
  }
  WS.sync();
})();
