# Changelog

## 2026-09-05 — Photo Nest custom cavities

### Replaced

- Replaced the measured segment Nest with **Photo Nest — custom part cavity**.
- Uploads accept JPG/JPEG, PNG, and WEBP; detect all four letter-paper corners,
  correct perspective to 215.9 × 279.4 mm, isolate one outside silhouette,
  remove small noise, and return a closed millimetre contour.
- The editor now contains only Upload part photo, Clearance, Wall height,
  Outline wall, and Soften outline. Bin wall/floor and flat-wall-band controls
  were removed from the browser editor.
- The 2D view draws the real cavity contour with move, rotation, and
  proportional-resize handles. Width/depth automatically snap upward to the
  smallest enclosing 8 mm-grid bin while Bin height remains independent.
- Geometry now builds an open raised cutter wall from the printable floor,
  softens small outline details on request, adds a chamfered reinforcing foot,
  and leaves the bin open inside. Old segment Nest files fail with an explicit
  retired-format message.

### Verified

- Added scale, perspective, cleanup, upload-rejection, contour offset, rim,
  cavity-depth, base-thickness, grid-sizing, serialization, API, browser
  contract, and retired-format tests.
- All 266 tests pass. Live browser QA confirmed outline editing, automatic bin
  resizing, clear upload errors, a clean console, and a watertight exported and
  reloaded 3MF/STL mesh.

## 2026-09-05 — Photo Nest cutter tuning

- Removed Advanced bin settings from the browser editor; printable wall, floor,
  and flat-band values now stay on tested defaults.
- Replaced the filled cavity block with an open contour wall rising from the
  bin floor. Added a small reinforced chamfered foot and a Soften outline
  control that removes small inward and outward details before clearance.

## 2026-09-05 — Cradle Spacing, and Auto Expand Bin

### Added

- **Cradle `Spacing` setting** (default `0`). At `0` the row of troughs is
  **one continuous body**, neighbours sharing the wall between their channels.
  Raising it first widens that shared wall; past one wall thickness the troughs
  become **separate solids** with a growing air gap. So the same control runs
  from "joined into one piece" to "fully separated". Exposed in the cradle
  editor next to Floor gap.
- **"Auto Expand Bin"** button at the top of the interior-supports section,
  shown only while a support does not fit. It grows the bin on the 8 mm grid to
  the smallest size that holds every support at the footprint it actually needs
  — a cradle clamped to a too-small bin gets its real tool length back — then
  trims any axis that overshot. Supports keep their position; nothing is
  rearranged. New endpoint `POST /api/layout/expand`.

### Changed

- Cradle pitch is now `diameter + wall + spacing` with `spacing` defaulting to
  `0` (was a fixed 1.2 mm gap). `RIB_SPACING` is gone.

### Tested

- `test_spacing_zero_joins_the_row_into_one_shared_body`,
  `test_raising_spacing_past_a_wall_splits_the_row`, and three
  `expand_layout_payload` tests (grows a clamped cradle back to size, leaves a
  fitting layout alone, refuses an empty layout). Full suite green.

## 2026-09-05 — A cradle is one continuous trough per tool

### Changed

- **The cradle is a continuous half-round trough, not two ribs.** It used to
  support a tool on two thin ribs, one near each end, with the tool bridging
  the gap between them. It is now a single block the length of the tool with a
  half-cylinder channel cut the whole way along the top, so the entire tool —
  shaft and handle — beds into one continuous cradle. The channel mouth still
  sits on the top face, so there is still no overhang for the printer.
- **Quantity places separate troughs, not more notches in a shared rib.**
  Quantity 3 is now three distinct trough bodies side by side, each its own
  solid with `spacing` mm of clear air between them, rather than one wide rib
  pair with three notches cut in it. "Auto" fills the zone with troughs.
- `rib_thickness` (still the JSON key, unexposed) is now the trough's wall,
  split half to each side of the channel; same proportional sizing as before.

### Tested

- Rewrote the cradle geometry suite for the trough model: one continuous body
  per tool spanning the full length, its top level with the channel mouth, a
  short tool still getting a full-length trough, N separate watertight troughs
  for Quantity N (alternating or not), clear air between neighbours, and the
  staggered row. `test_organizer_inserts` 103, full suite green.

## 2026-09-05 — Cradle X/Y and Quantity actually fit now

A pass over every cradle direction × quantity combination turned up three bugs
that made valid layouts fail:

### Fixed

- **Quantity 2+ was rejected in a bin with plenty of room.** The live footprint
  sizer produced a fractional zone (e.g. 16.4 mm across for two lanes); the
  design pipeline then snapped it to the *nearest* grid line — 16 mm — and the
  engine refused the now-too-small zone with *"needs 16.4 mm across but the zone
  gives 16.0 mm"*. Every auto-computed cradle edge now rounds **up** to the 1 mm
  grid, so the snap can't shrink it below what the tool needs.
- **"Auto" Quantity always built exactly one lane.** The sizer collapsed the
  across axis to a single lane before the engine's "fit as many as fit" could
  run. Auto now spans the whole bin, and the engine packs it with lanes.
- **A too-long tool gave a cryptic overflow.** Rotating a 40 mm tool across a
  13 mm bin axis reported *"a cradle reaches outside the bin: its zone is
  61.6 × 16.4 mm at (-30.8, -4.0)…"*. The sizer now clamps the zone to the bin,
  so the engine's specific message fires instead: *"Custom item is 40 mm long
  but its zone only runs 13 mm along x"* — which points straight at the fix
  (rotate, or turn off Alternate ends, whose stagger adds half a tool length).

### Changed

- **A cradle starts at Quantity 1**, like a post — "auto" is now opt-in and
  means "fill the bin with lanes".
- Resizing the bin re-fits the open cradle draft to the new floor instead of
  leaving its zone — and a stale error — hanging off the old size.
