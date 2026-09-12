# Fix B4B hardware redesign — authoritative dimensional implementation specification

Status: **design complete; implementation-ready.** This document is intended to remove design discretion from the coding LLM. The coding LLM should review the geometry for mathematical/boolean feasibility, concur or identify a concrete impossibility, and then implement this specification. It should **not** independently redesign the hardware, rescale parts by taste, choose different screw families, add new user options, or substitute percentage-based geometry unless this document explicitly calls for it.

The only expected post-implementation tuning is physical-print calibration of: printed thread-forming pilot diameter, tiny detent interference, and at most +/-0.05 mm running-fit adjustments. Those calibration values must remain centralized constants. Everything else below is the intended first-build design.

The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their absolute dimensions or case geometry. Preserve their useful design language: clean compact hardware, thin folding parts, rounded/tapered load paths, minimal projection, and hardware that looks grown from the case rather than attached as large blocks.

---

# 1. Authoritative product rules

1. B4B is a carrying/storage case, not merely a normal Wavefinity bin with hardware added.
2. Entered B4B X/Y are the authoritative child-bin field dimensions.
3. Minimum child field is exactly **48.00 x 48.00 mm (6U x 6U)**.
4. B4B X/Y/Z must never silently grow merely to make hinges, latches, or a handle fit.
5. B4B wall minimum/default is exactly **1.20 mm**.
6. Every secure B4B has exactly **two rear hinges**.
7. Secure-lid minimum entered child height is **16.00 mm**. Reject/disable a secure lid below this rather than silently increasing Z.
8. Lid opening requirement is **120.00 degrees nominal**. Validate the complete sweep from closed through 120 degrees.
9. Fastener diameter is never exposed to the user.
10. Hardware family is selected automatically from one authoritative helper.
11. Ordinary metric socket-head cap screws are used. No nuts, heat-set inserts, shoulder screws, rivets, specialty hinge pins, or user-supplied metal rods.
12. Screws pass through clearance-bored moving members and thread-form into the far printed lug.
13. Body prints upright.
14. Lid prints upside down.
15. Latch levers print flat on one broad face.
16. Handle prints flat on one broad face.
17. **No B4B part may require slicer supports.**
18. Carrying handle is a folding **front/body-mounted** U/bail. No top handle remains.
19. A handle requires a secure lid and latches.
20. A handled B4B uses M3 hardware for the whole case.
21. Stacking and the front handle are compatible unless an actual geometry collision is found.
22. The design language is **elegant strength**: compact pivots, local screw-head reinforcement only, tapered roots, real load paths, restrained projection, and no giant rectangular mounting pads.

---

# 2. Existing global Wavefinity geometry that remains authoritative

Unless another section below explicitly replaces a value, retain these existing Wavefinity fundamentals:

- grid pitch: **8.00 mm**;
- wave length: **4.00 mm**;
- wave amplitude: **0.40 mm**;
- wave mating gap: **0.25 mm**;
- corner inset: **1.00 mm**;
- B4B lid seat clearance: **0.15 mm**;
- passive lid skin: **1.60 mm**;
- secure lid skin: **2.40 mm**;
- lid locating skirt wall: **2.00 mm**;
- nominal skirt lap: **4.00 mm**, still capped by available headroom as current code does;
- support-free horizontal bore roofs: reuse the existing proven teardrop/self-supporting construction, parameterized by the new bore radius;
- support-free bridge upper bound: **3.00 mm**.

Do not re-phase the waves, change the child-field semantics, or buffer the authoritative mating wall in a way that breaks Wavefinity phase compatibility.

For reference, with a 1.20 mm B4B wall:

- max wave slope = `0.4 * 2*pi/4 = 0.62831853`;
- wall depth = `1.20 * sqrt(1 + slope^2) = 1.41721 mm`;
- 48.00 mm child field physical exterior is approximately **51.88442 mm** in X/Y using the current B4B outward-wall math.

---

# 3. Wall-thickness policy for ordinary bins and B4B

## 3.1 New ordinary-bin choices

Expose only:

- **0.40 mm — Very thin / prototype**
- **0.80 mm — Standard**
- **1.20 mm — Strong**
- **1.60 mm — Heavy**
- **2.00 mm — Extra heavy**
- **2.40 mm — Maximum**

Do not add 0.50 / 1.00 / 1.50 or retain a 0.20-step selector for newly chosen values.

Ordinary-bin default remains **0.80 mm**.

Legacy saved ordinary bins with non-preset values remain loadable and geometrically unchanged. UI may display `Legacy/Custom X.XX mm` until the user selects a current preset.

## 3.2 B4B choices

B4B always shows Wall thickness directly. Allowed new selections:

- **1.20 mm — Standard B4B / Strong**
- **1.60 mm — Heavy**
- **2.00 mm — Extra heavy**
- **2.40 mm — Maximum**

