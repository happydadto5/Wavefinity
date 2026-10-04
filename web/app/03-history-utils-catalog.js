"use strict";

// New Bin (B1): a fresh product-appropriate starter. Meaningful current work
// in a typed Space is preserved through the autosave flush first, never silently
// discarded; on flush failure New Bin is cancelled rather than losing work.
async function designerNewBin(acceptTransition = null) {
  if (acceptTransition && !acceptTransition()) return false;
  // Fix 103 (R6): structural -> New Bin settles an unsaved structural draft first.
  if (typeof designTargetIsStructural === "function" && designTargetIsStructural() && !(await SP.confirmLeaveStructuralEditor())) return false;
  if (acceptTransition && !acceptTransition()) return false;
  return withDeferredDraftSwitch(async () => {
  if (acceptTransition && !acceptTransition()) return false;
  if (state.folderMode === "space") {
    if (typedSpaceOrdinaryBin() &&
        !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) {
      const discard = await appConfirmAction({
        title: "Discard Invalid Changes?",
        message: "This bin has invalid changes that cannot be saved. Discard those changes and start a new bin?",
        actionLabel: "Discard & Start New Bin",
        cancelLabel: "Keep Editing",
        danger: true,
      });
      if (!discard) return false;
    }
    if (acceptTransition && !acceptTransition()) return false;
  } else if (designHasChanges() && !(await appConfirmAction({
    title: "Start a new bin?",
    message: "Start a new bin and discard the current changes?",
    actionLabel: "Discard Changes",
    danger: true,
  }))) return false;
  if (acceptTransition && !acceptTransition()) return false;
  if (!beginDesignMutation()) return false;
  if (acceptTransition && !acceptTransition()) { finishDesignMutation(); return false; }
  try {
    state.designInventoryId = null;
    state.surfaceHeightPromptSkipped = false;
    if (!acceptTransition && typeof DP !== "undefined" && state.folderMode === "space") DP.setMode("design");
    await loadFreshOrdinaryDesignForCurrentFolder();
    toast("Started a new bin.");
    return true;
  } finally {
    finishDesignMutation();
  }
  }, false);
}

// Fix 064: the largest whole base-unit X/Y footprint that fits inside a
// Storage Box's usable interior (rounding down, since the bin must fit),
// plus the full legal usable Z. Z is validated against `candidateDesign` -
// the fresh inside-bin starter that will actually be installed - not
// whatever bin happens to be open, since its remembered Base thickness can
// differ (Fix 064 Correction 1). Returns { x, y, z } or { error }; never
// throws, so the caller can show an actionable message and leave the
// current design untouched.
function insideBinFitForStorageBox(space, candidateDesign) {
  const unit = state.catalog.base_unit;
  const maxUnits = Math.floor((state.catalog.max_box_size || 350) / unit);
  const xUnits = Math.min(maxUnits, Math.floor(space.x / unit));
  const yUnits = Math.min(maxUnits, Math.floor(space.y / unit));
  if (xUnits < 1 || yUnits < 1) {
    return { error: "This Storage Box's inside is too small to fit a bin." };
  }
  const z = normalizeBinDimension("z", space.z, space.z, candidateDesign);
  if (z > space.z) {
    return { error: "This Storage Box is too short to fit a legal bin." };
  }
  return { x: xUnits * unit, y: yUnits * unit, z };
}

