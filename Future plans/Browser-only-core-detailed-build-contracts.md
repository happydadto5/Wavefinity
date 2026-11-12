# Wavefinity full browser-only cutover — executable implementation contracts

Status: DETAILED DESIGN, not implemented. Revision 2, November 12, 2026.
Owner decisions: desktop Windows Chrome and Edge; visitor installs nothing; RETAIN THE PRINT BUTTON and its complete print-preparation workflow; keep the existing Wavefinity interface; calculations and saves occur on the user's computer; no paid cloud geometry compute; keep wavefinity.org; do not create branches or worktrees; land safely on main. Do NOT file Poller Stories merely to follow this plan. These B00–B16 work packages are Story-sized coder assignments, NOT Story submissions. The owner accepts that the application may remain NON-FUNCTIONAL throughout partial implementation; do not invest in interim deployability.

This is the detailed companion to Browser-only-core-integration-plan.md. The two together govern the migration; this document wins wherever the original phase description was underspecified. Every package contains files, concrete patch, preconditions and a falsifiable acceptance gate.

## Definition of COMPLETE

A) wavefinity.org serves HTML, CSS, JS, fonts, pictures, pinned Python/Pyodide packages and WASM/static assets only; no running Python HTTP service is needed for any supported core operation.
B) The *existing* main UI designs ordinary bins, Wavefinity 7 mm and Gridfinity 21/42 mm, previews, edits features, handles all five Space types, maintains inventory and printer profiles, saves/recovers locally, generates valid individual and multipart STL and Bambu-compatible 3MF and preserves distinct first-class Print and Export actions. Print prepares validated, slicer-ready 3MF, provides a clear download/open-in-slicer handoff, and keeps honest inventory status. Core paths NEVER POST to a geometry server.
C) Entire end-to-end workflow passes with all /api/ requests blocked and with the existing Render Python app stopped. The user's GPU is optional; browser WASM processing runs on CPU. It must not require an installed Python interpreter, Bambu Studio, a separate helper, or a browser extension.
D) The old Render/Python-server approach is documented sufficiently to restore deliberately if the static cutover proves defective. No registrar account credentials or secrets in the public Wavefinity repo; the private Help-Code domain record remains in Help-Code.
E) Temporary proof-of-concept page and duplicate scaffolding are deleted AFTER the core runtime replaces them and checks pass. Keep enduring tests, fixture provenance, MeshGL64 build source/license and accuracy checks.
F) Full relevant test suite green. The nine tests removed in commit acc74c1 were not behavior fixes; replace their important coverage with actual passing tests, not skip/xfail, and never silently regress their former behavior.

The only intentional nonlocal class is an explicitly configured external AI provider, if supported. Optional AI Help is NOT ordinary local geometry and must not require a Wavefinity-operated server. Never expose a Wavefinity-owned API key in static assets. A browser cannot arbitrarily launch desktop slicer executables; the **Print UI remains** and performs full print preparation and slicer-ready 3MF handoff, not merely generic Export. The difference from native automatic slicer launch must be disclosed truthfully. The owner does not require the application to function at any intermediate migration phase.

## Frozen architecture decisions

