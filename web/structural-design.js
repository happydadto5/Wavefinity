/* Wavefinity — structural Space objects in Design (Fix 103).
 *
 * A Storage Drawers cabinet or a Storage Box case is a first-class Design
 * target: its full editor mounts in #structural-editor-host, its 3D preview
 * comes from the server's production geometry (never an ordinary bin), and its
 * 2D view is the Space canvas in view-only mode.
 *
 * Ownership (Fix 103 R2/R3/R6):
 *   - the mounted form owns the unsaved draft Space; nothing here persists
 *     until Save Changes;
 *   - one debounced, latest-wins preview scheduler feeds the single
 *     state.structuralPreview slot; every response is checked against
 *     { request, activeSpaceId, targetKind, formMountSerial, draftKey };
 *   - one dirty predicate (structuralEditorDirty) and one leave helper
 *     (SP.confirmLeaveStructuralEditor) settle every structural exit.
 *
 * Nothing in this file ever assigns state.design / state.cleanDesign /
 * state.preview.
 */

// ---------------------------------------------------------------- target

// "box" | "storage_drawers" | "base_trim" | null. The explicit Design target is
// { kind: "structural", structural: true, structuralKind, rowId, drawerId }.
// "base_trim" is preview-only: the trim is derived from the Surface Space, so
// it mounts no editable form (Fix 111 F3).
function structuralTargetKind() {
  if (typeof DP === "undefined" || !DP.getDesignTarget) return null;
  const target = DP.getDesignTarget();
  return target.kind === "structural" ? (target.structuralKind || null) : null;
}

// True while a structural target owns the visible Design panel.
function structuralDesignActive() {
  return structuralTargetKind() !== null && typeof DP !== "undefined" && DP.mode === "design";
}

// Fix 103: a stable id for the Space the editor is showing. Used only to
// notice that the accepted Space changed under a mounted editor.
function structuralSpaceKey() {
  return JSON.stringify([state.activeSpaceId || null, state.activeSpace || null]);
}

// Any later write to state.designTarget (ordinary bin install paths clear it
// without going through DP.clearDesignTarget) re-syncs the editor, so the
// structural chrome can never outlive its target.
(() => {
  let current = Object.hasOwn(state, "designTarget") ? state.designTarget : null;
  Object.defineProperty(state, "designTarget", {
    configurable: true, enumerable: true,
    get: () => current,
    set: next => {
      const changed = current !== next;
      current = next;
      if (changed) queueMicrotask(() => syncStructuralEditor());
    },
  });
})();

// ---------------------------------------------------------------- editor

let structuralEditorRecord = null;
let structuralPreviewTimer = null;
const STRUCTURAL_PREVIEW_DEBOUNCE_MS = 250;

