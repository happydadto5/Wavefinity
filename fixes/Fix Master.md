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
- **Status:** Needs remediation work — Correction 5
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Gemini pushed commit `5ce745b` and reported completion, but Render still fails at startup because `organizer_drawer.py` does not export module-level `drawer_routes`. Static review also found a stale `create_space_text` import, literal JavaScript `\\n` artifacts, Space API route mismatches, Drawer spacer DOM/function mismatches, invalid `save_inventory(..., bins=...)` usage, and Shapely/trimesh union misuse. Correction 5 consolidates the required repair for a fresh coding agent.

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