- The client computes the bin's usable rectangle itself (mirrors
  `BoxSpec.usable_inside`) so the sizer never fights a lagging preview.

### Tested

- New Python probe over 4 bin sizes × {1,2,3,8,auto} × {x,y} × alternate: every
  combination either builds or fails with a message that names the real
  constraint. Browser-verified the same matrix live. Full suite (240) green.

## 2026-09-05 — A cradle has no fit tolerance and no rib knob

### Changed

- **A cradle ignores fit clearance.** It is an open half-circle the tool drops
  into, not a socket that grips it, so the notch is now cut to the tool's true
  diameter. The **Fit clearance** field is gone from the cradle editor (Nest and
  Bore keep it); a cradle item's stored clearance is pinned at 0.
- **Rib thickness is automatic and proportional.** A cradle rib is now about a
  quarter of the tool's diameter, floored at the thinnest printable wall
  (1.6 mm) and capped at 6 mm, so a thin driver shaft gets a thin rib and a fat
  handle a chunkier one without anyone tuning a number. The **Rib mm** field is
  gone; `rib_thickness` still works as a JSON/CLI override for the rare case
  that needs it.
- **"Alternate ends" is unchecked by default** - it was always the code default;
  this just states it. Floor gap is unchanged and still editable.

### Tested

- Reworked the cradle geometry tests around the true diameter and the
  proportional rib; replaced "more fit clearance lifts the tool" with "a cradle
  ignores fit clearance". `test_organizer_inserts`, `test_organizer_app` and
  `test_wavefinity_web` all green.

## 2026-09-05 — The cradle is just a length and a diameter now

### Changed

- **A cradle holds one plain cylinder.** It used to describe the tool as a
  shaft plus a handle - four numbers - and cut a rib per segment so a
  screwdriver sat level. In practice a cradle is a half-circle notch, and the
  only things it needs to know are how long the tool is and how fat. The
  editor now shows **Length** and **Diameter** and nothing else; Handle length,
  Handle thickness and the Round/Hex/Square profile are gone from the cradle
  (they stay on Nest and Bore, which still use them). Each tool now rests on
  two ribs, one near each end.
- **"Alternate ends" now staggers, it does not flip.** With a single-diameter
  tool there is no end to flip, so the option instead shifts every second lane
  half a tool length along the run axis - a row of real screwdrivers, whose
  handles are fatter than this model, can interlock head-to-tail instead of
  butting handles. A cradle set to alternate needs a zone about 1.5x the tool
  length along the run.
- Old saved designs with a two-segment cradle item still load and build; the
  cradle just treats the item as one cylinder of the overall length at the
  widest diameter.

### Tested

- Rewrote the cradle suite and added `MultipleCradleTests` and
  `CradleAndDividerLayoutTests` - even lane pitch, one shared axis height,
  auto-fill without overrun, the staggered row, fused and removable assembly,
  and cradles sharing a bin with dividers. 103 tests in `test_organizer_inserts`,
  plus the app and browser suites, all green. Browser check: the cradle editor
  shows only Length and Diameter; Nest still shows the handle and profile
  fields; the 3D preview builds the two-rib notch.

## 2026-09-05 — Connector positions must be whole waves; corner flats explained

### Fixed

- **A connector slid half a wave along a seam jams by about 48 mm3.**
  `make_side_connector` accepted any position on a 2 mm lattice and told the
  user that this was what made one printed part fit every seam. It is not. The
  corridor between the arms is cut to the wall's wave, and that wave inverts
  every half cycle, so the clip wanted a half-wave along is the printed one
  **mirrored** — same volume, and a shape no amount of turning a part over
  will produce. Positions now have to be whole multiples of `WAVE_LENGTH`
  (4 mm). Every fixed position the suite happened to exercise landed on a whole
  wave, which is why nothing caught it. The browser generates at position 0 and
  was never affected; `organizer_app.py side --position` was.

### Added

- `placed_outline()` and `mating_clearance()` in the engine measure the real
  gap between two bins standing on the grid, and refuse a centre that is off
  the wave lattice rather than quietly reporting a number nothing can be built
  to. `nested_clearance()` names the figure they should return: 0.21 mm, the
  perpendicular gap between two mated walls.
- Regression tests for the thing the 8 mm grid exists for: a mixed-size seam
  has to clear by *exactly* as much as a matched one, not merely fail to
  overlap. Covered for 24x48 against two 24x24s in both orientations, the
  extremes of the size range against each other, and a packed drawer of seven
  different sizes. Plus: one printed clip still seats after being slid to
  another lattice step, and it grips a tall bin and a short neighbour at every
  position their shared wall has room for.

### Documented

- **Two of a bin's four corners really are flatter than the other two.** Walls
  stop 1 mm short of the nominal corner wherever the wave happens to be, and
  because the wave is odd one diagonal ends on a crest and the other on a
  trough. The chamfer joining them is about 1.97 mm on one pair and 0.86 mm on
  the other, leaving roughly 1.26 mm and 0.50 mm of flat after the 0.6 mm
  fillet. This is in the exported solid, not just the preview. It does not
  affect mating: a corner chord cuts *inward* from the wave envelope, so it can
  only add clearance. Bins sharing a wall clear by 0.21 mm; bins meeting only
  at a corner clear by about 1.2 mm.
- A clip cannot straddle the joint where two short bins butt end to end — the
  far side of the seam there is their end walls, full height. On the 4 mm
  lattice the first usable spot is 8 mm from the joint.

## 2026-09-05 — Removable inserts follow the waves

### Changed

- Removable-insert base plates now follow the box's real wavy interior with
  0.4 mm clearance all around. This covers the floor cleanly without leaving
  the long debris-catching gaps made by the former straight rectangle.

## 2026-09-05 — Repeated handled tools can alternate ends

