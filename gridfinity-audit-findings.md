# Gridfinity audit findings — 2026-11-12

Independent audit of the Gridfinity programme (Stage 1 Stories 2967–2977 and the Stage 2 stories that followed).

- **Code audited:** `happydadto5/Wavefinity`, branch `main`, commit `baf2844eb45ecf5f806b9bea9787ec0f458be4cb`. Fetch before acting; a local checkout may be behind.
- **Intent of record:** `Future plans/Gridfinity-implementation-master-plan.md`, `gridfinity-stage1-spec.md`, README UI rules, `features.md`.
- **Method:** code and records traced; bin, lid and magnet meshes built from the real builders and sliced at fixed heights. No browser session and no prints.
- **Audit only:** nothing was changed, filed or fixed by the audit.

## Notes for whoever files stories from this

- **Do G-1 first.** G-2 (loose lid) uses the same rim numbers and should follow it.
- **G-6 is an owner decision, not a coder job.** No baseplate output is Andrew's recorded ruling.
- **G-12 and G-13 are INFERRED** (read, not run). Confirm each before fixing.
- Product rules that still apply: no weight or load claims; no shims (spacers are the only gap fill); Storage Box hinges use M2/M3 screws and the regular bin hinged lid uses a 1.75 mm filament pin; verification is by Andrew's own prints, not test suites.

## Findings

