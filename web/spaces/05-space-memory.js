"use strict";

// Story 2903: exact set-aside bins. No validation on this storage path: a
// broken design and its unfinished editor fields are precisely what it keeps.
// Memory owns every copy until an explicit Discard; there is no eviction cap.
SP.BIN_RECOVERY_FIELD = "__wavefinity_set_aside_v1";
SP.BIN_RECOVERY_PREFIX = "wavefinity.binRecovery.v1.";
SP._binRecovery = new Map();
SP._binRecoveryTargets = new Map();
SP._binRecoveryBase = new Map();
SP._binRecoveryNotices = new Set();
SP._binRecoveryLoaded = false;
SP._binRecoveryFields = [
  "design", "cleanDesign", "designInventoryId", "lastOrdinaryDesign", "draft",
  "draftKind", "drafts", "draftResolvedOptions", "draftAutoCommit", "draftIsNew",
  "draftSourceIndex", "draftTouched", "selected", "paletteBrowsing",
  "edgeMountEditing", "modifierEditing", "pinnedZone", "partZoneLocks",
  "lidMemory", "binResizePending", "binFootprintResizePending", "surfaceHeightPromptSkipped",
  "nestPhoto", "nestOriginalImage", "nestRectifiedImage", "nestSensitivity",
  "nestCleanup", "nestPhotoOpacity", "nestCandidateContour", "nestCandidateCenterMm",
  "nestAcceptedCenterMm", "nestTuneStatus", "nestTraceResult", "nestPaperCorners",
  "nestCornerError", "nestCornerTipDismissed", "nestOutlineTool", "nestOutlineEditing",
  "nestViewZoom", "nestViewPanX", "nestViewPanY",
];

SP.binEditorVisible = () => {
  if (SP.dialog()?.open || designTargetIsStructural()) return false;
  if (typeof WS !== "undefined") return ["bin", "peek"].includes(WS.task);
  return typeof DP !== "undefined" && DP.mode === "design";
};

SP.binRecoveryInputs = () => $$("input, select, textarea", $(".controls"))
  .filter(el => !["file", "password", "button", "submit"].includes(el.type) &&
    !el.closest("#drawer-panel, #space-head, #ws-stage, #ws-aux"));

SP.captureBinSnapshot = (visible = SP.binEditorVisible()) => {
  const values = {};
  for (const key of SP._binRecoveryFields) {
    if (state[key] !== undefined) values[key] = clone(state[key]);
  }
  return {
    values,
    forms: visible ? SP.binRecoveryInputs().map((el, index) => ({
      id: el.id, draft: el.dataset.draft, index, value: el.value, checked: el.checked,
    })) : [],
    pendingDesign: visible ? clone(pendingPreEditDesign) : null,
    draftError: visible ? $("#draft-status")?.textContent || "" : "",
  };
};

SP.snapshotStoredBin = design => ({
  values: { design: clone(design), cleanDesign: clone(design), designInventoryId: null },
  forms: [], pendingDesign: null, draftError: "",
});

SP.withoutBinRecovery = design => {
  if (!design) return design;
  const plain = clone(design);
  delete plain[SP.BIN_RECOVERY_FIELD];
  return plain;
};

SP.packBinRecovery = entry => ({
  id: entry.id, spaceId: entry.spaceId, spaceName: entry.spaceName,
  binName: entry.binName, snapshot: entry.snapshot,
});

SP.isBinRecovery = entry => Boolean(entry && typeof entry.id === "string" &&
  typeof entry.spaceId === "string" && typeof entry.spaceName === "string" &&
  typeof entry.binName === "string" && entry.snapshot?.values?.design &&
  Array.isArray(entry.snapshot.forms));

