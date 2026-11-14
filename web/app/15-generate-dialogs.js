"use strict";

function setGenerationPrinterWarning(message) {
  const node = $("#generation-printer-warning");
  node.textContent = message;
  node.hidden = !message;
}

// The parts dialog opens over the preview and NOT modal while files are
// made, so the tree, the views and the previews stay usable behind it (a
// 350 x 350 bin with a lid takes over a minute). Its own status line and the
// row's status line both show progress.
function openGenerationDialog(dialog) {
  if (!dialog || dialog.open) return;
  positionGenerationDialog(dialog);
  dialog.classList.add("is-docked");
  try {
    dialog.show();
  } catch (_err) {
    // Already open
  }
}

function positionGenerationDialog(dialog) {
  const preview = $(".workspace .canvas-wrap.active") || $(".workspace");
  const bounds = preview?.getBoundingClientRect();
  dialog.style.setProperty("--generation-left", `${(bounds?.left || 0) + 16}px`);
  dialog.style.setProperty("--generation-top", `${(bounds?.top || 0) + 16}px`);
}

window.addEventListener("resize", () => {
  const dialog = $("#generation-dialog.is-docked[open]");
  if (dialog) positionGenerationDialog(dialog);
});

// An Export already running for the bin being exported again: the second
// click joins it (no second request, no second file set) and says so in place.
function joinRunningExport() {
  const entry = currentOutputReport;
  if (!entry?.busy || entry.action !== "export" || entry.owner !== "bin") return false;
  if (String(entry.rowIds?.[0] || "") !== String(state.designInventoryId || "")) return false;
  const note = " · Your second Export click joined this one - nothing extra is made.";
  entry.joined = true;
  if (!entry.text.endsWith(note)) entry.text += note;
  renderOutputReport();
  return true;
}

// Use the existing item status area for Print and inventory batches as well as Export.
function beginGenerationReport(working, rows = [{ id: "bin", title: "Bin" }], batch = false) {
  const place = beginOutputReport(working, batch ? "batch" : "bin",
    batch ? rows.map(one => one.id) : [state.designInventoryId].filter(Boolean));
  const dialog = $("#generation-dialog");
  dialog.dataset.outputBusy = "true";
  if (!dialog.dataset.outputCancelWired) {
    dialog.dataset.outputCancelWired = "true";
    dialog.addEventListener("cancel", event => {
      if (dialog.dataset.outputBusy === "true") event.preventDefault();
    });
  }
  const context = DL.spaceContext();
  const items = rows.length ? rows : [{ id: "bin", title: "Parts" }];
  renderGenerationItems(items.map(one => ({ ...one, status: "generating", text: working })));
  $("#generation-dialog-title").textContent = working;
  $("#generation-dialog-subtitle").textContent = "";
  setGenerationPrinterWarning(batch ? "" : binPrinterWarning());
  $("#generation-error").hidden = true;
  $("#generation-actions").hidden = true;
  openGenerationDialog(dialog);
  let settled = false;
  const report = (message, error = false) => {
    settled = true;
    dialog.dataset.outputBusy = "false";
    place(message, error);
    const text = DL.spaceContextCurrent(context) ? message : `For the Space you left: ${message}`;
    for (const one of items) setItemStatus(one.id, error ? "error" : "done", text);
    $("#generation-dialog-title").textContent = error ? "Needs attention" : "Finished";
    $("#generation-actions").hidden = false;
  };
  report.working = message => {
    place.working(message);
    if (typeof DP !== "undefined" && DP.built) DP.renderInventory(true);
    for (const one of items) setItemStatus(one.id, "generating", message);
  };
  report.progress = message => {
    place.progress(message);
    for (const one of items) setItemStatus(one.id, "generating", message);
  };
  report.entry = place.entry;
  report.batchResult = (result, printing, folder) => {
    const files = outputResultFiles(result);
    const message = result.partial ? result.error || "Some files could not be prepared."
      : printing ? `Sent ${outputFileNames(files)} to ${state.slicer?.name || "the slicer"}`
        : `Saved files to ${folder}: ${outputFileNames(files)}`;
    report(message, Boolean(result.partial));
    if (result.partial) {
      for (const one of items) {
        const saved = result.saved_rows?.includes(one.id);
        const file = (result.bins || []).find(bin => bin.id === one.id)?.file;
        const status = saved ? `Files saved to ${folder}: ${file || ""}. ${printing ? "Print did not finish. " : ""}` : "";
        setItemStatus(one.id, saved ? "done" : "error", status + message);
      }
    }
  };
  report.options = { onStillFinishing: () => report.working("Still working…") };
  report.finish = () => { if (!settled) report("Action stopped before files were sent or saved.", true); };
  return report;
}

async function generateParts(target) {
  if (joinRunningExport()) return;
  if (state.designMutationBusy || isGenerating || currentOutputReport?.busy) return;
  const report = beginOutputReport("Exporting…");
  try {
    await generatePartsWithReport(target, report);
  } catch (error) {
    report(friendlyError(error), true);
  } finally {
    report.finish();
  }
}


