"use strict";

// Drawer layout mode - the drawer canvas.
//
// Not a free 3D camera: the drawer is always seen from its front, and the only
// view controls are how steeply you look down (Top -> Low), pan and zoom. That
// keeps "front of the drawer" at the bottom of the screen, which is what the
// height rule (never a short bin behind a tall one) is about. The projection
// is a tilt about the drawer's left-right axis, so every bin face is a plain
// screen rectangle.

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

DV.frameFor = (width, height, drawer) => {
  const tilt = DV.view.tilt * Math.PI / 180;
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
  const s = base * DV.view.zoom;
  const cx = width / 2 + DV.view.panX;
  const cy = (height - footer) / 2 + DV.view.panY;
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
  const heights = DL.bins.filter(one => one.qty > 0 && !DL.isSpacer(one)).map(one => Number(one.z));
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
    if (problem.type === "height") {
      if (!keys.has(problem.keys[0])) keys.set(problem.keys[0], "height");
    } else {
      problem.keys.forEach(key => keys.set(key, "error"));
    }
  }
  return keys;
};

DV.fitText = (ctx, text, maxWidth) => {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let cut = text;
  while (cut.length > 1 && ctx.measureText(`${cut}…`).width > maxWidth) cut = cut.slice(0, -1);
  return cut.length > 1 ? `${cut}…` : "";
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
  const grid = DL.grid(drawer);
  const F = DV.frame = DV.frameFor(box.width, box.height, drawer);
  const P = F.project;
  const tilted = DV.view.tilt > 0.5;
  const U = DL.UNIT;
  // Screen rectangle of a level face at height z, and of a front-facing face.
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
  const gx1 = grid.ox + grid.cols * U;
  const gy1 = grid.oy + grid.rows * U;
  const hatch = DV.hatch(ctx, "rgba(150,130,95,.35)");
  [[0, 0, grid.ox, F.D], [gx1, 0, F.W, F.D], [grid.ox, 0, gx1, grid.oy], [grid.ox, gy1, gx1, F.D]]
    .forEach(([x0, y0, x1, y1]) => { if (x1 - x0 > 0.05 && y1 - y0 > 0.05) fill(level(x0, y0, x1, y1, 0), hatch); });
  ctx.strokeStyle = "rgba(120,100,70,.16)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  if (F.s * U >= 4) {
    for (let c = 0; c <= grid.cols; c += 1) {
      const [x, ya] = P(grid.ox + c * U, grid.oy, 0);
      const [, yb] = P(grid.ox + c * U, gy1, 0);
      ctx.moveTo(x, ya); ctx.lineTo(x, yb);
    }
    for (let r = 0; r <= grid.rows; r += 1) {
      const [xa, y] = P(grid.ox, grid.oy + r * U, 0);
      const [xb] = P(gx1, grid.oy + r * U, 0);
      ctx.moveTo(xa, y); ctx.lineTo(xb, y);
    }
  }
  ctx.stroke();

  // Keep-out zones.
  const keepHatch = DV.hatch(ctx, "rgba(168,68,61,.55)");
  (drawer.keepouts || []).forEach(zone => fill(level(zone.x, zone.y, zone.x + zone.w, zone.y + zone.d, 0), keepHatch, "rgba(168,68,61,.7)"));

  // Empty grid cells, and the largest empty spot the report found.
  if (DL.layout.settings.show_empty) {
    const taken = DL.blockedCells(drawer, grid);
    DL.gridItems(drawer).forEach(item => {
      for (let r = item.gy; r < item.gy + item.d; r += 1) for (let c = item.gx; c < item.gx + item.w; c += 1) taken.add(`${c},${r}`);
    });
    ctx.fillStyle = "rgba(47,150,110,.13)";
    for (let r = 0; r < grid.rows; r += 1) for (let c = 0; c < grid.cols; c += 1) {
      if (!taken.has(`${c},${r}`)) ctx.fillRect(...level(grid.ox + c * U + .6, grid.oy + r * U + .6, grid.ox + (c + 1) * U - .6, grid.oy + (r + 1) * U - .6, 0));
    }
    const spot = DL.report?.largest;
    if (spot && !DV.drag) {
      const rect = level(grid.ox + spot.gx * U, grid.oy + spot.gy * U, grid.ox + (spot.gx + spot.w) * U, grid.oy + (spot.gy + spot.d) * U, 0);
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

  // Bins, back to front so nearer bins cover the ones behind them.
  const range = DV.heightRange();
  const problems = DV.problemKeys();
  const items = [];
  for (const p of drawer.placements) {
    const one = DL.bin(p.bin);
    if (!one) continue;
    const key = DL.key(p);
    let mode = "";
    let x0, y0, x1, y1;
    if (p.gx !== undefined) {
      let { gx, gy } = p;
      if (DV.drag?.key === key && DV.drag.moved) {
        ({ gx, gy } = DV.drag);
        mode = DV.drag.outside ? "leaving" : DV.drag.valid ? "dragging" : "invalid";
      }
      const [w, d] = DL.units(one, drawer);
      x0 = grid.ox + gx * U; y0 = grid.oy + gy * U; x1 = x0 + w * U; y1 = y0 + d * U;
    } else {
      x0 = p.x; y0 = p.y; x1 = p.x + p.w; y1 = p.y + p.d;
    }
    items.push({ key, p, one, x0, y0, x1, y1, mode });
  }
  if (DV.drop) {
    const one = DV.drop.bin;
    const [w, d] = DL.units(one, drawer);
    const x0 = grid.ox + DV.drop.gx * U;
    const y0 = grid.oy + DV.drop.gy * U;
    items.push({ key: "__drop", p: null, one, x0, y0, x1: x0 + w * U, y1: y0 + d * U, mode: DV.drop.valid ? "ghost" : "invalid" });
  }
  items.sort((a, b) => b.y0 - a.y0 || a.x0 - b.x0);

  DV.hits = [];
  const inset = Math.min(1.5, 0.7 / F.s);
  for (const item of items) {
    const { one, mode } = item;
    const h = Number(one.z);
    const x0 = item.x0 + inset, x1 = item.x1 - inset, y0 = item.y0 + inset, y1 = item.y1 - inset;
    const color = DV.binColor(one, range);
    const problem = problems.get(item.key);
    let top = color.top, front = color.front, stroke = "rgba(23,37,45,.5)", ink = color.ink;
    if (mode === "invalid" || problem === "error") {
      top = "#f2bcb6"; front = "#d9918a"; stroke = "#a8443d"; ink = "#5e1f1b";
    }
    ctx.globalAlpha = mode === "leaving" ? 0.35 : (mode === "ghost" || mode === "dragging") ? 0.82 : 1;
    const topRect = level(x0, y0, x1, y1, h);
    const frontRect = tilted ? upright(x0, x1, y0, 0, h) : null;
    if (frontRect) fill(frontRect, front, stroke);
    fill(topRect, top, stroke);
    if (problem === "height") {
      ctx.save();
      ctx.setLineDash([4, 3]);
      ctx.strokeStyle = "#c8741f";
      ctx.lineWidth = 2;
      ctx.strokeRect(topRect[0] + 1, topRect[1] + 1, topRect[2] - 2, topRect[3] - 2);
      ctx.restore();
    }
    if (item.key === DL.selected || item.key === DV.hover) {
      const union = frontRect
        ? [topRect[0], topRect[1], topRect[2], frontRect[1] + frontRect[3] - topRect[1]]
        : topRect;
      ctx.strokeStyle = item.key === DL.selected ? "#146c70" : "rgba(20,108,112,.6)";
      ctx.lineWidth = item.key === DL.selected ? 3 : 2;
      ctx.strokeRect(union[0] - 1, union[1] - 1, union[2] + 2, union[3] + 2);
    }
    DV.drawLabel(ctx, item, topRect, ink);
    if (item.p?.locked && topRect[2] > 18 && topRect[3] > 14) {
      ctx.font = "10px 'Segoe UI Emoji', sans-serif";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText("🔒", topRect[0] + 3, topRect[1] + 2);
    }
    ctx.globalAlpha = 1;
    if (item.p) DV.hits.push({ key: item.key, grid: item.p.gx !== undefined, rects: frontRect ? [topRect, frontRect] : [topRect] });
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
  ctx.fillText(`FRONT · ${fmt(F.W)} mm wide · ${fmt(F.D)} deep · ${fmt(F.H)} tall`, fx, fy + 8);
  DV.renderSelection();
};

DV.drawLabel = (ctx, item, rect, ink) => {
  const [x, y, w, h] = rect;
  const { one } = item;
  const primary = one.kind === "shim" ? "Shim" : DL.label(one);
  const size = Math.min(14, h * 0.34, w / Math.max(3, primary.length * 0.56));
  if (size < 7) return;
  ctx.fillStyle = ink;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = `650 ${size}px 'Segoe UI', system-ui, sans-serif`;
  const twoLines = h > size * 2.7 && one.kind !== "shim";
  const cy = y + h / 2 - (twoLines ? size * 0.45 : 0);
  ctx.fillText(DV.fitText(ctx, primary, w - 6), x + w / 2, cy);
  if (twoLines) {
    const small = Math.max(7, size * 0.78);
    ctx.font = `500 ${small}px 'Segoe UI', system-ui, sans-serif`;
    const detail = one.name ? `${fmt(one.x)}×${fmt(one.y)} · ${fmt(one.z)} tall` : `${fmt(one.z)} mm tall`;
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
  card.innerHTML = `
    <strong>${escapeHtml(DL.label(one))}</strong>
    <span>${escapeHtml(DL.sizeText(one))}${copies > 1 ? ` · copy ${(p.copy ?? 0) + 1} of ${copies}` : ""}</span>
    ${found.drawer !== DL.drawer() ? `<span>In ${escapeHtml(found.drawer.name)}</span>` : ""}
    <div class="dl-selection-actions">
      ${p.gx !== undefined ? `<button type="button" data-sel="lock" title="Locked bins stay put when you drag or run Auto layout (L)">${p.locked ? "Unlock" : "Lock"}</button>` : ""}
      <button type="button" data-sel="remove" title="Take it out of the drawer (Delete)">Take out</button>
    </div>`;
};

DV.hitAt = (sx, sy) => {
  for (let index = DV.hits.length - 1; index >= 0; index -= 1) {
    const hit = DV.hits[index];
    if (hit.rects.some(([x, y, w, h]) => sx >= x && sx <= x + w && sy >= y && sy <= y + h)) return hit;
  }
  return null;
};

DV.point = event => {
  const box = $("#drawer-canvas").getBoundingClientRect();
  return [event.clientX - box.left, event.clientY - box.top];
};

// Where a bin dropped at this screen point would stand, centred on the pointer.
DV.cellUnder = (one, sx, sy) => {
  const drawer = DL.drawer();
  const grid = DL.grid(drawer);
  const [w, d] = DL.units(one, drawer);
  const [x, y] = DV.frame.unproject(sx, sy, Number(one.z));
  return [
    Math.round((x - grid.ox) / DL.UNIT - w / 2),
    Math.round((y - grid.oy) / DL.UNIT - d / 2),
  ];
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
      const found = DL.findPlacement(hit.key);
      if (hit.grid && found) {
        const { gx, gy } = found.placement;
        DV.drag = { key: hit.key, sx, sy, gx0: gx, gy0: gy, gx, gy, moved: false, valid: true, outside: false, locked: Boolean(found.placement.locked) };
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
        if (!drag.warned) { toast("This bin is locked. Unlock it (L) to move it."); drag.warned = true; }
        return;
      }
      drag.moved = true;
      const F = DV.frame;
      drag.gx = drag.gx0 + Math.round((sx - drag.sx) / F.s / DL.UNIT);
      drag.gy = drag.gy0 + Math.round(-(sy - drag.sy) / (F.s * F.c) / DL.UNIT);
      const found = DL.findPlacement(drag.key);
      const one = found && DL.bin(found.placement.bin);
      if (!one) return;
      const [x, y] = F.unproject(sx, sy, Number(one.z));
      drag.outside = x < -12 || y < -12 || x > F.W + 12 || y > F.D + 12;
      const fit = DL.fitsAt(DL.drawer(), one, drag.gx, drag.gy, drag.key);
      drag.valid = fit.ok;
      drag.reason = fit.reason;
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
        canvas.title = one ? `${DL.label(one)} - ${DL.sizeText(one)}${found.placement.locked ? " (locked)" : ""}` : "";
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
        DL.removePlacement(drag.key);
        toast("Taken out of the drawer. It is back in the inventory list.");
      } else if (drag.valid && (drag.gx !== drag.gx0 || drag.gy !== drag.gy0)) {
        DL.move(drag.key, drag.gx, drag.gy);
      } else if (!drag.valid) {
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

  // Dropping a bin dragged from the inventory list.
  canvas.addEventListener("dragover", event => {
    if (!DV.dragBin || !DV.frame) return;
    event.preventDefault();
    const [sx, sy] = DV.point(event);
    const [gx, gy] = DV.cellUnder(DV.dragBin, sx, sy);
    if (DV.drop?.gx !== gx || DV.drop?.gy !== gy) {
      DV.drop = { bin: DV.dragBin, gx, gy, valid: DL.fitsAt(DL.drawer(), DV.dragBin, gx, gy).ok };
      DV.render();
    }
  });
  canvas.addEventListener("dragleave", () => { DV.drop = null; DV.render(); });
  canvas.addEventListener("drop", event => {
    event.preventDefault();
    const drop = DV.drop;
    DV.drop = null;
    if (drop) DL.placeAt(drop.bin, drop.gx, drop.gy);
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
    const found = DL.selected && DL.findPlacement(DL.selected);
    const moves = { arrowleft: [-1, 0], arrowright: [1, 0], arrowup: [0, 1], arrowdown: [0, -1] };
    let handled = true;
    if (mod && key === "z") (event.shiftKey ? DL.redo : DL.undo)();
    else if (mod && key === "y") DL.redo();
    else if (mod && key === "s") DL.save();
    else if (mod || event.altKey) handled = false;
    else if (moves[key] && found && found.placement.gx !== undefined) {
      if (found.placement.locked) toast("This bin is locked. Unlock it (L) to move it.");
      else {
        const [dx, dy] = moves[key];
        const gx = found.placement.gx + dx;
        const gy = found.placement.gy + dy;
        const fit = DL.fitsAt(found.drawer, DL.bin(found.placement.bin), gx, gy, DL.selected);
        if (fit.ok) DL.move(DL.selected, gx, gy); else toast(fit.reason, true);
      }
    } else if ((key === "delete" || key === "backspace") && found) DL.removePlacement(DL.selected);
    else if (key === "l" && found) DL.toggleLock(DL.selected);
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
    <div class="layout-hint dl-hint">Drag bins to move · drag off the drawer to take out · drag the floor to pan · wheel zooms · L locks · Del removes</div>`);
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
    if (!action || !DL.selected) return;
    if (action === "lock") DL.toggleLock(DL.selected);
    if (action === "remove") DL.removePlacement(DL.selected);
  });
  DV.setTilt(DV.view.tilt);
};
