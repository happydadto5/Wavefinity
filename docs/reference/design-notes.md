# Wavefinity design decisions and historical notes

Contains settled geometry decisions, rejected approaches, traps and historical progress. Read relevant sections when a change intersects them; do not treat dated status snapshots as the current application state.

# Design notes

Everything from here down is for whoever changes the geometry next. Several of
these numbers look arbitrary and are not.

## The settled numbers

| | Value | Notes |
|---|---:|---|
| Wave cycle | **3.5** | two tangent circular arcs |
| Wave amplitude | **0.4** | 0.8 peak to peak |
| Wave shape | **odd circular arcs**, signed by wall axis | global phase; quarter-turn compatible |
| Mating gap | **0.25** | between two neighbouring walls |
| Size grid | **7.0** | box X and Y must be whole multiples |
| Minimum box | **7.0** | one grid step |
| Maximum requested X/Y | **350.0** | the 7 mm grid makes 350 mm the largest valid size |
| One "unit" | **7.0** | so 1, 2, 3 units = 7, 14, 21 mm |
| Smallest box that clips on both sides | **16.0** | derived, not hard-coded |
| Wall | **0.8** | independent of the floor |
| Base thickness | **0.8** default, **0.4** minimum | shown under Advanced in Build your bin |
| Flat wall band | **0–1.0**, default 0 | height above the floor, not a fill depth |
| Corner fillet | **0.6** | walls stop `CORNER_INSET` = 1.0 short of the nominal corner |
| **Connector tolerance** | **0.02** | **locked** by a physical print |
| **Connector length** | **12.0** | **locked** |
| **Connector height** | **9.6** | **locked**; cap 1.2, arms 1.0 thick |
| Connector position step | **3.5** | one whole wave; half a wave wants a mirrored part |
| Base Trim field range | **8–1200** | whole 7 mm units on each axis |
| Base Trim unit | **7.0** | enclosed field step |
| Base Trim size presets | **Small 6.5, Medium 7.5 (default), Large 10, XL 15, XXL 20** | square width = height |
| Base Trim width / height range / step | **4–20 / 0.5** | millimetres; presets are the normal path, legacy values still load |
| Base Trim default bed / effective area | **256 × 256 / 236 × 236** | 10 mm is reserved at each edge |
| Base Trim joint length / clearance | **0.55 × min(width, height) / 0.20** | one scaled drop-in dovetail; only used when the ring must split |
| Base Trim split-joint structural skin | **1.0 mm minimum** | between cleared joint and each physical face |
| Base Trim outer taper | **1.0 per side** | outside only |
| Mated wall clearance | slope-derived | 0.25 across the seam; normal clearance uses the arc maximum slope |
| Lock bump | **0.35** proud, 1.0 tall, **1.2** long | on every wave extremum, so every **1.75** |
| Bump corner clearance | **2.0** | keeps two walls' bumps apart at a corner |
| Bump band | top **4.0** below the rim | |
| Text letters | **15.0** usual base height, **5.0** readable minimum | centered; Letter height sets size; Inlay depth / Raised height **0.2–0.8** subject to backing |
| At-rim Text | **5.0** target letters, **7.0** ledge | auto-shrinks; 45-degree underside; Raised lowers the ledge by its height |
| Scoop | **60%** of usable wall height | full usable width at front |

Corner construction (Story 2272): the shared wall-outline builder caps each
wall run at the neighbouring faces' inward wave envelope. This keeps reduced
cavity corner chords from crossing a wall when arc-wave wall depth exceeds
the outside corner inset. Outside bin walls keep their original runs and
global wave; phased spacer outlines use the same rule. Preview rings retain
matching point counts even when cavity runs are shorter.

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
| 16 mm "bin" as the unit | Replaced with 8 mm, then re-based to 7 mm so whole numbers reach 7/14/21/28/35/42. |
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

