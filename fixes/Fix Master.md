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
- **Status:** Correction 12 code implemented; required targeted testing (per the updated Help Code testing policy) not yet performed — needs a follow-up testing pass before outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Claude commit `065d99e` implemented Correction 11A. A three-pass closure audit found remaining integration defects and produced Correction 12. Implemented Correction 12's exact repairs. (A) Removed `DP.wire()`'s dereference of the removed `#dl-output-folder`/`#dl-output-folder-picker` DOM nodes and deleted the now-callerless `DP.changeFolder()`; `DP.renderSave()` no longer touches that markup and now calls `SP.renderSpaceInfo()` to keep Drawer Space Info current. (B) `organizer_base_trim.BASE_TRIM_DEFAULT_WIDTH/HEIGHT` now derive from `organizer_product_rules.SURFACE_TRIM_HEIGHTS["medium"]`; `#base-trim-size` in `web/index.html` is now populated live from the catalog via a new `populateBaseTrimSizeChoices()` (called from `renderCatalog()`), with `baseTrimPresetRows()`/`baseTrimPresetValue()`/`surfaceTrimHeight()` replacing the removed hard-coded `BASE_TRIM_SIZE_PRESETS`/Surface preset table; `b4bMinField()`/`b4bLatchedMinHeight()` replace the removed `B4B_MIN_FIELD`/`B4B_LATCHED_MIN_HEIGHT` constants everywhere they were used; a new `drawerHardClearance()` replaces the hard-coded `0.55` in `web/drawer-panel.js`'s two Drawer-clearance call sites **and** in `web/drawer-model.js`'s `DL.grid()` (found during Pass 2 of the closure gate below; not in the original file list but directly required by that gate's own "no hard-coded Drawer 0.55" check). (C) `applySpaceSizingDefaults()` now sets fresh typed-Space X/Y unconditionally instead of skipping when `state.pinnedZone` is stale; `SP.renderSpaceInfo()`'s Drawer capacity display now uses `SP.drawerCapacity()`. (D) `spaceBinDefaultsFromDesign()` now deletes `design_kind`/`base_trim`/`box.b4b` from the snapshot, and both bin-generation and print call sites now also skip remembering a B4B design as the ordinary-bin default. (E) `SP.designBox` is renamed `SP.designPortable` (zero `designBox` references remain) and both `SP.designSurface`/`SP.designPortable` are now `async`, awaiting `toggleB4B()`/`refreshPreview()` and only calling `activatePreviewView("3d")` after the design is fully replaced; `SP.create()` now awaits both. (F) Updated the `organizer_inventory.py` module docstring, README's Inventory/Spaces section and folder-mode/Edge-Mount copy, and remaining "Space planning"-phrased user-facing strings in `web/index.html`/`web/app.js`/`web/spaces.js` to the current Drawer/Surface/Portable model; removed the now-unused `surface_trim_key_for_height` import from `organizer_spaces.py`. Ran the static three-pass closure gate specified at the end of Correction 12 (requirement trace, integration-contract cross-reference, adversarial state trace) — all clean. Per this session's explicit user instruction, no tests were written or run and the server was not started; this predates and does not satisfy the testing-policy override added to `fix-004.md` in the same window (commit `8c74d31`), which now requires a targeted test/browser-smoke pass before this correction can be accepted.
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
