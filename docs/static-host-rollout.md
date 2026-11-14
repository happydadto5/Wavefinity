# Static host rollout (browser-only edition)

This rollout handoff records the move to a Render **Static Site**. Andrew approved cutover on 2026-11-13; the public domains switched and the old Python Web Service was retired on 2026-11-14. See the [legacy hosting/recovery guide](legacy-python-server-hosting.md) for the recovery record.

## What changes for users

- No more ~60-second wake-up of a sleeping Python process: the site is static files on a CDN.
- First load downloads the browser engine (Pyodide/WASM) and starts it. Worked out on 2026-11-13 from
  the files the live page actually requests on first load: about 45 MB uncompressed (43 MiB; about 37 MB
  compressed), against the 64 MiB planning budget. The published site is about the same
  size: four vendored files the app never loaded (SciPy, lxml, OpenBLAS and the unused `pyodide.js` loader,
  about 17 MB) were removed on 2026-11-14. That one-time delay remains; the browser caches the
  files afterwards.
- Work stays on the user's own PC (their chosen Space folder). A DNS or hosting change neither uploads nor
  restores any user files. Browsers without folder access (Firefox/Safari) get the honest limited mode
  described in [static-capability-differences.md](static-capability-differences.md).
- Render Static Sites are free within monthly bandwidth and build-minute allowances; they are not unlimited.
  Check the allowances and the per-file size limit in Render's current documentation when creating the site
  (the largest shipped file is the 11.7 MB OpenCV wheel) and tell Andrew before anything is billed.

## Build

```
python3 scripts/build-static-site.py
```

Python standard library only, no network, no Emscripten. It aborts (non-zero exit) on:

- any route that is missing, duplicated, extra or unclassified between the flat route declaration
  (`web/browser-core/contracts/route-declaration.json`, the table both local runtimes dispatch from), the route
  manifest (`route-manifest.json`) and the source-route index, or a declared module that is unavailable;
- a retired route that is callable, or a retired route without its named local replacement;
- a stale browser engine bundle, a missing production file, a page reference that is not in `dist/`, a
  proof-of-concept file, or non-shipping source reaching `dist/`.

It regenerates `web/browser-core/engine/canonical.zip` and its manifest from the checked-out sources, then writes
`dist/`: production `web/*` at the root, repository-root `images/` at `dist/images/`, and `Brochure.md` as both
`dist/Brochure.md` and byte-identical `dist/brochure.md`. The bridge's C++/shell build inputs and the legacy `web/images/`
duplicates (the canonical artwork is `images/`) are not shipped.

## Render dashboard: Static Site setup (historical)

The Web Service could not be converted, so a separate Static Site was created through the dashboard, not a Blueprint:

| Setting | Value |
|---|---|
| Type | New → Static Site |
| Repository / branch | `happydadto5/Wavefinity` / `main` |
| Name | `wavefinity-static` (if free) |
| Build Command | `python3 scripts/build-static-site.py` |
| Publish Directory | `dist` |
| Auto-Deploy | On |
| Hostname | `wavefinity-static.onrender.com` |

If Render's build image cannot run the command, report the exact error; the script needs only Python 3.

### Settings → Headers (dashboard, not `render.yaml`)

| Path | Header | Value |
|---|---|---|
| `/*` | `X-Content-Type-Options` | `nosniff` |
| `/*` | `Referrer-Policy` | `no-referrer` |
| `/*` | `X-Frame-Options` | `DENY` |
| `/*` | `Content-Security-Policy` | `default-src 'self'; script-src 'self' 'unsafe-eval' 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' https://api.openai.com https://api.anthropic.com https://generativelanguage.googleapis.com; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; font-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'` |
| `/*.wasm` and `/**/*.wasm` | `Content-Type` | `application/wasm` |
| `/*.mjs` and `/**/*.mjs` | `Content-Type` | `text/javascript; charset=utf-8` |
| `/`, `/index.html`, `/Brochure.md`, `/brochure.md`, `/app/*`, `/spaces/*`, `/browser-core/*.js`, `/browser-core/contracts/*`, `/browser-core/engine/*` | `Cache-Control` | `no-cache` |

- **Live header record (read from https://wavefinity-static.onrender.com on 2026-11-13).** The dashboard
  policy is reflected in the table above; no COOP/COEP header is served. Keep this record in step with
  the dashboard whenever a header is changed there. The in-browser Python runtime requires `'unsafe-eval'`.
- **No immutable caching rule.** No shipped asset has a content hash in its file name, and a stable name must
  never be cached immutably. Do not add one.
- **No COOP/COEP headers.** The Manifold bridge is single-threaded and needs no cross-origin isolation.
- **AI provider origins.** The bring-your-own-key AI chat calls the three provider origins in the table directly
  from the browser. Copy/paste AI works without them.
- The microphone (AI dictation) needs no header here; no `Permissions-Policy` header is set.

## Domain cutover (completed 2026-11-14)

Registration and authoritative DNS stay at Porkbun. No nameserver change, registrar transfer, new domain, or
other host.

1. Attach `wavefinity.org` and `www` to the NEW Static Site in Render (Settings → Custom Domains). Render may
   require detaching them from the old Web Service first, which can briefly interrupt the live site.
2. Edit only the records Render's custom-domain instructions say must change, inside Porkbun. Keep the apex
   record only if Render's current instructions still call for it; point `www` at the new Static Site's real
   hostname.
3. Confirm both domains serve over HTTPS and the apex redirects to `www` in the new site's settings.
4. Fill in [static-host-rollback.md](static-host-rollback.md) **before** the old service is retired (B15).

The exact DNS record values live **only** in the private Help-Code record; they are not written here or in code.

## Historical approval gates (approved for this cutover)

- creating the Static Site if it could incur a charge or change a plan;
- detaching either domain from the old service, or any change at Porkbun;
- disabling, suspending or deleting the old Web Service;
- adding AI provider origins to the Content-Security-Policy.