Default = **1.20 mm**.

Entering B4B from a thinner ordinary bin promotes the active wall to 1.20 mm. Preserve any value already >=1.20 mm.

An old saved B4B below 1.20 mm may be read for migration, but any new regeneration/edit must require/promote the design to at least 1.20 mm with a visible explanation.

## 3.3 Mode-required minimum helper

Centralize one helper such as `required_min_wall(mode/options)`:

- ordinary non-stacking: 0.40;
- direct-snap stacking: 1.20;
- lid stacking: 1.20 where the snap/groove load path requires it;
- B4B: 1.20.

When a mode forces a promotion, remember the prior ordinary-bin wall in transient UI state. If the user later disables that mode without manually editing wall thickness while the mode was active, restore the prior wall. If the user manually changed the wall while the mode was active, preserve the explicit choice.

---

# 4. Remove all silent B4B hardware-driven size growth

Delete/replace any logic that repeatedly grows X/Y or silently increases Z until old hardware fits.

Authoritative behavior:

- X/Y remain exactly the requested child field.
- X <48 or Y <48 => B4B unavailable/invalid.
- secure lid with child height <16.00 => unavailable/invalid.
- handle fit is an eligibility result; never an X/Y/Z growth request.
- stacking may still increase effective base thickness enough to preserve the required floor skin below stacking recesses; this does **not** authorize changes to child X/Y/Z.

The existing `b4b_effective_box()` should become an effective-material/base normalizer, not a hardware-driven dimension mutator.

---

# 5. Exact hardware profiles

Create a single immutable `HardwareProfile` or equivalent and make preview, generation, validation, and BOM consume the same resolved profile.

All dimensions below are exact first-build nominal values.

## 5.1 M2 compact

- family name: `M2`
- nominal diameter: **2.00 mm**
- rotating clearance bore: **2.30 mm**
- printed thread-forming pilot: **1.70 mm**
- minimum thread engagement: **2.40 mm**
- socket-head nominal diameter reference: 3.80 mm
- printed head clearance diameter: **4.20 mm**
- local head-bearing radial margin outside head-clearance circle: **0.50 mm**
- resulting local head-bearing flare radius: **2.60 mm**
- standard screw lengths: **6 / 8 / 10 / 12 / 16 mm**
- standard moving axial gap: **0.30 mm**
- minimum radial shell around rotating clearance bore: **1.20 mm**
- general compact pivot outer radius: **2.40 mm**
- maximum screw protrusion beyond far lug: **0.50 mm**

Physical calibration allowance after first prints:

- pilot may move from 1.70 by at most +/-0.10 without redesign;
- clearance bore may move from 2.30 by at most +/-0.05 if printer fit requires it.

## 5.2 M3 standard

- family name: `M3`
- nominal diameter: **3.00 mm**
- rotating clearance bore: **3.40 mm**
- printed thread-forming pilot: **2.60 mm**
- minimum thread engagement: **3.00 mm**
- socket-head nominal diameter reference: 5.50 mm
- printed head clearance diameter: **6.00 mm**
- local head-bearing radial margin outside head-clearance circle: **0.60 mm**
- resulting local head-bearing flare radius: **3.60 mm**
- standard screw lengths: **6 / 8 / 10 / 12 / 16 / 20 mm**
- standard moving axial gap: **0.30 mm**
- minimum radial shell around rotating clearance bore: **1.30 mm**
- general compact pivot outer radius: **3.00 mm**
- maximum screw protrusion beyond far lug: **0.50 mm**

Physical calibration allowance after first prints:

- pilot may move from 2.60 by at most +/-0.10 without redesign;
- clearance bore may move from 3.40 by at most +/-0.05 if needed.

## 5.3 Automatic family selector

One helper only:

1. if handle enabled => M3;
2. otherwise M2 when child X <=96.00 **and** child Y <=96.00 **and** child height <=64.00;
3. otherwise M3.

Do not create separate hinge/latch selectors.

## 5.4 Screw selector

For each screw path:

1. compute actual clearance stack from near entry face through all clearance members and running gaps;
2. compute actual far-lug thickness;
3. iterate permitted family lengths shortest-first;
4. require `length - clearance_stack >= minimum_thread_engagement`;
5. require `length - clearance_stack - far_lug <=0.50`;
6. choose first passing length;
7. if none passes, report a geometry design error. Do not accept an exposed long tail.

---

# 6. Rear hinge — exact first-build geometry

Exactly two hinges for every secure B4B.

## 6.1 Axial stack

### M2 hinge

Along X from the outboard screw-head side toward the case center:

- near body ear: **2.20 mm**
- running gap: **0.30 mm**
- lid center ear: **2.60 mm**
- running gap: **0.30 mm**
- far body thread-forming lug: **2.60 mm**

