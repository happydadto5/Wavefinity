# Wavefinity browser-only migration — change-by-change implementation map

**DOMAIN OWNERSHIP/DNS LOCK (owner decision, 2026-11-12):** The domain `wavefinity.org` **stays registered, paid and renewed at Porkbun**. Keep **Porkbun authoritative DNS/nameservers**, too. No registration transfer, registrar change, Cloudflare nameserver switch, additional domain purchase or domain renewal payment. **Render Static Site is the selected hosting path**, with a new static site under the existing Render account. At final cutover only, request Andrew's permission to adjust the necessary existing DNS **records within Porkbun** (for example the `www` CNAME) and move the custom-domain association between Render services; the already-configured apex A `<read private Help-Code apex A>` should remain if Render continues specifying it. These are routing changes, not registrar/DNS hosting transfers. A fallback host requiring moving nameservers is **out of scope and not to be proposed** without Andrew specifically reversing this rule. Document the actual record edits in private Help-Code, not public registration/account details.


**Purpose:** Minimize coder rediscovery and token use. This is the implementation supplement to [Browser-only-core-detailed-build-contracts.md](Browser-only-core-detailed-build-contracts.md), not a test or QA plan. Frozen technical reference: Wavefinity source around the November 12, 2026 Gridfinity migration. Resolve target functions in current `main` before editing; line numbers are *navigation hints*, not immutable patch offsets.

**NO CODER TESTING:** Per README.md, coders implement and logically inspect source/diffs; no automated or manual application tests, testing scripts, fixtures, user QA plans, or interim working builds. Do not create a Story until Andrew finishes Gridfinity and explicitly says **go**. Coders must not change live DNS or retire Render until Andrew authorizes the final cutover.

## Hard destination decisions

- Existing `web/index.html` UI unchanged in intent and layout. All ordinary bins, Wavefinity, final Gridfinity variants, Storage Boxes, Storage Drawers, Drawer, Surface, Pegboard, inventory, all features, previews, STL, multipart 3MF, and first-class **Print** move to browser/PC.
- Browser executes canonical Python using pinned, **self-hosted** Pyodide; custom `MeshGL64` Manifold WebAssembly handles float64 geometry. Zero Wavefinity cloud geometry APIs. Do not reimplement waves/clearances or use float32 shortcuts.
- Existing `wavefinity.org` is served by a **static CDN**, not a Python web service. **DEFAULT HOST: Render Static Site (free tier, subject to bandwidth/build allowances)**. Separate *new static site* must be created; Render cannot convert the existing Web Service into a Static Site in place. First browser asset load and WebAssembly/Python initialization may take time; **no idle web-service 60-second wake-up**.
- Render Static is favored because Porkbun DNS already points apex `wavefinity.org` at Render's `<read private Help-Code apex A>`; `www` currently CNAMEs `<read private Help-Code old Render hostname>`. At final switch, root A may remain but domain association must move to the new Render Static service and `www` must target the **actual new static-service hostname**, as shown by Render—not an invented value. Detach the custom domains from old Web Service when Render requires it, associate both on new Static Site, wait for TLS, confirm redirect, then retire old service *only after Andrew approves*.
- **Cloudflare Pages is not an approved fallback:** its apex configuration requires changing authoritative nameservers, and Andrew explicitly wants to keep Porkbun registration and DNS management unchanged. If Render Static is unsuitable, do not propose nameserver changes; ask Andrew about another static host compatible with Porkbun DNS.
- Browser print limitation: static site cannot arbitrarily start `BambuStudio.exe`; **keep Print** and all its checks/status, save/download correct Bambu/Orca 3MF, then show a concise `Open in Bambu Studio` handoff. Export stays separate. Do not claim automatic slicer launch, and do not require a Wavefinity-installed app/helper/extension.
- Full application may be nonfunctional during migration. **No dual Python/browser mode, no half-release compatibility layers. One final static-site cutover.**
- Keep old server architecture and recovery documentation in `docs/legacy-python-server-hosting.md`; its existing source remains in Git history. Private Porkbun/domain/account record stays in private Help-Code `docs/wavefinity-domain.md`.