### Added

- Cradle and nest editors now include **Alternate ends**. It turns every
  second repeated tool end-for-end, placing neighbouring handles and shafts
  beside one another. The choice is preserved in saved designs as
  `alternate_ends`; older files continue to load with it off.

## 2026-09-04 — Divider gets radically simpler; every draft previews live in the bin

### Changed

- **The isolated "Live support preview" canvas is gone, for every kind.**
  Whatever is currently being edited (not yet added) now renders live,
  highlighted in amber, directly inside the main 3D and 2D bin views -
  right where it will actually sit, at the bin's own scale, instead of
  alone on a separate small canvas with its own camera. `/api/preview`
  gained an optional `draft` field: the draft is built and shown alongside
  the real placed supports (tagged `draft_<kind>` so the browser can colour
  it apart from them), but it never touches the real design - a draft
  that's currently invalid falls back to the same red placeholder prism a
  broken placed feature already used, so a rejected edit is now
  unmistakable (see the wedge/45° entry below) instead of silently leaving
  the old shape on screen.
- **Divider is now five fields, not ten.** Wall to wall by default, with
  quantity, spacing, angle and thickness fully determining where every
  wall goes - Center X/Y, the footprint Width/Depth, and the "Fit to bin"
  button are gone because there is no longer a manually-sized footprint
  for them to describe. With that its last caller gone, `/api/feature/
  autosize`, `auto_size_payload` and `_grow_zone_to_fit` are removed
  outright rather than left reachable by nothing - dead code, not a
  deprecation:
  - **Width mm** (renamed from "Wall mm" - it always meant the same
    thing, the wall's own thickness).
  - **Height mm** - blank by default, with grey placeholder text reading
    "height of box" instead of a pre-filled number, so "blank" visibly
    means "as tall as the bin," not "I forgot to look."
  - **Angle °**, **Quantity**, and **Leaning shape** (kept - see below) -
    unchanged.
  - **Spacing mm** (new) - blank by default ("fills evenly" placeholder),
    overriding the computed even gap between walls when you want an exact
    number instead. `divider_defaults` computes the auto value as
    `span / (count + 1)`; `build_divider` uses whichever `spacing` resolves
    to as the actual fence-post gap, so an override is anchored the same
    way the auto value already was - only the number changes, not the
    layout model.
- **The floor now has its own colour** (`#b9a97e`, a warm tan) instead of
  `#e8efef`, which was nearly indistinguishable from both the white page
  background and the pale "inside wall" colour.

### Fixed

- **"Changing to Wedge doesn't change the preview" and "wedge at 45° looks
  the same"** were two different things wearing one report. At the default
  0° angle, Wedge and Straight are mathematically identical (confirmed by
  diffing the returned geometry) - correct, matching the help text already
  under the control. At 45° with the default thickness, a *wedge*
  specifically is refused outright (tapers to under the printable minimum)
  - and the now-removed small preview canvas kept silently showing the
  last *successful* build on any error, so a rejected edit looked
  indistinguishable from a no-op. Confirmed live: the new live-in-bin
  preview turns the divider into the red invalid-placeholder shape the
  instant that happens, with the reason spelled out in the status line
  right above it.

### Verified, not changed

- **A full-span divider never reaches past the true outer wall.** Checked
  directly against the engine for a 3-way divider on the default bin: the
  maximum distance any vertex of any of the three walls sits outside the
  box's own outer wall polygon is `0.000000` mm. Full-span dividers hug
  the *wavy* wall exactly, not a flat approximation, so at some camera
  angles a wall's own crest can appear to weave in front of a divider's
  amber highlight in the simple painter's-algorithm preview - a rendering
  ambiguity between two faces meeting at (almost) the same depth, not the
  built part reaching anywhere it shouldn't. Softened the draft highlight's
  outline stroke (from a bold 1.4px to a light 0.6px) since that was most
  of what made the ambiguity visible; the fill colour remains the primary
  way a draft reads as "this one is different."

## 2026-09-04 — Close the last gap: find a stale process even with no PID on record

### Fixed

- **A relaunch could still silently reattach to an ancient process** if
  that process predated `wavefinity.pid` (or was started some other way)
  and so never recorded its own PID - exactly what happened after the
  slot-removal commit: the `.bat` launcher kept opening a browser tab
  against a process that had been running continuously since well before
  `SERVER_INSTANCE` existed (its `/api/health` didn't even have an
  `instance` field). The version-mismatch banner (previous entry) can tell
  a user *after the fact*, but the actual fix is not reattaching to it in
  the first place.
- `_replace_stale_process` now has a second way to find the PID to kill:
  `_pid_on_port(host, port)` asks the OS directly which process holds the
  port (`netstat -ano` on Windows, `lsof -ti` on macOS/Linux), used only
  when `wavefinity.pid` doesn't name one. The safety condition hasn't
  changed and doesn't depend on either lookup method - a real
  `/api/health` response confirming a genuine Wavefinity service, not
  merely something listening, still gates any kill. An unrelated program
  on the port (verified live with a plain `http.server` instance) is still
  left strictly alone.
- New tests: `test_a_service_with_no_recorded_pid_is_still_found_and_replaced`
  (a real subprocess with a decoy PID file elsewhere, found only via the OS
  lookup, and killed) and `test_an_unrelated_service_on_the_port_is_left_alone`
  (a real, separate `http.server` process, confirmed still running
  afterward). The old "no PID file means never touch it" test is gone -
  that was a proxy for "we can't be sure it's really Wavefinity," and the
  health-check schema was always the actual, stronger guarantee.

## 2026-09-04 — Detect a restarted backend instead of silently running stale

### Added

- **The browser now notices when the Python backend it's talking to has
  restarted**, and says so. `wavefinity_web.py` generates a random
  `SERVER_INSTANCE` id each time the process starts - not a manually-bumped
  version, so *any* restart is caught, even one that didn't change
  `SERVER_VERSION` - and returns it from `/api/health` and `/api/catalog`.
  `web/app.js` records the instance it loaded against and polls
  `/api/health` every 5 seconds; on a mismatch the connection indicator
  turns amber ("Engine updated") and a banner offers **Reload now**, which
  hard-reloads both the page and its connection to the (now current)
  backend. Both the indicator and the banner's button trigger the same
  reload.
- This is a detection layer, not a replacement for
  `_replace_stale_process` (2026-09-04, stale-server fix) - that one
  actively kills and replaces a process *this launcher* started. A process
  it did not start (an old one from before that fix existed, or a manual
  `python wavefinity_web.py` run some other way) is deliberately left
  running rather than killed on a guess, and previously gave no sign that
  the page was talking to it. The banner now catches exactly that case:
  confirmed live by killing a server process behind an already-open page,
  starting a fresh one on the same port without touching the page, and
  watching the banner appear within one 5-second poll and clear on Reload
  now.
- `StaleProcessReplacementTests` gained
  `test_two_separately_started_processes_report_different_instances`, and
  the health/catalog contract test now asserts `instance` is present and
  agrees between the two routes.

## 2026-09-04 — Claude (retire slot, expand divider)

### Removed

- **The `slot` holder is gone.** Its one genuine difference from a divider -
  a shallow groove with a solid floor left under it (`depth < height` was
  always enforced) - was judged not worth keeping as a separate kind versus
  the overhead of two similar-looking tools. `build_slot`/`slot_defaults`,
  its catalog entry, its palette icon and its own colour are all removed;
  a divider fills the gap it leaves.

### Added

- **A divider now defaults to running wall to wall.** `default_feature` sets
  `full_span=True` for a new divider and starts its zone at the bin's full
  footprint on both axes, instead of a thin 2 mm strip - "reach the real
  wall" is now the normal case, not something reached for with Fit to bin
  afterward.
- **`along` (Runs along X/Y) is now a direct browser choice for a divider**,
  the same segmented control every other along-having kind already has,
  instead of being silently inferred from whichever of Width/Depth happened
  to be bigger. The server no longer overrides a divider's `along` on every
  request; wherever it used to (loading a saved feature, after Fit to bin)
  now leaves it exactly as sent.
- **A divider's `count` places several evenly spaced parallel walls**
  instead of one - fence-post spacing, splitting the zone's cross axis into
  `count + 1` equal gaps, so `count = 1` (the default, shown as "auto")
  reproduces the existing single-centred-divider case exactly. Height,
  angle, thickness and full-span all apply to every wall the count places.
  Too many for the available width is refused with a clear "N dividers need
  at least X mm" message, the same style the removed slot used to give.
  `_feature_reach` widens for count generically now (each wall's own margin
  applied to the whole zone span, not the single-wall centred formula) -
  safe for any count, including the default of one.

## 2026-09-04 — Claude (preview wave-density fix)

### Fixed

- **The 3D/2D preview drew the longer pair of walls as straight segments
  meeting at angles instead of a smooth wave.** `preview_rings` sampled
  every wall with the same fixed point count (22) regardless of its
  length, so a short wall (say 13 mm, ~3 cycles) got a smooth ~7 points
  per wave cycle while a long one on the same box (say 45 mm, ~11 cycles)
  got barely 2 - visibly faceted, not curved. `_wall_points`'s override
  parameter is now a *density* (points per wave cycle, default 7), scaled
  by each wall's own length, so a non-square box's short and long walls
  read equally smooth. This only ever affected the coarse preview ring;
  the actual exported mesh always sampled by length via `_sample_count`
  and was correct the whole time. `PreviewRingDensityTests` pins the fix:
  a longer wall gets proportionally more points, and the short and long
  pair sample at the same density.

## 2026-09-04 — Claude (stale-server fix)

### Fixed

- **Relaunching silently reattached to an old, already-running server
  instead of replacing it with current code.** `wavefinity_web.py`'s port
  reuse-check (added to stop a launcher racing a genuinely separate second
  server) treated "something is already answering this port" as always
  meaning "nothing to do here" - including when that something was this
  same app's own previous run, holding stale code from before the last
  edit. Every stale-UI report earlier in this session traced back to this:
  clicking Fit to bin got `unknown API route` because the process actually
  answering the browser's requests predated the route's existence, even
  though the source on disk was current and the tests against it passed.
  The app now writes its own process id to `wavefinity.pid` on startup; on
  a relaunch, if the port is taken, it terminates whatever process that
  file names (after confirming a genuine Wavefinity service - not some
  unrelated program - is the one holding the port) and rebinds. A server
  this launcher did not itself start, or one from before this fix existed,
  is left alone with a clearer message explaining why and what to do.
  `test_wavefinity_web.StaleProcessReplacementTests` spawns a real
  subprocess to verify it actually gets killed and the port frees, and
  that an unrecorded process is never touched.

## 2026-09-04 — Claude (browser UI pass 3)

### Added

- **2D layout now draws the box's true wavy interior**, not a plain
  rectangle. `preview_payload` returns a new `cavity_outline` (the same
  `wavy_cavity_polygon` the engine itself builds from), and the 2D canvas
  fills and clips to that shape instead of the flat placement rectangle -
  which is still drawn, as a dashed reference line, since every
  non-full-span support still has to stay inside it. This is what makes it
  possible to see, at a glance, whether a divider actually reaches the real
  wall or stops short of it.
- **Every divider gets a 1 mm, 45-degree base chamfer for strength** - both
  long faces flare out by that much at the floor and taper back to the
  wall's own line one millimetre up (`DIVIDER_CHAMFER` in
  `organizer_inserts.py`). It is a pure addition below the wall's stated
  profile - the lean and thickness above the chamfer are exactly what was
  asked for - and applies to a plain, wedge, straight-leaning, and even a
  full-span leaning divider (inherited for free, since that path already
  builds its oversized wedge through the same function). A straight,
  non-leaning full-span divider is unaffected: it is built by a separate,
  simpler clip-and-extrude path this pass did not touch. `build_divider`'s
  plain-box special case is gone - every non-full-span divider now goes
  through one function (`_divider_wall`, renamed from `_angled_divider`).

