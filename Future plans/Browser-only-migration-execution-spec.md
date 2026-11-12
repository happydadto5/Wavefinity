# Wavefinity — FINAL browser-only migration execution specification

**STATUS: COMPLETE IMPLEMENTATION PLAN, NOT IMPLEMENTED.** Planning baseline: Wavefinity main on November 12, 2026. Gridfinity is still in flight; real implementation begins only when Andrew explicitly says GO and the Story-creation agent follows Future plans/Browser-only-migration-story-creation-handoff.md. This document is the **single authoritative planning entry point**. All decisions below are resolved unless a genuine technical impossibility emerges from current source.

**Delegation rule:** Future Story author: create actual Poller Stories for unfinished B00–B16 scope, including current-source Gridfinity changes, using the exact contracts and dependencies here and in Browser-only-core-detailed-build-contracts.md. Future coder: implement the assigned Story as written. Do not revisit architecture, create tests, invent product tradeoffs, or deploy partial code for compatibility. The owner accepts nonfunctional intermediate releases. NO Stories or code or DNS changes are authorized merely by reading this file.

## 1. Locked final architecture

- Existing Wavefinity application and UI stay in place. Ordinary Wavefinity bins with 7 mm waves, both 21 mm and 42 mm Gridfinity pitches, all completed Gridfinity Stage 1/merged Stage 2 capabilities, Storage Box, Storage Drawers, Drawer, Surface, Pegboard, connectors, advanced features, preview, inventory, local Spaces, and full STL/3MF output stay.
- Geometry executes on visitor CPU in **browser Worker → pinned Pyodide 0.28.3 → canonical Wavefinity Python engine → custom Manifold MeshGL64 float64 WASM**. This is NOT a rewrite to simplified JavaScript and NOT float32. All ordinary geometry and file generation are local; no Wavefinity-operated server-side geometry process and no visitor-installed Wavefinity application.
- Existing api(path,payload,opts) / apiSideEffect() callers remain stable where possible. B03 replaces the single transport with local worker + JS dispatcher. There is no Python HTTP fallback, no hybrid mode, no temporary browser/server feature flags. Files are returned as transferable binary buffers/Blobs, not /api/export token requests.
- **Print is NOT Export.** Preserve existing Print buttons, part selection, printer fit, real 3MF plate layout, progress, and status. Browser security prevents arbitrary launch of BambuStudio.exe. Print prepares a correctly assembled 3MF and saves/downloads it; the UI tells users “Open in Bambu Studio.” An explicit **“I opened it in Bambu Studio”** action changes the EXISTING Printed state only for the same current Space/design after a successful file handoff. Download alone does not set Printed. No new persistent Prepared state.
- **Static hosting is Render Static Site**, free within currently offered allowances; a NEW static site, not converting the existing Render Python Web Service. Static CDN removes the idle web-service ~60-second wake-up, although first-download/Pyodide/WASM initialization still takes time. No paid hosting change without Andrew's approval.
- **wavefinity.org registration, renewal, nameservers and DNS management stay at Porkbun.** No registrar transfer, nameserver migration, Cloudflare Pages root-domain alternative or second domain purchase. At authorized cutover, adjust only necessary DNS records **inside Porkbun** and move Render domain associations. Actual values stay in PRIVATE happydadto5/Help-Code/docs/wavefinity-domain.md, not public migration Stories.
- **AI Help product choice is resolved: direct browser AI chat using the USER'S OWN key when their provider permits browser calls, with manual copy/paste fallback always available.** Existing prompt, candidate checking, repair, history, editing and UI remain. No site-held provider key, no mandatory server proxy, no silent AI feature deletion. Key defaults to session memory only. Key security, provider CORS and optional external prompt sharing are stated honestly.
- Full persistent Space/folder use targets **Windows desktop Chrome and Edge** (File System Access API). Unsupported browsers see an early capability warning BEFORE Space creation/write/autosave; they may use only safe ephemeral previews/Blob downloads. Recovery: open wavefinity.org in Chrome/Edge and select the original folder or import an explicit B09 Space/preferences export in a supported browser. No cross-browser automatic handle/data transfer is promised.

## 2. Source references, priority and minimal reading

