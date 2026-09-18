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
- **Status:** Correction 7 implemented, ready for outside review
- **Fix file:** `/fixes/fix-004.md`
- **Implementation thread:** `Space Onboarding Redesign Imp #4`
- **Notes:** Correction 7 preserved the Correction 5/6 Render/module-route repair and spacer implementation, then fixed: hosted Create/Configure now reads/writes `SP.inventoryFilenameFor(folder)` against the *selected target* (not whatever was previously active) and activates `state.browserFolder`/the saved handle before applying it; new Create now collision-prompts on any folder already classified as a Space regardless of `needs_setup` (previously a v2/v3/legacy Space with `needs_setup=true` could still fall through to create-collision or silent replacement), and choosing "Open this Space" from that prompt now routes into setup first when it still needs it; selecting an existing untyped Wavefinity inventory folder during Create now shows an explicit "Configure this existing folder as this Space" vs "Choose another folder" prompt (new `space-existing-inventory-prompt` screen) that reuses the already-entered Space values, backed by a new hosted `exists` classification flag mirroring local `describe()`'s; hosted "I don't know what I'm designing yet" now collision-checks and writes real v4/`setup_version` Design metadata for a real directory handle (`SP.startUntyped` now delegates through the same guarded path as `SP.useUntypedFolder`, and both clear `SP.configureData` afterward); hosted Edit now updates the inventory's own `layout.space` (via `/api/space/configure-text`) together with metadata, instead of leaving a stale inventory-embedded Space definition that would win back on reopen; a new `SP.clearSetupContext()`/`SP.beginCreateNew()` clears `configureData`/collision/edit state before every fresh Create-New entry point (Welcome Create, New Drawer Space, the cross-type warning's "Create a New Space"); the cross-type warning dialog no longer carries a permanent `hidden` attribute that prevented `showModal()` from ever actually rendering it; and `organizer_inventory.SPACE_KINDS` no longer includes legacy `box` (only `allow_legacy=True` migration paths accept it now; the genuinely-new-Create paths no longer pass `allow_legacy=True` at all), so no current write path can persist a new `kind="box"` Space, while `SP.enterSetupFor()` now also safely prefills a Surface needing recovery setup.
  Verified statically only (no tests written or run, server never started): `import wavefinity_web` succeeds; every `web/spaces.js` API path (including the dynamic create/configure and create-text/configure-text choices) matches a registered route; every new DOM id referenced by the new prompt screen exists in `web/index.html`; every `SP.*` reference resolves to a real definition; a direct functional test confirms `/api/space/create` now refuses `kind="box"` while `/api/space/configure` still migrates a legacy box folder to `portable`; and the Correction 5/6 spacer/Render regression suite still passes unchanged.
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
