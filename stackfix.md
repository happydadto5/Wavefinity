# Stackable Bins Review and Fix Plan

## Purpose

Review the current ordinary-bin stacking implementation and define the corrections required before it should be considered complete.

This document is implementation guidance for an LLM. It is not a request for broad refactoring. Keep the work isolated to stacking geometry, the stacking-related bin settings, serialization/preview text, and focused tests.

## Required product behavior

1. Ordinary bins have three stacking states:
   - `none`
   - `lid` — snap-in lid, next bin stacks on the lid
   - `direct` — bin snaps directly into the bin below
2. Stacking must remain support-free to print.
3. Direct snap requires at least a 1.2 mm wall.
4. Lid mode also requires at least a 1.2 mm body wall because the lid uses the same snap groove in the bin mouth.
5. Selecting either stacking mode must visibly change the actual user settings rather than silently generating a different effective model:
   - uncheck `Standard walls`
   - expose `Wall thickness`
   - set it to at least 1.2 mm
   - do not allow a stacking design to be reduced below 1.2 mm
   - preserve a user-selected value above 1.2 mm while stacking remains enabled
6. Turning stacking back to `none` must restore normal defaults:
   - `Standard walls` checked
   - wall thickness back to 0.8 mm
   - hide the custom wall selector
7. Any stacking-required base-thickness change must follow the same truth-in-UI rule. Do not silently print a much thicker base while the visible form still says `Standard base`.
8. Lid thickness is not the same setting as body wall thickness. Validate the lid independently so its plate, recess floor, plug and snap have adequate printable material.
9. The user's requested height includes the lid contribution. The stack-height requirement must not be contradicted by the UI or summary.

---

# Review findings

## 1. HIGH: Current height semantics contradict the requested stack height

Current code:

- `stack_closed_height(box)` returns the requested Z.
- `stack_pitch(box)` returns `stack_closed_height(box) - stack_step_depth(box)`.
- `stack_step_depth` is 3.0 mm for direct mode and 1.0 mm for lid mode.

Therefore a requested 50 mm bin currently reports/behaves as:

- direct: 50 mm closed height, 47 mm stack pitch
- lid: 50 mm closed height, 49 mm stack pitch

The current test `StackHeightTests.test_pitch_is_shorter_than_the_bin_by_its_engagement` deliberately locks this behavior in.

This directly conflicts with the new requirement that two nominal 50 mm stack modules should contribute 100 mm total stack height.

### Important geometry constraint — do not hide this with a math-only change

A positive snap or locating step that physically overlaps the bin below creates vertical engagement. With identical rigid bins, it is geometrically impossible for all three statements to be literally true at the same time:

1. detached physical bounding height of every bin is exactly H,
2. each identical bin overlaps the one below by depth D > 0,
3. N stacked bins have total physical height exactly N × H.

Current geometry chooses (1) and (2), therefore stack pitch is H-D.

### Recommended product interpretation

Treat the user-entered height as the **stack module/pitch**, including any lid contribution. That makes 50 + 50 = 100 in an assembled stack, which is the user's explicit operational requirement.

However, do not falsely claim the detached STL bounding box is also exactly 50 mm if engagement geometry makes it taller. If literal detached bounding height must also remain exactly 50 mm, the current overlapping plug/step concept must be replaced by a zero-overlap/separate latching concept; changing `stack_pitch()` alone would create collisions.

Implementation must choose one coherent datum and use it everywhere. Recommended priority is exact assembled stack pitch because that is the explicit acceptance criterion.

Update comments, preview copy, tests, inventory assumptions, and any filename/reporting semantics so they all describe the same definition.

## 2. HIGH: Wall thickness is silently changed in the backend but not in the form

`stack_effective_box()` currently does:

- `wall = max(box.wall, STACK_MIN_WALL)`
- `STACK_MIN_WALL = 1.2`
- returns a replaced BoxSpec with `standard_walls=False`

That protects generated geometry, but it is hidden from the user's actual design state.

The browser's `readStackForm()` only changes/deletes `box.stack`. The stack-mode change handler does not change `standard_walls` or `wall`.

Result: the form can still show `Standard walls` / 0.8 mm while the backend actually previews/prints 1.2 mm.

