# Wavefinity Print-and-Assembly Fit Audit

**What is audited:** whether parts that are meant to go together actually go together once printed — bins in boxes and drawers, rows of bins, stacked bins, lids (resting, snap, hinged), storage box latch / handle / detents, bin connectors, inserts, dividers, spacers.

**Method:** build both mating parts with the app's own build code at sizes that are supposed to match, then measure clearance or interference in millimeters (through the full travel for moving parts). Fits are judged with a realistic print tolerance of about +/-0.2 mm: a fit that only works at exact nominal size is a finding. Each finding says whether it was **PROVEN** (both parts built and measured) or **SUSPECTED** (from reading the code).

**Severity:**
- **Won't go together** — parts cannot be assembled.
- **Lid won't close / strikes in motion** — assembles, but a lid or moving part is blocked.
- **Won't snap / loose** — assembles but does not hold or rattles.
- **Doesn't line up** — visible misalignment, step, or lean.
- **Cosmetic** — slivers, hairs, thin walls; works but looks wrong.

**Findings so far: 20**

---

## Findings

### 1. ~~Storage Box code does not load on committed `main`~~ — FIXED in `7fe4419` (rechecked: imports cleanly)
- **Parts:** every Storage Box part (body, lid, latches, handle).
- **Trigger:** any Storage Box, any size, on commit `28caa8a`.
- **Measured:** importing `organizer_b4b` fails: `ImportError: cannot import name 'B4B_LATCH_TWO_ABOVE_FIELD_X' from 'organizer_b4b._constants'`. The constant lives in `organizer_engine/_specs.py:270`, but `organizer_b4b/__init__.py:101` imports it from `._constants`.
- **Owner sees:** Storage Box generate/preview fails; nothing to print.
- **Severity:** Won't go together (nothing is produced).
- **Proof:** PROVEN (clean `git archive HEAD` copy, import fails). Uncommitted edits in the working copy at audit time may be fixing this.
- **Fix direction:** import the constant from `organizer_engine` (or move it into `_constants.py`) and add an import smoke test.

### 2. Unit-matched bin jams at the four corners of a Storage Box
- **Parts:** ordinary bin inside Storage Box body (the headline 7 x 7 test).
- **Trigger:** any bin sized unit-for-unit to the box field. Measured at 7x7, 4x10 and 14x20 units; identical at every size (wall 2.0, base 2.0, height 30).
- **Measured:** along the straight wavy sides the gap is a steady 0.25 mm per side (good). But at each corner the bin's outer corner stands **0.36 mm outside** the box's inner wall (0.19 mm² of overlap per corner, centred about 0.5 mm in from each corner tip, e.g. at (24.48, -24.01) on a 49 mm field). The box rounds its inside corner tighter-in than the bin rounds its outside corner. With +0.2 mm print growth that becomes ~0.55 mm of interference at all four corners.
- **Owner sees:** the bin will not drop in; it has to be forced, or sits up on its corners. Same for any corner bin in a full layout.
- **Severity:** Won't go together.
- **Proof:** PROVEN — bin outer outline (`wavy_outer_polygon`) and box cavity outline (`b4b_layout().inner_mating_polygon`, the exact polygon the body extrudes) built at matched sizes and intersected. Re-confirmed in 3D: a 7x3-unit bin (height 30) seated against the back wall of a 7x7x40 box (wall 1.6) overlaps the built box body by **9.55 mm³**, all at the two back corners.
- **Fix direction:** build the box's inside corner as the bin's outside corner offset outward by the side gap (same corner inset and fillet radius + gap), rather than its own `_wall_points` inset + 0.6 fillet; add a test that the unit-matched bin outline is fully inside the cavity with ≥0.25 mm everywhere. Storage Drawers already do this right: their cavity (`wavy_rect_cavity(field/2 + gap/2, …, wall=0)`) leaves 0.171 mm at every point including corners — reuse that outline for the box.

