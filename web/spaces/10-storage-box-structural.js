"use strict";

// ------------------------------------------------------------ Storage Box case settings
//
// A Storage Box Space owns its case: `space.storage_box` (see
// organizer_inventory.normalise_storage_box). These helpers fill and read the
// case settings on the Space setup/Edit form.

SP.storageBoxDefaults = () => ({
  secure_lid: true, latch_count: "1", hinge_count: "2", lid_headroom_mm: 1,
  label_enabled: false, label_text: "", label_location: "top", front_label_style: "flat",
  stacking: false, handle: false,
  wall_mm: Number(state.catalog?.b4b_rules?.default_wall_mm ?? 1.6),
  base_mm: Number(state.catalog?.b4b_rules?.default_base_mm ?? 1.6),
});

SP.fillMaterialSelect = (id, choices, value) => {
  const select = document.getElementById(id);
  if (!select) return;
  const rows = (choices || []).map(one => ({ value: Number(one.value), label: one.label }));
  if (!rows.some(one => Math.abs(one.value - value) < 1e-9)) rows.push({ value, label: "Custom" });
  select.innerHTML = rows.map(one =>
    `<option value="${one.value}">${fmt(one.value)} mm — ${escapeHtml(one.label)}</option>`).join("");
  select.value = String(value);
};

// The setup dialog has no bevel control (the Design-panel form owns it), so it
// carries the Space's own value through: Default for a new Storage Box, and
// None for a saved one that predates the option.
SP.storageBoxEdgeBevel = "default";
// Hinge type is chosen in the Design-panel form; the setup dialog keeps it.
SP.storageBoxHingeType = "screw";

SP.fillStorageBoxForm = box => {
  const one = { ...SP.storageBoxDefaults(), ...(box || {}) };
  SP.storageBoxEdgeBevel = box ? (box.edge_bevel || "none") : "default";
  SP.storageBoxHingeType = box && box.hinge_type === "piano" ? "piano" : "screw";
  const set = (id, value) => { const node = document.getElementById(id); if (node) node.value = String(value); };
  set("portable-lid-type", one.secure_lid === false ? "lid_only" : "latched");
  set("portable-lid-snugness", one.lid_headroom_mm);
  set("portable-stacking", Boolean(one.stacking));
  set("portable-latch-count", ["1", "2"].includes(String(one.latch_count)) ? String(one.latch_count) : "1");
  set("portable-hinge-count", String(one.hinge_count) === "1" ? "1" : "2");
  set("portable-handle", Boolean(one.handle) && one.secure_lid !== false);
  set("portable-label-location", one.label_enabled ? (one.label_location === "front" ? "front" : "top") : "none");
  set("portable-label-text", one.label_text || "");
  set("portable-front-label-style", one.front_label_style === "wavy" ? "wavy" : "flat");
  SP.fillMaterialSelect("portable-wall", state.catalog?.b4b_rules?.wall_choices, Number(one.wall_mm));
  SP.fillMaterialSelect("portable-base", state.catalog?.b4b_rules?.base_choices, Number(one.base_mm));
  SP.syncStorageBoxForm();
};

SP.syncStorageBoxForm = () => {
  const value = id => document.getElementById(id)?.value;
  const hide = (id, hidden) => { const node = document.getElementById(id); if (node) node.hidden = hidden; };
  const latched = value("portable-lid-type") !== "lid_only";
  hide("portable-latch-count-row", !latched);
  hide("portable-hinge-count-row", !latched);
  hide("portable-handle-row", !latched);
  if (!latched) {
    const handle = document.getElementById("portable-handle");
    if (handle) handle.value = "false";
  }
  const location = value("portable-label-location");
  hide("portable-label-text-row", location === "none");
  hide("portable-front-label-style-row", location !== "front");
};