function structuralEl(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function structuralLabel(kind = structuralTargetKind()) {
  return kind === "box" ? "Storage Box" : kind === "base_trim" ? "Base Trim" : "Storage Drawers";
}

// The one structural dirty predicate (R6). The ordinary designHasChanges()
// deliberately reports false for a structural target.
function structuralEditorDirty() {
  const form = structuralEditorRecord?.form;
  return Boolean(form && form.isDirty && form.isDirty());
}

function setStructuralStatus(message, { error = false } = {}) {
  const record = structuralEditorRecord;
  if (!record?.status) return;
  record.status.textContent = message || "";
  record.status.hidden = !message;
  record.status.classList.toggle("field-error", Boolean(error));
}

function updateStructuralActions() {
  const record = structuralEditorRecord;
  if (!record?.save) return;
  const dirty = structuralEditorDirty();
  record.save.disabled = record.saving || !dirty;
  record.cancel.disabled = record.saving || !dirty;
  record.dirtyNote.hidden = !dirty;
}

function unmountStructuralEditor({ clearPreview = true } = {}) {
  clearTimeout(structuralPreviewTimer);
  structuralPreviewTimer = null;
  const record = structuralEditorRecord;
  structuralEditorRecord = null;
  // A destroyed or remounted form invalidates every in-flight preview.
  state.structuralMountSerial += 1;
  state.structuralPreviewRequest += 1;
  state.structuralDimensionDrag = null;
  if (record) {
    try { record.form?.destroy(); } catch (_error) { /* already gone */ }
    record.wrap?.remove();
  }
  if (clearPreview) {
    state.structuralPreview = null;
    state.structuralPreviewStale = false;
    state.structuralPreviewError = "";
    state.structuralHighlightOwner = null;
  }
}

// Mounts the structural editor for the current target, or unmounts it when
// the target is an ordinary bin or Design is not showing. Idempotent: it only
// rebuilds when the target kind or the accepted Space changed (or `force`).
function syncStructuralEditor({ force = false } = {}) {
  const host = document.getElementById("structural-editor-host");
  const kind = structuralTargetKind();
  const active = Boolean(kind) && Boolean(host) && Boolean(state.activeSpace) &&
    typeof DP !== "undefined" && DP.mode === "design";
  document.body.classList.toggle("structural-design-active", active);
  if (!active) {
    if (structuralEditorRecord) unmountStructuralEditor({ clearPreview: !kind });
    if (host) { host.hidden = true; host.replaceChildren(); }
    return;
  }
  const key = structuralSpaceKey();
  const record = structuralEditorRecord;
  if (record && !force && record.kind === kind && record.spaceKey === key) {
    host.hidden = false;
    return;
  }
  mountStructuralEditor(kind, key);
}

function mountStructuralEditor(kind, key) {
  const host = document.getElementById("structural-editor-host");
  // A rebuild for the same Space (after Save/Cancel) keeps the last preview,
  // the highlight and the active drawer; another Space starts clean.
  const previous = structuralEditorRecord;
  const sameSpace = Boolean(previous) && previous.kind === kind && previous.spaceId === (state.activeSpaceId || null);
  const keepDrawer = sameSpace ? previous.form?.activeDrawerId?.() : null;
  unmountStructuralEditor({ clearPreview: !sameSpace });
  host.replaceChildren();
  host.hidden = false;
  const space = clone(state.activeSpace);
  const wrap = structuralEl("div", "structural-editor");
  wrap.append(structuralEl("h3", "structural-editor-title", `${structuralLabel(kind)} design`));
  const formHost = structuralEl("div", "structural-form-host");
  const dirtyNote = structuralEl("p", "structural-dirty-note", "Unsaved changes. The preview shows them; Save Changes keeps them.");
  dirtyNote.hidden = true;
  const status = structuralEl("p", "structural-status"); status.hidden = true;
  status.setAttribute("role", "status");
  const actions = structuralEl("div", "button-row equal structural-actions");
  const save = structuralEl("button", "button primary", "Save Changes"); save.type = "button"; save.disabled = true;
  const cancel = structuralEl("button", "button secondary", "Cancel"); cancel.type = "button"; cancel.disabled = true;
  actions.append(save, cancel);
  // Fix 111 (F3): the Base Trim has no editable draft — the preview is the
  // production trim derived from the Surface. Nothing to save or cancel here;
  // Save/Print live in the Space structural panel.
  const trimNote = structuralEl("p", "dl-note",
    "Production preview of the trim. It follows the Surface size — edit the Surface to change it.");
  trimNote.hidden = kind !== "base_trim";
  if (kind === "base_trim") { actions.hidden = true; formHost.hidden = true; }
  wrap.append(formHost, dirtyNote, status, trimNote, actions);
  host.append(wrap);
  const record = {
    kind, spaceKey: key, spaceId: state.activeSpaceId || null,
    serial: ++state.structuralMountSerial, wrap, formHost, status, save, cancel, dirtyNote,
    form: null, saving: false,
  };
  structuralEditorRecord = record;
  save.addEventListener("click", () => { void structuralSaveChanges(); });
  cancel.addEventListener("click", () => { void structuralDiscardDraft(); });
  try {
    if (kind === "base_trim") {
      // Fix 111 (F3): preview-only target — the trim is derived from the
      // accepted Surface Space, so no form is mounted. The preview below is
      // the production geometry that Save/Print manufactures.
    } else if (kind === "box") {
      if (!window.StorageBoxForm) throw new Error("The case editor did not load. Reload Wavefinity.");
      record.form = window.StorageBoxForm.mount({
        host: formHost, initialSpace: space,
        callbacks: { onChange: onStructuralDraftChange },
      });
    } else {
      if (!window.StorageDrawersForm) throw new Error("The cabinet editor did not load. Reload Wavefinity.");
      SP.ensureStorageDrawersRules();
      record.form = window.StorageDrawersForm.mount({
        host: formHost, initialSpace: space, catalog: state.catalog,
        printerProfile: PrinterProfile.current(), mode: "edit", scope: "full",
        callbacks: {
          structural: true,
          identity: () => state.activeSpaceId || state.activeSpace?.name || "structural",
          openPrinterSettings: () => SP.openPrinterSettings(),
          requestSummary: ({ space: draft, printer_profile }) => api("/api/space/storage-drawers-summary", {
            space: draft, ...(state.runtime.hosted ? { printer_profile } : {}),
          }, { timeoutMs: 15000 }),
          onChange: onStructuralDraftChange,
          onSummary: () => { if (structuralEditorRecord === record) updateStructuralActions(); },
          onHighlightDrawer: structuralHighlightDrawer,
          addDrawer: () => structuralCabinetMutation("add"),
          deleteDrawer: drawerId => structuralCabinetMutation("delete", drawerId),
        },
        onReadyChange: () => { if (structuralEditorRecord === record) updateStructuralActions(); },
      });
      if (keepDrawer) record.form.selectDrawer?.(keepDrawer);
    }
  } catch (error) {
    setStructuralStatus(friendlyError(error), { error: true });
    return;
  }
  // Base Trim is preview-only and intentionally has no form.
  record.form?.markPristine?.();
  updateStructuralActions();
  scheduleStructuralPreview({ immediate: true });
}

// Every draft change: refresh the action state at once, the geometry later.
function onStructuralDraftChange() {
  const record = structuralEditorRecord;
  if (!record || !record.form) return; // still mounting; mount schedules its own preview
  updateStructuralActions();
  scheduleStructuralPreview();
}

function structuralHighlightDrawer(owner, { ensure = false } = {}) {
  state.structuralHighlightOwner = ensure ? owner : (state.structuralHighlightOwner === owner ? null : owner);
  renderPreview3D();
}

// ---------------------------------------------------------------- draft

// The form's CURRENT draft Space (R2). Preview and Save both read this, never
// merely the accepted state.activeSpace. The Base Trim has no form: its
// preview reads the accepted Surface Space directly (Fix 111 F3).
function structuralDraftResult() {
  const record = structuralEditorRecord;
  if (!state.activeSpace) return { ok: false, message: "The editor is not ready." };
  if (record?.kind === "base_trim") return { ok: true, space: clone(state.activeSpace) };
  if (!record?.form) return { ok: false, message: "The editor is not ready." };
  const draft = record.form.draft();
  if (!draft.ok) return draft;
  if (record.kind === "box") {
    return {
      ok: true,
      space: {
        ...clone(state.activeSpace),
        x: draft.space.x, y: draft.space.y, z: draft.space.z,
        // Settings this form does not expose stay as the accepted Space has them.
        storage_box: { ...(state.activeSpace.storage_box || {}), ...draft.space.storage_box },
      },
    };
  }
  return { ok: true, space: draft.spaceDraft };
}

function structuralDraftKey(kind, space) {
  const profile = typeof PrinterProfile !== "undefined" ? PrinterProfile.current() : null;
  if (kind === "storage_drawers") return StorageDrawers.structuralDraftKey(space, profile);
  // Fix 111 (F3): the trim is fixed by the Surface footprint, trim size and
  // printer profile (hosted only — local uses the one global profile).
  if (kind === "base_trim") return JSON.stringify([space.x, space.y, space.trim_size, state.runtime.hosted ? profile : null]);
  return JSON.stringify([space.x, space.y, space.z, space.storage_box, state.runtime.hosted ? profile : null]);
}

// A cabinet draft row that has no saved id yet still needs one to preview.
function structuralWithDrawerIds(space) {
  const next = clone(space);
  for (const row of next.storage_drawers?.drawers || []) {
    if (!row.id) row.id = row.temp_key?.slice("temporary:".length) || crypto.randomUUID();
  }
  return next;
}

function structuralOutsideXYZ(preview, kind) {
  if (kind === "box") {
    const envelope = preview?.b4b?.assembled_envelope_mm;
    return Array.isArray(envelope) && envelope.length >= 3 ? envelope.map(Number) : null;
  }
  const bounds = preview?.bounds;
  return bounds ? [bounds.x, bounds.y, bounds.z].map(Number) : null;
}

// ---------------------------------------------------------------- preview

// R3: one debounced scheduler for both structural kinds. A drag release (or
// editor mount) asks for an immediate request; typing/pointermove just re-arm
// the idle timer.
function scheduleStructuralPreview({ immediate = false } = {}) {
  clearTimeout(structuralPreviewTimer);
  if (!structuralEditorRecord) return;
  structuralPreviewTimer = setTimeout(() => {
    structuralPreviewTimer = null;
    void refreshStructuralPreview();
  }, immediate ? 0 : STRUCTURAL_PREVIEW_DEBOUNCE_MS);
}

const STRUCTURAL_STALE_LABEL = "Last valid preview — your current changes are not shown";

function setStructuralPreviewState(text, { error = false } = {}) {
  const node = $("#preview-state");
  if (!node) return;
  node.textContent = text;
  node.classList.toggle("status-error", error);
  if (!error) node.classList.remove("status-ok");
}

async function refreshStructuralPreview() {
  const record = structuralEditorRecord;
  const kind = structuralTargetKind();
  // Fix 111 (F3): the Base Trim mounts no form; its preview reads the accepted
  // Surface Space (see structuralDraftResult).
  if (!record || !kind || DP.mode !== "design") return;
  if (!record.form && record.kind !== "base_trim") return;
  const draft = structuralDraftResult();
  if (!draft.ok) {
    // An incomplete draft cannot preview. The last good geometry stays, but it
    // is labelled so old geometry never passes for the current invalid draft;
    // the form's own message explains what to fix.
    state.structuralPreviewRequest += 1;
    state.structuralPreviewStale = Boolean(state.structuralPreview?.meshes?.length);
    setStructuralPreviewState(state.structuralPreviewStale ? STRUCTURAL_STALE_LABEL : "");
    renderPreview3D();
    return;
  }
  state.structuralPreviewStale = false;
  // Currentness tuple (R3). Any member changing makes the response stale.
  const identity = {
    request: ++state.structuralPreviewRequest,
    spaceId: state.activeSpaceId || null,
    kind,
    mount: record.serial,
    key: structuralDraftKey(kind, draft.space),
  };
  const current = () => {
    if (identity.request !== state.structuralPreviewRequest) return false;
    if (identity.spaceId !== (state.activeSpaceId || null)) return false;
    if (structuralTargetKind() !== identity.kind) return false;
    const live = structuralEditorRecord;
    if (!live || live.serial !== identity.mount || state.structuralMountSerial !== identity.mount) return false;
    const now = structuralDraftResult();
    return now.ok && structuralDraftKey(identity.kind, now.space) === identity.key;
  };
  setStructuralPreviewState("Building preview…");
  try {
    const hosted = Boolean(state.runtime.hosted);
    const profile = typeof PrinterProfile !== "undefined" ? PrinterProfile.current() : null;
    let result;
    if (kind === "box" || kind === "base_trim") {
      const structural = await api("/api/space/structural-design", {
        space: draft.space, ...(hosted ? { printer_profile: profile } : {}),
      });
      if (!current()) return;
      if (!structural?.design) throw new Error(kind === "base_trim"
        ? "The Base Trim preview is not available right now."
        : "The case preview is not available right now.");
      // Its own client lane: a structural request never supersedes, or is
      // superseded by, the Designer's own previews.
      result = await api("/api/preview", {
        design: structural.design, client_id: `${previewClientId}-structural`, generation: identity.request,
      });
      if (!current()) return;
      if (result.superseded) return; // a newer structural request owns the lane
    } else {
      // R4: production meshes only on this explicit structural-preview intent.
      const payload = await api("/api/space/structural-design", {
        space: structuralWithDrawerIds(draft.space), include_preview: true,
        ...(hosted ? { printer_profile: profile } : {}),
      });
      if (!current()) return;
      if (!payload?.preview) throw new Error("The cabinet preview is not available right now.");
      result = payload.preview;
    }
    state.structuralPreview = result;
    state.structuralPreviewError = "";
    state.structuralPreviewStale = false;
    if (state.structuralHighlightOwner) {
      const owners = new Set((result.meshes || []).map(mesh => mesh.owner));
      if (!owners.has(state.structuralHighlightOwner)) state.structuralHighlightOwner = null;
    }
    record.form?.setOutside?.(structuralOutsideXYZ(result, kind));
    record.form?.setError?.("");
    setStructuralPreviewState("");
    renderPreview3D();
  } catch (error) {
    if (!current()) return;
    state.structuralPreview = null;
    state.structuralPreviewStale = false;
    state.structuralPreviewError = friendlyError(error);
    record.form?.setError?.(state.structuralPreviewError);
    setStructuralPreviewState("Preview could not build", { error: true });
    renderPreview3D();
  }
}

// ---------------------------------------------------------------- 3D

let structuralBuffersCache = null;

function structuralKindColor(kind) {
  if (/^drawer/.test(kind)) return "#9bbfb0";
  if (/^cabinet/.test(kind)) return "#7d98a3";
  return kindColor(kind);
}

// The structural scene. Deliberately separate from renderPreview3DGL: the
// ordinary predicates (b4bEnabled, baseTrimEnabled, currentPreviewGroups ...)
// read the ordinary state.design and must never see the structural target.
function renderStructuralPreview3D() {
  const overlayCanvas = $("#preview-3d");
  const solidCanvas = $("#preview-3d-solid");
  const meshes = state.structuralPreview?.meshes || [];
  const renderer = ensurePreviewGL();
  const camera = state.camera;
  if (!renderer || renderer.lost) {
    if (solidCanvas) solidCanvas.hidden = true;
    drawGeometryLegacy2D(overlayCanvas, meshesToLegacyFaces(meshes), camera);
    return;
  }
  if (solidCanvas) solidCanvas.hidden = false;
  const { context, width, height } = canvasSize(overlayCanvas);
  context.clearRect(0, 0, width, height);
  state.previewDimensionHandles = [];
  state.previewSupportPolygons = [];
  state.previewPickMeshContext = null;
  if (!meshes.length) {
    window.Preview3DGL.draw(renderer, null, window.Preview3DGL.computeFrame(camera, null, width, height), width, height, []);
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText(state.structuralPreviewError || "Building preview…", width / 2, height / 2);
    return;
  }
  const highlight = typeof state.structuralHighlightOwner === "string" ? state.structuralHighlightOwner : null;
  const cache = structuralBuffersCache;
  if (!cache || cache.source !== meshes || cache.highlight !== highlight || cache.generation !== renderer.generation) {
    if (cache) window.Preview3DGL.disposeBuffers(renderer.gl, cache.buffers);
    const owners = [...new Set(meshes.map(mesh => mesh.owner))];
    structuralBuffersCache = {
      source: meshes, highlight, generation: renderer.generation, owners,
      buffers: window.Preview3DGL.buildBuffersFromMeshes(renderer.gl, meshes, owners, structuralKindColor, highlight),
    };
  }
  const { buffers, owners } = structuralBuffersCache;
  const frame = window.Preview3DGL.computeFrame(camera, buffers.allAabb, width, height);
  window.Preview3DGL.draw(renderer, buffers, frame, width, height, owners.map(group => ({ group, alpha: 1 })));
  const project = point => [
    width / 2 + (point[0] - frame.midX) * frame.scale,
    height / 2 + (point[1] - frame.midY) * frame.scale,
  ];
  drawStructuralOverlay(context, camera, project, buffers);
  if (state.structuralPreviewStale) {
    context.save();
    context.font = 'bold 13px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
    context.textAlign = "center";
    context.textBaseline = "top";
    context.fillStyle = "#8a4b00";
    context.fillText("Last valid preview", width / 2, 10);
    context.restore();
  }
}

const STRUCTURAL_AXIS_NAME = { x: "Width", y: "Depth", z: "Height" };

// Interior Width / Depth / Height guides with draggable labels (R1). The
// guides wrap the drawn geometry's own bounds; the labels and the drag edit
// the interior values through the form's single normalization path.
function drawStructuralOverlay(context, camera, project, buffers) {
  const aabb = buffers.allAabb;
  const record = structuralEditorRecord;
  if (!aabb || !record?.form?.getInterior) return;
  const center = [(aabb.min[0] + aabb.max[0]) / 2, (aabb.min[1] + aabb.max[1]) / 2, aabb.min[2]];
  const shift = iso(center, camera);
  // draw3DDimensions centres its footprint on the origin; a pure translation
  // in world space is a translation in iso space, so shift the projection.
  const centered = point => project([point[0] + shift[0], point[1] + shift[1]]);
  const size = [aabb.max[0] - aabb.min[0], aabb.max[1] - aabb.min[1], aabb.max[2] - aabb.min[2]];
  const drag = state.structuralDimensionDrag;
  if (drag) size["xyz".indexOf(drag.axis)] += drag.currentValue - drag.startValue;
  const interior = record.form.getInterior();
  const unit = Number(state.catalog?.base_unit || 8);
  let zSpan = null;
  if (record.kind === "storage_drawers") {
    const owner = `drawer:${record.form.activeDrawerId?.()}`;
    const box = buffers.groups[owner]?.aabb;
    if (box) zSpan = [box.min[2] - center[2], box.max[2] - center[2]];
  }
  const label = axis => {
    const value = interior[axis];
    if (!Number.isFinite(value)) return `Interior ${STRUCTURAL_AXIS_NAME[axis]} —`;
    const units = axis === "z" ? "" : ` · ${value / unit} ${value / unit === 1 ? "unit" : "units"}`;
    return `Interior ${STRUCTURAL_AXIS_NAME[axis]} ${fmt(value)} mm${units}`;
  };
  draw3DDimensions(
    context, { x: interior.x, y: interior.y, z: interior.z }, camera, centered, size,
    {
      interactive: axis => Number.isFinite(interior[axis]) && !record.saving,
      value: axis => interior[axis],
      label, zSpan,
    },
  );
  if (drag) {
    const hx = size[0] / 2, hy = size[1] / 2, hz = size[2];
    const corners = [[-hx, -hy, 0], [hx, -hy, 0], [hx, hy, 0], [-hx, hy, 0], [-hx, -hy, hz], [hx, -hy, hz], [hx, hy, hz], [-hx, hy, hz]]
      .map(point => centered(iso(point, camera)));
    context.save();
    context.strokeStyle = "rgba(31, 107, 112, 0.85)";
    context.lineWidth = 1.25;
    context.setLineDash([5, 4]);
    for (const [a, b] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]]) {
      context.beginPath();
      context.moveTo(corners[a][0], corners[a][1]);
      context.lineTo(corners[b][0], corners[b][1]);
      context.stroke();
    }
    context.restore();
  }
  const front = project(iso([center[0], aabb.min[1] - 5, center[2]], camera));
  context.save();
  context.font = 'bold 13px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = "#153f48";
  context.fillText("FRONT", front[0], front[1]);
  context.restore();
}