Total hinge-group axial width = **8.00 mm**.

Clearance stack before far lug = 2.20 +0.30 +2.60 +0.30 = **5.40 mm**.

Use **M2x8** by design:

- thread penetration = 8.00 -5.40 = **2.60 mm**;
- lug = 2.60 mm;
- exposed tail = **0.00 mm**.

### M3 hinge

Along X:

- near body ear: **2.80 mm**
- running gap: **0.30 mm**
- lid center ear: **3.20 mm**
- running gap: **0.30 mm**
- far body thread-forming lug: **3.40 mm**

Total = **10.00 mm**.

Clearance stack = 2.80 +0.30 +3.20 +0.30 = **6.60 mm**.

Use **M3x10** by design:

- thread penetration = **3.40 mm**;
- lug = 3.40 mm;
- tail = **0.00 mm**.

The general selector still verifies these results rather than hard-coding BOM strings.

## 6.2 Pivot radial geometry

M2:

- normal ear/center-ear pivot radius = **2.40 mm**;
- near-ear local head-bearing flare radius = **2.60 mm** only around the short head-bearing end.

M3:

- normal pivot radius = **3.00 mm**;
- near-ear local head-bearing flare radius = **3.60 mm** only around the head-bearing end.

Do not enlarge the lid center ear or far lug to the head-bearing radius.

Use the existing support-free faceted outer profile concept rather than a fully round horizontal barrel if a round underside would violate support-free print rules.

## 6.3 Rear axis Y starting position

For each hinge group determine the maximum local rear wall crest across that hinge/root X envelope.

First-build axis offset from that crest:

- M2: `2.40 +0.35 =` **2.75 mm** behind rear crest;
- M3: `3.00 +0.35 =` **3.35 mm** behind rear crest.

Expected nominal maximum pivot projection:

- M2: 2.75 +2.40 = **5.15 mm**;
- M3: 3.35 +3.00 = **6.35 mm**;

excluding the short head flare if it locally exceeds this.

Do not move the axis farther out preemptively.

## 6.4 Rear axis Z

Retain the useful print relationship:

`hinge_axis_z = secure_lid_top_z - normal_pivot_radius`.

Thus the upper flat/tangent region of the lid-side knuckle remains aligned with the broad lid top when the lid is flipped for printing.

## 6.5 Opening sweep and rear-lid relief

Validate lid positions every **5.00 degrees** from 0 through 120 inclusive.

If the starting Y location collides during sweep:

1. first introduce a support-free **45-degree rear lid relief/chamfer**, maximum relief depth **1.20 mm**;
2. grow relief only enough to clear the sweep;
3. only if 1.20 mm relief is insufficient may the axis move rearward;
4. rearward movement must be the minimum required and quantized in **0.05 mm** increments;
5. if M2 rear projection exceeds **5.75 mm** or M3 exceeds **7.00 mm**, flag for design review instead of silently accepting a backpack-like hinge.

This is an algorithm, not an invitation to redesign the hinge.

## 6.6 Hinge X placement

Nominal hinge centers:

`x = +/- child_x / 4`.

Root/corner clearance check:

- minimum root-to-corner-tangent clearance: **2.00 mm**.

If the nominal center violates that clearance, shift the affected symmetric pair inward by the minimum amount needed. Never shift outward. Preserve symmetry.

At the 48 mm minimum, nominal centers are exactly **+/-12.00 mm**.

## 6.7 Hinge root geometry

M2:

- pivot group width: 8.00;
- wall-contact/root width: **11.00 mm**;
- root coverage below the local top/rim zone: **8.00 mm**;
- target local total structural depth from inner mating face through outer reinforcement: **2.60 mm**.

M3:

- pivot group width: 10.00;
- wall-contact/root width: **13.60 mm**;
- root coverage below top/rim zone: **10.00 mm**;
- target local total structural depth: **3.00 mm**.

Implementation:

- pivot neck begins at group width;
- root widens linearly to wall-contact width;
- plan-view end transitions are 45-degree or shallower chamfers/tapers;
- Y/Z root underside also remains 45 degrees or shallower;
- extra depth grows outward only;
- no rectangular pad extending the full root envelope.

---

# 7. Front latch — exact first-build geometry

The old `Lightweight/Standard` design choice is retired for new designs. Geometry is determined by M2/M3 family.

## 7.1 Latch count

- child X <= **96.00 mm** => exactly **one centered latch**;
- child X > **96.00 mm** => exactly **two latches**.

One latch center = `x=0`.

Two latch centers = `x = +/- child_x/6` nominally.

If a true root/corner collision exists, move the pair symmetrically inward only as much as needed while maintaining at least **2.00 mm** root-to-corner-tangent clearance.

