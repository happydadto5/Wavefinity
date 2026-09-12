# B4B UI Cleanup — Exact Execution Plan

## Scope

This is a focused B4B UI/state cleanup. Do **not** redesign B4B geometry, hardware, hinge/latch/handle mechanics, stacking geometry, or saved-file schema unless explicitly called out below.

The goal is to make B4B controls simpler, denser, and more truthful while preserving the current working geometry.

---

# 1. Required user-visible changes

Implement all of the following.

1. **B4B dimensions are explicitly inside dimensions.**
   - In B4B mode rename the three dimension labels to:
     - `Width (Inside)`
     - `Length (Inside)`
     - `Height (Inside)`
   - In normal-bin mode restore the existing labels:
     - `Width`
     - `Length`
     - `Height`

2. **Do not change B4B height semantics.**
   - A user-entered B4B height of `40 mm` already means the case accepts a child bin up to `40 mm` high.
   - Keep that behavior exactly.
   - The lid headroom is added above the child capacity; do not subtract base, lid, hardware, or headroom from the entered height.

3. **B4B wall/base controls have no Standard checkboxes.**
   - While B4B is selected:
     - hide `Standard walls`
     - hide `Standard base`
     - always show `Wall thickness`
     - always show `Base thickness`
   - Keep both Standard checkboxes for ordinary bins.

4. **Base thickness becomes a dropdown everywhere.**
   Replace the current numeric Base thickness input with a `<select>`.

   Normal preset choices, in this exact order:
   - `0.4 mm — Very thin`
   - `0.6 mm — Good` **default**
   - `0.8 mm — Heavy`
   - `1.0 mm — Extra Heavy`
   - `1.2 mm — Maximum`

   These same normal presets are available to ordinary bins when `Standard base` is unchecked.

5. **Do not break ordinary-bin stacking when converting Base thickness to a dropdown.**
   Current ordinary stack modes require bases thicker than the normal preset list:
   - lid stacking: 1.8 mm minimum
   - direct stacking: 3.8 mm minimum

   Therefore the Base thickness select must support mode-required values dynamically.

   When ordinary stacking is active:
   - append the required value if it is not already present
   - label it clearly, for example:
     - `1.8 mm — Required for lid stacking`
     - `3.8 mm — Required for direct stacking`
   - force/select at least that value
   - prevent choosing a lower value while stacking is active
   - preserve the existing visible truth-in-UI behavior from `stackfix`

   Do not change stacking geometry or height semantics in this cleanup.

6. **Do not silently thicken a stackable B4B base.**
   Current B4B stacking requires:
   - 2.0 mm underside recess
   - 0.8 mm printable floor skin
   - therefore 2.8 mm minimum effective base

   When B4B `Stacking = Stackable`:
   - append/select `2.8 mm — Required for stacking`
   - save the actual 2.8 mm base thickness in the design
   - do not leave the visible control at 0.6/0.8/1.0/1.2 while the backend generates 2.8

   When switching from non-stackable to stackable, remember the previous non-stack base selection for the current browser session. If stacking is switched back off, restore that value. If there is no remembered value, restore 0.6 mm.

   Saved legacy/custom values that are not one of the presets must still reopen correctly by inserting a temporary `X mm — Saved/custom` option.

7. **Keep the current B4B wall rules.**
   - B4B minimum/default wall remains 1.2 mm.
   - Continue using the existing B4B wall presets from the catalog.
   - Do not allow B4B below 1.2 mm.
   - B4B wall thickness remains explicit/user-visible because the Standard Walls checkbox is hidden in B4B mode.

8. **Split B4B into two visual boxes: Options and Information.**

   The B4B panel should contain two distinct bordered cards:
   - `Options`
   - `Information`

   Do not mix the informational size/BOM readout into the options controls.

9. **Make B4B options compact and three columns wide where possible.**

   Use a three-column B4B options grid.

   Recommended exact layout:

   Row 1:
   - Name
   - Wall thickness
   - Base thickness

   Row 2:
   - Lid type
   - Lid snugness
   - Stacking

   Row 3:
   - Carrying handle
   - handle-unavailable notice when needed
   - Label

   Row 4, conditional:
   - Label text, shown only when Label is Top or Front; it may span two columns.

   Make the B4B select controls visibly more compact than the ordinary large form controls:
   - smaller vertical padding
   - approximately 11.5–12 px select text
   - 3 px top margin is enough
   - retain normal readable labels

