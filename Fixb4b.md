# Fix B4B hardware redesign

Status: review in progress. This document is intentionally design-first; do not implement the hinge/latch/handle changes until the open decisions are resolved.

## Phase 1 — Rear hinge review

### Goal
Redesign the B4B rear hinges so they look proportional on small and large cases, add strength through elegant load-spreading geometry rather than bulky blocks, use normal kit fasteners, and remain fully support-free. The B4B body prints upright. The lid must print upside down.

The supplied Rugged Box Light STLs are visual/mechanical references only. Do not copy their case geometry. For this phase, use them only to study hinge proportions, hinge-root/load-path treatment, compactness, and support-free construction.

## What is wrong with the current hinge design

### 1. The current math is M3-first rather than case-scale-first
The current design has one global M3 hardware profile:
- M3 nominal 3.0 mm
- 3.4 mm rotating clearance bore
- 2.6 mm thread-forming pilot
- 3.0 mm minimum thread engagement
- 6.0 mm head clearance
- allowed screw lengths 12/16/20/25/30 mm
- no nuts/inserts

The same head-driven boss radius is used for every hinge/latch pivot. With the current support-free octagonal section, that resolves to a boss radius of about 3.88 mm. The hinge axis is then placed `boss_radius + 0.45` behind the rear-wall crest and the boss reaches about another 4.11 mm outward. Result: the current hinge envelope can project roughly 8.4 mm behind the wall before considering its visual root treatment.

That absolute size is not unreasonable on a large rugged case, but it is far too large on the small B4B sizes Wavefinity permits.

### 2. The minimum hinge width dominates almost every small/medium B4B
Current hinge width is:
`clamp(0.16 * case_x, 12.5 mm, 24 mm)`

The 12.5 mm floor remains active until the case is roughly 78 mm wide. The reinforced root pad adds 2 mm on each end, making the minimum reinforced envelope 16.5 mm per hinge.

At the default 0.8 mm wall, the current two-hinge fit math forces a secure B4B child field to approximately 40 mm (5 Wavefinity units) before the two reinforced hinges fit. A roughly 5U-square B4B is only about 43 mm physically wide, so each 12.5 mm hinge is about 29% of the case width and the ~8.4 mm rear projection is about 20% of that scale. This is the main reason the hardware looks enormous.

### 3. Continuous percentage scaling is the wrong primary rule for a bolted hinge
The hinge width currently scales continuously with case width, but the fastener comes in discrete real sizes and lengths. This produces a geometry-first screw selection rather than a screw-profile-first design.

The redesign should define discrete hardware profiles around real kit screws, then let root reinforcement/placement scale with the case. Initial candidate profiles to evaluate:
- Compact: M2, likely around an M2x8 hinge pin.
- Standard: M3, likely around M3x10 or M3x12 depending the final three-knuckle stack.

Do not finalize those values until the complete motion/screw-engagement geometry is checked.

### 4. The current hinge root is structurally thoughtful but visually too much like an external bracket
The present design correctly tries to avoid hanging a hinge from a thin wall: it creates an exterior structural root web, gussets it into the barrel, fillets the internal corners, and chamfers the ends. Mechanically that is sensible.

The problem is the resulting visual language: the hinge reads as a large block/gusset/barrel assembly attached behind a thin box.

The reference case uses a better visual principle: the hinge appears to grow out of the case edge. Narrow hinge ears/ribs carry load farther into the wall, while the pivot region stays compact. The root transition is tapered/chamfered rather than a broad rectangular pad.

### 5. The hinge itself should become slimmer, not merely have a smaller root web
The current design makes every pivot section large enough to accommodate the M3 head footprint. That is unnecessarily conservative visually.

For the redesign, separate the jobs:
- rotating knuckle/ear size should be driven by bore diameter + printable shell;
- thread-forming terminal ear should be driven by pilot + required thread engagement + shell;
- screw-head bearing area should be local to the head-bearing end, not force the entire hinge barrel to use the same large radial section;
- the wall root should gain strength by spreading into the rear wall, not by pushing the whole pivot farther out.

### 6. Hinge position should be driven by sweep clearance and proportions, not boss radius
Current rear-axis Y is effectively based on `rear_crest + boss_radius + 0.45`. The new axis location should instead be solved from the actual lid/body opening sweep with a small clearance margin.

If needed, add a small support-free relief/chamfer at the rear lid edge so the pivot can tuck closer to the case without collision. This is preferable to moving a large barrel farther behind the wall.

Also review X placement. Current centers are derived near `eff.x / 4` and become crowded toward the middle on the smallest allowed secure case. The supplied reference places compact hinge groups farther toward the outer portions of the edge. Once the hinge envelopes are smaller, prefer a stable, balanced outer-third placement subject to corner keep-outs.

## Proposed hinge design direction

