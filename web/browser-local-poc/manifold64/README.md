# Browser double-precision bridge

This bridge builds the Manifold 3.5.0 C++ `MeshGL64` input and output API
for the isolated browser experiment. Coordinates cross both boundaries as
JavaScript numbers / `Float64Array`; the integer face indices use 32 bits in
JavaScript/WASM. The Python engine and its boolean operation order remain
unchanged. STL export uses STL's standard 32-bit coordinate format.

`build.sh` fetches Manifold commit `541c33bd2ab9b1a72816bdecff90566c0a3ee56c`
and builds with Emscripten 4.0.10, CMake and Ninja. The generated JavaScript and
WASM are served as static assets. See LICENSE for the upstream license.

## Validation on 2026-11-12

Linux Chromium 156, using the Wavefinity web server: the 42 × 42 × 28 mm bin
loaded, built and downloaded; the next build also succeeded with all browser
network requests blocked. No `/api/` requests were made. The generated mesh
was watertight, consistently wound and one component; its bounds were identical
to the pinned native reference to 1e-7 mm and its volume differed by less than
1e-7 relative. The profile and sampled 0.25 mm mating gap agreed within 1e-7 mm.

For a second test, the same bridge and canonical sources were run with an
84 × 42 × 28 mm spec and compared with a freshly generated native reference.
After STL export, maximum bidirectional nearest-vertex differences were
0.00000129 mm and 0.00000213 mm respectively (tolerance 0.00001 mm).
Each mesh had the same vertices and face count as its reference; 12 triangles
per mesh used different diagonals. Their centroid-to-reference-surface gaps
were below 0.00000030 mm. This comparison includes cavity and lock geometry;
no separate physical fit or printed part was tested. PyMeshFix independently
reported zero boundary edges and zero intersecting triangles for both STLs.
These measurements do not replace a Windows Chrome/Edge acceptance run.
