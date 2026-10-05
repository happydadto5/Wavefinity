"use strict";

async function generateParts(target) {
  // Ordinary output entry points defensively reject structural ownership:
  // a Storage Box or Storage Drawers target has its own Save/Print chrome.
  if (designTargetIsStructural()) {
    toast("These outputs are for ordinary bins. The structural editor has its own Save and Print actions.", true);
    return;
  }
  if (relocationBlocksWrites()) return;
  if (state.designMutationBusy || isGenerating) {
    toast("Finish the current action before saving files.", true);
    return;
  }
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  if (state.runtime.hosted && !state.browserFolder) {
    toast("Choose a folder before saving files.", true);
    return;
  }
  const beforeForm = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;

  cancelChangedDesignDebounce();
  pendingDesignHistory = null;

  if (!applyLiveFormWithModifierConflictGuard(beforeForm, previousCanGenerate)) {
    return;
  }
  noteCommittedDesignChange(beforeForm);

  if ((target === "all" || target === "bin") && !state.canGenerate) {
    toast("Resolve the highlighted issue before saving.", true);
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

  if (dialogTitle) dialogTitle.textContent = "Saving Parts…";
  if (dialogSubtitle) dialogSubtitle.textContent = "Please wait while your files are being saved.";
  if (dialogError) {
    dialogError.hidden = true;
    dialogError.textContent = "";
  }
  if (dialogActions) {
    dialogActions.hidden = true;
  }

  const boxTitle = `Bin (${fmt(state.design.box.x)} × ${fmt(state.design.box.y)} × ${fmt(state.design.box.z)} mm)`;
  const connTitle = state.connector.different_heights
    ? "Side Connector"
    : "Connectors (Side + 3-Way + 4-Way)";

  const items = [];
  if (target === "all" || target === "bin") {
    items.push({ id: "bin", title: boxTitle, status: "waiting", text: "Waiting…" });
  }
  if (target === "all" || target === "connector") {
    items.push({ id: "connector", title: connTitle, status: "waiting", text: "Waiting…" });
  }

  renderGenerationItems(items);

  isGenerating = true;
  state.designMutationBusy = true;
  setMutationSurfacesInert(true);
  updateGenerateAvailability();

  if (dialog && typeof dialog.showModal === "function") {
    try {
      if (!dialog.open) dialog.showModal();
    } catch (_err) {
      // Ignore if already open
    }
  }

  const allFiles = [];
  let connectorPlan = null;
  let saveOutput = state.output;
  let checkpointSaveFailed = null;
  // Stage truth: once the bin is really saved, a later connector failure must
  // say so instead of presenting the whole action as failed.
  let saveStage = "setup";
  let binSaved = false;

  try {
    // A debounced support edit may still be visible only in the draft. Save
    // it now so the exported files always match the canvas.
    await commitVisibleDraft();

    const payload = {
      design: clone(state.design),
      output: state.output,
      connector: state.connector,
      keep_log: designRowId ? false : state.keepLog,
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

    // Step 1: Generate Bin if requested
    if (target === "all" || target === "bin") {
      saveStage = "bin";
      setItemStatus("bin", "generating", "Saving…");
      const binResult = await apiSideEffect("/api/generate", payload, { onStillFinishing: () => setItemStatus("bin", "generating", "Still finishing…") });
      if (designSpaceContext) DL.requireSpaceContext(designSpaceContext);
      saveOutput = binResult.output || saveOutput;
      const binFiles = await saveGeneratedFiles(binResult, { ownedStale: staleFileNamesForRow(designRowId) });
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
      setItemStatus("bin", "done", "Done");
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
      saveStage = "connector";
      setItemStatus("connector", "generating", "Saving…");
      const connectorPayload = { ...payload, replace_existing_connectors: false };
      let connResult = await apiSideEffect("/api/connector", connectorPayload, { onStillFinishing: () => setItemStatus("connector", "generating", "Still finishing…") });
      if (connResult.requires_connector_replace) {
        const names = connResult.conflict_files || [];
        if (!(await confirmReplaceConnectorFiles(names))) {
          throw new Error("Connector save cancelled. Nothing was replaced.");
        }
        connResult = await apiSideEffect("/api/connector", {
          ...connectorPayload,
          replace_existing_connectors: true,
        }, { onStillFinishing: () => setItemStatus("connector", "generating", "Still finishing…") });
      }
      saveOutput = connResult.output || saveOutput;
      if (connResult.connector_plan) {
        connectorPlan = connResult.connector_plan;
        renderConnectorReadout(connResult.connector_plan);
      }
      const connFiles = await saveGeneratedFiles(connResult, { kind: "connector" });
      allFiles.push(...connFiles);
      if (connResult.partial) {
        // Some connectors were really written before a later one failed.
        setItemStatus("connector", "error", "Partly saved");
        const savedList = [...new Set(allFiles)];
        const message = `${binSaved ? "The bin was saved. " : ""}Some connector files were saved, but not all.\n${connResult.error || ""}`
          + `${savedList.length ? `\nSaved to ${saveOutput}\n${savedList.join("\n")}` : ""}`;
        if (dialogTitle) dialogTitle.textContent = binSaved ? "Bin Saved; Connectors Partly Saved" : "Connectors Partly Saved";
        if (dialogSubtitle) dialogSubtitle.textContent = "Some connector files were saved before the remaining connector failed.";
        if (dialogError) {
          dialogError.textContent = message;
          dialogError.hidden = false;
        }
        if (dialogActions) dialogActions.hidden = false;
        toast(message, true, 9000);
        return;
      }
      setItemStatus("connector", "done", "Done");
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

    // Pause briefly so user clearly sees checkmarks
    await new Promise(resolve => setTimeout(resolve, 650));

    if (dialog && dialog.open) {
      dialog.close();
    }

    const uniqueFiles = [...new Set(allFiles)];
    const planNote = connectorPlan && connectorPlan.webbed
      ? `\nConnector: ${fmt(connectorPlan.length_mm)} mm long, ${fmt(connectorPlan.web_thickness_mm)} mm web, `
        + `${fmt(connectorPlan.printed_height_mm)} mm printed height`
      : "";
    const savedMessage = `Saved to ${saveOutput}${uniqueFiles.length ? `\n${uniqueFiles.join("\n")}` : ""}${planNote}`;
    toast(
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
        setItemStatus("bin", "error", "Failed");
      }
    }
    if (target === "all" || target === "connector") {
      const connRow = $("#gen-item-connector");
      if (connRow && !connRow.classList.contains("status-done")) {
        setItemStatus("connector", "error", "Failed");
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
    toast(failureText, true, 7000);
  } finally {
    isGenerating = false;
    state.designMutationBusy = false;
    setMutationSurfacesInert(false);
    updateGenerateAvailability();
  }
}

async function generate(path, selector) {
  if (path && path.includes("connector")) {
    return generateParts("connector");
  }
  return generateParts("bin");
}

async function printModel(target = "bin", initiatingButton = null) {
  // Ordinary output entry points defensively reject structural ownership:
  // a Storage Box or Storage Drawers target has its own Save/Print chrome.
  if (designTargetIsStructural()) {
    toast("These outputs are for ordinary bins. The structural editor has its own Save and Print actions.", true);
    return;
  }
  if (relocationBlocksWrites()) return;
  if (state.runtime.hosted) return generateParts(target === "all" ? "all" : "bin");
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  if (!state.slicer || !state.slicer.available) {
    toast("A slicer prepares 3D-print files for your printer. Use Change Slicer below the print buttons to choose one.", true, 8000);
    return;
  }
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ materialize: target === "bin" || target === "all" }))) return;
  const designRowId = typedSpaceOrdinaryBin() && (target === "bin" || target === "all")
    ? state.designInventoryId : null;
  const designSpaceContext = designRowId ? DL.spaceContext() : null;
  if (!beginDesignMutation()) return;
  const button = initiatingButton || $("#print-without-connectors");
  const old = button.textContent;
  const printButtons = [$("#print-with-connectors"), $("#print-without-connectors")].filter(Boolean);
  printButtons.forEach(one => { one.disabled = true; });
  const slicerName = state.slicer?.name || "the slicer";
  button.textContent = `Sending to ${slicerName}…`;
  setError();
  try {
    await commitVisibleDraft();
    const payload = {
      design: clone(state.design),
      output: state.output,
      connector: state.connector,
      target: target,
      keep_log: designRowId ? false : state.keepLog,
      design_row_id: designRowId || undefined,
    };
    // R67: only a request. The server reuses the existing Printed file(s)
    // when it can prove the design is unchanged, else it generates as usual.
    if (designRowId) {
      const boundRow = DL.bin(designRowId);
      if (boundRow?.status === "printed" && String(boundRow.file || "").trim()) payload.reuse_printed_file = true;
    }
    // Fix 032 Correction 1: same exact resume checkpoint contract as
    // generateParts() - flush the pre-operation state before sending. If it
    // cannot be durably saved, stop before /api/print rather than proceed
    // as though the design would still be recoverable on a failed print.
    if (state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        throw new Error(`The current design could not be saved to this Space, so nothing was sent: ${error.message}`);
      }
    }
    const result = await apiSideEffect("/api/print", payload, { onStillFinishing: () => { button.textContent = "Still finishing…"; } });
    if (result.partial) {
      // Bin/design files are a real side effect even though connectors or
      // the slicer step failed after them: never mark this row Printed, and
      // never bury the truth of what was actually saved.
      let savedStatusFailed = null;
      // A reused Printed file was not newly saved; its row stays as it was.
      if (designSpaceContext && !result.design_reused) {
        try {
          DL.requireSpaceContext(designSpaceContext);
          if (state.designInventoryId !== designRowId ||
              JSON.stringify(state.design) !== JSON.stringify(payload.design))
            throw new Error("This bin changed during the slicer handoff.");
          const names = [...new Set((result.design_files || []).map(file => String(file).split(/[\\/]/).pop())
            .filter(name => /\.3mf$/i.test(name)))];
          const saved = await DL.inventoryCall("/api/drawer/design-source/status", {
            row_id: designRowId, action: "saved", file: names.join(", "), design: payload.design,
          }, { context: designSpaceContext, sideEffect: true });
          DL.adopt(saved);
          DL.emit();
        } catch (error) {
          savedStatusFailed = error;
        }
      }
      const partialMessage = result.error || "Files were saved, but the print could not finish.";
      setError(partialMessage);
      toast(
        savedStatusFailed
          ? `${partialMessage}\n\nSaved status could not be recorded: ${savedStatusFailed.message}`
          : partialMessage,
        true,
        9000,
      );
      return;
    }
    if (designSpaceContext) {
      try {
        DL.requireSpaceContext(designSpaceContext);
        if (state.designInventoryId !== designRowId ||
            JSON.stringify(state.design) !== JSON.stringify(payload.design))
          throw new Error("This bin changed during the slicer handoff.");
        const names = [...new Set((result.design_files || []).map(file => String(file).split(/[\\/]/).pop())
          .filter(name => /\.3mf$/i.test(name)))];
        const printed = await DL.inventoryCall("/api/drawer/design-source/status", {
          row_id: designRowId, action: "printed", file: names.join(", "), design: payload.design,
        }, { context: designSpaceContext, sideEffect: true });
        DL.adopt(printed);
        DL.emit();
      } catch (error) {
        throw new Error(`Bambu Studio opened, but Printed status could not be recorded: ${error.message}`);
      }
    }
    const files = result.files || [];
    const fileNames = files.map(f => f.split(/[\\/]/).pop());
    const sentMessage = `Sent to ${slicerName}!\n${fileNames.join("\n")}`;
    if (target === "bin" || target === "all") {
      // Fix 032 Correction 2 (C2.3): the slicer handoff already succeeded
      // by this point, so defer the success toast until after the final
      // checkpoint attempt and report exactly one message - never the
      // ordinary success toast followed by a contradicting failure one.
      let checkpointSaveFailed = null;
      if (state.folderMode === "space" && typeof SP !== "undefined") {
        try {
          await SP.flushResumeCheckpoint(payload.design, false);
        } catch (error) {
          checkpointSaveFailed = error;
        }
      }
      toast(
        checkpointSaveFailed
          ? `${sentMessage}\n\nThe current design could not be saved to this Space: ${checkpointSaveFailed.message}`
          : sentMessage,
        Boolean(checkpointSaveFailed),
        checkpointSaveFailed ? 9000 : 7000,
      );
    } else {
      toast(sentMessage, false, 7000);
    }
  } catch (error) {
    setError(error.message);
    toast(error.message, true, 8000);
  } finally {
    button.textContent = old;
    finishDesignMutation();
  }
}

