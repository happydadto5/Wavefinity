# Wavefinity browser migration — outside review brief

- **Prepared by:** Codex
- **Date:** 2026-09-04
- **Implementation commit:** `4401dac` (`Add local browser organizer app`)

## Review objective

Wavefinity previously used a large Tkinter interface over a tested Python CAD
engine. This change adds a browser interface without porting or duplicating the
geometry implementation. The review should determine whether the new local web
boundary preserves geometry/export behavior, safely exposes local file-writing
operations, and provides a reliable replacement UI while the desktop fallback
remains available.

The intended architecture is:

```text
Browser UI (HTML/CSS/JavaScript)
              |
       same-origin JSON
              |
Local loopback service (Python standard library)
              |
Existing design, validation, mesh and 3MF export modules
```

This is a local application, not a hosted service. By default it listens only
on `127.0.0.1:8765` and opens the user's normal browser.

## What changed

### Browser application

The new interface includes:

- **Build your bin:** X/Y grid units, height, fused/removable/cartridge mode,
  the seven registered interior supports, live parameter editing, placement,
  update and deletion.
- **Customize your bin:** curved scoop and the existing advanced physical and
  connector settings.
- **Label your bin:** label text, Bottom/Top selection and the part-name suffix
  used in generated filenames.
- A responsive 3D canvas with drag rotation, wheel zoom and reset.
- A top-down 2D editor with support selection, movement and corner resizing.
- Version-1 `.wavefinity.json` design download and validated reopening.
- Browser-triggered bin, connector and sampler `.3mf` generation into the
  selected local output directory.

Both canvas renderers use one uniform scale derived from the available width
and height. Window resizing changes the drawing size but does not independently
stretch an axis. Support parameter edits are debounced and rebuilt through
Python, so the draft drawing represents the same builder used for export.

### Python service

`wavefinity_web.py` uses only the Python standard library for HTTP. It is a
stateless translation layer: the complete design travels with every operation,
is parsed through the existing models, and is returned in the existing saved
design schema.

The API covers:

| Route | Purpose |
|---|---|
| `GET /api/health` | Identify an existing Wavefinity server. |
| `GET /api/catalog` | Registered supports, modes and initial values. |
| `POST /api/preview` | Validate a design and return camera-independent geometry. |
| `POST /api/design/validate` | Validate and normalize a saved design. |
| `POST /api/feature/default` | Create an engine-derived support draft. |
| `POST /api/feature/draft` | Build actual mesh faces for live parameter preview. |
| `POST /api/feature/apply` | Snap, validate, add or update a support. |
| `POST /api/feature/delete` | Remove a support. |
| `POST /api/layout/mode` | Convert a layout between print modes. |
| `POST /api/generate` | Generate the organizer parts. |
| `POST /api/connector` | Generate a connector. |
| `POST /api/sampler` | Generate the fit sampler. |

Boolean/mesh work is protected by a process-wide lock. This intentionally
serializes geometry operations instead of risking concurrent calls into the
mesh backends. UI camera movement remains local and does not call Python.

### Launch and fallback behavior

- `Launch_Organizer_UI.bat` now starts the browser interface by default.
- `Launch_Organizer_Desktop.bat` and `Launch_Organizer_UI.bat --desktop` retain
  the former Tkinter application.
- `Launch_Organizer_UI.bat --check` checks imports without starting a UI.
- A second browser launcher detects the existing local service and opens it
  instead of starting a second process on the same Windows port.
- The CLI and all pre-existing generation entry points remain in place.

## What deliberately did not change

The browser does not calculate box outlines, insert geometry, support meshes,
label placement, scoop geometry, connector fits or exports. Those remain in:

- `organizer_engine.py`
- `organizer_inserts.py`
- the non-widget functions in `organizer_app.py`

The following shared contracts are unchanged:

- `BoxSpec`, `Feature`, `Layout`, `Item`, `Segment` and `Zone`
- the registered `FEATURE_BUILDERS`
- version-1 design/layout JSON
- layout/customization clearance validation
- fused, fitted-insert and cartridge builders
- `.3mf` export functions and mesh validation

This is the main risk-control decision: the migration adds a consumer of the
engine rather than replacing the engine.

## Security boundary

The service can write generated files, so the local HTTP boundary received an
explicit hardening pass:

- Loopback binding by default; it is not exposed to the LAN.
- POST routes require `application/json`.
- Browser requests with a foreign `Origin` are rejected before route logic.
- Static paths are resolved beneath the `web` directory to prevent traversal.
- Responses use `nosniff`, same-origin resource policy and no-referrer headers.
- The page uses a restrictive content-security policy: scripts, styles and API
  connections are same-origin; objects, base replacement and framing are
  disabled.
- Request bodies are capped at 25 MB.
- No cookies, user accounts, credentials, remote resources or telemetry were
  added.

The output-directory field intentionally allows the local user to select an
arbitrary writable path. That is application functionality, not a sandbox.

## Verification evidence

### Automated