// ---- structural dimension drag (same label grab as an ordinary bin, but the
// value goes through the form's one normalization path, never state.design) ----

function beginStructuralDimensionDrag(handle, canvas, event) {
  state.structuralDimensionDrag = {
    view: "3d",
    axis: handle.axis,
    pointerId: event.pointerId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    startValue: handle.value,
    currentValue: handle.value,
    displayStartValue: handle.displayValue,
    screenAxis: handle.screenAxis,
    pixelSpan: handle.pixelSpan,
  };
  state.dimensionHover = null;
  canvas.style.cursor = pickResizeCursor(handle);
  try { canvas.setPointerCapture(event.pointerId); } catch (_error) { /* synthetic event */ }
}

function updateStructuralDimensionDrag(clientX, clientY) {
  const drag = state.structuralDimensionDrag;
  const form = structuralEditorRecord?.form;
  if (!drag || !form) return;
  const projected = (clientX - drag.startClientX) * drag.screenAxis[0] + (clientY - drag.startClientY) * drag.screenAxis[1];
  const pixelsPerMm = drag.pixelSpan / Math.max(1e-6, drag.displayStartValue);
  const applied = form.setInterior(drag.axis, drag.startValue + projected / pixelsPerMm);
  if (Number.isFinite(applied)) drag.currentValue = applied;
}