- **Top 1 mm accent (Story 3056):** take the horizontal band from the finished
  body at its shell's actual top, including a stacking receiving rim. Partition
  after fused features, mounts, lettering pockets and final side-opening cuts;
  splitting in the early builder would be lost through those later booleans.
  Preserve every closed connected component of both partitions as a registered
  part, with slot 2 for the band and slot 1 for the rest. A feature projecting
  above the shell does not raise the band datum. This changes material assignment
  only, preserving the rim and lid interface profile. Lids are never split.
  Single-mesh STL retains the original full mesh.

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
- **Option types come from feature metadata.** `OptionDefinition.value_type`
  drives browser/API coercion for numbers, whole numbers, booleans, enums,
  strings and nested JSON. Do not maintain a second key-based type list.
- **A tall feature at the wall can block a connector even when the 2D zones are
  valid.** Builders check the 2 mm edge strip against the connector-arm bottom;
  the default divider stops exactly at that safe height.
- **The `.venv` here is the only Python that works.** Use
  `.venv\Scripts\python.exe`, not the system interpreter.

## Historical geometry evidence

The measurements below describe earlier sine-wave geometry. They are retained
as history, not acceptance evidence for the Story 2260 arc walls and connectors.

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
  and every piece of lettering as named parts — verified with one base Text
  and independent rim sides. `model_settings.config` opens the
  body on filament 1 and all lettering on filament 2
- A raised text takes nothing out of the body; a recessed one is its exact
  complement
- Base Text remains centered; fused neighbours are judged against the actual
  buffered glyph outline, not the empty corners of its selection bounds.
  Rim Text is outside floor occupancy in every layout mode.

**Insert layouts**
- Nine registered builders: cradle, Snug Holder, bore, center post, divider,
  pocket, slot rack, steps and text
- Fused outputs remain one watertight solid; fitted and cartridge inserts clear
  the bin walls and stand on their own 0.6 mm print-flat plate
- Normal moves and resizes snap to 1 mm. Cartridge coordinates and sizes are
  validated on 7 mm cell edges and survive a JSON round trip
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

### Hinged lid preview repair (2026-11-07)

Ordinary hinged bins must use the actual `make_box()` mesh in preview. The
simplified wall-ring preview omits the bin knuckles, pin bore and swing cuts.
Both preview and export share the same piano hinge geometry: alternating
bin/lid knuckles, 2.3 mm single-end-access bore for 1.75 mm filament (2 mm end stop), 110 degree stop,
inside the wavy footprint and below the lid top. Bin-side support bevels are
45 degrees. No tests were authorized for this repair.

### Keep the launch checkout current (2026-11-07)

`C:\Projects\Wavefinity` must stay on `main`. Do branch-based audits or other
work in a separate checkout/worktree; never leave the normal launch folder on
an old branch. The normal BAT updates this folder from GitHub before starting;
it stops with a message if it cannot update safely. Preserve old audit work on
its branch.

### Export progress, the geometry lock and the switch cover (2026-11-11)

**Profile** (this PC, in-process, ms; `build_timings_ms` now comes back from
`/api/generate` as well as `/api/preview`). Height 40 mm for every case.
"Editor wait" is an editor call that takes `GEOMETRY_LOCK`
(`/api/design/inventory-preview`) made 1 s into a running Export.

| Bin | Export before | Export after | Shell before → after | Mesh checks | Editor wait before → after | Preview cold / during Export, "wait" |
|---|---|---|---|---|---|---|
| 98×98 | 6,837 | 4,094 | 2,408 → 807 | 2,313 → 1,710 | 6,138 → 635 | 452 / 40, wait 0 |
| 203×147 | 14,683 | 8,244 | 7,234 → 1,771 | 3,943 → 3,487 | 13,884 → 2,482 | 987 / 45, wait 0 |
| 350×350 | 46,155 | 18,434 | 29,708 → 5,026 | 8,732 → 7,041 | 39,435 → 7,829 | 3,669 / 74, wait 0 |
| 350×350 + lid | 72,702 | 55,331 | 30,716 → 9,743 | 11,267 → 11,192 | 77,887 → 13,986 | 17,222 / 16,048, wait 0 |

Findings:

- Previews never waited on `GEOMETRY_LOCK` (Story 2731 already took them
  off it): preview "wait" was 0 in every case, before and after. What waited
  the whole Export were editor calls still on the lock (feature fit/apply,
  expand layout, inventory preview, cabinet preview meshes).
