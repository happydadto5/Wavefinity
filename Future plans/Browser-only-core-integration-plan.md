# Wavefinity browser-only core integration and experiment retirement

**Status:** Implementation plan; NOT yet implemented.  
**Owner direction:** No installation for site visitors. Desktop Chrome and Edge on Windows are the target. Do not create a separate application or new hosting service while integrating. No feature branches/worktrees; land safely on `main` with fresh remote checks.  
**Goal:** Serve Wavefinity as static site assets while the visitor's own PC performs all geometry and file generation. Retain `wavefinity.org` regardless of host.  
**Evidence:** Story 2979 established a browser-only experimental runner. Direct local implementation pushed as `f25fee144d556a819a80eec6a89313603ce0460b` built 42x42x28 and 84x42x28 ordinary bins in Linux Chromium with the custom Manifold MeshGL64 WASM bridge. Geometry comparison and network-blocked builds passed according to its reported test results; Andrew manually confirmed the experiment generated printable STLs in Windows Chrome and Edge on 2026-11-12. This does **not** yet mean the core application works without the Python server.

## Non-negotiable invariants

1. One canonical geometry implementation: reuse Wavefinity's real engine and its 64-bit Boolean path; no parallel lower-fidelity model or float32 silent fallback. Retain existing 7 mm Wavefinity, 21/42 mm Gridfinity, and all precise fit/clearance rules.
2. No installed Python, local server, native application, browser extension, or helper is required of visitors. Use browser worker(s), WebAssembly and browser APIs only.
3. Keep the existing application UI and its saved-design semantics. Preserve exports, parts, printer profiles and space workflows; do not call a static-host migration complete with core controls broken or silently disabled.
4. No cloud geometry/API processing from the static build. A feature that genuinely needs external services (e.g. AI) must be explicitly separated and labeled, not represented as local. Never expose server secrets or provider keys in the static bundle.
5. Keep the current Render-hosted app available during integration, using opt-in browser execution, until the full acceptance suite is green.
6. No feature branches, Git worktrees, force pushes, or rewriting shared history. Before each direct-main publication fetch and safely reconcile any new origin/main changes; keep unrelated in-progress Stories intact.
7. Do not delete the browser experiment or its reference artifacts until the production implementation has replaced their useful validation coverage.

## Current code boundaries

