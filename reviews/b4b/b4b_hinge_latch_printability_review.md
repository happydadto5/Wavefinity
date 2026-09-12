# Wavefinity B4B Hinge / Latch Design Review

Repository snapshot reviewed: `main` at commit `cb912e49bdf155cc26749325d0cae8fd73913908`.

Purpose: implementation instructions for an LLM. This document intentionally lists only areas that need correction or hardening. Do not spend time rewriting B4B areas not identified below.

## Required outcome

The secure B4B must satisfy all of these simultaneously:

- Hinges, latch receivers, lid latch ears, and latch levers print without support in the orientation emitted by `b4b_build_parts()`.
- No integrated hinge/latch feature may depend on a full horizontal round overhang or an unsupported round-hole roof to print correctly.
- Hinge and latch loads must transfer into a structural reinforcement zone, not through a sub-millimetre Boolean overlap with a thin user-selected wall.
- M3 head-bearing faces and thread-forming lugs must have deliberate structural margin, not merely clear the mathematical minimum.
- Lightweight vs Standard latch strength must alter real structural geometry.
- Existing lid/body opening and latch sweep validation must still pass after the changes.

---

## P0-1 — Integrated horizontal round barrels and round bores are not support-free by construction

### Area

`organizer_b4b.py`

- `_round_profile_yz()`
- `_x_cylinder()`
- `_knuckle()`
- `_hinge_body_parts()`
- `_hinge_lid_parts()`
- `_latch_body_parts()`
- `_latch_lid_parts()`
- `_print_pose()`

### Problem / analysis

All integrated hinge and latch-ear barrels are full circular cylinders with their axis on world X. The B4B body is printed in assembly orientation, so those X-axis cylinders remain horizontal. The lid is rotated 180 degrees around X, which reverses Z but still leaves the barrel axis horizontal.

The supporting gussets reduce some of the unsupported area, but the final union still contains the lower arc of a full round barrel. That arc necessarily contains surfaces steeper than the allowed support-free overhang target. The same problem exists on the circular X-axis screw bores: their roofs are round horizontal-hole roofs and therefore rely on short-span bridging rather than geometry that is explicitly self-supporting.

The separate latch lever is different: `_print_pose(..., "latch")` rotates its extrusion axis onto Z, so its pivot bore is effectively vertical in print space. The integrated body/lid fittings do not get that benefit.

This means the current implementation is only "support-minimising"; it does not meet the requested guarantee that all hinge/latch parts print without support.

### Required alteration

Replace the full-round print-critical cross-sections used by integrated body/lid hardware with support-free X-axis primitives.

1. Add a print-safe outer barrel/boss helper based on a YZ polygon extruded on X. Use a symmetric octagonal / faceted barrel or equivalent profile with:
   - a finite flat at both +Z and -Z extremes,
   - no downward-facing facet steeper than 45 degrees in either the body or flipped-lid print orientation,
   - the existing pivot axis unchanged.

   A symmetric top-and-bottom support-safe profile is preferred because body and lid print with opposite Z directions.

2. Add a support-free X-axis bore helper instead of using a full round `_x_cylinder()` cutter for the integrated hardware bores.
   - For body fittings, the unsupported roof is assembly +Z.
   - For lid fittings, because the lid is flipped 180 degrees around X, the unsupported roof is assembly -Z.
   - The helper should accept a `roof_sign` / print-Z direction and create a teardrop or 45-degree roof while preserving at least the requested inscribed clearance/pilot diameter.
   - Clearance bores must still freely pass the M3 screw.
   - Pilot bores must retain enough material to thread-form rather than becoming an oversized polygonal clearance hole.

3. Do not alter the separately printed latch lever merely to match the new primitive. Its current broad-face print orientation is the right approach; only change it if needed for dimensional consistency.

4. Re-run moving-part clearance after changing barrel envelopes. A print-safe outer profile may be larger in selected directions even if its nominal radius is unchanged.

---

## P0-2 — Body hinge and latch supports attach through an extremely shallow wall overlap

### Area

`organizer_b4b.py`

- `_hinge_body_parts()`
- `_latch_body_parts()`
- B4B wall-thickness interaction through `BoxSpec.wall_depth`

### Problem / analysis

Both body-side hardware builders intentionally sink their root into the case wall by only:

`min(0.6, eff.wall_depth * 0.55)`

Wavefinity currently allows wall thickness down to 0.2 mm. Because `wall_depth` is only about 1.18 times the user wall value, a legal 0.2 mm wall gives only about 0.13 mm of hardware/root overlap. Even the normal 0.8 mm wall gives only roughly 0.52 mm of overlap.

A Boolean union can be watertight with that overlap, but it is not an adequate mechanical load path for a carrying-case hinge or latch. Hinge opening torque and latch pull are concentrated into a narrow root and can tear the fitting away from the wall, especially across FDM layer boundaries.

