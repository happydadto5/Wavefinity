"use strict";

function starterItem() {
  return {
    name: "Custom item", profile: "round", clearance: 0.4,
    segments: [{ length: 40, diameter: 6 }],
  };
}

function cancelPendingDraftWork() {
  refreshDraftSoon.cancel();
  commitNudge.cancel();
  pendingNudgeDraft = null;
  state.kindRequest += 1;
  state.fitRequest += 1;
  state.nestTraceRequest += 1;
  state.nestRetraceRequest += 1;
  state.draftRequest += 1;
  invalidatePendingPreview();
}

function resetNestPhotoSession() {
  state.nestOutlineEditing = false;
  state.nestPhoto = null;
  state.nestOriginalImage = null;
  state.nestRectifiedImage = null;
  state.nestSensitivity = 50;
  state.nestCleanup = 50;
  state.nestPhotoOpacity = 45;
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestAcceptedCenterMm = null;
  state.nestTuneStatus = "";
  state.nestTraceResult = null;
  state.nestPaperCorners = null;
  state.nestCornerError = "";
  state.nestCornerBusy = false;
  state.nestCornerTipDismissed = false;
  state.nestOutlineTool = "select";
  state.nestAccessWarningShown = null;
  hideNestCornerMagnifier();
}

// Nothing selected, nothing shown as a live draft - the state on first load
// and after New/Open/a delete/a mode switch with nothing selected. A
// palette button never doubles as "still working on the last shape you
// looked at": if none of them is highlighted, nothing has been added yet.
function clearDraftSelection(resetLocks = true) {
  // Opening, resetting, deleting or changing layout mode starts a new editing
  // context. Invalidate every in-flight draft operation so an old palette
  // response, fit, photo upload, or auto-save cannot alter the new design.
  cancelPendingDraftWork();
  commitReferenceEditSoon.cancel();
  state.referenceEditPending = false;
  resetNestPhotoSession();
  state.draft = null;
  state.draftKind = null;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.draftTouched = false;
  state.edgeMountEditing = false;
  state.modifierEditing = null;
  state.pinnedZone = {};
  if (resetLocks) state.partZoneLocks = {};
  state.selected = null;
  state.nudgeFeedback = null;
  updateNudgeUI();
  $$(".support-choice").forEach(button => button.classList.remove("active"));
  $(".support-editor").hidden = true;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  ["#lid-option", "#inside-handles-option", "#side-openings-option"].forEach(
    selector => { const panel = $(selector); if (panel) panel.hidden = true; },
  );
  $("#draft-status").textContent = "";
  $("#draft-status").classList.remove("error");
  updateDraftStatusColor(null);
  updateInteriorModeVisibility();
  updateSelectionButtons();
  syncNest2DWorkspace();
}

function pickKind(kind) {
  const info = partInfo(kind);
  const isModifier = info?.capabilities?.includes("box_modifier");
  if (!isModifier && state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour)) {
    toast("Photo Nest designs use Duplicate for another group; other interior parts are unavailable.", true, 5000);
    return;
  }
  // Fix 111 R4-3: a new Photo Nest cannot join ordinary interior parts. Say
  // so up front, matching the server, instead of the impossible "duplicate
  // an existing Photo Nest" instruction after photo upload and tracing.
  if (kind === "nest" && !isModifier && state.design?.layout?.features?.some(one => one.kind !== "nest")) {
    toast("Photo Nest designs can contain Photo Nests only. Remove the other interior parts first.", true, 5000);
    return;
  }
  if (b4bEnabled() && !b4bPartAllowed(kind)) {
    toast(B4B_PARTS_ONLY_DIVIDER_MESSAGE, true, 5000);
    return;
  }
  if (b4bEnabled() && kind === "divider") {
    const existing = state.design?.layout?.features?.findIndex(
      one => one.kind === "divider"
    );
    if (Number.isInteger(existing) && existing >= 0) {
      selectedFeature(existing);
      return;
    }
  }
  state.paletteBrowsing = false;
  if (isModifier) {
    if (partAtLimit(info)) return openModifier(kind);
    return addModifier(kind);
  }
  updateInteriorModeVisibility(true);
  selectKind(kind);
}

async function selectEdgeMount(fromPlaced = false) {
  return openModifier("edge_mount", fromPlaced);
}

function insideHandlesActive(design = state.design) {
  return Boolean(design?.box?.lift_grabbers?.enabled);
}

const INSIDE_HANDLES_REMOVABLE_MESSAGE =
  "Inside Grip is built into the bin wall, so it isn’t available with Removable insert. Choose Fused into box to use Inside Grip.";

async function openModifier(kind, fromPlaced = false) {
  if (b4bEnabled()) {
    toast(B4B_PARTS_ONLY_DIVIDER_MESSAGE, true, 5000);
    return;
  }
  if (!BOX_MODIFIER_KINDS.has(kind) || !edgeMountAvailable()) return;
  if (state.draft && !(await guardDraftSwitch())) return;
  resetNestPhotoSession();
  if (state.modifierEditing && state.modifierEditing !== kind &&
      !flushModifierForm()) {
    return;
  }
  cancelPendingDraftWork();
  state.paletteBrowsing = false;
  state.draft = null;
  state.draftKind = kind;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.draftTouched = false;
  state.selected = null;
  state.edgeMountEditing = kind === "edge_mount";
  state.modifierEditing = kind;
  $(".support-editor").hidden = false;
  $("#draft-fields").hidden = true;
  $("#edge-mount-editor").hidden = kind !== "edge_mount";
  const panelByKind = {
    lid_stacking: "#lid-option",
    inside_handles: "#inside-handles-option",
    side_openings: "#side-openings-option",
  };
  for (const [oneKind, selector] of Object.entries(panelByKind)) {
    const panel = $(selector);
    if (panel) panel.hidden = oneKind !== kind;
  }
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === kind));
  const info = partInfo(kind);
  syncDraftEditorIdentity(kind, info);
  if (kind === "edge_mount") {
    syncEdgeMountControls();
  } else if (kind === "lid_stacking") {
    syncLidForm();
    $("#lid-option-panel").hidden = false;
  } else if (kind === "inside_handles") {
    $("#lift-grabber-size").value = state.design.box.lift_grabbers?.size || "medium";
    $("#lift-grabber-location").value = state.design.box.lift_grabbers?.location || "sides";
    syncLiftGrabberControls();
  } else if (kind === "side_openings") {
    syncSideOpeningControls();
    $("#side-openings-panel").hidden = false;
  }
  renderPlaced();
  updateSelectionButtons();
}

