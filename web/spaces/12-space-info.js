"use strict";

// Recovery uses B09's validated export/import format, never browser-handle transfer.
SP.showBrowserRecovery = () => {
    let dialog = document.getElementById("browser-recovery-dialog");
    if (dialog) { dialog.showModal(); return; }
    dialog = document.createElement("dialog");
    dialog.id = "browser-recovery-dialog";
    dialog.className = "support-layout-dialog";
    dialog.setAttribute("aria-label", "Space and preferences recovery");
    dialog.innerHTML = `<h2>Space / preferences recovery</h2>
      <p>Open this same site in Windows desktop Chrome/Edge and choose your original folder to resume. Handles and browser data do not transfer automatically between browsers, profiles or origins.</p>
      <p>Or export a Space/preferences file here and import it in a supported browser. Restore a Space into an empty folder; existing files are never overwritten. Without writable folder access, use only temporary previews and downloads, with no Space autosave.</p>
      <div class="button-row"><button type="button" data-recovery="space-export" class="button secondary">Export current Space</button><button type="button" data-recovery="preferences-export" class="button secondary">Export preferences</button></div>
      <label>Choose recovery JSON <input type="file" accept="application/json,.json" data-recovery-file></label>
      <div class="button-row"><button type="button" data-recovery="space-import" class="button secondary">Restore Space to empty folder</button><button type="button" data-recovery="preferences-import" class="button secondary">Import preferences</button></div>
      <p role="status" data-recovery-status></p><button type="button" data-recovery-close class="button primary">Close</button>`;
    document.body.append(dialog);
    const note = dialog.querySelector('[data-recovery-status]');
    let busy = false;
    const fileInput = dialog.querySelector('[data-recovery-file]');
    const close = dialog.querySelector('[data-recovery-close]');
    close.onclick = () => dialog.close();
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.querySelectorAll('[data-recovery]').forEach(button => button.addEventListener('click', async () => {
        if (busy) return;
        const action = button.dataset.recovery;
        if (action.endsWith('import') && !WFFileSystem.supportsDirectoryPicker()) {
            note.textContent = 'Import Space/preferences exports in Windows desktop Chrome/Edge on the same site. This browser cannot save a Space; nothing was written.';
            return;
        }
        const file = fileInput.files[0];
        if (action.endsWith('import') && !file) { note.textContent = 'Choose a recovery JSON file first.'; return; }
        if (action.endsWith('import') && file.size > 256 * 1024 * 1024) { note.textContent = 'The recovery file exceeds 256 MB.'; return; }
        // Spend the explicit Restore click's activation before imports/reads.
        const picked = action === 'space-import' ? WFFileSystem.pickDirectory() : null;
        busy = true;
        for (const control of dialog.querySelectorAll('button,input')) control.disabled = true;
        note.textContent = 'Working…';
        try {
            const folderChoice = picked ? await picked : null;
            if (picked && folderChoice?.status !== 'ok') { note.textContent = 'Folder selection cancelled or access unavailable. Nothing was restored.'; return; }
            if (action.endsWith('export')) {
                const value = action === 'space-export'
                    ? await (await import('/browser-core/space-store.js')).exportSpace()
                    : await (await import('/browser-core/preferences.js')).exportPreferences();
                await WFFileSystem.writeBlob(null, action === 'space-export' ? 'Wavefinity Space.json' : 'Wavefinity preferences.json',
                    new Blob([JSON.stringify(value)], { type: 'application/json' }));
                note.textContent = 'Recovery export downloaded. Keep it somewhere safe on your PC.';
            } else {
                const backup = JSON.parse(await file.text());
                if (action === 'preferences-import') {
                    await (await import('/browser-core/preferences.js')).importPreferences(backup);
                    await (await import('/browser-core/ai-providers.js')).aiConnection({ action: 'clear' });
                    note.textContent = 'Preferences imported. Reload to apply all settings; enter your provider key again for direct AI.';
                } else {
                    const folder = { handle: folderChoice.handle, name: folderChoice.handle.name };
                    if (!(await SP.leaveSpaceSafely())) { note.textContent = 'Restore cancelled. Nothing was written.'; return; }
                    await (await import('/browser-core/space-store.js')).importSpace(backup, folder);
                    note.textContent = 'Space restored to the selected folder. Choose that folder from Open Space to resume.';
                }
            }
        } catch (error) { note.textContent = friendlyError(error); }
        finally {
            busy = false;
            for (const control of dialog.querySelectorAll('button,input')) control.disabled = false;
        }
    }));
    dialog.showModal();
};
document.addEventListener('click', event => {
    if (event.target.closest('[data-browser-recovery]')) SP.showBrowserRecovery();
});