// R66: "Finished outside" for the Storage Box setup draft. The number comes
// from the server's read-only summary (assembled_envelope_mm); there is no
// second formula here. A newer draft always wins over an older response.
SP.setupOutsideToken = 0;
SP.refreshSetupOutside = () => {
  const label = document.getElementById("portable-outside-label");
  const value = document.getElementById("portable-outside-readout");
  const fitWarn = document.getElementById("portable-printer-fit");
  // The readout box holds only the Finished outside row, so it shows only
  // while that row does.
  const readout = document.getElementById("portable-readout");
  if (!label || !value) return;
  const hideOutside = () => { label.hidden = true; value.hidden = true; value.textContent = ""; if (readout) readout.hidden = true; };
  const hideFit = () => { if (fitWarn) { fitWarn.hidden = true; fitWarn.textContent = ""; } };
  const token = ++SP.setupOutsideToken;
  clearTimeout(SP.setupOutsideTimer);
  const num = id => Number(document.getElementById(id)?.value);
  const x = SP.snap(num("portable-x")), y = SP.snap(num("portable-y")), z = num("portable-z");
  const minField = Number(state.catalog?.b4b_rules?.min_field_mm);
  const minHeight = Number(state.catalog?.b4b_rules?.min_secure_height_mm);
  const valid = [x, y, z].every(n => Number.isFinite(n) && n > 0) && x >= minField && y >= minField && z >= minHeight;
  if (!valid || SP.setupKind !== "portable") { hideOutside(); hideFit(); return; }
  const space = { kind: "portable", name: "Storage Box", x, y, z, storage_box: SP.readStorageBoxForm() };
  SP.setupOutsideTimer = setTimeout(async () => {
    try {
      const result = await api("/api/space/structural-design", {
        space,
        // Fix 111 N3: hosted supplies the printer profile so the server can
        // warn when the case will not fit the printer; local reads its own.
        ...(state.runtime.hosted ? { printer_profile: PrinterProfile.current() } : {}),
      });
      if (token !== SP.setupOutsideToken) return;
      const size = result.summary?.assembled_envelope_mm;
      if (!Array.isArray(size) || size.length < 3) { hideOutside(); hideFit(); return; }
      value.textContent = `${size.map(n => fmt(Number(n))).join(" × ")} mm`;
      label.hidden = false; value.hidden = false; if (readout) readout.hidden = false;
      // Fix 111 N3: nearby nonblocking printer-size warning, like Storage
      // Drawers - visible at the size input, creation stays allowed.
      const fitError = result.summary?.first_fit_error;
      if (fitWarn && result.summary?.fits_printer === false && fitError) {
        fitWarn.textContent = fitError;
        fitWarn.hidden = false;
      } else {
        hideFit();
      }
    } catch (_error) {
      if (token === SP.setupOutsideToken) { hideOutside(); hideFit(); }
    }
  }, 250);
};

SP.readStorageBoxForm = () => {
  const value = id => document.getElementById(id)?.value;
  const latched = value("portable-lid-type") !== "lid_only";
  const location = value("portable-label-location") || "none";
  const labelled = location !== "none";
  return {
    secure_lid: latched,
    latch_count: latched ? (value("portable-latch-count") || "1") : "1",
    hinge_count: latched ? (value("portable-hinge-count") === "1" ? "1" : "2") : "2",
    hinge_type: latched ? SP.storageBoxHingeType : "screw",
    lid_headroom_mm: parseFloat(value("portable-lid-snugness")) || 1,
    edge_bevel: SP.storageBoxEdgeBevel,
    label_enabled: labelled,
    label_text: labelled ? String(value("portable-label-text") || "").trim() : "",
    label_location: labelled ? location : "top",
    front_label_style: value("portable-front-label-style") === "wavy" ? "wavy" : "flat",
    stacking: value("portable-stacking") === "true",
    handle: latched && value("portable-handle") === "true",
    wall_mm: Number(value("portable-wall")),
    base_mm: Number(value("portable-base")),
  };
};

