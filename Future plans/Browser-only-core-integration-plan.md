# Wavefinity — complete browser-only core conversion

**Status: implementation plan only; no coder Stories submitted yet.**
**Owner direction, November 12, 2026:** Keep the Wavefinity interface and Print workflow, host at wavefinity.org without server geometry processing, require no installed Wavefinity software, finish all Gridfinity work first, and create implementation-ready Stories only after the owner's explicit "go".

**Development policy: WAVEFINITY IS USER-TESTED. CODERS DO NOT TEST.** Coders reason through logic, read source and callers, inspect their changes, and implement. They do not write, modify, repair or run automated tests; they do not manually operate the app; and they do not create user test plans, checklists or QA instructions. The owner tests the actual application when they decide. Code-level input validation, error handling, geometry invariants, integrity checks and other real production protections remain required.

**Implementation authority:** [Browser-only-core-detailed-build-contracts.md](Browser-only-core-detailed-build-contracts.md) contains the exact B00–B16 work packages, source files, created production modules, route ownership, change instructions and dependencies. This overview does not supersede it. The old Render/Python method is preserved in [docs/legacy-python-server-hosting.md](../docs/legacy-python-server-hosting.md) without exposing any private Porkbun credentials.

## Destination architecture

- Render/Python HTTP processing is retired after the final static deployment. The existing canonical Python geometry is bundled into the browser via pinned Pyodide, WebAssembly and the proven custom Manifold MeshGL64 bridge. User PC CPU performs all geometry and file preparation.
- Existing Wavefinity UI, models and controls remain authoritative; no second application, no watered-down geometry, no float32 fallback and no loss of Gridfinity/Wavefinity, Storage Boxes/Drawers, Surface, Pegboard, inserts, lids, stacks, text or photo nesting.
- Browser-side calls replace the existing `/api/*` responsibilities via the central adapter. Retain route response semantics, per-Space state ownership, preview cancellation, autosave, inventory and design source metadata.
- Reuse `web/browser-files.js`, IndexedDB directory handle persistence and local writable folder semantics already in the app. Generated files use local Blobs and the folder picker/download mechanism rather than server export URLs.
- Preserve genuine 3MF packaging (parts, arrangement, labels, material/filament metadata) and STL generation. Produce the actual printer-ready outputs in browser memory.
- **Print remains separate from Export.** Every Print button prepares selected parts, validates printer/Space rules, generates or reuses slicer-ready 3MF, saves/downloads it, and gives a clear "Open in Bambu Studio" handoff. Preserve truthful inventory state. Browser security prevents automatic execution of an arbitrary Windows slicer .exe; do not silently delete Print or pretend that saving a file proves the slicer opened.
- Optional AI that requires a provider may be disclosed as separate; never put private service API keys into the static site or require cloud geometry processing.
- Keep `wavefinity.org` on Porkbun and point DNS to a free/near-free static host only after the full implementation is complete. Retain the old server deployment documentation and Git source history for recovery.

## Implementation policy: one final migration, no halfway functionality

The owner accepts that the full application may be broken between coding packages. Do not add server/browser compatibility toggles, hybrid production fallbacks, partial-operation workarounds or temporary hosting solely to preserve a working interim app. Build the complete local execution path, commit safely to `main` without branches/worktrees/force pushes, and deploy the finished static site in one cutover.

**There are no coder testing phases, no suite requirements, no generated fixtures, no browser-driving instructions, no test automation, no developer-run manual tests and no user test scripts or checklists.** Coders validate the **logic** in the implementation through code reading and review, not by running the application. Preserve real runtime safety checks.

## Exact work order

The detailed specification defines 17 work packages with concrete files and patches:

1. **B00:** Preserve and document old Python/Render server architecture and recovery procedure.
2. **B01:** Read every current route/caller and document exact response and state-side-effect mapping; architecture only, no test scanners.
3. **B02:** Package canonical Python engine, pinned Pyodide and MeshGL64 as production static assets.
4. **B03:** Implement browser worker, message protocol, central local API adapter and Blob transfer.
5. **B04:** Port catalog, validation, fit, part/feature edit and layout rules.
6. **B05:** Integrate local geometry preview into the existing main UI.
7. **B06:** Implement ordinary bin and connector building, STL, file output handling.
8. **B07:** Implement real 3MF ZIP/model metadata packaging, part/group/filament layout and output safety handling.
9. **B08:** Keep every Print action and printer workflow. Generate print-ready 3MF and provide browser-legal slicer handoff.
10. **B09:** Move preference, Space, resume, folder, file and autosave operations to browser storage.
11. **B10:** Move inventory, bin source, drawer layout, spacers and file ownership to browser processing.
12. **B11:** Complete structural Space calculations for Storage Box, Storage Drawers, Drawer, Surface and Pegboard.
13. **B12:** Complete advanced features (text, dividers, bores, photo nest, openings, lids, etc.).
14. **B13:** Replace browser-incompatible desktop/AI-specific operations honestly, without breaking core Print.
15. **B14:** Build the full static site, configure the static host and prepare the one-time cutover after code completion.
16. **B15:** Retire the live Python HTTP service while retaining written legacy recovery and old source history.
17. **B16:** Delete temporary experiment page and superseded experiment/test scaffolding; keep the production MeshGL64 assets and license.

**Dependencies:** B00→B01→B02→B03→B04→B05→B06→B07→B08. B09 needs B03–B05, B10 needs B06+B09, B11 needs B07–B10, B12 needs B05+B07+B11, B13 needs B03+B09. B14 starts after all core code B00–B13 exists; B15→B16 follow. The independent packages may be organized for safe parallel coding if their files do not collide.

## Coder completion handoff

The coder reports only: the behavior implemented, files modified, important code decisions, identified limitations and pushed commit SHA. **No "Tests run", "Testing needed", "How to test", "QA checklist", or owner testing instructions.** A code change is treated as logically implemented and handed back for natural owner use, without claiming it has been empirically proven to work.

Historical context: Story #2979's initial feasibility runner required float64; direct implementation at `f25fee144d556a819a80eec6a89313603ce0460b` supplied custom MeshGL64 WASM and successfully generated ordinary bin STLs. The owner previously confirmed its browser result in Windows Chrome/Edge. That proof of concept is an implementation reference, **not a requirement to add tests**. Earlier nine failing web tests were removed in `acc74c1af7c34defe4865a842e62c5987076d609` and are not to be rebuilt.

**No Stories are to be filed until the owner finishes Gridfinity and says "go".**
