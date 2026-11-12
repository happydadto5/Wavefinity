# Gridfinity Storage Box Stacking Contract (S2-00)

| | |
|---|---|
| **Contract version** | 1.0 (revision r1) |
| **Story** | 3006 - Gridfinity Stage 2, S2-00: Storage Box stacking contract (specification only) |
| **Status** | SUBMITTED FOR REVIEW - not accepted. The build story S2-02 is filed only after this contract is completed, reviewed and accepted. |
| **Source pin** | `31dc4d6a962208aad11a98ab3e0ee233359dbbcb` (all line numbers below are at this commit) |
| **Date read** | 2026-11-12 |
| **Changes** | This document only. No production geometry, UI, README or features change in this story. |

## 0. How to read this document

* **The live code governs.** Every figure below was read from the source at the pin above in the same session. Where a figure in the brief, a plan note or a code comment disagrees with the code, the code value is recorded and the disagreement is listed in section 2.3.
* **Derived figures** (sections 4-6) were computed by calling the live plan functions (`b4b_layout`, `b4b_hardware_plan`, `b4b_lid_underside_z`, `b4b_lid_skin`, `organizer_features.gridfinity` helpers) on four sample boxes (section 3), plus a 2-D Y/Z sweep that mirrors `_sweep_clear_2d` (`organizer_b4b/_plans.py:305-325`). No mesh was built and no test was run. The formulas are given so a reviewer can recompute any number.
* **Status words.** `SETTLED` means the geometry in the live code decides it. `UNSETTLED` means the geometry cannot decide it and it is listed in section 7 and measured on Andrew's prints in section 8. `FORBIDDEN` is a rule. `UNVERIFIED` marks every fit statement: no printed result for either pitch is recorded in the files this contract cites, so no fit statement here is verified.
* **Coordinates.** X is width, Y is depth (front is negative, rear is positive), Z is up. Z = 0 is the underside of the Storage Box body as the code builds it today. The "ridge" is the receiving grid on the lid top, modelled on Stage 1 (section 4.1); it does not exist in the Storage Box code yet.

## 1. Verdict

1. A receiving grid can be added on top of a closed Storage Box lid **only as material added above the lid-top plane**. It cannot be cut into the 2.4 mm latched skin (the receiving profile is deeper than the skin, section 4.1), and the skin and headroom datums stay exactly as the code computes them today (section 4.2).
2. **Lid Only** boxes and **Latched** boxes with **screw hinges** (one or two) and **one or two latches** may carry the grid, at both pitches, from the smallest size the code allows each type. For these the 2-D envelope shows the grid never comes closer to the hinge or latch hardware than the lid plate already does (section 5). All of this is `UNVERIFIED` as printed fit.
3. **Not eligible until the owner records results:** Latched lids with **no latch**, and Latched lids with the **piano hinge** (section 6, rows E3 and E4).
4. **Forbidden together with grid stacking:** the lid-top label location, and the existing peg "Storage Box stacking" option (section 6).
5. The lid-with-grid swings through an envelope that reaches **9.6 to 12.5 mm behind the rear wall crest** at 111 to 117 degrees (section 5.1). The lid can only be opened with nothing seated on it.
6. One build question cannot be settled from geometry: how a lid with a tall grid prints, because the lid is printed upside down on its top face so the hinge and latch barrels print without support (section 7, U1). This contract does not invent a workaround.

## 2. Trace of `organizer_b4b` as landed by Stories 2956-2959

### 2.1 What each story changed (from `git show --stat`)

| Story | Commit | Subject | Files changed |
|---|---|---|---|
| 2956 | `6a6c0ab` | Reinforce secure lid plate | `organizer_b4b/_layout.py` |
| 2957 | `3719699` | Correct lid head-room | `README.md`, `organizer_b4b/_constants.py`, `_geometry/_body.py`, `_layout.py`, `_validation.py`, `organizer_engine/_specs.py`, `web/index.html`, `web/storage-box-form.js` |
| 2958 | `36a07fb`, `1a8a51b` | Strengthen latch grip and default wide boxes to two latches; honor selection | `organizer_b4b/_constants.py`, `web/spaces/10-storage-box-structural.js`, `web/spaces/09-event-wiring.js`, `web/storage-box-form.js`, `features.md`, `ai-features.md` |
| 2959 | `df0fba2` | Deepen fitting screw engagement | `organizer_b4b/_constants.py`, `_note.py`, `_plans.py`, `_validation.py` |

Note: the commit subject of 2959 is "Deepen fitting screw engagement". The screw-pivot hinge itself is described in the code as "the established default" (`organizer_engine/_specs.py:322`), so 2959 is the story that set the bite figures in 2.2, not the story that introduced screw hinges.

### 2.2 Confirmed figures

