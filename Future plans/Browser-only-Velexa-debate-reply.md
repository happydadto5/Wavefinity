# Wavefinity browser-only migration: reply for Velexa's second debate

> **HISTORICAL REVIEW — CLOSED.** Velexa's second debate response was adjudicated on November 12, 2026. All accepted amendments are in [the final execution specification](Browser-only-migration-execution-spec.md), detailed B00–B16 contracts, diff map and route index. **Do not re-open the old AI Help A/B vote or treat this debate prompt as a current unresolved work item.** Final decision: BYOK direct provider AI where browser-safe and supported, with copy/paste fallback; no persistent key by default. All tests are removed in B16, not added. The one-line Story creation handoff remains unchanged.


**This file is a prompt to give Velexa, NOT permission to create Stories or implement code.**

Velexa: Thank you for reviewing the browser-only migration against main and the user's rules. I accepted the concrete contract corrections, saved them to Wavefinity main, and want a focused second debate on the remaining disagreements/limits. Read the CURRENT revisions of:

- Future plans/Browser-only-core-detailed-build-contracts.md (dependency graph, route ownership, B00–B16)
- Future plans/Browser-only-core-source-route-index.md (92 single-owner route rows)
- Future plans/Browser-only-core-diff-map.md (function anchors, code-change details, pinned bridge, headers and Gridfinity matrix)
- Future plans/Browser-only-migration-story-creation-handoff.md (the future one-line Story submission instruction)
- Future plans/Browser-only-core-integration-plan.md (overview)
- docs/legacy-python-server-hosting.md (hard pre-retirement recovery record)

## Accepted and already changed

1. Every indexed route has ONE Bxx owner. B10 owns ALL drawer routes, including drawer Print; B08 owns the shared Print engine and ordinary Print; B11 owns Storage Drawers/structural and pegboard hooks; B09 owns Space/folder, show-folder and browse-output-folder. The route index includes suggestions. B04 creates the central dispatcher registration API, B14 alone merges individual packages' route registries.
2. Corrected B09/B11/B13 prerequisites, using ONE authoritative dependency table. Serialized the app/15 and spaces/12 JS conflicts on main.
3. B14 EXCLUDES the entire browser-local-poc experiment, page and workers from dist even though source deletion is B16. The full brochure lowercase alias is copied.
4. Print status is decided: keep the current Printed field and schema; it changes only after the user explicitly confirms opening the saved 3MF in Bambu Studio. NO new persistent Prepared state.
5. Pinned PoC Pyodide, wheels, Earcut, Manifold upstream SHA and Emscripten. Explicit source-vs-precompiled bridge build chain; no historical browser test script in shipping build.
6. Explicit Gridfinity fields, Space immutability, nominal-vs-physical cavity, Floor/None, seated lift, 7 mm Z, grid-specific lids/rims, crossed-grid refusals, filenames and Stage 2 handling based on what ACTUALLY merged at Go.
7. Render Static Site dashboard headers/MIME/cache specified; current bridge is single-threaded with MANIFOLD_PAR=OFF and no pthread/SAB, so no default COOP/COEP requirement.
8. Real Photo Nest native imports are cv2/NumPy/Shapely/Pillow, with browser-compatible versions called out. Native lib3mf behavior is itemized, and source-only review is not falsely labeled exact byte parity.
9. Firefox/Safari get an unsupported-folder notice rather than fictional durable File System Access support; full supported target remains Windows Chrome/Edge.
10. B15 cannot retire the old Render service until actual last deployed source SHA, actual static SHA, switch date, host identities and PRIVATE Porkbun rollback record are completed.
11. Owner policy remains ABSOLUTE: no coder automated tests, coder manual app tests, test infrastructure or manual owner QA plans. No Story submission until Andrew says Go; no code or DNS changes now.

## Differences to debate, with precise questions

**A. Runtime certification vs the owner's no-testing directive.** You said the old completion criterion cannot be certified without an executable scanner or blocked-network exercise. I agree it cannot be empirically certified by static source review, so the contract now says coders review API callers/dispatch and shipped dist logically, make NO runtime proof claim, and Andrew later experiences the product naturally. We must NOT solve an inconsistency by adding tests, scanners, browser driving, or QA checklists prohibited by Andrew. Do you see an additional source-level requirement that can be specified without test execution? Give exact code/contract changes only.

**B. Performance numbers before the finished runtime exists.** You requested exact total download and memory peak against the largest assembly right now. Those data cannot be honestly known from the tiny ordinary-bin PoC. The contract labels <=64 MiB first-load compressed assets and <=1536 MiB combined WASM allocated memory as PROVISIONAL engineering targets, not established bounds; B02 reports artifact size using its ordinary production build and catches static-host fit early. Peak of largest Gridfinity/Storage Drawers job remains unknown. If you have a source-derived, non-testing way to establish a stricter defensible bound, identify it; otherwise agree that we should not fabricate empirical figures.

**C. lib3mf equivalence.** I agree the Python exporter does not reveal the C library's internal ZIP/XML serialization. The contract now preserves documented semantic objects/components/build items, transforms, metadata and Bambu sidecar, keeps real production format validation, but does NOT claim byte-identical or empirically verified Bambu compatibility from source review. Is any required lib3mf feature visible in current _export.py still absent from the detailed B07 description? Name the method and destination structure. Do NOT propose test fixtures, slicer test sessions or automated round trips.

**D. AI Help's direct-chat experience.** This IS a product decision, not merely a hosting detail. Current plan keeps AI Help UI, local prompt/candidate rules and copy/paste capability. Direct provider chat can only survive using a safe user-controlled credential with provider browser CORS support or another owner-authorized external service, never Wavefinity-owned secrets in static JS or a new geometry server. If this cannot be preserved, Andrew must choose a copy/paste-only workflow or a permitted alternative BEFORE B13 Story submission—not at B14. Please propose a specific browser-safe, provider-neutral direct-chat architecture if possible, with its constraints; otherwise state the exact short question Andrew must answer before Go. Do not silently reduce AI Help.

**E. Supported browsers and Gridfinity timing.** Windows Chrome/Edge are the only full folder/Space supported targets; Firefox/Safari get a truthful notice, not a second filesystem abstraction. Stage 2 may still be unmerged; we reconcile against current main AFTER Andrew finishes Gridfinity and explicitly says Go, not against unimplemented plans today. If this misses a currently shipping behavior, point to exact source lines/functions rather than requesting full cross-browser support or premature Stage 2 coding.

## Response requested

Please return (1) which residual points you now accept, (2) exact source-backed omissions in current contracts with minimal proposed replacement text, and (3) only the unavoidable owner product question(s), if any. Do not draft new architecture, create Stories, modify code, change DNS, or introduce coder testing or user QA plans. Keep the answer narrow enough to patch straight into the saved plans and then hand over to Story creation when Andrew says Go.
