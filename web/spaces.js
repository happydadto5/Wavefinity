"use strict";

// A save folder is always available for normal design work. Space planning is
// an optional capability layered on that folder, never a design type.
const SP = { recent: [], setup: null, busy: false, resume: null, resumeTimer: null };
const RESUME_AUTOCONTINUE_SECONDS = 10;
const SP_KINDS = {
  portable: { icon: "🧰", label: "Portable Storage" },
  surface: { icon: "🔲", label: "Surface" },
  drawer: { icon: "🗄️", label: "Drawer" },
  box: { icon: "📦", label: "Box" },
};
const FOLDER_METADATA = ".wavefinity.json";
const LEGACY_METADATA = ".wavefinity-space.json";
const FOLDER_METADATA_VERSION = 4;

const spSame = (a, b) => {
  const tidy = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return tidy(a) === tidy(b);
};

SP.dialog = () => $("#welcome-dialog");
SP.close = () => { if (SP.dialog().open) SP.dialog().close(); };
SP.showOnly = id => {
  SP.cancelResumeAutoContinue();
  ["welcome-home", "welcome-resume", "space-unsupported", "space-type-cards", "space-form", "space-configure-prompt"]
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
SP.kind = () => $('input[name="space-kind"]:checked')?.value || "drawer";
SP.readSize = () => ["#space-x", "#space-y", "#space-z"].map(sel => number($(sel).value, NaN));
SP.snap = mm => {
  const unit = state.catalog?.base_unit || 8;
  const max = Math.floor((state.catalog?.max_box_size || 350) / unit) * unit;
  return Math.min(max, Math.max(unit, Math.round(mm / unit) * unit));
};
SP.hasFolder = () => Boolean(state.folderSelected);
SP.canPersistSpace = () => !state.runtime.hosted || Boolean(state.browserFolder?.handle);
SP.inventoryFilename = () => `${state.browserFolder?.name || "Wavefinity"} bins.md`;

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
  state.folderSelected = true;
  setFolderState(
    info.folder_mode,
    info.space,
    info.inventory,
    info.keep_bin_defaults,
    info.bin_defaults,
  );
  syncForm();
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
    x: Number(raw.x), y: Number(raw.y), z: Number(raw.z),
  };
  return [space.x, space.y, space.z].every(value => Number.isFinite(value) && value > 0) ? space : null;
};

