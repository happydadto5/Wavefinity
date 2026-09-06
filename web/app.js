"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// Mirrors organizer_inserts.py's MIN_WEDGE_EDGE - the thinnest a wedge
// divider's tapered top may print. A small margin over the server's own
// cutoff keeps float rounding from tripping the same error right back.
const MIN_WEDGE_EDGE_MM = 0.45;

function flashField(input) {
  if (!input) return;
  input.classList.remove("field-flash");
  void input.offsetWidth; // restart the animation if it's already flashing
  input.classList.add("field-flash");
}

const state = {
  catalog: null,
  design: null,
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
  selected: null,
  camera: { yaw: 45, elevation: 76, zoom: 1 },
  previewRequest: 0,
  draftRequest: 0,
  output: "",
  connector: {},
  layoutDrag: null,
  layoutTransform: null,
  previewSupportPolygons: [],
  designMutationBusy: false,
  canGenerate: true,
  history: [],
  future: [],
  serverInstance: null,
};

const VERSION_POLL_MS = 5000;

const COLORS = {
  outside: "#8ea8b2", inside: "#c9d9dc", rim: "#6f8f99", floor: "#b9a97e",
  label: "#315766", label_hole: "#e8efef", top_label_ledge: "#7799a3",
  scoop: "#a9bec3", insert_base: "#c5ab83", invalid: "#c95f58",
  cradle: "#e59f54", nest: "#df8d5b", bore: "#6fb98f", post: "#51a5a1",
  divider: "#9d86c8", pocket: "#d4778c", slot: "#8b78cf", steps: "#4b8eb9",
  // Floor lettering keeps the colour the single floor label always had, so a
  // text interior part reads as writing rather than as another holder.
  text: "#315766",
};
const INSERT_TINT = "#c2a075";
const INSERT_TINT_MIX = .5;
// The support currently being edited, not yet added - shown live in the
// same bin view instead of its own isolated canvas, so it needs a colour
// that reads as "this one is different" against every kind's own muted
// palette above.
const DRAFT_HIGHLIGHT = "#f0a93c";
const CAMERA_VIEWS = {
  top: { yaw: 45, elevation: 89, zoom: 1 },
  front: { yaw: 0, elevation: 8, zoom: 1 },
  side: { yaw: 90, elevation: 8, zoom: 1 },
  reset: { yaw: 45, elevation: 76, zoom: 1 },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
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
  const button = $("#generate-bin");
  if (button) {
    button.disabled = state.designMutationBusy || !state.canGenerate;
    button.title = state.canGenerate ? "Generate the current bin files" : "Resolve the highlighted issue before generating";
  }
  const printButton = $("#print-bin");
  if (printButton) {
    printButton.disabled = state.designMutationBusy || !state.canGenerate;
    printButton.title = state.canGenerate ? "Export and open in Bambu Studio" : "Resolve the highlighted issue before printing";
  }
}

async function restoreHistory(redo = false) {
  const from = redo ? state.future : state.history;
  const to = redo ? state.history : state.future;
  if (!from.length || state.designMutationBusy) return;
  updateDesignFromForm();
  to.push(clone(state.design));
  state.design = from.pop();
  syncForm();
  clearDraftSelection();
  updateHistoryButtons();
  await refreshPreview();
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
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
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
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
  const paths = {
    divider: '<rect x="4" y="5" width="24" height="22" rx="2"/><path d="M16 5v22"/>',
    post: '<ellipse cx="16" cy="23" rx="10" ry="4"/><path d="M10 22V10c0-5 12-5 12 0v12"/><ellipse cx="16" cy="10" rx="6" ry="2.5"/>',
    pocket: '<rect x="4" y="6" width="24" height="20" rx="3"/><rect x="8" y="10" width="16" height="12" rx="2"/>',
    bore: '<rect x="4" y="5" width="24" height="22" rx="2"/><circle cx="11" cy="12" r="3"/><circle cx="21" cy="12" r="3"/><circle cx="11" cy="21" r="3"/><circle cx="21" cy="21" r="3"/>',
    cradle: '<path d="M4 25h24M7 25V10h4c0 4 2 6 5 6s5-2 5-6h4v15"/>',
    nest: '<rect x="3" y="6" width="26" height="20" rx="3"/><path d="M7 17h6v-6h7v4h5v6H7z"/>',
    slot: '<rect x="4" y="5" width="24" height="22" rx="2"/><path d="M9 22l5-12M15 22l5-12M21 22l5-12"/>',
    steps: '<path d="M4 25h24V10h-8v5h-8v5H4z"/>',
  };
  return `<svg ${common}>${paths[kind] || paths.pocket}</svg>`;
}

function renderCatalog() {
  const modes = $("#mode-options");
  modes.innerHTML = state.catalog.modes.map(mode => `
    <label><input type="radio" name="layout-mode" value="${mode.value}"><span>${escapeHtml(mode.label)}</span></label>
  `).join("");
  $$('input[name="layout-mode"]', modes).forEach(input => {
    input.addEventListener("change", async () => {
      if (!input.checked || input.value === state.design.layout.mode) return;
      if (!beginDesignMutation()) {
        syncForm();
        return;
      }
      const oldMode = state.design.layout.mode;
      const previousDesign = clone(state.design);
      const previousSelected = state.selected;
      try {
        const result = await api("/api/layout/mode", { design: state.design, mode: input.value });
        state.design = result.design;
        recordHistory(previousDesign);
        syncForm();
        // A support that was already saved keeps being edited, just in its
        // converted form - only fall back to a fresh, not-yet-saved
        // suggestion when nothing was actually selected before the switch.
        if (previousSelected !== null && previousSelected < state.design.layout.features.length) {
          selectedFeature(previousSelected);
        } else {
          clearDraftSelection();
        }
        refreshPreview();
      } catch (error) {
        $(`input[name="layout-mode"][value="${oldMode}"]`).checked = true;
        toast(error.message, true);
      } finally {
        finishDesignMutation();
      }
    });
  });

  const palette = $("#support-palette");
  palette.innerHTML = state.catalog.parts.map(part => `
    <button class="support-choice" data-kind="${part.kind}" style="--support-color:${kindColor(part.kind)}" aria-label="${escapeHtml(part.title)}: ${escapeHtml(part.description)}" title="${escapeHtml(part.title)} — ${escapeHtml(part.description)}">
      ${iconFor(part.kind)}
      <span class="support-choice-copy"><strong>${escapeHtml(part.title)}</strong><small>${escapeHtml(part.description)}</small></span>
    </button>
  `).join("");
  $$(".support-choice", palette).forEach(button => {
    button.addEventListener("click", () => pickKind(button.dataset.kind));
  });
}

function syncForm() {
  const { box, layout } = state.design;
  $("#x-size").value = fmt(box.x);
  $("#y-size").value = fmt(box.y);
  $("#z").value = fmt(box.z);
  $("#base-thickness").value = fmt(box.base_thickness ?? 0.6);
  $("#label-text").value = state.design.label || "";
  $("#part-name").value = state.design.part_name || "";
  $("#scoop").checked = Boolean(state.design.scoop);
  const mode = $(`input[name="layout-mode"][value="${layout.mode}"]`);
  if (mode) mode.checked = true;
  $("#output-folder").value = state.output;
  $("#connector-tolerance").value = fmt(state.connector.tolerance);
  $("#connector-length").value = fmt(state.connector.length);
  $("#connector-bin-a-height").value = fmt(state.connector.bin_a_height);
  $("#connector-bin-b-height").value = fmt(state.connector.bin_b_height);
  $("#different-height-bins").checked = Boolean(state.connector.different_heights);
  syncConnectorHeightControls();
  updateInteriorModeVisibility();
  renderPlaced();
}