10. **Add a B4B Name field.**

   Do not add a new B4B data-model field.

   Wavefinity already has the design-level `part_name`. Reuse it.

   - Add a B4B `Name` input in the B4B Options card.
   - It reads/writes the same `design.part_name` as the existing ordinary Part name field.
   - While B4B is active, hide the existing lower/output-panel Part name row so there are not two visible name controls.
   - While an ordinary bin is active, hide the B4B Name input with the rest of the B4B panel and show the existing Part name row normally.
   - Keep `checkPartNamePresent()` behavior unchanged conceptually: B4Bs still require a name before generation/printing.
   - Ensure label-text auto-seeding of a blank part name also updates the B4B Name field when B4B is active.

11. **Stacking becomes a dropdown.**

   Replace the B4B stacking checkbox with:

   Label: `Stacking`

   Options:
   - `Not stackable` — value false/default
   - `Stackable` — value true

   Keep the existing `B4BSpec.stacking` boolean. This is a UI mapping only; no schema change.

12. **Carrying handle becomes a dropdown.**

   Replace the B4B carrying-handle checkbox with:

   Label: `Carrying handle`

   Options:
   - `No handle` — false/default
   - `Add handle` — true

   Keep the existing `B4BSpec.handle` boolean. No schema change.

13. **Handle unavailable state becomes much clearer.**

   Continue using the backend preview's authoritative:
   - `handle_available`
   - `handle_blocked_reason`

   Do not duplicate the geometry eligibility calculation in JavaScript.

   When the handle is unavailable:
   - force the select to `No handle`
   - disable the handle select
   - put a visible strike/slash through the `Carrying handle` label text
   - show the blocked reason immediately **to the right** of the handle control
   - blocked-reason text must be bold and dark/black (`var(--ink)`), not muted gray

   Use the same presentation for another genuine blocker such as Lid Only requiring a secure lid, but the important case is a B4B below the handle size minimum.

14. **Label becomes one dropdown.**

   Remove the separate `Add label` checkbox + `Label location` control.

   Replace them with one select:

   Label: `Label`

   Options:
   - `No label` — default
   - `Top`
   - `Front`

   Behavior:
   - `No label`: hide Label text and save `label_text=""`
   - `Top`: show Label text and save `label_location="top"`
   - `Front`: show Label text and save `label_location="front"`
   - Preserve typed-but-hidden label text in the input for the current browser session when the user temporarily switches to No label, matching the useful behavior of the current UI.

   Keep existing `label_text` and `label_location` data fields; no schema change.

15. **Simplify the Information card.**

   Current readout shows separate lines for inside capacity, case body outside, assembled envelope, and maximum child height. Remove the unnecessary lines.

   The Information card should show:

   **Line 1 — Inside capacity**

   Combine width, length, and height on one line:

   `Inside capacity: 80 × 64 × 40 mm — 10 × 8 units`

   Notes:
   - width/length are the existing B4B capacity mm
   - height is the existing `max_child_height_mm`
   - units remain only a width × length concept; do not invent a Z unit count
   - do not use the word `Maximum`

   Remove completely from the B4B UI:
   - `Case body outside`
   - `Complete assembled envelope`
   - separate `Maximum bin height`

   The backend may continue returning those numeric fields if other code/tests use them. This request is to remove them from the user readout, not to break downstream API consumers.

16. **Hardware is one clean line.**

   Do not tell the user how many latches exist; they can see the latches.

   Display one concise line containing all required purchased hardware, grouped by screw size/length, for example:

   `Hardware: 4 M2 × 8 mm, 2 M2 × 10 mm — no nuts`

   Requirements:
   - merge identical screw lengths exactly as the current `groupB4BHardware()` already does
   - include hinge, latch, catch, and handle screws when applicable
   - do not prefix with `1 latch`, `2 latches`, `handle`, etc.
   - include `no nuts` when appropriate
   - if no purchased hardware is needed, show `Hardware: None`

