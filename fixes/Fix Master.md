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
- **Status:** Correction 6 implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Correction 6 restored `SP.launch`/`SP.fail` (both called but never defined - a fatal browser error at every Space startup), removed the dead `space-optional` path, and split folder "open" from "use untyped"/"configure" so `/api/folder/use` never again demotes an already-configured typed Space (`/api/space/use-untyped` and `/api/space/configure` now also refuse/migrate correctly instead of sharing `/api/space/create`'s collision-rejecting path; a new `/api/space/configure-text` covers the hosted equivalent). Hosted `SP.inspectHosted` is now read-only (previously wrote metadata/inventory on every mere inspection), accepts v2/v3 migration inputs, and writes `setup_version`. `DL.planSpacers()` now reaches the server with the authoritative inventory instead of an empty bin list. Setup readouts are wired live. `SP.showSetup(kind, prefill, {update})` makes Edit-mode explicit so a stale Edit can no longer make Create/New Drawer Space silently call `SP.updateSpace()`. `wireInfoButtons(prefix)` now wires one prefix at a time instead of double-wiring the normal Space Info buttons.
  The spacer planner was reworked to build genuinely contiguous exposed boundary segments per component/side (previously bridged over notches/L-shapes and could span the entire unfilled grid instead of a compact ~28 mm contact pad), reject a candidate whose path crosses another bin/component, and drop the never-honored `max_length` "Longest piece" control rather than pretend it does anything (implementing safe print-bed splitting is its own unfinished fix - see Fix 002). Spacer filenames now use 2-decimal precision plus a Flexible/Rigid tag so distinct gaps or variants can no longer collide, and inventory X/Y now records the actual printed part size (gap + 0.5 mm preload for a real flexure) rather than the placement's gap envelope. Grouped spacer printing now aggregates and distributes newly-printed copies across every inventory row sharing identical geometry, not just one representative row, and the print flow now shows the returned "set copies to" counts.
  Static review under this correction also found and fixed: `DL.planSpacers()` calling a `DL.signature()` that was never defined (every "Plan / Update Spacers" click threw immediately); `SP.designBox`/`SP.designSurface` bugs already noted under Correction 5 remain fixed; a spacer plan that was never actually invalidated on layout/inventory changes (`DL.clearSpacerPlan()` now runs from `DL.afterChange()` and `DL.editBins()`).
  Verified statically only (no tests written or run, server never started): `import wavefinity_web` succeeds; every `web/spaces.js`/`drawer-model.js`/`drawer-panel.js` API path and every `SP.*`/`DL.*`/`DP.*` reference resolves to a real definition; direct calls into the plan/generate/report/space route handlers confirm correct segment geometry, rejection of paths crossing other bins, non-colliding filenames, and that opening a configured typed Space via `/api/folder/use` no longer demotes it.
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
