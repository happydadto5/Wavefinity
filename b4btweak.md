# B4B Hinge / Latch Tweak Plan

Audience: implementation LLM. This is a targeted mechanical cleanup of the current B4B hardware, not a redesign.

Repository reviewed: current `main`, especially `organizer_b4b.py`, `test_b4b.py`, and the prior `reviews/b4b/b4b_hinge_latch_printability_review.md`.

## Goal

Keep the current B4B architecture, hardware family selection, screw scheme, hinge/latch locations, compact appearance, supportless-print intent, lid motion, and latch motion. Correct three over-designed / under-connected details:

1. Body-side hinge/latch supports should use the real wavy wall as part of their structural load path instead of leaving visible local gaps and relying on the outer root pad alone.
2. Hinge/latch pivot stacks should not have one visibly oversized head-bearing ring. Use a uniform outer diameter through each pivot stack unless a real hardware constraint proves that impossible.
3. Stop treating every horizontal M2/M3 bore as if a perfectly self-supporting teardrop is mandatory. Current 1.7-3.4 mm screw/pin bores are small enough to print as circles; the teardrop removes useful material and introduces an apex/stress concentration. Use true round bores.

This plan must be applied consistently to rear hinges, front latch pivots, front catch receivers, body/lid halves, loose latch levers, and any shared helper that also affects the folding handle.

---

# 1. Current-code findings

## 1.1 Body hardware roots already exist, but the ear gussets do not always bite into the actual local wall

Relevant code:

- `b4b_hardware_plan()`
- `_wall_extreme_y()`
- `_root_profile_yz()`
- `_root_taper_prism()`
- `_gusset()`
- `_hinge_body_parts()`
- `_latch_body_parts()`
- `_handle_body_parts()`

The current root system is structurally much better than the old shallow-overlap design. `_root_profile_yz()` intentionally starts inside the inner mating face, crosses the wall band, grows outward, and is trimmed by `_cavity_prism()` so it does not consume child-bin capacity.

The remaining problem is more local: the actual ear/gusset is anchored from the root face rather than from the real wall at that ear's X position.

For the rear hinge, `_hinge_body_parts()` currently calls `_gusset()` with approximately:

`root_y = plan.hinge_root_face_y - 0.8`

`plan.hinge_root_face_y` is derived from the worst rear crest across the whole hinge-root span plus the outward reinforcement depth. On a wavy wall, an individual ear may sit over a local valley rather than that worst crest. The gusset can therefore stop outside the actual local wall and only connect through the outer reinforcement root. The screenshot symptom is exactly what this permits: the triangular support does not visually/structurally merge into the bin wall along all of the useful area available to it.

The same pattern exists on the front catch receiver and handle forks, with the sign reversed.

## 1.2 The visibly larger ring is the deliberate screw-head bearing flare

Relevant code:

- `HardwareProfile.head_clear`
- `HardwareProfile.head_edge_margin`
- `HardwareProfile.head_flare_radius`
- `HardwareProfile.head_bearing_margin`
- `_ear_solid()`
- `B4B_HINGE_MAX_PROJECTION`
- `B4B_HANDLE_MAX_PROJECTION`
- `b4b_summary()` metrics

`_ear_solid()` adds a short, larger-radius `support_free_profile_yz(flare)` pad to the outboard/head-side ear. That is the large ring visible in the hinge image.

Current examples:

- M2 ordinary hinge/latch pivot radius: `2.4`; head flare radius: `2.6`.
- M3 ordinary hinge/latch pivot radius: `3.0`; head flare radius: `3.6`.
- M3 catch radius: `2.7`; head flare radius: `3.6`.

The current code intentionally made the flare short rather than letting the screw head size enlarge the whole stack, but visually this still reads as one oversized washer/boss and is not needed if the actual socket-head bearing requirement can be satisfied by the normal stack diameter.

## 1.3 Teardrop bores are applied far more broadly than necessary

Relevant code:

- `support_free_bore_profile_yz()`
- `_support_free_bore()`
- `_ear_solid()`
- `_handle_bore_profile()`
- `make_b4b_handle()`
- `b4b_latch_lever_profile()`

Every bore created through `_ear_solid()` is currently a teardrop, including:

- rear hinge body clearance ear;
- rear hinge body terminal pilot lug;
- rear hinge lid centre ear;
- front latch lid clearance ear;
- front latch lid terminal pilot lug;
- body catch clearance ear;
- body catch terminal pilot lug;
- handle fork clearance ear;
- handle fork terminal pilot lug.

