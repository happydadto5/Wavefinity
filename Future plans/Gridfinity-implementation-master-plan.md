# Gridfinity in Wavefinity — implementation master plan and Velexa review

**Updated:** 2026-11-12  
**Repository owner:** Andrew; **reviewers:** GPT and Velexa  
**Authority:** This document consolidates Andrew's latest instructions and the concluded reviewer agreement. It supersedes conflicting *implementation scope* in the historical [Gridfinity.md](Gridfinity.md) (November 4). It does **not** erase those historical rulings.  
**Stage 1:** 12 Poller stories already submitted, numbered 2967–2978. Do not file duplicates.  
**Stage 2:** detailed proposal below; **NOT submitted** and not authorized to dispatch by the existence of this document.  
**Collaboration instructions:** Velexa should edit the response fields in §Review questions, mark each `AGREE / CHANGE / NEEDS ANDREW`, and propose specific changed requirements in place. Do not silently reopen the completed Stage 1 agreement. If a material Stage 1 defect is discovered, record it as a risk to existing stories, not as a replacement Story.

The full original Stage 1 story submission record follows unchanged, including the exact IDs and dependencies.

---

# Gridfinity in Wavefinity — Stage 1 story submission plan

**Plan date:** 2026-11-12  
**Status:** **12 of 12 Stage 1 stories submitted to Poller successfully.** Story IDs below come from successful create responses, not planned or inferred numbers.  
**Source:** `gridfable.md`, amended by the final Velexa/GPT agreement and Andrew's explicit unit-entry ruling.  
**Scope:** Stage 1 implementation only. Stage 2 is documented but **not submitted**.  
**Application / repository:** `wavefinity` / `Wavefinity`.

## Agreed contract — binding on every Stage 1 story

1. **One editor, one layout, one grid per Space.** A Space chooses at creation and does not change; its bins inherit the grid. A No-Space bin chooses its own. Existing files lacking the grid key remain Wavefinity and reproduce the same saved geometry. Supported pitches in **Stage 1**: 7 mm Wavefinity, 21 mm half-grid, 42 mm full Gridfinity. No automatic conversion or cross-grid placement.
2. **One grid is not one geometry.** Preserve the wavy Wall/connector rules for Wavefinity; generate flat-sided Gridfinity bins with proper feet, sockets and optional open-top stack rim. Independently specify the 21 mm extension against a named external reference implementation before writing its geometry; don't merely scale the 42 mm profile.
3. **Unit input:** For Width/Depth, a bare positive number **less than the current horizontal pitch** is a unit count: `6` -> 42/126/252 mm in 7/21/42 mm grids respectively. A bare number at or above the pitch is millimetres. `6u` explicitly means six current horizontal units; `6mm` explicitly means six millimetres. Interpret at commit only, not during typing. Unit-expressed fractional dimensions that do not land on a whole cell are refused in place rather than snapped; plain mm values use existing nearest-step snapping at commit. Out-of-range results are errors, never silently clamped. Show committed millimetres and unit count under the field.
4. **Height input:** Gridfinity height always uses **7 mm vertical units**, including in 21 mm Spaces: a bare `6` -> 42 mm; explicit `u` uses 7 mm, and committed heights use whole 7 mm steps. Wavefinity height retains today's plain-millimetre behavior, including short heights. Height parsing and min-height validation are distinct from horizontal pitch parsing.
5. **Interoperability, not self-compatibility alone:** Our 42 mm bins must fit commercially available 42 mm baseplates, third-party bins must fit built-in Wavefinity-generated floor grids, and appropriate multi-cell parts must fit. Independently verify the chosen 21 mm community implementation in both directions. Test both open-top rims and Gridfinity grid-topped stacking lids, both directions. Reconcile nominal, actual-exterior, and assembled stack height; check 0.35 mm socket relief and other dimensions against references and fit prints.
6. **Built-in grid `Floor` or `None`:** Printed floors integrate floor pockets; `None` takes a user-supplied baseplate. Distinguish the nominal exact-grid footprint from the physical printed cavity. The latter needs a tested removable-plate clearance (initial target 0.25–0.5 mm per side; *not* a presumed final dimension). Model the baseplate's **actual seated lift** above the container floor, not the total thickness. An unknown lift must not create a false verified height-fit claim. Plain Drawer Spaces retain their real-world free dimension and hatch the unusable leftover strip.
7. **Space defaults and boundaries:** Derive 21/42 mm Storage Box and Storage Drawers defaults from the verified **current shipping defaults** via nearest whole cells; do not use unsupported guesses. List and enforce every external bin entry path (drag/drop, duplicate, Space copy, AI Generate as New Bin, import/restore). Space is authoritative at API, serialization and UI boundaries.
8. **Stage 1 stacking and scope:** Both the normal optional open-bin stacking rim and the Gridfinity-grid stacking lid ship in Stage 1. The existing Stackable and Lid controls must never claim unsupported behavior. Storage Box-on-Storage Box stacking is **Stage 2**, and its future work must preserve the recently updated lid/latch/closure hardware.
9. **Printing and regression:** Meshes watertight and support-free for ordinary foot-down printing; combined exports, file names and AI Design descriptions updated alongside their exposed options. Check against configured printer volume and refuse oversize parts. If no printer is configured, report fit as **unverified**; splitting is excluded from Stage 1. Preserve all preexisting Wavefinity flows and saved design geometry.
10. **Release gate:** Test fixtures at least 1x1 and 2x3 on both 21 and 42 mm pitches; save/reload parity, meshes, dividers/pockets/bores/scoops/text without foot collisions, floor and lid fit, height checks, physical printed fit against selected third-party reference parts. **Automated tests do not substitute for Andrew's physical fit sign-off.** Do not call Stage 1 released/accepted until both pitches pass that manual gate.

## Groups and ordered filing plan