async function generatePartsWithReport(target, report) {
  // Ordinary output entry points defensively reject structural ownership:
  // a Storage Box or Storage Drawers target has its own Save/Print chrome.
  if (designTargetIsStructural()) {
    report("These outputs are for ordinary bins. The structural editor has its own Save and Print actions.", true);
    return;
  }
  if (relocationBlocksWrites()) return;
  if (state.designMutationBusy || isGenerating) {
    report("Finish the current action before saving files.", true);
    return;
  }
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  const beforeForm = pendingPreEditDesign || clone(state.design);
  const previousCanGenerate = state.canGenerate;

  cancelChangedDesignDebounce();
  pendingPreEditDesign = null;

  if (!applyLiveFormWithModifierConflictGuard(beforeForm, previousCanGenerate)) {
    return;
  }

  if ((target === "all" || target === "bin") && !state.canGenerate) {
    report("Resolve the highlighted issue before saving.", true);
    return;
  }
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ materialize: target === "all" || target === "bin" }))) return;
  const designRowId = typedSpaceOrdinaryBin() ? state.designInventoryId : null;
  const designSpaceContext = designRowId ? DL.spaceContext() : null;
  setError();

  const dialog = $("#generation-dialog");
  const dialogTitle = $("#generation-dialog-title");
  const dialogSubtitle = $("#generation-dialog-subtitle");
  const dialogError = $("#generation-error");
  const dialogActions = $("#generation-actions");

  if (dialogTitle) dialogTitle.textContent = "Exporting…";
  if (dialogSubtitle) dialogSubtitle.textContent = "Please wait while your files are being saved.";
  setGenerationPrinterWarning((target === "all" || target === "bin") ? binPrinterWarning() : "");
  if (dialogError) {
    dialogError.hidden = true;
    dialogError.textContent = "";
  }
  if (dialogActions) {
    dialogActions.hidden = true;
  }

  const boxTitle = `Bin (${fmt(state.design.box.x)} × ${fmt(state.design.box.y)} × ${fmt(state.design.box.z)} mm)`;
  const connTitle = "Side Connector";

  const items = [];
  if (target === "all" || target === "bin") {
    items.push({ id: "bin", title: boxTitle, status: "generating", text: "Exporting…" });
  }
  if (target === "all" || target === "connector") {
    items.push({ id: "connector", title: connTitle, status: "waiting", text: "Waiting…" });
  }

  renderGenerationItems(items);

  isGenerating = true;
  state.designMutationBusy = true;
  setMutationSurfacesInert(true, { keepTree: true });
  updateGenerateAvailability();

  openGenerationDialog(dialog);

  const allFiles = [];
  let connectorPlan = null;
  let saveOutput = state.output;
  let checkpointSaveFailed = null;
  // Stage truth: once the bin is really saved, a later connector failure must
  // say so instead of presenting the whole action as failed.
  let saveStage = "setup";
  let binSaved = false;
  const outputFolder = state.browserFolder, outputSpace = state.activeSpaceId;
  let outputEpoch = null;
  const requireOutputContext = () => {
    if (state.browserFolder !== outputFolder || state.activeSpaceId !== outputSpace ||
        (outputEpoch !== null && WFLocalAPI.designEpoch !== outputEpoch) || state.relocating) {
      throw new Error("The Space or design changed before the files were saved.");
    }
  };

  try {
    // A debounced support edit may still be visible only in the draft. Save
    // it now so the exported files always match the canvas.
    await commitVisibleDraft();
    requireOutputContext();
    outputEpoch = WFLocalAPI.designEpoch;

    const payload = {
      design: clone(state.design),
      connector: state.connector,
      keep_log: !designRowId && Boolean(outputFolder?.handle) && state.keepLog,
      design_row_id: designRowId || undefined,
      printer_profile: PrinterProfile.current(),
      printer_profile_configured: PrinterProfile.configured(),
      // Fix 1069: carry the active Space so direct Save in a Storage Box Space
      // is hard-blocked when the bin/closed stack exceeds the interior Z.
      // Standalone designs (no Space) send null and are unaffected.
      space: state.folderMode === "space" ? (state.activeSpace ?? null) : null,
    };

    // Fix 032 Correction 1: flush the exact pre-operation resume checkpoint
    // before this design is sent anywhere. Pending is computed for this
    // exact payload now, not blindly forced true - a reprint of an already-
    // reconciled unchanged design stays reconciled. If this checkpoint
    // cannot be durably saved, the "recoverable on failure" guarantee is not
    // met - stop here rather than proceed as though it were.
    if (state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        throw new Error(`The current design could not be saved to this Space, so nothing was saved: ${error.message}`);
      }
    }

    // Generation's grid guard reads saved ownership, never a client path or
    // the editable Space object as proof. Capture after the resume flush.
    if (outputFolder?.handle) {
      payload.inventory_text = await SP.readInventoryFor(outputFolder, { migrate: false });
      payload.space_metadata_text = await WFFileSystem.readText(outputFolder.handle, FOLDER_METADATA);
      payload.space_id = outputSpace || undefined;
    }
    requireOutputContext();

    // Step 1: Generate Bin if requested
    if (target === "all" || target === "bin") {
      saveStage = "bin";
      setItemStatus("bin", "generating", "Exporting…");
      // Elapsed time from the click, the server's stage and estimate every
      // 2 s, in the row's status line and the dialog's bin line.
      const progress = startOutputProgress("Exporting…", text => {
        report.progress?.(text);
        setItemStatus("bin", "generating", text);
      }, report.entry);
      let binResult;
      try {
        binResult = await apiSideEffect("/api/generate", payload, {
          onStillFinishing: () => {}, onProgress: progress.update,
        });
      } finally {
        progress.stop();
      }
      saveOutput = binResult.output || saveOutput;
      const binFiles = await saveGeneratedFiles(binResult, {
        ownedStale: staleFileNamesForRow(designRowId), requireCurrent: requireOutputContext,
      });
      if (designSpaceContext) {
        DL.requireSpaceContext(designSpaceContext);
        if (state.designInventoryId !== designRowId ||
            JSON.stringify(state.design) !== JSON.stringify(payload.design))
          throw new Error("This bin changed while its files were being saved. Its status was not changed.");
        const names = [...new Set(binFiles.map(file => String(file).split(/[\\/]/).pop())
          .filter(name => /\.3mf$/i.test(name)))];
        if (!names.length) throw new Error("No current bin files were saved.");
        const saved = await DL.inventoryCall("/api/drawer/design-source/status", {
          row_id: designRowId, action: "saved", file: names.join(", "), design: payload.design,
        }, { context: designSpaceContext, sideEffect: true });
        DL.adopt(saved);
        DL.emit();
      }
      if (!designRowId && binResult.inventory_bin && state.inventoryEnabled && typeof SP !== "undefined") {
        await SP.addInventoryBin(binResult.inventory_bin, binResult.inventory_design_spec || null);
      }
      allFiles.push(...binFiles);
      binSaved = true;
      setItemStatus("bin", "done", binResult.downloaded_archive
        ? `Downloaded ${binResult.downloaded_archive} containing: ${binFiles.join(", ")}`
        : "Saved to " + (state.browserFolder?.name || "your download folder") + ": " + binFiles.join(", "));
      // The just-saved bin is the next resume target. The generated files and
      // inventory entry already exist by this point, so a checkpoint-save
      // failure here must not be reported as the generation itself
      // failing (Correction 1) - only that this design still needs saving
      // to the Space, which a later preview/action will retry.
      if (state.folderMode === "space" && typeof SP !== "undefined") {
        try {
          await SP.flushResumeCheckpoint(payload.design, false);
        } catch (error) {
          checkpointSaveFailed = error;
        }
      }
    }

    // Step 2: Generate Connector if requested
    if (target === "all" || target === "connector") {
      requireOutputContext();
      saveStage = "connector";
      setItemStatus("connector", "generating", "Exporting…");
      const connectorPayload = { ...payload, replace_existing_connectors: false };
      let connResult = await apiSideEffect("/api/connector", connectorPayload, { onStillFinishing: () => { report.working("Still working…"); setItemStatus("connector", "generating", "Still working…"); } });
      if (connResult.requires_connector_replace) {
        const names = connResult.conflict_files || [];
        if (!(await confirmReplaceConnectorFiles(names))) {
          throw new Error("Connector save cancelled. Nothing was replaced.");
        }
        connResult = await apiSideEffect("/api/connector", {
          ...connectorPayload,
          replace_existing_connectors: true,
        }, { onStillFinishing: () => { report.working("Still working…"); setItemStatus("connector", "generating", "Still working…"); } });
      }
      saveOutput = connResult.output || saveOutput;
      if (connResult.connector_plan) {
        connectorPlan = connResult.connector_plan;
        renderConnectorReadout(connResult.connector_plan);
      }
      const connFiles = await saveGeneratedFiles(connResult, { kind: "connector", requireCurrent: requireOutputContext });
      allFiles.push(...connFiles);
      if (connResult.partial) {
        // Some connectors were really written before a later one failed.
        setItemStatus("connector", "error", "Partly saved");
        const savedList = [...new Set(allFiles)];
        const message = `${binSaved ? "The bin was saved. " : ""}Some connector files were saved, but not all.\n${connResult.error || ""}`
          + `${savedList.length ? `\nSaved to ${saveOutput}\n${savedList.join("\n")}` : ""}`;
        setItemStatus("connector", "error", message);
        if (dialogTitle) dialogTitle.textContent = binSaved ? "Bin Saved; Connectors Partly Saved" : "Connectors Partly Saved";
        if (dialogSubtitle) dialogSubtitle.textContent = "Some connector files were saved before the remaining connector failed.";
        if (dialogError) {
          dialogError.textContent = message;
          dialogError.hidden = false;
        }
        if (dialogActions) dialogActions.hidden = false;
        report(message, true, 9000);
        return;
      }
      setItemStatus("connector", "done", "Saved to " + (state.browserFolder?.name || "your download folder") + ": " + connFiles.join(", "));
    }

    // Fix 032 Correction 2 (C2.3): the generated output is real either way,
    // but a failed final checkpoint must not be buried under an
    // unconditional "Complete!" - and the two outcomes get exactly one
    // toast each, not a success toast followed by a contradicting one.
    if (checkpointSaveFailed) {
      if (dialogTitle) dialogTitle.textContent = "Saved — Design Save Needs Attention";
      if (dialogSubtitle) dialogSubtitle.textContent = "Parts were saved, but the current design could not be saved to this Space.";
    } else {
      if (dialogTitle) dialogTitle.textContent = "Saved";
      if (dialogSubtitle) dialogSubtitle.textContent = "All parts saved.";
    }

    if (dialogActions) dialogActions.hidden = false;

    const uniqueFiles = [...new Set(allFiles)];
    const planNote = connectorPlan && connectorPlan.webbed
      ? `\nConnector: ${fmt(connectorPlan.length_mm)} mm long, ${fmt(connectorPlan.web_thickness_mm)} mm web, `
        + `${fmt(connectorPlan.printed_height_mm)} mm printed height`
      : "";
    saveOutput = state.browserFolder?.name || "your download folder (multiple files are together in Wavefinity files.zip)";
    const savedMessage = `Saved to ${saveOutput}${uniqueFiles.length ? `\n${uniqueFiles.join("\n")}` : ""}${planNote}\nOpen the saved file in your slicer.`;
    report(
      checkpointSaveFailed
        ? `${savedMessage}\n\nThe current design could not be saved to this Space: ${checkpointSaveFailed.message}`
        : savedMessage,
      Boolean(checkpointSaveFailed),
      checkpointSaveFailed ? 9000 : 7000,
    );
  } catch (error) {
    if (target === "all" || target === "bin") {
      const binRow = $("#gen-item-bin");
      if (binRow && !binRow.classList.contains("status-done")) {
        setItemStatus("bin", "error", error.message);
      }
    }
    if (target === "all" || target === "connector") {
      const connRow = $("#gen-item-connector");
      if (connRow && !connRow.classList.contains("status-done")) {
        setItemStatus("connector", "error", error.message);
      }
    }

    const connectorsFailedAfterBin = binSaved && saveStage === "connector";
    let failureText = error.message;
    if (connectorsFailedAfterBin) {
      const savedList = [...new Set(allFiles)];
      failureText = `The bin was saved, but the connectors could not be saved: ${error.message}`
        + `${savedList.length ? `\nSaved to ${saveOutput}\n${savedList.join("\n")}` : ""}`;
    }
    if (dialogTitle) dialogTitle.textContent = connectorsFailedAfterBin ? "Bin Saved; Connectors Failed" : "Saving Failed";
    if (dialogSubtitle) dialogSubtitle.textContent = connectorsFailedAfterBin
      ? "The bin file was saved. Only the connectors failed."
      : "An error occurred while saving parts.";
    if (dialogError) {
      dialogError.textContent = failureText;
      dialogError.hidden = false;
    }
    if (dialogActions) {
      dialogActions.hidden = false;
    }
    setError(failureText);
    report(failureText, true, 7000);
  } finally {
    isGenerating = false;
    state.designMutationBusy = false;
    setMutationSurfacesInert(false);
    updateGenerateAvailability();
  }
}

