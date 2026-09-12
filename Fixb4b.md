# Fix B4B hardware redesign

Status: design review complete enough for implementation planning. Rear hinges, wall policy, front latches, and the folding front handle are now defined. This document is implementation guidance for an LLM.

The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their case geometry or absolute dimensions. Preserve the useful design language: compact hardware, clean proportions, rounded/tapered transitions, and parts that look integrated into the case rather than bolted onto large external blocks.

# Global B4B rules

1. B4B is a carrying/storage case, not merely a normal bin with hardware added.
2. Minimum entered B4B child field is **48 x 48 mm (6U x 6U)**. Do not silently grow smaller requested fields to make hardware fit.
3. Every secure B4B uses exactly **two rear hinges**.
4. Lid opening requirement is approximately **120 degrees**, not 180-degree fold-flat motion.
5. Fastener diameter is never a user setting. Select hardware automatically.
6. Use ordinary socket-head metric screws from common assortment kits. No nuts, heat-set inserts, shoulder screws, or specialty pins.
7. Screws pass through clearance-bored moving members and thread-form into the far printed ear/lug.
8. Body prints upright. Lid prints upside down. Separate latch/handle parts must have deliberate support-free print orientations. **No B4B part may require slicer supports.**
9. Design language is **elegant strength**: compact pivots, modest ribs/chamfers, real load paths, minimal protrusion.
10. The carrying handle is a **folding front handle attached to the body**, never a top handle attached to the lid.
11. Do not auto-grow a B4B merely to make hinges, latches, or the handle fit. Enforce meaningful minimums or disable incompatible options.

# Phase 1 — Wall policy

## B4B wall minimum/default

Use **1.2 mm as both the B4B minimum and default wall**.

A 0.8 mm wall can probably survive with enough local reinforcement, but it is the wrong baseline for a case that is repeatedly opened, latched, hinged, and carried. With a nominal 0.4 mm nozzle, 1.2 mm is roughly a three-line wall and gives materially better stiffness and peel resistance.

Because B4B preserves the authoritative child field and grows wall material outward, the capacity cost is essentially zero. At the 48 x 48 child-field minimum, changing from 0.8 to 1.2 mm only increases the physical case by roughly 1 mm total in X/Y.

When entering B4B from a thinner ordinary bin, promote wall to 1.2 automatically. Preserve a thicker user choice.

## Simplified wall presets

For new ordinary-bin choices, expose only:

- 0.4 mm — Very thin / prototype
- 0.8 mm — Standard
- 1.2 mm — Strong
- 1.6 mm — Heavy
- 2.0 mm — Extra heavy
- 2.4 mm — Maximum

Do not add 0.5, 1.0, 1.5, etc. Exact extrusion width is slicer-dependent and those values only recreate an unnecessarily large option list.

Ordinary bins remain 0.8 mm by default. B4B always exposes Wall thickness directly and offers only 1.2 / 1.6 / 2.0 / 2.4.

Existing saved non-preset values should reopen unchanged for compatibility. Show them as a temporary Legacy/Custom value if needed; once the user chooses a current preset, use the simplified list.

## Mode-required minimum wall

Centralize the rule instead of scattering special cases:

- ordinary non-stacking bin: UI minimum 0.4;
- direct-snap stacking: minimum 1.2;
- lid stacking: minimum 1.2 if required by snap/groove geometry;
- B4B: minimum 1.2.

Enabling a mode that requires 1.2 promotes a thinner wall to 1.2. Never silently reduce a thicker choice.

# Phase 2 — Shared automatic hardware profiles

Replace hard-coded M3 assumptions with a reusable internal hardware profile shared by hinges and latches. The user never chooses screw diameter.

Prototype profiles to validate physically:

## M2 compact

- nominal: 2.0 mm
- clearance bore: about 2.3 mm
- thread-forming pilot: about 1.7 mm initially
- target engagement: roughly 2.4–2.8 mm
- local socket-head clearance: about 4.1–4.2 mm
- common lengths: 6 / 8 / 10 / 12 / 16 mm
- prefer 8 or 10 mm pivot pins when possible

## M3 standard

- nominal: 3.0 mm
- clearance bore: 3.4 mm
- thread-forming pilot: 2.6 mm initially
- minimum engagement: 3.0 mm
- local socket-head clearance: about 6.0 mm
- common lengths: 6 / 8 / 10 / 12 / 16 / 20 mm
- prefer 10 or 12 mm pivots when possible

