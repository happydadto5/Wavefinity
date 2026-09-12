# Fix B4B hardware redesign — final implementation plan

Status: **design review complete; implementation-ready.** The remaining uncertainty is ordinary physical calibration (printed pilot size, detent feel, and small tolerance tuning), not product architecture. Do not reopen the basic hinge/latch/handle concepts unless prototype evidence shows a real failure.

This document is implementation guidance for an LLM. The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their case geometry or absolute dimensions. Preserve the useful design language: compact hardware, clean proportions, rounded/tapered transitions, minimal protrusion, and parts that look integrated into the case rather than bolted onto large external blocks.

# 1. Authoritative product rules

1. B4B is a carrying/storage case, not merely a normal bin with hardware added.
2. Minimum entered B4B child field is **48 x 48 mm (6U x 6U)**. With the new 1.2 mm B4B wall this produces a physical case around 51.9 mm square. Do not silently grow smaller requested child fields to make hardware fit.
3. B4B wall minimum/default is **1.2 mm**.
4. Every secure B4B uses exactly **two rear hinges**.
5. Lid opening requirement is approximately **120 degrees**. Do not design for 180-degree fold-flat motion.
6. Fastener diameter is never a user setting. Hardware is selected automatically.
7. Use ordinary socket-head metric screws from common assortment kits. No nuts, heat-set inserts, shoulder screws, or specialty hinge pins.
8. Screws pass through clearance-bored moving members and thread-form into the far printed ear/lug.
9. Body prints upright. Lid prints upside down. Separate latch levers and the handle print flat on deliberate broad faces. **No B4B part may require slicer supports.**
10. Design language is **elegant strength**: compact pivots, local head reinforcement only, modest tapered ribs/chamfers, real load paths, and minimum external projection.
11. The carrying handle is a **folding front handle attached to the body**, never a top handle attached to the lid.
12. A handle is a carrying feature and therefore requires a **secure lid/latches**. Do not allow a handled B4B with a passive/unsecured lid.
13. Do not auto-grow B4B X/Y/Z merely to make hinges, latches, or handle hardware fit. Enforce minimums or disable incompatible options with an actionable explanation.
14. B4B stacking may still increase effective base/floor thickness when structurally required for the stacking recess. That is not permission to change the user's child-field X/Y/Z.

# 2. Wall-thickness policy — B4B and ordinary bins

## 2.1 B4B wall minimum/default

Use **1.2 mm as both the B4B minimum and default wall**.

A 0.8 mm wall can probably survive with enough local reinforcement, but it is the wrong baseline for a repeatedly opened, latched, hinged and carried case. With a nominal 0.4 mm nozzle, 1.2 mm is roughly a three-line wall and gives materially better stiffness and peel resistance.

B4B preserves the authoritative inner child field and grows structural wall material outward, so the capacity cost is effectively zero. Moving the minimum 48 x 48 child field from 0.8 to 1.2 wall only increases physical X/Y by about 0.94 mm total per axis.

When entering B4B from a thinner ordinary bin, promote the visible/effective wall to 1.2 automatically. Preserve any thicker user choice.

## 2.2 Simplified wall presets

For newly selected ordinary-bin wall values, expose only:

- **0.4 mm — Very thin / prototype**
- **0.8 mm — Standard**
- **1.2 mm — Strong**
- **1.6 mm — Heavy**
- **2.0 mm — Extra heavy**
- **2.4 mm — Maximum**

Do not add 0.5, 1.0, 1.5, etc. Exact extrusion width is slicer-dependent and those values only recreate an unnecessarily large option list.

Ordinary bins remain 0.8 mm by default. B4B always exposes **Wall thickness** directly and offers only 1.2 / 1.6 / 2.0 / 2.4.

The engine may continue accepting legacy non-preset values for compatibility. Ordinary saved designs with values such as 0.6, 1.0 or 1.4 should reopen unchanged; UI may show `Legacy/Custom X mm` until the user chooses a current preset.

