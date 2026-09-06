---
title: Wavefinity
emoji: 🌊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Wavefinity — wavy drawer organizer generator

Parametric Python generator for a 3D-printable modular drawer organizer with
**wavy walls that interlock** and configurable holders inside. The local browser
UI, command-line interface, fit sampler and tests share the same Python box,
insert and export engines.

The basic system has a box and one **connector** — a small staple that joins two
boxes across their shared seam. Holders can be fused into the box, printed as a
removable fitted insert, or printed on an optional 8 mm cartridge footprint.
There is no corner connector.

Everything below is millimetres. This is the whole documentation for the
project: design, rationale, measured evidence, and the traps.

See [changelog.md](changelog.md) for dated implementation changes and
[TESTING.md](TESTING.md) for the log of what each test run actually found.

---

## Quick start

Double-click `Launch_Organizer_UI.vbs`. It starts Wavefinity without showing a
command window. On its first run it creates a private `.venv` beside the app,
installs the pinned geometry packages, starts the local Wavefinity service, and
opens the browser interface. Later launches reuse that environment. The service
listens only on `127.0.0.1`; it is not hosted on the internet and the browser
never replaces the Python geometry engine. Use `Launch_Organizer_UI.bat` only
when diagnosing a startup problem, because Windows must show a command window
for a batch file run directly.

Manual setup instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install opencv-python-headless==5.0.0.93 lib3mf==2.5.0 lxml==6.1.2 manifold3d==3.5.2 mapbox-earcut==2.0.0 matplotlib==3.11.1 networkx==3.6.1 numpy==2.5.2 shapely==2.1.2 trimesh==5.0.0
.venv\Scripts\python.exe wavefinity_web.py
```

Those ten pins are the whole dependency list. `matplotlib` is not optional — it
supplies the font outlines for floor labels. Run the tests with:

```powershell
.venv\Scripts\python.exe -m unittest
```

They take about two minutes; boolean operations dominate. **Log every run in
[TESTING.md](TESTING.md)** — the result, and whether it caught anything. Runs
that find nothing get logged too; that is how the file earns its keep.

### Using the browser UI

The page is split between intent-based controls and a large responsive
workspace. **Build your bin** contains the dimensions, print mode and interior
interior-part editor. **Customize your bin** contains the scoop and advanced
physical settings. **Label your bin** contains the rim label and the part
filename.

The 3D preview is real camera-independent geometry returned by Python and drawn
locally by the browser. Drag to rotate, use the wheel to zoom, and double-click
to reset. Click an interior part to open the 2D layout for adjustment. A single pixels-per-millimetre scale is chosen from the available
width and height, so enlarging the browser makes the model larger without
stretching it. The 2D tab uses the same rule and supports click-to-select,
drag-to-move and blue-corner resize. It draws the bin's true wavy interior,
not the flat placement rectangle - that rectangle still shows as a dashed
reference line, since every non-full-span interior part has to stay inside it, but
the wavy outline is what answers "does this actually reach the wall."

Selecting an interior part immediately builds its actual mesh and shows it
live, highlighted, right inside the main 3D and 2D bin views - at the bin's
own scale, alongside whatever is already placed, not on a separate isolated
canvas with its own camera. Parameter changes rebuild that draft after a
short typing pause, before it is added to the layout; a draft that is
currently invalid falls back to a red placeholder shape in the same spot, so
a rejected edit is never mistaken for no change happening. **Add interior
part** finds open floor space; selecting a placed one loads it back into the
same editor for exact changes. Invalid dimensions, overlaps, reserved
scoop/rim-label space, and lettering that cannot fit are reported beside the
preview and refused at export.

**Save design** downloads the existing `.wavefinity.json` format, and **Open
design** validates that format through Python before using it. Generated `.3mf`
files are written to the shown output folder, which is sticky — the server
saves it to `wavefinity_prefs.json` next to the app, so it survives a reload
or a different browser rather than resetting every launch. The browser API is
same-origin only, accepts JSON only, and applies a restrictive
content-security policy so an unrelated web page cannot invoke local file
generation.

### Using the browser editor

The browser editor is a three-step flow: **1. pick a shape** from the
interior-part palette and read its one-line description; **2. set parameters**;
**3. add interior part**. Placed parts can be selected in the list or on the 2D layout,
then moved or resized there, or edited with exact numeric size fields. Normal layouts snap
to **1 mm**. Overlaps and out-of-bounds features are refused at export.

A **divider** is a special case with no manually-sized footprint at all: it
defaults to full-span (wall to wall) and centres itself, so there is nothing
for Center X/Y or a footprint Width/Depth to describe, and no separate
"fit it to the bin" action either - it already is. Its whole field set is
just **Width mm** (the wall's own thickness), **Height mm** (blank by
default, reading "height of box" until you type one), **Angle °**,
**Quantity**, **Spacing mm** (blank - "fills evenly" - until overridden with
an exact gap), and **Leaning shape**. Every other kind keeps manual sizing
and the ordinary per-kind **Auto** button next to Quantity, since their
quantity means repeated elements inside one footprint, not sections of the
bin.

### Insert types

The browser UI offers two: **Fused**, where holders print as one solid part
with the bin — strongest, uses the most floor area, but the parts are
permanent — and **Removable**, where holders print separately on a thin
0.6 mm base plate that drops into the bin, so the interior can be swapped
while the bin stays put.

A third mode, **8 mm cartridge**, exists at the engine and CLI level
(`--mode cartridge`): a removable insert constrained to whole 8 mm cells, so
it is repeatable and interchangeable between matching bins at the cost of
some usable edge area (on the 128 x 88 comparison bin that is 120 x 80 mm,
9.8% less floor). The browser UI does not expose it as a choice — reusable
coordinate footprints across bins are a scripting concern, and picking it by
mistake in the editor just produced a confusing revert once an already-placed
interior part did not land on an 8 mm cell.

Tall holders may use the middle of the bin, but anything entering the 2 mm strip
beside a wall is capped below the connector arms. The editor's default divider
height follows that limit; an explicit unsafe height is refused at generation.

**Fused** is the default and gives the most usable floor.

Floor lettering is a **text** interior part, placed and checked like every other
one — see [Text on the floor, and the rim label](#text-on-the-floor-and-the-rim-label).
A bin may carry several. In removable modes each is inlaid into the insert plate
rather than hidden under it. The **rim label** is separate: fixed 5 mm letters
inlaid flush into a 7 mm-deep rear ledge at the rim, whose underside rises at 45
degrees and prints without supports.

The optional **curved scoop** spans the usable width at the front of the bin and
rises halfway up the usable wall height, so a part sweeps forward and lifts out
over the low front lip — the opposite wall from the rim-label ledge. In
removable modes it is part of the insert; in fused mode it is part of the box.
An auto-placed text moves clear of the scoop strip, and the 2D editor shades the
space reserved by a scoop or rim-label ledge and refuses overlapping parts.

What a scoop reserves is not its whole run. The curve meets the floor
tangentially, so its innermost millimetres are only microns proud of it — on a
40 mm bin the ramp stands 0.03 mm off the floor one millimetre in from where it
lands. Reserving that lip called a divider across the middle of the bin
"invalid" when it was in fact sitting flat, so the keep-out stops where
the curve has risen `SCOOP_FLOOR_TOLERANCE` (0.4 mm, about one layer) instead.
`scoop_floor_zone` is still the true footprint, used where the real extent
matters; `scoop_keep_out` is the smaller strip an interior part has to avoid.

Bin wall, floor, and mating geometry use the tested printable defaults. The
editor exposes only the dimensions and interior-part settings that affect the part.

Three buttons: **Generate Box** (including the current insert layout) and
**Generate Connector**, with a smaller
**Generate Sampler** beside them. There is no status bar — a button reports on
itself, briefly reading *Saved* when it has written the file, so nothing takes
up a line saying "Ready" for the 99% of the time it has nothing to report. A
failure still raises a dialog, because it needs acting on.

### The browser service

`wavefinity_web.py` is a dependency-free `http.server` wrapper, nothing more:

```text
Browser UI (HTML/CSS/JavaScript)
              |
       same-origin JSON
              |