- `python -m unittest` — **190 tests passed** in 169.702 seconds.
- `python -m unittest test_wavefinity_web` — **8 tests passed**.
- `node --check web/app.js` — passed.
- `Launch_Organizer_UI.bat --check` — passed.
- `git diff --check` — passed before commit.

The new tests cover the complete registered-support catalog, default design,
real parameter-driven mesh changes, add/update/delete schema round-tripping,
mode conversion, preview geometry/metadata, static serving, saved-design
validation, clear 400 errors and rejection of a foreign-origin generation
request.

### Browser exercise

The available controlled browser was Codex's in-app Chromium browser; Edge was
not exposed to the automation session. Testing covered narrow and wide layouts,
live dimension changes, support parameter changes before placement, support
placement, label and scoop controls, visible conflict reporting, removable-mode
conversion, the 2D layout view and browser-triggered export. The browser console
finished with no errors or warnings.

A real removable organizer was generated through the browser:

- `generated/Box 40 x 48 x 40 DRIVERS.3mf` — 848,974 bytes
- `generated/Insert 40 x 48.3mf` — 12,489 bytes

These generated artifacts are ignored working output and were not committed.

## Known limitations and follow-up risks

1. **Design download needs an ordinary-browser confirmation.** The controlled
   browser displayed the successful download feedback, but its automation layer
   did not surface the synthetic Blob download as a downloadable event.
2. **The JavaScript UI does not yet have a standalone DOM test suite.** Python
   API contracts, JavaScript syntax, and interactive browser QA are covered;
   long-term UI work would benefit from checked-in browser automation.
3. **Very complex previews may be bandwidth/paint heavy.** Actual triangle
   faces are serialized as JSON and painted on a 2D canvas. Camera motion is
   fast because it stays client-side, but an unusually dense design can produce
   a large initial preview payload.
4. **Geometry requests are serialized.** This is appropriate for one local
   user and safer for the current mesh stack, but it is not a multi-user server
   architecture.
5. **The Tkinter fallback should remain for at least one release cycle.** It is
   the recovery path if an untested browser/platform combination exposes a UI
   regression.

## External-audit resolution — 2026-09-04

Codex reproduced and accepted the audit's three live defects. Automatic holder
values are now display-only until edited, removable-holder tags and tint reach
both browser canvases, and the default post adapts to an 8 mm cartridge cell.
The fourth finding was already resolved in the reviewed branch because the
shared JSON response helper applies the baseline headers to both GET and POST;
the health-route test now verifies them explicitly.

The resolution passed all 193 tests. A Microsoft Edge smoke test also confirmed
that an 8 mm cartridge post can be selected, placed and previewed on the default
starter bin without console warnings or errors.

## Requested reviewer focus

Please prioritize these areas:

1. Confirm that every browser mutation returns to the existing Python models
   before validation or export; flag any geometry rule duplicated in JavaScript.
2. Review `/api/generate`, `/api/connector` and `/api/sampler` for ways a foreign
   webpage could trigger local writes despite the origin/content-type checks.
3. Review async request ordering in the live draft and full preview. Stale
   responses are discarded with request counters; verify all state-changing
   paths preserve that rule.
4. Exercise drag and resize near all four layout boundaries, around another
   support, and against scoop/top-label keep-outs in all three modes.
5. Compare one saved design and its resulting mesh reports between Tkinter/CLI
   and browser workflows.
6. Smoke-test startup, save/open, preview interaction and one export in Edge.
7. Check keyboard navigation, focus visibility, screen-reader names, narrow
   viewport behavior and high-DPI canvas clarity.
8. Profile preview response size and interaction smoothness with several dense
   cradle/nest/bore supports.

## Reproduction commands

From `C:\Users\happy\Projects\Wavefinity`:

```powershell
# Start the browser application without opening a tab automatically
.venv\Scripts\python.exe wavefinity_web.py --no-browser

# Then open
# http://127.0.0.1:8765/

# Run the new contract tests
.venv\Scripts\python.exe -m unittest test_wavefinity_web

# Run everything
.venv\Scripts\python.exe -m unittest

# Check both launch targets import
cmd /c Launch_Organizer_UI.bat --check

# Start the retained desktop fallback
cmd /c Launch_Organizer_Desktop.bat
```

## File map

| File | Review role |
|---|---|
| `wavefinity_web.py` | Local server, API translation, validation and security boundary. |
| `web/index.html` | Browser structure and accessible control labels. |
| `web/styles.css` | Responsive two-pane/single-pane layout and visual states. |
| `web/app.js` | Client state, canvas projection, editor interactions and API calls. |
| `test_wavefinity_web.py` | Browser-service contract and security regressions. |
| `Launch_Organizer_UI.bat` | Default browser launch and environment bootstrap. |
| `Launch_Organizer_Desktop.bat` | Explicit desktop fallback. |
| `README.md` | User-facing operation and architecture notes. |
| `TESTING.md` | Test runs and defects caught during browser QA. |
| `changelog.md` | Dated implementation record. |

## Current repository state at handoff

- Branch: `main`
- Browser migration commit: `4401dac`
- Remote: `origin/main` matched the local commit at implementation handoff.
- The browser application was left running on `http://127.0.0.1:8765/` for
  inspection.
