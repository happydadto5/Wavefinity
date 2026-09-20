"use strict";

// Normal Design can work without a persistent folder by downloading generated
// files. Inventory and typed Spaces require a real writable folder. A typed
// Space is a one-time Drawer/Surface/Portable setup layered on that folder;
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
};
const RESUME_AUTOCONTINUE_SECONDS = 10;
const SP_KINDS = {
  portable: { icon: "🧰", label: "Portable Storage" },
  surface: { icon: "🔲", label: "Surface" },
  drawer: { icon: "🗄️", label: "Drawer" },
  // Legacy kind, readable for migration only - never a current Space type;
  // it presents as Portable Storage, its recovery destination.
  box: { icon: "🧰", label: "Portable Storage" },
};
const FOLDER_METADATA = ".wavefinity.json";
const LEGACY_METADATA = ".wavefinity-space.json";
const SPACE_ID_REQUIRED_VERSION = 5;
const FOLDER_METADATA_VERSION = 6;
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
  SP.cancelResumeAutoContinue();
  ["welcome-home", "welcome-resume", "space-unsupported", "space-type-cards", "space-form", "space-configure-prompt", "space-collision-prompt", "space-existing-inventory-prompt"]
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

SP.drawerCapacity = mm => drawerSpaceCapacity(mm);
SP.hasFolder = () => Boolean(state.folderSelected);
SP.canPersistSpace = () => !state.runtime.hosted || Boolean(state.browserFolder?.handle);
// The active folder's inventory filename. Create/Configure must use
// SP.inventoryFilenameFor(folder) against the *selected target* instead -
// this one only ever reflects whatever was already active, which is wrong
// mid-Create before the new folder is activated - see Fix 004 Correction 7.A.
SP.inventoryFilename = () => SP.inventoryFilenameFor(state.browserFolder);
SP.inventoryFilenameFor = _folder => INVENTORY_FILENAME;

SP.resetDrawer = async () => {
  if (typeof DL === "undefined") return;
  if (DL.dirty && DL.layout && DL.output) await DL.save();
  DL.layout = null;
  DL.dirty = false;
  DL.candidates = [];
  DL.selected = null;
  DL.output = null;
  DL.loaded = false;
  if (typeof DP !== "undefined") DP.signatures = {};
};

SP.applyFolder = async (info, { reset = true } = {}) => {
  if (reset) await SP.resetDrawer();
  state.output = info.folder;
  state.activeSpaceId = info.space_id || null;
  state.folderSelected = true;
  setFolderState(
    info.folder_mode,
    info.space,
    info.inventory,
    info.keep_bin_defaults,
    info.bin_defaults,
    info.part_defaults,
  );
  syncForm();
  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
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
  if (!raw || !["drawer", "surface", "portable", "box"].includes(raw.kind)) return null;
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
  // (organizer_spaces._folder_state); v4 is already onboarded and v5 is
  // current - v4 only lacks the Space identity, which is not a setup pass.
  if (![2, 3, 4, 5, 6].includes(current.version)) return { status: "invalid" };
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
      return { status: "space", space, space_id: null, needsIdentityMigration: false, inventory: true, keep_bin_defaults: true, bin_defaults: null, part_defaults: {}, needsMigration: true, metadataVersion: 2 };
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

SP.writeMetadata = async (handle, mode, space = null, inventory = true, changes = {}) => {
  if (!handle) {
    throw new Error("Inventory and Spaces need access to a writable folder.");
  }
  // A Space's layout depends on the inventory, so it is never optional here.
  const metadata = {
    version: FOLDER_METADATA_VERSION, setup_version: SPACE_SETUP_VERSION,
    folder_mode: mode,
  };
  if (mode !== "space" || !space) metadata.inventory = Boolean(inventory);
  if (mode === "space" && space) {
    let spaceId = null;
    let keep = true;
    let defaults = null;
    let partDefaults = {};
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
    }
    if (Object.hasOwn(changes, "keep_bin_defaults")) keep = Boolean(changes.keep_bin_defaults);
    if (Object.hasOwn(changes, "bin_defaults")) defaults = changes.bin_defaults;
    if (Object.hasOwn(changes, "part_defaults")) partDefaults = changes.part_defaults;
    if (defaults !== null && (typeof defaults !== "object" || Array.isArray(defaults))) {
      throw new Error("Bin defaults must be an object or null.");
    }
    if (!partDefaults || typeof partDefaults !== "object" || Array.isArray(partDefaults)) {
      throw new Error("Part defaults must be an object.");
    }
    metadata.space_id = spaceId || crypto.randomUUID();
    metadata.inventory = true;
    metadata.space = space;
    metadata.keep_bin_defaults = keep;
    metadata.bin_defaults = defaults;
    metadata.part_defaults = partDefaults;
  }
  await WFFileSystem.writeText(handle, FOLDER_METADATA, JSON.stringify(metadata, null, 2));
  return metadata;
};

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

