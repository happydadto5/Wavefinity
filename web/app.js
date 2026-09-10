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
  // Which of the open draft's zone axes the user has set by hand. A pinned axis
  // is only ever grown to fit the part's contents, never shrunk back or
  // overwritten - a manual size always wins. Reset whenever a fresh draft loads.
  pinnedZone: {},
  // Session-only manual Base widths/lengths, keyed by placed-part index.
  partZoneLocks: {},
  // Set while a user-driven Width/Length edit waits for grow-only minimum
  // enforcement. Consumed by the debounced design update.
  binResizePending: false,
  camera: { yaw: 45, elevation: 76, zoom: 1 },
  lastBoxSize: null,
  previewRequest: 0,
  draftRequest: 0,
  output: "",
  keepLog: true,
  connector: {},
  layoutDrag: null,
  layoutTransform: null,
  // The 2D layout normally uses the same heading as the 3D camera.  Users can
  // instead pin it to the conventional top-up plan view.
  layoutOrientation: "match3d",
  previewSupportPolygons: [],
  designMutationBusy: false,
  canGenerate: true,
  previewMode: "standard",
  history: [],
  future: [],
  serverInstance: null,
  kindRequest: 0,
  fitRequest: 0,
  nestPhotoRequest: 0,
  // Rectified upload used only as an aligned tracing reference in the 2D view.
  // It deliberately stays out of saved design files.
  nestPhoto: null,
  nudgeFeedback: null,
};

const VERSION_POLL_MS = 5000;

