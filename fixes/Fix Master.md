# Wavefinity Fix Master

Permanent Help Code ledger. Individual fix files may be deleted after final review, but entries here remain.

This ledger was introduced after some earlier fixes already existed. The entries below reconstruct the currently visible/known fixes without inventing unavailable history.

## Fix 002 — Edge Trim Print-Bed Splitting
- **Status:** Needs remediation work
- **Fix file:** `/fixes/fix-002.md`
- **Notes:** Correction 1 is present in the fix file; keep the existing exact-perimeter/minimum-piece requirements. Await remediation/review lifecycle.

## Fix 003 — Base Trim Drop-In Joint and Size Presets
- **Status:** Work completed, ready for outside review
- **Fix file:** `/fixes/fix-003.md`
- **Implementation thread:** `Base Trim Joint Imp #3`
- **Notes:** Implementation outbrief is present in the fix file. Final completion must be determined by outside ChatGPT review before the fix file is deleted.

## Fix 004 — Space Onboarding Redesign
- **Status:** Correction 5 implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Correction 5 repaired the Render startup blocker (`drawer_routes`/`generate_connectors`/`print_spacers_and_connectors` restored at module scope in `organizer_drawer.py`, out of the unreachable block left after `generate_spacers()`'s return), the stale `create_space_text` import (now `configure_space_text` with a built `raw_def`, including `trim_size`), the Space API route contract (`/api/space/use-untyped` and `/api/space/create` now registered; `organizer_spaces.space_routes()` no longer references undefined `set_inventory`/`set_bin_defaults`/`open_folder`, which were missing entirely and would have raised `NameError` at import time as the very next startup blocker), the literal `\n` artifacts in `web/spaces.js`, the Drawer spacer DOM/JS mismatches (`dl-sp-flex` → `dl-sp-flexible`, a real `#dl-sp-print` button wired to the existing `#spacer-print-dialog`, `DL.spacerPrintRows()` → `DL.spacerPrintGroups()`), the invalid `save_inventory(..., bins=...)` call (now uses real `new_bins`, mm-valued `x`/`y`, and IDs the placements actually reference), and the Shapely/trimesh union type mismatch in `_serpentine_flexure` (now `shapely.ops.unary_union`, verified to produce watertight meshes).
  Static review under this correction also found and fixed: a missing `_overlaps` helper (called but never defined); `plan_spacers` candidates stored grid-cell `gx`/`gy` instead of the documented mm `x`/`y`, which would have mis-rendered and made `drawer_report` misclassify spacer placements as grid bins; `DL.spacerPrintGroups()`/`DL.printSelectedSpacers()` reading a `.row`/`.bin` field that `DL.items()` doesn't have, meaning edge-facing spacers (which have no `gx`) never appeared in the print dialog at all; `SP.designBox` called on Portable Space setup but never defined; `SP.designSurface` building a fake design object instead of reusing `makeBaseTrimDesign()`; `SP.crossTypeCheck` returning `false` (blocking) for every folder with no active Space, and never actually wired to a real UI entry point (`#design-type` does not exist — the real control is `#bin-type`/`changeBinType()`, now wired, plus the drawer panel's "Make Base Trim" path); `wireInfoButtons()` running once at startup before the Drawer panel's `dl-space-info-*` buttons exist, so Edit/Show Folder/New Drawer Space silently never wired inside Drawer mode; `SP.updateSpace()` reading the wrong shape back from `/api/space/update`; and a `drawer_report()` edge-spacer validity check comparing against the whole grid rectangle instead of actually-occupied cells, which flagged every freshly-generated back/right spacer as "no longer fits" whenever it reached across still-empty grid on its way to the wall.
  Verified statically: `import wavefinity_web` succeeds end-to-end in the project venv (previously failed at `organizer_drawer` import); all `/api/drawer/*`, `/api/space/*`, `/api/folder/*` routes present and callable; every `web/spaces.js` API path matches a registered route; `node --check` clean on all touched `web/*.js`; direct calls into `plan_spacers`/`generate_spacers`/`drawer_report`/`space_routes` handlers confirm correct mm geometry, watertight flexure meshes, correct `launch_slicer(Path, list[Path])` call shape, and correct `trim_size` round-trip through create/inspect/update. No tests were written or run; the HTTP server was never started.

## Fix 005 — Space Type Card Images
- **Status:** Blocked by Fix 004 completion
- **Fix file:** `/fixes/fix-005.md`
- **Planning thread:** `Space Card Images Plan #5`
- **Planned implementation thread:** `Space Card Images Imp #5`
- **Implementation model:** Low / Low
- **Notes:** Drawer, B4B, and Vanity rendered assets were committed to `/images` in commit `371366190b8a959e49bda8a9c419659d14533276`. Current main contains the required `.type-card` Create New Space screen structure, so this fix is limited to wiring those assets into the existing cards plus responsive card styling; it must not alter Fix 004 Space logic.

## Fix 006 — Portable Space Identity
- **Status:** Initial design
- **Fix file:** `/fixes/fix-006.md`
- **Planning thread:** `Portable Space Identity Plan #6`
- **Planned implementation thread:** `Portable Space Identity Imp #6`
- **Implementation branch:** `fix6`
- **Notes:** Fully specified, but implementation is blocked until Fix 004 is complete on `origin/main`. Fix 006 is the first fix using the per-fix branch workflow: after Fix 004 is accepted on `main`, create `fix6` from that current `origin/main` and perform all implementation/correction work there until outside review approves merge. Adds stable Space IDs, a per-user Space registry, rename recovery, and a folder-name-independent inventory filename.