Primary files:
1. **THIS FILE:** final decisions, interface contract, exact work order, cutover.
2. Future plans/Browser-only-core-detailed-build-contracts.md: B00–B16 exact file edits, methods, data/state ownership and 17-package dependency table.
3. Future plans/Browser-only-core-diff-map.md: before/after patches, actual function anchors, bundled assets, static response headers, Gridfinity matrix.
4. Future plans/Browser-only-core-source-route-index.md: 92 historical API paths with exactly one owner; 91 local, one retired export-token pattern. Refresh current route inventory at GO.
5. gridfinity-stage1-spec.md; Future plans/Gridfinity-implementation-master-plan.md; **CURRENT merged code at GO** controls final Gridfinity model and Stage 2.
6. README.md section 3: NO CODER TESTING; docs/legacy-python-server-hosting.md: recovery; private Help-Code domain record only for final authorized hosting.

**Read only the relevant assigned Bxx, its row in the diff map, matching route rows, and the current source paths.** Do not consume the entire repository/research history repeatedly. Literal line numbers are navigation aids only; live Gridfinity changes can shift them. Reconcile function names and schemas, not merely filenames.

## 3. Route contract — compile-time completeness and fail-closed runtime

B01 creates canonical machine-readable web/browser-core/contracts/route-manifest.json. Each entry has:
~~~json
{
  "path": "/api/preview",
  "method": "POST",
  "owner": "B05",
  "disposition": "local",
  "runtime": "python",
  "module": "preview_routes",
  "handler": "preview_payload",
  "input_fields": ["design"],
  "output_fields": ["preview_meshes"],
  "effects": "read-only geometry; stale epoch protected"
}
~~~
The fields above illustrate the **manifest schema**; B01 must use exact real handler/field names from current source, not treat these illustrative arrays as the authoritative /api/preview payload. For a retired path, disposition=retired, runtime/module/handler=null and a required replacement description. The legacy GET /api/export/<token>/<filename> is RETIRED → local_file_id/Blob. Other source-index rows are local as assigned. Include newly introduced Gridfinity paths at GO, with precisely one owner.

B04 creates web/browser-core/engine/route_dispatch.py with register_routes(ROUTES) and explicit fail-closed behavior. B05/B06/B08/B10/B11/B12/B13 Python modules export their own Python ROUTES; B09 and the browser-provider half of B13 export JS ROUTES. B14 is the **only** final integration editor of route_dispatch.py and B03 local-api.js.

**B14 shipping-build invariant (part of compiling the product, not a test):**
- The 92-row index is a frozen starting reference, not a fixed final handler count. B01 updates BOTH index and manifest to reflect current source, including all new routes, then later package Story scope is assigned to each.
- B14 generates a single flat final route declaration used by the runtime from the Python and JS registrations, and scripts/build-static-site.py compares it to the B01 manifest and current source-route-index route rows.
- Every manifest **local** row must appear **exactly once** in a Python OR JavaScript runtime registration with matching owner/runtime/module; every **retired** row must appear in the manifest/index but in NO callable registry and must name its local replacement. Build aborts on missing, duplicate, extra, unclassified, unavailable module/file or mismatch. Do not demand 92 callable entries; one historical entry is deliberately retired.
- This compile-time declaration comparison does not prove that the code works, that a dynamic request cannot fail or that no runtime packet escapes. It is production contract integrity, not a scanner, test harness, browser driving, or QA.
- Worker and WFLocalAPI MUST NEVER network-fallback for an unregistered/retired /api path. Return regular local error kind UNSUPPORTED_LOCAL_OPERATION and a clear unavailable-feature message. This guard is actual production error handling.

One semantic owner per path: B03 health/job status; B04 catalog/editor/feature/layout/pegboard layouts; B05 preview; B06 generate/connector/sampler plus retired token replacement; B08 /api/print; B09 folders/Space/preferences/show-folder/browse-output-folder/warm; B10 ALL drawer paths including drawer print; B11 structural, Storage Drawers and pegboard hooks; B12 Photo Nest; B13 AI/provider, suggestions/slicer browse/show-log. B08 shared Print helpers are NOT a second B10 route owner.

