"use strict";

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
      $("#surface-object-height-cancel").onclick = null;
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
    // Escape and the visible Cancel button are one path: close and abort the
    // triggering operation with no Object height, skip flag or preference change.
    const onCancel = event => { event.preventDefault(); if (!busy) finish(false); };
    $("#surface-object-height-cancel").onclick = () => { if (!busy) finish(false); };
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

function readInlineSurfaceObjectHeight() {
  const input = $("#surface-object-height");
  const error = $("#surface-object-height-inline-error");
  const text = String(input?.value ?? "").trim();
  const fail = message => {
    if (error) {
      error.textContent = message;
      error.hidden = false;
    }
    return { ok: false, value: null };
  };
  if (text === "") {
    if (error) {
      error.textContent = "";
      error.hidden = true;
    }
    return { ok: true, value: null };
  }
  const value = Number(text);
  if (!Number.isFinite(value) || value <= 0) {
    return fail("Enter a positive Object height, or leave it blank.");
  }
  if (error) {
    error.textContent = "";
    error.hidden = true;
  }
  return { ok: true, value };
}

function resolveSurfaceBase(design, { fromForm = false } = {}) {
  if (!isSurfaceBinDesign(design)) return;
  design.layout ||= {};
  const oldBase = number(
    design.box.base_thickness,
    state.catalog?.base_rules?.default_mm ?? 0.8,
  );
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
    const objectHeight = readInlineSurfaceObjectHeight();
    if (!objectHeight.ok) return false;
    design.layout.object_height_mm = objectHeight.value;
    design.layout.surface_lightweight_base = !surfaceStackingBlocked(design)
      && $("#surface-lightweight-base").checked;
  }
  return true;
}

