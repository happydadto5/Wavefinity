"use strict";

SP.wire = () => {
  wireInfoButtons();
  $("#space-cancel-edit")?.addEventListener("click", async () => {
    if (await SP.confirmDiscardSetup()) SP.cancelInlineEdit();
  });
  document.querySelectorAll("#welcome-close, #welcome-resume-close, #space-unsupported-close, #space-type-cards-close, #space-tutorial-close")
    .forEach(el => el?.addEventListener("click", SP.close));
  // A changed cabinet setup asks before it is discarded: X, backdrop, Escape and Back.
  document.getElementById("space-form-close")?.addEventListener("click", SP.requestClose);
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.requestClose(); });
  SP.dialog().addEventListener("cancel", event => {
    if (SP.setupIsDirty()) { event.preventDefault(); SP.requestClose(); }
  });
  document.getElementById("printer-settings-close")?.addEventListener("click", SP.closePrinterSettings);
  document.getElementById("printer-settings-close-x")?.addEventListener("click", SP.closePrinterSettings);
  const welcomeCreate = document.getElementById("welcome-create");
  if (welcomeCreate) welcomeCreate.addEventListener("click", SP.beginCreateNew);
  const welcomeOpen = document.getElementById("welcome-open");
  if (welcomeOpen) welcomeOpen.addEventListener("click", () => SP.run(SP.openExisting));
  document.querySelectorAll(".welcome-storage-change")
    .forEach(el => el.addEventListener("click", SP.changeStorageParent));
  document.getElementById("space-storage-close")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-cancel")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-conflict-cancel")?.addEventListener("click", SP.cancelStorageChange);
  document.getElementById("space-storage-repick")?.addEventListener("click", () => SP.run(SP.pickStorageParent));
  document.getElementById("space-storage-conflict-repick")?.addEventListener("click", () => SP.run(SP.pickStorageParent));
  document.getElementById("space-storage-apply")?.addEventListener("click", () => {
    const chosen = document.querySelector('input[name="space-storage-mode"]:checked');
    SP.applyStorageChange(chosen?.value === "switch" ? "switch" : "move");
  });
  document.getElementById("space-storage-use-existing")?.addEventListener("click", () => SP.applyStorageChange("use_existing"));
  const welcomeDesign = document.getElementById("welcome-design");
  if (welcomeDesign) welcomeDesign.addEventListener("click", () => {
    SP.clearSetupContext();
    SP.run(SP.startUntyped);
  });
  const tutorialOpen = document.getElementById("space-tutorial-open");
  if (tutorialOpen) tutorialOpen.addEventListener("click", SP.showTutorial);
  const tutorialBack = document.getElementById("space-tutorial-back");
  if (tutorialBack) tutorialBack.addEventListener("click", SP.showTypeCards);
  const welcomeResumeContinue = document.getElementById("welcome-resume-continue");
  if (welcomeResumeContinue) welcomeResumeContinue.addEventListener("click", () => SP.run(SP.confirmResume));
  document.getElementById("welcome-resume-create")?.addEventListener("click", SP.beginCreateNew);
  const welcomeResumeSwitch = document.getElementById("welcome-resume-switch");
  if (welcomeResumeSwitch) welcomeResumeSwitch.addEventListener("click", () => {
    // SP.run() calls the task immediately, so showDirectoryPicker() is still
    // reached from the trusted click.
    SP.run(SP.openExisting);
  });
  document.querySelectorAll(".type-card").forEach(el => {
      el.addEventListener("click", () => {
          // A stale inventory candidate may prefill only its own card type;
          // choosing a different type never inherits its dimensions.
          const kind = el.dataset.kind;
          if (kind === "storage_drawers" && SP.configureData) return;
          const candidate = SP.setupPrefillSpace;
          const candidateKind =
            candidate?.kind === "box" ? "portable" : candidate?.kind;
          SP.showSetup(kind, candidateKind === kind ? candidate : null);
      });
  });
  const untypedStart = document.getElementById("space-untyped-start");
  if (untypedStart) untypedStart.addEventListener("click", () => SP.run(SP.startUntyped));
  const spaceBack = document.getElementById("space-back");
  if (spaceBack) spaceBack.addEventListener("click", async () => {
    if (await SP.confirmDiscardSetup()) SP.showTypeCards();
  });
  const spaceForm = document.getElementById("space-form");
  if (spaceForm) {
    // Defensive only: typing/Enter in a field is never permission to create.
    spaceForm.addEventListener("submit", event => event.preventDefault());
  }

  document.getElementById("space-create")
    ?.addEventListener("click", () => SP.run(SP.create));

  document.getElementById("space-save-changes")
    ?.addEventListener("click", () => SP.run(SP.updateSpace));
  const colOpen = document.getElementById("space-collision-open");
  if (colOpen) colOpen.addEventListener("click", () => SP.run(async () => {
    // The collision prompt can be reached by a Space that still needs its
    // one-time setup pass (needs_setup=true) - route into the same explicit
    // setup flow rather than opening it as-is - see Fix 004 Correction 7.B.
    const folder = SP.collisionFolder;
    const data = SP.collisionData;
    SP.collisionFolder = null;
    SP.collisionData = null;
    SP.collisionOrigin = null;
    if (data?.needs_setup) SP.enterSetupFor(folder, data);
    else await SP.afterPick(folder);
  }));
  const colChoose = document.getElementById("space-collision-choose");
  if (colChoose) colChoose.addEventListener("click", () => SP.run(async () => {
    // Route back to whichever flow actually opened this prompt - the
    // untyped flow must never fall into typed SP.create(), which expects a
    // Space form/name/type that was never filled in - see Fix 004
    // Correction 9.A. Transition off the collision prompt onto a stable
    // screen *before* clearing the state it depends on, so a cancelled
    // replacement folder picker never leaves a dead collision prompt on
    // screen with its target already erased - see Fix 004 Correction 10.B.
    const origin = SP.collisionOrigin;
    if (origin === "untyped") SP.showTypeCards();
    else { SP.showOnly("space-form"); SP.showDialog(); }
    SP.collisionFolder = null;
    SP.collisionData = null;
    SP.collisionOrigin = null;
    if (origin === "untyped") await SP.startUntyped();
    else await SP.create();
  }));

  const existingYes = document.getElementById("space-existing-inventory-yes");
  if (existingYes) existingYes.addEventListener("click", () => SP.run(async () => {
    SP.configureData = SP.pendingConfigureFolder;
    SP.pendingConfigureFolder = null;
    await SP.create();
  }));
  const existingNo = document.getElementById("space-existing-inventory-no");
  if (existingNo) existingNo.addEventListener("click", () => SP.run(async () => {
    SP.showOnly("space-form");
    SP.showDialog();
    SP.pendingConfigureFolder = null;
    await SP.create();
  }));

  const confYes = document.getElementById("space-configure-yes");
  if (confYes) confYes.addEventListener("click", SP.configureFolder);
  const confNo = document.getElementById("space-configure-no");
  if (confNo) confNo.addEventListener("click", () => SP.run(SP.useUntypedFolder));
  const confChoose = document.getElementById("space-configure-choose");
  if (confChoose) confChoose.addEventListener("click", () => SP.run(async () => {
    // Transition to a stable screen before clearing the selected target and
    // asking for another folder, so a cancelled picker never leaves the
    // user on a dead configure prompt referring to a cleared folder - see
    // Fix 004 Correction 10.A.
    SP.showHome();
    SP.configureData = null;
    await SP.openExisting();
  }));

  const welcomeRecent = document.getElementById("welcome-recent");
  if (welcomeRecent) welcomeRecent.addEventListener("click", event => {
    const forget = event.target.closest("[data-forget]");
    const open = event.target.closest("[data-index]");
    const one = SP.recent[Number(forget ? forget.dataset.forget : open?.dataset.index)];
    if (!one) return;
    if (forget) SP.run(async () => {
      if (state.runtime.hosted) {
        const kept = SP.recent.filter((_, index) =>
          index !== Number(forget.dataset.forget));
        SP.recent = kept;
        await SP.saveHostedRecent(kept);
      } else {
        SP.recent = (await api("/api/space/forget", {
          space_id: one.space_id || null, output: one.folder,
        })).recent || [];
      }
      SP.renderRecent();
    });
    else SP.run(() => SP.afterPick(
      state.runtime.hosted
        ? { handle: one.handle, name: one.folder_name || one.name }
        : one.folder
    ));
  });
  document.querySelectorAll("[data-other-spaces-list]").forEach(list =>
    list.addEventListener("click", event => {
      const button = event.target.closest("[data-other-index]");
      const one = SP.otherSpaces[Number(button?.dataset.otherIndex)];
      if (one) SP.run(() => SP.afterPick(one.folder));
    }));

  // Live Drawer/Portable readouts while the user types, not only when the
  // setup screen first opens - see Fix 004 Correction 6.G.
  ["drawer-x", "drawer-y", "drawer-z", "surface-x", "surface-y", "portable-x", "portable-y", "portable-z", "pegboard-x", "pegboard-y", "pegboard-holes-x", "pegboard-holes-y"].forEach(id => {
    const input = document.getElementById(id);
    if (input) input.addEventListener("input", SP.updateReadouts);
  });
  ["portable-lid-type", "portable-latch-count", "portable-handle", "portable-stacking", "portable-wall", "portable-base", "portable-lid-snugness", "portable-label-location", "portable-front-label-style"].forEach(id =>
    document.getElementById(id)?.addEventListener("change", SP.updateReadouts));
  ["portable-label-text"].forEach(id => document.getElementById(id)?.addEventListener("input", SP.updateReadouts));
  ["portable-lid-type", "portable-label-location"].forEach(id =>
    document.getElementById(id)?.addEventListener("change", SP.syncStorageBoxForm));
  // Surface: the maximum stays exactly as typed; the readout below shows the
  // resolved field and finished outside size.
  // Changing trim re-resolves the largest field from that same maximum, never
  // from a previously rounded result.
  document.getElementById("surface-trim")?.addEventListener("change", SP.updateReadouts);
  ["pegboard-standard", "pegboard-size-mode"].forEach(id => document.getElementById(id)?.addEventListener("change", SP.updateReadouts));
};