- **Lock narrowed:** an ordinary-bin Export holds `GEOMETRY_LOCK` only for its
  build stages (checks, shell, features, extras, lid). Writing/validating the
  built meshes and the staged promote run with it released. A new
  `OUTPUT_LOCK` keeps two Exports' file work (serial reservation, staging,
  promote, inventory logging) from interleaving, exactly as before. Order is
  `OUTPUT_LOCK` before `GEOMETRY_LOCK`; a caller already holding
  `GEOMETRY_LOCK` keeps it throughout. An editor call during the file-writing
  stage now waits 0 ms (was the rest of the Export). The per-request
  supersede discipline was not needed, because previews were not waiting.
- **Hotspot fixed (one):** the wall lock bumps re-scanned every edge of the
  whole cavity outline for every sample of every bump (`_wall_face_values`),
  so shell time grew with perimeter squared. Each bump now keeps only the
  edges overlapping its own span, and the outline's vertex array is read once.
  Same edges, same arithmetic: lock paths and every benchmark 3MF are
  bit-identical to before.
- **Noted, not fixed:** each finished mesh is validated twice
  (`export_mesh` calls `mesh_report`, then the result calls it again), and
  its component count uses networkx (scipy is not installed) - about a third
  of a plain bin's Export. Lid bins spend most of their time in lid
  booleans, and a lid bin's preview rebuilds the lid every time (14-22 s).

**Progress.** `/api/operation-status` answers a running operation with
`elapsed_s` and `progress` (`stage`, `stage_text`, `estimate_s` low/high).
Export and single-bin Print poll it every 2 s from the click
(`apiSideEffect(..., { onProgress })`); the status line counts seconds and
shows a plain range, revised at stage boundaries and learned per machine from
finished Exports. No percentage bar. The parts dialog opens docked in a corner
and not modal. During an Export the Space tree stays live (it scrolls and
highlights); opening another row or a row action is refused in place
("Exporting this bin — other rows open once its files are saved.") because
switching bins mid-Export would leave its files unrecorded. The header and
the bin form stay locked, as before, so the file set cannot change under it. A second Export click for the
same bin joins the running one and says so in place. The preview notice
counts up after 2 s and shows a range learned from this session's own slow
rebuilds; the old preview stays underneath. Inventory batch Save/Print does
not show this progress yet.

**Layout switch.** The `#ws-switching` cover takes every dragover/drop while
it shows and refuses a drop in place with "The layout is still switching —
drop again once it appears."; nothing is held or queued, the bin is
unchanged. Leaving a bin whose preview is still building for the same
geometry waits for that build instead of starting it again. Opening a Space
asks `/api/space/warm` (the server skips anything already warm).

