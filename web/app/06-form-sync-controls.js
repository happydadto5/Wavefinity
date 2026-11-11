"use strict";

function updateDesignFromForm() {
  const design = state.design;
  const prevBoxX = design.box.x;
  if (isSurfaceBinDesign(design)) resolveSurfaceBase(design, { fromForm: true });
  const prevBoxY = design.box.y;
  const newBoxX = readBinSizeField("x");
  const newBoxY = readBinSizeField("y");
  design.box.x = newBoxX;
  design.box.y = newBoxY;
  const boxFootprintChanged = design.box.x !== prevBoxX || design.box.y !== prevBoxY;
  // Width/Length handlers update state before this debounced read, so the
  // dedicated pending flag detects a resize even when prevBoxX/Y already
  // contain the new values.
  const sideOpeningResizeChanged = state.binFootprintResizePending || boxFootprintChanged;
  const prevBoxZ = design.box.z;
  design.box.z = readBinSizeField("z");
  if (boxFootprintChanged) {
    turnOffNestAutoSizeForManualEdit();
  }
  checkBinSizeChange();
  if (sideOpeningResizeChanged) {
    reconcileSideOpeningsAfterResize(design);
    syncSideOpeningControls();
    state.binFootprintResizePending = false;
  }
  if (design.box.z !== prevBoxZ) {
    const setAutoConnectorHeight = selector => {
      const input = $(selector);
      const next = fmt(design.box.z);
      if (input && input.value !== next) {
        input.value = next;
        flashField(input);
      }
    };
    if ($("#connector-height-mode").value === "same") {
      setAutoConnectorHeight("#connector-bin-a-height");
      setAutoConnectorHeight("#connector-bin-b-height");
    } else {
      setAutoConnectorHeight("#connector-bin-a-height");
      autoAdjustConnectorFields();
    }
  }
  const b4bOn = b4bEnabled();
  const currentStackMode = stackMode();
  const hasOrdinaryLid = Boolean(design.box.lid?.enabled);
  const stackValues = stackRuleValues(currentStackMode, design.box.wall);
  // Wall is resolved before base: the required base depends on the *final*
  // wall value, so it must be looked up after the wall choice is settled.
  const previousWall = design.box.wall;
  const wallRules = state.catalog?.wall_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const defaultWall = b4bOn
    ? number(b4bRules.default_wall_mm, 1.6)
    : (wallRules.default_mm ?? 0.8);
  const minWall = b4bOn
    ? b4bMinWall()
    : (wallRules.min_mm ?? 0.2);
  const maxWall = wallRules.max_mm ?? 2.4;
  const wallChoice = $("#wall-thickness").value;
  design.box.standard_walls = !b4bOn && wallChoice === "standard";
  design.box.wall = design.box.standard_walls
    ? defaultWall
    : Math.max(minWall, Math.min(maxWall, number(
        wallChoice,
        design.box.wall ?? defaultWall,
      )));
  $("#wall-thickness").value = design.box.standard_walls ? "standard" : fmt(design.box.wall);
  if (design.box.wall !== previousWall) autoAdjustConnectorFields();
  const baseChoice = $("#base-thickness").value;
  design.box.standard_base = !isSurfaceBinDesign(design) && !b4bOn && currentStackMode === "none" && baseChoice === "standard";
  const defaultBase = b4bOn
    ? number(b4bRules.default_base_mm, 1.6)
    : number(state.catalog?.base_rules?.default_mm, 0.8);
  if (!isSurfaceBinDesign(design)) design.box.base_thickness = design.box.standard_base
    ? defaultBase
    : number(baseChoice, design.box.base_thickness ?? defaultBase);
  if (currentStackMode !== "none") {
    const minBase = stackBaseMinForWall(currentStackMode, design.box.wall);
    design.box.base_thickness = Math.max(minBase, design.box.base_thickness);
  }
  design.part_name = $("#part-name").value;
  readLiftGrabberForm(design);
  if (editingEdgeMount()) readEdgeMountForm(design);
  readSideOpeningForm(design);
  syncRimLabelFromFeatures();
  const newOutput = $("#output-folder").value.trim();
  if (!state.runtime.hosted && newOutput !== state.output) {
    state.output = newOutput;
    saveOutputPreference(newOutput);
  }
  state.connector = {
    tolerance: number($("#connector-tolerance").value, state.connector.tolerance),
    length: number($("#connector-length").value, state.connector.length),
    arm_thickness: number($("#connector-arm-thickness")?.value, state.connector.arm_thickness ?? 1.0),
    height: state.connector.height,
    bin_a_height: number($("#connector-bin-a-height").value, state.design.box.z),
    bin_b_height: number($("#connector-bin-b-height").value, state.design.box.z),
    different_heights: $("#connector-height-mode").value === "different",
    position: 0,
    axis: "y",
  };
  readPegboardMountForm(design);
  readStackForm(design);
  if (isSurfaceBinDesign(design) && surfaceStackingBlocked(design))
    design.layout.surface_lightweight_base = false;
  syncSurfaceControls();
}

// Fix 096 A4: output saves run one at a time, in the order the user made
// them - an older request can never finish (and become durable) after a newer
// one. A failed link never breaks the chain.
let outputPreferenceQueue = Promise.resolve();
const saveOutputPreference = debounce(output => {
  if (state.runtime.hosted) return;
  outputPreferenceQueue = outputPreferenceQueue.then(() =>
    // Fix 096 A4: a failed save must be visible instead of silent.
    api("/api/preferences", { output })
      .catch(() => toast("The output folder could not be remembered.", true))
  );
}, 500);


