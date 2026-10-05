"use strict";

function kindColor(kind) {
  if (kind === "reference_object") return "#9db8c2";
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

// Lighting is a smooth function of a face normal, and every face of one flat
// surface shares it, so the shaded colour repeats over and over. Quantise the
// multiplier and memoise the result: per-face regex, parseInt and string
// building become a map lookup, which on a mesh preview is the difference
// between a fluid spin and a slideshow. 128 steps over the 0.42-1.2 range is
// under one part in 255 - below what a screen can show.
const SHADE_STEPS = 128;
const shadeCache = new Map();

function shadedColor(kind, normal) {
  const step = Math.round(faceLighting(normal) * SHADE_STEPS);
  const key = `${kind}|${step}`;
  let hit = shadeCache.get(key);
  if (hit === undefined) {
    hit = shade(kindColor(kind), step / SHADE_STEPS);
    shadeCache.set(key, hit);
  }
  return hit;
}

// Opaque neutral ground so the object has something to sit against, plus a soft
// contact shadow projected from the model's base rectangle - cheap grounding,
// no ray tracing.
let backdropCache = null;

function paintBackdrop(context, width, height) {
  if (!backdropCache || backdropCache.context !== context || backdropCache.height !== height) {
    const bg = context.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, "#eef1f2");
    bg.addColorStop(1, "#dfe4e5");
    backdropCache = { context, height, bg };
  }
  context.fillStyle = backdropCache.bg;
  context.fillRect(0, 0, width, height);
}