- **Foundation (S1-01 to S1-03):** verified geometry/requirements, model invariants, common geometry. Dependency gates prevent downstream work from running before the reference and contracts are established.
- **Stacking (S1-04 to S1-05):** height and optional open-top rim, then stacking grid lid.
- **Parallelizable integration (S1-06 to S1-08):** No-Space editor, space layout / Plain Drawer, and shared printed-floor engine can start after the foundation and stacking parts. Keep source ownership separate.
- **Container integration (S1-09 to S1-10):** Storage Box and Storage Drawers separately after layout plus floor engine; they may run in parallel if Poller/worktrees isolate changes.
- **Consolidation and gate (S1-11 to S1-12):** cross-cutting print/AI/release checks, then automated and physical compatibility sign-off. Stage 2 remains dormant.

Each row below has the actual Poller Story ID returned after successful submission. **Submitted is not coded, landed, printed or physically accepted.**

| Key | Planned story | Review | Tier / thinking | Start-after | Poller ID | Status |
|---|---|---|---|---|---|---|
| S1-01 | Fix the geometry and migration reference specification | standard | medium / high | — | 2967 | Submitted |
| S1-02 | Introduce grids, persistence and cross-grid API invariants | comprehensive | high / high | S1-01 | 2968 | Submitted |
| S1-03 | Build 42 mm and independent 21 mm bin-foot geometry | comprehensive | high / high | S1-02 | 2969 | Submitted |
| S1-04 | Unify Gridfinity height model and optional open-top rim | comprehensive | high / high | S1-03 | 2970 | Submitted |
| S1-05 | Implement the stacking grid lid on both Gridfinity pitches | standard | high / high | S1-04 | 2971 | Submitted |
| S1-06 | Add unit input and the No-Space Gridfinity editor | standard | high / medium | S1-05 | 2972 | Submitted |
| S1-07 | Add Gridfinity layout, placement and Plain Drawer Space | comprehensive | high / high | S1-05 | 2973 | Submitted |
| S1-08 | Add shared floor-pocket grid and removable-baseplate sizing | standard | high / high | S1-05 | 2974 | Submitted |
| S1-09 | Integrate Gridfinity in Storage Box Spaces | comprehensive | high / high | S1-07, S1-08 | 2975 | Submitted |
| S1-10 | Integrate Gridfinity in Storage Drawers Spaces | standard | high / medium | S1-07, S1-08 | 2976 | Submitted |
| S1-11 | Complete export, printer fit, AI and end-to-end consistency | standard | high / medium | S1-06, S1-09, S1-10 | 2977 | Submitted |
| S1-12 | Run release acceptance and prepare physical-print sign-off | standard | medium / high | S1-11 | 2978 | Submitted |

## Detailed story briefs

### S1-01 — Fix the geometry and migration reference specification
**Group:** Foundation. **No feature enabled.** Confirm published 42 mm foot, socket, corner radius, stacking lip, height-unit, 0.35 mm socket relief, clearance and lid dimensions. Name and cite the chosen 21 mm reference implementation and make an *independent* 21 mm dimension/fit specification. Inspect actual shipped Storage Box/Drawers defaults, all inbound bin paths, existing construction latch/lid interactions, existing printer configuration and existing oversized-drawer behavior. Define comparable 1x1 and 2x3 reference test models, external baseplates and compatible third-party bins, intended physical fit-test steps, acceptance tolerances, and existing Wavefinity geometry regression baselines. Leave unresolved actual fit tolerances explicitly as print-verified gates, not invented facts. **Acceptance:** Versioned, actionable specification and test matrix for both pitches, current defaults and ingress inventory verified in code; no production geometry or behavior change.

### S1-02 — Introduce grids, persistence and cross-grid API invariants
**Group:** Foundation. Add Space grid (`wavefinity` legacy/missing, `gridfinity`, `gridfinity_half`), No-Space bin grid, `built_in_grid` in relevant container records, inventory grid tags and authority/validation across loaders, saves, API, duplicate/copy, import/restore and AI entry boundaries. Enforce immutable Space grid and reject mismatch without converting geometry. Do not expose unfinished UI. **Acceptance:** Old files/meshes round-trip unchanged; new records round-trip; mismatch rejections at every enumerated path; no false cross-grid compatibility. **Likely files:** `organizer_spaces/_core.py`, `organizer_engine/_specs.py`, `organizer_app_impl/_design_io.py`, `organizer_inventory/_rows.py`, relevant app/API normalization and tests.

### S1-03 — Build 42 mm and independent 21 mm bin-foot geometry
**Group:** Foundation. Implement flat Gridfinity wall/cavity outlines, per-pitch foot cutters, constant/profile and mesh construction, base thickness, dimension/clearance policy, checks and physical output fixtures. Keep Wavefinity wave/stack base unchanged and mutually exclusive. Geometry must handle 1x1 and 2x3 on both pitches; no magnet/screw holes yet. **Acceptance:** Both pitch variants produce watertight, support-free foot-down meshes; outside dimensions and feet conform to S1-01 reference; cavity/inside features don't collide; Wavefinity geometry parity. **Likely files:** `organizer_features/gridfinity.py`, `organizer_engine/_specs.py`, `_wave.py`, `_boxes.py`, geometry tests.

### S1-04 — Unify Gridfinity height model and optional open-top rim
**Group:** Stacking. Implement explicit nominal bin height, exterior height and assembled stack height, including 4.75 mm foot, base thickness, optional rim; calculate usable inside depth and minimum legal 7 mm unit height. Implement optional standard open-bin stack rim (not forced when Not Stackable), both pitches, and test fit/mesh. Wavefinity base/rim behavior unchanged. **Acceptance:** 1x1 and 2x3 open-top Stackable vs Not Stackable produce correct geometry, exact reported heights and usable interior, with independent 21 mm rim/profile checks. **Likely files:** `organizer_features/gridfinity.py`, `organizer_features/stack.py`, `organizer_engine/_boxes.py`, `_specs.py`, tests.

