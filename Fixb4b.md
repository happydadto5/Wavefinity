# Fix B4B hardware redesign

Status: design review in progress. Rear-hinge direction is locked. Wall-thickness policy and the front-latch redesign are now defined. The front folding handle is the next design phase and is intentionally not designed here beyond reserving space for it.

This document is implementation guidance for an LLM. The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their case geometry or absolute dimensions. Use them only for proportion, compactness, load-path, hinge/latch/handle design language, and support-free ideas.

# Global B4B rules

1. B4B is a carrying/storage case, not merely a normal bin with hardware added.
2. Minimum entered B4B child field is **48 x 48 mm (6U x 6U)**. Do not silently grow smaller requested fields to make hardware fit; dimensions below the minimum should be rejected/disabled in B4B mode.
3. Every secure B4B uses **exactly two rear hinges**.
4. The lid needs approximately **120 degrees** of opening, not 180-degree fold-flat motion.
5. Fastener diameter is never a user setting. Select M2 or M3 automatically.
6. Use ordinary socket-head metric screws from common assortment kits. No nuts, heat-set inserts, shoulder screws, or special metal hinge pins are required.
7. Screws pass through clearance-bored moving members and thread-form into the far printed ear/lug.
8. Body prints upright. Lid prints upside down. Separate latch levers print flat on a broad side. **No B4B part may require slicer supports.**
9. Hardware should read as part of the case, not large brackets attached to a thin shell. Design language is **elegant strength**: compact pivots, modest ribs/chamfers, long enough load paths, minimal protrusion.
10. The future carrying handle is a **folding front handle**, not a top handle. Latch geometry must leave useful front-wall area below the lid seam for that later phase.

# Phase 1 — Rear hinge redesign

## Why the current hinge is wrong

The current design is M3-first rather than case-scale-first. One global M3 hardware profile drives every boss:
- M3 nominal 3.0 mm;
- 3.4 mm rotating clearance bore;
- 2.6 mm thread-forming pilot;
- 3.0 mm minimum thread engagement;
- 6.0 mm head clearance;
- old screw list 12/16/20/25/30 mm;
- a head-driven support-free boss radius of about 3.88 mm.

The same boss size is used for hinge/latch pivots even when the case is very small. The old hinge width is `clamp(0.16 * case_x, 12.5 mm, 24 mm)`, and its reinforced root adds 2 mm at each end. The 12.5 mm minimum dominates until the case is roughly 78 mm wide, so a small case carries hardware that is visually closer to rugged-box scale than Wavefinity scale.

The screw head is also incorrectly controlling the whole hinge. Separate these jobs:
- rotating knuckle size: clearance bore + printable shell;
- far thread-forming ear: pilot + required engagement + printable shell;
- near head-bearing region: only this short local region needs head-sized material;
- structural strength: spread load into the rear wall through tapered/chamfered roots rather than enlarging the whole barrel.

## Automatic M2/M3 architecture

Replace hard-coded M3 constants with one reusable internal hardware-profile object used by hinges and latches. The user never sees the selection.

Candidate profile fields:
- nominal diameter;
- clearance bore;
- printed pilot;
- minimum thread engagement;
- head diameter/head clearance;
- permitted standard screw lengths;
- axial running gap;
- minimum shell around clearance bore;
- minimum shell around pilot;
- local head-bearing margin;
- maximum allowed protrusion.

Prototype values to validate physically:

**M2 compact**
- nominal 2.0;
- clearance bore about 2.3;
- printed thread-forming pilot about 1.7 initially;
- target engagement about 2.4–2.8;
- local head clearance about 4.1–4.2;
- common screw lengths 6/8/10/12/16;
- strongly prefer 8 or 10 mm hinge/latch pins.

**M3 standard**
- nominal 3.0;
- clearance bore 3.4;
- printed pilot 2.6 initially;
- minimum engagement 3.0;
- local head clearance about 6.0;
- common screw lengths 6/8/10/12/16/20;
- strongly prefer 10 or 12 mm hinge/latch pins.

