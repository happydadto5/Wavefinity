"use strict";

// Drops any leftover selected-folder/collision/edit state from a previous
// setup attempt before starting a genuinely new one, so a stale target
// folder or Edit mode can never leak into the next Create - see Fix 004
// Correction 7.F. Configure Existing intentionally does not call this: it
// deliberately carries SP.configureData from the Configure prompt through
// the type cards into the type-specific form.
SP.clearSetupContext = () => {
  SP.configureData = null;
  SP.collisionFolder = null;
  SP.collisionData = null;
  SP.collisionOrigin = null;
  SP.pendingConfigureFolder = null;
  SP.cancelInlineEdit();
  SP.isUpdate = false;
  SP.setupPrefillSpace = null;
  SP.setupPreserveIds = false;
  SP.setupFormSnapshot = null;
};

// Only a committed type - current or explicit legacy metadata - may resume or
// block a folder. Inventory/layout candidates are suggestions.
SP.authoritativeTypedSource = data =>
  ["metadata", "legacy_metadata"].includes(data?.space_source);

SP.beginCreateNew = () => {
  // Clear prior setup state first, so an abandoned migration/collision target
  // cannot survive an unsupported-browser message.
  SP.clearSetupContext();

  if (
    state.runtime.hosted &&
    !window.WFFileSystem?.supportsDirectoryPicker()
  ) {
    SP.showFolderAccessNeeded("unsupported");
    return;
  }

  SP.showTypeCards();
};

// Editing the open Space happens in the Space header, not in the Welcome
// dialog: the same setup form is moved into the header for the edit and put
// back afterwards, so Create and Edit share every field and check while the
// Create-only buttons (Back, Choose Folder & Create) never appear in Edit.
SP.editing = false;

SP.mountInlineEdit = () => {
  const form = $("#space-form");
  const host = $("#space-head-edit-host");
  if (!form || !host) return false;
  if (!SP.formHome) SP.formHome = { parent: form.parentNode, next: form.nextSibling };
  host.appendChild(form);
  host.hidden = false;
  SP.editing = true;
  return true;
};

SP.cancelInlineEdit = () => {
  if (!SP.editing) return;
  SP.editing = false;
  SP.destroyStorageDrawersForm?.();
  const form = $("#space-form");
  const host = $("#space-head-edit-host");
  if (form && SP.formHome) {
    SP.formHome.parent.insertBefore(form, SP.formHome.next && SP.formHome.next.parentNode === SP.formHome.parent ? SP.formHome.next : null);
    form.hidden = true;
  }
  if (host) host.hidden = true;
  SP.isUpdate = false;
  SP.setFormMode(false);
  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
};

// Create shows Back and Choose Folder & Create; Edit shows Save Changes and
// Cancel instead, and none of the onboarding chrome.
SP.setFormMode = edit => {
  $("#space-form").classList.toggle("editing", edit);
  $("#space-back").hidden = edit;
  $("#space-create").hidden = edit;
  $("#space-form-title").parentElement.hidden = edit;
};

SP.setupFormSnapshot = null;

SP.captureOrdinarySetupSnapshot = () => {
  const form = $("#space-form");
  if (!form || SP.setupKind === "storage_drawers") return null;
  const rows = [...form.querySelectorAll("input, select, textarea")]
    .filter(node => !node.disabled && !node.closest("[hidden]"))
    .map(node => [
      node.id || node.name || node.type,
      node.type === "checkbox" || node.type === "radio" ? Boolean(node.checked) : String(node.value),
    ]);
  return JSON.stringify(rows);
};

// Local folder line: a live path that names the Space as it is typed. Hosted
// shows the folder picked next instead, and Storage Drawers names its Space
// in its own form, so both keep their plain sentence.
SP.updateSavedAsMessage = () => {};