async function addModifier(kind) {
  if (b4bEnabled()) {
    toast(B4B_PARTS_ONLY_DIVIDER_MESSAGE, true, 5000);
    return;
  }
  if (kind === "inside_handles" && state.design.layout.mode !== "fused") {
    toast(INSIDE_HANDLES_REMOVABLE_MESSAGE, true, 6500);
    return;
  }
  return withDeferredDraftSwitch(async () => {
  if (kind === "edge_mount") {
    const previous = clone(state.design);
    const rules = state.catalog?.edge_mount || {};
    const side = state.design.box.edge_mount?.side || "front";
    const normalDepth = ["front", "back"].includes(side)
      ? number(state.design.box.y) : number(state.design.box.x);
    const projection = Math.min(
      number(rules.max_projection_mm, 200),
      Math.max(number(rules.min_projection_mm, 5), normalDepth / 3),
    );
    // This Space's remembered Edge Mount settings (label plate thickness,
    // type, ribs, screw settings...) seed the new option; text is always
    // blank and the label starts on with screw mounting off.
    const seed = spaceModifierDefaults("edge_mount") || {};
    const seededProjection = Number(seed.label_projection_mm);
    state.design.box.edge_mount = {
      ...EDGE_MOUNT_DEFAULTS,
      ...(state.design.box.edge_mount || {}),
      label_type: "separate",
      standoff_ribs_enabled: true,
      label_projection_mm: projection,
      access_diameter_mm: null,
      ...seed,
      ...(Number.isFinite(seededProjection) ? {
        label_projection_mm: Math.min(
          number(rules.max_projection_mm, 200),
          Math.max(number(rules.min_projection_mm, 5), seededProjection),
        ),
      } : {}),
      // Fix 058 Correction 1, C1.4B: a new Edge Mount defaults its Label
      // selector to None (and Screw Mounting stays off) rather than opening
      // pre-enabled - text is always blank regardless.
      label_enabled: false,
      holes_enabled: false,
      label_text: "",
    };
    noteCommittedDesignChange(previous);
    syncForm();
    await openModifier(kind);
    await refreshPreview();
    return;
  }
  const previous = clone(state.design);
  const seed = spaceModifierDefaults(kind) || {};
  if (kind === "lid_stacking") {
    if (seed.lid) {
      state.design.box.lid = { ...seed.lid, enabled: true };
      delete state.design.box.stack;
    } else {
      state.design.box.stack = { mode: "direct" };
    }
  } else if (kind === "inside_handles") {
    const rules = state.catalog?.lift_grabbers || {};
    state.design.box.lift_grabbers = {
      enabled: true,
      size: seed.size || rules.default_size || "medium",
      location: seed.location || rules.default_location || "sides",
    };
  } else if (kind === "side_openings") {
    const eligible = SIDE_OPENING_SIDE_IDS.filter(side => sideOpeningEligibleSide(side));
    const rememberedSides = Array.isArray(seed.sides)
      ? seed.sides.filter(side => eligible.includes(side)) : [];
    const sides = rememberedSides.length
      ? rememberedSides
      : ["left", "right"].filter(side => eligible.includes(side));
    if (!sides.length && eligible.length) sides.push(eligible[0]);
    if (!sides.length) {
      toast("No bin wall is available for Side Openings.", true, 5500);
      return;
    }
    state.design.box.side_openings = {
      ...SIDE_OPENING_DEFAULTS, ...seed, enabled: true, sides,
    };
    clampSideOpeningTopForLid(state.design, true);
  }
  noteCommittedDesignChange(previous);
  syncForm();
  await openModifier(kind);
  refreshPreview();
  });
}

async function removeModifier(kind) {
  if (!modifierIsActive(kind)) {
    clearDraftSelection();
    renderPlaced();
    return;
  }
  return withDeferredDraftSwitch(async () => {
  if (!beginDesignMutation()) return;
  try {
    const previous = clone(state.design);
    if (kind === "lid_stacking") {
      delete state.design.box.stack;
      delete state.design.box.lid;
      normalizeStackSettings(state.design, { restoreDefaults: true, flash: true });
    } else if (kind === "inside_handles") {
      state.design.box.lift_grabbers = { enabled: false, size: "medium", location: "sides" };
    } else if (kind === "side_openings") {
      state.design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    } else if (kind === "edge_mount") {
      state.design.box.edge_mount = { ...EDGE_MOUNT_DEFAULTS };
    }
    const result = await api("/api/design/validate", { design: state.design });
    state.design = result.design;
    noteCommittedDesignChange(previous);
    state.paletteBrowsing = true;
    clearDraftSelection();
    // Forms must match the validated design before any later form read, or a
    // stale handle/opening control would silently re-add the deleted option.
    syncForm();
    renderPlaced();
    await refreshPreview();
    toast(`${partInfo(kind)?.title || "Option"} deleted.`);
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
  });
}

function flushModifierForm() {
  if (!state.modifierEditing) return true;

  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;

  cancelChangedDesignDebounce();
  pendingDesignHistory = null;

  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
    return false;
  }

  noteCommittedDesignChange(previousDesign);
  return true;
}

async function flushVisibleDesignEditsBeforeModeSwitch({ previewAfterCommit = true } = {}) {
  if (state.designMutationBusy) return false;
  if (state.draft && !(await guardDraftSwitch({ previewAfterCommit }))) return false;
  if (state.modifierEditing) return flushModifierForm();

  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  cancelChangedDesignDebounce();
  pendingDesignHistory = null;
  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) return false;
  noteCommittedDesignChange(previousDesign);
  return true;
}
window.flushVisibleDesignEditsBeforeModeSwitch = flushVisibleDesignEditsBeforeModeSwitch;

function syncDraftEditorIdentity(kind, info) {
  const isNest = kind === "nest";
  const title = $("#draft-title");
  const description = $("#draft-description");

  title.textContent = info.title;
  description.textContent = "";
  description.hidden = true;

  // Fix 081 C: Bore now identifies itself above its settings like every
  // other kind, so its editor no longer needs a standalone "Type" card to
  // stand in for a name.
  title.hidden = isNest;
  // Fix 058 Correction 1, C1.4A: the palette keeps its short description for
  // discoverability, but the Edge Mount editor's own Label/Screw Mounting
  // hierarchy makes the redundant "Add a label and/or screw mounting..."
  // sentence unnecessary once the editor is open.
  // Fix 060 A: the Lid & Stacking editor's own Configuration/Lid/Handle/Label
  // hierarchy makes the redundant "Add a lid or make matching bins stack
  // together." sentence unnecessary once the editor is open; the palette
  // tile keeps it for discoverability.
  description.hidden = true;

  $(".support-editor")?.classList.toggle("nest-editor", isNest);
}

