# START HERE — Wavefinity browser-only migration Story creation

**Purpose:** This is the complete handoff for the agent that will create the implementation-ready Poller Stories AFTER Andrew finishes Gridfinity. This is an *execution instruction*, not an architecture brainstorming document.

**The owner's one-line authorization is:** “Read and execute `Future plans/Browser-only-migration-story-creation-handoff.md` exactly as written.”

On receiving that explicit instruction, **create and submit the Stories in Poller in this session**. Do not merely outline them, do not send another plan for approval, and do not ask whether Andrew means to proceed. The invocation is the go-ahead for **Story creation only**, not code implementation or hosting/DNS changes.

**The owner's one-line command authorizes Story submission only, not source implementation or domain changes.** `Browser-only-migration-execution-spec.md` supersedes prior unresolved question language. If source drift creates a genuine impossibility, file other Stories and report that narrowly rather than inventing a workaround or asking about already-settled architecture.

## Mission and boundaries

- App/repo: **Wavefinity**, `happydadto5/Wavefinity`; use its latest GitHub `main`.
- Deliver **all needed, implementation-ready Poller Stories** for one complete migration to browser-only geometry and static hosting.
- **Do not implement application code, change the live website, deploy a host, move DNS, transfer registration, create feature branches/worktrees, or create a separate planning project.**
- Do not file duplicate migration Stories already open/completed. If a package's code is already complete, identify it, skip redundant work, and record the reason.
- Coordinate dependencies and file ownership so future coding agents can work directly on `main` without colliding.
- All proposed Story instructions must comply with Wavefinity's **no-coder-testing** policy.

## Authoritative documents — read in this order

Read files from the latest Wavefinity `main` (not old conversation summaries or cached checkouts):

1. **`Future plans/Browser-only-migration-execution-spec.md` — SINGLE FINAL AUTHORITY: decisions, B00–B16 work order, final route/AI/plate/hosting contract.**
2. **`Future plans/Browser-only-core-detailed-build-contracts.md`** — exact B00–B16 package patches and definitive dependency table.
3. **`Future plans/Browser-only-core-diff-map.md`** — source function anchors, pseudo-diffs, runtime versions and static build/host details.
4. **`Future plans/Browser-only-core-source-route-index.md`** — frozen **92-route source map (91 local, 1 retired)**, single owner/disposition, handlers and prominent UI callers. Reconcile on current source, not a permanent route-count requirement.
5. **`Future plans/Browser-only-core-integration-plan.md`** — historical short overview; defer to execution spec if unclear.
6. **`README.md`** — owner-tested/no-coder-testing rules and canonical geometry behavior.
7. **`docs/legacy-python-server-hosting.md`** — historical server architecture and hard pre-retirement recovery record.

For private DNS details, read `happydadto5/Help-Code/docs/wavefinity-domain.md`. Do not copy private account/DNS details into public Stories beyond the minimal operational instructions needed for a domain handoff. Keep Porkbun as registrar and authoritative DNS.

Read Poller's **current** connected integration/protocol for Story creation and dependency registration. Use the actual Poller tools; do not invent IDs or claim submission without a returned ID. Do not create stories under a different app/repo.

## No extra architecture or discovery projects

The final architecture is **already chosen**. Do not repeat hosting comparisons, alternate kernel evaluations, or broad feasibility research. Use the pinned working 64-bit Manifold WebAssembly/Pyodide browser experiment as the basis, carrying forward the canonical Python engine.

Current-source reconciliation is necessary because Gridfinity work was underway when the plans were written. Limit source reading to the changed packages and routes that actually matter:

- Fetch latest `main`, inspect relevant functions from the diff map and route index, confirm paths/signatures, and note moved/renamed/added Gridfinity code and routes.
- Bring all newly completed Gridfinity behavior into migration scope, preserving 7 mm Wavefinity and 21/42 mm Gridfinity standards as defined by **current source**.
- Derive request/response keys, state transitions, side effects and file ownership from current functions, not guessed examples.
- B00's legacy document already exists: if no additional B00 implementation is needed, do not create a documentation-only duplicate. The exact last live Render Web Service SHA and other recovery fields are purposely pending until real cutover; B15 cannot retire anything until they are populated.
- If there is a material mismatch between plans and source, write the exact correction into the affected Story. Do not ask the coder to investigate it later. **Use the authoritative per-package dependency table at the end of the detailed contracts, not the older prose sequence.** B13 follows B08 and B12 to serialize shared JavaScript file edits; B14 alone assembles the central Python route dispatcher.
- Preserve actual UI/Print/Space behavior rather than reducing the product to a two-bin proof of concept.

## Mandatory final product requirements

**Execution:** Existing Wavefinity UI remains. All core validation, previews, wavy and Gridfinity geometry, connectors, advanced parts, Storage Box, Storage Drawers, Drawer, Surface, Pegboard, inventory, local save/reload/autosave and STL/3MF output run on the visitor's PC. Use canonical Python in browser Pyodide, the existing custom Manifold float64 WASM bridge and browser filesystem APIs. No native Wavefinity installation, local HTTP server, browser extension, cloud geometry API, or silent float32 fallback.

**Print is mandatory:** Keep Print separate from Export. Retain selection, printer fit, autosave, real slicer-ready 3MF and feedback. A browser cannot arbitrarily execute Bambu Studio. After saving/downloading a valid 3MF, present **Open in Bambu Studio** and the explicit action **I opened it in Bambu Studio**. Only on that user confirmation for the same Space/design is the EXISTING Printed state updated; DO NOT add a new persistent Prepared state. No false automatic-launch claim.

**Single cutover:** Andrew explicitly accepts that intermediate implementation stages may be nonfunctional. Do NOT add dual server/browser execution, half-working releases, backend fallbacks or compatibility layers solely to keep each Story operational in isolation. All work converges on one complete static application.

**Hosting:** Final target is NEW Render Static Site, free within allowances, not the sleeping Python Web Service. Build with production-only `web/*` to dist root, root `images/*` into `dist/images/*`, and BOTH `Brochure.md` and `brochure.md` aliases. Exclude PoC HTML/worker/`web/browser-local-poc/**` before B16 removal. Include pinned Pyodide/WASM with correct MIME/cache/CSP, full route declarations and the normal production build integrity check. Preserve legacy hosting record. Do not touch live DNS/Render domains now.

**Porkbun lock:** `wavefinity.org` STAYS registered and paid at Porkbun, and Porkbun remains authoritative DNS/nameservers. No nameserver migration, domain transfer, Cloudflare Pages apex hosting, new domain purchase or new registration payment. Static hosting can be changed by modifying authorized DNS **records within Porkbun** and attaching the domains to the new Render service. Existing exact DNS values belong in private Help-Code, NOT public Bxx Stories. Do not perform these actions now. The future hosting Story MUST include a step **tell Andrew exactly what action/account configuration is needed and obtain his explicit authorization** before creating a paid resource, detaching domains, changing any DNS records, or retiring the existing service. Do not invent a future Render hostname; use the actual dashboard value at cutover.

**User-tested rule — ABSOLUTE:** No coder may write, update, repair or run automated tests, run existing suites, build test fixtures/harnesses, manually operate the app for testing, perform browser/slicer QA, or write manual test plans/checklists/instructions for Andrew. **B16 must REMOVE all inherited test code and infrastructure rather than merely disable it**, while keeping historical evidence in prose. Coders **must inspect and reason through their logic, callers, constraints, data contracts, imports, error handling and final diff**. Keep legitimate *runtime* validation (input, geometry, file integrity, security); it is application code, not a test. Do not reintroduce the nine removed web tests. A reviewer must not expand a Story into a testing assignment.

## Story creation procedure