SP.updateReadouts = () => {
    const unit = state.catalog?.base_unit || 8;
    const kind = SP.setupKind;
    if (kind === "drawer") {
        const x = Number(document.getElementById("drawer-x").value);
        const y = Number(document.getElementById("drawer-y").value);
        const z = Number(document.getElementById("drawer-z").value);
        if (x > 0 && y > 0 && z > 0) {
            document.getElementById("drawer-readout").hidden = false;
            document.getElementById("drawer-size-readout").textContent = `${x} × ${y} × ${z} mm`;
            document.getElementById("drawer-capacity-readout").textContent = `${SP.drawerCapacity(x)} × ${SP.drawerCapacity(y)} units`;
        } else {
            document.getElementById("drawer-readout").hidden = true;
        }
    } else if (kind === "surface") {
        const trimKey = document.getElementById("surface-trim").value;
        const resolved = SP.resolveSurface(
            Number(document.getElementById("surface-x").value),
            Number(document.getElementById("surface-y").value),
            trimKey,
        );
        const readout = document.getElementById("surface-readout");
        const interior = document.getElementById("surface-size-readout");
        const trim = document.getElementById("surface-trim-readout");
        const outside = document.getElementById("surface-outside-readout");
        readout.hidden = !resolved.ok;
        if (resolved.ok) {
            interior.textContent = SP.fieldText(resolved.fieldX, resolved.fieldY);
            trim.textContent = `${SP.surfaceTrimLabel(trimKey)} — ${fmt(resolved.trimWidth)} mm`;
            outside.textContent = `${fmt(resolved.outerX)} × ${fmt(resolved.outerY)} mm`;
        }
    } else if (kind === "portable") {
        const x = Number(document.getElementById("portable-x").value);
        const y = Number(document.getElementById("portable-y").value);
        const z = Number(document.getElementById("portable-z").value);
        if (x > 0 && y > 0 && z > 0) {
            document.getElementById("portable-readout").hidden = false;
            const rx = SP.snap(x);
            const ry = SP.snap(y);
            document.getElementById("portable-size-readout").textContent = `${rx/unit} × ${ry/unit} units (${rx} × ${ry} mm)`;
        } else {
            document.getElementById("portable-readout").hidden = true;
        }
        SP.refreshSetupOutside();
    } else if (kind === "pegboard") {
        const mode = document.getElementById("pegboard-size-mode")?.value || "physical";
        const isPhysical = mode === "physical";
        document.getElementById("pegboard-physical-fields").hidden = !isPhysical;
        document.getElementById("pegboard-hole-fields").hidden = mode !== "holes";
        // Fix 060 C: the physical-size help text and the Residual border
        // readout only mean anything in Physical size mode - in Hole/slot
        // count mode the board is derived directly from an exact count and
        // the residual is always 0, so both leak meaningless state.
        const physicalHelp = document.getElementById("pegboard-physical-help");
        if (physicalHelp) physicalHelp.hidden = !isPhysical;
        const borderRow = document.getElementById("pegboard-border-row");
        if (borderRow) borderRow.hidden = !isPhysical;
        const resolved = SP.resolvePegboard();
        const readout = document.getElementById("pegboard-readout");
        readout.hidden = !resolved.ok;
        if (resolved.ok) {
          document.getElementById("pegboard-grid-readout").textContent = `${resolved.holesX} × ${resolved.holesY} positions — ${fmt(resolved.holesX * resolved.standard.pitch_x_mm)} × ${fmt(resolved.holesY * resolved.standard.pitch_y_mm)} mm`;
          document.getElementById("pegboard-border-readout").textContent = `${fmt(resolved.residualX / 2)} mm sides, ${fmt(resolved.residualY / 2)} mm top/bottom`;
        }
    }
};

