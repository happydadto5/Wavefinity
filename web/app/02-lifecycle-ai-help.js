"use strict";

// ------------------------------------------------------------ Fix 034 lifecycle

function applyDesignerLifecycleVisibility() {
  const typed = state.folderMode === "space";
  const hide = (selector, hidden) => { const el = $(selector); if (el) el.hidden = hidden; };
  hide("#designer-save-file", typed);
  hide("#designer-open-file-label", typed);
}

function typedSpaceOrdinaryBin() {
  return state.folderMode === "space" && typeof DL !== "undefined";
}

// Fix 103: the structural target never flows through the ordinary-bin
// design-source autosave/dirty owners.
function designTargetIsStructural() {
  return typeof DP !== "undefined" && DP.getDesignTarget && DP.getDesignTarget().kind === "structural";
}

// A Storage Box or Base Trim is a structural output of its Space (see
// SP.saveStructural in spaces.js), never a Designer object: the Designer
// only opens and edits ordinary Bins.
function isStructuralDesign(design) {
  return Boolean(design) && (design.design_kind === "base_trim" || Boolean(design.box?.b4b?.enabled));
}

let spaceAutosaveTimer = null;
let spaceAutosaveChain = Promise.resolve();

// Wavefinity-owned superseded output for one Inventory row, from the
// server-tracked layout.stale_files map. The browser owns the hosted folder,
// so a re-save may only replace names the server recorded as this row's own
// retired outputs; any other collision still demands a rename.
function staleFileNamesForRow(rowId) {
  if (!rowId || typeof DL === "undefined" || !DL.layout) return [];
  const stale = DL.layout.stale_files;
  const names = stale && stale[rowId];
  return Array.isArray(names) ? names.filter(name => typeof name === "string" && name) : [];
}

// Change Location quiescence: true while a Designer file refresh or a queued
// autosave could still write to the current Space root.
function designerWriteActive({ includeTimer = true } = {}) {
  return Boolean(
    isGenerating || state.designMutationBusy ||
    (includeTimer && spaceAutosaveTimer),
  );
}

function relocationBlocksWrites() {
  if (!state.relocating) return false;
  toast("Wavefinity is changing its folder. Try again in a moment.", true);
  return true;
}

async function settleDesignerWritesForRelocation() {
  clearTimeout(spaceAutosaveTimer);
  spaceAutosaveTimer = null;
  await spaceAutosaveChain;
}

function queueSpaceDesignAutosave() {
  if (DP.getDesignTarget().kind === "none") return;
  if (designTargetIsStructural()) return; // Fix 103
  if (state.relocating || !typedSpaceOrdinaryBin()) return;
  const context = DL.spaceContext();
  clearTimeout(spaceAutosaveTimer);
  spaceAutosaveTimer = setTimeout(() => {
    spaceAutosaveTimer = null;
    persistSpaceDesignSource(context).catch(error => {
      if (!DL.isStaleSpaceError(error)) toast(`Could not autosave this bin: ${error.message}`, true, 6000);
    });
  }, 350);
}

function persistSpaceDesignSource(expectedContext = null, force = false) {
  const run = async () => {
    if (DP.getDesignTarget().kind === "none") return true;
    if (designTargetIsStructural()) return true; // Fix 103
    if (!typedSpaceOrdinaryBin()) return true;
    const context = expectedContext || DL.spaceContext();
    DL.requireSpaceContext(context);
    if (!DL.loaded) {
      await DL.ensureLoaded();
      DL.requireSpaceContext(context);
    }
    const design = clone(state.design);
    if (!force && (!state.preview?.fits || state.preview.feature_errors?.length ||
        state.preview.draft_error || state.previewDesignKey !== JSON.stringify(design))) return true;
    if (!force && JSON.stringify(design) === JSON.stringify(state.cleanDesign)) return true;
    const rowId = state.designInventoryId;
    const previousClean = state.cleanDesign;
    const data = await DL.inventoryCall("/api/drawer/design-source/save", {
      design, row_id: rowId || undefined,
    }, { context, sideEffect: true });
    DL.requireSpaceContext(context);
    // The exact bin is now durable in design_specs. Space preferences follow
    // from that canonical design; a failure here never rolls the bin back.
    try {
      rememberSpacePreferences(data.design, previousClean);
    } catch (error) {
      toast(`This bin was saved, but the Space's remembered settings were not: ${error.message}`, true, 6000);
    }
    if (state.designInventoryId !== rowId) {
      return true;
    }
    state.designInventoryId = data.row_id;
    DL.adopt(data);
    DL.emit();
    if (state.runtime.hosted) SP.queueHostedBinBuild(data, context);
    if (JSON.stringify(state.design) === JSON.stringify(design)) {
      state.design = clone(data.design);
      state.cleanDesign = clone(data.design);
      // Only the assigned name can differ. Refresh just that field: a full
      // syncForm() would overwrite anything the user is typing that has not
      // reached state.design yet.
      if (data.design.part_name !== design.part_name) $("#part-name").value = data.design.part_name || "";
    } else {
      state.cleanDesign = clone(data.design);
      queueSpaceDesignAutosave();
    }
    return true;
  };
  const pending = spaceAutosaveChain.then(run, run);
  spaceAutosaveChain = pending.catch(() => {});
  return pending;
}

