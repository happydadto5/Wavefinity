# Wavefinity — Browser runtime architecture (static, browser-only)

Status: target architecture for the browser-only migration (GPU/server elimination). The migration is **not yet cut over**: the Python-hosted path is still the live implementation, and the `web/browser-core/` tree described below is built by later packages (B01–B14). Paths marked *planned* do not exist in the repository yet. Final authority: `Future plans/Browser-only-migration-execution-spec.md`; package details: `Future plans/Browser-only-core-detailed-build-contracts.md`. The old server path is preserved in [legacy-python-server-hosting.md](legacy-python-server-hosting.md).

## Request and data flow

```
existing UI (web/index.html, web/app/*, web/spaces/*)
  -> local API layer (planned web/browser-core/local-api.js, same call shapes as the old /api/* routes)
  -> browser Worker
  -> pinned Pyodide 0.28.3
  -> canonical Wavefinity Python engine (the same organizer_* / geometry source, packaged as engine/canonical.zip)
  -> custom Manifold MeshGL64 float64 WASM bridge (geometry kernel)
  -> preview data / 3MF / export files, returned to the UI as in-memory results or Blob downloads
```

- Geometry runs on the visitor's CPU. It is not a rewrite to simplified JavaScript and not float32; the canonical Python engine and the float64 MeshGL64 kernel are kept.
- There is **no Wavefinity-operated server-side geometry process** and no visitor-installed Wavefinity application. The hosting side only serves static files.
- Routes the UI used to call as `/api/*` are answered locally. Python-side routes are registered through `route_dispatch.py` (planned); JavaScript-side routes (Spaces/preferences storage, browser AI providers) are registered in JS. Unknown routes fail closed.
- The old `wavefinity_web.py` HTTP server is a different thing from the canonical geometry code. The server goes away at cutover; the geometry source stays and is what Pyodide runs.

## Local files

- Folders, Spaces, preferences and generated files are handled with browser filesystem APIs through `WFFileSystem` in `web/browser-files.js` (File System Access API, `showDirectoryPicker`). Full persistent folder use targets desktop Chrome and Edge.
- Unsupported browsers get an early capability warning before any Space creation, write or autosave, and are limited to ephemeral previews and Blob downloads.
- Visitor files are never uploaded to or stored on a Wavefinity server. There is no automatic cross-browser handle/data transfer; moving between browsers uses explicit Space/preferences export and import.
- Print cannot launch a local executable from a browser. The static Print command keeps validation, file preparation and truthful Inventory status, and hands off via save/download and open-in-slicer (see the Print section of the legacy record and build-contract B08).

## Single-cutover principle

The app is moved in one final cutover, not through a long-lived dual mode. No compatibility shims keep a half-migrated app working, and the old Render Web Service is not retired until the static site is accepted and the recovery record below is filled in (B15, with explicit owner approval).

## Where things live

| Item | Location |
| --- | --- |
| Version pins (Pyodide 0.28.3, wheels, MeshGL64 bridge) and vendored assets | `web/browser-core/vendor/`, verified by `scripts/build-browser-core.py` (B02) |
| Packaged engine and its source hashes | `web/browser-core/engine/canonical.zip` and `engine/manifest.json` (B02) |
| Route manifest (every route: local or retired, owner, runtime, module) | `web/browser-core/contracts/route-manifest.json` (B01); checked against runtime registrations by the static build (B14) |
| Proof-of-concept source that B02 starts from | `web/browser-local-poc*`, `web/browser-local-poc/` (not shipped in the final bundle) |
| Recovery record (last deployed SHAs, hostnames, cutover date, restore steps) | [legacy-python-server-hosting.md](legacy-python-server-hosting.md), section "Exact recovery-source references" — fields are intentionally still "NOT YET RECORDED" until B15 |
| Private domain/DNS/account record | private Help-Code repository (`docs/wavefinity-domain.md`), never in this public repo |

Do not record credentials, account values, private domain details or real user folder paths in this public document.

## Reproducible browser assets (B02)

Run `python scripts/build-browser-core.py` at every shipping build. It uses only
the standard library, never imports the native engine, never invokes Emscripten,
and always regenerates `canonical.zip` and its source-hash manifest from this
checkout. ZIP ordering, timestamps, permissions and source line endings are fixed.
Canonical package names remain unchanged; `engine/*.py` becomes `wf_browser_core/`.
`engine/manifold_bridge.py` provides a dimension-independent float64 adapter;
the later worker installs it before importing canonical geometry. It requires
the worker's combined-heap capacity callback and forwards geometry failures.

The committed vendor manifest pins every shipped byte, upstream download URL,
Pyodide dependency edge, bridge source/binary and required font. Normal builds
fail on missing or changed vendor inputs. `--fetch-vendor` can restore missing
HTTPS downloads at build time using those hashes; it cannot replace changed
inputs or rebuild the bridge. Its production source, binaries, build recipe and
license now live in `vendor/manifold64/` independently of the prototype. Bridge
rebuilds require the pinned external Emscripten 4.0.10 toolchain; review the new
binary hashes explicitly before updating the vendor manifest.

Browser pins are Pyodide 0.28.3, NumPy 2.2.5, Shapely 2.0.7 / GEOS 3.12.1,
networkx 3.4.2, Trimesh 5.0.0, Earcut 3.0.2 and Manifold C++ 3.5.0 at
`541c33bd2ab9b1a72816bdecff90566c0a3ee56c`. Matplotlib 3.8.4, Pillow 11.3.0,
OpenCV 4.11.0.86, SciPy 1.14.1, lxml 6.0.0 and their recursive dependencies
come from the same Pyodide release lock, rather than native requirements.txt.
Matplotlib's wheel carries the engine's DejaVu Sans Bold TTF and its license;
the font member's hash is separately recorded. These assets are self-hosted;
the later worker must set a local Pyodide indexURL and use the manifest's local
wheel/module paths. Manifest upstream URLs are build provenance, not runtime URLs.
The bridge is single-threaded (`MANIFOLD_PAR=OFF`); no pthread/SAB or COOP/COEP
requirement is introduced.

The build reports per-asset raw and gzip sizes and refuses to silently trim
features when the 64 MiB compressed planning target is exceeded. These are
encoded artifact sizes, not observed transfers or a hosting bandwidth allowance.
B14 must include the remaining UI/worker assets in final dist accounting.
The 1536 MiB combined allocated WASM heap target is likewise provisional:
individual WASM32 memories can grow beyond that sum without a worker policy,
and a large boolean can temporarily exceed a pre-operation estimate. B03 owns
heap checks, allocation errors and worker retirement; largest-job peak memory
is unknown. No benchmark or browser execution establishes a memory guarantee.

Bundling native-source modules does not complete their browser adaptation.
Native lib3mf is intentionally absent pending B07's serializer; B12 still owns
Photo Nest integration with the local cv2/Pillow wheels. Do not eagerly import
the native-dependent routes before those adapters are supplied. No route
handlers, dispatcher, hosting switch or new user-facing browser mode ships in B02.