function syncConnectorHeightControls() {
  const different = $("#different-height-bins").checked;
  $("#connector-bin-heights").hidden = !different;
}

function updateInteriorModeVisibility(reveal = false) {
  const fieldset = $("#interior-mode");
  const hasSupport = Boolean(state.draft || state.design?.layout?.features?.length);
  if (reveal && !hasSupport && state.design.layout.mode !== "fused") {
    state.design.layout.mode = "fused";
    const fused = $('input[name="layout-mode"][value="fused"]');
    if (fused) fused.checked = true;
  }
  fieldset.hidden = !(reveal || hasSupport);
}

function updateDesignFromForm() {
  const design = state.design;
  const snapSize = (value, fallback) => {
    const unit = state.catalog.base_unit;
    return Math.max(unit, Math.round(number(value, fallback) / unit) * unit);
  };
  design.box.x = snapSize($("#x-size").value, design.box.x);
  design.box.y = snapSize($("#y-size").value, design.box.y);
  design.box.z = number($("#z").value, design.box.z);
  design.box.base_thickness = number(
    $("#base-thickness").value,
    design.box.base_thickness ?? 0.6,
  );
  design.label = $("#label-text").value;
  design.part_name = $("#part-name").value;
  design.scoop = $("#scoop").checked;
  // The rim label is the only label the design itself carries, and it always
  // lives on the rear ledge. Empty simply means there isn't one; floor
  // lettering is a text interior part in the layout.
  design.label_position = design.label.trim() ? "top" : "bottom";
  const newOutput = $("#output-folder").value.trim();
  if (newOutput !== state.output) {
    state.output = newOutput;
    saveOutputPreference(newOutput);
  }
  state.connector = {
    tolerance: number($("#connector-tolerance").value, state.connector.tolerance),
    length: number($("#connector-length").value, state.connector.length),
    height: state.connector.height,
    bin_a_height: number($("#connector-bin-a-height").value, state.design.box.z),
    bin_b_height: number($("#connector-bin-b-height").value, state.design.box.z),
    different_heights: $("#different-height-bins").checked,
    position: 0,
    axis: "y",
  };
  syncConnectorHeightControls();
}

const saveOutputPreference = debounce(output => {
  api("/api/preferences", { output }).catch(() => {});
}, 500);

async function selectOutputFolder() {
  const button = $("#output-folder-picker");
  const old = button.textContent;
  button.disabled = true;
  try {
    const result = await api("/api/browse-output-folder", { current: state.output });
    if (result.folder) {
      state.output = result.folder;
      $("#output-folder").value = result.folder;
      saveOutputPreference(result.folder);
      toast(`Selected: ${result.folder}`);
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function updatePreviewHelp(view) {
  $("#preview-help").textContent = view === "2d"
    ? "Drag interior parts to move them. Photo Nest also has a proportional resize corner and round rotation handle."
    : "Visual preview only. Drag to rotate, use the wheel to zoom, or double-click to reset; these controls do not change the printed part.";
}

const changedDesign = debounce(() => {
  if (state.designMutationBusy) return;
  const previousDesign = clone(state.design);
  updateDesignFromForm();
  recordHistory(previousDesign);
  // A cradle hugs its zone to the tool and the bin, so re-fit the open cradle
  // draft to the resized bin - otherwise a shrunk bin leaves its zone hanging
  // outside with a stale "reaches outside the bin" error.
  if (state.draft?.kind === "cradle") sizeCradleToItem(state.draft);
  refreshPreview();
  if (state.draft) refreshDraft();
}, 280);

// The largest straight-sided rectangle that fits a bin's wavy cavity - the
// same number the engine's BoxSpec.usable_inside returns, recomputed here so
// the cradle auto-sizer never has to wait on a preview round-trip to know how
// much floor it has. Browser designs are always fused/removable (no cartridge)
// and the flat-inside band does not touch this rectangle, so the plain formula
// is exact.
function binInsideExtent(box) {
  const WAVE_AMPLITUDE = 0.4, WAVE_LENGTH = 4.0, WAVE_MATING_GAP = 0.25;
  const slope = (WAVE_AMPLITUDE * 2 * Math.PI) / WAVE_LENGTH;
  const wallDepth = number(box.wall, 0.8) * Math.sqrt(1 + slope * slope);
  const trim = WAVE_MATING_GAP + 2 * wallDepth + 2 * WAVE_AMPLITUDE;
  return [Math.max(1, number(box.x) - trim), Math.max(1, number(box.y) - trim)];
}

function setSidebarCollapsed(collapsed) {
  const shell = $("#app-shell");
  const button = $("#sidebar-toggle");
  shell.classList.toggle("sidebar-collapsed", collapsed);
  button.setAttribute("aria-expanded", String(!collapsed));
  button.title = collapsed ? "Show controls" : "Hide controls";
  $("span", button).textContent = collapsed ? "Show controls" : "Hide controls";
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
  $("#sidebar-toggle").addEventListener("click", () => setSidebarCollapsed(!shell.classList.contains("sidebar-collapsed")));
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

function wireCameraControls() {
  $$('[data-camera-view]').forEach(button => button.addEventListener("click", () => setCameraView(button.dataset.cameraView)));
  $$('[data-camera-zoom]').forEach(button => button.addEventListener("click", () => {
    state.camera.zoom = Math.max(.35, Math.min(4, state.camera.zoom * (button.dataset.cameraZoom === "in" ? 1.2 : 1 / 1.2)));
    renderPreview3D();
  }));
}

function wireControls() {
  wireSidebar();
  wireCameraControls();
  $$(".section-heading").forEach(button => button.addEventListener("click", () => {
    const section = button.closest(".control-section");
    section.classList.toggle("open");
    button.setAttribute("aria-expanded", String(section.classList.contains("open")));
  }));

  $("#advanced-settings").addEventListener("change", event => {
    $("#advanced-build-settings").hidden = !event.target.checked;
  });

  ["#x-size", "#y-size", "#z", "#base-thickness", "#label-text", "#part-name"]
    .forEach(selector => $(selector).addEventListener("input", () => {
      state.canGenerate = false;
      updateGenerateAvailability();
      changedDesign();
    }));
  ["#x-size", "#y-size"].forEach(selector => $(selector).addEventListener("blur", () => {
    const input = $(selector);
    const unit = state.catalog.base_unit;
    const snapped = Math.max(unit, Math.round(number(input.value, unit) / unit) * unit);
    if (String(snapped) !== input.value) {
      input.value = String(snapped);
      flashField(input);
    }
  }));
  $("#scoop").addEventListener("change", () => {
    const previousDesign = clone(state.design);
    updateDesignFromForm();
    recordHistory(previousDesign);
    refreshPreview();
    if (state.draft) refreshDraft();
  });
  ["#output-folder", "#connector-tolerance", "#connector-length",
    "#connector-bin-a-height", "#connector-bin-b-height"]
    .forEach(selector => $(selector).addEventListener("change", updateDesignFromForm));
  ["#connector-bin-a-height", "#connector-bin-b-height"].forEach(selector =>
    $(selector).addEventListener("input", syncConnectorHeightControls));
  $("#different-height-bins").addEventListener("change", () => {
    if ($("#different-height-bins").checked && !state.connector.different_heights) {
      $("#connector-bin-a-height").value = fmt(state.design.box.z);
      $("#connector-bin-b-height").value = fmt(state.design.box.z);
    }
    updateDesignFromForm();
  });
  $("#output-folder-picker").addEventListener("click", selectOutputFolder);

  const viewTabs = $$(".view-tab");
  const activateView = tab => {
    $$(".view-tab").forEach(other => {
      other.classList.toggle("active", other === tab);
      other.setAttribute("aria-selected", String(other === tab));
      other.tabIndex = other === tab ? 0 : -1;
    });
    $$(".canvas-wrap").forEach(wrap => wrap.classList.toggle("active", wrap.dataset.canvas === tab.dataset.view));
    updatePreviewHelp(tab.dataset.view);
    requestAnimationFrame(() => tab.dataset.view === "3d" ? renderPreview3D() : renderLayout2D());
  };
  viewTabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateView(tab));
    tab.addEventListener("keydown", event => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const targetIndex = event.key === "Home" ? 0
        : event.key === "End" ? viewTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      activateView(viewTabs[targetIndex]);
      viewTabs[targetIndex].focus();
    });
  });
  activateView(viewTabs.find(tab => tab.classList.contains("active")) || viewTabs[0]);

  // This is the only control that starts another support. Palette choices
  // change the currently selected support instead.
  $("#add-support").addEventListener("click", () => selectKind(state.draftKind, true));
  $("#auto-expand-bin").addEventListener("click", autoExpandBin);
  $("#save-design").addEventListener("click", saveDesign);
  $("#open-design").addEventListener("change", openDesign);
  $("#new-design").addEventListener("click", newDesign);
  $("#undo-design").addEventListener("click", () => restoreHistory());
  $("#redo-design").addEventListener("click", () => restoreHistory(true));
  document.addEventListener("keydown", event => {
    if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
    if (event.target.closest("input, textarea, select, [contenteditable='true']")) return;
    if (event.key.toLowerCase() === "z") {
      event.preventDefault();
      restoreHistory(event.shiftKey);
    } else if (event.key.toLowerCase() === "y") {
      event.preventDefault();
      restoreHistory(true);
    }
  });
  $("#connection").addEventListener("click", () => location.reload(true));
  $("#update-banner-reload").addEventListener("click", () => location.reload(true));
  $("#print-bin").addEventListener("click", () => printModel("bin"));
  $("#generate-bin").addEventListener("click", () => generate("/api/generate", "#generate-bin"));
  $("#generate-connector").addEventListener("click", () => generate("/api/connector", "#generate-connector"));
  $("#generate-sampler").addEventListener("click", () => generate("/api/sampler", "#generate-sampler"));
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

// Nothing selected, nothing shown as a live draft - the state on first load
// and after New/Open/a delete/a mode switch with nothing selected. A
// palette button never doubles as "still working on the last shape you
// looked at": if none of them is highlighted, nothing has been added yet.
function clearDraftSelection() {
  state.draft = null;
  state.draftKind = null;
  state.draftAutoCommit = false;
  state.draftIsNew = false;
  state.draftSourceIndex = null;
  state.selected = null;
  $$(".support-choice").forEach(button => button.classList.remove("active"));
  $(".support-editor").hidden = true;
  $("#draft-status").textContent = "";
  $("#draft-status").classList.remove("error");
  updateInteriorModeVisibility();
  updateSelectionButtons();
}

function pickKind(kind) {
  updateInteriorModeVisibility(true);
  selectKind(kind);
}

async function selectKind(kind, reset = false) {
  updateInteriorModeVisibility(true);
  state.draftKind = kind;
  state.selected = reset ? null : state.selected;
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
    state.draft = result.feature;
    state.draftResolvedOptions = result.resolved_options || {};
    // What the engine started this text at, so the Part Name is only ever
    // seeded from lettering the user actually typed - never the placeholder.
    state.draftStartingText = result.feature?.options?.text ?? null;
    renderDraftFields();
    updateSelectionButtons();
    refreshDraft();
  } catch (error) {
    $("#draft-status").textContent = error.message;
    toast(error.message, true);
  }
}

