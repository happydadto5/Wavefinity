"use strict";

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
        const reset = await apiSideEffect("/api/space/storage-drawers-reset", { space: raw });
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