Ordinary socket-head dimensions are roughly 3.8 mm head diameter for M2 and 5.5 mm for M3. Do not propagate those head diameters into every surrounding pivot section.

Hardware-family selection must consider the overall case/load, not just X width. A provisional envelope to validate is M2 only when both child-field plan dimensions are <= 96 mm and child height <= 64 mm; M3 otherwise. This threshold is not sacred. Final selection must be deterministic and shared by preview, export, validation and BOM.

Prefer one hardware family for the whole case. If a case resolves to M2, hinges and latches should normally both use M2. If it resolves to M3, both normally use M3. This keeps the BOM and assembly simple.

## New rear-hinge geometry

Retain the mechanically useful three-knuckle concept: two body ears with one lid ear between them. Redesign the three regions independently rather than extruding one oversized common boss.

### Body ears
Each hinge group gets two slim ears:
- pivot section sized from bore + shell;
- compact self-supporting horizontal bore;
- pin axis tucked close to the rear wall;
- short neck leaving the pivot;
- shallow diagonal/trapezoidal rib flowing into the wall;
- rib widens modestly at the wall;
- plan-view ends taper/chamfer into the wall rather than ending as a rectangular pad;
- reinforcement grows outward and must never steal child-field volume.

Only the near ear gets a local screw-head flare. The far ear is a thread-forming lug sized for engagement, not head diameter.

### Lid ear
Use one compact center ear close to the rear lid edge. Carry load into the lid through a shallow triangular/trapezoidal arm reaching inward into the lid plate. Avoid the current large vertical tab.

Because the lid prints upside down, evaluate every face in print space. The root must build from the bed-facing lid top/edge and use vertical or <=45-degree transitions. Keep the horizontal bore self-supporting with the roof orientation reversed correctly for the flipped lid.

### Axis placement and opening sweep
Do not place the pivot from `boss_radius + fixed_offset`. Solve the closest safe axis from:
- closed-lid clearance;
- lid rear-edge thickness;
- body rim/rear wall;
- true knuckle envelope;
- running clearance;
- sampled motion from closed through approximately 120 degrees.

Put the axis **as close to the rear wall as the sweep permits**. If a small support-free relief/chamfer on the lid rear edge moves the axis inward significantly, prefer that to moving the whole hinge farther out.

### Hinge width and X placement
Stop using `0.16 * case_x` as the primary width rule. Derive the axial stack from hardware profile, moving gaps and far-lug engagement. Optionally let only the root coverage grow modestly on larger cases; do not continuously balloon the pivot.

Place two hinges symmetrically toward the outer thirds while respecting corner tangent keep-outs and leaving visible separation between roots.

### Rear projection
Add an explicit calculated/reportable value for maximum hardware projection behind the local rear-wall crest. This is a regression metric. A compact M2 hinge on the minimum case should look tucked into the edge. M3 may be larger but should still remain compact because only its head-bearing end needs head-scale material.

### Screw termination
Choose the shortest standard screw that achieves the required engagement. Prefer termination inside or approximately flush with the far ear. Retire the old philosophy allowing up to 6 mm of exposed screw beyond the lug.

## Rear-hinge validation

At minimum validate:
- 48 x 48 minimum child field with exactly two hinges and no hardware-driven growth;
- cases immediately below/above the automatic M2->M3 transition;
- long/narrow and large cases;
- closed and sampled opening sweep through ~120 degrees;
- support-free upright body;
- support-free upside-down lid;
- thread engagement and near-flush screw termination;
- watertight single solids;
- rear projection and hinge-group width regression metrics;
- root load path into the wall without tiny Boolean-only overlaps.

# Phase 1.5 — Wall-thickness policy for ordinary bins, stacking and B4B

## Decision: B4B minimum/default wall is 1.2 mm

A 0.8 mm B4B wall can probably be made to survive if every hinge/latch/handle root is separately reinforced, but that is the wrong baseline for a carrying case. A B4B is repeatedly opened, latched and ultimately carried by hardware attached to its shell. With a nominal 0.4 mm nozzle:
- 0.8 mm is roughly a two-line wall;
- 1.2 mm is roughly a three-line wall and gives much more useful stiffness and peel resistance.

