"use strict";

// Story 2692 - the unified screen (Debate 2691 ruling; replaces the 2674 one-task-per-page layout).
//
// One screen, two persistent panes under a global top bar:
//   LEFT   (A) a bounded "In this space" selector (container first, then bins) pinned at the top;
//          (B) the editor beneath it - the existing, unchanged container / bin / Space settings
//              forms, or temporarily the Print Space tick list or the New Space kinds.
//   RIGHT  shows the selected bin, container, or Space layout without changing the editor.
// Choosing a row selects it AND opens its form at once; there is no separate edit mode.
// This layer changes where the existing forms live and how they are reached, never what they hold:
//   Container editor -> DP.openStructuralTarget()   Storage Box / Drawers / Surface
//   Bin editor       -> DP.openInventoryRow(id)     the bin form
//   Space settings   -> DP.selectMode("space") + SP.editSpace()
// The classic screens and forms remain as the editors this layer hosts; there is no switch back to the old layout.

const WS = {
  task: "landing", // landing | container | bin | settings | print | newspace | picker  (bin with no Space = My Bins)
  prior: null, // the editor Print Space / New Space was opened from
  printPick: new Set(),
  printContainer: false,
  busy: false,
  message: "",
  landing: null,
  placeSeen: "",
  signature: "",
  auxSignature: "",
  previewSignature: "",
  entered: "",
};
const WS_TASKS = ["landing", "container", "bin", "settings", "print", "newspace", "picker"];

WS.open = () => Boolean(typeof DL !== "undefined" && DL.active && DL.layout && state.folderMode === "space");

const wsEsc = value => escapeHtml(String(value ?? ""));

// ------------------------------------------------------------------ places

WS.placeKey = () => (WS.open() ? `space:${state.activeSpaceId || state.activeSpace?.name}`
  : state.folderMode === "space" ? "space-pending" : "loose");

WS.placeName = () => (WS.open() ? state.activeSpace?.name || "Space" : state.folderMode === "space" ? "" : "My Bins");

// The one container a Space owns.
WS.containerKind = () => SP.structuralKind();
WS.containerName = () => ({ storage_box: "Storage box", storage_drawers: "Drawers", base_trim: "Surface" })[WS.containerKind()] || "";

WS.looseName = () => ($("#part-name")?.value || "").trim() || "New bin";

// ------------------------------------------------------------------ items