function updateNudgeUI() {
  const el = $("#layout-help");
  if (!el) return;
  if (state.dividerSegmentHover?.action === "blocked") {
    el.textContent = "That merge would make an irregular compartment. Compartments must stay rectangular.";
  } else if (state.dividerSegmentHits.length) {
    el.textContent = "Click a divider segment to combine compartments. Click a dashed segment to restore it. Compartments stay rectangular.";
  } else if (state.nudgeFeedback) {
    el.innerHTML = `<strong>Moved ${state.nudgeFeedback.amount}</strong> &nbsp;·&nbsp; Arrow: 1 mm | Shift: 10 mm | Ctrl: 0.1 mm`;
  } else {
    el.textContent = "Use Arrow keys or drag to move";
  }
}

function updatePreviewHelp(view) {
  const el = $("#preview-help");
  if (!el) return;
  if (view === "drawer") {
    el.textContent = "Drag the floor to pan (or right-drag). Wheel or −/+ to zoom, Fit to reset.";
  } else if (view !== "2d") {
    el.textContent = "Drag to spin, or click the arrows for a 15° step (shift-click for 2°). Wheel to zoom, double-click to reset.";
  } else if (isNestEditWorkspaceActive()) {
    el.textContent = "Drag a source-outline point to reshape this Photo Nest. Use Add point or Delete point for outline detail.";
  } else if (state.draft?.kind === "nest" || state.design?.layout?.features?.[state.selected]?.kind === "nest") {
    el.textContent = "Drag the whole repeated Photo Nest group to move it; use the square to resize and circle to rotate.";
  } else {
    el.textContent = "Drag a part to move it; use the square to resize and circle to rotate.";
  }
}

// Advisory only: a user-changed wall that differs from known ordinary bins already
// in this Space. Never blocks the change and stays silent if the read fails.
async function maybeWarnSpaceWallMismatch(newWall) {
  if (state.folderMode !== "space" || !state.output) return;
  const spaceKey = () => state.activeSpaceId || state.output;
  const spaceAtStart = spaceKey();
  try {
    let bins;
    if (typeof DL !== "undefined" && DL.loaded && DL.output === DL.folder()) {
      bins = DL.bins;
    } else {
      const data = await DL.inventoryCall("/api/drawer/load", {}, { write: false });
      bins = data.bins;
    }
    // Bins are compared with the OTHER bins only: the bin being edited still
    // holds its previous wall in its saved row, and a container's own wall
    // (Storage Box, Storage Drawers) is never a bin thickness.
    const editedId = state.designInventoryId;
    const differs = (bins || []).some(row => {
      if (row?.kind !== "bin") return false;
      if (editedId && row.id === editedId) return false;
      const wall = Number(row.wall);
      return row.wall != null && Number.isFinite(wall) && wall > 0 && Math.abs(wall - newWall) > 1e-6;
    });
    if (!differs) return;
    if (state.folderMode !== "space" || spaceKey() !== spaceAtStart) return;
    if (state.design?.box?.wall !== newWall) return;
    toast(
      "This Space already has bins with a different wall thickness. Connectors only fit bins with the same wall thickness. You can keep this thickness, but do not use one connector across different wall thicknesses.",
      false, 9000,
    );
  } catch (_error) {
    // Advisory warning only.
  }
}

// Fix 1137: undo/redo is gone. This single pre-edit snapshot is NOT history -
// it lets the modifier-conflict guard compare the committed design against
// the design before the first edit of the burst.
let pendingPreEditDesign = null;
let pendingWallMismatchCheck = false;
const applyChangedDesign = debounce(() => {
  const checkWall = pendingWallMismatchCheck;
  pendingWallMismatchCheck = false;
  if (state.designMutationBusy) {
    pendingPreEditDesign = null;
    return;
  }
  const previousDesign = pendingPreEditDesign || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  pendingPreEditDesign = null;
  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
    state.pendingStackableBaseBefore = null;
    return;
  }

  if (state.pendingStackableBaseBefore !== null && state.pendingStackableBaseBefore !== undefined) {
    if (state.design.box.stack?.mode === "direct" && state.design.box.base_thickness > state.pendingStackableBaseBefore)
      showStackableBaseChange(state.design.box.base_thickness);
    state.pendingStackableBaseBefore = null;
  }
  if (checkWall) maybeWarnSpaceWallMismatch(state.design.box.wall);
  // Fix 1137: undo is gone, but the starter-preview lifecycle is not. A real
  // design change committed before the first preview must clear the pending
  // flag, or pre-preview edits silently never persist.
  if (previousDesign && JSON.stringify(previousDesign) !== JSON.stringify(state.design)) {
    state.spaceStarterPreviewPending = false;
  }
  // Re-fit contents-driven drafts after the bin changes. Arbitrarily sized
  // parts keep the size the user chose; if the bin was made too small, the
  // automatic grow pass below restores enough room instead of trimming them.
  reflowDraftToBin(state.draft);
  // Rebuild the selected part first. Divider and Scoop footprints are
  // derived from the bin, so previewing the resized bin before that rebuild
  // can briefly validate their old footprint and show a false fit error.
  // refreshDraft() finishes by refreshing the whole preview.
  if (state.draft) refreshDraft();
  else if (previewShowsCurrentGeometry() && !state.binResizePending) {
    // Story 2773: a name-only edit changes no shape; keep the preview.
    keepPreviewForLabelOnlyChange();
  } else refreshPreview();
  if (state.binResizePending &&
      (state.draft || state.design.layout.features.length)) {
    enforceBinMinimumSoon();
  }
  state.binResizePending = false;
  state.binFootprintResizePending = false;
}, 280);

