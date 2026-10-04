"use strict";

// Probe the same authoritative layout-expansion owner used for the final
// resize, with a cloned candidate. Until OK there is no draft/history/save or
// preview mutation; Cancel only restores the control's displayed value.
async function commitBoreAngleChange(event) {
  const input = event.currentTarget;
  if (state.draft?.kind !== "bore" || !state.design || state.boreAngleGrowthPending) return;
  const key = input.dataset.draft;
  const original = state.draft;
  const originalSnapshot = clone(original);
  const originalBox = clone(state.design.box);
  const candidate = clone(original);
  candidate.options ||= {};
  const previousValue = key === "option:angle"
    ? fmt(90 - number(original.options?.angle, 0))
    : original.options?.angle_towards || (original.along === "y" ? "front" : "left");
  const restoreField = () => { input.value = previousValue; };
  if (key === "option:angle") {
    const shown = Number(input.value);
    if (!input.value.trim() || !Number.isFinite(shown) || shown < 20 || shown > 90) {
      restoreField();
      toast("Bore angle must be between 20° and 90°.", true, 4500);
      return;
    }
    candidate.options.angle = 90 - shown;
    if (number(original.options?.angle, 0) <= 1e-9 && candidate.options.angle > 1e-9 &&
        !Object.prototype.hasOwnProperty.call(candidate.options, "angle_towards")) {
      candidate.options.angle_towards = boreDefaultAngleDirection(state.design);
    }
  } else {
    if (!["back", "front", "left", "right"].includes(input.value)) {
      restoreField();
      return;
    }
    candidate.options.angle_towards = input.value;
  }
  sizeBoreToGrid(candidate, { syncFields: false });
  const index = draftCommitIndex();
  if (index === false) { restoreField(); return; }
  const design = clone(state.design);
  const features = design.layout.features;
  if (index === null) features.push(candidate);
  else features[index] = candidate;
  const anchor = index === null ? features.length - 1 : index;
  const fit = boreXyMode(candidate) === "bin_to_bore";
  const epoch = state.boreEpoch || 0;
  const space = state.activeSpace, folderMode = state.folderMode;
  const inventoryId = state.designInventoryId;
  const current = () => state.draft === original && (state.boreEpoch || 0) === epoch &&
    state.activeSpace === space && state.folderMode === folderMode &&
    state.designInventoryId === inventoryId;
  state.boreAngleGrowthPending = true;
  try {
    const trial = await api("/api/layout/expand", { design, anchor, fit });
    if (!current()) return;
    const spaceError = aiSpaceViolation(trial.design, state.design);
    if (spaceError) {
      restoreField();
      toast("This angle does not fit in this Space.", true, 6000);
      return;
    }
    const growth = trial.box.x > state.design.box.x + 1e-6 ||
      trial.box.y > state.design.box.y + 1e-6;
    if (growth) {
      const accepted = await appConfirmAction({
        title: "Angled option will require a bigger bin. OK to size bin?",
        message: "The current angle or direction needs a larger bin footprint than it has. Wavefinity can grow the bin to the smallest size that fits.",
        actionLabel: "OK",
      });
      if (!current()) return;
      if (!accepted) { restoreField(); return; }
    }
    updateDraftFromFields({ currentTarget: input, target: input, type: "change" });
    if (growth) {
      refreshDraftSoon.cancel();
      const result = await autoExpandBin({ keepDraft: true, silent: true, fit });
      if (result !== "done") {
        toast("This angle does not fit in this Space.", true, 6000);
        state.draft = originalSnapshot;
        state.design.box = originalBox;
        renderDraftFields();
        renderPlaced();
        await refreshPreview();
      }
    }
  } catch (error) {
    if (current()) {
      restoreField();
      toast(error.message || "This angle cannot be fitted.", true, 6000);
    }
  } finally {
    state.boreAngleGrowthPending = false;
  }
}

function syncNest2DWorkspace() {
  const wrap = $('.canvas-wrap[data-canvas="2d"]');
  if (!wrap) return;

  const canvas = $("#preview-2d");
  const layoutControls = $(".layout-controls", wrap);
  const scanPanel = $("#nest-scan-controls");
  const recovery = $("#nest-corner-recovery");

  const isNest = state.draft?.kind === "nest";
  const recoveryActive =
    isNest
    && Array.isArray(state.nestPaperCorners)
    && Boolean(state.nestOriginalImage);
  // The dedicated outline editor owns the canvas only while the user has
  // explicitly entered it. A saved Photo Nest otherwise stays in Layout.
  const hasPhotoSession = isNest && !recoveryActive && Boolean(state.nestRectifiedImage);
  const editingOutline = isNest && !recoveryActive
    && state.nestOutlineEditing === true
    && (hasPhotoSession || Boolean(state.draft.contour?.length));
  const hasContour = editingOutline && Boolean(state.draft.contour?.length);
  if (wrap.classList.contains("active")) updatePreviewHelp("2d");

  recovery.hidden = !recoveryActive;
  canvas.hidden = recoveryActive;
  if (layoutControls) layoutControls.hidden = recoveryActive || editingOutline;
  wrap.classList.toggle("nest-scan-active", editingOutline);

  if (recoveryActive) {
    scanPanel.hidden = true;

    const image = $("#nest-corner-image");
    if (image.src !== state.nestOriginalImage.dataUrl) {
      image.src = state.nestOriginalImage.dataUrl;
    }

    const corners = state.nestPaperCorners;
    $("#nest-corner-count").textContent = state.nestCornerBusy
      ? "Checking selected corners…"
      : `${corners.length} of 4 corners selected`;

    const markers = $("#nest-corner-markers");
    markers.innerHTML = corners.map((corner, index) =>
      `<span class="nest-corner-marker" data-corner-index="${index}"></span>`).join("");
    $$(".nest-corner-marker", markers).forEach((marker, index) => {
      marker.style.left = `${corners[index].xPct}%`;
      marker.style.top = `${corners[index].yPct}%`;
    });
    renderNestPaperOutline(corners);

    $("#nest-corners-clear").disabled = state.nestCornerBusy;
    $("#nest-corner-error").textContent = state.nestCornerError || "";
    $("#nest-corner-tip").hidden = state.nestCornerTipDismissed || state.nestCornerBusy;
    return;
  }

  scanPanel.hidden = !editingOutline;

  if (!editingOutline) return;

  const photoControls = $("#nest-scan-photo-controls");
  if (photoControls) photoControls.hidden = !hasPhotoSession;

  if (hasPhotoSession) {
    const opacity = $("#nest-photo-opacity-range");
    const sensitivity = $("#nest-sensitivity-range");
    const cleanup = $("#nest-cleanup-range");

    opacity.value = String(state.nestPhotoOpacity);
    sensitivity.value = String(state.nestSensitivity);
    cleanup.value = String(state.nestCleanup);

    $("#nest-photo-opacity-value").textContent =
      `${Math.round(state.nestPhotoOpacity)}%`;
    $("#nest-sensitivity-value").textContent =
      String(Math.round(state.nestSensitivity));
    $("#nest-cleanup-value").textContent =
      String(Math.round(state.nestCleanup));
  }

  const softenInput = $("#nest-soften-input");
  if (softenInput && document.activeElement !== softenInput) {
    softenInput.value = fmt(number(state.draft.options?.smoothing, 0));
  }

  const outlineTools = $("#nest-outline-tools");
  if (outlineTools) outlineTools.hidden = !hasContour;
  $$('input[name="nest-outline-tool"]').forEach(input => {
    input.checked = input.value === state.nestOutlineTool;
  });

  const viewportTools = $("#nest-viewport-tools");
  if (viewportTools) viewportTools.hidden = !hasContour;

  $("#nest-scan-apply").disabled = !hasContour && !state.nestCandidateContour;
  $("#nest-scan-status").textContent = state.nestTuneStatus || "";
}