async function flushSpaceDesignAutosave({ visible = true, materialize = false,
    deferDraftPreview = false, noDeferredPreview = false, leavingDesign = false,
    abandonBuild = false, spaceSwitch = false, mutationOwned = false } = {}) {
  if (DP.getDesignTarget().kind === "none") return true;
  if (designTargetIsStructural()) return true; // Fix 103
  if (!typedSpaceOrdinaryBin()) return true;
  visible = visible && SP.binEditorVisible();
  // Landing on a Space's container/first bin can also replace a hidden
  // starter. It gets the same recovery guarantee as the folder switch.
  if (!spaceSwitch && !visible) return SP.leaveBinForSpaceSwitch({
    visible: false, materialize, noDeferredPreview,
  });
  // Fix 109 A1: leaving Design for Space is where a first bin becomes durable.
  // state.designInventoryId is the idempotency key - once the save below
  // stores the returned row id, every later exit is an update, never a create.
  if (leavingDesign && !state.designInventoryId &&
      DP.getDesignTarget().kind === "new_bin") materialize = true;
  const originalDesign = state.design;
  const ownerAtStart = fullPreviewStarts;
  try {
    clearTimeout(spaceAutosaveTimer);
    spaceAutosaveTimer = null;
    if (spaceSwitch && visible) {
      // A Space switch never enters a draft-conflict or small-label dialog.
      // Unfinished work takes the exact recovery path instead.
      if (draftNeedsSaving() || $(".controls input:invalid")) return false;
      const candidate = visibleDesignSnapshot();
      if (newModifierConflict(pendingPreEditDesign || state.design, candidate)) return false;
      state.design = candidate;
    }
    if (!spaceSwitch && visible && !(await flushVisibleDesignEditsBeforeModeSwitch({
      previewAfterCommit: !deferDraftPreview,
    }))) return false;
    if (!spaceSwitch && visible && !(await maybePromptSurfaceObjectHeight())) return false;
    if (!mutationOwned && !beginDesignMutation({ readForm: visible && !spaceSwitch, quiet: spaceSwitch })) return false;
    let saved = false;
    try {
      // Story 2773: leaving (e.g. Manage Spaces) with an already-current preview
      // rebuilds nothing; only a label-only difference is recorded.
      if (abandonBuild && state.previewSettledRequest !== state.previewRequest) {
        // Story 2777: New Bin during a geometry rebuild switches at once. The
        // unfinished preview is dropped (the server abandons the superseded build
        // when the new bin's preview starts); only the design's settings are saved.
        invalidatePendingPreview();
        await persistSpaceDesignSource(null, true);
        await SP.flushDefaults();
        saved = true;
        return saved;
      }
      if (previewShowsCurrentGeometry() || await awaitInFlightPreviewFor(state.design)) {
        if (state.previewDesignKey !== JSON.stringify(state.design)) state.previewDesignKey = JSON.stringify(state.design);
      } else await refreshPreview();
      if (!state.preview?.fits || state.preview.feature_errors?.length || state.preview.draft_error ||
          state.previewDesignKey !== JSON.stringify(state.design))
        throw new Error("Resolve the design issue before leaving this bin.");
      await persistSpaceDesignSource(null, materialize);
      await SP.flushDefaults();
      saved = true;
    } catch (error) {
      if (!spaceSwitch) toast(`Could not autosave this bin: ${error.message}`, true, 6000);
      return false;
    } finally {
      if (!mutationOwned) finishDesignMutation();
    }
    return saved;
  } finally {
    if (!spaceSwitch && visible && deferDraftPreview && !noDeferredPreview && state.design !== originalDesign &&
        fullPreviewStarts === ownerAtStart) refreshPreview();
  }
}

// Install a canonical design (from Inventory Edit or Duplicate) as the working Designer
// design, replacing whatever is currently shown. A plain bin open passes no
// successMessage and shows no notice; actions with an outcome to confirm (such as
// Duplicate) pass their own message.
async function installLoadedDesignSource(rowId, spec, {
  successMessage = null,
  acceptTransition = null,
} = {}) {
  if (acceptTransition && !acceptTransition()) return false;
  if (!beginDesignMutation()) return false;
  const sourceSpace = state.activeSpace, sourceFolder = state.folderMode;
  try {
    const result = await api("/api/design/validate", { design: spec });
    if (state.activeSpace !== sourceSpace || state.folderMode !== sourceFolder ||
        (acceptTransition && !acceptTransition())) return false;
    state.design = result.design;
    state.lastOrdinaryDesign = clone(state.design);
    resetNestPhotoSession();
    state.cleanDesign = clone(spec);
    state.spaceStarterPreviewPending = false;
    state.designInventoryId = rowId;
    state.designTarget = null; // Fix 103
    if (typeof DP !== "undefined") { DP.refreshDesignerDeleteBin(); }
    state.surfaceHeightPromptSkipped = false;
    state.drafts = {};
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    if (!acceptTransition) {
      if (typeof DP !== "undefined" && state.folderMode === "space") DP.setMode("design");
      activatePreviewView(preferredDesignView());
    }
    const preview = refreshPreview();
    if (rowId === null && typedSpaceOrdinaryBin()) {
      await preview;
      await persistSpaceDesignSource(null, true);
    }
    if (successMessage) toast(successMessage);
    return true;
  } catch (error) {
    toast(`Could not load that design: ${error.message}`, true, 6000);
    return false;
  } finally {
    finishDesignMutation();
  }
}

async function designerEditInventoryRow(rowId, acceptTransition = null) {
  if (acceptTransition && !acceptTransition()) return false;
  if (state.folderMode !== "space" || typeof DL === "undefined") return false;
  const one = DL.bin(rowId);
  const spec = DL.layout?.design_specs?.[rowId];
  if (!one || !["bin", "b4b"].includes(one.kind)) return false;
  // Fix 096 A2: keep the row visible, but say plainly why it can't be edited.
  if (!spec) {
    toast("The original editable design for this row is unavailable, so it can't be edited.", true);
    return false;
  }
  if (isStructuralDesign(spec)) {
    toast("A Storage Box or Base Trim is saved from its Space, not designed here.", true, 6000);
    return false;
  }
  return designerInstallInventorySpec(rowId, spec, acceptTransition);
}