## Exact source change map (B00–B16)

| Package | Existing ownership anchors | Required concrete edit / new production file |
|---|---|---|
| B00 | `render.yaml`, `Dockerfile`, `wavefinity_web.py`, `docs/legacy-python-server-hosting.md` | Legacy hosting record **already exists**. Refresh only if server startup or rollback instructions have changed. Record last actually deployed server SHA at final cutover. Do not recreate documentation. |
| B01 | `wavefinity_web.py:POST_ROUTES` near line 3486; `organizer_drawer/__init__.py:drawer_routes` near 331; `organizer_spaces/__init__.py:space_routes` near 473; JS `api` callers | Read the 92-entry source-route index and current handlers. Create ONLY web/browser-core/contracts/route-manifest.json (source-derived notes, one Bxx owner per path). Include local-only space_routes, dynamic routes, caller/handler request and error fields. No scanner. |
| B02 | `web/browser-local-poc-worker.js`, `web/browser-local-poc/bridge.py`, `web/browser-local-poc/manifold64/*`; canonical Python engine | Pin Pyodide 0.28.3, Manifold C++ commit 541c33bd2ab9b1a72816bdecff90566c0a3ee56c and Emscripten 4.0.10; create shipping build-browser-core.py, canonical.zip, version/hash manifest and self-hosted vendor assets. Canonical.zip regenerated from current main during production build; precompiled committed bridge64 binary is copied, never compiled on Render. No browser-tests/prepare-local-poc.py. |
| B03 | `web/index.html` bottom script block near lines 1154–1199; `web/app/03-history-utils-catalog.js:api` near 369 and `apiSideEffect` near 587; `web/app.js:init` | Create `web/browser-core/{worker.js,bootstrap.js,local-api.js,local-files.js,runtime-status.js}`. Add bootstrap script **after browser-files.js and before app runtime scripts**. Keep `api(path,payload,options)` public signatures; replace underlying fetch/HTTP with `WFLocalAPI.call(path,payload,options)`. No server fallback. |
| B04 | `wavefinity_web.py` routes; `wavefinity_web_impl/_designs/{_features,_layout,_preview}.py`; JS catalog/draft/fit callers | Use wavefinity_web.py:_validate_design_open_guard -> wavefinity_web_impl/_designs/_preview.py:validate_design_payload; _features.py:default_feature_payload,draft_payload,feature_fit_payload,apply_feature_payload,duplicate_feature_payload,delete_feature_payload,mode_payload; _layout.py:expand_layout_payload,inventory_preview_payload,pegboard_layouts_payload. Create route-dispatch.py registration API with B04 pure routes. B14 alone assembles final registry; B04 does not own health, sampler, pegboard hooks or Storage Drawers. |
| B05 | `web/app/11-parts-preview-requests.js:refreshPreview` ~727, `adoptPreviewResult` ~557, `invalidatePendingPreview` ~482; `web/structural-design.js:refreshStructuralPreview` ~345; `web/app/12-3d-preview-render.js` | Route preview requests to worker. Preserve current request generation/epoch, latest-only application, last good mesh, warnings/progress, structural preview behavior; do not rewrite WebGL renderer. |
| B06 | `web/app/15-generate-dialogs.js:generatePartsWithReport` ~111, `saveGeneratedFiles` ~658; `wavefinity_web.py:generate_payload` ~1731 and `connector_save_payload` ~2072 | Create browser-core/engine/build-outputs.py and ROUTES for generate/connector/sampler; replace /api/export tokens with transferable Blob IDs. Source web/app/15-generate-dialogs.js:generatePartsWithReport/saveGeneratedFiles and wavefinity_web.py:generate_payload/connector_save_payload/sampler_payload. Preserve actual Gridfinity feet and filename segments. Do not edit central dispatcher. |
| B07 | `organizer_engine/_export.py`: native `lib3mf` currently imported at top; `export_*_3mf` and `validate_3mf` functions | Source organizer_engine/_export.py:export_bambu_compatible_3mf,_model_settings_config,_object_groups_model_settings_config,export_text_body_3mf,export_assembly_3mf,export_object_groups_3mf,validate_3mf. Create browser-core/engine/three_mf.py implementing 3MF OPC XML/ZIP, part resources, component/build items, transforms, Bambu model_settings.config and filament mapping. Isolate native lib3mf import from browser module graph; byte-level equivalence cannot be inferred from native C library. |
| B08 | `web/app/15-generate-dialogs.js:printModelWithReport` ~406, `chooseIndividualBinPrint` ~579, `updatePrimaryPrintButtonLabel` ~607; `web/spaces/10-storage-box-structural.js:SP.printStorageBox` ~269; `web/spaces/11-base-trim.js:SP.printSurface` ~328; `web/spaces/14-drawers-cabinet.js:SP.printCabinetAndBins` ~383 | Keep Print UI separate from Export; generate file then show explicit I opened it in Bambu Studio confirmation. Existing Printed state/schema only changes after user affirms successful slicer handoff for current Space/design; do NOT add persistent Prepared state. B08 supplies ordinary/shared Print; B10 owns drawer-print routes. |
| B09 | `web/browser-files.js` existing `WFFileSystem`; `web/spaces/03-safe-switching.js:SP.applyFolder`; `04-metadata-persistence.js:SP.readMetadata/writeMetadata`; `05-space-memory.js`; `07-welcome-folders.js`; `08-space-setup.js` | Create browser-core/space-store.js and preferences.js; own all folder/Space routes including browse-output-folder, show-folder, warm and printer profile. Reuse WFFileSystem IndexedDB handles, metadata, immutable Gridfinity Space pitch and autosave. B13 must not own show-folder. |
| B10 | `web/spaces/06-inventory-io.js:SP.inventoryRequest` ~132, `SP.readInventoryFor` ~9; `web/drawer-model.js`; `organizer_drawer/__init__.py:drawer_routes` | Create browser-core/engine/drawer-routes.py; owner of every /api/drawer/* including print-bins, print-spacers, print-complete, consuming B08 print service. Source SP.inventoryRequest and organizer_drawer.drawer_routes; preserve source/Space state and grid refusals. |
| B11 | `web/structural-design.js:refreshStructuralPreview`; `web/spaces/10-storage-box-structural.js:SP.runStructural`; `11-base-trim.js:SP.saveBaseTrim`; `14-drawers-cabinet.js:SP.runCabinetStructural`; `wavefinity_web.py:structural_*_payload` | Create structural-routes.py; own all structural and Storage Drawers routes and pegboard hooks, not space/warm. Source web/spaces/10-storage-box-structural.js,11-base-trim.js,14-drawers-cabinet.js, organizer_storage/drawers.py,drawer_geometry.py,drawer_outputs.py, organizer_features/gridfinity.py and organizer_b4b. Preserve nominal/physical floor, seated lift, current Gridfinity Stage 1 and merged Stage 2. |
| B12 | `wavefinity_web_impl/_nest.py`, `organizer_inserts/_nest/*`, `organizer_inserts/_text.py`, `web/app/11-parts-preview-requests.js` | Source wavefinity_web_impl/_nest.py:nest_retrace_payload; photo_nest.py:decode_image_data/retrace_outline_from_rectified; organizer_inserts/_nest/* and _text.py, web/spaces/12-space-info.js. Create nest-routes.py and use Pyodide cv2/NumPy/Pillow/Shapely; preserve native image contour semantics. B13 edits space-info only after B12. |
| B13 | `web/app/02-lifecycle-ai-help.js:aiConnectionRefresh/aiAsk/aiGeneratePrompt` ~876/905/576; `wavefinity_web.py:ai_*_payload`; `web/app/15-generate-dialogs.js:browseSlicer/showAboutDialog` | Source web/app/02-lifecycle-ai-help.js:aiConnectionRefresh/aiAsk/aiGeneratePrompt; wavefinity_web_impl/_ai.py; web/app/15-generate-dialogs.js:browseSlicer/showAboutDialog and spaces/12-space-info.js. Own AI, suggestions, slicer-browse, show-log and Chrome/Edge unsupported-browser notice. No show-folder route. Require Andrew decision BEFORE B13 Story if safe direct AI chat cannot survive. |
| B14 | `render.yaml` currently **Python web service**; `Dockerfile` old Hugging Face path; `web/index.html` absolute-root assets; `wavefinity_web.py:do_GET` ~3671 | Create scripts/build-static-site.py and host docs; sole assembler of central route-dispatch.py. Copy production web/* into dist root, repo images/* into dist/images/, Brochure.md to dist/Brochure.md AND dist/brochure.md. EXCLUDE browser-local-poc.html, browser-local-poc.js, browser-local-poc-worker.js and entire browser-local-poc/ directory. Configure Render Static Dashboard headers; no live DNS changes without owner approval. |
| B15 | `wavefinity_web.py`, `wavefinity_web_impl/`, `render.yaml`, `Dockerfile` | Retire Python service only AFTER documenting actual last deployed Render Web Service SHA, new static deployment SHA, date, hostname, DNS and rollback instructions in legacy/private records; require Andrew's cutover authorization. |
| B16 | `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, PoC-only resources | Remove PoC-only source and harness after static cutover while keeping production MeshGL64 runtime/source/licensing; PoC already excluded by B14 from shipped dist. |

## Before/after implementation sketches (pseudo-diffs; resolve current source)

### 1) Single API switch, not every caller

```diff
// web/app/03-history-utils-catalog.js
 async function api(path, payload = null, opts = {}) {
-  const response = await fetch(path, ...);
-  /* JSON timeout/poll handling over HTTP */
+  return WFLocalAPI.call(path, payload, opts);
 }
