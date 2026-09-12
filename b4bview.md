# B4B 3D Viewer Redesign Plan

## Purpose

Fix the B4B 3D preview so it is fast enough to manipulate, visually solid rather than apparently see-through, and presents controls that make sense for a carrying case.

This is implementation guidance for an LLM. It is **not** a request to redesign B4B geometry or export geometry. The generated B4B files remain authoritative. The work here is preview/rendering/UI only unless a preview-specific data contract must be added.

## Product decision

For B4B, replace the current `Standard / Xray / Bin / Interior` buttons with exactly three mutually exclusive view buttons:

- **All** — complete assembled B4B case, closed, including base/body, lid, latches, hinges, handle, stacking details and labels that are part of the preview.
- **Base** — base/body and everything physically owned by the base/body.
- **Lid** — lid and everything physically owned by the lid.

Exactly one is active at a time. Default to **All** when entering B4B.

Do **not** remove or change the existing `Standard / Xray / Bin / Interior` controls for ordinary bins unless a small shared-renderer change requires it. Their current behavior can remain for non-B4B designs.

Do not add an explode view, transparency slider, photo renderer, animation mode, or additional B4B view controls as part of this work.

---

# Current-code findings

## 1. HIGH: Current preview mode controls do not classify B4B geometry

`web/app.js` currently defines an `isBinFace(kind)` check inside the 3D painter. It recognizes ordinary-bin kinds such as:

- `outside`
- `inside`
- `rim`
- `floor`
- `top_label_ledge`
- `label`
- `label_hole`

B4B preview geometry instead arrives as kinds such as `b4b_body`, `b4b_lid`, `b4b_latch`, `b4b_handle`, `b4b_stack`, and possible metadata-qualified B4B kinds.

The existing mode logic is therefore not meaningful for B4B:

```js
if (mode === "bin" && !isBin) continue;
if (mode === "interior" && isBin) continue;
if (mode === "xray" && isBin && isFacingSide(face)) continue;
```

For B4B, `isBin` is normally false. That explains why the controls appear ineffective or behave nonsensically.

### Required correction

Do not patch `isBinFace()` by simply declaring every `b4b_*` face to be an ordinary bin face. That would preserve the wrong product model.

Give B4B its own view state and its own three-button UI: `all`, `base`, `lid`.

## 2. HIGH: The B4B renderer is CPU-bound by software triangle painting

The code already documents the problem accurately:

- a B4B case can be well over 100,000 triangles;
- `_mesh_preview_geometry()` converts finished meshes into individual preview faces;
- `drawGeometry()` then loops those faces in JavaScript;
- on every spin/tilt it culls, projects, depth-sorts and paints the visible triangles using the 2D canvas API.

Backend `lru_cache` in `_b4b_preview_geometry()` helps repeated geometry builds, but it cannot make camera movement fast because rotation still repaints the triangle set in JavaScript.

### Required correction

Do not try to solve this only with more micro-optimizations to the current face loop. The current architecture has reached the wrong side of the cost curve for B4B.

Use a GPU depth-buffered path for B4B preview rendering.

## 3. HIGH: The apparent transparency is a depth-ordering limitation, not a desired material effect

The current canvas renderer uses a painter-style sort:

```js
faces.sort((a, b) => a.depth - b.depth || a.layer - b.layer)
```

That orders triangles by a single depth value. It cannot reliably resolve all overlap/intersection cases across a complex case containing body, lid, hinges, latches, handle, labels and stacking geometry. A triangle or component can therefore paint over something that is actually in front of it, creating a see-through/broken-surface appearance.

There is no reason for the normal B4B view to be transparent.

### Required correction

B4B rendering must use a real depth buffer. All normal B4B surfaces are opaque.

---

# Recommended implementation

## Phase 1 — separate B4B view semantics from ordinary-bin preview modes

### `web/index.html`

Keep the existing ordinary mode control group, but add a B4B-specific group in the same location:

- `All`
- `Base`
- `Lid`

Only one group is visible at a time.

Recommended structure:

- existing ordinary group gets an identifying container such as `#ordinary-preview-modes`;
- new B4B group gets `#b4b-preview-modes`;
- B4B buttons use `data-b4b-view="all|base|lid"`, not `data-camera-mode`.

Do not overload `data-camera-mode` with two unrelated meanings.

### `web/app.js`

Add session state separate from ordinary preview state:

```js
b4bView: "all"
```

Add a small setter such as `setB4BView(view)` that:

1. validates `all/base/lid`;
2. stores `state.b4bView`;
3. updates the active button and `aria-pressed`/selected state;
4. redraws from already-loaded geometry;
5. does **not** call the backend just because the user switches All/Base/Lid.

`applyB4BVisibility()` already centralizes B4B-specific UI visibility. Extend it so:

- B4B enabled -> hide ordinary preview modes, show B4B view controls;
- B4B disabled -> show ordinary preview modes, hide B4B view controls;
- entering B4B with invalid/missing state -> use `all`.