async function printModel(target = "bin", initiatingButton = null) {
  if (state.designMutationBusy || isGenerating || currentOutputReport?.busy) return;
  const report = beginGenerationReport("Printing…");
  try {
    await printModelWithReport(target, initiatingButton, report);
  } catch (error) {
    report(friendlyError(error), true);
  } finally {
    report.finish();
  }
}


// B08: the browser cannot launch a slicer, so Print prepares one arranged 3MF
// locally, saves it, and asks the user to open it in Bambu Studio. The page
// never claims the slicer was opened for them; only this explicit
// confirmation (a user action) may update the existing Printed state.
function confirmOpenedInBambuStudio(filename, where, note = "") {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "wf-confirm-dialog";
    const title = document.createElement("h3");
    title.textContent = "Open in Bambu Studio";
    const body = document.createElement("p");
    body.textContent = `Your print file is ready: ${filename}`;
    const where_ = document.createElement("p");
    where_.textContent = `${where} Open this file in Bambu Studio yourself; Wavefinity cannot open it for you from the browser.`;
    const extra = document.createElement("p");
    extra.textContent = note;
    extra.hidden = !note;
    const actions = document.createElement("div");
    actions.className = "button-row";
    const later = document.createElement("button");
    later.type = "button"; later.textContent = "Not yet"; later.className = "button secondary";
    const opened = document.createElement("button");
    opened.type = "button"; opened.textContent = "I opened it in Bambu Studio"; opened.className = "button";
    let answer = false;
    opened.addEventListener("click", () => { answer = true; dialog.close(); });
    later.addEventListener("click", () => dialog.close());
    actions.append(later, opened);
    dialog.append(title, body, where_, extra, actions);
    dialog.addEventListener("close", () => { dialog.remove(); resolve(answer); }, { once: true });
    document.body.append(dialog);
    dialog.showModal();
    opened.focus();
  });
}

