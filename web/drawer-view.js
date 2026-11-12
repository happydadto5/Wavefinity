"use strict";

// Drawer layout mode - the drawer canvas.
//
// A camera looking into the drawer, not a free orbit. It always stands in
// front of the drawer and above it, looking in: you choose how steeply (Angle,
// from low to overhead), turn a little to either side (Turn, up to 30°), pan
// and zoom - but never spin it round or look from underneath, so the front of
// the drawer is always the side nearest you. Bins are real boxes in
// perspective: their tops, the fronts and the sides that face you, lit from
// above.

const DV = {
  view: { tilt: 48, turn: 0, top: false, zoom: 1, panX: 0, panY: 0 },
  LIMITS: { tilt: [22, 86], turn: [-30, 30], zoom: [0.5, 6] },
  PRESETS: { look: { tilt: 48, turn: 0 }, overhead: { top: true }, low: { tilt: 26, turn: 0 } },
  hits: [],
  drag: null,
  pan: null,
  hover: null,
  drop: null,
  dragBin: null,
  cam: null,
};

try {
  const saved = JSON.parse(localStorage.getItem("wavefinity-drawer-camera") || "{}");
  if (Number.isFinite(saved.tilt)) DV.view.tilt = saved.tilt;
  if (Number.isFinite(saved.turn)) DV.view.turn = saved.turn;
} catch (_error) {}
DV.saveView = debounce(() => {
  try { localStorage.setItem("wavefinity-drawer-camera", JSON.stringify({ tilt: DV.view.tilt, turn: DV.view.turn })); }
  catch (_error) { toast("The camera view could not be remembered in this browser.", true); }
}, 300);

const dvClamp = (value, [low, high]) => Math.max(low, Math.min(high, Number(value) || 0));
const V3 = {
  add: (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]],
  sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
  scale: (a, s) => [a[0] * s, a[1] * s, a[2] * s],
  dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
  cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
  norm: a => { const length = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / length, a[1] / length, a[2] / length]; },
};

// ------------------------------------------------------------------ camera

DV.syncControls = () => {
  const tilt = $("#dl-tilt");
  const turn = $("#dl-turn");
  // A Pegboard has one fixed camera, so the angle sliders and the Look in /
  // Overhead / Low presets do nothing there; Fit and zoom still work.
  const fixedCamera = Boolean(DL.layout && DL.isPegboard());
  const sliderRow = tilt?.closest(".camera-controls-row");
  if (sliderRow) sliderRow.hidden = fixedCamera;
  $$("[data-dl-view]").forEach(button => {
    if (button.dataset.dlView !== "fit") button.hidden = fixedCamera;
  });
  if (tilt) tilt.value = String(Math.round(DV.view.tilt));
  if (turn) turn.value = String(Math.round(DV.view.turn));
  // Overhead is a flat plan: angle has no meaning there, so the sliders grey out.
  if (tilt) tilt.disabled = DV.view.top;
  if (turn) turn.disabled = DV.view.top;
  $$(".dl-tilt-control").forEach(label => label.classList.toggle("disabled", DV.view.top));
  $$("[data-dl-view]").forEach(button => {
    const preset = DV.PRESETS[button.dataset.dlView];
    button.classList.toggle("active", Boolean(preset) && (preset.top
      ? DV.view.top
      : !DV.view.top && Math.round(DV.view.tilt) === preset.tilt && Math.round(DV.view.turn) === preset.turn));
  });
};

DV.setView = ({ tilt = DV.view.tilt, turn = DV.view.turn, top = false } = {}) => {
  DV.view.top = Boolean(top);
  DV.view.tilt = dvClamp(tilt, DV.LIMITS.tilt);
  DV.view.turn = dvClamp(turn, DV.LIMITS.turn);
  DV.syncControls();
  DV.saveView();
  DV.render();
};

DV.fit = () => {
  Object.assign(DV.view, { zoom: 1, panX: 0, panY: 0 });
  DV.render();
};

DV.size = () => {
  const box = $("#drawer-canvas")?.getBoundingClientRect();
  return box ? [box.width, box.height] : [0, 0];
};

// Zoom about a screen point: the floor point under it stays put.
DV.zoomBy = (factor, sx = null, sy = null) => {
  const [width, height] = DV.size();
  if (!DL.layout || !width) return;
  const drawer = DL.drawer();
  const camera = () => DL.isPegboard(drawer) ? DV.pegboardCamera(width, height, drawer) : DV.camera(width, height, drawer);
  const before = sx === null ? null : camera().onPlane(sx, sy, 0);
  DV.view.zoom = dvClamp(DV.view.zoom * factor, DV.LIMITS.zoom);
  if (before) {
    const after = camera().onPlane(sx, sy, 0);
    if (after) {
      DV.view.panX += before[0] - after[0];
      DV.view.panY += before[1] - after[1];
    }
  }
  DV.clampPan(drawer);
  DV.render();
};

DV.clampPan = drawer => {
  DV.view.panX = Math.max(-drawer.width * 0.6, Math.min(drawer.width * 0.6, DV.view.panX));
  DV.view.panY = Math.max(-drawer.depth * 0.6, Math.min(drawer.depth * 0.6, DV.view.panY));
};

// A perspective camera standing in front of and above the drawer, aimed at
// its middle. At zoom 1 it stands just far enough back to frame the whole
// drawer; zooming walks it in, never below the drawer's rim.
DV.safeFrame = (width, height) => {
  const canvas = $("#drawer-canvas");
  const controls = $('.canvas-wrap[data-canvas="drawer"] .dl-view-controls');
  const canvasBox = canvas?.getBoundingClientRect();
  const controlBox = controls && !controls.hidden ? controls.getBoundingClientRect() : null;
  const top = canvasBox && controlBox
    ? Math.max(0, Math.min(height - 80, controlBox.bottom - canvasBox.top + 12))
    : 0;
  const bottom = 30;
  return {
    top,
    bottom,
    height: Math.max(80, height - top - bottom),
    cy: top + Math.max(80, height - top - bottom) / 2,
  };
};
// Overhead: straight down, orthographic, so the Space draws as a flat 2D plan.
// Height is ignored (project drops z, onPlane returns the floor point), so
// nothing recedes and picking/dragging work exactly as in the tilted view.
DV.topCamera = (width, height, drawer, view = DV.view) => {
  const pad = 34;
  const frame = DV.safeFrame(width, height);
  const scale = Math.max(
    0.05,
    Math.min((width - 2 * pad) / drawer.width, (frame.height - 2 * pad) / drawer.depth) * view.zoom,
  );
  const left = (width - drawer.width * scale) / 2 - view.panX * scale;
  const top = frame.cy - (drawer.depth * scale) / 2 + view.panY * scale;
  return {
    W: drawer.width, D: drawer.depth, H: 0, rimH: 0, flat: true,
    eye: [drawer.width / 2, drawer.depth / 2, 1e6],
    project: point => [left + point[0] * scale, top + (drawer.depth - point[1]) * scale],
    onPlane: (sx, sy) => [(sx - left) / scale, drawer.depth - (sy - top) / scale, 0],
  };
};
DV.camera = (width, height, drawer, view = DV.view) => {
  if (view.top) return DV.topCamera(width, height, drawer, view);
  const W = drawer.width;
  const D = drawer.depth;
  const H = DL.isSurface() ? Math.max(drawer.height, ...DL.items(drawer).map(item => item.plan_h || item.h)) : drawer.height;
  const tilt = view.tilt * Math.PI / 180;
  const turn = view.turn * Math.PI / 180;
  const away = [Math.sin(turn) * Math.cos(tilt), -Math.cos(turn) * Math.cos(tilt), Math.sin(tilt)];
  const frame = DV.safeFrame(width, height);
  const focal = (frame.height / 2) / Math.tan(17 * Math.PI / 180); // a 34° field of view
  const margin = 36;
  const halfW = Math.max(40, width / 2 - margin);
  const halfH = Math.max(40, frame.height / 2 - margin);
  const cx = width / 2;
  const cy = frame.cy;
  const basis = (target, dist) => {
    const f = V3.scale(away, -1);
    const r = V3.norm(V3.cross(f, [0, 0, 1]));
    return { eye: V3.add(target, V3.scale(away, dist)), f, r, u: V3.cross(r, f) };
  };
  const corners = [];
  for (const x of [0, W]) for (const y of [0, D]) for (const z of [0, H]) corners.push([x, y, z]);
  const home = [W / 2, D / 2, H / 3];
  let fit = 1.6 * Math.hypot(W, D, H);
  for (let pass = 0; pass < 5; pass += 1) {
    const b = basis(home, fit);
    let need = 0;
    for (const corner of corners) {
      const v = V3.sub(corner, b.eye);
      const depth = V3.dot(v, b.f);
      if (depth <= 1) { need = 2; break; }
      need = Math.max(need,
        Math.abs(focal * V3.dot(v, b.r) / depth) / halfW,
        Math.abs(focal * V3.dot(v, b.u) / depth) / halfH);
    }
    fit *= need || 1;
  }
  const target = [home[0] + view.panX, home[1] + view.panY, home[2]];
  // Never let a close zoom put the lens inside the drawer.
  const lowest = (H * 1.25 + 25 - target[2]) / Math.max(0.2, away[2]);
  // Unified Space entry must fit even a small Space, despite the normal zoom safety distance.
  const minimum = typeof WS !== "undefined" && WS.open() ? Math.min(fit, lowest) : lowest;
  const b = basis(target, Math.max(fit / view.zoom, minimum));
  const project = point => {
    const v = V3.sub(point, b.eye);
    const depth = Math.max(0.5, V3.dot(v, b.f));
    return [cx + focal * V3.dot(v, b.r) / depth, cy - focal * V3.dot(v, b.u) / depth];
  };
  const onPlane = (sx, sy, z = 0) => {
    const ray = V3.norm(V3.add(b.f, V3.add(V3.scale(b.r, (sx - cx) / focal), V3.scale(b.u, -(sy - cy) / focal))));
    if (Math.abs(ray[2]) < 1e-6) return null;
    const t = (z - b.eye[2]) / ray[2];
    return t > 0 ? V3.add(b.eye, V3.scale(ray, t)) : null;
  };
  // Framing may grow to the tallest planned object, but the drawn rim/walls stay
  // at the Space's real boundary height: an open Surface never grows tall walls.
  return { W, D, H, rimH: DL.isSurface() ? drawer.height : H, eye: b.eye, project, onPlane };
};