Do not allow multiple B4B buttons to appear active.

## Phase 2 — give preview geometry explicit physical ownership

Do not make the browser guess whether a B4B triangle belongs to the base or lid from color names or substring matching.

The backend already knows which source mesh it is converting in `organizer_b4b._b4b_preview_geometry()`:

- `b4b_body_with_features(box)` -> base group
- `make_b4b_front_label_plate(box)` -> base group
- `make_b4b_lid(box)` -> lid group
- top-label inlay -> lid group
- `make_b4b_handle(box)` -> base group
- `make_b4b_latches(box)` -> lid group because the latch levers are lid-mounted moving parts
- base-side latch catches/hinge roots already fused into the body stay base because they originate from the body mesh
- lid-side hinge/root geometry fused into the lid stays lid because it originates from the lid mesh
- `_stack_pegs(box)` -> assign according to their actual owning printed part; current standalone preview pegs should normally be base if they are body features. Verify this against the actual generated part before hard-coding.

Add an explicit preview-only `group`/`owner` field (`base` or `lid`) to the B4B preview bundle.

The distinction is physical ownership, not visual color and not hardware type.

### View rules

- `all`: render both groups
- `base`: render only `base`
- `lid`: render only `lid`

The view filter must happen before camera bounds/framing are calculated so Base and Lid each fill the preview instead of being framed against invisible geometry.

## Phase 3 — move B4B 3D drawing to WebGL with a real Z-buffer

### Preferred architecture

Add a small dedicated renderer module, for example:

- `web/b4b-view.js` or
- `web/preview3d-webgl.js`

Use native WebGL/WebGL2 rather than pulling a rendering framework from a CDN. Wavefinity should remain usable locally/offline and this requirement does not need a full scene framework.

The renderer only needs:

- positions
- normals
- one color/material id per preview mesh/part
- model/view/projection matrix
- depth testing
- simple directional + ambient lighting

No texture system, physically based materials, post-processing, shadow maps or continuous animation loop is required.

### Required WebGL behavior

- request an antialiased WebGL context;
- enable depth testing;
- clear color and depth buffers each redraw;
- render all normal B4B materials fully opaque;
- use existing B4B color family or a visually equivalent muted palette;
- use simple Lambert-style directional lighting plus ambient light so curved/chamfered surfaces read clearly;
- cap effective device-pixel-ratio if necessary (for example 1.5-2) so high-DPI displays do not multiply GPU cost for no meaningful preview benefit;
- redraw on design change, view change, resize and camera interaction only;
- do **not** run an idle 60 fps animation loop.

### Back-face handling

Depth testing is mandatory. Back-face culling is optional until mesh winding is confirmed reliable across every boolean-generated B4B mesh.

Safer sequence:

1. first ship depth-tested opaque rendering without relying on culling;
2. verify body/lid/hardware meshes have consistent winding;
3. enable culling only if it measurably improves performance and does not create holes.

Do not trade the present see-through defect for missing faces caused by aggressive culling.

### Fallback

If WebGL context creation fails, retain the current canvas renderer as a fallback and show the B4B through that path. Do not block design/export because 3D acceleration is unavailable.

## Phase 4 — stop shipping B4B as hundreds of thousands of JavaScript face objects

Even with WebGL, the initial B4B preview should not continue indefinitely with one JSON object per triangle if that remains a meaningful build/load delay.

Create a B4B-specific compact preview contract while leaving ordinary-bin preview payloads alone.

Recommended payload shape conceptually:

```text
b4b_meshes: [
  {
    owner: "base" | "lid",
    kind: "b4b_body" | "b4b_lid" | ...,
    positions: [x,y,z, x,y,z, ...],
    normals: [nx,ny,nz, nx,ny,nz, ...],
    ...
  }
]
```

Use flat numeric arrays rather than per-face dictionaries containing repeated field names.

It is acceptable to duplicate triangle vertices for flat shading. The first goal is dramatically less JavaScript object allocation/iteration and direct upload into typed WebGL buffers.

Keep the existing micron-level coordinate rounding or equivalent preview quantization; export geometry is unaffected.

Cache the compact B4B preview representation using the existing design-key cache strategy so camera/view changes never rebuild it.

### Do not add mesh decimation first

Do not introduce lossy geometry simplification as the first fix. The current problem can be solved more cleanly by GPU rendering, depth buffering and a compact transport format. If a representative very large case remains slow to *build* after those changes, preview-only mesh simplification can be considered later as a separate measured optimization.

## Phase 5 — keep camera interaction lightweight

Existing camera controls should continue to work:

- Top
- Front
- Side
- Reset
- zoom
- spin/tilt

For the WebGL B4B path:

- cache GPU buffers until preview geometry changes;
- camera movement should update uniforms/matrices and redraw only;
- All/Base/Lid should toggle mesh-group visibility and redraw only;
- no API request on spin, tilt, zoom, preset view, or All/Base/Lid switch;
- no re-triangulation on camera changes.