- Preserve the original UI and the DOM/state abstractions: web/index.html, web/app/*.js, web/drawer-*.js, web/spaces/*.js, web/storage-*.js, web/workspace.js and web/structural-design.js. Do not build a second app.
- One shared production worker runtime wrapping the canonical Python geometry source from organizer_engine, organizer_geometry, organizer_inserts, organizer_features, organizer_drawer and related modules. Use pinned Pyodide plus the custom float64 Manifold MeshGL64 bridge already proven in browser-local-poc. No float32 fallback.
- One transport adapter in web/app/03-history-utils-catalog.js, NOT dozens of independent fetch rewrites. Existing api(path,payload,opts) and apiSideEffect(...) signatures remain stable for consumers; a new WFLocalAPI dispatch layer implements local paths and errors. Build only the final local-mode adapter. Do not implement a temporary server/browser switch or fallback merely to keep intermediate releases functioning. A partly migrated app may be broken until final integration.
- One versioned worker protocol: request = {v:1, job_id:string, path:string, payload:object|null, design_epoch:string|null}; emitted messages are {v:1,job_id,type:"progress"|"result"|"error"|"file", ...}. Match request/response shapes of the existing routes, not just example calls. Progress and cancellation must never alter a later design epoch.
- One file result protocol: worker returns named bytes via transferable ArrayBuffers; main thread holds Blob objects in a one-shot WFLocalFiles table keyed by opaque local_file_id, and normal route responses list files with {name,local_file_id}. The existing saveGeneratedFiles() resolves these Blob handles, not GET /api/export tokens. Revoke consumed/expired objects.
- Reuse existing window.WFFileSystem in web/browser-files.js, which ALREADY supports IndexedDB handles, showDirectoryPicker, explicit permission checks, file reads/writes and Blob download fallback. Do not invent a second folder abstraction. Use browser storage for lightweight preferences and recovery; writable user folder remains authority for Space and inventory files where selected.
- No invisible semantics change: folder permissions, inventory operations, Space IDs, printer limits, 7/21/42 grids, stale-work cancellation, overwrite prompts, resume checkpoints, 3MF filament metadata, generated part names and error behavior are contract behavior.
- Production canonical Python files remain the single source of geometry rules. A deterministic pack step builds the browser zip from the checked-out main version. Prevent drift with file/hash/version checks; never hand-edit duplicate geometry formulas in JS.
- Direct-main process: before coding fetch and fast-forward, and immediately before publishing fetch and reconcile remote changes, rerun affected checks and push without force. Do not reset or overwrite concurrently active coder changes.

## Owner overrides: PRINT survives, one complete cutover, no interim compatibility work

**Print is mandatory.** Do not remove, rename to Export, hide, or disable the existing Print buttons in the bin editor, individual bin selection, inventory, Storage Box, Storage Drawers, Surface/base trim, or other structural workflows. Export/Save remain separate operations. Print is an intent to *prepare and hand off a print job*, not a synonym for downloading raw geometry.

**Present behavior to retain where technically possible:** The local Windows Python version of `printModelWithReport()` in `web/app/15-generate-dialogs.js` validates, autosaves, runs `/api/print`, generates/reuses the correct 3MF files, launches an installed slicer via the native server, and updates printed status. The current hosted mode explicitly refuses Print and says to use Export. The final static edition MUST revive a working Print button in the hosted web app, not carry that refusal forward.

**Final browser Print contract:**
1. User clicks the existing **Print** button; optional bin/connector selection remains unchanged. Print snapshots the current design, Space identity and selected printer profile; flushes pending edits/resume checkpoint; validates printer limits and geometry; builds accurate, correctly arranged and named Bambu/Orca-compatible multipart 3MF files locally via the canonical engine and new 3MF packager. Same checks as the old native Print flow.
2. If a writable user folder is selected, write the prepared 3MF there using `WFFileSystem`; otherwise download it. Show a direct, prominent **Open in Bambu Studio** next-step message with the exact saved/downloaded filename; browser Downloads can open the .3mf using Windows file association, or the user can import it in the slicer. Do **not** send the user through generic Export settings after pressing Print. Preserve progress and part-selection feedback.
3. Keep explicit and truthful status: prepared/downloaded ≠ proven opened in slicer ≠ physically printed. Acknowledge successful handoff before recording an existing Printed status, or introduce a distinct Prepared status with full inventory compatibility. Never display “Sent to slicer” or mark Printed simply because a Blob downloaded. Maintain partial-save errors, duplicate reuse and cancellation semantics.
4. A normal static website cannot execute an arbitrary Windows BambuStudio.exe or OrcaSlicer.exe. Do not promise an identical one-click *automatic slicer launch* without a proven, supported, opt-in registered protocol. Such a protocol is optional and must fall back to the ordinary 3MF file. **No installed Wavefinity helper, PWA, local HTTP daemon or extension is permitted**. Users may have an installed slicer because they intend to print, but installing Wavefinity is not required.
5. This one unavoidable browser-security difference is documented; preserve everything else about Print's distinct workflow and visual placement.
6. Windows Chrome and Edge acceptance must include clicking Print for a normal bin+connector and a structural Space, verifying 3MF opens correctly in Bambu Studio, checking exact print metadata/part placement and status transitions, and confirming no /api/print request or server-side geometry use.

**Single completion gate, no halfway app:** The owner explicitly accepts a broken/incomplete app until the entire browser-only implementation is finished. Therefore remove requirements for interim browser-mode switches, simultaneous Python/browser APIs, dual hosting, or stage-by-stage functional deployments. Build final components in isolated modules and test them individually with fixtures as needed; only after ALL B00–B13 packages are implemented is the full main UI expected to work. B14 is the only end-to-end application functionality and deployment gate. No partial cutover, no extra workarounds to keep each intermediate package operating. Keep the old Render/Python approach in documentation and version history, but don't spend effort on maintaining two working paths.

## Required API inventory (explicit route checklist)

The original API includes routes from wavefinity_web.py, drawer_routes(...) and frontend callers. Enumerate both request shapes and side effects in B01; these names form the minimum known coverage list. All currently reachable routes must have a disposition in the generated manifest; unclassified additions block cutover.

STATIC / STATUS: GET /api/catalog, /api/health, /Brochure.md, /images/*; /api/suggestions; /api/operation-status.

PURE RULES / EDIT: /api/design/validate, /api/design/inventory-preview, /api/design/division-label-fit, /api/feature/default, /api/feature/draft, /api/feature/fit, /api/feature/apply, /api/feature/duplicate, /api/feature/delete, /api/layout/mode, /api/layout/expand, /api/pegboard/layouts, /api/pegboard/hooks, /api/sampler.

GEOMETRY: /api/preview, /api/generate, /api/connector, /api/print, /api/nest/trace, /api/nest/photo, /api/nest/retrace, /api/space/warm, /api/space/structural-design, /api/space/structural-generate, /api/space/structural-print, /api/space/structural-print-combined, /api/space/storage-box-print, /api/space/surface-print, /api/space/storage-drawers-summary, /api/space/storage-drawers-validate, /api/space/storage-drawers-reset, /api/space/storage-drawers-mutate-text, /api/space/storage-drawers-mutate.

FOLDER / SPACE / SETTINGS: /api/preferences, /api/folder/no-defined-space, /api/folder/use, /api/browse-output-folder, /api/browse-slicer-path, /api/show-log, /api/space/show-folder, /api/space/browse-storage-parent, /api/space/startup, /api/space/inspect, /api/space/other-spaces, /api/space/storage-state, /api/space/storage-plan, /api/space/storage-change, /api/space/use-untyped, /api/space/create, /api/space/configure, /api/space/create-text, /api/space/configure-text, /api/space/copy-text, /api/space/copy-name, /api/space/update, /api/space/forget, /api/space/defaults, /api/space/resume, /api/space/printer-profile.

DRAWER / INVENTORY: /api/drawer/load, /api/drawer/save, /api/drawer/report, /api/drawer/design-source/save, /api/drawer/design-source/duplicate, /api/drawer/design-source/status, /api/drawer/generate-bin, /api/drawer/surface-fill, /api/drawer/surface-fill/create, /api/drawer/spacers, /api/drawer/spacers/refresh, /api/drawer/connectors, /api/drawer/save-bins, /api/drawer/print-bins, /api/drawer/print-spacers, /api/drawer/print-complete.

AI (separately gated): /api/ai/connection, /api/ai/ask, /api/ai/prompt, /api/ai/candidate, /api/ai/repair-prompt.

DEPRECATED SERVER-ONLY: GET /api/export/<token>/<filename> becomes named local Blob transfer; local desktop executable detection/launch and opening server log/folders are removed from static mode with explicit user-facing replacement. The static deployment must contain ZERO unresolved imports of these server-only operations.

## Work packages (execute in order; independent subsets can be tested but cannot skip gates)

### B00 — Freeze documentation for the old Render/Python path

Requires: none.
Existing files: render.yaml, Dockerfile, wavefinity_web.py, requirements.txt, README.md, docs (create directory).
Create docs/legacy-python-server-hosting.md, docs/browser-runtime-architecture.md.
Patch:
1. Document the old request path (index.html -> /api/* -> wavefinity_web.py -> native engine -> temporary export URL), process start from Dockerfile/render.yaml, server-side preference/folder paths, configuration/environment variables as read from actual files (NO example secrets with values), manual rollback/deploy commands, health endpoint, evidence-gathering commands, strengths/limitations (Render sleep/RAM), and migration risks.
2. Record exact starting baseline SHA, source fingerprint and last known working Render URL; link the relevant Git commit containing the old server implementation. No branch required. Distinguish old server framework from the Python geometry engine still packaged for browsers.
3. Document new static request/data flow and keep the private Porkbun ownership/DNS record in private Help-Code, not in this public repository.
Gate: a new coder can follow the documented instructions to re-enable the old Python server from retained source/history without guessing; no secret values are committed; the document is retained even after static cutover.

### B01 — Exhaustive executable route contract and equivalence fixtures

Requires: B00.
Existing files: wavefinity_web.py, wavefinity_web_impl/*.py, organizer_drawer/*.py, web/**/*.js, tests/test_wavefinity_web.py.
Create browser-core/contracts/route-manifest.json, scripts/audit-browser-routes.py, browser-tests/core/route-contract.test.mjs, browser-tests/core/fixtures/README.md.
Patch:
1. Implement a scanner of ALL calls to api()/apiSideEffect()/fetch() within current web JS plus server POST_ROUTES, drawer_routes and server GET paths, including computed/dynamic references. Record method, source file:function, handler, request schema/canonical fixture, response fixture, errors, mutations, call ordering, and local replacement package for every path. File is versioned and generated/checked.
2. Capture native golden request/response examples for each reachable action and snapshot/error cases. Do not cache paths or secrets from local user folders. Identify stable schema vs nondeterministic metadata like timestamps/temporary filenames; explicitly normalize those.
3. Hard fail the checker if a frontend path has no manifest entry, a backend path is removed without an explicit retired disposition, a current UI operation still implicitly needs the HTTP server, or a response field silently disappears.
Gate: repository includes a reviewed complete route manifest and CI/checker that detects newly added unmapped calls. This is the only place where additional concrete routes discovered after this document may be enumerated; newly discovered work MUST be assigned to a numbered package and not left as a vague later task.