SP.showSetup = (kind, prefillSpace = null, { update = false } = {}) => {
  if (update) {
    if (!SP.mountInlineEdit()) return;
    $("#space-form").hidden = false;
    SP.close();
  } else {
    SP.showOnly("space-form");
  }
  SP.setFormMode(update);
  // Every entry into setup explicitly states whether it is editing the
  // current Space, so a stale Edit that was backed out of can never make a
  // later Create/New Space silently call SP.updateSpace() - see
  // Fix 004 Correction 6.F.
  SP.isUpdate = update;
  SP.setupKind = kind;
  SP.setupChangedField = null;
  SP.setupValidationStarted = false;
  $("#space-form").querySelectorAll("[data-setup-touched]").forEach(input => delete input.dataset.setupTouched);
  $("#space-form").querySelectorAll('[id$="-setup-error"]').forEach(note => { note.hidden = false; note.textContent = ""; });
  SP.dialog().classList.toggle("storage-drawers-config", kind === "storage_drawers" && !update);
  const typeLabel = SP_KINDS[kind]?.label || kind;
  const title = document.getElementById("space-form-title");
  if (title) {
    title.textContent = "Configure " + typeLabel;
  }
  $("#space-form").querySelectorAll("#space-name, #drawer-x, #drawer-y, #drawer-z, #drawer-lift, #surface-x, #surface-y, #surface-trim, #portable-x, #portable-y, #portable-z, #portable-lift, #pegboard-x, #pegboard-y, #pegboard-holes-x, #pegboard-holes-y").forEach(input => {
    SP.setupFieldNote(`#${input.id}`, "", "hint");
    SP.setupFieldNote(`#${input.id}`, "", "error");
  });
  $("#space-form").querySelectorAll(".derived-readout").forEach(readout => {
    if (!readout.parentElement.classList.contains("setup-readout-slot")) {
      const slot = document.createElement("div");
      slot.className = "setup-readout-slot";
      readout.before(slot);
      slot.append(readout);
    }
  });
  SP.populateSurfaceTrim();
  SP.populatePegboardStandards();
  document.querySelectorAll(".space-type-fields").forEach(el => el.hidden = true);
  const field = document.getElementById(`space-fields-${kind}`);
  if (field) field.hidden = false;
  // Fix 103 (Packet B) / Fix 117: Basic Setup and header Edit for Storage Box
  // show Name + Size only. The full case settings live in the structural
  // Design editor, not in the setup dialog. Hidden controls keep their
  // canonical defaults on create and the accepted Space's own values on edit
  // (SP.fillStorageBoxForm below), so readStorageBoxForm() works unchanged.
  const portableCase = document.getElementById("portable-case");
  if (portableCase) portableCase.hidden = kind === "portable";
  // The cabinet form owns its own name field.
  const nameRow = document.getElementById("space-name-row");
  if (nameRow) nameRow.hidden = kind === "storage_drawers";
  if (kind === "storage_drawers") SP.mountStorageDrawersForm(prefillSpace, update);
  else SP.destroyStorageDrawersForm();
  const spaceNameField = document.getElementById("space-name");
  spaceNameField.value = prefillSpace?.name || "";
  spaceNameField.placeholder = kind === "surface" ? "e.g. Kitchen worktop, Desk top"
    : kind === "portable" ? "e.g. Small parts box" : "e.g. Tool chest, drawer 2";
  // The display name can change without moving the Space's folder or identity.
  spaceNameField.disabled = false;
  document.getElementById("space-error").hidden = true;
  // Story 2755: no "can't be changed" notice; the name just shows plainly.
  document.getElementById("space-note").textContent = "";
  // Drawer setup names the field for what it is and says up front that a
  // name is needed and why a folder comes next. Other types keep "Name".
  document.getElementById("space-name-label").innerHTML =
    kind === "drawer" ? 'Drawer name <span class="required-cue">required</span>' : "Name";
  const createButton = document.getElementById("space-create");
  if (createButton && !update) {
    createButton.textContent = state.runtime.hosted && !SP.hostedHome && !SP.configureData
      ? "Choose Home Folder & Create" : "Create Space";
  }
  // Story 2747: no save-location explainer under the Space name.
  const folderHelp = document.getElementById("space-folder-help");
  if (folderHelp) {
    folderHelp.hidden = !state.runtime.hosted || update || Boolean(SP.hostedHome) || Boolean(SP.configureData);
    folderHelp.textContent = "In the folder window that opens, go to Documents, make a new folder called Wavefinity, and select it.";
  }
  if (kind === 'drawer') {
      document.getElementById('drawer-x').value = prefillSpace?.x || '';
      document.getElementById('drawer-y').value = prefillSpace?.y || '';
      document.getElementById('drawer-z').value = prefillSpace?.z || '';
      // Story 2973: the grid is chosen at setup and immutable once the Space exists.
      const gridSelect = document.getElementById("drawer-grid");
      gridSelect.value = prefillSpace?.grid || "wavefinity";
      gridSelect.disabled = update;
      gridSelect.title = update ? "A Space's grid is set when it is created and cannot be changed." : "";
      document.getElementById("drawer-lift").value = prefillSpace?.seated_lift_mm ?? "";
      gridSelect.onchange = SP.updateReadouts;
  } else if (kind === 'surface') {
      const trimSelect = document.getElementById("surface-trim");
      if (trimSelect) {
        if (!prefillSpace) {
          trimSelect.value = "medium";
        } else {
          const stored = String(prefillSpace.trim_size || "").toLowerCase();
          const validStored = Object.hasOwn(SP.surfacePresetMap(), stored);
          trimSelect.value = validStored
            ? stored
            : (SP.surfaceTrimKeyForHeight(prefillSpace.z) || "");
        }
      }
      // Edit prefills the saved maximum (a legacy Space with none is seeded from
      // its current finished footprint); nothing is migrated.
      const prefillTrim = trimSelect?.value;
      const hasSize = prefillSpace?.x && prefillSpace?.y && prefillTrim;
      const maximum = hasSize ? SP.surfaceMaxFor({ ...prefillSpace, trim_size: prefillTrim }) : null;
      document.getElementById("surface-x").value = maximum ? fmt(maximum.x) : "";
      document.getElementById("surface-y").value = maximum ? fmt(maximum.y) : "";
  } else if (kind === "portable") {
      // Story 2975: Grid (Wavefinity preselected) and, for a Gridfinity pitch,
      // Floor/None are chosen at creation and immutable once the Space exists
      // (the Plain Drawer pattern above). Set before the size so the field is
      // read at the right pitch.
      const grid = Object.hasOwn(SP.STORAGE_BOX_PITCHES, prefillSpace?.grid) ? prefillSpace.grid : "wavefinity";
      const gridSelect = document.getElementById("portable-grid");
      const floorSelect = document.getElementById("portable-floor");
      gridSelect.value = grid;
      floorSelect.value = (prefillSpace?.built_in_grid ?? prefillSpace?.storage_box?.built_in_grid) === "none" ? "none" : "floor";
      for (const select of [gridSelect, floorSelect]) {
        select.disabled = update;
        select.title = update ? "A Storage Box's grid and floor are set when it is created and cannot be changed." : "";
      }
      gridSelect.onchange = SP.onStorageBoxGridChosen;
      floorSelect.onchange = () => { SP.syncStorageBoxGrid(); SP.updateReadouts(); };
      document.getElementById("portable-x").value = prefillSpace?.x || "";
      document.getElementById("portable-y").value = prefillSpace?.y || "";
      document.getElementById("portable-z").value = prefillSpace?.z || "";
      SP.fillStorageBoxForm(prefillSpace?.storage_box);
      document.getElementById("portable-lift").value = prefillSpace?.storage_box?.seated_lift_mm ?? prefillSpace?.seated_lift_mm ?? "";
      SP.syncStorageBoxGrid();
  } else if (kind === "pegboard") {
      document.getElementById("pegboard-standard").value = prefillSpace?.pegboard_standard || "standard";
      document.getElementById("pegboard-thickness").value = String(prefillSpace?.pegboard_thickness_mm ?? 3.2);
      document.getElementById("pegboard-size-mode").value = prefillSpace?.pegboard_size_mode || "physical";
      document.getElementById("pegboard-x").value = prefillSpace?.x || "";
      document.getElementById("pegboard-y").value = prefillSpace?.y || "";
      document.getElementById("pegboard-holes-x").value = prefillSpace?.pegboard_holes_x || "";
      document.getElementById("pegboard-holes-y").value = prefillSpace?.pegboard_holes_y || "";
  }
  SP.updateReadouts();
  SP.setupFormSnapshot = SP.captureOrdinarySetupSnapshot();
  if (update) { clearTimeout(SP.setupAutosaveTimer); SP.setupAutosaveRevision = 0; SP.setupSavedRevision = 0; }
  if (update) {
    if (SP.renderSpaceInfo) SP.renderSpaceInfo();
    $("#space-name").focus();
  } else {
    SP.showDialog();
  }
};

