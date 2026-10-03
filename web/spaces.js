"use strict";

// ------------------------------------------------------------ Storage Drawers (Fix 084B)
//
// Thin adapters only: the cabinet's rules, planning, geometry and UI live in the
// StorageDrawers / StorageDrawersForm / StorageDrawersWorkspace / PrinterProfile
// modules and the server's Storage Drawers owners. Nothing here plans a cabinet.

SP.ensureStorageDrawersRules = () => {
  const catalog = state.catalog;
  if (SP._sdRulesCatalog === catalog) return;
  StorageDrawers.configureRules(catalog);
  SP._sdRulesCatalog = catalog;
};

SP.storageDrawersSummaryText = space => {
  try {
    SP.ensureStorageDrawersRules();
    const [x, y] = StorageDrawers.unitCounts(space);
    const count = StorageDrawers.drawerDescriptors(space).length;
    return `${count} ${count === 1 ? "drawer" : "drawers"} · ${fmt(x)} × ${fmt(y)} units each`;
  } catch (_error) {
    return "";
  }
};

// ---- Create / Edit form host

SP.destroyStorageDrawersForm = () => {
  SP.storageDrawersForm?.destroy();
  SP.storageDrawersForm = null;
  for (const id of ["space-create", "space-save-changes"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = false;
  }
};

// ---- dirty setup guard

SP.setupIsDirty = () => {
  if (SP.setupKind === "storage_drawers") {
    return Boolean(SP.storageDrawersForm?.isDirty?.());
  }
  if (SP.setupFormSnapshot === null) return false;
  return SP.captureOrdinarySetupSnapshot() !== SP.setupFormSnapshot;
};

SP.confirmDiscardSetup = async () => {
  if (!SP.setupIsDirty()) return true;
  const cabinet = SP.setupKind === "storage_drawers";
  return appConfirmAction({
    title: cabinet ? "Discard Cabinet Changes?" : "Discard Space Changes?",
    message: cabinet
      ? "You changed this cabinet's settings and have not saved them. Discard the changes?"
      : "You changed this Space's setup and have not saved it. Discard the changes?",
    actionLabel: "Discard Changes",
    cancelLabel: "Keep Editing",
    danger: true,
  });
};

SP.requestClose = async () => {
  if (!(await SP.confirmDiscardSetup())) return;
  SP.close();
};

SP.mountStorageDrawersForm = (prefill, update) => {
  SP.destroyStorageDrawersForm();
  const primaryButton = document.getElementById(update ? "space-save-changes" : "space-create");
  if (primaryButton) primaryButton.disabled = true;
  const host = document.getElementById("space-fields-storage_drawers");
  try {
    SP.ensureStorageDrawersRules();
  } catch (error) {
    // Fail closed: no form is built from rules that are not published.
    const note = document.createElement("p");
    note.className = "sd-field-error"; note.textContent = friendlyError(error);
    host.replaceChildren(note);
    return;
  }
  let initial = null;
  if (prefill?.kind === "storage_drawers") {
    initial = clone(prefill);
    if (!update && !SP.setupPreserveIds) {
      // A repeat-size template never inherits the old cabinet's drawer identities.
      initial.storage_drawers.drawers = initial.storage_drawers.drawers.map(row => ({
        temp_key: `temporary:${crypto.randomUUID()}`, height_mm: row.height_mm, label_text: row.label_text || "",
      }));
    }
  }
  const createToken = crypto.randomUUID();
  SP.storageDrawersForm = StorageDrawersForm.mount({
    host,
    initialSpace: initial,
    catalog: state.catalog,
    printerProfile: PrinterProfile.current(),
    mode: update ? "edit" : "create",
    scope: update ? "full" : "basic",
    callbacks: {
      identity: () => update ? (state.activeSpaceId || state.activeSpace?.name) : createToken,
      openPrinterSettings: () => SP.openPrinterSettings(),
      requestSummary: ({ space, printer_profile }) => api("/api/space/storage-drawers-summary", {
        space, ...(state.runtime.hosted ? { printer_profile } : {}),
      }, { timeoutMs: 15000 }),
    },
    onReadyChange: ready => { if (primaryButton) primaryButton.disabled = !ready; },
  });
};

SP.readStorageDrawersSetup = async () => {
  const form = SP.storageDrawersForm;
  let result = form?.read();
  if (!result) {
    SP.fail("Storage Drawers settings are not ready.", "#space-create");
    return null;
  }
  if (!result.ok && result.pending && typeof form.whenValidationSettled === "function") {
    // The live cabinet check was still in flight when Create/Save was
    // clicked: wait for it to settle, then read once more, instead of
    // failing with a confusing "Checking cabinet…" message.
    SP.fail("Checking the cabinet — one moment…", "#space-create");
    await form.whenValidationSettled(30000);
    document.getElementById("space-error").hidden = true;
    result = form.read();
    if (!result) {
      SP.fail("Storage Drawers settings are not ready.", "#space-create");
      return null;
    }
    if (!result.ok && result.pending) {
      SP.fail("The cabinet check is taking too long. Check your connection and try again.", "#space-create");
      return null;
    }
  }
  if (!result.ok) {
    SP.fail(result.message, result.focusId ? `#${result.focusId}` : "#space-create");
    return null;
  }
  const draft = result.spaceDraft;
  return {
    kind: "storage_drawers", name: draft.name, x: draft.x, y: draft.y, z: draft.z, trimSize: null,
    extra: { storage_drawers: draft.storage_drawers },
  };
};

// ---- serialized cabinet mutation (Add / Delete / Edit-reconfigure)

SP._cabinetController = null;
SP._releaseCabinet = null;

SP.cabinetController = () => {
  if (!SP._cabinetController) {
    SP._cabinetController = StorageDrawers.createMutationController({
      captureContext: () => DL.spaceContext(),
      settleLayout: async () => {
        if (!(await SP.leaveDrawerLayoutSafely())) throw new Error("Save the current layout before changing the cabinet.");
      },
      isCurrent: context => DL.spaceContextCurrent(context),
      // From here until the result is adopted, ordinary layout saves wait.
      advanceLayoutEpoch: () => {
        DL.cabinetMutationEpoch += 1;
        DL.cabinetMutating = new Promise(resolve => { SP._releaseCabinet = resolve; });
      },
      mutate: (operation, payload) => SP.cabinetMutate(operation, payload),
      adopt: result => SP.adoptCabinetResult(result),
    });
  }
  return SP._cabinetController;
};

SP.mutateCabinet = async (operation, payload = {}) => {
  try {
    return await SP.cabinetController().run(operation, payload);
  } finally {
    if (SP._releaseCabinet) {
      const release = SP._releaseCabinet;
      SP._releaseCabinet = null;
      DL.cabinetMutating = null;
      release();
    }
  }
};

SP.cabinetMutate = async (operation, { drawer_id = null, space = null } = {}) => {
  if (!state.runtime.hosted) {
    return apiSideEffect("/api/space/storage-drawers-mutate", {
      output: state.output, space_id: state.activeSpaceId, operation, drawer_id, space,
    });
  }
  // Hosted twin: the browser folder is the transaction owner.
  const folder = state.browserFolder;
  const spaceId = state.activeSpaceId;
  const filename = SP.inventoryFilenameFor(folder);
  const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
  const { current } = await SP.readMetadata(folder.handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw new Error("This folder is not the Space that was open before. Nothing was changed.");
  }
  if (meta.cabinet_recovery && operation !== "reset") {
    throw new Error(`Reset cabinet settings before changing the cabinet. ${meta.cabinet_recovery.message}`);
  }
  const result = await apiSideEffect("/api/space/storage-drawers-mutate-text", {
    inventory_text: inventoryText, inventory_title: meta.space.name, operation, drawer_id,
    // Reset rebuilds from the folder's stored (damaged) definition.
    space: operation === "reset" ? current.data?.space : space,
  });
  await WFFileSystem.writeText(folder.handle, filename, result.inventory_text);
  try {
    await SP.writeMetadata(folder.handle, "space", result.space, true, {}, { expectedSpaceId: spaceId });
  } catch (error) {
    await WFFileSystem.writeText(folder.handle, filename, inventoryText);
    throw error;
  }
  return result;
};

SP.adoptCabinetResult = result => {
  const keepRow = DL.selectedRow;
  state.activeSpace = result.space;
  DL.adopt(result);
  DL.normaliseLayout(result.layout);
  state.cabinetRecovery = null;
  DL.reconcileCabinet();
  DL.history = [];
  DL.future = [];
  DL.dirty = false;
  DL.selected = null;
  // Keep the row selected only when it still exists and physically lives in
  // the reconciled active drawer (or is unplaced). Otherwise the Inventory
  // highlight and the drawer on screen would name different drawers.
  const holder = keepRow && DL.bin(keepRow) ? StorageDrawers.drawerHoldingRow(DL.layout, keepRow) : null;
  DL.selectedRow = keepRow && DL.bin(keepRow) && (!holder || holder === DL.layout.active) ? keepRow : null;
  DL.saveState = "saved";
  DL.prune();
  DL.clearSpacerPlan();
  SP.cabinetInfo.key = "";
  DL.emit();
  DL.requestReport();
  if (typeof DV !== "undefined") DV.fit();
  SP.renderSpaceInfo();
};

// Resolves true only when the change was adopted into the current Space, so a
// caller (the structural editor) knows whether to rebuild from the new Space.
SP.cabinetAdd = async () => {
  try {
    // The controller resolves null for a stale or superseded result, so success
    // is announced only when it was adopted into the same current Space.
    if (await SP.mutateCabinet("add")) { toast("Drawer added."); return true; }
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 6000);
  }
  return false;
};

