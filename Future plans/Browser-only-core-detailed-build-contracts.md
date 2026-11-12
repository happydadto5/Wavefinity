# Wavefinity full browser-only cutover — executable implementation contracts

**DOMAIN OWNERSHIP/DNS LOCK (owner decision, 2026-11-12):** The domain `wavefinity.org` **stays registered, paid and renewed at Porkbun**. Keep **Porkbun authoritative DNS/nameservers**, too. No registration transfer, registrar change, Cloudflare nameserver switch, additional domain purchase or domain renewal payment. **Render Static Site is the selected hosting path**, with a new static site under the existing Render account. At final cutover only, request Andrew's permission to adjust the necessary existing DNS **records within Porkbun** (for example the `www` CNAME) and move the custom-domain association between Render services; the already-configured apex A `<actual apex A from private Help-Code>` should remain if Render continues specifying it. These are routing changes, not registrar/DNS hosting transfers. A fallback host requiring moving nameservers is **out of scope and not to be proposed** without Andrew specifically reversing this rule. Document the actual record edits in private Help-Code, not public registration/account details.


Status: DETAILED DESIGN, not implemented. Revision 5, November 12, 2026.
Owner decisions: desktop Windows Chrome and Edge; visitor installs nothing; RETAIN THE PRINT BUTTON and its complete print-preparation workflow; keep the existing Wavefinity interface; calculations and saves occur on the user's computer; no paid cloud geometry compute; keep wavefinity.org; do not create branches or worktrees; land safely on main. Do not file Poller Stories merely by reading this reference; the explicit command to execute `Browser-only-migration-story-creation-handoff.md` IS authorization to create and submit them (not code). These B00–B16 work packages are Story-sized coder assignments, NOT Story submissions. The owner accepts that the application may remain NON-FUNCTIONAL throughout partial implementation; do not invest in interim deployability.

This is the detailed companion to Browser-only-core-integration-plan.md. The two together govern the migration; this document wins wherever the original phase description was underspecified. Every package specifies files, code changes, dependencies and implementation deliverables, NOT test assignments. **The owner tests the actual application. Coders must never author, run or repair automated tests, perform manual application tests, or create manual user test plans/checklists.** Coders reason through logic and inspect changed code instead.

**LOW-TOKEN READING RULE:** [Browser-only-core-diff-map.md](Browser-only-core-diff-map.md) gives exact source symbols, before/after edits, asset layout and static-host handoff. [Browser-only-core-source-route-index.md](Browser-only-core-source-route-index.md) indexes 91 source routes and major UI call sites. A coder assigned Bxx reads only that Bxx package and matching diff/source-index sections, then the current affected source files. No repeated repo-wide architectural investigation. Line numbers can drift while Gridfinity is being completed.

**FINAL HOST:** Render **Static Site** is the default (free subject to bandwidth/build allowances); not a Render Free Python Web Service. Static CDN has no web-service idle sleep or roughly 60-second server wake-up. First browser download/Pyodide/WASM initialization can still take time. Do not switch or repoint the live domain until Andrew expressly approves. Do not use Cloudflare Pages as a fallback: apex-domain Pages hosting requires nameserver changes, which Andrew does not approve. If Render Static is unsuitable, stop and present an alternative that keeps Porkbun registrar and nameservers unchanged.

## Definition of COMPLETE

A) wavefinity.org serves HTML, CSS, JS, fonts, pictures, pinned Python/Pyodide packages and WASM/static assets only; no running Python HTTP service is needed for any supported core operation.
B) The *existing* main UI designs ordinary bins, Wavefinity 7 mm and Gridfinity 21/42 mm, previews, edits features, handles all five Space types, maintains inventory and printer profiles, saves/recovers locally, generates valid individual and multipart STL and Bambu-compatible 3MF and preserves distinct first-class Print and Export actions. Print prepares validated, slicer-ready 3MF, provides a clear download/open-in-slicer handoff, and keeps honest inventory status. Core paths NEVER POST to a geometry server.
C) Final code has no network `/api/*` geometry dependency or Python HTTP process, judged by source-level inspection of caller/dispatch code and shipped static asset paths by the coding agent; the owner alone evaluates actual end-to-end operation in ordinary use. This is **not** a coder-certified empirical acceptance claim; no automated scanner, network-blocking exercise, manual application test or user QA plan. The user's GPU is optional and geometry runs on CPU. No installed Python, Wavefinity helper/server, app or extension. Bambu Studio remains optional for preparing physical prints.
D) The old Render/Python-server approach is documented sufficiently to restore deliberately if the static cutover proves defective. No registrar account credentials or secrets in the public Wavefinity repo; the private Help-Code domain record remains in Help-Code.
E) Temporary proof-of-concept page and testing-only scaffolding are removed when the core runtime replaces them. Retain required MeshGL64 build source, license, production binary and integrity metadata; do not retain testing infrastructure as a new requirement.
F) **No coder testing whatsoever:** no automated test code, fixtures, harnesses, regression suites, test runs, browser driving, testing scripts or manual test plans for the owner. Do not recreate the nine deleted tests. Code review and logical validation of implementation only; owner performs application testing separately.

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
- Direct-main process: before coding fetch and fast-forward, and immediately before publishing fetch and reconcile remote changes, inspect affected diffs for logical consistency, and push without force. Do not reset or overwrite concurrently active coder changes. No test execution.

## Owner overrides: PRINT survives, one complete cutover, no interim compatibility work

**Print is mandatory.** Do not remove, rename to Export, hide, or disable the existing Print buttons in the bin editor, individual bin selection, inventory, Storage Box, Storage Drawers, Surface/base trim, or other structural workflows. Export/Save remain separate operations. Print is an intent to *prepare and hand off a print job*, not a synonym for downloading raw geometry.

**Present behavior to retain where technically possible:** The local Windows Python version of `printModelWithReport()` in `web/app/15-generate-dialogs.js` validates, autosaves, runs `/api/print`, generates/reuses the correct 3MF files, launches an installed slicer via the native server, and updates printed status. The current hosted mode explicitly refuses Print and says to use Export. The final static edition MUST revive a working Print button in the hosted web app, not carry that refusal forward.