SP.addInventoryBin = async entry => {
  const data = await SP.inventoryRequest("/api/drawer/save", { new_bins: [entry] });
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

  return {
    folder: folder.name,
    folder_name: folder.name,
    folder_mode: mode,
    space,
    space_id: mode === "space" ? spaceId : null,
    needs_identity_migration: mode === "space" && needsIdentity,
    space_source: spaceSource,
    setup_prefill_space: setupPrefillSpace,
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

SP.useHostedFolder = async (folder, { expectedSpaceId = null } = {}) => {
  // A hosted Design session without a persistent folder is "no folder
  // selected", never a fabricated one. Opening a Wavefinity folder therefore
  // always needs a real handle.
  if (!folder?.handle) {
    throw new Error("Opening a Wavefinity folder requires writable folder access.");
  }
  let info = await SP.inspectHosted(folder);
  // The hosted equivalent of the local technical open: only after read-only
  // classification says no setup is needed, adopt the canonical inventory
  // filename and give a configured v4 folder its v5 identity.
  SP.assertExpectedHostedIdentity(info, expectedSpaceId);
  if (!info.needs_setup) {
    if (info.inventory) await SP.readInventoryFor(folder, { migrate: true });
    const upgradeSpace = info.folder_mode === "space" && (
      info.needs_identity_migration || (info.metadata_version || 0) < FOLDER_METADATA_VERSION
    );
    const upgradeDesign = info.folder_mode === "design" && info.metadata_version && info.metadata_version < FOLDER_METADATA_VERSION;
    if (upgradeSpace) {
      await SP.writeMetadata(folder.handle, "space", info.space, true, {
        keep_bin_defaults: info.keep_bin_defaults, bin_defaults: info.bin_defaults,
        part_defaults: info.part_defaults,
      });
    } else if (upgradeDesign) {
      await SP.writeMetadata(folder.handle, "design", null, info.inventory);
    }
    if (upgradeSpace || upgradeDesign) info = await SP.inspectHosted(folder);
  }
  if (expectedSpaceId && info.space_id !== expectedSpaceId) {
    throw new Error("This folder is not the Space that was open before. Use Open Existing Space to choose it.");
  }
  await SP.resetDrawer();
  state.browserFolder = folder;
  await WFFileSystem.save("active", { handle: folder.handle, space_id: info.space_id || null });
  await SP.applyFolder(info, { reset: false });
  SP.close();
  toast(info.folder_mode === "space"
    ? `Opened ${info.space.name || folder.name}.`
    : `Saving designs to ${folder.name}.`);
  return info;
};

// ------------------------------------------------------------ folder choice

// Returns a real folder or null - never a pretend one. With stayOnSetup the
// caller is mid-setup, so a refusal explains itself inline instead of
// throwing the person's entered Space details away.
SP.pickFolder = async ({ stayOnSetup = false } = {}) => {
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

  const data = await api("/api/browse-output-folder", { current: state.output });
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
    return SP.useHostedFolder(folder);
  }
  const inspected = await api("/api/space/inspect", { output: folder });
  SP.recent = inspected.recent || [];
  if (inspected.folder?.needs_setup) {
    SP.enterSetupFor(folder, inspected.folder);
    return inspected.folder;
  }
  const data = await api("/api/folder/use", { output: folder });
  SP.recent = data.recent || [];
  await SP.applyFolder(data.folder);
  SP.close();
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

SP.updateBinDefaults = async (changes = {}) => {
  if (state.folderMode !== "space") return;
  const updates = {};
  if (Object.hasOwn(changes, "enabled")) updates.keep_bin_defaults = Boolean(changes.enabled);
  if (Object.hasOwn(changes, "snapshot")) updates.bin_defaults = changes.snapshot;
  if (Object.hasOwn(changes, "partDefaults")) updates.part_defaults = changes.partDefaults;
  if (!Object.keys(updates).length) return;
  let info;
  if (state.runtime.hosted) {
    info = await SP.writeMetadata(
      state.browserFolder?.handle,
      "space",
      state.activeSpace,
      true,
      updates,
    );
  } else {
    const data = await api("/api/space/defaults", { output: state.output, ...updates });
    info = data.folder;
  }
  state.keepBinDefaults = Boolean(info.keep_bin_defaults);
  state.spaceBinDefaults = info.bin_defaults && typeof info.bin_defaults === "object"
    ? clone(info.bin_defaults) : null;
  state.spacePartDefaults = info.part_defaults && typeof info.part_defaults === "object"
    ? clone(info.part_defaults) : {};
  if (typeof DP !== "undefined" && DP.built) DP.renderSave();
};

SP.setKeepBinDefaults = enabled => SP.run(async () => {
  await SP.updateBinDefaults({ enabled });
  toast(enabled ? "Keeping bin defaults for this Space." : "Bin defaults turned off for this Space.");
});

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
    if (remaining <= 0) { SP.confirmResume(); return; }
    if (button) button.textContent = `Open Space (${remaining})`;
  }, 1000);
};