For an old B4B saved below 1.2 mm, structural safety wins over preserving a newly generated weak case: the file may be read for compatibility, but regeneration/editing must clearly require/promote the B4B wall to at least 1.2 rather than silently exporting the old weak wall.

## 2.3 Mode-required minimum wall

Centralize one `required_min_wall(mode/options)` concept instead of scattering special cases:

- ordinary non-stacking bin: UI minimum 0.4;
- direct-snap stacking: minimum 1.2;
- lid stacking: minimum 1.2 when the snap/groove load path requires it;
- B4B: minimum 1.2.

Enabling a strength-requiring mode promotes a thinner wall to 1.2. Never silently reduce a thicker choice.

Where the browser maintains transient session state, remember the user's previous ordinary-bin wall when the mode itself forced a promotion. If the user turns that strength-requiring mode back off without manually changing wall thickness in the meantime, restore the prior ordinary-bin wall/default. If the user explicitly changed the wall while the mode was active, preserve the explicit choice.

# 3. Eliminate silent B4B size growth

The current `b4b_effective_box()` grows X until old reinforced hinges/handle fit and raises Z to the old latch minimum. That behavior must be removed for hardware fit.

New rule:

- X/Y are the requested child field and remain authoritative.
- Minimum B4B child field is 48 x 48; below that, reject/disable B4B rather than grow it.
- Keep a secure-lid minimum height of **at least the current 16 mm floor** unless the new latch geometry proves a higher minimum is required. Enforce the final minimum in validation/UI; do not silently increase Z.
- Handle eligibility is derived from actual width/height available. If it does not fit, handle is unavailable; the case remains valid.
- Stacking may still increase effective base thickness to preserve floor skin under recesses, but not child X/Y/Z.

Delete/replace any loops whose purpose is “keep growing until hardware fits.”

# 4. Shared automatic hardware profiles

Replace hard-coded M3 assumptions with a reusable internal hardware profile used by hinges/latches and consulted by the handle plan.

Recommended fields:

- name / nominal diameter;
- clearance bore;
- printed thread-forming pilot;
- minimum thread engagement;
- socket-head diameter/clearance;
- permitted standard screw lengths;
- running gap;
- minimum shell around clearance bore;
- minimum shell around pilot;
- local head-bearing margin;
- maximum screw protrusion.

## 4.1 M2 compact profile

Initial values to implement and physically calibrate:

- nominal: 2.0 mm;
- clearance bore: about 2.3 mm;
- printed pilot: about 1.7 mm initially;
- **minimum engagement: 2.4 mm**;
- local socket-head clearance: about 4.1–4.2 mm;
- standard lengths: 6 / 8 / 10 / 12 / 16 mm;
- prefer 8 or 10 mm pivots when possible.

## 4.2 M3 standard profile

Initial values:

- nominal: 3.0 mm;
- clearance bore: 3.4 mm;
- printed pilot: 2.6 mm initially;
- **minimum engagement: 3.0 mm**;
- local socket-head clearance: about 6.0 mm;
- standard lengths: 6 / 8 / 10 / 12 / 16 / 20 mm;
- prefer 10 or 12 mm pivots when possible.

Ordinary socket-head heads are roughly 3.8 mm diameter for M2 and 5.5 mm for M3. **Only the short local head-bearing region needs head-sized plastic.** Never let screw-head diameter determine the entire hinge/latch/handle pivot envelope.

## 4.3 First-implementation automatic selection rule

Make this deterministic so preview/export/BOM cannot disagree:

- if handle is enabled -> **M3 for the entire B4B**;
- otherwise M2 when child-field X <= 96 mm **and** child-field Y <= 96 mm **and** child height <= 64 mm;
- otherwise M3.

This is the first implementation rule, not a user setting. Physical load testing may later move the thresholds, but do not invent a different rule in separate call paths.

