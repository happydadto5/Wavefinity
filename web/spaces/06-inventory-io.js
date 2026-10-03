"use strict";

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
SP.writeHostedFileSet = async (handle, filesBase64 = {}) => {
  const names = Object.keys(filesBase64 || {});
  if (!names.length) return { rollback: async () => {} };

  const prior = new Map();
  const written = [];

  const restore = async () => {
    const failed = [];
    for (const name of [...written].reverse()) {
      try {
        const old = prior.get(name);
        if (old) await WFFileSystem.writeBlob(handle, name, old);
        else await WFFileSystem.removeFile(handle, name);
      } catch (error) {
        failed.push(`${name}: ${error?.message || "restore failed"}`);
      }
    }
    if (failed.length) {
      throw new Error(
        "Some generated files could not be restored; check the Space folder. "
        + failed.join("; ")
      );
    }
  };

  try {
    for (const name of names) {
      prior.set(name, await WFFileSystem.readBlob(handle, name));
      const bytes = Uint8Array.from(atob(filesBase64[name]), c => c.charCodeAt(0));
      await WFFileSystem.writeBlob(
        handle,
        name,
        new Blob([bytes], { type: "model/3mf" }),
      );
      written.push(name);
    }
  } catch (error) {
    try {
      await restore();
    } catch (rollbackError) {
      throw new Error(
        `${error?.message || "Generated-file write failed."} ${rollbackError.message}`
      );
    }
    throw error;
  }

  return { rollback: restore };
};
SP.inventoryRequest = async (
  path,
  extra = {},
  {
    write = true,
    context = null,
    sideEffect = false,
    onStillFinishing = null,
    ...requestOptions
  } = {},
) => {
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
    const inventoryText = await SP.readInventoryFor(
      { ...folder, handle },
      { migrate: write },
    );
    const deleting = path === "/api/drawer/save" && Boolean(extra.delete_ids?.length);
    const mayDeleteOwnedFiles =
      deleting || path === "/api/drawer/spacers/refresh";
    const needsFilenameSnapshot =
      mayDeleteOwnedFiles ||
      path === "/api/drawer/design-source/save" ||
      path === "/api/drawer/design-source/status";

    requireContext();
    const availableFilenames = needsFilenameSnapshot
      ? await WFFileSystem.listFilenames(handle)
      : [];
    requireContext();

    const requestBody = {
      inventory_text: inventoryText,
      inventory_title: title,
      ...extra,
      ...(needsFilenameSnapshot
        ? { available_filenames: availableFilenames }
        : {}),
    };
    const data = sideEffect
      ? await apiSideEffect(path, requestBody, { onStillFinishing })
      : await api(path, requestBody, requestOptions);

    requireContext();
    const fileTxn = await SP.writeHostedFileSet(
      handle,
      data.files_base64 || {},
    );

    try {
      requireContext();
      if (write && typeof data.inventory_text === "string") {
        await WFFileSystem.writeText(
          handle,
          INVENTORY_FILENAME,
          data.inventory_text,
        );
      }
    } catch (error) {
      try {
        await fileTxn.rollback();
      } catch (rollbackError) {
        throw new Error(
          `${error?.message || "Inventory write failed."} ${rollbackError.message}`
        );
      }
      throw error;
    }

    if (data.cleanup_files?.length) {
      const generatedNames = new Set(Object.keys(data.files_base64 || {}));
      const failed = [];
      for (const name of data.cleanup_files) {
        requireContext();
        if (generatedNames.has(name)) continue;
        if (availableFilenames.length && !availableFilenames.includes(name)) continue;
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
  // Fix 096 A2: the row and its canonical editable source are one atomic
  // creation - a bin/b4b row is never durably created without its
  // design_specs entry, so no two-step window can leave it source-less.
  // The backend raises (operation failure) if a bin/b4b row arrives without
  // a spec.
  const data = await SP.inventoryRequest("/api/drawer/save", {
    new_bins: [entry], ...(designSpec ? { new_bin_specs: [designSpec] } : {}),
  }, { sideEffect: true });
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
    const ok = await SP.leaveSpaceSafely();
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
  await SP.rememberHostedRecent(folder, info);
  SP.close();
  if (openPreferredView && info.folder_mode === "space") {
    if (!(await SP.openTypedSpacePreferredView())) return null;
  }
  toast(info.folder_mode === "space"
    ? `Opened ${info.space.name || folder.name}.`
    : `Saving designs to ${folder.name}.`);
  return info;
};

// The active folder's inventory filename. Create/Configure must use
// SP.inventoryFilenameFor(folder) against the *selected target* instead -
// this one only ever reflects whatever was already active, which is wrong
// mid-Create before the new folder is activated - see Fix 004 Correction 7.A.
SP.inventoryFilename = () => SP.inventoryFilenameFor(state.browserFolder);
SP.inventoryFilenameFor = _folder => INVENTORY_FILENAME;

