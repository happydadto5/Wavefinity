# Wavefinity browser-only migration — change-by-change implementation map

**Purpose:** Minimize coder rediscovery and token use. This is the implementation supplement to [Browser-only-core-detailed-build-contracts.md](Browser-only-core-detailed-build-contracts.md), not a test or QA plan. Frozen technical reference: Wavefinity source around the November 12, 2026 Gridfinity migration. Resolve target functions in current `main` before editing; line numbers are *navigation hints*, not immutable patch offsets.

**NO CODER TESTING:** Per README.md, coders implement and logically inspect source/diffs; no automated or manual application tests, testing scripts, fixtures, user QA plans, or interim working builds. Do not create a Story until Andrew finishes Gridfinity and explicitly says **go**. Coders must not change live DNS or retire Render until Andrew authorizes the final cutover.

## Hard destination decisions

- Existing `web/index.html` UI unchanged in intent and layout. All ordinary bins, Wavefinity, final Gridfinity variants, Storage Boxes, Storage Drawers, Drawer, Surface, Pegboard, inventory, all features, previews, STL, multipart 3MF, and first-class **Print** move to browser/PC.
- Browser executes canonical Python using pinned, **self-hosted** Pyodide; custom `MeshGL64` Manifold WebAssembly handles float64 geometry. Zero Wavefinity cloud geometry APIs. Do not reimplement waves/clearances or use float32 shortcuts.
- Existing `wavefinity.org` is served by a **static CDN**, not a Python web service. **DEFAULT HOST: Render Static Site (free tier, subject to bandwidth/build allowances)**. Separate *new static site* must be created; Render cannot convert the existing Web Service into a Static Site in place. First browser asset load and WebAssembly/Python initialization may take time; **no idle web-service 60-second wake-up**.
- Render Static is favored because Porkbun DNS already points apex `wavefinity.org` at Render's `216.24.57.1`; `www` currently CNAMEs `wavefinity.onrender.com`. At final switch, root A may remain but domain association must move to the new Render Static service and `www` must target the **actual new static-service hostname**, as shown by Render—not an invented value. Detach the custom domains from old Web Service when Render requires it, associate both on new Static Site, wait for TLS, confirm redirect, then retire old service *only after Andrew approves*.
- Cloudflare Pages is fallback, not mandatory. Free plan currently has a 25 MiB **per file** and 20,000-file limit; `wavefinity.org` apex on Cloudflare Pages requires changing authoritative DNS nameservers to Cloudflare (Porkbun still registrar). Prefer staying on Render Static unless package constraints or owner preference justify Cloudflare.
- Browser print limitation: static site cannot arbitrarily start `BambuStudio.exe`; **keep Print** and all its checks/status, save/download correct Bambu/Orca 3MF, then show a concise `Open in Bambu Studio` handoff. Export stays separate. Do not claim automatic slicer launch, and do not require a Wavefinity-installed app/helper/extension.
- Full application may be nonfunctional during migration. **No dual Python/browser mode, no half-release compatibility layers. One final static-site cutover.**
- Keep old server architecture and recovery documentation in `docs/legacy-python-server-hosting.md`; its existing source remains in Git history. Private Porkbun/domain/account record stays in private Help-Code `docs/wavefinity-domain.md`.

## Exact source change map (B00–B16)