function endStructuralDimensionDrag(canvas, { commit }) {
  const drag = state.structuralDimensionDrag;
  if (!drag) return;
  state.structuralDimensionDrag = null;
  releaseDimensionPointerCapture(canvas, drag.pointerId);
  const form = structuralEditorRecord?.form;
  if (!commit && form && drag.currentValue !== drag.startValue) form.setInterior(drag.axis, drag.startValue);
  // The release schedules the final geometry request immediately.
  scheduleStructuralPreview({ immediate: true });
}

// ---------------------------------------------------------------- 2D

// R5: the structural 2D view is the Space canvas, view/pan only. Space remains
// the sole placement owner (DP.structuralReadOnly2D gates every mutation path
// in drawer-view.js).
function activateStructural2D() {
  activatePreviewView("drawer");
  $$(".view-tab").forEach(tab => {
    const on = tab.dataset.view === "2d";
    tab.classList.toggle("active", on);
    tab.setAttribute("aria-selected", String(on));
    tab.tabIndex = on ? 0 : -1;
  });
  state.lastDesignView = "2d";
  const wrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (wrap && !wrap.querySelector(".structural-2d-badge")) {
    const badge = structuralEl("div", "structural-2d-badge", "View only. Place and move bins in Space. ");
    // The sole placement-edit handoff: the existing mode switch, which also
    // settles an unsaved structural draft first.
    const go = structuralEl("button", "structural-2d-go", "Go to Space");
    go.type = "button";
    go.addEventListener("click", () => { DP.selectMode("space"); });
    badge.append(go);
    wrap.append(badge);
  }
}

