# Browser migration review confirmation

- **Reviewed by:** Codex
- **Date:** 2026-09-04
- **Browser-only cleanup commit:** `b3f2f87`
- **Scope:** Independent verification of `BROWSER_MIGRATION_REVIEW_REPLY.md`,
  followed by the requested browser-only cleanup.

## Independently confirmed

- The two “please confirm” defects were real in the reviewed implementation:
  automatic feature options could be persisted when a support was placed, and
  the fused/removable geometry tint was not consistently represented in the
  browser renderer. Both were already corrected in commit `b41555d`; the
  existing regression tests still pass.
- The default-post/cartridge report was reproducible in the original branch.
  The engine-side adaptation is present and the untouched starter design now
  produces a valid one-cell cartridge post.
- The mutation-order warning was a real browser bug, not merely a theoretical
  invariant. A delayed local server reproduced an add-support followed quickly
  by mode-switch leaving the radio in removable mode while the summary still
  said fused. Mutation locking, stale-preview invalidation, and rollback of a
  rejected drag are now in `web/app.js`.
- In Microsoft Edge, the live app connected, exposed all seven support choices,
  placed a pocket, switched through removable and cartridge modes, and updated
  the 2D layout from a real pointer drag. Numeric Center X/Y/Width/Depth fields
  are keyboard-editable and their validation feedback is exposed in the
  accessibility tree. The tab controls expose selected state and keyboard
  navigation semantics.
- The pre-existing post/cartridge failure was confirmed as an engine behavior
  in the untouched starter design before the adaptation; it is now covered by
  the existing regression and no longer blocks that first click.

## What was fixed in this pass

- Removed `Launch_Organizer_Desktop.bat` and the Tkinter widget UI from
  `organizer_app.py`; `Launch_Organizer_UI.bat` is now the sole UI launcher and
  always starts the browser application.
- Removed stale desktop-launch documentation and updated the architecture and
  code-layout descriptions.
- Added concise in-app and README descriptions of fused, removable, and 8 mm
  cartridge inserts.
- Added accessible canvas roles/descriptions, explicit keyboard equivalents,
  and roving keyboard behavior for the 3D/2D tabs.
- Added static browser-contract assertions for the browser-only sections and
  mutation guard.

## Qualifications and disagreements

- Claude’s security conclusion is supported: same-origin, JSON-only POSTs and
  the loopback binding protect the file-writing routes for the stated local
  threat model. No additional security fix was warranted from that review.
- The mutation concern was understated as “worth a look”: the delayed-server
  reproduction demonstrated visible stale state, so it warranted a fix.
- The former fallback recommendation is no longer applicable because the
  product owner explicitly requested browser-only operation. Historical review
  records remain in the changelog/testing log, but no desktop launcher or UI is
  shipped.

## Still genuinely open

- The app has no checked-in Playwright/WebDriver suite; Edge verification above
  is a live smoke test. Pointer move was exercised directly; exhaustive automated
  sweeps of every boundary, keep-out, and resize-handle combination remain a
  future QA task.
- Save/open download-event capture and very dense preview payload performance
  remain browser-platform limitations noted in the migration review.
- The Python engine and CLI remain intentionally available as non-UI tooling;
  they are not alternate graphical interfaces.