### S1-05 — Implement the stacking grid lid on both Gridfinity pitches
**Group:** Stacking. A Gridfinity `Lid for stacking` has matching grid on its top, seats a matching bin above, preserves the closed-height contract and actual assembled height, and is geometrically viable at edge ridges. Add fit fixtures and enforce same-footprint stacking in model. Other lid types remain Stage 2. **Acceptance:** Both pitches, 1x1 and 2x3, lid and rim/foot mating checked by tests and physical-fit checklist; watertight meshes; no height overstatement or lid/body interference. **Likely files:** `organizer_features/stack.py`, Gridfinity grid shared builder, height model, tests.

### S1-06 — Add unit input and the No-Space Gridfinity editor
**Group:** Integration. Add existing-form `Grid` select to No-Space bin editor; conditional controls for Stackable and Lid for stacking; hide Wavefinity connectors in Gridfinity. Implement horizontal `<pitch` bare unit rule, `u` and `mm` explicit forms, commit-only conversion, on-field errors for invalid unit fractions, mm snapping, no clamping; separate 7 mm Gridfinity Height and existing Wavefinity Height parsing. Show sizes/units. Hook print/save/AI prompt in the **same story as the new choices**. **Acceptance:** `6` -> 42/126/252 mm for Wavefinity/half/full widths; Gridfinity Height `6` -> 42 mm; Wavefinity Height `6` -> 6 mm; 1.5 units on 42 mm refuses; 63 mm on 21 mm shows 3 units; existing Wavefinity user data unchanged. **Likely files:** `web/index.html`, `web/app/08`–`10`, design IO, `wavefinity_web_impl/_ai.py`, `ai-features.md`, tests.

### S1-07 — Add Gridfinity layout, placement and Plain Drawer Space
**Group:** Integration. Make space grid the source for cell spacing, snapping, overlap and mismatch refusals across every enumerated entry path. Add grid selector in Plain Drawer Space; preserve real drawer measurements, hatch the leftover strip, select front-left origin, no Gridfinity bin-to-bin spacers/connectors. Add vertical stack/available-height validation (including lid/rim) and a measured baseplate **seated lift** field for user-supplied plates; unknown lift reports unverified. **Acceptance:** Both grids place 1x1/2x3 correctly, reject incompatible bin at drop/API, reject collisions and over-height stacks, show correct remaining strip. **Likely files:** `web/drawer-model.js`, `web/drawer-view.js`, `web/drawer-panel.js`, `organizer_drawer/_core.py`, Space setup, tests.

### S1-08 — Add shared floor-pocket grid and removable-baseplate sizing
**Group:** Integration. Build a shared 42/21 mm raised floor-grid builder for container floors and grid lids, conforming to S1-01 verified socket relief. Define nominal grid-area size separately from real cavity-size/margin; expose `Floor` and `None` geometry, test removable-baseplate clearance (initial 0.25–0.5 mm/side) before selecting final values, and calculate actual seated lift for height consumption. **Acceptance:** External 1x1/2x3 bins locate on printed floor; third-party baseplates physically drop into `None` floor cavities with tested clearance and seat-height reporting; geometry watertight, no unreported fit claims. **Likely files:** `organizer_features/gridfinity.py`, relevant shared geometry/layout planners and tests.

### S1-09 — Integrate Gridfinity in Storage Box Spaces
**Group:** Containers. Use existing Storage Box setup with Grid select fixed at creation, both pitches, Floor/None floor setting, verified-derived defaults, new cavity profile and layout, output naming/print, physical seated baseplate lift and height checks. Preserve recently fixed Storage Box lid/latch/hinge design; do **not** implement Storage Box-on-Storage Box stacking in Stage 1. Keep Wavefinity current paths unchanged. Update AI feature descriptions alongside controls. **Acceptance:** Box with full/half grid and `Floor`/`None` prints and lays out 1x1/2x3 parts; no lid/latch regressions; unknown printed fit is not misrepresented. **Likely files:** `organizer_b4b/`, `web/storage-box-form.js`, `web/spaces/08-space-setup.js`, `web/spaces/10-storage-box-structural.js`, outputs, tests.

### S1-10 — Integrate Gridfinity in Storage Drawers Spaces
**Group:** Containers. Existing cabinet/Drawer setup gets fixed Grid select, 21/42 step defaults derived from real shipping values, Floor/None settings, flat cavity plus raised grid profile, layout and print/export for drawers. Model baseplate seated lift and drawer vertical clearance. Preserve all legacy Wavefinity drawer paths. Update AI descriptions alongside controls. **Acceptance:** Both pitches, both floor settings, 1x1/2x3 occupied grid cases, correct drawer-height and floor margins, no regressions. **Likely files:** `organizer_storage/drawers.py`, `drawer_geometry.py`, `drawer_outputs.py`, `web/storage-drawers-form.js`, `web/storage-drawers.js`, tests.

### S1-11 — Complete export, printer fit, AI and end-to-end consistency
**Group:** Consolidation. Verify all exposed Gridfinity choices are in AI Design docs/prompts, saved design flows, STL/3MF or existing print outputs, filenames with grid/pitch and nominal units, and combined real-bounds placement. Detect part-volume overflow for selected printer and refuse with clear reason; with no printer configured state `fit unverified`. Explicitly exclude automatic splitting. Check no production option exposed prematurely, old Wavefinity exports identical. **Acceptance:** End-to-end save/print/restore fixtures for both pitches across No-Space, Plain Drawer, Storage Box, and Storage Drawers; correct printer failure/unknown cases. **Likely files:** `organizer_app_impl/_filenames.py`, `organizer_outputs`, `plate_layout.py` tests, `wavefinity_web_impl/_ai.py`, `ai-features.md`, docs.