// Container first, then bins (grouped by drawer when a Space has several).
// In My Bins the loose bin is listed with no container row.
WS.items = () => {
  const items = [];
  const add = (kind, id, label, extra = {}) => items.push({ kind, id, label, ...extra });
  if (!WS.open()) {
    add("bin", "", WS.looseName(), { note: "on this screen now" });
    return items;
  }
  if (WS.containerKind()) add("container", "container", WS.containerName());
  const bins = (DL.bins || []).filter(DL.isOrdinary);
  const binItem = one => add("bin", one.id, DL.label(one), {
    note: [`${fmt(one.x)} × ${fmt(one.y)} mm`, DL.statusLabel(one)].join(" · "),
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

// Which row is the active one: the container, or the bin whose form is open.
// While Print Space / New Space is showing, it is the row of the editor they came from.
WS.current = () => {
  const temporary = WS.task === "print" || WS.task === "newspace";
  const task = temporary ? WS.prior?.task : WS.task;
  if (task === "settings") return { kind: "settings", id: "settings" };
  if (task === "container") return { kind: "container", id: "container" };
  if (task === "bin") return { kind: "bin", id: WS.open() ? (temporary ? WS.prior.id : state.designInventoryId) || "" : "" };
  return null;
};

// ------------------------------------------------------------------ left: selector (A)

// Launch screen: existing spaces, My Bins, and (beside it) the New Space kinds.
WS.renderPicker = () => {
  const cards = WS.spaceRows().map(one => `<li><button type="button" class="ws-menu-item" data-ws-act="open-space" data-src="${one.src}" data-index="${one.index ?? ""}"${one.invalid ? " disabled" : ""}>
      <span class="ws-card-icon" aria-hidden="true">${SP.compactKindIcon(one.kind)}</span>
      <span class="ws-card-text"><strong>${wsEsc(one.name)}</strong><small>${wsEsc([SP_KINDS[one.kind]?.label, one.meta].filter(Boolean).join(" · "))}</small></span></button></li>`).join("");
  return `<div class="ws-sel">
    <div class="ws-sel-head"><h2>Open a Space</h2></div>
    ${WS.message ? `<p class="field-error" role="alert">${wsEsc(WS.message)}</p>` : ""}
    <ul class="ws-menu-list" aria-label="Your Spaces">${cards}
      <li><button type="button" class="ws-menu-item" data-ws-act="my-bins">
        <span class="ws-card-icon" aria-hidden="true">📦</span>
        <span class="ws-card-text"><strong>My Bins / No Space</strong><small>Bins that are not in a Space</small></span></button></li>
    </ul>
    <p class="ws-links"><button type="button" class="link-button" data-ws-act="open-folder">Open a Space folder…</button>${state.runtime.hosted ? "" : ' <button type="button" class="link-button" data-ws-act="storage">Change Wavefinity folder…</button>'}</p>
  </div>`;
};

WS.renderSelector = () => {
  if (WS.task === "picker") return WS.renderPicker();
  if (!WS.open() && state.folderMode === "space") return '<div class="ws-sel"><p role="status">Opening…</p></div>';
  const items = WS.items();
  const here = WS.open();
  const now = WS.current();
  const locked = WS.task === "print" || WS.task === "newspace";
  const rows = (here ? [{ kind: "settings", id: "settings", label: "Space design" }, ...items] : items).map(one => {
    if (one.kind === "group") return `<li class="ws-group" role="presentation">${wsEsc(one.label)}</li>`;
    const picked = Boolean(now) && now.kind === one.kind && (one.kind === "container" || String(now.id || "") === String(one.id || ""));
    const icon = one.kind === "container" ? "▦" : "▢";
    return `<li class="ws-row"><button type="button" class="ws-rowbtn${picked ? " selected" : ""}${one.kind === "container" ? " container" : ""}" data-ws-pick="${one.kind}" data-id="${wsEsc(one.id)}" aria-pressed="${picked}"${locked ? " disabled" : ""}>
      <span class="ws-ico" aria-hidden="true">${icon}</span><span class="ws-label">${wsEsc(one.label)}</span>${one.note ? `<span class="ws-note">${wsEsc(one.note)}</span>` : ""}</button></li>`;
  }).join("");
  const binSelected = !locked && WS.task === "bin" && (!here || Boolean(state.designInventoryId));
  const canDuplicate = binSelected && !$("#designer-duplicate")?.hidden && !$("#designer-duplicate")?.disabled;
  const selectedBin = here && state.designInventoryId ? DL.bin(state.designInventoryId) : null;
  const canDelete = binSelected && selectedBin && DP.editableSourceFor(selectedBin) && !DP.designNavBlocked();
  const actions = `${here ? "" : '<button type="button" class="button secondary dl-small" data-ws-act="new-space-choose">New Space</button>'}
      <button type="button" class="button primary dl-small" data-ws-act="new-bin"${locked ? " disabled" : ""}>+ New Bin</button>
      <button type="button" class="button secondary dl-small" data-ws-act="duplicate"${canDuplicate ? "" : " disabled"}>Duplicate</button>
      <button type="button" class="button danger dl-small" data-ws-act="delete"${canDelete ? "" : " disabled"}>Delete</button>`;
  return `<div class="ws-sel">
    <div class="ws-sel-head"><h2>${wsEsc(here ? WS.placeName() : "My Bins")}</h2><span class="ws-sel-actions">${actions}</span></div>
    ${WS.message ? `<p class="field-error" role="alert">${wsEsc(WS.message)}</p>` : ""}
    <ul class="ws-items" aria-label="${here ? `Contents of ${wsEsc(WS.placeName())}` : "Bins that are not in a Space"}">${rows || '<li class="ws-empty">Nothing here yet. Choose New Bin to add the first bin.</li>'}</ul>
  </div>`;
};

// ------------------------------------------------------------------ left: temporary editors (B)

WS.tickRows = items => items.map(one => {
  if (one.kind === "group") return `<li class="ws-group" role="presentation">${wsEsc(one.label)}</li>`;
  const on = one.kind === "container" ? WS.printContainer : WS.printPick.has(one.id);
  const off = one.kind === "bin" && !one.printable;
  return `<li class="ws-item"><label><input type="checkbox" data-ws-tick="${wsEsc(one.id)}"${on ? " checked" : ""}${off ? " disabled" : ""}>
    <span class="ws-label">${wsEsc(one.label)}</span>${one.note ? `<span class="ws-note">${wsEsc(one.note)}</span>` : ""}</label></li>`;
}).join("");

WS.pickedIds = () => [...WS.printPick].filter(id => DL.bin(id) && DL.printEligible(DL.bin(id)));

WS.renderPrint = () => {
  const items = WS.items();
  const hosted = Boolean(state.runtime.hosted);
  const noSlicer = !state.slicer || !state.slicer.available;
  const n = WS.pickedIds().length + (WS.printContainer ? 1 : 0);
  const none = n === 0 || DL.busy;
  return `<div class="ws-page ws-print">
    <h2>Print Space</h2>
    <p class="ws-printcount" role="status">${n === 0 ? "Tick what to print. The preview stays live on the right." : `${n} ${n === 1 ? "item" : "items"} ticked`}</p>
    <ul class="ws-items" aria-label="Items to print">${WS.tickRows(items)}</ul>
    <div class="ws-toprow" role="group" aria-label="Print Space">
      ${hosted ? "" : `<button type="button" class="button primary dl-small" data-ws-act="print-picked"${none || noSlicer ? " disabled" : ""}${noSlicer ? ' title="A slicer is needed to print. Open Printer Settings… to choose one."' : ""}>Print Selected</button>`}
      <button type="button" class="button secondary dl-small" data-ws-act="export-picked"${none ? " disabled" : ""}>Export Selected</button>
      <button type="button" class="button secondary dl-small" data-ws-act="pick-all">Tick all</button>
      <button type="button" class="button secondary dl-small" data-ws-act="pick-none">Clear</button>
      <button type="button" class="button secondary dl-small" data-ws-act="cancel">Cancel</button>
      <button type="button" class="button secondary dl-small" data-ws-act="cancel">Done</button>
    </div>
  </div>`;
};

// Every kind is a full artwork choice, equal in size.
WS.KINDS = [
  ["portable", "Storage Box", "A carrying case for your bins.", "B4B.png"],
  ["storage_drawers", "Storage Drawers", "Print a new cabinet with drawers.", "StorageDrawers.png"],
  ["surface", "Surface", "A countertop, shelf, or vanity.", "Vanity.png"],
  ["drawer", "Drawer", "A drawer you already have.", "Drawer.png"],
  ["pegboard", "Pegboard", "A pegboard you already have.", "Pegboard.png"],
];

WS.renderNewSpace = () => `<div class="ws-page ws-newspace">
    <h2>New Space - what are you organizing?</h2>
    <div class="ws-choices">${WS.KINDS.map(([kind, title, text, img]) => `<button type="button" class="ws-choice" data-ws-act="new-space" data-kind="${kind}">
      <img src="/images/${img}" alt="" width="120" height="90" decoding="async"><strong>${title}</strong><small>${text}</small></button>`).join("")}</div>
    ${WS.task === "picker" ? "" : '<div class="ws-toprow"><button type="button" class="button secondary dl-small" data-ws-act="cancel">Cancel</button></div>'}
  </div>`;

// ------------------------------------------------------------------ top bar

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

// The Spaces switcher: a dropdown anchored to the bar, never a full-screen picker.
WS.renderSpaceMenu = () => {
  const cards = WS.spaceRows().map(one => `<li><button type="button" class="ws-menu-item${one.current ? " current" : ""}" data-ws-act="open-space" data-src="${one.src}" data-index="${one.index ?? ""}"${one.invalid ? " disabled" : ""}>
      <span class="ws-card-icon" aria-hidden="true">${SP.compactKindIcon(one.kind)}</span>
      <span class="ws-card-text"><strong>${wsEsc(one.name)}</strong><small>${wsEsc([SP_KINDS[one.kind]?.label, one.meta].filter(Boolean).join(" · "))}</small></span>
      ${one.current ? '<em class="ws-card-tag">open now</em>' : ""}</button></li>`).join("");
  return `<ul class="ws-menu-list">${cards}
    <li><button type="button" class="ws-menu-item${state.folderMode !== "space" ? " current" : ""}" data-ws-act="my-bins">
      <span class="ws-card-icon" aria-hidden="true">📦</span>
      <span class="ws-card-text"><strong>My Bins / No Space</strong><small>Bins that are not in a Space</small></span></button></li>
  </ul>
  <p class="ws-links"><button type="button" class="link-button" data-ws-act="new-space-choose">New Space…</button> <button type="button" class="link-button" data-ws-act="open-welcome">Open a Space folder…</button>${state.runtime.hosted ? "" : ' <button type="button" class="link-button" data-ws-act="storage">Change Wavefinity folder…</button>'}</p>`;
};

WS.render = () => {
  const stage = $("#ws-stage");
  const aux = $("#ws-aux");
  if (!stage || !aux) return;
  stage.hidden = false;
  const draw = (host, html, key) => {
    if (html === WS[key]) return;
    const top = host.scrollTop;
    const focused = document.activeElement?.closest?.(`#${host.id}`) ? document.activeElement : null;
    const find = focused ? (focused.dataset.wsAct ? `[data-ws-act="${focused.dataset.wsAct}"]`
      : focused.dataset.wsPick ? `[data-ws-pick="${focused.dataset.wsPick}"][data-id="${CSS.escape(focused.dataset.id || "")}"]`
      : focused.dataset.wsTick ? `[data-ws-tick="${CSS.escape(focused.dataset.wsTick)}"]` : null) : null;
    host.innerHTML = html;
    WS[key] = html;
    host.scrollTop = top;
    if (find) host.querySelector(find)?.focus();
  };
  draw(stage, WS.renderSelector(), "signature");
  const auxHtml = WS.task === "print" ? WS.renderPrint() : WS.task === "newspace" || WS.task === "picker" ? WS.renderNewSpace() : "";
  aux.hidden = !auxHtml;
  draw(aux, auxHtml, "auxSignature");
};

// ------------------------------------------------------------------ navigation

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

// Remember which editor a temporary one (Print Space, New Space) was opened from.
WS.rememberPrior = () => {
  if (WS.task === "print" || WS.task === "newspace") return;
  WS.prior = { task: WS.task, id: WS.task === "bin" && WS.open() ? state.designInventoryId || "" : "" };
};

WS.transition = async (task, arg) => {
  const from = WS.task;
  if (task === "newspace") {
    if (!(await WS.closeSettings()) || !(await WS.flushBin())) return false;
    SP.close?.();
    WS.rememberPrior();
    WS.task = "newspace";
    SP.refreshOtherSpaces?.().then(() => WS.sync());
    return true;
  }
  if (task === "picker") {
    if (!(await WS.closeSettings()) || !(await WS.flushBin())) return false;
    SP.close?.();
    WS.prior = null;
    WS.task = "picker";
    SP.refreshOtherSpaces?.().then(() => WS.sync());
    return true;
  }
  if (task === "bin" && !WS.open()) {
    if (state.folderMode === "space") return false;
    WS.task = "bin"; // the loose bin is already on screen (My Bins)
    return true;
  }
  if (!WS.open()) return false;
  if (from === "settings" && task !== "settings" && !(await WS.closeSettings())) return false;
  if (task === "settings") {
    if (!(await WS.toSpaceMode())) return false;
    SP.editSpace();
    WS.task = "settings";
    return true;
  }
  if (task === "print") {
    WS.rememberPrior();
    WS.printPick = new Set();
    WS.printContainer = false;
    WS.task = "print";
    return true;
  }
  if (task === "container") {
    if (DP.mode !== "design" && !(await DP.selectMode("design"))) return false;
    if (!(await DP.openStructuralTarget())) return false;
    WS.task = "container";
    DL.selected = null; DL.selectedRow = null; DL.emit();
    return true;
  }
  if (task === "bin") {
    const ok = arg ? await DP.openInventoryRow(arg) : await DP.newBinFromSpace();
    if (!ok) return false;
    WS.task = "bin";
    if (arg) DL.selectRow(arg);
    return true;
  }
  return false;
};

// Cancel / Done: back to the editor that was showing before.
WS.resume = () => {
  const prior = WS.prior;
  WS.prior = null;
  if (prior && WS.open() && prior.task !== "landing") {
    if (prior.task === "settings") return WS.go("settings");
    WS.task = prior.task;
    WS.sync();
    return true;
  }
  if (prior && !WS.open() && state.folderMode !== "space") {
    WS.task = "bin";
    WS.sync();
    return true;
  }
  return WS.open() ? WS.land() : WS.go("bin");
};

// The screen a Space opens on: its container selected (a Space with none opens its first bin).
WS.land = async () => {
  if (!WS.open()) return false;
  if (WS.containerKind()) return WS.go("container");
  const first = (DL.bins || []).find(DL.isOrdinary);
  if (first) return WS.go("bin", first.id);
  return WS.go("settings");
};

// A place just changed (a Space opened, created or left).
WS.arrive = () => {
  WS.message = "";
  WS.prior = null;
  WS.printPick = new Set();
  WS.printContainer = false;
  if (WS.open()) {
    Object.assign(DV.view, { zoom: 1, panX: 0, panY: 0 });
    WS.task = "landing";
    WS.settle(0);
  } else if (state.folderMode !== "space") {
    WS.task = "bin";
    WS.landing = null;
  }
};

// Opening a Space can leave the panel in Design or Space mode; once its own flow has
// finished, put it on the container.
WS.settle = tries => {
  setTimeout(() => {
    if (WS.task !== "landing" || !WS.open()) return;
    if (WS.busy || SP.busy) { if (tries < 60) WS.settle(tries + 1); return; }
    WS.land();
  }, 150);
};

// ------------------------------------------------------------------ actions

// Open a Space from a row. On the open screen nothing is being edited, so leaving the
// restored Space must not wait on an editor prompt; if the switch cannot proceed the
// reason is shown on the screen itself, not only as a toast.
WS.pickSpace = folder => SP.run(async () => {
  WS.message = "";
  let opened = null;
  try {
    opened = await SP.afterPick(folder, WS.task === "picker" ? { visible: false } : undefined);
  } catch (error) {
    WS.message = `Could not open that Space: ${friendlyError(error)}`;
    WS.sync();
    throw error;
  }
  if (!opened) {
    WS.message = "That Space could not be opened because the Space that is open could not be saved first. Fix the problem there, then try again.";
    WS.sync();
  }
});

WS.openSpaceRow = button => {
  const src = button.dataset.src;
  const index = Number(button.dataset.index);
  if (src === "current") {
    if (!WS.open()) return null;
    DV.fit();
    return WS.land();
  }
  if (src === "other") {
    const one = SP.otherSpaces[index];
    if (one) WS.pickSpace(one.folder);
    return null;
  }
  const one = SP.recent[index];
  if (one) WS.pickSpace(state.runtime.hosted ? { handle: one.handle, name: one.folder_name || one.name } : one.folder);
  return null;
};

WS.newSpace = async kind => {
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

// My Bins / No Space: leave any Space and land on the loose bin.
WS.enterLoose = async () => {
  if (WS.busy) return;
  if (state.folderMode === "space") {
    await SP.startNoSpace();
    if (state.folderMode === "space") return;
    WS.task = "bin";
    WS.prior = null;
    WS.sync();
    return;
  }
  WS.go("bin");
};

WS.printContainerNow = event => {
  if (WS.containerKind() === "storage_drawers") return SP.printCabinetAndBins(event);
  return SP.printStructural(event);
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

WS.newBin = async () => {
  if (WS.open()) return WS.go("bin", null);
  if (!(await designerNewBin())) return false;
  return WS.go("bin");
};

// A row click selects the item and shows its form at once.
WS.pick = (kind, id) => {
  if (WS.busy || WS.task === "print" || WS.task === "newspace") return null;
  if (!WS.open()) return WS.go("bin");
  if (kind === "settings") return WS.task === "settings" ? null : WS.go("settings");
  if (kind === "container") return WS.task === "container" ? null : WS.go("container");
  if (!id || (WS.task === "bin" && id === state.designInventoryId)) return null;
  return WS.go("bin", id);
};

WS.onAction = async (act, button, event) => {
  switch (act) {
    case "open-space": return WS.openSpaceRow(button);
    case "my-bins": return WS.enterLoose();
    case "open-welcome": return WS.go("picker");
    case "open-folder": return SP.run(SP.openExisting);
    case "storage": return SP.changeStorageParent();
    case "new-space-choose": return WS.go("newspace");
    case "new-space": return WS.newSpace(button.dataset.kind);
    case "new-bin": return WS.newBin();
    case "duplicate": return $("#designer-duplicate")?.click();
    case "delete": return $("#designer-delete-bin")?.click();
    case "print-picked": return WS.printPicked(event);
    case "export-picked": return WS.exportPicked();
    case "pick-all": return WS.pickAll();
    case "pick-none": WS.printPick = new Set(); WS.printContainer = false; WS.sync(); return null;
    case "cancel": return WS.resume();
    default: return null;
  }
};

// ------------------------------------------------------------------ top bar: Print Bin / Export

// What Print Bin / Export act on: the selected container (Storage Box, Drawers, Surface) or the
// selected bin. Nothing else prints. Read from the live selection every time, never remembered.
WS.outputTarget = () => {
  if (WS.busy || !["bin", "container"].includes(WS.task)) return null;
  if (WS.task === "container") return WS.open() && WS.containerKind() && !SP.structuralBusy ? "container" : null;
  const bin = WS.open() ? Boolean(state.designInventoryId) : state.folderMode !== "space";
  return bin && !state.designMutationBusy && state.canGenerate ? "bin" : null;
};

WS.syncOutput = () => {
  const printBin = $("#ws-print-bin");
  const printContainer = $("#ws-print-container");
  const exportButton = $("#ws-export");
  if (!printBin || !exportButton) return;
  const target = WS.outputTarget();
  const what = WS.task === "container" ? WS.containerName().toLowerCase() || "container" : "bin";
  const hosted = Boolean(state.runtime.hosted);
  printBin.disabled = target !== "bin";
  printContainer.disabled = target !== "container";
  printContainer.textContent = `Print ${{ storage_box: "Box", storage_drawers: "Drawers", base_trim: "Surface" }[WS.containerKind()] || "Container"}`;
  exportButton.disabled = !target;
  printBin.title = !target ? "Select a bin, the storage box or the drawers to print it."
    : hosted ? "Printing needs local Wavefinity and a slicer"
    : !state.slicer?.available ? "A slicer is needed - use Printer Settings to choose one"
    : `Send the ${what} to ${state.slicer.name || "the slicer"}`;
  exportButton.title = target ? `Create the 3MF file for the ${what}` : "Select a bin, the storage box or the drawers to export it.";
};

WS.output = (mode, button, event) => {
  const target = WS.outputTarget();
  if (!target) return null;
  if (target === "bin") return chooseIndividualBinPrint(button);
  const drawers = WS.containerKind() === "storage_drawers";
  if (mode === "export") return drawers ? SP.runStructural("save") : SP.saveStructural();
  return drawers ? SP.runStructural("print", event) : SP.printStructural(event);
};

// ------------------------------------------------------------------ sync

WS.sync = () => {
  const body = document.body;
  const frame = $("#ws-frame");
  if (frame) frame.hidden = false;
  // The AI help button lives in the bar.
  const ai = $("#ai-help-open");
  const aiSlot = $("#ws-ai-slot");
  if (ai && aiSlot && ai.parentElement !== aiSlot) aiSlot.appendChild(ai);
  const key = WS.placeKey();
  if (key !== WS.placeSeen) {
    const first = WS.placeSeen === "";
    WS.placeSeen = key;
    if (!first && key !== "space-pending") WS.arrive();
  }
  // A task that needs an open Space falls back when that Space is gone.
  if (["landing", "container", "settings", "print"].includes(WS.task) && !WS.open() && state.folderMode !== "space") {
    WS.task = "bin";
  }
  // Story 2704: on the open screen nothing is chosen yet - no preview, nothing current, and the
  // space-dependent actions stay off, though the restored session is kept for picking from the list.
  const open = WS.open() && WS.task !== "picker";
  body.classList.add("ws-on");
  body.classList.toggle("ws-open", open);
  for (const name of WS_TASKS) body.classList.toggle(`ws-task-${name}`, WS.task === name);
  if (WS.task !== WS.entered) {
    WS.entered = WS.task;
    if (["bin", "container", "settings"].includes(WS.task)) WS.editorToTop();
  }
  const place = $("#ws-place");
  if (place) place.textContent = "Change Space";
  const printSpace = $("#ws-print-space");
  if (printSpace) {
    printSpace.disabled = !open || WS.task !== "settings" || WS.busy;
    printSpace.title = open ? "" : "My Bins have no Space to print. Open a Space first.";
  }
  WS.syncOutput();
  if (open) {
    const view = WS.task === "bin" || WS.task === "container" ? "3d" : "drawer";
    const wrap = $(`.canvas-wrap[data-canvas="${view}"]`);
    if (wrap && !wrap.classList.contains("active")) wsActivatePreview(view);
  }
  WS.render();
  WS.measure();
  const signature = `${WS.task}|${[...WS.printPick].join(",")}|${WS.printContainer}|${state.designInventoryId || ""}|${WS.prior?.id ?? ""}`;
  if (signature !== WS.previewSignature) {
    WS.previewSignature = signature;
    if (open && typeof DV !== "undefined") DV.paint();
  }
};

// An editor opens at its heading and first field, whatever the sidebar was scrolled to before
// (or a field focused while it filled in scrolled it partway down).
WS.editorToTop = () => {
  const reset = () => {
    if (!["bin", "container", "settings"].includes(WS.task)) return;
    const controls = $(".controls");
    const stage = $("#ws-stage");
    if (controls) controls.scrollTop = 0;
    if (stage) stage.scrollTop = 0;
    window.scrollTo(0, 0);
  };
  reset();
  requestAnimationFrame(reset);
  setTimeout(reset, 150);
};

WS.measure = () => {
  const root = document.documentElement.style;
  const frame = $("#ws-frame");
  if (!frame) { root.setProperty("--ws-chrome", "0px"); return; }
  const frameHeight = frame.offsetHeight;
  root.setProperty("--ws-frame", `${frameHeight}px`);
  root.setProperty("--ws-chrome", `${frameHeight}px`);
};

// ------------------------------------------------------------------ right: preview marks

// The preview is never edited; it only shows what the left side has selected:
// the container outline, the selected bin, or the bins ticked for print.
WS.paintPreview = () => {
  if (!WS.open() || !DV.cam || !DV.hits) return;
  const canvas = $("#drawer-canvas");
  const ctx = canvas?.getContext("2d");
  if (!ctx) return;
  const printing = WS.task === "print";
  const marked = printing ? WS.printPick
    : WS.task === "bin" && state.designInventoryId ? new Set([state.designInventoryId]) : new Set();
  const containerMarked = printing ? WS.printContainer : WS.task === "container";
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  ctx.save();
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.lineJoin = "round";
  if (containerMarked && Number.isFinite(DV.cam.W) && Number.isFinite(DV.cam.D)) {
    const { W, D } = DV.cam;
    const corners = [[0, 0, 0], [W, 0, 0], [W, D, 0], [0, D, 0]].map(DV.cam.project);
    ctx.beginPath();
    corners.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 4;
    ctx.stroke();
  }
  for (const hit of DV.hits) {
    const id = hit.key && DL.findPlacement(hit.key)?.placement?.bin;
    if (!id || !marked.has(id)) continue;
    ctx.fillStyle = "rgba(37,99,235,.22)";
    ctx.strokeStyle = "#2563eb";
    ctx.lineWidth = 3;
    for (const poly of hit.polys) {
      ctx.beginPath();
      poly.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    if (printing) {
      const top = hit.polys[hit.polys.length - 1];
      const cx = top.reduce((sum, p) => sum + p[0], 0) / top.length;
      const cy = top.reduce((sum, p) => sum + p[1], 0) / top.length;
      ctx.fillStyle = "#15803d";
      ctx.font = '700 16px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("✓", cx, cy);
    }
  }
  ctx.restore();
};

// ------------------------------------------------------------------ hooks into the existing code

// The unified selection owns the preview; the classic interface keeps its normal routing.
const wsActivatePreview = activatePreviewView;
activatePreviewView = view => {
  if (!WS.open()) return wsActivatePreview(view);
  const chosen = WS.task === "bin" || WS.task === "container" ? "3d" : "drawer";
  return wsActivatePreview(chosen);
};

const wsRender = DV.render;
DV.render = () => { wsRender(); WS.paintPreview(); };

// A click on a bin in the preview picks it (its form opens at once); the preview never edits.
DP.onLayoutClick = key => {
  if (!WS.open() || WS.task === "settings" || WS.task === "print" || WS.task === "newspace") return false;
  const found = DL.findPlacement(key);
  const one = found && DL.bin(found.placement.bin);
  if (!one || !DL.isOrdinary(one)) return false;
  WS.pick("bin", one.id);
  return true;
};
DP.layoutViewOnly = () => WS.open() && WS.task !== "settings";

// The welcome / type-card dialogs become the bar and the New Space kinds; a restored
// session opens its last Space (container selected) straight away - nothing covers it.
SP.showHome = (message = null) => {
  SP.close();
  WS.message = message || "";
  if (WS.open()) WS.resume(); else WS.enterLoose();
  WS.sync();
  return null;
};
SP.showTypeCards = () => {
  SP.close();
  WS.go("newspace");
  return null;
};
SP.showResume = (info, { startup = false } = {}) => {
  SP.resume = info;
  SP.close();
  if (startup) {
    // Launch always shows the open screen (spaces, My Bins, New Space) - never the last space,
    // and no "Designing without a Space" toast: nothing is opened yet.
    WS.placeSeen = WS.placeKey();
    WS.prior = null;
    WS.task = "picker";
    SP.refreshOtherSpaces?.().then(() => WS.sync());
    WS.sync();
    return null;
  }
  SP.run(SP.confirmResume).then(() => { if (!WS.open()) WS.enterLoose(); });
  return null;
};
SP.openTypedSpacePreferredView = async () => {
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
  const controls = $(".controls");
  if (!stage || !controls) return;
  // The selector lives at the top of the left pane; the temporary editors sit right under it.
  const aux = document.createElement("section");
  aux.id = "ws-aux";
  aux.className = "ws-aux";
  aux.hidden = true;
  controls.prepend(aux);
  controls.prepend(stage);

  const menu = $("#ws-space-menu");
  const toggle = $("#ws-spaces");
  const closeMenu = () => { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); };
  const delegate = event => {
    const pick = event.target.closest("[data-ws-pick]");
    if (pick) { WS.pick(pick.dataset.wsPick, pick.dataset.id || ""); return; }
    const button = event.target.closest("[data-ws-act]");
    if (button && !button.disabled) {
      closeMenu();
      WS.onAction(button.dataset.wsAct, button, event);
    }
  };
  [stage, aux, menu].forEach(host => host.addEventListener("click", delegate));
  aux.addEventListener("change", event => {
    const tick = event.target.dataset.wsTick;
    if (!tick) return;
    if (tick === "container") WS.printContainer = event.target.checked;
    else if (event.target.checked) WS.printPick.add(tick); else WS.printPick.delete(tick);
    WS.sync();
  });

  toggle.addEventListener("click", event => {
    event.stopPropagation();
    if (menu.hidden) {
      menu.innerHTML = WS.renderSpaceMenu();
      SP.refreshOtherSpaces?.().then(() => { if (!menu.hidden) menu.innerHTML = WS.renderSpaceMenu(); });
    }
    menu.hidden = !menu.hidden;
    toggle.setAttribute("aria-expanded", String(!menu.hidden));
  });
  document.addEventListener("click", event => { if (!menu.hidden && !menu.contains(event.target)) closeMenu(); });
  $("#ws-print-space").addEventListener("click", () => { closeMenu(); WS.go("print"); });
  for (const id of ["#ws-print-bin", "#ws-print-container", "#ws-export"]) {
    $(id).addEventListener("click", event => { closeMenu(); WS.output(event.currentTarget.dataset.output, event.currentTarget, event); });
  }
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
    observer.observe($(".workspace"));
    observer.observe($("#ws-frame"));
  }
  WS.sync();
})();