// ------------------------------------------------------------ Storage Box case settings
//
// A Storage Box Space owns its case: `space.storage_box` (see
// organizer_inventory.normalise_storage_box). These helpers fill and read the
// case settings on the Space setup/Edit form.

SP.storageBoxDefaults = () => ({
  secure_lid: true, latch_count: "auto", lid_headroom_mm: 1,
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

SP.fillStorageBoxForm = box => {
  const one = { ...SP.storageBoxDefaults(), ...(box || {}) };
  const set = (id, value) => { const node = document.getElementById(id); if (node) node.value = String(value); };
  set("portable-lid-type", one.secure_lid === false ? "lid_only" : "latched");
  set("portable-lid-snugness", one.lid_headroom_mm);
  set("portable-stacking", Boolean(one.stacking));
  set("portable-latch-count", ["1", "2"].includes(String(one.latch_count)) ? String(one.latch_count) : "auto");
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
  if (!label || !value) return;
  const hideOutside = () => { label.hidden = true; value.hidden = true; value.textContent = ""; };
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
      label.hidden = false; value.hidden = false;
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
    latch_count: latched ? (value("portable-latch-count") || "auto") : "auto",
    lid_headroom_mm: parseFloat(value("portable-lid-snugness")) || 1,
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
SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP = "Printing needs local Wavefinity with Bambu Studio. Use Save to put the files in your folder.";
SP.HOSTED_SURFACE_PRINT_TOOLTIP = "Printing needs local Wavefinity. On hosted Wavefinity, use the Save Base Trim button to save the Base Trim files to your folder.";

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
  // A dirty structural Design draft must be settled before output is
  // manufactured from the accepted Space: Save Changes, Discard, or the
  // output stays blocked while the user keeps editing.
  if (!(await SP.confirmLeaveStructuralEditor())) return;
  const label = SP.structuralLabel(kind);
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
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
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
    } else {
      const result = await apiSideEffect("/api/space/structural-generate", payload);
      DL.requireSpaceContext(context);
      const saved = await saveGeneratedFiles(result, { kind: "structural" });
      DL.requireSpaceContext(context);
      toast(`Saved ${label} to ${result.output || state.output}${saved.length ? `\n${[...new Set(saved.map(file => String(file).split(/[\\/]/).pop()))].join("\n")}` : ""}`, false, 7000);
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
// ---- Surface Base Trim: owned-output lifecycle, current-printer readiness (Fix 095)
//
// The server owns the Base Trim piece plan, signature and, locally, the currentness
// status. Hosted status is recomputed here from the committed browser manifest and
// the real files in the chosen folder - never from a server temp.

SP.baseTrimInfo = { key: "", plan: null, status: null, error: "", serial: 0 };

SP.BASE_TRIM_STATUS_TEXT = {
  current: "Current",
  missing: "Needs save",
  needs_update: "Needs save",
  externally_changed: "Saved file changed outside Wavefinity",
  recovery_error: "Needs recovery",
};

SP.baseTrimSummaryText = () => {
  const info = SP.baseTrimInfo;
  if (info.error) return `Base Trim · ${info.error}`;
  if (info.status && info.status.status === "recovery_error") {
    // (Fix 096 A8) An interrupted save that could not be settled: surface
    // the recovery instructions, never "Needs save".
    return `Base Trim · ${SP.BASE_TRIM_STATUS_TEXT.recovery_error} · ${info.status.message}`;
  }
  if (!info.plan || !info.status) return "";
  const count = Number(info.plan.piece_count);
  const pieces = `${count} ${count === 1 ? "piece" : "pieces"} for current printer`;
  return `Base Trim · ${pieces} · ${SP.BASE_TRIM_STATUS_TEXT[info.status.status] || "Needs save"}`;
};

// ---- hosted Base Trim durable save journal (Fix 096 A8)
//
// Clones the hosted cabinet save journal pattern (Fix 086) under Base Trim's
// own namespace. Before any owned final is replaced, an app-owned journal
// (Space ID, prior and candidate manifests, filenames, backup filenames,
// newly-created filenames) and durable backups are written into the folder
// itself. The next hosted status or save settles the journal first, so an
// interrupted save is idempotent across reload/retry. Cabinet journal keys
// are never used here.
SP.BASE_TRIM_JOURNAL = ".wavefinity-basetrim-journal.json";
SP.BASE_TRIM_BACKUP_PREFIX = ".wavefinity-basetrim-backup-";
SP.BASE_TRIM_BACKUP_NAME = /^\.wavefinity-basetrim-backup-[0-9a-f-]+-\d+\.3mf$/;

SP.baseTrimRecoveryError = message =>
  Object.assign(new Error(`Base Trim recovery is needed: ${message}`), { code: "BASE_TRIM_RECOVERY" });

// A journal this tab is writing right now is a live transaction, not an
// interrupted one: only the save itself (`own`) may settle it.
SP._hostedBaseTrimSaving = false;

// Orphan app-owned backups only, and only when no journal is active.
SP.sweepHostedBaseTrimDebris = async handle => {
  for (const name of await WFFileSystem.listFilenames(handle)) {
    if (SP.BASE_TRIM_BACKUP_NAME.test(name)) {
      try { await WFFileSystem.removeFile(handle, name); } catch (_error) { /* left for the next sweep */ }
    }
  }
};

SP.recoverBaseTrimJournal = async (handle, spaceId, { own = false } = {}) => {
  if (SP._hostedBaseTrimSaving && !own) return "busy";
  const text = await WFFileSystem.readText(handle, SP.BASE_TRIM_JOURNAL);
  if (text === null) {
    await SP.sweepHostedBaseTrimDebris(handle);
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
    throw SP.baseTrimRecoveryError(`the interrupted-save record in this folder (${SP.BASE_TRIM_JOURNAL}) is damaged. Check the Base Trim files, then delete that file to continue.`);
  }
  if (journal.space_id !== spaceId) {
    throw SP.baseTrimRecoveryError("an unfinished Base Trim save in this folder belongs to a different Space.");
  }
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw SP.baseTrimRecoveryError("this folder's Space could not be confirmed.");
  }
  const stored = meta.structural_outputs?.base_trim || null;
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
          throw SP.baseTrimRecoveryError(`the backup of ${file.name} is damaged, so the original could not be restored.`);
        }
        await WFFileSystem.writeBlob(handle, file.name, new Blob([await backup.arrayBuffer()]));
      } else if ((await WFFileSystem.sha256(handle, file.name)) !== file.original_sha256) {
        throw SP.baseTrimRecoveryError(`the original ${file.name} could not be restored.`);
      }
    }
  }
  for (const file of journal.files) {
    if (file.backup) await SP.removeIfPresent(handle, file.backup);
  }
  await SP.removeIfPresent(handle, SP.BASE_TRIM_JOURNAL);
  return committed ? "committed" : "rolled_back";
};

