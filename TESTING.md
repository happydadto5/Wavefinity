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

## Defects found outside the suites

| Date | Found by | Defect | Would a test have caught it? |
|---|---|---|---|
| 2026-09-03 | User, from the running app | The preview called a divider at the centre of a scooped bin "invalid". The scoop reserved its whole run as a keep-out, including the tangent lip that stands 0.03 mm off the floor. | No. The suite asserted the keep-out *equalled* the scoop's run, so it locked the bug in rather than catching it. Now covered by `test_the_scoop_only_reserves_the_floor_it_actually_lifts`. |
| 2026-09-03 | User, from the running app | Switching between fused and removable changed nothing visible in the preview. The insert's base plate was drawn as the bare layout rectangle, flush to the wall and 4% off the floor's colour. | No. Nothing compared the two forms, and nothing tied the drawn plate to the exported one. Now covered by `InsertFormPreviewTests`. |
| 2026-09-03 | User, from the running app | The nest's "Recess" box was blank and typing in it changed nothing on screen. Options left unset were resolved inside each builder, so the editor had no number to show and no feedback when a value was refused. | No. The suite only ever built holders from explicit options, so it never saw a blank field. Now covered by `ResolvedOptionTests`. |
| 2026-09-03 | User, from the running app | Delete did nothing with a part highlighted. Not reproducible through any input path, but the action returned silently whenever its own record of the selection was unset - indistinguishable from a broken button. | No, and it still would not: the failure needs the two selection records to disagree. The fallback and the "pick a part first" reply are covered by `DesktopUiTests`. |
| 2026-09-03 | User, from the running app | Parameter leader lines crossed each other on the diagram. | No. `PartDiagramTests` checked that every parameter had an anchor, not that the drawing was readable. A crossing check now runs against the live canvas during review; `CalloutLayoutTests` pins the placement rule. |

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