DV.pegboardCamera = (width, height, drawer) => {
  const pad = 34;
  const frame = DV.safeFrame(width, height);
  const scale = Math.max(
    0.05,
    Math.min((width - 2 * pad) / drawer.width, (frame.height - 2 * pad) / drawer.depth) * DV.view.zoom,
  );
  const left = (width - drawer.width * scale) / 2 - DV.view.panX * scale;
  const top = frame.cy - (drawer.depth * scale) / 2 + DV.view.panY * scale;
  return {
    W: drawer.width, D: drawer.depth, H: 0, eye: [drawer.width / 2, -1, drawer.depth / 2],
    project: point => [left + point[0] * scale, top + (drawer.depth - point[1]) * scale],
    onPlane: (sx, sy) => [(sx - left) / scale, drawer.depth - (sy - top) / scale, 0],
  };
};

// ------------------------------------------------------------------ colour

DV.heightRange = () => {
  const heights = DL.bins.filter(one => !DL.isSpacer(one)).map(one => DL.isSurface() ? DL.effectiveHeight(one) : Number(one.z));
  return heights.length ? [Math.min(...heights), Math.max(...heights)] : [0, 1];
};

// Short bins light, tall bins dark, so height order reads at a glance. `top`,
// `front` and `ink` stay plain colour strings for the panel's swatches.
DV.binColor = (one, range) => {
  let hue, sat, light;
  if (one.kind === "spacer") [hue, sat, light] = one.boundary === "edge" ? [42, 28, 72] : [43, 20, 82];
  else {
    const height = DL.isSurface() ? DL.effectiveHeight(one) : Number(one.z);
    const t = range[1] > range[0] ? (height - range[0]) / (range[1] - range[0]) : 0.5;
    const b4b = one.kind === "b4b";
    hue = b4b ? 262 : 188 - t * 6;
    sat = b4b ? 28 : 30 + t * 22;
    light = 85 - t * 42;
  }
  return {
    hue, sat, light,
    top: `hsl(${hue} ${sat}% ${light}%)`,
    front: `hsl(${hue} ${sat}% ${light - 13}%)`,
    ink: light < 60 ? "#ffffff" : "#17252d",
  };
};

DV.tone = (color, delta) => `hsl(${color.hue} ${color.sat}% ${Math.max(8, Math.min(97, color.light + delta))}%)`;

// How much light each face gets: tops brightest, then the front, the sides
// and the back.
DV.FACE_TONE = { top: 0, front: -11, back: -20, left: -17, right: -15 };

DV.hatch = (ctx, color) => {
  const tile = document.createElement("canvas");
  tile.width = tile.height = 8;
  const pen = tile.getContext("2d");
  pen.strokeStyle = color;
  pen.lineWidth = 1.2;
  pen.beginPath();
  pen.moveTo(0, 8); pen.lineTo(8, 0);
  pen.moveTo(-2, 2); pen.lineTo(2, -2);
  pen.moveTo(6, 10); pen.lineTo(10, 6);
  pen.stroke();
  return ctx.createPattern(tile, "repeat");
};

DV.problemKeys = () => {
  const keys = new Map();
  for (const problem of DL.report?.problems || []) {
    const tone = DL.isAdvisoryProblem(problem) ? "height" : "error";
    problem.keys.forEach(key => { if (keys.get(key) !== "error") keys.set(key, tone); });
  }
  return keys;
};

DV.fitText = (ctx, text, maxWidth) => {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) cut = cut.slice(0, -1);
  return cut.length > 1 ? `${cut}…` : "";
};

// ------------------------------------------------------------------ scene

// Everything standing in the drawer, as footprints with their layers, with a
// drag or drop shown where it would land. Every layer carries its own
// footprint rectangle: a smaller bin on a larger lid covers only its part.
DV.entries = (drawer, grid) => {
  const box = (gx, gy, w, d) => ({ x0: grid.ox + gx * grid.stepX, y0: grid.oy + gy * grid.stepY, x1: grid.ox + (gx + w) * grid.stepX, y1: grid.oy + (gy + d) * grid.stepY });
  const entries = [];
  const drag = DV.drag?.moved ? DV.drag : null;
  for (const item of DL.items(drawer)) {
    const layers = item.layers.filter(layer => !drag?.keys.has(layer.key))
      .map(layer => ({ ...layer, ...box(layer.gx, layer.gy, layer.w, layer.d) }));
    if (layers.length) entries.push({ key: item.key, item,
      ex: DL.envelopeExtForBins(layers.map(layer => layer.bin), drawer),
      ...box(item.gx, item.gy, item.w, item.d), layers, mode: "" });
  }
  for (const p of drawer.placements.filter(DL.isEdgePlacement)) {
    const one = DL.bin(p.bin);
    if (one) entries.push({ key: DL.key(p), x0: p.x, y0: p.y, x1: p.x + p.w, y1: p.y + p.d, layers: [{ bin: one, key: DL.key(p), z0: 0, z1: Number(one.z), x0: p.x, y0: p.y, x1: p.x + p.w, y1: p.y + p.d }], mode: "", edge: true });
  }
  const ghost = drag || DV.drop;
  if (ghost) {
    const moving = ghost.moving;
    const root = moving.nodes[0];
    const target = ghost.target;
    // A stack-target ghost seats on its support's next seating datum, at the
    // offset the pointer chose; a floor ghost stands at its own cell.
    const originX = target ? target.layer.gx + target.cx : ghost.gx;
    const originY = target ? target.layer.gy + target.cy : ghost.gy;
    const seat = !target ? 0
      : DL.usesStackMetrics() ? target.layer.z0 + DL.pitch(target.layer.bin)
        : target.layer.z1 - (DL.stackSteps[root.bin.stack] ?? 0);
    const layers = moving.nodes.map(node => ({
      bin: node.bin, key: node.key, z0: seat + node.rz0, z1: seat + node.rz1,
      gx: originX + node.dx, gy: originY + node.dy, w: node.w, d: node.d,
      parent: node.parent >= 0 ? moving.nodes[node.parent].key : null,
      ...box(originX + node.dx, originY + node.dy, node.w, node.d),
    }));
    const mode = drag?.outside ? "leaving" : ghost.valid ? "ghost" : "invalid";
    entries.push({ key: "__ghost", ...box(originX, originY, root.w, root.d),
      ex: DL.envelopeExtForBins(moving.bins, drawer), layers, mode, ghost: true });
  }
  return entries;
};

// Layers of one footprint in painting order (far side first, a bin after the
// one it stands on).
DV.layerOrder = (layers, eye) => DV.paintOrder(layers.map(layer => ({ ...layer, lz: layer.z0 })), eye);

// Which of two columns to paint first. Footprints never overlap, so a plane
// between them always exists; the column on the far side of that plane from
// the camera cannot hide the other one, so it is painted first.
DV.fartherFirst = (a, b, eye) => {
  if (a.x1 <= b.x0 + 1e-6) return eye[0] > a.x1;
  if (b.x1 <= a.x0 + 1e-6) return eye[0] < a.x0;
  if (a.y1 <= b.y0 + 1e-6) return eye[1] > a.y1;
  if (b.y1 <= a.y0 + 1e-6) return eye[1] < a.y0;
  if (a.lz !== undefined && b.lz !== undefined) return a.lz <= b.lz;   // one stands on the other: lower first
  if (a.ghost || b.ghost) return Boolean(b.ghost);    // a drag preview over a bin draws last
  return null;
};

DV.paintOrder = (entries, eye) => {
  const count = entries.length;
  const next = Array.from({ length: count }, () => []);
  const waiting = new Array(count).fill(0);
  for (let i = 0; i < count; i += 1) {
    for (let j = i + 1; j < count; j += 1) {
      const first = DV.fartherFirst(entries[i], entries[j], eye);
      if (first === null) continue;
      const [a, b] = first ? [i, j] : [j, i];
      next[a].push(b);
      waiting[b] += 1;
    }
  }
  const distance = entry => Math.hypot((entry.x0 + entry.x1) / 2 - eye[0], (entry.y0 + entry.y1) / 2 - eye[1]);
  const done = new Array(count).fill(false);
  const ready = [];
  for (let i = 0; i < count; i += 1) if (!waiting[i]) ready.push(i);
  const order = [];
  while (order.length < count) {
    if (!ready.length) {
      // A cycle (it takes odd shapes to make one): break it at the farthest.
      let pick = -1;
      for (let i = 0; i < count; i += 1) if (!done[i] && (pick < 0 || distance(entries[i]) > distance(entries[pick]))) pick = i;
      ready.push(pick);
    }
    ready.sort((a, b) => distance(entries[b]) - distance(entries[a]));
    const index = ready.shift();
    if (done[index]) continue;
    done[index] = true;
    order.push(entries[index]);
    for (const after of next[index]) {
      waiting[after] -= 1;
      if (waiting[after] <= 0 && !done[after]) ready.push(after);
    }
  }
  return order;
};