**Final browser Print contract:**
1. User clicks the existing **Print** button; optional bin/connector selection remains unchanged. Print snapshots the current design, Space identity and selected printer profile; flushes pending edits/resume checkpoint; validates printer limits and geometry; builds accurate, correctly arranged and named Bambu/Orca-compatible multipart 3MF files locally via the canonical engine and new 3MF packager. Same checks as the old native Print flow.
2. If a writable user folder is selected, write the prepared 3MF there using `WFFileSystem`; otherwise download it. Show a direct, prominent **Open in Bambu Studio** next-step message with the exact saved/downloaded filename; browser Downloads can open the .3mf using Windows file association, or the user can import it in the slicer. Do **not** send the user through generic Export settings after pressing Print. Preserve progress and part-selection feedback.
3. **DECIDED: retain the existing Printed state/schema; do NOT add a persistent Prepared status.** After generating/saving/downloading the 3MF, show `Print file ready — open <filename> in Bambu Studio` and an explicit `I opened it in Bambu Studio` confirmation action. Until the user confirms, status stays unchanged/not Printed. Only after confirmation for the same active Space ID/design epoch and successfully prepared file may the existing Printed status be updated. Download alone is NOT confirmed slicer handoff or a physical print. Never claim automatic slicer launch. Maintain partial-save errors, reuse and cancellation semantics. B08 owns general Print UI/ordinary status confirmation; B10 owns drawer inventory status endpoint and must apply the same rule.
4. A normal static website cannot execute an arbitrary Windows BambuStudio.exe or OrcaSlicer.exe. Do not promise an identical one-click *automatic slicer launch* without a proven, supported, opt-in registered protocol. Such a protocol is optional and must fall back to the ordinary 3MF file. **No installed Wavefinity helper, PWA, local HTTP daemon or extension is permitted**. Users may have an installed slicer because they intend to print, but installing Wavefinity is not required.
5. This one unavoidable browser-security difference is documented; preserve everything else about Print's distinct workflow and visual placement.
6. Print must be implemented for normal bins/connectors and structural Spaces. No coder browser test, slicer test, QA checklist, acceptance procedure or manual owner test plan may be written or performed. The owner will evaluate the product in ordinary use.

**Single completion gate, no halfway app:** The owner explicitly accepts a broken/incomplete app until the entire browser-only implementation is finished. Therefore remove requirements for interim browser-mode switches, simultaneous Python/browser APIs, dual hosting, or stage-by-stage functional deployments. Build final components directly by logical code inspection, WITHOUT per-package test harnesses, fixtures or test runs. Only after all B00–B13 packages are implemented is the main UI expected to work. B14 is integration and deployment, not a QA or test phase. No partial cutover, no extra workarounds to keep each intermediate package operating. Keep the old Render/Python approach in documentation and version history, but don't spend effort on maintaining two working paths.

## Required API inventory (explicit route checklist)

The original API includes routes from wavefinity_web.py, drawer_routes(...), space_routes(...) and frontend callers. B01 documents request shapes and side effects **by code reading**, including dynamically assembled routes. All reachable routes must have a **single owner** in `web/browser-core/contracts/route-manifest.json` and the [authoritative route index](Browser-only-core-source-route-index.md). A coding agent may assert source review is complete, NOT empirically certify runtime absence of network calls; the owner judges behavior through use. If a route cannot be classified from source, resolve its owner before submitting that Story; do not add automated scanners or tests.