Prefer one hardware family for the entire case. A handled case is intentionally all-M3 rather than M2 hinges/latches plus M3 handle pivots.

## 4.4 Screw selection

For every pivot/catch:

1. calculate the true clearance-bored stack;
2. calculate physical far-lug thickness;
3. choose the **shortest allowed standard screw** that achieves minimum family-specific thread engagement;
4. prefer termination inside or flush with the far lug;
5. maximum acceptable protrusion past the far face: **0.5 mm**;
6. if no standard screw works, change the geometry rather than accepting a long exposed tail.

BOM must name the actual family/length used.

# 5. Rear hinge redesign

## 5.1 Current failure

The current hinge is M3-first: one universal head-driven boss, a 12.5 mm hard minimum width, and large external root web/pads. This makes small B4Bs look like thin organizer boxes with rugged-case hardware bolted on.

The existing concept of two body ears plus one lid center ear is mechanically good. Keep that topology but completely resize/re-root it.

## 5.2 Body ears

Each of the exactly two hinge groups gets two slim body ears:

- pivot section size = selected clearance bore + printable shell;
- near ear gets a short local head-bearing flare only;
- far ear is the thread-forming lug;
- axis is tucked as close to the rear wall as the motion sweep permits;
- a short neck leaves the pivot and flows into a shallow diagonal/trapezoidal rib;
- rib widens modestly as it meets the wall;
- root fades into rear wall with plan-view chamfers/tapers, not a broad rectangular pad;
- reinforcement grows outward only and never steals child-field capacity.

A local reinforced/root wall thickness around 2.4–3.0 mm total is acceptable when needed; taper it back into the 1.2+ shell.

## 5.3 Lid center ear

Use one compact center ear close to the rear lid edge. Carry load into the secure lid plate through a shallow triangular/trapezoidal arm reaching inward into the plate. Avoid the old oversized vertical tab.

The lid prints upside down. Evaluate geometry in print space:

- root grows from the bed-facing lid top/edge;
- horizontal bore uses the roof direction appropriate to the flipped lid;
- no unsupported shelf;
- transitions are vertical or <=45 degrees where they would otherwise overhang.

## 5.4 Axis placement and 120-degree sweep

Stop deriving hinge Y from `boss_radius + fixed_offset`.

Solve the closest collision-free axis from:

- closed lid/body geometry;
- lid rear edge thickness;
- body rim/rear wall;
- actual knuckle envelope;
- running clearances;
- sampled lid motion from 0 through approximately 120 degrees.

A small support-free relief/chamfer on the rear lid edge is preferable to moving the entire hinge farther behind the case.

## 5.5 Axial width and X placement

Stop using percentage-of-case-width as the primary hinge width rule.

Derive the three-knuckle stack from:

- selected hardware profile;
- running gaps;
- minimum far-lug engagement;
- near local head-bearing geometry.

Place the two hinges symmetrically toward the outer thirds while preserving corner keep-outs and visible separation between roots.

## 5.6 Hinge targets and validation

Design targets, subject to collision-free sweep:

- M2 hinge maximum rear projection preferably <= about 5.5 mm beyond local wall crest;
- M3 hinge preferably <= about 6.5–7 mm;
- no root web should be the feature that sets excessive projection.

Validate/report:

- exactly two hinges at 48 x 48 minimum child field;
- no hardware-driven X growth;
- hinge group width;
- max rear projection;
- root coverage;
- screw family/length;
- engagement and <=0.5 mm protrusion;
- closed clearance;
- sampled motion to ~120 degrees;
- upright-body and upside-down-lid support-free geometry;
- watertight solids.

# 6. Front latch redesign

## 6.1 Current failure

The current latch repeats the universal-M3-boss problem twice: large lid pivot ears, large body catch ears, broad pads, and a bulbous lever made from large circular ends. Its reinforced envelope and front projection are wildly disproportionate on a ~52 mm B4B.

Retain the basic mechanism but redesign every printed part around the selected hardware family.

## 6.2 Mechanism to keep