async function printModelWithReport(target, initiatingButton, report) {
  // Ordinary output entry points defensively reject structural ownership:
  // a Storage Box or Storage Drawers target has its own Save/Print chrome.
  if (designTargetIsStructural()) {
    report("These outputs are for ordinary bins. The structural editor has its own Save and Print actions.", true);
    return;
  }
  if (relocationBlocksWrites()) return;
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ materialize: target === "bin" || target === "all" }))) return;
  const designRowId = typedSpaceOrdinaryBin() && (target === "bin" || target === "all")
    ? state.designInventoryId : null;
  const designSpaceContext = designRowId ? DL.spaceContext() : null;
  if (!beginDesignMutation()) return;
  const button = initiatingButton || document.createElement("button");
  const old = button.textContent;
  button.textContent = "Preparing…";
  setError();
  const outputFolder = state.browserFolder, outputSpace = state.activeSpaceId;
  let outputEpoch = null;
  const requireOutputContext = () => {
    if (state.browserFolder !== outputFolder || state.activeSpaceId !== outputSpace ||
        (outputEpoch !== null && WFLocalAPI.designEpoch !== outputEpoch) || state.relocating) {
      throw new Error("The Space or design changed before the files were saved.");
    }
  };
  const savedNames = result => [...new Set((result.design_files || []).map(file => String(file).split(/[\\/]/).pop())
    .filter(name => /\.3mf$/i.test(name)))];
  const requireSameDesign = payload => {
    DL.requireSpaceContext(designSpaceContext);
    if (state.designInventoryId !== designRowId ||
        JSON.stringify(state.design) !== JSON.stringify(payload.design))
      throw new Error("This bin changed during the print preparation.");
  };
  try {
    await commitVisibleDraft();
    requireOutputContext();
    outputEpoch = WFLocalAPI.designEpoch;
    // Snapshot of the design, Space identity and selected printer profile.
    const payload = {
      design: clone(state.design),
      output: state.output,
      connector: state.connector,
      target: target,
      keep_log: false,
      design_row_id: designRowId || undefined,
      printer_profile: PrinterProfile.current(),
      printer_profile_configured: PrinterProfile.configured(),
      // Fix 1069: carry the active Space so direct Print in a Storage Box
      // Space is hard-blocked when the bin/closed stack exceeds the interior Z.
      space: state.folderMode === "space" ? (state.activeSpace ?? null) : null,
    };
    // Fix 032 Correction 1: same exact resume checkpoint contract as
    // generateParts() - flush the pre-operation state before building. If it
    // cannot be durably saved, stop rather than proceed as though the design
    // would still be recoverable on a failed print.
    if (state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        throw new Error(`The current design could not be saved to this Space, so nothing was prepared: ${error.message}`);
      }
    }
    if (outputFolder?.handle) {
      payload.inventory_text = await SP.readInventoryFor(outputFolder, { migrate: false });
      payload.space_metadata_text = await WFFileSystem.readText(outputFolder.handle, FOLDER_METADATA);
      payload.space_id = outputSpace || undefined;
    }
    requireOutputContext();
    const progress = startOutputProgress("Preparing print file…", text => report.progress?.(text), report.entry);
    let result;
    try {
      result = await apiSideEffect("/api/print", payload, {
        onStillFinishing: () => { if (button) button.textContent = "Still working…"; },
        onProgress: progress.update,
      });
    } finally {
      progress.stop();
    }
    // Write to the selected writable folder, or download. Truthful either way.
    const saved = await saveGeneratedFiles(result, {
      ownedStale: designRowId ? staleFileNamesForRow(designRowId) : [], requireCurrent: requireOutputContext,
    });
    const where = result.downloaded_archive
      ? `Downloaded ${result.downloaded_archive}.`
      : `Saved to ${state.browserFolder?.name || "your download folder"}.`;
    if (result.partial) {
      // Files are real even though Print could not finish after them: never
      // mark this row Printed, and never bury what was actually saved.
      let savedStatusFailed = null;
      if (designSpaceContext && savedNames(result).length) {
        try {
          requireSameDesign(payload);
          const status = await DL.inventoryCall("/api/drawer/design-source/status", {
            row_id: designRowId, action: "saved", file: savedNames(result).join(", "), design: payload.design,
          }, { context: designSpaceContext, sideEffect: true });
          DL.adopt(status);
          DL.emit();
        } catch (error) {
          savedStatusFailed = error;
        }
      }
      const partialMessage = `${result.error || "Files were saved, but the print could not be prepared."}\n${where}\n${saved.join("\n")}`;
      setError(result.error || partialMessage);
      report(
        savedStatusFailed
          ? `${partialMessage}\n\nSaved status could not be recorded: ${savedStatusFailed.message}`
          : partialMessage,
        true,
        9000,
      );
      return;
    }
    const fileName = result.handoff?.filename || saved[0];
    // A final checkpoint failure is reported once, together with the outcome.
    let checkpointSaveFailed = null;
    if ((target === "bin" || target === "all") && state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        checkpointSaveFailed = error;
      }
    }
    report(`Prepared ${fileName}. ${where}\nNext: open it in Bambu Studio.`, false, 7000);
    // Prominent next step, with the exact filename and an explicit confirmation.
    const confirmed = await confirmOpenedInBambuStudio(fileName, where,
      checkpointSaveFailed ? `The current design could not be saved to this Space: ${checkpointSaveFailed.message}` : "");
    const printable = target === "bin" || target === "all";
    if (!confirmed) {
      report(`${fileName} is saved but not marked Printed. Open it in Bambu Studio, then use Print again to confirm.`, false, 8000);
      return;
    }
    if (!printable) {
      report(`${fileName} opened in Bambu Studio (confirmed by you).`, false, 5000);
      return;
    }
    if (designSpaceContext) {
      try {
        requireSameDesign(payload);
        const printed = await DL.inventoryCall("/api/drawer/design-source/status", {
          row_id: designRowId, action: "printed", file: savedNames(result).join(", ") || fileName, design: payload.design,
        }, { context: designSpaceContext, sideEffect: true });
        DL.adopt(printed);
        DL.emit();
      } catch (error) {
        throw new Error(`You confirmed ${fileName} was opened, but Printed status could not be recorded: ${error.message}`);
      }
    } else if (typeof WS !== "undefined") {
      WS.markLooseBinPrinted();
    }
    report(`${fileName} marked Printed after your confirmation.`, Boolean(checkpointSaveFailed), 7000);
  } catch (error) {
    setError(error.message);
    report(error.message, true, 8000);
  } finally {
    report.finish();
    button.textContent = old;
    finishDesignMutation();
  }
}