const COLORS = {
  outside: "#8ea8b2", inside: "#c9d9dc", rim: "#6f8f99", floor: "#b9a97e",
  label: "#315766", label_hole: "#e8efef", top_label_ledge: "#7799a3",
  scoop: "#a9bec3", insert_base: "#c5ab83", invalid: "#c95f58",
  cradle: "#e59f54", nest: "#df8d5b", bore: "#6fb98f", post: "#51a5a1",
  divider: "#9d86c8", pocket: "#d4778c", slot: "#8b78cf", steps: "#4b8eb9",
  divider_slope: "#1f6b45",
  // Floor lettering keeps the colour the single floor label always had, so a
  // text interior part reads as writing rather than as another holder.
  text: "#315766",
  // B4B parts get their own colour family, distinct from interior features.
  b4b_rail: "#8ea8b2", b4b_lid: "#7fa9b6", b4b_hinge: "#5f8794",
  b4b_latch: "#c98a4a", b4b_stack: "#9d86c8", b4b_label: "#315766",
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

function pinDraftAxis(axis) {
  state.pinnedZone[axis] = true;
}

function recordHistory(before) {
  if (!before || JSON.stringify(before) === JSON.stringify(state.design)) return;
  state.history.push(clone(before));
  if (state.history.length > 50) state.history.shift();
  state.future = [];
  updateHistoryButtons();
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
    binButton.title = state.canGenerate ? "Generate the current bin files" : "Resolve the highlighted issue before generating";
  }
  const allButton = $("#generate-all");
  if (allButton) {
    allButton.disabled = state.designMutationBusy || !state.canGenerate;
    allButton.title = state.canGenerate ? "Generate bin and connector files" : "Resolve the highlighted issue before generating";
  }
  const connectorButton = $("#generate-connector");
  if (connectorButton) {
    connectorButton.disabled = state.designMutationBusy;
    connectorButton.title = "Generate connector for the current bin";
  }
  const printButton = $("#print-bin");
  if (printButton) {
    printButton.disabled = state.designMutationBusy || !state.canGenerate;
    printButton.title = state.canGenerate ? "Export and open in Bambu Studio" : "Resolve the highlighted issue before printing";
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
    syncForm();
    clearDraftSelection();
    updateHistoryButtons();
    await refreshPreview();
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
function toast(message, error = false, hold = 3200) {
  const node = $("#toast");
  node.textContent = message;
  node.classList.toggle("error", error);
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

function iconFor(kind) {
  const common = 'viewBox="0 0 32 32" aria-hidden="true"';
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
        if (modes.value !== "fused" && state.design?.box?.easy_clean_style === "curve") {
          state.design.box.easy_clean_style = "bevel";
        }
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
  palette.innerHTML = state.catalog.parts.map(part => `
    <button class="support-choice" data-kind="${part.kind}" style="--support-color:${kindColor(part.kind)}" aria-label="${escapeHtml(part.title)}: ${escapeHtml(part.description)}" title="${escapeHtml(part.title)} — ${escapeHtml(part.description)}">
      <span class="support-choice-icon">
        ${iconFor(part.kind)}
      </span>
      <span class="support-choice-copy">
        <strong>${escapeHtml(part.title)}</strong>
        <span class="support-choice-desc">${escapeHtml(part.description)}</span>
      </span>
    </button>
  `).join("");
  $$(".support-choice", palette).forEach(button => {
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
}

function syncEasyCleanControls() {
  const isClean = $("#easy-clean") ? $("#easy-clean").checked : false;
  const mode = state.design?.layout?.mode || $("#mode-select")?.value || "fused";
  const isFused = mode === "fused";

  const curveOption = $("#easy-clean-style option[value='curve']");
  if (!isFused) {
    if (curveOption) {
      curveOption.hidden = true;
      curveOption.disabled = true;
    }
    if ($("#easy-clean-style") && $("#easy-clean-style").value === "curve") {
      $("#easy-clean-style").value = "bevel";
      if (state.design?.box) state.design.box.easy_clean_style = "bevel";
    }
  } else {
    if (curveOption) {
      curveOption.hidden = false;
      curveOption.disabled = false;
    }
  }

  if ($("#easy-clean-style-setting")) $("#easy-clean-style-setting").hidden = !isClean;
  if ($("#easy-clean-radius-setting")) $("#easy-clean-radius-setting").hidden = !isClean;

  const currentStyle = ($("#easy-clean-style") && $("#easy-clean-style").value) || "bevel";
  const labelEl = $("#easy-clean-radius-label");
  if (labelEl) {
    labelEl.textContent = currentStyle === "bevel" ? "Bevel" : "Curve";
  }
}

function populateWallChoices(box) {
  const select = $("#wall-thickness");
  const rules = state.catalog?.wall_rules || {};
  const fallbackLabels = [
    "Very thin (experimental)", "Thin", "Light", "Standard",
    "Reinforced", "Strong", "Extra strong", "Very strong",
    "Heavy duty", "Very heavy duty", "Extra heavy duty", "Maximum thickness",
  ];
  const choices = Array.isArray(rules.choices) && rules.choices.length
    ? rules.choices
    : Array.from({ length: 12 }, (_, index) => {
        const value = 0.2 + index * 0.2;
        return { value, label: fallbackLabels[index] };
      });
  const wall = number(box?.wall, rules.default_mm ?? 0.8);
  const value = fmt(wall);
  const isDiscrete = choices.some(choice => fmt(choice.value) === value);
  const legacyValue = isDiscrete ? "" : value;
  const signature = JSON.stringify({ choices, legacyValue });
  if (select.dataset.choices !== signature) {
    select.replaceChildren(...choices.map(choice => new Option(
      `${number(choice.value).toFixed(1)} mm — ${choice.label}`,
      fmt(choice.value),
    )));
    if (legacyValue) {
      select.add(new Option(`${legacyValue} mm — Existing custom`, legacyValue));
    }
    select.dataset.choices = signature;
  }
  select.value = value;
  if (box?.standard_walls === false) select.dataset.customValue = value;
}

function syncWallControls() {
  const standard = $("#standard-walls").checked;
  const rules = state.catalog?.wall_rules || {};
  $("#wall-thickness-setting").hidden = standard;
  $("#thin-wall-warning").hidden = standard || Math.abs(
    number($("#wall-thickness").value, rules.default_mm ?? 0.8)
      - (rules.min_mm ?? 0.2)
  ) > 1e-9;
}

function syncForm() {
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
  $("#z").value = fmt(box.z);
  $("#standard-base").checked = box.standard_base !== false;
  $("#standard-walls").checked = box.standard_walls !== false;
  populateWallChoices(box);
  syncWallControls();
  $("#easy-clean").checked = Boolean(box.easy_clean);
  $("#easy-clean-style").value = box.easy_clean_style || "bevel";
  $("#easy-clean-radius").value = fmt(box.easy_clean_radius ?? 2.0);
  $("#base-thickness").value = fmt(box.base_thickness ?? 0.6);
  $("#base-thickness-setting").hidden = $("#standard-base").checked;
  syncEasyCleanControls();
  $("#part-name").value = state.design.part_name || "";
  const scoopEl = $("#scoop");
  if (scoopEl) scoopEl.checked = Boolean(state.design.scoop);
  $("#mode-select").value = layout.mode;
  $("#output-folder").value = state.output;
  const keepLogEl = $("#keep-log");
  if (keepLogEl) keepLogEl.checked = Boolean(state.keepLog);
  $("#connector-tolerance").value = fmt(state.connector.tolerance);
  $("#connector-length").value = fmt(state.connector.length);
  const armThicknessEl = $("#connector-arm-thickness");
  if (armThicknessEl) armThicknessEl.value = fmt(state.connector.arm_thickness ?? 1.0);
  $("#connector-bin-a-height").value = fmt(state.connector.bin_a_height ?? box.z);
  $("#connector-bin-b-height").value = fmt(state.connector.bin_b_height ?? box.z);
  $("#different-height-bins").checked = Boolean(state.connector.different_heights);
  syncConnectorHeightControls();
  syncB4BForm();
  updateInteriorModeVisibility();
  renderPlaced();
}

function autoAdjustConnectorFields() {
  const rules = state.catalog?.connector_rules || {};
  const armT = rules.arm_thickness_mm ?? 1.0;
  const minDrop = rules.min_drop_mm ?? 2.0;
  const fullDrop = rules.full_drop_mm ?? 30.0;
  const webT = rules.web_thickness_mm ?? 3.0;
  const gain = rules.length_gain ?? 0.5;
  const baseLen = 12.0;

  const different = $("#different-height-bins").checked;
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
  const different = $("#different-height-bins").checked;
  $("#connector-bin-heights").hidden = !different;
  const settingsEl = $("#connector-settings");
  if (settingsEl) settingsEl.hidden = !different;
  autoAdjustConnectorFields();
}

function renderConnectorReadout() {
  const el = $("#connector-derived");
  if (el) {
    el.hidden = true;
    el.innerHTML = "";
  }
}

function updateInteriorModeVisibility(reveal = false) {
  const hasSupport = Boolean(state.draft || state.design?.layout?.features?.length);
  if (reveal && !hasSupport && state.design.layout.mode !== "fused") {
    state.design.layout.mode = "fused";
    $("#mode-select").value = "fused";
  }
}

const B4B_DEFAULTS = {
  enabled: false, lid: true, secure_lid: true, latch_count: "auto",
  latch_strength: "standard", lid_headroom_mm: 1, label_text: "",
  label_location: "none", stacking: false,
};

function b4bState() {
  return { ...B4B_DEFAULTS, ...(state.design?.box?.b4b || {}) };
}

function b4bEnabled() {
  return Boolean(state.design?.box?.b4b?.enabled);
}

// A B4B interior is reserved for child bins: hide the interior-parts workflow,
// Easy Clean, the interior print mode and the Connect bins section entirely.
function applyB4BVisibility() {
  const on = b4bEnabled();
  $("#b4b-panel").hidden = !on;
  const hide = (sel, hidden) => { const el = $(sel); if (el) el.hidden = hidden; };
  hide(".subheading-row", on);
  hide(".palette-wrap", on);
  hide(".support-editor", on && !state.draft);
  const modeLabel = $("#mode-select")?.closest("label");
  if (modeLabel) modeLabel.hidden = on;
  const ecRow = $("#easy-clean")?.closest("label");
  if (ecRow) ecRow.hidden = on;
  hide("#easy-clean-style-setting", on || !$("#easy-clean")?.checked);
  hide("#easy-clean-radius-setting", on || !$("#easy-clean")?.checked);
  const connectorSection = document.querySelector('.control-section[data-section="connector"]');
  if (connectorSection) connectorSection.hidden = on;
  hide("#generate-all", on);
  hide("#generate-connector", on);
  const layoutTab = document.querySelector('.view-tab[data-view="2d"]');
  if (layoutTab) layoutTab.hidden = on;
  if (on && document.querySelector('.view-tab[data-view="2d"]')?.classList.contains("active")) {
    document.querySelector('.view-tab[data-view="3d"]')?.click();
  }
  if (on) {
    $("#b4b-lid-options").hidden = !$("#b4b-lid").checked;
    $("#b4b-secure-options").hidden = !($("#b4b-lid").checked && $("#b4b-secure-lid").checked);
  }
}

function syncB4BForm() {
  const b4b = b4bState();
  $("#b4b-enabled").checked = Boolean(b4b.enabled);
  $("#b4b-lid").checked = b4b.lid !== false;
  $("#b4b-secure-lid").checked = b4b.secure_lid !== false;
  $("#b4b-stacking").checked = Boolean(b4b.stacking);
  $("#b4b-lid-snugness").value = String(b4b.lid_headroom_mm ?? 1);
  $("#b4b-latch-count").value = b4b.latch_count || "auto";
  $("#b4b-latch-strength").value = b4b.latch_strength || "standard";
  $("#b4b-label-text").value = b4b.label_text || "";
  $("#b4b-label-location").value = b4b.label_location || "none";
  const topOpt = $("#b4b-label-location").querySelector('option[value="top"]');
  if (topOpt) topOpt.disabled = !$("#b4b-lid").checked;
  applyB4BVisibility();
}

function readB4BForm(design) {
  design.box = design.box || {};
  const enabled = $("#b4b-enabled").checked;
  if (!enabled) {
    if (design.box.b4b) design.box.b4b = { ...B4B_DEFAULTS };
    return;
  }
  const lid = $("#b4b-lid").checked;
  const secure = lid && $("#b4b-secure-lid").checked;
  let location = $("#b4b-label-location").value;
  if (location === "top" && !lid) location = "none";
  design.box.b4b = {
    enabled: true,
    lid,
    secure_lid: secure,
    latch_count: secure ? $("#b4b-latch-count").value : "auto",
    latch_strength: $("#b4b-latch-strength").value,
    lid_headroom_mm: parseFloat($("#b4b-lid-snugness").value) || 1,
    label_text: $("#b4b-label-text").value,
    label_location: location,
    stacking: lid && $("#b4b-stacking").checked,
  };
}

function renderB4BReadout() {
  if (!b4bEnabled()) return;
  const b4b = state.preview?.b4b;
  const capLine = $("#b4b-capacity-line");
  const heightLine = $("#b4b-child-height");
  const grew = $("#b4b-grew");
  const hardware = $("#b4b-hardware");
  if (!b4b) {
    capLine.textContent = "Fits bins totaling — units";
    heightLine.textContent = "Maximum bin height: — mm";
    grew.hidden = true;
    hardware.textContent = "Hardware: —";
    return;
  }
  capLine.textContent = b4b.capacity_text;
  heightLine.textContent = b4b.max_child_height_text;
  if (b4b.grew) {
    grew.hidden = false;
    grew.textContent =
      `Grown to ${b4b.outer_mm[0]} x ${b4b.outer_mm[1]} mm ` +
      `(${b4b.outer_units[0]} x ${b4b.outer_units[1]} units) to fit the interior and hardware.`;
  } else {
    grew.hidden = true;
  }
  if (b4b.secure_lid && b4b.hardware) {
    hardware.textContent =
      `Hardware: ${b4b.hardware.hinge_qty} x ${b4b.hardware.hinge_screw} hinge pins, ` +
      `${b4b.hardware.latch_qty} x ${b4b.hardware.latch_screw} latch pins, no nuts`;
    hardware.hidden = false;
  } else {
    hardware.hidden = true;
  }
}

async function toggleB4B(wantEnabled) {
  if (wantEnabled && state.design?.layout?.features?.length) {
    const ok = window.confirm(
      "Turning on Bin for Bins clears the interior parts - the B4B interior is " +
      "reserved for child bins. Continue?");
    if (!ok) { $("#b4b-enabled").checked = false; return; }
    state.design.layout.features = [];
    state.selected = null;
    state.draft = null;
  }
  if (wantEnabled) {
    state.design.layout.mode = "fused";
    state.design.box.easy_clean = false;
  }
  changedDesign();
}

function updateDesignFromForm() {
  const design = state.design;
  const snapSize = (value, fallback) => {
    const unit = state.catalog.base_unit;
    return Math.max(unit, Math.round(number(value, fallback) / unit) * unit);
  };
  const newBoxX = snapSize($("#x-size").value, design.box.x);
  const newBoxY = snapSize($("#y-size").value, design.box.y);
  design.box.x = newBoxX;
  design.box.y = newBoxY;
  const prevBoxZ = design.box.z;
  design.box.z = number($("#z").value, design.box.z);
  checkBinSizeChange();
  if (design.box.z !== prevBoxZ) {
    const setAutoConnectorHeight = selector => {
      const input = $(selector);
      const next = fmt(design.box.z);
      if (input && input.value !== next) {
        input.value = next;
        flashField(input);
      }
    };
    if (!$("#different-height-bins").checked) {
      setAutoConnectorHeight("#connector-bin-a-height");
      setAutoConnectorHeight("#connector-bin-b-height");
    } else {
      setAutoConnectorHeight("#connector-bin-a-height");
      autoAdjustConnectorFields();
    }
  }
  design.box.base_thickness = number(
    $("#base-thickness").value,
    design.box.base_thickness ?? 0.6,
  );
  design.box.standard_base = $("#standard-base").checked;
  if (design.box.standard_base) design.box.base_thickness = 0.6;
  const previousWall = design.box.wall;
  const wallRules = state.catalog?.wall_rules || {};
  const defaultWall = wallRules.default_mm ?? 0.8;
  const minWall = wallRules.min_mm ?? 0.2;
  const maxWall = wallRules.max_mm ?? 2.4;
  design.box.standard_walls = $("#standard-walls").checked;
  design.box.wall = design.box.standard_walls
    ? defaultWall
    : Math.max(minWall, Math.min(maxWall, number(
        $("#wall-thickness").value,
        design.box.wall ?? defaultWall,
      )));
  $("#wall-thickness").value = fmt(design.box.wall);
  if (design.box.wall !== previousWall) autoAdjustConnectorFields();
  design.box.easy_clean = $("#easy-clean").checked;
  design.box.easy_clean_style = ($("#easy-clean-style") && $("#easy-clean-style").value) || "bevel";
  if (design.layout?.mode !== "fused" && design.box.easy_clean_style === "curve") {
    design.box.easy_clean_style = "bevel";
  }
  design.box.easy_clean_radius = number(
    $("#easy-clean-radius").value,
    design.box.easy_clean_radius ?? 2.0,
  );
  design.part_name = $("#part-name").value;
  const scoopEl = $("#scoop");
  if (scoopEl) design.scoop = scoopEl.checked;
  syncRimLabelFromFeatures();
  const newOutput = $("#output-folder").value.trim();
  if (newOutput !== state.output) {
    state.output = newOutput;
    saveOutputPreference(newOutput);
  }
  const keepLogEl = $("#keep-log");
  if (keepLogEl) {
    const newKeepLog = keepLogEl.checked;
    if (newKeepLog !== state.keepLog) {
      state.keepLog = newKeepLog;
      api("/api/preferences", { keep_log: newKeepLog }).catch(() => {});
    }
  }
  state.connector = {
    tolerance: number($("#connector-tolerance").value, state.connector.tolerance),
    length: number($("#connector-length").value, state.connector.length),
    arm_thickness: number($("#connector-arm-thickness")?.value, state.connector.arm_thickness ?? 1.0),
    height: state.connector.height,
    bin_a_height: number($("#connector-bin-a-height").value, state.design.box.z),
    bin_b_height: number($("#connector-bin-b-height").value, state.design.box.z),
    different_heights: $("#different-height-bins").checked,
    position: 0,
    axis: "y",
  };
  readB4BForm(design);
  applyB4BVisibility();
}

const saveOutputPreference = debounce(output => {
  api("/api/preferences", { output }).catch(() => {});
}, 500);

let isSelectingFolder = false;
async function selectOutputFolder() {
  if (isSelectingFolder) return;
  isSelectingFolder = true;
  const input = $("#output-folder");
  const button = $("#output-folder-picker");
  if (button) button.disabled = true;
  if (input) input.style.pointerEvents = "none";
  try {
    const result = await api("/api/browse-output-folder", { current: state.output });
    if (result.folder) {
      state.output = result.folder;
      if (input) input.value = result.folder;
      saveOutputPreference(result.folder);
      toast(`Selected: ${result.folder}`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    if (button) button.disabled = false;
    if (input) input.style.pointerEvents = "";
    isSelectingFolder = false;
  }
}

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
  if (state.nudgeFeedback) {
    el.innerHTML = `<strong>Moved ${state.nudgeFeedback.amount}</strong> &nbsp;·&nbsp; Arrow: 1 mm | Shift: 10 mm | Ctrl: 0.1 mm`;
  } else {
    el.textContent = "Use Arrow keys or drag to move";
  }
}

function updatePreviewHelp(view) {
  const el = $("#preview-help");
  if (!el) return;
  el.textContent = view === "2d"
    ? "Drag a Snug Holder outline point to reshape it. Drag inside to move; use the square to resize and circle to rotate."
    : "Drag to rotate, use the wheel to zoom, or double-click to reset.";
}

let pendingDesignHistory = null;
const applyChangedDesign = debounce(() => {
  if (state.designMutationBusy) {
    pendingDesignHistory = null;
    return;
  }
  const previousDesign = pendingDesignHistory || clone(state.design);
  pendingDesignHistory = null;
  updateDesignFromForm();
  recordHistory(previousDesign);
  // Re-fit contents-driven drafts after the bin changes. Arbitrarily sized
  // parts keep the size the user chose; if the bin was made too small, the
  // automatic grow pass below restores enough room instead of trimming them.
  reflowDraftToBin(state.draft);
  refreshPreview();
  if (state.draft) refreshDraft();
  if (state.binResizePending &&
      (state.draft || state.design.layout.features.length)) {
    enforceBinMinimumSoon();
  }
  state.binResizePending = false;
}, 280);

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
}

let pendingNudgeHistory = null;
const commitNudge = debounce(async () => {
  if (state.selected === null || !state.draft) {
    pendingNudgeHistory = null;
    return;
  }
  const historySnapshot = pendingNudgeHistory || clone(state.design);
  pendingNudgeHistory = null;
  const index = state.selected;
  try {
    const result = await api("/api/feature/apply", {
      design: state.design,
      feature: state.draft,
      index,
    });
    state.design = result.design;
    recordHistory(historySnapshot);
    state.selected = result.selected;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshPreview();
    refreshDraft();
    renderLayout2D();
  } catch (error) {
    toast(error.message, true, 5000);
    if (state.design?.layout?.features?.[index]) {
      state.draft = clone(state.design.layout.features[index]);
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
  input.value = `${fmt(val)}mm (${inside} inside)`;
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

function setPreviewMode(mode) {
  state.previewMode = mode;
  $$('[data-preview-mode]').forEach(button => button.classList.toggle("active", button.dataset.previewMode === mode));
  renderPreview3D();
}

function wireCameraControls() {
  $$('[data-camera-view]').forEach(button => button.addEventListener("click", () => setCameraView(button.dataset.cameraView)));
  $$('[data-preview-mode]').forEach(button => button.addEventListener("click", () => setPreviewMode(button.dataset.previewMode)));
  $$('[data-camera-zoom]').forEach(button => button.addEventListener("click", () => {
    state.camera.zoom = Math.max(.35, Math.min(4, state.camera.zoom * (button.dataset.cameraZoom === "in" ? 1.2 : 1 / 1.2)));
    renderPreview3D();
  }));
}

function setLayoutOrientation(orientation) {
  state.layoutOrientation = orientation;
  $$('[data-layout-orientation]').forEach(button =>
    button.classList.toggle("active", button.dataset.layoutOrientation === orientation));
  renderLayout2D();
}

function activatePreviewView(view) {
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
  if (view === "2d") updateNudgeUI();
  requestAnimationFrame(() => view === "3d" ? renderPreview3D() : renderLayout2D());
}

function wireControls() {
  wireSidebar();
  wireCameraControls();
  $$('[data-layout-orientation]').forEach(button =>
    button.addEventListener("click", () => setLayoutOrientation(button.dataset.layoutOrientation)));
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
        syncWallControls();
      }
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign();
    }));
  $("#standard-base").addEventListener("change", () => {
    const isStandard = $("#standard-base").checked;
    $("#base-thickness-setting").hidden = isStandard;
    if (!isStandard) {
      if (!$("#base-thickness").value) {
        $("#base-thickness").value = fmt(state.design?.box?.base_thickness ?? 0.6);
      }
    } else {
      $("#base-thickness").value = "0.6";
    }
    changedDesign();
  });
  $("#standard-walls").addEventListener("change", () => {
    const isStandard = $("#standard-walls").checked;
    const rules = state.catalog?.wall_rules || {};
    const select = $("#wall-thickness");
    const defaultValue = fmt(rules.default_mm ?? 0.8);
    if (isStandard) {
      if (select.value && select.value !== defaultValue) {
        select.dataset.customValue = select.value;
      }
      select.value = defaultValue;
    } else if (
      select.dataset.customValue
      && [...select.options].some(option => option.value === select.dataset.customValue)
    ) {
      select.value = select.dataset.customValue;
    } else if (!select.value) {
      select.value = fmt(state.design?.box?.wall ?? rules.default_mm ?? 0.8);
    }
    syncWallControls();
    state.binResizePending = true;
    changedDesign();
  });
  $("#easy-clean").addEventListener("change", () => {
    syncEasyCleanControls();
    changedDesign();
  });
  const cleanStyleEl = $("#easy-clean-style");
  if (cleanStyleEl) {
    cleanStyleEl.addEventListener("change", () => {
      syncEasyCleanControls();
      changedDesign();
    });
  }
  $("#easy-clean-radius").addEventListener("input", changedDesign);

  $("#b4b-enabled").addEventListener("change", () => toggleB4B($("#b4b-enabled").checked));
  ["#b4b-lid", "#b4b-secure-lid", "#b4b-stacking"].forEach(sel =>
    $(sel).addEventListener("change", () => { syncB4BForm(); changedDesign(); }));
  ["#b4b-lid-snugness", "#b4b-latch-count", "#b4b-latch-strength", "#b4b-label-location"]
    .forEach(sel => $(sel).addEventListener("change", changedDesign));
  $("#b4b-label-text").addEventListener("input", () => {
    state.canGenerate = false; updateGenerateAvailability(); changedDesign();
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
      const snapped = Math.max(unit, Math.round(rawVal / unit) * unit);
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
        const next = Math.max(unit, Math.round((current + delta) / unit) * unit);
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
      const next = Math.max(unit, Math.round((current + delta) / unit) * unit);
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
  $("#scoop")?.addEventListener("change", () => {
    const previousDesign = clone(state.design);
    updateDesignFromForm();
    recordHistory(previousDesign);
    refreshPreview();
    if (state.draft) refreshDraft();
  });
  ["#output-folder", "#keep-log", "#connector-tolerance", "#connector-length",
    "#connector-arm-thickness", "#connector-bin-a-height", "#connector-bin-b-height"]
    .forEach(selector => $(selector)?.addEventListener("change", updateDesignFromForm));
  ["#connector-bin-a-height", "#connector-bin-b-height"].forEach(selector => {
    $(selector)?.addEventListener("input", () => {
      autoAdjustConnectorFields();
      updateDesignFromForm();
    });
  });
  $("#different-height-bins").addEventListener("change", () => {
    if ($("#different-height-bins").checked) {
      $("#connector-bin-a-height").value = fmt(state.design.box.z);
      if (!Number.isFinite(number($("#connector-bin-b-height").value, NaN))) {
        $("#connector-bin-b-height").value = fmt(state.design.box.z);
      }
    }
    syncConnectorHeightControls();
    updateDesignFromForm();
  });
  const outputFolderEl = $("#output-folder");
  if (outputFolderEl) {
    outputFolderEl.addEventListener("click", selectOutputFolder);
    outputFolderEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selectOutputFolder();
      }
    });
  }
  $('label[for="output-folder"]')?.addEventListener("click", (e) => {
    e.preventDefault();
    selectOutputFolder();
  });
  $("#output-folder-picker")?.addEventListener("click", selectOutputFolder);
  $("#show-log-button")?.addEventListener("click", showLog);

  const viewTabs = $$(".view-tab");
  viewTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activatePreviewView(tab.dataset.view));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0
        : event.key === "End" ? viewTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      activatePreviewView(viewTabs[targetIndex].dataset.view);
      viewTabs[targetIndex].focus();
    });
  });
  activatePreviewView((viewTabs.find(tab => tab.classList.contains("active")) || viewTabs[0]).dataset.view);

  // Editing a part: "Save Part" finalises it and returns to the 10-part
  // palette; "Delete Part" removes the part being edited and does the same.
  $("#save-part").addEventListener("click", saveCurrentPart);
  $("#delete-part").addEventListener("click", deleteCurrentPart);
  $("#save-design").addEventListener("click", saveDesign);
  $("#open-design").addEventListener("change", openDesign);
  $("#new-design").addEventListener("click", newDesign);
  $("#undo-design").addEventListener("click", () => restoreHistory());
  $("#redo-design").addEventListener("click", () => restoreHistory(true));
  document.addEventListener("keydown", event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (event.target.closest("input, textarea, select, [contenteditable='true']")) return;
    const isZ = event.key.toLowerCase() === "z" || event.code === "KeyZ";
    const isY = event.key.toLowerCase() === "y" || event.code === "KeyY";
    if (isZ) {
      event.preventDefault();
      restoreHistory(event.shiftKey);
    } else if (isY) {
      event.preventDefault();
      restoreHistory(true);
    }
  });
  window.addEventListener("beforeunload", event => {
    if (!state.design || !designHasChanges()) return;
    event.preventDefault();
    event.returnValue = "";
  });
  $("#connection").addEventListener("click", () => location.reload(true));
  $("#update-banner-reload").addEventListener("click", () => location.reload(true));
  $("#print-bin").addEventListener("click", () => printModel("bin"));
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
  state.kindRequest += 1;
  state.fitRequest += 1;
  state.nestPhotoRequest += 1;
  state.draftRequest += 1;
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
  state.draft = null;
  state.draftKind = null;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.draftTouched = false;
  state.pinnedZone = {};
  if (resetLocks) state.partZoneLocks = {};
  state.selected = null;
  state.nudgeFeedback = null;
  updateNudgeUI();
  $$(".support-choice").forEach(button => button.classList.remove("active"));
  $(".support-editor").hidden = true;
  $("#draft-status").textContent = "";
  $("#draft-status").classList.remove("error");
  updateDraftStatusColor(null);
  updateInteriorModeVisibility();
  updateSelectionButtons();
}

