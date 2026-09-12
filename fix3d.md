# fix3d.md — Generic Wavefinity 3D Preview Improvement Plan

## Objective

Replace the current Wavefinity 3D preview approach with one correct, lightweight renderer for **all 3D models**, including ordinary bins, interiors, inserts, stacking systems, and B4B.

Fix:

- geometry incorrectly showing through other geometry;
- floors/interiors painting through side walls;
- diagonal triangulation/fan lines;
- walls appearing caved, folded, or distorted;
- broken/dashed-looking edges;
- unstable depth ordering while rotating;
- unnecessary CPU cost during camera movement.

Target: a clean, responsive, functional engineering view. No photorealism and no CAD redesign.

## 1. Replace the shared 2D software painter with WebGL

Create one shared WebGL/WebGL2 renderer for Wavefinity 3D previews.

Required:

- use the existing 3D canvas;
- enable depth testing and depth writes;
- render normal solid geometry opaque;
- clear color and depth buffers each redraw;
- use orthographic projection consistent with the current preview;
- redraw only when geometry, camera, visibility mode, or canvas size changes;
- no continuous animation loop.

All Wavefinity 3D geometry should use this renderer.

## 2. Do not use back-face culling initially

Do not reproduce the current manual face-culling behavior.

Initially:

- render both sides of faces;
- rely on the depth buffer for visibility;
- do not enable GPU `CULL_FACE`.

Back-face culling can be considered later only if mesh winding is proven reliable and it provides a worthwhile performance gain.

## 3. Remove visible triangle/face seams

Do not draw individual mesh triangle boundaries.

Remove from solid rendering:

- fill-matching face strokes;
- dark contrast triangle strokes;
- wireframe-like seams created by tessellation.

Flat and curved surfaces should visually read as surfaces rather than collections of triangles.

## 4. Use simple functional lighting

Use inexpensive lighting only to make geometry readable:

- one directional light;
- ambient light;
- existing geometry normals;
- simple diffuse/Lambert shading;
- current Wavefinity part colors or equivalent muted colors.

Do not add:

- PBR;
- reflections;
- textures;
- environment maps;
- shadow maps;
- SSAO;
- bloom;
- post-processing;
- photo/render-quality modes.

## 5. Standardize preview geometry around mesh groups

Move the 3D preview toward mesh-oriented data instead of individual JavaScript face objects.

Recommended conceptual structure:

```text
meshes: [
  {
    kind: "outside",
    group: "bin",
    positions: [...],
    normals: [...]
  },
  {
    kind: "feature_divider",
    group: "interior",
    positions: [...],
    normals: [...]
  }
]
```

Use flat numeric arrays suitable for direct conversion into typed GPU buffers.

Preserve semantic information needed for visibility modes and coloring.

Do not change printable/export geometry.

## 6. Cache GPU buffers

Upload geometry only when the design geometry changes.

Reuse those buffers for:

- drag rotation;
- spin/tilt;
- Top/Front/Side/Reset;
- zoom;
- preview-mode changes;
- canvas resizing.

Camera interaction must not rebuild Python geometry.

## 7. Preserve ordinary-bin visibility modes

Ordinary bins keep:

- Standard
- Xray
- Bin
- Interior

Implement those modes on top of the new renderer rather than through painter-order tricks.

### Standard

Render all applicable geometry normally with depth testing.

### Bin

Render only bin-owned geometry.

### Interior

Render only interior/support geometry.

### Xray

Preserve the useful intent of Xray, but implement it explicitly.

Do not simulate Xray by deleting whichever wall triangles approximately face the camera.

Use a deterministic visibility/material approach that produces a stable view.

Keep Xray lightweight; no advanced transparency system is required.

## 8. Keep B4B-specific All / Base / Lid controls

B4B remains the UI exception because its useful view semantics differ from an ordinary bin.

For B4B show:

- All
- Base
- Lid

Do not show Standard/Xray/Bin/Interior for B4B.

B4B geometry must have explicit physical ownership:

```text
owner: "base"
owner: "lid"
```

Switching All/Base/Lid must be frontend-only and reuse loaded GPU buffers.

## 9. Use stable geometry bounds for framing

Maintain bounds for the relevant logical geometry groups rather than deriving bounds from currently visible/front-facing triangles.

For ordinary bins, maintain appropriate bounds for:

- full model;
- bin;
- interior.

For B4B:

- full assembly;
- base;
- lid.

Rotation must not make the model visibly change scale.

Switching visibility modes should frame the geometry actually being shown.

## 10. Preserve existing camera behavior

Keep:

- pointer drag;
- wheel zoom;
- Top;
- Front;
- Side;
- Reset;
- left/right spin;
- up/down tilt.

Reuse current camera state and orientation conventions where practical.

The renderer changes; the user interaction model does not.

## 11. Correct dimension overlays

Dimension guides must correspond to the physical geometry they visually bracket.

### Ordinary bins

Continue using the appropriate physical bin width/depth/height.

### B4B

Do not use child-field X/Y values as though they are the physical case exterior.

Use the authoritative physical case/envelope dimensions already available from B4B calculations.

Keep child-bin capacity information in the B4B information readout.

## 12. Keep annotations outside solid rendering

Use WebGL for solid 3D geometry.

Keep appropriate UI overlays such as:

- dimension lines;
- labels/help overlays;
- bore direction annotations;

in an overlay/DOM/2D layer where practical.

Do not put solid model rendering back through the 2D painter.

## 13. Optimize transport where it matters

The shared renderer should support compact mesh buffers.

B4B should definitely use the compact representation because of its very high triangle counts.

Ordinary geometry may migrate to the same format at the same time if straightforward.

Do not build two long-term rendering architectures.

The desired end state is:

```text
Python geometry
      ↓
compact preview meshes
      ↓
shared WebGL renderer
```

## 14. Do not use geometry simplification as the fix

Do not initially:

- decimate meshes;
- reduce wave detail;
- simplify B4B hardware;
- change lid tessellation;
- alter ordinary-bin geometry;
- modify STL/3MF output.

Fix rendering correctness first.

Preview-only simplification can be considered later only if measured initial-load performance still requires it.

## 15. Preserve fallback behavior

If WebGL cannot initialize:

- fall back to the existing canvas renderer;
- do not block design work;
- do not block export or printing.

The old renderer becomes fallback only, not a second actively developed 3D system.

## 16. Files expected to change

Primary:

```text
web/app.js
web/index.html
wavefinity_web.py
organizer_app.py
organizer_b4b.py
```

Recommended new shared renderer:

```text
web/preview3d-webgl.js
```

Possible small support change:

```text
web/styles.css
```

Do not modify mechanical/CAD geometry merely to improve the viewer.

## 17. Execution order

1. Add one shared WebGL preview renderer.
2. Route ordinary-bin geometry through it.
3. Route B4B geometry through the same renderer.
4. Enable depth testing and opaque rendering.
5. Remove triangle/face-edge drawing.
6. Add simple directional + ambient lighting.
7. Match existing camera behavior.
8. Implement ordinary Standard/Bin/Interior visibility in the new renderer.
9. Implement a stable Xray mode without camera-facing triangle deletion.
10. Add/retain explicit B4B Base/Lid ownership.
11. Implement B4B All/Base/Lid on the shared renderer.
12. Add stable per-view bounds/framing.
13. Correct dimension-overlay inputs.
14. Move B4B to compact mesh transport.
15. Move ordinary geometry to the same compact transport where straightforward.
16. Cache and reuse GPU buffers until geometry actually changes.
17. Leave CAD/export geometry otherwise untouched.

**Execution model:** Middle  
**Thinking:** Medium
