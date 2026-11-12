# Wavefinity — Legacy Python HTTP / Render hosting (preservation record)

Status: historical-operating-method reference. The Python-hosted implementation is still present during the browser-only migration; this document is a preservation record, not a declaration that the new static deployment has launched.

## Architecture

User opens an ordinary browser -> public hostname -> Render Python Web Service -> wavefinity_web.py (http.server-based application) serves web/index.html and static assets, and responds to /api/* requests -> canonical Python geometry and application modules (organizer_engine, organizer_geometry, organizer_inserts, organizer_drawer, organizer_spaces, organizer_outputs, etc.) -> preview JSON, temporary generated files, /api/export/<token>/<filename> downloads. Some hosted flows write into the visitor's selected folder through browser-files.js rather than storing user files on Render. Distinguish these client-side saves from the server's own temporary generated outputs and settings.

This old HTTP server is NOT the same thing as the canonical Python geometry code: browser-only deployment keeps the canonical geometry via Pyodide/WASM and removes the need for the server as request handler.

## Current checked-in legacy hosting configurations

- render.yaml: service type web, name wavefinity, Python runtime, plan free, autoDeploy false, buildCommand = pip install -r requirements.txt && python -c "import wavefinity_web", startCommand = WAVEFINITY_DEPLOYMENT=hosted python wavefinity_web.py --host 0.0.0.0 --no-browser, healthCheckPath = /api/health, PYTHON_VERSION=3.14.8, WAVEFINITY_PID_FILE=/tmp/wavefinity.pid.
- Render managed domain: wavefinity.org; www.wavefinity.org redirects to apex, with HTTPS certificate. The authoritative DNS/account operations are recorded separately in the PRIVATE Help-Code repository at docs/wavefinity-domain.md, not in this public repo.
- Dockerfile: an ALTERNATIVE historic Hugging Face Spaces Docker SDK build using python:3.14-slim, installs libglib2.0-0 and libgomp1, runs under uid 1000, exposes port 7860 and starts python wavefinity_web.py --host 0.0.0.0 --port 7860 --no-browser. The Dockerfile is not the active Render Python-runtime plan.
- Main public Render service hostname during migration: https://wavefinity.onrender.com (formerly used directly; retains value for troubleshooting). Active deployment SHA must be read from Render Events; do not infer it merely from GitHub main.
- Optional env WAVEFINITY_DATA_DIR (wavefinity_web_impl/_runtime.py) selects the server's data root; without it, the repo APP_DIR is used, and DEFAULT_OUTPUT is DATA_DIR/generated. Server-side legacy preferences can use DATA_DIR/wavefinity_prefs.json and per-OS user configuration. Do not store access tokens or private paths in this doc.
- RENDER_GIT_COMMIT populates the server build identity when supplied by the provider; source fingerprints and /api/health may expose build information to distinguish stale instances.

## Request and filesystem responsibilities

- GET / serves web/index.html; /images/* serves the repository images; /Brochure.md is served from the repo root; static web assets are served from web/.
- GET /api/catalog and /api/health identify the service and runtime.
- POST routes are registered in wavefinity_web.py POST_ROUTES, merged with organizer_drawer.drawer_routes; include preview/validate/feature/layout, generate/connector/print, storage/Space, inventory, AI and slicer preferences.
- Generate/Print can run long and are managed by an operation_id registry and /api/operation-status; server output tokens are time-limited and materialize through GET /api/export/<token>/<filename>.
- The legacy local desktop process can locate and launch Bambu Studio; the hosted/browser variant cannot run local desktop executables. The browser uses showDirectoryPicker and WFFileSystem for authorized local file writes where possible.
- The site can be woken, deployed or rolled back by Render; requests to server geometry cease only when the full static migration has finished.

## Historical Print behavior and the browser replacement

The local Windows Python implementation's `printModelWithReport()` (in `web/app/15-generate-dialogs.js`) uses `/api/print`, `wavefinity_web.launch_slicer()` and an installed slicer executable to generate/reuse output, launch Bambu Studio/OrcaSlicer, report success/partial failure and update the Inventory Printed status. The current hosted Python mode refuses native Print and directs users to Export, because a remote server cannot start a slicer on the visitor's PC.

**Preservation requirement:** The browser-only cutover must KEEP a true Print command, retaining printer/Space validation, file preparation/3MF metadata, part selection and truthful Inventory status, with a browser-safe save/download-and-open-in-slicer handoff. It cannot claim arbitrary executable launch without a supported protocol. This is the explicitly documented legacy-vs-static Print behavior difference, not permission to remove Print. Exact work contract: `Future plans/Browser-only-core-detailed-build-contracts.md`, Owner Print preservation contract and B08.

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

On a free Render plan, idle/sleep and CPU/RAM limits can affect complex mesh generation, and server-side processing scales with visitor usage. The browser-only replacement aims to eliminate server geometry computation, but the full cutover requires client-side validation, 3MF, persistence, all Space types, and backend-free acceptance—not merely the two successful proof-of-concept bins.

## Exact recovery-source references (HARD B15 prerequisite — do not retire the old service while incomplete)

**Current status:** The values below are NOT YET RECORDED because no static cutover has happened. This is intentional honesty, not an already workable rollback. B15 must read actual Render dashboard/revision data, fill every recovery-critical field and document a real source restore procedure BEFORE disabling/retiring the old service. Full DNS target/rollback and service association details belong in private Help-Code/docs/wavefinity-domain.md, not this public document. Do not invent values from GitHub main. No application tests are required by coders.

- Last actually verified production Render commit: NOT YET RECORDED; must be read from live Render Events.
- Last known historical server source baseline for the successful browser experiment: f25fee144d556a819a80eec6a89313603ce0460b (the branch also contains experimental browser files).
- Final **actually deployed** Render Static Site commit SHA: NOT YET RECORDED.
- Render Static Site real hostname/service identifier and TLS association: NOT YET RECORDED.
- Render retirement / approved DNS cutover date: NOT YET RECORDED.
- Exact restore source/ref and legacy Web Service reactivation steps: NOT YET RECORDED.
- Private Porkbun old/new DNS records + old/new Render service-domain associations, with rollback procedure: NOT YET RECORDED in private Help-Code.

See Future plans/Browser-only-core-detailed-build-contracts.md work packages B00, B14 and B15 for the explicit cutover and rollback gates.