SP.hostedBaseTrimStatus = async (plan, signature) => {
  const handle = state.browserFolder?.handle;
  if (!handle) return { status: "missing" };
  if (SP._hostedBaseTrimSaving) return SP.baseTrimInfo.status || { status: "missing" };
  // A journal left by an interrupted save is settled first: committed leftovers
  // are cleaned, anything else is rolled back, before ownership is compared. (Fix 096 A8)
  await SP.recoverBaseTrimJournal(handle, state.activeSpaceId);
  const { current } = await SP.readMetadata(handle);
  const manifest = SP.classifyMetadata(current).structural_outputs?.base_trim;
  const rows = manifest?.pieces;
  if (manifest?.schema !== 1 || !Array.isArray(rows) || !rows.length ||
      rows.some(one => typeof one?.filename !== "string" || typeof one?.sha256 !== "string") ||
      (state.activeSpaceId && manifest.space_id !== state.activeSpaceId)) {
    return { status: "missing" };
  }
  if (manifest.signature !== signature ||
      rows.map(one => one.filename).join("\n") !== plan.filenames.join("\n")) {
    return { status: "needs_update" };
  }
  const changed = [];
  const absent = [];
  for (const piece of rows) {
    const hash = await WFFileSystem.sha256(handle, piece.filename);
    if (hash === null) absent.push(piece.filename);
    else if (hash !== piece.sha256) changed.push(piece.filename);
  }
  if (changed.length) return { status: "externally_changed", changed, absent };
  if (absent.length) return { status: "missing", absent };
  return { status: "current" };
};

