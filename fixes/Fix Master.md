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
- **Status:** Correction 8 implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Correction 8 was a narrow cleanup pass; the Render/module-route repair and current spacer implementation were untouched. Moved the `startSpaces()`/`if (state.ready)` startup block to the very end of `web/spaces.js`, after every `SP.*` helper it depends on - previously it sat right before `SP.wire`'s own definition, so a `state.ready===true` load would call `SP.wire()` before that assignment ever ran. Local `use_folder()` (backing `/api/space/use-untyped`) now refuses *every* `mode==="space"` folder, not only ones that are already fully set up, and `SP.startUntyped()` now inspects first in both modes and routes a folder already classified as a Space into the existing collision prompt instead of calling Use-Untyped on it. Local `describe()`'s `exists` flag now also checks for current/legacy metadata files, not just the inventory file, so a metadata-only folder no longer skips the Configure-vs-Choose-Another confirmation - matching hosted's existing behavior. `normalise_space_definition()` now normalizes legacy `kind="box"` to `"portable"` at the point of persistence (so no write path can persist a new `box`, regardless of which caller passes `allow_legacy=True`), and a stored Space still carrying `kind="box"` is now always classified as needing the explicit migration/setup pass even inside an otherwise fully-valid v4/`setup_version`-1 metadata file left over from an earlier incomplete build - fixed consistently in local `_folder_state()`, hosted `SP.classifyMetadata()`, and a final catch-all in `SP.inspectHosted()`.
  Verified statically only (no tests written or run, server never started): `import wavefinity_web` succeeds with `drawer_routes`/`generate_connectors`/`print_spacers_and_connectors` still at module scope; every `SP.*` reference resolves; direct functional tests confirm `/api/space/use-untyped` refuses a `needs_setup=true` typed Space, `describe()` reports `exists=true` for a metadata-only folder, `normalise_space_definition` normalizes `box`→`portable` and refuses `box` without `allow_legacy`, and a v4/`setup_version`-1 folder with a stored `kind="box"` is still classified `needs_setup=true`; and the Correction 5/6 spacer/Render regression suite still passes unchanged.
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

## Fix 007 — Adaptive Edge Connectors
- **Status:** Requirements questions
- **Planning thread:** `Adaptive Edge Connectors Plan #7`
- **Planned implementation thread:** `Adaptive Edge Connectors Imp #7`
- **Notes:** Requirements gathering for expanded connector behavior: add three-way and four-way corner connectors, keep those corner connector types incompatible with variable height, ensure ordinary connectors derive fit from active bin wall thickness, and warn when a Space contains mixed wall thicknesses because connectors between different thicknesses are not supported. The current README already states that custom-wall connectors are generated for the selected wall thickness and are only for same-thickness bins; implementation details and warning behavior remain to be specified.