// Fix 1018 (Andrew 2026-10-10): memory-only entry - "Design without a Space"
// with no folder chosen means no folder at all. Everything stays in memory;
// nothing is saved until the user downloads. Separate from SP.startUntyped
// (the folder path) so the hosted collision "Choose another folder" re-entry
// keeps its folder picker.
//
// The transition uses the same owners as every other folder/Space identity
// change: SP.leaveSpaceSafely() settles a dirty Space/structural edit first
// (Keep Editing or a failed save aborts here, exactly as when switching
// folders); then the old Drawer state is cleared once, any in-flight preview
// is invalidated, the old Space's resume checkpoint is flushed, and the
// identity is torn down coherently - the memory-only equivalent of
// SP.applyFolder()'s synchronous identity block. The persistent Recent list
// (and the backend's remembered active folder - there is no "forget" endpoint,
// and startup resuming the previously-active folder after a restart is
// existing intended behavior) may still name old folders; the ACTIVE RUNTIME
// identity below must not.
SP.startMemoryOnly = () => SP.run(async () => {
  SP.clearSetupContext();
  const okToLeave = await SP.leaveSpaceSafely();
  if (!okToLeave) return;
  // The leave decision is already resolved - clear the old Drawer state
  // exactly once, with no second prompt.
  if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return;
  // Any preview still in flight belongs to the OUTGOING Space/folder, and
  // the old Space's queued/in-flight resume checkpoint must land before ANY
  // identity field below changes - same ordering as SP.applyFolder().
  state.previewRequest += 1;
  cancelPreviewWait();
  await SP.flushOutgoingResumeCheckpoint();
  SP.close();
  // Coherent teardown to "no persisted folder identity". browserFolder,
  // output, activeSpaceId, cabinetRecovery, and folderSelected are the
  // fields SP.applyFolder() owns outright; setFolderState("design") clears
  // the rest (folderMode, activeSpace, Space defaults, resume checkpoint,
  // designInventoryId/designTarget) and disables the folder-inventory toggle
  // (it keys off folderSelected).
  state.browserFolder = null;
  state.output = "";
  state.activeSpaceId = null;
  state.cabinetRecovery = null;
  state.folderSelected = false;
  setFolderState("design");
  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  await loadFreshOrdinaryDesignForCurrentFolder();
  toast("Designing without a saved folder. Your work stays in this session — use 'Save design file' to keep it.", false, 9000);
});

SP.startNoSpace = async () => {
  if (state.runtime.hosted) return SP.startMemoryOnly();
  let fallback = false;
  await SP.run(async () => {
    SP.clearSetupContext();
    if (!(await SP.leaveSpaceSafely())) return;
    if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return;
    state.previewRequest += 1;
    cancelPreviewWait();
    await SP.flushOutgoingResumeCheckpoint();
    SP.close();
    let data;
    try {
      data = await api("/api/folder/no-defined-space", {});
      if (!data.folder) throw new Error("No default folder");
    } catch (_error) {
      fallback = true;
      return;
    }
    SP.recent = data.recent || [];
    if (!(await SP.applyFolder(data.folder, { reset: false, initDesign: false, browserFolder: null }))) return;
    await loadFreshOrdinaryDesignForCurrentFolder();
    toast("Designing without a Space. Bins save to the No Defined Space folder.", false, 9000);
  });
  if (fallback) await SP.startMemoryOnly();
};

SP.startUntyped = async () => {
  // Reuse the folder onboarding already chose rather than asking a second
  // time: "I don't know yet" on the type cards is about this folder.
  // accessContext "untyped" keeps the folder-access message honest: this
  // user chose to design without a Space, so it must not lecture about
  // Inventory and Spaces.
  const folder = SP.configureData || await SP.pickFolder({ accessContext: "untyped" });
  if (!folder) return;
  // Inspect first in both modes and never call Use Untyped on a folder that
  // holds an *authoritative* typed Space - committed and ready, or still
  // needing its one-time setup pass - route it into the same collision
  // prompt instead - see Fix 004 Correction 8.B. An inventory-only or
  // inferred candidate is not a committed type, so the explicit exploration
  // choice may make it ordinary Design without deleting its inventory.
  const data = state.runtime.hosted
      ? await SP.inspectHosted(folder)
      : (await api("/api/space/inspect", { output: folder })).folder;
  if (data.folder_mode === "space" && SP.authoritativeTypedSource(data)) {
      SP.collisionFolder = folder;
      SP.collisionData = data;
      SP.collisionOrigin = "untyped";
      SP.showOnly("space-collision-prompt");
      document.getElementById("space-collision-meta").textContent = `${data.space.name} (${data.space.kind})`;
      SP.showDialog();
      return;
  }
  // Reuses the same guarded write path as the Configure prompt's "Use
  // without a Space type" button - see Fix 004 Correction 7.D.
  SP.configureData = folder;
  await SP.useUntypedFolder();
};

// The single validated reader for both Create and Edit, so setup minimums
// (drawer grid capacity/height floor, B4B field/height floor, whole-unit
// Surface presets) are enforced identically in one place - Fix 004
// Correction 11.A6.
SP.readSetupValues = async () => {
  SP.setupValidationStarted = true;
  if (SP.setupKind === "storage_drawers") return SP.readStorageDrawersSetup();
  return SP.readOrdinarySetupValues();
};

// Live feedback uses the same rules as Create/Save, without moving focus or
// entering the cabinet's asynchronous Continue path.
// Field notes have separate hint/error slots so a limit stays visible even
// before an invalid entry. All Create, Edit and live reads share these rules.
SP.setupFieldNote = (selector, text, slot = "hint") => {
  const input = $(selector);
  if (!input) return;
  const id = `${input.id}-setup-${slot}`;
  let note = document.getElementById(id);
  if (!note) {
    note = document.createElement("small");
    note.id = id;
    note.className = slot === "error" ? "field-help status-error" : "field-help";
    note.setAttribute("aria-live", "polite");
    input.after(note);
    input.setAttribute("aria-describedby", [input.getAttribute("aria-describedby"), id].filter(Boolean).join(" "));
  }
  note.textContent = text;
  note.hidden = false;
};

