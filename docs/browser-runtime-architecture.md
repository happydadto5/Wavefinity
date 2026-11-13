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
| Version pins (Pyodide 0.28.3, wheels, MeshGL64 bridge) and vendored assets | planned `web/browser-core/vendor/`, built by planned `scripts/build-browser-core.py` (B02) |
| Packaged engine and its source hashes | planned `web/browser-core/engine/canonical.zip` and `engine/manifest.json` (B02) |
| Route manifest (every route: local or retired, owner, runtime, module) | planned `web/browser-core/contracts/route-manifest.json` (B01); checked against runtime registrations by the static build (B14) |
| Proof-of-concept source that B02 starts from | `web/browser-local-poc*`, `web/browser-local-poc/` (not shipped in the final bundle) |
| Recovery record (last deployed SHAs, hostnames, cutover date, restore steps) | [legacy-python-server-hosting.md](legacy-python-server-hosting.md), section "Exact recovery-source references" — fields are intentionally still "NOT YET RECORDED" until B15 |
| Private domain/DNS/account record | private Help-Code repository (`docs/wavefinity-domain.md`), never in this public repo |

Do not record credentials, account values, private domain details or real user folder paths in this public document.
