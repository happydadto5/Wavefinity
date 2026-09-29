"use strict";

// Normal Design can work without a persistent folder by downloading generated
// files. Inventory and typed Spaces require a real writable folder. A typed
// Space is a one-time Drawer/Storage Box/Surface/Pegboard setup layered on that folder;
// an untyped folder just keeps ordinary designs.
const SP = {
  recent: [],
  otherSpaces: [],
  otherSpacesFresh: false,
  setup: null,
  busy: false,
  resume: null,
  isUpdate: false,
  collisionOrigin: null,
  // A read-only setup candidate offered only to its matching type card.
  // It may come from existing inventory/layout recovery or from an explicit
  // New Space repeat-size template. It is never itself the active Space.
  setupPrefillSpace: null,
  // Set once SP.initializeDesignForActiveSpace() has kicked off its own
  // fresh preview during startup, so startSpaces()'s own fallback preview
  // does not fire a redundant duplicate for the same design (Fix 032
  // Correction 3, C3.2).
  _activationPreviewRequested: false,
  // Fix 058 K: the local-only first-run Space storage state from the last
  // /api/space/startup response - {parent, root, explicit, first_run,
  // unavailable} or null before startup has run / in hosted mode.
  storage: null,
};
const SP_KINDS = {
  // The internal kind stays "portable"; users only ever see "Storage Box".
  portable: { icon: "🧰", label: "Storage Box" },
  surface: { icon: "🔲", label: "Surface" },
  drawer: { icon: "🗄️", label: "Drawer" },
  storage_drawers: { icon: "🗃️", label: "Storage Drawers" },
  pegboard: { icon: "🧱", label: "Pegboard" },
  // Legacy kind, readable for migration only - never a current Space type;
  // it presents as a Storage Box, its recovery destination.
  box: { icon: "🧰", label: "Storage Box" },
};
const FOLDER_METADATA = ".wavefinity.json";
const LEGACY_METADATA = ".wavefinity-space.json";
const SPACE_ID_REQUIRED_VERSION = 5;
const FOLDER_METADATA_VERSION = 9;
const RESUME_REQUIRED_VERSION = 8;
const SPACE_SETUP_VERSION = 1;
// One fixed name for every inventory-enabled folder: it never follows the
// folder's own (renamable) name.
const INVENTORY_FILENAME = "Wavefinity bins.md";
const LEGACY_INVENTORY_SUFFIX = " bins.md";
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const spSame = (a, b) => {
  const tidy = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return tidy(a) === tidy(b);
};

SP.dialog = () => $("#welcome-dialog");
SP.close = () => {
  SP.destroyStorageDrawersForm?.();
  if (SP.dialog().open) SP.dialog().close();
};
SP.showOnly = id => {
  SP.cancelInlineEdit();
  ["welcome-home", "welcome-resume", "space-unsupported", "space-type-cards", "space-tutorial", "space-form", "space-configure-prompt", "space-collision-prompt", "space-existing-inventory-prompt", "space-storage-change"]
    .forEach(one => { $("#" + one).hidden = one !== id; });
};
SP.showDialog = () => { if (!SP.dialog().open) SP.dialog().showModal(); };

SP.run = async task => {
  if (SP.busy) return;
  SP.busy = true;
  SP.dialog().classList.add("busy");
  try { await task(); }
  catch (error) { toast(error.message, true, 6000); }
  finally {
    SP.busy = false;
    SP.dialog().classList.remove("busy");
  }
};

SP.sizeText = size => Array.isArray(size) ? `${size.map(fmt).join(" × ")} mm` : "";
SP.snap = mm => {
  const unit = state.catalog?.base_unit || 8;
  const max = Math.floor((state.catalog?.max_box_size || 350) / unit) * unit;
  return Math.min(max, Math.max(unit, Math.round(mm / unit) * unit));
};

// The single source of the Small/Medium/Large Surface trim presets: the
// authoritative Base Trim catalog, never a second hard-coded mm table.
SP.surfacePresetRows = () => {
  const rows = state.catalog?.base_trim_rules?.size_presets || [];
  return rows.filter(row => ["small", "medium", "large"].includes(row.key));
};

SP.surfacePresetMap = () => Object.fromEntries(
  SP.surfacePresetRows().map(row => [row.key, Number(row.value_mm)])
);

SP.surfaceTrimKeyForHeight = value => {
  const z = Number(value);
  if (!Number.isFinite(z)) return null;
  for (const [key, height] of Object.entries(SP.surfacePresetMap())) {
    if (Math.abs(z - height) <= 1e-6) return key;
  }
  return null;
};

// Surface setup asks for the maximum finished OUTSIDE size in mm. Space
// x / y stay the interior Wavefinity field in mm; this is the one place that
// converts between the two, using the catalog's Base Trim rules (never a
// second hard-coded table):
//   outside = field + mating gap + 2 * trim width
SP.surfaceRules = () => {
  const rules = state.catalog?.base_trim_rules || {};
  return {
    unit: Number(rules.unit_mm || state.catalog?.base_unit),
    gap: Number(rules.mating_gap_mm),
    maxField: Number(rules.max_field_mm),
  };
};

SP.surfaceOutsideFor = (fieldMm, trimKey) => {
  const { gap } = SP.surfaceRules();
  const width = SP.surfacePresetMap()[trimKey];
  return fieldMm + gap + 2 * width;
};

// Largest whole-unit interior field that fits inside the requested outside
// size (never nearest/up). Returns { ok, error, fieldX, fieldY, unitsX,
// unitsY, outerX, outerY, trimWidth }.
SP.resolveSurface = (requestedX, requestedY, trimKey) => {
  const { unit, gap, maxField } = SP.surfaceRules();
  const width = SP.surfacePresetMap()[trimKey];
  if (!Number.isFinite(width)) return { ok: false, error: "Choose Small, Medium, or Large trim." };
  if (!Number.isFinite(requestedX) || !Number.isFinite(requestedY) || requestedX <= 0 || requestedY <= 0) {
    return { ok: false, error: "Enter the outside width and length in mm." };
  }
  const epsilon = 1e-6;
  const extra = gap + 2 * width;
  const unitsFor = requested => Math.floor((requested - extra + epsilon) / unit);
  const unitsX = unitsFor(requestedX);
  const unitsY = unitsFor(requestedY);
  if (unitsX < 1 || unitsY < 1) {
    return {
      ok: false,
      error: `Too small: the smallest Surface is ${fmt(unit + extra)} mm outside with this trim.`,
    };
  }
  const fieldX = unitsX * unit;
  const fieldY = unitsY * unit;
  if (fieldX > maxField + epsilon || fieldY > maxField + epsilon) {
    return {
      ok: false,
      error: `Too large: the Wavefinity field cannot exceed ${fmt(maxField)} mm.`,
    };
  }
  return {
    ok: true, fieldX, fieldY, unitsX, unitsY, trimWidth: width,
    outerX: fieldX + extra, outerY: fieldY + extra,
  };
};

// The user's maximum finished outside rectangle (Fix 095). A Space that has
// no stored maximum is seeded from its current finished footprint, so the seed
// reproduces its current field exactly and can never grow the organizer. The
// visible inputs always keep the maximum; they are never overwritten with the
// smaller resolved finished size.
SP.surfaceMaxFor = space => {
  const seed = SP.surfaceOutsideFor(Number(space.x), space.trim_size);
  const seedY = SP.surfaceOutsideFor(Number(space.y), space.trim_size);
  const stored = (value, minimum) => {
    const number = Number(value);
    return value !== null && value !== undefined && value !== "" && Number.isFinite(number) && number > 0
      && number >= minimum - 1e-6 ? number : minimum;
  };
  return { x: stored(space.max_x_mm, seed), y: stored(space.max_y_mm, seedY) };
};

SP.surfaceTrimLabel = key =>
  SP.surfacePresetRows().find(row => row.key === key)?.label || key || "";

// "35X × 29X — 280 × 232 mm" for a stored interior field.
SP.fieldText = (x, y) => {
  const { unit } = SP.surfaceRules();
  return `${fmt(x / unit)}X × ${fmt(y / unit)}X — ${fmt(x)} × ${fmt(y)} mm`;
};

SP.populateSurfaceTrim = () => {
  const select = document.getElementById("surface-trim");
  if (!select) return;
  const rows = SP.surfacePresetRows();
  select.innerHTML = [
    '<option value="" disabled>Choose trim size</option>',
    ...rows.map(row =>
      `<option value="${escapeHtml(row.key)}">${escapeHtml(row.label)}</option>`
    ),
  ].join("");
};

SP.pegboardStandards = () => state.catalog?.pegboard_rules?.standards || [];
SP.pegboardStandard = id => SP.pegboardStandards().find(row => row.id === id) || SP.pegboardStandards()[0];
SP.populatePegboardStandards = () => {
  const select = document.getElementById("pegboard-standard");
  if (!select) return;
  select.innerHTML = SP.pegboardStandards().map(row =>
    `<option value="${escapeHtml(row.id)}">${escapeHtml(row.name)}</option>`
  ).join("");
};
SP.resolvePegboard = () => {
  const standard = SP.pegboardStandard(document.getElementById("pegboard-standard")?.value);
  const mode = document.getElementById("pegboard-size-mode")?.value || "physical";
  if (!standard) return { ok: false, error: "Pegboard standards are unavailable." };
  let holesX, holesY, width, height, residualX = 0, residualY = 0;
  if (mode === "holes") {
    holesX = Number(document.getElementById("pegboard-holes-x")?.value);
    holesY = Number(document.getElementById("pegboard-holes-y")?.value);
    if (![holesX, holesY].every(value => Number.isInteger(value) && value >= 1 && value <= 500)) {
      return { ok: false, error: "Enter whole hole or slot counts from 1 to 500." };
    }
    width = holesX * standard.pitch_x_mm;
    height = holesY * standard.pitch_y_mm;
  } else {
    width = Number(document.getElementById("pegboard-x")?.value);
    height = Number(document.getElementById("pegboard-y")?.value);
    if (![width, height].every(value => Number.isFinite(value) && value > 0)) {
      return { ok: false, error: "Enter the pegboard width and height in mm." };
    }
    holesX = Math.floor(width / standard.pitch_x_mm + 1e-9);
    holesY = Math.floor(height / standard.pitch_y_mm + 1e-9);
    if (holesX < 1 || holesY < 1) return { ok: false, error: "The board must contain at least one mount position." };
    if (holesX > 500 || holesY > 500) return { ok: false, error: "That board is too large. The limit is 500 mount positions per side." };
    residualX = width - holesX * standard.pitch_x_mm;
    residualY = height - holesY * standard.pitch_y_mm;
  }
  return { ok: true, standard, mode, holesX, holesY, width, height, residualX, residualY };
};

SP.drawerCapacity = mm => drawerSpaceCapacity(mm);
SP.hasFolder = () => Boolean(state.folderSelected);
SP.canPersistSpace = () => !state.runtime.hosted || Boolean(state.browserFolder?.handle);
// The active folder's inventory filename. Create/Configure must use
// SP.inventoryFilenameFor(folder) against the *selected target* instead -
// this one only ever reflects whatever was already active, which is wrong
// mid-Create before the new folder is activated - see Fix 004 Correction 7.A.
SP.inventoryFilename = () => SP.inventoryFilenameFor(state.browserFolder);
SP.inventoryFilenameFor = _folder => INVENTORY_FILENAME;

// ------------------------------------------------------------ safe Drawer/Space switch (Fix 019 Item 2)
//
// Folder identity must never change until leaving the current Drawer layout
// either succeeds or the user deliberately discards it. Fix 034 K1: autosave
// has no off state any more, so this always just flushes a dirty layout and
// ABORTS the switch (old Space stays active, DL.layout/DL.dirty stay intact)
// if that save fails - never an ambiguous native confirm().

// Resolves true when it is safe to proceed (nothing dirty, or a successful
// flush) and false when the switch must be aborted with everything -
// including DL.layout/DL.dirty - left exactly as it was.
SP.leaveDrawerLayoutSafely = async ({ noDeferredPreview = false } = {}) => {
  if (typeof flushSpaceDesignAutosave === "function" &&
      !(await flushSpaceDesignAutosave({ deferDraftPreview: true, noDeferredPreview }))) return false;
  if (SP._inventoryWriteChain) await SP._inventoryWriteChain;
  if (typeof DL === "undefined") return true;
  if (DL.savePromise) {
    const ok = await DL.savePromise;
    if (!ok && DL.dirty) {
      toast(`Could not switch Spaces: ${DL.saveError || "the layout failed to save."}`, true, 6000);
      return false;
    }
  }
  if (!DL.dirty || !DL.layout || !DL.output) return true;
  const ok = await DL.save();
  if (!ok) {
    toast(`Could not switch Spaces: ${DL.saveError || "the layout failed to save."}`, true, 6000);
    return false;
  }
  return true;
};