async function designerInstallInventorySpec(rowId, spec, acceptTransition = null) {
  if (!spec) return false;
  if (acceptTransition && !acceptTransition()) return false;
  if (state.designInventoryId === rowId) {
    if (!acceptTransition) activatePreviewView(preferredDesignView());
    return true;
  }
  // Story 2808: picking another bin shows its stored details at once. A geometry build
  // still running for the outgoing bin is dropped (as New Bin does, Story 2777), not awaited;
  // only its settings are saved, and the new bin's preview builds in the background.
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ deferDraftPreview: true, abandonBuild: true }))) return false;
  if (acceptTransition && !acceptTransition()) return false;
  return installLoadedDesignSource(rowId, spec, { acceptTransition });
}

// ------------------------------------------------------------ AI Help (Fix 073)
//
// Wavefinity never talks to an AI. It writes a prompt the person pastes into any
// outside AI, then checks the pasted answer here. Every check happens before
// anything changes: the candidate is proven in the real geometry path first, and
// only a fully valid design is installed. All of this state is runtime-only -
// never saved into a design, a Space or a preference.

const AI_SCHEMA = "wavefinity-ai-design-v1";
// `generatedFor`: the trimmed description the current prompt/session was
// generated from - Generate Prompt stays disabled while the live description
// still equals it (Fix 078).
const aiHelp = { session: null, busy: false, generation: 0, failure: null,
  generatedFor: null, openIdentityKey: null };

function aiTypedSpaceActive() {
  return state.folderMode === "space" && typeof DL !== "undefined" && DL.active && Boolean(DL.layout);
}

// Per-Space history of object descriptions AI Design actually generated a
// prompt from (Fix 078) - never the prompt text itself, never a bin design.
function aiRecentDescriptions() {
  if (!aiTypedSpaceActive()) return [];
  return DL.layout.settings?.ai_design_recent_descriptions || [];
}

// Only after Generate Prompt succeeds. Moves an existing case-insensitive
// match to the top instead of duplicating it; keeps at most 10, newest first.
// A save failure here must never invalidate the prompt/session already
// established - it is reported as a separate, non-blocking warning.
async function aiRecordRecentDescription(description) {
  if (!aiTypedSpaceActive()) return;
  try {
    const trimmed = description.trim();
    DL.change(() => {
      const kept = (DL.layout.settings.ai_design_recent_descriptions || [])
        .filter(one => one.trim().toLowerCase() !== trimmed.toLowerCase());
      DL.layout.settings.ai_design_recent_descriptions = [trimmed, ...kept].slice(0, 10);
    });
    aiRenderRecentDescriptions();
    if (!(await DL.save())) throw new Error("Recent descriptions were not saved");
  } catch (_error) {
    toast("The prompt is ready, but its description could not be saved to Recent descriptions.", true, 6000);
  }
}

function aiRenderRecentDescriptions() {
  const block = $("#ai-help-recent-block");
  const list = $("#ai-help-recent-list");
  const toggle = $("#ai-help-recent-toggle");
  if (!block || !list || !toggle) return;
  const entries = aiRecentDescriptions();
  block.hidden = entries.length === 0;
  list.hidden = true;
  toggle.setAttribute("aria-expanded", "false");
  list.innerHTML = entries.map((text, index) =>
    `<button type="button" class="ai-help-recent-item" role="option" data-recent-index="${index}">${escapeHtml(text)}</button>`
  ).join("");
}

// Wavefinity, not the outside AI, owns final bin-name uniqueness (Fix 078):
// trimmed, case-insensitive comparison. Keep an exact free requested name;
// only on collision strip one trailing " (N)" and find the first free suffix.
// Mirrors (generalizes) the
// existing Inventory duplicate-name convention in
// organizer_inventory.py::_duplicate_name(), so there is one suffix rule.
function aiResolveCandidateName(candidateName, { excludeCurrent }) {
  const requested = String(candidateName || "").trim() || "Bin";
  const rows = aiTypedSpaceActive() ? (DL.bins || []) : [];
  const currentId = state.designInventoryId;
  const taken = new Set(
    rows.filter(one => !(excludeCurrent && one.id === currentId))
      .map(one => String(one.name || "").trim().toLowerCase())
  );
  if (!taken.has(requested.toLowerCase())) return requested;
  const root = requested.replace(/ \(\d+\)$/, "").trim() || "Bin";
  let number = 2;
  while (taken.has(`${root} (${number})`.toLowerCase())) number += 1;
  return `${root} (${number})`;
}

// `stale`: the answer belongs to an older prompt/context - needs a fresh prompt.
// `operational`: the answer was fine but Wavefinity itself failed (service, save,
// apply) - the AI cannot fix that, so it is never offered a repair.
// `applied`: the design was already installed when that failure happened.
class AiHelpError extends Error {
  constructor(message, { stale = false, operational = false, applied = false } = {}) {
    super(message);
    this.stale = stale;
    this.operational = operational;
    this.applied = applied;
  }
}

// The Space facts an AI needs to make legal choices, and nothing else.
function aiSpaceContext() {
  const space = state.folderMode === "space" ? state.activeSpace : null;
  if (!space) return null;
  const limits = space.kind === "storage_drawers" ? cabinetActiveLimits() : {};
  const context = {
    kind: space.kind, x: limits.x ?? space.x, y: limits.y ?? space.y, z: limits.z ?? space.z,
    trim_size: space.trim_size, pegboard_standard: space.pegboard_standard,
  };
  if (space.kind === "pegboard") {
    const minimum = pegboardProductMinimums(space.pegboard_standard);
    if (minimum.x > 0) context.min_x = minimum.x;
    context.min_z = minimum.z;
  }
  return context;
}