function cancelChangedDesignDebounce() {
  applyChangedDesign.cancel();
  pendingWallMismatchCheck = false;
}

// Re-evaluate contents-driven parts after the bin itself changes size. Plain
// sized blocks are deliberately untouched: their footprint is user intent,
// so a too-small bin must grow around them rather than cutting them down.
function reflowDraftToBin(one) {
  if (!one) return;
  if (one.kind === "cradle") return sizeCradleToItem(one);
  if (one.kind === "bore") return sizeBoreToGrid(one);
  if (one.kind === "post") return sizePostToRow(one);
  if (one.kind === "slot") return sizeSlotToBank(one);
}

function showStackableBaseChange(value) {
  const note = $("#stackable-base-change-note");
  note.textContent = `Base thickness changed to ${fmt(value)} mm — changed for you. A stackable bin sits directly on the bin below, with no lid in between, so its base has to be this thick to carry the stack.`;
  note.dataset.choice = "true";
  note.hidden = false;
}

function changedDesign(previousDesign = null) {
  noteLidThicknessEdit();
  // Width/length keyboard, wheel and blur handlers update state immediately so
  // their inline inside-dimension readout stays correct. Preserve the snapshot
  // from before the first such edit until the debounced commit lands, so the
  // modifier-conflict guard can compare against the pre-edit design.
  if (previousDesign && pendingPreEditDesign === null) {
    pendingPreEditDesign = clone(previousDesign);
  }
  applyChangedDesign();
}

function markBinAxisManual(_axis) {
  state.binResizePending = true;
  state.binFootprintResizePending = true;
}

let pendingNudgeDraft = null;
const commitNudge = debounce(async request => {
  if (request !== state.draftRequest || state.selected === null || !state.draft) return;
  const index = state.selected;
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const ownsRequest = () => request === state.draftRequest
    && state.selected === index
    && state.draft === draft
    && JSON.stringify(draft) === snapshot;
  try {
    const result = await api("/api/feature/apply", {
      design: state.design,
      feature: draft,
      index,
    });
    if (!ownsRequest()) return;
    state.design = result.design;
    pendingNudgeDraft = null;
    if (request !== state.draftRequest) return;
    state.selected = result.selected;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshDraft();
    if (request !== state.draftRequest) return;
    renderLayout2D();
  } catch (error) {
    if (!ownsRequest()) return;
    const restoreDraft = pendingNudgeDraft;
    pendingNudgeDraft = null;
    toast(error.message, true, 5000);
    if (restoreDraft || state.design?.layout?.features?.[index]) {
      state.draft = clone(restoreDraft || state.design.layout.features[index]);
      renderDraftFields();
      refreshDraft();
      renderLayout2D();
    }
  }
}, 200);

// The largest straight-sided rectangle that fits a bin's wavy cavity - the
// same number the engine's BoxSpec.usable_inside returns, recomputed here so
// the cradle auto-sizer never has to wait on a preview round-trip to know how
// much floor it has. Browser designs are always fused/removable (no cartridge)
// and the flat-inside band does not touch this rectangle, so the plain formula
// is exact.
function binInsideExtent(box) {
  const rules = state.catalog?.wall_rules || {};
  const wallDepth = number(box.wall, rules.default_mm ?? 0.8)
    * (rules.wall_depth_factor ?? 1.181);
  const trim = (rules.mating_gap_mm ?? 0.25)
    + 2 * wallDepth
    + 2 * (rules.wave_amplitude_mm ?? 0.4);
  return [Math.max(1, number(box.x) - trim), Math.max(1, number(box.y) - trim)];
}

const binSizeSelector = axis => axis === "x" ? "#x-size" : axis === "y" ? "#y-size" : "#z";

// Bind only when opening/replacing a design. Routine refreshes and server
// auto-sizing keep the person's text, even when the effective size changes.
function bindBinSizeFields(design = state.design) {
  state.binSizeFields = {};
  for (const axis of ["x", "y", "z"]) {
    const raw = String(design.box[axis]);
    state.binSizeFields[axis] = { raw };
    const input = $(binSizeSelector(axis));
    if (input) input.value = raw;
  }
  syncBinPrinterWarning();
}

function readBinSizeField(axis) {
  if (!state.binSizeFields) bindBinSizeFields();
  const input = $(binSizeSelector(axis));
  const previous = state.binSizeFields[axis];
  // An unchanged request must not undo a later automatic size adjustment.
  const requested = !previous.edited && input.value === previous.raw ? state.design.box[axis] : input.value;
  previous.raw = input.value;
  previous.edited = false;
  return normalizeBinDimension(axis, requested, state.design.box[axis]);
}