### B02 — Reproducible self-hosted browser toolchain and canonical Python bundle

Requires: B01.
Existing files: web/browser-local-poc-worker.js, web/browser-local-poc/bridge.py, web/browser-local-poc/manifold64/{bridge64.cpp,bridge64.mjs,bridge64.wasm,build.sh,LICENSE,README.md}; browser-tests/prepare-local-poc.py, requirements.txt, organizer_geometry/__init__.py.
Create scripts/build-browser-core.py, web/browser-core/vendor/manifest.json, web/browser-core/engine/canonical.zip, web/browser-core/engine/manifest.json, browser-tests/core/bundle-integrity.test.mjs.
Patch:
1. Pin exact Pyodide version/wheels and Manifold 3.5.0 C++ upstream commit and Emscripten version already recorded in the PoC README. Make a reproducible build and canonical-source zip from the checked-out engine and all *real* required dependent modules; record SHA256 of every output. Verify LICENSE inclusion.
2. Bundle all required runtime assets locally instead of relying on cdn.jsdelivr.net or files.pythonhosted.org when executing the deployed static site. Follow the runtime's package-loading rules for both .mjs and .wasm, and test MIME types from a static HTTP server.
3. Eliminate the hard-coded 42 mm reference restriction from the reusable runtime (not from the historical experiment yet), while preserving exact Manifold float64 processing. Pin memory ceiling and measurable performance baselines; return a meaningful capacity error instead of crashing or freezing a tab.
Gate: deterministic canonical.zip and manifest pass hash checks; a static-only local server with network disabled after initial load can build a 42x42x28 and an 84x42x28 real bin, matching canonical native references within <=0.00001 mm vertex deviation where correspondences are defined; watertight, one solid, no intersecting facets.