// `outerXY`, when given, overrides the shadow's footprint with the true
// case exterior - see draw3DDimensions for why box.x/box.y alone are wrong
// for B4B. Callers suppress the shadow outright (pass no box) for a view
// that isn't actually sitting on the ground, such as B4B's isolated Lid.
function drawContactShadow(context, box, camera, project, outerXY) {
  if (!box) return;
  const hx = (outerXY ? number(outerXY[0]) : number(box.x)) / 2;
  const hy = (outerXY ? number(outerXY[1]) : number(box.y)) / 2;
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

// A B4B preview is one triangle per mesh face - well over a hundred thousand of
// them on a big case. At that size the painter loop is the whole cost of a
// spin, so it is written flat: no per-face object spread, no closures, no
// throwaway arrays, no string colour maths, and back faces are dropped before
// anything is projected. The picture it paints is the same one as before.
// An ordinary bin's own geometry vs. everything a user has placed inside it -
// shared with the WebGL path's group classification so Bin/Interior/Xray
// mean the same thing whichever renderer is drawing them.
const isBinFace = kind =>
  kind === "outside" || kind === "inside" || kind === "rim" || kind === "floor" ||
  kind === "top_label_ledge" || kind === "label" || kind === "label_hole" ||
  kind === "lid" || kind === "lid_label" || kind === "base_trim";

// Which cardinal side of the bin the camera is looking from, by yaw alone
// (elevation only affects pitch, not which wall is nearest). Shared by the
// legacy Xray cull and the WebGL cutaway-buffer builder so both remove
// exactly the same wall.
function cameraFacingSide(camera = state.camera) {
  const yaw = number(camera?.yaw, 45) * Math.PI / 180;
  const camX = -Math.sin(yaw);
  const camY = -Math.cos(yaw);
  if (Math.abs(camX) >= Math.abs(camY)) return camX > 0 ? "x+" : "x-";
  return camY > 0 ? "y+" : "y-";
}

// A face counts as "on" the facing side either by its normal pointing
// strongly that way (catches near-planar wall faces directly) or, failing
// that, by its centroid sitting out past the 0.45-of-halfwidth band (catches
// bevelled/gusseted faces whose normal alone wouldn't clear the threshold).
// Both checks and both thresholds are load-bearing - see the legacy 2D
// painter this was extracted from.
function faceOnBinSide(face, side) {
  const [nx, ny] = face.normal;
  if (side === "x+" && nx > 0.3) return true;
  if (side === "x-" && nx < -0.3) return true;
  if (side === "y+" && ny > 0.3) return true;
  if (side === "y-" && ny < -0.3) return true;
  if (!face.points?.length) return false;
  let sumX = 0, sumY = 0;
  for (const point of face.points) {
    sumX += point[0];
    sumY += point[1];
  }
  const avgX = sumX / face.points.length;
  const avgY = sumY / face.points.length;
  const box = state.design?.box;
  const hx = box ? number(box.x) / 2 : 1;
  const hy = box ? number(box.y) / 2 : 1;
  switch (side) {
    case "x+": return avgX > hx * 0.45;
    case "x-": return avgX < -hx * 0.45;
    case "y+": return avgY > hy * 0.45;
    case "y-": return avgY < -hy * 0.45;
    default: return false;
  }
}

function isFacingBinWall(face, camera = state.camera) {
  return isBinFace(face.kind) && faceOnBinSide(face, cameraFacingSide(camera));
}

// Legacy full 2D-canvas painter. Used only as a fallback when WebGL is
// unavailable (see renderPreview3D) - the primary path is the depth-buffered
// WebGL renderer in preview3d-webgl.js, which this file no longer needs to
// keep pixel-identical to, though it still shares isBinFace/iso/project and
// the shading/colour helpers below.
function drawGeometryLegacy2D(canvas, geometry, camera) {
  const { context, width, height } = canvasSize(canvas);
  paintBackdrop(context, width, height);
  state.previewSupportPolygons = [];
  state.previewPickMeshContext = null;
  const visibleGroups = b4bEnabled()
    ? new Set(state.b4bView === "base" ? ["base"] : state.b4bView === "lid" ? ["lid"] : ["base", "lid"])
    : baseTrimEnabled() ? new Set(["bin"])
      : new Set([...(state.binVisible ? ["bin"] : []), ...(state.interiorVisible ? ["interior", "reference"] : [])]);
  if (!geometry?.length) {
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText("No geometry", width / 2, height / 2);
    return;
  }
  // Leaned-bore centre lines are annotation, not solid faces - pull them out so
  // the painter below doesn't cull them, and draw them on top at the end.
  const partitions = b4bEnabled() || baseTrimEnabled() ? null : ordinaryPreviewPartitions(state.preview);
  const boreAxes = partitions?.boreAxes || geometry.filter(face => face.kind?.endsWith("bore_axis"));
  if (partitions) geometry = partitions.solidGeometry;
  else if (boreAxes.length) geometry = geometry.filter(face => !face.kind?.endsWith("bore_axis"));
  const vector = cameraVector(camera);
  const yawRad = camera.yaw * Math.PI / 180;
  const elevationRad = camera.elevation * Math.PI / 180;
  const cosYaw = Math.cos(yawRad), sinYaw = Math.sin(yawRad);
  const cosEl = Math.cos(elevationRad), sinEl = Math.sin(elevationRad);
  const vx = vector[0], vy = vector[1], vz = vector[2];

  // Cull first, project second: a back face costs one dot product instead of
  // an iso() call per corner.
  const faces = [];
  for (let index = 0; index < geometry.length; index += 1) {
    const face = geometry[index];
    const kind = face.kind;
    const normal = face.normal;
    const facing = normal[0] * vx + normal[1] * vy + normal[2] * vz;
    if (facing <= 0 && kind !== "label_hole") continue;
    if (!visibleGroups.has(currentPreviewClassify()(face))) continue;
    if (state.xrayOn && isFacingBinWall(face, camera)) continue;
    const points = face.points;
    const corners = points.length;
    const projected = new Float64Array(corners * 2);
    let depth = 0;
    for (let at = 0; at < corners; at += 1) {
      const point = points[at];
      const px = point[0], py = point[1], pz = point[2];
      const forward = px * sinYaw + py * cosYaw;
      projected[at * 2] = px * cosYaw - py * sinYaw;
      projected[at * 2 + 1] = -forward * sinEl - pz * cosEl;
      depth += px * vx + py * vy + pz * vz;
    }
    faces.push({
       kind, normal, points, projected, corners, pick: face.pick,
      depth: depth / corners, layer: number(face.layer),
    });
  }
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
      if (face.layer < 2) face.layer = 2;
    }
  }
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const face of faces) {
    const flat = face.projected;
    for (let at = 0; at < flat.length; at += 2) {
      const x = flat[at], y = flat[at + 1];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  const spanX = Math.max(1e-8, maxX - minX), spanY = Math.max(1e-8, maxY - minY);
  const scale = Math.min((width * 0.75) / spanX, (height * 0.75) / spanY) * camera.zoom;
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
  const project = point => [width / 2 + (point[0] - midX) * scale, height / 2 + (point[1] - midY) * scale];
  if (b4bEnabled()) state.previewPickMeshContext = { camera, project, visibleGroups };
  const originX = width / 2 - midX * scale;
  const originY = height / 2 - midY * scale;
  faces.sort((a, b) => a.depth - b.depth || a.layer - b.layer);
  drawContactShadow(context, b4bShadowBox(), camera, project, b4bAssembledEnvelope());
  context.lineJoin = "round";
  let penFill = "", penStroke = "", penWidth = -1;
  for (let index = 0; index < faces.length; index += 1) {
    const face = faces[index];
    const flat = face.projected;
    const corners = face.corners;
    if (corners < 3) continue;
    let x = originX + flat[0] * scale, y = originY + flat[1] * scale;
    let lowX = x, highX = x, lowY = y, highY = y;
    context.beginPath();
    context.moveTo(x, y);
    for (let at = 1; at < corners; at += 1) {
      x = originX + flat[at * 2] * scale;
      y = originY + flat[at * 2 + 1] * scale;
      if (x < lowX) lowX = x; else if (x > highX) highX = x;
      if (y < lowY) lowY = y; else if (y > highY) highY = y;
      context.lineTo(x, y);
    }
    context.closePath();
    const kind = face.kind;
    const isDraft = kind.startsWith("draft_");
    const polygon = new Array(corners);
    for (let at = 0; at < corners; at += 1) {
      polygon[at] = [originX + flat[at * 2] * scale, originY + flat[at * 2 + 1] * scale];
    }
    if (!b4bEnabled() && kind !== "reference_object") addPreviewPickFace(face, polygon, camera);
    context.globalAlpha = kind === "reference_object" ? 0.3 : 1;
    const fill = shadedColor(kind, face.normal);
    if (fill !== penFill) { context.fillStyle = fill; penFill = fill; }
    context.fill();
    // Match the seam stroke to the fill first so internal triangulation stops
    // reading as a wireframe, then lay only a whisper of darker contrast where
    // surfaces actually meet.
    if (fill !== penStroke) { context.strokeStyle = fill; penStroke = fill; }
    if (penWidth !== 0.8) { context.lineWidth = 0.8; penWidth = 0.8; }
    context.stroke();
    // A face smaller than the seam stroke is already entirely covered by it, so
    // the contrast pass would land on pixels it has just painted. Skipping it
    // there costs nothing visible and is most of a mesh preview.
    if (highX - lowX < 0.6 && highY - lowY < 0.6) continue;
    const ink = isDraft ? "rgba(196,131,20,.45)" : "rgba(18,32,38,.08)";
    const inkWidth = isDraft ? 0.6 : 0.35;
    if (ink !== penStroke) { context.strokeStyle = ink; penStroke = ink; }
    if (penWidth !== inkWidth) { context.lineWidth = inkWidth; penWidth = inkWidth; }
    context.stroke();
  }
  context.globalAlpha = 1;
  drawUsableFloor(context, partitions?.floorZ ?? null, camera, project);
  drawBoreAxes(context, boreAxes, camera, project);
  draw3DDimensions(context, state.design?.box, camera, project, b4bAssembledEnvelope());
  addPreviewPickProxies(camera, point => project(iso(point, camera)), visibleGroups);
  drawFrontMarker(context, camera, point => project(iso(point, camera)), width, height);
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
function drawUsableFloor(context, floorZ, camera, project) {
  if (!state.binVisible) return;
  const box = state.design?.box;
  if (!box || floorZ === null) return;
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

// `outerXYZ`, when given, overrides the guides' extent and labels with the
// true assembled envelope - B4B's box.x/y/z are the child field, not the
// printed case (and for height, not even the full assembly: closed-lid
// height alone ignores hinge knuckles, and stacking pegs stand proud of
// that again), so the dimension overlay would otherwise mislabel the case
// and fail to reach its drawn edges on every axis. See fix3d.md.
function draw3DDimensions(context, box, camera, project, outerXYZ, options = null) {
  state.previewDimensionHandles = [];
  widthPillBox = null;
  if (!box) return;
  // Fix 103 (R1): `options` is the structural variant. It supplies the
  // interior values to edit/label, per-axis interactivity and an optional
  // height span (the active drawer); the guide geometry still comes from
  // `outerXYZ`. Without it this is exactly the ordinary bin overlay.
  const interactive = options ? true : !baseTrimEnabled();
  const axisInteractive = axis => interactive && (!options || options.interactive(axis));
  const axisHandle = (axis, value, displayValue) => (axisInteractive(axis)
    ? { view: "3d", axis, value: options ? options.value(axis) : value, displayValue, structural: Boolean(options) }
    : null);
  const axisLabel = (axis, fallback) => (options ? options.label(axis) : fallback);
  const outerX = outerXYZ ? number(outerXYZ[0]) : number(box.x);
  const outerY = outerXYZ ? number(outerXYZ[1]) : number(box.y);
  const outerZ = outerXYZ ? number(outerXYZ[2]) : number(box.z);
  const hx = outerX / 2;
  const hy = outerY / 2;
  const hz = outerZ;
  if (hx <= 0 || hy <= 0 || hz <= 0) return;
  // B4B's guides show the assembled envelope (outerX/Y/Z) but box.x/y/z is
  // still the field a drag actually edits - each handle carries both: the
  // envelope number to draw/scale the guide with, and the real field to
  // start the drag from (see dimensionDisplayOverride/fix3d.md).
  const editBox = { x: number(box.x), y: number(box.y), z: number(box.z) };

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
    axisLabel("x", `Width ${fmt(outerX)} mm`),
    gap,
    over,
    axisHandle("x", editBox.x, outerX),
    box => { widthPillBox = box; }
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
    axisLabel("y", `Depth ${fmt(outerY)} mm`),
    gap,
    over,
    axisHandle("y", editBox.y, outerY)
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

  const zLow = options?.zSpan ? options.zSpan[0] : 0;
  const zHigh = options?.zSpan ? options.zSpan[1] : hz;
  const sBot = project(iso([leftmostCorner[0], leftmostCorner[1], zLow], camera));
  const sTop = project(iso([leftmostCorner[0], leftmostCorner[1], zHigh], camera));
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
    axisLabel("z", `Height ${fmt(outerZ)} mm`),
    gap,
    over,
    axisHandle("z", editBox.z, options?.zSpan ? zHigh - zLow : outerZ)
  );
}

// Screen-space box of the Width pill from the latest 3D dimension pass, so the
// FRONT marker can step out of its way. Null when no Width pill was drawn.
let widthPillBox = null;

// `handle`, when given, registers a canvas-space hit region around the drawn
// label into state.previewDimensionHandles/layoutDimensionHandles so a
// pointerdown on the label can start a resize drag instead of orbiting the
// camera or moving a feature - see hitDimensionHandle().
function renderDimensionGuide(context, pStart, pEnd, witA, witB, normal, label, gap, over, handle = null,
    onPillBox = null) {
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
  context.font = '600 11px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
  context.textAlign = "center";
  context.textBaseline = "middle";

  const tw = context.measureText(label).width;
  const padX = 8;
  const bw = tw + padX * 2;
  const bh = 18;
  const r = 5;

  const active = handle && (
    (state.dimensionHover?.view === handle.view && state.dimensionHover?.axis === handle.axis) ||
    (state.dimensionDrag?.view === handle.view && state.dimensionDrag?.axis === handle.axis)
  );

  // Subtle drop shadow for badge
  context.shadowColor = "rgba(18, 38, 46, 0.25)";
  context.shadowBlur = 6;
  context.shadowOffsetY = 2;

  // Dark HUD pill badge - a touch darker/bolder while draggable and under
  // the pointer, so the label reads as grabbable without adding clutter.
  context.fillStyle = active ? "rgba(10, 24, 30, 0.95)" : "rgba(18, 38, 46, 0.90)";
  context.beginPath();
  if (context.roundRect) {
    context.roundRect(-bw / 2, -bh / 2, bw, bh, r);
  } else {
    context.rect(-bw / 2, -bh / 2, bw, bh);
  }
  context.fill();

  context.shadowColor = "transparent";
  context.strokeStyle = active ? "rgba(146, 214, 209, 0.95)" : "rgba(105, 172, 168, 0.70)";
  context.lineWidth = active ? 1.5 : 1;
  context.stroke();

  // Crisp text
  context.fillStyle = "#ffffff";
  context.fillText(label, 0, 0.5);

  context.restore();

  if (onPillBox) {
    // The visible pill only (no hit padding), as the axis-aligned box of the
    // rotated badge.
    const cosT = Math.abs(Math.cos(textAngle)), sinT = Math.abs(Math.sin(textAngle));
    const boxW = bw * cosT + bh * sinT;
    const boxH = bw * sinT + bh * cosT;
    onPillBox({ x: mid[0] - boxW / 2, y: mid[1] - boxH / 2, width: boxW, height: boxH });
  }

  if (handle) {
    // Generous hit region around the label itself (not the whole dimension
    // line) - padded well past the visible pill so it's an easy grab target,
    // and rotated the same as the badge so it stays aligned to the label at
    // any camera yaw.
    const padHit = 9;
    const halfW = bw / 2 + padHit;
    const halfH = Math.max(14, bh / 2 + padHit);
    const cos = Math.cos(textAngle), sin = Math.sin(textAngle);
    const corners = [[-halfW, -halfH], [halfW, -halfH], [halfW, halfH], [-halfW, halfH]]
      .map(([lx, ly]) => [mid[0] + lx * cos - ly * sin, mid[1] + lx * sin + ly * cos]);
    const xs = corners.map(point => point[0]);
    const ys = corners.map(point => point[1]);
    const hitBox = {
      x: Math.min(...xs),
      y: Math.min(...ys),
      width: Math.max(...xs) - Math.min(...xs),
      height: Math.max(...ys) - Math.min(...ys),
    };
    let screenAxisX = dx / span, screenAxisY = dy / span;
    if (Math.abs(dx) >= Math.abs(dy)) {
      if (dx < 0) { screenAxisX = -screenAxisX; screenAxisY = -screenAxisY; }
    } else if (dy > 0) {
      screenAxisX = -screenAxisX; screenAxisY = -screenAxisY;
    }
    const target = handle.view === "3d" ? state.previewDimensionHandles : state.layoutDimensionHandles;
    target.push({
      view: handle.view,
      axis: handle.axis,
      hitBox,
      screenAxis: [screenAxisX, screenAxisY],
      pixelSpan: span,
      value: handle.value,
      displayValue: handle.displayValue ?? handle.value,
      labelCenter: mid,
      structural: Boolean(handle.structural),
    });
  }
}

let glRenderer = null;
let glInitAttempted = false;
let glBuffersCache = null; // { source, b4b, generation, buffers, xray }
let ordinaryPartitionsCache = null;

function ordinaryPreviewPartitions(preview) {
  if (ordinaryPartitionsCache?.source === preview) return ordinaryPartitionsCache;
  const geometry = preview.geometry || [];
  const boreAxes = [];
  const solidGeometry = [];
  let floorZ = null;
  for (const face of geometry) {
    if (face.kind?.endsWith("bore_axis")) {
      boreAxes.push(face);
    } else {
      solidGeometry.push(face);
    }
    if (face.kind === "floor") {
      for (const point of face.points) floorZ = Math.max(floorZ ?? -Infinity, point[2]);
    }
  }
  ordinaryPartitionsCache = {
    source: preview, boreAxes,
    solidGeometry: boreAxes.length ? solidGeometry : geometry,
    floorZ, pickProxies: preview.pick_proxies || [],
  };
  return ordinaryPartitionsCache;
}

function ensurePreviewGL() {
  if (glInitAttempted) return glRenderer;
  glInitAttempted = true;
  const canvas = $("#preview-3d-solid");
  if (canvas && window.Preview3DGL) {
    try {
      glRenderer = window.Preview3DGL.init(canvas, {
        // Restoration rebuilds the program and advances `generation` but
        // does not itself trigger a redraw - without this, the view stays
        // blank after a genuine context loss until something else happens
        // to call renderPreview3D() (rotate, zoom, resize, a new preview).
        onContextRestored: () => requestAnimationFrame(renderPreview3D),
      });
    } catch (error) {
      glRenderer = null;
    }
  }
  return glRenderer;
}

// B4B classifies preview faces by which physical part they belong to - an
// explicit `owner` field the backend attaches to every B4B face (see
// fix3d.md) - rather than guessing from `kind`, which B4B's own kinds
// (b4b_body/b4b_lid/...) were never meaningful input for. Anything without
// an owner (should not happen for B4B geometry) defaults to base so it is
// never silently dropped from every view.
function classifyB4BFace(face) {
  return face.owner === "lid" ? "lid" : "base";
}

function classifyOrdinaryFace(face) {
  if (face.kind === "reference_object") return "reference";
  return isBinFace(face.kind) ? "bin" : "interior";
}

function currentPreviewGroups() {
  return b4bEnabled() ? ["base", "lid"] : ["bin", "interior", "reference"];
}

function previewAabbWithoutReference(buffers) {
  const selected = [buffers.groups.bin?.aabb, buffers.groups.interior?.aabb].filter(Boolean);
  if (!selected.length) return null;
  return {
    min: [0, 1, 2].map(axis => Math.min(...selected.map(box => box.min[axis]))),
    max: [0, 1, 2].map(axis => Math.max(...selected.map(box => box.max[axis]))),
  };
}

function currentPreviewClassify() {
  return b4bEnabled() ? classifyB4BFace : classifyOrdinaryFace;
}

// Which groups draw (and at what alpha), and which group's bounds the camera
// frames to. Bin/Interior/Xray are independent pure-visibility toggles over
// the SAME complete geometry, so they all frame to the complete model's
// AABB - toggling any of them must never re-fit the camera to whatever
// happens to still be visible. (Xray's camera-facing wall cutaway is a buffer
// swap done separately in renderPreview3DGL(); the passes below already
// describe its fully-opaque bin+interior result.)
function currentPreviewPasses(buffers) {
  if (b4bEnabled()) {
    const view = state.b4bView;
    if (view === "base") {
      return { passes: [{ group: "base", alpha: 1 }], aabb: buffers.groups.base?.aabb, visible: new Set(["base"]) };
    }
    if (view === "lid") {
      return { passes: [{ group: "lid", alpha: 1 }], aabb: buffers.groups.lid?.aabb, visible: new Set(["lid"]) };
    }
    return {
      passes: [{ group: "base", alpha: 1 }, { group: "lid", alpha: 1 }],
      aabb: buffers.allAabb, visible: new Set(["base", "lid"]),
    };
  }
  if (baseTrimEnabled()) {
    return {
      passes: [{ group: "bin", alpha: 1 }],
      aabb: buffers.allAabb,
      visible: new Set(["bin"]),
    };
  }
  const passes = [];
  const visible = new Set();
  if (state.binVisible) { passes.push({ group: "bin", alpha: 1 }); visible.add("bin"); }
  if (state.interiorVisible) {
    passes.push({ group: "interior", alpha: 1 }); visible.add("interior");
    passes.push({ group: "reference", alpha: 0.3 }); visible.add("reference");
  }
  return { passes, aabb: state.interiorVisible ? buffers.allAabb : previewAabbWithoutReference(buffers), visible };
}

function renderPreview3D() {
  // Fix 103 (Section C): a structural target in Design renders from its own
  // slot through its own scene; the ordinary predicates below read
  // state.design and must never see the structural target.
  if (typeof structuralDesignActive === "function" && structuralDesignActive()) { renderStructuralPreview3D(); return; }
  if (!state.preview) return;
  checkBinSizeChange();
  const overlayCanvas = $("#preview-3d");
  const solidCanvas = $("#preview-3d-solid");
  // B4B ships its geometry as compact mesh groups (state.preview.meshes) -
  // "geometry" is always [] for a B4B response, only kept for response-shape
  // compatibility. See organizer_b4b.b4b_preview_meshes.
  const b4b = b4bEnabled();
  const compact = b4b || baseTrimEnabled();
  const geometry = state.preview.geometry || [];
  const meshes = state.preview.meshes || [];
  const renderer = ensurePreviewGL();
  if (!renderer || renderer.lost) {
    if (solidCanvas) solidCanvas.hidden = true;
    // The legacy 2D fallback only ever understood the per-face format, and
    // never shipped for B4B before compact transport existed; give it the
    // one geometry shape it knows rather than teaching it a second one for
    // a path that only runs when WebGL itself is unavailable.
    drawGeometryLegacy2D(overlayCanvas, compact ? meshesToLegacyFaces(meshes) : geometry, state.camera);
    return;
  }
  if (solidCanvas) solidCanvas.hidden = false;
  renderPreview3DGL(renderer, overlayCanvas, compact, geometry, meshes, state.camera);
}

// The legacy painter only ever spoke the per-face format; B4B's compact
// mesh groups need expanding back into that shape for it. Only reached when
// WebGL itself is unavailable, so this never runs on the normal path.
function meshesToLegacyFaces(meshes) {
  const faces = [];
  for (const mesh of meshes) {
    const { positions, normals, kind, layer, owner } = mesh;
    const triangleCount = (positions.length / 9) | 0;
    for (let t = 0; t < triangleCount; t += 1) {
      const at = t * 9;
      faces.push({
        points: [
          [positions[at], positions[at + 1], positions[at + 2]],
          [positions[at + 3], positions[at + 4], positions[at + 5]],
          [positions[at + 6], positions[at + 7], positions[at + 8]],
        ],
        normal: [normals[t * 3], normals[t * 3 + 1], normals[t * 3 + 2]],
        kind, layer, owner,
      });
    }
  }
  return faces;
}

function renderPreview3DGL(renderer, overlayCanvas, b4b, fullGeometry, meshes, camera) {
  const { context, width, height } = canvasSize(overlayCanvas);
  context.clearRect(0, 0, width, height);
  state.previewSupportPolygons = [];
  const hasContent = b4b ? meshes.length > 0 : fullGeometry.length > 0;
  if (!hasContent) {
    window.Preview3DGL.draw(renderer, null, window.Preview3DGL.computeFrame(camera, null, width, height), width, height, []);
    context.fillStyle = "#8b989e";
    context.textAlign = "center";
    context.fillText("No geometry", width / 2, height / 2);
    return;
  }
  // Neither bore axes, the usable-floor rectangle nor placed-part hit-test
  // polygons apply to B4B (it has no bores, no "floor" kind, and no
  // interior-part editing - see _reject_if_b4b), so the overlay gets an
  // empty face list for it rather than a parallel code path.
  const partitions = b4b ? null : ordinaryPreviewPartitions(state.preview);
  const boreAxes = partitions?.boreAxes || [];
  const solidGeometry = partitions?.solidGeometry || [];
  const classify = currentPreviewClassify();
  const source = b4b ? meshes : fullGeometry;
  // Keyed on renderer.generation, not on having observed `lost` at some
  // point: loss and restore can both happen between two redraws (nothing
  // requires a repaint while the context is actually down), so `lost`
  // alone can never be relied on to have been seen. `generation` instead
  // advances exactly once per successful restore and stays put otherwise,
  // so this always notices when the cached buffers belong to a context
  // that no longer exists - regardless of when the redraw that discovers
  // it happens to run.
  if (
    !glBuffersCache || glBuffersCache.source !== source || glBuffersCache.b4b !== b4b
    || glBuffersCache.generation !== renderer.generation
  ) {
    if (glBuffersCache) {
      window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.buffers);
      if (glBuffersCache.xray?.buffers) window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.xray.buffers);
    }
    const groupNames = currentPreviewGroups();
    glBuffersCache = {
      source, b4b, generation: renderer.generation,
      buffers: b4b
        ? window.Preview3DGL.buildBuffersFromMeshes(renderer.gl, meshes, groupNames, kindColor)
        : window.Preview3DGL.buildBuffers(renderer.gl, solidGeometry, groupNames, classify, kindColor),
      xray: null,
    };
  }
  const buffers = glBuffersCache.buffers;
  const chosen = currentPreviewPasses(buffers);
  let drawBuffers = buffers;

  // Xray's cutaway wall is a separate, lazily-built buffer over the SAME
  // complete geometry - never a rebuild of the normal buffer, and never a
  // reason to re-fit the camera (both aabb and frame below still come from
  // the complete, unfiltered `buffers`). Only four side variants exist, so
  // one cached buffer per current facing side is enough to keep spinning
  // smooth without rebuilding on every frame.
  if (!b4b && !baseTrimEnabled() && state.xrayOn) {
    const side = cameraFacingSide(camera);
    if (!glBuffersCache.xray || glBuffersCache.xray.side !== side) {
      if (glBuffersCache.xray?.buffers) window.Preview3DGL.disposeBuffers(renderer.gl, glBuffersCache.xray.buffers);
      const xrayGeometry = solidGeometry.filter(face => !isFacingBinWall(face, camera));
      glBuffersCache.xray = {
        side,
        buffers: window.Preview3DGL.buildBuffers(renderer.gl, xrayGeometry, currentPreviewGroups(), classify, kindColor),
      };
    }
    drawBuffers = glBuffersCache.xray.buffers;
  }

  const aabb = chosen.aabb || buffers.allAabb;
  const frame = window.Preview3DGL.computeFrame(camera, aabb, width, height);
  window.Preview3DGL.draw(renderer, drawBuffers, frame, width, height, chosen.passes);
  drawOverlay2D(context, width, height, solidGeometry, boreAxes, camera, frame, classify,
    chosen.visible, partitions);
}