| Package | Existing ownership anchors | Required concrete edit / new production file |
|---|---|---|
| B00 | `render.yaml`, `Dockerfile`, `wavefinity_web.py`, `docs/legacy-python-server-hosting.md` | Legacy hosting record **already exists**. Refresh only if server startup or rollback instructions have changed. Record last actually deployed server SHA at final cutover. Do not recreate documentation. |
| B01 | `wavefinity_web.py:POST_ROUTES` near line 3486; `organizer_drawer/__init__.py:drawer_routes` near 331; `organizer_spaces/__init__.py:space_routes` near 473; JS `api` callers | Read [source-route-index](Browser-only-core-source-route-index.md) (91 current routes) and *only relevant current handlers*. Refine `browser-core/contracts/route-manifest.json` into plain static owner/schema notes: path, current handler, input/output keys, side effects, Bxx owner. No route audit generator or tests. |
| B02 | `web/browser-local-poc-worker.js`, `web/browser-local-poc/bridge.py`, `web/browser-local-poc/manifold64/*`; canonical Python engine | Create `scripts/build-browser-core.py`, `web/browser-core/vendor/`, `web/browser-core/engine/{canonical.zip,manifest.json}`. Move/copy pinned Manifold64 bridge + license into production path; bundle Pyodide/wheels/fonts and canonical Python. Remove PoC hard-coded 42 mm reference gating, not precision. |
| B03 | `web/index.html` bottom script block near lines 1154–1199; `web/app/03-history-utils-catalog.js:api` near 369 and `apiSideEffect` near 587; `web/app.js:init` | Create `web/browser-core/{worker.js,bootstrap.js,local-api.js,local-files.js,runtime-status.js}`. Add bootstrap script **after browser-files.js and before app runtime scripts**. Keep `api(path,payload,options)` public signatures; replace underlying fetch/HTTP with `WFLocalAPI.call(path,payload,options)`. No server fallback. |
| B04 | `wavefinity_web.py` routes; `wavefinity_web_impl/_designs/{_features,_layout,_preview}.py`; JS catalog/draft/fit callers | Create `web/browser-core/engine/route-dispatch.py` with explicit current route-to-Python-function mapping (source index); return unchanged result fields/error shape. Pull canonical rules, catalog/static data into browser bundle. Use a single dispatch function; avoid copied geometry formulas. |
| B05 | `web/app/11-parts-preview-requests.js:refreshPreview` ~727, `adoptPreviewResult` ~557, `invalidatePendingPreview` ~482; `web/structural-design.js:refreshStructuralPreview` ~345; `web/app/12-3d-preview-render.js` | Route preview requests to worker. Preserve current request generation/epoch, latest-only application, last good mesh, warnings/progress, structural preview behavior; do not rewrite WebGL renderer. |
| B06 | `web/app/15-generate-dialogs.js:generatePartsWithReport` ~111, `saveGeneratedFiles` ~658; `wavefinity_web.py:generate_payload` ~1731 and `connector_save_payload` ~2072 | Create `web/browser-core/engine/build-outputs.py`. Replace server temp output path/token with `[{name,local_file_id}]` + transferable bytes; bind file IDs to `Blob` and `WFFileSystem.writeBlob()`/download. Keep existing connector selection, file conflict prompts and canonical geometry. |
| B07 | `organizer_engine/_export.py`: native `lib3mf` currently imported at top; `export_*_3mf` and `validate_3mf` functions | Create `web/browser-core/engine/three_mf.py`. Ensure Pyodide runtime import does NOT require native `lib3mf` at module load; use late native import or import-compatible backend separation. Implement native-equivalent 3MF ZIP/XML package, groups, object names, transforms, material/filament mapping and Bambu metadata. Don't silently produce STL-only. |
| B08 | `web/app/15-generate-dialogs.js:printModelWithReport` ~406, `chooseIndividualBinPrint` ~579, `updatePrimaryPrintButtonLabel` ~607; `web/spaces/10-storage-box-structural.js:SP.printStorageBox` ~269; `web/spaces/11-base-trim.js:SP.printSurface` ~328; `web/spaces/14-drawers-cabinet.js:SP.printCabinetAndBins` ~383 | Keep **all Print controls**. Delete hosted-mode refusal and slicer-path hard gate; call local Print output builder. Preserve autosave, printer limits, selection, reuse and truthful status; expose print-prepared 3MF and clear open-in-slicer instruction. Do not simply alias Print to Export. |
| B09 | `web/browser-files.js` existing `WFFileSystem`; `web/spaces/03-safe-switching.js:SP.applyFolder`; `04-metadata-persistence.js:SP.readMetadata/writeMetadata`; `05-space-memory.js`; `07-welcome-folders.js`; `08-space-setup.js` | Create `web/browser-core/{space-store.js,preferences.js}`. Reuse existing directory handle/IndexedDB functions; make local folder/Space operations authoritative. Remove server-only folder path branching, preserve `.wavefinity.json`, Space IDs, permissions, autosave, resume, printer profiles, and explicit import/export. |
| B10 | `web/spaces/06-inventory-io.js:SP.inventoryRequest` ~132, `SP.readInventoryFor` ~9; `web/drawer-model.js`; `organizer_drawer/__init__.py:drawer_routes` | Create `web/browser-core/engine/drawer-routes.py`; reuse `organizer_inventory` parsing and merge logic, but pass browser-supplied text, not server `Path`. Return new inventory text and file bytes; commit local file changes through existing browser transactional save helpers. |
| B11 | `web/structural-design.js:refreshStructuralPreview`; `web/spaces/10-storage-box-structural.js:SP.runStructural`; `11-base-trim.js:SP.saveBaseTrim`; `14-drawers-cabinet.js:SP.runCabinetStructural`; `wavefinity_web.py:structural_*_payload` | Create `web/browser-core/engine/structural-routes.py`; route cabinet, Storage Box, Surface, Space print and multipart exports to canonical Python/3MF builder. Remove hosted refusal/temporary path assumptions while keeping all existing layout/cabinet journal logic. |
| B12 | `wavefinity_web_impl/_nest.py`, `organizer_inserts/_nest/*`, `organizer_inserts/_text.py`, `web/app/11-parts-preview-requests.js` | Create `web/browser-core/engine/nest-routes.py`; convert selected photos to browser bytes/Blob, retain authoritative contour/nesting and all advanced insert paths; bundle fonts and compatible packages. No parallel simplified geometry engine. |
| B13 | `web/app/02-lifecycle-ai-help.js:aiConnectionRefresh/aiAsk/aiGeneratePrompt` ~876/905/576; `wavefinity_web.py:ai_*_payload`; `web/app/15-generate-dialogs.js:browseSlicer/showAboutDialog` | Create `web/browser-core/capabilities.js` and `docs/static-capability-differences.md`. Preserve local AI prompt/candidate logic; external AI provider only when user-controlled and browser-safe. Replace unsupported executable/folder/log commands with honest UI; keep static `Brochure.md`. |
| B14 | `render.yaml` currently **Python web service**; `Dockerfile` old Hugging Face path; `web/index.html` absolute-root assets; `wavefinity_web.py:do_GET` ~3671 | Create `scripts/build-static-site.py` and `docs/static-host-rollout.md` (instructions below). Copy `web/` content into `dist/` root and repo-root `images/` and `Brochure.md`. Author **new Render Static Site** deployment settings; never silently change existing Python `render.yaml` before cutover. |
| B15 | `wavefinity_web.py`, `wavefinity_web_impl/`, `render.yaml`, `Dockerfile` | After Andrew authorizes cutover: retire Python HTTP serving from deployed site, mark old startup config historic, keep legacy docs/source SHA. Do NOT delete canonical Python geometry that browser bundle needs. |
| B16 | `web/browser-local-poc.html`, `web/browser-local-poc.js`, `web/browser-local-poc-worker.js`, PoC-only resources | Delete superseded public experimental interface and comparison scaffolding, not the production Manifold64 engine or license. Remove references from shipped HTML and update legacy evidence notes. No new tests or replacement fixtures. |

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
  Brochure.md                   => dist/Brochure.md
  (optional other static docs)  => only explicit UI-reachable assets
