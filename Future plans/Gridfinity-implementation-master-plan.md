# Gridfinity in Wavefinity — implementation master plan and Velexa review

**Updated:** 2026-11-12 (Velexa response reconciled; Stage 2 filing instructions finalized)  
**Repository owner:** Andrew; **reviewers:** GPT and Velexa  
**Authority:** This document consolidates Andrew's latest instructions and the concluded reviewer agreement. It supersedes conflicting *implementation scope* in the historical [Gridfinity.md](Gridfinity.md) (November 4). It does **not** erase those historical rulings.  
**Stage 1:** 12 Poller stories already submitted, numbered 2967–2978. Do not file duplicates.  
**Stage 2:** final reviewer-agreed filing plan below; **NOT submitted**. File only after the recorded Stage 1 physical sign-off and Andrew's submission direction; screw holes are declined, and load capacity is intentionally not discussed, tested, or published.  
**Collaboration result:** Velexa answered Q1–Q8 on 2026-11-12; GPT agrees with the proposed technical changes, which are incorporated into the authoritative Stage 2 story descriptions and filing ledger. The unedited responses remain preserved below. Do not reopen settled Stage 1 scope; record any newly demonstrated Stage 1 defect as a risk to its already-filed Story, not a duplicate.

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

- Magnet holes in 42 mm bin feet; screw holes were expressly declined by Andrew (2026-11-12) and are out of scope.
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

## Stage 2 — agreed technical filing plan (not yet submitted)

**Status:** Reviewer agreement reached 2026-11-12. These are complete *future* Poller story briefs, not filed Stories. Stage 1 remains Stories **2967–2978**; **never file those again**. This section incorporates the Velexa responses preserved below. It takes precedence over earlier draft wording and proposed story labels.

**Blocking prerequisite for filing:** Poller Story **2978** must contain Andrew's documented **physical-fit acceptance** for *both* 42 mm and 21 mm, including independent third-party plate/bin mating and both stack directions. A numeric `start_after: [2978]` gate is not a substitute for that recorded human sign-off. If the sign-off is absent or ambiguous, **do not file any Stage 2 story**; first obtain or record the acceptance through the appropriate existing Stage 1 workflow. Do not assume `done` alone proves a successful physical print test. If a prerequisite fails or is cancelled, stop and request instructions rather than routing around it.

**Authority and scope:** The owner has approved Stage 1 and jointly agreed *what belongs in* Stage 2, but this document is not a claim that any Stage 2 story was submitted. A future filing agent should use this signed-off plan when asked to submit the remaining stories, after the Stage 1 physical gate is met. Andrew has **declined screw holes**; there is no screw-hole story. Per his recorded response, **weight is not discussed** in this project: do not claim, test, propose, estimate, or document a stacking weight capacity. Continue geometric fit/functional closure checks without turning them into a weight-rating exercise.

**Common constraints for all Stage 2 stories:** Both Gridfinity pitches 21 mm and 42 mm continue to work except the explicitly 42 mm-only magnet-hole option. Preserve the one-grid-per-Space rule, single editor/layout and existing Wavefinity geometry, file compatibility and printed outputs. Stage 1 already implements open-top rim, receiving-grid lid, Plain Drawer, both printed-container floor options and proper height semantics; do not recreate or regress those. Change AI Design feature declarations in the same story as each new user-visible option; update README/features, run save/load/print/export regression and 1×1 and 2×3 geometry tests. All fit claims require actual test prints or are explicitly marked unverified. Automatic printer-bed splitting, separately generated baseplates, Edge Mount, container magnet/screw holes and 21 mm magnet holes remain excluded.

### Final Story ledger, proposed order and numeric dependency rules

| Filing sequence | Key | Story title / scope | Review depth · tier · thinking | Numeric start-after at filing | Poller ID | State |
|---|---|---|---|---|---|---|
| 1 | S2-00 | Verify and document Storage Box stacking closure/geometry contract only | slim · medium · high | `[2978]` | — | NOT FILED |
| 2 | S2-01 | Optional standard magnet holes in 42 mm bin feet | standard · medium · medium | `[2978]` | — | NOT FILED |
| 3 | S2-03a | Plain lids for 21/42 mm Gridfinity bins | standard · high · medium | `[2978]` | — | NOT FILED |
| 4 | S2-03b | Hinged lids within Gridfinity bin envelope | standard · high · medium | `[2978]` (add S2-03a ID only if live file conflicts require serialization) | — | NOT FILED |
| 5 | S2-05 | Measured edge-shim retention for loose drawer baseplates | standard · medium · medium | `[2978]` | — | NOT FILED |
| 6 | S2-06 | Third-party bin placeholders, inventory/layout only | comprehensive · high · medium | `[2978]` | — | NOT FILED |
| 7* | S2-02 | Storage Box-on-Box stacking, both pitches, preservation of closures | comprehensive · high · high | `[2978, actual S2-00 ID]` | — | NOT FILED |
| 8 | S2-04 | Side Openings that preserve foot/rim and cell envelope | standard · high · medium | `[2978, actual S2-01 ID]` | — | NOT FILED |
| — | S2-07 | Screw holes — declined by Andrew 2026-11-12 | OUT OF SCOPE | **do not file** | — | DECLINED |