### B03 — Stable browser worker API and local dispatcher

Requires: B02.
Existing files: web/index.html, web/app/03-history-utils-catalog.js, web/app/01-runtime-state.js, web/app.js, web/app/11-parts-preview-requests.js.
Create web/browser-core/worker.js, web/browser-core/bootstrap.js, web/browser-core/local-api.js, web/browser-core/local-files.js, web/browser-core/runtime-status.js, browser-tests/core/worker-transport.test.mjs.
Patch:
1. Replace network execution at one point in api()/apiSideEffect() with the final WFLocalAPI transport; no server/browser executionMode, intermediate compatibility toggle or silent server fallback. Initialize the local engine before catalog load. Broken UI until the last package is acceptable.
2. Worker dispatch envelope: {v,job_id,path,payload,design_epoch}; returns progress, results/errors, and transferable file bytes. Preserve server-like object schemas and useful error.status/type. One worker initialization shared across calls; bounded queue for expensive geometry, cancellation via terminating/restarting worker, active design epoch guard, and release of stale file handles.
3. LocalFileStore maintains file-ID-to-Blob mapping and exposes claim()/discard()/discardAll(); never inject fake /api/export URLs. apiSideEffect operation_id behavior maps to a local operation ledger and worker progress so retries cannot accidentally duplicate side effects.
4. Do not build a hosted/browser toggle, preview deploy, or dual-stack compatibility path. Final static-only mode is the sole target; incomplete UI need not be runnable.
Gate: timeout, cancellation, error, retry, two rapid successive previews, stale result suppression, worker crash/restart, Blob lifetime and main-thread responsiveness pass automated browser tests.

### B04 — Catalog and pure edit/validation operations

