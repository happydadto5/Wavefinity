# Fix 011 — Connector Auto-Generation

FIRST: Sync your checkout with `origin/main` before reading this fix.

Implementation thread title: **Connector Auto-Generation Imp #11**

## Status / prerequisite

**READY TO IMPLEMENT. Fix 010 is merged into `main` and archived.**

Fix 010 and Fix 011 both touch `web/index.html`, `web/app.js`, and `test_wavefinity_web.py`, so implementation must begin from current `origin/main` containing Fix 010. Sync current `origin/main`, re-read this file against that code, and then create the Fix 011 implementation branch.

The product behavior in this file is decided. Adapt the patch to the merged Fix 010 code shape without changing this behavior.

---

## User intent

The current Connectors UI incorrectly treats **Side connectors** and **Base Trim** as mutually exclusive ways to join bins. They are not mutually exclusive physical choices, so that chooser should not exist.

The second chooser is also unnecessary. The user should not have to decide whether to generate Side, 3-Way Corner, or 4-Way Corner connectors.

New rule:

- **Same-height bins:** generate one Side connector, one 3-Way Corner connector, and one 4-Way Corner connector.
- **Different-height bins:** generate only the Side connector, because the corner connectors require equal-height bins.
- The user can delete any generated connector file they do not need.
- Base Trim remains its own separately generated part/design and is not a connector-vs-trim preference.

Existing physical connector restrictions remain valid, including same-wall-thickness requirements and the 16 mm X/Y minimum for corner connectors.

---

# Mandatory startup / branch workflow

1. Fetch and fast-forward local `main` to current `origin/main`.
2. Confirm Fix 010 is merged into `main` before starting.
3. Confirm `/fixes/fix-011.md` exists on current `origin/main`.
4. Read this entire file plus current `README.md` and `AGENTS.md`.
5. Create branch exactly `fix11` from that current `origin/main` and push with upstream tracking.
6. Name the implementation thread exactly **Connector Auto-Generation Imp #11** if supported.
7. Do not edit `/fixes/Fix Master.md` on `fix11`; ChatGPT owns it on `main`.
8. Do not merge `fix11`. Push implementation/outbrief and stop for outside ChatGPT completion review.
9. If another merged fix changes these same files while `fix11` is active, merge current `origin/main` into `fix11`, resolve deliberately, rerun required tests, and have the resulting branch reviewed again.

---

# Part A — Remove the fake “connectors vs Base Trim” choice

## `web/index.html`

Delete the entire control:

```html
<label class="inline-select">Join bins with
  <select id="bin-join-mode">
    <option value="side">Side connectors</option>
    <option value="base_trim">Base Trim</option>
  </select>
</label>
```

Do not replace it with another connector/Base Trim selector.

Base Trim continues to be selected/generated through its existing Base Trim design flow. Ordinary bins can use connectors regardless of whether the user may also create Base Trim for the Space.

## `web/app.js`

Remove the user preference/state whose only purpose is that false exclusivity:

- `state.joinMode`
- `default_join_mode` preference loading/saving
- `persistJoinMode()`
- `#bin-join-mode` event wiring
- branches that suppress connectors merely because `state.joinMode === "base_trim"`
- `join_mode` from connector/print payloads

Do **not** remove Base Trim design state such as `lastBaseTrimDesign`, `baseTrimSourceLayout`, `baseTrimEnabled()`, or the existing Base Trim generation flow.

Where current code needs to know whether the *active design itself* is Base Trim, use the existing design-type check (`baseTrimEnabled()`) rather than a join preference.

Specific current anchors that must be corrected after syncing:

- `generateParts(target)` must no longer coerce `target === "all"` to bin-only because of `state.joinMode`.
- hosted `printModel()` must no longer use `state.joinMode === "base_trim"` as a reason to omit connectors.
- local print payloads must no longer send `join_mode`.
- `renderConnectorReadout()` must no longer hide itself based on `state.joinMode`.
- `syncJoiningControls()` should be removed/refactored rather than left as hidden dead behavior.
- Base Trim setup/toggle code should no longer persist a join preference.

It is still correct to hide connector controls while the active design is literally a Base Trim, B4B, or a bin configuration that does not support connectors (for example a lid), because there is no ordinary bin connector to generate from that active design. That is a design capability rule, not a Base-Trim-vs-connectors product choice.

---

# Part B — Remove connector-type and corner-quantity choices

## `web/index.html`

Delete:

```html
<label id="connector-type-row" class="inline-select">Connector type
  <select id="connector-type">
    <option value="side">Side</option>
    <option value="three_way">3-Way Corner</option>
    <option value="four_way">4-Way Corner</option>
  </select>
</label>

<label id="corner-connector-quantity-row" class="inline-select" hidden>Quantity
  <input id="corner-connector-quantity" type="number" min="1" max="20" step="1" value="1">
</label>
```