function pickKind(kind) {
  state.paletteBrowsing = false;
  updateInteriorModeVisibility(true);
  selectKind(kind);
}

async function selectKind(kind, reset = false) {
  // Re-picking the shape already open keeps the same draft, so there is nothing
  // to lose - skip the guard in that case. Anything else replaces the draft, so
  // give the user the chance to keep unsaved work first.
  const keepsSameDraft = !reset && state.draft?.kind === kind;
  if (!keepsSameDraft && !(await guardDraftSwitch())) return;
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
  $("#draft-title").textContent = info.title;
  $("#draft-description").textContent = info.description;
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
    state.draft = result.feature;
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
  cancelPendingDraftWork();
  state.paletteBrowsing = false;
  state.selected = index;
  state.nudgeFeedback = null;
  updateNudgeUI();
  state.draft = clone(state.design.layout.features[index]);
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
  $("#draft-title").textContent = info.title;
  $("#draft-description").textContent = info.description;
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
  return `<label class="${classes}"${tip}>${escapeHtml(label)}${options.unit ? `<span class="unit">${escapeHtml(options.unit)}</span>` : ""}
    <input type="${type}" ${data} value="${escapeHtml(value ?? "")}" ${attrs}${min}${max}${placeholder}>
  </label>`;
}

function scoopDepthField(key, value, options = {}) {
  return field("Depth", key, value, {
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

function textPlacementFields(levelKey, sideKey, level, side = "back") {
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
  }
  return `<div class="pair">${html}</div>`;
}

function dividerScoopDefaultDepth() {
  const scoop = partInfo("scoop");
  return scoop?.fields?.find(field => field.key === "depth")?.default ?? "";
}

function renderDraftFields() {
  if (!state.draft) return;
  const info = partInfo();
  const one = state.draft;
  const zone = one.zone;
  const width = zone[2] - zone[0];
  const depth = zone[3] - zone[1];
  // The bore editor carries its own "Base" / "Hole" headings, so the grey
  // panel blurb just wastes space there.
  const descEl = $("#draft-description");
  if (descEl) descEl.hidden = one.kind === "bore";
  let html = "";
  // Keys pulled up into the "Repeats" cluster, so the body loop skips them.
  const repeatKeys = new Set();
  if (one.kind === "scoop") {
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, "depth");
    const shown = explicit ? one.options.depth : state.draftResolvedOptions?.depth ?? 60;
    html += scoopDepthField("option:depth", shown);
  }
  if (one.kind === "nest") {
    const assist = String(one.options?.lift_assist ?? state.draftResolvedOptions?.lift_assist ?? "finger_grasp");
    const fingerPosition = String(one.options?.finger_position ?? state.draftResolvedOptions?.finger_position ?? "sides");
    const pushPosition = String(one.options?.push_position ?? state.draftResolvedOptions?.push_position ?? "right");
    const selected = (value, actual) => value === actual ? "selected" : "";
    const liftAssist = `<label>Lift assist
      <select data-draft="option:lift_assist">
        <option value="finger_grasp" ${selected("finger_grasp", assist)}>Finger grasp</option>
        <option value="push_out" ${selected("push_out", assist)}>Push Out</option>
        <option value="none" ${selected("none", assist)}>No assist</option>
      </select>
    </label>`;
    html += `<div class="draft-triple">`;
    html += field("Object thickness", "option:depth",
      fmt(one.options?.depth ?? state.draftResolvedOptions?.depth ?? 8),
      { unit: "mm", step: "0.5", min: "0.5" });
    html += field("Fit clearance", "option:clearance",
      fmt(one.options?.clearance ?? state.draftResolvedOptions?.clearance ?? 0.6), { unit: "mm", step: "0.1", min: "0" });
    html += field("Soften outline", "option:smoothing",
      fmt(one.options?.smoothing ?? state.draftResolvedOptions?.smoothing ?? 0), { step: "1", min: "0" });
    html += `</div>`;
    if (assist === "finger_grasp") {
      html += `<div class="draft-triple">${liftAssist}<label>Finger grasps
        <select data-draft="option:finger_position">
          <option value="sides" ${selected("sides", fingerPosition)}>Sides (left/right)</option>
          <option value="top_bottom" ${selected("top_bottom", fingerPosition)}>Top/bottom</option>
          <option value="both" ${selected("both", fingerPosition)}>Both</option>
        </select>
      </label>`;
      html += field(
        "Finger opening width", "option:finger_width",
        fmt(one.options?.finger_width ?? state.draftResolvedOptions?.finger_width ?? 25),
        { unit: "mm", step: "1", min: "12", max: "40",
          tip: "The openings rotate with the photographed outline. Their edges curve gently down into the grasp instead of ending in a sharp corner." },
      );
      html += `</div>`;
    } else if (assist === "push_out") {
      html += `<div class="draft-triple">${liftAssist}`;
      html += `<label>Push at
        <select data-draft="option:push_position">
          <option value="right" ${selected("right", pushPosition)}>Right</option>
          <option value="left" ${selected("left", pushPosition)}>Left</option>
          <option value="top" ${selected("top", pushPosition)}>Top</option>
          <option value="bottom" ${selected("bottom", pushPosition)}>Bottom</option>
        </select>
      </label>`;
      html += field(
        "Push area", "option:push_area",
        fmt(one.options?.push_area ?? state.draftResolvedOptions?.push_area ?? 30),
        { unit: "%", step: "5", min: "15", max: "40" },
      );
      html += field(
        "Push depth", "option:push_depth",
        fmt(one.options?.push_depth ?? state.draftResolvedOptions?.push_depth ?? 4),
        { unit: "mm", step: "0.5", min: "2", max: "8",
          tip: "Most of the tool rests on a raised floor. Press the selected end into the lower area to lift the opposite end." },
      );
      html += `</div>`;
    } else {
      html += liftAssist;
    }
    html += `<div class="photo-upload wide">
      <label class="button secondary photo-button" for="nest-photo-input">Upload part photo</label>
      <input id="nest-photo-input" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp">
      <details><summary>Photo requirements</summary><ul>
        <li>Entire 8.5 × 11 in sheet visible</li>
        <li>Camera directly overhead</li>
        <li>Part lies flat</li>
        <li>Plain, high-contrast background preferred</li>
      </ul></details>
      ${one.contour ? `<p class="photo-measurement">Outline ready — drag its points over the photo in 2D to reshape it.</p>` : ""}
    </div>`;
  }
  if (info.flags.text) {
    const textLevel = one.options?.level === "rim" ? "rim" : "base";
    html += textPlacementFields(
      "option:level", "option:rim_side", textLevel, one.options?.rim_side,
    );
    html += `<label class="wide">What it says
      <input type="text" maxlength="80" data-draft="option:text" value="${escapeHtml(one.options?.text ?? "")}" placeholder="${textLevel === "rim" ? "e.g. M3 BOLTS" : "e.g. M3"}">
    </label>`;
    if (textLevel === "base") {
      const capShown = one.options?.cap_height ?? state.draftResolvedOptions?.cap_height ?? "";
      const depthShown = one.options?.depth ?? state.draftResolvedOptions?.depth ?? 0.4;
      html += field("Letter height", "option:cap_height", capShown === "" ? "" : fmt(capShown), { unit: "mm", step: "0.5" });
      html += field("Depth", "option:depth", fmt(depthShown), { unit: "mm", step: "0.1" });
      html += `<fieldset class="wide"><legend>Turn</legend><div class="segmented four">
        ${[0, 1, 2, 3].map(turn => `<label><input type="radio" name="draft-turns" value="${turn}" ${(number(one.options?.quarter_turns, 0) % 4) === turn ? "checked" : ""}><span>${turn * 90}°</span></label>`).join("")}
      </div></fieldset>`;
      html += `<div class="toggle-grid">`;
      html += toggle("option:auto", "Place it for me",
        "Keeps it centred where it fits, moving around the other interior parts as they change. Turn this off to put it exactly where you want.",
        one.options?.auto === true);
      html += toggle("option:raised", "Stand proud",
        "Letters sit on top of the floor instead of sunk flush into it. Either way they stay a separate object for a second filament.",
        one.options?.raised === true);
      html += `</div>`;
    }
  }
  if (info.flags.size && one.kind !== "cradle" && !(one.kind === "text" && one.options?.level === "rim")) {
    const isPocket = one.kind === "pocket";
    const isBore = one.kind === "bore";
    const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
    const shownWidth = isPocket ? Math.max(0.1, width - 2 * wall) : width;
    const shownDepth = isPocket ? Math.max(0.1, depth - 2 * wall) : depth;
    // A bore's footprint reads Width x Length, matching Pocket and the item terms.
    // Slot and base Text each also carry their own "Depth" field (slot cut / letter
    // sink), so the footprint dimension is named apart to avoid two "Depth" boxes.
    const depthLabel = isPocket || isBore ? "Length"
      : one.kind === "slot" ? "Footprint depth"
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
      // X / Y counts show the fitter's current count until the user edits one.
      const gridField = (key, label) => {
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        return field(label, `option:${key}`, explicit ? one.options[key]
          : state.draftResolvedOptions?.[key] ?? 1, {
          step: "1", min: "1",
        });
      };
      // Diameter is locked to the preset for a hex-bit profile.
      const diameterField = hexBit
        ? `<label>Diameter<span class="unit">mm</span>
            <input type="number" value="${HEX_BIT_PROFILES[draftProfile].diameter}" disabled></label>`
        : field("Diameter", "item_diameter", fmt(boreFirst.diameter), { unit: "mm" });
      const boreProfiles = [
        ["round", "Round"], ["hex", "Hex"], ["square", "Square"],
        ["hex_bit_short", HEX_BIT_PROFILES.hex_bit_short.label],
        ["hex_bit_long", HEX_BIT_PROFILES.hex_bit_long.label],
      ];
      const shapeField = `<label>Shape<select data-draft="profile">
        ${boreProfiles.map(([value, label]) => `<option value="${value}" ${draftProfile === value ? "selected" : ""}>${label}</option>`).join("")}
      </select></label>`;

      // Base: the solid block the holes are cut into - its size and the hole
      // grid that fills it (X / Y counts drive the same footprint as Width /
      // Length, so they belong together).
      html += `<div class="bore-group wide">
        <span class="bore-group-label">Base</span>
        <div class="bore-group-fields">
          ${field("Width", "width", fmt(shownWidth), { unit: "mm", step: "1" })}
          ${field("Length", "depth", fmt(shownDepth), { unit: "mm", step: "1" })}
          ${optionField("height", "Height", { unit: "mm", step: "0.5" })}
          ${gridField("columns", "X Qty")}
          ${gridField("rows", "Y Qty")}
        </div>
      </div>`;

      // Hole: everything about the holes cut into that block.
      html += `<div class="bore-group wide">
        <span class="bore-group-label">Hole</span>
        <div class="bore-group-fields bore-hole-fields">
          ${diameterField}
          ${shapeField}
          ${optionField("depth", "Depth", { unit: "mm", step: "0.5" })}
          ${optionField("wall", "Wall", { unit: "mm", step: "0.5" })}
          ${hexBit ? "" : optionField("angle", "Angle", { step: "1", min: "20", max: "90", transform: value => 90 - number(value, 0) })}
          ${hexBit || number(one.options?.angle ?? state.draftResolvedOptions?.angle, 0) <= 1e-9 ? "" : `<label>Angle towards<select data-draft="option:angle_towards">
            ${[["back", "Back"], ["front", "Front"], ["left", "Left"], ["right", "Right"]].map(([value, label]) => `<option value="${value}" ${(one.options?.angle_towards || (one.along === "y" ? "front" : "left")) === value ? "selected" : ""}>${label}</option>`).join("")}
          </select></label>`}
        </div>
      </div>`;
    } else {
      html += field("Width", "width", fmt(shownWidth), { unit: "mm", step: "1" });
      html += field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" });
    }
  }
  // Repeats: how many, how far apart, which way they run - one cluster, in
  // reading order, instead of Quantity / spacing / Runs along scattered apart.
  if (info.flags.qty || info.flags.along) {
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
      html += `<label title="Walls dividing the bin left to right (across X). 0 for none.">Qty X<input type="number" min="0" step="1" data-draft="option:count_x" value="${gx}" placeholder="0"></label>
        <label title="Walls dividing the bin front to back (across Y). 0 for none.">Qty Y<input type="number" min="0" step="1" data-draft="option:count_y" value="${gy}" placeholder="0"></label>`;
    } else {
      html += `<div class="editor-group"><span class="editor-group-label">${info.flags.qty ? "Repeats" : "Orientation"}</span>`;
      if (info.flags.qty) {
        html += `<div class="pair"><label>Quantity<div class="input-with-button">
          <input type="number" min="1" step="1" data-draft="count" value="${resolvedDraftCount(one)}">
          ${["cradle", "slot"].includes(info.kind) ? "" : `<button type="button" class="button secondary" data-action="auto-count">Auto</button>`}
        </div></label>${repeatFieldsHtml}</div>`;
        if (info.kind === "cradle") {
          const item = one.item || starterItem();
          const first = item.segments[0] || { length: 40, diameter: 6 };
          const tip = "Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool.";
          html += `<div class="pair">${field("Length", "item_length", fmt(first.length), { unit: "mm", step: "1", tip })}${field("Diameter", "item_diameter", fmt(first.diameter), { unit: "mm", step: "1", tip })}</div>`;
        }
      } else if (repeatFieldsHtml) {
        html += `<div class="pair">${repeatFieldsHtml}</div>`;
      }
      if (info.flags.alternate) {
        html += toggle("alternate_ends", "Alternate ends",
          "Places every second trough near the opposite end of the bin; each trough becomes a separate body.",
          one.alternate_ends === true, { wide: true });
      }
      if (info.flags.along && !["divider", "bore"].includes(info.kind)) {
        html += `<fieldset><legend>Runs along</legend><div class="segmented two">
          <label><input type="radio" name="draft-along" value="x" ${one.along === "x" ? "checked" : ""}><span>X direction</span></label>
          <label><input type="radio" name="draft-along" value="y" ${one.along === "y" ? "checked" : ""}><span>Y direction</span></label>
        </div></fieldset>`;
      }
      if (info.flags.alternate && (info.kind !== "cradle" || one.alternate_ends === true)) {
        // One field, two readings. Alternate ends on: the clearance kept at each
        // run end (writes end_margin). Off: a signed slide of the whole row along
        // the bin (writes run_offset). Each key keeps its own last value.
        const alternating = one.alternate_ends === true;
        const key = alternating ? "end_margin" : "run_offset";
        const label = alternating ? "% from end" : "Offset from center";
        const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, key);
        const shown = explicit
          ? one.options[key]
          : alternating
          ? state.draftResolvedOptions?.end_margin ?? 10
          : 0;
        const tip = alternating
          ? "Share of the run kept clear at each end. Larger pulls the alternating troughs toward the middle; smaller pushes them to the ends."
          : "Slides the trough along the bin from centre, as a share of the room to the wall. Positive one way, negative the other; 0 stays centred.";
        html += field(label, `option:${key}`, fmt(shown), { step: "1", tip });
      }
      html += `</div>`;
    }
  }
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
    // under "What it says".
    if (info.kind === "nest" && (option.key === "clearance" || option.key === "smoothing")) continue;
    if (info.kind === "text" && (option.key === "cap_height" || option.key === "depth")) continue;
    // Rendered by the divider bottom-slope block below, on its own and only
    // while Use support crossbars is ticked.
    if (option.key === "bottom_supports") continue;
    // Slope and angle are handled specifically for divider below.
    if (info.kind === "divider" && (option.key === "bottom_angle" || option.key === "angle")) continue;
    // The scoop depth field is rendered with its own % unit and help text above.
    if (info.kind === "scoop") continue;
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
    const shown = explicit ? one.options[option.key]
      : state.draftResolvedOptions?.[option.key] ?? option.default;
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
    bodyHtml += field(option.label, `option:${option.key}`, shown, fieldOpts);
  }
  // Three-across for the kinds whose leftover body fields would otherwise leave
  // a half-empty row (matches the Width / Length / Height row at the top).
  if (bodyHtml) {
    html += ["post", "pocket", "slot"].includes(info.kind)
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

    html += plainCheckbox("option:slope_base", "Slope base", hasSlope, {
      wide: true,
      help: "Tilts the tool-slot bottoms so tools rest at an angle instead of flat.",
    });

    if (hasSlope) {
      const explicitAngle = Object.prototype.hasOwnProperty.call(opt, "bottom_angle");
      const angleVal = explicitAngle ? opt.bottom_angle : (number(state.draftResolvedOptions?.bottom_angle, 0) || 20);
      const angleNum = number(angleVal, 0);
      const useBars = angleNum !== 0 && opt.minimal_bottom === true;
      html += `<div class="pair divider-slope-options"><div class="divider-slope-fields">`;
      html += field("Degree °", "option:bottom_angle", angleVal, { step: "1" });
      if (angleNum !== 0) {
        if (useBars) {
          const explicitBars = Object.prototype.hasOwnProperty.call(opt, "bottom_supports");
          const bars = explicitBars
            ? opt.bottom_supports
            : state.draftResolvedOptions?.bottom_supports ?? 3;
          html += field("Number of crossbars", "option:bottom_supports", bars, { step: "1" });
        }
      }
      html += `</div><div class="divider-slope-toggles">`;
      html += toggle("option:alternate_bottom", "Alternate slopes",
        "Reverses every second tool slot.", opt.alternate_bottom === true);
      if (angleNum !== 0) {
        const barsHelp = "A few thin bars hung off the walls at the tool line instead of a solid slope.";
        html += toggle("option:minimal_bottom", "Use support crossbars", barsHelp, useBars);
      }
      html += `</div></div>`;
    }

    html += plainCheckbox("enabled", "Curved scoop", Boolean(scoopConfig), {
      wide: true,
      dataAttribute: "data-divider-scoop-enabled",
      help: "Adds the same curved Scoop used by the standalone Scoop part to every Divider compartment.",
    });
    if (scoopConfig) {
      const scoopDepth = Object.prototype.hasOwnProperty.call(scoopConfig, "depth")
        ? scoopConfig.depth : dividerScoopDefaultDepth();
      html += scoopDepthField("depth", scoopDepth, {
        dataAttribute: "data-divider-scoop-depth",
        tip: "Every Divider compartment gets the same Scoop depth and starts at its front floor edge.",
      });
    }

    const hasLabels = opt.label_divisions === true;
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

      html += `<table class="division-table division-grid">`;
      for (let r = 0; r < nRows; r++) {
        html += `<tr>`;
        for (let c = 0; c < nCols; c++) {
          const idx = r * nCols + c;
          const val = escapeHtml(String(divLabels[idx] || ""));
          html += `<td><input type="text" data-division-index="${idx}" value="${val}"></td>`;
        }
        html += `</tr>`;
      }
      html += `</table>`;
    }
  }
  // The auto-size buttons sit at the very bottom of the editor.
  if (!(one.kind === "text" && one.options?.level === "rim")) {
    html += renderFitActions(one);
  }
  $("#draft-fields").innerHTML = html;
  const photoInput = $("#nest-photo-input", $("#draft-fields"));
  if (photoInput) photoInput.addEventListener("change", uploadNestPhoto);
  $$('[data-draft]', $("#draft-fields")).forEach(input => {
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", updateDraftFromFields);
  });
  const dividerAngle = $('[data-draft="option:bottom_angle"]', $("#draft-fields"));
  if (dividerAngle) dividerAngle.addEventListener("focus", () => dividerAngle.select());
  $$('input[data-division-index]', $("#draft-fields")).forEach(input => input.addEventListener("input", () => {
    markDraftChanged();
    state.draft.options ||= {};
    let labels = Array.isArray(state.draft.options.division_labels) ? [...state.draft.options.division_labels] : [];
    const idx = parseInt(input.dataset.divisionIndex, 10);
    labels[idx] = input.value;
    state.draft.options.division_labels = labels;
    renderLayout2D();
    refreshDraftSoon();
  }));
  const dividerScoopEnabled = $('[data-divider-scoop-enabled]', $("#draft-fields"));
  if (dividerScoopEnabled) dividerScoopEnabled.addEventListener("change", () => {
    markDraftChanged();
    state.draft.options ||= {};
    if (dividerScoopEnabled.checked) {
      state.draft.options.scoop = {};
      for (const key of ["slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom", "minimal_bottom", "bottom_supports"]) {
        delete state.draft.options[key];
      }
    } else delete state.draft.options.scoop;
    state.draftAutoCommit = true;
    renderDraftFields();
    renderLayout2D();
    refreshDraftSoon();
  });
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
  const autoCount = $('[data-action="auto-count"]', $("#draft-fields"));
  if (autoCount) autoCount.addEventListener("click", () => {
    markDraftChanged();
    state.draft.count = null;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    const input = $('[data-draft="count"]', $("#draft-fields"));
    if (input) {
      input.value = String(resolvedDraftCount(state.draft));
      flashField(input);
    }
    syncCountAutoHint();
    updateSelectionButtons();
    refreshDraftSoon();
  });
  // The three per-part auto-size buttons (see renderFitActions).
  const fitBtn = $('[data-action="fit-part"]', $("#draft-fields"));
  if (fitBtn) fitBtn.addEventListener("click", fitPartToContents);
  const fillBtn = $('[data-action="fill-part"]', $("#draft-fields"));
  if (fillBtn) fillBtn.addEventListener("click", fillPartToBin);
  const growBtn = $('[data-action="grow-bin"]', $("#draft-fields"));
  if (growBtn) growBtn.addEventListener("click", autoExpandBin);
  updateFitActions();
  // Bore: "Auto" beside an X / Y quantity hands that count back to the fitter.
  $$('[data-action="auto-option"]', $("#draft-fields")).forEach(button => button.addEventListener("click", () => {
    markDraftChanged();
    const key = button.dataset.key;
    if (state.draft.options) delete state.draft.options[key];
    const input = $(`[data-draft="option:${key}"]`, $("#draft-fields"));
    if (input) {
      input.value = fmt(state.draftResolvedOptions?.[key] ?? 1);
      flashField(input);
    }
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
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
function sizeBoreToGrid(one) {
  if (one.kind !== "bore") return;
  const opts = one.options || {};
  const resolved = state.draftResolvedOptions || {};
  const profile = one.item?.profile || "round";
  const hexBit = isHexBitProfile(profile);
  const diameter = hexBit
    ? HEX_BIT_PROFILES[profile].diameter
    : number(one.item?.segments?.[0]?.diameter, 6);
  const held = diameter + 0.25;
  const angle = hexBit ? 0 : Math.min(70, Math.max(0, number(opts.angle ?? resolved.angle, 0)));
  // A leaned bore defaults to a thicker wall (engine: BORE_TILTED_WALL) unless
  // Wall was hand-set - match that so the block sizing tracks the real pitch.
  const wall = opts.wall !== undefined ? number(opts.wall) : (angle > 0 ? 3 : 1.6);
  const sides = profile === "round" ? 48 : profile === "square" ? 4 : 6;
  const holeRadius = held / 2 / (sides < 8 ? Math.cos(Math.PI / sides) : 1);
  const crossPitch = 2 * holeRadius + wall;
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
  const axisSpan = (count, axis) => {
    const pitch = along === axis ? leanPitch : crossPitch;
    return Math.ceil(count * pitch + (along === axis ? reach : 0) - 1e-6);
  };
  // An unset quantity means one hole, not “fill the existing Base.” Changing
  // X/Y, hole diameter, Wall, depth, or lean grows the Base to its exact need.
  const resolveAxis = (countKey, cur, pinKey, leanAxis) => {
    const count = Math.max(1, Math.round(number(opts[countKey] ?? resolved[countKey], 1)));
    const minimum = axisSpan(count, leanAxis);
    return state.pinnedZone[pinKey] ? Math.max(cur, minimum) : minimum;
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
  const ncx = place(leanTarget(cx, "x"), width, insideX);
  const ncy = place(leanTarget(cy, "y"), depth, insideY);
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
  const acrossNeeded = Math.ceil((count - 1) * pitch + thickness / cosA + 2 * wall - 1e-6);
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

function syncNestZone(one) {
  if (!one?.contour?.length) return;
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  // The server owns the exact outline calculation: it includes smoothing and
  // the reinforced outside foot. Keep only a valid centre placeholder here;
  // /api/feature/apply refits the authoritative footprint before saving.
  one.zone = [cx - .5, cy - .5, cx + .5, cy + .5];
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
  state.nestPhoto = { image, bounds: reference.bounds.map(value => number(value)) };
  image.addEventListener("load", renderLayout2D, { once: true });
  image.addEventListener("error", () => { state.nestPhoto = null; }, { once: true });
  image.src = reference.image;
}

async function uploadNestPhoto(event) {
  const file = event.target.files?.[0];
  if (!file) return;
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
  const input = event.target;
  const draft = state.draft;
  const request = ++state.nestPhotoRequest;
  let mutationStarted = false;
  $("#draft-status").textContent = "Finding letter paper and tracing the part…";
  try {
    const image = await readFileDataUrl(file);
    // The file picker stays open while the browser reads it. If the user
    // chose another palette part meanwhile, never let this old photo replace
    // that newer design choice (a Photo Nest replaces the whole layout).
    if (request !== state.nestPhotoRequest || state.draft !== draft ||
        state.draftKind !== "nest") return;
    if (!beginDesignMutation()) return;
    mutationStarted = true;
    const previousDesign = clone(state.design);
    const result = await api("/api/nest/photo", {
      design: state.design,
      image,
      mime_type: mimeType,
      options: state.draft?.options || {},
    });
    state.design = result.design;
    recordHistory(previousDesign);
    state.selected = result.selected;
    state.draftKind = "nest";
    state.draft = clone(state.design.layout.features[state.selected]);
    setNestPhotoReference(result.reference);
    state.draftAutoCommit = true;
    state.drafts = {};
    syncForm();
    renderDraftFields();
    await refreshPreview();
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    $('.view-tab[data-view="2d"]').click();
    toast(`Snug Holder ready: ${fmt(result.outline.width)} × ${fmt(result.outline.depth)} mm outline.`);
  } catch (error) {
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    toast(error.message, true, 6500);
  } finally {
    input.value = "";
    if (mutationStarted) finishDesignMutation();
  }
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
  let width = Math.max(0.1, number(get("width"), isPocket ? oldWidth - 2 * wall : oldWidth));
  let depth = Math.max(0.1, number(get("depth"), isPocket ? oldDepth - 2 * wall : oldDepth));
  if (isPocket) {
    width = width + 2 * wall;
    depth = depth + 2 * wall;
  }
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
  const info = partInfo();
  if (info.flags.qty) {
    const count = String(get("count") ?? "auto").trim().toLowerCase();
    one.count = count === "" || count === "auto" ? null : Math.max(1, Math.round(number(count, 1)));
  }
  if (info.flags.alternate) {
    one.alternate_ends = $('[data-draft="alternate_ends"]', $("#draft-fields"))?.checked === true;
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
  const changed = event?.currentTarget?.dataset?.draft || "";
  if (one.kind === "cradle") {
    delete one.options.floor_gap;
    delete one.options.run_offset;
  }
  if (one.kind === "bore") {
    const toward = get("option:angle_towards");
    if (toward !== undefined) one.options.angle_towards = toward;
    else delete one.options.angle_towards;
  }
  if (one.kind === "nest") {
    for (const key of ["lift_assist", "finger_position", "push_position"]) {
      const value = get(`option:${key}`);
      if (value !== undefined) one.options[key] = value;
    }
  }
  // Text carries the only options that are not numbers: what it says, and two
  // plain yes/no choices. Read them straight off their own controls.
  if (info.flags.text) {
    const fields = $("#draft-fields");
    const said = $('[data-draft="option:text"]', fields);
    if (said) one.options.text = said.value;
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
      one.options.raised = $('[data-draft="option:raised"]', fields)?.checked === true;
      if (changed === "option:auto" && one.options.auto) {
        // Handing placement back to the engine: drop the hand-set letter height
        // so it can pick the biggest that fits wherever it lands.
        delete one.options.cap_height;
        const capField = $('[data-draft="option:cap_height"]', fields);
        if (capField) capField.value = "";
      }
    }
    syncRimLabelFromFeatures();
  }
  // A divider's sloped-bottom yes/no choices, read straight off their
  // checkboxes; an unticked one is dropped so a saved design stays clean and
  if (one.kind === "divider") {
    const fields = $("#draft-fields");
    for (const key of ["slope_base", "alternate_bottom", "minimal_bottom", "label_divisions"]) {
      const boxEl = $(`[data-draft="option:${key}"]`, fields);
      if (!boxEl) continue;
      if (boxEl.checked) one.options[key] = true;
      else delete one.options[key];
    }
    if (!one.options.slope_base) {
      delete one.options.bottom_angle;
      delete one.options.alternate_bottom;
      delete one.options.minimal_bottom;
      delete one.options.bottom_supports;
    }
    if (changed === "option:slope_base" && one.options.slope_base) {
      delete one.options.scoop;
      if (!Object.prototype.hasOwnProperty.call(one.options, "bottom_angle")) {
        one.options.bottom_angle = 20;
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
        "slope_base", "label_divisions", "division_level", "division_side", "division_labels",
        "level", "rim_side",
        "lift_assist", "finger_position", "push_position", "angle_towards"]
        .includes(changed.slice("option:".length))) {
    const key = changed.slice("option:".length);
    const option = info.fields.find(entry => entry.key === key);
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
    }
    if (info.kind === "pocket" && key === "wall") {
      const newWall = number(one.options.wall, 1.6);
      const prevWall = number(state.draftResolvedOptions?.wall, 1.6);
      const innerW = Math.max(0.1, oldWidth - 2 * prevWall);
      const innerD = Math.max(0.1, oldDepth - 2 * prevWall);
      const newW = innerW + 2 * newWall;
      const newD = innerD + 2 * newWall;
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
    if (one.kind === "nest" && one.contour && ["clearance", "rim", "smoothing"].includes(key)) {
      syncNestZone(one);
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
    changed === "option:angle_towards"
  )) sizeBoreToGrid(one);
  // The peg row and the slot bank track their own contents the same way the
  // bore base tracks its grid: change the count, peg size, gap, slot pitch or
  // lean and the zone re-fits (grow or shrink) on the driven axis.
  if (one.kind === "post" && (
    changed === "count" || changed === "option:diameter" ||
    changed === "option:spacing" || changed === "along"
  )) sizePostToRow(one);
  if (one.kind === "slot" && (
    changed === "count" || changed === "option:thickness" ||
    changed === "option:wall" || changed === "option:angle" || changed === "along"
  )) sizeSlotToBank(one);
  // A hand-typed Base Width / Length pins that axis: from now on the contents
  // sizers only ever grow it to fit, never shrink or overwrite the number.
  if (info.flags.size && (changed === "width" || changed === "depth")) {
    pinDraftAxis(changed);
    if (Number.isInteger(state.selected)) state.partZoneLocks[state.selected] = state.pinnedZone;
  }
  // Toggling Alternate ends swaps the field beneath Runs along between
  // "% from end" and "Offset from center".
  if (changed === "alternate_ends") renderDraftFields();
  // Switching a bore's profile swaps which fields show (locked hex-bit size,
  // the Angle field for round/square only).
  if ((changed === "profile" || changed === "option:angle") && one.kind === "bore") renderDraftFields();
  if (changed === "option:lift_assist" && one.kind === "nest") renderDraftFields();
  // Ticking Use support crossbars reveals (or hides) Number of crossbars.
  if (changed === "option:minimal_bottom") renderDraftFields();
  if (changed === "option:level") renderDraftFields();
  if (one.kind === "divider" && (
    changed === "option:slope_base" || changed === "option:label_divisions" ||
    changed === "option:division_level" || changed === "count" ||
    changed === "option:count_x" || changed === "option:count_y"
  )) renderDraftFields();
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
    const [insideX, insideY] = binInsideExtent(state.design.box);
    state.draft.zone = [-insideX / 2, -insideY / 2, insideX / 2, insideY / 2];
  }
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
      if (input && Object.prototype.hasOwnProperty.call(state.draftResolvedOptions, option.key)) {
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
        await autoExpandBin({ keepDraft: true });
      } finally {
        state.autoGrowingBin = false;
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
//
// "Real" means the user typed it. A text part starts life with placeholder
// lettering so it is valid and visible the moment it is added, and naming
// every file after that placeholder would be worse than leaving it blank.
function seedPartNameFromText(one) {
  if (!one || one.kind !== "text") return;
  const partInput = $("#part-name");
  if (!partInput || partInput.value.trim() !== "") return;
  const said = String(one.options?.text ?? "").trim();
  if (!said || SIZE_LIKE_TEXT.test(said)) return;
  if (said === String(state.draftStartingText ?? "").trim()) return;
  partInput.value = said;
  state.design.part_name = said;
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
// instead of waiting for an explicit button click. Runs silently - no
// button state, no toast, no field re-render - so it never interrupts
// active typing; a failure (e.g. it now overlaps another support, which the
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
    renderPlaced();
    updateSelectionButtons();
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
  renderDraftFields();
  renderPlaced();
  updateSelectionButtons();
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
    return true;
  } catch (error) {
    toast(error.message, true, 5000);
    return false;
  } finally {
    finishDesignMutation();
  }
}

// "Save Part": fold the open draft into the design (appending a new part or
// updating the one being re-edited), then return to the 10-part palette. A
// draft that can't be saved (overlap, doesn't fit) keeps the editor open with
// its error.
async function saveCurrentPart() {
  if (!state.draft || !beginDesignMutation()) return;
  try {
    const index = draftCommitIndex();
    const applyIndex = Number.isInteger(index) ? index : null;
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", {
      design: state.design, feature: state.draft, index: applyIndex,
    });
    state.design = result.design;
    seedPartNameFromText(state.draft);
    recordHistory(previousDesign);
    state.paletteBrowsing = true;
    clearDraftSelection();
    renderPlaced();
    await refreshPreview();
    toast("Part saved.");
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
  if (!state.draft) return;
  const index = draftCommitIndex();
  state.paletteBrowsing = true;
  if (Number.isInteger(index)) {
    await deleteSupportAt(index);
    return;
  }
  // Never committed - nothing on the server to delete.
  clearDraftSelection();
  renderPlaced();
  refreshPreview();
}

async function deleteSupportAt(index) {
  if (index === null || index === undefined || !beginDesignMutation()) return;
  let deleted = false;
  try {
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/delete", { design: state.design, index });
    state.design = result.design;
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
    '#x-size, #y-size, #z, #standard-base, #base-thickness, #standard-walls, #wall-thickness, #easy-clean, #easy-clean-style, #easy-clean-radius, #part-name, ' +
    '#mode-select, ' +
    '#new-design, #open-design, #save-design'
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
  // The mutation operates on a new snapshot of the design. Pending draft
  // work was calculated against the old snapshot and must not land afterward.
  const beforeForm = clone(pendingDesignHistory || state.design);
  cancelPendingDraftWork();
  // A queued size-history snapshot belongs to the design before this atomic
  // operation. Do not let it become the "before" state of a later edit.
  applyChangedDesign.cancel();
  pendingDesignHistory = null;
  updateDesignFromForm();
  recordHistory(beforeForm);
  state.designMutationBusy = true;
  state.previewRequest += 1;
  setMutationSurfacesInert(true);
  mutationControls().forEach(control => control.disabled = true);
  updateSelectionButtons();
  updateHistoryButtons();
  updateGenerateAvailability();
  return true;
}

function finishDesignMutation() {
  state.designMutationBusy = false;
  setMutationSurfacesInert(false);
  mutationControls().forEach(control => control.disabled = false);
  updateSelectionButtons();
  updateHistoryButtons();
  updateGenerateAvailability();
}

function updateSelectionButtons() {
  const busy = state.designMutationBusy;
  // The editor being open IS "editing mode" - set synchronously the moment a
  // part is picked, before its defaults have loaded. Collapse the palette to
  // just that part. Placed parts remain available in the preview for direct
  // 2D editing.
  const editing = !$(".support-editor").hidden;
  $("#support-palette").classList.toggle("editing", editing);
  // Save / Delete Part ride in the top-right of the green part chip, shown
  // only while a part is open for editing.
  const draftActions = $("#draft-actions");
  if (draftActions) draftActions.hidden = !editing;
  const placedBlock = $(".placed-block");
  if (placedBlock) {
    placedBlock.hidden = !state.design?.layout?.features?.length;
  }
  $("#save-part").disabled = busy || !state.draft;
  $("#delete-part").disabled = busy || !state.draft;
  const hasPhotoNest = state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour);
  const replacingPhotoNest = hasPhotoNest && state.selected !== null &&
    state.design.layout.features[state.selected]?.kind === "nest";
  $$(".support-choice").forEach(button => {
    button.disabled = busy || (hasPhotoNest && !replacingPhotoNest && button.dataset.kind !== "nest");
  });
  $$(".placed-item-select, .placed-item-delete").forEach(button => button.disabled = busy);
  $("#support-count").textContent = `${state.design?.layout.features.length || 0} placed`;
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

function renderPlaced() {
  if (!state.design) return;
  const features = state.design.layout.features;
  const container = $("#placed-supports");
  if (!features.length) {
    container.innerHTML = '<div class="placed-empty">No interior parts yet. Pick a shape above.</div>';
  } else {
    container.innerHTML = features.map((one, index) => {
      const width = one.zone[2] - one.zone[0];
      const depth = one.zone[3] - one.zone[1];
      const isRim = one.kind === "text" && one.options?.level === "rim";
      const title = isRim ? "Text (Rim Level)" : escapeHtml(partInfo(one.kind)?.title || one.kind);
      const specs = isRim ? escapeHtml(one.options?.text || "Rim label") : `${fmt(width)} × ${fmt(depth)} mm`;
      const invalid = new Set(state.preview?.invalid_feature_indexes || []).has(index);
      const statusClass = invalid ? "status-error" : (index === state.selected ? "status-valid" : "");
      return `<div class="placed-item ${index === state.selected ? "selected" : ""} ${statusClass}" style="--support-color:${kindColor(one.kind)}">
        <button type="button" class="placed-item-select" data-index="${index}">
          <span class="placed-item-icon">${iconFor(one.kind)}</span>
          <span class="placed-item-copy"><strong>${title}</strong><span>${specs}</span></span>
        </button>
        <button type="button" class="placed-item-delete" data-index="${index}" title="Delete this interior part" aria-label="Delete ${title}">✕</button>
      </div>`;
    }).join("");
    $$(".placed-item-select", container).forEach(button => button.addEventListener("click", async () => {
      const index = Number(button.dataset.index);
      await selectedFeature(index);
      if (state.selected === index) activatePreviewView("2d");
    }));
    $$(".placed-item-delete", container).forEach(button => button.addEventListener("click", () => deleteSupportAt(Number(button.dataset.index))));
  }
  $("#support-count").textContent = `${features.length} placed`;
  const summaryEl = $("#design-summary");
  if (summaryEl) {
    summaryEl.textContent = features.length
      ? `${features.length} interior part${features.length === 1 ? "" : "s"} · ${state.design.layout.mode}`
      : `No interior parts placed · ${state.design.layout.mode}`;
  }

  // With a single support there's nothing to choose between, so drop straight
  // into its settings rather than make the user pick it out of the list first.
  // selectedFeature() sets state.selected, so the re-entrant renderPlaced() it
  // triggers falls through here instead of looping. Suppressed right after an
  // explicit Save / Delete Part, when the user asked to be back at the palette.
  if (features.length === 1 && state.selected === null && !state.draft
      && !state.paletteBrowsing) {
    selectedFeature(0);
  }
}

async function refreshPreview() {
  const request = ++state.previewRequest;
  state.canGenerate = false;
  updateGenerateAvailability();
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
    state.preview = result;
    state.design = result.design;
    checkBinSizeChange();
    const previewHasErrors = !result.fits || result.feature_errors.length || result.draft_error;
    $("#preview-state").textContent = previewHasErrors ? "Design needs attention" : "Preview current";
    $("#preview-state").classList.toggle("status-error", Boolean(previewHasErrors));
    $("#preview-state").classList.toggle("status-ok", !previewHasErrors);
    formatDimField("x");
    formatDimField("y");
    $(".dimension-width", $("#dimensions")).textContent = `Width ${fmt(state.design.box.x)} mm`;
    $(".dimension-depth", $("#dimensions")).textContent = `Depth ${fmt(state.design.box.y)} mm`;
    $(".dimension-height", $("#dimensions")).textContent = `Height ${fmt(state.design.box.z)} mm`;
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
    renderB4BReadout();
    renderPreview3D();
    renderLayout2D();
    renderPlaced();
  } catch (error) {
    if (request !== state.previewRequest) return;
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
    rows.push(`<button type="button" class="button" data-action="grow-bin" hidden>Grow the bin</button>`);
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

// Grow the bin to hold every interior part. Options:
//   keepDraft - stay in the editor on the same part instead of closing it
//   silent    - no toast
async function autoExpandBin(event) {
  const opts = event && !event.currentTarget ? event : {};
  const draftIndex = state.draft ? draftCommitIndex() : null;
  if (draftIndex === false) {
    if (!opts.silent) toast("Select the interior part again before growing the bin.", true);
    return;
  }
  if (!beginDesignMutation()) return;
  const button = event?.currentTarget || null;
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
    });
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
      toast(`Bin resized to ${fmt(result.box.x)} × ${fmt(result.box.y)} mm.`);
    } else if (!opts.silent && !opts.keepDraft) {
      toast("The interior parts already fit - bin unchanged.");
    }
  } catch (error) {
    if (!opts.silent) toast(error.message, true, 5000);
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

// Opaque neutral ground so the object has something to sit against, plus a soft
// contact shadow projected from the model's base rectangle - cheap grounding,
// no ray tracing.
function paintBackdrop(context, width, height) {
  const bg = context.createLinearGradient(0, 0, 0, height);
  bg.addColorStop(0, "#eef1f2");
  bg.addColorStop(1, "#dfe4e5");
  context.fillStyle = bg;
  context.fillRect(0, 0, width, height);
}

function drawContactShadow(context, box, camera, project) {
  if (!box) return;
  const hx = number(box.x) / 2, hy = number(box.y) / 2;
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

function drawGeometry(canvas, geometry, camera) {
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
  const camX = -Math.sin(yawRad);
  const camY = -Math.cos(yawRad);

  const isBinFace = kind =>
    kind === "outside" || kind === "inside" || kind === "rim" || kind === "floor" ||
    kind === "top_label_ledge" || kind === "label" || kind === "label_hole";

  const isFacingSide = (face) => {
    let sideX = 0, sideY = 0;
    if (Math.abs(camX) >= Math.abs(camY)) {
      sideX = camX > 0 ? 1 : -1;
    } else {
      sideY = camY > 0 ? 1 : -1;
    }
    const nx = face.normal[0], ny = face.normal[1];
    if (sideX !== 0) {
      if (sideX > 0 ? nx > 0.3 : nx < -0.3) return true;
    }
    if (sideY !== 0) {
      if (sideY > 0 ? ny > 0.3 : ny < -0.3) return true;
    }
    let sumX = 0, sumY = 0;
    for (const pt of face.points) {
      sumX += pt[0];
      sumY += pt[1];
    }
    const avgX = sumX / face.points.length;
    const avgY = sumY / face.points.length;
    const box = state.design?.box;
    const hx = box ? number(box.x) / 2 : 1;
    const hy = box ? number(box.y) / 2 : 1;
    if (sideX > 0 && avgX > hx * 0.45) return true;
    if (sideX < 0 && avgX < -hx * 0.45) return true;
    if (sideY > 0 && avgY > hy * 0.45) return true;
    if (sideY < 0 && avgY < -hy * 0.45) return true;
    return false;
  };

  const faces = geometry.map(face => {
    const points = face.points.map(point => iso(point, camera));
    const depth = face.points.reduce((sum, point) => sum + dot(point, vector), 0) / face.points.length;
    const facing = dot(face.normal, vector);
    return { ...face, projected: points, depth, facing };
  }).filter(face => {
    const isBin = isBinFace(face.kind);
    const mode = state.previewMode || "standard";
    if (mode === "bin" && !isBin) return false;
    if (mode === "interior" && isBin) return false;
    if (mode === "xray" && isBin && isFacingSide(face)) return false;
    return face.facing > 0 || face.kind === "label_hole";
  });
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
      if (number(face.layer) < 2) face.layer = 2;
    }
  }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const face of faces) for (const point of face.projected) {
    minX = Math.min(minX, point[0]); maxX = Math.max(maxX, point[0]);
    minY = Math.min(minY, point[1]); maxY = Math.max(maxY, point[1]);
  }
  const spanX = Math.max(1e-8, maxX - minX), spanY = Math.max(1e-8, maxY - minY);
  const scale = Math.min((width * 0.75) / spanX, (height * 0.75) / spanY) * camera.zoom;
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const project = point => [width / 2 + (point[0] - midX) * scale, height / 2 + (point[1] - midY) * scale];
  faces.sort((a, b) => a.depth - b.depth || number(a.layer) - number(b.layer));
  drawContactShadow(context, state.design?.box, camera, project);
  context.lineJoin = "round";
  for (const face of faces) {
    const points = face.projected.map(project);
    if (points.length < 3) continue;
    if (/^(feature_|insert_|draft_)/.test(face.kind)) state.previewSupportPolygons.push(points);
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach(point => context.lineTo(point[0], point[1]));
    context.closePath();
    const base = kindColor(face.kind);
    context.fillStyle = shade(base, faceLighting(face.normal));
    context.fill();
    const isDraft = face.kind.startsWith("draft_");
    // Match the seam stroke to the fill first so internal triangulation stops
    // reading as a wireframe, then lay only a whisper of darker contrast where
    // surfaces actually meet.
    context.strokeStyle = context.fillStyle;
    context.lineWidth = .8;
    context.stroke();
    context.strokeStyle = isDraft ? "rgba(196,131,20,.45)" : "rgba(18,32,38,.08)";
    context.lineWidth = isDraft ? .6 : .35;
    context.stroke();
  }
  drawUsableFloor(context, geometry, camera, project);
  drawBoreAxes(context, boreAxes, camera, project);
  draw3DDimensions(context, state.design?.box, camera, project);
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
  if (state.previewMode === "interior") return;
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

function draw3DDimensions(context, box, camera, project) {
  if (!box) return;
  const hx = number(box.x) / 2;
  const hy = number(box.y) / 2;
  const hz = number(box.z);
  if (hx <= 0 || hy <= 0 || hz <= 0) return;

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
    `Width ${fmt(box.x)} mm`,
    gap,
    over
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
    `Depth ${fmt(box.y)} mm`,
    gap,
    over
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
    `Height ${fmt(box.z)} mm`,
    gap,
    over
  );
}

function renderDimensionGuide(context, pStart, pEnd, witA, witB, normal, label, gap, over) {
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

  // Subtle drop shadow for badge
  context.shadowColor = "rgba(18, 38, 46, 0.25)";
  context.shadowBlur = 6;
  context.shadowOffsetY = 2;

  // Dark HUD pill badge
  context.fillStyle = "rgba(18, 38, 46, 0.90)";
  context.beginPath();
  if (context.roundRect) {
    context.roundRect(-bw / 2, -bh / 2, bw, bh, r);
  } else {
    context.rect(-bw / 2, -bh / 2, bw, bh);
  }
  context.fill();

  context.shadowColor = "transparent";
  context.strokeStyle = "rgba(105, 172, 168, 0.70)";
  context.lineWidth = 1;
  context.stroke();

  // Crisp text
  context.fillStyle = "#ffffff";
  context.fillText(label, 0, 0.5);

  context.restore();
}

function renderPreview3D() {
  if (!state.preview) return;
  checkBinSizeChange();
  drawGeometry($("#preview-3d"), state.preview.geometry, state.camera);
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

function wireSceneInteraction(canvas, camera, render) {
  let drag = null;
  canvas.addEventListener("pointerdown", event => {
    drag = { x: event.clientX, y: event.clientY, yaw: camera.yaw, elevation: camera.elevation, moved: false };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!drag) return;
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 4) drag.moved = true;
    $$('[data-camera-view]').forEach(button => button.classList.remove("active"));
    camera.yaw = drag.yaw + (event.clientX - drag.x) * .45;
    camera.elevation = Math.max(8, Math.min(89, drag.elevation - (event.clientY - drag.y) * .35));
    render();
  });
  canvas.addEventListener("pointerup", event => {
    const clickedSupport = drag && !drag.moved && clickedPreviewSupport(canvas, event);
    drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (clickedSupport) {
      const dialog = $("#support-layout-dialog");
      if (!dialog.open) dialog.showModal();
    }
  });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    camera.zoom = Math.max(.35, Math.min(4, camera.zoom * Math.exp(-event.deltaY * .001)));
    render();
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
  context.globalAlpha = .55;
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

function drawClosedPath(context, points, toCanvas) {
  const path = new Path2D();
  points.forEach((point, index) => {
    const p = toCanvas(point);
    index === 0 ? path.moveTo(p[0], p[1]) : path.lineTo(p[0], p[1]);
  });
  path.closePath();
  return path;
}

function drawDimensionLine(context, start, end, label, vertical = false) {
  context.save();
  context.strokeStyle = "#496873";
  context.fillStyle = "#496873";
  context.lineWidth = 1;
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
  context.fillStyle = "rgba(248,250,249,.92)";
  context.fillRect(-textWidth / 2 - 5, -8, textWidth + 10, 16);
  context.fillStyle = "#496873";
  context.fillText(label, 0, 0);
  context.restore();
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

function renderDividerDivisionLabels(context, feature, toCanvas, scale) {
  const opt = feature.options || {};
  let labels = opt.division_labels;
  if (!labels) return;
  if (typeof labels === "string") {
    try { labels = JSON.parse(labels); } catch { labels = labels.split(","); }
  }
  if (!Array.isArray(labels) || !labels.length) return;

  const [z0, z1, z2, z3] = feature.zone;   // x0, y0, x1, y1
  const thickness = number(opt.thickness, 1.6);
  const along = feature.along || "x";
  const legacyN = feature.count == null ? 1 : Math.max(1, number(feature.count, 1));
  let gx = number(opt.count_x, NaN);
  if (!Number.isFinite(gx)) gx = along === "y" ? legacyN : 0;
  let gy = number(opt.count_y, NaN);
  if (!Number.isFinite(gy)) gy = along === "x" ? legacyN : 0;
  gx = Math.max(0, Math.round(gx));
  gy = Math.max(0, Math.round(gy));

  const xEdges = [z0];
  for (let i = 0; i < gx; i++) xEdges.push(z0 + (i + 1) * (z2 - z0) / (gx + 1));
  xEdges.push(z2);
  const yEdges = [z1];
  for (let i = 0; i < gy; i++) yEdges.push(z1 + (i + 1) * (z3 - z1) / (gy + 1));
  yEdges.push(z3);
  const nCols = xEdges.length - 1;
  const nRows = yEdges.length - 1;

  for (let r = 0; r < nRows; r++) {
    for (let c = 0; c < nCols; c++) {
      const idx = r * nCols + c;
      if (idx >= labels.length) continue;
      const text = String(labels[idx] || "").trim();
      if (!text) continue;

      const x0 = xEdges[c] + (c === 0 ? 0 : thickness / 2);
      const x1 = xEdges[c + 1] - (c === nCols - 1 ? 0 : thickness / 2);
      let y0 = yEdges[r] + (r === 0 ? 0 : thickness / 2);
      const y1 = yEdges[r + 1] - (r === nRows - 1 ? 0 : thickness / 2);
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
}

function renderLayout2D() {
  if (!state.preview) return;
  const canvas = $("#preview-2d");
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
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
    if (active?.kind === "nest") drawNestPhotoReference(context, active, toCanvas);
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
      const outline = drawClosedPath(context, nestOutlineWorld(
        feature, editingPoint ? null : state.preview.nest_soft_contours?.[index]
      ), toCanvas);
      context.fillStyle = color + "35";
      context.fill(outline);
      context.stroke(outline);
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
          context.save();
          context.clip(worldRect(feature.zone));
          context.strokeStyle = "#1f6b45";
          context.lineWidth = 1.8;
          context.globalAlpha = .78;
          const [sx0, sy0, sx1, sy1] = feature.zone;
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
        drawNestContourHandles(context, feature, toCanvas);
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
      const outline = drawClosedPath(context, nestOutlineWorld(liveDraft, softContour), toCanvas);
      context.fillStyle = draftColor + "18";
      context.strokeStyle = draftColor;
      context.fill(outline); context.stroke(outline);
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
  const offsetOutside = (start, end) => {
    const middle = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2];
    const length = Math.max(1, Math.hypot(middle[0] - width / 2, middle[1] - height / 2));
    const dx = (middle[0] - width / 2) * 18 / length;
    const dy = (middle[1] - height / 2) * 18 / length;
    return [[start[0] + dx, start[1] + dy], [end[0] + dx, end[1] + dy]];
  };
  const widthLine = offsetOutside(toCanvas([bounds[0], bounds[3]]), toCanvas([bounds[2], bounds[3]]));
  const depthLine = offsetOutside(toCanvas([bounds[0], bounds[1]]), toCanvas([bounds[0], bounds[3]]));
  drawDimensionLine(context, ...widthLine, `Width ${fmt(state.design.box.x)} mm`);
  drawDimensionLine(context, ...depthLine, `Depth ${fmt(state.design.box.y)} mm`);

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
      if (hitNestContourPoint(feat, world) !== null) return selIndex;
      if (state.layoutTransform) {
        const cx = (zone[0] + zone[2]) / 2;
        const handles = [[zone[2], zone[1]], [cx, zone[3] + 8]];
        if (handles.some(point => Math.hypot(
          (world[0] - point[0]) * state.layoutTransform.scale,
          (world[1] - point[1]) * state.layoutTransform.scale,
        ) < 14)) return selIndex;
      }
      if (pointInPolygon(world, nestOutlineWorld(feat, state.preview?.nest_soft_contours?.[selIndex]))) return selIndex;
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
      if (pointInPolygon(world, nestOutlineWorld(feat, state.preview?.nest_soft_contours?.[index]))) return index;
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

function wireLayoutInteraction() {
  const canvas = $("#preview-2d");
  // Tracks whether the pointer is still down after an awaited "keep this part?"
  // prompt - if the user lifted their finger to answer it, there's no drag.
  let pointerActive = false;
  canvas.addEventListener("pointercancel", () => { pointerActive = false; });
  canvas.addEventListener("pointerdown", async event => {
    if (!state.layoutTransform || state.designMutationBusy) return;
    pointerActive = true;
    const world = layoutPoint(event);
    let index = hitFeature(world);
    if (index === null) {
      if (state.selected !== null) {
        if (!(await guardDraftSwitch())) return;
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
    // Moving or resizing lettering by hand is a placement decision, so it
    // stops placing itself - otherwise the next preview would put it straight
    // back where the engine wanted it and the drag would look broken.
    if (feature.kind === "text" && feature.options?.auto) {
      feature.options.auto = false;
      const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
      if (autoField) autoField.checked = false;
    }
    const zone = feature.zone;
    const handlePixels = Math.hypot((world[0] - zone[2]) * state.layoutTransform.scale, (world[1] - zone[1]) * state.layoutTransform.scale);
    const rotatePoint = [(zone[0] + zone[2]) / 2, zone[3] + 8];
    const rotatePixels = Math.hypot((world[0] - rotatePoint[0]) * state.layoutTransform.scale, (world[1] - rotatePoint[1]) * state.layoutTransform.scale);
    const centre = [(zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2];
    const resizable = Boolean(partInfo(feature.kind)?.flags?.size || feature.kind === "nest");
    const contourPoint = feature.kind === "nest" ? hitNestContourPoint(feature, world) : null;
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
    const drag = state.layoutDrag;
    if (!drag || !state.layoutTransform) return;
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
      drag.feature.rotation = Math.round(number(drag.original.rotation) + (angle - drag.startAngle) * 180 / Math.PI);
      syncNestZone(drag.feature);
    } else if (drag.feature.kind === "nest") {
      const radius = Math.hypot(world[0] - drag.centre[0], world[1] - drag.centre[1]);
      drag.feature.scale = Math.max(.1, number(drag.original.scale, 1) * radius / drag.startRadius);
      syncNestZone(drag.feature);
    } else {
      const width = Math.max(pitch, snap(2 * Math.abs(world[0] - drag.centre[0])));
      const depth = Math.max(pitch, snap(2 * Math.abs(world[1] - drag.centre[1])));
      drag.feature.zone = [drag.centre[0] - width / 2, drag.centre[1] - depth / 2, drag.centre[0] + width / 2, drag.centre[1] + depth / 2];
    }
    renderLayout2D();
  });
  canvas.addEventListener("pointerup", async event => {
    pointerActive = false;
    const drag = state.layoutDrag;
    if (!drag) return;
    state.layoutDrag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (typeof drag.index !== "number") return;   // not a feature drag - nothing to apply
    state.draft = drag.feature;
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
  const z = feature.zone;
  const roundCoord = val => Math.round(val * 1000) / 1000;
  feature.zone = [
    roundCoord(z[0] + dx),
    roundCoord(z[1] + dy),
    roundCoord(z[2] + dx),
    roundCoord(z[3] + dy),
  ];

  if (state.design.layout.features[state.selected]) {
    state.design.layout.features[state.selected].zone = clone(feature.zone);
  }
  if (feature.kind === "text" && feature.options?.auto) {
    feature.options.auto = false;
    const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
    if (autoField) autoField.checked = false;
  }
  if (feature.kind === "nest") {
    syncNestZone(feature);
  }

  state.nudgeFeedback = {
    amount: `${step} mm`,
    mod,
  };
  updateNudgeUI();
  renderLayout2D();

  if (!pendingNudgeHistory) {
    pendingNudgeHistory = clone(state.design);
  }
  commitNudge();
}

async function saveDesign() {
  if (!beginDesignMutation()) return;
  try {
    // The editor saves valid part edits after a short typing pause. Commit the
    // visible draft explicitly so an immediate Save cannot download the older
    // server copy while the new value is still waiting in that pause.
    await commitVisibleDraft();
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

function designHasChanges() {
  const visibleDesign = clone(state.design);
  const snapSize = (value, fallback) => {
    const unit = state.catalog.base_unit;
    return Math.max(unit, Math.round(number(value, fallback) / unit) * unit);
  };
  visibleDesign.box.x = snapSize($("#x-size").value, visibleDesign.box.x);
  visibleDesign.box.y = snapSize($("#y-size").value, visibleDesign.box.y);
  visibleDesign.box.z = number($("#z").value, visibleDesign.box.z);
  visibleDesign.box.standard_base = $("#standard-base").checked;
  visibleDesign.box.base_thickness = visibleDesign.box.standard_base
    ? 0.6
    : number($("#base-thickness").value, visibleDesign.box.base_thickness ?? 0.6);
  const wallRules = state.catalog?.wall_rules || {};
  visibleDesign.box.standard_walls = $("#standard-walls").checked;
  visibleDesign.box.wall = visibleDesign.box.standard_walls
    ? (wallRules.default_mm ?? 0.8)
    : Math.max(wallRules.min_mm ?? 0.2, Math.min(
        wallRules.max_mm ?? 2.4,
        number($("#wall-thickness").value, visibleDesign.box.wall ?? wallRules.default_mm ?? 0.8),
      ));
  visibleDesign.part_name = $("#part-name").value;
  const scoopEl = $("#scoop");
  if (scoopEl) visibleDesign.scoop = scoopEl.checked;
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
  if (designHasChanges() && !window.confirm("Open this design and replace the current one?")) {
    event.target.value = "";
    return;
  }
  if (!beginDesignMutation()) return;
  try {
    const parsed = JSON.parse(await file.text());
    const result = await api("/api/design/validate", { design: parsed });
    state.design = result.design;
    state.nestPhoto = null;
    state.cleanDesign = clone(state.design);
    state.drafts = {};
    state.history = [];
    state.future = [];
    state.binResizePending = false;
    syncForm();
    clearDraftSelection();
    await refreshPreview();
    toast(`Opened ${file.name}.`);
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    event.target.value = "";
    finishDesignMutation();
  }
}

async function newDesign() {
  if (designHasChanges() && !window.confirm("Start a new design and discard the current changes?")) return;
  if (!beginDesignMutation()) return;
  const previousDesign = clone(state.design);
  state.design = clone(state.catalog.defaults.design);
  state.nestPhoto = null;
  state.cleanDesign = clone(state.design);
  state.binResizePending = false;
  recordHistory(previousDesign);
  state.drafts = {};
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
    return `<span class="gen-spinner" aria-label="Generating"></span>`;
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

async function generateParts(target) {
  if (state.designMutationBusy || isGenerating) {
    toast("Finish the current action before generating files.", true);
    return;
  }
  if ((target === "all" || target === "bin") && !state.canGenerate) {
    toast("Resolve the highlighted issue before generating.", true);
    return;
  }

  updateDesignFromForm();
  setError();

  const dialog = $("#generation-dialog");
  const dialogTitle = $("#generation-dialog-title");
  const dialogSubtitle = $("#generation-dialog-subtitle");
  const dialogError = $("#generation-error");
  const dialogActions = $("#generation-actions");

  if (dialogTitle) dialogTitle.textContent = "Generating Parts…";
  if (dialogSubtitle) dialogSubtitle.textContent = "Please wait while your files are being generated and saved.";
  if (dialogError) {
    dialogError.hidden = true;
    dialogError.textContent = "";
  }
  if (dialogActions) {
    dialogActions.hidden = true;
  }

  const boxTitle = `Bin (${fmt(state.design.box.x)} × ${fmt(state.design.box.y)} × ${fmt(state.design.box.z)} mm)`;
  const connTitle = `Connector (${fmt(state.design.box.z)} mm)`;

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

  try {
    // A debounced support edit may still be visible only in the draft. Save
    // it now so the exported files always match the canvas.
    await commitVisibleDraft();

    const payload = {
      design: state.design,
      output: state.output,
      connector: state.connector,
      keep_log: state.keepLog,
    };

    // Step 1: Generate Bin if requested
    if (target === "all" || target === "bin") {
      setItemStatus("bin", "generating", "Generating…");
      const binResult = await api("/api/generate", payload);
      saveOutput = binResult.output || saveOutput;
      const binFiles = collectOutputs(binResult.result);
      allFiles.push(...binFiles);
      setItemStatus("bin", "done", "Done");
    }

    // Step 2: Generate Connector if requested
    if (target === "all" || target === "connector") {
      setItemStatus("connector", "generating", "Generating…");
      const connResult = await api("/api/connector", payload);
      saveOutput = connResult.output || saveOutput;
      if (connResult.connector_plan) {
        connectorPlan = connResult.connector_plan;
        renderConnectorReadout(connResult.connector_plan);
      }
      const connFiles = collectOutputs(connResult.result);
      allFiles.push(...connFiles);
      setItemStatus("connector", "done", "Done");
    }

    if (dialogTitle) dialogTitle.textContent = "Complete!";
    if (dialogSubtitle) dialogSubtitle.textContent = "All parts generated and saved.";

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
    toast(
      `Saved to ${saveOutput}${uniqueFiles.length ? `\n${uniqueFiles.join("\n")}` : ""}${planNote}`,
      false,
      7000,
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

    if (dialogTitle) dialogTitle.textContent = "Generation Failed";
    if (dialogSubtitle) dialogSubtitle.textContent = "An error occurred while generating parts.";
    if (dialogError) {
      dialogError.textContent = error.message;
      dialogError.hidden = false;
    }
    if (dialogActions) {
      dialogActions.hidden = false;
    }
    setError(error.message);
    toast(error.message, true, 7000);
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

async function printModel(target = "bin") {
  if (!state.slicer || !state.slicer.available) {
    toast("Bambu Studio is not installed or could not be found. Please install Bambu Studio or click 'Change slicer' to locate the executable.", true, 8000);
    return;
  }
  if (!beginDesignMutation()) return;
  const button = $("#print-bin");
  const old = button.textContent;
  button.disabled = true;
  const slicerName = state.slicer?.name || "Bambu Studio";
  button.textContent = `Sending to ${slicerName}…`;
  setError();
  try {
    await commitVisibleDraft();
    const payload = {
      design: state.design,
      output: state.output,
      connector: state.connector,
      target: target,
      keep_log: state.keepLog,
    };
    const result = await api("/api/print", payload);
    const files = result.files || [];
    const fileNames = files.map(f => f.split(/[\\/]/).pop());
    toast(`Sent to ${slicerName}!\n${fileNames.join("\n")}`, false, 7000);
  } catch (error) {
    setError(error.message);
    toast(error.message, true, 8000);
  } finally {
    button.textContent = old;
    finishDesignMutation();
  }
}

function updateSlicerUI() {
  const printBtn = $("#print-bin");
  const wrap = $(".print-button-wrap");
  if (!printBtn) return;
  const slicer = state.slicer || {};
  if (slicer.available) {
    if (wrap) wrap.hidden = false;
    printBtn.hidden = false;
    printBtn.textContent = `Print to ${slicer.name || "Bambu Studio"}`;
    printBtn.title = `Send directly to ${slicer.name || "Bambu Studio"}`;
  } else {
    if (wrap) wrap.hidden = false;
    printBtn.hidden = false;
    printBtn.textContent = `Print to ${slicer.name || "Bambu Studio"}`;
    printBtn.title = "Bambu Studio is not installed - click 'Change slicer' to locate executable";
  }
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

function watchServerVersion() {
  setInterval(async () => {
    let health;
    try {
      health = await api("/api/health");
    } catch (_error) {
      return; // A blip shouldn't flip the banner - only a confirmed different instance should.
    }
    if (health.instance === state.serverInstance) return;
    $("#connection").textContent = "Engine updated";
    $("#connection").classList.remove("ready");
    $("#connection").classList.add("stale");
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

async function init() {
  wireAboutDialog();
  try {
    const catalog = await api("/api/catalog");
    state.catalog = catalog;
    state.serverInstance = catalog.instance;
    state.design = clone(catalog.defaults.design);
    state.nestPhoto = null;
    state.cleanDesign = clone(state.design);
    state.output = catalog.preferences?.output || catalog.defaults.output;
    state.keepLog = catalog.preferences?.keep_log !== undefined ? Boolean(catalog.preferences.keep_log) : true;
    state.connector = clone(catalog.defaults.connector);
    state.slicer = catalog.slicer || { available: false, path: null, name: "Bambu Studio" };
    updateSlicerUI();
    renderCatalog();
    wireControls();
    syncForm();
    $("#connection").textContent = "Local engine connected";
    $("#connection").classList.add("ready");
    $("#connection").classList.remove("stale");
    watchServerVersion();
    updateHistoryButtons();
    clearDraftSelection();
    await refreshPreview();
  } catch (error) {
    $("#connection").textContent = "Engine unavailable";
    $("#connection").classList.remove("ready");
    $("#connection").classList.add("stale");
    setError(error.message);
    toast(error.message, true, 8000);
  }
}

init();
