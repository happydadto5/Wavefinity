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
  task: "landing", // landing | container | bin | peek | settings | newspace | picker  (bin with no Space = My Bins)
  peekId: null,
  prior: null, // the editor Print Space / New Space was opened from
  busy: false,
  queuedDeleteId: null,
  message: "",
  treeNote: "",
  placeSeen: "",
  signature: "",
  auxSignature: "",
  previewSignature: "",
  entered: "",
};
const WS_TASKS = ["landing", "container", "bin", "peek", "settings", "newspace", "picker", "none"];

WS.open = () => Boolean(typeof DL !== "undefined" && DL.active && DL.layout && state.folderMode === "space");

const wsEsc = value => escapeHtml(String(value ?? ""));

WS.showNote = (id, text) => {
  const node = document.getElementById(id);
  if (node) { node.textContent = text; node.hidden = !text; }
};
WS.showTreeNote = text => {
  WS.treeNote = text;
  WS.sync();
};
// Clear the previous action's notes before the next action can set new ones.
for (const type of ["pointerdown", "keydown", "change"]) {
  document.addEventListener(type, () => {
    WS.treeNote = "";
    for (const id of ["ws-action-note", "bin-action-note", "dl-sp-action-note", "dl-layout-action-note"]) WS.showNote(id, "");
  }, true);
}

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
  // Story 2753: a bin placed in a drawer carries that drawer's label in its own row, not only the group line.
  // The bin whose editor is open shows the name as typed in Part Name, not the last saved one, so a rename
  // lands in the pick list in the same edit (Story 2806). Blank typing falls back to the saved label.
  const liveLabel = one => {
    const typed = ["bin", "peek"].includes(WS.task) && String(one.id) === String(state.designInventoryId ?? "")
      ? ($("#part-name")?.value || "").trim() : "";
    return typed || DL.label(one);
  };
  const stackNote = (one, drawer = DL.drawer()) => {
    const item = DL.items(drawer).find(entry => entry.layers.some(layer => String(layer.bin.id) === String(one.id)));
    if (!item || item.layers.length < 2) return "";
    const layer = item.layers.find(entry => String(entry.bin.id) === String(one.id));
    if (layer.parent) {
      const parent = item.layers.find(entry => entry.key === layer.parent);
      return parent ? `Stacked on ${DL.label(parent.bin)}` : "";
    }
    return `Bottom of a stack of ${item.layers.length}`;
  };
  const binItem = (one, drawerLabel = "", drawer = DL.drawer()) => add("bin", one.id, liveLabel(one), {
    note: [drawerLabel, `${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm`, stackNote(one, drawer)].filter(Boolean).join(" · "),
    printable: DL.printEligible(one),
  });
  const placed = new Set(bins.filter(one => DL.placedCount(one.id) > 0).map(one => one.id));
  const loose = bins.filter(one => !placed.has(one.id));
  if (loose.length) { add("group", null, "Not placed"); loose.forEach(one => binItem(one)); }
  const drawers = DL.layout.drawers || [];
  if (DL.isStorageDrawers() || drawers.length > 1) {
    drawers.forEach((drawer, index) => {
      const here = [...new Map((drawer.placements || []).map(p => DL.bin(p.bin))
        .filter(one => one && DL.isOrdinary(one)).map(one => [one.id, one])).values()];
      const label = drawer.name || `Drawer ${index + 1}`;
      if (here.length) { add("group", null, label); here.forEach(one => binItem(one, label, drawer)); }
    });
  } else if (placed.size) {
    add("group", null, "Placed");
    bins.filter(one => placed.has(one.id)).forEach(one => binItem(one));
  }
  return items;
};

// Which row is the active one: the container, or the bin whose form is open.
// While Print Space / New Space is showing, it is the row of the editor they came from.
WS.current = () => {
  if (WS.pending) return WS.pending; // Story 2735: a clicked row is selected at once, before its view is ready
  const temporary = WS.task === "newspace";
  const task = temporary ? WS.prior?.task : WS.task;
  if (task === "settings") return { kind: "settings", id: "settings" };
  if (task === "container") return { kind: "container", id: "container" };
  if (task === "peek") return { kind: "bin", id: temporary ? WS.prior.id : WS.peekId };
  if (task === "bin") return { kind: "bin", id: WS.open() ? (temporary ? WS.prior.id : state.designInventoryId) || "" : "" };
  return null;
};

// ------------------------------------------------------------------ left: selector (A)