SP.readOrdinarySetupValues = ({ focus = true } = {}) => {
  const form = $("#space-form");
  form.querySelectorAll('[id$="-setup-error"]').forEach(note => { note.hidden = false; note.textContent = ""; });
  form.querySelectorAll('[aria-invalid]').forEach(input => input.removeAttribute("aria-invalid"));
  $("#space-error").hidden = true;
  let firstInvalid = null;
  const fail = (message, selector) => {
    const input = $(selector);
    firstInvalid ||= input;
    const show = focus || SP.setupValidationStarted || input?.dataset.setupTouched || input?.value.trim();
    if (show) {
      SP.setupFieldNote(selector, message, "error");
      input?.setAttribute("aria-invalid", "true");
    }
  };
  const readNumber = selector => {
    const input = $(selector);
    return input.value.trim() && !input.validity.badInput ? Number(input.value) : NaN;
  };
  const kind = SP.setupKind;
  const name = $("#space-name").value.trim();
  if (!name) fail("Give the Space a name.", "#space-name");
  const unit = Number(state.catalog?.base_unit || 7);
  let values = null;

  if (kind === "drawer" || kind === "portable") {
    const prefix = kind === "drawer" ? "drawer" : "portable";
    const dimensions = {};
    for (const axis of ["x", "y", "z"]) {
      const selector = `#${prefix}-${axis}`;
      const raw = readNumber(selector);
      const used = kind === "portable" && axis !== "z" ? SP.storageBoxSnap(raw) : raw;
      dimensions[axis] = used;
      const notes = ["At most 2000 mm."];
      if (kind === "drawer") notes.push(axis === "z"
        ? `Usable drawer height must be at least ${fmt(ordinaryBinMinimumHeight())} mm.`
        : "Must fit at least one Wavefinity unit after wall clearance.");
      if (Number.isFinite(raw) && raw > 0 && Math.abs(raw - used) > 1e-6) {
        const cell = kind === "portable" ? SP.storageBoxPitch() : unit;
        notes.push(`Uses ${fmt(used)} mm (${fmt(used / cell)} ${kind === "portable" && SP.storageBoxGrid() !== "wavefinity" ? "cells" : "units"}).`);
      }
      SP.setupFieldNote(selector, notes.join(" "));
      if (!Number.isFinite(raw) || raw <= 0) fail("Enter a dimension in mm greater than zero.", selector);
      else if (raw > 2000 || used > 2000) fail("Dimensions must be at most 2000 mm.", selector);
      else if (axis === "z") {
        const minimum = kind === "drawer" ? ordinaryBinMinimumHeight() : Number(state.catalog?.b4b_rules?.min_secure_height_mm);
        if (raw < minimum) fail(kind === "drawer"
          ? `Usable drawer height must be at least ${fmt(minimum)} mm.`
          : `A Storage Box's usable height must be at least ${fmt(minimum)} mm.`, selector);
      } else if (kind === "drawer" && SP.drawerCapacity(raw, $("#drawer-grid").value) < 1) {
        fail($("#drawer-grid").value === "wavefinity"
          ? "The drawer must have room for at least one Wavefinity unit after wall clearance."
          : `The drawer must have room for at least one ${state.catalog?.grids?.find(row => row.value === $("#drawer-grid").value)?.label || "Gridfinity"} cell.`, selector);
      } else if (kind === "portable" && used < SP.storageBoxMinimumField()) {
        fail(`A Storage Box needs at least ${fmt(SP.storageBoxMinimumField())} mm of child-bin field.`, selector);
      }
    }
    const liftSelector = `#${prefix}-lift`;
    const liftInput = $(liftSelector);
    const usesLift = kind === "drawer" ? $("#drawer-grid").value !== "wavefinity"
      : SP.storageBoxGrid() !== "wavefinity" && SP.storageBoxFloor() === "none";
    const liftText = liftInput.value.trim();
    if (usesLift && (liftInput.validity.badInput || (liftText && (!Number.isFinite(Number(liftText)) || Number(liftText) < 0)))) {
      fail("Seated lift must be a measured non-negative height or blank for unverified.", liftSelector);
    }
    values = { kind, name, ...dimensions, trimSize: null,
      ...(kind === "portable" ? { extra: { ...SP.storageBoxGridFields(), storage_box: SP.readStorageBoxForm() } } : {}),
      ...(kind === "drawer" ? { extra: { grid: $("#drawer-grid").value, seated_lift_mm: usesLift && liftText ? Number(liftText) : null } } : {}) };
  } else if (kind === "surface") {
    const trimSize = $("#surface-trim").value;
    const maxX = readNumber("#surface-x"), maxY = readNumber("#surface-y");
    const trimValid = SP.surfacePresetMap()[trimSize] !== undefined;
    if (!trimValid) fail("Choose Small, Medium, or Large trim.", "#surface-trim");
    for (const [axis, raw] of [["x", maxX], ["y", maxY]]) {
      const selector = `#surface-${axis}`;
      const resolvedAxis = SP.resolveSurface(raw, raw, trimSize);
      SP.setupFieldNote(selector, "");
      if (trimValid) {
        if (!resolvedAxis.ok) fail(resolvedAxis.error, selector);
        else if (Math.abs(raw - resolvedAxis.outerX) > 1e-6) {
          SP.setupFieldNote(selector, `Uses ${fmt(resolvedAxis.outerX)} mm outside (${fmt(resolvedAxis.unitsX)} units inside).`);
        }
      }
    }
    const resolved = SP.resolveSurface(maxX, maxY, trimSize);
    if (resolved.ok) values = { kind, name, x: resolved.fieldX, y: resolved.fieldY,
      z: SP.surfacePresetMap()[trimSize], trimSize, extra: { max_x_mm: maxX, max_y_mm: maxY } };
  } else if (kind === "pegboard") {
    const mode = $("#pegboard-size-mode").value;
    const standard = SP.pegboardStandard($("#pegboard-standard").value);
    for (const axis of ["x", "y"]) {
      const selector = mode === "holes" ? `#pegboard-holes-${axis}` : `#pegboard-${axis}`;
      const raw = readNumber(selector);
      SP.setupFieldNote(selector, mode === "holes" ? "From 1 to 500 whole holes or slots." : "At most 2000 mm.");
      if (mode === "holes") {
        if (!Number.isInteger(raw) || raw < 1 || raw > 500) fail("Enter a whole hole or slot count from 1 to 500.", selector);
      } else if (!Number.isFinite(raw) || raw <= 0 || raw > 2000) fail("Enter a dimension greater than zero and at most 2000 mm.", selector);
      else if (standard && Math.floor(raw / standard[`pitch_${axis}_mm`] + 1e-9) < 1) {
        fail("The board must contain at least one mount position on this side.", selector);
      }
    }
    const resolved = SP.resolvePegboard();
    if (!resolved.ok && !firstInvalid) fail(resolved.error, "#pegboard-standard");
    if (resolved.ok) values = { kind, name, x: resolved.width, y: resolved.height, z: 350, trimSize: null,
      extra: { pegboard_standard: resolved.standard.id,
        pegboard_thickness_mm: Number($("#pegboard-thickness").value), pegboard_size_mode: resolved.mode,
        pegboard_holes_x: resolved.holesX, pegboard_holes_y: resolved.holesY } };
  } else {
    SP.fail("Choose a Space type.");
    return null;
  }
  if (firstInvalid) {
    if (focus) firstInvalid.focus();
    return null;
  }
  return values;
};

SP.refreshSetupError = event => {
  if (event?.target?.matches?.("input, select, textarea")) {
    event.target.dataset.setupTouched = "1";
    SP.setupChangedField = event.target.id ? `#${event.target.id}` : null;
  }
  if (SP.setupKind === "storage_drawers") {
    $("#space-error").hidden = true;
    $("#space-form").querySelectorAll('[id$="-setup-error"]').forEach(note => {
      note.textContent = "";
      note.hidden = true;
    });
    return;
  }
  SP.readOrdinarySetupValues({ focus: false });
};