function renderNestPaperOutline(corners) {
  const outline = $("#nest-paper-outline");
  if (!outline) return;
  if (corners.length < 2) {
    outline.innerHTML = "";
    return;
  }
  if (corners.length === 2) {
    const points = corners.map(corner => `${corner.xPct},${corner.yPct}`).join(" ");
    outline.innerHTML = `<polyline points="${points}"></polyline>`;
    return;
  }
  if (corners.length === 3) {
    const sides = [];
    for (let a = 0; a < corners.length; a += 1) {
      for (let b = a + 1; b < corners.length; b += 1) {
        const dx = corners[a].xPct - corners[b].xPct;
        const dy = corners[a].yPct - corners[b].yPct;
        sides.push({ a, b, length: dx * dx + dy * dy });
      }
    }
    const outside = sides.sort((one, two) => one.length - two.length).slice(0, 2);
    outline.innerHTML = outside.map(side => {
      const a = corners[side.a], b = corners[side.b];
      return `<line x1="${a.xPct}" y1="${a.yPct}" x2="${b.xPct}" y2="${b.yPct}"></line>`;
    }).join("");
    return;
  }
  const center = corners.reduce((sum, corner) => ({
    xPct: sum.xPct + corner.xPct / corners.length,
    yPct: sum.yPct + corner.yPct / corners.length,
  }), { xPct: 0, yPct: 0 });
  const points = [...corners]
    .sort((one, two) => Math.atan2(one.yPct - center.yPct, one.xPct - center.xPct)
      - Math.atan2(two.yPct - center.yPct, two.xPct - center.xPct))
    .map(corner => `${corner.xPct},${corner.yPct}`).join(" ");
  outline.innerHTML = `<polygon points="${points}"></polygon>`;
}

function nestCornerPoint(event) {
  const image = $("#nest-corner-image");
  const rect = image.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    xPct: Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100)),
    yPct: Math.max(0, Math.min(100, (event.clientY - rect.top) / rect.height * 100)),
  };
}

function showNestCornerMagnifier(point) {
  const magnifier = $("#nest-corner-magnifier");
  const image = $("#nest-corner-image");
  if (!magnifier || !image || !state.nestOriginalImage) return;
  const rect = image.getBoundingClientRect();
  const size = 144;
  const border = 3;
  const zoom = 4;
  const lensCenter = (size - border * 2) / 2;
  const sourceX = point.xPct / 100 * rect.width;
  const sourceY = point.yPct / 100 * rect.height;
  magnifier.style.backgroundImage = `url("${state.nestOriginalImage.dataUrl}")`;
  magnifier.style.backgroundSize = `${rect.width * zoom}px ${rect.height * zoom}px`;
  magnifier.style.backgroundPosition =
    `${lensCenter - sourceX * zoom}px ${lensCenter - sourceY * zoom}px`;
  magnifier.style.left = `${Math.max(6, Math.min(rect.width - size - 6, point.xPct / 100 * rect.width + 18))}px`;
  magnifier.style.top = `${Math.max(6, Math.min(rect.height - size - 6, point.yPct / 100 * rect.height + 18))}px`;
  magnifier.hidden = false;
}

function hideNestCornerMagnifier() {
  const magnifier = $("#nest-corner-magnifier");
  if (magnifier) magnifier.hidden = true;
}

function beginNestCornerPointer(event, index = null) {
  if (state.nestCornerBusy || !Array.isArray(state.nestPaperCorners)) return;
  const point = nestCornerPoint(event);
  if (!point) return;
  event.preventDefault();
  nestCornerPointer = { id: event.pointerId, index, magnifying: false, point };
  nestCornerHoldTimer = setTimeout(() => {
    if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
    nestCornerPointer.magnifying = true;
    showNestCornerMagnifier(nestCornerPointer.point);
  }, 350);
}

function moveNestCornerPointer(event) {
  if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
  const point = nestCornerPoint(event);
  if (!point) return;
  nestCornerPointer.point = point;
  if (nestCornerPointer.index !== null) {
    state.nestPaperCorners[nestCornerPointer.index] = point;
    state.nestCornerError = "";
    syncNest2DWorkspace();
  }
  if (nestCornerPointer.magnifying) showNestCornerMagnifier(point);
}

function endNestCornerPointer(event, cancelled = false) {
  if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
  clearTimeout(nestCornerHoldTimer);
  const interaction = nestCornerPointer;
  nestCornerPointer = null;
  hideNestCornerMagnifier();
  if (cancelled) return;
  const point = nestCornerPoint(event);
  if (!point || !Array.isArray(state.nestPaperCorners)) return;
  if (interaction.index === null) state.nestPaperCorners.push(point);
  else state.nestPaperCorners[interaction.index] = point;
  if (state.nestPaperCorners.length >= 1) state.nestCornerTipDismissed = true;
  state.nestCornerError = "";
  syncNest2DWorkspace();
  if (state.nestPaperCorners.length === 4) {
    state.nestCornerBusy = true;
    syncNest2DWorkspace();
    void acceptNestPaperCorners();
  }
}