*Do **not** file S2-02 just because S2-00 was entered: wait for the S2-00 contract to be **completed, reviewed, and accepted**, then incorporate its actual resolved eligibility and clearance map in the S2-02 description/design. For S2-04, use the actual returned numeric S2-01 ID. The parallel stories are independent only after checking live changed-file ownership; if code paths would collide, file a safe additional numeric `start_after` gate before work starts and record the reason. Filing order is not necessarily work order.

The exact `submission_id` values proposed for idempotent filing are `gridfinity-s2-20261112-00`, `-01`, `-03a`, `-03b`, `-05`, `-06`, `-02`, `-04` appended to the same prefix. Before using them, check Poller for an already-filed Story by title/ID; never create a duplicate. When a submission succeeds, immediately replace **that row's** em dash with the **returned numeric Story ID** and change state to `SUBMITTED`. Record the date, result, and actual gates. If creation fails, leave state `NOT FILED`, record the error, and do not invent or reserve an ID.

### S2-00 — Storage Box stacking contract, specification only

**Problem:** Adding Gridfinity feet under a Storage Box and a receiving grid over its closed lid may collide with the newly completed hinge, latch and headroom geometry. It is unsafe to select lid eligibility or clearance by guesswork while coding the build.

**Deliverable:** A checked-in, versioned contract at `Future plans/Gridfinity-Storage-Box-Stacking-Contract.md` derived from current source, with no production geometry/UI changes. Trace `organizer_b4b` and verified construction Stories 2956–2959; document the latched 2.4 mm lid skin, selectable lid headroom 0.5/1.0/2.0 mm, latch detent 0.35/0.40/0.45 mm, two-latch threshold over 96 mm and screw-hinge geometry; independently confirm in live code, not just notes. Record for both 21/42 pitches: which *existing* box lid types may safely carry a top grid; top-label location prohibited while grid stacking is enabled (front labeling remains usable); lid grid must not alter skin/headroom underside measurement; hinge-and-grid sweep envelope, hinge screw bite, latch reach/clearance and foot landing; assembled exterior/stack heights, and detailed 1×1/multi-cell **physical mating and functional closure** test protocol. If hinge/grid coexistence cannot be established from geometry, list the specific unsupported configurations and further *fit* tests required; do not invent a workaround. Do not discuss or test weight capacity.

**Likely code to inspect (verify paths before writing spec):** `organizer_b4b/_geometry/_body.py`, `organizer_b4b/_geometry/_hinges.py`, `organizer_b4b/_geometry/_cutters.py`, `organizer_b4b/_plans.py`, `organizer_b4b/_constants.py`, `organizer_b4b/_outputs.py`, storage box settings/UI and lid assembly tests.

**Acceptance:** Contract includes explicit allowed/forbidden combinations, geometry and interference diagram or table, testable elevations and tolerances, preserving the construction-system latch and closure operation, plus a reviewed acceptance sign-off. The S2-02 build story remains unfiled until the resulting contract is accepted. **No production feature here.**

**Filing fields:** `type=task`; `review_depth=slim`; `tier=medium`; `thinking=high`; `tier_reason="A bounded source and geometry audit must settle lid, hinge and closure-clearance compatibility before the large Storage Box stacking implementation."`

### S2-01 — 42 mm-only optional magnet pockets in bin feet

**Problem:** Stage 1 Gridfinity bins locate in baseplates but cannot accept the standard 6×2 mm magnets.

**Deliverable:** Add `Magnet holes: None (default) / 6×2 mm` on ordinary **42 mm** Gridfinity bins only. Use four locations per 42 mm cell at nominal centers ±13 mm in X/Y around cell center (26 mm pattern), **but first cite the same named external reference family established for the Stage 1 foot**. Hole diameter **6.5 mm** and blind depth **2.4 mm** are *test starting values*, not final agreed tolerances; confirm with Andrew's actual printer/material/slicer and a fit/retention print. Prefer press-fit retention, allow optional adhesive, do not bore through the bottom into useful floor geometry and do not break minimum structural material thickness. Do not change outside foot profile or require support prints. Do not add magnet holes to 21 mm feet or either container floor. Preserve the exported bin shape when option is off.