SP.cabinetDelete = async drawerId => {
  const rows = StorageDrawers.drawerDescriptors(state.activeSpace);
  const index = rows.findIndex(row => row.id === drawerId);
  if (index < 0 || rows.length <= 1) return false;
  if (DL.layout.drawers.find(one => one.id === drawerId)?.placements?.length) {
    toast(`Empty Drawer ${index + 1} before deleting it.`, true, 5000);
    return false;
  }
  const ok = await appConfirmAction({
    title: `Delete Drawer ${index + 1}?`,
    message: `Delete Drawer ${index + 1}? It is removed from the cabinet.`,
    actionLabel: "Delete Drawer",
    danger: true,
  });
  if (!ok) return false;
  try {
    return Boolean(await SP.mutateCabinet("delete", { drawer_id: drawerId }));
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 6000);
    return false;
  }
};

SP.resetCabinetSettings = async () => {
  const problem = state.cabinetRecovery?.message || "A cabinet setting is not valid.";
  const ok = await appConfirmAction({
    title: "Reset Cabinet Settings?",
    message: `${problem}\n\nWavefinity keeps every drawer that is still valid and replaces only what is damaged with current defaults. Your Inventory and bin designs are not changed.`,
    actionLabel: "Reset Cabinet Settings",
  });
  if (!ok) return;
  try {
    if (await SP.mutateCabinet("reset")) toast("Cabinet settings were reset.");
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 8000);
  }
};