Local loopback service (Python standard library)
              |
Existing design, validation, mesh and 3MF export modules
```

It is a stateless translation layer — every request carries the complete
design, every response uses the same versioned `.wavefinity.json` schema the
CLI and saved files already use. Nothing about the geometry, validation or
export changed to add it; the browser is a new consumer of the existing
engine, not a reimplementation of it. It binds to `127.0.0.1:8765` by
default and is never exposed to the network.

| Route | Purpose |
|---|---|
| `GET /api/health` | Identify an existing Wavefinity server. |
| `GET /api/catalog` | Registered interior parts, modes and initial values. |
| `POST /api/preview` | Validate a design and return camera-independent geometry, plus an optional live-highlighted draft. |
| `POST /api/design/validate` | Validate and normalize a saved design. |
| `POST /api/feature/default` | Create an engine-derived interior-part draft. |
| `POST /api/feature/draft` | Build one interior part's own mesh faces to validate it and resolve its blank options. |
| `POST /api/feature/apply` | Snap, validate, add or update an interior part. |
| `POST /api/feature/delete` | Remove an interior part. |
| `POST /api/layout/mode` | Convert a layout between print modes. |
| `POST /api/generate` | Generate the organizer parts. |
| `POST /api/connector` | Generate a connector. |
| `POST /api/sampler` | Generate the fit sampler. |
| `POST /api/preferences` | Persist sticky per-machine settings (currently the output folder) to `wavefinity_prefs.json`. |

**Security boundary**, since the service writes files: loopback binding
only; POST routes require `application/json` and reject a foreign `Origin`;
static file paths resolve beneath `web/`, blocking traversal; every response
carries `nosniff` and same-origin resource policy, the static page also gets
`no-referrer` and a same-origin-only content-security-policy; request bodies
are capped at 25 MB; no cookies, accounts, credentials or telemetry. The
output-folder field intentionally lets the local user pick any writable
path — that is application function, not a sandbox escape. Mesh boolean
operations run behind a process-wide lock, serializing geometry work rather
than risking concurrent calls into the mesh backend — fine for one local
user, not a multi-user server design.

**Known limitations:** no standalone browser/DOM test suite yet — Python API
contracts and JavaScript syntax are covered by `test_wavefinity_web.py` and
`node --check`, interactive QA is manual. A very dense design (many
cradle/bore parts at once) serializes a large triangle payload to
the browser; camera motion stays client-side and fast regardless, but the
initial load is heavier. **Save design** relies on the browser's own
download prompt, which some browser-automation tools cannot observe as an
event — a real browser session shows it normally.

---

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

When any interior part does not fit the current bin, an **Auto Expand Bin** button
appears at the top of the interior section; it grows the bin on the 8 mm grid
to the smallest size that holds every interior part at its real footprint (a clamped
cradle gets its full length back), trims any axis that overshot, and leaves
each part where it sat.

**Photo Nest — custom part cavity** creates a raised cookie-cutter wall from a JPG, JPEG, PNG,
or WEBP photo. Put one flat part on an 8.5 × 11 in sheet, keep all four paper
corners visible, and photograph it directly overhead. Wavefinity corrects the
paper to 215.9 × 279.4 mm, isolates the outside silhouette, cleans camera
noise, and stores only the closed millimetre contour — never the source image.
The 2D layout draws the softened silhouette — the same one the printed cutter
gets — and provides move, proportional-resize, and rotation handles. Only two
settings are exposed: **Fit clearance** sets the gap between the wall and the
part, and **Soften outline** rounds off small inward and outward details so the
wall does not have to trace every jag. The wall's
thickness and height are fixed printable defaults. The Photo Nest prints on its
own as a bare cookie-cutter loop standing straight on the bed — no wavy bin, no
floor — with a chamfered foot so the thin wall has no sharp root to snap at. It
holds the part in place; it is not a filled block with the part cut out. The
outer bin width and depth still recalculate to the smallest enclosing 8 mm-grid
footprint. Missing paper, severe perspective, an edge-touching part, multiple
parts, and unusably small/noisy outlines are rejected with a specific
correction. The retired measured/segment Nest format is rejected explicitly
rather than silently reinterpreted.

Cradle holders also offer **Alternate ends** (off by default): when enabled,
every second repeated tool sits near the opposite end of the run axis, leaving
about 10% of that axis clear at each end. Each trough becomes its own separate
solid body. Alternating needs a run axis at least 1.25× the tool length; turn
it off, or rotate, if the run axis runs short. Saved as `alternate_ends`; no
effect when only one tool fits.

| Holder | Purpose | Optional `key=value` settings |
|---|---|---|
| `cradle` | Half-round troughs along X or Y - `spacing` 0 joins the row into one shared body, higher values split it. No fit clearance; wall thickness auto-scales with the tool | `spacing`, `floor_gap` |
| `nest` | Photo-scaled cookie-cutter wall on a chamfered foot, printed on its own with no bin. `depth` (height) and `rim` (thickness) are fixed | `clearance`, `smoothing` |
| `bore` | Round, hex or square holes for items standing up | `depth`, `height`, `wall`, `columns`, `rows` |
| `post` | Lightly tapered pegs for rolls, spools, sockets and ring-shaped parts | `diameter`, `height`, `spacing`, `taper` |
| `divider` | One or more straight or leaning subdividing walls along X or Y, with optional sloped tool-slot bottoms | `height`, `thickness`, `angle`, `spacing`, `bottom_angle`, `reverse_bottom`, `alternate_bottom`, `minimal_bottom`, `bottom_supports` |
| `pocket` | Raised rectangular tray with a recessed centre and 0.5 mm chamfered edges | `height`, `wall` |
| `text` | Lettering sunk flush into the floor (or standing proud), one 3MF object each, any number per bin | `text`, `cap_height`, `quarter_turns`, `depth`, `raised`, `auto` |

There is no separate "slot" kind - a divider covers it. A slot's one real
extra, a shallow groove with a solid floor left under it, was a narrower need
than a full separator wall; the browser now defaults a new divider to run
wall to wall and lets `count` place several of them, which covers dividing
a bin into compartments in one action instead.

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
(0–45°, default 0 — a plain flat bin bottom, so older designs are
unchanged) sets the rise, measured along the divider/tool direction: +X
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

Every divider - wedge, straight-leaning or plain vertical - also gets a
1 mm, 45-degree chamfer where its two long faces meet the floor
(`DIVIDER_CHAMFER`). It is a pure addition below the wall's stated profile,
not a substitute for any of it: the lean and thickness the fields describe
are exactly what is built above that first millimetre. A straight
(non-leaning) full-span divider does not get one yet - it is built by a
separate, simpler path that has not been extended to match.

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

Every straight wall carries the same fixed-pitch wave:

- **4.0 mm per full cycle** — 2 out, 2 back
- **0.4 mm deviation each way**, 0.8 mm peak to peak
- **Odd about the wall's centre** — it leaves the middle at zero and comes back
  inverted
- **Full amplitude the whole way into the corners**; there is no corner blend

Changing X or Y reveals more or fewer whole cycles; it never stretches the wave.

Bins have an assembly orientation: **left mates with right, and top mates with
bottom**. Same-side seams are not part of the supported layout. The odd wave
keeps each opposing pair on the same global phase lattice.

Turning a bin 180 degrees is still fine, and that is what the odd wave buys.
Spun, a bin's +X wall lands where its —X wall was, and an odd wave means the two
carry the same shape, so the turned bin tiles exactly as before
(`test_a_box_still_tiles_when_it_is_turned_round`). The orientation rule above
is about which *faces* meet, not about keeping every bin the same way up.

### The 8 mm size grid

**Box X and Y must be whole multiples of 8 mm, from 8 mm up.** X and Y are
independent, so 16x16, 16x48, 40x56 and so on are all fine — nothing has to
scale proportionally.

**One unit is 8 mm** — the grid step itself — so every legal size is a whole
number of units and no decimals are needed: 1, 2, 3, 4, 5, 6 = 8, 16, 24, 32,
40, 48 mm. The browser UI takes the modular drawer footprint in millimetres and
snaps it to the nearest 8 mm step. Usable interior is a derived measurement;
making it the input would add the wall allowance once per bin and break mixed-size
tiling.

**16 mm (2 units)** is the smallest box that takes a connector on both sides. A
1-unit side is still legal and useful: an 8 mm wall is too short for a connector
and too short to seat a lock bump, so a narrow bin joins on its long sides only
— put the clips where clips work. Asking for a connector on a wall that cannot
hold it gives a clear error rather than bad geometry.

The rule falls out of wanting to drop boxes of any size into a drawer and have
every seam work. Pack boxes edge to edge and a box of size `S` sits with its
centre half a size in from its edge. Sizes that are multiples of `2 × 4 mm` put
every box centre on a multiple of the wave, and once that holds,
`sin(2π(y − centre)/4)` collapses to `sin(2πy/4)`: **the wave stops depending on
which box it belongs to and becomes one global function of position in the
drawer.** Any two walls that meet then nest, whatever the boxes measure.

Off-grid sizes still tile with their own clones but foul the moment they meet a
different size — a half-wave shift puts crest against crest, a 0.55 mm
interference. They are rejected with the nearest legal size named.

### What a size actually measures

The UI shows this live as you change the size:

| X units | Grid footprint | Outside (crest to crest) | Usable inside | Joins on |
|---:|---:|---:|---:|---|
| 1 | 8 x 48 | 8.55 x 48.55 | 5.06 x 45.06 | long sides only |
| 2 | 16 x 48 | 16.55 x 48.55 | 13.06 x 45.06 | both |
| 4 | 32 x 48 | 32.55 x 48.55 | 29.06 x 45.06 | both |
| 6 | 48 x 48 | 48.55 x 48.55 | 45.06 x 45.06 | both |

(All 6 units deep, so 48 mm in Y.)

**Grid footprint** is what the box occupies in the drawer. **Outside** is the
real bounding box — the wave crests stand one amplitude proud of the footprint
on each side, and the mating gap pulls it back a little. **Usable inside** is the
largest straight-sided object that fits: both faces of a wall carry the same
wave, so the cavity is a constant-width channel that **weaves** side to side, and
anything straight has to clear the full swing. That costs one amplitude at each
end on top of the two walls.

### Grid and mating

Boxes tile on a plain X by Y pitch. The solid outline is smaller than that pitch
by a **0.25 mm mating gap**, so two boxes placed one pitch apart have their waves
nested with a constant 0.25 mm clearance and never touch. Measured perpendicular
to the leaning wall rather than straight across the seam that is **0.21 mm**
— `nested_clearance()`, and the figure a slicer actually sees.

Where two wavy walls meet, the corner is a short chamfer eased to a **0.6 mm
fillet**. The rounding is a morphological opening, which only affects convex
corners sharper than that radius — the wave's own crests are far blunter, so they
come through untouched.

**Two of the four corners look flatter than the other two, and that is correct.**
Walls stop `CORNER_INSET` = 1.0 mm short of the nominal corner, wherever the wave
happens to be at that point. Because the wave is odd, one diagonal's walls end on
a crest and the other's on a trough, so the chamfer joining them comes out about
**1.97 mm** on one pair of corners and **0.86 mm** on the other. The 0.6 mm
fillet eases the ends of each chord but does not remove it, leaving roughly
**1.26 mm** and **0.50 mm** of flat in the exported solid. This is real geometry,
not a preview artefact.

It is also not a mating surface. A corner is a chord across the wave, and a
chord cuts *inward* from the envelope the walls sweep — so a corner can only
ever add clearance, never take it away. Two bins sharing a wall clear each other
by 0.21 mm the whole length of that wall, matched sizes and mixed sizes alike;
two meeting only at a corner clear each other by about **1.2 mm**.
`mating_clearance()` measures exactly this, and the suite pins it for a packed
drawer of seven different sizes.

### Lock detent

Each wall carries a row of **small chamfered bumps** on its **interior face**,
and each connector arm has **matching notches**:

- **0.35 mm** protrusion, 1.0 mm tall, 1.2 mm long
- One on **every** wave extremum the wall can carry — crests as well as troughs,
  so every 2 mm — kept clear of the corners. A 16 mm wall gets four, a 48 mm wall
  gets twenty, an 8 mm wall gets none
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
multiple of **4 mm**; anything else is rejected.

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
4 mm lattice makes the first usable spot 8 mm away.

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

### Text on the floor, and the rim label

Floor lettering is an **interior part**, not a property of the bin — so a bin can
carry **as many labels as it needs**: a size over each bore cluster, a name along
the front. Pick **Text** from the palette, type what it should say, and it moves,
resizes, turns and is checked against its neighbours through exactly the same
editor path as a cradle or a divider.

Each text is **sunk into the surface it sits on**: that surface gets a pocket and
the lettering is the solid that fills it flush, exported as **its own part of the
3MF**. The `.3mf` is written as one assembly object with the body and every piece
of lettering as named parts, so Bambu Studio / OrcaSlicer opens it directly — no
"load as a single object with multiple parts?" prompt — and a
`Metadata/model_settings.config` sidecar opens the body on **filament 1** and all
lettering on **filament 2**, so the two-colour intent is already set. No print
profile is embedded, so an opened file still uses the slicer's current printer
and process. (A generic 3MF from a non-slicer tool: recent Bambu Studio may still
note it "only contains geometry" — nothing is lost, and slicing is unaffected.)

- **Its zone is its size.** Drag a corner and the lettering scales to fill it.
  **Letter height** overrides that but is never allowed to overflow the box; a
  box too small to hold the text at the **4 mm** minimum is refused, saying what
  it needs.
- **Place it for me** hands positioning back to the engine: stay centred where it
  fits, otherwise move beside whatever is in the way, then turn, then shrink (no
  smaller than **7 mm** on that path). Dragging, resizing or turning it by hand
  switches that off, so it stays where you put it.
- **Stand proud** puts the letters on top of the floor instead of sunk into it.
  Either way they remain their own part on filament 2.
- Sunk **0.4 mm** into the default 0.6 mm floor, leaving 0.2 mm beneath, and
  reads correctly looking into the open box, which is the way the box prints.
  The pocket and the inlay are exact complements: put them back together and you
  get the plain box, to the last cubic micron.
- In removable modes the lettering is inlaid into the **0.6 mm insert plate**
  rather than hidden under it. Text that would hang over that plate's edge is
  refused rather than clipped mid-letter.
- Two texts reading the same thing get distinct part names (`M3`, `M3 2`) — a
  3MF object name has to be unique or the second silently replaces the first.

The **rim label** is the one piece of lettering that is not an interior part: it
sits on a shelf at the rear rim, so it has no floor zone to drag. Fixed **5 mm**
letter height on a **7 mm** front-to-back shelf, still a 0.4 mm-deep flush inlay
and its own part on filament 2; the shelf's underside rises 7 mm over its 7 mm
run, an exact 45-degree self-supporting slope. Leave **Rim label** empty for none. One
that cannot fit at its fixed size is rejected with a clear message rather than
silently shrunk.

**The part name alone names the file**: `Box 48 x 48 x 40 Driver rack.3mf`.
Lettering does not appear in it — with several labels there is no answer to which
one would stand for the whole file. The first label you actually type seeds a
blank **Part Name** once (a bare size like `8` or `12mm` never does); after that
the two are independent, so a bin can say `M3` on the floor and still save as
`Driver rack`. Characters a filesystem would object to are stripped.

---

## Command line

```powershell
python organizer_app.py box --x 40 --y 32 --z 55 --output box_40x32x55.3mf
python organizer_app.py box --x 48 --y 48 --z 40 --label BOLTS --output "Box 48 x 48 x 40 BOLTS.3mf"
python organizer_app.py box --x 48 --y 48 --z 40 --label M3 --label-position top --scoop --output custom.3mf
python organizer_app.py box --x 32 --y 32 --z 40 --flat-inside 1.0 --output flat.3mf
python organizer_app.py side --box-x 40 --box-y 32 --box-z 55 --along y --output side_y.3mf
python organizer_app.py kit --x 40 --y 32 --z 55 --output-dir generated_40x32
python organizer_app.py sampler --boxes 2x6,4x6,6x6 --output WAVY_SAMPLE_SET.3mf
python organizer_app.py organizer --layout drivers.wavefinity.json --output-dir generated
python organizer_app.py organizer --layout drivers.wavefinity.json --mode cartridge --label HEX --part-name "Driver rack" --output-dir generated
```

X and Y must be multiples of 8 mm (minimum 8); Z and wall are free. `--boxes`
takes units (`2x6`), or millimetres with an explicit suffix (`16x48mm`).

Generated box files are named for their size, plus the part name if there is
one: `Box 16 x 48 x 40.3mf` or `Box 16 x 48 x 40 Driver rack.3mf`. Lettering
does not appear in a filename — a bin may carry several labels. The connector is
one part, so it is just `Connector.3mf`.

On the `organizer` command, `--label` is sugar for a **text interior part that
places itself**, and seeds a blank `--part-name` from it; `--label-position top`
puts it on the rim ledge instead. On the plain `box` command (which has no
layout) `--label` remains a single centred floor label.

The `organizer` command reads either a complete saved UI design or a bare layout
object. A complete design supplies its box, rim label, scoop choice and part
name; explicit CLI values override any of them. `--mode` overrides the saved
fused/separate/cartridge mode.
Fused export writes one box file. Removable modes write a plain box and a
separate `Insert ...3mf` or `Cartridge ...3mf`. A lettered file is a strict 3MF
**assembly** — the body and every piece of lettering as named parts of one
object, one build item — with a `model_settings.config` sidecar opening the
lettering on filament 2. Both `.3mf` and `.stl` continue to work for legacy
individual-part commands.

## Generate the sample print file

Run the sampler command above to create `WAVY_SAMPLE_SET.3mf` with eight
separately selectable objects:

- **2 x 6 (16 x 48 mm)**, **4 x 6 (32 x 48 mm)** and **6 x 6 (48 x 48 mm)** boxes
- **Five identical connectors** at the locked 0.02 mm tolerance

Print the boxes open side up and the connectors cap side down; no supports either
way. The three sizes are deliberately different so you can check that mixed sizes
really do interlock and take a clip at every seam.

## Code layout

Four live Python modules and three test modules. Nothing here is legacy or
superseded — the old Tkinter desktop UI was fully removed once the browser
replaced it:

| File | Role | Entry point? |
|---|---|---|
| `organizer_engine.py` | Wavy boxes, connectors, glyph outlines and the text-to-solid core, mesh validation and 3MF/STL export. | No. |
| `organizer_inserts.py` | Item/segment model, zones, 1 mm and cartridge layouts, JSON persistence, holder registry, nine builders, and fused/removable assembly. | No. |
| `organizer_app.py` | CLI, exporters, validation and the catalog/defaults the browser service reads. | Yes, for CLI subcommands. |
| `wavefinity_web.py` | The local HTTP service — see [The browser service](#the-browser-service). | Yes, the default UI launch target. |
| `test_organizer_app.py` | Box, connector, label, preview, CLI and export regressions. | Only via `python -m unittest`. |
| `test_organizer_inserts.py` | Items, layout, registry, primitive and insert regressions. | Only via `python -m unittest`. |
| `test_wavefinity_web.py` | Browser-service API contract, security boundary and static-file regressions. | Only via `python -m unittest`. |

`web/index.html`, `web/styles.css` and `web/app.js` are the browser front
end: plain HTML/CSS and dependency-free JavaScript, no build step. `app.js`
holds all client state and API calls; it never computes geometry itself —
every preview, validation and export result comes from a `wavefinity_web.py`
call into the same engine the CLI uses.

`TESTING.md` is the running log of what those three suites have caught,
alongside the defects that got past them. It exists to answer a fair
question - whether two minutes a run is buying anything - with evidence
instead of a feeling.

Dependencies run one way: the insert module imports the geometry engine, the
app imports both, and the web service imports all three. Nothing is imported
back the other way.

Two things worth knowing before tidying anything up:

- The `*Tests` classes look unreferenced, because
  nothing calls them by name - `unittest` discovers them. They are not dead.
- Registered holder builders look unreferenced because the registry calls them.
  A new holder is one `@feature("name")` function; removing it is deleting that
  function. Check the tests before deleting apparently orphaned definitions.

Non-Python files:

| File | What |
|---|---|
| `Launch_Organizer_UI.vbs` | normal windowless application launcher |
| `Launch_Organizer_UI.bat` | bootstrapper and diagnostic launcher; starts the local service windowlessly |
| `generated/WAVY_SAMPLE_SET.3mf` | regenerable local sample print plate; intentionally gitignored |

## Working on this

This project is developed locally, mostly by prompting an LLM. GitHub is a
**backup and a record of what changed** — it is not a review gate.

**After completing an implementation, commit all changes and push them to
GitHub before reporting that the work is finished.**

**One prompt may become one cohesive commit.** Keep all code, tests, and
documentation needed to complete that prompt together; do not split a single
request into artificial commits just to make the history look smaller. When a
prompt is complete and its tests pass, commit and push it so the history has a
clear entry and the work is backed up. Separate unrelated prompts into separate
commits when practical. No feature branches or pull requests are needed for
this local workflow:

```powershell
.venv\Scripts\python.exe -m unittest
git add -A
git commit -m "short description of what changed"
git push
```

Add a line to [TESTING.md](TESTING.md) for that run before committing, and a
dated entry to [changelog.md](changelog.md) for the change itself.

**Run the full regression suite before every commit.** The only exception is a
change so minor it could not affect behavior — a label, a comment, a doc typo.
Any change to model assembly or build/geometry logic must be tested, full
stop, no judgment call. If a fingerprint test fails, that is the suite telling
you the geometry moved — decide whether you meant it, then re-pin deliberately.

**Write commit messages that say why.** The history is the record. A message
that explains the reasoning is worth more here than a tidy branch structure.

**Relaunching replaces whatever is already running on the port.** If a
relaunch finds the port taken, it first confirms a genuine Wavefinity
service - not some unrelated program - answers there (a real `/api/health`
response, not just something listening), then asks the operating system
which process currently owns that port (`netstat` on Windows, `lsof` on
macOS/Linux). It does not trust `wavefinity.pid` for this: a stale PID can
be reused by an unrelated program. It then kills that verified port owner
and rebinds. Only if a genuine service answers but no current port owner
can be found, or killing it fails, is it left alone and reported as already running - close
that window by hand and relaunch. A browser tab has no way to tell it is
talking to code from before your last edit, so silently reattaching to an
old process would serve stale code with no visible sign anything was wrong.

**A page that outlives the backend it loaded against says so.** The server
generates a random instance id on every start (`SERVER_INSTANCE`, separate
from `SERVER_VERSION`, so any restart is caught even without a version bump)
and returns it from `/api/health`. The browser polls that every 5 seconds; if
the id it gets back ever differs from the one it loaded with, the connection
indicator turns amber ("Engine updated") and a banner offers **Reload now**.
This is the backstop for the rare case the paragraph above can't fix on its
own - a genuine service whose process could not be identified - so an
editing session never runs silently stale for more than a few seconds
either way.

### If more than one person is working in the repo

Everyone commits to `main`, so the only rule that matters is: **pull before you
start, push as soon as you are done.**

```powershell
git pull --rebase        # before starting
git push                 # right after committing
```

Long-lived uncommitted work is the thing to avoid — two sessions editing
`organizer_engine.py` for a day will conflict, and geometry conflicts are
unpleasant to resolve by hand. Small, frequent, pushed commits keep that from
happening.

If a push is rejected because someone else pushed first, `git pull --rebase`
then push again. If that surfaces a real conflict, resolve it and **re-run the
full suite** before pushing — a merged file that imports cleanly can still be
geometrically wrong, and only the tests will tell you.

Also worth knowing before editing: the **traps** section below, and that
`.venv/`, `__pycache__/` and `generated/` are gitignored and should stay that
way.

---

# Design notes

Everything from here down is for whoever changes the geometry next. Several of
these numbers look arbitrary and are not.

## The settled numbers

| | Value | Notes |
|---|---:|---|
| Wave cycle | **4.0** | 2 out, 2 back |
| Wave amplitude | **0.4** | 0.8 peak to peak |
| Wave shape | **odd sine** about each wall centre | load-bearing |
| Mating gap | **0.25** | between two neighbouring walls |
| Size grid | **8.0** | box X and Y must be whole multiples |
| Minimum box | **8.0** | one grid step |
| One "unit" | **8.0** | so 1, 2, 3 units = 8, 16, 24 mm |
| Smallest box that clips on both sides | **16.0** | derived, not hard-coded |
| Wall | **0.8** | independent of the floor |
| Base thickness | **0.6** default, **0.4** minimum | shown under Advanced in Build your bin |
| Flat wall band | **0–1.0**, default 0 | height above the floor, not a fill depth |
| Corner fillet | **0.6** | walls stop `CORNER_INSET` = 1.0 short of the nominal corner |
| **Connector tolerance** | **0.02** | **locked** by a physical print |
| **Connector length** | **12.0** | **locked** |
| **Connector height** | **9.6** | **locked**; cap 1.2, arms 1.0 thick |
| Connector position step | **4.0** | one whole wave; half a wave wants a mirrored part |
| Mated wall clearance | **0.21** | 0.25 across the seam, measured perpendicular |
| Lock bump | **0.35** proud, 1.0 tall, **1.2** long | on every wave extremum, so every **2.0** |
| Bump corner clearance | **2.0** | keeps two walls' bumps apart at a corner |
| Bump band | top **4.0** below the rim | |
| Text letters | **10.0** ideal, **7.0** auto minimum, **4.0** floor | sunk **0.4**; a zone sizes it, a hand-set height is capped by that zone |
| Rim label | **5.0** letters, **7.0** ledge | flush at rim; 45-degree underside |
| Scoop | **50%** of usable wall height | full usable width at front |

Connector tolerance, length and height were chosen from a **printed five-clip fit
plate** — the leftmost clip, read back from that 3MF as `side_clip_tol_0p020`.

## Already tried and rejected

Do not re-derive these.

| Tried | Outcome |
|---|---|
| Four-box corner connector | Removed. Over-constrained four independently printed corners; also produced unprintable slivers along the seams. |
| Shortening the connector to make it reversible | Provably useless — it is a parity clash, not a size problem. |
| Bumps on alternate troughs only | Locked one side of a mixed-size seam, and blocked reversibility. |
| Even (cosine) wave | Replaced with odd sine so boxes can be turned round. |
| Raised (proud) floor labels *as the only option* | Replaced with a sunk inlay by default; **Stand proud** is now a per-text choice. |
| One label per bin, owned by the design | Replaced by `text` interior parts, any number of them. One label meant no answer to "which compartment is this size for", and the label already had bespoke move/rotate/resize code duplicating the feature editor. |
| Reading "flat inside walls" as a horizontal fill depth | Wrong. It is a **height**: a flat-walled band rising from the floor, with the wave unchanged above it. |
| 16 mm "bin" as the unit | Replaced with 8 mm so whole numbers reach 8/16/24/32/40/48. |
| Success dialog after generating | Removed; the status line reports instead. Failures still get a dialog. |
| Connector-fit line in the size readout | Removed. |
| Native `.f3d` export | Impossible outside Fusion. A build script was written and is now stale — it predates the 4 mm wave and the removal of the corner connector. |

## Three claims this project got wrong

Both were stated as done and later found false. Tests now exist for each.

1. **"A box is the same whichever way round you turn it."** False while the wave
   was even. The test behind it checked that a *wall* is symmetric about its own
   midpoint, which is a different property from the whole box being invariant
   under rotation. Measured: a box turned 180 degrees clashed with its neighbour
   by **159 mm³** and overlapped its own footprint by only **54%**. Fixed by
   making the wave odd.
2. **A readout line naming which sides take a connector.** Documented as
   working; the edit had silently failed to apply and the line never existed.
   The line was later removed at the user's request anyway, but a test now
   asserts the readout and preview actually have content.
3. **"One connector part fits every seam, at any half-wave position."** False by
   a factor of two. The wave inverts every half cycle, so the clip a half-wave
   along is the printed one **mirrored** — identical volume, 58% shape overlap,
   and not obtainable by turning a part over. Measured: the real part slid 2 mm
   along a seam jams by **48 mm3**. The tests that looked universal all
   regenerated the clip for the position they were checking, and every fixed
   position they used happened to land on a whole wave. Positions are now whole
   multiples of `WAVE_LENGTH`, and
   `test_the_printed_clip_still_seats_when_slid_to_another_lattice_step` prints
   one part and slides it, which is what the claim was actually about.

## Traps

- **Fingerprints.** `test_organizer_app.py` pins STL hashes for the default box
  and connector. Any geometry change moves them; re-pin deliberately, never by
  reflex.
- **3MF hashes are not reproducible.** `lib3mf` writes a fresh build UUID each
  export, so identical code gives a different `.3mf` hash every run. The STL
  fingerprints are the real regression guard.
- **`mesh_report` demands a single component.** Right for boxes and connectors,
  wrong for labels — a label is legitimately one solid per letter, so it uses
  `label_mesh_report` and `validate_3mf(..., multipart=(...))`.
- **A non-empty `multipart` also means "assembly".** `export_text_body_3mf`
  groups the body and every text into one components object with a single build
  item, so `validate_3mf` then expects `expected_objects + 1` strict objects and
  1 build item, and reports `filaments`. A plain `export_mesh` file is still
  N objects / N build items. Bambu opens the assembly with no multi-part prompt;
  the filament split lives in `Metadata/model_settings.config`, not the mesh.
- **Glyph contours arrive unnested.** Ring-containment depth decides shell from
  hole, or every `O` fills in.
- **Label sizes are cap height, not font size.** A 10 mm font size gives 7.29 mm
  letters in DejaVu Sans; everything converts through the font's measured ratio.
- **Bumps on adjacent walls can collide at a corner.** `LOCK_CORNER_CLEAR` = 2.0
  exists for that; it broke a 20x40 box's boolean before it was added.
- **The preview needs back-face culling, not just a depth sort.** From above, the
  far outside wall's top edge is genuinely nearer the camera than the floor, so
  painting order alone draws it over the interior. Label faces are pinned just in
  front of the floor's depth rather than given their own, or far-side letters
  sort behind the floor and vanish. The 76-degree elevation was calculated: for a
  40 mm bin the floor only clears the near rim past about 88 degrees, so a low
  dramatic angle hides the floor and the label with it.
- **Cartridge cells are anchored at the cartridge corner, not world zero.** An
  even cell count puts legal feature centres half a cell from zero; snapping the
  centre itself creates layouts that look aligned but are not reusable.
- **Text is built by `build_features` but kept out of its returned solids.** A
  recessed inlay has to be *subtracted* from the body, not added to it, so the
  builder runs (its errors surface with every other interior part's) while the
  exporter collects the solids separately through `build_texts`. Pass
  `include_text=True` to get them, as the preview does.
- **Lettering flush with the floor needs a painter *layer*, not just a depth.**
  Text sunk into the floor shares the floor's face exactly, so pinning it to the
  floor's sort depth leaves only the layer to break the tie — and an interior
  part arrives on layer 0, under the floor's own layer 1. Without lifting it the
  lettering is painted over and renders nothing at all. No Python test can see
  this; it was found by reading pixels out of the real canvas.
- **The browser layer converts every builder option to a float.** Text brought
  the first options that are not numbers, so `NON_NUMERIC_OPTIONS` in
  `organizer_inserts.py` declares them and `option_value` does the conversion.
  Add a non-numeric option anywhere and it must be declared there too.
- **A tall feature at the wall can block a connector even when the 2D zones are
  valid.** Builders check the 2 mm edge strip against the connector-arm bottom;
  the default divider stops exactly at that safe height.
- **The `.venv` here is the only Python that works.** Use
  `.venv\Scripts\python.exe`, not the system interpreter.

## Verified behaviour

Measured and regression-tested; run the suite for the current exact count.

**Mating and the grid**
- Boxes one pitch apart: **0.0 mm³** interference, constant 0.25 mm clearance
- Off-grid sizes against a different size: **>10 mm³** interference — rejected
- One connector across 4 box sizes × 4 positions: **100.000%** volume match, so
  it really is one universal part

**Turning things round**
- Connector spun 180 degrees: seats at **<0.001 mm³**, locks at **>0.1 mm³** —
  identical to unspun, on 32x32, 16x48, 24x48 at +4 and 48x48x24 at −6
- Box spun 180 degrees: **100.0%** self-overlap, **0.0 mm³** against an unturned
  neighbour
- Before the fix: connector **48.5 mm³**, box **159.0 mm³**

**Lock**
- Seated: **0.0 mm³**. At 0.5 mm lift: **1.70 mm³**. Rose from 1.41 when bumps
  went to every extremum — shorter bumps, twice as many under a clip

**Flat wall band**
- Cavity cross-section is the straight profile (**844.47 mm²**) throughout the
  band and the wavy one (**892.01 mm²**) immediately above it, on a 32x32x40
  box with a 1 mm band
- The band's height tracks the setting continuously; it is not on/off
- The straight profile is fully contained by the wavy one, so the band cannot
  cut into the wall
- Outer profile area identical to 6 places, so grid and mating are unaffected
- Connector still seats and locks with the band at 0, 0.5 and 1.0

**Text and labels**
- Pocket volume removed == inlay volume; the two intersect by **<0.01 mm³**;
  union restores the plain box exactly. Checked on 48x48, 16x48 and 24x40
- Strict 3MF, **zero warnings**; one assembly object, one build item, the body
  and every piece of lettering as named parts — verified with three floor texts
  and with a rim label alongside floor text. `model_settings.config` opens the
  body on filament 1 and all lettering on filament 2
- A raised text takes nothing out of the body; a recessed one is its exact
  complement
- An auto-placed text moves around holders, reserved scoop/ledge space and other
  auto texts with a 1 mm clearance; the same placement is used by the 2D editor,
  3D preview, mesh pocket and export report
- Neighbours are judged on the lettering's **ink**, not the box it was dragged
  out to, so a short word in a wide box does not push a holder away

**Insert layouts**
- Nine registered builders: cradle, Photo Nest, bore, center post, divider,
  pocket, slot rack, steps and text
- Fused outputs remain one watertight solid; fitted and cartridge inserts clear
  the bin walls and stand on their own 0.6 mm print-flat plate
- Normal moves and resizes snap to 1 mm. Cartridge coordinates and sizes are
  validated on 8 mm cell edges and survive a JSON round trip
- All three production modes were exported as strict, zero-warning 3MF files;
  a lettered output is a one-build-item assembly of the body and every piece of
  lettering as named parts, and two texts reading the same thing stay distinct

**Usable inside**
- The exact reported rectangle fits; **+0.3 mm does not**

## Where it stands

Working and verified: box, connector, lock, insert registry and primitives,
fused/removable/cartridge exports, multi-label text parts, flat-inside fill,
interactive 3D preview, 2D drag editor, saved layouts, CLI, UI and sample plate.

Physically printed so far: **test pieces only** — the five-clip tolerance plate
that set the connector fit. That plate predates the 4 mm wave, so **nothing in
the current design is confirmed in plastic yet.**

Remaining physical next steps:

- Print `WAVY_SAMPLE_SET.3mf` and check the lock feel, the label colour change,
  and that a connector really does drop on either way round.
- Nothing enforces that all boxes in a drawer share a `flat_inside` value; a
  connector made for one fill depth is only guaranteed against boxes with the
  same fill.