Retain:

- folding lever pivoted from the lid;
- metal screw-shank catch pin on the body;
- near clearance ear + far thread-forming ear at both pivot and catch;
- positive hook capture around the metal catch pin.

The screw shank remains the wear surface. No printed catch pin, nut or insert.

## 6.3 Body catch receiver

Replace broad pad/giant bosses with compact ears:

- radial size from bore + shell;
- local head flare only on near ear;
- far ear thick enough for family-specific thread engagement;
- catch pin only as far from wall as lever/hook clearance requires;
- each ear flows into the 1.2+ wall through a modest triangular/trapezoidal root;
- root tapers in X/Z rather than ending as a large block;
- all upright-print undersides remain vertical or <=45 degrees;
- child field remains untouched.

## 6.4 Lid pivot receiver

Use two compact ears at the front lid edge with the lever between them:

- pivot close to lid/front wall;
- local head flare only on near ear;
- far ear thread-forming lug;
- shallow tapered arms into secure lid plate;
- mechanism visually remains at the lid seam;
- support-free horizontal bore roof must be correct for the upside-down lid print orientation.

## 6.5 Lever

Replace the old convex-hull/two-large-disc form with a **thin folding strap** inspired by the reference latch:

- compact rounded pivot end;
- flat/slightly tapered strap body;
- modest finger lip at lower edge;
- integrated hook around catch screw;
- controlled fillets at pivot/strap/hook stress transitions;
- no large bulb at either end.

The lever prints flat on one broad face. Its pivot hole is vertical in that print orientation and can be round.

Hook behavior:

- closing rotation guides hook onto pin;
- modest detent/interference provides tactile retention;
- one-finger lift releases it;
- ordinary lid-opening force does not naturally self-release it;
- avoid a deep C-hook that needs large elastic flex every cycle;
- no sharp internal hook-mouth corner.

## 6.6 Latch count — deterministic first implementation

Retire user-facing latch count/strength complexity for new designs except where legacy data must remain readable.

First implementation:

- child-field X <= **96 mm** -> **one centered latch**;
- child-field X > **96 mm** -> **two latches**.

For two latches, target approximately one-third/two-thirds positions, i.e. centers near `+/- front_width/6` from case center, adjusted only enough for true corner/root keep-outs.

Do not decide count from whether two old-style giant pads happen to fit. The compact redesign must fit its intended count. If prototype closure testing later proves the 96 mm transition should move, change one authoritative threshold constant.

Retire `Lightweight / Standard` latch strength as a new user choice. Use one robust proportional profile per selected M2/M3 hardware family. Preserve legacy fields only for file migration/compatibility.

## 6.7 Latch projection target

- M2 compact latch: target roughly **5–6 mm maximum closed projection** beyond local front-wall crest;
- M3 latch: remain **under about 9 mm**, preferably less;
- root reinforcement must not be the reason projection grows.

Keep latch mechanism high at the lid seam. Lower/central front remains available for the handle.

## 6.8 Latch validation

Validate explicitly; do not rely on appearance alone:

- closed lever/catch relationship;
- intended tiny detent/contact only, no broad rubbing;
- opening sweep from closed through full release/open angle;
- hook clears catch after release;
- lever does not hit body, lid, handle or handle roots;
- one/two-latch placement is deterministic and symmetric;
- body upright support-free;
- lid upside down support-free;
- lever flat support-free;
- screw family/length/engagement/protrusion;
- max front projection;
- total latch/root envelope width;
- pivot/catch distance from wall crest;
- lever vertical extent below seam;
- watertight solids.

# 7. Folding front handle redesign

## 7.1 Replace, do not adapt, the current top handle

The current handle architecture is wrong for the requested product. It creates a large fixed arch on the lid, drills handle screws into the lid plate, thickens the lid so it becomes the thread-forming handle lug, and conflicts with stacking.

Remove that structural assumption completely.