| # | Figure | Brief / note value | Live value | Read from | Result |
|---|---|---|---|---|---|
| F1 | Latched lid skin | 2.4 mm | `B4B_SECURE_LID_SKIN = 2.4`; returned for any secure lid by `b4b_lid_skin_from_eff` | `organizer_b4b/_constants.py:48`; `_layout.py:514-516` | Matches |
| F2 | Lid Only skin | (not stated) | `eff.base_thickness`, not the constant `B4B_LID_SKIN = 1.6` | `_layout.py:516`; `_constants.py:43` | See D3 |
| F3 | Lid headroom choices | 0.5 / 1.0 / 2.0 mm | `B4B_LID_HEADROOM_CHOICES = (0.5, 1.0, 2.0)`; default 1.0; any other value is refused | `organizer_engine/_specs.py:314`, `:561`, `:624-631`; `organizer_inventory/_space.py:186-199` | Matches |
| F4 | Headroom datum | measured to the lid underside | `lid underside z = base_thickness + z + lid_headroom_mm`; the body rim rises to that same z (the rim is the lid seat); `b4b_max_child_height` returns the entered `z` unchanged | `_layout.py:567-575`, `:604-607`, `:618-629` | Matches |
| F5 | Latch detent | 0.35 / 0.40 / 0.45 mm | `B4B_LATCH_DETENT = 0.40`, plus `0.05 x {loose: -1, default: 0, tight: +1}`. Detent is `nominal - hook_mouth` (M2: 2.0 - 1.60; M3: 3.0 - 2.60). Evaluated live: 0.350 / 0.400 / 0.450 for both M2 and M3. Checked at generation to within 0.025 mm | `_constants.py:340-343`, `:210`, `:247`; `_plans.py:100-106`; `_validation.py:789-799` | Matches |
| F6 | Two-latch threshold | over 96 mm interior width | `B4B_LATCH_TWO_ABOVE_FIELD_X = 96.0`, strictly greater-than. Applied in three places (see D2) | `_specs.py:317`, `:943-945`; `organizer_inventory/_space.py:180-185`; `web/storage-box-form.js:144-149` | Matches, with D2 |
| F7 | Hinge kind | screw hinge, not the ordinary bin's filament-pin hinge | `B4B_HINGE_TYPES = ("screw", "piano")`; default `screw`; the UI offers "Piano hinge (filament pin)" | `_specs.py:324`, `:560`; `web/storage-box-form.js:172` | See D1 |
| F8 | Screw hinge count | (not stated) | `hinge_count` "1" or "2", default "2"; centres at +/- x/4, pulled inward only | `_specs.py:321`, `:559`; `_plans.py:499-502`; `_layout.py:345-362` | Recorded |
| F9 | Hinge screw bite | (not stated) | Screw enters the near ear and the lid centre ear on clearance bores, then threads into the far lug. Beyond the clearance stack: M2 x10 = 10 - 5.4 = 4.6 mm into a 4.6 mm lug (minimum 4.6); M3 x12 = 12 - 6.6 = 5.4 mm into a 5.4 mm lug (minimum 5.4). Tail 0.0 mm (limit 0.5). Same stack and lengths for latch pivot and catch screws | `_constants.py:92`, `:95`, `:194`, `:201-203`, `:228`, `:235-237`; `_plans.py:163-204`, `:539-542`; `_validation.py:378-416` | Matches |
| F10 | Hardware family | (not stated) | M2 when `x <= 120`, `y <= 120` and `z <= 64`; otherwise M3 | `_constants.py:265-266`; `_layout.py:288-303` | Recorded |
| F11 | Hinge axis and opening | (not stated) | Axis at `rear crest + hinge_standoff` (M2 2.75, M3 3.65), at `lid top z - pivot_radius` (M2 2.45, M3 3.32). Opening required: 120 degrees, sampled every 5 degrees. Rear lid relief is tried first (up to 1.2 mm), the axis moves rearward only if relief is not enough | `_constants.py:207`, `:244`, `:198`, `:232`, `:308-317`; `_plans.py:337-372`, `:512`, `:529-538` | Recorded |
| F12 | Latch geometry | (not stated) | Pivot axis at `lid top z - pivot_radius`, `pivot_standoff` ahead of the front crest (M2 2.85, M3 3.45); catch axis `latch_draw` below the pivot (M2 9.0, M3 10.5), `catch_standoff` ahead of the crest (M2 2.6, M3 3.1). Release by 25 degrees, full swing 75 degrees | `_plans.py:544-603`; `_constants.py:204-206`, `:238-240`, `:338-339` | Recorded |
| F13 | Barrel section | (not stated) | Every hinge and latch barrel is a faceted section with vertical faces at +/-Y and flats at +/-Z, so its **top flat is exactly at `lid top z`**. No hardware stands above the closed lid-top plane | `_geometry/_cutters.py:29-43`; `_plans.py:512`, `:575` | Recorded |
| F14 | Minimum sizes | (not stated) | Latched lid: x and y at least 48 mm (`B4B_MIN_FIELD_XY`), z at least 16 mm (`B4B_LATCHED_MIN_HEIGHT`). Lid Only on a Gridfinity grid: one cell at the pitch | `organizer_engine/product_rules.py:32-33`; `_layout.py:321-332`; `_validation.py:566-585`; `organizer_inventory/_space.py:292-315` | Recorded; see 3 |
| F15 | Exterior outline | (not stated) | Gridfinity Storage Box cavity is a plain rectangle (cells x pitch, or plus 0.35 mm per side with no floor); the **outside faces keep the wavy wall (+/-0.4 mm)** and corner arcs. Outer half = inner half + `wall_depth` (`wall x sqrt(1 + max_slope^2)`, 2.4454 mm for a 1.6 mm wall) | `_layout.py:93-172`, `:211-223`; `organizer_engine/_specs.py:1010-1016`, `:1058-1064`; `gridfinity.py:558-561` | Recorded |
| F16 | Height-unit rule | (not stated) | The 7 mm Gridfinity height-unit rule is not applied to Storage Boxes: `normalize_gridfinity_settings` is called only when `box.b4b.enabled` is false | `organizer_app_impl/_design_io.py:1025-1026`; `gridfinity.py:215-257` | Recorded |

### 2.3 Discrepancies between the brief / notes and the live code