STATIC / STATUS: GET /api/catalog, /api/health, /Brochure.md, /images/*; /api/suggestions; /api/operation-status.

PURE RULES / EDIT: /api/design/validate, /api/design/inventory-preview, /api/design/division-label-fit, /api/feature/default, /api/feature/draft, /api/feature/fit, /api/feature/apply, /api/feature/duplicate, /api/feature/delete, /api/layout/mode, /api/layout/expand, /api/pegboard/layouts, /api/pegboard/hooks, /api/sampler.

GEOMETRY: /api/preview, /api/generate, /api/connector, /api/print, /api/nest/trace, /api/nest/photo, /api/nest/retrace, /api/space/warm, /api/space/structural-design, /api/space/structural-generate, /api/space/structural-print, /api/space/structural-print-combined, /api/space/storage-box-print, /api/space/surface-print, /api/space/storage-drawers-summary, /api/space/storage-drawers-validate, /api/space/storage-drawers-reset, /api/space/storage-drawers-mutate-text, /api/space/storage-drawers-mutate.

FOLDER / SPACE / SETTINGS: /api/preferences, /api/folder/no-defined-space, /api/folder/use, /api/browse-output-folder, /api/browse-slicer-path, /api/show-log, /api/space/show-folder, /api/space/browse-storage-parent, /api/space/startup, /api/space/inspect, /api/space/other-spaces, /api/space/storage-state, /api/space/storage-plan, /api/space/storage-change, /api/space/use-untyped, /api/space/create, /api/space/configure, /api/space/create-text, /api/space/configure-text, /api/space/copy-text, /api/space/copy-name, /api/space/update, /api/space/forget, /api/space/defaults, /api/space/resume, /api/space/printer-profile.

DRAWER / INVENTORY: /api/drawer/load, /api/drawer/save, /api/drawer/report, /api/drawer/design-source/save, /api/drawer/design-source/duplicate, /api/drawer/design-source/status, /api/drawer/generate-bin, /api/drawer/surface-fill, /api/drawer/surface-fill/create, /api/drawer/spacers, /api/drawer/spacers/refresh, /api/drawer/connectors, /api/drawer/save-bins, /api/drawer/print-bins, /api/drawer/print-spacers, /api/drawer/print-complete.

AI (separately gated): /api/ai/connection, /api/ai/ask, /api/ai/prompt, /api/ai/candidate, /api/ai/repair-prompt.

DEPRECATED SERVER-ONLY: GET /api/export/<token>/<filename> becomes named local Blob transfer; local desktop executable detection/launch and opening server log/folders are removed from static mode with explicit user-facing replacement. The static deployment must contain ZERO unresolved imports of these server-only operations.

## Work packages (implement in dependency order; NO tests or testing work)

### B00 — Freeze documentation for the old Render/Python path

Requires: none.
Existing files: render.yaml, Dockerfile, wavefinity_web.py, requirements.txt, README.md, docs (create directory).
Already created: `docs/legacy-python-server-hosting.md` (do not recreate). Create only `docs/browser-runtime-architecture.md` if missing.
Patch:
1. Document the old request path (index.html -> /api/* -> wavefinity_web.py -> native engine -> temporary export URL), process start from Dockerfile/render.yaml, server-side preference/folder paths, configuration/environment variables as read from actual files (NO example secrets with values), manual rollback/deploy commands, health endpoint, evidence-gathering commands, strengths/limitations (Render sleep/RAM), and migration risks.
2. Record exact starting baseline SHA, source fingerprint and last known working Render URL; link the relevant Git commit containing the old server implementation. No branch required. Distinguish old server framework from the Python geometry engine still packaged for browsers.
3. Document new static request/data flow and keep the private Porkbun ownership/DNS record in private Help-Code, not in this public repository.
Deliverable: legacy server recovery documentation, without secrets, kept after static cutover.

### B01 — Exhaustive route mapping from existing source

Requires: B00.
Existing files: wavefinity_web.py, wavefinity_web_impl/*.py, organizer_drawer/*.py, web/**/*.js.
Create `web/browser-core/contracts/route-manifest.json` (source-derived, non-executable notes; **only canonical location**), excluding this planning-only JSON from static `dist/` if it has no runtime use.
Patch:
1. Read existing `api()`/`apiSideEffect()`/`fetch()` call sites, Python `POST_ROUTES`, `drawer_routes()`, local-only `space_routes()`, dynamic string construction and GET handlers. Use [route index](Browser-only-core-source-route-index.md) as the 92-route initial lookup, not a perfect current inventory. Record route, method, caller, handler, required fields/error shape, side-effect owner and ONE local Bxx owner. Explicitly include `/api/browse-output-folder`, `/api/pegboard/hooks`, `/api/suggestions`, `/api/space/no-inventory`, `/api/space/open`, `/api/space/delete`, `/api/folder/inventory`, `/api/drawer/spacers/generate` and any newly merged Gridfinity routes. This is source documentation only, not a scanner.
2. Derive request/response shapes, callbacks, errors and filesystem side effects from existing Python and JS code. `/api/design/validate` enters via `_validate_design_open_guard` which calls `validate_design_payload`; `/api/space/no-inventory` is the inline lambda that calls `set_inventory({...payload, inventory: False})`. Source anchors in the index are lookup hints, not ownership of the full function. Document time/file differences; no snapshots, fixtures or tests.
3. Read the manifest and every source route registry together once before Story submission; assign any new route one Bxx owner and its actual input/output contract. Explicit single-owner rule: B03 health/operation-status; B04 catalog/edit/layout/pegboard layouts; B05 preview; B06 generate/connector/sampler and replacement of export tokens; B08 ordinary Print; B09 Space/folder/preferences/`browse-output-folder`/`show-folder`/warm; B10 **all drawer routes including drawer Print** (consumes B08 shared Print); B11 structural/Storage Drawers and pegboard hooks; B12 nest/photo; B13 AI/suggestions/slicer-browse/show-log. No route co-owner, automated checker or new test requirement.
Deliverable: a complete source-derived route manifest; newly discovered implementation work is assigned to a concrete Bxx package, never deferred vaguely. No CI/checker.

### B02 — Reproducible self-hosted browser toolchain and canonical Python bundle

Requires: B01.
Existing files: `web/browser-local-poc-worker.js`, `web/browser-local-poc/bridge.py`, `web/browser-local-poc/manifold64/{bridge64.cpp,bridge64.mjs,bridge64.wasm,build.sh,LICENSE,README.md}`, `requirements.txt`, canonical engine modules. **Do not invoke/import/reuse** `browser-tests/prepare-local-poc.py`; it is historical test scaffolding removed by B16.
Create scripts/build-browser-core.py (production asset compiler), web/browser-core/vendor/manifest.json, web/browser-core/engine/canonical.zip, web/browser-core/engine/manifest.json.
Patch:
1. **Pinned proven PoC foundation:** `Pyodide 0.28.3`; built-in browser packages `numpy 2.2.5`, `shapely 2.0.7` / GEOS 3.12.1, `networkx 3.4.2`; pure-Python `trimesh-5.0.0-py3-none-any.whl` SHA-256 `51ec67d7f9f74b918f2a695da5fd511b9c084e96307648ae83f45b58f13f8009`; JS `earcut@3.0.2`; custom **Manifold MeshGL64 bridge** from Manifold C++ 3.5.0 commit `541c33bd2ab9b1a72816bdecff90566c0a3ee56c`, Emscripten `4.0.10`, CMake/Ninja, with existing source `bridge64.cpp` and `build.sh`. Native `manifold3d==3.5.2`, `numpy==2.5.2`, `shapely==2.1.2` and `opencv-python-headless==5.0.0.93` are **native pins, not browser wheel requirements**. Pin other actually needed Pyodide-compatible modules as their import graph is resolved; preserve/hash production assets in `manifest.json`. Never claim a complete full-app package list before its imports are inspected. LICENSE ships. Build source zip from current canonical files, not pinned historical PoC archive.
2. Package all Pyodide `.mjs`/`.wasm`/package wheels, JS Earcut and Python source/assets locally (no runtime calls to jsdelivr or files.pythonhosted.org). The Render static host serves `.wasm` as `application/wasm`, `.mjs` as JavaScript. **Current PoC is single-threaded**: `build.sh` uses `-DMANIFOLD_PAR=OFF` and no `-pthread`/SharedArrayBuffer. The pinned standard Pyodide worker also has no required pthread/SAB feature in this route. Consequently COOP/COEP cross-origin isolation is **not currently required**. Do not enable threaded builds without updating B14 headers/asset policy and recording the new reason. No static-server test execution.
3. Remove 42 mm-only PoC restriction, preserve float64. **Planning budgets (not measurements or acceptance tests):** first-load compressed production assets target <=64 MiB; combined Pyodide + Manifold WASM allocated linear memories target <=1536 MiB before refusing further growth/jobs with a clear capacity error; 32-bit WASM linear memory has a theoretical 4 GiB address-space ceiling per memory, but browser availability may be lower. The legacy negative PoC's observed ~22.34 MB network bytes and ~90.4 MB Python heap are NOT full-app figures. The largest Storage Box/Drawers/Gridfinity assembly's peak heap is UNKNOWN. B02 must account for full production dist asset sizes from its normal build output and reason about memory growth/large-job bounds from code; if these provisional limits make complete product support impossible, raise the concrete conflict instead of silently discarding features. Do not run benchmarks or tests.
Deliverable: pinned runtime assets, checked-in `bridge64.mjs`/`.wasm` produced by an Emscripten toolchain **outside** Render, reproducible build script for maintainers, source-generated `canonical.zip`, package/hash manifest, and float64 runtime path for supported dimensions. The ordinary 42x42 and 84x42 bins are the **entire proved geometry scope** of the November 2026 bridge; no claim that Gridfinity feet/magnets/lids, Photo Nest, Storage Box/Drawers large booleans or 3MF already work in browser. These are the main open implementation risks; coders reason through them, owner later assesses naturally. No tests added.

