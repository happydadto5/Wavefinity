// Shared WebGL preview renderer (fix3d.md).
//
// Replaces the 2D canvas painter for *solid* 3D geometry with a real
// depth-buffered GPU renderer: no painter's-algorithm sort, no camera-facing
// triangle culling to fake Xray, no visible triangle seams. Annotations
// (dimension guides, bore axes, the usable-floor overlay, the contact
// shadow) stay on a 2D canvas layered on top - see drawOverlay2D() in
// app.js - because none of that is solid geometry.
//
// Exposed as `window.Preview3DGL` (plain <script>, no bundler in this app).
(function () {
  "use strict";

  // Matches app.js's KEY_LIGHT/FILL_LIGHT exactly (same vectors, normalized).
  const KEY_LIGHT = [-0.504843, -0.353390, 0.787487];
  const FILL_LIGHT = [0.609459, 0.744895, 0.270871];

  const VERTEX_SRC = `
    attribute vec3 aPosition;
    attribute vec3 aNormal;
    attribute vec3 aColor;
    uniform vec3 uRight;
    uniform vec3 uUp;
    uniform vec3 uForward;
    uniform vec2 uMid;
    uniform float uScale;
    uniform vec2 uHalfSize;
    uniform float uNearCam;
    uniform float uFarCam;
    varying vec3 vNormal;
    varying vec3 vColor;
    void main() {
      float viewX = dot(aPosition, uRight);
      float viewY = dot(aPosition, uUp);
      float viewZ = dot(aPosition, uForward);
      float clipX = (viewX - uMid.x) * uScale / uHalfSize.x;
      float clipY = -(viewY - uMid.y) * uScale / uHalfSize.y;
      float depthRange = max(uNearCam - uFarCam, 1.0e-6);
      float t = (uNearCam - viewZ) / depthRange;
      float clipZ = clamp(t * 2.0 - 1.0, -1.0, 1.0);
      gl_Position = vec4(clipX, clipY, clipZ, 1.0);
      vNormal = aNormal;
      vColor = aColor;
    }
  `;

  const FRAGMENT_SRC = `
    precision mediump float;
    varying vec3 vNormal;
    varying vec3 vColor;
    uniform float uAlpha;
    const vec3 KEY_LIGHT = vec3(${KEY_LIGHT.join(", ")});
    const vec3 FILL_LIGHT = vec3(${FILL_LIGHT.join(", ")});
    void main() {
      vec3 n = normalize(vNormal);
      if (!gl_FrontFacing) n = -n;
      float key = max(0.0, dot(n, KEY_LIGHT));
      float fill = max(0.0, dot(n, FILL_LIGHT));
      float light = 0.46 + 0.46 * key + 0.13 * fill + 0.12 * n.z;
      light = clamp(light, 0.42, 1.2);
      gl_FragColor = vec4(vColor * light, uAlpha);
    }
  `;

  // A preview face's own corner count decides how it is turned into
  // triangles: mesh-derived faces already arrive as triangles (3 corners),
  // and the hand-built rectangular wall/rim faces are always convex, but the
  // wavy cavity floor and label-glyph outlines are neither triangles nor
  // reliably convex. A GPU triangle fan gets those wrong, so anything with
  // more than 3 corners goes through ear-clipping in the face's own plane.
  function triangulatePolygon(points, normal) {
    const n = points.length;
    if (n < 3) return [];
    if (n === 3) return [[0, 1, 2]];
    let [nx, ny, nz] = normal;
    const nlen = Math.hypot(nx, ny, nz) || 1;
    nx /= nlen; ny /= nlen; nz /= nlen;
    let hx = 0, hy = 0, hz = 1;
    if (Math.abs(nz) > 0.9) { hx = 1; hy = 0; hz = 0; }
    let ux = hy * nz - hz * ny, uy = hz * nx - hx * nz, uz = hx * ny - hy * nx;
    const ulen = Math.hypot(ux, uy, uz) || 1;
    ux /= ulen; uy /= ulen; uz /= ulen;
    const vx = ny * uz - nz * uy, vy = nz * ux - nx * uz, vz = nx * uy - ny * ux;
    const pts2 = new Array(n);
    for (let i = 0; i < n; i += 1) {
      const p = points[i];
      pts2[i] = [p[0] * ux + p[1] * uy + p[2] * uz, p[0] * vx + p[1] * vy + p[2] * vz];
    }
    let area2 = 0;
    for (let i = 0; i < n; i += 1) {
      const a = pts2[i], b = pts2[(i + 1) % n];
      area2 += a[0] * b[1] - b[0] * a[1];
    }
    const ccw = area2 > 0;
    const cross2 = (ox, oy, ax, ay, bx, by) => (ax - ox) * (by - oy) - (ay - oy) * (bx - ox);
    const pointInTri = (px, py, ax, ay, bx, by, cx, cy) => {
      const d1 = cross2(ax, ay, bx, by, px, py);
      const d2 = cross2(bx, by, cx, cy, px, py);
      const d3 = cross2(cx, cy, ax, ay, px, py);
      const hasNeg = d1 < 0 || d2 < 0 || d3 < 0;
      const hasPos = d1 > 0 || d2 > 0 || d3 > 0;
      return !(hasNeg && hasPos);
    };
    const indices = [];
    for (let i = 0; i < n; i += 1) indices.push(i);
    const triangles = [];
    let guard = 0;
    while (indices.length > 3 && guard++ < n * n + 8) {
      let earFound = false;
      for (let i = 0; i < indices.length; i += 1) {
        const i0 = indices[(i - 1 + indices.length) % indices.length];
        const i1 = indices[i];
        const i2 = indices[(i + 1) % indices.length];
        const [ax, ay] = pts2[i0], [bx, by] = pts2[i1], [cx, cy] = pts2[i2];
        const cr = cross2(ax, ay, bx, by, cx, cy);
        const convex = ccw ? cr > 1e-9 : cr < -1e-9;
        if (!convex) continue;
        let contains = false;
        for (let k = 0; k < indices.length; k += 1) {
          const idx = indices[k];
          if (idx === i0 || idx === i1 || idx === i2) continue;
          const [px, py] = pts2[idx];
          if (pointInTri(px, py, ax, ay, bx, by, cx, cy)) { contains = true; break; }
        }
        if (contains) continue;
        triangles.push([i0, i1, i2]);
        indices.splice(i, 1);
        earFound = true;
        break;
      }
      if (!earFound) {
        // Degenerate/self-intersecting input: fan it rather than drop it -
        // the same imperfect result the old painter would have shown.
        for (let i = 1; i < indices.length - 1; i += 1) {
          triangles.push([indices[0], indices[i], indices[i + 1]]);
        }
        indices.length = 0;
        break;
      }
    }
    if (indices.length === 3) triangles.push([indices[0], indices[1], indices[2]]);
    return triangles;
  }

  function compileShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const info = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error("shader compile failed: " + info);
    }
    return shader;
  }

  function init(canvas) {
    let gl = null;
    try {
      gl = canvas.getContext("webgl2", { antialias: true, alpha: true, depth: true })
        || canvas.getContext("webgl", { antialias: true, alpha: true, depth: true })
        || canvas.getContext("experimental-webgl", { antialias: true, alpha: true, depth: true });
    } catch (error) {
      gl = null;
    }
    if (!gl) return null;
    let program;
    try {
      const vertexShader = compileShader(gl, gl.VERTEX_SHADER, VERTEX_SRC);
      const fragmentShader = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SRC);
      program = gl.createProgram();
      gl.attachShader(program, vertexShader);
      gl.attachShader(program, fragmentShader);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error("program link failed: " + gl.getProgramInfoLog(program));
      }
    } catch (error) {
      return null;
    }
    const renderer = {
      canvas, gl, program,
      attribs: {
        position: gl.getAttribLocation(program, "aPosition"),
        normal: gl.getAttribLocation(program, "aNormal"),
        color: gl.getAttribLocation(program, "aColor"),
      },
      uniforms: {
        right: gl.getUniformLocation(program, "uRight"),
        up: gl.getUniformLocation(program, "uUp"),
        forward: gl.getUniformLocation(program, "uForward"),
        mid: gl.getUniformLocation(program, "uMid"),
        scale: gl.getUniformLocation(program, "uScale"),
        halfSize: gl.getUniformLocation(program, "uHalfSize"),
        nearCam: gl.getUniformLocation(program, "uNearCam"),
        farCam: gl.getUniformLocation(program, "uFarCam"),
        alpha: gl.getUniformLocation(program, "uAlpha"),
      },
      lost: false,
    };
    canvas.addEventListener("webglcontextlost", event => {
      event.preventDefault();
      renderer.lost = true;
    });
    canvas.addEventListener("webglcontextrestored", () => {
      renderer.lost = false;
    });
    return renderer;
  }

  // Builds one interleaved GPU buffer per named group (exactly two groups:
  // ["bin","interior"] for an ordinary bin, ["base","lid"] for B4B).
  // `classify(face)` returns which group a face belongs to, or a falsy value
  // to drop it (annotation-only faces such as bore axes should already be
  // filtered out by the caller). Rebuilding this is the only geometry-change
  // cost; camera/mode changes never call it again.
  function buildBuffers(gl, geometry, groupNames, classify, kindColor) {
    const LAYER_EPSILON = 0.01; // mm - see the "layer" field's docstring
    const raw = new Map(groupNames.map(name => [name, { positions: [], normals: [], colors: [] }]));
    const aabb = new Map(groupNames.map(name => [name, {
      min: [Infinity, Infinity, Infinity], max: [-Infinity, -Infinity, -Infinity],
    }]));
    const colorCache = new Map();
    for (const face of geometry) {
      const group = classify(face);
      if (!raw.has(group)) continue;
      const bucket = raw.get(group);
      const box = aabb.get(group);
      let hex = colorCache.get(face.kind);
      if (!hex) { hex = kindColor(face.kind); colorCache.set(face.kind, hex); }
      const r = parseInt(hex.slice(1, 3), 16) / 255;
      const g = parseInt(hex.slice(3, 5), 16) / 255;
      const b = parseInt(hex.slice(5, 7), 16) / 255;
      const normal = face.normal;
      const [nx, ny, nz] = normal;
      const bias = (face.layer || 0) * LAYER_EPSILON;
      const points = face.points;
      const tris = points.length === 3 ? [[0, 1, 2]] : triangulatePolygon(points, normal);
      for (const tri of tris) {
        for (const idx of tri) {
          const p = points[idx];
          const px = p[0] + nx * bias, py = p[1] + ny * bias, pz = p[2] + nz * bias;
          bucket.positions.push(px, py, pz);
          bucket.normals.push(nx, ny, nz);
          bucket.colors.push(r, g, b);
          if (px < box.min[0]) box.min[0] = px; if (px > box.max[0]) box.max[0] = px;
          if (py < box.min[1]) box.min[1] = py; if (py > box.max[1]) box.max[1] = py;
          if (pz < box.min[2]) box.min[2] = pz; if (pz > box.max[2]) box.max[2] = pz;
        }
      }
    }
    const groups = {};
    const allMin = [Infinity, Infinity, Infinity], allMax = [-Infinity, -Infinity, -Infinity];
    for (const name of groupNames) {
      const bucket = raw.get(name);
      const vertexCount = bucket.positions.length / 3;
      const buffer = gl.createBuffer();
      const interleaved = new Float32Array(vertexCount * 9);
      for (let i = 0; i < vertexCount; i += 1) {
        interleaved[i * 9 + 0] = bucket.positions[i * 3 + 0];
        interleaved[i * 9 + 1] = bucket.positions[i * 3 + 1];
        interleaved[i * 9 + 2] = bucket.positions[i * 3 + 2];
        interleaved[i * 9 + 3] = bucket.normals[i * 3 + 0];
        interleaved[i * 9 + 4] = bucket.normals[i * 3 + 1];
        interleaved[i * 9 + 5] = bucket.normals[i * 3 + 2];
        interleaved[i * 9 + 6] = bucket.colors[i * 3 + 0];
        interleaved[i * 9 + 7] = bucket.colors[i * 3 + 1];
        interleaved[i * 9 + 8] = bucket.colors[i * 3 + 2];
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, interleaved, gl.STATIC_DRAW);
      const box = aabb.get(name);
      const empty = vertexCount === 0;
      groups[name] = {
        buffer, vertexCount,
        aabb: empty ? null : box,
      };
      if (!empty) {
        for (let axis = 0; axis < 3; axis += 1) {
          if (box.min[axis] < allMin[axis]) allMin[axis] = box.min[axis];
          if (box.max[axis] > allMax[axis]) allMax[axis] = box.max[axis];
        }
      }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
    const allAabb = allMin[0] === Infinity ? null : { min: allMin, max: allMax };
    return { groups, allAabb };
  }

  function disposeBuffers(gl, buffers) {
    if (!buffers) return;
    for (const name of Object.keys(buffers.groups)) {
      gl.deleteBuffer(buffers.groups[name].buffer);
    }
  }

  // Camera-frame math shared with the 2D overlay: `iso(point, camera)` there
  // is exactly [dot(point, right), dot(point, up)], so the overlay's
  // dimension guides / bore axes / usable-floor rectangle line up
  // pixel-for-pixel with what this function frames for the solid pass.
  function computeFrame(camera, aabb, width, height) {
    const yaw = camera.yaw * Math.PI / 180;
    const elevation = camera.elevation * Math.PI / 180;
    const cosYaw = Math.cos(yaw), sinYaw = Math.sin(yaw);
    const cosEl = Math.cos(elevation), sinEl = Math.sin(elevation);
    const right = [cosYaw, -sinYaw, 0];
    const up = [-sinYaw * sinEl, -cosYaw * sinEl, -cosEl];
    const forward = [-sinYaw * cosEl, -cosYaw * cosEl, sinEl];
    if (!aabb) {
      return { right, up, forward, scale: 1, midX: 0, midY: 0, nearCam: 1, farCam: -1 };
    }
    const { min, max } = aabb;
    let minVX = Infinity, maxVX = -Infinity, minVY = Infinity, maxVY = -Infinity;
    let minVF = Infinity, maxVF = -Infinity;
    for (const x of [min[0], max[0]]) {
      for (const y of [min[1], max[1]]) {
        for (const z of [min[2], max[2]]) {
          const vx = x * right[0] + y * right[1] + z * right[2];
          const vy = x * up[0] + y * up[1] + z * up[2];
          const vf = x * forward[0] + y * forward[1] + z * forward[2];
          if (vx < minVX) minVX = vx; if (vx > maxVX) maxVX = vx;
          if (vy < minVY) minVY = vy; if (vy > maxVY) maxVY = vy;
          if (vf < minVF) minVF = vf; if (vf > maxVF) maxVF = vf;
        }
      }
    }
    const spanX = Math.max(1e-6, maxVX - minVX);
    const spanY = Math.max(1e-6, maxVY - minVY);
    const scale = Math.min((width * 0.75) / spanX, (height * 0.75) / spanY) * camera.zoom;
    const pad = Math.max(1e-3, (maxVF - minVF) * 0.05 + 1e-3);
    return {
      right, up, forward, scale,
      midX: (minVX + maxVX) / 2, midY: (minVY + maxVY) / 2,
      nearCam: maxVF + pad, farCam: minVF - pad,
    };
  }

  // `passes` is an array of { group, alpha } drawn in order - opaque passes
  // first (depth write on), any translucent pass (alpha < 1) last (depth
  // write off, blended), so a translucent Xray shell never hides the opaque
  // interior drawn under it.
  function draw(renderer, buffers, frame, width, height, passes) {
    const { gl, program, attribs, uniforms } = renderer;
    const ratio = Math.min(2, window.devicePixelRatio || 1);
    const pixelWidth = Math.max(1, Math.round(width * ratio));
    const pixelHeight = Math.max(1, Math.round(height * ratio));
    if (renderer.canvas.width !== pixelWidth || renderer.canvas.height !== pixelHeight) {
      renderer.canvas.width = pixelWidth;
      renderer.canvas.height = pixelHeight;
    }
    gl.viewport(0, 0, pixelWidth, pixelHeight);
    gl.clearColor(0, 0, 0, 0);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);
    gl.disable(gl.CULL_FACE);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    if (!buffers) return;
    gl.useProgram(program);
    gl.uniform3fv(uniforms.right, frame.right);
    gl.uniform3fv(uniforms.up, frame.up);
    gl.uniform3fv(uniforms.forward, frame.forward);
    gl.uniform2f(uniforms.mid, frame.midX, frame.midY);
    gl.uniform1f(uniforms.scale, frame.scale);
    gl.uniform2f(uniforms.halfSize, width / 2, height / 2);
    gl.uniform1f(uniforms.nearCam, frame.nearCam);
    gl.uniform1f(uniforms.farCam, frame.farCam);
    const stride = 9 * 4;
    for (const pass of passes) {
      const group = buffers.groups[pass.group];
      if (!group || !group.vertexCount) continue;
      const translucent = (pass.alpha ?? 1) < 1;
      gl.depthMask(!translucent);
      if (translucent) {
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      } else {
        gl.disable(gl.BLEND);
      }
      gl.uniform1f(uniforms.alpha, pass.alpha ?? 1);
      gl.bindBuffer(gl.ARRAY_BUFFER, group.buffer);
      gl.enableVertexAttribArray(attribs.position);
      gl.vertexAttribPointer(attribs.position, 3, gl.FLOAT, false, stride, 0);
      gl.enableVertexAttribArray(attribs.normal);
      gl.vertexAttribPointer(attribs.normal, 3, gl.FLOAT, false, stride, 12);
      gl.enableVertexAttribArray(attribs.color);
      gl.vertexAttribPointer(attribs.color, 3, gl.FLOAT, false, stride, 24);
      gl.drawArrays(gl.TRIANGLES, 0, group.vertexCount);
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, null);
  }

  window.Preview3DGL = { init, buildBuffers, disposeBuffers, computeFrame, draw, triangulatePolygon };
})();