SP.create = async () => {
  if (SP.isUpdate) return SP.updateSpace();
  // Fix 1019: hard preflight - the app cannot run without DP (drawer-panel.js
  // failed to load), so fail HERE: before the folder picker, before the
  // safe-leave prompt, before any Space persistence, and before identity
  // adoption. The failure path creates no Space metadata and adopts no
  // half-open identity; the setup form stays open with a plain-language
  // error instead of the cryptic "DP is not defined".
  if (typeof DP === "undefined") {
    SP.fail("Something didn't load properly. Try reloading the page.", "#space-create");
    return;
  }
  const values = await SP.readSetupValues();
  if (!values) return;
  let { kind, name, x, y, z, trimSize, extra = {} } = values;
  if (kind === "storage_drawers" && state.runtime.hosted) {
    // Hosted Create assigns the stable drawer IDs here, exactly once; the
    // server keeps them. Local Create lets Python assign them.
    const prepared = StorageDrawers.prepareCreateDraft({ kind, name, x, y, z, ...extra });
    extra = { ...StorageDrawers.gridFields(prepared), storage_drawers: prepared.storage_drawers };
    z = prepared.z;
  }
  const migrating = Boolean(SP.configureData);
  let folder = SP.configureData || null;

  if (!migrating && state.runtime.hosted) {
    let home = SP.hostedHome || await WFFileSystem.load("home");
    if (home?.handle) {
      if (!(await WFFileSystem.requestReadWritePermission(home.handle))) {
        SP.fail("Folder access was not granted. Your Space details are still here; choose the folder again and allow read/write access.", "#space-create");
        return;
      }
    } else {
      const picked = await SP.pickFolder({ stayOnSetup: true, home: true });
      if (!picked) return;
      home = { handle: picked.handle };
      await WFFileSystem.save("home", home);
      SP.hostedHome = home;
      document.getElementById("space-folder-help").hidden = true;
      document.getElementById("space-create").textContent = "Create Space";
    }
    try {
      folder = { handle: await home.handle.getDirectoryHandle(name, { create: true }), name, home_name: name };
    } catch (_error) {
      SP.fail("That Space name can't be used as a folder name. Change the name and try again.", "#space-name");
      return;
    }
  }

  if (!migrating && state.runtime.hosted) {
      const data = await SP.inspectHosted(folder);
      // A folder holding an *authoritative* typed Space - committed and
      // ready, or still needing its one-time setup pass - must never be
      // treated as a brand-new create target; it always collision-prompts
      // instead, in both modes - see Fix 004 Correction 7.B. An
      // inventory-only or inferred candidate is existing Wavefinity content,
      // not a committed type, so it falls through to the confirmation below.
      if (data.folder_mode === "space" && SP.authoritativeTypedSource(data)) {
          SP.collisionFolder = folder;
          SP.collisionData = data;
          SP.collisionOrigin = "create";
          SP.showOnly("space-collision-prompt");
          document.getElementById("space-collision-meta").textContent = `${data.space.name} (${data.space.kind})`;
          SP.showDialog();
          return;
      }
      // Existing Wavefinity content of either classified mode must not be
      // silently repurposed as this new Space - confirm explicitly, reusing
      // the already-entered Space setup values - see Fix 004 Correction 7.C.
      if (data.exists) {
          SP.pendingConfigureFolder = folder;
          SP.showOnly("space-existing-inventory-prompt");
          document.getElementById("space-existing-inventory-meta").textContent =
              state.runtime.hosted ? folder.name : String(folder);
          SP.showDialog();
          return;
      }
  }
  SP.configureData = null;

  // Resolve the safe-leave decision BEFORE any write to the target folder
  // (inventory migration, metadata write) or backend mutation, and before
  // the new active handle is saved (Fix 019 correction C1.2/C1.3). This
  // covers Create New Space, Configure Existing and migrate, in both hosted
  // and local runtimes - Cancel or a failed save must abort here, leaving
  // the target folder, the backend's remembered active folder, and the
  // previously active handle all untouched.
  const okToLeave = await SP.leaveSpaceSafely();
  if (!okToLeave) return;

  let info;
  if (state.runtime.hosted) {
    // Read/write the *selected target's* inventory filename, never the
    // previously-active folder's - see Fix 004 Correction 7.A.
    const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
    const result = await api(migrating ? "/api/space/configure-text" : "/api/space/create-text", {
      inventory_text: inventoryText, inventory_title: name,
      name, kind, x, y, z, ...extra, ...(trimSize ? { trim_size: trimSize } : {}),
    });
    // Fix 096 A3: the inventory write and the metadata write are one logical
    // commit - if the metadata write fails, put the previous Inventory text
    // back rather than leave a half-applied new Space.
    const inventoryName = SP.inventoryFilenameFor(folder);
    await WFFileSystem.writeText(folder.handle, inventoryName, result.inventory_text);
    const space = result.layout.space;
    // This call owns the new Space definition, but not the bin/part
    // defaults - on Create there is nothing yet to preserve (the writer's
    // own under-lock defaults already match), and on Configure Existing/
    // migrate, leaving them unset lets the writer preserve the newest
    // under-lock value instead of a copy captured here before its own
    // read/lock (Fix 032 Correction 4, C4.1 - this mirrors the previous
    // pre-lock SP.readMetadata() capture that used to run only when
    // `migrating`, now removed).
    let metadata;
    try {
      metadata = await SP.writeMetadata(folder.handle, "space", space, true, {});
    } catch (error) {
      try {
        await WFFileSystem.writeText(folder.handle, inventoryName, inventoryText);
      } catch (_restore) {
        // Fix 096 A3: a failed restore is a partial commit, not a clean
        // failure - say so explicitly instead of reporting the original
        // error while the new Inventory may still be durable.
        console.error(error, _restore);
        toast("The Space could not be saved and the previous Inventory could not be restored. Open the folder and check its Inventory before continuing.", true, 7000);
        return;
      }
      throw error;
    }
    // Activate the selected target folder itself, not whatever folder was
    // previously active - see Fix 004 Correction 7.A. state.browserFolder
    // itself is set inside SP.applyFolder() below, never here (Fix 032
    // Correction 2, C2.1) - this only writes the remembered-active record.
    // Fix 096 A3: a failed active-handle save is a different failure class -
    // the Space files above committed fine, so keep the valid Space, say so
    // truthfully, and continue activation instead of reporting a failed
    // create/update.
    try {
      await WFFileSystem.save("active", { handle: folder.handle, space_id: metadata.space_id, ...(folder.home_name ? { home_name: folder.home_name } : {}) });
      SP.pendingReconnect = null;
    } catch (_remember) {
      toast(migrating
        ? "The Space was updated, but it could not be remembered as the current Space. Open it again from the Space list."
        : "The Space was created, but it could not be remembered as the current Space. Open it again from the Space list.", true);
    }
    info = {
      folder: folder.name, folder_name: folder.name, folder_mode: "space", space,
      space_id: metadata.space_id,
      inventory: true, keep_bin_defaults: metadata.keep_bin_defaults,
      bin_defaults: metadata.bin_defaults, part_defaults: metadata.part_defaults,
      // A brand-new Space never inherits the previous Space's in-memory
      // resume design just because this manually-built info could have
      // omitted these fields - state them explicitly (Correction 2, item 8).
      resume_design: metadata.resume_design ?? null,
      resume_pending: Boolean(metadata.resume_pending),
    };
  } else {
    const payload = {
      name, kind, x, y, z, keep_bin_defaults: true,
      ...extra, ...(trimSize ? { trim_size: trimSize } : {}),
    };
    if (migrating) payload.output = folder;

    let data;
    try {
      data = await api(
        migrating ? "/api/space/configure" : "/api/space/create",
        payload,
      );
    } catch (error) {
      if (!migrating) {
        const message = String(error?.message || "Could not create this Space.");
        const nameError =
          message.includes("Space name") ||
          message.includes("space name") ||
          message.includes("Windows folder");
        console.error(error);
        SP.fail(nameError ? "Please check the Space name and try again." : "The Space could not be created. Please try again.", nameError ? "#space-name" : "#space-create");
        return;
      }
      throw error;
    }
    SP.recent = data.recent || [];
    info = data.folder;
    // Fix 096 A3: the Space committed fine but could not be remembered as
    // current - say so truthfully instead of silently dropping the warning.
    if (data.remember_warning) toast(data.remember_warning, true);
  }

  try {
    if (state.runtime.hosted) {
      try { await SP.rememberHostedRecent(folder, info); }
      catch (error) { console.error(error); }
    }
    // The leave decision is already resolved above - clear the old Drawer
    // state exactly once, with no second prompt.
    if (!(await SP.resetDrawer({ skipSafeLeave: true }))) throw new Error("Could not leave the previous Space");
    // SP.create() always follows with an explicit
    // loadFreshOrdinaryDesignForCurrentFolder call below, which installs the
    // starter design itself - skip applyFolder's own (redundant) activation.
    const applyOptions = { initDesign: false, reset: false };
    // `folder` is a real handle-bearing object only in the hosted branch
    // above - in the local branch it may be a plain output path string, so
    // state.browserFolder must not be set from it there.
    if (state.runtime.hosted) applyOptions.browserFolder = folder;
    await SP.applyFolder(info, applyOptions);
    SP.storageDrawersForm?.markPristine?.();
    SP.setupFormSnapshot = null;
    SP.close();

    // Fix 103 (Section F): a structural Space lands on its structural Design
    // (cabinet / case), never on an ordinary starter bin. No generic bin is
    // created until the user explicitly chooses New Bin.
    const createdStructural = DP.structuralTargetEnabled ? DP.structuralKindFor({ kind }) : null;
    if (createdStructural) {
      await SP.landOnStructuralDesign(createdStructural);
    } else {
      // Ordinary typed Spaces land Space-first on the Space just created: the
      // starter design is installed for the session, then the Space workspace
      // opens in Space mode - never an unbound generic starter bin in Design.
      await loadFreshOrdinaryDesignForCurrentFolder();
      await DL.ensureLoaded();
      if (!(await DP.enter("space"))) throw new Error("Space workspace did not open");
    }
  } catch (error) {
    console.error(error);
    SP.showHome();
    toast("The Space was created, but could not be opened. Try opening it from the Space list or choose its folder again.", true, 7000);
  }
};

