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
- **Status:** Completed — accepted by outside ChatGPT review
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Final implementation commit:** `8e7a7281ecc60d963dc54fe6bd38ef280e0c278b`
- **Notes:** Final closure review accepted Fix 004 after Corrections 1–10. The finished work includes the new Create/Open Space onboarding flow, Drawer/Surface/Portable setup and defaults, safe v2/v3/legacy migration, Space Info/New Drawer Space behavior, cross-type warnings, restored Render-safe drawer route infrastructure, strategic/flexible spacer planning/generation/printing, and the final navigation/legacy-drawer cleanup. The individual `/fixes/fix-004.md` file was deleted after acceptance per Help Code protocol. No tests were run by ChatGPT during outside review.
## Fix 005 — Space Type Card Images
- **Status:** Work completed, ready for outside review
- **Fix file:** `/fixes/fix-005.md`
- **Planning thread:** `Space Card Images Plan #5`
- **Implementation thread:** `Space Card Images Imp #5`
- **Implementation model:** Low / Low
- **Notes:** Replaced the emoji `.type-card-ill` illustration in each Create New Space type card (`web/index.html`) with the committed `/images/Drawer.png`, `/images/Vanity.png`, and `/images/B4B.png` assets (Drawer/Surface/Portable Storage respectively), keeping the existing button/text/click-handling untouched. Added `.type-cards`/`.type-card`/`.type-card-image` rules to `web/styles.css` in the existing Welcome screen: spaces section (4:3 image grid on desktop) and extended the existing `@media (max-width: 620px)` welcome/Space block with a stacked single-column card layout. No Space logic, `web/spaces.js` click wiring, or image assets were changed. Verified statically only (no tests written or run, server never started) per the fix's testing rule.

## Fix 006 — Portable Space Identity
- **Status:** Ready to branch/implement
- **Fix file:** `/fixes/fix-006.md`
- **Planning thread:** `Portable Space Identity Plan #6`
- **Planned implementation thread:** `Portable Space Identity Imp #6`
- **Implementation branch:** `fix6`
- **Notes:** Fully specified and now unblocked by Fix 004 completion. Fix 006 is the first fix using the per-fix branch workflow: create `fix6` from the current `origin/main` and perform all implementation/correction work there until outside review approves merge. Adds stable Space IDs, a per-user Space registry, rename recovery, and a folder-name-independent inventory filename.

## Fix 007 — Adaptive Edge Connectors
- **Status:** Requirements questions
- **Planning thread:** `Adaptive Edge Connectors Plan #7`
- **Planned implementation thread:** `Adaptive Edge Connectors Imp #7`
- **Notes:** Requirements gathering for expanded connector behavior: add three-way and four-way corner connectors, keep those corner connector types incompatible with variable height, ensure ordinary connectors derive fit from active bin wall thickness, and warn when a Space contains mixed wall thicknesses because connectors between different thicknesses are not supported. The current README already states that custom-wall connectors are generated for the selected wall thickness and are only for same-thickness bins; implementation details and warning behavior remain to be specified.