// Returns true once it is safe for the caller to change folder/Space
// identity, false when the switch was aborted (a failed save, or the user
// choosing Cancel) - in which case DL.layout/DL.dirty are left untouched.
SP.resetDrawer = async ({ skipSafeLeave = false } = {}) => {
  if (typeof DL === "undefined") return true;
  if (!skipSafeLeave || DL.savePromise || DL.dirty) {
    const ok = await SP.leaveDrawerLayoutSafely();
    if (!ok) return false;
  }
  // A different folder means a different Space: close the workspace first.
  DL.busyTicket += 1;
  DL.busy = "";
  if (typeof DP !== "undefined" && DP.leave) DP.leave();
  DL.loadEpoch += 1;
  DL.loadPromise = null;
  DL.layout = null;
  DL.dirty = false;
  DL.loaded = false;
  DL.exists = false;
  DL.bins = [];
  DL.file = "";
  DL.warnings = [];
  DL.report = null;
  DL.reportTicket += 1;
  DL.selected = null;
  DL.selectedRow = null;
  DL.output = null;
  DL.pegboardLayouts = {};
  DL.pegboardRefreshError = "";
  DL.saveState = "idle";
  DL.saveError = "";
  DL.history = [];
  DL.future = [];
  DL.clearSpacerPlan();
  if (typeof DP !== "undefined") DP.printSelected = new Set();
  if (typeof DP !== "undefined") DP.signatures = {};
  return true;
};

// Folder/Space identity and persisted Space defaults only - see
// SP.initializeDesignForActiveSpace below for the (separate) Current-design
// activation this triggers whenever the newly-applied folder is a typed
// Space (Fix 019 Item 1). Resolves false without changing anything when a
// dirty Drawer layout blocked the switch (see SP.resetDrawer above).
//
// The single owner of the ENTIRE frontend folder/Space identity transition,
// including state.browserFolder (Fix 032 Correction 2, C2.1). No caller may
// assign state.browserFolder itself before calling in here - an old Space's
// preview finishing during that window could otherwise capture its id/
// design paired with the new Space's folder handle. Pass `browserFolder`
// only from a hosted caller that has one to hand over.
SP.applyFolder = async (info, options = {}) => {
  const { reset = true, initDesign = true } = options;
  if (reset) {
    const ok = await SP.resetDrawer();
    if (!ok) return false;
  }
  // Any preview still in flight belongs to the OUTGOING Space/folder.
  // Invalidate it before the resume flush/identity switch below - its own
  // stale-request guard (`request !== state.previewRequest`) is what stops
  // a late Space-A response from landing into the now-active Space-B
  // state.design and getting persisted as B's checkpoint (Fix 032
  // Correction 3, C3.1). cancelPreviewWait() also explicitly hides any
  // visible "recalculating" notice/overlay (not just its timers - Fix 032
  // Correction 4, C4.3), so a cancelled Space-A preview cannot leave a
  // stale overlay showing in Space B.
  state.previewRequest += 1;
  cancelPreviewWait();
  // The old Space's queued/in-flight resume checkpoint must land before ANY
  // identity field below changes - a completion for it after the switch
  // must never write into, or overwrite in memory, the new Space's
  // checkpoint.
  await SP.flushOutgoingResumeCheckpoint();
  // Everything from here through setFolderState() is one synchronous block
  // with no intervening await, so nothing can ever observe a half-migrated
  // identity (e.g. the new state.browserFolder paired with the old
  // state.activeSpaceId).
  if (Object.hasOwn(options, "browserFolder")) state.browserFolder = options.browserFolder;
  state.output = info.folder;
  state.activeSpaceId = info.space_id || null;
  state.cabinetRecovery = info.cabinet_recovery || null;
  state.folderSelected = true;
  // A manually-built `info` that omits these fields (e.g. hosted
  // SP.create()'s constructed object) must not let the outgoing Space's
  // in-memory checkpoint leak into the new one - absence normalizes to
  // explicit null/false, never "preserve whatever is already there".
  const resumeDesign = Object.hasOwn(info, "resume_design") ? info.resume_design : null;
  const resumePending = Object.hasOwn(info, "resume_pending") ? info.resume_pending : false;
  setFolderState(
    info.folder_mode,
    info.space,
    info.inventory,
    info.keep_bin_defaults,
    info.bin_defaults,
    info.part_defaults,
    resumeDesign,
    resumePending,
  );
  if (initDesign && info.folder_mode === "space") await SP.initializeDesignForActiveSpace();
  syncForm();
  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  return true;
};

// ------------------------------------------------------------ browser files

SP.readMetadata = async handle => {
  const read = async name => {
    const raw = await WFFileSystem.readText(handle, name);
    if (raw === null) return { exists: false, data: null };
    try { return { exists: true, data: JSON.parse(raw) }; }
    catch (_error) { return { exists: true, error: "invalid-json" }; }
  };
  const current = await read(FOLDER_METADATA);
  await SP.validateHostedCabinet(current);
  return { current, legacy: await read(LEGACY_METADATA) };
};

// Hosted cabinet metadata is judged by the server's one canonical normalizer,
// exactly as the desktop app judges it. A valid definition is adopted in its
// normalized form; a known-setting failure enters the cabinet recovery state
// (Inventory and designs stay reachable). A network failure never guesses.
SP._cabinetValidation = new Map();
SP.validateHostedCabinet = async record => {
  const raw = record?.data?.space;
  if (!record?.exists || record.error || record.data?.folder_mode !== "space" || raw?.kind !== "storage_drawers") return;
  const key = JSON.stringify(raw);
  let outcome = SP._cabinetValidation.get(key);
  if (!outcome) {
    outcome = (async () => {
      try {
        const reply = await api("/api/space/storage-drawers-validate", { space: raw });
        return { space: reply.space };
      } catch (error) {
        if (!error.status) throw error;
        const reset = await api("/api/space/storage-drawers-reset", { space: raw });
        return { recovery: { message: reset.message || error.message, resetSpace: reset.space } };
      }
    })();
    SP._cabinetValidation.set(key, outcome);
    if (SP._cabinetValidation.size > 8) SP._cabinetValidation.delete(SP._cabinetValidation.keys().next().value);
    outcome.catch(() => SP._cabinetValidation.delete(key));
  }
  const result = await outcome;
  if (result.space) record.data = { ...record.data, space: result.space };
  else record.cabinetRecovery = result.recovery;
};

SP.validSpace = raw => {
  if (!raw || !["drawer", "surface", "portable", "box", "pegboard", "storage_drawers"].includes(raw.kind)) return null;
  const space = {
    kind: raw.kind,
    name: String(raw.name || "").trim(),
    x: Number(raw.x),
    y: Number(raw.y),
    z: Number(raw.z),
  };
  if (![space.x, space.y, space.z].every(value => Number.isFinite(value) && value > 0)) {
    return null;
  }

  if (space.kind === "surface") {
    const trimSize = String(raw.trim_size || "").trim().toLowerCase();
    const expected = SP.surfacePresetMap()[trimSize];
    if (Number.isFinite(expected) && Math.abs(space.z - expected) <= 1e-6) {
      space.trim_size = trimSize;
      const maximum = SP.surfaceMaxFor({ ...space, max_x_mm: raw.max_x_mm, max_y_mm: raw.max_y_mm });
      space.max_x_mm = maximum.x;
      space.max_y_mm = maximum.y;
    }
  }
  if ((space.kind === "portable" || space.kind === "box") && raw.storage_box && typeof raw.storage_box === "object") {
    space.storage_box = clone(raw.storage_box);
  }
  if (space.kind === "storage_drawers") {
    // The cabinet block is validated and canonicalised by its own owner.
    try {
      SP.ensureStorageDrawersRules();
      StorageDrawers.drawerDescriptors(raw);
    } catch (_error) { return null; }
    space.storage_drawers = clone(raw.storage_drawers);
  }
  if (space.kind === "pegboard") {
    const standard = SP.pegboardStandard(raw.pegboard_standard);
    const holesX = Number(raw.pegboard_holes_x);
    const holesY = Number(raw.pegboard_holes_y);
    if (!standard || !Number.isInteger(holesX) || holesX < 1 || !Number.isInteger(holesY) || holesY < 1) return null;
    Object.assign(space, {
      pegboard_standard: standard.id,
      pegboard_size_mode: raw.pegboard_size_mode === "holes" ? "holes" : "physical",
      pegboard_holes_x: holesX,
      pegboard_holes_y: holesY,
      pegboard_usable_x: Number(raw.pegboard_usable_x ?? holesX * standard.pitch_x_mm),
      pegboard_usable_y: Number(raw.pegboard_usable_y ?? holesY * standard.pitch_y_mm),
      pegboard_residual_x: Number(raw.pegboard_residual_x ?? 0),
      pegboard_residual_y: Number(raw.pegboard_residual_y ?? 0),
    });
  }
  return space;
};

SP.validUuid = raw => {
  const text = String(raw || "").trim();
  return UUID_PATTERN.test(text) ? text.toLowerCase() : null;
};

SP.classifyMetadata = record => {
  if (!record?.exists) return { status: "missing" };
  if (record.error || !record.data || typeof record.data !== "object" || Array.isArray(record.data)) {
    return { status: "invalid" };
  }
  const current = record.data;
  if (Number(current.version) > FOLDER_METADATA_VERSION) return { status: "unsupported" };
  // v2 and v3 are readable migration inputs, same as the local backend
  // (organizer_spaces._folder_state); v4+ are already onboarded. Older
  // current formats upgrade in place; v4 only lacks the Space identity.
  if (![2, 3, 4, 5, 6, 7, 8, 9].includes(current.version)) return { status: "invalid" };
  const needsMigration = current.version < 4 || current.setup_version !== SPACE_SETUP_VERSION;
  const explicitInventory = typeof current.inventory === "boolean" ? current.inventory : null;
  if (current.folder_mode === "design") {
    return { status: "design", inventory: explicitInventory, needsMigration, metadataVersion: current.version };
  }
  if (current.folder_mode === "space") {
    const recovering = record.cabinetRecovery || null;
    const space = SP.validSpace(recovering ? recovering.resetSpace : current.space);
    if (!space) return { status: "invalid-space" };
    if (current.version === 2) {
      // v2 predates keep_bin_defaults/bin_defaults entirely.
      return { status: "space", space, space_id: null, needsIdentityMigration: false, inventory: true, keep_bin_defaults: true, bin_defaults: null, part_defaults: {}, needsMigration: true, metadataVersion: 2, resume_design: null, resume_pending: false };
    }
    // A current-version typed Space must carry a valid ID; it is never healed
    // with a replacement identity.
    // v2/v3 are setup inputs (handled above for v2): never trust their ID.
    const spaceId = current.version >= 4 ? SP.validUuid(current.space_id) : null;
    if (current.version >= SPACE_ID_REQUIRED_VERSION && !spaceId) return { status: "invalid-space" };
    const keep = current.keep_bin_defaults === undefined ? true : current.keep_bin_defaults;
    const defaults = current.bin_defaults === undefined ? null : current.bin_defaults;
    const partDefaults = current.version <= 5 ? (current.part_defaults || {}) : current.part_defaults;
    if (typeof keep !== "boolean"
        || (defaults !== null && (typeof defaults !== "object" || Array.isArray(defaults)))
        || !partDefaults || typeof partDefaults !== "object" || Array.isArray(partDefaults)) {
      return { status: "invalid" };
    }
    // The exact resume checkpoint only exists from v8 on. /api/design/validate
    // remains the canonical design-schema validator on restore - this only
    // checks the top-level shape, same as the local backend's _metadata_resume.
    let resumeDesign = null;
    let resumePending = false;
    if (current.version >= RESUME_REQUIRED_VERSION) {
      resumeDesign = current.resume_design === undefined ? null : current.resume_design;
      if (resumeDesign !== null && (typeof resumeDesign !== "object" || Array.isArray(resumeDesign))) {
        return { status: "invalid" };
      }
      // A missing/explicit-null resume_design normalizes to null, but a v8
      // typed Space must carry a literal boolean resume_pending - a missing
      // field is malformed metadata, not a silent "not pending" - see
      // Fix 032 Correction 1.
      if (typeof current.resume_pending !== "boolean") return { status: "invalid" };
      resumePending = resumeDesign === null ? false : current.resume_pending;
    }
    // A stored legacy "box" identity always requires the explicit
    // migration/setup pass, even inside an otherwise fully-valid v4 +
    // setup_version-1 file left over from an earlier incomplete Fix 004
    // build - see Fix 004 Correction 8.D. A Surface missing its validated
    // trim_size is likewise recoverable migration input - Correction 11.A4.
    const surfaceNeedsMigration = space.kind === "surface" && !space.trim_size;
    const spaceNeedsMigration = needsMigration || space.kind === "box" || surfaceNeedsMigration;
    return {
      status: "space", space, space_id: spaceId,
      needsIdentityMigration: current.version < SPACE_ID_REQUIRED_VERSION && !spaceNeedsMigration,
      inventory: true, keep_bin_defaults: keep, bin_defaults: defaults,
      part_defaults: partDefaults, needsMigration: spaceNeedsMigration,
      metadataVersion: current.version,
      resume_design: resumeDesign, resume_pending: resumePending,
      structural_outputs: current.structural_outputs && typeof current.structural_outputs === "object"
        && !Array.isArray(current.structural_outputs) ? current.structural_outputs : {},
      cabinet_recovery: recovering ? { message: recovering.message } : null,
    };
  }
  return { status: "invalid" };
};