The separate latch lever pivot hole is already round because it prints flat. The handle's own pivot eye uses another rotated teardrop helper.

The current maximum integrated hardware bore is only the M3 clearance bore at `3.4 mm`; M3 pilot is `2.6 mm`, M2 clearance is `2.3 mm`, and M2 pilot is `1.7 mm`. These are short horizontal bridges, not large unsupported cavities. A normal circular hole is the better trade here: stronger ligament above the bore, no teardrop apex, cleaner screw fit, and better appearance.

The printability requirement should therefore be revised from "every horizontal bore must be mathematically self-supporting" to "the part prints without added slicer supports; small circular M2/M3 bores are explicitly allowed to bridge their short roof span."

---

# 2. Required change A — fuse gussets directly into the real local wall

## 2.1 Preserve the current root system

Do **not** replace `_root_profile_yz()` / `_root_taper_prism()` with a large rectangular backing block. The current tapered exterior root is a good concept and should remain.

Do not move the child-field mating face inward. Do not grow into child-bin capacity. Any strengthening must remain in the existing wall band or outside it.

## 2.2 Change the ear/gusset wall anchor from root-face based to local-wall based

For every body-side ear, determine the actual local outer wall position over the axial width of that ear, not the global/worst crest of the entire root.

Recommended helper concept:

`_local_wall_crest_for_ear(layout, x_centre, ear_thickness, outward_sign)`

Use the existing `_wall_extreme_y()` over `[x_centre - ear_thickness/2, x_centre + ear_thickness/2]` so the support is guaranteed to reach the wall over the ear's real width.

Then give the gusset a deliberate bite *into* the structural wall band:

- rear hinge / `outward_sign=+1`: `gusset_root_y = local_rear_crest - wall_bite`;
- front latch / `outward_sign=-1`: `gusset_root_y = local_front_crest + wall_bite`.

The final cavity subtraction remains authoritative, so an intentionally generous bite cannot steal child-bin volume.

Add one centralized constant or derived rule for this bite. Target roughly `0.5-0.8 mm` of positive wall engagement at the minimum B4B wall, but derive/cap it so it never assumes a thicker wall than exists. A reasonable implementation shape is:

`wall_bite = min(0.7, 0.5 * eff.wall_depth)`

The exact number is less important than these invariants:

- positive-volume wall overlap, never tangent-only contact;
- at least several extrusion-line widths of useful attachment on the standard B4B wall;
- no cavity intrusion after the existing cavity trim;
- no new unsupported underside.

## 2.3 Apply to all body-side hardware that uses the shared root/gusset pattern

Mandatory:

- `_hinge_body_parts()` — both ears of both rear hinges;
- `_latch_body_parts()` — both ears of every body catch receiver.

Shared-helper audit:

- `_handle_body_parts()` uses the same pattern and must be checked. Do not leave the handle forks using an old root-face anchor if the hinge/latch path is corrected.

## 2.4 Lid-side fittings

The lid-side hinge and latch fittings use `_lid_root_profile()` and local `layout.rear_wall_y(...)` / `layout.front_wall_y(...)` references rather than the body root-face pattern. Do not mechanically apply the body fix to the lid.

Instead verify:

- `_hinge_lid_parts()` remains positively unioned through the full intended arm into the secure lid plate;
- `_latch_lid_parts()` remains positively unioned through the full intended arm into the secure lid plate;
- the existing `B4B_LID_ROOT_BITE`, `B4B_LID_ROOT_REACH`, secure lid skin, and fillet still provide a continuous load path.

Only change lid-root geometry if inspection after the body fix shows an actual gap or tangent-only union.

## 2.5 Preserve printability

The new gusset/root edge must still use a downward surface at 45 degrees or shallower. Do not improve fusion by adding a horizontal shelf under the hinge/catch.

---

# 3. Required change B — uniform pivot-stack outside diameter; remove the oversized ring

## 3.1 Remove the visible local head flare as a separate outer diameter

`_ear_solid()` should no longer add a larger-radius outboard `pad` around the head-side ear for hinges/latches.

The intended visual/mechanical result for a hinge is:

`same outside barrel radius -> gap -> same outside barrel radius -> gap -> same outside barrel radius`

The outboard screw head may sit against the first ear, but the printed ear itself should not have a larger washer-like ring.

## 3.2 Define "uniform" per functional pivot stack

Do not force unrelated mechanisms to one global diameter.

Uniform means:

### Rear hinge

- body near ear;
- lid centre ear;
- body far/thread-forming lug;

all use the same outside pivot radius for that hardware family.

### Front latch pivot