The cost is tiny because B4B preserves the authoritative inner child field and grows its structural wall outward. With the current wave math:
- 48 x 48 child field at 0.8 wall -> about **50.94 x 50.94 mm** physical case;
- 48 x 48 child field at 1.2 wall -> about **51.88 x 51.88 mm** physical case.

So the stronger default costs under 1 mm total width/depth and does not reduce child-bin capacity. Therefore:

**B4B wall minimum = 1.2 mm. B4B default = 1.2 mm.**

Do not permit a newly-created B4B below 1.2 mm. If the user enters B4B mode from an ordinary bin whose wall is below 1.2, promote it to 1.2 automatically. If it is already 1.2 or thicker, preserve it.

## Simplify the wall options

The UI currently offers too much granularity. Standardize new user choices around a nominal 0.4 mm nozzle and 0.4 mm model increments:

- **0.4 mm — Very thin / prototype**
- **0.8 mm — Standard**
- **1.2 mm — Strong**
- **1.6 mm — Heavy**
- **2.0 mm — Extra heavy**
- **2.4 mm — Maximum**

Do **not** add 0.5, 1.0, 1.5, etc. Exact extrusion width is slicer/material dependent; mixing a second 0.5-mm progression doubles the choices without giving a stable printer-independent meaning. The six 0.4-step values are enough.

The labels may mention approximate perimeter count for a 0.4 nozzle, but do not promise exact slicer line count because Arachne/line-width settings can differ.

## Ordinary-bin UI behavior

Keep the ordinary-bin default at 0.8 mm. The existing `Standard walls` concept may remain:
- checked -> fixed 0.8 mm and hide custom selector;
- unchecked -> expose the simplified preset selector above.

If simplifying the UI further later, a single always-visible wall dropdown is also acceptable, but do not expand the option list again.

For new ordinary-bin choices, UI minimum is 0.4 mm. The geometry engine may continue accepting old non-preset values for saved-file/CLI compatibility.

## B4B UI behavior

B4B should always expose **Wall thickness** because shell strength matters to the user here. Do not make the user uncheck `Standard walls` just to see it.

Allowed new B4B choices:
- 1.2 mm — Standard B4B / Strong;
- 1.6 mm — Heavy;
- 2.0 mm — Extra heavy;
- 2.4 mm — Maximum.

The B4B selector defaults to 1.2.

The ordinary-bin `standard_walls=True` meaning of 0.8 does not map cleanly to B4B. Treat B4B's wall as an explicitly visible case setting rather than pretending 0.8 remains the standard.

## Stacking/direct-snap interaction

Use one central concept: **mode-required minimum wall**.

Current/expected policies:
- ordinary non-stacking bin: UI may go down to 0.4;
- direct-snap stacking: minimum 1.2;
- lid-based stacking: use 1.2 minimum if the snap/groove load path requires it;
- B4B: minimum 1.2.

When a user enables a mode requiring 1.2 and the current wall is thinner, automatically promote to 1.2 and expose the resulting thickness. If the UI maintains session state, remember the prior ordinary-bin wall and restore it when the strength-requiring mode is turned off. Do not silently reduce a thicker user choice.

## Legacy/saved designs

Do not rewrite old saved designs merely because their wall thickness is no longer a new-preset value. Examples such as 0.6, 1.0, 1.4 or even the old 0.2 minimum should reopen with their exact stored geometry when compatibility permits.

Recommended UI treatment for an old non-preset value:
- show the exact saved value as a temporary `Legacy/Custom X mm` selection;
- once the user chooses a new preset, use only the simplified preset list thereafter.

This UI simplification should not require an unnecessary geometry compatibility break.

# Phase 2 — Front latch redesign

## Current latch review: why it looks oversized

The present latch repeats the same M3-first mistake as the hinge and compounds it with two full external pivot systems.