## 4. Locked implementation order and exact package boundaries

The following is the **minimal, transitively reduced direct dependency graph**. Poller `start_after` records ONLY listed direct prerequisites (plus actual Story IDs if package division changes), with no redundant edges. B14 follows B13, which transitively requires completion of B00–B12. B15 and B16 are NOT authorized to retire/deploy prematurely.

| Package | Direct dependencies | Existing function/file anchors and exact implementation deliverable |
|---|---|---|
| B00 | none | docs/legacy-python-server-hosting.md **already exists**. Fill genuinely missing source/recovery documentation only; preserve legacy Render/Python history. Do NOT invent yet-unknown deployed SHA/hostname/date. |
| B01 | B00 | wavefinity_web.py POST_ROUTES/GET and guards, organizer_drawer/__init__.py:drawer_routes, organizer_spaces/__init__.py:space_routes, JS api/apiSideEffect/fetch callers. Build source-derived manifest of all routes, schemas, errors and side effects. Update frozen route index for final Gridfinity main. No tests/scanners. |
| B02 | B01 | Source web/browser-local-poc-worker.js, browser-local-poc/bridge.py and manifold64/bridge64.cpp,mjs,wasm,build.sh/LICENSE. Create scripts/build-browser-core.py and web/browser-core/{vendor/,engine/canonical.zip,engine/manifest.json}. Vendor pinned Pyodide+wheels+MeshGL64. Regenerate canonical.zip from checked-out source during shipping build; copy committed precompiled bridge binary; never compile Emscripten on Render or run browser-tests/prepare-local-poc.py. |
| B03 | B02 | Source web/app/03-history-utils-catalog.js:api/apiSideEffect, web/app.js:init and web/index.html bootstrap. Create web/browser-core/{worker.js,bootstrap.js,local-api.js,local-files.js,runtime-status.js}. Versioned job messages, request IDs, stale epochs, cancellable worker, progress, local operation ledger, transferable ArrayBuffers and Blob lifetime; no network fallback. |
| B04 | B03 | Source wavefinity_web.py:_validate_design_open_guard; wavefinity_web_impl/_designs/_preview.py:validate_design_payload; _features.py:default_feature_payload/draft_payload/feature_fit_payload/apply_feature_payload/duplicate_feature_payload/delete_feature_payload/mode_payload; _layout.py:expand_layout_payload/inventory_preview_payload/pegboard_layouts_payload. Create engine/route_dispatch.py. Pure edit/catalog/layout/grid validation routes only. Add local unsupported-route failure. B14 integrates other registries later. |
| B05 | B04 | web/app/11-parts-preview-requests.js:refreshPreview/adoptPreviewResult/invalidatePendingPreview, 12-3d-preview-render.js and structural-design.js:refreshStructuralPreview. Create engine/preview_routes.py with /api/preview Python ROUTES. Preserve original renderer, epochs, last-good mesh and preview warnings; do not reconstruct preview formulas. |
| B06 | B05 | web/app/15-generate-dialogs.js:generatePartsWithReport/saveGeneratedFiles, wavefinity_web.py:generate_payload/connector_save_payload/sampler_payload, organizer_engine/_boxes.py. Create engine/build_outputs.py with B06 route map and local byte/file-ID conversion; no temp server paths or /api/export tokens. Preserve ALL current grid/connector/naming rules, not just 42×42 PoC. |
| B07 | B06 | **BOTH** organizer_engine/_export.py and plate_layout.py:plan_plate/_plan_bounds/pack_mesh_objects/_placement_move/_move_file/space_out_for_plate/combine_for_plate. Create engine/three_mf.py and engine/plate_layout.py (or equivalent named interface). Replace native lib3mf dependency in browser import graph with 3MF ZIP/XML output and preserve separate normal-export and combined-plate formats; details section 5. |
| B08 | B07 | web/app/15-generate-dialogs.js:printModelWithReport/chooseIndividualBinPrint/updatePrimaryPrintButtonLabel, printer profile/structural Print buttons. Create engine/print_routes.py. Keep all Print actions separate, true multipart 3MF/bed arrangement, user confirmation before marking existing Printed; remove hosted refusal and native executable launch. |
| B09 | B04 | web/browser-files.js:WFFileSystem, web/spaces/{03-safe-switching,04-metadata-persistence,05-space-memory,07-welcome-folders,08-space-setup}.js, organizer_spaces/__init__.py. Create browser-core/{space-store.js,preferences.js} JS local ROUTES. Folder/Space/preference, metadata, files, autosave, explicit export/import and immutable grids. |
| B10 | B08,B09 | web/spaces/06-inventory-io.js:SP.inventoryRequest, web/drawer-model.js, organizer_drawer/__init__.py:drawer_routes, organizer_inventory/*.py. Create engine/drawer_routes.py. Own every /api/drawer/* including print-bins/print-spacers/print-complete; reuse B08 printer/3MF engine, user-confirmation semantics and B09 browser file authority. |
| B11 | B10 | web/structural-design.js, web/spaces/{10-storage-box-structural,11-base-trim,14-drawers-cabinet}.js, organizer_storage/{drawers.py,drawer_geometry.py,drawer_outputs.py}, organizer_b4b/, organizer_features/gridfinity.py. Create engine/structural_routes.py. Own ALL structural/Storage Drawers/Storage Box/Surface print paths and pegboard hooks. Preserve full 7/21/42 geometry, container floors and all merged Stage 2 features. |
| B12 | B11 | wavefinity_web_impl/_nest.py:nest_retrace_payload, photo_nest.py:decode_image_data/retrace_outline_from_rectified, organizer_inserts/_nest/, organizer_inserts/_text.py, web/app/11-parts-preview-requests.js, web/spaces/12-space-info.js. Create engine/nest_routes.py. Port OpenCV/Pillow/NumPy/Shapely native interfaces, preserve contour/warping, text, dividers and advanced features. Complete space-info.js edits before B13. |
| B13 | B12 | web/app/02-lifecycle-ai-help.js:aiConnectionRefresh/aiConnectionAction/aiAsk/aiPasteManually; wavefinity_web.py:ai_* payloads, wavefinity_web_impl/_ai.py, web/app/15-generate-dialogs.js:browseSlicer/showAboutDialog, web/spaces/12-space-info.js. Create browser-core/capabilities.js, ai-providers.js, engine/ai_routes.py and docs/static-capability-differences.md. BYOK chat with session-memory default; manual fallback, honest browser notices, no secret server proxy. |
| B14 | B13 (implies B00–B12) | scripts/build-static-site.py, docs/static-host-rollout.md, docs/static-host-rollback.md. **Only final shared registry assembler**. Copy approved production web/* to dist root, root images/* to dist/images/* and Brochure.md to dist/Brochure.md **and** dist/brochure.md. Explicitly EXCLUDE browser-local-poc.html, browser-local-poc.js, browser-local-poc-worker.js and entire web/browser-local-poc/ directory. Add normal build route-integrity check; Render Static Site headers/config and one final owner authorization prompt. No domain changes yet. |
| B15 | B14 + explicit Andrew cutover approval | Before retiring anything, record last ACTUALLY deployed legacy Render Web Service SHA, last/static deployed SHA, switch date/hostname, restoration commit/source and private old/new Porkbun DNS and Render domain association. Fill legacy and private recovery docs, then retire old Python web execution without deleting canonical geometry/source history. |
| B16 | B15 | **Delete ALL automated test code and testing infrastructure**: entire `tests/` directory, entire `browser-tests/` directory (including harnesses, test HTML, evidence fixtures and preparation scripts), root `run_tests.py`, any other test-only scripts/fixtures/CI invocations found by reading current source, and obsolete PoC HTML/JS/worker and `web/browser-local-poc/` experiment tree. Remove test commands/links from README, package/build/CI configs and docs; preserve only relevant historical evidence in ordinary documentation and production MeshGL64 cpp,mjs,wasm/LICENSE. B14 already excludes all test/PoC materials from dist. **No tests, runners or replacement QA scripts remain in the final repository.** |

**Parallel-track safety:** B06 and B08 touch app/15-generate-dialogs.js but B08 follows B07→B06. B13 follows B08 for the same file and B12 for spaces/12-space-info.js. B10 must consume shared B08 Print before implementing drawer Print. B04's dispatcher is edited next only by B14. Direct-to-main, no branches/worktrees/force pushes; reconcile latest main and inspect changed diffs before commit.

## 5. Critical file formats, geometry and browser constraints

### Native exporter vs print plate (B07: do not merge their semantics)

Existing organizer_engine/_export.py uses native lib3mf and maintains named mesh objects, component groups, identity transforms, Application/Title metadata, Bambu relationship http://schemas.bambulab.com/package/2021, and Metadata/model_settings.config with per-part name/identity matrix/extruder slot. Ordinary body uses slot 1; separated lettering defaults to slot 2; a part on slot 1 omits explicit extruder metadata. Its C-library serialization bytes/order are not visible through Python. Preserve **structure and meaning**, never claim byte identity from source.

Existing plate_layout.py has a second path:
- plan_plate/_plan_bounds/pack_mesh_objects: printer fit, plate margins, 10 mm default gap, shelf arrangement and optional 90° rotation.
- _move_file: copy an existing 3MF archive member-for-member, changing only the 3D model build item transforms using row-vector composition (existing transform multiplied by placement transform); original design file remains unchanged.
- combine_for_plate: merge models from source packages, renumber resource IDs starting at 1, uniquify names, remap component objectid/pid, Bambu config object/part IDs and names, compose build transforms while preserving original mesh data/component transforms. Output is EXACTLY four ZIP members: 3D/3dmodel.model; Metadata/model_settings.config; [Content_Types].xml; _rels/.rels. **No ordinary-export Bambu attachment relationship and no Application/Title stamp** in this merged output; the config is a plain member. These differences are required native behavior, not bugs.
- Retain runtime 3MF validity/format integrity and errors; no separate test files, roundtrip harness, coder slicer execution or owner testing instructions.

### Gridfinity invariants across all packages

Source at GO is authoritative; do not revive pre-Gridfinity generic 21/42 behavior. Preserve: grid recorded on every design; immutable Space grid once created; No-Space bin chooses its grid; 21/42 horizontal unit entry, **7 mm height units for either Gridfinity pitch**; Wavefinity 7 mm waves unaffected; flat Gridfinity walls/foot/socket/stacking lid profiles each pitch distinct; open rim and stacking lid eligibility, nominal whole-unit assembled height; Gridfinity pitch and nominal unit segments in file names/readouts and AI text; cross-grid refusal names BOTH grids on every new/duplicate/import/resume/placement/AI entry path; layout snapping uses Space grid.

Containers: built_in_grid Floor vs None; floor_grid=null for None; nominal_grid_mm is exact cell grid while physical_cavity_mm includes provisional EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM=0.35 per side for external third-party plate; preserve separate measured seated_lift_mm (unknown/unverified NOT zero, zero is a valid recorded measurement) through one shared accessor and fit status; printed container floor sockets match pitch, minimum base 5.8 mm or 8.3 mm over Storage Box underside stacking recess where current source requires. Never represent provisional physical compatibility as established. Include Stage 2 magnets, lids, side openings, whole-box stacking and variants ONLY if actually merged when Story creation begins.

### Browser/WASM assets and known unproved risks

Pins: Pyodide 0.28.3; browser NumPy 2.2.5, Shapely 2.0.7/GEOS 3.12.1, networkx 3.4.2; Trimesh 5.0.0 wheel SHA256 51ec67d7f9f74b918f2a695da5fd511b9c084e96307648ae83f45b58f13f8009; JS Earcut 3.0.2; Manifold C++ source 3.5.0 commit 541c33bd2ab9b1a72816bdecff90566c0a3ee56c, custom MeshGL64 float64 bridge, Emscripten 4.0.10. Native Python requirement versions are different from browser wheels. Bundle all needed runtime assets locally; not downloaded from a third-party CDN at runtime. B02 vendor manifest and canonical source zip are built from current source, not an isolated historical 42 mm archive. Bridge .wasm/.mjs precompiled and committed; Render does not install Emscripten or depend on historical browser test generators. Bundle exact required fonts.

Current bridge is single-threaded (MANIFOLD_PAR=OFF, no pthread/SAB); **no default COOP/COEP**. Production static host serves .wasm as application/wasm and .mjs as JavaScript with version-aware Cache-Control and CSP allowing current WASM compilation. Place headers in the NEW Render Static Site Dashboard, not the OLD render.yaml; see diff map for exact paths and baseline CSP.

Planning targets, NOT proven performance claims: <=64 MiB compressed cold assets, <=1536 MiB combined allocated WASM linear heaps; WASM32 single memory address space max 4 GiB, practical/browser limits lower. B02 production asset accounting evaluates host size/allowance before B14. The proof of concept covered ordinary 42×42 and 84×42 bins, NOT Photo Nest, advanced Gridfinity feet/lids/magnets, largest assemblies or multipart 3MF. B07 native lib3mf and B12 native OpenCV+Pillow represent independent import/format risks; do not pretend they are solved merely because ordinary STL succeeded. Code-level capacity/error handling is production functionality, not testing.

### AI Help BYOK exact safety and UX

Keep existing AI Help fields (name, URL/provider, model, key), status/test/save, prompt, ask, manual paste, repair, candidate proof/accept/modify and new-bin. B13 makes provider adapters in browser JS:
- OpenAI-compatible /chat/completions (Bearer key) when the chosen HTTPS provider allows explicit user-supplied browser access.
- Anthropic /v1/messages, x-api-key + anthropic-version + anthropic-dangerous-direct-browser-access: true; some organizations still reject browser CORS.
- Gemini generateContent only where the provider permits browser access for this user credential and the user accepts its key risk; never claim universal browser key security.

Key lives in JS session memory by default, not persistent plaintext localStorage; persist only nonsecret provider/model settings. Optional persistent-key storage is NOT required and must never be enabled without a user-facing informed opt-in and clear/remove control. Don't log key or put in URL/ZIP, worker messages to untrusted paths, exceptions, telemetry or shipped assets. Block key forwarding on redirects. Show realistic credential-exposure and provider-billing warning; user explicitly starts requests. Some prompts include design/Space descriptors sent to user's selected AI provider: never claim *all* design data remains local when user invokes AI. Actual meshes and STL/3MF rendering remain on visitor PC. If provider CORS/key policy blocks direct chat, show specific error and retain copy/paste—not an unrelated downgrade or server-proxy workaround. Any new AI provider means explicit supported-origin CSP adjustment.

### Unsupported browser path

B13 feature-detects reliable File System Access folder handles before ANY Space create/write/autosave; show unsupported-folder notice and disable misleading actions. Existing folder/data is still on user's machine; opening same URL in supported Chrome/Edge then selecting original folder is the primary recovery. A B09 explicit preferences/Spaces export file can be imported in a supported browser. Blob-only exports/previews may remain available in an unsupported browser, clearly without autosave guarantees.

## 6. Build and hosting exact outputs / owner handoff

Production build command should be a single reproducible invocation, provisionally:

~~~shell
python3 scripts/build-static-site.py
~~~

That production script invokes scripts/build-browser-core.py, regenerates canonical.zip and checks its source hashes/production vendor asset integrity, creates clean dist, copies all approved web paths at root and the root images/Brochure aliases, refuses any PoC/test-only paths in shipping assets, and verifies the route manifest/index against assembled runtime declarations. **This is product compilation/integrity checking, not a testing phase.**

Ship at least: dist/index.html, app/, spaces/, regular CSS/JS/icon files, browser-core worker/bootstrap/local API, canonical.zip+manifest, pinned self-hosted Pyodide packages+WASM bridge, dist/images/, dist/Brochure.md and dist/brochure.md. Explicit exclusions: web/browser-local-poc.html, web/browser-local-poc.js, web/browser-local-poc-worker.js, all web/browser-local-poc/**, browser-tests/, tests/, run_tests.py, Future plans/, server secrets, old Python HTTP entrypoint and unrelated Git metadata. B16 later deletes prototype source, not needed for exclusion at B14.

Render Static Site settings after **Andrew approves the hosting action**: connect existing GitHub Wavefinity main, NEW Static Site (name if available wavefinity-static), publish directory dist, build command above if supported, auto-deploy decision approved by Andrew, custom domain wavefinity.org + www, HTTPS/redirect, no server runtime and no geometry edge functions. New static service has its own actual *.onrender.com hostname read from Dashboard. Headers configured through NEW Static Site settings:
- /*: X-Content-Type-Options nosniff, Referrer-Policy no-referrer, X-Frame-Options DENY, source-constrained CSP as in diff-map.
- /*.wasm and /**/*.wasm: Content-Type application/wasm; similarly JS MIME for *.mjs.
- index.html and other unversioned JS/worker/source archive: Cache-Control no-cache; only explicitly content-hash-named assets may get max-age=31536000,immutable.
- No COOP/COEP for current unthreaded bridge. Review CSP against actual source imports without running app tests.