- lid near ear;
- separate latch lever pivot end;
- lid far/thread-forming lug;

all use the same outside pivot radius for that family, subject to the lever's existing strap blend.

### Body catch receiver

The two body ears carrying the catch screw must use the same outside `catch_radius`; no larger head-side ring.

The latch hook around the catch pin is a separate moving feature and does not need to equal the catch-ear diameter.

### Handle

The handle shares `_ear_solid()`. Removing the flare must not accidentally break the handle. The two body fork ears should not retain an oversized head-side ring. The handle eye may remain at its deliberately chosen eye radius if the small radius difference is functionally useful, but no one-sided flare should remain.

## 3.3 Revisit the head-bearing rule instead of preserving `head_flare_radius`

The current validation uses `head_clear` plus `head_edge_margin` to justify a larger flare. That is too conservative for this compact fitting because `head_clear` is being treated as if the printed ear must surround a free-clearance circle around the entire screw head.

Refactor the profile semantics so head bearing is checked against the **actual socket-head outside diameter envelope**, not the through-head clearance envelope.

Recommended data model:

- retain `head_clear` only if some other geometry genuinely needs clearance around the head;
- add/rename a value representing maximum expected physical screw-head OD for the chosen common M2/M3 socket-head kit;
- add a modest printed bearing margin appropriate for a screw head clamping against a solid end face;
- derive the required uniform pivot/catch radius from that value plus the existing bore-shell requirement.

Do not invent a large margin that recreates the same oversized ring under a different name.

If the ordinary current radius is a fraction too small for M3, the preferred correction is a **small uniform increase to the entire stack**, e.g. all M3 hinge/latch pivot members together, rather than a large near-ear flare. Keep the adjustment minimal and re-run motion/projection checks.

In particular, review `catch_radius=2.7` for M3. If an M3 socket-head cannot bear cleanly on a 5.4 mm catch ear, increase the M3 catch radius slightly and apply it to *both* catch ears. Do not put the 3.6 mm flare back on only the head side.

## 3.4 Delete/update obsolete flare behavior and reporting

Once the local flare is gone:

- remove `head_flare_radius` if it has no remaining purpose, or stop using it for visible geometry;
- update `HardwareProfile.head_bearing_margin` to use the uniform stack radius and the actual head OD rule;
- remove `hinge_flare_projection` / `hinge_flare_projection_mm` if it no longer describes real geometry;
- update comments on `B4B_HINGE_MAX_PROJECTION` and `B4B_HANDLE_MAX_PROJECTION` that currently mention the local head flare;
- make assembled-envelope reporting use the real uniform hardware envelope rather than `head_flare_radius`;
- update any validation that currently assumes the flare exists.

Do not change screw lengths, thread engagement, axial stack widths, or M2/M3 family selection merely because the outer ring is removed.

---

# 4. Required change C — round screw/pin bores instead of teardrops

## 4.1 Keep the support-free *outer barrel* profile

Do not confuse the outer boss with the hole.

`support_free_profile_yz()` can remain for the outside of horizontally printed hinge/latch/handle bosses. Its faceted lower surfaces are useful and do not create the same internal stress concentration as a teardrop cutter.

The requested change is specifically the bore.

## 4.2 Replace integrated teardrop bores with true circles

Create/use one X-axis round-bore helper for integrated hardware. It should make a true circular Y/Z section and extrude it along X.

Use the existing exact bore radii:

- M2 clearance `2.3 / 2`;
- M2 pilot `1.7 / 2`;
- M3 clearance `3.4 / 2`;
- M3 pilot `2.6 / 2`.

Do not enlarge them pre-emptively. If a physical print later shows consistent roof sag that impedes a clearance screw, calibrate the clearance diameter by a small amount; do not reintroduce a teardrop by default.

## 4.3 Update `_ear_solid()`

Replace:

`_support_free_bore(bore_r, ..., roof_sign)`

with the new round-bore cutter.

After this, `roof_sign` is no longer needed for the bore. Remove it from `_ear_solid()` and its callers unless some separate non-bore behavior still needs it.

This one helper change must be deliberately reviewed at every call site, because it touches more than the rear hinge.

## 4.4 Required call-site audit

### Rear hinge body

- near clearance ear -> round;
- far pilot/thread lug -> round.

### Rear hinge lid

- centre rotating clearance ear -> round.

### Front latch lid pivot

- near clearance ear -> round;
- far pilot/thread lug -> round.

### Front catch receiver on body

- near clearance ear -> round;
- far pilot/thread lug -> round.

### Separate latch lever