### Body side
Prefer two slim hinge ears per hinge group rather than two full-size barrel bosses. Each ear should:
- project only as far as required for pin/sweep clearance;
- have a compact support-free/teardrop horizontal pin bore;
- blend into a narrow vertical or diagonal rib on the rear wall;
- use a modest 45-degree-or-shallower shoulder/chamfer to spread load into more wall area;
- avoid a wide rectangular pad unless a localized wall-strength calculation proves one is needed.

The intent is “elegant strength”: a small hinge with a longer load path into the wall, not a big hinge with a big block behind it.

### Lid side
Use one compact center knuckle/ear between the two body ears. Keep it visually close to the lid edge. Because the lid prints upside down, its print-space underside must remain self-supporting. A faceted/D-shaped external section and the existing support-free bore concept are acceptable even if the visible outer portions are rounded/filleted.

### Support-free rule
No generated B4B part may require slicer supports.
- Body upright: all hinge-root undersides <= 45 degrees from printable support, or vertical.
- Lid upside down: hinge features must build upward from the bed-facing lid top/edge without unsupported shelves.
- Horizontal screw bores should retain a self-supporting roof profile rather than relying on a perfect round bridge.
- Do not trade support-free printing away merely to imitate the reference STL.

## Hardware scaling direction

Recommended architecture: introduce a hardware profile object rather than M3 constants embedded throughout hinge/latch/handle math. The same profile can later be reused by latches.

Candidate fields:
- nominal screw diameter
- clearance bore
- printed pilot
- minimum thread engagement
- head clearance / head-bearing geometry
- permitted standard screw lengths
- axial running gap
- minimum printed shell around clearance bore
- minimum printed shell around pilot

Recommended user behavior, pending decision:
- default `Auto` hardware selection;
- M2 for compact B4Bs;
- M3 for larger/heavier B4Bs;
- optionally allow an advanced M2/M3 override if desired.

Do not choose the M2/M3 threshold solely from X width. Consider at least case footprint/size so a long or deep carrying case is not given tiny hardware merely because one axis is short.

## Screw-length review
The current screw-selection algorithm is good in principle: choose from a fixed kit set and prove minimum thread engagement. Keep that behavior.

Change the design philosophy so hinge axial geometry is intentionally compatible with common screw lengths rather than continuously scaling first and accepting whatever screw happens to fit. Candidate hinge pins should land on common lengths such as M2x8 and M3x10/M3x12. Final choices must be verified against the actual ear/knuckle stack.

The current maximum allowed screw protrusion of 6 mm is too permissive for the redesigned hardware. Target a screw that terminates inside or approximately flush with the printed terminal ear; allow only a small tolerance beyond the far face if required.

## Reference-STL observations relevant to rear hinges
The reference case is much larger than many Wavefinity B4Bs, so its absolute hardware dimensions must not be copied. Its useful lessons are proportional and structural:
- hinge groups are relatively narrow compared with the case edge;
- the pivot hardware is visually tucked into the edge rather than mounted on a large stand-off block;
- load is carried into the wall through narrow ribs/ears and tapered transitions;
- the fastener/pivot feature does not force the entire surrounding structure to become one huge cylindrical boss.

Approximate reference proportions from the supplied lid STL: one hinge group spans roughly 17 mm on a ~218 mm edge (about 8% of the edge), while the hardware stand-off is under ~9 mm on a ~191 mm case depth (about 5%). These are design-language references, not target dimensions.

By comparison, the current B4B minimum 12.5 mm hinge on a ~43 mm minimum secure case is ~29% of the edge, which explains the disproportion even though the absolute hinge size is not wildly different from the rugged-box reference.

## Open decisions before hinge geometry is finalized
1. Should hardware choice be `Auto` only, or `Auto / M2 / M3` with an advanced manual override?
2. Must every secure B4B always have two rear hinges, or may the very smallest size use one centered hinge rather than auto-growing the case?
3. Required opening angle: must the lid fold approximately 180 degrees flat behind the case, or is roughly 110–120 degrees sufficient? This directly controls how tightly the pivot can be tucked into the rear wall.
4. Confirm fastener strategy: keep the current no-nut/no-insert approach, with the screw clearance-bored through the moving pieces and thread-forming into the far printed ear?
5. Confirm ordinary socket-head screws from common M2/M3 assortment kits are the baseline, rather than requiring button-head, countersunk, shoulder screws, or a metal hinge pin.

## Next hinge-review step after decisions
After the open decisions are answered:
1. define the M2/M3 hardware profiles and exact standard screw lengths;
2. derive compact ear/knuckle dimensions from those profiles;
3. derive the closest collision-free hinge axis from an opening-angle sweep;
4. derive root rib/chamfer geometry that spreads load into the rear wall without a bulky pad;
5. calculate placement/fit across the supported B4B size range;
6. verify upright-body and upside-down-lid support-free constraints;
7. only then move to latch redesign, carrying the same hardware/proportion rules forward.