Ordinary socket-head heads are roughly 3.8 mm diameter for M2 and 5.5 mm for M3. **Only the local head-bearing region needs head-sized plastic.** Never let screw-head diameter dictate the entire hinge/latch boss.

Hardware-family selection should consider overall case size/load, not only X width. A provisional non-handle envelope to test is M2 when both child-field plan dimensions are <= 96 mm and child height <= 64 mm; M3 otherwise. Final selection must be deterministic and shared by preview, export, validation, and BOM.

Prefer one hardware family for the whole case.

**Important handle rule:** a case with the carrying handle enabled is automatically promoted to **M3 hardware for the whole B4B**. A handle carries the entire loaded case; do not use tiny M2 pivots for that load, and do not mix M2 hinge/latch hardware with M3 handle hardware unless later physical testing proves promotion unnecessary. On a handle-capable case the redesigned compact M3 hinges/latches should still be visually proportional.

# Phase 3 — Rear hinge redesign

## Problem in current code

The current hinge is M3-first. A universal head-driven boss is used on every pivot, the hinge has a 12.5 mm hard minimum width, and the root becomes a large external web/pad. This makes small B4Bs look as if rugged-case hardware was attached to a thin organizer box.

## Geometry direction

Retain the useful three-knuckle concept: two body ears with one lid ear between them.

### Body ears

Each hinge group gets two slim ears:

- pivot size = bore + printable shell, not screw-head diameter;
- near ear gets a short local head-bearing flare;
- far ear is the thread-forming lug;
- axis tucked as close to the wall as motion allows;
- short neck from pivot into a shallow diagonal/trapezoidal rib;
- rib widens modestly as it meets the wall;
- root fades into the rear wall with plan-view chamfers/tapers rather than a broad rectangular pad;
- reinforcement grows outward only and never steals child-field capacity.

### Lid ear

Use one compact center ear and a shallow tapered arm reaching inward into the secure lid plate. Avoid the current oversized vertical tab.

The lid prints upside down, so all root geometry and horizontal bore roofs must be correct in that print orientation.

### Axis placement

Stop deriving Y position from boss radius plus a fixed offset. Solve the closest collision-free hinge axis from actual closed geometry and a sampled sweep through approximately 120 degrees. A small support-free relief/chamfer at the rear lid edge is preferable to moving the entire hinge farther out.

### Width/placement

Stop using percentage-of-case-width as the primary hinge-width rule. Derive the three-knuckle axial stack from:

- hardware profile;
- running gaps;
- thread engagement;
- local head-bearing geometry.

Place the two hinges symmetrically toward the outer thirds while preserving corner keep-outs and visible separation between roots.

### Regression metrics

Report/validate at least:

- hinge group width;
- maximum rear projection beyond local wall crest;
- root wall coverage;
- selected hardware and screw length;
- thread engagement/protrusion.

The 48 x 48 B4B must accept two hinges with no hardware-driven case growth.

# Phase 4 — Front latch redesign

## Problem in current code

The current latch repeats the same universal-M3-boss mistake twice: large lid pivot ears, large body catch ears, broad exterior pads, and a bulbous lever built from oversized circular ends. A standard latch can consume an enormous fraction of a ~52 mm front edge and project well over 10 mm from the wall.

## Basic mechanism to keep

Retain:

- a folding lever pivoted from the lid;
- a metal screw-shank catch pin on the body;
- near clearance ear + far thread-forming ear at both pivot and catch;
- positive hook capture around the metal catch pin.

This keeps wear on metal rather than a printed pin and stays within the no-nut/no-insert strategy.

## Body catch receiver

Replace the broad pad and giant bosses with compact ears:

- radial size from bore + shell;
- local head flare only on near ear;
- far ear thick enough for thread engagement;
- catch pin only as far from the wall as lever/hook clearance requires;
- each ear flows into the 1.2+ mm wall through a modest triangular/trapezoidal root;
- root tapers in X/Z rather than ending in a large block;
- all upright-print undersides remain vertical or <=45 degrees.

## Lid pivot receiver

Use two compact ears at the front lid edge with the lever between them. Root them into the secure lid plate with shallow tapered arms. Keep the mechanism visually at the lid seam rather than extending far down the front.

## Lever

Replace the current convex-hull/two-disc look with a **thin folding strap** inspired by the reference latch:

- compact rounded pivot end;
- flat/slightly tapered strap body;
- modest finger lip at the lower edge;
- integrated hook around the catch pin;
- fillets at high-stress strap/pivot/hook transitions;
- no huge bulb at either end.