// Ordinary bin print bounds use the entered dimensions; the editor has no
// resolved separate printed-bin size. Match component_fit's two bed rotations.
function binPrinterWarning() {
  if (!state.design?.box || !window.PrinterProfile) return "";
  const sizes = ["x", "y", "z"].map(axis => {
    const input = $(binSizeSelector(axis));
    const raw = input?.value.trim();
    return raw && Number.isFinite(Number(raw)) && Number(raw) > 0 ? Number(raw) : Number(state.design.box[axis]);
  });
  const [x, y, z] = sizes;
  const printer = PrinterProfile.current();
  const epsilon = 1e-6;
  const bedFits = (x <= printer.x_mm + epsilon && y <= printer.y_mm + epsilon) ||
    (y <= printer.x_mm + epsilon && x <= printer.y_mm + epsilon);
  const warnings = [];
  if (!bedFits) warnings.push(`This bin is ${fmt(x)} x ${fmt(y)} mm; the printer bed in Printer Settings is ${fmt(printer.x_mm)} x ${fmt(printer.y_mm)} mm.`);
  if (z > printer.z_mm + epsilon) warnings.push(`This bin is ${fmt(z)} mm tall; the printer in Printer Settings is ${fmt(printer.z_mm)} mm tall.`);
  return warnings.join(" ");
}

function syncBinPrinterWarning() {
  const node = $("#bin-printer-warning");
  if (!node) return;
  const message = binPrinterWarning();
  node.textContent = message;
  node.hidden = !message;
}

function formatDimField(axis) {
  if (!state.binSizeFields) bindBinSizeFields();
  const input = $(binSizeSelector(axis));
  if (!input) return;
  const raw = input.value.trim();
  const requested = Number(raw);
  const valid = raw !== "" && Number.isFinite(requested) && requested > 0;
  const used = normalizeBinDimension(axis,
    !state.binSizeFields[axis].edited && input.value === state.binSizeFields[axis].raw ? state.design.box[axis] : requested,
    state.design.box[axis]);
  const unit = state.catalog?.base_unit || 7;
  const max = Math.floor((state.catalog?.max_box_size || 350) / unit) * unit;
  const notes = [];
  if (!valid) notes.push("Enter a size in mm greater than zero.");
  if (axis !== "z" && requested > max) notes.push(`A bin can be at most ${fmt(max)} mm on this side.`);
  if (valid && Math.abs(requested - used) > 1e-6) {
    notes.push(`Uses ${fmt(used)} mm${axis === "z" ? "" : ` (${fmt(used / unit)} units)`}.`);
  }
  let note = document.getElementById(`${input.id}-size-note`);
  if (!note) {
    note = document.createElement("small");
    note.id = `${input.id}-size-note`;
    note.className = "field-help";
    note.setAttribute("aria-live", "polite");
    input.after(note);
    input.setAttribute("aria-describedby", [input.getAttribute("aria-describedby"), note.id].filter(Boolean).join(" "));
  }
  note.textContent = notes.join(" ");
  note.hidden = !notes.length;
  input.toggleAttribute("aria-invalid", !valid || (axis !== "z" && requested > max));
  syncBinPrinterWarning();
}

function formatHeightField() { formatDimField("z"); }


function wireSidebar() {
  const shell = $("#app-shell");
  const resizer = $("#sidebar-resizer");
  let drag = null;
  try {
    const savedWidth = Number(localStorage.getItem("wavefinity-sidebar-width"));
    if (Number.isFinite(savedWidth) && savedWidth >= 420) {
      shell.style.setProperty("--sidebar-width", `${savedWidth}px`);
    }
    localStorage.removeItem("wavefinity-sidebar-collapsed");
  } catch (_error) {}
  resizer.addEventListener("pointerdown", event => {
    drag = { startX: event.clientX, width: $(".controls").getBoundingClientRect().width };
    resizer.classList.add("dragging");
    resizer.setPointerCapture(event.pointerId);
  });
  resizer.addEventListener("pointermove", event => {
    if (!drag) return;
    const width = Math.max(420, Math.min(window.innerWidth - 440, drag.width + event.clientX - drag.startX));
    shell.style.setProperty("--sidebar-width", `${width}px`);
  });
  resizer.addEventListener("pointerup", event => {
    if (!drag) return;
    const width = Math.round($(".controls").getBoundingClientRect().width);
    drag = null;
    resizer.classList.remove("dragging");
    if (resizer.hasPointerCapture(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    try { localStorage.setItem("wavefinity-sidebar-width", String(width)); } catch (_error) { toast("The sidebar width could not be remembered in this browser.", true); }
  });
  resizer.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const current = $(".controls").getBoundingClientRect().width;
    const width = Math.max(420, Math.min(window.innerWidth - 440, current + (event.key === "ArrowRight" ? 24 : -24)));
    shell.style.setProperty("--sidebar-width", `${width}px`);
    try { localStorage.setItem("wavefinity-sidebar-width", String(Math.round(width))); } catch (_error) { toast("The sidebar width could not be remembered in this browser.", true); }
  });
}

function setCameraView(view) {
  Object.assign(state.camera, CAMERA_VIEWS[view] || CAMERA_VIEWS.reset);
  $$('[data-camera-view]').forEach(button => button.classList.toggle("active", button.dataset.cameraView === view && view !== "reset"));
  renderPreview3D();
  updateDividerEditBreadcrumb();
}

// A click-to-spin alternative to dragging: 15 degrees a step, or 2 with
// shift held for lining something up precisely.
function rotateCameraStep(direction, fine) {
  const step = fine ? 2 : 15;
  const camera = state.camera;
  if (direction === "left") camera.yaw -= step;
  else if (direction === "right") camera.yaw += step;
  else if (direction === "up") camera.elevation = Math.max(-89, Math.min(89, camera.elevation + step));
  else if (direction === "down") camera.elevation = Math.max(-89, Math.min(89, camera.elevation - step));
  $$('[data-camera-view]').forEach(button => button.classList.remove("active"));
  renderPreview3D();
  updateDividerEditBreadcrumb();
}