// Make Inside Bin (Fix 064): a Storage-Box-only Space Action. Starts a fresh
// ordinary bin, exactly like New Bin (same safety/reset primitives, same
// remembered reusable Space preferences, no clone of the current bin's
// name/text/features), but with X/Y/Z forced to fit the Storage Box's usable
// interior instead of the normal New Bin starter size. The fit is validated
// against the fresh starter itself (Fix 064 Correction 1) - there is no
// await between building it and installing it, so it stays the same
// candidate the user sees land.
async function designerMakeInsideBin() {
  return withDeferredDraftSwitch(async () => {
  // A Storage Box Space owns a structural case editor: settle an unsaved
  // structural draft through the one leave owner before this subject switch,
  // or the switch silently discards the case edits.
  if (typeof designTargetIsStructural === "function" && designTargetIsStructural() &&
      !(await SP.confirmLeaveStructuralEditor())) return;
  if (!(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
  const candidate = freshDesignForCurrentFolder();
  const fit = insideBinFitForStorageBox(state.activeSpace, candidate);
  if (fit.error) {
    toast(fit.error, true, 6000);
    return;
  }
  if (!beginDesignMutation()) return;
  try {
    state.designInventoryId = null;
    state.surfaceHeightPromptSkipped = false;
    await loadFreshOrdinaryDesignForCurrentFolder({ x: fit.x, y: fit.y, z: fit.z });
    // Make Inside Bin is a Design action: land on the created bin in Design
    // instead of leaving the user in Space.
    if (typeof DP !== "undefined") DP.setMode("design");
    toast("Started an inside bin.");
  } finally {
    finishDesignMutation();
  }
  });
}

// Duplicate (B2): a deep copy of the exact current design with name/label
// text cleared and source-row identity cleared, so a later Save/Generate/
// Print creates a distinct source rather than mutating the original's row.
async function designerDuplicate() {
  return withDeferredDraftSwitch(async () => {
  if (typedSpaceOrdinaryBin()) {
    if (!(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
    if (!state.designInventoryId) {
      toast("Edit this bin before duplicating it.", true);
      return;
    }
    const context = DL.spaceContext();
    try {
      const data = await DL.inventoryCall("/api/drawer/design-source/duplicate", {
        row_id: state.designInventoryId,
      }, { context, sideEffect: true });
      DL.adopt(data);
      DL.emit();
      await installLoadedDesignSource(data.row_id, data.design, { successMessage: "Duplicated bin." });
    } catch (error) {
      toast(`Could not duplicate bin: ${error.message}`, true, 6000);
    }
    return;
  }
  const design = clone(visibleDesignSnapshot());
  if (design.layout) design.layout.object_height_mm = null;
  design.part_name = "";
  design.label = "";
  if (design.box?.edge_mount) design.box.edge_mount.label_text = "";
  if (design.box?.lid) {
    design.box.lid.label_text = "";
    design.box.lid.division_labels = (design.box.lid.division_labels || []).map(() => "");
  }
  if (design.box?.b4b) design.box.b4b.label_text = "";
  if (Array.isArray(design.layout?.features)) {
    design.layout.features = design.layout.features.map(feature => {
      if (feature.kind !== "divider" || !Array.isArray(feature.options?.division_labels)) return feature;
      return {
        ...feature,
        options: { ...feature.options, division_labels: feature.options.division_labels.map(() => "") },
      };
    });
  }
  if (!beginDesignMutation()) return;
  try {
    const result = await api("/api/design/validate", { design });
    state.design = result.design;
    // A duplicate is a new design identity: the old design's undo/redo
    // history must not cross the identity boundary.
    clearDesignerHistory();
    state.lastOrdinaryDesign = clone(state.design);
    state.cleanDesign = clone(state.design);
    state.designInventoryId = null;
    state.designTarget = null; // Fix 103
    state.surfaceHeightPromptSkipped = false;
    state.drafts = {};
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    if (typeof DP !== "undefined" && state.folderMode === "space") DP.setMode("design");
    activatePreviewView("3d");
    await refreshPreview();
    toast("Duplicated. Edit the copy freely - the original is unchanged.");
  } catch (error) {
    toast(error.message, true, 6000);
  } finally {
    finishDesignMutation();
  }
  });
}

function pinDraftAxis(axis) {
  state.pinnedZone[axis] = true;
}

function designerHistorySnapshot(design = state.design) {
  return {
    design: clone(design),
    selected: Number.isInteger(state.selected) ? state.selected : null,
    draftSourceIndex: Number.isInteger(state.draftSourceIndex) ? state.draftSourceIndex : null,
    modifierEditing: state.modifierEditing || null,
    lastDesignView: state.lastDesignView,
  };
}

function clearDesignerHistory() {
  state.designerHistory = [];
  state.designerFuture = [];
  updateDesignerHistoryButtons();
}

function updateDesignerHistoryButtons() {
  const undo = $("#designer-undo");
  const redo = $("#designer-redo");
  if (undo) undo.disabled = state.designerHistoryRestoring || !state.designerHistory.length;
  if (redo) redo.disabled = state.designerHistoryRestoring || !state.designerFuture.length;
}

function noteCommittedDesignChange(before = null) {
  if (!before || JSON.stringify(before) === JSON.stringify(state.design)) return false;
  if (!state.designerHistoryRestoring) {
    state.designerHistory.push(designerHistorySnapshot(before));
    if (state.designerHistory.length > 100) state.designerHistory.shift();
    state.designerFuture = [];
    updateDesignerHistoryButtons();
  }
  state.spaceStarterPreviewPending = false;
  return true;
}

async function restoreDesignerHistory(redo = false) {
  if (state.designerHistoryRestoring || state.designMutationBusy) return;
  if (typeof DP !== "undefined" && DP.spaceEditing?.()) return;
  const from = redo ? state.designerFuture : state.designerHistory;
  const to = redo ? state.designerHistory : state.designerFuture;
  if (!from.length) return;

  const target = from.pop();
  to.push(designerHistorySnapshot());
  state.designerHistoryRestoring = true;
  updateDesignerHistoryButtons();
  cancelChangedDesignDebounce();
  pendingDesignHistory = null;
  cancelPendingDraftWork();
  invalidatePendingPreview();

  try {
    state.design = clone(target.design);
    state.lastOrdinaryDesign = clone(state.design);
    state.selected = null;
    state.draft = null;
    state.draftKind = null;
    state.draftSourceIndex = null;
    state.draftIsNew = false;
    state.draftTouched = false;
    state.draftAutoCommit = false;
    state.modifierEditing = null;
    state.edgeMountEditing = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection(false);

    if (target.modifierEditing && modifierIsActive(target.modifierEditing)) {
      await openModifier(target.modifierEditing, true);
    } else {
      const index = Number.isInteger(target.draftSourceIndex)
        ? target.draftSourceIndex
        : target.selected;
      if (Number.isInteger(index) && state.design.layout.features[index]) {
        state.selected = index;
        state.draftSourceIndex = index;
        state.draftKind = state.design.layout.features[index].kind;
        state.draft = clone(state.design.layout.features[index]);
        state.draftAutoCommit = true;
        state.draftIsNew = false;
        state.draftTouched = false;
        renderDraftFields();
      }
    }

    state.canGenerate = false;
    updateGenerateAvailability();
    renderPlaced();
    updateSelectionButtons();
    activatePreviewView(target.lastDesignView === "2d" ? "2d" : "3d");
    await refreshPreview();

    if (typedSpaceOrdinaryBin()) {
      // Undo/redo persists through the same current Space context as
      // ordinary design edits. (state.cleanDesign is a design object, not a
      // space context: passing it as expectedContext failed
      // DL.spaceContextCurrent, so every undo/redo rolled back with a bogus
      // stale-space error.)
      await persistSpaceDesignSource(null, false);
      await settleStaleFileRefresh();
    }
  } catch (error) {
    const rollback = to.pop();
    if (rollback?.design) state.design = clone(rollback.design);
    from.push(target);
    syncForm();
    renderPlaced();
    updateSelectionButtons();
    toast(`Could not ${redo ? "redo" : "undo"} that Designer change: ${error.message}`, true, 7000);
  } finally {
    state.designerHistoryRestoring = false;
    updateDesignerHistoryButtons();
  }
}

const designerUndo = () => restoreDesignerHistory(false);
const designerRedo = () => restoreDesignerHistory(true);

function updateGenerateAvailability() {
  const binButton = $("#generate-bin");
  if (binButton) {
    binButton.disabled = state.designMutationBusy || !state.canGenerate;
    binButton.title = state.canGenerate ? "Save the current bin files" : "Resolve the highlighted issue before saving";
  }
  const allButton = $("#generate-all");
  if (allButton) {
    allButton.disabled = state.designMutationBusy || !state.canGenerate;
    allButton.title = state.canGenerate ? "Save bin and connector files" : "Resolve the highlighted issue before saving";
  }
  const connectorButton = $("#generate-connector");
  if (connectorButton) {
    connectorButton.disabled = state.designMutationBusy;
  }
  syncConnectorActionLabels();
  updatePrimaryPrintButtonLabel();
  for (const printButton of [$("#print-with-connectors"), $("#print-without-connectors")]) {
    if (!printButton) continue;
    printButton.disabled = state.designMutationBusy || !state.canGenerate;
    if (!state.canGenerate) printButton.title = "Resolve the highlighted issue before printing";
  }
}

function number(value, fallback = 0) {
  if (typeof value === "number") return Number.isFinite(value) ? value : fallback;
  const parsed = Number(value);
  if (Number.isFinite(parsed)) return parsed;
  const match = String(value ?? "").match(/^\s*([+-]?\d+(?:\.\d+)?)/);
  if (match) {
    const num = Number(match[1]);
    if (Number.isFinite(num)) return num;
  }
  return fallback;
}

function fmt(value) {
  const rounded = Math.round(number(value) * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function debounce(fn, delay) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
  wrapped.cancel = () => {
    clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

// Fix 096 F7: one place where raw technical failures become plain language.
// Every error shown to the user passes through here. Messages the backend
// itself wrote (data.error) pass through untouched.
function friendlyError(error) {
  let text = "";
  if (typeof error === "string") {
    text = error.trim();
  } else if (error && typeof error === "object") {
    if (typeof error.message === "string") text = error.message.trim();
    else if (typeof error.error === "string") text = error.error.trim();
  }
  if (!text) return "Wavefinity hit a problem. Try again.";
  if (/Failed to fetch/i.test(text)) {
    return "Wavefinity's local service isn't responding. Start (or restart) local Wavefinity and try again.";
  }
  if (/The local Wavefinity service returned \d+/i.test(text)) {
    return "Wavefinity's local service had a problem. Try again.";
  }
  if (/^\[object Object\]$/i.test(text)) {
    return "Wavefinity hit a problem. Try again.";
  }
  return text;
}

async function api(path, payload = null, { timeoutMs = 60000, onStillFinishing = null } = {}) {
  // Every backend call is bounded: a stalled request must surface as an
  // error, never wedge the UI forever (e.g. the drawers configure form's
  // live validation, which blocks Create while its summary is pending).
  const controller = new AbortController();
  const abortTimer = setTimeout(() => controller.abort(), timeoutMs);
  const options = payload === null ? { signal: controller.signal } : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal: controller.signal,
  };
  try {
    const response = await fetch(path, options);
    let data;
    try {
      data = await response.json();
    } catch (_error) {
      throw new Error(`The local Wavefinity service returned ${response.status}.`);
    }
    if (!response.ok) {
      const error = new Error(data.error || `Request failed (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return data;
  } catch (error) {
    if (error?.name === "AbortError") {
      // (Fix 096 A5) The abort only cancels this wait: a side-effecting
      // request may still be running on the server. When the call carries an
      // operation_id, never show the generic "try again" (the first request
      // may still finish) - the UI switches to "Still finishing…" and the
      // first request's result is polled instead.
      const operationId = payload && typeof payload === "object" ? payload.operation_id : null;
      // (Fix 096 A5) Status polls carry __noPoll, so a timed-out status check
      // throws the ordinary timeout error instead of re-entering the poll loop.
      const noPoll = Boolean(payload && typeof payload === "object" && payload.__noPoll);
      if (typeof operationId === "string" && operationId && !noPoll) {
        try {
          (typeof onStillFinishing === "function" ? onStillFinishing : defaultStillFinishing)();
        } catch (_ignored) { /* the poll below still runs */ }
        return pollOperationResult(operationId);
      }
      throw new Error("The request took too long. Please try again.");
    }
    throw error;
  } finally {
    clearTimeout(abortTimer);
  }
}

// (Fix 096 A5) Default "still finishing" UI for side-effecting calls that do
// not supply their own hook.
function defaultStillFinishing() {
  toast("Still finishing…", false, 8000);
}

// (Fix 096 A5) Poll the read-only /api/operation-status endpoint until the
// named operation is terminal, then return its result or throw its stored
// error. The overall wait is capped so the UI can never wedge if the server
// goes away mid-operation.
async function pollOperationResult(operationId) {
  const deadline = Date.now() + 10 * 60 * 1000;
  for (;;) {
    let status;
    try {
      status = await api("/api/operation-status", { operation_id: operationId, __noPoll: true }, { timeoutMs: 30000 });
    } catch (error) {
      // The status check itself failed: the operation may still be running,
      // so mark it non-terminal - a retry must reuse this id.
      error.operationStillRunning = true;
      throw error;
    }
    if (status.operation_status === "done") return status.result;
    if (status.operation_status === "error") throw new Error(status.error || "The earlier request failed.");
    if (status.operation_status === "unknown") {
      // The server has no record of this operation id: the first request may
      // have completed and been pruned from the registry, or it may never
      // have run. The outcome is INDETERMINATE - never "safe to try again".
      // Pin the id as indeterminate so apiSideEffect() refuses a silent
      // retry; the user must first establish whether the change landed (for
      // example, reopen or refresh the Space and check), and only an explicit
      // apiSideEffectStartOver() - separately confirmed in the UI as
      // potentially duplicating the side effect - may clear it.
      indeterminateOperationIds.add(operationId);
      const error = new Error("The earlier request's outcome could not be established. Please check whether the change landed (for example, reopen or refresh the Space) before trying again - trying again now could apply the change twice.");
      error.operationUnknown = true;
      throw error;
    }
    if (Date.now() > deadline) {
      // The operation may still be running: keep the id so a retry reuses it
      // instead of minting a new one (which the server would execute again).
      const error = new Error("The request is still finishing on the server. Please wait a little longer and try again.");
      error.operationStillRunning = true;
      throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 2000));
  }
}

// (Fix 096 A5) In-flight operation ids, keyed by a stable fingerprint of the
// logical action (route + payload, minus any operation_id). A retry of the
// same action reuses the first request's id until it is terminal, so the
// server can never execute the same logical operation twice for one user
// action. Entries are forgotten once the operation settles terminally. An
// "unknown" registry result is indeterminate - the first request may already
// have completed - so the id is never forgotten silently: it is pinned in
// indeterminateOperationIds, and apiSideEffect() refuses any further silent
// attempt for that id until the user explicitly confirms a fresh start.
const inFlightOperationIds = new Map();
const indeterminateOperationIds = new Set();

function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return "[" + value.map(stableStringify).join(",") + "]";
  return "{" + Object.keys(value).sort()
    .map(key => JSON.stringify(key) + ":" + stableStringify(value[key]))
    .join(",") + "}";
}

function operationFingerprint(path, payload) {
  const body = { ...(payload || {}) };
  delete body.operation_id;
  return path + "\n" + stableStringify(body);
}

function mintOperationId() {
  return (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function")
    ? crypto.randomUUID()
    : `op-${Date.now()}-${Math.floor(Math.random() * 1000000000)}`;
}

// (Fix 096 A5) Side-effecting requests go through here. Each logical action
// gets one operation_id, remembered in inFlightOperationIds and reused by any
// retry until the operation is terminal (pass operationId to pin an explicit
// id instead, which bypasses the map); the server registry guarantees the
// operation never executes twice for the same id. If the browser's wait times
// out, the UI switches to "Still finishing…" via onStillFinishing and the
// first request's result is polled instead of inviting a duplicate. If the
// outcome becomes indeterminate (server reports "unknown"), the id stays
// pinned and any further silent attempt for it is refused - the user must
// first establish whether the first request completed, and only an explicit
// apiSideEffectStartOver() (separately confirmed in the UI as potentially
// duplicating) may proceed.
async function apiSideEffect(path, payload, { timeoutMs = 60000, operationId = null, onStillFinishing = null } = {}) {
  const fingerprint = operationId ? null : operationFingerprint(path, payload);
  let id = operationId || inFlightOperationIds.get(fingerprint);
  if (!id) {
    id = mintOperationId();
    if (fingerprint) inFlightOperationIds.set(fingerprint, id);
  }
  if (indeterminateOperationIds.has(id)) {
    // A previous attempt's outcome is indeterminate: refuse a silent retry.
    // The user must establish whether the first request completed (for
    // example, reopen or refresh the Space and check whether the change
    // landed); only apiSideEffectStartOver() may proceed from here.
    const error = new Error("The earlier request's outcome could not be established. Please check whether the change landed (for example, reopen or refresh the Space) before trying again - trying again now could apply the change twice.");
    error.operationUnknown = true;
    throw error;
  }
  const forget = () => { if (fingerprint) inFlightOperationIds.delete(fingerprint); };
  let data;
  try {
    data = await api(path, { ...(payload || {}), operation_id: id }, { timeoutMs, onStillFinishing });
  } catch (error) {
    // Still running or indeterminate server-side: keep the id pinned. A
    // pinned running id lets a retry reuse it; a pinned indeterminate id
    // makes the entry guard above refuse any silent retry until the user
    // explicitly confirms a fresh start. Any other outcome is terminal:
    // forget it.
    if (!error || (!error.operationStillRunning && !error.operationUnknown)) forget();
    throw error;
  }
  if (data && data.operation_id === id && data.operation_status === "running") {
    // A retry that reused an in-flight id: the server answered synchronously
    // instead of executing again. Poll it exactly like a timed-out request.
    try {
      data = await pollOperationResult(id);
    } catch (error) {
      if (!error || (!error.operationStillRunning && !error.operationUnknown)) forget();
      throw error;
    }
  }
  forget();
  return data;
}

// (Fix 096 A5) Explicit fresh attempt after an indeterminate outcome. The UI
// offers this ONLY after telling the user to establish whether the first
// request completed (for example, reopen or refresh the Space and check
// whether the change landed), and labels the action as potentially applying
// the change twice. It clears the pinned indeterminate id so the next
// apiSideEffect() mints a genuinely fresh operation_id - never a reuse of the
// indeterminate one. `operationId` is not accepted here: a caller-supplied id
// would re-enter the same server operation that already returned "unknown".
// This helper has no silent or internal callers.
function apiSideEffectStartOver(path, payload, opts = {}) {
  if (opts && opts.operationId) {
    throw new TypeError("apiSideEffectStartOver does not accept operationId: the fresh start must mint a new operation_id.");
  }
  const fingerprint = operationFingerprint(path, payload);
  const id = inFlightOperationIds.get(fingerprint);
  if (id) indeterminateOperationIds.delete(id);
  inFlightOperationIds.delete(fingerprint);
  const { operationId: _ignored, ...rest } = opts;
  return apiSideEffect(path, payload, rest);
}

let toastTimer;
function toast(message, error = false, hold = 3200) {
  const node = $("#toast");
  // Fix 096 F6: toasts always appear above the current top layer. While a
  // dialog is open the toast node lives inside the open dialog; otherwise it
  // lives directly in the document body. No per-call-site changes needed.
  const openDialog = document.querySelector("dialog[open]");
  if (openDialog) {
    openDialog.appendChild(node);
  } else if (node.parentElement !== document.body) {
    document.body.appendChild(node);
  }
  node.textContent = message;
  node.classList.toggle("error", error);
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), hold);
}

function setError(message = "", actions = []) {
  const panel = $("#error-panel");
  panel.replaceChildren();
  if (actions.length) {
    actions.forEach(action => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "error-link";
      button.textContent = action.message;
      button.addEventListener("click", action.activate);
      panel.append(button);
    });
  } else if (message) {
    panel.textContent = message;
  }
  panel.hidden = !message && !actions.length;
}

// Fix 078: the primary "Invalid settings" location, physically over the
// active Design canvas (3D and 2D both carry it, kept in sync, never the
// Space/Drawer canvas). Runtime-only projection of refreshPreview()'s own
// latest-request error state - never a second source of truth.
function setDesignInvalidOverlay(message = "") {
  ["#design-invalid-overlay-3d", "#design-invalid-overlay-2d"].forEach(selector => {
    const overlay = $(selector);
    if (!overlay) return;
    overlay.hidden = !message;
    const text = $(".design-invalid-message", overlay);
    if (text) text.textContent = message;
  });
}

const TEXT_DEPTH_NAMES = new Map([
  ["0.2", "Thin"], ["0.4", "Default"], ["0.6", "Thick"], ["0.8", "Thickest"],
]);

function textDepthChoices(info = partInfo("text")) {
  const depth = (info?.options || []).find(option => option.key === "depth");
  return (depth?.choices || []).map(choice => {
    const value = Number(choice.value);
    const name = TEXT_DEPTH_NAMES.get(String(value));
    return {
      value,
      label: name ? `${name} ${value} mm` : (choice.label || `${value} mm`),
    };
  }).filter(choice => Number.isFinite(choice.value));
}

function textBackingRules() {
  return state.catalog?.text_depth_rules || {};
}

function baseTextReceivingThickness(design = state.design) {
  const base = number(design?.box?.base_thickness, NaN);
  if (!Number.isFinite(base)) return NaN;
  if ((design?.layout?.mode || "fused") === "fused") return base;
  return base + number(textBackingRules().removable_base_plate_mm, 0);
}

function inlayDepthLegal(depth, receivingThickness, minimumBacking) {
  return Number.isFinite(depth) && Number.isFinite(receivingThickness) &&
    Number.isFinite(minimumBacking) &&
    depth <= receivingThickness - minimumBacking + 1e-9;
}

function partInfo(kind = state.draftKind) {
  return state.catalog.parts.find(part => part.kind === kind);
}

function editingEdgeMount() {
  return state.modifierEditing === "edge_mount";
}

const BOX_MODIFIER_KINDS = new Set([
  "lid_stacking", "inside_handles", "side_openings", "edge_mount",
]);

function modifierIsActive(kind, design = state.design) {
  const box = design?.box || {};
  if (kind === "lid_stacking") {
    return Boolean(box.lid?.enabled || (box.stack?.mode && box.stack.mode !== "none"));
  }
  if (kind === "inside_handles") return Boolean(box.lift_grabbers?.enabled);
  if (kind === "side_openings") return Boolean(box.side_openings?.enabled);
  if (kind === "edge_mount") {
    return Boolean(box.edge_mount?.label_enabled || box.edge_mount?.holes_enabled);
  }
  return false;
}

function partInstanceCount(kind, design = state.design) {
  if (BOX_MODIFIER_KINDS.has(kind)) return modifierIsActive(kind, design) ? 1 : 0;
  return (design?.layout?.features || []).filter(one => one.kind === kind).length;
}

function partAtLimit(info, design = state.design) {
  const max = info?.max_instances;
  return Number.isInteger(max) && partInstanceCount(info.kind, design) >= max;
}

function edgeMountActive(design = state.design) {
  const one = design?.box?.edge_mount;
  return Boolean(one?.label_enabled || one?.holes_enabled);
}

function edgeMountAvailable(design = state.design) {
  return !baseTrimEnabled(design) && !Boolean(design?.box?.b4b?.enabled);
}

function placedPartCount() {
  return (state.design?.layout?.features?.length || 0) +
    [...BOX_MODIFIER_KINDS].filter(kind => modifierIsActive(kind)).length;
}

function iconFor(kind) {
  const common = 'viewBox="2 2 28 28" aria-hidden="true"';
  const iconId = partInfo(kind)?.icon || kind;
  const paths = window.WavefinityFeatureIcons || {};
  return `<svg ${common}>${paths[iconId] || paths.pocket || ""}</svg>`;
}

function renderCatalog() {
  const modes = $("#mode-select");
  modes.innerHTML = state.catalog.modes.map(mode => `
    <option value="${escapeHtml(mode.value)}">${escapeHtml(mode.label)}</option>
  `).join("");
  modes.addEventListener("change", async () => {
      if (modes.value === state.design.layout.mode) return;
      if (modes.value === "separate" && insideHandlesActive()) {
        modes.value = state.design.layout.mode;
        toast(INSIDE_HANDLES_REMOVABLE_MESSAGE, true, 6500);
        return;
      }
      if (!beginDesignMutation()) {
        syncForm();
        return;
      }
      const oldMode = state.design.layout.mode;
      let committedDraft = false;
      try {
        // Preserve the exact visible edit before converting the saved layout.
        // A debounced draft must not disappear just because the user switches
        // print mode quickly after changing a field.
        committedDraft = await commitVisibleDraft({ previewAfterCommit: false });
        const previousDesign = clone(state.design);
        const previousSelected = state.selected;
        const result = await api("/api/layout/mode", { design: state.design, mode: modes.value });
        state.design = result.design;
        noteCommittedDesignChange(previousDesign);
        syncForm();
        // A support that was already saved keeps being edited, just in its
        // converted form - only fall back to a fresh, not-yet-saved
        // suggestion when nothing was actually selected before the switch.
        if (previousSelected !== null && previousSelected < state.design.layout.features.length) {
          // The visible draft was already folded in by commitVisibleDraft above
          // and the layout has just been reconverted - reselect straight through.
          if (!(await selectedFeature(previousSelected, true))) refreshPreview();
        } else {
          clearDraftSelection();
          refreshPreview();
        }
        committedDraft = false;
      } catch (error) {
        if (committedDraft) refreshPreview();
        modes.value = oldMode;
        toast(error.message, true);
      } finally {
        finishDesignMutation();
      }
  });

  const palette = $("#support-palette");
  palette.innerHTML = state.catalog.parts
    .filter(part => part.palette_visible !== false)
    .map(part => `
    <button class="support-choice" data-kind="${part.kind}" aria-label="${escapeHtml(part.title)}: ${escapeHtml(part.description)}" title="${escapeHtml(part.title)} — ${escapeHtml(part.description)}">
      <span class="support-choice-icon">
        ${iconFor(part.kind)}
      </span>
      <span class="support-choice-copy">
        <strong>${escapeHtml(part.title)}</strong>
        <span class="support-choice-desc">${escapeHtml(part.description)}</span>
        <span class="support-choice-state" hidden></span>
      </span>
    </button>
  `).join("");
  $$(".support-choice", palette).forEach(button => {
    button.style.setProperty("--support-color", kindColor(button.dataset.kind));
    button.addEventListener("click", () => pickKind(button.dataset.kind));
  });
}

function ensureRimFeatureInLayout() {
  if (!state.design) return;
  const tidy = (state.design.label || "").trim();
  const hasRimFeature = state.design.layout?.features?.some(f => f.kind === "text" && f.options?.level === "rim");
  if (tidy && !hasRimFeature) {
    state.design.layout.features = [
      ...state.design.layout.features,
      {
        kind: "text",
        zone: [-16, -4, 16, 4],
        options: {
          text: tidy,
          level: "rim",
          rim_side: ["front", "back", "left", "right"].includes(state.design.label_position)
            ? state.design.label_position : "back",
        },
        along: "x",
        item: null,
        count: null,
      },
    ];
  }
}

function syncRimLabelFromFeatures() {
  if (!state.design) return;
  // General rim lettering belongs to independent Text features. These old
  // fields are accepted on load only and must never collapse those features.
  state.design.label = "";
  state.design.label_position = "bottom";
}

function populateLiftGrabberChoices() {
  const rules = state.catalog?.lift_grabbers || {};
  const sizeSelect = $("#lift-grabber-size");
  const locationSelect = $("#lift-grabber-location");
  if (sizeSelect && !sizeSelect.options.length) {
    for (const choice of rules.sizes || []) {
      const opt = document.createElement("option");
      opt.value = choice.value;
      opt.textContent = choice.label;
      sizeSelect.appendChild(opt);
    }
  }
  if (locationSelect && !locationSelect.options.length) {
    for (const choice of rules.locations || []) {
      const opt = document.createElement("option");
      opt.value = choice.value;
      opt.textContent = choice.label;
      locationSelect.appendChild(opt);
    }
  }
}

function syncLiftGrabberControls() {
  const enabled = $("#lift-grabber-size")?.value !== "no";
  if ($("#lift-grabber-location-setting")) $("#lift-grabber-location-setting").hidden = !enabled;
}


// Fix 058 Correction 1, C1.4B/G: the Label selector (None / Separate Part /
// Integrated) is UI-only - it is derived from the existing label_enabled/
// label_type fields, never persisted as its own key.
function edgeMountLabelMode(edgeMount) {
  if (!edgeMount?.label_enabled) return "none";
  return edgeMount.label_type === "integrated" ? "integrated" : "separate";
}

// Mirrors readLiftGrabberForm/readStackForm: only resets an *existing* key to
// defaults when both subsections are off, so a design that never touched
// Edge Mount keeps no key at all and design_to_dict omits the block while
// disabled. Both subsections' fields are always preserved together so
// toggling one off never erases the other's settings.
function readEdgeMountForm(design) {
  design.box = design.box || {};
  const labelMode = $("#edge-mount-label-mode")?.value || "none";
  const labelEnabled = labelMode !== "none";
  const holesEnabled = Boolean($("#edge-mount-holes-enabled")?.checked);
  if (!labelEnabled && !holesEnabled) {
    if (design.box.edge_mount) design.box.edge_mount = { ...EDGE_MOUNT_DEFAULTS };
    return;
  }
  const current = { ...EDGE_MOUNT_DEFAULTS, ...(design.box.edge_mount || {}) };
  // Label=None preserves the previously chosen label_type (Separate/
  // Integrated) rather than resetting it, just like the former enable
  // checkbox left it untouched - re-enabling later restores the same choice.
  const labelType = labelMode === "none" ? current.label_type : labelMode;
  const projection = number(
    $("#edge-mount-label-projection-mm")?.value, current.label_projection_mm,
  );
  const thicknessInput = $("#edge-mount-label-thickness-mm");
  const thicknessRaw = thicknessInput?.value ?? "";
  const thicknessWasEdited = thicknessRaw !== (thicknessInput?.dataset.storedValue ?? thicknessRaw);
  let thickness = current.label_thickness_mm;
  if (thicknessWasEdited) {
    // Typed intent is kept exactly as entered, even when out of range: the
    // field stays editable and edgeMountInputProblems() explains the limit.
    thickness = number(thicknessRaw, current.label_thickness_mm);
    // The design now owns this value; without this, typing the original
    // number back would look "unedited" and silently keep the new one.
    if (thicknessInput && thicknessRaw !== "") thicknessInput.dataset.storedValue = thicknessRaw;
  }
  const spacingMode = $("#edge-mount-spacing-mode")?.value || "auto";
  const ribCountMode = $("#edge-mount-standoff-rib-count-mode")?.value || "auto";
  // Fix 058 Correction 1, C1.4C: a Separate Part label is always Inlaid /
  // Flush - Raised text is not a valid manufacturing state for it, so the
  // Label style control is hidden entirely and label_raised is forced false
  // whenever Separate Part is selected. Label=None preserves whatever the
  // Style control last held, same as every other detail field.
  const labelRaised = labelType === "separate"
    ? false
    : labelMode === "none" ? current.label_raised : $("#edge-mount-label-style")?.value === "raised";
  const requestedTextDepth = number(
    $("#edge-mount-label-depth")?.value, current.label_text_depth_mm,
  );
  const labelTextDepth = requestedTextDepth;
  if ($("#edge-mount-label-depth") && !labelRaised) {
    $("#edge-mount-label-depth").max = String(edgeMountLegalInlayDepth({
      ...current,
      label_thickness_mm: thickness,
      label_type: labelType,
      label_raised: labelRaised,
    }));
  }
  const accessChoice = $("#edge-mount-access-diameter")?.value || "auto";
  design.box.edge_mount = {
    side: $("#edge-mount-side")?.value || "front",
    label_enabled: labelEnabled,
    label_text: $("#edge-mount-label-text")?.value || "",
    label_type: labelType,
    label_projection_mm: projection,
    label_length_mode: $("#edge-mount-label-length-mode")?.value || "full",
    label_thickness_mm: thickness,
    label_raised: labelRaised,
    label_text_depth_mm: labelTextDepth,
    label_flip: Boolean($("#edge-mount-label-flip")?.checked),
    standoff_ribs_enabled: Boolean($("#edge-mount-standoff-ribs-enabled")?.checked),
    standoff_rib_count: ribCountMode === "manual"
      ? number($("#edge-mount-standoff-rib-count")?.value, current.standoff_rib_count || 1)
      : null,
    holes_enabled: holesEnabled,
    hole_count: number($("#edge-mount-hole-count")?.value, current.hole_count),
    hole_orientation: $("#edge-mount-hole-orientation")?.value || "horizontal",
    screw_diameter_mm: number($("#edge-mount-screw-diameter")?.value, current.screw_diameter_mm),
    access_diameter_mm: accessChoice === "auto"
      ? null
      : number(accessChoice, resolvedEdgeMountAccessDiameter(current)),
    top_offset_mm: number($("#edge-mount-top-offset")?.value, current.top_offset_mm),
    hole_spacing_mm: spacingMode === "custom"
      ? number($("#edge-mount-spacing-mm")?.value, current.hole_spacing_mm || EDGE_MOUNT_DEFAULTS.top_offset_mm)
      : null,
  };
}

// Python remains authoritative for real validation/geometry; this is only
// for the immediate "Auto: X mm" readout while typing.
function resolvedEdgeMountAccessDiameter(edgeMount) {
  if (edgeMount.access_diameter_mm !== null && edgeMount.access_diameter_mm !== undefined) {
    return number(edgeMount.access_diameter_mm, 8);
  }
  return Math.max(8, number(edgeMount.screw_diameter_mm, 4) * 2);
}

// Local, visible validation for the two label inputs that used to be silently
// rewritten. Python stays authoritative; these messages sit beside the field
// and the out-of-range value is still what the design (and so print) sees.
function edgeMountInputProblems() {
  const rules = state.catalog?.edge_mount || {};
  const problems = { thickness: "", depth: "" };
  const mode = $("#edge-mount-label-mode")?.value || "none";
  if (mode === "none") return problems;
  const rawThickness = ($("#edge-mount-label-thickness-mm")?.value ?? "").trim();
  const minT = number(rules.min_thickness_mm, 0.8), maxT = number(rules.max_thickness_mm, 6);
  const thickness = rawThickness === "" ? NaN : Number(rawThickness);
  if (!Number.isFinite(thickness)) problems.thickness = "Enter a label thickness.";
  else if (thickness < minT || thickness > maxT) problems.thickness = `Label thickness must be ${fmt(minT)}–${fmt(maxT)} mm.`;
  const rawDepth = ($("#edge-mount-label-depth")?.value ?? "").trim();
  const minD = number(rules.min_text_depth_mm, 0.2), maxD = number(rules.max_text_depth_mm, 2);
  const depth = rawDepth === "" ? NaN : Number(rawDepth);
  if (!Number.isFinite(depth)) problems.depth = "Enter a text depth.";
  else if (depth < minD || depth > maxD) problems.depth = `Text depth must be ${fmt(minD)}–${fmt(maxD)} mm.`;
  else if (Number.isFinite(thickness) && !(mode === "integrated" && $("#edge-mount-label-style")?.value === "raised")) {
    const legal = Math.min(maxD, thickness - number(textBackingRules().min_backing_mm, 0.2));
    if (depth > legal + 1e-9) problems.depth = `Inlay depth cannot exceed ${fmt(Math.max(minD, legal))} mm for a ${fmt(thickness)} mm label.`;
  }
  return problems;
}

function syncEdgeMountInputProblems() {
  const problems = edgeMountInputProblems();
  for (const [key, id, input] of [["thickness", "#edge-mount-thickness-error", "#edge-mount-label-thickness-mm"],
                                   ["depth", "#edge-mount-depth-error", "#edge-mount-label-depth"]]) {
    const node = $(id);
    if (node) { node.textContent = problems[key]; node.hidden = !problems[key]; }
    $(input)?.toggleAttribute("aria-invalid", Boolean(problems[key]));
  }
  return problems;
}

function edgeMountLegalInlayDepth(edgeMount) {
  const rules = state.catalog?.edge_mount || {};
  const backing = number(textBackingRules().min_backing_mm, 0.2);
  return Math.max(
    number(rules.min_text_depth_mm, 0.2),
    Math.min(
      number(rules.max_text_depth_mm, 2),
      number(edgeMount.label_thickness_mm, 2) - backing,
    ),
  );
}

function syncEdgeMountDepthLimit(edgeMount) {
  const input = $("#edge-mount-label-depth");
  if (!input) return;
  const raised = edgeMount.label_type === "integrated" && edgeMount.label_raised;
  input.max = String(raised
    ? number(state.catalog?.edge_mount?.max_text_depth_mm, 2)
    : edgeMountLegalInlayDepth(edgeMount));
}

function syncEdgeMountAutoAccessFromForm() {
  const select = $("#edge-mount-access-diameter");
  if (!select || select.value !== "auto") return;
  const auto = [...select.options].find(option => option.value === "auto");
  if (!auto) return;
  const screw = number(
    $("#edge-mount-screw-diameter")?.value,
    state.design?.box?.edge_mount?.screw_diameter_mm ?? EDGE_MOUNT_DEFAULTS.screw_diameter_mm,
  );
  auto.textContent = `Auto (${fmt(Math.max(8, screw * 2))} mm)`;
}

function syncEdgeMountControls() {
  const edgeMount = { ...EDGE_MOUNT_DEFAULTS, ...(state.design?.box?.edge_mount || {}) };
  if ($("#edge-mount-side")) $("#edge-mount-side").value = edgeMount.side;
  if ($("#edge-mount-label-mode")) $("#edge-mount-label-mode").value = edgeMountLabelMode(edgeMount);
  if ($("#edge-mount-holes-enabled")) $("#edge-mount-holes-enabled").checked = edgeMount.holes_enabled;
  if ($("#edge-mount-label-text")) $("#edge-mount-label-text").value = edgeMount.label_text;
  if ($("#edge-mount-label-length-mode")) $("#edge-mount-label-length-mode").value = edgeMount.label_length_mode;
  if ($("#edge-mount-label-style")) $("#edge-mount-label-style").value = edgeMount.label_raised ? "raised" : "flush";
  if ($("#edge-mount-label-depth")) $("#edge-mount-label-depth").value = fmt(edgeMount.label_text_depth_mm);
  syncEdgeMountDepthLimit(edgeMount);
  if ($("#edge-mount-label-flip")) $("#edge-mount-label-flip").checked = edgeMount.label_flip;
  if ($("#edge-mount-standoff-ribs-enabled")) {
    $("#edge-mount-standoff-ribs-enabled").checked = edgeMount.standoff_ribs_enabled;
  }
  const ribCountMode = edgeMount.standoff_rib_count === null || edgeMount.standoff_rib_count === undefined
    ? "auto" : "manual";
  if ($("#edge-mount-standoff-rib-count-mode")) $("#edge-mount-standoff-rib-count-mode").value = ribCountMode;
  if ($("#edge-mount-standoff-rib-count")) {
    $("#edge-mount-standoff-rib-count").value = String(edgeMount.standoff_rib_count || 1);
  }
  if ($("#edge-mount-standoff-rib-count-row")) {
    $("#edge-mount-standoff-rib-count-row").hidden = ribCountMode !== "manual";
  }
  if ($("#edge-mount-hole-count")) $("#edge-mount-hole-count").value = String(edgeMount.hole_count);
  if ($("#edge-mount-hole-orientation")) $("#edge-mount-hole-orientation").value = edgeMount.hole_orientation;
  if ($("#edge-mount-screw-diameter")) $("#edge-mount-screw-diameter").value = fmt(edgeMount.screw_diameter_mm);
  if ($("#edge-mount-top-offset")) $("#edge-mount-top-offset").value = fmt(edgeMount.top_offset_mm);
  if ($("#edge-mount-label-projection-mm")) {
    $("#edge-mount-label-projection-mm").value = fmt(edgeMount.label_projection_mm);
  }

  const thicknessInput = $("#edge-mount-label-thickness-mm");
  if (thicknessInput) {
    thicknessInput.value = fmt(edgeMount.label_thickness_mm);
    thicknessInput.dataset.storedValue = thicknessInput.value;
  }
  const accessSelect = $("#edge-mount-access-diameter");
  if (accessSelect) {
    $("option[data-legacy]", accessSelect)?.remove();
    const resolved = resolvedEdgeMountAccessDiameter(edgeMount);
    const auto = [...accessSelect.options].find(option => option.value === "auto");
    if (auto) auto.textContent = `Auto (${fmt(resolved)} mm)`;
    if (edgeMount.access_diameter_mm === null || edgeMount.access_diameter_mm === undefined) {
      accessSelect.value = "auto";
    } else {
      const explicit = number(edgeMount.access_diameter_mm, resolved);
      const standard = [6, 8, 10].some(value => Math.abs(value - explicit) < 1e-9);
      if (!standard) {
        const option = new Option(`${fmt(explicit)} mm — Existing`, fmt(explicit));
        option.dataset.legacy = "true";
        accessSelect.appendChild(option);
      }
      accessSelect.value = fmt(explicit);
    }
  }
  const spacingMode = edgeMount.hole_spacing_mm === null || edgeMount.hole_spacing_mm === undefined ? "auto" : "custom";
  if ($("#edge-mount-spacing-mode")) $("#edge-mount-spacing-mode").value = spacingMode;
  if ($("#edge-mount-spacing-custom-row")) $("#edge-mount-spacing-custom-row").hidden = spacingMode !== "custom";
  if (spacingMode === "custom" && $("#edge-mount-spacing-mm")) {
    $("#edge-mount-spacing-mm").value = fmt(edgeMount.hole_spacing_mm);
  }

  // Fix 058 Correction 1, C1.4: the Label and Screw Mounting cards are
  // always visible; only their detail groups hide/show, driven by the Label
  // selector and the Screw Mounting checkbox respectively.
  const labelMode = edgeMountLabelMode(edgeMount);
  if ($("#edge-mount-label-details")) $("#edge-mount-label-details").hidden = labelMode === "none";
  if ($("#edge-mount-holes-details")) $("#edge-mount-holes-details").hidden = !edgeMount.holes_enabled;
  if ($("#edge-mount-label-style-row")) $("#edge-mount-label-style-row").hidden = labelMode !== "integrated";
  if ($("#edge-mount-standoff-rib-controls")) {
    $("#edge-mount-standoff-rib-controls").hidden = labelMode !== "separate";
  }
  if ($("#edge-mount-integrated-support-warning")) {
    $("#edge-mount-integrated-support-warning").hidden = labelMode !== "integrated";
  }
  if ($("#edge-mount-hole-orientation-row")) $("#edge-mount-hole-orientation-row").hidden = number(edgeMount.hole_count) <= 1;
  syncEdgeMountInputProblems();
}

function syncEdgeMountEditorVisibility() {
  const scratch = { box: { edge_mount: { ...EDGE_MOUNT_DEFAULTS, ...(state.design?.box?.edge_mount || {}) } } };
  readEdgeMountForm(scratch);
  const labelMode = $("#edge-mount-label-mode")?.value || "none";
  $("#edge-mount-label-details").hidden = labelMode === "none";
  $("#edge-mount-holes-details").hidden = !$("#edge-mount-holes-enabled").checked;
  if ($("#edge-mount-label-style-row")) $("#edge-mount-label-style-row").hidden = labelMode !== "integrated";
  $("#edge-mount-standoff-rib-controls").hidden = labelMode !== "separate";
  if ($("#edge-mount-integrated-support-warning")) {
    $("#edge-mount-integrated-support-warning").hidden = labelMode !== "integrated";
  }
  $("#edge-mount-standoff-rib-count-row").hidden = $("#edge-mount-standoff-rib-count-mode").value !== "manual";
  $("#edge-mount-spacing-custom-row").hidden = $("#edge-mount-spacing-mode").value !== "custom";
  $("#edge-mount-hole-orientation-row").hidden = number($("#edge-mount-hole-count").value) <= 1;
  syncEdgeMountInputProblems();
  const access = $("#edge-mount-access-diameter");
  if (access) {
    const tooSmall = number(access.value) < number($("#edge-mount-screw-diameter")?.value);
    access.setCustomValidity(tooSmall ? "Screwdriver access must be at least the screw diameter." : "");
  }
}