### S1-12 — Run release acceptance and prepare physical-print sign-off
**Group:** Release gate. Execute automated cross-feature test matrix (1x1, 2x3, full and half; open stack rim and grid lid; mesh integrity; interior dividers/cradles/pockets/bores/scoops/text; save/reload; API ingress; old Wavefinity baselines; build volume; Floor/None). Produce a clearly labelled printed-fit sign-off sheet for Andrew covering external bin/baseplate mating in both directions, both pitches, and both stacking directions, with measured tolerances and failures recorded. **Do not report Stage 1 physically accepted or released merely because automated tests pass; Andrew's real print sign-off is mandatory.** **Acceptance:** Automated regression evidence and physical acceptance checklist ready; final Stage 1 completion is conditional on documented successful physical fit results. **Likely files:** geometry, integration and acceptance tests; `README.md`, `features.md` and an acceptance report.

## Stage 2 — explicitly deferred; no stories created

- Magnet holes in 42 mm bin feet; optional screw holes, only if Andrew approves.
- Storage Box-on-Storage Box stacking with lid grid + box feet, preserving rebuilt lid/latch/closure hardware.
- Other Gridfinity lids, hinges and Side Openings.
- Baseplate-retaining spacers for plain drawers (not bin-to-bin spacers).
- Third-party bin placeholders in Gridfinity layout.
- Optional future printer-bed splitting, only by separate approved story.

## Filing ledger

**Submission result:** 12 accepted / 0 failed, IDs **2967–2978**. S1-01 was accepted in `awaiting_design`; S1-02 through S1-12 were accepted in `dormant` status, held behind their actual `start_after` gate(s). These are Poller workflow states at submission, not a promise that status will remain unchanged.

**Actual dependency gates recorded at submission:** 2968 ← 2967; 2969 ← 2968; 2970 ← 2969; 2971 ← 2970; 2972/2973/2974 ← 2971; 2975/2976 ← 2973 + 2974; 2977 ← 2972 + 2975 + 2976; 2978 ← 2977.

Stories are filed through Poller with unique `submission_id` values, `application_id=wavefinity`, `target_repo=Wavefinity`, an explicit tier/thinking/reason, and `start_after` dependencies on actual returned IDs. **Submitted** means the Poller create endpoint returned `ok: true` with a real Story ID, not that code was implemented or accepted.



---

## Stage 2 — filing-ready draft for Velexa's in-document review

**Status:** `DRAFT / NOT SUBMITTED`. Nothing in this section has a Poller ID. This is not permission to start Stage 2 before Stage 1 physical acceptance. After Velexa reviews and Andrew decides any marked owner questions, another LLM can submit these records in the approved order using the Poller `wavefinity` application and `Wavefinity` target repository; enter returned numbers into the ledger, do not invent them.

**Stage 2 assumptions (do not silently change):** 21 mm and 42 mm Gridfinity, open-bin rim, stacking grid lid, ordinary bin editor, Plain Drawer, Storage Box/Drawers, and `Floor/None` are Stage 1 requirements. Their Stories 2967–2978 already exist. Stage 2 must not redo, regress, or weaken them. Magnets in 42 mm bin feet are optional and default off; **21 mm magnets are not specified**. No Gridfinity bin-to-bin connectors/spacers. The entire Storage Box stacking system is an advanced Stage 2 addition; ordinary bins' rim and grid-lid stacking are already Stage 1. Existing Wavefinity geometry is unchanged. Optional screw holes require a distinct Andrew decision. Automatic printer-bed splitting is a separate future proposal and is not part of an approved Stage 2.

### Proposed Stage 2 story ledger

| Key | Proposal | Review / tier / thinking | Submission prerequisites | Poller ID | Status |
|---|---|---|---|---|---|
| S2-01 | Optional magnet pockets in 42 mm bin feet | standard / medium / medium | Stage 1 acceptance + magnet spec Q1 | — | Not submitted |
| S2-02 | Storage Box-to-Storage Box Gridfinity stacking | comprehensive / high / high | Stage 1 acceptance + box interface Q2 | — | Not submitted |
| S2-03 | Other ordinary-bin Gridfinity lids (plain and hinged) | standard / high / medium | Stage 1 acceptance + lid matrix Q3 | — | Not submitted |
| S2-04 | Gridfinity side openings without losing baseplate compatibility | standard / high / medium | Stage 1 acceptance + opening matrix Q4 | — | Not submitted |
| S2-05 | Optional loose-baseplate retention in Plain Drawer Spaces | standard / medium / medium | Stage 1 acceptance + plate retention Q5 | — | Not submitted |
| S2-06 | Third-party Gridfinity bin placeholders in layout | comprehensive / high / medium | Stage 1 acceptance + metadata rules Q6 | — | Not submitted |
| S2-07? | Optional screw holes in 42 mm feet | **not approved / review TBD** | Andrew's explicit approval + S2-01 | — | Decision pending |
| Future | Printer-bed split-and-join geometry | **not Stage 2** | Separate scope and owner approval | — | Out of scope |

**Recommended filing sequence and start-after gates:** First confirm Stage 1 physical sign-off in the S1-12 acceptance record, **not merely that Story 2978 is marked complete**. File S2-01, S2-02, S2-03, S2-04, S2-05 and S2-06 in that order once their specific review questions are resolved. Give each `start_after: [2978]` as a minimum automated gate, but keep the separate manual sign-off requirement in its description. S2-01/S2-03/S2-04/S2-05/S2-06 can otherwise proceed independently when their interface contracts are settled; S2-02 should not be bundled with unrelated bin-lid changes. If any actual files or invariants collide, add `start_after` for the prerequisite **real returned** Stage 2 ID before filing the dependent story. Never put a proposed key such as S2-01 into the numeric gate. Do not file optional S2-07 without Andrew's explicit answer.

### S2-01 — Optional magnet pockets in 42 mm bin feet