The B4B design requirement already permits hardware reinforcement to grow outward. There is no reason to make hinge/latch strength depend on the user's general wall-thickness setting.

### Required alteration

Create dedicated exterior reinforcement zones for the rear hinges and front latch receivers.

1. The reinforcement must begin at the B4B **inner mating face** and grow outward through the full existing wall thickness, then continue outward to the fitting. It must not project inward into the child-bin cavity.

2. Do not use `wall_depth * 0.55` as the structural root depth. The fitting must overlap the entire local B4B wall band.

3. Add a backing pad / root web wider than the individual barrel:
   - hinge reinforcement: distribute the two body knuckles into a backing region spanning the hinge envelope plus a small X margin;
   - latch reinforcement: distribute each catch pair into a backing region spanning the latch/catch envelope plus a small X margin.

4. Taper the reinforcement into the normal wall at 45 degrees or shallower so the body still prints upright without support.

5. Make the reinforcement dimensions independent of the normal wall setting. A thin B4B wall may remain thin away from hardware, but the hardware zone must meet its own minimum structural thickness.

6. Keep the authoritative inner mating polygon unchanged. All strength growth should be outward.

---

## P0-3 — Hinge minimum-width/thread-lug protection has regressed

### Area

`organizer_b4b.py`

- `B4B_HINGE_WIDTH_MIN`
- `B4B_HINGE_AXIAL_GAP`
- `_hinge_screw_stack()`
- `B4B_SECURE_MIN_FIELD_X`
- `b4b_hardware_plan()`

### Problem / analysis

Current `main` has:

- `B4B_HINGE_WIDTH_MIN = 10.0`
- `B4B_HINGE_AXIAL_GAP = 0.20`
- `B4B_SECURE_MIN_FIELD_X = 3 * GRID_PITCH` = 24 mm

But the comment directly above the minimum still explains a 12 mm minimum and a substantially thicker terminal lug. Repository history also contains an explicit earlier correction that raised the hinge minimum from 10 mm to 12 mm so the thread-forming terminal lug was not merely at the M3 engagement floor.

At the current 10 mm minimum, the terminal lug thickness is approximately:

`10 / 3 - 0.20 = 3.13 mm`

The required engagement minimum is 3.0 mm. That leaves only about 0.13 mm of geometric margin before manufacturing variation, horizontal-hole deformation, repeated screw insertion, and FDM anisotropy are considered.

The code's safety check prevents a mathematically sub-3.0 mm lug, but the design is again operating essentially at that minimum instead of with useful physical margin.

### Required alteration

Do not simply hard-code another unexplained number. Make the minimum hinge width derive from a target lug thickness with safety margin.

Recommended target:

- terminal thread-forming lug target: at least 3.6 mm, preferably 3.8 mm;
- derive minimum hinge width from `3 * (target_lug + axial_gap)` and round up to a practical value;
- with the current 0.20 mm gap, 12 mm is a reasonable minimum.

Then update secure-case auto-growth so **two complete hinge envelopes** fit with:

- corner keep-out,
- a nonzero central separation between the two hinge assemblies,
- the new reinforcement-pad width.

Prefer deriving minimum secure field X by fit rather than maintaining a separate magic `24` or `32` constant that can drift from the actual hardware.

Add validation that checks the target safety thickness, not only the 3.0 mm absolute thread-engagement floor.

---

## P1-4 — The defined hinge corner keep-out is not applied

### Area

`organizer_b4b.py`

- `B4B_HINGE_CLEAR_KEEPOUT`
- `b4b_hardware_plan()` hinge placement

### Problem / analysis

`B4B_HINGE_CLEAR_KEEPOUT = 1.0` is defined as an extra gap from the wall's corner tangent, but current hinge placement computes the limit from:

`outer_half_x - CORNER_INSET - hinge_width / 2`

The additional hinge keep-out constant is not included. The constant is therefore dead and the hardware can be pushed right up to the corner tangent.

That is especially undesirable once the hinge receives the wider backing/root reinforcement required above: a reinforcement pad that reaches a rounded/wavy corner has a weaker and less predictable load path and may create new local overhangs.

### Required alteration

Apply the keep-out in the actual placement constraint:

`limit = outer_half_x - CORNER_INSET - B4B_HINGE_CLEAR_KEEPOUT - hinge_width / 2`

Also enforce a central gap between the left/right hinge envelopes. If the two reinforced hinges cannot satisfy both the corner keep-out and central separation, auto-grow the B4B field by `GRID_PITCH` until they can.

Do not silently squeeze or overlap the reinforcement pads.

---

## P1-5 — M3 head clearance is declared but not used to size the bearing boss

### Area

`organizer_b4b.py`