The new handle attaches to the **B4B body/front wall**. The lid carries no handle load. Carrying force goes directly into the case shell rather than through the lid, latches and rear hinges.

Required consequences:

- remove handle-driven lid thickening;
- remove handle screw bores from lid;
- stacking and handle are no longer mutually exclusive;
- never auto-grow X/Y/Z for handle fit;
- handle roots become body hardware;
- handle remains one separately printed part;
- handle requires secure lid/latches.

## 7.2 Reference-handle design language

The reference handle is roughly 99 mm along its pivot span, ~27.6 mm U reach/drop and ~7 mm thick. Do not copy those numbers. Preserve:

- one clean U/bail;
- rounded pivot eyes at the two open ends;
- broad smooth lower radii;
- simple straight arms and grip;
- restrained local pivot thickening;
- compact folded state;
- no decorative complexity.

## 7.3 Orientation and motion

Mount the handle centered on the front wall. The two pivot eyes are collinear on one horizontal X-axis.

- **Stowed:** U hangs downward, nearly flat against front wall.
- **Carry:** U rotates outward to a broad mechanical stop.
- Initial stop target: **95 degrees** from stowed. Small tuning within roughly 90–100 degrees is acceptable only if required for comfortable clearance.
- Do not permit 180-degree rotation.
- Normal assembled preview shows the handle stowed.

The handle must not depend on screw threads/head as its rotation stop.

## 7.4 Handle shape and ergonomic targets

Single-piece U/bail:

- straight arms from pivot eyes;
- large-radius lower transitions;
- straight lower grip;
- rounded exterior edges and generous internal radii;
- local pivot-eye reinforcement only;
- no oversized circular end bosses.

Initial physical targets:

- in-plane band width: **6–7 mm**;
- front-to-back thickness folded: **5.5–6 mm**;
- minimum clear grip width: **72 mm**;
- preferred clear grip: **85–95 mm**;
- cap useful clear grip around **105 mm** rather than growing indefinitely;
- U drop from pivot axis to grip: **26–32 mm**, use as much of this range as available.

Keep cross-section approximately constant through grip/arms and thicken only locally around pivot eyes.

Target total folded front projection around **6–7 mm or less** from local front-wall crest, including running clearance.

## 7.5 Handle eligibility — never grow the case

A real adult handle does not belong on a 48–52 mm-wide minimum B4B.

Calculate handle eligibility from actual geometry:

- available front width after corner and pivot-root keep-outs;
- actual pivot-fork envelopes;
- true clear grip >=72 mm;
- vertical front-wall space below latch zone;
- achievable U drop >=26 mm;
- minimum **4 mm bottom margin** above the base/floor edge;
- latch and label keep-outs.

The width threshold will likely land around 88–96 mm child-field width, but **derive and round it to the next valid 8 mm grid size from actual geometry**. Do not hard-code the estimate instead of solving the geometry.

Likewise derive minimum handle-capable height. If the case is too narrow or short:

- handle is unavailable/unchecked;
- explain why concisely;
- do not change case dimensions;
- saved impossible handled designs fail validation with an actionable message.

## 7.6 Pivot architecture

Use two compact body forks, one at each handle end.

Each fork:

- near body ear: clearance bore + short local socket-head bearing flare;
- handle eye: clearance bore and rotates between ears;
- far body ear: M3 thread-forming pilot;
- one M3 socket-head screw passes through near ear -> handle eye -> far ear;
- shortest valid M3 screw, prefer M3x10 or M3x12, M3x16 only if genuinely needed;
- screw ends inside/flush or <=0.5 mm beyond far ear.

Mirror screw direction for clean assembly: **left pivot screw head faces the left/outboard side; right pivot screw head faces the right/outboard side.** Thread-forming far ears therefore face toward the center of the case. This keeps both screw heads accessible from the sides and keeps the visual center clean.

The screw remains stationary relative to body; handle rotates around the screw shank.

## 7.7 Body-side handle roots