// Connectors are physically unavailable for a B4B, a Base Trim or a lidded
// bin - the same rule that hides Save Bin + Connectors.
function connectorsUnavailable() {
  return b4bEnabled() || baseTrimEnabled() || Boolean(state.design?.box?.lid?.enabled);
}

function syncPrintChoiceAvailability() {
  const withButton = $("#print-with-connectors");
  if (withButton) withButton.hidden = connectorsUnavailable();
}

function updatePrimaryPrintButtonLabel() {
  const withButton = $("#print-with-connectors");
  const withoutButton = $("#print-without-connectors");
  const wrap = $(".print-button-wrap");
  if (!withButton || !withoutButton) return;
  if (wrap) wrap.hidden = false;
  syncPrintChoiceAvailability();
  withoutButton.hidden = false;
  if (state.runtime.hosted) {
    withButton.textContent = "Save with Connectors";
    withButton.title = "Save the bin and its connector files into your selected folder";
    withoutButton.textContent = "Save without Connectors";
    withoutButton.title = "Save only the bin into your selected folder";
    $("#slicer-picker-button").hidden = true;
    return;
  }
  const name = state.slicer?.name || "the slicer";
  const missing = !state.slicer?.available;
  withButton.textContent = "Print with Connectors";
  withoutButton.textContent = "Print without Connectors";
  withButton.title = missing
    ? "Bambu Studio is not installed - click 'Change slicer' to locate executable"
    : `Send the bin and its connectors to ${name}`;
  withoutButton.title = missing
    ? "Bambu Studio is not installed - click 'Change slicer' to locate executable"
    : `Send only the bin to ${name}`;
}