SP.refreshBaseTrimSummary = async () => {
  const space = state.activeSpace;
  if (SP.structuralKind() !== "base_trim" || !space) return;
  const hosted = Boolean(state.runtime.hosted);
  const profile = PrinterProfile.current();
  const key = JSON.stringify([space, profile, state.activeSpaceId, SP.baseTrimInfo.serial,
    hosted ? state.browserFolder?.name : state.output]);
  if (SP.baseTrimInfo.key === key) return;
  SP.baseTrimInfo = { ...SP.baseTrimInfo, key, plan: null, status: null, error: "" };
  try {
    const result = await api("/api/space/structural-design", {
      space: clone(space),
      ...(hosted ? { printer_profile: profile } : { output: state.output, space_id: state.activeSpaceId }),
    });
    if (SP.baseTrimInfo.key !== key) return;
    SP.baseTrimInfo.plan = result.plan;
    SP.baseTrimInfo.status = hosted
      ? await SP.hostedBaseTrimStatus(result.plan, result.signature) : result.status;
  } catch (error) {
    if (SP.baseTrimInfo.key !== key) return;
    if (error.code === "BASE_TRIM_RECOVERY") {
      // An interrupted save that cannot be settled is a Base Trim recovery
      // problem, never "changed outside Wavefinity". (Fix 096 A8)
      SP.baseTrimInfo.status = { status: "recovery_error", message: error.message };
    } else {
      SP.baseTrimInfo.error = error.message;
    }
  }
  if (SP.baseTrimInfo.key === key) SP.renderStructuralActions();
};

// Any change to what "current" is measured against re-derives the line next render.
SP.invalidateBaseTrimSummary = () => {
  SP.baseTrimInfo.key = "";
  if (SP.structuralKind() === "base_trim") SP.renderSpaceInfo();
};

SP.fileNames = files => [...new Set((files || []).map(file => String(file?.name || file).split(/[\\/]/).pop()))].join("\n");

// Hosted Save: every piece is downloaded and verified first, only files the prior
// manifest proves are ours (same name, same hash) are replaced, and the manifest is
// committed only after every write succeeded. A durable journal plus on-disk
// backups make an interrupted save recoverable: the next status or save settles
// the journal first, idempotently. (Fix 096 A8)
SP.hostedBaseTrimSave = async (payload, context) => {
  const handle = state.browserFolder.handle;
  const spaceId = state.activeSpaceId;
  // Settle any earlier interrupted save before ownership is compared.
  await SP.recoverBaseTrimJournal(handle, spaceId);
  const exported = await apiSideEffect("/api/space/structural-generate", { ...payload, space_id: spaceId });
  DL.requireSpaceContext(context);
  const candidate = exported.manifest;
  if (!candidate?.pieces?.length) throw new Error("The server did not return the Base Trim files.");
  const { current } = await SP.readMetadata(handle);
  const meta = SP.classifyMetadata(current);
  if (meta.status !== "space" || meta.space_id !== spaceId) {
    throw new Error("This folder is not the Space that was open before. Nothing was changed.");
  }
  const prior = meta.structural_outputs?.base_trim || null;
  const owned = new Map((prior?.schema === 1 && prior.space_id === spaceId && Array.isArray(prior.pieces) ? prior.pieces : [])
    .filter(one => typeof one?.filename === "string" && typeof one?.sha256 === "string")
    .map(one => [one.filename, one.sha256]));

  const blobs = new Map();
  for (const item of exported.files || []) {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error(`Could not download ${item.name}.`);
    blobs.set(item.name, await response.blob());
  }
  for (const piece of candidate.pieces) {
    const blob = blobs.get(piece.filename);
    if (!blob || (await WFFileSystem.sha256Blob(blob)) !== piece.sha256) {
      throw new Error("A Base Trim file did not download correctly. Nothing was changed.");
    }
  }
  for (const piece of candidate.pieces) {
    const existing = await WFFileSystem.sha256(handle, piece.filename);
    if (existing === null) continue;
    // Only a file the prior manifest owns, still unchanged, may be replaced.
    if (owned.get(piece.filename) === undefined || owned.get(piece.filename) !== existing) {
      throw new Error(`${piece.filename} already exists and Wavefinity cannot safely replace it. Rename or move that file, then Save Base Trim again. Nothing was changed.`);
    }
  }
  const txid = crypto.randomUUID();
  const entries = [];
  const backups = [];
  for (const [index, piece] of candidate.pieces.entries()) {
    const old = await WFFileSystem.readBlob(handle, piece.filename);
    if (old) {
      const bytes = new Blob([await old.arrayBuffer()]);
      const backup = `${SP.BASE_TRIM_BACKUP_PREFIX}${txid}-${index}.3mf`;
      entries.push({ name: piece.filename, created: false, backup, original_sha256: await WFFileSystem.sha256Blob(bytes) });
      backups.push([backup, bytes]);
    } else {
      entries.push({ name: piece.filename, created: true });
    }
  }
  SP._hostedBaseTrimSaving = true;
  try {
    // Durable backups first, then the journal that names them, then the installs.
    for (const [name, blob] of backups) await WFFileSystem.writeBlob(handle, name, blob);
    await WFFileSystem.writeText(handle, SP.BASE_TRIM_JOURNAL, JSON.stringify({
      version: 1, tx: txid, space_id: spaceId, prior_manifest: prior, candidate_manifest: candidate, files: entries,
    }));
    for (const piece of candidate.pieces) {
      await WFFileSystem.writeBlob(handle, piece.filename, blobs.get(piece.filename));
    }
    for (const piece of candidate.pieces) {
      if ((await WFFileSystem.sha256(handle, piece.filename)) !== piece.sha256) {
        throw new Error(`${piece.filename} did not save correctly.`);
      }
    }
    DL.requireSpaceContext(context);
    await SP.writeMetadata(handle, "space", null, true, {
      structural_output_updates: { base_trim: candidate },
    }, { preserveSpace: true, expectedSpaceId: spaceId });
  } catch (error) {
    // Roll back from the same durable record a lost tab would have used.
    try { await SP.recoverBaseTrimJournal(handle, spaceId, { own: true }); }
    catch (_recovery) { /* the journal stays; the next status or save settles it */ }
    SP._hostedBaseTrimSaving = false;
    throw error;
  }
  // Committed: only now are the backups, then the journal, cleaned.
  try {
    for (const [name] of backups) await SP.removeIfPresent(handle, name);
    await SP.removeIfPresent(handle, SP.BASE_TRIM_JOURNAL);
  } catch (_cleanup) { /* committed leftovers are cleaned by the next status or save */ }
  SP._hostedBaseTrimSaving = false;
  const warnings = [];
  const desired = new Set(candidate.pieces.map(one => one.filename));
  for (const [name, hash] of owned) {
    if (desired.has(name)) continue;
    try {
      const existing = await WFFileSystem.sha256(handle, name);
      if (existing === null) continue;
      if (existing === hash) await WFFileSystem.removeFile(handle, name);
      else warnings.push(`${name} changed outside Wavefinity; left in place without Base Trim ownership`);
    } catch (_error) {
      warnings.push(`Could not remove old Base Trim file ${name}; remove it manually`);
    }
  }
  return { files: [...desired], warnings };
};