17. **Keep actionable warnings in Information.**

   `#b4b-grew` / validation notices still belong in the Information card.

   After this cleanup a normal new stackable B4B should not need a "base thickened" warning because the required 2.8 mm value is visible and saved directly. Keep compatibility handling for old/saved designs, but do not show redundant warnings when the UI has already normalized the value.

---

# 2. Current-code review and what must change

## `web/index.html`

Current state:
- dimensions share ordinary labels; Height has no dedicated label span
- Standard base/walls controls live outside the B4B panel
- Base thickness is a numeric input
- B4B readout includes outside/envelope/max-height lines
- B4B stacking, handle, and label enablement use checkboxes
- B4B options are vertically stacked
- no B4B-local Name control

Required changes:

1. Add `id="z-size-label"` around the Height label text, matching X/Y label spans.
2. Replace `#base-thickness` number input with a select.
3. Restructure `#b4b-panel` into two child cards:
   - Options
   - Information
4. Add `#b4b-part-name`.
5. Replace:
   - `#b4b-stacking` checkbox -> select
   - `#b4b-handle` checkbox -> select
   - `#b4b-label-enabled` + `#b4b-label-location` -> single label select, preferably keep id `#b4b-label-location` only if that avoids unnecessary code churn; values must be `none/top/front`
6. Keep `#b4b-label-text` but make it conditional on label dropdown != `none`.
7. Remove the outside/envelope/separate-height DOM lines from the visible B4B card.
8. Put `#b4b-handle-note` in the grid cell immediately right of Carrying handle.
9. Preserve IDs that are useful where doing so reduces JS churn, but do not preserve obsolete checkbox-only semantics just to save a few lines.

## `web/styles.css`

1. Change `.b4b-panel` to be a simple container for two cards rather than one large card.
2. Add card styles for Options and Information.
3. Add `.b4b-options-grid` with three equal/minmax columns.
4. Add compact B4B select/input styling.
5. Add unavailable-handle styling:
   - struck-through/slashed handle label text
   - bold dark note
6. Information card remains compact; capacity is the primary bold line and hardware is one secondary line.
7. Keep responsive behavior reasonable: if sidebar becomes too narrow, allow the three-column grid to wrap/fall back rather than overflow.

## `web/app.js`

This is the main implementation file.

### A. Dimension labels
In `applyB4BVisibility()` set:
- B4B on: `Width (Inside)`, `Length (Inside)`, `Height (Inside)`
- B4B off: `Width`, `Length`, `Height`

Do not change dimension values.

### B. Base choices
Add a `populateBaseChoices(box, select)` helper analogous in spirit to `populateWallChoices()`.

Normal choices come from catalog base rules, not duplicated literals if possible.

The helper must also handle:
- ordinary lid/direct stack required minimums
- B4B stacking 2.8 mm minimum
- legacy/custom saved values

### C. Standard control visibility
In B4B mode:
- hide the `Standard base` label
- hide the `Standard walls` label
- show both thickness selects
- write `standard_base=false` and `standard_walls=false` into the visible/saved B4B design

In normal mode:
- existing Standard checkbox behavior remains

Do not alter ordinary-bin Easy Clean or stacking dependency behavior beyond what is needed for the new Base select.

### D. B4B stacking base normalization
Add one small B4B-specific UI normalization helper, e.g. `normalizeB4BBaseForStacking()`.

When stacking transitions false -> true:
- remember current non-stack base selection in session/client state
- set base to at least catalog B4B stack minimum (2.8)
- repopulate/select required option

When true -> false:
- restore remembered non-stack value or 0.6
- repopulate normal base choices

The Python backend remains a defensive safety net, not the primary place where the user discovers the floor changed.

### E. B4B Name
- `syncB4BForm()` copies current `state.design.part_name` into `#b4b-part-name`
- B4B Name input updates the existing `#part-name` value and `design.part_name`
- ordinary `#part-name` row is hidden while B4B is active
- `seedPartNameFromLabel()` updates both controls when seeding a blank name

Do not create `b4b.name`.

### F. Dropdown mappings
Update `syncB4BForm()` and `readB4BForm()`:

Stacking:
- select `not_stackable` / `stackable`
- map to boolean `b4b.stacking`

Handle:
- select `none` / `handle`
- map to boolean `b4b.handle`
- preserve secure-lid requirement

Label:
- select `none` / `top` / `front`
- `none` writes blank `label_text`
- top/front write existing location values

No `B4BSpec` field additions.

### G. Handle unavailable state
Refactor current checkbox logic in `applyB4BVisibility()` to select logic.

Continue to call `b4bHandleBlockedReason()`.

If blocked:
- value = no handle
- disable select
- add unavailable CSS class to handle label
- show bold dark note at right

If available:
- enable select
- remove unavailable class
- hide note

### H. Readout
Rewrite `renderB4BReadout()`.

New capacity line:
`Inside capacity: {capacity_mm_x} × {capacity_mm_y} × {max_child_height_mm} mm — {units_x} × {units_y} units`

Remove assignments/references for:
- case outside line
- assembled envelope line
- separate child-height line

Hardware:
- use grouped screw list only
- no latch count prose
- append `— no nuts` when hardware.nuts === 0
- `Hardware: None` when nothing is needed

Retain warning/problem display.

### I. Event wiring
Replace checkbox listeners with select `change` listeners.

Ensure changes call the existing sequence needed to keep preview/state current:
- normalize dependent controls
- read B4B form
- enforce B4B minimums
- apply visibility
- changedDesign()

Add `input` handling for `#b4b-part-name` and label text.

Update `mutationControls()` so the new B4B selects/name control are disabled during design mutations just like other design controls.

---

# 3. Python/catalog changes

## `organizer_engine.py`

Add a central base preset tuple so labels/values are not hardcoded only in JavaScript:

```python
BASE_PRESETS = (
    (0.4, "Very thin"),
    (0.6, "Good"),
    (0.8, "Heavy"),
    (1.0, "Extra Heavy"),
    (1.2, "Maximum"),
)
```

Keep:
- `DEFAULT_BASE_THICKNESS = 0.6`
- existing base validation

Do not change box geometry.

## `organizer_b4b.py`

Geometry behavior stays unchanged.

Make the existing stack base requirement explicit as one reusable constant/helper if needed for catalog/UI truth, e.g.:

`B4B_STACK_MIN_BASE = B4B_STACK_RECESS_DEPTH + B4B_MIN_FLOOR_SKIN`

Use that same value inside `b4b_effective_base_thickness()` rather than duplicating the expression.

Preserve `b4b_max_child_height()` exactly: the selected B4B height is the child capacity height.

Do not remove existing summary numeric fields solely because the UI no longer displays them; other code may consume them.

Optional cleanup: `max_child_height_text` and the old formatted outside/envelope convenience strings may remain for compatibility. The browser should simply stop using them.

## `wavefinity_web.py`

Expose catalog data needed by the browser:

```text
base_rules:
  default_mm: 0.6
  choices: BASE_PRESETS

b4b_rules:
  ...existing rules...
  stack_min_base_mm: 2.8
```

Keep current ordinary stack rules and B4B wall rules intact.

---

# 4. Saved-design compatibility

No B4B schema bump is needed.

Do not add new persisted B4B fields for UI-only choices.

Existing saved fields remain authoritative:
- `design.part_name`
- `box.wall`
- `box.base_thickness`
- `box.standard_walls`
- `box.standard_base`
- `b4b.secure_lid`
- `b4b.lid_headroom_mm`
- `b4b.stacking`
- `b4b.handle`
- `b4b.label_text`
- `b4b.label_location`

Old saved designs with arbitrary valid base thicknesses must reopen without losing their value. Add a temporary custom select option when necessary.

---

# 5. Focused tests only

Do not run or expand unrelated geometry matrices for this UI cleanup.

Update/add only focused tests needed to protect the changed contract.

## `test_b4b.py`

Add/retain an explicit semantic test:

- B4B `z=40` -> `b4b_max_child_height(box) == 40`
- changing lid snugness does not change that 40 mm capacity
- stacking base minimum is exactly 2.8 mm

Do not alter geometry tests unrelated to these facts.

## `test_wavefinity_web.py`

Add focused catalog/static-UI contract checks:

1. `base_rules` exposes exactly:
   - 0.4 Very thin
   - 0.6 Good
   - 0.8 Heavy
   - 1.0 Extra Heavy
   - 1.2 Maximum
2. default base is 0.6
3. B4B stack minimum base is 2.8
4. HTML contains:
   - B4B Options box
   - B4B Information box
   - B4B Name control
   - B4B stacking select
   - B4B handle select
   - label select with none/top/front
   - Height label span/id
5. obsolete B4B readout text is gone from `index.html`:
   - `Case body outside`
   - `Complete assembled envelope`
   - `Maximum bin height`
6. JS contains one base-choice population path rather than treating base as a free numeric input.

## `test_stack.py`

Only adjust what is necessary because `#base-thickness` changed from an input to a select.

Preserve assertions that ordinary lid/direct stacking visibly enforces 1.8/3.8 mm rather than silently generating those values.

---

# 6. Acceptance checklist

Do a final pass against every item below before declaring done.

- [ ] Normal bin still shows Standard base checkbox.
- [ ] Normal bin still shows Standard walls checkbox.
- [ ] Normal base custom control is now a dropdown with 0.4/0.6/0.8/1.0/1.2 presets.
- [ ] 0.6 is the normal base default.
- [ ] Ordinary lid stacking still visibly forces/offers 1.8 mm.
- [ ] Ordinary direct stacking still visibly forces/offers 3.8 mm.
- [ ] B4B hides both Standard checkboxes.
- [ ] B4B always shows Wall thickness and Base thickness.
- [ ] B4B wall cannot go below 1.2 mm.
- [ ] B4B non-stack base defaults to 0.6 mm.
- [ ] B4B stackable mode visibly saves/selects 2.8 mm base.
- [ ] Turning B4B stacking off restores the user's prior non-stack base or 0.6 fallback.
- [ ] B4B dimensions read Width (Inside), Length (Inside), Height (Inside).
- [ ] A 40 mm B4B still reports 40 mm child capacity height.
- [ ] B4B has a visible Name field backed by existing `part_name`.
- [ ] Duplicate lower Part name row is hidden while B4B is active.
- [ ] Lid type / Lid snugness / Stacking fit three across.
- [ ] Stacking is a dropdown defaulting to Not stackable.
- [ ] Carrying handle is a dropdown defaulting to No handle.
- [ ] Handle unavailable state is disabled, visibly struck/slashed, with bold dark reason immediately to its right.
- [ ] Label is one dropdown: No label / Top / Front.
- [ ] Label text appears only for Top or Front.
- [ ] Information is a separate card from Options.
- [ ] Inside capacity is one line with X × Y × height plus X × Y units.
- [ ] No separate "Maximum" height line.
- [ ] No Case body outside line.
- [ ] No Complete assembled envelope line.
- [ ] Hardware is one line and does not state latch count.
- [ ] Hardware line includes all required screws and no-nuts status.
- [ ] No B4B geometry/hardware redesign was introduced.
- [ ] Existing saved B4Bs reopen with the same geometry/settings.

---

# 7. Files expected to change

Primary:
- `web/index.html`
- `web/app.js`
- `web/styles.css`

Small supporting changes:
- `organizer_engine.py` — base preset source of truth
- `organizer_b4b.py` — expose/reuse 2.8 mm stack base minimum; no geometry redesign
- `wavefinity_web.py` — catalog base/B4B rules

Focused tests:
- `test_b4b.py`
- `test_wavefinity_web.py`
- `test_stack.py` only where the Base select affects current UI-contract checks

Do not touch unrelated B4B hardware geometry, direct stacking geometry, interior-feature code, drawer layout, or connector geometry.

---

# Final implementation guidance

This is intentionally a straightforward UI/state cleanup. Prefer small helpers and one source of truth over new abstractions.

The two rules most likely to be accidentally broken are:

1. **B4B Height is already inside child capacity height. Do not recalculate it.**
2. **A dropdown capped at 1.2 mm cannot replace the current base input unless stack-required 1.8/2.8/3.8 mm values are dynamically represented and saved.**

Everything else is presentation and mapping existing booleans/fields to cleaner controls.