* **D1 - Hinge kind.** The brief says the Storage Box hinge is a screw hinge and not a filament-pin hinge. Live code: screw is the default and is the Story 2959 hardware, but a second selectable kind, the **piano hinge**, exists in the engine and the UI. It is a full-width hinge behind the back wall on a 1.75 mm filament pin (`organizer_b4b/_constants.py:321-334`, `_plans.py:375-452`, `_geometry/_hinges.py:193-294`). It is the Storage Box's own piano hinge, not the ordinary bin's pin hinge, but it is not a screw hinge. This contract settles the screw hinge and treats the piano hinge as not eligible (section 6, E4).
* **D2 - Two-latch rule.** The brief reads "two-latch threshold over 96 mm interior width". Live code: the engine default is one latch (`_specs.py:557`); an explicit count of 0, 1 or 2 is accepted at any width; only the legacy value `"auto"` resolves by width (`x > 96` gives 2) in `_specs.py:943-945` and `organizer_inventory/_space.py:180-185`. The Space form **offers** "2" only when the interior width is over 96 mm and defaults a new Space to 2 over 96 mm (`web/storage-box-form.js:56`, `:144-149`). `organizer_outputs/space.py:72` also writes the width rule into the saved count of a Lid Only box, where it has no effect. At the two pitches the first widths over 96 mm are 126 mm (3 cells) at 42 mm and 105 mm (5 cells) at 21 mm.
* **D3 - Lid Only skin.** `_constants.py:43` says the passive lid plate is `B4B_LID_SKIN = 1.6`. No datum function reads it (it is only re-exported, `organizer_b4b/__init__.py:69`). The live Lid Only skin is `eff.base_thickness` (`_layout.py:516`): 5.8 mm for a Gridfinity floor box at its minimum floor build.
* **D4 - Summary heights.** `b4b_summary()["outer_mm"][2]` is the entered interior height `eff.z`, not an exterior height (`_outputs.py:107-108`). `assembled_envelope_mm[2]` is the closed lid top (plus 2.0 mm if the peg option is on) and has no foot or grid term (`_outputs.py:65-67`, `:102-103`). Neither may be reused as a stack height.
* **D5 - Stage 1 stack helper.** `gridfinity.assembled_lid_stack_height` simply returns `assembled_stack_height` = `lower.z + upper.z - SEAT_DESCENT` (`gridfinity.py:191-199`). It has no lid-plate or ridge term and, for a Storage Box, `z` is the interior height. It must not be reused for a Storage Box.
* **D6 - Ordinary-bin lid types.** `validate_grid_lid` (`organizer_features/stack.py:131-140`) limits Gridfinity ordinary-bin lids to a plain plate or a stacking socket and refuses hinged, handle and label lids. Those are ordinary-bin lids. The "existing box lid types" in this contract are the two Storage Box types the Space form offers, "Latched lid" and "Lid only" (`web/storage-box-form.js:133`).

## 3. Sample boxes used for the derived figures

All four: wall 1.6 mm, interior height z = 35 mm, headroom 1.0 mm, two screw hinges, default latch tightness, no edge bevel, built-in floor at its minimum build (5.8 mm, `gridfinity.py:468-474`, `:460`).

| Id | Pitch | Cells | Interior x y | Family | Latches |
|---|---|---|---|---|---|
| S1 | 42 mm | 2 x 2 | 84 x 84 | M2 | 1 |
| S2 | 42 mm | 3 x 3 | 126 x 126 | M3 | 2 |
| S3 | 21 mm | 3 x 3 | 63 x 63 | M2 | 1 |
| S4 | 21 mm | 6 x 6 | 126 x 126 | M3 | 2 |

**Smallest latched box** (x and y at least 48 mm, whole cells): 42 mm pitch = 2 x 2 (84 mm); 21 mm pitch = 3 x 3 (63 mm). A **1 x 1 box can only be a Lid Only box** at both pitches. A 21 mm 2 x 3 box (42 x 63 mm) is also Lid Only only, because 42 mm is under 48 mm.

## 4. Lid datums and the receiving grid

### 4.1 What the receiving grid is

Stage 1 builds the grid on an ordinary-bin lid as a **perimeter ridge** standing on the plate top: `rim_depth` tall, from the plate outline in to the rim mouth, with the receiving socket cut into the ridge only (`organizer_features/stack.py:747-778`; ridge solid `:772-773`, socket cut `:774`, "no crossbars between cells" `:770`). Receiving depth (`rim_depth`) and foot sink (`SEAT_DESCENT`) come from the profile data:

| Pitch | `rim_depth` R | `SEAT_DESCENT` d | Foot height F | Source |
|---|---|---|---|---|
| 42 mm | 3.8 mm | 0.35 mm | 4.75 mm | `gridfinity.py:36`, `:96`, `:111-124`, `:127-141` |
| 21 mm | 4.75 mm | 0.25 mm | 4.75 mm | `gridfinity.py:36`, `:100`, `:111-124`, `:127-141` |

Because R (3.8 or 4.75 mm) is greater than the 2.4 mm latched skin, the receiving profile cannot be cut into a latched lid plate. For a Lid Only box the skin is the base thickness (5.8 mm at minimum floor build), which would physically hold the depth, but the rule in 4.2 forbids altering the skin either way. **The grid is therefore added above the lid-top plane `z_t` and nothing is cut below it.** The Stage 1 construction already behaves this way: the socket cutter's lowest band stops on the plate top and the ridge overlaps the plate by 0.1 mm only to fuse (`stack.py:770-773`).

### 4.2 Datum rules (SETTLED)

* **Skin.** The skin figure used by every datum stays `b4b_lid_skin_from_eff`: 2.4 mm for a Latched lid, `eff.base_thickness` for Lid Only (`_layout.py:514-520`). The grid adds no thickness to it and the plate is not cut.
* **Headroom.** The underside stays `base_thickness + z + lid_headroom_mm` (`_layout.py:604-607`) and the body rim stays at that z (`_layout.py:618-629`). The entered interior height stays the tallest child that fits (`_layout.py:567-575`). Headroom is measured to the lid underside, not to the top of the grid.
* **Lid-top plane.** `z_t = underside + skin`. Everything the grid adds is at `z >= z_t`.

### 4.3 Elevations (nominal, current code, Z = 0 at the body underside)

| Symbol | Meaning | Formula | S1-S4 (b 5.8, z 35, headroom 1.0) | Source |
|---|---|---|---|---|
| `b` | floor top | `eff.base_thickness` | 5.8 | `_layout.py:270-285`, `:600-601` |
| `z_c` | tallest child top | `b + z` | 40.8 | `_layout.py:567-575` |
| `z_u` | lid underside = rim top | `b + z + h` | 41.8 (h = 0.5 / 1.0 / 2.0 gives 41.3 / 41.8 / 42.8) | `_layout.py:604-607` |
| `z_t` | lid top plane | `z_u + s` | 44.2 (43.7 / 44.2 / 45.2) | `_layout.py:514-520` |
| `a_h` | hinge axis | `z_t - r_p` | M2 41.750; M3 40.880 | `_plans.py:512` |
| `a_l` | latch pivot axis | `z_t - r_p` | M2 41.750; M3 40.880 | `_plans.py:575` |
| `a_c` | catch axis | `a_l - latch_draw` | M2 32.750; M3 30.380 | `_plans.py:576` |
| | hinge / latch ear top | = `z_t` (flat of the barrel) | 44.2 | `_geometry/_cutters.py:29-43` |
| | ridge top (hypothetical) | `z_t + R` | 48.0 (42 mm) / 48.95 (21 mm) | 4.1 |

