"use strict";

// Drawer layout mode - the drawer canvas.
//
// Not a free 3D camera: the drawer is always seen from its front, and the only
// view controls are how steeply you look down (Top -> Low), pan and zoom. That
// keeps "front of the drawer" at the bottom of the screen, which is what the
// height rule (never a short bin behind a tall one) is about. The projection
// is a tilt about the drawer's left-right axis, so every bin face is a plain
// screen rectangle and a stack is just boxes drawn on top of each other.

const DV = {
  view: { tilt: 35, zoom: 1, panX: 0, panY: 0 },
  PRESETS: { top: 0, angled: 35, low: 62 },
  hits: [],
  drag: null,
  pan: null,
  hover: null,
  drop: null,
  dragBin: null,
  frame: null,
};

try {
  const saved = JSON.parse(localStorage.getItem("wavefinity-drawer-view") || "{}");
  if (Number.isFinite(saved.tilt)) DV.view.tilt = saved.tilt;
} catch (_error) {}
DV.saveView = debounce(() => {
  try { localStorage.setItem("wavefinity-drawer-view", JSON.stringify({ tilt: DV.view.tilt })); } catch (_error) {}
}, 300);

DV.setTilt = tilt => {
  DV.view.tilt = Math.max(0, Math.min(70, Number(tilt) || 0));
  const slider = $("#dl-tilt");
  if (slider) slider.value = String(Math.round(DV.view.tilt));
  $$("[data-dl-view]").forEach(button => button.classList.toggle(
    "active", DV.PRESETS[button.dataset.dlView] === Math.round(DV.view.tilt)));
  DV.saveView();
  DV.render();
};

DV.fit = () => {
  Object.assign(DV.view, { zoom: 1, panX: 0, panY: 0 });
  DV.render();
};

DV.zoomBy = (factor, sx = null, sy = null) => {
  const frame = DV.frame;
  const next = Math.max(0.4, Math.min(8, DV.view.zoom * factor));
  const applied = next / DV.view.zoom;
  if (frame && sx !== null) {
    DV.view.panX += (sx - frame.cx) * (1 - applied);
    DV.view.panY += (sy - frame.cy) * (1 - applied);
  }
  DV.view.zoom = next;
  DV.render();
};

DV.frameFor = (width, height, drawer, tiltDeg = DV.view.tilt, view = DV.view) => {
  const tilt = tiltDeg * Math.PI / 180;
  const c = Math.cos(tilt);
  const sn = Math.sin(tilt);
  const W = drawer.width;
  const D = drawer.depth;
  const H = drawer.height;
  const margin = 46;
  const footer = 30;
  const base = Math.max(0.02, Math.min(
    (width - 2 * margin) / W,
    (height - 2 * margin - footer) / (D * c + H * sn),
  ));
  const s = base * view.zoom;
  const cx = width / 2 + view.panX;
  const cy = (height - footer) / 2 + view.panY;
  return {
    s, c, sn, W, D, H, cx, cy,
    project: (x, y, z) => [cx + (x - W / 2) * s, cy + ((D / 2 - y) * c - (z - H / 2) * sn) * s],
    unproject: (sx, sy, z = 0) => [
      (sx - cx) / s + W / 2,
      D / 2 - ((sy - cy) / s + (z - H / 2) * sn) / c,
    ],
  };
};

DV.heightRange = () => {
  const heights = DL.bins.filter(one => !DL.isSpacer(one)).map(one => Number(one.z));
  return heights.length ? [Math.min(...heights), Math.max(...heights)] : [0, 1];
};

// Short bins light, tall bins dark, so height order reads at a glance.
DV.binColor = (one, range) => {
  if (one.kind === "spacer") return { top: "#dcd5c4", front: "#c5bca7", ink: "#4d4636" };
  if (one.kind === "shim") return { top: "#cdbf9f", front: "#b3a582", ink: "#4d4636" };
  const t = range[1] > range[0] ? (one.z - range[0]) / (range[1] - range[0]) : 0.5;
  const b4b = one.kind === "b4b";
  const hue = b4b ? 262 : 188 - t * 6;
  const sat = b4b ? 28 : 30 + t * 22;
  const light = 85 - t * 42;
  return {
    top: `hsl(${hue} ${sat}% ${light}%)`,
    front: `hsl(${hue} ${sat}% ${light - 13}%)`,
    ink: light < 60 ? "#ffffff" : "#17252d",
  };
};

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