Already round in `b4b_latch_lever_profile()` via `Point(...).buffer(...)`. Preserve it.

### Handle body forks

Because they use `_ear_solid()`, both fork bores become round. Verify screw fit and the existing carry-stop geometry.

### Handle eye

`make_b4b_handle()` currently uses `_handle_bore_profile()`, which is another teardrop rotated for the handle's print pose. Replace this with a round bore as well. There is no reason to retain a teardrop in the handle eye while eliminating it from every other M3 pivot.

## 4.5 Remove dead helpers if unused

After migration, remove if they have no remaining callers:

- `support_free_bore_profile_yz()`;
- `_support_free_bore()`;
- `_handle_bore_profile()`.

Do not leave dead alternate geometry that a future change could accidentally start using again.

---

# 5. Mechanism-by-mechanism review matrix

The implementation is incomplete until every row below has been checked.

| Mechanism | Part | Root/load path | Outside diameter | Bore |
|---|---|---|---|---|
| Rear hinge | body near ear | direct gusset bite into real local rear wall + existing root | same hinge radius as other knuckles; no flare | round clearance |
| Rear hinge | lid centre ear | verify secure-lid arm/plate fusion | same hinge radius | round clearance |
| Rear hinge | body far lug | direct gusset bite into real local rear wall + existing root | same hinge radius | round pilot |
| Front latch pivot | lid near ear | verify secure-lid arm/plate fusion | same pivot radius; no flare | round clearance |
| Front latch pivot | loose lever | n/a; prints separately | existing pivot radius | already round; preserve |
| Front latch pivot | lid far lug | verify secure-lid arm/plate fusion | same pivot radius | round pilot |
| Front catch | body near ear | direct gusset bite into real local front wall + existing root | same catch radius as far ear; no flare | round clearance |
| Front catch | body far lug | direct gusset bite into real local front wall + existing root | same catch radius | round pilot |
| Front latch hook | loose lever | n/a | preserve hook geometry | preserve round pin arc/mouth |
| Handle fork | body near/far | audit same local-wall bite rule | no one-sided flare | round clearance/pilot |
| Handle eye | loose handle | n/a | keep intentional eye radius unless needed | round clearance |

---

# 6. Validation changes

## 6.1 Remove teardrop-specific validation assumptions

The current secure-lid validation contains a bridge check based on `head_flare_radius` and the support-free faceted flare. Once the flare is removed, this check must be rewritten around the real outer barrel profile or removed if it no longer proves anything useful.

Do **not** add a new rule that rejects circular horizontal M2/M3 bores. The design decision is now explicit: these small bores may bridge their short roof and still count as supportless printing.

## 6.2 Keep outer-barrel printability protection

The outer `support_free_profile_yz()` still needs to obey the existing short-flat / <=45-degree surface intent for body and flipped-lid print poses.

Retain a check on the largest actual outer boss radius if useful. Do not conflate that check with bore shape.

## 6.3 Add positive wall-fusion validation for body hardware

Current watertightness is not enough: a tangent or tiny sliver can still produce a technically watertight union.

Add a small geometry-level invariant for body hinge and catch roots:

- construct or reuse the body wall-band solid in the hardware X window;
- before final body union, verify each hinge/catch support has positive intersection volume with that wall band;
- the intersection must represent intentional attachment, not numerical noise.

This can be a targeted test rather than an expensive runtime check if runtime cost is undesirable.

At minimum test both M2 and M3 cases and place hardware over different wave phases so a crest-only implementation cannot pass accidentally.

## 6.4 Update head-bearing validation

Replace `head_bearing_margin` logic that depends on `head_flare_radius` with the new uniform-radius / real-head-OD rule.

Acceptance is not "the head-clearance circle fits inside the boss." Acceptance is "the actual screw head bears on enough printed material to clamp reliably without requiring a visible oversized collar."

## 6.5 Preserve all existing mechanical checks

These must continue to pass:

- screw engagement and tail;
- body/lid watertightness;
- latch release geometry;
- latch swing;
- lid 120-degree opening sweep;
- handle swing/stop when enabled;
- hinge/latch root corner keep-out;
- projection ceilings;
- child field/capacity unchanged.

---

# 7. Targeted tests only

This is a localized mechanical tweak. Do not turn it into another broad test campaign.

Update/add only tests that protect the changed behavior.

## Required targeted tests

1. **Round bore helper**
   - M2 and M3 clearance/pilot profiles are circular;
   - no teardrop apex;
   - diameter equals requested bore diameter.