These roots carry the full loaded case and may spread farther than latch roots, but must still look integrated.

Each pivot fork:

- only as far in front of wall as rotation requires;
- tapered into 1.2+ wall through narrow vertical/diagonal reinforcement;
- spreads load above/below pivot over meaningful wall height;
- local reinforced/root wall thickness around **2.4–3.0 mm total** is acceptable;
- all extra material grows outward;
- lower transitions vertical or <=45 degrees for upright printing;
- no broad rectangular mounting plate;
- no intrusion into child field.

## 7.8 Folded clearance and anti-rattle

Handle lies close to front shell without rubbing the wavy wall.

- use about **0.6 mm initial running clearance** to the highest relevant wall crest, then tune if physical prints show unnecessary looseness;
- do not create a thick flat backing pad merely to make the wall planar;
- add two small symmetric low-force stow detents near lower arms/corners;
- initial detent interference: **0.20 mm** (acceptable physical-tuning band about 0.15–0.25);
- approach/release faces <=45 degrees;
- grip remains finger-accessible from below when stowed.

No user setting for detent force.

## 7.9 Carry stop

Use broad printed heel/stop surfaces at both pivots:

- target ~95-degree deployed angle;
- stop loads broad plastic faces, never screw head/thread or a thin edge;
- stop geometry support-free in body and handle print orientations;
- include stop in sweep/collision validation.

## 7.10 Interaction with latches

Latches stay high at lid seam; handle pivots stay below them.

Validate one- and two-latch cases so:

- latch sweep never strikes stowed/deployed handle;
- handle sweep never strikes latch receivers/levers;
- two latch roots do not merge accidentally into handle roots;
- one centered latch remains clear of the central upper portion of the folded U;
- impossible shallow combinations disable handle rather than distort either mechanism.

## 7.11 Interaction with front labels

When handle is enabled, use the **open interior of the folded U** as preferred front-label zone.

- label layout accounts for handle outline, pivot roots and latch keep-outs;
- auto-fit/scale label into clear central area when possible;
- if it cannot fit, report clearly or direct user to top label rather than overlap;
- handle should visually frame, not cover, front label.

## 7.12 Interaction with stacking

Front handle and B4B stacking are compatible in principle because the handle no longer occupies the lid top.

Remove the old normalization rule that disables handle when stacking is selected. Reject only a real geometry collision, not an architectural assumption from the old top handle.

## 7.13 Handle print orientation

Handle prints separately on one broad face.

In this pose the pivot bores are horizontal. Use the same support-free/teardrop roof principle as other horizontal bores.

Requirements:

- broad flat print face;
- no support under lower U radii;
- pivot bores self-supporting;
- edge rounds/fillets do not create hidden down-facing overhangs;
- one watertight solid.

Body pivot forks print upright with support-free horizontal bores and no bridge spanning both ears.

## 7.14 Handle validation

Validate:

- smallest geometry-derived handle-capable B4B;
- case one grid step below threshold remains valid but handle unavailable;
- >=72 mm true clear grip;
- large B4B grip span capped ergonomically;
- stowed wall clearance/detents;
- folded projection target;
- sampled sweep from 0 to stop angle;
- no body/latch/label collision;
- carry stop contacts intended broad faces;
- all-hardware M3 promotion when handle enabled;
- exact screw lengths/engagement/protrusion;
- support-free body + handle;
- root load path into 1.2+ wall;
- watertight solid;
- regression metrics: pivot span, clear grip, U drop, band width/thickness, folded projection, root projection, screw dimensions.

# 8. B4B UI and saved-data behavior

## 8.1 New-design controls

For new B4B designs:

- Wall thickness always visible: 1.2 / 1.6 / 2.0 / 2.4;
- hardware size never visible;
- rear hinge count never visible: always two on secure lid;
- latch strength removed from normal UI;
- latch count automatic;
- handle checkbox only enabled when secure lid is enabled and current dimensions can support the handle;
- stacking and handle may coexist;
- no UI operation silently grows child X/Y/Z to make hardware fit.