Requires: B03.
Existing files: wavefinity_web.py (reference only), wavefinity_web_impl/_designs/*.py, web/app/02-lifecycle-ai-help.js, web/app/03-history-utils-catalog.js, web/app/10-draft-update-commit.js, web/app/11-parts-preview-requests.js.
Create web/browser-core/engine/route-dispatch.py, browser-tests/core/edit-parity.test.mjs.
Patch:
1. Port local equivalents behind existing route names for GET /api/catalog and /api/health (health becomes local manifest/build identity) plus /api/design/validate, /api/design/inventory-preview, /api/design/division-label-fit, /api/feature/default/draft/fit/apply/duplicate/delete, /api/layout/mode/expand, /api/pegboard/layouts, /api/sampler and /api/space/storage-drawers-summary/validate.
2. Call original Python implementations with only environment adapters (not reimplemented constants). Preserve 7 mm Wavefinity and 21/42 mm Gridfinity limits, Space fit and cross-grid rejection, feature order, error shape and validations. Package remaining source dependencies uncovered by the route-manifest tests.
3. Move static catalog JSON/capability data into the generated bundle and include its version/hash. Local async call remains the same Promise resolved by api().
Gate: fixture-by-fixture equality for request/response (aside from documented ephemeral fields), including invalid cases and error/status shape; no network requests; existing UI form-state tests pass.

### B05 — Full core preview and editor integration

Requires: B04.
Existing files: web/app/11-parts-preview-requests.js (refreshPreview, adoptPreviewResult), web/app/12-3d-preview-render.js, web/preview3d-webgl.js, web/app/01-runtime-state.js, web/app/04-side-openings-wall-choices.js, web/app/13-layout-geometry.js.
Create browser-tests/core/preview-parity.test.mjs.
Patch:
1. Route /api/preview and any dependent nest/layout/feature previews to browser-core worker using the native canonical geometry; keep payload and returned preview_mesh/layout/status shapes compatible.
2. Preserve mutation controls, stale preview epoch logic, last-valid preview, warning banners, fit/feature errors, and exact nested_clearance/seam rules. Progress events use current preview wait UI; do not block the main thread.
3. Test changing inputs during a build, invalid text/scoop/bore, closing or switching a Space, and a too-large mesh. The last valid preview must not disappear on an out-of-order worker response.
Gate: ordinary and complex preview parity + responsiveness across Windows Chrome/Edge; no /api/preview POST.

### B06 — Ordinary bin, connector, STL and multiparts core

Requires: B05.
Existing files: web/app/15-generate-dialogs.js (generatePartsWithReport, saveGeneratedFiles), organizer_engine/_boxes.py, organizer_engine/_export.py, web/app/03-history-utils-catalog.js.
Create web/browser-core/engine/build-outputs.py, browser-tests/core/bin-connector-exports.test.mjs.
Patch:
1. Route /api/generate and /api/connector through canonical Python build functions, keeping outputs and the existing dialog progress/error semantics. Implement 42x42, 84x42, wavy 7 mm and Gridfinity 21/42 bins, actual wave locking connectors and installed feature cases.
2. Return [{name,local_file_id}] file descriptors and buffer bytes, not hosted filesystem paths or ephemeral server tokens. Update saveGeneratedFiles() to save browser blobs to the already-selected writable handle or download if no folder exists; collision/overwrite prompts and all-or-nothing save logic remain.
3. Verify every output file independently for watertightness, winding, intersections, wall fit, naming and sizes. Preserve cancellation if tab navigates away.
Gate: local generation/output modules and contract/mesh fixtures pass without API network calls; 0.25 mm seam remains. Full original GUI integration is deferred to final B14 acceptance.

### B07 — Exact 3MF and printer-file equivalence

Requires: B06. MUST NOT be skipped just because STL succeeds.
Existing reference: organizer_engine/_export.py (export_bambu_compatible_3mf, export_text_body_3mf, export_assembly_3mf, export_object_groups_3mf, validate_3mf, validate_object_groups_3mf), organizer_outputs/*.
Create web/browser-core/engine/three_mf.py, browser-tests/core/three-mf-parity.test.mjs and fixtures.
Patch:
1. Avoid native lib3mf dependency in Pyodide by implementing its currently used 3MF behaviors using Python zipfile/XML (or a proven wasm wrapper) in browser engine, without re-creating geometry formulas. ZIP must contain legal 3MF package files including [Content_Types].xml, _rels/.rels, 3D/3dmodel.model and appropriate Bambu metadata. Keep each object's vertices/triangles, transforms, names, filament assignment and settings equivalent to the Python/lib3mf output.
2. Preserve object groups, separate label/body where specified, multi-plate arrangement, all existing filament color/material/profile metadata, and output filenames. Do not merely package an STL inside a .3mf file.
3. Build round-trip validator for object count, per-object mesh stats, material mapping, transforms and package integrity; compare against native references after stripping nonsemantic identifiers. Inspect opening in Bambu Studio on Windows.
Gate: representative ordinary, labels, connectors, lids and multi-part 3MF load in Bambu Studio with correct placement/color assignments; parser validates the 3MF ZIP and every solid; no native lib3mf package or Python server required.

### B08 — Preserve full Print workflow and slicer-ready handoff (distinct from Export)

Requires: B07.
Existing files: web/app/15-generate-dialogs.js (printModelWithReport, saveGeneratedFiles, browseSlicer, watchServerVersion), web/printer-profile.js, web/spaces/13-printer-profiles.js, web/browser-files.js.
Create browser-tests/core/print-download.test.mjs.
Patch:
1. Route /api/print and reusable print operations through browser output builder. Preserve printer volume limits, part/plate packing, labels and status on inventory rows.
2. KEEP the current Print buttons and part selection dialogs. Replace only the prohibited native executable auto-launch with the Print contract above: autosave, validation, generation/reuse, arranged 3MF, save/download, explicit slicer-opening handoff. Preserve a separate Export action. Do not report "Sent to slicer" without verified proof.
3. Keep progress, timeout/cancellation, partial-save truth and printed-status state. Prepared does not equal Printed; use acknowledgement or a distinct Prepared state and compatibility tests. Replace /api/operation-status polling with local worker job status; /api/health now checks browser bundle version.
Gate: Print module builds correct prepared 3MF and exposes working download/open-next-step protocol, printer/Space validation and honest state transitions. Whole GUI Print acceptance on Windows occurs at B14, not a requirement for intermediate runnable app.

### B09 — Browser persistence, preferences and Space identity

Requires: B03–B05.
Existing files: web/browser-files.js, web/spaces/01-core.js, web/spaces/03-safe-switching.js, web/spaces/04-metadata-persistence.js, web/spaces/05-space-memory.js, web/spaces/07-welcome-folders.js, web/spaces/08-space-setup.js, web/spaces/09-event-wiring.js, web/app/02-lifecycle-ai-help.js.
Create web/browser-core/space-store.js, web/browser-core/preferences.js, browser-tests/core/persistence.test.mjs.
Patch:
1. Retain .wavefinity.json (current metadata version), Space ID, Wavefinity bins.md and existing File System Access/IndexedDB handle semantics as authority. No fake server paths or parallel invented database for the same Space. Use IndexedDB for preference/recovery only; persist printer and UI preferences by origin and preserve explicit export/import.
2. Replace /api/preferences; /api/folder/*; /api/space/startup/inspect/other-spaces/storage-state/storage-plan/storage-change/use-untyped/create/configure/create-text/configure-text/copy-text/copy-name/update/forget/defaults/resume/printer-profile and /api/space/show-folder/browse-storage-parent with local file + in-memory operations. The route-manifest document specifies exact JSON schemas and important write ordering.
3. Reuse existing SP and WFFileSystem functions; preserve user gestures for directory pickers. No folder selected -> design-only + downloadable files. Folder denied/revoked -> clear actionable error and do not falsely report autosave complete. No automatic overwrite or copy of user files.
4. State ownership: Space ID/design epoch guard on every asynchronous file load/write. Queue writes per folder, coalesce redundant updates, use rollback of partially generated file sets and flush on Space switch/print/export. Never allow an old Space completion to overwrite the current Space.
Gate: create/rename/open/switch/reopen each Space type; close/reopen browser; restore recovery; revoke permissions; switch during autosave; preserve all files and identity. Existing shipped metadata/inventory is still readable, without requiring Render.

### B10 — Inventory and drawer flow parity

Requires: B06, B09.
Existing files: web/drawer-model.js, web/drawer-panel.js, web/drawer-view.js, web/spaces/06-inventory-io.js, organizer_drawer/{_core,_inventory,_report,_spacers}.py and organizer_inventory/*.py.
Create web/browser-core/engine/drawer-routes.py, browser-tests/core/drawer-parity.test.mjs.
Patch:
1. Implement full route family /api/drawer/load/save/report/design-source/save/duplicate/status/generate-bin/surface-fill/surface-fill/create/spacers/spacers/refresh/connectors/save-bins/print-bins/print-spacers/print-complete, preserving shapes, touched filenames, row idempotency and deletion behavior.
2. Keep the browser folder as storage authority; do not reintroduce server-side inventory. Integrate SP.inventoryRequest's existing transactional write/rollback and bin generation stamp logic. Keep stale result guard when Space changes.
3. Verify launch/open, row create/update/delete, duplicate/move, autosave, restore, reopening, print outputs, and Gridfinity cross-grid checks; do not silently resurrect deleted draft rows.
Gate: all inventory and drawer user flows pass with /api blocked, and resulting folder files compare to canonical expected layout/state.

### B11 — All remaining structural Space geometry

Requires: B07–B10.
Existing files: web/structural-design.js, web/storage-box-form.js, web/storage-drawers-form.js, web/storage-drawers-workspace.js, web/spaces/10-storage-box-structural.js, web/spaces/11-base-trim.js, web/spaces/14-drawers-cabinet.js, organizer_outputs/space.py, organizer_spaces/*.py, organizer_storage/drawers/*.py (where present), organizer_features/*.py.
Create web/browser-core/engine/structural-routes.py, browser-tests/core/structural-parity.test.mjs.
Patch:
1. Implement /api/space/warm, structural-design/generate/print/print-combined, storage-box-print, surface-print, storage-drawers-summary/validate/reset/mutate/mutate-text. Retain standard Space presets and printer fit, right file names, storage drawer height/material constraints and space location metadata.
2. Test Storage Box assembly, lid/hinge/latch; Drawer and Storage Drawers parts; Surface/base trim; pegboard hooks; grid-aware 7/21/42 Space compatibility, no-space bin assembly, labels and stacking.
3. Reuse B07 3MF writer and B09 folder storage; every build uses a snapshotted Space state, returns operation progress, and cannot cross-save outputs to a different Space.
Gate: each supported Space type exports and prints multipart assets with complete parity; all relevant preview and save/reopen tests pass offline after load.

### B12 — Text, photo/nesting, advanced features and fixtures

Requires: B05, B07, B11.
Existing files: wavefinity_web_impl/_nest.py, wavefinity_web_impl/_designs/*, organizer_inserts/_nest/*, organizer_inserts/_text.py, web/app/11-parts-preview-requests.js, web/app/04-side-openings-wall-choices.js, web/spaces/12-space-info.js.
Create web/browser-core/engine/nest-routes.py, browser-tests/core/feature-matrix.test.mjs.
Patch:
1. Implement /api/nest/trace/photo/retrace with browser File/Blob image input, browser decoder when helpful, and the authoritative image contour/shape behavior. Port only incompatible native image-processing dependencies without altering designed contour semantics.
2. Include bores, side openings, wall choices, dividers, cradles, labels/text, scoops, pockets, post/slots/steps, hinged/lid features, photo nest and pegboard hooks in fixture matrix. Package fonts/assets deterministically; no silent omission because a Python wheel is incompatible.
3. Prove feature editor -> preview -> export matches native reference mesh and part counts. Bad user files/errors must be explicit and non-destructive.
Gate: full advanced-feature matrix green with browser geometry and printable exports; no /api/nest endpoints used.

### B13 — Optional AI and intentional desktop-only capability replacements

Requires: B03, B09.
Existing files: web/app/02-lifecycle-ai-help.js, wavefinity_web.py (AI handlers), web/spaces/12-space-info.js, web/app/15-generate-dialogs.js, web/app/16-suggestions.js, web/index.html.
Create web/browser-core/capabilities.js, docs/static-capability-differences.md, browser-tests/core/capabilities.test.mjs.
Patch:
1. Preserve AI Help UI if configured: local prompt assembly and local candidate validation always use canonical rules. For actual LLM responses use only a user-configured third-party service reachable securely and directly from the browser when CORS/auth allows. No Wavefinity-owned keys or hidden server proxy. If no supported safe direct mode, show "AI Help requires an external provider and is unavailable in this browser-only edition" instead of silently calling Render or claiming the same functionality. This explicit feature exception requires owner approval before final cutover if preserving AI Help unchanged is mandatory.
2. Replace /api/suggestions with local static/help content; replace /api/space/show-folder, /api/browse-slicer-path, /api/show-log and native desktop dialogs with browser-legal equivalents. Preserve Print as a first-class action; remove only deceptive automatic-executable-launch claims and keep the true print workflow.
3. Keep ABOUT / Brochure.md as a static file in the deployed output with the same URL. Display truthful capability/status indicators; printer profile remains local.
Gate: no API key leaks, no unsupported native operations; every visible control does what its label says; users can accomplish all core geometry tasks without any external AI service.

### B14 — Static-only build, deployment and rollout

Requires: B00–B13 acceptance.
Existing files: web/index.html, web/app.js, Dockerfile, render.yaml, README.md, scripts/build-browser-core.py, docs/browser-runtime-architecture.md.
Create scripts/build-static-site.py, browser-tests/core/static-smoke.test.mjs, docs/static-host-rollout.md, docs/static-host-rollback.md, deployment/static-host-config/ (only if needed).
Patch:
1. Build dist/ containing only required static assets, complete locally pinned Python/Pyodide/wasm bundles, Brochure.md, images, fonts and metadata. Manifest references must be integrity checked; stale mixed JS/WASM versions must fail visibly. Normalize content types, CSP/CORS, Brotli/gzip optional; check per-file static-host limits.
2. Launch a simple STATIC file server against dist, intentionally block every /api/* request, and run a scripted full product tour for Chrome and Edge on Windows; verify no backend process started and inspect network logs.
3. After the entire app passes Windows Chrome/Edge acceptance including Print, upload the same dist artifact to a free/near-free static provider (Cloudflare Pages default if compatible, otherwise GitHub Pages subject to limits), configure HTTPS for wavefinity.org/www. Preserve legacy Render rollback docs but do not maintain two operational modes. Domain/DNS ownership remains at Porkbun with the private Help-Code DNS record.
4. Switch production ONCE after all packages are complete; no gradual per-feature toggles or interim production releases. Monitor load/error status without collecting private designs. DNS rollback to the preserved Render setup does not restore browser-held files. Optional AI or asset hosting may have independent costs.
Gate: all core routes work with /api blocked; entire product including all original Print and Export entry points works in Windows Chrome/Edge, 3MF slicer handoff and truthful inventory status validated, data persists, tests green, URL+TLS correct, no Python service. No halfway deployment.

### B15 — Retire old service *from execution*, retain historical documentation

Requires: B14 complete and owner acceptance.
Existing files: Dockerfile, render.yaml, wavefinity_web.py, wavefinity_web_impl/, organizer_engine/, organizer_geometry/, docs/legacy-python-server-hosting.md.
Patch:
1. Leave docs/legacy-python-server-hosting.md and its immutable commit references. Document the actual last working server deployment SHA and what to restore. Retain relevant source history accessible through Git. Move old HTTP/Render runtime out of the static build and remove production import/dependency paths; do not delete the canonical Python geometry modules still needed in the browser.
2. Remove or visibly mark the old Render deployment config and Python HTTP entrypoint as historical, after rollback window. Keep ability to reconstitute from recorded old commit; no new branches required. Update README.md to prefer static deploy instructions and link historical recovery doc.
3. Confirm no public frontend includes a "silent fallback" request to /api on a server. A failing WASM runtime must surface failure, not send designs to an external server.
Gate: static application, docs and tests work after disabling Render entirely. Old approach has readable recovery documentation and a source SHA, even though it is no longer the live infrastructure.

### B16 — Remove prototype-only code, retain enduring coverage

Requires: B14–B15 complete.
Existing files: web/browser-local-poc.html, web/browser-local-poc.js, web/browser-local-poc-worker.js, web/browser-local-poc/{bridge.py,canonical.zip,reference.json,style.css}, browser-tests/{README.md,prepare-local-poc.py,run-local-poc.mjs,reference-42x42x28.npz}, web/browser-local-poc/manifold64/*.
Patch:
1. Delete only those experiment files that have been superseded by the new supported core runtime and have no production/CI references; move or preserve Manifold64 source, build script, license and binary in the production vendor path. Keep useful golden reference fixtures and re-home them to browser-tests/core/.
2. Replace outdated unsuccessful-POC notes with accurate retained history: the original failure, custom double-precision breakthrough, Windows manual confirmation and cutover. Preserve docs rather than showing obsolete "POC failed" as the current state.
3. Replace historically important coverage from the nine removed web tests with stable behavior tests that pass; do not use regexes that fail when code is split across JS modules. Prefer interactive behavior/API contract tests over string matching.
Gate: no links/imports to retired paths, static site no longer exposes experiment controls, no loss of regression coverage, all suites green, geometry parity remains <=0.00001 mm where test comparable.

## Mandatory global regression gates after every package

- File integrity: no stale bundle/manifold asset, missing packages or license files.
- Geometry: canonical 7-mm wave and 21/42 Gridfinity, outer/cavity/rim/connector precision and mating gap, watertightness, single solids and Bambu STL/3MF import where applicable.
- Workflow: New Bin, discard/keep edit, save/restore/switch/delete/duplicate, no resurrected deleted draft, resume queue coalescing + stale Space guard, autosave flush on output/Space switch, correct print file handoff and Brochure.md content. These explicitly replace the nine tests deleted at the owner's request.
- Browser isolation: worker event loop stays responsive; no geometry or private-file data sent to /api. Browser storage failure is never called success. Worker errors never silently fall back to server.
- Tests: all previously passing tests keep passing plus new browser-core suites; no required test is skipped, disabled or deleted to make a green total.

## Execution order (hard dependencies)

B00 -> B01 -> B02 -> B03 -> B04 -> B05 -> B06 -> B07 -> B08.
B03/B04 also unblock B09; B06+B09 unblock B10; B07+B10 unblock B11; B05+B07+B11 unblock B12.
B03+B09 unblock B13. B00 through B13 -> B14 -> B15 -> B16.

Each coder assignment uses one Bxx package as its scope, reads this file and current main, implements specified files/tests, and reports changes, runtime, limits and commit SHA. Intermediate packages may leave the UI broken; a package gate tests its own modules/fixtures. B14 alone requires a fully runnable integrated UI and full Windows Print acceptance.

## Stop conditions / design escalations

The first implementation may reveal a genuinely impossible compatibility issue not observable from this architecture review. Do not invent product behavior, drop features, weaken tolerances, silently require installation, move visitor files into the cloud, or ship a hybrid server dependency to bypass that problem. Preserve partial progress, report the concrete affected route/feature/asset and propose the smallest compatible alternative for Andrew's decision. The primary goal and architecture are settled; only unforeseen technical blockers should require owner judgment.