1. **Inventory existing Poller Wavefinity Stories** and current repository state. Match B00–B16 package scope and identify existing work. Record skipped/completed scope to prevent duplicates.
2. **Resolve current source only where necessary**, starting from exact symbols in the diff map and 92-entry route index. Read `gridfinity-stage1-spec.md` and `Future plans/Gridfinity-implementation-master-plan.md` as source-invariant references, and check what Stage 2 code actually merged (magnet feet, lid variants, container stacking, side openings); do NOT assume merely planned features shipped. Include Space/grid immutability; nominal versus physical cavity; Floor/None and third-party baseplate relief; measured/unverified seated lift; 7-mm Z units; printed floor sockets; grid/lid stacking; cross-grid refusals and filename pitch/unit segments. No route scanner, tests or manual test plan.
3. **Use B00–B16 as the default Story division** and the authoritative dependency table in the detailed contracts. The **normal shipping-build check** compares updated source-route index + B01 manifest with final flat Python/JS runtime registry, failing on missing/duplicate/unclassified routes; historical export-token path is `retired` and NOT a callable handler. Missing route fails closed with `UNSUPPORTED_LOCAL_OPERATION` and never calls a server. This is production compile integrity, NOT coder testing. Single OWNER per route from the 92-row historical index: B10 owns ALL `/api/drawer/*`, B11 owns ALL structural/Storage Drawers and pegboard hooks, B09 owns folder/Space paths including `/api/browse-output-folder`, `/api/space/show-folder` and `/api/space/warm`; B13 owns slicer browse/show-log/AI. B04 creates Python `route_dispatch.py`; B05/B06/B08/B10/B11/B12/B13 Python modules export Python `ROUTES`. B09 and B13's browser-only handlers export JavaScript `ROUTES`. **B14 wires Python maps into Python dispatcher and JavaScript maps into `local-api.js` separately**, never imports JS into Python. No competing writers or dual route owners. Split only for safe truly independent code ownership.
4. **AI Help product choice is ALREADY RESOLVED in the execution spec:** BYOK browser-direct AI chat where user provider CORS allows, session-memory key only by default, ALWAYS retain manual copy/paste. No site key or new Wavefinity server. Never pause Story creation for a repeat A/B vote; if a particular provider blocks browser CORS, the app must report that and retain copy/paste. Preserve all local prompt/candidate/repair flows and disclose prompt/design context sent only after user asks. Include B07 `plate_layout.py` four-member merged 3MF path and B13 pre-Space unsupported-browser recovery in their Stories.
5. **Create the Stories through Poller**, each self-contained and implementation-ready.
6. **Register dependencies** using Poller's supported dependency/ordering mechanism. If Poller cannot represent a dependency, write the exact blocking Story IDs and required deliverables in the relevant Story's contract. Avoid cycles and same-file parallel ownership conflicts.
7. **Align reviewer and coder instructions** with the owner-tested rule and single cutover. Reviewers validate contractual/code reasoning without adding tests or manual QA plans. Preserve direct-`main` no-force-push safety and latest-origin reconciliation.
8. **Finish only when submissions are confirmed**. Report actual Story IDs and links, packages covered, dependency order, completed/skipped packages, known unresolved technical decisions, and confirmation of no tests, Print preserved, Porkbun preserved and no code/hosting/DNS changed.

## Exact minimum contents of EACH Story

Write the following as compact prose with section headings, not repeated generic architecture essays:

- **Identity**: `Bxx` number, precise implementation title, owning Wavefinity repo.
- **Purpose**: present broken/server-dependent behavior and exact final browser behavior.
- **Preconditions**: actual upstream Poller Story ID(s) and the code/contract each must have delivered.
- **Source targets**: exact paths, functions/classes and relevant entry points from current `main`; mention file-level ownership and collisions.
- **Required edits**: direct before → after changes, new production files, removed server assumptions, current import/data dependencies; include small pseudocode when it materially prevents a design decision.
- **Public contract**: request/result shape, local worker messages, error and status handling, file formats/names and state mutations, where applicable.
- **Preserve**: unchanged UI behavior, full geometry, Print and Export semantics, Space identity, permissions, versioning, precision and product constraints.
- **Out of scope**: unrelated code, interim compatibility, testing, hosting/DNS changes before authorization.
- **Code completion definition**: required implementation and actual production files, logical consistency to inspect, real runtime input/mesh/3MF integrity checks, NOT automated tests, browser driving, user QA instructions or any empirical certification claim.
- **Handoff**: exact modified files, important assumptions, unresolved blocker if any, pushed commit SHA.

