# Testing log

Every run of the suites gets a line here — **including the runs that found
nothing**, which are most of them. That is the point. The suites cost about two
minutes each time, and the only honest way to decide whether they are worth it
is to keep a record of what they actually caught.

Read a row like this:

- **Nothing** — everything passed. The run cost two minutes and bought
  confidence, not a fix.
- **Caught** — a test failed and the failure was a real defect in the code. This
  is the column that justifies the suite.
- **Stale** — a test failed because the *test* was out of date, not the code.
  Overhead, not value.

The second table is the counterweight: defects that reached the user because no
test was looking. If that table keeps growing while the "Caught" column stays
empty, the suites are not testing the things that break.

## Runs

| Date | Run by | Command | Tests | Result | What it found |
|---|---|---|---|---|---|
| 2026-09-03 | Claude | `unittest test_organizer_app.DesktopUiTests` | 9 | Nothing | Ran after the interior-support editor was rebuilt around the part diagram. Confirmed the widget-structure tests still located the parameter fields through the new layout. |
| 2026-09-03 | Claude | `unittest test_organizer_app` | 116 | Nothing | Full app suite after the resizable preview and diagram changes. |
| 2026-09-03 | Claude | `unittest test_organizer_app test_organizer_inserts` | 159 | Nothing | Both suites, after the diagram tests were added. |
| 2026-09-03 | Claude | `unittest test_organizer_app test_organizer_inserts` | 164 | Nothing | Both suites, after the scoop keep-out fix and its regression test. |
| 2026-09-03 | Claude | `unittest test_organizer_app test_organizer_inserts` | 164 | Nothing | After the preview learned to draw the removable insert's real plate. |
| 2026-09-03 | Claude | `unittest test_organizer_app.DesktopUiTests` | 13 | Caught | The UI suite hung, not failed: `Add part` popped a modal `showerror` that no test can dismiss, and the run blocked forever. `DesktopUiTests.setUp` now stubs `messagebox` so a dialog is recorded and asserted on instead of shown. |
| 2026-09-03 | Claude | `unittest test_organizer_app test_organizer_inserts` | 179 | Nothing | Both suites, after the resolved-option defaults, live parameter editing, the delete fallback and the callout layout fix. |
| 2026-09-03 | Codex | `unittest test_organizer_app.PartDiagramTests test_organizer_app.DesktopUiTests.test_parameter_typing_redraws_the_actual_part_before_it_is_added test_organizer_app.DesktopUiTests.test_choosing_a_shape_draws_it_with_a_field_beside_each_parameter` | 7 | Nothing | Focused verification of uniform diagram scaling, actual-geometry redraws and parameter callouts. |
| 2026-09-03 | Codex | `unittest` | 182 | Nothing | Complete suite after the proportional, live holder-diagram and divider-orientation fixes. |
| 2026-09-04 | Codex | `unittest test_wavefinity_web` | 8 | Caught | Initial live-browser startup exposed two arrays that mixed selector strings with DOM elements and called `addEventListener` on the strings. Corrected both, then verified the API, security boundary and static application contract. |
| 2026-09-04 | Codex | Browser QA plus real organizer export | — | Caught | Verified narrow and wide responsive layouts, parameter-driven draft geometry, support placement, label/scoop conflict feedback, mode conversion, 2D layout and browser-triggered `.3mf` generation. Caught the disabled Add button after an asynchronous draft load; the selection state now refreshes when the real draft arrives. Browser console finished with no errors or warnings. |
| 2026-09-04 | Codex | `unittest` | 190 | Nothing | Complete geometry, insert, desktop UI and browser/API suite after the browser migration and hardening pass. |
| 2026-09-04 | Codex | `unittest` | 169 | Nothing | Complete browser-only suite after removing the obsolete Tkinter UI and adding mutation-race and accessibility protections. |
| 2026-09-04 | Codex | `unittest test_wavefinity_web test_organizer_app.InsertEditorTests.test_default_post_adapts_to_a_one_cell_wide_cartridge` | 11 | Nothing | Focused audit regressions for display-only automatic values, fused/removable draft tags, GET hardening headers and a valid one-cell cartridge post. |
| 2026-09-04 | Codex | Microsoft Edge smoke test | — | Nothing | Live automatic nest defaults followed a changed item; the default 8 mm cartridge post built, placed and refreshed the full preview; no browser warnings or errors. |
| 2026-09-04 | Codex | `unittest` | 193 | Nothing | Complete suite after resolving the external browser-port audit findings. |
| 2026-09-04 | Claude | `unittest test_organizer_inserts` | 49 | Nothing | Full-span divider capability, plus a slice-the-real-mesh check (`trimesh.intersections.mesh_plane` at 9 points across 3 positions, both axes) that the built edge matches the true wavy wall to sub-millimetre precision, not just its bounding box. |
| 2026-09-04 | Claude | `unittest test_organizer_inserts.AngledDividerTests` | 9 | Nothing | Divider lean/wedge capability, verified by slicing the built solid at several heights: the straight wall holds its stated thickness while sliding, the wedge's back face never moves while the front narrows to `thickness − height·tan(angle)`, negative angle mirrors correctly, `along="y"` mirrors `along="x"`, and both the ±45° limit and a wedge tapered past its own thickness are refused. |
| 2026-09-04 | Claude | live HTTP round trip against `wavefinity_web.py` | — | Nothing | Catalog exposes the `angle` field and `lean` flag; a fresh divider resolves angle to 0 with `wedge: true`; setting angle=30/wedge=false drafts real geometry (12 faces) and persists both fields through apply and re-select. |
| 2026-09-04 | Claude | `unittest` | 169 | Nothing | Complete suite after wiring the divider angle field and wedge/straight toggle into the browser editor. |
| 2026-09-04 | Claude | live browser (Wall mm = 4 on a default divider) | — | Caught | A thickness wider than the 2 mm default footprint was refused outright - see the matching row below. Fixed in `_feature_reach` and `web/app.js`; `test_a_thicker_wall_than_the_zone_widens_to_match` added, `test_a_builder_cannot_escape_the_zone_claimed_by_the_editor` repointed at a mocked builder so the safety net it was guarding stays tested now that a divider is the documented exception to it. |
| 2026-09-04 | Claude | `unittest test_organizer_inserts` | 59 | Nothing | After the thickness/footprint fix; includes the repointed escape-check test. |
| 2026-09-04 | Claude | `unittest test_organizer_inserts.FullSpanLeaningDividerTests` | 6 | Nothing | Full-span + leaning divider combined. The precision check samples several (position-across-the-lean, height) points directly and compares each to the wall's true boundary at that exact point (not just each height's bounding box), finding zero gap to mesh precision. Also covers negative angle, straight (non-wedge) mode, `along="y"`, the `flat_inside` two-piece split, insert-mode clipping, and that the ±45° and collapsed-wedge refusals still apply. |
| 2026-09-04 | Claude | `unittest test_organizer_inserts` | 64 | Nothing | After combining full-span with a lean. |
| 2026-09-04 | Claude | `unittest` (full suite) | 175 | Nothing | After the browser-UI overhaul pass (sidebar layout, preferences, quantity/auto controls, dirty-check on Update selected). The bugs found this run were all layout/CSS/visual, so the suite itself caught none of them - see below. |