// Fix 109 A3: a brand-new Cradle grows its bin to the minimum legal size.
// The trial is read-only: nothing live is assigned until the Space rules
// (aiSpaceViolation) accept it. Returns "adopted" (the expanded canonical design
// is now live and already contains the Cradle), "blocked" (live design/bin/
// Inventory untouched; only the uncommitted draft remains) or "stale".
async function growBinForNewCradle(request) {
  const designAtStart = state.design;
  const source = state.designInventoryId, space = state.activeSpace;
  const stale = () => request !== state.kindRequest || state.design !== designAtStart ||
    source !== state.designInventoryId || space !== state.activeSpace;
  // The engine's starter may be clamped to the container; the real minimum
  // always comes from sizeCradleToItem (mirrors cradle_min_footprint).
  sizeCradleToItem(state.draft);
  const blocker = message => {
    state.draftAutoCommit = false;
    $("#draft-status").textContent = message;
    $("#draft-status").classList.add("error");
    renderDraftFields();
    updateSelectionButtons();
    return "blocked";
  };
  const features = [...designAtStart.layout.features, state.draft];
  const design = { ...designAtStart, layout: { ...designAtStart.layout, features } };
  let trial;
  try {
    trial = await api("/api/layout/expand", { design, anchor: features.length - 1, fit: false });
  } catch (error) {
    return stale() ? "stale" : blocker(friendlyError(error));
  }
  if (stale()) return "stale";
  const violation = aiSpaceViolation(trial.design, designAtStart);
  if (violation) return blocker(violation);
  const previousDesign = clone(designAtStart);
  const previousBox = { ...designAtStart.box };
  state.design = trial.design;
  noteCommittedDesignChange(previousDesign);
  const at = features.length - 1;
  state.selected = at;
  state.draftIsNew = false;
  state.draftTouched = false;
  state.draftSourceIndex = at;
  state.draft = clone(state.design.layout.features[at]);
  syncForm();
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
  if (trial.box.x !== previousBox.x) flashField($("#x-size"));
  if (trial.box.y !== previousBox.y) flashField($("#y-size"));
  return "adopted";
}

async function selectKind(kind, reset = false) {
  if (b4bEnabled() && !b4bPartAllowed(kind)) {
    toast(B4B_PARTS_ONLY_DIVIDER_MESSAGE, true, 5000);
    return;
  }
  if (kind === "divider" && dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  // Re-picking the shape already open keeps the same draft, so there is nothing
  // to lose - skip the guard in that case. Anything else replaces the draft, so
  // give the user the chance to keep unsaved work first.
  const keepsSameDraft = !reset && state.draft?.kind === kind;
  const switchGuard = keepsSameDraft ? null : await deferredDraftSwitch();
  try {
  if (switchGuard && !switchGuard.proceed) return;
  if (!keepsSameDraft && state.draft?.kind === "nest") resetNestPhotoSession();
  if (!flushModifierForm()) return;
  state.edgeMountEditing = false;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  // The palette request is independent of preview/draft requests. Without its
  // own token, a slower earlier click could overwrite a newer shape choice.
  // A new palette choice also makes every pending edit to the prior draft
  // obsolete. Otherwise its auto-save could land after this new choice.
  cancelPendingDraftWork();
  const request = ++state.kindRequest;
  updateInteriorModeVisibility(true);
  state.draftKind = kind;
  state.selected = null;
  state.draftIsNew = true;
  state.draftSourceIndex = null;
  state.draftAutoCommit = kind !== "nest";
  $(".support-editor").hidden = false;
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === kind));
  const info = partInfo(kind);
  syncDraftEditorIdentity(kind, info);
  updateSelectionButtons();
  if (!reset && state.draft?.kind === kind) {
    renderDraftFields();
    const preview = refreshDraft();
    if (switchGuard) switchGuard.claimDraft(preview);
    return;
  }
  $("#draft-status").textContent = "Loading shape…";
  try {
    const result = await api("/api/feature/default", {
      design: state.design,
      kind,
      along: "x",
      item: info.flags.item ? starterItem() : null,
    });
    if (request !== state.kindRequest) return;
    // A newly added part starts from this Space's remembered settings for its
    // kind (size, count, options - never position or text). An existing part
    // is opened from the bin's own exact design instead (selectedFeature).
    state.draft = state.folderMode === "space"
      ? seedFeatureFromPartDefaults(result.feature, state.spacePartDefaults?.[kind])
      : result.feature;
    state.draftTouched = false;
    state.pinnedZone = {};
    state.draftResolvedOptions = result.resolved_options || {};
    state.referenceResolutionRequest = state.draftRequest;
    // What the engine started this text at, so the Part Name is only ever
    // seeded from lettering the user actually typed - never the placeholder.
    state.draftStartingText = result.feature?.options?.text ?? null;
    if (kind === "bore") sizeBoreToGrid(state.draft);
    renderDraftFields();
    updateSelectionButtons();

    // Auto-save the new part immediately and treat it as a saved part we are editing.
    // Fix 082 H: a brand-new Text with no words yet is an inert editor state,
    // not a design mutation - it stays an uncommitted armed draft (draftIsNew)
    // until real lettering is typed, at which point the normal edit pipeline
    // (refreshDraft -> autoCommitDraft) saves it for the first time.
    let cradleGrown = false;
    if (kind === "cradle" && !designTargetIsStructural()) {
      const outcome = await growBinForNewCradle(request);
      if (outcome !== "adopted") return;
      cradleGrown = true;
    }
    if (kind !== "nest" && !cradleGrown && !isBlankTextDraft(state.draft)) {
      try {
        const applyResult = await api("/api/feature/apply", {
          design: state.design,
          feature: state.draft,
          index: null,
        });
        if (request !== state.kindRequest) return;
        const previousDesign = clone(state.design);
        state.design = applyResult.design;
        seedPartNameFromText(state.draft);
        noteCommittedDesignChange(previousDesign);
        state.selected = applyResult.selected;
        state.draftIsNew = false;
        state.draftTouched = false;
        if (Number.isInteger(applyResult.selected)) state.draftSourceIndex = applyResult.selected;
        if (state.selected !== null && state.design.layout.features[state.selected]) {
          state.draft = clone(state.design.layout.features[state.selected]);
        }
        renderDraftFields();
        renderPlaced();
        updateSelectionButtons();
      } catch (applyErr) {
        $("#draft-status").textContent = applyErr.message;
        $("#draft-status").classList.add("error");
      }
    }
    const preview = refreshDraft();
    if (switchGuard) switchGuard.claimDraft(preview);
  } catch (error) {
    if (request !== state.kindRequest) return;
    $("#draft-status").textContent = friendlyError(error);
    toast(error.message, true);
  }
  } finally {
    switchGuard?.finish();
  }
}