SP.loadBrowserBinRecovery = () => {
  if (SP._binRecoveryLoaded) return;
  SP._binRecoveryLoaded = true;
  try {
    for (let index = 0; index < localStorage.length; index++) {
      const key = localStorage.key(index);
      if (!key?.startsWith(SP.BIN_RECOVERY_PREFIX)) continue;
      try {
        const entry = JSON.parse(localStorage.getItem(key));
        if (SP.isBinRecovery(entry) && !SP._binRecovery.has(entry.id))
          SP._binRecovery.set(entry.id, { ...entry, tier: "browser", browserCopy: true });
      } catch (_error) { /* Leave an unreadable stored copy untouched. */ }
    }
  } catch (_error) { /* Memory remains available when browser storage is blocked. */ }
};

SP.readBinRecoveryCheckpoint = () => {
  SP._binSwitchAside = null;
  SP.loadBrowserBinRecovery();
  const target = SP._captureResumeTarget();
  if (!target) return;
  SP._binRecoveryTargets.set(target.spaceId, target);
  const records = state.spaceResumeDesign?.[SP.BIN_RECOVERY_FIELD];
  if (Array.isArray(records)) for (const entry of records) {
    if (SP.isBinRecovery(entry) && entry.spaceId === target.spaceId) {
      const existing = SP._binRecovery.get(entry.id);
      SP._binRecovery.set(entry.id, { ...entry, ...existing, tier: "space" });
    }
  }
  state.spaceResumeDesign = SP.withoutBinRecovery(state.spaceResumeDesign);
  SP._binRecoveryBase.set(target.spaceId, clone(state.spaceResumeDesign));
};

SP.withBinRecovery = (target, design) => {
  const plain = SP.withoutBinRecovery(design);
  const records = [...SP._binRecovery.values()]
    .filter(entry => entry.spaceId === target.spaceId && !entry.discarding)
    .map(SP.packBinRecovery);
  // With no recovery, valid saves retain their existing payload exactly.
  return records.length ? { ...plain, [SP.BIN_RECOVERY_FIELD]: records } : plain;
};

SP.saveBinRecovery = async entry => {
  const target = SP._binRecoveryTargets.get(entry.spaceId);
  if (target) {
    try {
      // Settle the old write owner first; no late checkpoint may erase entries.
      await SP.flushOutgoingResumeCheckpoint();
      await SP._writeResumeCheckpointNow(target,
        SP._binRecoveryBase.get(entry.spaceId) || entry.snapshot.values.design, false);
      entry.message = "";
      return;
    } catch (_error) { /* Unwritable Space: keep the exact copy in this browser. */ }
  }
  try {
    const text = JSON.stringify(SP.packBinRecovery(entry));
    const key = SP.BIN_RECOVERY_PREFIX + entry.id;
    localStorage.setItem(key, text);
    if (localStorage.getItem(key) !== text) throw new Error("Recovery write did not finish");
    entry.tier = "browser";
    entry.browserCopy = true;
  } catch (_error) {
    // Never remove the live copy, even if BOTH durable stores failed.
    if (entry.tier !== "space" && entry.tier !== "browser") entry.tier = "memory";
  }
};

SP.setAsideBin = async snapshot => {
  SP.loadBrowserBinRecovery();
  const target = SP._captureResumeTarget();
  if (!target || !snapshot.values.design) return;
  SP._binRecoveryTargets.set(target.spaceId, target);
  const key = JSON.stringify(snapshot);
  let entry = [...SP._binRecovery.values()].find(one =>
    one.spaceId === target.spaceId && JSON.stringify(one.snapshot) === key);
  if (!entry) {
    const binName = snapshot.forms.find(one => one.id === "part-name")?.value ||
      snapshot.values.design.part_name || "New bin";
    entry = { id: crypto.randomUUID(), spaceId: target.spaceId,
      spaceName: target.space.name || "Space", binName, snapshot, tier: "memory" };
    // Retain FIRST, before any write or wait that can fail.
    SP._binRecovery.set(entry.id, entry);
  }
  await SP.saveBinRecovery(entry);
  SP._binRecoveryNotices.add(entry.id);
  SP.renderBinRecovery();
};