`h` is the headroom, `s` the skin and `r_p` the pivot radius (M2 2.45, M3 3.32). Changing the headroom moves every datum above in step; it does not change any relative distance in section 5 (checked on S1 at 0.5 / 1.0 / 2.0 mm: hinge axis 41.250 / 41.750 / 42.750, root top 40.300 / 40.800 / 41.800, rear relief 0.00 in all three).

### 4.4 Tolerances stated as geometry

This contract sets **no pass/fail tolerance for a printed part**, because none can be derived from geometry. It records the clearances the geometry builds in, which the worksheet in section 8 compares against Andrew's prints:

| Clearance | Value | Source |
|---|---|---|
| Lid skirt to cavity mouth, per side | 0.15 mm | `_constants.py:53` |
| Lid skirt lap below the rim (Lid Only, two X-side runs only) | `min(2.0, headroom)` = 0.5 / 1.0 / 2.0 mm, at least 0.30 | `_constants.py:54`, `:58`; `_geometry/_body.py:331-339`, `:376-395`; `_validation.py:598-607` |
| Running gap between moving printed parts | 0.30 mm | `_constants.py:92` |
| Static gap, body fitting to lid fitting | 0.6 mm | `_constants.py:281` |
| Lid ear root clear of the rear / front crest | `0.30 + fillet` = 1.035 mm (M2), 1.100 mm (M3) (fillet `min(1.0, 0.8, 0.3 x r_p)`) | `_geometry/_hinges.py:144`, `:410`; `_plans.py:494` |
| Foot to receiving band, per side | 42 mm: 0.35 (bottom band: 36.3 mm opening over a 35.6 mm foot); 21 mm: 0.25 (15.1 over 14.6) | `gridfinity.py:96`, `:100`, `:103-108`, `:127-141` |
| Foot sink past the grid-top datum | 0.35 (42 mm) / 0.25 (21 mm) | `gridfinity.py:141` |
| Removable external plate, per side (no-floor box) | 0.35 mm, marked PROVISIONAL in the code | `gridfinity.py:458-459` |

## 5. Clearance map

The four moving or reaching parts are the hinge sweep, the hinge screw, the latch, and the upper box's feet. All lie in the Y/Z plane for a given X; hinge and latch positions in X are fixed by the plan (hinges at +/- x/4 or one at centre, latches at +/- x/6 or one at centre: `_plans.py:500-502`, `:551-553`).

### 5.1 Hinge-and-grid sweep envelope (SETTLED for screw hinges; UNVERIFIED as printed)

Let `s_h` be the hinge standoff (M2 2.75, M3 3.65), `r_p` the pivot radius, `R` the ridge height, and let the ridge be flush with the plate's rear edge (the worst case: any set-back only shrinks the envelope). The ridge's rear top corner sits `s_h` in front of the hinge axis and `r_p + R` above it, so it travels on a circle of radius `rho = sqrt(s_h^2 + (r_p + R)^2)` about the axis.

```
        rear (+Y) ------------------------------------------------------>
 z
 ^       ridge top  z_t+R  ____
 |                        |    |   <- hypothetical ridge, R tall, flush with rear edge
 |       lid top    z_t  _|____|__ . . . . . . . . . . . . . . .
 |       (hinge ear top, flush)          .--.                        ear top = z_t
 |       hinge axis a_h = z_t - r_p     ( ox )  <- axis, ears reach rho_ear
 |       rim / underside z_u  ____|      '--'
 |                              |<-s_h->|
 |                           rear crest   axis
 +------------------------------------------------------------------> y
 rho_plate = sqrt(s_h^2 + r_p^2)  (existing lid corner)
 rho_ridge = sqrt(s_h^2 + (r_p+R)^2)  (ridge top-rear corner)
 rho_ear   = r_p x 1.0595 (barrel diagonal)       Not to scale.
```

Rotating the lid by `theta` (0 to 120 degrees, front edge lifting) moves the ridge corner to `y = a_y + (-s_h cos(theta) + (r_p+R) sin(theta))`, `z = a_h + (s_h sin(theta) + (r_p+R) cos(theta))` (`a_y` = axis y). Computed values:

| Sample | R | `rho_ear` | `rho_plate` (existing corner) | `rho_ridge` | Min distance, ridge to body section and ear, 0-120 deg at 1 deg | Rear reach behind rear crest (at angle) | Ridge corner at 120 deg (y, z) | Hinge's own projection |
|---|---|---|---|---|---|---|---|---|
| S1 (42 mm M2) | 3.8 | 2.596 | 3.678 | 6.826 | 1.082 mm, no overlap | 9.57 mm (113.7 deg) | 54.373, 41.001 | 5.200 |
| S2 (42 mm M3) | 3.8 | 3.517 | 4.932 | 8.000 | 1.415 mm, no overlap | 11.65 mm (117.1 deg) | 77.482, 40.479 | 6.970 |
| S3 (21 mm M2) | 4.75 | 2.596 | 3.678 | 7.705 | 1.082 mm, no overlap | 10.45 mm (110.9 deg) | 44.696, 40.526 | 5.200 |
| S4 (21 mm M3) | 4.75 | 3.517 | 4.932 | 8.856 | 1.415 mm, no overlap | 12.50 mm (114.3 deg) | 78.305, 40.004 | 6.970 |

General rear reach behind the rear crest (valid while the angle of maximum reach is within 120 degrees, true for all four samples): `B = s_h + sqrt(s_h^2 + (r_p + R)^2)`.

