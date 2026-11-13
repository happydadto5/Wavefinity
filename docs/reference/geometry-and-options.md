# Wavefinity geometry and options — detailed reference

Geometry and feature behavior. Open task-relevant subsections rather than reading the entire reference for orientation.

## The design

### Holder primitives

Every holder owns a floor zone. Item-based holders (`cradle`, `bore`) describe
the stored tool with measured dimensions. `cradle` is deliberately just
**Length** and **Diameter** — it
beds the whole tool, shaft and handle, into one continuous half-round trough,
so the fatter handle needs no separate number. The trough is an open channel
the tool simply drops into, so it takes the tool at its **true diameter — no
fit clearance** — and has no fit-clearance field. The trough walls are sized
automatically, proportional to the tool diameter (about a quarter of it,
floored at the thinnest printable wall and capped so a fat handle never grows a
slab), so there is no wall setting to expose either. There are no fixed tool
presets, since every bin is cut for one specific tool.

A cradle starts as a single trough (**Quantity 1**, like a post). **Quantity =
N** places N troughs across the zone, **Quantity = auto** fits as many as the
zone holds. **Spacing** controls how a row relates: `0` (the default) joins the
row into **one continuous body**, with each pair of facing side walls fully
overlapping so the middle joint is no thicker than either outer side. Raising
it separates those walls; once they no longer touch, a real air gap opens and
the row splits into separate pieces. For ordinary cradles, its footprint tracks
what it holds: the run axis (the tool lies along it) is the tool length; the across axis is N
channels at `diameter + half wall + spacing` pitch. **X direction / Y direction** chooses which bin axis the tool
lies along — a 40 mm tool needs 40+ mm that way, so in a long narrow bin only
one direction fits, and the editor says which when it doesn't: *"40 mm long but
its zone only runs 13 mm along x"* rather than a raw overflow. Every
auto-computed edge rounds up to the 1 mm editor grid so the pipeline's snap
can't trim a trough below what the tool needs.

When an interior part does not fit, its editor offers **Grow the bin** and the
same growth normally happens automatically. The bin grows on the 7 mm grid to
hold every part at its real footprint. It never shrinks an already-large bin.

**Bin Height means wall height, not interior part height.** A shallow bin -
a 10 mm vanity-top organizer, say - can still carry useful interior geometry
that rises above its own wall, but only under narrow conditions. In **Fused**
mode, with no active stacking interface and no enabled lid, **Cradle**,
**Bore**, **Post**, **Pocket**, **Slot Rack**, **Steps**, and a **Raised-Wall**
Photo Nest may extend above the rim - a 30 mm post can stand as a ring holder
on a 10 mm wall, for example. **Divider**, **Scoop**, **Text**, and a
**Recessed** Photo Nest always stay bounded by the bin, in every mode, because
their geometry genuinely depends on the material above them. Every part in
**Separate** or **Cartridge** mode stays height-bound too. Stacking, a lid,
and the existing wall-touching connector clearance always win regardless of
this policy - a tall holder that would collide with any of them is refused,
never silently shrunk or clipped, and the bin is never made taller
automatically to accommodate it. The 3D editor shows a plain informational
note ("Extends N mm above rim") when the part being edited legally does so;
there is no separate "allow above rim" setting.

**Photo Nest — a custom holder built from your photo.** Put one flat tool on a
US Letter (8.5 × 11 in) sheet, keep all four paper corners visible, photograph
it directly overhead, and upload the photo. Wavefinity corrects the paper to its
true size, traces the tool's outline, and asks for one number: **Tool
thickness**. As soon as both are ready it builds a complete, practical,
printable bin in seconds — no other choice is required. Missing paper, severe
perspective, an edge-touching part, multiple parts, and unusably small/noisy
outlines are rejected with a specific correction. If automatic paper detection
fails, Wavefinity switches to the 2D view and shows the original photo. Click
all four paper corners in any order; Wavefinity orders and validates them
automatically and retries the same photo without requiring another upload.
The retired measured/segment
Nest format is rejected explicitly rather than silently reinterpreted.

A new scan defaults to **Recessed Cavity**: a solid deck fills the fitted area
and the tool's own shape is cut down to the ordinary printable floor, with a
small automatic lead-in so the tool drops in without catching an edge. Cavity
depth defaults to **60% of Tool thickness** and stays in that Auto mode -
recalculating whenever Tool thickness changes - until it is hand-edited, which
switches it to Manual (with a **Reset to 60%** button to switch back); a
Manual depth is clamped to Tool thickness if that later gets thinner.
**Raised Wall** remains available: a contour-following wall grows from the
floor, with an adaptive exterior buttress sized to its own height (rather than
one fixed foot) and a gentle top round, broader outside than in.