SP.leaveBinForSpaceSwitch = async ({ visible = true, ...options } = {}) => {
  await waitForDesignMutation();
  if (!typedSpaceOrdinaryBin() || designTargetIsStructural() ||
      DP.getDesignTarget().kind === "none") return true;
  visible = visible && SP.binEditorVisible();
  const currentKey = () => JSON.stringify([state.design, state.draft, state.drafts]);
  // Entering the picker already set this work aside. Opening a card from
  // that picker must not make a second recovery of the same hidden bin.
  if (!visible && SP._binSwitchAside?.spaceId === state.activeSpaceId &&
      SP._binSwitchAside.key === currentKey()) {
    clearTimeout(spaceAutosaveTimer);
    spaceAutosaveTimer = null;
    cancelChangedDesignDebounce();
    cancelPendingDraftWork();
    return true;
  }
  // Freeze pending work before saving, so a late preview cannot replace the
  // failed design or a debounced edit land under the next Space's identity.
  clearTimeout(spaceAutosaveTimer);
  spaceAutosaveTimer = null;
  await spaceAutosaveChain;
  await waitForDesignMutation();
  const snapshot = SP.captureBinSnapshot(visible);
  const settled = state.previewSettledRequest === state.previewRequest;
  const owned = beginDesignMutation({ readForm: false, quiet: true });
  if (settled && owned) state.previewSettledRequest = state.previewRequest;
  let saved = false;
  try {
    try {
      saved = owned && await flushSpaceDesignAutosave({ ...options, visible, spaceSwitch: true,
        mutationOwned: true, deferDraftPreview: true, noDeferredPreview: true });
    } catch (_error) { /* All bin flush failures use the same exact set-aside. */ }
    clearTimeout(spaceAutosaveTimer);
    spaceAutosaveTimer = null;
    if (!saved) {
      await SP.setAsideBin(snapshot);
    }
  } finally {
    if (owned) finishDesignMutation();
  }
  if (!saved) SP._binSwitchAside = { spaceId: state.activeSpaceId, key: currentKey() };
  return true;
};

