"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const previewClientId = [...crypto.getRandomValues(new Uint8Array(16))]
  .map(byte => byte.toString(16).padStart(2, "0")).join("");

let engineeringInputId = 0;
const engineeringInputSelector = 'input[type="number"], input[inputmode="numeric"], input[inputmode="decimal"]';
function suppressEngineeringAutofill(root = document) {
  const inputs = root.matches?.(engineeringInputSelector)
    ? [root]
    : root.querySelectorAll?.(engineeringInputSelector) || [];
  for (const input of inputs) {
    input.autocomplete = "off";
    if (!input.name || !input.name.startsWith("wavefinity-")) {
      const identity = input.id || input.dataset.draft || input.dataset.dividerScoopDepth || "field";
      const safeIdentity = identity.replace(/[^a-zA-Z0-9_-]+/g, "-");
      input.name = `wavefinity-${safeIdentity}-${++engineeringInputId}`;
    }
  }
}
suppressEngineeringAutofill();
new MutationObserver(records => {
  for (const record of records) {
    for (const node of record.addedNodes) {
      if (node.nodeType === Node.ELEMENT_NODE) suppressEngineeringAutofill(node);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

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
  // Fix 103 (Section C): the single client slot for structural 3D preview.
  // Holds the adopted preview result (meshes, bounds, etc.) for the current
  // structural target. Never mixed into state.preview / state.design.
  structuralPreview: null,
  structuralPreviewError: "",
  structuralPreviewStale: false,
  // Fix 103 (Section E): "drawer:<id>" owner highlighted in the 3D preview.
  structuralHighlightOwner: null,
  // Fix 103 (R3): bumped whenever the structural form is destroyed/remounted,
  // so a response for an older mount can never be adopted.
  structuralMountSerial: 0,
  // Fix 103 (R1): live drag of an Interior Width/Depth/Height label.
  structuralDimensionDrag: null,
  draftKind: "divider",
  draft: null,
  draftResolvedOptions: {},
  referenceResolutionRequest: null,
  // The last Design 2D/3D view actually used, runtime-only (Fix 078): a mode
  // switch through Space never overwrites it, only 2D/3D activation does.
  lastDesignView: "3d",
  // True while a Bore-angle/direction OK/Cancel growth confirmation is open,
  // so the generic silent auto-grow catch does not preempt it (Fix 078).
  boreAngleGrowthPending: false,
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
  lidThicknessReport: null,
  lidLabelBackingReport: null,
  lidThicknessEpoch: 0,
  lidThicknessFormKey: null,
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
  // Fix 103 (Section C): epoch for structural preview requests; stale
  // responses are dropped, latest request wins.
  structuralPreviewRequest: 0,
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
  // Fix 103: explicit Design target selection. Only the structural target is
  // ever stored here ({ kind: "structural", structural: true, structuralKind:
  // "box" | "storage_drawers", rowId: null, drawerId: null }); null means
  // "derive from the legacy designInventoryId binding" (DP.getDesignTarget).
  // Every bin/new-bin install path keeps it null so derivation stays exact.
  designTarget: null,
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
  designerHistory: [],
  designerFuture: [],
  designerHistoryRestoring: false,
  canGenerate: true,
  // Bin/Interior/Xray are independent on/off switches, not one exclusive
  // mode - each button flips only its own state (see setPreviewToggle()).
  binVisible: true,
  interiorVisible: true,
  xrayOn: false,
  // All/Base/Lid preview state for a Storage Box preview response. The Designer
  // only ever holds ordinary bins now, so this stays "all".
  b4bView: "all",
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
    state.designTarget = null; // Fix 103
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

// Fix 082 H: a Text feature with no words yet is an incomplete editor state,
// not an invalid design - never committed, never a fit error, never an
// Inventory row by itself.
function isBlankTextDraft(feature) {
  return feature?.kind === "text" && !String(feature.options?.text ?? "").trim();
}

// Consent belongs to this edit and, for a typed Space, its durable settings.
// It is never a property of the Text feature or a geometry requirement.
async function acknowledgeSmallText() {
  const inSpace = state.folderMode === "space" && typeof DL !== "undefined" && DL.layout;
  const context = inSpace ? DL.spaceContext() : null;
  if (inSpace && DL.layout.settings?.text_small_size_ack === true) return true;
  await appConfirm({
    title: "Small Text Size",
    message: "Text height will be adjusted to smaller than the recommended 5 mm to accommodate your text.",
    primaryLabel: "OK",
    cancelLabel: null,
    dismissible: false,
  });
  if (inSpace) {
    if (!DL.spaceContextCurrent(context)) return false;
    DL.change(() => { DL.layout.settings.text_small_size_ack = true; }, { history: false });
    const saved = await DL.save();
    if (!DL.spaceContextCurrent(context)) return false;
    if (!saved) {
      DL.change(() => { DL.layout.settings.text_small_size_ack = false; }, { history: false });
      return false;
    }
  }
  return true;
}

async function allowSmallTextEdit(cap, request, draft) {
  if (draft?.kind !== "text") return true;
  if (!Number.isFinite(cap) || cap <= 0) {
    throw new Error("Could not determine a printable Letter height for this Text.");
  }
  if (cap >= 5) return true;
  const index = draftCommitIndex();
  const changed = state.draftIsNew || (Number.isInteger(index)
    ? JSON.stringify(state.design.layout.features[index]) !== JSON.stringify(draft)
    : state.draftTouched);
  if (!changed) return true; // reopening an existing sub-5 Text is not an edit
  if (state.smallTextApprovedDraftRequest === request) return true;
  if (!state.smallTextConsentPromise) {
    const pending = acknowledgeSmallText();
    state.smallTextConsentPromise = pending;
    const clearPending = () => {
      if (state.smallTextConsentPromise === pending) state.smallTextConsentPromise = null;
    };
    pending.then(clearPending, clearPending);
  }
  const allowed = await state.smallTextConsentPromise;
  if (request !== state.draftRequest || state.draft !== draft) return false;
  if (allowed) state.smallTextApprovedDraftRequest = request;
  return allowed;
}

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
  // reference_object is object-specific; reusable Space settings exclude it.
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
  // Fix 082 H: a brand-new Text always starts On base - Inlaid - 0 degrees,
  // regardless of what style/rotation the last Text in this Space happened
  // to use, so those settings are never remembered for this kind.
  if (feature.kind === "text") {
    delete copy.options.small_size_ack;
    delete copy.options.level;
    delete copy.options.raised;
    delete copy.options.rim_side;
    delete copy.options.quarter_turns;
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

// The Space's remembered Text default: the last qualifying (>= 5 mm) Text
// height actually applied in this Space, or null when the Space has none.
// Untyped Design has no remembered Space Text height.
function spaceRememberedTextHeight() {
  if (state.folderMode !== "space") return null;
  const raw = state.spacePartDefaults?.text?.options?.cap_height;
  const value = Number(raw);
  return Number.isFinite(value) && value >= 5 ? value : null;
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
  if (entry.kind === "text") {
    delete clean.options.small_size_ack;
    delete clean.options.level;
    delete clean.options.raised;
    delete clean.options.rim_side;
    delete clean.options.quarter_turns;
    // A Text footprint is fully derived from its lettering and height; a
    // glyph-derived zone is not a reusable setting and must never steer a fit.
    delete clean.zone_size;
  }
  if (Object.hasOwn(entry, "count")) clean.count = entry.count;
  if (typeof entry.along === "string") clean.along = entry.along;
  if (typeof entry.wedge === "boolean") clean.wedge = entry.wedge;
  if (typeof entry.alternate_ends === "boolean") clean.alternate_ends = entry.alternate_ends;
  // Item measurements/profile/clearance are reusable; a user's item name is
  // identity and never carries into another bin.
  if (plainObject(entry.item)) clean.item = { ...clone(entry.item), name: "Custom item" };
  delete clean.reference_object;
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
  delete seeded.reference_object;
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
    if (kind === "text" && entry.options) {
      const cap = Number(entry.options.cap_height);
      if (Number.isFinite(cap) && cap > 0 && cap < 5) {
        // A forced sub-5 height is usable for this Text but never becomes the
        // Space default. Keep the previous qualifying default; other reusable
        // Text settings (e.g. depth) still update.
        const previousQualifying = spaceRememberedTextHeight();
        if (previousQualifying !== null) {
          entry.options.cap_height = previousQualifying;
        } else {
          delete entry.options.cap_height;
        }
      }
    }
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
      number(state.catalog?.base_rules?.default_mm, 0.8)
      + number(state.catalog?.min_height_above_base_mm, 5),
    ),
  );
}

// Smallest bin (mm) the product allows on a Pegboard Space: Standard needs a
// minimum height only; SKÅDIS needs a minimum width and height. New Bin and AI Help
// both read this, so there is one table.
function pegboardProductMinimums(standard) {
  return standard === "standard" ? { x: 0, z: 48 } : { x: 56, z: 40 };
}

// `remembered` is this Space's bin-preference snapshot (see
// spaceBinPreferences). Its X/Y/Z seed the bin, then the Space's own capacity
// and height rules clamp them - a remembered value that no longer fits is
// normalized, never turned into an invalid bin. With nothing remembered the
// product starter sizing applies unchanged.
// The selected physical drawer's usable X/Y/height for a Storage Drawers Space.
function cabinetActiveLimits() {
  if (state.activeSpace?.kind !== "storage_drawers" || typeof StorageDrawers === "undefined") return {};
  try {
    if (typeof SP !== "undefined") SP.ensureStorageDrawersRules();
    return StorageDrawers.activeDrawerLimits(state.activeSpace, typeof DL !== "undefined" ? DL.layout : null);
  } catch (_error) {
    return {};
  }
}

// The first time a cabinet's layout loads, an untouched starter bin is
// re-sized to the drawer that is actually active (startup builds the starter
// before the persisted active drawer is known). A resumed, bound or edited
// design is never resized, and later drawer switches never resize anything.
function reseedCabinetStarterAfterLayoutLoad() {
  if (state.activeSpace?.kind !== "storage_drawers" || state.cabinetStarterSeededFor === state.activeSpaceId) return;
  state.cabinetStarterSeededFor = state.activeSpaceId;
  if (state.designInventoryId || state.spaceResumeDesign || state.spaceResumePending) return;
  if (JSON.stringify(state.design) !== JSON.stringify(state.cleanDesign)) return;
  const next = freshDesignForCurrentFolder();
  if (JSON.stringify(next.box) === JSON.stringify(state.design.box)) return;
  state.design = next;
  state.cleanDesign = clone(next);
  if (typeof syncForm === "function") syncForm();
  if (typeof refreshPreview === "function") refreshPreview();
}

function applySpaceSizingDefaults(design, remembered = null) {
  if (state.folderMode !== "space" || !state.activeSpace) return design;

  const kind = state.activeSpace.kind;
  // Storage Drawers: the physical drawer being designed for, never the
  // cabinet's compatibility total.
  const space = kind === "storage_drawers"
    ? { ...state.activeSpace, ...cabinetActiveLimits() }
    : state.activeSpace;
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
      const exactMinimum = base + minimumAbove;
      design.box.z = haveRememberedZ && rememberedZ >= exactMinimum
        ? Math.round(rememberedZ * 10) / 10
        : roundUpHalfMm(exactMinimum);
    }
  } else if (kind === "portable" || kind === "box" || kind === "storage_drawers") {
    design.box.z = normalizeBinDimension(
      "z", haveRememberedZ ? Math.min(space.z, rememberedZ) : space.z,
    );
  } else if (kind === "pegboard") {
    if (haveRememberedZ) design.box.z = normalizeBinDimension("z", rememberedZ, rememberedZ);
    const minimum = pegboardProductMinimums(space.pegboard_standard);
    design.box.x = Math.max(minimum.x, design.box.x);
    design.box.z = Math.max(minimum.z, design.box.z);
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
  if (!remembered) {
    // Fix 1012: a fresh ordinary New Bin starts at 50x50 mm.
    starter.box.x = 50;
    starter.box.y = 50;
    return applySpaceSizingDefaults(starter);
  }
  return applySpaceSizingDefaults(mergeDesignDefaults(starter, remembered), remembered);
}

async function loadFreshOrdinaryDesignForCurrentFolder(overrideBox = null) {
  const design = freshDesignForCurrentFolder();
  if (overrideBox) Object.assign(design.box, overrideBox);
  state.design = design;
  clearDesignerHistory();
  state.designInventoryId = null;
  state.designTarget = null; // Fix 103
  state.lastOrdinaryDesign = clone(state.design);
  resetNestPhotoSession();
  state.cleanDesign = clone(state.design);
  state.spaceStarterPreviewPending = state.folderMode === "space";
  // Showing a fresh starter does not create an Inventory row.
  state.drafts = {};
  state.binResizePending = false;
  state.binFootprintResizePending = false;
  bindLidMemoryForDesign();
  syncForm();
  clearDraftSelection();
  activatePreviewView(preferredDesignView());
  await refreshPreview();
  const starterHelp = $("#design-first-size-help");
  if (starterHelp) {
    const show = state.folderMode !== "space";
    starterHelp.hidden = !show;
    starterHelp.textContent = show
      ? `Starting size: ${fmt(state.design.box.x)} × ${fmt(state.design.box.y)} mm. Change Width and Depth to fit what you want to organize.`
      : "";
  }
  if (typeof DP !== "undefined") { DP.refreshDesignBinNav(); DP.refreshDesignerDeleteBin(); }
}