SP.saveBaseTrim = async () => {
  if (SP.structuralBusy || SP.structuralKind() !== "base_trim") return;
  const hosted = Boolean(state.runtime.hosted);
  if (hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
  const context = DL.spaceContext();
  const payload = {
    space: clone(state.activeSpace), space_id: state.activeSpaceId,
    ...(hosted ? { printer_profile: PrinterProfile.current() } : { output: state.output }),
  };
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    const saved = hosted
      ? await SP.hostedBaseTrimSave(payload, context)
      : await apiSideEffect("/api/space/structural-generate", payload);
    DL.requireSpaceContext(context);
    const warnings = saved.warnings?.length ? `\n${saved.warnings.join("\n")}` : "";
    toast(`Saved Base Trim${hosted ? "" : ` to ${saved.output || state.output}`}\n${SP.fileNames(saved.files)}${warnings}`, false, 7000);
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast("Base Trim finished for the Space you left. Nothing was changed in the current Space.");
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.baseTrimInfo.serial += 1;
    SP.renderSpaceInfo();
  }
};

// The one Surface print: current-printer Base Trim + placed Not Printed bins + the
// required connectors, handed to the slicer once. Ctrl+Shift+click stays the hidden
// maintainer joint-fit sample (no bins, connectors or status changes).
SP.printSurface = async event => {
  if (SP.structuralBusy || SP.structuralKind() !== "base_trim") return;
  if (state.runtime.hosted) { toast(SP.HOSTED_SURFACE_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
    return;
  }
  if (event?.ctrlKey && event?.shiftKey) return SP.runStructural("print", event);
  const context = DL.spaceContext();
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
    DL.requireSpaceContext(context);
    if (typeof flushSpaceDesignAutosave === "function" &&
        !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) return;
    DL.requireSpaceContext(context);
    if (!(await DL.save())) return;
    DL.requireSpaceContext(context);
    const result = await apiSideEffect("/api/space/surface-print", {
      output: context.output, space_id: context.spaceId,
      slicer_path: state.slicer?.path || null,
    });
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) toast(result.error || "Surface print stopped before Bambu Studio opened.", true, 10000);
    else toast(`Sent Surface + Bins to ${state.slicer?.name || "the slicer"}!\n${SP.fileNames(result.files)}`, false, 8000);
  } catch (error) {
    if (DL.isStaleSpaceError(error)) {
      toast("Surface print belongs to the Space you left. The current Space was not changed.");
    } else {
      toast(error.message, true, 8000);
    }
  } finally {
    SP.structuralBusy = false;
    SP.baseTrimInfo.serial += 1;
    SP.renderSpaceInfo();
  }
};

SP.saveStructural = () => SP.structuralKind() === "base_trim"
  ? SP.saveBaseTrim() : SP.runStructural("save");