SP.classifyMetadata = record => {
  if (!record?.exists) return { status: "missing" };
  if (record.error || !record.data || typeof record.data !== "object" || Array.isArray(record.data)) {
    return { status: "invalid" };
  }
  const current = record.data;
  if (Number(current.version) > FOLDER_METADATA_VERSION) return { status: "unsupported" };
  if (![2, FOLDER_METADATA_VERSION].includes(current.version)) return { status: "invalid" };
  const needsMigration = current.version === 2;
  const explicitInventory = typeof current.inventory === "boolean" ? current.inventory : null;
  if (current.folder_mode === "design") return { status: "design", inventory: explicitInventory, needsMigration };
  if (current.folder_mode === "space") {
    const space = SP.validSpace(current.space);
    if (!space) return { status: "invalid-space" };
    if (needsMigration) {
      return { status: "space", space, inventory: true, keep_bin_defaults: true, bin_defaults: null, needsMigration: true };
    }
    const keep = current.keep_bin_defaults === undefined ? true : current.keep_bin_defaults;
    const defaults = current.bin_defaults === undefined ? null : current.bin_defaults;
    if (typeof keep !== "boolean" || (defaults !== null && (typeof defaults !== "object" || Array.isArray(defaults)))) {
      return { status: "invalid" };
    }
    return { status: "space", space, inventory: true, keep_bin_defaults: keep, bin_defaults: defaults, needsMigration: false };
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
  if (!handle) return;
  // A Space's layout depends on the inventory, so it is never optional here.
  const metadata = { version: FOLDER_METADATA_VERSION, folder_mode: mode, inventory: mode === "space" ? true : Boolean(inventory) };
  if (mode === "space" && space) {
    let keep = true;
    let defaults = null;
    const { current } = await SP.readMetadata(handle);
    const currentState = SP.classifyMetadata(current);
    if (!["missing", "design", "space"].includes(currentState.status)) throw SP.metadataError(currentState.status);
    if (currentState.status === "space") {
      keep = currentState.keep_bin_defaults;
      defaults = currentState.bin_defaults;
    }
    if (Object.hasOwn(changes, "keep_bin_defaults")) keep = Boolean(changes.keep_bin_defaults);
    if (Object.hasOwn(changes, "bin_defaults")) defaults = changes.bin_defaults;
    if (defaults !== null && (typeof defaults !== "object" || Array.isArray(defaults))) {
      throw new Error("Bin defaults must be an object or null.");
    }
    metadata.space = space;
    metadata.keep_bin_defaults = keep;
    metadata.bin_defaults = defaults;
  }
  await WFFileSystem.writeText(handle, FOLDER_METADATA, JSON.stringify(metadata, null, 2));
  return metadata;
};

SP.inventoryRequest = async (path, extra = {}, { write = true } = {}) => {
  const folder = state.browserFolder;
  if (!folder?.handle) throw new Error("Keeping an inventory needs folder access so Wavefinity can save it with your designs.");
  const inventoryText = await WFFileSystem.readText(folder.handle, SP.inventoryFilename()) || "";
  const data = await api(path, {
    inventory_text: inventoryText,
    inventory_title: state.activeSpace?.name || folder.name,
    ...extra,
  });
  if (write && typeof data.inventory_text === "string") {
    await WFFileSystem.writeText(folder.handle, SP.inventoryFilename(), data.inventory_text);
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

SP.inspectHosted = async folder => {
  const { current, legacy } = await SP.readMetadata(folder.handle);
  const currentState = SP.classifyMetadata(current);
  const legacyState = SP.classifyLegacyMetadata(legacy);
  const inventoryText = await WFFileSystem.readText(folder.handle, `${folder.name} bins.md`) || "";
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
  // An explicit layout.space is authoritative. One the server had to infer
  // from the drawer layout alone (no layout.space at all) can only ever
  // guess "drawer" - it must not outrank real Box metadata below, so it is
  // only considered as a last resort further down.
  const genuineInventorySpace = inventorySpace && !inventorySpaceInferred;

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
  const legacyMatters = !genuineInventorySpace && currentState.status !== "space";
  if (legacyMatters && legacyState.status === "invalid") {
    throw SP.metadataError(legacyState.status);
  }

  let mode;
  let space = null;
  let inventory = true;
  let keepBinDefaults = true;
  let binDefaults = null;
  let shouldWriteMetadata = false;
  if (genuineInventorySpace) {
    mode = "space";
    space = inventorySpace;
    shouldWriteMetadata = ["missing", "design", "space"].includes(currentState.status);
    if (currentState.status === "space") {
      keepBinDefaults = currentState.keep_bin_defaults;
      binDefaults = currentState.bin_defaults;
    }
  } else if (currentState.status === "space") {
    mode = "space";
    space = currentState.space;
    keepBinDefaults = currentState.keep_bin_defaults;
    binDefaults = currentState.bin_defaults;
    shouldWriteMetadata = currentState.needsMigration;
  } else if (legacyState.status === "space") {
    // A stale or absent current "design" marker must not hide a genuine
    // legacy Space identity - a current "design" marker is not a positive
    // Space identity, only current "space" metadata (handled above) is.
    mode = "space";
    space = legacyState.space;
    shouldWriteMetadata = true;
  } else if (currentState.status === "design") {
    mode = "design";
    // A folder saved before this preference existed keeps inventory on by default.
    inventory = currentState.inventory === null ? true : currentState.inventory;
    shouldWriteMetadata = currentState.needsMigration || currentState.inventory === null;
  } else if (legacyState.status === "design") {
    mode = "design";
    shouldWriteMetadata = true;
  } else if (inventorySpace) {
    // No authoritative metadata anywhere: fall back to the layout-only
    // inference (always "drawer" - there is no Box concept for it to recover).
    mode = "space";
    space = inventorySpace;
    shouldWriteMetadata = true;
  } else {
    mode = "design";
    shouldWriteMetadata = true;
  }

  if (mode === "space" && space && !genuineInventorySpace) {
    const result = await api("/api/space/create-text", {
      inventory_text: inventoryText,
      inventory_title: space.name || folder.name,
      ...space,
    });
    await WFFileSystem.writeText(folder.handle, `${folder.name} bins.md`, result.inventory_text);
  }
  if (shouldWriteMetadata) await SP.writeMetadata(folder.handle, mode, space, inventory, {
    keep_bin_defaults: keepBinDefaults,
    bin_defaults: binDefaults,
  });
  return {
    folder: folder.name,
    folder_name: folder.name,
    folder_mode: mode,
    space,
    inventory: mode === "space" ? true : inventory,
    keep_bin_defaults: mode === "space" ? keepBinDefaults : false,
    bin_defaults: mode === "space" ? binDefaults : null,
    missing: false,
  };
};

SP.useHostedFolder = async folder => {
  // A download-only fallback is not a folder: there is no handle to inspect,
  // no metadata to restore, and nowhere to keep inventory. Treating it like a
  // chosen folder would make inspectHosted() default inventory back on.
  const info = folder?.handle
    ? await SP.inspectHosted(folder)
    : {
        folder: folder.name,
        folder_name: folder.name,
        folder_mode: "design",
        space: null,
        inventory: false,
        keep_bin_defaults: false,
        bin_defaults: null,
        missing: false,
      };
  await SP.resetDrawer();
  state.browserFolder = folder;
  await WFFileSystem.save("active", { handle: folder.handle });
  await SP.applyFolder(info, { reset: false });
  SP.close();
  toast(folder.fallback
    ? "Downloads still work. Inventory and Space planning need desktop Chrome or Edge with folder access allowed."
    : info.folder_mode === "space"
    ? `Opened ${info.space.name || folder.name}.`
    : `Saving designs to ${folder.name}.`, false, folder.fallback ? 7000 : 3200);
  return info;
};

// ------------------------------------------------------------ folder choice

SP.pickFolder = async () => {
  if (state.runtime.hosted) {
    if (!window.WFFileSystem?.supportsDirectoryPicker()) {
      return { handle: null, name: "Browser downloads", fallback: true };
    }
    const handle = await WFFileSystem.pickDirectory();
    return handle ? { handle, name: handle.name } : null;
  }
  const data = await api("/api/browse-output-folder", { current: state.output });
  return data.folder || null;
};

SP.afterPick = async folder => {
  if (!folder) return null;
  if (state.runtime.hosted) return SP.useHostedFolder(folder);
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
// on, and a hosted download-only fallback has no folder to keep one in, so
// the control is disabled in both cases (see setFolderState) - these checks
// just guard against a stray change event reaching here anyway.
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
  if (typeof DP !== "undefined" && DP.built) DP.renderSave();
};

SP.setKeepBinDefaults = enabled => SP.run(async () => {
  await SP.updateBinDefaults({ enabled });
  toast(enabled ? "Keeping bin defaults for this Space." : "Bin defaults turned off for this Space.");
});

SP.continueSpaceSetup = info => {
  if (info?.folder_mode === "space") return SP.showResume(info);
  if (!SP.canPersistSpace()) return SP.showFolderAccessNeeded();
  SP.showSetup();
};

SP.changeFolderThenSetup = () => SP.run(async () => {
  const folder = await SP.pickFolder();
  if (!folder) return;
  const info = await SP.afterPick(folder);
  SP.continueSpaceSetup(info);
});

// ------------------------------------------------------------ welcome/manage

SP.renderRecent = () => {
  const list = $("#welcome-recent");
  if (!SP.recent.length) {
    list.innerHTML = `<li class="welcome-empty">No recent folders yet.</li>`;
    return;
  }
  list.innerHTML = SP.recent.map((one, index) => {
    const unavailable = one.missing || one.invalid;
    const space = one.folder_mode === "space";
    const kind = SP_KINDS[one.kind];
    const meta = [one.invalid ? "metadata unavailable" : space ? `${kind?.label || "Space"} · SPACE` : "Design folder", SP.sizeText(one.size), one.missing ? "folder not found" : ""]
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

SP.offerSpacePlanning = () => {
  if (!SP.hasFolder()) return SP.showHome();
  if (!SP.canPersistSpace()) return SP.showFolderAccessNeeded();
  SP.showOnly("space-optional");
  SP.showDialog();
};

SP.showFolderAccessNeeded = () => {
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

SP.showSetup = (kind) => {
  SP.showOnly("space-form");
  SP.setupKind = kind;
  document.querySelectorAll(".space-type-fields").forEach(el => el.hidden = true);
  const field = document.getElementById(`space-fields-${kind}`);
  if (field) field.hidden = false;
  document.getElementById("space-name").value = "";
  document.getElementById("space-error").hidden = true;
  document.getElementById("space-note").textContent = "";
  if (kind === 'drawer') {
      document.getElementById('drawer-x').value = '';
      document.getElementById('drawer-y').value = '';
      document.getElementById('drawer-z').value = '';
  } else if (kind === 'surface') {
      document.getElementById('surface-x').value = '';
      document.getElementById('surface-y').value = '';
  } else if (kind === 'portable') {
      document.getElementById('portable-x').value = '';
      document.getElementById('portable-y').value = '';
      document.getElementById('portable-z').value = '';
  }
  SP.showDialog();
};

SP.startUntyped = async () => {
  const folder = await SP.pickFolder();
  if (!folder) return;
  if (state.runtime.hosted) {
      await SP.useHostedFolder(folder);
  } else {
      const data = await api("/api/space/use-untyped", { output: folder });
      SP.recent = data.recent || [];
      await SP.applyFolder(data.folder);
      SP.close();
  }
};

SP.create = async () => {
  const kind = SP.setupKind;
  const name = document.getElementById("space-name").value.trim();
  if (!name) return SP.fail("Give the Space a name.", "#space-name");
  
  let x, y, z;
  const unit = state.catalog?.base_unit || 8;
  
  if (kind === 'drawer') {
      x = Number(document.getElementById('drawer-x').value);
      y = Number(document.getElementById('drawer-y').value);
      z = Number(document.getElementById('drawer-z').value);
      if (![x, y, z].every(v => Number.isFinite(v) && v > 0)) return SP.fail("Enter valid mm dimensions.", "#drawer-x");
  } else if (kind === 'surface') {
      const wUnits = Number(document.getElementById('surface-x').value);
      const dUnits = Number(document.getElementById('surface-y').value);
      if (![wUnits, dUnits].every(v => Number.isFinite(v) && v > 0)) return SP.fail("Enter valid unit dimensions.", "#surface-x");
      x = wUnits * unit;
      y = dUnits * unit;
      const trimPreset = document.getElementById('surface-trim').value;
      z = trimPreset === 'small' ? 6.5 : (trimPreset === 'large' ? 10.0 : 7.5);
  } else if (kind === 'portable') {
      let rawX = Number(document.getElementById('portable-x').value);
      let rawY = Number(document.getElementById('portable-y').value);
      z = Number(document.getElementById('portable-z').value);
      if (![rawX, rawY, z].every(v => Number.isFinite(v) && v > 0)) return SP.fail("Enter valid mm dimensions.", "#portable-x");
      x = SP.snap(rawX);
      y = SP.snap(rawY);
  }

  // Folder last
  const folder = await SP.pickFolder();
  if (!folder) return;

  let info;
  if (state.runtime.hosted) {
    const inventoryText = await WFFileSystem.readText(folder.handle, SP.inventoryFilename()) || "";
    const result = await api("/api/space/create-text", {
      inventory_text: inventoryText, inventory_title: name,
      name, kind, x, y, z,
    });
    await WFFileSystem.writeText(folder.handle, SP.inventoryFilename(), result.inventory_text);
    const space = result.layout.space;
    await SP.writeMetadata(folder.handle, "space", space, true, {
      keep_bin_defaults: true,
      bin_defaults: null,
    });
    await WFFileSystem.save("active", { handle: folder.handle });
    info = {
      folder: folder.name, folder_name: folder.name, folder_mode: "space", space,
      inventory: true, keep_bin_defaults: true, bin_defaults: null,
    };
  } else {
    const data = await api("/api/space/create", {
      output: folder, name, kind, x, y, z, keep_bin_defaults: true,
    });
    SP.recent = data.recent || [];
    info = data.folder;
  }

  await SP.applyFolder(info);
  SP.close();
  
  if (kind === "portable") SP.designBox(info.space);
  else if (kind === "surface") SP.designSurface(info.space);
  else activatePreviewView("drawer");
};

SP.designSurface = space => {
  activatePreviewView("3d");
  state.design = clone(state.catalog.defaults.design);
  const { box, layout } = state.design;
  Object.assign(box, { x: space.x, y: space.y, z: space.z });
  box.base_trim = { enabled: true, trim_size: space.z === 6.5 ? 'small' : (space.z === 10.0 ? 'large' : 'medium') };
  state.design.part_name = space.name;
  syncForm();
  toast(`Designing Surface: ${space.name}`);
};

SP.openExisting = async () => {
    const folder = await SP.pickFolder();
    if (!folder) return;
    let data;
    if (state.runtime.hosted) {
        data = await SP.inspectHosted(folder);
    } else {
        const resp = await api("/api/space/inspect", { output: folder });
        data = resp.folder;
    }
    
    if (data.needs_setup) {
        SP.configureData = folder;
        SP.showOnly("space-configure-prompt");
        SP.showDialog();
    } else {
        await SP.afterPick(folder);
    }
};

SP.configureFolder = async () => {
    SP.showTypeCards();
};

SP.useUntypedFolder = async () => {
    if (state.runtime.hosted) {
        await SP.useHostedFolder(SP.configureData);
    } else {
        const data = await api("/api/space/use-untyped", { output: SP.configureData });
        SP.recent = data.recent || [];
        await SP.applyFolder(data.folder);
        SP.close();
    }
};



const startSpaces = () => {
  SP.wire();
  SP.launch();
};

if (state.ready) {
  startSpaces();
} else {
  window.addEventListener("wavefinity:ready", startSpaces, { once: true });
}


SP.wire = () => {
  document.querySelectorAll("#welcome-close, #welcome-resume-close, #space-unsupported-close, #space-form-close, #space-type-cards-close")
    .forEach(el => el?.addEventListener("click", SP.close));
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.close(); });
  SP.dialog().addEventListener("close", SP.cancelResumeAutoContinue);
  const welcomeCreate = document.getElementById("welcome-create");
  if (welcomeCreate) welcomeCreate.addEventListener("click", SP.showTypeCards);
  const welcomeOpen = document.getElementById("welcome-open");
  if (welcomeOpen) welcomeOpen.addEventListener("click", SP.openExisting);
  const welcomeResumeContinue = document.getElementById("welcome-resume-continue");
  if (welcomeResumeContinue) welcomeResumeContinue.addEventListener("click", SP.confirmResume);
  const welcomeResumeSwitch = document.getElementById("welcome-resume-switch");
  if (welcomeResumeSwitch) welcomeResumeSwitch.addEventListener("click", () => {
    SP.cancelResumeAutoContinue();
    SP.openExisting();
  });
  document.querySelectorAll(".type-card").forEach(el => {
      el.addEventListener("click", () => SP.showSetup(el.dataset.kind));
  });
  const untypedStart = document.getElementById("space-untyped-start");
  if (untypedStart) untypedStart.addEventListener("click", SP.startUntyped);
  const spaceBack = document.getElementById("space-back");
  if (spaceBack) spaceBack.addEventListener("click", SP.showTypeCards);
  const spaceForm = document.getElementById("space-form");
  if (spaceForm) spaceForm.addEventListener("submit", event => {
    event.preventDefault();
    SP.run(SP.create);
  });
  
  const confYes = document.getElementById("space-configure-yes");
  if (confYes) confYes.addEventListener("click", SP.configureFolder);
  const confNo = document.getElementById("space-configure-no");
  if (confNo) confNo.addEventListener("click", SP.useUntypedFolder);

  const welcomeRecent = document.getElementById("welcome-recent");
  if (welcomeRecent) welcomeRecent.addEventListener("click", event => {
    const forget = event.target.closest("[data-forget]");
    const open = event.target.closest("[data-index]");
    const one = SP.recent[Number(forget ? forget.dataset.forget : open?.dataset.index)];
    if (!one) return;
    if (forget) SP.run(async () => {
      SP.recent = (await api("/api/space/forget", { output: one.folder })).recent || [];
      SP.renderRecent();
    });
    else SP.run(() => SP.afterPick(one.folder));
  });
};
