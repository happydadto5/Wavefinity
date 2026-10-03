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
  portable: { icon: "images/space-icon-storage-box-64.png", label: "Storage Box" },
  surface: { icon: "images/space-icon-surface-64.png", label: "Surface" },
  drawer: { icon: "images/space-icon-drawer-64.png", label: "Drawer" },
  storage_drawers: { icon: "images/space-icon-storage-drawers-64.png", label: "Storage Drawers" },
  pegboard: { icon: "images/space-icon-pegboard-64.png", label: "Pegboard" },
  // Legacy kind, readable for migration only - never a current Space type;
  // it presents as a Storage Box, its recovery destination.
  box: { icon: "images/space-icon-storage-box-64.png", label: "Storage Box" },
};
SP.compactKindIcon = kind => {
  const row = SP_KINDS[kind] || SP_KINDS.drawer;
  return `<img class="space-kind-compact-icon" src="${escapeHtml(row.icon)}" alt="">`;
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
  SP.dialog().classList.remove("storage-drawers-config");
  if (SP.dialog().open) SP.dialog().close();
};
SP.showOnly = id => {
  SP.cancelInlineEdit();
  if (id !== "space-form") SP.dialog().classList.remove("storage-drawers-config");
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

SP.hasFolder = () => Boolean(state.folderSelected);
SP.canPersistSpace = () => !state.runtime.hosted || Boolean(state.browserFolder?.handle);