// Layers (bottom first) for bins standing on a stack or on the floor.
DV.layersFor = (bins, keys, start) => {
  let top = 0;
  return bins.map((one, index) => {
    const bottom = index ? top - (DL.stackSteps[one.stack] ?? 0) : start;
    top = bottom + Number(one.z);
    return { bin: one, key: keys[index], z0: bottom, z1: top };
  });
};

// What to draw: every footprint in the drawer, with a drag or drop shown
// where it would land.
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
  return entries.sort((a, b) => b.y0 - a.y0 || a.x0 - b.x0 || Number(Boolean(a.ghost)) - Number(Boolean(b.ghost)));
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
  DV.frame = DV.frameFor(box.width, box.height, drawer);
  DV.hits = DV.paint(ctx, drawer, DV.frame, { labels: true, interactive: true });
  DV.renderSelection();
};

// Draw one drawer into a 2D context through a frame. Returns hit rectangles.
DV.paint = (ctx, drawer, F, { labels = true, interactive = false } = {}) => {
  const grid = DL.grid(drawer);
  const P = F.project;
  const tilted = F.sn > 0.01;
  const step = grid.step;
  const level = (x0, y0, x1, y1, z) => {
    const [ax, ay] = P(x0, y1, z);
    const [bx, by] = P(x1, y0, z);
    return [ax, ay, bx - ax, by - ay];
  };
  const upright = (x0, x1, y, z0, z1) => {
    const [ax, ay] = P(x0, y, z1);
    const [bx, by] = P(x1, y, z0);
    return [ax, ay, bx - ax, by - ay];
  };
  const fill = (rect, style, stroke = null, width = 1) => {
    ctx.fillStyle = style;
    ctx.fillRect(...rect);
    if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = width; ctx.strokeRect(...rect); }
  };

  // Drawer: back wall, floor, the strips the grid cannot use, grid lines.
  if (tilted) fill(upright(0, F.W, F.D, 0, F.H), "#e3d9c5", "rgba(120,100,70,.35)");
  fill(level(0, 0, F.W, F.D, 0), "#f1ebdf", "rgba(120,100,70,.55)", 1.2);
  const gx1 = grid.ox + grid.cols * step;
  const gy1 = grid.oy + grid.rows * step;
  const hatch = DV.hatch(ctx, "rgba(150,130,95,.35)");
  [[0, 0, grid.ox, F.D], [gx1, 0, F.W, F.D], [grid.ox, 0, gx1, grid.oy], [grid.ox, gy1, gx1, F.D]]
    .forEach(([x0, y0, x1, y1]) => { if (x1 - x0 > 0.05 && y1 - y0 > 0.05) fill(level(x0, y0, x1, y1, 0), hatch); });
  if (F.s * step >= 4) {
    ctx.lineWidth = 1;
    for (const [every, tone] of [[step, "rgba(120,100,70,.10)"], [DL.UNIT, "rgba(120,100,70,.18)"]]) {
      if (every === step && step === DL.UNIT) continue;
      ctx.strokeStyle = tone;
      ctx.beginPath();
      for (let x = 0; x <= grid.cols * step + 1e-6; x += every) {
        const [sx, ya] = P(grid.ox + x, grid.oy, 0);
        const [, yb] = P(grid.ox + x, gy1, 0);
        ctx.moveTo(sx, ya); ctx.lineTo(sx, yb);
      }
      for (let y = 0; y <= grid.rows * step + 1e-6; y += every) {
        const [xa, sy] = P(grid.ox, grid.oy + y, 0);
        const [xb] = P(gx1, grid.oy + y, 0);
        ctx.moveTo(xa, sy); ctx.lineTo(xb, sy);
      }
      ctx.stroke();
    }
  }

  const keepHatch = DV.hatch(ctx, "rgba(168,68,61,.55)");
  (drawer.keepouts || []).forEach(zone => fill(level(zone.x, zone.y, zone.x + zone.w, zone.y + zone.d, 0), keepHatch, "rgba(168,68,61,.7)"));

  // Empty cells, and the largest empty spot the report found.
  if (interactive && DL.layout.settings.show_empty) {
    const taken = DL.blockedCells(drawer, grid);
    DL.items(drawer).forEach(item => {
      for (let r = item.gy; r < item.gy + item.d; r += 1) for (let c = item.gx; c < item.gx + item.w; c += 1) taken.add(`${c},${r}`);
    });
    ctx.fillStyle = "rgba(47,150,110,.13)";
    const inset = Math.min(0.6, step / 10);
    for (let r = 0; r < grid.rows; r += 1) for (let c = 0; c < grid.cols; c += 1) {
      if (!taken.has(`${c},${r}`)) ctx.fillRect(...level(grid.ox + c * step + inset, grid.oy + r * step + inset, grid.ox + (c + 1) * step - inset, grid.oy + (r + 1) * step - inset, 0));
    }
    const spot = DL.report?.largest;
    if (spot && !DV.drag && DL.report.grid?.step === step) {
      const rect = level(grid.ox + spot.gx * step, grid.oy + spot.gy * step, grid.ox + (spot.gx + spot.w) * step, grid.oy + (spot.gy + spot.d) * step, 0);
      ctx.save();
      ctx.setLineDash([5, 4]);
      ctx.strokeStyle = "rgba(31,107,69,.8)";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(...rect);
      ctx.restore();
      if (rect[2] > 60 && rect[3] > 16) {
        ctx.fillStyle = "rgba(31,107,69,.9)";
        ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(`${fmt(spot.w_mm)} × ${fmt(spot.d_mm)} free`, rect[0] + rect[2] / 2, rect[1] + rect[3] / 2);
      }
    }
  }

  // Footprints back to front; within one, layers bottom to top.
  const range = DV.heightRange();
  const problems = interactive ? DV.problemKeys() : new Map();
  const hits = [];
  const inset = Math.min(1.5, 0.7 / F.s);
  for (const entry of DV.entries(drawer, grid)) {
    if (!interactive && entry.ghost) continue;
    const x0 = entry.x0 + inset, x1 = entry.x1 - inset, y0 = entry.y0 + inset, y1 = entry.y1 - inset;
    const rects = [];
    entry.layers.forEach((layer, index) => {
      const one = layer.bin;
      const color = DV.binColor(one, range);
      const planned = layer.key !== "__drop" && layer.key.includes(":") && DL.isPlanned({ bin: one.id, copy: Number(layer.key.split(":")[1]) });
      const problem = problems.get(layer.key);
      let top = color.top, front = color.front, stroke = "rgba(23,37,45,.5)", ink = color.ink;
      if (entry.mode === "invalid" || problem === "error") { top = "#f2bcb6"; front = "#d9918a"; stroke = "#a8443d"; ink = "#5e1f1b"; }
      ctx.globalAlpha = entry.mode === "leaving" ? 0.35 : entry.mode === "ghost" ? 0.8 : planned ? 0.55 : 1;
      const frontRect = tilted ? upright(x0, x1, y0, layer.z0, layer.z1) : null;
      const topRect = level(x0, y0, x1, y1, layer.z1);
      if (frontRect) fill(frontRect, front, stroke);
      fill(topRect, top, stroke);
      if (planned) {
        ctx.save();
        ctx.globalAlpha = 1;
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = "#146c70";
        ctx.lineWidth = 1.5;
        if (frontRect) ctx.strokeRect(...frontRect);
        ctx.strokeRect(...topRect);
        ctx.restore();
      }
      if (problem === "height") {
        ctx.save();
        ctx.setLineDash([4, 3]);
        ctx.strokeStyle = "#c8741f";
        ctx.lineWidth = 2;
        ctx.strokeRect(topRect[0] + 1, topRect[1] + 1, topRect[2] - 2, topRect[3] - 2);
        ctx.restore();
      }
      ctx.globalAlpha = 1;
      rects.push({ layer, frontRect, topRect, ink, planned, last: index === entry.layers.length - 1 });
    });
    const last = rects[rects.length - 1];
    if (interactive && !entry.ghost) {
      const keys = entry.layers.map(layer => layer.key);
      const pick = DL.selected && keys.includes(DL.selected) ? DL.selected : DV.hover && keys.includes(DV.hover) ? DV.hover : null;
      if (pick) {
        const chosen = rects.find(r => r.layer.key === pick);
        const outline = chosen.frontRect
          ? [chosen.topRect[0], (chosen.last ? chosen.topRect : chosen.frontRect)[1], chosen.topRect[2], chosen.frontRect[1] + chosen.frontRect[3] - (chosen.last ? chosen.topRect : chosen.frontRect)[1]]
          : chosen.topRect;
        ctx.strokeStyle = pick === DL.selected ? "#146c70" : "rgba(20,108,112,.6)";
        ctx.lineWidth = pick === DL.selected ? 3 : 2;
        ctx.strokeRect(outline[0] - 1, outline[1] - 1, outline[2] + 2, outline[3] + 2);
      }
    }
    if (labels) DV.drawLabel(ctx, entry, last.topRect, last.ink, last.planned);
    const base = entry.item?.chain[0];
    if (base?.locked && last.topRect[2] > 18 && last.topRect[3] > 14) {
      ctx.font = "10px 'Segoe UI Emoji', sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("🔒", last.topRect[0] + 3, last.topRect[1] + 2);
    }
    if (!entry.ghost) {
      rects.forEach(r => hits.push({ key: r.layer.key, grid: !entry.shim, rects: r.frontRect ? (r.last ? [r.topRect, r.frontRect] : [r.frontRect]) : (r.last ? [r.topRect] : []) }));
    }
  }

  // The drawer's front wall, see-through, then its rim and the labels.
  if (tilted) fill(upright(0, F.W, 0, 0, F.H), "rgba(227,217,197,.28)");
  ctx.strokeStyle = "rgba(120,100,70,.55)";
  ctx.lineWidth = 1.2;
  ctx.strokeRect(...level(0, 0, F.W, F.D, F.H));
  ctx.beginPath();
  [[0, 0], [F.W, 0], [0, F.D], [F.W, F.D]].forEach(([x, y]) => {
    const [ax, ay] = P(x, y, 0);
    const [bx, by] = P(x, y, F.H);
    ctx.moveTo(ax, ay); ctx.lineTo(bx, by);
  });
  ctx.stroke();
  const [fx, fy] = P(F.W / 2, 0, 0);
  ctx.fillStyle = "#66757d";
  ctx.font = "700 11px 'Segoe UI', system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  ctx.fillText(`FRONT · ${fmt(F.W)} mm wide · ${fmt(F.D)} deep · ${fmt(F.H)} max height`, fx, fy + 8);
  return hits;
};