// Existing ordinary-bin names, advisory-only context for the AI prompt so it
// can avoid an obvious duplicate (Fix 078). Wavefinity still enforces final
// uniqueness itself on adoption.
function aiExistingBinNames() {
  if (state.folderMode !== "space" || typeof DL === "undefined" || !DL.bins) return [];
  return DL.bins.map(one => String(one.name || "").trim()).filter(Boolean).slice(0, 200);
}

// Who owns this bin: the pieces of context that never change just because a
// form re-rendered or the bin was auto-named.
function aiIdentityKey() {
  return JSON.stringify({
    folder: state.folderMode,
    spaceId: state.folderMode === "space" ? (state.activeSpaceId || null) : null,
    space: aiSpaceContext(),
    inventoryId: state.designInventoryId ?? null,
  });
}

// Exact context a prompt was written for: everything the person can see, the bin
// name included, so a name typed after the prompt was written is never overwritten.
function aiContextKey() {
  const design = visibleDesignSnapshot();
  return JSON.stringify({
    identity: aiIdentityKey(),
    structural: isStructuralDesign(design),
    design,
    draft: draftNeedsSaving() ? state.draft : null,
  });
}

// Accepts exactly one JSON object, optionally inside ONE outer markdown fence.
// It never scrapes JSON out of prose, merges objects, repairs syntax, or fills in
// a missing envelope field.
function aiParseEnvelope(text) {
  let source = String(text ?? "").trim();
  if (!source) throw new AiHelpError("Paste the AI's answer first.");
  const fence = source.match(/^```[A-Za-z]*[ \t]*\r?\n([\s\S]*?)\r?\n?```$/);
  if (fence) source = fence[1].trim();
  let data;
  try {
    data = JSON.parse(source);
  } catch (_error) {
    throw new AiHelpError("The answer is not one valid JSON object. It must be only the JSON, with no extra text.");
  }
  const plain = value => value !== null && typeof value === "object" && !Array.isArray(value);
  if (!plain(data)) throw new AiHelpError("The answer must be one JSON object.");
  if (data.schema !== AI_SCHEMA) throw new AiHelpError(`"schema" must be exactly "${AI_SCHEMA}".`);
  if (typeof data.request_id !== "string" || typeof data.context_fingerprint !== "string") {
    throw new AiHelpError('"request_id" and "context_fingerprint" must be copied exactly as text.');
  }
  if (!Array.isArray(data.assumptions)) throw new AiHelpError('"assumptions" must be a list.');
  if (!plain(data.design)) throw new AiHelpError('"design" must be a complete design object.');
  return data;
}

// A response is only good for the exact prompt and context it was written for.
function aiCheckSession(envelope, session) {
  const fresh = "Your design or Space changed since the prompt was made. Generate a new AI prompt for what is open now.";
  if (!session) throw new AiHelpError("Generate an AI prompt first, then paste its answer.", { stale: true });
  if (envelope && (envelope.request_id !== session.request_id ||
      envelope.context_fingerprint !== session.context_fingerprint)) {
    throw new AiHelpError("This answer belongs to a different prompt. Generate a new AI prompt and use its answer.", { stale: true });
  }
  if (aiContextKey() !== session.contextKey) throw new AiHelpError(fresh, { stale: true });
}

// The active Space's exact rules, checked rather than silently clamped.
function aiSpaceViolation(design, baseline) {
  const box = design.box || {};
  if (isStructuralDesign(design)) return "A Storage Box or Base Trim cannot be used as an AI bin.";
  const mount = JSON.stringify(box.pegboard || null);
  const space = state.folderMode === "space" ? state.activeSpace : null;
  if (!space) {
    return mount === JSON.stringify(baseline?.box?.pegboard || null)
      ? null : "Pegboard mounting belongs to a Pegboard Space and cannot be changed here.";
  }
  const kind = space.kind;
  // Story 2973: an AI bin of another grid never enters this Space; both grids are named.
  const spaceGrid = space.grid || "wavefinity", designGrid = design.grid || "wavefinity";
  if (designGrid !== spaceGrid) {
    const named = grid => state.catalog?.grids?.find(row => row.value === grid)?.label || grid;
    return `This AI bin is a ${named(designGrid)} design and this Space is ${named(spaceGrid)}. Nothing was changed.`;
  }
  const unit = kind === "drawer" && DRAWER_GRID_PITCHES[spaceGrid] ? DRAWER_GRID_PITCHES[spaceGrid] : number(state.catalog?.base_unit, 7);
  const capacity = mm => kind === "drawer" ? drawerSpaceCapacity(mm, spaceGrid) : Math.floor(number(mm, 0) / unit + 1e-9);
  const maxX = capacity(space.x) * unit, maxY = capacity(space.y) * unit;
  if (box.x > maxX + 1e-6 || box.y > maxY + 1e-6) {
    return `The bin is ${fmt(box.x)} x ${fmt(box.y)} mm but this Space fits at most ${fmt(maxX)} x ${fmt(maxY)} mm.`;
  }
  const spaceZ = kind === "storage_drawers" ? (cabinetActiveLimits().z ?? space.z) : space.z;
  if (["drawer", "portable", "box", "storage_drawers"].includes(kind) && box.z > number(spaceZ, Infinity) + 1e-6) {
    return `The bin is ${fmt(box.z)} mm tall but this Space is only ${fmt(spaceZ)} mm tall.`;
  }
  if (kind === "pegboard") {
    if (!box.pegboard?.enabled || box.pegboard.standard !== space.pegboard_standard ||
        mount !== JSON.stringify(baseline?.box?.pegboard || null)) {
      return "This Space's Pegboard mounting must be kept exactly as it was.";
    }
    const minimum = pegboardProductMinimums(space.pegboard_standard);
    if (box.x < minimum.x - 1e-6 || box.z < minimum.z - 1e-6) {
      const needs = [minimum.x > 0 ? `${fmt(minimum.x)} mm wide` : "", `${fmt(minimum.z)} mm tall`].filter(Boolean);
      return `A bin on this Pegboard Space must be at least ${needs.join(" and ")}.`;
    }
  } else if (mount !== JSON.stringify(baseline?.box?.pegboard || null)) {
    return "Pegboard mounting belongs to a Pegboard Space and cannot be changed here.";
  }
  if (kind === "surface") {
    const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
    if (!same(box.base_thickness, baseline?.box?.base_thickness) ||
        !same(box.standard_base, baseline?.box?.standard_base) ||
        !same(design.layout?.surface_base_mode, baseline?.layout?.surface_base_mode)) {
      return "This Surface Space controls the bin base, so it must be kept exactly as it was.";
    }
  }
  return null;
}