### 3. Storage Box lid skirt hangs only 0.15 mm above the bin rims
- **Parts:** Storage Box lid (side locating skirt) over unit-matched bins of full box height.
- **Trigger:** every Storage Box with a bin of the full "maximum bin height", every snugness setting (0.5 / 1.0 / 2.0 mm). Checked at 7x7x30, 7x7x60, 4x10x100, 14x20x40.
- **Measured:** the skirt's depth is computed as headroom − 0.15, so its bottom always lands exactly 0.15 mm above a full-height bin's rim (e.g. 7x7x30, standard: bin top 32.00, skirt bottom 32.15, lid underside 33.00). In plan the 2 mm skirt sits directly over the perimeter bins' wall tops (397 mm² of overlap on a 7x7 box). A bin printed just 0.15 mm tall — normal for a first layer squish or a tall print — lifts the lid.
- **Owner sees:** lid rocks or stands slightly proud; latches feel tight or won't hook. The "Standard" headroom of 1.0 mm is really 0.15 mm wherever the skirt is.
- **Severity:** Lid won't close (marginal; lid sits proud).
- **Proof:** PROVEN by building box and lid datums (`_skirt_lap`, `_skirt_polygons`, `b4b_lid_underside_z`) against the bin outline; heights checked numerically, not by full mesh boolean.
- **Tight snugness (0.5 mm):** the skirt is only **0.35 mm** tall (0.5 − 0.15). That is under two 0.2 mm layers, so the slicer either drops it, leaving the lid unlocated, or rounds it up to 0.4 mm, which leaves it 0.10 mm above the bins. Either way it is a sliver, not a locator.
- **Fix direction:** keep at least ~0.4–0.5 mm under the skirt (lap = headroom − 0.5, drop the skirt when that is below the minimum), or move the skirt outboard of the bins' wall tops.

### 4. A "30 mm" lidded bin is really 31 mm, so it won't fit a 30 mm Storage Box
- **Parts:** ordinary bin with its own lid (default lid; plain or flip), inside a Storage Box of matching height.
- **Trigger:** any lidded bin whose lid is stackable (the default). Measured 7x7x30 and 7x7x60 units/mm, plain and flip.
- **Measured:** `stack_summary` gives module height 30 but closed height **31.0** (60 → 61.0). The extra 1.0 mm is the stacking foot under the base. A 7x7x30 Storage Box promises "Maximum bin height: 30 mm"; its lid skirt sits only 0.15 mm above 30 (finding 3), so the bin stands 0.85 mm into it.
- **Owner sees:** inside the app the generator refuses the bin for that box (overheight gate uses the 31 mm figure); printed standalone and dropped in, the box lid won't close. The number he typed (30) is not the height he gets.
- **Severity:** Lid won't close / confusing promise.
- **Proof:** PROVEN for the heights (built `stack_summary` / lid mesh: lid top 31.00 above a 28.55 rim on a 30 bin). The box-lid clash is from datums, not a mesh boolean.
- **Fix direction:** either keep the foot inside the typed height (as direct-stack mode already does), or show "prints 31 mm tall — needs a 31 mm box" wherever the bin height is entered and when matching bins to a box.

### 5. Handle is offered on 13- and 14-unit-wide Storage Boxes, then the box refuses to build
- **Parts:** Storage Box body + folding handle (carry stop).
- **Trigger:** box width 91 mm or 98 mm (13 or 14 units), any depth tested (49, 63, 98), height 40, wall 2.0, handle on, screw or piano hinge. 84 and 105–133 mm build fine.
- **Measured:** `b4b_handle_eligibility` says yes, but `validate_b4b_design` fails with `the handle stop has no cleared landing over the wall trough`. The handle's stop lands on a wave trough at these two widths.
- **Owner sees:** handle checkbox is allowed, then generate errors out; no box.
- **Severity:** Won't go together (nothing produced at those widths).
- **Proof:** PROVEN by calling the eligibility check and the full design validator at each width.
- **Fix direction:** move the stop landing to the nearest wave crest (or widen it to span a full wave, 3.5 mm), or make eligibility run the same landing check so the option is greyed out instead of failing late.