DV.drawLabel = (ctx, entry, rect, ink, planned) => {
  const [x, y, w, h] = rect;
  const top = entry.layers[entry.layers.length - 1].bin;
  const primary = top.kind === "shim" ? "Shim" : DL.label(top);
  const size = Math.min(14, h * 0.34, w / Math.max(3, primary.length * 0.56));
  if (size < 7) return;
  ctx.fillStyle = planned ? "#0d5356" : ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `650 ${size}px 'Segoe UI', system-ui, sans-serif`;
  const twoLines = h > size * 2.7 && top.kind !== "shim";
  const cy = y + h / 2 - (twoLines ? size * 0.45 : 0);
  ctx.fillText(DV.fitText(ctx, primary, w - 6), x + w / 2, cy);
  if (twoLines) {
    const small = Math.max(7, size * 0.78);
    ctx.font = `500 ${small}px 'Segoe UI', system-ui, sans-serif`;
    const stackHeight = entry.layers[entry.layers.length - 1].z1;
    const detail = entry.layers.length > 1
      ? `${entry.layers.length}-high stack · ${fmt(stackHeight)} tall`
      : planned ? `planned · ${fmt(top.z)} tall`
        : top.name ? `${fmt(top.x)}×${fmt(top.y)} · ${fmt(top.z)} tall` : `${fmt(top.z)} mm tall`;
    ctx.fillText(DV.fitText(ctx, detail, w - 6), x + w / 2, cy + size * 1.05);
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

DV.hitAt = (sx, sy, skip = null) => {
  for (let index = DV.hits.length - 1; index >= 0; index -= 1) {
    const hit = DV.hits[index];
    if (skip?.has(hit.key)) continue;
    if (hit.rects.some(([x, y, w, h]) => sx >= x && sx <= x + w && sy >= y && sy <= y + h)) return hit;
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
  const [x, y] = DV.frame.unproject(sx, sy, DL.stackHeight(bins));
  return [Math.round((x - grid.ox) / grid.step - w / 2), Math.round((y - grid.oy) / grid.step - d / 2)];
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

DV.wire = () => {
  const canvas = $("#drawer-canvas");
  canvas.addEventListener("contextmenu", event => event.preventDefault());
  canvas.addEventListener("pointerdown", event => {
    if (!DL.layout || !DV.frame) return;
    const [sx, sy] = DV.point(event);
    canvas.setPointerCapture(event.pointerId);
    const hit = event.button === 0 ? DV.hitAt(sx, sy) : null;
    if (hit) {
      DL.selected = hit.key;
      const chain = hit.grid && DL.stackOf(hit.key);
      if (chain) {
        const moving = chain.slice(chain.findIndex(p => DL.key(p) === hit.key));
        const drawer = DL.drawer();
        const gx = DL.toCell(chain[0].gx, drawer);
        const gy = DL.toCell(chain[0].gy, drawer);
        DV.drag = {
          key: hit.key, keys: new Set(moving.map(DL.key)), bins: moving.map(p => DL.bin(p.bin)),
          sx, sy, gx0: gx, gy0: gy, gx, gy, moved: false, valid: true, outside: false,
          target: null, locked: Boolean(chain[0].locked),
        };
      }
    } else {
      if (event.button === 0) DL.selected = null;
      DV.pan = { sx, sy, panX: DV.view.panX, panY: DV.view.panY };
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
      drag.moved = true;
      const F = DV.frame;
      const step = DL.grid().step;
      drag.gx = drag.gx0 + Math.round((sx - drag.sx) / F.s / step);
      drag.gy = drag.gy0 + Math.round(-(sy - drag.sy) / (F.s * F.c) / step);
      // Off the drawer means off every bin too: pointing at the top of a tall
      // stack projects "behind" the drawer at the dragged bin's own height.
      const [x, y] = F.unproject(sx, sy, DL.stackHeight(drag.bins));
      drag.outside = !DV.hitAt(sx, sy, drag.keys) && (x < -12 || y < -12 || x > F.W + 12 || y > F.D + 12);
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
      DV.view.panX = DV.pan.panX + sx - DV.pan.sx;
      DV.view.panY = DV.pan.panY + sy - DV.pan.sy;
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
    if (!DV.dragBin || !DV.frame) return;
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
    <div class="camera-controls dl-view-controls" aria-label="Drawer view controls">
      <div class="camera-controls-row">
        <div class="camera-views"><div class="camera-views-row">
          <button type="button" data-dl-view="top" title="Straight down">Top</button>
          <button type="button" data-dl-view="angled" title="Looking in from the front">Angled</button>
          <button type="button" data-dl-view="low" title="Low, as if crouched at the drawer - shows what hides behind what">Low</button>
          <button type="button" data-dl-view="fit" title="Fit the drawer to the view (F)">Fit</button>
        </div></div>
        <div class="zoom-controls">
          <button type="button" data-dl-zoom="out" aria-label="Zoom out">−</button>
          <button type="button" data-dl-zoom="in" aria-label="Zoom in">+</button>
        </div>
      </div>
      <div class="camera-controls-row">
        <label class="canvas-select dl-tilt-control">Tilt <input id="dl-tilt" type="range" min="0" max="70" step="1"></label>
        <label class="canvas-select dl-empty-control">Empty cells <input id="dl-show-empty" type="checkbox"></label>
      </div>
    </div>
    <div id="dl-selection" class="dl-selection" hidden></div>
    <div class="layout-hint dl-hint">Drag bins to move · drop on a same-size stackable bin to stack · drag off the drawer to take out · drag the floor to pan · wheel zooms · L locks · Del removes</div>`);
  $$("[data-dl-view]").forEach(button => button.addEventListener("click", () => {
    if (button.dataset.dlView === "fit") DV.fit(); else DV.setTilt(DV.PRESETS[button.dataset.dlView]);
  }));
  $$("[data-dl-zoom]").forEach(button => button.addEventListener("click",
    () => DV.zoomBy(button.dataset.dlZoom === "in" ? 1.2 : 1 / 1.2)));
  $("#dl-tilt").addEventListener("input", event => DV.setTilt(event.target.value));
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
  DV.setTilt(DV.view.tilt);
};

// A printable map of the active drawer: a top-down plan and a list of what
// goes where, measured from the inside front-left corner.
DV.printMap = () => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const canvas = document.createElement("canvas");
  canvas.width = 1400;
  canvas.height = Math.round(1400 * (drawer.depth + 60) / (drawer.width + 60));
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const F = DV.frameFor(canvas.width, canvas.height, drawer, 0, { zoom: 1, panX: 0, panY: 0 });
  DV.paint(ctx, drawer, F, { labels: true, interactive: false });
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
    <img alt="Drawer map" src="${canvas.toDataURL("image/png")}">
    <table><thead><tr><th>#</th><th>Bin</th><th>Size</th><th>Where (front-left corner, mm)</th><th>Stacking</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
  document.body.classList.add("dl-printing");
  const done = () => { document.body.classList.remove("dl-printing"); window.removeEventListener("afterprint", done); };
  window.addEventListener("afterprint", done);
  setTimeout(() => window.print(), 50);
};