DV.render = () => {
  if (!DL.active || !DL.layout) return;
  const canvas = $("#drawer-canvas");
  const box = canvas.getBoundingClientRect();
  if (!box.width || !box.height) return;
  // Beyond 2x the extra pixels cost real time and show nothing: a 3x screen
  // would otherwise ask for nine times the fill of a 1x one.
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const pixelW = Math.round(box.width * dpr);
  const pixelH = Math.round(box.height * dpr);
  if (canvas.width !== pixelW || canvas.height !== pixelH) { canvas.width = pixelW; canvas.height = pixelH; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, box.width, box.height);
  const drawer = DL.drawer();
  DV.cam = DL.isPegboard(drawer) ? DV.pegboardCamera(box.width, box.height, drawer) : DV.camera(box.width, box.height, drawer);
  DV.hits = DL.isPegboard(drawer) ? DV.paintPegboardScene(ctx, drawer, DV.cam) : DV.paintScene(ctx, drawer, DV.cam);
  const emptyHint = $("#dl-empty-hint");
  if (emptyHint) {
    const hasBins = DL.bins.some(one => DL.isOrdinary(one));
    const drawerHasBins = drawer.placements?.some(placement => DL.isOrdinary(DL.bin(placement.bin)));
    const title = emptyHint.querySelector("strong");
    const detail = emptyHint.querySelector("span");
    if (hasBins) {
      if (title) title.textContent = "Drag bins to place";
      if (detail) detail.textContent = DL.isPegboard(drawer) ? "Drop them on the holes" : "Drag onto a bin to stack";
    } else {
      if (title) title.textContent = "No bins yet";
      if (detail) detail.textContent = "Choose New Bin to make one";
    }
    emptyHint.hidden = Boolean(!hasBins || DV.drag?.moved || drawerHasBins);
  }
  // Taking a bin off the Space is a drop onto the tree.
  $("#ws-stage")?.classList.toggle("receiving", Boolean(DV.drag?.moved && DV.drag.overTree));
  // Story 2932: one plain-text key for colours, front numbers and the stacking icon, in every Space kind.
  // Pegboard bins are one flat teal, so the height-shade segment is left out there.
  const colorKey = $("#dl-color-key");
  if (colorKey) {
    const shades = DL.isPegboard(drawer) ? [] : ["light teal = shortest bins, dark teal = tallest bins"];
    colorKey.textContent = `Colours: ${[...shades, "purple = Storage Box bin", "sand = spacer", "red = a problem to fix", "dashed orange outline = too tall to fit", "pale green = empty space"].join(" · ")}. The number on a bin's front is its place in the bin list (Bin 1, Bin 2… — it changes if an earlier bin is deleted); S1, S2… marks a spacer. The stacked-boxes icon means the bin can take a stack on top, can sit on another bin, or both, as its arrows show.`;
  }
  const heightLegend = $("#dl-height-legend");
  if (heightLegend) {
    // Story 2973: a Gridfinity Space states plainly whether its height fit is
    // verified (its baseplate's seated lift is recorded) - a note, never a dialog.
    const fit = DL.heightFit(drawer);
    const keyed = DL.isStorageBox() || DL.isStorageDrawers();
    heightLegend.hidden = !keyed && !fit;
    heightLegend.innerHTML = (keyed ? `<span class="dl-height-swatch yellow"></span>Yellow: below full height · <span class="dl-height-swatch red"></span>Red: over space height · ${DL.stackIconForRoles({ bottom: true })} can take a stack · ${DL.stackIconForRoles({ top: true })} can sit on a bin` : "")
      + (fit ? `<div class="dl-height-fit" data-verified="${fit.verified}">${fit.note}</div>` : "");
  }
};