**Finger access** defaults to **Automatic**: one Python search finds a safe
pair of opposing openings (or falls back to one, or to none with a warning) -
spherical scoops cut into a Recessed deck, rounded U-notches cut into a
Raised Wall. **Off** leaves the holder plain. **Custom** exposes Sides / Ends
/ Both and a 12-40 mm opening width. **Push Out**, raising the tool on a
shaped floor with one end left low to press up, remains an advanced
Raised-Wall-only option; switching to Recessed while it is active turns
Finger access back to Automatic instead.

**Automatic footprint sizing** is on by default: the bin's Width and Length
grow or shrink to the smallest footprint that fits the holder, centred, every
time the outline, Tool thickness, Holder or Finger access changes. It owns
Width/Length only — Bin Height is always the height the user set, and a
manual Height edit never turns it off. Typing a Width or Length, or dragging
the Nest off-centre, turns it off for that design ("Fit footprint to tool"
then does the same X/Y fit as a one-off); turning it back on recentres and
resizes again. A design saved before Auto-size existed keeps its old
grow-only behaviour unchanged, including its historical Z growth.

The 2D layout draws the softened silhouette - the same one the printed part
gets - with move, proportional-resize and rotation handles, plus an outline
editor: drag a point directly, **Add Point** (click near an edge) and
**Delete Point** (click a point, minimum three left), and **Reset outline**
to return to the most recently accepted scan. **Photo opacity**, **Object
sensitivity** and **Edge cleanup** are available in the 2D **Scan controls**
panel (the scan settings default to reproducing the original trace); a slider shows
its retraced candidate dashed over the accepted outline without changing
anything until **Apply adjusted outline** accepts it, and a tuning attempt that fails
to produce a valid outline leaves the accepted one untouched. **Fit
clearance** sets the gap between the holder and the part, and **Soften
outline** rounds off small inward and outward details - a separate pass from
Edge cleanup, which affects tracing itself. Photo opacity dims the reference
photo behind the outline in the browser only; it disappears, along
with the tuning and paper-corner tools, once a design is reopened without its
original photo, since the photo itself is never saved.

Cradle holders also offer **Alternate ends** (off by default): when enabled,
every second repeated tool sits near the opposite end of the run axis, leaving
about 10% of that axis clear at each end. Each trough becomes its own separate
solid body. Alternating needs a run axis at least 1.25× the tool length; turn
it off, or rotate, if the run axis runs short. Saved as `alternate_ends`; no
effect when only one tool fits.

| Holder | Purpose | Optional `key=value` settings |
|---|---|---|
| `cradle` | Half-round troughs along X or Y - `spacing` 0 joins the row into one shared body, higher values split it. No fit clearance; wall thickness auto-scales with the tool | `spacing`, `floor_gap` |
| `nest` | Photo-traced Photo Nest: a Recessed Cavity deck (default) or a Raised Wall, on the bin floor or removable insert, with Automatic (default), Off, or Custom finger access, or Push Out (Raised Wall only). `rim` (thickness) is fixed | `clearance`, `smoothing`, `tool_thickness`, `holder_style`, `cavity_depth`, `cavity_depth_mode`, `auto_size`, `lift_assist`, `finger_position`, `finger_width`, `push_position`, `push_area`, `push_depth` |
| `bore` | Round, hex or square holes for items standing up. One `bore_style`: `base_straight` (default), `base_wavy`, `walls_straight`, `walls_wavy`. Sizing is persistent: `xy_size_mode` (`manual` / `bore_to_bin` / `bin_to_bore`; Walls Only offers only `manual` and `bin_to_bore`, default `bin_to_bore`) and `height_size_mode` (`manual` / `bore_to_bin` / `bin_to_bore`). X/Y counts are always explicit. Auto Height under an Edge Mount screwdriver-access hole stops 2 mm below the lowest cutter. A Base cavity may be as deep as the Bore is tall (`depth == height`) | `bore_style`, `depth`, `height`, `wall` (Walls Only only), `columns`, `rows`, `xy_size_mode`, `height_size_mode` |
| `post` | Lightly tapered pegs for rolls, spools, sockets and ring-shaped parts | `diameter`, `height`, `spacing`, `taper` |
| `divider` | One or more straight or leaning subdividing walls along X or Y, with optional sloped tool-slot bottoms and per-compartment **Labels** (No label / On base / Rim level) | `height`, `thickness`, `angle`, `spacing`, `bottom_angle`, `reverse_bottom`, `alternate_bottom`, `minimal_bottom`, `bottom_supports` |
| `pocket` | Raised rectangular tray with a recessed centre and 0.5 mm chamfered edges | `height`, `wall` |
| `slot` | Slot Rack: angled slots for driver bits, cards, and small tools | `height`, `depth`, `thickness`, `angle`, `wall`, `wall_style` |
| `steps` | Tiered riser shelves that climb from front to back | `height`, `count` |
| `text` | Centered lettering, Inlaid or Raised, on the base or at a rim wall; one 3MF object each. One On-base Text per bin, one At-rim Text per rim side | `text`, `cap_height`, `quarter_turns`, `depth`, `raised`, `level`, `rim_side` |

