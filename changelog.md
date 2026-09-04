# Changelog

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