function updateSlicerUI() {
  updatePrimaryPrintButtonLabel();
}

async function browseSlicer() {
  const button = $("#slicer-picker-button");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/browse-slicer-path", { current: state.slicer?.path });
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
  if (!state.runtime.hosted) return collectOutputs(result.result);
  const files = result.files || [];
  if (!files.length) throw new Error("The server did not return any files to save.");
  const folder = state.browserFolder;
  const connector = policy.kind === "connector";
  const blobs = new Map();
  const skip = new Set();
  if (connector) {
    // Fetch every candidate before anything is written: a failed download
    // must leave the folder exactly as it was.
    for (const file of files) {
      const response = await fetch(file.url);
      if (!response.ok) throw new Error(`Could not download ${file.name}.`);
      blobs.set(file.name, await response.blob());
    }
  }
  if (folder?.handle) {
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
      for (const file of files) {
        if (!blobs.has(file.name)) {
          const response = await fetch(file.url);
          if (!response.ok) throw new Error(`Could not download ${file.name}.`);
          blobs.set(file.name, await response.blob());
        }
      }
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
        ? "Give the Space a different name, then save again."
        : undefined;
      showFilenameConflictDialog(foreign.map(file => file.name), hint);
      throw new Error(policy.kind === "structural"
        ? "Give the Space a different name to avoid overwriting an existing file."
        : "Give the bin a different name to avoid overwriting an existing file.");
    }
  }
  const saved = [];
  for (const file of files) {
    if (!skip.has(file.name)) {
      let blob = blobs.get(file.name);
      if (!blob) {
        const response = await fetch(file.url);
        if (!response.ok) throw new Error(`Could not download ${file.name}.`);
        blob = await response.blob();
      }
      await WFFileSystem.writeBlob(folder?.handle, file.name, blob);
    }
    saved.push(file.name);
  }
  return saved;
}