**Likely touch points:** `organizer_features/gridfinity.py`, `organizer_engine/_specs.py`, `organizer_engine/_boxes.py`, web bin controls, save/load, AI docs and print/export tests.

**Acceptance:** Watertight 1×1 and 2×3 magnets-on/off specimens; confirm measured magnets and retention by physical test; unchanged third-party baseplate fit; no through-floor cuts; choice survives reload; no 21 mm or Wavefinity geometry regressions. Reference check and physical test are **part of this story**: no extra prerequisite story needed.

**Filing fields:** `type=feature`; `review_depth=standard`; `tier=medium`; `thinking=medium`; `tier_reason="An isolated optional 42 mm foot cutter and UI/save-load choice can reuse the Stage 1 foot geometry once dimensions are verified by print tests."`

### S2-02 — Stack complete Storage Boxes on Gridfinity feet and lid grids

**Problem:** Stage 1 stacks ordinary bins, but a complete Storage Box cannot yet seat on a standard Gridfinity plate or another closed box.

**Deliverable:** Follow the **accepted S2-00 contract exactly** on which box lid types are eligible for stacking; do not assume every hinged or latched lid is safe. For allowed 21 and 42 mm Gridfinity Storage Boxes, add feet under the body and a compatible receiving grid to the top of a closed lid. Keep the confirmed **2.4 mm latched lid skin** and 0.5/1.0/2.0 mm headroom semantics unchanged; neither upper grid nor bottom feet may interfere with hinge sweep, screw engagement, latch detents/reach, two-latch configuration or box closure. Disable/refuse a lid-top label in stacking configuration, retaining supported front label. Use proper foot/socket positioning, collision/height model and geometric fit tests. Do not discuss, test or publish a weight capacity.

**Likely touch points:** `organizer_b4b/_geometry/_body.py`, verified lid and hinge builders, `organizer_b4b/_plans.py`, storage-box form, lid/box outputs, shared grid helpers, tests. Verify file existence; do not assume a `_lid.py` module exists.

**Acceptance:** Both pitches, 1×1 and multi-cell box; box on bought plate, stacked closed boxes and loose bin atop box; opening and closing without latches/hinges fouling; accurate exterior and assembled height; physical fit and closure checks; watertight export; existing Wavefinity box latch/hinge/headroom/regression remains unchanged. If physical fit/closure proof is missing, mark the feature unverified and do not claim accepted.

**Filing fields:** `type=feature`; `review_depth=comprehensive`; `tier=high`; `thinking=high`; `tier_reason="Storage Box stacking alters integrated shell/lid/hinge/latch algorithms and geometric clearances, requiring coordinated architectural review and physical fit acceptance."`

### S2-03a — Plain lids for 21 and 42 mm Gridfinity bins

**Problem:** Stage 1 supplies the grid stacking lid but not the existing ordinary plain lid option.

**Deliverable:** Enable plain, non-stacking ordinary-bin lids on both 21/42 pitches while preserving the external Gridfinity cell footprint, correct closed/exterior height, seating of adjacent bins and no collision with the chosen stackable open-top rim. Keep one Lid selector: `Lid for stacking` is mutually exclusive with the ordinary plain lid, and the plain lid must **never** be represented as having a receiving grid or accepting another bin unless its geometry really permits it. If a rim is incompatible with the chosen plain lid, explicitly hide/refuse that combination. Retain Wavefinity lid behavior.

**Likely touch points:** `organizer_features/stack.py`, `organizer_engine/_specs.py` and `LidSpec`, bin editor UI, export and height/layout tests.

**Acceptance:** Both pitches, 1×1 and 2×3; lid closing and adjacent placement, correct height/footprint, watertight mesh, reload/AI parity, no unsupported stacking claim or Wavefinity regression.

**Filing fields:** `type=feature`; `review_depth=standard`; `tier=high`; `thinking=medium`; `tier_reason="Adding plain Gridfinity lids crosses shared rim, height and editor semantics but does not require redesigning the existing lid system."`

### S2-03b — Hinged lids for 21 and 42 mm Gridfinity bins

**Problem:** The existing ordinary-bin rear filament-pin hinged lid (nominal **1.75 mm** pin) is not validated within the much tighter Gridfinity footprint and neighbor clearance.