SP.classifyLegacyMetadata = record => {
  if (!record?.exists) return { status: "missing" };
  if (record.error || !record.data || typeof record.data !== "object" || Array.isArray(record.data)) {
    return { status: "invalid" };
  }
  const space = SP.validSpace(record.data);
  if (space) return { status: "space", space };
  if (record.data.kind === "none") return { status: "design" };
  return { status: "invalid" };
};

SP.metadataError = status => {
  if (status === "unsupported") return new Error("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.");
  if (status === "invalid-space") return new Error("This folder's Space information is incomplete or damaged. Nothing was changed.");
  return new Error("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.");
};

// Every SP.writeMetadata() call is a read/preserve/write transaction against
// the same file. Serialized through one promise-chain queue so a resume
// checkpoint save (from a background preview) can never race a rename/
// defaults/version-upgrade write and read the same stale file - see Fix 032.
// A rejected write must not poison the tail: the caller still gets its own
// rejection, but later queued writes still run.
SP._metadataWriteQueue = Promise.resolve();
SP._serializeMetadataWrite = task => {
  const result = SP._metadataWriteQueue.then(task, task);
  SP._metadataWriteQueue = result.then(() => {}, () => {});
  return result;
};

// `options.preserveSpace`/`options.expectedSpaceId` (Fix 032 Correction 4,
// C4.1): serialization alone does not stop a caller from writing back a
// Space definition it captured before this transaction's own read. With
// `preserveSpace: true`, the `space` argument is ignored and the CURRENT
// on-disk Space definition (read inside this same serialized transaction)
// is written back instead; `expectedSpaceId` additionally refuses to write
// at all if that current Space's id no longer matches what the caller
// captured - it must never create/recreate a Space under a new UUID.
SP.writeMetadata = (handle, mode, space = null, inventory = true, changes = {}, options = {}) =>
  SP._serializeMetadataWrite(() => SP._writeMetadataNow(handle, mode, space, inventory, changes, options));

SP._writeMetadataNow = async (handle, mode, space = null, inventory = true, changes = {}, options = {}) => {
  const { preserveSpace = false, expectedSpaceId = null } = options;
  if (!handle) {
    throw new Error("Inventory and Spaces need access to a writable folder.");
  }
  const hasSpace = Boolean(space) || preserveSpace;
  // A Space's layout depends on the inventory, so it is never optional here.
  const metadata = {
    version: FOLDER_METADATA_VERSION, setup_version: SPACE_SETUP_VERSION,
    folder_mode: mode,
  };
  if (mode !== "space" || !hasSpace) metadata.inventory = Boolean(inventory);
  if (mode === "space" && hasSpace) {
    let spaceId = null;
    let keep = true;
    let defaults = null;
    let partDefaults = {};
    let resumeDesign = null;
    let resumePending = false;
    let currentSpace = null;
    let structuralOutputs = {};
    const { current } = await SP.readMetadata(handle);
    const currentState = SP.classifyMetadata(current);
    if (!["missing", "design", "space"].includes(currentState.status)) throw SP.metadataError(currentState.status);
    if (currentState.status === "space") {
      keep = currentState.keep_bin_defaults;
      defaults = currentState.bin_defaults;
      partDefaults = currentState.part_defaults || {};
      // The identity choke point: keep an existing ID, only new or pre-v5
      // Spaces may get one. (A damaged v5 already threw above.)
      spaceId = currentState.space_id;
      resumeDesign = currentState.resume_design ?? null;
      resumePending = Boolean(currentState.resume_pending);
      currentSpace = currentState.space;
      structuralOutputs = { ...(currentState.structural_outputs || {}) };
    }
    if ((preserveSpace || expectedSpaceId) && currentState.status !== "space") {
      throw new Error("This Space no longer exists in that folder. Nothing was changed.");
    }
    if (expectedSpaceId && spaceId !== expectedSpaceId) {
      throw new Error("This folder is not the Space that was open before. Nothing was changed.");
    }
    const resolvedSpace = preserveSpace ? currentSpace : space;
    if (!resolvedSpace) {
      throw new Error("This folder is not the Space that was open before. Nothing was changed.");
    }
    if (Object.hasOwn(changes, "keep_bin_defaults")) keep = Boolean(changes.keep_bin_defaults);
    if (Object.hasOwn(changes, "bin_defaults")) defaults = changes.bin_defaults;
    if (Object.hasOwn(changes, "part_defaults")) partDefaults = changes.part_defaults;
    if (Object.hasOwn(changes, "resume_design")) resumeDesign = changes.resume_design;
    if (Object.hasOwn(changes, "resume_pending")) resumePending = Boolean(changes.resume_pending);
    if (defaults !== null && (typeof defaults !== "object" || Array.isArray(defaults))) {
      throw new Error("Bin defaults must be an object or null.");
    }
    if (!partDefaults || typeof partDefaults !== "object" || Array.isArray(partDefaults)) {
      throw new Error("Part defaults must be an object.");
    }
    if (resumeDesign !== null && (typeof resumeDesign !== "object" || Array.isArray(resumeDesign))) {
      throw new Error("The Space resume design must be an object or null.");
    }
    if (resumeDesign === null) resumePending = false;
    // Fix 084B: structural-output manifests survive every ordinary write; an
    // explicit update merges/deletes only its named keys, inside this same
    // serialized read-modify-write.
    if (Object.hasOwn(changes, "structural_output_updates")) {
      for (const [key, value] of Object.entries(changes.structural_output_updates || {})) {
        if (value === null) delete structuralOutputs[key];
        else structuralOutputs[key] = value;
      }
    }
    metadata.space_id = spaceId || crypto.randomUUID();
    metadata.inventory = true;
    metadata.space = resolvedSpace;
    metadata.keep_bin_defaults = keep;
    metadata.bin_defaults = defaults;
    metadata.part_defaults = partDefaults;
    metadata.resume_design = resumeDesign;
    metadata.resume_pending = resumePending;
    if (Object.keys(structuralOutputs).length) metadata.structural_outputs = structuralOutputs;
  }
  await WFFileSystem.writeText(handle, FOLDER_METADATA, JSON.stringify(metadata, null, 2));
  return metadata;
};

// ------------------------------------------------ exact resume checkpoint
//
// A typed Space's exact-design resume checkpoint (Fix 032). One coalescing
// slot, not a per-Space queue: SP.applyFolder always flushes whatever is
// queued/in-flight for the outgoing Space before it changes state.output/
// state.activeSpaceId (see SP.flushOutgoingResumeCheckpoint below), so only
// one Space is ever actively queuing at a time - Space A and Space B are
// never coalesced into the same slot, and a stale Space-A completion is
// still gated by identity before it is allowed to overwrite in-memory state.
SP._resume = {
  latest: null,          // { target, design, pending, key, waiters } - queued, unsent
  inFlight: null,         // the write currently in progress, if any
  savedKey: new Map(),   // space_id -> dedupe key of the last value actually saved
};

// A queued item a background save is about to replace, discarded before it
// was ever written under its own content, tells whoever was waiting on it
// (an explicit SP.flushResumeCheckpoint() caller) rather than leaving it
// hanging silently - see Correction 1.
SP._rejectSupersededWaiters = () => {
  const waiters = SP._resume.latest?.waiters;
  if (!waiters?.length) return;
  const error = new Error("a newer design replaced this save before it was written");
  waiters.forEach(w => w.reject(error));
};

// Captured synchronously, before any await - never resolved from mutable
// global state after a wait, so a queued write always targets the exact
// Space that owned the design when it was queued.
SP._captureResumeTarget = () => {
  if (state.folderMode !== "space" || !state.activeSpace || !state.activeSpaceId) return null;
  return {
    spaceId: state.activeSpaceId,
    // Cloned so the queued target is immutable - a later in-place edit to
    // state.activeSpace (e.g. a rename/resize) must not retroactively
    // change what an already-queued write sends (Fix 032 Correction 2,
    // item 9).
    space: clone(state.activeSpace),
    output: state.output,
    browserFolder: state.browserFolder,
    hosted: Boolean(state.runtime.hosted),
  };
};

SP._resumeMatchesActive = target =>
  state.folderMode === "space" && state.activeSpaceId === target.spaceId;

SP._writeResumeCheckpointNow = async (target, design, pending) => {
  if (target.hosted) {
    // A missing captured folder handle must throw, not silently resolve as
    // though the design were saved - an explicit flush must never mark
    // itself/its dedupe key successful when nothing was actually written
    // (Fix 032 Correction 2, item 10).
    if (!target.browserFolder?.handle) {
      throw new Error("This Space has no writable folder access in this browser session.");
    }
    // preserveSpace/expectedSpaceId: this transaction owns only the resume
    // fields, never the Space definition - never write back the possibly-
    // stale target.space captured when this write was queued, and never
    // recreate a Space under a new id if it disappeared/changed identity in
    // the meantime (Fix 032 Correction 4, C4.1).
    await SP.writeMetadata(target.browserFolder.handle, "space", null, true, {
      resume_design: design, resume_pending: pending,
    }, { preserveSpace: true, expectedSpaceId: target.spaceId });
  } else {
    // space_id lets the local /api/space/resume route refuse to write if
    // this Space is no longer the one on disk at that output path, instead
    // of writing into whatever Space is there now (Fix 032 Correction 4,
    // C4.1).
    await api("/api/space/resume", {
      output: target.output, space_id: target.spaceId,
      resume_design: design, resume_pending: pending,
    });
  }
};

SP._pumpResumeQueue = () => {
  if (SP._resume.inFlight) return SP._resume.inFlight;
  const item = SP._resume.latest;
  if (!item) return Promise.resolve();
  SP._resume.latest = null;
  SP._resume.inFlight = SP._writeResumeCheckpointNow(item.target, item.design, item.pending)
    .then(() => {
      SP._resume.savedKey.set(item.target.spaceId, item.key);
      // The file write for an outgoing Space may finish after a switch;
      // that is fine. Adopting it into memory only when that Space is still
      // active is what stops a late completion overwriting a newer Space's
      // in-memory checkpoint.
      if (SP._resumeMatchesActive(item.target)) {
        state.spaceResumeDesign = clone(item.design);
        state.spaceResumePending = item.pending;
      }
      item.waiters.forEach(w => w.resolve());
    })
    .catch(error => {
      // A rejected write must not poison the tail - the queue recovers so
      // later writes still run. A background autosave has no waiter, so
      // this generic toast is its only report; an explicit
      // SP.flushResumeCheckpoint() caller instead gets its own rejection
      // through its waiter, and OWNS the user-facing message from there -
      // reporting both here and at the caller would duplicate/contradict
      // it (Fix 032 Correction 2, C2.3). The same ownership hand-off
      // applies when an explicit flush is already queued up BEHIND this
      // failing background write for the same Space (e.g. the preview
      // autosave that immediately precedes a Surface first-bin flush) -
      // that upcoming call owns the one warning, so stay silent here too
      // (Fix 032 Correction 3, C3.3).
      const nextOwnsMessage = Boolean(SP._resume.latest?.waiters.length);
      if (!item.waiters.length && !nextOwnsMessage) {
        toast(`The current design could not be saved to this Space: ${error.message}`, true, 6000);
      }
      item.waiters.forEach(w => w.reject(error));
    })
    .then(() => {
      SP._resume.inFlight = null;
      if (SP._resume.latest) return SP._pumpResumeQueue();
    });
  return SP._resume.inFlight;
};

// Background autosave choke point - call only after a fully valid preview
// (see refreshPreview in web/app.js). Coalesces with whatever is already
// queued for the same Space and skips an exact duplicate of the last value
// actually saved for it. Fire-and-forget: never blocks the caller, and a
// failure is reported as its own toast, not thrown.
SP.queueResumeCheckpoint = (design, pending) => {
  if (state.relocating) return;
  const target = SP._captureResumeTarget();
  if (!target) return;
  const key = `${pending ? 1 : 0}:${JSON.stringify(design)}`;
  if (SP._resume.savedKey.get(target.spaceId) === key) return;
  if (SP._resume.latest?.target.spaceId === target.spaceId && SP._resume.latest.key === key) return;
  SP._rejectSupersededWaiters();
  SP._resume.latest = { target, design: clone(design), pending: Boolean(pending), key, waiters: [] };
  SP._pumpResumeQueue();
};