function watchServerVersion() {
  setInterval(async () => {
    let health;
    try {
      health = await api("/api/health");
    } catch (_error) {
      return; // A blip shouldn't flip the banner - only a confirmed different instance should.
    }
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
  const runtime = document.createElement("section");
  runtime.className = "about-runtime";
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) throw new Error("Health unavailable");
    const health = await response.json();
    if (!health.source_fingerprint) throw new Error("Runtime identity unavailable");
    const heading = document.createElement("h3");
    heading.textContent = "Runtime";
    runtime.append(heading);
    for (const [label, value] of [
      ["Build", health.build], ["Source", health.source_root],
      ["Fingerprint", health.source_fingerprint],
    ]) {
      if (value == null) continue;
      const line = document.createElement("p");
      line.textContent = `${label}: ${value}`;
      runtime.append(line);
    }
  } catch (_error) {
    runtime.textContent = "Runtime details unavailable";
  }
  content.append(runtime);
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

// ---- Fix 096 F5: backdrop dismissal convention. Only these six dialogs
// close when the backdrop is clicked: informational or single-action dialogs
// where an accidental close loses nothing. Decision dialogs
// (#app-confirm-dialog, #draft-switch-dialog, #surface-object-height-dialog,
// #printer-settings-dialog), the busy #generation-dialog, and the Connector
// Replace dialog never dismiss on backdrop click.
const SAFE_BACKDROP_DIALOG_IDS = [
  "support-layout-dialog",
  "spacer-print-dialog",
  "ai-help-dialog",
  "bin-name-dialog",
  "about-dialog",
  "welcome-dialog",
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