// Everything that is not solid geometry: the contact shadow, the usable-
// floor rectangle, bore-axis arrows, dimension guides, and the (invisible)
// hit-test polygons clickedPreviewSupport() uses to tell a click on a placed
// part from a click on empty canvas. Drawn on the transparent 2D canvas
// layered over the WebGL solid pass, using the same camera frame so
// everything lines up with it pixel-for-pixel.
function drawOverlay2D(context, width, height, solidGeometry, boreAxes, camera, frame, classify,
    visibleGroups, partitions) {
  const vector = cameraVector(camera);
  const project = point => [
    width / 2 + (point[0] - frame.midX) * frame.scale,
    height / 2 + (point[1] - frame.midY) * frame.scale,
  ];
  state.previewPickMeshContext = b4bEnabled() ? { camera, project, visibleGroups } : null;
  for (const face of solidGeometry) {
    const kind = face.kind;
    if (!visibleGroups.has(classify(face))) continue;
    if (state.xrayOn && isFacingBinWall(face, camera)) continue;
    if (dot(face.normal, vector) <= 0 || face.kind === "reference_object") continue;
    addPreviewPickFace(face, face.points.map(point => project(iso(point, camera))), camera);
  }
  addPreviewPickProxies(camera, point => project(iso(point, camera)), visibleGroups,
    partitions?.pickProxies);
  const box = dimensionDragBoxOverride(state.design?.box, "3d");
  drawContactShadow(context, b4bShadowBox(), camera, project, b4bAssembledEnvelope());
  drawUsableFloor(context, partitions?.floorZ ?? null, camera, project);
  drawBoreAxes(context, boreAxes, camera, project);
  const outerXYZ = dimensionDisplayOverride(b4bAssembledEnvelope());
  draw3DDimensions(context, box, camera, project, outerXYZ);
  drawDimensionGhost3D(context, camera, project, box, outerXYZ);
  drawFrontMarker(context, camera, point => project(iso(point, camera)), width, height);
}