// Story 2658: New Bin sits beside New Space while the Space header's button row is
// showing. The header is hidden with no active Space and while Space edit is open,
// so the same element goes back to the front of the Bin actions row then.
SP.placeNewBin = () => {
    const newBin = document.getElementById("designer-new-bin");
    const newSpace = document.getElementById("space-head-new-space");
    const binActions = document.getElementById("bin-actions");
    if (!newBin || !newSpace || !binActions) return;
    const head = document.getElementById("space-head");
    const viewing = document.getElementById("space-head-view");
    const headShowing = Boolean(head && !head.hidden && viewing && !viewing.hidden);
    if (headShowing) {
        if (newSpace.nextElementSibling !== newBin) newSpace.after(newBin);
    } else if (newBin.parentElement !== binActions) {
        binActions.prepend(newBin);
    }
};

SP.renderSpaceInfo = () => {
    SP.renderSpaceInfoBody();
    SP.placeNewBin();
    renderOutputReport();
};

SP.renderSpaceInfoBody = () => {
    const isSpace = state.folderMode === "space" && state.activeSpace;
    if (SP.actionSpaceSeen !== state.activeSpaceId) {
        SP.actionSpaceSeen = state.activeSpaceId;
        SP.deleteSpaceId = null;
        document.getElementById("space-delete-confirm").hidden = true;
        SP.spaceActionNote("");
    }
    // Story 2519: the Storage Box action presence follows the contents on every render.
    SP.syncStorageBoxBinActions();
    const saveEl = document.getElementById("save-location-row");
    if (saveEl) saveEl.hidden = Boolean(isSpace);

    // The one place a Space's identity is shown and edited: name, type and
    // size at the top left, read-only until Edit is chosen.
    const head = document.getElementById("space-head");
    if (!head) return;
    if (!isSpace) {
        head.hidden = true;
        SP.cancelInlineEdit();
        return;
    }
    head.hidden = false;
    const viewing = document.getElementById("space-head-view");
    if (viewing) viewing.hidden = SP.editing && !(typeof WS !== "undefined" && WS.task === "settings");
    document.getElementById("space-head-name").textContent = state.activeSpace.name;

    const kind = state.activeSpace.kind;
    const kindLabel = SP_KINDS[kind]?.label || kind;
    document.getElementById("space-head-type").textContent = kindLabel;

    // New Space is offered for every typed Space, not only Drawer.
    const btnNew = document.getElementById("space-head-new-space");
    if (btnNew) btnNew.hidden = false;

    const btnShow = document.getElementById("space-head-show");
    if (btnShow) btnShow.hidden = state.runtime.hosted;
    const btnHooks = document.getElementById("space-pegboard-hooks");
    if (btnHooks) {
        btnHooks.hidden = kind !== "pegboard";
        btnHooks.disabled = SP.pegboardHooksBusy;
    }
    SP.renderStructuralActions();
    SP.updateCabinetWorkspace?.();
    // Fix 103: a mounted structural editor follows the accepted Space.
    if (typeof syncStructuralEditor === "function") syncStructuralEditor();
};

SP.showFolder = async () => {
    if (!state.output || state.runtime.hosted) return;
    const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
    const isWin = navigator.platform.toUpperCase().indexOf("WIN") >= 0;
    const fm = isMac ? "Finder" : (isWin ? "File Explorer" : "your file manager");
    // Not destructive - ordinary primary/secondary styling, not danger.
    const ok = await appConfirmAction({
      title: "Open Space Folder?",
      message: `Open this Space folder in ${fm}?`,
      actionLabel: "Open Folder",
    });
    if (!ok) return;
    try {
        await api("/api/space/show-folder", { output: state.output });
    } catch (e) {
        toast("Failed to open folder: " + friendlyError(e), true);
    }
};

SP.editSpace = () => {
    if (!state.activeSpace || SP.editing || SP.spaceActionBusy) return;
    SP.showSetup(state.activeSpace.kind === "box" ? "portable" : state.activeSpace.kind, state.activeSpace, { update: true });
};

SP.spaceActionNote = message => {
    const note = document.getElementById("space-action-status");
    note.textContent = message;
    note.hidden = !message;
};