async function selectedFeature(index, force = false, acceptPreviewPick = null) {
  if (index === null || index < 0 || index >= state.design.layout.features.length) return false;
  if (!force && index === state.selected) return !acceptPreviewPick || acceptPreviewPick();
  const request = state.selectionRequest = (state.selectionRequest || 0) + 1;
  const design = state.design, source = state.designInventoryId, space = state.activeSpace;
  const previewRequest = state.previewRequest;
  // Don't drop unsaved work on the part currently open without asking first.
  const switchGuard = force ? null : await deferredDraftSwitch();
  try {
  if (switchGuard && !switchGuard.proceed) return false;
  const expectedDesign = switchGuard?.committed ? state.design : design;
  if (request !== state.selectionRequest || expectedDesign !== state.design ||
      source !== state.designInventoryId || space !== state.activeSpace) return false;
  if (acceptPreviewPick && !acceptPreviewPick(expectedDesign,
      switchGuard?.committed && state.previewRequest === previewRequest + 1)) return false;
  const selected = state.design.layout.features[index];
  if (state.draft?.kind === "nest" || selected?.kind === "nest") resetNestPhotoSession();
  if (!flushModifierForm()) return false;
  cancelPendingDraftWork();
  state.edgeMountEditing = false;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  state.paletteBrowsing = false;
  state.selected = index;
  state.nudgeFeedback = null;
  updateNudgeUI();
  // A fresh selection starts the outline editor's viewport fitted again,
  // rather than carrying over whatever zoom/pan the previous part left set.
  state.nestViewZoom = 1;
  state.nestViewPanX = 0;
  state.nestViewPanY = 0;
  state.draft = clone(state.design.layout.features[index]);
  state.nestOutlineEditing = false;
  state.draftTouched = false;
  state.draftAutoCommit = true;
  state.draftIsNew = false;
  state.draftSourceIndex = index;
  state.pinnedZone = state.partZoneLocks[index] ||= {};
  if (AUTO_FOOTPRINT_KINDS.has(state.draft.kind)) {
    // Once a part is placed, its stored footprint is user-owned. Locks remain
    // session-only, but every reopened part starts protected on both axes.
    state.pinnedZone.width = true;
    state.pinnedZone.depth = true;
  }
  state.draftResolvedOptions = {};
  state.referenceResolutionRequest = null;
  if (state.draft.kind === "bore") sizeBoreToGrid(state.draft);
  state.draftKind = state.draft.kind;
  updateInteriorModeVisibility(true);
  $(".support-editor").hidden = false;
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === state.draftKind));
  const info = partInfo();
  syncDraftEditorIdentity(state.draftKind, info);
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
  const preview = refreshDraft();
  if (switchGuard) switchGuard.claimDraft(preview);
  renderLayout2D();
  return true;
  } finally {
    switchGuard?.finish();
  }
}
const roundUpHalfMm = value => Math.ceil((number(value, 0) - 1e-9) * 2) / 2;
const roundNearestHalfMm = value => Math.round(number(value, 0) * 2) / 2;
const boreDerivedDimension = (key, value) => ["height", "depth"].includes(key) &&
  value !== null && value !== undefined && value !== ""
  ? roundNearestHalfMm(value) : value;
