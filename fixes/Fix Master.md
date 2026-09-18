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
- **Status:** Correction 9 implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Correction 9 was a narrow frontend flow fix in `web/spaces.js` only; the Render/module-route repair and current spacer implementation were untouched. `SP.collisionOrigin` ("create" | "untyped") is now set at all three places that show `#space-collision-prompt` (`SP.create()`, `SP.startUntyped()`, the guarded hosted branch of `SP.useUntypedFolder()`) and cleared on resolution and inside `SP.clearSetupContext()`. "Choose another folder" now routes on that origin - `SP.startUntyped()` for an untyped collision (reopening the folder picker without touching the typed Create form) and `SP.create()` only for a typed-Create collision (preserving the already-entered form). `SP.afterPick()` itself now inspects a folder first (local `/api/space/inspect`, hosted `SP.inspectHosted()`) and routes into `SP.enterSetupFor()` before ever applying/opening it when `needs_setup` is true, so every caller - Recents, Open Existing, collision "Open this Space", Choose Folder - gets the same protection; previously only callers that inspected before calling `SP.afterPick()` were protected, so clicking a recent v2/v3/legacy (including legacy Box) folder could open it directly and bypass the required explicit migration pass.
  Verified statically only (no tests written or run, server never started): `import wavefinity_web` succeeds with `drawer_routes`/`generate_connectors`/`print_spacers_and_connectors` still at module scope; the Correction 8 startup block remains the last thing in `web/spaces.js`; every `SP.*` reference resolves; and the Correction 5/6 spacer/Render regression suite still passes unchanged.
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