```

Do NOT copy `tests/`, `browser-tests/`, `Future plans/`, `README.md`, `run_tests.py`, server credentials or non-shipping Python sources outside the bundled canonical engine into `dist/`. Preserve absolute-root paths (`/styles.css`, `/images/*`, `/Brochure.md`) already used by index.html. Include no dynamic server endpoints or /api/export paths. `dist/index.html` must be the root landing page; no catch-all route rewrite needed for existing file-based UI unless the app adopts client-side history routing.

The build script may compile/copy production assets but must not create/run test programs, browser sessions or manual QA scripts. Manage versioned asset paths and cache headers coherently so new JS and WASM don't mix. Include declared WASM MIME and security headers in static host config.

## B14: hosting selection and exact owner handoff

**Preferred target — Render Static Site.** Current documentation (November 2026) describes free static sites, CDN, custom domains and managed HTTPS with no free *web-service* idle spin-down. Static sites consume monthly included bandwidth/build minutes; do not claim unlimited free traffic. Check the deployed artifact's per-file size, total bandwidth expectations and Render account limits using vendor docs before proposing any paid service.

**Coder implements before notifying Andrew:**
1. Complete `scripts/build-static-site.py`, static asset directory and build instructions; the compiler uses source `web/`, `images/`, `Brochure.md` and B02 production files as above. No browser walkthroughs or test plans.
2. Write `docs/static-host-rollout.md` with current service names, actual present Render host, exact new Static Site build command, publish directory and domain controls. Keep `render.yaml` old Python Web Service entry unchanged for now; do not accidentally redeploy it to static or create an extra service via a Blueprint.
3. Preferred manual Render dashboard settings after code completion: `New → Static Site` → GitHub repo `happydadto5/Wavefinity` → branch `main` → name `wavefinity-static` (unless occupied) → **Build Command:** `python3 scripts/build-static-site.py` *only if dependencies are already prepared and Render build environment supports this command* → **Publish Directory:** `dist` → auto-deploy OFF until Andrew chooses otherwise. Document fallback command if the host's build image requires it; do not assume a new runtime service.
4. Publish only static files; do not add API functions or edge workers to do geometry. The new Static Site gets an actual `*.onrender.com` hostname, to copy from dashboard.
5. Keep root A DNS value `216.24.57.1` **only if Render's current custom-domain instructions still say so**. Change `www` CNAME target from `wavefinity.onrender.com` to the **actual** new Static Site hostname. The apex and www domain *attachments* must move from the old Render Web Service to the new Render Static Site, which may require detaching them first and temporarily interrupting service. Do not guess existing domain transfer automation. Confirm apex → HTTPS and www redirect in the new Static Site settings.
6. **Do not actually attach/detach wavefinity.org, touch Porkbun, switch provider, or disable/delete the old service without Andrew's explicit action/approval.**

**Prompt to Andrew only when implementation is complete:** “The browser-only site is ready for static hosting. I recommend Render Static Site because it is free for this hobby-scale use within allowances and has no idle wake-up. The current Python Web Service cannot be converted in place. Please create or authorize the separate Static Site, then we can move wavefinity.org and www. Here are the actual build/publish settings and the DNS change from the dashboard. Shall we cut over?” This is an operational decision, **not** a manual application testing plan.

**Fallback — Cloudflare Pages:** If Render static limits/fees are unfavorable for the actual package, tell Andrew before making any changes. Cloudflare Pages Free currently permits up to 20,000 files but each file must be <=25 MiB; the apex custom domain requires transferring authoritative nameservers to Cloudflare, while Porkbun remains registrar. No automatic DNS change. Do not assume that splitting the WASM into smaller files solves every package limit. GitHub Pages remains a lesser fallback subject to real asset and bandwidth constraints.

**No 60-second wake-up:** The old Render Free **Python Web Service** sleeps after idle time and can take about a minute to reactivate. Render **Static Site** serves CDN assets and does not use that sleeping application process. A first-time browser still needs to download/initialize Pyodide/WASM and generate geometry on its CPU; these are user-side delays, not a Render cold start.

**Domain/migration security:** Preserve same-origin `wavefinity.org` for client file handle/storage continuity where possible, but never promise IndexedDB/browser permission persistence through host migration; browser protections may re-request permission. Store no design or private geometry on the new CDN. Porkbun auto-renewal is already enabled and recorded in private Help-Code.

## Minimal-token implementation handoff (for each future Poller Story)

- **Coder reads:** current assigned Bxx paragraph from `Browser-only-core-detailed-build-contracts.md`, corresponding row/section in THIS diff map, and only matching routes from `Browser-only-core-source-route-index.md`. Avoid rereading entire repository README (the no-test policy is enough), entire previous debate or unrelated Bxx packages.
- **Coder uses:** exact file/function anchors above to locate code in live `main`, reconcile changed Gridfinity functions by name, and implement the *specific* named before/after changes. Do not generate alternative architectures or ask to choose between several hosting providers unless an actual dependency makes the default impossible.
- **Coder leaves alone:** `render.yaml` old service until cutover; unrelated product geometry; personal checkouts, current hosted DNS and user folder contents; disabled/retired tests (do not run/repair/recreate); code outside assigned change scope unless essential for compilation/integration.
- **Coder reports only:** implemented behavior, affected file names/functions, key unavoidable deviations, committed SHA and push state. No tests-run section, no test plan for user, no fabricated empirical success.
- **Coordinator handles:** dependencies B00–B16, same-file collision scheduling, one final owner notification and static-host decision, and archiving old Render method. No independent duplicate planning by each coder.
- **Future drift:** this map deliberately avoids brittle whole-file patches while specifying functions, new file paths and behavior. The coder may adjust specific lines to changes in main without re-planning the architecture; notify the owner only for unavoidable product or cost choices.