When switching `Base` or `Lid`, compute/use bounds for the visible group so the selected part is centered and sensibly scaled.

When returning to `All`, restore assembly bounds without unexpectedly resetting yaw/elevation unless the existing app already does so for comparable view changes.

---

# Visual-quality acceptance criteria

The B4B 3D preview is successful when:

1. The lid/base are visually opaque; surfaces behind them do not paint through them.
2. Hinges, latch parts, handle and labels respect real front/back depth ordering.
3. Internal triangulation is not visually emphasized as a wireframe.
4. Curves/chamfers are readable from lighting without expensive photoreal rendering.
5. The model remains visually stable while rotating; no triangle-order flickering.
6. `All` clearly shows the complete assembled case.
7. `Base` clearly shows only the body/base-owned geometry.
8. `Lid` clearly shows only lid-owned geometry.
9. Exactly one B4B view button is active.
10. Ordinary bins retain their existing ordinary preview-mode controls.

---

# Performance acceptance criteria

Do not create a giant benchmark suite. Use one representative ordinary B4B and one deliberately large/complex B4B as focused manual/dev checks.

Required behavior:

- Rotation/tilt/zoom must not cause a backend request.
- All/Base/Lid switches must not cause a backend request.
- Camera interaction should feel immediate rather than repainting a six-figure triangle list in JS.
- No per-frame sort of every B4B triangle.
- No continuous animation loop while the user is idle.
- A cached unchanged B4B design should reuse preview geometry/buffers.
- Ordinary-bin responsiveness must not regress.

If timing instrumentation is added, keep it development-only or remove it after verification.

---

# Focused validation only

Per project direction, do not respond to this viewer change by running or adding broad unrelated test suites.

Add/modify only focused tests/checks needed to protect the new behavior:

1. frontend/static contract check that B4B has `All/Base/Lid` controls and ordinary modes still exist;
2. backend preview test confirming B4B geometry bundles contain explicit `base`/`lid` ownership and neither group is empty for a normal latched case;
3. backend test confirming a lid label belongs to `lid` and a front/body label belongs to `base`;
4. if payload format changes, one contract test for its compact shape;
5. manual visual check of one normal and one complex B4B for depth correctness and interaction speed.

Do not add screenshot testing, randomized geometry testing, or broad performance infrastructure for this task.

---

# Files expected to change

Primary:

- `web/index.html`
- `web/app.js`
- `organizer_b4b.py`
- `wavefinity_web.py`

Likely new:

- `web/b4b-view.js` or `web/preview3d-webgl.js`

Possible small supporting changes:

- `web/styles.css`
- `test_wavefinity_web.py`

Avoid changing B4B export geometry builders merely to make the preview easier to render.

---

# Implementation order

1. Add B4B-specific All/Base/Lid UI/state without changing geometry.
2. Add explicit base/lid ownership to B4B preview data.
3. Implement WebGL B4B renderer using current geometry semantics and depth testing.
4. Make camera/view changes reuse GPU buffers.
5. Compact the B4B preview transport into mesh bundles/flat arrays if the initial preview load remains materially slow; this is recommended and should normally be completed in this work because the current one-object-per-face payload is unnecessarily expensive.
6. Verify normal and large B4B cases manually.
7. Run only the focused contract tests affected by the change.
8. Final review against every acceptance criterion below.

---

# Final gap review checklist

Before declaring the work complete, explicitly verify:

- [ ] B4B shows only `All / Base / Lid`, not `Standard / Xray / Bin / Interior`.
- [ ] Ordinary bins still show their ordinary preview controls.
- [ ] Exactly one B4B view is active.
- [ ] `All` includes both physical groups.
- [ ] `Base` excludes every lid-owned moving/printed component.
- [ ] `Lid` excludes every base-owned component.
- [ ] Top lid label follows the lid; front/body label follows the base.
- [ ] Latch levers are assigned to the part they physically mount to.
- [ ] Hinge geometry follows source-part ownership rather than a generic `hinge` category.
- [ ] No normal B4B material is intentionally translucent.
- [ ] A real depth buffer prevents rear surfaces/components from drawing through front surfaces.
- [ ] No full-triangle depth sort occurs on every B4B camera movement.
- [ ] Camera changes do not call the backend.
- [ ] All/Base/Lid changes do not call the backend.
- [ ] GPU/preview buffers are reused until design geometry changes.
- [ ] Base and Lid views frame the visible part rather than the hidden full assembly.
- [ ] WebGL failure has a functional fallback and does not prevent export.
- [ ] B4B export STL/3MF geometry has not been altered by preview-only optimization.
- [ ] Normal B4B and large/complex B4B both look solid and manipulate smoothly.
- [ ] No unrelated test/refactor work was added.

## Recommended implementation stance

Treat this as a renderer/UI correction, not a B4B geometry redesign. The current B4B preview is asking a 2D software painter to behave like a real 3D renderer. The clean fix is to give B4B a depth-buffered GPU preview and a B4B-specific three-state visibility model, while preserving the existing geometry/export pipeline.