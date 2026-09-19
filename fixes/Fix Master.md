# Wavefinity Fix Master

Permanent Help Code ledger. After a fix receives **YES — DONE** and is integrated into `main`, rename its individual file to `fix-### archive.md`; never delete the completed fix record. Entries here remain permanently.

This ledger was introduced after some earlier fixes already existed. The entries below reconstruct the currently visible/known fixes without inventing unavailable history.

## Fix 002 — Edge Trim Print-Bed Splitting
- **Status:** YES — DONE; integrated into `main` and archived
- **Archive file:** `/fixes/fix-002 archive.md`
- **Notes:** The earlier Correction 1 status was stale. Final outside review of current `main` confirmed the two documented material issues are resolved: perimeter pieces use exact side-run `clip_regions` rather than one rectangular approximation, and the minimum-piece search allows independently varying/unequal arc lengths while trying piece counts from smallest upward. The 10 mm-per-edge effective-bed rule and final actual-mesh fit check remain in place. No known Fix 002 issue remains.

## Fix 003 — Base Trim Drop-In Joint and Size Presets
- **Status:** YES — DONE; integrated into `main` and archived
- **Archive file:** `/fixes/fix-003 archive.md`
- **Implementation thread:** `Base Trim Joint Imp #3`
- **Notes:** Final outside review of current `main` confirmed the requested Base Trim behavior is present: named square size presets with Medium 7.5 × 7.5 mm default, single drop-in dovetail joint with 0.20 mm clearance and legacy join normalization, and the hidden local Ctrl+Shift Print path producing the two-piece physical-fit sample through production geometry. No known Fix 003 issue remains.

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
- **Status:** YES — DONE; merged into `main` and archived
- **Archive file:** `/fixes/fix-007 archive.md`
- **Planning thread:** `Adaptive Edge Connectors Plan #7`
- **Implementation thread:** `Adaptive Edge Connectors Imp #7`
- **Implementation branch:** `fix7`
- **Accepted branch head:** `52e9a6d2662fd8f4687c7b372249170547149feb`
- **Implementation commit:** `212da3340429eb0f84db40600efebec1ba873e16`
- **Correction 1 implementation commit:** `6be2ff75b761e2f299240174e57668b3c143cf9b`
- **Main integration commit:** `01dfdc0a07a7f6aab494d5196dfeb72a151f8d5e`
- **Testing class:** Class B — limited targeted connector/geometry checks completed
- **Notes:** Outside review accepted Fix 007 after Correction 1. The implementation adds Side / 3-Way Corner / 4-Way Corner connector selection, equal-height/same-wall corner connectors using the existing lock lattice and 16 mm minimum joinable size, automatic connector fit from the active wall thickness, quantity 1–20 for corner parts, and a non-blocking mixed-wall warning only after an explicit Wall change in a typed Space. Correction 1 cleared stale warning state whenever the debounced design update is cancelled and made `installed_corner_boxes()` reject invalid way counts. The branch was merged forward to current `main` before final review.
## Fix 008 — First Run Drawer
- **Status:** YES — DONE; accepted by user, merged into `main`, and archived
- **Archive file:** `/fixes/fix-008 archive.md`
- **Planning thread:** `First Run Drawer Plan #8`
- **Implementation thread:** `First Run Drawer Imp #8`
- **Implementation branch:** `fix8`
- **Merge PR:** #4
- **Main integration commit:** `c705f60f7595cfe05f3deba4cc1df5b4671f9e56`
- **Testing class:** Class B targeted UI/interaction verification was not completed live by the coding agent; user explicitly accepted closure with no known implementation issue
- **Notes:** Outside code review found no known implementation defect. The coding agent could not perform live browser verification and initially substituted code-reading checks. After that limitation was made explicit, the user chose to accept and close Fix 008 rather than keep it open solely for live verification. The accepted implementation includes clearer first-run Drawer copy, visible Bin Name/Height cues, actionable empty Drawer/Inventory states, empty-state action gating, and typed single-drawer canonical name/size synchronization. No special post-create tutorial card was added and advanced Bin options remain visible per user decision.


## Fix 009 — First Run Reliability
- **Status:** Completed / merged to `main`
- **Planning thread:** `First Run Reliability Plan #9`
- **Implementation thread:** `First Run Reliability Imp #9`
- **Implementation branch:** `claude/fix9-implement-uertxg`
- **Merge:** PR #5, merge commit `dac06dafe94613047611191ba125009ccd5700de`
- **Testing class:** Class B — focused regression coverage / targeted existing tests
- **Review verdict:** YES — DONE
- **Notes:** Completed first-run/hosted reliability work. Final implementation separates committed Space authority from safe setup prefill data, preserves unrestricted “just get started” Design mode, starts onboarding before initial preview generation, adds the immediate startup cover, securely serves the three Space-card images from `/images/`, removes the fake “Browser downloads” folder path, preserves deliberate generated-file downloads, and makes hosted persistence capability/permission-driven across macOS, Linux, Android, and iOS/iPadOS. Targeted Space identity, static image/traversal, pseudo-folder regression, and JS syntax checks were added/run by the implementation agent and reviewed in code before merge. Individual Fix 009 file removed after completion; permanent history retained here.

## Fix 010 — New Space Flow
- **Status:** NO — NOT FULLY DONE; Correction 1 issued because no remote `fix10` implementation branch/outbrief exists
- **Planning thread:** `(10) New Space Flow`
- **Implementation thread:** `New Space Flow Imp #10`
- **Implementation branch:** `fix10`
- **Testing class:** Moderate UI/Space-routing change — focused web regression coverage plus full test script required
- **Notes:** Compact the normal Interior Parts / Parts & options choice cards from 48 px to 34 px without shrinking the 34 × 34 SVG artwork, and tighten the feature-icon viewBox so the actual glyph is larger. Rename the Drawer-specific “New Drawer Space” action to “New Space” and route it through the existing three-image Drawer / Surface / Portable Storage chooser. Same-type repeat creation carries the current Space dimensions/trim with a blank new name; cross-type creation does not inherit dimensions. Preserve the existing folder-last create/collision/persistence path.


## Fix 011 — Connector Auto-Generation
- **Status:** Planned — implement after Fix 010 is merged
- **Planning thread:** `Connector Auto-Generation Plan #11`
- **Implementation thread:** `Connector Auto-Generation Imp #11`
- **Implementation branch:** `fix11`
- **Testing class:** Moderate UI/backend generation change — targeted connector/web coverage plus full test suite required
- **Notes:** Remove the false Side-connectors-vs-Base-Trim chooser and the Side/3-Way/4-Way connector-type chooser. Same-height connector generation automatically creates one Side, one 3-Way Corner, and one 4-Way Corner file; different-height generation creates Side only. Existing physical corner eligibility remains, but an ineligible corner must not prevent a valid Side connector from being generated. Hosted folder generation and local Bambu Studio printing must use the same automatic bundle. Fix 011 overlaps Fix 010 in `web/index.html`, `web/app.js`, and `test_wavefinity_web.py`, so implementation starts only after Fix 010 is integrated into current `main`.
