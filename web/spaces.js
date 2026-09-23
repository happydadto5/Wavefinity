"use strict";

// Normal Design can work without a persistent folder by downloading generated
// files. Inventory and typed Spaces require a real writable folder. A typed
// Space is a one-time Drawer/Surface/Portable/Pegboard setup layered on that folder;
// an untyped folder just keeps ordinary designs.
const SP = {
  recent: [],
  setup: null,
  busy: false,
  resume: null,
  resumeTimer: null,
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
};
const RESUME_AUTOCONTINUE_SECONDS = 10;
const SP_KINDS = {
  portable: { icon: "🧰", label: "Portable Storage" },
  surface: { icon: "🔲", label: "Surface" },
  drawer: { icon: "🗄️", label: "Drawer" },
  pegboard: { icon: "🧱", label: "Pegboard" },
  // Legacy kind, readable for migration only - never a current Space type;
  // it presents as Portable Storage, its recovery destination.
  box: { icon: "🧰", label: "Portable Storage" },
};
const FOLDER_METADATA = ".wavefinity.json";
const LEGACY_METADATA = ".wavefinity-space.json";
const SPACE_ID_REQUIRED_VERSION = 5;
const FOLDER_METADATA_VERSION = 8;
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
SP.close = () => { if (SP.dialog().open) SP.dialog().close(); };
SP.showOnly = id => {
  SP.cancelInlineEdit();
  SP.cancelResumeAutoContinue();
  ["welcome-home", "welcome-resume", "space-unsupported", "space-type-cards", "space-tutorial", "space-form", "space-configure-prompt", "space-collision-prompt", "space-existing-inventory-prompt"]
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

// Show the resolved finished size in the visible inputs, so a hidden
// request never lingers after resolution.
SP.normalizeSurfaceInputs = resolved => {
  if (!resolved?.ok) return;
  document.getElementById("surface-x").value = fmt(resolved.outerX);
  document.getElementById("surface-y").value = fmt(resolved.outerY);
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
SP.leaveDrawerLayoutSafely = async () => {
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
  DL.candidates = [];
  DL.selected = null;
  DL.output = null;
  DL.pegboardLayouts = {};
  DL.pegboardRefreshError = "";
  DL.working = null;
  DL.workingTicket += 1;
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
  return { current: await read(FOLDER_METADATA), legacy: await read(LEGACY_METADATA) };
};

SP.validSpace = raw => {
  if (!raw || !["drawer", "surface", "portable", "box", "pegboard"].includes(raw.kind)) return null;
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
    }
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
  if (![2, 3, 4, 5, 6, 7, 8].includes(current.version)) return { status: "invalid" };
  const needsMigration = current.version < 4 || current.setup_version !== SPACE_SETUP_VERSION;
  const explicitInventory = typeof current.inventory === "boolean" ? current.inventory : null;
  if (current.folder_mode === "design") {
    return { status: "design", inventory: explicitInventory, needsMigration, metadataVersion: current.version };
  }
  if (current.folder_mode === "space") {
    const space = SP.validSpace(current.space);
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
    metadata.space_id = spaceId || crypto.randomUUID();
    metadata.inventory = true;
    metadata.space = resolvedSpace;
    metadata.keep_bin_defaults = keep;
    metadata.bin_defaults = defaults;
    metadata.part_defaults = partDefaults;
    metadata.resume_design = resumeDesign;
    metadata.resume_pending = resumePending;
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
        toast(`Current design could not be saved to this Space: ${error.message}`, true, 6000);
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

SP.inventoryRequest = async (path, extra = {}, { write = true } = {}) => {
  const folder = state.browserFolder;
  if (!folder?.handle) throw new Error("Keeping an inventory needs folder access so Wavefinity can save it with your designs.");
  const inventoryText = await SP.readInventoryFor(folder, { migrate: write });
  const data = await api(path, {
    inventory_text: inventoryText,
    inventory_title: state.activeSpace?.name || folder.name,
    ...extra,
  });
  if (write && typeof data.inventory_text === "string") {
    await WFFileSystem.writeText(folder.handle, INVENTORY_FILENAME, data.inventory_text);
  }
  return data;
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
SP.pickFolder = async ({ stayOnSetup = false, spaceRoot = false } = {}) => {
  if (state.runtime.hosted) {
    if (!window.WFFileSystem?.supportsDirectoryPicker()) {
      if (stayOnSetup) {
        SP.fail(
          "This browser cannot give Wavefinity writable folder access. Your Space details have not been changed.",
          "#space-create",
        );
      } else {
        SP.showFolderAccessNeeded("unsupported");
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
    const meta = [one.conflict ? "duplicate Space identity" : one.invalid ? "metadata unavailable" : space ? `${kind?.label || "Space"} · SPACE` : "Design folder", SP.sizeText(one.size), one.missing ? "folder not found" : ""]
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

SP.showResume = info => {
  SP.resume = info;
  SP.showOnly("welcome-resume");
  const space = info.space || {};
  const kind = SP_KINDS[space.kind] || SP_KINDS.drawer;
  $("#welcome-resume-icon").textContent = kind.icon;
  $("#welcome-resume-name").textContent = space.name || info.folder_name;
  $("#welcome-resume-meta").textContent = [kind.label, SP.sizeText([space.x, space.y, space.z])].filter(Boolean).join(" · ");
  $("#welcome-resume-folder").textContent = info.folder;
  $("#welcome-resume-folder").title = info.folder;
  SP.showDialog();
  SP.armResumeAutoContinue();
};

// Left alone, the resume prompt continues on its own after ~10 seconds - the
// same thing Continue does, landing in Design. Anything that dismisses or
// replaces this screen (the buttons below, the dialog's own close - Escape,
// backdrop, the X - or showing a different screen) cancels it first, so a
// stale timer can never fire after the user has moved on.
SP.cancelResumeAutoContinue = () => {
  clearInterval(SP.resumeTimer);
  SP.resumeTimer = null;
  const button = $("#welcome-resume-continue");
  if (button) button.textContent = "Open Space";
};

SP.armResumeAutoContinue = () => {
  SP.cancelResumeAutoContinue();
  let remaining = RESUME_AUTOCONTINUE_SECONDS;
  const button = $("#welcome-resume-continue");
  SP.resumeTimer = setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) { SP.run(SP.confirmResume); return; }
    if (button) button.textContent = `Open Space (${remaining})`;
  }, 1000);
};

// An existing Space lands by its loaded Inventory, without changing its
// restored Current design or making a second inventory parser.
SP.openTypedSpacePreferredView = async () => {
  try {
    await DL.ensureLoaded();
  } catch (error) {
    toast(`Could not read this Space's inventory: ${error.message}`, true, 7000);
    return false;
  }
  const preferred = DL.bins.some(one => ["bin", "b4b", "manual"].includes(one.kind))
    ? "space" : "design";
  if (preferred === "space") {
    await DP.enter("space", true);
    activatePreviewView("drawer");
  } else {
    if (DL.active) DP.setMode("design");
    activatePreviewView("3d");
  }
  return true;
};

SP.confirmResume = async () => {
  SP.cancelResumeAutoContinue();
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
SP.showFolderAccessNeeded = (reason = "unsupported") => {
  const lead = document.getElementById("space-unsupported-lead");
  const detail = document.getElementById("space-unsupported-detail");
  if (lead && detail) {
    if (reason === "denied") {
      lead.textContent =
        "Wavefinity was not given read/write access to that folder.";
      detail.textContent =
        "You can still design and download parts normally. Choose the folder again and allow access to use Inventory and Spaces.";
    } else {
      lead.textContent =
        "This browser cannot give Wavefinity ongoing read/write access to a chosen folder.";
      detail.textContent =
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
  const hasRecent = SP.recent.length > 0;
  document.getElementById("welcome-recent-container").hidden = !hasRecent;
  SP.showDialog();
};

SP.showTypeCards = () => {
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
      folderHelp.textContent = "Wavefinity keeps this drawer's designs and inventory together in the folder you choose next.";
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
      // Edit prefills the finished outside size from the stored interior
      // field plus the selected trim; nothing is migrated.
      const prefillTrim = trimSelect?.value;
      const hasSize = prefillSpace?.x && prefillSpace?.y && prefillTrim;
      document.getElementById("surface-x").value =
        hasSize ? fmt(SP.surfaceOutsideFor(prefillSpace.x, prefillTrim)) : "";
      document.getElementById("surface-y").value =
        hasSize ? fmt(SP.surfaceOutsideFor(prefillSpace.y, prefillTrim)) : "";
  } else if (kind === "portable") {
      document.getElementById("portable-x").value = prefillSpace?.x || "";
      document.getElementById("portable-y").value = prefillSpace?.y || "";
      document.getElementById("portable-z").value = prefillSpace?.z || "";
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
  const folder = SP.configureData || await SP.pickFolder();
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
SP.readSetupValues = () => {
  const fail = (message, selector) => {
    SP.fail(message, selector);
    return null;
  };

  const kind = SP.setupKind;
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
    const resolved = SP.resolveSurface(
      Number(document.getElementById("surface-x").value),
      Number(document.getElementById("surface-y").value),
      trimSize,
    );
    if (!resolved.ok) {
      return fail(
        resolved.error,
        SP.surfacePresetMap()[trimSize] === undefined ? "#surface-trim" : "#surface-x",
      );
    }
    SP.normalizeSurfaceInputs(resolved);
    return {
      kind,
      name,
      x: resolved.fieldX,
      y: resolved.fieldY,
      z: SP.surfacePresetMap()[trimSize],
      trimSize,
    };
  }

  if (kind === "portable") {
    const rawX = Number(document.getElementById("portable-x").value);
    const rawY = Number(document.getElementById("portable-y").value);
    const z = Number(document.getElementById("portable-z").value);
    if (![rawX, rawY, z].every(Number.isFinite)) {
      return fail("Enter valid Portable Storage dimensions in mm.", "#portable-x");
    }

    const x = SP.snap(rawX);
    const y = SP.snap(rawY);
    const minField = Number(state.catalog?.b4b_rules?.min_field_mm);
    const minHeight = Number(state.catalog?.b4b_rules?.min_secure_height_mm);

    if (x < minField || y < minField) {
      return fail(
        `Portable Storage needs at least ${fmt(minField)} × ${fmt(minField)} mm of child-bin field.`,
        "#portable-x",
      );
    }
    if (z < minHeight) {
      return fail(
        `Portable Storage usable height must be at least ${fmt(minHeight)} mm.`,
        "#portable-z",
      );
    }
    return { kind, name, x, y, z, trimSize: null };
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
  const values = SP.readSetupValues();
  if (!values) return;
  const { kind, name, x, y, z, trimSize, extra = {} } = values;
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
  // SP.create() always follows with an explicit designSurface/designPortable/
  // loadFreshOrdinaryDesignForCurrentFolder call below, which installs the
  // starter design itself - skip applyFolder's own (redundant) activation.
  const applyOptions = { initDesign: false, reset: false };
  // `folder` is a real handle-bearing object only in the hosted branch
  // above - in the local branch it may be a plain output path string, so
  // state.browserFolder must not be set from it there.
  if (state.runtime.hosted) applyOptions.browserFolder = folder;
  await SP.applyFolder(info, applyOptions);
  SP.close();

  if (kind === "portable") await SP.designPortable(info.space);
  else if (kind === "surface") await SP.designSurface(info.space);
  else await loadFreshOrdinaryDesignForCurrentFolder();
};

// ------------------------------------------------------------ design/session activation (Fix 019 Item 1/5)
//
// Every session-only Current-design/editor/Surface-first-run flag that must
// never leak from one typed-Space identity to another. Base Trim source/
// switching memory (lastOrdinaryDesign/lastBaseTrimDesign/
// baseTrimSourceLayout) is per-design editing-session bookkeeping, not
// per-Space persisted state, so it is cleared here too rather than carried
// into a different Space.
SP.resetDesignSession = () => {
  state.workingPending = false;
  state.workingGeneratedKey = null;
  state.surfaceEdgeHandled = false;
  state.baseTrimSourceLayout = null;
  state.lastOrdinaryDesign = null;
  state.lastBaseTrimDesign = null;
  state.drafts = {};
  state.history = [];
  state.future = [];
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  if (typeof resetNestPhotoSession === "function") resetNestPhotoSession();
  if (typeof clearDraftSelection === "function") clearDraftSelection();
  if (typeof updateHistoryButtons === "function") updateHistoryButtons();
};

// Builds the correct design family's clean starter design for `space` into
// state.design/state.cleanDesign. Does not touch preview/toast/the working-
// pending flag - callers decide those. Shared by SP.initializeDesignForActiveSpace
// (silent, for open/resume/switch) and SP.designSurface/SP.designPortable
// (explicit, user-visible creation) instead of duplicating the reset logic -
// see Fix 004/Fix 019 Item 1.
SP.installSpaceStarterDesign = async space => {
  if (space.kind === "surface") {
    const trimValue = SP.surfacePresetMap()[space.trim_size];
    state.design = makeBaseTrimDesign(space.x, space.y);
    if (Number.isFinite(trimValue)) {
      state.design.base_trim.width_mm = trimValue;
      state.design.box.z = trimValue;
    }
    state.design.part_name = space.name;
  } else if (space.kind === "portable" || space.kind === "box") {
    state.design = clone(state.catalog.defaults.design);
    state.design.box.x = space.x;
    state.design.box.y = space.y;
    state.design.box.z = normalizeBinDimension("z", space.z);
    state.design.part_name = space.name;
    const binType = document.getElementById("bin-type");
    if (binType) binType.value = "b4b";
    await toggleB4B(true);
  } else if (space.kind === "pegboard") {
    state.design = freshDesignForCurrentFolder();
    state.design.box.pegboard = {
      enabled: true,
      standard: space.pegboard_standard,
      cleat_x: "auto",
      cleat_y: "auto",
    };
  } else {
    // Drawer (and any other/untyped folder that reaches here) -> the fresh
    // ordinary Bin starter, same as loadFreshOrdinaryDesignForCurrentFolder.
    state.design = freshDesignForCurrentFolder();
  }
  state.cleanDesign = clone(state.design);
};

// The ONE authoritative typed-Space design/session activation path (Fix 019
// Item 1). SP.applyFolder calls this after folder/Space identity is already
// current, for every path that activates a typed Space: local/hosted
// startup resume, Open Existing Space, Recent Space selection, collision
// "Open this Space", a newly created Space, a configured/migrated Space, and
// any later folder switch. The resulting starter design is clean/untouched:
// opening/switching alone never marks it as a pending Current design -
// explicit user actions (New design, Design first bin, opening a design
// file) continue to call markWorkingDesignPending() themselves.
SP.initializeDesignForActiveSpace = async () => {
  if (state.folderMode !== "space" || !state.activeSpace || !state.catalog) return;
  SP.resetDesignSession();

  let restored = false;
  let resumeValidationFailed = false;
  if (state.spaceResumeDesign) {
    try {
      const result = await api("/api/design/validate", {
        design: clone(state.spaceResumeDesign),
      });
      // A restored design bypasses SP.installSpaceStarterDesign() and
      // applySpaceSizingDefaults() entirely - it is the exact design the
      // user left, not a fresh starter seeded from remembered defaults.
      state.design = result.design;
      state.cleanDesign = clone(result.design);
      state.workingPending = Boolean(state.spaceResumePending);
      restored = true;
    } catch (error) {
      // The stored checkpoint itself is left untouched - a validation
      // failure here must never delete or rewrite recoverable user data.
      resumeValidationFailed = true;
      toast(`The last design for this Space could not be restored: ${error.message}`, true, 7000);
    }
  }

  if (!restored) await SP.installSpaceStarterDesign(state.activeSpace);
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

// Reuses the real Base Trim design path (makeBaseTrimDesign) rather than
// building a second, incompatible "edge" design object - see Fix 004. This
// is the explicit "design this Surface now" action (e.g. right after
// Create), so it forces the 3D preview and announces itself - unlike the
// silent SP.initializeDesignForActiveSpace used for open/resume.
SP.designSurface = async space => {
  SP.resetDesignSession();
  await SP.installSpaceStarterDesign(space);
  syncForm();
  activatePreviewView("3d");
  await refreshPreview();

  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  toast(`Designing Surface: ${space.name}`);
};

// Reuses the ordinary bin -> B4B toggle machinery (toggleB4B/readB4BForm)
// rather than forking B4B form logic - see Fix 004 ("Portable -> Bin for Bins").
SP.designPortable = async space => {
  SP.resetDesignSession();
  await SP.installSpaceStarterDesign(space);
  syncForm();
  activatePreviewView("3d");
  await refreshPreview();

  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  toast(`Designing Portable Storage: ${space.name}`);
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
      ["drawer", "surface", "box", "portable", "pegboard"].includes(candidate.kind);

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
  $("#space-cancel-edit")?.addEventListener("click", SP.cancelInlineEdit);
  document.querySelectorAll("#welcome-close, #welcome-resume-close, #space-unsupported-close, #space-form-close, #space-type-cards-close, #space-tutorial-close")
    .forEach(el => el?.addEventListener("click", SP.close));
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.close(); });
  SP.dialog().addEventListener("close", SP.cancelResumeAutoContinue);
  const welcomeCreate = document.getElementById("welcome-create");
  if (welcomeCreate) welcomeCreate.addEventListener("click", SP.beginCreateNew);
  const welcomeOpen = document.getElementById("welcome-open");
  if (welcomeOpen) welcomeOpen.addEventListener("click", () => SP.run(SP.openExisting));
  const tutorialOpen = document.getElementById("space-tutorial-open");
  if (tutorialOpen) tutorialOpen.addEventListener("click", SP.showTutorial);
  const tutorialBack = document.getElementById("space-tutorial-back");
  if (tutorialBack) tutorialBack.addEventListener("click", SP.showTypeCards);
  const welcomeResumeContinue = document.getElementById("welcome-resume-continue");
  if (welcomeResumeContinue) welcomeResumeContinue.addEventListener("click", () => SP.run(SP.confirmResume));
  const welcomeResumeSwitch = document.getElementById("welcome-resume-switch");
  if (welcomeResumeSwitch) welcomeResumeSwitch.addEventListener("click", () => {
    SP.cancelResumeAutoContinue();
    // SP.run() calls the task immediately, so showDirectoryPicker() is still
    // reached from the trusted click.
    SP.run(SP.openExisting);
  });
  document.querySelectorAll(".type-card").forEach(el => {
      el.addEventListener("click", () => {
          // A stale inventory candidate may prefill only its own card type;
          // choosing a different type never inherits its dimensions.
          const kind = el.dataset.kind;
          const candidate = SP.setupPrefillSpace;
          const candidateKind =
            candidate?.kind === "box" ? "portable" : candidate?.kind;
          SP.showSetup(kind, candidateKind === kind ? candidate : null);
      });
  });
  const untypedStart = document.getElementById("space-untyped-start");
  if (untypedStart) untypedStart.addEventListener("click", () => SP.run(SP.startUntyped));
  const spaceBack = document.getElementById("space-back");
  if (spaceBack) spaceBack.addEventListener("click", SP.showTypeCards);
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

  // Live Drawer/Portable readouts while the user types, not only when the
  // setup screen first opens - see Fix 004 Correction 6.G.
  ["drawer-x", "drawer-y", "drawer-z", "surface-x", "surface-y", "portable-x", "portable-y", "portable-z", "pegboard-x", "pegboard-y", "pegboard-holes-x", "pegboard-holes-y"].forEach(id => {
    const input = document.getElementById(id);
    if (input) input.addEventListener("input", SP.updateReadouts);
  });
  // Surface: on blur show the actual resolved outside size in the inputs.
  ["surface-x", "surface-y"].forEach(id => {
    document.getElementById(id)?.addEventListener("blur", () => {
      const resolved = SP.resolveSurface(
        Number(document.getElementById("surface-x").value),
        Number(document.getElementById("surface-y").value),
        document.getElementById("surface-trim").value,
      );
      SP.normalizeSurfaceInputs(resolved);
      SP.updateReadouts();
    });
  });
  // Changing trim re-resolves the largest field that fits the request that
  // is currently visible; it never grows beyond it.
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
        readout.hidden = false;
        if (resolved.ok) {
            interior.textContent = SP.fieldText(resolved.fieldX, resolved.fieldY);
            trim.textContent = `${SP.surfaceTrimLabel(trimKey)} — ${fmt(resolved.trimWidth)} mm`;
            outside.textContent = `${fmt(resolved.outerX)} × ${fmt(resolved.outerY)} mm`;
        } else {
            interior.textContent = resolved.error;
            trim.textContent = "—";
            outside.textContent = "—";
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
    } else if (kind === "pegboard") {
        const mode = document.getElementById("pegboard-size-mode")?.value || "physical";
        document.getElementById("pegboard-physical-fields").hidden = mode !== "physical";
        document.getElementById("pegboard-hole-fields").hidden = mode !== "holes";
        const resolved = SP.resolvePegboard();
        const readout = document.getElementById("pegboard-readout");
        readout.hidden = !resolved.ok;
        if (resolved.ok) {
          document.getElementById("pegboard-grid-readout").textContent = `${resolved.holesX} × ${resolved.holesY} positions — ${fmt(resolved.holesX * resolved.standard.pitch_x_mm)} × ${fmt(resolved.holesY * resolved.standard.pitch_y_mm)} mm`;
          document.getElementById("pegboard-border-readout").textContent = `${fmt(resolved.residualX / 2)} mm sides, ${fmt(resolved.residualY / 2)} mm top/bottom`;
        }
    }
};

SP.renderSpaceInfo = () => {
    if (typeof syncBaseTrimOption === "function") syncBaseTrimOption();
    const isSpace = state.folderMode === "space" && state.activeSpace;
    const wsName = document.getElementById("workspace-space-name");
    if (wsName) {
        if (isSpace) {
            wsName.textContent = state.activeSpace.name;
            wsName.hidden = false;
        } else {
            wsName.hidden = true;
        }
    }
    
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
    const toggle = document.getElementById("space-mode-toggle");
    if (toggle) {
        const hideToggle = !(typeof DL !== "undefined" && DL.active);
        toggle.hidden = hideToggle;
        const modeRow = document.getElementById("space-mode-row");
        if (modeRow) modeRow.hidden = hideToggle;
    }
    const viewing = document.getElementById("space-head-view");
    if (viewing) viewing.hidden = SP.editing;
    document.getElementById("space-head-name").textContent = state.activeSpace.name;

    const kind = state.activeSpace.kind;
    const kindLabel = SP_KINDS[kind]?.label || kind;
    document.getElementById("space-head-type").textContent = ` - ${kindLabel}`;

    // Fix 034 J: the top Space summary is the single authoritative Actual
    // size / Usable interior readout - existing calculations only, never
    // duplicated math (Portable Storage still uses its simple stored field
    // pending a full B4B assembled-envelope summary wire-up here).
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
        const previewCurrent = Boolean(
            state.preview?.b4b &&
            state.previewDesignKey &&
            state.previewDesignKey === JSON.stringify(state.design)
        );
        const b4b = previewCurrent ? state.preview.b4b : null;
        if (!b4b) {
            actualText = "Calculating…";
            usableText = "Calculating…";
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
};

SP.updateSpace = async () => {
    const values = SP.readSetupValues();
    if (!values) return;
    const { kind, name, x, y, z, trimSize, extra = {} } = values;

    if (state.runtime.hosted) {
        // Mirror local update semantics: the inventory's own layout.space is
        // authoritative on reopen, so it must be updated together with
        // metadata, through the same backend validation as local Edit -
        // see Fix 004 Correction 7.E.
        const folder = state.browserFolder;
        const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
        const result = await api("/api/space/configure-text", {
          inventory_text: inventoryText, inventory_title: name,
          name, kind: state.activeSpace.kind, x, y, z, ...extra,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        await WFFileSystem.writeText(folder.handle, SP.inventoryFilenameFor(folder), result.inventory_text);
        const space = result.layout.space;
        // This call owns the new Space definition (just written above), but
        // not the bin/part defaults - reading them here and passing them
        // back would be exactly the stale pre-lock capture Correction 4
        // eliminates; leaving them unset lets the serialized writer read
        // the newest value from under its own lock instead (C4.1).
        const metadata = await SP.writeMetadata(folder.handle, "space", space, true, {});
        state.activeSpace = space;
        state.activeSpaceId = metadata.space_id || null;
    } else {
        const data = await api("/api/space/update", {
          output: state.output, name: name, x: x, y: y, z: z, ...extra,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        state.activeSpace = data.folder.space;
    }
    SP.cancelInlineEdit();
    toast("Space updated.");
    
    if ((kind === "drawer" || kind === "pegboard") && typeof DL !== "undefined" && DL.active) {
        DL.syncSingleDrawerFromSpace(state.activeSpace);
    }
};



// Cross-type warning
SP.crossTypeCheck = (designType) => {
    if (!state.activeSpace || state.folderMode !== "space") return Promise.resolve(true);
    const kind = state.activeSpace.kind;
    
    let warning = null;
    let targetKind = null;
    if (designType === "b4b" && (kind === "drawer" || kind === "surface" || kind === "pegboard")) {
        warning = `This Space is configured as a ${SP_KINDS[kind].label} and will not be converted. Storage Box is meant for Portable Storage.`;
        targetKind = "portable";
    } else if ((designType === "base-trim" || designType === "base_trim") && (kind === "drawer" || kind === "portable" || kind === "box" || kind === "pegboard")) {
        warning = `This Space is configured as a ${SP_KINDS[kind].label} and will not be converted. Base Trim is meant for Surface Spaces.`;
        targetKind = "surface";
    }
    
    if (warning) {
        document.getElementById("cross-type-warning-text").textContent = warning;
        const dialog = document.getElementById("cross-type-warning-dialog");
        
        return new Promise(resolve => {
            const btnContinue = document.getElementById("cross-type-continue");
            const btnNew = document.getElementById("cross-type-new");

            const cleanup = () => {
                btnContinue.removeEventListener("click", onContinue);
                btnNew.removeEventListener("click", onNew);
                dialog.removeEventListener("cancel", onCancel);
                if (dialog.open) dialog.close();
            };

            const finish = value => {
                cleanup();
                resolve(value);
            };

            const onContinue = () => finish(true);

            const onNew = () => {
                cleanup();
                SP.clearSetupContext();
                SP.showSetup(targetKind);
                resolve(false);
            };

            const onCancel = event => {
                event.preventDefault();
                finish(false);
            };

            btnContinue.addEventListener("click", onContinue);
            btnNew.addEventListener("click", onNew);
            dialog.addEventListener("cancel", onCancel);
            dialog.showModal();
        });
    }
    
    return Promise.resolve(true);
};

// The real design-type control is #bin-type (see changeBinType() in app.js),
// which calls SP.crossTypeCheck() itself before switching into B4B/Base Trim.

// Startup must come after every SP.* helper it (transitively) depends on -
// SP.wire, wireInfoButtons, SP.updateReadouts, SP.renderSpaceInfo,
// SP.crossTypeCheck, and everything SP.launch()/SP.wire() call - is defined,
// so this stays the very last thing in the file. state.ready can already be
// true by the time this script runs, which would otherwise call SP.wire()
// before it exists - see Fix 004 Correction 8.A.
const startSpaces = async () => {
  try {
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

if (state.ready) {
  startSpaces();
} else {
  window.addEventListener("wavefinity:ready", startSpaces, { once: true });
}