Favor **short, exact file/function edits** over repeating all architecture text. Cite the existing plan files as the shared authority. Do not give future coders tasks such as “research appropriate solution” when one is already specified here.

**Rendering/browser limits to write into appropriate Stories:** The standard Manifold bridge is single-threaded (no current pthread/SAB and no mandatory COOP/COEP); the static Render Dashboard headers, `application/wasm` MIME and cache rules are in the diff map. PoC routes/assets are EXCLUDED from B14 dist even before B16 source removal. `dist/Brochure.md` and `dist/brochure.md` are both emitted. Default Chrome/Edge Windows folder workflow; B13 shows explicit unsupported-browser notice rather than claiming Firefox/Safari autosave. Photo Nest uses cv2/NumPy/Shapely/Pillow with browser-native package versions; 3MF lib3mf serialization is not observable from Python source. The ordinary-bin PoC does not prove complex 3MF/Gridfinity/Storage Drawers browser behavior. Asset budgets (64 MiB first-load target, 1536 MiB combined linear heap) are planning targets, not measured product guarantees. Coder may logically inspect and report risk but not run tests.

## Dependency order / Story scope

Use the actual B00–B16 dependencies in the detailed contracts, reconciled with current Gridfinity code. The main path is:

- B00 legacy preservation (already documented; only create if genuinely unfinished)
- B01 route/source-contract mapping
- B02 reproducible pinned runtime and canonical bundle
- B03 worker/adapter/binary transfer
- B04 catalog/editor/rules
- B05 previews
- B06 standard bin/connectors/STL
- B07 native 3MF **plus plate_layout.py exact transform/combined-plate four-file ZIP behavior**
- B08 **Print** preparation/handoff
- B09 local Space/preferences/files/autosave (after relevant base runtime)
- B10 inventory/drawer save and print
- B11 all structural Spaces and related exports
- B12 advanced features, image nesting, text
- B13 decided BYOK AI Help (with manual fallback) and browser capability/recovery notices
- B14 static build **and explicit Andrew hosting approval handoff**
- B15 retire Python HTTP execution while preserving historical rollback
- B16 **remove ALL testing infrastructure** including `tests/`, `browser-tests/`, `run_tests.py`, any other test-only harness/CI commands and the prototype, but retain production MeshGL64 and historic prose

Follow the ONE minimal direct dependency table in detailed contracts: B09 after B04 (parallel to B05–B08); B10 after B08+B09; B11 after B10; B12 after B11; B13 after B12 (and therefore after both B08/B09, preventing shared-file collisions); B14 after B13, transitively after all earlier work. B14 alone integrates Python and JavaScript registries. Do NOT add redundant transitive `start_after` edges. Every route has ONE owner. No test Story and no test-related scope. The full application may remain nonfunctional until all code is implemented.

## What to tell Andrew after submission

Give a compact table of **actual** Story IDs, Bxx numbers, titles and dependency order; distinguish already-complete/skipped packages and unresolved blockers. State clearly:

- All implementation-ready Stories are submitted to Poller (or precisely which are blocked).
- No coding was started by this planning agent.
- No hosting/DNS or domain registration changes were made.
- Print remains part of the final application.
- Porkbun registration and DNS remain unchanged.
- No automated tests, coder manual tests or user test plans were introduced.

**Do not ask Andrew to review another high-level plan. Do not begin implementation automatically.**