function roundFitZoneUpHalfMm(zone) {
  const cx = (zone[0] + zone[2]) / 2, cy = (zone[1] + zone[3]) / 2;
  const width = roundUpHalfMm(zone[2] - zone[0]);
  const depth = roundUpHalfMm(zone[3] - zone[1]);
  return [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
}

// One live pair owns the inset_v2 range. Upper is measured from the floor;
// the saved compatibility field measures that same edge down from the rim.
function sideOpeningPairFromControls() {
  return {
    lower: number($("#side-opening-lower")?.value, 0),
    upper: number($("#side-opening-upper")?.value, 100),
  };
}

function sideOpeningRangeLegal(design, pair) {
  if (pair.lower < 0 || pair.upper > 100 || pair.lower >= pair.upper) return false;
  const fromTop = 100 - pair.upper;
  if (sideOpeningLidStackForced(design) && fromTop + 1e-8 < sideOpeningMinFromTop(design)) return false;
  const shape = $("#side-opening-shape")?.value || sideOpeningState(design).shape;
  const size = $("#side-opening-size")?.value || sideOpeningState(design).size;
  const width = (state.catalog?.side_openings?.sizes || []).find(one => one.value === size)?.width_mm;
  return !width || sideOpeningVerticalFits(design, {
    shape, from_bottom_percent: pair.lower, from_top_percent: fromTop,
  }, width);
}

function normalizeSideOpeningPair(design, pair, changed = "lower") {
  const maximum = sideOpeningLidStackForced(design) ? 100 - sideOpeningMinFromTop(design) : 100;
  const trial = { lower: Math.max(0, Math.min(99.9, pair.lower)),
    upper: Math.max(0.1, Math.min(maximum, pair.upper)) };
  if (sideOpeningRangeLegal(design, trial)) return trial;
  if (changed === "lower") {
    for (let value = Math.min(trial.lower, trial.upper - 0.1); value >= 0; value -= 0.1) {
      trial.lower = Math.round(value * 10) / 10;
      if (sideOpeningRangeLegal(design, trial)) return trial;
    }
  } else {
    for (let value = Math.max(trial.upper, trial.lower + 0.1); value <= maximum + 1e-8; value += 0.1) {
      trial.upper = Math.round(value * 10) / 10;
      if (sideOpeningRangeLegal(design, trial)) return trial;
    }
  }
  return { lower: number(sideOpeningState(design).from_bottom_percent, 0),
    upper: 100 - number(sideOpeningState(design).from_top_percent, 0) };
}

function syncSideOpeningRange(spec) {
  const lower = $("#side-opening-lower"), upper = $("#side-opening-upper");
  if (!lower || !upper) return;
  const pair = { lower: number(spec.from_bottom_percent, 0),
    upper: 100 - number(spec.from_top_percent, 0) };
  const maximum = sideOpeningLidStackForced() ? 100 - sideOpeningMinFromTop() : 100;
  lower.max = String(Math.max(0, pair.upper - 0.1));
  upper.min = String(Math.min(100, pair.lower + 0.1));
  upper.max = String(maximum);
  lower.value = String(pair.lower);
  upper.value = String(pair.upper);
  const box = state.design?.box || {};
  const floorZ = number(box.base_thickness);
  const usable = number(box.z) - floorZ;
  const lowerMm = floorZ + usable * (number(spec.from_bottom_percent, 0) / 100);
  const upperMm = number(box.z) - usable * (number(spec.from_top_percent, 0) / 100);
  $("#side-opening-upper-mm").textContent = `${fmt(upperMm)} mm`;
  $("#side-opening-lower-mm").textContent = `${fmt(lowerMm)} mm`;
  lower.setAttribute("aria-valuetext", `${fmt(pair.lower)}% from bottom`);
  upper.setAttribute("aria-valuetext", `${fmt(pair.upper)}% up from floor, ${fmt(100 - pair.upper)}% from top`);
  const fill = $("#side-opening-range-fill");
  if (fill) {
    fill.style.bottom = `${pair.lower}%`;
    fill.style.height = `${pair.upper - pair.lower}%`;
  }
  // Fix 081 G: the two dotted connectors point from each handle to the wall
  // edge it controls, at that same handle's live position.
  const connectorUpper = $("#side-opening-connector-upper");
  const connectorLower = $("#side-opening-connector-lower");
  if (connectorUpper) connectorUpper.style.bottom = `${pair.upper}%`;
  if (connectorLower) connectorLower.style.bottom = `${pair.lower}%`;
  // Fix 078: the visible UI shows only the Top of bin / Base of bin cues and
  // the fill span - no visible percent-from-top/bottom text. The exact
  // percentages remain available to assistive technology via aria-valuetext
  // above.
}

function field(label, key, value, options = {}) {
  const classes = options.wide ? "wide" : "";
  const type = options.type || "number";
  const attrs = type === "number" ? `step="${options.step || "0.1"}"` : "";
  const min = options.min !== undefined ? ` min="${escapeHtml(options.min)}"` : "";
  const max = options.max !== undefined ? ` max="${escapeHtml(options.max)}"` : "";
  const placeholder = options.placeholder ? ` placeholder="${escapeHtml(options.placeholder)}"` : "";
  const tip = options.tip ? ` title="${escapeHtml(options.tip)}"` : "";
  const data = options.dataAttribute
    ? `${options.dataAttribute}="${escapeHtml(key)}"`
    : `data-draft="${escapeHtml(key)}"`;
  return `<label class="${classes}"${tip}><span class="field-label">${escapeHtml(label)}${options.unit ? `<span class="unit">${escapeHtml(options.unit)}</span>` : ""}</span>
    <input type="${type}" ${data} value="${escapeHtml(value ?? "")}" ${attrs}${min}${max}${placeholder}>
  </label>`;
}

// The Divider's own wall thickness is a real numeric option (no "standard"
// sentinel like the bin wall), but it draws from the same preset catalog so
// the two controls can never drift apart.
function dividerThicknessField(value, key = "option:thickness") {
  const choices = wallPresetChoices();
  const current = fmt(number(value, 1.6));
  const isPreset = choices.some(choice => fmt(choice.value) === current);
  const optionsHtml = choices.map(choice => {
    const choiceValue = fmt(choice.value);
    return `<option value="${choiceValue}" ${choiceValue === current ? "selected" : ""}>${number(choice.value).toFixed(1)} mm — ${escapeHtml(choice.label)}</option>`;
  }).join("");
  // A saved design keeps whatever thickness it was made with: the preset list
  // is what a *new* choice may be, not a migration of existing geometry.
  const customOption = isPreset ? ""
    : `<option value="${current}" selected>${current} mm — Existing</option>`;
  return `<label><span class="field-label">Wall thickness</span>
    <select data-draft="${key}">${optionsHtml}${customOption}</select>
  </label>`;
}

function scoopDepthField(key, value, options = {}) {
  return field("Scoop height", key, value, {
    unit: "% of bin height", step: "1", min: "1", max: "100",
    tip: options.tip || "The scoop always spans the full usable bin width and starts at the front floor edge.",
    dataAttribute: options.dataAttribute,
  });
}

// Compact inline checkbox - the space-saving replacement for the full-width
// check-card. `help` becomes a hover tooltip rather than always-on body text.
// `key` is the full data-draft attribute (e.g. "option:slope_base").
function toggle(key, title, help, on, options = {}) {
  const classes = ["editor-toggle"];
  if (options.wide) classes.push("wide");
  const tip = help ? ` title="${escapeHtml(help)}"` : "";
  return `<label class="${classes.join(" ")}"${tip}>
    <input type="checkbox" data-draft="${key}" ${on ? "checked" : ""}>
    <span>${escapeHtml(title)}</span>
  </label>`;
}

// The two fixed-size hex-bit profiles. Selecting one locks the hole to a
// 1/4-inch bit and drives the hole depth so the bit stands well proud.
const HEX_BIT_PROFILES = {
  hex_bit_short: { label: "Hex bit – short", length: 25, diameter: 6.35, clearance: 0.25 },
  hex_bit_long: { label: "Hex bit – long", length: 38, diameter: 6.35, clearance: 0.25 },
};
const isHexBitProfile = profile => Object.prototype.hasOwnProperty.call(HEX_BIT_PROFILES, profile);

function resolvedDraftCount(one) {
  if (one.count != null) return Math.max(1, Math.round(number(one.count, 1)));
  const [x0, y0, x1, y1] = one.zone;
  const width = x1 - x0, depth = y1 - y0;
  const options = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  const along = one.along === "y" ? "y" : "x";
  const across = along === "x" ? depth : width;
  if (one.kind === "cradle") {
    const diameter = number(one.item?.segments?.[0]?.diameter, 6);
    const wall = number(resolved.rib_thickness, Math.max(1.6, diameter * .25));
    const spacing = Math.max(0, number(options.spacing ?? resolved.spacing, 0));
    const body = diameter + wall;
    const pitch = diameter + wall / 2 + spacing;
    return Math.max(1, Math.floor((across - body + 1e-6) / pitch) + 1);
  }
  if (one.kind === "post") {
    const diameter = number(options.diameter ?? resolved.diameter, 12);
    const spacing = Math.max(0, number(options.spacing ?? resolved.spacing, 4));
    const countX = Math.max(1, Math.floor((width - diameter + 1e-6) / (diameter + spacing)) + 1);
    const countY = Math.max(1, Math.floor((depth - diameter + 1e-6) / (diameter + spacing)) + 1);
    return countX * countY;
  }
  if (one.kind === "slot") {
    const thickness = number(options.thickness ?? resolved.thickness, 4);
    const wall = number(options.wall ?? resolved.wall, 1.6);
    const angle = Math.abs(number(options.angle ?? resolved.angle, 20)) * Math.PI / 180;
    const pitch = (thickness + wall) / Math.cos(angle);
    return Math.max(1, Math.floor((across - 2 * wall - thickness / Math.cos(angle) + 1e-6) / pitch) + 1);
  }
  return Math.max(1, Math.round(number(options.count ?? resolved.count, 3)));
}

function plainCheckbox(key, title, on, options = {}) {
  const classes = ["checkbox-row"];
  if (options.wide) classes.push("wide");
  const tip = options.help ? ` title="${escapeHtml(options.help)}"` : "";
  const attribute = options.dataAttribute || "data-draft";
  return `<label class="${classes.join(" ")}"${tip}>
    <input type="checkbox" ${attribute}="${escapeHtml(key)}" ${on ? "checked" : ""}>
    <span>${escapeHtml(title)}</span>
  </label>`;
}

// Photo Nest Access state has exactly one writer per value. Finger access owns
// lift_assist (auto / none / finger_grasp), the Push Out toggle owns
// lift_assist = "push_out", and Location / Push at own their own positions.
// A value is written only when its own control is what changed, so an
// unrelated edit can never re-read a select that cannot represent push_out.
function applyNestAccessOptions(options, changed, get) {
  for (const key of ["lift_assist", "finger_position", "push_position"]) {
    if (changed !== `option:${key}`) continue;
    const value = get(`option:${key}`);
    if (value !== undefined) options[key] = value;
  }
}

// The Push Out toggle: on writes push_out; off returns to a legal Automatic.
function setNestPushOut(options, on) {
  options.lift_assist = on ? "push_out" : "auto";
}

// Finger access is replaced by Push Out while that is on, so it is not shown.
function nestFingerAccessVisible(holderStyle, assist) {
  return !(assist === "push_out" && holderStyle === "raised_wall");
}

// Photo Nest's editor: Tool, Holder, Finger access, Raised Wall advanced,
// Fit, Bin and Outline (spec section 45). Broken out of renderDraftFields
// only because it is long, not because it is reused elsewhere.
function renderNestFields(one) {
  const opt = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  const val = (key, fallback) => (opt[key] !== undefined && opt[key] !== null ? opt[key] : (resolved[key] ?? fallback));
  const selected = (value, actual) => value === actual ? "selected" : "";
  const holderStyle = String(val("holder_style", "raised_wall"));
  const assist = String(val("lift_assist", "auto"));
  const isPushOut = assist === "push_out";
  const fingerPosition = String(val("finger_position", "sides"));
  const cavityMode = String(val("cavity_depth_mode", "auto"));
  // Tool thickness is the one measurement the user actually has to supply -
  // show it blank (never a fabricated "8") until it is explicitly stored,
  // even though every other computed default below still needs some number
  // to illustrate against.
  const hasMeasuredThickness = opt.tool_thickness != null || opt.depth != null;
  const toolThickness = number(opt.tool_thickness ?? opt.depth ?? resolved.tool_thickness, 8);
  let html = "";

  html += `<div class="photo-upload wide">
    <label class="button secondary photo-button" for="nest-photo-input">
      ${one.contour ? "Replace photo" : "Upload part photo"}
    </label>
    <input id="nest-photo-input"
           type="file"
           accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp">
    <details>
      <summary>Photo requirements</summary>
      <ul>
        <li>Entire US Letter (8.5 × 11 in) reference sheet visible</li>
        <li>Camera directly overhead</li>
        <li>Part lies flat</li>
        <li>Plain, high-contrast background preferred</li>
      </ul>
    </details>
  </div>`;

  const shownRotation = ((number(one.rotation, 0) % 360) + 360) % 360;
  const standardRotation = [0, 90, 180, 270].some(value => Math.abs(value - shownRotation) < 1e-6);
  const spacing = opt.repeat_spacing_percent ?? 0;
  html += `<fieldset class="wide editor-group"><legend>Copies</legend>
    <div class="pair">
      <label>Quantity<input type="number" min="1" max="20" step="1" data-draft="nest-count" value="${Math.max(1, Math.min(20, Math.round(number(one.count, 1))))}"></label>
      <label>Orientation<select data-draft="nest-orientation">
        ${standardRotation ? "" : `<option value="${escapeHtml(String(one.rotation))}" selected disabled>Current ${fmt(one.rotation)}° (existing)</option>`}
        ${[[0, "As scanned"], [90, "90°"], [180, "180°"], [270, "270°"]].map(([value, label]) => `<option value="${value}" ${standardRotation && shownRotation === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>
    </div>
    ${plainCheckbox("nest-alternate", "Flip every other one", one.alternate_ends === true, { wide: true, help: "Turns every second copy 180° end-for-end." })}
    <label class="wide">Space between nests<select data-draft="option:repeat_spacing_percent">
      ${[[-100, "-100% (Minimum)"], [-75, "-75%"], [-50, "-50%"], [-25, "-25%"], [0, "Auto"], [25, "+25%"], [50, "+50%"], [75, "+75%"], [100, "+100%"]].map(([value, label]) => `<option value="${value}" ${Number(spacing) === value ? "selected" : ""}>${label}</option>`).join("")}
    </select></label>
    ${one.contour ? `<div class="pair"><button type="button" class="button secondary" data-action="duplicate-nest">Duplicate</button><button type="button" class="button secondary" data-action="edit-nest-outline">Edit outline</button></div>` : ""}
  </fieldset>`;

  const autoCavity = 0.6 * toolThickness;
  const cavityDepth = cavityMode === "manual"
    ? number(val("cavity_depth", autoCavity), autoCavity)
    : autoCavity;
  const cavityUnavailable = !hasMeasuredThickness && cavityMode !== "manual";

  // Holder: the Nest type owns what follows, so it comes first.
  html += `<div class="editor-group"><span class="editor-group-label">Holder</span>
    <label>Nest type
      <select data-draft="option:holder_style">
        <option value="recessed" ${selected("recessed", holderStyle)}>Recessed cavity</option>
        <option value="raised_wall" ${selected("raised_wall", holderStyle)}>Raised wall</option>
      </select>
    </label>`;

  html += `<div class="nest-primary-row">`;

  html += field(
    "Tool thickness",
    "option:tool_thickness",
    hasMeasuredThickness ? fmt(toolThickness) : "",
    {
      unit: "mm",
      step: "0.5",
      min: "0.5",
      placeholder: "required",
      tip: "The one measurement Wavefinity cannot work out from the photo.",
    },
  );

  if (holderStyle === "recessed") {
    html += `<div class="nest-cavity-column">`;

    html += field(
      "Cavity depth",
      "option:cavity_depth",
      cavityUnavailable ? "" : fmt(cavityDepth),
      {
        unit: "mm",
        step: "0.1",
        min: "0.1",
        placeholder: cavityUnavailable ? "needs Tool thickness" : undefined,
        tip: "Editing this switches to Manual so later Tool thickness changes stop recalculating it.",
      },
    );

    html += `<div class="nest-cavity-status">
      <span>${cavityMode === "manual"
        ? "Manual"
        : cavityUnavailable
          ? "Needs tool thickness"
          : "Auto — 60%"}</span>
      <button type="button"
              class="button secondary"
              data-action="nest-cavity-auto"
              ${cavityMode === "manual" ? "" : "disabled"}>
        Reset to 60%
      </button>
    </div>`;

    html += `</div>`;
  }

  html += `</div></div>`;

  // Access. Push Out replaces Finger access, so while it is on the Finger
  // access selector is not shown at all - it cannot even represent push_out.
  html += `<div class="editor-group"><span class="editor-group-label">Access</span>`;
  if (nestFingerAccessVisible(holderStyle, assist)) {
    html += `<label>Finger access
      <select data-draft="option:lift_assist">
        <option value="auto" ${selected("auto", isPushOut ? "" : assist)}>Automatic</option>
        <option value="none" ${selected("none", assist)}>Off</option>
        <option value="finger_grasp" ${selected("finger_grasp", assist)}>Custom</option>
      </select>
    </label>`;
    if (assist === "finger_grasp") {
      html += `<div class="pair">`;
      html += `<label>Location
        <select data-draft="option:finger_position">
          <option value="sides" ${selected("sides", fingerPosition)}>Sides</option>
          <option value="top_bottom" ${selected("top_bottom", fingerPosition)}>Ends</option>
          <option value="both" ${selected("both", fingerPosition)}>Both</option>
        </select>
      </label>`;
      html += field("Finger width", "option:finger_width",
        fmt(val("finger_width", resolved.finger_width ?? 25)),
        { unit: "mm", step: "1", min: "12", max: "40" });
      html += `</div>`;
    }
  }

  // Raised Wall advanced.
  if (holderStyle === "raised_wall") {
    html += `<details class="wide nest-advanced" ${isPushOut ? "open" : ""}><summary>Raised Wall advanced</summary>`;
    html += toggle("nest-push-out", "Push Out",
      "Raises the tool on a shaped floor with one selected end low, for pressing the opposite end up. Replaces Finger access while on.",
      isPushOut);
    if (isPushOut) {
      html += `<div class="pair triple">`;
      html += `<label>Push at
        <select data-draft="option:push_position">
          <option value="right" ${selected("right", val("push_position", "right"))}>Right</option>
          <option value="left" ${selected("left", val("push_position", "right"))}>Left</option>
          <option value="top" ${selected("top", val("push_position", "right"))}>Top</option>
          <option value="bottom" ${selected("bottom", val("push_position", "right"))}>Bottom</option>
        </select>
      </label>`;
      html += field("Push area", "option:push_area", fmt(val("push_area", 30)),
        { unit: "%", step: "5", min: "15", max: "40" });
      html += field("Push depth", "option:push_depth", fmt(val("push_depth", 4)),
        { unit: "mm", step: "0.5", min: "2", max: "8" });
      html += `</div>`;
    }
    html += `</details>`;
  }
  html += `</div>`;

  // Fit.
  html += `<div class="editor-group"><span class="editor-group-label">Fit</span>`;
  html += field(
    "Fit clearance",
    "option:clearance",
    fmt(val("clearance", 0.6)),
    { unit: "mm", step: "0.1", min: "0" },
  );
  html += `</div>`;

  // Bin. Read straight from the stored option, never the resolved fallback:
  // a legacy design with no stored preference must show as off here, not as
  // on just because it happens to behave in a similar grow-only way.
  html += `<div class="editor-group"><span class="editor-group-label">Bin</span>`;
  html += toggle("option:auto_size", "Automatically size footprint to tool",
    "Grows or shrinks the bin Width and Length to fit this Nest and keeps it centered. "
    + "Bin height stays at the height you set.",
    opt.auto_size === true, { wide: true });
  html += `</div>`;

  // Outline shape (Soften outline, manual point editing, zoom/pan, Finish
  // Editing) lives in the 2D view's own Outline editor panel now - editing
  // the outline is done looking directly at it, not from this sidebar.
  if (one.contour) {
    html += `<p class="photo-measurement">Outline ready — open the 2D view's Outline editor to reshape it.</p>`;
  }
  return html;
}

// Informational-only readout of how far the draft's own built geometry rises
// above the bin rim, straight from the preview's real mesh bounds - never
// recomputed here. Only ever a note, never a warning: a legal fused holder
// above the rim (Post, Cradle, Bore, Pocket, Slot, Steps, Raised-Wall Photo
// Nest) still generates fine.
function updateDraftOverhangNote() {
  const note = $('[data-draft-overhang]', $("#draft-fields"));
  if (!note) return;

  const overhang = number(state.preview?.draft_overhang_mm, 0);

  note.hidden = overhang <= 0.05;
  note.textContent = note.hidden
    ? ""
    : `Extends ${fmt(overhang)} mm above rim`;
}

// Bore style and sizing model (Fix 068). One persisted Style word and two
// persisted sizing modes replace the old wall_style / auto_base / auto_height /
// auto_grid state. Mirrors normalize_bore_style() / normalize_bore_modes() in
// organizer_inserts/_bore.py.
const BORE_STYLES = [
  ["base_straight", "Base - Straight Walls"],
  ["base_wavy", "Base - Wavy Walls"],
  ["walls_straight", "Straight Walls Only"],
  ["walls_wavy", "Wavy Walls Only"],
];
const BORE_LEGACY_STYLES = { full_base: "base_straight", wavy_base: "base_wavy" };
const boreWallsOnly = style => style === "walls_straight" || style === "walls_wavy";
const boreWavy = style => style === "base_wavy" || style === "walls_wavy";

function normalizeBoreStyle(style, wallStyle) {
  const word = String(style ?? "");
  if (BORE_STYLES.some(([value]) => value === word)) return word;
  if (BORE_LEGACY_STYLES[word]) return BORE_LEGACY_STYLES[word];
  if (word === "wall_only") return wallStyle === "straight" ? "walls_straight" : "walls_wavy";
  return "base_straight";
}

function boreStyleOf(one) {
  return normalizeBoreStyle(
    one?.options?.bore_style ?? state.draftResolvedOptions?.bore_style,
    one?.options?.wall_style,
  );
}

// A new lean with no explicit direction defaults to Back, or the side
// opposite the design's one allowed rim Text (Fix 078). Never used once the
// user has explicitly chosen a direction.
function boreDefaultAngleDirection(design) {
  const opposite = { back: "front", front: "back", left: "right", right: "left" };
  const rimText = (design?.layout?.features || []).find(
    feature => feature.kind === "text" && feature.options?.level === "rim");
  return opposite[rimText?.options?.rim_side || ""] || "back";
}

// Width / Length sizing: Walls Only has no Base fields, so it only chooses
// between Manually and sizing the bin to itself (its default).
function boreXyMode(one) {
  const style = boreStyleOf(one);
  const walls = boreWallsOnly(style);
  const mode = one?.options?.xy_size_mode;
  const allowed = walls ? ["manual", "bin_to_bore"] : ["manual", "bore_to_bin", "bin_to_bore"];
  return allowed.includes(mode) ? mode : (walls ? "bin_to_bore" : "manual");
}

function boreHeightMode(one) {
  const mode = one?.options?.height_size_mode;
  return ["manual", "bore_to_bin", "bin_to_bore"].includes(mode) ? mode : "manual";
}

function wallStyleSelect(style) {
  return `<label><span class="field-label">Walls</span><select data-draft="option:wall_style">
    <option value="wavy" ${style === "wavy" ? "selected" : ""}>Wavy Walls</option>
    <option value="straight" ${style === "wavy" ? "" : "selected"}>Straight Walls</option>
  </select></label>`;
}

// Match Pocket's backend envelope and Bore Wall Only's outward wave reach.
// The catalog's wall_rules is the one authoritative owner of the wave
// contract - see sizeBoreToGrid, which already consumes it the same way.
function pocketWallReach(wall, style) {
  if (style !== "wavy") return wall;
  const wallRules = state.catalog?.wall_rules || {};
  const amplitude = number(wallRules.wave_amplitude_mm, 0.4);
  const depthFactor = number(wallRules.wall_depth_factor, 1.181);
  const waveNoiseFloor = 1e-4;  // ensure wavy troughs never self-intersect
  return 2 * amplitude + wall * depthFactor + waveNoiseFloor;
}

function referencePhysicalHeight(draft, resolvedOptions) {
  const explicitHeight = draft.options?.height;
  const rawHeight = explicitHeight !== null && explicitHeight !== undefined && explicitHeight !== ""
    ? explicitHeight : resolvedOptions?.height;
  const height = Number(rawHeight);
  if (rawHeight === null || rawHeight === undefined || rawHeight === "" ||
      !Number.isFinite(height) || height <= 0) return null;
  if (draft.kind !== "steps") return height;
  const explicitLip = draft.options?.lip;
  const rawLip = explicitLip !== null && explicitLip !== undefined && explicitLip !== ""
    ? explicitLip : resolvedOptions?.lip;
  const lip = Number(rawLip);
  if (rawLip === null || rawLip === undefined || rawLip === "" || !Number.isFinite(lip)) return null;
  const physicalHeight = height + Math.max(0, lip);
  return Number.isFinite(physicalHeight) ? physicalHeight : null;
}

function referenceSeedForDraft(draft, resolvedOptions, design) {
  const zone = draft.zone;
  const usable = Math.max(0.1, number(design?.box?.z, 8) - number(design?.box?.base_thickness, 0.6));
  const resolved = draft.kind === "nest" ? _nestMeasuredThickness(draft.options)
    : referencePhysicalHeight(draft, resolvedOptions);
  if (["pocket", "post", "slot", "steps"].includes(draft.kind) &&
      (!Number.isFinite(resolved) || resolved <= 0)) {
    throw new Error("Wait for this part's height to finish updating before adding a reference.");
  }
  return { width: zone[2] - zone[0], depth: zone[3] - zone[1],
    height: Number.isFinite(resolved) && resolved > 0 ? resolved : usable };
}

function updateReferenceAxis(draft, axis, raw) {
  const value = Number(raw);
  if (!raw.trim() || !Number.isFinite(value) || value <= 0) return false;
  draft.reference_object[axis] = value;
  return true;
}

function referenceAddReady() {
  if (!state.draft || state.draftIsNew || state.draftTouched ||
      !Number.isInteger(draftCommitIndex())) return false;
  if (state.draft.kind === "nest") {
    return Boolean(state.draft.contour && _nestMeasuredThickness(state.draft.options) > 0);
  }
  if (!["pocket", "post", "slot", "steps"].includes(state.draft.kind)) return false;
  const resolved = state.referenceResolutionRequest === state.draftRequest
    ? state.draftResolvedOptions : null;
  return referencePhysicalHeight(state.draft, resolved) !== null;
}

function updateReferenceAddAvailability() {
  const button = $('[data-action="add-reference"]', $("#draft-fields"));
  if (button) button.hidden = !referenceAddReady();
}

function addReferenceToCurrentDraft() {
  const draft = state.draft;
  if (!draft || !referenceAddReady()) return;
  const resolved = state.referenceResolutionRequest === state.draftRequest
    ? state.draftResolvedOptions : null;
  markDraftChanged(true);
  draft.reference_object = referenceSeedForDraft(draft, resolved, state.design);
  state.draftAutoCommit = true;
  state.referenceEditPending = true;
  renderDraftFields();
  commitReferenceEditSoon();
}

function removeReferenceFromCurrentDraft() {
  if (!state.draft?.reference_object) return;
  markDraftChanged(true);
  delete state.draft.reference_object;
  state.draftAutoCommit = true;
  state.referenceEditPending = true;
  renderDraftFields();
  commitReferenceEditSoon();
}

const commitReferenceEditSoon = debounce(commitReferenceEdit, 180);

async function commitReferenceEdit() {
  if (!state.draft || !state.referenceEditPending) return;
  const index = draftCommitIndex();
  if (index === false) return;
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const request = state.draftRequest;
  const before = clone(state.design);
  try {
    const result = await api("/api/feature/reference", { design: before, feature: draft, index });
    if (request !== state.draftRequest || state.draft !== draft || JSON.stringify(draft) !== snapshot) return;
    state.design = result.design;
    noteCommittedDesignChange(before);
    state.draftIsNew = false;
    state.draftTouched = false;
    state.referenceEditPending = false;
    state.selected = result.selected;
    state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[result.selected]);
    updateReferenceAddAvailability();
    renderPlaced(); updateSelectionButtons();
    await refreshPreview();
  } catch (error) {
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = friendlyError(error);
    $("#draft-status").classList.add("error");
  }
}