**B02 build chain resolution:** `scripts/build-browser-core.py` always regenerates the canonical source zip and manifest from the checked-out production code at actual static build time; the zip can be committed for convenience but is never blindly trusted when source hashes differ. The Manifold bridge `.mjs`/`.wasm` is committed and copied at deploy time; Render's static-site builder does **not** install Emscripten or call `web/browser-local-poc/manifold64/build.sh`. No build step depends on `browser-tests/prepare-local-poc.py`. Source/binary hash entries are created by the *shipping asset build* (not a test). Full-package native dependencies are researched by reading imports, with B07/12 explicit portability adapters. Render bandwidth/asset-size feasibility is addressed here from emitted production artifact sizes, not deferred to B14.

### B03 — Stable browser worker API and local dispatcher

Requires: B02.
Existing files: web/index.html, web/app/03-history-utils-catalog.js, web/app/01-runtime-state.js, web/app.js, web/app/11-parts-preview-requests.js.
Create web/browser-core/worker.js, web/browser-core/bootstrap.js, web/browser-core/local-api.js, web/browser-core/local-files.js, web/browser-core/runtime-status.js.
Patch:
1. Replace network execution at one point in api()/apiSideEffect() with the final WFLocalAPI transport; no server/browser executionMode, intermediate compatibility toggle or silent server fallback. Initialize the local engine before catalog load. Broken UI until the last package is acceptable.
2. Worker dispatch envelope: {v,job_id,path,payload,design_epoch}; returns progress, results/errors, and transferable file bytes. Preserve server-like object schemas and useful error.status/type. One worker initialization shared across calls; bounded queue for expensive geometry, cancellation via terminating/restarting worker, active design epoch guard, and release of stale file handles.
3. LocalFileStore maintains file-ID-to-Blob mapping and exposes claim()/discard()/discardAll(); never inject fake /api/export URLs. apiSideEffect operation_id behavior maps to a local operation ledger and worker progress so retries cannot accidentally duplicate side effects.
4. Do not build a hosted/browser toggle, preview deploy, or dual-stack compatibility path. Final static-only mode is the sole target; incomplete UI need not be runnable.
Deliverable: worker protocol and local dispatcher code for timeout, cancellation, error, retry, stale-result suppression, crash recovery and Blob lifetime, reviewed through control-flow analysis. Do not run browser tests.

### B04 — Catalog and pure edit/validation operations