2. **Uniform hinge stack diameter**
   - for M2 and M3, near/head ear, middle lid knuckle, and far lug use the same nominal pivot radius;
   - no separate `head_flare_radius` mesh extends the near ear.

3. **Uniform catch receiver diameter**
   - near and far body catch ears have the same outer radius;
   - any M3 radius adjustment is shared by both.

4. **Positive local-wall fusion**
   - one representative M2 secure case and one representative M3 secure case;
   - verify each body hinge ear/gusset and each body catch ear/gusset has intentional positive overlap with the actual wavy wall band;
   - select dimensions/centres that put at least one ear away from a wave crest.

5. **Existing mechanics smoke check**
   - run the existing focused B4B mechanics/opening/latch tests for one M2 and one M3 case;
   - include handle once because `_ear_solid()` is shared.

Do not run the entire repository test suite unless one of these localized changes unexpectedly touches non-B4B code.

---

# 8. Implementation order

1. Add the local-ear wall-crest helper and wall-bite rule.
2. Apply direct wall bite to `_hinge_body_parts()` and `_latch_body_parts()`; audit `_handle_body_parts()`.
3. Add the round X-axis bore helper.
4. Convert `_ear_solid()` and all callers; convert the handle eye.
5. Remove the head-side flare from `_ear_solid()`.
6. Re-derive uniform pivot/catch radii from bore shell + actual screw-head bearing needs; change radii only if required.
7. Delete/update obsolete flare/teardrop constants, helpers, comments, validation, metrics, and envelope reporting.
8. Run the targeted tests above.
9. Generate one M2 and one M3 secure B4B preview and visually inspect rear hinge + front latch/catch from oblique angles.

---

# 9. Visual acceptance criteria

The work is not complete merely because meshes are watertight.

Rear hinge:

- no visible daylight/gap between a body hinge support web and the wavy bin wall where useful attachment area exists;
- gusset visually grows out of the wall/root rather than hanging off the outer root face;
- all three hinge knuckles read as one uniform barrel diameter;
- no washer-like oversized ring on one end;
- bore is visibly round.

Front latch/catch:

- body catch supports grow cleanly into the real front wall;
- paired catch ears are the same outside diameter;
- lid pivot ears and lever pivot read as one coherent pivot size;
- no head-side oversized ring;
- all pin/screw bores are round.

Handle:

- no regression from the shared helper changes;
- no oversized head ring on the fork;
- round pivot holes;
- carry stop and stow clearance unchanged.

---

# 10. Mechanical acceptance criteria

- Child-bin capacity and B4B outer wall semantics unchanged.
- Exactly two rear hinges remain.
- Latch count rule unchanged.
- M2/M3 family selection unchanged unless an existing physical-fit bug is discovered.
- Existing standard screw lengths remain valid.
- No nuts/inserts added.
- No support material required for normal slicing; short bridge/sag at the roof of a 1.7-3.4 mm round horizontal bore is explicitly acceptable.
- No horizontal underside/shelf is introduced under body hardware.
- Hinge opens to 120 degrees without new collision.
- Latches release/swing without new collision.
- Handle still folds/deploys if enabled.
- Body and lid remain watertight.
- Hardware projections do not increase materially; they should normally decrease because the head flare disappears.

---

# 11. Non-goals

Do not use this task to redesign:

- hinge count or hinge placement philosophy;
- latch strap/hook concept;
- screw family or screw lengths;
- handle shape;
- secure-lid plate/skirt architecture;
- stacking;
- labels;
- B4B capacity semantics;
- web UI;
- preview renderer.

This is a geometry refinement pass, not B4B v2.

---

# 12. Final gap check before declaring complete

The implementing LLM must explicitly answer all of these in its completion note:

1. Do body hinge gussets now intersect the actual local rear wall at each ear, not merely the outer reinforcement root?
2. Do body catch gussets now intersect the actual local front wall at each ear?
3. Was the same shared-root issue audited on the handle forks?
4. Are rear hinge near/mid/far outer radii uniform?
5. Are latch-pivot near/lever/far outer radii coherent and free of a one-sided flare?
6. Are paired catch ears the same outer radius?
7. Is `head_flare_radius` removed from visible geometry and from stale metrics/validation?
8. Are every M2/M3 hinge/latch/catch bore circular?
9. Is the handle eye circular too?
10. Are the separate latch lever pivot and hook pin geometry still round and unchanged where already correct?
11. Were body/lid/latch/handle motion checks rerun after the geometry changes?
12. Were only targeted B4B tests used unless a real cross-module regression forced broader testing?

If any answer is "no", the tweak is not complete.