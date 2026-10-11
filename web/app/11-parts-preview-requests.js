"use strict";

// Done flushes the latest valid edit, then exits editing. Persistence belongs
// to auto-add/auto-save; this action never appends a second copy.
async function saveCurrentPart() {
  if (state.modifierEditing) return saveModifierPart();
  commitReferenceEditSoon.cancel();
  const badReference = $('#draft-fields [data-reference-axis]:invalid');
  if (badReference) { badReference.reportValidity(); return; }
  if (!state.draft || !beginDesignMutation()) return;
  // An incomplete Photo Nest (no traced cavity outline yet) has nothing legal
  // to commit. Save must not silently discard it - stay in the editor with
  // the same actionable status refreshDraft() already shows; Delete remains
  // the explicit way to abandon it.
  if (state.draft.kind === "nest" && !state.draft.contour) {
    finishDesignMutation();
    $("#draft-status").textContent = "Upload one part photo to create the cavity outline before finishing.";
    $("#draft-status").classList.add("error");
    return;
  }
  let committed = false;
  try {
    committed = await commitVisibleDraft({ previewAfterCommit: false });
    state.paletteBrowsing = true;
    clearDraftSelection();
    renderPlaced();
    await refreshPreview();
    committed = false;
  } catch (error) {
    if (committed) await refreshPreview();
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
}

async function saveModifierPart() {
  const kind = state.modifierEditing;
  if (!kind) return;
  if (!beginDesignMutation()) return;
  try {
    if (!flushModifierForm()) return;
    if (kind === "edge_mount" && !state.design?.box?.edge_mount?.label_enabled &&
        !state.design?.box?.edge_mount?.holes_enabled) {
      throw new Error("Choose a Label or turn on Screw Mounting first.");
    }
    const result = await api("/api/design/validate", { design: state.design });
    state.design = result.design;
    state.paletteBrowsing = true;
    clearDraftSelection();
    renderPlaced();
    await refreshPreview();
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
}

// "Delete Part": drop the part currently being edited - a placed one is
// removed from the design, a brand-new draft is just discarded - then return
// to the 10-part palette.
async function deleteCurrentPart() {
  if (state.modifierEditing) return removeModifier(state.modifierEditing);
  if (!state.draft) return;
  const deletingNest = state.draft.kind === "nest";
  const index = draftCommitIndex();
  state.paletteBrowsing = true;
  if (Number.isInteger(index)) {
    await deleteSupportAt(index);
    return;
  }
  // Never committed - nothing on the server to delete.
  if (deletingNest) resetNestPhotoSession();
  clearDraftSelection();
  renderPlaced();
  refreshPreview();
}

async function deleteEdgeMountPart(fromPlaced = false) {
  return removeModifier("edge_mount");
}

async function deleteSupportAt(index) {
  if (index === null || index === undefined) return;
  const target = state.design.layout.features[index];
  if (!target) return;
  if (target.kind === "divider" && dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  // Deleting a part other than the one open in the editor can throw away an
  // unsaved edit underneath it - route through the same guard used to switch
  // parts so that edit is saved (or the user confirms losing it) first.
  const switchGuard = state.draft && draftCommitIndex() !== index
    ? await deferredDraftSwitch() : null;
  try {
  if (switchGuard && !switchGuard.proceed) return;
  if (!beginDesignMutation()) return;
  const deletingNest = state.design.layout.features[index]?.kind === "nest";
  let deleted = false;
  try {
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/delete", { design: state.design, index });
    state.design = result.design;
    if (deletingNest) resetNestPhotoSession();
    noteCommittedDesignChange(previousDesign);
    state.selected = null;
    clearDraftSelection();
    renderPlaced();
    refreshPreview();
    toast("Interior part deleted.");
    deleted = true;
  } catch (error) {
    toast(error.message, true);
  } finally {
    finishDesignMutation();
  }
  } finally {
    switchGuard?.finish();
  }
}

function mutationControls() {
  return $$(
    '#x-size, #y-size, #z, #base-thickness, #wall-thickness, #part-name, ' +
    '#lift-grabber-size, #lift-grabber-location, #connector-height-mode, ' +
    '#mode-select, ' +
    '#lid-option-toggle, #lid-configuration, #lid-thickness, #lid-fit, #lid-handle-type, #lid-handle-size, ' +
    '#lid-handle-position, #lid-label-enabled, #lid-label-orientation, #lid-label-style, #lid-label-depth, #lid-label-text, ' +
    '#designer-new-bin, #designer-duplicate, #ai-help-open, ' +
    '#designer-save-file, #designer-open-file'
  );
}

function setMutationSurfacesInert(inert) {
  [$('header'), $('.controls')].forEach(surface => {
    if (surface) surface.inert = inert;
  });
}

function beginDesignMutation() {
  if (relocationBlocksWrites()) return false;
  if (state.designMutationBusy) {
    toast("Finish the current design change first.", true);
    return false;
  }

  const beforeForm = clone(pendingDesignHistory || state.design);
  const previousCanGenerate = state.canGenerate;

  // Flush/cancel the debounced ordinary path, but do not cancel unrelated
  // draft work until we know the live modifier form is allowed to commit.
  cancelChangedDesignDebounce();
  pendingDesignHistory = null;

  if (!applyLiveFormWithModifierConflictGuard(beforeForm, previousCanGenerate)) {
    return false;
  }

  // The mutation is now allowed to own a new design snapshot. Pending draft
  // work calculated against the old snapshot must not land afterward.
  cancelPendingDraftWork();
  noteCommittedDesignChange(beforeForm);
  state.designMutationBusy = true;
  setMutationSurfacesInert(true);
  mutationControls().forEach(control => control.disabled = true);
  updateSelectionButtons();
  updateGenerateAvailability();
  return true;
}

function finishDesignMutation() {
  state.designMutationBusy = false;
  flushBoreReconcile();
  setMutationSurfacesInert(false);
  mutationControls().forEach(control => control.disabled = false);
  syncLidForm();
  updateSelectionButtons();
  updateGenerateAvailability();
}

function updateSelectionButtons() {
  const busy = state.designMutationBusy;
  // The editor being open IS "editing mode" - set synchronously the moment a
  // part is picked, before its defaults have loaded. Browse state shows the
  // palette; edit state hides it while "Already added to this bin" stays visible.
  const editing = !$(".support-editor").hidden;
  $("#support-palette").hidden = editing;
  const hasPlaced = placedPartCount() > 0;
  $$(".placed-block").forEach(placedBlock => { placedBlock.hidden = !hasPlaced; });
  const lockedDivider = state.draft?.kind === "divider" && dividerLockedByLidLabels();
  $$(".placed-item-remove, #active-option-delete").forEach(button => {
    const index = Number(button.dataset.index);
    const target = Number.isInteger(index) ? state.design?.layout?.features?.[index] : null;
    button.disabled = busy || (target?.kind === "divider" && lockedDivider);
  });
  const hasPhotoNest = state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour);
  $$(".support-choice").forEach(button => {
    const info = partInfo(button.dataset.kind);
    const isModifier = info?.capabilities?.includes("box_modifier");
    const count = partInstanceCount(button.dataset.kind);
    const alreadyAdded = count > 0;
    const active = button.classList.contains("active");
    // Storage Box designs keep the Divider tile live; every other tile is
    // visibly unavailable while the design is a Storage Box (Fix 111).
    const b4bDisallowed = b4bEnabled() && !b4bPartAllowed(button.dataset.kind);
    button.disabled = busy || (hasPhotoNest && !isModifier) || b4bDisallowed;
    button.classList.toggle("added", alreadyAdded && !active);
    // "Editing"/"Setting up" are edit-state cues, not duplicate presence
    // counts - an already-present, non-editing tile shows no state label at
    // all; the green "added" border alone is the presence cue.
    button.classList.toggle("has-state", active);
    const stateLabel = $(".support-choice-state", button);
    if (stateLabel) {
      stateLabel.hidden = !active;
      const settingUpNest = active && button.dataset.kind === "nest" &&
        state.draft?.kind === "nest" && !state.draft.contour;
      stateLabel.textContent = settingUpNest ? "Setting up" : active ? "Editing" : "";
    }
    // The title is derived from current state on every refresh. That prevents
    // a Storage Box-only disabled reason from leaking into the next ordinary
    // design after the tile becomes enabled again.
    if (b4bDisallowed) {
      button.title = `${info?.title || button.dataset.kind} — ${B4B_PARTS_ONLY_DIVIDER_MESSAGE}`;
    } else if (isModifier) {
      button.title = alreadyAdded
        ? `${info.title} already added. Select it to edit.`
        : `${info.title} — ${info.description}`;
    } else {
      button.title = `${info.title} — ${info.description}`;
    }
  });
}

function updateDraftStatusColor(hasError) {
  const editor = $(".support-editor");
  editor?.classList.toggle("status-valid", hasError === false);
  editor?.classList.toggle("status-error", hasError === true);
  $$(".support-choice").forEach(button => {
    const active = button.classList.contains("active");
    button.classList.toggle("status-valid", active && hasError === false);
    button.classList.toggle("status-error", active && hasError === true);
  });
}

function placedRowData() {
  // Fix 1011: exactly one row may carry the "Currently editing" badge.
  // state.modifierEditing is a single value (never a set), and while a
  // modifier editor is open no feature row is editing - the draft panel is
  // hidden. This makes zero-or-one structural, not dependent on every
  // transition clearing every flag.
  const editingModifier = state.modifierEditing;
  const editingFeatureIndex = state.draft && !editingModifier
    ? (Number.isInteger(draftCommitIndex()) ? draftCommitIndex() : state.draftSourceIndex)
    : null;
  const modifierDetail = kind => {
    const box = state.design.box || {};
    if (kind === "lid_stacking") {
      return !box.lid?.enabled ? "Stackable bin on bin"
        : box.lid.stackable ? "Stackable bin on lid" : "Lid with handle";
    }
    if (kind === "inside_handles") {
      return `${box.lift_grabbers?.size || "medium"} · ${box.lift_grabbers?.location || "sides"}`;
    }
    if (kind === "side_openings") return (box.side_openings?.sides || []).join(" + ");
    const edge = box.edge_mount || {};
    const detail = edge.label_enabled && edge.holes_enabled
      ? "Label + Screws" : edge.label_enabled ? "Label" : "Screws";
    return `${edge.side || "front"} · ${detail}`;
  };
  const invalid = new Set(state.preview?.invalid_feature_indexes || []);
  const rows = state.design.layout.features.map((one, index) => {
    const width = one.zone[2] - one.zone[0];
    const depth = one.zone[3] - one.zone[1];
    const isRim = one.kind === "text" && one.options?.level === "rim";
    return {
      type: "feature", index, kind: one.kind,
      title: isRim ? "Label (Rim Level)" : partInfo(one.kind)?.title || one.kind,
      detail: isRim ? one.options?.text || "Rim label" : `${fmt(width)} × ${fmt(depth)} mm`,
      editing: index === editingFeatureIndex,
      selected: index === state.selected,
      invalid: invalid.has(index),
    };
  });
  for (const kind of BOX_MODIFIER_KINDS) {
    if (!modifierIsActive(kind) && state.modifierEditing !== kind) continue;
    rows.push({
      type: "modifier", kind,
      title: partInfo(kind)?.title || kind,
      detail: modifierIsActive(kind) ? modifierDetail(kind) : "Setting up",
      editing: state.modifierEditing === kind,
      selected: state.modifierEditing === kind,
      invalid: false,
    });
  }
  // A newly chosen draft (e.g. Photo Nest setup) has no saved feature yet:
  // show it as one temporary selected row so Done / Delete stay reachable.
  // Presentation only - nothing is persisted for it.
  if (state.draft && !Number.isInteger(draftCommitIndex()) && !Number.isInteger(state.draftSourceIndex)) {
    rows.push({
      type: "draft", kind: state.draft.kind,
      title: partInfo(state.draft.kind)?.title || state.draft.kind,
      detail: "Setting up",
      editing: true, selected: true, invalid: false,
    });
  }
  return rows;
}

function placedRowsMarkup(rows, { actions = false } = {}) {
  return rows.map(row => {
    const statusClass = row.invalid ? "status-error" : row.selected ? "status-valid" : "";
    const identity = row.type === "feature"
      ? `data-index="${row.index}"`
      : row.type === "modifier" ? `data-kind="${row.kind}"` : 'data-draft="true"';
    const title = escapeHtml(row.title);
    // Fix 082 L2: the row currently open for editing renders in the active
    // option row above, not here - every row this list ever shows is an
    // inactive sibling, so it always shows Edit, never Done.
    const rowActions = actions
      ? `<div class="placed-item-actions">
        <button type="button" class="placed-item-edit button secondary" ${identity} aria-label="Edit ${title}">Edit</button>
        <button type="button" class="placed-item-remove button danger" ${identity} title="Delete ${title}" aria-label="Delete ${title}">Delete</button>
      </div>` : "";
    return `<div class="placed-item ${row.selected ? "selected" : ""} ${statusClass}" data-support-kind="${escapeHtml(row.kind)}">
      <div class="placed-item-content">
        <span class="placed-item-icon">${iconFor(row.kind)}</span>
        <span class="placed-item-copy">
          <strong>${title}</strong>
          <span class="placed-item-detail">${escapeHtml(row.detail)}</span>
          ${row.editing ? '<span class="placed-editing-status">Currently editing</span>' : ""}
        </span>
      </div>
      ${rowActions}
    </div>`;
  }).join("");
}

function wirePlacedRows(container) {
  if (!container) return;
  $$(".placed-item[data-support-kind]", container).forEach(row => {
    row.style.setProperty("--support-color", kindColor(row.dataset.supportKind));
  });
  // The whole option card opens the option for editing; the Edit button is
  // only the visible affordance. Clicks on the row's own action buttons
  // (Edit/Delete) keep their own handlers: a synthesized Edit click bubbles
  // from inside .placed-item-actions, which this listener ignores, so it
  // never double-fires.
  $$(".placed-item[data-support-kind]", container).forEach(row => {
    row.addEventListener("click", event => {
      if (event.target.closest?.(".placed-item-actions")) return;
      row.querySelector(".placed-item-edit")?.click();
    });
  });
  $$(".placed-item-edit[data-index]", container).forEach(button => button.addEventListener("click", async () => {
    const index = Number(button.dataset.index);
    if (Number.isInteger(index) && index === draftCommitIndex()) return;
    await selectedFeature(index);
  }));
  $$(".placed-item-edit[data-kind]", container).forEach(button =>
    button.addEventListener("click", () => {
      if (state.modifierEditing === button.dataset.kind) return;
      openModifier(button.dataset.kind, true);
    }));
  $$(".placed-item-edit[data-draft]", container).forEach(button => button.addEventListener("click", () => {
    if (state.draft) selectKind(state.draft.kind);
  }));
  $$(".placed-item-remove[data-index]", container).forEach(button => button.addEventListener("click", async () => {
    await deleteSupportAt(Number(button.dataset.index));
  }));
  $$(".placed-item-remove[data-kind]", container).forEach(button => button.addEventListener("click", async () => {
    await removeModifier(button.dataset.kind);
  }));
  $$(".placed-item-remove[data-draft]", container).forEach(button => button.addEventListener("click", deleteCurrentPart));
}

// Fix 082 L2: the option currently open for editing shows once, above its
// own settings, with its identity and the one Done action (plus Delete, so
// abandoning an in-progress part loses no capability the combined list used
// to give it). "Options in this bin" below never repeats this row.
function renderActiveOptionRow(row) {
  const container = $("#active-option-row");
  if (!container) return;
  if (!row) { container.hidden = true; return; }
  container.hidden = false;
  const title = $("#active-option-title");
  if (title) title.textContent = row.title;
  const deleteBtn = $("#active-option-delete");
  if (deleteBtn) {
    if (row.type === "feature") deleteBtn.dataset.index = String(row.index);
    else delete deleteBtn.dataset.index;
    if (row.type === "modifier") deleteBtn.dataset.kind = row.kind;
    else delete deleteBtn.dataset.kind;
  }
}

function renderPlaced() {
  if (!state.design) return;
  const rows = placedRowData();
  const activeRow = rows.find(row => row.editing) || null;
  renderActiveOptionRow(activeRow);
  const added = $("#added-parts-list");
  if (added) {
    added.innerHTML = placedRowsMarkup(rows, { actions: true }) ||
      '<div class="placed-empty">Nothing added yet.</div>';
    wirePlacedRows(added);
  }
  const total = placedPartCount();

  updateSelectionButtons();
  updateDividerEditBreadcrumb();
}

function clearPreviewWaitTimers() {
  if (previewWaitTimer !== null) clearTimeout(previewWaitTimer);
  if (previewSlowTimer !== null) clearTimeout(previewSlowTimer);
  previewWaitTimer = null;
  previewSlowTimer = null;
}

// Explicit invalidation of the visible "recalculating" state, for when the
// in-flight request is intentionally no longer current (e.g. a Space/folder
// switch) rather than having completed normally. clearPreviewWaitTimers()
// alone only cancels timeouts - it does not hide #preview-wait or remove
// .preview-recalculating, so a switch mid-build could otherwise leave a
// stale overlay showing in the newly active Space (Fix 032 Correction 4,
// C4.3 - clearPreviewWaitTimers() was believed to already do this).
// endPreviewWait(requestId) remains request-guarded for ordinary preview
// completion; this helper is unconditional on purpose.
function cancelPreviewWait() {
  clearPreviewWaitTimers();
  const wrapper = $('[data-canvas="3d"]');
  const notice = $("#preview-wait");
  if (notice) notice.hidden = true;
  if (wrapper) wrapper.classList.remove("preview-recalculating");
}

function invalidatePendingPreview() {
  state.previewRequest += 1;
  cancelPreviewWait();
}

function beginPreviewWait(requestId) {
  clearPreviewWaitTimers();
  const wrapper = $('[data-canvas="3d"]');
  const notice = $("#preview-wait");
  const text = $("#preview-wait-text");
  if (!wrapper || !notice || !text) return;

  // Keep an already-visible notice up across edits while the newest preview
  // replaces the old one; only restart its wording and slow-build timer.
  if (!notice.hidden) text.textContent = "Updating design…";
  previewWaitTimer = setTimeout(() => {
    if (requestId !== state.previewRequest) return;
    notice.hidden = false;
    wrapper.classList.add("preview-recalculating");
    previewWaitTimer = null;
  }, 175);
  previewSlowTimer = setTimeout(() => {
    if (requestId !== state.previewRequest) return;
    notice.hidden = false;
    wrapper.classList.add("preview-recalculating");
    text.textContent = "Rebuilding geometry…";
    previewSlowTimer = null;
  }, 1500);
}

function endPreviewWait(requestId) {
  if (requestId !== state.previewRequest) return;
  clearPreviewWaitTimers();
  const wrapper = $('[data-canvas="3d"]');
  const notice = $("#preview-wait");
  if (notice) notice.hidden = true;
  if (wrapper) wrapper.classList.remove("preview-recalculating");
}

// Everything a finished, current preview does to the browser: geometry and pick
// data, fit/error state, generation availability, the canonical design, the
// preview currentness key, checkpoints/autosave and every render. refreshPreview()
// calls it for its own result, and AI Help calls it for a candidate it already
// proved, so an accepted design never costs a second identical geometry build.
function adoptPreviewResult(result, { persistResume = true, lidEpochAtRequest = state.lidThicknessEpoch } = {}) {
  const grownX = result.design?.box?.x !== state.design?.box?.x;
  const grownY = result.design?.box?.y !== state.design?.box?.y;
  const grownZ = result.design?.box?.z !== state.design?.box?.z;
  state.preview = result;
  state.design = result.design;
  // Bind the three backend-measured lid thicknesses to the design and edit
  // epoch they were measured for; a later bin or a newer edit never shows them.
  applyLidThicknessReport(result, lidEpochAtRequest);
  syncSurfaceControls();
  state.previewDesignKey = JSON.stringify(result.design);
  updateDraftOverhangNote();
  checkBinSizeChange();
  // Surface the access planner's own warning (spec section 46) once per
  // distinct message, not on every preview refresh.
  const accessWarning = (result.draft_nest_access || result.nest_access?.[state.selected])?.warning;
  if (accessWarning && accessWarning !== state.nestAccessWarningShown) {
    toast(accessWarning, true, 6500);
  }
  state.nestAccessWarningShown = accessWarning || null;
  const rimLabelWarning = result.label_meta?.warning || null;
  if (rimLabelWarning && rimLabelWarning !== state.rimLabelWarningShown) {
    toast(rimLabelWarning, false, 6500);
  }
  state.rimLabelWarningShown = rimLabelWarning;
  // A B4B preview returns its effective printable dimensions. Adopt them
  // into the controls and flash every field the engine adjusted.
  if (grownX) flashField($("#x-size"));
  if (grownY) flashField($("#y-size"));
  if (grownZ) flashField($("#z"));
  const previewHasErrors = !result.fits || result.feature_errors.length || result.draft_error;
  // Fix 078: the overlay's primary message follows a deterministic priority -
  // result.message, then the first feature error, then the draft error, then
  // a generic fallback. Only the latest preview request may set it.
  setDesignInvalidOverlay(previewHasErrors
    ? (result.message || result.feature_errors[0] || result.draft_error
      || "The current settings cannot build a valid design.")
    : "");
  $("#preview-state").textContent = previewHasErrors ? "Design needs attention" : "";
  $("#preview-state").classList.toggle("status-error", Boolean(previewHasErrors));
  $("#preview-state").classList.remove("status-ok");
  formatDimField("x");
  formatDimField("y");
  formatHeightField();
  // The backend may have grown X/Y. Their displayed values now match the
  // accepted report, so an unrelated next edit must not look like a size edit.
  if (lidEpochAtRequest === state.lidThicknessEpoch) settleLidThicknessFormKey();
  const physical = result.base_trim?.outer_mm || [state.design.box.x, state.design.box.y];
  $(".dimension-width", $("#dimensions")).textContent = `Width ${fmt(physical[0])} mm`;
  $(".dimension-depth", $("#dimensions")).textContent = `Depth ${fmt(physical[1])} mm`;
  $(".dimension-height", $("#dimensions")).textContent = `Height ${fmt(state.design.box.z)} mm`;
  // A typed Space's exact resume checkpoint (Fix 032): only a fully valid
  // preview - never one that merely returned HTTP 200 while still
  // reporting fit/feature/draft errors - replaces the last valid one.
  // Placed after the controls above so the checkpoint is the same canonical
  // design the user now sees, including any server-adjusted X/Y/Z.
  if (!previewHasErrors && typedSpaceOrdinaryBin()) {
    if (state.spaceStarterPreviewPending) {
      state.cleanDesign = clone(state.design);
      state.spaceStarterPreviewPending = false;
    } else queueSpaceDesignAutosave();
  }
  if (persistResume && !previewHasErrors && state.folderMode === "space" && typeof SP !== "undefined") {
    SP.queueResumeCheckpoint(state.design, false);
  }
  const messages = [result.message, ...result.feature_errors, result.draft_error].filter(Boolean);
  const actions = [];
  result.feature_errors.forEach((message, errorIndex) => {
    const featureIndex = result.invalid_feature_indexes?.[errorIndex];
    actions.push({
      message: featureIndex === undefined ? message : `Interior part ${featureIndex + 1}: ${message}`,
      activate: async () => {
        if (featureIndex === undefined) return;
        await selectedFeature(featureIndex);
        if (state.selected !== featureIndex) return;
        $(".support-editor").scrollIntoView({ behavior: "smooth", block: "center" });
        flashField($(".support-editor"));
      },
    });
  });
  if (result.draft_error) actions.push({
    message: result.draft_error,
    activate: () => {
      $(".support-editor").scrollIntoView({ behavior: "smooth", block: "center" });
      const invalidField = $('#draft-fields input:invalid') || $('#draft-fields input');
      invalidField?.focus();
      flashField(invalidField || $(".support-editor"));
    },
  });
  state.canGenerate = !messages.length;
  updateGenerateAvailability();
  if (actions.length) setError("", actions);
  state.textMeta = result.text_meta || [];
  updateBoreCeilingWarning(result.bore_ceiling_warning);
  updateStorageBoxHeightWarning(result.storage_box_height_warning);
  state.fitError = Boolean(result.feature_errors.length || result.draft_error);
  updateDraftStatusColor(state.draft ? Boolean(result.draft_error) : null);
  updateAutoExpandButton();
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) {
    SP.renderSpaceInfo();
  }
  applyStackVisibility();
  renderPreview3D();
  renderLayout2D();
  renderPlaced();
}

function updateBoreCeilingWarning(warning) {
  const element = $("#bore-ceiling-warning");
  if (!element) return;
  element.hidden = !warning;
  element.textContent = warning
    ? `Object reaches ${fmt(warning.top_mm)} mm; this ${warning.space_kind === "drawer" || warning.space_kind === "storage_drawers" ? "Drawer" : "Storage Box"} is ${fmt(warning.cap_mm)} mm high. The object may not fit when closed.`
    : "";
}

function updateStorageBoxHeightWarning(warning) {
  const element = $("#storage-box-height-warning");
  if (!element) return;
  element.hidden = !warning;
  element.textContent = !warning ? "" : warning.kind === "two_bins"
    ? `Two of these bins would stack to ${fmt(warning.height_mm)} mm; this Storage Box has ${fmt(warning.cap_mm)} mm of usable closed height.`
    : `This bin is ${fmt(warning.height_mm)} mm tall; this Storage Box has ${fmt(warning.cap_mm)} mm of usable closed height. It may not fit when the lid is closed.`;
}

// `persistResume: false` (Fix 032 Correction 4, C4.2) renders a normal,
// fully valid preview WITHOUT queuing it as the Space's resume checkpoint.
// Used only for the one narrow starter preview that replaces a stored
// resume design that just failed canonical validation - that starter is
// otherwise indistinguishable from any other valid preview and would
// silently overwrite the bad checkpoint the original contract says must be
// left alone for possible recovery. Every ordinary call (the ordinary
// default) persists exactly as before.
async function refreshPreview({ persistResume = true } = {}) {
  // Fix 103: the structural target owns its own preview (refreshStructuralPreview);
  // an ordinary design must never preview or checkpoint under it.
  if (typeof designTargetIsStructural === "function" && designTargetIsStructural()) return;
  fullPreviewStarts += 1;
  const request = ++state.previewRequest;
  const lidEpochAtRequest = state.lidThicknessEpoch;
  if (state.folderMode !== "space" || !["drawer", "portable", "box"].includes(state.activeSpace?.kind)) {
    updateBoreCeilingWarning(null);
    updateStorageBoxHeightWarning(null);
  }
  beginPreviewWait(request);
  state.canGenerate = false;
  updateGenerateAvailability();
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) {
    SP.renderSpaceInfo();
  }
  $("#preview-state").textContent = "Building preview…";
  $("#preview-state").classList.remove("status-ok", "status-error");
  setError();
  setDesignInvalidOverlay();
  try {
    // Storage Drawers: the bore-ceiling cap is the active drawer's usable
    // closed height (cabinetActiveLimits), never the cabinet's compatibility
    // total. The server reads this same space for _capped_bore_warning and
    // _ai_space_cap_violation, so both are fixed by the one payload.
    const previewSpace = state.folderMode === "space" && state.activeSpace?.kind === "storage_drawers"
      ? { ...state.activeSpace, ...cabinetActiveLimits() }
      : (state.folderMode === "space" ? state.activeSpace : null);
    const payload = { design: state.design, client_id: previewClientId, generation: request,
      space: previewSpace };
    if (state.draft && !(state.draft.kind === "nest" && !state.draft.contour)) {
      payload.draft = state.draft;
      // A draft opened from a placed part replaces that part for preview
      // validation. Without its index, the server sees the saved bore and its
      // live draft as two separate bores and reports a false self-overlap.
      const draftIndex = draftCommitIndex();
      if (Number.isInteger(draftIndex)) payload.selected = draftIndex;
    }
    const result = await api("/api/preview", payload);
    if (request !== state.previewRequest) return;
    if (result.superseded) throw new Error("Current preview was unexpectedly superseded. Try again.");
    endPreviewWait(request);
    adoptPreviewResult(result, { persistResume, lidEpochAtRequest });
  } catch (error) {
    if (request !== state.previewRequest) return;
    endPreviewWait(request);
    clearLidThicknessReport();
    $("#preview-state").textContent = "Preview could not build";
    $("#preview-state").classList.remove("status-ok");
    $("#preview-state").classList.add("status-error");
    setDesignInvalidOverlay(error.message);
    setError(error.message);
    state.canGenerate = false;
    updateGenerateAvailability();
    // A hard preview failure with supports present is usually a footprint that
    // outgrew the bin - offer the expand button and let the endpoint judge.
    state.fitError = true;
    updateAutoExpandButton();
  }
}

