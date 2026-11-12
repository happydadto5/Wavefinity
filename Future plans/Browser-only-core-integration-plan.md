# Wavefinity — complete browser-only core conversion

**DOMAIN OWNERSHIP/DNS LOCK (owner decision, 2026-11-12):** The domain `wavefinity.org` **stays registered, paid and renewed at Porkbun**. Keep **Porkbun authoritative DNS/nameservers**, too. No registration transfer, registrar change, Cloudflare nameserver switch, additional domain purchase or domain renewal payment. **Render Static Site is the selected hosting path**, with a new static site under the existing Render account. At final cutover only, request Andrew's permission to adjust the necessary existing DNS **records within Porkbun** (for example the `www` CNAME) and move the custom-domain association between Render services; the already-configured apex A `216.24.57.1` should remain if Render continues specifying it. These are routing changes, not registrar/DNS hosting transfers. A fallback host requiring moving nameservers is **out of scope and not to be proposed** without Andrew specifically reversing this rule. Document the actual record edits in private Help-Code, not public registration/account details.


**Status: implementation plan only; no coder Stories submitted yet.**
**Owner direction, November 12, 2026:** Keep the Wavefinity interface and Print workflow, host at wavefinity.org without server geometry processing, require no installed Wavefinity software, finish all Gridfinity work first, and create implementation-ready Stories only after the owner's explicit "go".

**Development policy: WAVEFINITY IS USER-TESTED. CODERS DO NOT TEST.** Coders reason through logic, read source and callers, inspect their changes, and implement. They do not write, modify, repair or run automated tests; they do not manually operate the app; and they do not create user test plans, checklists or QA instructions. The owner tests the actual application when they decide. Code-level input validation, error handling, geometry invariants, integrity checks and other real production protections remain required.

**Implementation authority:** [Browser-only-core-detailed-build-contracts.md](Browser-only-core-detailed-build-contracts.md) contains the B00–B16 packages. The [diff-level implementation map](Browser-only-core-diff-map.md) gives source-function anchors, pseudo-diffs, static output layout and exact host cutover. The [source-route index](Browser-only-core-source-route-index.md) lists 91 currently registered routes/major callers. **Token-efficient coder reading:** only assigned Bxx, matching diff-map entry and relevant route rows/current source—not every plan, past debate or full README. This overview does not supersede the detailed contract. The old Render/Python method is preserved in [docs/legacy-python-server-hosting.md](../docs/legacy-python-server-hosting.md) without exposing any private Porkbun credentials.

## Destination architecture

- Render/Python HTTP processing is retired after the final static deployment. The existing canonical Python geometry is bundled into the browser via pinned Pyodide, WebAssembly and the proven custom Manifold MeshGL64 bridge. User PC CPU performs all geometry and file preparation.
- Existing Wavefinity UI, models and controls remain authoritative; no second application, no watered-down geometry, no float32 fallback and no loss of Gridfinity/Wavefinity, Storage Boxes/Drawers, Surface, Pegboard, inserts, lids, stacks, text or photo nesting.
- Browser-side calls replace the existing `/api/*` responsibilities via the central adapter. Retain route response semantics, per-Space state ownership, preview cancellation, autosave, inventory and design source metadata.
- Reuse `web/browser-files.js`, IndexedDB directory handle persistence and local writable folder semantics already in the app. Generated files use local Blobs and the folder picker/download mechanism rather than server export URLs.
- Preserve genuine 3MF packaging (parts, arrangement, labels, material/filament metadata) and STL generation. Produce the actual printer-ready outputs in browser memory.
- **Print remains separate from Export.** Every Print button prepares selected parts, validates printer/Space rules, generates or reuses slicer-ready 3MF, saves/downloads it, and gives a clear "Open in Bambu Studio" handoff. Preserve truthful inventory state. Browser security prevents automatic execution of an arbitrary Windows slicer .exe; do not silently delete Print or pretend that saving a file proves the slicer opened.
- Optional AI that requires a provider may be disclosed as separate; never put private service API keys into the static site or require cloud geometry processing.
- Keep `wavefinity.org` registered at Porkbun. **Default final host is a NEW Render Static Site (free tier within allowances), not the old Render Free Python Web Service.** It uses a CDN, no server-side geometry and no sleeping web-service ~60-second cold start. Browser Pyodide/WASM first-load initialization may still take time. The current Render Web Service cannot be converted in place. Add apex and www to the new Static Site at the authorized cutover; current apex A `216.24.57.1` may remain if Render still requires it, and www CNAME must change to the new Static Site's REAL hostname. Preserve existing TLS and redirect. Cloudflare Pages is not an approved fallback because its root-domain configuration would move DNS nameservers away from Porkbun; if Render's static tier becomes unsuitable, stop and ask Andrew for an alternative that keeps registrar and DNS management at Porkbun. **Tell Andrew the exact steps/price and request explicit permission before changing DNS, detaching old Render domains or retiring the old service.** Retain old hosting docs and source for recovery.

