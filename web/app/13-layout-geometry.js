"use strict";

function wireSupportLayoutDialog() {
  const dialog = $("#support-layout-dialog");
  $("#support-layout-dialog-open").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    try { localStorage.setItem("wavefinity-3d-pick-help-dismissed",
      $("#support-layout-remember").checked ? "1" : "0"); }
    catch (_error) { toast("Your choice could not be remembered in this browser.", true); }
  });
}

async function selectFromPreview(pick, context) {
  if (!pick) return;
  const current = (expectedDesign = context.design, ownCommit = false) =>
    state.design === expectedDesign &&
    state.designInventoryId === context.source && state.activeSpace === context.space &&
    state.previewRequest === context.preview + Number(ownCommit) && DP.mode === "design";
  if (!current()) return;
  const status = $("#preview-state");
  status.textContent = "Selecting part…";
  status.classList.add("preview-pending");
  try {
    if (pick.type === "saved") {
      if (!Number.isInteger(pick.index)) return;
      const alreadySelected = pick.index === state.selected;
      if (!(await selectedFeature(pick.index, false, current))) return;
      if (alreadySelected && !current()) return;
      // Selecting cancels the old preview request itself. Its guard already
      // rejects stale design/Space switches; check the accepted target here.
      if (state.designInventoryId !== context.source || state.activeSpace !== context.space ||
          state.selected !== pick.index || DP.mode !== "design") return;
    } else if (pick.type !== "draft" || !state.draft) return;
    activatePreviewView("2d");
    renderLayout2D();
    let dismissed = false;
    try { dismissed = localStorage.getItem("wavefinity-3d-pick-help-dismissed") === "1"; } catch (_error) {}
    if (!dismissed) {
      $("#support-layout-remember").checked = true;
      const dialog = $("#support-layout-dialog");
      if (!dialog.open) dialog.showModal();
    }
  } finally {
    status.classList.remove("preview-pending");
    if (status.textContent === "Selecting part…") status.textContent = "";
  }
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

// A completed drag uses the same design-change path as a typed
// Width/Length/Height edit, so manual-size and auto-grow semantics stay
// identical between mouse and keyboard.
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
        // Fix 103 (R1): a structural label edits the structural form's draft,
        // never state.design.
        if (handle.structural) beginStructuralDimensionDrag(handle, canvas, event);
        else beginDimensionDrag("3d", handle, canvas, event);
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
    if (state.structuralDimensionDrag) {
      updateStructuralDimensionDrag(event.clientX, event.clientY);
      repaint();
      return;
    }
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
    if (state.structuralDimensionDrag) {
      endStructuralDimensionDrag(canvas, { commit: true });
      repaint();
      return;
    }
    if (state.dimensionDrag) {
      commitDimensionDrag(canvas);
      repaint();
      return;
    }
    const clickedSupport = drag && !drag.moved && clickedPreviewSupport(canvas, event);
    const pickContext = { design: state.design, source: state.designInventoryId,
      space: state.activeSpace, preview: state.previewRequest };
    drag = null;
    if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    if (clickedSupport) void selectFromPreview(clickedSupport, pickContext);
  });
  canvas.addEventListener("pointercancel", () => {
    if (state.structuralDimensionDrag) {
      endStructuralDimensionDrag(canvas, { commit: false });
      repaint();
    }
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
  context.font = '700 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
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
    context.font = 'italic 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText("Label", centerCanvas[0], centerCanvas[1]);
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
  const fontSizePx = Math.max(1, (cap / 0.729) * scale);
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