Requires: B03.
Existing files: wavefinity_web.py (reference only), wavefinity_web_impl/_designs/*.py, web/app/02-lifecycle-ai-help.js, web/app/03-history-utils-catalog.js, web/app/10-draft-update-commit.js, web/app/11-parts-preview-requests.js.
Create `web/browser-core/engine/route-dispatch.py` with a `register_routes(routes)` API and the initial B04 route map. **B04 owns this central file during its creation; B14 alone updates it at final assembly** to import/merge B05/06/08/09/10/11/12/13 route maps. Later packages export their own `ROUTES` and **do not edit central dispatcher**. Python-owned and JS-owned routes can each be registered by the B03 local API adapter; B14 wires their final combined path table. The B14 assembly is shared integration, not a second route owner.
Patch:
1. Own `/api/catalog`, `/api/design/validate`, `/api/design/inventory-preview`, `/api/design/division-label-fit`, `/api/feature/default/draft/fit/apply/duplicate/delete`, `/api/layout/mode/expand` and `/api/pegboard/layouts`. **Do not own** `/api/health` or operation status (B03), `/api/sampler` (B06), `/api/pegboard/hooks` (B11), or any Storage Drawers summary/validation (B11). Call existing canonical source, not duplicated formulas.
2. Call original Python implementations with environment adapters rather than duplicated constants. Preserve 7 mm Wavefinity and 21/42 mm Gridfinity rules, Space fit, error shapes and feature order; include all imported source dependencies identified by reading the dispatch graph.
3. Move static catalog JSON/capability data into the generated bundle and include its version/hash. Local async call remains the same Promise resolved by api().
Deliverable: complete local equivalents for listed edit/validation operations, with request/response shapes and error paths reasoned through against the original source. No test files or test runs.

### B05 — Full core preview and editor integration

Requires: B04.
Existing files: web/app/11-parts-preview-requests.js (refreshPreview, adoptPreviewResult), web/app/12-3d-preview-render.js, web/preview3d-webgl.js, web/app/01-runtime-state.js, web/app/04-side-openings-wall-choices.js, web/app/13-layout-geometry.js.
No testing files created.
Patch:
1. Route /api/preview and any dependent nest/layout/feature previews to browser-core worker using the native canonical geometry; keep payload and returned preview_mesh/layout/status shapes compatible.
2. Preserve mutation controls, stale preview epoch logic, last-valid preview, warning banners, fit/feature errors, and exact nested_clearance/seam rules. Progress events use current preview wait UI; do not block the main thread.
3. Implement robust epoch/cancellation handling for input changes during active builds, Space switches, invalid drafts and oversized meshes. Inspect stale-result and last-valid-preview control flow logically.
Deliverable: actual main UI preview uses browser geometry, preserves geometry shape/error semantics, and makes no /api/preview calls. No coder interaction or browser acceptance runs.

### B06 — Ordinary bin, connector, STL and multiparts core

Requires: B05.
Existing files: web/app/15-generate-dialogs.js (generatePartsWithReport, saveGeneratedFiles), organizer_engine/_boxes.py, organizer_engine/_export.py, web/app/03-history-utils-catalog.js.
Create web/browser-core/engine/build-outputs.py.
Patch:
1. Route /api/generate and /api/connector through canonical Python build functions, keeping outputs and the existing dialog progress/error semantics. Implement 42x42, 84x42, wavy 7 mm and Gridfinity 21/42 bins, actual wave locking connectors and installed feature cases.
2. Return [{name,local_file_id}] file descriptors and buffer bytes, not hosted filesystem paths or ephemeral server tokens. Update saveGeneratedFiles() to save browser blobs to the already-selected writable handle or download if no folder exists; collision/overwrite prompts and all-or-nothing save logic remain.
3. Retain production mesh-validity checks (watertightness, winding, intersections, fit, sizes, naming) wherever the existing engine needs them; these are runtime output safeguards, not external tests. Preserve navigation cancellation.
Deliverable: local generation and connector paths, transferable output buffers and correct Wavefinity fit rules. Do not build test fixtures or run the app for verification.

### B07 — Exact 3MF and printer-file equivalence

**Native 3MF porting limitation:** `organizer_engine/_export.py` uses lib3mf Wrapper/CreateModel, QueryReader/ReadFromBuffer, GetMeshObjects, GetBuildItems, RemoveBuildItem, AddComponentsObject/AddComponent/AddBuildItem, GetMetaDataGroup/AddMetaData, AddAttachment/ReadFromBuffer, strict QueryWriter/WriteToFile and re-read. The actual native library XML serialization/ordering is not visible from Python; cannot claim literal XML/byte equivalence from inspection. Reimplement OPC/3MF objects, transforms, resources, Application/Title metadata, Bambu relationship `http://schemas.bambulab.com/package/2021` and `Metadata/model_settings.config` slots/names. Keep runtime validity safeguards. Isolate native `lib3mf` from the Pyodide import graph; leave historical native source available for recovery. No testing programs.


Requires: B06. MUST NOT be skipped just because STL succeeds.
Existing reference: organizer_engine/_export.py (export_bambu_compatible_3mf, export_text_body_3mf, export_assembly_3mf, export_object_groups_3mf, validate_3mf, validate_object_groups_3mf), organizer_outputs/*.
Create web/browser-core/engine/three_mf.py.
Patch:
1. Avoid native lib3mf dependency in Pyodide by implementing its currently used 3MF behaviors using Python zipfile/XML (or a proven wasm wrapper) in browser engine, without re-creating geometry formulas. ZIP must contain legal 3MF package files including [Content_Types].xml, _rels/.rels, 3D/3dmodel.model and appropriate Bambu metadata. Keep each object's vertices/triangles, transforms, names, filament assignment and settings equivalent to the Python/lib3mf output.
2. Preserve object groups, separate label/body where specified, multi-plate arrangement, all existing filament color/material/profile metadata, and output filenames. Do not merely package an STL inside a .3mf file.
3. Preserve necessary product-level 3MF structure checks and output error handling. Determine required structure, materials, object counts and transforms by reading the existing exporter; do not create a round-trip test validator, test fixture or slicer experiment.
Deliverable: browser 3MF packager implementing the existing output metadata, object grouping, transforms and material logic. No native lib3mf package or Python server required, and no coder slicer testing.

### B08 — Preserve full Print workflow and slicer-ready handoff (distinct from Export)

Requires: B07.
Existing files: web/app/15-generate-dialogs.js (printModelWithReport, saveGeneratedFiles, browseSlicer, watchServerVersion), web/printer-profile.js, web/spaces/13-printer-profiles.js, web/browser-files.js.
No testing files created.
Patch:
1. Route /api/print and reusable print operations through browser output builder. Preserve printer volume limits, part/plate packing, labels and status on inventory rows.
2. KEEP the current Print buttons and part selection dialogs. Replace only the prohibited native executable auto-launch with the Print contract above: autosave, validation, generation/reuse, arranged 3MF, save/download, explicit slicer-opening handoff. Preserve a separate Export action. Do not report "Sent to slicer" without verified proof.
3. Keep progress, cancellation, partial-save truth and the **existing Printed schema only**. Do not add a persistent Prepared field. After valid 3MF save/download, show `I opened it in Bambu Studio`; mark Printed only on explicit user confirmation with the same current design and Space ID. Replace `/api/operation-status` polling with local job status and `/api/health` with local bundle identity. No test requirements.
Deliverable: Print remains a real main-UI command with browser-side 3MF preparation, printer/Space limits, save/download, handoff guidance and honest state transitions. No coder execution or user test plan.

### B09 — Browser persistence, preferences and Space identity

Requires: B04 (B03 transitively). **B05 preview is not required for Space/persistence implementation.**
Existing files: web/browser-files.js, web/spaces/01-core.js, web/spaces/03-safe-switching.js, web/spaces/04-metadata-persistence.js, web/spaces/05-space-memory.js, web/spaces/07-welcome-folders.js, web/spaces/08-space-setup.js, web/spaces/09-event-wiring.js, web/app/02-lifecycle-ai-help.js.
Create web/browser-core/space-store.js, web/browser-core/preferences.js.
Patch:
1. Retain .wavefinity.json (current metadata version), Space ID, Wavefinity bins.md and existing File System Access/IndexedDB handle semantics as authority. No fake server paths or parallel invented database for the same Space. Use IndexedDB for preference/recovery only; persist printer and UI preferences by origin and preserve explicit export/import.
2. B09 owns `/api/preferences`, `/api/folder/*`, `/api/browse-output-folder`, `/api/space/show-folder`, `/api/space/warm`, `/api/space/startup/inspect/other-spaces/storage-state/storage-plan/storage-change/use-untyped/create/configure/create-text/configure-text/copy-text/copy-name/copy/delete/open/no-inventory/update/forget/defaults/resume/printer-profile/storage-parent/browse-storage-parent`. Reuse `WFFileSystem` and current file handle APIs; replace the old show-folder command with an in-app reveal/current-folder display appropriate to a browser. **B13 must not implement this route**. B13 owns `/api/browse-slicer-path` and `/api/show-log`, not B09.
3. Reuse existing SP and WFFileSystem functions; preserve user gestures for directory pickers. No folder selected -> design-only + downloadable files. Folder denied/revoked -> clear actionable error and do not falsely report autosave complete. No automatic overwrite or copy of user files.
4. State ownership: Space ID/design epoch guard on every asynchronous file load/write. Queue writes per folder, coalesce redundant updates, use rollback of partially generated file sets and flush on Space switch/print/export. Never allow an old Space completion to overwrite the current Space.
Deliverable: local Space and preference implementations preserve current metadata formats, space identities, file permissions, autosave and error recovery. This is a code requirement, not a request for manual or automated test procedures.

### B10 — Inventory and drawer flow parity

Requires: B06, B09.
Existing files: web/drawer-model.js, web/drawer-panel.js, web/drawer-view.js, web/spaces/06-inventory-io.js, organizer_drawer/{_core,_inventory,_report,_spacers}.py and organizer_inventory/*.py.
Create web/browser-core/engine/drawer-routes.py.
Patch:
1. Implement full route family /api/drawer/load/save/report/design-source/save/duplicate/status/generate-bin/surface-fill/surface-fill/create/spacers/spacers/refresh/connectors/save-bins/print-bins/print-spacers/print-complete, preserving shapes, touched filenames, row idempotency and deletion behavior.
2. Keep the browser folder as storage authority; do not reintroduce server-side inventory. Integrate SP.inventoryRequest's existing transactional write/rollback and bin generation stamp logic. Keep stale result guard when Space changes.
3. Preserve code paths for launch/open, create/update/delete, duplicate/move, autosave, restore, print, Gridfinity constraints and prevention of deleted-draft resurrection; inspect these transitions for logical correctness.
Deliverable: inventory and drawer UI requests route to the local engine and browser folder authority, without server API reliance. No test runs, fixture comparisons or QA plans.

### B11 — All remaining structural Space geometry

Requires: B08 and B10 (B07 transitively through B08).
Existing files: `web/structural-design.js`, `web/storage-box-form.js`, `web/storage-drawers-form.js`, `web/storage-drawers-workspace.js`, `web/spaces/10-storage-box-structural.js`, `web/spaces/11-base-trim.js`, `web/spaces/14-drawers-cabinet.js`, `organizer_outputs/space.py`, `organizer_spaces/__init__.py`, **real** `organizer_storage/{drawers.py,drawer_geometry.py,drawer_outputs.py}`, `organizer_features/gridfinity.py`, `organizer_b4b/` and relevant canonical modules (do not guess `organizer_storage/drawers/*.py`).
Create web/browser-core/engine/structural-routes.py.
Patch:
1. B11 exclusively owns `/api/space/structural-design/generate/print/print-combined`, `/api/space/storage-box-print`, `/api/space/surface-print`, `/api/space/storage-drawers-summary/validate/reset/mutate/mutate-text`, and `/api/pegboard/hooks`. `/api/space/warm` is B09 (local worker startup/no-op as appropriate); B04 must not also implement Storage Drawers summary/validate. Retain exact current Space, printer, cabinet, floor-grid, names and metadata semantics.
2. Implement Storage Box assembly/lid/hinge/latch, Drawer and Storage Drawers outputs, Surface/base trim, pegboard hooks, 7/21/42 compatibility, labels and stacking according to existing source; do not create a feature test matrix.
3. Reuse B07 3MF writer and B09 folder storage; every build uses a snapshotted Space state, returns operation progress, and cannot cross-save outputs to a different Space.
Deliverable: all structural Space and print/export routes translated to client-side execution, with original geometry and file-format behavior retained. No coder tests or fixture sets.

### B12 — Text, photo/nesting and advanced features

**Photo Nest native-library boundary:** `wavefinity_web_impl/_nest.py` delegates to `photo_nest.py`, using `cv2`, NumPy, Shapely and Pillow `PIL.Image`. The native requirements use `opencv-python-headless 5.0.0.93`, Pillow 13; Pyodide 0.28.3 offers opencv-python 4.11.0.86 and Pillow 11.3.0. Adapt only incompatible APIs by reading the source; preserve all existing contour and perspective logic. This does not prove ABI equivalence. B12 finishes edits to `web/spaces/12-space-info.js` before B13 begins.


Requires: B05 and B11 (B07 transitively).
Existing files: wavefinity_web_impl/_nest.py, wavefinity_web_impl/_designs/*, organizer_inserts/_nest/*, organizer_inserts/_text.py, web/app/11-parts-preview-requests.js, web/app/04-side-openings-wall-choices.js, web/spaces/12-space-info.js.
Create web/browser-core/engine/nest-routes.py.
Patch:
1. Implement /api/nest/trace/photo/retrace with browser File/Blob image input, browser decoder when helpful, and the authoritative image contour/shape behavior. Port only incompatible native image-processing dependencies without altering designed contour semantics.
2. Implement bores, side openings, wall choices, dividers, cradles, labels/text, scoops, pockets, post/slots/steps, hinged/lid features, photo nest and pegboard hooks with the canonical engine and packaged font/assets. Do not build a fixture matrix.
3. Connect feature editor -> preview -> export using the same original geometry calls and output shapes, without recreating an independent engine. Handle invalid user files explicitly without destructively modifying saved data.
Deliverable: advanced-feature routes use the local engine, with equivalent geometry and print/export semantics derived from original source; no /api/nest calls.

### B13 — Optional AI and intentional desktop-only capability replacements

**Browser support:** B13 shows an honest Chrome/Edge notice for browsers lacking File System Access directory pickers/handle persistence. Firefox/Safari may use safe previews and Blob downloads if available but must NOT claim durable folder/Space autosave. Do not build a second storage architecture simply for unsupported browsers.

**AI decision before Story creation:** Preserve AI Help UI, local prompt generation/candidate validation, and paste/copy workflow. If direct chat cannot be implemented safely with user-controlled credentials and browser CORS, Andrew must decide between copy/paste-only and an explicitly authorized external AI mechanism BEFORE B13 Story submission, not at B14. No API keys in static files and no secret server geometry proxy.


Requires: B08, B09 and B12. **B13 is serialized after B08 for `web/app/15-generate-dialogs.js`, and after B12 for `web/spaces/12-space-info.js`; this forbids concurrent same-file edits on main.**
Existing files: web/app/02-lifecycle-ai-help.js, wavefinity_web.py (AI handlers), web/spaces/12-space-info.js, web/app/15-generate-dialogs.js, web/app/16-suggestions.js, web/index.html.
Create web/browser-core/capabilities.js, docs/static-capability-differences.md.
Patch:
1. **Preserve AI Help, not silently disable it.** Keep existing prompt generation, candidate validation, copying/pasting provider responses, history where present, and user-facing AI Help UI. Direct AI-provider chat may call a third-party endpoint **only with a user-supplied credential, provider-supported browser CORS and explicit user action**; never expose Wavefinity-held secrets or quietly proxy through the retired Python service. **Blocking product decision before B13 Story submission:** if direct AI chat cannot be retained safely, present Andrew with the concrete limitation and choose between copy/paste-only mode or another owner-approved service design **before Stories are submitted**, not during B14. Do not let the coder decide this tradeoff. See the Velexa debate file.
2. B13 exclusively owns `/api/suggestions`, `/api/browse-slicer-path`, `/api/show-log` and browser-only UI capability notices. **B09 owns `/api/space/show-folder`**. B08 already owns the Print flow, so B13 may change only browser-native capability/slicer UI there; it cannot delete Print or its route. Preserve truthful labels and external AI privacy.
3. Ship ABOUT at `/Brochure.md` and a physical `dist/brochure.md` lowercase alias. **Unsupported browser behavior:** B13 owns a clear up-front notice for Firefox/Safari/any browser without File System Access directory handles. It may allow safe preview/Blob download where implemented but must not claim persistent Spaces, autosave or folder writes function without Chromium directory access; recommend desktop Chrome/Edge. No fake folder authority, no silent data loss. Printer profiles remain local.
Deliverable: browser-legal capabilities, accurate labels, honest AI restrictions and no embedded secret keys. No test plan.

**B11 Gridfinity and Stage 2 rule:** The [current Gridfinity master plan](Gridfinity-implementation-master-plan.md), `gridfinity-stage1-spec.md`, and merged code own the exact geometry and feature set. Preserve Space grid immutability, integer 7/21/42 cell conversions, `nominal_grid_mm` vs `physical_cavity_mm`, removable baseplate floor None/printed Floor, provisional `EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM=0.35` per side, `floor_grid=null` on None, measured-vs-unverified `seated_lift_mm`, Gridfinity pitch-specific foot/socket profiles, 7-mm nominal height units, grid lid/open rim rules, allowed stack combinations, filename pitch/unit segments and cross-grid refusals naming both grids. Preserve Stage 2 magnets, lids, side openings and whole-box stacking **only if merged into current main before Story creation**. Do not treat merely proposed Stage 2 as already shipped. Exact field ownership is pinned in the Gridfinity annex below.

### B14 — Build the complete static site; tell Andrew exactly how to cut over

Requires: all B00–B13 code implemented. No coder testing.

Existing source: `web/index.html`, `web/app.js`, `web/browser-files.js`, `wavefinity_web.py:do_GET`, `render.yaml` (old Python service), `Dockerfile` (legacy Hugging Face), `README.md`, B02 browser runtime.

Create: `scripts/build-static-site.py` (production asset copier/bundler only), `docs/static-host-rollout.md`, `docs/static-host-rollback.md`; optionally a separate static hosting config that **does not mutate old Render service**. See [Browser-only-core-diff-map.md](Browser-only-core-diff-map.md) B14 for exact paths, setup values, DNS and owner-facing handoff.

Patch (implementation, not testing):
1. Ship `dist/index.html` from `web/index.html`, approved production `web/*` UI paths at dist root, repository-root `images/` at `dist/images/`, and `Brochure.md` at **BOTH** `dist/Brochure.md` and byte-identical `dist/brochure.md`. **EXCLUDE** `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, and **ALL** `web/browser-local-poc/**`, even though B16 deletes them only later. The bridge must ship from its B02 production vendor path. Do not ship non-production source, tests or secrets.
2. Replace core HTTP with worker-local dispatch. **B14 alone finalizes `web/browser-core/engine/route-dispatch.py`**, importing each package's `ROUTES` map into B04's registry; that is shared wiring, not semantic ownership. Keep Print/Export separate, Bambu 3MF, Space state and preview. Source-review the final imports/asset paths logically, not by tests or browser automation. Specify MIME, CSP and Cache-Control in **new Render Static Site Dashboard → Settings → Headers**, using exact paths in the diff map; do not alter legacy `render.yaml`. Pinned bridge is single-threaded and does not require COOP/COEP.
3. **Choose Render Static Site** in the existing Render account, free within current bandwidth/build limits, HTTPS/custom domains, without sleeping Python process. The old Web Service cannot convert in place; prepare a NEW Static Site on `happydadto5/Wavefinity` `main`, publishing `dist` from the self-contained shipping build (provisionally `python3 scripts/build-static-site.py`). Auto-deploy OFF initially. Before a hosting change, use B02's shipping-bundle asset sizes and current Render limits; no hosting surprises deferred from B02. Do not provision or touch `render.yaml` early.
4. Preserve Porkbun registration and authoritative nameservers, apex `wavefinity.org` and `www` redirect. Existing exact live DNS record values are in PRIVATE Help-Code, not in public plans; read them when Andrew approves. Attach the domain to the NEW actual Render Static Site hostname and edit only necessary records **within Porkbun**; detach old domain association only when needed and approved. **NEVER** silently detach domains, modify DNS, change plans, disable the old service or incur charges.
5. **ASK/TELL ANDREW AT THE RIGHT TIME:** On completion, explain the final static edition no longer has Render's ~60-second sleeping Python Web Service; disclose remaining first-load browser Pyodide/WASM delay, applicable free limits and any cost; provide exact new Static Site creation settings, real new hostname, and pending Porkbun/Render domain steps. Request authorization to move the domains and retire the old service. This is an operational approval, **not a QA or user-testing checklist**.
6. If Render Static Site limits or costs are unsuitable, stop and ask Andrew; do not propose a root-domain host that requires changing Porkbun nameservers. No Cloudflare Pages apex migration, no registrar transfer, no new domain or billing changes. The replacement must continue using the existing Porkbun registrar and authoritative DNS unless Andrew explicitly changes his decision.
7. Prepare one final cutover, no half-working deployments or dual-mode runtime. Preserve legacy recovery guide and record actual last live Render Web Service source SHA. Browser persistence remains on the PC; a DNS change neither uploads nor restores user files.

Deliverable: static-only `dist/` with PoC excluded, correct brochure aliases/assets and Render header settings, complete local UI/Print, and Andrew-facing hosting approval request. Coders do not run tests or create user test plans.

### B15 — Retire old service *from execution*, retain historical documentation

Requires: B14 complete and owner acceptance.
Existing files: Dockerfile, render.yaml, wavefinity_web.py, wavefinity_web_impl/, organizer_engine/, organizer_geometry/, docs/legacy-python-server-hosting.md.
Patch:
1. **HARD PRE-RETIREMENT RECORD:** Complete `docs/legacy-python-server-hosting.md` with the **actual last deployed** Python Web Service SHA, actual old service identity/hostname, **actual final static deployed** SHA, date of authorized switch and exact source/ref restore procedure; fill full DNS/host association rollback values in PRIVATE `Help-Code/docs/wavefinity-domain.md`. No recovery-critical placeholders may remain before retiring anything. Retain canonical Python geometry for browser.
2. Only after Andrew's explicit authorization, completed rollback record and rollback window, retire the old Render Python Web Service and mark historical startup configs; keep Git history and pinned restore instructions. Update README static usage. No forced migration of user data or loss of canonical Python modules.
3. Inspect production code and import/call graph logically for HTTP fallback; failing WASM must report an error, never upload designs to the old server. This is code reasoning, **not an empirically certified zero-network claim**, automated scanner or test.
Deliverable: retired Render execution and preserved legacy source/rollback documentation with exact SHA, while canonical geometry remains packaged for browser execution.

### B16 — Remove prototype-only code and testing scaffold

Requires: B14–B15 complete.
Existing files: `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, PoC-only `web/browser-local-poc/{bridge.py,canonical.zip,reference.json,style.css}`, old `browser-tests/` historical files and `web/browser-local-poc/manifold64/*`. B14 explicitly excludes PoC paths from dist already; B16 removes source scaffolding but retains B02 production-bridged MeshGL64 files/LICENSE.
Patch:
1. Delete the superseded experimental page, isolated worker, obsolete comparison harness and testing-only fixtures; preserve production Manifold64 source, build script, license and binary by moving them to the production vendor path. No new test or fixture directories.
2. Replace outdated unsuccessful-POC notes with accurate retained history: the original failure, custom double-precision breakthrough, Windows manual confirmation and cutover. Preserve docs rather than showing obsolete "POC failed" as the current state.
3. Do not recreate the nine removed tests or add replacement automation. Coders instead inspect implementation contracts, source correctness and file paths. Retain the original history in docs only.
Deliverable: no shipped references to obsolete prototype paths, no experiment page or test scaffolding in the static bundle, and retained functional MeshGL64 runtime and geometry rules. No executed tests.

## Mandatory coding rules (NOT testing rules)

- Review source logic and modified diff for correctness, imports, asynchronous ownership, error paths, data formats and canonical geometry rules. Fix mistakes found by reading and reasoning.
- Do not write, update, repair, run or request automated tests, build test fixtures, use browsers/slicers to perform manual testing, or produce manual testing/acceptance plans for the owner.
- Preserve real application runtime validation for mesh validity, input handling, file integrity, saved state and security. These are production behaviors, not test scaffolding.
- Coders implement and report work. The owner tests the application naturally when they decide. Their feedback can drive corrections without introducing a coder testing phase.
- Intermediate packages may leave the UI broken. Do not add test gates or dual-mode compatibility layers to keep partial implementations operable.

## Authoritative dependencies and same-file serialization

This list is the **single authoritative dependency graph**. Bxx headers above must agree; Poller `start_after` uses ONLY these edges (do not create redundant transitive edges):

| Package | Direct prerequisites | Shared-file ownership / note |
|---|---|---|
| B00 | none | Legacy doc already exists; only fill gaps |
| B01 | B00 | route manifest documentation |
| B02 | B01 | canonical bundle/bridge binary |
| B03 | B02 | `app/03-history-utils-catalog.js` transport |
| B04 | B03 | creates `engine/route-dispatch.py`; pure route map |
| B05 | B04 | preview route module; no central dispatcher edit |
| B06 | B05 | owns generation changes in `app/15-generate-dialogs.js` |
| B07 | B06 | 3MF exporter only, no API route |
| B08 | B07 | owns Print changes in `app/15-generate-dialogs.js`; follows B06 |
| B09 | B04 | folders/Space/preferences; B05 not needed |
| B10 | B06, B09, B08 | owns entire drawer route group, including Print; uses shared B08 engine |
| B11 | B08, B10 | structural/Storage Drawers/pegboard hooks; no `/api/space/warm` |
| B12 | B05, B11 | photo/nest/feature integration; edits `spaces/12-space-info.js` before B13 |
| B13 | B08, B09, B12 | edits `app/15-generate-dialogs.js` **after** B08 and `spaces/12-space-info.js` **after** B12 |
| B14 | B00–B13 implemented | **sole final `route-dispatch.py` registry assembly owner**, static bundle excludes PoC |
| B15 | B14 and Andrew's explicit hosting approval | fill rollback record BEFORE old service retires |
| B16 | B15 | delete obsolete PoC files; already excluded from published dist |

Shared helper dependencies are not second API-route ownership. B10 consumes B08's Print engine but owns every drawer API handler. Each package exports `ROUTES` without editing B04's central dispatcher, which B14 assembles exactly once. Coders avoid overlapping same-file writes by following these edges; no branches/worktrees, no dual running.

Each coder assignment uses one Bxx package as its scope, reads this file and current main, implements specified files (no tests), and reports changes, limitations and commit SHA. Intermediate packages may leave the UI broken. There are NO coder tests, no test gates and no manual test plans for the user. The owner evaluates the integrated application after final delivery.

## Stop conditions / design escalations

The first implementation may reveal a genuinely impossible compatibility issue not observable from this architecture review. Do not invent product behavior, drop features, weaken tolerances, silently require installation, move visitor files into the cloud, or ship a hybrid server dependency to bypass that problem. Preserve partial progress, report the concrete affected route/feature/asset and propose the smallest compatible alternative for Andrew's decision. The primary goal and architecture are settled; only unforeseen technical blockers should require owner judgment.