**Divider labels.** The **Labels** group has one **Label Type**: *No label*
(default), *On base* or *Rim level*. Each compartment gets a text box whose
grey placeholder shows its position (`1,1` is the front-left compartment;
columns run left to right, then rows front to back). Placeholders are hints
only — they are never saved or printed. Base labels are inlaid into the floor.
Rim labels sit on a shelf against the chosen wall (Back for a new Divider; a
saved side is kept) whose root runs into the real wavy wall material on both the
flat top and the sloped underside, without reaching the outside skin. Each
label's lettering is its own recessed part of the 3MF.

**Bore supports.** A **Walls Only** Bore sized around its holes (`bin_to_bore`)
reaches the bin wall with **thin webs** about one Bore wall thick — a straight
web for Straight walls, a wavy web following Wavefinity's wall wave for Wavy —
at most one per bin wall for each connected group of holes, only where there is
a real gap. Sleeves that already touch a wall are simply fused to it, and every
requested opening is re-cut after the webs are added, so a web never narrows it.

**Slot Rack** makes angled slots for driver bits, cards, and small tools. It is
separate from Divider, which makes upright compartment walls.

A divider can lean up to **45 degrees** off vertical — the standard
support-free FDM overhang limit — for holding what it stores at an angle
instead of straight up. `angle` is signed (negative leans the other way). A
second flag, `wedge` (default **on**), picks the cross-section: a wedge
keeps its back face vertical and only the leaning face slopes, so the wall
stays thickest at the floor — where the sideways push of whatever leans
against it actually bears — and tapers as it rises, the shape a physical
gusset uses. Turning `wedge` off gets a uniform-thickness sheared wall
instead: the same lean, thinner at the base, and the shape that snaps.
In the browser this control is now labelled **Wall lean** so it is not
confused with **Bottom slope** below; `wedge` / straight still applies only
to the wall lean.

A divider can also tilt the **bottoms of the tool slots** it forms, so a
tool rests at an angle without the wall itself leaning. `bottom_angle`
(0–80°, default 0 — a plain flat bin bottom, so older designs are
unchanged; choosing Sloped in the editor starts at 45° and Curved at 60%,
or the largest value that legally fits a short bin) sets the rise, measured along the divider/tool direction: +X
(toward the right) for a divider that runs along X, +Y (toward the back)
along Y. `reverse_bottom` sends the rise the other way; `alternate_bottom`
flips every second slot, ordered across the divider zone, and
`reverse_bottom` then flips that whole alternating pattern. `count`
dividers make `count + 1` supported slots, each rising `slot_length ×
tan(bottom_angle)` from the existing floor. A combination whose high end
clears the divider height or the bin is refused with a plain "reduce the
bottom slope, shorten the run, or increase the bin height". By default the
slope material is one solid wedge per slot; `minimal_bottom` replaces it
with `bottom_supports` (default 3, a positive whole number) evenly spaced
crossbars that touch the same theoretical sloped plane, print support-free
(vertical stems, 45° gussets to the floor), and use materially less
plastic. Either way the normal structural bin floor or removable-insert
plate is untouched — this is only the material added above it.

Every divider path that meets the floor - wedge, straight-leaning, plain
vertical, or full-span - also gets a 1 mm, 45-degree strengthening chamfer
where its two long faces meet the floor
(`DIVIDER_CHAMFER`). It is a pure addition below the wall's stated profile,
not a substitute for any of it: the lean and thickness the fields describe
are exactly what is built above that first millimetre. A full-span divider is
built by its own trimmed path, which gives it the same strengthening foot while
still following the true interior wall outline.