// Explicit/deterministic persistence for Generate/Print and for leaving a
// Space. Unlike the background autosave path, this one is observable: it
// rejects if the exact requested checkpoint could not be durably saved, so
// its caller (Generate/Print) can refuse to proceed, or to report itself
// fully complete, on that specific failure - see Correction 1. It never
// poisons the shared queue - other pending/future writes still run.
SP.flushResumeCheckpoint = (design, pending) => {
  const target = SP._captureResumeTarget();
  if (!target) return Promise.resolve();
  const key = `${pending ? 1 : 0}:${JSON.stringify(design)}`;
  return new Promise((resolve, reject) => {
    SP._rejectSupersededWaiters();
    SP._resume.latest = {
      target, design: clone(design), pending: Boolean(pending), key,
      waiters: [{ resolve, reject }],
    };
    SP._pumpResumeQueue();
  });
};

// Waits out whatever is queued/in-flight before SP.applyFolder changes
// state.output/state.activeSpaceId to a different folder/Space. Best-effort:
// a failure here already toasted itself via the queue and must not block
// the folder switch the user asked for.
SP.flushOutgoingResumeCheckpoint = () => SP._pumpResumeQueue();

// ------------------------------------------------ Space preference memory (Fix 053)
//
// A typed Space always remembers its last-used bin and per-kind part settings
// in `bin_defaults` / `part_defaults`. Every write is a serialized transaction
// that names the Space it was queued for (captured synchronously, like the
// resume checkpoint), so a late write can never land in a Space the user has
// since left. Queued-but-unstarted writes for the same Space coalesce.
SP._defaults = { chain: Promise.resolve(), tail: null };

SP._writeDefaultsNow = async (target, changes) => {
  const updates = {};
  if (Object.hasOwn(changes, "bin_defaults")) updates.bin_defaults = changes.bin_defaults;
  if (Object.hasOwn(changes, "part_defaults")) updates.part_defaults = changes.part_defaults;
  if (!Object.keys(updates).length) return;
  if (target.hosted) {
    if (!target.browserFolder?.handle) {
      throw new Error("This Space has no writable folder access in this browser session.");
    }
    await SP.writeMetadata(target.browserFolder.handle, "space", null, true, updates, {
      preserveSpace: true, expectedSpaceId: target.spaceId,
    });
  } else {
    await api("/api/space/defaults", {
      output: target.output, space_id: target.spaceId, ...updates,
    });
  }
};

SP.queueDefaults = changes => {
  if (state.relocating) return;
  const target = SP._captureResumeTarget();
  if (!target) return;
  const queue = SP._defaults;
  const last = queue.tail;
  if (last && !last.started && last.target.spaceId === target.spaceId) {
    last.changes = { ...last.changes, ...changes };
    return;
  }
  const item = { target, changes: { ...changes }, started: false };
  queue.tail = item;
  queue.chain = queue.chain.then(async () => {
    item.started = true;
    if (queue.tail === item) queue.tail = null;
    try {
      await SP._writeDefaultsNow(item.target, item.changes);
    } catch (error) {
      toast(`This bin was saved, but the Space's remembered settings were not: ${error.message}`, true, 6000);
    }
  });
};

// Resolves once everything queued so far has been written (a failure already
// toasted itself and never blocks leaving a bin or Space).
SP.flushDefaults = () => SP._defaults.chain;

// The one place hosted code reads a folder's inventory. Mirrors the local
// organizer_inventory.resolve_inventory_path: the canonical file wins, exactly
// one old "<name> bins.md" is adopted (renamed only when migrate is true, and
// only after the canonical copy is written), and anything ambiguous stops
// instead of creating a second, empty inventory. Always operates on the
// handle it is given - never the previously-active folder.
SP.readInventoryFor = async (folder, { migrate = false } = {}) => {
  const handle = folder?.handle;
  if (!handle) {
    throw new Error("Inventory and Spaces need access to a writable folder.");
  }
  const names = await WFFileSystem.listFilenames(handle);
  const legacy = names.filter(name => name !== INVENTORY_FILENAME && name.endsWith(LEGACY_INVENTORY_SUFFIX));
  const conflict = () => new Error("Multiple Wavefinity inventory files were found; nothing was changed.");
  if (names.includes(INVENTORY_FILENAME)) {
    const text = await WFFileSystem.readText(handle, INVENTORY_FILENAME) || "";
    for (const name of legacy) {
      if ((await WFFileSystem.readText(handle, name)) !== text) throw conflict();
    }
    if (migrate) for (const name of legacy) await WFFileSystem.removeFile(handle, name);
    return text;
  }
  if (!legacy.length) return "";
  if (legacy.length !== 1) throw conflict();
  const text = await WFFileSystem.readText(handle, legacy[0]) || "";
  if (migrate) {
    await WFFileSystem.writeText(handle, INVENTORY_FILENAME, text);
    await WFFileSystem.removeFile(handle, legacy[0]);
  }
  return text;
};

SP._inventoryWriteChain = Promise.resolve();
SP.inventoryRequest = async (path, extra = {}, { write = true, context = null } = {}) => {
  const folder = state.browserFolder;
  const handle = folder?.handle;
  if (!handle) throw new Error("Keeping an inventory needs folder access so Wavefinity can save it with your designs.");
  const title = state.activeSpace?.name || folder.name;
  const spaceId = state.activeSpaceId || null;
  const requireContext = () => {
    if (state.browserFolder !== folder || state.browserFolder?.handle !== handle ||
        (state.activeSpaceId || null) !== spaceId ||
        (context && !DL.spaceContextCurrent(context))) {
      throw DL.staleSpaceError();
    }
  };
  const run = async () => {
    requireContext();
    const inventoryText = await SP.readInventoryFor({ ...folder, handle }, { migrate: write });
    const deleting = path === "/api/drawer/save" && Boolean(extra.delete_ids?.length);
    const needsFilenameSnapshot = deleting || path === "/api/drawer/design-source/save";
    requireContext();
    const availableFilenames = needsFilenameSnapshot ? await WFFileSystem.listFilenames(handle) : [];
    requireContext();
    const data = await api(path, {
      inventory_text: inventoryText,
      inventory_title: title,
      ...extra,
      ...(needsFilenameSnapshot ? { available_filenames: availableFilenames } : {}),
    });
    requireContext();
    if (write && typeof data.inventory_text === "string") {
      await WFFileSystem.writeText(handle, INVENTORY_FILENAME, data.inventory_text);
    }
    if (deleting && data.cleanup_files?.length) {
      const failed = [];
      for (const name of data.cleanup_files) {
        requireContext();
        if (!availableFilenames.includes(name)) continue;
        try {
          await WFFileSystem.removeFile(handle, name);
        } catch (error) {
          if (error?.name !== "NotFoundError") failed.push(name);
        }
      }
      if (failed.length) data.cleanup_failed = failed;
    }
    return data;
  };
  const pending = SP._inventoryWriteChain.then(run, run);
  if (write) SP._inventoryWriteChain = pending.catch(() => {});
  return pending;
};

// Fix 034 F1: hosted Generate/Print has no server folder to write to
// directly, so the browser appends the row itself, then (when the generator
// supplied a canonical design) attaches it as that row's design_specs entry
// so a spec-only Wavefinity row stays reloadable even without Save to Space.
SP.addInventoryBin = async (entry, designSpec = null) => {
  let data = await SP.inventoryRequest("/api/drawer/save", { new_bins: [entry] });
  if (designSpec) {
    const added = (data.bins || []).find(one => one.file === entry.file);
    if (added) {
      data = await SP.inventoryRequest("/api/drawer/design-source/save", {
        design: designSpec, row_id: added.id,
      });
      if (entry.file) {
        data = await SP.inventoryRequest("/api/drawer/design-source/status", {
          row_id: data.row_id, action: "saved", file: entry.file, design: data.design,
        });
      }
    }
  }
  if (typeof DL !== "undefined" && DL.active) {
    DL.adopt(data);
    DL.exists = true;
    DL.emit();
  }
};

// Read-only classification of a hosted folder's Space/Design status. Never
// writes metadata or inventory - inspecting a folder must never silently
// onboard/migrate it (see Fix 004 Correction 6.E). Only an explicit
// Create/Configure Existing/Use Untyped action may write - see SP.create()
// and SP.useUntypedFolder().
SP.inspectHosted = async folder => {
  const { current, legacy } = await SP.readMetadata(folder.handle);
  const currentState = SP.classifyMetadata(current);
  const legacyState = SP.classifyLegacyMetadata(legacy);
  const inventoryText = await SP.readInventoryFor(folder, { migrate: false });
  let inventorySpace = null;
  let inventorySpaceInferred = false;
  if (inventoryText) {
    const data = await api("/api/drawer/load", {
      inventory_text: inventoryText,
      inventory_title: folder.name,
    });
    inventorySpace = SP.validSpace(data.layout?.space);
    inventorySpaceInferred = Boolean(data.space_inferred);
  }
  // An explicit layout.space is a genuine candidate, not automatic authority:
  // completed current Design metadata still outranks it. One the server had
  // to infer from the drawer layout alone (no layout.space at all) can only
  // ever guess "drawer" - it must not outrank real Box metadata below, so it
  // is only considered as a last resort further down.
  const genuineInventorySpace = inventorySpace && !inventorySpaceInferred;
  // A completed current Design marker is authoritative: stale inventory or
  // legacy data may prefill a setup card, but cannot convert the folder back
  // into a typed Space - mirrors organizer_spaces._folder_state.
  const currentDesignAuthoritative =
    currentState.status === "design" && !currentState.needsMigration;

  // Damaged/future current metadata stops the folder outright, before
  // anything falls through to the legacy file.
  if (!["missing", "design", "space"].includes(currentState.status)) {
    throw SP.metadataError(currentState.status);
  }
  // Legacy is only actually consulted once nothing more authoritative
  // (an explicit layout.space, or current metadata already saying "space")
  // has settled things - and once consulted, a damaged legacy file must
  // stop the folder too, not be silently skipped just because a stale
  // current "design" marker happens to be sitting next to it.
  const legacyMatters =
    !currentDesignAuthoritative &&
    !genuineInventorySpace &&
    currentState.status !== "space";
  if (legacyMatters && legacyState.status === "invalid") {
    throw SP.metadataError(legacyState.status);
  }

  let mode;
  let space = null;
  let inventory = true;
  let keepBinDefaults = true;
  let binDefaults = null;
  let partDefaults = {};
  let needsSetup = false;
  let spaceId = null;
  let needsIdentity = false;
  // Where a typed result's authority came from: "metadata"/"legacy_metadata"
  // are committed types; "inventory_layout"/"inventory_inferred" are only
  // candidates. A prefill is suggestion-only and never the active space.
  let spaceSource = null;
  let setupPrefillSpace = null;
  let resumeDesign = null;
  let resumePending = false;
  if (currentDesignAuthoritative) {
    mode = "design";
    // A folder saved before this preference existed keeps inventory on by default.
    inventory = currentState.inventory === null ? true : currentState.inventory;
    setupPrefillSpace = inventorySpace || null;
    needsSetup = currentState.inventory === null;
  } else if (genuineInventorySpace) {
    mode = "space";
    space = inventorySpace;
    if (currentState.status === "space") {
      spaceSource = "metadata";
      keepBinDefaults = currentState.keep_bin_defaults;
      binDefaults = currentState.bin_defaults;
      partDefaults = currentState.part_defaults || {};
      spaceId = currentState.space_id;
      needsIdentity = currentState.needsIdentityMigration;
      resumeDesign = currentState.resume_design || null;
      resumePending = Boolean(currentState.resume_pending);
      // Already valid current v4/v5 setup_version-1 metadata: the inventory's
      // own explicit layout.space is only the values source here, not a
      // reason to force setup again - mirrors organizer_spaces._folder_state.
      needsSetup = currentState.needsMigration;
    } else {
      spaceSource = "inventory_layout";
      needsSetup = true;
    }
  } else if (currentState.status === "space") {
    mode = "space";
    space = currentState.space;
    spaceSource = "metadata";
    keepBinDefaults = currentState.keep_bin_defaults;
    binDefaults = currentState.bin_defaults;
    partDefaults = currentState.part_defaults || {};
    spaceId = currentState.space_id;
    needsIdentity = currentState.needsIdentityMigration;
    resumeDesign = currentState.resume_design || null;
    resumePending = Boolean(currentState.resume_pending);
    needsSetup = currentState.needsMigration;
  } else if (legacyState.status === "space") {
    // A stale or absent current "design" marker must not hide a genuine
    // legacy Space identity - a current "design" marker is not a positive
    // Space identity, only current "space" metadata (handled above) is.
    mode = "space";
    space = legacyState.space;
    spaceSource = "legacy_metadata";
    needsSetup = true;
  } else if (currentState.status === "design") {
    mode = "design";
    inventory = currentState.inventory === null ? true : currentState.inventory;
    setupPrefillSpace = inventorySpace || null;
    needsSetup = currentState.needsMigration || currentState.inventory === null;
  } else if (legacyState.status === "design") {
    mode = "design";
    setupPrefillSpace = inventorySpace || null;
    needsSetup = true;
  } else if (inventorySpace) {
    // No authoritative metadata anywhere: fall back to the layout-only
    // inference (always "drawer" - there is no Box concept for it to recover).
    mode = "space";
    space = inventorySpace;
    spaceSource = "inventory_inferred";
    needsSetup = true;
  } else {
    mode = "design";
    needsSetup = true;
  }

  // A stored legacy "box" identity always requires the explicit
  // migration/setup pass, whichever path above produced it - see Fix 004
  // Correction 8.D.
  if (mode === "space" && space?.kind === "box") needsSetup = true;
  // A Surface missing its validated trim_size is recoverable migration
  // input, not a corrupt file - see Fix 004 Correction 11.A4.
  if (mode === "space" && space?.kind === "surface" && !space.trim_size) {
    needsSetup = true;
  }
  if (needsSetup) needsIdentity = false;
  // An exact resume checkpoint only ever comes from current v8+ typed-Space
  // metadata (spaceSource === "metadata"); a legacy/inferred Space or one
  // still needing setup has none - mirrors organizer_spaces.describe().
  const hasResumeCheckpoint = mode === "space" && spaceSource === "metadata" && !needsSetup;

  return {
    folder: folder.name,
    folder_name: folder.name,
    folder_mode: mode,
    space,
    space_id: mode === "space" ? spaceId : null,
    needs_identity_migration: mode === "space" && needsIdentity,
    space_source: spaceSource,
    setup_prefill_space: setupPrefillSpace,
    resume_design: hasResumeCheckpoint ? resumeDesign : null,
    resume_pending: hasResumeCheckpoint ? resumePending : false,
    metadata_version: currentState.metadataVersion || null,
    inventory: mode === "space" ? true : inventory,
    keep_bin_defaults: mode === "space" ? keepBinDefaults : false,
    bin_defaults: mode === "space" ? binDefaults : null,
    part_defaults: mode === "space" ? partDefaults : {},
    cabinet_recovery: mode === "space" ? (currentState.cabinet_recovery || null) : null,
    missing: false,
    needs_setup: needsSetup,
    inventory_text: inventoryText,
    // The browser-owned equivalent of local describe()'s inventory-exists
    // flag, for the explicit Configure-vs-Choose-Another confirmation - see
    // Fix 004 Correction 7.C.
    exists: Boolean(inventoryText) || currentState.status !== "missing" || legacyState.status !== "missing",
  };
};