function aiSetStatus(message = "", { error = false, repair = false } = {}) {
  const status = $("#ai-help-status");
  if (!status) return;
  status.textContent = message;
  status.hidden = !message;
  status.classList.toggle("error", error);
  const repairButton = $("#ai-help-repair");
  if (repairButton) repairButton.hidden = !repair || aiMode !== "automatic";
}

function aiSetBusy(busy) {
  aiHelp.busy = busy;
  ["#ai-help-settings", "#ai-help-generate-new", "#ai-help-repair", "#ai-help-cancel", "#ai-help-ask"].forEach(selector => {
    const button = $(selector);
    if (button) button.disabled = busy;
  });
  if (busy) {
    const generate = $("#ai-help-generate");
    if (generate) generate.disabled = true;
  } else {
    aiUpdateGenerateAvailability();
  }
}

// Blank description keeps Generate Prompt disabled; a successful generation
// disables it again while the live description still equals the one it was
// generated from (Fix 078). A failed generation never sets that marker.
function aiUpdateGenerateAvailability() {
  const button = $("#ai-help-generate");
  if (!button) return;
  const text = $("#ai-help-description").value.trim();
  button.disabled = !text || (aiHelp.generatedFor !== null && text === aiHelp.generatedFor);
}

function aiSetCopyState(label) {
  const button = $("#ai-help-copy");
  if (button) button.textContent = label;
}

function aiShowPrompt(text) {
  const area = $("#ai-help-prompt");
  area.value = text;
  $("#ai-help-prompt-block").hidden = aiMode !== "manual";
  aiSetCopyState("Copy Prompt");
}

async function aiCopyText(text, area) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_error) {
    try {
      area?.select();
      return Boolean(document.execCommand?.("copy"));
    } catch (_inner) {
      return false;
    }
  }
}

async function aiGeneratePrompt() {
  if (aiHelp.busy) return;
  if (designTargetIsStructural()) { // Fix 103
    aiSetStatus("AI Design designs ordinary bins only.", { error: true });
    return;
  }
  if (aiHelp.openIdentityKey && aiIdentityKey() !== aiHelp.openIdentityKey) {
    aiSetStatus("The open bin or Space changed. Close AI Design and open it again for the current bin.", { error: true });
    return;
  }
  const description = $("#ai-help-description").value.trim();
  if (!description) {
    aiSetStatus("Describe the object first.", { error: true });
    return;
  }
  aiHelp.session = null;
  aiHelp.failure = null;
  aiSetBusy(true);
  aiSetStatus("Writing the prompt…");
  try {
    // Unsaved work on an interior part is saved into the design first, through the
    // same owner every other bin transition uses, so the prompt - and the session
    // bound to it - describe exactly what the person sees now.
    const done = await withDeferredDraftSwitch(async () => {
      const baseline = visibleDesignSnapshot();
      if (isStructuralDesign(baseline)) throw new AiHelpError("AI Design designs ordinary bins only.");
      const contextKey = aiContextKey();
      const space = aiSpaceContext();
      const records = await aiSavedContext();
      const result = await api("/api/ai/prompt", {
        ...records, editor_grid: baseline.grid || "wavefinity",
        description, design: baseline, space, existing_names: aiExistingBinNames(),
      });
      if (aiContextKey() !== contextKey) {
        throw new AiHelpError("Your design changed while the prompt was being written. Try again.");
      }
      aiHelp.session = {
        records,
        request_id: result.request_id,
        context_fingerprint: result.context_fingerprint,
        contextKey,
        baseline,
        // The exact Space facts the prompt was written against (Fix 078) -
        // candidate proof reuses these, never a newly switched Space.
        space,
      };
      aiHelp.generatedFor = description;
      aiShowPrompt(result.prompt);
      aiSetStatus(aiMode === "manual" ? "Prompt ready. Copy it into your AI, then paste its reply below." : "Prompt ready.");
      await aiRecordRecentDescription(description);
      return true;
    }, false);
    if (!done) aiSetStatus("Finish or discard the part you are editing, then generate the prompt again.", { error: true });
  } catch (error) {
    aiSetStatus(friendlyError(error), { error: true });
  } finally {
    aiSetBusy(false);
  }
}

