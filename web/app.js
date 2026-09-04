"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  catalog: null,
  design: null,
  preview: null,
  draftKind: "divider",
  draft: null,
  draftResolvedOptions: {},
  draftGeometry: [],
  selected: null,
  camera: { yaw: 45, elevation: 76, zoom: 1 },
  draftCamera: { yaw: 45, elevation: 58, zoom: 1 },
  previewRequest: 0,
  draftRequest: 0,
  output: "",
  connector: {},
  selectedOriginal: null,
  layoutDrag: null,
  layoutTransform: null,
  designMutationBusy: false,
};

const COLORS = {
  outside: "#8ea8b2", inside: "#c9d9dc", rim: "#6f8f99", floor: "#e8efef",
  label: "#315766", label_hole: "#e8efef", top_label_ledge: "#7799a3",
  scoop: "#a9bec3", insert_base: "#c5ab83", invalid: "#c95f58",
  cradle: "#e59f54", nest: "#df8d5b", bore: "#6fb98f", post: "#51a5a1",
  divider: "#9d86c8", pocket: "#d4778c", slot: "#d5b84d",
};
const INSERT_TINT = "#c2a075";
const INSERT_TINT_MIX = .5;

function clone(value) {
  return JSON.parse(JSON.stringify(value));
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

function setError(message = "") {
  const panel = $("#error-panel");
  panel.hidden = !message;
  panel.textContent = message;
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
    slot: '<path d="M4 25h24V8H4zM9 20V11m5 9V11m5 9V11m5 9V11"/>',
    bore: '<rect x="4" y="5" width="24" height="22" rx="2"/><circle cx="11" cy="12" r="3"/><circle cx="21" cy="12" r="3"/><circle cx="11" cy="21" r="3"/><circle cx="21" cy="21" r="3"/>',
    cradle: '<path d="M4 24h24M7 24V9m18 15V9M7 11c3 0 3 5 6 5s3-5 6-5 3 5 6 5"/>',
    nest: '<rect x="3" y="6" width="26" height="20" rx="3"/><path d="M7 17h6v-6h7v4h5v6H7z"/>',
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
      try {
        const result = await api("/api/layout/mode", { design: state.design, mode: input.value });
        state.design = result.design;
        state.selected = null;
        syncForm();
        await selectKind(state.draftKind, true);
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
    <button class="support-choice" data-kind="${part.kind}" title="${escapeHtml(part.description)}">
      ${iconFor(part.kind)}<span>${escapeHtml(part.title)}</span>
    </button>
  `).join("");
  $$(".support-choice", palette).forEach(button => {
    button.addEventListener("click", () => {
      state.selected = null;
      selectKind(button.dataset.kind, true);
    });
  });
}

function syncForm() {
  const { box, layout } = state.design;
  $("#x-units").value = fmt(box.x / state.catalog.base_unit);
  $("#y-units").value = fmt(box.y / state.catalog.base_unit);
  $("#z").value = fmt(box.z);
  $("#wall").value = fmt(box.wall);
  $("#flat-inside").value = fmt(box.flat_inside);
  $("#label-text").value = state.design.label || "";
  $("#part-name").value = state.design.part_name || "";
  $("#scoop").checked = Boolean(state.design.scoop);
  const mode = $(`input[name="layout-mode"][value="${layout.mode}"]`);
  if (mode) mode.checked = true;
  const labelPosition = $(`input[name="label-position"][value="${state.design.label_position}"]`);
  if (labelPosition) labelPosition.checked = true;
  $("#output-folder").value = state.output;
  $("#connector-tolerance").value = fmt(state.connector.tolerance);
  $("#connector-height").value = fmt(state.connector.height);
  $("#connector-length").value = fmt(state.connector.length);
  $("#connector-position").value = fmt(state.connector.position);
  const connectorAxis = $(`input[name="connector-axis"][value="${state.connector.axis}"]`);
  if (connectorAxis) connectorAxis.checked = true;
  renderPlaced();
}

function updateDesignFromForm() {
  const design = state.design;
  const xUnits = number($("#x-units").value, design.box.x / state.catalog.base_unit);
  const yUnits = number($("#y-units").value, design.box.y / state.catalog.base_unit);
  design.box.x = xUnits * state.catalog.base_unit;
  design.box.y = yUnits * state.catalog.base_unit;
  design.box.z = number($("#z").value, design.box.z);
  design.box.wall = number($("#wall").value, design.box.wall);
  design.box.flat_inside = number($("#flat-inside").value, design.box.flat_inside);
  design.label = $("#label-text").value;
  design.part_name = $("#part-name").value;
  design.scoop = $("#scoop").checked;
  design.label_position = $('input[name="label-position"]:checked')?.value || "bottom";
  const newOutput = $("#output-folder").value.trim();
  if (newOutput !== state.output) {
    state.output = newOutput;
    saveOutputPreference(newOutput);
  }
  state.connector = {
    tolerance: number($("#connector-tolerance").value, state.connector.tolerance),
    height: number($("#connector-height").value, state.connector.height),
    length: number($("#connector-length").value, state.connector.length),
    position: number($("#connector-position").value, state.connector.position),
    axis: $('input[name="connector-axis"]:checked')?.value || "y",
  };
}

const saveOutputPreference = debounce(output => {
  api("/api/preferences", { output }).catch(() => {});
}, 500);

function updatePreviewHelp(view) {
  $("#preview-help").textContent = view === "2d"
    ? "Pointer: drag supports to move them or drag the blue corner to resize. Keyboard or screen reader: choose a placed support, then edit Center X, Center Y, Width, and Depth."
    : "Visual preview only. Drag to rotate, use the wheel to zoom, or double-click to reset; these controls do not change the printed part.";
}

const changedDesign = debounce(() => {
  if (state.designMutationBusy) return;
  updateDesignFromForm();
  refreshPreview();
  if (state.draft) refreshDraft();
}, 280);

function wireControls() {
  $$(".section-heading").forEach(button => button.addEventListener("click", () => {
    const section = button.closest(".control-section");
    section.classList.toggle("open");
    button.setAttribute("aria-expanded", String(section.classList.contains("open")));
  }));

  ["#x-units", "#y-units", "#z", "#wall", "#flat-inside", "#label-text", "#part-name"]
    .forEach(selector => $(selector).addEventListener("input", changedDesign));
  [$("#scoop"), ...$$('input[name="label-position"]')].forEach(input => {
    input.addEventListener("change", () => {
      updateDesignFromForm();
      refreshPreview();
    });
  });
  ["#output-folder", "#connector-tolerance", "#connector-height",
    "#connector-length", "#connector-position"]
    .forEach(selector => $(selector).addEventListener("change", updateDesignFromForm));
  $$('input[name="connector-axis"]').forEach(input =>
    input.addEventListener("change", updateDesignFromForm));

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

  $("#add-support").addEventListener("click", () => applySupport(null));
  $("#update-support").addEventListener("click", () => applySupport(state.selected));
  $("#delete-support").addEventListener("click", deleteSupport);
  $("#save-design").addEventListener("click", saveDesign);
  $("#open-design").addEventListener("change", openDesign);
  $("#new-design").addEventListener("click", newDesign);
  $("#generate-bin").addEventListener("click", () => generate("/api/generate", "#generate-bin"));
  $("#generate-connector").addEventListener("click", () => generate("/api/connector", "#generate-connector"));
  $("#generate-sampler").addEventListener("click", () => generate("/api/sampler", "#generate-sampler"));
  wireSceneInteraction($("#preview-3d"), state.camera, renderPreview3D);
  wireLayoutInteraction();
  new ResizeObserver(() => renderPreview3D()).observe($("#preview-3d").parentElement);
  new ResizeObserver(() => renderLayout2D()).observe($("#preview-2d").parentElement);
  new ResizeObserver(() => renderDraftPreview()).observe($("#draft-preview"));
}

function starterItem() {
  return {
    name: "Custom item", profile: "round", clearance: 0.4,
    segments: [{ length: 40, diameter: 6 }],
  };
}

async function selectKind(kind, reset = false) {
  state.draftKind = kind;
  state.selected = reset ? null : state.selected;
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
  state.selectedOriginal = clone(state.draft);
  state.draftResolvedOptions = {};
  state.draftKind = state.draft.kind;
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
  return `<label class="${classes}">${escapeHtml(label)}${options.unit ? `<span class="unit">${escapeHtml(options.unit)}</span>` : ""}
    <input type="${type}" data-draft="${key}" value="${escapeHtml(value ?? "")}" ${attrs}>
  </label>`;
}

function renderDraftFields() {
  if (!state.draft) return;
  const info = partInfo();
  const one = state.draft;
  const zone = one.zone;
  const cx = (zone[0] + zone[2]) / 2;
  const cy = (zone[1] + zone[3]) / 2;
  const width = zone[2] - zone[0];
  const depth = zone[3] - zone[1];
  let html = field("Center X", "cx", fmt(cx), { unit: "mm" }) + field("Center Y", "cy", fmt(cy), { unit: "mm" });
  if (info.flags.size) {
    html += field("Width", "width", fmt(width), { unit: "mm" });
    html += field("Depth", "depth", fmt(depth), { unit: "mm" });
  }
  if (info.flags.qty) {
    html += `<label class="wide">Quantity<div class="input-with-button">
      <input type="number" min="1" step="1" data-draft="count" value="${one.count ?? ""}" placeholder="auto">
      <button type="button" class="button secondary" data-action="auto-count">Auto</button>
    </div></label>`;
  }
  if (info.flags.along) {
    html += `<fieldset class="wide"><legend>Runs along</legend><div class="segmented two">
      <label><input type="radio" name="draft-along" value="x" ${one.along === "x" ? "checked" : ""}><span>X direction</span></label>
      <label><input type="radio" name="draft-along" value="y" ${one.along === "y" ? "checked" : ""}><span>Y direction</span></label>
    </div></fieldset>`;
  }
  if (info.flags.item) {
    const item = one.item || starterItem();
    const first = item.segments[0] || { length: 40, diameter: 6 };
    const handle = item.segments[1] || { length: "", diameter: "" };
    html += field("Item name", "item_name", item.name || "Custom item", { type: "text", wide: true });
    html += field("Length", "item_length", fmt(first.length), { unit: "mm" });
    html += field("Thickness", "item_diameter", fmt(first.diameter), { unit: "mm" });
    html += field("Handle length", "handle_length", handle.length === "" ? "" : fmt(handle.length), { unit: "mm" });
    html += field("Handle thickness", "handle_diameter", handle.diameter === "" ? "" : fmt(handle.diameter), { unit: "mm" });
    html += `<label>Profile<select data-draft="profile">
      ${["round", "hex", "square"].map(profile => `<option value="${profile}" ${item.profile === profile ? "selected" : ""}>${profile[0].toUpperCase() + profile.slice(1)}</option>`).join("")}
    </select></label>`;
    html += field("Fit clearance", "clearance", fmt(item.clearance ?? 0.4), { unit: "mm" });
  }
  for (const option of info.fields) {
    const explicit = Object.prototype.hasOwnProperty.call(one.options || {}, option.key);
    const shown = explicit
      ? one.options[option.key]
      : state.draftResolvedOptions?.[option.key] ?? option.default;
    html += field(option.label, `option:${option.key}`, shown);
    if (option.key === "angle") {
      html += `<fieldset class="wide"><legend>Leaning shape</legend><div class="segmented two">
        <label><input type="radio" name="draft-wedge" value="wedge" ${one.wedge !== false ? "checked" : ""}><span>Wedge</span></label>
        <label><input type="radio" name="draft-wedge" value="straight" ${one.wedge === false ? "checked" : ""}><span>Straight</span></label>
      </div></fieldset>
      <p class="field-help">Only matters once the angle above is not zero. <strong>Wedge</strong> stays thick at the floor and tapers as it leans, so it takes the sideways push of whatever rests against it. <strong>Straight</strong> keeps the same thin thickness the whole way up and can snap off.</p>`;
    }
  }
  $("#draft-fields").innerHTML = html;
  $$('[data-draft]', $("#draft-fields")).forEach(input => {
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", updateDraftFromFields);
  });
  $$('input[name="draft-along"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    state.draft.along = input.value;
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  $$('input[name="draft-wedge"]', $("#draft-fields")).forEach(input => input.addEventListener("change", () => {
    state.draft.wedge = input.value === "wedge";
    updateSelectionButtons();
    refreshDraftSoon();
  }));
  const autoCount = $('[data-action="auto-count"]', $("#draft-fields"));
  if (autoCount) autoCount.addEventListener("click", () => {
    state.draft.count = null;
    const input = $('[data-draft="count"]', $("#draft-fields"));
    if (input) input.value = "";
    updateSelectionButtons();
    refreshDraftSoon();
  });
}

function updateDraftFromFields(event) {
  const one = state.draft;
  const get = key => $(`[data-draft="${key}"]`, $("#draft-fields"))?.value;
  const oldZone = one.zone;
  const oldCx = (oldZone[0] + oldZone[2]) / 2;
  const oldCy = (oldZone[1] + oldZone[3]) / 2;
  const oldWidth = oldZone[2] - oldZone[0];
  const oldDepth = oldZone[3] - oldZone[1];
  const cx = number(get("cx"), oldCx);
  const cy = number(get("cy"), oldCy);
  const width = Math.max(0.1, number(get("width"), oldWidth));
  const depth = Math.max(0.1, number(get("depth"), oldDepth));
  one.zone = [cx - width / 2, cy - depth / 2, cx + width / 2, cy + depth / 2];
  const info = partInfo();
  if (info.flags.qty) {
    const count = String(get("count") ?? "auto").trim().toLowerCase();
    one.count = count === "" || count === "auto" ? null : Math.max(1, Math.round(number(count, 1)));
  }
  if (info.flags.item) {
    const item = one.item || starterItem();
    item.name = get("item_name") || "Custom item";
    item.profile = get("profile") || "round";
    item.clearance = number(get("clearance"), item.clearance ?? 0.4);
    const first = {
      length: number(get("item_length"), item.segments?.[0]?.length || 40),
      diameter: number(get("item_diameter"), item.segments?.[0]?.diameter || 6),
    };
    const handleLength = String(get("handle_length") ?? "").trim();
    const handleDiameter = String(get("handle_diameter") ?? "").trim();
    item.segments = [first];
    if (handleLength && handleDiameter) item.segments.push({
      length: number(handleLength), diameter: number(handleDiameter),
    });
    one.item = item;
  }
  one.options ||= {};
  const changed = event?.currentTarget?.dataset?.draft || "";
  if (changed.startsWith("option:")) {
    const key = changed.slice("option:".length);
    const option = info.fields.find(entry => entry.key === key);
    const raw = String(get(changed) ?? "").trim();
    if (raw === "") delete one.options[key];
    else one.options[key] = number(
      raw,
      one.options[key] ?? state.draftResolvedOptions?.[key] ?? number(option?.default),
    );
    if (info.kind === "divider" && key === "thickness") {
      // A divider builds from this, not from the footprint drawn below -
      // widen that footprint to match so what the Width/Depth fields and
      // the 2D layout show never falls short of the real wall.
      const t = one.options.thickness;
      if (Number.isFinite(t) && t > 0) {
        const zw = one.zone[2] - one.zone[0], zd = one.zone[3] - one.zone[1];
        const cx = (one.zone[0] + one.zone[2]) / 2, cy = (one.zone[1] + one.zone[3]) / 2;
        const wideningKey = zw >= zd ? "depth" : "width";
        if (zw >= zd) {
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
    }
  }
  updateSelectionButtons();
  refreshDraftSoon();
}

const refreshDraftSoon = debounce(refreshDraft, 220);

async function refreshDraft() {
  if (!state.draft) return;
  const request = ++state.draftRequest;
  $("#draft-status").textContent = "Rebuilding…";
  try {
    const result = await api("/api/feature/draft", { design: state.design, feature: state.draft });
    if (request !== state.draftRequest) return;
    state.draftGeometry = result.geometry;
    state.draftResolvedOptions = result.resolved_options || {};
    const info = partInfo();
    for (const option of info.fields) {
      if (Object.prototype.hasOwnProperty.call(state.draft.options || {}, option.key)) continue;
      const input = $(`[data-draft="option:${option.key}"]`, $("#draft-fields"));
      if (input && Object.prototype.hasOwnProperty.call(state.draftResolvedOptions, option.key)) {
        input.value = fmt(state.draftResolvedOptions[option.key]);
      }
    }
    $("#draft-status").textContent = "";
    renderDraftPreview();
  } catch (error) {
    if (request !== state.draftRequest) return;
    $("#draft-status").textContent = error.message;
  }
}

async function applySupport(index) {
  if (!state.draft || !beginDesignMutation()) return;
  const button = index === null ? $("#add-support") : $("#update-support");
  const previous = button.textContent;
  button.textContent = index === null ? "Placing…" : "Updating…";
  try {
    const result = await api("/api/feature/apply", { design: state.design, feature: state.draft, index });
    state.design = result.design;
    state.selected = result.selected;
    state.draft = clone(state.design.layout.features[state.selected]);
    state.selectedOriginal = clone(state.draft);
    state.draftResolvedOptions = {};
    renderDraftFields();
    renderPlaced();
    updateSelectionButtons();
    await refreshPreview();
    refreshDraft();
    toast(index === null ? "Support placed." : "Support updated.");
    return true;
  } catch (error) {
    toast(error.message, true, 5000);
    return false;
  } finally {
    button.textContent = previous;
    finishDesignMutation();
  }
}

async function deleteSupport() {
  if (state.selected === null || !beginDesignMutation()) return;
  try {
    const result = await api("/api/feature/delete", { design: state.design, index: state.selected });
    state.design = result.design;
    state.selected = null;
    renderPlaced();
    updateSelectionButtons();
    await selectKind(state.draftKind, true);
    refreshPreview();
    toast("Support deleted.");
  } catch (error) {
    toast(error.message, true);
  } finally {
    finishDesignMutation();
  }
}

function mutationControls() {
  return $$(
    '#x-units, #y-units, #z, #wall, #flat-inside, #label-text, #part-name, ' +
    '#scoop, input[name="label-position"], input[name="layout-mode"], ' +
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
  return true;
}

function finishDesignMutation() {
  state.designMutationBusy = false;
  mutationControls().forEach(control => control.disabled = false);
  updateSelectionButtons();
}

function draftIsDirty() {
  if (state.selected === null || !state.selectedOriginal) return false;
  return JSON.stringify(state.draft) !== JSON.stringify(state.selectedOriginal);
}

function updateSelectionButtons() {
  const selected = state.selected !== null;
  const busy = state.designMutationBusy;
  $("#update-support").disabled = busy || !draftIsDirty();
  $("#delete-support").disabled = busy || !selected;
  $("#add-support").disabled = busy || !state.draft;
  $$(".support-choice, .placed-item").forEach(button => button.disabled = busy);
  $("#support-count").textContent = `${state.design?.layout.features.length || 0} placed`;
}

function renderPlaced() {
  if (!state.design) return;
  const features = state.design.layout.features;
  const container = $("#placed-supports");
  if (!features.length) {
    container.innerHTML = '<div class="placed-empty">No supports yet. Pick a shape above.</div>';
  } else {
    container.innerHTML = features.map((one, index) => {
      const width = one.zone[2] - one.zone[0];
      const depth = one.zone[3] - one.zone[1];
      return `<button class="placed-item ${index === state.selected ? "selected" : ""}" data-index="${index}">
        <strong>${index + 1}. ${escapeHtml(partInfo(one.kind)?.title || one.kind)}</strong>
        <span>${fmt(width)} × ${fmt(depth)} mm</span>
      </button>`;
    }).join("");
    $$(".placed-item", container).forEach(button => button.addEventListener("click", () => selectedFeature(Number(button.dataset.index))));
  }
  $("#support-count").textContent = `${features.length} placed`;
  $("#design-summary").textContent = features.length
    ? `${features.length} support${features.length === 1 ? "" : "s"} · ${state.design.layout.mode}`
    : `No supports placed · ${state.design.layout.mode}`;
}

async function refreshPreview() {
  const request = ++state.previewRequest;
  $("#preview-state").textContent = "Building preview…";
  setError();
  try {
    const result = await api("/api/preview", { design: state.design });
    if (request !== state.previewRequest) return;
    state.preview = result;
    state.design = result.design;
    $("#preview-state").textContent = result.fits ? "Preview current" : "Label needs attention";
    $("#inside-size").textContent = `${result.dimensions.x} wide · ${result.dimensions.y} deep · ${result.dimensions.z}`;
    $("#dimensions").innerHTML = `<span>${escapeHtml(result.dimensions.x)}</span><span>${escapeHtml(result.dimensions.y)}</span><span>${escapeHtml(result.dimensions.z)}</span>`;
    const messages = [result.message, ...result.feature_errors].filter(Boolean);
    if (messages.length) setError(messages.join(" · "));
    renderPreview3D();
    renderLayout2D();
    renderPlaced();
  } catch (error) {
    if (request !== state.previewRequest) return;
    $("#preview-state").textContent = "Preview could not build";
    setError(error.message);
  }
}

function kindColor(kind) {
  if (COLORS[kind]) return COLORS[kind];
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

function drawGeometry(canvas, geometry, camera, draft = false) {
  const { context, width, height } = canvasSize(canvas);
  context.clearRect(0, 0, width, height);
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
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const face of faces) for (const point of face.projected) {
    minX = Math.min(minX, point[0]); maxX = Math.max(maxX, point[0]);
    minY = Math.min(minY, point[1]); maxY = Math.max(maxY, point[1]);
  }
  const spanX = Math.max(1e-8, maxX - minX), spanY = Math.max(1e-8, maxY - minY);
  const pad = draft ? 15 : Math.max(34, Math.min(width, height) * .08);
  const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY) * camera.zoom;
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const project = point => [width / 2 + (point[0] - midX) * scale, height / 2 + (point[1] - midY) * scale];
  faces.sort((a, b) => a.depth - b.depth || number(a.layer) - number(b.layer));
  context.lineJoin = "round";
  for (const face of faces) {
    const points = face.projected.map(project);
    if (points.length < 3) continue;
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach(point => context.lineTo(point[0], point[1]));
    context.closePath();
    const base = kindColor(face.kind);
    const light = .78 + Math.max(0, Math.min(1, face.facing)) * .35;
    context.fillStyle = shade(base, light);
    context.fill();
    context.strokeStyle = draft ? "rgba(31,62,71,.18)" : "rgba(38,65,75,.13)";
    context.lineWidth = draft ? .45 : .35;
    context.stroke();
  }
}

function renderPreview3D() {
  if (!state.preview) return;
  drawGeometry($("#preview-3d"), state.preview.geometry, state.camera, false);
}

function renderDraftPreview() {
  drawGeometry($("#draft-preview"), state.draftGeometry, state.draftCamera, true);
}

function wireSceneInteraction(canvas, camera, render) {
  let drag = null;
  canvas.addEventListener("pointerdown", event => {
    drag = { x: event.clientX, y: event.clientY, yaw: camera.yaw, elevation: camera.elevation };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", event => {
    if (!drag) return;
    camera.yaw = drag.yaw + (event.clientX - drag.x) * .45;
    camera.elevation = Math.max(8, Math.min(89, drag.elevation - (event.clientY - drag.y) * .35));
    render();
  });
  canvas.addEventListener("pointerup", event => {
    drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    camera.zoom = Math.max(.35, Math.min(4, camera.zoom * Math.exp(-event.deltaY * .001)));
    render();
  }, { passive: false });
  canvas.addEventListener("dblclick", () => {
    Object.assign(camera, { yaw: 45, elevation: 76, zoom: 1 });
    render();
  });
}

function layoutFeatures() {
  const features = state.design.layout.features.map(feature => clone(feature));
  if (state.layoutDrag?.feature && state.layoutDrag.index !== null) features[state.layoutDrag.index] = state.layoutDrag.feature;
  return features;
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
  context.fillStyle = "#ffffff";
  context.strokeStyle = "#5e7f88";
  context.lineWidth = 2;
  context.fillRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
  context.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
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
    context.fillStyle = color + "cc";
    context.strokeStyle = index === state.selected ? "#176e91" : shade(color, .72);
    context.lineWidth = index === state.selected ? 3 : 1.2;
    context.fillRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
    context.strokeRect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1]);
    context.fillStyle = "rgba(20,36,42,.82)";
    context.font = "600 11px Segoe UI";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(`${index + 1} ${partInfo(feature.kind)?.title || feature.kind}`, (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2);
    if (index === state.selected) {
      context.fillStyle = "#237fa6";
      context.strokeStyle = "white";
      context.lineWidth = 1;
      context.fillRect(p1[0] - 6, p1[1] - 6, 12, 12);
      context.strokeRect(p1[0] - 6, p1[1] - 6, 12, 12);
    }
  });
}

function layoutPoint(event) {
  const rect = $("#preview-2d").getBoundingClientRect();
  return state.layoutTransform.toWorld([event.clientX - rect.left, event.clientY - rect.top]);
}

function hitFeature(world) {
  const features = state.design.layout.features;
  for (let index = features.length - 1; index >= 0; index--) {
    const zone = features[index].zone;
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
    const zone = feature.zone;
    const handlePixels = Math.hypot((world[0] - zone[2]) * state.layoutTransform.scale, (world[1] - zone[1]) * state.layoutTransform.scale);
    state.layoutDrag = {
      index, feature, original: clone(feature),
      mode: handlePixels < 14 ? "resize" : "move",
      start: world,
      centre: [(zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2],
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
    state.selected = null;
    syncForm();
    await selectKind("divider", true);
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
  if (state.design.layout.features.length && !window.confirm("Start a new design and clear the placed supports?")) return;
  if (!beginDesignMutation()) return;
  state.design = clone(state.catalog.defaults.design);
  state.selected = null;
  syncForm();
  try {
    await selectKind("divider", true);
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
    button.disabled = false;
    button.textContent = old;
  }
}

function collectOutputs(value, found = []) {
  if (!value || typeof value !== "object") return found;
  if (typeof value.output === "string") found.push(value.output.split(/[\\/]/).pop());
  Object.values(value).forEach(item => collectOutputs(item, found));
  return [...new Set(found)];
}

async function init() {
  try {
    const catalog = await api("/api/catalog");
    state.catalog = catalog;
    state.design = clone(catalog.defaults.design);
    state.output = catalog.preferences?.output || catalog.defaults.output;
    state.connector = clone(catalog.defaults.connector);
    renderCatalog();
    wireControls();
    syncForm();
    $("#connection").textContent = "Local engine connected";
    $("#connection").classList.add("ready");
    await selectKind("divider", true);
    await refreshPreview();
  } catch (error) {
    $("#connection").textContent = "Engine unavailable";
    setError(error.message);
    toast(error.message, true, 8000);
  }
}

init();
