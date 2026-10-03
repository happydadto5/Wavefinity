"use strict";

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
  };
};

SP._resumeMatchesActive = target =>
  state.folderMode === "space" && state.activeSpaceId === target.spaceId;

SP._writeResumeCheckpointNow = async (target, design, pending) => {
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
  if (SP._resume.savedKey.get(target.spaceId) === key) return;
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