// A saved browser record that names a Space ID must be proven by the folder
// itself before anything in that folder is migrated, set up or opened. A
// record from before Fix 006 has no ID and is allowed through.
SP.assertExpectedHostedIdentity = (info, expectedSpaceId) => {
  if (!expectedSpaceId) return;
  if (info.space_id !== expectedSpaceId) {
    throw new Error("This folder is not the Space that was open before. Use Open Existing Space to choose it.");
  }
};

SP.useHostedFolder = async (folder, { expectedSpaceId = null, skipLeaveCheck = false, openPreferredView = false } = {}) => {
  // A hosted Design session without a persistent folder is "no folder
  // selected", never a fabricated one. Opening a Wavefinity folder therefore
  // always needs a real handle.
  if (!folder?.handle) {
    throw new Error("Opening a Wavefinity folder requires writable folder access.");
  }
  // Read-only classification of the target folder only - no write yet.
  let info = await SP.inspectHosted(folder);
  SP.assertExpectedHostedIdentity(info, expectedSpaceId);

  // Leave the old Drawer layout safely BEFORE any write to the target
  // folder - the inventory-filename migration and metadata version upgrade
  // just below - or adoption of it as the active folder/handle (Fix 019
  // correction C1.3). Cancel or a failed save must abort here, leaving the
  // target folder and the previously active folder/handle untouched.
  // skipLeaveCheck is set only by a caller that already resolved this exact
  // decision itself immediately beforehand (e.g. hosted
  // SP.useUntypedFolder(), which must write the target's own metadata
  // before calling in here) - it must never be used to skip the decision
  // itself, only to avoid asking twice.
  if (!skipLeaveCheck) {
    const ok = await SP.leaveDrawerLayoutSafely();
    if (!ok) return null;
  }

  // The hosted equivalent of the local technical open: only after read-only
  // classification says no setup is needed, adopt the canonical inventory
  // filename and give a configured v4 folder its v5 identity.
  if (!info.needs_setup) {
    if (info.inventory) await SP.readInventoryFor(folder, { migrate: true });
    const upgradeSpace = info.folder_mode === "space" && (
      info.needs_identity_migration || (info.metadata_version || 0) < FOLDER_METADATA_VERSION
    );
    const upgradeDesign = info.folder_mode === "design" && info.metadata_version && info.metadata_version < FOLDER_METADATA_VERSION;
    if (upgradeSpace) {
      // `info` was read by SP.inspectHosted() just above, outside this
      // write's own serialized transaction - preserveSpace re-reads the
      // current Space definition (and leaving keep/bin/part defaults unset
      // re-reads those too) instead of writing back this possibly-stale
      // copy over a concurrent rename/resize (Fix 032 Correction 4, C4.1).
      await SP.writeMetadata(folder.handle, "space", null, true, {}, { preserveSpace: true });
    } else if (upgradeDesign) {
      await SP.writeMetadata(folder.handle, "design", null, info.inventory);
    }
    if (upgradeSpace || upgradeDesign) info = await SP.inspectHosted(folder);
  }
  if (expectedSpaceId && info.space_id !== expectedSpaceId) {
    throw new Error("This folder is not the Space that was open before. Use Open Existing Space to choose it.");
  }
  // The safe-leave decision is already resolved above - clear the old
  // Drawer state exactly once, with no second prompt.
  if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return null;
  // This only writes the remembered-active record; it does not mutate the
  // live editor identity, so it may run before the atomic identity
  // transition below (Fix 032 Correction 2, item 7). state.browserFolder
  // itself is set inside SP.applyFolder(), never here.
  await WFFileSystem.save("active", { handle: folder.handle, space_id: info.space_id || null });
  await SP.applyFolder(info, { reset: false, browserFolder: folder });
  SP.close();
  if (openPreferredView && info.folder_mode === "space") {
    if (!(await SP.openTypedSpacePreferredView())) return null;
  }
  toast(info.folder_mode === "space"
    ? `Opened ${info.space.name || folder.name}.`
    : `Saving designs to ${folder.name}.`);
  return info;
};

// ------------------------------------------------------------ folder choice

// Returns a real folder or null - never a pretend one. With stayOnSetup the
// caller is mid-setup, so a refusal explains itself inline instead of
// throwing the person's entered Space details away.
SP.pickFolder = async ({ stayOnSetup = false, spaceRoot = false, accessContext = null } = {}) => {
  if (state.runtime.hosted) {
    if (!window.WFFileSystem?.supportsDirectoryPicker()) {
      if (stayOnSetup) {
        SP.fail(
          "This browser cannot give Wavefinity writable folder access. Your Space details have not been changed.",
          "#space-create",
        );
      } else {
        SP.showFolderAccessNeeded("unsupported", accessContext);
      }
      return null;
    }

    const picked = await WFFileSystem.pickDirectory();
    // A cancel is silent and leaves everything as it was.
    if (!picked || picked.status === "cancelled") return null;

    if (picked.status !== "ok" || !picked.handle) {
      if (stayOnSetup) {
        SP.fail(
          "Folder access was not granted. Your Space details are still here; choose the folder again and allow read/write access.",
          "#space-create",
        );
      } else {
        SP.showFolderAccessNeeded(
          picked.status === "denied" ? "denied" : "unsupported",
          accessContext,
        );
      }
      return null;
    }

    return { handle: picked.handle, name: picked.handle.name };
  }

  const data = await api("/api/browse-output-folder", {
    current: state.output,
    space_root: Boolean(spaceRoot),
  });
  return data.folder || null;
};

// Safe for every caller (Recents, Open Existing, collision "Open this
// Space", Choose Folder, etc.): a folder that still needs its one-time
// setup pass - including a legacy box, v2/v3, or migration-needed Space -
// is never applied/opened directly; it always goes through the explicit
// setup/migration flow first - see Fix 004 Correction 9.B.
SP.afterPick = async folder => {
  if (!folder) return null;
  if (state.runtime.hosted) {
    // A hosted object with no handle is not a folder and is never adopted.
    if (!folder.handle) {
      SP.showFolderAccessNeeded("unsupported");
      return null;
    }
    const inspected = await SP.inspectHosted(folder);
    if (inspected.needs_setup) {
      SP.enterSetupFor(folder, inspected);
      return inspected;
    }
    return SP.useHostedFolder(folder, { openPreferredView: true });
  }
  const inspected = await api("/api/space/inspect", { output: folder });
  SP.recent = inspected.recent || [];
  if (inspected.folder?.needs_setup) {
    SP.enterSetupFor(folder, inspected.folder);
    return inspected.folder;
  }
  // Resolve the safe-leave decision BEFORE the backend remembers this
  // folder as active (Fix 019 correction C1.2) - Cancel or a failed save
  // must abort before /api/folder/use ever runs, so the backend's
  // remembered active folder/Space cannot get ahead of what is on screen.
  const okToLeave = await SP.leaveDrawerLayoutSafely();
  if (!okToLeave) return null;
  const data = await api("/api/folder/use", { output: folder });
  SP.recent = data.recent || [];
  // The leave decision is already resolved - clear the old Drawer state
  // exactly once, with no second prompt, then adopt the new folder.
  if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return null;
  if (!(await SP.applyFolder(data.folder, { reset: false }))) return null;
  SP.close();
  if (data.folder.folder_mode === "space") {
    if (!(await SP.openTypedSpacePreferredView())) return null;
  }
  toast(data.folder.folder_mode === "space"
    ? `Opened ${data.folder.space?.name || data.folder.folder_name}.`
    : `Saving designs to ${data.folder.folder_name}.`);
  return data.folder;
};

SP.chooseFolder = () => SP.run(async () => {
  const folder = await SP.pickFolder();
  if (folder) await SP.afterPick(folder);
});

// The opt-out checkbox beside the save folder. Space always keeps inventory
// on, and a hosted session with no persistent folder has nowhere to keep one,
// so the control is disabled in both cases (see setFolderState) - these
// checks just guard against a stray change event reaching here anyway.
SP.setInventory = enabled => SP.run(async () => {
  if (!SP.hasFolder() || state.folderMode === "space") return;
  if (state.runtime.hosted && !state.browserFolder?.handle) return;
  if (state.runtime.hosted) {
    await SP.writeMetadata(state.browserFolder?.handle, "design", null, enabled);
  } else {
    await api("/api/folder/inventory", { output: state.output, inventory: enabled });
  }
  state.inventoryEnabled = enabled;
  state.keepLog = enabled;
  toast(enabled ? "Keeping inventory for this folder." : "Inventory turned off for this folder.");
});

// Fix 034 K2: Keep bin defaults is retired (New Bin is always fresh;
// Duplicate is the explicit clone workflow) - old keep_bin_defaults/
// bin_defaults/part_defaults metadata keys are still read tolerantly on
// folder load elsewhere, but nothing writes or acts on them any more.

// ------------------------------------------------------------ welcome/manage

SP.renderRecent = () => {
  const list = $("#welcome-recent");
  if (!SP.recent.length) {
    list.innerHTML = `<li class="welcome-empty">No recent folders yet.</li>`;
    return;
  }
  list.innerHTML = SP.recent.map((one, index) => {
    const unavailable = one.missing || one.invalid || one.conflict;
    const space = one.folder_mode === "space";
    const kind = SP_KINDS[one.kind];
    const meta = [one.conflict ? "duplicate Space identity" : one.invalid ? "metadata unavailable" : space ? `${kind?.label || "Space"} · SPACE` : "Design folder", one.summary_text || SP.sizeText(one.size), one.missing ? "folder not found" : ""]
      .filter(Boolean).join(" · ");
    const current = spSame(one.folder, state.output) ? " <em>current</em>" : "";
    return `<li class="welcome-recent-item${unavailable ? " missing" : ""}">
      <button type="button" class="welcome-recent-open" data-index="${index}" title="${escapeHtml(one.folder)}"${unavailable ? " disabled" : ""}>
        <span class="welcome-recent-icon" aria-hidden="true">${space ? kind?.icon || "📦" : "📁"}</span>
        <span class="welcome-recent-text"><span><strong>${escapeHtml(one.name)}</strong>${current}</span>
          <small>${escapeHtml(meta)}</small><small>${escapeHtml(one.folder)}</small></span>
      </button>
      <button type="button" class="welcome-recent-forget" data-forget="${index}" title="Remove from this list" aria-label="Remove ${escapeHtml(one.name)} from recent folders">✕</button>
    </li>`;
  }).join("");
};