A divider can also be told to run the full width or depth of the bin and
hug the box's true wavy wall exactly — not the safe straight-sided
rectangle every other holder is confined to, which would leave a visible
gap at most points along the wall. This `full_span` flag works together with
a lean: the two combine into one 3D boolean intersection against the bin's
real interior volume, so a leaning full-span divider hugs the wave in both
directions at once. The browser sets it by default for every new divider -
"wall to wall" is the normal case, and there is no manual toggle for it yet
(saving a design still preserves whatever a script or an older save set it
to, `full_span` or not).

A divider is also the one kind whose `along` is a direct browser choice
("Runs along" X/Y) rather than inferred from its footprint, and whose
`count` places several parallel walls instead of repeating some other
element: `count` dividers split the cross axis into `count + 1` equal gaps -
fence-post spacing, so `count = 1` (the default) lands exactly where a
single centred divider always has. `spacing` overrides that computed gap
with an exact one instead (blank keeps it automatic); since it is used as
the gap as-is, an override only keeps the group centred if it happens to
equal the auto value. Height, angle, thickness and spacing apply to every
wall the count places, not just one.

Builder options are intentionally generic. The editor passes them to the
registered builder, so a future `@feature` function can add its own settings
without changing the layout file format or editor data model.

### The wave

Every straight wall carries the same global-phase circular-arc wave:

- **3.5 mm per full cycle**, two cycles per 7 mm grid cell.
- **0.4 mm deviation each way**, 0.8 mm peak to peak.
- Alternating circular segments meet with a shared tangent at each zero crossing.
- The wave stays at full amplitude up to the corner chords.

The displacement is `f(y)` on walls running along Y and `-f(x)` on walls
running along X, where `f` is odd and periodic. A quarter-turn maps this pair
back onto itself. Any side can therefore mate with any compatible side after
0, 90, 180 or 270 degrees of rotation, including a short wall meeting part of
a longer wall. Placement still follows the 7 mm grid; arbitrary angles and
off-grid translations are not supported mating positions.

Side and corner connectors follow that same signed arc profile, including their
arms, different-height webs and lock notches. The existing chamfered wall bumps
and receiving notches keep their locking action. Connector positions remain
whole 3.5 mm cycles: a half-cycle shift still needs a mirrored channel.
Compatible seams require matching wall thicknesses and enough shared wall for
the connector, with the existing rim-height and lid restrictions.

This changes printable geometry. Regenerate adjoining bins and connectors as a
set; earlier sine-wave prints do not share the new mating profile. Physical fit
and lock feel still need a print review.

### The 7 mm size grid

**Box X and Y must be whole multiples of 7 mm, from 7 mm up.** X and Y are
independent, so 16x16, 16x48, 40x56 and so on are all fine — nothing has to
scale proportionally.

**One unit is 7 mm** — the grid step itself — so every legal size is a whole
number of units and no decimals are needed: 1, 2, 3, 4, 5, 6 = 7, 14, 21, 28,
35, 42 mm. The browser UI takes the modular drawer footprint in millimetres and
snaps it to the nearest 7 mm step. Usable interior is a derived measurement;
making it the input would add the wall allowance once per bin and break mixed-size
tiling.

**14 mm (2 units)** is the smallest box that takes a connector on both sides. A
1-unit side is still legal and useful: a 7 mm wall is too short for a connector
and too short to seat a lock bump, so a narrow bin joins on its long sides only
— put the clips where clips work. Asking for a connector on a wall that cannot
hold it gives a clear error rather than bad geometry.

The rule falls out of wanting to drop boxes of any size into a drawer and have
every seam work. Pack boxes edge to edge and a box of size `S` sits with its
centre half a size in from its edge. Sizes that are multiples of `2 × 3.5 mm` put
every box centre on a multiple of the wave, and once that holds,
`f(y - centre)` becomes `f(y)`: **the wave stops depending on
which box it belongs to and becomes one global function of position in the
drawer.** Any two walls that meet then nest, whatever the boxes measure.

Off-grid sizes still tile with their own clones but foul the moment they meet a
different size: a phase shift can put crest against crest. They are rejected with the nearest legal size named.

### What a size actually measures

The UI shows this live as you change the size:

| X units | Grid footprint | Outside (crest to crest) | Usable inside | Joins on |
|---:|---:|---:|---:|---|
| 1 | 7 x 42 | 7.55 x 42.55 | 4.06 x 39.06 | long sides only |
| 2 | 14 x 42 | 14.55 x 42.55 | 12.06 x 39.06 | both |
| 4 | 28 x 42 | 28.55 x 42.55 | 25.06 x 39.06 | both |
| 6 | 42 x 42 | 42.55 x 42.55 | 39.06 x 39.06 | both |

