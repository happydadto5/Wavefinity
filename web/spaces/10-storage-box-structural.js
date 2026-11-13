"use strict";

// ------------------------------------------------------------ Storage Box case settings
//
// A Storage Box Space owns its case: `space.storage_box` (see
// organizer_inventory.normalise_storage_box). These helpers fill and read the
// case settings on the Space setup/Edit form.

SP.storageBoxDefaults = fieldWidth => ({
  grid: "wavefinity", built_in_grid: "floor", seated_lift_mm: null,
  secure_lid: true, latch_count: fieldWidth > 96 ? "2" : "1", hinge_count: "2", lid_headroom_mm: 1, latch_tightness: "default",
  label_enabled: false, label_text: "", label_location: "top", front_label_style: "flat", label_size: "default",
  stacking: false, grid_stacking: false, handle: false,
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
// Case options live in Design; basic setup edits must preserve grid stacking.
SP.storageBoxGridStacking = false;

// portable-x is Interior width, not the finished outside case size.
// Match the normalized child-bin field passed to the engine.
SP.storageBoxSetupFieldWidth = () => SP.storageBoxSnap(Number(document.getElementById("portable-x")?.value));

// Story 2975: the Grid and Floor choices of the Storage Box setup. The grid is
// chosen at creation and immutable afterwards; Floor/None only exists for a
// Gridfinity pitch. The nominal field is always whole cells at the pitch.
SP.STORAGE_BOX_PITCHES = { wavefinity: 7, gridfinity_half: 21, gridfinity: 42 };
SP.storageBoxGrid = () => {
  const value = document.getElementById("portable-grid")?.value;
  return Object.hasOwn(SP.STORAGE_BOX_PITCHES, value) ? value : "wavefinity";
};
SP.storageBoxPitch = (grid = SP.storageBoxGrid()) => {
  const row = (state.catalog?.grids || []).find(one => one.value === grid);
  return Number(row?.pitch_mm) || SP.STORAGE_BOX_PITCHES[grid] || Number(state.catalog?.base_unit || 7);
};
SP.storageBoxFloor = () => SP.storageBoxGrid() === "wavefinity" ? null
  : (document.getElementById("portable-floor")?.value === "none" ? "none" : "floor");
SP.storageBoxMinimumField = () => SP.storageBoxGrid() !== "wavefinity"
  && document.getElementById("portable-lid-type")?.value === "lid_only"
  ? SP.storageBoxPitch() : Number(state.catalog?.b4b_rules?.min_field_mm);
// The nearest legal whole-cell field at the chosen pitch (the spec's rounding
// rule: nearest positive whole cells, never fewer than the box's minimum field).
SP.storageBoxSnap = mm => {
  const grid = SP.storageBoxGrid();
  if (grid === "wavefinity") return SP.snap(mm);
  const pitch = SP.storageBoxPitch(grid);
  const minimum = SP.storageBoxMinimumField() || 0;
  return Math.max(1, Math.ceil(minimum / pitch - 1e-9), Math.floor(mm / pitch + 0.5)) * pitch;
};
SP.syncStorageBoxGrid = () => {
  const gridfinity = SP.storageBoxGrid() !== "wavefinity";
  const row = document.getElementById("portable-floor-row");
  if (row) row.hidden = !gridfinity;
  document.getElementById("portable-lift-row").hidden = !gridfinity || SP.storageBoxFloor() !== "none";
  const note = document.getElementById("portable-grid-note");
  if (note) {
    const editing = Boolean(document.getElementById("portable-grid")?.disabled);
    const parts = [];
    if (gridfinity) parts.push(`Width and depth are whole ${fmt(SP.storageBoxPitch())} mm cells.`);
    if (gridfinity && SP.storageBoxFloor() === "none") {
      parts.push("With no floor the box prints a plain cavity, a little larger than the nominal grid, for a baseplate you supply.");
    }
    if (editing) parts.push("Grid and floor are set when the Space is created and cannot be changed.");
    note.textContent = parts.join(" ");
    note.hidden = !parts.length;
  }
};
// Choosing a pitch re-derives the offered field from what was already entered.
SP.onStorageBoxGridChosen = () => {
  SP.syncStorageBoxGrid();
  for (const id of ["portable-x", "portable-y"]) {
    const input = document.getElementById(id);
    const entered = input && input.value.trim() ? Number(input.value) : NaN;
    if (Number.isFinite(entered) && entered > 0) input.value = String(SP.storageBoxSnap(entered));
  }
  SP.updateReadouts();
};
SP.syncNewStorageBoxLatchDefault = () => {
  if (!SP.newStorageBox) return;
  const select = document.getElementById("portable-latch-count");
  if (select) select.value = SP.storageBoxDefaults(SP.storageBoxSetupFieldWidth()).latch_count;
};

SP.fillStorageBoxForm = box => {
  SP.newStorageBox = !box;
  document.getElementById("portable-lift").value = box?.seated_lift_mm ?? "";
  const one = { ...SP.storageBoxDefaults(SP.storageBoxSetupFieldWidth()), ...(box || {}) };
  SP.storageBoxEdgeBevel = box ? (box.edge_bevel || "none") : "default";
  SP.storageBoxHingeType = box && box.hinge_type === "piano" ? "piano" : "screw";
  SP.storageBoxGridStacking = Boolean(one.grid_stacking);
  const set = (id, value) => { const node = document.getElementById(id); if (node) node.value = String(value); };
  set("portable-lid-type", one.secure_lid === false ? "lid_only" : "latched");
  set("portable-lid-snugness", one.lid_headroom_mm);
  set("portable-latch-tightness", ["loose", "default", "tight"].includes(one.latch_tightness) ? one.latch_tightness : "default");
  set("portable-stacking", Boolean(one.stacking));
  set("portable-latch-count", ["1", "2"].includes(String(one.latch_count)) ? String(one.latch_count) : "1");
  set("portable-hinge-count", String(one.hinge_count) === "1" ? "1" : "2");
  set("portable-handle", Boolean(one.handle) && one.secure_lid !== false);
  set("portable-label-location", one.label_enabled ? (one.label_location === "front" ? "front" : "top") : "none");
  set("portable-label-text", one.label_text || "");
  set("portable-label-size", one.label_size || "default");
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
  hide("portable-latch-tightness-row", !latched);
  hide("portable-hinge-count-row", !latched);
  hide("portable-handle-row", !latched);
  if (!latched) {
    const handle = document.getElementById("portable-handle");
    if (handle) handle.value = "false";
  }
  const location = value("portable-label-location");
  hide("portable-label-text-row", location === "none");
  hide("portable-label-size-row", location === "none");
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
  const x = SP.storageBoxSnap(num("portable-x")), y = SP.storageBoxSnap(num("portable-y")), z = num("portable-z");
  const minField = SP.storageBoxMinimumField();
  const minHeight = Number(state.catalog?.b4b_rules?.min_secure_height_mm);
  const valid = [x, y, z].every(n => Number.isFinite(n) && n > 0) && x >= minField && y >= minField && z >= minHeight;
  if (!valid || SP.setupKind !== "portable") { hideOutside(); hideFit(); return; }
  const space = { kind: "portable", name: "Storage Box", x, y, z, ...SP.storageBoxGridFields(), storage_box: SP.readStorageBoxForm() };
  SP.setupOutsideTimer = setTimeout(async () => {
    try {
      const result = await api("/api/space/structural-design", {
        space,
        // Fix 111 N3: hosted supplies the printer profile so the server can
        // warn when the case will not fit the printer; local reads its own.
        printer_profile: PrinterProfile.current(), printer_profile_configured: PrinterProfile.configured(),
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

// The Space-level grid fields of the setup form: the grid always, the floor
// only for a Gridfinity pitch (it has no meaning on the Wavefinity grid).
SP.storageBoxGridFields = () => ({
  grid: SP.storageBoxGrid(),
  ...(SP.storageBoxFloor() ? { built_in_grid: SP.storageBoxFloor() } : {}),
});

SP.readStorageBoxForm = () => {
  const value = id => document.getElementById(id)?.value;
  const latched = value("portable-lid-type") !== "lid_only";
  const location = value("portable-label-location") || "none";
  const labelled = location !== "none";
  return {
    ...SP.storageBoxGridFields(),
    seated_lift_mm: SP.storageBoxFloor() === "none" && value("portable-lift").trim() !== ""
      ? Number(value("portable-lift")) : null,
    secure_lid: latched,
    latch_count: value("portable-latch-count") || "1",
    hinge_count: latched ? (value("portable-hinge-count") === "1" ? "1" : "2") : "2",
    hinge_type: latched ? SP.storageBoxHingeType : "screw",
    lid_headroom_mm: parseFloat(value("portable-lid-snugness")) || 1,
    latch_tightness: ["loose", "default", "tight"].includes(value("portable-latch-tightness")) ? value("portable-latch-tightness") : "default",
    edge_bevel: SP.storageBoxEdgeBevel,
    label_enabled: labelled,
    label_text: labelled ? String(value("portable-label-text") || "").trim() : "",
    label_location: labelled ? location : (SP.storageBoxGridStacking ? "none" : "top"),
    front_label_style: value("portable-front-label-style") === "wavy" ? "wavy" : "flat",
    label_size: value("portable-label-size") || "default",
    stacking: value("portable-stacking") === "true",
    grid_stacking: SP.storageBoxGridStacking,
    handle: latched && value("portable-handle") === "true",
    wall_mm: Number(value("portable-wall")),
    base_mm: SP.storageBoxFloorBase(Number(value("portable-base")), value("portable-stacking") === "true"),
  };
};

// A Floor (the box's own raised socket grid) needs at least the catalog's floor
// build; a Wavefinity box and a Gridfinity box with no floor keep the chosen base.
SP.storageBoxFloorBase = (chosen, stacking) => {
  if (SP.storageBoxFloor() !== "floor") return chosen;
  const row = (state.catalog?.grids || []).find(one => one.value === SP.storageBoxGrid());
  const minimum = Number(stacking ? row?.container_floor_stacking_build_mm : row?.container_floor_build_mm);
  return Number.isFinite(minimum) && minimum > chosen ? minimum : chosen;
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
SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP = "Print prepares a local 3MF to open in Bambu Studio.";
SP.HOSTED_SURFACE_PRINT_TOOLTIP = "Print prepares a local 3MF to open in Bambu Studio.";

SP.beginStructuralReport = working => {
  const report = beginOutputReport(working, "container", []);
  SP.structuralBusyLabel = working;
  const update = report.working;
  report.working = message => {
    SP.structuralBusyLabel = message;
    update(message);
    SP.renderSpaceInfo();
  };
  report.options.onStillFinishing = () => report.working("Still working…");
  return report;
};

// B11: folder writes use the captured Space; Print only prepares a file.
SP.structuralSnapshotKey = value => JSON.stringify(value, (_key, item) =>
  item && typeof item === "object" && !Array.isArray(item)
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, item[key]])) : item);
SP.structuralBlob = file => {
  const blob = WFLocalFiles.claim(file.local_file_id);
  if (!blob?.size) throw new Error(`The local file ${file.name} expired. Prepare it again.`);
  return blob;
};

SP.requireStructuralFolder = async (handle, payload, context) => {
  DL.requireSpaceContext(context);
  const { current } = await SP.readMetadata(handle);
  DL.requireSpaceContext(context);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== payload.space_id ||
      SP.structuralSnapshotKey(meta.space) !== SP.structuralSnapshotKey(payload.space)) {
    throw new Error("The saved Space changed while files were prepared. Nothing was applied.");
  }
};

SP.saveBrowserStructure = async (result, payload, context) => {
  DL.requireSpaceContext(context);
  if (SP.structuralSnapshotKey(state.activeSpace) !== SP.structuralSnapshotKey(payload.space)) throw DL.staleSpaceError();
  await SP.requireStructuralFolder(state.browserFolder.handle, payload, context);
  const exported = { ...result, files: result.structural_files || result.files };
  if (result.manifest && payload.space.kind === "storage_drawers") {
    return SP.hostedCabinetSave(payload, context, {}, exported);
  }
  if (result.manifest && payload.space.kind === "surface") {
    return SP.hostedBaseTrimSave(payload, context, {}, exported);
  }
  const files = await saveGeneratedFiles(exported, { kind: "structural", requireCurrent: () => DL.requireSpaceContext(context) });
  return { files };
};

SP.browserStructural = async ({ mode = "print", combined = false, event = null } = {}) => {
  if (SP.structuralBusy) return;
  const kind = SP.structuralKind();
  const label = SP.structuralLabel(kind);
  const report = SP.beginStructuralReport(mode === "print" ? "Preparing Print…" : `Saving ${label}…`);
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  let result;
  try {
    if (!(await SP.confirmLeaveStructuralEditor())) return;
    if (!state.browserFolder?.handle || !state.activeSpaceId) throw new Error("Choose a Space folder before saving files.");
    const context = DL.spaceContext();
    if (combined) {
      if (typeof flushSpaceDesignAutosave === "function" && !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
      DL.requireSpaceContext(context);
      if (!(await DL.save())) return;
    }
    DL.requireSpaceContext(context);
    const epoch = WFLocalAPI.designEpoch;
    const payload = { space: clone(state.activeSpace), space_id: state.activeSpaceId,
      printer_profile: PrinterProfile.current(), printer_profile_configured: PrinterProfile.configured(),
      ...(kind === "base_trim" && mode === "print" && event?.ctrlKey && event?.shiftKey ? { joint_test_sample: true } : {}) };
    const current = () => {
      DL.requireSpaceContext(context);
      if (WFLocalAPI.designEpoch !== epoch || SP.structuralSnapshotKey(state.activeSpace) !== SP.structuralSnapshotKey(payload.space)) throw DL.staleSpaceError();
      return true;
    };
    const path = combined ? (kind === "storage_box" ? "/api/space/storage-box-print"
      : kind === "base_trim" ? "/api/space/surface-print" : "/api/space/structural-print-combined")
      : `/api/space/structural-${mode === "print" ? "print" : "generate"}`;
    result = combined
      ? await SP.inventoryRequest(path, payload, { context, sideEffect: true, buildOnly: true, ...report.options })
      : await apiSideEffect(path, payload, report.options);
    current();
    // A changed inventory must not install a stale structural snapshot either.
    if (combined && (await SP.readInventoryFor(state.browserFolder)) !== result.original_inventory_text) {
      throw new Error("Inventory changed while Print was prepared. Nothing was applied.");
    }
    const saved = await SP.saveBrowserStructure(result, payload, context);
    current();
    if (combined) {
      const applied = await SP.inventoryRequest("/api/drawer/load", {}, { context,
        preparedResult: result, expectedInventoryText: result.original_inventory_text, promotionCurrent: current });
      DL.adoptBatchResult(applied);
      DP.renderInventory(true); DL.emit(); DL.requestReport();
    } else if (result.print_file) {
      await saveGeneratedFiles({ files: [result.print_file] }, { kind: "structural", requireCurrent: current });
    }
    if (result.partial) { report(result.error || "Some files were saved, but Print could not finish.", true); return; }
    const notes = `${kind === "storage_box" ? SP.storageBoxMaterialNote(payload.space) : ""}${saved.warnings?.length ? "\n" + saved.warnings.join("\n") : ""}`;
    if (mode !== "print") { report(`Saved ${label}: ${outputFileNames(saved.files)}${notes}`, false); return; }
    current();
    const confirmed = combined
      ? await DL.confirmDrawerPrint(result, context, epoch)
      : await confirmOpenedInBambuStudio(result.handoff.filename, "Saved in your selected Space folder.");
    current();
    if (!confirmed) { report(`Print file ready: ${result.handoff.filename}. Printed status is unchanged.`); return; }
    if (combined && confirmed.bins) DL.adoptBatchResult(confirmed);
    if (!payload.joint_test_sample && typeof WS !== "undefined") WS.markContainerPrinted();
    DP.renderInventory(true); DL.emit(); DL.requestReport();
    report(`Confirmed opening ${result.handoff.filename} in Bambu Studio.${notes}`, false);
  } catch (error) {
    report(DL.isStaleSpaceError(error) ? "The Space changed. The current Space was not changed by this Print." : error.message, true);
  } finally {
    for (const file of [...(result?.structural_files || result?.files || []), result?.print_file].filter(Boolean)) {
      if (file.local_file_id) WFLocalFiles.discard(file.local_file_id);
    }
    report.finish(); SP.structuralBusy = false; SP.structuralBusyLabel = "";
    if (SP.cabinetInfo) SP.cabinetInfo.commitSerial += 1;
    if (SP.baseTrimInfo) SP.baseTrimInfo.serial += 1;
    SP.renderSpaceInfo();
  }
};

SP.runStructural = (mode, event) => SP.browserStructural({ mode, event });

SP.saveStructural = () => {
  if (SP.structuralKind() === "base_trim") return SP.saveBaseTrim();
  if (SP.structuralKind() === "storage_box") return SP.printStorageBox("export");
};
SP.storageBoxMaterialNote = space => space?.storage_box?.secure_lid === false
  ? ""
  : " The latch holds by spring; ordinary PLA softens in heat at about 55–60 °C, such as in a closed car or a bag in the sun, and can lose that spring first. For a box that will be carried or left in heat, a heat-tolerant material is safer."
SP.printStorageBox = (mode = "print") => SP.browserStructural({ mode, combined: mode === "print" });

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
  // The cabinet's Save/Print live in its workspace panel. A Storage Box's Print and
  // Export live on its tree row (Story 2721), so this panel serves only Base Trim.
  box.hidden = !kind || kind === "storage_drawers" || kind === "storage_box";
  if (box.hidden) return;
  const save = document.getElementById("space-structural-save");
  const print = document.getElementById("space-structural-print");
  const hosted = Boolean(state.runtime.hosted);
  save.hidden = false;
  save.textContent = SP.structuralBusy ? SP.structuralBusyLabel : "Export";
  save.title = "Create files for you to save.";
  print.textContent = SP.structuralBusy ? SP.structuralBusyLabel : "Print";
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
    printReason.hidden = true;
    printReason.textContent = hosted
      ? "Print prepares a local 3MF to open in Bambu Studio."
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
  const fit = insideBinFitForStorageBox({ ...limits, z: Math.floor(limits.z) }, freshDesignForCurrentFolder());
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