SP.renderOtherSpaces = () => {
  document.querySelectorAll("[data-other-spaces-container]").forEach(container => {
    container.hidden = state.runtime.hosted || SP.otherSpaces.length === 0;
    const list = container.querySelector("[data-other-spaces-list]");
    list.innerHTML = SP.otherSpaces.map((one, index) => {
      const kind = SP_KINDS[one.kind];
      const meta = [kind?.label || "Space", one.summary_text || SP.sizeText(one.size)].filter(Boolean).join(" · ");
      return `<li class="welcome-recent-item"><button type="button" class="welcome-recent-open" data-other-index="${index}" title="${escapeHtml(one.folder)}">
        <span class="welcome-recent-icon" aria-hidden="true">${kind?.icon || "📦"}</span>
        <span class="welcome-recent-text"><strong>${escapeHtml(one.name)}</strong><small>${escapeHtml(meta)}</small></span>
      </button></li>`;
    }).join("");
  });
};

SP.refreshOtherSpaces = async () => {
  if (state.runtime.hosted) return;
  try {
    SP.otherSpaces = (await api("/api/space/other-spaces", {})).other_spaces || [];
    SP.renderOtherSpaces();
  } catch (_error) {
    SP.otherSpaces = [];
    SP.renderOtherSpaces();
  }
};

SP.welcomeOtherSpaces = () => {
  SP.renderOtherSpaces();
  if (!SP.otherSpacesFresh) void SP.refreshOtherSpaces();
  SP.otherSpacesFresh = false;
};

SP.showResume = info => {
  SP.resume = info;
  SP.showOnly("welcome-resume");
  const space = info.space || {};
  const kind = SP_KINDS[space.kind] || SP_KINDS.drawer;
  $("#welcome-resume-icon").textContent = kind.icon;
  $("#welcome-resume-name").textContent = space.name || info.folder_name;
  $("#welcome-resume-meta").textContent = [kind.label, space.kind === "storage_drawers" ? SP.storageDrawersSummaryText(space) : SP.sizeText([space.x, space.y, space.z])].filter(Boolean).join(" · ");
  $("#welcome-resume-folder").textContent = info.folder;
  $("#welcome-resume-folder").title = info.folder;
  SP.renderStorageCard();
  SP.refreshStorage();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

// An existing Space lands by its loaded Inventory, without changing its
// restored design or making a second inventory parser.
SP.openTypedSpacePreferredView = async () => {
  try {
    if (!(await DL.ensureLoaded())) return false;
  } catch (error) {
    toast(`Could not read this Space's inventory: ${error.message}`, true, 7000);
    return false;
  }
  if (!(await DP.enter("space", true))) return false;
  const ordinary = DL.bins.filter(DL.isOrdinary);
  if (ordinary.length !== 1) return true;
  const row = ordinary[0];
  if (!DP.editableSourceFor(row)) return true;
  try {
    if (!(await DP.openInventoryRow(row.id))) {
      toast("Could not open this bin in Design. The Space is still open.", true, 7000);
    }
  } catch (error) {
    toast(`Could not open this bin in Design: ${error.message}`, true, 7000);
  }
  return true;
};

SP.confirmResume = async () => {
  if (await SP.openTypedSpacePreferredView()) SP.close();
};

// The current folder isn't a typed Space yet (e.g. the user tried to switch
// to the Drawer view). Route it through the same explicit setup flow as
// Open Existing/Configure Existing, using only screens that actually exist -
// the old "Space planning is optional" screen is gone, see Fix 004
// Correction 6.B.
SP.offerSpacePlanning = async () => {
  if (!SP.hasFolder()) return SP.showHome();
  if (!SP.canPersistSpace()) return SP.showFolderAccessNeeded();
  try {
    const folder = state.runtime.hosted ? state.browserFolder : state.output;
    const data = state.runtime.hosted
        ? await SP.inspectHosted(folder)
        : (await api("/api/space/inspect", { output: folder })).folder;
    SP.enterSetupFor(folder, data);
  } catch (error) {
    toast(error.message, true, 6000);
  }
};

// Capability-driven, never an OS or browser name: either this browser cannot
// give writable folder access at all, or access was not granted.
SP.showFolderAccessNeeded = (reason = "unsupported", context = null) => {
  const title = document.querySelector("#space-unsupported .welcome-header h2");
  const lead = document.getElementById("space-unsupported-lead");
  const detail = document.getElementById("space-unsupported-detail");
  // The "Design without a Space" flow must never lecture about Inventory
  // and Spaces: the user explicitly declined a Space. Tell them plainly
  // their work won't be saved to a folder, then let them design.
  if (context === "untyped") {
    if (title) title.textContent = "Designing without a saved folder";
    if (lead) lead.textContent = reason === "denied"
      ? "Wavefinity was not given read/write access to that folder."
      : "This browser cannot give Wavefinity ongoing read/write access to a chosen folder.";
    if (detail) detail.textContent =
      "You can still design and download parts normally — your work just won't be saved into a folder.";
  } else {
    if (title) title.textContent = "Inventory and Spaces need folder access";
    if (reason === "denied") {
      if (lead) lead.textContent =
        "Wavefinity was not given read/write access to that folder.";
      if (detail) detail.textContent =
        "You can still design and download parts normally. Choose the folder again and allow access to use Inventory and Spaces.";
    } else {
      if (lead) lead.textContent =
        "This browser cannot give Wavefinity ongoing read/write access to a chosen folder.";
      if (detail) detail.textContent =
        "You can still design and download parts normally. Inventory and Spaces require a browser that supports writable folder access.";
    }
  }
  SP.showOnly("space-unsupported");
  SP.showDialog();
};

SP.open = () => {
  if (state.folderMode === "space" && state.activeSpace) {
    return SP.showResume({
      folder: state.output,
      folder_name: state.browserFolder?.name || String(state.output).split(/[\\/]/).pop(),
      folder_mode: "space",
      space: state.activeSpace,
    });
  }
  return SP.offerSpacePlanning();
};

// ------------------------------------------------------------ setup


// `message`, when given, is a startup recovery error (Fix 019 Item 6) shown
// in #welcome-startup-error. Ordinary navigation to Welcome (no message)
// clears any previously-shown error.
SP.showHome = (message = null) => {
  SP.showOnly("welcome-home");
  const errorEl = document.getElementById("welcome-startup-error");
  if (errorEl) {
    errorEl.textContent = message || "";
    errorEl.hidden = !message;
  }
  SP.renderRecent();
  // Proactive, not just reactive: on a browser that cannot give writable
  // folder access, the Spaces screen itself says so up front — Spaces and
  // Inventory are unavailable here, but designing still works.
  const folderNotice = document.getElementById("welcome-folder-notice");
  if (folderNotice) {
    folderNotice.hidden = !(state.runtime.hosted && !window.WFFileSystem?.supportsDirectoryPicker());
  }
  const hasRecent = SP.recent.length > 0;
  document.getElementById("welcome-recent-container").hidden = !state.runtime.hosted || !hasRecent;
  SP.renderStorageCard();
  SP.refreshStorage();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

// The Wavefinity Folder control stays below the main Welcome actions.
SP.renderStorageCard = () => {
  const info = SP.storage;
  document.querySelectorAll("[data-storage-card]").forEach(el => {
    // The card also owns the printer settings, so it stays visible in hosted
    // mode; only the local Wavefinity Folder details come and go.
    const details = el.querySelector("[data-storage-folder-details]");
    const showFolder = !state.runtime.hosted && Boolean(info);
    if (details) details.hidden = !showFolder;
    el.toggleAttribute("data-folder-hidden", !showFolder);
    el.hidden = false;
    if (!showFolder) return;
    const lead = el.querySelector(".welcome-storage-lead");
    if (info.unavailable) {
      lead.textContent = "Your saved Space storage location could not be found. Choose a folder to continue.";
    } else if (!info.explicit) {
      lead.textContent = "Wavefinity folder: Documents (default)";
    } else {
      lead.textContent = "Wavefinity folder";
    }
    const path = el.querySelector(".welcome-storage-path");
    path.textContent = !info.unavailable && info.explicit ? info.root : "";
    path.hidden = !path.textContent;
    const leftover = el.querySelector(".welcome-storage-leftover");
    leftover.hidden = !info.leftover;
    leftover.textContent = info.leftover
      ? `An extra copy of Wavefinity data is still at ${info.leftover}. Wavefinity did not delete it. You can delete it yourself once you are sure you do not need it.`
      : "";
  });
  SP.mountPrinterProfiles?.();
};

// Quietly re-reads the storage state so the card never shows a stale root
// (for example right after the first Space creates the folder).
SP.refreshStorage = async () => {
  if (state.runtime.hosted) return;
  try {
    SP.storage = (await api("/api/space/storage-state", {})).storage || null;
  } catch (_error) {
    return;
  }
  SP.renderStorageCard();
};

// Change Location. With no Wavefinity folder yet (first run, or a missing saved
// location) there is nothing to move, so the chosen parent is simply saved.
// Otherwise the user picks a parent, sees the resulting folder, and chooses
// Move existing data or Use new location; a folder that already exists there
// is never merged or replaced (see SP.renderStoragePlan).
SP.storagePlan = null;
SP.storageReturn = "welcome-home";

SP.changeStorageParent = () => SP.run(SP.startStorageChange);

SP.startStorageChange = async () => {
  SP.storageReturn = $("#welcome-resume").hidden ? "welcome-home" : "welcome-resume";
  await SP.pickStorageParent();
};

SP.pickStorageParent = async () => {
  const picked = await api("/api/space/browse-storage-parent", { pick_only: true });
  if (!picked.folder) return; // a cancel is a no-op
  const data = await api("/api/space/storage-plan", { parent: picked.folder });
  if (data.plan.same) {
    toast("That is already your Wavefinity folder.");
    return;
  }
  SP.storagePlan = data.plan;
  // Nothing to move and nothing at the destination: just use the new location.
  if (!data.plan.source_exists && !data.plan.conflict) {
    await SP.doStorageChange("switch");
    return;
  }
  SP.renderStoragePlan();
};

SP.renderStoragePlan = () => {
  const plan = SP.storagePlan;
  if (!plan) return;
  SP.showOnly("space-storage-change");
  $("#space-storage-choose").hidden = plan.conflict;
  $("#space-storage-conflict").hidden = !plan.conflict;
  $("#space-storage-new-root").textContent = plan.root;
  $("#space-storage-conflict-root").textContent = plan.root;
  const move = document.querySelector('input[name="space-storage-mode"][value="move"]');
  const other = document.querySelector('input[name="space-storage-mode"][value="switch"]');
  move.checked = true;
  other.checked = false;
  SP.showDialog();
};

SP.cancelStorageChange = () => {
  SP.storagePlan = null;
  SP.showOnly(SP.storageReturn);
  SP.renderStorageCard();
  SP.welcomeOtherSpaces();
  SP.showDialog();
};

SP.applyStorageChange = mode => SP.run(() => SP.doStorageChange(mode));

SP.doStorageChange = async mode => {
  const plan = SP.storagePlan;
  if (!plan) return;
  const busyMessage = "Finish the current Space action, then try Change Location again.";
  const writeBusy = includeTimer =>
    (typeof DL !== "undefined" && Boolean(DL.busy || DL.savePromise)) ||
    (typeof designerWriteActive === "function" && designerWriteActive({ includeTimer }));
  // Never relocate underneath a running save/generate/print/refresh.
  if ((typeof DL !== "undefined" && DL.busy) ||
      (typeof designerWriteActive === "function" && designerWriteActive({ includeTimer: false }))) {
    toast(busyMessage, true, 6000);
    return;
  }
  // Settle every write owner (design autosave, inventory, layout); a failed
  // save aborts before anything is changed. No deferred preview may survive.
  if (!(await SP.leaveDrawerLayoutSafely({ noDeferredPreview: true }))) return;
  state.relocating = true; // blocks every new write entry point
  document.body.classList.add("relocating");
  if (typeof DL !== "undefined") DL.saveSoon.cancel();
  let reloading = false;
  try {
    if (typeof settleDesignerWritesForRelocation === "function") await settleDesignerWritesForRelocation();
    await SP.flushOutgoingResumeCheckpoint();
    await SP.flushDefaults();
    if (writeBusy(true) || (typeof DL !== "undefined" && DL.dirty)) {
      toast(busyMessage, true, 6000);
      return;
    }
    const data = await api("/api/space/storage-change", { parent: plan.parent, mode });
    if (data.status === "conflict") {
      SP.storagePlan = { ...plan, conflict: true };
      SP.renderStoragePlan();
      return;
    }
    SP.storagePlan = null;
    SP.storage = data.storage || null;
    if (data.status === "unchanged") {
      toast("That is already your Wavefinity folder.");
      SP.cancelStorageChange();
      return;
    }
    // Reload at once so no owner can write to the old path; the card shows any
    // leftover old copy after the reload.
    reloading = true;
    location.reload();
  } finally {
    if (!reloading) {
      state.relocating = false;
      document.body.classList.remove("relocating");
      if (typeof DL !== "undefined" && DL.dirty) DL.saveSoon();
    }
  }
};

SP.showTypeCards = () => {
  SP.destroyStorageDrawersForm?.();
  // An arbitrary existing folder can never be converted into a Storage Drawers
  // Space: the card is not offered while a folder is being given a type.
  const arbitrary = Boolean(SP.configureData);
  document.querySelectorAll('.type-card[data-kind="storage_drawers"]').forEach(card => { card.hidden = arbitrary; });
  SP.showOnly("space-type-cards");
  SP.showDialog();
  SP.dialog().scrollTop = 0;
};

SP.showTutorial = () => {
  SP.showOnly("space-tutorial");
  SP.showDialog();
  SP.dialog().scrollTop = 0;
};

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
  const typeLine = $("#space-form-type");
  if (typeLine) typeLine.hidden = edit;
  $("#space-back").hidden = edit;
  $("#space-create").hidden = edit;
  $("#space-save-changes").hidden = !edit;
  $("#space-cancel-edit").hidden = !edit;
  $("#space-form-title").parentElement.hidden = edit;
};

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
  const typeLabel = SP_KINDS[kind]?.label || kind;
  const typeLine = document.getElementById("space-form-type");
  if (typeLine) {
    typeLine.textContent = "Type: " + typeLabel;
    typeLine.hidden = update;
  }
  SP.populateSurfaceTrim();
  SP.populatePegboardStandards();
  document.querySelectorAll(".space-type-fields").forEach(el => el.hidden = true);
  const field = document.getElementById(`space-fields-${kind}`);
  if (field) field.hidden = false;
  // The cabinet form owns its own name field.
  const nameRow = document.getElementById("space-name-row");
  if (nameRow) nameRow.hidden = kind === "storage_drawers";
  if (kind === "storage_drawers") SP.mountStorageDrawersForm(prefillSpace, update);
  else SP.destroyStorageDrawersForm();
  document.getElementById("space-name").value = prefillSpace?.name || "";
  document.getElementById("space-error").hidden = true;
  document.getElementById("space-note").textContent = "";
  // Drawer setup names the field for what it is and says up front that a
  // name is needed and why a folder comes next. Other types keep "Name".
  document.getElementById("space-name-label").innerHTML =
    kind === "drawer" ? 'Drawer name <span class="required-cue">required</span>' : "Name";
  const createButton = document.getElementById("space-create");
  if (createButton && !update) {
    createButton.textContent = state.runtime.hosted
      ? "Choose Folder & Create"
      : "Create Space";
  }
  const folderHelp = document.getElementById("space-folder-help");
  if (folderHelp) {
    if (update) {
      folderHelp.hidden = true;
    } else if (state.runtime.hosted) {
      folderHelp.hidden = false;
      folderHelp.textContent = "Wavefinity keeps this Space's designs and inventory together in the folder you choose next.";
    } else {
      folderHelp.hidden = false;
      folderHelp.textContent = "Wavefinity will save this Space under Documents\\Wavefinity using the Space name.";
    }
  }
  if (kind === 'drawer') {
      document.getElementById('drawer-x').value = prefillSpace?.x || '';
      document.getElementById('drawer-y').value = prefillSpace?.y || '';
      document.getElementById('drawer-z').value = prefillSpace?.z || '';
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
      document.getElementById("portable-x").value = prefillSpace?.x || "";
      document.getElementById("portable-y").value = prefillSpace?.y || "";
      document.getElementById("portable-z").value = prefillSpace?.z || "";
      SP.fillStorageBoxForm(prefillSpace?.storage_box);
  } else if (kind === "pegboard") {
      document.getElementById("pegboard-standard").value = prefillSpace?.pegboard_standard || "standard";
      document.getElementById("pegboard-size-mode").value = prefillSpace?.pegboard_size_mode || "physical";
      document.getElementById("pegboard-x").value = prefillSpace?.x || "";
      document.getElementById("pegboard-y").value = prefillSpace?.y || "";
      document.getElementById("pegboard-holes-x").value = prefillSpace?.pegboard_holes_x || "";
      document.getElementById("pegboard-holes-y").value = prefillSpace?.pegboard_holes_y || "";
  }
  SP.updateReadouts();
  if (update) {
    if (SP.renderSpaceInfo) SP.renderSpaceInfo();
    $("#space-name").focus();
  } else {
    SP.showDialog();
  }
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
  const fail = (message, selector) => {
    SP.fail(message, selector);
    return null;
  };

  const kind = SP.setupKind;
  if (kind === "storage_drawers") return SP.readStorageDrawersSetup();
  const name = document.getElementById("space-name").value.trim();
  if (!name) return fail("Give the Space a name.", "#space-name");

  const unit = Number(state.catalog?.base_unit || 8);

  if (kind === "drawer") {
    const x = Number(document.getElementById("drawer-x").value);
    const y = Number(document.getElementById("drawer-y").value);
    const z = Number(document.getElementById("drawer-z").value);
    if (![x, y, z].every(Number.isFinite)) {
      return fail("Enter valid drawer dimensions in mm.", "#drawer-x");
    }
    if (SP.drawerCapacity(x) < 1 || SP.drawerCapacity(y) < 1) {
      return fail(
        "The drawer must have room for at least one Wavefinity unit after wall clearance.",
        "#drawer-x",
      );
    }
    const minHeight = ordinaryBinMinimumHeight();
    if (z < minHeight) {
      return fail(
        `Usable drawer height must be at least ${fmt(minHeight)} mm.`,
        "#drawer-z",
      );
    }
    return { kind, name, x, y, z, trimSize: null };
  }

  if (kind === "surface") {
    const trimSize = document.getElementById("surface-trim").value;
    const maxX = Number(document.getElementById("surface-x").value);
    const maxY = Number(document.getElementById("surface-y").value);
    const resolved = SP.resolveSurface(maxX, maxY, trimSize);
    if (!resolved.ok) {
      return fail(
        resolved.error,
        SP.surfacePresetMap()[trimSize] === undefined ? "#surface-trim" : "#surface-x",
      );
    }
    return {
      kind,
      name,
      x: resolved.fieldX,
      y: resolved.fieldY,
      z: SP.surfacePresetMap()[trimSize],
      trimSize,
      extra: { max_x_mm: maxX, max_y_mm: maxY },
    };
  }

  if (kind === "portable") {
    const rawX = Number(document.getElementById("portable-x").value);
    const rawY = Number(document.getElementById("portable-y").value);
    const z = Number(document.getElementById("portable-z").value);
    if (![rawX, rawY, z].every(Number.isFinite)) {
      return fail("Enter valid Storage Box dimensions in mm.", "#portable-x");
    }

    const x = SP.snap(rawX);
    const y = SP.snap(rawY);
    const minField = Number(state.catalog?.b4b_rules?.min_field_mm);
    const minHeight = Number(state.catalog?.b4b_rules?.min_secure_height_mm);

    if (x < minField || y < minField) {
      return fail(
        `A Storage Box needs at least ${fmt(minField)} × ${fmt(minField)} mm of child-bin field.`,
        "#portable-x",
      );
    }
    if (z < minHeight) {
      return fail(
        `A Storage Box's usable height must be at least ${fmt(minHeight)} mm.`,
        "#portable-z",
      );
    }
    return { kind, name, x, y, z, trimSize: null, extra: { storage_box: SP.readStorageBoxForm() } };
  }

  if (kind === "pegboard") {
    const resolved = SP.resolvePegboard();
    if (!resolved.ok) return fail(resolved.error, resolved.mode === "holes" ? "#pegboard-holes-x" : "#pegboard-x");
    return {
      kind, name, x: resolved.width, y: resolved.height, z: 350, trimSize: null,
      extra: {
        pegboard_standard: resolved.standard.id,
        pegboard_size_mode: resolved.mode,
        pegboard_holes_x: resolved.holesX,
        pegboard_holes_y: resolved.holesY,
      },
    };
  }

  return fail("Choose a Space type.", "#space-name");
};