// Bin/Interior/Lid/Xray each toggle their own state only - see the state.binVisible
// comment. Bin, Interior and Lid are ON by default, so their button shows the light
// red "off" treatment only when turned off; Xray is OFF by default, so its
// button shows the active/blue treatment only when turned on.
const PREVIEW_TOGGLE_KEYS = { bin: "binVisible", interior: "interiorVisible", lid: "lidVisible", xray: "xrayOn" };
function setPreviewToggle(name, on) {
  const key = PREVIEW_TOGGLE_KEYS[name];
  if (!key) return;
  state[key] = on;
  const button = $(`[data-camera-toggle="${name}"]`);
  if (button) {
    button.setAttribute("aria-pressed", String(on));
    const offIsNormal = name === "xray";
    button.classList.toggle("mode-toggle-off", !offIsNormal && !on);
    button.classList.toggle("active", offIsNormal && on);
  }
  renderPreview3D();
}

function wireCameraControls() {
  $$('[data-camera-view]').forEach(button => button.addEventListener("click", () => setCameraView(button.dataset.cameraView)));
  $$('[data-camera-toggle]').forEach(button => button.addEventListener("click", () => {
    const name = button.dataset.cameraToggle;
    const key = PREVIEW_TOGGLE_KEYS[name];
    setPreviewToggle(name, !state[key]);
  }));
  $$('[data-camera-zoom]').forEach(button => button.addEventListener("click", () => {
    state.camera.zoom = Math.max(.35, Math.min(4, state.camera.zoom * (button.dataset.cameraZoom === "in" ? 1.2 : 1 / 1.2)));
    renderPreview3D();
  }));
  $$('[data-camera-rotate]').forEach(button => button.addEventListener("click", event => {
    rotateCameraStep(button.dataset.cameraRotate, event.shiftKey);
  }));
}