- Existing live web UI: `web/index.html`, `web/app.js`, `web/app/*.js`, `web/spaces.js`, `web/spaces/*.js` plus related drawer, printer and preview modules.
- Existing Python HTTP interface: `wavefinity_web.py`, `wavefinity_web_impl/` and a broad catalog of `/api/*` routes. This is more than a compute endpoint; it also owns application preferences, folder and design I/O, preview, print/3MF, photo/AI, inventory and Space operations.
- Browser proof of concept: `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, `web/browser-local-poc/bridge.py`, `web/browser-local-poc/manifold64/`, and `web/browser-local-poc/{canonical.zip,reference.json}`.
- Browser reference harness: `browser-tests/prepare-local-poc.py`, `browser-tests/run-local-poc.mjs`, `browser-tests/reference-42x42x28.npz`. Do not confuse these with unrelated browser tests.
- Python engine: `organizer_geometry/`, `organizer_engine/`, `organizer_features/`, `organizer_inserts/`, `organizer_b4b/`, `organizer_drawer/`, `organizer_outputs/`, `organizer_storage/`, etc.
- Test baseline: the nine previously failing tests in `tests/test_wavefinity_web.py` were deleted in commit `acc74c1af7c34defe4865a842e62c5987076d609` at Andrew's instruction. Removing tests is NOT evidence that the behaviors they once checked are correct. Require fresh functional coverage for the affected flows during integration.

## Execution phases and acceptance gates

### Phase 0 — Inventory the whole API contract and establish parity fixtures

- Enumerate every `/api/*` usage from all web modules and pair it with a Python handler and its side effects. Classify each endpoint: (a) pure rules/validation, (b) preview/mesh, (c) print/export/geometry, (d) persistence/filesystem, (e) cloud/external integration, or (f) local desktop-only operation.
- Document all indirect dependencies (fonts, geometry kernels, triangulation, material profiles, fixtures, resource paths, backend-dependent state).
- Establish native golden references for ordinary bins in several dimensions, connectors and fit, lids/stacking, text, dividers/inserts, Gridfinity 21/42 geometry, Space and Storage Drawers structures, and representative multi-part 3MF outputs. Compare with the canonical engine; make no unsupported precision concessions.
- Set up repeatable desktop browser harnesses. Check WASM build provenance, license compliance, pinned dependencies and reproducible binaries. The currently CDN-loaded Pyodide/Earcut/Trimesh packages must be pinned; for future static hosting decide whether to vendor/copy required assets locally with integrity checks.
- **Gate:** A complete endpoint inventory and deterministic reference fixtures exist; existing production tests still run as before, and there is a reliable browser CI/smoke procedure.

### Phase 1 — Extract a reusable browser engine (no UI switchover)

- Promote the proof-of-concept worker, Python loader, `manifold64` WASM bridge and data conversion into a supported `web/` browser geometry runtime with a stable typed/versioned request/response protocol. Do not keep the generic experiment page as the runtime owner.
- Package the necessary real Python geometry modules, rules and non-compiled assets via a reproducible build step; enforce parity with the native source and reject stale/corrupt archives.
- Provide worker cancellation, superseded-job handling, progress updates, memory/timeout/error reporting, and a cache/startup strategy; prevent repeated runtime downloads for every button click.
- Preserve MeshGL64 float64 conversion and numerical invariants across Python/JS/WASM boundaries. Benchmark realistic large meshes and concurrent actions on ordinary Windows PCs.
- **Gate:** Browser engine can generate + validate the reference set, including more than plain boxes, with no geometry endpoint calls; independent mesh checks pass; new runtime can be tested without the experimental page.

### Phase 2 — Attach engine to actual Wavefinity UI behind an explicit opt-in

- Introduce a browser-side API/geometry adapter at the existing UI's request boundary instead of rewriting controls: the same UI request/response shapes route either to current server functions or to the new local runtime for the covered operations.
- Wire core catalog/rules, draft validation, preview, fit/feature changes and generated mesh previews first. Ensure latest request wins and a failed build does not erase the last valid state. Keep UI responsive during heavy builds.
- Require coherent preview and final export geometry; do not introduce a preview-only geometry rewrite with different rules.
- Use a visible but isolated development toggle on `wavefinity.org` during the migration. Production default stays on existing server until parity gates pass.
- **Gate:** Ordinary bin edit -> preview -> generate -> download works entirely through the original core UI using browser engine, with no server geometry requests and unchanged design behavior.

### Phase 3 — Finish real product coverage and file exports

- Migrate other geometry families systematically: connectors/lock fit, labels/text, dividers/cradles/pockets, lids/hinges, Storage Box, Storage Drawers, spaces/layouts, base trim/surface parts, Gridfinity, structural designs and all used part generators. Require feature-specific parity fixtures for each.
- Implement reliable STL and multi-part **3MF** generation, including Bambu/Orca-compatible object naming, placement, filament assignments and packaging metadata. This may require a WASM-capable replacement for the Python `lib3mf` path; do not claim done with STL alone.
- Convert server-side ZIP/staged download flows into browser Blob/download/export actions; for printer handoff, provide files users can open in Bambu Studio rather than claiming a static webpage can directly launch arbitrary local executables.
- Explicitly classify photo nesting, AI assistant/provider calls and other network features. Photo processing can be client-side if ported; AI API access may require a separate optional, clearly disclosed service. Never bundle secrets in JavaScript.
- **Gate:** Every supported user workflow and exported part produces equivalent meshes/files. Any feature that cannot be static is transparently identified and deliberately retained as optional external functionality (or explicitly removed with Andrew's approval).

### Phase 4 — Replace server storage and local filesystem operations

- Identify what currently lives in server `DATA_DIR` and generated directories: spaces, inventory, drafts/resume checkpoints, printer preferences, project files, export tokens and user-selected folders.
- Define browser storage semantics (IndexedDB/OPFS for local cache and automatic recovery; browser File System Access API where supported, plus explicit import/export and backups). Ensure data stays on that visitor's PC, not on Render.
- Preserve save/reload, restore, autosave, cross-Space moves, layout identity, inventory consistency and error recovery; test file permissions, browser clearing, version upgrades and data export/reimport.
- Migration from server-held data must be explicit and safe: no automatic loss or silent substitution of a different storage location.
- **Gate:** Complete return-visit workflow, backups/restore and print/export work with Render's backend inaccessible.

### Phase 5 — Cut over and qualify static hosting

- Bundle a truly self-contained static site (`index.html`, JS/CSS, WASM, Python assets, images and required metadata). Add build/version stamps and cache invalidation to prevent mismatched JS/geometry revisions.
- Run the whole intended workflow in Windows Chrome and Edge against a static-only local test server, then against the existing Render server with all `/api` calls intentionally blocked. Inspect Network traffic to prove that no Python backend is required for covered workflows. Test large files, cancellation and a later return visit.
- Compare load time, network bytes and memory. Preserve a rollback path through current Render configuration. Only after acceptance choose a free static host (e.g., Cloudflare Pages or GitHub Pages), deploy the same assets and repoint DNS for `wavefinity.org`.
- **Gate:** No backend dependency for the full committed scope, secure origin, successful STL/3MF exports, reliable browser persistence, and all applicable tests green. Render can then be retired for core geometry.

### Phase 6 — Remove the testing scaffold, not production assets

After Phase 5 passes, remove `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, and experiment-only fixture/bootstrap files not reused by the production runtime. Remove stale temporary page routes and UI controls. Keep the proven `manifold64` build/source/licenses and whichever real reference fixtures/testing infrastructure the production browser engine still uses, relocating them into their supported locations first.

Do not remove `browser-tests/test-1105-two-instance.html` or unrelated tools simply because they share the `browser-tests` directory.

- **Gate:** Nothing in the shipped core runtime imports a removed experiment path; no broken links; production browser tests and parity tests still provide coverage. Final test run is green without skips that hide required functionality.

## Operational rollout / safety

1. Continue existing Render hosting and direct-`main` publishing during development; all experimental activation is opt-in.
2. Keep data local and private by default; no hidden upload of user geometry. Be explicit about browser storage not being equivalent to cloud backup.
3. Integrate in bounded, verifiable slices (runtime, ordinary bin, other shapes, 3MF, persistence, static-site cutover, cleanup). Each slice has its own observable acceptance, not merely a code review.
4. If a regression surfaces, disable browser mode and route the current site back to the existing Python service while fixing parity. Never silently generate different geometry.
5. Completion claim requires a real Windows Chrome + Edge manual acceptance run and a clean automated relevant test suite, not simply passing the original two-bin proof of concept.

## Immediate next implementation step

**Begin Phase 0**, then Phase 1. Do not delete the experiment now: it is the working comparison harness. The nine test removals do not replace acceptance testing of the once-covered behaviors.