// Steps 3-7 of the transaction: canonical design, structural rejection, the real
// preview/geometry proof and the Space's rules. Nothing here touches state.design.
async function aiProveCandidate(envelope, session) {
  let result;
  try {
    result = await api("/api/ai/candidate", {
      ...session.records, editor_grid: session.baseline.grid || "wavefinity",
      design: envelope.design, client_id: `${previewClientId}-ai`, generation: ++aiHelp.generation,
      // The prompt-bound Space context, never a newly switched Space
      // (Fix 078): the Space-cap preflight must judge against what the
      // prompt actually described.
      space: session.space,
    });
  } catch (error) {
    // 400 means Wavefinity judged the answer invalid; anything else is Wavefinity failing.
    if (error.status === 400) throw new AiHelpError(error.message);
    throw new AiHelpError(`Wavefinity could not check the answer just now (${friendlyError(error)}). Nothing was changed; try again.`,
      { operational: true });
  }
  aiCheckSession(envelope, session);
  if (result.superseded) throw new AiHelpError("Another check was started. Try again.");
  if (result.problems.length) {
    throw new AiHelpError(`Wavefinity could not build this design: ${result.problems.slice(0, 3).join(" ")}`);
  }
  const violation = aiSpaceViolation(result.design, session.baseline);
  if (violation) throw new AiHelpError(violation);
  return result;
}

// Step 8: install the proven design and adopt its already-built preview through
// the same owner refreshPreview() uses - no second identical geometry build.
// `mode` is "modify" or "new" - the user's explicit adoption choice (Fix 078).
// There is no "clean bin" auto-chooser any more. Returns true on success,
// false when nothing was changed.
async function aiInstallCandidate(candidate, session, mode) {
  // The one expected identity change: the pre-install save of a nonblank typed-Space
  // bin may legitimately give that bin a name and row ID. So the first check compares
  // everything including the bin's own ID, and the re-check after that save compares
  // only the folder/Space identity. Nothing else is ever ignored.
  const identity = ({ inventory = false } = {}) => {
    const now = JSON.parse(aiIdentityKey()), then = JSON.parse(JSON.parse(session.contextKey).identity);
    if (!inventory) { delete now.inventoryId; delete then.inventoryId; }
    if (JSON.stringify(now) !== JSON.stringify(then)) {
      throw new AiHelpError("Your Space or bin changed. Generate a new AI prompt for what is open now.", { stale: true });
    }
  };
  return withDeferredDraftSwitch(async () => {
    identity({ inventory: true });
    const design = clone(candidate.design);
    const currentName = String(session.baseline?.part_name || "").trim();
    if (mode === "modify") {
      // Preserve the current bin's own nonblank name even when the AI
      // proposes another; only a blank current name may adopt the AI name,
      // after collision-checking against every *other* surviving row.
      design.part_name = currentName || aiResolveCandidateName(design.part_name, { excludeCurrent: true });
    } else {
      if (state.folderMode === "space") {
        if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave({ deferDraftPreview: true }))) {
          aiSetStatus("The current bin could not be saved first, so nothing was changed.", { error: true });
          return false;
        }
      } else if (designHasChanges() && !(await appConfirmAction({
        title: "Generate as a new bin?",
        message: "Replace the current bin with the AI design as a new bin and discard its unsaved changes?",
        actionLabel: "Generate as New Bin",
        danger: true,
      }))) {
        aiSetStatus("Nothing was changed. Your answer is still here.");
        return false;
      }
      identity();
      design.part_name = aiResolveCandidateName(design.part_name, { excludeCurrent: false });
    }
    if (!beginDesignMutation()) {
      aiSetStatus("Wavefinity is finishing another change. Try again in a moment.", { error: true });
      return false;
    }
    let installed = false;
    try {
      state.design = design;
      installed = true;
      state.lastOrdinaryDesign = clone(state.design);
      resetNestPhotoSession();
      if (mode === "new") {
        // The equivalent New Bin baseline (the unedited starter), never the finished
        // candidate: persisting the AI design then updates the Space's remembered
        // bin/part defaults exactly as the same edits made by hand would.
        state.cleanDesign = clone(freshDesignForCurrentFolder());
        state.designInventoryId = null;
        state.designTarget = null; // Fix 103
      }
      state.spaceStarterPreviewPending = false;
      state.surfaceHeightPromptSkipped = false;
      state.drafts = {};
      state.binResizePending = false;
      state.binFootprintResizePending = false;
      bindLidMemoryForDesign();
      syncForm();
      clearDraftSelection();
      if (typeof DP !== "undefined" && state.folderMode === "space") DP.setMode("design");
      activatePreviewView("3d");
      // Claim preview ownership (older in-flight previews become stale, exactly as a
      // normal refresh would) and adopt the proven result instead of rebuilding it -
      // only its design's part_name differs from what was just proven, which does
      // not change geometry/validity, so the candidate's proof still stands.
      invalidatePendingPreview();
      fullPreviewStarts += 1;
      adoptPreviewResult({ ...candidate.preview, design: clone(state.design) });
      if (typedSpaceOrdinaryBin()) persistSpaceDesignSource(null, true).catch(error => {
        if (!DL.isStaleSpaceError(error)) toast(`Could not autosave this bin: ${error.message}`, true, 6000);
      });
      return true;
    } catch (error) {
      if (error instanceof AiHelpError) throw error;
      // The answer was valid; this is Wavefinity failing to apply or save it.
      throw new AiHelpError(installed
        ? `The AI design is valid and is open in the Designer, but applying or saving it hit a problem: ${friendlyError(error)}`
        : `The AI design is valid, but Wavefinity could not apply it: ${friendlyError(error)}. Nothing was changed.`,
      { operational: true, applied: installed });
    } finally {
      finishDesignMutation();
    }
  }, false);
}