// Launch screen: existing spaces, My Bins, and (beside it) the New Space kinds.
WS.renderPicker = () => {
  const spaces = WS.spaceRows();
  const browserRequirement = state.runtime.hosted && !window.WFFileSystem?.supportsDirectoryPicker()
    ? "Use Chrome or Edge on a computer. This browser or device can't give Wavefinity a folder, so here you can design and download parts only."
    : "";
  const hasFolder = Boolean(state.folderSelected || SP.hostedHome?.handle || SP.pendingReconnect);
  const cards = spaces.map(one => `<li><button type="button" class="ws-menu-item" data-ws-act="open-space" data-src="${one.src}" data-index="${one.index ?? ""}" aria-label="${wsEsc(`Open ${[one.name, SP_KINDS[one.kind]?.label, one.meta].filter(Boolean).join(", ")}${one.invalid ? " (unavailable)" : ""}`)}"${one.invalid ? " disabled" : ""}>
      <span class="ws-card-icon" aria-hidden="true">${SP.compactKindIcon(one.kind)}</span>
      <span class="ws-card-text"><strong>${wsEsc(one.name)}</strong><small>${wsEsc([SP_KINDS[one.kind]?.label, one.meta].filter(Boolean).join(" · "))}</small></span></button></li>`).join("");
  return `<div class="ws-sel">
    <div class="ws-sel-head"><h2>${hasFolder || spaces.length ? "Open an existing space" : "Welcome to Wavefinity"}</h2></div>
    ${browserRequirement ? `<p>${wsEsc(browserRequirement)}</p>` : ""}
    ${spaces.length ? "" : '<p class="ws-links">No spaces yet - pick what you\'re organizing below.</p>'}
    ${WS.message ? `<p class="field-error" role="alert">${wsEsc(WS.message)}</p>` : ""}
    ${SP.pendingReconnect ? `<p><button type="button" class="button primary" data-ws-act="reconnect">Reconnect folder</button>${SP.pendingReconnect.homeReconnect ? '<span> Your browser may offer "Allow on every visit" — choose it so you are not asked again.</span>' : ""}</p>` : ""}
    <ul class="ws-menu-list" aria-label="Your Spaces">${cards}
      <li><button type="button" class="ws-menu-item" data-ws-act="my-bins" aria-label="Open My Bins, bins that are not in a Space">
        <span class="ws-card-icon" aria-hidden="true">📦</span>
        <span class="ws-card-text"><strong>My Bins / No Space</strong><small>Bins that are not in a Space</small></span></button></li>
    </ul>
    ${!hasFolder || !state.runtime.hosted ? `<p class="ws-links">${hasFolder ? "" : '<button type="button" class="link-button" data-ws-act="open-folder">Open a Space folder…</button>'}${state.runtime.hosted ? "" : ' <button type="button" class="link-button" data-ws-act="storage">Change Wavefinity folder…</button>'}</p>` : ""}
  </div>`;
};

// Story 2752: in a Storage Drawers space the Layout row carries small 1 / 2 / 3 drawer buttons.
WS.drawerButtons = locked => {
  if (!DL.isStorageDrawers() || !DL.layout?.drawers?.length) return "";
  const off = locked || SP.editing || SP.structuralBusy || DP.designNavBlocked();
  return `<span class="ws-drawers" role="group" aria-label="Drawers"><span class="ws-drawers-word">Drawers:</span>${DL.layout.drawers.map((row, index) =>
    `<button type="button" class="ws-drawerbtn${DL.layout.active === row.id ? " selected" : ""}" data-ws-act="drawer" data-id="${wsEsc(row.id)}" aria-pressed="${DL.layout.active === row.id}" aria-label="Show Drawer ${index + 1}"${off ? " disabled" : ""}>${index + 1}</button>`).join("")}</span>`;
};

WS.renderSelector = () => {
  if (WS.task === "picker") return WS.renderPicker();
  if (!WS.open() && state.folderMode === "space") return '<div class="ws-sel"><p role="status">Opening…</p></div>';
  const items = WS.items();
  const here = WS.open();
  const now = WS.current();
  // Story 2816: Print Space (the layout preview) keeps the tree live; only New Space locks it.
  const locked = WS.task === "newspace";
  const spaceRows = here ? [{ kind: "settings", id: "settings", label: "Layout or print your space" }, ...items] : items;
  const hasOrdinaryBins = here && items.some(one => one.kind === "bin");
  const rows = (here && !hasOrdinaryBins
    ? [...spaceRows, { kind: "empty", id: "empty", label: "No bins yet. New Bin makes your first one." }]
    : spaceRows).map(one => {
    if (one.kind === "empty") return `<li class="ws-empty">${wsEsc(one.label)}</li>`;
    if (one.kind === "group") return `<li class="ws-group" role="presentation">${wsEsc(one.label)}</li>`;
    const picked = Boolean(now) && now.kind === one.kind && (one.kind === "container" || String(now.id || "") === String(one.id || ""));
    const drawerButtons = one.kind === "settings" ? WS.drawerButtons(locked) : "";
    // Story 2840: the Layout line's one button, Manage, opens the same space details screen as a click on the line.
    const manage = one.kind === "settings"
      ? `<button type="button" class="ws-out" data-ws-pick="settings" data-id="" title="Layout or print your space"${locked ? " disabled" : ""}>Print</button>` : "";

    const level = one.kind === "container" ? 1 : one.kind === "bin" && here && WS.containerKind() ? 2 : 0;
    // Story 2840: Print and Export are rendered only on the selected row; other rows carry no output buttons.
    return `<li class="ws-row ws-level-${level}"><button type="button" class="ws-rowbtn${picked ? " selected" : ""}${one.kind === "container" ? " container" : ""}" data-ws-pick="${one.kind}" data-id="${wsEsc(one.id)}" aria-pressed="${picked}"${one.kind === "bin" && here && !locked ? ' draggable="true"' : ""}${locked ? " disabled" : ""}>
      <span class="ws-label">${wsEsc(one.label)}</span>${one.note ? `<span class="ws-note">${wsEsc(one.note)}</span>` : ""}</button>${drawerButtons}${manage}${picked ? WS.rowOutputs(one, !locked) : ""}${WS.rowBinActions(one, picked, locked)}</li>`;
  }).join("");
  // Story 2725: live on any bin view (a bin in a space or a loose bin in My Bins). Greyed only on the
  // container and Layout views, or while a switch/action is in flight. Not tied to the classic form's
  // button state, which is hidden or disabled in states where the header action still works.
  // Story 2783: Duplicate and Delete live on the selected bin's own row, so the top keeps New Bin only.
  const actions = `${here ? "" : '<button type="button" class="button secondary dl-small" data-ws-act="new-space-choose">New Space</button>'}<button type="button" class="button primary dl-small" data-ws-act="new-bin"${locked ? " disabled" : ""}>New Bin</button>`;
  return `<div class="ws-sel">
    <div class="ws-sel-head"><h2>${wsEsc(here ? WS.placeName() : "My Bins")}</h2><span class="ws-sel-actions">${actions}</span></div>
    <p id="ws-action-note" class="dl-note" role="status"${WS.treeNote ? "" : " hidden"}>${wsEsc(WS.treeNote)}</p>
    ${WS.message ? `<p class="field-error" role="alert">${wsEsc(WS.message)}</p>` : ""}
    <ul class="ws-items" aria-label="${here ? `Contents of ${wsEsc(WS.placeName())}` : "Bins that are not in a Space"}">${rows || '<li class="ws-empty">Nothing here yet. Choose New Bin to add the first bin.</li>'}</ul>
  </div>`;
};