function wireNest2DControls() {
  $("#nest-photo-opacity-range")?.addEventListener("input", event => {
    state.nestPhotoOpacity = number(event.target.value, 45);
    syncNest2DWorkspace();
    renderLayout2D();
  });

  $("#nest-sensitivity-range")?.addEventListener("input", event => {
    state.nestSensitivity = number(event.target.value, 50);
    queueNestRetrace();
  });

  $("#nest-cleanup-range")?.addEventListener("input", event => {
    state.nestCleanup = number(event.target.value, 50);
    queueNestRetrace();
  });

  $("#nest-scan-defaults")?.addEventListener("click", () => {
    state.nestSensitivity = 50;
    state.nestCleanup = 50;
    queueNestRetrace("Restoring default scan settings…");
  });

  $("#nest-scan-apply")?.addEventListener("click", finishNestEditing);

  // Soften outline lives in this panel now, not the sidebar, so it cannot
  // use the generic data-draft wiring (scoped to #draft-fields) - commit it
  // directly, the same way other one-off nest fields already do.
  $("#nest-soften-input")?.addEventListener("input", event => {
    if (state.draft?.kind !== "nest") return;
    markDraftChanged();
    state.draft.options ||= {};
    const raw = event.target.value.trim();
    if (raw === "") delete state.draft.options.smoothing;
    else state.draft.options.smoothing = Math.max(0, number(raw, 0));
    state.draftAutoCommit = true;
    renderLayout2D();
    refreshDraftSoon();
  });

  $$('input[name="nest-outline-tool"]').forEach(input => input.addEventListener("change", () => {
    state.nestOutlineTool = input.value;
    renderLayout2D();
  }));

  $("#nest-reset-outline")?.addEventListener("click", resetNestOutline);

  $("#nest-zoom-in")?.addEventListener("click", () => nestZoomBy(1.4));
  $("#nest-zoom-out")?.addEventListener("click", () => nestZoomBy(1 / 1.4));
  $("#nest-zoom-fit")?.addEventListener("click", resetNestView);

  $("#preview-2d")?.addEventListener("wheel", event => {
    if (!isNestEditWorkspaceActive()) return;
    event.preventDefault();
    const point = canvasPointFromEvent(event.currentTarget, event);
    nestZoomBy(Math.exp(-event.deltaY * .001), point);
  }, { passive: false });

  $("#nest-corners-clear")?.addEventListener("click", () => {
    if (state.nestCornerBusy) return;
    state.nestPaperCorners = [];
    state.nestCornerError = "";
    hideNestCornerMagnifier();
    syncNest2DWorkspace();
  });

  $("#nest-corner-tip-close")?.addEventListener("click", () => {
    state.nestCornerTipDismissed = true;
    syncNest2DWorkspace();
  });

  $("#nest-corner-markers")?.addEventListener("pointerdown", event => {
    const marker = event.target.closest(".nest-corner-marker");
    if (!marker) return;
    event.stopPropagation();
    beginNestCornerPointer(event, Number(marker.dataset.cornerIndex));
  });

  $("#nest-corner-image")?.addEventListener("pointerdown", event => {
    if (!Array.isArray(state.nestPaperCorners)
        || state.nestPaperCorners.length >= 4
        || state.nestCornerBusy) {
      return;
    }
    beginNestCornerPointer(event);
  });

  window.addEventListener("pointermove", moveNestCornerPointer);
  window.addEventListener("pointerup", event => endNestCornerPointer(event));
  window.addEventListener("pointercancel", event => endNestCornerPointer(event, true));
}

function queueNestRetrace(status = "Retracing…") {
  // The visible sliders no longer describe the old candidate. Remove it at
  // once so Apply can never accept an outline from the previous settings
  // during the debounce or while the replacement is still being calculated.
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestTuneStatus = status;
  syncNest2DWorkspace();
  renderLayout2D();
  requestNestRetrace();
}