// ------------------------------------------------------------ structural outputs
//
// Space Actions own the outputs a Space itself makes: a Storage Box case, or a
// Surface Base Trim. Each is a transient design built by the server from the
// authoritative Space definition; it never becomes an Inventory row.

SP.structuralKind = () => {
  const kind = state.folderMode === "space" ? state.activeSpace?.kind : null;
  if (kind === "portable" || kind === "box") return "storage_box";
  if (kind === "surface") return "base_trim";
  if (kind === "storage_drawers") return "storage_drawers";
  return null;
};
SP.structuralLabel = kind => kind === "storage_box" ? "Storage Box" : kind === "storage_drawers" ? "Cabinet" : "Base Trim";
SP.structuralInfo = { key: "", data: null, error: "" };
SP.structuralBusy = false;
SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP = "Printing needs local Wavefinity and a slicer. Use Export to get the files.";
SP.HOSTED_SURFACE_PRINT_TOOLTIP = "Printing needs local Wavefinity and a slicer. Use Export to get the files.";

// The derived outside/capacity summary of a Storage Box, from the server.
SP.refreshStructuralSummary = async () => {
  const space = state.activeSpace;
  if (SP.structuralKind() !== "storage_box" || !space) return;
  const key = JSON.stringify(space);
  if (SP.structuralInfo.key === key) return;
  SP.structuralInfo = { key, data: null, error: "" };
  try {
    const result = await api("/api/space/structural-design", { space: clone(space) });
    if (SP.structuralInfo.key !== key) return;
    SP.structuralInfo.data = result.summary;
  } catch (error) {
    if (SP.structuralInfo.key !== key) return;
    SP.structuralInfo.error = error.message;
  }
  SP.renderSpaceInfo();
};