SP.create = async () => {
  if (SP.isUpdate) return SP.updateSpace();
  const values = await SP.readSetupValues();
  if (!values) return;
  let { kind, name, x, y, z, trimSize, extra = {} } = values;
  if (kind === "storage_drawers" && state.runtime.hosted) {
    // Hosted Create assigns the stable drawer IDs here, exactly once; the
    // server keeps them. Local Create lets Python assign them.
    const prepared = StorageDrawers.prepareCreateDraft({ kind, name, x, y, z, storage_drawers: extra.storage_drawers });
    extra = { storage_drawers: prepared.storage_drawers };
    z = prepared.z;
  }
  const migrating = Boolean(SP.configureData);
  let folder = SP.configureData || null;

  if (!migrating && state.runtime.hosted) {
    folder = await SP.pickFolder({ stayOnSetup: true });
    if (!folder) return;
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
  const okToLeave = await SP.leaveDrawerLayoutSafely();
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
    await WFFileSystem.writeText(folder.handle, SP.inventoryFilenameFor(folder), result.inventory_text);
    const space = result.layout.space;
    // This call owns the new Space definition, but not the bin/part
    // defaults - on Create there is nothing yet to preserve (the writer's
    // own under-lock defaults already match), and on Configure Existing/
    // migrate, leaving them unset lets the writer preserve the newest
    // under-lock value instead of a copy captured here before its own
    // read/lock (Fix 032 Correction 4, C4.1 - this mirrors the previous
    // pre-lock SP.readMetadata() capture that used to run only when
    // `migrating`, now removed).
    const metadata = await SP.writeMetadata(folder.handle, "space", space, true, {});
    // Activate the selected target folder itself, not whatever folder was
    // previously active - see Fix 004 Correction 7.A. state.browserFolder
    // itself is set inside SP.applyFolder() below, never here (Fix 032
    // Correction 2, C2.1) - this only writes the remembered-active record.
    await WFFileSystem.save("active", { handle: folder.handle, space_id: metadata.space_id });
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
        SP.fail(message, nameError ? "#space-name" : "#space-create");
        return;
      }
      throw error;
    }
    SP.recent = data.recent || [];
    info = data.folder;
  }

  // The leave decision is already resolved above - clear the old Drawer
  // state exactly once, with no second prompt.
  if (!(await SP.resetDrawer({ skipSafeLeave: true }))) return;
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
  SP.close();

  // The Designer always means an ordinary Bin. A Storage Box or Base Trim is
  // saved from the Space itself (Space Actions), never designed here.
  await loadFreshOrdinaryDesignForCurrentFolder();
};

// ------------------------------------------------------------ design/session activation (Fix 019 Item 1/5)
//
// Every session-only editor flag that must never leak from one typed-Space
// identity to another.
SP.resetDesignSession = () => {
  state.designInventoryId = null;
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
      toast(`The last design for this Space could not be restored: ${error.message}`, true, 7000);
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
      if (!untouched) await persistSpaceDesignSource(null, true);
    }
  }

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
        const okToLeave = await SP.leaveDrawerLayoutSafely();
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
        const okToLeave = await SP.leaveDrawerLayoutSafely();
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
    }
};



SP.fail = (message, selector) => {
  $("#space-error").textContent = message;
  $("#space-error").hidden = false;
  $(selector)?.focus();
};