**Critical operational separation:** B14 produces the static artifact and tells Andrew what to authorize. It does not silently create hosting, detach domains, modify Porkbun, incur fees or switch live traffic. During approved cutover preserve Porkbun registration and authoritative DNS; edit only needed records there and move domain association from OLD Render Web Service to NEW Static Site. The initial apex record may stay IF current Render documentation still requires it; www CNAME uses new actual site hostname. These precise live DNS values and credential-safe rollback steps are private in Help-Code. No nameserver moves, domain repurchase or Cloudflare root-domain transfer.

**B15 HARD before-retirement record:** obtain actual last deployed Python Web Service SHA and hostname, actual deployed static SHA and hostname, switch date, exact restore source/ref, existing/new Render service identities/domain associations and private old/new Porkbun DNS records with reversal steps. Fill docs/legacy-python-server-hosting.md and Help-Code private record before retiring old service, with explicit Andrew approval. If any is unknown, DO NOT retire. B16 then removes **ALL** remaining test source/infrastructure (`tests/`, `browser-tests/`, `run_tests.py`, all other test-only files and references) and historical PoC source after B15, retaining only production MeshGL64 and historical prose/license.

## 7. Code-policy and truthfulness limits

Wavefinity is an OWNER-TESTED APPLICATION. Future coders do not write/update/repair/run any automated tests, do not run legacy suites, do not perform browser/slicer/manual application tests, do not create user test plans or QA checklists. They **do** inspect code, trace imports/data flow/state/route dispatch, validate logic and output invariants, handle errors correctly, maintain production mesh/3MF/input checks, and review each changed diff. The normal static build may reject an incomplete route/asset manifest; that is the app's shipping integrity, NOT a new test suite. No new test Stories or fixtures. Do not claim the app was empirically proven by source reading.