SP.confirmResume = () => {
  SP.cancelResumeAutoContinue();
  SP.close();
  activatePreviewView("3d");
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


SP.showHome = () => {
  SP.showOnly("welcome-home");
  SP.renderRecent();
  const hasRecent = SP.recent.length > 0;
  document.getElementById("welcome-recent-container").hidden = !hasRecent;
  SP.showDialog();
};

SP.showTypeCards = () => {
  SP.showOnly("space-type-cards");
  SP.showDialog();
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

SP.showSetup = (kind, prefillSpace = null, { update = false } = {}) => {
  SP.showOnly("space-form");
  // Every entry into setup explicitly states whether it is editing the
  // current Space, so a stale Edit that was backed out of can never make a
  // later Create/New Space silently call SP.updateSpace() - see
  // Fix 004 Correction 6.F.
  SP.isUpdate = update;
  SP.setupKind = kind;
  SP.populateSurfaceTrim();
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
  document.getElementById("space-folder-help").hidden = !(kind === "drawer" && !update);
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
  }
  SP.updateReadouts();
  SP.showDialog();
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

  return fail("Choose a Space type.", "#space-name");
};

SP.create = async () => {
  if (SP.isUpdate) return SP.updateSpace();
  const values = SP.readSetupValues();
  if (!values) return;
  const { kind, name, x, y, z, trimSize } = values;

  // Folder last
  const folder = SP.configureData || await SP.pickFolder({ stayOnSetup: true });
  if (!folder) return;
  // A folder already selected via SP.configureData (Open Existing ->
  // needs setup, or Configure Existing) is an explicit migration of that
  // folder, not a brand-new typed Space - see Fix 004 Correction 6.D.
  const migrating = Boolean(SP.configureData);

  if (!migrating) {
      const data = state.runtime.hosted
          ? await SP.inspectHosted(folder)
          : (await api("/api/space/inspect", { output: folder })).folder;
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

  let info;
  if (state.runtime.hosted) {
    // Read/write the *selected target's* inventory filename, never the
    // previously-active folder's - see Fix 004 Correction 7.A.
    const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
    let keepBinDefaults = true;
    let binDefaults = null;
    let partDefaults = {};
    if (migrating) {
      const { current } = await SP.readMetadata(folder.handle);
      const currentState = SP.classifyMetadata(current);
      if (currentState.status === "space") {
        keepBinDefaults = currentState.keep_bin_defaults;
        binDefaults = currentState.bin_defaults;
        partDefaults = currentState.part_defaults || {};
      }
    }
    const result = await api(migrating ? "/api/space/configure-text" : "/api/space/create-text", {
      inventory_text: inventoryText, inventory_title: name,
      name, kind, x, y, z, ...(trimSize ? { trim_size: trimSize } : {}),
    });
    await WFFileSystem.writeText(folder.handle, SP.inventoryFilenameFor(folder), result.inventory_text);
    const space = result.layout.space;
    const metadata = await SP.writeMetadata(folder.handle, "space", space, true, {
      keep_bin_defaults: keepBinDefaults,
      bin_defaults: binDefaults,
      part_defaults: partDefaults,
    });
    // Activate the selected target folder itself, not whatever folder was
    // previously active - see Fix 004 Correction 7.A.
    state.browserFolder = folder;
    await WFFileSystem.save("active", { handle: folder.handle, space_id: metadata.space_id });
    info = {
      folder: folder.name, folder_name: folder.name, folder_mode: "space", space,
      space_id: metadata.space_id,
      inventory: true, keep_bin_defaults: metadata.keep_bin_defaults,
      bin_defaults: metadata.bin_defaults, part_defaults: metadata.part_defaults,
    };
  } else {
    const data = await api(migrating ? "/api/space/configure" : "/api/space/create", {
      output: folder, name, kind, x, y, z, keep_bin_defaults: true,
      ...(trimSize ? { trim_size: trimSize } : {}),
    });
    SP.recent = data.recent || [];
    info = data.folder;
  }

  await SP.applyFolder(info);
  SP.close();
  
  if (kind === "portable") await SP.designPortable(info.space);
  else if (kind === "surface") await SP.designSurface(info.space);
  else await loadFreshOrdinaryDesignForCurrentFolder();
};

// Reuses the real Base Trim design path (makeBaseTrimDesign) rather than
// building a second, incompatible "edge" design object - see Fix 004.
SP.designSurface = async space => {
  const trimValue = SP.surfacePresetMap()[space.trim_size];
  state.surfaceEdgeHandled = false;
  if (!baseTrimEnabled()) state.lastOrdinaryDesign = clone(state.design);

  state.design = makeBaseTrimDesign(space.x, space.y);
  state.design.base_trim.width_mm = trimValue;
  state.design.box.z = trimValue;
  state.design.part_name = space.name;

  clearDraftSelection();
  syncForm();
  activatePreviewView("3d");
  await refreshPreview();

  if (SP.renderSpaceInfo) SP.renderSpaceInfo();
  toast(`Designing Surface: ${space.name}`);
};

// Reuses the ordinary bin -> B4B toggle machinery (toggleB4B/readB4BForm)
// rather than forking B4B form logic - see Fix 004 ("Portable -> Bin for Bins").
SP.designPortable = async space => {
  state.design = clone(state.catalog.defaults.design);
  state.design.box.x = space.x;
  state.design.box.y = space.y;
  state.design.box.z = normalizeBinDimension("z", space.z);
  state.design.part_name = space.name;

  clearDraftSelection();
  syncForm();
  $("#bin-type").value = "b4b";
  await toggleB4B(true);
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
      ["drawer", "surface", "box", "portable"].includes(candidate.kind);

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
    const folder = await SP.pickFolder();
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
        await SP.writeMetadata(folder.handle, "design", null, true);
        SP.configureData = null;
        await SP.useHostedFolder(folder);
        await loadFreshOrdinaryDesignForCurrentFolder();
    } else {
        const data = await api("/api/space/use-untyped", { output: SP.configureData });
        // Clear the selected-folder setup context now that it has been
        // used, so a later Create New Space cannot accidentally reuse it -
        // see Fix 004 Correction 7.F.
        SP.configureData = null;
        SP.recent = data.recent || [];
        await SP.applyFolder(data.folder);
        SP.close();
        await loadFreshOrdinaryDesignForCurrentFolder();
    }
};



SP.fail = (message, selector) => {
  $("#space-error").textContent = message;
  $("#space-error").hidden = false;
  $(selector)?.focus();
};

SP.launch = async () => {
  if (state.runtime.hosted) {
    try {
      const saved = await WFFileSystem.load("active");
      // Startup is not a user gesture: only already-granted permission may
      // resume silently. A handle whose permission needs renewing falls
      // through to Welcome, where an explicit action supplies the gesture.
      // The saved record itself is kept.
      if (saved?.handle && await WFFileSystem.queryReadWritePermission(saved.handle)) {
        const folder = { handle: saved.handle, name: saved.handle.name };
        const data = await SP.inspectHosted(folder);
        SP.assertExpectedHostedIdentity(data, saved.space_id || null);
        if (data.needs_setup) {
          SP.enterSetupFor(folder, data);
          return;
        }
        const info = await SP.useHostedFolder(folder, { expectedSpaceId: saved.space_id || null });
        if (info.folder_mode === "space") SP.showResume(info);
        return;
      }
    } catch (_error) { /* The welcome screen offers a fresh folder choice. */ }
    SP.showHome();
    return;
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
    await SP.applyFolder(data);
    // The routing decision must always end somewhere definite: the startup
    // cover is dismissed only once this resolves.
    if (data.folder_mode === "space") SP.showResume(data);
    else SP.close();
  } catch (_error) {
    SP.showHome();
  }
};

SP.wire = () => {
  wireInfoButtons();
  document.querySelectorAll("#welcome-close, #welcome-resume-close, #space-unsupported-close, #space-form-close, #space-type-cards-close")
    .forEach(el => el?.addEventListener("click", SP.close));
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.close(); });
  SP.dialog().addEventListener("close", SP.cancelResumeAutoContinue);
  const welcomeCreate = document.getElementById("welcome-create");
  if (welcomeCreate) welcomeCreate.addEventListener("click", SP.beginCreateNew);
  const welcomeOpen = document.getElementById("welcome-open");
  if (welcomeOpen) welcomeOpen.addEventListener("click", () => SP.run(SP.openExisting));
  const welcomeResumeContinue = document.getElementById("welcome-resume-continue");
  if (welcomeResumeContinue) welcomeResumeContinue.addEventListener("click", SP.confirmResume);
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
  if (spaceForm) spaceForm.addEventListener("submit", event => {
    event.preventDefault();
    SP.run(SP.create);
  });
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
  ["drawer-x", "drawer-y", "drawer-z", "surface-x", "surface-y", "portable-x", "portable-y", "portable-z"].forEach(id => {
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
    }
};