// B4B's assembled_envelope_mm accounts for hinge/latch/handle/stacking
// projection on every axis (see b4b_summary), unlike box.x/y/z which are
// the child field. Used to correct both the dimension guides and the
// contact shadow's footprint so they track the physical case.
function b4bAssembledEnvelope() {
  if (baseTrimEnabled()) {
    const outer = state.preview?.base_trim?.outer_mm;
    return outer ? [outer[0], outer[1], state.design?.box?.z] : null;
  }
  return state.preview?.b4b?.assembled_envelope_mm;
}

// The contact shadow represents something resting on the ground. That's
// true for the whole assembly and for an isolated Base, but not for an
// isolated Lid - it is normally shown up on its hinges, not sitting flat -
// so a full-case shadow under it would be a footprint nothing is casting.
function b4bShadowBox() {
  if (b4bEnabled() && state.b4bView === "lid") return null;
  return state.design?.box;
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

function addPreviewPickFace(face, polygon, camera) {
  state.previewSupportPolygons.push({
    polygon, depths: face.points.map(point => dot(point, cameraVector(camera))),
    pick: face.pick || null, proxy: false,
  });
}

function addPreviewPickProxies(camera, project, visibleGroups, proxies = state.preview?.pick_proxies || []) {
  if (baseTrimEnabled() || (b4bEnabled()
    ? !visibleGroups.has("base") : !visibleGroups.has("interior"))) return;
  for (const proxy of proxies) {
    if (!proxy.points?.length || !proxy.pick) continue;
    state.previewSupportPolygons.push({
      polygon: proxy.points.map(project),
      depths: proxy.points.map(point => dot(point, cameraVector(camera))),
      pick: proxy.pick, proxy: true,
    });
  }
}

function pickTriangleDepth(point, record, first, second, third, requireInside) {
  const [a, b, c] = [first, second, third].map(index => record.polygon[index]);
  const cross = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
  if (Math.abs(cross) < 1e-9) return null;
  const u = ((b[1] - c[1]) * (point[0] - c[0]) + (c[0] - b[0]) * (point[1] - c[1])) / cross;
  const v = ((c[1] - a[1]) * (point[0] - c[0]) + (a[0] - c[0]) * (point[1] - c[1])) / cross;
  const w = 1 - u - v;
  if (requireInside && Math.min(u, v, w) < -1e-6) return null;
  return u * record.depths[first] + v * record.depths[second] + w * record.depths[third];
}

function previewPickDepth(point, record) {
  if (!pointInPolygon(point, record.polygon)) return null;
  for (let at = 1; at < record.polygon.length - 1; at += 1) {
    const depth = pickTriangleDepth(point, record, 0, at, at + 1, !record.proxy);
    if (depth !== null) return depth;
  }
  return null;
}

function clickedPreviewSupport(canvas, event) {
  const bounds = canvas.getBoundingClientRect();
  const point = [event.clientX - bounds.left, event.clientY - bounds.top];
  let closest = null;
  for (const record of state.previewSupportPolygons) {
    const depth = previewPickDepth(point, record);
    if (depth !== null && (!closest || depth > closest.depth)) closest = { depth, pick: record.pick };
  }
  const mesh = clickedPreviewMesh(point);
  if (mesh && (!closest || mesh.depth > closest.depth)) closest = mesh;
  return closest?.pick || null;
}

// Compact Storage Box meshes remain the printable visual source. This
// preview-only map identifies its one supported Divider without copying the
// triangles into the response or changing each mesh's physical owner.
function clickedPreviewMesh(point) {
  const context = state.previewPickMeshContext;
  if (!context || !state.preview?.pick_meshes?.length) return null;
  const identities = new Map(state.preview.pick_meshes.map(one => [one.mesh_index, one.pick]));
  const vector = cameraVector(context.camera);
  let closest = null;
  for (const [index, mesh] of (state.preview.meshes || []).entries()) {
    if (!context.visibleGroups.has(mesh.owner === "lid" ? "lid" : "base")) continue;
    const positions = mesh.positions || [], normals = mesh.normals || [];
    for (let at = 0; at + 8 < positions.length; at += 9) {
      const normalAt = at / 3;
      if (normals[normalAt] * vector[0] + normals[normalAt + 1] * vector[1]
          + normals[normalAt + 2] * vector[2] <= 0) continue;
      const points = [0, 3, 6].map(offset => positions.slice(at + offset, at + offset + 3));
      const record = {
        polygon: points.map(corner => context.project(iso(corner, context.camera))),
        depths: points.map(corner => dot(corner, vector)),
      };
      const depth = previewPickDepth(point, record);
      if (depth !== null && (!closest || depth > closest.depth)) {
        closest = { depth, pick: identities.get(index) || null };
      }
    }
  }
  return closest;
}

// Strict overlap: boxes that only share an edge do not collide.
function screenBoxesOverlap(a, b) {
  return a.x < b.x + b.width && b.x < a.x + a.width
    && a.y < b.y + b.height && b.y < a.y + a.height;
}

function drawFrontMarker(context, camera, project, viewWidth, viewHeight) {
  if (!state.design?.box || baseTrimEnabled()) return;
  const frontY = b4bEnabled()
    ? state.preview?.b4b?.assembled_bounds_mm?.[1]
    : -state.design.box.y / 2;
  if (!Number.isFinite(frontY)) return;
  const point = project([0, frontY - 5, 0]);
  context.save();
  context.font = 'bold 13px "Segoe UI Variable", "Segoe UI", system-ui, sans-serif';
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.fillStyle = "#153f48";
  const markerW = context.measureText("FRONT").width;
  const markerH = 13;
  const markerBox = y => ({ x: point[0] - markerW / 2, y: y - markerH / 2, width: markerW, height: markerH });
  let markerY = point[1];
  const pill = widthPillBox;
  if (pill && screenBoxesOverlap(markerBox(markerY), pill)) {
    // Vertical moves only (X stays put): above the pill, then below it, each
    // kept 4 px inside the viewport. If neither clears the pill, skip FRONT.
    const inset = 4;
    const lowest = inset + markerH / 2;
    const highest = Number.isFinite(viewHeight) ? viewHeight - inset - markerH / 2 : Infinity;
    const candidates = [pill.y - markerH / 2, pill.y + pill.height + markerH / 2]
      .map(y => Math.min(Math.max(y, lowest), highest));
    markerY = candidates.find(y => lowest <= highest && !screenBoxesOverlap(markerBox(y), pill));
  }
  if (markerY !== undefined) context.fillText("FRONT", point[0], markerY);
  context.restore();
}