// ---- workspace navigator (mounted into the Space canvas host)

SP.cabinetInfo = { key: "", summary: null, status: null, commitSerial: 0 };
SP.cabinetWorkspace = null;

SP.cabinetJumpToRow = async rowId => {
  if (!DL.isStorageDrawers() || !SP.cabinetWorkspace) return false;
  return SP.cabinetWorkspace.jumpToInventoryRow(rowId);
};

SP.cabinetCallbacks = () => ({
  addDrawer: () => SP.cabinetAdd(),
  deleteDrawer: drawerId => SP.cabinetDelete(drawerId),
  resetCabinet: () => SP.resetCabinetSettings(),
  openPrinterSettings: () => SP.openPrinterSettings(),
  saveCabinet: () => SP.runStructural("save"),
  printCabinet: event => SP.runStructural("print", event),
  printCabinetAndBins: event => SP.printCabinetAndBins(event),
  setActiveDrawer: async id => {
    DL.change(() => { DL.layout.active = id; }, { history: false });
    DL.selected = null;
    DL.emit();
  },
  clearCanvasPlacementSelection: () => { DL.selected = null; DL.emit(); },
  selectedRow: () => DL.selectedRow,
  clearSelectedRow: () => { DL.selectedRow = null; DL.emit(); },
  selectRow: rowId => DL.selectRow(rowId),
  revealPlacement: rowId => { DL.selectRow(rowId); DV.revealRow(rowId); },
  reframeCamera: () => DV.fit(),
});