SP.printStorageBox = async () => {
  if (SP.structuralBusy || SP.structuralKind() !== "storage_box") return;
  // A dirty structural Design draft must be settled before output is
  // manufactured from the accepted Space: Save Changes, Discard, or the
  // output stays blocked while the user keeps editing.
  if (!(await SP.confirmLeaveStructuralEditor())) return;
  if (state.runtime.hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer prepares 3D-print files for your printer. Open Printer Settings… to choose one.", true, 8000);
    return;
  }
  const context = DL.spaceContext();
  SP.structuralBusy = true;
  SP.renderSpaceInfo();
  try {
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
  const box = document.getElementById("space-structural");
  if (!box) return;
  const kind = SP.structuralKind();
  // The cabinet's Save/Print live in its workspace panel.
  box.hidden = !kind || kind === "storage_drawers";
  if (!kind || kind === "storage_drawers") return;
  const label = SP.structuralLabel(kind);
  const save = document.getElementById("space-structural-save");
  const print = document.getElementById("space-structural-print");
  const hosted = Boolean(state.runtime.hosted);
  save.textContent = `Save ${label}`;
  print.textContent = kind === "storage_box" ? "Print Storage Box + Bins"
    : kind === "base_trim" ? "Print Surface + Bins" : `Print ${label}`;
  const summary = document.getElementById("space-structural-summary");
  if (summary) {
    const text = kind === "base_trim" ? SP.baseTrimSummaryText() : "";
    summary.hidden = !text;
    summary.textContent = text;
  }
  if (kind === "base_trim") SP.refreshBaseTrimSummary();
  save.disabled = SP.structuralBusy;
  print.disabled = SP.structuralBusy || hosted;
  print.title = hosted ? (kind === "base_trim" ? SP.HOSTED_SURFACE_PRINT_TOOLTIP : SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP) : "";
  // Fix 096 F9: visible reason beside the disabled Print button, not only a tooltip.
  const printReason = document.getElementById("space-structural-print-reason");
  if (printReason) {
    printReason.hidden = !hosted;
    printReason.textContent = hosted
      ? "Printing is unavailable on hosted Wavefinity: there is no local slicer here."
      : "";
  }
  const makeInsideBin = document.getElementById("space-make-inside-bin");
  if (makeInsideBin) makeInsideBin.hidden = kind !== "storage_box";
};

SP.renderSpaceInfo = () => {
    const isSpace = state.folderMode === "space" && state.activeSpace;
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
    if (viewing) viewing.hidden = SP.editing;
    document.getElementById("space-head-name").textContent = state.activeSpace.name;

    const kind = state.activeSpace.kind;
    const kindLabel = SP_KINDS[kind]?.label || kind;
    document.getElementById("space-head-type").textContent = ` - ${kindLabel}`;

    // Fix 034 J: the top Space summary is the single authoritative Actual
    // size / Usable interior readout - existing calculations only, never
    // duplicated math.
    let actualText = "";
    let usableText = "";
    const unit = state.catalog?.base_unit || 8;
    if (kind === "drawer") {
        const x = state.activeSpace.x;
        const y = state.activeSpace.y;
        const z = state.activeSpace.z;
        actualText = `${fmt(x)} × ${fmt(y)} × ${fmt(z)} mm`;
        let gx = SP.drawerCapacity(x);
        let gy = SP.drawerCapacity(y);
        try {
            if (typeof DL !== "undefined" && DL.active && DL.layout) {
                const grid = DL.grid(DL.drawer());
                if (grid) { gx = grid.cols; gy = grid.rows; }
            }
        } catch (_error) { /* keep the approximate unit count above */ }
        usableText = `${gx} × ${gy} units`;
    } else if (kind === "surface") {
        const x = state.activeSpace.x;
        const y = state.activeSpace.y;
        // Current fully-configured Surface Spaces are guaranteed a
        // valid trim_size - see Fix 004 Correction 11.A4/A6.
        const trimRow = SP.surfacePresetRows().find(
            row => row.key === state.activeSpace.trim_size
        );
        const trim = trimRow?.label || state.activeSpace.trim_size || "";
        const outsideX = SP.surfaceOutsideFor(x, state.activeSpace.trim_size);
        const outsideY = SP.surfaceOutsideFor(y, state.activeSpace.trim_size);
        actualText = `${fmt(outsideX)} × ${fmt(outsideY)} mm (${trim} trim)`;
        usableText = SP.fieldText(x, y);
    } else if (kind === "portable") {
        // The outside case and its capacity are derived by the server from the
        // Space's own dimensions and case settings.
        SP.refreshStructuralSummary();
        const b4b = SP.structuralInfo.key === JSON.stringify(state.activeSpace) ? SP.structuralInfo.data : null;
        if (!b4b) {
            actualText = SP.structuralInfo.error ? "Not available" : "Calculating…";
            usableText = SP.structuralInfo.error || "Calculating…";
        } else {
            const outer = b4b.assembled_envelope_mm;
            const capacity = b4b.capacity_mm;
            const units = b4b.capacity_units;
            actualText = `${fmt(outer[0])} × ${fmt(outer[1])} × ${fmt(outer[2])} mm`;
            usableText =
                `${fmt(capacity[0])} × ${fmt(capacity[1])} mm ` +
                `(${units[0]} × ${units[1]} units), max bin height ` +
                `${fmt(b4b.max_child_height_mm)} mm`;
        }
    } else if (kind === "box") {
        const x = state.activeSpace.x;
        const y = state.activeSpace.y;
        const z = state.activeSpace.z;
        actualText = `${fmt(x)} × ${fmt(y)} mm`;
        usableText = `${fmt(x / unit)} × ${fmt(y / unit)} units, ${fmt(z)} mm usable height`;
    } else if (kind === "storage_drawers") {
        // Never the compatibility z: the outside size comes from the server
        // summary once it is already known.
        const outside = SP.cabinetInfo.summary?.outside_xyz;
        actualText = Array.isArray(outside) && outside.length === 3
            ? `${outside.map(fmt).join(" × ")} mm` : "";
        usableText = SP.storageDrawersSummaryText(state.activeSpace);
    } else if (kind === "pegboard") {
        const standard = SP.pegboardStandard(state.activeSpace.pegboard_standard);
        actualText = `${fmt(state.activeSpace.x)} × ${fmt(state.activeSpace.y)} mm`;
        usableText = `${standard?.name || "Pegboard"}: ${state.activeSpace.pegboard_holes_x} × ${state.activeSpace.pegboard_holes_y} positions`;
    }
    const extraText = kind === "drawer" && typeof DP !== "undefined" && DP.extraSpaceText
        ? DP.extraSpaceText()
        : "";
    const summary = [
        actualText ? `Actual size: ${actualText}` : "",
        usableText ? `Usable interior: ${usableText}` : "",
        extraText ? `Extra space: ${extraText}` : "",
    ].filter(Boolean).join(" · ");
    const summaryEl = document.getElementById("space-head-summary");
    if (summaryEl) summaryEl.textContent = summary;

    // New Space is offered for every typed Space, not only Drawer.
    const btnNew = document.getElementById("space-head-new-space");
    if (btnNew) btnNew.hidden = false;

    const btnShow = document.getElementById("space-head-show");
    if (btnShow) btnShow.hidden = state.runtime.hosted;
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
      title: "Show Folder",
      message: `Open this Space in ${fm}?`,
      actionLabel: "Show Folder",
    });
    if (!ok) return;
    try {
        await api("/api/space/show-folder", { output: state.output });
    } catch (e) {
        toast("Failed to open folder: " + friendlyError(e), true);
    }
};

SP.editSpace = () => {
    if (!state.activeSpace) return;
    SP.showSetup(state.activeSpace.kind === "box" ? "portable" : state.activeSpace.kind, state.activeSpace, { update: true });
};