Do not change the 96 mm threshold in different code paths.

## 7.2 Latch pivot and catch axial stacks

Use the same compact screw-stack philosophy for both the lid pivot and body catch.

### M2 latch pivot/catch stack

Along X:

- near clearance ear: **2.20 mm**
- gap: **0.30 mm**
- lever or exposed catch span corresponding to lever width: **2.60 mm**
- gap: **0.30 mm**
- far thread lug: **2.60 mm**

Total = **8.00 mm**.

Use **M2x8**. Clearance span=5.40; engagement=2.60; tail=0.00.

### M3 latch pivot/catch stack

- near clearance ear: **2.80 mm**
- gap: **0.30 mm**
- lever/exposed center span: **3.20 mm**
- gap: **0.30 mm**
- far thread lug: **3.40 mm**

Total = **10.00 mm**.

Use **M3x10**. Clearance span=6.60; engagement=3.40; tail=0.00.

## 7.3 Lid pivot ear radial geometry

M2:

- normal pivot radius: **2.40 mm**;
- local near-ear head flare radius: **2.60 mm**.

M3:

- normal pivot radius: **3.00 mm**;
- local head flare radius: **3.60 mm**.

## 7.4 Body catch-ear radial geometry

These ears do not need to be as radially large as the rotating pivot region.

M2 body catch ear normal radius: **2.20 mm**.

M3 body catch ear normal radius: **2.70 mm**.

Near catch ear still gets the same local family head-bearing flare (2.60 M2 / 3.60 M3) only where the screw head bears.

## 7.5 Pivot/catch position relative to front wall

Determine the minimum local front-wall Y crest across the full latch/root X envelope.

Outward distances from that crest:

### M2

- lid pivot axis: **2.85 mm** outward = 2.40 radius +0.45 running space;
- body catch axis: **2.60 mm** outward = 2.20 radius +0.40 running space.

### M3

- lid pivot axis: **3.45 mm** outward = 3.00 +0.45;
- body catch axis: **3.10 mm** outward = 2.70 +0.40.

These are first-build positions. Do not add arbitrary extra standoff.

Expected normal closed projection near pivot:

- M2 ~5.25 mm before the short local head flare;
- M3 ~6.45 mm before the short local head flare.

## 7.6 Pivot/catch Z spacing

Set pivot Z from the secure lid top/ear print relationship:

`pivot_axis_z = secure_lid_top_z - pivot_radius`.

Catch-axis vertical drop from pivot:

- M2: **9.00 mm**;
- M3: **10.50 mm**.

Thus:

`catch_axis_z = pivot_axis_z - family_draw`.

Do not use old latch strength pad-height values.

## 7.7 Lever section

Axial extrusion width is already fixed by the stack:

- M2 lever X width: **2.60 mm**;
- M3 lever X width: **3.20 mm**.

In the Y/Z outline:

M2:

- strap body thickness normal to its centerline: **2.00 mm**;
- pivot end outer radius: **2.40 mm**;
- catch pin inner clearance radius: **1.25 mm** (`M2/2 +0.25`);
- hook wall radial thickness: **1.40 mm**;
- hook outer radius: **2.65 mm**;
- hook mouth clear height: **1.80 mm**;
- effective pin-mouth interference: **0.20 mm** versus 2.00 mm pin;
- lead-in chamfer/run at hook mouth: **0.60 mm**;
- finger-lip outward extension beyond strap: **1.20 mm**;
- finger-lip vertical length: **2.50 mm**.

M3:

- strap body thickness: **2.40 mm**;
- pivot end outer radius: **3.00 mm**;
- catch inner clearance radius: **1.75 mm** (`M3/2 +0.25`);
- hook wall radial thickness: **1.60 mm**;
- hook outer radius: **3.35 mm**;
- hook mouth clear height: **2.80 mm**;
- effective pin-mouth interference: **0.20 mm** versus 3.00 mm pin;
- lead-in chamfer/run: **0.80 mm**;
- finger-lip outward extension: **1.50 mm**;
- finger-lip vertical length: **3.00 mm**.

Use controlled fillets at the pivot-to-strap and strap-to-hook internal stress transitions:

- M2 fillet radius: **0.80 mm**;
- M3 fillet radius: **1.00 mm**.

Do not fillet the print-bed face in a way that loses a broad flat printing surface.

## 7.8 Latch root geometry

M2:

- total wall-contact root width: **10.80 mm**;
- vertical root coverage: **9.00 mm**;
- target local structural depth: **2.60 mm**.

M3:

- total wall-contact root width: **13.40 mm**;
- vertical root coverage: **11.00 mm**;
- target local structural depth: **3.00 mm**.

The root tapers from the ear stack into this wall-contact area. No broad rectangular receiver pad.

## 7.9 Latch movement validation