SP.renderSpaceInfo = () => {
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
    
    const infoBlocks = [
        { prefix: "space-info", saveBlock: "save-location-row" },
        { prefix: "dl-space-info", saveBlock: null }
    ];
    
    infoBlocks.forEach(({prefix, saveBlock}) => {
        const block = document.getElementById(prefix + "-block");
        if (!block) return;
        if (saveBlock) {
            const saveEl = document.getElementById(saveBlock);
            if (saveEl) saveEl.hidden = isSpace;
        }
        
        if (!isSpace) {
            block.hidden = true;
            return;
        }
        
        block.hidden = false;
        document.getElementById(prefix + "-name").textContent = state.activeSpace.name;
        
        const kind = state.activeSpace.kind;
        const kindLabel = SP_KINDS[kind]?.label || kind;
        document.getElementById(prefix + "-type").textContent = kindLabel;
        
        let sizeText = "";
        const unit = state.catalog?.base_unit || 8;
        if (kind === "drawer") {
            const x = state.activeSpace.x;
            const y = state.activeSpace.y;
            const z = state.activeSpace.z;
            sizeText = x + " × " + y + " × " + z + " mm (" + SP.drawerCapacity(x) + " × " + SP.drawerCapacity(y) + " units)";
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
            sizeText = "Interior " + SP.fieldText(x, y) + ", " + trim + " trim; finished outside "
                + fmt(outsideX) + " × " + fmt(outsideY) + " mm";
        } else if (kind === "portable" || kind === "box") {
            const x = state.activeSpace.x;
            const y = state.activeSpace.y;
            const z = state.activeSpace.z;
            sizeText = (x/unit) + " × " + (y/unit) + " units (" + x + " × " + y + " mm) x " + z + " mm usable height";
        }
        document.getElementById(prefix + "-size").textContent = sizeText;
        
        const btnNew = document.getElementById(prefix + "-new-space");
        if (btnNew) btnNew.hidden = false;
        
        const btnShow = document.getElementById(prefix + "-show");
        if (btnShow) btnShow.hidden = state.runtime.hosted;
    });
};