// Fix 103 (Section F): select the structural target for the active Space and
// open Design on it. Leaves state.design / state.cleanDesign untouched.
SP.landOnStructuralDesign = async structuralKind => {
  SP.resetDesignSession();
  DP.setDesignTarget({ kind: "structural", structural: true, structuralKind, rowId: null, drawerId: null });
  if (!(await DP.enter("design", false))) return false;
  activatePreviewView(preferredDesignView());
  return true;
};

// ------------------------------------------------------------ design/session activation (Fix 019 Item 1/5)
//
// Every session-only editor flag that must never leak from one typed-Space
// identity to another.
SP.resetDesignSession = () => {
  state.designInventoryId = null;
  state.designTarget = null; // Fix 103
  state.spaceStarterPreviewPending = false;
  state.lastOrdinaryDesign = null;
  state.drafts = {};
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  if (typeof resetNestPhotoSession === "function") resetNestPhotoSession();
  if (typeof clearDraftSelection === "function") clearDraftSelection();
};

// Builds the clean starter design for `space` into state.design/
// state.cleanDesign. The Designer always starts an ordinary Bin - a Storage Box
// or Base Trim is a structural output of the Space, not a Designer object.
// Does not touch preview/toast - callers decide those.
SP.installSpaceStarterDesign = async () => {
  state.spaceStarterPreviewPending = true;
  state.design = freshDesignForCurrentFolder();
  state.cleanDesign = clone(state.design);
};