Implementation cannot be guaranteed error-free before code is written. Therefore:
- **Known, resolved**: destination architecture, every current route's semantic owner, direct dependencies, source anchors, 3MF normal/plate differences, user-acknowledged Print, AI Help BYOK/default key storage, unsupported-browser behavior, static hosting/Porkbun, rollback gate, no tests.
- **Intentionally unresolved factual unknowns, not coder design decisions**: final merged Gridfinity Stage 2 code at Andrew's GO; full production package sizes and largest-job memory; browser support for every canonical native import; real Bambu slicer interpretation of new 3MF, and account-specific Render/DNS values before cutover. These must be handled by preserving source contracts, normal production compiler/error logic, and reporting concrete blockers—not by silent feature deletion, guessing, tests or unilateral hosting moves.
- Coders must not downgrade wavy geometry, layouts, storage, Gridfinity, Print, or AI Help to make an intermediate piece runnable.
- Final coder report: changed files, implemented behavior, unavoidable deviations/blocked product capability and pushed commit SHA. No “tests run” or user QA instructions.

## 8. Delegation (the only instruction Andrew needs at GO)

When Gridfinity is finished and Andrew wants **Stories created** (not code implemented), send the next agent exactly:

**Read and execute Future plans/Browser-only-migration-story-creation-handoff.md in happydadto5/Wavefinity exactly as written.**

That handoff reads THIS authoritative spec, reconciles current main and produces the actual dependent implementation-ready Poller Stories with specific file/function edits and no testing. The separate Poller coding agents then implement those Stories in dependency order. Implementation cannot begin merely because this plan was committed.