Why this is settled from geometry: every ridge point lies inside the plate outline and at or above the plate top, so it is at least as far from the hinge axis as the plate's own rear top corner (`rho_plate`, 3.68 / 4.93). Everything on the body that the opening lid can meet near the axis is closer to the axis than that corner: the hinge ears reach `rho_ear` (2.60 / 3.52) and the reinforcement root's top corner is 2.76 (S1) / 3.58 (S2) from the axis. The existing opening check already proves the plate corner clears the body (`_validation.py:484-506`), and the 2-D sweep above, run against the same rear body section (`_plans.py:286-302`) plus the ear section, gives a minimum distance of 1.082 / 1.415 mm, which is exactly `rho_plate - rho_ear`. The ridge therefore adds no closer approach, provided:

* **C1.** The ridge stays inside the plate outline in plan, including over the hinge X-bands (centre +/- `hinge_root_width / 2`: 11.0 mm M2, 13.6 mm M3). It does not overhang the rear edge and does not sit on the lid ear arms behind the crest.
* **C2.** The ridge stands on the plate top (`z >= z_t`) and nothing below the plate changes.
* **C3.** Rear lid relief, if the solver ever needs it, is cut from the rear-bottom corner of the plate (`_plans.py:262-283`, `_geometry/_body.py:407-408`) and does not touch the ridge. All evaluated cases have 0.00 mm relief (`b4b_hardware_plan(...).lid_rear_relief`).
* **C4.** The opening sweep is defined with **nothing seated on the lid**. A box standing on the lid is not part of any hinged assembly.

Not covered by the live validator: `_validate_b4b_mechanics` step 6 sweeps the real lid mesh against the body only, in 5-degree steps to 120 degrees (`_validation.py:484-506`). It would include a ridge that is part of `make_b4b_lid`, but it knows nothing about the free space behind the box that the reach `B` needs. `b4b_summary` reports no open-lid envelope.

### 5.2 Hinge screw bite where grid cells meet the hinge edge (SETTLED; unchanged)

The grid does not touch any term of the bite (F9). The screw passes along X through the near ear, the lid centre ear and into the body's far lug, all behind the rear crest at `y = axis_y` (`_geometry/_hinges.py:52-185`). The lug thickness (4.6 / 5.4 mm), the clearance stack (5.4 / 6.6 mm) and the screw length (x10 / x12) are properties of `HardwareProfile` and are not read by the ridge. Where the ridge meets the hinge edge in plan, the clear run between the ridge's rear face (at or in front of the plate edge) and the lid ear root is at least 1.035 mm (M2) / 1.100 mm (M3) (section 4.4). Conditions C1 and C2 keep it so. The ridge must not be notched into the ear arm: the arm sits inside the plate's own Z band (`_geometry/_cutters.py:127-151`) and the plate is not altered (4.2).

The socket cut is applied to the ridge only and stops on the plate top, so it cannot reduce the bite. The existing check `_validation.py:401-416` stays the guard and must keep passing unchanged.

### 5.3 Latch reach and clearance (SETTLED for one or two latches; UNVERIFIED as printed)

| Sample | Closed front projection (limit) | Lever outline, closed (y range, z range) | Min distance, 0-75 deg swing, lever to a front ridge flush with the plate edge |
|---|---|---|---|
| S1 | 5.300 mm (6.0) | -50.145 to -45.001, 27.600 to 44.200 | 1.308 mm, no overlap |
| S2 | 6.770 mm (9.0) | -72.615 to -65.976, 24.030 to 44.200 | 1.468 mm, no overlap |
| S3 | 5.300 mm (6.0) | -39.645 to -34.501, 27.600 to 44.200 | 1.308 mm, no overlap |
| S4 | 6.770 mm (9.0) | -72.615 to -65.976, 24.030 to 44.200 | 1.468 mm, no overlap |

Sources: `_plans.py:129-135`, `_constants.py:344`, `_geometry/_hinges.py:450-512`, `_validation.py:455-478`. The lever's highest point is the pivot end, whose top flat is at `z_t`; the strap and hook hang below it and swing outward and up to 75 degrees (release at 25 degrees, `_constants.py:338-339`) staying at or below `z_t`. The latch pivot ears and the catch ears are outboard of the front wall (the lid ear root starts at `front crest - 0.30 - fillet`, `_geometry/_hinges.py:410`) and the receiver ears are on the body below the seam (`latch_root_top_z` is below the underside, `_plans.py:586-588`). A ridge that satisfies C1 and C2 on the front edge does not enter any of this. Latch tightness (0.35 / 0.40 / 0.45 mm) acts on the hook and the catch pin below the plate and does not interact with the ridge. Latch count 0, 1 or 2 changes only the number of identical sections along X.