// Connectors are physically unavailable for a B4B, a Base Trim or a lidded
// bin.
function connectorsUnavailable() {
  return b4bEnabled() || baseTrimEnabled() || !binGridRules().side_connectors || Boolean(state.design?.box?.lid?.enabled);
}

let includeIndividualBinConnectors = true;

function syncPrintChoiceAvailability() {
  const option = $("#individual-bin-include-connectors");
  const unavailable = connectorsUnavailable();
  option.closest("label").hidden = !binGridRules().side_connectors;
  option.disabled = unavailable;
  option.checked = !unavailable && includeIndividualBinConnectors;
  $("#individual-bin-connectors-unavailable").hidden = !unavailable;
}

function chooseIndividualBinPrint(button) {
  const dialog = $("#individual-bin-print-dialog");
  if (dialog.open) return;
  const exporting = button.dataset.output === "export";
  if (exporting && joinRunningExport()) return;
  // Nothing to choose when connectors cannot apply: print the bin directly.
  if (!exporting && connectorsUnavailable()) {
    printModel("bin", button);
    return;
  }
  syncPrintChoiceAvailability();
  dialog.querySelector('[value="export"]').hidden = !exporting;
  dialog.querySelector('[value="print"]').hidden = exporting;
  $("#individual-bin-print-message").textContent = exporting
    ? "Choose what to include in the files."
    : "Choose what to include in the print file.";
  dialog.returnValue = "cancel";
  dialog.addEventListener("close", () => {
    if (!["export", "print"].includes(dialog.returnValue)) return;
    const option = $("#individual-bin-include-connectors");
    if (!option.disabled) includeIndividualBinConnectors = option.checked;
    const target = option.checked ? "all" : "bin";
    if (dialog.returnValue === "export") generateParts(target);
    else printModel(target, button);
  }, { once: true });
  dialog.showModal();
}