That is not acceptable because saved design intent, UI state, preview summary, and generated geometry disagree.

### Required correction

On stack-mode transition from `none` to `lid` or `direct`:

- set `design.box.standard_walls = false`
- if current wall < 1.2, set `design.box.wall = 1.2`
- update `#standard-walls` to unchecked
- expose `#wall-thickness-setting`
- constrain/disable wall choices below 1.2 while stacking is active
- show a short dependency note such as `Stacking requires at least 1.2 mm walls.`

On stack-mode transition to `none`:

- set `design.box.standard_walls = true`
- set `design.box.wall = DEFAULT_WALL` (0.8)
- check `#standard-walls`
- hide the custom wall selector
- restore the normal full wall-choice range for the next custom-wall use

Do not keep a hidden backend clamp as the primary behavior. A final defensive clamp/validation may remain, but the saved/user-visible design must already be legal.

## 3. HIGH: Base thickness is also silently changed

`stack_effective_box()` currently forces minimum base thickness to:

- direct: `3.0 + 0.8 = 3.8 mm`
- lid: `1.0 + 0.8 = 1.8 mm`

It also sets `standard_base=False` only on the temporary effective BoxSpec.

The visible design can therefore say `Standard base` / 0.6 mm while the generated stack body is much thicker.

### Required correction

First decide whether the redesigned support-free stack foot still requires these floor values.

If a raised minimum is still required:

- reflect it in `state.design.box.base_thickness`
- uncheck `Standard base`
- expose the base thickness control
- enforce the stacking minimum in the UI and backend
- on stacking `none`, return to standard base 0.6 mm unless another non-stacking feature independently requires a custom base

Do not preserve the current hidden 0.6 -> 3.8 mm mutation.

## 4. MEDIUM/HIGH: Lid mode fits in code and has an assembled test, but direct mode lacks an equivalent assembly test

Lid mode currently has useful focused geometry verification:

- lid seated in body has negligible intersection
- partially inserted lid has intentional snap interference
- an upper bin placed at current lid stack pitch does not foul the lid/body

Direct mode has only plan-outline clearance checks. There is no matching test that actually places one generated direct-mode body into another and verifies:

- seated body-to-body collision is effectively zero except intended snap contact
- bead aligns vertically with the lower groove
- partial insertion produces intentional interference
- the upper bin reaches the intended seating datum

The formulas appear internally aligned, but lack of an assembled direct test means this should not be declared proven.

### Required correction

Add a focused direct-stack assembly test using two generated bodies. Use actual mesh intersection volume and explicit Z placement. This should be a small targeted test, not a broad randomized test suite.

## 5. MEDIUM: Lid and direct modes are not cross-compatible as stack interfaces

The module language suggests a broadly shared interlock, but the actual stack interfaces differ:

- direct upper bin has a 3 mm stepped base plus snap bead
- lid-mode upper bin has a 1 mm locating step and no base snap bead
- lid top seat is only 1 mm deep

Consequences:

- a direct-mode bin cannot sit flush in the 1 mm lid recess; its 3 mm foot/bead conflicts
- a lid-mode bin placed directly into a direct lower bin does not have the required base bead/depth to snap into the mouth groove

If the product only promises same-mode stacks, explicitly encode/document that and test it.

If the product promise is that any stackable bin can mix lid/direct within one stack, redesign around one common bottom interface and one common receiving interface. Do not assume current geometry provides this.

## 6. HIGH: Current snap/base geometry is not cleanly support-free by design

The current stack foot is made by subtracting a vertical outer shell for the first `step` millimetres and then returning abruptly to the full outside wall. That creates a horizontal outward shoulder at the top of the inset foot.

The current snap bead is also a rectangular Z extrusion that appears abruptly from the plug surface.

Those are exactly the kinds of underside ledges that can become unsupported perimeter overhangs when the body is printed base-down.

The lid has the same rectangular snap bead, and the plug-to-full-plate transition also needs a deliberate print orientation and support-free transition.

### Required geometry correction

Official print orientations:

- bin body: base/stack foot down
- stacking lid: plug down

Then make every growing outward surface printable at <=45 degrees:

### Body foot