// ---------------------------------------------------------------- Save / Cancel

// Save Changes is the only persistence boundary (R1/R2). It commits through
// the existing cabinet / Space mutation owners and bypasses the leave prompt.
async function structuralSaveChanges() {
  const record = structuralEditorRecord;
  if (!record?.form || record.saving) return false;
  const kind = record.kind;
  record.saving = true;
  updateStructuralActions();
  setStructuralStatus("Saving…");
  try {
    if (kind === "storage_drawers") {
      const form = record.form;
      let result = form.read();
      if (!result.ok && result.pending && form.whenValidationSettled) {
        await form.whenValidationSettled(30000);
        result = form.read();
      }
      if (!result.ok) { setStructuralStatus(result.message || "Fix the cabinet settings first.", { error: true }); return false; }
      const draft = result.spaceDraft;
      // The existing serialized cabinet mutation checks every placement before
      // anything is committed; a conflict throws and leaves the draft dirty.
      const updated = await SP.mutateCabinet("reconfigure", {
        space: { kind: "storage_drawers", name: draft.name, x: draft.x, y: draft.y, z: draft.z, storage_drawers: draft.storage_drawers },
      });
      if (!updated) { setStructuralStatus("The cabinet changed before it could be saved. Try again.", { error: true }); return false; }
    } else {
      const draft = structuralDraftResult();
      if (!draft.ok) { setStructuralStatus(draft.message, { error: true }); return false; }
      const space = state.activeSpace;
      await SP.commitSpaceUpdate({
        kind: space.kind, name: space.name, x: draft.space.x, y: draft.space.y, z: draft.space.z,
        trimSize: null, extra: { storage_box: draft.space.storage_box },
      }, { structural: true });
    }
    // Accepted: rebuild the editor from the accepted Space so it is pristine,
    // keeping the active drawer and the highlight.
    // (A cabinet Save already remounted it when the accepted Space was adopted.)
    if (structuralEditorRecord === record) syncStructuralEditor({ force: true });
    setStructuralStatus("");
    toast("Space updated.");
    return true;
  } catch (error) {
    if (!(typeof DL !== "undefined" && DL.isStaleSpaceError?.(error))) {
      setStructuralStatus(friendlyError(error), { error: true });
      toast(friendlyError(error), true, 6000);
    }
    return false;
  } finally {
    record.saving = false;
    if (structuralEditorRecord === record) updateStructuralActions();
  }
}