Keep the existing **Bin heights: Same / Different** control. That is now the only connector-mode choice the user needs.

## `web/app.js`

Remove browser state/UI logic that exists only to choose one connector type:

- `CONNECTOR_TYPES`
- `CONNECTOR_TYPE_NAMES`
- `normalizeConnectorType()`
- `connectorTypeNow()`
- `syncConnectorTypeControls()`
- `#connector-type` event listener
- `#corner-connector-quantity` event listeners
- writes to `state.connector.type`
- writes to `state.connector.quantity`

In `syncForm()`, do not read/write removed DOM elements.

In `updateDesignFromForm()`, connector state should be based on the height mode and existing Side/different-height geometry settings only. Target shape:

```js
state.connector = {
  tolerance: number($("#connector-tolerance").value, 0.02),
  height: number($("#connector-height").value, 9.6),
  length: number($("#connector-length").value, 12),
  arm_thickness: number($("#connector-arm-thickness").value, 1),
  bin_a_height: number($("#connector-bin-a-height").value, design.box.z),
  bin_b_height: number($("#connector-bin-b-height").value, design.box.z),
  different_heights: $("#connector-height-mode").value === "different",
  position: 0,
  axis: "y",
};
```

Use the exact current defaults/catalog-backed values already present in the merged code rather than introducing hard-coded defaults if the current implementation already resolves them another way.

### Connector readout

Replace type-specific readout with automatic behavior text:

- Same height: **“Generates Side, 3-Way Corner, and 4-Way Corner connectors. Connectors only fit bins with the same wall thickness.”**
- Different height: **“Generates a Side connector only. 3-Way and 4-Way Corner connectors require equal-height bins.”**

If current design dimensions are too small for corner connectors, add a non-blocking readout note that corner connectors require at least 16 mm in both X and Y.

### Generation dialog

When generating connectors:

- same-height row title: **Connectors (Side + 3-Way + 4-Way)**
- different-height row title: **Side Connector**

Do not add three user-selectable rows/check boxes. The point of this fix is to eliminate that decision.

---

# Part C — Make `/api/connector` generate the automatic bundle

## `wavefinity_web.py::connector_payload()`

Refactor this endpoint so the request no longer selects a connector type.

### 1. Remove obsolete exclusivity/type gates

Delete the `join_mode == "base_trim"` rejection.

Delete the logic that requires `connector.type` to be one of side/three_way/four_way.

Do keep capability rejection for:

- B4B
- lid-enabled bins
- an active design that is itself a Base Trim

For Base Trim, check the actual design type (for example the existing `_is_base_trim_design(payload["design"])`) and return a clear error such as:

`Connectors are generated from a bin design, not from a Base Trim design.`

### 2. Resolve common connector values once

Continue using the current payload values for:

- tolerance
- connector height
- arm thickness
- Side connector length
- different-height A/B heights

Preserve the current direct-stack physical-rim resolution.

### 3. Different-height request

When `different_heights == true`:

- generate exactly one Side connector using the existing mature Side path;
- generate no 3-Way or 4-Way connector;
- return a bundle/plan that explicitly lists only `side`.

Preserve all current different-height Side geometry, filename, auto-adjust/web behavior, and validation.

### 4. Same-height request

When `different_heights == false`:

Generate into the **same output directory**:

1. one Side connector;
2. one 3-Way Corner connector;
3. one 4-Way Corner connector.

Corner quantity is fixed at **1** for each automatically included corner file.

Reuse the existing production functions:

- `generate_side_file(...)`
- `generate_corner_file(... ways=3, quantity=1)`
- `generate_corner_file(... ways=4, quantity=1)`
- current filename helpers

Do not duplicate connector geometry and do not make three frontend API calls.

Recommended result shape:

```python
result = {
    "side": side_result,
    "three_way": three_way_result,
    "four_way": four_way_result,
}
```

and a connector plan conceptually like:

```python
{
    "mode": "auto",
    "types": ["side", "three_way", "four_way"],
    "different_heights": False,
    "wall_mm": ...,
    "requires_same_wall": True,
}
```

The existing `_generation_reply()` / `_extract_generated_files()` recursion can then expose all three files in hosted mode without a new download mechanism.

### 5. Existing 16 mm corner eligibility

The existing corner geometry requires at least 16 mm in both X and Y. Preserve that physical rule.

Do **not** let an ineligible corner abort a valid Side connector generation. If the active same-height bin is too small for corner connectors:

- generate the Side connector;
- omit the impossible corner files;
- return plan metadata/readout explaining that corners were skipped because they require at least 16 mm in X and Y.