// The ONE authoritative typed-Space design/session activation path (Fix 019
// Item 1). SP.applyFolder calls this after folder/Space identity is already
// current, for every path that activates a typed Space: local/hosted
// startup resume, Open Existing Space, Recent Space selection, collision
// "Open this Space", a newly created Space, a configured/migrated Space, and
// any later folder switch. The resulting starter design is clean/untouched:
// opening/switching alone never creates an Inventory row.
SP.initializeDesignForActiveSpace = async () => {
  if (state.folderMode !== "space" || !state.activeSpace || !state.catalog) return;
  SP.resetDesignSession();

  let restored = false;
  let resumeValidationFailed = false;
  // A checkpoint left by an older version may hold a Storage Box or Base Trim
  // design. Those are Space outputs now, not Designer objects: the checkpoint is
  // left untouched and the Designer starts a fresh Bin instead.
  const resumeIsStructural = Boolean(state.spaceResumeDesign) && (
    state.spaceResumeDesign.design_kind === "base_trim" || Boolean(state.spaceResumeDesign.box?.b4b?.enabled));
  if (state.spaceResumeDesign && !resumeIsStructural) {
    try {
      const result = await api("/api/design/validate", {
        design: clone(state.spaceResumeDesign),
      });
      // A restored design bypasses SP.installSpaceStarterDesign() and
      // applySpaceSizingDefaults() entirely - it is the exact design the
      // user left, not a fresh starter seeded from remembered defaults.
      state.design = result.design;
      state.cleanDesign = clone(result.design);
      state.spaceStarterPreviewPending = false;
      restored = true;
    } catch (error) {
      // The stored checkpoint itself is left untouched - a validation
      // failure here must never delete or rewrite recoverable user data.
      resumeValidationFailed = true;
      await SP.setAsideBin(SP.snapshotStoredBin(state.spaceResumeDesign));
    }
  }

  // Resume is a recovery snapshot; bind it back to its existing Inventory
  // source when that exact canonical design is already present.
  if (restored && typeof DL !== "undefined" && DL.ensureLoaded) {
    await DL.ensureLoaded();
    const key = JSON.stringify(state.design);
    const matches = Object.entries(DL.layout?.design_specs || {})
      .filter(([, design]) => JSON.stringify(design) === key);
    if (matches.length === 1) {
      state.designInventoryId = matches[0][0];
      state.designTarget = null; // Fix 103
    } else if (matches.length === 0 && typeof freshDesignForCurrentFolder === "function" &&
               typeof persistSpaceDesignSource === "function") {
      // Fix 082 B: a resume checkpoint can represent real, meaningful work
      // that never got a durable Inventory row (e.g. a crash between the
      // preview and the debounced autosave). Showing that as editable
      // current work with nothing backing it is an orphan that could
      // vanish on the next navigation. A checkpoint that is not
      // distinguishable from an untouched fresh starter needs no row yet;
      // anything else is atomically attached to a durable row now, through
      // the same owner every other meaningful change already uses, before
      // it is exposed as editable.
      const untouched = JSON.stringify(freshDesignForCurrentFolder()) === key;
      if (!untouched) {
        try { await persistSpaceDesignSource(null, true); }
        catch (_error) { await SP.setAsideBin(SP.snapshotStoredBin(state.spaceResumeDesign)); }
      }
    }
  }

  // Fix 103 (Section F): structural Spaces activate the structural target, not
  // an ordinary bin. The legacy row binding is cleared (the row, if any, stays
  // in Inventory); no starter design, form sync or ordinary preview follows.
  // Fix 1019: DP (drawer-panel.js) may be unavailable if its script failed to
  // load. Defense-in-depth only: the primary preflight (Change 3A, top of
  // SP.applyFolder) throws before this function is ever reached on the
  // typed-Space path, so this guard exists solely for a hypothetical future
  // caller that bypasses applyFolder. The app cannot run without DP, so this
  // is a hard, friendly abort: throw a plain-language error instead of the
  // cryptic "DP is not defined" ReferenceError.
  if (typeof DP === "undefined") {
    throw new Error("Something didn't load properly. Try reloading the page.");
  }
  const structuralKind = DP.structuralTargetEnabled ? DP.structuralKindFor(state.activeSpace) : null;
  if (structuralKind) {
    state.designInventoryId = null;
    DP.setDesignTarget({ kind: "structural", structural: true, structuralKind, rowId: null, drawerId: null });
    return;
  }
  await DL.ensureLoaded();
  if (!restored) await SP.installSpaceStarterDesign();
  // Fix 060 Correction 3: this is the one shared syncForm() call for every
  // way a typed Space activates/resumes a design (restored checkpoint or a
  // fresh starter), so this is the single place that needs to reseed/clear
  // the remembered Lid/Handle/Label memory for the design just bound here.
  bindLidMemoryForDesign();
  syncForm();
  // The active Space identity, state.design, and the preview must all
  // belong to the same Space/design generation - request a fresh preview
  // for the design just installed here, rather than leaving the 3D view
  // showing whatever an earlier Space last rendered until some later edit
  // triggers one (Fix 032 Correction 3, C3.2). Fire-and-forget: it owns its
  // own errors and stale-request guard, so nothing here needs to await it.
  // startSpaces()'s own startup fallback preview checks this flag so a
  // Space-activating startup does not also fire a redundant duplicate.
  if (typeof refreshPreview === "function") {
    SP._activationPreviewRequested = true;
    // A starter preview installed only because the stored resume design
    // just failed validation must not silently overwrite that bad
    // checkpoint merely because the starter itself previews validly - it
    // stays untouched for possible recovery until a real edit/new/open
    // replaces it with ordinary refreshPreview() (Fix 032 Correction 4,
    // C4.2). Every other case (no stored resume, or a successfully
    // restored one) persists exactly as before.
    refreshPreview({ persistResume: !resumeValidationFailed });
  }
};

// Enters the same explicit setup/migration screen for a folder that needs
// the one-time setup pass: prefilled for a recognized legacy kind, else the
// Configure-vs-Untyped prompt. Shared by SP.openExisting() and SP.launch()
// so neither one silently migrates a folder it merely inspected - see
// Fix 004 Correction 6.A/E.
SP.enterSetupFor = (folder, data) => {
    SP.configureData = folder;
    SP.setupPrefillSpace = null;

    // Includes "surface" for recovery: a Surface created during an earlier
    // incomplete v4 pass, missing setup_version, must still safely prefill
    // instead of falling through to the generic Configure-vs-Untyped prompt
    // - see Fix 004 Correction 7.I.
    const candidate = data?.space || data?.setup_prefill_space;
    const recognized = candidate &&
      ["drawer", "surface", "box", "portable", "pegboard", "storage_drawers"].includes(candidate.kind);

    // A recoverable Storage Drawers definition re-enters its own form, prefilled,
    // keeping its drawer identities - never a blank generic picker.
    if (recognized && candidate.kind === "storage_drawers") {
        SP.setupPreserveIds = true;
        SP.showSetup("storage_drawers", candidate);
        return;
    }

    // Only a committed type goes straight to its own setup form.
    if (data?.space && recognized && SP.authoritativeTypedSource(data)) {
        const kind = candidate.kind === "box" ? "portable" : candidate.kind;
        SP.showSetup(kind, candidate);
        return;
    }

    if (recognized) {
        SP.setupPrefillSpace = clone(candidate);
    }

    // Existing Wavefinity content with no committed typed Space goes straight
    // to the three choices. A truly unmanaged folder still gets the explicit
    // Configure-vs-Untyped confirmation first.
    if (recognized || data?.exists) {
        SP.showTypeCards();
        return;
    }

    SP.showOnly("space-configure-prompt");
    SP.showDialog();
};

SP.openExisting = async () => {
    const folder = await SP.pickFolder({ spaceRoot: true });
    if (!folder) return;
    const data = state.runtime.hosted
        ? await SP.inspectHosted(folder)
        : (await api("/api/space/inspect", { output: folder })).folder;
    if (data.needs_setup) SP.enterSetupFor(folder, data);
    else await SP.afterPick(folder);
};

SP.configureFolder = async () => {
    SP.showTypeCards();
};

SP.useUntypedFolder = async () => {
    if (state.runtime.hosted) {
        const folder = SP.configureData;
        const data = await SP.inspectHosted(folder);
        // Never demote an *authoritative* typed Space just because "Use
        // without a Space type" reached it - collision-prompt instead, the
        // hosted equivalent of the local backend's refuse guard - see
        // Fix 004 Correction 7.D. An inventory-only or inferred candidate is
        // not a committed type and may be committed as Design.
        if (data.folder_mode === "space" && SP.authoritativeTypedSource(data)) {
            SP.configureData = null;
            SP.collisionFolder = folder;
            SP.collisionData = data;
            SP.collisionOrigin = "untyped";
            SP.showOnly("space-collision-prompt");
            document.getElementById("space-collision-meta").textContent = `${data.space.name} (${data.space.kind})`;
            SP.showDialog();
            return;
        }
        // Resolve the safe-leave decision BEFORE writing the target folder's
        // own metadata (Fix 019 correction C1.3) - Cancel or a failed save
        // must abort before "design" is committed to this folder.
        const okToLeave = await SP.leaveSpaceSafely();
        if (!okToLeave) return;
        await SP.writeMetadata(folder.handle, "design", null, true);
        SP.configureData = null;
        // The leave decision above already covers this switch - skip asking
        // again inside SP.useHostedFolder().
        const info = await SP.useHostedFolder(folder, { skipLeaveCheck: true });
        if (!info) return; // switch aborted (cancelled or a failed save) - stay put
        await loadFreshOrdinaryDesignForCurrentFolder();
    } else {
        // Resolve the safe-leave decision BEFORE the backend mutates the
        // active folder (Fix 019 correction C1.2) - Cancel or a failed save
        // must abort before /api/space/use-untyped ever runs.
        const okToLeave = await SP.leaveSpaceSafely();
        if (!okToLeave) return;
        const data = await api("/api/space/use-untyped", { output: SP.configureData });
        // Clear the selected-folder setup context now that it has been
        // used, so a later Create New Space cannot accidentally reuse it -
        // see Fix 004 Correction 7.F.
        SP.configureData = null;
        SP.recent = data.recent || [];
        // The leave decision is already resolved - clear the old Drawer
        // state once, with no second prompt, then adopt the new folder.
        if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return;
        if (!(await SP.applyFolder(data.folder, { reset: false }))) return;
        SP.close();
        await loadFreshOrdinaryDesignForCurrentFolder();
        toast(`Designs will save to ${data.folder?.folder || state.output}.`, false, 6500);
    }
};