The lever prints flat on a broad face.

## Latch count

Automatic only:

- one centered latch on small cases when sufficient;
- two latches on larger/wider cases, approximately near one-third/two-thirds positions.

Do not base two-latch eligibility on whether two oversized pads happen to fit. Base it on closure quality using the actual compact fitting envelope.

Retire the user-facing Lightweight/Standard latch-strength choice for new designs unless physical testing proves a real reason to keep it. Legacy data may remain readable.

## Front projection

Design targets:

- compact latch: roughly 5–6 mm maximum closed projection if geometry permits;
- larger M3 latch: remain in single-digit millimeters;
- root reinforcement should not be the part setting projection.

Latches remain high near the lid seam so the lower/central front is available for the handle.

# Phase 5 — Folding front handle redesign

## Current handle must be replaced, not adapted

The present implementation is the wrong architecture for the requested product. It creates a large fixed arch standing on the lid, drills two handle screws into the lid plate, thickens a handled lid so the lid itself becomes the thread-forming lug, and disables the handle when stacking is enabled because the arch occupies the lid top.

Remove that entire structural assumption.

The new handle is attached to the **B4B body/front wall**. The lid carries no handle load. This is structurally better: carrying force goes directly into the case body rather than through the lid plate and then through latches/hinges.

Consequences:

- remove handle-driven lid thickening;
- remove handle screw bores from the lid;
- stacking and handle are no longer mutually exclusive;
- do not auto-grow X just to fit a handle;
- handle geometry belongs to the body hardware plan, while the handle itself remains a separately printed part.

## Reference-handle design language

The supplied reference handle is approximately 99 mm along its pivot span, about 27.6 mm of U-shaped reach/drop, and 7 mm thick. **Do not copy those absolute values.** Preserve the concept:

- one clean U/bail shape;
- two rounded pivot eyes at the open ends;
- broad smooth radii at the lower corners;
- straight/simple arms and grip;
- no decorative complexity;
- compact when folded;
- looks like a purpose-designed case handle rather than a top-mounted drawer pull.

## Finished orientation and motion

Mount the handle centered on the front wall with its two pivot eyes on one horizontal X-axis.

- **Stowed:** U hangs downward and lies nearly flat against the front wall.
- **Carry:** U rotates outward approximately 90–100 degrees.
- Use a broad printed stop surface at each pivot so the carry position stops on plastic faces, not on screw threads or a thin edge.
- Do not design for 180-degree rotation.

The handle should display stowed in the normal assembled preview.

## Handle shape

Use a single-piece U/bail with:

- straight upper arms from the pivot eyes;
- large-radius lower transitions;
- a straight lower grip;
- rounded exterior edges and generous internal corner radii;
- slightly thickened/rounded material only around the pivot eyes;
- no oversized round end bosses.

Prototype physical targets for an M3 handle, to be tuned by geometry/print tests:

- in-plane band width: roughly **6–7 mm**;
- outward/front-to-back thickness when folded: roughly **5.5–6 mm**;
- minimum clear grip width: about **72 mm**;
- preferred clear grip width: roughly **85–95 mm**;
- cap useful clear grip around ~105 mm rather than making the handle continuously wider on huge cases;
- U drop from pivot axis to grip: roughly **26–32 mm** when space permits.

Keep the cross-section approximately constant through the arms/grip. Increase material locally at pivot eyes instead of making the whole handle bulky.

Target folded projection from the local front-wall crest at roughly **6–7 mm or less**, including running clearance. The handle itself, not a large wall pad, should set most of that envelope.

## Handle fit: never grow the case

A genuine adult carry handle cannot fit a 48–52 mm-wide minimum B4B and still be pleasant to use. Do not create a toy-sized grip merely so every B4B can claim to have a handle.

Resolve handle eligibility from actual available geometry:

1. available front width after corner/pivot-root keep-outs;
2. minimum ~72 mm clear grip;
3. pivot-eye/root width;
4. available vertical front-wall space below the latch zone;
5. bottom margin above the case floor/base edge.

Expected minimum handle-capable child-field width will likely land around **88–96 mm** after the final pivot stack is solved. Derive the exact grid-valid threshold from the geometry rather than hard-coding that estimate first.

Likewise, require enough vertical space for a useful ~26–32 mm drop. If the B4B is too shallow, the handle option is unavailable.

UI behavior:

- do not silently grow the case;
- if handle cannot fit, disable/uncheck the handle option with a concise explanation;
- increasing dimensions may make the option available again;
- saved designs requesting an impossible handle should fail with an actionable validation message rather than silently changing dimensions.

## Pivot architecture

Use **two compact case forks**, one at each end of the handle.

At each pivot:

- body provides a near ear and far ear;
- the single rounded handle eye rotates between them;
- near body ear has a clearance bore and only a local socket-head bearing flare;
- handle eye has a clearance bore;
- far body ear has the M3 thread-forming pilot;
- one ordinary M3 socket-head screw passes through the near ear + handle eye and thread-forms into the far ear;
- use the shortest normal screw that provides the required engagement and ends approximately flush/inside the far ear.

This architecture keeps the screw stationary relative to the body while the handle rotates around the screw shank. It avoids relying on a screw head rubbing directly against a moving handle and avoids nuts/inserts.

Prefer M3x10 / M3x12 if the final fork stack allows it; M3x16 only if structurally necessary. Do not enlarge the fork just to consume a convenient long screw.

## Body-side handle roots

The handle carries the entire loaded case, so its roots deserve more load-spreading area than a latch, but they still must look restrained.

Each pivot fork should:

- sit only as far in front of the wall as handle rotation requires;
- taper into the 1.2+ mm front wall with a narrow vertical/diagonal reinforcement zone;
- spread load above/below the pivot over a meaningful wall height;
- use 45-degree-or-shallower lower transitions for upright support-free printing;
- avoid a broad rectangular mounting plate;
- never intrude into the child field.

A local reinforced wall/root thickness around roughly 2.4–3.0 mm total may be appropriate even though the general wall is 1.2 mm. Achieve it by growing outward locally and tapering back into the shell.

The visual goal is two small pivot stations that look grown from the wall, not two giant blocks supporting a handle.

## Folded-state clearance and anti-rattle behavior

The handle should lie close to the local front-wall crest without rubbing across the wavy shell.

Use a small running clearance from the highest wall crest. Do not add a thick backing pad merely to create a flat landing surface.

Add a **very light automatic stow detent** so the handle does not flap/rattle:

- tiny chamfered wall bumps/rests with matching shallow pockets on the handle, or equivalent;
- target only about 0.15–0.25 mm interference initially;
- approach/release faces <=45 degrees;
- use two symmetric detents near the lower handle corners/arms rather than a giant central snap;
- handle should release easily with one finger from the lower grip edge.

This is not a user-adjustable setting.

The lower grip should remain reachable from underneath when folded, so no large stand-off or finger tab is required.

## Carry stop

Design a broad heel/stop at each handle pivot so rotation stops around 90–100 degrees on robust printed surfaces.

The stop must:

- not contact the screw head/thread as the primary stop;
- have enough area to avoid point loading;
- remain support-free on both the body and handle print orientations;
- be included in the handle sweep validator.

## Interaction with latches

Latches remain high at the lid seam. Handle pivots sit below them.

Validate both one- and two-latch layouts so:

- latch lever sweep never hits a folded or deployed handle;
- handle sweep never hits latch receivers;
- two latches leave the central/lower front visually clean;
- pivot-root reinforcement does not merge into latch-root reinforcement unless a deliberate shared structure is proven cleaner.

Do not distort the handle to fit an impossibly shallow case; disable handle instead.

## Interaction with labels

A front label may coexist with the handle by using the **open interior of the folded U as the preferred label zone**.

When handle is enabled:

- front-label layout must account for the handle outline and pivot/root keep-outs;
- auto-fit/scale the label into the open central area when possible;
- if a requested front label cannot fit, report that clearly or direct it to the top-label option rather than letting geometry overlap.

The handle should visually frame the label rather than cover it.

## Interaction with stacking

The new front handle **can coexist with B4B stacking** because it no longer occupies the lid top.

Remove the existing normalization rule that turns `handle` off whenever stacking is enabled. Stacking should only be rejected if a real body-envelope collision is found, not because the old top-handle architecture required a flat lid.

## Handle print orientation

The handle prints separately on one broad face.

Because the pivot bores run along the handle's in-plane pivot axis, they are horizontal in that print pose. Use the same support-free/teardrop roof concept used elsewhere rather than a fully round unsupported horizontal ceiling.

Handle requirements:

- broad flat print face;
- no support under U corners;
- pivot bores self-supporting;
- exterior edge rounds/fillets may not create hidden down-facing overhangs;
- one watertight solid.