### Investigated, not a bug

- "Changing quantity and clicking Update selected does nothing" -
  reproduced on cradle and bore with a fresh server: the dirty-check
  correctly enables Update selected the moment quantity changes, and a
  rejected edit (e.g. an item too long for a since-shrunk zone) correctly
  shows a 5-second red toast naming exactly why. Likely explanation: an
  old server process still running from earlier in this session, predating
  several of today's fixes - screenshots showed the pre-merge "Customize
  your bin" section and the old standalone Delete button, both gone in the
  commit before this one. Restarting the app should resolve it; if not,
  the toast text is the thing to report back.

### Changed

- **Auto-size simplified to one button.** The previous "Fill the bin" /
  "Guess from quantity" pair on a divider or slot was confusing and, for
  anyone still running an older server process, silently did nothing (the
  route did not exist yet on that process - restarting picks up the fix).
  It is now a single **Fit to bin**: a divider grows only along its run
  axis to reach the walls; a slot grows in both directions and also drops
  any typed quantity back to automatic, so the builder fits as many slots
  as the new, bigger footprint actually holds. The existing per-kind
  **Auto** button next to Quantity is unchanged.
- **Delete moved to the placed-supports list.** It was a single button up
  in the parameter editor, enabled only for whichever support happened to
  be selected. Each row in **Placed supports** now carries its own small
  ✕, so a support can be removed directly without first selecting it.