Closed pose = 0 degrees.

Validate lever sweep in **5-degree increments from 0 through 75 degrees open**.

Requirements:

- closed state has only intentional hook/pin detent contact;
- no broad body rubbing;
- by **25 degrees** open, the hook must be geometrically released from the catch pin;
- 25 through75 degrees must remain collision-free against body, lid, handle, and handle roots;
- latch must not self-release merely from upward lid load in closed position.

If tiny physical detent force needs tuning, only the **0.20 mm** mouth interference may move within **0.15–0.25 mm** after print testing. Do not alter the overall latch architecture to tune feel.

---

# 8. Folding front handle — exact first-build geometry

Handle is M3 only and promotes entire case hardware family to M3.

## 8.1 Handle shape

Single-piece U/bail, centered on front wall.

Nominal lower arm/grip in-plane band width: **6.50 mm**.

Front-to-back handle thickness when stowed: **5.80 mm**.

Near each pivot, taper the in-plane arm/eye axial width from 6.50 down to **5.40 mm** over a vertical run of **8.00 mm**. This narrower top section is what allows a compact M3x12 pivot stack.

Pivot-eye Y/Z outer radius around the horizontal X-axis bore: **2.90 mm**.

Pivot clearance bore: **3.40 mm** support-free horizontal profile.

Lower corner centerline radius: **7.50 mm**.

Preferred pivot-axis-to-grip-center drop: **29.00 mm**.

Minimum permitted drop: **26.00 mm**.

Do not increase drop above 29.00 merely because a case is tall; a hand does not benefit from indefinite growth.

Exposed front/back perimeter edge treatment: use a maximum **1.00 mm 45-degree chamfer** or equivalent support-free softening on non-bed edges. Preserve one truly broad flat print face.

## 8.2 Handle pivot screw stack

Each of two pivot forks, along X from outboard screw head toward case center:

- near body ear: **2.60 mm**
- running gap: **0.30 mm**
- handle eye axial thickness: **5.40 mm**
- running gap: **0.30 mm**
- far body thread lug: **3.40 mm**

Total = **12.00 mm**.

Clearance stack =2.60 +0.30 +5.40 +0.30 = **8.60 mm**.

Use **M3x12**:

- thread penetration = 12.00 -8.60 = **3.40 mm**;
- lug =3.40;
- tail =0.00.

Screw direction is mirrored:

- left pivot head faces left/outboard;
- right pivot head faces right/outboard;
- both far thread-forming lugs face inward toward case center.

## 8.3 Handle fork radial geometry

Normal body fork pivot radius around X-axis: **3.00 mm**.

Near-ear local head-bearing flare radius: **3.60 mm** only around head region.

Handle eye outer radius: **2.90 mm**.

## 8.4 Stowed Y position / wall clearance

When stowed, handle rear surface must clear the highest relevant front-wall crest by exactly **0.60 mm nominal**.

Therefore initial handle pivot-axis outward distance from the local front crest is:

`2.90 +0.60 =` **3.50 mm**.

Nominal handle eye frontmost projection =3.50 +2.90 = **6.40 mm**.

The local M3 screw-head flare may project up to approximately 3.50 +3.60 = **7.10 mm** at the short head-bearing region. This is acceptable; do not enlarge the entire fork to 7.10 mm projection.

Physical clearance tuning after first print may move 0.60 to **0.55–0.70 mm** only if needed.

## 8.5 Handle X span and exact eligibility algorithm

Define:

- family fork axial envelope width = **12.00 mm**;
- minimum fork/root-to-corner-tangent clearance = **2.00 mm** each side;
- lower arm/grip band width = **6.50 mm**.

Determine the usable straight-ish front span from the same B4B front-wall/corner geometry already used by hardware planning.

Maximum pivot-center span available:

`max_pivot_span = usable_front_span - 2*(12.00/2 + 2.00)`

which simplifies to:

`max_pivot_span = usable_front_span -16.00`.

Target clear grip:

`target_clear_grip = clamp(0.75 * child_x, 72.00, 95.00)`.

Required pivot-center span:

`required_pivot_span = target_clear_grip + 6.50`.

Eligibility requires:

`max_pivot_span >= required_pivot_span`.

If not, handle is unavailable. Do not reduce the clear grip below72.00 and do not enlarge the case.

For the current 1.20 wall geometry this should naturally make **96 mm child X the first grid-valid width** that supports a >=72 mm grip. The implementation must derive this from the formula and include a regression assertion that 88 mm does not fit while 96 mm does. Do not merely hard-code `if x>=96` without validating the geometry formula.

When eligible:

- pivot span = `required_pivot_span`, not the maximum available span;
- handle remains ergonomically centered instead of spreading to case edges;
- once target clear grip reaches95.00, larger cases retain that capped grip.