SP.runStructural = async (mode, event) => {
  const kind = SP.structuralKind();
  if (kind === "storage_drawers") return SP.runCabinetStructural(mode);
  if (!kind || SP.structuralBusy) return;
  const label = SP.structuralLabel(kind);
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    // A dirty structural Design draft must be settled before output is
    // manufactured from the accepted Space: Save Changes, Discard, or the
    // output stays blocked while the user keeps editing.
    if (!(await SP.confirmLeaveStructuralEditor())) return;
    const hosted = Boolean(state.runtime.hosted);
    if (hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
    // Hosted Wavefinity has no local slicer: Print is disabled there (Save stays
    // available) and never quietly becomes a Save.
    if (mode === "print" && hosted) {
      toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000);
      return;
    }
    const printing = mode === "print";
    if (printing && !state.slicer?.available) {
      toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
      return;
    }
    // Fix 056 D: hidden maintainer shortcut restored at its new owner - local
    // Base Trim Print only. Ctrl+Shift+click sends the existing production
    // joint-fit sample instead of the full Base Trim; Storage Box Print has no
    // special behavior for the same chord.
    const jointTest = printing && kind === "base_trim" && Boolean(event?.ctrlKey && event?.shiftKey);
    // Built from the Space definition alone, so the Designer's autosave is not involved.
    const context = DL.spaceContext();
    const space = clone(state.activeSpace);
    const payload = {
      space, output: state.output,
      // Base Trim's bed is the one global printer profile; hosted supplies it.
      ...(kind === "base_trim" && hosted ? { printer_profile: PrinterProfile.current() } : {}),
      ...(jointTest ? { joint_test_sample: true } : {}),
    };
    if (printing) {
      const result = await apiSideEffect("/api/space/structural-print", { ...payload, slicer_path: state.slicer?.path || null });
      DL.requireSpaceContext(context);
      if (result.partial) {
        // Files are a real side effect even though the slicer step failed -
        // never claim "Sent to Bambu Studio" when it did not open.
        toast(result.error || `${label} files were saved, but the slicer did not open.`, true, 8000);
      } else {
        const names = (result.files || []).map(file => String(file).split(/[\\/]/).pop());
        toast(`Sent to ${state.slicer?.name || "the slicer"}!\n${names.join("\n")}`, false, 7000);
      }
    }
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast(`${label} finished for the Space you left. Nothing was changed in the current Space.`);
    } else if (/different name to avoid overwriting/i.test(String(error.message))) {
      toast(`A file with that ${label} name already exists in this folder. Rename or move it, then try again.`, true, 8000);
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.renderSpaceInfo();
  }
};
SP.saveStructural = () => {
  if (SP.structuralKind() === "base_trim") return SP.saveBaseTrim();
  if (SP.structuralKind() === "storage_box") return SP.printStorageBox("export");
};
SP.printStorageBox = async (mode = "print") => {
  if (SP.structuralBusy || SP.structuralKind() !== "storage_box") return;
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    // A dirty structural Design draft must be settled before output is
    // manufactured from the accepted Space: Save Changes, Discard, or the
    // output stays blocked while the user keeps editing.
    if (!(await SP.confirmLeaveStructuralEditor())) return;
    if (mode === "print" && state.runtime.hosted) {
      toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000);
      return;
    }
    if (mode === "export") {
      const context = DL.spaceContext();
      const result = await apiSideEffect("/api/space/structural-generate", {
        space: clone(state.activeSpace), output: state.output,
      });
      DL.requireSpaceContext(context);
      if (!result.files?.length) throw new Error("The server did not return any print files.");
      if (state.runtime.hosted) {
        for (const file of result.files) {
          const response = await fetch(file.url);
          if (!response.ok) throw new Error(`Could not download ${file.name}.`);
          await WFFileSystem.writeBlob(null, file.name, await response.blob());
        }
      }
      toast(state.runtime.hosted ? "Storage Box files downloaded." : `Storage Box files saved to ${result.output || state.output}.`, false, 7000);
      return;
    }
    if (!state.slicer?.available) {
      toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
      return;
    }
    const context = DL.spaceContext();
    DL.requireSpaceContext(context);
    if (typeof flushSpaceDesignAutosave === "function" &&
        !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
    DL.requireSpaceContext(context);
    if (!(await DL.save())) return;
    DL.requireSpaceContext(context);
    const result = await apiSideEffect("/api/space/storage-box-print", {
      output: context.output, space_id: context.spaceId,
      slicer_path: state.slicer?.path || null,
    });
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) toast(result.error || "Storage Box print stopped before Bambu Studio opened.", true, 10000);
    else toast(`Sent Storage Box + Bins to ${state.slicer?.name || "the slicer"}!\n${(result.files || []).map(file => String(file).split(/[\\/]/).pop()).join("\n")}`, false, 8000);
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast("Storage Box print belongs to the Space you left. The current Space was not changed.");
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.renderSpaceInfo();
  }
};
SP.printStructural = event => {
  const kind = SP.structuralKind();
  if (kind === "storage_box") return SP.printStorageBox();
  if (kind === "base_trim") return SP.printSurface(event);
  return SP.runStructural("print", event);
};

SP.renderStructuralActions = () => {
  if (typeof WS !== "undefined" && WS.syncOutput) WS.syncOutput();
  const box = document.getElementById("space-structural");
  if (!box) return;
  const kind = SP.structuralKind();
  // The cabinet's Save/Print live in its workspace panel.
  box.hidden = !kind || kind === "storage_drawers";
  if (!kind || kind === "storage_drawers") return;
  const save = document.getElementById("space-structural-save");
  const print = document.getElementById("space-structural-print");
  const hosted = Boolean(state.runtime.hosted);
  save.hidden = false;
  save.textContent = "Export";
  save.title = "Create files for you to save.";
  print.textContent = "Print";
  const summary = document.getElementById("space-structural-summary");
  if (summary) {
    const text = kind === "base_trim" ? SP.baseTrimSummaryText() : "";
    summary.hidden = !text;
    summary.textContent = text;
  }
  if (kind === "base_trim") SP.refreshBaseTrimSummary();
  document.getElementById("space-structural-saving").hidden = !SP.structuralBusy;
  save.disabled = SP.structuralBusy;
  print.disabled = SP.structuralBusy;
  print.title = hosted ? (kind === "base_trim" ? SP.HOSTED_SURFACE_PRINT_TOOLTIP : SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP) : "";
  // Show the hosted printing limitation beside the action.
  const printReason = document.getElementById("space-structural-print-reason");
  if (printReason) {
    printReason.hidden = !hosted;
    printReason.textContent = hosted
      ? "Printing is unavailable on hosted Wavefinity: there is no local slicer here."
      : "";
  }
};