SP.updateCabinetWorkspace = () => {
  const host = document.getElementById("sd-workspace-host");
  if (!host) return;
  const active = state.folderMode === "space" && DL.isStorageDrawers() && Boolean(DL.layout);
  host.hidden = !active;
  if (!active) {
    SP.cabinetWorkspace?.destroy();
    SP.cabinetWorkspace = null;
    return;
  }
  try {
    SP.ensureStorageDrawersRules();
    const data = {
      space: state.activeSpace, layout: DL.layout, editing: Boolean(SP.editing),
      structuralStatus: SP.cabinetInfo.status, summary: SP.cabinetInfo.summary,
      printer: PrinterProfile.current(), recovery: state.cabinetRecovery || null,
    };
    if (!SP.cabinetWorkspace) {
      SP.cabinetWorkspace = StorageDrawersWorkspace.mount({ host, state: data, callbacks: SP.cabinetCallbacks() });
    } else {
      SP.cabinetWorkspace.update(data);
    }
    // Hosted Wavefinity has no local slicer: both Print actions stay disabled, never a Save.
    const printButtons = [".sd-print", ".sd-print-both"]
      .map(selector => host.querySelector(selector))
      .filter(Boolean);
    if (state.runtime.hosted && printButtons.length) {
      for (const printButton of printButtons) {
        printButton.disabled = true;
        printButton.title = SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP;
      }
      // Fix 096 F9: visible reason beside the disabled buttons, not only a tooltip.
      let reason = host.querySelector(".sd-print-reason");
      if (!reason) {
        reason = document.createElement("p");
        reason.className = "sd-help sd-print-reason";
        printButtons[printButtons.length - 1].after(reason);
      }
      reason.textContent = "Printing is unavailable on hosted Wavefinity: there is no local slicer here.";
    }
    if (!state.cabinetRecovery) SP.refreshCabinetStructural();
  } catch (error) {
    console.error("Storage Drawers workspace", error);
  }
};

// The cabinet's fit summary and saved-file status. Local status comes from the
// real files on disk; hosted status is recomputed from the committed browser
// manifest and the actual files in the chosen folder - never from a server temp.
SP.refreshCabinetStructural = async () => {
  if (!DL.isStorageDrawers() || !state.activeSpace || state.cabinetRecovery) return;
  const hosted = Boolean(state.runtime.hosted);
  const profile = PrinterProfile.current();
  const key = JSON.stringify([state.activeSpace, profile, state.activeSpaceId, SP.cabinetInfo.commitSerial]);
  if (SP.cabinetInfo.key === key) return;
  SP.cabinetInfo = { ...SP.cabinetInfo, key };
  try {
    const result = await api("/api/space/structural-design", {
      space: clone(state.activeSpace),
      ...(hosted ? { printer_profile: profile } : { output: state.output, space_id: state.activeSpaceId }),
    });
    if (SP.cabinetInfo.key !== key) return;
    SP.cabinetInfo.summary = result.summary;
    SP.cabinetInfo.status = hosted ? await SP.hostedCabinetStatus(result.signature, result.orientations) : result.status;
  } catch (error) {
    if (SP.cabinetInfo.key !== key) return;
    if (error.code === "CABINET_RECOVERY") {
      // An interrupted save that cannot be settled is a cabinet-recovery
      // problem, never "changed outside Wavefinity".
      SP.cabinetInfo.status = { status: "recovery_error", message: error.message };
    } else {
      SP.cabinetInfo.summary = { fits_printer: false, first_fit_error: error.message };
      SP.cabinetInfo.status = { status: "need_save" };
    }
  }
  if (SP.cabinetInfo.key === key) SP.updateCabinetWorkspace();
};