**Problem:** Stage 1 bins locate mechanically but do not offer magnetic retention on standard 42 mm Gridfinity bases. The 21 mm pitch does not have enough independent room for the agreed magnet pattern and was not promised magnets.

**Intended behavior:** Add `Magnet holes: None (default) / 6×2 mm magnets` to **ordinary 42 mm Gridfinity bin feet only**. Use the verified standard location pattern on every 42 mm cell and conservative clearance/depth from approved reference/test prints. Account for the foot's tapered profile, material between bore and floor, print orientation and press-fit/adhesive retention. Never cut a hole through the useful bin floor or interfere with support-free printing. No magnets in container floors, in 21 mm feet, or in legacy Wavefinity designs. Preserve existing 42 mm foot fit whether magnet holes are selected or not.

**Likely touch points (verify current file paths):** `organizer_features/gridfinity.py`, `organizer_engine/_specs.py`, mesh cutters in `organizer_engine/_boxes.py`, No-Space editor, save/load, AI option text, tests and print export.

**Acceptance:** 1×1 and 2×3 42 mm bins with and without magnets remain watertight and fit the same third-party plate; confirmed magnet fit/retention test print; no unusable/through holes; serialized choice and exported geometry match; 21 mm and legacy Wavefinity paths unchanged. **Do not file until Q1 establishes whether geometry and magnet retention have a settled fit reference.**

### S2-02 — Gridfinity stacking for entire Storage Boxes

**Problem:** Stage 1 supports loose-bin rim/lid stacking but not a complete Storage Box sitting on another Storage Box or a third-party 42/21 mm Gridfinity plate.

**Intended behavior:** When Storage Box stacking is enabled in a Gridfinity Space, provide correctly located feet under the box and a compatible receiving grid on the closed lid/top, for **both 42 and 21 mm grids**. State the assembled exterior height and box-to-box stack height correctly; refuse layout/collision/over-height use and handle unsupported sizes or load-bearing geometry. Reuse verified shared floor/foot profiles and existing stacking grid lid geometry when compatible.

**Non-negotiable regression guard:** The current Storage Box construction-package hinge, latch count/tightness, lid snugness/headroom, screw engagement, opening clearance and closed-lid rigidity must remain intact. Do not replace the existing latch mechanism as a shortcut. Check real load/closure geometry and third-party plate interaction. Do not extend this mode to Wavefinity boxes or unapproved lid variants by accident.

**Likely touch points:** `organizer_b4b/_geometry/_body.py`, `organizer_b4b/_geometry/_lid.py` (if present; verify), `organizer_b4b/_plans.py`, box outputs, layout and storage-box form, shared Gridfinity profile helpers, tests.

**Acceptance:** Both pitches with 1×1 and multi-cell footprints, closed box on a third-party plate, one box on another, loose bin on top of a box, full opening/closing of hinge and latches, mesh watertightness, correct printed exterior/stack dimensions. Existing Storage Box Wavefinity lid/latch regression snapshots match before/after. Perform physical strength and fit checks rather than claiming heavy stacking capacity without test. **Do not file until Q2 resolves lid-grid/latch compatibility details.**

### S2-03 — Remaining ordinary-bin lids (plain and hinged) on Gridfinity

**Problem:** Stage 1 offers the Gridfinity `Lid for stacking` but leaves other ordinary-bin lid choices unsupported.

**Intended behavior:** For both pitches, enable existing plain lid and hinged lid configurations only where their closure geometry can stay inside the Gridfinity footprint and avoid interfering with feet, upper rim, adjacent bins or baseplate seating. Explicitly define the compatibility matrix among `Stackable`, stacking grid lid, plain lid and hinged lid; never label a lid as stack-compatible unless it has proven receiving geometry. Preserve Wavefinity lids. This is **ordinary-bin lids**, not whole Storage Box-on-box stacking (S2-02).

**Likely touch points:** `organizer_features/stack.py`, `lid_hinge.py`, `organizer_engine/_specs.py`, existing editor controls, export, layout height and tests.

**Acceptance:** Tested 1×1 and 2×3 lid configurations for 21/42, no external hinge protrusions making neighbor fit falsely pass, correct closed/assembled heights, support/clearance and mesh tests, valid persisted options, no Wavefinity regressions. **Do not file until Q3 settles which legacy lid combinations actually fit.**

### S2-04 — Gridfinity Side Openings

**Problem:** Side Openings have been kept Wavefinity-only pending geometry and wall-strength verification.

**Intended behavior:** Support existing Side Openings on flat Gridfinity bins for both pitches while preserving external dimensions, standard baseplate placement, neighboring bins' clearance and foot/stack-rim strength. Reject or constrain openings that intersect functional feet, rim support, hinges, or wall thickness rather than emitting fragile/unprintable meshes. Keep Edge Mount unsupported unless Andrew separately authorizes a compatible inside-footprint design; it can project beyond Gridfinity cell allowance.

**Likely touch points:** `organizer_features/side_openings.py`, `organizer_engine/_boxes.py`, specs, editor controls, AI descriptions, tests.

**Acceptance:** Both pitches, side opening cases with normal interior features and stacking rim/lid, watertight mesh, no over-cell protrusions, minimum wall strength and unchanged mating-foot fit. Stage 1 bins without openings and legacy Wavefinity designs remain unchanged. **Do not file until Q4 defines opening/hinge interactions.**

### S2-05 — Retain loose external baseplates inside Plain Drawer Spaces

**Problem:** A purchased baseplate in a real drawer can slide within the leftover gap although bins are held to that plate.

**Intended behavior:** Provide optional measured retaining pieces or stops to locate the user's own baseplate inside the real drawer without reintroducing bin-to-bin spacers or claiming Wavefinity prints separate baseplates. Support arbitrary unused left/right/front/back margins from actual drawer and plate measurements; do not quietly assume a nominal plate has exact physical external dimensions. Keep bin seating/lift model from Stage 1 accurate.