(All 6 units deep, so 42 mm in Y.)

**Grid footprint** is what the box occupies in the drawer. **Outside** is the
real bounding box — the wave crests stand one amplitude proud of the footprint
on each side, and the mating gap pulls it back a little. **Usable inside** is the
largest straight-sided object that fits: both faces of a wall carry the same
wave, so the cavity is a constant-width channel that **weaves** side to side, and
anything straight has to clear the full swing. That costs one amplitude at each
end on top of the two walls.

### Grid and mating

Boxes tile on the 7 mm grid with the same global circular-arc wave on every
wall: **3.5 mm per cycle**, **0.4 mm amplitude**, and **0.25 mm nominal mating
gap** across a shared seam. The wave is uninterrupted along each wall; no
periodic dents or local T-junction recesses are added. Normal clearance is
smaller than the across-seam gap; `nested_clearance()` derives its conservative
bound from the arc slope.

Wall runs stop `CORNER_INSET` = **1.0 mm** before the nominal corner. At the
default corner fillet the two runs' own waves are continued through the corner
and joined by a tangent fillet of `CORNER_TIP_RADIUS` = **0.25 mm** (Story
2425). The continuation keeps the seam's offset to every unchanged receiving
wall, so no dents are needed. Each corner is checked against those walls (to
`T_JUNCTION_CLEARANCE` = 0.164 mm) and the diagonal bin's corner; if a check
fails the tip radius grows, and the earlier **0.6 mm** outline rounding of a
chord corner remains the fallback and the behaviour of any other corner fillet
setting. The opening where four bins meet is smaller than the chord's, but its
size is unverified. The cavity remains the finished
exterior eroded by the declared wall thickness. Preview rings follow that same
finished exterior and cavity; side clips follow the original eroded wall face.

**Direct repair, 2026-10-31:** Andrew reported rough waves and mismatching bin
edges after the corner-tightening work. Story 2335 added 0.30 mm inward relief
at interior 7 mm nodes, changed connector faces to clear that relief, and
restricted fine-grid placement. Those changes and Story 2300's pointed corner
posts were backed out together, restoring the geometry from `05ae617`.
Finished-outline preview sampling is retained. Smooth, matching walls take
priority over the smaller corner opening. Regenerate bins and side clips made
with the corner-tightening profile as a set; existing exports do not update.

### Lock detent

Each wall carries a row of **small chamfered bumps** on its **interior face**,
and each connector arm has **matching notches**:

- **0.35 mm** protrusion, 1.0 mm tall, 1.2 mm long
- One on **every** wave extremum the wall can carry — crests as well as troughs,
  so every 2 mm — kept clear of the corners. A 14 mm wall gets four, a 42 mm wall
  gets twenty, a 7 mm wall gets none
- Both faces run at exactly **45 degrees** from the buried root right out to the
  tip, so there is no horizontal face anywhere on the feature: it prints
  **without supports** in either orientation
- Top of the feature sits 4.0 mm below the rim

Push the connector down and the arms ride over the bumps, then the notches drop
over them. Seated, the clip is free (0.0 mm³ interference); lifting it drives the
notches onto the bumps, and that is the lock.

Because every box centre lands on a multiple of the wave, these bump positions
form **one lattice shared by every box in the drawer**. That is what lets a
connector engage *both* neighbours even when they are different sizes.

### Connector

A staple that drops over the seam between two boxes; its two arms descend inside
both. Arms are **1.0 mm** thick (two 0.5 mm perimeters), the cap is 1.2 mm, total
height 9.6 mm, default length 12 mm.

Set the two rim heights in **Connect bins**. When they differ, the arm over the
shorter bin is extended by the height difference, so both sides still lock. The
generated file is flipped with its flat cap down for support-free printing.

Across that extension the shorter bin's wall has not started yet, so the arm has
nothing bracing it. Past a 2 mm difference the extended arm is fattened into a
**tapered web** over the unbraced span — up to 3.0 mm thick at a 30 mm
difference (a 50→20 mm pair), ramped back to a plain arm over the last 6 mm
before it enters the bin, with a brace in the corner under the cap — and the
whole part is made up to **50% longer** so more bumps share the load. Equal-rim
connectors are unchanged. Handles differences of roughly 30–40 mm; see the
`DIFFERING_*` constants in `organizer_engine.py`.

The 0.02 mm tolerance, 12 mm length and 9.6 mm base connector height were
chosen from a printed five-clip fit plate. **Connect bins** shows the resulting
printed height, including any extension for a shorter bin.