function selectedFeature(index) {
  if (index === null || index < 0 || index >= state.design.layout.features.length) return;
  state.selected = index;
  state.draft = clone(state.design.layout.features[index]);
  state.draftAutoCommit = true;
  state.draftIsNew = false;
  state.draftSourceIndex = index;
  state.draftResolvedOptions = {};
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
  const placeholder = options.placeholder ? ` placeholder="${escapeHtml(options.placeholder)}"` : "";
  return `<label class="${classes}">${escapeHtml(label)}${options.unit ? `<span class="unit">${escapeHtml(options.unit)}</span>` : ""}
    <input type="${type}" data-draft="${key}" value="${escapeHtml(value ?? "")}" ${attrs}${placeholder}>
  </label>`;
}

// Fields that stay blank with explanatory grey placeholder text instead of
// showing the resolved number, for the one kind (so far) where knowing the
// exact auto-computed value matters less than knowing what "blank" means.
const AUTO_PLACEHOLDER = {
  divider: { height: "height of box", spacing: "fills evenly" },
};

function renderDraftFields() {
  if (!state.draft) return;
  const info = partInfo();
  const one = state.draft;
  const zone = one.zone;
  const width = zone[2] - zone[0];
  const depth = zone[3] - zone[1];
  let html = "";
  if (one.kind === "nest") {
    html += `<div class="photo-upload wide">
      <label class="button secondary photo-button" for="nest-photo-input">Upload part photo</label>
      <input id="nest-photo-input" type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp">
      <div><strong>Photo requirements</strong><ul>
        <li>Entire 8.5 × 11 in sheet visible</li>
        <li>Camera directly overhead</li>
        <li>Part lies flat</li>
        <li>Plain, high-contrast background preferred</li>
      </ul></div>
      ${one.contour ? `<p class="photo-measurement">Outline ready — move, rotate, or proportionally resize it in 2D.</p>` : ""}
    </div>`;
  }
  if (info.flags.text) {
    html += `<label class="wide">What it says
      <input type="text" maxlength="80" data-draft="option:text" value="${escapeHtml(one.options?.text ?? "")}" placeholder="e.g. M3">
    </label>`;
    html += `<label class="check-card wide">
      <input type="checkbox" data-draft="option:auto" ${one.options?.auto ? "checked" : ""}>
      <span><strong>Place it for me</strong><small>Keeps it centred where it fits, moving around the other interior parts as they change. Turn this off to put it exactly where you want.</small></span>
    </label>`;
    html += `<fieldset class="wide"><legend>Turn</legend><div class="segmented two">
      ${[0, 1, 2, 3].map(turn => `<label><input type="radio" name="draft-turns" value="${turn}" ${(number(one.options?.quarter_turns, 0) % 4) === turn ? "checked" : ""}><span>${turn * 90}°</span></label>`).join("")}
    </div></fieldset>`;
    html += `<label class="check-card wide">
      <input type="checkbox" data-draft="option:raised" ${one.options?.raised ? "checked" : ""}>
      <span><strong>Stand proud</strong><small>Letters sit on top of the floor instead of sunk flush into it. Either way they stay a separate object for a second filament.</small></span>
    </label>`;
  }
  if (info.flags.size && one.kind !== "cradle") {
    const isPocket = one.kind === "pocket";
    const wall = isPocket ? number(one.options?.wall, state.draftResolvedOptions?.wall ?? 1.6) : 0;
    const shownWidth = isPocket ? Math.max(0.1, width - 2 * wall) : width;
    const shownDepth = isPocket ? Math.max(0.1, depth - 2 * wall) : depth;
    const depthLabel = isPocket ? "Length" : "Depth";
    html += field("Width", "width", fmt(shownWidth), { unit: "mm", step: "1" });
    html += field(depthLabel, "depth", fmt(shownDepth), { unit: "mm", step: "1" });
  }
  if (info.flags.qty) {
    html += `<label class="wide">Quantity<div class="input-with-button">
      <input type="number" min="1" step="1" data-draft="count" value="${one.count ?? ""}" placeholder="auto">
      <button type="button" class="button secondary" data-action="auto-count">Auto</button>
    </div></label>`;
    // Unlike Cradle/Bore/Post, a divider's "auto" isn't "fit as many as
    // possible" - it's always a single centered wall, with Spacing (above)
    // doing the auto-fill work instead. Worth saying, since that reads as
    // the same "auto" everywhere else.
    if (info.kind === "divider") {
      html += `<p id="count-auto-hint" class="field-help" ${one.count == null ? "" : "hidden"}>Auto places a single, centered divider - set a number here for more.</p>`;
    }
  }
  if (info.flags.alternate) {
    html += `<label class="check-card wide">
      <input type="checkbox" data-draft="alternate_ends" ${one.alternate_ends === true ? "checked" : ""}>
      <span><strong>Alternate ends</strong><small>Places every second trough near the opposite end of the bin; each trough becomes a separate body.</small></span>
    </label>`;
  }
  if (info.flags.along) {
    html += `<fieldset class="wide"><legend>Runs along</legend><div class="segmented two">
      <label><input type="radio" name="draft-along" value="x" ${one.along === "x" ? "checked" : ""}><span>X direction</span></label>
      <label><input type="radio" name="draft-along" value="y" ${one.along === "y" ? "checked" : ""}><span>Y direction</span></label>
    </div></fieldset>`;
  }
  if (info.flags.alternate) {
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
    html += field(label, `option:${key}`, fmt(shown), { step: "1" });
    html += `<p class="field-help wide">${alternating
      ? "Share of the run kept clear at each end. Larger pulls the alternating troughs toward the middle; smaller pushes them to the ends."
      : "Slides the trough along the bin from centre, as a share of the room to the wall. Positive one way, negative the other; 0 stays centred."}</p>`;
  }
  if (info.flags.item) {
    const item = one.item || starterItem();
    const first = item.segments[0] || { length: 40, diameter: 6 };
    const isCradle = one.kind === "cradle";
    const isBore = one.kind === "bore";
    // Cradles and bores use measured dimensions. Photo Nest has no item fields.
    const measuredStep = isCradle ? "1" : undefined;
    if (!isBore) html += field("Length", "item_length", fmt(first.length), { unit: "mm", step: measuredStep });
    html += field("Diameter", "item_diameter", fmt(first.diameter), { unit: "mm", step: measuredStep });
    if (!isCradle) {
      html += `<label>Profile<select data-draft="profile">
        ${["round", "hex", "square"].map(profile => `<option value="${profile}" ${item.profile === profile ? "selected" : ""}>${profile[0].toUpperCase() + profile.slice(1)}</option>`).join("")}
      </select></label>`;
      html += field("Fit clearance", "clearance", fmt(item.clearance ?? 0.4), { unit: "mm" });
    }
    if (isCradle) {
      html += `<p class="field-help wide">Enter the tool's length and diameter. The cradle drops it into a half-circle notch and sizes its own ribs to the tool.</p>`;
    }
    if (isBore) {
      html += `<p class="field-help wide">Enter the widest diameter that must drop into the hole. The bore adds its own wall and fit clearance; set the hole's depth below.</p>`;
    }
  }
  for (const option of info.fields) {
    // Rendered together as the one "% from end / Offset from center" field
    // beneath Runs along, above.
    if (option.key === "end_margin" || option.key === "run_offset") continue;
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
    const autoHint = AUTO_PLACEHOLDER[info.kind]?.[option.key];
    const shown = !explicit && autoHint
      ? ""
      : explicit
      ? one.options[option.key]
      : state.draftResolvedOptions?.[option.key] ?? option.default;
    html += field(option.label, `option:${option.key}`, shown, autoHint ? { placeholder: autoHint } : {});
    if (option.key === "angle") {
      html += `<fieldset class="wide"><legend>Leaning shape</legend><div class="segmented two">
        <label><input type="radio" name="draft-wedge" value="wedge" ${one.wedge !== false ? "checked" : ""}><span>Wedge</span></label>
        <label><input type="radio" name="draft-wedge" value="straight" ${one.wedge === false ? "checked" : ""}><span>Straight</span></label>
      </div></fieldset>
      <p class="field-help">Only matters once the angle above is not zero. <strong>Wedge</strong> stays thick at the floor and tapers as it leans, so it takes the sideways push of whatever rests against it. <strong>Straight</strong> keeps the same thin thickness the whole way up and can snap off.</p>`;
    }
  }
  $("#draft-fields").innerHTML = html;
  const photoInput = $("#nest-photo-input", $("#draft-fields"));
  if (photoInput) photoInput.addEventListener("change", uploadNestPhoto);
  $$('[data-draft]', $("#draft-fields")).forEach(input => {
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", updateDraftFromFields);
  });
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
    state.draft.along = input.value;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-wedge"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    state.draft.wedge = input.value === "wedge";
    state.draftAutoCommit = true;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-turns"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
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
    state.draft.count = null;
    if (state.draft.kind === "cradle") sizeCradleToItem(state.draft);
    state.draftAutoCommit = true;
    const input = $('[data-draft="count"]', $("#draft-fields"));
    if (input) input.value = "";
    syncCountAutoHint();
    updateSelectionButtons();
    refreshDraftSoon();
  });
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
    shownField.value = fmt(newSpan);
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
  const spacing = number(one.options?.spacing, state.draftResolvedOptions?.spacing ?? 0);
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

  const oneLane = diameter + rib;
  const pitch = diameter + rib / 2 + spacing;
  const run = spansRun ? roomAlong : Math.min(roomAlong, Math.max(1, Math.ceil(length)));
  const across = auto
    ? roomAcross
    : Math.min(roomAcross, Math.max(1, Math.ceil(oneLane + (count - 1) * pitch)));

  const width = one.along === "x" ? run : across;
  const depth = one.along === "x" ? across : run;
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
}