**Deliverable:** Assess hinge knuckles, pin channel, hinge line and full open/close swing against the **41.5 mm per-cell external allowance for a single 42 mm cell** (with equivalent independently verified 21 mm clearance) and against feet/rim/lids and immediately adjacent bins. Add an ordinary hinged lid on each pitch **only where it actually fits** within the entire permitted envelope and coexists with chosen rim and lid options. Stage 1 `Lid for stacking` and hinged lid are mutually exclusive; never claim stackable geometry from a hinged lid unless separately verified receiving geometry exists. Unsupported sizes or combinations must be disabled/refused in plain language, not silently reshaped. If a usable 21 mm or 42 mm hinged-lid design cannot satisfy the envelope, record a clear blocker and obtain Andrew's product decision instead of dropping the promised option silently.

**Likely touch points:** `organizer_features/stack.py`, the existing ordinary-bin hinge builder (locate rather than guess filename), `organizer_engine/_specs.py`, editor, collision/height engine, tests.

**Acceptance:** 1×1 and 2×3 on both pitches, neighbor clearance, hinge sweep and printability, correct height and option visibility/refusal, no over-cell projections, persisted/reloaded results and Wavefinity unchanged. Any non-fit case must be explicitly documented as unsupported.

**Filing fields:** `type=feature`; `review_depth=standard`; `tier=high`; `thinking=medium`; `tier_reason="A constrained geometric feasibility and implementation task must reconcile the filament hinge with tight Gridfinity neighboring-bin envelopes."`

### S2-04 — Side Openings on both Gridfinity pitches

**Problem:** Side Openings are still Wavefinity-only because openings can damage functional foot, top rim or wall structures.

**Deliverable:** Support existing Side Openings on flat 21/42 mm Gridfinity bins while preserving the complete outside Gridfinity envelope. **Reject at point of entry**, with plain text and no silent clipping or shrinking, any opening intersecting: (a) the **4.75 mm foot zone plus its base**, (b) the optional open-bin **stacking rim zone**, (c) foot-carrying corner-radius regions, or (d) a remaining wall segment thinner than the selected wall thickness. Maintain stack-rim support, third-party baseplate fit and standard bins' neighbor clearance. **Edge Mount stays excluded**; it projects beyond the cell and only Andrew may separately approve an inside-envelope replacement. Gate this story behind completed S2-01 to avoid shared gridfinity foot/wall cutter conflicts.

**Likely touch points:** `organizer_features/side_openings.py`, `organizer_engine/_boxes.py`, `organizer_features/gridfinity.py`, specs, editor and AI option docs, tests.

**Acceptance:** Maximal permitted opening on 1×1 and 2×3 at both pitches; mates bought reference baseplate, accepts another standard bin on optional upper rim, watertight, minimum wall and foot/rim strength remain; rejected intersection cases show a clear message and do not emit corrupt mesh; no Wavefinity regression.

**Filing fields:** `type=feature`; `review_depth=standard`; `tier=high`; `thinking=medium`; `tier_reason="Openings must validate multiple structural no-cut zones in shared bin geometry while preserving third-party mating and stack behavior."`

### S2-05 — Measured edge-shim retention for a loose Plain Drawer baseplate

**Problem:** In an ordinary real drawer, an externally supplied baseplate can slide because its actual footprint is smaller than the drawer cavity.

**Deliverable:** Generate **optional, measured edge shims** (simple printed strips) from user-entered **actual measured outside size of the purchased plate** and actual drawer inside size. Fill the existing hatched leftover gap with a user-chosen positioning arrangement and a verified **0.25–0.5 mm per-side working clearance starting range**, not a force fit. Ask for actual measured plate size when missing; never assume nominal Gridfinity size equals printed outside size, silently change the plate layout, or create a new baseplate. Output only the requested retaining shims; **no bin-to-bin spacer system**. Preserve Stage 1 measured seating-lift/stack-height model.

**Likely touch points:** `organizer_drawer/_spacers.py` or dedicated retainer builder, `web/drawer-panel.js`, Plain Drawer layout/print, sizing UI and tests.

**Acceptance:** Both pitches and non-grid-multiple real drawer sizes; measurable strips fit without obstructing plate/bin seating, dimensions honor actual plate size and clearance, missing measurements requested before print, save/reload and export appropriate, no baseplate output and no Wavefinity regression.

**Filing fields:** `type=feature`; `review_depth=standard`; `tier=medium`; `thinking=medium`; `tier_reason="Measured drawer/plate strips are straightforward geometry, with bounded UI measurement and output integration."`

### S2-06 — Third-party Gridfinity bin placeholders in layout

**Problem:** A Gridfinity Space cannot accurately represent a purchased or externally printed bin that has no Wavefinity design.