**Likely touch points:** `organizer_drawer/_spacers.py` (or new retaining feature), `web/drawer-panel.js`, Plain Drawer setup/layout and print outputs.

**Acceptance:** Placement and print examples for both pitch types and a non-multiple real drawer width, plate held without forced dimensional changes, unobstructed bin insertion, output only when user requests retention, no bin-to-bin connectors/spacers. Unspecified plate dimensions result in a clear prompt or unverified fit claim, not a guessed part. **Do not file until Q5 chooses the simplest retention design.**

### S2-06 — Third-party bin placeholders in layout

**Problem:** Layout currently models only bins made by Wavefinity, even when the user physically uses third-party Gridfinity bins.

**Intended behavior:** Add inventory/layout-only placeholders with selected grid pitch (21 or 42), whole-cell width/depth, optional measured actual exterior height and readable name/label. Place them by the same collision, mixed-grid refusal, and stack-height rules as Wavefinity-made bins. Show a clearly different icon/label; do not fabricate a mesh, geometry editor, STL, print file or AI-generated bin from a placeholder. Define how importing, duplicating, moving between Spaces, and save/reload work without violating Space grid authority. Unknown height must never pass a vertical fit as verified.

**Likely touch points:** `organizer_inventory/_rows.py`, `web/drawer-model.js`, `web/drawer-view.js`, layout editor and save/import, tests.

**Acceptance:** A user can place one 1×1 and one 2×3 third-party placeholder on both grids, accurately detect overlap/height, preserve records across save/reload, reject cross-grid entry and avoid export as manufactured parts. Existing real-bin inventory remains unchanged. **Do not file until Q6 settles the record schema and unknown-height behavior.**

### S2-07? — Screw holes (optional, *not authorized*)

**Decision boundary:** The older November 4 plan referred to screw holes in the first pass, but Andrew's November 11–12 decisions explicitly deferred them and says they **may** be added in Stage 2. No tool or reviewer may interpret this as approval. If Andrew requests them, create a separate 42 mm ordinary-bin foot story for screw-hole selection, with an independently verified reference location, clearances, compatibility with optional magnet pockets, print/fastener safety and non-regression tests. **No story ID, tier or dispatch until owner approval.** Container-floor screw/magnet holes remain excluded unless separately approved.

### Exclusions and release policy

- **No Stage 2 story submission yet.** This plan is editable review material for Velexa, not a Poller submission authorization.
- Automatic splitting of oversized parts, 21 mm magnets, separately generated baseplates, Edge Mount and stronger mechanical attachment systems are not included.
- Stage 2 acceptance requires physical fit tests appropriate to each new geometry, including confirmation that existing Stage 1 21 mm and 42 mm interoperability is still intact.
- Every submitted story must independently include the exact intended behavior, affected files (updated by a quick source inspection), acceptance criteria, `application_id=wavefinity`, `target_repo=Wavefinity`, review depth, tier/thinking/tier reason and numeric `start_after` Story IDs, and then record its returned Story ID in the ledger. Never write `Submitted` before Poller returns success.

## Review questions for Velexa — answer **directly in this document**

**Do not reopen settled Stage 1 scope** unless identifying a demonstrable contradiction. For each question, replace the response line with your reasoning, recommendation and any exact edits to the Stage 2 story above. Mark `AGREE`, `CHANGE` or `NEEDS ANDREW`. If there is a genuine product choice, don't decide it on Andrew's behalf. Add source paths or standards where applicable.

### Q1 — Magnet-hole geometry and retention

Can you verify the actual 42 mm Gridfinity magnetic foot reference (nominal 6×2 magnet, hole diameter/depth, 26 mm center spacing, minimum wall/floor thickness, whether glue/press fit and through-bottom relief are expected)? Are the suggested 6.5×2.4 mm cavities right for Wavefinity's print orientation, or should they be test-derived? Does S2-01 need any separate compatibility or slicer tests?