// Kept as the single hook the preview/draft paths call whenever the fit state
// moves; the top-of-section button it once toggled is gone - the per-part
// "Grow the bin" button below replaces it.
function updateAutoExpandButton() {
  updateFitActions();
}

// Bore and Slot Rack keep their Base snug around their selected quantities and
// grow the bin when needed, so they do not need manual Fit or Fill shortcuts.
// Pocket and Steps have no contents from which to derive one. The Post
// "Fit to pegs" button was removed per Andrew (2026-10-09, Q5: remove it).
const FILL_PART_KINDS = new Set(["pocket", "steps"]);

function renderFitActions(one) {
  const kind = one.kind;
  const rows = [];
  if (FILL_PART_KINDS.has(kind)) {
    rows.push(`<button type="button" class="button" data-action="fill-part" hidden>Fill the bin</button>`);
  }
  if (kind !== "scoop") {
    const label = kind === "nest" ? "Fit footprint to tool" : "Grow the bin";
    rows.push(`<button type="button" class="button" data-action="grow-bin" hidden>${label}</button>`);
  }
  if (!rows.length) return "";
  return `<div class="fit-actions">${rows.join("")}</div>`;
}

function updateFitActions() {
  const container = $(".fit-actions", $("#draft-fields"));
  if (!container || !state.draft) return;
  const fitBtn = $('[data-action="fit-part"]', container);
  const fillBtn = $('[data-action="fill-part"]', container);
  const growBtn = $('[data-action="grow-bin"]', container);
  // "Fit to …" is always available for its kinds - it grows the part when the
  // zone was drawn too small and shrinks it when there is slack.
  if (fitBtn) fitBtn.hidden = false;
  // "Grow the bin" only makes sense while something does not fit.
  if (growBtn) growBtn.hidden = !state.fitError;
  if (fillBtn) {
    const [insideX, insideY] = binInsideExtent(state.design.box);
    const z = state.draft.zone;
    const alreadyFull = Math.abs((z[2] - z[0]) - insideX) < 0.5
      && Math.abs((z[3] - z[1]) - insideY) < 0.5;
    fillBtn.hidden = alreadyFull;
  }
}