## 8.6 Handle Z placement and height eligibility

Pivot center nominally sits **8.00 mm below the body rim/lid-seat datum**.

Preferred drop to grip center =29.00.

Grip half-width vertically =6.50/2 = **3.25 mm**.

Required exterior bottom margin from lowest handle geometry to case bottom = **4.00 mm**.

Available drop calculation:

`available_drop = pivot_axis_z - 4.00 - 3.25`.

Use:

`handle_drop = min(29.00, available_drop)`.

Handle is eligible only if `handle_drop >=26.00`.

This makes the geometric minimum rim height:

`8.00 +26.00 +3.25 +4.00 = 41.25 mm`.

Do not convert this into an arbitrary child-height constant; calculate against actual rim Z, base thickness, and lid/headroom datums. With typical base/headroom values a ~40 mm child-height B4B should be near the minimum handle-capable height, which is intentional.

## 8.7 Lower U geometry

Arms descend vertically from pivot regions until the lower 7.50 mm centerline corner radii begin.

The lower grip is horizontal and centered.

Clear grip is measured between the **inner faces of the two vertical arms**, not pivot centers and not outside-to-outside width.

Nominal clear grip must match the target formula above to within **0.01 mm** mathematically before mesh tessellation.

## 8.8 Handle body roots

Each body fork root:

- fork axial envelope at pivot: **12.00 mm**;
- wall-contact/root X width: **16.00 mm**;
- total vertical wall coverage: **18.00 mm**;
- root extends **6.00 mm above** pivot center and **12.00 mm below** pivot center before fading completely into normal wall;
- target local total structural depth from inner mating face through outer reinforcement: **3.00 mm**;
- all added material outward only;
- X taper from16.00 wall contact to12.00 fork envelope;
- lower Y/Z transitions no steeper than45 degrees;
- no rectangular 16 x18 slab left visually exposed: perimeter must taper/chamfer into wall.

These roots are intentionally stronger/larger than latch roots because they carry the entire case.

## 8.9 Stow detents

Use two symmetric detents near the lower arms/corner region.

Each body bump:

- outward bump height: **0.35 mm**;
- matching handle pocket depth: **0.15 mm**;
- resulting nominal interference: **0.20 mm**;
- ramp run: **0.50 mm** minimum, producing a ramp shallower than45 degrees;
- detents symmetric left/right.

Physical tuning band: interference 0.15–0.25 only.

The grip must remain finger-accessible from below when stowed; do not add a separate finger tab.

## 8.10 Carry stop

Deployed stop angle = exactly **95.00 degrees from stowed** for first build.

At each pivot use a broad heel/stop contact face:

- minimum contact length in Y/Z section: **2.50 mm**;
- extruded across at least the **5.40 mm** handle-eye axial width;
- minimum nominal contact area therefore >= **13.50 mm^2** per pivot.

Stop must load printed plastic faces, not screw head/thread or a knife edge.

Validate handle every **5 degrees from0 through90**, plus exact **95 degrees**.

If the nominal stop produces a real collision at 95, geometry should be corrected around the stop/root. Do not casually choose a different angle. A post-print ergonomic change may later move the single centralized stop-angle constant within90–100 degrees.

---

# 9. Front interactions — latches, handle, labels

## 9.1 Latch/handle

Latches live high at lid seam. Handle pivots are 8.00 mm below rim and toward the outer front region.

Validate both latch-count modes against handle stowed and deployed sweeps.

No merging of latch and handle roots by accident. If envelopes approach, preserve at least **1.00 mm visible normal-wall separation** between finished tapered root regions whenever geometry allows. If a mathematically unavoidable overlap occurs on a valid dimension, report it for design review rather than silently unioning into one giant bracket.

## 9.2 Front label

With handle enabled, preferred front-label zone is the open center of the folded U.

Keep-outs:

- handle arms/grip outline plus **1.00 mm** label clearance;
- handle root/fork envelopes plus1.00;
- latch envelopes plus1.00.

Auto-fit label into remaining central opening. Never let label geometry intersect moving hardware.

If requested front label cannot fit at minimum readable size, report the fit failure or steer user to top label. Do not move the handle or latches just to preserve a label.

## 9.3 Stacking

Remove any normalization that disables handle simply because stacking is on.

Handle is front/body mounted; stacking features remain on top/bottom. Only a demonstrated geometry collision may invalidate the combination.

---

# 10. Print-orientation requirements

## 10.1 Body upright

- hinge/latch/handle-fork horizontal bores use existing self-supporting teardrop roof construction;
- no unsupported horizontal shelf under any pivot;
- gusset/root underside slopes <=45 degrees from vertical build support;
- no bridge spanning fork ears;
- decorative fillets may not create hidden unsupported downward arcs.

## 10.2 Lid upside down