- **"Customize your bin" folded into "Build your bin."** It did not need
  to be its own accordion section; the scoop checkbox and the physical
  settings (renamed **Advanced bin settings**, still an expandable
  `<details>`) now sit at the end of the bin section, after Placed
  supports.
- **8 mm cartridge removed from the browser UI.** It is still a real,
  tested engine and CLI mode (`organizer_app.py organizer --mode
  cartridge`), useful for a reusable coordinate footprint across bins, but
  in the editor it mostly produced a confusing flash-and-revert the moment
  an already-placed support did not land on an 8 mm cell. The browser now
  offers only **Fused** and **Removable**.
- **Removable's base plate thinned from 1.2 mm to 0.6 mm** (`BASE_PLATE`
  in `organizer_inserts.py`) - "thin" was the point of a separately
  printed plate that just drops into the bin.
- **Zone fields (Center X/Y, Width, Depth) now step by 1 mm**, not 0.1 mm,
  matching the 1 mm snap every one of those edits is already silently
  rounded to server-side. Per-kind option fields (Height, Wall, Angle, and
  so on) are unaffected - they are not snapped and keep finer control.

## 2026-09-04 — Claude (browser UI pass)

### Fixed

- The 3D/2D preview could grow far taller than the viewport and run off
  the bottom, with the floor painting mostly white. Root cause was a
  circular height dependency: `.app-shell` set only `min-height`, so
  `.workspace`'s `minmax(500px, 1fr)` canvas row had no definite height to
  resolve against, and the canvas's own pixel-buffer size fed back into
  that same calculation. `.app-shell` now gets a firm `height`, both
  columns get `min-height: 0` so they can actually shrink to their track,
  and the mobile stacked layout gets its own explicit height instead of
  inheriting the desktop one.
- Switching Fused/Removable/Cartridge did change the preview - confirmed
  by directly reading back `kindColor()` - but the insert tint (a 30%
  blend) was too close to each holder's own hue to read as "changed" at a
  glance. Raised to 50%.
- The mode-description text sat directly against the segmented control
  above it (`.field-help` had a *negative* top margin), reported as
  "overlapping."

### Changed

- Left settings column widened from a 430px cap to 690px (+60%); the
  preview column gives up the difference.
- "Build your bin" / "Customize your bin" / "Label your bin" lost their
  01/02/03 prefixes and gained a bolder 3px divider between them.
- "Width X" / "Depth Y" are now "Units X" / "Units Y"; the per-field
  "8 mm units" caption is gone, replaced by one "(unit = 8 mm)" note next
  to the "Build your bin" heading.
- The bin-size readout ("16mm (13 inside) wide...") is larger and bolder.
  Number-input spin buttons are forced visible (`opacity: 1`) rather than
  hover-only.
- Removed the "Live geometry" status text (silent on success, matching
  every other status line in the app) and the description paragraphs
  under Bottom/Top label.
- "Part name" is now "Part Name (For file)"; the "filename only" caption
  is gone.
- Removed the "Sampler boxes" field - the sample plate is a fixed set of
  sizes, matching what the README already said.
- Quantity is now a real number field with an adjacent **Auto** button
  that clears it back to "let the builder fit as many as possible,"
  instead of a text field where typing the word "auto" was the only way in.
- **Update selected** is now enabled only when the draft actually differs
  from the placed feature it came from (a `JSON.stringify` comparison
  against a snapshot taken at selection time), not merely because
  something is selected - it no longer lights up from clicking a support
  in the 2D layout alone.
- **Output folder** is now sticky: a new `POST /api/preferences` route
  writes it to `wavefinity_prefs.json` next to the app (gitignored, a
  per-machine file, not browser storage - it survives a different browser
  or a cleared profile because the *server* owns it), and the catalog
  response returns the saved value on the next load.

### Added