async function fitPartToContents() {
  if (!state.draft) return;
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const request = ++state.fitRequest;
  try {
    const result = await api("/api/feature/fit", {
      design: state.design, feature: draft,
    });
    // Do not apply a completed fit to a different part, or over an edit made
    // while the calculation was in flight.
    if (request !== state.fitRequest || state.draft !== draft ||
        JSON.stringify(draft) !== snapshot) return;
    const zone = roundFitZoneUpHalfMm(result.feature.zone);
    const unchanged = state.draft.zone.every((v, i) => Math.abs(v - zone[i]) < 0.05);
    markDraftChanged();
    state.draft.zone = zone;
    renderDraftFields();
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
    if (unchanged) toast("Already a snug fit — nothing to trim.");
  } catch (error) {
    toast(error.message, true, 5000);
  }
}

function fillPartToBin() {
  if (!state.draft) return;
  markDraftChanged();
  const [insideX, insideY] = binInsideExtent(state.design.box);
  state.draft.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  pinDraftAxis("width");
  pinDraftAxis("depth");
  if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
  renderDraftFields();
  state.draftAutoCommit = true;
  updateSelectionButtons();
  refreshDraftSoon();
}

// Persistent "Auto size bin to bore" (Width / Length and Height). The server says
// what bin the Bore asks for (result.bore_bin / result.bore_bin_height); when the
// bin is not already there this runs the exact resize through the one existing
// expand endpoint.
//   * One identity (state.boreEpoch + Space/design/selection ids) is captured up
//     front and re-proved before EVERY async resize result is applied and before
//     a second resize starts, so an answer for an older edit, Bore or design is
//     ignored.
//   * If another design mutation owns the design the request is kept pending and
//     retried by flushBoreReconcile() when that owner finishes - never dropped.
//   * A failed or interrupted attempt is never remembered as done, so the same
//     desired fit can retry; only a converged pass records boreFitDone, which just
//     skips repeat calls while another part holds the bin larger.
// Returns true when it resized, so the caller stops instead of saving a stale
// preview.
function boreReconcileContext() {
  return JSON.stringify([state.folderMode, state.activeSpaceId || null,
    state.designInventoryId || null, draftCommitIndex()]);
}

