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
- **Status:** Closed by user
- **Archive file:** `/fixes/fix-004 archive.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Final implementation commit:** `be5ed7e30f58c8aecc99c328d16512a756a1ecef`
- **Notes:** Fix 004 was closed by the user after Correction 12 implementation. The final Correction 12 code included the three-pass closure-audit repairs across Drawer panel wiring, shared product-rule usage, fresh typed-Space sizing, ordinary-bin default sanitation, deterministic Surface/Portable transitions, and current documentation/copy. The targeted testing pass introduced by the updated Help Code policy was not completed before the user's explicit closure decision. The active fix file was renamed to `/fixes/fix-004 archive.md` instead of being deleted so the full correction history remains available.
## Fix 005 — Space Type Card Images
- **Status:** Completed — accepted by outside ChatGPT review
- **Planning thread:** `Space Card Images Plan #5`
- **Implementation thread:** `Space Card Images Imp #5`
- **Final implementation commit:** `32b0e3958cd2cc9e2cb6f37aa9cc8cb83bab9ebb`
- **Notes:** Final review confirmed Drawer/Surface/Portable Storage use the approved `/images/Drawer.png`, `/images/Vanity.png`, and `/images/B4B.png` assets, preserve the existing visible text and full-card button interaction, use decorative empty alt text, and add consistent responsive 4:3 card styling without changing Space logic. The individual `/fixes/fix-005.md` file was deleted after acceptance per Help Code protocol. No tests were run by ChatGPT during outside review.

## Fix 006 — Portable Space Identity
- **Status:** YES — DONE; merged into `main` and archived
- **Archive file:** `/fixes/fix-006 archive.md`
- **Planning thread:** `Portable Space Identity Plan #6`
- **Implementation thread:** `Portable Space Identity Imp #6`
- **Implementation branch:** `fix6`
- **Accepted branch head:** `00b3588e80b2e2589925bd2c6278a84d037e008d`
- **Correction 1 implementation commit:** `a9ccd74f0da2b7f8ab2381e973b61c564fcaded1`
- **Correction 2 implementation commit:** `502f7ea7a87be002a74c2f100e474d67930e8761`
- **Testing class:** Class C risk-directed testing completed
- **Notes:** Outside review accepted the final implementation after two correction passes. The accepted Fix 006 runtime/product changes were integrated onto the then-current `main` while preserving newer Help Code/testing policy and Fix 007/008 planning work. The completed fix specification/outbrief is retained as `fix-006 archive.md`. Hosted File System Access smoke remains the documented environment limitation from implementation review.

## Fix 007 — Adaptive Edge Connectors
- **Status:** Requirements questions
- **Planning thread:** `Adaptive Edge Connectors Plan #7`
- **Planned implementation thread:** `Adaptive Edge Connectors Imp #7`
- **Notes:** Requirements gathering for expanded connector behavior: add three-way and four-way corner connectors, keep those corner connector types incompatible with variable height, ensure ordinary connectors derive fit from active bin wall thickness, and warn when a Space contains mixed wall thicknesses because connectors between different thicknesses are not supported. The current README already states that custom-wall connectors are generated for the selected wall thickness and are only for same-thickness bins; implementation details and warning behavior remain to be specified.

## Fix 008 — First Run Drawer
- **Status:** Planning revised with user decisions; implementation blocked until Fix 006 is accepted and merged to `main`
- **Fix file:** `/fixes/fix-008.md`
- **Planning thread:** `First Run Drawer Plan #8`
- **Planned implementation thread:** `First Run Drawer Imp #8`
- **Planned implementation branch:** `fix8`
- **Testing class:** Class B targeted UI/interaction verification
- **Notes:** Created from a 25-point first-run audit of the Drawer Space workflow. User decisions recorded: no post-create Drawer-ready/tutorial card, and do not collapse Interior print mode/Base/Walls/Lift Grabbers. Scope remains clearer Space/measurement/folder copy, visible print requirement for bin names, missing Height unit, actionable empty Drawer/Inventory states, sensible empty-state action gating, and eliminating separate planner edits of canonical typed Drawer name/size. Connector behavior itself remains Fix 007 territory. Fix 008 must be rebased/re-audited against accepted Fix 006 because Fix 006 changes `web/spaces.js` startup/persistence contracts.

