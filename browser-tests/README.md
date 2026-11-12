# Story 2979: browser-only geometry feasibility

**Result: unsuccessful POC.** The available pinned browser dependencies cannot
perform Wavefinity's required float64 mesh booleans. No finished bin, valid
finished-shell comparison, or downloadable STL was produced. This experiment
does not replace the Python engine.

Baseline: `d60d78ee5bdbd38dff62e21c6b0f962856f2816b`. Measured on the desktop PC
on 2026-11-12, using installed Chrome and Edge in headless desktop mode.
No software was installed, no new hosting was created, and no production API
was called. The existing application server served static experiment assets.
The browser downloaded its runtime once; calculations ran in worker memory.

## What worked

The native reference uses ordinary `BoxSpec(x=42, y=42, z=28)` and `make_box`,
including canonical wall waves, floor, cavity and wall-lock bumps. It has
80,092 triangles, one component, consistent winding, positive volume and a
watertight surface. Volume is 5,457.809109038011 mm³; bounds are
[-21.275, -21.275, 0] to [21.275, 21.275, 28] mm. Native build: 766.7 ms on
this PC, excluding validation. The float64 reference mesh is preserved in
`reference-42x42x28.npz`; report, profiles, wave samples, source hashes and
tolerances are in `web/browser-local-poc/reference.json`.

Pyodide 0.28.3 loaded NumPy 2.2.5, Shapely 2.0.7/GEOS 3.12.1, networkx 3.4.2
and the pure Python Trimesh 5.0.0 wheel. Native Shapely is 2.1.2. The browser
ran the pinned, unmodified ordinary-bin source files, not a mesh replay.
Namespace package initialization bypassed unrelated eager label/3MF exporters.

The JS Earcut 3.0.2 bridge retains double-precision coordinates and supplies
Trimesh's `mapbox_earcut.triangulate_float64` operation. Separate exterior and
cavity prisms are watertight positive volumes. In both browsers, exterior
profile Hausdorff error was zero, cavity error 3.56e-15 mm or less, and sampled
wave error zero. The envelope has the same bounds as the native finished bin.
145 straight-wall seam samples all measure 0.25 mm across the seam; the
canonical conservative normal clearance bound is 0.16357191087103307 mm.
This measures the outline seam, not physical printed fit or lock-bump parity.

## Exact failure and limits

`organizer_geometry._boolean` explicitly constructs `manifold3d.Mesh64` and
reads `to_mesh64()`. The Pyodide distribution does not include manifold3d,
mapbox-earcut, Trimesh or lib3mf. Trimesh and Earcut were bridged successfully;
no Emscripten/Pyodide wheel is published among manifold3d 3.5.2's 43 release
files. The npm 3.5.2 endpoint is absent (404); the tested JS release is 3.5.0.

The loaded Manifold WASM 3.5.0 module has no `Mesh64` export. Its mesh interface
exposes `Float32Array`, as independently observed in the loaded module and its
published type definitions. A diagnostic coordinate 0.123456789012345 rounds
to 0.12345679104328156 through that interface. The `warpBatch(Float64Array)`
callback is not a float64 mesh input/output interface. Internal double
arithmetic does not recover coordinates rounded at the mesh boundary.

An explicit unavailable-dependency sentinel lets canonical imports run, then
raises `FLOAT64_BOOLEAN_UNAVAILABLE` at the first `Mesh64` constructor in the
actual `make_box` difference. This is a deliberate fail-closed dependency
check, not a failed numerical boolean or an attempted WASM/Python ABI bridge.
No float32 fallback, substitute box, downloaded reference mesh or repaired
mesh is offered as output. Full-shell volume error, validity, bump geometry,
finished-shell mating and STL export remain **unmeasured/unavailable**. The
page exposes STL download only for a successful result; this pinned negative
experiment never produces one. Side connectors were not investigated.

## Measurements

Single cold load per final browser run, new private profile, browser HTTP cache
disabled. Transfer totals include page/static assets and runtime/package
downloads, using CDP encoded bytes. These timings are observations, not
benchmarks of a successful build. Failure times include profile checks and
prism construction before the unavailable boolean.