SP.newSpace = () => {
    if (!state.activeSpace) return;

    const template = clone(state.activeSpace);
    if (template.kind === "box") template.kind = "portable";
    template.name = "";

    // Clear stale folder/collision/edit state first, then install only the
    // read-only repeat-size template for the type chooser.
    SP.clearSetupContext();
    SP.setupPrefillSpace = template;
    SP.showTypeCards();
};

// Wire the Space Info Edit/Show Folder/New Space buttons for one
// prefix only, so the normal Design controls (wired once at startup) and
// the Drawer panel's dynamically-built copy (wired once when DP.build()
// creates it) never both attach a listener to the same button - see
// Fix 004 Correction 6.M.
const wireInfoButtons = (prefix = "space-head") => {
    const btnOpen = document.getElementById(prefix + "-open");
    if (btnOpen) btnOpen.addEventListener("click", () => SP.run(SP.openExisting));
    const btnEdit = document.getElementById(prefix + "-edit");
    if (btnEdit) btnEdit.addEventListener("click", SP.editSpace);
    const btnPrinterSettings = document.getElementById(prefix + "-printer-settings");
    if (btnPrinterSettings) btnPrinterSettings.addEventListener("click", SP.openPrinterSettings);
    const btnShow = document.getElementById(prefix + "-show");
    if (btnShow) btnShow.addEventListener("click", SP.showFolder);
    const btnNew = document.getElementById(prefix + "-new-space");
    if (btnNew) btnNew.addEventListener("click", SP.newSpace);
    const btnSave = document.getElementById("space-structural-save");
    if (btnSave) btnSave.addEventListener("click", SP.saveStructural);
    const btnPrint = document.getElementById("space-structural-print");
    if (btnPrint) btnPrint.addEventListener("click", SP.printStructural);
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

SP.updateSpace = async () => {
    const values = await SP.readSetupValues();
    if (!values) return;
    const { kind, name, x, y, z, trimSize, extra = {} } = values;
    if (kind === "storage_drawers") {
        // Edit goes through the serialized cabinet mutation, which checks every
        // current placement before Inventory or metadata is committed.
        const updated = await SP.mutateCabinet("reconfigure", {
          space: { kind, name, x, y, z, storage_drawers: extra.storage_drawers },
        });
        // Only an adopted result closes the form and reports success.
        if (!updated) return;
        SP.storageDrawersForm?.markPristine?.();
        SP.cancelInlineEdit();
        toast("Space updated.");
        return;
    }
    return SP.commitSpaceUpdate(values);
};

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
        if (!(await SP.confirmPrintedAutoBases(trimSize))) return;
        requireCurrent();
    }
    if ((kind === "surface" || kind === "portable") && typeof DL !== "undefined" && DL.loaded && !(await DL.save())) {
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
    if ((kind === "drawer" || kind === "pegboard") && typeof DL !== "undefined" && DL.active) {
        DL.syncSingleDrawerFromSpace(state.activeSpace);
    }
};



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

// ---- global printer build volume (one runtime authority: PrinterProfile)

SP._printerHosts = new Map();

SP.mountPrinterProfiles = () => {
  document.querySelectorAll("[data-printer-profile-host]").forEach(host => {
    if (SP._printerHosts.has(host)) return;
    const callbacks = state.runtime.hosted
      ? { hosted: true, reset: () => PrinterProfile.resetHosted(), onError: error => toast(error.message, true, 6000) }
      : {
        write: async (_key, value) => {
          const saved = await api("/api/space/printer-profile", { profile: value.profile });
          PrinterProfile.loadLocal(saved);
        },
        // Only the printer keys return to defaults, and the reset is persisted.
        reset: async () => {
          const saved = await api("/api/space/printer-profile", { reset: true });
          PrinterProfile.loadLocal(saved);
        },
        onError: error => toast(error.message, true, 6000),
      };
    SP._printerHosts.set(host, PrinterProfile.mount(host, callbacks));
  });
};

SP.initPrinterProfile = async () => {
  try {
    if (state.runtime.hosted) {
      const loaded = await PrinterProfile.loadHosted();
      if (!loaded.explicit && !loaded.malformed) {
        PrinterProfile.persistHosted(PrinterProfile.readLegacyBaseTrimSeed() || PrinterProfile.DEFAULT);
      }
      PrinterProfile.retireLegacyBaseTrim();
    } else {
      const local = await api("/api/space/printer-profile", {});
      PrinterProfile.loadLocal(local);
      if (!local.explicit && !local.malformed) {
        const seed = PrinterProfile.readLegacyBaseTrimSeed() || PrinterProfile.DEFAULT;
        // The old Base Trim key is retired only after the new authority holds it.
        const saved = await api("/api/space/printer-profile", { profile: { ...seed } });
        PrinterProfile.loadLocal(saved);
        PrinterProfile.retireLegacyBaseTrim();
      }
    }
  } catch (error) {
    toast(`Printer settings could not be loaded: ${error.message}`, true, 6000);
  }
  PrinterProfile.subscribe(profile => {
    SP.storageDrawersForm?.setPrinterProfile(profile);
    SP.cabinetInfo.key = "";
    SP.updateCabinetWorkspace();
    SP.invalidateBaseTrimSummary();
  });
  SP.mountPrinterProfiles();
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

// ---- Printer Settings dialog: the one PrinterProfile authority, reachable from
// the setup Summary and from the cabinet panel. Closing it changes nothing else.

SP.openPrinterSettings = () => {
  const dialog = document.getElementById("printer-settings-dialog");
  if (dialog && !dialog.open) dialog.showModal();
};

SP.closePrinterSettings = () => {
  const dialog = document.getElementById("printer-settings-dialog");
  if (dialog?.open) dialog.close();
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