SP.exportBinRecovery = entry => {
  const design = clone(entry.snapshot.values.design);
  // The design stays a normal design-file payload; the extra recovery field
  // also carries the exact unfinished forms/draft for lossless re-import.
  design[SP.BIN_RECOVERY_FIELD] = [SP.packBinRecovery(entry)];
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob([JSON.stringify(design, null, 2) + "\n"], { type: "application/json" }));
  link.download = `${entry.binName.replace(/[^a-z0-9 _-]/gi, "").trim() || "New bin"}.wavefinity.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
};

SP.openBinRecovery = async entry => {
  if (state.activeSpaceId !== entry.spaceId || state.designMutationBusy) return;
  if (SP.editing && !(await SP.flushSetupAutosave())) return;
  if (!(await SP.confirmLeaveStructuralEditor())) return;
  const context = DL.spaceContext();
  await SP.leaveBinForSpaceSwitch();
  if (!DL.spaceContextCurrent(context) || !beginDesignMutation({ readForm: false })) return;
  let restoreEditor = null;
  try {
    SP.resetDesignSession();
    clearDraftSelection();
    const restoreValues = () => {
      for (const key of SP._binRecoveryFields) {
        if (Object.hasOwn(entry.snapshot.values, key)) state[key] = clone(entry.snapshot.values[key]);
      }
    };
    restoreValues();
    // A missing former row is a new bin, never another row's identity.
    if (state.designInventoryId && !DL.bin(state.designInventoryId)) state.designInventoryId = null;
    state.designTarget = null;
    state.spaceStarterPreviewPending = false;
    bindLidMemoryForDesign();
    syncForm();
    if (state.draft) renderDraftFields();
    restoreValues();
    if (state.designInventoryId && !DL.bin(state.designInventoryId)) state.designInventoryId = null;
    pendingPreEditDesign = clone(entry.snapshot.pendingDesign);
    DP.setMode("design");
    if (typeof WS !== "undefined") { WS.task = "bin"; WS.peekId = null; WS.sync(); }
    activatePreviewView(preferredDesignView());
    // Show the real fault using the ordinary preview owner, without adopting
    // a normalized design or saving over this recovery during the open.
    await refreshPreview({ persistResume: false, recovery: true });
    // Rendering can adjust fields/remembered settings; reopening recovery
    // never commits those adjustments into the saved unfinished state.
    restoreEditor = () => {
      restoreValues();
      if (state.designInventoryId && !DL.bin(state.designInventoryId)) state.designInventoryId = null;
      const inputs = SP.binRecoveryInputs();
      for (const field of entry.snapshot.forms) {
        const el = field.id ? document.getElementById(field.id) : inputs[field.index];
        if (!el || (field.draft && el.dataset.draft !== field.draft)) continue;
        el.value = field.value;
        if (field.checked !== undefined) el.checked = field.checked;
      }
      if (entry.snapshot.draftError && $("#draft-status")) {
        $("#draft-status").textContent = entry.snapshot.draftError;
        $("#draft-status").classList.add("error");
      }
    };
    entry.message = "Opened this set-aside bin. Its saved recovery copy stays here while you fix it.";
  } catch (_error) {
    entry.message = "This bin could not be opened. Retry, or export its design file to keep a copy.";
  } finally {
    finishDesignMutation();
    restoreEditor?.();
    SP.renderBinRecovery();
  }
};

SP.discardBinRecovery = async entry => {
  // Remove stored copies before hiding the entry. A failed deletion remains
  // visible and retryable, rather than reappearing without explanation later.
  entry.discarding = true;
  try {
    if (entry.tier === "space") {
      const target = SP._binRecoveryTargets.get(entry.spaceId);
      if (!target) throw new Error("Space unavailable");
      await SP.flushOutgoingResumeCheckpoint();
      await SP._writeResumeCheckpointNow(target, SP._binRecoveryBase.get(entry.spaceId), false);
    }
    if (entry.browserCopy) localStorage.removeItem(SP.BIN_RECOVERY_PREFIX + entry.id);
    SP._binRecovery.delete(entry.id);
    SP._binRecoveryNotices.delete(entry.id);
  } catch (_error) {
    entry.message = "This saved copy could not be discarded. Try Discard again.";
  } finally {
    entry.discarding = false;
    SP.renderBinRecovery();
  }
};

SP.renderBinRecovery = () => {
  const host = $("#ws-stage");
  if (!host) return;
  let panel = $("#bin-recovery-notes");
  if (!panel) {
    panel = document.createElement("section");
    panel.id = "bin-recovery-notes";
    panel.className = "ws-links";
    panel.setAttribute("aria-label", "Set-aside bins");
    host.appendChild(panel);
  }
  const entries = [...SP._binRecovery.values()].filter(entry =>
    entry.spaceId === state.activeSpaceId || SP._binRecoveryNotices.has(entry.id));
  const signature = JSON.stringify(entries.map(entry => [entry.id, entry.tier, entry.message, entry.spaceId === state.activeSpaceId]));
  if (panel.dataset.signature === signature) return;
  panel.dataset.signature = signature;
  panel.replaceChildren();
  for (const entry of entries) {
    const row = document.createElement("div");
    const note = document.createElement("p");
    note.setAttribute("role", "status");
    const place = entry.tier === "space" ? "in its Space" : entry.tier === "browser"
      ? "in this browser's recovery storage" : "only in this session";
    note.textContent = `${entry.binName} was set aside because it could not be saved, ${place}. It belongs to ${entry.spaceName}.`;
    if (entry.tier === "memory") note.textContent += " It could not be saved anywhere. It is kept only until the app closes or this page reloads. Retry save or export its design file to keep it.";
    row.appendChild(note);
    const action = (label, run) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "button secondary dl-small";
      button.textContent = label;
      button.disabled = Boolean(entry.busy);
      button.onclick = async () => {
        if (entry.busy) return;
        entry.busy = true;
        row.querySelectorAll("button").forEach(one => { one.disabled = true; });
        try { await run(); }
        catch (_error) { entry.message = "That action could not finish. Try again, or export the design file."; }
        finally {
          entry.busy = false;
          row.querySelectorAll("button").forEach(one => { one.disabled = false; });
          SP.renderBinRecovery();
        }
      };
      row.appendChild(button);
    };
    if (entry.spaceId === state.activeSpaceId) action("Open set-aside bin", () => SP.openBinRecovery(entry));
    action("Retry save", () => SP.saveBinRecovery(entry));
    action("Export design file", () => SP.exportBinRecovery(entry));
    action("Discard", () => SP.discardBinRecovery(entry));
    if (entry.message) {
      const message = document.createElement("p");
      message.textContent = entry.message;
      row.appendChild(message);
    }
    panel.appendChild(row);
  }
};

// ------------------------------------------------ exact resume checkpoint
//
// A typed Space's exact-design resume checkpoint (Fix 032). One coalescing
// slot, not a per-Space queue: SP.applyFolder always flushes whatever is
// queued/in-flight for the outgoing Space before it changes state.output/
// state.activeSpaceId (see SP.flushOutgoingResumeCheckpoint below), so only
// one Space is ever actively queuing at a time - Space A and Space B are
// never coalesced into the same slot, and a stale Space-A completion is
// still gated by identity before it is allowed to overwrite in-memory state.
SP._resume = {
  latest: null,          // { target, design, pending, key, waiters } - queued, unsent
  inFlight: null,         // the write currently in progress, if any
  savedKey: new Map(),   // space_id -> dedupe key of the last value actually saved
};

// A queued item a background save is about to replace, discarded before it
// was ever written under its own content, tells whoever was waiting on it
// (an explicit SP.flushResumeCheckpoint() caller) rather than leaving it
// hanging silently - see Correction 1.
SP._rejectSupersededWaiters = () => {
  const waiters = SP._resume.latest?.waiters;
  if (!waiters?.length) return;
  const error = new Error("a newer design replaced this save before it was written");
  waiters.forEach(w => w.reject(error));
};

// Captured synchronously, before any await - never resolved from mutable
// global state after a wait, so a queued write always targets the exact
// Space that owned the design when it was queued.
SP._captureResumeTarget = () => {
  if (state.folderMode !== "space" || !state.activeSpace || !state.activeSpaceId) return null;
  return {
    spaceId: state.activeSpaceId,
    // Cloned so the queued target is immutable - a later in-place edit to
    // state.activeSpace (e.g. a rename/resize) must not retroactively
    // change what an already-queued write sends (Fix 032 Correction 2,
    // item 9).
    space: clone(state.activeSpace),
    output: state.output,
    browserFolder: state.browserFolder,
    hosted: Boolean(state.runtime.hosted),
    designEpoch: window.WFLocalAPI?.designEpoch,
    previewRequest: state.previewRequest,
  };
};

SP._resumeMatchesActive = target =>
  state.folderMode === "space" && state.activeSpaceId === target.spaceId &&
  target.browserFolder === state.browserFolder &&
  target.designEpoch === window.WFLocalAPI?.designEpoch &&
  target.previewRequest === state.previewRequest;

SP._writeResumeCheckpointNow = async (target, design, pending) => {
  // Recovery entries share the existing raw, identity-checked checkpoint
  // transaction. They never pass through design validation/normalization.
  design = SP.withBinRecovery(target, design);
  if (target.hosted) {
    // A missing captured folder handle must throw, not silently resolve as
    // though the design were saved - an explicit flush must never mark
    // itself/its dedupe key successful when nothing was actually written
    // (Fix 032 Correction 2, item 10).
    if (!target.browserFolder?.handle) {
      throw new Error("This Space has no writable folder access in this browser session.");
    }
    // preserveSpace/expectedSpaceId: this transaction owns only the resume
    // fields, never the Space definition - never write back the possibly-
    // stale target.space captured when this write was queued, and never
    // recreate a Space under a new id if it disappeared/changed identity in
    // the meantime (Fix 032 Correction 4, C4.1).
    await SP.writeMetadata(target.browserFolder.handle, "space", null, true, {
      resume_design: design, resume_pending: pending,
    }, { preserveSpace: true, expectedSpaceId: target.spaceId });
  } else {
    // space_id lets the local /api/space/resume route refuse to write if
    // this Space is no longer the one on disk at that output path, instead
    // of writing into whatever Space is there now (Fix 032 Correction 4,
    // C4.1).
    await api("/api/space/resume", {
      output: target.output, space_id: target.spaceId,
      resume_design: design, resume_pending: pending,
    });
  }
  SP._binRecoveryBase.set(target.spaceId, SP.withoutBinRecovery(design));
  const recovered = design?.[SP.BIN_RECOVERY_FIELD] || [];
  for (const saved of recovered) {
    const entry = SP._binRecovery.get(saved.id);
    if (entry) entry.tier = "space";
  }
  if (recovered.length) SP.renderBinRecovery();
};

SP._pumpResumeQueue = () => {
  if (SP._resume.inFlight) return SP._resume.inFlight;
  const item = SP._resume.latest;
  if (!item) return Promise.resolve();
  SP._resume.latest = null;
  SP._resume.inFlight = SP._writeResumeCheckpointNow(item.target, item.design, item.pending)
    .then(() => {
      SP._resume.savedKey.set(item.target.spaceId, item.key);
      // The file write for an outgoing Space may finish after a switch;
      // that is fine. Adopting it into memory only when that Space is still
      // active is what stops a late completion overwriting a newer Space's
      // in-memory checkpoint.
      if (SP._resumeMatchesActive(item.target)) {
        state.spaceResumeDesign = clone(item.design);
        state.spaceResumePending = item.pending;
      }
      item.waiters.forEach(w => w.resolve());
    })
    .catch(error => {
      // A rejected write must not poison the tail - the queue recovers so
      // later writes still run. A background autosave has no waiter, so
      // this generic toast is its only report; an explicit
      // SP.flushResumeCheckpoint() caller instead gets its own rejection
      // through its waiter, and OWNS the user-facing message from there -
      // reporting both here and at the caller would duplicate/contradict
      // it (Fix 032 Correction 2, C2.3). The same ownership hand-off
      // applies when an explicit flush is already queued up BEHIND this
      // failing background write for the same Space (e.g. the preview
      // autosave that immediately precedes a Surface first-bin flush) -
      // that upcoming call owns the one warning, so stay silent here too
      // (Fix 032 Correction 3, C3.3).
      const nextOwnsMessage = Boolean(SP._resume.latest?.waiters.length);
      if (!item.waiters.length && !nextOwnsMessage) {
        toast(`The current design could not be saved to this Space: ${error.message}`, true, 6000);
      }
      item.waiters.forEach(w => w.reject(error));
    })
    .then(() => {
      SP._resume.inFlight = null;
      if (SP._resume.latest) return SP._pumpResumeQueue();
    });
  return SP._resume.inFlight;
};

// Background autosave choke point - call only after a fully valid preview
// (see refreshPreview in web/app.js). Coalesces with whatever is already
// queued for the same Space and skips an exact duplicate of the last value
// actually saved for it. Fire-and-forget: never blocks the caller, and a
// failure is reported as its own toast, not thrown.
SP.queueResumeCheckpoint = (design, pending) => {
  if (state.relocating) return;
  const target = SP._captureResumeTarget();
  if (!target) return;
  const key = `${pending ? 1 : 0}:${JSON.stringify(design)}`;
  if (!SP._resume.inFlight && !SP._resume.latest && SP._resume.savedKey.get(target.spaceId) === key) return;
  if (SP._resume.latest?.target.spaceId === target.spaceId && SP._resume.latest.key === key) return;
  SP._rejectSupersededWaiters();
  SP._resume.latest = { target, design: clone(design), pending: Boolean(pending), key, waiters: [] };
  SP._pumpResumeQueue();
};

// Explicit/deterministic persistence for Generate/Print and for leaving a
// Space. Unlike the background autosave path, this one is observable: it
// rejects if the exact requested checkpoint could not be durably saved, so
// its caller (Generate/Print) can refuse to proceed, or to report itself
// fully complete, on that specific failure - see Correction 1. It never
// poisons the shared queue - other pending/future writes still run.
SP.flushResumeCheckpoint = (design, pending) => {
  const target = SP._captureResumeTarget();
  if (!target) return Promise.resolve();
  const key = `${pending ? 1 : 0}:${JSON.stringify(design)}`;
  return new Promise((resolve, reject) => {
    SP._rejectSupersededWaiters();
    SP._resume.latest = {
      target, design: clone(design), pending: Boolean(pending), key,
      waiters: [{ resolve, reject }],
    };
    SP._pumpResumeQueue();
  });
};

// Waits out whatever is queued/in-flight before SP.applyFolder changes
// state.output/state.activeSpaceId to a different folder/Space. Best-effort:
// a failure here already toasted itself via the queue and must not block
// the folder switch the user asked for.
SP.flushOutgoingResumeCheckpoint = () => SP._pumpResumeQueue();

// ------------------------------------------------ Space preference memory (Fix 053)
//
// A typed Space always remembers its last-used bin and per-kind part settings
// in `bin_defaults` / `part_defaults`. Every write is a serialized transaction
// that names the Space it was queued for (captured synchronously, like the
// resume checkpoint), so a late write can never land in a Space the user has
// since left. Queued-but-unstarted writes for the same Space coalesce.
SP._defaults = { chain: Promise.resolve(), tail: null };

SP._writeDefaultsNow = async (target, changes) => {
  const updates = {};
  if (Object.hasOwn(changes, "bin_defaults")) updates.bin_defaults = changes.bin_defaults;
  if (Object.hasOwn(changes, "part_defaults")) updates.part_defaults = changes.part_defaults;
  if (!Object.keys(updates).length) return;
  if (target.hosted) {
    if (!target.browserFolder?.handle) {
      throw new Error("This Space has no writable folder access in this browser session.");
    }
    await SP.writeMetadata(target.browserFolder.handle, "space", null, true, updates, {
      preserveSpace: true, expectedSpaceId: target.spaceId,
    });
  } else {
    await api("/api/space/defaults", {
      output: target.output, space_id: target.spaceId, ...updates,
    });
  }
};

SP.queueDefaults = changes => {
  if (state.relocating) return;
  const target = SP._captureResumeTarget();
  if (!target) return;
  const queue = SP._defaults;
  const last = queue.tail;
  if (last && !last.started && last.target.spaceId === target.spaceId) {
    last.changes = { ...last.changes, ...changes };
    return;
  }
  const item = { target, changes: { ...changes }, started: false };
  queue.tail = item;
  queue.chain = queue.chain.then(async () => {
    item.started = true;
    if (queue.tail === item) queue.tail = null;
    try {
      await SP._writeDefaultsNow(item.target, item.changes);
    } catch (error) {
      toast(`This bin was saved, but the Space's remembered settings were not: ${error.message}`, true, 6000);
    }
  });
};

// Resolves once everything queued so far has been written (a failure already
// toasted itself and never blocks leaving a bin or Space).
SP.flushDefaults = () => SP._defaults.chain;