**Deliverable:** Add a **distinct inventory row kind** representing an external, **non-printable layout placeholder** with grid pitch 21 or 42, whole-cell width/depth, optional measured **actual exterior height** and name. **No design payload** is ever attached. It cannot enter bin editor, AI Design, STL/mesh generation or print/export, and cannot be converted into a design in place. Duplicate and Space copy preserve kind and grid; import into a mismatched Space is refused at UI/API/save boundary under existing cross-grid authority. Unknown height is a true unknown (never zero/default) displayed as **Not measured**: floor placement may show its footprint, but any vertical collision/stack calculation involving it is **unverified**, not passed; a stack above an unmeasured placeholder cannot be claimed valid. When measured height is supplied, apply ordinary vertical and same-grid layout rules. Distinguish external placeholder visually and in any output lists.

**Likely touch points:** `organizer_inventory/_rows.py`, `web/drawer-model.js`, `web/drawer-view.js`, storage layout UI/save/import/API, tests.

**Acceptance:** 1×1 and 2×3 placeholders in both pitches, overlap and known-height rejection, unknown-height unverified state, duplicate/copy/import and mismatch refusal, unaltered save/load, no accidental print/export/AI path, no real-bin regression.

**Filing fields:** `type=feature`; `review_depth=comprehensive`; `tier=high`; `thinking=medium`; `tier_reason="A distinct persisted inventory kind affects shared data structures, import/save boundaries, layout collision and downstream print eligibility."`

### S2-07 — Screw holes: expressly declined

Andrew's latest in-repository ruling dated 2026-11-12 **declined screw holes in 42 mm feet**. S2-07 is **not** a proposed story and must **not** be filed. No screw holes in Gridfinity bins or container floors are within this plan.

### Filing protocol for the next LLM (operational checklist)

1. Read this complete plan, preserved Velexa Q1–Q8 answers and the current repository implementation. Check Poller **Story 2978** and its actual physical 21/42 mm sign-off. If missing, **stop without filing Stage 2**; the immediate next step is to finish/record Stage 1 acceptance.
2. If Andrew has requested Stage 2 submission and the sign-off is present, read the current Poller Story list to detect already-submitted Stage 2 work; do not duplicate any story. Verify repository file paths and that new Stage 1 code actually provides the claimed prerequisites. Record any changed file/API names in each submitted description without changing approved behavior.
3. File in the ledger's sequence. Use `application_id="wavefinity"`, `target_repo="Wavefinity"`, the ledger's `type`, `review_depth`, `tier`, `thinking`, and exact one-sentence `tier_reason`; `description` must include the *complete* problem, deliverable, constraints, file paths (verified), acceptance, physical-test requirement, and owner authority. Do **not** pass `andrew_instruction` on standard/comprehensive/slim filings (the Poller endpoint rejects it); that field is for direct or debate. For `start_after`, pass the numeric IDs exactly; do not pass textual keys or future guessed IDs.
4. Use the listed stable `submission_id` per key, and do not reuse the same ID for different descriptions. On success, record Poller's actual returned ID, stage, numeric `start_after`, submission date, and `SUBMITTED` in this table **immediately**. On error, leave `NOT FILED` and write the error alongside the key. If a Story must be changed after filing, use Poller's proper review/contract workflow rather than filing a duplicate.
5. S2-02 is **special**: S2-00 must be submitted, completed, and its contract reviewed/accepted before filing S2-02. Copy the accepted contract's eligible lid types, forbidden cases and clearance map into S2-02; only then use `start_after: [2978, S2-00 numeric ID]`. S2-04 must use `start_after: [2978, S2-01 numeric ID]`. S2-07 is declined and must never be filed from this plan.
6. Each completed geometry Story must show reproducible mesh tests, both-pitch compatibility (where applicable), no Wavefinity regression, and physical print acceptance. If tests are not yet performed, label that part unverified and do not claim release-ready fit. The agent should not claim an entire Stage is released merely because every Poller story is `done`.

### Stage 2 non-goals and owner-only decisions

- **Not in the agreed Stage 2:** automatic printer-bed split/join, standalone baseplate creation, Gridfinity Edge Mount, 21 mm magnets, container floor magnets or screws, any redesign of settled Stage 1 dimension entry.
- **Decisions closed by Andrew (2026-11-12):** screw holes are declined and out of scope; weight capacity is never discussed, tested or documented. No further decision is needed to prepare S2-00..S2-06 with those exclusions.
- Velexa's complete answers remain below as the historical review record. Andrew's later Q8 response **supersedes earlier Q2 suggestions to discuss or test weight capacity**. Its no-screw and no-weight decisions are integrated above. If a future answer conflicts with this accepted section, record and resolve the difference before creating conflicting stories.

---

## Velexa review record — answered 2026-11-12 (preserved verbatim)