```

Keep `apiSideEffect(path,payload,...)`'s existing caller signature and logical dedupe/operation identity; replace HTTP polling with worker operation bookkeeping, not a server API. Require local runtime initialization before `web/app.js:init()` requests `/api/catalog`. Do not add mode toggle or fallback.

### 2) Worker message and local outputs

```text
REQUEST: {v:1,job_id,path,payload,design_epoch}
PROGRESS: {v:1,job_id,type:"progress",stage,percent?}
RESULT: {v:1,job_id,type:"result",value}
ERROR: {v:1,job_id,type:"error",error:{kind,message}}
FILE: {v:1,job_id,type:"file",name,local_file_id,bytes:ArrayBuffer}
```

`worker.js` initializes Pyodide once, installs canonical bundle/Manifold64 bridge and dispatches paths to Python. The UI uses `local-api.js` to resolve/reject Promises by job ID; stale design epochs do not overwrite current UI state. Transfer ArrayBuffers, never base64 large 3MF to main thread. The main thread's `local-files.js` owns Blob lifetime and `WFFileSystem.writeBlob`/download. Keep actual runtime mesh/file validity checks and security checks; don't add testing artifacts.

### 3) Production Pyodide/Manifold64 extraction

```diff
// web/browser-local-poc-worker.js is SOURCE MATERIAL ONLY
- const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/";
- import("./browser-local-poc/manifold64/bridge64.mjs");
- load one static 42mm reference.json and require exact fixture identity
+ import self-hosted, version-pinned Pyodide assets from /browser-core/vendor/;
+ import /browser-core/vendor/manifold64/bridge64.mjs + bridge64.wasm;
+ load /browser-core/engine/canonical.zip from build output;
+ import the real Python engine functions for the requested dimensions/parts;
+ return actual geometry, status and file bytes (no reference.json restriction).
```

Make `scripts/build-browser-core.py` a **production asset generator**, NOT a testing tool. Use source inclusion lists + hash manifest to prevent accidental drift when Gridfinity code moves. As source evolves, update import graph rather than rewriting geometry.

### 4) Print remains Print

```diff
// web/app/15-generate-dialogs.js:printModelWithReport
- if (state.runtime.hosted) { report("Printing needs local Wavefinity ... Export",true); return; }
- if (!state.slicer?.available) { report("Change slicer...",true); return; }
- const result = await apiSideEffect("/api/print", payload);
- report("Sent ... to " + slicerName)
+ await existing autosave + printer/space validation;
+ const result = await apiSideEffect("/api/print", payload); // now local worker route
+ save or download generated .3mf via WFLocalFiles + WFFileSystem;
+ show print-prepared filename and "Open in Bambu Studio";
+ do not record Printed unless handoff acknowledged; prepared != opened != physically printed.
```

Also modify `SP.HOSTED_STRUCTURAL_PRINT_TOOLTIP`, `SP.HOSTED_SURFACE_PRINT_TOOLTIP`, `SP.printStorageBox`, `SP.printSurface`, `SP.printCabinetAndBins`, `SP.runCabinetStructural` and drawer Print handlers. Preserve existing Print dialogs and separate Export.

### 5) Browser saving is already implemented in part

`window.WFFileSystem` in `web/browser-files.js` currently exports `pickDirectory`, `queryReadWritePermission`, `requestReadWritePermission`, `writeBlob`, `writeText`, `readText`, `fileExists`, `listFilenames`, `removeFile`, `readBlob`, `sha256`, `sha256Blob`, `copyDirectory`, `removeDirectory`, `save`, `load`. **Reuse them.**

`SP.readMetadata / SP.writeMetadata` in `04-metadata-persistence.js` and `SP.inventoryRequest / SP.writeHostedFileSet / SP.useHostedFolder` in `06-inventory-io.js` already own important state and local write behavior. Do not create a new competing persistence layer. Replace Python Path requirements with browser file handle/contents and preserve locked Space identity across asynchronous operations.

### 6) Exact static-site output layout

```text
Wavefinity repo:
  web/index.html                 => dist/index.html
  web/styles.css                 => dist/styles.css
  web/app/*.js                   => dist/app/*.js
  web/spaces/*.js                => dist/spaces/*.js
  web/browser-core/**/*         => dist/browser-core/**/*
  web/other CSS, JS, HTML       => dist/<same path relative to web>
  images/**/*                   => dist/images/**/*
  Brochure.md                   => dist/Brochure.md AND dist/brochure.md (literal lowercase alias)
  (optional other static docs)  => only explicit UI-reachable assets
  web/browser-local-poc.html      => EXCLUDE
  web/browser-local-poc.js        => EXCLUDE
  web/browser-local-poc-worker.js => EXCLUDE
  web/browser-local-poc/**/*      => EXCLUDE (bridge copied into production vendor path)