- Two auto-size buttons sit above the parameter fields for **divider** and
  **slot** - the only two kinds where a quantity or a footprint has an
  unambiguous "divide the bin" meaning; the other five kinds' `count` means
  repeated elements inside one footprint, not sections of the bin, so they
  keep manual sizing only. **Fill the bin** (new `POST
  /api/feature/autosize`, `goal: "fill"`) grows the draft's zone one
  `snap`-sized step at a time on each side independently until it meets
  the usable floor edge, another placed support, or a reserved scoop/label
  zone - a divider only grows along its run axis, a slot grows in both
  directions. It is a greedy fill, not a true maximal-rectangle solve, so
  a divider recentred after a big manual shrink can land a step short of
  the wall on 1 mm grid rounding; good enough for "make this big," not a
  precision tool. **Guess from quantity** (`goal: "quantity"`, slot only)
  sets the footprint's cross-axis - the direction the N grooves stack
  across - to the *whole* usable floor in that direction, ignoring what
  else is already placed, exactly as asked for: an estimate, not a
  collision-checked fit.

## 2026-09-04 — Claude (latest)

### Added

- Added a lean to the divider holder: an `angle` option (±45°, the standard
  support-free FDM overhang limit) and a `wedge` shape flag
  (`organizer_inserts.py`, `Feature.wedge`, default `True`), plus the
  browser field to drive both.
  - **Wedge (default)**: the back face stays vertical; only the leaning face
    slopes, so the wall is thickest at the floor - where the sideways push
    of whatever leans against it actually bears - and tapers as it rises,
    the same shape a physical gusset uses.
  - **Straight**: both faces shear together, uniform thickness the whole way
    up, with no extra material at the base. Deliberately the weaker,
    opt-in option; it is exactly the "easy to break" shape the wedge exists
    to avoid.
  - Verified geometrically, not just that it builds: sliced the actual solid
    at several heights and confirmed the straight wall holds its stated
    thickness everywhere while sliding, and the wedge's back face never
    moves while its front face narrows linearly to
    `thickness − height·tan(angle)` at the top - and uses measurably less
    material than the straight wall spanning the same lean. Negative angles
    mirror correctly, `along="y"` mirrors `along="x"`, angles past ±45° and
    wedges tapered past their own thickness are refused with a clear
    message, and both fields round-trip through the saved-design schema
    with safe defaults for older files.
  - Wired into the browser editor: an "Angle °" field beside the divider's
    existing Height/Wall fields, and a Wedge/Straight toggle next to it that
    explains the trade-off inline. Uses the same resolve-for-display,
    write-only-on-edit pattern as every other option field, so an
    unedited angle keeps showing the live resolved default instead of a
    frozen number.
  - A full-span divider can lean too (`_full_span_leaning_divider`).
    Originally shipped as a refusal, on the assumption that combining "hug
    the true wavy wall" with "lean at an angle" would need the wall
    intersection done one height-slice at a time. It doesn't: the same
    oversized wedge `_angled_divider` already builds, generously widened in
    the run direction, intersects directly against the box's real 3D
    interior volume - one boolean, not a slice per height - and the result
    hugs the wave correctly in both directions at once, because the lean
    only moves the wedge's *cross*-axis position and the wave only varies
    along its *run* axis; the two never fight over the same coordinate.
    Verified by sampling several (position-across-the-lean, height) points
    directly, not just each height's overall bounding box, and comparing
    each to the wall's true boundary at that exact point: zero gap to mesh
    precision, at every one of them.

### Fixed

- A divider's "Wall mm" (its real thickness) could be refused outright for
  being wider than "Depth" - the footprint rectangle the editor happened to
  draw, a separate number that was never kept in step with it. Caught live
  in the browser testing the wedge above: the default 2 mm footprint
  rejected any wedge thick enough to actually work. A divider has always
  built from its own `thickness` option on the cross axis, not from the
  zone (`build_divider` has never used `zone.depth` there); `_feature_reach`
  now says so explicitly and widens to whichever is bigger, instead of
  treating the disagreement as an escaped builder. The browser editor keeps
  the two in step going forward: typing a new "Wall mm" widens the shown
  Width/Depth field to match, live, rather than leaving it to fall behind.

## 2026-09-04 — Codex

- Completed the browser-only transition: removed the obsolete Tkinter launcher
  and widget UI, and made `Launch_Organizer_UI.bat` the sole application entry
  point.
- Added visible descriptions for fused, removable, and 8 mm cartridge inserts.
- Added mutation locking and stale-preview invalidation so rapid add/delete or
  mode changes cannot overwrite newer browser state.
- Added keyboard/tab semantics and accessible equivalent fields for the canvas
  editors; full suite now passes 169 tests.

Notable Wavefinity changes are recorded here by date and author.

## 2026-09-04 — Claude (later)

### Added

- Added a full-span option to the divider holder (`Feature.full_span`,
  `organizer_inserts.py`). A straight rib sized to the safe usable
  rectangle - the only rectangle guaranteed to clear the wave at every
  position - still leaves the wave's own swing as a gap at most positions
  along its own thickness, since that rectangle gives up a full amplitude
  just to stay valid everywhere. A full-span divider only has to be right at
  its own position: it is built oversized and trimmed against the box's real
  interior outline (the flat band near the floor if the box has one, the
  wavy profile above it) instead of approximated with a margin, so its end
  face follows the true wall contour and touches it everywhere along its
  thickness, not just at the centre. Verified by slicing the built solid at
  several points across its own band and comparing the true cross-section to
  the wall's, not just the bounding box.
  - Inside a removable or cartridge insert, the same oversized divider is
    re-clipped to the insert's own straight, rounded-rectangle footprint by
    the existing insert-trim step, so it meets *that* edge exactly instead of
    the wavy wall it was built against.
  - `full_span` is refused on every kind but `divider`, and round-trips
    through the saved-design JSON schema (`layout_to_dict`/`layout_from_dict`),
    defaulting to `False` for designs saved before this existed.
  - Engine-only so far: no editor checkbox yet in either front end. See the
    note below.