## 8.2 Legacy fields

Keep old fields readable as needed to load prior designs, but new geometry is authoritative:

- legacy latch strength may be read/migrated but new designs use automatic family profile;
- old top-handle data maps to the new front-handle intent, subject to fit validation;
- old handled+stacking designs no longer need handle stripped merely because stacking is on;
- old sub-1.2 B4B wall must be surfaced as requiring the new minimum before regeneration.

If schema semantics materially change, increment the saved-design version and perform deterministic migration; do not infer version from dimensions.

# 9. Specific current-code architecture to replace

The implementation should explicitly remove old assumptions instead of leaving dead behavior:

1. Replace global M3-only constants/logic with `HardwareProfile` (or equivalent) and one authoritative selector.
2. Update `B4BHardwarePlan` to carry selected profile/family and remove assumptions that BOM strings are always M3.
3. Replace `_screw_for_stack()` hard-coded M3 engagement/protrusion logic with profile-driven values and <=0.5 mm protrusion.
4. Remove old `B4B_HW_BOSS_RADIUS` as a universal hinge/latch size. Head diameter may size only local head-bearing flares.
5. Remove `_hinge_width_for_case()` percentage/fixed-min architecture and derive hinge stack from hardware.
6. Remove secure-lid X-growth loop in `b4b_effective_box()`; enforce 48 mm minimum and actual geometry fit instead.
7. Remove silent `z = max(z, B4B_LATCHED_MIN_HEIGHT)` behavior; validate/UI-gate minimum secure height.
8. Retire `B4B_LATCH_PROFILES` Lightweight/Standard as a user-facing geometry choice; replace with family-proportional latch dimensions.
9. Replace old reinforced latch pad/boss architecture and bulbous lever.
10. Replace old top-arch `B4BHandlePlan` fields with front-bail plan fields: pivot centers/span, clear grip, drop, band width, thickness, eye geometry, wall clearance, stop angle, detent geometry, screw length.
11. Remove `_handle_arch()`, `_handle_span()`, `_handle_fits()` logic built around a lid-mounted arch.
12. Remove handle X-growth loop from `b4b_effective_box()`.
13. Remove handle-driven `B4B_HANDLE_LID_SKIN` path from `b4b_lid_skin_from_eff()`.
14. Remove `_handle_lid_bores()` and all handle drilling from `make_b4b_lid()`.
15. Add handle pivot-fork body geometry to `make_b4b_body()` when handle is enabled.
16. Rewrite `make_b4b_handle()` as separate front U/bail and preview it in folded pose.
17. Remove normalization that disables handle merely because stacking is enabled.
18. Make handle enablement force secure lid and M3 case hardware before any hinge/latch/handle plan is resolved.
19. Add actual handle eligibility and sweep validation rather than growth.
20. Add projection/width/BOM metrics to B4B summary/validation so oversized regressions are visible.

# 10. Support-free invariants

No implementation is acceptable if it needs slicer supports.

## Body upright

- all horizontal hinge/latch/handle-root bores use self-supporting roof geometry;
- no hidden underside shelves;
- root/gusset undersides vertical or <=45 degrees;
- no unsupported bridge between fork ears;
- exterior aesthetic fillets may not create down-facing unsupported arcs.

## Lid upside down

- hinge/latch roots build from bed-facing lid plate/edge;
- horizontal bores use flipped roof orientation;
- no feature relies on assembled body for support;
- top surface remains suitable for stacking/printing.

## Latch lever flat

- broad face down;
- pivot bore vertical in print pose;
- hook outline support-free;
- no support trapped in hook mouth.

## Handle flat

- broad face down;
- pivot bores horizontal but self-supporting;
- U radii and edge rounds support-free;
- one watertight solid.

Retain the existing support-free bridge discipline; a horizontal bridge around 3 mm is an upper bound, not a target to increase casually.