| Browser | Cold bytes | Loader ms | First attempt ms | Network-blocked attempt ms |
| --- | ---: | ---: | ---: | ---: |
| Chrome 157.0.8103.78 | 22,335,798 | 3,665.7 | 975.7 | 771.6 |
| Edge 157.0.4341.42 | 22,335,713 | 4,377.9 | 1,024.0 | 925.6 |

Both second attempts used page offline emulation plus all-URL blocking on
page and worker targets. Both made **zero new network requests**, reached the
same precision failure, and hid the STL link. All builds additionally reject
worker fetch/XHR/WebSocket calls. This proves the partial path works after
load without network; it does not prove an offline full-bin build.

Python WASM allocated heap was approximately 90.4 MB (86.25 MiB) after each
attempt. Manifold heap size was unavailable. Total JS/browser/process peak
memory was not measured. No runtime exceptions outside the reported dependency
failure, and zero production `/api/` requests, were observed. See raw evidence
in `evidence/chrome.json`, `evidence/edge.json` and `evidence/dependencies.json`.

## Reproduce this exact case

Open `/browser-local-poc.html` on the existing Wavefinity host. Choose **Load
tools**, then **Build bin**, then **Build with network blocked**. The last button
enforces an in-worker network guard; the recorded acceptance exercise also
blocked network independently through the browser debugging protocol.
**Download report** saves the evidence in memory. Cancel or navigation kills
the worker; there is no persisted experiment state or production UI link.
Each Build has a fixed input snapshot and request ID; results from an older
request or replaced worker cannot overwrite a newer request.

For the same bounded automated exercise, run `node browser-tests/run-local-poc.mjs
chrome <existing-server-url>` and repeat with `edge`. It uses installed browsers
and Node built-ins, with disposable profiles/evidence in `local-temp/story-2979`.
This is the story-specific acceptance exercise, not a general test suite.

To deliberately establish a new baseline, use the project's existing working
Python environment to run `browser-tests/prepare-local-poc.py` against committed
canonical sources. It regenerates both the double-precision native reference
and the immutable browser source bundle. This preparation uses native Python;
the web server and browser calculation path never invoke it. Before landing,
compare every `source_sha256` entry against current source. Any mismatch
invalidates the comparison; regenerate and repeat the same ordinary-bin case
before making a new parity claim. This report applies only to its stated pin.

## Mitigation and next Story

Keep the existing Python production geometry. A follow-up Story must deliver a
pinned prebuilt browser Manifold float64 mesh input/output bridge, or a
compatible Pyodide manifold3d wheel, with matching Mesh64 semantics. Include
uint64 index conversion/range handling, boolean status and explicit WASM object
cleanup. Then re-run this ordinary bin to completion, compare finished mesh
bounds/volume/validity/waves/seams and download/reopen its STL before considering
side connectors. Building that new runtime is outside this no-installation
dependency investigation. This is a proposed next Story; no new Story was filed.

Future 3MF is a separate dependency/export task: lib3mf 2.5.0 publishes native
Windows/Linux/macOS wheels, not a browser WASM package. Its native wrapper
cannot simply load in Pyodide. A prebuilt WASM binding or a separately validated
browser XML/ZIP implementation would be needed, including Wavefinity's strict
validation, multipart/material and slicer metadata behavior. 3MF is not required
or implemented here.

Primary dependency sources: [Pyodide package loading](https://pyodide.org/en/stable/usage/loading-packages.html),
[pinned Pyodide package lock](https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide-lock.json),
[pinned Manifold types](https://cdn.jsdelivr.net/npm/manifold-3d@3.5.0/manifold.d.ts),
[Manifold mesh interface](https://manifoldcad.org/docs/jsapi/classes/manifold.Mesh.html),
[manifold3d release files](https://pypi.org/pypi/manifold3d/3.5.2/json),
[lib3mf release files](https://pypi.org/pypi/lib3mf/2.5.0/json).