### 6. Handle grazes the case at its carry stop on every buildable Storage Box (the "handle strikes the box" bug, back again)
- **Parts:** Storage Box body + folding handle, swung to its 95° carry stop.
- **Trigger:** **every** Storage Box with a handle that gets past the basic checks. Swept widths 84–238 mm in 14 mm steps × depth 63 and 140 × wall 1.6 / 2.4 / 3.0, height 60, auto latches: **69 of 69 buildable combinations fail**. Clearance at the 95° stop by width (identical at all three walls): 84 → 0.000, 98 (deep) → 0.000, 112 → 0.243 (0.000 at 140 deep), 126 → 0.299, 140 → 0.247, 154 → 0.146, 168 → 0.093, 182 → 0.289, 196 → 0.267, 210–238 → 0.256 mm. At 84 mm and 98 x 140 the handle **touches** the case (0.000).
- **Measured:** the app's own deep motion check (`validate_b4b_design(deep=True)`, run at export) fails, e.g. `the handle has only 0.247 mm clearance at -95.0000 degrees (needs 0.30 mm); its ends must not graze the case`. The shallow check the UI uses passes, so the option looks fine until export.
- **Owner sees:** export fails; or, if the check is bypassed, the handle ends rub the box when it is swung up to carry. A 0.25 mm gap closes once the print grows by ±0.2 mm.
- **Severity:** Strikes in motion (and blocks export).
- **Proof:** PROVEN by the app's own swept-clearance check on built meshes.
- **Fix direction:** clearance does not change with wall thickness, so the problem is in the handle's own plan (end shape vs. the wave at the stop angle), and it varies with width as the arm ends land on different wave phases. Raise the end clearance to ≥0.5 mm (≥0.30 after ±0.2 tolerance), e.g. trim the arm-end corners or add stop-angle relief to the case. Run the swept check inside `b4b_handle_eligibility` so the UI can never offer a handle that export refuses.

### 7. Dividers make uneven compartments: end cells wider than the middle ones, and slightly off-centre
- **Parts:** ordinary bin with a fused Divider (count along X); the same builder makes Storage Box dividers.
- **Trigger:** any divider count ≥ 2. Measured on a 0.8 mm wall, height 30 bin, by probing the built solid at 3 mm and 15 mm above the floor:
  - 49 mm bin, 2 dividers: cells **14.87 / 13.57 / 15.16** mm
  - 70 mm, 3 dividers: 16.33 / 15.03 / 15.03 / 16.62
  - 84 mm, 5 dividers: 13.12 / 11.82 ×4 / 13.41
  - 35 mm, 4 dividers: 6.0 / 4.7 ×3 / 6.3 (end cells 28–34 % bigger)
  - 1 divider, 49 mm: 22.45 / 22.75 (0.3 mm off-centre)
  - Storage Box 7x7, 2 dividers (from the solids): 15.05 / 12.74 / 15.05 mm. A 2-unit bin (13.75 mm wide) fits the end cells but **not the middle one**.
- **Cause (from the numbers):** dividers are spaced at equal centre-to-centre pitch, so each end cell gains half a divider thickness (1.6 mm wall → +0.8 … +1.3 mm). The whole set is also shifted 0.15 mm toward −X (left cell always 0.29 mm narrower than right).
- **Owner sees:** compartments visibly unequal; in a Storage Box, unit bins fit some cells and not others.
- **Severity:** Doesn't line up (Won't go together for unit bins in a Storage Box's middle cells).
- **Proof:** PROVEN — built bin + divider solids, measured clear widths along a probe line.
- **Fix direction:** space dividers by equal clear cell width, measured from the real inner wall faces at the wave mean; fix the 0.15 mm shift (likely wave phase or half the mating gap applied on one side). For a Storage Box, offer divider positions on whole units plus seam gaps so unit bins fit every cell.

