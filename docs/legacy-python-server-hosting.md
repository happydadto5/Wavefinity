# Wavefinity — Legacy Python HTTP / Render hosting (preservation record)

Status: historical-operating-method and recovery reference. The browser-only static site is live; the Python Web Service was retired on 2026-11-14.

## Architecture

User opens an ordinary browser -> public hostname -> Render Python Web Service -> wavefinity_web.py (http.server-based application) serves web/index.html and static assets, and responds to /api/* requests -> canonical Python geometry and application modules (organizer_engine, organizer_geometry, organizer_inserts, organizer_drawer, organizer_spaces, organizer_outputs, etc.) -> preview JSON, temporary generated files, /api/export/<token>/<filename> downloads. Some hosted flows write into the visitor's selected folder through browser-files.js rather than storing user files on Render. Distinguish these client-side saves from the server's own temporary generated outputs and settings.

This old HTTP server is NOT the same thing as the canonical Python geometry code: browser-only deployment keeps the canonical geometry via Pyodide/WASM and removes the need for the server as request handler.

## Current checked-in legacy hosting configurations

- render.yaml: service type web, name wavefinity, Python runtime, plan free, autoDeploy false, buildCommand = pip install -r requirements.txt && python -c "import wavefinity_web", startCommand = WAVEFINITY_DEPLOYMENT=hosted python wavefinity_web.py --host 0.0.0.0 --no-browser, healthCheckPath = /api/health, PYTHON_VERSION=3.14.8, WAVEFINITY_PID_FILE=/tmp/wavefinity.pid.
- At cutover, wavefinity.org and www.wavefinity.org were attached to the static site with issued HTTPS certificates; the apex redirects to www. The authoritative DNS/account operations are recorded separately in the PRIVATE Help-Code repository at docs/wavefinity-domain.md, not in this public repo.
- Dockerfile: an ALTERNATIVE historic Hugging Face Spaces Docker SDK build using python:3.14-slim, installs libglib2.0-0 and libgomp1, runs under uid 1000, exposes port 7860 and starts python wavefinity_web.py --host 0.0.0.0 --port 7860 --no-browser. The Dockerfile is not the active Render Python-runtime plan.
- Former Render Web Service hostname: https://wavefinity.onrender.com. The service was retired on 2026-11-14.
- Optional env WAVEFINITY_DATA_DIR (wavefinity_web_impl/_runtime.py) selects the server's data root; without it, the repo APP_DIR is used, and DEFAULT_OUTPUT is DATA_DIR/generated. Server-side legacy preferences can use DATA_DIR/wavefinity_prefs.json and per-OS user configuration. Do not store access tokens or private paths in this doc.
- RENDER_GIT_COMMIT populates the server build identity when supplied by the provider; source fingerprints and /api/health may expose build information to distinguish stale instances.

## Request and filesystem responsibilities

- GET / serves web/index.html; /images/* serves the repository images; /Brochure.md is served from the repo root; static web assets are served from web/.
- GET /api/catalog and /api/health identify the service and runtime.
- POST routes are registered in wavefinity_web.py POST_ROUTES, merged with organizer_drawer.drawer_routes; include preview/validate/feature/layout, generate/connector/print, storage/Space, inventory, AI and slicer preferences.
- Generate/Print can run long and are managed by an operation_id registry and /api/operation-status; server output tokens are time-limited and materialize through GET /api/export/<token>/<filename>.
- The legacy local desktop process can locate and launch Bambu Studio; the hosted/browser variant cannot run local desktop executables. The browser uses showDirectoryPicker and WFFileSystem for authorized local file writes where possible.
- The retired service formerly handled server geometry requests; the live static site runs the geometry engine in the browser.

## Historical Print behavior and the browser replacement

The local Windows Python implementation's `printModelWithReport()` (in `web/app/15-generate-dialogs.js`) uses `/api/print`, `wavefinity_web.launch_slicer()` and an installed slicer executable to generate/reuse output, launch Bambu Studio/OrcaSlicer, report success/partial failure and update the Inventory Printed status. The historical hosted Python mode refuses native Print and directs users to Export, because a remote server cannot start a slicer on the visitor's PC.

**Preservation requirement:** The browser-only edition must KEEP a true Print command, retaining printer/Space validation, file preparation/3MF metadata, part selection and truthful Inventory status, with a browser-safe save/download-and-open-in-slicer handoff. It cannot claim arbitrary executable launch without a supported protocol. This is the explicitly documented legacy-vs-static Print behavior difference, not permission to remove Print. Exact work contract: `Future plans/Browser-only-core-detailed-build-contracts.md`, Owner Print preservation contract and B08.

## Starting the server for recovery and verification

From a clean checkout at the intended historical source SHA and with Python 3.14 and the required native libraries installed:

1. Create and activate a dedicated Python virtual environment. Install dependencies from requirements.txt.
2. Test the import exactly as Render builds: python -c "import wavefinity_web".
3. Start the hosted-compatible local server on an unused port: python wavefinity_web.py --host 127.0.0.1 --port 8765 --no-browser with WAVEFINITY_DEPLOYMENT=hosted in the environment.
4. Open http://127.0.0.1:8765 and confirm /api/health as well as representative preview/generation and export. Use scratch folders only; never test against user-owned production inventory without explicit permission.
5. For Render, inspect Events -> Manual Deploy / Deploy latest commit, verify the actual deployed SHA and /api/health, and verify hostname/TLS in Custom Domains.

Never assume a successful GitHub push triggers deployment; checked-in Render autoDeploy is false. Do not force-push the shared repository or change main to an earlier commit to recover. Restore a known-good version using an ordinary commit/revert only after verifying the impact of newer work, or deploy the pinned historical SHA using supported provider controls.

## Archival and rollback policy

- Keep this document permanently after browser-only cutover; link the last known good server commit SHA and the date when Render was disabled after final acceptance.
- Retain the old implementation in Git history; no feature branch is necessary. Do not delete the geometry source used by Pyodide just because the old HTTP server is no longer deployed.
- Keep legacy startup instructions and necessary pinned external dependency information; record any actual provider-specific runtime changes in this file before retiring Render.
- If browser-only cutover fails, restore the historical server deployment at Render and point wavefinity.org back to it as documented in the PRIVATE Help-Code DNS ownership record. Reverify HTTPS and preserve browser-only data; changing DNS does not migrate or restore user files.
- Never write Porkbun credentials, 2FA recovery codes, billing information, API tokens or real user folder locations into public Git.

## Known limitations of historical hosted method

On a free Render plan, idle/sleep and CPU/RAM limits can affect complex mesh generation, and server-side processing scales with visitor usage. The browser-only edition eliminates server geometry computation.

## Exact recovery-source references

**Cutover record:** Andrew approved full cutover on 2026-11-13. The public domains switched to the browser-only static site and Andrew retired the Python Web Service on 2026-11-14. DNS remains at Porkbun; private DNS details belong in Help-Code/docs/wavefinity-domain.md.

- Last deployed legacy Web Service commit: `2552cbf0d89c8283c37223e4b48a70ccd47289dd` (final deploy live 2026-11-13 23:55 EST).
- Last known historical server source baseline for the successful browser experiment: f25fee144d556a819a80eec6a89313603ce0460b (the branch also contains experimental browser files).
- Static Site commit at the switch: `2552cbf0d89c8283c37223e4b48a70ccd47289dd`; the site auto-deploys main and tracks HEAD.
- Render Static Site: `wavefinity-static` at `wavefinity-static.onrender.com`; both custom domains were verified with certificates issued.
- Render retirement and domain cutover date: 2026-11-14.
- Restore by creating a new Render Web Service from `happydadto5/Wavefinity` at commit `2552cbf0d89c8283c37223e4b48a70ccd47289dd`, using `render.yaml` and the Dockerfile as of that commit. Build with `pip install -r requirements.txt`; start with `WAVEFINITY_DEPLOYMENT=hosted python wavefinity_web.py --host 0.0.0.0 --no-browser`. Remove both custom domains from the static site and add them to the restored service. DNS stays at Porkbun and changes only as Render directs at that time.
- Private Porkbun DNS and Render service-domain details are maintained separately in Help-Code/docs/wavefinity-domain.md.

See Future plans/Browser-only-core-detailed-build-contracts.md work packages B00, B14 and B15 for the explicit cutover and rollback gates.
