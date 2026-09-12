# Fix B4B hardware redesign

Status: rear-hinge direction locked; detailed geometry still to be implemented and validated. This document is design-first. Do not move to latch/handle implementation until the rear hinge geometry is proven across the supported B4B range.

## Phase 1 — Rear hinge review

### Goal
Redesign the B4B rear hinges so they look proportional on small and large cases, gain strength through elegant load-spreading geometry instead of bulky external blocks, use ordinary metric kit fasteners, and remain fully support-free. The B4B body prints upright. The lid prints upside down.

The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their case geometry. For this phase, use them only to study hinge proportions, hinge-root/load-path treatment, compactness, and support-free construction.

## Confirmed design decisions

1. **Fastener size is never a user option.** B4B chooses M2 or M3 automatically behind the scenes.
2. **Every B4B uses exactly two rear hinges.** No single-hinge fallback.
3. **B4B has a meaningful minimum footprint around 50 x 50 mm.** Because Wavefinity X/Y dimensions live on an 8 mm grid, use a minimum entered child field of **48 x 48 mm (6U x 6U)**. At the normal 0.8 mm wall this produces a physical B4B envelope of roughly **50.94 x 50.94 mm**, which matches the intended “about 50 x 50” minimum almost exactly.
4. **The lid only needs about 120 degrees of opening.** Do not design for 180-degree fold-flat motion.
5. **Keep the no-nut/no-insert strategy.** The screw passes through clearance-bored moving members and thread-forms into the far printed ear.
6. **Use ordinary socket-head M2/M3 screws from common assortment kits.** Do not require button-head, countersunk, shoulder screws, metal pins, or special hardware.

## What is wrong with the current hinge design

### 1. Current math is M3-first rather than case-scale-first
The current design has one global M3 hardware profile:
- M3 nominal 3.0 mm
- 3.4 mm rotating clearance bore
- 2.6 mm thread-forming pilot
- 3.0 mm minimum thread engagement
- 6.0 mm head clearance
- allowed screw lengths 12/16/20/25/30 mm
- no nuts/inserts

The same head-driven boss radius is used for every hinge/latch pivot. With the current support-free octagonal section, that resolves to a boss radius of about 3.88 mm. The hinge axis is then placed `boss_radius + 0.45` behind the rear-wall crest and the boss reaches about another 4.11 mm outward. Result: the current hinge envelope can project roughly 8.4 mm behind the wall before considering its visual root treatment.

That absolute size is reasonable on a large rugged case, but it is much too large on a roughly 51 mm B4B.

### 2. The minimum hinge width dominates small/medium B4Bs
Current hinge width is:
`clamp(0.16 * case_x, 12.5 mm, 24 mm)`

The 12.5 mm floor remains active until the case is roughly 78 mm wide. The reinforced root pad adds 2 mm on each end, making the minimum reinforced envelope 16.5 mm per hinge.

On the minimum B4B, each hinge therefore occupies an excessive fraction of the rear edge. The continuous percentage scaling is mostly irrelevant because the hard M3-derived minimum dominates.

### 3. Screw-head size is incorrectly controlling the whole hinge
The current hinge effectively sizes every pivot section around the M3 head-bearing requirement. That is the wrong structural decomposition.

Separate the jobs:
- rotating knuckle/ear size is driven by clearance bore + printable shell;
- far thread-forming ear is driven by pilot + thread engagement + printable shell;
- only the near head-bearing area needs local material sized around the screw head;
- the wall root gains strength by spreading load into more rear-wall area, not by making the whole pivot a large head-sized barrel.

### 4. The root is structurally thoughtful but visually too much like an external bracket
The present design correctly avoids attaching a hinge to a thin wall by creating an exterior root web, gussets, fillets, and end chamfers. Mechanically that is sensible.

Visually it reads as a large block/gusset/barrel assembly stuck onto a thin box.

The preferred design language is **elegant strength**:
- compact pivot hardware;
- a narrow rib or web leaving the pivot;
- reinforcement that widens gradually as it reaches the rear wall;
- a shallow side chamfer/gusset carrying the load into more wall area;
- no broad blunt rectangular pad unless strength calculations genuinely require one.

### 5. Hinge position should be driven by a 120-degree motion sweep
Current rear-axis Y is effectively based on `rear_crest + boss_radius + 0.45`.

The new hinge axis must instead be solved from actual geometry:
- closed-lid clearance;
- lid rear-edge thickness;
- body rim/rear wall;
- knuckle envelope;
- approximately 120-degree opening;
- small manufacturing/running clearance.

The pivot should be placed **as close to the rear wall as the 120-degree sweep permits**. Excessive rear protrusion is a design failure, not an acceptable consequence of boss sizing.

If a small support-free relief/chamfer on the rear lid edge allows the axis to move inward substantially, prefer that over moving the whole hinge farther backward.

## Minimum B4B rule

B4B mode should reject/disable dimensions below **48 x 48 mm child field** rather than auto-growing tiny bins merely to make hardware fit.