// Photo Nest's own sidebar buttons - separated out because they carry
// session-only state that no other feature kind touches.
function wireNestFieldActions() {
  const fields = $("#draft-fields");
  const pushOut = $('[data-draft="nest-push-out"]', fields);
  if (pushOut) pushOut.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    setNestPushOut(state.draft.options, pushOut.checked);
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  const cavityAuto = $('[data-action="nest-cavity-auto"]', fields);
  if (cavityAuto) cavityAuto.addEventListener("click", () => {
    markDraftChanged();
    state.draft.options ||= {};
    delete state.draft.options.cavity_depth;
    state.draft.options.cavity_depth_mode = "auto";
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  const editOutline = $('[data-action="edit-nest-outline"]', fields);
  if (editOutline) editOutline.addEventListener("click", () => {
    state.nestOutlineEditing = true;
    state.nestViewZoom = 1; state.nestViewPanX = 0; state.nestViewPanY = 0;
    activatePreviewView("2d"); syncNest2DWorkspace(); renderLayout2D();
  });
  const duplicate = $('[data-action="duplicate-nest"]', fields);
  if (duplicate) duplicate.addEventListener("click", duplicateNest);
}

async function duplicateNest() {
  if (!state.draft?.contour || !Number.isInteger(state.selected)) return;
  let previousDesign = null;
  let previousSelected = null;
  let mutationStarted = false;
  let committedDraft = false;
  try {
    committedDraft = await commitVisibleDraft({ previewAfterCommit: false });
    const index = state.selected;
    if (!Number.isInteger(index) || !state.design.layout.features[index] || !beginDesignMutation()) {
      if (committedDraft) refreshPreview();
      return;
    }
    mutationStarted = true;
    previousDesign = clone(state.design);
    previousSelected = index;
    const result = await api("/api/feature/duplicate", { design: state.design, index });
    state.design = result.design;
    noteCommittedDesignChange(previousDesign);
    resetNestPhotoSession();
    state.selected = result.selected;
    state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[result.selected]);
    state.draftKind = "nest"; state.draftIsNew = false; state.draftTouched = false;
    state.draftAutoCommit = true; state.nestOutlineEditing = false;
    syncForm(); renderDraftFields(); renderPlaced(); await refreshPreview();
    committedDraft = false;
    toast("Photo Nest duplicated.");
  } catch (error) {
    if (previousDesign && Number.isInteger(previousSelected)) {
      state.design = previousDesign;
      state.selected = previousSelected;
      state.draftSourceIndex = previousSelected;
      state.draft = clone(previousDesign.layout.features[previousSelected]);
      state.draftKind = "nest"; state.draftIsNew = false; state.draftTouched = false;
      state.draftAutoCommit = true; state.nestOutlineEditing = false;
      renderDraftFields(); renderPlaced(); await refreshPreview();
    }
    if (committedDraft && !previousDesign) refreshPreview();
    toast(error.message, true, 6500);
  } finally { if (mutationStarted) finishDesignMutation(); }
}

async function resetNestOutline() {
  const one = state.draft;
  const index = draftCommitIndex();
  if (!one || one.kind !== "nest" || !Number.isInteger(index)) return;
  const baseline = one.source_contour || one.contour;
  if (!baseline) return;
  state.nestCandidateContour = null;
  await commitNestContourEdit(index, baseline.map(point => [...point]));
}

// Debounced live retrace: segmentation + cleanup only, on the already-
// rectified reference sheet - paper detection never repeats per slider move.
// Every retrace re-centres its new contour around its own new bounding box
// (contour_to_millimetres always does this), so a candidate's own local
// origin can differ a little from the accepted outline's. Rather than
// swapping the displayed photo to match the candidate (which would make the
// still-visible accepted outline look wrong against it), translate the
// candidate into the accepted outline's own stable frame using both traces'
// trace_center_mm, so accepted outline, candidate outline and photo all sit
// in one consistent physical frame at once.
const requestNestRetrace = debounce(async () => {
  const rectified = state.nestRectifiedImage;
  const draft = state.draft;
  if (!rectified || !draft || draft.kind !== "nest") return;
  const request = ++state.nestRetraceRequest;
  state.nestTuneStatus = "Retracing…";
  syncNest2DWorkspace();
  try {
    const result = await api("/api/nest/retrace", {
      rectified_image: rectified.dataUrl,
      mime_type: rectified.mimeType,
      sensitivity: state.nestSensitivity,
      cleanup: state.nestCleanup,
    });
    if (request !== state.nestRetraceRequest || state.draft !== draft) return;
    const accepted = state.nestAcceptedCenterMm || [0, 0];
    const candidateCenter = result.trace_center_mm || accepted;
    const delta = [candidateCenter[0] - accepted[0], candidateCenter[1] - accepted[1]];
    state.nestCandidateContour = result.contour.map(([x, y]) => [x + delta[0], y + delta[1]]);
    state.nestCandidateCenterMm = candidateCenter;
    state.nestTuneStatus = `Candidate: ${fmt(result.outline.width)} × ${fmt(result.outline.depth)} mm — press Finish Editing to accept.`;
  } catch (error) {
    if (request !== state.nestRetraceRequest) return;
    // Failed retrace is non-destructive (spec section 34): keep the accepted
    // outline and its photo registration exactly as they were, and just
    // report why the candidate failed.
    state.nestCandidateContour = null;
    state.nestCandidateCenterMm = null;
    state.nestTuneStatus = `Could not retrace at this setting: ${error.message}`;
  }
  syncNest2DWorkspace();
  renderLayout2D();
}, 300);

// "Finish Editing": commit any pending scan-tuning candidate exactly as
// Apply always did, then - once a real nest feature exists to show - leave
// the dedicated outline editor and switch straight to the 3D view, which
// already highlights the selected part live (spec: "Nested 2D Outline
// Editing"). Still mid-trace (no Tool thickness yet)? There is nothing to
// build yet, so stay in 2D instead of jumping to an empty selection.
async function finishNestEditing() {
  const one = state.draft;
  if (!one || one.kind !== "nest") return;
  if (state.nestCandidateContour) await acceptNestTrace();
  if (!state.draft?.contour?.length) return;
  state.nestOutlineEditing = false;
  activatePreviewView("3d");
}

async function acceptNestTrace() {
  const one = state.draft;
  const index = draftCommitIndex();
  if (!one || one.kind !== "nest" || !state.nestCandidateContour) return;
  let candidate = state.nestCandidateContour.map(point => [...point]);
  const candidateCenter = state.nestCandidateCenterMm;
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestTuneStatus = "";
  if (!Number.isInteger(index)) {
    if (one.contour || !state.nestTraceResult) {
      // The part was placed (or the trace result vanished) in the moment
      // between retracing and pressing Apply - the edit above can no longer
      // land anywhere, so say so instead of silently dropping it.
      state.nestTuneStatus = "Could not apply the adjusted outline - please retrace.";
      renderLayout2D();
      return;
    }
    const pending = {
      contour: candidate,
      source_contour: null,
      zone: [-.5, -.5, .5, .5],
      rotation: 0,
      scale: 1,
    };
    normalizeNestContour(pending);
    candidate = pending.contour;
    const xs = candidate.map(point => point[0]);
    const ys = candidate.map(point => point[1]);
    state.nestTraceResult.contour = candidate;
    state.nestTraceResult.outline = {
      width: Math.max(...xs) - Math.min(...xs),
      depth: Math.max(...ys) - Math.min(...ys),
    };
    if (state.nestTraceResult.reference && state.nestPhoto?.bounds) {
      state.nestTraceResult.reference.bounds = [...state.nestPhoto.bounds];
    }
    if (candidateCenter) {
      state.nestTraceResult.trace_center_mm = candidateCenter;
      state.nestAcceptedCenterMm = candidateCenter;
    }
    state.nestTuneStatus = "Adjusted outline accepted.";
    syncNest2DWorkspace();
    renderLayout2D();
    await finishPhotoNestIfReady();
    return;
  }
  await commitNestContourEdit(index, candidate, { source_contour: candidate.map(point => [...point]) });
  // The committed contour re-centres around its own new bounding box
  // (normalizeNestContour, inside commitNestContourEdit) - which for an
  // already-self-centred raw candidate lands exactly back on the candidate's
  // own trace centre, so that becomes the new accepted stable-frame centre.
  if (candidateCenter) state.nestAcceptedCenterMm = candidateCenter;
  syncNest2DWorkspace();
}

// Runs the trace-only phase (spec section 1): paper detection/correction (or
// supplied corners), segmentation and contour extraction. Independent of any
// design - never touches Tool thickness, the bin, or Nest geometry. Whoever
// finishes last between this and Tool thickness triggers finalization.
async function runNestTrace(paperCorners) {
  const original = state.nestOriginalImage;
  const draft = state.draft;
  if (!original || !draft || draft.kind !== "nest") return;
  const request = ++state.nestTraceRequest;
  $("#draft-status").textContent = "Finding the reference sheet and tracing the part…";
  $("#draft-status").classList.remove("error");
  try {
    const result = await api("/api/nest/trace", {
      image: original.dataUrl,
      mime_type: original.mimeType,
      sensitivity: state.nestSensitivity,
      cleanup: state.nestCleanup,
      paper_corners: paperCorners,
    });
    if (request !== state.nestTraceRequest || state.draft !== draft) return;
    state.nestTraceResult = result;
    state.nestOutlineEditing = true;
    state.nestRectifiedImage = result.rectified_image
      ? { dataUrl: result.rectified_image, mimeType: "image/jpeg" } : state.nestRectifiedImage;
    state.nestPaperCorners = null;
    state.nestCornerError = "";
    state.nestCornerBusy = false;
    state.nestAcceptedCenterMm = result.trace_center_mm || null;
    setNestPhotoReference(result.reference);
    if (_nestMeasuredThickness(draft.options) == null) {
      $("#draft-status").textContent = "Photo traced — enter Tool thickness above to finish.";
    }
    renderDraftFields();
    activatePreviewView("2d");
    setLayoutOrientation("topup");
    syncNest2DWorkspace();
    renderLayout2D();
    await finishPhotoNestIfReady();
  } catch (error) {
    if (request !== state.nestTraceRequest) return;
    $("#draft-status").textContent = friendlyError(error);
    $("#draft-status").classList.add("error");
    if (paperCorners) {
      // The user supplied four corners but Python still rejected them.
      // Keep those points visible so they can clear/retry without re-uploading.
      state.nestCornerBusy = false;
      state.nestCornerError = error.message;
      syncNest2DWorkspace();
      toast(error.message, true, 6500);
    } else if (/paper missing|paper detection/i.test(error.message)) {
      state.nestPaperCorners = [];
      state.nestCornerBusy = false;
      state.nestCornerError = error.message;
      syncNest2DWorkspace();
      toast(
        "Automatic paper detection failed. Click the four paper corners in 2D.",
        true, 8500,
      );
    } else {
      toast(error.message, true, 6500);
    }
  }
}

// Whichever of tracing / Tool thickness finishes last calls this. Does
// nothing until both a completed trace and a measured Tool thickness exist;
// never decodes or retraces the photo itself (spec section 1).
async function finishPhotoNestIfReady() {
  const trace = state.nestTraceResult;
  const draft = state.draft;
  if (!trace || !draft || draft.kind !== "nest") return;
  if (_nestMeasuredThickness(draft.options) == null) return;
  if (!beginDesignMutation()) return;
  const previousDesign = clone(state.design);
  try {
    const payload = {
      design: state.design,
      contour: trace.contour,
      options: draft.options || {},
    };
    // Replacing an existing photo: send the live draft too, so a setting
    // changed since the last debounced save is not lost (spec section 7).
    if (draft.contour) {
      payload.feature = draft;
      payload.index = draftCommitIndex();
    }
    const result = await api("/api/nest/photo", payload);
    state.design = result.design;
    noteCommittedDesignChange(previousDesign);
    state.selected = result.selected;
    state.draftKind = "nest";
    state.draft = clone(state.design.layout.features[state.selected]);
    setNestPhotoReference(trace.reference);
    state.nestAcceptedCenterMm = trace.trace_center_mm || null;
    state.nestTraceResult = null;
    state.draftAutoCommit = true;
    state.drafts = {};
    syncForm();
    renderDraftFields();
    await refreshPreview();
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    $('.view-tab[data-view="2d"]').click();
    setLayoutOrientation("topup");
    toast(`Photo Nest ready: ${fmt(trace.outline.width)} × ${fmt(trace.outline.depth)} mm outline.`);
    for (const warning of result.warnings || []) toast(warning, false, 6500);
  } catch (error) {
    $("#draft-status").textContent = friendlyError(error);
    $("#draft-status").classList.add("error");
    toast(error.message, true, 6500);
  } finally {
    finishDesignMutation();
  }
}

async function acceptNestPaperCorners() {
  const original = state.nestOriginalImage;
  const corners = state.nestPaperCorners;

  if (!original || !Array.isArray(corners) || corners.length !== 4) return;

  const img = new Image();
  img.src = original.dataUrl;
  await (img.decode ? img.decode().catch(() => {}) : Promise.resolve());

  const width = img.naturalWidth || 1;
  const height = img.naturalHeight || 1;

  const paperCorners = corners.map(corner => [
    corner.xPct / 100 * width,
    corner.yPct / 100 * height,
  ]);

  state.nestCornerError = "";
  state.nestCornerBusy = true;
  syncNest2DWorkspace();
  await runNestTrace(paperCorners);
}

// A divider builds from its thickness option, not from the footprint drawn
// below - widen that footprint to match so what the Width/Depth fields and
// the 2D layout show never falls short of the real wall. Which side is
// "across" follows the explicit Runs-along choice, not a guess from
// whichever of width/depth is currently bigger. Round the wall's thickness up
// to the 1 mm grid first, so the pipeline's nearest-line snap can't leave the
// footprint a hair under the wall (same trap sizeCradleToItem sidesteps).
function widenDividerFootprint(one) {
  const t = Math.ceil(one.options.thickness);
  if (!Number.isFinite(t) || t <= 0) return;
  const zw = one.zone[2] - one.zone[0], zd = one.zone[3] - one.zone[1];
  const cx = (one.zone[0] + one.zone[2]) / 2, cy = (one.zone[1] + one.zone[3]) / 2;
  const wideningKey = one.along === "x" ? "depth" : "width";
  if (one.along === "x") {
    const depth = Math.max(zd, t);
    one.zone = [one.zone[0], cy - depth / 2, one.zone[2], cy + depth / 2];
  } else {
    const width = Math.max(zw, t);
    one.zone = [cx - width / 2, one.zone[1], cx + width / 2, one.zone[3]];
  }
  const shownField = $(`[data-draft="${wideningKey}"]`, $("#draft-fields"));
  if (shownField) {
    const newSpan = wideningKey === "width"
      ? one.zone[2] - one.zone[0]
      : one.zone[3] - one.zone[1];
    if (shownField.value !== fmt(newSpan)) {
      shownField.value = fmt(newSpan);
      flashField(shownField);
    }
  }
}

// Keep a cradle's footprint hugging what it actually holds, so the Width/Depth
// fields and the 2D layout never disagree with the built ribs.
//
//   run axis (the tool lies along it): tool length, except Alternate ends uses
//     the whole available run so troughs can sit 10% in from opposite sides.
//   across axis (lanes sit side by side on it): a set Quantity hugs to exactly
//     that many lanes; Quantity = auto spans the whole bin so the engine's
//     "fit as many as will fit" has room to work - otherwise a 1-lane zone
//     boxes it in and auto can only ever place one.
//
// Every dimension is rounded UP to the 1 mm editor grid: the design pipeline
// snaps a zone to the nearest grid line, and rounding a 16.4 mm need down to
// 16 mm builds a cradle the engine then rejects. Both axes are also clamped to
// the usable floor so an over-long tool yields the engine's specific "40 mm
// long but the zone only runs 39 mm" message instead of a generic overflow.
function sizeCradleToItem(one) {
  const item = one.item;
  if (!item?.segments?.length) return;
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const spacing = Math.max(0, number(one.options?.spacing, state.draftResolvedOptions?.spacing ?? 0));
  const length = item.segments.reduce((total, segment) => total + number(segment.length), 0);
  // The true tool diameter (no fit slack) and a wall a quarter of it, floored at
  // the thinnest printable wall and capped so a fat handle never grows a slab.
  // Mirrors _cradle_wall in organizer_inserts.py.
  const diameter = Math.max(...item.segments.map(segment => number(segment.diameter)));
  const rib = Math.min(Math.max(diameter * 0.25, 1.6), 6);
  const auto = one.count == null;
  const count = auto ? 1 : one.count;
  // Auto Quantity may become multiple lanes, so it also uses the end-to-end
  // layout whenever Alternate ends is on.
  const alternating = one.alternate_ends === true && (auto || count > 1);
  // A non-alternating cradle hugs its tool until "Offset from center" is set;
  // then it needs the whole run so the trough has room to slide within it.
  const offset = alternating ? 0 : number(one.options?.run_offset, 0);
  const spansRun = alternating || Math.abs(offset) > 1e-9;

  const [insideX, insideY] = binInsideExtent(state.design.box);
  const roomAlong = one.along === "x" ? insideX : insideY;
  const roomAcross = one.along === "x" ? insideY : insideX;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curRun = one.along === "x" ? curW : curD;
  const curAcross = one.along === "x" ? curD : curW;
  const runKey = one.along === "x" ? "width" : "depth";
  const acrossKey = one.along === "x" ? "depth" : "width";

  const oneLane = diameter + rib;
  const pitch = diameter + rib / 2 + spacing;
  const endMargin = Math.min(.45, Math.max(0,
    number(one.options?.end_margin, state.draftResolvedOptions?.end_margin ?? 10) / 100));
  const minimumRun = Math.max(1, Math.ceil(
    alternating ? length / (1 - 2 * endMargin) : length,
  ));
  const minimumAcross = Math.max(1, Math.ceil(oneLane + (count - 1) * pitch));
  const wantedRun = spansRun ? Math.max(roomAlong, minimumRun) : minimumRun;
  const wantedAcross = auto ? roomAcross : minimumAcross;
  // A hand-sized axis is a floor, never a target to overwrite. Requirements
  // may still grow it. Do not clamp a required footprint to the current bin;
  // the bin grower needs the real size in order to make enough room.
  const run = state.pinnedZone[runKey] ? Math.max(curRun, minimumRun) : wantedRun;
  const across = state.pinnedZone[acrossKey]
    ? Math.max(curAcross, auto ? oneLane : minimumAcross)
    : wantedAcross;

  const width = one.along === "x" ? run : across;
  const depth = one.along === "x" ? across : run;
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
}

// Keep a bore's Base (the drilled block) exactly big enough for its hole grid,
// so the Width / Length fields and the 2D layout never disagree with what the
// engine builds - and so raising a count, widening a hole, or leaning the grid
// grows the block on its own instead of throwing "reaches outside the bin".
//
// Mirrors feature_min_footprint()'s bore branch in organizer_inserts/_layout.py:
// pitch is (hole + wall), the block runs columns x pitch by rows x pitch, and a
// leaned grid adds along its lean axis the sideways "reach" the slanting hole
// bottoms travel. The block grows AND shrinks to that minimum on its own; when
// it now needs more floor than the bin has, refreshDraft()'s catch grows the
// bin around it. A pinned axis (see state.pinnedZone) only ever grows to the
// minimum - a hand-set Base size is never shrunk back. An axis left on "auto"
// count still keeps room for at least one hole so the fitter always has
// something to divide.
// Persisted Bore sizing modes (options xy_size_mode / height_size_mode). Mirrors
// normalize_bore_modes() in organizer_inserts/_bore.py: retired state is dropped,
// Base "bore to bin" owns the zone (the whole usable floor, never a pin or a
// minimum grid), and Height "bore to bin" owns its number by leaving it unset so
// the engine derives it. Returns true when "bore to bin" placed the zone.
function applyBoreSizing(one, { syncState = true } = {}) {
  if (one?.kind !== "bore") return false;
  const opts = one.options ||= {};
  const style = normalizeBoreStyle(opts.bore_style, opts.wall_style);
  for (const retired of ["auto_base", "auto_height", "auto_grid", "wall_style"]) delete opts[retired];
  opts.bore_style = style;
  opts.xy_size_mode = boreXyMode(one);
  opts.height_size_mode = boreHeightMode(one);
  if (style !== "base_straight") {
    delete opts.angle;
    delete opts.angle_towards;
  }
  if (!boreWallsOnly(style)) delete opts.wall;   // Base styles use internal defaults
  if (opts.height_size_mode === "bore_to_bin") delete opts.height;
  if (opts.xy_size_mode === "bin_to_bore" && boreWallsOnly(style)) {
    // Mirrors normalize_bore_modes(): a bin-sized Walls Only Bore is centred.
    const halfW = (one.zone[2] - one.zone[0]) / 2;
    const halfD = (one.zone[3] - one.zone[1]) / 2;
    one.zone = [-halfW, -halfD, halfW, halfD];
    return false;
  }
  if (opts.xy_size_mode !== "bore_to_bin" || boreWallsOnly(style)) return false;
  const [insideX, insideY] = binInsideExtent(state.design.box);
  one.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  if (syncState) {
    delete state.pinnedZone.width;
    delete state.pinnedZone.depth;
  }
  return true;
}

// Mirrors bore_minimum_pitches() in organizer_inserts/_bore.py. Axis-aligned
// square holes (square_axis) pitch at held + wall; other polygons use the
// circumscribed radius.
function boreCrossPitch(profile, held, wall) {
  if (profile === "square_axis") return held + wall;
  const sides = profile === "round" ? 48 : profile === "square" ? 4 : 6;
  const holeRadius = held / 2 / (sides < 8 ? Math.cos(Math.PI / sides) : 1);
  return 2 * holeRadius + wall;
}

function sizeBoreToGrid(one, { syncFields = true } = {}) {
  if (one.kind !== "bore") return;
  // "Auto size bore to bin" fills the bin whatever the grid needs. Every other
  // Base grows to its grid; a Walls Only Bore, or one whose bin is sized around
  // it, always sits exactly at its minimum footprint.
  const opts = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  if (applyBoreSizing(one, { syncState: syncFields })) return;
  const profile = one.item?.profile || "round";
  const hexBit = isHexBitProfile(profile);
  const diameter = hexBit
    ? HEX_BIT_PROFILES[profile].diameter
    : number(one.item?.segments?.[0]?.diameter, 6);
  const held = diameter + 0.25;
  const boreStyle = boreStyleOf(one);
  const walls = boreWallsOnly(boreStyle);
  // Both Walls Only styles and Base - Wavy Walls stand upright and size to their
  // wavy/straight sleeves' outer envelope.
  const wallOnly = boreStyle !== "base_straight";
  const exactSize = walls || boreXyMode(one) === "bin_to_bore";
  const angle = hexBit || wallOnly ? 0 : Math.min(70, Math.max(0, number(opts.angle ?? resolved.angle, 0)));
  // A leaned bore defaults to a thicker wall (engine: BORE_TILTED_WALL) unless
  // Wall was hand-set - match that so the block sizing tracks the real pitch.
  // Wall Only takes the current bin wall instead (engine: bore_defaults).
  const wall = opts.wall !== undefined ? number(opts.wall)
    : wallOnly ? number(state.design?.box?.wall, 0.8)
    : (angle > 0 ? 3 : 1.6);
  const crossPitch = boreCrossPitch(profile, held, wall);
  const leanPitch = crossPitch / Math.cos(angle * Math.PI / 180);
  if (!(crossPitch > 0) || !(leanPitch > 0)) return;

  const holeDepth = number(opts.depth ?? resolved.depth, 0);
  const reach = angle > 0 ? holeDepth * Math.sin(angle * Math.PI / 180) : 0;
  const angleTowards = opts.angle_towards;
  const along = ["left", "right"].includes(angleTowards) ? "x"
    : ["front", "back"].includes(angleTowards) ? "y"
    : one.along === "y" ? "y" : "x";

  // A leaned bore's angled tools sweep past the block toward `angle_towards`,
  // right up to the bin rim (see bore_tool_clearance_zone in
  // organizer_inserts/_bore.py). Bias the block away from that wall by half the
  // tool's overhang so the tools stay balanced in the bin and it never has to
  // grow just to let a slanting tool clear one side.
  const leanSign = angleTowards === "right" || angleTowards === "back" ? 1 : -1;
  const box = state.design.box;
  const baseZ = number(box.base_thickness, 0.6) +
    (state.design.layout.mode === "fused" ? 0 : 0.6);
  const boreHeight = number(opts.height ?? resolved.height, holeDepth + 2);
  const riseToRim = number(box.z, 0) - (baseZ + boreHeight);
  const toolOverhang = angle > 0 && riseToRim > 0
    ? riseToRim * Math.tan(angle * Math.PI / 180) : 0;

  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const [insideX, insideY] = binInsideExtent(state.design.box);
  // Wall Only mirrors wall_only_envelope() in organizer_inserts/_bore.py: the
  // footprint is the sleeves' true outer envelope, wave included.
  const wallRules = state.catalog?.wall_rules || {};
  const amplitude = number(wallRules.wave_amplitude_mm ?? state.catalog?.wave_amplitude_mm, 0.4);
  const depthFactor = number(wallRules.wall_depth_factor ?? state.catalog?.wall_depth_factor, 1.181);
  const waveNoiseFloor = 1e-4;  // ensure wavy troughs never self-intersect
  const wavy = boreWavy(boreStyle);
  const shellReach = wavy ? 2 * amplitude + wall * depthFactor + waveNoiseFloor : wall;
  const clearSpan = (axis) => {
    if (profile === "round") {
      // Conservative round clear span: a 256-sided circumscribed polygon.
      // Backend uses >= 256 sides for all Wavy sampling, so this is safe.
      return held / Math.cos(Math.PI / 256);
    }
    if (profile === "square_axis") return held;
    const sides = profile === "square" ? 4 : 6;
    const circum = held / Math.cos(Math.PI / sides);   // corner-to-corner
    return sides === 4 || axis === "x" ? circum : held;
  };
  // Mirrors WALL_ONLY_FOOT in _bore.py: the strengthening foot reaches this far
  // past the sleeve on each outside side. Walls Only only - never Base - Wavy.
  const wallOnlyFoot = walls ? 0.5 : 0;
  const axisSpan = (count, axis) => {
    if (wallOnly) {
      return Math.ceil(clearSpan(axis) + 2 * shellReach + 2 * wallOnlyFoot + (count - 1) * crossPitch - 1e-6);
    }
    const pitch = along === axis ? leanPitch : crossPitch;
    return Math.ceil(count * pitch + (along === axis ? reach : 0) - 1e-6);
  };
  // An unset quantity means one hole, not “fill the existing Base.” Changing
  // X/Y, hole diameter, Wall, depth, or lean grows the Base to its exact need.
  const resolveAxis = (countKey, cur, pinKey, leanAxis) => {
    const count = Math.max(1, Math.round(number(opts[countKey] ?? resolved[countKey], 1)));
    const minimum = axisSpan(count, leanAxis);
    // Walls Only and "bin to bore" always take their exact minimum; a manual Base
    // that has been pinned only ever grows.
    return state.pinnedZone[pinKey] && !exactSize ? Math.max(cur, minimum) : minimum;
  };
  const width = resolveAxis("columns", curW, "width", "x");
  const depth = resolveAxis("rows", curD, "depth", "y");
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;

  // Stay where the block already sits when it still fits; once an axis outgrows
  // the bin, keep it on its old centre and let the bin grow around it.
  const place = (centre, span, inside) => {
    if (span >= inside) return centre;
    const half = span / 2;
    return Math.min(Math.max(centre, -inside / 2 + half), inside / 2 - half);
  };
  // Push the block off the wall its tools lean toward - never back toward it,
  // so a hand-placed bore that already sits clear is left where it is.
  const leanTarget = (centre, axis) => {
    if (toolOverhang <= 0 || along !== axis) return centre;
    const bias = -leanSign * toolOverhang / 2;
    return leanSign < 0 ? Math.max(centre, bias) : Math.min(centre, bias);
  };
  // A Walls Only Bore that sizes the bin around itself stays centred.
  const centred = walls && boreXyMode(one) === "bin_to_bore";
  const ncx = centred ? 0 : place(leanTarget(cx, "x"), width, insideX);
  const ncy = centred ? 0 : place(leanTarget(cy, "y"), depth, insideY);
  one.zone = [ncx - width / 2, ncy - depth / 2, ncx + width / 2, ncy + depth / 2];

  if (!syncFields) return;
  const widthField = $('[data-draft="width"]', $("#draft-fields"));
  if (widthField && Math.abs(width - curW) >= 0.05) { widthField.value = fmt(width); flashField(widthField); }
  const depthField = $('[data-draft="depth"]', $("#draft-fields"));
  if (depthField && Math.abs(depth - curD) >= 0.05) { depthField.value = fmt(depth); flashField(depthField); }
}

// The peg-row twin of sizeBoreToGrid. feature_min_footprint()'s post branch:
// the run axis carries count pegs of `diameter` with `spacing` gaps between;
// the across axis only needs one `diameter`. Count on "auto" is left for the
// fitter. Only the run axis is resized - the across axis is whatever the user
// drew (grown if a fat peg now needs more). A pinned run axis only grows.
function sizePostToRow(one) {
  if (one.kind !== "post" || one.count == null) return;
  const resolved = state.draftResolvedOptions || {};
  const opts = one.options || {};
  const diameter = number(opts.diameter ?? resolved.diameter, 12);
  const spacing = Math.max(0, number(opts.spacing ?? resolved.spacing, 4));
  const count = Math.max(1, Math.round(one.count));
  if (!(diameter > 0)) return;
  const runNeeded = Math.ceil(count * diameter + (count - 1) * spacing - 1e-6);
  const acrossNeeded = Math.ceil(diameter - 1e-6);
  const along = one.along === "y" ? "y" : "x";
  const runKey = along === "x" ? "width" : "depth";
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curRun = along === "x" ? curW : curD;
  const curAcross = along === "x" ? curD : curW;
  const run = state.pinnedZone[runKey] ? Math.max(curRun, runNeeded) : runNeeded;
  const across = Math.max(curAcross, acrossNeeded);
  const width = along === "x" ? run : across;
  const depth = along === "x" ? across : run;
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;
  applyResizedZone(one, cx, cy, width, depth);
}

// The slot-bank twin. feature_min_footprint()'s slot branch: pitch is
// (thickness + wall) / cos(angle); the across axis holds count of them plus a
// half-slot and a wall each end; the run axis is left as drawn (slots span it
// minus walls). Count on "auto" is the fitter's. A pinned across axis only
// grows.
function sizeSlotToBank(one) {
  if (one.kind !== "slot" || one.count == null) return;
  const resolved = state.draftResolvedOptions || {};
  const opts = one.options || {};
  const thickness = number(opts.thickness ?? resolved.thickness, 4);
  const wall = number(opts.wall ?? resolved.wall, 1.6);
  const angle = Math.min(45, Math.abs(number(opts.angle ?? resolved.angle, 20)));
  const cosA = Math.cos(angle * Math.PI / 180);
  if (!(thickness > 0) || !(wall > 0) || !(cosA > 0)) return;
  const count = Math.max(1, Math.round(one.count));
  const pitch = (thickness + wall) / cosA;
  const amplitude = number(state.catalog?.wall_rules?.wave_amplitude_mm, 0.4);
  const waveReach = (opts.wall_style ?? resolved.wall_style) === "wavy" ? 2 * amplitude : 0;
  const acrossNeeded = Math.ceil((count - 1) * pitch + thickness / cosA + 2 * wall + waveReach - 1e-6);
  const along = one.along === "y" ? "y" : "x";
  const acrossKey = along === "x" ? "depth" : "width";
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curAcross = along === "x" ? curD : curW;
  const curRun = along === "x" ? curW : curD;
  const across = state.pinnedZone[acrossKey] ? Math.max(curAcross, acrossNeeded) : acrossNeeded;
  const width = along === "x" ? curRun : across;
  const depth = along === "x" ? across : curRun;
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;
  applyResizedZone(one, cx, cy, width, depth);
}

// Set one.zone to width x depth about (cx, cy), nudged back inside the bin when
// it still fits, and push the matching Width / Length fields. Shared by the
// post / slot sizers (the bore sizer inlines the same steps).
function applyResizedZone(one, cx, cy, width, depth) {
  const prevW = one.zone[2] - one.zone[0];
  const prevD = one.zone[3] - one.zone[1];
  const [insideX, insideY] = binInsideExtent(state.design.box);
  const place = (centre, span, inside) => {
    if (span >= inside) return centre;
    const half = span / 2;
    return Math.min(Math.max(centre, -inside / 2 + half), inside / 2 - half);
  };
  const ncx = place(cx, width, insideX);
  const ncy = place(cy, depth, insideY);
  one.zone = [ncx - width / 2, ncy - depth / 2, ncx + width / 2, ncy + depth / 2];
  const widthField = $('[data-draft="width"]', $("#draft-fields"));
  if (widthField && Math.abs(width - prevW) >= 0.05) { widthField.value = fmt(width); flashField(widthField); }
  const depthField = $('[data-draft="depth"]', $("#draft-fields"));
  if (depthField && Math.abs(depth - prevD) >= 0.05) { depthField.value = fmt(depth); flashField(depthField); }
}

// A manual Width, Length, or layout edit turns Automatic footprint sizing off
// for any Photo Nest in the design - it never silently fights a footprint the
// user just typed. Height is independent: it never triggers this, and never
// gets turned off by it. Only the new explicit "true" is affected; a legacy
// design with no stored preference keeps its historical grow-only behaviour,
// and an already-Manual Nest is already what this asks for.
function turnOffNestAutoSizeForManualEdit() {
  const candidates = [];
  if (state.draft?.kind === "nest") candidates.push(state.draft);
  for (const feature of state.design?.layout?.features || []) {
    if (feature.kind === "nest" && feature !== state.draft) candidates.push(feature);
  }
  let turnedOff = false;
  for (const one of candidates) {
    one.options ||= {};
    if (one.options.auto_size === true) {
      one.options.auto_size = false;
      turnedOff = true;
    }
  }
  if (turnedOff) {
    toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
    if (state.draft?.kind === "nest") renderDraftFields();
  }
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The selected photo could not be read."));
    reader.readAsDataURL(file);
  });
}