# 11. Focused validation matrix

Do not expand into a broad slow test campaign. Use geometry assertions/sweeps and a small representative matrix because these are mechanically consequential changes.

Required representative cases:

1. **48 x 48 minimum B4B, 1.2 wall, secure lid, no handle**
   - two hinges;
   - one latch;
   - M2 if height <=64;
   - no X/Y/Z growth;
   - support-free;
   - proportional projections.

2. **M2/M3 threshold cases**
   - immediately below and above each relevant 96/64 boundary;
   - preview/export/BOM same family.

3. **96 mm front-width case and next grid step above**
   - one latch at <=96;
   - two latches above 96;
   - symmetric placement, no collision.

4. **Smallest handle-capable case and one grid step below**
   - below: handle unavailable, B4B remains valid;
   - at threshold: >=72 mm clear grip, all hardware M3, secure lid required.

5. **Handle + one latch**
   - stowed/deployed sweep clear.

6. **Handle + two latches**
   - all sweeps clear, roots remain visually distinct.

7. **Handle + stacking**
   - no old top-handle conflict remains.

8. **Large B4B**
   - hardware does not balloon continuously with case size;
   - handle grip capped around ergonomic max;
   - M3 hardware remains compact.

9. **Long/narrow and tall cases**
   - automatic hardware selector responds to total case/load envelope;
   - no placement assumptions based only on X.

For moving mechanisms, sample enough intermediate angles to catch collision, not only endpoints.

# 12. Implementation sequence

1. Implement simplified wall preset policy, mode-required minimums, and B4B 1.2 wall default/minimum.
2. Enforce 48 x 48 B4B minimum and remove silent hardware-driven X/Y/Z growth.
3. Introduce shared M2/M3 hardware profiles and deterministic family selector; handle => secure lid + all-M3.
4. Convert screw selection/BOM to profile-driven standard lengths and <=0.5 mm protrusion.
5. Implement compact rear hinges and validate full ~120-degree lid sweep.
6. Implement compact front catch/pivot ears and flat strap latch lever.
7. Implement deterministic latch count: <=96 mm X one centered; >96 mm X two near one-third/two-thirds.
8. Delete old top-handle/lid-thickening/handle-vs-stacking architecture.
9. Implement front U/bail handle, compact body forks, mirrored screw heads, ~95-degree stop and light stow detents.
10. Implement geometry-derived handle width/height eligibility without case growth.
11. Reconcile front labels with latch/handle keep-outs and folded-U label zone.
12. Add authoritative projection/width/hardware/BOM metrics.
13. Run only the focused validation matrix above and visually inspect the representative meshes/previews.
14. Remove dead constants/functions and update saved-design migration/UI copy.

# 13. Final acceptance criteria

The redesign is complete only when all of the following are true:

- B4B begins at 48 x 48 child field and 1.2 wall without silent hardware growth;
- secure lid always has two proportional rear hinges;
- hinge opens ~120 degrees without collision;
- latches are slim, lie close to front, and count automatically by one authoritative rule;
- handle is a front folding U/bail attached to the body, not lid;
- handle requires secure lid, fits only where a real adult grip fits, and never grows the case;
- handle-capable cases use all-M3 hardware automatically;
- stacking and front handle coexist;
- no part requires slicer support;
- hardware heads enlarge only local bearing regions, not entire bosses;
- roots spread load through tapered/chamfered geometry rather than large blocks;
- screws use normal assortment lengths, meet engagement, and have <=0.5 mm exposed tail;
- minimum/transition/large representative cases look intentional rather than scaled copies of one rugged-case fitting;
- preview, export, validation and BOM all read the same resolved geometry/hardware plan;
- focused tests/sweeps cover the mechanical changes without returning to broad low-value test expansion.

At that point do not continue redesigning for aesthetics by guesswork. Print representative minimum, handle-threshold and larger cases; only physical failures or clearly visible proportion problems should drive another geometry iteration.