// Story 2519: a Storage Box holds one full interior bin or ordinary bins, never
// both. The mode follows the contents and is never stored: "empty" (no ordinary
// rows), "full_interior" (a placed ordinary row whose size is the fit that
// insideBinFitForStorageBox computes), or "ordinary" (ordinary rows, none of
// them the full interior bin).
// Classification uses the saved bin body, not its lid/handle print envelope.
SP.binMatchesInteriorFit = (one, fit) => {
  const design = DL.layout?.design_specs?.[one.id];
  const body = design?.box || design;
  return !fit.error && ["x", "y", "z"].every(axis =>
    Number(body?.[axis] ?? one[axis]) === Number(fit[axis]));
};
SP.storageBoxBinContents = () => {
  if (SP.structuralKind() !== "storage_box" || typeof DL === "undefined" || !DL.layout) return "empty";
  const rows = DL.bins.filter(DL.isOrdinary);
  if (!rows.length) return "empty";
  const fit = insideBinFitForStorageBox(state.activeSpace, freshDesignForCurrentFolder());
  const full = !fit.error && rows.some(one =>
    DL.isPlaced(one.id) && SP.binMatchesInteriorFit(one, fit));
  return full ? "full_interior" : "ordinary";
};

SP.drawerBinContents = () => {
  if (!DL.active || !DL.layout || !DL.isStorageDrawers()) return "empty";
  const drawer = DL.drawer();
  const rows = (drawer.placements || []).map(p => DL.bin(p.bin)).filter(one => one && DL.isOrdinary(one));
  if (!rows.length) return "empty";
  const limits = cabinetActiveLimits();
  const fit = insideBinFitForStorageBox({ ...limits, z: Math.floor(limits.z - 2) }, freshDesignForCurrentFolder());
  return rows.some(one => SP.binMatchesInteriorFit(one, fit))
    ? "full_interior" : "ordinary";
};

// Presence of the three Storage Box actions, re-derived on every Space render and
// content change. Make full interior bin is offered only for an empty box; New Bin
// and Duplicate Bin go away while a full interior bin is present.
SP.syncStorageBoxBinActions = () => {
  const contents = SP.storageBoxBinContents();
  const makeInsideBin = document.getElementById("space-make-inside-bin");
  if (makeInsideBin) makeInsideBin.hidden = SP.structuralKind() !== "storage_box" || contents !== "empty";
  const isDrawer = DL.active && DL.layout && DL.isStorageDrawers();
  const drawerContents = isDrawer ? SP.drawerBinContents() : "empty";
  const drawerAction = document.getElementById("designer-make-drawer-bin");
  if (drawerAction) drawerAction.hidden = !isDrawer || drawerContents !== "empty";
  const fullInterior = contents === "full_interior" || (isDrawer && drawerContents === "full_interior");
  const newBin = document.getElementById("designer-new-bin");
  if (newBin) newBin.hidden = fullInterior;
  const stagingNew = document.querySelector("[data-staging-new-bin]");
  if (stagingNew) stagingNew.hidden = isDrawer && drawerContents === "full_interior";
  const duplicate = document.getElementById("designer-duplicate");
  if (duplicate) duplicate.hidden = fullInterior;
};

