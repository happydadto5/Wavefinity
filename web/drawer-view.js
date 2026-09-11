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
  view: { tilt: 48, turn: 0, zoom: 1, panX: 0, panY: 0 },
  LIMITS: { tilt: [22, 86], turn: [-30, 30], zoom: [0.5, 6] },
  PRESETS: { look: { tilt: 48, turn: 0 }, overhead: { tilt: 86, turn: 0 }, low: { tilt: 26, turn: 0 } },
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
  try { localStorage.setItem("wavefinity-drawer-camera", JSON.stringify({ tilt: DV.view.tilt, turn: DV.view.turn })); } catch (_error) {}
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
  if (tilt) tilt.value = String(Math.round(DV.view.tilt));
  if (turn) turn.value = String(Math.round(DV.view.turn));
  $$("[data-dl-view]").forEach(button => {
    const preset = DV.PRESETS[button.dataset.dlView];
    button.classList.toggle("active", Boolean(preset)
      && Math.round(DV.view.tilt) === preset.tilt && Math.round(DV.view.turn) === preset.turn);
  });
};

DV.setView = ({ tilt = DV.view.tilt, turn = DV.view.turn } = {}) => {
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
  const before = sx === null ? null : DV.camera(width, height, drawer).onPlane(sx, sy, 0);
  DV.view.zoom = dvClamp(DV.view.zoom * factor, DV.LIMITS.zoom);
  if (before) {
    const after = DV.camera(width, height, drawer).onPlane(sx, sy, 0);
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
DV.camera = (width, height, drawer, view = DV.view) => {
  const W = drawer.width;
  const D = drawer.depth;
  const H = drawer.height;
  const tilt = view.tilt * Math.PI / 180;
  const turn = view.turn * Math.PI / 180;
  const away = [Math.sin(turn) * Math.cos(tilt), -Math.cos(turn) * Math.cos(tilt), Math.sin(tilt)];
  const focal = (height / 2) / Math.tan(17 * Math.PI / 180);   // a 34° field of view
  const margin = 36;
  const footer = 30;
  const halfW = Math.max(40, width / 2 - margin);
  const halfH = Math.max(40, (height - footer) / 2 - margin);
  const cx = width / 2;
  const cy = (height - footer) / 2;
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
  const b = basis(target, Math.max(fit / view.zoom, lowest));
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
  return { W, D, H, eye: b.eye, project, onPlane };
};

// ------------------------------------------------------------------ colour

DV.heightRange = () => {
  const heights = DL.bins.filter(one => !DL.isSpacer(one)).map(one => Number(one.z));
  return heights.length ? [Math.min(...heights), Math.max(...heights)] : [0, 1];
};

// Short bins light, tall bins dark, so height order reads at a glance. `top`,
// `front` and `ink` stay plain colour strings for the panel's swatches.
DV.binColor = (one, range) => {
  let hue, sat, light;
  if (one.kind === "spacer") [hue, sat, light] = [43, 20, 82];
  else if (one.kind === "shim") [hue, sat, light] = [42, 28, 72];
  else {
    const t = range[1] > range[0] ? (one.z - range[0]) / (range[1] - range[0]) : 0.5;
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
    const tone = problem.type === "height" ? "height" : "error";
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

// Layers (bottom first) for bins standing on a stack or on the floor.
DV.layersFor = (bins, keys, start) => {
  let top = 0;
  return bins.map((one, index) => {
    const bottom = index ? top - (DL.stackSteps[one.stack] ?? 0) : start;
    top = bottom + Number(one.z);
    return { bin: one, key: keys[index], z0: bottom, z1: top };
  });
};

// Everything standing in the drawer, as columns of boxes, with a drag or
// drop shown where it would land.
DV.entries = (drawer, grid) => {
  const step = grid.step;
  const box = (gx, gy, w, d) => ({ x0: grid.ox + gx * step, y0: grid.oy + gy * step, x1: grid.ox + (gx + w) * step, y1: grid.oy + (gy + d) * step });
  const entries = [];
  const drag = DV.drag?.moved ? DV.drag : null;
  for (const item of DL.items(drawer)) {
    const layers = item.layers.filter(layer => !drag?.keys.has(layer.key));
    if (layers.length) entries.push({ key: item.key, item, ...box(item.gx, item.gy, item.w, item.d), layers, mode: "" });
  }
  for (const p of drawer.placements.filter(DL.isShim)) {
    const one = DL.bin(p.bin);
    if (one) entries.push({ key: DL.key(p), x0: p.x, y0: p.y, x1: p.x + p.w, y1: p.y + p.d, layers: [{ bin: one, key: DL.key(p), z0: 0, z1: Number(one.z) }], mode: "", shim: true });
  }
  const ghost = drag || DV.drop;
  if (ghost) {
    const bins = drag ? drag.bins : [DV.drop.bin];
    const keys = drag ? [...drag.keys] : ["__drop"];
    const [w, d] = DL.cells(bins[0], drawer);
    const target = ghost.target;
    const start = target ? target.h - (DL.stackSteps[bins[0].stack] ?? 0) : 0;
    const where = target ? box(target.gx, target.gy, target.w, target.d) : box(ghost.gx, ghost.gy, w, d);
    const mode = drag?.outside ? "leaving" : ghost.valid ? "ghost" : "invalid";
    entries.push({ key: "__ghost", ...where, layers: DV.layersFor(bins, keys, start), mode, ghost: true });
  }
  return entries;
};

// Which of two columns to paint first. Footprints never overlap, so a plane
// between them always exists; the column on the far side of that plane from
// the camera cannot hide the other one, so it is painted first.
DV.fartherFirst = (a, b, eye) => {
  if (a.x1 <= b.x0 + 1e-6) return eye[0] > a.x1;
  if (b.x1 <= a.x0 + 1e-6) return eye[0] < a.x0;
  if (a.y1 <= b.y0 + 1e-6) return eye[1] > a.y1;
  if (b.y1 <= a.y0 + 1e-6) return eye[1] < a.y0;
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
  const dpr = window.devicePixelRatio || 1;
  const pixelW = Math.round(box.width * dpr);
  const pixelH = Math.round(box.height * dpr);
  if (canvas.width !== pixelW || canvas.height !== pixelH) { canvas.width = pixelW; canvas.height = pixelH; }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, box.width, box.height);
  const drawer = DL.drawer();
  DV.cam = DV.camera(box.width, box.height, drawer);
  DV.hits = DV.paintScene(ctx, drawer, DV.cam);
  DV.renderSelection();
};

DV.paintScene = (ctx, drawer, cam) => {
  const grid = DL.grid(drawer);
  const step = grid.step;
  const { W, D, H, eye } = cam;
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
    { inside: eye[1] < D, points: [[0, D, 0], [W, D, 0], [W, D, H], [0, D, H]], tone: "#e2d7c2" },
    { inside: eye[0] > 0, points: [[0, 0, 0], [0, D, 0], [0, D, H], [0, 0, H]], tone: "#dcd1bb" },
    { inside: eye[0] < W, points: [[W, 0, 0], [W, D, 0], [W, D, H], [W, 0, H]], tone: "#d9cdb6" },
    { inside: eye[1] > 0, points: [[0, 0, 0], [W, 0, 0], [W, 0, H], [0, 0, H]], tone: "#e0d5c0" },
  ];

  // The drawer: floor, then the inside faces of the walls you can see.
  face(flat(0, 0, W, D), "#f1ebdf", "rgba(120,100,70,.5)", 1.2);
  walls.filter(wall => wall.inside).forEach(wall => face(wall.points, wall.tone, "rgba(120,100,70,.35)"));

  // On the floor: the strips the grid cannot use, grid lines, keep-outs.
  const gx1 = grid.ox + grid.cols * step;
  const gy1 = grid.oy + grid.rows * step;
  const hatch = DV.hatch(ctx, "rgba(150,130,95,.35)");
  [[0, 0, grid.ox, D], [gx1, 0, W, D], [grid.ox, 0, gx1, grid.oy], [grid.ox, gy1, gx1, D]]
    .forEach(([x0, y0, x1, y1]) => { if (x1 - x0 > 0.05 && y1 - y0 > 0.05) face(flat(x0, y0, x1, y1), hatch); });
  const line = (a, b) => { const [ax, ay] = cam.project(a); const [bx, by] = cam.project(b); ctx.moveTo(ax, ay); ctx.lineTo(bx, by); };
  ctx.lineWidth = 1;
  for (const [every, tone] of [[step, "rgba(120,100,70,.10)"], [DL.UNIT, "rgba(120,100,70,.2)"]]) {
    if (every === step && step === DL.UNIT) continue;
    ctx.strokeStyle = tone;
    ctx.beginPath();
    for (let x = 0; x <= grid.cols * step + 1e-6; x += every) line([grid.ox + x, grid.oy, 0], [grid.ox + x, gy1, 0]);
    for (let y = 0; y <= grid.rows * step + 1e-6; y += every) line([grid.ox, grid.oy + y, 0], [gx1, grid.oy + y, 0]);
    ctx.stroke();
  }
  const keepHatch = DV.hatch(ctx, "rgba(168,68,61,.55)");
  (drawer.keepouts || []).forEach(zone => face(flat(zone.x, zone.y, zone.x + zone.w, zone.y + zone.d), keepHatch, "rgba(168,68,61,.7)"));

  // Empty cells, and the largest empty spot the report found.
  if (DL.layout.settings.show_empty) {
    const taken = DL.blockedCells(drawer, grid);
    DL.items(drawer).forEach(item => {
      for (let r = item.gy; r < item.gy + item.d; r += 1) for (let c = item.gx; c < item.gx + item.w; c += 1) taken.add(`${c},${r}`);
    });
    const inset = Math.min(0.6, step / 10);
    ctx.fillStyle = "rgba(47,150,110,.14)";
    for (let r = 0; r < grid.rows; r += 1) for (let c = 0; c < grid.cols; c += 1) {
      if (taken.has(`${c},${r}`)) continue;
      shape(flat(grid.ox + c * step + inset, grid.oy + r * step + inset, grid.ox + (c + 1) * step - inset, grid.oy + (r + 1) * step - inset));
      ctx.fill();
    }
    const spot = DL.report?.largest;
    if (spot && !DV.drag && DL.report.grid?.step === step) {
      const x0 = grid.ox + spot.gx * step, y0 = grid.oy + spot.gy * step;
      const x1 = grid.ox + (spot.gx + spot.w) * step, y1 = grid.oy + (spot.gy + spot.d) * step;
      ctx.save();
      ctx.setLineDash([5, 4]);
      face(flat(x0, y0, x1, y1), null, "rgba(31,107,69,.8)", 1.5);
      ctx.restore();
      const [ax] = cam.project([x0, (y0 + y1) / 2, 0]);
      const [bx] = cam.project([x1, (y0 + y1) / 2, 0]);
      const [mx, my] = cam.project([(x0 + x1) / 2, (y0 + y1) / 2, 0]);
      if (Math.abs(bx - ax) > 70) {
        ctx.fillStyle = "rgba(31,107,69,.9)";
        ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${fmt(spot.w_mm)} × ${fmt(spot.d_mm)} free`, mx, my);
      }
    }
  }

  // Bins, far columns first; within a column, layers bottom to top.
  const range = DV.heightRange();
  const problems = DV.problemKeys();
  const hits = [];
  const inset = 0.35;
  for (const entry of DV.paintOrder(DV.entries(drawer, grid), eye)) {
    const x0 = entry.x0 + inset, x1 = entry.x1 - inset, y0 = entry.y0 + inset, y1 = entry.y1 - inset;
    const keys = entry.layers.map(layer => layer.key);
    const pick = entry.ghost ? null
      : DL.selected && keys.includes(DL.selected) ? DL.selected
        : DV.hover && keys.includes(DV.hover) ? DV.hover : null;
    let topFace = null;
    let topInk = "#17252d";
    let topPlanned = false;
    entry.layers.forEach((layer, index) => {
      const one = layer.bin;
      const { z0, z1 } = layer;
      const planned = !entry.ghost && DL.isPlanned({ bin: one.id, copy: Number(layer.key.split(":")[1]) });
      const problem = problems.get(layer.key);
      let color = DV.binColor(one, range);
      if (entry.mode === "invalid" || problem === "error") color = { ...color, hue: 5, sat: 62, light: 83, ink: "#5e1f1b" };
      ctx.globalAlpha = entry.mode === "leaving" ? 0.35 : entry.mode === "ghost" ? 0.78 : planned ? 0.55 : 1;
      const faces = [];
      if (eye[1] < y0) faces.push(["front", [[x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1]]]);
      if (eye[1] > y1) faces.push(["back", [[x1, y1, z0], [x0, y1, z0], [x0, y1, z1], [x1, y1, z1]]]);
      if (eye[0] < x0) faces.push(["left", [[x0, y1, z0], [x0, y0, z0], [x0, y0, z1], [x0, y1, z1]]]);
      if (eye[0] > x1) faces.push(["right", [[x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]]]);
      faces.push(["top", flat(x0, y0, x1, y1, z1)]);
      const stroke = entry.mode === "invalid" || problem === "error" ? "#a8443d" : "rgba(23,37,45,.45)";
      const screens = faces.map(([side, points]) => ({ side, screen: face(points, DV.tone(color, DV.FACE_TONE[side]), stroke) }));
      ctx.globalAlpha = 1;
      if (planned || problem === "height") {
        ctx.save();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = planned ? "#146c70" : "#c8741f";
        ctx.lineWidth = planned ? 1.5 : 2;
        screens.forEach(({ screen }) => { ctx.beginPath(); screen.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.stroke(); });
        ctx.restore();
      }
      if (pick === layer.key) {
        ctx.strokeStyle = pick === DL.selected ? "#146c70" : "rgba(20,108,112,.6)";
        ctx.lineWidth = pick === DL.selected ? 2.6 : 1.8;
        screens.forEach(({ screen }) => { ctx.beginPath(); screen.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath(); ctx.stroke(); });
      }
      if (index === entry.layers.length - 1) {
        topFace = screens[screens.length - 1].screen;
        topInk = color.light + DV.FACE_TONE.top < 60 ? "#ffffff" : color.ink;
        topPlanned = planned;
      }
      if (!entry.ghost) hits.push({ key: layer.key, grid: !entry.shim, z: z1, polys: screens.map(s => s.screen) });
    });
    if (topFace) DV.drawLabel(ctx, entry, topFace, topInk, topPlanned);
    const base = entry.item?.chain[0];
    if (base?.locked && topFace) {
      const [lx, ly] = topFace[3];
      ctx.font = "10px 'Segoe UI Emoji', sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("🔒", lx + 3, ly + 2);
    }
  }

  // Walls between you and the drawer, see-through; then every rim.
  walls.filter(wall => !wall.inside).forEach(wall => face(wall.points, "rgba(224,213,192,.3)", "rgba(120,100,70,.45)"));
  ctx.strokeStyle = "rgba(110,90,60,.7)";
  ctx.lineWidth = 1.4;
  face(flat(0, 0, W, D, H), null, "rgba(110,90,60,.6)", 1.4);
  ctx.beginPath();
  [[0, 0], [W, 0], [0, D], [W, D]].forEach(([x, y]) => line([x, y, 0], [x, y, H]));
  ctx.stroke();
  const [fx, fy] = cam.project([W / 2, 0, 0]);
  ctx.fillStyle = "#66757d";
  ctx.font = "700 11px 'Segoe UI', system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText(`FRONT · ${fmt(W)} mm wide · ${fmt(D)} deep · ${fmt(H)} max height`, fx, fy + 10);
  return hits;
};

// Name (or size) on the top of each column; a second line when there is room.
DV.drawLabel = (ctx, entry, topFace, ink, planned) => {
  const mid = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
  const [p0, p1, p2, p3] = topFace;           // front-left, front-right, back-right, back-left
  const width = Math.hypot(...mid(p1, p2).map((v, i) => v - mid(p0, p3)[i]));
  const height = Math.hypot(...mid(p3, p2).map((v, i) => v - mid(p0, p1)[i]));
  const [cx, cy] = mid(mid(p0, p2), mid(p1, p3));
  const top = entry.layers[entry.layers.length - 1].bin;
  const primary = top.kind === "shim" ? "Shim" : DL.label(top);
  const size = Math.min(14, height * 0.36, width / Math.max(3, primary.length * 0.56));
  if (size < 7) return;
  ctx.fillStyle = planned ? "#0d5356" : ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `650 ${size}px 'Segoe UI', system-ui, sans-serif`;
  const twoLines = height > size * 2.7 && top.kind !== "shim";
  const y = cy - (twoLines ? size * 0.45 : 0);
  ctx.fillText(DV.fitText(ctx, primary, width - 6), cx, y);
  if (twoLines) {
    const small = Math.max(7, size * 0.78);
    ctx.font = `500 ${small}px 'Segoe UI', system-ui, sans-serif`;
    const stackHeight = entry.layers[entry.layers.length - 1].z1;
    const detail = entry.layers.length > 1
      ? `${entry.layers.length}-high stack · ${fmt(stackHeight)} tall`
      : planned ? `planned · ${fmt(top.z)} tall`
        : top.name ? `${fmt(top.x)}×${fmt(top.y)} · ${fmt(top.z)} tall` : `${fmt(top.z)} mm tall`;
    ctx.fillText(DV.fitText(ctx, detail, width - 6), cx, y + size * 1.05);
  }
};

DV.renderSelection = () => {
  const card = $("#dl-selection");
  if (!card) return;
  const found = DL.selected && DL.findPlacement(DL.selected);
  const one = found && DL.bin(found.placement.bin);
  card.hidden = !one;
  if (!one) return;
  const p = found.placement;
  const copies = Number(one.qty) || 0;
  const planned = DL.isPlanned(p);
  const chain = DL.stackOf(DL.selected, found.drawer);
  const where = chain && chain.length > 1 ? ` · ${chain.findIndex(q => q === p) + 1} of ${chain.length} in a stack` : "";
  card.innerHTML = `
    <strong>${escapeHtml(DL.label(one))}</strong>
    <span>${escapeHtml(DL.sizeText(one))}${!planned && copies > 1 ? ` · copy ${(p.copy ?? 0) + 1} of ${copies}` : ""}</span>
    <span>${escapeHtml(DL.stackName(one.stack))}${where}</span>
    ${planned ? `<span class="dl-planned-note">Planned - not printed yet</span>` : ""}
    ${found.drawer !== DL.drawer() ? `<span>In ${escapeHtml(found.drawer.name)}</span>` : ""}
    <div class="dl-selection-actions">
      ${planned ? `<button type="button" data-sel="printed" title="You have printed this one">Mark printed</button>` : ""}
      ${chain ? `<button type="button" data-sel="lock" title="Locked stacks stay put when you drag or run Auto layout (L)">${chain[0].locked ? "Unlock" : "Lock"}</button>` : ""}
      <button type="button" data-sel="remove" title="Take it out of the drawer (Delete)">Take out</button>
    </div>`;
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

// Where bins dropped at this screen point would stand, centred on the pointer.
DV.cellUnder = (bins, sx, sy) => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const [w, d] = DL.cells(bins[0], drawer);
  const point = DV.cam.onPlane(sx, sy, DL.stackHeight(bins)) || DV.cam.onPlane(sx, sy, 0);
  if (!point) return [-999, -999];
  return [Math.round((point[0] - grid.ox) / grid.step - w / 2), Math.round((point[1] - grid.oy) / grid.step - d / 2)];
};

// If the pointer is over a stack these bins can snap onto, that stack. The
// sides snap: the bins take the stack's exact footprint.
DV.stackTarget = (bins, sx, sy, skip) => {
  const hit = DV.hitAt(sx, sy, skip);
  if (!hit?.grid) return { target: null, refusal: "" };
  const item = DL.items().find(one => one.keys.includes(hit.key));
  if (!item || item.keys.some(key => skip?.has(key))) return { target: null, refusal: "" };
  const fit = DL.fitsOn(DL.drawer(), bins, item);
  return fit.ok ? { target: item, refusal: "" } : { target: null, refusal: fit.reason };
};

// ------------------------------------------------------------------ input

DV.wire = () => {
  const canvas = $("#drawer-canvas");
  canvas.addEventListener("contextmenu", event => event.preventDefault());
  canvas.addEventListener("pointerdown", event => {
    if (!DL.layout || !DV.cam) return;
    const [sx, sy] = DV.point(event);
    canvas.setPointerCapture(event.pointerId);
    const hit = event.button === 0 ? DV.hitAt(sx, sy) : null;
    if (hit) {
      DL.selected = hit.key;
      const chain = hit.grid && DL.stackOf(hit.key);
      const start = DV.cam.onPlane(sx, sy, hit.z);
      if (chain && start) {
        const moving = chain.slice(chain.findIndex(p => DL.key(p) === hit.key));
        const drawer = DL.drawer();
        const gx = DL.toCell(chain[0].gx, drawer);
        const gy = DL.toCell(chain[0].gy, drawer);
        DV.drag = {
          key: hit.key, keys: new Set(moving.map(DL.key)), bins: moving.map(p => DL.bin(p.bin)),
          sx, sy, plane: hit.z, start, gx0: gx, gy0: gy, gx, gy, moved: false, valid: true, outside: false,
          target: null, locked: Boolean(chain[0].locked),
        };
      }
    } else {
      if (event.button === 0) DL.selected = null;
      const start = DV.cam.onPlane(sx, sy, 0);
      if (start) DV.pan = { cam: DV.cam, start, panX: DV.view.panX, panY: DV.view.panY };
      canvas.classList.add("panning");
    }
    DL.emit();
  });
  canvas.addEventListener("pointermove", event => {
    const [sx, sy] = DV.point(event);
    if (DV.drag) {
      const drag = DV.drag;
      if (!drag.moved && Math.hypot(sx - drag.sx, sy - drag.sy) < 4) return;
      if (drag.locked) {
        if (!drag.warned) { toast("This stack is locked. Unlock it (L) to move it."); drag.warned = true; }
        return;
      }
      const point = DV.cam.onPlane(sx, sy, drag.plane);
      if (!point) return;
      drag.moved = true;
      const step = DL.grid().step;
      drag.gx = drag.gx0 + Math.round((point[0] - drag.start[0]) / step);
      drag.gy = drag.gy0 + Math.round((point[1] - drag.start[1]) / step);
      // Off the drawer means off every bin too, so pointing at a tall stack
      // never counts as throwing a bin away.
      drag.outside = !DV.hitAt(sx, sy, drag.keys)
        && (point[0] < -12 || point[1] < -12 || point[0] > DV.cam.W + 12 || point[1] > DV.cam.D + 12);
      const { target, refusal } = DV.stackTarget(drag.bins, sx, sy, drag.keys);
      drag.target = target;
      if (target) Object.assign(drag, { valid: true, reason: "" });
      else {
        const fit = DL.fitsAt(DL.drawer(), drag.bins, drag.gx, drag.gy, drag.keys);
        Object.assign(drag, { valid: fit.ok, reason: fit.ok ? "" : refusal || fit.reason });
      }
      canvas.style.cursor = drag.outside ? "no-drop" : "grabbing";
      DV.render();
    } else if (DV.pan) {
      const point = DV.pan.cam.onPlane(sx, sy, 0);
      if (!point) return;
      DV.view.panX = DV.pan.panX - (point[0] - DV.pan.start[0]);
      DV.view.panY = DV.pan.panY - (point[1] - DV.pan.start[1]);
      DV.clampPan(DL.drawer());
      DV.render();
    } else {
      const hit = DV.hitAt(sx, sy);
      const key = hit?.key || null;
      canvas.style.cursor = hit ? (hit.grid ? "grab" : "pointer") : "";
      if (key !== DV.hover) {
        DV.hover = key;
        const found = key && DL.findPlacement(key);
        const one = found && DL.bin(found.placement.bin);
        canvas.title = one ? `${DL.label(one)} - ${DL.sizeText(one)}${DL.stackable(one) ? ` · ${DL.stackName(one.stack)}` : ""}${DL.isPlanned(found.placement) ? " (planned)" : ""}` : "";
        DV.render();
      }
    }
  });
  const finish = event => {
    if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    canvas.classList.remove("panning");
    canvas.style.cursor = "";
    const drag = DV.drag;
    DV.drag = null;
    DV.pan = null;
    if (drag?.moved) {
      if (drag.outside) {
        const count = DL.takeOut(drag.key);
        toast(`Taken out of the drawer${count > 1 ? ` (${count} bins)` : ""}. Back in the inventory list.`);
      } else if (drag.target) {
        DL.moveTo(drag.key, { target: drag.target });
      } else if (drag.valid) {
        DL.moveTo(drag.key, { gx: drag.gx, gy: drag.gy });
      } else {
        toast(drag.reason || "It does not fit there.", true);
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

  // Dropping a bin dragged from the inventory list: onto the floor, or onto a
  // stack it can snap onto.
  canvas.addEventListener("dragover", event => {
    if (!DV.dragBin || !DV.cam) return;
    event.preventDefault();
    const [sx, sy] = DV.point(event);
    const bins = [DV.dragBin];
    const [gx, gy] = DV.cellUnder(bins, sx, sy);
    const { target, refusal } = DV.stackTarget(bins, sx, sy, null);
    const fit = target ? { ok: true } : DL.fitsAt(DL.drawer(), bins, gx, gy);
    const next = { bin: DV.dragBin, gx, gy, target, valid: fit.ok, reason: fit.ok ? "" : refusal || fit.reason };
    if (DV.drop?.gx !== next.gx || DV.drop?.gy !== next.gy || DV.drop?.target !== next.target) {
      DV.drop = next;
      DV.render();
    }
  });
  canvas.addEventListener("dragleave", () => { DV.drop = null; DV.render(); });
  canvas.addEventListener("drop", event => {
    event.preventDefault();
    const drop = DV.drop;
    DV.drop = null;
    if (drop) {
      if (!drop.valid) toast(drop.reason || "It does not fit there.", true);
      else DL.placeAt(drop.bin, drop.target ? { target: drop.target } : { gx: drop.gx, gy: drop.gy });
    }
    DV.render();
  });

  new ResizeObserver(() => DV.render()).observe(canvas.parentElement);

  // Keys while the drawer is on screen. Capture phase, so the bin editor's
  // own shortcuts (Undo, arrow nudges) never act on the hidden design.
  window.addEventListener("keydown", event => {
    if (!DL.active || !DL.layout) return;
    if (event.target.closest?.("input, textarea, select, [contenteditable='true']")) return;
    if (document.querySelector("dialog[open]")) return;
    const key = event.key.toLowerCase();
    const mod = event.ctrlKey || event.metaKey;
    const chain = DL.selected && DL.stackOf(DL.selected);
    const moves = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, 1], arrowdown: [0, -1] };
    let handled = true;
    if (mod && key === "z") (event.shiftKey ? DL.redo : DL.undo)();
    else if (mod && key === "y") DL.redo();
    else if (mod && key === "s") DL.save();
    else if (mod && key === "p") DV.printMap();
    else if (mod || event.altKey) handled = false;
    else if (moves[key] && chain) {
      if (chain[0].locked) toast("This stack is locked. Unlock it (L) to move it.");
      else {
        const drawer = DL.drawer();
        const [dx, dy] = moves[key];
        const gx = DL.toCell(chain[0].gx, drawer) + dx;
        const gy = DL.toCell(chain[0].gy, drawer) + dy;
        const fit = DL.fitsAt(drawer, chain.map(p => DL.bin(p.bin)), gx, gy, new Set(chain.map(DL.key)));
        if (fit.ok) DL.moveTo(DL.key(chain[0]), { gx, gy }); else toast(fit.reason, true);
      }
    } else if ((key === "delete" || key === "backspace") && DL.selected) DL.removePlacement(DL.selected);
    else if (key === "l" && chain) DL.toggleLock(DL.selected);
    else if (key === "escape") DL.selected = null;
    else if (key === "f") DV.fit();
    else handled = false;
    if (handled) {
      event.preventDefault();
      event.stopImmediatePropagation();
      DL.emit();
    }
  }, true);

  // The header's Undo/Redo act on the drawer while this view is showing.
  document.addEventListener("click", event => {
    if (!DL.active) return;
    const button = event.target.closest?.("#undo-design, #redo-design");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    (button.id === "undo-design" ? DL.undo : DL.redo)();
  }, true);
};

DV.buildOverlay = () => {
  const wrap = $('.canvas-wrap[data-canvas="drawer"]');
  if (!wrap || $("#dl-tilt")) return;
  wrap.insertAdjacentHTML("beforeend", `
    <div class="camera-controls dl-view-controls" aria-label="Drawer camera">
      <div class="camera-controls-row">
        <div class="camera-views"><div class="camera-views-row">
          <button type="button" data-dl-view="look" title="Standing at the drawer, looking in">Look in</button>
          <button type="button" data-dl-view="overhead" title="Almost straight down, like a plan">Overhead</button>
          <button type="button" data-dl-view="low" title="Low, as if crouched at the drawer - shows what hides behind what">Low</button>
          <button type="button" data-dl-view="fit" title="Frame the whole drawer again (F)">Fit</button>
        </div></div>
        <div class="zoom-controls">
          <button type="button" data-dl-zoom="out" aria-label="Zoom out">−</button>
          <button type="button" data-dl-zoom="in" aria-label="Zoom in">+</button>
        </div>
      </div>
      <div class="camera-controls-row">
        <label class="canvas-select dl-tilt-control" title="How steeply you look down into the drawer">Angle <input id="dl-tilt" type="range" min="${DV.LIMITS.tilt[0]}" max="${DV.LIMITS.tilt[1]}" step="1"></label>
        <label class="canvas-select dl-tilt-control" title="Step a little to the left or right of the drawer">Turn <input id="dl-turn" type="range" min="${DV.LIMITS.turn[0]}" max="${DV.LIMITS.turn[1]}" step="1"></label>
        <label class="canvas-select dl-empty-control">Empty cells <input id="dl-show-empty" type="checkbox"></label>
      </div>
    </div>
    <div id="dl-selection" class="dl-selection" hidden></div>
    <div class="layout-hint dl-hint">Drag bins to move · drop on a same-size stackable bin to stack · drag off the drawer to take out · drag the floor to pan · wheel zooms · L locks · Del removes</div>`);
  $$("[data-dl-view]").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.dlView === "fit") DV.fit(); else DV.setView(DV.PRESETS[button.dataset.dlView]);
  }));
  $$("[data-dl-zoom]").forEach(button => button.addEventListener("click",
    () => DV.zoomBy(button.dataset.dlZoom === "in" ? 1.2 : 1 / 1.2)));
  $("#dl-tilt").addEventListener("input", event => DV.setView({ tilt: event.target.value }));
  $("#dl-turn").addEventListener("input", event => DV.setView({ turn: event.target.value }));
  $("#dl-show-empty").addEventListener("change", event => DL.change(
    () => { DL.layout.settings.show_empty = event.target.checked; }, { history: false }));
  $("#dl-selection").addEventListener("click", event => {
    const action = event.target.closest("[data-sel]")?.dataset.sel;
    const found = DL.selected && DL.findPlacement(DL.selected);
    if (!action || !found) return;
    if (action === "lock") DL.toggleLock(DL.selected);
    if (action === "remove") DL.removePlacement(DL.selected);
    if (action === "printed") DL.markPrinted(DL.bin(found.placement.bin));
  });
  DV.syncControls();
};

// ------------------------------------------------------------------ print map

// A plain top-down plan of the active drawer for printing: numbered footprints
// that match the list under it, front of the drawer at the bottom.
DV.planImage = (drawer, width = 1400) => {
  const grid = DL.grid(drawer);
  const pad = 30;
  const s = (width - 2 * pad) / drawer.width;
  const height = Math.round(drawer.depth * s + 2 * pad);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const at = (x, y) => [pad + x * s, pad + (drawer.depth - y) * s];
  const rect = (x0, y0, x1, y1) => { const [ax, ay] = at(x0, y1); return [ax, ay, (x1 - x0) * s, (y1 - y0) * s]; };
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = "#f1ebdf";
  ctx.fillRect(...rect(0, 0, drawer.width, drawer.depth));
  ctx.strokeStyle = "rgba(120,100,70,.18)";
  ctx.beginPath();
  for (let x = 0; x <= grid.cols * grid.step + 1e-6; x += DL.UNIT) { const [ax, ay] = at(grid.ox + x, grid.oy); const [, by] = at(grid.ox + x, grid.oy + grid.rows * grid.step); ctx.moveTo(ax, ay); ctx.lineTo(ax, by); }
  for (let y = 0; y <= grid.rows * grid.step + 1e-6; y += DL.UNIT) { const [ax, ay] = at(grid.ox, grid.oy + y); const [bx] = at(grid.ox + grid.cols * grid.step, grid.oy + y); ctx.moveTo(ax, ay); ctx.lineTo(bx, ay); }
  ctx.stroke();
  const keepHatch = DV.hatch(ctx, "rgba(168,68,61,.6)");
  (drawer.keepouts || []).forEach(zone => { ctx.fillStyle = keepHatch; ctx.fillRect(...rect(zone.x, zone.y, zone.x + zone.w, zone.y + zone.d)); });
  const range = DV.heightRange();
  const items = DL.items(drawer);
  items.forEach((item, index) => {
    const x0 = grid.ox + item.gx * grid.step;
    const y0 = grid.oy + item.gy * grid.step;
    const box = rect(x0, y0, x0 + item.w * grid.step, y0 + item.d * grid.step);
    const top = item.bins[item.bins.length - 1];
    ctx.fillStyle = DV.binColor(top, range).top;
    ctx.fillRect(...box);
    ctx.strokeStyle = "#17252d";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(...box);
    ctx.fillStyle = "#17252d";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const size = Math.max(10, Math.min(20, box[3] * 0.28, box[2] / 6));
    ctx.font = `700 ${size}px 'Segoe UI', system-ui, sans-serif`;
    ctx.fillText(`${index + 1}`, box[0] + box[2] / 2, box[1] + box[3] / 2 - size * 0.55);
    ctx.font = `500 ${Math.max(9, size * 0.7)}px 'Segoe UI', system-ui, sans-serif`;
    const text = `${DL.label(top)}${item.bins.length > 1 ? ` ×${item.bins.length}` : ""}`;
    ctx.fillText(DV.fitText(ctx, text, box[2] - 6), box[0] + box[2] / 2, box[1] + box[3] / 2 + size * 0.55);
  });
  drawer.placements.filter(DL.isShim).forEach(p => {
    ctx.fillStyle = "#cdbf9f";
    ctx.fillRect(...rect(p.x, p.y, p.x + p.w, p.y + p.d));
  });
  ctx.strokeStyle = "#6b5d3a";
  ctx.lineWidth = 2;
  ctx.strokeRect(...rect(0, 0, drawer.width, drawer.depth));
  return canvas.toDataURL("image/png");
};

DV.printMap = () => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const rows = DL.items(drawer).map((item, index) => {
    const top = item.bins[item.bins.length - 1];
    const x = grid.ox + item.gx * grid.step;
    const y = grid.oy + item.gy * grid.step;
    const planned = item.chain.filter(DL.isPlanned).length;
    return `<tr><td>${index + 1}</td><td>${escapeHtml(item.bins.map(one => DL.label(one)).join(" + "))}</td>
      <td>${escapeHtml(DL.sizeText(item.bins[0]))}</td><td>${fmt(x)} from left, ${fmt(y)} from front</td>
      <td>${item.bins.length > 1 ? `${item.bins.length}-high, ${fmt(item.h)} mm` : escapeHtml(DL.stackName(top.stack))}</td>
      <td>${planned ? "planned" : ""}</td></tr>`;
  }).join("");
  let sheet = $("#dl-print-sheet");
  if (!sheet) {
    sheet = document.createElement("div");
    sheet.id = "dl-print-sheet";
    document.body.appendChild(sheet);
  }
  sheet.innerHTML = `<h1>${escapeHtml(drawer.name)}</h1>
    <p>${fmt(drawer.width)} × ${fmt(drawer.depth)} mm inside, ${fmt(drawer.height)} mm max height. Front of the drawer at the bottom.</p>
    <img alt="Drawer map" src="${DV.planImage(drawer)}">
    <table><thead><tr><th>#</th><th>Bin</th><th>Size</th><th>Where (front-left corner, mm)</th><th>Stacking</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  document.body.classList.add("dl-printing");
  const done = () => { document.body.classList.remove("dl-printing"); window.removeEventListener("afterprint", done); };
  window.addEventListener("afterprint", done);
  setTimeout(() => window.print(), 50);
};