function updatePrimaryPrintButtonLabel() {
  $("#settings-slicer-picker").hidden = true; // B08: a browser cannot launch a slicer
  $("#print-dialog-slicer-picker").hidden = true; // B08: a browser cannot launch a slicer
}

function updateSlicerUI() {
  updatePrimaryPrintButtonLabel();
}

async function browseSlicer(button) {
  if (button) button.disabled = true;
  try {
    const result = await api("/api/browse-slicer-path", { current: state.slicer?.path });
    if (result.message) toast(result.message, false, 10000);
    if (result.slicer_path) {
      const name = result.slicer_path.split(/[\\/]/).pop().replace(/\.exe$/i, "");
      if (!/bambu|orca/i.test(name)) {
        const use = await appConfirmAction({
          title: "Use this program as your slicer?",
          message: `"${name}" does not look like Bambu Studio or OrcaSlicer. Use it anyway?`,
          actionLabel: "Use It",
        });
        if (!use) return;
      }
      // Persist first; only a successful save changes the live slicer.
      await api("/api/preferences", { slicer_path: result.slicer_path });
      state.slicer = {
        available: true,
        path: result.slicer_path,
        name: /bambu/i.test(name) ? "Bambu Studio" : /orca/i.test(name) ? "OrcaSlicer" : name,
      };
      updateSlicerUI();
      toast(`Slicer set to ${state.slicer.name}`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function collectOutputs(value, found = []) {
  if (!value || typeof value !== "object") return found;
  if (typeof value.output === "string") found.push(value.output.split(/[\\/]/).pop());
  Object.values(value).forEach(item => collectOutputs(item, found));
  return [...new Set(found)];
}

// policy.kind: "bin" (default), "connector", "structural" or "pegboard_hooks".
// Ownership is decided by the caller, never by the file name.
const OWNED_OUTPUT_LABELS = { structural: "Storage Box", pegboard_hooks: "Pegboard hook" };

async function saveGeneratedFiles(result, policy = {}) {
  const files = result.files || [];
  if (!files.length) throw new Error("The local engine did not return any files to save.");
  const folder = state.browserFolder;
  const spaceId = state.activeSpaceId;
  const epoch = WFLocalAPI.designEpoch;
  const requireCurrent = () => {
    policy.requireCurrent?.();
    if (state.browserFolder !== folder || state.activeSpaceId !== spaceId ||
        WFLocalAPI.designEpoch !== epoch || state.relocating) {
      throw new Error("The Space or design changed before the files were saved.");
    }
  };
  const connector = policy.kind === "connector";
  const blobs = new Map();
  const skip = new Set();
  try {
    // Claim the whole set before the first write. A missing/expired handle or
    // invalid/duplicate name leaves the destination untouched.
    const ids = new Set(), names = new Set();
    for (const file of files) {
      const folded = typeof file.name === "string" ? file.name.normalize("NFC").toLowerCase() : "";
      if (!folded || /[<>:"\\/|?*\x00-\x1f]/.test(file.name) || /[. ]$/.test(file.name) ||
          /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(file.name) || names.has(folded) ||
          typeof file.local_file_id !== "string" || ids.has(file.local_file_id)) {
        throw new Error("The local engine returned an invalid file set.");
      }
      ids.add(file.local_file_id);
      names.add(folded);
      const blob = WFLocalFiles.claim(file.local_file_id);
      if (!blob?.size) throw new Error(`The local file ${file.name} is unavailable. Generate the files again.`);
      blobs.set(file.name, blob);
    }
    requireCurrent();
    if (!folder?.handle) {
      result.downloaded_archive = await WFLocalFiles.downloadSet(files.map(file => ({ name: file.name, blob: blobs.get(file.name) })), requireCurrent);
      return files.map(file => file.name);
    }
    return await WFFileSystem.queueFolderWrite(folder.handle, async () => {
      requireCurrent();
      const existing = [];
      for (const file of files) {
        if (await WFFileSystem.fileExists(folder.handle, file.name)) existing.push(file);
      }
      // A re-save may replace Wavefinity's own superseded output: the caller
      // lists those names in policy.ownedStale (the row's server-tracked
      // stale_files). Any other collision still demands a rename.
      const ownedStale = new Set((policy.ownedStale || []).filter(name => typeof name === "string" && name));
      const foreign = existing.filter(file => !ownedStale.has(file.name));
      if (existing.length && connector) {
        const different = [];
        for (const file of existing) {
          const [oldHash, newHash] = await Promise.all([
            WFFileSystem.sha256(folder.handle, file.name), WFFileSystem.sha256Blob(blobs.get(file.name)),
          ]);
          if (oldHash === newHash) skip.add(file.name); else different.push(file.name);
        }
        if (different.length && !(await confirmReplaceConnectorFiles(different))) {
          throw new Error("Connector save cancelled. Nothing was replaced.");
        }
      } else if (OWNED_OUTPUT_LABELS[policy.kind] && existing.length) {
        // A Storage Box or Pegboard hooks re-save reuses the same deterministic
        // names. A byte-identical file is provably Wavefinity's own prior output
        // and is left alone; a differing same-name file gets an explicit Replace
        // / Cancel choice instead of a hard rename demand.
        const label = OWNED_OUTPUT_LABELS[policy.kind];
        const different = [];
        for (const file of existing) {
          const [oldHash, newHash] = await Promise.all([
            WFFileSystem.sha256(folder.handle, file.name), WFFileSystem.sha256Blob(blobs.get(file.name)),
          ]);
          if (oldHash === newHash) skip.add(file.name); else different.push(file.name);
        }
        if (different.length && !(await confirmReplaceOutputFiles(different, label))) {
          throw new Error(`${label} save cancelled. Nothing was replaced.`);
        }
      } else if (foreign.length) {
        const hint = policy.kind === "structural"
          ? "Give the Space a different name, then try exporting again."
          : undefined;
        showFilenameConflictDialog(foreign.map(file => file.name), hint);
        throw new Error(policy.kind === "structural"
          ? "Give the Space a different name to avoid overwriting an existing file."
          : "Give the bin a different name to avoid overwriting an existing file.");
      }
      const previous = new Map(), touched = [];
      for (const file of files) {
        if (skip.has(file.name)) continue;
        // Capture original bytes before changing any member of the set.
        const old = existing.some(one => one.name === file.name)
          ? await (await folder.handle.getFileHandle(file.name)).getFile() : null;
        previous.set(file.name, old ? new Blob([await old.arrayBuffer()], { type: old.type }) : null);
      }
      try {
        for (const file of files) {
          requireCurrent();
          if (!skip.has(file.name)) {
            touched.push(file.name); // includes a create/write that fails midway
            await WFFileSystem.writeBlob(folder.handle, file.name, blobs.get(file.name));
          }
        }
        requireCurrent();
      } catch (error) {
        const failed = [];
        for (const name of touched.reverse()) {
          try {
            const old = previous.get(name);
            if (old) await WFFileSystem.writeBlob(folder.handle, name, old);
            else {
              try { await WFFileSystem.removeFile(folder.handle, name); }
              catch (removeError) { if (removeError.name !== "NotFoundError") throw removeError; }
            }
          } catch (_rollbackError) { failed.push(name); }
        }
        if (failed.length) throw new Error(`${error.message} The folder could not be fully restored: ${failed.join(", ")}.`);
        throw error;
      }
      return files.map(file => file.name);
    });
  } finally {
    for (const file of files) WFLocalFiles.discard(file.local_file_id);
  }
}

function watchServerVersion() {
  setInterval(async () => {
    let health;
    try {
      health = await api("/api/health");
    } catch (_error) {
      return; // A blip shouldn't flip the banner - only a confirmed different instance should.
    }
    // Browser edition: there is no server to restart. Its health identity is made
    // per page and never matches the catalog's, so it must not raise the banner.
    if (health.runtime === "browser") return;
    if (health.instance === state.serverInstance) return;
    if (state.runtime.hosted && health.api_compat === state.apiCompat) {
      state.serverInstance = health.instance;
      return;
    }
    const incompatibleHosted = state.runtime.hosted;
    const message = $("#update-banner span");
    if (message) message.textContent = incompatibleHosted
      ? "Wavefinity was updated. This update requires the page to reload before you continue."
      : "Wavefinity restarted. Reload to use the current code.";
    $("#update-banner").hidden = false;
  }, VERSION_POLL_MS);
}

async function showAboutDialog() {
  const dialog = $("#about-dialog");
  const content = $("#about-dialog-content");
  if (!dialog || !content) return;
  dialog.showModal();
  try {
    const res = await fetch("/Brochure.md");
    if (!res.ok) throw new Error("Could not load Brochure.md");
    let text = await res.text();
    const cutIndex = text.search(/##\s*🚀\s*Ready to test it out/i);
    if (cutIndex !== -1) {
      text = text.slice(0, cutIndex).trimEnd();
      if (text.endsWith("---")) {
        text = text.slice(0, -3).trimEnd();
      }
    }
    content.innerHTML = renderSimpleMarkdown(text);
  } catch (err) {
    content.textContent = "Could not load brochure: " + err.message;
  }
  const capabilities = document.createElement("p");
  capabilities.textContent = "Browser edition: geometry, meshes and folder files stay on this PC. Invoking AI sends your prompt and design/Space descriptors to your chosen provider. Direct chat needs your own session key and provider browser permission. Manual copy/paste is always available. Spaces and autosave need writable folder handles; unsupported browsers offer temporary previews and downloads only. Print prepares a 3MF for you to open in Bambu Studio; a browser cannot launch it or open a server log.";
  content.prepend(capabilities);
  const recovery = document.createElement("button");
  recovery.type = "button";
  recovery.className = "button secondary";
  recovery.textContent = "Space / preferences recovery";
  recovery.onclick = () => SP.showBrowserRecovery();
  content.append(recovery);
}

function renderSimpleMarkdown(md) {
  let html = md
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/\[(.*?)\]\((.*?)\)/gim, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/^(?:---|\*\*\*)$/gim, '<hr>');

  const lines = html.split("\n");
  let inList = false;
  const processed = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ")) {
      if (!inList) {
        processed.push("<ul>");
        inList = true;
      }
      processed.push(`<li>${trimmed.slice(2)}</li>`);
    } else {
      if (inList) {
        processed.push("</ul>");
        inList = false;
      }
      if (trimmed && !trimmed.startsWith("<h") && !trimmed.startsWith("<blockquote") && !trimmed.startsWith("<hr")) {
        processed.push(`<p>${trimmed}</p>`);
      } else if (trimmed) {
        processed.push(trimmed);
      }
    }
  }
  if (inList) processed.push("</ul>");
  return processed.join("\n");
}

// ---- Fix 096 F5: backdrop dismissal convention. Only these five dialogs
// close when the backdrop is clicked: informational or single-action dialogs
// where an accidental close loses nothing. Decision dialogs
// (#app-confirm-dialog, #draft-switch-dialog, #surface-object-height-dialog,
// #printer-settings-dialog), the busy #generation-dialog, and the Connector
// Replace dialog never dismiss on backdrop click.
// Spaces owns #welcome-dialog dismissal through SP.requestClose, including
// its unsaved-setup guard. A second listener here would close the setup
// underneath the confirmation, even when the user chooses Keep Editing.
const SAFE_BACKDROP_DIALOG_IDS = [
  "support-layout-dialog",
  "spacer-print-dialog",
  "ai-help-dialog",
  "bin-name-dialog",
  "about-dialog",
];
function wireDialogBackdropDismiss(dialog) {
  if (!dialog || dialog.dataset.backdropWired === "true") return;
  dialog.dataset.backdropWired = "true";
  dialog.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) {
      dialog.close();
    }
  });
}
function wireSafeDialogBackdrops() {
  for (const id of SAFE_BACKDROP_DIALOG_IDS) {
    wireDialogBackdropDismiss(document.getElementById(id));
  }
}
function wireAboutDialog() {
  const aboutBtn = $("#about-btn");
  const dialog = $("#about-dialog");
  const closeBtn = $("#about-dialog-close");
  const closeHeaderBtn = $("#about-dialog-close-btn");

  if (aboutBtn) {
    aboutBtn.addEventListener("click", () => showAboutDialog());
  }
  if (closeBtn && dialog) {
    closeBtn.addEventListener("click", () => dialog.close());
  }
  if (closeHeaderBtn && dialog) {
    closeHeaderBtn.addEventListener("click", () => dialog.close());
  }
  if (dialog) {
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });
  }
}

function wireBinNameDialog() {
  const dialog = $("#bin-name-dialog");
  const okBtn = $("#bin-name-dialog-ok");
  if (okBtn && dialog) {
    okBtn.addEventListener("click", () => dialog.close());
  }
  if (dialog) {
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });
  }
}