**Division labels that cannot fit (2026-11-12).** Lettering never goes below
2.5 mm, so a division label wider than its compartment used to be cut into the
bin wall, leaving a sealed hole and a bin that failed the one-solid check ("A
part of the bin could not be made"). It is now cut short instead
(`_fit_label_text` in `organizer_inserts/_divider/_shelf.py`): the longest start
of the text that sits inside the compartment's margins is built, and the bin
exports. A label that fits the compartment, even crowding the margin, is left
whole. The editor shows a red "Text doesn't fit" over each cut label (its tooltip
says what will be made); it steps aside while the field has focus. The server
measures this through `POST /api/design/division-label-fit` (read-only: the
divider's feature in, `labels: [{index, kept}]` out). Lid division labels are
not covered. Separately, `make_fused_box` drops zero-volume boolean slivers
(under 2 mm) that a divider/wavy-wall join could leave as extra "pieces".

### Browser-only geometry feasibility (Story 2979, 2026-11-12)

An opt-in, isolated experiment on the existing host loaded tools into browser
memory without installation. Chrome and Edge
reproduce the canonical wall/cavity profiles and 0.25 mm seam, including with
network blocked after load. The original PoC lacked a float64 boolean interface, but the later custom
MeshGL64 WebAssembly bridge generated valid downloadable bins with real
Wavefinity geometry, and Windows Chrome/Edge were confirmed by the owner.
The experiment and its test harness have since been removed from the
repository; this section is the retained record. Production still uses the
legacy Python server until the complete browser-only migration is delivered.

### Gridfinity container floors (Story 2974, model and geometry)

Storage Boxes and Storage Drawers use the shared 42/21 mm socket field when
their Gridfinity setting has a built-in floor. Each pitch keeps its own seat
and relief. The minimum base build is 5.8 mm (5 mm pocket plus 0.8 mm skin),
or 8.3 mm above Storage Box underside stacking recesses; insufficient bases
are refused rather than silently changed. Small 1x1 Storage Boxes use Lid Only;
secure-lid hardware retains its existing minimum field.

With `built_in_grid="none"`, the floor is flat. The Space still records its
pitch; `floor_grid=null` identifies the absence of a built-in floor. Nominal
layout dimensions (`nominal_grid_mm`) stay exact-grid; the built cavity
(`physical_cavity_mm`) adds **0.35 mm per side, PROVISIONAL until Stage 1 fit
prints settle it**, from `EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM` alone.
`seated_lift_mm` is an optional measured foot-bottom lift above the container
floor, never the plate's thickness. Missing measurements are `unverified`;
recorded zero is a measurement. Height fit remains unverified for the later
layout checks (Story 2973). Container UI and exports are later work.

Gridfinity Plain Drawers and Storage Boxes with Floor None can record and edit
this measurement in Space setup. Layout heights include the recorded lift.

### Gridfinity plate lids (Story 2971)

The Gridfinity 42 mm and independent 21 mm paths build a separate loose lid:
a flush plate and shallow locating skirt, optionally carrying the pitch's
receiving socket in a perimeter ridge. The body shortens by the plate plus
ridge rise, so the closed bin retains its nominal whole-7-mm height. Interior
parts retain the regular lid's skirt clearance and 0.5 mm margin. A lid and an
open stacking rim are alternatives on one bin. Only the same footprint and
pitch stack on a lid; lid-on-lid uses the standard rim seat descent. Label
and handle variants remain Wavefinity-only. The two-unit lid minimum
does not replace the existing body clearance check: the remaining body must
still clear its effective floor by 5 mm. Physical compatibility remains
**not yet printed**, pending S1-13.

### Gridfinity hinged lid: unsupported on both pitches (Story 3009)

The ordinary filament-pin hinged lid (`organizer_features/lid_hinge.py`) was
assessed against one cell's external allowance: 41.5 mm on the 42 pitch and the
20.5 mm body on the 21 pitch (`gridfinity-stage1-spec.md`), each leaving 0.25 mm
per side before the next bin. `assess_gridfinity_hinge` takes the open swing of
the lid plate from closed to the 110 degree stop about the back-top axis, at or
below the lid-top plane, and compares how far behind the back plane it reaches
with that gap. It reaches about 2.4 mm on both pitches, so both are recorded
**unsupported** and the option is refused in plain language: absent from the
Gridfinity Lid selector, with the reason beside it, and invalid at
`validate_grid_lid` for saved or API designs. Nothing is reshaped to make it
fit. The hinged lid and Lid for stacking are mutually exclusive, and no stackable
claim is made for a hinged lid. These are nominal figures, **unverified** by any
print. **Raised for Andrew's product decision:** no usable hinged-lid design
fits the Gridfinity envelope as it stands; options are a different hinge
(a printed-in-place or shorter-swing design), a smaller stop angle with a
relieved lid corner, or leaving the hinged lid Wavefinity-only. Wavefinity
hinged-lid behaviour is unchanged.

## Local temp space

This project keeps a folder named `local-temp/` at the repository root. It is local temp space: files that belong with this project on this machine but are never backed up to the cloud repo - captures, trial output, scratch files. The project's .gitignore ignores `local-temp/`, so nothing in it is ever committed. Its contents are disposable: never keep the only copy of anything that matters in it. The convention is defined once for every project in Help-Code (REVIEWER-CHAT.md, 'Local temp space').

# Reference appendix

Material kept for occasional use. It is not part of the everyday read above; follow a pointer from the main text when a task needs it.

### Gridfinity magnet holes (Story 3007)

Ordinary 42 mm Gridfinity bins can optionally have four blind 6x2 mm magnet pockets per foot; None is the default. The 6.5 mm diameter and 2.4 mm depth are unconfirmed starting values, intended for press-fit with adhesive optional. Only Andrew’s recorded fit print on his printer, material and slicer can confirm fit. The 21 mm feet and container floors have no magnet holes.
