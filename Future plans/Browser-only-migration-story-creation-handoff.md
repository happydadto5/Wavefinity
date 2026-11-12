# START HERE — Wavefinity browser-only migration Story creation

**Purpose:** This is the complete handoff for the agent that will create the implementation-ready Poller Stories AFTER Andrew finishes Gridfinity. This is an *execution instruction*, not an architecture brainstorming document.

**The owner's one-line authorization is:** “Read and execute `Future plans/Browser-only-migration-story-creation-handoff.md` exactly as written.”

On receiving that explicit instruction, **create and submit the Stories in Poller in this session**. Do not merely outline them, do not send another plan for approval, and do not ask whether Andrew means to proceed. The invocation is the go-ahead for **Story creation only**, not code implementation or hosting/DNS changes.

## Mission and boundaries

- App/repo: **Wavefinity**, `happydadto5/Wavefinity`; use its latest GitHub `main`.
- Deliver **all needed, implementation-ready Poller Stories** for one complete migration to browser-only geometry and static hosting.
- **Do not implement application code, change the live website, deploy a host, move DNS, transfer registration, create feature branches/worktrees, or create a separate planning project.**
- Do not file duplicate migration Stories already open/completed. If a package's code is already complete, identify it, skip redundant work, and record the reason.
- Coordinate dependencies and file ownership so future coding agents can work directly on `main` without colliding.
- All proposed Story instructions must comply with Wavefinity's **no-coder-testing** policy.

## Authoritative documents — read in this order

Read files from the latest Wavefinity `main` (not old conversation summaries or cached checkouts):

1. **`Future plans/Browser-only-core-detailed-build-contracts.md`** — complete B00–B16 work packages, invariants and dependency order.
2. **`Future plans/Browser-only-core-diff-map.md`** — precise existing function anchors, pseudo-diffs, new module paths, static `dist/` layout and Render Static Site cutover.
3. **`Future plans/Browser-only-core-source-route-index.md`** — **92-entry, single Bxx owner** route table, Python handlers, prominent UI callers; a frozen reference snapshot, not a claim of current runtime coverage.
4. **`Future plans/Browser-only-core-integration-plan.md`** — short master architecture and scope.
5. **`README.md`** — owner policy, live product behavior, geometry and workflow rules.
6. **`docs/legacy-python-server-hosting.md`** — historical server architecture, recovery record and legacy Print behavior.

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

**Hosting:** Final target is a **new Render Static Site, using the free tier if within allowances**. It serves static HTML/JS/Pyodide/WASM/assets; no Python Web Service execution, idle sleep or ~60-second server cold start. Browser initialization may still take time. Copy `web/*` to `dist/` root, repository `images/*` to `dist/images/*`, and repo-root `Brochure.md` to `dist/Brochure.md`. Ship required pinned local runtime assets with proper MIME/cache paths. Keep historical Python/Render deployment documentation and recovery source.

**Porkbun lock:** `wavefinity.org` STAYS registered and paid at Porkbun, and Porkbun remains authoritative DNS/nameservers. No nameserver migration, domain transfer, Cloudflare Pages apex hosting, new domain purchase or new registration payment. Static hosting can be changed by modifying authorized DNS **records within Porkbun** and attaching the domains to the new Render service. Existing exact DNS values belong in private Help-Code, NOT public Bxx Stories. Do not perform these actions now. The future hosting Story MUST include a step **tell Andrew exactly what action/account configuration is needed and obtain his explicit authorization** before creating a paid resource, detaching domains, changing any DNS records, or retiring the existing service. Do not invent a future Render hostname; use the actual dashboard value at cutover.

**User-tested rule — ABSOLUTE:** No coder may write, update, repair or run automated tests, run existing suites, build test fixtures/harnesses, manually operate the app for testing, perform browser/slicer QA, or write manual test plans/checklists/instructions for Andrew. Coders **must inspect and reason through their logic, callers, constraints, data contracts, imports, error handling and final diff**. Keep legitimate *runtime* validation (input, geometry, file integrity, security); it is application code, not a test. Do not reintroduce the nine removed web tests. A reviewer must not expand a Story into a testing assignment.

## Story creation procedure

1. **Inventory existing Poller Wavefinity Stories** and current repository state. Match B00–B16 package scope and identify existing work. Record skipped/completed scope to prevent duplicates.
2. **Resolve current source only where necessary**, starting from exact symbols in the diff map and 92-entry route index. Read `gridfinity-stage1-spec.md` and `Future plans/Gridfinity-implementation-master-plan.md` as source-invariant references, and check what Stage 2 code actually merged (magnet feet, lid variants, container stacking, side openings); do NOT assume merely planned features shipped. Include Space/grid immutability; nominal versus physical cavity; Floor/None and third-party baseplate relief; measured/unverified seated lift; 7-mm Z units; printed floor sockets; grid/lid stacking; cross-grid refusals and filename pitch/unit segments. No route scanner, tests or manual test plan.
3. **Use B00–B16 as the default Story division** and the authoritative dependency table in the detailed contracts. Single OWNER per route from the 92-row index: B10 owns ALL `/api/drawer/*`, B11 owns ALL structural/Storage Drawers and pegboard hooks, B09 owns folder/Space paths including `/api/browse-output-folder`, `/api/space/show-folder` and `/api/space/warm`; B13 owns slicer browse/show-log/AI. B04 creates `route-dispatch.py`; only B14 later wires all modules' `ROUTES`. Do not create competing writers or dual route owners. Split only for safe truly independent code ownership.
4. **Resolve the ONLY known product-decision blocker BEFORE filing dependent Stories:** preserve AI Help UI, local prompt/candidate validation and copy/paste assistance. If current code/provider facts cannot safely preserve one-click direct AI chat under static hosting without server secrets or disallowed CORS, ask Andrew to choose a copy/paste-only mode or an explicitly permitted external AI service BEFORE filing B13 or B14. Do not silently disable chat or defer this decision until hosting cutover. Other Stories may still be submitted while a genuinely blocked B13 is pending; report that precisely.
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
- B07 correct 3MF
- B08 **Print** preparation/handoff
- B09 local Space/preferences/files/autosave (after relevant base runtime)
- B10 inventory/drawer save and print
- B11 all structural Spaces and related exports
- B12 advanced features, image nesting, text
- B13 optional AI and browser-incompatible desktop actions
- B14 static build **and explicit Andrew hosting approval handoff**
- B15 retire Python HTTP execution while preserving historical rollback
- B16 remove prototype/test-only scaffolding, not the production Manifold64 engine

Follow the ONE definitive dependency table in detailed contracts; **B09 needs B04, B11 needs B08+B10, B13 needs B08+B09+B12**. B10 requires B06+B09+B08. B13 cannot run before B08 or B12 because of shared JS files. B14 is solely responsible for final `route-dispatch.py` integration. Every route has ONE owner. No test Story and no test-related scope. The full application may remain nonfunctional until all code is implemented.

## What to tell Andrew after submission

Give a compact table of **actual** Story IDs, Bxx numbers, titles and dependency order; distinguish already-complete/skipped packages and unresolved blockers. State clearly:

- All implementation-ready Stories are submitted to Poller (or precisely which are blocked).
- No coding was started by this planning agent.
- No hosting/DNS or domain registration changes were made.
- Print remains part of the final application.
- Porkbun registration and DNS remain unchanged.
- No automated tests, coder manual tests or user test plans were introduced.

**Do not ask Andrew to review another high-level plan. Do not begin implementation automatically.**