Do not weaken `MIN_JOINABLE_SIZE` and do not invent new corner geometry in this fix.

### 6. Retire obsolete corner request helpers if no longer needed

After the automatic bundle is implemented, remove or fold away request-only helpers such as `_corner_quantity()` / `_corner_connector_payload()` if they have no remaining callers.

Keep lower-level organizer functions and filename helpers; they are still used to build the automatic bundle.

---

# Part D — Printing must receive the same automatic connector bundle

## `wavefinity_web.py::print_payload()`

The current print path appends one Side connector to an ordinary bin print and gates that behavior with `join_mode`.

Change it so:

- no `join_mode` validation exists;
- an ordinary supported bin print calls the new `connector_payload(payload)`;
- same-height bins therefore send Side + 3-Way + 4-Way files to Bambu Studio;
- different-height connector-only printing sends Side only;
- B4B, lid, and Base Trim designs remain excluded based on their actual design capabilities.

Update the comment that currently says the default bin print carries one Side connector.

Because `connector_payload()` returns a recursive multi-file result, continue using `_extract_generated_files()` rather than manually enumerating filenames.

---

# Part E — Frontend generation/save behavior

## `web/app.js::generateParts()`

Keep a single `/api/connector` request.

The current `saveGeneratedFiles(connResult)` and `collectOutputs()` already walk result structures recursively. Reuse them so all returned connector files save to the selected folder.

Do not make the browser call `/api/connector` three times.

Update generation completion/toast/readout code so it does not assume a single `connector_plan.type` or a single selected connector.

---

# Files expected to change

Normally:

- `web/index.html`
- `web/app.js`
- `wavefinity_web.py`
- `test_wavefinity_web.py`
- optionally existing connector-specific tests if current coverage lives elsewhere
- `/fixes/fix-011.md` for implementation outbrief/status only

Do not change connector mesh math in `organizer_engine.py` unless implementation reveals a genuine bug preventing the already-supported 3-Way/4-Way production functions from being reused.

Do not edit `/fixes/Fix Master.md` on `fix11`.

---

# Testing required

This changes UI state, hosted generation, local printing, and multi-file connector output. It is not a tiny change.

Update/extend existing tests rather than creating a new framework.

At minimum cover:

1. `web/index.html` no longer contains `bin-join-mode`.
2. `web/index.html` no longer contains `connector-type`.
3. `web/index.html` no longer contains `corner-connector-quantity`.
4. Browser source no longer persists/uses `default_join_mode` or sends `join_mode`.
5. Same-height `connector_payload()` generates Side + 3-Way + 4-Way, one each.
6. Different-height `connector_payload()` generates only Side.
7. Same-height corner-ineligible dimensions still generate Side and report skipped corner types instead of failing the whole request.
8. Base Trim design passed to `connector_payload()` is rejected because it is not a bin design, not because of any user join preference.
9. `print_payload()` appends the same automatic bundle for an ordinary supported bin and no longer validates `join_mode`.
10. B4B/lid/Base Trim print exclusions remain intact.
11. Hosted multi-file extraction exposes all generated connector files without duplicate names.

Run at least:

```bash
python -m unittest test_wavefinity_web.py
python run_tests.py
```

If the repository's merged current instructions use a different canonical full-suite command, use that documented equivalent.

Do not call the fix complete with failing tests.

---

# Acceptance criteria

Fix 011 is ready for outside review only when:

- The Connectors section has no Side-connectors-vs-Base-Trim chooser.
- The Connectors section has no Side/3-Way/4-Way type chooser.
- The Connectors section has no corner quantity chooser.
- Same/Different bin height remains the only connector mode choice.
- Same-height generation produces one Side, one 3-Way Corner, and one 4-Way Corner file whenever the geometry is eligible.
- Different-height generation produces only Side.
- Physically ineligible corner connectors do not prevent a valid Side file from being produced.
- The user can simply delete unneeded generated connector files.
- Base Trim remains fully available as its separate existing design/generation flow.
- No hidden/persisted `joinMode` can silently suppress connector generation.
- Hosted save-to-folder receives the full automatic connector bundle.
- Local Print to Bambu Studio receives the same automatic bundle.
- Existing Side/different-height and corner geometry behavior is preserved.
- Relevant targeted tests pass.
- The normal full test suite passes.

---

# Implementation outbrief

Implemented on branch `claude/fix-11-3f5n9i` (this repo's harness-assigned
branch name for this task; behavior matches the `fix11` spec above exactly).

**Files changed:**
- `web/index.html` — removed the "Join bins with" (Side/Base Trim) select and
  the "Connector type" (Side/3-Way/4-Way) select plus the corner-quantity row.
  Bin heights (Same/Different) is the only remaining connector-mode control.
