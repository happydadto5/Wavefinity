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
- **Status:** Needs remediation work — Correction 12 three-pass closure audit
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Claude commit `065d99e` implemented Correction 11A, but a deliberate three-pass top-to-bottom closure audit found remaining original-scope integration defects. The Drawer panel still dereferences removed `dl-output-folder` DOM nodes and can fail at initialization; browser code still duplicates authoritative Surface/Base Trim presets, B4B minimums, and Drawer clearance; fresh typed-Space sizing can be defeated by stale `state.pinnedZone`; B4B generation can contaminate the remembered ordinary-bin defaults; seeded Surface/Portable transitions are not fully awaited/refreshed and still use stale `designBox` naming; and README/current copy still documents the old optional Space-planning / drawer-box model. Correction 12 gives exact repairs and a required three-pass closure gate.
## Fix 005 — Space Type Card Images
- **Status:** Completed — accepted by outside ChatGPT review
- **Planning thread:** `Space Card Images Plan #5`
- **Implementation thread:** `Space Card Images Imp #5`
- **Final implementation commit:** `32b0e3958cd2cc9e2cb6f37aa9cc8cb83bab9ebb`
- **Notes:** Final review confirmed Drawer/Surface/Portable Storage use the approved `/images/Drawer.png`, `/images/Vanity.png`, and `/images/B4B.png` assets, preserve the existing visible text and full-card button interaction, use decorative empty alt text, and add consistent responsive 4:3 card styling without changing Space logic. The individual `/fixes/fix-005.md` file was deleted after acceptance per Help Code protocol. No tests were run by ChatGPT during outside review.

## Fix 006 — Portable Space Identity
- **Status:** Blocked until Fix 004 Correction 11 is accepted
- **Fix file:** `/fixes/fix-006.md`
- **Planning thread:** `Portable Space Identity Plan #6`
- **Planned implementation thread:** `Portable Space Identity Imp #6`
- **Implementation branch:** `fix6`
- **Notes:** Final dependency audit completed against Fix 004 Correction 11A (`065d99e`). The Fix 006 plan was tightened for v4->v5 identity migration without re-onboarding, UUID preservation, active-ID startup recovery, duplicate-copy handling, uncapped Space registry vs capped Recents, identity-aware Forget, exact read-only/write inventory filename migration, hosted target-folder preservation, and failure ordering. Implementation remains blocked until Fix 004 receives outside **YES — DONE**; then create a fresh `fix6` branch from accepted `origin/main`.

## Fix 007 — Adaptive Edge Connectors
- **Status:** Requirements questions
- **Planning thread:** `Adaptive Edge Connectors Plan #7`
- **Planned implementation thread:** `Adaptive Edge Connectors Imp #7`
- **Notes:** Requirements gathering for expanded connector behavior: add three-way and four-way corner connectors, keep those corner connector types incompatible with variable height, ensure ordinary connectors derive fit from active bin wall thickness, and warn when a Space contains mixed wall thicknesses because connectors between different thicknesses are not supported. The current README already states that custom-wall connectors are generated for the selected wall thickness and are only for same-thickness bins; implementation details and warning behavior remain to be specified.