## Defects found outside the suites

| Date | Found by | Defect | Would a test have caught it? |
|---|---|---|---|
| 2026-09-04 | Claude, testing the wedge feature live in the browser | Typing a "Wall mm" wider than the divider's 2 mm default footprint was refused with "exceeds its layout zone" - a legitimate thickness, rejected because a separate, never-synced number happened to be smaller. Pre-existing (`build_divider` has always built from `thickness`, never `zone.depth`); the wedge feature just made a wider wall a normal thing to type. | No. `test_a_builder_cannot_escape_the_zone_claimed_by_the_editor` asserted the *old, wrong* behaviour - a thicker-than-zone divider must fail - so it would have failed loudly the moment this got fixed, not caught the bug beforehand. It only surfaced from actually using the running app. Now covered by `test_a_thicker_wall_than_the_zone_widens_to_match`. |
| 2026-09-03 | User, from the running app | The preview called a divider at the centre of a scooped bin "invalid". The scoop reserved its whole run as a keep-out, including the tangent lip that stands 0.03 mm off the floor. | No. The suite asserted the keep-out *equalled* the scoop's run, so it locked the bug in rather than catching it. Now covered by `test_the_scoop_only_reserves_the_floor_it_actually_lifts`. |
| 2026-09-03 | User, from the running app | Switching between fused and removable changed nothing visible in the preview. The insert's base plate was drawn as the bare layout rectangle, flush to the wall and 4% off the floor's colour. | No. Nothing compared the two forms, and nothing tied the drawn plate to the exported one. Now covered by `InsertFormPreviewTests`. |
| 2026-09-03 | User, from the running app | The nest's "Recess" box was blank and typing in it changed nothing on screen. Options left unset were resolved inside each builder, so the editor had no number to show and no feedback when a value was refused. | No. The suite only ever built holders from explicit options, so it never saw a blank field. Now covered by `ResolvedOptionTests`. |
| 2026-09-03 | User, from the running app | Delete did nothing with a part highlighted. Not reproducible through any input path, but the action returned silently whenever its own record of the selection was unset - indistinguishable from a broken button. | No, and it still would not: the failure needs the two selection records to disagree. The fallback and the "pick a part first" reply are covered by `DesktopUiTests`. |
| 2026-09-03 | User, from the running app | Parameter leader lines crossed each other on the diagram. | No. `PartDiagramTests` checked that every parameter had an anchor, not that the drawing was readable. A crossing check now runs against the live canvas during review; `CalloutLayoutTests` pins the placement rule. |
| 2026-09-04 | User, from the running app | The 2D/3D preview ran off the bottom of the window, and the box floor rendered white instead of its real colour. `.app-shell` only set a `min-height`, so its `.workspace` grid child (and the `<canvas>` reading its own bounding box back into its `width`/`height` attributes) inflated in a feedback loop - measured live at 2205px against a 720px viewport. Fixed with a firm `.app-shell` height and `min-height: 0` on the grid children. | No. Nothing in the suite renders the page or measures layout; this only showed up looking at the running browser. |
| 2026-09-04 | User, from the running app | Switching print mode "doesn't change" the preview. Traced live (calling `kindColor()` directly in the page) to a real but too-subtle 30% colour blend toward the insert tint - working, not visibly working. Raised `INSERT_TINT_MIX` to 0.5. | No. Colour-blend amount is a visual judgement call, not something a unit test asserts a threshold for. |
| 2026-09-04 | Claude, reviewing the layout during the same pass | The mode-help caption sat under a negative top margin shared with the field-help caption above it, so the two overlapped whenever both were present. | No. Nothing in the suite checks rendered caption positions. |

## Reading the pattern

Four runs, nothing caught; one real defect, found by using the app. That is one
session, not a pattern — but it is the shape of evidence to watch. Two things
worth noticing before drawing a conclusion:

- A suite that finds nothing during *additive* work is behaving normally. The
  fingerprint tests exist to fail on the day someone changes wall geometry by
  accident, which has not happened yet in this log.
- The one defect that did land came from a test asserting the current behaviour
  was correct. Tests that pin behaviour cannot question it. That is an argument
  for fewer, more sceptical tests — not necessarily for fewer runs.