function bumpBoreEpoch() {
  state.boreEpoch = (state.boreEpoch || 0) + 1;
}

function flushBoreReconcile() {
  const pending = state.boreFitPending;
  if (!pending || state.autoGrowingBin || state.designMutationBusy) return;
  state.boreFitPending = null;
  if (state.draft?.kind === "bore" && state.draftAutoCommit
      && pending === boreReconcileContext()) {
    setTimeout(() => { if (state.draft?.kind === "bore") refreshDraft(); }, 0);
  }
}

async function reconcileBoreBin(result) {
  const draft = state.draft;
  if (draft?.kind !== "bore" || !state.draftAutoCommit) return false;
  const box = state.design.box;
  const wantXY = boreXyMode(draft) === "bin_to_bore" ? result?.bore_bin : null;
  const wantZ = boreHeightMode(draft) === "bin_to_bore" ? number(result?.bore_bin_height, NaN) : NaN;
  const xyOff = !!wantXY && (Math.abs(number(box.x) - number(wantXY.x)) > 1e-6
    || Math.abs(number(box.y) - number(wantXY.y)) > 1e-6);
  const zOff = Number.isFinite(wantZ) && Math.abs(number(box.z) - wantZ) > 1e-6;
  if (!xyOff && !zOff) return false;
  const fitKey = () => JSON.stringify([boreReconcileContext(), state.design.box.x,
    state.design.box.y, state.design.box.z, wantXY, wantZ, state.draft?.zone,
    state.draft?.options, state.draft?.item]);
  if (state.boreFitDone === fitKey()) return false;
  const context = boreReconcileContext();
  if (state.autoGrowingBin || state.designMutationBusy) {
    state.boreFitPending = context;
    return false;
  }
  const token = state.boreEpoch || 0;
  const isCurrent = () => (state.boreEpoch || 0) === token
    && boreReconcileContext() === context && state.draft?.kind === "bore";
  state.autoGrowingBin = true;
  let converged = true;
  try {
    if (zOff) converged = (await sizeBinHeightToBore({ silent: true, guard: isCurrent })) === "done";
    if (converged && xyOff && isCurrent()) {
      converged = (await autoExpandBin({
        keepDraft: true, silent: true, fit: true, guard: isCurrent })) === "done";
    }
  } finally {
    state.autoGrowingBin = false;
  }
  if (converged && isCurrent()) state.boreFitDone = fitKey();
  flushBoreReconcile();
  return true;
}