The existing latch checks compare the lever with the **body** only (`_validation.py:455-478`). They would need to include the lid with its ridge for the swept outline above (not needed for the closed pose, since the ridge is above the lever's top).

### 5.4 Where an upper box's feet may land (SETTLED as a plan-view rule; UNVERIFIED as fit)

* **Cell lattice.** Feet and receiving sockets are placed on pitch centres about the box centre (`gridfinity.py:323-335`, `:420-436`). For two boxes with the same cell counts the lattices coincide. For an upper box of a different cell count the lattice coincides only if `(n_lower - n_upper)` is even on that axis; if it is odd the upper box has to be offset by half a pitch to land. An upper cell field must lie wholly inside the lower cell field: a foot outside the lower field has no receiving socket.
* **Perimeter-only receiving.** The ridge has no crossbars (`stack.py:770`). Only feet over the perimeter band meet a socket; a foot over the interior ends `R - d` above the plate top (3.45 mm at 42 mm, 4.50 mm at 21 mm), assuming the upper box has a foot in every cell as an ordinary Gridfinity bin does (`gridfinity.py:342-355`).
* **Plan extent.** The outer edge of the top receiving band, measured from the box centre, against the case half extent at the wave crest:

| Sample | Cell field half extent | Top receiving band half extent | Case half extent (crest) | Material left outboard of the top band (crest / trough) |
|---|---|---|---|---|
| S1 | 38.000 | 41.150 | 44.845 | 3.695 / 2.895 mm |
| S2 | 59.000 | 62.150 | 65.845 | 3.695 / 2.895 mm |
| S3 | 27.500 | 30.850 | 34.345 | 3.495 / 2.695 mm |
| S4 | 59.000 | 62.350 | 65.845 | 3.495 / 2.695 mm |

(The 21 mm top band is clamped to `pitch - 0.5 - 2 x RIM_MIN_WALL` = 19.7 mm by `rim_socket_cutter`, `gridfinity.py:89`, `:429`.) The case outline is `cells x pitch + 5.691 mm` for a 1.6 mm wall (S1: 89.691 mm for 84 mm of cells), so it is **not** a whole number of cells.
* **Hardware zone.** The hinge ears, hinge roots, latch ears and receivers are all outside the plate outline in plan (behind the rear crest and ahead of the front crest, 5.3 to 6.8 mm out). The feet and sockets are inside it. Feet therefore cannot land on any hinge or latch part.
* **Vertical gap above the lower hardware (models M1 and M2, section 6.3).** The lower hardware tops out at `z_t` (F13). The upper shell underside is `R + F - d` above `z_t`: 8.2 mm (42 mm) / 9.25 mm (21 mm). The handle, the front label holder and the upper box's own outboard hardware are not traced against this gap (U8).

### 5.5 Label rule (FORBIDDEN / SETTLED)

* **Prohibited while grid stacking is enabled: the lid-top label location.** The top label is a text pocket sunk `TEXT_DEPTH` = 0.4 mm into the lid-top plane, with a separate inlay (`_labels.py:231-239`; `organizer_engine/_specs.py:277`; printed as its own object, `_outputs.py:316-324`), placed about one third back from the front (`_labels.py:181-228`). The ridge and the upper box's feet occupy that plane, and a pocket would alter the skin that 4.2 fixes. The live stored default is `label_location = "top"` (`_specs.py:567`, `organizer_inventory/_space.py:121`, `web/storage-box-form.js:58`), so the build must not let that default reach geometry: enabling grid stacking must refuse the top location (or move it to Front or None) and must never emit the pocket.
* **Front label remains usable.** It is a removable plate in a holder on the front wall that drops in from above (`_labels.py:42-123`, `:242-304`). Its insertion ceiling is set by the lower latch (or handle) hardware, `min(catch_axis_z - catch_radius - 1.0, latch_root_top_z - latch_root_height - 1.0)` (`_labels.py:266-291`), which the ridge does not alter. Eligibility stays `b4b_front_label_eligibility` (`_labels.py:321-333`). Fit and insertion with an upper box seated remain UNVERIFIED (worksheet W-C).

## 6. Allowed and forbidden combinations

Status key: **ALLOWED** = settled by geometry (section 5), fit UNVERIFIED. **NOT ELIGIBLE** = not settled; refused by the build story until a revision of this contract records the owner's results. **FORBIDDEN** = rule.

### 6.1 Lid type, by pitch

Applies to the 42 mm and the 21 mm pitch alike unless a size limit is shown.

| Id | Configuration | 42 mm pitch | 21 mm pitch | Reason |
|---|---|---|---|---|
| E1 | **Lid Only** (no hinge, no latch), headroom 0.5 / 1.0 / 2.0 | ALLOWED from 1 x 1 | ALLOWED from 1 x 1 | No hardware exists (`_plans.py:487-488`; hinge and latch parts are skipped, `_geometry/_body.py:285-289`, `:397-405`). Skin = base thickness. Sideways location of the loose plate is not settled (U3) |
| E2 | **Latched lid**, screw hinges (1 or 2), 1 or 2 latches, headroom 0.5 / 1.0 / 2.0, tightness loose / default / tight | ALLOWED from 2 x 2 (2 latches from 3 x 3) | ALLOWED from 3 x 3 (2 latches from 5 x 5) | Section 5. Print pose is unsettled (U1) |
| E3 | Latched lid, **latch count 0** (hinged, nothing holds it shut) | NOT ELIGIBLE | NOT ELIGIBLE | Hinge and ridge geometry are as E2, but nothing in the geometry keeps the lid closed (U4) |
| E4 | Latched lid, **piano hinge** | NOT ELIGIBLE | NOT ELIGIBLE | Different hinge (D1): full-width, axis `back_y + swing_radius` behind the wall, stop at 105 degrees, knuckle tops flush with the lid top; S1 sample axis y 47.448, z 42.026, projection 4.777 mm. Not traced to a sweep envelope here (U7) |
| E5 | Any 1 x 1 box with a latched lid | FORBIDDEN (cannot exist: x, y under 48 mm) | FORBIDDEN (cannot exist) | `_layout.py:321-332`; `_validation.py:566-572` |
| E6 | Latched lid with z under 16 mm | FORBIDDEN | FORBIDDEN | `_validation.py:579-585` |

### 6.2 Options combined with grid stacking

| Id | Option | Status | Reason |
|---|---|---|---|
| O1 | Label location **Top** | FORBIDDEN | 5.5 |
| O2 | Label location **Front** or None | ALLOWED | 5.5 |
| O3 | Existing peg option ("Storage Box stacking: Stackable") | FORBIDDEN together with grid stacking | It cuts four 4.84 mm sockets 1.6 mm deep into the lid top and four 5.5 mm recesses 2.5 mm deep into the underside (`_geometry/_body.py:69-94`, `:435-448`; `_constants.py:28-40`), the same two surfaces the grid and the feet occupy. At 42 mm 2 x 2 the sockets sit at +/-28.56 mm, inside the cell field |
| O4 | Carrying handle (folding bail on the body front wall) | ALLOWED, not traced to a sweep (U8) | Body-mounted, pivot 8.0 mm below the rim datum (`_constants.py:410`), not part of the lid |
| O5 | Built-in grid "floor" or "none" (external plate) | ALLOWED | Lid and ridge geometry are the same; the floor sockets are inside the cavity (`_geometry/_body.py:277-280`) |
| O6 | Edge bevel (none / light / default / heavy, 0 to 1.0 mm) | ALLOWED; ridge outer-face position against the plate-edge chamfer is a build decision | The lid-top outer edge is chamfered by `min(bevel, skin / 2)` (`_geometry/_body.py:365-373`) |
| O7 | Headroom, latch tightness, hinge count, latch count (1 or 2) | ALLOWED | 4.3, 5.1, 5.3 |
| O8 | Lift grabbers, side openings, edge mount | already refused on Storage Box | `_geometry/_body.py:118-137`; `_validation.py:618-621` |

### 6.3 Assembled exterior and stack height model

Symbols: `b`, `z`, `h`, `s`, `z_t` as in 4.3; `F` foot height; `R` ridge height; `d` foot sink (4.1).

**Model assumptions (not in live code yet).**
* **M1.** Feet of height `F` are added **below** `Z = 0`, so the body datum rises by `F`.
* **M2.** The ridge adds `R` above `z_t` and the upper box's foot bottoms sit `d` below the ridge top (the Stage 1 relationship, `stack.py:143-160`, `gridfinity.py:191-194`).

| Quantity | Formula | Live-code term today |
|---|---|---|
| Closed exterior, current code | `H0 = b + z + h + s` (+2.0 if peg option, `_outputs.py:102-103`) | `b4b_summary assembled_envelope_mm[2]` |
| Closed exterior with feet | `H_f = F + H0` | none |
| Closed exterior with feet and grid | `H_r = F + H0 + R` | none |
| Two identical boxes stacked, upper without its own grid | `H_2 = H_r + H_f - d` | none |
| Two stacked, upper with its own grid | `H_2 + R` | none |
| Gap from lower ridge top to upper shell underside | `F - d` | none |
| Gap from lower hardware top (`z_t`) to upper shell underside | `R + F - d` | none |

| Sample (b 5.8, z 35, s 2.4, h 1.0) | `H0` | `H_f` | `H_r` | `H_2` | `H_2` with upper grid | `F - d` | `R + F - d` |
|---|---|---|---|---|---|---|---|
| S1, S2 (42 mm) | 44.20 | 48.95 | 52.75 | 101.35 | 105.15 | 4.40 | 8.20 |
| S3, S4 (21 mm) | 44.20 | 48.95 | 53.70 | 102.40 | 107.15 | 4.50 | 9.25 |

Headroom 0.5 / 2.0 mm moves `H0` to 43.70 / 45.20 and every height above by the same amount. Passive lid (E1): `s = b`, so `H0 = 2b + z + h`. The Storage Box exterior is not constrained to whole 7 mm units (F16).

## 7. Unsettled configurations (not decidable from geometry alone)

No workaround is invented for any item. Each is listed with what would settle it.

| Id | Configuration | Why geometry cannot settle it | Settled by |
|---|---|---|---|
| U1 | **Latched lid with a ridge: print pose.** E2, both pitches | The lid prints flipped 180 degrees about X so its top face is on the bed (`_outputs.py:226-229`), and the barrels use a support-free section for exactly that pose (`_constants.py:62-75`). With a ridge `R` tall on the top face, the flipped lid rests on the ridge crest and the hinge and latch barrel flats (at `z_t`) are `R` above the bed, so the support-free assumption is not shown to hold. `b4b_print_object_bounds` also takes the lid height from the plate, not from a ridge (`_outputs.py:415-423`) | Owner decision on print pose and printed test (W-A) |
| U2 | **Foot to socket fit, both pitches, 1 x 1 and multi-cell.** | Receiving bands come from the Stage 1 profile data; the removable-plate clearance is marked provisional (`gridfinity.py:458`); no printed fit result is recorded in the cited files | W-B |
| U3 | **Lid Only: sideways location of the loose plate** while an upper box is lowered on and lifted off, and whether the plate lifts with the box. E1 | The lid is held only by a 0.15 mm-per-side skirt on the two X-side runs (`_geometry/_body.py:386-395`) | W-B, W-C |
| U4 | **Latched lid, latch count 0.** E3 | Nothing keeps the lid closed; geometry cannot say whether that is acceptable | Owner ruling plus W-C |
| U5 | **Latch engagement and release with an upper box seated**, tightness loose / default / tight, one and two latches | The strap and pin geometry is settled (5.3) but whether a snug upper box leaves the latch operable by hand is a physical question | W-C |
| U6 | **Open-lid rear reach** (9.6 to 12.5 mm behind the rear crest) against real surroundings | Free space behind the box is not a property of the box | W-C |
| U7 | **Piano hinge.** E4 | Section 5.1 was not run for the piano axis, stop ledge and 105 degree stop | Separate trace and prints, or exclusion |
| U8 | **Folded and deployed handle, front label holder and the upper box's own outboard hardware** against the lower box and the upper shell | Not traced to a sweep envelope | W-C |
| U9 | **Parity and offset mating:** a smaller upper box on a larger lower one with odd and even cell differences, offset by half a pitch | The rule in 5.4 is geometric; whether the receiving band tolerates the offset foot is not | W-B |
| U10 | **Ridge placement details:** ridge outer-face set-back from the plate edge and its relation to the lid-top edge chamfer (O6) | Build decisions inside the limits C1 and C2; not settled by geometry | S2-02 design plus W-A |

## 8. Owner measurement worksheet (Andrew's own prints)

Fill one block per printed box. Nominal values are the model values in this contract; a blank "Measured" column is expected until prints exist. Nothing here is pre-filled as a result.

### 8.1 Print record

| Field | Entry |
|---|---|
| Pitch (21 / 42 mm), cells X x Y, floor mode (floor / none) | |
| Lid type (Latched / Lid only), hinge count, latch count, latch tightness, headroom | |
| Wall, base, interior z | |
| Printer, material, nozzle, layer height, slicer, orientation used for the lid | |
| Date, print id | |

### 8.2 W-A - Dimensions of each printed part (calipers)

| Id | Measure | Nominal | Measured | Note |
|---|---|---|---|---|
| A1 | Foot height (foot bottom to shell start) | 4.75 mm | | |
| A2 | Case outer X and Y at the widest wave crest | `cells x pitch + 5.691` (1.6 mm wall) | | |
| A3 | Lid plate thickness (away from ridge and fittings) | 2.4 mm latched; base thickness for Lid Only | | |
| A4 | Ridge height above the plate top | 3.8 mm (42) / 4.75 mm (21) | | |
| A5 | Lid underside to floor top, lid seated, nothing inside | `z + headroom` | | |
| A6 | Closed exterior height, feet to lid top, no ridge fitted or ridge included (state which) | `H_f` or `H_r` | | |
| A7 | Socket opening at its narrowest (bottom band) and at the ridge top, one corner cell | 36.3 / 40.3 mm (42); 15.1 / 19.7 mm (21) | | |
| A8 | Foot width at its bottom and at its top, one corner cell | 35.6 / 41.5 mm (42); 14.6 / 20.5 mm (21) (`2 x (foot_half + radius)`, `gridfinity.py:48`, `:50-72`) | | |
| A9 | Latched lid only: did the lid print without support at the hinge and latch barrels in the pose used (yes / no, describe) | n/a | | U1 |

### 8.3 W-B - Mating (upper on lower; repeat for 1 x 1 and multi-cell)

Pairs to try: 1 x 1 on 1 x 1 (Lid Only); smallest latched on itself (42 mm 2 x 2, 21 mm 3 x 3); a multi-cell pair such as 2 x 3 on 2 x 3 (42 mm) and 3 x 5 on 3 x 5 (21 mm); smaller on larger with even and with odd cell difference.

| Id | Measure | Nominal | Measured |
|---|---|---|---|
| B1 | Gap from lower ridge top to upper shell underside, at four corners | 4.40 mm (42) / 4.50 mm (21) | |
| B2 | Total stacked height, two boxes | `H_2` (101.35 / 102.40 for the samples) | |
| B3 | Seats by hand without force (yes / no / needs force) | yes | |
| B4 | Sideways play at the rim seam, X and Y | not stated | |
| B5 | Upper lifted straight off: does the lower lid come with it (yes / no) | no | |
| B6 | Which feet contact which socket faces (describe or photograph) | perimeter band only | |
| B7 | Odd-difference pair: lands when offset half a pitch (yes / no) | yes | |

### 8.4 W-C - Closure, hinge, latch and label (lower box, with and without an upper box)

| Id | Check | Nominal | Result |
|---|---|---|---|
| C1 | Lid closes fully, seam gap around the perimeter | 0 (plate on rim) | |
| C2 | Each latch engages; detent feel (loose / default / tight set) | 0.35 / 0.40 / 0.45 mm interference | |
| C3 | Each latch releases by hand with nothing on the lid | yes | |
| C4 | Each latch releases and re-engages with an upper box seated | yes | |
| C5 | Lid stays shut when the box is lifted by the body, upper box seated | not stated | |
| C6 | Lid opens to 120 degrees with ridge fitted and nothing on it: free (yes / no) | yes | |
| C7 | Free depth behind the rear wall needed at the position of maximum reach | 9.57 / 11.65 mm (42 M2 / M3); 10.45 / 12.50 mm (21 M2 / M3) | |
| C8 | Hinge screws: installed, engaged, driver reaches the heads with the ridge fitted | 4.6 mm (M2) / 5.4 mm (M3) engaged | |
| C9 | Lid cannot be opened with an upper box seated (expected) | cannot | |
| C10 | Front label drops in and lifts out with the upper box seated | yes | |
| C11 | Folded handle and deployed handle clear the upper box (only if fitted) | clear | |
| C12 | Latch count 0 box (only if the owner wants U4 settled): lid stays closed when the stack is moved | not stated | |

### 8.5 Recording rule

Record each result against the sample it belongs to (pitch, cells, lid type, headroom, tightness). A result that fits is recorded as that exact configuration only. No fit statement in any later document is made for a configuration without a recorded result here.

## 9. Obligations on the S2-02 build story

1. Take the allowed and forbidden sets from section 6 exactly. Refuse E3, E4, O1 and O3 with a plain message; never silently change a user's choice.
2. Keep `b4b_lid_skin_from_eff` (2.4 mm latched), `b4b_lid_underside_z_from_eff` and `b4b_max_child_height` unchanged (4.2). Add grid material only at `z >= z_t`; cut nothing below it.
3. Keep the hinge, latch and screw geometry unchanged (`HardwareProfile`, `_plans.py`, `_geometry/_hinges.py`). The existing screw-bite check (`_validation.py:378-416`) and detent check (`:789-799`) must keep passing.
4. Keep the ridge inside the plate outline and out of the hinge X-bands behind the crest (C1, C2). Extend the opening sweep and the latch sweep to cover the lid with its ridge, and report the open-lid rear reach `B`.
5. Report heights from the model in 6.3 (not from `outer_mm[2]`, not from `assembled_lid_stack_height`), and add `R` to the lid term of `b4b_print_object_bounds` (`_outputs.py:415-423`).
6. Do not offer the lid-top label location while grid stacking is on; front labelling keeps its existing eligibility.
7. Resolve U1 and U10 by an explicit decision recorded in the S2-02 story before geometry is written. Any statement about fit, closure or mating stays marked unverified until the worksheet in section 8 holds a recorded result.
8. Both pitches, 1 x 1 (Lid Only) and multi-cell, remain in scope for acceptance. S2-02 acceptance already requires physical fit and closure checks (master plan, S2-02).

## 10. Review and acceptance

| | |
|---|---|
| Source read | `organizer_b4b/_constants.py`, `_layout.py`, `_plans.py`, `_outputs.py`, `_labels.py`, `_validation.py`, `_geometry/_body.py`, `_geometry/_hinges.py`, `_geometry/_cutters.py`; `organizer_engine/_specs.py`, `product_rules.py`; `organizer_features/gridfinity.py`, `stack.py`; `organizer_inventory/_space.py`; `organizer_outputs/space.py`; `organizer_app_impl/_design_io.py`; `web/storage-box-form.js` |
| Verification | By inspection against the live code at the pin. No automated test written, run or repaired; no test file kept. |
| Reviewer | |
| Accepted on | |
| Owner sign-off | |