**Historical record only:** These questions and Velexa's original responses are preserved for traceability. Their agreed technical edits have been applied to the authoritative Stage 2 filing plan above. Do not treat the old proposed S2 labels or draft status language inside the responses as live filing instructions.

### Q1 — Magnet-hole geometry and retention

Can you verify the actual 42 mm Gridfinity magnetic foot reference (nominal 6×2 magnet, hole diameter/depth, 26 mm center spacing, minimum wall/floor thickness, whether glue/press fit and through-bottom relief are expected)? Are the suggested 6.5×2.4 mm cavities right for Wavefinity's print orientation, or should they be test-derived? Does S2-01 need any separate compatibility or slicer tests?

**Velexa response — CHANGE:** The pattern figures are the right starting point and they are traceable: Fable's plan (gridfable.md, geometry notes) specifies magnet 6 x 2 mm, four per 42 mm cell on a 26 mm square (that is, hole centres 13 mm either side of the cell centre), hole 6.5 mm across, 2.4 mm deep. But no named external reference has verified them yet, and the landed Stage 1 specification (gridfinity-stage1-spec.md, section 3) deliberately lists magnet/screw fit as a (confirm) item. Exact edit to S2-01: its first step names and cites the magnet reference it follows (the same Gridfinity reference family the Stage 1 foot profile was taken from), and the 6.5 x 2.4 mm cavity is recorded as a test-derived starting value to be confirmed on Andrew's printer, material and slicer — the same discipline as every other fit dimension in Stage 1 — not as a settled fact. Retention: press fit, adhesive optional; no through-bottom relief and no hole that breaks the bin floor above the foot (the foot profile is 4.75 mm tall; the 2.4 mm cavity must leave the floor structure intact, and the story's acceptance already requires no unusable/through holes). No separate slicer or compatibility story is needed: the magnet fit/retention test print already in S2-01's acceptance covers it. Settled and not reopened: magnets in 42 mm bin feet only, none in 21 mm feet (the pattern does not fit the 21 mm foot), none in container floors (Andrew's rule).

### Q2 — Whole Storage Box stacking and current closure hardware

Trace the **current** `organizer_b4b` lid, hinge, latch, headroom and hardware paths. Does Gridfinity grid-on-lid plus bottom feet physically coexist with them on both pitches? What must be explicitly forbidden or recomputed to avoid regression (e.g. labels, lid type, latch clearance, opening swing and load-bearing assumptions)? Is S2-02 best as one comprehensive story, or should it have a contract-only prerequisite?

**Velexa response — CHANGE (add a contract-only prerequisite):** I traced the current closure hardware through the landed construction package (Stories 2956-2960, all complete) and the Stage 1 spec's code inventory. The facts S2-02 must respect: the latched lid's plate is a fixed 2.4 mm skin (2956); lid head-room is a shown choice (0.5 / 1.0 / 2.0 mm) measuring the whole-inside gap to the lid underside (2957); latch detent is 0.35 / 0.40 / 0.45 mm with the two-latch default set by interior width over 96 mm (2958); the box hinges are screw hinges (2959); lid label location defaults to the lid top (gridfinity-stage1-spec.md, section 5). Coexistence findings: (1) a receiving grid on the lid top collides with a top label — a stacking-enabled box must not offer the top label location; (2) grid features added on top of the latched lid must not change the 2.4 mm plate or the head-room measurement, which is taken to the lid underside; (3) a hinged lid swings itself and anything on it through an arc — whether the grid and an upper box's feet clear that swing, and whether hinge screw bite survives grid cells at the hinge edge, is an open geometry question, not a detail; (4) the upper box's feet must not land where the lower box's latches swing or grip; (5) weight is not part of this work at all: Andrew ruled on 2026-11-12 that weight is never discussed — no capacity is claimed, tested, or documented for stacked boxes. Because (3) is an empirical geometry question, exact edit: file a slim contract-only prerequisite story first (the same role Story 2967 played for Stage 1) that settles lid-type eligibility for stacking (which lid types may carry the grid), the label rule, the latch/feet clearance map, and the assembled-height model. S2-02 itself stays one comprehensive build story, filed after that prerequisite is agreed.

### Q3 — Plain versus hinged Gridfinity bin lids

Which existing ordinary-bin lid variants actually work with the 21/42 mm footprint, optional open-top stacking rim and neighboring bins? Can plain and hinged lids share one coherent S2-03 story, or should they be split? Confirm actual files and the display/disable rules for unsupported combinations.

**Velexa response — CHANGE (split S2-03 in two):** The two lid kinds have different risk. A plain lid is a plate inside the footprint; nothing moves and nothing protrudes — low risk on both pitches. The ordinary-bin hinged lid is a different mechanism from the Storage Box hinges: it uses a 1.75 mm filament pin along the rear wall, and its knuckles must be verified inside the 41.5 mm cell allowance with a neighbour seated, against the optional stacking rim, and against the foot of a bin above when the lid is closed. A hinge problem should not park the plain lid. Exact edits: S2-03 becomes S2-03a — plain lids on Gridfinity bins, both pitches (standard / high / medium as proposed); S2-03b — hinged lid on Gridfinity bins (standard / high / medium), whose design first names the envelope check (hinge line, pin channel, swing) against the cell allowance and the rim, and records the lid as ineligible rather than forcing geometry if it cannot stay inside. Combination rules for both: a lid choice that cannot apply is not offered (the app's existing convention — compare the latch choice, which exists only for the latched lid type); 'Lid for stacking' (Stage 1) and a plain or hinged lid are mutually exclusive choices in the one Lid control; no lid may be labelled stack-compatible without the receiving geometry from Stage 1's grid lid or the open-top rim. Files confirmed from the Stage 1 inventory: organizer_features/stack.py for lid/rim behaviour, the hinge construction beside the existing bin lid code, organizer_engine/_specs.py LidSpec.

### Q4 — Side Openings and Edge Mount

Can Side Openings be safely supported on a standard flat Gridfinity sidewall without exceeding cell envelope or weakening the stacking rim/feet? Specify invalid intersections, minimum wall constraints and fit tests. Confirm Edge Mount remains excluded unless a new inside-envelope solution is expressly approved.

**Velexa response — AGREE, with the constraint list written into S2-04:** Flat Gridfinity walls make openings geometrically simpler than on wavy Wavefinity walls, and the story's shape is right. Exact additions to S2-04's intended behaviour: an opening is refused in place, in plain words, when it would intersect (a) the foot zone — the 4.75 mm foot profile plus the base above it; (b) the stacking-rim zone at the top of a Stackable bin; (c) the corner regions carrying the foot corner radii; or (d) any wall section that would leave less than the bin's chosen wall thickness standing. Refusal, never silent clipping or shrinking of the opening. Fit tests to add to acceptance: with a maximum-size opening present, the bin's foot still mates the reference plate and a reference bin still seats on its rim, both pitches, 1x1 and 2x3. Edge Mount: confirmed excluded — it projects beyond the cell allowance; only an inside-envelope design Andrew expressly approves could reopen it, and none is proposed here.

### Q5 — Loose baseplate retention in real drawers

Given Stage 1's `None` floor clearance and measured seated-lift model, what is the smallest physically reliable retention feature (corner stops, edge shims, modular wedges, or something else)? Should it be one story or separable geometry/UI stages? Confirm no accidental duplicate baseplate generation.

**Velexa response — AGREE, with the retention design named:** The smallest physically reliable feature is measured edge shims: simple printed strips generated from the drawer's actual interior size and the plate's actual measured outside size, placed in the leftover margins Stage 1 already computes and hatches, filling the gap so the plate is located and cannot wander. They are spacers for the plate, not bin-to-bin spacers, and they carry a small working clearance per side in line with the Stage 1 None-floor clearance testing (0.25-0.5 mm), never a force fit. One story is right: the geometry is plain strips, and the real work is the measured-plate entry and placement in the existing Plain Drawer layout. Confirmed: this story prints retaining pieces only — Wavefinity still does not generate baseplates; when the user has not measured their plate, the flow asks for the measurement instead of assuming a nominal size (S2-05's acceptance already says this; keep it as a hard requirement, not a fallback).

### Q6 — Third-party placeholder representation

What persisted shape and UI should represent third-party Gridfinity bins so they never masquerade as printable designs? How should unknown height be modeled and displayed, and what happens on duplicate/copy/import and stacking? Does this cross enough core data structures to justify comprehensive review as suggested?

**Velexa response — AGREE (comprehensive is justified):** This crosses inventory rows (organizer_inventory/_rows.py), layout collision and stack rules, save/load and import, and the Space-grid authority from Story 2968, so comprehensive review is earned, not ceremony. Persisted shape, to write into S2-06: a row of a distinct placeholder kind carrying grid pitch, whole-cell width and depth, an optional measured exterior height, and a name — and deliberately NO design payload, so a placeholder can never enter the bin editor, print, export, or AI Design paths; it is not a design and must not be convertible into one in place. Unknown height is stored as unknown (not zero, not a default): any height check touching an unknown-height placeholder reports unverified rather than passing, and the layout shows the placeholder in its distinct style with the height shown as not measured wherever heights appear. Duplicate and Space copy preserve the record and its pitch unchanged; import into a Space of a different grid is refused under the same cross-grid rule as real bins. Stacking: a placeholder may be shown in a stack only with its measured height; with unknown height it sits at floor level in the layout and any stack above it is reported unverified.

### Q7 — Stage 2 grouping, filing and dependencies

Do the proposed S2-01..S2-06 groups minimize file ownership conflicts and review load, given the actual current repository? Are any additional baseline regression or physical-test stories required before the implementation stories? Propose concrete changes to sequence/gates with reasons. Do not invent Poller IDs or submit stories while reviewing.

**Velexa response — CHANGE (one added gate; the rest agreed):** The grouping is sound and the filing discipline in the ledger (real returned IDs only, manual sign-off recorded in S1-12's record rather than inferred from Story 2978's completion) is exactly right — keep it. One file-ownership collision to gate: S2-01 and S2-04 both cut into the Gridfinity foot and wall geometry (organizer_features/gridfinity.py and the mesh construction in organizer_engine/_boxes.py). File S2-04 with start_after on S2-01's real returned ID so the two never edit the foot cutters concurrently. S2-02 files only after its Q2 prerequisite spec is agreed (that gate replaces nothing else in its row). S2-03a and S2-03b are independent of each other once Stage 1 is accepted; S2-05 and S2-06 touch separate areas (drawer retention; inventory/layout records) and can proceed in parallel with the others. No additional baseline-regression or physical-test stories are needed: Story 2978's acceptance record is the baseline, and each Stage 2 story already carries its own physical-fit acceptance under the release policy. Nothing in this section is filed until Stage 1 physical sign-off is recorded — agreed without change.

### Q8 — Owner decisions versus technical clarifications

Identify **only** remaining decisions that genuinely require Andrew (rather than implementation verification). In particular, screw holes are optional and **not approved** for filing; list any other decision you cannot settle from the existing plan. Avoid asking again about both grids, unit entry, the Stage 1 rim/lid, or one-grid-per-Space: Andrew has already settled those.

**Velexa response — NEEDS ANDREW (both decisions answered by Andrew, 2026-11-12):** (1) Screw holes in 42 mm bin feet (S2-07): Andrew decided — declined. Screw holes are out; no story will be filed. (2) Weight: Andrew ruled — weight is never discussed. No load capacity is claimed, tested, or documented anywhere in this work; the topic is closed. Everything else in Q1-Q7 is verification against named references and test prints, or reviewer judgment inside the agreed plan. Explicitly NOT reopened, per Andrew's settled rulings: magnets exist in 42 mm bin feet only (none in 21 mm feet, none in containers); Edge Mount stays excluded unless Andrew affirmatively raises it; both grids, unit entry, the Stage 1 rim and grid lid, and one grid per Space are settled. Andrew's physical print sign-off remains the Stage 1 release gate (Story 2978's record) — a gate, not a new question.

### Review summary (Velexa fills)

- **Review date / commit:** 2026-11-12, Velexa, responding to the plan as committed in 07a44a31 and ebdc76b8.
- **Accepted Stage 2 story set:** S2-01 (magnet pockets, with the Q1 reference-and-confirm edit), S2-02 (Storage Box stacking, filed only after a new contract-only prerequisite spec — see Q2), S2-03 split into S2-03a plain lids and S2-03b hinged lid (Q3), S2-04 (Side Openings, with the Q4 constraint list and gated behind S2-01 — Q7), S2-05 (baseplate retention by measured edge shims, Q5), S2-06 (third-party placeholders, comprehensive, Q6). S2-07 screw holes: declined by Andrew on 2026-11-12 — will not be filed.
- **Recommended changes:** Q1 — magnet cavity figures are test-confirmed starting values from a named reference, not settled fact. Q2 — add a slim prerequisite spec story for Storage Box stacking (lid eligibility, label rule, latch/feet clearances, assembled-height model) before the comprehensive build. Q3 — split plain and hinged lids. Q4 — write the refusal constraints (foot zone, rim zone, corners, wall minimum) into S2-04. Q7 — S2-04 starts after S2-01 (shared foot/wall geometry files).
- **Explicit Andrew questions:** Both answered by Andrew on 2026-11-12: (1) screw holes in 42 mm bin feet — declined, S2-07 will not be filed; (2) weight — never discussed: no capacity claimed, tested, or documented. Recorded in Q8.
- **Can another LLM file the approved stories without guessing?** YES for S2-01, S2-03a, S2-03b, S2-04, S2-05 and S2-06, once Stage 1 physical sign-off is recorded in Story 2978's acceptance record; S2-02 after its prerequisite spec story is agreed; S2-07 NO — declined by Andrew; it will not be filed.
- **Stage 2 filing authorization:** `NOT GIVEN BY THIS DOCUMENT`