// ------------------------------------------------------------------ left: temporary editors (B)

// Every kind is a full artwork choice, equal in size.
WS.KINDS = [
  ["portable", "Storage Box", "A carrying case for your bins.", "B4B.png"],
  ["storage_drawers", "Storage Drawers", "Drawers to hold your bins", "StorageDrawers.png"],
  ["surface", "Surface", "A countertop, shelf, or vanity.", "Vanity.png"],
  ["drawer", "Drawer", "Organize one of your drawers", "Drawer.png"],
  ["pegboard", "Pegboard", "Create Bins for your pegboard", "Pegboard.png"],
];

WS.renderNewSpace = () => `<div class="ws-page ws-newspace">
    <h2>Create a new space</h2>
    <div class="ws-choices">${WS.KINDS.map(([kind, title, text, img]) => `<button type="button" class="ws-choice" data-ws-act="new-space" data-kind="${kind}" aria-label="${wsEsc(`New Space: ${title} — ${text}`)}">
      <img src="/images/${img}" alt="" width="120" height="90" decoding="async"><strong>${title}</strong><small>${text}</small></button>`).join("")}</div>
    ${WS.task === "picker" ? "" : '<div class="ws-toprow"><button type="button" class="button secondary dl-small" data-ws-act="cancel">Cancel</button></div>'}
  </div>`;

// ------------------------------------------------------------------ top bar

WS.spaceRows = () => {
  const rows = [];
  const here = state.folderMode === "space" && state.activeSpace;
  if (here) {
    rows.push({ src: "current", name: state.activeSpace.name, kind: state.activeSpace.kind, current: true,
      meta: state.activeSpace.kind === "storage_drawers" ? SP.storageDrawersSummaryText(state.activeSpace) : SP.spaceListSize({ ...state.activeSpace, size: [state.activeSpace.x, state.activeSpace.y, state.activeSpace.z] }) });
  }
  const seen = new Set(here ? [String(state.activeSpace.name).toLowerCase()] : []);
  const add = (src, index, one) => {
    const key = String(one.name || "").toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({ src, index, name: one.name, kind: one.kind, invalid: Boolean(one.invalid || one.missing || one.conflict),
      meta: one.invalid ? one.error || "unavailable" : SP.spaceListSize(one) });
  };
  if (state.runtime.hosted) {
    SP.recent.forEach((one, index) => { if (one.folder_mode === "space") add("recent", index, one); });
  } else {
    SP.otherSpaces.forEach((one, index) => add("other", index, one));
    SP.recent.forEach((one, index) => { if (one.folder_mode === "space") add("recent", index, one); });
  }
  return rows;
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
      : focused.dataset.wsOut !== undefined ? `[data-ws-out][data-kind="${focused.dataset.kind}"][data-id="${CSS.escape(focused.dataset.id || "")}"][data-output="${focused.dataset.output}"]`
      : null) : null;
    host.innerHTML = html;
    WS[key] = html;
    host.scrollTop = top;
    if (find) host.querySelector(find)?.focus();
  };
  // Preserve the native drag source until dragend; regroup as soon as the drag finishes.
  if (!WS.draggingRow) draw(stage, WS.renderSelector(), "signature");
  const auxHtml = WS.task === "newspace" || WS.task === "picker" ? WS.renderNewSpace() : "";
  aux.hidden = !auxHtml;
  draw(aux, auxHtml, "auxSignature");
  renderOutputReport();
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

WS.flushBin = async ({ spaceSwitch = false } = {}) => {
  if (["bin", "peek"].includes(WS.task) && WS.open() && typeof flushSpaceDesignAutosave === "function") {
    if (spaceSwitch) return SP.leaveBinForSpaceSwitch();
    return flushSpaceDesignAutosave({ deferDraftPreview: true });
  }
  return true;
};

// Going to or from the space layout can take a moment; a big message in the middle section says so
// at once and stays until the next view is actually ready (or the switch fails).
WS.switchingMessage = task => {
  if (!WS.open()) return "";
  if (task === "settings" && !["settings", "peek"].includes(WS.task)) return "Switching to space layout";
  if ((task === "container" || task === "bin") && ["settings", "peek"].includes(WS.task)) return "Switching to bin view";
  return "";
};

WS.showSwitching = text => {
  const host = $(".workspace");
  if (!host) return;
  let box = $("#ws-switching");
  if (!text) { if (box) box.hidden = true; return; }
  if (!box) {
    box = document.createElement("div");
    box.id = "ws-switching";
    box.className = "ws-switching";
    box.setAttribute("role", "status");
    host.appendChild(box);
    WS.wireSwitchingDrops(box);
  }
  box.textContent = text;
  box.hidden = false;
};

WS.EXPORT_HOLDS_TREE = "Exporting this bin — other rows open once its files are saved.";
WS.exportHoldsTree = () => typeof isGenerating !== "undefined" && isGenerating;