```
FINDING G-1
SEVERITY: critical
WHERE: organizer_features/gridfinity.py (_RIM_42, RIM_PROFILES, rim_socket_cutter, rim_cutter, SEAT_DESCENT, assembled_stack_height); organizer_features/stack.py (_make_grid_lid, stack_step_depth, stack_lid_rise); organizer_engine/_boxes.py make_box. User surface: "Stackable" on any Gridfinity bin and "Lid for stacking", both pitches; every stack-height readout.
ENTRY PATH / REPRO STATE: origin/main baf2844. Built 1x1 bins, Z 42, Stackable, walls 0.8/1.2/1.6, at 42 mm and 21 mm, plus a "Lid for stacking", through make_box / make_lid_parts, then sliced the meshes at fixed heights.
EXPECTED vs OBSERVED: Spec section 1 gives the receiving rim with Z measured UP from the nominal rim: opening 36.3 at the bottom, 37.7 through the straight band, 40.3 at the top (41.5 theoretical tip), so a foot nests its full depth with 0.25 mm side clearance and the lip stands above the 7 mm-unit height. The code reads the same table as "depth BELOW the rim" and builds it upside-down: narrowest (36.3) at the top, widest (40.3) at the bottom, all inside the typed height.
EVIDENCE: gridfinity.py comment "(depth below the rim, opening width, corner radius)" and rim_socket_cutter `(opening_z - band_depth, ...) for ... in reversed(bands)`. Measured open bin, 42 mm, Z 42: mouth at the top is just the plain cavity (39.9 / 39.1 / 38.3 mm for walls 0.8 / 1.2 / 1.6) with a shallow groove 3.7 mm down — no lip at all. On 21 mm with a 0.8 wall the cutter removes nothing, so Stackable equals Not Stackable. Measured stacking lid: ridge opening 36.4 at the top, 37.7 mid, 40.1 at the plate — an undercut, so a standard foot (35.6 bottom, 37.2 at 0.8 mm) enters only 0.35 mm. SEAT_DESCENT = 0.35 / 0.25 encodes that shallow landing as the design. On the open bin a foot actually sinks about 3.2–3.95 mm (until it wedges on the wall's top inner edge), while assembled_stack_height reports only 0.35 less than the two heights.
WHY IT MATTERS: Stacking is a core Gridfinity promise. Lidded stacks rest on a 0.35 mm ledge (bins slide off); open-bin stacks wedge with no standard lip, and the reported stack height is wrong by about 3 mm, which feeds drawer-height checks. A bought bin will not seat on our rim the standard way. Stackable bin heights also do not match the standard (lip belongs above the unit height).
FIX DIRECTION: Build the receiving profile right way up (narrow at the bottom, wide at the top) as a real lip, decide and record whether the lip sits above the unit height as the reference does, and recompute seat descent, lid rise and every stack-height readout from the corrected profile on both pitches.
STATUS: VERIFIED (code traced and meshes measured). A print of one Stackable 1x1 with a bought bin set on top would show it by eye.

FINDING G-2
SEVERITY: serious
WHERE: organizer_features/stack.py _make_grid_lid; user surface: "Gridfinity Lid" and "Lid for stacking", both pitches.
ENTRY PATH / REPRO STATE: 1x1 bin, Z 42, wall 1.2, lid on; built lid and body, sliced both.
EXPECTED vs OBSERVED: A lid should locate on its bin. The lid's locating skirt is sized to the rim's narrowest band (36.3 mm footprint less 0.25 fit), but a lidded body never gets a rim (make_box cuts the rim only when there is no lid), so the skirt sits in a plain cavity far wider than itself.
EVIDENCE: Measured 42 mm lid skirt outer width 35.8; body cavity 39.1 (wall 1.2) or 39.9 (wall 0.8): 1.65–2.05 mm of slide per side. 21 mm: skirt 14.6 in an 18.1 cavity, 1.75 per side.
WHY IT MATTERS: The lid slides about 2 mm any way, overhanging the 0.25 mm neighbour gap; a bin stacked on it moves with it.
FIX DIRECTION: Size the skirt to the body's actual mouth (cavity less fit) when no rim is present.
STATUS: VERIFIED (meshes measured). A printed lid on its bin shows the slop by hand.

FINDING G-3
SEVERITY: serious
WHERE: organizer_inventory/_space.py normalise_space_definition (drawer kind); wavefinity_web_impl/_designs/_layout.py create/configure payloads; web/index.html Plain Drawer and Storage Box setup; web/spaces/10-storage-box-structural.js; layout note from web/drawer-model.js DL.heightFit.
ENTRY PATH / REPRO STATE: New Plain Drawer Space, Grid = Gridfinity 42 mm; also new Storage Box, Floor = None.
EXPECTED vs OBSERVED: Plan S1-07 promises a measured baseplate seated-lift field for user-supplied plates. Plain Drawer has no field, and the server drops the value if sent. Storage Box (None) has no control either; the code comment says the form "has no control for it". Only Storage Drawers has the field.
EVIDENCE: normalise_space_definition({kind: drawer, grid: gridfinity, seated_lift_mm: 4.65}) returns a record with no lift. Plain Drawer markup has only width, depth, height, Grid. The layout then shows "Height fit is not verified: no seated lift is recorded for this Space's baseplate" forever.
WHY IT MATTERS: The honest "unverified" note is right, but the user has no way to clear it, and heights are computed with zero lift, so a stack that looks fine can foul the drawer above once a real plate is in.
FIX DIRECTION: Give Plain Drawer and Storage Box (None) the same lift field Storage Drawers has, stored and read through the one lift accessor; allow editing it later since it is a measurement, not a creation choice.
STATUS: VERIFIED (records and markup traced).

FINDING G-4
SEVERITY: serious
WHERE: organizer_app_impl/_design_io.py design_from_dict; organizer_engine/_specs.py BoxSpec; organizer_features/gridfinity.py cell_counts; organizer_app_impl/_filenames.py grid_filename_segment. Surfaces: opening a saved or imported design, AI "apply", any API caller.
ENTRY PATH / REPRO STATE: Fed the loader a design with grid = gridfinity and widths 49, 63, 21 and 14 mm; grid = gridfinity_half with 28 and 14 mm.
EXPECTED vs OBSERVED: Width and depth must be whole cells of the pitch; a unit fraction is refused, never snapped. The loader only checks the old 7 mm rule, so all of these load. Geometry then silently rounds to whole cells.
EVIDENCE: 49 x 42 loads and names its file "Box 49 x 42 x 42 Gridfinity 42mm 1.16667x1u.3mf" while the body builds as one 41.5 mm cell; 63 mm builds as two cells (83.5 mm); 21 and 14 mm load, then fail later at build. The editor's own parser does enforce whole cells, so the gap is every path that skips the editor field.
WHY IT MATTERS: A part whose record, filename and printed size disagree is exactly the fit-claim conflation the plan forbids; the AI prompt asks for whole cells but nothing enforces it on the answer.
FIX DIRECTION: Refuse off-pitch width/depth at the loader for Gridfinity grids, naming the nearest whole-cell sizes.
STATUS: VERIFIED for the loader. INFERRED that the AI apply path reaches it unguarded (it runs the same validation); pasting an AI answer with a 49 mm width would confirm.

FINDING G-5
SEVERITY: serious
WHERE: web/app/10-draft-update-commit.js commitBinGrid; starter from wavefinity_web_impl/_runtime.py default_design. Surface: bin editor Grid select, No-Space bin.
ENTRY PATH / REPRO STATE: Blank start, untouched starter bin (14 x 42 x 40 mm), choose Grid = Gridfinity 42 mm (or half).
EXPECTED vs OBSERVED: A first-time user picks Gridfinity and gets a Gridfinity bin. Instead the switch is refused: width 14 is under one cell and height 40 is not whole 7 mm units, so errors appear under the fields and the select snaps back to Wavefinity.
EVIDENCE: commitBinGrid re-parses each current size on the new grid and refuses on any change or range error; the starter fails on X and Z for 42 mm and on X and Z for 21 mm.
WHY IT MATTERS: The very first Gridfinity step fails unless the user knows to retype sizes on the Wavefinity grid first. That is tribal knowledge.
FIX DIRECTION: When the bin is an unedited starter, switch grid by loading that grid's own starter (for example 1x1 cell, 6 units); keep the refusal for bins the user has actually sized.
STATUS: VERIFIED in code. Not exercised in a browser.

FINDING G-6
SEVERITY: serious
WHERE: Product scope (master plan Stage 2 exclusions); Plain Drawer Gridfinity Spaces; Floor = None containers.
ENTRY PATH / REPRO STATE: Blank-start user with a real drawer chooses Gridfinity.
EXPECTED vs OBSERVED: Yardstick: blank start to a working, fitting result. The app makes bins but no baseplate; a Plain Drawer has nothing for the feet to sit in unless the user makes a plate elsewhere. The plan records this as an owner exclusion.
EVIDENCE: Plan "standalone baseplate creation" listed under non-goals; socket geometry already exists (socket_cutter, floor_pocket_cutter) but is only used inside container floors.
WHY IT MATTERS: Every other Gridfinity generator leads with baseplates; without one, drawer space management stops halfway.
FIX DIRECTION: Owner decision. If reopened, reuse the existing socket field to output plates sized to the drawer's cell capacity, with spacers taking the leftover strip.
STATUS: VERIFIED as absent; recorded exclusion, raised only against the yardstick.

FINDING G-7
SEVERITY: serious
WHERE: web/ help and welcome pages, Brochure.md, features.md.
ENTRY PATH / REPRO STATE: Searched every user-facing page for "Gridfinity".
EXPECTED vs OBSERVED: A person arriving for Gridfinity should see it offered and explained. It appears only as options in three Grid selects and a few field notes; no welcome, help or brochure text mentions it, and Floor, None and seated lift are explained only inside the cabinet form. Third-party stand-ins (Story 3010) are absent from features.md.
EVIDENCE: Only code files and index.html option tags match; no help page does. "stand-in" has zero hits in features.md and ai-features.md.
WHY IT MATTERS: Discovery and first use depend on guessing.
FIX DIRECTION: Add a short Gridfinity start path to the welcome/help text and document stand-ins in features.md.
STATUS: VERIFIED by search.

FINDING G-8
SEVERITY: minor
WHERE: web/app/09-draft-sizing-helpers.js parseCellDimension, parseVerticalDimension. Surface: bin Height and Width/Depth fields on Gridfinity.
ENTRY PATH / REPRO STATE: Gridfinity bin; type a bare height of 9 or 12; type width 30 on the 42 mm grid.
EXPECTED vs OBSERVED: Plan: Gridfinity height always uses 7 mm units. The code applies the "under the pitch means units" rule to height too, so 6 is 6 units but 9 is read as 9 mm (error "Use at least 14 mm") and 12 silently becomes 14 mm. Width 30 on 42 mm is read as 30 cells and answers "Use at least 42 mm and at most 336 mm" without saying why.
EVIDENCE: Same regex and threshold path for both axes; height pitch passed as 7.
WHY IT MATTERS: Tall bins (7 units and up) are common; the user must know to type "9u".
FIX DIRECTION: Treat bare Gridfinity heights as units throughout, and make range errors say how the number was read.
STATUS: VERIFIED in code; intent for heights of 7 and above is INFERRED from the plan wording.

FINDING G-9
SEVERITY: minor
WHERE: organizer_features/gridfinity.py messages; organizer_engine/_specs.py BoxSpec; wavefinity_web_impl/_ai.py prompt; ai-features.md; features.md; web/drawer-model.js DL.heightFit.
ENTRY PATH / REPRO STATE: Triggered refusals through the loader; read prompt and docs.
EXPECTED vs OBSERVED: One plain name per thing. Refusals print internal keys ("a gridfinity bin's Z must be...", "for gridfinity_half"); a 7 mm tall Gridfinity bin is refused with "to fit the lock bump", a Wavefinity part it does not have; minimum_height_units says one unit is legal but the real floor is two (14 mm). The AI prompt and docs carry "Stage 1", "S1-13 gate" and "Story 3009". "Verified" means "lift recorded" in the layout note but "print-confirmed" elsewhere.
EVIDENCE: Probe output for Z 40 and Z 7; _ai.py prompt lines; DL.heightFit versus container_floor_record height_fit_verified.
WHY IT MATTERS: Bolt-on feel; users and the outside AI see project jargon.
FIX DIRECTION: Use grid_label everywhere, give Gridfinity its own short-bin message stating 14 mm, strip stage and story codes from user and AI text, and reserve "verified" for one meaning.
STATUS: VERIFIED.

FINDING G-10
SEVERITY: minor
WHERE: organizer_app_impl/_filenames.py lid_filename.
ENTRY PATH / REPRO STATE: Export a Gridfinity bin with the plain Gridfinity Lid.
EXPECTED vs OBSERVED: A name that says what the part is. Any lid that is not a stacking lid is named "Handled Lid ...", yet handles are refused on Gridfinity.
EVIDENCE: `'Stack Lid' if lid_receives_stack(box) else 'Handled Lid'`, then the Gridfinity segment is appended.
WHY IT MATTERS: Export naming contradicts the form's "Gridfinity Lid".
FIX DIRECTION: Name it by the form's own word for that lid.
STATUS: VERIFIED by reading; not exported.

FINDING G-11
SEVERITY: minor
WHERE: organizer_inventory/_space.py normalise_space_definition (surface, pegboard branches).
ENTRY PATH / REPRO STATE: Sent a Surface Space definition with grid = gridfinity straight to the normaliser.
EXPECTED vs OBSERVED: Grid choice exists only for No-Space bins, Plain Drawers, Storage Box and Storage Drawers. A Surface with a Gridfinity grid is accepted and stored; Pegboard takes the same path.
EVIDENCE: Probe returned a Surface record with "grid": "gridfinity".
WHY IT MATTERS: The UI offers no such select, so only API or hand-edited files reach it, but the Space is the grid authority and its bins would inherit a grid that kind cannot lay out.
FIX DIRECTION: Refuse a non-Wavefinity grid on kinds that do not offer one.
STATUS: VERIFIED for Surface; INFERRED for Pegboard.

FINDING G-12
SEVERITY: minor
WHERE: web/app/01-runtime-state.js (~line 918) and web/app/03-history-utils-catalog.js (~line 67).
ENTRY PATH / REPRO STATE: Storage Drawers Space, Gridfinity, Floor = None, lift left blank; add a new bin.
EXPECTED vs OBSERVED: Lift comes from the one accessor and an unknown lift is never treated as known. These two places read `space.seated_lift_mm ?? 0` directly and size the new bin to the full drawer height.
EVIDENCE: Both lines shown in the trace; DL.baseLift is the accessor used elsewhere.
WHY IT MATTERS: The starter bin is offered at a height that will not fit once the plate is in.
FIX DIRECTION: Route both through the shared accessor and leave one height unit spare, or say so, while lift is unverified.
STATUS: INFERRED (read, not run).

FINDING G-13
SEVERITY: minor
WHERE: web/index.html portable-stacking; web/storage-box-form.js.
ENTRY PATH / REPRO STATE: New Storage Box, Grid = Gridfinity.
EXPECTED vs OBSERVED: Gridfinity box-on-box stacking is unfiled Stage 2 work. The existing "Stackable" choice stays offered on a Gridfinity box and builds the older Wavefinity-style recess.
EVIDENCE: storage-box-form.js picks container_floor_stacking_build_mm for a Gridfinity box when stacking is on.
WHY IT MATTERS: A Gridfinity user will read "Stackable" as Gridfinity feet and a grid on the lid.
FIX DIRECTION: Label what it does on Gridfinity boxes, or hide it until the real feature lands.
STATUS: INFERRED; geometry of that combination not built.
```

