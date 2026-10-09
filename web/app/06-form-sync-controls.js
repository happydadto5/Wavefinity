"use strict";

function updateDesignFromForm() {
  const design = state.design;
  const prevBoxX = design.box.x;
  if (isSurfaceBinDesign(design)) resolveSurfaceBase(design, { fromForm: true });
  const prevBoxY = design.box.y;
  const newBoxX = normalizeBinDimension("x", $("#x-size").value, design.box.x);
  const newBoxY = normalizeBinDimension("y", $("#y-size").value, design.box.y);
  design.box.x = newBoxX;
  design.box.y = newBoxY;
  const boxFootprintChanged = design.box.x !== prevBoxX || design.box.y !== prevBoxY;
  // Width/Length handlers update state before this debounced read, so the
  // dedicated pending flag detects a resize even when prevBoxX/Y already
  // contain the new values.
  const sideOpeningResizeChanged = state.binFootprintResizePending || boxFootprintChanged;
  const prevBoxZ = design.box.z;
  design.box.z = normalizeBinDimension("z", $("#z").value, design.box.z);
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
    : (currentStackMode === "none" && !hasOrdinaryLid
        ? wallRules.min_mm ?? 0.2
        : stackValues.minWall);
  const maxWall = wallRules.max_mm ?? 2.4;
  const wallChoice = $("#wall-thickness").value;
  design.box.standard_walls = !b4bOn && currentStackMode === "none" && !hasOrdinaryLid && wallChoice === "standard";
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
    const differs = (bins || []).some(row => {
      if (row?.kind !== "bin") return false;
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

let pendingDesignHistory = null;
let pendingWallMismatchCheck = false;
const applyChangedDesign = debounce(() => {
  const checkWall = pendingWallMismatchCheck;
  pendingWallMismatchCheck = false;
  if (state.designMutationBusy) {
    pendingDesignHistory = null;
    return;
  }
  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  pendingDesignHistory = null;
  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
    return;
  }

  if (checkWall) maybeWarnSpaceWallMismatch(state.design.box.wall);
  noteCommittedDesignChange(previousDesign);
  // Re-fit contents-driven drafts after the bin changes. Arbitrarily sized
  // parts keep the size the user chose; if the bin was made too small, the
  // automatic grow pass below restores enough room instead of trimming them.
  reflowDraftToBin(state.draft);
  // Rebuild the selected part first. Divider and Curved Scoop footprints are
  // derived from the bin, so previewing the resized bin before that rebuild
  // can briefly validate their old footprint and show a false fit error.
  // refreshDraft() finishes by refreshing the whole preview.
  if (state.draft) refreshDraft();
  else refreshPreview();
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

function changedDesign(previousDesign = null) {
  noteLidThicknessEdit();
  // Width/length keyboard, wheel and blur handlers update state immediately so
  // their inline inside-dimension readout stays correct. Preserve the snapshot
  // from before the first such edit until the debounced commit lands.
  if (previousDesign && pendingDesignHistory === null) {
    pendingDesignHistory = clone(previousDesign);
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
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", {
      design: state.design,
      feature: draft,
      index,
    });
    if (!ownsRequest()) return;
    state.design = result.design;
    pendingNudgeDraft = null;
    noteCommittedDesignChange(previousDesign);
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

function getInsideDimension(axis, val) {
  const key = axis === "x" ? "inside_x" : "inside_y";
  if (state.preview?.dimensions?.[key] != null && state.design?.box?.[axis] === val) {
    return state.preview.dimensions[key];
  }
  const box = state.design?.box || {
    x: val,
    y: val,
    wall: state.catalog?.wall_rules?.default_mm ?? 0.8,
  };
  const tempBox = { ...box, [axis]: val };
  const extents = binInsideExtent(tempBox);
  return Math.floor(axis === "x" ? extents[0] : extents[1]);
}

function formatDimField(axis) {
  const selector = axis === "x" ? "#x-size" : "#y-size";
  const input = $(selector);
  if (!input || document.activeElement === input) return;
  const val = state.design?.box?.[axis];
  if (val == null) return;
  const key = axis === "x" ? "inside_x" : "inside_y";
  const previewCurrent =
    state.previewDesignKey === JSON.stringify(state.design) &&
    state.preview?.dimensions?.[key] != null;
  const inside = previewCurrent ? state.preview.dimensions[key] : null;
  // Blurred state keeps the whole fit story short enough to stay in the field.
  // The unit count is the integer number of whole grid steps, from the
  // authoritative base unit.
  const unit = state.catalog?.base_unit || 8;
  const units = Math.round(val / unit);
  // Fix 081 E: physical mm first, then usable-inside mm, then the spelled-out
  // unit count - never a count glued to a letter like "30X".
  input.value = inside == null
    ? `${fmt(val)} mm (inside updating…) — ${units} unit${units === 1 ? "" : "s"}`
    : `${fmt(val)} mm (${fmt(inside)} mm inside) — ${units} unit${units === 1 ? "" : "s"}`;
}

function formatHeightField() {
  const input = $("#z");
  if (!input || document.activeElement === input) return;
  const val = state.design?.box?.z;
  if (val == null) return;
  input.value = `${fmt(val)} mm`;
}


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
}

// Bin/Interior/Xray each toggle their own state only - see the state.binVisible
// comment. Bin and Interior are ON by default, so their button shows the light
// red "off" treatment only when turned off; Xray is OFF by default, so its
// button shows the active/blue treatment only when turned on.
const PREVIEW_TOGGLE_KEYS = { bin: "binVisible", interior: "interiorVisible", xray: "xrayOn" };
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
}

async function openDividerSegmentEditor() {
  const eligible = eligibleGridDividerIndexes();
  if (!eligible.length) return;
  const index = eligible.includes(state.selected) ? state.selected : eligible[0];
  if (state.selected !== index) await selectedFeature(index);
  if (state.selected !== index || state.draft?.kind !== "divider") return;
  activatePreviewView("2d");
  renderLayout2D();
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
  wireSidebar();
  wireCameraControls();
  wireNest2DControls();
  $$('[data-layout-orientation]').forEach(button =>
    button.addEventListener("click", () => setLayoutOrientation(button.dataset.layoutOrientation)));
  $("#divider-edit-breadcrumb")?.addEventListener("click", openDividerSegmentEditor);
  $("#active-option-save")?.addEventListener("click", saveCurrentPart);
  $("#active-option-delete")?.addEventListener("click", async event => {
    const button = event.currentTarget;
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
      if (selector === "#x-size" || selector === "#y-size") {
        const starterHelp = $("#design-first-size-help");
        if (starterHelp) starterHelp.hidden = true;
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
        $("#z").value = fmt(state.design.box.z);
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
    "#edge-mount-label-length-mode", "#edge-mount-label-projection",
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
  ["#lid-configuration", "#lid-thickness", "#lid-fit", "#lid-handle-type", "#lid-handle-size",
   "#lid-handle-position", "#lid-label-enabled", "#lid-label-orientation", "#lid-label-style",
   "#lid-label-depth"]
    .forEach(selector => $(selector).addEventListener("change", () => {
      const previous = clone(state.design);
      readStackForm(state.design);
      normalizeStackSettings(state.design);
      clampSideOpeningTopForLid(state.design, true);
      syncLidForm();
      syncSideOpeningControls();
      populateWallChoices(state.design.box);
      populateBaseChoices(state.design.box);
      changedDesign(previous);
    }));
  $("#lid-label-text").addEventListener("input", () => {
    const previous = clone(state.design);
    readStackForm(state.design);
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
      input.value = fmt(state.design.box[axis]);
      input.select();
    });
    input.addEventListener("blur", () => {
      const previousDesign = clone(state.design);
      const unit = state.catalog.base_unit;
      const rawVal = number(input.value, state.design.box[axis]);
      const snapped = snapToUnit(rawVal, unit);
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
        const next = snapToUnit(current + delta, unit);
        markBinAxisManual(axis);
        input.value = String(next);
        input.select();
        state.design.box[axis] = next;
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
      const next = snapToUnit(current + delta, unit);
      if (next === current && delta < 0) return;
      markBinAxisManual(axis);
      state.design.box[axis] = next;
      if (document.activeElement === input) {
        input.value = String(next);
        input.select();
      } else {
        formatDimField(axis);
      }
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }, { passive: false });
  });
  const heightInput = $("#z");
  heightInput.addEventListener("focus", () => {
    heightInput.value = fmt(state.design.box.z);
    heightInput.select();
  });
  heightInput.addEventListener("blur", () => {
    const previousDesign = clone(state.design);
    const next = normalizeBinDimension("z", heightInput.value, state.design.box.z);
    const changed = next !== state.design.box.z;
    state.design.box.z = next;
    formatHeightField();
    if (changed) {
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }
  });
  ["#output-folder", "#keep-log", "#connector-tolerance", "#connector-length",
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
  $("#designer-undo")?.addEventListener("click", () => designerUndo());
  $("#designer-redo")?.addEventListener("click", () => designerRedo());
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
  $("#print-with-connectors").addEventListener("click", event => printModel("all", event.currentTarget));
  $("#print-without-connectors").addEventListener("click", event => printModel("bin", event.currentTarget));
  $("#generate-all")?.addEventListener("click", () => generateParts("all"));
  $("#generate-bin")?.addEventListener("click", () => generateParts("bin"));
  $("#generate-connector")?.addEventListener("click", () => generateParts("connector"));
  wireGenerationDialog();
  $("#slicer-picker-button").addEventListener("click", browseSlicer);
  wireSceneInteraction($("#preview-3d"), state.camera, renderPreview3D);
  wireSupportLayoutDialog();
  wireLayoutInteraction();
  new ResizeObserver(() => renderPreview3D()).observe($("#preview-3d").parentElement);
  new ResizeObserver(() => renderLayout2D()).observe($("#preview-2d").parentElement);
}