Important distinction:
- 48 x 48 mm is the entered B4B child field.
- The actual exterior is slightly larger because the wall grows outward and the wave has amplitude.
- With the standard 0.8 mm wall, the calculated physical envelope is about 50.94 mm square.

Therefore the redesign target is:

**Two complete support-free hinges must fit cleanly on a 48 mm-wide child field without any hardware-driven X growth.**

Do not retain the current behavior where secure-lid hardware can silently grow the user’s child field to make oversized hinges fit.

## Automatic M2/M3 architecture

Replace hard-coded M3 assumptions with a reusable internal hardware profile object. The user never sees this selection.

Candidate fields:
- nominal screw diameter
- clearance bore
- printed pilot
- minimum thread engagement
- head diameter / head clearance
- permitted standard screw lengths
- axial running gap
- minimum printed shell around the clearance bore
- minimum printed shell around the pilot
- preferred local head-bearing wall
- maximum acceptable screw protrusion

### Verified standard screw-head envelope
Ordinary ISO-style socket-head screws are approximately:
- M2 head diameter: 3.8 mm
- M3 head diameter: 5.5 mm

Provide a small printed clearance margin around those values, but **do not propagate the head diameter into the whole hinge barrel**.

### Common kit lengths to target
Use a short common list that matches normal assortments:
- M2: 6, 8, 10, 12, 16 mm
- M3: 6, 8, 10, 12, 16, 20 mm

For the redesigned hinge, strongly prefer pins in the 8–12 mm range. A compact B4B hinge that needs a 20–30 mm pin is probably geometrically wrong.

### Initial profile targets for geometry work
These are prototype targets, not final print-calibrated values:

**M2 compact profile**
- nominal: 2.0 mm
- clearance bore: about 2.3 mm
- printed thread-forming pilot: start around 1.7 mm and validate physically
- target thread engagement: roughly 2.4–2.8 mm
- local head clearance: about 4.1–4.2 mm
- preferred screw: M2x8 / M2x10, M2x12 only if required

**M3 standard profile**
- nominal: 3.0 mm
- clearance bore: 3.4 mm
- printed pilot: 2.6 mm unless physical testing proves a better value
- minimum thread engagement: 3.0 mm
- local head clearance: about 6.0 mm
- preferred screw: M3x10 / M3x12, M3x16 only if required

### Automatic selection philosophy
M2 is not simply “small X”; M3 is not simply “large X.” Selection should consider the overall case being carried.

Recommended implementation approach:
1. First solve a compact M2 hinge candidate.
2. Use M2 only when the case is within a compact load envelope.
3. Promote to M3 for larger/deeper/taller cases even if one axis is narrow.
4. Once the geometry is finalized, reduce this to one deterministic helper so preview/export/BOM all agree.

A practical starting envelope to test is:
- M2 only when both child-field plan dimensions are <= 96 mm and B4B child height is <= 64 mm;
- M3 otherwise.

This threshold is intentionally provisional. Validate it against hinge proportions, resulting part mass/capacity, and the final root geometry before locking it. The final user experience remains completely automatic either way.

## New hinge geometry direction

### Three-knuckle layout remains appropriate
Keep the basic two-body-ear + one-lid-center-ear hinge arrangement. It gives a straightforward screw path, avoids loose hardware besides the screw, and provides two bearing regions on the body.

But redesign each region independently instead of extruding one oversized common boss shape.

### Body-side ears
Each hinge group should have two slim body ears.

For each ear:
- size the pivot section from bore + shell, not screw-head diameter;
- use the existing self-supporting horizontal bore concept or an improved equivalent;
- keep the pin axis close to the wall;
- flow the ear into a diagonal/trapezoidal rib;
- widen that rib modestly as it meets the rear wall;
- chamfer/taper the rib ends in plan so there is no blunt rectangular root;
- preserve the child-field cavity exactly — reinforcement grows outward only.

The near ear receives a **local head-bearing flare/pad** around the screw head. That local flare may be larger than the rest of the ear, but it should be short in the axial direction and visually integrated.

The far ear becomes the thread-forming lug. It needs enough axial length for thread engagement but does not need head-sized radial geometry.

### Lid-side center ear
The center ear should be compact and close to the lid edge.

Strength should flow into the lid through a shallow triangular/trapezoidal arm that reaches inward into the lid plate. Avoid a large vertical tab whose width/height is dictated by the old boss.

Because the lid prints upside down:
- the bed-facing top plate must provide the starting support;
- all added hinge-root faces must build upward from it;
- no hidden horizontal shelf may appear once the lid is flipped into print orientation;
- a 45-degree-or-shallower transition is preferred where the root leaves the plate.

### Root reinforcement visual target
From side/rear view, the hinge should look approximately like:
- compact pin barrel/ear near the rear edge;
- a short neck;
- a shallow diagonal reinforcement into the wall;
- reinforcement fading into the wall over a larger area than the pivot itself.

Do **not** make the chamfer huge. The strength comes from creating a continuous load path and eliminating the sharp peel point, not from covering half the rear wall with a triangular block.

## Hinge width and X placement

Stop using `0.16 * case_x` as the primary dimensional rule.

