"use strict";

// ------------------------------------------------------------ safe Drawer/Space switch (Fix 019 Item 2)
//
// Folder identity must never change until leaving the current Drawer layout
// either succeeds or the user deliberately discards it. Fix 034 K1: autosave
// has no off state any more, so this always just flushes a dirty layout and
// ABORTS the switch (old Space stays active, DL.layout/DL.dirty stay intact)
// if that save fails - never an ambiguous native confirm().

// Resolves true when it is safe to proceed (nothing dirty, or a successful
// flush) and false when the switch must be aborted with everything -
// including DL.layout/DL.dirty - left exactly as it was.
SP.leaveDrawerLayoutSafely = async ({ noDeferredPreview = false } = {}) => {
  if (typeof flushSpaceDesignAutosave === "function" &&
      !(await flushSpaceDesignAutosave({ deferDraftPreview: true, noDeferredPreview }))) return false;
  if (SP._inventoryWriteChain) await SP._inventoryWriteChain;
  if (typeof DL === "undefined") return true;
  if (DL.savePromise) {
    const ok = await DL.savePromise;
    if (!ok && DL.dirty) {
      toast(`Could not switch Spaces: ${DL.saveError || "the layout failed to save."}`, true, 6000);
      return false;
    }
  }
  if (!DL.dirty || !DL.layout || !DL.output) return true;
  const ok = await DL.save();
  if (!ok) {
    toast(`Could not switch Spaces: ${DL.saveError || "the layout failed to save."}`, true, 6000);
    return false;
  }
  return true;
};

// Fix 103 (R6): the one settle/leave owner for an unsaved structural draft.
// Resolves true when nothing is dirty, or after Save Changes succeeded, or
// after the user chose Discard; resolves false for Keep Editing or a failed
// Save (the structural editor stays mounted and dirty). Structural Save itself
// never calls this - it commits straight through the cabinet / Space owners.
SP.confirmLeaveStructuralEditor = async () => {
  if (typeof structuralEditorDirty !== "function" || !structuralEditorDirty()) return true;
  const what = structuralTargetKind() === "box" ? "case" : "cabinet";
  const choice = await appConfirm({
    title: "Save Changes?",
    message: `You changed this ${what}'s settings and have not saved them.`,
    primaryLabel: "Save Changes",
    secondaryLabel: "Discard",
    secondaryDanger: true,
    cancelLabel: "Keep Editing",
  });
  if (choice === "primary") return structuralSaveChanges();
  if (choice === "secondary") return structuralDiscardDraft();
  return false;
};

// Every Space/folder identity exit settles a structural draft first, then the
// Drawer layout. (The cabinet mutation controller keeps calling
// SP.leaveDrawerLayoutSafely directly.)
SP.leaveSpaceSafely = async options => {
  if (!(await SP.confirmLeaveStructuralEditor())) return false;
  return SP.leaveDrawerLayoutSafely(options);
};

// Returns true once it is safe for the caller to change folder/Space
// identity, false when the switch was aborted (a failed save, or the user
// choosing Cancel) - in which case DL.layout/DL.dirty are left untouched.
SP.resetDrawer = async ({ skipSafeLeave = false } = {}) => {
  if (typeof DL === "undefined") return true;
  if (!skipSafeLeave || DL.savePromise || DL.dirty) {
    const ok = await SP.leaveSpaceSafely();
    if (!ok) return false;
  }
  // A different folder means a different Space: close the workspace first.
  DL.busyTicket += 1;
  DL.busy = "";
  if (typeof DP !== "undefined" && DP.leave) DP.leave();
  DL.loadEpoch += 1;
  DL.loadPromise = null;
  DL.layout = null;
  DL.dirty = false;
  DL.loaded = false;
  DL.exists = false;
  DL.bins = [];
  DL.file = "";
  DL.warnings = [];
  DL.report = null;
  DL.reportTicket += 1;
  DL.selected = null;
  DL.selectedRow = null;
  DL.output = null;
  DL.pegboardLayouts = {};
  DL.pegboardRefreshError = "";
  DL.saveState = "idle";
  DL.saveError = "";
  DL.history = [];
  DL.future = [];
  DL.clearSpacerPlan();
  if (typeof DP !== "undefined") DP.printSelected = new Set();
  if (typeof DP !== "undefined") DP.signatures = {};
  return true;
};

// Folder/Space identity and persisted Space defaults only - see
// SP.initializeDesignForActiveSpace below for the (separate) Current-design
// activation this triggers whenever the newly-applied folder is a typed
// Space (Fix 019 Item 1). Resolves false without changing anything when a
// dirty Drawer layout blocked the switch (see SP.resetDrawer above).
//
// The single owner of the ENTIRE frontend folder/Space identity transition,
// including state.browserFolder (Fix 032 Correction 2, C2.1). No caller may
// assign state.browserFolder itself before calling in here - an old Space's
// preview finishing during that window could otherwise capture its id/
// design paired with the new Space's folder handle. Pass `browserFolder`
// only from a hosted caller that has one to hand over.
SP.applyFolder = async (info, options = {}) => {
  const { reset = true, initDesign = true } = options;
  if (reset) {
    const ok = await SP.resetDrawer();
    if (!ok) return false;
  }
  // Any preview still in flight belongs to the OUTGOING Space/folder.
  // Invalidate it before the resume flush/identity switch below - its own
  // stale-request guard (`request !== state.previewRequest`) is what stops
  // a late Space-A response from landing into the now-active Space-B
  // state.design and getting persisted as B's checkpoint (Fix 032
  // Correction 3, C3.1). cancelPreviewWait() also explicitly hides any
  // visible "recalculating" notice/overlay (not just its timers - Fix 032
  // Correction 4, C4.3), so a cancelled Space-A preview cannot leave a
  // stale overlay showing in Space B.
  state.previewRequest += 1;
  cancelPreviewWait();
  // The old Space's queued/in-flight resume checkpoint must land before ANY
  // identity field below changes - a completion for it after the switch
  // must never write into, or overwrite in memory, the new Space's
  // checkpoint.
  await SP.flushOutgoingResumeCheckpoint();
  // Everything from here through setFolderState() is one synchronous block
  // with no intervening await, so nothing can ever observe a half-migrated
  // identity (e.g. the new state.browserFolder paired with the old
  // state.activeSpaceId).
  if (Object.hasOwn(options, "browserFolder")) state.browserFolder = options.browserFolder;
  state.output = info.folder;
  state.activeSpaceId = info.space_id || null;
  state.cabinetRecovery = info.cabinet_recovery || null;
  state.folderSelected = true;
  // A manually-built `info` that omits these fields (e.g. hosted
  // SP.create()'s constructed object) must not let the outgoing Space's
  // in-memory checkpoint leak into the new one - absence normalizes to
  // explicit null/false, never "preserve whatever is already there".
  const resumeDesign = Object.hasOwn(info, "resume_design") ? info.resume_design : null;
  const resumePending = Object.hasOwn(info, "resume_pending") ? info.resume_pending : false;
  setFolderState(
    info.folder_mode,
    info.space,
    info.inventory,
    info.keep_bin_defaults,
    info.bin_defaults,
    info.part_defaults,
    resumeDesign,
    resumePending,
  );
  if (initDesign && info.folder_mode === "space") await SP.initializeDesignForActiveSpace();
  syncForm();
  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  return true;
};