For equal-height bins it is one universal part and goes on either way round.
For unequal-height bins, generate the connector with the two actual rim heights.
Its centre has to land on a **whole wave**, so `--position` must be a whole
multiple of **3.5 mm**; anything else is rejected.

Whole waves, not half waves. The corridor between the arms is cut to the wall's
wave, and that wave *inverts* every half cycle. A clip made a half-wave along is
therefore the printed one **mirrored** — identical volume, and a shape no amount
of turning a part over will produce. Slide the real part half a wave onto a seam
and it meets the wall crest to crest, jamming by about 48 mm3. The rule used to
accept 2 mm, and every fixed position the tests exercised happened to land on a
whole wave, so nothing caught it.

A clip also needs open cavity on **both** sides of the seam. Where two short bins
butt end to end, the far side of the seam at that joint is their end walls, full
height — so the clip has to clear the joint by half its own length, which on the
3.5 mm lattice makes the first usable spot 7 mm away.

Reversibility is why the bumps sit on **every** extremum rather than every other
one. Two things have to line up when you spin a connector: the wall it hugs must
look the same upside down about the connector's centre, which needs the centre on
an **even** millimetre, and the notches must mirror about that centre, which with
bumps every 2 mm they do. With bumps on alternate extrema the two requirements
landed on odd and even millimetres and could never both hold — **no length or
position could fix that**, which is why the wave shape had to change instead.

Note that spinning the part and *moving* it are two different requirements.
Turning it over needs an even millimetre; being the same part at all needs a
whole wave. Whole waves satisfy both, which is why 4 mm is the rule.

### Flat wall band at the base (optional)

The wave runs on both faces of a wall, so the inside is wavy too, right down to
the floor. An advanced setting, **0 to 1 mm**, gives the bottom of the bin a
band of **flat** wall rising from the floor:

| Setting | What you get |
|---:|---|
| 0.0 | wavy all the way down (default) |
| 0.5 | the first 0.5 mm above the floor has flat walls |
| 1.0 | the first 1 mm above the floor has flat walls |

It is a **height**, not a strength: the wave above the band is completely
unchanged. The cavity becomes two stacked shapes - a straight-sided one sitting
on the floor, and the usual wavy one above it.

The band is sized to the innermost point the wave ever reaches, so it only ever
**adds** material against the wall and can never cut into it. That is also why
**usable interior does not change**: the band is exactly the rectangle
`usable_inside` already reported.

The outside profile, the grid and the mating are untouched. The band sits on the
floor and the connector arms hang from the rim, so on any normal bin they are
nowhere near each other; on a very shallow one they would meet, and asking for a
connector then gives an error saying how tall the box needs to be.

### Text — centered lettering on the base or at a rim wall

**Text** is one part with one **Text Type** control:

1. **On base — Inlaid** (the default)
2. **On base — Raised**
3. **At rim — Inlaid**
4. **At rim — Raised**

Text is **centered automatically** in its destination; there is no Footprint,
Width/Depth, **Place it for me** or drag/offset control. Size comes from
**Letter height** (new On-base Text starts at 15 mm and shrinks only if the
bin needs it; never below the 5 mm minimum). **Turn** (0/90/180/270°) is
kept for On-base Text; At-rim Text reads the right way up for its **Rim side**
(default Back).

- **Inlay depth** (Inlaid) or **Raised height** (Raised): Thin 0.2 mm, Default
  0.4 mm, Thick 0.6 mm or Thickest 0.8 mm. Inlay depth is how deeply the
  letters are cut into the receiving surface (the pocket keeps its backing);
  Raised height is how far they stand above it. Deeper inlays require a thick
  enough base or insert to leave at least 0.2 mm of backing.
- Every Text is its **own part of the 3MF** (its own filament). The pocket and
  the inlay are exact complements. In a removable insert the lettering is inlaid
  into the **0.6 mm insert plate**.
- **One On-base Text per bin** and **one At-rim Text per rim side**, because
  each is centered on its destination. Different rim sides work independently.
  A second Text on an occupied destination is refused with a clear message
  instead of overlapping.
- **At rim** Text belongs to the **bin shell**, never to a removable insert. It
  sits on a **7 mm** shelf just below the rim, whose surface stays **3.4 mm**
  below the rim so the stacking foot or lid still fits. **Raised** rim Text
  lowers its shelf by the Raised height, so the top of the letters stays at that
  safe datum. Rim Text reserves **no floor space**, but it cannot share a wall
  with a Side Opening, a Separate Edge Mount label, a Divider rim-label shelf
  or a real overlap with an Inside Handle.