## Claim-versus-evidence matrix

| Claim | Evidence | Verdict |
|---|---|---|
| 42 mm foot matches the reference | Mesh: 35.6 / 37.2 / 41.5 at Z 0 / 0.8–2.6 / 4.75; 2x3 is 83.5 x 125.5 | Proven |
| 21 mm foot is its own profile | Mesh: 14.6 / 16.2 / 20.5 on ±6.5 centres | Proven |
| Heights are whole 7 mm units | Z 40 refused with nearest values | Proven; 1-unit claim false (G-9) |
| Stackable rim receives a standard foot | Meshes show inverted profile | Disproven (G-1) |
| Lid locates and stacks | 1.65–2 mm slop; 0.35 mm seat | Disproven (G-1, G-2) |
| Space grid immutable | Update to another grid refused; omitted key keeps saved grid; legacy Space stays Wavefinity | Proven |
| Floor fixed at creation | _refuse_floor_change, retain_storage_drawers_fields | Proven by reading |
| Cross-grid bin refused, both grids named | cross_grid_message on save, duplicate, generate, print, expand, resume, Space copy, AI | Proven on server; drop path partial |
| Unknown lift reads unverified | Layout note, cabinet summary, headroom record | Proven; cannot be recorded on two Space kinds (G-3) |
| Nominal grid and printed cavity kept apart | container_floor_record; cabinet summary | Proven for cabinets; Storage Box readout partial |
| Filenames carry pitch and units | "Gridfinity 42mm 1x1u" | Proven; fractional units possible (G-4) |
| Oversize part refused naming part and axis | require_export_fit on the written 3MF | Proven |
| No printer set means fit unverified | fit_status, component_fit | Proven |
| Magnets 42 mm only | Refused on 21 mm; holes at ±13, 6.5 wide, 2.4 deep, blind | Proven |
| Legacy designs unchanged | No-grid design loads as Wavefinity, same sizes and filename | Proven for the record; geometry not diffed |