Instead:
1. derive the minimum axial stack from the selected screw family and required thread engagement;
2. keep the moving gaps fixed by print tolerance;
3. derive the hinge group width from that stack;
4. optionally allow modest root-width growth on larger cases without enlarging the pivot itself.

Place the two hinge groups toward the outer thirds of the rear edge, while maintaining:
- corner tangent keep-out;
- root-chamfer room;
- equal symmetry;
- enough material between each hinge and the nearest corner;
- enough center spacing that the roots do not visually merge.

The reference STL is useful here only as a proportion cue: its hinge groups are a small percentage of the rear edge and visually sit toward the outer portions, rather than clustering near the middle.

## Rear protrusion target

The final rear projection should be a derived result of the 120-degree sweep, not a fixed boss-based stand-off.

Desired behavior:
- M2 hinge on the minimum case should look tucked into the rear edge, not like a backpack attached to it.
- M3 should still remain compact because only its local head-bearing zone grows to head size.
- the root reinforcement may spread along/down the wall but should not significantly increase Y protrusion.

Add an explicit validation/report value for maximum rear hardware projection beyond the local rear-wall crest. This makes future regressions visible.

## Support-free print rules

No B4B hinge geometry may require slicer supports.

### Body upright
- horizontal pin bores need a self-supporting roof;
- root undersides must be vertical or supported by <=45-degree transitions;
- no underside shelf below the barrel;
- no decorative fillet may create a hidden downward overhang beyond the project limit.

### Lid upside down
Evaluate support in **print space**, not assembly space.
- hinge root must grow from the bed-facing lid top/edge;
- center ear and arm must remain self-supporting when flipped;
- horizontal bore roof direction must flip correctly;
- no underside detail may depend on support from the body because the lid is printed separately.

## Screw termination rule

The current 6 mm permitted screw protrusion is much too generous for the redesigned compact hardware.

New target:
- choose the shortest standard screw that reaches the required thread engagement;
- ideally terminate within the far ear;
- allow approximately flush or at most a very small controlled protrusion;
- do not accept a long screw simply because it technically satisfies minimum engagement.

The BOM should report the automatically selected hardware clearly, e.g. `2 x M2x8 hinge pins` or `2 x M3x10 hinge pins`.

## Required validation before hinge phase is complete

Validate at minimum:

1. **48 x 48 mm minimum B4B**
   - exactly two hinges;
   - no hardware-driven case growth;
   - proportions visually reasonable;
   - full ~120-degree motion;
   - support-free body and lid.

2. **Hardware-family transition cases**
   - case immediately below M2->M3 threshold;
   - case immediately above threshold;
   - no abrupt grotesque visual jump;
   - BOM and geometry select the same profile.

3. **Long narrow case**
   - verifies that overall case size/load can promote M3 even if rear width is relatively small.

4. **Large B4B**
   - M3 remains strong without continuously ballooning pivot diameter/width;
   - root reinforcement scales modestly rather than hardware becoming enormous.

5. **Motion sweep**
   - closed state clears;
   - intermediate angles clear;
   - ~120-degree open state clears;
   - hard stop, if intentionally designed, contacts broad printable surfaces rather than screw threads or a thin edge.

6. **Printability**
   - body upright without supports;
   - lid upside down without supports;
   - all horizontal bores self-support;
   - no bridge exceeds the project’s support-free bridge target.

7. **Structural path**
   - hinge forces enter a reinforced rear-wall zone;
   - no load depends on a tiny Boolean overlap with a 0.2–0.8 mm wall;
   - thread-forming far lug has family-specific minimum engagement;
   - local head pad leaves adequate plastic outside the screw-head footprint.

8. **Envelope regression check**
   - record hinge group width;
   - record maximum rear projection;
   - record root wall coverage;
   - compare these values across representative sizes so future changes cannot silently return to the oversized current design.

## Reference-STL lesson to preserve

Do not copy dimensions. Preserve only the useful design principles:
- small hinge groups relative to the case edge;
- pivot tucked close to the edge;
- strength carried away from the pivot through ribs/tapered transitions;
- hardware head size does not dictate the scale of the entire hinge assembly;
- attachment looks integrated into the case rather than bolted onto an external block.

## Next implementation step

The rear hinge design is sufficiently specified to move from review into geometry work without additional user questions.

Next work should:
1. add internal M2/M3 hardware profiles;
2. enforce the 48 x 48 mm B4B minimum;
3. replace current hardware-driven auto-growth for hinge fit;
4. derive compact three-knuckle axial stacks around short standard screws;
5. solve the hinge Y-axis location from the 120-degree opening sweep;
6. create the narrow-ear + tapered-root body geometry;
7. create the upside-down-printable lid center ear/root;
8. validate representative minimum/transition/large cases;
9. review the result visually before proceeding to latch redesign.

## Later phases

After the rear hinge design is accepted, redesign the latches and front folding handle using the same principles:
- automatic M2/M3 hardware where appropriate;
- compact pivots;
- local head-bearing reinforcement only;
- tapered load paths;
- minimal protrusion;
- no supports;
- proportions tied to the case rather than one universal rugged-case-scale fitting.