SP.fail = (message, selector) => {
  const input = selector && $(selector);
  if (input?.matches("input, select, textarea")) {
    SP.setupFieldNote(selector, message, "error");
    input.setAttribute("aria-invalid", "true");
  } else {
    $("#space-error").textContent = message;
    $("#space-error").hidden = false;
  }
  input?.focus();
};

// Reopens the remembered hosted folder (permission already granted). A folder
// that was moved or deleted is reported plainly and the one pick is offered.
SP.resumeSavedHosted = async saved => {
  try {
    const home = saved.home_name ? await WFFileSystem.load("home") : null;
    const handle = saved.home_name ? await home.handle.getDirectoryHandle(saved.home_name) : saved.handle;
    const folder = { handle, name: saved.home_name || handle.name, ...(saved.home_name ? { home_name: saved.home_name } : {}) };
    const data = await SP.inspectHosted(folder);
    SP.assertExpectedHostedIdentity(data, saved.space_id || null);
    if (data.needs_setup) {
      SP.enterSetupFor(folder, data);
      return;
    }
    const info = await SP.useHostedFolder(folder, { expectedSpaceId: saved.space_id || null });
    if (!info) { SP.showHome(); return; } // switch aborted mid-startup - fall back quietly
    if (info.folder_mode === "space") SP.showResume(info, { startup: true });
  } catch (error) {
    if (error?.name === "NotFoundError" || error?.name === "TypeMismatchError") {
      SP.pendingReconnect = null;
      SP.showHome(`The folder "${saved.handle?.name || "you used last time"}" was moved or deleted. Choose a folder to continue - you can make a new one in the folder dialog.`);
      return;
    }
    console.error(error);
    SP.showHome("The Space could not be opened. Choose it from the Space list and try again.");
  }
};

// One click on a user gesture: restore access to the remembered folder.
SP.reconnectSavedFolder = () => SP.run(async () => {
  const saved = SP.pendingReconnect;
  if (!saved?.handle) { SP.showHome(); return; }
  let granted = false;
  try {
    granted = await WFFileSystem.requestReadWritePermission(saved.handle);
  } catch (error) {
    if (error?.name === "NotFoundError") {
      SP.pendingReconnect = null;
      SP.showHome(`The folder "${saved.handle.name}" was moved or deleted. Choose a folder to continue.`);
      return;
    }
    throw error;
  }
  if (!granted) {
    SP.showHome("Folder access was not allowed. Choose Reconnect and allow access, or pick a folder.");
    return;
  }
  SP.pendingReconnect = null;
  if (saved.active) await SP.resumeSavedHosted(saved.active);
  else if (!saved.homeReconnect) await SP.resumeSavedHosted(saved);
  else SP.showHome();
});

// Fix 019 Item 6: "no remembered folder" and "permission not (yet) granted"
// are expected, silent outcomes - Welcome with no message. An exception from
// actually reading/classifying/identifying the remembered folder is a real
// condition (damaged/newer metadata, an identity mismatch, a read failure)
// and must reach the user as visible text on Welcome, not be swallowed into
// an ordinary-looking Welcome screen. Recovery never mutates the
// damaged/newer metadata itself - it only stops and explains.
SP.launch = async () => {
  if (state.runtime.hosted) {
    try {
      SP.recent = await SP.loadHostedRecent();
    } catch (_error) {
      SP.recent = [];
    }
    let saved = null;
    let hasPermission = false;
    try {
      saved = await WFFileSystem.load("active");
      SP.hostedHome = await WFFileSystem.load("home");
      const reconnectHome = Boolean(SP.hostedHome?.handle && (!saved?.handle || saved.home_name));
      const permissionRecord = reconnectHome ? SP.hostedHome : saved;
      // Startup is not a user gesture: only already-granted permission may
      // resume silently. A handle whose permission needs renewing falls
      // through to Welcome, where an explicit action supplies the gesture.
      // The saved record itself is kept.
      hasPermission = Boolean(permissionRecord?.handle) && await WFFileSystem.queryReadWritePermission(permissionRecord.handle);
      SP.pendingReconnect = permissionRecord?.handle ? (reconnectHome ? { ...permissionRecord, homeReconnect: true, active: saved } : saved) : null;
    } catch (error) {
      // A thrown exception here means the saved-handle read or the
      // permission query itself failed (damaged storage, a read error, a
      // permission-query failure) - a real startup read failure, not the
      // ordinary "nothing saved" / "permission not granted" outcomes above,
      // so it must be visible (Fix 019 correction C1.5), consistent with
      // Fix 019 Item 6's other startup-read-failure handling below.
      SP.showHome(error?.message || "Wavefinity could not read your saved folder.");
      return;
    }
    if (!hasPermission) {
      // The browser wants re-approval (needs a click). Offer one reconnect
      // action for the remembered folder instead of a fresh pick.
      if (SP.pendingReconnect) SP.showHome();
      else SP.showResume(null, { startup: true });
      return;
    }
    SP.pendingReconnect = null;
    if (saved?.handle) await SP.resumeSavedHosted(saved);
    else SP.showResume(null, { startup: true });
    return;
  }

  try {
    // The backend resolves the active Space by its ID (recovering a renamed
    // folder in the same parent) before falling back to the saved path.
    const resp = await api("/api/space/startup", {});
    SP.recent = resp.recent || [];
    SP.otherSpaces = resp.other_spaces || [];
    SP.otherSpacesFresh = Array.isArray(resp.other_spaces);
    SP.storage = resp.storage || null;
    const data = resp.folder;
    if (!data || data.missing) { SP.showResume(null, { startup: true }); return; }
    if (data.needs_setup) {
      SP.enterSetupFor(data.folder, data);
      return;
    }
    if (!(await SP.applyFolder(data))) { SP.showHome(); return; }
    // The routing decision must always end somewhere definite: the startup
    // cover is dismissed only once this resolves.
    if (data.folder_mode === "space") SP.showResume(data, { startup: true });
    else SP.close();
  } catch (error) {
    console.error(error);
    SP.showHome("The Space could not be opened. Choose it from the Space list and try again.");
  }
};