**Velexa response:** **Velexa response — CHANGE:** The pattern figures are the right starting point and they are traceable: Fable's plan (gridfable.md, geometry notes) specifies magnet 6 x 2 mm, four per 42 mm cell on a 26 mm square (that is, hole centres 13 mm either side of the cell centre), hole 6.5 mm across, 2.4 mm deep. But no named external reference has verified them yet, and the landed Stage 1 specification (gridfinity-stage1-spec.md, section 3) deliberately lists magnet/screw fit as a (confirm) item. Exact edit to S2-01: its first step names and cites the magnet reference it follows (the same Gridfinity reference family the Stage 1 foot profile was taken from), and the 6.5 x 2.4 mm cavity is recorded as a test-derived starting value to be confirmed on Andrew's printer, material and slicer — the same discipline as every other fit dimension in Stage 1 — not as a settled fact. Retention: press fit, adhesive optional; no through-bottom relief and no hole that breaks the bin floor above the foot (the foot profile is 4.75 mm tall; the 2.4 mm cavity must leave the floor structure intact, and the story's acceptance already requires no unusable/through holes). No separate slicer or compatibility story is needed: the magnet fit/retention test print already in S2-01's acceptance covers it. Settled and not reopened: magnets in 42 mm bin feet only, none in 21 mm feet (the pattern does not fit the 21 mm foot), none in container floors (Andrew's rule).

### Q2 — Whole Storage Box stacking and current closure hardware

Trace the **current** `organizer_b4b` lid, hinge, latch, headroom and hardware paths. Does Gridfinity grid-on-lid plus bottom feet physically coexist with them on both pitches? What must be explicitly forbidden or recomputed to avoid regression (e.g. labels, lid type, latch clearance, opening swing and load-bearing assumptions)? Is S2-02 best as one comprehensive story, or should it have a contract-only prerequisite?

**Velexa response:** **Velexa response — CHANGE (add a contract-only prerequisite):** I traced the current closure hardware through the landed construction package (Stories 2956-2960, all complete) and the Stage 1 spec's code inventory. The facts S2-02 must respect: the latched lid's plate is a fixed 2.4 mm skin (2956); lid head-room is a shown choice (0.5 / 1.0 / 2.0 mm) measuring the whole-inside gap to the lid underside (2957); latch detent is 0.35 / 0.40 / 0.45 mm with the two-latch default set by interior width over 96 mm (2958); the box hinges are screw hinges (2959); lid label location defaults to the lid top (gridfinity-stage1-spec.md, section 5). Coexistence findings: (1) a receiving grid on the lid top collides with a top label — a stacking-enabled box must not offer the top label location; (2) grid features added on top of the latched lid must not change the 2.4 mm plate or the head-room measurement, which is taken to the lid underside; (3) a hinged lid swings itself and anything on it through an arc — whether the grid and an upper box's feet clear that swing, and whether hinge screw bite survives grid cells at the hinge edge, is an open geometry question, not a detail; (4) the upper box's feet must not land where the lower box's latches swing or grip; (5) a stacked box's weight lands on a lid plate designed for closure, not load — no stacking load capacity may be stated anywhere without a physical test result. Because (3) and (5) are empirical, exact edit: file a slim contract-only prerequisite story first (the same role Story 2967 played for Stage 1) that settles lid-type eligibility for stacking (which lid types may carry the grid), the label rule, the latch/feet clearance map, the assembled-height model, and the load-test protocol. S2-02 itself stays one comprehensive build story, filed after that prerequisite is agreed.

### Q3 — Plain versus hinged Gridfinity bin lids

Which existing ordinary-bin lid variants actually work with the 21/42 mm footprint, optional open-top stacking rim and neighboring bins? Can plain and hinged lids share one coherent S2-03 story, or should they be split? Confirm actual files and the display/disable rules for unsupported combinations.

**Velexa response:** **Velexa response — CHANGE (split S2-03 in two):** The two lid kinds have different risk. A plain lid is a plate inside the footprint; nothing moves and nothing protrudes — low risk on both pitches. The ordinary-bin hinged lid is a different mechanism from the Storage Box hinges: it uses a 1.75 mm filament pin along the rear wall, and its knuckles must be verified inside the 41.5 mm cell allowance with a neighbour seated, against the optional stacking rim, and against the foot of a bin above when the lid is closed. A hinge problem should not park the plain lid. Exact edits: S2-03 becomes S2-03a — plain lids on Gridfinity bins, both pitches (standard / high / medium as proposed); S2-03b — hinged lid on Gridfinity bins (standard / high / medium), whose design first names the envelope check (hinge line, pin channel, swing) against the cell allowance and the rim, and records the lid as ineligible rather than forcing geometry if it cannot stay inside. Combination rules for both: a lid choice that cannot apply is not offered (the app's existing convention — compare the latch choice, which exists only for the latched lid type); 'Lid for stacking' (Stage 1) and a plain or hinged lid are mutually exclusive choices in the one Lid control; no lid may be labelled stack-compatible without the receiving geometry from Stage 1's grid lid or the open-top rim. Files confirmed from the Stage 1 inventory: organizer_features/stack.py for lid/rim behaviour, the hinge construction beside the existing bin lid code, organizer_engine/_specs.py LidSpec.

### Q4 — Side Openings and Edge Mount

Can Side Openings be safely supported on a standard flat Gridfinity sidewall without exceeding cell envelope or weakening the stacking rim/feet? Specify invalid intersections, minimum wall constraints and fit tests. Confirm Edge Mount remains excluded unless a new inside-envelope solution is expressly approved.

**Velexa response:** **Velexa response — AGREE, with the constraint list written into S2-04:** Flat Gridfinity walls make openings geometrically simpler than on wavy Wavefinity walls, and the story's shape is right. Exact additions to S2-04's intended behaviour: an opening is refused in place, in plain words, when it would intersect (a) the foot zone — the 4.75 mm foot profile plus the base above it; (b) the stacking-rim zone at the top of a Stackable bin; (c) the corner regions carrying the foot corner radii; or (d) any wall section that would leave less than the bin's chosen wall thickness standing. Refusal, never silent clipping or shrinking of the opening. Fit tests to add to acceptance: with a maximum-size opening present, the bin's foot still mates the reference plate and a reference bin still seats on its rim, both pitches, 1x1 and 2x3. Edge Mount: confirmed excluded — it projects beyond the cell allowance; only an inside-envelope design Andrew expressly approves could reopen it, and none is proposed here.

### Q5 — Loose baseplate retention in real drawers

Given Stage 1's `None` floor clearance and measured seated-lift model, what is the smallest physically reliable retention feature (corner stops, edge shims, modular wedges, or something else)? Should it be one story or separable geometry/UI stages? Confirm no accidental duplicate baseplate generation.

**Velexa response:** **Velexa response — AGREE, with the retention design named:** The smallest physically reliable feature is measured edge shims: simple printed strips generated from the drawer's actual interior size and the plate's actual measured outside size, placed in the leftover margins Stage 1 already computes and hatches, filling the gap so the plate is located and cannot wander. They are spacers for the plate, not bin-to-bin spacers, and they carry a small working clearance per side in line with the Stage 1 None-floor clearance testing (0.25-0.5 mm), never a force fit. One story is right: the geometry is plain strips, and the real work is the measured-plate entry and placement in the existing Plain Drawer layout. Confirmed: this story prints retaining pieces only — Wavefinity still does not generate baseplates; when the user has not measured their plate, the flow asks for the measurement instead of assuming a nominal size (S2-05's acceptance already says this; keep it as a hard requirement, not a fallback).

### Q6 — Third-party placeholder representation

What persisted shape and UI should represent third-party Gridfinity bins so they never masquerade as printable designs? How should unknown height be modeled and displayed, and what happens on duplicate/copy/import and stacking? Does this cross enough core data structures to justify comprehensive review as suggested?

**Velexa response:** **Velexa response — AGREE (comprehensive is justified):** This crosses inventory rows (organizer_inventory/_rows.py), layout collision and stack rules, save/load and import, and the Space-grid authority from Story 2968, so comprehensive review is earned, not ceremony. Persisted shape, to write into S2-06: a row of a distinct placeholder kind carrying grid pitch, whole-cell width and depth, an optional measured exterior height, and a name — and deliberately NO design payload, so a placeholder can never enter the bin editor, print, export, or AI Design paths; it is not a design and must not be convertible into one in place. Unknown height is stored as unknown (not zero, not a default): any height check touching an unknown-height placeholder reports unverified rather than passing, and the layout shows the placeholder in its distinct style with the height shown as not measured wherever heights appear. Duplicate and Space copy preserve the record and its pitch unchanged; import into a Space of a different grid is refused under the same cross-grid rule as real bins. Stacking: a placeholder may be shown in a stack only with its measured height; with unknown height it sits at floor level in the layout and any stack above it is reported unverified.

### Q7 — Stage 2 grouping, filing and dependencies

Do the proposed S2-01..S2-06 groups minimize file ownership conflicts and review load, given the actual current repository? Are any additional baseline regression or physical-test stories required before the implementation stories? Propose concrete changes to sequence/gates with reasons. Do not invent Poller IDs or submit stories while reviewing.

**Velexa response:** **Velexa response — CHANGE (one added gate; the rest agreed):** The grouping is sound and the filing discipline in the ledger (real returned IDs only, manual sign-off recorded in S1-12's record rather than inferred from Story 2978's completion) is exactly right — keep it. One file-ownership collision to gate: S2-01 and S2-04 both cut into the Gridfinity foot and wall geometry (organizer_features/gridfinity.py and the mesh construction in organizer_engine/_boxes.py). File S2-04 with start_after on S2-01's real returned ID so the two never edit the foot cutters concurrently. S2-02 files only after its Q2 prerequisite spec is agreed (that gate replaces nothing else in its row). S2-03a and S2-03b are independent of each other once Stage 1 is accepted; S2-05 and S2-06 touch separate areas (drawer retention; inventory/layout records) and can proceed in parallel with the others. No additional baseline-regression or physical-test stories are needed: Story 2978's acceptance record is the baseline, and each Stage 2 story already carries its own physical-fit acceptance under the release policy. Nothing in this section is filed until Stage 1 physical sign-off is recorded — agreed without change.

### Q8 — Owner decisions versus technical clarifications

Identify **only** remaining decisions that genuinely require Andrew (rather than implementation verification). In particular, screw holes are optional and **not approved** for filing; list any other decision you cannot settle from the existing plan. Avoid asking again about both grids, unit entry, the Stage 1 rim/lid, or one-grid-per-Space: Andrew has already settled those.

**Velexa response:** **Velexa response — NEEDS ANDREW (two decisions only):** (1) Screw holes in 42 mm bin feet (S2-07): not approved. Andrew's word is needed before any story exists; the November rulings deferred screw holes and nothing since has approved them. (2) A stacking load claim for Storage Boxes: whether the app or its documentation may state any weight capacity for a box stacked on a box. My recommendation is to claim none — the lid plate was designed for closure, not load — but if Andrew wants a number, it must come from the physical load test in the Q2 prerequisite spec, and choosing to publish a tested number is his call. Everything else in Q1-Q7 is verification against named references and test prints, or reviewer judgment inside the agreed plan. Explicitly NOT reopened, per Andrew's settled rulings: magnets exist in 42 mm bin feet only (none in 21 mm feet, none in containers); Edge Mount stays excluded unless Andrew affirmatively raises it; both grids, unit entry, the Stage 1 rim and grid lid, and one grid per Space are settled. Andrew's physical print sign-off remains the Stage 1 release gate (Story 2978's record) — a gate, not a new question.

### Review summary (Velexa fills)

- **Review date / commit:** 2026-11-12, Velexa, responding to the plan as committed in 07a44a31 and ebdc76b8.
- **Accepted Stage 2 story set:** S2-01 (magnet pockets, with the Q1 reference-and-confirm edit), S2-02 (Storage Box stacking, filed only after a new contract-only prerequisite spec — see Q2), S2-03 split into S2-03a plain lids and S2-03b hinged lid (Q3), S2-04 (Side Openings, with the Q4 constraint list and gated behind S2-01 — Q7), S2-05 (baseplate retention by measured edge shims, Q5), S2-06 (third-party placeholders, comprehensive, Q6). S2-07 screw holes: NOT accepted — not approved, Andrew's decision pending.
- **Recommended changes:** Q1 — magnet cavity figures are test-confirmed starting values from a named reference, not settled fact. Q2 — add a slim prerequisite spec story for Storage Box stacking (lid eligibility, label rule, latch/feet clearances, load-test protocol) before the comprehensive build. Q3 — split plain and hinged lids. Q4 — write the refusal constraints (foot zone, rim zone, corners, wall minimum) into S2-04. Q7 — S2-04 starts after S2-01 (shared foot/wall geometry files).
- **Explicit Andrew questions:** (1) Screw holes in 42 mm bin feet — approve or decline S2-07. (2) May a tested stacking load capacity for Storage Boxes be published, or should no capacity be claimed (Velexa recommends claiming none)? Both are also recorded in Q8.
- **Can another LLM file the approved stories without guessing?** YES for S2-01, S2-03a, S2-03b, S2-04, S2-05 and S2-06, once Stage 1 physical sign-off is recorded in Story 2978's acceptance record; S2-02 after its prerequisite spec story is agreed; S2-07 NO — it must not be filed without Andrew's explicit approval.
- **Stage 2 filing authorization:** `NOT GIVEN BY THIS DOCUMENT`