function setNestPhotoReference(reference) {
  if (!reference?.image || !Array.isArray(reference.bounds) || reference.bounds.length !== 4) {
    state.nestPhoto = null;
    return;
  }
  const image = new Image();
  const photo = { image, bounds: reference.bounds.map(value => number(value)) };
  state.nestPhoto = photo;
  image.addEventListener("load", renderLayout2D, { once: true });
  image.addEventListener("error", () => {
    if (state.nestPhoto === photo) state.nestPhoto = null;
  }, { once: true });
  image.src = reference.image;
}

function _nestMeasuredThickness(options) {
  const raw = options?.tool_thickness ?? options?.depth;
  const value = number(raw, NaN);
  return Number.isFinite(value) && value > 0 ? value : null;
}

async function uploadNestPhoto(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const input = event.target;
  input.value = "";
  const uploadRequest = ++state.nestTraceRequest;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const mimeByExtension = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp" };
  const mimeType = file.type || mimeByExtension[extension];
  if (!mimeType || !["image/jpeg", "image/png", "image/webp"].includes(mimeType)) {
    toast("Choose a JPG, JPEG, PNG, or WEBP photo.", true, 5000);
    return;
  }
  if (file.size > 17_000_000) {
    toast("The photo must be smaller than 17 MB.", true, 5000);
    return;
  }
  let image;
  try {
    image = await readFileDataUrl(file);
  } catch (error) {
    toast(error.message, true, 5000);
    return;
  }
  if (uploadRequest !== state.nestTraceRequest
      || state.draft?.kind !== "nest" || state.draftKind !== "nest") return;
  $('.view-tab[data-view="2d"]')?.click();
  setLayoutOrientation("topup");
  // Choosing a photo starts analysis immediately - Tool thickness is a
  // separate field the user can fill in while it runs (spec section 1).
  // Whichever finishes last triggers finalization (finishPhotoNestIfReady).
  resetNestPhotoSession();
  state.nestOriginalImage = { dataUrl: image, mimeType };
  renderDraftFields();
  await runNestTrace();
}