## Implementation policy: one final migration, no halfway functionality

The owner accepts that the full application may be broken between coding packages. Do not add server/browser compatibility toggles, hybrid production fallbacks, partial-operation workarounds or temporary hosting solely to preserve a working interim app. Build the complete local execution path, commit safely to `main` without branches/worktrees/force pushes, and deploy the finished static site in one cutover.

**There are no coder testing phases, no suite requirements, no generated fixtures, no browser-driving instructions, no test automation, no developer-run manual tests and no user test scripts or checklists.** Coders validate the **logic** in the implementation through code reading and review, not by running the application. Preserve real runtime safety checks.

**Gridfinity preservation, beyond generic 21/42:** The migration preserves grid on designs, immutable Space grid, nominal grid footprint versus printed physical cavity, built-in Floor versus None/third-party baseplate, provisional 0.35-mm-per-side external plate allowance, seated lift measured/unverified, 7-mm Z units on both pitches, grid lids/rims and stacking, explicit cross-grid mismatch messages and pitch/nominal-unit file naming. Preserve Stage 2 only if merged by the user's go-ahead; see the detailed diff-map invariant table. The browser PoC proves ordinary bins, NOT all future structural/3MF geometry.

**Supported browser policy:** Windows Chrome/Edge are the complete Space/folder target; B13 owns an honest notice for browsers without File System Access directory handles. Blob downloads alone do not mean Firefox/Safari can save/reopen Spaces.

**Open AI Help decision:** Local prompt generation/AI validation and paste/copy interaction stay. If safe browser-native direct provider chat cannot be delivered without exposing secrets, get Andrew's decision before B13 Story creation; do not silently downgrade AI Help or defer to the final hosting cutover.

**No coder runtime certification:** Coders inspect actual route implementations/source and static build composition; the owner uses the app to assess operation. Do not require blocked-network exercises, scanners, test suites or user QA plans. The B02 production build records real asset sizes; 64 MiB first-load and 1536 MiB combined WASM heap are planning targets, not claims about the unbuilt full app.

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
15. **B14:** Build `dist/` from production-only `web/*`, copy `images/*` and BOTH `Brochure.md`/`brochure.md`, and explicitly **EXCLUDE** prototype page/JS/worker and `web/browser-local-poc/**`. Assemble the final route registry once. Specify Render Static headers/MIME/cache and **notify Andrew for authorization** before hosting/DNS changes.
16. **B15:** Retire the live Python HTTP service only AFTER the actual last deployed server SHA, final static SHA, cutover date/hostname and private DNS rollback record have been filled in, with Andrew's permission.
17. **B16:** Delete temporary experiment page and superseded experiment/test scaffolding; keep the production MeshGL64 assets and license.

**One authoritative dependency graph (exact direct edges are in detailed contracts):** B00→B01→B02→B03→B04→B05→B06→B07→B08. B09 requires B04; B10 requires B06+B09+B08; B11 requires B08+B10; B12 requires B05+B11; **B13 requires B08+B09+B12**, preventing simultaneous edits to `web/app/15-generate-dialogs.js` and `web/spaces/12-space-info.js`. B14 starts only after B00–B13 and is the sole final dispatcher integration owner; B15 requires approved hosting and completed rollback record; B16 follows B15. A shared service does not mean double route ownership. The 92-entry route index has ONE Bxx owner per route.

## Coder completion handoff

The coder reports only: the behavior implemented, files modified, important code decisions, identified limitations and pushed commit SHA. The coordinator alone notifies Andrew when the full build is ready for the free/static hosting action and domain move. **No "Tests run", "Testing needed", "How to test", "QA checklist", or owner testing instructions.** A code change is treated as logically implemented and handed back for natural owner use, without claiming it has been empirically proven to work.

Historical context: Story #2979's initial feasibility runner required float64; direct implementation at `f25fee144d556a819a80eec6a89313603ce0460b` supplied custom MeshGL64 WASM and successfully generated ordinary bin STLs. The owner previously confirmed its browser result in Windows Chrome/Edge. That proof of concept is an implementation reference, **not a requirement to add tests**. Earlier nine failing web tests were removed in `acc74c1af7c34defe4865a842e62c5987076d609` and are not to be rebuilt.

**No Stories are to be filed until the owner finishes Gridfinity and says "go".**