## Coverage map

- **P0 bases, heights, magnets:** checked.
- **P0 rim and lids:** checked.
- **P0 grid immutability:** checked on the server; UI partial.
- **P0 floors and lift:** partial. Records and readouts checked; container floor meshes not built.
- **P0 cross-grid refusals:** server checked; drag-and-drop partial; hosted mode with no inventory text not checked.
- **P0 fit honesty, filenames, printer fit:** checked; combined-plate packing read only.
- **P1 blank-start journey:** traced in code, not driven in a browser.
- **P1 legacy Space journey:** partial. Record round-trip only.
- **P1 Space kinds:** No-Space, Plain Drawer and Storage Box checked; Storage Drawers partial.
- **P1 AI Design:** partial. Prompt and context read; option-by-option match not completed.
- **P2 cohesion:** partial.

## Severity summary

- **Critical:** G-1.
- **Serious:** G-2, G-3, G-4, G-5, G-6, G-7.
- **Minor:** G-8, G-9, G-10, G-11, G-12, G-13.

## Areas checked and clean

- Foot profiles at both pitches, body outline, corner radius, one 0.5 mm perimeter gap per bin.
- Magnet pockets: position, size, depth, 42 mm only, watertight single solid on 2x3.
- Space grid immutability and legacy default to Wavefinity.
- Server cross-grid refusal wording and coverage of the listed write routes.
- Printer-fit refusal and the "fit unverified" state.
- Storage Box whole-cell field rule with the nearest legal size named.
- Hinged lid refused on both pitches; Edge Mount refused on Gridfinity.
- Cabinet defaults: 42 mm usable height on both Gridfinity pitches.

## Blind spots

- No browser session: every UI statement is from reading code.
- No prints: all physical fit stays unconfirmed, as the spec itself says.
- Container floor and drawer meshes, side openings, plate packing and stand-in layout were not built or measured.
- Hosted-mode guards when the browser sends no inventory text.
- Wavefinity geometry was not diffed against older output.
- Poller story records were not read; only the repository.

## Top 3 product gaps

1. **Stacking does not work as Gridfinity** (G-1, G-2): rim upside-down, lids loose, stack heights wrong.
2. **No baseplate and no way to record lift in a plain drawer** (G-6, G-3): space management stops at the drawer floor.
3. **The blank start trips on step one and nothing explains Gridfinity** (G-5, G-7, G-8).