### Note for whoever wires the UI

This landed as engine capability only (`organizer_inserts.py` +
`test_organizer_inserts.py`), deliberately not touching `organizer_app.py`,
`web/app.js` or `web/index.html` - all four were mid-edit, uncommitted, at
the time (`organizer_app.py` had just dropped from 3425 to ~1035 lines and
lost its `launch_ui()` entirely; `test_organizer_app.py` had dropped by 899
lines). Once that settles, the remaining piece is a "Full width" checkbox on
the divider editor that sets `full_span=True` and hands the run-axis
width/depth field over to the engine (any manual width edit should clear the
flag again, since it's an explicit override of "figure it out").

## 2026-09-04 — Codex

### Audit follow-up

- Preserved automatic holder parameters as automatic values in the browser.
  Resolved dimensions still appear in the form, but only a field the user
  edits is stored as an explicit override. Nests, pockets, bores, slots and
  dividers therefore continue to follow later item, zone and bin changes.
- Restored the visual distinction between fused holders and holders printed on
  removable/cartridge inserts. Both the full preview and live support preview
  now retain the engine's `feature_*` / `insert_*` geometry tags, and removable
  holders receive a related warm tint.
- Made the default post fit a one-cell-wide 8 mm cartridge by adapting its
  starter diameter to the available footprint. Wider layouts retain the
  established 12 mm post default.
- Confirmed that JSON GET responses already receive the shared nosniff and
  same-origin resource-policy headers, and added a regression assertion so the
  hardening cannot silently drift.

### Added

- Added a dependency-free local browser application backed by the existing
  Python geometry engine. It includes the complete Build, Customize and Label
  sections; live Python-generated support meshes; responsive 3D and 2D views;
  drag/zoom/reset camera controls; drag/resize layout editing; support
  add/update/delete; mode conversion; design save/open; and bin, connector and
  sampler generation.
- Added a small JSON API for catalog, design validation, preview, holder drafts,
  layout edits and exports. Browser state uses the existing versioned
  `.wavefinity.json` schema rather than introducing a second design model.
- Added `Launch_Organizer_Desktop.bat` as an explicit Tkinter fallback.
- Added browser/API contract tests covering static delivery, all registered
  supports, real parameter-driven geometry, layout editing, mode conversion,
  preview metadata, validation errors and cross-origin request rejection.

### Changed

- `Launch_Organizer_UI.bat` now opens the local browser app by default while
  preserving `--desktop` and `--check` behavior.
- Both browser previews use one uniform scale, so resizing makes the geometry
  larger or smaller without changing its proportions.

### Security

- The service binds to loopback by default, requires JSON for API calls, rejects
  foreign browser origins, prevents directory traversal in static files, and
  sends a restrictive content-security policy and same-origin resource policy.

### Validation

- Exercised the application in a Chromium browser at narrow and wide responsive
  sizes. Confirmed live dimension changes, live holder parameters, holder
  placement, top-label and scoop validation, removable-mode conversion, 2D
  layout rendering, design download feedback, and a real two-file `.3mf`
  organizer export. No browser console errors remained.
- Re-ran the audit scenarios against the live application and completed an
  independent Microsoft Edge smoke test. The automatic nest dimensions tracked
  a changed tool, and an 8 mm cartridge post placed and previewed successfully
  with no Edge console warnings or errors.
- All 193 tests pass after the audit fixes.

### Documentation

- Added `BROWSER_MIGRATION_REVIEW.md`, a self-contained outside-review brief
  covering the architecture boundary, implementation scope, security controls,
  test evidence, known limitations, reproduction commands and reviewer focus.

## 2026-09-03 — Codex (later)

### Fixed

- The interior-part diagram now enlarges with one uniform pixels-per-millimetre
  scale. Widening the window can no longer stretch the part horizontally while
  leaving its vertical scale unchanged.
- The parameter diagram now renders the actual holder geometry produced by the
  export builder instead of a fixed illustration. Editing dimensions, heights,
  wall thicknesses, recesses, bores, tapers, counts, or stored-tool measurements
  redraws the part after the typing debounce, including before a draft is added.
- Live diagram redraws update only the mesh and leader endpoints, preserving
  focus in the parameter field being edited.
- Divider orientation is now inferred from its Width and Depth. A 13 x 2 mm
  divider runs across X, while 2 x 13 mm rotates across Y instead of collapsing
  into a 2 mm nub. The redundant divider-only axis control was removed.

### Validation

- Added regressions for proportional diagram scaling, live pre-add parameter
  redraws, preserved parameter widgets, and both divider orientations.
- All 182 tests pass.

## 2026-09-03 — Claude (later)

### Fixed

- The 3D preview now shows the difference between a fused and a removable
  insert. It drew the removable form's base plate as the bare layout rectangle:
  flush with the wall, so its sides were hidden behind the wall, and in a colour
  4% away from the floor's. Switching insert form changed a full-floor rectangle
  from one near-white to another and nothing else. The preview now builds the
  plate from `insert_footprint`, the same outline the exporter uses, so the
  0.4 mm clearance that makes the insert removable is visible as a gap all
  round, and the whole insert - plate and every holder standing on it - is
  tinted away from the bin's blues, with each holder keeping its own hue.
- Every shape parameter now shows the number it will actually be built with.
  A holder could leave an option unset, meaning "work it out from the bin, the
  zone or the item", and the editor showed that as a blank box: the nest's
  recess came up empty, so typing in it looked like it changed nothing because
  there was no number to see change. Defaults are now registered per kind in
  `FEATURE_DEFAULTS` and read through `resolved_options`, by the builders and
  the editor alike.
- Typing a parameter now re-makes the selected part as you type, instead of
  waiting for "Update selected". A value that cannot be built leaves the last
  good part on screen and says why on the editor's own line, so a refused
  recess or an over-thick wall no longer looks like a dead field.
- Delete acts on the row highlighted in the parts list when the editor's own
  record of the selection has drifted from it, and says "Pick a part in the
  list first" when there is genuinely nothing selected. A button that silently
  returns cannot be told from a broken one.
- Leader lines on the part diagram no longer cross. Tags were spread evenly
  across the whole panel while their targets clustered in the middle, so the
  outermost tag reached right across the drawing. Each tag now sits level with
  the point it labels and is pushed aside only far enough to fit, and the
  anchors that pointed at the far side of the sketch were moved to the side
  they point at. Zero crossings and zero tag overlaps for all seven shapes at
  a 1440-line screen.
- `draw_diagram` no longer re-enters itself. Measuring a tag runs pending
  events, including the canvas `<Configure>` asking for the same redraw, which
  left the outer pass adding leaders to a canvas the inner pass had cleared.
  The nested call is deferred to a second pass so a resize is not lost either.
- Timers scheduled with `root.after` are cancelled when the window closes,
  instead of firing into a torn-down interpreter and reporting an error.

### Changed

- Folded "Customize your bin" into "Build your bin" and gave the reclaimed
  height to the interior-support editor, which is the row that actually runs
  out of room. Spare height now goes mostly there rather than to the preview.
- The part sketch may now be up to 1.9 times as wide as it is tall, so on a
  wide screen the drawing fills the panel instead of sitting marooned in the
  middle of it with every callout crowded into one narrow band.

## 2026-09-03 — Claude

### Added

- Added a labelled part diagram to the interior-support editor. Picking a shape
  now draws that shape, and each parameter it uses is a field pinned beside the
  feature it changes, joined to it by a leader line: quantity and the run axis
  above the part, the width and depth footprint below it, heights, wall
  thicknesses, hole depths and the stored-tool description against the edge or
  hole they set. The bore, cradle and nest sketches include the tool they hold,
  so the tool's own measurements point at the tool.
- Added `scoop_keep_out` alongside `scoop_floor_zone`, splitting the scoop's
  true footprint from the smaller strip a support has to avoid, with
  `SCOOP_FLOOR_TOLERANCE` (0.4 mm) as the line between them.
- Added `TESTING.md`, a log of every test run and what it found, plus the
  defects that got past the suites. It exists to answer whether two minutes a
  run is buying anything with evidence rather than a feeling.

### Changed

- Made the window resize properly. Both preview canvases fill their panel and
  redraw at the new size instead of staying 330 px, so enlarging the window
  draws a bigger bin; spare height goes mostly to the preview, with minimums
  that stop a squeezed window swallowing the settings column or the diagram.
  The window opens at the size its contents ask for, clamped to the screen.
- Replaced the editor's flat rows of parameter fields with the diagram, and
  moved the placed-parts list, the centre coordinates and the part buttons into
  a panel beside it.
- Fitted the preview to each axis separately rather than to the larger span, so
  a wide canvas is actually used.

### Fixed

- Fixed a false "selected support settings are invalid" warning. The scoop
  reserved its whole run as a keep-out, but the curve meets the floor
  tangentially — one millimetre in from where it lands, a 40 mm bin's scoop
  stands 0.03 mm proud. A divider across the centre of a scooped bin was called
  a collision while sitting flat on the floor. The keep-out now stops where the
  curve has risen 0.4 mm, about one layer; a support genuinely on the ramp is
  still refused.

### Validation

- Added coverage for the diagram (every shape's parameters are pinned and
  anchored, each sketch stays inside the room it is given, a wider canvas draws
  a bigger bin, and choosing a shape draws it with one field and one leader per
  parameter) and a regression test for the scoop keep-out that pins the
  tolerance to the curve's own profile.
- Both suites pass. Runs logged in `TESTING.md`.

## 2026-09-03 — Codex

### Added

- Added a Bottom/Top label selector beside the label field.
- Added top labels with fixed 5 mm lettering, a 7 mm rear rim ledge, a flush
  multi-material inlay, and an exact 45-degree self-supporting underside.
- Added an optional full-width curved scoop at the front of the bin. It rises
  halfway up the usable wall height and becomes part of the removable insert
  when the bin uses a removable or cartridge layout.
- Added scoop and top-ledge keep-out regions to the 2D editor, label placement,
  support collision checks, and export preflight validation.
- Added top-label and scoop support to saved designs and the command-line
  interface, including saved-value overrides.
- Added a guided visual part palette for dividers, posts, pockets, slots,
  bores, cradles, and contour nests with shape-specific parameter controls.
- Added a cut-section slider to the interactive 3D preview.
- Added **Reload code**, which restarts the desktop application while carrying
  the current design into the new process.

### Changed

- Reorganized the desktop controls into **Build your bin**, **Customize your
  bin**, and **Label your bin** sections.
- Changed the desktop window title to **Wavefinity** and removed the redundant
  in-page application heading.
- Gave all peer top-level sections a consistent, more pronounced 3 px border.
- Simplified the interior-support workflow into pick a shape, set its relevant
  parameters, and add or update the part.
- Improved the 3D and 2D previews so top labels, scoops, actual holder geometry,
  invalid settings, and reserved regions are visible before export.
- Preserved removable-insert clearance for scoop geometry and placed bottom
  labels around the scoop instead of beneath it.
- Updated the README for the new customization, labeling, editor, preview, and
  CLI behavior.

### Validation

- Added regression coverage for top-label dimensions and flush inlays, the
  45-degree ledge, scoop size and placement, removable and fused exports,
  customization persistence, CLI overrides, collision handling, and live Tk
  widget structure and styling.
- Verified Python compilation, clean patch formatting, strict multipart 3MF
  exports, and the complete 159-test suite.