SP.hostedCabinetStatus = async (signature, orientations = null) => {
  const handle = state.browserFolder?.handle;
  if (!handle) return { status: "need_save" };
  if (SP._hostedCabinetSaving) return SP.cabinetInfo.status || { status: "need_save" };
  // A journal left by an interrupted save is settled first: committed leftovers
  // are cleaned, anything else is rolled back, before ownership is compared.
  await SP.recoverHostedCabinetJournal(handle, state.activeSpaceId);
  const { current } = await SP.readMetadata(handle);
  const manifest = SP.classifyMetadata(current).structural_outputs?.storage_drawers;
  const rows = manifest?.components;
  if (!Array.isArray(rows) || !rows.length || rows.some(one => typeof one?.filename !== "string" || typeof one?.sha256 !== "string")) {
    return { status: "need_save" };
  }
  if (manifest.signature !== signature) return { status: "need_update" };
  for (const component of rows) {
    if ((await WFFileSystem.sha256(handle, component.filename)) !== component.sha256) return { status: "need_save" };
  }
  if (orientations && rows.some(one => one.orientation !== orientations[one.key])) return { status: "need_update" };
  return { status: "saved" };
};

// ---- structural Save / Print for the cabinet

// (Fix 096 C7) Print Cabinet + Bins: the cabinet and every placed bin under
// one truthful preflight (the backend runs C6's blocking predicate literally)
// and one slicer handoff. Hosted stays unavailable: it has no local slicer.
SP.printCabinetAndBins = async event => {
  if (SP.structuralBusy) return;
  // A dirty structural Design draft must be settled before output is
  // manufactured from the accepted Space: Save Changes, Discard, or the
  // output stays blocked while the user keeps editing.
  if (!(await SP.confirmLeaveStructuralEditor())) return;
  const hosted = Boolean(state.runtime.hosted);
  if (hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer was not found. Use Change slicer in Design to locate Bambu Studio or OrcaSlicer.", true, 8000);
    return;
  }
  const context = DL.spaceContext();
  const savedName = state.activeSpace?.name || "the cabinet";
  const savedWhere = state.output;
  let wroteFiles = false;
  const names = files => [...new Set((files || []).map(file => String(file?.name || file).split(/[\\\\/]/).pop()))].join("\\n");
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    DL.requireSpaceContext(context);
    if (typeof flushSpaceDesignAutosave === "function" &&
        !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
    DL.requireSpaceContext(context);
    if (!(await DL.save())) return;
    DL.requireSpaceContext(context);
    const result = await apiSideEffect("/api/space/structural-print-combined", {
      space: clone(state.activeSpace),
      output: state.output, space_id: state.activeSpaceId,
      slicer_path: state.slicer?.path || null,
    });
    wroteFiles = true;
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) {
      toast(result.error || "Cabinet + bins files were saved, but the slicer did not open.", true, 8000);
    } else {
      toast(`Sent to ${state.slicer?.name || "Bambu Studio"}!\\n${names(result.files)}`, false, 7000);
    }
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast(wroteFiles
        ? `Cabinet + bins files for "${savedName}" were saved to ${savedWhere}. The Space you switched to was not changed.`
        : `You switched Spaces before "${savedName}" was saved, so nothing was written.`, false, 8000);
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.cabinetInfo.commitSerial += 1;
    SP.renderSpaceInfo();
  }
};
SP.runCabinetStructural = async mode => {
  if (SP.structuralBusy) return;
  // A dirty structural Design draft must be settled before output is
  // manufactured from the accepted Space: Save Changes, Discard, or the
  // output stays blocked while the user keeps editing.
  if (!(await SP.confirmLeaveStructuralEditor())) return;
  const hosted = Boolean(state.runtime.hosted);
  if (hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
  if (mode === "print" && hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (mode === "print" && !state.slicer?.available) {
    toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
    return;
  }
  const context = DL.spaceContext();
  const payload = {
    space: clone(state.activeSpace),
    ...(hosted ? { printer_profile: PrinterProfile.current() } : { output: state.output, space_id: state.activeSpaceId }),
  };
  // Remembered now, so a late completion can say exactly what it did and to whom.
  const savedName = state.activeSpace?.name || "the cabinet";
  const savedWhere = hosted ? (state.browserFolder?.name || "your chosen folder") : state.output;
  let wroteFiles = false;
  const names = files => [...new Set((files || []).map(file => String(file?.name || file).split(/[\\/]/).pop()))].join("\n");
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    let saved;
    if (mode === "print") {
      const result = await apiSideEffect("/api/space/structural-print", { ...payload, slicer_path: state.slicer?.path || null });
      wroteFiles = true;
      DL.requireSpaceContext(context);
      if (result.partial) {
        toast(result.error || "Cabinet files were saved, but the slicer did not open.", true, 8000);
      } else {
        toast(`Sent to ${state.slicer?.name || "the slicer"}!\n${names(result.files)}`, false, 7000);
      }
      saved = result;
    } else if (hosted) {
      saved = await SP.hostedCabinetSave(payload, context);
      wroteFiles = true;
      DL.requireSpaceContext(context);
      toast(`Saved cabinet files\n${names(saved.files)}${saved.warnings?.length ? `\n${saved.warnings.join("\n")}` : ""}`, false, 8000);
    } else {
      saved = await apiSideEffect("/api/space/structural-generate", payload);
      wroteFiles = true;
      DL.requireSpaceContext(context);
      toast(`Saved cabinet to ${saved.output || state.output}\n${names(saved.files)}${saved.warnings?.length ? `\n${saved.warnings.join("\n")}` : ""}`, false, 8000);
    }
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast(wroteFiles
        ? `Cabinet files for "${savedName}" were saved to ${savedWhere}. The Space you switched to was not changed.`
        : `You switched Spaces before "${savedName}" was saved, so nothing was written.`, false, 8000);
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.cabinetInfo.commitSerial += 1;
    SP.renderSpaceInfo();
  }
};

// ---- hosted durable save journal (Fix 086)
//
// The browser folder owns the hosted file transaction, and a closed tab or a
// crash must never leave it half done. Before any owned final is replaced, an
// app-owned journal (Space ID, prior and candidate manifests, filenames, backup
// filenames, newly-created filenames) and durable backups are written into the
// folder itself. The next hosted status or save settles the journal first.
SP.CABINET_JOURNAL = ".wavefinity-cabinet-journal.json";
SP.CABINET_BACKUP_PREFIX = ".wavefinity-cabinet-backup-";
SP.CABINET_BACKUP_NAME = /^\.wavefinity-cabinet-backup-[0-9a-f-]+-\d+\.3mf$/;

SP.cabinetRecoveryError = message =>
  Object.assign(new Error(`Cabinet recovery is needed: ${message}`), { code: "CABINET_RECOVERY" });

SP.removeIfPresent = async (handle, name) => {
  try { await WFFileSystem.removeFile(handle, name); }
  catch (error) { if (error?.name !== "NotFoundError") throw error; }
};

// Orphan app-owned backups only, and only when no journal is active.
SP.sweepHostedCabinetDebris = async handle => {
  for (const name of await WFFileSystem.listFilenames(handle)) {
    if (SP.CABINET_BACKUP_NAME.test(name)) {
      try { await WFFileSystem.removeFile(handle, name); } catch (_error) { /* left for the next sweep */ }
    }
  }
};

// A journal this tab is writing right now is a live transaction, not an
// interrupted one: only the save itself (`own`) may settle it.
SP._hostedCabinetSaving = false;

SP.recoverHostedCabinetJournal = async (handle, spaceId, { own = false } = {}) => {
  if (SP._hostedCabinetSaving && !own) return "busy";
  const text = await WFFileSystem.readText(handle, SP.CABINET_JOURNAL);
  if (text === null) {
    await SP.sweepHostedCabinetDebris(handle);
    return "none";
  }
  let journal;
  try {
    journal = JSON.parse(text);
    const valid = journal && journal.version === 1 && typeof journal.tx === "string" &&
      typeof journal.space_id === "string" && Array.isArray(journal.files) &&
      journal.candidate_manifest && typeof journal.candidate_manifest === "object" &&
      journal.files.every(file => file && typeof file.name === "string" && typeof file.created === "boolean" &&
        (file.created || (typeof file.backup === "string" && typeof file.original_sha256 === "string")));
    if (!valid) throw new Error("invalid journal");
  } catch (_error) {
    throw SP.cabinetRecoveryError(`the interrupted-save record in this folder (${SP.CABINET_JOURNAL}) is damaged. Check the cabinet files, then delete that file to continue.`);
  }
  if (journal.space_id !== spaceId) {
    throw SP.cabinetRecoveryError("an unfinished cabinet save in this folder belongs to a different Space.");
  }
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw SP.cabinetRecoveryError("this folder's Space could not be confirmed.");
  }
  const stored = meta.structural_outputs?.storage_drawers || null;
  const committed = Boolean(stored) && JSON.stringify(stored) === JSON.stringify(journal.candidate_manifest);
  if (!committed) {
    for (const file of journal.files) {
      if (file.created) {
        await SP.removeIfPresent(handle, file.name);
        continue;
      }
      const backup = await WFFileSystem.readBlob(handle, file.backup);
      if (backup) {
        if ((await WFFileSystem.sha256Blob(backup)) !== file.original_sha256) {
          throw SP.cabinetRecoveryError(`the backup of ${file.name} is damaged, so the original could not be restored.`);
        }
        await WFFileSystem.writeBlob(handle, file.name, new Blob([await backup.arrayBuffer()]));
      } else if ((await WFFileSystem.sha256(handle, file.name)) !== file.original_sha256) {
        throw SP.cabinetRecoveryError(`the original ${file.name} could not be restored.`);
      }
    }
  }
  for (const file of journal.files) {
    if (file.backup) await SP.removeIfPresent(handle, file.backup);
  }
  await SP.removeIfPresent(handle, SP.CABINET_JOURNAL);
  return committed ? "committed" : "rolled_back";
};