Replace the abrupt foot-to-full-body shoulder with a 45-degree-or-shallower transition above the insertion zone. The portion that enters the lower bin must remain entirely inside the receiving cavity; the flare to full outside width begins only after the seating/rim datum.

Do not simply chamfer into the mating region and create a collision.

### Snap bead

Replace rectangular bead cross-section with a printable wedge/teardrop profile:

- lower/insertion face ramps outward at <=45 degrees
- maximum protrusion still provides the required snap interference
- upper/release shoulder can return inward sharply because shrinking inward on subsequent layers is supported by the layer below

### Receiving groove

Do not leave a rectangular internal groove with an unsupported upper ceiling if strict support-free printing is required. Use a complementary printable V/teardrop/chamfered groove profile while preserving enough retention.

### Lid underside

When printing plug-down, the lid cannot jump horizontally from the narrow plug to the full plate. Add a <=45-degree underside flare above the seating rim datum. Keep it above the body rim so it does not foul the receiving bin.

The top seat/recess is on the upward-facing side in this print orientation and is acceptable as a recess; ensure its remaining skin is adequate.

## 7. MEDIUM/HIGH: Full-perimeter 0.30 mm snap interference is mechanically aggressive

Current `_bead_band()` makes essentially a continuous perimeter snap bead with `STACK_SNAP = 0.30` mm.

A continuous bead around a large wavy perimeter forces a large amount of wall/plug to flex at once. Mesh intersection proves interference exists; it does not prove insertion force, durability, or release force are reasonable.

### Recommended correction

Prefer segmented snap detents rather than a continuous full-perimeter bead:

- use symmetric segments on each usable side
- keep clear of corners
- size segment count/length by bin size
- use the same printable ramp profile
- keep locating geometry continuous if needed, but keep the actual retaining interference intermittent

If the existing continuous bead is retained, explicitly treat it as an unverified mechanical risk and do not claim the snap is production-ready solely from boolean-geometry tests.

## 8. MEDIUM: Preview text currently exposes the height inconsistency instead of enforcing one rule

Current UI text reports both:

- `Finished bin X mm tall — exactly the height you set.`
- `Each bin adds Y mm to a stack.`

where Y is smaller than X.

Once height semantics are corrected, the preview should expose one simple rule, for example:

`Stack height contribution: 50 mm including lid.`

Optional secondary technical text may show engagement depth, but do not present two competing meanings of the user's Height field.

---

# Implementation plan

## Phase 1 — Make stack requirements explicit in the model

Files:

- `organizer_stack.py`
- `organizer_engine.py` only if the StackSpec needs a small additional semantic/helper

Tasks:

1. Define one documented stack Z datum.
2. Make one authoritative helper for requested stack module height/pitch.
3. Remove the current semantic contradiction between module docstring, `stack_closed_height`, `stack_pitch`, and tests.
4. Preserve lid contribution inside the requested module height.
5. Do not change pitch mathematically without also changing geometry placement; otherwise direct/lid parts will collide.
6. Keep backend validation for wall/base minimums as a safety net even after the UI writes valid values.

### Acceptance

For a nominal 50 mm design, the chosen product definition must result in exactly 50 mm contribution per stacked module, so two modules add 100 mm according to the same assembly datum.

If literal detached STL bounding height = 50 mm is also demanded, stop and redesign the interlock concept rather than falsifying measurements.

## Phase 2 — Correct wall/base dependency behavior in the browser

Files:

- `web/app.js`
- possibly `web/index.html` for one short dependency note
- `wavefinity_web.py` only if catalog data should expose `stack_min_wall` / stack base minimums instead of duplicating numbers in JavaScript

Tasks:

1. Add a single stack-settings normalization function called whenever stack mode changes and when a design is opened/synchronized.
2. For `lid` or `direct`:
   - force `standard_walls=false`
   - clamp wall to >=1.2
   - expose custom wall selector
   - disallow choices <1.2
3. For `none`:
   - force `standard_walls=true`
   - wall=0.8
   - hide custom wall selector
4. Apply corresponding visible base behavior if the final geometry still requires a raised base minimum.
5. Do not let the normal `Standard walls` change handler create an illegal stacking state.
6. Save the actual values that the user sees. Reopening a design must reproduce the same controls without relying on `stack_effective_box()` to silently repair it.