- `web/app.js` — removed `state.joinMode`, `persistJoinMode()`,
  `syncJoiningControls()`, `CONNECTOR_TYPES`/`CONNECTOR_TYPE_NAMES`,
  `normalizeConnectorType()`, `connectorTypeNow()`, `syncConnectorTypeControls()`,
  and all `join_mode`/`default_join_mode` reads, writes, and payload fields.
  Added `syncConnectorSectionVisibility()` (folds the old joining-controls
  visibility logic into a single capability-driven function: hidden only for
  an actual Base Trim or B4B design, never for a join preference) and rewrote
  `renderConnectorReadout()` to describe the automatic bundle instead of a
  chosen type. `generateParts()`'s connector row title is now
  "Connectors (Side + 3-Way + 4-Way)" or "Side Connector" depending on the
  height mode.
- `web/spaces.js` — removed the one remaining `state.joinMode`/`persistJoinMode()`
  write (Surface Space creation).
- `wavefinity_web.py` — `connector_payload()` no longer takes a `type`/`quantity`
  option or a `join_mode` gate. It rejects an active Base Trim design (checked
  via `_is_base_trim_design`) with "Connectors are generated from a bin
  design, not from a Base Trim design." Same-height requests generate Side +
  3-Way + 4-Way (each via new small helpers `_generate_side_connector` /
  `_generate_corner_connector`, factored out of the old single-type body) into
  one output directory, returning `{"side":..., "three_way":..., "four_way":...}`
  plus a `connector_plan` with `mode: "auto"`, `types`, and `skipped_types`
  when a corner is physically ineligible (< 16 mm X/Y) — the Side file is
  still produced in that case. Different-height requests generate Side only.
  `print_payload()` no longer reads/validates `join_mode`; it calls the same
  `connector_payload()` for an eligible print, so Bambu Studio receives the
  identical automatic bundle. Removed the now-dead `_corner_quantity()` /
  `_corner_connector_payload()` request helpers, the `default_join_mode`
  preference read/write, and the now-unused `re` import.
- `test_wavefinity_web.py` — updated the two existing `connector_payload()`
  filename/height tests to also mock `generate_corner_file` (the default
  design's 16×48 mm box is corner-eligible, so the same-height path now calls
  it too). Added tests for: same-height bundle generates all three types;
  different-height generates Side only; an X/Y-too-small bin still generates
  Side and reports `skipped_types`; a Base Trim design is rejected by design
  type, not by a join preference; hosted extraction exposes all bundle files
  without duplicate names; `print_payload()` sends the bundle for an ordinary
  bin and ignores a garbage `join_mode` value; `print_payload()` still skips
  the bundle for B4B, a lidded bin, and Base Trim; and source-level checks
  that `bin-join-mode`, `connector-type`, `corner-connector-quantity`,
  `joinMode`, `join_mode`, and `default_join_mode` are gone from the browser
  source.

**Tests run:**
- `python3 -m unittest test_wavefinity_web -v` (via the project's pinned
  dependencies in a local `.venv`, with `numpy` relaxed to `<2.5` only because
  this sandbox's Python is 3.11 and pinned `numpy==2.5.2` requires 3.12; no
  project file was changed for this) — **92/92 passed.**
- `python3 run_tests.py` (whole suite) — **613 passed, 1 skipped, 1 errored,
  615 total in ~1046s.** The one error
  (`test_b4b.B4BWallTests.test_body_has_flat_floor_and_full_height_perimeter_wall`)
  was `ModuleNotFoundError: No module named 'rtree'` — an optional trimesh
  ray-query dependency missing from this ad-hoc sandbox `.venv`, not a pinned
  project dependency and unrelated to B4B or connector code. Installing
  `rtree` and re-running that single test confirms it passes
  (`OK`, 1 test in 0.487s). No failures attributable to this change.

**Deviations from the plan:** none in product behavior. The implementation
branch name is the harness-assigned `claude/fix-11-3f5n9i` rather than a
manually created `fix11`, per this session's branch-workflow instructions;
the code changes match the `fix11` spec exactly.

---

**Recommended coding model: Medium**  
**Recommended thinking/reasoning: Medium**


---

## Final completion

- **Review verdict:** YES — DONE
- **Accepted implementation branch:** `claude/fix-11-3f5n9i`
- **Accepted branch head:** `ad05fc673f7391716e5ab402ef448ca02561c31a`
- **Merge PR:** #7
- **Main integration commit:** `7c25b1d95843ba3b42788baa2af2ed5034822be3`
- **Completion:** Reviewed by ChatGPT, merged into `main`, verified integrated, and archived on 2026-09-19.