SP.showFolder = async () => {
    if (!state.output || state.runtime.hosted) return;
    const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
    const isWin = navigator.platform.toUpperCase().indexOf("WIN") >= 0;
    const fm = isMac ? "Finder" : (isWin ? "File Explorer" : "your file manager");
    if (!confirm("Open this Space in " + fm + "?")) return;
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
const wireInfoButtons = (prefix = "space-info") => {
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
    const { kind, name, x, y, z, trimSize } = values;

    if (state.runtime.hosted) {
        // Mirror local update semantics: the inventory's own layout.space is
        // authoritative on reopen, so it must be updated together with
        // metadata, through the same backend validation as local Edit -
        // see Fix 004 Correction 7.E.
        const folder = state.browserFolder;
        const inventoryText = await SP.readInventoryFor(folder, { migrate: true });
        const result = await api("/api/space/configure-text", {
          inventory_text: inventoryText, inventory_title: name,
          name, kind: state.activeSpace.kind, x, y, z,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        await WFFileSystem.writeText(folder.handle, SP.inventoryFilenameFor(folder), result.inventory_text);
        const space = result.layout.space;
        const { current } = await SP.readMetadata(folder.handle);
        const currentState = SP.classifyMetadata(current);
        const keep = currentState.status === "space" ? currentState.keep_bin_defaults : true;
        const defaults = currentState.status === "space" ? currentState.bin_defaults : null;
        const partDefaults = currentState.status === "space" ? currentState.part_defaults : {};
        const metadata = await SP.writeMetadata(folder.handle, "space", space, true, {
          keep_bin_defaults: keep,
          bin_defaults: defaults,
          part_defaults: partDefaults,
        });
        state.activeSpace = space;
        state.activeSpaceId = metadata.space_id || null;
    } else {
        const data = await api("/api/space/update", {
          output: state.output, name: name, x: x, y: y, z: z,
          ...(trimSize ? { trim_size: trimSize } : {}),
        });
        state.activeSpace = data.folder.space;
    }
    SP.isUpdate = false;
    SP.renderSpaceInfo();
    SP.close();
    toast("Space updated.");
    
    if (kind === "drawer" && typeof DL !== "undefined" && DL.active) {
        DL.syncSingleDrawerFromSpace(state.activeSpace);
    }
};



// Cross-type warning
SP.crossTypeCheck = (designType) => {
    if (!state.activeSpace || state.folderMode !== "space") return Promise.resolve(true);
    const kind = state.activeSpace.kind;
    
    let warning = null;
    let targetKind = null;
    if (designType === "b4b" && (kind === "drawer" || kind === "surface")) {
        warning = `This Space is configured as a ${SP_KINDS[kind].label} and will not be converted. Storage Box is meant for Portable Storage.`;
        targetKind = "portable";
    } else if ((designType === "base-trim" || designType === "base_trim") && (kind === "drawer" || kind === "portable" || kind === "box")) {
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

  // Only now does the first preview begin, behind the correct screen.
  // refreshPreview() discards stale responses, so a later user action wins.
  await refreshPreview();
};

if (state.ready) {
  startSpaces();
} else {
  window.addEventListener("wavefinity:ready", startSpaces, { once: true });
}