- Base Text keeps others away by its **real letter shapes** plus the normal gap,
  not by an editor rectangle around them.
- Two texts reading the same thing get distinct part names (`M3`, `M3 2`) — a
  3MF object name has to be unique or the second silently replaces the first.
- **Old designs still open.** Footprint, `auto` placement and the old single
  top-level rim label are read once and migrated: a base Text keeps its centre
  and effective Letter height, an old rim label becomes one At-rim Text on the
  same wall, and the next save writes only the new fields.

The `.3mf` is written as one assembly object with the body and every piece of
lettering as named parts, so Bambu Studio / OrcaSlicer opens it directly, and a
`Metadata/model_settings.config` sidecar opens the body on **filament 1** and all
lettering on **filament 2**. No print profile is embedded, so an opened file still
uses the slicer's current printer and process.

**The part name alone names the file**: `Box 48 x 48 x 40 Driver rack.3mf`.
Lettering does not appear in it — with several labels there is no answer to which
one would stand for the whole file. The first label you actually type seeds a
blank **Part Name** once (a bare size like `8` or `12mm` never does); after that
the two are independent, so a bin can say `M3` on the floor and still save as
`Driver rack`. Characters a filesystem would object to are stripped.

### Edge Mount

**Edge Mount modifies an ordinary bin; it is not a bin type, an interior
part, or a second bin-generation path.** It is available for a normal Bin
and for both Stacked Bin-to-Bin and Stacked Lid-to-Bin, and it is hidden (but
preserved in the saved design) while Storage Box is selected, since Storage Box uses a
separate body architecture. It lets a normal bin hang vertically outside a
cart, table, shelf or workbench: one selected wall (**Front** `-Y`, **Back**
`+Y`, **Left** `-X`, **Right** `+X` - the same convention the rim label
uses) faces the support. That one **side** setting controls both
subsections at once - there are no separate mounting-side and label-side
choices.

The editor reads in a fixed order: **Mounting side** is the only field above
both sections; **Label** and **Screw Mounting** are always-visible sections
below it, each owning its own enable control - Label's is a **Label: None /
Separate Part / Integrated** selector (its first control), Screw Mounting's
is a checkbox in its own section header. A brand-new Edge Mount opens at
Label **None** with Screw Mounting off; turning Label to **None** hides its
detail fields without erasing their stored values, so re-enabling Label
later restores the same text/dimensions. Saving still needs at least one of
the two switched on.

- **Label** - choosing **Separate Part** prints the projecting plate as its
  own **Edge Mount Label** file on one continuous shallow snap/slide saddle
  that follows the selected wall's real wavy shape; it is shown installed in
  preview. Separate labels also use vertical **Standoff Ribs** on the bin
  body by default: they match the clip's outer thickness so the bin sits
  flat on its mounting surface. Auto spaces the ribs across the selected
  wall, or you can choose 1-20 manually. Existing saved Separate labels keep
  ribs Off until you enable them. A Separate Part label is always
  Inlaid/Flush - it is exported and rotated for print with its text face
  down, so Raised is not a valid state for it, and the Label style control
  is hidden entirely while Separate Part is selected; this is enforced both
  in the editor and, so a legacy save or any non-UI input cannot bypass it,
  by the saved-shape data itself. **Integrated** keeps the original fused
  plate and can still choose **Inlaid/Flush** or **Raised**; old saved
  labels without a label type reopen as Integrated. **Length** is either
  Full Side (the wall's real wavy-envelope span) or Text Length (the fitted
  text plus a 2 mm margin on every side, never wider than Full Side).
  Projection is one exact 5-200 mm field; a new Edge Mount starts at
  one-third of the mount-normal bin dimension, clamped to that range.
  Thickness (0.8-6.0 mm) keeps its named choices; Integrated is marked **Requires support** (Separate is the support-free choice), and out-of-range thickness or text depth is reported beside the field instead of being silently clamped. The two free Label corners
  have a fixed ~1 mm 45-degree shave. Lettering reuses the ordinary text
  engine, sunk to a text depth that defaults to 0.6 mm for a new or missing
  Edge Mount (an explicit saved 0.4 mm design stays 0.4 mm - this default is
  Edge Mount's own and never touches the floor-label text-depth default used
  elsewhere), needing the usual minimum backing when flush. Text targets a
  12 mm cap height and only shrinks - never below 6 mm - to fit the plate;
  if it still will not fit at 6 mm, generation refuses with a plain
  explanation rather than truncating or enlarging the plate. **Flip text**
  (next to the Text field) turns the reading direction 180 degrees for
  mounting on the underside of a surface.