Current architecture:
- lid carries two large M3 pivot ears;
- a separate lever rotates on that M3 pivot;
- the body carries two more large receiver ears;
- a second M3 screw spans those receiver ears and acts as the catch pin;
- the lever has a C-shaped hook that snaps over the catch pin;
- both pivot and catch ears use the same ~3.88 mm head-driven boss radius;
- the whole system sits on broad reinforced external pads.

For the current `standard` latch profile, the minimum latch width is 12 mm, but the reinforced receiver envelope is much wider: 12 mm lever/pivot width + two ~4 mm catch ears + 2 mm root margin on both sides, about **24 mm total** before visual blending. On a ~52 mm minimum B4B that single fitting consumes almost half the front edge.

The Y projection is worse. The standard receiver web is 3.6 mm thick outside the wall; the catch axis is another hook-radius + clearance outward; the pivot sits farther outward again; and the old 3.88 mm pivot disc extends beyond that. The existing standard geometry can approach roughly **14 mm of front projection beyond the wall crest**. That is why it reads as a giant mechanism hanging from a thin box.

The lightweight profile remains oversized because it still uses the same universal M3 boss and only changes several secondary dimensions.

## Latch design goal

Keep the useful basic mechanism — a folding lever on the lid engaging a metal screw-shank catch pin on the body — but redesign every surrounding printed part around the selected hardware family and case scale.

The desired closed appearance:
- compact fitting directly under the lid seam;
- lever lies nearly flat against the front face;
- no giant round pivot pods;
- no broad rectangular body pad;
- only a modest finger lip/rolled edge projects enough to operate easily;
- lower front wall remains visually and physically available for the later folding front handle.

The reference STL's useful lesson is the **thin folding strap/lever language with compact rolled/pivot regions**, not its absolute 31 mm-wide dimensions. The reference case is much larger than a minimum B4B, so copy proportions and integration, not size.

## Keep the metal catch pin

Retain a screw as the body catch pin. This is desirable:
- the hook bears against metal rather than wearing a printed pin;
- it matches the earlier no-nut/no-insert hardware strategy;
- the same M2/M3 family can serve hinge and latch hardware;
- replacement is easy from a normal screw assortment.

Use one near clearance ear and one far thread-forming ear around the body catch pin. The screw shank between them is the exposed catch surface.

Likewise, the lid lever pivot uses one near clearance ear and one far thread-forming ear. The lever itself clearance-rotates between them.

Aim to make pivot and catch use the **same screw diameter and, where geometry permits without distortion, the same screw length**. Do not make the mechanism bulky merely to force one common length; compactness wins if two lengths are genuinely cleaner.

## Automatic latch hardware

Latch hardware should normally inherit the case's automatic hardware family:
- compact/M2 case -> M2 latch pivot and M2 catch pin;
- standard/M3 case -> M3 latch pivot and M3 catch pin.

Do not expose a latch bolt-size selector.

The existing `lightweight` versus `standard` latch-strength choice is tied to the old geometry and should be retired from the user-facing design unless a later physical test proves a genuine need. Preferred design is **one robust proportional latch profile per hardware family**. Keep legacy fields readable if needed for saved-file compatibility, but normalize new B4B geometry to the automatic profile.

## Latch count and placement

Latch count remains automatic.

Use:
- **one centered latch** on small cases where one latch provides adequate lid retention;
- **two latches** on larger/wider cases when needed for lid pull-down and edge control.

For two latches, place them approximately at the one-third/two-thirds positions (`x ~= +/- case_width/6` from center), then adjust only as required for corner/root keep-outs.

Do not derive two-latch eligibility merely from whether two giant pads mathematically fit. The new decision should consider lid width/stiffness and closure quality using the actual compact fitting envelope.

The latch(s) should stay high on the front wall near the lid seam. This deliberately leaves the lower front region available for the later folding handle.

## New body catch receiver

Replace the broad receiver web + oversized bosses with two compact ears integrated into the front wall.