- `B4B_M3_HEAD_CLEAR = 6.0`
- `B4B_HINGE_KNUCKLE_RADIUS = 3.1`
- latch `boss_r = B4B_M3_CLEAR_BORE / 2 + 1.6`
- near-side clearance-bored hinge/latch/catch ears

### Problem / analysis

`B4B_M3_HEAD_CLEAR` exists but is not used as a boss-sizing constraint.

The hinge barrel diameter is only 6.2 mm around a declared 6.0 mm head-clearance diameter. That leaves about 0.1 mm radial edge margin at the head-bearing face. The latch/catch boss diameter is about 6.6 mm, leaving only about 0.3 mm.

The screw head bears directly on the printed near ear. With no washer or insert, such small edge margin makes cracking, crushing, and layer splitting more likely even if the bore itself has adequate wall thickness.

### Required alteration

Make screw-head bearing margin a real geometric constraint.

Recommended rule for every head-bearing near ear:

`bearing_outer_radius >= B4B_M3_HEAD_CLEAR / 2 + 0.6 mm`

A 0.8 mm edge margin is preferable if it does not create clearance conflicts.

Use the new support-free faceted boss profile from P0-1 at this derived outer size. Keep the screw head on a flat end face; do not add a countersink that reduces the remaining wall.

If only the near ear needs the larger head-bearing envelope, the far pilot lug may stay smaller, but a common profile is simpler if motion clearances allow it.

Add a validation check so `B4B_M3_HEAD_CLEAR` cannot become dead again.

---

## P1-6 — Lid hardware is connected by a plate-skin bridge, not a true structural root

### Area

`organizer_b4b.py`

- `_hardware_bridges()`
- `_hinge_lid_parts()`
- `_latch_lid_parts()`
- `B4B_LID_SKIN`

### Problem / analysis

The bridge code was added so lid-side fittings would export as one connected solid. It does that, but the connection is structurally minimal:

- the bridge exists only through the normal lid-skin Z band;
- current lid skin is 1.6 mm;
- the bridge only bites 0.6 mm into the fitting;
- bridge X width is only the part's current bound.

This fixes disconnected geometry but still leaves hinge/latch loads entering a thin flat tongue. A carrying case can put much larger peel/bending loads into that tongue than a connectivity check reveals.

### Required alteration

Strengthen the secure-lid root while retaining the current top-down print orientation.

Recommended approach:

1. Add an authoritative secure-lid skin thickness helper. Keep passive lids at the current 1.6 mm if desired, but use at least 2.4 mm for a secure lid.

2. Replace direct uses of `B4B_LID_SKIN` in B4B lid/hardware datum calculations with that helper so these stay synchronized:
   - lid plate thickness,
   - lid top Z,
   - hinge-axis Z,
   - latch pivot Z,
   - stacking socket roof thickness,
   - top-label pocket/inlay datum,
   - assembled envelope summary.

3. Strengthen `_hardware_bridges()`:
   - increase fitting bite from 0.6 mm to at least 1.0 mm;
   - widen the bridge/root in X beyond the bare fitting width where the adjacent moving hardware leaves clearance;
   - extend farther into the plate in Y so the load is distributed instead of entering at the plate edge.

4. Do not add a downward projection inside the body footprint below the lid underside; that would collide with the rim. Any extra depth outside the footprint must be checked against the interleaved body hardware and the existing opening sweep.

5. Re-run `_validate_b4b_mechanics()` after the root changes.

---

## P1-7 — `catch_thickness` is a dead strength-profile parameter

### Area

`organizer_b4b.py`

- `B4B_LATCH_PROFILES`
- `_latch_body_parts()`
- `_latch_frame()`

### Problem / analysis

Both latch profiles define `catch_thickness`:

- Lightweight: 2.4 mm
- Standard: 3.6 mm

The current geometry does not consume this parameter. The catch boss radial shell is fixed, and the receiver support geometry is not thickened according to `catch_thickness`.

As a result, the Standard profile does not receive all of the structural strengthening implied by its own parameter set. `pad_wall`, hook depth, detent, and placement differ, but this declared catch-strength dimension is dead.

### Required alteration

Give `catch_thickness` one explicit structural meaning and use it consistently.

Recommended meaning: exterior receiver/backing-web thickness behind the M3 catch boss, independent of the user wall thickness.

- Lightweight uses the smaller receiver web.
- Standard uses the thicker receiver web.
- Both still obey the minimum full-wall-root requirement in P0-2 and the M3 head-bearing margin in P1-5.
- Keep the child-field inner mating face unchanged; additional thickness grows outward.

If the parameter is not intended to control real geometry, remove it instead. Do not leave a dead strength control in the profile dictionary.

---

## P1-8 — Current tests validate the loose latch lever's bed contact but not the integrated support-free hardware

### Area

`test_b4b.py`