DV.paintPegboardScene = (ctx, drawer, cam) => {
  const grid = DL.grid(drawer);
  const rect = (x0, y0, x1, y1) => [cam.project([x0, y0, 0]), cam.project([x1, y0, 0]), cam.project([x1, y1, 0]), cam.project([x0, y1, 0])];
  const path = points => { ctx.beginPath(); points.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)); ctx.closePath(); };
  const board = rect(0, 0, drawer.width, drawer.depth);
  path(board); ctx.fillStyle = "#d9c79e"; ctx.fill(); ctx.strokeStyle = "#816d48"; ctx.lineWidth = 2; ctx.stroke();
  const standard = state.catalog?.pegboard_rules?.standards?.find(row => row.id === drawer.pegboard_standard) || {};
  // One standard-aware logical->physical mount transform (Fix 111): the hole
  // loop and every exact-mount dot loop below share it, so the SKÅDIS
  // odd-row stagger can never drift between them again.
  const holeXY = (gx, gy) => [
    grid.ox + (gx + 0.5) * grid.stepX + (standard.stagger_x_mm && gy % 2 ? standard.stagger_x_mm : 0),
    grid.oy + (gy + 0.5) * grid.stepY,
  ];
  for (let gy = 0; gy < grid.rows; gy += 1) for (let gx = 0; gx < grid.cols; gx += 1) {
    const [px, py] = holeXY(gx, gy);
    if (px > drawer.width - grid.ox + 1e-9) continue;
    const [sx, sy] = cam.project([px, py, 0]);
    const [rx] = cam.project([px + Number(standard.opening_width_mm || 6) / 2, py, 0]);
    const [, ry] = cam.project([px, py + Number(standard.opening_height_mm || 6) / 2, 0]);
    ctx.beginPath();
    if (standard.opening_shape === "rounded_slot") ctx.roundRect(sx - Math.abs(rx - sx), sy - Math.abs(ry - sy), Math.abs(rx - sx) * 2, Math.abs(ry - sy) * 2, Math.abs(rx - sx));
    else ctx.arc(sx, sy, Math.max(1.5, Math.abs(rx - sx)), 0, Math.PI * 2);
    ctx.fillStyle = "#4e4638"; ctx.fill();
  }
  for (const entry of DV.entries(drawer, grid)) {
    if (entry.ghost) continue;
    const one = entry.layers[entry.layers.length - 1].bin;
    const layout = DL.pegboardRefreshError ? null : (DL.pegboardLayouts[one.id] || one.pegboard_layout);
    if (!layout || layout.error || !Array.isArray(layout.mount_offsets)) continue;
    const baseGx = Math.round((entry.x0 - grid.ox) / grid.stepX);
    const baseGy = Math.round((entry.y0 - grid.oy) / grid.stepY);
    for (const [mx, my] of layout.mount_offsets) {
      const [px, py] = holeXY(baseGx + mx, baseGy + my);
      const [hx, hy] = cam.project([px, py, 0]);
      ctx.beginPath();
      ctx.arc(hx, hy, 5, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(255, 225, 107, 0.34)";
      ctx.fill();
      ctx.strokeStyle = "rgba(169, 116, 0, 0.72)";
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }
  const hits = [];
  const problems = DV.problemKeys();
  for (const entry of DV.entries(drawer, grid)) {
    const one = entry.layers[entry.layers.length - 1].bin;
    const poly = rect(entry.x0, entry.y0, entry.x1, entry.y1);
    path(poly);
    const invalid = entry.mode === "invalid" || entry.layers.some(layer => problems.get(layer.key) === "error");
    ctx.fillStyle = invalid ? "rgba(210,75,63,.72)" : entry.ghost ? "rgba(63,155,155,.55)" : "rgba(67,137,139,.86)";
    ctx.fill(); ctx.strokeStyle = DL.selected && entry.layers.some(layer => layer.key === DL.selected) ? "#ffb000" : "#244b4c"; ctx.lineWidth = 2; ctx.stroke();
    const [cx, cy] = cam.project([(entry.x0 + entry.x1) / 2, (entry.y0 + entry.y1) / 2, 0]);
    const info = DV.binLabelInfo(one, 1);
    const boxW = Math.abs(poly[1][0] - poly[0][0]);
    const boxH = Math.abs(poly[3][1] - poly[0][1]);
    ctx.fillStyle = "white";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    DV.drawStackIcon(ctx, poly, one, "white");
    if (boxH >= 40 && boxW >= 55) {
      const fontSize = Math.min(12, boxW / Math.max(4, info.name.length * 0.55));
      const subSize = Math.max(7.5, Math.min(9.5, fontSize * 0.8));
      const lineGap = subSize * 1.25;
      ctx.font = `700 ${fontSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
      ctx.fillText(DV.fitText(ctx, info.name, boxW - 8), cx, cy - lineGap);
      ctx.font = `500 ${subSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
      ctx.fillText(DV.fitText(ctx, info.dimLine, boxW - 8), cx, cy);
      ctx.fillText(DV.fitText(ctx, info.heightLine, boxW - 8), cx, cy + lineGap);
    } else if (boxH >= 24 && boxW >= 40) {
      const fontSize = Math.min(11, boxW / Math.max(4, info.name.length * 0.55));
      const subSize = Math.max(7, Math.min(9, fontSize * 0.8));
      const lineGap = subSize * 0.65;
      ctx.font = `700 ${fontSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
      ctx.fillText(DV.fitText(ctx, info.name, boxW - 8), cx, cy - lineGap);
      ctx.font = `500 ${subSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
      const compactDetail = `${fmt(one.x)}×${fmt(one.y)} · ${fmt(one.z)} mm`;
      ctx.fillText(DV.fitText(ctx, compactDetail, boxW - 8), cx, cy + lineGap);
    } else {
      ctx.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
      ctx.fillText(DV.fitText(ctx, info.name, Math.max(20, boxW - 8)), cx, cy);
    }
    if (!entry.ghost) {
      entry.layers.forEach(layer => hits.push({
        key: layer.key,
        grid: true,
        z: 0,
        polys: [poly],
      }));
    }
    const selected = entry.layers.some(layer => layer.key === DL.selected);
    if (selected) {
      const layout = DL.pegboardRefreshError ? null : (DL.pegboardLayouts[one.id] || one.pegboard_layout);
      for (const [mx, my] of layout?.mount_offsets || []) {
        const baseGx = Math.round((entry.x0 - grid.ox) / grid.stepX);
        const baseGy = Math.round((entry.y0 - grid.oy) / grid.stepY);
        const [px, py] = holeXY(baseGx + mx, baseGy + my);
        const [hx, hy] = cam.project([px, py, 0]);
        ctx.beginPath(); ctx.arc(hx, hy, 5, 0, Math.PI * 2); ctx.fillStyle = "#ffe16b"; ctx.fill(); ctx.strokeStyle = "#5d4800"; ctx.stroke();
      }
    }
  }
  return hits;
};

// One repaint per frame while dragging, panning or hovering. Pointer events
// arrive far faster than the screen refreshes and every repaint redraws the
// whole drawer, so the extra ones are work the screen never shows.
DV.framePending = false;
DV.paint = () => {
  if (DV.framePending) return;
  DV.framePending = true;
  requestAnimationFrame(() => { DV.framePending = false; DV.render(); });
};

DV.paintScene = (ctx, drawer, cam) => {
  const grid = DL.grid(drawer);
  const step = grid.step;
  const entries = DV.entries(drawer, grid);
  // Fix 2490: set below when any placed bin stack is over the Storage Box height,
  // so the height legend shows only in that case.
  DV.stackOverHeight = false;
  const { W, D, H, eye } = cam;
  const rimH = cam.rimH ?? H;
  const isFlat = Boolean(cam.flat);
  const shape = points => {
    const screen = points.map(cam.project);
    ctx.beginPath();
    screen.forEach(([x, y], index) => (index ? ctx.lineTo(x, y) : ctx.moveTo(x, y)));
    ctx.closePath();
    return screen;
  };
  const face = (points, fill, stroke = null, width = 1) => {
    const screen = shape(points);
    if (fill) { ctx.fillStyle = fill; ctx.fill(); }
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.stroke(); }
    return screen;
  };
  const flat = (x0, y0, x1, y1, z = 0) => [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]];
  const walls = [
    { inside: !isFlat && eye[1] < D, points: [[0, D, 0], [W, D, 0], [W, D, rimH], [0, D, rimH]], tone: "#e2d7c2" },
    { inside: !isFlat && eye[0] > 0, points: [[0, 0, 0], [0, D, 0], [0, D, rimH], [0, 0, rimH]], tone: "#dcd1bb" },
    { inside: !isFlat && eye[0] < W, points: [[W, 0, 0], [W, D, 0], [W, D, rimH], [W, 0, rimH]], tone: "#d9cdb6" },
    { inside: !isFlat && eye[1] > 0, points: [[0, 0, 0], [W, 0, 0], [W, 0, rimH], [0, 0, rimH]], tone: "#e0d5c0" },
  ];

  // The drawer: floor, then the inside faces of the walls you can see.
  face(flat(0, 0, W, D), "#f1ebdf", "rgba(120,100,70,.5)", 1.2);
  walls.filter(wall => wall.inside).forEach(wall => face(wall.points, wall.tone, "rgba(120,100,70,.35)"));

  // On the floor: the strips the grid cannot use, grid lines.
  const gx1 = grid.ox + grid.cols * step;
  const gy1 = grid.oy + grid.rows * step;
  const hatch = DV.hatch(ctx, "rgba(150,130,95,.35)");
  [[0, 0, grid.ox, D], [gx1, 0, W, D], [grid.ox, 0, gx1, grid.oy], [grid.ox, gy1, gx1, D]]
    .forEach(([x0, y0, x1, y1]) => { if (x1 - x0 > 0.05 && y1 - y0 > 0.05) face(flat(x0, y0, x1, y1), hatch); });
  const line = (a, b) => { const [ax, ay] = cam.project(a); const [bx, by] = cam.project(b); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); };
  ctx.lineWidth = 1;
  for (const [every, tone] of [[step, "rgba(120,100,70,.10)"], [grid.unit, "rgba(120,100,70,.2)"]]) {
    if (every === step && step === grid.unit) continue;
    ctx.strokeStyle = tone;
    ctx.beginPath();
    for (let x = 0; x <= grid.cols * step + 1e-6; x += every) line([grid.ox + x, grid.oy, 0], [grid.ox + x, gy1, 0]);
    for (let y = 0; y <= grid.rows * step + 1e-6; y += every) line([grid.ox, grid.oy + y, 0], [gx1, grid.oy + y, 0]);
    ctx.stroke();
  }

  // Empty cells, and the largest empty spot the report found.
  {
    const taken = new Set();
    entries.filter(entry => entry.item).forEach(entry => {
      const rect = DL.layersRect(entry.layers, drawer);
      for (let r = rect.y0; r < rect.y1; r += 1) {
        for (let c = rect.x0; c < rect.x1; c += 1) taken.add(`${c},${r}`);
      }
    });
    const inset = Math.min(0.6, step / 10);
    ctx.fillStyle = "rgba(47,150,110,.14)";
    for (let r = 0; r < grid.rows; r += 1) for (let c = 0; c < grid.cols; c += 1) {
      if (taken.has(`${c},${r}`)) continue;
      shape(flat(grid.ox + c * step + inset, grid.oy + r * step + inset, grid.ox + (c + 1) * step - inset, grid.oy + (r + 1) * step - inset));
      ctx.fill();
    }
    // Keep the report's subtle open-space outlines and the primary on-canvas
    // label in the preview.
    const opens = DL.report?.opens;
    if (opens && !DV.drag && DL.report.grid?.step === step) {
      opens.forEach((spot, index) => {
        const x0 = grid.ox + spot.gx * step, y0 = grid.oy + spot.gy * step;
        const x1 = grid.ox + (spot.gx + spot.w) * step, y1 = grid.oy + (spot.gy + spot.d) * step;
        ctx.save();
        ctx.setLineDash([5, 4]);
        face(flat(x0, y0, x1, y1), null, index === 0 ? "rgba(31,107,69,.8)" : "rgba(31,107,69,.5)", 1.5);
        ctx.restore();
        if (index > 0) return;
        const [ax] = cam.project([x0, (y0 + y1) / 2, 0]);
        const [bx] = cam.project([x1, (y0 + y1) / 2, 0]);
        const [mx, my] = cam.project([(x0 + x1) / 2, (y0 + y1) / 2, 0]);
        if (Math.abs(bx - ax) > 70) {
          ctx.fillStyle = "rgba(31,107,69,.9)";
          ctx.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          // Units only when the free area is a whole number of units; a
          // fractional figure is never rounded, so the label stays mm-only.
          const wUnits = spot.w_mm / grid.unit, dUnits = spot.d_mm / grid.unit;
          const whole = value => Math.abs(value - Math.round(value)) < 1e-9;
          const units = whole(wUnits) && whole(dUnits)
            ? ` - ${Math.round(wUnits)} × ${Math.round(dUnits)} ${grid.grid ? "cells" : "units"}` : "";
          ctx.fillText(`${fmt(spot.w_mm)} × ${fmt(spot.d_mm)} mm free${units}`, mx, my);
        }
      });
    }
  }

  // Bins, far columns first; within a column, layers bottom to top.
  const range = DV.heightRange();
  const problems = DV.problemKeys();
  const hits = [];
  const inset = 0.35;
  for (const entry of DV.paintOrder(entries, eye)) {
    const keys = entry.layers.map(layer => layer.key);
    const pick = entry.ghost ? null
      : DL.selected && keys.includes(DL.selected) ? DL.selected
        : DV.hover && keys.includes(DV.hover) ? DV.hover : null;
    // A label goes on the top face of every layer with nothing stacked on it,
    // naming the bin and how high its own stack is.
    const labels = [];
    const covered = new Set(entry.layers.map(layer => layer.parent));
    const byKey = new Map(entry.layers.map(layer => [layer.key, layer]));
    DV.layerOrder(entry.layers, eye).forEach(layer => {
      const one = layer.bin;
      const { z0, z1 } = layer;
      const x0 = layer.x0 + inset, x1 = layer.x1 - inset, y0 = layer.y0 + inset, y1 = layer.y1 - inset;
      const problem = problems.get(layer.key);
      let color = DV.binColor(one, range);
      if (entry.mode === "invalid" || problem === "error") color = { ...color, hue: 5, sat: 62, light: 83, ink: "#5e1f1b" };
      ctx.globalAlpha = entry.mode === "leaving" ? 0.35 : entry.mode === "ghost" ? 0.78 : 1;
      const faces = [];
      if (!isFlat) if (eye[1] < y0) faces.push(["front", [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]]]);
      if (!isFlat) if (eye[1] > y1) faces.push(["back", [[x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1]]]);
      if (!isFlat) if (eye[0] < x0) faces.push(["left", [[x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1]]]);
      if (!isFlat) if (eye[0] > x1) faces.push(["right", [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]]]);
      faces.push(["top", flat(x0, y0, x1, y1, z1)]);
      const stroke = entry.mode === "invalid" || problem === "error" ? "#a8443d" : "rgba(23,37,45,.45)";
      const screens = faces.map(([side, points]) => ({ side, screen: face(points, DV.tone(color, DV.FACE_TONE[side]), stroke) }));
      ctx.globalAlpha = 1;
      if (DL.isOrdinary(one)) {
        const side = screens.find(({ side, screen }) => side !== "top" &&
          Math.hypot(screen[1][0] - screen[0][0], screen[1][1] - screen[0][1]) > 34 &&
          Math.hypot(screen[3][0] - screen[0][0], screen[3][1] - screen[0][1]) > 14);
        if (side) {
          const points = side.screen;
          ctx.fillStyle = color.ink;
          ctx.font = '700 10px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillText(DL.badgeLabel(one), points.reduce((sum, p) => sum + p[0], 0) / 4,
            points.reduce((sum, p) => sum + p[1], 0) / 4);
        }
      }
      if (problem === "height") {
        ctx.save();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = "#c8741f";
        ctx.lineWidth = 2;
        screens.forEach(({ screen }) => { ctx.beginPath(); screen.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.stroke(); });
        ctx.restore();
      }
      if (pick === layer.key) {
        ctx.strokeStyle = pick === DL.selected ? "#146c70" : "rgba(20,108,112,.6)";
        ctx.lineWidth = pick === DL.selected ? 2.6 : 1.8;
        screens.forEach(({ screen }) => { ctx.beginPath(); screen.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.stroke(); });
      }
      if (!covered.has(layer.key)) {
        const path = [];
        for (let up = layer; up; up = byKey.get(up.parent)) path.unshift(up);
        labels.push({ path, face: screens[screens.length - 1].screen,
          ink: color.light + DV.FACE_TONE.top < 60 ? "#ffffff" : color.ink });
      }
      if (!entry.ghost) {
        hits.push({ key: layer.key, grid: !entry.edge, z: z1, polys: screens.map(s => s.screen) });
      }
      if (DL.isSurface() && !DL.isSpacer(one)) {
        const planTop = z0 + DL.effectiveHeight(one);
        if (!isFlat && planTop > z1 + 0.1) {
          ctx.save();
          ctx.setLineDash([4, 4]);
          ctx.globalAlpha = entry.ghost ? 0.2 : 0.35;
          const tint = "rgba(32,143,150,.14)";
          const outline = "#168b92";
          if (eye[1] < y0) face([[x0, y0, z1], [x1, y0, z1], [x1, y0, planTop], [x0, y0, planTop]], tint, outline);
          if (eye[1] > y1) face([[x1, y1, z1], [x0, y1, z1], [x0, y1, planTop], [x1, y1, planTop]], tint, outline);
          if (eye[0] < x0) face([[x0, y1, z1], [x0, y0, z1], [x0, y0, planTop], [x0, y1, planTop]], tint, outline);
          if (eye[0] > x1) face([[x1, y0, z1], [x1, y1, z1], [x1, y1, planTop], [x1, y0, planTop]], tint, outline);
          face(flat(x0, y0, x1, y1, planTop), tint, outline);
          ctx.restore();
        }
      }
    });
    labels.forEach(({ path, face: topFace, ink }) => DV.drawLabel(ctx, { layers: path }, topFace, ink));
    // Fix 1068: yellow/red rim for under-/over-height bins (Storage Box / Drawer).
    // Fix 1098 (Opus H1, option A): for Storage Drawers the threshold is the
    // safe max — usable drawer height minus 2 mm running clearance, the same
    // hard rule New Bin applies and the Layout report enforces. Storage Box
    // still compares against the raw interior. Red when the stack top exceeds
    // the threshold, yellow for any stack top strictly below it.
    if (!entry.ghost && (DL.isStorageBox() || DL.isStorageDrawers()) &&
        entry.layers.some(layer => !DL.isSpacer(layer.bin))) {
      const interior = DL.isStorageBox() ? Number(DL.layout.space.z) : Number(drawer.height);
      const threshold = interior;
      const stackTop = Math.max(0, ...entry.layers.map(layer => Number(layer.z1) || 0));
      let rim = null;
      if (threshold > 0) {
        if (stackTop > threshold + 1e-6) { rim = "#d43d2f"; DV.stackOverHeight = true; }
        else if (stackTop < threshold - 1e-6) rim = "#e0a100";
      }
      if (rim) {
        // Stack-level footprint: the ACTUAL union perimeter of all layer
        // footprints at the stack-top height (per GPT G2M-0322 — a min/max
        // bounding rectangle is NOT a union and can rim empty area on
        // offset/stepped stacks, so it must not be used here). Coordinate
        // compression over every layer's x/y edges gives an exact
        // rectangular partition of the union; a covered cell edge with no
        // covered neighbor on that side is union perimeter and is stroked
        // as a 3D segment at stackTop. Each layer's rect is inset first,
        // exactly matching how the bins themselves are drawn (layer.x0 +
        // inset, ...), so the rim sits on the drawn top faces.
        const inX0 = layer => layer.x0 + inset, inX1 = layer => layer.x1 - inset;
        const inY0 = layer => layer.y0 + inset, inY1 = layer => layer.y1 - inset;
        const xs = [...new Set(entry.layers.flatMap(layer => [inX0(layer), inX1(layer)]))].sort((a, b) => a - b);
        const ys = [...new Set(entry.layers.flatMap(layer => [inY0(layer), inY1(layer)]))].sort((a, b) => a - b);
        const cellHit = (cx, cy) => entry.layers.some(layer =>
          inX0(layer) <= xs[cx] + 1e-9 && xs[cx + 1] <= inX1(layer) + 1e-9 &&
          inY0(layer) <= ys[cy] + 1e-9 && ys[cy + 1] <= inY1(layer) + 1e-9);
        ctx.save();
        ctx.lineCap = "round";
        const seg = (x0, y0, x1, y1) => face([[x0, y0, stackTop], [x1, y1, stackTop]], null, rim, 3);
        for (let cx = 0; cx < xs.length - 1; cx++) {
          for (let cy = 0; cy < ys.length - 1; cy++) {
            if (!cellHit(cx, cy)) continue;
            if (!cellHit(cx, cy - 1)) seg(xs[cx], ys[cy], xs[cx + 1], ys[cy]);         // front edge (y0 side)
            if (!cellHit(cx, cy + 1)) seg(xs[cx], ys[cy + 1], xs[cx + 1], ys[cy + 1]); // back edge (y1 side)
            if (!cellHit(cx - 1, cy)) seg(xs[cx], ys[cy], xs[cx], ys[cy + 1]);         // left edge (x0 side)
            if (!cellHit(cx + 1, cy)) seg(xs[cx + 1], ys[cy], xs[cx + 1], ys[cy + 1]); // right edge (x1 side)
          }
        }
        ctx.restore();
      }
    }
    if (entry.ex && Object.values(entry.ex).some(Boolean)) {
      // The projecting reach: only where a layer's own envelope goes past the
      // footprint the layers cover.
      const nominal = entry.layers.reduce((box, layer) => ({
        x0: Math.min(box.x0, layer.x0), y0: Math.min(box.y0, layer.y0),
        x1: Math.max(box.x1, layer.x1), y1: Math.max(box.y1, layer.y1),
      }), { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity });
      const reach = {};
      const note = (side, edge, layer, beyond) => {
        if (beyond && (!reach[side] || (side === "l" || side === "t" ? edge < reach[side].edge : edge > reach[side].edge))) {
          reach[side] = { edge, x0: layer.x0, x1: layer.x1, y0: layer.y0, y1: layer.y1 };
        }
      };
      for (const layer of entry.layers) {
        const own = DL.envelopeExt(layer.bin, drawer);
        const l = layer.x0 - own.l * grid.stepX, t = layer.y0 - own.t * grid.stepY;
        const r = layer.x1 + own.r * grid.stepX, b = layer.y1 + own.b * grid.stepY;
        note("l", l, layer, l < nominal.x0 - 1e-6);
        note("t", t, layer, t < nominal.y0 - 1e-6);
        note("r", r, layer, r > nominal.x1 + 1e-6);
        note("b", b, layer, b > nominal.y1 + 1e-6);
      }
      const bands = [];
      if (reach.l) bands.push(flat(reach.l.edge, reach.l.y0, nominal.x0, reach.l.y1, 0.2));
      if (reach.t) bands.push(flat(reach.t.x0, reach.t.edge, reach.t.x1, nominal.y0, 0.2));
      if (reach.r) bands.push(flat(nominal.x1, reach.r.y0, reach.r.edge, reach.r.y1, 0.2));
      if (reach.b) bands.push(flat(reach.b.x0, nominal.y1, reach.b.x1, reach.b.edge, 0.2));
      ctx.save();
      ctx.setLineDash([5, 4]);
      bands.forEach(band => face(band, entry.ghost ? "rgba(196,123,66,.25)" : null, "#c47b42", 1));
      ctx.restore();
    }
  }

  // Walls between you and the drawer, see-through; then every rim.
  walls.filter(wall => !isFlat && !wall.inside).forEach(wall => face(wall.points, "rgba(224,213,192,.3)", "rgba(120,100,70,.45)"));
  ctx.strokeStyle = "rgba(110,90,60,.7)";
  ctx.lineWidth = 1.4;
  face(flat(0, 0, W, D, rimH), null, "rgba(110,90,60,.6)", 1.4);
  ctx.beginPath();
  if (!isFlat) [[0, 0], [W, 0], [0, D], [W, D]].forEach(([x, y]) => line([x, y, 0], [x, y, rimH]));
  ctx.stroke();
  const [fx, fy] = cam.project([W / 2, 0, 0]);
  ctx.fillStyle = "#66757d";
  ctx.font = '700 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText(DL.isSurface()
    ? `FRONT · ${fmt(W)} mm wide · ${fmt(D)} mm deep · ${fmt(drawer.height)} mm edge`
    : `FRONT · ${fmt(W)} mm wide · ${fmt(D)} mm deep · ${fmt(H)} max height`, fx, fy + 10);
  if (DL.isSurface() && DL.fillPlan) {
    DL.fillPlan.forEach(candidate => {
      const selected = DL.fillSelected.has(candidate.id);
      const x = grid.ox + candidate.gx * grid.stepX;
      const y = grid.oy + candidate.gy * grid.stepY;
      ctx.setLineDash(selected ? [] : [4, 4]);
      face(flat(x, y, x + candidate.w * grid.stepX, y + candidate.d * grid.stepY, 0.2),
        selected ? "rgba(37,151,159,.35)" : "rgba(37,151,159,.10)", "#168b92", 2);
      ctx.setLineDash([]);
    });
  }

  return hits;
};