function markDraftChanged(referenceOnly = false) {
  const keepReferenceResolution = referenceOnly &&
    state.referenceResolutionRequest === state.draftRequest;
  if (!referenceOnly) {
    commitReferenceEditSoon.cancel();
    state.referenceEditPending = false;
  }
  // Invalidate an auto-save immediately, at the moment the user changes the
  // visible draft. Waiting for the debounced rebuild leaves a short window in
  // which the older response can replace the newer edit.
  state.draftTouched = true;
  state.draftRequest += 1;
  if (keepReferenceResolution) state.referenceResolutionRequest = state.draftRequest;
  updateReferenceAddAvailability();
  state.canGenerate = false;
  updateGenerateAvailability();
}

// Pocket, Bore and Slot all need a solid floor below their cut. The field the
// user is editing owns the decision; adjust its counterpart once, without
// dispatching another input event or allowing an A -> B -> A update loop.
function keepCutBelowHeight(one, changedKey, gap = 2) {
  if (!one || !["pocket", "bore", "slot"].includes(one.kind) ||
      !["depth", "height"].includes(changedKey)) return;
  // A Bore Base cavity may be exactly as deep as the Bore is tall - it then
  // reaches the normal bin floor - so it needs no raised floor. Walls Only has
  // no hole depth at all. Pocket and Slot keep their 2 mm floor.
  if (one.kind === "bore") {
    if (boreWallsOnly(boreStyleOf(one))) return;
    gap = 0;
  }
  if (changedKey === "depth") {
    const depth = number(one.options.depth, 0);
    const height = number(
      one.options.height ?? state.draftResolvedOptions?.height, depth + gap,
    );
    if (depth > 0 && height < depth + gap) {
      one.options.height = depth + gap;
      const field = $('[data-draft="option:height"]', $("#draft-fields"));
      if (field) { field.value = fmt(one.options.height); flashField(field); }
    }
    return;
  }
  const height = number(one.options.height, 0);
  const depth = number(one.options.depth ?? state.draftResolvedOptions?.depth, 0);
  if (height > gap && depth >= height - gap) {
    one.options.depth = Math.max(0.1, height - gap);
    const field = $('[data-draft="option:depth"]', $("#draft-fields"));
    if (field) { field.value = fmt(one.options.depth); flashField(field); }
  }
}