SP.hostedActionParent = async folder => {
    let parent = (SP.hostedHome || await WFFileSystem.load("home"))?.handle;
    let path = parent ? await parent.resolve(folder.handle) : null;
    if (!path || path.length !== 1) {
      SP.spaceActionNote("Choose the folder containing this Space to continue.");
      const picked = await WFFileSystem.pickDirectory();
      if (picked.status === "cancelled") return null;
      if (picked.status !== "ok") throw new Error("Folder access was not granted.");
      parent = picked.handle;
      path = await parent.resolve(folder.handle);
    }
    if (!path || path.length !== 1) throw new Error("Choose the folder directly containing this Space. Nothing was changed.");
    return { parent, entry: path[0] };
};

SP.runSpaceAction = async action => {
    if (!state.activeSpace || SP.spaceActionBusy || (typeof WS !== "undefined" && WS.busy)) return;
    SP.spaceActionBusy = true;
    const context = DL.spaceContext();
    const spaceId = state.activeSpaceId;
    if (typeof WS !== "undefined") WS.busy = true;
    const buttons = [...document.querySelectorAll("#space-actions button, #space-delete-confirm button")];
    const disabled = buttons.map(button => button.disabled);
    buttons.forEach(button => { button.disabled = true; });
    const form = document.getElementById("space-form");
    form.inert = true;
    try {
      if (!(await SP.flushSetupAutosave()) || !(await SP.leaveSpaceSafely())) return;
      DL.requireSpaceContext(context);
      await SP.flushOutgoingResumeCheckpoint();
      if (state.runtime.hosted) {
        const folder = state.browserFolder;
        const location = await SP.hostedActionParent(folder);
        if (!location) { SP.spaceActionNote(""); return; }
        const { parent, entry } = location;
        DL.requireSpaceContext(context);
        const source = await SP.inspectHosted(folder);
        if (source.space_id !== spaceId) throw new Error("This is no longer the open Space. Nothing was changed.");
        const perform = async () => {
          await WFFileSystem.removeDirectory(parent, entry);
          SP.recent = (await SP.loadHostedRecent()).filter(one => one.space_id !== spaceId);
          await SP.saveHostedRecent(SP.recent);
          await WFFileSystem.save("active", null);
        };
        const pending = SP._inventoryWriteChain.then(perform, perform);
        SP._inventoryWriteChain = pending.catch(() => {});
        await pending;
      } else {
        const result = await api("/api/space/delete", { output: state.output, space_id: spaceId });
        SP.recent = result.recent || [];
        if (result.other_spaces) SP.otherSpaces = result.other_spaces;
      }
      DL.requireSpaceContext(context);
      document.getElementById("space-delete-confirm").hidden = true;
      SP.deleteSpaceId = null;
      SP.cancelInlineEdit();
      await SP.resetDrawer({ skipSafeLeave: true });
      SP.resetDesignSession();
      state.output = ""; state.browserFolder = null; state.activeSpaceId = null;
      state.folderSelected = false;
        setFolderState("design", null, false, false, null, {});
        SP.otherSpaces = (SP.otherSpaces || []).filter(one => one.space_id !== spaceId);
        SP.otherSpacesFresh = false;
        SP.spaceActionNote("");
        SP.renderSpaceInfo();
      if (typeof WS !== "undefined") {
        WS.task = "picker"; WS.prior = null; WS.message = "";
      } else SP.showHome();
    } catch (error) {
      SP.spaceActionNote(friendlyError(error));
    } finally {
      SP.spaceActionBusy = false;
      form.inert = false;
      buttons.forEach((button, i) => { button.disabled = disabled[i]; });
      if (typeof WS !== "undefined") { WS.busy = false; WS.sync(); }
    }
};

SP.newSpace = async () => {
    if (!state.activeSpace || (SP.editing && !(await SP.flushSetupAutosave()))) return;

    const template = clone(state.activeSpace);
    if (template.kind === "box") template.kind = "portable";
    template.name = "";

    // Clear stale folder/collision/edit state first, then install only the
    // read-only repeat-size template for the type chooser.
    SP.clearSetupContext();
    SP.setupPrefillSpace = template;
    SP.showTypeCards();
};