// Unified label info helper for canvas, hover, and selection details.
DV.binLabelInfo = (one, stackCount = 1) => {
  const isEdgeSpacer = one.kind === "spacer" && one.boundary === "edge";
  const rawName = String(one.name || "").trim();
  const name = DL.isSpacer(one) ? "Spacer" : DL.hasName(one) ? rawName : DL.binNumberLabel(one);
  const wMm = fmt(one.x);
  const lMm = fmt(one.y);
  const wUnits = DL.mmToUnits ? DL.mmToUnits(one.x) : fmt(Number(one.x) / DL.UNIT);
  const lUnits = DL.mmToUnits ? DL.mmToUnits(one.y) : fmt(Number(one.y) / DL.UNIT);
  const dimLine = `${wMm} × ${lMm} mm · ${wUnits} × ${lUnits} units`;
  const plan = DL.isSurface() ? DL.rowPlanning(one) : null;
  const heightLine = DL.isSurface()
    ? `${fmt(one.z)} mm print · ${plan?.estimated ? "~" : ""}${fmt(DL.effectiveHeight(one))} mm installed planning`
    : `${fmt(one.z)} mm high`;
  const stackNote = stackCount > 1 ? ` · ${stackCount}-high stack` : "";
  return {
    name,
    dimLine,
    heightLine,
    fullHeightLine: `${heightLine}${stackNote}`,
    detailLine: `${dimLine} · ${heightLine}${stackNote}`,
  };
};