Each body receiver should:
- use two small ears around the selected M2/M3 catch screw;
- position the catch pin only as far in front of the wall as required for lever/hook clearance;
- size radial material from bore + shell, not screw-head diameter;
- add a short local head-bearing flare only on the near ear;
- give the far ear enough axial thickness for thread-forming engagement;
- flow each ear into the 1.2+ mm front wall through a modest triangular/trapezoidal root;
- widen/taper the root gradually in X/Z rather than creating a broad rectangular pad;
- use <=45-degree printable undersides when the body is upright;
- preserve the authoritative child field; all added reinforcement grows outward.

Because B4B now has a 1.2 mm minimum shell, the root no longer has to compensate for a possible 0.2–0.8 mm carrying-case wall. Still reinforce locally; do not assume 1.2 alone is enough to hang an ear from a tiny contact patch.

## New lid pivot receiver

Use two compact ears at the front lid edge with the lever between them.

Requirements:
- pivot axis close to the lid/front wall rather than far outboard;
- near ear gets only a short local screw-head flare;
- far ear is the thread-forming lug;
- ears connect into the secure lid plate through shallow tapered arms, not big tabs;
- all geometry remains support-free when the lid is flipped upside down for printing;
- horizontal pivot bores retain a self-supporting roof oriented for the flipped print pose.

Do not let the lid pivot ears extend downward across a large vertical zone; the mechanism should visually live at the seam.

## New lever shape

The separate lever is where the reference design language is most useful.

Replace the current convex-hull-of-two-large-discs look with a **thin folding strap/lever**:
- compact circular/rounded pivot end sized around the pivot bore;
- mostly flat/slightly tapered strap body;
- modest curved/rolled lower operating edge or finger lip;
- hook geometry integrated near the lower end to capture the body catch screw;
- gentle fillets at strap-to-pivot and strap-to-hook transitions;
- no huge bulb at either end.

The lever should lie nearly parallel to the front wall when closed. Its visible thickness/projection should come mostly from what the hand needs to grab and what the hook needs to clear, not from a universal boss radius.

The lever prints flat on one broad face. In that print orientation the pivot bore runs vertically through the print and can be round; the hook/strap outline is a 2D profile extruded to width, so smooth curves and fillets do not require supports.

## Hook and retention behavior

Retain positive hook capture around the metal catch pin, but reduce dependence on a large flexing snap jaw.

Target behavior:
- closing rotation guides the hook onto the pin;
- a modest detent/interference gives tactile retention;
- lifting the finger edge releases it cleanly;
- ordinary lid-opening force should not naturally rotate the lever open;
- avoid a deep C-hook that requires large elastic deformation every cycle;
- avoid sharp internal corners at the hook mouth; use a controlled fillet that does not close the release path.

The final hook geometry must be validated by sweep, not by static distance alone.

## Front projection target

The current ~13–14 mm projection is unacceptable.

Design objective:
- M2 latch on a minimum/small B4B should preferably stay around **5–6 mm maximum closed projection** beyond the local front-wall crest;
- M3 may be somewhat larger but should remain **single-digit millimeters**;
- no root reinforcement should materially increase Y projection beyond the mechanism itself.

These are design targets, not permission to create interference. Solve the smallest collision-free geometry and report the resulting projection as a regression metric.

## Width/proportion target

Stop using `clamp(0.14 * case_x, 12, 22)` as the fundamental lever width rule.

Derive width from:
- selected M2/M3 screw family;
- near ear/head-bearing region;
- lever running gaps;
- lever width needed for stiffness and hand operation;
- far lug engagement.

Prototype goal, subject to actual geometry:
- compact M2 latch fitting should be noticeably narrower than the old 24 mm reinforced receiver envelope, ideally in the low-teens total root envelope;
- M3 grows only enough for hardware and load, not as a percentage of case width.

On a larger case, strength may be increased by slightly widening/lengthening the wall roots or using two latches, not by making one latch visually enormous.

## Interaction with future front handle

Do not design the handle yet, but reserve for it now:
- latch pivot and catch should occupy the upper front zone near the lid seam;
- avoid long latch roots extending halfway down the front wall;
- one centered latch may coexist with a later handle below it;
- two latches should sit toward one-third/two-thirds positions and leave the central/lower front region clean;
- latch sweep must not swing through the expected lower handle zone when the handle is folded flat.