// Pegboard Spaces only: one plate of printable hooks for the board's standard,
// saved through the same generate/save path as every other generated file.
SP.pegboardHooksBusy = false;
SP.printPegboardHooks = async () => {
    if (SP.pegboardHooksBusy || state.activeSpace?.kind !== "pegboard") return;
    if (state.runtime.hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
    const context = DL.spaceContext();
    const payload = {
        standard: state.activeSpace.pegboard_standard,
        thickness_mm: state.activeSpace.pegboard_thickness_mm ?? 3.2,
        count: 4,
        output: state.output,
    };
    SP.pegboardHooksBusy = true;
    SP.renderSpaceInfo();
    try {
        const result = await apiSideEffect("/api/pegboard/hooks", payload);
        DL.requireSpaceContext(context);
        const saved = await saveGeneratedFiles(result, { kind: "pegboard_hooks" });
        DL.requireSpaceContext(context);
        const names = [...new Set(saved.map(file => String(file).split(/[\\/]/).pop()))];
        toast(`Saved Pegboard hooks to ${result.output || state.output}${names.length ? "\n" + names.join("\n") : ""}`, false, 7000);
    } catch (error) {
        if (DL.isStaleSpaceError(error)) {
            toast("Pegboard hooks finished for the Space you left. Nothing was changed in the current Space.");
        } else {
            toast(error.message, true, 8000);
        }
    } finally {
        SP.pegboardHooksBusy = false;
        SP.renderSpaceInfo();
    }
};

// Wire the Space Info Edit/Show Folder/New Space buttons for one
// prefix only, so the normal Design controls (wired once at startup) and
// the Drawer panel's dynamically-built copy (wired once when DP.build()
// creates it) never both attach a listener to the same button - see
// Fix 004 Correction 6.M.
const wireInfoButtons = (prefix = "space-head") => {
    const btnOpen = document.getElementById(prefix + "-open");
    if (btnOpen) btnOpen.addEventListener("click", SP.openLaunchSelection);
    const btnEdit = document.getElementById(prefix + "-edit");
    if (btnEdit) btnEdit.addEventListener("click", SP.editSpace);
    if (prefix === "space-head") {
      document.getElementById("space-head-delete")?.addEventListener("click", () => {
        if (!state.activeSpace || SP.spaceActionBusy) return;
        SP.deleteSpaceId = state.activeSpaceId;
        document.getElementById("space-delete-message").textContent =
          `Delete “${state.activeSpace.name}”? The Space and all its bins will be deleted. There is no undo.`;
        document.getElementById("space-delete-confirm").hidden = false;
      });
      document.getElementById("space-delete-cancel")?.addEventListener("click", () => {
        document.getElementById("space-delete-confirm").hidden = true;
        SP.deleteSpaceId = null;
      });
      document.getElementById("space-delete-yes")?.addEventListener("click", () => {
        if (SP.deleteSpaceId === state.activeSpaceId) SP.runSpaceAction("delete");
      });
    }
    const btnPrinterSettings = document.getElementById(prefix + "-printer-settings");
    if (btnPrinterSettings) btnPrinterSettings.addEventListener("click", SP.openPrinterSettings);
    const btnShow = document.getElementById(prefix + "-show");
    if (btnShow) btnShow.addEventListener("click", SP.showFolder);
    const btnNew = document.getElementById(prefix + "-new-space");
    if (btnNew) btnNew.addEventListener("click", SP.newSpace);
    const btnHooks = document.getElementById("space-pegboard-hooks");
    if (btnHooks) btnHooks.addEventListener("click", SP.printPegboardHooks);
    const btnSave = document.getElementById("space-structural-save");
    if (btnSave) btnSave.addEventListener("click", SP.saveStructural);
    const btnPrint = document.getElementById("space-structural-print");
    if (btnPrint) btnPrint.addEventListener("click", SP.printStructural);
    const drawerBin = document.getElementById("designer-make-drawer-bin");
    if (drawerBin && prefix === "space-head") drawerBin.addEventListener("click", async () => {
      const context = DL.spaceContext(), drawerId = DL.layout?.active;
      if (!DL.isStorageDrawers() || SP.drawerBinContents() !== "empty") return;
      const confirmed = await appConfirmAction({
        title: "Create one full-size inside bin?",
        message: "This creates one bin sized to fill the drawer's available interior, so other bins cannot be placed beside it.",
        actionLabel: "Continue", cancelLabel: "Cancel",
      });
      if (!confirmed || !DL.spaceContextCurrent(context) || DL.layout?.active !== drawerId ||
          SP.drawerBinContents() !== "empty") return;
      await designerMakeInsideBin();
    });
    const btnMakeInsideBin = document.getElementById("space-make-inside-bin");
    if (btnMakeInsideBin) btnMakeInsideBin.addEventListener("click", async () => {
      const context = DL.spaceContext();
      const confirmed = await appConfirmAction({
        title: "Create one full-size inside bin?",
        message: "This creates one bin sized to fill the Storage Box's available interior, so other bins cannot be placed beside it.",
        actionLabel: "Continue", cancelLabel: "Cancel",
      });
      if (!confirmed || !DL.spaceContextCurrent(context) || SP.structuralKind() !== "storage_box") return;
      await designerMakeInsideBin();
    });
};

// Printed bins that still follow the Surface edge (Auto base) and would keep their
// old physical base when the trim preset changes the edge height.
SP.printedAutoBaseRows = trimSize => {
    const presets = SP.surfacePresetMap();
    const oldEdge = presets[state.activeSpace?.trim_size];
    const newEdge = presets[trimSize];
    if (!Number.isFinite(oldEdge) || !Number.isFinite(newEdge) || Math.abs(oldEdge - newEdge) <= 1e-9) return [];
    const specs = DL.layout?.design_specs || {};
    return (DL.bins || []).filter(one =>
      one.status === "printed" && specs[one.id]?.layout?.surface_base_mode === "edge");
};

SP.confirmPrintedAutoBases = async trimSize => {
    const rows = SP.printedAutoBaseRows(trimSize);
    if (!rows.length) return true;
    const names = rows.slice(0, 5).map(one => DL.label(one));
    const shown = names.join(", ") + (rows.length > 5 ? ` and ${rows.length - 5} more` : "");
    return appConfirmAction({
      title: "Printed bins will keep their current base height",
      message: `${shown} ${rows.length === 1 ? "is" : "are"} already printed and will remain at ${rows.length === 1 ? "its" : "their"} existing base height while the Base Trim changes. Bins not yet printed that follow the Surface edge will use the new trim.`,
      actionLabel: "Continue", cancelLabel: "Cancel",
    });
};

SP.setupAutosaveRevision = 0;
SP.setupSavedRevision = 0;
SP.setupAutosaveChain = Promise.resolve(true);
SP.queueSetupAutosave = () => {
    if (!SP.isUpdate || !SP.editing) return;
    SP.setupAutosaveRevision += 1;
    clearTimeout(SP.setupAutosaveTimer);
    SP.setupAutosaveTimer = setTimeout(() => { SP.setupAutosaveTimer = null; void SP.flushSetupAutosave(); }, 350);
};
SP.flushSetupAutosave = () => {
    clearTimeout(SP.setupAutosaveTimer);
    SP.setupAutosaveTimer = null;
    const run = async () => {
      while (SP.isUpdate && SP.editing && SP.setupSavedRevision !== SP.setupAutosaveRevision) {
        const revision = SP.setupAutosaveRevision;
        const values = SP.setupKind === "storage_drawers"
          ? await SP.readSetupValues() : SP.readOrdinarySetupValues({ focus: false });
        // Validation can await a server response while the user keeps editing.
        // Re-read the latest draft before committing or reporting an error.
        if (revision !== SP.setupAutosaveRevision) continue;
        if (!values) return false;
        try {
          const { kind, name, x, y, z, extra = {} } = values;
          if (kind === "storage_drawers") {
            const updated = await SP.mutateCabinet("reconfigure", {
              space: { kind, name, x, y, z, ...extra },
            });
            if (!updated) return false;
            if (revision === SP.setupAutosaveRevision) SP.storageDrawersForm?.markPristine?.();
          } else {
            const updated = await SP.commitSpaceUpdate(values, { structural: true });
            if (updated === false) return false;
          }
          SP.setupSavedRevision = revision;
          if (revision === SP.setupAutosaveRevision) SP.setupFormSnapshot = SP.captureOrdinarySetupSnapshot();
          SP.renderSpaceInfo();
        } catch (error) {
          if (revision !== SP.setupAutosaveRevision) continue;
          const message = friendlyError(error);
          if (SP.setupChangedField && !message.includes("no longer fit at this size")) {
            SP.setupFieldNote(SP.setupChangedField, message, "error");
            $(SP.setupChangedField)?.setAttribute("aria-invalid", "true");
          } else SP.fail(message);
          return false;
        }
      }
      return true;
    };
    const pending = SP.setupAutosaveChain.then(run, run);
    SP.setupAutosaveChain = pending.catch(() => false);
    return pending;
};
SP.updateSpace = () => SP.flushSetupAutosave();

// The ordinary (non-cabinet) Space update, shared by the setup form and the
// structural Storage Box editor (Fix 103). `structural` skips the setup-form
// chrome (inline edit teardown, toast) and the ordinary-bin preview refresh;
// the structural editor reports and previews for itself.
SP.commitSpaceUpdate = async (values, { structural = false } = {}) => {
    const { kind, name, x, y, z, trimSize, extra = {} } = values;
    const context = typeof DL !== "undefined" ? DL.spaceContext() : null;
    const requireCurrent = () => { if (context) DL.requireSpaceContext(context); };
    // Fix 095: the one confirmation happens before anything is committed; Cancel
    // leaves the Surface and its Inventory exactly as they were.
    if (kind === "surface" && typeof DL !== "undefined" && DL.loaded) {
        if (!(await SP.confirmPrintedAutoBases(trimSize))) return false;
        requireCurrent();
    }
    if (typeof DL !== "undefined" && DL.loaded && !(await DL.save())) {
        throw new Error("Save the current Space layout before changing its size or case settings.");
    }
    requireCurrent();

    if (state.runtime.hosted) {
        // Hosted Space updates join the normal Inventory-write serialization
        // chain (SP._inventoryWriteChain, owned by SP.inventoryRequest) so a
        // concurrent hosted Inventory write cannot interleave with this one.
        const hostedUpdateRun = async () => {
        // Mirror local update semantics: the inventory's own layout.space is
        // authoritative on reopen, so it must be updated together with
        // metadata, through the same backend validation as local Edit -
        // see Fix 004 Correction 7.E.
        const folder = state.browserFolder;
        const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
        requireCurrent();
        const result = await api("/api/space/configure-text", {
          inventory_text: inventoryText, inventory_title: name,
          name, kind: state.activeSpace.kind, x, y, z, ...extra,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        requireCurrent();
        // The server validated the whole proposed Surface before returning this text,
        // so nothing has been written yet. If the metadata write then fails, put the
        // previous Inventory text back rather than leave a half-applied resize.
        const inventoryName = SP.inventoryFilenameFor(folder);
        await WFFileSystem.writeText(folder.handle, inventoryName, result.inventory_text);
        const space = result.layout.space;
        let metadata;
        try {
          requireCurrent();
          // This call owns the new Space definition (just written above), but
          // not the bin/part defaults - reading them here and passing them
          // back would be exactly the stale pre-lock capture Correction 4
          // eliminates; leaving them unset lets the serialized writer read
          // the newest value from under its own lock instead (C4.1).
          metadata = await SP.writeMetadata(folder.handle, "space", space, true, {});
        } catch (error) {
          try { await WFFileSystem.writeText(folder.handle, inventoryName, inventoryText); }
          catch (_restore) { /* the folder is no longer writable; nothing more can be done */ }
          throw error;
        }
        requireCurrent();
        state.activeSpace = space;
        state.activeSpaceId = metadata.space_id || null;
        await SP.rememberHostedRecent(folder, { folder_mode: "space", space, space_id: metadata.space_id });
        };
        const hostedUpdatePending = SP._inventoryWriteChain.then(hostedUpdateRun, hostedUpdateRun);
        SP._inventoryWriteChain = hostedUpdatePending.catch(() => {});
        await hostedUpdatePending;
    } else {
        const data = await api("/api/space/update", {
          output: state.output, name: name, x: x, y: y, z: z, ...extra,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        requireCurrent();
        state.activeSpace = data.folder.space;
        SP.recent = data.recent || SP.recent;
    }
    SP.setupFormSnapshot = null;
    if (!structural) {
        SP.cancelInlineEdit();
        toast("Space updated.");
    }
    
    if (kind === "surface" && typeof DL !== "undefined" && DL.loaded) {
        await DL.load();
        requireCurrent();
        DL.clearSpacerPlan();
        if (typeof isSurfaceBinDesign === "function" && isSurfaceBinDesign()) {
            const source = DL.layout?.design_specs?.[state.designInventoryId];
            if (source?.layout?.surface_base_mode === "custom")
                state.design.layout.surface_base_mode = "custom";
            if (typeof resolveSurfaceBase === "function") resolveSurfaceBase(state.design);
            if (typeof syncForm === "function") syncForm();
            if (typeof refreshPreview === "function") await refreshPreview();
        }
    }
    if (kind === "portable") {
        if (typeof DL !== "undefined" && DL.loaded) {
            await DL.load();
            requireCurrent();
        }
        if (!structural && typeof refreshPreview === "function") await refreshPreview();
    }
    if ((kind === "drawer" || kind === "pegboard") && typeof DL !== "undefined" && DL.loaded) {
        await DL.load();
        requireCurrent();
    }
};