// Fix 019 Item 6: "no remembered folder" and "permission not (yet) granted"
// are expected, silent outcomes - Welcome with no message. An exception from
// actually reading/classifying/identifying the remembered folder is a real
// condition (damaged/newer metadata, an identity mismatch, a read failure)
// and must reach the user as visible text on Welcome, not be swallowed into
// an ordinary-looking Welcome screen. Recovery never mutates the
// damaged/newer metadata itself - it only stops and explains.
SP.launch = async () => {
  if (state.runtime.hosted) {
    let saved = null;
    let hasPermission = false;
    try {
      saved = await WFFileSystem.load("active");
      // Startup is not a user gesture: only already-granted permission may
      // resume silently. A handle whose permission needs renewing falls
      // through to Welcome, where an explicit action supplies the gesture.
      // The saved record itself is kept.
      hasPermission = Boolean(saved?.handle) && await WFFileSystem.queryReadWritePermission(saved.handle);
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
    if (!hasPermission) { SP.showHome(); return; }
    try {
      const folder = { handle: saved.handle, name: saved.handle.name };
      const data = await SP.inspectHosted(folder);
      SP.assertExpectedHostedIdentity(data, saved.space_id || null);
      if (data.needs_setup) {
        SP.enterSetupFor(folder, data);
        return;
      }
      const info = await SP.useHostedFolder(folder, { expectedSpaceId: saved.space_id || null });
      if (!info) { SP.showHome(); return; } // switch aborted mid-startup - fall back quietly
      if (info.folder_mode === "space") SP.showResume(info);
      return;
    } catch (error) {
      SP.showHome(error.message);
      return;
    }
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
    if (!data || data.missing) { SP.showHome(); return; }
    if (data.needs_setup) {
      SP.enterSetupFor(data.folder, data);
      return;
    }
    if (!(await SP.applyFolder(data))) { SP.showHome(); return; }
    // The routing decision must always end somewhere definite: the startup
    // cover is dismissed only once this resolves.
    if (data.folder_mode === "space") SP.showResume(data);
    else SP.close();
  } catch (error) {
    SP.showHome(error.message);
  }
};

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
      SP.recent = (await api("/api/space/forget", { space_id: one.space_id || null, output: one.folder })).recent || [];
      SP.renderRecent();
    });
    else SP.run(() => SP.afterPick(one.folder));
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
  secure_lid: true, latch_count: "auto", latch_strength: "standard", lid_headroom_mm: 1,
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
  SP.storageBoxStrength = one.latch_strength || "standard";
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
  if (!label || !value) return;
  const hideOutside = () => { label.hidden = true; value.hidden = true; value.textContent = ""; };
  const token = ++SP.setupOutsideToken;
  clearTimeout(SP.setupOutsideTimer);
  const num = id => Number(document.getElementById(id)?.value);
  const x = SP.snap(num("portable-x")), y = SP.snap(num("portable-y")), z = num("portable-z");
  const minField = Number(state.catalog?.b4b_rules?.min_field_mm);
  const minHeight = Number(state.catalog?.b4b_rules?.min_secure_height_mm);
  const valid = [x, y, z].every(n => Number.isFinite(n) && n > 0) && x >= minField && y >= minField && z >= minHeight;
  if (!valid || SP.setupKind !== "portable") { hideOutside(); return; }
  const space = { kind: "portable", name: "Storage Box", x, y, z, storage_box: SP.readStorageBoxForm() };
  SP.setupOutsideTimer = setTimeout(async () => {
    try {
      const result = await api("/api/space/structural-design", { space });
      if (token !== SP.setupOutsideToken) return;
      const size = result.summary?.assembled_envelope_mm;
      if (!Array.isArray(size) || size.length < 3) { hideOutside(); return; }
      value.textContent = `${size.map(n => fmt(Number(n))).join(" × ")} mm`;
      label.hidden = false; value.hidden = false;
    } catch (_error) {
      if (token === SP.setupOutsideToken) hideOutside();
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
    latch_strength: SP.storageBoxStrength || "standard",
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
    toast("A slicer was not found. Use Change slicer in Design to locate Bambu Studio or OrcaSlicer.", true, 8000);
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
      const result = await api("/api/space/structural-print", { ...payload, slicer_path: state.slicer?.path || null });
      DL.requireSpaceContext(context);
      if (result.partial) {
        // Files are a real side effect even though the slicer step failed -
        // never claim "Sent to Bambu Studio" when it did not open.
        toast(result.error || `${label} files were saved, but the slicer did not open.`, true, 8000);
      } else {
        const names = (result.files || []).map(file => String(file).split(/[\\/]/).pop());
        toast(`Sent to ${state.slicer?.name || "Bambu Studio"}!\n${names.join("\n")}`, false, 7000);
      }
    } else {
      const result = await api("/api/space/structural-generate", payload);
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
};

SP.baseTrimSummaryText = () => {
  const info = SP.baseTrimInfo;
  if (info.error) return `Base Trim · ${info.error}`;
  if (!info.plan || !info.status) return "";
  const count = Number(info.plan.piece_count);
  const pieces = `${count} ${count === 1 ? "piece" : "pieces"} for current printer`;
  return `Base Trim · ${pieces} · ${SP.BASE_TRIM_STATUS_TEXT[info.status.status] || "Needs save"}`;
};

SP.hostedBaseTrimStatus = async (plan, signature) => {
  const handle = state.browserFolder?.handle;
  if (!handle) return { status: "missing" };
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
    SP.baseTrimInfo.error = error.message;
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
// committed only after every write succeeded. A failure puts every touched file back.
SP.hostedBaseTrimSave = async (payload, context) => {
  const handle = state.browserFolder.handle;
  const spaceId = state.activeSpaceId;
  const exported = await api("/api/space/structural-generate", { ...payload, space_id: spaceId });
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
  const previous = new Map();
  for (const piece of candidate.pieces) {
    const existing = await WFFileSystem.sha256(handle, piece.filename);
    if (existing === null) continue;
    // Ours and unchanged, or byte-identical to the new file (nothing is lost).
    if (existing !== owned.get(piece.filename) && existing !== piece.sha256) {
      throw new Error(`${piece.filename} is already in this folder and was not made by this Base Trim, or it was changed outside Wavefinity. Rename or move it, then save again. Nothing was changed.`);
    }
    const old = await WFFileSystem.readBlob(handle, piece.filename);
    if (old) previous.set(piece.filename, new Blob([await old.arrayBuffer()]));
  }
  const written = [];
  try {
    for (const piece of candidate.pieces) {
      await WFFileSystem.writeBlob(handle, piece.filename, blobs.get(piece.filename));
      written.push(piece.filename);
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
    // Files are never left claiming to be current: restore what was replaced and
    // remove what was newly made, best effort.
    for (const name of written) {
      try {
        if (previous.has(name)) await WFFileSystem.writeBlob(handle, name, previous.get(name));
        else await SP.removeIfPresent(handle, name);
      } catch (_restore) { /* the next status check reports the folder as it is */ }
    }
    throw error;
  }
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
      : await api("/api/space/structural-generate", payload);
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
  if (state.runtime.hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer was not found. Use Change slicer in Design to locate Bambu Studio or OrcaSlicer.", true, 8000);
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
    const result = await api("/api/space/surface-print", {
      output: context.output, space_id: context.spaceId,
      slicer_path: state.slicer?.path || null,
    });
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) toast(result.error || "Surface print stopped before Bambu Studio opened.", true, 10000);
    else toast(`Sent Surface + Bins to ${state.slicer?.name || "Bambu Studio"}!\n${SP.fileNames(result.files)}`, false, 8000);
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
  if (state.runtime.hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (!state.slicer?.available) {
    toast("A slicer was not found. Use Change slicer in Design to locate Bambu Studio or OrcaSlicer.", true, 8000);
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
    const result = await api("/api/space/storage-box-print", {
      output: context.output, space_id: context.spaceId,
      slicer_path: state.slicer?.path || null,
    });
    DL.requireSpaceContext(context);
    DL.adoptBatchResult(result);
    DP.renderInventory(true);
    DL.emit();
    DL.requestReport();
    if (result.partial) toast(result.error || "Storage Box print stopped before Bambu Studio opened.", true, 10000);
    else toast(`Sent Storage Box + Bins to ${state.slicer?.name || "Bambu Studio"}!\n${(result.files || []).map(file => String(file).split(/[\\/]/).pop()).join("\n")}`, false, 8000);
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
  print.title = hosted ? SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP : "";
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
        actualText = `${x} × ${y} × ${z} mm`;
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
        actualText = `${x} × ${y} mm`;
        usableText = `${fmt(x / unit)} × ${fmt(y / unit)} units, ${z} mm usable height`;
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
        toast("Failed to open folder: " + e.message, true);
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
    } else {
        const data = await api("/api/space/update", {
          output: state.output, name: name, x: x, y: y, z: z, ...extra,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        requireCurrent();
        state.activeSpace = data.folder.space;
    }
    SP.cancelInlineEdit();
    toast("Space updated.");
    
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
        if (typeof refreshPreview === "function") await refreshPreview();
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

SP.setupIsDirty = () => Boolean(SP.storageDrawersForm?.isDirty?.());

SP.confirmDiscardSetup = async () => {
  if (!SP.setupIsDirty()) return true;
  return appConfirmAction({
    title: "Discard cabinet changes?",
    message: "You changed this cabinet's settings and have not saved them. Discard the changes?",
    actionLabel: "Discard",
    cancelLabel: "Keep editing",
    danger: true,
  });
};

SP.requestClose = async () => {
  if (!(await SP.confirmDiscardSetup())) return;
  SP.close();
};

SP.mountStorageDrawersForm = (prefill, update) => {
  SP.destroyStorageDrawersForm();
  const host = document.getElementById("space-fields-storage_drawers");
  try {
    SP.ensureStorageDrawersRules();
  } catch (error) {
    // Fail closed: no form is built from rules that are not published.
    const note = document.createElement("p");
    note.className = "sd-field-error"; note.textContent = error.message;
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
    callbacks: {
      identity: () => update ? (state.activeSpaceId || state.activeSpace?.name) : createToken,
      openPrinterSettings: () => SP.openPrinterSettings(),
      requestSummary: ({ space, printer_profile }) => api("/api/space/storage-drawers-summary", {
        space, ...(state.runtime.hosted ? { printer_profile } : {}),
      }, { timeoutMs: 15000 }),
    },
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
    return api("/api/space/storage-drawers-mutate", {
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
  const result = await api("/api/space/storage-drawers-mutate-text", {
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
  DL.selectedRow = keepRow && DL.bin(keepRow) ? keepRow : null;
  DL.saveState = "saved";
  DL.prune();
  DL.clearSpacerPlan();
  SP.cabinetInfo.key = "";
  DL.emit();
  DL.requestReport();
  if (typeof DV !== "undefined") DV.fit();
  SP.renderSpaceInfo();
};

SP.cabinetAdd = async () => {
  try {
    // The controller resolves null for a stale or superseded result, so success
    // is announced only when it was adopted into the same current Space.
    if (await SP.mutateCabinet("add")) toast("Drawer added.");
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 6000);
  }
};

SP.cabinetDelete = async drawerId => {
  const rows = StorageDrawers.drawerDescriptors(state.activeSpace);
  const index = rows.findIndex(row => row.id === drawerId);
  if (index < 0 || rows.length <= 1) return;
  if (DL.layout.drawers.find(one => one.id === drawerId)?.placements?.length) {
    toast(`Empty Drawer ${index + 1} before deleting it.`, true, 5000);
    return;
  }
  const ok = await appConfirmAction({
    title: `Delete Drawer ${index + 1}?`,
    message: `Delete Drawer ${index + 1}? It is removed from the cabinet.`,
    actionLabel: "Delete Drawer",
    danger: true,
  });
  if (!ok) return;
  try {
    await SP.mutateCabinet("delete", { drawer_id: drawerId });
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(error.message, true, 6000);
  }
};

SP.resetCabinetSettings = async () => {
  const problem = state.cabinetRecovery?.message || "A cabinet setting is not valid.";
  const ok = await appConfirmAction({
    title: "Reset cabinet settings?",
    message: `${problem}\n\nWavefinity keeps every drawer that is still valid and replaces only what is damaged with current defaults. Your Inventory and bin designs are not changed.`,
    actionLabel: "Reset cabinet settings",
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
    // Hosted Wavefinity has no local slicer: Print stays disabled, never a Save.
    const printButton = host.querySelector(".sd-print");
    if (state.runtime.hosted && printButton) {
      printButton.disabled = true;
      printButton.title = SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP;
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

SP.runCabinetStructural = async mode => {
  if (SP.structuralBusy) return;
  const hosted = Boolean(state.runtime.hosted);
  if (hosted && !state.browserFolder) { toast("Choose a folder before saving files.", true); return; }
  if (mode === "print" && hosted) { toast(SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP, true, 6000); return; }
  if (mode === "print" && !state.slicer?.available) {
    toast("A slicer was not found. Use Change slicer in Design to locate Bambu Studio or OrcaSlicer.", true, 8000);
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
      const result = await api("/api/space/structural-print", { ...payload, slicer_path: state.slicer?.path || null });
      wroteFiles = true;
      DL.requireSpaceContext(context);
      if (result.partial) {
        toast(result.error || "Cabinet files were saved, but the slicer did not open.", true, 8000);
      } else {
        toast(`Sent to ${state.slicer?.name || "Bambu Studio"}!\n${names(result.files)}`, false, 7000);
      }
      saved = result;
    } else if (hosted) {
      saved = await SP.hostedCabinetSave(payload, context);
      wroteFiles = true;
      DL.requireSpaceContext(context);
      toast(`Saved cabinet files\n${names(saved.files)}${saved.warnings?.length ? `\n${saved.warnings.join("\n")}` : ""}`, false, 8000);
    } else {
      saved = await api("/api/space/structural-generate", payload);
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
  const exported = await api("/api/space/structural-generate", payload);
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