// Add Drawer / Delete Drawer in full structural Design (Correction 1 C2). The
// form only asks; the existing cabinet mutation authority (SP.cabinetAdd /
// SP.cabinetDelete -> SP.mutateCabinet) keeps every placement check,
// confirmation, hosted/local persistence rule and history reset. A dirty draft
// is settled first through the one dirty/leave owner; an adopted result
// rebuilds the editor from the new accepted Space.
async function structuralCabinetMutation(kind, drawerId = null) {
  const first = structuralEditorRecord;
  if (!first || first.kind !== "storage_drawers" || first.saving || first.mutating) return false;
  first.mutating = true;
  try {
    // Save may remount the editor; read the live record again afterwards.
    if (!(await SP.confirmLeaveStructuralEditor())) return false;
    const adopted = kind === "add" ? await SP.cabinetAdd() : await SP.cabinetDelete(drawerId);
    if (adopted && structuralEditorRecord && structuralTargetKind() === "storage_drawers") {
      // Adoption normally rebuilt it already (SP.renderSpaceInfo); make sure.
      if (structuralEditorRecord.spaceKey !== structuralSpaceKey()) syncStructuralEditor({ force: true });
    }
    return Boolean(adopted);
  } finally {
    first.mutating = false;
  }
}

// Cancel / Discard: drop the draft and show the accepted Space again.
async function structuralDiscardDraft() {
  if (!structuralEditorRecord) return true;
  syncStructuralEditor({ force: true });
  setStructuralStatus("");
  return true;
}