function activeSpaceMaximumBinHeight() {
  if (state.folderMode !== "space" || !state.activeSpace) return undefined;
  if (!["drawer", "portable", "box", "storage_drawers"].includes(state.activeSpace.kind)) return undefined;
  const maximum = number(
    state.activeSpace.kind === "storage_drawers" ? cabinetActiveLimits().z : state.activeSpace.z, NaN);
  return Number.isFinite(maximum) ? maximum : undefined;
}

async function sizeBinHeightToBore({ button = null, silent = false, guard = null } = {}) {
  if (state.draft?.kind !== "bore") return "skipped";
  const draftIndex = draftCommitIndex();
  if (!Number.isInteger(draftIndex)) {
    if (!silent) toast("Select the bore again before sizing the bin height.", true, 5000);
    return "skipped";
  }
  if (!beginDesignMutation()) return "skipped";
  if (button) button.disabled = true;
  try {
    const previousDesign = clone(state.design);
    const features = state.design.layout.features.map(
      (feature, index) => index === draftIndex ? state.draft : feature,
    );
    const design = {
      ...state.design,
      layout: { ...state.design.layout, features },
    };
    const result = await api("/api/layout/expand", {
      design,
      anchor: draftIndex,
      fit_height_to_bore: true,
      max_height: activeSpaceMaximumBinHeight(),
    });
    if (guard && !guard()) return "stale";
    state.design = result.design;
    if (result.changed) noteCommittedDesignChange(previousDesign);
    state.selected = draftIndex;
    state.draftSourceIndex = draftIndex;
    state.draftIsNew = false;
    state.draftTouched = false;
    state.draft = clone(state.design.layout.features[draftIndex]);
    state.draftResolvedOptions = {};
    syncForm();
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshPreview();
    if (result.changed) flashField($("#z"));
    return "done";
  } catch (error) {
    if (silent) {
      $("#draft-status").textContent = friendlyError(error);
      $("#draft-status").classList.add("error");
    } else {
      toast(error.message, true, 5000);
    }
    return "failed";
  } finally {
    if (button) button.disabled = false;
    finishDesignMutation();
  }
}

