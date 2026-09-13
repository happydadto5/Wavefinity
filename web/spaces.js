"use strict";

// A save folder is always available for normal design work. Space planning is
// an optional capability layered on that folder, never a design type.
const SP = { recent: [], setup: null, busy: false, resume: null };
const SP_KINDS = {
  drawer: { icon: "🗄️", label: "Drawer" },
  box: { icon: "📦", label: "Box" },
};
const FOLDER_METADATA = ".wavefinity.json";
const LEGACY_METADATA = ".wavefinity-space.json";
const FOLDER_METADATA_VERSION = 2;

const spSame = (a, b) => {
  const tidy = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
  return tidy(a) === tidy(b);
};

SP.dialog = () => $("#welcome-dialog");
SP.close = () => { if (SP.dialog().open) SP.dialog().close(); };
SP.showOnly = id => {
  ["welcome-home", "welcome-resume", "space-optional", "space-unsupported", "space-form"]
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
  setFolderState(info.folder_mode, info.space);
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
  if (!raw || !["drawer", "box"].includes(raw.kind)) return null;
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
  if (current.version !== FOLDER_METADATA_VERSION) return { status: "invalid" };
  if (current.folder_mode === "design") return { status: "design" };
  if (current.folder_mode === "space") {
    const space = SP.validSpace(current.space);
    return space ? { status: "space", space } : { status: "invalid-space" };
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

SP.writeMetadata = async (handle, mode, space = null) => {
  if (!handle) return;
  const metadata = { version: 2, folder_mode: mode };
  if (mode === "space" && space) metadata.space = space;
  await WFFileSystem.writeText(handle, FOLDER_METADATA, JSON.stringify(metadata, null, 2));
};

SP.inventoryRequest = async (path, extra = {}, { write = true } = {}) => {
  const folder = state.browserFolder;
  if (!folder?.handle) throw new Error("Space planning needs folder access so Wavefinity can keep its inventory with your designs.");
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
  if (inventoryText) {
    const data = await api("/api/drawer/load", {
      inventory_text: inventoryText,
      inventory_title: folder.name,
    });
    inventorySpace = SP.validSpace(data.layout?.space);
  }

  let mode;
  let space = null;
  let shouldWriteMetadata = false;
  if (inventorySpace) {
    mode = "space";
    space = inventorySpace;
    shouldWriteMetadata = ["missing", "design", "space"].includes(currentState.status);
  } else if (currentState.status === "space") {
    mode = "space";
    space = currentState.space;
  } else if (currentState.status === "design") {
    mode = "design";
  } else if (!["missing"].includes(currentState.status)) {
    throw SP.metadataError(currentState.status);
  } else if (legacyState.status === "space") {
    mode = "space";
    space = legacyState.space;
    shouldWriteMetadata = true;
  } else if (legacyState.status === "design") {
    mode = "design";
    shouldWriteMetadata = true;
  } else if (legacyState.status !== "missing") {
    throw SP.metadataError(legacyState.status);
  } else {
    mode = "design";
    shouldWriteMetadata = true;
  }

  if (mode === "space" && space && !inventorySpace) {
    const result = await api("/api/space/create-text", {
      inventory_text: inventoryText,
      inventory_title: space.name || folder.name,
      ...space,
    });
    await WFFileSystem.writeText(folder.handle, `${folder.name} bins.md`, result.inventory_text);
  }
  if (shouldWriteMetadata) await SP.writeMetadata(folder.handle, mode, space);
  return {
    folder: folder.name,
    folder_name: folder.name,
    folder_mode: mode,
    space,
    missing: false,
  };
};

SP.useHostedFolder = async folder => {
  const info = await SP.inspectHosted(folder);
  await SP.resetDrawer();
  state.browserFolder = folder;
  await WFFileSystem.save("active", { handle: folder.handle });
  await SP.applyFolder(info, { reset: false });
  SP.close();
  toast(info.folder_mode === "space"
    ? `Opened ${info.space.name || folder.name}.`
    : `Saving designs to ${folder.name}.`);
  return info;
};

// ------------------------------------------------------------ folder choice

SP.pickFolder = async () => {
  if (state.runtime.hosted) {
    if (!window.WFFileSystem?.supportsDirectoryPicker()) {
      const fallback = { handle: null, name: "Browser downloads", fallback: true };
      state.browserFolder = fallback;
      state.output = fallback.name;
      state.folderSelected = true;
      setFolderState("design");
      syncForm();
      toast("This browser will download files normally. Persistent Space planning needs folder access.");
      return fallback;
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

SP.continueSpaceSetup = info => {
  if (info?.folder_mode === "space") return SP.showResume(info);
  if (!SP.canPersistSpace()) return SP.showFolderAccessNeeded();
  SP.showSetup();
};

SP.chooseFolderThenSetup = () => SP.run(async () => {
  if (SP.hasFolder()) {
    if (state.folderMode === "space") return SP.open();
    return SP.continueSpaceSetup(null);
  }
  const folder = await SP.pickFolder();
  if (!folder) return;
  const info = await SP.afterPick(folder);
  SP.continueSpaceSetup(info);
});

SP.changeFolderThenSetup = () => SP.run(async () => {
  const folder = await SP.pickFolder();
  if (!folder) return;
  const info = await SP.afterPick(folder);
  SP.continueSpaceSetup(info);
});

// ------------------------------------------------------------ welcome/manage

SP.showHome = () => {
  SP.showOnly("welcome-home");
  SP.renderRecent();
  SP.showDialog();
};

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

SP.showSetup = () => {
  SP.showOnly("space-form");
  SP.setup = { folder: state.output, folder_name: state.browserFolder?.name || String(state.output).split(/[\\/]/).pop() };
  $("#space-folder").textContent = SP.setup.folder_name;
  $("#space-folder").title = state.output;
  $("#space-name").value = SP.setup.folder_name || "";
  $$('input[name="space-kind"]').forEach(radio => { radio.checked = radio.value === "drawer"; });
  ["x", "y", "z"].forEach(axis => { $("#space-" + axis).value = ""; });
  $("#space-error").hidden = true;
  SP.syncSetup();
  SP.showDialog();
  $("#space-name").focus();
  $("#space-name").select();
};

SP.syncSetup = () => {
  const kind = SP.kind();
  const labels = kind === "box"
    ? ["Inside width (X)", "Inside depth (Y)", "Inside height (Z)"]
    : ["Inside width (X)", "Inside depth (Y)", "Inside height (Z)"];
  ["#space-x-label", "#space-y-label", "#space-z-label"].forEach((sel, i) => { $(sel).textContent = labels[i]; });
  $("#space-create").textContent = kind === "box" ? "Create Space and design the box" : "Enable Space planning";
  SP.noteSize();
};

SP.noteSize = () => {
  const kind = SP.kind();
  const [x, y] = SP.readSize();
  let note = kind === "drawer"
    ? "Measure the inside dimensions of the drawer."
    : "These are the usable inside dimensions of the storage box.";
  if (kind === "box" && x > 0 && y > 0 && (SP.snap(x) !== x || SP.snap(y) !== y)) {
    note = `Box insides use ${state.catalog?.base_unit || 8} mm steps, so this becomes ${fmt(SP.snap(x))} × ${fmt(SP.snap(y))} mm.`;
  }
  $("#space-note").textContent = note;
};

SP.fail = (message, selector) => {
  $("#space-error").textContent = message;
  $("#space-error").hidden = false;
  $(selector)?.focus();
};

SP.create = async () => {
  const kind = SP.kind();
  const name = $("#space-name").value.trim();
  let [x, y, z] = SP.readSize();
  if (!name) return SP.fail("Give the Space a name.", "#space-name");
  if (![x, y, z].every(value => Number.isFinite(value) && value > 0)) return SP.fail("Enter the inside width, depth and height in mm.", "#space-x");
  if (kind === "box") [x, y] = [SP.snap(x), SP.snap(y)];

  let info;
  if (state.runtime.hosted) {
    const folder = state.browserFolder;
    const inventoryText = await WFFileSystem.readText(folder.handle, SP.inventoryFilename()) || "";
    const result = await api("/api/space/create-text", {
      inventory_text: inventoryText, inventory_title: name,
      name, kind, x, y, z,
    });
    await WFFileSystem.writeText(folder.handle, SP.inventoryFilename(), result.inventory_text);
    const space = result.layout.space;
    await SP.writeMetadata(folder.handle, "space", space);
    await WFFileSystem.save("active", { handle: folder.handle });
    info = { folder: folder.name, folder_name: folder.name, folder_mode: "space", space };
  } else {
    const data = await api("/api/space/create", { output: state.output, name, kind, x, y, z });
    SP.recent = data.recent || [];
    info = data.folder;
  }

  await SP.applyFolder(info);
  SP.close();
  if (kind === "box") SP.designBox(info.space);
  else {
    activatePreviewView("drawer");
    toast(`${name} is ready. New bins in this folder will be inventoried.`);
  }
};

SP.designBox = space => {
  activatePreviewView("3d");
  if (state.designMutationBusy) {
    toast(`${space.name} is ready. Choose Bin for Bins when you want to design its case.`, false, 7000);
    return;
  }
  if (designHasChanges() && !window.confirm(`Replace the current design with a Bin for Bins case for ${space.name}?`)) {
    toast(`${space.name} is ready. Choose Bin for Bins when you want to design its case.`, false, 7000);
    return;
  }
  const previous = clone(state.design);
  clearDraftSelection();
  state.design = clone(state.catalog.defaults.design);
  state.nestPhoto = null;
  state.drafts = {};
  const { box, layout } = state.design;
  Object.assign(box, { x: space.x, y: space.y, z: space.z });
  delete box.stack;
  box.b4b = { ...B4B_DEFAULTS, enabled: true };
  layout.features = [];
  layout.mode = "fused";
  state.design.part_name = space.name;
  syncForm();
  readB4BForm(state.design);
  enforceB4BMinimumHeight(state.design, false);
  applyB4BVisibility();
  changedDesign(previous);
  toast(`Designing the box for ${space.name}: ${SP.sizeText([space.x, space.y, space.z])} inside.`, false, 6000);
};

// ------------------------------------------------------------ startup/wiring

SP.launch = async () => {
  if (state.runtime.hosted) {
    try {
      const saved = await WFFileSystem.load("active");
      if (saved?.handle && await WFFileSystem.requestReadWritePermission(saved.handle)) {
        await SP.useHostedFolder({ handle: saved.handle, name: saved.handle.name });
        return;
      }
    } catch (_error) { /* The welcome screen offers a fresh folder choice. */ }
    SP.showHome();
    return;
  }

  if (!state.catalog?.preferences?.output) {
    SP.showHome();
    return;
  }
  try {
    const data = await api("/api/space/inspect", { output: state.output });
    SP.recent = data.recent || [];
    if (!data.folder?.missing) {
      await SP.applyFolder(data.folder);
      if (data.folder.folder_mode === "space") SP.showResume(data.folder);
      return;
    }
  } catch (error) { toast(error.message, true); }
  SP.showHome();
};

SP.wire = () => {
  $("#spaces-btn").addEventListener("click", SP.open);
  ["#welcome-close", "#welcome-resume-close", "#space-optional-not-now", "#space-unsupported-close"]
    .forEach(sel => $(sel)?.addEventListener("click", SP.close));
  SP.dialog().addEventListener("click", event => { if (event.target === SP.dialog()) SP.close(); });
  $("#welcome-new").addEventListener("click", SP.chooseFolder);
  $("#welcome-open").addEventListener("click", SP.chooseFolderThenSetup);
  $("#space-optional-setup").addEventListener("click", SP.showSetup);
  $("#welcome-resume-continue").addEventListener("click", () => {
    SP.close();
    activatePreviewView("drawer");
  });
  $("#welcome-resume-switch").addEventListener("click", SP.chooseFolder);
  $("#space-folder-change").addEventListener("click", SP.changeFolderThenSetup);
  $("#space-back").addEventListener("click", SP.offerSpacePlanning);
  $("#welcome-recent").addEventListener("click", event => {
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
  $$('input[name="space-kind"]').forEach(radio => radio.addEventListener("change", SP.syncSetup));
  ["#space-x", "#space-y"].forEach(sel => $(sel).addEventListener("input", SP.noteSize));
  $("#space-form").addEventListener("submit", event => {
    event.preventDefault();
    SP.run(SP.create);
  });
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