```

Do NOT copy `tests/`, `browser-tests/`, `Future plans/`, `README.md`, `run_tests.py`, server credentials or non-shipping Python sources outside the bundled canonical engine into `dist/`. Preserve absolute-root paths (`/styles.css`, `/images/*`, `/Brochure.md`) already used by index.html. Include no dynamic server endpoints or /api/export paths. `dist/index.html` must be the root landing page; no catch-all route rewrite needed for existing file-based UI unless the app adopts client-side history routing.

The build script may compile/copy production assets but must not create/run test programs, browser sessions or manual QA scripts. Manage versioned asset paths and cache headers coherently so new JS and WASM don't mix. Include declared WASM MIME and security headers in static host config.

## Pinned bridge, production build and unresolved limits

**Proven scope, not a completeness claim:** The Windows Chrome/Edge confirmation covers the ordinary 42 × 42 × 28 mm bin. The 84 × 42 × 28 mm ordinary bin was checked in Linux Chromium. The bridge has NOT been demonstrated on large Storage Drawers/Storage Boxes, Gridfinity feet, grid lids, magnets, Photo Nest or multipart 3MF. Porting these remains the main risk.

**Pinned foundation copied from actual source:** Pyodide 0.28.3; Pyodide NumPy 2.2.5, Shapely 2.0.7 (GEOS 3.12.1), networkx 3.4.2; pure Trimesh 5.0.0 wheel SHA256 51ec67d7f9f74b918f2a695da5fd511b9c084e96307648ae83f45b58f13f8009; JS Earcut 3.0.2; Manifold C++ 3.5.0 upstream commit 541c33bd2ab9b1a72816bdecff90566c0a3ee56c; custom MeshGL64 bridge; Emscripten 4.0.10. Existing native requirements.txt pins are NOT the same as browser-package versions. Additional packages come from current Python import graph, not speculative downloads.

**Build chain locked:** Production scripts/build-browser-core.py rebuilds canonical.zip from checked-out current source whenever scripts/build-static-site.py prepares the shipping bundle; records its SHA256 and hashes every locally vendored asset in the production manifest. Precompiled bridge64.mjs and bridge64.wasm are COMMITTED production files copied at Render static deployment; the historical Emscripten build.sh is for a separate maintainer rebuild, never invoked on Render. Bundle Pyodide and Python wheels locally. Never call browser-tests/prepare-local-poc.py and never copy historical test resources into dist.

**Numeric capacity assumptions, not measurements:** target <=64 MiB first-load compressed assets and <=1536 MiB combined allocated Pyodide + Manifold WASM linear memory. WASM32's theoretical per-memory address limit is 4 GiB; usable browser limits may be lower. The old negative prototype measured 22,335,798 cold bytes and ~90.4 MB Python heap; neither number represents the complete final app. The largest current job peak is unknown. B02 assesses actual production artifact file sizes as part of the normal asset build (not a test) and reasons about worst-case memory growth from code; if target limits would compromise supported geometry, report a precise blocker rather than weaken the product. Check Render free-tier per-asset/traffic limits here, not after coding at B14.

**Single-thread assumption and CORS:** bridge64/build.sh sets MANIFOLD_PAR=OFF, does not compile with -pthread, and the current default Pyodide worker path does not require SharedArrayBuffer. COOP/COEP cross-origin isolation is NOT required for this frozen implementation. If a later revision adds pthreads/SAB, that separate decision requires COOP same-origin, COEP require-corp, and audit of CORS/CORP for every pinned asset.

**3MF native-library truth:** organizer_engine/_export.py imports native lib3mf at module top; its visible Python calls include Wrapper/CreateModel, QueryReader/ReadFromBuffer, GetMeshObjects, GetBuildItems/RemoveBuildItem, AddComponentsObject/AddComponent/AddBuildItem, SetName, GetMetaDataGroup/AddMetaData, AddAttachment/ReadFromBuffer, strict QueryWriter/WriteToFile and strict re-read. The native library's internal XML serialization/ordering is NOT visible in Python. B07 isolates that import from Pyodide, implements 3MF OPC content types, 3D model resource mesh, object/component ID and transforms, build items, identity Application/Title metadata, Bambu attachment relationship http://schemas.bambulab.com/package/2021 and Metadata/model_settings.config with part names and filament slots. Preserve real product format-validity checks. Do NOT claim byte-level or empirical Bambu parity was established through source review; owner naturally uses Print after implementation. No coder tests.

**Photo Nest native-library truth:** wavefinity_web_impl/_nest.py imports photo_nest.py; the latter imports cv2, NumPy, Shapely and PIL.Image (for decoding/size guarding). Pyodide 0.28.3 has opencv-python 4.11.0.86 and Pillow 11.3.0, which are NOT the native opencv-python-headless 5.0.0.93 / Pillow 13 pins. B12 preserves the actual perspective, contour and warp algorithms and makes import/API adapters only where source analysis requires. No claim of unverified ABI equivalence.

## Render Static Site headers: concrete B14 settings

Use the NEW Render Static Site Dashboard > Settings > Headers with path patterns, not Cloudflare Pages _headers, and do not edit the legacy render.yaml early. See https://render.com/docs/static-site-headers.

- Path /*: X-Content-Type-Options = nosniff; Referrer-Policy = no-referrer; X-Frame-Options = DENY. Content-Security-Policy baseline: default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'. Add only an explicitly owner-approved AI provider origin. If Pyodide needs unsafe-eval, document the minimum exception; do not silently relax all sources. Preserve microphone availability for existing AI dictation if supported.
- Paths /**/*.wasm and /*.wasm: Content-Type = application/wasm. Paths /**/*.mjs and /*.mjs: Content-Type = text/javascript; charset=utf-8. Streaming WebAssembly loads rely on correct MIME.
- Path / and /index.html, /Brochure.md and /brochure.md, unversioned /app/* and /spaces/*, and /browser-core/engine/canonical.zip: Cache-Control = no-cache. Every unversioned runtime entrypoint must revalidate.
- Path /browser-core/vendor/<content-hash>/* ONLY if truly content-hash-versioned: Cache-Control = public, max-age=31536000, immutable. Never cache a stable filename immutably; avoid mixed main JS and WASM versions.

## Gridfinity implementation invariants for every Bxx Story

Read gridfinity-stage1-spec.md and Future plans/Gridfinity-implementation-master-plan.md as the geometry/data model references, then check current main at the post-Gridfinity GO. Proposed Stage 2 features MUST NOT be described as shipped until merged. Existing Stage 1 prose containing old test instructions does NOT override README's no-coder-testing rule.

| Bxx | Exact Gridfinity preservation scope |
|---|---|
| B01, B02 | Record final Gridfinity fields/routes and package the canonical grid, foot, socket, lid and container-floor modules actually present; do not create generic substitute 21/42 geometry. |
| B04 | Persist design grid; Space grid chosen at creation and immutable thereafter. No-Space design has its own explicit grid. Width/depth bare numbers below pitch map to grid units, heights on BOTH Gridfinity pitches use 7 mm units. Every entry path validates cross-grid mismatch with both grid names. |
| B05 | Show correct nominal grid dimensions, actual physical cavity and effective height as distinct readouts; don't call unknown seated lift zero. |
| B06 | Independent 42 and 21 mm flat-sided Gridfinity profiles, foot/socket/rim per pitch, 0.5 mm total nominal XY relief where specified; parts and filenames include grid/pitch and nominal-unit segments, never replace Wavefinity's 7 mm wavy geometry. |
| B07, B08 | 3MF naming/assemblies include correct feet, grid lid/open rim, printed profile and multi-filament parts. Print uses printer limits and correct Space grid. |
| B09 | Preserve Space grid immutability, built_in_grid Floor versus None, floor_grid=null on None, nominal_grid_mm versus physical_cavity_mm, seated_lift_mm measured/unknown distinction and current metadata versions across save/restore. |
| B10 | Layout snap/fit uses the Space grid accessor, cross-grid refusal identifies both grids on every insert/duplicate/import/restore path; one seated-lift accessor supplies fit and unmeasured remains unverified. |
| B11 | Storage Box/Drawers printed Floor pockets are pitch-specific; None accepts external baseplate with provisional EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM=0.35 per side. Nominal stays exact, physical cavity grows; min base 5.8 mm (or 8.3 mm above Storage Box underside recess), do not silently grant unverified physical fit. |
| B12, B13 | Advanced features and AI prompts must honor final Gridfinity eligibility, lid/stacking conditions, 7 mm vertical units, nominal-versus-physical dimensions, current Stage 2 magnets/lids/side openings only if merged. |

**The route-dispatch.py shared file is created by B04; B14 alone merges exported route maps from other Bxx modules. All drawer routes belong to B10 (including Print); shared B08 helper use is not dual route ownership.**

## B14: hosting selection and exact owner handoff

**Preferred target — Render Static Site.** Current documentation (November 2026) describes free static sites, CDN, custom domains and managed HTTPS with no free *web-service* idle spin-down. Static sites consume monthly included bandwidth/build minutes; do not claim unlimited free traffic. Check the deployed artifact's per-file size, total bandwidth expectations and Render account limits using vendor docs before proposing any paid service.

**Coder implements before notifying Andrew:**
1. Complete `scripts/build-static-site.py`, static asset directory and build instructions; the compiler uses source `web/`, `images/`, `Brochure.md` and B02 production files as above. No browser walkthroughs or test plans.
2. Write `docs/static-host-rollout.md` with current service names, actual present Render host, exact new Static Site build command, publish directory and domain controls. Keep `render.yaml` old Python Web Service entry unchanged for now; do not accidentally redeploy it to static or create an extra service via a Blueprint.
3. Preferred manual Render dashboard settings after code completion: `New → Static Site` → GitHub repo `happydadto5/Wavefinity` → branch `main` → name `wavefinity-static` (unless occupied) → **Build Command:** `python3 scripts/build-static-site.py` *only if dependencies are already prepared and Render build environment supports this command* → **Publish Directory:** `dist` → auto-deploy OFF until Andrew chooses otherwise. Document fallback command if the host's build image requires it; do not assume a new runtime service.
4. Publish only static files; do not add API functions or edge workers to do geometry. The new Static Site gets an actual `*.onrender.com` hostname, to copy from dashboard.
5. Keep root A DNS value `<read private Help-Code apex A>` **only if Render's current custom-domain instructions still say so**. Change `www` CNAME target from `<read private Help-Code old Render hostname>` to the **actual** new Static Site hostname. The apex and www domain *attachments* must move from the old Render Web Service to the new Render Static Site, which may require detaching them first and temporarily interrupting service. Do not guess existing domain transfer automation. Confirm apex → HTTPS and www redirect in the new Static Site settings.
6. **Do not actually attach/detach wavefinity.org, touch Porkbun, switch provider, or disable/delete the old service without Andrew's explicit action/approval.**

**Prompt to Andrew only when implementation is complete:** “The browser-only site is ready for static hosting. I recommend Render Static Site because it is free for this hobby-scale use within allowances and has no idle wake-up. The current Python Web Service cannot be converted in place. Please create or authorize the separate Static Site, then we can move wavefinity.org and www. Here are the actual build/publish settings and the DNS change from the dashboard. Shall we cut over?” This is an operational decision, **not** a manual application testing plan.

**Other hosting options:** Render Static Site is the approved target. Cloudflare Pages at the root domain is out of scope because it requires changing nameservers, which Andrew does not want. If Render limits/costs make static hosting unsuitable, stop and present only alternatives that preserve Porkbun as registrar **and authoritative DNS**; request his explicit choice. Do not change nameservers, purchase another domain or transfer registration.

**No 60-second wake-up:** The old Render Free **Python Web Service** sleeps after idle time and can take about a minute to reactivate. Render **Static Site** serves CDN assets and does not use that sleeping application process. A first-time browser still needs to download/initialize Pyodide/WASM and generate geometry on its CPU; these are user-side delays, not a Render cold start.

**Domain/migration security:** Preserve same-origin `wavefinity.org` for client file handle/storage continuity where possible, but never promise IndexedDB/browser permission persistence through host migration; browser protections may re-request permission. Store no design or private geometry on the new CDN. Porkbun auto-renewal is already enabled and recorded in private Help-Code.

## Minimal-token implementation handoff (for each future Poller Story)

- **Coder reads:** current assigned Bxx paragraph from `Browser-only-core-detailed-build-contracts.md`, corresponding row/section in THIS diff map, and only matching routes from `Browser-only-core-source-route-index.md`. Avoid rereading entire repository README (the no-test policy is enough), entire previous debate or unrelated Bxx packages.
- **Coder uses:** exact file/function anchors above to locate code in live `main`, reconcile changed Gridfinity functions by name, and implement the *specific* named before/after changes. Do not generate alternative architectures or ask to choose between several hosting providers unless an actual dependency makes the default impossible.
- **Coder leaves alone:** `render.yaml` old service until cutover; unrelated product geometry; personal checkouts, current hosted DNS and user folder contents; disabled/retired tests (do not run/repair/recreate); code outside assigned change scope unless essential for compilation/integration.
- **Coder reports only:** implemented behavior, affected file names/functions, key unavoidable deviations, committed SHA and push state. No tests-run section, no test plan for user, no fabricated empirical success.
- **Coordinator handles:** dependencies B00–B16, same-file collision scheduling, one final owner notification and static-host decision, and archiving old Render method. No independent duplicate planning by each coder.
- **Future drift:** this map deliberately avoids brittle whole-file patches while specifying functions, new file paths and behavior. The coder may adjust specific lines to changes in main without re-planning the architecture; notify the owner only for unavoidable product or cost choices.
