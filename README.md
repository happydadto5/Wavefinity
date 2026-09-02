# Wavefinity — wavy drawer organizer generator

Parametric Python generator for a 3D-printable modular drawer organizer with
**wavy walls that interlock**. The desktop UI, command-line interface, fit
sampler and tests all use `organizer_engine.py` as their only geometry source.

There are **two printed parts**: the box, and one **connector** — a small staple
that joins two boxes across their shared seam. There is no corner connector.

Everything below is millimetres. This is the whole documentation for the
project: design, rationale, measured evidence, and the traps.

---

## Quick start

Double-click `Launch_Organizer_UI.bat`. On its first run it creates a private
`.venv` beside the app, installs the pinned geometry packages, and opens the UI.
Later launches reuse that environment.

Manual setup instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install lib3mf==2.5.0 lxml==6.1.2 manifold3d==3.5.2 mapbox-earcut==2.0.0 matplotlib==3.11.1 networkx==3.6.1 numpy==2.5.2 shapely==2.1.2 trimesh==5.0.0
.venv\Scripts\python.exe organizer_app.py ui
```

Those nine pins are the whole dependency list. `matplotlib` is not optional — it
supplies the font outlines for floor labels. Run the tests with:

```powershell
.venv\Scripts\python.exe -m unittest
```

They take about two minutes; boolean operations dominate.

### Using the UI

The main form is deliberately short: **box X and Y in units**, box height in mm,
and a **floor label**. Beside them a **live 3D preview** draws the box and its
label, with the dimensions written along the bottom and side as
`32mm (29 inside)` — outside size first, usable interior in brackets — and the
height in the corner. It turns the label when the box is too narrow and says so
if the label will not fit.

Everything else — wall thickness, flat-inside fill, connector tolerance, height,
length, position, wall direction and the sample-plate contents — sits behind an
**Advanced settings** checkbox.

Generating writes the file and reports on the status line; no dialog to dismiss.
A failure still raises one, because it needs acting on.

---

## The design

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

### Flat inside walls (optional)

The wave runs on both faces of a wall, so by default the inside is wavy too. An
advanced setting, **flat inside, 0 to 1 mm**, fills that in:

| Setting | Inside wall |
|---:|---|
| 0.0 | follows the wave, wandering the full 0.8 mm (default) |
| 0.4 | half straightened |
| **0.8** | **dead flat** — the fill exactly cancels the wave |
| 1.0 | flat, plus 0.2 mm of extra wall |

Only the inside changes; the outside profile, the grid and the mating are
untouched. Three things follow the fill so nothing stops fitting: the cavity
itself; the **lock bumps**, which stand proud of the *new* face, so a bump on a
filled-in crest is not buried; and the **connector arm**, which hugs that face and
would otherwise clash with it.

Usable interior does **not** improve, because a straight-sided object was always
limited by the innermost point of the wave. The fill buys a clean wall, not
capacity.

### Floor label

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
- **Blank label changes nothing**: one object, and the plain filename

The label is added to the filename: `Box 48 x 48 x 40 BOLTS.3mf`. Characters a
filesystem would object to are stripped.

---

## Command line

```powershell
python organizer_app.py box --x 40 --y 32 --z 55 --output box_40x32x55.3mf
python organizer_app.py box --x 48 --y 48 --z 40 --label BOLTS --output "Box 48 x 48 x 40 BOLTS.3mf"
python organizer_app.py box --x 32 --y 32 --z 40 --flat-inside 0.8 --output flat.3mf
python organizer_app.py side --box-x 40 --box-y 32 --box-z 55 --along y --output side_y.3mf
python organizer_app.py kit --x 40 --y 32 --z 55 --output-dir generated_40x32
python organizer_app.py sampler --boxes 2x6,4x6,6x6 --output WAVY_SAMPLE_SET.3mf
```

X and Y must be multiples of 8 mm (minimum 8); Z and wall are free. `--boxes`
takes units (`2x6`), or millimetres with an explicit suffix (`16x48mm`).

Generated box files are named for their size, plus the label if there is one:
`Box 16 x 48 x 40.3mf` or `Box 16 x 48 x 40 BOLTS.3mf`. The connector is one
part, so it is just `Connector.3mf`.

Both `.3mf` and `.stl` work for individual parts. Combined files are strict 3MF
packages.

## Supplied print file

`WAVY_SAMPLE_SET.3mf` — eight separately selectable objects:

- **2 x 6 (16 x 48 mm)**, **4 x 6 (32 x 48 mm)** and **6 x 6 (48 x 48 mm)** boxes
- **Five identical connectors** at the locked 0.02 mm tolerance

Print the boxes open side up and the connectors cap side down; no supports either
way. The three sizes are deliberately different so you can check that mixed sizes
really do interlock and take a clip at every seam.

## Code layout

| File | What |
|---|---|
| `organizer_engine.py` | all geometry, validation, fit simulation, export. Single source of truth. |
| `organizer_app.py` | CLI and Tkinter UI, including the 3D preview |
| `test_organizer_app.py` | 80 tests, written against behaviour rather than implementation |
| `Launch_Organizer_UI.bat` | bootstraps `.venv` and opens the UI |
| `WAVY_SAMPLE_SET.3mf` | sample print plate |
| `VISUAL_QA_SAMPLER.png` | render of the actual meshes |

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
| Corner fillet | **0.6** | walls stop `CORNER_INSET` = 1.0 short of the nominal corner |
| **Connector tolerance** | **0.02** | **locked** by a physical print |
| **Connector length** | **12.0** | **locked** |
| **Connector height** | **9.6** | **locked**; cap 1.2, arms 1.0 thick |
| Lock bump | **0.35** proud, 1.0 tall, **1.2** long | on every wave extremum, so every **2.0** |
| Bump corner clearance | **2.0** | keeps two walls' bumps apart at a corner |
| Bump band | top **4.0** below the rim | |
| Label letters | **10.0** ideal, **7.0** minimum | sunk **0.4** into the floor |
| Flat inside fill | **0–1.0**, default 0 | 0.8 = dead flat |

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
- **The `.venv` here is the only Python that works.** Use
  `.venv\Scripts\python.exe`, not the system interpreter.

## Verified behaviour

Measured, not asserted. All figures from the current geometry; 80/80 tests pass.

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

**Flat inside**
- +X interior wall wanders **0.76 / 0.58 / 0.38 / 0.000 mm** at fills of
  0 / 0.2 / 0.4 / 0.8
- Outer profile area identical to 6 places, so grid and mating are unaffected
- Connector still seats and locks at fills of 0, 0.4, 0.8 and 1.0

**Labels**
- Pocket volume removed == inlay volume; the two intersect by **<0.01 mm³**;
  union restores the plain box exactly. Checked on 48x48, 16x48 and 24x40
- Strict 3MF, **zero warnings**, two named objects

**Usable inside**
- The exact reported rectangle fits; **+0.3 mm does not**

## Where it stands

Working and verified: box, connector, lock, labels, flat-inside fill, 3D
preview, CLI, UI, sample plate.

Physically printed so far: **test pieces only** — the five-clip tolerance plate
that set the connector fit. That plate predates the 4 mm wave, so **nothing in
the current design is confirmed in plastic yet.**

Next steps, none started:

- Print `WAVY_SAMPLE_SET.3mf` and check the lock feel, the label colour change,
  and that a connector really does drop on either way round.
- Nothing enforces that all boxes in a drawer share a `flat_inside` value; a
  connector made for one fill depth is only guaranteed against boxes with the
  same fill.