// A bin dragged from the tree and let go over the switching cover is refused
// right there, in words, and stays exactly as it was (unplaced, unchanged).
// Drops are never held or queued for after the switch, and none vanishes
// silently: the cover takes every dragover/drop for as long as it shows.
WS.SWITCHING_DROP_REFUSAL = "The layout is still switching — drop again once it appears.";
WS.wireSwitchingDrops = box => {
  const showing = () => !box.hidden;
  const accept = event => {
    if (!showing()) return;
    event.preventDefault();
    event.stopPropagation();
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  };
  box.addEventListener("dragenter", accept);
  box.addEventListener("dragover", accept);
  box.addEventListener("drop", event => {
    if (!showing()) return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof DV !== "undefined") DV.drop = null;
    toastAt(WS.SWITCHING_DROP_REFUSAL, event.clientX, event.clientY, true, 5000);
  });
};

// Story 2735: switching between items (bin / container / space layout) inside an open Space.
// The clicked row is highlighted at once, the old preview is cleared and "Building geometry"
// shows until the new item's preview is ready.
WS.itemSwitchTarget = (task, arg) => {
  if (!WS.open() || !["bin", "peek", "container", "settings", "none"].includes(WS.task)) return null;
  const target = task === "container" ? { kind: "container", id: "container" }
    : task === "settings" ? { kind: "settings", id: "settings" }
    : ["bin", "peek"].includes(task) && arg ? { kind: "bin", id: arg } : null;
  const now = WS.current();
  return target && !(now && now.kind === target.kind && String(now.id || "") === String(target.id)) ? target : null;
};

WS.beginItemSwitch = () => {
  document.body.classList.add("ws-item-switching");
  const text = $("#preview-wait-text");
  if (text) text.textContent = "Building geometry…";
  const notice = $("#preview-wait");
  if (notice) notice.hidden = false;
  $('[data-canvas="3d"]')?.classList.add("preview-recalculating");
};

WS.endItemSwitch = () => {
  if (!document.body.classList.contains("ws-item-switching")) return;
  document.body.classList.remove("ws-item-switching");
  const text = $("#preview-wait-text");
  if (text) text.textContent = "Updating design…";
  const notice = $("#preview-wait");
  if (notice) notice.hidden = true;
  $('[data-canvas="3d"]')?.classList.remove("preview-recalculating");
};

// A container's preview builds on its own after the view mounts; hold the notice until it lands.
WS.waitStructuralPreview = async token => {
  const building = () => /^(Building|Updating) preview/.test($("#preview-state")?.textContent || "");
  for (let i = 0; i < 300 && token === WS.switchToken && building(); i++) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
};

WS.commitQueuedDelete = async () => {
  if (!WS.queuedDeleteId) return true;
  const one = DL.bin(WS.queuedDeleteId);
  WS.queuedDeleteId = null;
  WS.sync();
  if (!one) {
    toast("Could not delete bin: the bin is no longer available.", true, 6000);
    return false;
  }
  return DP.deleteBinNow(one);
};

WS.go = async (task, arg = null) => {
  if (WS.busy) return false;
  WS.busy = true;
  const sameBin = ["bin", "peek"].includes(task) && arg && String(arg) === String(WS.queuedDeleteId);
  if (WS.queuedDeleteId && !sameBin && !(await WS.commitQueuedDelete())) {
    WS.busy = false;
    WS.sync();
    return false;
  }
  const switching = WS.switchingMessage(task);
  const pending = WS.itemSwitchTarget(task, arg);
  const token = WS.switchToken = (WS.switchToken || 0) + 1;
  if (pending) {
    WS.pending = pending;
    WS.sync(); // highlight the new row now
    if (!switching && pending.kind !== "settings" && task !== "peek") WS.beginItemSwitch();
  }
  if (switching || pending) {
    if (switching) WS.showSwitching(switching);
    await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 0))); // let it paint first
  }
  try { return await WS.transition(task, arg); }
  catch (error) { toast(friendlyError(error), true, 6000); return false; }
  finally {
    WS.busy = false;
    WS.pending = null;
    WS.sync();
    if (pending && token === WS.switchToken && document.body.classList.contains("ws-item-switching")) {
      if (WS.task === "container") await WS.waitStructuralPreview(token);
      if (token === WS.switchToken) WS.endItemSwitch();
    }
    if (switching) {
      // Keep it up until the new view has been drawn.
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      WS.showSwitching("");
    }
  }
};

WS.toSpaceMode = async () => (DP.mode === "space" || await DP.selectMode("space"));

// Remember which editor a temporary one (Print Space, New Space) was opened from.
WS.rememberPrior = () => {
  if (WS.task === "newspace") return;
  WS.prior = { task: WS.task, id: ["bin", "peek"].includes(WS.task) && WS.open() ? state.designInventoryId || "" : "" };
};