// Hosted Save Cabinet. Every candidate file is downloaded and verified first,
// only files this cabinet already owns (same bytes as its committed manifest)
// are replaced, and the manifest is committed only after every write succeeded.
// Any failure - or a lost tab - is settled from the durable journal.
SP.hostedCabinetSave = async (payload, context) => {
  const handle = state.browserFolder.handle;
  const spaceId = state.activeSpaceId;
  // Settle any earlier interrupted save before ownership is compared.
  await SP.recoverHostedCabinetJournal(handle, spaceId);
  const exported = await apiSideEffect("/api/space/structural-generate", payload);
  DL.requireSpaceContext(context);
  const candidate = exported.manifest;
  if (!candidate?.components?.length) throw new Error("The server did not return the cabinet files.");
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw new Error("This folder is not the Space that was open before. Nothing was changed.");
  }
  if (meta.cabinet_recovery) {
    throw new Error(`Reset cabinet settings before saving the cabinet. ${meta.cabinet_recovery.message}`);
  }
  const prior = meta.structural_outputs?.storage_drawers || null;
  const owned = new Map((Array.isArray(prior?.components) ? prior.components : []).map(one => [one.filename, one]));

  const blobs = new Map();
  for (const item of exported.files || []) {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error(`Could not download ${item.name}.`);
    blobs.set(item.name, await response.blob());
  }
  for (const component of candidate.components) {
    const blob = blobs.get(component.filename);
    if (!blob || (await WFFileSystem.sha256Blob(blob)) !== component.sha256) {
      throw new Error("A cabinet file did not download correctly. Nothing was changed.");
    }
  }
  for (const component of candidate.components) {
    const existing = await WFFileSystem.sha256(handle, component.filename);
    if (existing === null) continue;
    if (owned.get(component.filename)?.sha256 !== existing) {
      throw new Error(`${component.filename} changed outside Wavefinity; rename or move it before updating the cabinet.`);
    }
  }
  const txid = crypto.randomUUID();
  const entries = [];
  const backups = [];
  for (const [index, component] of candidate.components.entries()) {
    const old = await WFFileSystem.readBlob(handle, component.filename);
    if (old) {
      const bytes = new Blob([await old.arrayBuffer()]);
      const backup = `${SP.CABINET_BACKUP_PREFIX}${txid}-${index}.3mf`;
      entries.push({ name: component.filename, created: false, backup, original_sha256: await WFFileSystem.sha256Blob(bytes) });
      backups.push([backup, bytes]);
    } else {
      entries.push({ name: component.filename, created: true });
    }
  }
  SP._hostedCabinetSaving = true;
  try {
    // Durable backups first, then the journal that names them, then the installs.
    for (const [name, blob] of backups) await WFFileSystem.writeBlob(handle, name, blob);
    await WFFileSystem.writeText(handle, SP.CABINET_JOURNAL, JSON.stringify({
      version: 1, tx: txid, space_id: spaceId, prior_manifest: prior, candidate_manifest: candidate, files: entries,
    }));
    for (const component of candidate.components) {
      await WFFileSystem.writeBlob(handle, component.filename, blobs.get(component.filename));
    }
    await SP.writeMetadata(handle, "space", null, true, {
      structural_output_updates: { storage_drawers: candidate },
    }, { preserveSpace: true, expectedSpaceId: spaceId });
  } catch (error) {
    // Roll back from the same durable record a lost tab would have used.
    try { await SP.recoverHostedCabinetJournal(handle, spaceId, { own: true }); }
    catch (_recovery) { /* the journal stays; the next status or save settles it */ }
    SP._hostedCabinetSaving = false;
    throw error;
  }
  // Committed: only now are the backups, then the journal, cleaned.
  try {
    for (const [name] of backups) await SP.removeIfPresent(handle, name);
    await SP.removeIfPresent(handle, SP.CABINET_JOURNAL);
  } catch (_cleanup) { /* committed leftovers are cleaned by the next status or save */ }
  SP._hostedCabinetSaving = false;
  const warnings = [...(exported.warnings || [])];
  const desired = new Set(candidate.components.map(one => one.filename));
  for (const [name, old] of owned) {
    if (desired.has(name)) continue;
    try {
      const hash = await WFFileSystem.sha256(handle, name);
      if (hash === null) continue;
      if (hash === old.sha256) await WFFileSystem.removeFile(handle, name);
      else warnings.push(`${name} changed outside Wavefinity; left in place without cabinet ownership`);
    } catch (_error) {
      warnings.push(`Could not remove old cabinet file ${name}; remove it manually`);
    }
  }
  return { files: [...desired], warnings };
};