### 8. Wide Storage Boxes: handle plus latches collide on the front wall, but the handle is still offered
- **Parts:** Storage Box front wall: handle mounts and latch mounts.
- **Trigger:** width ≥ 252 mm (36 units), handle on, latches Auto or 2 (Auto picks 2 above 96 mm). Any depth or wall tested.
- **Measured:** refused with `the latch and handle roots would merge into one bracket on the front wall (closest approach -0.20 mm …)` at 252 mm, and −2.34 mm (wall 1.6) or −0.72 mm (wall 2.4 / 3.0) from 266 to 350 mm. Meanwhile `b4b_handle_eligibility` says the handle is fine. With 1 latch these sizes pass the basic check, then fail the motion check (finding 6).
- **Owner sees:** picks a big box, handle and default latches; generate refuses. The only way out is dropping to 1 latch, which the app doesn't suggest.
- **Severity:** Won't go together (nothing produced).
- **Proof:** PROVEN by the app's own validator.
- **Fix direction:** on wide boxes, move the two latches outboard of the handle mounts (they are clearly placed relative to the handle's fixed grip maximum of 105 mm, not the box width), or make eligibility check the latch-root spacing and grey out the conflicting choice.

### 9. "Number of latches: None" is offered but every box set to None is refused
- **Parts:** Storage Box latched lid with latches set to None.
- **Trigger:** latch count `0` (shown as **None** in `web/storage-box-form.js:130`), any size: tested 49, 98, 140, 203, 350 mm wide, with and without handle.
- **Measured:** every case refused: `the latch pivot screw did not resolve to an allowed M2 length` (M3 above 120 mm). With zero latches there is no latch screw, so the screw-length check should be skipped.
- **Owner sees:** chooses None (for example a hinged lid that just rests closed) and generate fails with a confusing screw message.
- **Severity:** Won't go together (nothing produced).
- **Proof:** PROVEN by the app's own validator.
- **Fix direction:** skip latch screw resolution when the resolved latch count is 0, or remove None from the menu.

### 10. Rigid drawer spacers have about 0.125 mm of play, not the 0.40 mm the code means to give
- **Parts:** rigid edge spacer (left, right or back) between a drawer wall and the bins beside it.
- **Trigger:** any rigid spacer, either because Flexible is off or because the gap is under 9 mm or the contact under 6 mm (it then falls back to rigid automatically). All bin sizes and wall thicknesses.
- **Measured:** the gap is measured from the drawer wall to the bins' **grid line** (`organizer_drawer/_spacers.py` placements: `gap = ox + edge*step`). The printed part is a flat block `gap − 0.40` wide (`RIGID_SPACER_CLEARANCE_MM`). But every bin's wavy outer face stands **0.275 mm past its grid line** at each crest (measured: `wavy_outer_polygon` bounds − half field = 0.275 for 7–98 mm bins, walls 0.4 and 0.8). So real total play is 0.40 − 0.275 = **0.125 mm**. With ±0.2 mm print growth on the spacer, it jams.
- **Owner sees:** a "loose" rigid spacer has to be pressed in hard, or pushes the bin row sideways.
- **Severity:** Won't go together (marginal) / forced fit.
- **Proof:** PROVEN for the numbers (bin outline built; spacer width read from the spacer builder's `shape_box(relief/2, w − relief/2)`). Spacer and bin were not assembled as meshes.
- **Fix direction:** measure the gap to the bin's crest line (grid + 0.275), or set rigid clearance to 0.40 + 0.275. The flexible spacer already uses a bin-facing wave, so this is the rigid path only.

### 11. Stacked Storage Boxes: locator pegs bottom out in the recess, so the upper box can sit on four peg tips
- **Parts:** four loose stacking pegs (pressed into the lower box's lid sockets) and the recesses under the upper box.
- **Trigger:** Storage Box stacking on, any size. Built at 98 x 63 x 40, base 3.0, 1 latch.
- **Measured:** lid top z = 47.00; peg tips at 49.00; upper box recess floor at 47.00 + 2.00 (`B4B_STACK_RECESS_DEPTH`) = **49.00**. Zero axial clearance. Upper box seated on the lid: overlap 0.000 with lid and pegs; 0.1 mm lower collides with both. Any peg not pressed fully home (the socket is a 0.08 mm radial press fit, overlap 7.9 mm³), or printed 0.1 mm long, holds the upper box up on its peg tips.
- **Owner sees:** the top box rocks or sits proud of the lid, and doesn't seat flat.
- **Severity:** Doesn't line up / stack leans.
- **Proof:** PROVEN by building body, lid and pegs and stacking a second body.
- **Also affects Storage Drawers cabinets** (from reading the code): `organizer_storage/drawer_geometry.py` reuses the same constants. The peg is `B4B_STACK_RECESS_DEPTH + B4B_STACK_SOCKET_DEPTH` = 3.6 mm, the top socket is 1.6 mm and the base recess 2.0 mm, so stacked cabinets have the same zero spare depth.
- **Fix direction:** make the recess 0.4–0.5 mm deeper than the peg's exposed length (e.g. recess 2.5 with the peg still at 2.0), keeping the 0.8 mm floor skin rule. Change it once in `organizer_b4b/_constants.py` and both products get it.

### 12. Front label plate has zero side clearance in its channel and won't slide in
- **Parts:** Storage Box front label plate (separate print) and the top-loading channel frame on the box front.
- **Trigger:** label location Front, flat or wavy style. Measured at 98x63x40, 140x63x60, 350x63x100 (wall 1.6, 1 latch).
- **Measured** (plate placed at the app's own seated position, then nudged until it hits the body):
  - left/right play: **0.000 / 0.000 mm** at every size and style. The plate edges touch the channel sides.
  - front/back: 0.25 mm out, 0.25 mm in; but only **0.041 mm** inward on the 98 mm box.
  - down: 0.000 (resting on the bottom stop, as intended).
  - Seated overlap 0.000, so it is a zero-gap fit, not interference.
- **Owner sees:** the printed plate is a hair too wide (plus ±0.2 mm growth) and won't drop into the channel, or has to be sanded.
- **Severity:** Won't go together.
- **Proof:** PROVEN — `b4b_front_label_geometry` plate and `b4b_body_with_features` body built; clearances found by stepping the plate along each axis.
- **Fix direction:** cut the channel slots 0.3 mm wider per side than the plate (or shrink the plate width by 0.6 mm), and give ≥0.25 mm front/back on small boxes too.

### 13. Removable inserts crash into the bin's Inside Grip (lift grabber) ledges
- **Parts:** ordinary bin with Inside Grip on, plus a removable ("separate") insert, here a 2x2 divider insert.
- **Trigger:** any insert whose walls reach the grabber band (the grabbers sit 8 mm below the rim). The app accepts the insert heights below; it only caps divider height for the connector band, not for grabbers.
- **Measured** (insert built by `make_fitted_insert`, placed on the bin floor, intersected with the built bin):
  - 49x49x30, grips medium on sides (grip z 15–22): insert top 20.4 → **14.2 mm³** collision; top 17.4 → 2.4 mm³; top 11.4 → 0.
  - 49x49x40, grips large, all sides (z 23–32): top 30.4 → **56.3 mm³**; top 27.4 → 26.9 mm³.
  - 49x49x40, grips XL: top 30.4 → **96.5 mm³**; top 27.4 → 65.5 mm³.
- **Owner sees:** the insert won't drop past the grip ledges; it sits on them, proud of the floor.
- **Severity:** Won't go together.
- **Proof:** PROVEN by building both parts and intersecting.
- **Fix direction:** in `make_fitted_insert` / `insert_footprint`, also subtract the grabber solids (plus 0.4 mm) from the insert's clip volume, or cap insert height below the grabbers' bottom; or warn that Inside Grip and a removable insert conflict.

### 14. Bin-to-bin connector can't seat on a wall that carries a rim label ledge
- **Parts:** side connector clip + a bin with a rim-level Text label (top label ledge) on the wall it shares with its neighbour.
- **Trigger:** rim label on the left or right (or front/back) wall of a bin whose neighbour shares that wall. Built at 21x42x30 and 49x49x40, ledge on the shared side.
- **Measured:** clip seated at the seam: **57.05 mm³** of collision with the labelled bin (the clip arm drives into the 7 mm label ledge), 0.000 with the plain neighbour. Clip length 12 mm; the ledge runs most of the wall, so there is nowhere else on that seam to put it.
- **Owner sees:** the clip printed for that seam won't push down; the label ledge blocks it.
- **Severity:** Won't go together.
- **Proof:** PROVEN for the clash (both parts built). Connector planning (`organizer_drawer/_report.py::_connector_eligible`) checks Storage Box, stacking, lids and spacers but **not** rim labels, so the app still counts and prints a clip for that seam (from reading the code).
- **Fix direction:** skip (or shorten) connectors on seams where either bin has a rim label ledge on that wall, and tell the user; or keep the ledge clear of a 12 mm connector zone at the seam centre.

### 15. (SUSPECTED) Connector planning ignores side openings on the shared wall
- **Parts:** side connector + a bin with a Side Opening on the wall it shares.
- **Trigger:** a side opening (especially the open-top style, which cuts through the rim) on a wall that a neighbour shares, at a seam long enough to get a connector.
- **Evidence:** `_connector_eligible` and `_connectors` in `organizer_drawer/_report.py` never read `side_openings`. The clip's lock depends on the wall bumps 4 mm below the rim, and an opening removes that wall over its width (corner margin only 3.5 mm). On a short seam the remaining wall may be shorter than the 12 mm clip.
- **Owner sees (expected):** a connector printed for a seam where it has nothing to grip, or that sits over the opening and won't lock.
- **Severity:** Won't snap (suspected).
- **Proof:** SUSPECTED from reading the code; not built.
- **Fix direction:** when planning connectors, subtract opening spans from each seam's usable length and require ≥ clip length of intact wall.

### 16. Flip-lid bins can't open when a same-height bin, or the Storage Box wall, is right behind them
- **Parts:** ordinary bin with Flip lid (filament-pin piano hinge), and whatever stands behind its back wall: a neighbour bin on the 7 mm grid, or the Storage Box back wall.
- **Trigger:** any flip-lid bin with a neighbour behind it that is as tall or taller. Clear if the neighbour is ≥10 mm shorter. Every size tested: 21x21x30, 49x49x60, 84x35x60, 49x21x15.
- **Measured** (lid swung about its own hinge axis; neighbour = same bin shifted one bin-depth back, bare body with no lid):
  - 21x21x30: lid digs into the neighbour 0.23 / 1.12 / 2.19 / 5.35 / 2.29 / 0.37 mm³ at 30 / 40 / 45 / 60 / 90 / 105°.
  - 49x49x60: 0.63 / 3.08 / 6.04 / **14.81** / 6.33 / 1.01 mm³.
  - 84x35x60: 1.20 / 5.83 / 11.42 / **27.96** / 11.97 / 1.92 mm³.
  - The knuckle corner sits 2.07 mm in front of the back face (axis y 14.91, lid back 16.98, neighbour crest 17.23) and swings out past it as the lid opens.
  - Inside a Storage Box (7x7x40 box, 7x3x30 flip bin against the back wall): **7.7 mm³ already at 15°**, 20.4 at 45°, and **711.6 mm³ at the 105° rest**. The box wall stands taller than the bin, so the lid can't get anywhere near open.
  - Adding a knob or pull doesn't change it; first contact is still 45° on 84x35x60.
- **Owner sees:** in a packed drawer, or at the back of a Storage Box, the flip lid only opens partway before it jams on the neighbour or the box wall.
- **Severity:** Strikes in motion / lid won't open.
- **Proof:** PROVEN by building bin, lid and neighbour (or box body) and sweeping the lid.
- **Fix direction:** the swept corner must stay inside the bin's own back crest. Move the axis forward by the swing radius minus the knuckle half-size (about 1 mm), or round the lid's back-top corner to the axis radius. Also warn when a flip-lid bin is placed against a taller neighbour or a box wall, since the lid must rise past vertical to rest open.

### 17. (SUSPECTED) Standard pegboard adapter's hook may not clear a 1/4-inch-thick board
- **Parts:** pegboard board adapter (`make_board_adapter`, standard 25.4 mm pegboard) on a real board.
- **Trigger:** "Standard Pegboard" with 6.35 mm (1/4 in) holes. That hole size usually comes on **1/4 in (6.35 mm) thick** hardboard.
- **Evidence** (from the builder's dimensions): the pegs are Ø5.3 mm (0.5 mm radial clearance in the 6.35 hole, fine) and 25.4 mm apart (correct). The adapter's back face is at y = 0, the pegs run to y = −7.65, and the locking hook block spans **y −8.5 to −5.5**. So the hook's front face is only 5.5 mm behind the board face. On a 6.35 mm board it would be 0.85 mm inside the board and can't drop behind it. On 1/8 in (3.2 mm) board it clears by 2.3 mm.
- **Owner sees (expected):** on thick pegboard the adapter won't hook in or sit flush.
- **Severity:** Won't go together (suspected; depends on board thickness).
- **Proof:** SUSPECTED. Dimensions read from code, not assembled against a board model, and the board thickness the design targets isn't stated in the code.
- **Fix direction:** put the hook's front face at least 6.6 mm behind the board face (pegs ≥ 9 mm long), or offer a board-thickness choice.

### 18. Interior parts are allowed right up to the lid plug, with 0.00 mm left under it
- **Parts:** bin lid (its plug drops 3 mm into the mouth) + a fused interior part (here a free-standing divider; the same limit applies to every interior part, via the "keep interior parts below …" rule).
- **Trigger:** interior part at the tallest height the app accepts. Measured on 49x49x30 and 84x49x60, lid Thin and Thick, fit Standard and Loose (0.1 mm height steps).
- **Measured:** Thin lid: tallest accepted part top **25.55**, plug bottom **25.55**, gap **0.00 mm** (60 mm bin: 55.55 / 55.55). Thick lid: 0.05 mm gap. No overlap at nominal size, so it is a zero-gap fit: any +0.1 mm in the part's height, or a stringy top, props the lid up.
- **Owner sees:** with a tall divider, the lid won't push fully home or rocks on the divider tops.
- **Severity:** Lid won't close (marginal).
- **Proof:** PROVEN — app's own `build_features` accepted the height; lid built; gap measured.
- **Comparison:** direct stacking applies the same rule correctly. The tallest accepted part stops **1.00 mm** below the upper bin's skirt (49x49x30: top 27.00, skirt 28.00), while stackable lids leave 0.00. So the lid path is the one missing a margin.
- **Fix direction:** cap interior parts at plug bottom − 0.5 mm (the message's "below 25.6" currently equals the plug bottom rounded up).

### 19. Some ordinary bin sizes with lids crash while building (no file at all)
- **Parts:** ordinary bin body with a lid (lid, flip lid or snap lid).
- **Trigger:** found by a sweep of 2,592 builds: every width and depth 7–84 mm in 7 mm steps × heights 15 / 30 / 60 × six lid/stack modes. Thirteen builds crash with an internal error (not a friendly refusal):
  - **77 x 7 mm (11 x 1 units)**, stackable lid, flip lid or snap lid, at every height 15 / 30 / 60: `stack body cuts did not leave one printable solid` (9 cases).
  - **49 x 42 / 49 / 56 / 63 mm, height 30**, flip lid set to *not* stackable: `stack snap detents did not join the body` (4 cases). The same sizes build fine with a stackable flip lid, or at height 60.
- **Owner sees:** generate fails with a technical message for an ordinary-looking size; nothing to print.
- **Severity:** Won't go together (nothing produced).
- **Proof:** PROVEN by running the app's own builders (`stack_effective_box` → `make_box`, then `make_lid_parts`). The other 2,444 builds succeeded and 135 got proper refusals (too narrow or too shallow for a flip lid).
- **Fix direction:** the stacking-lid cutters and detent unions depend on mesh booleans that split or fail to touch at certain sizes. Add a small overlap (≥0.05 mm) where detents join the wall, look at why a 77 x 7 lid bin's stack cut separates a sliver, and add these exact sizes as regression tests.

### 20. SUSPECTED: Storage Drawers keyhole screw heads end up inside the cabinet, 0.5 mm from drawer travel
- **Parts:** Storage Drawers cabinet rear panel with Wall mounting = Keyholes, and the drawer behind it.
- **Trigger:** any cabinet with keyholes on.
- **Numbers (from code):** the keyhole is cut straight through the 4.0 mm rear reinforcement (head hole 10.0 mm, slot 5.2 mm, 7.0 mm slide). There is no recessed pocket for the screw head. After hanging, the screw head sits on the *inside* face of the panel. The code only keeps that inside face 0.5 mm clear of drawer travel. A normal pan or round screw head is about 2.5–3.5 mm tall.
- **Owner sees:** cabinet hangs fine, but the rearmost drawer hits the screw heads and will not close fully, or scrapes.
- **Severity:** Annoying to dangerous for the drawer fit; not measured on a built mesh.
- **Fix direction:** either give the head a recessed pocket in the panel (keyhole with an undercut), or keep at least head height + 0.5 mm (about 4 mm) between the inside face and drawer travel. Tell the owner the screw must stand out about 4 mm from the wall.

---

## Closing: checked and clean, and not reached (second pass)

All checks ran on a clean copy of `origin/main` at `7fe4419`. Finding 1 was found on `28caa8a` and is fixed in `7fe4419`. "PROVEN" means both parts were built with the app's own builders and measured; "SUSPECTED" means from reading the code.

**Checked and clean (PROVEN):**
- **Bins in Storage Drawers:** 1x1, 7x7, 4x10, 14x20 units: 0.171 mm everywhere, corners included.
- **Rows, grids and junctions of bins:** 7x1 and 7x7 grids of 1x1, 2x2 four-way corners, T-junctions (even/odd), pinwheel, an 8-bin mixed 7x7 layout. Every seam 0.171 mm, no overlap, no build-up. A bin turned 90° or 180° is the identical outline.
- **Bin walls 0.4 / 0.8 / 2.4 mm** at 14x14x10, 49x49x30, 49x49x200: nothing pokes out of the outer face (lock bumps stay inside).
- **Bin lids closed** (21x21x30, 49x49x30, 84x35x60): plain, Tight, Loose, snap, flip, flip+stackable all 0 overlap.
- **Snap lid engages:** lifting a seated snap lid 0.3 mm hits the catch (0.8–3.1 mm³); plain lids lock from 0.6 mm.
- **Flip lid swing on its own bin:** 0–105° clear in 5° steps; strikes past 110°, so the stop works. (Neighbours behind are a problem: finding 16.)
- **Direct stacking:** seats at the stated pitch, bottoms out solidly; interior parts keep 1.0 mm under the upper skirt.
- **Lid stacking:** upper bin rests on a single datum (the recess floor), no rocking.
- **Bin-to-bin connectors:** free when seated, lock from 0.2 mm of lift, at walls 0.4–2.4 and with 50→20 mm height differences.
- **Removable and cartridge inserts:** 0.55 mm / 1.9–2.0 mm all round (but see finding 13 with Inside Grip).
- **Storage Box hinges and latches, deep motion check:** 180 combinations at standard snugness (widths 49–343, heights 16/40/120, screw/piano, 1/2 latches, stacking on/off) plus 192 more at Tight 0.5 and Loose 2.0 snugness (widths 49–350, heights 16/60): all 372 pass.
- **Storage Box hinge or lid vs. full-height bins:** screw and piano hinges, snugness 0.5/1/2, no intrusion (apart from the corner jam, finding 2).
- **Handle rest dots:** centred on the arm centrelines (x = ±half pivot span); pocket at the arm-to-corner tangent, under 0.1 mm off.
- **Storage Drawers slide:** each drawer slides 0–45 mm out without rubbing (one small catch bump near 30 mm, by design); about 0.4 mm side and vertical play.
- **Storage Drawers height:** the gap really is the promised usable height, and the layout already warns 2 mm below it.
- **Storage Box gates:** overheight uses the real closed height; Inside Grip and Side Openings refused on Storage Box; edge-mount reach reserved in whole cells.
- **Base Trim:** inner outline matches the drawer one; dovetail keys have 0.2 mm all round.
- **Storage Box top label:** flush inlay, kept clear of stacking pegs.

**Borderline, not logged as findings:**
- The system-wide seam is 0.171–0.25 mm per side, at or under ±0.2 mm print tolerance. It is treated as owner-calibrated.
- A 40 mm "usable" drawer leaves 0 mm under the drawer above for a 40 mm bin. The layout's 2 mm warning covers it, but the form's "usable height" wording overstates it.

**Not reached:**
- Pegboard adapters on a real board model (finding 17 is from dimensions only).
- Snap fingers' flex force; filament-pin threading; Storage Drawers keyhole wall mounts; flexible spacer squeeze.
- A full print-flaw scan (slivers, sub-0.4 mm walls) beyond the specific cases above.

### Third pass (stopped at 10:00 as asked)
- **Clean:** wider bin sweep, walls 0.4 and 2.4 mm, heights 12 and 45 mm, six lid/stack modes. 1,428 of 6,144 planned builds ran before the stop: 993 built, 435 got proper refusals, and none crashed.
- **Not reached:** the other 4,716 sweep builds (mostly the wider sizes), flexible spacer squeeze, pegboard against a modelled board, snap finger flex, filament pin threading, a full thin-sliver scan. Keyhole drawer clash (#20) is read from code only, not built.