// Grow (or, with fit, shrink-or-grow to the smallest fit) the bin to hold
// every interior part. Options:
//   keepDraft - stay in the editor on the same part instead of closing it
//   silent    - no toast
//   fit       - smallest legal footprint instead of only growing
//   button    - the button element to disable while the request runs
//   guard     - returns false once the request that asked for this is stale; the
//               result is then ignored instead of becoming the design
// Returns "done", "failed", "skipped" (nothing was started) or "stale".
async function autoExpandBin({ keepDraft = false, silent = false, fit = false, button = null, guard = null } = {}) {
  const opts = { keepDraft, silent };
  const draftIndex = state.draft ? draftCommitIndex() : null;
  if (draftIndex === false) {
    if (!opts.silent) toast("Select the interior part again before growing the bin.", true);
    return "skipped";
  }
  if (!beginDesignMutation()) return "skipped";
  if (button) button.disabled = true;
  try {
    // Grow for what the user is actually looking at: an open draft may hold
    // edits (a flipped direction, a raised count) that never committed because
    // they don't fit yet. Fold it in - appended if new, in place if it's the
    // selected support being edited.
    const layout = state.design.layout;
    let features = layout.features;
    if (state.draft) {
      features = draftIndex === null
        ? [...layout.features, state.draft]
        : layout.features.map((f, i) => i === draftIndex ? state.draft : f);
    }
    const design = features === layout.features
      ? state.design
      : { ...state.design, layout: { ...layout, features } };
    // Name the part being edited so the server slides the *others* apart around
    // it, not it around them.
    const anchorIndex = draftIndex === null ? features.length - 1 : draftIndex;
    const anchor = features === layout.features ? undefined : anchorIndex;
    const previousDesign = clone(state.design);
    const previousBox = { ...state.design.box };
    const result = await api("/api/layout/expand", {
      design,
      anchor,
      fit,
    });
    if (guard && !guard()) return "stale";
    const changed = result.changed ?? result.grew;
    state.design = result.design;
    if (changed) noteCommittedDesignChange(previousDesign);
    state.fitError = false;
    if (opts.keepDraft && state.draft) {
      // Keep editing the same part with whatever zone the resize settled on.
      const at = anchorIndex < state.design.layout.features.length ? anchorIndex : null;
      if (at !== null) {
        state.selected = at;
        state.draftIsNew = false;
        state.draftSourceIndex = at;
        state.draft = clone(state.design.layout.features[at]);
      }
      renderDraftFields();
      syncForm();
      updateSelectionButtons();
      await refreshPreview();
    } else {
      clearDraftSelection(false);
      syncForm();
      updateAutoExpandButton();
      await refreshPreview();
    }
    if (result.box.x !== previousBox.x) flashField($("#x-size"));
    if (result.box.y !== previousBox.y) flashField($("#y-size"));
    if (!opts.silent && changed) {
      toast(fit
        ? `Bin sized to the smallest fit: ${fmt(result.box.x)} × ${fmt(result.box.y)} mm.`
        : `Bin resized to ${fmt(result.box.x)} × ${fmt(result.box.y)} mm.`);
    } else if (!opts.silent && fit) {
      toast("The bin is already at the smallest fit.");
    } else if (!opts.silent && !opts.keepDraft) {
      toast("The interior parts already fit - bin unchanged.");
    }
    return "done";
  } catch (error) {
    if (!opts.silent) toast(error.message, true, 5000);
    return "failed";
  } finally {
    if (button) button.disabled = false;
    finishDesignMutation();
  }
}

// A manually reduced bin never leaves existing parts invalid. The server grows
// only when required, and autoExpandBin flashes each corrected axis.
const enforceBinMinimumSoon = debounce(() => {
  if (state.autoGrowingBin || state.designMutationBusy ||
      !(state.draft || state.design?.layout?.features?.length)) return;
  state.autoGrowingBin = true;
  Promise.resolve(autoExpandBin({ keepDraft: true, silent: true }))
    .finally(() => { state.autoGrowingBin = false; });
}, 120);