Body pivot forks print upright:

- horizontal bores self-supporting;
- root undersides <=45 degrees or vertical;
- no bridge spanning the two ears.

## Handle validation

At minimum validate:

1. **Smallest handle-capable B4B**
   - geometry-derived width/height threshold;
   - true >=72 mm clear grip;
   - no case auto-growth;
   - no corner/latch collision;
   - visually proportional.

2. **Case just below the threshold**
   - handle unavailable with clear reason;
   - case itself remains valid B4B.

3. **Large B4B**
   - handle span capped to an ergonomic range rather than growing across the whole case;
   - pivot/root reinforcement remains restrained.

4. **Stowed pose**
   - wall running clearance;
   - anti-rattle detents engage;
   - front projection within target;
   - front label zone remains valid if used.

5. **Motion sweep**
   - sample from stowed through ~100 degrees;
   - no body/latch/label collision;
   - carry stop occurs on intended broad surfaces.

6. **Hardware**
   - case promoted to M3 when handle enabled;
   - both pivot screws use standard lengths;
   - minimum thread engagement proven;
   - screw ends inside/approximately flush with far lugs;
   - BOM clearly reports `2 x M3xN handle pivots`.

7. **Printability**
   - body upright support-free;
   - handle broad-face-down support-free;
   - all horizontal bores self-support;
   - no unsupported hidden shelves.

8. **Structural path**
   - pivot roots distribute carry load into a meaningful area of the 1.2+ mm wall;
   - no critical connection relies on tiny Boolean overlap;
   - handle pivot eyes have adequate shell around M3 clearance bore;
   - hard-stop forces enter broad root geometry.

9. **Regression metrics**
   - pivot span;
   - clear grip width;
   - U drop;
   - handle band width/thickness;
   - folded front projection;
   - pivot-root front projection;
   - screw length/engagement/protrusion;
   - handle-enabled hardware-family selection.

# Code-architecture changes implied by the handle redesign

The implementation should explicitly remove the old top-handle assumptions rather than leave dead behavior in place:

1. Replace the existing top-arch `B4BHandlePlan` fields with a front-bail plan: pivot centers/span, drop, band width, band thickness, pivot-eye size, front-wall clearance, stop angle, detent geometry, screw length.
2. Remove `_handle_arch()` / `_handle_span()` logic that exists to stand an arch on the lid.
3. Remove the `b4b_effective_box()` loop that grows X until the old top handle fits. Handle fit becomes validation/UI eligibility, never silent capacity growth.
4. Remove handle-driven `B4B_HANDLE_LID_SKIN` behavior from `b4b_lid_skin_from_eff()`.
5. Remove `_handle_lid_bores()` and all handle drilling from `make_b4b_lid()`.
6. Add compact body pivot-fork geometry to `make_b4b_body()` when handle is enabled.
7. Rewrite `make_b4b_handle()` as the separate front U/bail and put its normal assembly preview in the folded/stowed pose.
8. Change B4B normalization so stacking no longer disables the handle.
9. Make handle enablement promote the case hardware profile to M3 before hinge/latch/handle plans are resolved so every downstream path agrees.
10. Add handle sweep/fit/projection validation to the same authoritative mechanical validation path used for hinges/latches.

# Implementation sequence

1. Implement simplified wall preset policy and B4B 1.2 mm minimum/default.
2. Enforce 48 x 48 B4B minimum without hardware-driven growth.
3. Introduce shared automatic M2/M3 hardware profiles; include the rule that an enabled handle promotes the case to M3.
4. Implement compact rear hinges and validate the ~120-degree lid sweep.
5. Implement compact front catch/pivot ears and flat strap latch lever; resolve automatic one/two latch layout.
6. Delete the old top-handle/lid-thickening/handle-vs-stacking assumptions.
7. Implement the front U/bail handle, compact body pivot forks, carry stop, and light stow detents.
8. Add fit gating so undersized cases do not silently grow for a handle.
9. Reconcile front labels with the folded-handle interior opening.
10. Add projection/width/BOM regression values to B4B summary/validation.
11. Visually review minimum B4B, smallest handle-capable B4B, M2/M3 transition cases, two-latch cases, stacked cases, and large cases.

Do not spend time on broad test expansion. Preserve/update tests that directly encode changed geometry/behavior and add only focused validation for wall rules, hardware selection, thread engagement, motion sweeps, support-free constraints, handle/latch/hinge collisions, and envelope regressions.