- **Screw Mounting** - its section-header checkbox reveals 1-4 round screw
  holes through the selected wall (default 2, arranged Horizontal or
  Vertical, default Horizontal), each paired with a larger round
  Screwdriver access passage that opens from the *opposite* wall and crosses
  the cavity to reach it - so a screwdriver can follow the screw in from the
  far side; that explanation lives as hover/title help on the checkbox
  itself rather than as permanent page text. Both holes are always round;
  there are no teardrops, countersinks or counterbores. Default screw
  diameter is 4 mm; new Screwdriver access choices are Small (6 mm),
  Default (8 mm), or Large (10 mm). Legacy exact access values reopen
  unchanged when relevant. The first (or only) hole centres 12.7 mm (1/2 in)
  below the top rim by default (**From top**); additional holes use Auto
  spacing (evenly fit, up to 20 mm apart) or an exact custom spacing. A
  pattern that cannot fit - too close to a corner, too close to the floor,
  or two access holes too close together - is refused with the reason,
  never silently shrunk, reduced or repositioned. Screw Mounting cannot
  share its mounting or opposite wall with Inside Handles; enabling both on
  conflicting walls is refused.

The plate's projection is real geometry but is not part of the bin's
nominal X/Y footprint, inventory dimensions or Space sizing/layout - those
keep using the ordinary bin size. A removable/cartridge insert is never drilled,
since it can simply be lifted out before the bin is mounted; the fused
access passage does clear any fused interior holder material blocking its
path, since that material cannot be removed. Edge Mount's own label is
independent of floor Text parts, the rim label, and Storage Box/divider labels -
none of those are migrated or replaced.

### Side Openings

Side Openings are available on ordinary flat 21 mm and 42 mm Gridfinity bins.
The requested cut is refused before geometry is built if it enters the 4.75 mm
foot plus its base, the optional open-bin stacking rim, the foot-carrying corner
radii, or leaves a remaining wall strip thinner than the selected wall thickness.
The largest existing opening size that meets those limits is supported; invalid
choices are never clipped or shrunk. Cuts remove flat wall material only, keeping
the outside envelope, rim support, feet and neighbour clearance by construction.
Third-party baseplate and printed fit remain **unverified** until Andrew records
his own fit prints. Edge Mount stays unavailable on both Gridfinity pitches:
it projects beyond the cell; only Andrew may approve a separate inside-envelope
replacement. Wavefinity Side Openings keep their existing behaviour.

**Side Openings modifies an ordinary bin; it is not an interior part.**
It is a normal **Options** palette option. It cuts centered finger-access
notches through selected bin walls - built by making the normal selected-grid
bin first, then subtracting negative cutter solids through the selected
wall(s), so the ordinary shell, cavity, wave, lock and connector geometry
never change. Default is off.

- **Shape** - Curved (a rounded finger slot) or Square (a rectangular
  notch).
- **Cutout on:** Front, Back, Left and Right are independent toggle buttons,
  not a single choice; any combination can be selected together. A new opening
  prefers Left + Right when both are legal.
- **Opening size** - Small (8 mm), Medium (10 mm, default), Large (15 mm)
  or XL (20 mm).
- **Vertical range** - two handles show the opening on one wall-height track.
  The lower handle is the percentage up from the floor; the upper handle is
  `100 - % from top`. Both work by pointer or keyboard and cannot cross.
  Saved designs keep their original `from_bottom_percent` and
  `from_top_percent` values.

On Wavefinity, a wall needs to be at least **2 Wavefinity units (14 mm)** long to take a
Side Opening at all, with a 4 mm solid corner shoulder kept at each end of
the opening. That modular rule means a 2-unit wall only offers Small, a
3-unit wall offers up to Large, and a 4-unit-or-larger wall offers every
size including XL. The browser only offers sizes that fit every currently
selected side and the current Shape and percentage combination; Python
re-validates the same rule and refuses an impossible saved or imported
combination outright.

Side Openings are for **ordinary bins only** - hidden for Storage Box and Base
Trim. Lid & Stacking limits the upper handle to keep its required
bridge. Curved supported openings use a pointed supportless arch with a
minimum 45-degree underside, rather than the old fixed arch.
A rim Text, an Edge Mount
mounting wall, or an Inside Grip may not share a wall with a Side Opening -
different walls are fine for all three. The scoop and other interior parts
are never globally blocked; the cutter is authoritative wherever a Side
Opening's wall intersects other body geometry, and it is re-applied to the
finished body right before export so a later fused feature can never
quietly fill an opening back in.

---