// Story 2920: show every layer's own full size, from bottom to top.
DV.stackSummary = bins => {
  const last = bins.length - 1;
  return {
    heading: "Stacked Bins",
    binLines: bins.map((one, at) =>
      `${fmt(one.x)} × ${fmt(one.y)} × ${fmt(one.z)} mm (${at === 0 ? "Bottom" : at === last ? "Top" : "Middle"})`),
  };
};

// Place a complete icon inside the projected face, including its stroke.
DV.drawStackIcon = (ctx, poly, one, ink) => {
  const { top, bottom } = DL.stackRoles(one);
  if (!top && !bottom) return;
  const size = 16, margin = 1;
  const center = poly.reduce((sum, p) => [sum[0] + p[0] / 4, sum[1] + p[1] / 4], [0, 0]);
  const inside = point => {
    let sign = 0;
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      const cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
      if (Math.abs(cross) < 1e-6) continue;
      if (sign && Math.sign(cross) !== sign) return false;
      sign = Math.sign(cross);
    }
    return sign !== 0;
  };
  let pos = null;
  for (let t = 0.1; t <= 1.001; t += 0.05) {
    const x = poly[3][0] * (1 - t) + center[0] * t - size / 2;
    const y = poly[3][1] * (1 - t) + center[1] * t - size / 2;
    if ([[x-margin,y-margin], [x+size+margin,y-margin], [x+size+margin,y+size+margin], [x-margin,y+size+margin]].every(inside)) { pos = [x, y]; break; }
  }
  if (!pos) return;
  const [x, y] = pos;
  ctx.save();
  ctx.translate(x, y);
  ctx.strokeStyle = ink;
  ctx.lineWidth = 1.2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeRect(5, 4, 8, 3.5);
  ctx.strokeRect(3, 8.5, 8, 3.5);
  ctx.beginPath();
  if (bottom) { ctx.moveTo(8, 3); ctx.lineTo(8, 0.8); ctx.moveTo(6.5, 2.3); ctx.lineTo(8, 0.8); ctx.lineTo(9.5, 2.3); }
  if (top) { ctx.moveTo(8, 13); ctx.lineTo(8, 15.2); ctx.moveTo(6.5, 13.7); ctx.lineTo(8, 15.2); ctx.lineTo(9.5, 13.7); }
  ctx.stroke();
  ctx.restore();
};