function syncNestZone(one) {
  if (!one?.contour?.length) return;
  const cx = (one.zone[0] + one.zone[2]) / 2;
  const cy = (one.zone[1] + one.zone[3]) / 2;
  const angle = number(one.rotation) * Math.PI / 180;
  const scale = Math.max(.05, number(one.scale, 1));
  const cosine = Math.cos(angle), sine = Math.sin(angle);
  const points = one.contour.map(([x, y]) => [
    scale * (number(x) * cosine - number(y) * sine),
    scale * (number(x) * sine + number(y) * cosine),
  ]);
  const xs = points.map(point => point[0]), ys = points.map(point => point[1]);
  const margin = Math.max(0, number(one.options?.clearance, .6))
    + Math.max(0, number(one.options?.rim, 3));
  const width = Math.max(...xs) - Math.min(...xs) + 2 * margin;
  const depth = Math.max(...ys) - Math.min(...ys) + 2 * margin;
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
}

function readFileDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error("The selected photo could not be read."));
    reader.readAsDataURL(file);
  });
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
  let mutationStarted = false;
  $("#draft-status").textContent = "Finding letter paper and tracing the part…";
  try {
    const image = await readFileDataUrl(file);
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
    state.draftAutoCommit = true;
    state.drafts = {};
    syncForm();
    renderDraftFields();
    await refreshPreview();
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    $('.view-tab[data-view="2d"]').click();
    toast(`Photo Nest ready: ${fmt(result.outline.width)} × ${fmt(result.outline.depth)} mm outline.`);
  } catch (error) {
    $("#draft-status").textContent = error.message;
    $("#draft-status").classList.add("error");
    toast(error.message, true, 6500);
  } finally {
    input.value = "";
    if (mutationStarted) finishDesignMutation();
  }
}