async function aiProcessResponse() {
  if (aiHelp.busy) return;
  const text = $("#ai-help-response").value;
  const session = aiHelp.session;
  aiHelp.failure = null;
  aiSetBusy(true);
  aiSetStatus("Checking the answer…");
  try {
    const envelope = aiParseEnvelope(text);
    aiCheckSession(envelope, session);
    const candidate = await aiProveCandidate(envelope, session);
    if (await aiInstallCandidate(candidate, session, "new")) {
      aiHelp.session = null;
      $("#ai-help-dialog").close();
      toast("AI design applied.");
    }
  } catch (error) {
    // A stale answer needs a fresh prompt; a Wavefinity (service/save/apply) failure is
    // not the AI's fault; only a defect in the answer itself can be repaired.
    const known = error instanceof AiHelpError;
    const operational = !known || error.operational;
    if (error.stale) {
      aiHelp.session = null;
      aiHelp.generatedFor = null;
      aiUpdateGenerateAvailability();
    }
    if (error.applied) aiHelp.session = null;
    const repairable = known && !error.stale && !operational && Boolean(session);
    if (repairable) aiHelp.failure = { response: text, message: error.message, session };
    aiSetStatus(known ? error.message
      : `Wavefinity hit a problem (${friendlyError(error)}). Your answer is still here.`, { error: true, repair: repairable });
  } finally {
    aiSetBusy(false);
  }
}

async function aiMakeRepairPrompt() {
  const failure = aiHelp.failure;
  if (!failure || aiHelp.busy) return;
  aiSetBusy(true);
  try {
    const result = await api("/api/ai/repair-prompt", {
      request_id: failure.session.request_id,
      context_fingerprint: failure.session.context_fingerprint,
      response: failure.response,
      error: failure.message,
    });
    // Keep the repair prompt for the next explicit Ask my AI action.
    aiShowPrompt(result.prompt);
    aiSetStatus("Repair prompt ready. Choose Ask my AI.", { repair: true });
  } catch (error) {
    aiSetStatus(friendlyError(error), { error: true, repair: true });
  } finally {
    aiSetBusy(false);
  }
}

// Every open is a fresh transaction (Fix 078): all current-dialog working
// state is cleared before showModal() except per-Space Recent descriptions,
// which are never cleared here.
function aiResetDialog() {
  $("#ai-help-description").value = "";
  $("#ai-help-prompt").value = "";
  $("#ai-help-prompt-block").hidden = true;
  $("#ai-help-response").value = "";
  aiHelp.session = null;
  aiHelp.failure = null;
  aiHelp.generatedFor = null;
  aiHelp.openIdentityKey = aiIdentityKey();
  aiSetCopyState("Copy Prompt");
  aiSetStatus("");
  aiUpdateGenerateAvailability();
  aiRenderRecentDescriptions();
}

let aiConnection = null;
let aiMode = null;
async function aiSavedContext() {
  if (!aiSpaceContext()) return {};
  const folder = state.browserFolder, spaceId = state.activeSpaceId;
  if (!folder?.handle) throw new Error("Open the saved Space folder before using AI Design for it.");
  const inventory_text = await SP.readInventoryFor(folder, { migrate: false });
  const space_metadata_text = await WFFileSystem.readText(folder.handle, FOLDER_METADATA);
  if (folder !== state.browserFolder || spaceId !== state.activeSpaceId) throw new Error("The Space changed while reading its records. Generate a fresh prompt.");
  return { inventory_text: inventory_text || "", space_metadata_text, space_id: spaceId };
}
async function aiConnectionRefresh() {
  aiConnection = await api("/api/ai/connection", { action: "status" });
  aiMode = aiConnection.mode;
}
function aiApplyMode() {
  $("#ai-help-ask").hidden = aiMode !== "automatic";
  $("#ai-help-generate").hidden = aiMode !== "manual";
  $("#ai-help-prompt-block").hidden = aiMode !== "manual" || !$("#ai-help-prompt").value;
  $("#ai-help-repair").hidden = aiMode !== "automatic" || !aiHelp.failure;
}
async function aiChooseMode(mode) {
  await api("/api/ai/connection", { action: "mode", mode });
  aiMode = mode;
  aiApplyMode();
  $("#ai-setup-dialog").close();
  if (!$("#ai-help-dialog").open) $("#ai-help-dialog").showModal();
}
function aiOpenSetup() {
  aiConnectionForm(false);
  if (!$("#ai-setup-dialog").open) $("#ai-setup-dialog").showModal();
}
function aiConnectionForm(show) {
  $("#ai-connection-form").hidden = !show;
  $("#ai-connection-offer").hidden = show;
  $("#ai-connection-key").value = "";
  $("#ai-connection-key").placeholder = aiConnection?.has_key ? "Key in session memory (leave blank to keep)" : "Required for direct chat this session";
  $("#ai-connection-provider").value = aiConnection?.provider || "openai";
  $("#ai-connection-browser-access").checked = false;
  $("#ai-connection-trust").checked = false;
  for (const field of ["name", "url", "model"]) $("#ai-connection-" + field).value = aiConnection?.[field] || "";
  $("#ai-connection-status").textContent = "";
}
async function aiConnectionAction(action) {
  const payload = { action, keep_key: Boolean(aiConnection?.has_key && aiConnection.url === $("#ai-connection-url").value.trim().replace(/\/$/, "")) };
  for (const field of ["name", "url", "model", "key"]) payload[field] = $("#ai-connection-" + field).value;
  payload.provider = $("#ai-connection-provider").value;
  payload.browser_access = $("#ai-connection-browser-access").checked;
  payload.trust_endpoint = $("#ai-connection-trust").checked;
  const status = $("#ai-connection-status");
  status.textContent = action === "test" ? "Contacting your AI..." : "Saving...";
  for (const id of ["save", "test", "clear"]) $("#ai-connection-" + id).disabled = true;
  try {
    await api("/api/ai/connection", payload);
    if (action === "save") { await aiConnectionRefresh(); await aiChooseMode("automatic"); }
    else if (action === "clear") { await aiConnectionRefresh(); aiConnectionForm(true); status.textContent = "Session key cleared."; }
    else status.textContent = "Connection worked. Your AI answered.";
  } catch (error) { status.textContent = friendlyError(error); }
  finally { for (const id of ["save", "test", "clear"]) $("#ai-connection-" + id).disabled = false; }
}
async function aiAsk() {
  if (aiHelp.busy) return;
  if (!aiHelp.session || aiHelp.generatedFor !== $("#ai-help-description").value.trim()) await aiGeneratePrompt();
  if (!aiHelp.session || aiHelp.busy) return;
  aiSetBusy(true);
  try {
    aiCheckSession(null, aiHelp.session);
    aiSetStatus("Asking your AI...");
    const result = await api("/api/ai/ask", { prompt: $("#ai-help-prompt").value });
    $("#ai-help-response").value = result.answer;
    const envelope = aiParseEnvelope(result.answer);
    aiCheckSession(envelope, aiHelp.session);
    await aiProveCandidate(envelope, aiHelp.session);
    aiHelp.failure = null;
    aiSetStatus("Your AI's answer is ready. Review it, then choose Generate Bin.");
  } catch (error) {
    const repairable = error instanceof AiHelpError && !error.stale && !error.operational && Boolean(aiHelp.session);
    if (repairable) aiHelp.failure = { response: $("#ai-help-response").value, message: error.message, session: aiHelp.session };
    aiSetStatus(friendlyError(error), { error: true, repair: repairable });
  } finally { aiSetBusy(false); }
}