// Startup must come after every SP.* helper it (transitively) depends on -
// SP.wire, wireInfoButtons, SP.updateReadouts, SP.renderSpaceInfo,
// and everything SP.launch()/SP.wire() call - is defined,
// so this stays the very last thing in the file. state.ready can already be
// true by the time this script runs, which would otherwise call SP.wire()
// before it exists - see Fix 004 Correction 8.A.
const startSpaces = async () => {
  try {
    try { SP.ensureStorageDrawersRules(); } catch (_error) { /* catalog unavailable: validated lazily */ }
    await SP.initPrinterProfile();
    SP.wire();
    // The routing decision - saved folder / Welcome / Resume / setup - is
    // made first, behind the startup cover the initial HTML already shows.
    await SP.launch();
  } finally {
    // Single owner of successful cover dismissal, so the bare Design UI never
    // flashes between routing states - and an unexpected startup error can
    // never leave "Opening Wavefinity..." on screen forever.
    const cover = document.getElementById("startup-cover");
    if (cover) cover.hidden = true;
  }

  // Only now does the first preview begin, behind the correct screen -
  // unless Space activation during SP.launch() already started one for the
  // design it just installed (Fix 032 Correction 3, C3.2); firing this one
  // too would be a redundant duplicate of the same design/generation.
  // refreshPreview() discards stale responses, so a later user action wins.
  if (!SP._activationPreviewRequested) await refreshPreview();
};

// A Base Trim file changed outside Wavefinity is noticed when the window is used again.
window.addEventListener("focus", () => {
  if (SP.structuralKind() === "base_trim" && !SP.structuralBusy) SP.invalidateBaseTrimSummary();
});

if (state.ready) {
  startSpaces();
} else {
  window.addEventListener("wavefinity:ready", startSpaces, { once: true });
}