function updateDraftFromFields(event) {
  // Any deliberate edit is a strong enough signal to start saving this draft
  // as it goes, even if the app put it up on its own (see state.draftAutoCommit).
  state.draftAutoCommit = true;
  state.canGenerate = false;
  updateGenerateAvailability();
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
    item.profile = isCradle ? "round" : (get("profile") || "round");
    // A cradle ignores fit slack entirely, so it has no clearance field - keep
    // the stored value at 0 rather than a stale 0.4 nothing reads.
    item.clearance = isCradle ? 0 : number(get("clearance"), item.clearance ?? 0.4);
    const first = {
      length: number(get("item_length"), item.segments?.[0]?.length || 40),
      diameter: number(get("item_diameter"), item.segments?.[0]?.diameter || 6),
    };
    item.segments = [first];
    one.item = item;
  }
  one.options ||= {};
  const changed = event?.currentTarget?.dataset?.draft || "";
  // Text carries the only options that are not numbers: what it says, and two
  // plain yes/no choices. Read them straight off their own controls.
  if (info.flags.text) {
    const fields = $("#draft-fields");
    const said = $('[data-draft="option:text"]', fields);
    if (said) one.options.text = said.value;
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
  if (changed.startsWith("option:") &&
      !["text", "auto", "raised"].includes(changed.slice("option:".length))) {
    const key = changed.slice("option:".length);
    const option = info.fields.find(entry => entry.key === key);
    const raw = String(get(changed) ?? "").trim();
    if (raw === "") delete one.options[key];
    else one.options[key] = number(
      raw,
      one.options[key] ?? state.draftResolvedOptions?.[key] ?? number(option?.default),
    );
    // A hand-set letter height means the user is placing it themselves.
    if (info.flags.text && key === "cap_height" && raw !== "") {
      one.options.auto = false;
      const autoField = $('[data-draft="option:auto"]', $("#draft-fields"));
      if (autoField) autoField.checked = false;
    }
    if (info.kind === "divider" && key === "thickness") {
      widenDividerFootprint(one);
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
    if (info.kind === "divider" && key === "angle" && one.wedge !== false) {
      // A wedge keeps its back face flat and only tapers the leaning face,
      // so a steep angle on a tall divider can taper that face down to
      // nothing before it reaches the top. Rather than block the angle,
      // widen the wall (Width mm) just enough to keep a printable edge up
      // there, and flash that field since its value just changed on its own.
      const angle = one.options.angle ?? 0;
      const height = one.options.height ?? state.draftResolvedOptions?.height;
      if (Number.isFinite(angle) && Number.isFinite(height) && height > 0) {
        const lean = Math.abs(height * Math.tan((angle * Math.PI) / 180));
        const required = Math.ceil((lean + MIN_WEDGE_EDGE_MM) * 10) / 10;
        const current = one.options.thickness ?? state.draftResolvedOptions?.thickness ?? 1.6;
        if (required > current) {
          one.options.thickness = required;
          const thicknessField = $('[data-draft="option:thickness"]', $("#draft-fields"));
          if (thicknessField) thicknessField.value = fmt(required);
          flashField(thicknessField);
          widenDividerFootprint(one);
        }
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
  // Toggling Alternate ends swaps the field beneath Runs along between
  // "% from end" and "Offset from center".
  if (changed === "alternate_ends") renderDraftFields();
  updateSelectionButtons();
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
    const result = await api("/api/feature/draft", { design: state.design, feature: state.draft });
    if (request !== state.draftRequest) return;
    state.draftResolvedOptions = result.resolved_options || {};
    const info = partInfo();
    const autoHints = AUTO_PLACEHOLDER[info.kind] || {};
    for (const option of info.fields) {
      if (option.key in autoHints) continue; // stays blank with its placeholder, not a filled number
      if (Object.prototype.hasOwnProperty.call(state.draft.options || {}, option.key)) continue;
      const input = $(`[data-draft="option:${option.key}"]`, $("#draft-fields"));
      if (input && Object.prototype.hasOwnProperty.call(state.draftResolvedOptions, option.key)) {
        input.value = fmt(state.draftResolvedOptions[option.key]);
      }
    }
    $("#draft-status").textContent = "";
    $("#draft-status").classList.remove("error");
    if (state.draftAutoCommit) await autoCommitDraft(request);
  } catch (error) {
    if (request !== state.draftRequest) return;
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
    const previousDesign = clone(state.design);
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    if (request !== state.draftRequest) return;
    state.design = result.design;
    seedPartNameFromText(state.draft);
    recordHistory(previousDesign);
    state.draftIsNew = false;
    if (Number.isInteger(result.selected)) state.draftSourceIndex = result.selected;
    if (state.selected === null) state.selected = result.selected;
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

async function deleteSupportAt(index) {
  if (index === null || index === undefined || !beginDesignMutation()) return;
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
  } catch (error) {
    toast(error.message, true);
  } finally {
    finishDesignMutation();
  }
}

function mutationControls() {
  return $$(
    '#x-size, #y-size, #z, #base-thickness, #label-text, #part-name, ' +
    '#scoop, input[name="layout-mode"], ' +
    '#new-design, #open-design, #save-design'
  );
}

function beginDesignMutation() {
  if (state.designMutationBusy) {
    toast("Finish the current design change first.", true);
    return false;
  }
  updateDesignFromForm();
  state.designMutationBusy = true;
  state.previewRequest += 1;
  mutationControls().forEach(control => control.disabled = true);
  updateSelectionButtons();
  updateHistoryButtons();
  updateGenerateAvailability();
  return true;
}

function finishDesignMutation() {
  state.designMutationBusy = false;
  mutationControls().forEach(control => control.disabled = false);
  updateSelectionButtons();
  updateHistoryButtons();
  updateGenerateAvailability();
}

function updateSelectionButtons() {
  const busy = state.designMutationBusy;
  $("#add-support").disabled = busy || !state.draft;
  const hasPhotoNest = state.design?.layout?.features?.some(one => one.kind === "nest" && one.contour);
  const hasPlacedPart = Boolean(state.design?.layout?.features?.length);
  const replacingPhotoNest = hasPhotoNest && state.selected !== null &&
    state.design.layout.features[state.selected]?.kind === "nest";
  $("#add-support").hidden = !hasPlacedPart || hasPhotoNest || state.draft?.kind === "nest";
  $$(".support-choice").forEach(button => {
    button.disabled = busy || (hasPhotoNest && !replacingPhotoNest && button.dataset.kind !== "nest");
  });
  $$(".placed-item-select, .placed-item-delete").forEach(button => button.disabled = busy);
  $("#support-count").textContent = `${state.design?.layout.features.length || 0} placed`;
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
      const title = escapeHtml(partInfo(one.kind)?.title || one.kind);
      const specs = `${fmt(width)} × ${fmt(depth)} mm`;
      return `<div class="placed-item ${index === state.selected ? "selected" : ""}" style="--support-color:${kindColor(one.kind)}">
        <button type="button" class="placed-item-select" data-index="${index}">
          <span class="placed-item-icon">${iconFor(one.kind)}</span>
          <span class="placed-item-copy"><strong>${title}</strong><span>${specs}</span></span>
        </button>
        <button type="button" class="placed-item-delete" data-index="${index}" title="Delete this interior part" aria-label="Delete ${title}">✕</button>
      </div>`;
    }).join("");
    $$(".placed-item-select", container).forEach(button => button.addEventListener("click", () => selectedFeature(Number(button.dataset.index))));
    $$(".placed-item-delete", container).forEach(button => button.addEventListener("click", () => deleteSupportAt(Number(button.dataset.index))));
  }
  $("#support-count").textContent = `${features.length} placed`;
  $("#design-summary").textContent = features.length
    ? `${features.length} interior part${features.length === 1 ? "" : "s"} · ${state.design.layout.mode}`
    : `No interior parts placed · ${state.design.layout.mode}`;

  // With a single support there's nothing to choose between, so drop straight
  // into its settings rather than make the user pick it out of the list first.
  // selectedFeature() sets state.selected, so the re-entrant renderPlaced() it
  // triggers falls through here instead of looping.
  if (features.length === 1 && state.selected === null && !state.draft) {
    selectedFeature(0);
  }
}

async function refreshPreview() {
  const request = ++state.previewRequest;
  state.canGenerate = false;
  updateGenerateAvailability();
  $("#preview-state").textContent = "Building preview…";
  setError();
  try {
    const payload = { design: state.design };
    if (state.draft && !(state.draft.kind === "nest" && !state.draft.contour)) payload.draft = state.draft;
    const result = await api("/api/preview", payload);
    if (request !== state.previewRequest) return;
    state.preview = result;
    state.design = result.design;
    const previewHasErrors = !result.fits || result.feature_errors.length || result.draft_error;
    $("#preview-state").textContent = previewHasErrors ? "Design needs attention" : "Preview current";
    $("#inside-size").textContent = result.dimensions.size;
    $(".dimension-width", $("#dimensions")).textContent = `Width ${fmt(state.design.box.x)} mm`;
    $(".dimension-depth", $("#dimensions")).textContent = `Depth ${fmt(state.design.box.y)} mm`;
    $(".dimension-height", $("#dimensions")).textContent = `Height ${fmt(state.design.box.z)} mm`;
    const messages = [result.message, ...result.feature_errors, result.draft_error].filter(Boolean);
    const actions = [];
    if (result.message) actions.push({
      message: result.message,
      activate: () => {
        const input = $("#label-text");
        input.scrollIntoView({ behavior: "smooth", block: "center" });
        input.focus();
        flashField(input);
      },
    });
    result.feature_errors.forEach((message, errorIndex) => {
      const featureIndex = result.invalid_feature_indexes?.[errorIndex];
      actions.push({
        message: featureIndex === undefined ? message : `Interior part ${featureIndex + 1}: ${message}`,
        activate: () => {
          if (featureIndex === undefined) return;
          selectedFeature(featureIndex);
          $(".support-editor").scrollIntoView({ behavior: "smooth", block: "center" });
          flashField($(".support-editor"));
        },
      });
    });
    if (result.draft_error) actions.push({
      message: `Current interior part: ${result.draft_error}`,
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
    // The rim-label fit message is about the Rim label field specifically, so
    // show it right there too - the workspace panel above is easy to miss
    // since it sits far from the field the user is actually typing in.
    const labelError = $("#label-error");
    labelError.textContent = !result.fits && result.message ? result.message : "";
    labelError.hidden = !labelError.textContent;
    // An auto text part places itself server-side, so adopt the zones the
    // preview resolved - otherwise the next edit would send the stale ones.
    adoptResolvedFeatures(result.design?.layout?.features);
    state.textMeta = result.text_meta || [];
    state.fitError = Boolean(result.feature_errors.length || result.draft_error);
    updateAutoExpandButton();
    renderPreview3D();
    renderLayout2D();
    renderPlaced();
  } catch (error) {
    if (request !== state.previewRequest) return;
    $("#preview-state").textContent = "Preview could not build";
    setError(error.message);
    state.canGenerate = false;
    updateGenerateAvailability();
    $("#label-error").hidden = true;
    $("#label-error").textContent = "";
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

// "Auto Expand Bin" shows only while an interior part does not fit; clicking it
// grows the bin (see /api/layout/expand) to the smallest size that holds them all.
function updateAutoExpandButton() {
  const hasParts = Boolean(
    state.design?.layout?.features?.length || state.draft
  );
  $("#auto-expand-bin").hidden = !(state.fitError && hasParts);
}

async function autoExpandBin() {
  if (!beginDesignMutation()) return;
  const button = $("#auto-expand-bin");
  button.disabled = true;
  try {
    // Grow for what the user is actually looking at: an open draft may hold
    // edits (a flipped direction, a raised count) that never committed because
    // they don't fit yet. Fold it in - appended if new, in place if it's the
    // selected support being edited.
    const layout = state.design.layout;
    let features = layout.features;
    if (state.draft) {
      features = state.selected === null
        ? [...layout.features, state.draft]
        : layout.features.map((f, i) => i === state.selected ? state.draft : f);
    }
    const design = features === layout.features
      ? state.design
      : { ...state.design, layout: { ...layout, features } };
    const previousDesign = clone(state.design);
    const result = await api("/api/layout/expand", { design });
    state.design = result.design;
    recordHistory(previousDesign);
    clearDraftSelection();
    syncForm();
    state.fitError = false;
    updateAutoExpandButton();
    await refreshPreview();
    toast(result.grew
      ? `Bin expanded to ${fmt(result.box.x)} × ${fmt(result.box.y)} mm.`
      : "The interior parts already fit - bin unchanged.");
  } catch (error) {
    toast(error.message, true, 5000);
  } finally {
    button.disabled = false;
    finishDesignMutation();
  }
}

function kindColor(kind) {
  if (COLORS[kind]) return COLORS[kind];
  if (kind === "draft_invalid") return COLORS.invalid;
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
  context.clearRect(0, 0, width, height);
  state.previewSupportPolygons = [];
  if (!geometry?.length) {
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText("No geometry", width / 2, height / 2);
    return;
  }
  const vector = cameraVector(camera);
  const faces = geometry.map(face => {
    const points = face.points.map(point => iso(point, camera));
    const depth = face.points.reduce((sum, point) => sum + dot(point, vector), 0) / face.points.length;
    const facing = dot(face.normal, vector);
    return { ...face, projected: points, depth, facing };
  }).filter(face => face.facing > 0 || face.kind === "label_hole");
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
  const pad = Math.max(34, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY) * camera.zoom;
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const project = point => [width / 2 + (point[0] - midX) * scale, height / 2 + (point[1] - midY) * scale];
  faces.sort((a, b) => a.depth - b.depth || number(a.layer) - number(b.layer));
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
    const light = .78 + Math.max(0, Math.min(1, face.facing)) * .35;
    context.fillStyle = shade(base, light);
    context.fill();
    const isDraft = face.kind.startsWith("draft_");
    context.strokeStyle = isDraft ? "rgba(196,131,20,.5)" : "rgba(38,65,75,.13)";
    context.lineWidth = isDraft ? .6 : .35;
    context.stroke();
  }
}

function renderPreview3D() {
  if (!state.preview) return;
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

function renderLayout2D() {
  if (!state.preview) return;
  const canvas = $("#preview-2d");
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
  const bounds = state.preview.layout_bounds;
  const worldWidth = bounds[2] - bounds[0], worldHeight = bounds[3] - bounds[1];
  const pad = Math.max(42, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / worldWidth, (height - 2 * pad) / worldHeight);
  const cx = (bounds[0] + bounds[2]) / 2, cy = (bounds[1] + bounds[3]) / 2;
  const toCanvas = ([x, y]) => [width / 2 + (x - cx) * scale, height / 2 - (y - cy) * scale];
  const toWorld = ([x, y]) => [cx + (x - width / 2) / scale, cy - (y - height / 2) / scale];
  state.layoutTransform = { toCanvas, toWorld, scale };
  const a = toCanvas([bounds[0], bounds[3]]), b = toCanvas([bounds[2], bounds[1]]);
  const cavity = state.preview.cavity_outline;
  const cavityPath = new Path2D();
  if (cavity && cavity.length) {
    cavity.forEach((point, index) => {
      const p = toCanvas(point);
      index === 0 ? cavityPath.moveTo(p[0], p[1]) : cavityPath.lineTo(p[0], p[1]);
    });
    cavityPath.closePath();
  } else {
    cavityPath.rect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
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
      const p = toCanvas([x, 0]); context.beginPath(); context.moveTo(p[0], a[1]); context.lineTo(p[0], b[1]); context.stroke();
    }
    for (let y = bounds[1] + pitch; y < bounds[3] - 1e-8; y += pitch) {
      const p = toCanvas([0, y]); context.beginPath(); context.moveTo(a[0], p[1]); context.lineTo(b[0], p[1]); context.stroke();
    }
  }
  context.restore();
  // The flat rectangle every non-full-span support must still stay inside,
  // drawn as a reference against the true wavy wall around it.
  context.strokeStyle = "rgba(94,127,136,.55)";
  context.lineWidth = 1;
  context.setLineDash([4, 3]);
  context.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
  context.setLineDash([]);
  for (const reserved of state.preview.customization_zones) {
    const r0 = toCanvas([reserved.zone[0], reserved.zone[3]]), r1 = toCanvas([reserved.zone[2], reserved.zone[1]]);
    context.fillStyle = "rgba(201,95,88,.13)";
    context.strokeStyle = "rgba(164,68,61,.55)";
    context.setLineDash([5, 4]);
    context.fillRect(r0[0], r0[1], r1[0] - r0[0], r1[1] - r0[1]);
    context.strokeRect(r0[0], r0[1], r1[0] - r0[0], r1[1] - r0[1]);
    context.setLineDash([]);
    context.fillStyle = "#8f4540";
    context.font = "11px Segoe UI";
    context.fillText(reserved.name, r0[0] + 6, r0[1] + 15);
  }
  const invalid = new Set(state.preview.invalid_feature_indexes || []);
  layoutFeatures().forEach((feature, index) => {
    const p0 = toCanvas([feature.zone[0], feature.zone[3]]), p1 = toCanvas([feature.zone[2], feature.zone[1]]);
    const color = invalid.has(index) ? COLORS.invalid : kindColor(feature.kind);
    context.strokeStyle = index === state.selected ? "#176e91" : shade(color, .72);
    context.lineWidth = index === state.selected ? 3 : 1.2;
    if (feature.kind === "nest" && feature.contour) {
      const outline = drawClosedPath(context, nestOutlineWorld(feature, state.preview.nest_soft_contours?.[index]), toCanvas);
      context.fillStyle = color + "35";
      context.fill(outline);
      context.stroke(outline);
    } else {
      // A fused cradle, post or divider fills less of its zone than the zone
      // itself, and the rest is floor a neighbour may use. Fill what the part
      // really covers and leave the zone as a faint outline around it, so the
      // difference between "mine" and "just my handle" is visible.
      const covered = footprintWorld(feature, index);
      const f0 = covered && toCanvas([covered[0], covered[3]]);
      const f1 = covered && toCanvas([covered[2], covered[1]]);
      context.fillStyle = color + "cc";
      context.fillRect(...(covered ? [f0[0], f0[1], f1[0] - f0[0], f1[1] - f0[1]]
                                   : [p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]]));
      if (covered) {
        context.strokeRect(f0[0], f0[1], f1[0] - f0[0], f1[1] - f0[1]);
        context.save();
        context.globalAlpha = .45;
        context.setLineDash([4, 3]);
      }
      context.strokeRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
      if (covered) context.restore();
      if (feature.kind === "pocket") {
        const wall = number(feature.options?.wall, 1.6);
        const i0 = toCanvas([feature.zone[0] + wall, feature.zone[3] - wall]);
        const i1 = toCanvas([feature.zone[2] - wall, feature.zone[1] + wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.4)";
        context.fillRect(i0[0], i0[1], i1[0] - i0[0], i1[1] - i0[1]);
        context.strokeStyle = shade(color, 0.5);
        context.lineWidth = 1;
        context.strokeRect(i0[0], i0[1], i1[0] - i0[0], i1[1] - i0[1]);
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
      context.fillStyle = "rgba(20,36,42,.82)";
      context.font = "600 11px Segoe UI";
      context.textAlign = "center";
      context.textBaseline = "middle";
      const [tx, ty] = covered ? [(f0[0] + f1[0]) / 2, (f0[1] + f1[1]) / 2]
                               : [(p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2];
      context.fillText(partInfo(feature.kind)?.title || feature.kind, tx, ty);
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
      }
    }
  });
  if (state.draft) {
    const zone = state.draft.zone;
    const p0 = toCanvas([zone[0], zone[3]]), p1 = toCanvas([zone[2], zone[1]]);
    context.fillStyle = DRAFT_HIGHLIGHT + "55";
    context.strokeStyle = DRAFT_HIGHLIGHT;
    context.lineWidth = 2;
    context.setLineDash([6, 3]);
    if (state.draft.kind === "nest" && state.draft.contour) {
      const outline = drawClosedPath(context, nestOutlineWorld(state.draft, state.preview.draft_soft_contour), toCanvas);
      context.fill(outline); context.stroke(outline);
    } else if (state.draft.kind !== "nest") {
      // Same as a placed support: fill the floor it really covers, outline the
      // zone it lives in.
      const covered = state.preview.draft_footprint;
      if (covered) {
        const d0 = toCanvas([covered[0], covered[3]]), d1 = toCanvas([covered[2], covered[1]]);
        context.fillRect(d0[0], d0[1], d1[0] - d0[0], d1[1] - d0[1]);
        context.strokeRect(d0[0], d0[1], d1[0] - d0[0], d1[1] - d0[1]);
      } else {
        context.fillRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
      }
      context.strokeRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
      if (state.draft.kind === "pocket") {
        const wall = number(state.draft.options?.wall, state.draftResolvedOptions?.wall ?? 1.6);
        const i0 = toCanvas([zone[0] + wall, zone[3] - wall]);
        const i1 = toCanvas([zone[2] - wall, zone[1] + wall]);
        context.save();
        context.fillStyle = "rgba(255, 255, 255, 0.35)";
        context.fillRect(i0[0], i0[1], i1[0] - i0[0], i1[1] - i0[1]);
        context.strokeStyle = DRAFT_HIGHLIGHT;
        context.lineWidth = 1;
        context.strokeRect(i0[0], i0[1], i1[0] - i0[0], i1[1] - i0[1]);
        context.restore();
      }
    }
    context.setLineDash([]);
  }
  drawDimensionLine(context, [a[0], a[1] - 18], [b[0], a[1] - 18], `Width ${fmt(state.design.box.x)} mm`);
  drawDimensionLine(context, [a[0] - 18, a[1]], [a[0] - 18, b[1]], `Depth ${fmt(state.design.box.y)} mm`, true);
}

function layoutPoint(event) {
  const rect = $("#preview-2d").getBoundingClientRect();
  return state.layoutTransform.toWorld([event.clientX - rect.left, event.clientY - rect.top]);
}

function hitFeature(world) {
  const features = state.design.layout.features;
  for (let index = features.length - 1; index >= 0; index--) {
    const zone = features[index].zone;
    if (features[index].kind === "nest" && features[index].contour) {
      if (index === state.selected && state.layoutTransform) {
        const cx = (zone[0] + zone[2]) / 2;
        const handles = [[zone[2], zone[1]], [cx, zone[3] + 8]];
        if (handles.some(point => Math.hypot(
          (world[0] - point[0]) * state.layoutTransform.scale,
          (world[1] - point[1]) * state.layoutTransform.scale,
        ) < 14)) return index;
      }
      if (pointInPolygon(world, nestOutlineWorld(features[index], state.preview?.nest_soft_contours?.[index]))) return index;
      continue;
    }
    if (world[0] >= zone[0] && world[0] <= zone[2] && world[1] >= zone[1] && world[1] <= zone[3]) return index;
  }
  return null;
}

function wireLayoutInteraction() {
  const canvas = $("#preview-2d");
  canvas.addEventListener("pointerdown", event => {
    if (!state.layoutTransform || state.designMutationBusy) return;
    const world = layoutPoint(event);
    let index = hitFeature(world);
    if (index === null) {
      state.selected = null;
      state.layoutDrag = null;
      renderPlaced(); updateSelectionButtons(); renderLayout2D();
      return;
    }
    if (index !== state.selected) selectedFeature(index);
    const feature = clone(state.design.layout.features[index]);
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
    state.layoutDrag = {
      index, feature, original: clone(feature),
      mode: feature.kind === "nest" && rotatePixels < 14 ? "rotate" : (resizable && handlePixels < 14) ? "resize" : "move",
      start: world,
      centre,
      startAngle: Math.atan2(world[1] - centre[1], world[0] - centre[0]),
      startRadius: Math.max(.01, Math.hypot(world[0] - centre[0], world[1] - centre[1])),
    };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    const drag = state.layoutDrag;
    if (!drag || !state.layoutTransform) return;
    const world = layoutPoint(event);
    const pitch = state.design.layout.mode === "cartridge" ? 8 : 1;
    const snap = value => Math.round(value / pitch) * pitch;
    const original = drag.original.zone;
    if (drag.mode === "move") {
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
    const drag = state.layoutDrag;
    if (!drag) return;
    state.layoutDrag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (typeof drag.index !== "number") return;   // not a feature drag - nothing to apply
    state.draft = drag.feature;
    const applied = await applySupport(drag.index);
    if (!applied) {
      state.draft = clone(state.design.layout.features[drag.index]);
      renderDraftFields();
      refreshDraft();
      renderLayout2D();
    }
  });
}

function saveDesign() {
  updateDesignFromForm();
  const body = JSON.stringify(state.design, null, 2) + "\n";
  const blob = new Blob([body], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${(state.design.part_name || "Wavefinity design").replace(/[^a-z0-9 _-]/gi, "").trim() || "Wavefinity design"}.wavefinity.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  toast("Design downloaded.");
}

async function openDesign(event) {
  const file = event.target.files?.[0];
  if (!file || !beginDesignMutation()) return;
  try {
    const parsed = JSON.parse(await file.text());
    const result = await api("/api/design/validate", { design: parsed });
    state.design = result.design;
    state.drafts = {};
    state.history = [];
    state.future = [];
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
  if (state.design.layout.features.length && !window.confirm("Start a new design and clear the placed interior parts?")) return;
  if (!beginDesignMutation()) return;
  const previousDesign = clone(state.design);
  state.design = clone(state.catalog.defaults.design);
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

async function generate(path, selector) {
  if (state.designMutationBusy) {
    toast("Finish the current design change before generating files.", true);
    return;
  }
  updateDesignFromForm();
  const button = $(selector);
  const old = button.textContent;
  button.disabled = true;
  button.textContent = "Generating…";
  setError();
  try {
    // A debounced support edit may still be visible only in the draft. Save
    // it now so the exported files always match the canvas.
    if (state.draft && state.draftAutoCommit && draftCommitIndex() !== false) {
      state.draftRequest += 1;
      const previousDesign = clone(state.design);
      const committed = await api("/api/feature/apply", {
        design: state.design, feature: state.draft, index: draftCommitIndex(),
      });
      state.design = committed.design;
      state.draftIsNew = false;
      if (Number.isInteger(committed.selected)) state.draftSourceIndex = committed.selected;
      if (state.selected === null) state.selected = committed.selected;
      recordHistory(previousDesign);
      renderPlaced();
    }
    const payload = {
      design: state.design,
      output: state.output,
      connector: state.connector,
    };
    const result = await api(path, payload);
    const files = collectOutputs(result.result);
    toast(`Saved to ${result.output}${files.length ? `\n${files.join("\n")}` : ""}`, false, 7000);
  } catch (error) {
    setError(error.message);
    toast(error.message, true, 7000);
  } finally {
    button.disabled = selector === "#generate-bin" ? !state.canGenerate : false;
    button.textContent = old;
  }
}

async function printModel(target = "bin") {
  if (!state.slicer || !state.slicer.available) {
    toast("Bambu Studio is not installed or could not be found. Please install Bambu Studio or click 'Change slicer' to locate the executable.", true, 8000);
    return;
  }
  if (state.designMutationBusy) {
    toast("Finish the current design change before printing.", true);
    return;
  }
  updateDesignFromForm();
  const button = $("#print-bin");
  const old = button.textContent;
  button.disabled = true;
  const slicerName = state.slicer?.name || "Bambu Studio";
  button.textContent = `Sending to ${slicerName}…`;
  setError();
  try {
    if (state.draft && state.draftAutoCommit && draftCommitIndex() !== false) {
      state.draftRequest += 1;
      const previousDesign = clone(state.design);
      const committed = await api("/api/feature/apply", {
        design: state.design, feature: state.draft, index: draftCommitIndex(),
      });
      state.design = committed.design;
      state.draftIsNew = false;
      if (Number.isInteger(committed.selected)) state.draftSourceIndex = committed.selected;
      if (state.selected === null) state.selected = committed.selected;
      recordHistory(previousDesign);
      renderPlaced();
    }
    const payload = {
      design: state.design,
      output: state.output,
      connector: state.connector,
      target: target,
    };
    const result = await api("/api/print", payload);
    const files = result.files || [];
    const fileNames = files.map(f => f.split(/[\\/]/).pop());
    toast(`Sent to ${slicerName}!\n${fileNames.join("\n")}`, false, 7000);
  } catch (error) {
    setError(error.message);
    toast(error.message, true, 8000);
  } finally {
    button.disabled = !state.canGenerate;
    button.textContent = old;
  }
}

function updateSlicerUI() {
  const statusEl = $("#slicer-status-text");
  const printBtn = $("#print-bin");
  if (!statusEl) return;
  const slicer = state.slicer || {};
  if (slicer.available) {
    statusEl.innerHTML = `<span class="slicer-status-dot"></span>${slicer.name || "Bambu Studio"}: Ready`;
    if (printBtn) {
      printBtn.textContent = "Print";
      printBtn.title = `Send directly to ${slicer.name || "Bambu Studio"}`;
    }
  } else {
    statusEl.innerHTML = `<span class="slicer-status-dot missing"></span>Bambu Studio: Not found`;
    if (printBtn) {
      printBtn.textContent = "Print";
      printBtn.title = "Bambu Studio is not installed - click 'Change slicer' to locate executable";
    }
  }
}

async function browseSlicer() {
  try {
    const result = await api("/api/browse-slicer-path");
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

async function init() {
  try {
    const catalog = await api("/api/catalog");
    state.catalog = catalog;
    state.serverInstance = catalog.instance;
    state.design = clone(catalog.defaults.design);
    state.output = catalog.preferences?.output || catalog.defaults.output;
    state.connector = clone(catalog.defaults.connector);
    state.slicer = catalog.slicer || { available: false, path: null, name: "Bambu Studio" };
    updateSlicerUI();
    renderCatalog();
    wireControls();
    syncForm();
    $("#connection").textContent = "Local engine connected";
    $("#connection").classList.add("ready");
    watchServerVersion();
    updateHistoryButtons();
    clearDraftSelection();
    await refreshPreview();
  } catch (error) {
    $("#connection").textContent = "Engine unavailable";
    setError(error.message);
    toast(error.message, true, 8000);
  }
}

init();