## Phase 3 — Redesign stack mating geometry for support-free printing

File:

- `organizer_stack.py`

Tasks:

1. Replace abrupt foot shoulder with support-free transition.
2. Replace rectangular bead with printable ramped profile.
3. Replace/modify rectangular groove to avoid unsupported internal ceiling.
4. Make lid plug-down printable with a support-free plug-to-plate flare.
5. Keep all mating XY clearances derived from shared helpers so the lid plug, direct plug, groove and seat cannot drift independently.
6. Re-evaluate whether the current 3.8 mm direct base and 1.8 mm lid-mode base are still necessary after geometry redesign.
7. If retaining a large base minimum, expose it in the user settings as described above.
8. Prefer segmented snap detents over a continuous full perimeter bead unless there is a deliberate reason not to.

## Phase 4 — Decide and enforce same-mode versus mixed-mode compatibility

Recommended default: promise and validate `lid-with-lid` stacks and `direct-with-direct` stacks only unless mixed mode is an explicit product requirement.

If mixed mode is required:

- redesign to one common lower foot/interface for every stackable bin
- ensure that common foot works both in the lid seat and directly in a bin mouth
- use one common seating depth and datum
- add mixed-mode assembly tests

Do not claim current 1 mm lid seat and 3 mm direct foot are interchangeable.

## Phase 5 — Focused tests only

This change is geometry-heavy enough to justify targeted tests, but do not run or expand the entire project test suite as busywork.

Update `test_stack.py` and only the directly affected web/standard-wall tests.

Required focused tests:

1. requested stack pitch/height semantics, including the 50 + 50 = 100 acceptance case
2. lid seated fit
3. lid partial-insertion snap interference
4. lid-mode upper-bin stack seating
5. direct seated body-to-body fit
6. direct partial-insertion snap interference
7. snap bead/groove Z alignment
8. no mesh collision at final direct seating
9. stack mode enables visible wall >=1.2 / standard walls false
10. stacking off restores standard walls 0.8
11. stack design save/open retains the visible legal wall/base settings
12. support-free profile invariants: every deliberately outward-growing stack surface is <=45 degrees for its official print orientation

If mixed-mode stacking is promised, add direct-on-lid and lid-on-direct tests. Otherwise add a clear test/documented rule that mixed mode is not a supported assembly.

Do not add unrelated randomized geometry suites.

---

# Files expected to change

Primary:

- `organizer_stack.py`
- `web/app.js`
- `test_stack.py`

Likely secondary:

- `wavefinity_web.py`
- `web/index.html`
- `test_wavefinity_web.py`
- `test_standard_walls.py`
- `organizer_app.py` if reports/serialization assumptions about height need correction

Avoid unrelated changes.

---

# Final acceptance checklist

- [x] Stacking `none` produces the unchanged ordinary 0.8 mm standard-wall bin.
- [x] Selecting `lid` visibly switches the design to custom walls >=1.2 mm.
- [x] Selecting `direct` visibly switches the design to custom walls >=1.2 mm.
- [x] User cannot create/save a stacking design below 1.2 mm wall.
- [x] Turning stacking off restores standard walls at 0.8 mm.
- [x] Any required nonstandard base thickness is visible in the form and saved design.
- [x] Lid snaps into the receiving body with intended clearance/interference.
- [x] Lid top seat receives the intended upper-bin base without collision.
- [x] Direct upper bin seats into lower bin without unintended collision.
- [x] Direct snap bead and groove align in both XY and Z.
- [x] Body stack foot prints base-down without unsupported abrupt ledges.
- [x] Lid prints plug-down without unsupported abrupt ledges.
- [x] Snap bead/groove profiles are support-free by construction, not merely hoped to slice.
- [x] Height/pitch language is consistent in code, UI, tests, reports and saved design semantics.
- [x] Two nominal 50 mm stack modules contribute 100 mm according to the chosen stack datum.
- [x] Mixed-mode compatibility is either explicitly implemented/tested or explicitly not promised.

Implemented 2026-09-12. Compatibility is deliberately same-mode only: lid-on-lid and direct-on-direct.