The handle phase may impose a minimum B4B height for a usable front handle. Do not distort latch geometry now to force a handle onto an impossibly shallow case.

## Support-free latch rules

### Body upright
- catch-pin bores: self-supporting roof/teardrop equivalent;
- ear undersides and wall roots: vertical or <=45-degree transitions;
- no hidden shelf under the catch barrel;
- no broad bridge between ears.

### Lid upside down
- pivot ears grow from the bed-facing lid plate/edge;
- pivot bores use the correct flipped roof direction;
- no ear root depends on the assembled body for print support.

### Separate lever
- print flat on broad face;
- pivot hole vertical in print pose;
- hook mouth/strap outline fully self-supporting;
- no support material inside the hook or pivot bore.

## Latch screw selection and BOM

Use the same family-specific shortest-standard-screw logic as the hinge:
- prove required thread engagement;
- terminate within/near-flush to far lug;
- no long exposed screw tails;
- report exact BOM, e.g. `1 x M2x8 latch pivot`, `1 x M2x8 catch pin` or the two-latch equivalent.

If pivot and catch can use one common length cleanly, prefer it and combine the BOM count.

## Front-latch validation

At minimum validate:

1. **Minimum 48 x 48 B4B with 1.2 wall**
   - one centered latch unless closure analysis proves two are required;
   - fitting looks proportional;
   - closed projection near the compact target;
   - no collision with corners or lid skirt;
   - lower front region remains available for future handle.

2. **Automatic M2/M3 transition**
   - latch changes family with the same case-level policy as hinges;
   - no absurd visual jump;
   - BOM agrees with geometry.

3. **One-to-two latch transition**
   - closure policy, not pad-fit accident, determines count;
   - two latches land near one-third/two-thirds;
   - no root overlap;
   - central/lower handle zone remains useful.

4. **Closed retention**
   - lever captures catch pin positively;
   - no rubbing against body except intended tiny detent/contact;
   - lid pull does not self-release the latch.

5. **Opening sweep**
   - sample from closed through full lever-open angle;
   - release band is intentional and geometrically clear;
   - no lever/body or lever/lid collision after release;
   - lever cannot strike the future reserved handle region during normal operation.

6. **Printability**
   - body upright support-free;
   - lid upside down support-free;
   - lever flat support-free;
   - horizontal bores self-support;
   - no unsupported hidden shelves.

7. **Structural path**
   - catch ears load into the 1.2+ wall through tapered roots;
   - lid pivot ears load into secure lid plate through tapered roots;
   - no critical strength depends on tiny Boolean overlap;
   - far lugs meet family-specific thread engagement;
   - near head regions have local bearing material without inflating the full fitting.

8. **Regression metrics**
   - maximum front projection;
   - total latch/root envelope width;
   - catch-pin distance from front-wall crest;
   - pivot distance from front-wall crest;
   - lever vertical extent below lid seam;
   - screw lengths and protrusion.

# Implementation sequencing

The design can now be implemented in this order:

1. Add/simplify central wall preset policy and B4B minimum wall logic.
2. Enforce 48 x 48 B4B minimum and update minimum-case calculations to the 1.2 mm B4B default (~51.88 mm exterior).
3. Introduce the shared automatic M2/M3 hardware-profile abstraction.
4. Implement and validate the redesigned rear hinges against the 120-degree sweep.
5. Replace current latch pads/bosses with compact body catch ears and lid pivot ears.
6. Replace current bulbous latch lever with the flat strap/hook design.
7. Resolve automatic one/two latch count and placement using the new actual fitting envelope and closure needs.
8. Add projection/width/BOM regression values to the B4B summary/validation path.
9. Visually review minimum, transition and large cases before moving on.
10. **Then design the folding front handle.** Remove/replace the current top-handle architecture; do not try to adapt the existing top arch as the final solution.

Do not spend time on broad test expansion. Preserve/update tests that directly encode changed geometry/behavior and add only focused validation for the new wall rules, hardware selection, support-free constraints, screw engagement, motion sweeps and projection regressions.