WS.transition = async (task, arg) => {
  const from = WS.task;
  if (task === "newspace") {
    if (!(await WS.closeSettings()) || !(await WS.flushBin({ spaceSwitch: true }))) return false;
    SP.close?.();
    WS.rememberPrior();
    WS.task = "newspace";
    SP.refreshOtherSpaces?.().then(() => WS.sync());
    return true;
  }
  if (task === "picker") {
    if (!(await WS.closeSettings()) || !(await WS.flushBin({ spaceSwitch: true }))) return false;
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
  if (task === "peek") {
    if (!arg || (from === "peek" && WS.peekId === arg)) return Boolean(arg);
    const context = DL.spaceContext();
    const previousId = WS.peekId;
    const restore = () => {
      if (DL.spaceContextCurrent(context)) { WS.task = from; WS.peekId = previousId; }
    };
    WS.task = "peek";
    WS.peekId = arg;
    WS.sync(); // highlight now; the ordinary editor installs through its existing save/load owner
    try {
      if (await DP.openInventoryRow(arg, { peek: true })) return true;
    } catch (error) {
      restore();
      throw error;
    }
    restore();
    return false;
  }
  if (task === "settings") {
    if (from === "peek" && !(await WS.flushBin())) return false;
    // Story 2818: the left side swaps to the space details screen at once; the mode switch and
    // the form load below (the heavy part) fill it in. A failed switch puts the old screen back.
    const shown = WS.task;
    WS.task = "settings";
    WS.sync();
    if (!(await WS.toSpaceMode())) { WS.task = shown; WS.sync(); return false; }
    SP.editSpace();
    // Story 2817: the space details screen is the layout row alone; an edited bin's old highlight clears.
    WS.peekId = null;
    DL.selected = null; DL.selectedRow = null; DL.emit();
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
    WS.peekId = null;
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
  WS.peekId = null;
  WS.prior = null;
  if (WS.open()) {
    Object.assign(DV.view, { zoom: 1, panX: 0, panY: 0 });
    // A drawer's space opens in Overhead: flat, fitted, not turned (Story 2750).
    // Other kinds of space keep the view they had.
    if (DL.isStorageDrawers()) DV.setView(DV.PRESETS.overhead);
    WS.task = "landing";
    WS.settle(0);
    WS.warmSpaces();
  } else if (state.folderMode !== "space") {
    WS.task = "bin";
  }
};

// Opening a Space can leave the panel in Design or Space mode; once its own flow has
// finished, put it on the container.
WS.settle = tries => {
  setTimeout(() => {
    if (WS.task !== "landing" || !WS.open()) return;
    if (WS.busy || SP.busy) { if (tries < 60) WS.settle(tries + 1); return; }
    WS.land().then(landed => { if (!landed && WS.landingPending) WS.endOpening(); });
  }, 150);
};

// ------------------------------------------------------------------ actions

// Open a Space from a row. On the open screen nothing is being edited, so leaving the
// restored Space must not wait on an editor prompt; if the switch cannot proceed the
// reason is shown on the screen itself, not only as a toast.
// Opening a Space says so at once, over the middle section, until it is drawn (Story 2719).
// The message is not held across WS.land: SP.run keeps SP.busy set, and settle waits on that.
// Instead it is cleared by WS.sync once the view has left "landing" (see WS.endOpening).
WS.endOpening = () => {
  WS.landingPending = false;
  WS.showSwitching("");
};

WS.pickSpace = (folder, name = "") => SP.run(async () => {
  if (!(await WS.commitQueuedDelete())) return;
  WS.message = "";
  WS.landingPending = false;
  if (name) WS.showSwitching(`Opening ${name}...`);
  let opened = null;
  try {
    opened = await SP.afterPick(folder, WS.task === "picker" ? { visible: false } : undefined);
  } catch (error) {
    WS.endOpening();
    WS.message = `Could not open that Space: ${friendlyError(error)}`;
    WS.sync();
    throw error;
  }
  if (!opened) {
    WS.endOpening();
    WS.message = "That Space could not be opened because the Space that is open could not be saved first. Fix the problem there, then try again.";
    WS.sync();
    return;
  }
  // Adopted but not yet drawn: keep the message until the landing view is shown.
  if (name && WS.open() && WS.task === "landing") WS.landingPending = true;
  else WS.endOpening();
});

WS.openSpaceRow = button => {
  const src = button.dataset.src;
  const index = Number(button.dataset.index);
  if (src === "current") {
    if (!WS.open()) {
      // Launch-restored Space: listed first, but its layout is not loaded until it is truly
      // entered. Enter it through the normal open path; a failure shows on the picker.
      const folder = state.runtime.hosted ? state.browserFolder : state.output;
      const name = state.activeSpace?.name || "";
      if (folder) WS.pickSpace(folder, name);
      else {
        WS.message = "That Space could not be opened because its folder is not available. Choose it again from Open Existing.";
        WS.sync();
      }
      return null;
    }
    DV.fit();
    return WS.land();
  }
  if (src === "other") {
    const one = SP.otherSpaces[index];
    if (one) WS.pickSpace(one.folder, one.name);
    return null;
  }
  const one = SP.recent[index];
  if (one) WS.pickSpace(state.runtime.hosted ? { handle: one.handle, name: one.folder_name || one.name, home_name: one.home_name } : one.folder, one.name);
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
  if (!(await WS.commitQueuedDelete())) return;
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

WS.newBin = async () => {
  if (WS.open()) return WS.go("bin", null);
  if (!(await designerNewBin())) return false;
  return WS.go("bin");
};

// A row click selects the item and shows its form at once.
WS.pick = (kind, id) => {
  if (WS.busy || WS.task === "newspace") return null;
  if (!WS.open()) return WS.go("bin");
  if (kind === "settings") return WS.task === "settings" ? null : WS.go("settings");
  if (kind === "container") return WS.task === "container" ? null : WS.go("container");
  if (!id || (WS.task === "bin" && id === state.designInventoryId)) return null;
  return WS.go("bin", id);
};

WS.openDrawer = async id => {
  if (!DL.isStorageDrawers() || !DL.layout?.drawers.some(row => row.id === id)) return;
  if (SP.editing || SP.structuralBusy || DP.designNavBlocked()) return;
  await WS.pick("settings");
  if (DL.layout.active === id) return;
  const oldId = DL.layout.active;
  const cb = SP.cabinetCallbacks();
  await cb.setActiveDrawer(id);
  cb.clearCanvasPlacementSelection();
  const selectedRow = cb.selectedRow();
  if (selectedRow && window.StorageDrawers.drawerHoldingRow(DL.layout, selectedRow) === oldId) cb.clearSelectedRow();
  cb.reframeCamera();
};

WS.onAction = async (act, button, event) => {
  switch (act) {
    case "open-space": return WS.openSpaceRow(button);
    case "reconnect": return SP.reconnectSavedFolder();
    case "my-bins": return WS.enterLoose();
    case "open-welcome": return WS.go("picker");
    case "open-folder": return SP.run(SP.openExisting);
    case "storage": return SP.changeStorageParent();
    case "new-space-choose": return WS.go("newspace");
    case "new-space": return WS.newSpace(button.dataset.kind);
    case "new-bin": return WS.newBin();
    // Story 2725: call the operations directly (a .click() on a disabled classic button does nothing).
    case "drawer": return WS.openDrawer(button.dataset.id);
    case "edit-bin": return WS.pick("bin", button.dataset.id);
    case "duplicate-bin": { const one = DL.bin(button.dataset.id); return one ? DP.duplicateRow(one) : null; }
    case "delete-bin": {
      const one = DL.bin(button.dataset.id);
      if (!one) return null;
      WS.queuedDeleteId = String(WS.queuedDeleteId) === String(one.id) ? null : one.id;
      WS.sync();
      return true;
    }
    case "cancel": return WS.resume();
    default: return null;
  }
};

// ------------------------------------------------------------------ row buttons: Print / Export

// Story 2721: Print and Export live at the right end of every selector row. Only the row being
// edited has live buttons; the others stay disabled but still read by printed state.
// Printed state: a bin row is green when its stored status is Printed (any edit resets it); the
// container and the loose bin remember the design signature last printed, green while it still
// matches; Layout is green when everything printable in the space is printed and current.
WS.PRINTED_KEY = "wavefinity.printedSignatures";
WS.printedSigs = (() => {
  try { return JSON.parse(localStorage.getItem(WS.PRINTED_KEY) || "{}") || {}; } catch { return {}; }
})();
WS.sigKey = kind => (kind === "container" ? `container:${state.activeSpaceId || state.activeSpace?.name || ""}` : "loose");
WS.currentSig = kind => {
  try { return JSON.stringify(kind === "container" ? state.activeSpace : state.design); } catch { return ""; }
};
WS.markPrinted = kind => {
  const sig = WS.currentSig(kind);
  if (!sig) return;
  WS.printedSigs[WS.sigKey(kind)] = sig;
  try { localStorage.setItem(WS.PRINTED_KEY, JSON.stringify(WS.printedSigs)); } catch { /* storage unavailable: stays in memory */ }
  WS.sync();
};
WS.markContainerPrinted = () => { if (WS.open() && WS.containerKind()) WS.markPrinted("container"); };
WS.markLooseBinPrinted = () => { if (!WS.open() && state.folderMode !== "space") WS.markPrinted("loose"); };

WS.isPrinted = one => {
  if (one.kind === "container") return WS.printedSigs[WS.sigKey("container")] === WS.currentSig("container");
  if (one.kind === "settings") {
    const bins = (DL.bins || []).filter(bin => DL.isOrdinary(bin) && DL.printEligible(bin));
    const parts = bins.length + (WS.containerKind() ? 1 : 0);
    return parts > 0 && bins.every(bin => bin.status === "printed")
      && (!WS.containerKind() || WS.isPrinted({ kind: "container" }));
  }
  if (!WS.open()) return WS.printedSigs[WS.sigKey("loose")] === WS.currentSig("loose");
  return DL.bin(one.id)?.status === "printed";
};

// Is this row's Print / Export live? Only the row being edited, and only when its action can run.
WS.rowLive = one => {
  if (WS.busy) return false;
  if (one.kind === "settings") return WS.task === "settings";
  if (one.kind === "container") return WS.task === "container" && WS.containerReady();
  return ["bin", "peek"].includes(WS.task) && WS.binReady();
};

WS.rowOutputs = (one, picked) => {
  const live = picked && WS.rowLive(one);
  const tone = WS.isPrinted(one) ? "printed" : "unprinted";
  const what = one.kind === "settings" ? "the space" : one.kind === "container" ? (WS.containerName().toLowerCase() || "container") : "bin";
  const hosted = Boolean(state.runtime.hosted);
  const printTitle = !live ? "Select this row to print it."
    : one.kind === "settings" ? "Choose which bins to print"
    : one.kind === "container" ? "Prepare a local 3MF to open in Bambu Studio"
    : hosted ? "Printing needs local Wavefinity and a slicer"
    : !state.slicer?.available ? "A slicer is needed - use Printer Settings to choose one"
    : `Send the ${what} to ${state.slicer.name || "the slicer"}`;
  const exportTitle = !live ? "Select this row to export it."
    : `Create the 3MF file for the ${what}`;
  const attrs = `data-ws-out data-kind="${one.kind}" data-id="${wsEsc(one.id)}"`;
  const running = currentOutputReport?.busy && DL.spaceContextCurrent(currentOutputReport.context)
    && (one.kind === "container" ? currentOutputReport.owner === "container"
      : one.kind === "bin" && (currentOutputReport.rowIds.includes(one.id)
        || currentOutputReport.owner === "bin" && one.id === (state.designInventoryId || "")));
  const label = mode => running && currentOutputReport.action === mode ? wsEsc(currentOutputReport.short ?? currentOutputReport.text)
    : one.kind === "bin" && hosted ? "Save file" : mode === "print" ? "Print" : "Export";
  // Story 2815: the space line has no Print button; clicking the line opens the space details screen.
  // Story 2829: the space line has no Export button either; the details screen exports the space's files.
  if (one.kind === "settings") return "";
  const binHostedSave = one.kind === "bin" && hosted;
  const printButton = `<button type="button" class="ws-out ${tone}" ${attrs} data-output="${binHostedSave ? "export" : "print"}"${live && !running ? "" : " disabled"} title="${wsEsc(binHostedSave ? "Save this bin's file" : printTitle)}">${label(binHostedSave ? "export" : "print")}</button>`;
  return printButton + (one.kind === "container" ? `<button type="button" class="ws-out ${tone}" ${attrs} data-output="export"${live && !running ? "" : " disabled"} title="${wsEsc(exportTitle)}">${label("export")}</button>` : "");
};

// Story 2807: Duplicate and Delete sit on the selected bin's own row (and no other row). They are the same
// operations as the Inventory row's (Stories 2782 / 2783), confirmation included.
WS.rowBinActions = (one, selected, locked) => {
  if (one.kind !== "bin" || !selected || !WS.open() || !one.id) return "";
  const bin = DL.bin(one.id);
  if (!bin || !DL.isOrdinary(bin)) return "";
  const off = locked || WS.busy || DP.designNavBlocked() ? " disabled" : "";
  const attrs = `data-ws-act="%A" data-id="${wsEsc(one.id)}"${off}`;
  const duplicate = ["bin", "b4b"].includes(bin.kind) && Boolean(DL.layout?.design_specs?.[bin.id])
    ? `<button type="button" class="ws-out" ${attrs.replace("%A", "duplicate-bin")} title="Duplicate this bin">Duplicate</button>` : "";
  const queued = String(WS.queuedDeleteId) === String(one.id);
  return `${duplicate}<button type="button" class="ws-out" ${attrs.replace("%A", "delete-bin")} title="${queued ? "Cancel queued deletion" : "Delete this bin"}">${queued ? "Will delete when another row is selected (cancel)" : "Delete"}</button>`;
};

// Layout: every printable bin's file, and the container's, brought up to date.
WS.exportAll = async () => {
  const ids = (DL.bins || []).filter(one => DL.isOrdinary(one) && DL.printEligible(one)).map(one => one.id);
  if (ids.length) await DL.saveSelectedBins(ids, true);
  if (WS.containerKind()) {
    if (WS.containerKind() === "storage_drawers") await SP.runStructural("save");
    else await SP.saveStructural();
  }
};

WS.output = (kind, mode, button, event) => {
  if (!WS.rowLive({ kind })) return null;
  if (kind === "settings") return WS.go("settings");
  if (kind === "container") {
    const drawers = WS.containerKind() === "storage_drawers";
    if (mode === "print") return drawers ? SP.runStructural("print", event) : SP.printStructural(event);
    return drawers ? SP.runStructural("save") : SP.saveStructural();
  }
  return chooseIndividualBinPrint(button);
};

// The container print: lit whenever the open space has a container.
WS.containerReady = () => !WS.busy && WS.open() && Boolean(WS.containerKind()) && !SP.structuralBusy
  && ["bin", "peek", "container", "settings"].includes(WS.task);

// Print Bin: only an actual selected bin (never the container or the space layout).
WS.binReady = () => {
  if (WS.busy || !["bin", "peek"].includes(WS.task)) return false;
  const bin = WS.open() ? Boolean(state.designInventoryId) : state.folderMode !== "space";
  return bin && !state.designMutationBusy && state.canGenerate;
};

// Callers that report a change in output availability land here; the row buttons are redrawn
// with the selector by WS.sync().
WS.syncOutput = () => { if (WS.entered) WS.render(); };

// ------------------------------------------------------------------ sync

// Story 2720: once the space list is showing, ask the server (once) to quietly pre-build the
// listed spaces' previews so the first click is fast. Fire-and-forget: it opens, selects and
// changes nothing, and a failure is ignored.
// Also asked once per opened Space, so its layout and bins are pre-built
// before the first switch to them (the server skips anything already warm).
WS.warmedFor = null;
WS.warmSpaces = () => {
  if (state.runtime.hosted) return;
  const key = WS.task === "picker" ? "picker" : WS.placeKey();
  if (WS.warmedFor === key) return;
  WS.warmedFor = key;
  setTimeout(() => { api("/api/space/warm", {}).catch(() => {}); }, 1500);
};

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
  // The opening message ends once the Space's view has been drawn (or the open did not land).
  if (WS.landingPending && (WS.task !== "landing" || !WS.open())) WS.endOpening();
  // A task that needs an open Space falls back when that Space is gone.
  if (["landing", "container", "peek", "settings"].includes(WS.task) && !WS.open() && state.folderMode !== "space") {
    WS.task = "bin";
  }
  // Keep the Inventory and placement selection aligned with the tree's current row.
  if (WS.open() && DL.layout) {
    const current = WS.current();
    const rowId = current?.kind === "bin" && current.id ? current.id : null;
    if (DL.selectedRow !== rowId) DL.selectRow(rowId);
  }
  // Story 2704: on the open screen nothing is chosen yet - no preview, nothing current, and the
  // space-dependent actions stay off, though the restored session is kept for picking from the list.
  const open = WS.open() && !["picker", "none"].includes(WS.task);
  if (WS.task === "picker") WS.warmSpaces();
  body.classList.add("ws-on");
  body.classList.toggle("ws-open", open);
  for (const name of WS_TASKS) body.classList.toggle(`ws-task-${name}`, WS.task === name);
  DP.syncEditorVisibility();
  if (DP.built && ["settings", "none"].includes(WS.task)) DP.renderBatch();
  if (WS.task !== WS.entered) {
    WS.entered = WS.task;
    if (["bin", "peek", "container", "settings"].includes(WS.task)) WS.editorToTop();
  }
  const switcher = $("#ws-spaces");
  if (switcher) switcher.disabled = WS.task === "picker";
  const place = $("#ws-place");
  if (place) place.textContent = "All Spaces";
  if (open || (WS.task === "none" && WS.open())) {
    const view = WS.task === "bin" || WS.task === "container" ? "3d" : "drawer";
    const wrap = $(`.canvas-wrap[data-canvas="${view}"]`);
    if (wrap && !wrap.classList.contains("active")) wsActivatePreview(view);
  }
  WS.render();
  SP.renderBinRecovery();
  WS.measure();
  const signature = `${WS.task}|${[...DP.printSelected].join(",")}|${DP.containerPinned}|${state.designInventoryId || ""}|${WS.peekId || ""}|${WS.prior?.id ?? ""}`;
  if (signature !== WS.previewSignature) {
    WS.previewSignature = signature;
    if (open && typeof DV !== "undefined") DV.paint();
  }
};

// An editor opens at its heading and first field, whatever the sidebar was scrolled to before
// (or a field focused while it filled in scrolled it partway down).
WS.editorToTop = () => {
  const reset = () => {
    if (!["bin", "peek", "container", "settings"].includes(WS.task)) return;
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
  const printing = WS.task === "settings";
  const marked = printing ? DP.printSelected
    : WS.task === "peek" && WS.peekId ? new Set([WS.peekId])
    : WS.task === "bin" && state.designInventoryId ? new Set([state.designInventoryId]) : new Set();
  const containerMarked = printing ? DP.containerPinned : WS.task === "container";
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

// A layout click peeks at the ordinary editor while the layout stays live.
DP.onLayoutClick = key => {
  if (!WS.open() || WS.task === "newspace") return false;
  const found = DL.findPlacement(key);
  const one = found && DL.bin(found.placement.bin);
  if (!one || !DL.isOrdinary(one)) return false;
  WS.go("peek", one.id);
  DV.revealRow(one.id);
  return true;
};
DP.layoutViewOnly = () => WS.open() && !["settings", "peek", "none"].includes(WS.task);

// The welcome / type-card dialogs become the bar and the New Space kinds; a restored
// session opens its last Space (container selected) straight away - nothing covers it.
SP.showHome = (message = null) => {
  SP.close();
  WS.message = message || "";
  if (WS.open()) WS.resume();
  else if (state.runtime.hosted && !SP.canPersistSpace()) WS.task = "picker";
  else WS.enterLoose();
  WS.sync();
  return null;
};
SP.showTypeCards = () => {
  SP.close();
  WS.go("newspace");
  return null;
};
SP.showResume = (info, { startup = false } = {}) => {
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

  const delegate = event => {
    if (WS.draggingRow || Date.now() < (WS.suppressRowClickUntil || 0)) return;
    // The tree stays live during an Export (it scrolls and highlights), but
    // opening another row, or a row action, waits for the files: switching the
    // bin mid-Export would leave its saved files unrecorded. Said in place.
    if (WS.exportHoldsTree() && event.target.closest("[data-ws-out], [data-ws-pick], [data-ws-act]")) {
      event.preventDefault();
      toastAt(WS.EXPORT_HOLDS_TREE, event.clientX, event.clientY, false, 4000);
      return;
    }
    const out = event.target.closest("[data-ws-out]");
    if (out) { if (!out.disabled) WS.output(out.dataset.kind, out.dataset.output, out, event); return; }
    const pick = event.target.closest("[data-ws-pick]");
    if (pick) { WS.pick(pick.dataset.wsPick, pick.dataset.id || ""); return; }
    const button = event.target.closest("[data-ws-act]");
    if (button && !button.disabled) WS.onAction(button.dataset.wsAct, button, event);
  };
  [stage, aux].forEach(host => host.addEventListener("click", delegate));
  stage.addEventListener("dragstart", event => {
    if (WS.exportHoldsTree()) {
      event.preventDefault();
      toastAt(WS.EXPORT_HOLDS_TREE, event.clientX, event.clientY, false, 4000);
      return;
    }
    const row = event.target.closest('[data-ws-pick="bin"][draggable="true"]');
    const one = row && DL.bin(row.dataset.id);
    if (!one || WS.busy || WS.task === "newspace") { event.preventDefault(); return; }
    WS.draggingRow = true;
    DV.dragBin = one;
    event.dataTransfer.setData("text/plain", one.id);
    event.dataTransfer.effectAllowed = "move";
  });
  stage.addEventListener("dragend", () => {
    DV.dragBin = null; DV.drop = null;
    WS.draggingRow = false;
    WS.suppressRowClickUntil = Date.now() + 400;
    WS.sync();
    DV.render();
  });
  // Story 2716: Manage Spaces is a plain button that opens the space management (picker) screen.
  $("#ws-spaces").addEventListener("click", () => WS.go("picker"));
  $("#part-name")?.addEventListener("input", () => WS.sync());

  // Every owner that changes what is open reports through one of these.
  // The pre-unified bin selector's refresh used to carry this hook; the delete-row refresh (always paired
  // with it) and the Design-mode inventory render now report the same changes.
  for (const name of ["applyMode", "setMode", "setDesignTarget", "clearDesignTarget", "refreshDesignerDeleteBin"]) {
    const original = DP[name];
    DP[name] = (...args) => {
      const result = original(...args);
      WS.sync();
      return result;
    };
  }
  const renderInventory = DP.renderInventory;
  DP.renderInventory = (...args) => {
    const result = renderInventory(...args);
    if (DP.mode === "design") WS.sync();
    return result;
  };
  DL.on(WS.sync);
  if (window.ResizeObserver) {
    const observer = new ResizeObserver(() => { WS.measure(); if (typeof DV !== "undefined") DV.render(); });
    observer.observe($(".workspace"));
    observer.observe($("#ws-frame"));
  }
  WS.sync();
})();
