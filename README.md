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

Double-click `Launch_Organizer_UI.bat`. On its first run it creates a private
`.venv` beside the app, installs the pinned geometry packages, starts the local
Wavefinity service, and opens the browser interface. Later launches reuse that
environment. The service listens only on `127.0.0.1`; it is not hosted on the
internet and the browser never replaces the Python geometry engine.

Manual setup instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install lib3mf==2.5.0 lxml==6.1.2 manifold3d==3.5.2 mapbox-earcut==2.0.0 matplotlib==3.11.1 networkx==3.6.1 numpy==2.5.2 shapely==2.1.2 trimesh==5.0.0
.venv\Scripts\python.exe wavefinity_web.py
```

Those nine pins are the whole dependency list. `matplotlib` is not optional — it
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
support editor. **Customize your bin** contains the scoop and advanced physical
settings. **Label your bin** contains the label position and part filename.

The 3D preview is real camera-independent geometry returned by Python and drawn
locally by the browser. Drag to rotate, use the wheel to zoom, and double-click
to reset. A single pixels-per-millimetre scale is chosen from the available
width and height, so enlarging the browser makes the model larger without
stretching it. The 2D tab uses the same rule and supports click-to-select,
drag-to-move and blue-corner resize. It draws the bin's true wavy interior,
not the flat placement rectangle - that rectangle still shows as a dashed
reference line, since every non-full-span support has to stay inside it, but
the wavy outline is what answers "does this actually reach the wall."

Selecting an interior support immediately builds its actual mesh. Parameter
changes rebuild that draft after a short typing pause, before it is added to the
layout. **Add support** finds open floor space; selecting a placed support loads
it back into the same editor for exact changes. Invalid dimensions, overlaps,
reserved scoop/label space, and labels that cannot fit are reported beside the
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

The browser editor is a three-step flow: **1. pick a shape** from the support
palette and read its one-line description; **2. set parameters**; **3. add
support**. Placed supports can be selected in the list or on the 2D layout,
then moved, resized, or edited with exact numeric fields. Normal layouts snap
to **1 mm**. Overlaps and out-of-bounds features are refused at export.

A **divider** also gets a **Fit to bin** button above its fields, since it is
the one kind where a size has an unambiguous "reach the bin" meaning - every
other kind's quantity means repeated elements inside one footprint, not
sections of the bin, so they keep manual sizing and the ordinary per-kind
**Auto** button next to Quantity. Fit to bin grows the zone to the usable
floor edge, a placed neighbour, or a reserved scoop/label zone, only along
the divider's own run axis - its wall thickness is a separate field.

### Insert types

The browser UI offers two: **Fused**, where holders print as one solid part
with the bin — strongest, uses the most floor area, but the supports are
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
support did not land on an 8 mm cell.

Tall holders may use the middle of the bin, but anything entering the 2 mm strip
beside a wall is capped below the connector arms. The editor's default divider
height follows that limit; an explicit unsafe height is refused at generation.

**Fused** is the default and gives the most usable floor.

Bottom labels are placed after holders. They stay centred when possible, then
move, rotate, and finally shrink (never below 7 mm) to dodge occupied zones. In
removable modes a bottom label is inlaid into the insert plate rather than
hidden under it. A top label instead uses fixed 5 mm letters inlaid flush into a
7 mm-deep rear ledge at the rim. The ledge underside rises at 45 degrees and
prints without supports.

The optional **curved scoop** spans the usable width at the front of the bin and
rises halfway up the usable wall height, so a part sweeps forward and lifts out
over the low front lip — the opposite wall from the top-label ledge. In
removable modes it is part of the insert; in fused mode it is part of the box.
A floor label is moved clear of the scoop strip, and the 2D editor shades the
space reserved by a scoop or top-label ledge and refuses overlapping supports.

What a scoop reserves is not its whole run. The curve meets the floor
tangentially, so its innermost millimetres are only microns proud of it — on a
40 mm bin the ramp stands 0.03 mm off the floor one millimetre in from where it
lands. Reserving that lip called a divider across the middle of the bin
"invalid" when it was in fact sitting flat, so the support keep-out stops where
the curve has risen `SCOOP_FLOOR_TOLERANCE` (0.4 mm, about one layer) instead.
`scoop_floor_zone` is still the true footprint, used where the real extent
matters; `scoop_keep_out` is the smaller strip a support has to avoid.

Everything else — wall thickness, the flat wall band, connector tolerance,
height, length, position and wall direction — sits behind an **Advanced
settings** checkbox. The sample plate is a fixed set of sizes, so it has no
settings at all.

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
| `GET /api/catalog` | Registered supports, modes and initial values. |
| `POST /api/preview` | Validate a design and return camera-independent geometry. |
| `POST /api/design/validate` | Validate and normalize a saved design. |
| `POST /api/feature/default` | Create an engine-derived support draft. |
| `POST /api/feature/autosize` | "Fit to bin": grow a divider draft's zone to the usable floor. |
| `POST /api/feature/draft` | Build actual mesh faces for live parameter preview. |
| `POST /api/feature/apply` | Snap, validate, add or update a support. |
| `POST /api/feature/delete` | Remove a support. |
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
cradle/nest/bore supports at once) serializes a large triangle payload to
the browser; camera motion stays client-side and fast regardless, but the
initial load is heavier. **Save design** relies on the browser's own
download prompt, which some browser-automation tools cannot observe as an
event — a real browser session shows it normally.

---

## The design

### Holder primitives

Every holder owns a rectangular floor zone. Item-based holders (`cradle`,
`nest`, `bore`) describe the stored tool as one or more `length x diameter`
segments internally, so `50x6, 30x18` is a hex driver shaft and handle without
hard-coding a hex-driver rack. The editor collects this as plain **Length /
Thickness** fields, with optional **Handle length / Handle thickness** for a
two-part tool — there are no fixed tool presets, since every bin is cut for one
specific tool. `Count = auto` fills the zone; a number requests exactly that
many.

| Holder | Purpose | Optional `key=value` settings |
|---|---|---|
| `cradle` | Scalloped ribs for items lying along X or Y; every segment gets its own radius while all seats share one axis height | `rib_thickness`, `spacing`, `floor_gap` |
| `nest` | Snug, support-free top-down recess following every measured item segment | `depth`, `height`, `wall` |
| `bore` | Round, hex or square holes for items standing up | `depth`, `height`, `wall`, `columns`, `rows` |
| `post` | Lightly tapered pegs for rolls, spools, sockets and ring-shaped parts | `diameter`, `height`, `spacing`, `taper` |
| `divider` | One or more straight or leaning subdividing walls along X or Y | `height`, `thickness`, `angle` |
| `pocket` | Raised rectangular tray with a recessed centre | `height`, `depth`, `wall` |

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
element: `count` dividers split the zone's cross axis into `count + 1` equal
gaps - fence-post spacing, so `count = 1` (the default) lands exactly where a
single centred divider always has. Height, angle and thickness apply to
every wall the count places, not just one.

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

The wave being *odd* is load-bearing, not cosmetic. It is what lets a box be
**turned round**: spun 180 degrees, a box's +X wall lands where its −X wall was,
and an odd wave means the two carry the same shape, so the turned box still
nests with its neighbours.

### The 8 mm size grid

**Box X and Y must be whole multiples of 8 mm, from 8 mm up.** X and Y are
independent, so 16x16, 16x48, 40x56 and so on are all fine — nothing has to
scale proportionally.

**One unit is 8 mm** — the grid step itself — so every legal size is a whole
number of units and no decimals are needed: 1, 2, 3, 4, 5, 6 = 8, 16, 24, 32,
40, 48 mm. The UI takes X and Y in units.

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

The UI shows this live as you change the units:

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
nested with a constant 0.25 mm clearance and never touch.

Where two wavy walls meet, the corner is a short chamfer eased to a **0.6 mm
fillet**. The rounding is a morphological opening, which only affects convex
corners sharper than that radius — the wave's own crests are far blunter, so they
come through untouched.

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

**The connector is locked**: 0.02 mm tolerance, 12 mm long, 9.6 mm tall, chosen
from a printed five-clip fit plate. Those three numbers are no longer tuning
knobs, and the UI hides them behind **Advanced settings**.

**It is one universal part, and it goes on either way round.** Because the wave
and the lock lattice are global, a connector generated for any box seats on any
seam. Its centre has to land on a half-wave, so `--position` must be a whole
multiple of 2 mm; anything else is rejected.

Reversibility is why the bumps sit on **every** extremum rather than every other
one. Two things have to line up when you spin a connector: the wall it hugs must
look the same upside down about the connector's centre, which needs the centre on
an **even** millimetre, and the notches must mirror about that centre, which with
bumps every 2 mm they do. With bumps on alternate extrema the two requirements
landed on odd and even millimetres and could never both hold — **no length or
position could fix that**, which is why the wave shape had to change instead.

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

### Bottom and top labels

Give a box a label and the text is **sunk into its floor**: the box gets a pocket
and the label is the solid that fills it flush, exported as a **second object in
the same 3MF**. Open it in Bambu Studio, answer yes to "load as a single object
with multiple parts", and the label can be given its own filament — that is the
whole reason it stays a separate object.

- Letters are **10 mm** tall if they fit, shrinking no further than **7 mm**
- Text runs **across** the box when it can; only if 7 mm still will not fit does
  it **turn** to run up the box, always the same way round so a row of printed
  boxes reads consistently
- Sunk **0.4 mm** into the 0.8 mm floor, leaving 0.4 mm beneath, and reads
  correctly looking into the open box, which is the way the box prints
- The pocket and the inlay are exact complements: put them back together and you
  get the plain box, to the last cubic micron
- If it will not fit either way at 7 mm you get an error naming what it needs
- With holders present, the label automatically moves to unused floor; if none
  remains, export gives a clear error instead of burying text in a holder
- **Blank label changes nothing**: one object, and the plain filename

Choose **Top** to put the label at the rear rim instead. Top labels use fixed
**5 mm** letter height on a **7 mm** front-to-back shelf. The text remains a
0.4 mm-deep flush inlay and a second selectable 3MF object. The shelf's underside
rises by 7 mm over its 7 mm run, an exact 45-degree self-supporting slope. A top
label that cannot fit at its fixed size is rejected with a clear message rather
than silently shrunk.

The label is added to the filename: `Box 48 x 48 x 40 BOLTS.3mf`. Characters a
filesystem would object to are stripped.

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

Generated box files are named for their size, plus the label if there is one:
`Box 16 x 48 x 40.3mf` or `Box 16 x 48 x 40 BOLTS.3mf`. The connector is one
part, so it is just `Connector.3mf`.

The `organizer` command reads either a complete saved UI design or a bare layout
object. A complete design supplies its box, label position, scoop choice and
part name; explicit CLI values override any of them. `--mode` overrides the saved
fused/separate/cartridge mode.
Fused export writes one box file. Removable modes write a plain box and a
separate `Insert ...3mf` or `Cartridge ...3mf`. Labelled parts are strict
two-object 3MF packages so the inlay can use another filament. Both `.3mf` and
`.stl` continue to work for legacy individual-part commands.

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
| `organizer_engine.py` | Wavy boxes, connectors, labels, mesh validation and 3MF/STL export. | No. |
| `organizer_inserts.py` | Item/segment model, zones, 1 mm and cartridge layouts, JSON persistence, holder registry, six builders, and fused/removable assembly. | No. |
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
| `Launch_Organizer_UI.bat` | bootstraps `.venv`, installs the pinned packages, starts `wavefinity_web.py`, opens the browser |
| `generated/WAVY_SAMPLE_SET.3mf` | regenerable local sample print plate; intentionally gitignored |

## Working on this

This project is developed locally, mostly by prompting an LLM. GitHub is a
**backup and a record of what changed** — it is not a review gate.

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

**Run the tests before committing.** They take about two minutes, and they are
the only thing standing between a plausible-looking geometry edit and parts that
no longer fit. If a fingerprint test fails, that is the suite telling you the
geometry moved — decide whether you meant it, then re-pin deliberately.

**Write commit messages that say why.** The history is the record. A message
that explains the reasoning is worth more here than a tidy branch structure.

**Relaunching replaces the running server, but only one it started.**
`wavefinity_web.py` records its own process id in `wavefinity.pid` and, if a
relaunch finds the port already taken, kills whatever process that file names
and rebinds - a browser tab has no way to tell it is talking to code from
before your last edit, so silently reattaching to an old process would serve
stale code with no visible sign anything was wrong. A server the launcher did
not itself start (or one from before this existed) is left alone and reported
as already running - close that window by hand and relaunch.

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
| Wall / floor | **0.8** | |
| Flat wall band | **0–1.0**, default 0 | height above the floor, not a fill depth |
| Corner fillet | **0.6** | walls stop `CORNER_INSET` = 1.0 short of the nominal corner |
| **Connector tolerance** | **0.02** | **locked** by a physical print |
| **Connector length** | **12.0** | **locked** |
| **Connector height** | **9.6** | **locked**; cap 1.2, arms 1.0 thick |
| Lock bump | **0.35** proud, 1.0 tall, **1.2** long | on every wave extremum, so every **2.0** |
| Bump corner clearance | **2.0** | keeps two walls' bumps apart at a corner |
| Bump band | top **4.0** below the rim | |
| Label letters | **10.0** ideal, **7.0** minimum | sunk **0.4** into the floor |
| Top label | **5.0** letters, **7.0** ledge | flush at rim; 45-degree underside |
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
| Raised (proud) floor labels | Replaced with a sunk inlay. |
| Reading "flat inside walls" as a horizontal fill depth | Wrong. It is a **height**: a flat-walled band rising from the floor, with the wave unchanged above it. |
| 16 mm "bin" as the unit | Replaced with 8 mm so whole numbers reach 8/16/24/32/40/48. |
| Success dialog after generating | Removed; the status line reports instead. Failures still get a dialog. |
| Connector-fit line in the size readout | Removed. |
| Native `.f3d` export | Impossible outside Fusion. A build script was written and is now stale — it predates the 4 mm wave and the removal of the corner connector. |

## Two claims this project got wrong

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
- **Labels avoid complete feature zones, not just generated surfaces.** That is
  conservative by design: it preserves readable clearance and makes preview and
  export agree without running expensive booleans on every drag.
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

**Labels**
- Pocket volume removed == inlay volume; the two intersect by **<0.01 mm³**;
  union restores the plain box exactly. Checked on 48x48, 16x48 and 24x40
- Strict 3MF, **zero warnings**, two named objects
- Labels move around insert zones with a 1 mm clearance; the same placement is
  used by the 2D editor, 3D preview, mesh pocket and export report

**Insert layouts**
- Six registered builders: cradle, contour nest, bore, center post, divider
  and pocket
- Fused outputs remain one watertight solid; fitted and cartridge inserts clear
  the bin walls and stand on their own 0.6 mm print-flat plate
- Normal moves and resizes snap to 1 mm. Cartridge coordinates and sizes are
  validated on 8 mm cell edges and survive a JSON round trip
- All three production modes were exported as strict, zero-warning 3MF files;
  labelled outputs contain exactly two named objects

**Usable inside**
- The exact reported rectangle fits; **+0.3 mm does not**

## Where it stands

Working and verified: box, connector, lock, insert registry and primitives,
fused/removable/cartridge exports, insert-aware labels, flat-inside fill,
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
