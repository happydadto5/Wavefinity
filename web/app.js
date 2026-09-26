"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function flashField(input) {
  if (!input) return;
  input.classList.remove("field-flash");
  void input.offsetWidth; // restart the animation if it's already flashing
  input.classList.add("field-flash");
}

const state = {
  catalog: null,
  design: null,
  cleanDesign: null,
  preview: null,
  previewDesignKey: null,
  draftKind: "divider",
  draft: null,
  draftResolvedOptions: {},
  // Whether the current draft should save itself into the design as it's edited,
  // rather than staying a preview-only suggestion. True for anything the user
  // deliberately started (palette pick, Additional support, re-editing a placed
  // one); false for drafts the app puts up on its own (New/Open/after a delete/
  // mode switch) until the user actually touches a field.
  draftAutoCommit: false,
  // Whether the armed draft is a brand-new support (from the palette) that
  // should be appended on first commit, versus an edit of one already placed.
  // draftSourceIndex is that placed support's index, so an edit still commits
  // in place even if the canvas selection gets cleared underneath it.
  draftIsNew: false,
  draftSourceIndex: null,
  // Set the moment the user actually changes the open draft (a field edit, a
  // fit button, a quarter turn). Cleared when a draft is freshly loaded or
  // successfully saved. Lets a part switch tell "untouched suggestion, safe to
  // drop" apart from "real work that would be lost".
  draftTouched: false,
  selected: null,
  // True right after an explicit "Save Part" / "Delete Part": the user asked to
  // be back at the 10-part palette, so renderPlaced() must not helpfully re-open
  // a lone part for editing. Cleared the moment a part is picked or reopened.
  paletteBrowsing: false,
  edgeMountEditing: false,
  modifierEditing: null,
  // Which of the open draft's zone axes the user has set by hand. A pinned axis
  // is only ever grown to fit the part's contents, never shrunk back or
  // overwritten - a manual size always wins. Reset whenever a fresh draft loads.
  pinnedZone: {},
  // Session-only manual Base widths/lengths, keyed by placed-part index.
  partZoneLocks: {},
  // Fix 060 Correction 1: the last known Lid/Handle/Label field values for the
  // design currently open in the editor, kept while Stackable Bin hides
  // design.box.lid entirely so switching back to Handled/Stackable Lid
  // restores them. Reseeded from the design's own box.lid (or cleared)
  // whenever a different design is bound to the editor - see syncForm().
  lidMemory: null,
  // Set while a user-driven Width/Length edit waits for grow-only minimum
  // enforcement. Consumed by the debounced design update.
  binResizePending: false,
  // Only Width/Length edits set this; wall/base edits also use
  // binResizePending but do not change Side Opening wall eligibility.
  binFootprintResizePending: false,
  camera: { yaw: 45, elevation: 76, zoom: 1 },
  lastBoxSize: null,
  previewRequest: 0,
  draftRequest: 0,
  output: "",
  runtime: { hosted: false, filesystem: "server" },
  browserFolder: null,
  folderSelected: false,
  folderMode: "design",
  activeSpace: null,
  keepBinDefaults: false,
  spaceBinDefaults: null,
  spacePartDefaults: {},
  // The active typed Space's exact resume checkpoint (Fix 032) - the full
  // canonical design it should reopen to (recovery only, never an Inventory
  // identity). null/false outside a typed Space.
  spaceResumeDesign: null,
  spaceResumePending: false,
  // Fix 034 D: the current Designer's bound editable-source Inventory row in
  // the active Space, or null when the current design has no saved source
  // there yet. Cleared on New Bin/Duplicate/folder switch; set by autosave,
  // Inventory Edit and on-demand source attach from Save/Print.
  designInventoryId: null,
  spaceStarterPreviewPending: false,
  // Whether this folder logs generated bins/B4Bs to its inventory file - the
  // default for any folder, independent of whether Space planning is on.
  inventoryEnabled: true,
  keepLog: false,
  connector: {},
  lastOrdinaryDesign: null,
  layoutDrag: null,
  layoutTransform: null,
  // Interactive dimension-label handles, rebuilt every overlay render - not
  // part of any saved design. hitDimensionHandle() reads these to let a drag
  // on a Width/Depth/Height label resize the bin directly (see fix3d.md).
  previewDimensionHandles: [],
  layoutDimensionHandles: [],
  dimensionDrag: null,
  dimensionHover: null,
  dividerSegmentHits: [],
  dividerSegmentHover: null,
  dividerTopologyBusy: false,
  // The 2D layout normally uses the same heading as the 3D camera.  Users can
  // instead pin it to the conventional top-up plan view.
  layoutOrientation: "match3d",
  previewSupportPolygons: [],
  designMutationBusy: false,
  canGenerate: true,
  // Bin/Interior/Xray are independent on/off switches, not one exclusive
  // mode - each button flips only its own state (see setPreviewToggle()).
  binVisible: true,
  interiorVisible: true,
  xrayOn: false,
  // All/Base/Lid preview state for a Storage Box preview response. The Designer
  // only ever holds ordinary bins now, so this stays "all".
  b4bView: "all",
  history: [],
  future: [],
  serverInstance: null,
  apiCompat: null,
  kindRequest: 0,
  fitRequest: 0,
  // Rectified upload used only as an aligned tracing reference in the 2D view.
  // It deliberately stays out of saved design files.
  nestPhoto: null,
  // Scan-tuning session state, kept only in the browser - never saved into
  // the design. The original upload lets Scan controls and paper-
  // corner recovery work without asking the user to choose the file again.
  nestOriginalImage: null,   // { dataUrl, mimeType }
  nestRectifiedImage: null,  // { dataUrl, mimeType } - full rectified sheet, for retracing
  nestSensitivity: 50,
  nestCleanup: 50,
  nestPhotoOpacity: 45,
  nestCandidateContour: null,   // a not-yet-accepted retrace, drawn dashed - already
                                 // translated into the accepted outline's own stable frame
  nestCandidateCenterMm: null,  // that candidate's own trace_center_mm, pre-translation
  nestAcceptedCenterMm: null,   // the accepted outline's trace_center_mm, stable rectified-sheet frame
  nestTuneStatus: "",
  nestRetraceRequest: 0,
  nestTraceRequest: 0,
  nestTraceResult: null,        // a completed trace phase waiting on Tool thickness to finalize
  nestPaperCorners: null, // null = no recovery; []..4 = corners clicked in 2D recovery
  nestCornerError: "",
  nestCornerBusy: false,
  nestCornerTipDismissed: false,
  nestOutlineTool: "select",    // "select" | "add-point" | "delete-point"
  nestOutlineEditing: false,
  nestAccessWarningShown: null, // last access-planner warning already toasted
  nestViewZoom: 1,              // dedicated outline-editor viewport zoom (1 = fitted)
  nestViewPanX: 0,               // viewport pan, in canvas pixels, on top of the fit
  nestViewPanY: 0,
  nudgeFeedback: null,
};

let previewWaitTimer = null;
let previewSlowTimer = null;
let nestCornerPointer = null;
let nestCornerHoldTimer = null;

const VERSION_POLL_MS = 5000;

// `inventory` is the folder's real setting and should be passed explicitly by
// anything that knows it (a fresh /api/folder/use or SP.inspectHosted reply,
// or an explicit new folder that has never had a setting). Leaving it
// `undefined` - as a routine syncForm() refresh does - preserves whatever is
// already in state.inventoryEnabled instead of silently resetting it: the
// third argument is data about a folder, not a reset-to-default action.
// `resumeDesign`/`resumePending` follow the same "undefined preserves it"
// rule as `inventory` above: only SP.applyFolder() (which just read the
// folder's own metadata) supplies new values. A routine syncForm() refresh
// that re-passes its own current state.spaceResume* leaves them untouched.
function setFolderState(
  mode = "design",
  space = null,
  inventory = undefined,
  keepBinDefaults = undefined,
  binDefaults = undefined,
  partDefaults = undefined,
  resumeDesign = undefined,
  resumePending = undefined,
) {
  state.folderMode = mode === "space" ? "space" : "design";
  state.activeSpace = state.folderMode === "space" ? (space || null) : null;
  if (state.folderMode === "space") {
    state.keepBinDefaults = keepBinDefaults === undefined ? true : Boolean(keepBinDefaults);
    state.spaceBinDefaults = binDefaults && typeof binDefaults === "object" ? clone(binDefaults) : null;
    state.spacePartDefaults = partDefaults && typeof partDefaults === "object" ? clone(partDefaults) : {};
    if (resumeDesign !== undefined) {
      state.spaceResumeDesign = resumeDesign && typeof resumeDesign === "object" ? clone(resumeDesign) : null;
    }
    if (resumePending !== undefined) state.spaceResumePending = Boolean(resumePending);
    if (!state.spaceResumeDesign) state.spaceResumePending = false;
  } else {
    state.keepBinDefaults = false;
    state.spaceBinDefaults = null;
    state.spacePartDefaults = {};
    // No source row means anything outside a typed Space.
    state.designInventoryId = null;
    // No longer a typed Space: neither the Space workspace nor a stale
    // resume checkpoint from it has anything left to show.
    state.spaceResumeDesign = null;
    state.spaceResumePending = false;
    if (typeof DP !== "undefined" && DP.leave) DP.leave();
  }
  const resolvedInventory = inventory === undefined ? state.inventoryEnabled : Boolean(inventory);
  // Space always keeps inventory - it is what the layout is built from.
  state.inventoryEnabled = state.folderMode === "space" ? true : resolvedInventory;
  state.keepLog = state.inventoryEnabled;
  // A hosted session with no persistent folder has nowhere to keep an
  // inventory file, whatever the dropdown says.
  const canPersistInventory = !state.runtime.hosted || Boolean(state.browserFolder?.handle);
  const toggle = $("#folder-inventory-toggle");
  if (toggle) {
    toggle.value = state.inventoryEnabled ? "true" : "false";
    toggle.disabled = !state.folderSelected || state.folderMode === "space" || !canPersistInventory;
    toggle.title = !canPersistInventory
      ? "Inventory and Spaces need writable folder access in this browser. Downloads still work without it."
      : state.folderMode === "space"
        ? "A Space needs this folder's inventory turned on."
        : "Add each generated bin and Storage Box to this folder's inventory file";
  }
  applyDesignerLifecycleVisibility();
}

const COLORS = {
  outside: "#8ea8b2", inside: "#c9d9dc", rim: "#6f8f99", floor: "#b9a97e",
  label: "#315766", label_hole: "#e8efef", top_label_ledge: "#7799a3",
  lid: "#6c909b", lid_label: "#e8efef",
  scoop: "#a9bec3", insert_base: "#c5ab83", invalid: "#c95f58",
  cradle: "#e59f54", nest: "#df8d5b", bore: "#6fb98f", post: "#51a5a1",
  divider: "#9d86c8", pocket: "#d4778c", slot: "#8b78cf", steps: "#4b8eb9",
  edge_mount: "#c47b42",
  divider_slope: "#1f6b45",
  // Floor lettering keeps the colour the single floor label always had, so a
  // text interior part reads as writing rather than as another holder.
  text: "#315766",
  // B4B parts get their own colour family, distinct from interior features.
  b4b_body: "#8ea8b2", b4b_lid: "#6c909b", b4b_hinge: "#5f8794",
  b4b_latch: "#c98a4a", b4b_stack: "#9d86c8", b4b_label: "#315766",
  b4b_label_text: "#e8efef", b4b_handle: "#6b9aa7",
  base_trim: "#397f87",
};
const INSERT_TINT = "#c2a075";
const INSERT_TINT_MIX = .5;
// The support currently being edited, not yet added - shown live in the
// same bin view instead of its own isolated canvas, so it needs a colour
// that reads as "this one is different" against every kind's own muted
// palette above.
const DRAFT_HIGHLIGHT = "#1f6b45";
const AUTO_FOOTPRINT_KINDS = new Set(["cradle", "bore", "post", "slot"]);
const CAMERA_VIEWS = {
  top: { yaw: 45, elevation: 89, zoom: 1 },
  front: { yaw: 0, elevation: 8, zoom: 1 },
  side: { yaw: 90, elevation: 8, zoom: 1 },
  reset: { yaw: 45, elevation: 76, zoom: 1 },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function plainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

// ------------------------------------------------ Space preference memory (Fix 053)
//
// A typed Space remembers PREFERENCES (bin_defaults / part_defaults); each
// Inventory bin separately remembers its EXACT design in design_specs. The
// preference rule is exclusion-based: every user-configurable value is
// remembered unless it is identity/text content, feature/modifier presence, or
// placement/session/trace state - so a future option participates
// automatically. Preferences only ever seed a NEW bin or a newly added
// part/option; they never rewrite a bin that already exists.

function isSpaceTextKey(key) {
  return key === "text" || key === "label" || key === "division_labels" ||
    key === "photo" || key.endsWith("_text");
}

function blankSpaceTextFields(value) {
  const copy = clone(value);
  for (const key of Object.keys(copy)) {
    if (isSpaceTextKey(key)) copy[key] = Array.isArray(copy[key]) ? [] : "";
  }
  return copy;
}

function mergeDesignDefaults(current, remembered) {
  if (!plainObject(current) || !plainObject(remembered)) return clone(remembered);
  const merged = clone(current);
  for (const [key, value] of Object.entries(remembered)) {
    merged[key] = plainObject(value) && plainObject(merged[key])
      ? mergeDesignDefaults(merged[key], value)
      : clone(value);
  }
  return merged;
}

const SPACE_MODIFIER_BOX_KEYS = ["stack", "lid", "lift_grabbers", "edge_mount", "side_openings"];

// The bin-level preference snapshot: the whole design minus identity/text,
// modifier and feature presence, and per-object state. Idempotent, so it is
// also the sanitizer for older stored payloads.
function spaceBinDefaultsFromDesign(design) {
  if (!plainObject(design)) return null;
  const snapshot = clone(design);
  delete snapshot.version;
  delete snapshot.design_kind;
  delete snapshot.base_trim;
  delete snapshot.scoop;
  snapshot.part_name = "";
  snapshot.label = "";
  if (plainObject(snapshot.box)) {
    delete snapshot.box.b4b;
    for (const key of SPACE_MODIFIER_BOX_KEYS) delete snapshot.box[key];
    if (plainObject(snapshot.box.pegboard)) {
      const cleat = {};
      for (const key of ["cleat_x", "cleat_y"]) {
        if (snapshot.box.pegboard[key] !== undefined) cleat[key] = snapshot.box.pegboard[key];
      }
      snapshot.box.pegboard = cleat;
    }
  }
  snapshot.layout = plainObject(snapshot.layout) ? snapshot.layout : {};
  snapshot.layout.features = [];
  snapshot.layout.object_height_mm = null;
  return snapshot;
}

// What a brand-new bin is seeded from, or null when nothing is remembered.
function spaceBinPreferences() {
  if (state.folderMode !== "space" || !plainObject(state.spaceBinDefaults)) return null;
  const snapshot = spaceBinDefaultsFromDesign(state.spaceBinDefaults);
  if (!plainObject(snapshot?.box)) return null;
  delete snapshot.layout.features;
  delete snapshot.part_name;
  delete snapshot.label;
  if (state.activeSpace?.kind !== "pegboard") delete snapshot.box.pegboard;
  return snapshot;
}

// One interior-feature kind's reusable settings: logical size (never the
// absolute position), count, orientation and options - never literal text,
// photos or traced contours.
function partDefaultsFromFeature(feature) {
  if (!feature?.kind || !Array.isArray(feature.zone) || feature.zone.length !== 4) return null;
  const copy = {
    kind: feature.kind,
    options: clone(feature.options || {}),
    count: feature.count ?? null,
    along: feature.along || "x",
  };
  if (!feature.full_span) {
    copy.zone_size = [
      number(feature.zone[2]) - number(feature.zone[0]),
      number(feature.zone[3]) - number(feature.zone[1]),
    ];
  }
  if (typeof feature.wedge === "boolean") copy.wedge = feature.wedge;
  if (typeof feature.alternate_ends === "boolean") copy.alternate_ends = feature.alternate_ends;
  for (const key of Object.keys(copy.options)) {
    if (isSpaceTextKey(key)) delete copy.options[key];
  }
  if (feature.kind === "nest") {
    delete copy.count;
    delete copy.options.repeat_spacing_percent;
  }
  if (feature.kind === "bore") {
    // A sizing mode is remembered as the mode itself; the numbers it supersedes
    // are derived from each new bin, never carried over from the old one.
    if (copy.options.xy_size_mode && copy.options.xy_size_mode !== "manual") delete copy.zone_size;
    if (copy.options.height_size_mode === "bore_to_bin") delete copy.options.height;
  }
  if (!partInfo(feature.kind)?.flags?.photo && feature.item) copy.item = clone(feature.item);
  return cleanPartDefaultEntry(copy);
}

// Reduces any stored per-feature entry (including older shapes that may carry
// text, features or modifier presence) to the known safe fields.
function cleanPartDefaultEntry(entry) {
  if (!plainObject(entry) || typeof entry.kind !== "string" || BOX_MODIFIER_KINDS.has(entry.kind)) return null;
  const clean = { kind: entry.kind };
  if (Array.isArray(entry.zone_size) && entry.zone_size.length === 2 &&
      entry.zone_size.every(one => Number.isFinite(Number(one)) && Number(one) > 0)) {
    clean.zone_size = entry.zone_size.map(Number);
  }
  clean.options = plainObject(entry.options) ? clone(entry.options) : {};
  for (const key of Object.keys(clean.options)) {
    if (isSpaceTextKey(key)) delete clean.options[key];
  }
  if (Object.hasOwn(entry, "count")) clean.count = entry.count;
  if (typeof entry.along === "string") clean.along = entry.along;
  if (typeof entry.wedge === "boolean") clean.wedge = entry.wedge;
  if (typeof entry.alternate_ends === "boolean") clean.alternate_ends = entry.alternate_ends;
  // Item measurements/profile/clearance are reusable; a user's item name is
  // identity and never carries into another bin.
  if (plainObject(entry.item)) clean.item = { ...clone(entry.item), name: "Custom item" };
  return clean;
}

// The remembered entry for a feature kind comes from the instance whose
// settings actually changed between the design a save replaced and the one it
// stored, not merely the last feature of that kind. Instances are matched by
// their reusable settings (position is not one), so reordering or moving
// features invents nothing and deleting one changes nothing. When several
// instances are new or changed, the last of them wins.
function changedPartDefault(design, previous, kind) {
  const unmatched = new Map();
  for (const one of previous?.layout?.features || []) {
    if (one.kind !== kind) continue;
    const key = JSON.stringify(partDefaultsFromFeature(one));
    unmatched.set(key, (unmatched.get(key) || 0) + 1);
  }
  let changed = null;
  for (const one of design.layout?.features || []) {
    if (one.kind !== kind) continue;
    const entry = partDefaultsFromFeature(one);
    if (!entry) continue;
    const key = JSON.stringify(entry);
    const left = unmatched.get(key) || 0;
    if (left > 0) unmatched.set(key, left - 1);
    else changed = entry;
  }
  return changed;
}

function seedFeatureFromPartDefaults(feature, entry) {
  const remembered = cleanPartDefaultEntry(entry);
  if (!feature || !remembered || remembered.kind !== feature.kind) return feature;
  const seeded = clone(feature);
  if (remembered.zone_size) {
    const cx = (number(seeded.zone[0]) + number(seeded.zone[2])) / 2;
    const cy = (number(seeded.zone[1]) + number(seeded.zone[3])) / 2;
    const width = Math.max(0.1, remembered.zone_size[0]);
    const depth = Math.max(0.1, remembered.zone_size[1]);
    seeded.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
  }
  seeded.options = { ...(seeded.options || {}), ...remembered.options };
  if (seeded.kind === "bore") {
    if (seeded.options.height_size_mode === "bore_to_bin") delete seeded.options.height;
  }
  if (Object.hasOwn(remembered, "count") && seeded.kind !== "nest") seeded.count = remembered.count;
  if (remembered.along) seeded.along = remembered.along;
  if (typeof remembered.wedge === "boolean") seeded.wedge = remembered.wedge;
  if (typeof remembered.alternate_ends === "boolean") seeded.alternate_ends = remembered.alternate_ends;
  if (remembered.item && !partInfo(feature.kind)?.flags?.photo) seeded.item = clone(remembered.item);
  delete seeded.contour;
  delete seeded.source_contour;
  return seeded;
}

// A box modifier's reusable settings, or null when there is nothing to keep.
// Which sub-parts are switched on (Label / Screw mounting, enabled) is
// composition, not a preference, so those flags are dropped; text is blanked.
function cleanModifierSettings(kind, settings) {
  if (!plainObject(settings)) return null;
  if (kind === "lid_stacking") {
    const lid = plainObject(settings.lid) && settings.lid.enabled ? blankSpaceTextFields(settings.lid) : null;
    const direct = plainObject(settings.stack) && settings.stack.mode === "direct";
    if (!lid && !direct) return null;
    return { lid, stack: direct ? { mode: "direct" } : null };
  }
  const one = blankSpaceTextFields(settings);
  delete one.enabled;
  if (kind === "edge_mount") {
    delete one.label_enabled;
    delete one.holes_enabled;
  }
  return one;
}

function modifierSettingsFromDesign(kind, design) {
  const box = design?.box;
  if (!plainObject(box)) return null;
  if (kind === "lid_stacking") return cleanModifierSettings(kind, { lid: box.lid, stack: box.stack });
  const source = { edge_mount: box.edge_mount, inside_handles: box.lift_grabbers, side_openings: box.side_openings }[kind];
  return cleanModifierSettings(kind, source);
}

// Remembered settings for a modifier the user is adding: this Space's stored
// per-kind entry, falling back to an older bin_defaults snapshot's modifier
// block (its enabled state is ignored - only its reusable settings seed).
function spaceModifierDefaults(kind) {
  if (state.folderMode !== "space") return null;
  const entry = state.spacePartDefaults?.[kind];
  if (plainObject(entry) && entry.kind === kind) {
    const settings = cleanModifierSettings(kind, entry.settings);
    if (settings) return settings;
  }
  return modifierSettingsFromDesign(kind, state.spaceBinDefaults);
}

function cleanedSpacePartDefaults(raw) {
  const clean = {};
  if (!plainObject(raw)) return clean;
  for (const [kind, entry] of Object.entries(raw)) {
    if (BOX_MODIFIER_KINDS.has(kind)) {
      const settings = plainObject(entry) ? cleanModifierSettings(kind, entry.settings) : null;
      if (settings) clean[kind] = { kind, settings };
    } else {
      const one = cleanPartDefaultEntry(entry);
      if (one) clean[kind] = one;
    }
  }
  return clean;
}

// Called once an exact bin save has succeeded, with that save's canonical
// design. `previous` is the design that save replaced: only a feature/modifier
// kind whose settings actually changed replaces its remembered entry, so
// reopening an old bin and renaming it never overwrites newer preferences.
function rememberSpacePreferences(design, previous) {
  if (state.folderMode !== "space" || typeof SP === "undefined" ||
      !plainObject(design) || isStructuralDesign(design)) return;
  const currentParts = plainObject(state.spacePartDefaults) ? state.spacePartDefaults : {};
  const parts = cleanedSpacePartDefaults(currentParts);
  let partsChanged = JSON.stringify(parts) !== JSON.stringify(currentParts);
  for (const kind of new Set((design.layout?.features || []).map(one => one.kind))) {
    const entry = changedPartDefault(design, previous, kind);
    if (!entry) continue;
    parts[kind] = entry;
    partsChanged = true;
  }
  for (const kind of BOX_MODIFIER_KINDS) {
    if (!modifierIsActive(kind, design)) continue;
    const settings = modifierSettingsFromDesign(kind, design);
    if (!settings) continue;
    const before = modifierIsActive(kind, previous) ? modifierSettingsFromDesign(kind, previous) : null;
    if (JSON.stringify(settings) === JSON.stringify(before)) continue;
    parts[kind] = { kind, settings };
    partsChanged = true;
  }
  const binDefaults = spaceBinDefaultsFromDesign(design);
  const binChanged = JSON.stringify(binDefaults) !== JSON.stringify(state.spaceBinDefaults);
  if (!binChanged && !partsChanged) return;
  const changes = {};
  if (binChanged) {
    state.spaceBinDefaults = binDefaults;
    changes.bin_defaults = binDefaults;
  }
  if (partsChanged) {
    state.spacePartDefaults = parts;
    changes.part_defaults = parts;
  }
  SP.queueDefaults(changes);
}

function drawerHardClearance() {
  return number(state.catalog?.drawer_rules?.hard_wall_clearance_mm, 0);
}

function drawerSpaceCapacity(mm) {
  const unit = number(state.catalog?.base_unit, 8);
  const clearance = drawerHardClearance();
  return Math.max(
    0,
    Math.floor((number(mm, 0) - clearance) / unit + 1e-9),
  );
}

function ordinaryBinMinimumHeight() {
  return number(
    state.catalog?.drawer_rules?.ordinary_bin_min_height_mm,
    Math.ceil(
      number(state.catalog?.base_rules?.default_mm, 0.6)
      + number(state.catalog?.min_height_above_base_mm, 5),
    ),
  );
}

// `remembered` is this Space's bin-preference snapshot (see
// spaceBinPreferences). Its X/Y/Z seed the bin, then the Space's own capacity
// and height rules clamp them - a remembered value that no longer fits is
// normalized, never turned into an invalid bin. With nothing remembered the
// product starter sizing applies unchanged.
function applySpaceSizingDefaults(design, remembered = null) {
  if (state.folderMode !== "space" || !state.activeSpace) return design;

  const kind = state.activeSpace.kind;
  const space = state.activeSpace;
  const unit = state.catalog?.base_unit || 8;
  const rememberedBox = plainObject(remembered?.box) ? remembered.box : {};
  const rememberedLayout = plainObject(remembered?.layout) ? remembered.layout : {};
  const largestUnits = Math.floor((state.catalog?.max_box_size || 350) / unit);
  const rememberedUnits = (axis, capacity) => {
    const value = Number(rememberedBox[axis]);
    if (!Number.isFinite(value) || value <= 0) return null;
    return Math.min(largestUnits, Math.max(1, capacity), Math.max(1, Math.round(value / unit)));
  };
  const rememberedZ = Number(rememberedBox.z);
  const haveRememberedZ = Number.isFinite(rememberedZ) && rememberedZ > 0;

  const spaceXUnits = kind === "drawer" ? drawerSpaceCapacity(space.x) : Math.floor(space.x / unit);
  const spaceYUnits = kind === "drawer" ? drawerSpaceCapacity(space.y) : Math.floor(space.y / unit);
  const startX = Math.min(4, Math.max(1, spaceXUnits));
  const startY = Math.min(4, Math.max(1, spaceYUnits));

  design.box.x = (rememberedUnits("x", spaceXUnits) ?? startX) * unit;
  design.box.y = (rememberedUnits("y", spaceYUnits) ?? startY) * unit;

  if (kind === "drawer") {
    design.box.z = Math.min(
      space.z,
      haveRememberedZ
        ? normalizeBinDimension("z", rememberedZ, rememberedZ)
        : normalizeBinDimension("z", space.z - 3, space.z - 3),
    );
  } else if (kind === "surface") {
    const trimHeight = surfaceTrimHeight(space.trim_size);
    if (Number.isFinite(trimHeight)) {
      const minimumAbove = number(state.catalog?.min_height_above_base_mm, 5);
      const rememberedBase = Number(rememberedBox.base_thickness);
      const customBase = rememberedLayout.surface_base_mode === "custom" &&
        Number.isFinite(rememberedBase) && rememberedBase > 0;
      const base = customBase ? rememberedBase : trimHeight;
      design.layout.surface_base_mode = customBase ? "custom" : "edge";
      design.layout.surface_lightweight_base = typeof rememberedLayout.surface_lightweight_base === "boolean"
        ? rememberedLayout.surface_lightweight_base : true;
      design.layout.object_height_mm = null;
      design.box.standard_base = false;
      design.box.base_thickness = base;
      design.box.z = Math.max(
        base + minimumAbove,
        haveRememberedZ ? Math.round(rememberedZ * 10) / 10 : 0,
      );
    }
  } else if (kind === "portable" || kind === "box") {
    design.box.z = normalizeBinDimension(
      "z", haveRememberedZ ? Math.min(space.z, rememberedZ) : space.z,
    );
  } else if (kind === "pegboard") {
    if (haveRememberedZ) design.box.z = normalizeBinDimension("z", rememberedZ, rememberedZ);
    if (space.pegboard_standard === "standard") design.box.z = Math.max(48, design.box.z);
    else {
      design.box.x = Math.max(56, design.box.x);
      design.box.z = Math.max(40, design.box.z);
    }
    design.box.pegboard = {
      enabled: true,
      standard: space.pegboard_standard,
      cleat_x: design.box.pegboard?.cleat_x || "auto",
      cleat_y: design.box.pegboard?.cleat_y || "auto",
    };
  }
  if (kind !== "surface") {
    design.layout.surface_base_mode = "custom";
    design.layout.surface_lightweight_base = false;
    design.layout.object_height_mm = null;
  }
  
  return design;
}

// New Bin (Fix 053): the catalog starter, plus this Space's remembered bin
// preferences, then the active Space's own constraints. It never copies the
// last bin's parts, modifiers, names or text - Duplicate is the only
// clone-the-last-design workflow.
function freshDesignForCurrentFolder() {
  const starter = clone(state.catalog.defaults.design);
  const remembered = spaceBinPreferences();
  if (!remembered) return applySpaceSizingDefaults(starter);
  return applySpaceSizingDefaults(mergeDesignDefaults(starter, remembered), remembered);
}

async function loadFreshOrdinaryDesignForCurrentFolder(overrideBox = null) {
  const design = freshDesignForCurrentFolder();
  if (overrideBox) Object.assign(design.box, overrideBox);
  state.design = design;
  state.designInventoryId = null;
  state.lastOrdinaryDesign = clone(state.design);
  resetNestPhotoSession();
  state.cleanDesign = clone(state.design);
  state.spaceStarterPreviewPending = state.folderMode === "space";
  // Showing a fresh starter does not create an Inventory row.
  state.drafts = {};
  state.history = [];
  state.future = [];
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  bindLidMemoryForDesign();
  syncForm();
  clearDraftSelection();
  activatePreviewView("3d");
  await refreshPreview();
}

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

// A Storage Box or Base Trim is a structural output of its Space (see
// SP.saveStructural in spaces.js), never a Designer object: the Designer
// only opens and edits ordinary Bins.
function isStructuralDesign(design) {
  return Boolean(design) && (design.design_kind === "base_trim" || Boolean(design.box?.b4b?.enabled));
}

let spaceAutosaveTimer = null;
let spaceAutosaveChain = Promise.resolve();

// Rows whose saved files went stale during editing. A row is queued once at
// the generated -> In Space transition; the focus-exit gate resolves it.
//
// Row IDs such as "B1" only mean something inside one Space, so every entry
// carries the identity of the Space that produced it (folder + Space ID, taken
// from the validated save context). An entry is only ever resolved, prompted,
// or regenerated while that same Space is active. An entry waits if its Space
// is left while the question is open.
const staleFileRefreshQueue = new Map();
let staleFileRefreshGate = null;

const staleFileRefreshKey = entry => JSON.stringify([entry.output, entry.spaceId, entry.rowId]);
const staleFileRefreshEntryCurrent = entry =>
  typeof DL !== "undefined" && entry.output === DL.folder() && entry.spaceId === (state.activeSpaceId || null);

function queueStaleFileRefresh(context, rowId, wasPrinted = false) {
  const entry = { output: context.output, spaceId: context.spaceId, rowId, wasPrinted };
  staleFileRefreshQueue.set(staleFileRefreshKey(entry), entry);
}

function discardStaleFileRefreshRows(ids) {
  const removed = new Set(ids);
  for (const [key, entry] of staleFileRefreshQueue) if (removed.has(entry.rowId) && staleFileRefreshEntryCurrent(entry)) staleFileRefreshQueue.delete(key);
}

// Called only at a focus exit, after the design-source autosave has settled.
function settleStaleFileRefresh({ materialize = false } = {}) {
  if (staleFileRefreshGate) return staleFileRefreshGate;
  const run = async () => {
    if (state.runtime.hosted || !state.designInventoryId) return true;
    const context = DL.spaceContext();
    const entry = [...staleFileRefreshQueue.values()].find(one =>
      staleFileRefreshEntryCurrent(one) && one.rowId === state.designInventoryId);
    if (!entry) return true;
    const key = staleFileRefreshKey(entry);
    const row = DL.bin(entry.rowId);
    if (!row || String(row.file || "").trim()) { staleFileRefreshQueue.delete(key); return true; }
    if (!entry.approved && DL.layout?.settings?.auto_update_changed_files !== true) {
      const choice = await appConfirm({
        title: "Update saved files?",
        message: `${DL.label(row)} ${entry.wasPrinted ? "was saved and printed" : "has saved files"}. Update the saved files to match your changes?`,
        primaryLabel: "Update saved files", cancelLabel: "Not now",
        checkboxLabel: "Automatically update saved files after future edits",
      });
      if (!DL.spaceContextCurrent(context)) return false;
      if (choice !== "primary") { staleFileRefreshQueue.delete(key); return !materialize; }
      if (appConfirm.checked) {
        DL.change(() => { DL.layout.settings.auto_update_changed_files = true; }, { history: false });
        if (!(await DL.save()) || !DL.spaceContextCurrent(context)) return false;
      }
    }
    if (materialize) { entry.approved = true; return true; }
    try {
      if (!(await designerGenerateInventoryRow(entry.rowId, context, { skipFlush: true }))) return false;
      if (!DL.spaceContextCurrent(context)) return false;
      staleFileRefreshQueue.delete(key);
      return true;
    } catch (error) {
      if (!DL.isStaleSpaceError(error)) toast(`Could not update saved files: ${error.message}`, true, 6000);
      return false;
    }
  };
  staleFileRefreshGate = run().finally(() => { staleFileRefreshGate = null; });
  return staleFileRefreshGate;
}

function queueSpaceDesignAutosave() {
  if (!typedSpaceOrdinaryBin()) return;
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
    const wasPrinted = DL.bin(rowId)?.status === "printed";
    const data = await DL.inventoryCall("/api/drawer/design-source/save", {
      design, row_id: rowId || undefined,
    }, { context });
    DL.requireSpaceContext(context);
    // The exact bin is now durable in design_specs. Space preferences follow
    // from that canonical design; a failure here never rolls the bin back.
    try {
      rememberSpacePreferences(data.design, previousClean);
    } catch (error) {
      toast(`This bin was saved, but the Space's remembered settings were not: ${error.message}`, true, 6000);
    }
    if (data.files_became_stale && !state.runtime.hosted) queueStaleFileRefresh(context, data.row_id, wasPrinted);
    if (state.designInventoryId !== rowId) {
      return true;
    }
    state.designInventoryId = data.row_id;
    DL.adopt(data);
    DL.emit();
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

async function flushSpaceDesignAutosave({ visible = true, materialize = false } = {}) {
  if (!typedSpaceOrdinaryBin()) return true;
  clearTimeout(spaceAutosaveTimer);
  spaceAutosaveTimer = null;
  if (visible && !(await flushVisibleDesignEditsBeforeModeSwitch())) return false;
  if (visible && !(await maybePromptSurfaceObjectHeight())) return false;
  if (!beginDesignMutation()) return false;
  let saved = false;
  try {
    await refreshPreview();
    if (!state.preview?.fits || state.preview.feature_errors?.length || state.preview.draft_error ||
        state.previewDesignKey !== JSON.stringify(state.design))
      throw new Error("Resolve the design issue before leaving this bin.");
    await persistSpaceDesignSource(null, materialize);
    await SP.flushDefaults();
    saved = true;
  } catch (error) {
    toast(`Could not autosave this bin: ${error.message}`, true, 6000);
    return false;
  } finally {
    finishDesignMutation();
  }
  return saved && await settleStaleFileRefresh({ materialize });
}

// Install a canonical design (from Inventory Edit or Duplicate) as the working Designer
// design, replacing whatever is currently shown.
async function installLoadedDesignSource(rowId, spec, {
  successMessage = "Loaded from Space.",
} = {}) {
  if (!beginDesignMutation()) return false;
  try {
    const result = await api("/api/design/validate", { design: spec });
    state.design = result.design;
    state.lastOrdinaryDesign = clone(state.design);
    resetNestPhotoSession();
    state.cleanDesign = clone(spec);
    state.spaceStarterPreviewPending = false;
    state.designInventoryId = rowId;
    state.surfaceHeightPromptSkipped = false;
    state.drafts = {};
    state.history = [];
    state.future = [];
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    activatePreviewView("3d");
    await refreshPreview();
    if (rowId === null && typedSpaceOrdinaryBin()) await persistSpaceDesignSource(null, true);
    toast(successMessage);
    return true;
  } catch (error) {
    toast(`Could not load that design: ${error.message}`, true, 6000);
    return false;
  } finally {
    finishDesignMutation();
  }
}

async function designerEditInventoryRow(rowId) {
  if (state.folderMode !== "space" || typeof DL === "undefined") return false;
  const one = DL.bin(rowId);
  const spec = DL.layout?.design_specs?.[rowId];
  if (!one || !["bin", "b4b"].includes(one.kind) || !spec) return false;
  if (isStructuralDesign(spec)) {
    toast("A Storage Box or Base Trim is saved from its Space, not designed here.", true, 6000);
    return false;
  }
  return designerInstallInventorySpec(rowId, spec);
}

async function designerInstallInventorySpec(rowId, spec) {
  if (!spec) return false;
  if (state.designInventoryId === rowId) {
    activatePreviewView("3d");
    return true;
  }
  if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave())) return false;
  return installLoadedDesignSource(rowId, spec);
}

// Regenerate a saved source without replacing the live Designer edit.
// ``expected`` (an automatic refresh) binds the whole run to the Space that
// asked for it: it is checked before and after every await, so a Space switch
// can never send this row ID to another Space.
async function designerGenerateInventoryRow(rowId, expected = null, { skipFlush = false } = {}) {
  if (state.folderMode !== "space" || typeof DL === "undefined") return;
  const bound = () => !expected || DL.spaceContextCurrent(expected);
  if (!bound()) return;
  if (!skipFlush && (DL.busy || isGenerating || state.designMutationBusy)) {
    toast("Finish the current action before saving files.", true);
    return;
  }
  if (!skipFlush && typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave({ materialize: true }))) return false;
  if (!bound()) return;
  const one = DL.bin(rowId);
  const spec = DL.layout?.design_specs?.[rowId];
  if (!one || !["bin", "b4b"].includes(one.kind) || !spec) return false;
  const generateRow = async context => {
    if (expected && !DL.spaceContextCurrent(expected)) return;
    const result = await api("/api/generate", {
      design: clone(spec), output: state.output, connector: state.connector,
      keep_log: false,
    });
    try {
      DL.requireSpaceContext(context);
    } catch (error) {
      if (!DL.isStaleSpaceError(error)) throw error;
      toast("Generation finished for the Space you left. No files were saved to the current Space and its Inventory was not changed.");
      return;
    }
    const savedFiles = await saveGeneratedFiles(result);
    try {
      DL.requireSpaceContext(context);
    } catch (error) {
      if (!DL.isStaleSpaceError(error)) throw error;
      toast("Files were generated in the Space you left, but its Inventory row was not updated.");
      return;
    }
    const files = [...new Set(savedFiles.map(path => String(path).split(/[\\/]/).pop())
      .filter(name => /\.3mf$/i.test(name)))];
    if (!files.length) throw new Error("The generated design files were not returned.");
    const file = files.join(", ");
    const saved = await DL.inventoryCall("/api/drawer/design-source/status", {
      row_id: rowId, action: "saved", file, design: clone(spec),
    }, { context });
    DL.adopt(saved);
    DL.emit();
    toast(`Generated ${file}.`);
    return true;
  };
  return skipFlush ? generateRow(expected) : DL.busyWith("generate-row", generateRow);
}

// New Bin (B1): a fresh product-appropriate starter. Meaningful current work
// in a typed Space is preserved through the autosave flush first, never silently
// discarded; on flush failure New Bin is cancelled rather than losing work.
async function designerNewBin() {
  if (!(await guardDraftSwitch())) return;
  if (state.folderMode === "space") {
    if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave())) return;
  } else if (designHasChanges() && !(await appConfirmAction({
    title: "Start a new bin?",
    message: "Start a new bin and discard the current changes?",
    actionLabel: "Discard Changes",
    danger: true,
  }))) return;
  if (!beginDesignMutation()) return;
  try {
    state.designInventoryId = null;
    state.surfaceHeightPromptSkipped = false;
    await loadFreshOrdinaryDesignForCurrentFolder();
    toast("Started a new bin.");
  } finally {
    finishDesignMutation();
  }
}

// Fix 064: the largest whole base-unit X/Y footprint that fits inside a
// Storage Box's usable interior (rounding down, since the bin must fit),
// plus the full legal usable Z. Z is validated against `candidateDesign` -
// the fresh inside-bin starter that will actually be installed - not
// whatever bin happens to be open, since its remembered Base thickness can
// differ (Fix 064 Correction 1). Returns { x, y, z } or { error }; never
// throws, so the caller can show an actionable message and leave the
// current design untouched.
function insideBinFitForStorageBox(space, candidateDesign) {
  const unit = state.catalog.base_unit;
  const maxUnits = Math.floor((state.catalog.max_box_size || 350) / unit);
  const xUnits = Math.min(maxUnits, Math.floor(space.x / unit));
  const yUnits = Math.min(maxUnits, Math.floor(space.y / unit));
  if (xUnits < 1 || yUnits < 1) {
    return { error: "This Storage Box's inside is too small to fit a bin." };
  }
  const z = normalizeBinDimension("z", space.z, space.z, candidateDesign);
  if (z > space.z) {
    return { error: "This Storage Box is too short to fit a legal bin." };
  }
  return { x: xUnits * unit, y: yUnits * unit, z };
}

// Make Inside Bin (Fix 064): a Storage-Box-only Space Action. Starts a fresh
// ordinary bin, exactly like New Bin (same safety/reset primitives, same
// remembered reusable Space preferences, no clone of the current bin's
// name/text/features), but with X/Y/Z forced to fit the Storage Box's usable
// interior instead of the normal New Bin starter size. The fit is validated
// against the fresh starter itself (Fix 064 Correction 1) - there is no
// await between building it and installing it, so it stays the same
// candidate the user sees land.
async function designerMakeInsideBin() {
  if (!(await guardDraftSwitch())) return;
  if (!(await flushSpaceDesignAutosave())) return;
  const candidate = freshDesignForCurrentFolder();
  const fit = insideBinFitForStorageBox(state.activeSpace, candidate);
  if (fit.error) {
    toast(fit.error, true, 6000);
    return;
  }
  if (!beginDesignMutation()) return;
  try {
    state.designInventoryId = null;
    state.surfaceHeightPromptSkipped = false;
    await loadFreshOrdinaryDesignForCurrentFolder({ x: fit.x, y: fit.y, z: fit.z });
    toast("Started an inside bin.");
  } finally {
    finishDesignMutation();
  }
}

// Duplicate (B2): a deep copy of the exact current design with name/label
// text cleared and source-row identity cleared, so a later Save/Generate/
// Print creates a distinct source rather than mutating the original's row.
async function designerDuplicate() {
  if (!(await guardDraftSwitch())) return;
  if (typedSpaceOrdinaryBin()) {
    if (!(await flushSpaceDesignAutosave())) return;
    if (!state.designInventoryId) {
      toast("Edit this bin before duplicating it.", true);
      return;
    }
    const context = DL.spaceContext();
    try {
      const data = await DL.inventoryCall("/api/drawer/design-source/duplicate", {
        row_id: state.designInventoryId,
      }, { context });
      DL.adopt(data);
      DL.emit();
      await installLoadedDesignSource(data.row_id, data.design, { successMessage: "Duplicated bin." });
    } catch (error) {
      toast(`Could not duplicate bin: ${error.message}`, true, 6000);
    }
    return;
  }
  const design = clone(visibleDesignSnapshot());
  if (design.layout) design.layout.object_height_mm = null;
  design.part_name = "";
  design.label = "";
  if (design.box?.edge_mount) design.box.edge_mount.label_text = "";
  if (design.box?.lid) {
    design.box.lid.label_text = "";
    design.box.lid.division_labels = (design.box.lid.division_labels || []).map(() => "");
  }
  if (design.box?.b4b) design.box.b4b.label_text = "";
  if (Array.isArray(design.layout?.features)) {
    design.layout.features = design.layout.features.map(feature => {
      if (feature.kind !== "divider" || !Array.isArray(feature.options?.division_labels)) return feature;
      return {
        ...feature,
        options: { ...feature.options, division_labels: feature.options.division_labels.map(() => "") },
      };
    });
  }
  if (!beginDesignMutation()) return;
  try {
    const result = await api("/api/design/validate", { design });
    state.design = result.design;
    state.lastOrdinaryDesign = clone(state.design);
    state.cleanDesign = clone(state.design);
    state.designInventoryId = null;
    state.surfaceHeightPromptSkipped = false;
    state.drafts = {};
    state.history = [];
    state.future = [];
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    activatePreviewView("3d");
    await refreshPreview();
    toast("Duplicated. Edit the copy freely - the original is unchanged.");
  } catch (error) {
    toast(error.message, true, 6000);
  } finally {
    finishDesignMutation();
  }
}

function pinDraftAxis(axis) {
  state.pinnedZone[axis] = true;
}

function recordHistory(before) {
  if (!before || JSON.stringify(before) === JSON.stringify(state.design)) return;
  state.spaceStarterPreviewPending = false;
  state.history.push(clone(before));
  if (state.history.length > 50) state.history.shift();
  state.future = [];
  updateHistoryButtons();
  // Accepted paths refresh the preview, or the next boundary flushes them.
}

function updateHistoryButtons() {
  const undo = $("#undo-design");
  const redo = $("#redo-design");
  if (undo) undo.disabled = state.designMutationBusy || !state.history.length;
  if (redo) redo.disabled = state.designMutationBusy || !state.future.length;
}

function updateGenerateAvailability() {
  const binButton = $("#generate-bin");
  if (binButton) {
    binButton.disabled = state.designMutationBusy || !state.canGenerate;
    binButton.title = state.canGenerate ? "Save the current bin files" : "Resolve the highlighted issue before saving";
  }
  const allButton = $("#generate-all");
  if (allButton) {
    allButton.disabled = state.designMutationBusy || !state.canGenerate;
    allButton.title = state.canGenerate ? "Save bin and connector files" : "Resolve the highlighted issue before saving";
  }
  const connectorButton = $("#generate-connector");
  if (connectorButton) {
    connectorButton.disabled = state.designMutationBusy;
  }
  syncConnectorActionLabels();
  updatePrimaryPrintButtonLabel();
  for (const printButton of [$("#print-with-connectors"), $("#print-without-connectors")]) {
    if (!printButton) continue;
    printButton.disabled = state.designMutationBusy || !state.canGenerate;
    if (!state.canGenerate) printButton.title = "Resolve the highlighted issue before printing";
  }
}

async function restoreHistory(redo = false) {
  if (!(redo ? state.future : state.history).length) return;
  if (!beginDesignMutation()) return;
  try {
    // Fold any values still visible only in controls/the live part draft into
    // history first. Undo then removes that newest edit; a new edit correctly
    // invalidates Redo instead of applying an obsolete future state.
    await commitVisibleDraft();
    const from = redo ? state.future : state.history;
    const to = redo ? state.history : state.future;
    if (!from.length) return;
    to.push(clone(state.design));
    state.design = from.pop();
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    updateHistoryButtons();
    await refreshPreview();
    if (typedSpaceOrdinaryBin()) queueSpaceDesignAutosave();
  } finally {
    finishDesignMutation();
  }
}

function number(value, fallback = 0) {
  if (typeof value === "number") return Number.isFinite(value) ? value : fallback;
  const parsed = Number(value);
  if (Number.isFinite(parsed)) return parsed;
  const match = String(value ?? "").match(/^\s*([+-]?\d+(?:\.\d+)?)/);
  if (match) {
    const num = Number(match[1]);
    if (Number.isFinite(num)) return num;
  }
  return fallback;
}

function fmt(value) {
  const rounded = Math.round(number(value) * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : String(rounded);
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function debounce(fn, delay) {
  let timer = null;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
  wrapped.cancel = () => {
    clearTimeout(timer);
    timer = null;
  };
  return wrapped;
}

async function api(path, payload = null) {
  const options = payload === null ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch (_error) {
    throw new Error(`The local Wavefinity service returned ${response.status}.`);
  }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}

let toastTimer;
function toast(message, error = false, hold = 3200, style = "") {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
  node.classList.toggle("prominent", style === "prominent");
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => node.classList.remove("show"), hold);
}

function setError(message = "", actions = []) {
  const panel = $("#error-panel");
  panel.replaceChildren();
  if (actions.length) {
    actions.forEach(action => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "error-link";
      button.textContent = action.message;
      button.addEventListener("click", action.activate);
      panel.append(button);
    });
  } else if (message) {
    panel.textContent = message;
  }
  panel.hidden = !message && !actions.length;
}

function partInfo(kind = state.draftKind) {
  return state.catalog.parts.find(part => part.kind === kind);
}

function editingEdgeMount() {
  return state.modifierEditing === "edge_mount";
}

const BOX_MODIFIER_KINDS = new Set([
  "lid_stacking", "inside_handles", "side_openings", "edge_mount",
]);

function modifierIsActive(kind, design = state.design) {
  const box = design?.box || {};
  if (kind === "lid_stacking") {
    return Boolean(box.lid?.enabled || (box.stack?.mode && box.stack.mode !== "none"));
  }
  if (kind === "inside_handles") return Boolean(box.lift_grabbers?.enabled);
  if (kind === "side_openings") return Boolean(box.side_openings?.enabled);
  if (kind === "edge_mount") {
    return Boolean(box.edge_mount?.label_enabled || box.edge_mount?.holes_enabled);
  }
  return false;
}

function partInstanceCount(kind, design = state.design) {
  if (BOX_MODIFIER_KINDS.has(kind)) return modifierIsActive(kind, design) ? 1 : 0;
  return (design?.layout?.features || []).filter(one => one.kind === kind).length;
}

function partAtLimit(info, design = state.design) {
  const max = info?.max_instances;
  return Number.isInteger(max) && partInstanceCount(info.kind, design) >= max;
}

function edgeMountActive(design = state.design) {
  const one = design?.box?.edge_mount;
  return Boolean(one?.label_enabled || one?.holes_enabled);
}

function edgeMountAvailable(design = state.design) {
  return !baseTrimEnabled(design) && !Boolean(design?.box?.b4b?.enabled);
}

function placedPartCount() {
  return (state.design?.layout?.features?.length || 0) +
    [...BOX_MODIFIER_KINDS].filter(kind => modifierIsActive(kind)).length;
}

function iconFor(kind) {
  const common = 'viewBox="2 2 28 28" aria-hidden="true"';
  const iconId = partInfo(kind)?.icon || kind;
  const paths = window.WavefinityFeatureIcons || {};
  return `<svg ${common}>${paths[iconId] || paths.pocket || ""}</svg>`;
}

function renderCatalog() {
  const modes = $("#mode-select");
  modes.innerHTML = state.catalog.modes.map(mode => `
    <option value="${escapeHtml(mode.value)}">${escapeHtml(mode.label)}</option>
  `).join("");
  modes.addEventListener("change", async () => {
      if (modes.value === state.design.layout.mode) return;
      if (modes.value === "separate" && insideHandlesActive()) {
        modes.value = state.design.layout.mode;
        toast(INSIDE_HANDLES_REMOVABLE_MESSAGE, true, 6500);
        return;
      }
      if (!beginDesignMutation()) {
        syncForm();
        return;
      }
      const oldMode = state.design.layout.mode;
      try {
        // Preserve the exact visible edit before converting the saved layout.
        // A debounced draft must not disappear just because the user switches
        // print mode quickly after changing a field.
        await commitVisibleDraft();
        const previousDesign = clone(state.design);
        const previousSelected = state.selected;
        const result = await api("/api/layout/mode", { design: state.design, mode: modes.value });
        state.design = result.design;
        recordHistory(previousDesign);
        syncForm();
        // A support that was already saved keeps being edited, just in its
        // converted form - only fall back to a fresh, not-yet-saved
        // suggestion when nothing was actually selected before the switch.
        if (previousSelected !== null && previousSelected < state.design.layout.features.length) {
          // The visible draft was already folded in by commitVisibleDraft above
          // and the layout has just been reconverted - reselect straight through.
          selectedFeature(previousSelected, true);
        } else {
          clearDraftSelection();
        }
        refreshPreview();
      } catch (error) {
        modes.value = oldMode;
        toast(error.message, true);
      } finally {
        finishDesignMutation();
      }
  });

  const palette = $("#support-palette");
  palette.innerHTML = state.catalog.parts
    .filter(part => part.palette_visible !== false)
    .map(part => `
    <button class="support-choice" data-kind="${part.kind}" aria-label="${escapeHtml(part.title)}: ${escapeHtml(part.description)}" title="${escapeHtml(part.title)} — ${escapeHtml(part.description)}">
      <span class="support-choice-icon">
        ${iconFor(part.kind)}
      </span>
      <span class="support-choice-copy">
        <strong>${escapeHtml(part.title)}</strong>
        <span class="support-choice-desc">${escapeHtml(part.description)}</span>
        <span class="support-choice-state" hidden></span>
      </span>
    </button>
  `).join("");
  $$(".support-choice", palette).forEach(button => {
    button.style.setProperty("--support-color", kindColor(button.dataset.kind));
    button.addEventListener("click", () => pickKind(button.dataset.kind));
  });
}

function ensureRimFeatureInLayout() {
  if (!state.design) return;
  const tidy = (state.design.label || "").trim();
  const hasRimFeature = state.design.layout?.features?.some(f => f.kind === "text" && f.options?.level === "rim");
  if (tidy && !hasRimFeature) {
    state.design.layout.features = [
      ...state.design.layout.features,
      {
        kind: "text",
        zone: [-16, -4, 16, 4],
        options: {
          text: tidy,
          level: "rim",
          rim_side: ["front", "back", "left", "right"].includes(state.design.label_position)
            ? state.design.label_position : "back",
        },
        along: "x",
        item: null,
        count: null,
      },
    ];
  }
}

function syncRimLabelFromFeatures() {
  if (!state.design) return;
  let rimText = "";
  let rimSide = "back";
  if (state.draft?.kind === "text" && state.draft.options?.level === "rim") {
    rimText = String(state.draft.options?.text ?? "").trim();
    rimSide = state.draft.options?.rim_side || "back";
  } else {
    const rimFeature = state.design.layout?.features?.find(f => f.kind === "text" && f.options?.level === "rim");
    if (rimFeature) {
      rimText = String(rimFeature.options?.text ?? "").trim();
      rimSide = rimFeature.options?.rim_side || "back";
    }
  }
  state.design.label = rimText;
  state.design.label_position = rimText ? rimSide : "bottom";
  if (rimText) seedPartNameFromLabel(rimText);
}

function populateLiftGrabberChoices() {
  const rules = state.catalog?.lift_grabbers || {};
  const sizeSelect = $("#lift-grabber-size");
  const locationSelect = $("#lift-grabber-location");
  if (sizeSelect && !sizeSelect.options.length) {
    for (const choice of rules.sizes || []) {
      const opt = document.createElement("option");
      opt.value = choice.value;
      opt.textContent = choice.label;
      sizeSelect.appendChild(opt);
    }
  }
  if (locationSelect && !locationSelect.options.length) {
    for (const choice of rules.locations || []) {
      const opt = document.createElement("option");
      opt.value = choice.value;
      opt.textContent = choice.label;
      locationSelect.appendChild(opt);
    }
  }
}

function syncLiftGrabberControls() {
  const enabled = $("#lift-grabber-size")?.value !== "no";
  if ($("#lift-grabber-location-setting")) $("#lift-grabber-location-setting").hidden = !enabled;
}

function populateEdgeMountChoices() {
  const rules = state.catalog?.edge_mount || {};
  const projectionSelect = $("#edge-mount-label-projection");
  if (projectionSelect && !projectionSelect.options.length) {
    for (const choice of rules.projection_choices || []) {
      projectionSelect.add(new Option(choice.label, choice.value));
    }
    projectionSelect.add(new Option("Custom", "custom"));
  }
}

// Fix 058 Correction 1, C1.4B/G: the Label selector (None / Separate Part /
// Integrated) is UI-only - it is derived from the existing label_enabled/
// label_type fields, never persisted as its own key.
function edgeMountLabelMode(edgeMount) {
  if (!edgeMount?.label_enabled) return "none";
  return edgeMount.label_type === "integrated" ? "integrated" : "separate";
}

// Mirrors readLiftGrabberForm/readStackForm: only resets an *existing* key to
// defaults when both subsections are off, so a design that never touched
// Edge Mount keeps no key at all and design_to_dict omits the block while
// disabled. Both subsections' fields are always preserved together so
// toggling one off never erases the other's settings.
function readEdgeMountForm(design) {
  design.box = design.box || {};
  const labelMode = $("#edge-mount-label-mode")?.value || "none";
  const labelEnabled = labelMode !== "none";
  const holesEnabled = Boolean($("#edge-mount-holes-enabled")?.checked);
  if (!labelEnabled && !holesEnabled) {
    if (design.box.edge_mount) design.box.edge_mount = { ...EDGE_MOUNT_DEFAULTS };
    return;
  }
  const current = { ...EDGE_MOUNT_DEFAULTS, ...(design.box.edge_mount || {}) };
  // Label=None preserves the previously chosen label_type (Separate/
  // Integrated) rather than resetting it, just like the former enable
  // checkbox left it untouched - re-enabling later restores the same choice.
  const labelType = labelMode === "none" ? current.label_type : labelMode;
  const projection = number(
    $("#edge-mount-label-projection-mm")?.value, current.label_projection_mm,
  );
  const thicknessInput = $("#edge-mount-label-thickness-mm");
  const thicknessRaw = thicknessInput?.value ?? "";
  const thicknessWasEdited = thicknessRaw !== (thicknessInput?.dataset.storedValue ?? thicknessRaw);
  let thickness = current.label_thickness_mm;
  if (thicknessWasEdited) {
    const clamped = Math.min(4, Math.max(0.8, number(thicknessRaw, current.label_thickness_mm)));
    thickness = Math.round((clamped + Number.EPSILON) * 10) / 10;
    if (thicknessInput && thicknessRaw !== "") {
      thicknessInput.value = fmt(thickness);
      // The design now owns this value; without this, typing the original
      // number back would look "unedited" and silently keep the new one.
      thicknessInput.dataset.storedValue = thicknessInput.value;
    }
  }
  const spacingMode = $("#edge-mount-spacing-mode")?.value || "auto";
  const ribCountMode = $("#edge-mount-standoff-rib-count-mode")?.value || "auto";
  // Fix 058 Correction 1, C1.4C: a Separate Part label is always Inlaid /
  // Flush - Raised text is not a valid manufacturing state for it, so the
  // Label style control is hidden entirely and label_raised is forced false
  // whenever Separate Part is selected. Label=None preserves whatever the
  // Style control last held, same as every other detail field.
  const labelRaised = labelType === "separate"
    ? false
    : labelMode === "none" ? current.label_raised : $("#edge-mount-label-style")?.value === "raised";
  design.box.edge_mount = {
    side: $("#edge-mount-side")?.value || "front",
    label_enabled: labelEnabled,
    label_text: $("#edge-mount-label-text")?.value || "",
    label_type: labelType,
    label_projection_mm: projection,
    label_length_mode: $("#edge-mount-label-length-mode")?.value || "full",
    label_thickness_mm: thickness,
    label_raised: labelRaised,
    label_text_depth_mm: number($("#edge-mount-label-depth")?.value, current.label_text_depth_mm),
    label_flip: Boolean($("#edge-mount-label-flip")?.checked),
    standoff_ribs_enabled: Boolean($("#edge-mount-standoff-ribs-enabled")?.checked),
    standoff_rib_count: ribCountMode === "manual"
      ? number($("#edge-mount-standoff-rib-count")?.value, current.standoff_rib_count || 1)
      : null,
    holes_enabled: holesEnabled,
    hole_count: number($("#edge-mount-hole-count")?.value, current.hole_count),
    hole_orientation: $("#edge-mount-hole-orientation")?.value || "horizontal",
    screw_diameter_mm: number($("#edge-mount-screw-diameter")?.value, current.screw_diameter_mm),
    access_diameter_mm: number(
      $("#edge-mount-access-diameter")?.value,
      resolvedEdgeMountAccessDiameter(current),
    ),
    top_offset_mm: number($("#edge-mount-top-offset")?.value, current.top_offset_mm),
    hole_spacing_mm: spacingMode === "custom"
      ? number($("#edge-mount-spacing-mm")?.value, current.hole_spacing_mm || EDGE_MOUNT_DEFAULTS.top_offset_mm)
      : null,
  };
}

// Python remains authoritative for real validation/geometry; this is only
// for the immediate "Auto: X mm" readout while typing.
function resolvedEdgeMountAccessDiameter(edgeMount) {
  if (edgeMount.access_diameter_mm !== null && edgeMount.access_diameter_mm !== undefined) {
    return number(edgeMount.access_diameter_mm, 8);
  }
  return Math.max(8, number(edgeMount.screw_diameter_mm, 4) * 2);
}

function syncEdgeMountControls() {
  const edgeMount = { ...EDGE_MOUNT_DEFAULTS, ...(state.design?.box?.edge_mount || {}) };
  if ($("#edge-mount-side")) $("#edge-mount-side").value = edgeMount.side;
  if ($("#edge-mount-label-mode")) $("#edge-mount-label-mode").value = edgeMountLabelMode(edgeMount);
  if ($("#edge-mount-holes-enabled")) $("#edge-mount-holes-enabled").checked = edgeMount.holes_enabled;
  if ($("#edge-mount-label-text")) $("#edge-mount-label-text").value = edgeMount.label_text;
  if ($("#edge-mount-label-length-mode")) $("#edge-mount-label-length-mode").value = edgeMount.label_length_mode;
  if ($("#edge-mount-label-style")) $("#edge-mount-label-style").value = edgeMount.label_raised ? "raised" : "flush";
  if ($("#edge-mount-label-depth")) $("#edge-mount-label-depth").value = fmt(edgeMount.label_text_depth_mm);
  if ($("#edge-mount-label-flip")) $("#edge-mount-label-flip").checked = edgeMount.label_flip;
  if ($("#edge-mount-standoff-ribs-enabled")) {
    $("#edge-mount-standoff-ribs-enabled").checked = edgeMount.standoff_ribs_enabled;
  }
  const ribCountMode = edgeMount.standoff_rib_count === null || edgeMount.standoff_rib_count === undefined
    ? "auto" : "manual";
  if ($("#edge-mount-standoff-rib-count-mode")) $("#edge-mount-standoff-rib-count-mode").value = ribCountMode;
  if ($("#edge-mount-standoff-rib-count")) {
    $("#edge-mount-standoff-rib-count").value = String(edgeMount.standoff_rib_count || 1);
  }
  if ($("#edge-mount-standoff-rib-count-row")) {
    $("#edge-mount-standoff-rib-count-row").hidden = ribCountMode !== "manual";
  }
  if ($("#edge-mount-hole-count")) $("#edge-mount-hole-count").value = String(edgeMount.hole_count);
  if ($("#edge-mount-hole-orientation")) $("#edge-mount-hole-orientation").value = edgeMount.hole_orientation;
  if ($("#edge-mount-screw-diameter")) $("#edge-mount-screw-diameter").value = fmt(edgeMount.screw_diameter_mm);
  if ($("#edge-mount-top-offset")) $("#edge-mount-top-offset").value = fmt(edgeMount.top_offset_mm);
  if ($("#edge-mount-label-projection-mm")) {
    $("#edge-mount-label-projection-mm").value = fmt(edgeMount.label_projection_mm);
  }

  const thicknessInput = $("#edge-mount-label-thickness-mm");
  if (thicknessInput) {
    thicknessInput.value = fmt(edgeMount.label_thickness_mm);
    thicknessInput.dataset.storedValue = thicknessInput.value;
  }
  const accessSelect = $("#edge-mount-access-diameter");
  if (accessSelect) {
    $("option[data-legacy]", accessSelect)?.remove();
    const access = resolvedEdgeMountAccessDiameter(edgeMount);
    const standard = [6, 8, 10].some(value => Math.abs(value - access) < 1e-9);
    if (!standard) {
      const option = new Option(`Existing — ${fmt(access)} mm`, fmt(access));
      option.dataset.legacy = "true";
      accessSelect.appendChild(option);
    }
    accessSelect.value = fmt(access);
  }
  const spacingMode = edgeMount.hole_spacing_mm === null || edgeMount.hole_spacing_mm === undefined ? "auto" : "custom";
  if ($("#edge-mount-spacing-mode")) $("#edge-mount-spacing-mode").value = spacingMode;
  if ($("#edge-mount-spacing-custom-row")) $("#edge-mount-spacing-custom-row").hidden = spacingMode !== "custom";
  if (spacingMode === "custom" && $("#edge-mount-spacing-mm")) {
    $("#edge-mount-spacing-mm").value = fmt(edgeMount.hole_spacing_mm);
  }

  // Fix 058 Correction 1, C1.4: the Label and Screw Mounting cards are
  // always visible; only their detail groups hide/show, driven by the Label
  // selector and the Screw Mounting checkbox respectively.
  const labelMode = edgeMountLabelMode(edgeMount);
  if ($("#edge-mount-label-details")) $("#edge-mount-label-details").hidden = labelMode === "none";
  if ($("#edge-mount-holes-details")) $("#edge-mount-holes-details").hidden = !edgeMount.holes_enabled;
  if ($("#edge-mount-label-style-row")) $("#edge-mount-label-style-row").hidden = labelMode !== "integrated";
  if ($("#edge-mount-standoff-rib-controls")) {
    $("#edge-mount-standoff-rib-controls").hidden = labelMode !== "separate";
  }
  if ($("#edge-mount-integrated-support-warning")) {
    $("#edge-mount-integrated-support-warning").hidden = labelMode !== "integrated";
  }
  if ($("#edge-mount-hole-orientation-row")) $("#edge-mount-hole-orientation-row").hidden = number(edgeMount.hole_count) <= 1;
}

function syncEdgeMountEditorVisibility() {
  const scratch = { box: { edge_mount: { ...EDGE_MOUNT_DEFAULTS, ...(state.design?.box?.edge_mount || {}) } } };
  readEdgeMountForm(scratch);
  const labelMode = $("#edge-mount-label-mode")?.value || "none";
  $("#edge-mount-label-details").hidden = labelMode === "none";
  $("#edge-mount-holes-details").hidden = !$("#edge-mount-holes-enabled").checked;
  if ($("#edge-mount-label-style-row")) $("#edge-mount-label-style-row").hidden = labelMode !== "integrated";
  $("#edge-mount-standoff-rib-controls").hidden = labelMode !== "separate";
  if ($("#edge-mount-integrated-support-warning")) {
    $("#edge-mount-integrated-support-warning").hidden = labelMode !== "integrated";
  }
  $("#edge-mount-standoff-rib-count-row").hidden = $("#edge-mount-standoff-rib-count-mode").value !== "manual";
  $("#edge-mount-spacing-custom-row").hidden = $("#edge-mount-spacing-mode").value !== "custom";
  $("#edge-mount-hole-orientation-row").hidden = number($("#edge-mount-hole-count").value) <= 1;
  const access = $("#edge-mount-access-diameter");
  if (access) {
    const tooSmall = number(access.value) < number($("#edge-mount-screw-diameter")?.value);
    access.setCustomValidity(tooSmall ? "Screwdriver access must be at least the screw diameter." : "");
  }
}

// Fix 034 H inset_v2 semantics: 0 means the opening reaches that edge
// (floor for bottom, rim for top); a higher percentage pulls it inward.
const SIDE_OPENING_DEFAULTS = {
  enabled: false, shape: "curved", sides: [], size: "medium",
  from_bottom_percent: 0, from_top_percent: 0,
};
const SIDE_OPENING_SIDE_IDS = ["front", "back", "left", "right"];
let sideOpeningAdjustmentNote = "";

function sideOpeningState(design = state.design) {
  return { ...SIDE_OPENING_DEFAULTS, ...(design?.box?.side_openings || {}) };
}

function sideOpeningPartActive(design = state.design) {
  return Boolean(design?.box?.side_openings?.enabled);
}

const MODIFIER_SIDE_TO_WALL = {
  front: "-y",
  back: "+y",
  left: "-x",
  right: "+x",
};

const MODIFIER_OPPOSITE_SIDE = {
  front: "back",
  back: "front",
  left: "right",
  right: "left",
};

const MODIFIER_SIDE_LABEL = {
  front: "Front",
  back: "Back",
  left: "Left",
  right: "Right",
};

function insideGripWalls(box) {
  const grip = box?.lift_grabbers;
  if (!grip?.enabled) return new Set();
  if (grip.location === "sides") return new Set(["-x", "+x"]);
  if (grip.location === "front_back") return new Set(["-y", "+y"]);
  if (grip.location === "both") return new Set(["-x", "+x", "-y", "+y"]);
  return new Set();
}

function rimLabelSideForDesign(design) {
  if (!String(design?.label || "").trim()) return null;
  const side = design?.label_position;
  if (side === "top") return "back";
  return SIDE_OPENING_SIDE_IDS.includes(side) ? side : null;
}

function modifierConflicts(design) {
  const conflicts = [];
  const box = design?.box || {};
  const sideOpenings = sideOpeningState(design);
  const openSides = sideOpenings.enabled
    ? new Set(sideOpenings.sides || [])
    : new Set();
  const gripWalls = insideGripWalls(box);

  for (const side of SIDE_OPENING_SIDE_IDS) {
    if (!openSides.has(side)) continue;
    if (gripWalls.has(MODIFIER_SIDE_TO_WALL[side])) {
      conflicts.push({
        key: `side-opening:inside-grip:${side}`,
        message:
          `The ${MODIFIER_SIDE_LABEL[side]} wall already has a Side Opening. ` +
          "Move the Inside Grip to a different wall or remove that Side Opening.",
      });
    }
  }

  const edgeMount = box.edge_mount || {};
  if ((edgeMount.label_enabled || edgeMount.holes_enabled) &&
      openSides.has(edgeMount.side)) {
    conflicts.push({
      key: `side-opening:edge-mount:${edgeMount.side}`,
      message:
        `The ${MODIFIER_SIDE_LABEL[edgeMount.side]} wall already has a Side Opening. ` +
        "Choose another Edge Mount wall or remove that Side Opening.",
    });
  }

  const rimSide = rimLabelSideForDesign(design);
  if (rimSide && openSides.has(rimSide)) {
    conflicts.push({
      key: `side-opening:rim-label:${rimSide}`,
      message:
        `The ${MODIFIER_SIDE_LABEL[rimSide]} wall already has a Side Opening. ` +
        "Put the rim label on another wall or remove that Side Opening.",
    });
  }

  if (edgeMount.label_enabled && edgeMount.label_type === "separate") {
    const edgeSide = SIDE_OPENING_SIDE_IDS.includes(edgeMount.side)
      ? edgeMount.side
      : "front";
    if (rimSide && rimSide === edgeSide) {
      conflicts.push({
        key: `edge-mount-separate:rim-label:${edgeSide}`,
        message:
          `A Separate Edge Mount label and rim label cannot use the same ${MODIFIER_SIDE_LABEL[edgeSide]} wall. ` +
          "Move the rim label, choose another Edge Mount wall, or use Integrated.",
      });
    }
    if (box.lid?.enabled || box.stack?.mode === "lid") {
      conflicts.push({
        key: "edge-mount-separate:lid",
        message:
          "A Separate Edge Mount label cannot be used with a lid. " +
          "Use Integrated or remove the lid.",
      });
    }
  }

  if (edgeMount.holes_enabled) {
    const side = SIDE_OPENING_SIDE_IDS.includes(edgeMount.side)
      ? edgeMount.side
      : "front";
    const opposite = MODIFIER_OPPOSITE_SIDE[side];
    const mountWall = MODIFIER_SIDE_TO_WALL[side];
    const accessWall = MODIFIER_SIDE_TO_WALL[opposite];
    if (gripWalls.has(mountWall) || gripWalls.has(accessWall)) {
      conflicts.push({
        key: `edge-mount-holes:inside-grip:${side}`,
        message:
          `Edge Mount screw access needs both the ${MODIFIER_SIDE_LABEL[side]} wall ` +
          `and opposite ${MODIFIER_SIDE_LABEL[opposite]} wall clear of Inside Grips. ` +
          "Move the Inside Grip, choose another Edge Mount wall, or turn off Screw Mounting.",
      });
    }
  }

  if (design?.scoop && gripWalls.has("-y")) {
    const usableHeight = number(box.z) - number(box.base_thickness);
    const scoopTop = number(box.base_thickness)
      + usableHeight * number(state.catalog?.scoop_rules?.height_fraction, 0.6);
    const selectedSize = box.lift_grabbers?.size || "medium";
    const sizeRule = (state.catalog?.lift_grabbers?.sizes || [])
      .find(one => one.value === selectedSize);
    const grabberHeight = Number(sizeRule?.height_mm);
    const rimClearance = Number(state.catalog?.lift_grabbers?.rim_clearance_mm);
    if (Number.isFinite(grabberHeight) && Number.isFinite(rimClearance)) {
      const grabberBottom = number(box.z) - rimClearance - grabberHeight;
      if (scoopTop > grabberBottom) {
        conflicts.push({
          key: "scoop:inside-grip:front",
          message:
            "The front scoop rises into the front Inside Grip. Use side-only Inside Grip, " +
            "choose a smaller grip that clears, make the bin taller, or turn off the scoop.",
        });
      }
    }
  }

  return conflicts;
}

function newModifierConflict(previousDesign, nextDesign) {
  const previousKeys = new Set(
    modifierConflicts(previousDesign).map(conflict => conflict.key)
  );
  return modifierConflicts(nextDesign)
    .find(conflict => !previousKeys.has(conflict.key)) || null;
}

function rejectModifierConflict(previousDesign, previousCanGenerate, conflict) {
  state.design = previousDesign;
  state.canGenerate = previousCanGenerate;
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  sideOpeningAdjustmentNote = "";
  syncForm();
  updateGenerateAvailability();
  toast(conflict.message, true, 6000);
}

function applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate) {
  updateDesignFromForm();
  const conflict = newModifierConflict(previousDesign, state.design);
  if (!conflict) return true;
  rejectModifierConflict(previousDesign, previousCanGenerate, conflict);
  return false;
}

function applyPendingLiveFormWithModifierConflictGuard() {
  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  return applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate);
}

// Wall span a Side Opening's width is measured against - Front/Back run
// along X, Left/Right run along Y. Mirrors organizer_side_openings.
// side_opening_side_span() so the UI can filter eligibility client-side.
function sideOpeningSideSpan(side, design = state.design) {
  const box = design?.box || {};
  return side === "front" || side === "back" ? number(box.x) : number(box.y);
}

function sideOpeningEligibleSide(side, design = state.design) {
  const rules = state.catalog?.side_openings || {};
  const minSide = number(rules.min_side_mm, 16);
  if (sideOpeningSideSpan(side, design) < minSide - 1e-9) return false;

  const box = design?.box || {};
  if (insideGripWalls(box).has(MODIFIER_SIDE_TO_WALL[side])) return false;

  if ((box.edge_mount?.label_enabled || box.edge_mount?.holes_enabled) &&
      box.edge_mount.side === side) return false;

  if (rimLabelSideForDesign(design) === side) return false;

  return true;
}

// BEGIN SIDE_OPENING_SELECTION_HELPER
function reconcileSideOpeningSelection(selectedSides, eligibleSides) {
  const eligible = new Set(eligibleSides);
  const sides = selectedSides.filter(side => eligible.has(side));
  const removed = selectedSides.filter(side => !eligible.has(side));
  let replacement = null;
  if (!sides.length && eligibleSides.length) {
    replacement = eligibleSides[0];
    sides.push(replacement);
  }
  return { sides, removed, replacement };
}
// END SIDE_OPENING_SELECTION_HELPER

function reconcileSideOpeningsAfterResize(design) {
  sideOpeningAdjustmentNote = "";
  const current = sideOpeningState(design);
  if (!current.enabled) return;

  const eligibleSides = SIDE_OPENING_SIDE_IDS.filter(side => sideOpeningEligibleSide(side, design));
  const result = reconcileSideOpeningSelection(current.sides || [], eligibleSides);
  if (!result.sides.length) {
    design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }

  design.box.side_openings = { ...current, enabled: true, sides: result.sides };
  const allowed = sideOpeningAllowedSizes(design);
  if (allowed.length && !allowed.includes(design.box.side_openings.size)) {
    design.box.side_openings.size = allowed[allowed.length - 1];
  }

  if (result.removed.length) {
    const removed = result.removed.map(side => side[0].toUpperCase() + side.slice(1)).join(" and ");
    const replacement = result.replacement
      ? ` ${result.replacement[0].toUpperCase() + result.replacement.slice(1)} was selected instead.`
      : "";
    const verb = result.removed.length === 1 ? "was" : "were";
    const wall = result.removed.length === 1 ? "that wall is" : "those walls are";
    sideOpeningAdjustmentNote = `${removed} ${verb} turned off because ${wall} now shorter than 2 units (16 mm).${replacement}`;
  }
}

// Python remains authoritative for real validation/geometry; this mirrors
// organizer_side_openings._vertical_fits() only for the immediate size-list
// filtering while typing.
function sideOpeningVerticalFits(design, spec, widthMm) {
  const box = design?.box || {};
  const floorZ = number(box.base_thickness);
  const rimZ = number(box.z);
  const usable = rimZ - floorZ;
  const bottomZ = floorZ + usable * (number(spec.from_bottom_percent, 0) / 100);
  const topZ = rimZ - usable * (number(spec.from_top_percent, 0) / 100);
  const r = widthMm / 2;
  if (bottomZ < floorZ - 1e-9) return false;
  if (topZ <= bottomZ + 1e-9) return false;
  if (number(spec.from_top_percent, 0) <= 1e-9) {
    return spec.shape === "curved" ? (rimZ - bottomZ) >= r - 1e-9 : true;
  }
  return spec.shape === "curved"
    ? (topZ - bottomZ) >= 2.5 * r - 1e-9
    : (topZ - bottomZ) >= r - 1e-9;
}

// Sizes that fit every currently-selected side at the current shape/depth/
// top-support combination. Mirrors organizer_side_openings.
// side_opening_allowed_sizes() so the browser never offers an impossible
// preset, but Python still re-validates on every preview/generate.
function sideOpeningAllowedSizes(design = state.design) {
  const rules = state.catalog?.side_openings || {};
  const sizes = rules.sizes || [];
  const margin = number(rules.corner_margin_mm, 4);
  const so = sideOpeningState(design);
  const spans = (so.sides || []).map(side => sideOpeningSideSpan(side, design));
  return sizes.filter(entry => {
    if (spans.some(span => entry.width_mm > span - 2 * margin + 1e-9)) return false;
    return sideOpeningVerticalFits(design, so, entry.width_mm);
  }).map(entry => entry.value);
}

function sideOpeningLidStackForced(design = state.design) {
  return lidPartActive(design);
}

// Fix 034 H: renamed from the old MaxFromTop - with inset_v2 semantics the
// Lid/Stack bridge is now a MINIMUM top inset (a higher % from top means
// more material left at the rim), not a maximum.
function sideOpeningMinFromTop(design = state.design) {
  const box = design?.box || {};
  const usable = number(box.z) - number(box.base_thickness);
  const bridge = number(state.catalog?.side_openings?.top_bridge_mm, 4);
  return usable > 0 ? 100 * bridge / usable : 0;
}

function clampSideOpeningTopForLid(design = state.design, flash = false) {
  const current = sideOpeningState(design);
  if (!current.enabled || !sideOpeningLidStackForced(design)) return;
  const minimum = Math.max(0, sideOpeningMinFromTop(design));
  if (number(current.from_top_percent, 0) < minimum) {
    design.box.side_openings = { ...current, from_top_percent: minimum };
    if (flash) flashField($("#side-opening-from-top"));
  }
}

function populateSideOpeningChoices() {
  const rules = state.catalog?.side_openings || {};
  const sizeSelect = $("#side-opening-size");
  if (sizeSelect && !sizeSelect.options.length) {
    for (const choice of rules.sizes || []) {
      sizeSelect.add(new Option(choice.label, choice.value));
    }
  }
}

// Mirrors readEdgeMountForm/readLiftGrabberForm: only resets an *existing*
// key to defaults when off, so a design that never touched Side Openings
// keeps no key at all and design_to_dict omits the block while disabled.
function readSideOpeningForm(design) {
  design.box = design.box || {};
  // Ordinary bins only - never surfaced for B4B or Base Trim.
  if (b4bEnabled() || baseTrimEnabled(design)) {
    if (design.box.side_openings) design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }
  const sides = SIDE_OPENING_SIDE_IDS.filter(
    side => $(`#side-opening-${side}`)?.getAttribute("aria-pressed") === "true"
  );
  const enabled = sides.length > 0 && !$("#side-openings-panel").hidden;
  if (!enabled) {
    if (design.box.side_openings) design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    return;
  }
  const current = { ...SIDE_OPENING_DEFAULTS, ...(design.box.side_openings || {}) };
  const shape = $("#side-opening-shape")?.value || current.shape;
  const fromBottom = number($("#side-opening-from-bottom")?.value, current.from_bottom_percent);
  let fromTop = number($("#side-opening-from-top")?.value, current.from_top_percent);
  if (sideOpeningLidStackForced(design)) fromTop = Math.max(fromTop, sideOpeningMinFromTop(design));
  const allowed = sideOpeningAllowedSizes({
    ...design,
    box: { ...design.box, side_openings: {
      ...current, sides, shape,
      from_bottom_percent: fromBottom, from_top_percent: fromTop,
    } },
  });
  let size = $("#side-opening-size")?.value || current.size;
  if (allowed.length && !allowed.includes(size)) size = allowed[allowed.length - 1];
  design.box.side_openings = {
    enabled: true,
    shape,
    sides,
    size,
    from_bottom_percent: fromBottom,
    from_top_percent: fromTop,
  };
}

function syncSideOpeningControls() {
  const active = sideOpeningPartActive();
  const forced = sideOpeningLidStackForced();
  if (forced) clampSideOpeningTopForLid(state.design, true);
  const so = sideOpeningState();
  $("#side-openings-panel").hidden = !active;
  $("#side-opening-shape").value = so.shape;
  $("#side-opening-from-bottom").value = fmt(so.from_bottom_percent);
  $("#side-opening-from-top").value = fmt(so.from_top_percent);
  for (const side of SIDE_OPENING_SIDE_IDS) {
    const input = $(`#side-opening-${side}`);
    if (!input) continue;
    input.setAttribute("aria-pressed", String((so.sides || []).includes(side)));
    input.classList.toggle("active", (so.sides || []).includes(side));
    const eligible = sideOpeningEligibleSide(side);
    input.disabled = !eligible;
    if (!eligible) input.setAttribute("aria-pressed", "false");
  }
  const anyEligible = SIDE_OPENING_SIDE_IDS.some(side => sideOpeningEligibleSide(side));
  const allowed = sideOpeningAllowedSizes();
  const sizeSelect = $("#side-opening-size");
  if (sizeSelect) {
    for (const option of sizeSelect.options) option.disabled = !allowed.includes(option.value);
    if (allowed.length && !allowed.includes(sizeSelect.value)) {
      sizeSelect.value = allowed[allowed.length - 1];
      flashField(sizeSelect);
    } else {
      sizeSelect.value = so.size;
    }
  }
  const note = $("#side-opening-note");
  if (note) {
    if (!anyEligible) {
      const rules = state.catalog?.side_openings || {};
      note.textContent = `Side openings require at least one bin side to be 2 units (${fmt(number(rules.min_side_mm, 16))} mm) or longer.`;
    } else if (sideOpeningAdjustmentNote) {
      note.textContent = sideOpeningAdjustmentNote;
    } else if (forced) {
      note.textContent = "% from top has a minimum to keep the Lid & Stacking bridge.";
    } else {
      note.textContent = "";
    }
  }
}

function wallPresetChoices(box = state.design?.box) {
  if (box?.b4b?.enabled) {
    const b4bChoices = state.catalog?.b4b_rules?.wall_choices;
    if (Array.isArray(b4bChoices) && b4bChoices.length) return b4bChoices;
  }
  const rules = state.catalog?.wall_rules || {};
  return Array.isArray(rules.choices) && rules.choices.length
    ? rules.choices
    : [
        { value: 0.4, label: "Very thin / prototype" },
        { value: 0.8, label: "Standard" },
        { value: 1.2, label: "Strong" },
        { value: 1.6, label: "Heavy" },
        { value: 2.0, label: "Extra heavy" },
        { value: 2.4, label: "Maximum" },
      ];
}

function populateWallChoices(box, select = $("#wall-thickness")) {
  const isB4B = Boolean(box?.b4b?.enabled);
  const ordinaryRules = state.catalog?.wall_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const stacking = (box?.stack?.mode || "none") === "direct" || Boolean(box?.lid?.enabled && box.lid.stackable);
  const hasLid = Boolean(box?.lid?.enabled);
  const stackMin = (stacking || hasLid) ? number(state.catalog?.stack_rules?.min_wall_mm, 1.2) : -Infinity;
  const modeMin = isB4B ? b4bMinWall() : stackMin;
  const choices = wallPresetChoices(box).filter(choice => number(choice.value) >= modeMin - 1e-9);
  const defaultWall = isB4B
    ? number(b4bRules.default_wall_mm, 1.6)
    : number(ordinaryRules.default_mm, 0.8);
  const wall = number(box?.wall, defaultWall);
  const value = fmt(wall);
  const standard = !isB4B && box?.standard_walls !== false && !stacking && !hasLid;
  const ordinaryDefaultValue = fmt(ordinaryRules.default_mm ?? 0.8);
  const numericChoices = isB4B
    ? choices
    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);
  const isDiscrete = numericChoices.some(choice => fmt(choice.value) === value);
  const customValue = !standard && !isDiscrete ? value : "";
  const signature = JSON.stringify({ numericChoices, customValue, modeMin, standard });
  if (select.dataset.choices !== signature) {
    select.replaceChildren();
    if (!stacking && !hasLid && !isB4B) select.add(new Option("Standard", "standard"));
    select.append(...numericChoices.map(choice => new Option(
      `${number(choice.value).toFixed(1)} mm — ${choice.label}`,
      fmt(choice.value),
    )));
    if (customValue) {
      // A saved design keeps whatever wall it was made with: the preset list is
      // what a *new* choice may be, not a migration of existing geometry.
      select.add(new Option(`${customValue} mm — Existing custom`, customValue));
    }
    select.dataset.choices = signature;
  }
  select.value = standard ? "standard" : value;
  if (box?.standard_walls === false) select.dataset.customValue = value;
}

// Minimum base thickness depends on wall thickness (the foot's flare has to
// finish inside solid base material before the wall begins), so the browser
// carries a Python-generated table rather than one fixed number per mode. A
// wall that falls between table entries takes the NEXT THICKER wall's
// minimum - never the thinner one, which would under-report what the
// geometry actually needs.
function stackBaseMinForWall(mode, wall) {
  const table = state.catalog?.stack_rules?.base_min_by_wall_mm?.[mode];
  const fallback = mode === "direct" ? 3.8 : 1.8;
  const entries = Object.entries(table || {})
    .map(([w, v]) => ({ wall: number(w), min: number(v) }))
    .filter(entry => Number.isFinite(entry.wall) && Number.isFinite(entry.min))
    .sort((a, b) => a.wall - b.wall);
  if (!entries.length) return fallback;
  const wallValue = number(wall, entries[0].wall);
  for (const entry of entries) {
    if (wallValue <= entry.wall + 1e-9) return entry.min;
  }
  return entries[entries.length - 1].min;
}

// The base value a stacking mode *requires*, or -Infinity when nothing forces
// it.  Ordinary lid/direct stacking and B4B stacking are the only two things
// that do; the two never apply at once (B4B and ordinary stacking are
// mutually exclusive), so one helper covers both without a conflict.
function baseRequiredMin(box) {
  if (box?.b4b?.enabled) {
    return box.b4b.stacking
      ? number(state.catalog?.b4b_rules?.stack_min_base_mm, 2.8)
      : -Infinity;
  }
  const mode = (box?.stack?.mode || "none") === "direct"
    ? "direct" : box?.lid?.enabled && box.lid.stackable ? "lid" : "none";
  if (mode === "none") return -Infinity;
  return stackBaseMinForWall(mode, box?.wall);
}

function baseRequiredLabel(box) {
  if (box?.b4b?.enabled) return "Required for stacking";
  const mode = (box?.stack?.mode || "none") === "direct"
    ? "direct" : box?.lid?.enabled && box.lid.stackable ? "lid" : "none";
  if (mode === "direct") return "Required for direct stacking";
  if (mode === "lid") return "Required for lid stacking";
  return "";
}

function populateBaseChoices(box, select = $("#base-thickness")) {
  const isB4B = Boolean(box?.b4b?.enabled);
  const ordinaryRules = state.catalog?.base_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const rules = isB4B
    ? {
        default_mm: number(b4bRules.default_base_mm, 1.6),
        choices: Array.isArray(b4bRules.base_choices)
          ? b4bRules.base_choices
          : [],
      }
    : ordinaryRules;
  const modeMin = baseRequiredMin(box);
  const allChoices = Array.isArray(rules.choices) && rules.choices.length
    ? rules.choices
    : [
        { value: 0.4, label: "Very thin" },
        { value: 0.6, label: "Good" },
        { value: 0.8, label: "Heavy" },
        { value: 1.0, label: "Extra Heavy" },
        { value: 1.2, label: "Maximum" },
      ];
  // A mode floor above the highest preset (B4B's 2.8, ordinary direct's 3.8)
  // filters every ordinary preset out, which is the point: the control must
  // not sit at a base the geometry cannot use.
  const choices = allChoices.filter(choice => number(choice.value) >= modeMin - 1e-9);
  const requiredLabel = baseRequiredLabel(box);
  const needsRequiredOption = Number.isFinite(modeMin) && requiredLabel
    && !choices.some(choice => Math.abs(number(choice.value) - modeMin) < 1e-9);
  const base = number(box?.base_thickness, rules.default_mm ?? 0.6);
  const value = fmt(base);
  const verticalStack = (box?.stack?.mode || "none") === "direct" || Boolean(box?.lid?.enabled && box.lid.stackable);
  const standard = box?.standard_base !== false && !isB4B && !verticalStack;
  const ordinaryDefaultValue = fmt(ordinaryRules.default_mm ?? 0.6);
  const numericChoices = isB4B
    ? choices
    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);
  const knownValues = numericChoices.map(choice => fmt(choice.value));
  if (needsRequiredOption) knownValues.push(fmt(modeMin));
  const customValue = !standard && !knownValues.includes(value) ? value : "";
  const signature = JSON.stringify({ numericChoices, needsRequiredOption, modeMin, customValue, standard });
  if (select.dataset.choices !== signature) {
    select.replaceChildren();
    if (!isB4B && !verticalStack) {
      select.add(new Option("Standard", "standard"));
    }
    select.append(...numericChoices.map(choice => new Option(
      `${number(choice.value).toFixed(1)} mm — ${choice.label}`,
      fmt(choice.value),
    )));
    if (needsRequiredOption) {
      select.add(new Option(`${fmt(modeMin)} mm — ${requiredLabel}`, fmt(modeMin)));
    }
    if (customValue) {
      // A saved design keeps whatever base it was made with: the preset list
      // is what a *new* choice may be, not a migration of existing geometry.
      select.add(new Option(`${customValue} mm — Existing custom`, customValue));
    }
    select.dataset.choices = signature;
  }
  select.value = standard ? "standard" : value;
}

function syncBaseControls() {
  $("#base-thickness-setting").hidden = isSurfaceBinDesign();
}

function syncWallControls() {
  const isB4B = b4bEnabled();
  const stacking = stackMode() !== "none" || Boolean(state.design?.box?.lid?.enabled);
  $("#wall-thickness-setting").hidden = false;
  const choices = wallPresetChoices(state.design?.box);
  const thinnest = choices.length ? number(choices[0].value, 0.4) : 0.4;
  const currentWall = number($("#wall-thickness").value, isB4B ? 1.6 : 0.8);
  const warningEl = $("#thin-wall-warning");
  if (warningEl) {
    const isThinnest = Math.abs(currentWall - thinnest) <= 1e-9;
    const hideWarning = (!isB4B && stacking) || $("#wall-thickness").value === "standard" || !isThinnest;
    warningEl.hidden = hideWarning;
    if (!hideWarning) {
      warningEl.textContent = isB4B
        ? "Super thin / light duty — reduced case strength."
        : "Very thin - may not print reliably with standard nozzle/slicer settings.";
    }
  }
}

function syncForm() {
  // Fix 060 Correction 3: syncForm() is also called for routine same-design
  // refreshes (modifier apply/rollback, Nest operations, preview auto-grow,
  // and more), not only when a different design is bound - so it must never
  // touch state.lidMemory itself. Real design-replacement call sites reseed
  // it explicitly via bindLidMemoryForDesign() before calling this.
  normalizeStackSettings(state.design);
  const { box, layout } = state.design;
  ensureRimFeatureInLayout();
  syncRimLabelFromFeatures();
  if (document.activeElement === $("#x-size")) {
    $("#x-size").value = fmt(box.x);
  } else {
    formatDimField("x");
  }
  if (document.activeElement === $("#y-size")) {
    $("#y-size").value = fmt(box.y);
  } else {
    formatDimField("y");
  }
  if (document.activeElement === $("#z")) {
    $("#z").value = fmt(box.z);
  } else {
    formatHeightField();
  }
  populateWallChoices(box);
  syncWallControls();
  populateBaseChoices(box);
  syncBaseControls();
  syncStackDependencyControls();
  populateLiftGrabberChoices();
  $("#lift-grabber-size").value = box.lift_grabbers?.enabled ? (box.lift_grabbers?.size || "medium") : "no";
  $("#lift-grabber-location").value = box.lift_grabbers?.location || "sides";
  syncLiftGrabberControls();
  populateEdgeMountChoices();
  if (editingEdgeMount()) syncEdgeMountControls();
  if (!state.design.part_name || !state.design.part_name.trim()) {
    const labelCandidate = state.design.label || state.design.b4b?.label_text || state.design.layout?.features?.find(f => f.kind === "text")?.options?.text;
    if (labelCandidate && !SIZE_LIKE_TEXT.test(labelCandidate)) {
      state.design.part_name = labelCandidate.trim();
    }
  }
  $("#part-name").value = state.design.part_name || "";
  const scoopEl = $("#scoop");
  if (scoopEl) scoopEl.checked = Boolean(state.design.scoop);
  $("#mode-select").value = layout.mode;
  $("#output-folder").value = state.runtime.hosted
    ? (state.browserFolder?.name || "Select a folder...")
    : state.output;
  // A routine form refresh must not touch the folder's inventory setting.
  setFolderState(
    state.folderMode,
    state.activeSpace,
    state.inventoryEnabled,
    state.keepBinDefaults,
    state.spaceBinDefaults,
    state.spacePartDefaults,
  );
  $("#connector-tolerance").value = fmt(state.connector.tolerance);
  $("#connector-length").value = fmt(state.connector.length);
  const armThicknessEl = $("#connector-arm-thickness");
  if (armThicknessEl) armThicknessEl.value = fmt(state.connector.arm_thickness ?? 1.0);
  $("#connector-bin-a-height").value = fmt(state.connector.bin_a_height ?? box.z);
  $("#connector-bin-b-height").value = fmt(state.connector.bin_b_height ?? box.z);
  $("#connector-height-mode").value = state.connector.different_heights ? "different" : "same";
  syncLidForm();
  populateSideOpeningChoices();
  syncSideOpeningControls();
  syncPegboardMountForm();
  syncConnectorSectionVisibility();
  updateInteriorModeVisibility();
  syncSurfaceControls();
  renderPlaced();
}

function activePegboardStandard() {
  const id = state.design?.box?.pegboard?.standard || state.activeSpace?.pegboard_standard || "standard";
  return state.catalog?.pegboard_rules?.standards?.find(row => row.id === id) || null;
}

function pegboardMinimumFor(count, standard, axis) {
  const sizes = axis === "x" ? standard?.minimum_widths_mm : standard?.minimum_heights_mm;
  return Number(sizes?.[count - 1] ?? Infinity);
}

function syncPegboardMountForm() {
  const row = $("#pegboard-mount-row");
  if (!row) return;
  const mount = state.design?.box?.pegboard;
  const active = Boolean(mount?.enabled) || (state.folderMode === "space" && state.activeSpace?.kind === "pegboard");
  row.hidden = !active || b4bEnabled() || baseTrimEnabled();
  if (row.hidden) return;
  const standard = activePegboardStandard();
  $("#pegboard-mount-standard").textContent = standard?.name || "Pegboard";
  $("#pegboard-cleat-x").value = String(mount?.cleat_x ?? "auto");
  $("#pegboard-cleat-y").value = String(mount?.cleat_y ?? "auto");
  for (const [selector, size, axis] of [["#pegboard-cleat-x", state.design.box.x, "x"], ["#pegboard-cleat-y", state.design.box.z, "y"]]) {
    for (const option of $(selector).options) {
      option.disabled = option.value !== "auto" && size + 1e-9 < pegboardMinimumFor(Number(option.value), standard, axis);
    }
    if ($(selector).selectedOptions[0]?.disabled) {
      $(selector).value = "auto";
      if (state.design.box.pegboard) state.design.box.pegboard[selector.endsWith("-x") ? "cleat_x" : "cleat_y"] = "auto";
    }
  }
  const preview = state.preview?.pegboard;
  const ribCount = preview?.ribs?.length || 0;
  $("#pegboard-mount-note").textContent = preview
    ? `${preview.resolved_x} × ${preview.resolved_y} receiver grid${ribCount ? `, ${ribCount} support rib${ribCount === 1 ? "" : "s"}` : ""}.`
    : "The receiver is standard-neutral; generation also creates the matching board adapters.";
}

function readPegboardMountForm(design) {
  design.box ||= {};
  const enabled = Boolean(design.box.pegboard?.enabled) ||
    (state.folderMode === "space" && state.activeSpace?.kind === "pegboard");
  if (!enabled || b4bEnabled(design) || baseTrimEnabled(design)) {
    if (design.box.pegboard) design.box.pegboard.enabled = false;
    return;
  }
  const standard = activePegboardStandard();
  const choice = (selector, size, axis) => {
    const value = $(selector)?.value || "auto";
    if (value === "auto" || size + 1e-9 >= pegboardMinimumFor(Number(value), standard, axis)) return value;
    $(selector).value = "auto";
    return "auto";
  };
  design.box.pegboard = {
    enabled: true,
    standard: design.box.pegboard?.standard || state.activeSpace?.pegboard_standard || "standard",
    cleat_x: choice("#pegboard-cleat-x", design.box.x, "x"),
    cleat_y: choice("#pegboard-cleat-y", design.box.z, "y"),
  };
}

function autoAdjustConnectorFields() {
  const rules = state.catalog?.connector_rules || {};
  const armT = rules.arm_thickness_mm ?? 1.0;
  const minDrop = rules.min_drop_mm ?? 2.0;
  const fullDrop = rules.full_drop_mm ?? 30.0;
  const webT = rules.web_thickness_mm ?? 3.0;
  const gain = rules.length_gain ?? 0.5;
  const baseLen = 12.0;

  const different = $("#connector-height-mode").value === "different";
  const binA = number($("#connector-bin-a-height").value, state.design?.box?.z ?? 40);
  const binB = different
    ? number($("#connector-bin-b-height").value, binA)
    : binA;
  const drop = different ? Math.abs(binA - binB) : 0;
  const frac = drop <= minDrop
    ? 0
    : Math.max(0, Math.min(1, (drop - minDrop) / (fullDrop - minDrop)));

  // Over the drop the seam holds one wall, not two, so the web has to reach
  // back across the empty half of the channel and run on the taller bin's
  // outer face. That reach is set by the seam, not by the drop, so it is a
  // floor under the drop-scaled thickness rather than a fraction of it - the
  // web is never thinner than this, however small the difference in height.
  const wallRules = state.catalog?.wall_rules || {};
  const wall = state.design?.box?.wall ?? wallRules.default_mm ?? 0.8;
  const tolerance = number($("#connector-tolerance")?.value, 0.02);
  const reach = wall * (wallRules.wall_depth_factor ?? rules.wall_depth_factor ?? 1.181)
    + (wallRules.mating_gap_mm ?? rules.mating_gap_mm ?? 0.25)
    + tolerance
    - (rules.web_run_clearance_mm ?? 0.15);

  const adjustedLen = baseLen * (1 + gain * frac);
  // frac === 0 is a plain extension with no web at all.
  const adjustedArm = frac > 0
    ? armT + Math.max((webT - armT) * frac, reach)
    : armT;

  const lenEl = $("#connector-length");
  if (lenEl && lenEl.value !== fmt(adjustedLen)) {
    lenEl.value = fmt(adjustedLen);
    flashField(lenEl);
  }
  const armEl = $("#connector-arm-thickness");
  if (armEl && armEl.value !== fmt(adjustedArm)) {
    armEl.value = fmt(adjustedArm);
    flashField(armEl);
  }
  if (state.connector) {
    state.connector.length = adjustedLen;
    state.connector.arm_thickness = adjustedArm;
  }
}

function syncConnectorHeightControls() {
  const different = $("#connector-height-mode").value === "different";
  $("#connector-bin-heights").hidden = !different;
  const settingsEl = $("#connector-settings");
  if (settingsEl) settingsEl.hidden = !different;
  autoAdjustConnectorFields();
  syncConnectorActionLabels();
}

// Mirrors organizer_engine.MIN_JOINABLE_SIZE; corner connectors below this
// in either X or Y are physically impossible regardless of user choice.
const MIN_CORNER_JOINABLE_MM = 16;

function syncConnectorSectionVisibility() {
  const noConnectors = baseTrimEnabled() || b4bEnabled();
  const heightWrap = $("#connector-height-wrap");
  if (noConnectors) {
    if (heightWrap) heightWrap.hidden = true;
    $("#connector-bin-heights").hidden = true;
    $("#connector-settings").hidden = true;
    renderConnectorReadout();
    return;
  }
  if (heightWrap) heightWrap.hidden = false;
  syncConnectorHeightControls();
  renderConnectorReadout();
  const connectorLocked = Boolean(state.design?.box?.lid?.enabled);
  $("#generate-all").hidden = connectorLocked;
  syncPrintChoiceAvailability();
  $("#generate-bin").hidden = false;
  $("#generate-connector").hidden = connectorLocked;
  syncConnectorActionLabels();
}

// Fix 019 Item 7: same-height bins auto-bundle Side + 3-Way + 4-Way
// connectors; different-height bins only ever produce a Side connector -
// keep the action wording matching that actual bundle, on every
// syncForm()/height-mode change, not just at first render.
function syncConnectorActionLabels() {
  const allButton = $("#generate-all");
  const connectorButton = $("#generate-connector");
  if (!allButton && !connectorButton) return;
  const different = $("#connector-height-mode")?.value === "different";
  if (allButton) {
    allButton.textContent = different ? "Save Bin + Side Connector" : "Save Bin + Connectors";
  }
  if (connectorButton) {
    connectorButton.textContent = different ? "Save Side Connector" : "Save Connectors";
    connectorButton.title = different
      ? "Save the Side connector for the current bin"
      : "Save Side, 3-Way Corner, and 4-Way Corner connectors for the current bin";
  }
}

function renderConnectorReadout(plan = null) {
  const el = $("#connector-derived");
  if (!el) return;
  if (baseTrimEnabled() || b4bEnabled()) {
    el.hidden = true;
    el.innerHTML = "";
    return;
  }
  // Audit 006 J3: the readout is exception-only. An ordinary eligible
  // same-height bin gets no generic explanation - only a set that actually
  // changed (different heights, or too small for corners) earns a line.
  const different = plan
    ? Boolean(plan.different_heights)
    : $("#connector-height-mode").value === "different";
  if (different) {
    el.textContent = "Side connector only — corner connectors require equal-height bins.";
    el.hidden = false;
    return;
  }
  const x = Number(plan?.box_x_mm ?? state.design?.box?.x);
  const y = Number(plan?.box_y_mm ?? state.design?.box?.y);
  const cornersSkipped = Array.isArray(plan?.skipped_types) && plan.skipped_types.length > 0;
  const tooSmall = cornersSkipped
    || (Number.isFinite(x) && Number.isFinite(y) && (x < MIN_CORNER_JOINABLE_MM || y < MIN_CORNER_JOINABLE_MM));
  if (tooSmall) {
    el.textContent = `Side connector only — corner connectors need at least ${MIN_CORNER_JOINABLE_MM} mm in both X and Y.`;
    el.hidden = false;
    return;
  }
  el.textContent = "";
  el.hidden = true;
}

function updateInteriorModeVisibility(reveal = false) {
  const hasSupport = Boolean(state.draft || state.design?.layout?.features?.length);
  if (reveal && !hasSupport && state.design.layout.mode !== "fused") {
    state.design.layout.mode = "fused";
    $("#mode-select").value = "fused";
  }
}

function baseTrimPresetRows() {
  return state.catalog?.base_trim_rules?.size_presets || [];
}

function surfaceTrimHeight(trimSize) {
  const row = baseTrimPresetRows().find(one => one.key === trimSize);
  const value = Number(row?.value_mm);
  return Number.isFinite(value) ? value : null;
}

// One prompt per unfinished Surface bin. The setting lives in this Space's
// saved layout, while the number belongs to this bin and its Inventory row.
async function maybePromptSurfaceObjectHeight() {
  if (!isSurfaceBinDesign() || state.design.layout.object_height_mm != null ||
      state.surfaceHeightPromptSkipped || typeof DL === "undefined") return true;
  if (!(await DL.ensureLoaded())) return false;
  const context = DL.spaceContext();
  if (DL.layout?.settings?.surface?.ask_object_height === false) return true;
  const dialog = $("#surface-object-height-dialog");
  const input = $("#surface-object-height-prompt");
  const noAsk = $("#surface-object-height-no-ask");
  const error = $("#surface-object-height-error");
  input.value = "";
  noAsk.checked = false;
  error.hidden = true;
  return new Promise(resolve => {
    let busy = false;
    const finish = value => {
      $("#surface-object-height-save").onclick = null;
      $("#surface-object-height-continue").onclick = null;
      dialog.removeEventListener("cancel", onCancel);
      if (dialog.open) dialog.close();
      resolve(value);
    };
    const persistPreference = async () => {
      if (!noAsk.checked) return true;
      DL.requireSpaceContext(context);
      DL.change(() => { DL.layout.settings.surface.ask_object_height = false; }, { history: false });
      return DL.save();
    };
    const onCancel = event => { event.preventDefault(); if (!busy) finish(false); };
    $("#surface-object-height-save").onclick = async () => {
      if (busy) return;
      const height = Number(input.value);
      if (!input.value.trim() || !Number.isFinite(height) || height <= 0) {
        error.textContent = "Enter a positive Object height, or continue without one.";
        error.hidden = false;
        return;
      }
      busy = true;
      try {
        DL.requireSpaceContext(context);
        if (state.designInventoryId && !typedSpaceOrdinaryBin() &&
            !(await DL.editBins({ bin_updates: [{ id: state.designInventoryId,
              object_height_mm: height }] }, { context, customFailure: true })))
          throw new Error("Object height was not saved.");
        if (!(await persistPreference())) throw new Error("Surface setting was not saved.");
        DL.requireSpaceContext(context);
        const before = clone(state.design);
        state.design.layout.object_height_mm = height;
        $("#surface-object-height").value = height;
        changedDesign(before);
        finish(true);
      } catch (cause) {
        error.textContent = cause.message;
        error.hidden = false;
      } finally { busy = false; }
    };
    $("#surface-object-height-continue").onclick = async () => {
      if (busy) return;
      busy = true;
      try {
        if (!(await persistPreference())) throw new Error("Surface setting was not saved.");
        DL.requireSpaceContext(context);
        state.surfaceHeightPromptSkipped = true;
        finish(true);
      } catch (cause) {
        error.textContent = cause.message;
        error.hidden = false;
      } finally { busy = false; }
    };
    dialog.addEventListener("cancel", onCancel);
    dialog.showModal();
    input.focus();
  });
}

function isSurfaceBinDesign(design = state.design) {
  return state.folderMode === "space" && state.activeSpace?.kind === "surface"
    && !design?.box?.b4b?.enabled && !baseTrimEnabled(design);
}

function surfaceStackingBlocked(design = state.design) {
  return design?.box?.stack?.mode === "direct" || Boolean(design?.box?.lid?.enabled && design.box.lid.stackable);
}

function resolveSurfaceBase(design, { fromForm = false } = {}) {
  if (!isSurfaceBinDesign(design)) return;
  design.layout ||= {};
  const oldBase = number(design.box.base_thickness, 0.6);
  const oldZ = number(design.box.z, oldBase + 5);
  const minimum = number(state.catalog?.min_height_above_base_mm, 5);
  const mode = fromForm ? $("#surface-base-mode").value : (design.layout.surface_base_mode || "custom");
  const edge = surfaceTrimHeight(state.activeSpace.trim_size);
  const base = mode === "edge" ? edge : (fromForm
    ? number($("#surface-base-custom").value, oldBase) : oldBase);
  if (!Number.isFinite(base) || base <= 0) return;
  design.layout.surface_base_mode = mode;
  design.box.standard_base = false;
  design.box.base_thickness = base;
  if (Math.abs(base - oldBase) > 1e-9) {
    design.box.z = mode === "edge"
      ? base + Math.max(minimum, oldZ - oldBase)
      : Math.max(oldZ, base + minimum);
  }
  if (fromForm) {
    const objectText = $("#surface-object-height").value.trim();
    design.layout.object_height_mm = objectText ? Number(objectText) : null;
    design.layout.surface_lightweight_base = !surfaceStackingBlocked(design)
      && $("#surface-lightweight-base").checked;
  }
}

function syncSurfaceControls() {
  const shown = isSurfaceBinDesign();
  const controls = $("#surface-bin-controls");
  if (!controls) return;
  controls.hidden = !shown;
  $("#base-thickness-setting").hidden = shown;
  if (!shown) return;
  const layout = state.design.layout || {};
  const edge = surfaceTrimHeight(state.activeSpace.trim_size);
  $("#z-size-label").textContent = "Bin height";
  $("#surface-base-mode").value = layout.surface_base_mode === "edge" ? "edge" : "custom";
  $("#surface-base-custom-row").hidden = layout.surface_base_mode === "edge";
  if (document.activeElement !== $("#surface-base-custom"))
    $("#surface-base-custom").value = fmt(state.design.box.base_thickness);
  $("#surface-base-resolved").textContent = `Platform: ${fmt(state.design.box.base_thickness)} mm${layout.surface_base_mode === "edge" ? ` (Surface edge ${fmt(edge)} mm)` : ""}`;
  const blocked = surfaceStackingBlocked();
  $("#surface-lightweight-base").disabled = blocked;
  $("#surface-lightweight-base").checked = !blocked && Boolean(layout.surface_lightweight_base);
  $("#surface-lightweight-base").title = blocked ? "Unavailable with vertical stacking." : "Hidden support-free underside cavities.";
  if (document.activeElement !== $("#surface-object-height"))
    $("#surface-object-height").value = layout.object_height_mm ?? "";
  const plan = Number(state.preview?.planning?.object_height_mm) === Number(layout.object_height_mm)
    ? state.preview.planning : null;
  $("#surface-planning-height").textContent = layout.object_height_mm == null
    ? "Object height not set — using physical bin height for planning"
    : plan?.source === "bore"
      ? `Installed planning height: ${fmt(plan.effective_mm)} mm`
      : `Installed planning height: ~${fmt(plan?.effective_mm ?? layout.object_height_mm)} mm (estimated)`;
}

const LIFT_GRABBER_DEFAULTS = { enabled: false, size: "medium", location: "sides" };
// Fix 058 Correction 1, C1.4D: 0.6 mm is Edge Mount's own default text depth
// for a new/missing value - this never changes the global text-depth default
// used by other label/text systems (floor labels, lid labels, ...).
const EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM = 0.6;
const EDGE_MOUNT_DEFAULTS = {
  side: "front",
  label_enabled: false,
  label_text: "",
  label_type: "separate",
  label_projection_mm: 50,
  label_length_mode: "full",
  label_thickness_mm: 2,
  label_raised: false,
  label_text_depth_mm: EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
  label_flip: false,
  standoff_ribs_enabled: true,
  standoff_rib_count: null,
  holes_enabled: false,
  hole_count: 2,
  hole_orientation: "horizontal",
  screw_diameter_mm: 4,
  access_diameter_mm: null,
  top_offset_mm: 12.7,
  hole_spacing_mm: null,
};

function baseTrimEnabled(design = state.design) {
  return design?.design_kind === "base_trim";
}

function storedPreference(key, fallback) {
  if (!state.runtime.hosted) return state.catalog?.preferences?.[key] ?? fallback;
  try {
    const raw = localStorage.getItem(`wavefinity-${key.replaceAll("_", "-")}`);
    return raw === null ? fallback : raw;
  } catch (_error) {
    return fallback;
  }
}

function saveSimplePreference(key, value) {
  if (state.runtime.hosted) {
    try { localStorage.setItem(`wavefinity-${key.replaceAll("_", "-")}`, String(value)); } catch (_error) {}
    return;
  }
  api("/api/preferences", { [key]: value }).catch(() => {});
  if (state.catalog?.preferences) state.catalog.preferences[key] = value;
}


// Shared by updateDesignFromForm() and designHasChanges() so both compute the
// same box.lift_grabbers from the live form. Mirrors readStackForm:
// only resets an *existing* key to defaults when off, so a design that never
// touched this feature keeps no key at all and stays byte-identical to what
// the server would save (design_to_dict omits the block while disabled).
function readLiftGrabberForm(design) {
  design.box = design.box || {};
  const size = $("#lift-grabber-size")?.value || "no";
  const enabled = size !== "no";
  if (!enabled) {
    if (design.box.lift_grabbers) design.box.lift_grabbers = { ...LIFT_GRABBER_DEFAULTS };
    return;
  }
  design.box.lift_grabbers = {
    enabled: true,
    size,
    location: $("#lift-grabber-location")?.value || "sides",
  };
}

// Lift grabbers need a real bite into the wall, not just wave clearance on
// paper - a very thin wall fails that check server-side. Rather than reject
// the combination, bump the wall preset up to the first one that clears it
// (normally Strong, since Standard's 0.8 mm is no longer enough) whenever
// grabbers are switched on over too thin a wall. A wall that already clears
// it - including a legacy value like 1.4 mm - is left exactly as the user
// set it.
function promoteWallForLiftGrabbers() {
  const select = $("#wall-thickness");
  if (!select) return;
  const defaultWall = number(state.catalog?.wall_rules?.default_mm, 0.8);
  const minWall = number(state.catalog?.lift_grabbers?.min_wall_mm, defaultWall);
  const currentValue = select.value;
  const currentWall = currentValue === "standard" ? defaultWall : number(currentValue, defaultWall);
  if (currentWall >= minWall - 1e-9) return;
  const candidates = [...select.options]
    .map(option => ({
      option,
      wall: option.value === "standard" ? defaultWall : number(option.value, NaN),
    }))
    .filter(entry => Number.isFinite(entry.wall) && entry.wall >= minWall - 1e-9)
    .sort((a, b) => a.wall - b.wall);
  if (!candidates.length) return;
  select.value = candidates[0].option.value;
  if (select.value === "standard") {
    delete select.dataset.customValue;
  } else {
    select.dataset.customValue = select.value;
  }
  flashField(select);
}
function b4bMinWall() {
  return number(state.catalog?.b4b_rules?.min_wall_mm, 0.8);
}

function b4bEnabled() {
  return Boolean(state.design?.box?.b4b?.enabled);
}

function b4bPartAllowed(kind) {
  return kind === "divider";
}

function dividerLayoutExtent(box = state.design?.box) {
  if (box?.b4b?.enabled) {
    return [number(box.x), number(box.y)];
  }
  return binInsideExtent(box);
}

function stackMode() {
  if ((state.design?.box?.stack?.mode || "none") === "direct") return "direct";
  return state.design?.box?.lid?.enabled && state.design.box.lid.stackable ? "lid" : "none";
}

const LID_DEFAULTS = {
  enabled: false, stackable: false, thickness: "thin",
  label_enabled: false, label_style: "flush", label_orientation: "horizontal",
  label_text: "", division_labels: [], handle_type: "knob",
  handle_size: "medium", handle_position: "middle",
};

function lidState(design = state.design) {
  const boxLid = design?.box?.lid;
  // Fix 060 Correction 1: fall back to the remembered Lid/Handle/Label values
  // while Stackable Bin hides design.box.lid, but `enabled` always reflects
  // the actual design - never the memory - so a hidden/inactive lid never
  // reads as active (e.g. for the compartment-label editor or divider lock).
  return { ...LID_DEFAULTS, ...(state.lidMemory || {}), ...(boxLid || {}), enabled: Boolean(boxLid?.enabled) };
}

// Fix 060 Correction 2: label_style is a real, unforced preference only while
// Handled Lid is active - Stackable Lid always forces the active value to
// Flush. Snapshotting the true style (not the forced one) here, rather than
// wherever design.box.lid is about to be mutated, lets it survive any number
// of Stackable Bin/Stackable Lid switches until Handled Lid is chosen again.
function rememberedLidSnapshot(design = state.design) {
  const boxLid = design?.box?.lid;
  if (!boxLid) return null;
  const merged = lidState(design);
  const labelStyle = lidConfiguration(design) === "stackable_lid"
    ? (state.lidMemory?.label_style ?? merged.label_style)
    : boxLid.label_style;
  return { ...merged, label_style: labelStyle };
}

// Fix 060 Correction 3: the only safe moment to reseed/clear the remembered
// Lid/Handle/Label values is when a genuinely different design is bound to
// the editor (New, Open, Duplicate, Undo/Redo, a Space activating/resuming a
// design, app bootstrap) - never a routine same-design syncForm() refresh
// (modifier add/remove/rollback, feature apply, Nest operations, preview
// auto-grow, and every other syncForm() caller not listed here). Call this
// explicitly at each such replacement site, after state.design is reassigned
// and before the resulting syncForm()/syncLidForm() call reads it.
function bindLidMemoryForDesign(design = state.design) {
  state.lidMemory = rememberedLidSnapshot(design);
}

function lidPartActive(design = state.design) {
  return (design?.box?.stack?.mode || "none") === "direct" || Boolean(design?.box?.lid?.enabled);
}

function lidConfiguration(design = state.design) {
  if ((design?.box?.stack?.mode || "none") === "direct") return "stackable_bin";
  if (design?.box?.lid?.enabled) return design.box.lid.stackable ? "stackable_lid" : "handled_lid";
  return "stackable_bin";
}

function lidDivider(design = state.design) {
  return design?.layout?.features?.find(one => one.kind === "divider") || null;
}

function lidDivisionLabelsMeaningful(design = state.design) {
  return Boolean(design?.box?.lid?.enabled && design.box.lid.label_enabled && lidDivider(design) &&
    (design.box.lid.division_labels || []).some(value => String(value || "").trim()));
}

function dividerLockedByLidLabels(design = state.design) {
  return lidDivisionLabelsMeaningful(design);
}

function dividerLockMessage() {
  return "This divider layout is being used by the lid labels. Clear the lid compartment labels before changing the divider layout.";
}

function dividerLabelsForLid(divider) {
  let labels = divider?.options?.division_labels;
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { labels = labels.split(","); }
  }
  return Array.isArray(labels) ? [...labels] : [];
}

function applyDivisionGridLayout(root) {
  if (!root) return;
  $$(".division-grid[data-grid-columns][data-grid-rows]", root).forEach(grid => {
    grid.style.setProperty("--division-columns", grid.dataset.gridColumns);
    grid.style.setProperty("--division-rows", grid.dataset.gridRows);
  });
  $$("[data-grid-column][data-grid-row]", root).forEach(input => {
    input.style.gridColumn = `${input.dataset.gridColumn} / span ${input.dataset.gridColumnSpan}`;
    input.style.gridRow = `${input.dataset.gridRow} / span ${input.dataset.gridRowSpan}`;
  });
}

function renderLidLabelEditor() {
  const holder = $("#lid-division-labels");
  const textRow = $("#lid-label-text-row");
  if (!holder || !textRow) return;
  const lid = lidState();
  const divider = lidDivider();
  const enabled = lid.enabled && lid.label_enabled;
  textRow.hidden = !enabled || Boolean(divider);
  holder.hidden = !enabled || !divider;
  if (!enabled || !divider) {
    holder.replaceChildren();
    return;
  }
  const topology = dividerCompartmentsClient(divider);
  const labels = Array.isArray(lid.division_labels) ? lid.division_labels : [];
  holder.innerHTML = `<span class="field-label">Compartment labels</span><div class="division-table division-grid" data-grid-columns="${topology.columns}" data-grid-rows="${topology.rows}">
    ${topology.cells.map(cell => {
      const index = cell.row * topology.columns + cell.column;
      return `<input type="text" data-lid-division-index="${index}" data-grid-column="${cell.column + 1}" data-grid-column-span="${cell.columnSpan}" data-grid-row="${cell.row + 1}" data-grid-row-span="${cell.rowSpan}" value="${escapeHtml(String(labels[index] || ""))}">`;
    }).join("")}</div>`;
  applyDivisionGridLayout(holder);
  $$('[data-lid-division-index]', holder).forEach(input => input.addEventListener("input", () => {
    const previous = clone(state.design);
    const values = Array.isArray(state.design.box.lid.division_labels)
      ? [...state.design.box.lid.division_labels] : [];
    values[Number(input.dataset.lidDivisionIndex)] = input.value;
    state.design.box.lid.division_labels = values;
    seedPartNameFromLabel(input.value);
    if (state.draft?.kind === "divider") renderDraftFields();
    updateSelectionButtons();
    changedDesign(previous);
  }));
}

function syncLidForm() {
  const active = lidPartActive();
  const lid = lidState();
  const config = lidConfiguration();
  $("#lid-option-panel").hidden = !active;
  $("#lid-configuration").value = config;
  $("#lid-thickness").value = lid.thickness;
  $("#lid-handle-type").value = lid.handle_type;
  $("#lid-handle-size").value = lid.handle_size;
  $("#lid-handle-position").value = lid.handle_position;
  $("#lid-label-enabled").value = String(Boolean(lid.label_enabled));
  $("#lid-label-orientation").value = lid.label_orientation;
  $("#lid-label-style").value = lid.label_style;
  $("#lid-label-text").value = lid.label_text || "";
  const hasLid = config !== "stackable_bin";
  const handled = config === "handled_lid";
  // Fix 060 A: Lid / Handle / Label now read as separate groups instead of one
  // mixed grid. Handle is hidden entirely (not just disabled) outside Handled
  // Lid - its saved values are left untouched so switching configurations
  // back and forth never erases them.
  $("#lid-group-lid").hidden = !hasLid;
  $("#lid-group-handle").hidden = !handled;
  ["#lid-handle-type-row", "#lid-handle-size-row", "#lid-handle-position-row"].forEach(selector => {
    $(selector).hidden = !handled;
  });
  $("#lid-group-label").hidden = !hasLid;
  const labelOn = hasLid && lid.label_enabled;
  $("#lid-label-details").hidden = !labelOn;
  $("#lid-label-orientation-row").hidden = !labelOn;
  // Style is a one-choice control for Stackable Lid (Raised is invalid and the
  // engine already forces Flush), so it is hidden there rather than shown
  // disabled; Handled Lid keeps the real Level-with-top/Raised choice.
  $("#lid-label-style-row").hidden = !labelOn || !handled;
  const raised = [...$("#lid-label-style").options].find(option => option.value === "raised");
  if (raised) raised.disabled = config === "stackable_lid";
  if (config === "stackable_lid" && $("#lid-label-style").value === "raised") {
    $("#lid-label-style").value = "flush";
  }
  const note = $("#lid-option-note");
  note.textContent = config === "stackable_bin"
    ? "No lid. This bin stacks directly into another matching bin."
    : config === "stackable_lid"
      ? "Handle and raised lettering are unavailable because the next bin needs a flat seating surface."
      : "One removable handled lid. This bin is not stackable.";
  renderLidLabelEditor();
  applyStackVisibility();
}

function stackRuleValues(mode = stackMode(), wall = state.design?.box?.wall) {
  const rules = state.catalog?.stack_rules || {};
  return {
    minWall: number(rules.min_wall_mm, 1.2),
    defaultWall: number(rules.default_wall_mm, state.catalog?.wall_rules?.default_mm ?? 0.8),
    defaultBase: number(rules.default_base_mm, 0.6),
    minBase: stackBaseMinForWall(mode, wall),
  };
}

function normalizeStackSettings(design, { restoreDefaults = false, flash = false } = {}) {
  const box = design?.box;
  if (!box) return;
  const mode = (box.stack?.mode || "none") === "direct"
    ? "direct" : box.lid?.enabled && box.lid.stackable ? "lid" : "none";
  const hasLid = Boolean(box.lid?.enabled);
  const changed = [];
  const set = (key, value, selector) => {
    if (box[key] === value) return;
    box[key] = value;
    if (selector) changed.push(selector);
  };
  if (mode !== "none" || hasLid) {
    const values = stackRuleValues(mode, box.wall);
    set("standard_walls", false, "#wall-thickness");
    if (number(box.wall, values.defaultWall) < values.minWall) {
      set("wall", values.minWall, "#wall-thickness");
    }
    // The base minimum depends on the (possibly just-bumped) wall value, so
    // it is resolved again after the wall is settled, never before.
    if (mode !== "none") {
      const minBase = stackBaseMinForWall(mode, box.wall);
      set("standard_base", false, "#base-thickness");
      if (number(box.base_thickness, values.defaultBase) < minBase) {
        set("base_thickness", minBase, "#base-thickness");
      }
    }
  } else if (restoreDefaults) {
    const values = stackRuleValues(mode, box.wall);
    set("standard_walls", true, "#wall-thickness");
    set("wall", values.defaultWall, "#wall-thickness");
    set("standard_base", true, "#base-thickness");
    set("base_thickness", values.defaultBase, "#base-thickness");
  }
  if (flash) changed.forEach(selector => {
    const field = $(selector);
    if (field) flashField(field);
  });
}

function syncStackDependencyControls() {
  syncBaseControls();
  syncWallControls();
}

function applyStackVisibility() {
  const b4b = b4bEnabled();
  const mode = stackMode();
  const hasLid = Boolean(state.design?.box?.lid?.enabled);
  const note = $("#stack-note");
  if (!note) return;
  const connectorLocked = hasLid;
  const connectorSection = document.querySelector('.control-section[data-section="connector"]');
  if (connectorSection) connectorSection.hidden = b4b || baseTrimEnabled() || connectorLocked;
  ["#generate-all", "#generate-connector"].forEach(selector => {
    const element = $(selector);
    if (element) element.hidden = b4b || baseTrimEnabled() || connectorLocked;
  });
  syncPrintChoiceAvailability();
  if (!baseTrimEnabled()) {
    $("#generate-bin").textContent = hasLid ? "Save Bin + Lid" : "Save Bin";
  }
  const info = state.preview?.stack;
  if (b4b || (mode === "none" && !hasLid)) {
    note.hidden = true;
    return;
  }
  const values = stackRuleValues(mode);
  const moduleHeight = info?.mode === mode
    ? info.module_height_mm
    : state.design?.box?.z;
  const bits = mode === "none"
    ? [`The handled lid uses at least ${fmt(values.minWall)} mm walls for its retention clips. It does not add stacking geometry.`]
    : [
        `Stacking requires at least ${fmt(values.minWall)} mm walls and a ${fmt(values.minBase)} mm base.`,
        `Stack height contribution: ${fmt(moduleHeight)} mm${mode === "lid" ? " including lid" : ""}.`,
      ];
  if (info?.mode === mode) {
    bits.push(`Detached closed part: ${fmt(info.closed_height_mm)} mm including the ${fmt(info.engagement_mm)} mm interlock.`);
    if (info.parts.length > 1) bits.push(`Prints as ${info.parts.join(" + ")}.`);
  }
  note.textContent = bits.join(" ");
  note.hidden = false;
}

function readStackForm(design) {
  design.box = design.box || {};
  if (!lidPartActive(design)) {
    delete design.box.stack;
    delete design.box.lid;
    return;
  }
  const previousConfig = lidConfiguration(design);
  const config = $("#lid-configuration")?.value || previousConfig;
  const remembered = lidState(design);
  // Fix 060 Correction 1+2: snapshot the real Lid/Handle/Label values -
  // including the true (not forced-Flush) label_style - before this call
  // mutates design.box.lid, so switching to Stackable Bin or Stackable Lid
  // never erases what Handled Lid had, however many switches happen next.
  if (design.box.lid) state.lidMemory = rememberedLidSnapshot(design);
  if (config === "stackable_bin") {
    // No active design.box.lid here: the backend/output and Divider label
    // locking must see Stackable Bin as having no lid at all.
    design.box.stack = { mode: "direct" };
    delete design.box.lid;
    return;
  }
  delete design.box.stack;
  const divider = lidDivider(design);
  let divisionLabels = Array.isArray(remembered.division_labels) ? [...remembered.division_labels] : [];
  const labelEnabled = $("#lid-label-enabled").value === "true";
  if (!labelEnabled) divisionLabels = [];
  if (divider && labelEnabled && !divisionLabels.some(value => String(value || "").trim())) {
    divisionLabels = dividerLabelsForLid(divider);
  }
  // Stackable Lid always forces the active style to Flush; leaving Stackable
  // Lid restores the remembered Handled Lid style rather than the live
  // control, which was itself forced to Flush the moment Stackable Lid
  // became active and so cannot be trusted here. A direct field edit while
  // already in one of the two active configs still reads the live control.
  const labelStyle = config === "stackable_lid"
    ? "flush"
    : previousConfig === "stackable_lid"
      ? (state.lidMemory?.label_style ?? $("#lid-label-style").value)
      : $("#lid-label-style").value;
  design.box.lid = {
    enabled: true,
    stackable: config === "stackable_lid",
    thickness: $("#lid-thickness").value,
    label_enabled: labelEnabled,
    label_style: labelStyle,
    label_orientation: $("#lid-label-orientation").value,
    label_text: $("#lid-label-text").value,
    division_labels: divisionLabels,
    handle_type: $("#lid-handle-type").value || remembered.handle_type,
    handle_size: $("#lid-handle-size").value || remembered.handle_size,
    handle_position: $("#lid-handle-position").value || remembered.handle_position,
  };
}

// Shared by typed Width/Length/Height edits, by dragging their dimension
// labels (see hitDimensionHandle/commitDimensionDrag), so every path
// lands on the same legal value: X/Y snap to the catalog base unit and clamp
// to [unit, max_box_size]; Z rounds to whole millimetres with a floor that
// clears the base thickness by min_height_above_base_mm (BoxSpec requires
// it).
function normalizeBinDimension(axis, requestedValue, fallback, design = state.design) {
  const value = number(requestedValue, fallback);
  if (axis === "z") {
    const base = number(
      design?.box?.base_thickness,
      state.catalog?.base_rules?.default_mm ?? 0.6
    );
    const minimum = base + number(state.catalog.min_height_above_base_mm, 5);
    return isSurfaceBinDesign(design)
      ? Math.max(minimum, Math.round(value * 10) / 10)
      : Math.max(Math.ceil(minimum), Math.round(value));
  }
  const unit = state.catalog.base_unit;
  const max = Math.floor((state.catalog.max_box_size || 350) / unit) * unit;
  return Math.min(max, snapToUnit(value, unit));
}

// The exact X/Y rounding rule normal Width/Length arrow keys, wheel and blur
// all use: nearest whole catalog unit, floored at one unit.
function snapToUnit(value, unit) {
  return Math.max(unit, Math.round(value / unit) * unit);
}

function updateDesignFromForm() {
  const design = state.design;
  const prevBoxX = design.box.x;
  if (isSurfaceBinDesign(design)) resolveSurfaceBase(design, { fromForm: true });
  const prevBoxY = design.box.y;
  const newBoxX = normalizeBinDimension("x", $("#x-size").value, design.box.x);
  const newBoxY = normalizeBinDimension("y", $("#y-size").value, design.box.y);
  design.box.x = newBoxX;
  design.box.y = newBoxY;
  const boxFootprintChanged = design.box.x !== prevBoxX || design.box.y !== prevBoxY;
  // Width/Length handlers update state before this debounced read, so the
  // dedicated pending flag detects a resize even when prevBoxX/Y already
  // contain the new values.
  const sideOpeningResizeChanged = state.binFootprintResizePending || boxFootprintChanged;
  const prevBoxZ = design.box.z;
  design.box.z = normalizeBinDimension("z", $("#z").value, design.box.z);
  if (boxFootprintChanged) {
    turnOffNestAutoSizeForManualEdit();
  }
  checkBinSizeChange();
  if (sideOpeningResizeChanged) {
    reconcileSideOpeningsAfterResize(design);
    syncSideOpeningControls();
    state.binFootprintResizePending = false;
  }
  if (design.box.z !== prevBoxZ) {
    const setAutoConnectorHeight = selector => {
      const input = $(selector);
      const next = fmt(design.box.z);
      if (input && input.value !== next) {
        input.value = next;
        flashField(input);
      }
    };
    if ($("#connector-height-mode").value === "same") {
      setAutoConnectorHeight("#connector-bin-a-height");
      setAutoConnectorHeight("#connector-bin-b-height");
    } else {
      setAutoConnectorHeight("#connector-bin-a-height");
      autoAdjustConnectorFields();
    }
  }
  const b4bOn = b4bEnabled();
  const currentStackMode = stackMode();
  const hasOrdinaryLid = Boolean(design.box.lid?.enabled);
  const stackValues = stackRuleValues(currentStackMode, design.box.wall);
  // Wall is resolved before base: the required base depends on the *final*
  // wall value, so it must be looked up after the wall choice is settled.
  const previousWall = design.box.wall;
  const wallRules = state.catalog?.wall_rules || {};
  const b4bRules = state.catalog?.b4b_rules || {};
  const defaultWall = b4bOn
    ? number(b4bRules.default_wall_mm, 1.6)
    : (wallRules.default_mm ?? 0.8);
  const minWall = b4bOn
    ? b4bMinWall()
    : (currentStackMode === "none" && !hasOrdinaryLid
        ? wallRules.min_mm ?? 0.2
        : stackValues.minWall);
  const maxWall = wallRules.max_mm ?? 2.4;
  const wallChoice = $("#wall-thickness").value;
  design.box.standard_walls = !b4bOn && currentStackMode === "none" && !hasOrdinaryLid && wallChoice === "standard";
  design.box.wall = design.box.standard_walls
    ? defaultWall
    : Math.max(minWall, Math.min(maxWall, number(
        wallChoice,
        design.box.wall ?? defaultWall,
      )));
  $("#wall-thickness").value = design.box.standard_walls ? "standard" : fmt(design.box.wall);
  if (design.box.wall !== previousWall) autoAdjustConnectorFields();
  const baseChoice = $("#base-thickness").value;
  design.box.standard_base = !isSurfaceBinDesign(design) && !b4bOn && currentStackMode === "none" && baseChoice === "standard";
  const defaultBase = b4bOn
    ? number(b4bRules.default_base_mm, 1.6)
    : number(state.catalog?.base_rules?.default_mm, 0.6);
  if (!isSurfaceBinDesign(design)) design.box.base_thickness = design.box.standard_base
    ? defaultBase
    : number(baseChoice, design.box.base_thickness ?? defaultBase);
  if (currentStackMode !== "none") {
    const minBase = stackBaseMinForWall(currentStackMode, design.box.wall);
    design.box.base_thickness = Math.max(minBase, design.box.base_thickness);
  }
  design.part_name = $("#part-name").value;
  const scoopEl = $("#scoop");
  if (scoopEl) design.scoop = scoopEl.checked;
  readLiftGrabberForm(design);
  if (editingEdgeMount()) readEdgeMountForm(design);
  readSideOpeningForm(design);
  syncRimLabelFromFeatures();
  const newOutput = $("#output-folder").value.trim();
  if (!state.runtime.hosted && newOutput !== state.output) {
    state.output = newOutput;
    saveOutputPreference(newOutput);
  }
  state.connector = {
    tolerance: number($("#connector-tolerance").value, state.connector.tolerance),
    length: number($("#connector-length").value, state.connector.length),
    arm_thickness: number($("#connector-arm-thickness")?.value, state.connector.arm_thickness ?? 1.0),
    height: state.connector.height,
    bin_a_height: number($("#connector-bin-a-height").value, state.design.box.z),
    bin_b_height: number($("#connector-bin-b-height").value, state.design.box.z),
    different_heights: $("#connector-height-mode").value === "different",
    position: 0,
    axis: "y",
  };
  readPegboardMountForm(design);
  readStackForm(design);
  if (isSurfaceBinDesign(design) && surfaceStackingBlocked(design))
    design.layout.surface_lightweight_base = false;
  syncSurfaceControls();
}

const saveOutputPreference = debounce(output => {
  if (state.runtime.hosted) return;
  api("/api/preferences", { output }).catch(() => {});
}, 500);

async function showLog() {
  const button = $("#show-log-button");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/show-log", { output: state.output });
    toast(`Opened log: ${result.file.split(/[\\\\/]/).pop()}`);
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function updateNudgeUI() {
  const el = $("#layout-help");
  if (!el) return;
  if (state.dividerSegmentHover?.action === "blocked") {
    el.textContent = "That merge would make an irregular compartment. Compartments must stay rectangular.";
  } else if (state.dividerSegmentHits.length) {
    el.textContent = "Click a divider segment to combine compartments. Click a dashed segment to restore it. Compartments stay rectangular.";
  } else if (state.nudgeFeedback) {
    el.innerHTML = `<strong>Moved ${state.nudgeFeedback.amount}</strong> &nbsp;·&nbsp; Arrow: 1 mm | Shift: 10 mm | Ctrl: 0.1 mm`;
  } else {
    el.textContent = "Use Arrow keys or drag to move";
  }
}

function updatePreviewHelp(view) {
  const el = $("#preview-help");
  if (!el) return;
  if (view !== "2d") {
    el.textContent = "Drag to spin, or click the arrows for a 15° step (shift-click for 2°). Wheel to zoom, double-click to reset.";
  } else if (isNestEditWorkspaceActive()) {
    el.textContent = "Drag a source-outline point to reshape this Photo Nest. Use Add point or Delete point for outline detail.";
  } else if (state.draft?.kind === "nest" || state.design?.layout?.features?.[state.selected]?.kind === "nest") {
    el.textContent = "Drag the whole repeated Photo Nest group to move it; use the square to resize and circle to rotate.";
  } else {
    el.textContent = "Drag a part to move it; use the square to resize and circle to rotate.";
  }
}

// Advisory only: a user-changed wall that differs from known ordinary bins already
// in this Space. Never blocks the change and stays silent if the read fails.
async function maybeWarnSpaceWallMismatch(newWall) {
  if (state.folderMode !== "space" || !state.output) return;
  const spaceKey = () => state.activeSpaceId || state.output;
  const spaceAtStart = spaceKey();
  try {
    let bins;
    if (typeof DL !== "undefined" && DL.loaded && DL.output === DL.folder()) {
      bins = DL.bins;
    } else {
      const data = await DL.inventoryCall("/api/drawer/load", {}, { write: false });
      bins = data.bins;
    }
    const differs = (bins || []).some(row => {
      if (row?.kind !== "bin") return false;
      const wall = Number(row.wall);
      return row.wall != null && Number.isFinite(wall) && wall > 0 && Math.abs(wall - newWall) > 1e-6;
    });
    if (!differs) return;
    if (state.folderMode !== "space" || spaceKey() !== spaceAtStart) return;
    if (state.design?.box?.wall !== newWall) return;
    toast(
      "This Space already has bins with a different wall thickness. Connectors only fit bins with the same wall thickness. You can keep this thickness, but do not use one connector across different wall thicknesses.",
      false, 9000,
    );
  } catch (_error) {
    // Advisory warning only.
  }
}

let pendingDesignHistory = null;
let pendingWallMismatchCheck = false;
const applyChangedDesign = debounce(() => {
  const checkWall = pendingWallMismatchCheck;
  pendingWallMismatchCheck = false;
  if (state.designMutationBusy) {
    pendingDesignHistory = null;
    return;
  }
  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  pendingDesignHistory = null;
  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
    return;
  }

  if (checkWall) maybeWarnSpaceWallMismatch(state.design.box.wall);
  recordHistory(previousDesign);
  // Re-fit contents-driven drafts after the bin changes. Arbitrarily sized
  // parts keep the size the user chose; if the bin was made too small, the
  // automatic grow pass below restores enough room instead of trimming them.
  reflowDraftToBin(state.draft);
  // Rebuild the selected part first. Divider and Curved Scoop footprints are
  // derived from the bin, so previewing the resized bin before that rebuild
  // can briefly validate their old footprint and show a false fit error.
  // refreshDraft() finishes by refreshing the whole preview.
  if (state.draft) refreshDraft();
  else refreshPreview();
  if (state.binResizePending &&
      (state.draft || state.design.layout.features.length)) {
    enforceBinMinimumSoon();
  }
  state.binResizePending = false;
  state.binFootprintResizePending = false;
}, 280);

function cancelChangedDesignDebounce() {
  applyChangedDesign.cancel();
  pendingWallMismatchCheck = false;
}

// Re-evaluate contents-driven parts after the bin itself changes size. Plain
// sized blocks are deliberately untouched: their footprint is user intent,
// so a too-small bin must grow around them rather than cutting them down.
function reflowDraftToBin(one) {
  if (!one) return;
  if (one.kind === "cradle") return sizeCradleToItem(one);
  if (one.kind === "bore") return sizeBoreToGrid(one);
  if (one.kind === "post") return sizePostToRow(one);
  if (one.kind === "slot") return sizeSlotToBank(one);
}

function changedDesign(previousDesign = null) {
  // Width/length keyboard, wheel and blur handlers update state immediately so
  // their inline inside-dimension readout stays correct. Preserve the snapshot
  // from before the first such edit until the debounced history entry lands.
  if (previousDesign && pendingDesignHistory === null) {
    pendingDesignHistory = clone(previousDesign);
  }
  applyChangedDesign();
}

function markBinAxisManual(_axis) {
  state.binResizePending = true;
  state.binFootprintResizePending = true;
}

let pendingNudgeHistory = null;
let pendingNudgeDraft = null;
const commitNudge = debounce(async request => {
  if (request !== state.draftRequest || state.selected === null || !state.draft) return;
  const index = state.selected;
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const historySnapshot = pendingNudgeHistory || clone(state.design);
  const ownsRequest = () => request === state.draftRequest
    && state.selected === index
    && state.draft === draft
    && JSON.stringify(draft) === snapshot;
  try {
    const result = await api("/api/feature/apply", {
      design: state.design,
      feature: draft,
      index,
    });
    if (!ownsRequest()) return;
    state.design = result.design;
    pendingNudgeHistory = null;
    pendingNudgeDraft = null;
    recordHistory(historySnapshot);
    if (request !== state.draftRequest) return;
    state.selected = result.selected;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshPreview();
    if (request !== state.draftRequest) return;
    refreshDraft();
    renderLayout2D();
  } catch (error) {
    if (!ownsRequest()) return;
    const restoreDraft = pendingNudgeDraft;
    pendingNudgeHistory = null;
    pendingNudgeDraft = null;
    toast(error.message, true, 5000);
    if (restoreDraft || state.design?.layout?.features?.[index]) {
      state.draft = clone(restoreDraft || state.design.layout.features[index]);
      renderDraftFields();
      refreshDraft();
      renderLayout2D();
    }
  }
}, 200);

// The largest straight-sided rectangle that fits a bin's wavy cavity - the
// same number the engine's BoxSpec.usable_inside returns, recomputed here so
// the cradle auto-sizer never has to wait on a preview round-trip to know how
// much floor it has. Browser designs are always fused/removable (no cartridge)
// and the flat-inside band does not touch this rectangle, so the plain formula
// is exact.
function binInsideExtent(box) {
  const rules = state.catalog?.wall_rules || {};
  const wallDepth = number(box.wall, rules.default_mm ?? 0.8)
    * (rules.wall_depth_factor ?? 1.181);
  const trim = (rules.mating_gap_mm ?? 0.25)
    + 2 * wallDepth
    + 2 * (rules.wave_amplitude_mm ?? 0.4);
  return [Math.max(1, number(box.x) - trim), Math.max(1, number(box.y) - trim)];
}

function getInsideDimension(axis, val) {
  const key = axis === "x" ? "inside_x" : "inside_y";
  if (state.preview?.dimensions?.[key] != null && state.design?.box?.[axis] === val) {
    return state.preview.dimensions[key];
  }
  const box = state.design?.box || {
    x: val,
    y: val,
    wall: state.catalog?.wall_rules?.default_mm ?? 0.8,
  };
  const tempBox = { ...box, [axis]: val };
  const extents = binInsideExtent(tempBox);
  return Math.floor(axis === "x" ? extents[0] : extents[1]);
}

function formatDimField(axis) {
  const selector = axis === "x" ? "#x-size" : "#y-size";
  const input = $(selector);
  if (!input || document.activeElement === input) return;
  const val = state.design?.box?.[axis];
  if (val == null) return;
  const inside = getInsideDimension(axis, val);
  // Blurred state keeps the whole fit story short enough to stay in the field.
  // The unit count is the integer number of whole grid steps, from the
  // authoritative base unit.
  const unit = state.catalog?.base_unit || 8;
  const units = Math.round(val / unit);
  input.value = `${fmt(val)}mm (${units}X ${fmt(inside)}mm inside)`;
}

function formatHeightField() {
  const input = $("#z");
  if (!input || document.activeElement === input) return;
  const val = state.design?.box?.z;
  if (val == null) return;
  input.value = `${fmt(val)}mm`;
}

function setSidebarCollapsed(collapsed) {
  const shell = $("#app-shell");
  const button = $("#sidebar-toggle");
  shell.classList.toggle("sidebar-collapsed", collapsed);
  if (button) {
    button.setAttribute("aria-expanded", String(!collapsed));
    button.title = collapsed ? "Show controls" : "Hide controls";
    $("span", button).textContent = collapsed ? "Show controls" : "Hide controls";
  }
  try { localStorage.setItem("wavefinity-sidebar-collapsed", collapsed ? "1" : "0"); } catch (_error) {}
  requestAnimationFrame(() => { renderPreview3D(); renderLayout2D(); });
}

function wireSidebar() {
  const shell = $("#app-shell");
  const resizer = $("#sidebar-resizer");
  let drag = null;
  try {
    const savedWidth = Number(localStorage.getItem("wavefinity-sidebar-width"));
    if (Number.isFinite(savedWidth) && savedWidth >= 420) shell.style.setProperty("--sidebar-width", `${savedWidth}px`);
    setSidebarCollapsed(localStorage.getItem("wavefinity-sidebar-collapsed") === "1");
  } catch (_error) {
    setSidebarCollapsed(false);
  }
  $("#sidebar-toggle")?.addEventListener("click", () => setSidebarCollapsed(!shell.classList.contains("sidebar-collapsed")));
  resizer.addEventListener("pointerdown", event => {
    drag = { startX: event.clientX, width: $(".controls").getBoundingClientRect().width };
    resizer.classList.add("dragging");
    resizer.setPointerCapture(event.pointerId);
  });
  resizer.addEventListener("pointermove", event => {
    if (!drag) return;
    const width = Math.max(420, Math.min(window.innerWidth - 440, drag.width + event.clientX - drag.startX));
    shell.style.setProperty("--sidebar-width", `${width}px`);
  });
  resizer.addEventListener("pointerup", event => {
    if (!drag) return;
    const width = Math.round($(".controls").getBoundingClientRect().width);
    drag = null;
    resizer.classList.remove("dragging");
    if (resizer.hasPointerCapture(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    try { localStorage.setItem("wavefinity-sidebar-width", String(width)); } catch (_error) {}
  });
  resizer.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const current = $(".controls").getBoundingClientRect().width;
    const width = Math.max(420, Math.min(window.innerWidth - 440, current + (event.key === "ArrowRight" ? 24 : -24)));
    shell.style.setProperty("--sidebar-width", `${width}px`);
    try { localStorage.setItem("wavefinity-sidebar-width", String(Math.round(width))); } catch (_error) {}
  });
}

function setCameraView(view) {
  Object.assign(state.camera, CAMERA_VIEWS[view] || CAMERA_VIEWS.reset);
  $$('[data-camera-view]').forEach(button => button.classList.toggle("active", button.dataset.cameraView === view && view !== "reset"));
  renderPreview3D();
}

// A click-to-spin alternative to dragging: 15 degrees a step, or 2 with
// shift held for lining something up precisely.
function rotateCameraStep(direction, fine) {
  const step = fine ? 2 : 15;
  const camera = state.camera;
  if (direction === "left") camera.yaw -= step;
  else if (direction === "right") camera.yaw += step;
  else if (direction === "up") camera.elevation = Math.max(-89, Math.min(89, camera.elevation + step));
  else if (direction === "down") camera.elevation = Math.max(-89, Math.min(89, camera.elevation - step));
  $$('[data-camera-view]').forEach(button => button.classList.remove("active"));
  renderPreview3D();
}

// Bin/Interior/Xray each toggle their own state only - see the state.binVisible
// comment. Bin and Interior are ON by default, so their button shows the light
// red "off" treatment only when turned off; Xray is OFF by default, so its
// button shows the active/blue treatment only when turned on.
const PREVIEW_TOGGLE_KEYS = { bin: "binVisible", interior: "interiorVisible", xray: "xrayOn" };
function setPreviewToggle(name, on) {
  const key = PREVIEW_TOGGLE_KEYS[name];
  if (!key) return;
  state[key] = on;
  const button = $(`[data-camera-toggle="${name}"]`);
  if (button) {
    button.setAttribute("aria-pressed", String(on));
    const offIsNormal = name === "xray";
    button.classList.toggle("mode-toggle-off", !offIsNormal && !on);
    button.classList.toggle("active", offIsNormal && on);
  }
  renderPreview3D();
}

function wireCameraControls() {
  $$('[data-camera-view]').forEach(button => button.addEventListener("click", () => setCameraView(button.dataset.cameraView)));
  $$('[data-camera-toggle]').forEach(button => button.addEventListener("click", () => {
    const name = button.dataset.cameraToggle;
    const key = PREVIEW_TOGGLE_KEYS[name];
    setPreviewToggle(name, !state[key]);
  }));
  $$('[data-camera-zoom]').forEach(button => button.addEventListener("click", () => {
    state.camera.zoom = Math.max(.35, Math.min(4, state.camera.zoom * (button.dataset.cameraZoom === "in" ? 1.2 : 1 / 1.2)));
    renderPreview3D();
  }));
  $$('[data-camera-rotate]').forEach(button => button.addEventListener("click", event => {
    rotateCameraStep(button.dataset.cameraRotate, event.shiftKey);
  }));
}

function setLayoutOrientation(orientation) {
  state.layoutOrientation = orientation;
  $$('[data-layout-orientation]').forEach(button => {
    const active = button.dataset.layoutOrientation === orientation;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  renderLayout2D();
}

function eligibleGridDividerIndexes() {
  if (!state.design?.layout?.features) return [];
  return state.design.layout.features
    .map((feature, index) => dividerEligibleClient(
      index === state.selected && state.draft?.kind === "divider" ? state.draft : feature,
    ) ? index : null)
    .filter(Number.isInteger);
}

function updateDividerEditBreadcrumb() {
  const button = $("#divider-edit-breadcrumb");
  if (!button) return;
  const in3d = $('.canvas-wrap[data-canvas="3d"]')?.classList.contains("active");
  button.hidden = !in3d || eligibleGridDividerIndexes().length === 0;
}

async function openDividerSegmentEditor() {
  const eligible = eligibleGridDividerIndexes();
  if (!eligible.length) return;
  const index = eligible.includes(state.selected) ? state.selected : eligible[0];
  if (state.selected !== index) await selectedFeature(index);
  if (state.selected !== index || state.draft?.kind !== "divider") return;
  activatePreviewView("2d");
  renderLayout2D();
}

function activatePreviewView(view) {
  if (view === "drawer" && state.folderMode !== "space") {
    if (typeof SP !== "undefined") SP.offerSpacePlanning();
    return;
  }
  if (view === "drawer" && state.runtime.hosted && !state.browserFolder?.handle) {
    if (typeof SP !== "undefined") SP.showFolderAccessNeeded();
    return;
  }
  if (typeof DP !== "undefined") {
    if ((view === "2d" || view === "3d") && DP.spaceEditing()) DP.setMode("design");
    else if (view === "drawer") {
      if (DL.active) DP.setMode("space");
      else DP.enter("space");
    }
  }
  const tab = $(`.view-tab[data-view="${view}"]`);
  const canvasWrap = $(`.canvas-wrap[data-canvas="${view}"]`);
  if (!tab || !canvasWrap) return;
  $$(".view-tab").forEach(other => {
    const active = other === tab;
    other.classList.toggle("active", active);
    other.setAttribute("aria-selected", String(active));
    other.tabIndex = active ? 0 : -1;
  });
  $$(".canvas-wrap").forEach(wrap => wrap.classList.toggle("active", wrap === canvasWrap));
  canvasWrap.classList.remove("view-enter");
  void canvasWrap.offsetWidth;
  canvasWrap.classList.add("view-enter");
  updatePreviewHelp(view);
  updateDividerEditBreadcrumb();
  if (view === "2d") updateNudgeUI();
  requestAnimationFrame(() => view === "3d" ? renderPreview3D() : renderLayout2D());
}

function wireControls() {
  wireSidebar();
  wireCameraControls();
  wireNest2DControls();
  $$('[data-layout-orientation]').forEach(button =>
    button.addEventListener("click", () => setLayoutOrientation(button.dataset.layoutOrientation)));
  $("#divider-edit-breadcrumb")?.addEventListener("click", openDividerSegmentEditor);
  $$("button.section-heading").forEach(button => button.addEventListener("click", () => {
    const section = button.closest(".control-section");
    section.classList.toggle("open");
    button.setAttribute("aria-expanded", String(section.classList.contains("open")));
  }));

  $("#advanced-settings")?.addEventListener("change", event => {
    $("#advanced-build-settings").hidden = !event.target.checked;
  });

  ["#x-size", "#y-size", "#z", "#base-thickness", "#wall-thickness", "#part-name"]
    .forEach(selector => $(selector).addEventListener("input", () => {
      if (selector === "#wall-thickness") {
        const select = $(selector);
        select.dataset.customValue = select.value;
        const legacyOption = [...select.options].find(option =>
          option.textContent.endsWith("Existing custom")
        );
        if (legacyOption && legacyOption.value !== select.value) {
          legacyOption.remove();
          delete select.dataset.choices;
        }
        state.binResizePending = true;
        pendingWallMismatchCheck = true;
        syncWallControls();
      }
      if (selector === "#base-thickness") {
        $(selector).dataset.customValue = $(selector).value;
        state.binResizePending = true;
        syncBaseControls();
      }
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign();
    }));
  ["#surface-base-mode", "#surface-base-custom", "#surface-lightweight-base", "#surface-object-height"]
    .forEach(selector => $(selector)?.addEventListener(selector === "#surface-base-mode" ? "change" : "input", () => {
      if (!isSurfaceBinDesign()) return;
      resolveSurfaceBase(state.design, { fromForm: true });
      if (selector === "#surface-base-mode" || selector === "#surface-base-custom") {
        $("#z").value = fmt(state.design.box.z);
        state.binResizePending = true;
      }
      syncSurfaceControls();
      changedDesign();
    }));
  $("#lift-grabber-size").addEventListener("change", () => {
    syncLiftGrabberControls();
    if ($("#lift-grabber-size").value !== "no") promoteWallForLiftGrabbers();
    changedDesign();
  });
  $("#lift-grabber-location").addEventListener("change", changedDesign);

  const edgeMountChangeIds = [
    "#edge-mount-side",
    "#edge-mount-label-length-mode", "#edge-mount-label-projection",
    "#edge-mount-label-style", "#edge-mount-label-flip",
    "#edge-mount-standoff-ribs-enabled", "#edge-mount-standoff-rib-count-mode",
    "#edge-mount-hole-count", "#edge-mount-hole-orientation", "#edge-mount-access-diameter",
    "#edge-mount-spacing-mode",
  ];
  edgeMountChangeIds.forEach(selector => $(selector)?.addEventListener("change", () => {
    syncEdgeMountEditorVisibility();
    changedDesign();
  }));
  // Fix 058 Correction 1, C1.4B/E: the Label selector's None state and the
  // Screw Mounting checkbox's off state together replace the former pair of
  // top-level enable checkboxes. An Edge Mount already active in the saved
  // design must still keep at least one of the two on while its editor is
  // open - switching both off here reverts the just-made change and points
  // the user at Delete instead. A brand-new, not-yet-saved Edge Mount may
  // freely sit at Label=None + Screw Mounting off while the editor is open.
  $("#edge-mount-label-mode")?.addEventListener("change", event => {
    const holesEnabled = Boolean($("#edge-mount-holes-enabled")?.checked);
    if (state.modifierEditing === "edge_mount" && edgeMountActive() &&
        event.currentTarget.value === "none" && !holesEnabled) {
      event.currentTarget.value = edgeMountLabelMode(state.design.box.edge_mount);
      toast("Edge Mount needs Label or Screw Mounting. Use Delete to remove Edge Mount.", true, 6000);
      return;
    }
    syncEdgeMountEditorVisibility();
    changedDesign();
  });
  $("#edge-mount-holes-enabled")?.addEventListener("change", event => {
    const labelMode = $("#edge-mount-label-mode")?.value || "none";
    if (state.modifierEditing === "edge_mount" && edgeMountActive() &&
        labelMode === "none" && !event.currentTarget.checked) {
      event.currentTarget.checked = true;
      toast("Edge Mount needs Label or Screw Mounting. Use Delete to remove Edge Mount.", true, 6000);
      return;
    }
    syncEdgeMountEditorVisibility();
    changedDesign();
  });
  const edgeMountInputIds = [
    "#edge-mount-label-text", "#edge-mount-label-projection-mm", "#edge-mount-label-thickness-mm",
    "#edge-mount-label-depth", "#edge-mount-standoff-rib-count", "#edge-mount-screw-diameter", "#edge-mount-access-diameter",
    "#edge-mount-top-offset", "#edge-mount-spacing-mm",
  ];
  edgeMountInputIds.forEach(selector => $(selector)?.addEventListener("input", () => {
    syncEdgeMountEditorVisibility();
    changedDesign();
  }));

  ["#pegboard-cleat-x", "#pegboard-cleat-y"].forEach(selector => $(selector)?.addEventListener("change", () => {
    readPegboardMountForm(state.design);
    syncPegboardMountForm();
    changedDesign();
  }));
  ["#lid-configuration", "#lid-thickness", "#lid-handle-type", "#lid-handle-size",
   "#lid-handle-position", "#lid-label-enabled", "#lid-label-orientation", "#lid-label-style"]
    .forEach(selector => $(selector).addEventListener("change", () => {
      const previous = clone(state.design);
      readStackForm(state.design);
      normalizeStackSettings(state.design);
      clampSideOpeningTopForLid(state.design, true);
      syncLidForm();
      syncSideOpeningControls();
      populateWallChoices(state.design.box);
      populateBaseChoices(state.design.box);
      changedDesign(previous);
    }));
  $("#lid-label-text").addEventListener("input", () => {
    const previous = clone(state.design);
    readStackForm(state.design);
    seedPartNameFromLabel($("#lid-label-text").value);
    changedDesign(previous);
  });
  ["#side-opening-shape", "#side-opening-size"]
    .forEach(selector => $(selector)?.addEventListener("change", () => {
      const previous = clone(state.design);
      sideOpeningAdjustmentNote = "";
      readSideOpeningForm(state.design);
      syncSideOpeningControls();
      changedDesign(previous);
    }));
  ["#side-opening-from-bottom", "#side-opening-from-top"].forEach(selector =>
    $(selector)?.addEventListener("input", () => {
      const previous = clone(state.design);
      readSideOpeningForm(state.design);
      syncSideOpeningControls();
      changedDesign(previous);
    }));
  SIDE_OPENING_SIDE_IDS.forEach(side => {
    $(`#side-opening-${side}`)?.addEventListener("click", event => {
      const button = event.currentTarget;
      const active = button.getAttribute("aria-pressed") === "true";
      const selected = SIDE_OPENING_SIDE_IDS.filter(
        one => $(`#side-opening-${one}`)?.getAttribute("aria-pressed") === "true"
      );
      if (active && selected.length === 1) {
        toast("Side Openings need at least one side.", true, 4000);
        return;
      }
      button.setAttribute("aria-pressed", String(!active));
      const previous = clone(state.design);
      readSideOpeningForm(state.design);
      syncSideOpeningControls();
      changedDesign(previous);
    });
  });
  ["#x-size", "#y-size"].forEach(selector => {
    const axis = selector === "#x-size" ? "x" : "y";
    const input = $(selector);
    input.addEventListener("input", () => markBinAxisManual(axis));
    input.addEventListener("focus", () => {
      input.value = fmt(state.design.box[axis]);
      input.select();
    });
    input.addEventListener("blur", () => {
      const previousDesign = clone(state.design);
      const unit = state.catalog.base_unit;
      const rawVal = number(input.value, state.design.box[axis]);
      const snapped = snapToUnit(rawVal, unit);
      const prev = state.design.box[axis];
      if (snapped !== prev) markBinAxisManual(axis);
      state.design.box[axis] = snapped;
      formatDimField(axis);
      if (snapped !== prev) {
        flashField(input);
        state.canGenerate = false;
        updateGenerateAvailability();
        changedDesign(previousDesign);
      }
    });
    input.addEventListener("keydown", event => {
      if (event.key === "Enter") {
        input.blur();
      } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
        event.preventDefault();
        const previousDesign = clone(state.design);
        const unit = state.catalog.base_unit;
        const current = number(input.value, state.design.box[axis]);
        const delta = event.key === "ArrowUp" ? unit : -unit;
        const next = snapToUnit(current + delta, unit);
        markBinAxisManual(axis);
        input.value = String(next);
        input.select();
        state.design.box[axis] = next;
        state.canGenerate = false;
        updateGenerateAvailability();
        changedDesign(previousDesign);
      }
    });
    input.addEventListener("wheel", event => {
      event.preventDefault();
      const previousDesign = clone(state.design);
      const unit = state.catalog.base_unit;
      const current = number(input.value, state.design.box[axis]);
      const delta = event.deltaY < 0 ? unit : -unit;
      const next = snapToUnit(current + delta, unit);
      if (next === current && delta < 0) return;
      markBinAxisManual(axis);
      state.design.box[axis] = next;
      if (document.activeElement === input) {
        input.value = String(next);
        input.select();
      } else {
        formatDimField(axis);
      }
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }, { passive: false });
  });
  const heightInput = $("#z");
  heightInput.addEventListener("focus", () => {
    heightInput.value = fmt(state.design.box.z);
    heightInput.select();
  });
  heightInput.addEventListener("blur", () => {
    const previousDesign = clone(state.design);
    const next = normalizeBinDimension("z", heightInput.value, state.design.box.z);
    const changed = next !== state.design.box.z;
    state.design.box.z = next;
    formatHeightField();
    if (changed) {
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign(previousDesign);
    }
  });
  $("#scoop")?.addEventListener("change", () => {
    const previousDesign = clone(state.design);
    const previousCanGenerate = state.canGenerate;
    if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
      return;
    }

    recordHistory(previousDesign);
    refreshPreview();
    if (state.draft) refreshDraft();
  });
  ["#output-folder", "#keep-log", "#connector-tolerance", "#connector-length",
    "#connector-arm-thickness", "#connector-bin-a-height", "#connector-bin-b-height"]
    .forEach(selector => $(selector)?.addEventListener("change", () => {
      applyPendingLiveFormWithModifierConflictGuard();
    }));
  ["#connector-bin-a-height", "#connector-bin-b-height"].forEach(selector => {
    $(selector)?.addEventListener("input", () => {
      autoAdjustConnectorFields();
      applyPendingLiveFormWithModifierConflictGuard();
    });
  });
  $("#connector-height-mode").addEventListener("change", () => {
    if ($("#connector-height-mode").value === "different") {
      $("#connector-bin-a-height").value = fmt(state.design.box.z);
      if (!Number.isFinite(number($("#connector-bin-b-height").value, NaN))) {
        $("#connector-bin-b-height").value = fmt(state.design.box.z);
      }
    }
    syncConnectorHeightControls();
    if (!applyPendingLiveFormWithModifierConflictGuard()) return;
    renderConnectorReadout();
  });
  // The folder icon covers both picking a save folder and Space planning -
  // SP.open() already offers recent/new folders before it gets to Space setup.
  const outputFolderEl = $("#output-folder");
  if (outputFolderEl) {
    outputFolderEl.addEventListener("click", () => SP.open());
    outputFolderEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        SP.open();
      }
    });
  }
  $('label[for="output-folder"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    SP.open();
  });
  $("#output-folder-picker")?.addEventListener("click", () => SP.open());
  $("#show-log-button")?.addEventListener("click", showLog);

  const viewTabs = $$(".view-tab");
  const selectPreviewTab = view => {
    if (view === "drawer" && typedSpaceOrdinaryBin() && DP.mode === "design") return DP.selectMode("space");
    return activatePreviewView(view);
  };
  viewTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectPreviewTab(tab.dataset.view));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0
        : event.key === "End" ? viewTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      selectPreviewTab(viewTabs[targetIndex].dataset.view);
      viewTabs[targetIndex].focus();
    });
  });
  activatePreviewView((viewTabs.find(tab => tab.classList.contains("active")) || viewTabs[0]).dataset.view);

  // Editing a part: "Save Part" finalises it and returns to the 10-part
  // palette; "Delete Part" removes the part being edited and does the same.
  // Fix 034 I: the global top-right lifecycle/history controls are gone -
  // New Bin/Duplicate/Save/Load live at the bottom of the Designer instead
  // (Section E1), and Undo/Redo have no replacement (autosave + explicit
  // Duplicate cover their role). Internal history snapshot plumbing remains
  // for the algorithms that still use it (e.g. size-drag history).
  $("#designer-new-bin").addEventListener("click", designerNewBin);
  $("#designer-duplicate").addEventListener("click", designerDuplicate);
  $("#designer-save-file").addEventListener("click", saveDesign);
  $("#designer-open-file").addEventListener("change", openDesign);
  window.addEventListener("beforeunload", event => {
    const layoutUnsaved = typeof DL !== "undefined" && DL.active
      && (DL.dirty || DL.saving || Boolean(DL.savePromise) || DL.saveState === "error");
    if (designHasChanges() || layoutUnsaved) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  $("#update-banner-reload").addEventListener("click", () => location.reload(true));
  $("#print-with-connectors").addEventListener("click", event => printModel("all", event.currentTarget));
  $("#print-without-connectors").addEventListener("click", event => printModel("bin", event.currentTarget));
  $("#generate-all")?.addEventListener("click", () => generateParts("all"));
  $("#generate-bin")?.addEventListener("click", () => generateParts("bin"));
  $("#generate-connector")?.addEventListener("click", () => generateParts("connector"));
  wireGenerationDialog();
  $("#slicer-picker-button").addEventListener("click", browseSlicer);
  wireSceneInteraction($("#preview-3d"), state.camera, renderPreview3D);
  wireSupportLayoutDialog();
  wireLayoutInteraction();
  new ResizeObserver(() => renderPreview3D()).observe($("#preview-3d").parentElement);
  new ResizeObserver(() => renderLayout2D()).observe($("#preview-2d").parentElement);
}

function starterItem() {
  return {
    name: "Custom item", profile: "round", clearance: 0.4,
    segments: [{ length: 40, diameter: 6 }],
  };
}

function cancelPendingDraftWork() {
  refreshDraftSoon.cancel();
  commitNudge.cancel();
  pendingNudgeHistory = null;
  pendingNudgeDraft = null;
  state.kindRequest += 1;
  state.fitRequest += 1;
  state.nestTraceRequest += 1;
  state.nestRetraceRequest += 1;
  state.draftRequest += 1;
  state.previewRequest += 1;
  cancelPreviewWait();
}

function resetNestPhotoSession() {
  state.nestOutlineEditing = false;
  state.nestPhoto = null;
  state.nestOriginalImage = null;
  state.nestRectifiedImage = null;
  state.nestSensitivity = 50;
  state.nestCleanup = 50;
  state.nestPhotoOpacity = 45;
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestAcceptedCenterMm = null;
  state.nestTuneStatus = "";
  state.nestTraceResult = null;
  state.nestPaperCorners = null;
  state.nestCornerError = "";
  state.nestCornerBusy = false;
  state.nestCornerTipDismissed = false;
  state.nestOutlineTool = "select";
  state.nestAccessWarningShown = null;
  hideNestCornerMagnifier();
}

// Nothing selected, nothing shown as a live draft - the state on first load
// and after New/Open/a delete/a mode switch with nothing selected. A
// palette button never doubles as "still working on the last shape you
// looked at": if none of them is highlighted, nothing has been added yet.
function clearDraftSelection(resetLocks = true) {
  // Opening, resetting, deleting or changing layout mode starts a new editing
  // context. Invalidate every in-flight draft operation so an old palette
  // response, fit, photo upload, or auto-save cannot alter the new design.
  cancelPendingDraftWork();
  resetNestPhotoSession();
  state.draft = null;
  state.draftKind = null;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.draftTouched = false;
  state.edgeMountEditing = false;
  state.modifierEditing = null;
  state.pinnedZone = {};
  if (resetLocks) state.partZoneLocks = {};
  state.selected = null;
  state.nudgeFeedback = null;
  updateNudgeUI();
  $$(".support-choice").forEach(button => button.classList.remove("active"));
  $(".support-editor").hidden = true;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  ["#lid-option", "#inside-handles-option", "#side-openings-option"].forEach(
    selector => { const panel = $(selector); if (panel) panel.hidden = true; },
  );
  $("#draft-status").textContent = "";
  $("#draft-status").classList.remove("error");
  updateDraftStatusColor(null);
  updateInteriorModeVisibility();
  updateSelectionButtons();
  syncNest2DWorkspace();
}

function pickKind(kind) {
  const info = partInfo(kind);
  const isModifier = info?.capabilities?.includes("box_modifier");
  if (!isModifier && state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour)) {
    toast("Photo Nest designs use Duplicate for another group; other interior parts are unavailable.", true, 5000);
    return;
  }
  if (b4bEnabled() && !b4bPartAllowed(kind)) return;
  if (b4bEnabled() && kind === "divider") {
    const existing = state.design?.layout?.features?.findIndex(
      one => one.kind === "divider"
    );
    if (Number.isInteger(existing) && existing >= 0) {
      selectedFeature(existing);
      return;
    }
  }
  state.paletteBrowsing = false;
  if (isModifier) {
    if (partAtLimit(info)) return openModifier(kind);
    return addModifier(kind);
  }
  updateInteriorModeVisibility(true);
  selectKind(kind);
}

async function selectEdgeMount(fromPlaced = false) {
  return openModifier("edge_mount", fromPlaced);
}

function insideHandlesActive(design = state.design) {
  return Boolean(design?.box?.lift_grabbers?.enabled);
}

const INSIDE_HANDLES_REMOVABLE_MESSAGE =
  "Inside Grip is built into the bin wall, so it isn’t available with Removable insert. Choose Fused into box to use Inside Grip.";

async function openModifier(kind, fromPlaced = false) {
  if (b4bEnabled()) return;
  if (!BOX_MODIFIER_KINDS.has(kind) || !edgeMountAvailable()) return;
  if (state.draft && !(await guardDraftSwitch())) return;
  resetNestPhotoSession();
  if (state.modifierEditing && state.modifierEditing !== kind &&
      !commitEdgeMountFormBeforeSwitch()) {
    return;
  }
  cancelPendingDraftWork();
  state.paletteBrowsing = false;
  state.draft = null;
  state.draftKind = kind;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.draftTouched = false;
  state.selected = null;
  state.edgeMountEditing = kind === "edge_mount";
  state.modifierEditing = kind;
  $(".support-editor").hidden = false;
  $("#draft-fields").hidden = true;
  $("#edge-mount-editor").hidden = kind !== "edge_mount";
  const panelByKind = {
    lid_stacking: "#lid-option",
    inside_handles: "#inside-handles-option",
    side_openings: "#side-openings-option",
  };
  for (const [oneKind, selector] of Object.entries(panelByKind)) {
    const panel = $(selector);
    if (panel) panel.hidden = oneKind !== kind;
  }
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === kind));
  const info = partInfo(kind);
  syncDraftEditorIdentity(kind, info);
  if (kind === "edge_mount") {
    populateEdgeMountChoices();
    syncEdgeMountControls();
  } else if (kind === "lid_stacking") {
    syncLidForm();
    $("#lid-option-panel").hidden = false;
  } else if (kind === "inside_handles") {
    $("#lift-grabber-size").value = state.design.box.lift_grabbers?.size || "medium";
    $("#lift-grabber-location").value = state.design.box.lift_grabbers?.location || "sides";
    syncLiftGrabberControls();
  } else if (kind === "side_openings") {
    syncSideOpeningControls();
    $("#side-openings-panel").hidden = false;
  }
  renderPlaced();
  updateSelectionButtons();
}

async function addModifier(kind) {
  if (b4bEnabled()) return;
  if (kind === "inside_handles" && state.design.layout.mode !== "fused") {
    toast(INSIDE_HANDLES_REMOVABLE_MESSAGE, true, 6500);
    return;
  }
  if (kind === "edge_mount") {
    const previous = clone(state.design);
    const rules = state.catalog?.edge_mount || {};
    const side = state.design.box.edge_mount?.side || "front";
    const normalDepth = ["front", "back"].includes(side)
      ? number(state.design.box.y) : number(state.design.box.x);
    const projection = Math.min(
      number(rules.max_projection_mm, 200),
      Math.max(number(rules.min_projection_mm, 5), normalDepth / 3),
    );
    // This Space's remembered Edge Mount settings (label plate thickness,
    // type, ribs, screw settings...) seed the new option; text is always
    // blank and the label starts on with screw mounting off.
    const seed = spaceModifierDefaults("edge_mount") || {};
    const seededProjection = Number(seed.label_projection_mm);
    state.design.box.edge_mount = {
      ...EDGE_MOUNT_DEFAULTS,
      ...(state.design.box.edge_mount || {}),
      label_type: "separate",
      standoff_ribs_enabled: true,
      label_projection_mm: projection,
      access_diameter_mm: resolvedEdgeMountAccessDiameter(
        state.design.box.edge_mount || EDGE_MOUNT_DEFAULTS,
      ),
      ...seed,
      ...(Number.isFinite(seededProjection) ? {
        label_projection_mm: Math.min(
          number(rules.max_projection_mm, 200),
          Math.max(number(rules.min_projection_mm, 5), seededProjection),
        ),
      } : {}),
      // Fix 058 Correction 1, C1.4B: a new Edge Mount defaults its Label
      // selector to None (and Screw Mounting stays off) rather than opening
      // pre-enabled - text is always blank regardless.
      label_enabled: false,
      holes_enabled: false,
      label_text: "",
    };
    recordHistory(previous);
    syncForm();
    await openModifier(kind);
    await refreshPreview();
    return;
  }
  const previous = clone(state.design);
  const seed = spaceModifierDefaults(kind) || {};
  if (kind === "lid_stacking") {
    if (seed.lid) {
      state.design.box.lid = { ...seed.lid, enabled: true };
      delete state.design.box.stack;
    } else {
      state.design.box.stack = { mode: "direct" };
    }
  } else if (kind === "inside_handles") {
    const rules = state.catalog?.lift_grabbers || {};
    state.design.box.lift_grabbers = {
      enabled: true,
      size: seed.size || rules.default_size || "medium",
      location: seed.location || rules.default_location || "sides",
    };
  } else if (kind === "side_openings") {
    const eligible = SIDE_OPENING_SIDE_IDS.filter(side => sideOpeningEligibleSide(side));
    const rememberedSides = Array.isArray(seed.sides)
      ? seed.sides.filter(side => eligible.includes(side)) : [];
    const sides = rememberedSides.length
      ? rememberedSides
      : ["left", "right"].filter(side => eligible.includes(side));
    if (!sides.length && eligible.length) sides.push(eligible[0]);
    if (!sides.length) {
      toast("No bin wall is available for Side Openings.", true, 5500);
      return;
    }
    state.design.box.side_openings = {
      ...SIDE_OPENING_DEFAULTS, ...seed, enabled: true, sides,
    };
    clampSideOpeningTopForLid(state.design, true);
  }
  recordHistory(previous);
  syncForm();
  await openModifier(kind);
  refreshPreview();
}

async function removeModifier(kind) {
  if (!modifierIsActive(kind)) {
    clearDraftSelection();
    return;
  }
  if (state.draft && !(await guardDraftSwitch())) return;
  if (!beginDesignMutation()) return;
  try {
    const previous = clone(state.design);
    if (kind === "lid_stacking") {
      delete state.design.box.stack;
      delete state.design.box.lid;
      normalizeStackSettings(state.design, { restoreDefaults: true, flash: true });
    } else if (kind === "inside_handles") {
      state.design.box.lift_grabbers = { enabled: false, size: "medium", location: "sides" };
    } else if (kind === "side_openings") {
      state.design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };
    } else if (kind === "edge_mount") {
      state.design.box.edge_mount = { ...EDGE_MOUNT_DEFAULTS };
    }
    const result = await api("/api/design/validate", { design: state.design });
    state.design = result.design;
    recordHistory(previous);
    state.paletteBrowsing = true;
    clearDraftSelection();
    // Forms must match the validated design before any later form read, or a
    // stale handle/opening control would silently re-add the deleted option.
    syncForm();
    renderPlaced();
    await refreshPreview();
    toast(`${partInfo(kind)?.title || "Option"} deleted.`);
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
}

function commitEdgeMountFormBeforeSwitch() {
  if (!state.modifierEditing) return true;

  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;

  cancelChangedDesignDebounce();
  pendingDesignHistory = null;

  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) {
    return false;
  }

  recordHistory(previousDesign);
  return true;
}

async function flushVisibleDesignEditsBeforeModeSwitch() {
  if (state.designMutationBusy) return false;
  if (state.draft && !(await guardDraftSwitch())) return false;
  if (state.modifierEditing) return commitEdgeMountFormBeforeSwitch();

  const previousDesign = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;
  cancelChangedDesignDebounce();
  pendingDesignHistory = null;
  if (!applyLiveFormWithModifierConflictGuard(previousDesign, previousCanGenerate)) return false;
  recordHistory(previousDesign);
  return true;
}
window.flushVisibleDesignEditsBeforeModeSwitch = flushVisibleDesignEditsBeforeModeSwitch;

function syncDraftEditorIdentity(kind, info) {
  const isNest = kind === "nest";
  const title = $("#draft-title");
  const description = $("#draft-description");

  title.textContent = info.title;
  description.textContent = info.description;

  title.hidden = isNest || kind === "bore";
  // Fix 058 Correction 1, C1.4A: the palette keeps its short description for
  // discoverability, but the Edge Mount editor's own Label/Screw Mounting
  // hierarchy makes the redundant "Add a label and/or screw mounting..."
  // sentence unnecessary once the editor is open.
  // Fix 060 A: the Lid & Stacking editor's own Configuration/Lid/Handle/Label
  // hierarchy makes the redundant "Add a lid or make matching bins stack
  // together." sentence unnecessary once the editor is open; the palette
  // tile keeps it for discoverability.
  description.hidden = isNest || kind === "edge_mount" || kind === "lid_stacking";

  $(".support-editor")?.classList.toggle("nest-editor", isNest);
}

async function selectKind(kind, reset = false) {
  if (b4bEnabled() && !b4bPartAllowed(kind)) return;
  if (kind === "divider" && dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  // Re-picking the shape already open keeps the same draft, so there is nothing
  // to lose - skip the guard in that case. Anything else replaces the draft, so
  // give the user the chance to keep unsaved work first.
  const keepsSameDraft = !reset && state.draft?.kind === kind;
  if (!keepsSameDraft && !(await guardDraftSwitch())) return;
  if (!keepsSameDraft && state.draft?.kind === "nest") resetNestPhotoSession();
  if (!commitEdgeMountFormBeforeSwitch()) return;
  state.edgeMountEditing = false;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  // The palette request is independent of preview/draft requests. Without its
  // own token, a slower earlier click could overwrite a newer shape choice.
  // A new palette choice also makes every pending edit to the prior draft
  // obsolete. Otherwise its auto-save could land after this new choice.
  cancelPendingDraftWork();
  const request = ++state.kindRequest;
  updateInteriorModeVisibility(true);
  state.draftKind = kind;
  state.selected = null;
  state.draftIsNew = true;
  state.draftSourceIndex = null;
  state.draftAutoCommit = kind !== "nest";
  $(".support-editor").hidden = false;
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === kind));
  const info = partInfo(kind);
  syncDraftEditorIdentity(kind, info);
  updateSelectionButtons();
  if (!reset && state.draft?.kind === kind) {
    renderDraftFields();
    refreshDraft();
    return;
  }
  $("#draft-status").textContent = "Loading shape…";
  try {
    const result = await api("/api/feature/default", {
      design: state.design,
      kind,
      along: "x",
      item: info.flags.item ? starterItem() : null,
    });
    if (request !== state.kindRequest) return;
    // A newly added part starts from this Space's remembered settings for its
    // kind (size, count, options - never position or text). An existing part
    // is opened from the bin's own exact design instead (selectedFeature).
    state.draft = state.folderMode === "space"
      ? seedFeatureFromPartDefaults(result.feature, state.spacePartDefaults?.[kind])
      : result.feature;
    state.draftTouched = false;
    state.pinnedZone = {};
    state.draftResolvedOptions = result.resolved_options || {};
    // What the engine started this text at, so the Part Name is only ever
    // seeded from lettering the user actually typed - never the placeholder.
    state.draftStartingText = result.feature?.options?.text ?? null;
    if (kind === "bore") sizeBoreToGrid(state.draft);
    renderDraftFields();
    updateSelectionButtons();

    // Auto-save the new part immediately and treat it as a saved part we are editing
    if (kind !== "nest") {
      try {
        const applyResult = await api("/api/feature/apply", {
          design: state.design,
          feature: state.draft,
          index: null,
        });
        if (request !== state.kindRequest) return;
        const previousDesign = clone(state.design);
        state.design = applyResult.design;
        seedPartNameFromText(state.draft);
        recordHistory(previousDesign);
        state.selected = applyResult.selected;
        state.draftIsNew = false;
        state.draftTouched = false;
        if (Number.isInteger(applyResult.selected)) state.draftSourceIndex = applyResult.selected;
        if (state.selected !== null && state.design.layout.features[state.selected]) {
          state.draft = clone(state.design.layout.features[state.selected]);
        }
        renderPlaced();
        updateSelectionButtons();
      } catch (applyErr) {
        $("#draft-status").textContent = applyErr.message;
        $("#draft-status").classList.add("error");
      }
    }
    refreshDraft();
  } catch (error) {
    if (request !== state.kindRequest) return;
    $("#draft-status").textContent = error.message;
    toast(error.message, true);
  }
}

async function selectedFeature(index, force = false) {
  if (index === null || index < 0 || index >= state.design.layout.features.length) return;
  if (!force && index === state.selected) return;
  // Don't drop unsaved work on the part currently open without asking first.
  if (!force && !(await guardDraftSwitch())) return;
  const selected = state.design.layout.features[index];
  if (state.draft?.kind === "nest" || selected?.kind === "nest") resetNestPhotoSession();
  if (!commitEdgeMountFormBeforeSwitch()) return;
  cancelPendingDraftWork();
  state.edgeMountEditing = false;
  $("#draft-fields").hidden = false;
  $("#edge-mount-editor").hidden = true;
  state.paletteBrowsing = false;
  state.selected = index;
  state.nudgeFeedback = null;
  updateNudgeUI();
  // A fresh selection starts the outline editor's viewport fitted again,
  // rather than carrying over whatever zoom/pan the previous part left set.
  state.nestViewZoom = 1;
  state.nestViewPanX = 0;
  state.nestViewPanY = 0;
  state.draft = clone(state.design.layout.features[index]);
  state.nestOutlineEditing = false;
  state.draftTouched = false;
  state.draftAutoCommit = true;
  state.draftIsNew = false;
  state.draftSourceIndex = index;
  state.pinnedZone = state.partZoneLocks[index] ||= {};
  if (AUTO_FOOTPRINT_KINDS.has(state.draft.kind)) {
    // Once a part is placed, its stored footprint is user-owned. Locks remain
    // session-only, but every reopened part starts protected on both axes.
    state.pinnedZone.width = true;
    state.pinnedZone.depth = true;
  }
  state.draftResolvedOptions = {};
  if (state.draft.kind === "bore") sizeBoreToGrid(state.draft);
  state.draftKind = state.draft.kind;
  updateInteriorModeVisibility(true);
  $(".support-editor").hidden = false;
  $$(".support-choice").forEach(button => button.classList.toggle("active", button.dataset.kind === state.draftKind));
  const info = partInfo();
  syncDraftEditorIdentity(state.draftKind, info);
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
  refreshDraft();
  renderLayout2D();
}

function field(label, key, value, options = {}) {
  const classes = options.wide ? "wide" : "";
  const type = options.type || "number";
  const attrs = type === "number" ? `step="${options.step || "0.1"}"` : "";
  const min = options.min !== undefined ? ` min="${escapeHtml(options.min)}"` : "";
  const max = options.max !== undefined ? ` max="${escapeHtml(options.max)}"` : "";
  const placeholder = options.placeholder ? ` placeholder="${escapeHtml(options.placeholder)}"` : "";
  const tip = options.tip ? ` title="${escapeHtml(options.tip)}"` : "";
  const data = options.dataAttribute
    ? `${options.dataAttribute}="${escapeHtml(key)}"`
    : `data-draft="${escapeHtml(key)}"`;
  return `<label class="${classes}"${tip}><span class="field-label">${escapeHtml(label)}${options.unit ? `<span class="unit">${escapeHtml(options.unit)}</span>` : ""}</span>
    <input type="${type}" ${data} value="${escapeHtml(value ?? "")}" ${attrs}${min}${max}${placeholder}>
  </label>`;
}

// The Divider's own wall thickness is a real numeric option (no "standard"
// sentinel like the bin wall), but it draws from the same preset catalog so
// the two controls can never drift apart.
function dividerThicknessField(value, key = "option:thickness") {
  const choices = wallPresetChoices();
  const current = fmt(number(value, 1.6));
  const isPreset = choices.some(choice => fmt(choice.value) === current);
  const optionsHtml = choices.map(choice => {
    const choiceValue = fmt(choice.value);
    return `<option value="${choiceValue}" ${choiceValue === current ? "selected" : ""}>${number(choice.value).toFixed(1)} mm — ${escapeHtml(choice.label)}</option>`;
  }).join("");
  // A saved design keeps whatever thickness it was made with: the preset list
  // is what a *new* choice may be, not a migration of existing geometry.
  const customOption = isPreset ? ""
    : `<option value="${current}" selected>${current} mm — Existing custom</option>`;
  return `<label><span class="field-label">Wall thickness</span>
    <select data-draft="${key}">${optionsHtml}${customOption}</select>
  </label>`;
}

function scoopDepthField(key, value, options = {}) {
  return field("Scoop height", key, value, {
    unit: "% of bin height", step: "1", min: "1", max: "100",
    tip: options.tip || "The scoop always spans the full usable bin width and starts at the front floor edge.",
    dataAttribute: options.dataAttribute,
  });
}

// Compact inline checkbox - the space-saving replacement for the full-width
// check-card. `help` becomes a hover tooltip rather than always-on body text.
// `key` is the full data-draft attribute (e.g. "option:slope_base").
function toggle(key, title, help, on, options = {}) {
  const classes = ["editor-toggle"];
  if (options.wide) classes.push("wide");
  const tip = help ? ` title="${escapeHtml(help)}"` : "";
  return `<label class="${classes.join(" ")}"${tip}>
    <input type="checkbox" data-draft="${key}" ${on ? "checked" : ""}>
    <span>${escapeHtml(title)}</span>
  </label>`;
}

// The two fixed-size hex-bit profiles. Selecting one locks the hole to a
// 1/4-inch bit and drives the hole depth so the bit stands well proud.
const HEX_BIT_PROFILES = {
  hex_bit_short: { label: "Hex bit – short", length: 25, diameter: 6.35, clearance: 0.25 },
  hex_bit_long: { label: "Hex bit – long", length: 38, diameter: 6.35, clearance: 0.25 },
};
const isHexBitProfile = profile => Object.prototype.hasOwnProperty.call(HEX_BIT_PROFILES, profile);

function resolvedDraftCount(one) {
  if (one.count != null) return Math.max(1, Math.round(number(one.count, 1)));
  const [x0, y0, x1, y1] = one.zone;
  const width = x1 - x0, depth = y1 - y0;
  const options = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  const along = one.along === "y" ? "y" : "x";
  const across = along === "x" ? depth : width;
  if (one.kind === "cradle") {
    const diameter = number(one.item?.segments?.[0]?.diameter, 6);
    const wall = number(resolved.rib_thickness, Math.max(1.6, diameter * .25));
    const spacing = Math.max(0, number(options.spacing ?? resolved.spacing, 0));
    const body = diameter + wall;
    const pitch = diameter + wall / 2 + spacing;
    return Math.max(1, Math.floor((across - body + 1e-6) / pitch) + 1);
  }
  if (one.kind === "post") {
    const diameter = number(options.diameter ?? resolved.diameter, 12);
    const spacing = Math.max(0, number(options.spacing ?? resolved.spacing, 4));
    const countX = Math.max(1, Math.floor((width - diameter + 1e-6) / (diameter + spacing)) + 1);
    const countY = Math.max(1, Math.floor((depth - diameter + 1e-6) / (diameter + spacing)) + 1);
    return countX * countY;
  }
  if (one.kind === "slot") {
    const thickness = number(options.thickness ?? resolved.thickness, 4);
    const wall = number(options.wall ?? resolved.wall, 1.6);
    const angle = Math.abs(number(options.angle ?? resolved.angle, 20)) * Math.PI / 180;
    const pitch = (thickness + wall) / Math.cos(angle);
    return Math.max(1, Math.floor((across - 2 * wall - thickness / Math.cos(angle) + 1e-6) / pitch) + 1);
  }
  return Math.max(1, Math.round(number(options.count ?? resolved.count, 3)));
}

function plainCheckbox(key, title, on, options = {}) {
  const classes = ["checkbox-row"];
  if (options.wide) classes.push("wide");
  const tip = options.help ? ` title="${escapeHtml(options.help)}"` : "";
  const attribute = options.dataAttribute || "data-draft";
  return `<label class="${classes.join(" ")}"${tip}>
    <input type="checkbox" ${attribute}="${escapeHtml(key)}" ${on ? "checked" : ""}>
    <span>${escapeHtml(title)}</span>
  </label>`;
}

// Text location and whatever sits beside it share one row: the rim shelf
// side when the text is on the rim, otherwise `companion` (the text itself),
// so the location is never left on a half-empty row.
function textPlacementFields(levelKey, sideKey, level, side = "back", companion = "") {
  const sides = [["front", "Front"], ["back", "Back"], ["left", "Left"], ["right", "Right"]];
  const pickedSide = sides.some(([value]) => value === side) ? side : "back";
  let html = `<label>Text location<select data-draft="${escapeHtml(levelKey)}">
    <option value="base" ${level === "base" ? "selected" : ""}>On base</option>
    <option value="rim" ${level === "rim" ? "selected" : ""}>Rim level</option>
  </select></label>`;
  if (level === "rim") {
    html += `<label>Rim shelf<select data-draft="${escapeHtml(sideKey)}">
      ${sides.map(([value, label]) => `<option value="${value}" ${pickedSide === value ? "selected" : ""}>${label}</option>`).join("")}
    </select></label>`;
  } else {
    html += companion;
  }
  return `<div class="pair">${html}</div>`;
}

function dividerScoopDefaultDepth() {
  const scoop = partInfo("scoop");
  return scoop?.fields?.find(field => field.key === "depth")?.default ?? "";
}

// Photo Nest Access state has exactly one writer per value. Finger access owns
// lift_assist (auto / none / finger_grasp), the Push Out toggle owns
// lift_assist = "push_out", and Location / Push at own their own positions.
// A value is written only when its own control is what changed, so an
// unrelated edit can never re-read a select that cannot represent push_out.
function applyNestAccessOptions(options, changed, get) {
  for (const key of ["lift_assist", "finger_position", "push_position"]) {
    if (changed !== `option:${key}`) continue;
    const value = get(`option:${key}`);
    if (value !== undefined) options[key] = value;
  }
}

// The Push Out toggle: on writes push_out; off returns to a legal Automatic.
function setNestPushOut(options, on) {
  options.lift_assist = on ? "push_out" : "auto";
}

// Finger access is replaced by Push Out while that is on, so it is not shown.
function nestFingerAccessVisible(holderStyle, assist) {
  return !(assist === "push_out" && holderStyle === "raised_wall");
}

// Photo Nest's editor: Tool, Holder, Finger access, Raised Wall advanced,
// Fit, Bin and Outline (spec section 45). Broken out of renderDraftFields
// only because it is long, not because it is reused elsewhere.
function renderNestFields(one) {
  const opt = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  const val = (key, fallback) => (opt[key] !== undefined && opt[key] !== null ? opt[key] : (resolved[key] ?? fallback));
  const selected = (value, actual) => value === actual ? "selected" : "";
  const holderStyle = String(val("holder_style", "raised_wall"));
  const assist = String(val("lift_assist", "auto"));
  const isPushOut = assist === "push_out";
  const fingerPosition = String(val("finger_position", "sides"));
  const cavityMode = String(val("cavity_depth_mode", "auto"));
  // Tool thickness is the one measurement the user actually has to supply -
  // show it blank (never a fabricated "8") until it is explicitly stored,
  // even though every other computed default below still needs some number
  // to illustrate against.
  const hasMeasuredThickness = opt.tool_thickness != null || opt.depth != null;
  const toolThickness = number(opt.tool_thickness ?? opt.depth ?? resolved.tool_thickness, 8);
  let html = "";

  html += `<div class="photo-upload wide">
    <label class="button secondary photo-button" for="nest-photo-input">
      ${one.contour ? "Replace photo" : "Upload part photo"}
    </label>
    <input id="nest-photo-input"
           type="file"
           accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp">
    <details>
      <summary>Photo requirements</summary>
      <ul>
        <li>Entire US Letter (8.5 × 11 in) reference sheet visible</li>
        <li>Camera directly overhead</li>
        <li>Part lies flat</li>
        <li>Plain, high-contrast background preferred</li>
      </ul>
    </details>
  </div>`;

  const shownRotation = ((number(one.rotation, 0) % 360) + 360) % 360;
  const standardRotation = [0, 90, 180, 270].some(value => Math.abs(value - shownRotation) < 1e-6);
  const spacing = opt.repeat_spacing_percent ?? 0;
  html += `<fieldset class="wide editor-group"><legend>Copies</legend>
    <div class="pair">
      <label>Quantity<input type="number" min="1" max="20" step="1" data-draft="nest-count" value="${Math.max(1, Math.min(20, Math.round(number(one.count, 1))))}"></label>
      <label>Orientation<select data-draft="nest-orientation">
        ${standardRotation ? "" : `<option value="${escapeHtml(String(one.rotation))}" selected disabled>Current ${fmt(one.rotation)}° (existing)</option>`}
        ${[[0, "As Scanned"], [90, "90°"], [180, "180°"], [270, "270°"]].map(([value, label]) => `<option value="${value}" ${standardRotation && shownRotation === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>
    </div>
    ${plainCheckbox("nest-alternate", "Flip every other one", one.alternate_ends === true, { wide: true, help: "Turns every second copy 180° end-for-end." })}
    <label class="wide">Space between nests<select data-draft="option:repeat_spacing_percent">
      ${[[-100, "-100% (Minimum)"], [-75, "-75%"], [-50, "-50%"], [-25, "-25%"], [0, "Auto"], [25, "+25%"], [50, "+50%"], [75, "+75%"], [100, "+100%"]].map(([value, label]) => `<option value="${value}" ${Number(spacing) === value ? "selected" : ""}>${label}</option>`).join("")}
    </select></label>
    ${one.contour ? `<div class="pair"><button type="button" class="button secondary" data-action="duplicate-nest">Duplicate</button><button type="button" class="button secondary" data-action="edit-nest-outline">Edit outline</button></div>` : ""}
  </fieldset>`;

  const autoCavity = 0.6 * toolThickness;
  const cavityDepth = cavityMode === "manual"
    ? number(val("cavity_depth", autoCavity), autoCavity)
    : autoCavity;
  const cavityUnavailable = !hasMeasuredThickness && cavityMode !== "manual";

  // Holder: the Nest type owns what follows, so it comes first.
  html += `<div class="editor-group"><span class="editor-group-label">Holder</span>
    <label>Nest type
      <select data-draft="option:holder_style">
        <option value="recessed" ${selected("recessed", holderStyle)}>Recessed Cavity</option>
        <option value="raised_wall" ${selected("raised_wall", holderStyle)}>Raised Wall</option>
      </select>
    </label>`;

  html += `<div class="nest-primary-row">`;

  html += field(
    "Tool thickness",
    "option:tool_thickness",
    hasMeasuredThickness ? fmt(toolThickness) : "",
    {
      unit: "mm",
      step: "0.5",
      min: "0.5",
      placeholder: "required",
      tip: "The one measurement Wavefinity cannot work out from the photo.",
    },
  );

  if (holderStyle === "recessed") {
    html += `<div class="nest-cavity-column">`;

    html += field(
      "Cavity depth",
      "option:cavity_depth",
      cavityUnavailable ? "" : fmt(cavityDepth),
      {
        unit: "mm",
        step: "0.1",
        min: "0.1",
        placeholder: cavityUnavailable ? "needs Tool thickness" : undefined,
        tip: "Editing this switches to Manual so later Tool thickness changes stop recalculating it.",
      },
    );

    html += `<div class="nest-cavity-status">
      <span>${cavityMode === "manual"
        ? "Manual"
        : cavityUnavailable
          ? "Needs Tool thickness"
          : "Auto — 60%"}</span>
      <button type="button"
              class="button secondary"
              data-action="nest-cavity-auto"
              ${cavityMode === "manual" ? "" : "disabled"}>
        Reset to 60%
      </button>
    </div>`;

    html += `</div>`;
  }

  html += `</div></div>`;

  // Access. Push Out replaces Finger access, so while it is on the Finger
  // access selector is not shown at all - it cannot even represent push_out.
  html += `<div class="editor-group"><span class="editor-group-label">Access</span>`;
  if (nestFingerAccessVisible(holderStyle, assist)) {
    html += `<label>Finger access
      <select data-draft="option:lift_assist">
        <option value="auto" ${selected("auto", isPushOut ? "" : assist)}>Automatic</option>
        <option value="none" ${selected("none", assist)}>Off</option>
        <option value="finger_grasp" ${selected("finger_grasp", assist)}>Custom</option>
      </select>
    </label>`;
    if (assist === "finger_grasp") {
      html += `<div class="pair">`;
      html += `<label>Location
        <select data-draft="option:finger_position">
          <option value="sides" ${selected("sides", fingerPosition)}>Sides</option>
          <option value="top_bottom" ${selected("top_bottom", fingerPosition)}>Ends</option>
          <option value="both" ${selected("both", fingerPosition)}>Both</option>
        </select>
      </label>`;
      html += field("Finger width", "option:finger_width",
        fmt(val("finger_width", resolved.finger_width ?? 25)),
        { unit: "mm", step: "1", min: "12", max: "40" });
      html += `</div>`;
    }
  }

  // Raised Wall advanced.
  if (holderStyle === "raised_wall") {
    html += `<details class="wide nest-advanced" ${isPushOut ? "open" : ""}><summary>Raised Wall advanced</summary>`;
    html += toggle("nest-push-out", "Push Out",
      "Raises the tool on a shaped floor with one selected end low, for pressing the opposite end up. Replaces Finger access while on.",
      isPushOut);
    if (isPushOut) {
      html += `<div class="pair">`;
      html += `<label>Push at
        <select data-draft="option:push_position">
          <option value="right" ${selected("right", val("push_position", "right"))}>Right</option>
          <option value="left" ${selected("left", val("push_position", "right"))}>Left</option>
          <option value="top" ${selected("top", val("push_position", "right"))}>Top</option>
          <option value="bottom" ${selected("bottom", val("push_position", "right"))}>Bottom</option>
        </select>
      </label>`;
      html += field("Push area", "option:push_area", fmt(val("push_area", 30)),
        { unit: "%", step: "5", min: "15", max: "40" });
      html += field("Push depth", "option:push_depth", fmt(val("push_depth", 4)),
        { unit: "mm", step: "0.5", min: "2", max: "8" });
      html += `</div>`;
    }
    html += `</details>`;
  }
  html += `</div>`;

  // Fit.
  html += `<div class="editor-group"><span class="editor-group-label">Fit</span>`;
  html += field(
    "Fit clearance",
    "option:clearance",
    fmt(val("clearance", 0.6)),
    { unit: "mm", step: "0.1", min: "0" },
  );
  html += `</div>`;

  // Bin. Read straight from the stored option, never the resolved fallback:
  // a legacy design with no stored preference must show as off here, not as
  // on just because it happens to behave in a similar grow-only way.
  html += `<div class="editor-group"><span class="editor-group-label">Bin</span>`;
  html += toggle("option:auto_size", "Automatically size footprint to tool",
    "Grows or shrinks the bin Width and Length to fit this Nest and keeps it centered. "
    + "Bin Height stays at the height you set.",
    opt.auto_size === true, { wide: true });
  html += `</div>`;

  // Outline shape (Soften outline, manual point editing, zoom/pan, Finish
  // Editing) lives in the 2D view's own Outline editor panel now - editing
  // the outline is done looking directly at it, not from this sidebar.
  if (one.contour) {
    html += `<p class="photo-measurement">Outline ready — open the 2D view's Outline editor to reshape it.</p>`;
  }
  return html;
}

// Informational-only readout of how far the draft's own built geometry rises
// above the bin rim, straight from the preview's real mesh bounds - never
// recomputed here. Only ever a note, never a warning: a legal fused holder
// above the rim (Post, Cradle, Bore, Pocket, Slot, Steps, Raised-Wall Photo
// Nest) still generates fine.
function updateDraftOverhangNote() {
  const note = $('[data-draft-overhang]', $("#draft-fields"));
  if (!note) return;

  const overhang = number(state.preview?.draft_overhang_mm, 0);

  note.hidden = overhang <= 0.05;
  note.textContent = note.hidden
    ? ""
    : `Extends ${fmt(overhang)} mm above rim`;
}

// Bore style and sizing model (Fix 068). One persisted Style word and two
// persisted sizing modes replace the old wall_style / auto_base / auto_height /
// auto_grid state. Mirrors normalize_bore_style() / normalize_bore_modes() in
// organizer_inserts/_bore.py.
const BORE_STYLES = [
  ["base_straight", "Base - Straight Walls"],
  ["base_wavy", "Base - Wavy Walls"],
  ["walls_straight", "Straight Walls Only"],
  ["walls_wavy", "Wavy Walls Only"],
];
const BORE_LEGACY_STYLES = { full_base: "base_straight", wavy_base: "base_wavy" };
const boreWallsOnly = style => style === "walls_straight" || style === "walls_wavy";
const boreWavy = style => style === "base_wavy" || style === "walls_wavy";

function normalizeBoreStyle(style, wallStyle) {
  const word = String(style ?? "");
  if (BORE_STYLES.some(([value]) => value === word)) return word;
  if (BORE_LEGACY_STYLES[word]) return BORE_LEGACY_STYLES[word];
  if (word === "wall_only") return wallStyle === "straight" ? "walls_straight" : "walls_wavy";
  return "base_straight";
}

function boreStyleOf(one) {
  return normalizeBoreStyle(
    one?.options?.bore_style ?? state.draftResolvedOptions?.bore_style,
    one?.options?.wall_style,
  );
}

// Width / Length sizing: Walls Only has no Base fields, so it only chooses
// between Manually and sizing the bin to itself (its default).
function boreXyMode(one) {
  const style = boreStyleOf(one);
  const walls = boreWallsOnly(style);
  const mode = one?.options?.xy_size_mode;
  const allowed = walls ? ["manual", "bin_to_bore"] : ["manual", "bore_to_bin", "bin_to_bore"];
  return allowed.includes(mode) ? mode : (walls ? "bin_to_bore" : "manual");
}

function boreHeightMode(one) {
  const mode = one?.options?.height_size_mode;
  return ["manual", "bore_to_bin", "bin_to_bore"].includes(mode) ? mode : "manual";
}

function wallStyleSelect(style) {
  return `<label><span class="field-label">Walls</span><select data-draft="option:wall_style">
    <option value="wavy" ${style === "wavy" ? "selected" : ""}>Wavy Walls</option>
    <option value="straight" ${style === "wavy" ? "" : "selected"}>Straight Walls</option>
  </select></label>`;
}

// Match Pocket's backend envelope and Bore Wall Only's outward wave reach.
// The catalog's wall_rules is the one authoritative owner of the wave
// contract - see sizeBoreToGrid, which already consumes it the same way.
function pocketWallReach(wall, style) {
  if (style !== "wavy") return wall;
  const wallRules = state.catalog?.wall_rules || {};
  const amplitude = number(wallRules.wave_amplitude_mm, 0.4);
  const depthFactor = number(wallRules.wall_depth_factor, 1.181);
  const waveNoiseFloor = 1e-4;  // ensure wavy troughs never self-intersect
  return 2 * amplitude + wall * depthFactor + waveNoiseFloor;
}

function renderDraftFields() {
  if (!state.draft) return;
  const info = partInfo();
  const one = state.draft;
  const zone = one.zone;
  const width = zone[2] - zone[0];
  const depth = zone[3] - zone[1];
  // Bore and Photo Nest carry their own identity inside their controls, so the
  // grey panel blurb just wastes space there.
  const descEl = $("#draft-description");
  if (descEl) descEl.hidden = one.kind === "bore" || one.kind === "nest";
  let html = "";
  // Keys pulled up into the "Repeats" cluster, so the body loop skips them.
  const repeatKeys = new Set();
  // Fix 061 F1: Post and Steps describe the physical part before its repeat
  // layout, so their Repeats group is held back until the part fields exist.
  let repeatsHtml = "";
  let stepsSizeHtml = "";
  let cradleToolHtml = "";
  const editorGroup = (label, inner) =>
    `<div class="editor-group"><span class="editor-group-label">${label}</span>${inner}</div>`;
  if (one.kind === "scoop") {
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, "depth");
    const shown = explicit ? one.options.depth : state.draftResolvedOptions?.depth ?? 60;
    html += scoopDepthField("option:depth", shown);
  }
  if (one.kind === "nest") {
    html += renderNestFields(one);
  }
  if (info.flags.text) {
    const textLevel = one.options?.level === "rim" ? "rim" : "base";
    const textInput = `<input type="text" maxlength="80" data-draft="option:text" value="${escapeHtml(one.options?.text ?? "")}" placeholder="${textLevel === "rim" ? "e.g. M3 BOLTS" : "e.g. M3"}">`;
    let textGroup = `<label>Text${textInput}</label>`;
    let placementGroup = textPlacementFields(
      "option:level", "option:rim_side", textLevel, one.options?.rim_side, "",
    );
    if (textLevel === "base") {
      const capShown = one.options?.cap_height ?? state.draftResolvedOptions?.cap_height ?? "";
      const depthShown = one.options?.depth ?? state.draftResolvedOptions?.depth ?? 0.4;
      textGroup += `<div class="pair">${field("Letter height", "option:cap_height", capShown === "" ? "" : fmt(capShown), { unit: "mm", step: "0.5" })}${field("Depth", "option:depth", fmt(depthShown), { unit: "mm", step: "0.1" })}</div>`;
      textGroup += `<fieldset><legend>Text style</legend><div class="segmented two">
        <label><input type="radio" name="draft-text-style" value="inlaid" ${one.options?.raised === true ? "" : "checked"}><span>Inlaid</span></label>
        <label><input type="radio" name="draft-text-style" value="raised" ${one.options?.raised === true ? "checked" : ""}><span>Raised</span></label>
      </div></fieldset>`;
      placementGroup += `<fieldset><legend>Turn</legend><div class="segmented four">
        ${[0, 1, 2, 3].map(turn => `<label><input type="radio" name="draft-turns" value="${turn}" ${(number(one.options?.quarter_turns, 0) % 4) === turn ? "checked" : ""}><span>${turn * 90}°</span></label>`).join("")}
      </div></fieldset>`;
      placementGroup += toggle("option:auto", "Place it for me",
        "Keeps it centred where it fits, moving around the other interior parts as they change. Turn this off to put it exactly where you want.",
        one.options?.auto === true);
    }
    html += editorGroup("Text", textGroup);
    html += editorGroup("Placement", placementGroup);
  }
  if (info.flags.size && one.kind !== "cradle" && !(one.kind === "text" && one.options?.level === "rim")) {
    const isPocket = one.kind === "pocket";
    const isBore = one.kind === "bore";
    const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
    const reach = isPocket ? pocketWallReach(wall, one.options?.wall_style ?? state.draftResolvedOptions?.wall_style) : 0;
    const shownWidth = isPocket ? Math.max(0.1, width - 2 * reach) : width;
    const shownDepth = isPocket ? Math.max(0.1, depth - 2 * reach) : depth;
    // A bore's footprint reads Width x Length, matching Pocket and the item terms.
    // Slot and base Text each also carry their own "Depth" field (slot cut / letter
    // sink), so the footprint dimension is named apart to avoid two "Depth" boxes.
    const widthLabel = isPocket ? "Inside width" : one.kind === "slot" ? "Rack width" : "Width";
    const depthLabel = isPocket || isBore ? (isPocket ? "Inside length" : "Length")
      : one.kind === "slot" ? "Rack length"
      : one.kind === "text" ? "Text box depth"
      : "Depth";
    if (isBore) {
      const draftProfile = one.item?.profile || "round";
      const hexBit = isHexBitProfile(draftProfile);
      const boreItem = one.item || starterItem();
      const boreFirst = boreItem.segments[0] || { length: 40, diameter: 6 };
      // An option field always shows its current resolved number. An absent
      // stored option remains automatic and will update when its inputs do.
      const optionField = (key, label, opts = {}) => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        const value = explicit ? one.options[key]
          : state.draftResolvedOptions?.[key] ?? info.fields.find(f => f.key === key)?.default;
        const shown = opts.transform ? opts.transform(value) : value;
        const { transform, ...fieldOpts } = opts;
        return field(label, `option:${key}`, shown, fieldOpts);
      };
      const gridField = (key, label) => field(label, `option:${key}`,
        one.options?.[key] ?? state.draftResolvedOptions?.[key] ?? 1, { step: "1", min: "1" });
      // Diameter is locked to the preset for a hex-bit profile.
      const diameterField = hexBit
        ? `<label><span class="field-label">Diameter<span class="unit">mm</span></span>
            <input type="number" value="${HEX_BIT_PROFILES[draftProfile].diameter}" disabled></label>`
        : field("Diameter", "item_diameter", fmt(boreFirst.diameter), { unit: "mm" });
      const boreProfiles = [
        ["round", "Round"], ["hex", "Hex"], ["square", "Diamond"],
        ["square_axis", "Square"],
        ["hex_bit_short", HEX_BIT_PROFILES.hex_bit_short.label],
        ["hex_bit_long", HEX_BIT_PROFILES.hex_bit_long.label],
      ];
      // One persisted Style word (Fix 068): Base styles are a solid block the
      // holes are cut into; Walls Only builds just the perimeter sleeve(s)
      // rising from the floor.
      const boreStyle = boreStyleOf(one);
      const wallsOnly = boreWallsOnly(boreStyle);
      const xyMode = boreXyMode(one);
      const heightMode = boreHeightMode(one);
      const modeSelect = (label, key, value, choices) => `<label><span class="field-label">${label}</span><select data-draft="option:${key}">
        ${choices.map(([choice, text]) => `<option value="${choice}" ${value === choice ? "selected" : ""}>${text}</option>`).join("")}
      </select></label>`;
      const styleField = `<label><span class="field-label">Style</span><select data-draft="option:bore_style">
        ${BORE_STYLES.map(([value, label]) => `<option value="${value}" ${boreStyle === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;
      const boreWallShown = one.options?.wall ?? state.draftResolvedOptions?.wall ?? state.design?.box?.wall;
      const shapeField = `<label><span class="field-label">Shape</span><select data-draft="profile">
        ${boreProfiles.map(([value, label]) => `<option value="${value}" ${draftProfile === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;

      html += `<div class="bore-group wide">
        <span class="bore-group-label">Type</span>
        <div class="bore-group-fields">${styleField}</div>
      </div>`;

      // Base: the zone the Bore occupies and the hole grid that fills it. Sizing
      // is one persistent mode per relationship (never a one-shot button); the
      // X / Y counts are always explicit.
      const xySelect = wallsOnly
        ? modeSelect("Set bin width / length", "xy_size_mode", xyMode, [
          ["manual", "Manually"], ["bin_to_bore", "Auto size bin to bore"]])
        : modeSelect("Set base width / length", "xy_size_mode", xyMode, [
          ["manual", "Manually"], ["bore_to_bin", "Auto size bore to bin"],
          ["bin_to_bore", "Auto size bin to bore"]]);
      const showXy = !wallsOnly && xyMode === "manual";
      const showHeight = heightMode !== "bore_to_bin";
      html += `<div class="bore-group wide">
        <span class="bore-group-label">Base</span>
        <div class="bore-group-fields">
          <div class="bore-auto-row">
            ${xySelect}
            ${showXy
              ? field("Width", "width", fmt(shownWidth), { unit: "mm", step: "1" }) +
                field("Length", "depth", fmt(shownDepth), { unit: "mm", step: "1" })
              : ""}
          </div>
          <div class="bore-auto-row">
            ${modeSelect("Set height", "height_size_mode", heightMode, [
              ["manual", "Manually"], ["bore_to_bin", "Auto size bore to bin"],
              ["bin_to_bore", "Auto size bin to bore"]])}
            ${showHeight ? optionField("height", "Height", { unit: "mm", step: "0.5" }) : ""}
          </div>
          <div class="bore-auto-row">
            ${gridField("columns", "X count")}${gridField("rows", "Y count")}
          </div>
        </div>
      </div>`;

      // Hole: everything about the holes cut into that block.
      html += `<div class="bore-group wide">
        <span class="bore-group-label">Hole</span>
        <div class="bore-group-fields bore-hole-fields">
          ${diameterField}
          ${shapeField}
          ${wallsOnly ? "" : optionField("depth", "Depth", { unit: "mm", step: "0.5" })}
          ${wallsOnly ? dividerThicknessField(boreWallShown, "option:wall") : ""}
          ${hexBit || boreStyle !== "base_straight" ? "" : optionField("angle", "Tool angle", { unit: "°", step: "1", min: "20", max: "90", transform: value => 90 - number(value, 0), tip: "90° is upright. Smaller angles lean the tool toward the selected direction." })}
          ${hexBit || boreStyle !== "base_straight" || number(one.options?.angle ?? state.draftResolvedOptions?.angle, 0) <= 1e-9 ? "" : `<label><span class="field-label">Angle towards</span><select data-draft="option:angle_towards">
            ${[["back", "Back"], ["front", "Front"], ["left", "Left"], ["right", "Right"]].map(([value, label]) => `<option value="${value}" ${(one.options?.angle_towards || (one.along === "y" ? "front" : "left")) === value ? "selected" : ""}>${label}</option>`).join("")}
          </select></label>`}
        </div>
      </div>`;
    } else if (isPocket || one.kind === "slot") {
      // Audit 006 J1: Pocket and Slot Rack group their related controls into
      // the same `.editor-group` language Bore/Divider already use, instead
      // of scattering Width/Length from Height/Wall/geometry across the
      // renderer's default field order. Every data-draft key, default source,
      // unit, min/step rule and autosize action below is identical to the
      // plain fields this replaces - only the markup/grouping changed.
      const isSlot = one.kind === "slot";
      const fieldFor = (key, label, opts = {}) => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        const def = info.fields.find(f => f.key === key)?.default;
        const value = explicit ? one.options[key] : state.draftResolvedOptions?.[key] ?? def;
        return field(label, `option:${key}`, value, opts);
      };
      const wallStyleShown = one.options?.wall_style ?? state.draftResolvedOptions?.wall_style
        ?? info.fields.find(f => f.key === "wall_style")?.default;
      const wallField = fieldFor("wall", "Wall", isSlot ? { unit: "mm" } : { unit: "mm", min: "0.4" });
      const wallsField = wallStyleSelect(wallStyleShown);
      const sizeFieldsHtml = field(widthLabel, "width", fmt(shownWidth), { unit: "mm", step: "1" })
        + field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" })
        + (isSlot ? "" : fieldFor("depth", "Pocket depth", { unit: "mm", step: "0.5", min: "0.1" }))
        + fieldFor("height", "Height", isSlot ? { unit: "mm" } : { unit: "mm", step: "0.5", min: "1.0" });
      html += `<div class="editor-group"><span class="editor-group-label">${isSlot ? "Rack size" : "Pocket size"}</span><div class="draft-triple">${sizeFieldsHtml}</div></div>`;
      if (isSlot) {
        const geometryFieldsHtml = fieldFor("thickness", "Slot width", { unit: "mm" })
          + fieldFor("depth", "Slot depth", { unit: "mm" })
          + fieldFor("angle", "Tilt angle", { unit: "°" });
        html += `<div class="editor-group"><span class="editor-group-label">Slot geometry</span><div class="draft-triple">${geometryFieldsHtml}</div></div>`;
      }
      html += `<div class="editor-group"><span class="editor-group-label">Walls</span><div class="pair">${wallField}${wallsField}</div></div>`;
    } else {
      const footprint = field(widthLabel, "width", fmt(shownWidth), { unit: "mm", step: "1" })
        + field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" });
      if (one.kind === "text") html += editorGroup("Footprint", `<div class="pair">${footprint}</div>`);
      else if (one.kind === "steps") stepsSizeHtml += footprint;
      else html += footprint;
    }
  }
  // Repeats: how many, how far apart, which way they run - one cluster, in
  // reading order, instead of Quantity / spacing / Runs along scattered apart.
  if (info.flags.qty || info.flags.along) {
    const htmlBeforeRepeats = html;
    html = "";
    // The part's own spacing / gap belongs with Quantity, not up in the body.
    let repeatFieldsHtml = "";
    for (const option of info.fields) {
      if (!["spacing", "floor_gap"].includes(option.key)) continue;
      if (info.kind === "cradle" && option.key === "floor_gap") continue;
      repeatKeys.add(option.key);
      // Grid dividers space their walls evenly on both axes; no spacing field.
      if (info.kind === "divider") continue;
      const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
      const shown = explicit ? one.options[option.key]
        : state.draftResolvedOptions?.[option.key] ?? option.default;
      const fo = {};
      if (info.kind === "cradle" && option.key === "spacing") fo.min = 0;
      if (["cradle", "post"].includes(info.kind) && option.key === "spacing") fo.unit = "mm";
      repeatFieldsHtml += field(option.label, `option:${option.key}`, shown, fo);
    }

    if (info.kind === "divider") {
      // Two quantities instead of one direction: walls across X and walls
      // across Y, together making a grid of compartments.
      const opt = one.options || {};
      const legacyN = one.count == null ? 1 : Math.max(1, number(one.count, 1));
      const gx = (opt.count_x != null && opt.count_x !== "") ? opt.count_x
        : (one.along === "y" ? legacyN : 0);
      const gy = (opt.count_y != null && opt.count_y !== "") ? opt.count_y
        : (one.along === "x" ? legacyN : 0);
      const shownGx = (number(gx, 0) === 0) ? "" : gx;
      const shownGy = (number(gy, 0) === 0) ? "" : gy;
      const shownThickness = opt.thickness ?? state.draftResolvedOptions?.thickness ?? 1.6;
      const shownHeight = opt.height ?? state.draftResolvedOptions?.height ?? "";
      const wallStyle = opt.wall_style ?? state.draftResolvedOptions?.wall_style ?? "straight";
      html += `<div class="editor-group divider-layout"><span class="editor-group-label">Divider layout</span><div class="pair">
        ${field("X count", "option:count_x", shownGx, { min: "0", step: "1", tip: "Walls dividing the bin left to right. 0 for none." })}
        ${field("Y count", "option:count_y", shownGy, { min: "0", step: "1", tip: "Walls dividing the bin front to back. 0 for none." })}
        ${dividerThicknessField(shownThickness)}
        ${field("Height", "option:height", shownHeight, { unit: "mm", step: "0.5" })}
        ${wallStyleSelect(wallStyle)}
      </div></div>`;
    } else {
      const autoPost = info.kind === "post" && one.count == null;
      const directionLabel = info.kind === "steps" ? "Shelf direction" : "Runs along";
      const runsAlong = info.flags.along && !["divider", "bore"].includes(info.kind) && !autoPost
        ? `<fieldset><legend>${directionLabel}</legend><div class="segmented two">
          <label><input type="radio" name="draft-along" value="x" ${one.along === "x" ? "checked" : ""}><span>X direction</span></label>
          <label><input type="radio" name="draft-along" value="y" ${one.along === "y" ? "checked" : ""}><span>Y direction</span></label>
        </div></fieldset>`
        : "";
      const hasOrientationControls = Boolean(info.flags.qty || repeatFieldsHtml || runsAlong || info.flags.alternate);
      if (hasOrientationControls) {
        html += `<div class="editor-group"><span class="editor-group-label">${info.flags.qty ? "Repeats" : "Orientation"}</span>`;
        // A part with no spacing field of its own (Slot Rack) would leave
        // Quantity alone on its row: Runs along takes the second column instead.
        const alongInPair = Boolean(info.flags.qty && !repeatFieldsHtml && runsAlong);
        if (info.flags.qty) {
          const quantityLabel = info.kind === "steps" ? "Number of steps" : "Quantity";
          const autoState = info.kind !== "steps" && one.count == null;
          html += `<div class="pair"><label><span class="field-label">${quantityLabel}${autoState ? '<span class="unit">Auto</span>' : ""}</span><div class="input-with-button">
            <input type="number" min="1" step="1" data-draft="count" value="${resolvedDraftCount(one)}">
            ${info.kind === "steps" ? "" : `<button type="button" class="button secondary" data-action="auto-count">Auto</button>`}
          </div></label>${repeatFieldsHtml}${alongInPair ? runsAlong : ""}</div>`;
          if (autoPost) html += `<p class="inline-help">Auto fills the available area with posts.</p>`;
          if (info.kind === "cradle") {
            const item = one.item || starterItem();
            const first = item.segments[0] || { length: 40, diameter: 6 };
            const tip = "Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool.";
            cradleToolHtml = editorGroup("Tool", `<div class="pair">${field("Length", "item_length", fmt(first.length), { unit: "mm", step: "1", tip })}${field("Diameter", "item_diameter", fmt(first.diameter), { unit: "mm", step: "1", tip })}</div>`);
          }
        } else if (repeatFieldsHtml) {
          html += `<div class="pair">${repeatFieldsHtml}</div>`;
        }
        if (info.flags.alternate) {
          html += `<label>End layout<select data-draft="alternate_ends">
            <option value="aligned" ${one.alternate_ends === true ? "" : "selected"}>Aligned</option>
            <option value="alternate" ${one.alternate_ends === true ? "selected" : ""}>Alternate ends</option>
          </select></label>`;
        }
        if (runsAlong && !alongInPair) html += runsAlong;
        if (info.flags.alternate) {
          // One field, two readings. Alternate ends on: the clearance kept at each
          // run end (writes end_margin). Off: a signed slide of the whole row along
          // the bin (writes run_offset). Each key keeps its own last value.
          const alternating = one.alternate_ends === true;
          const key = alternating ? "end_margin" : "run_offset";
          const label = alternating ? "From ends" : "Offset from center";
          const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
          const shown = explicit
            ? one.options[key]
            : alternating
            ? state.draftResolvedOptions?.end_margin ?? 10
            : 0;
          const tip = alternating
            ? "Share of the run kept clear at each end. Larger pulls the alternating troughs toward the middle; smaller pushes them to the ends."
            : "Slides the trough along the bin from centre, as a share of the room to the wall. Positive one way, negative the other; 0 stays centred.";
          html += field(label, `option:${key}`, fmt(shown), { unit: "%", step: "1", tip });
        }
        html += `</div>`;
      }
    }
    repeatsHtml = html;
    html = htmlBeforeRepeats + cradleToolHtml;
  }
  if (!["post", "steps"].includes(info.kind)) html += repeatsHtml;
  if (info.flags.item && !["bore", "cradle"].includes(one.kind)) {
    // A bore's Diameter / Profile / Clearance are drawn in the "Hole" group above.
    const item = one.item || starterItem();
    const first = item.segments[0] || { length: 40, diameter: 6 };
    const isCradle = one.kind === "cradle";
    // Cradles use measured dimensions. Photo Nest has no item fields.
    const measuredStep = isCradle ? "1" : undefined;
    const lengthTip = isCradle
      ? "Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool."
      : undefined;
    html += field("Length", "item_length", fmt(first.length), { unit: "mm", step: measuredStep, tip: lengthTip });
    html += field("Diameter", "item_diameter", fmt(first.diameter), { unit: "mm", step: measuredStep, tip: lengthTip });
    if (!isCradle) {
      const profiles = [["round", "Round"], ["hex", "Hex"], ["square", "Square"]];
      html += `<label>Shape<select data-draft="profile">
        ${profiles.map(([value, label]) => `<option value="${value}" ${item.profile === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;
      html += field("Fit clearance", "clearance", fmt(item.clearance ?? 0.4), { unit: "mm" });
    }
  }
  let bodyHtml = "";
  for (const option of info.fields) {
    if (one.kind === "text" && one.options?.level === "rim") continue;
    // Rendered together as the one "% from end / Offset from center" field
    // beneath Runs along, above.
    if (option.key === "end_margin" || option.key === "run_offset") continue;
    // Pulled up into the "Repeats" cluster (spacing / floor gap).
    if (repeatKeys.has(option.key)) continue;
    // Every bore field is drawn up with the footprint above; nothing is left
    // for this loop.
    if (info.kind === "bore") continue;
    // Nest's fit numbers ride beside Lift assist; Text's letter size/depth ride
    // with the Text field.
    if (info.kind === "nest" && (option.key === "clearance" || option.key === "smoothing")) continue;
    if (info.kind === "text" && (option.key === "cap_height" || option.key === "depth")) continue;
    // Rendered by the Divider slope block below only for Crossbars.
    if (option.key === "bottom_supports") continue;
    // Slope and angle are handled specifically for divider below.
    if (info.kind === "divider" && ["bottom_angle", "angle", "thickness", "height", "wall_style"].includes(option.key)) continue;
    // The scoop depth field is rendered with its own % unit and help text above.
    if (info.kind === "scoop") continue;
    // Audit 006 J1: Pocket size/geometry/Walls are already rendered as
    // grouped fields above (Inside width/length, Pocket depth, Height, Wall,
    // Walls) - nothing is left for this loop.
    if (info.kind === "pocket" && ["height", "wall", "wall_style", "depth"].includes(option.key)) continue;
    // Audit 006 J1: Rack size/Slot geometry/Walls are already rendered above
    // (Rack width/length, Height, Slot width/depth, Tilt angle, Wall, Walls).
    if (info.kind === "slot" && ["height", "wall", "wall_style", "depth", "thickness", "angle"].includes(option.key)) continue;
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
    const shown = explicit ? one.options[option.key]
      : state.draftResolvedOptions?.[option.key] ?? option.default;
    if (option.key === "wall_style") {
      bodyHtml += wallStyleSelect(shown);
      continue;
    }
    // Mouse-wheel / spinner steps: lean and slope a whole degree, width
    // half a mm.
    const stepFor = { angle: "1" };
    if (info.kind === "divider") {
      stepFor.thickness = "0.5";
      stepFor.bottom_angle = "1";
    }
    if (info.kind === "post") {
      stepFor.height = "1.0";
    }
    if (info.kind === "pocket") {
      stepFor.height = "0.5";
      stepFor.depth = "0.5";
      stepFor.wall = "0.1";
      stepFor.rounding = "0.1";
    }
    const fieldOpts = {};
    if (stepFor[option.key]) fieldOpts.step = stepFor[option.key];
    if (info.kind === "cradle" && option.key === "spacing") fieldOpts.min = 0;
    if (info.kind === "pocket" && option.key === "rounding") fieldOpts.min = 0;
    if (info.kind === "pocket" && option.key === "wall") fieldOpts.min = 0.4;
    if (info.kind === "pocket" && option.key === "depth") fieldOpts.min = 0.1;
    if (info.kind === "pocket" && option.key === "height") fieldOpts.min = 1.0;
    const labels = {
      pocket: { depth: "Pocket depth" },
      slot: { depth: "Slot depth", thickness: "Slot width", angle: "Tilt angle" },
    };
    const mmKinds = new Set(["post", "pocket", "slot", "steps"]);
    if (mmKinds.has(info.kind) && option.key !== "angle") fieldOpts.unit = "mm";
    if (info.kind === "slot" && option.key === "angle") fieldOpts.unit = "°";
    bodyHtml += field(labels[info.kind]?.[option.key] || option.label, `option:${option.key}`, shown, fieldOpts);
  }
  // Three-across for the kinds whose leftover body fields would otherwise leave
  // a half-empty row (matches the Width / Length / Height row at the top).
  if (info.kind === "post") {
    html += editorGroup("Post", `<div class="draft-triple">${bodyHtml}</div>`) + repeatsHtml;
  } else if (info.kind === "steps") {
    html += editorGroup("Steps size", `<div class="pair">${stepsSizeHtml}${bodyHtml}</div>`) + repeatsHtml;
  } else if (bodyHtml) {
    html += ["pocket", "slot"].includes(info.kind)
      ? `<div class="draft-triple">${bodyHtml}</div>`
      : bodyHtml;
  }
  if (info.kind === "divider") {
    const opt = one.options || {};
    const scoopConfig = opt.scoop && typeof opt.scoop === "object" && !Array.isArray(opt.scoop)
      ? opt.scoop : null;
    const hasSlope = !scoopConfig && (
      opt.slope_base === true || (opt.bottom_angle !== undefined && Number(opt.bottom_angle) !== 0)
    );

    const bottomMode = scoopConfig ? "scoop" : hasSlope ? "slope" : "flat";
    html += `<div class="editor-group"><span class="editor-group-label">Bottom</span>`;
    html += `<label class="wide">Bottom<select data-draft="option:bottom_mode">
      <option value="flat" ${bottomMode === "flat" ? "selected" : ""}>Flat</option>
      <option value="slope" ${bottomMode === "slope" ? "selected" : ""}>Sloped</option>
      <option value="scoop" ${bottomMode === "scoop" ? "selected" : ""}>Curved scoop</option>
    </select></label>`;

    if (hasSlope) {
      const explicitAngle = Object.prototype.hasOwnProperty.call(opt, "bottom_angle");
      const angleVal = explicitAngle ? opt.bottom_angle : (number(state.draftResolvedOptions?.bottom_angle, 0) || 20);
      const angleNum = number(angleVal, 0);
      const useBars = angleNum !== 0 && opt.minimal_bottom === true;
      const construction = useBars ? "crossbars" : "solid";
      html += `<div class="pair divider-slope-options"><div class="divider-slope-fields">`;
      html += field("Slope angle", "option:bottom_angle", angleVal, { step: "1", unit: "°" });
      html += `<label>Slope construction<select data-draft="option:slope_construction">
        <option value="solid" ${construction === "solid" ? "selected" : ""}>Solid</option>
        <option value="crossbars" ${construction === "crossbars" ? "selected" : ""}>Crossbars</option>
      </select></label>`;
      if (angleNum !== 0) {
        if (useBars) {
          const explicitBars = Object.prototype.hasOwnProperty.call(opt, "bottom_supports");
          const bars = explicitBars
            ? opt.bottom_supports
            : state.draftResolvedOptions?.bottom_supports ?? 3;
          html += field("Crossbars", "option:bottom_supports", bars, { step: "1" });
        }
      }
      html += `</div><div class="divider-slope-toggles">`;
      html += toggle("option:alternate_bottom", "Alternate slopes",
        "Reverses every second tool slot.", opt.alternate_bottom === true);
      html += `</div></div>`;
    }

    if (scoopConfig) {
      const scoopDepth = Object.prototype.hasOwnProperty.call(scoopConfig, "depth")
        ? scoopConfig.depth : dividerScoopDefaultDepth();
      html += scoopDepthField("depth", scoopDepth, {
        dataAttribute: "data-divider-scoop-depth",
        tip: "Every Divider compartment gets the same Scoop depth and starts at its front floor edge.",
      });
    }
    html += `</div>`;

    if (!b4bEnabled()) {
      const hasLabels = opt.label_divisions === true;
      html += `<div class="editor-group"><span class="editor-group-label">Division labels</span>`;
      html += plainCheckbox("option:label_divisions", "Label divisions", hasLabels, {
        wide: true,
        help: "Add text labels to each division slot.",
      });

      if (hasLabels) {
        const divLevel = opt.division_level === "rim" ? "rim" : "base";
        html += textPlacementFields(
          "option:division_level", "option:division_side", divLevel, opt.division_side,
        );

        // A cell per compartment: (Qty X + 1) columns by (Qty Y + 1) rows,
        // laid out to mirror the bin so a label lands where its slot is.
        const legacyN = one.count == null ? 1 : Math.max(1, number(one.count, 1));
        let gcX = number(opt.count_x, NaN);
        if (!Number.isFinite(gcX)) gcX = one.along === "y" ? legacyN : 0;
        let gcY = number(opt.count_y, NaN);
        if (!Number.isFinite(gcY)) gcY = one.along === "x" ? legacyN : 0;
        gcX = Math.max(0, Math.round(gcX));
        gcY = Math.max(0, Math.round(gcY));
        const nCols = gcX + 1;
        const nRows = gcY + 1;
        let divLabels = [];
        if (Array.isArray(opt.division_labels)) {
          divLabels = opt.division_labels;
        } else if (typeof opt.division_labels === "string") {
          try {
            divLabels = JSON.parse(opt.division_labels);
          } catch {
            divLabels = opt.division_labels.split(",");
          }
        }

        const topology = dividerCompartmentsClient(one);
        html += `<div class="division-table division-grid" data-grid-columns="${nCols}" data-grid-rows="${nRows}">`;
        for (const cell of topology.cells) {
          const idx = cell.row * nCols + cell.column;
          const val = escapeHtml(String(divLabels[idx] || ""));
          html += `<input type="text" data-division-index="${idx}" data-grid-column="${cell.column + 1}" data-grid-column-span="${cell.columnSpan}" data-grid-row="${cell.row + 1}" data-grid-row-span="${cell.rowSpan}" value="${val}">`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }
  }
  // The auto-size buttons sit at the very bottom of the editor.
  if (!(one.kind === "text" && one.options?.level === "rim")) {
    html += renderFitActions(one);
  }
  // Informational only - a legal fused part above the rim still generates
  // fine. No checkbox, no warning styling; just a plain note of the fact.
  html += `<p class="inline-help" data-draft-overhang hidden></p>`;
  const activeDraft = document.activeElement?.dataset?.draft;
  $("#draft-fields").innerHTML = html;
  applyDivisionGridLayout($("#draft-fields"));
  if (one.kind === "divider" && dividerLockedByLidLabels()) {
    $$('input, select, button', $("#draft-fields")).forEach(control => { control.disabled = true; });
    $("#draft-status").textContent = dividerLockMessage();
  }
  updateDraftOverhangNote();
  syncNest2DWorkspace();
  const photoInput = $("#nest-photo-input", $("#draft-fields"));
  if (photoInput) photoInput.addEventListener("change", uploadNestPhoto);
  $$('[data-draft]', $("#draft-fields")).forEach(input => {
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", updateDraftFromFields);
  });
  if (activeDraft) {
    const el = $(`[data-draft="${activeDraft}"]`, $("#draft-fields"));
    if (el) el.focus();
  }
  const dividerAngle = $('[data-draft="option:bottom_angle"]', $("#draft-fields"));
  if (dividerAngle) dividerAngle.addEventListener("focus", () => dividerAngle.select());
  $$('input[data-division-index]', $("#draft-fields")).forEach(input => input.addEventListener("input", () => {
    markDraftChanged();
    state.draft.options ||= {};
    let labels = Array.isArray(state.draft.options.division_labels) ? [...state.draft.options.division_labels] : [];
    const idx = parseInt(input.dataset.divisionIndex, 10);
    labels[idx] = input.value;
    state.draft.options.division_labels = labels;
    seedPartNameFromLabel(input.value);
    renderLayout2D();
    refreshDraftSoon();
  }));
  const scoopDepth = $('[data-divider-scoop-depth]', $("#draft-fields"));
  if (scoopDepth) scoopDepth.addEventListener("input", () => {
    markDraftChanged();
    state.draft.options ||= {};
    const config = state.draft.options.scoop ||= {};
    const raw = scoopDepth.value.trim();
    if (raw === "") delete config.depth;
    else config.depth = number(raw, dividerScoopDefaultDepth());
    state.draftAutoCommit = true;
    renderLayout2D();
    refreshDraftSoon();
  });
  const textInput = $('[data-draft="option:text"]', $("#draft-fields"));
  if (textInput) {
    const clearIfLabel = () => {
      if (textInput.value.trim().toLowerCase() === "label") {
        textInput.value = "";
        textInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    };
    textInput.addEventListener("focus", clearIfLabel);
    textInput.addEventListener("click", clearIfLabel);
  }
  // Width/Depth are floored to a minimum footprint below - reflect that back
  // once the user leaves the field, so a typed 0 or -5 doesn't keep showing
  // as though it were still in effect while a different error is displayed.
  $$('[data-draft="width"], [data-draft="depth"]', $("#draft-fields")).forEach(input => {
    input.addEventListener("blur", () => {
      const zone = state.draft.zone;
      const isPocket = state.draft.kind === "pocket";
      const wall = isPocket ? number(state.draft.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
      let actual = input.dataset.draft === "width" ? zone[2] - zone[0] : zone[3] - zone[1];
      if (isPocket) actual = Math.max(0.1, actual - 2 * wall);
      if (fmt(actual) !== input.value) input.value = fmt(actual);
    });
  });
  // Quantity is floored to 1 below (blank/"auto" stays open-ended) - same
  // reasoning as Width/Depth above: reflect the floor back so a typed 0
  // doesn't keep showing while one is actually placed.
  const countField = $('[data-draft="count"]', $("#draft-fields"));
  const countAutoHint = $("#count-auto-hint", $("#draft-fields"));
  const syncCountAutoHint = () => { if (countAutoHint) countAutoHint.hidden = state.draft.count != null; };
  if (countField) {
    countField.addEventListener("input", syncCountAutoHint);
    countField.addEventListener("blur", () => {
      if (state.draft.count != null && String(state.draft.count) !== countField.value) {
        countField.value = String(state.draft.count);
      }
    });
  }
  $$('input[name="draft-along"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.along = input.value;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-wedge"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.wedge = input.value === "wedge";
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-turns"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    state.draft.options.quarter_turns = Number(input.value) % 4;
    // Turning it is a placement decision, so it stops being auto-placed.
    if (state.draft.options.auto) {
      state.draft.options.auto = false;
      const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
      if (autoField) autoField.checked = false;
    }
    // The zone was fitted to the old orientation; swap its sides so the
    // lettering keeps roughly the same size after the quarter turn.
    const zone = state.draft.zone;
    const cx = (zone[0] + zone[2]) / 2, cy = (zone[1] + zone[3]) / 2;
    const w = zone[2] - zone[0], d = zone[3] - zone[1];
    state.draft.zone = [cx - d / 2, cy - w / 2, cx + d / 2, cy + w / 2];
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-text-style"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    if (input.value === "raised") state.draft.options.raised = true;
    else delete state.draft.options.raised;
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  const autoCount = $('[data-action="auto-count"]', $("#draft-fields"));
  if (autoCount) autoCount.addEventListener("click", () => {
    markDraftChanged();
    state.draft.count = null;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  // The three per-part auto-size buttons (see renderFitActions).
  const fitBtn = $('[data-action="fit-part"]', $("#draft-fields"));
  if (fitBtn) fitBtn.addEventListener("click", fitPartToContents);
  const fillBtn = $('[data-action="fill-part"]', $("#draft-fields"));
  if (fillBtn) fillBtn.addEventListener("click", fillPartToBin);
  const growBtn = $('[data-action="grow-bin"]', $("#draft-fields"));
  if (growBtn) growBtn.addEventListener("click", event => autoExpandBin({ button: event.currentTarget }));
  updateFitActions();
  if (state.draft?.kind === "nest") wireNestFieldActions();
}

function syncNest2DWorkspace() {
  const wrap = $('.canvas-wrap[data-canvas="2d"]');
  if (!wrap) return;

  const canvas = $("#preview-2d");
  const layoutControls = $(".layout-controls", wrap);
  const scanPanel = $("#nest-scan-controls");
  const recovery = $("#nest-corner-recovery");

  const isNest = state.draft?.kind === "nest";
  const recoveryActive =
    isNest
    && Array.isArray(state.nestPaperCorners)
    && Boolean(state.nestOriginalImage);
  // The dedicated outline editor owns the canvas only while the user has
  // explicitly entered it. A saved Photo Nest otherwise stays in Layout.
  const hasPhotoSession = isNest && !recoveryActive && Boolean(state.nestRectifiedImage);
  const editingOutline = isNest && !recoveryActive
    && state.nestOutlineEditing === true
    && (hasPhotoSession || Boolean(state.draft.contour?.length));
  const hasContour = editingOutline && Boolean(state.draft.contour?.length);
  if (wrap.classList.contains("active")) updatePreviewHelp("2d");

  recovery.hidden = !recoveryActive;
  canvas.hidden = recoveryActive;
  if (layoutControls) layoutControls.hidden = recoveryActive || editingOutline;
  wrap.classList.toggle("nest-scan-active", editingOutline);

  if (recoveryActive) {
    scanPanel.hidden = true;

    const image = $("#nest-corner-image");
    if (image.src !== state.nestOriginalImage.dataUrl) {
      image.src = state.nestOriginalImage.dataUrl;
    }

    const corners = state.nestPaperCorners;
    $("#nest-corner-count").textContent = state.nestCornerBusy
      ? "Checking selected corners…"
      : `${corners.length} of 4 corners selected`;

    const markers = $("#nest-corner-markers");
    markers.innerHTML = corners.map((corner, index) =>
      `<span class="nest-corner-marker" data-corner-index="${index}"></span>`).join("");
    $$(".nest-corner-marker", markers).forEach((marker, index) => {
      marker.style.left = `${corners[index].xPct}%`;
      marker.style.top = `${corners[index].yPct}%`;
    });
    renderNestPaperOutline(corners);

    $("#nest-corners-clear").disabled = state.nestCornerBusy;
    $("#nest-corner-error").textContent = state.nestCornerError || "";
    $("#nest-corner-tip").hidden = state.nestCornerTipDismissed || state.nestCornerBusy;
    return;
  }

  scanPanel.hidden = !editingOutline;

  if (!editingOutline) return;

  const photoControls = $("#nest-scan-photo-controls");
  if (photoControls) photoControls.hidden = !hasPhotoSession;

  if (hasPhotoSession) {
    const opacity = $("#nest-photo-opacity-range");
    const sensitivity = $("#nest-sensitivity-range");
    const cleanup = $("#nest-cleanup-range");

    opacity.value = String(state.nestPhotoOpacity);
    sensitivity.value = String(state.nestSensitivity);
    cleanup.value = String(state.nestCleanup);

    $("#nest-photo-opacity-value").textContent =
      `${Math.round(state.nestPhotoOpacity)}%`;
    $("#nest-sensitivity-value").textContent =
      String(Math.round(state.nestSensitivity));
    $("#nest-cleanup-value").textContent =
      String(Math.round(state.nestCleanup));
  }

  const softenInput = $("#nest-soften-input");
  if (softenInput && document.activeElement !== softenInput) {
    softenInput.value = fmt(number(state.draft.options?.smoothing, 0));
  }

  const outlineTools = $("#nest-outline-tools");
  if (outlineTools) outlineTools.hidden = !hasContour;
  $$('input[name="nest-outline-tool"]').forEach(input => {
    input.checked = input.value === state.nestOutlineTool;
  });

  const viewportTools = $("#nest-viewport-tools");
  if (viewportTools) viewportTools.hidden = !hasContour;

  $("#nest-scan-apply").disabled = !hasContour && !state.nestCandidateContour;
  $("#nest-scan-status").textContent = state.nestTuneStatus || "";
}

function renderNestPaperOutline(corners) {
  const outline = $("#nest-paper-outline");
  if (!outline) return;
  if (corners.length < 2) {
    outline.innerHTML = "";
    return;
  }
  if (corners.length === 2) {
    const points = corners.map(corner => `${corner.xPct},${corner.yPct}`).join(" ");
    outline.innerHTML = `<polyline points="${points}"></polyline>`;
    return;
  }
  if (corners.length === 3) {
    const sides = [];
    for (let a = 0; a < corners.length; a += 1) {
      for (let b = a + 1; b < corners.length; b += 1) {
        const dx = corners[a].xPct - corners[b].xPct;
        const dy = corners[a].yPct - corners[b].yPct;
        sides.push({ a, b, length: dx * dx + dy * dy });
      }
    }
    const outside = sides.sort((one, two) => one.length - two.length).slice(0, 2);
    outline.innerHTML = outside.map(side => {
      const a = corners[side.a], b = corners[side.b];
      return `<line x1="${a.xPct}" y1="${a.yPct}" x2="${b.xPct}" y2="${b.yPct}"></line>`;
    }).join("");
    return;
  }
  const center = corners.reduce((sum, corner) => ({
    xPct: sum.xPct + corner.xPct / corners.length,
    yPct: sum.yPct + corner.yPct / corners.length,
  }), { xPct: 0, yPct: 0 });
  const points = [...corners]
    .sort((one, two) => Math.atan2(one.yPct - center.yPct, one.xPct - center.xPct)
      - Math.atan2(two.yPct - center.yPct, two.xPct - center.xPct))
    .map(corner => `${corner.xPct},${corner.yPct}`).join(" ");
  outline.innerHTML = `<polygon points="${points}"></polygon>`;
}

function nestCornerPoint(event) {
  const image = $("#nest-corner-image");
  const rect = image.getBoundingClientRect();
  if (!rect.width || !rect.height) return null;
  return {
    xPct: Math.max(0, Math.min(100, (event.clientX - rect.left) / rect.width * 100)),
    yPct: Math.max(0, Math.min(100, (event.clientY - rect.top) / rect.height * 100)),
  };
}

function showNestCornerMagnifier(point) {
  const magnifier = $("#nest-corner-magnifier");
  const image = $("#nest-corner-image");
  if (!magnifier || !image || !state.nestOriginalImage) return;
  const rect = image.getBoundingClientRect();
  const size = 144;
  const border = 3;
  const zoom = 4;
  const lensCenter = (size - border * 2) / 2;
  const sourceX = point.xPct / 100 * rect.width;
  const sourceY = point.yPct / 100 * rect.height;
  magnifier.style.backgroundImage = `url("${state.nestOriginalImage.dataUrl}")`;
  magnifier.style.backgroundSize = `${rect.width * zoom}px ${rect.height * zoom}px`;
  magnifier.style.backgroundPosition =
    `${lensCenter - sourceX * zoom}px ${lensCenter - sourceY * zoom}px`;
  magnifier.style.left = `${Math.max(6, Math.min(rect.width - size - 6, point.xPct / 100 * rect.width + 18))}px`;
  magnifier.style.top = `${Math.max(6, Math.min(rect.height - size - 6, point.yPct / 100 * rect.height + 18))}px`;
  magnifier.hidden = false;
}

function hideNestCornerMagnifier() {
  const magnifier = $("#nest-corner-magnifier");
  if (magnifier) magnifier.hidden = true;
}

function beginNestCornerPointer(event, index = null) {
  if (state.nestCornerBusy || !Array.isArray(state.nestPaperCorners)) return;
  const point = nestCornerPoint(event);
  if (!point) return;
  event.preventDefault();
  nestCornerPointer = { id: event.pointerId, index, magnifying: false, point };
  nestCornerHoldTimer = setTimeout(() => {
    if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
    nestCornerPointer.magnifying = true;
    showNestCornerMagnifier(nestCornerPointer.point);
  }, 350);
}

function moveNestCornerPointer(event) {
  if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
  const point = nestCornerPoint(event);
  if (!point) return;
  nestCornerPointer.point = point;
  if (nestCornerPointer.index !== null) {
    state.nestPaperCorners[nestCornerPointer.index] = point;
    state.nestCornerError = "";
    syncNest2DWorkspace();
  }
  if (nestCornerPointer.magnifying) showNestCornerMagnifier(point);
}

function endNestCornerPointer(event, cancelled = false) {
  if (!nestCornerPointer || nestCornerPointer.id !== event.pointerId) return;
  clearTimeout(nestCornerHoldTimer);
  const interaction = nestCornerPointer;
  nestCornerPointer = null;
  hideNestCornerMagnifier();
  if (cancelled) return;
  const point = nestCornerPoint(event);
  if (!point || !Array.isArray(state.nestPaperCorners)) return;
  if (interaction.index === null) state.nestPaperCorners.push(point);
  else state.nestPaperCorners[interaction.index] = point;
  if (state.nestPaperCorners.length >= 1) state.nestCornerTipDismissed = true;
  state.nestCornerError = "";
  syncNest2DWorkspace();
  if (state.nestPaperCorners.length === 4) {
    state.nestCornerBusy = true;
    syncNest2DWorkspace();
    void acceptNestPaperCorners();
  }
}

function wireNest2DControls() {
  $("#nest-photo-opacity-range")?.addEventListener("input", event => {
    state.nestPhotoOpacity = number(event.target.value, 45);
    syncNest2DWorkspace();
    renderLayout2D();
  });

  $("#nest-sensitivity-range")?.addEventListener("input", event => {
    state.nestSensitivity = number(event.target.value, 50);
    queueNestRetrace();
  });

  $("#nest-cleanup-range")?.addEventListener("input", event => {
    state.nestCleanup = number(event.target.value, 50);
    queueNestRetrace();
  });

  $("#nest-scan-defaults")?.addEventListener("click", () => {
    state.nestSensitivity = 50;
    state.nestCleanup = 50;
    queueNestRetrace("Restoring default scan settings…");
  });

  $("#nest-scan-apply")?.addEventListener("click", finishNestEditing);

  // Soften outline lives in this panel now, not the sidebar, so it cannot
  // use the generic data-draft wiring (scoped to #draft-fields) - commit it
  // directly, the same way other one-off nest fields already do.
  $("#nest-soften-input")?.addEventListener("input", event => {
    if (state.draft?.kind !== "nest") return;
    markDraftChanged();
    state.draft.options ||= {};
    const raw = event.target.value.trim();
    if (raw === "") delete state.draft.options.smoothing;
    else state.draft.options.smoothing = Math.max(0, number(raw, 0));
    state.draftAutoCommit = true;
    renderLayout2D();
    refreshDraftSoon();
  });

  $$('input[name="nest-outline-tool"]').forEach(input => input.addEventListener("change", () => {
    state.nestOutlineTool = input.value;
    renderLayout2D();
  }));

  $("#nest-reset-outline")?.addEventListener("click", resetNestOutline);

  $("#nest-zoom-in")?.addEventListener("click", () => nestZoomBy(1.4));
  $("#nest-zoom-out")?.addEventListener("click", () => nestZoomBy(1 / 1.4));
  $("#nest-zoom-fit")?.addEventListener("click", resetNestView);

  $("#preview-2d")?.addEventListener("wheel", event => {
    if (!isNestEditWorkspaceActive()) return;
    event.preventDefault();
    const point = canvasPointFromEvent(event.currentTarget, event);
    nestZoomBy(Math.exp(-event.deltaY * .001), point);
  }, { passive: false });

  $("#nest-corners-clear")?.addEventListener("click", () => {
    if (state.nestCornerBusy) return;
    state.nestPaperCorners = [];
    state.nestCornerError = "";
    hideNestCornerMagnifier();
    syncNest2DWorkspace();
  });

  $("#nest-corner-tip-close")?.addEventListener("click", () => {
    state.nestCornerTipDismissed = true;
    syncNest2DWorkspace();
  });

  $("#nest-corner-markers")?.addEventListener("pointerdown", event => {
    const marker = event.target.closest(".nest-corner-marker");
    if (!marker) return;
    event.stopPropagation();
    beginNestCornerPointer(event, Number(marker.dataset.cornerIndex));
  });

  $("#nest-corner-image")?.addEventListener("pointerdown", event => {
    if (!Array.isArray(state.nestPaperCorners)
        || state.nestPaperCorners.length >= 4
        || state.nestCornerBusy) {
      return;
    }
    beginNestCornerPointer(event);
  });

  window.addEventListener("pointermove", moveNestCornerPointer);
  window.addEventListener("pointerup", event => endNestCornerPointer(event));
  window.addEventListener("pointercancel", event => endNestCornerPointer(event, true));
}

function queueNestRetrace(status = "Retracing…") {
  // The visible sliders no longer describe the old candidate. Remove it at
  // once so Apply can never accept an outline from the previous settings
  // during the debounce or while the replacement is still being calculated.
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestTuneStatus = status;
  syncNest2DWorkspace();
  renderLayout2D();
  requestNestRetrace();
}

// Photo Nest's own sidebar buttons - separated out because they carry
// session-only state that no other feature kind touches.
function wireNestFieldActions() {
  const fields = $("#draft-fields");
  const pushOut = $('[data-draft="nest-push-out"]', fields);
  if (pushOut) pushOut.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    setNestPushOut(state.draft.options, pushOut.checked);
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  const cavityAuto = $('[data-action="nest-cavity-auto"]', fields);
  if (cavityAuto) cavityAuto.addEventListener("click", () => {
    markDraftChanged();
    state.draft.options ||= {};
    delete state.draft.options.cavity_depth;
    state.draft.options.cavity_depth_mode = "auto";
    state.draftAutoCommit = true;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  const editOutline = $('[data-action="edit-nest-outline"]', fields);
  if (editOutline) editOutline.addEventListener("click", () => {
    state.nestOutlineEditing = true;
    state.nestViewZoom = 1; state.nestViewPanX = 0; state.nestViewPanY = 0;
    activatePreviewView("2d"); syncNest2DWorkspace(); renderLayout2D();
  });
  const duplicate = $('[data-action="duplicate-nest"]', fields);
  if (duplicate) duplicate.addEventListener("click", duplicateNest);
}

async function duplicateNest() {
  if (!state.draft?.contour || !Number.isInteger(state.selected)) return;
  let previousDesign = null;
  let previousSelected = null;
  let mutationStarted = false;
  try {
    await commitVisibleDraft();
    const index = state.selected;
    if (!Number.isInteger(index) || !state.design.layout.features[index]) return;
    if (!beginDesignMutation()) return;
    mutationStarted = true;
    previousDesign = clone(state.design);
    previousSelected = index;
    const result = await api("/api/feature/duplicate", { design: state.design, index });
    state.design = result.design;
    recordHistory(previousDesign);
    resetNestPhotoSession();
    state.selected = result.selected;
    state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[result.selected]);
    state.draftKind = "nest"; state.draftIsNew = false; state.draftTouched = false;
    state.draftAutoCommit = true; state.nestOutlineEditing = false;
    syncForm(); renderDraftFields(); renderPlaced(); await refreshPreview();
    toast("Photo Nest duplicated.");
  } catch (error) {
    if (previousDesign && Number.isInteger(previousSelected)) {
      state.design = previousDesign;
      state.selected = previousSelected;
      state.draftSourceIndex = previousSelected;
      state.draft = clone(previousDesign.layout.features[previousSelected]);
      state.draftKind = "nest"; state.draftIsNew = false; state.draftTouched = false;
      state.draftAutoCommit = true; state.nestOutlineEditing = false;
      renderDraftFields(); renderPlaced(); await refreshPreview();
    }
    toast(error.message, true, 6500);
  } finally { if (mutationStarted) finishDesignMutation(); }
}

async function resetNestOutline() {
  const one = state.draft;
  const index = draftCommitIndex();
  if (!one || one.kind !== "nest" || !Number.isInteger(index)) return;
  const baseline = one.source_contour || one.contour;
  if (!baseline) return;
  state.nestCandidateContour = null;
  await commitNestContourEdit(index, baseline.map(point => [...point]));
}

// Debounced live retrace: segmentation + cleanup only, on the already-
// rectified reference sheet - paper detection never repeats per slider move.
// Every retrace re-centres its new contour around its own new bounding box
// (contour_to_millimetres always does this), so a candidate's own local
// origin can differ a little from the accepted outline's. Rather than
// swapping the displayed photo to match the candidate (which would make the
// still-visible accepted outline look wrong against it), translate the
// candidate into the accepted outline's own stable frame using both traces'
// trace_center_mm, so accepted outline, candidate outline and photo all sit
// in one consistent physical frame at once.
const requestNestRetrace = debounce(async () => {
  const rectified = state.nestRectifiedImage;
  const draft = state.draft;
  if (!rectified || !draft || draft.kind !== "nest") return;
  const request = ++state.nestRetraceRequest;
  state.nestTuneStatus = "Retracing…";
  syncNest2DWorkspace();
  try {
    const result = await api("/api/nest/retrace", {
      rectified_image: rectified.dataUrl,
      mime_type: rectified.mimeType,
      sensitivity: state.nestSensitivity,
      cleanup: state.nestCleanup,
    });
    if (request !== state.nestRetraceRequest || state.draft !== draft) return;
    const accepted = state.nestAcceptedCenterMm || [0, 0];
    const candidateCenter = result.trace_center_mm || accepted;
    const delta = [candidateCenter[0] - accepted[0], candidateCenter[1] - accepted[1]];
    state.nestCandidateContour = result.contour.map(([x, y]) => [x + delta[0], y + delta[1]]);
    state.nestCandidateCenterMm = candidateCenter;
    state.nestTuneStatus = `Candidate: ${fmt(result.outline.width)} × ${fmt(result.outline.depth)} mm — press Finish Editing to accept.`;
  } catch (error) {
    if (request !== state.nestRetraceRequest) return;
    // Failed retrace is non-destructive (spec section 34): keep the accepted
    // outline and its photo registration exactly as they were, and just
    // report why the candidate failed.
    state.nestCandidateContour = null;
    state.nestCandidateCenterMm = null;
    state.nestTuneStatus = `Could not retrace at this setting: ${error.message}`;
  }
  syncNest2DWorkspace();
  renderLayout2D();
}, 300);

// "Finish Editing": commit any pending scan-tuning candidate exactly as
// Apply always did, then - once a real nest feature exists to show - leave
// the dedicated outline editor and switch straight to the 3D view, which
// already highlights the selected part live (spec: "Nested 2D Outline
// Editing"). Still mid-trace (no Tool thickness yet)? There is nothing to
// build yet, so stay in 2D instead of jumping to an empty selection.
async function finishNestEditing() {
  const one = state.draft;
  if (!one || one.kind !== "nest") return;
  if (state.nestCandidateContour) await acceptNestTrace();
  if (!state.draft?.contour?.length) return;
  state.nestOutlineEditing = false;
  activatePreviewView("3d");
}

async function acceptNestTrace() {
  const one = state.draft;
  const index = draftCommitIndex();
  if (!one || one.kind !== "nest" || !state.nestCandidateContour) return;
  let candidate = state.nestCandidateContour.map(point => [...point]);
  const candidateCenter = state.nestCandidateCenterMm;
  state.nestCandidateContour = null;
  state.nestCandidateCenterMm = null;
  state.nestTuneStatus = "";
  if (!Number.isInteger(index)) {
    if (one.contour || !state.nestTraceResult) {
      // The part was placed (or the trace result vanished) in the moment
      // between retracing and pressing Apply - the edit above can no longer
      // land anywhere, so say so instead of silently dropping it.
      state.nestTuneStatus = "Could not apply the adjusted outline - please retrace.";
      renderLayout2D();
      return;
    }
    const pending = {
      contour: candidate,
      source_contour: null,
      zone: [-.5, -.5, .5, .5],
      rotation: 0,
      scale: 1,
    };
    normalizeNestContour(pending);
    candidate = pending.contour;
    const xs = candidate.map(point => point[0]);
    const ys = candidate.map(point => point[1]);
    state.nestTraceResult.contour = candidate;
    state.nestTraceResult.outline = {
      width: Math.max(...xs) - Math.min(...xs),
      depth: Math.max(...ys) - Math.min(...ys),
    };
    if (state.nestTraceResult.reference && state.nestPhoto?.bounds) {
      state.nestTraceResult.reference.bounds = [...state.nestPhoto.bounds];
    }
    if (candidateCenter) {
      state.nestTraceResult.trace_center_mm = candidateCenter;
      state.nestAcceptedCenterMm = candidateCenter;
    }
    state.nestTuneStatus = "Adjusted outline accepted.";
    syncNest2DWorkspace();
    renderLayout2D();
    await finishPhotoNestIfReady();
    return;
  }
  await commitNestContourEdit(index, candidate, { source_contour: candidate.map(point => [...point]) });
  // The committed contour re-centres around its own new bounding box
  // (normalizeNestContour, inside commitNestContourEdit) - which for an
  // already-self-centred raw candidate lands exactly back on the candidate's
  // own trace centre, so that becomes the new accepted stable-frame centre.
  if (candidateCenter) state.nestAcceptedCenterMm = candidateCenter;
  syncNest2DWorkspace();
}

// Runs the trace-only phase (spec section 1): paper detection/correction (or
// supplied corners), segmentation and contour extraction. Independent of any
// design - never touches Tool thickness, the bin, or Nest geometry. Whoever
// finishes last between this and Tool thickness triggers finalization.
async function runNestTrace(paperCorners) {
  const original = state.nestOriginalImage;
  const draft = state.draft;
  if (!original || !draft || draft.kind !== "nest") return;
  const request = ++state.nestTraceRequest;
  $("#draft-status").textContent = "Finding the reference sheet and tracing the part…";
  $("#draft-status").classList.remove("error");
  try {
    const result = await api("/api/nest/trace", {
      image: original.dataUrl,
      mime_type: original.mimeType,
      sensitivity: state.nestSensitivity,
      cleanup: state.nestCleanup,
      paper_corners: paperCorners,
    });
    if (request !== state.nestTraceRequest || state.draft !== draft) return;
    state.nestTraceResult = result;
    state.nestOutlineEditing = true;
    state.nestRectifiedImage = result.rectified_image
      ? { dataUrl: result.rectified_image, mimeType: "image/jpeg" } : state.nestRectifiedImage;
    state.nestPaperCorners = null;
    state.nestCornerError = "";
    state.nestCornerBusy = false;
    state.nestAcceptedCenterMm = result.trace_center_mm || null;
    setNestPhotoReference(result.reference);
    if (_nestMeasuredThickness(draft.options) == null) {
      $("#draft-status").textContent = "Photo traced — enter Tool thickness above to finish.";
    }
    renderDraftFields();
    activatePreviewView("2d");
    setLayoutOrientation("topup");
    syncNest2DWorkspace();
    renderLayout2D();
    await finishPhotoNestIfReady();
  } catch (error) {
    if (request !== state.nestTraceRequest) return;
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    if (paperCorners) {
      // The user supplied four corners but Python still rejected them.
      // Keep those points visible so they can clear/retry without re-uploading.
      state.nestCornerBusy = false;
      state.nestCornerError = error.message;
      syncNest2DWorkspace();
      toast(error.message, true, 6500);
    } else if (/paper missing|paper detection/i.test(error.message)) {
      state.nestPaperCorners = [];
      state.nestCornerBusy = false;
      state.nestCornerError = error.message;
      syncNest2DWorkspace();
      toast(
        "Automatic paper detection failed. Click the four paper corners in 2D.",
        true, 8500, "prominent",
      );
    } else {
      toast(error.message, true, 6500);
    }
  }
}

// Whichever of tracing / Tool thickness finishes last calls this. Does
// nothing until both a completed trace and a measured Tool thickness exist;
// never decodes or retraces the photo itself (spec section 1).
async function finishPhotoNestIfReady() {
  const trace = state.nestTraceResult;
  const draft = state.draft;
  if (!trace || !draft || draft.kind !== "nest") return;
  if (_nestMeasuredThickness(draft.options) == null) return;
  if (!beginDesignMutation()) return;
  const previousDesign = clone(state.design);
  try {
    const payload = {
      design: state.design,
      contour: trace.contour,
      options: draft.options || {},
    };
    // Replacing an existing photo: send the live draft too, so a setting
    // changed since the last debounced save is not lost (spec section 7).
    if (draft.contour) {
      payload.feature = draft;
      payload.index = draftCommitIndex();
    }
    const result = await api("/api/nest/photo", payload);
    state.design = result.design;
    recordHistory(previousDesign);
    state.selected = result.selected;
    state.draftKind = "nest";
    state.draft = clone(state.design.layout.features[state.selected]);
    setNestPhotoReference(trace.reference);
    state.nestAcceptedCenterMm = trace.trace_center_mm || null;
    state.nestTraceResult = null;
    state.draftAutoCommit = true;
    state.drafts = {};
    syncForm();
    renderDraftFields();
    await refreshPreview();
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    $('.view-tab[data-view="2d"]').click();
    setLayoutOrientation("topup");
    toast(`Photo Nest ready: ${fmt(trace.outline.width)} × ${fmt(trace.outline.depth)} mm outline.`);
    for (const warning of result.warnings || []) toast(warning, false, 6500);
  } catch (error) {
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    toast(error.message, true, 6500);
  } finally {
    finishDesignMutation();
  }
}

async function acceptNestPaperCorners() {
  const original = state.nestOriginalImage;
  const corners = state.nestPaperCorners;

  if (!original || !Array.isArray(corners) || corners.length !== 4) return;

  const img = new Image();
  img.src = original.dataUrl;
  await (img.decode ? img.decode().catch(() => {}) : Promise.resolve());

  const width = img.naturalWidth || 1;
  const height = img.naturalHeight || 1;

  const paperCorners = corners.map(corner => [
    corner.xPct / 100 * width,
    corner.yPct / 100 * height,
  ]);

  state.nestCornerError = "";
  state.nestCornerBusy = true;
  syncNest2DWorkspace();
  await runNestTrace(paperCorners);
}

// A divider builds from its thickness option, not from the footprint drawn
// below - widen that footprint to match so what the Width/Depth fields and
// the 2D layout show never falls short of the real wall. Which side is
// "across" follows the explicit Runs-along choice, not a guess from
// whichever of width/depth is currently bigger. Round the wall's thickness up
// to the 1 mm grid first, so the pipeline's nearest-line snap can't leave the
// footprint a hair under the wall (same trap sizeCradleToItem sidesteps).
function widenDividerFootprint(one) {
  const t = Math.ceil(one.options.thickness);
  if (!Number.isFinite(t) || t <= 0) return;
  const zw = one.zone[2] - one.zone[0], zd = one.zone[3] - one.zone[1];
  const cx = (one.zone[0] + one.zone[2]) / 2, cy = (one.zone[1] + one.zone[3]) / 2;
  const wideningKey = one.along === "x" ? "depth" : "width";
  if (one.along === "x") {
    const depth = Math.max(zd, t);
    one.zone = [one.zone[0], cy - depth / 2, one.zone[2], cy + depth / 2];
  } else {
    const width = Math.max(zw, t);
    one.zone = [cx - width / 2, one.zone[1], cx + width / 2, one.zone[3]];
  }
  const shownField = $(`[data-draft="${wideningKey}"]`, $("#draft-fields"));
  if (shownField) {
    const newSpan = wideningKey === "width"
      ? one.zone[2] - one.zone[0]
      : one.zone[3] - one.zone[1];
    if (shownField.value !== fmt(newSpan)) {
      shownField.value = fmt(newSpan);
      flashField(shownField);
    }
  }
}

// Keep a cradle's footprint hugging what it actually holds, so the Width/Depth
// fields and the 2D layout never disagree with the built ribs.
//
//   run axis (the tool lies along it): tool length, except Alternate ends uses
//     the whole available run so troughs can sit 10% in from opposite sides.
//   across axis (lanes sit side by side on it): a set Quantity hugs to exactly
//     that many lanes; Quantity = auto spans the whole bin so the engine's
//     "fit as many as will fit" has room to work - otherwise a 1-lane zone
//     boxes it in and auto can only ever place one.
//
// Every dimension is rounded UP to the 1 mm editor grid: the design pipeline
// snaps a zone to the nearest grid line, and rounding a 16.4 mm need down to
// 16 mm builds a cradle the engine then rejects. Both axes are also clamped to
// the usable floor so an over-long tool yields the engine's specific "40 mm
// long but the zone only runs 39 mm" message instead of a generic overflow.
function sizeCradleToItem(one) {
  const item = one.item;
  if (!item?.segments?.length) return;
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const spacing = Math.max(0, number(one.options?.spacing, state.draftResolvedOptions?.spacing ?? 0));
  const length = item.segments.reduce((total, segment) => total + number(segment.length), 0);
  // The true tool diameter (no fit slack) and a wall a quarter of it, floored at
  // the thinnest printable wall and capped so a fat handle never grows a slab.
  // Mirrors _cradle_wall in organizer_inserts.py.
  const diameter = Math.max(...item.segments.map(segment => number(segment.diameter)));
  const rib = Math.min(Math.max(diameter * 0.25, 1.6), 6);
  const auto = one.count == null;
  const count = auto ? 1 : one.count;
  // Auto Quantity may become multiple lanes, so it also uses the end-to-end
  // layout whenever Alternate ends is on.
  const alternating = one.alternate_ends === true && (auto || count > 1);
  // A non-alternating cradle hugs its tool until "Offset from center" is set;
  // then it needs the whole run so the trough has room to slide within it.
  const offset = alternating ? 0 : number(one.options?.run_offset, 0);
  const spansRun = alternating || Math.abs(offset) > 1e-9;

  const [insideX, insideY] = binInsideExtent(state.design.box);
  const roomAlong = one.along === "x" ? insideX : insideY;
  const roomAcross = one.along === "x" ? insideY : insideX;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curRun = one.along === "x" ? curW : curD;
  const curAcross = one.along === "x" ? curD : curW;
  const runKey = one.along === "x" ? "width" : "depth";
  const acrossKey = one.along === "x" ? "depth" : "width";

  const oneLane = diameter + rib;
  const pitch = diameter + rib / 2 + spacing;
  const endMargin = Math.min(.45, Math.max(0,
    number(one.options?.end_margin, state.draftResolvedOptions?.end_margin ?? 10) / 100));
  const minimumRun = Math.max(1, Math.ceil(
    alternating ? length / (1 - 2 * endMargin) : length,
  ));
  const minimumAcross = Math.max(1, Math.ceil(oneLane + (count - 1) * pitch));
  const wantedRun = spansRun ? Math.max(roomAlong, minimumRun) : minimumRun;
  const wantedAcross = auto ? roomAcross : minimumAcross;
  // A hand-sized axis is a floor, never a target to overwrite. Requirements
  // may still grow it. Do not clamp a required footprint to the current bin;
  // the bin grower needs the real size in order to make enough room.
  const run = state.pinnedZone[runKey] ? Math.max(curRun, minimumRun) : wantedRun;
  const across = state.pinnedZone[acrossKey]
    ? Math.max(curAcross, auto ? oneLane : minimumAcross)
    : wantedAcross;

  const width = one.along === "x" ? run : across;
  const depth = one.along === "x" ? across : run;
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
}

// Keep a bore's Base (the drilled block) exactly big enough for its hole grid,
// so the Width / Length fields and the 2D layout never disagree with what the
// engine builds - and so raising a count, widening a hole, or leaning the grid
// grows the block on its own instead of throwing "reaches outside the bin".
//
// Mirrors feature_min_footprint()'s bore branch in organizer_inserts/_layout.py:
// pitch is (hole + wall), the block runs columns x pitch by rows x pitch, and a
// leaned grid adds along its lean axis the sideways "reach" the slanting hole
// bottoms travel. The block grows AND shrinks to that minimum on its own; when
// it now needs more floor than the bin has, refreshDraft()'s catch grows the
// bin around it. A pinned axis (see state.pinnedZone) only ever grows to the
// minimum - a hand-set Base size is never shrunk back. An axis left on "auto"
// count still keeps room for at least one hole so the fitter always has
// something to divide.
// Persisted Bore sizing modes (options xy_size_mode / height_size_mode). Mirrors
// normalize_bore_modes() in organizer_inserts/_bore.py: retired state is dropped,
// Base "bore to bin" owns the zone (the whole usable floor, never a pin or a
// minimum grid), and Height "bore to bin" owns its number by leaving it unset so
// the engine derives it. Returns true when "bore to bin" placed the zone.
function applyBoreSizing(one) {
  if (one?.kind !== "bore") return false;
  const opts = one.options ||= {};
  const style = normalizeBoreStyle(opts.bore_style, opts.wall_style);
  for (const retired of ["auto_base", "auto_height", "auto_grid", "wall_style"]) delete opts[retired];
  opts.bore_style = style;
  opts.xy_size_mode = boreXyMode(one);
  opts.height_size_mode = boreHeightMode(one);
  if (style !== "base_straight") {
    delete opts.angle;
    delete opts.angle_towards;
  }
  if (!boreWallsOnly(style)) delete opts.wall;   // Base styles use internal defaults
  if (opts.height_size_mode === "bore_to_bin") delete opts.height;
  if (opts.xy_size_mode === "bin_to_bore" && boreWallsOnly(style)) {
    // Mirrors normalize_bore_modes(): a bin-sized Walls Only Bore is centred.
    const halfW = (one.zone[2] - one.zone[0]) / 2;
    const halfD = (one.zone[3] - one.zone[1]) / 2;
    one.zone = [-halfW, -halfD, halfW, halfD];
    return false;
  }
  if (opts.xy_size_mode !== "bore_to_bin" || boreWallsOnly(style)) return false;
  const [insideX, insideY] = binInsideExtent(state.design.box);
  one.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  delete state.pinnedZone.width;
  delete state.pinnedZone.depth;
  return true;
}

// Mirrors bore_minimum_pitches() in organizer_inserts/_bore.py. Axis-aligned
// square holes (square_axis) pitch at held + wall; other polygons use the
// circumscribed radius.
function boreCrossPitch(profile, held, wall) {
  if (profile === "square_axis") return held + wall;
  const sides = profile === "round" ? 48 : profile === "square" ? 4 : 6;
  const holeRadius = held / 2 / (sides < 8 ? Math.cos(Math.PI / sides) : 1);
  return 2 * holeRadius + wall;
}

function sizeBoreToGrid(one) {
  if (one.kind !== "bore") return;
  // "Auto size bore to bin" fills the bin whatever the grid needs. Every other
  // Base grows to its grid; a Walls Only Bore, or one whose bin is sized around
  // it, always sits exactly at its minimum footprint.
  const opts = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  if (applyBoreSizing(one)) return;
  const profile = one.item?.profile || "round";
  const hexBit = isHexBitProfile(profile);
  const diameter = hexBit
    ? HEX_BIT_PROFILES[profile].diameter
    : number(one.item?.segments?.[0]?.diameter, 6);
  const held = diameter + 0.25;
  const boreStyle = boreStyleOf(one);
  const walls = boreWallsOnly(boreStyle);
  // Both Walls Only styles and Base - Wavy Walls stand upright and size to their
  // wavy/straight sleeves' outer envelope.
  const wallOnly = boreStyle !== "base_straight";
  const exactSize = walls || boreXyMode(one) === "bin_to_bore";
  const angle = hexBit || wallOnly ? 0 : Math.min(70, Math.max(0, number(opts.angle ?? resolved.angle, 0)));
  // A leaned bore defaults to a thicker wall (engine: BORE_TILTED_WALL) unless
  // Wall was hand-set - match that so the block sizing tracks the real pitch.
  // Wall Only takes the current bin wall instead (engine: bore_defaults).
  const wall = opts.wall !== undefined ? number(opts.wall)
    : wallOnly ? number(state.design?.box?.wall, 0.8)
    : (angle > 0 ? 3 : 1.6);
  const crossPitch = boreCrossPitch(profile, held, wall);
  const leanPitch = crossPitch / Math.cos(angle * Math.PI / 180);
  if (!(crossPitch > 0) || !(leanPitch > 0)) return;

  const holeDepth = number(opts.depth ?? resolved.depth, 0);
  const reach = angle > 0 ? holeDepth * Math.sin(angle * Math.PI / 180) : 0;
  const angleTowards = opts.angle_towards;
  const along = ["left", "right"].includes(angleTowards) ? "x"
    : ["front", "back"].includes(angleTowards) ? "y"
    : one.along === "y" ? "y" : "x";

  // A leaned bore's angled tools sweep past the block toward `angle_towards`,
  // right up to the bin rim (see bore_tool_clearance_zone in
  // organizer_inserts/_bore.py). Bias the block away from that wall by half the
  // tool's overhang so the tools stay balanced in the bin and it never has to
  // grow just to let a slanting tool clear one side.
  const leanSign = angleTowards === "right" || angleTowards === "back" ? 1 : -1;
  const box = state.design.box;
  const baseZ = number(box.base_thickness, 0.6) +
    (state.design.layout.mode === "fused" ? 0 : 0.6);
  const boreHeight = number(opts.height ?? resolved.height, holeDepth + 2);
  const riseToRim = number(box.z, 0) - (baseZ + boreHeight);
  const toolOverhang = angle > 0 && riseToRim > 0
    ? riseToRim * Math.tan(angle * Math.PI / 180) : 0;

  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const [insideX, insideY] = binInsideExtent(state.design.box);
  // Wall Only mirrors wall_only_envelope() in organizer_inserts/_bore.py: the
  // footprint is the sleeves' true outer envelope, wave included.
  const wallRules = state.catalog?.wall_rules || {};
  const amplitude = number(wallRules.wave_amplitude_mm ?? state.catalog?.wave_amplitude_mm, 0.4);
  const depthFactor = number(wallRules.wall_depth_factor ?? state.catalog?.wall_depth_factor, 1.181);
  const waveNoiseFloor = 1e-4;  // ensure wavy troughs never self-intersect
  const wavy = boreWavy(boreStyle);
  const shellReach = wavy ? 2 * amplitude + wall * depthFactor + waveNoiseFloor : wall;
  const clearSpan = (axis) => {
    if (profile === "round") {
      // Conservative round clear span: a 256-sided circumscribed polygon.
      // Backend uses >= 256 sides for all Wavy sampling, so this is safe.
      return held / Math.cos(Math.PI / 256);
    }
    if (profile === "square_axis") return held;
    const sides = profile === "square" ? 4 : 6;
    const circum = held / Math.cos(Math.PI / sides);   // corner-to-corner
    return sides === 4 || axis === "x" ? circum : held;
  };
  // Mirrors WALL_ONLY_FOOT in _bore.py: the strengthening foot reaches this far
  // past the sleeve on each outside side. Walls Only only - never Base - Wavy.
  const wallOnlyFoot = walls ? 0.5 : 0;
  const axisSpan = (count, axis) => {
    if (wallOnly) {
      return Math.ceil(clearSpan(axis) + 2 * shellReach + 2 * wallOnlyFoot + (count - 1) * crossPitch - 1e-6);
    }
    const pitch = along === axis ? leanPitch : crossPitch;
    return Math.ceil(count * pitch + (along === axis ? reach : 0) - 1e-6);
  };
  // An unset quantity means one hole, not “fill the existing Base.” Changing
  // X/Y, hole diameter, Wall, depth, or lean grows the Base to its exact need.
  const resolveAxis = (countKey, cur, pinKey, leanAxis) => {
    const count = Math.max(1, Math.round(number(opts[countKey] ?? resolved[countKey], 1)));
    const minimum = axisSpan(count, leanAxis);
    // Walls Only and "bin to bore" always take their exact minimum; a manual Base
    // that has been pinned only ever grows.
    return state.pinnedZone[pinKey] && !exactSize ? Math.max(cur, minimum) : minimum;
  };
  const width = resolveAxis("columns", curW, "width", "x");
  const depth = resolveAxis("rows", curD, "depth", "y");
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;

  // Stay where the block already sits when it still fits; once an axis outgrows
  // the bin, keep it on its old centre and let the bin grow around it.
  const place = (centre, span, inside) => {
    if (span >= inside) return centre;
    const half = span / 2;
    return Math.min(Math.max(centre, -inside / 2 + half), inside / 2 - half);
  };
  // Push the block off the wall its tools lean toward - never back toward it,
  // so a hand-placed bore that already sits clear is left where it is.
  const leanTarget = (centre, axis) => {
    if (toolOverhang <= 0 || along !== axis) return centre;
    const bias = -leanSign * toolOverhang / 2;
    return leanSign < 0 ? Math.max(centre, bias) : Math.min(centre, bias);
  };
  // A Walls Only Bore that sizes the bin around itself stays centred.
  const centred = walls && boreXyMode(one) === "bin_to_bore";
  const ncx = centred ? 0 : place(leanTarget(cx, "x"), width, insideX);
  const ncy = centred ? 0 : place(leanTarget(cy, "y"), depth, insideY);
  one.zone = [ncx - width / 2, ncy - depth / 2, ncx + width / 2, ncy + depth / 2];

  const widthField = $('[data-draft="width"]', $("#draft-fields"));
  if (widthField && Math.abs(width - curW) >= 0.05) { widthField.value = fmt(width); flashField(widthField); }
  const depthField = $('[data-draft="depth"]', $("#draft-fields"));
  if (depthField && Math.abs(depth - curD) >= 0.05) { depthField.value = fmt(depth); flashField(depthField); }
}

// The peg-row twin of sizeBoreToGrid. feature_min_footprint()'s post branch:
// the run axis carries count pegs of `diameter` with `spacing` gaps between;
// the across axis only needs one `diameter`. Count on "auto" is left for the
// fitter. Only the run axis is resized - the across axis is whatever the user
// drew (grown if a fat peg now needs more). A pinned run axis only grows.
function sizePostToRow(one) {
  if (one.kind !== "post" || one.count == null) return;
  const resolved = state.draftResolvedOptions || {};
  const opts = one.options || {};
  const diameter = number(opts.diameter ?? resolved.diameter, 12);
  const spacing = Math.max(0, number(opts.spacing ?? resolved.spacing, 4));
  const count = Math.max(1, Math.round(one.count));
  if (!(diameter > 0)) return;
  const runNeeded = Math.ceil(count * diameter + (count - 1) * spacing - 1e-6);
  const acrossNeeded = Math.ceil(diameter - 1e-6);
  const along = one.along === "y" ? "y" : "x";
  const runKey = along === "x" ? "width" : "depth";
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curRun = along === "x" ? curW : curD;
  const curAcross = along === "x" ? curD : curW;
  const run = state.pinnedZone[runKey] ? Math.max(curRun, runNeeded) : runNeeded;
  const across = Math.max(curAcross, acrossNeeded);
  const width = along === "x" ? run : across;
  const depth = along === "x" ? across : run;
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;
  applyResizedZone(one, cx, cy, width, depth);
}

// The slot-bank twin. feature_min_footprint()'s slot branch: pitch is
// (thickness + wall) / cos(angle); the across axis holds count of them plus a
// half-slot and a wall each end; the run axis is left as drawn (slots span it
// minus walls). Count on "auto" is the fitter's. A pinned across axis only
// grows.
function sizeSlotToBank(one) {
  if (one.kind !== "slot" || one.count == null) return;
  const resolved = state.draftResolvedOptions || {};
  const opts = one.options || {};
  const thickness = number(opts.thickness ?? resolved.thickness, 4);
  const wall = number(opts.wall ?? resolved.wall, 1.6);
  const angle = Math.min(45, Math.abs(number(opts.angle ?? resolved.angle, 20)));
  const cosA = Math.cos(angle * Math.PI / 180);
  if (!(thickness > 0) || !(wall > 0) || !(cosA > 0)) return;
  const count = Math.max(1, Math.round(one.count));
  const pitch = (thickness + wall) / cosA;
  const amplitude = number(state.catalog?.wall_rules?.wave_amplitude_mm, 0.4);
  const waveReach = (opts.wall_style ?? resolved.wall_style) === "wavy" ? 2 * amplitude : 0;
  const acrossNeeded = Math.ceil((count - 1) * pitch + thickness / cosA + 2 * wall + waveReach - 1e-6);
  const along = one.along === "y" ? "y" : "x";
  const acrossKey = along === "x" ? "depth" : "width";
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const curW = one.zone[2] - one.zone[0];
  const curD = one.zone[3] - one.zone[1];
  const curAcross = along === "x" ? curD : curW;
  const curRun = along === "x" ? curW : curD;
  const across = state.pinnedZone[acrossKey] ? Math.max(curAcross, acrossNeeded) : acrossNeeded;
  const width = along === "x" ? curRun : across;
  const depth = along === "x" ? across : curRun;
  if (Math.abs(width - curW) < 0.05 && Math.abs(depth - curD) < 0.05) return;
  applyResizedZone(one, cx, cy, width, depth);
}

// Set one.zone to width x depth about (cx, cy), nudged back inside the bin when
// it still fits, and push the matching Width / Length fields. Shared by the
// post / slot sizers (the bore sizer inlines the same steps).
function applyResizedZone(one, cx, cy, width, depth) {
  const prevW = one.zone[2] - one.zone[0];
  const prevD = one.zone[3] - one.zone[1];
  const [insideX, insideY] = binInsideExtent(state.design.box);
  const place = (centre, span, inside) => {
    if (span >= inside) return centre;
    const half = span / 2;
    return Math.min(Math.max(centre, -inside / 2 + half), inside / 2 - half);
  };
  const ncx = place(cx, width, insideX);
  const ncy = place(cy, depth, insideY);
  one.zone = [ncx - width / 2, ncy - depth / 2, ncx + width / 2, ncy + depth / 2];
  const widthField = $('[data-draft="width"]', $("#draft-fields"));
  if (widthField && Math.abs(width - prevW) >= 0.05) { widthField.value = fmt(width); flashField(widthField); }
  const depthField = $('[data-draft="depth"]', $("#draft-fields"));
  if (depthField && Math.abs(depth - prevD) >= 0.05) { depthField.value = fmt(depth); flashField(depthField); }
}

// A manual Width, Length, or layout edit turns Automatic footprint sizing off
// for any Photo Nest in the design - it never silently fights a footprint the
// user just typed. Height is independent: it never triggers this, and never
// gets turned off by it. Only the new explicit "true" is affected; a legacy
// design with no stored preference keeps its historical grow-only behaviour,
// and an already-Manual Nest is already what this asks for.
function turnOffNestAutoSizeForManualEdit() {
  const candidates = [];
  if (state.draft?.kind === "nest") candidates.push(state.draft);
  for (const feature of state.design?.layout?.features || []) {
    if (feature.kind === "nest" && feature !== state.draft) candidates.push(feature);
  }
  let turnedOff = false;
  for (const one of candidates) {
    one.options ||= {};
    if (one.options.auto_size === true) {
      one.options.auto_size = false;
      turnedOff = true;
    }
  }
  if (turnedOff) {
    toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
    if (state.draft?.kind === "nest") renderDraftFields();
  }
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The selected photo could not be read."));
    reader.readAsDataURL(file);
  });
}

function setNestPhotoReference(reference) {
  if (!reference?.image || !Array.isArray(reference.bounds) || reference.bounds.length !== 4) {
    state.nestPhoto = null;
    return;
  }
  const image = new Image();
  const photo = { image, bounds: reference.bounds.map(value => number(value)) };
  state.nestPhoto = photo;
  image.addEventListener("load", renderLayout2D, { once: true });
  image.addEventListener("error", () => {
    if (state.nestPhoto === photo) state.nestPhoto = null;
  }, { once: true });
  image.src = reference.image;
}

function _nestMeasuredThickness(options) {
  const raw = options?.tool_thickness ?? options?.depth;
  const value = number(raw, NaN);
  return Number.isFinite(value) && value > 0 ? value : null;
}

async function uploadNestPhoto(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const input = event.target;
  input.value = "";
  const uploadRequest = ++state.nestTraceRequest;
  const extension = file.name.split(".").pop()?.toLowerCase();
  const mimeByExtension = { jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp" };
  const mimeType = file.type || mimeByExtension[extension];
  if (!mimeType || !["image/jpeg", "image/png", "image/webp"].includes(mimeType)) {
    toast("Choose a JPG, JPEG, PNG, or WEBP photo.", true, 5000);
    return;
  }
  if (file.size > 17_000_000) {
    toast("The photo must be smaller than 17 MB.", true, 5000);
    return;
  }
  let image;
  try {
    image = await readFileDataUrl(file);
  } catch (error) {
    toast(error.message, true, 5000);
    return;
  }
  if (uploadRequest !== state.nestTraceRequest
      || state.draft?.kind !== "nest" || state.draftKind !== "nest") return;
  $('.view-tab[data-view="2d"]')?.click();
  setLayoutOrientation("topup");
  // Choosing a photo starts analysis immediately - Tool thickness is a
  // separate field the user can fill in while it runs (spec section 1).
  // Whichever finishes last triggers finalization (finishPhotoNestIfReady).
  resetNestPhotoSession();
  state.nestOriginalImage = { dataUrl: image, mimeType };
  renderDraftFields();
  await runNestTrace();
}

function markDraftChanged() {
  // Invalidate an auto-save immediately, at the moment the user changes the
  // visible draft. Waiting for the debounced rebuild leaves a short window in
  // which the older response can replace the newer edit.
  state.draftTouched = true;
  state.draftRequest += 1;
  state.canGenerate = false;
  updateGenerateAvailability();
}

// Pocket, Bore and Slot all need a solid floor below their cut. The field the
// user is editing owns the decision; adjust its counterpart once, without
// dispatching another input event or allowing an A -> B -> A update loop.
function keepCutBelowHeight(one, changedKey, gap = 2) {
  if (!one || !["pocket", "bore", "slot"].includes(one.kind) ||
      !["depth", "height"].includes(changedKey)) return;
  // A Bore Base cavity may be exactly as deep as the Bore is tall - it then
  // reaches the normal bin floor - so it needs no raised floor. Walls Only has
  // no hole depth at all. Pocket and Slot keep their 2 mm floor.
  if (one.kind === "bore") {
    if (boreWallsOnly(boreStyleOf(one))) return;
    gap = 0;
  }
  if (changedKey === "depth") {
    const depth = number(one.options.depth, 0);
    const height = number(
      one.options.height ?? state.draftResolvedOptions?.height, depth + gap,
    );
    if (depth > 0 && height < depth + gap) {
      one.options.height = depth + gap;
      const field = $('[data-draft="option:height"]', $("#draft-fields"));
      if (field) { field.value = fmt(one.options.height); flashField(field); }
    }
    return;
  }
  const height = number(one.options.height, 0);
  const depth = number(one.options.depth ?? state.draftResolvedOptions?.depth, 0);
  if (height > gap && depth >= height - gap) {
    one.options.depth = Math.max(0.1, height - gap);
    const field = $('[data-draft="option:depth"]', $("#draft-fields"));
    if (field) { field.value = fmt(one.options.depth); flashField(field); }
  }
}

function updateDraftFromFields(event) {
  bumpBoreEpoch();
  const previousConflictDesign = clone(state.design);
  const previousDraftForConflict = clone(state.draft);
  const previousDraftAutoCommit = state.draftAutoCommit;
  const previousDraftTouched = state.draftTouched;
  const previousCanGenerate = state.canGenerate;
  // Any deliberate edit is a strong enough signal to start saving this draft
  // as it goes, even if the app put it up on its own (see state.draftAutoCommit).
  state.draftAutoCommit = true;
  state.draftTouched = true;
  markDraftChanged();
  const one = state.draft;
  const get = key => $(`[data-draft="${key}"]`, $("#draft-fields"))?.value;
  const oldZone = one.zone;
  const oldCx = (oldZone[0] + oldZone[2]) / 2;
  const oldCy = (oldZone[1] + oldZone[3]) / 2;
  const oldWidth = oldZone[2] - oldZone[0];
  const oldDepth = oldZone[3] - oldZone[1];
  const cx = number(get("cx"), oldCx);
  const cy = number(get("cy"), oldCy);
  const isPocket = one.kind === "pocket";
  const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
  const oldStyle = one.options?.wall_style ?? state.draftResolvedOptions?.wall_style ?? "straight";
  const oldReach = isPocket ? pocketWallReach(wall, oldStyle) : 0;
  let width = Math.max(0.1, number(get("width"), isPocket ? oldWidth - 2 * oldReach : oldWidth));
  let depth = Math.max(0.1, number(get("depth"), isPocket ? oldDepth - 2 * oldReach : oldDepth));
  if (isPocket) {
    width = width + 2 * oldReach;
    depth = depth + 2 * oldReach;
  }
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
  const info = partInfo();
  const changed = event?.currentTarget?.dataset?.draft || "";
  if (["divider", "pocket", "slot"].includes(one.kind) && changed === "option:wall_style") {
    one.options.wall_style = get(changed) === "wavy" ? "wavy" : "straight";
    if (isPocket) {
      const reach = pocketWallReach(wall, one.options.wall_style);
      const insideW = Math.max(0.1, oldWidth - 2 * oldReach);
      const insideD = Math.max(0.1, oldDepth - 2 * oldReach);
      one.zone = [cx - insideW / 2 - reach, cy - insideD / 2 - reach,
        cx + insideW / 2 + reach, cy + insideD / 2 + reach];
    }
  }
  if (info.flags.qty && one.kind !== "divider" && changed === "count") {
    const count = String(get("count") ?? "auto").trim().toLowerCase();
    one.count = one.kind === "steps"
      ? Math.max(1, Math.round(number(count, 3)))
      : (count === "" || count === "auto" ? null : Math.max(1, Math.round(number(count, 1))));
    if (changed === "count" && one.count != null) {
      const autoUnit = event?.currentTarget?.closest("label")?.querySelector(".unit");
      if (autoUnit?.textContent === "Auto") autoUnit.textContent = "";
    }
  }
  if (info.flags.alternate) {
    one.alternate_ends = get("alternate_ends") === "alternate";
  }
  if (info.flags.item) {
    const item = one.item || starterItem();
    const isCradle = one.kind === "cradle";
    // No holder editor names the tool any more; keep whatever is stored so the
    // engine still has a label for its error messages.
    item.name = item.name || "Custom item";
    const previousProfile = item.profile;
    item.profile = isCradle ? "round" : (get("profile") || "round");
    // Leaving a locked hex-bit profile: drop its fixed 6.35 / 0.25 back to
    // ordinary editable defaults rather than carrying them over.
    const leftHexBit = isHexBitProfile(previousProfile) && !isHexBitProfile(item.profile);
    if (!isCradle && isHexBitProfile(item.profile)) {
      // Size, length and fit are fixed for a hex bit - the fields are locked,
      // so take the preset regardless of what the disabled inputs read.
      const preset = HEX_BIT_PROFILES[item.profile];
      item.clearance = preset.clearance;
      item.segments = [{ length: preset.length, diameter: preset.diameter }];
      delete one.options?.angle;   // a hex bit always stands straight up
      delete one.options?.angle_towards;
    } else {
      // A cradle ignores fit slack entirely, so it has no clearance field -
      // keep the stored value at 0 rather than a stale 0.4 nothing reads.
      item.clearance = isCradle ? 0
        : one.kind === "bore" ? 0.25
        : leftHexBit ? 0.4
        : number(get("clearance"), item.clearance ?? 0.4);
      item.segments = [{
        length: number(get("item_length"), item.segments?.[0]?.length || 40),
        diameter: leftHexBit ? 6 : number(get("item_diameter"), item.segments?.[0]?.diameter || 6),
      }];
    }
    one.item = item;
  }
  one.options ||= {};
  if (one.kind === "cradle") {
    delete one.options.floor_gap;
  }
  if (one.kind === "bore") {
    const toward = get("option:angle_towards");
    if (toward !== undefined) one.options.angle_towards = toward;
    else delete one.options.angle_towards;
    // Style and sizing choices are words, never numbers.
    if (changed === "option:bore_style") {
      const previousStyle = boreStyleOf(one);
      const resolvedHeight = number(one.options.height ?? state.draftResolvedOptions?.height, NaN);
      const chosen = normalizeBoreStyle(get(changed));
      one.options.bore_style = chosen;
      delete one.options.wall_style;
      // Base - Wavy Walls and both Walls Only styles stand upright.
      if (chosen !== "base_straight") {
        delete one.options.angle;
        delete one.options.angle_towards;
      }
      // Wall Thickness belongs to Walls Only; a Base style returns to its
      // internal default and a Walls Only style to the bin wall.
      delete one.options.wall;
      if (boreWallsOnly(chosen) && !boreWallsOnly(previousStyle)) {
        // Switching to Walls Only sizes the bin to the Bore by default.
        one.options.xy_size_mode = "bin_to_bore";
      } else if (!boreWallsOnly(chosen) && boreWallsOnly(previousStyle)) {
        // Walls Only -> Base keeps a cavity that reaches the normal bin floor:
        // Hole Depth becomes the Bore's resolved Height.
        if (Number.isFinite(resolvedHeight)) {
          one.options.depth = resolvedHeight;
          if (boreHeightMode(one) !== "bore_to_bin") one.options.height = resolvedHeight;
        }
        if (one.options.xy_size_mode === "bin_to_bore") delete one.options.xy_size_mode;
      }
    }
    if (changed === "option:xy_size_mode") {
      const before = boreXyMode(one);
      const chosen = get(changed);
      one.options.xy_size_mode = chosen;
      if (chosen === "manual" && before !== "manual") {
        // Leaving an automatic mode keeps its current size as the manual Base.
        pinDraftAxis("width");
        pinDraftAxis("depth");
        if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
      } else {
        delete state.pinnedZone.width;
        delete state.pinnedZone.depth;
      }
    }
    if (changed === "option:height_size_mode") {
      const before = boreHeightMode(one);
      const chosen = get(changed);
      one.options.height_size_mode = chosen;
      const resolvedHeight = number(state.draftResolvedOptions?.height, NaN);
      if (chosen === "bore_to_bin") delete one.options.height;
      else if (before === "bore_to_bin" && Number.isFinite(resolvedHeight)) {
        // Leaving "bore to bin" keeps the height it resolved to as the visible number.
        one.options.height = resolvedHeight;
      }
    }
  }
  if (one.kind === "nest") {
    if (changed === "nest-count") one.count = Math.max(1, Math.min(20, Math.round(number(get("nest-count"), 1))));
    if (changed === "nest-orientation") {
      const angle = number(get("nest-orientation"), NaN);
      if ([0, 90, 180, 270].includes(angle)) one.rotation = angle;
    }
    if (changed === "nest-alternate") one.alternate_ends = event.currentTarget?.checked === true;
    if (changed === "option:repeat_spacing_percent") {
      const spacing = Math.round(number(get("option:repeat_spacing_percent"), NaN));
      if ([-100, -75, -50, -25, 0, 25, 50, 75, 100].includes(spacing)) one.options.repeat_spacing_percent = spacing;
    }
    applyNestAccessOptions(one.options, changed, get);
    // holder_style is a legacy-compatibility marker: absence of it means a
    // true legacy Photo Nest that must keep its exact old geometry. A Nest
    // that has never had one stored must not silently acquire it just
    // because some unrelated field changed - only a deliberate Holder edit
    // (or a Nest that already has one, i.e. every new-format Nest) may
    // create/update it.
    const holderStyleValue = get("option:holder_style");
    if (holderStyleValue !== undefined && (changed === "option:holder_style"
        || Object.prototype.hasOwnProperty.call(one.options, "holder_style"))) {
      one.options.holder_style = holderStyleValue;
    }
    // Switching Holder resets whatever the previous style's advanced/Push
    // Out state was, so a stale push_out never survives a jump to Recessed.
    if (changed === "option:holder_style" && one.options.holder_style === "recessed"
        && one.options.lift_assist === "push_out") {
      one.options.lift_assist = "auto";
    }
    // Only write auto_size when its own checkbox was the thing that changed -
    // it is a three-way stored preference (true/false/legacy-missing), and
    // any other field edit must leave "missing" as missing rather than
    // silently upgrading a legacy design to full Auto-size.
    if (changed === "option:auto_size") {
      const autoSizeBox = $('[data-draft="option:auto_size"]', $("#draft-fields"));
      one.options.auto_size = autoSizeBox?.checked === true;
    }
  }
  // Text carries the only options that are not numbers: what it says, and its
  // placement choice. Read them straight off their own controls.
  if (info.flags.text) {
    const fields = $("#draft-fields");
    const said = $('[data-draft="option:text"]', fields);
    if (said) {
      one.options.text = said.value;
      seedPartNameFromText(one);
    }
    one.options.level = get("option:level") === "rim" ? "rim" : "base";
    if (one.options.level === "rim") {
      one.options.rim_side = get("option:rim_side") || one.options.rim_side || "back";
      delete one.options.auto;
      delete one.options.raised;
      delete one.options.quarter_turns;
      delete one.options.cap_height;
      delete one.options.depth;
    } else {
      delete one.options.rim_side;
      one.options.auto = $('[data-draft="option:auto"]', fields)?.checked === true;
      if (changed === "option:auto" && one.options.auto) {
        // Handing placement back to the engine: drop the hand-set letter height
        // so it can pick the biggest that fits wherever it lands.
        delete one.options.cap_height;
        const capField = $('[data-draft="option:cap_height"]', fields);
        if (capField) capField.value = "";
      }
    }
    syncRimLabelFromFeatures();
    const conflict = newModifierConflict(previousConflictDesign, state.design);
    if (conflict) {
      state.design = previousConflictDesign;
      state.draft = previousDraftForConflict;
      state.draftAutoCommit = previousDraftAutoCommit;
      state.draftTouched = previousDraftTouched;
      state.canGenerate = previousCanGenerate;
      syncForm();
      renderDraftFields();
      updateGenerateAvailability();
      toast(conflict.message, true, 6000);
      return;
    }
  }
  // A Divider's bottom is one construction mode. Translate that visible choice
  // into its established saved options so older designs stay compatible.
  if (one.kind === "divider") {
    const fields = $("#draft-fields");
    const bottomMode = get("option:bottom_mode") || "flat";
    if (bottomMode === "slope") {
      one.options.slope_base = true;
      delete one.options.scoop;
      if (!Object.prototype.hasOwnProperty.call(one.options, "bottom_angle")) one.options.bottom_angle = 20;
    } else if (bottomMode === "scoop") {
      one.options.scoop ||= {};
      for (const key of ["slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom", "minimal_bottom", "bottom_supports"]) delete one.options[key];
    } else {
      for (const key of ["slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom", "minimal_bottom", "bottom_supports", "scoop"]) delete one.options[key];
    }
    for (const key of ["alternate_bottom", "label_divisions"]) {
      const boxEl = $(`[data-draft="option:${key}"]`, fields);
      if (!boxEl) continue;
      if (boxEl.checked) one.options[key] = true;
      else delete one.options[key];
    }
    if (bottomMode === "slope") {
      if (get("option:slope_construction") === "crossbars") one.options.minimal_bottom = true;
      else {
        delete one.options.minimal_bottom;
        delete one.options.bottom_supports;
      }
    }
    if (!one.options.label_divisions) {
      delete one.options.division_level;
      delete one.options.division_labels;
      delete one.options.division_side;
    } else {
      one.options.division_level = get("option:division_level") === "rim" ? "rim" : "base";
      if (one.options.division_level === "rim") {
        one.options.division_side = get("option:division_side") || one.options.division_side || "back";
      } else delete one.options.division_side;
    }
  }
  if (changed.startsWith("option:") &&
      !["text", "auto", "raised", "reverse_bottom", "alternate_bottom", "minimal_bottom",
        "slope_base", "bottom_mode", "slope_construction", "label_divisions", "division_level", "division_side", "division_labels",
        "level", "rim_side",
        "lift_assist", "finger_position", "push_position", "angle_towards",
        "bore_style", "wall_style", "xy_size_mode", "height_size_mode", "holder_style", "auto_size", "repeat_spacing_percent"]
        .includes(changed.slice("option:".length))) {
    const key = changed.slice("option:".length);
    const option = info.fields.find(entry => entry.key === key);
    const previousGridCount = info.kind === "divider" && (key === "count_x" || key === "count_y")
      ? Math.max(0, Math.round(number(one.options?.[key], 0))) : null;
    const raw = String(get(changed) ?? "").trim();
    if (raw === "") delete one.options[key];
    else {
      let value = number(
        raw,
        one.options[key] ?? state.draftResolvedOptions?.[key] ?? number(option?.default),
      );
      // Bore geometry stores lean away from vertical. The user sees the more
      // natural absolute angle: 90 is straight up and down.
      if (info.kind === "bore" && key === "angle") {
        value = 90 - Math.min(90, Math.max(20, value));
      }
      // A bore's grid counts are whole numbers.
      if (info.kind === "bore" && (key === "columns" || key === "rows")) {
        value = Math.max(1, Math.round(value));
        const autoUnit = event?.currentTarget?.closest("label")?.querySelector(".unit");
        if (autoUnit?.textContent === "Auto") autoUnit.textContent = "";
      }
      // A grid divider's wall counts are whole numbers, zero or more.
      if (info.kind === "divider" && (key === "count_x" || key === "count_y")) {
        value = Math.max(0, Math.round(value));
      }
      if (info.kind === "cradle" && key === "spacing") value = Math.max(0, value);
      one.options[key] = value;
    }
    // A hand-set letter height means the user is placing it themselves.
    if (info.flags.text && key === "cap_height" && raw !== "") {
      one.options.auto = false;
      const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
      if (autoField) autoField.checked = false;
    }
    if (info.kind === "divider" && key === "thickness") {
      widenDividerFootprint(one);
    }
    // Once either grid quantity is set, the divider is a grid: pin both
    // quantities and drop the old single-direction count so nothing double-builds.
    // An older Divider may have only its one-axis count. Its first grid edit
    // begins at one wall on the other axis rather than silently replacing it.
    if (info.kind === "divider" && (key === "count_x" || key === "count_y")) {
      const otherKey = key === "count_x" ? "count_y" : "count_x";
      if (!Object.prototype.hasOwnProperty.call(one.options, otherKey)) {
        one.options[otherKey] = 1;
      }
      if ("count_x" in one.options || "count_y" in one.options) {
        one.options.count_x = Math.max(0, Math.round(number(one.options.count_x, 0)));
        one.options.count_y = Math.max(0, Math.round(number(one.options.count_y, 0)));
        one.count = null;
      }
      const nextGridCount = Math.max(0, Math.round(number(one.options[key], 0)));
      if (previousGridCount !== nextGridCount && one.options.compartment_spans?.length) {
        delete one.options.compartment_spans;
        state.dividerSegmentHover = null;
        toast("Custom compartment merges reset because the divider grid changed.");
      }
    }
    if (info.kind === "pocket" && key === "wall") {
      // Use the live pre-edit wall/reach already captured at the top of this
      // event (`wall`/`oldStyle`/`oldReach`), never the async
      // draftResolvedOptions - that can still lag the live draft while a
      // prior 220 ms preview is in flight, which would subtract the wrong
      // prior reach on rapid edits and drift the inside Width/Length.
      const newWall = number(one.options.wall, 1.6);
      const nextReach = pocketWallReach(newWall, oldStyle);
      const innerW = Math.max(0.1, oldWidth - 2 * oldReach);
      const innerD = Math.max(0.1, oldDepth - 2 * oldReach);
      const newW = innerW + 2 * nextReach;
      const newD = innerD + 2 * nextReach;
      one.zone = [cx - newW / 2, cy - newD / 2, cx + newW / 2, cy + newD / 2];
    }
    keepCutBelowHeight(one, key);
    if (info.kind === "bore" && key === "angle" && !("wall" in (one.options || {}))) {
      // A leaned bore defaults to a thicker wall (engine: BORE_TILTED_WALL);
      // reflect that in the field right away when Wall hasn't been hand-set.
      const wallField = $('[data-draft="option:wall"]', $("#draft-fields"));
      if (wallField) {
        const nextWall = number(one.options.angle, 0) > 0 ? "3" : "1.6";
        if (wallField.value !== nextWall) { wallField.value = nextWall; flashField(wallField); }
      }
    }
    if (one.kind === "nest" && key === "cavity_depth" && raw !== "") {
      // A hand-typed cavity depth means Manual; it stops following Tool
      // thickness until Reset to 60% is pressed.
      one.options.cavity_depth_mode = "manual";
    }
    // The trace may already be done and waiting only on this measurement.
    if (one.kind === "nest" && key === "tool_thickness" && state.nestTraceResult
        && _nestMeasuredThickness(one.options) != null) {
      finishPhotoNestIfReady();
    }
  }
  if (one.kind === "cradle" && (
    changed === "count" || changed === "item_length" || changed === "item_diameter" ||
    changed === "alternate_ends" || changed === "option:spacing" ||
    changed === "option:end_margin" || changed === "option:run_offset"
  )) sizeCradleToItem(one);
  // Any hole parameter that moves the grid's footprint - the X / Y counts, the
  // hole size, the wall between holes, or the lean that adds sideways reach -
  // re-fits the Base block to that grid. Runs before the profile re-render
  // below so the refreshed Width / Length fields show the new size.
  if (one.kind === "bore" && (
    changed === "option:columns" || changed === "option:rows" ||
    changed === "option:depth" || changed === "option:wall" ||
    changed === "option:angle" || changed === "item_diameter" ||
    changed === "clearance" || changed === "profile" || changed === "along" ||
    changed === "option:angle_towards" ||
    changed === "option:bore_style" || changed === "option:xy_size_mode" ||
    changed === "option:height_size_mode"
  )) sizeBoreToGrid(one);
  if (one.kind === "bore" && (changed === "option:bore_style" ||
      changed === "option:xy_size_mode" || changed === "option:height_size_mode")) {
    renderDraftFields();
  }
  // The peg row and the slot bank track their own contents the same way the
  // bore base tracks its grid: change the count, peg size, gap, slot pitch or
  // lean and the zone re-fits (grow or shrink) on the driven axis.
  if (one.kind === "post" && (
    changed === "count" || changed === "option:diameter" ||
    changed === "option:spacing" || changed === "along"
  )) sizePostToRow(one);
  if (one.kind === "slot" && (
    changed === "count" || changed === "option:thickness" ||
    changed === "option:wall" || changed === "option:angle" || changed === "along" ||
    changed === "option:wall_style"
  )) sizeSlotToBank(one);
  // A hand-typed Base Width / Length pins that axis: from now on the contents
  // sizers only ever grow it to fit, never shrink or overwrite the number.
  if (info.flags.size && (changed === "width" || changed === "depth")) {
    pinDraftAxis(changed);
    if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
  }
  // Changing End layout swaps the field beneath Runs along between
  // "From ends" and "Offset from center".
  if (changed === "alternate_ends") renderDraftFields();
  // Switching a bore's profile swaps which fields show (locked hex-bit size,
  // the Angle field for round/square only).
  if ((changed === "profile" || changed === "option:angle") && one.kind === "bore") renderDraftFields();
  if ((changed === "option:lift_assist" || changed === "option:holder_style") && one.kind === "nest") renderDraftFields();
  if (changed === "option:level") renderDraftFields();
  if (one.kind === "divider" && (
    changed === "option:bottom_mode" || changed === "option:slope_construction" || changed === "option:label_divisions" ||
    changed === "option:division_level" || changed === "count" ||
    changed === "option:count_x" || changed === "option:count_y"
  )) renderDraftFields();
  if (one.kind === "post" && changed === "count") renderDraftFields();
  updateSelectionButtons();
  renderLayout2D();
  refreshDraftSoon();
}

const refreshDraftSoon = debounce(refreshDraft, 220);

async function refreshDraft() {
  if (!state.draft) return;
  if (state.draft.kind === "nest" && !state.draft.contour) {
    $("#draft-status").textContent = "Upload one part photo to create the cavity outline.";
    $("#draft-status").classList.remove("error");
    refreshPreview();
    return;
  }
  // A divider always splits the whole bin, so keep its footprint pinned to
  // the usable inside - re-stretched here every rebuild, which is what makes
  // the walls re-space evenly after the bin is resized (or a wall lean is
  // added, which needs more room between centres). Matches how default_feature
  // first lays a divider out. Its run axis reaches past this rectangle to the
  // wavy wall on its own; this only sets the axis the walls divide.
  if (state.draft.kind === "divider") {
    const [insideX, insideY] = dividerLayoutExtent(state.design.box);
    state.draft.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  }
  applyBoreSizing(state.draft);
  bumpBoreEpoch();
  const request = ++state.draftRequest;
  if (state.draft.kind === "nest") {
    $("#draft-status").textContent = "Resizing bin around cavity…";
    if (state.draftAutoCommit && !(await autoCommitDraft(request))) {
      refreshPreview();
      return;
    }
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    refreshPreview();
    return;
  }
  $("#draft-status").textContent = "Rebuilding…";
  try {
    const index = draftCommitIndex();
    const result = await api("/api/feature/draft", {
      design: state.design, feature: state.draft,
      ...(index === false ? {} : { index }),
    });
    if (request !== state.draftRequest) return;
    state.draftResolvedOptions = result.resolved_options || {};
    // The server's usable layout area is the authority for "bore to bin".
    if (state.draft.kind === "bore" && boreXyMode(state.draft) === "bore_to_bin"
        && !boreWallsOnly(boreStyleOf(state.draft))
        && Array.isArray(result.feature?.zone)) {
      state.draft.zone = result.feature.zone;
    }
    const info = partInfo();
    // The resolver now has the real item depth and lean. Re-size before saving
    // so Base always reflects the actual hole grid, not a stale preview size.
    if (info.kind === "bore") sizeBoreToGrid(state.draft);
    for (const option of info.fields) {
      if (Object.prototype.hasOwnProperty.call(state.draft.options || {}, option.key)) continue;
      const input = $(`[data-draft="option:${option.key}"]`, $("#draft-fields"));
      // Don't overwrite a field the user is still typing in - clearing it to
      // retype briefly drops the key from options, and stomping the auto value
      // back in mid-edit is exactly what makes a 16->20 change snap back to 16.
      if (input && input === document.activeElement) continue;
      if (input && option.type !== "enum"
          && Object.prototype.hasOwnProperty.call(state.draftResolvedOptions, option.key)) {
        const value = state.draftResolvedOptions[option.key];
        const next = fmt(info.kind === "bore" && option.key === "angle" ? 90 - number(value, 0) : value);
        if (input.value !== next) {
          input.value = next;
          flashField(input);
        }
      }
    }
    if (info.flags.qty && state.draft.count == null) {
      const input = $('[data-draft="count"]', $("#draft-fields"));
      const next = String(resolvedDraftCount(state.draft));
      if (input && input.value !== next) {
        input.value = next;
        flashField(input);
      }
    }
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    if (state.draftAutoCommit) await autoCommitDraft(request);
    // "Auto size bin to bore" (Width / Length or Height) keeps the bin fitted to
    // this Bore after every edit.
    if (request === state.draftRequest && await reconcileBoreBin(result)) return;
  } catch (error) {
    if (request !== state.draftRequest) return;
    // A part whose contents outgrew the bin: grow the bin around it instead of
    // stopping at the error, so "put 10 x 10 holes in a stock bin" (or a longer
    // tool, more pegs, more slots) just resizes the bin the way the "Grow the
    // bin" button would. Guarded so the expand's own rebuild can't loop back in.
    const outgrewBin = new RegExp(
      "reaches outside the bin|bores need|posts need|slots? need|zone is too small" +
      "|the zone (only )?runs|mm long but the zone|layout area|does not fit in|overlap|tool reaches the side",
      "i",
    ).test(error.message || "");
    const growKinds = new Set(["bore", "post", "slot", "cradle", "pocket", "steps"]);
    if (growKinds.has(state.draft?.kind) && outgrewBin && !state.autoGrowingBin) {
      state.autoGrowingBin = true;
      try {
        // A Bore that sizes the bin around itself lands on the smallest fit, so
        // the bin shrinks as well as grows to meet it.
        await autoExpandBin({
          keepDraft: true,
          fit: state.draft.kind === "bore" && boreXyMode(state.draft) === "bin_to_bore",
        });
      } finally {
        state.autoGrowingBin = false;
        flushBoreReconcile();
      }
      return;
    }
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    state.fitError = true;
    updateAutoExpandButton();
  }
  refreshPreview();
}

// Anything that is only a size - "8", "12mm" - names a compartment, not the
// part, so it never becomes the filename.
const SIZE_LIKE_TEXT = /^\s*\d+(\.\d+)?\s*(mm)?\s*$/i;

// The first real piece of lettering fills in a blank Part Name, once. After
// that the two are independent: renaming either never touches the other, so a
// bin can say "M3" on the floor and still save as "Driver rack".
function seedPartNameFromLabel(said) {
  const partInput = $("#part-name");
  if (!partInput) return;
  if (partInput.value.trim() !== "" && document.activeElement === partInput) return;
  const tidy = String(said ?? "").trim();
  if (!tidy || SIZE_LIKE_TEXT.test(tidy)) return;
  partInput.value = tidy;
  if (state.design) state.design.part_name = tidy;
}

// "Real" means the user typed it. A text part starts life with placeholder
// lettering so it is valid and visible the moment it is added, and naming
// every file after that placeholder would be worse than leaving it blank.
function seedPartNameFromText(one) {
  if (!one || one.kind !== "text") return;
  const said = String(one.options?.text ?? "").trim();
  if (said === String(state.draftStartingText ?? "").trim()) return;
  seedPartNameFromLabel(said);
}

// Where /api/feature/apply should land the current draft:
//   number -> update that already-placed support in place
//   null   -> append it as a brand-new support (a fresh palette draft only)
//   false  -> don't commit: the canvas selection was cleared while editing a
//             placed support, and appending would duplicate it
function draftCommitIndex() {
  if (state.selected !== null) return state.selected;
  if (state.draftIsNew) return null;
  if (Number.isInteger(state.draftSourceIndex) &&
      state.draftSourceIndex < state.design.layout.features.length) {
    return state.draftSourceIndex;
  }
  return false;
}

// Saves the draft into the design as its own feature (or updates it in
// place if it's already one) - the "auto add" half of the workflow: once a
// draft is armed (state.draftAutoCommit), every valid edit lands here
// instead of waiting for an explicit button click. Normal success stays
// silent so it never interrupts active typing; an automatic correction is
// explained once, and a failure (e.g. overlap, which the
// single-feature check above can't see) just shows in draft-status like any
// other validation error.
async function autoCommitDraft(request) {
  if (state.draft?.kind === "nest" && !state.draft.contour) return false;
  const index = draftCommitIndex();
  if (index === false) return false;   // stale edit - don't append a duplicate
  try {
    const wasNew = state.draftIsNew;
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    if (request !== state.draftRequest) return;
    state.design = result.design;
    seedPartNameFromText(state.draft);
    recordHistory(previousDesign);
    state.draftIsNew = false;
    state.draftTouched = false;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    if (state.selected === null && wasNew) state.selected = result.selected;
    // Saved support zones snap to the grid. Without this sync the preview
    // draws an almost-identical draft over the saved support, which is most
    // noticeable after changing a cradle row from one tool to two.
    if (state.selected !== null && state.design.layout.features[state.selected]) {
      state.draft = clone(state.design.layout.features[state.selected]);
    }
    if (state.draft?.kind === "nest") syncForm();
    for (const warning of result.warnings || []) toast(warning, false, 6500);
    renderPlaced();
    updateSelectionButtons();
    if (wasNew && state.draft?.kind !== "text") await maybePromptSurfaceObjectHeight();
    return true;
  } catch (error) {
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    return false;
  }
}

async function commitVisibleDraft() {
  if (!state.draft) return false;
  if (state.draft?.kind === "nest" && !state.draft.contour) return false;
  const index = draftCommitIndex();
  if (index === false) return false;
  if (Number.isInteger(index) &&
      JSON.stringify(state.design.layout.features[index]) === JSON.stringify(state.draft)) {
    return false;
  }
  const draft = state.draft;
  const snapshot = JSON.stringify(draft);
  const previousDesign = clone(state.design);
  state.draftRequest += 1;
  const committed = await api("/api/feature/apply", {
    design: state.design, feature: draft, index,
  });
  if (state.draft !== draft || JSON.stringify(draft) !== snapshot) {
    throw new Error("The interior part changed while it was being saved. Try again.");
  }
  state.design = committed.design;
  seedPartNameFromText(draft);
  recordHistory(previousDesign);
  state.draftIsNew = false;
  state.draftTouched = false;
  state.selected = committed.selected;
  if (Number.isInteger(committed.selected)) {
    state.draftSourceIndex = committed.selected;
    const saved = state.design.layout.features[committed.selected];
    if (saved) state.draft = clone(saved);
  }
  state.draftResolvedOptions = {};
  if (state.draft?.kind === "nest") syncForm();
  for (const warning of committed.warnings || []) toast(warning, false, 6500);
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
  if (typedSpaceOrdinaryBin()) refreshPreview();
  return true;
}

// True when the open draft holds work that switching parts would throw away:
// a new part the user has actually started, or edits to a placed part that
// haven't been saved back yet. An untouched suggestion the app put up on its
// own counts as nothing to lose.
function draftNeedsSaving() {
  if (!state.draft) return false;
  const index = draftCommitIndex();
  if (Number.isInteger(index)) {
    return JSON.stringify(state.design.layout.features[index]) !== JSON.stringify(state.draft);
  }
  // index is null (brand-new) or false (its row was cleared underneath it).
  return state.draftTouched === true;
}

// Gate every "switch to a different interior part" path. Returns true if the
// caller may go ahead and replace the draft, false if the user chose to stay
// and keep editing. Edits are auto-saved cleanly when valid; only an edit
// that cannot be saved prompts the user to discard or keep editing.
async function guardDraftSwitch() {
  if (!draftNeedsSaving()) return true;
  try {
    state.draftAutoCommit = true;
    await commitVisibleDraft();
    return true;
  } catch (error) {
    return promptDraftConflict(error.message);
  }
}

// The "discard this change?" dialog shown when an edit cannot be saved cleanly.
// Simple and intuitive: only 2 buttons ("Keep editing" or "Discard change").
function promptDraftConflict(reason) {
  return new Promise(resolve => {
    const dialog = $("#draft-switch-dialog");
    const titleEl = $("#draft-switch-title");
    const msgEl = $("#draft-switch-message");
    const reasonEl = $("#draft-switch-reason");
    const keepBtn = $("#draft-switch-keep");
    const discardBtn = $("#draft-switch-discard");
    const addBtn = $("#draft-switch-add");
    const title = partInfo(state.draft?.kind)?.title || "interior part";

    let done = false;
    const finish = proceed => {
      if (done) return;
      done = true;
      keepBtn.onclick = discardBtn.onclick = null;
      if (addBtn) addBtn.onclick = null;
      dialog.removeEventListener("cancel", onCancel);
      if (dialog.open) dialog.close();
      resolve(proceed);
    };
    const onCancel = event => { event.preventDefault(); finish(false); };

    reasonEl.textContent = reason || "";
    reasonEl.hidden = !reason;
    if (addBtn) addBtn.hidden = true;

    titleEl.textContent = "Discard this change?";
    msgEl.textContent = `Your last change to this ${title} can't be saved yet, so leaving it now will lose that change.`;
    discardBtn.textContent = "Discard change";

    keepBtn.onclick = () => finish(false);
    discardBtn.onclick = () => {
      const index = draftCommitIndex();
      if (Number.isInteger(index) && state.design.layout.features[index]) {
        state.draft = clone(state.design.layout.features[index]);
        state.draftTouched = false;
      }
      finish(true);
    };

    dialog.addEventListener("cancel", onCancel);
    if (!dialog.open) dialog.showModal();
  });
}

// ---- Reusable application confirmation dialog (Fix 019 Item 8). One shared
// implementation instead of one-off native confirm()s or duplicated custom
// dialogs. Resolves "primary" / "secondary" / "cancel" - Escape, the
// backdrop, and the dialog's own close all behave as "cancel". Danger
// actions use the existing danger button styling and move focus to Cancel
// (the safe default); ordinary actions move focus to the primary button.
function appConfirm({
  title, message,
  primaryLabel = "OK", secondaryLabel = null, cancelLabel = "Cancel",
  danger = false, secondaryDanger = false, checkboxLabel = null,
} = {}) {
  return new Promise(resolve => {
    const dialog = $("#app-confirm-dialog");
    const titleEl = $("#app-confirm-title");
    const msgEl = $("#app-confirm-message");
    const primaryBtn = $("#app-confirm-primary");
    const secondaryBtn = $("#app-confirm-secondary");
    const cancelBtn = $("#app-confirm-cancel");
    if (!dialog || !titleEl || !msgEl || !primaryBtn || !secondaryBtn || !cancelBtn) {
      // Markup missing (older cached HTML): fail safe to "cancel" rather
      // than silently proceeding with a destructive/ambiguous action.
      resolve("cancel");
      return;
    }

    const checkRow = $("#app-confirm-check-row");
    const checkBox = $("#app-confirm-check");
    if (checkRow && checkBox) {
      checkRow.hidden = !checkboxLabel;
      checkBox.checked = false;
      $("#app-confirm-check-label").textContent = checkboxLabel || "";
    }
    let done = false;
    const finish = choice => {
      if (done) return;
      done = true;
      // Read by callers that offered a checkbox (see appConfirm.checked).
      appConfirm.checked = Boolean(checkboxLabel && checkBox?.checked);
      primaryBtn.onclick = secondaryBtn.onclick = cancelBtn.onclick = null;
      dialog.removeEventListener("cancel", onCancel);
      if (dialog.open) dialog.close();
      resolve(choice);
    };
    const onCancel = event => { event.preventDefault(); finish("cancel"); };

    titleEl.textContent = title || "";
    msgEl.textContent = message || "";
    primaryBtn.textContent = primaryLabel;
    primaryBtn.classList.toggle("danger", danger);
    primaryBtn.classList.toggle("primary", !danger);
    cancelBtn.textContent = cancelLabel;
    if (secondaryLabel) {
      secondaryBtn.hidden = false;
      secondaryBtn.textContent = secondaryLabel;
      secondaryBtn.classList.toggle("danger", secondaryDanger);
    } else {
      secondaryBtn.hidden = true;
      secondaryBtn.classList.remove("danger");
    }

    primaryBtn.onclick = () => finish("primary");
    secondaryBtn.onclick = () => finish("secondary");
    cancelBtn.onclick = () => finish("cancel");

    dialog.addEventListener("cancel", onCancel);
    if (!dialog.open) dialog.showModal();
    // Focus always stays on a safe default - the primary action, or Cancel
    // when the primary itself is the dangerous one - never on a danger-
    // styled secondary button (e.g. "Discard & Switch").
    (danger ? cancelBtn : primaryBtn).focus();
  });
}

// Ordinary two-choice confirmation. Resolves true for the action, false for
// Cancel/Escape/backdrop.
async function appConfirmAction({ title, message, actionLabel = "OK", cancelLabel = "Cancel", danger = false }) {
  const choice = await appConfirm({ title, message, primaryLabel: actionLabel, cancelLabel, danger });
  return choice === "primary";
}

// Used only for committing a 2D-layout drag of an already-placed support -
// a discrete one-shot action, unlike the continuous autoCommitDraft above.
async function applySupport(index) {
  if (!state.draft || !beginDesignMutation()) return;
  try {
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    state.design = result.design;
    recordHistory(previousDesign);
    state.selected = result.selected;
    state.draftIsNew = false;
    state.draftTouched = false;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    state.draftResolvedOptions = {};
    if (state.draft.kind === "nest") syncForm();
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshPreview();
    refreshDraft();
    for (const warning of result.warnings || []) toast(warning, false, 6500);
    if (index === null && state.draft?.kind !== "text") await maybePromptSurfaceObjectHeight();
    return true;
  } catch (error) {
    toast(error.message, true, 5000);
    return false;
  } finally {
    finishDesignMutation();
  }
}

// Done flushes the latest valid edit, then exits editing. Persistence belongs
// to auto-add/auto-save; this action never appends a second copy.
async function saveCurrentPart() {
  if (state.modifierEditing) return saveEdgeMountPart();
  if (!state.draft || !beginDesignMutation()) return;
  try {
    await commitVisibleDraft();
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

async function saveEdgeMountPart() {
  const kind = state.modifierEditing;
  if (!kind) return;
  if (kind === "edge_mount" && ($("#edge-mount-label-mode")?.value || "none") === "none" &&
      !$("#edge-mount-holes-enabled")?.checked) {
    toast("Choose a Label or turn on Screw Mounting first.", true, 5000);
    return;
  }
  if (!beginDesignMutation()) return;
  try {
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
  if (state.draft && draftCommitIndex() !== index && !(await guardDraftSwitch())) return;
  if (!beginDesignMutation()) return;
  const deletingNest = state.design.layout.features[index]?.kind === "nest";
  let deleted = false;
  try {
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/delete", { design: state.design, index });
    state.design = result.design;
    if (deletingNest) resetNestPhotoSession();
    recordHistory(previousDesign);
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
}

function mutationControls() {
  return $$(
    '#x-size, #y-size, #z, #base-thickness, #wall-thickness, #part-name, ' +
    '#lift-grabber-size, #lift-grabber-location, #connector-height-mode, ' +
    '#mode-select, ' +
    '#lid-option-toggle, #lid-configuration, #lid-thickness, #lid-handle-type, #lid-handle-size, ' +
    '#lid-handle-position, #lid-label-enabled, #lid-label-orientation, #lid-label-style, #lid-label-text, ' +
    '#designer-new-bin, #designer-duplicate, ' +
    '#designer-save-file, #designer-open-file'
  );
}

function setMutationSurfacesInert(inert) {
  [$('header'), $('.controls')].forEach(surface => {
    if (surface) surface.inert = inert;
  });
}

function beginDesignMutation() {
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
  recordHistory(beforeForm);
  state.designMutationBusy = true;
  setMutationSurfacesInert(true);
  mutationControls().forEach(control => control.disabled = true);
  updateSelectionButtons();
  updateHistoryButtons();
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
  updateHistoryButtons();
  updateGenerateAvailability();
}

function updateSelectionButtons() {
  const busy = state.designMutationBusy;
  // The editor being open IS "editing mode" - set synchronously the moment a
  // part is picked, before its defaults have loaded. Browse state shows the
  // palette; edit state hides it while "Added to this bin" stays visible and
  // its selected row owns Done / Delete.
  const editing = !$(".support-editor").hidden;
  $("#support-palette").hidden = editing;
  const hasPlaced = placedPartCount() > 0;
  $$(".placed-block").forEach(placedBlock => { placedBlock.hidden = !hasPlaced; });
  const lockedDivider = state.draft?.kind === "divider" && dividerLockedByLidLabels();
  $$(".placed-item-done").forEach(button => { button.disabled = busy; });
  $$(".placed-item-remove").forEach(button => { button.disabled = busy || lockedDivider; });
  const hasPhotoNest = state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour);
  $$(".support-choice").forEach(button => {
    const info = partInfo(button.dataset.kind);
    const isModifier = info?.capabilities?.includes("box_modifier");
    const count = partInstanceCount(button.dataset.kind);
    const alreadyAdded = count > 0;
    const active = button.classList.contains("active");
    button.disabled = busy || (hasPhotoNest && !isModifier);
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
    if (isModifier) {
      button.title = alreadyAdded
        ? `${info.title} already added. Select it to edit.`
        : `${info.title} — ${info.description}`;
    }
  });
  $$(".placed-item-select").forEach(button => { button.disabled = busy; });
  $("#support-count").textContent = `${placedPartCount()} added`;
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
  const editingFeatureIndex = state.draft
    ? (Number.isInteger(draftCommitIndex()) ? draftCommitIndex() : state.draftSourceIndex)
    : null;
  const modifierDetail = kind => {
    const box = state.design.box || {};
    if (kind === "lid_stacking") return box.lid?.enabled ? "Lid" : "Stackable Bin";
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
      title: isRim ? "Text (Rim Level)" : partInfo(one.kind)?.title || one.kind,
      detail: isRim ? one.options?.text || "Rim label" : `${fmt(width)} × ${fmt(depth)} mm`,
      editing: index === editingFeatureIndex,
      selected: index === state.selected,
      invalid: invalid.has(index),
    };
  });
  for (const kind of BOX_MODIFIER_KINDS) {
    if (!modifierIsActive(kind)) continue;
    rows.push({
      type: "modifier", kind,
      title: partInfo(kind)?.title || kind,
      detail: modifierDetail(kind),
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
    const rowActions = actions && row.editing
      ? `<div class="placed-item-actions">
        <button type="button" class="placed-item-done button primary">Done</button>
        <button type="button" class="placed-item-remove button danger" title="Delete ${title}" aria-label="Delete ${title}">Delete</button>
      </div>` : "";
    return `<div class="placed-item ${row.selected ? "selected" : ""} ${statusClass}" data-support-kind="${escapeHtml(row.kind)}">
      <button type="button" class="placed-item-select" ${identity}>
        <span class="placed-item-icon">${iconFor(row.kind)}</span>
        <span class="placed-item-copy"><strong>${title}</strong><span class="placed-item-detail">${escapeHtml(row.detail)}</span></span>
      </button>
      ${rowActions}
    </div>`;
  }).join("");
}

function wirePlacedRows(container) {
  if (!container) return;
  $$(".placed-item[data-support-kind]", container).forEach(row => {
    row.style.setProperty("--support-color", kindColor(row.dataset.supportKind));
  });
  $$(".placed-item-select[data-index]", container).forEach(button => button.addEventListener("click", async () => {
    await selectedFeature(Number(button.dataset.index));
  }));
  $$(".placed-item-select[data-kind]", container).forEach(button =>
    button.addEventListener("click", () => openModifier(button.dataset.kind, true)));
  $$(".placed-item-done", container).forEach(button =>
    button.addEventListener("click", saveCurrentPart));
  $$(".placed-item-remove", container).forEach(button =>
    button.addEventListener("click", deleteCurrentPart));
}

function renderPlaced() {
  if (!state.design) return;
  const rows = placedRowData();
  const previewRows = rows.filter(row => !row.editing);
  const preview = $("#placed-supports");
  if (preview) {
    preview.innerHTML = placedRowsMarkup(previewRows) || (rows.length
      ? '<div class="placed-empty">No other parts or options.</div>'
      : '<div class="placed-empty">No parts or options yet. Pick one above.</div>');
    wirePlacedRows(preview);
  }
  const added = $("#added-parts-list");
  if (added) {
    added.innerHTML = placedRowsMarkup(rows, { actions: true }) || '<div class="placed-empty">Nothing added yet.</div>';
    wirePlacedRows(added);
  }
  const total = placedPartCount();
  $("#support-count").textContent = `${total} added`;
  const summaryEl = $("#design-summary");
  if (summaryEl) {
    summaryEl.textContent = total
      ? `${total} added · ${state.design.layout.mode}`
      : `Nothing added · ${state.design.layout.mode}`;
  }

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

// `persistResume: false` (Fix 032 Correction 4, C4.2) renders a normal,
// fully valid preview WITHOUT queuing it as the Space's resume checkpoint.
// Used only for the one narrow starter preview that replaces a stored
// resume design that just failed canonical validation - that starter is
// otherwise indistinguishable from any other valid preview and would
// silently overwrite the bad checkpoint the original contract says must be
// left alone for possible recovery. Every ordinary call (the ordinary
// default) persists exactly as before.
async function refreshPreview({ persistResume = true } = {}) {
  const request = ++state.previewRequest;
  beginPreviewWait(request);
  state.canGenerate = false;
  updateGenerateAvailability();
  if (typeof SP !== "undefined" && SP.renderSpaceInfo) {
    SP.renderSpaceInfo();
  }
  $("#preview-state").textContent = "Building preview…";
  $("#preview-state").classList.remove("status-ok", "status-error");
  setError();
  try {
    const payload = { design: state.design };
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
    endPreviewWait(request);
    const grownX = result.design?.box?.x !== state.design?.box?.x;
    const grownY = result.design?.box?.y !== state.design?.box?.y;
    const grownZ = result.design?.box?.z !== state.design?.box?.z;
    state.preview = result;
    state.design = result.design;
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
    $("#preview-state").textContent = previewHasErrors ? "Design needs attention" : "Preview current";
    $("#preview-state").classList.toggle("status-error", Boolean(previewHasErrors));
    $("#preview-state").classList.toggle("status-ok", !previewHasErrors);
    formatDimField("x");
    formatDimField("y");
    formatHeightField();
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
    if (result.message) actions.push({
      message: result.message,
      activate: () => {
        const input = $('[data-draft="option:text"]', $("#draft-fields"));
        if (input) {
          input.scrollIntoView({ behavior: "smooth", block: "center" });
          input.focus();
          flashField(input);
        }
      },
    });
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
    if (messages.length) setError("", actions);
    // An auto text part places itself server-side, so adopt the zones the
    // preview resolved - otherwise the next edit would send the stale ones.
    adoptResolvedFeatures(result.design?.layout?.features);
    state.textMeta = result.text_meta || [];
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
  } catch (error) {
    if (request !== state.previewRequest) return;
    endPreviewWait(request);
    $("#preview-state").textContent = "Preview could not build";
    $("#preview-state").classList.remove("status-ok");
    $("#preview-state").classList.add("status-error");
    setError(error.message);
    state.canGenerate = false;
    updateGenerateAvailability();
    // A hard preview failure with supports present is usually a footprint that
    // outgrew the bin - offer the expand button and let the endpoint judge.
    state.fitError = true;
    updateAutoExpandButton();
  }
}

// An auto-placed text part is positioned by the engine, not by the editor, so
// the zone it lands on only comes back with the preview. Take those zones -
// and nothing else - so a drag or a field edit in flight is never overwritten.
function adoptResolvedFeatures(resolved) {
  const features = state.design?.layout?.features;
  if (!Array.isArray(resolved) || !Array.isArray(features)) return;
  if (resolved.length !== features.length) return;
  features.forEach((one, index) => {
    if (one.kind !== "text" || !one.options?.auto) return;
    const from = resolved[index];
    if (!from || from.kind !== "text") return;
    one.zone = from.zone.slice();
    if (from.options && from.options.quarter_turns !== undefined) {
      one.options.quarter_turns = from.options.quarter_turns;
    }
  });
}

// Kept as the single hook the preview/draft paths call whenever the fit state
// moves; the top-of-section button it once toggled is gone - the per-part
// "Grow the bin" button below replaces it.
function updateAutoExpandButton() {
  updateFitActions();
}

// Bore and Slot Rack keep their Base snug around their selected quantities and
// grow the bin when needed, so they do not need manual Fit or Fill shortcuts.
// A Post Rack may still need a deliberately sized footprint, while Pocket and
// Steps have no contents from which to derive one.
const FIT_PART_KINDS = { post: "pegs" };
const FILL_PART_KINDS = new Set(["pocket", "steps"]);

function renderFitActions(one) {
  const kind = one.kind;
  const rows = [];
  if (FIT_PART_KINDS[kind]) {
    rows.push(`<button type="button" class="button" data-action="fit-part" hidden>Fit to ${FIT_PART_KINDS[kind]}</button>`);
  }
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
    const zone = result.feature.zone;
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
  if (!["drawer", "portable", "box"].includes(state.activeSpace.kind)) return undefined;
  const maximum = number(state.activeSpace.z, NaN);
  return Number.isFinite(maximum) ? maximum : undefined;
}

async function sizeBinHeightToBore({ button = null, silent = false, guard = null } = {}) {
  if (state.draft?.kind !== "bore") return "skipped";
  const draftIndex = draftCommitIndex();
  if (!Number.isInteger(draftIndex)) {
    if (!silent) toast("Select the Bore again before sizing the bin height.", true, 5000);
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
    if (result.changed) recordHistory(previousDesign);
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
      $("#draft-status").textContent = error.message;
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
    if (changed) recordHistory(previousDesign);
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

function kindColor(kind) {
  if (COLORS[kind]) return COLORS[kind];
  if (kind === "draft_invalid") return COLORS.invalid;
  if (kind.endsWith("_divider_slope")) return COLORS.divider_slope;
  if (kind.startsWith("draft_")) return DRAFT_HIGHLIGHT;
  const base = kind.replace(/^insert_/, "").replace(/^feature_/, "");
  if (kind.endsWith("invalid")) return COLORS.invalid;
  if (kind.startsWith("insert_") && COLORS[base]) {
    return blend(COLORS[base], INSERT_TINT, INSERT_TINT_MIX);
  }
  return COLORS[base] || "#7896a0";
}

function blend(start, end, amount) {
  const channels = value => [1, 3, 5].map(at => parseInt(value.slice(at, at + 2), 16));
  const from = channels(start), to = channels(end);
  return "#" + from.map((value, index) =>
    Math.round(value + (to[index] - value) * amount).toString(16).padStart(2, "0")
  ).join("");
}

function shade(hex, amount) {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map(at => parseInt(value.slice(at, at + 2), 16));
  return `rgb(${channels.map(channel => Math.max(0, Math.min(255, Math.round(channel * amount)))).join(",")})`;
}

// One directional key light plus a weak fill and a hemispheric term, all in
// world space so form stays readable as the model rotates. Returns a multiplier
// applied to each face's own colour (baseColor x lighting), clamped so no
// surface goes black or washes out to a flat sheet.
const KEY_LIGHT = (() => {
  const v = [-0.5, -0.35, 0.78];
  const len = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / len, v[1] / len, v[2] / len];
})();
const FILL_LIGHT = (() => {
  const v = [0.45, 0.55, 0.2];
  const len = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / len, v[1] / len, v[2] / len];
})();

function faceLighting(normal) {
  let [nx, ny, nz] = normal;
  const len = Math.hypot(nx, ny, nz) || 1;
  nx /= len; ny /= len; nz /= len;
  const key = Math.max(0, nx * KEY_LIGHT[0] + ny * KEY_LIGHT[1] + nz * KEY_LIGHT[2]);
  const fill = Math.max(0, nx * FILL_LIGHT[0] + ny * FILL_LIGHT[1] + nz * FILL_LIGHT[2]);
  // nz is the up-component: top faces gain, downward/back faces lose.
  const light = 0.46 + 0.46 * key + 0.13 * fill + 0.12 * nz;
  return Math.max(0.42, Math.min(1.2, light));
}

// Lighting is a smooth function of a face normal, and every face of one flat
// surface shares it, so the shaded colour repeats over and over. Quantise the
// multiplier and memoise the result: per-face regex, parseInt and string
// building become a map lookup, which on a mesh preview is the difference
// between a fluid spin and a slideshow. 128 steps over the 0.42-1.2 range is
// under one part in 255 - below what a screen can show.
const SHADE_STEPS = 128;
const shadeCache = new Map();

function shadedColor(kind, normal) {
  const step = Math.round(faceLighting(normal) * SHADE_STEPS);
  const key = `${kind}|${step}`;
  let hit = shadeCache.get(key);
  if (hit === undefined) {
    hit = shade(kindColor(kind), step / SHADE_STEPS);
    shadeCache.set(key, hit);
  }
  return hit;
}

// Opaque neutral ground so the object has something to sit against, plus a soft
// contact shadow projected from the model's base rectangle - cheap grounding,
// no ray tracing.
let backdropCache = null;

function paintBackdrop(context, width, height) {
  if (!backdropCache || backdropCache.context !== context || backdropCache.height !== height) {
    const bg = context.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, "#eef1f2");
    bg.addColorStop(1, "#dfe4e5");
    backdropCache = { context, height, bg };
  }
  context.fillStyle = backdropCache.bg;
  context.fillRect(0, 0, width, height);
}

// `outerXY`, when given, overrides the shadow's footprint with the true
// case exterior - see draw3DDimensions for why box.x/box.y alone are wrong
// for B4B. Callers suppress the shadow outright (pass no box) for a view
// that isn't actually sitting on the ground, such as B4B's isolated Lid.
function drawContactShadow(context, box, camera, project, outerXY) {
  if (!box) return;
  const hx = (outerXY ? number(outerXY[0]) : number(box.x)) / 2;
  const hy = (outerXY ? number(outerXY[1]) : number(box.y)) / 2;
  if (!(hx > 0) || !(hy > 0)) return;
  const base = [[-hx, -hy, 0], [hx, -hy, 0], [hx, hy, 0], [-hx, hy, 0]]
    .map(point => project(iso(point, camera)));
  let cx = 0, cy = 0, minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of base) {
    cx += x; cy += y;
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  cx /= 4; cy /= 4;
  const rx = Math.max(8, (maxX - minX) / 2) * 1.08;
  const ry = Math.max(5, (maxY - minY) / 2) * 1.12;
  context.save();
  context.translate(cx, cy);
  context.scale(1, ry / rx);
  const grad = context.createRadialGradient(0, 0, 0, 0, 0, rx);
  grad.addColorStop(0, "rgba(18,30,36,.26)");
  grad.addColorStop(0.55, "rgba(18,30,36,.14)");
  grad.addColorStop(1, "rgba(18,30,36,0)");
  context.fillStyle = grad;
  context.beginPath();
  context.arc(0, 0, rx, 0, Math.PI * 2);
  context.fill();
  context.restore();
}

function cameraVector(camera) {
  const yaw = camera.yaw * Math.PI / 180;
  const elevation = camera.elevation * Math.PI / 180;
  return [-Math.sin(yaw) * Math.cos(elevation), -Math.cos(yaw) * Math.cos(elevation), Math.sin(elevation)];
}

function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

function iso(point, camera) {
  const yaw = camera.yaw * Math.PI / 180;
  const elevation = camera.elevation * Math.PI / 180;
  const [x, y, z] = point;
  const side = x * Math.cos(yaw) - y * Math.sin(yaw);
  const forward = x * Math.sin(yaw) + y * Math.cos(yaw);
  return [side, -forward * Math.sin(elevation) - z * Math.cos(elevation)];
}

function canvasSize(canvas) {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const ratio = Math.min(2, window.devicePixelRatio || 1);
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

// A B4B preview is one triangle per mesh face - well over a hundred thousand of
// them on a big case. At that size the painter loop is the whole cost of a
// spin, so it is written flat: no per-face object spread, no closures, no
// throwaway arrays, no string colour maths, and back faces are dropped before
// anything is projected. The picture it paints is the same one as before.
// An ordinary bin's own geometry vs. everything a user has placed inside it -
// shared with the WebGL path's group classification so Bin/Interior/Xray
// mean the same thing whichever renderer is drawing them.
const isBinFace = kind =>
  kind === "outside" || kind === "inside" || kind === "rim" || kind === "floor" ||
  kind === "top_label_ledge" || kind === "label" || kind === "label_hole" ||
  kind === "lid" || kind === "lid_label" || kind === "base_trim";

// Which cardinal side of the bin the camera is looking from, by yaw alone
// (elevation only affects pitch, not which wall is nearest). Shared by the
// legacy Xray cull and the WebGL cutaway-buffer builder so both remove
// exactly the same wall.
function cameraFacingSide(camera = state.camera) {
  const yaw = number(camera?.yaw, 45) * Math.PI / 180;
  const camX = -Math.sin(yaw);
  const camY = -Math.cos(yaw);
  if (Math.abs(camX) >= Math.abs(camY)) return camX > 0 ? "x+" : "x-";
  return camY > 0 ? "y+" : "y-";
}

// A face counts as "on" the facing side either by its normal pointing
// strongly that way (catches near-planar wall faces directly) or, failing
// that, by its centroid sitting out past the 0.45-of-halfwidth band (catches
// bevelled/gusseted faces whose normal alone wouldn't clear the threshold).
// Both checks and both thresholds are load-bearing - see the legacy 2D
// painter this was extracted from.
function faceOnBinSide(face, side) {
  const [nx, ny] = face.normal;
  if (side === "x+" && nx > 0.3) return true;
  if (side === "x-" && nx < -0.3) return true;
  if (side === "y+" && ny > 0.3) return true;
  if (side === "y-" && ny < -0.3) return true;
  if (!face.points?.length) return false;
  let sumX = 0, sumY = 0;
  for (const point of face.points) {
    sumX += point[0];
    sumY += point[1];
  }
  const avgX = sumX / face.points.length;
  const avgY = sumY / face.points.length;
  const box = state.design?.box;
  const hx = box ? number(box.x) / 2 : 1;
  const hy = box ? number(box.y) / 2 : 1;
  switch (side) {
    case "x+": return avgX > hx * 0.45;
    case "x-": return avgX < -hx * 0.45;
    case "y+": return avgY > hy * 0.45;
    case "y-": return avgY < -hy * 0.45;
    default: return false;
  }
}

function isFacingBinWall(face, camera = state.camera) {
  return isBinFace(face.kind) && faceOnBinSide(face, cameraFacingSide(camera));
}

// Legacy full 2D-canvas painter. Used only as a fallback when WebGL is
// unavailable (see renderPreview3D) - the primary path is the depth-buffered
// WebGL renderer in preview3d-webgl.js, which this file no longer needs to
// keep pixel-identical to, though it still shares isBinFace/iso/project and
// the shading/colour helpers below.
function drawGeometryLegacy2D(canvas, geometry, camera) {
  const { context, width, height } = canvasSize(canvas);
  paintBackdrop(context, width, height);
  state.previewSupportPolygons = [];
  if (!geometry?.length) {
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText("No geometry", width / 2, height / 2);
    return;
  }
  // Leaned-bore centre lines are annotation, not solid faces - pull them out so
  // the painter below doesn't cull them, and draw them on top at the end.
  const boreAxes = geometry.filter(face => face.kind?.endsWith("bore_axis"));
  if (boreAxes.length) geometry = geometry.filter(face => !face.kind?.endsWith("bore_axis"));
  const vector = cameraVector(camera);
  const yawRad = camera.yaw * Math.PI / 180;
  const elevationRad = camera.elevation * Math.PI / 180;
  const cosYaw = Math.cos(yawRad), sinYaw = Math.sin(yawRad);
  const cosEl = Math.cos(elevationRad), sinEl = Math.sin(elevationRad);
  const vx = vector[0], vy = vector[1], vz = vector[2];

  // Cull first, project second: a back face costs one dot product instead of
  // an iso() call per corner.
  const faces = [];
  for (let index = 0; index < geometry.length; index += 1) {
    const face = geometry[index];
    const kind = face.kind;
    const normal = face.normal;
    const facing = normal[0] * vx + normal[1] * vy + normal[2] * vz;
    if (facing <= 0 && kind !== "label_hole") continue;
    const isBin = isBinFace(kind);
    if (isBin && !state.binVisible) continue;
    if (!isBin && !state.interiorVisible) continue;
    if (state.xrayOn && isFacingBinWall(face, camera)) continue;
    const points = face.points;
    const corners = points.length;
    const projected = new Float64Array(corners * 2);
    let depth = 0;
    for (let at = 0; at < corners; at += 1) {
      const point = points[at];
      const px = point[0], py = point[1], pz = point[2];
      const forward = px * sinYaw + py * cosYaw;
      projected[at * 2] = px * cosYaw - py * sinYaw;
      projected[at * 2 + 1] = -forward * sinEl - pz * cosEl;
      depth += px * vx + py * vy + pz * vz;
    }
    faces.push({
      kind, normal, points, projected, corners,
      depth: depth / corners, layer: number(face.layer),
    });
  }
  if (!faces.length) return;
  // Lettering sits flush on one big surface (the floor, or the top-label
  // ledge). The painter sort compares face centroids, so a glyph near the edge
  // of that surface can sort behind it at some viewing angles and vanish - the
  // "missing first letter" effect. Pin every letter face to its substrate's
  // depth so the layer tie-break (floor/ledge < label < label_hole) always
  // paints them on top, without letting them punch through nearer walls. Text
  // interior parts are inlaid into the same surface and need the same pin.
  const isLettering = face =>
    face.kind === "label" || face.kind === "label_hole" ||
    /^(feature|insert|draft)_text$/.test(face.kind);
  const substrate = faces.filter(face => face.kind === "floor" || face.kind === "top_label_ledge");
  if (substrate.length) {
    const substrateDepth = Math.max(...substrate.map(face => face.depth));
    for (const face of faces) {
      if (!isLettering(face)) continue;
      face.depth = substrateDepth;
      // Sharing the substrate's depth leaves only the layer to break the tie,
      // and a text part arrives on layer 0 like every other holder - under the
      // floor's own layer 1, which would paint straight over it. Lift it onto
      // the layer the floor label has always used.
      if (face.layer < 2) face.layer = 2;
    }
  }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const face of faces) {
    const flat = face.projected;
    for (let at = 0; at < flat.length; at += 2) {
      const x = flat[at], y = flat[at + 1];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  const spanX = Math.max(1e-8, maxX - minX), spanY = Math.max(1e-8, maxY - minY);
  const scale = Math.min((width * 0.75) / spanX, (height * 0.75) / spanY) * camera.zoom;
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const project = point => [width / 2 + (point[0] - midX) * scale, height / 2 + (point[1] - midY) * scale];
  const originX = width / 2 - midX * scale;
  const originY = height / 2 - midY * scale;
  faces.sort((a, b) => a.depth - b.depth || a.layer - b.layer);
  drawContactShadow(context, b4bShadowBox(), camera, project, b4bAssembledEnvelope());
  context.lineJoin = "round";
  let penFill = "", penStroke = "", penWidth = -1;
  for (let index = 0; index < faces.length; index += 1) {
    const face = faces[index];
    const flat = face.projected;
    const corners = face.corners;
    if (corners < 3) continue;
    let x = originX + flat[0] * scale, y = originY + flat[1] * scale;
    let lowX = x, highX = x, lowY = y, highY = y;
    context.beginPath();
    context.moveTo(x, y);
    for (let at = 1; at < corners; at += 1) {
      x = originX + flat[at * 2] * scale;
      y = originY + flat[at * 2 + 1] * scale;
      if (x < lowX) lowX = x; else if (x > highX) highX = x;
      if (y < lowY) lowY = y; else if (y > highY) highY = y;
      context.lineTo(x, y);
    }
    context.closePath();
    const kind = face.kind;
    const isDraft = kind.startsWith("draft_");
    if (isDraft || kind.startsWith("feature_") || kind.startsWith("insert_")) {
      const polygon = new Array(corners);
      for (let at = 0; at < corners; at += 1) {
        polygon[at] = [originX + flat[at * 2] * scale, originY + flat[at * 2 + 1] * scale];
      }
      state.previewSupportPolygons.push(polygon);
    }
    const fill = shadedColor(kind, face.normal);
    if (fill !== penFill) { context.fillStyle = fill; penFill = fill; }
    context.fill();
    // Match the seam stroke to the fill first so internal triangulation stops
    // reading as a wireframe, then lay only a whisper of darker contrast where
    // surfaces actually meet.
    if (fill !== penStroke) { context.strokeStyle = fill; penStroke = fill; }
    if (penWidth !== 0.8) { context.lineWidth = 0.8; penWidth = 0.8; }
    context.stroke();
    // A face smaller than the seam stroke is already entirely covered by it, so
    // the contrast pass would land on pixels it has just painted. Skipping it
    // there costs nothing visible and is most of a mesh preview.
    if (highX - lowX < 0.6 && highY - lowY < 0.6) continue;
    const ink = isDraft ? "rgba(196,131,20,.45)" : "rgba(18,32,38,.08)";
    const inkWidth = isDraft ? 0.6 : 0.35;
    if (ink !== penStroke) { context.strokeStyle = ink; penStroke = ink; }
    if (penWidth !== inkWidth) { context.lineWidth = inkWidth; penWidth = inkWidth; }
    context.stroke();
  }
  drawUsableFloor(context, geometry, camera, project);
  drawBoreAxes(context, boreAxes, camera, project);
  draw3DDimensions(context, state.design?.box, camera, project, b4bAssembledEnvelope());
}

// A line up the centre of every hole in a leaned bore, arrow-tipped, so it's
// clear which way the holes point and how far they lean. Drawn last, over the
// solid, since it's an annotation rather than part of the model.
function drawBoreAxes(context, boreAxes, camera, project) {
  if (!boreAxes?.length) return;
  for (const line of boreAxes) {
    const points = (line.points || []).map(point => project(iso(point, camera)));
    if (points.length < 2) continue;
    const isDraft = line.kind.startsWith("draft_");
    const ink = isDraft ? "rgba(196,131,20,.95)" : "rgba(20,108,112,.95)";
    context.save();
    context.lineJoin = "round";
    context.lineCap = "round";
    const trace = () => {
      context.beginPath();
      context.moveTo(points[0][0], points[0][1]);
      for (let i = 1; i < points.length; i += 1) context.lineTo(points[i][0], points[i][1]);
    };
    trace();
    context.strokeStyle = "rgba(255,255,255,.85)";
    context.lineWidth = 3.6;
    context.stroke();
    context.strokeStyle = ink;
    context.lineWidth = 1.6;
    context.stroke();
    // Arrowhead on the stub end, aimed along the last segment.
    const tip = points[points.length - 1];
    const prev = points[points.length - 2];
    const heading = Math.atan2(tip[1] - prev[1], tip[0] - prev[0]);
    const size = 7;
    context.beginPath();
    context.moveTo(tip[0], tip[1]);
    context.lineTo(tip[0] - size * Math.cos(heading - 0.42), tip[1] - size * Math.sin(heading - 0.42));
    context.lineTo(tip[0] - size * Math.cos(heading + 0.42), tip[1] - size * Math.sin(heading + 0.42));
    context.closePath();
    context.fillStyle = ink;
    context.strokeStyle = "rgba(255,255,255,.85)";
    context.lineWidth = 1.1;
    context.fill();
    context.stroke();
    context.restore();
  }
}

// Lay the straight-sided placement rectangle - the real usable floor, the same
// one the 2D layout draws dashed and the engine's BoxSpec.usable_inside
// returns - flat on the bin floor. The wavy cavity floor painted behind it is
// larger, so a tool as long as the bin can still be rejected for want of room;
// this makes that gap visible. The margin between the two is tinted.
function drawUsableFloor(context, geometry, camera, project) {
  if (!state.binVisible) return;
  const box = state.design?.box;
  const floors = (geometry || []).filter(face => face.kind === "floor");
  if (!box || !floors.length) return;
  const floorZ = Math.max(
    ...floors.flatMap(face => face.points.map(point => point[2])),
  );
  const flat = point => project(iso([point[0], point[1], floorZ], camera));
  const [insideX, insideY] = binInsideExtent(box);
  const halfX = insideX / 2, halfY = insideY / 2;
  const rect = [[-halfX, -halfY], [halfX, -halfY], [halfX, halfY], [-halfX, halfY]]
    .map(flat);
  const trace = (points, close = true) => {
    context.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach(point => context.lineTo(point[0], point[1]));
    if (close) context.closePath();
  };
  const cavity = state.preview?.cavity_outline;
  if (cavity && cavity.length > 2) {
    context.save();
    context.beginPath();
    trace(cavity.map(flat));
    trace(rect);
    context.fillStyle = "rgba(196,131,20,.16)";
    context.fill("evenodd");
    context.restore();
  }
  context.save();
  context.beginPath();
  trace(rect);
  context.setLineDash([5, 4]);
  context.lineWidth = 1.3;
  context.strokeStyle = "rgba(38,65,75,.6)";
  context.stroke();
  context.setLineDash([]);
  context.restore();
}

function checkBinSizeChange() {
  const box = state.design?.box;
  if (!box) return;
  const current = { x: number(box.x), y: number(box.y), z: number(box.z) };
  if (state.lastBoxSize && (
    state.lastBoxSize.x !== current.x ||
    state.lastBoxSize.y !== current.y ||
    state.lastBoxSize.z !== current.z
  )) {
    state.camera.zoom = 1;
  }
  state.lastBoxSize = current;
}

// `outerXYZ`, when given, overrides the guides' extent and labels with the
// true assembled envelope - B4B's box.x/y/z are the child field, not the
// printed case (and for height, not even the full assembly: closed-lid
// height alone ignores hinge knuckles, and stacking pegs stand proud of
// that again), so the dimension overlay would otherwise mislabel the case
// and fail to reach its drawn edges on every axis. See fix3d.md.
function draw3DDimensions(context, box, camera, project, outerXYZ) {
  state.previewDimensionHandles = [];
  if (!box) return;
  const interactive = !baseTrimEnabled();
  const outerX = outerXYZ ? number(outerXYZ[0]) : number(box.x);
  const outerY = outerXYZ ? number(outerXYZ[1]) : number(box.y);
  const outerZ = outerXYZ ? number(outerXYZ[2]) : number(box.z);
  const hx = outerX / 2;
  const hy = outerY / 2;
  const hz = outerZ;
  if (hx <= 0 || hy <= 0 || hz <= 0) return;
  // B4B's guides show the assembled envelope (outerX/Y/Z) but box.x/y/z is
  // still the field a drag actually edits - each handle carries both: the
  // envelope number to draw/scale the guide with, and the real field to
  // start the drag from (see dimensionDisplayOverride/fix3d.md).
  const editBox = { x: number(box.x), y: number(box.y), z: number(box.z) };

  const yawRad = camera.yaw * Math.PI / 180;
  const camX = -Math.sin(yawRad);
  const camY = -Math.cos(yawRad);

  const frontY = camY < 0 ? -hy : hy;
  const frontX = camX < 0 ? -hx : hx;
  const normWidth = [0, frontY > 0 ? 1 : -1, 0];
  const normDepth = [frontX > 0 ? 1 : -1, 0, 0];

  const standoff = 24;
  const gap = 3;
  const over = 4;

  const computeDimGuide = (p3dA, p3dB, norm3d) => {
    const sA = project(iso(p3dA, camera));
    const sB = project(iso(p3dB, camera));
    const sNorm = project(iso([p3dA[0] + norm3d[0], p3dA[1] + norm3d[1], p3dA[2] + norm3d[2]], camera));
    let nx = sNorm[0] - sA[0], ny = sNorm[1] - sA[1];
    const nLen = Math.hypot(nx, ny);
    if (nLen > 1e-4) {
      nx /= nLen;
      ny /= nLen;
    } else {
      nx = 0;
      ny = 1;
    }
    const offA = [sA[0] + nx * standoff, sA[1] + ny * standoff];
    const offB = [sB[0] + nx * standoff, sB[1] + ny * standoff];
    return { sA, sB, offA, offB, normal: [nx, ny] };
  };

  // 1. Width (along X on front ground)
  const widthDim = computeDimGuide([-hx, frontY, 0], [hx, frontY, 0], normWidth);
  renderDimensionGuide(
    context,
    widthDim.offA,
    widthDim.offB,
    widthDim.sA,
    widthDim.sB,
    widthDim.normal,
    `Width ${fmt(outerX)} mm`,
    gap,
    over,
    interactive ? { view: "3d", axis: "x", value: editBox.x, displayValue: outerX } : null
  );

  // 2. Depth (along Y on front ground)
  const depthDim = computeDimGuide([frontX, -hy, 0], [frontX, hy, 0], normDepth);
  renderDimensionGuide(
    context,
    depthDim.offA,
    depthDim.offB,
    depthDim.sA,
    depthDim.sB,
    depthDim.normal,
    `Depth ${fmt(outerY)} mm`,
    gap,
    over,
    interactive ? { view: "3d", axis: "y", value: editBox.y, displayValue: outerY } : null
  );

  // 3. Height (vertical Z edge on the leftmost corner of the bin)
  const corners = [
    [-hx, -hy],
    [hx, -hy],
    [hx, hy],
    [-hx, hy],
  ];
  let leftmostCorner = corners[0];
  let minScreenX = Infinity;
  for (const [cx, cy] of corners) {
    const pt = project(iso([cx, cy, 0], camera));
    if (pt[0] < minScreenX) {
      minScreenX = pt[0];
      leftmostCorner = [cx, cy];
    }
  }

  const sBot = project(iso([leftmostCorner[0], leftmostCorner[1], 0], camera));
  const sTop = project(iso([leftmostCorner[0], leftmostCorner[1], hz], camera));
  const heightNormal = [-1, 0];
  const offBot = [sBot[0] - standoff, sBot[1]];
  const offTop = [sTop[0] - standoff, sTop[1]];

  renderDimensionGuide(
    context,
    offBot,
    offTop,
    sBot,
    sTop,
    heightNormal,
    `Height ${fmt(outerZ)} mm`,
    gap,
    over,
    interactive ? { view: "3d", axis: "z", value: editBox.z, displayValue: outerZ } : null
  );
}

// `handle`, when given, registers a canvas-space hit region around the drawn
// label into state.previewDimensionHandles/layoutDimensionHandles so a
// pointerdown on the label can start a resize drag instead of orbiting the
// camera or moving a feature - see hitDimensionHandle().
function renderDimensionGuide(context, pStart, pEnd, witA, witB, normal, label, gap, over, handle = null) {
  const dx = pEnd[0] - pStart[0];
  const dy = pEnd[1] - pStart[1];
  const span = Math.hypot(dx, dy);
  if (span < 14) return;

  context.save();

  // Extension / witness lines from bin corner to dimension line
  context.strokeStyle = "rgba(20, 108, 112, 0.45)";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(witA[0] + normal[0] * gap, witA[1] + normal[1] * gap);
  context.lineTo(pStart[0] + normal[0] * over, pStart[1] + normal[1] * over);
  context.moveTo(witB[0] + normal[0] * gap, witB[1] + normal[1] * gap);
  context.lineTo(pEnd[0] + normal[0] * over, pEnd[1] + normal[1] * over);
  context.stroke();

  // Dimension line
  context.strokeStyle = "#146c70";
  context.lineWidth = 1.25;
  context.beginPath();
  context.moveTo(pStart[0], pStart[1]);
  context.lineTo(pEnd[0], pEnd[1]);
  context.stroke();

  // Inward arrowheads at each end
  const lineAngle = Math.atan2(dy, dx);
  for (const [pt, dir] of [[pStart, 1], [pEnd, -1]]) {
    context.beginPath();
    context.moveTo(pt[0], pt[1]);
    context.lineTo(
      pt[0] + Math.cos(lineAngle + 0.45) * 6 * dir,
      pt[1] + Math.sin(lineAngle + 0.45) * 6 * dir
    );
    context.moveTo(pt[0], pt[1]);
    context.lineTo(
      pt[0] + Math.cos(lineAngle - 0.45) * 6 * dir,
      pt[1] + Math.sin(lineAngle - 0.45) * 6 * dir
    );
    context.stroke();
  }

  // Label badge at midpoint
  const mid = [(pStart[0] + pEnd[0]) / 2, (pStart[1] + pEnd[1]) / 2];

  // Text orientation: spins with line, but NEVER upside-down!
  let textAngle = lineAngle;
  if (textAngle > Math.PI / 2) {
    textAngle -= Math.PI;
  } else if (textAngle < -Math.PI / 2) {
    textAngle += Math.PI;
  }
  if (Math.abs(textAngle - Math.PI / 2) < 1e-4) {
    textAngle = -Math.PI / 2;
  }

  context.translate(mid[0], mid[1]);
  context.rotate(textAngle);
  context.font = "600 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
  context.textAlign = "center";
  context.textBaseline = "middle";

  const tw = context.measureText(label).width;
  const padX = 8;
  const bw = tw + padX * 2;
  const bh = 18;
  const r = 5;

  const active = handle && (
    (state.dimensionHover?.view === handle.view && state.dimensionHover?.axis === handle.axis) ||
    (state.dimensionDrag?.view === handle.view && state.dimensionDrag?.axis === handle.axis)
  );

  // Subtle drop shadow for badge
  context.shadowColor = "rgba(18, 38, 46, 0.25)";
  context.shadowBlur = 6;
  context.shadowOffsetY = 2;

  // Dark HUD pill badge - a touch darker/bolder while draggable and under
  // the pointer, so the label reads as grabbable without adding clutter.
  context.fillStyle = active ? "rgba(10, 24, 30, 0.95)" : "rgba(18, 38, 46, 0.90)";
  context.beginPath();
  if (context.roundRect) {
    context.roundRect(-bw / 2, -bh / 2, bw, bh, r);
  } else {
    context.rect(-bw / 2, -bh / 2, bw, bh);
  }
  context.fill();

  context.shadowColor = "transparent";
  context.strokeStyle = active ? "rgba(146, 214, 209, 0.95)" : "rgba(105, 172, 168, 0.70)";
  context.lineWidth = active ? 1.5 : 1;
  context.stroke();

  // Crisp text
  context.fillStyle = "#ffffff";
  context.fillText(label, 0, 0.5);

  context.restore();

  if (handle) {
    // Generous hit region around the label itself (not the whole dimension
    // line) - padded well past the visible pill so it's an easy grab target,
    // and rotated the same as the badge so it stays aligned to the label at
    // any camera yaw.
    const padHit = 9;
    const halfW = bw / 2 + padHit;
    const halfH = Math.max(14, bh / 2 + padHit);
    const cos = Math.cos(textAngle), sin = Math.sin(textAngle);
    const corners = [[-halfW, -halfH], [halfW, -halfH], [halfW, halfH], [-halfW, halfH]]
      .map(([lx, ly]) => [mid[0] + lx * cos - ly * sin, mid[1] + lx * sin + ly * cos]);
    const xs = corners.map(point => point[0]);
    const ys = corners.map(point => point[1]);
    const hitBox = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
    };
    let screenAxisX = dx / span, screenAxisY = dy / span;
    if (Math.abs(dx) >= Math.abs(dy)) {
      if (dx < 0) { screenAxisX = -screenAxisX; screenAxisY = -screenAxisY; }
    } else if (dy > 0) {
      screenAxisX = -screenAxisX; screenAxisY = -screenAxisY;
    }
    const target = handle.view === "3d" ? state.previewDimensionHandles : state.layoutDimensionHandles;
    target.push({
      view: handle.view,
      axis: handle.axis,
      hitBox,
      screenAxis: [screenAxisX, screenAxisY],
      pixelSpan: span,
      value: handle.value,
      displayValue: handle.displayValue ?? handle.value,
      labelCenter: mid,
    });
  }
}

let glRenderer = null;
let glInitAttempted = false;
let glBuffersCache = null; // { source, b4b, generation, buffers, xray }

function ensurePreviewGL() {
  if (glInitAttempted) return glRenderer;
  glInitAttempted = true;
  const canvas = $("#preview-3d-solid");
  if (canvas && window.Preview3DGL) {
    try {
      glRenderer = window.Preview3DGL.init(canvas, {
        // Restoration rebuilds the program and advances `generation` but
        // does not itself trigger a redraw - without this, the view stays
        // blank after a genuine context loss until something else happens
        // to call renderPreview3D() (rotate, zoom, resize, a new preview).
        onContextRestored: () => requestAnimationFrame(renderPreview3D),
      });
    } catch (error) {
      glRenderer = null;
    }
  }
  return glRenderer;
}

// B4B classifies preview faces by which physical part they belong to - an
// explicit `owner` field the backend attaches to every B4B face (see
// fix3d.md) - rather than guessing from `kind`, which B4B's own kinds
// (b4b_body/b4b_lid/...) were never meaningful input for. Anything without
// an owner (should not happen for B4B geometry) defaults to base so it is
// never silently dropped from every view.
function classifyB4BFace(face) {
  return face.owner === "lid" ? "lid" : "base";
}

function classifyOrdinaryFace(face) {
  return isBinFace(face.kind) ? "bin" : "interior";
}

function currentPreviewGroups() {
  return b4bEnabled() ? ["base", "lid"] : ["bin", "interior"];
}

function currentPreviewClassify() {
  return b4bEnabled() ? classifyB4BFace : classifyOrdinaryFace;
}

// Which groups draw (and at what alpha), and which group's bounds the camera
// frames to. Bin/Interior/Xray are independent pure-visibility toggles over
// the SAME complete geometry, so they all frame to the complete model's
// AABB - toggling any of them must never re-fit the camera to whatever
// happens to still be visible. (Xray's camera-facing wall cutaway is a buffer
// swap done separately in renderPreview3DGL(); the passes below already
// describe its fully-opaque bin+interior result.)
function currentPreviewPasses(buffers) {
  if (b4bEnabled()) {
    const view = state.b4bView;
    if (view === "base") {
      return { passes: [{ group: "base", alpha: 1 }], aabb: buffers.groups.base?.aabb, visible: new Set(["base"]) };
    }
    if (view === "lid") {
      return { passes: [{ group: "lid", alpha: 1 }], aabb: buffers.groups.lid?.aabb, visible: new Set(["lid"]) };
    }
    return {
      passes: [{ group: "base", alpha: 1 }, { group: "lid", alpha: 1 }],
      aabb: buffers.allAabb, visible: new Set(["base", "lid"]),
    };
  }
  if (baseTrimEnabled()) {
    return {
      passes: [{ group: "bin", alpha: 1 }],
      aabb: buffers.allAabb,
      visible: new Set(["bin"]),
    };
  }
  const passes = [];
  const visible = new Set();
  if (state.binVisible) { passes.push({ group: "bin", alpha: 1 }); visible.add("bin"); }
  if (state.interiorVisible) { passes.push({ group: "interior", alpha: 1 }); visible.add("interior"); }
  return { passes, aabb: buffers.allAabb, visible };
}

function renderPreview3D() {
  if (!state.preview) return;
  checkBinSizeChange();
  const overlayCanvas = $("#preview-3d");
  const solidCanvas = $("#preview-3d-solid");
  // B4B ships its geometry as compact mesh groups (state.preview.meshes) -
  // "geometry" is always [] for a B4B response, only kept for response-shape
  // compatibility. See organizer_b4b.b4b_preview_meshes.
  const b4b = b4bEnabled();
  const compact = b4b || baseTrimEnabled();
  const geometry = state.preview.geometry || [];
  const meshes = state.preview.meshes || [];
  const renderer = ensurePreviewGL();
  if (!renderer || renderer.lost) {
    if (solidCanvas) solidCanvas.hidden = true;
    // The legacy 2D fallback only ever understood the per-face format, and
    // never shipped for B4B before compact transport existed; give it the
    // one geometry shape it knows rather than teaching it a second one for
    // a path that only runs when WebGL itself is unavailable.
    drawGeometryLegacy2D(overlayCanvas, compact ? meshesToLegacyFaces(meshes) : geometry, state.camera);
    return;
  }
  if (solidCanvas) solidCanvas.hidden = false;
  renderPreview3DGL(renderer, overlayCanvas, compact, geometry, meshes, state.camera);
}

// The legacy painter only ever spoke the per-face format; B4B's compact
// mesh groups need expanding back into that shape for it. Only reached when
// WebGL itself is unavailable, so this never runs on the normal path.
function meshesToLegacyFaces(meshes) {
  const faces = [];
  for (const mesh of meshes) {
    const { positions, normals, kind, layer, owner } = mesh;
    const triangleCount = (positions.length / 9) | 0;
    for (let t = 0; t < triangleCount; t += 1) {
      const at = t * 9;
      faces.push({
        points: [
          [positions[at], positions[at + 1], positions[at + 2]],
          [positions[at + 3], positions[at + 4], positions[at + 5]],
          [positions[at + 6], positions[at + 7], positions[at + 8]],
        ],
        normal: [normals[t * 3], normals[t * 3 + 1], normals[t * 3 + 2]],
        kind, layer, owner,
      });
    }
  }
  return faces;
}

function renderPreview3DGL(renderer, overlayCanvas, b4b, fullGeometry, meshes, camera) {
  const { context, width, height } = canvasSize(overlayCanvas);
  context.clearRect(0, 0, width, height);
  state.previewSupportPolygons = [];
  const hasContent = b4b ? meshes.length > 0 : fullGeometry.length > 0;
  if (!hasContent) {
    window.Preview3DGL.draw(renderer, null, window.Preview3DGL.computeFrame(camera, null, width, height), width, height, []);
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText("No geometry", width / 2, height / 2);
    return;
  }
  // Neither bore axes, the usable-floor rectangle nor placed-part hit-test
  // polygons apply to B4B (it has no bores, no "floor" kind, and no
  // interior-part editing - see _reject_if_b4b), so the overlay gets an
  // empty face list for it rather than a parallel code path.
  const boreAxes = b4b ? [] : fullGeometry.filter(face => face.kind?.endsWith("bore_axis"));
  const solidGeometry = b4b ? [] : (boreAxes.length
    ? fullGeometry.filter(face => !face.kind?.endsWith("bore_axis"))
    : fullGeometry);
  const classify = currentPreviewClassify();
  const source = b4b ? meshes : fullGeometry;
  // Keyed on renderer.generation, not on having observed `lost` at some
  // point: loss and restore can both happen between two redraws (nothing
  // requires a repaint while the context is actually down), so `lost`
  // alone can never be relied on to have been seen. `generation` instead
  // advances exactly once per successful restore and stays put otherwise,
  // so this always notices when the cached buffers belong to a context
  // that no longer exists - regardless of when the redraw that discovers
  // it happens to run.
  if (
    !glBuffersCache || glBuffersCache.source !== source || glBuffersCache.b4b !== b4b
    || glBuffersCache.generation !== renderer.generation
  ) {
    if (glBuffersCache) {
      window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.buffers);
      if (glBuffersCache.xray?.buffers) window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.xray.buffers);
    }
    const groupNames = currentPreviewGroups();
    glBuffersCache = {
      source, b4b, generation: renderer.generation,
      buffers: b4b
        ? window.Preview3DGL.buildBuffersFromMeshes(renderer.gl, meshes, groupNames, kindColor)
        : window.Preview3DGL.buildBuffers(renderer.gl, solidGeometry, groupNames, classify, kindColor),
      xray: null,
    };
  }
  const buffers = glBuffersCache.buffers;
  const chosen = currentPreviewPasses(buffers);
  let drawBuffers = buffers;

  // Xray's cutaway wall is a separate, lazily-built buffer over the SAME
  // complete geometry - never a rebuild of the normal buffer, and never a
  // reason to re-fit the camera (both aabb and frame below still come from
  // the complete, unfiltered `buffers`). Only four side variants exist, so
  // one cached buffer per current facing side is enough to keep spinning
  // smooth without rebuilding on every frame.
  if (!b4b && !baseTrimEnabled() && state.xrayOn) {
    const side = cameraFacingSide(camera);
    if (!glBuffersCache.xray || glBuffersCache.xray.side !== side) {
      if (glBuffersCache.xray?.buffers) window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.xray.buffers);
      const xrayGeometry = solidGeometry.filter(face => !isFacingBinWall(face, camera));
      glBuffersCache.xray = {
        side,
        buffers: window.Preview3DGL.buildBuffers(renderer.gl, xrayGeometry, currentPreviewGroups(), classify, kindColor),
      };
    }
    drawBuffers = glBuffersCache.xray.buffers;
  }

  const aabb = chosen.aabb || buffers.allAabb;
  const frame = window.Preview3DGL.computeFrame(camera, aabb, width, height);
  window.Preview3DGL.draw(renderer, drawBuffers, frame, width, height, chosen.passes);
  drawOverlay2D(context, width, height, solidGeometry, boreAxes, camera, frame, classify, chosen.visible);
}

// Everything that is not solid geometry: the contact shadow, the usable-
// floor rectangle, bore-axis arrows, dimension guides, and the (invisible)
// hit-test polygons clickedPreviewSupport() uses to tell a click on a placed
// part from a click on empty canvas. Drawn on the transparent 2D canvas
// layered over the WebGL solid pass, using the same camera frame so
// everything lines up with it pixel-for-pixel.
function drawOverlay2D(context, width, height, solidGeometry, boreAxes, camera, frame, classify, visibleGroups) {
  const vector = cameraVector(camera);
  const project = point => [
    width / 2 + (point[0] - frame.midX) * frame.scale,
    height / 2 + (point[1] - frame.midY) * frame.scale,
  ];
  for (const face of solidGeometry) {
    const kind = face.kind;
    const isSupport = kind.startsWith("draft_") || kind.startsWith("feature_") || kind.startsWith("insert_");
    if (!isSupport || !visibleGroups.has(classify(face))) continue;
    if (dot(face.normal, vector) <= 0) continue;
    state.previewSupportPolygons.push(face.points.map(point => project(iso(point, camera))));
  }
  const box = dimensionDragBoxOverride(state.design?.box, "3d");
  drawContactShadow(context, b4bShadowBox(), camera, project, b4bAssembledEnvelope());
  drawUsableFloor(context, solidGeometry, camera, project);
  drawBoreAxes(context, boreAxes, camera, project);
  const outerXYZ = dimensionDisplayOverride(b4bAssembledEnvelope());
  draw3DDimensions(context, box, camera, project, outerXYZ);
  drawDimensionGhost3D(context, camera, project, box, outerXYZ);
}

// B4B's assembled_envelope_mm accounts for hinge/latch/handle/stacking
// projection on every axis (see b4b_summary), unlike box.x/y/z which are
// the child field. Used to correct both the dimension guides and the
// contact shadow's footprint so they track the physical case.
function b4bAssembledEnvelope() {
  if (baseTrimEnabled()) {
    const outer = state.preview?.base_trim?.outer_mm;
    return outer ? [outer[0], outer[1], state.design?.box?.z] : null;
  }
  return state.preview?.b4b?.assembled_envelope_mm;
}

// The contact shadow represents something resting on the ground. That's
// true for the whole assembly and for an isolated Base, but not for an
// isolated Lid - it is normally shown up on its hinges, not sitting flat -
// so a full-case shadow under it would be a footprint nothing is casting.
function b4bShadowBox() {
  if (b4bEnabled() && state.b4bView === "lid") return null;
  return state.design?.box;
}

function pointInPolygon([x, y], polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index++) {
    const [xi, yi] = polygon[index];
    const [xj, yj] = polygon[previous];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function clickedPreviewSupport(canvas, event) {
  const bounds = canvas.getBoundingClientRect();
  const point = [event.clientX - bounds.left, event.clientY - bounds.top];
  return state.previewSupportPolygons.some(polygon => pointInPolygon(point, polygon));
}

function wireSupportLayoutDialog() {
  const dialog = $("#support-layout-dialog");
  $("#support-layout-dialog-close").addEventListener("click", () => dialog.close());
  $("#support-layout-dialog-open").addEventListener("click", () => {
    dialog.close();
    $('.view-tab[data-view="2d"]').click();
  });
}

// ---------------------------------------------------------------------------
// Drag-to-resize dimension labels (Width/Depth/Height in 3D, Width/Depth in
// 2D). See fix3d.md - the labels are direct manipulation of the same
// box.x/y/z the sidebar fields edit, not a second sizing system.
// ---------------------------------------------------------------------------

function canvasPointFromEvent(canvas, event) {
  const bounds = canvas.getBoundingClientRect();
  return [event.clientX - bounds.left, event.clientY - bounds.top];
}

function hitDimensionHandle(view, point) {
  const handles = view === "3d" ? state.previewDimensionHandles : state.layoutDimensionHandles;
  for (let index = handles.length - 1; index >= 0; index--) {
    const handle = handles[index];
    const box = handle.hitBox;
    if (point[0] >= box.x && point[0] <= box.x + box.width &&
        point[1] >= box.y && point[1] <= box.y + box.height) {
      return handle;
    }
  }
  return null;
}

// The box a dimension guide should currently draw/label with: the live drag
// candidate for the axis being dragged in this view, otherwise the real
// design. Keeps solid geometry untouched during the drag (see item 8 of
// fix3d.md) while the label and ghost outline update every frame.
function dimensionDragBoxOverride(box, view) {
  const drag = state.dimensionDrag;
  if (!box || !drag || drag.view !== view) return box;
  return { ...box, [drag.axis]: drag.currentValue };
}

// B4B's guide labels/extent come from the server-computed assembled
// envelope (outerXYZ), which does not recompute mid-drag (see item 8 of
// fix3d.md - no geometry regeneration on every pointermove). During a B4B
// drag this approximates the live envelope instead: the hinge/latch/handle
// offset between the envelope and the edited field is basically constant
// for a given axis, so envelope = edited field + (that offset at drag
// start). Corrects itself to the exact server value once the drag commits
// and a real preview lands.
function dimensionDisplayOverride(outerXYZ) {
  const drag = state.dimensionDrag;
  if (!drag || drag.view !== "3d" || !outerXYZ) return outerXYZ;
  const index = { x: 0, y: 1, z: 2 }[drag.axis];
  const offset = drag.displayStartValue - drag.startValue;
  const next = outerXYZ.slice();
  next[index] = drag.currentValue + offset;
  return next;
}

function pickResizeCursor(handle) {
  const [ax, ay] = handle.screenAxis;
  return Math.abs(ax) >= Math.abs(ay) ? "ew-resize" : "ns-resize";
}

function beginDimensionDrag(view, handle, canvas, event) {
  state.dimensionDrag = {
    view,
    axis: handle.axis,
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startValue: handle.value,
    currentValue: handle.value,
    // The guide is drawn/scaled to displayValue (B4B's assembled envelope,
    // same as `value` everywhere else) - pixelsPerMm must use that, not the
    // edited field, or the drag would run at the wrong speed for B4B.
    displayStartValue: handle.displayValue,
    originalDesign: clone(state.design),
    screenAxis: handle.screenAxis,
    pixelSpan: handle.pixelSpan,
  };
  state.dimensionHover = null;
  canvas.style.cursor = pickResizeCursor(handle);
  try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
}

// Applies only to the transient drag/sidebar-field state - state.design.box
// itself is untouched until commitDimensionDrag() lands on pointerup.
function updateDimensionDrag(clientX, clientY) {
  const drag = state.dimensionDrag;
  if (!drag) return;
  const dx = clientX - drag.startClientX;
  const dy = clientY - drag.startClientY;
  const projectedPixels = dx * drag.screenAxis[0] + dy * drag.screenAxis[1];
  const pixelsPerMm = drag.pixelSpan / Math.max(1e-6, drag.displayStartValue);
  const requested = drag.startValue + projectedPixels / pixelsPerMm;
  drag.currentValue = normalizeBinDimension(drag.axis, requested, drag.startValue);
  const field = drag.axis === "x" ? "#x-size" : drag.axis === "y" ? "#y-size" : "#z";
  const input = $(field);
  if (input && document.activeElement !== input) input.value = fmt(drag.currentValue);
}

function releaseDimensionPointerCapture(canvas, pointerId) {
  canvas.style.cursor = "";
  try { if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId); } catch (_error) {}
}

// One completed drag = one Undo entry (see item 12 of fix3d.md) - the same
// design-change path a typed Width/Length/Height edit uses, so manual-size
// and auto-grow semantics stay identical between mouse and keyboard.
function commitDimensionDrag(canvas) {
  const drag = state.dimensionDrag;
  if (!drag) return;
  state.dimensionDrag = null;
  releaseDimensionPointerCapture(canvas, drag.pointerId);
  if (drag.currentValue === drag.startValue) return;
  const previousDesign = drag.originalDesign;
  state.design.box[drag.axis] = drag.currentValue;
  if (drag.axis !== "z") {
    formatDimField(drag.axis);
    markBinAxisManual(drag.axis);
  } else {
    formatHeightField();
  }
  // A dragged Width/Length handle is exactly as deliberate as typing the
  // field - it must turn off Photo Nest Auto footprint sizing the same way
  // (see updateDesignFromForm / turnOffNestAutoSizeForManualEdit). Height is
  // independent and never disables it.
  if (drag.axis !== "z") {
    turnOffNestAutoSizeForManualEdit();
  }
  state.canGenerate = false;
  updateGenerateAvailability();
  changedDesign(previousDesign);
}

function cancelDimensionDrag(canvas) {
  const drag = state.dimensionDrag;
  if (!drag) return;
  state.dimensionDrag = null;
  releaseDimensionPointerCapture(canvas, drag.pointerId);
  state.design = drag.originalDesign;
  syncForm();
}

function updateDimensionHover(view, handle, canvas) {
  const prev = state.dimensionHover;
  const changed = (prev?.view !== handle?.view) || (prev?.axis !== handle?.axis);
  state.dimensionHover = handle;
  canvas.style.cursor = handle ? pickResizeCursor(handle) : "";
  return changed;
}

// Mirrors draw3DDimensions' own outer-extent math so the ghost always
// matches the guides it belongs to - the true assembled envelope for B4B,
// box.x/y/z everywhere else.
function drawDimensionGhost3D(context, camera, project, box, outerXYZ) {
  const drag = state.dimensionDrag;
  if (!drag || drag.view !== "3d" || !box) return;
  const outerX = outerXYZ ? number(outerXYZ[0]) : number(box.x);
  const outerY = outerXYZ ? number(outerXYZ[1]) : number(box.y);
  const outerZ = outerXYZ ? number(outerXYZ[2]) : number(box.z);
  const hx = outerX / 2, hy = outerY / 2, hz = outerZ;
  if (hx <= 0 || hy <= 0 || hz <= 0) return;
  const corners3d = [
    [-hx, -hy, 0], [hx, -hy, 0], [hx, hy, 0], [-hx, hy, 0],
    [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz],
  ];
  const s = corners3d.map(point => project(iso(point, camera)));
  const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
  context.save();
  context.strokeStyle = "rgba(31, 107, 112, 0.85)";
  context.lineWidth = 1.25;
  context.setLineDash([5, 4]);
  for (const [a, b] of edges) {
    context.beginPath();
    context.moveTo(s[a][0], s[a][1]);
    context.lineTo(s[b][0], s[b][1]);
    context.stroke();
  }
  context.restore();
}

function drawDimensionGhost2D(context, toCanvas, bounds) {
  const drag = state.dimensionDrag;
  if (!drag || drag.view !== "2d") return;
  const cx = (bounds[0] + bounds[2]) / 2, cy = (bounds[1] + bounds[3]) / 2;
  const ratio = drag.currentValue / Math.max(1e-6, drag.startValue);
  let halfX = (bounds[2] - bounds[0]) / 2, halfY = (bounds[3] - bounds[1]) / 2;
  if (drag.axis === "x") halfX *= ratio;
  if (drag.axis === "y") halfY *= ratio;
  const corners = [
    [cx - halfX, cy - halfY], [cx + halfX, cy - halfY],
    [cx + halfX, cy + halfY], [cx - halfX, cy + halfY],
  ];
  context.save();
  context.strokeStyle = "rgba(31, 107, 112, 0.85)";
  context.lineWidth = 1.5;
  context.setLineDash([6, 4]);
  context.beginPath();
  corners.forEach((point, index) => {
    const c = toCanvas(point);
    index === 0 ? context.moveTo(c[0], c[1]) : context.lineTo(c[0], c[1]);
  });
  context.closePath();
  context.stroke();
  context.restore();
}

function wireSceneInteraction(canvas, camera, render) {
  let drag = null;
  // A pointer reports far faster than the screen refreshes, and a mesh preview
  // repaint is expensive. Coalesce to one repaint per frame, always with the
  // camera as it stands when that frame runs: the same picture, without
  // queueing up work the screen will never show.
  let framePending = false;
  const repaint = () => {
    if (framePending) return;
    framePending = true;
    requestAnimationFrame(() => { framePending = false; render(); });
  };
  canvas.addEventListener("pointerdown", event => {
    // A dimension label always wins over orbit - hit-test it first so a
    // drag that starts on "Width 96 mm" resizes the bin instead of spinning
    // the camera (see fix3d.md, item 5).
    if (!state.designMutationBusy) {
      const handle = hitDimensionHandle("3d", canvasPointFromEvent(canvas, event));
      if (handle) {
        beginDimensionDrag("3d", handle, canvas, event);
        repaint();
        return;
      }
    }
    // Degrees per pixel scale to the canvas itself (as TinkerCAD's orbit
    // does) so a drag spins the model by the same feel regardless of how
    // wide the preview panel happens to be - a drag clear across it is
    // about one full turn.
    drag = {
      x: event.clientX, y: event.clientY, yaw: camera.yaw, elevation: camera.elevation, moved: false,
      yawPerPixel: 360 / Math.max(200, canvas.clientWidth),
      elevationPerPixel: 240 / Math.max(200, canvas.clientHeight),
    };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (state.dimensionDrag) {
      updateDimensionDrag(event.clientX, event.clientY);
      repaint();
      return;
    }
    if (!drag) {
      const handle = hitDimensionHandle("3d", canvasPointFromEvent(canvas, event));
      if (updateDimensionHover("3d", handle, canvas)) repaint();
      return;
    }
    if (!drag.moved && Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) {
      drag.moved = true;
      $$('[data-camera-view]').forEach(button => button.classList.remove("active"));
    }
    camera.yaw = drag.yaw + (event.clientX - drag.x) * drag.yawPerPixel;
    camera.elevation = Math.max(-89, Math.min(89, drag.elevation - (event.clientY - drag.y) * drag.elevationPerPixel));
    repaint();
  });
  canvas.addEventListener("pointerup", event => {
    if (state.dimensionDrag) {
      commitDimensionDrag(canvas);
      repaint();
      return;
    }
    const clickedSupport = drag && !drag.moved && clickedPreviewSupport(canvas, event);
    drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (clickedSupport) {
      const dialog = $("#support-layout-dialog");
      if (!dialog.open) dialog.showModal();
    }
  });
  canvas.addEventListener("pointercancel", () => {
    if (state.dimensionDrag) {
      cancelDimensionDrag(canvas);
      repaint();
    }
    drag = null;
  });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    camera.zoom = Math.max(.35, Math.min(4, camera.zoom * Math.exp(-event.deltaY * .001)));
    repaint();
  }, { passive: false });
  canvas.addEventListener("dblclick", () => {
    setCameraView("reset");
  });
}

function layoutFeatures() {
  const features = state.design.layout.features.map(feature => clone(feature));
  if (state.layoutDrag?.feature && state.layoutDrag.index !== null) features[state.layoutDrag.index] = state.layoutDrag.feature;
  return features;
}

// The floor a placed support actually covers, in world space, or null when it
// simply fills its own zone and there is nothing extra to draw. The server
// works this out (see occupied_zones) against the saved zone, so a live drag -
// which moves a support without waiting for the next preview - shifts it by the
// same amount. A resize drag only re-centres it until that preview lands.
function footprintWorld(feature, index) {
  const all = state.preview?.feature_footprints;
  if (!all || all.length !== state.design.layout.features.length) return null;
  const covered = all[index];
  if (!covered) return null;
  const saved = state.design.layout.features[index].zone;
  const dx = (feature.zone[0] + feature.zone[2] - saved[0] - saved[2]) / 2;
  const dy = (feature.zone[1] + feature.zone[3] - saved[1] - saved[3]) / 2;
  if (!dx && !dy) return covered;
  return [covered[0] + dx, covered[1] + dy, covered[2] + dx, covered[3] + dy];
}

// The nest silhouette in world space. Prefer the server's softened contour
// (the Soften outline pass, in the feature's own local mm) so the 2D layout
// matches the 3D preview and the printed part; the raw contour is the fallback
// before the first preview comes back. Move/rotate/resize stay client-side, so
// this still tracks a live drag - smoothing does not depend on those.
function nestOutlineWorld(feature, softContour = null) {
  const local = softContour?.length ? softContour : feature?.contour;
  if (!local?.length) return [];
  const cx = (feature.zone[0] + feature.zone[2]) / 2;
  const cy = (feature.zone[1] + feature.zone[3]) / 2;
  const angle = number(feature.rotation) * Math.PI / 180;
  const scale = Math.max(.05, number(feature.scale, 1));
  const cosine = Math.cos(angle), sine = Math.sin(angle);
  return local.map(([x, y]) => [
    cx + scale * (number(x) * cosine - number(y) * sine),
    cy + scale * (number(x) * sine + number(y) * cosine),
  ]);
}

function nestLocalToWorld(feature, [x, y]) {
  const cx = (feature.zone[0] + feature.zone[2]) / 2;
  const cy = (feature.zone[1] + feature.zone[3]) / 2;
  const angle = number(feature.rotation) * Math.PI / 180;
  const scale = Math.max(.05, number(feature.scale, 1));
  const cosine = Math.cos(angle), sine = Math.sin(angle);
  return [
    cx + scale * (number(x) * cosine - number(y) * sine),
    cy + scale * (number(x) * sine + number(y) * cosine),
  ];
}

function nestWorldToLocal(feature, [x, y]) {
  const cx = (feature.zone[0] + feature.zone[2]) / 2;
  const cy = (feature.zone[1] + feature.zone[3]) / 2;
  const angle = -number(feature.rotation) * Math.PI / 180;
  const scale = Math.max(.05, number(feature.scale, 1));
  const dx = (x - cx) / scale, dy = (y - cy) / scale;
  return [dx * Math.cos(angle) - dy * Math.sin(angle),
    dx * Math.sin(angle) + dy * Math.cos(angle)];
}

function normalizeNestContour(feature) {
  if (!feature?.contour?.length) return;
  const xs = feature.contour.map(point => number(point[0]));
  const ys = feature.contour.map(point => number(point[1]));
  const offset = [(Math.min(...xs) + Math.max(...xs)) / 2,
    (Math.min(...ys) + Math.max(...ys)) / 2];
  if (Math.abs(offset[0]) < 1e-9 && Math.abs(offset[1]) < 1e-9) return;
  const movedCentre = nestLocalToWorld(feature, offset);
  feature.contour = feature.contour.map(([x, y]) => [number(x) - offset[0], number(y) - offset[1]]);
  // source_contour lives in the same local frame as contour - carry it
  // through the same shift, or a later Reset Outline would restore a
  // baseline offset from where it should be.
  if (feature.source_contour?.length) {
    feature.source_contour = feature.source_contour.map(
      ([x, y]) => [number(x) - offset[0], number(y) - offset[1]]
    );
  }
  feature.zone = [movedCentre[0] - .5, movedCentre[1] - .5,
    movedCentre[0] + .5, movedCentre[1] + .5];
  if (state.nestPhoto?.bounds) {
    const [x0, y0, x1, y1] = state.nestPhoto.bounds;
    state.nestPhoto.bounds = [x0 - offset[0], y0 - offset[1],
      x1 - offset[0], y1 - offset[1]];
  }
}

function drawNestPhotoReference(context, feature, toCanvas) {
  const reference = state.nestPhoto;
  if (!reference?.image?.complete || !reference.image.naturalWidth || !feature?.contour?.length) return;
  const [x0, y0, x1, y1] = reference.bounds;
  const topLeft = toCanvas(nestLocalToWorld(feature, [x0, y1]));
  const topRight = toCanvas(nestLocalToWorld(feature, [x1, y1]));
  const bottomLeft = toCanvas(nestLocalToWorld(feature, [x0, y0]));
  const width = reference.image.naturalWidth, height = reference.image.naturalHeight;
  context.save();
  context.globalAlpha = Math.min(1, Math.max(0, number(state.nestPhotoOpacity, 45) / 100));
  context.transform(
    (topRight[0] - topLeft[0]) / width,
    (topRight[1] - topLeft[1]) / width,
    (bottomLeft[0] - topLeft[0]) / height,
    (bottomLeft[1] - topLeft[1]) / height,
    topLeft[0], topLeft[1],
  );
  context.drawImage(reference.image, 0, 0);
  context.restore();
}

function drawNestContourHandles(context, feature, toCanvas) {
  if (!feature?.contour?.length) return;
  context.save();
  context.fillStyle = "#ffffff";
  context.strokeStyle = "#176e91";
  context.lineWidth = 1.5;
  for (const point of feature.contour) {
    const [x, y] = toCanvas(nestLocalToWorld(feature, point));
    context.beginPath();
    context.arc(x, y, 3.5, 0, Math.PI * 2);
    context.fill();
    context.stroke();
  }
  context.restore();
}

function drawPendingNestTrace(context, width, height) {
  const trace = state.nestTraceResult;
  if (state.draft?.kind !== "nest" || state.draft.contour || !trace?.contour?.length) return false;
  const accepted = trace.contour;
  const candidate = state.nestCandidateContour;
  const all = candidate?.length ? [...accepted, ...candidate] : accepted;
  const xs = all.map(point => number(point[0]));
  const ys = all.map(point => number(point[1]));
  if (state.nestPhoto?.bounds) {
    const [x0, y0, x1, y1] = state.nestPhoto.bounds;
    xs.push(x0, x1);
    ys.push(y0, y1);
  }
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX), spanY = Math.max(1, maxY - minY);
  const pad = Math.max(24, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const toCanvas = ([x, y]) => [
    width / 2 + (number(x) - cx) * scale,
    height / 2 - (number(y) - cy) * scale,
  ];
  const pending = { contour: accepted, zone: [-.5, -.5, .5, .5], rotation: 0, scale: 1 };
  drawNestPhotoReference(context, pending, toCanvas);
  const drawOutline = (points, color, dashed = false) => {
    const path = drawClosedPath(context, points, toCanvas);
    context.save();
    context.strokeStyle = "rgba(255,255,255,.95)";
    context.lineWidth = 8;
    context.stroke(path);
    if (dashed) context.setLineDash([6, 4]);
    context.strokeStyle = color;
    context.lineWidth = dashed ? 4 : 3;
    context.stroke(path);
    context.restore();
  };
  drawOutline(accepted, "#145d76");
  if (candidate?.length) drawOutline(candidate, "#007ca8", true);
  return true;
}

// Whether the dedicated outline-editor workspace should own the 2D canvas
// right now: an already-committed Photo Nest feature is open for editing.
// The pre-commit "waiting on Tool thickness" case is handled above by
// drawPendingNestTrace instead, since it has no manual-edit handles yet.
function isNestEditWorkspaceActive() {
  return state.draft?.kind === "nest" && Boolean(state.draft.contour?.length)
    && state.nestOutlineEditing === true;
}

function nestOccurrenceOutlines(feature, softContour, occurrences) {
  const local = softContour?.length ? softContour : feature?.contour;
  if (!local?.length || !Array.isArray(occurrences) || !occurrences.length) {
    return [nestOutlineWorld(feature, softContour)];
  }
  const scale = Math.max(.05, number(feature.scale, 1));
  return occurrences.map(occurrence => {
    const angle = number(occurrence.rotation) * Math.PI / 180;
    const cosine = Math.cos(angle), sine = Math.sin(angle);
    return local.map(([x, y]) => [
      number(occurrence.x) + scale * (number(x) * cosine - number(y) * sine),
      number(occurrence.y) + scale * (number(x) * sine + number(y) * cosine),
    ]);
  });
}

// The dedicated 2D outline editor (spec: "Nested 2D Outline Editing"): the
// nest's own photo, outline and edit handles, fitted then zoomed/panned to
// fill the whole canvas. None of the bin's walls, grid or other parts are
// relevant to "what shape is this object?" and are deliberately not drawn
// here - see renderLayout2D's early return. Reuses the ordinary
// state.layoutTransform contract, so the existing point-drag and
// hit-testing code keeps working unchanged at any zoom/pan.
function drawNestEditWorkspace(context, width, height) {
  if (!isNestEditWorkspaceActive()) return false;
  const index = state.selected;
  const dragging = state.layoutDrag?.mode === "point" && state.layoutDrag.index === index;
  const feature = dragging ? state.layoutDrag.feature : state.draft;
  const softContour = dragging ? null : state.preview?.nest_soft_contours?.[index];
  const outlineWorld = nestOutlineWorld(feature, softContour);
  // The viewport fit is taken from the stable committed draft, never the
  // live drag copy - a point being dragged toward the current edge of the
  // outline must not rescale the view out from under the pointer mid-drag.
  const fitOutlineWorld = dragging ? nestOutlineWorld(state.draft, softContour) : outlineWorld;
  const xs = fitOutlineWorld.map(point => point[0]);
  const ys = fitOutlineWorld.map(point => point[1]);
  if (state.nestPhoto?.bounds) {
    const [x0, y0, x1, y1] = state.nestPhoto.bounds;
    for (const corner of [[x0, y0], [x0, y1], [x1, y0], [x1, y1]]) {
      const at = nestLocalToWorld(state.draft, corner);
      xs.push(at[0]); ys.push(at[1]);
    }
  }
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = Math.max(1, maxX - minX), spanY = Math.max(1, maxY - minY);
  const pad = Math.max(24, Math.min(width, height) * .08);
  const fitScale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  // Snapshot the pure (zoom-independent) fit so the zoom controls can
  // convert a canvas point to world space and back without re-deriving it.
  state.nestFit = { cx, cy, fitScale, width, height };
  const zoom = Math.max(.5, Math.min(12, number(state.nestViewZoom, 1)));
  const panX = number(state.nestViewPanX, 0), panY = number(state.nestViewPanY, 0);
  const scale = fitScale * zoom;
  const toCanvas = ([x, y]) => [
    width / 2 + (number(x) - cx) * scale + panX,
    height / 2 - (number(y) - cy) * scale + panY,
  ];
  const toWorld = ([px, py]) => [
    cx + (px - width / 2 - panX) / scale,
    cy - (py - height / 2 - panY) / scale,
  ];
  state.layoutTransform = { toCanvas, toWorld, scale };

  drawNestPhotoReference(context, feature, toCanvas);

  const outline = drawClosedPath(context, outlineWorld, toCanvas);
  context.fillStyle = kindColor("nest") + "35";
  context.fill(outline);
  context.save();
  context.strokeStyle = "rgba(255,255,255,.95)";
  context.lineWidth = 7;
  context.stroke(outline);
  context.strokeStyle = "#145d76";
  context.lineWidth = 3;
  context.stroke(outline);
  context.restore();

  if (state.nestCandidateContour?.length) {
    const candidateWorld = state.nestCandidateContour.map(point => nestLocalToWorld(feature, point));
    const candidatePath = drawClosedPath(context, candidateWorld, toCanvas);
    context.save();
    context.strokeStyle = "rgba(255,255,255,.95)";
    context.lineWidth = 8;
    context.stroke(candidatePath);
    context.setLineDash([6, 4]);
    context.strokeStyle = "#007ca8";
    context.lineWidth = 4;
    context.stroke(candidatePath);
    context.restore();
  }

  // Access-plan markers (finger-grasp scoop/notch) are generated 3D-holder
  // geometry, not part of "what shape is this object?" - they belong with
  // the ordinary Nest/3D view, not this outline editor.
  drawNestContourHandles(context, feature, toCanvas);
  return true;
}

// Zoom the dedicated outline editor, keeping the world point under
// canvasPoint (or the viewport centre, for the +/- buttons) fixed on
// screen - this is what makes wheel-zoom feel centred on the cursor.
// Purely a viewport change: never touches the contour itself.
function nestZoomBy(factor, canvasPoint = null) {
  if (!isNestEditWorkspaceActive() || !state.nestFit) return;
  const fit = state.nestFit;
  const point = canvasPoint || [fit.width / 2, fit.height / 2];
  const oldZoom = Math.max(.5, Math.min(12, number(state.nestViewZoom, 1)));
  const newZoom = Math.max(.5, Math.min(12, oldZoom * factor));
  const oldScale = fit.fitScale * oldZoom;
  const worldX = fit.cx + (point[0] - fit.width / 2 - number(state.nestViewPanX, 0)) / oldScale;
  const worldY = fit.cy - (point[1] - fit.height / 2 - number(state.nestViewPanY, 0)) / oldScale;
  const newScale = fit.fitScale * newZoom;
  state.nestViewZoom = newZoom;
  state.nestViewPanX = point[0] - fit.width / 2 - (worldX - fit.cx) * newScale;
  state.nestViewPanY = point[1] - fit.height / 2 + (worldY - fit.cy) * newScale;
  renderLayout2D();
}

function resetNestView() {
  state.nestViewZoom = 1;
  state.nestViewPanX = 0;
  state.nestViewPanY = 0;
  renderLayout2D();
}

// Informational-only markers for the server's resolved access plan (spec
// section 46) - a small ring for each point, filled for a scoop (Recessed),
// hollow for a notch (Raised Wall). Draws nothing when access is off, and
// nothing when the plan could not place anything (its warning covers that).
function drawNestAccessIndicators(context, access, toCanvas) {
  if (!access || access.style !== "finger_grasp" || !access.points?.length) return;
  const filled = access.holder_style === "recessed";
  context.save();
  context.strokeStyle = "#1f7a4d";
  context.fillStyle = "#1f7a4d55";
  context.lineWidth = 1.5;
  const radius = Math.max(3, Math.min(10, (access.width || 20) / 2 * (state.layoutTransform?.scale || 1)));
  for (const point of access.points) {
    const [x, y] = toCanvas([point.x, point.y]);
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    if (filled) context.fill();
    context.stroke();
  }
  context.restore();
}

function hitNestContourPoint(feature, world) {
  if (!feature?.contour?.length || !state.layoutTransform) return null;
  let closest = null, distance = 10;
  feature.contour.forEach((point, index) => {
    const at = nestLocalToWorld(feature, point);
    const pixels = Math.hypot(world[0] - at[0], world[1] - at[1]) * state.layoutTransform.scale;
    if (pixels < distance) { closest = index; distance = pixels; }
  });
  return closest;
}

// Nearest point on the contour's boundary to a world-space click, within
// ~12 screen pixels - used by the Add Point tool to find which segment to
// split. Returns the segment's first vertex index and the projected point
// in the outline's own local (pre-rotation/placement) coordinates.
function hitNestContourSegment(feature, world) {
  if (!feature?.contour?.length || !state.layoutTransform) return null;
  const scale = state.layoutTransform.scale;
  const count = feature.contour.length;
  let closest = null, distance = 12;
  for (let i = 0; i < count; i++) {
    const a = nestLocalToWorld(feature, feature.contour[i]);
    const b = nestLocalToWorld(feature, feature.contour[(i + 1) % count]);
    const abx = b[0] - a[0], aby = b[1] - a[1];
    const lengthSq = abx * abx + aby * aby;
    let t = lengthSq > 1e-9 ? ((world[0] - a[0]) * abx + (world[1] - a[1]) * aby) / lengthSq : 0;
    t = Math.max(0, Math.min(1, t));
    const projected = [a[0] + t * abx, a[1] + t * aby];
    const pixels = Math.hypot(world[0] - projected[0], world[1] - projected[1]) * scale;
    if (pixels < distance) { closest = { index: i, world: projected }; distance = pixels; }
  }
  return closest ? { index: closest.index, local: nestWorldToLocal(feature, closest.world) } : null;
}

// Add Point / Delete Point / Reset Outline all go through here: apply the
// edited contour as the selected Nest's new draft and commit it exactly like
// any other field edit - the server validates the polygon and access plan,
// and an invalid result is rejected and the previous contour restored,
// exactly as dragging a point already does.
async function commitNestContourEdit(index, newContour, extra = {}) {
  markDraftChanged();
  const updated = clone(
    state.selected === index && state.draft ? state.draft : state.design.layout.features[index]
  );
  updated.contour = newContour;
  Object.assign(updated, extra);
  normalizeNestContour(updated);
  state.draft = updated;
  state.selected = index;
  state.draftKind = "nest";
  state.draftAutoCommit = true;
  renderDraftFields();
  renderLayout2D();
  const applied = await applySupport(index);
  if (!applied) {
    state.draft = clone(state.design.layout.features[index]);
    renderDraftFields();
    renderLayout2D();
  }
}

function drawClosedPath(context, points, toCanvas) {
  const path = new Path2D();
  points.forEach((point, index) => {
    const p = toCanvas(point);
    index === 0 ? path.moveTo(p[0], p[1]) : path.lineTo(p[0], p[1]);
  });
  path.closePath();
  return path;
}

// `handle`, when given, registers a canvas-space hit region around the label
// into state.layoutDimensionHandles - see hitDimensionHandle().
function drawDimensionLine(context, start, end, label, vertical = false, handle = null) {
  context.save();
  const active = handle && (
    (state.dimensionHover?.view === handle.view && state.dimensionHover?.axis === handle.axis) ||
    (state.dimensionDrag?.view === handle.view && state.dimensionDrag?.axis === handle.axis)
  );
  context.strokeStyle = active ? "#237fa6" : "#496873";
  context.fillStyle = "#496873";
  context.lineWidth = active ? 1.5 : 1;
  context.font = "700 11px Segoe UI";
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.beginPath();
  context.moveTo(start[0], start[1]);
  context.lineTo(end[0], end[1]);
  context.stroke();
  const angle = Math.atan2(end[1] - start[1], end[0] - start[0]);
  for (const [point, direction] of [[start, 1], [end, -1]]) {
    context.beginPath();
    context.moveTo(point[0], point[1]);
    context.lineTo(point[0] + Math.cos(angle + .55) * 7 * direction, point[1] + Math.sin(angle + .55) * 7 * direction);
    context.moveTo(point[0], point[1]);
    context.lineTo(point[0] + Math.cos(angle - .55) * 7 * direction, point[1] + Math.sin(angle - .55) * 7 * direction);
    context.stroke();
  }
  const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
  context.translate(middle[0], middle[1]);
  if (vertical) context.rotate(-Math.PI / 2);
  const textWidth = context.measureText(label).width;
  context.fillStyle = active ? "rgba(230,245,248,.96)" : "rgba(248,250,249,.92)";
  context.fillRect(-textWidth / 2 - 5, -8, textWidth + 10, 16);
  context.strokeStyle = active ? "#237fa6" : "transparent";
  if (active) context.strokeRect(-textWidth / 2 - 5, -8, textWidth + 10, 16);
  context.fillStyle = "#496873";
  context.fillText(label, 0, 0);
  context.restore();

  if (handle) {
    const padHit = 9;
    const halfW = textWidth / 2 + 5 + padHit;
    const halfH = Math.max(14, 8 + padHit);
    const rot = vertical ? -Math.PI / 2 : 0;
    const cos = Math.cos(rot), sin = Math.sin(rot);
    const corners = [[-halfW, -halfH], [halfW, -halfH], [halfW, halfH], [-halfW, halfH]]
      .map(([lx, ly]) => [middle[0] + lx * cos - ly * sin, middle[1] + lx * sin + ly * cos]);
    const xs = corners.map(point => point[0]);
    const ys = corners.map(point => point[1]);
    const dx = end[0] - start[0], dy = end[1] - start[1];
    const span = Math.hypot(dx, dy);
    let screenAxisX = dx / span, screenAxisY = dy / span;
    if (Math.abs(dx) >= Math.abs(dy)) {
      if (dx < 0) { screenAxisX = -screenAxisX; screenAxisY = -screenAxisY; }
    } else if (dy > 0) {
      screenAxisX = -screenAxisX; screenAxisY = -screenAxisY;
    }
    state.layoutDimensionHandles.push({
      view: "2d",
      axis: handle.axis,
      hitBox: {
        x: Math.min(...xs), y: Math.min(...ys),
        width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys),
      },
      screenAxis: [screenAxisX, screenAxisY],
      pixelSpan: span,
      value: handle.value,
      displayValue: handle.value,
      labelCenter: middle,
    });
  }
}

function renderLayoutText(context, feature, toCanvas, scale, isDraft = false) {
  const text = String(feature.options?.text ?? "").trim();
  const zone = feature.zone;
  const turns = ((Number(feature.options?.quarter_turns || 0) % 4) + 4) % 4;
  const zw = Math.abs(zone[2] - zone[0]);
  const zd = Math.abs(zone[3] - zone[1]);
  const cx = (zone[0] + zone[2]) / 2;
  const cy = (zone[1] + zone[3]) / 2;
  const centerCanvas = toCanvas([cx, cy]);
  const run = (turns % 2 === 0) ? zw : zd;
  const across = (turns % 2 === 0) ? zd : zw;

  if (!text) {
    context.save();
    context.fillStyle = "rgba(20,36,42,.35)";
    context.font = "italic 11px Segoe UI, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("Text", centerCanvas[0], centerCanvas[1]);
    context.restore();
    return;
  }

  context.save();
  context.font = 'bold 100px "DejaVu Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif';
  const refWidth = context.measureText(text).width || 100;
  context.restore();

  const aspect = (refWidth / 100) / 0.729;
  const fitRun = Math.max(0.1, run - 0.5) / Math.max(0.1, aspect);
  const fitAcross = Math.max(0.1, across - 0.5) / 1.15;
  const fits = Math.min(fitRun, fitAcross);

  let cap = Number(feature.options?.cap_height);
  if (!Number.isFinite(cap) || cap <= 0) {
    cap = Math.min(7.0, fits);
  } else {
    cap = Math.min(cap, fits);
  }
  cap = Math.max(cap, 3.5);

  const fontSizePx = Math.max(6, (cap / 0.729) * scale);
  const angle = -turns * (Math.PI / 2);

  context.save();
  context.translate(centerCanvas[0], centerCanvas[1]);
  context.rotate(angle);
  context.font = `bold ${fontSizePx}px "DejaVu Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = isDraft ? DRAFT_HIGHLIGHT : "#315766";
  context.fillText(text, 0, 0);
  context.restore();
}

function dividerGridCountsClient(feature) {
  const opt = feature?.options || {};
  const along = feature?.along || "x";
  const legacy = feature?.count == null ? 1 : Math.max(1, Math.round(number(feature.count, 1)));
  let gx = number(opt.count_x, NaN);
  if (!Number.isFinite(gx)) gx = along === "y" ? legacy : 0;
  let gy = number(opt.count_y, NaN);
  if (!Number.isFinite(gy)) gy = along === "x" ? legacy : 0;
  return [Math.max(0, Math.round(gx)), Math.max(0, Math.round(gy))];
}

function dividerEligibleClient(feature) {
  if (feature?.kind !== "divider") return false;
  const [gx, gy] = dividerGridCountsClient(feature);
  return gx > 1 || gy > 1 || (gx > 0 && gy > 0);
}

function normalizeDividerSpansClient(feature, rows, columns) {
  let raw = feature.options?.compartment_spans;
  if (raw === undefined || raw === null || raw === "") return { valid: true, spans: [] };
  if (typeof raw === "string") {
    try { raw = JSON.parse(raw); } catch { return { valid: false, spans: [] }; }
  }
  if (!Array.isArray(raw)) return { valid: false, spans: [] };

  const claimed = Array.from({ length: rows }, () => Array(columns).fill(false));
  const spans = [];
  for (const rawSpan of raw) {
    if (!rawSpan || typeof rawSpan !== "object" || Array.isArray(rawSpan)) {
      return { valid: false, spans: [] };
    }
    const values = [rawSpan.row, rawSpan.column, rawSpan.row_span, rawSpan.column_span];
    if (!values.every(Number.isInteger)) return { valid: false, spans: [] };
    const [row, column, rowSpan, columnSpan] = values;
    if (row < 0 || column < 0 || rowSpan < 1 || columnSpan < 1 ||
        row + rowSpan > rows || column + columnSpan > columns) {
      return { valid: false, spans: [] };
    }
    if (rowSpan === 1 && columnSpan === 1) continue;
    for (let oneRow = row; oneRow < row + rowSpan; oneRow++) {
      for (let oneColumn = column; oneColumn < column + columnSpan; oneColumn++) {
        if (claimed[oneRow][oneColumn]) return { valid: false, spans: [] };
      }
    }
    const span = { row, column, rowSpan, columnSpan };
    spans.push(span);
    for (let oneRow = row; oneRow < row + rowSpan; oneRow++) {
      for (let oneColumn = column; oneColumn < column + columnSpan; oneColumn++) {
        claimed[oneRow][oneColumn] = true;
      }
    }
  }
  spans.sort((a, b) => a.row - b.row || a.column - b.column ||
    a.rowSpan - b.rowSpan || a.columnSpan - b.columnSpan);
  return { valid: true, spans };
}

function dividerCompartmentsClient(feature) {
  const [gx, gy] = dividerGridCountsClient(feature);
  const columns = gx + 1, rows = gy + 1;
  const [x0, y0, x1, y1] = feature.zone;
  const xEdges = Array.from({ length: columns + 1 }, (_, index) => x0 + index * (x1 - x0) / columns);
  const yEdges = Array.from({ length: rows + 1 }, (_, index) => y0 + index * (y1 - y0) / rows);
  const normalized = normalizeDividerSpansClient(feature, rows, columns);
  const owner = Array.from({ length: rows }, () => Array(columns).fill(null));
  if (!normalized.valid) {
    return { valid: false, gx, gy, rows, columns, xEdges, yEdges, cells: [], owner };
  }
  const rectangles = [];
  for (const cell of normalized.spans) {
    const { row, column, rowSpan, columnSpan } = cell;
    rectangles.push(cell);
    for (let r = row; r < row + rowSpan; r++) {
      for (let c = column; c < column + columnSpan; c++) owner[r][c] = cell;
    }
  }
  for (let row = 0; row < rows; row++) {
    for (let column = 0; column < columns; column++) {
      if (owner[row][column]) continue;
      const cell = { row, column, rowSpan: 1, columnSpan: 1 };
      rectangles.push(cell);
      owner[row][column] = cell;
    }
  }
  const thickness = number(feature.options?.thickness, 1.6);
  rectangles.sort((a, b) => a.row - b.row || a.column - b.column);
  for (const cell of rectangles) {
    const rowEnd = cell.row + cell.rowSpan;
    const columnEnd = cell.column + cell.columnSpan;
    cell.zone = [
      xEdges[cell.column] + (cell.column ? thickness / 2 : 0),
      yEdges[cell.row] + (cell.row ? thickness / 2 : 0),
      xEdges[columnEnd] - (columnEnd < columns ? thickness / 2 : 0),
      yEdges[rowEnd] - (rowEnd < rows ? thickness / 2 : 0),
    ];
  }
  return { valid: true, gx, gy, rows, columns, xEdges, yEdges, cells: rectangles, owner };
}

function serializeDividerSpansClient(cells) {
  return cells
    .filter(cell => cell.rowSpan > 1 || cell.columnSpan > 1)
    .map(cell => ({
      row: cell.row, column: cell.column,
      row_span: cell.rowSpan, column_span: cell.columnSpan,
    }))
    .sort((a, b) => a.row - b.row || a.column - b.column ||
      a.row_span - b.row_span || a.column_span - b.column_span);
}

function dividerMergeClient(a, b) {
  if (a.row === b.row && a.rowSpan === b.rowSpan &&
      (a.column + a.columnSpan === b.column || b.column + b.columnSpan === a.column)) {
    return {
      row: a.row, column: Math.min(a.column, b.column), rowSpan: a.rowSpan,
      columnSpan: a.columnSpan + b.columnSpan,
    };
  }
  if (a.column === b.column && a.columnSpan === b.columnSpan &&
      (a.row + a.rowSpan === b.row || b.row + b.rowSpan === a.row)) {
    return {
      row: Math.min(a.row, b.row), column: a.column,
      rowSpan: a.rowSpan + b.rowSpan, columnSpan: a.columnSpan,
    };
  }
  return null;
}

function sameDividerCompartmentClient(a, b) {
  return Boolean(a && b &&
    a.row === b.row &&
    a.column === b.column &&
    a.rowSpan === b.rowSpan &&
    a.columnSpan === b.columnSpan);
}

function dividerBoundarySegmentsClient(feature, featureIndex, toCanvas) {
  if (!dividerEligibleClient(feature)) return [];
  const topology = dividerCompartmentsClient(feature);
  if (!topology.valid) return [];
  const hits = [];
  const add = (orientation, line, segment, a, b, p0, p1) => {
    const same = a === b;
    const merged = same ? null : dividerMergeClient(a, b);
    let operation0 = p0, operation1 = p1;
    if (same) {
      operation0 = orientation === "vertical"
        ? [topology.xEdges[line], topology.yEdges[a.row]]
        : [topology.xEdges[a.column], topology.yEdges[line]];
      operation1 = orientation === "vertical"
        ? [topology.xEdges[line], topology.yEdges[a.row + a.rowSpan]]
        : [topology.xEdges[a.column + a.columnSpan], topology.yEdges[line]];
    } else if (merged) {
      operation0 = orientation === "vertical"
        ? [topology.xEdges[line], topology.yEdges[merged.row]]
        : [topology.xEdges[merged.column], topology.yEdges[line]];
      operation1 = orientation === "vertical"
        ? [topology.xEdges[line], topology.yEdges[merged.row + merged.rowSpan]]
        : [topology.xEdges[merged.column + merged.columnSpan], topology.yEdges[line]];
    }
    hits.push({
      featureIndex, orientation, line, segment, a, b,
      action: same ? "split" : merged ? "merge" : "blocked", merged,
      screen0: toCanvas(p0), screen1: toCanvas(p1),
      operation0: toCanvas(operation0), operation1: toCanvas(operation1),
    });
  };
  for (let line = 1; line < topology.columns; line++) {
    for (let row = 0; row < topology.rows; row++) {
      add("vertical", line, row, topology.owner[row][line - 1], topology.owner[row][line],
        [topology.xEdges[line], topology.yEdges[row]],
        [topology.xEdges[line], topology.yEdges[row + 1]]);
    }
  }
  for (let line = 1; line < topology.rows; line++) {
    for (let column = 0; column < topology.columns; column++) {
      add("horizontal", line, column, topology.owner[line - 1][column], topology.owner[line][column],
        [topology.xEdges[column], topology.yEdges[line]],
        [topology.xEdges[column + 1], topology.yEdges[line]]);
    }
  }
  return hits;
}

function sameDividerHit(a, b) {
  return a === b || Boolean(a && b && a.featureIndex === b.featureIndex &&
    a.orientation === b.orientation && a.line === b.line && a.segment === b.segment);
}

function renderDividerSegments(context, feature, featureIndex, toCanvas) {
  const hits = dividerBoundarySegmentsClient(feature, featureIndex, toCanvas);
  state.dividerSegmentHits.push(...hits);
  for (const hit of hits) {
    const hovered = sameDividerHit(hit, state.dividerSegmentHover);
    context.save();
    context.beginPath();
    const start = hovered ? hit.operation0 : hit.screen0;
    const end = hovered ? hit.operation1 : hit.screen1;
    context.moveTo(start[0], start[1]); context.lineTo(end[0], end[1]);
    context.lineWidth = hovered ? 5 : hit.action === "split" ? 1.5 : 2.5;
    context.strokeStyle = hovered ? "#b07a22" : hit.action === "split" ? "rgba(49,87,102,.38)" : "#315766";
    if (hit.action === "split" && !hovered) context.setLineDash([5, 5]);
    context.stroke();
    context.restore();
  }
}

function distanceToDividerSegment(point, hit) {
  const [x, y] = point, [x0, y0] = hit.screen0, [x1, y1] = hit.screen1;
  const dx = x1 - x0, dy = y1 - y0;
  const length2 = dx * dx + dy * dy || 1;
  const t = Math.max(0, Math.min(1, ((x - x0) * dx + (y - y0) * dy) / length2));
  return Math.hypot(x - (x0 + t * dx), y - (y0 + t * dy));
}

function hitDividerSegment(point) {
  let best = null, distance = 8;
  for (const hit of state.dividerSegmentHits) {
    const next = distanceToDividerSegment(point, hit);
    if (next <= distance) { best = hit; distance = next; }
  }
  return best;
}

function renderDividerDivisionLabels(context, feature, toCanvas, scale) {
  const opt = feature.options || {};
  let labels = opt.division_labels;
  if (!labels) return;
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { labels = labels.split(","); }
  }
  if (!Array.isArray(labels) || !labels.length) return;

  const topology = dividerCompartmentsClient(feature);
  for (const cell of topology.cells) {
    const idx = cell.row * topology.columns + cell.column;
    if (idx >= labels.length) continue;
    const text = String(labels[idx] || "").trim();
    if (!text) continue;

    const [x0, rawY0, x1, y1] = cell.zone;
    let y0 = rawY0;
    if (opt.scoop && typeof opt.scoop === "object" && opt.division_level !== "rim") {
      y0 = (y0 + y1) / 2;
    }
    const cellW = Math.max(1, x1 - x0);
    const cellD = Math.max(1, y1 - y0);

    context.save();
    context.font = 'bold 100px "DejaVu Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif';
    const refWidth = context.measureText(text).width || 100;
    context.restore();

    const aspect = (refWidth / 100) / 0.729;
    const fitW = Math.max(0.1, cellW - 2) / Math.max(0.1, aspect);
    const fitD = Math.max(0.1, cellD - 2) / 1.15;
    const cap = Math.max(2.5, Math.min(fitW, fitD));

    const fontSizePx = Math.max(6, (cap / 0.729) * scale);
    const centerCanvas = toCanvas([(x0 + x1) / 2, (y0 + y1) / 2]);

    context.save();
    context.translate(centerCanvas[0], centerCanvas[1]);
    context.font = `bold ${fontSizePx}px "DejaVu Sans", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Arial, sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#1e4c5f";
    context.fillText(text, 0, 0);
    context.restore();
  }
}

function renderLayout2D() {
  if (!state.preview) return;
  state.layoutDimensionHandles = [];
  state.dividerSegmentHits = [];
  const canvas = $("#preview-2d");
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  if (drawPendingNestTrace(context, width, height)) return;
  if (drawNestEditWorkspace(context, width, height)) return;
  const bounds = state.preview.layout_bounds;
  const worldWidth = bounds[2] - bounds[0], worldHeight = bounds[3] - bounds[1];
  const layoutYaw = (state.layoutOrientation === "topup" ? 0 : state.camera.yaw) * Math.PI / 180;
  const cosine = Math.cos(layoutYaw), sine = Math.sin(layoutYaw);
  // Match the 3D camera's top-down projection: as it turns, the 2D placement
  // view turns with it.  This makes on-screen drag directions agree between
  // the two views without changing the layout's actual world coordinates.
  const layoutWidth = Math.abs(cosine) * worldWidth + Math.abs(sine) * worldHeight;
  const layoutHeight = Math.abs(sine) * worldWidth + Math.abs(cosine) * worldHeight;
  const pad = Math.max(42, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / layoutWidth, (height - 2 * pad) / layoutHeight);
  const cx = (bounds[0] + bounds[2]) / 2, cy = (bounds[1] + bounds[3]) / 2;
  const toCanvas = ([x, y]) => {
    const dx = x - cx, dy = y - cy;
    return [width / 2 + (dx * cosine - dy * sine) * scale,
      height / 2 + (-dx * sine - dy * cosine) * scale];
  };
  const toWorld = ([x, y]) => {
    const horizontal = (x - width / 2) / scale, vertical = (y - height / 2) / scale;
    return [cx + horizontal * cosine - vertical * sine,
      cy - horizontal * sine - vertical * cosine];
  };
  state.layoutTransform = { toCanvas, toWorld, scale };
  const worldRect = zone => drawClosedPath(context, [
    [zone[0], zone[1]], [zone[2], zone[1]], [zone[2], zone[3]], [zone[0], zone[3]],
  ], toCanvas);
  const cavity = state.preview.cavity_outline;
  const cavityPath = new Path2D();
  if (cavity && cavity.length) {
    cavity.forEach((point, index) => {
      const p = toCanvas(point);
      index === 0 ? cavityPath.moveTo(p[0], p[1]) : cavityPath.lineTo(p[0], p[1]);
    });
    cavityPath.closePath();
  } else {
    const path = worldRect(bounds);
    cavityPath.addPath(path);
  }
  context.fillStyle = "#ffffff";
  context.strokeStyle = "#5e7f88";
  context.lineWidth = 2;
  context.fill(cavityPath);
  context.stroke(cavityPath);
  context.save();
  context.clip(cavityPath);
  const pitch = state.design.layout.mode === "cartridge" ? 8 : 1;
  if (pitch * scale >= 8) {
    context.strokeStyle = "rgba(55,96,105,.10)";
    context.lineWidth = 1;
    for (let x = bounds[0] + pitch; x < bounds[2] - 1e-8; x += pitch) {
      const p0 = toCanvas([x, bounds[1]]), p1 = toCanvas([x, bounds[3]]);
      context.beginPath(); context.moveTo(p0[0], p0[1]); context.lineTo(p1[0], p1[1]); context.stroke();
    }
    for (let y = bounds[1] + pitch; y < bounds[3] - 1e-8; y += pitch) {
      const p0 = toCanvas([bounds[0], y]), p1 = toCanvas([bounds[2], y]);
      context.beginPath(); context.moveTo(p0[0], p0[1]); context.lineTo(p1[0], p1[1]); context.stroke();
    }
  }
  context.restore();
  // The flat rectangle every non-full-span support must still stay inside,
  // drawn as a reference against the true wavy wall around it.
  context.strokeStyle = "rgba(94,127,136,.55)";
  context.lineWidth = 1;
  context.setLineDash([4, 3]);
  context.stroke(worldRect(bounds));
  context.setLineDash([]);
  for (const reserved of state.preview.customization_zones) {
    const reservedPath = worldRect(reserved.zone);
    const reservedCenter = toCanvas([(reserved.zone[0] + reserved.zone[2]) / 2, (reserved.zone[1] + reserved.zone[3]) / 2]);
    context.fillStyle = "rgba(201,95,88,.13)";
    context.strokeStyle = "rgba(164,68,61,.55)";
    context.setLineDash([5, 4]);
    context.fill(reservedPath);
    context.stroke(reservedPath);
    context.setLineDash([]);
    context.fillStyle = "#8f4540";
    context.font = "11px Segoe UI";
    context.fillText(reserved.name, reservedCenter[0], reservedCenter[1]);
  }
  if (state.selected !== null) {
    const saved = state.design.layout.features[state.selected];
    const active = state.layoutDrag?.index === state.selected
      ? state.layoutDrag.feature
      : (state.draft?.kind === "nest" ? state.draft : saved);
    if (active?.kind === "nest" && isNestEditWorkspaceActive()) drawNestPhotoReference(context, active, toCanvas);
  }
  const invalid = new Set(state.preview.invalid_feature_indexes || []);
  layoutFeatures().forEach((feature, index) => {
    const zonePath = worldRect(feature.zone);
    const p1 = toCanvas([feature.zone[2], feature.zone[1]]);
    const zoneCenter = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, (feature.zone[1] + feature.zone[3]) / 2]);
    const color = invalid.has(index) ? COLORS.invalid : kindColor(feature.kind);
    context.strokeStyle = index === state.selected ? "#176e91" : shade(color, .72);
    context.lineWidth = index === state.selected ? 3 : 1.2;
    if (feature.kind === "nest" && feature.contour) {
      const editingPoint = state.layoutDrag?.index === index && state.layoutDrag?.mode === "point";
      context.fillStyle = color + "35";
      for (const points of nestOccurrenceOutlines(feature,
        editingPoint ? null : state.preview.nest_soft_contours?.[index],
        state.preview.nest_occurrences?.[index])) {
        const outline = drawClosedPath(context, points, toCanvas);
        context.fill(outline); context.stroke(outline);
      }
      // A not-yet-accepted scan-tuning retrace draws dashed over the
      // accepted (solid) outline - see spec section 35.
      if (isNestEditWorkspaceActive() && index === state.selected && state.nestCandidateContour?.length) {
        const candidateWorld = state.nestCandidateContour.map(point => nestLocalToWorld(feature, point));
        const candidatePath = drawClosedPath(context, candidateWorld, toCanvas);
        context.save();
        context.strokeStyle = "rgba(255,255,255,.95)";
        context.lineWidth = 8;
        context.stroke(candidatePath);
        context.setLineDash([6, 4]);
        context.strokeStyle = "#007ca8";
        context.lineWidth = 4;
        context.stroke(candidatePath);
        context.restore();
      }
      // Informational-only indicators for the resolved finger-access plan -
      // a scoop footprint on Recessed, a notch location on Raised Wall.
      drawNestAccessIndicators(context, state.preview?.nest_access?.[index], toCanvas);
    } else {
      // A fused cradle, post or divider fills less of its zone than the zone
      // itself, and the rest is floor a neighbour may use. Fill what the part
      // really covers and leave the zone as a faint outline around it, so the
      // difference between "mine" and "just my handle" is visible.
      const covered = footprintWorld(feature, index);
      const coveredPath = covered && worldRect(covered);
      const coveredCenter = covered && toCanvas([(covered[0] + covered[2]) / 2, (covered[1] + covered[3]) / 2]);
      context.fillStyle = feature.kind === "text" ? color + "25" : color + "cc";
      context.fill(coveredPath || zonePath);
      if (covered) {
        context.stroke(coveredPath);
        context.save();
        context.globalAlpha = .45;
        context.setLineDash([4, 3]);
      }
      context.stroke(zonePath);
      if (covered) context.restore();
      if (feature.kind === "pocket") {
        const wall = number(feature.options?.wall, 1.6);
        const innerPath = worldRect([feature.zone[0] + wall, feature.zone[1] + wall, feature.zone[2] - wall, feature.zone[3] - wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.4)";
        context.fill(innerPath);
        context.strokeStyle = shade(color, 0.5);
        context.lineWidth = 1;
        context.stroke(innerPath);
        context.restore();
      }
      if (feature.kind === "slot") {
        const wall = number(feature.options?.wall, 1.6);
        const along = feature.along || "x";
        const count = feature.count || 2;
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        if (along === "x") {
          const step = (z3 - z1 - 2 * wall) / Math.max(1, count);
          for (let s = 0; s < count; s++) {
            const y = z1 + wall + (s + 0.5) * step;
            const pt0 = toCanvas([z0 + wall, y]), pt1 = toCanvas([z2 - wall, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          const step = (z2 - z0 - 2 * wall) / Math.max(1, count);
          for (let s = 0; s < count; s++) {
            const x = z0 + wall + (s + 0.5) * step;
            const pt0 = toCanvas([x, z1 + wall]), pt1 = toCanvas([x, z3 - wall]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "steps") {
        const along = feature.along || "x";
        const count = feature.count || 3;
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        if (along === "x") {
          const step = (z3 - z1) / Math.max(1, count);
          for (let s = 1; s < count; s++) {
            const y = z1 + s * step;
            const pt0 = toCanvas([z0, y]), pt1 = toCanvas([z2, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          const step = (z2 - z0) / Math.max(1, count);
          for (let s = 1; s < count; s++) {
            const x = z0 + s * step;
            const pt0 = toCanvas([x, z1]), pt1 = toCanvas([x, z3]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "scoop") {
        const along = feature.along || "x";
        context.save();
        context.strokeStyle = shade(color, 0.4);
        context.lineWidth = 1;
        const [z0, z1, z2, z3] = feature.zone;
        const steps = [0.2, 0.45, 0.7, 0.9];
        if (along === "x") {
          for (const s of steps) {
            const y = z1 + (z3 - z1) * s;
            const pt0 = toCanvas([z0, y]), pt1 = toCanvas([z2, y]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        } else {
          for (const s of steps) {
            const x = z0 + (z2 - z0) * s;
            const pt0 = toCanvas([x, z1]), pt1 = toCanvas([x, z3]);
            context.beginPath(); context.moveTo(pt0[0], pt0[1]); context.lineTo(pt1[0], pt1[1]); context.stroke();
          }
        }
        context.restore();
      }
      if (feature.kind === "text") {
        const activeFeature = (index === state.selected && state.draft?.kind === "text") ? state.draft : feature;
        renderLayoutText(context, activeFeature, toCanvas, scale, false);
      } else if (feature.kind === "divider") {
        const activeFeature = (index === state.selected && state.draft?.kind === "divider") ? state.draft : feature;
        const opt = activeFeature.options || {};
        const slopeOn = opt.slope_base === true ||
          ["true", "1", "yes", "on"].includes(String(opt.slope_base).toLowerCase()) ||
          Number(opt.bottom_angle) !== 0;
        if (slopeOn) {
          const slopeZones = activeFeature.options?.compartment_spans?.length
            ? dividerCompartmentsClient(activeFeature).cells.map(cell => cell.zone)
            : [activeFeature.zone];
          for (const slopeZone of slopeZones) {
            context.save();
            context.clip(worldRect(slopeZone));
            context.strokeStyle = "#1f6b45";
            context.lineWidth = 1.8;
            context.globalAlpha = .78;
            const [sx0, sy0, sx1, sy1] = slopeZone;
            const span = Math.max(sx1 - sx0, sy1 - sy0);
            for (let mark = -span; mark <= span * 2; mark += 8) {
              const a = activeFeature.along === "y"
                ? toCanvas([sx0, sy0 + mark])
                : toCanvas([sx0 + mark, sy0]);
              const b = activeFeature.along === "y"
                ? toCanvas([sx1, sy1 + mark])
                : toCanvas([sx1 + mark, sy1]);
              context.beginPath(); context.moveTo(a[0], a[1]); context.lineTo(b[0], b[1]); context.stroke();
            }
            context.restore();
          }
        }
        if (opt.label_divisions && opt.division_labels) {
          renderDividerDivisionLabels(context, activeFeature, toCanvas, scale);
        } else {
          context.fillStyle = "rgba(20,36,42,.82)";
          context.font = "600 11px Segoe UI";
          context.textAlign = "center";
          context.textBaseline = "middle";
          const [tx, ty] = coveredCenter || zoneCenter;
          context.fillText(partInfo(feature.kind)?.title || feature.kind, tx, ty);
        }
      } else {
        context.fillStyle = "rgba(20,36,42,.82)";
        context.font = "600 11px Segoe UI";
        context.textAlign = "center";
        context.textBaseline = "middle";
        const [tx, ty] = coveredCenter || zoneCenter;
        context.fillText(partInfo(feature.kind)?.title || feature.kind, tx, ty);
      }
    }
    if (index === state.selected) {
      const resizable = Boolean(partInfo(feature.kind)?.flags?.size || feature.kind === "nest");
      if (resizable) {
        context.fillStyle = "#237fa6";
        context.strokeStyle = "white";
        context.lineWidth = 1;
        context.fillRect(p1[0] - 6, p1[1] - 6, 12, 12);
        context.strokeRect(p1[0] - 6, p1[1] - 6, 12, 12);
      }
      if (feature.kind === "nest" && feature.contour) {
        const top = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, feature.zone[3]]);
        const rotate = toCanvas([(feature.zone[0] + feature.zone[2]) / 2, feature.zone[3] + 8]);
        context.strokeStyle = "#237fa6";
        context.beginPath(); context.moveTo(top[0], top[1]); context.lineTo(rotate[0], rotate[1]); context.stroke();
        context.fillStyle = "#237fa6";
        context.beginPath(); context.arc(rotate[0], rotate[1], 6, 0, Math.PI * 2); context.fill();
        context.strokeStyle = "white"; context.stroke();
        if (isNestEditWorkspaceActive()) drawNestContourHandles(context, feature, toCanvas);
      }
    }
  });
  if (state.draft) {
    const draftHasError = Boolean(state.preview.draft_error);
    const draftColor = draftHasError ? COLORS.invalid : DRAFT_HIGHLIGHT;
    const zone = state.draft.zone;
    const zonePath = worldRect(zone);
    context.fillStyle = draftColor;
    context.strokeStyle = draftColor;
    context.lineWidth = 2;
    context.setLineDash([6, 3]);
    if (state.draft.kind === "nest" && state.draft.contour) {
      const liveDraft = state.layoutDrag?.feature || state.draft;
      const softContour = state.layoutDrag?.mode === "point" ? null : state.preview.draft_soft_contour;
      context.fillStyle = draftColor + "18";
      context.strokeStyle = draftColor;
      for (const points of nestOccurrenceOutlines(liveDraft, softContour,
        state.preview.draft_nest_occurrences)) {
        const outline = drawClosedPath(context, points, toCanvas);
        context.fill(outline); context.stroke(outline);
      }
    } else if (state.draft.kind !== "nest") {
      // Same as a placed support: fill the floor it really covers, outline the
      // zone it lives in.
      const covered = state.preview.draft_footprint;
      if (covered) {
        const coveredPath = worldRect(covered);
        context.fill(coveredPath);
        context.stroke(coveredPath);
      } else {
        context.fill(zonePath);
      }
      context.stroke(zonePath);
      if (state.draft.kind === "pocket") {
        const wall = number(state.draft.options?.wall, state.draftResolvedOptions?.wall ?? 1.6);
        const innerPath = worldRect([zone[0] + wall, zone[1] + wall, zone[2] - wall, zone[3] - wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.35)";
        context.fill(innerPath);
        context.strokeStyle = draftColor;
        context.lineWidth = 1;
        context.stroke(innerPath);
        context.restore();
      }
      if (state.draft.kind === "text" && state.selected === null) {
        renderLayoutText(context, state.draft, toCanvas, scale, true);
      }
    }
    context.setLineDash([]);
  }
  layoutFeatures().forEach((feature, index) => {
    if (feature.kind !== "divider") return;
    const activeFeature = index === state.selected && state.draft?.kind === "divider"
      ? state.draft : feature;
    renderDividerSegments(context, activeFeature, index, toCanvas);
  });
  const offsetOutside = (start, end) => {
    const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
    const length = Math.max(1, Math.hypot(middle[0] - width / 2, middle[1] - height / 2));
    const dx = (middle[0] - width / 2) * 18 / length;
    const dy = (middle[1] - height / 2) * 18 / length;
    return [[start[0] + dx, start[1] + dy], [end[0] + dx, end[1] + dy]];
  };
  const widthLine = offsetOutside(toCanvas([bounds[0], bounds[3]]), toCanvas([bounds[2], bounds[3]]));
  const depthLine = offsetOutside(toCanvas([bounds[0], bounds[1]]), toCanvas([bounds[0], bounds[3]]));
  const displayBox = dimensionDragBoxOverride(state.design.box, "2d");
  drawDimensionGhost2D(context, toCanvas, bounds);
  drawDimensionLine(context, ...widthLine, `Width ${fmt(displayBox.x)} mm`, false, { axis: "x", value: displayBox.x });
  drawDimensionLine(context, ...depthLine, `Depth ${fmt(displayBox.y)} mm`, false, { axis: "y", value: displayBox.y });

  const binBottom = Math.max(...[
    toCanvas([bounds[0], bounds[1]])[1], toCanvas([bounds[2], bounds[1]])[1],
    toCanvas([bounds[2], bounds[3]])[1], toCanvas([bounds[0], bounds[3]])[1],
  ]);
  const hintY = Math.min(height - 15, Math.max(binBottom + 24, height - 24));
  context.save();
  context.textAlign = "center";
  context.textBaseline = "middle";
  if (state.nudgeFeedback) {
    const text = `Moved ${state.nudgeFeedback.amount}  (Arrow: 1 mm · Shift: 10 mm · Ctrl: 0.1 mm)`;
    context.font = "600 11px Segoe UI, sans-serif";
    const tw = context.measureText(text).width;
    context.fillStyle = "rgba(248, 250, 249, 0.94)";
    context.fillRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.strokeStyle = "#237fa6";
    context.lineWidth = 1;
    context.strokeRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.fillStyle = "#176e91";
    context.fillText(text, width / 2, hintY);
  } else {
    const text = "Use Arrow keys or drag to move";
    context.font = "11px Segoe UI, sans-serif";
    const tw = context.measureText(text).width;
    context.fillStyle = "rgba(248, 250, 249, 0.88)";
    context.fillRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.strokeStyle = "rgba(94, 127, 136, 0.35)";
    context.lineWidth = 1;
    context.strokeRect(width / 2 - tw / 2 - 8, hintY - 10, tw + 16, 20);
    context.fillStyle = "#5e7f88";
    context.fillText(text, width / 2, hintY);
  }
  context.restore();
  updateNudgeUI();
}

function layoutPoint(event) {
  const rect = $("#preview-2d").getBoundingClientRect();
  return state.layoutTransform.toWorld([event.clientX - rect.left, event.clientY - rect.top]);
}

function hitFeature(world) {
  const features = state.design.layout.features;
  // Prioritize the currently selected feature using its live draft zone (with generous padding for text)
  if (state.selected !== null && state.selected < features.length) {
    const selIndex = state.selected;
    const feat = (state.draft && state.draft.kind === features[selIndex].kind) ? state.draft : features[selIndex];
    const zone = feat.zone;
    if (feat.kind === "nest" && feat.contour) {
      if (isNestEditWorkspaceActive() && hitNestContourPoint(feat, world) !== null) return selIndex;
      if (state.layoutTransform) {
        const cx = (zone[0] + zone[2]) / 2;
        const handles = [[zone[2], zone[1]], [cx, zone[3] + 8]];
        if (handles.some(point => Math.hypot(
          (world[0] - point[0]) * state.layoutTransform.scale,
          (world[1] - point[1]) * state.layoutTransform.scale,
        ) < 14)) return selIndex;
      }
      if (nestOccurrenceOutlines(feat, state.preview?.nest_soft_contours?.[selIndex],
          state.preview?.nest_occurrences?.[selIndex]).some(outline => pointInPolygon(world, outline))) return selIndex;
    } else {
      const pad = feat.kind === "text" ? 3.0 : 0;
      if (world[0] >= zone[0] - pad && world[0] <= zone[2] + pad &&
          world[1] >= zone[1] - pad && world[1] <= zone[3] + pad) {
        return selIndex;
      }
    }
  }

  for (let index = features.length - 1; index >= 0; index--) {
    if (index === state.selected) continue;
    const feat = features[index];
    const zone = feat.zone;
    if (feat.kind === "nest" && feat.contour) {
      if (nestOccurrenceOutlines(feat, state.preview?.nest_soft_contours?.[index],
          state.preview?.nest_occurrences?.[index]).some(outline => pointInPolygon(world, outline))) return index;
      continue;
    }
    const pad = feat.kind === "text" ? 3.0 : 0;
    if (world[0] >= zone[0] - pad && world[0] <= zone[2] + pad &&
        world[1] >= zone[1] - pad && world[1] <= zone[3] + pad) {
      return index;
    }
  }
  return null;
}

function dividerLabelsClient(feature) {
  let labels = feature.options?.division_labels;
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { labels = labels.split(","); }
  }
  return Array.isArray(labels) ? [...labels] : [];
}

function promoteMergedDividerLabel(feature, merged, columns) {
  const labels = dividerLabelsClient(feature);
  const anchor = merged.row * columns + merged.column;
  if (String(labels[anchor] || "").trim()) return;
  const values = new Set();
  for (let row = merged.row; row < merged.row + merged.rowSpan; row++) {
    for (let column = merged.column; column < merged.column + merged.columnSpan; column++) {
      const text = String(labels[row * columns + column] || "").trim();
      if (text) values.add(text);
    }
  }
  if (values.size === 1) {
    labels[anchor] = [...values][0];
    feature.options.division_labels = labels;
  }
}

async function editDividerSegment(originalHit) {
  if (dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  if (state.dividerTopologyBusy) return;
  state.dividerTopologyBusy = true;
  try {
    if (state.selected !== originalHit.featureIndex) {
      await selectedFeature(originalHit.featureIndex);
    }
    if (state.selected !== originalHit.featureIndex || state.draft?.kind !== "divider") return;
    const topology = dividerCompartmentsClient(state.draft);
    const currentHit = dividerBoundarySegmentsClient(
      state.draft, originalHit.featureIndex, point => point,
    ).find(hit => hit.orientation === originalHit.orientation &&
      hit.line === originalHit.line && hit.segment === originalHit.segment);
    if (!currentHit) return;
    if (currentHit.action === "blocked") {
      state.dividerSegmentHover = originalHit;
      updateNudgeUI();
      toast("That merge would make an irregular compartment. Compartments must stay rectangular.");
      return;
    }

    let cells;
    if (currentHit.action === "merge") {
      cells = topology.cells.filter(cell =>
        !sameDividerCompartmentClient(cell, currentHit.a) &&
        !sameDividerCompartmentClient(cell, currentHit.b));
      cells.push(currentHit.merged);
      promoteMergedDividerLabel(state.draft, currentHit.merged, topology.columns);
    } else {
      const owner = currentHit.a;
      cells = topology.cells.filter(cell => !sameDividerCompartmentClient(cell, owner));
      if (currentHit.orientation === "vertical") {
        const leftWidth = currentHit.line - owner.column;
        cells.push(
          { row: owner.row, column: owner.column, rowSpan: owner.rowSpan, columnSpan: leftWidth },
          { row: owner.row, column: currentHit.line, rowSpan: owner.rowSpan, columnSpan: owner.columnSpan - leftWidth },
        );
      } else {
        const lowHeight = currentHit.line - owner.row;
        cells.push(
          { row: owner.row, column: owner.column, rowSpan: lowHeight, columnSpan: owner.columnSpan },
          { row: currentHit.line, column: owner.column, rowSpan: owner.rowSpan - lowHeight, columnSpan: owner.columnSpan },
        );
      }
    }

    refreshDraftSoon.cancel();
    state.draft.options ||= {};
    state.draft.options.compartment_spans = serializeDividerSpansClient(cells);
    state.draftAutoCommit = true;
    state.dividerSegmentHover = null;
    markDraftChanged();
    renderDraftFields();
    renderLayout2D();
    await refreshDraft();
  } finally {
    state.dividerTopologyBusy = false;
  }
}

function wireLayoutInteraction() {
  const canvas = $("#preview-2d");
  // Tracks whether the pointer is still down after an awaited "keep this part?"
  // prompt - if the user lifted their finger to answer it, there's no drag.
  let pointerActive = false;
  canvas.addEventListener("pointercancel", () => {
    pointerActive = false;
    if (state.dimensionDrag?.view === "2d") {
      cancelDimensionDrag(canvas);
      renderLayout2D();
    }
  });
  canvas.addEventListener("pointerdown", async event => {
    if (!state.layoutTransform || state.designMutationBusy || state.dividerTopologyBusy) return;
    // A dimension label always wins over ordinary feature selection/move/
    // resize - hit-test it first (see fix3d.md, item 5).
    const handle = hitDimensionHandle("2d", canvasPointFromEvent(canvas, event));
    if (handle) {
      beginDimensionDrag("2d", handle, canvas, event);
      renderLayout2D();
      return;
    }
    const dividerHit = hitDividerSegment(canvasPointFromEvent(canvas, event));
    if (dividerHit) {
      pointerActive = false;
      state.layoutDrag = null;
      await editDividerSegment(dividerHit);
      return;
    }
    pointerActive = true;
    const world = layoutPoint(event);
    let index = hitFeature(world);
    // In the dedicated outline editor, a click that misses the outline/photo
    // pans the view instead of deselecting - there is nothing else on this
    // canvas to click, so a miss is never "click away to close".
    if (index === null && isNestEditWorkspaceActive()) {
      pointerActive = false;
      state.layoutDrag = {
        mode: "pan",
        startCanvas: canvasPointFromEvent(canvas, event),
        startPanX: state.nestViewPanX,
        startPanY: state.nestViewPanY,
      };
      try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
      return;
    }
    if (index === null) {
      if (state.selected !== null) {
        if (!(await guardDraftSwitch())) return;
        resetNestPhotoSession();
        state.selected = null;
        state.draft = null;
        state.draftKind = null;
        $(".support-editor").hidden = true;
      }
      state.layoutDrag = null;
      state.nudgeFeedback = null;
      updateNudgeUI();
      renderPlaced(); updateSelectionButtons(); renderLayout2D();
      return;
    }
    if (index !== state.selected) {
      // May put up the "keep this part?" dialog before the selection moves.
      await selectedFeature(index);
      if (state.selected !== index) return;   // user chose to keep editing
      if (!pointerActive) return;             // finger already lifted for the dialog
    } else {
      cancelPendingDraftWork();
    }
    // A field edit may still exist only in the live draft. Start the drag from
    // exactly what is on screen, not the last server-saved copy, or moving the
    // same part immediately after typing can silently restore its old values.
    const feature = clone(
      state.selected === index && state.draft
        ? state.draft
        : state.design.layout.features[index]
    );
    if (feature.kind === "divider" && dividerLockedByLidLabels()) {
      pointerActive = false;
      toast(dividerLockMessage(), true, 6500);
      return;
    }
    // Moving or resizing lettering by hand is a placement decision, so it
    // stops placing itself - otherwise the next preview would put it straight
    // back where the engine wanted it and the drag would look broken.
    if (feature.kind === "text" && feature.options?.auto) {
      feature.options.auto = false;
      const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
      if (autoField) autoField.checked = false;
    }
    if (feature.kind === "nest" && feature.contour && isNestEditWorkspaceActive()
        && (state.nestOutlineTool === "add-point" || state.nestOutlineTool === "delete-point")) {
      pointerActive = false;
      if (state.nestOutlineTool === "add-point") {
        const hit = hitNestContourSegment(feature, world);
        if (hit) {
          const contour = feature.contour.map(point => [...point]);
          contour.splice(hit.index + 1, 0, hit.local);
          await commitNestContourEdit(index, contour);
        }
      } else {
        const pointIndex = hitNestContourPoint(feature, world);
        if (pointIndex !== null && feature.contour.length > 3) {
          const contour = feature.contour.filter((_point, i) => i !== pointIndex);
          await commitNestContourEdit(index, contour);
        } else if (pointIndex !== null) {
          toast("A Photo Nest outline needs at least three points.", true);
        }
      }
      return;
    }
    // The dedicated outline editor never moves, rotates or resizes the part
    // itself - Select/Edit only drags an actual contour point; anything else,
    // including a click inside the filled outline, pans the viewport instead.
    if (isNestEditWorkspaceActive()) {
      const contourPoint = hitNestContourPoint(feature, world);
      if (contourPoint === null) {
        pointerActive = false;
        state.layoutDrag = {
          mode: "pan",
          startCanvas: canvasPointFromEvent(canvas, event),
          startPanX: state.nestViewPanX,
          startPanY: state.nestViewPanY,
        };
        try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
        return;
      }
      state.layoutDrag = {
        index, feature, original: clone(feature),
        mode: "point",
        contourPoint,
        photoBounds: state.nestPhoto?.bounds ? [...state.nestPhoto.bounds] : null,
        start: world,
        centre: [(feature.zone[0] + feature.zone[2]) / 2, (feature.zone[1] + feature.zone[3]) / 2],
        startAngle: 0,
        startRadius: 1,
      };
      try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
      return;
    }
    const zone = feature.zone;
    const handlePixels = Math.hypot((world[0] - zone[2]) * state.layoutTransform.scale, (world[1] - zone[1]) * state.layoutTransform.scale);
    const rotatePoint = [(zone[0] + zone[2]) / 2, zone[3] + 8];
    const rotatePixels = Math.hypot((world[0] - rotatePoint[0]) * state.layoutTransform.scale, (world[1] - rotatePoint[1]) * state.layoutTransform.scale);
    const centre = [(zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2];
    const resizable = Boolean(partInfo(feature.kind)?.flags?.size || feature.kind === "nest");
    const contourPoint = feature.kind === "nest" && isNestEditWorkspaceActive()
      ? hitNestContourPoint(feature, world) : null;
    state.layoutDrag = {
      index, feature, original: clone(feature),
      mode: contourPoint !== null ? "point"
        : feature.kind === "nest" && rotatePixels < 14 ? "rotate"
          : (resizable && handlePixels < 14) ? "resize" : "move",
      contourPoint,
      photoBounds: state.nestPhoto?.bounds ? [...state.nestPhoto.bounds] : null,
      start: world,
      centre,
      startAngle: Math.atan2(world[1] - centre[1], world[0] - centre[0]),
      startRadius: Math.max(.01, Math.hypot(world[0] - centre[0], world[1] - centre[1])),
    };
    try { canvas.setPointerCapture(event.pointerId); } catch (_error) {}
  });
  canvas.addEventListener("pointermove", event => {
    if (state.dimensionDrag?.view === "2d") {
      updateDimensionDrag(event.clientX, event.clientY);
      renderLayout2D();
      return;
    }
    if (!state.layoutDrag) {
      const handle = state.layoutTransform ? hitDimensionHandle("2d", canvasPointFromEvent(canvas, event)) : null;
      if (handle) {
        state.dividerSegmentHover = null;
        if (updateDimensionHover("2d", handle, canvas)) renderLayout2D();
        return;
      }
      updateDimensionHover("2d", null, canvas);
      const dividerHit = hitDividerSegment(canvasPointFromEvent(canvas, event));
      if (!sameDividerHit(dividerHit, state.dividerSegmentHover)) {
        state.dividerSegmentHover = dividerHit;
        canvas.style.cursor = dividerHit?.action === "blocked" ? "not-allowed" : dividerHit ? "pointer" : "";
        renderLayout2D();
      }
      return;
    }
    const drag = state.layoutDrag;
    if (!drag || !state.layoutTransform) return;
    if (drag.mode === "pan") {
      const point = canvasPointFromEvent(canvas, event);
      state.nestViewPanX = drag.startPanX + (point[0] - drag.startCanvas[0]);
      state.nestViewPanY = drag.startPanY + (point[1] - drag.startCanvas[1]);
      renderLayout2D();
      return;
    }
    const world = layoutPoint(event);
    const pitch = state.design.layout.mode === "cartridge" ? 8 : 1;
    const snap = value => Math.round(value / pitch) * pitch;
    const original = drag.original.zone;
    if (drag.mode === "point") {
      drag.feature.contour[drag.contourPoint] = nestWorldToLocal(drag.feature, world);
      normalizeNestContour(drag.feature);
    } else if (drag.mode === "move") {
      const width = original[2] - original[0], depth = original[3] - original[1];
      const cx = snap(drag.centre[0] + world[0] - drag.start[0]);
      const cy = snap(drag.centre[1] + world[1] - drag.start[1]);
      drag.feature.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
    } else if (drag.feature.kind === "nest" && drag.mode === "rotate") {
      const angle = Math.atan2(world[1] - drag.centre[1], world[0] - drag.centre[0]);
      const raw = number(drag.original.rotation) + (angle - drag.startAngle) * 180 / Math.PI;
      drag.feature.rotation = ((Math.round(raw / 90) * 90) % 360 + 360) % 360;
    } else if (drag.feature.kind === "nest") {
      const radius = Math.hypot(world[0] - drag.centre[0], world[1] - drag.centre[1]);
      drag.feature.scale = Math.max(.1, number(drag.original.scale, 1) * radius / drag.startRadius);
    } else {
      const width = Math.max(pitch, snap(2 * Math.abs(world[0] - drag.centre[0])));
      const depth = Math.max(pitch, snap(2 * Math.abs(world[1] - drag.centre[1])));
      drag.feature.zone = [drag.centre[0] - width / 2, drag.centre[1] - depth / 2, drag.centre[0] + width / 2, drag.centre[1] + depth / 2];
    }
    renderLayout2D();
  });
  canvas.addEventListener("pointerleave", () => {
    if (state.layoutDrag || state.dimensionDrag?.view === "2d") return;
    if (state.dividerSegmentHover) {
      state.dividerSegmentHover = null;
      canvas.style.cursor = "";
      renderLayout2D();
    }
  });
  canvas.addEventListener("pointerup", async event => {
    pointerActive = false;
    if (state.dimensionDrag?.view === "2d") {
      commitDimensionDrag(canvas);
      renderLayout2D();
      return;
    }
    const drag = state.layoutDrag;
    if (!drag) return;
    state.layoutDrag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (typeof drag.index !== "number") return;   // not a feature drag - nothing to apply
    state.draft = drag.feature;
    if (drag.mode === "move" && drag.feature.kind === "nest" && drag.feature.options?.auto_size === true
        && state.design.layout.features.filter(one => one.kind === "nest").length === 1) {
      const zone = drag.feature.zone;
      const cx = (zone[0] + zone[2]) / 2, cy = (zone[1] + zone[3]) / 2;
      if (Math.abs(cx) > 0.5 || Math.abs(cy) > 0.5) {
        drag.feature.options.auto_size = false;
        toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
      }
    }
    if (drag.mode === "resize" && drag.feature.kind !== "nest") {
      // Resizing by the blue corner is just as intentional as typing Width or
      // Length. Preserve both axes from later contents-driven auto fitting.
      pinDraftAxis("width");
      pinDraftAxis("depth");
      state.partZoneLocks[drag.index] = state.pinnedZone;
    }
    const applied = await applySupport(drag.index);
    if (!applied) {
      if (drag.photoBounds && state.nestPhoto) state.nestPhoto.bounds = drag.photoBounds;
      state.draft = clone(state.design.layout.features[drag.index]);
      renderDraftFields();
      refreshDraft();
      renderLayout2D();
    }
  });
  window.addEventListener("keydown", handleLayoutArrowKeys);
}

function handleLayoutArrowKeys(event) {
  const arrowKeys = ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
  if (!arrowKeys.includes(event.key)) return;

  const is2D = $(".canvas-wrap[data-canvas='2d']")?.classList.contains("active");
  if (!is2D) return;

  const inField = Boolean(
    event.target.closest("input, textarea, select, [contenteditable='true'], .view-tab") ||
    document.activeElement?.closest("input, textarea, select, [contenteditable='true'], .view-tab")
  );
  if (inField) return;

  if (document.querySelector("dialog[open], .modal.active")) return;
  if (state.selected === null || !state.design?.layout?.features?.[state.selected]) return;

  event.preventDefault();

  let step = 1;
  let mod = "normal";
  if (event.ctrlKey || event.metaKey) {
    step = 0.1;
    mod = "ctrl";
  } else if (event.shiftKey) {
    step = 10;
    mod = "shift";
  }

  let dx = 0, dy = 0;
  if (event.key === "ArrowLeft") dx = -step;
  else if (event.key === "ArrowRight") dx = step;
  else if (event.key === "ArrowUp") dy = step;
  else if (event.key === "ArrowDown") dy = -step;

  if (!state.draft) {
    state.draft = clone(state.design.layout.features[state.selected]);
    state.draftAutoCommit = true;
  }
  const feature = state.draft;
  if (feature.kind === "divider" && dividerLockedByLidLabels()) {
    toast(dividerLockMessage(), true, 6500);
    return;
  }
  if (!pendingNudgeHistory) {
    pendingNudgeHistory = clone(state.design);
    pendingNudgeDraft = clone(state.draft);
  }
  const request = ++state.draftRequest;
  const z = feature.zone;
  const roundCoord = val => Math.round(val * 1000) / 1000;
  feature.zone = [
    roundCoord(z[0] + dx),
    roundCoord(z[1] + dy),
    roundCoord(z[2] + dx),
    roundCoord(z[3] + dy),
  ];

  if (feature.kind === "text" && feature.options?.auto) {
    feature.options.auto = false;
    const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
    if (autoField) autoField.checked = false;
  }
  if (feature.kind === "nest") {
    if (feature.options?.auto_size === true
        && state.design.layout.features.filter(one => one.kind === "nest").length === 1) {
      const cx = (feature.zone[0] + feature.zone[2]) / 2, cy = (feature.zone[1] + feature.zone[3]) / 2;
      if (Math.abs(cx) > 0.5 || Math.abs(cy) > 0.5) {
        feature.options.auto_size = false;
        toast("Automatic footprint sizing turned off because the bin size or layout was manually changed.");
      }
    }
  }

  state.nudgeFeedback = {
    amount: `${step} mm`,
    mod,
  };
  updateNudgeUI();
  renderLayout2D();

  commitNudge(request);
}

async function saveDesign() {
  if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave())) return;
  if (!beginDesignMutation()) return;
  try {
    // The editor saves valid part edits after a short typing pause. Commit the
    // visible draft explicitly so an immediate Save cannot download the older
    // server copy while the new value is still waiting in that pause.
    await commitVisibleDraft();
    updateDesignFromForm();
    const body = JSON.stringify(state.design, null, 2) + "\n";
    const blob = new Blob([body], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${(state.design.part_name || "Wavefinity design").replace(/[^a-z0-9 _-]/gi, "").trim() || "Wavefinity design"}.wavefinity.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    state.cleanDesign = clone(state.design);
    toast("Design downloaded.");
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    finishDesignMutation();
  }
}

// The design as the form currently shows it, without touching state.design.
function visibleDesignSnapshot() {
  const visibleDesign = clone(state.design);
  visibleDesign.box.x = normalizeBinDimension("x", $("#x-size").value, visibleDesign.box.x);
  visibleDesign.box.y = normalizeBinDimension("y", $("#y-size").value, visibleDesign.box.y);
  visibleDesign.box.z = number($("#z").value, visibleDesign.box.z);
  if (isSurfaceBinDesign(visibleDesign)) resolveSurfaceBase(visibleDesign, { fromForm: true });
  const defaultBase = number(state.catalog?.base_rules?.default_mm, 0.6);
  if (!isSurfaceBinDesign(visibleDesign)) {
    visibleDesign.box.standard_base = $("#base-thickness").value === "standard";
    visibleDesign.box.base_thickness = visibleDesign.box.standard_base
      ? defaultBase
      : number($("#base-thickness").value, visibleDesign.box.base_thickness ?? defaultBase);
  }
  const wallRules = state.catalog?.wall_rules || {};
  const defaultWall = wallRules.default_mm ?? 0.8;
  visibleDesign.box.standard_walls = $("#wall-thickness").value === "standard";
  visibleDesign.box.wall = visibleDesign.box.standard_walls
    ? defaultWall
    : Math.max(wallRules.min_mm ?? 0.2, Math.min(
        wallRules.max_mm ?? 2.4,
        number($("#wall-thickness").value, visibleDesign.box.wall ?? defaultWall),
      ));
  visibleDesign.part_name = $("#part-name").value;
  readStackForm(visibleDesign);
  normalizeStackSettings(visibleDesign);
  if (isSurfaceBinDesign(visibleDesign) && surfaceStackingBlocked(visibleDesign))
    visibleDesign.layout.surface_lightweight_base = false;
  const scoopEl = $("#scoop");
  if (scoopEl) visibleDesign.scoop = scoopEl.checked;
  readLiftGrabberForm(visibleDesign);
  if (editingEdgeMount()) readEdgeMountForm(visibleDesign);
  readSideOpeningForm(visibleDesign);
  return visibleDesign;
}

function designHasChanges() {
  const visibleDesign = visibleDesignSnapshot();
  const index = draftCommitIndex();
  if (state.draft && state.draftAutoCommit && (
    index === null ||
    (Number.isInteger(index) &&
      JSON.stringify(state.draft) !== JSON.stringify(state.design.layout.features[index]))
  )) return true;
  return JSON.stringify(visibleDesign) !== JSON.stringify(state.cleanDesign);
}

async function openDesign(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  if (typedSpaceOrdinaryBin() && !(await flushSpaceDesignAutosave())) {
    event.target.value = "";
    return;
  }
  if (designHasChanges() && !(await appConfirmAction({
    title: "Open a different design?",
    message: "Open this design and replace the current one? Unsaved changes to the current design will be lost.",
    actionLabel: "Open Design",
  }))) {
    event.target.value = "";
    return;
  }
  if (!beginDesignMutation()) return;
  try {
    const parsed = JSON.parse(await file.text());
    const result = await api("/api/design/validate", { design: parsed });
    if (isStructuralDesign(result.design)) {
      throw new Error("A Storage Box or Base Trim is saved from its Space, not opened in the Designer.");
    }
    state.design = result.design;
    resetNestPhotoSession();
    state.cleanDesign = clone(state.design);
    state.spaceStarterPreviewPending = false;
    if (state.folderMode === "space") state.designInventoryId = null;
    state.drafts = {};
    state.history = [];
    state.future = [];
    state.binResizePending = false;
    state.binFootprintResizePending = false;
    bindLidMemoryForDesign();
    syncForm();
    clearDraftSelection();
    await refreshPreview();
    if (typedSpaceOrdinaryBin()) await persistSpaceDesignSource(null, true);
    toast(`Opened ${file.name}.`);
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    event.target.value = "";
    finishDesignMutation();
  }
}

async function newDesign() {
  if (typedSpaceOrdinaryBin()) return designerNewBin();
  if (designHasChanges() && !(await appConfirmAction({
    title: "Start a new design?",
    message: "Start a new design and discard the current changes?",
    actionLabel: "Discard Changes",
    danger: true,
  }))) return;
  if (!beginDesignMutation()) return;
  const previousDesign = clone(state.design);
  state.design = freshDesignForCurrentFolder();
  state.surfaceHeightPromptSkipped = false;
  resetNestPhotoSession();
  state.cleanDesign = clone(state.design);
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  recordHistory(previousDesign);
  state.drafts = {};
  bindLidMemoryForDesign();
  syncForm();
  try {
    clearDraftSelection();
    await refreshPreview();
  } finally {
    finishDesignMutation();
  }
}

let isGenerating = false;

function wireGenerationDialog() {
  const dialog = $("#generation-dialog");
  const closeBtn = $("#generation-dialog-close");
  if (!dialog) return;
  dialog.addEventListener("cancel", (event) => {
    if (isGenerating) {
      event.preventDefault();
    }
  });
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      dialog.close();
    });
  }
}

function getIndicatorHtml(status) {
  if (status === "generating") {
    return `<span class="gen-spinner" aria-label="Saving"></span>`;
  }
  if (status === "done") {
    return `<span class="gen-status-icon done" aria-label="Done">✓</span>`;
  }
  if (status === "error") {
    return `<span class="gen-status-icon error" aria-label="Failed">✕</span>`;
  }
  return `<span class="gen-status-icon waiting" aria-label="Waiting">⋯</span>`;
}

function renderGenerationItems(items) {
  const container = $("#generation-items");
  if (!container) return;
  container.innerHTML = items.map(item => `
    <div class="generation-item status-${item.status}" id="gen-item-${item.id}">
      <div class="gen-item-indicator">
        ${getIndicatorHtml(item.status)}
      </div>
      <div class="gen-item-details">
        <strong class="gen-item-title">${escapeHtml(item.title)}</strong>
        <span class="gen-item-status">${escapeHtml(item.text)}</span>
      </div>
    </div>
  `).join("");
}

function setItemStatus(id, status, text) {
  const row = $(`#gen-item-${id}`);
  if (!row) return;
  row.className = `generation-item status-${status}`;
  const indicator = row.querySelector(".gen-item-indicator");
  if (indicator) indicator.innerHTML = getIndicatorHtml(status);
  const statusSpan = row.querySelector(".gen-item-status");
  if (statusSpan) statusSpan.textContent = text;
}

function showBinNameRequiredDialog(title, message) {
  const dialog = $("#bin-name-dialog");
  const partInput = $("#part-name");
  const titleEl = $("#bin-name-dialog-title");
  const messageEl = $("#bin-name-dialog-message");
  if (titleEl) titleEl.textContent = title || "Bins must have a name";
  if (messageEl) messageEl.textContent = message || "Bins must have a name before you can save or print.";
  if (!dialog || typeof dialog.showModal !== "function") {
    alert(message || "Bins must have a name");
    if (partInput) {
      partInput.focus();
      partInput.select();
    }
    return;
  }
  const onDone = () => {
    if (partInput) {
      partInput.focus();
      partInput.select();
    }
  };
  dialog.addEventListener("close", onDone, { once: true });
  if (!dialog.open) {
    dialog.showModal();
    $("#bin-name-dialog-ok")?.focus();
  }
}

function showFilenameConflictDialog(names) {
  const list = names.join(", ");
  showBinNameRequiredDialog(
    "This name is already used",
    `A file named "${list}" already exists in your chosen folder. Please label the bin with a different name, then save again.`
  );
}

function checkPartNamePresent(target = "bin") {
  if (target === "connector") return true;
  const val = ($("#part-name")?.value || "").trim();
  if (!val) {
    showBinNameRequiredDialog();
    return false;
  }
  return true;
}

async function generateParts(target) {
  if (state.designMutationBusy || isGenerating) {
    toast("Finish the current action before saving files.", true);
    return;
  }
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  if (state.runtime.hosted && !state.browserFolder) {
    toast("Choose a folder before saving files.", true);
    return;
  }
  const beforeForm = pendingDesignHistory || clone(state.design);
  const previousCanGenerate = state.canGenerate;

  cancelChangedDesignDebounce();
  pendingDesignHistory = null;

  if (!applyLiveFormWithModifierConflictGuard(beforeForm, previousCanGenerate)) {
    return;
  }
  recordHistory(beforeForm);

  if ((target === "all" || target === "bin") && !state.canGenerate) {
    toast("Resolve the highlighted issue before saving.", true);
    return;
  }
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ materialize: target === "all" || target === "bin" }))) return;
  const designRowId = typedSpaceOrdinaryBin() ? state.designInventoryId : null;
  const designSpaceContext = designRowId ? DL.spaceContext() : null;
  setError();

  const dialog = $("#generation-dialog");
  const dialogTitle = $("#generation-dialog-title");
  const dialogSubtitle = $("#generation-dialog-subtitle");
  const dialogError = $("#generation-error");
  const dialogActions = $("#generation-actions");

  if (dialogTitle) dialogTitle.textContent = "Saving Parts…";
  if (dialogSubtitle) dialogSubtitle.textContent = "Please wait while your files are being saved.";
  if (dialogError) {
    dialogError.hidden = true;
    dialogError.textContent = "";
  }
  if (dialogActions) {
    dialogActions.hidden = true;
  }

  const boxTitle = `Bin (${fmt(state.design.box.x)} × ${fmt(state.design.box.y)} × ${fmt(state.design.box.z)} mm)`;
  const connTitle = state.connector.different_heights
    ? "Side Connector"
    : "Connectors (Side + 3-Way + 4-Way)";

  const items = [];
  if (target === "all" || target === "bin") {
    items.push({ id: "bin", title: boxTitle, status: "waiting", text: "Waiting…" });
  }
  if (target === "all" || target === "connector") {
    items.push({ id: "connector", title: connTitle, status: "waiting", text: "Waiting…" });
  }

  renderGenerationItems(items);

  isGenerating = true;
  state.designMutationBusy = true;
  setMutationSurfacesInert(true);
  updateGenerateAvailability();
  updateHistoryButtons();

  if (dialog && typeof dialog.showModal === "function") {
    try {
      if (!dialog.open) dialog.showModal();
    } catch (_err) {
      // Ignore if already open
    }
  }

  const allFiles = [];
  let connectorPlan = null;
  let saveOutput = state.output;
  let checkpointSaveFailed = null;
  // Stage truth: once the bin is really saved, a later connector failure must
  // say so instead of presenting the whole action as failed.
  let saveStage = "setup";
  let binSaved = false;

  try {
    // A debounced support edit may still be visible only in the draft. Save
    // it now so the exported files always match the canvas.
    await commitVisibleDraft();

    const payload = {
      design: clone(state.design),
      output: state.output,
      connector: state.connector,
      keep_log: designRowId ? false : state.keepLog,
    };

    // Fix 032 Correction 1: flush the exact pre-operation resume checkpoint
    // before this design is sent anywhere. Pending is computed for this
    // exact payload now, not blindly forced true - a reprint of an already-
    // reconciled unchanged design stays reconciled. If this checkpoint
    // cannot be durably saved, the "recoverable on failure" guarantee is not
    // met - stop here rather than proceed as though it were.
    if (state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        throw new Error(`The current design could not be saved to this Space, so nothing was saved: ${error.message}`);
      }
    }

    // Step 1: Generate Bin if requested
    if (target === "all" || target === "bin") {
      saveStage = "bin";
      setItemStatus("bin", "generating", "Saving…");
      const binResult = await api("/api/generate", payload);
      if (designSpaceContext) DL.requireSpaceContext(designSpaceContext);
      saveOutput = binResult.output || saveOutput;
      const binFiles = await saveGeneratedFiles(binResult);
      if (designSpaceContext) {
        DL.requireSpaceContext(designSpaceContext);
        if (state.designInventoryId !== designRowId ||
            JSON.stringify(state.design) !== JSON.stringify(payload.design))
          throw new Error("This bin changed while its files were being saved. Its status was not changed.");
        const names = [...new Set(binFiles.map(file => String(file).split(/[\\/]/).pop())
          .filter(name => /\.3mf$/i.test(name)))];
        if (!names.length) throw new Error("No current bin files were saved.");
        const saved = await DL.inventoryCall("/api/drawer/design-source/status", {
          row_id: designRowId, action: "saved", file: names.join(", "), design: payload.design,
        }, { context: designSpaceContext });
        DL.adopt(saved);
        DL.emit();
      }
      if (!designRowId && binResult.inventory_bin && state.inventoryEnabled && typeof SP !== "undefined") {
        await SP.addInventoryBin(binResult.inventory_bin, binResult.inventory_design_spec || null);
      }
      allFiles.push(...binFiles);
      binSaved = true;
      setItemStatus("bin", "done", "Done");
      // The just-saved bin is the next resume target. The generated files and
      // inventory entry already exist by this point, so a checkpoint-save
      // failure here must not be reported as the generation itself
      // failing (Correction 1) - only that this design still needs saving
      // to the Space, which a later preview/action will retry.
      if (state.folderMode === "space" && typeof SP !== "undefined") {
        try {
          await SP.flushResumeCheckpoint(payload.design, false);
        } catch (error) {
          checkpointSaveFailed = error;
        }
      }
    }

    // Step 2: Generate Connector if requested
    if (target === "all" || target === "connector") {
      saveStage = "connector";
      setItemStatus("connector", "generating", "Saving…");
      const connResult = await api("/api/connector", payload);
      saveOutput = connResult.output || saveOutput;
      if (connResult.connector_plan) {
        connectorPlan = connResult.connector_plan;
        renderConnectorReadout(connResult.connector_plan);
      }
      const connFiles = await saveGeneratedFiles(connResult);
      allFiles.push(...connFiles);
      if (connResult.partial) {
        // Some connectors were really written before a later one failed.
        setItemStatus("connector", "error", "Partly saved");
        const savedList = [...new Set(allFiles)];
        const message = `${binSaved ? "The bin was saved. " : ""}Some connector files were saved, but not all.\n${connResult.error || ""}`
          + `${savedList.length ? `\nSaved to ${saveOutput}\n${savedList.join("\n")}` : ""}`;
        if (dialogTitle) dialogTitle.textContent = binSaved ? "Bin saved; connectors partly saved" : "Connectors partly saved";
        if (dialogSubtitle) dialogSubtitle.textContent = "Some connector files were saved before the remaining connector failed.";
        if (dialogError) {
          dialogError.textContent = message;
          dialogError.hidden = false;
        }
        if (dialogActions) dialogActions.hidden = false;
        toast(message, true, 9000);
        return;
      }
      setItemStatus("connector", "done", "Done");
    }

    // Fix 032 Correction 2 (C2.3): the generated output is real either way,
    // but a failed final checkpoint must not be buried under an
    // unconditional "Complete!" - and the two outcomes get exactly one
    // toast each, not a success toast followed by a contradicting one.
    if (checkpointSaveFailed) {
      if (dialogTitle) dialogTitle.textContent = "Saved — design save needs attention";
      if (dialogSubtitle) dialogSubtitle.textContent = "Parts were saved, but the current design could not be saved to this Space.";
    } else {
      if (dialogTitle) dialogTitle.textContent = "Saved";
      if (dialogSubtitle) dialogSubtitle.textContent = "All parts saved.";
    }

    // Pause briefly so user clearly sees checkmarks
    await new Promise(resolve => setTimeout(resolve, 650));

    if (dialog && dialog.open) {
      dialog.close();
    }

    const uniqueFiles = [...new Set(allFiles)];
    const planNote = connectorPlan && connectorPlan.webbed
      ? `\nConnector: ${fmt(connectorPlan.length_mm)} mm long, ${fmt(connectorPlan.web_thickness_mm)} mm web, `
        + `${fmt(connectorPlan.printed_height_mm)} mm printed height`
      : "";
    const savedMessage = `Saved to ${saveOutput}${uniqueFiles.length ? `\n${uniqueFiles.join("\n")}` : ""}${planNote}`;
    toast(
      checkpointSaveFailed
        ? `${savedMessage}\n\nThe current design could not be saved to this Space: ${checkpointSaveFailed.message}`
        : savedMessage,
      Boolean(checkpointSaveFailed),
      checkpointSaveFailed ? 9000 : 7000,
    );
  } catch (error) {
    if (target === "all" || target === "bin") {
      const binRow = $("#gen-item-bin");
      if (binRow && !binRow.classList.contains("status-done")) {
        setItemStatus("bin", "error", "Failed");
      }
    }
    if (target === "all" || target === "connector") {
      const connRow = $("#gen-item-connector");
      if (connRow && !connRow.classList.contains("status-done")) {
        setItemStatus("connector", "error", "Failed");
      }
    }

    const connectorsFailedAfterBin = binSaved && saveStage === "connector";
    let failureText = error.message;
    if (connectorsFailedAfterBin) {
      const savedList = [...new Set(allFiles)];
      failureText = `The bin was saved, but the connectors could not be saved: ${error.message}`
        + `${savedList.length ? `\nSaved to ${saveOutput}\n${savedList.join("\n")}` : ""}`;
    }
    if (dialogTitle) dialogTitle.textContent = connectorsFailedAfterBin ? "Bin saved; connectors failed" : "Saving Failed";
    if (dialogSubtitle) dialogSubtitle.textContent = connectorsFailedAfterBin
      ? "The bin file was saved. Only the connectors failed."
      : "An error occurred while saving parts.";
    if (dialogError) {
      dialogError.textContent = failureText;
      dialogError.hidden = false;
    }
    if (dialogActions) {
      dialogActions.hidden = false;
    }
    setError(failureText);
    toast(failureText, true, 7000);
  } finally {
    isGenerating = false;
    state.designMutationBusy = false;
    setMutationSurfacesInert(false);
    updateGenerateAvailability();
    updateHistoryButtons();
  }
}

async function generate(path, selector) {
  if (path && path.includes("connector")) {
    return generateParts("connector");
  }
  return generateParts("bin");
}

async function printModel(target = "bin", initiatingButton = null) {
  if (state.runtime.hosted) return generateParts(target === "all" ? "all" : "bin");
  if (!typedSpaceOrdinaryBin() && !checkPartNamePresent(target)) return;
  if (!state.slicer || !state.slicer.available) {
    toast("Bambu Studio is not installed or could not be found. Please install Bambu Studio or click 'Change slicer' to locate the executable.", true, 8000);
    return;
  }
  if (typedSpaceOrdinaryBin() &&
      !(await flushSpaceDesignAutosave({ materialize: target === "bin" || target === "all" }))) return;
  const designRowId = typedSpaceOrdinaryBin() && (target === "bin" || target === "all")
    ? state.designInventoryId : null;
  const designSpaceContext = designRowId ? DL.spaceContext() : null;
  if (!beginDesignMutation()) return;
  const button = initiatingButton || $("#print-without-connectors");
  const old = button.textContent;
  const printButtons = [$("#print-with-connectors"), $("#print-without-connectors")].filter(Boolean);
  printButtons.forEach(one => { one.disabled = true; });
  const slicerName = state.slicer?.name || "Bambu Studio";
  button.textContent = `Sending to ${slicerName}…`;
  setError();
  try {
    await commitVisibleDraft();
    const payload = {
      design: clone(state.design),
      output: state.output,
      connector: state.connector,
      target: target,
      keep_log: designRowId ? false : state.keepLog,
      design_row_id: designRowId || undefined,
    };
    // Fix 032 Correction 1: same exact resume checkpoint contract as
    // generateParts() - flush the pre-operation state before sending. If it
    // cannot be durably saved, stop before /api/print rather than proceed
    // as though the design would still be recoverable on a failed print.
    if (state.folderMode === "space" && typeof SP !== "undefined") {
      try {
        await SP.flushResumeCheckpoint(payload.design, false);
      } catch (error) {
        throw new Error(`The current design could not be saved to this Space, so nothing was sent: ${error.message}`);
      }
    }
    const result = await api("/api/print", payload);
    if (result.partial) {
      // Bin/design files are a real side effect even though connectors or
      // the slicer step failed after them: never mark this row Printed, and
      // never bury the truth of what was actually saved.
      let savedStatusFailed = null;
      if (designSpaceContext) {
        try {
          DL.requireSpaceContext(designSpaceContext);
          if (state.designInventoryId !== designRowId ||
              JSON.stringify(state.design) !== JSON.stringify(payload.design))
            throw new Error("This bin changed during the slicer handoff.");
          const names = [...new Set((result.design_files || []).map(file => String(file).split(/[\\/]/).pop())
            .filter(name => /\.3mf$/i.test(name)))];
          const saved = await DL.inventoryCall("/api/drawer/design-source/status", {
            row_id: designRowId, action: "saved", file: names.join(", "), design: payload.design,
          }, { context: designSpaceContext });
          DL.adopt(saved);
          DL.emit();
        } catch (error) {
          savedStatusFailed = error;
        }
      }
      const partialMessage = result.error || "Files were saved, but the print could not finish.";
      setError(partialMessage);
      toast(
        savedStatusFailed
          ? `${partialMessage}\n\nSaved status could not be recorded: ${savedStatusFailed.message}`
          : partialMessage,
        true,
        9000,
      );
      return;
    }
    if (designSpaceContext) {
      try {
        DL.requireSpaceContext(designSpaceContext);
        if (state.designInventoryId !== designRowId ||
            JSON.stringify(state.design) !== JSON.stringify(payload.design))
          throw new Error("This bin changed during the slicer handoff.");
        const names = [...new Set((result.design_files || []).map(file => String(file).split(/[\\/]/).pop())
          .filter(name => /\.3mf$/i.test(name)))];
        const printed = await DL.inventoryCall("/api/drawer/design-source/status", {
          row_id: designRowId, action: "printed", file: names.join(", "), design: payload.design,
        }, { context: designSpaceContext });
        DL.adopt(printed);
        DL.emit();
      } catch (error) {
        throw new Error(`Bambu Studio opened, but Printed status could not be recorded: ${error.message}`);
      }
    }
    const files = result.files || [];
    const fileNames = files.map(f => f.split(/[\\/]/).pop());
    const sentMessage = `Sent to ${slicerName}!\n${fileNames.join("\n")}`;
    if (target === "bin" || target === "all") {
      // Fix 032 Correction 2 (C2.3): the slicer handoff already succeeded
      // by this point, so defer the success toast until after the final
      // checkpoint attempt and report exactly one message - never the
      // ordinary success toast followed by a contradicting failure one.
      let checkpointSaveFailed = null;
      if (state.folderMode === "space" && typeof SP !== "undefined") {
        try {
          await SP.flushResumeCheckpoint(payload.design, false);
        } catch (error) {
          checkpointSaveFailed = error;
        }
      }
      toast(
        checkpointSaveFailed
          ? `${sentMessage}\n\nThe current design could not be saved to this Space: ${checkpointSaveFailed.message}`
          : sentMessage,
        Boolean(checkpointSaveFailed),
        checkpointSaveFailed ? 9000 : 7000,
      );
    } else {
      toast(sentMessage, false, 7000);
    }
  } catch (error) {
    setError(error.message);
    toast(error.message, true, 8000);
  } finally {
    button.textContent = old;
    finishDesignMutation();
  }
}

// Connectors are physically unavailable for a B4B, a Base Trim or a lidded
// bin - the same rule that hides Save Bin + Connectors.
function connectorsUnavailable() {
  return b4bEnabled() || baseTrimEnabled() || Boolean(state.design?.box?.lid?.enabled);
}

function syncPrintChoiceAvailability() {
  const withButton = $("#print-with-connectors");
  if (withButton) withButton.hidden = connectorsUnavailable();
}

function updatePrimaryPrintButtonLabel() {
  const withButton = $("#print-with-connectors");
  const withoutButton = $("#print-without-connectors");
  const wrap = $(".print-button-wrap");
  if (!withButton || !withoutButton) return;
  if (wrap) wrap.hidden = false;
  syncPrintChoiceAvailability();
  withoutButton.hidden = false;
  if (state.runtime.hosted) {
    withButton.textContent = "Save with Connectors";
    withButton.title = "Save the bin and its connector files into your selected folder";
    withoutButton.textContent = "Save without Connectors";
    withoutButton.title = "Save only the bin into your selected folder";
    $("#slicer-picker-button").hidden = true;
    return;
  }
  const name = state.slicer?.name || "Bambu Studio";
  const missing = !state.slicer?.available;
  withButton.textContent = "Print with Connectors";
  withoutButton.textContent = "Print without Connectors";
  withButton.title = missing
    ? "Bambu Studio is not installed - click 'Change slicer' to locate executable"
    : `Send the bin and its connectors to ${name}`;
  withoutButton.title = missing
    ? "Bambu Studio is not installed - click 'Change slicer' to locate executable"
    : `Send only the bin to ${name}`;
}

function updateSlicerUI() {
  updatePrimaryPrintButtonLabel();
}

async function browseSlicer() {
  const button = $("#slicer-picker-button");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/browse-slicer-path", { current: state.slicer?.path });
    if (result.slicer_path) {
      const name = result.slicer_path.split(/[\\/]/).pop().replace(/\.exe$/i, "");
      state.slicer = {
        available: true,
        path: result.slicer_path,
        name: /bambu/i.test(name) ? "Bambu Studio" : /orca/i.test(name) ? "OrcaSlicer" : name,
      };
      updateSlicerUI();
      toast(`Slicer set to ${state.slicer.name}`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function collectOutputs(value, found = []) {
  if (!value || typeof value !== "object") return found;
  if (typeof value.output === "string") found.push(value.output.split(/[\\/]/).pop());
  Object.values(value).forEach(item => collectOutputs(item, found));
  return [...new Set(found)];
}

async function saveGeneratedFiles(result) {
  if (!state.runtime.hosted) return collectOutputs(result.result);
  const files = result.files || [];
  if (!files.length) throw new Error("The server did not return any files to save.");
  const folder = state.browserFolder;
  if (folder?.handle) {
    const conflicts = [];
    for (const file of files) {
      if (await WFFileSystem.fileExists(folder.handle, file.name)) conflicts.push(file.name);
    }
    if (conflicts.length) {
      showFilenameConflictDialog(conflicts);
      throw new Error("Give the bin a different name to avoid overwriting an existing file.");
    }
  }
  const saved = [];
  for (const file of files) {
    const response = await fetch(file.url);
    if (!response.ok) throw new Error(`Could not download ${file.name}.`);
    await WFFileSystem.writeBlob(folder?.handle, file.name, await response.blob());
    saved.push(file.name);
  }
  return saved;
}

function watchServerVersion() {
  setInterval(async () => {
    let health;
    try {
      health = await api("/api/health");
    } catch (_error) {
      return; // A blip shouldn't flip the banner - only a confirmed different instance should.
    }
    if (health.instance === state.serverInstance) return;
    if (state.runtime.hosted && health.api_compat === state.apiCompat) {
      state.serverInstance = health.instance;
      return;
    }
    const incompatibleHosted = state.runtime.hosted;
    const message = $("#update-banner span");
    if (message) message.textContent = incompatibleHosted
      ? "Wavefinity was updated. This update requires the page to reload before you continue."
      : "Wavefinity restarted. Reload to use the current code.";
    $("#update-banner").hidden = false;
  }, VERSION_POLL_MS);
}

async function showAboutDialog() {
  const dialog = $("#about-dialog");
  const content = $("#about-dialog-content");
  if (!dialog || !content) return;
  dialog.showModal();
  try {
    const res = await fetch("/Brochure.md");
    if (!res.ok) throw new Error("Could not load Brochure.md");
    let text = await res.text();
    const cutIndex = text.search(/##\s*🚀\s*Ready to test it out/i);
    if (cutIndex !== -1) {
      text = text.slice(0, cutIndex).trimEnd();
      if (text.endsWith("---")) {
        text = text.slice(0, -3).trimEnd();
      }
    }
    content.innerHTML = renderSimpleMarkdown(text);
  } catch (err) {
    content.textContent = "Could not load brochure: " + err.message;
  }
}

function renderSimpleMarkdown(md) {
  let html = md
    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
    .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
    .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/gim, '<em>$1</em>')
    .replace(/\[(.*?)\]\((.*?)\)/gim, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/^(?:---|\*\*\*)$/gim, '<hr>');

  const lines = html.split("\n");
  let inList = false;
  const processed = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ")) {
      if (!inList) {
        processed.push("<ul>");
        inList = true;
      }
      processed.push(`<li>${trimmed.slice(2)}</li>`);
    } else {
      if (inList) {
        processed.push("</ul>");
        inList = false;
      }
      if (trimmed && !trimmed.startsWith("<h") && !trimmed.startsWith("<blockquote") && !trimmed.startsWith("<hr")) {
        processed.push(`<p>${trimmed}</p>`);
      } else if (trimmed) {
        processed.push(trimmed);
      }
    }
  }
  if (inList) processed.push("</ul>");
  return processed.join("\n");
}

function wireAboutDialog() {
  const aboutBtn = $("#about-btn");
  const dialog = $("#about-dialog");
  const closeBtn = $("#about-dialog-close");
  const closeHeaderBtn = $("#about-dialog-close-btn");

  if (aboutBtn) {
    aboutBtn.addEventListener("click", () => showAboutDialog());
  }
  if (closeBtn && dialog) {
    closeBtn.addEventListener("click", () => dialog.close());
  }
  if (closeHeaderBtn && dialog) {
    closeHeaderBtn.addEventListener("click", () => dialog.close());
  }
  if (dialog) {
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });
  }
}

function wireBinNameDialog() {
  const dialog = $("#bin-name-dialog");
  const okBtn = $("#bin-name-dialog-ok");
  if (okBtn && dialog) {
    okBtn.addEventListener("click", () => dialog.close());
  }
  if (dialog) {
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });
  }
}

async function init() {
  wireAboutDialog();
  wireBinNameDialog();
  try {
    const catalog = await api("/api/catalog");
    state.catalog = catalog;
    state.runtime = catalog.runtime || { hosted: false, filesystem: "server" };
    state.serverInstance = catalog.instance;
    state.apiCompat = catalog.api_compat;
    state.design = clone(catalog.defaults.design);
    resetNestPhotoSession();
    state.cleanDesign = clone(state.design);
    state.output = state.runtime.hosted ? "" : (catalog.preferences?.output || catalog.defaults.output);
    setFolderState("design");
    state.connector = clone(catalog.defaults.connector);
    state.slicer = catalog.slicer || { available: false, path: null, name: "Bambu Studio" };
    updateSlicerUI();
    renderCatalog();
    wireControls();
    bindLidMemoryForDesign();
    syncForm();
    watchServerVersion();
    updateHistoryButtons();
    clearDraftSelection();

    // Space startup owns the first preview. Catalog/UI initialization is
    // enough to begin onboarding, so Welcome/Resume no longer waits behind
    // preview generation.
    state.ready = true;
    window.dispatchEvent(new Event("wavefinity:ready"));
  } catch (error) {
    // A startup failure must never leave an infinite "Opening Wavefinity..."
    // cover over the actual error.
    document.getElementById("startup-cover")?.setAttribute("hidden", "");
    setError(error.message);
    toast(error.message, true, 8000);
  }
}

init();