function syncSurfaceControls() {
  const shown = isSurfaceBinDesign();
  const controls = $("#surface-bin-controls");
  if (!controls) return;
  controls.hidden = !shown;
  $("#base-thickness-setting").hidden = shown;
  $("#z-size-label").textContent = shown ? "Bin height" : "Height";
  if (!shown) return;
  const layout = state.design.layout || {};
  const edge = surfaceTrimHeight(state.activeSpace.trim_size);
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
// Edge Mount owns a separate text-depth default. The backend catalog is the
// authority; 0.6 is only the stale-catalog fallback for an older server.
function edgeMountTextDepthDefault() {
  return number(
    state.catalog?.edge_mount?.defaults?.label_text_depth_mm,
    0.6,
  );
}
const EDGE_MOUNT_DEFAULTS = {
  side: "front",
  label_enabled: false,
  label_text: "",
  label_type: "separate",
  label_projection_mm: 50,
  label_length_mode: "full",
  label_thickness_mm: 2,
  label_raised: false,
  label_text_depth_mm: edgeMountTextDepthDefault(),
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

// R76: connector settings are system-wide (desktop preferences file, or
// browser localStorage when hosted). Only these six fields are remembered.
const CONNECTOR_SETTINGS_KEY = "wavefinity-connector-settings-v1";

// One shared step for restoring and saving: each field must be legal (the same
// ranges as the connector form) or it falls back to `fallback`.
const CONNECTOR_SETTING_LIMITS = {
  tolerance: [0, 1], length: [2, Infinity], arm_thickness: [0.5, 10],
  bin_a_height: [2, Infinity], bin_b_height: [2, Infinity],
};
function normalizeConnectorSettings(raw, fallback = {}) {
  const source = raw && typeof raw === "object" ? raw : {};
  const result = {};
  for (const [key, [low, high]] of Object.entries(CONNECTOR_SETTING_LIMITS)) {
    const value = source[key];
    let legal = typeof value === "number" && Number.isFinite(value) && value >= low && value <= high;
    if (key === "arm_thickness") {
      // The generator's own floor, served by the catalog; unknown means not legal.
      const floor = state.catalog?.connector_rules?.arm_thickness_floor_mm;
      legal = legal && typeof floor === "number" && value > floor;
    }
    result[key] = legal ? value : fallback[key];
  }
  result.different_heights = typeof source.different_heights === "boolean"
    ? source.different_heights : fallback.different_heights === true;
  return result;
}

function readConnectorSettingsFields() {
  const field = selector => {
    const text = String($(selector)?.value ?? "").trim();
    return text === "" ? NaN : Number(text);
  };
  const raw = {
    tolerance: field("#connector-tolerance"),
    length: field("#connector-length"),
    arm_thickness: field("#connector-arm-thickness"),
    bin_a_height: field("#connector-bin-a-height"),
    bin_b_height: field("#connector-bin-b-height"),
    different_heights: $("#connector-height-mode")?.value === "different",
  };
  const clean = normalizeConnectorSettings(raw);
  return Object.values(clean).some(value => value === undefined) ? null : clean;
}

function restoreConnectorSettings() {
  let raw = null;
  try {
    raw = state.runtime.hosted
      ? JSON.parse(localStorage.getItem(CONNECTOR_SETTINGS_KEY) || "null")
      : state.catalog?.preferences?.connector_settings;
  } catch (_error) { raw = null; }
  if (!raw || typeof raw !== "object") return;
  Object.assign(state.connector, normalizeConnectorSettings(raw, state.connector));
}

let lastSavedConnectorSettings = "";
// Fix 096 A4: connector saves run one at a time, in the order the user made
// them - an older request can never finish (and become durable) after a newer
// one. A failed link never breaks the chain.
let connectorSettingsQueue = Promise.resolve();
function persistConnectorSettings() {
  const settings = readConnectorSettingsFields();
  if (!settings) return;
  const text = JSON.stringify(settings);
  if (text === lastSavedConnectorSettings) return;
  if (state.runtime.hosted) {
    try { localStorage.setItem(CONNECTOR_SETTINGS_KEY, text); lastSavedConnectorSettings = text; }
    catch (_error) { toast("Connector settings could not be remembered in this browser.", true); }
    return;
  }
  connectorSettingsQueue = connectorSettingsQueue.then(() =>
    api("/api/preferences", { connector_settings: settings })
      .then(() => {
        lastSavedConnectorSettings = text;
        if (state.catalog?.preferences) state.catalog.preferences.connector_settings = settings;
      })
      .catch(() => toast("Connector settings could not be remembered.", true))
  );
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

// The one shared reason shown for every Storage Box-disallowed option
// (Fix 111): disallowed tiles are disabled with this as their hover text,
// and the same sentence explains any click that still reaches
// pickKind/selectKind/openModifier/addModifier.
const B4B_PARTS_ONLY_DIVIDER_MESSAGE = "Storage Box bins support Dividers only.";

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
  handle_size: "medium", handle_position: "middle", fit: "standard",
};

// Everything that changes the resolved lid rise for the current bin. The three
// Thin/Medium/Thick measurements the backend returns belong to exactly this key.
function lidThicknessKey(design = state.design) {
  const box = design?.box || {};
  return JSON.stringify([box.x, box.y, box.wall, box.corner_fillet, box.flat_inside,
    Boolean(box.lid?.enabled), Boolean(box.lid?.stackable), (box.stack?.mode || "none")]);
}

// Inlay depth / Raised height as shown: an explicit saved value wins; an older
// file with none was 0.4 mm inlaid and 0.6 mm raised. Both numbers come from
// the backend catalog, never from a table kept here.
function lidLabelDepthShown(lid) {
  if (lid.label_depth_mm !== undefined && lid.label_depth_mm !== null && lid.label_depth_mm !== "") {
    return Number(lid.label_depth_mm);
  }
  const rules = state.catalog?.lid_rules || {};
  return lid.label_style === "raised"
    ? Number(rules.legacy_raised_label_relief_mm ?? 0.6)
    : Number(rules.default_label_relief_mm ?? 0.4);
}

function renderLidLabelDepthLegality() {
  const select = $("#lid-label-depth");
  if (!select) return;
  const handled = lidConfiguration() === "handled_lid";
  const raised = handled && $("#lid-label-style")?.value === "raised";
  const report = state.lidLabelBackingReport;
  const fresh = report && report.epoch === state.lidThicknessEpoch &&
    report.key === lidThicknessKey(state.design);
  for (const option of select.options) {
    option.disabled = false;
    const baseLabel = option.dataset.baseLabel || option.textContent;
    option.dataset.baseLabel = baseLabel;
    option.textContent = baseLabel;
    if (raised || !fresh) continue;
    const depth = Number(option.value);
    if (Number.isFinite(depth) &&
        !inlayDepthLegal(depth, report.backing, report.minimumBacking)) {
      option.disabled = true;
      option.textContent = `${baseLabel} (lid too thin)`;
    }
  }
}

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
// the editor (New, Open, Duplicate, a Space activating/resuming a
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

// Fit and label-depth choices, and the Thin/Medium/Thick measurements, are all
// read from the backend (catalog + the latest matching preview report).
function populateLidChoices() {
  const rules = state.catalog?.lid_rules || {};
  const fit = $("#lid-fit");
  if (fit && Array.isArray(rules.fits) && fit.options.length !== rules.fits.length) {
    fit.replaceChildren(...rules.fits.map(choice => new Option(choice.label, choice.value)));
  }
  const depth = $("#lid-label-depth");
  if (depth && Array.isArray(rules.label_reliefs) && depth.options.length !== rules.label_reliefs.length) {
    depth.replaceChildren(...rules.label_reliefs.map(choice => new Option(choice.label, String(choice.value))));
  }
}

function renderLidThicknessOptions() {
  const select = $("#lid-thickness");
  if (!select) return;
  const report = state.lidThicknessReport;
  // A report only labels the bin it was measured for; while a newer one is
  // pending the plain names show rather than another bin's measurements.
  const fresh = report && report.epoch === state.lidThicknessEpoch
    && report.key === lidThicknessKey(state.design);
  const names = { thin: "Thin", medium: "Medium", thick: "Thick" };
  [...select.options].forEach(option => {
    const mm = fresh ? report.values?.[option.value] : undefined;
    option.textContent = Number.isFinite(mm) ? `${fmt(mm)} mm \u2014 ${names[option.value]}` : names[option.value];
  });
}

// Everything that can change the resolved lid rise: the design plus the raw
// Width / Length / wall / Stacking Method fields, which only reach the design
// after a debounce. Typed edits, wall and method selects and dimension-handle
// drags all pass through changedDesign(), so this is the one place that stops
// the old measurements being presented as current.
function lidThicknessFormKey() {
  return JSON.stringify([lidThicknessKey(state.design), $("#x-size")?.value,
    $("#y-size")?.value, $("#wall-thickness")?.value, $("#lid-configuration")?.value]);
}

// Programmatic form updates do not represent a user edit. Capture their final
// state only after the controls have been synchronized with the measured design.
function settleLidThicknessFormKey() {
  state.lidThicknessFormKey = lidThicknessFormKey();
}

// Called on every design change. When a lid-rise input moved, the measurements
// on screen stop being authoritative at once: the epoch advances, so only a
// preview requested after this edit can bring them back.
function noteLidThicknessEdit() {
  const key = lidThicknessFormKey();
  if (key === state.lidThicknessFormKey) return;
  state.lidThicknessFormKey = key;
  state.lidThicknessEpoch += 1;
  renderLidThicknessOptions();
}

// A landed preview brings back the measurement-first labels only when it was
// requested at the current epoch; an older response leaves the plain names.
function applyLidThicknessReport(result, epochAtRequest) {
  state.lidThicknessReport = result.stack?.lid_thickness_mm
    ? { key: lidThicknessKey(result.design), epoch: epochAtRequest,
        values: result.stack.lid_thickness_mm } : null;
  state.lidLabelBackingReport = result.stack?.lid_label_backing_mm != null
    ? {
        key: lidThicknessKey(result.design),
        epoch: epochAtRequest,
        backing: Number(result.stack.lid_label_backing_mm),
        minimumBacking: Number(result.stack.lid_label_min_backing_mm),
      }
    : null;
  renderLidThicknessOptions();
  renderLidLabelDepthLegality();
}

// A failed replacement preview never leaves the old bin's millimetres shown.
function clearLidThicknessReport() {
  state.lidThicknessReport = null;
  state.lidLabelBackingReport = null;
  renderLidThicknessOptions();
  renderLidLabelDepthLegality();
}

function syncLidForm() {
  const active = lidPartActive();
  const lid = lidState();
  const config = lidConfiguration();
  populateLidChoices();
  $("#lid-option-panel").hidden = !active;
  $("#lid-configuration").value = config;
  $("#lid-thickness").value = lid.thickness;
  renderLidThicknessOptions();
  if ($("#lid-fit")) $("#lid-fit").value = lid.fit || "standard";
  $("#lid-handle-type").value = lid.handle_type;
  $("#lid-handle-size").value = lid.handle_size;
  $("#lid-handle-position").value = lid.handle_position;
  $("#lid-label-enabled").value = String(Boolean(lid.label_enabled));
  $("#lid-label-orientation").value = lid.label_orientation;
  $("#lid-label-style").value = lid.label_style;
  $("#lid-label-text").value = lid.label_text || "";
  const depthField = $("#lid-label-depth");
  if (depthField) {
    const shown = lidLabelDepthShown(lid);
    if (![...depthField.options].some(option => Number(option.value) === shown)) {
      depthField.append(new Option(`${fmt(shown)} mm — Existing`, String(shown)));
    }
    depthField.value = String(shown);
  }
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
  // Inlay depth / Raised height follows the active style; a Stackable Lid is
  // always Inlaid, so it shows Inlay depth.
  const depthRow = $("#lid-label-depth-row");
  if (depthRow) {
    depthRow.hidden = !labelOn;
    const raisedActive = handled && $("#lid-label-style").value === "raised";
    $("#lid-label-depth-name").textContent = raisedActive ? "Raised height" : "Inlay depth";
    depthRow.title = raisedActive
      ? "How far the lid lettering projects above the lid top."
      : "How deeply the lid lettering is cut into the lid; the lid keeps material under it.";
  }
  renderLidLabelDepthLegality();
  const raised = [...$("#lid-label-style").options].find(option => option.value === "raised");
  if (raised) raised.disabled = config === "stackable_lid";
  if (config === "stackable_lid" && $("#lid-label-style").value === "raised") {
    $("#lid-label-style").value = "flush";
  }
  const note = $("#lid-option-note");
  note.textContent = config === "stackable_bin"
    ? "No lid. This bin stacks directly onto another bin with the same footprint and compatible stacking geometry. Remove Lid & Stacking to go back to no lid and no stacking."
    : config === "stackable_lid"
      ? "Handle and raised lettering are unavailable because the next bin needs a flat seating surface."
      : "One removable lid with a handle. This bin is not stackable.";
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
  // Fix 111 N10: one eligibility contract - a lid locks ordinary side
  // connectors everywhere. The section stays visible with a compact reason
  // (rendered by renderConnectorReadout); only the actions hide.
  if (connectorSection) connectorSection.hidden = b4b || baseTrimEnabled();
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
    // Written explicitly on every save, so a missing value only ever means an
    // older file.
    fit: $("#lid-fit")?.value || remembered.fit || "standard",
    ...(($("#lid-label-depth")?.value || remembered.label_depth_mm)
      ? { label_depth_mm: Number($("#lid-label-depth")?.value || remembered.label_depth_mm) } : {}),
  };
}

// Shared by typed Width/Length/Height edits, by dragging their dimension
// labels (see hitDimensionHandle/commitDimensionDrag), so every path
// lands on the same legal value: X/Y snap to the catalog base unit and clamp
// to [unit, max_box_size]; ordinary Z stays on whole millimetres, while
// Surface Z uses half millimetres. A computed minimum always rounds upward.
function normalizeBinDimension(axis, requestedValue, fallback, design = state.design) {
  const value = number(requestedValue, fallback);
  if (axis === "z") {
    const base = number(
      design?.box?.base_thickness,
      state.catalog?.base_rules?.default_mm ?? 0.8
    );
    const minimum = base + number(state.catalog.min_height_above_base_mm, 5);
    return isSurfaceBinDesign(design)
      ? Math.max(roundUpHalfMm(minimum), Math.round(value * 2) / 2)
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