Current relevant test: `test_latch_lever_prints_flat_on_its_broad_face()`.

### Problem / analysis

That test is useful for the separately printed latch lever, but there is no equivalent protection for:

- body hinge barrels;
- body latch/catch bosses;
- flipped-lid hinge barrel;
- flipped-lid latch pivot bosses;
- horizontal screw-bore roofs;
- minimum-wall hardware-root strength geometry;
- hinge corner keep-out;
- M3 head-bearing margin.

Watertightness, single-component checks, and motion sweeps do not prove support-free printability or adequate structural load paths.

### Required alteration

Because this change is a major mechanical geometry change, add a small set of targeted tests rather than expanding general regression testing.

At minimum add tests that prove:

1. The support-free barrel helper has no print-facing profile segment steeper than 45 degrees for either body print Z or flipped-lid print Z.
2. The support-free bore helper points its roof toward the actual unsupported print direction for body vs lid.
3. The minimum secure B4B at the thinnest legal wall still has full-wall-depth hinge and latch root overlap.
4. Hinge terminal lug thickness meets the new safety target, not merely 3.0 mm.
5. Every near head-bearing boss satisfies the derived M3 head-clearance edge margin.
6. Hinge envelopes satisfy corner and central keep-outs after auto-growth.
7. Lightweight and Standard produce measurably different catch receiver structural geometry.
8. Existing deep latch and lid motion sweeps continue to pass.

Do not add broad randomized or exhaustive tests for unrelated Wavefinity features.

---

# Implementation order

1. Introduce derived hardware sizing helpers/constants: hinge lug target, M3 head-bearing margin, secure-lid skin, and local hardware reinforcement dimensions.
2. Fix secure-field auto-growth and hinge placement using real reinforced hardware envelopes plus corner/central keep-outs.
3. Implement support-free integrated barrel and bore helpers.
4. Replace body hinge and body latch roots with full-wall-depth outward reinforcement zones.
5. Replace lid-side connectivity-only roots with the strengthened secure-lid root/bridge design.
6. Wire `catch_thickness` into real receiver reinforcement geometry.
7. Update summary/envelope/BOM calculations that depend on changed radii, width, lid skin, or screw length.
8. Run the existing deep mechanical sweep and correct only real collisions caused by the new envelopes.
9. Add the targeted B4B tests listed above.

---

# Final plan gap review

Second-pass review of the plan found these downstream dependencies that must be handled so the implementation is complete:

- **Hardware plan:** any hinge-width/radius/root-envelope change must remain authoritative in `b4b_hardware_plan()` rather than being recomputed ad hoc in builders.
- **Auto-growth:** the effective field must grow before geometry is built when the reinforced two-hinge arrangement cannot fit. Do not let geometry silently clip into a corner.
- **Screw selection/BOM:** if axial ear widths change, `_hinge_screw_stack()`, `_latch_screw_stack()`, `_screw_for_stack()`, `B4BHardwarePlan.screw_bom()`, and summary output must remain synchronized. Radius-only changes do not require a new screw length.
- **Preview/export parity:** both already use the same B4B builders; keep the new reinforcement and support-free profiles inside those shared builders so preview cannot diverge from export.
- **Lid datums:** if secure lid skin changes, update every top/underside/axis/socket/label datum through one helper; do not scatter another thickness constant.
- **Stacking:** verify the stacking socket leaves adequate roof after secure-lid thickness changes and that the larger hardware roots do not intersect locator/socket keep-outs.
- **Top label:** verify label pocket depth and stacking keep-outs remain valid with the new secure-lid skin/top datum.
- **Front label:** body-side reinforcement must not invade the current front-label channel clear band. If both are enabled, the label-frame placement must be checked against the reinforced latch receiver envelope.
- **Mechanical sweep:** larger print-safe barrels, head-bearing bosses, and root webs must be included in the existing latch and lid opening collision checks.
- **Assembled envelope:** `b4b_summary()` currently derives hardware envelope dimensions from existing radii/widths. Update it to use the new authoritative profiles/radii so displayed size is not understated.
- **Thin-wall cases:** specifically verify 0.2, 0.4, and default 0.8 mm walls; hardware strength must no longer collapse as wall thickness is reduced.
- **Strength profiles:** confirm every profile field either changes real geometry or is deleted; do not leave dead mechanical tuning values.

No additional B4B subsystem appears necessary for this correction. The affected chain is: constants/derived sizing -> hardware plan -> body/lid hardware builders -> print pose -> deep mechanics -> build parts -> summary/BOM -> targeted B4B tests.

## Recommended execution model

Use a **Top-level coding model with Medium thinking**. The design decisions are already specified with high confidence, but the implementation touches parametric 3D geometry, mirrored print orientations, mechanical clearances, and downstream datum calculations, so a top model is justified even though a large amount of the design reasoning has already been completed here.