function setLayoutOrientation(orientation) {
  state.layoutOrientation = orientation;
  $$('[data-layout-orientation]').forEach(button => {
    const active = button.dataset.layoutOrientation === orientation;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderLayout2D();
}

function eligibleGridDividerIndexes() {
  if (!state.design?.layout?.features) return [];
  return state.design.layout.features
    .map((feature, index) => dividerEligibleClient(
      index === state.selected && state.draft?.kind === "divider" ? state.draft : feature,
    ) ? index : null)
    .filter(Number.isInteger);
}

function updateDividerEditBreadcrumb() {
  const button = $("#divider-edit-breadcrumb");
  if (!button) return;
  const in3d = $('.canvas-wrap[data-canvas="3d"]')?.classList.contains("active");
  button.hidden = !in3d || eligibleGridDividerIndexes().length === 0;
  const top = isTopCameraView();
  button.textContent = top ? "Click individual segments to remove" : "Switch to Top to remove individual dividers";
  button.classList.toggle("divider-edit-note-static", top);
}

// A bin's Top view: camera straight down (flat plan, no tilt).
function isTopCameraView(camera = state.camera) {
  return camera.elevation >= 90;
}

// The note is a shortcut to Top when it asks for Top; in Top it is just a hint.
function openDividerSegmentEditor() {
  if (!isTopCameraView()) setCameraView("top");
}

// The Space/Drawer canvas has no matching .view-tab (there is no third tab -
// Space is reached only programmatically), so it must not be gated on one.
// A view-only switch never touches remembered design/Space state; it only
// remembers the last Design 2D/3D view actually used (Fix 078).
function activatePreviewView(view) {
  // Fix 103 (R5): while a structural target owns Design, its 2D view is the
  // Space canvas in view-only mode (no second 2D owner).
  if (view === "2d" && typeof structuralDesignActive === "function" && structuralDesignActive()) { activateStructural2D(); return; }
  if (view === "drawer" && state.folderMode !== "space") {
    if (typeof SP !== "undefined") SP.offerSpacePlanning();
    return;
  }
  if (view === "drawer" && state.runtime.hosted && !state.browserFolder?.handle) {
    if (typeof SP !== "undefined") SP.showFolderAccessNeeded();
    return;
  }
  const canvasWrap = $(`.canvas-wrap[data-canvas="${view}"]`);
  if (!canvasWrap) return;
  if (view === "drawer") {
    $$(".canvas-wrap").forEach(wrap => wrap.classList.toggle("active", wrap === canvasWrap));
  } else {
    const tab = $(`.view-tab[data-view="${view}"]`);
    if (!tab) return;
    $$(".view-tab").forEach(other => {
      const active = other === tab;
      other.classList.toggle("active", active);
      other.setAttribute("aria-selected", String(active));
      other.tabIndex = active ? 0 : -1;
    });
    $$(".canvas-wrap").forEach(wrap => wrap.classList.toggle("active", wrap === canvasWrap));
    state.lastDesignView = view;
  }
  canvasWrap.classList.remove("view-enter");
  void canvasWrap.offsetWidth;
  canvasWrap.classList.add("view-enter");
  updatePreviewHelp(view);
  updateDividerEditBreadcrumb();
  if (view === "2d") updateNudgeUI();
  requestAnimationFrame(() => {
    if (view === "3d") renderPreview3D();
    else if (view === "2d") renderLayout2D();
    else if (typeof DV !== "undefined" && DV.render) DV.render();
  });
}

// The Design 2D/3D view the user last actually chose, for transitions that
// merely re-enter Design without themselves choosing a specific view.
function preferredDesignView() {
  return state.lastDesignView === "2d" ? "2d" : "3d";
}

function wireControls() {
  PrinterProfile.subscribe(syncBinPrinterWarning);
  syncBinPrinterWarning();
  wireSidebar();
  wireCameraControls();
  wireNest2DControls();
  $$('[data-layout-orientation]').forEach(button =>
    button.addEventListener("click", () => setLayoutOrientation(button.dataset.layoutOrientation)));
  $("#divider-edit-breadcrumb")?.addEventListener("click", openDividerSegmentEditor);
  $("#active-option-save")?.addEventListener("click", saveCurrentPart);
  $("#active-option-delete")?.addEventListener("click", async event => {
    const button = event.currentTarget;
    // Fix 1137: undo is gone, so a misclick on Delete (adjacent to Done, no
    // confirmation) would destroy work irrecoverably. Confirm once here, at
    // the active-option click choke point, so all three delete branches
    // below are covered and none can bypass the prompt.
    const deleteLabel = $("#active-option-title")?.textContent?.trim()
      || state.draft?.title || state.draft?.kind || "this part";
    if (!confirm(`Delete ${deleteLabel}? This cannot be undone.`)) return;
    if (button.dataset.kind) { await removeModifier(button.dataset.kind); return; }
    if (button.dataset.index !== undefined) { await deleteSupportAt(Number(button.dataset.index)); return; }
    await deleteCurrentPart();
  });
  $$("button.section-heading").forEach(button => button.addEventListener("click", () => {
    const section = button.closest(".control-section");
    section.classList.toggle("open");
    button.setAttribute("aria-expanded", String(section.classList.contains("open")));
  }));

  ["#x-size", "#y-size", "#z", "#base-thickness", "#wall-thickness", "#part-name"]
    .forEach(selector => $(selector).addEventListener("input", () => {
      if (["#x-size", "#y-size", "#z"].includes(selector)) {
        const axis = selector === "#x-size" ? "x" : selector === "#y-size" ? "y" : "z";
        if (!state.binSizeFields) bindBinSizeFields();
        state.binSizeFields[axis].edited = true;
        formatDimField(axis);
      }
      if (selector === "#x-size" || selector === "#y-size") {
        state.starterHintActive = false;
        syncStarterSizeHint();
      }
      if (selector === "#wall-thickness") {
        const select = $(selector);
        select.dataset.customValue = select.value;
        const legacyOption = [...select.options].find(option =>
          option.textContent.endsWith("— Existing")
        );
        if (legacyOption && legacyOption.value !== select.value) {
          legacyOption.remove();
          delete select.dataset.choices;
        }
        state.binResizePending = true;
        pendingWallMismatchCheck = true;
        syncWallControls();
      }
      if (selector === "#base-thickness") {
        $(selector).dataset.customValue = $(selector).value;
        state.binResizePending = true;
        syncBaseControls();
      }
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign();
    }));
  ["#surface-base-mode", "#surface-base-custom", "#surface-lightweight-base", "#surface-object-height"]
    .forEach(selector => $(selector)?.addEventListener(selector === "#surface-base-mode" ? "change" : "input", () => {
      if (!isSurfaceBinDesign()) return;
      const resolved = resolveSurfaceBase(state.design, { fromForm: true });
      if (resolved === false) return;
      if (selector === "#surface-base-mode" || selector === "#surface-base-custom") {
        formatHeightField();
        state.binResizePending = true;
      }
      syncSurfaceControls();
      changedDesign();
    }));
  $("#lift-grabber-size").addEventListener("change", () => {
    syncLiftGrabberControls();
    if ($("#lift-grabber-size").value !== "no") promoteWallForLiftGrabbers();
    changedDesign();
  });
  $("#lift-grabber-location").addEventListener("change", changedDesign);

  const edgeMountChangeIds = [
    "#edge-mount-side",
    "#edge-mount-label-length-mode",
    "#edge-mount-label-style", "#edge-mount-label-flip",
    "#edge-mount-standoff-ribs-enabled", "#edge-mount-standoff-rib-count-mode",
    "#edge-mount-hole-count", "#edge-mount-hole-orientation", "#edge-mount-access-diameter",
    "#edge-mount-spacing-mode",
  ];
  edgeMountChangeIds.forEach(selector => $(selector)?.addEventListener("change", () => {
    syncEdgeMountEditorVisibility();
    changedDesign();
  }));
  // Fix 058 Correction 1, C1.4B/E: the Label selector's None state and the
  // Screw Mounting checkbox's off state together replace the former pair of
  // top-level enable checkboxes. An Edge Mount already active in the saved
  // design must still keep at least one of the two on while its editor is
  // open - switching both off here reverts the just-made change and points
  // the user at Delete instead. A brand-new, not-yet-saved Edge Mount may
  // freely sit at Label=None + Screw Mounting off while the editor is open.
  $("#edge-mount-label-mode")?.addEventListener("change", event => {
    const holesEnabled = Boolean($("#edge-mount-holes-enabled")?.checked);
    if (state.modifierEditing === "edge_mount" && edgeMountActive() &&
        event.currentTarget.value === "none" && !holesEnabled) {
      event.currentTarget.value = edgeMountLabelMode(state.design.box.edge_mount);
      toast("Edge Mount needs Label or Screw Mounting. Use Delete to remove Edge Mount.", true, 6000);
      return;
    }
    syncEdgeMountEditorVisibility();
    changedDesign();
  });
  $("#edge-mount-holes-enabled")?.addEventListener("change", event => {
    const labelMode = $("#edge-mount-label-mode")?.value || "none";
    if (state.modifierEditing === "edge_mount" && edgeMountActive() &&
        labelMode === "none" && !event.currentTarget.checked) {
      event.currentTarget.checked = true;
      toast("Edge Mount needs Label or Screw Mounting. Use Delete to remove Edge Mount.", true, 6000);
      return;
    }
    syncEdgeMountEditorVisibility();
    changedDesign();
  });
  const edgeMountInputIds = [
    "#edge-mount-label-text", "#edge-mount-label-projection-mm", "#edge-mount-label-thickness-mm",
    "#edge-mount-label-depth", "#edge-mount-standoff-rib-count", "#edge-mount-screw-diameter", "#edge-mount-access-diameter",
    "#edge-mount-top-offset", "#edge-mount-spacing-mm",
  ];
  edgeMountInputIds.forEach(selector => $(selector)?.addEventListener("input", () => {
    syncEdgeMountEditorVisibility();
    if (selector === "#edge-mount-screw-diameter") syncEdgeMountAutoAccessFromForm();
    changedDesign();
  }));

  ["#pegboard-cleat-x", "#pegboard-cleat-y"].forEach(selector => $(selector)?.addEventListener("change", () => {
    readPegboardMountForm(state.design);
    syncPegboardMountForm();
    changedDesign();
  }));
  ["#bin-stackable", "#lid-choice", "#lid-thickness", "#lid-fit", "#lid-alignment", "#lid-handle-type", "#lid-handle-size",
   "#lid-handle-position", "#lid-label-orientation", "#lid-label-style", "#lid-label-size", "#lid-label-depth"]
    .forEach(selector => $(selector).addEventListener("change", () => {
      const previous = clone(state.design);
      readStackForm(state.design);
      normalizeStackSettings(state.design);
      if (selector === "#lid-choice") {
        const note = $("#lid-wall-change-note");
        const choice = $("#lid-choice").value;
        note.hidden = true;
        if (state.design.box.wall > previous.box.wall) {
          note.textContent = `${choice === "hinged" ? "Hinged lids" : "Lids"} need ${fmt(state.design.box.wall)} mm walls ? changed for you.`;
          note.dataset.choice = choice;
          note.hidden = false;
        }
      }
      if (selector === "#bin-stackable") {
        state.pendingStackableBaseBefore = $("#bin-stackable").value === "true" ? previous.box.base_thickness : null;
        if (state.pendingStackableBaseBefore !== null && state.design.box.base_thickness > state.pendingStackableBaseBefore)
          showStackableBaseChange(state.design.box.base_thickness);
      }
      clampSideOpeningTopForLid(state.design, true);
      syncLidForm();
      syncSideOpeningControls();
      populateWallChoices(state.design.box);
      populateBaseChoices(state.design.box);
      changedDesign(previous);
    }));
  $("#lid-label-text").addEventListener("input", () => {
    const previous = clone(state.design);
    state.lidLabelEnabled = Boolean($("#lid-label-text").value.trim());
    readStackForm(state.design);
    $("#lid-label-details").hidden = !state.lidLabelEnabled;
    $("#lid-label-orientation-row").hidden = !state.lidLabelEnabled;
    $("#lid-label-style-row").hidden = !state.lidLabelEnabled;
    $("#lid-label-size-row").hidden = !state.lidLabelEnabled;
    $("#lid-label-depth-row").hidden = !state.lidLabelEnabled;
    renderLidLabelEditor();
    seedPartNameFromLabel($("#lid-label-text").value);
    changedDesign(previous);
  });
  ["#side-opening-shape", "#side-opening-size"]
    .forEach(selector => $(selector)?.addEventListener("change", () => {
      const previous = clone(state.design);
      sideOpeningAdjustmentNote = "";
      readSideOpeningForm(state.design);
      syncSideOpeningControls();
      changedDesign(previous);
    }));
  [["#side-opening-lower", "lower"], ["#side-opening-upper", "upper"]].forEach(([selector, changed]) =>
    $(selector)?.addEventListener("input", () => {
      const previous = clone(state.design);
      const pair = normalizeSideOpeningPair(state.design, sideOpeningPairFromControls(), changed);
      $("#side-opening-lower").value = String(pair.lower);
      $("#side-opening-upper").value = String(pair.upper);
      readSideOpeningForm(state.design, changed);
      syncSideOpeningControls();
      changedDesign(previous);
    }));
  SIDE_OPENING_SIDE_IDS.forEach(side => {
    $(`#side-opening-${side}`)?.addEventListener("change", event => {
      const checkbox = event.currentTarget;
      const wasActive = !checkbox.checked;
      const selected = SIDE_OPENING_SIDE_IDS.filter(
        one => $(`#side-opening-${one}`)?.checked === true
      );
      if (wasActive && selected.length === 0) {
        checkbox.checked = true;
        toast("Side Openings need at least one side.", true, 4000);
        return;
      }
      const previous = clone(state.design);
      readSideOpeningForm(state.design);
      syncSideOpeningControls();
      changedDesign(previous);
    });
  });
  ["#x-size", "#y-size"].forEach(selector => {
    const axis = selector === "#x-size" ? "x" : "y";
    const input = $(selector);
    input.addEventListener("input", () => markBinAxisManual(axis));
    input.addEventListener("focus", () => {
      input.select();
    });
    input.addEventListener("blur", () => {
      const previousDesign = clone(state.design);
      const snapped = readBinSizeField(axis);
      const prev = state.design.box[axis];
      if (snapped !== prev) markBinAxisManual(axis);
      state.design.box[axis] = snapped;
      formatDimField(axis);
      if (snapped !== prev) {
        flashField(input);
        state.canGenerate = false;
        updateGenerateAvailability();
        changedDesign(previousDesign);
      }
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        input.blur();
      } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        const previousDesign = clone(state.design);
        const unit = state.catalog.base_unit;
        const current = number(input.value, state.design.box[axis]);
        const delta = event.key === "ArrowUp" ? unit : -unit;
        const next = current + delta;
        markBinAxisManual(axis);
        input.value = String(next);
        input.select();
        state.design.box[axis] = readBinSizeField(axis);
        formatDimField(axis);
        state.canGenerate = false;
        updateGenerateAvailability();
        changedDesign(previousDesign);
      }
    });
    input.addEventListener("wheel", event => {
      event.preventDefault();
      const previousDesign = clone(state.design);
      const unit = state.catalog.base_unit;
      const current = number(input.value, state.design.box[axis]);
      const delta = event.deltaY < 0 ? unit : -unit;
      const next = current + delta;
      if (next === current && delta < 0) return;
      markBinAxisManual(axis);
      input.value = String(next);
      state.design.box[axis] = readBinSizeField(axis);
      if (document.activeElement === input) {
        input.select();
      }
      formatDimField(axis);
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }, { passive: false });
  });
  const heightInput = $("#z");
  heightInput.addEventListener("focus", () => {
    heightInput.select();
  });
  heightInput.addEventListener("blur", () => {
    const previousDesign = clone(state.design);
    const next = readBinSizeField("z");
    const changed = next !== state.design.box.z;
    state.design.box.z = next;
    formatHeightField();
    if (changed) {
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }
    syncContainerInsideHint();
  });
  ["#output-folder", "#connector-tolerance", "#connector-length",
    "#connector-arm-thickness", "#connector-bin-a-height", "#connector-bin-b-height"]
    .forEach(selector => $(selector)?.addEventListener("change", () => {
      applyPendingLiveFormWithModifierConflictGuard();
    }));
  ["#connector-bin-a-height", "#connector-bin-b-height"].forEach(selector => {
    $(selector)?.addEventListener("input", () => {
      autoAdjustConnectorFields();
      applyPendingLiveFormWithModifierConflictGuard();
    });
  });
  ["#connector-tolerance", "#connector-length", "#connector-arm-thickness",
    "#connector-bin-a-height", "#connector-bin-b-height", "#connector-height-mode"]
    .forEach(selector => $(selector)?.addEventListener("change", () => setTimeout(persistConnectorSettings, 0)));
  $("#connector-height-mode").addEventListener("change", () => {
    if ($("#connector-height-mode").value === "different") {
      $("#connector-bin-a-height").value = fmt(state.design.box.z);
      if (!Number.isFinite(number($("#connector-bin-b-height").value, NaN))) {
        $("#connector-bin-b-height").value = fmt(state.design.box.z);
      }
    }
    syncConnectorHeightControls();
    if (!applyPendingLiveFormWithModifierConflictGuard()) return;
    renderConnectorReadout();
  });
  // The folder icon covers both picking a save folder and Space planning -
  // SP.open() already offers recent/new folders before it gets to Space setup.
  const outputFolderEl = $("#output-folder");
  if (outputFolderEl) {
    outputFolderEl.addEventListener("click", () => SP.open());
    outputFolderEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        SP.open();
      }
    });
  }
  $('label[for="output-folder"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    SP.open();
  });
  $("#output-folder-picker")?.addEventListener("click", () => SP.open());

  const viewTabs = $$(".view-tab");
  const selectPreviewTab = view => activatePreviewView(view);
  viewTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectPreviewTab(tab.dataset.view));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0
        : event.key === "End" ? viewTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      selectPreviewTab(viewTabs[targetIndex].dataset.view);
      viewTabs[targetIndex].focus();
    });
  });
  activatePreviewView((viewTabs.find(tab => tab.classList.contains("active")) || viewTabs[0]).dataset.view);

  // Editing a part: "Save Part" finalises it and returns to the 10-part
  // palette; "Delete Part" removes the part being edited and does the same.
  // New Bin/Duplicate/Save/Load live at the bottom of the Designer.
  $("#designer-new-bin").addEventListener("click", () => designerNewBin());
  $("#designer-duplicate").addEventListener("click", designerDuplicate);

  aiWireHelp();
  $("#designer-save-file").addEventListener("click", saveDesign);
  $("#designer-open-file").addEventListener("change", openDesign);
  window.addEventListener("beforeunload", event => {
    const layoutUnsaved = typeof DL !== "undefined" && DL.active
      && (DL.dirty || DL.saving || Boolean(DL.savePromise) || DL.saveState === "error");
    const structuralUnsaved = typeof structuralEditorDirty === "function" && structuralEditorDirty();
    if (designHasChanges() || layoutUnsaved || structuralUnsaved) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  $("#update-banner-reload").addEventListener("click", () => location.reload(true));
  wireGenerationDialog();
  $("#print-dialog-slicer-picker").addEventListener("click", event => browseSlicer(event.currentTarget));
  wireSceneInteraction($("#preview-3d"), state.camera, renderPreview3D);
  wireSupportLayoutDialog();
  wireLayoutInteraction();
  new ResizeObserver(() => renderPreview3D()).observe($("#preview-3d").parentElement);
  new ResizeObserver(() => renderLayout2D()).observe($("#preview-2d").parentElement);
}