// Name, Width × Length, Height on the top of each column; compact when small.
DV.drawLabel = (ctx, entry, topFace, ink) => {
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const [p0, p1, p2, p3] = topFace;           // front-left, front-right, back-right, back-left
  const width = Math.hypot(...mid(p1, p2).map((v, i) => v - mid(p0, p3)[i]));
  const height = Math.hypot(...mid(p3, p2).map((v, i) => v - mid(p0, p1)[i]));
  const [cx, cy] = mid(mid(p0, p2), mid(p1, p3));
  const top = entry.layers[entry.layers.length - 1].bin;
  if (top.kind === "spacer" && top.boundary === "edge") {
    // Every placed spacer carries its "Spacer" label, however thin: the text
    // runs along the block's longer side and shrinks to fit rather than
    // being dropped.
    const along = height > width ? [p3[0] - p0[0], p3[1] - p0[1]] : [p1[0] - p0[0], p1[1] - p0[1]];
    let angle = Math.atan2(along[1], along[0]);
    if (angle > Math.PI / 2) angle -= Math.PI;
    else if (angle <= -Math.PI / 2) angle += Math.PI;
    const long = Math.max(width, height), short = Math.min(width, height);
    const size = Math.max(4, Math.min(14, short * 0.7, long / 3.4));
    ctx.save();
    ctx.fillStyle = ink;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = `650 ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    ctx.translate(cx, cy);
    ctx.rotate(angle);
    ctx.fillText("Spacer", 0, 0);
    ctx.restore();
    return;
  }
  DP.paintPrintMark?.(ctx, top, cx, cy, Math.min(width, height)); // Story 2671: print-mode tick
  DV.drawStackIcon(ctx, topFace, top, ink);
  const stackCount = entry.layers.length;
  if (stackCount > 1) {
    const summary = DV.stackSummary(entry.layers.map(layer => layer.bin));
    const lines = [summary.heading, ...summary.binLines];
    const gap = Math.min(12, height / (lines.length + 1));
    const size = Math.max(7, Math.min(10, gap * 0.85));
    const fitsWidth = lines.every((text, at) => {
      ctx.font = `${at === 0 ? 700 : 500} ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
      return ctx.measureText(text).width <= width - 6;
    });
    if (gap >= 8 && width >= 36 && fitsWidth) {
      ctx.fillStyle = ink;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      lines.forEach((text, at) => {
        ctx.font = `${at === 0 ? 700 : 500} ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
        ctx.fillText(text, cx, cy + (at - (lines.length - 1) / 2) * gap);
      });
      return;
    }
  }
  const info = DV.binLabelInfo(top, stackCount);
  const size = Math.min(13, height * 0.28, width / Math.max(3, info.name.length * 0.55));
  if (size < 6) return;
  ctx.fillStyle = ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";

  const can3Lines = height >= 38 && width >= 50;
  const can2Lines = !can3Lines && height >= 24 && width >= 36;
  if (can3Lines) {
    const subSize = Math.max(7.5, Math.min(10, size * 0.82));
    const lineGap = Math.max(9, size * 0.95);
    ctx.font = `700 ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(DV.fitText(ctx, info.name, width - 6), cx, cy - lineGap);
    ctx.font = `500 ${subSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(DV.fitText(ctx, info.dimLine, width - 6), cx, cy);
    ctx.fillText(DV.fitText(ctx, info.fullHeightLine, width - 6), cx, cy + lineGap);
  } else if (can2Lines) {
    const subSize = Math.max(7, Math.min(9, size * 0.8));
    const lineGap = subSize * 0.65;
    ctx.font = `700 ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(DV.fitText(ctx, info.name, width - 6), cx, cy - lineGap);
    ctx.font = `500 ${subSize}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    const compactDetail = `${fmt(top.x)}×${fmt(top.y)} · ${fmt(top.z)} mm` + (stackCount > 1 ? ` (${stackCount}×)` : "");
    ctx.fillText(DV.fitText(ctx, compactDetail, width - 6), cx, cy + lineGap);
  } else {
    ctx.font = `650 ${size}px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif`;
    ctx.fillText(DV.fitText(ctx, info.name, width - 6), cx, cy);
  }
};

// ------------------------------------------------------------------ picking

DV.inside = ([x, y], points) => {
  let hit = false;
  for (let i = 0, j = points.length - 1; i < points.length; j = i, i += 1) {
    const [xi, yi] = points[i];
    const [xj, yj] = points[j];
    if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
};

DV.hitAt = (sx, sy, skip = null) => {
  for (let index = DV.hits.length - 1; index >= 0; index -= 1) {
    const hit = DV.hits[index];
    if (skip?.has(hit.key)) continue;
    if (hit.polys.some(poly => DV.inside([sx, sy], poly))) return hit;
  }
  return null;
};

DV.point = event => {
  const box = $("#drawer-canvas").getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
};

// Where a moving subtree dropped at this screen point would stand on the
// floor, centred on the pointer.
DV.cellUnder = (moving, sx, sy) => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const { w, d } = moving.nodes[0];
  const point = DV.cam.onPlane(sx, sy, moving.height) || DV.cam.onPlane(sx, sy, 0);
  if (!point) return [-999, -999];
  return [Math.round((point[0] - grid.ox) / grid.stepX - w / 2), Math.round((point[1] - grid.oy) / grid.stepY - d / 2)];
};

// If the pointer is over a support the moving subtree can seat on, that
// support and where on it the subtree would stand. A bin with the support's own
// footprint takes exactly that footprint; a smaller one stands centred on the
// pointer, snapped to the grid. A position that would reach past the support is
// refused, never nudged back inside.
DV.stackTarget = (moving, sx, sy, skip) => {
  const hit = DV.hitAt(sx, sy, skip);
  if (!hit?.grid) return { target: null, refusal: "" };
  const found = DL.layerOf(hit.key);
  if (!found || skip?.has(found.layer.key)) return { target: null, refusal: "" };
  const { item, layer } = found;
  const root = moving.nodes[0];
  let cx = 0, cy = 0;
  if (root.w !== layer.w || root.d !== layer.d) {
    const grid = DL.grid(DL.drawer());
    const point = DV.cam.onPlane(sx, sy, hit.z);
    if (!point) return { target: null, refusal: "" };
    cx = Math.round((point[0] - grid.ox) / grid.stepX - root.w / 2) - layer.gx;
    cy = Math.round((point[1] - grid.oy) / grid.stepY - root.d / 2) - layer.gy;
  }
  const target = { item, layer, cx, cy };
  const fit = DL.fitsOn(DL.drawer(), moving, target, skip);
  return fit.ok ? { target, refusal: "" } : { target: null, refusal: fit.reason };
};

// A valid placement may leave a stacking lid only partly covered.
DV.lidCoverageNotice = (target, moving, movingKeys = new Set()) => {
  if (!target || !DL.lidTakesStack(target.layer.bin)) return "";
  const siblings = target.item.layers.filter(layer => layer.parent === target.layer.key && !movingKeys.has(layer.key));
  if (moving.nodes[0].bin.stack !== "direct" && !siblings.some(layer => layer.bin.stack === "direct")) return "";
  const covered = moving.nodes[0].w * moving.nodes[0].d + siblings.reduce((sum, layer) => sum + layer.w * layer.d, 0);
  return covered < target.layer.w * target.layer.d
    ? `Placed — bins on ${DL.label(target.layer.bin)} must together cover the whole lid. Add bins until no part of the lid is showing.` : "";
};

// ------------------------------------------------------------------ input

DV.wire = () => {
  const canvas = $("#drawer-canvas");
  // Fix 103 (R5): structural Design shows this canvas view-only.
  // Fix 1107 (Astra AD-006): while a cabinet print is in flight the server is
  // generating from the submitted Space and its response replaces the whole
  // layout on adoption (DL.adoptBatchResult) — any placement edit made now
  // would be silently discarded. The canvas is explicitly non-editable until
  // the print finishes (pan/zoom still work); every edit entry point already
  // funnels through readOnly().
  // Story 2671: the workspace shows this canvas beside a bin being edited; it
  // is then view-and-pick only (DP.layoutViewOnly), never a placement editor.
  const readOnly = () => Boolean(DP.structuralReadOnly2D?.()) || Boolean(SP.structuralBusy) || Boolean(DP.layoutViewOnly?.());
  canvas.addEventListener("contextmenu", event => event.preventDefault());
  canvas.addEventListener("pointerdown", event => {
    if (!DL.layout || !DV.cam) return;
    const [sx, sy] = DV.point(event);
    canvas.setPointerCapture(event.pointerId);
    if (readOnly()) {
      // View only: no spacer toggle or bin drag - just pan. The workspace may
      // still pick a bin here (Story 2671).
      const picked = event.button === 0 && DP.onLayoutClick ? DV.hitAt(sx, sy) : null;
      if (picked && DP.onLayoutClick(picked.key)) return;
      const start = DV.cam.onPlane(sx, sy, 0);
      if (start) DV.pan = { cam: DV.cam, start, panX: DV.view.panX, panY: DV.view.panY };
      canvas.classList.add("panning");
      return;
    }
    const hit = event.button === 0 ? DV.hitAt(sx, sy) : null;
    if (hit) {
      DL.selectPlacement(hit.key);
      DV.revealRow(DL.selectedRow);
      // Dragging takes the clicked bin and whatever stands on it - never its
      // siblings or the bin under it.
      const found = hit.grid && DL.layerOf(hit.key);
      const moving = found && DL.movingFor(hit.key);
      const start = DV.cam.onPlane(sx, sy, hit.z);
      if (moving && start) {
        const { gx, gy } = found.layer;
        DV.drag = {
          key: hit.key, keys: moving.keys, bins: moving.bins, moving,
          pointerId: event.pointerId,
          sx, sy, plane: hit.z, start, gx0: gx, gy0: gy, gx, gy, moved: false, valid: true, outside: false,
          target: null,
        };
      }
    } else {
      if (event.button === 0) DL.selectPlacement(null);
      const start = DV.cam.onPlane(sx, sy, 0);
      if (start) DV.pan = { cam: DV.cam, start, panX: DV.view.panX, panY: DV.view.panY,
        sx, sy, moved: false, emptyClick: event.button === 0 };
      canvas.classList.add("panning");
    }
    DL.emit();
  });
  canvas.addEventListener("pointermove", event => {
    const [sx, sy] = DV.point(event);
    if (DV.drag && readOnly()) { DV.drag = null; DV.render(); return; }
    if (DV.drag) {
      const drag = DV.drag;
      if (!drag.moved && Math.hypot(sx - drag.sx, sy - drag.sy) < 4) return;
      const point = DV.cam.onPlane(sx, sy, drag.plane);
      if (!point) return;
      drag.moved = true;
      const grid = DL.grid();
      drag.gx = drag.gx0 + Math.round((point[0] - drag.start[0]) / grid.stepX);
      drag.gy = drag.gy0 + Math.round((point[1] - drag.start[1]) / grid.stepY);
      // Off the drawer means off every bin too, so pointing at a tall stack
      // never counts as throwing a bin away.
      drag.outside = !DV.hitAt(sx, sy, drag.keys)
        && (point[0] < -12 || point[1] < -12 || point[0] > DV.cam.W + 12 || point[1] > DV.cam.D + 12);
      const { target, refusal } = DV.stackTarget(drag.moving, sx, sy, drag.keys);
      drag.target = target;
      if (target) Object.assign(drag, { valid: true, reason: "" });
      else {
        const fit = DL.fitsAt(DL.drawer(), drag.moving, drag.gx, drag.gy, drag.keys);
        Object.assign(drag, { valid: fit.ok, reason: fit.ok ? "" : refusal || fit.reason });
      }
      drag.overTree = DV.overTree(event);
      canvas.style.cursor = drag.outside && !drag.overTree ? "no-drop" : "grabbing";
      DV.paint();
    } else if (DV.pan) {
      if (Math.hypot(sx - DV.pan.sx, sy - DV.pan.sy) >= 4) DV.pan.moved = true;
      const point = DV.pan.cam.onPlane(sx, sy, 0);
      if (!point) return;
      DV.view.panX = DV.pan.panX - (point[0] - DV.pan.start[0]);
      DV.view.panY = DV.pan.panY - (point[1] - DV.pan.start[1]);
      DV.clampPan(DL.drawer());
      DV.paint();
    } else {
      const hit = DV.hitAt(sx, sy);
      const key = hit?.key || null;
      canvas.style.cursor = hit ? (hit.grid ? "grab" : "pointer") : "";
      if (key !== DV.hover) {
        DV.hover = key;
        const found = key && DL.findPlacement(key);
        const one = found && DL.bin(found.placement.bin);
        const standing = found ? DL.layerOf(key, found.drawer) : null;
        const levels = standing ? Math.max(...standing.item.layers.map(layer => layer.depth)) + 1 : 1;
        const info = one ? DV.binLabelInfo(one, levels) : null;
        if (standing && standing.item.layers.length > 1) {
          const summary = DV.stackSummary(standing.item.layers.map(layer => layer.bin));
          canvas.title = [summary.heading, ...summary.binLines].join("\n");
        } else canvas.title = info ? `${info.name} — ${info.detailLine}` : "";
        DV.paint();
      }
    }
  });
  const finish = event => {
    if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    canvas.classList.remove("panning");
    canvas.style.cursor = "";
    const drag = DV.drag;
    const pan = DV.pan;
    DV.drag = null;
    DV.pan = null;
    if (event.type === "pointerup" && pan?.emptyClick && !pan.moved && !readOnly() &&
        typeof WS !== "undefined" && WS.task === "peek") WS.go("settings");
    if (drag && !drag.moved && !readOnly()) DP.onLayoutClick?.(drag.key); // Story 2671: a click, not a drag
    if (drag?.moved && !readOnly()) {
      if (DV.overTree(event)) {
        const count = DL.takeOut(drag.key);
        // The bin visibly moves into the Not placed tree group.
      } else if (drag.outside) {
        // Released off the Space but not on the tree: nothing changes.
      } else if (drag.target) {
        const notice = DV.lidCoverageNotice(drag.target, drag.moving, drag.keys);
        dismissToast();
        DL.moveTo(drag.key, { target: drag.target });
        if (notice) toastAt(notice, event.clientX, event.clientY);
      } else if (drag.valid) {
        dismissToast();
        DL.moveTo(drag.key, { gx: drag.gx, gy: drag.gy });
      } else {
        toastAt(drag.reason || "It does not fit there.", event.clientX, event.clientY, true);
      }
    }
    DV.render();
  };
  canvas.addEventListener("pointerup", finish);
  canvas.addEventListener("pointercancel", finish);
  canvas.addEventListener("pointerleave", () => { if (DV.hover && !DV.drag) { DV.hover = null; DV.render(); } });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    const [sx, sy] = DV.point(event);
    DV.zoomBy(event.deltaY < 0 ? 1.12 : 1 / 1.12, sx, sy);
  }, { passive: false });
  canvas.addEventListener("dblclick", event => {
    const [sx, sy] = DV.point(event);
    if (!DV.hitAt(sx, sy)) DV.fit();
  });

  // Dropping a bin dragged from the tree: onto the floor, or onto a
  // stack it can snap onto.
  canvas.addEventListener("dragover", event => {
    if (readOnly() || !DV.dragBin || !DV.cam) return;
    event.preventDefault();
    const [sx, sy] = DV.point(event);
    const moving = DL.movingForBins([DV.dragBin]);
    const [gx, gy] = DV.cellUnder(moving, sx, sy);
    const { target, refusal } = DV.stackTarget(moving, sx, sy, null);
    const fit = target ? { ok: true } : DL.fitsAt(DL.drawer(), moving, gx, gy);
    const next = { bin: DV.dragBin, moving, gx, gy, target, valid: fit.ok, reason: fit.ok ? "" : refusal || fit.reason };
    const spot = one => one ? `${one.layer.key}@${one.cx},${one.cy}` : "";
    if (DV.drop?.gx !== next.gx || DV.drop?.gy !== next.gy || spot(DV.drop?.target) !== spot(next.target)) {
      DV.drop = next;
      DV.paint();
    }
  });
  canvas.addEventListener("dragleave", () => { DV.drop = null; DV.render(); });
  canvas.addEventListener("drop", event => {
    event.preventDefault();
    const drop = DV.drop;
    DV.drop = null;
    if (drop && !readOnly()) {
      if (DL.isOrdinary(drop.bin) && DL.isPlaced(drop.bin.id)) {
        DL.placeAt(drop.bin, {});
      } else if (!drop.valid) toastAt(drop.reason || "It does not fit there.", event.clientX, event.clientY, true);
      else {
        const notice = DV.lidCoverageNotice(drop.target, drop.moving);
        dismissToast();
        if (DL.placeAt(drop.bin, drop.target ? { target: drop.target } : { gx: drop.gx, gy: drop.gy }) && notice)
          toastAt(notice, event.clientX, event.clientY);
      }
    }
    DV.render();
  });

  const resized = new ResizeObserver(() => DV.render());
  resized.observe(canvas.parentElement);
  resized.observe(canvas);

  // Keys while the drawer is on screen. Capture phase, so the bin editor's
  // own shortcuts (arrow nudges) never act on the hidden design.
  window.addEventListener("keydown", event => {
    if (!DP.spaceEditing() || !DL.layout || readOnly()) return;
    if (document.querySelector("dialog[open]")) return;
    if (event.key === "Escape" && !DV.drag && typeof WS !== "undefined" && WS.task === "peek") {
      event.preventDefault();
      event.stopImmediatePropagation();
      WS.go("settings");
      return;
    }
    if (event.target.closest?.("input, textarea, select, [contenteditable='true']")) return;
    if (event.key === "Escape" && DV.drag) {
      const pointerId = DV.drag.pointerId;
      DV.drag = null;
      DV.dragBin = null;
      if (Number.isInteger(pointerId) && canvas.hasPointerCapture?.(pointerId)) {
        canvas.releasePointerCapture(pointerId);
      }
      canvas.classList.remove("panning");
      canvas.style.cursor = "";
      event.preventDefault();
      event.stopImmediatePropagation();
      DV.render();
      return;
    }
    const key = event.key.toLowerCase();
    const mod = event.ctrlKey || event.metaKey;
    const standing = DL.selected && DL.layerOf(DL.selected);
    const moves = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, 1], arrowdown: [0, -1] };
    let handled = true;
    if (mod && key === "s") DL.save();
    else if (mod || event.altKey) handled = false;
    else if (moves[key] && standing) {
      // Arrows nudge the selected bin and what stands on it one cell: on the
      // floor for a floor bin, within its support for a stacked one.
      const drawer = DL.drawer();
      const [dx, dy] = moves[key];
      const { item, layer } = standing;
      const moving = DL.movingFor(layer.key);
      const support = layer.parent && item.layers.find(one => one.key === layer.parent);
      if (support) {
        const target = { item, layer: support, cx: layer.gx - support.gx + dx, cy: layer.gy - support.gy + dy };
        const fit = DL.fitsOn(drawer, moving, target);
        if (fit.ok) DL.moveTo(layer.key, { target }); else toast(fit.reason, true);
      } else {
        const gx = layer.gx + dx, gy = layer.gy + dy;
        const fit = DL.fitsAt(drawer, moving, gx, gy, moving.keys);
        if (fit.ok) DL.moveTo(layer.key, { gx, gy }); else toast(fit.reason, true);
      }
    } else if ((key === "delete" || key === "backspace") && DL.selected) DL.removePlacement(DL.selected);
    else if (key === "escape") DL.selectPlacement(null);
    else if (key === "f") DV.fit();
    else handled = false;
    if (handled) {
      event.preventDefault();
      event.stopImmediatePropagation();
      DL.emit();
    }
  }, true);

};

// Pointer capture keeps the canvas drag alive while the pointer is over the tree.
DV.overTree = event => {
  const over = document.elementFromPoint(event.clientX, event.clientY);
  return Boolean(over?.closest?.("#ws-stage"));
};

// Story 2751: in a Storage Drawers space, picking an unplaced bin in the list
// sets its design height to exactly the viewed drawer's safe height (inside
// height minus the 2 mm running clearance - the same cap the height rim and
// the Layout report judge against), so it fits top to bottom. It is a normal
// design-source edit, saved the way every bin edit is saved.
DV.fitStagedBinHeight = async id => {
  if (!DL.isStorageDrawers() || !DL.layout) return;
  const drawer = DL.drawer();
  const spec = DL.layout.design_specs?.[id];
  const target = Number(drawer?.height);
  if (!spec?.box || !DL.bin(id) || !DL.isOrdinary(DL.bin(id)) || !(target > 0)) return;
  if (Math.abs(Number(spec.box.z) - target) < 1e-9) return;
  const context = DL.spaceContext();
  const design = clone(spec);
  design.box.z = target;
  try {
    const data = await DL.inventoryCall("/api/drawer/design-source/save", { design, row_id: id },
      { context, sideEffect: true });
    DL.requireSpaceContext(context);
    DL.adopt(data);
    if (state.designInventoryId === id && state.design?.box) {
      state.design.box.z = target;
      if (state.cleanDesign?.box) state.cleanDesign.box.z = target;
    }
    DL.emit();
    DL.requestReport();
  } catch (error) {
    if (!DL.isStaleSpaceError(error)) toast(friendlyError(error), true, 6000);
  }
};

// Scroll the tree row for `id` into view (canvas -> tree).
DV.revealRow = id => {
  if (!id) return;
  const row = document.querySelector(`#ws-stage [data-ws-pick="bin"][data-id="${CSS.escape(id)}"]`);
  if (row && row.scrollIntoView) row.scrollIntoView({ block: "nearest" });
};

DV.buildOverlay = () => {
  const wrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (!wrap || $("#dl-tilt")) return;
  wrap.insertAdjacentHTML("beforeend", `
    <div class="camera-controls dl-view-controls" aria-label="Space camera">
      <div class="camera-controls-row">
        <div class="camera-views"><div class="camera-views-row">
          <button type="button" data-dl-view="look" title="Looking in from the front of this Space">Look in</button>
          <button type="button" data-dl-view="overhead" title="Straight down, flat like a 2D plan (angle controls are off)">Overhead</button>
          <button type="button" data-dl-view="low" title="Low view from the front of this Space - shows what hides behind what">Low</button>
          <button type="button" data-dl-view="fit" title="Frame the whole Space again (F)">Fit</button>
        </div></div>
        <div class="zoom-controls">
          <button type="button" data-dl-zoom="out" aria-label="Zoom out">−</button>
          <button type="button" data-dl-zoom="in" aria-label="Zoom in">+</button>
        </div>
      </div>
      <div class="camera-controls-row">
        <label class="canvas-select dl-tilt-control" title="How steeply you look down into the Space">Angle <input id="dl-tilt" type="range" min="${DV.LIMITS.tilt[0]}" max="${DV.LIMITS.tilt[1]}" step="1"></label>
        <label class="canvas-select dl-tilt-control" title="Move the viewpoint left or right around the Space">Turn <input id="dl-turn" type="range" min="${DV.LIMITS.turn[0]}" max="${DV.LIMITS.turn[1]}" step="1"></label>
      </div>
    </div>
    <div id="sd-workspace-host" class="sd-workspace-host" hidden></div>
    <div id="dl-empty-hint" class="dl-empty-hint" hidden><strong>Drag bins to place</strong><span>Drag onto a bin to stack</span></div>
    <div class="layout-hint dl-hint">Drag bins to move · drop on a compatible bin to stack (smaller bins on a Lid for stacking must together cover the whole lid) · drag a bin onto the tree to unplace · drag the floor to pan · wheel zooms · Del unplaces</div>
    <div id="dl-layout-action-note" class="layout-hint" role="status" hidden></div>
    <div class="layout-hint dl-color-key" id="dl-color-key"></div>
    <div class="layout-hint dl-height-legend" id="dl-height-legend" hidden></div>`);
  $$("[data-dl-view]").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.dlView === "fit") DV.fit(); else DV.setView(DV.PRESETS[button.dataset.dlView]);
  }));
  $$("[data-dl-zoom]").forEach(button => button.addEventListener("click",
    () => DV.zoomBy(button.dataset.dlZoom === "in" ? 1.2 : 1 / 1.2)));
  $("#dl-tilt").addEventListener("input", event => DV.setView({ tilt: event.target.value }));
  $("#dl-turn").addEventListener("input", event => DV.setView({ turn: event.target.value }));
  DV.syncControls();
};
