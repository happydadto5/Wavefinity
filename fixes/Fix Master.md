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
- **Status:** Correction 11A implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Implemented Correction 11A's exact recipe across all 12 listed files. Added `organizer_product_rules.py` as the single shared source for the Drawer hard-wall clearance, the B4B 48 mm/16 mm minimums, and the Small/Medium/Large Surface trim presets, and rewired `organizer_b4b.py`/`organizer_base_trim.py`/`organizer_drawer.py` to import from it instead of duplicating the values. `organizer_inventory.normalise_space_definition()` now enforces real Drawer/Portable/Surface setup minimums (grid capacity after wall clearance, ordinary-bin height floor, B4B field/height floor, whole-unit Surface dimensions, validated `trim_size` with a matching Z) instead of a bare `> 0` check, and `_setup_space_layout()` updates the actual active legacy drawer (falling back to the first existing drawer, never a hard-coded `d1`) instead of always targeting `d1`. `organizer_spaces.py` now treats a Surface missing a validated `trim_size` as recoverable migration input (`needs_setup=True`) the same way it already treated legacy `box`, and its dead duplicate `_folder_state()` fallback block was removed. `wavefinity_web.py`'s catalog now exposes `drawer_rules` (hard-wall clearance + ordinary-bin minimum height) so the frontend never hard-codes them. On the frontend, `web/app.js` gained `drawerSpaceCapacity()`/`ordinaryBinMinimumHeight()`/`loadFreshOrdinaryDesignForCurrentFolder()`, Drawer default sizing now uses the real clearance-aware grid capacity (never overstating capacity at unit boundaries) and clips Z to the Space's actual usable height, and `changeBinType()` now sends a typed Space's seeded Base Trim/B4B design back to a fresh Space-sized ordinary Bin instead of restoring a stale prior design. `web/spaces.js` gained a single shared `SP.readSetupValues()` validator used by both Create and Edit, Surface's Small/Medium/Large choices are now populated live from the authoritative Base Trim catalog (no more hard-coded 6.5/7.5/10 tables anywhere in the file), Surface has a live unit→mm readout, Drawer/untyped Space creation now lands on a fresh ordinary Bin, the existing-inventory "Choose another folder" prompt is now cancel-safe (returns to the populated form before asking for a replacement), Escape on the cross-type warning dialog now resolves as "do not switch" instead of leaving the promise unresolved, and the unused `SP.kind`/`SP.readSize`/`SP.continueSpaceSetup`/`SP.changeFolderThenSetup` helpers and the stale "Space planning is optional" header were removed; legacy `box` now always displays as "Portable Storage". `web/drawer-model.js`'s `DL.spacerPrintGroups()` now derives Printed/Qty-to-print from each placement's `copy` index versus the owning row's `qty` (not a row-Qty-vs-placement-count subtraction), and a new `DL.promoteSpacerCopies()` renumbers only the newly-printed active-drawer copies to the next contiguous printed indices before `DL.printSelectedSpacers()` raises `qty`, so deliberate reprints never inflate the logical quantity. `web/drawer-panel.js`'s Print Spacers button is now hidden/disabled whenever the active drawer holds no spacer placements. `web/index.html` gained the Surface field-size readout markup and an empty `#surface-trim` `<select>` populated by JavaScript. Verified statically only: `py_compile`/module-import checks confirmed no circular imports across the new `organizer_product_rules` module and every importer, direct functional tests exercised every new validation branch (drawer/portable/surface minimums, whole-unit checks, invalid trim rejection) and the active-legacy-drawer selection logic, `node --check` passed on every touched JS file, and a cross-reference script confirmed every `SP.*`/`DL.*`/`DP.*` reference resolves. No tests were written or run, and the server was never started. The Correction 5 Render/module-route repair, the Correction 8 startup-block-at-end-of-file ordering, and the Corrections 9–10 navigation/cancel-safety fixes were all confirmed intact; no Fix 005 card-image markup or assets were touched.
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