function aiWireHelp() {
  const dialog = $("#ai-help-dialog");
  if (!dialog) return;
  const setup = $("#ai-setup-dialog");
  $("#ai-help-open").addEventListener("click", async () => {
    aiResetDialog();
    try {
      await aiConnectionRefresh();
      aiApplyMode();
      if (!aiMode || (aiMode === "automatic" && !aiConnection.has_key)) aiOpenSetup();
      else if (!dialog.open) dialog.showModal();
    } catch (error) {
      if (!dialog.open) dialog.showModal();
      aiSetStatus(friendlyError(error), { error: true });
    }
  });
  $("#ai-help-settings").addEventListener("click", aiOpenSetup);
  $("#ai-connection-configure").addEventListener("click", () => aiConnectionForm(true));
  $("#ai-connection-later").addEventListener("click", async () => {
    try { await aiChooseMode("manual"); }
    catch (error) { aiConnectionForm(true); $("#ai-connection-status").textContent = friendlyError(error); }
  });
  $("#ai-connection-cancel").addEventListener("click", () => aiConnectionForm(false));
  $("#ai-connection-test").addEventListener("click", () => aiConnectionAction("test"));
  $("#ai-connection-save").addEventListener("click", () => aiConnectionAction("save"));
  $("#ai-connection-clear").addEventListener("click", () => aiConnectionAction("clear"));
  $("#ai-connection-url").addEventListener("input", () => { $("#ai-connection-trust").checked = false; });
  setup.addEventListener("close", () => { $("#ai-connection-key").value = ""; });
  window.addEventListener("pagehide", () => { $("#ai-connection-key").value = ""; aiConnection = null; });
  $("#ai-help-ask").addEventListener("click", aiAsk);
  $("#ai-help-description").addEventListener("input", aiUpdateGenerateAvailability);
  $("#ai-help-generate").addEventListener("click", aiGeneratePrompt);
  $("#ai-help-generate-new").addEventListener("click", aiProcessResponse);
  $("#ai-help-repair").addEventListener("click", aiMakeRepairPrompt);
  $("#ai-help-copy").addEventListener("click", async () => {
    const copied = await aiCopyText($("#ai-help-prompt").value, $("#ai-help-prompt"));
    if (copied) {
      aiSetCopyState("Copied");
      aiSetStatus(aiMode === "manual" ? "Prompt ready. Copy it into your AI, then paste its reply below." : "Prompt ready.");
    } else {
      aiSetCopyState("Copy Prompt");
      aiSetStatus("Select the prompt and copy it.", { error: true });
    }
  });
  const recentToggle = $("#ai-help-recent-toggle");
  const recentList = $("#ai-help-recent-list");
  if (recentToggle && recentList) {
    recentToggle.addEventListener("click", () => {
      const expanded = !recentList.hidden;
      recentList.hidden = expanded;
      recentToggle.setAttribute("aria-expanded", String(!expanded));
    });
    recentList.addEventListener("click", event => {
      const button = event.target.closest(".ai-help-recent-item");
      if (!button) return;
      const text = aiRecentDescriptions()[Number(button.dataset.recentIndex)];
      if (text === undefined) return;
      // Selecting an entry only populates Description; it never generates a
      // prompt or creates/rebinds a session (Fix 078).
      const field = $("#ai-help-description");
      field.value = text;
      recentList.hidden = true;
      recentToggle.setAttribute("aria-expanded", "false");
      aiUpdateGenerateAvailability();
      field.focus();
    });
  }
  $("#ai-help-cancel").addEventListener("click", () => {
    dialog.close();
  });
  // A check in flight owns the dialog; closing never applies anything half-checked.
  dialog.addEventListener("cancel", event => {
    if (aiHelp.busy) event.preventDefault();
  });
}