- hinge and latch roots grow from bed-facing lid plate/edge;
- horizontal bore roof orientation flips correctly;
- no geometry assumes body support during printing;
- retain broad lid-top bed contact compatible with stacking geometry.

## 10.3 Latch lever flat

- one broad face fully bed-capable;
- pivot hole vertical in print pose and may be circular;
- hook outline support-free;
- no trapped support requirement inside hook mouth.

## 10.4 Handle flat

- one broad face fully bed-capable;
- horizontal X-axis pivot bores use teardrop/self-supporting roof;
- lower U radii are simply 2D outline geometry extruded through thickness and need no support;
- exposed-edge softening must preserve flat bed face.

---

# 11. UI behavior

New B4B UI:

- child X/Y minimum48;
- wall always visible, choices1.2/1.6/2.0/2.4;
- hardware family hidden;
- rear hinge count hidden/fixed at2 when secure;
- latch strength hidden/removed;
- latch count hidden/automatic;
- handle checkbox enabled only if secure lid is on and exact handle eligibility passes;
- if dimensions no longer support a previously checked handle, uncheck/disable it with concise visible reason;
- stacking + handle allowed;
- no UI action silently grows X/Y/Z for hardware.

Suggested handle-disabled reasons should be factual and dimensional, e.g.:

- `Handle needs at least 72 mm of clear grip width.`
- `Handle needs more front-wall height.`
- `Handle requires a secure lid.`

Do not expose engineering dimensions or M2/M3 decisions unless in an advanced report/BOM.

---

# 12. Saved-design migration

- preserve deterministic version-based migration;
- old latch strength/count fields may be read but normalize new geometry to the automatic rules above;
- old top-handle boolean maps to new front-handle intent, then passes exact eligibility validation;
- old handled+stacking design keeps handle if geometry now allows it;
- old B4B below1.20 wall must surface/promote the new minimum before regeneration;
- if schema semantics change materially, bump design version;
- never infer old/new semantics from dimensions alone.

---

# 13. Current code architecture to replace

The implementing LLM should specifically inspect and replace these old assumptions:

1. global M3-only pivot constants;
2. universal `B4B_HW_BOSS_RADIUS` used for every pivot member;
3. old 12.5+ mm hinge percentage/min-width logic;
4. secure-lid X-growth loop;
5. silent latch-driven Z growth;
6. `Lightweight/Standard` latch geometry as a new user choice;
7. old large latch pads/bosses;
8. old bulbous convex-hull lever;
9. top-arch `B4BHandlePlan`;
10. `_handle_arch()`, `_handle_span()`, `_handle_fits()`;
11. handle X-growth loop;
12. handle-driven lid thickness;
13. handle lid screw bores;
14. stacking=>handle-off normalization;
15. BOM strings assuming M3.

Replace with:

- central M2/M3 profile object;
- one family selector;
- exact profile-driven screw selector;
- exact hinge plans above;
- exact latch plans above;
- front-handle plan with span/drop/root/stop/detent fields;
- body handle forks;
- motion-sweep validators;
- explicit projection/root metrics.

---

# 14. Authoritative validation tolerances

Moving-part collision checks should not use large allowances that can hide a real clash.

Use:

- intended running gaps as modeled: typically **0.30 mm axial**, 0.35–0.60 positional clearances as specified;
- boolean/intersection numerical noise allowance: **0.05 cc maximum** only where existing mesh booleans require a volume tolerance;
- physical geometry clearance must be positive by construction rather than relying on the 0.05 cc allowance.

Screw acceptance:

- engagement >= family minimum;
- tail <=0.50 mm;
- preferred exact stacks above should normally produce zero tail.

Projection regression ceilings requiring explicit review if exceeded:

- M2 rear hinge: **5.75 mm**;
- M3 rear hinge: **7.00 mm**;
- M2 closed latch: **6.00 mm**;
- M3 closed latch: **8.00 mm** normal target, absolute review ceiling **9.00 mm**;
- handle body/eye normal folded projection: **7.25 mm** including local head flare.

If a generated model exceeds a review ceiling, fail validation or emit a clearly surfaced engineering error. Do not silently accept bulkier geometry.

---

# 15. Focused validation matrix

Do not return to broad low-value testing. These changes are a major mechanical redesign, so run the focused representative matrix below.

## 15.1 Minimum B4B

48x48, wall1.20, secure, child height <=64, no handle:

- M2;
- exactly2 hinges at +/-12 nominal centers;
- one centered latch;
- M2x8 hinge pins;
- M2x8 latch pivot/catch;
- no X/Y/Z growth;
- all support-free;
- lid sweep 0..120 by5 degrees;
- latch sweep0..75 by5 degrees;
- projections within limits.

## 15.2 Hardware thresholds

Test immediately below/at/above:

- X96;
- Y96;
- Z64.

All call paths must resolve the same family.

## 15.3 Latch-count transition

- X96 => one latch;
- next grid step X104 => two latches at nominal +/-17.333... mm before any necessary symmetric keep-out adjustment.

## 15.4 Handle width threshold

With1.20 wall and otherwise handle-compatible geometry:

- child X88 => exact formula must fail >=72 clear grip requirement;
- child X96 => exact formula must pass;
- at X96 target clear grip =72.00 and required pivot span =78.50 mm.

## 15.5 Handle height threshold

Create one case with rim height just below41.25 => handle unavailable.

Create one at/above41.25 => drop at least26.00 and handle available if width passes.

## 15.6 Handle motions

At smallest handle-capable case and a larger case:

- stowed clear wall by nominal0.60;
- detents engage;
- sweep0..90 by5 plus95;
- stop contacts broad faces;
- no latch collision;
- no label collision for a valid fitted label;
- M3x12 pivot screws;
- all case hardware M3.

## 15.7 Two-latch + handle

Use X>96:

- two latches;
- handle M3;
- all sweeps independent and collision-free;
- root regions remain visually separated.

## 15.8 Handle + stacking

- no top-handle conflict;
- stacking base/lid remains functional;
- handle does not alter stacking normalization except hardware family/secure requirement.

## 15.9 Large B4B

- M3 hardware remains fixed compact dimensions rather than scaling continuously;
- clear grip caps at95.00;
- handle does not widen to fill case;
- root widths remain fixed first-build dimensions unless an explicit structural rule says otherwise.

---

# 16. Implementation sequence

1. Simplify wall presets and implement B4B1.20 minimum/default.
2. Remove all hardware-driven X/Y/Z growth.
3. Enforce 48x48 minimum and16.00 secure-lid height minimum.
4. Add exact M2/M3 profiles and selector.
5. Add exact screw selector.
6. Rewrite rear hinge plan/geometry to exact stacks/radii/root values above.
7. Implement 5-degree lid sweep and relief-first collision resolution.
8. Rewrite latch count/profile/stack/lever/root geometry exactly as above.
9. Implement latch sweep/release validation.
10. Delete top-handle/lid-handle architecture.
11. Add exact front-handle eligibility/span/drop formulas.
12. Add exact M3x12 handle pivots, body forks, roots,0.20 detents,95-degree stop.
13. Reconcile front-label keep-outs.
14. Remove stacking=>handle-off behavior.
15. Make BOM/profile reporting authoritative.
16. Add projection/root/clearance metrics.
17. Run focused validation matrix only.
18. Remove dead constants/functions and update schema/UI migration.

---

# 17. Coding-LLM review instruction

Before implementation, the coding LLM should perform one short feasibility review of this specification against the current code and report only:

- any exact dimension/formula here that is mathematically impossible with the existing authoritative Wavefinity wall/lid datums;
- any Boolean construction that cannot represent the specified geometry without changing topology;
- any direct contradiction between two exact requirements.

It should **not** reopen choices merely because another design could also work.

If no contradiction exists, implement the plan as written.

If a contradiction exists, preserve the product intent and change the smallest possible dimensional item, documenting:

1. specified value;
2. why it is impossible;
3. replacement value;
4. exact downstream effect.

No unreported dimensional improvisation.

---

# 18. Final acceptance criteria

Implementation is accepted when:

- B4B minimum is48x48 at1.20 wall;
- no hardware-driven X/Y/Z growth remains;
- secure lid minimum height is validated, not auto-grown;
- secure cases always have2 compact rear hinges;
- hinge stacks resolve to M2x8 or M3x10 using the exact first-build stacks;
- lid opens through120 degrees without collision;
- one/two latch rule is exactly96 mm transition;
- latch stacks resolve to M2x8 or M3x10;
- latch lever is thin strap/hook, not bulbous old form;
- handle is front/body folding U, not top arch;
- handle width formula rejects88 and accepts96 at1.20 wall;
- handle requires >=72 clear grip and >=26 drop;
- handle pivots use mirrored M3x12 screws;
- handle has0.60 wall clearance,0.20 detents,95-degree stop;
- handle root loads enter a3.00 mm local structural zone with tapered geometry;
- stacking and handle coexist;
- all parts are support-free in mandated orientations;
- screw engagement/tails pass exact limits;
- projection ceilings pass;
- preview/export/validation/BOM all consume the same resolved plan;
- coding model did not add new user hardware/strength options;
- only centralized physical-calibration constants remain tunable after first prints.

At that point stop redesigning in software. Print the minimum M2 case, the smallest handle-capable M3 case, and one larger two-latch M3 case. Only actual print/fit/load evidence should justify changing the centralized calibration values or reopening a structural dimension.
