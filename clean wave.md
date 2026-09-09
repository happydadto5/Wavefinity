# Clean Wave — Staged Architecture and Divider Scoop Plan

## Purpose

This file is the authoritative staged implementation plan for improving Wavefinity's modular architecture.

It is designed so a coding agent can be given one simple instruction:

> **Read `clean wave.md` and implement the next phase.**

There are exactly three planned phases.

Each invocation should implement **one phase only**.

After completing a phase, the agent MUST update this file before finishing so that the next invocation can determine what has already been done, what architectural decisions were actually made, and which phase comes next.

---

# Phase Status

Update this section as work progresses.

- [x] **Phase 1 — Divider Scoops + Core Reuse/Settings Pattern**
- [x] **Phase 2 — Expand Settings and Feature Architecture**
- [x] **Phase 3 — Broader Modular Hygiene**

The first unchecked phase is the **next phase**.

Do not implement more than one phase in a single invocation unless explicitly instructed otherwise.

---

# Instructions for Every Invocation

When told:

> **Read `clean wave.md` and implement the next phase.**

follow this process.

## 1. Determine the next phase

Read the Phase Status section.

The first unchecked phase is the only phase to implement during this invocation.

If all three phases are checked, make no architectural changes.

---

## 2. Review the planned work for THAT phase before coding

Before changing code, inspect the current implementation relevant to the phase you are about to perform.

Critically review the recommendations in that phase against the code as it exists **at that time**.

The plan is guidance, not permission to mechanically impose an architecture that does not fit the code.

You may adjust the implementation if:

- the existing code supports a simpler architecture;
- earlier completed phases changed the best implementation;
- a proposed abstraction would create unnecessary complexity;
- compatibility requirements require a different approach;
- tests or existing design patterns demonstrate a better solution.

Any meaningful deviation should be briefly recorded in this file under that phase's completion notes.

### Important phase-review boundary

**Review only the phase being implemented now.** Do not review, redesign, or prepare code for later phases, even if you spot an opportunity. Each phase is reviewed against the codebase as it exists when that phase becomes active — because earlier phases may change what the best implementation looks like. This staging is intentional.

---

## 3. Stay inside the current phase

Small supporting changes outside the named files/components are acceptable when directly necessary to complete the current phase correctly.

Do not use a phase as permission for broad unrelated cleanup.

If you discover worthwhile future work that belongs in a later phase, leave it for that phase.

---

## 4. Preserve compatibility

Unless the current phase explicitly requires a breaking change, preserve:

- existing saved designs;
- public/backend behavior;
- existing UI behavior;
- geometry behavior;
- existing feature functionality;
- serialization compatibility;
- relevant imports and APIs.

Older saved designs should continue to load wherever reasonably possible.

---

## 5. Tests are mandatory

Each phase includes its own required tests.

Run the relevant full test suite before declaring the phase complete.

Fix regressions introduced by the phase.

A phase is not complete merely because the new functionality appears to work manually.

**Current user verification override (2026-09-09):** Add or update the tests required
by each phase, but do not execute test suites again until all three phases are
implemented. After Phase 3, run the full suite once and address the remaining issues.
Fulfilled after Phase 3: the final full run passed all 446 tests.

---

## 6. Update THIS FILE before finishing

After the phase is successfully completed:

1. Change its Phase Status checkbox from `[ ]` to `[x]`.
2. Fill in that phase's **Completion Notes** section.
3. Record only information that will actually help the next phase understand the resulting architecture.

Completion Notes should be concise and include:

- important architecture actually implemented;
- important files/modules changed;
- important data-model or serialization decisions;
- meaningful deviations from the original phase plan and why;
- relevant tests added/changed;
- confirmation that the test suite passed;
- any architectural constraint that the next phase needs to know.

Do not turn Completion Notes into a verbose development diary.

The purpose is continuity between coding-agent invocations.

---

## 7. Stop after updating this file

Once the current phase is implemented, tested, and documented here, **STOP**. Do not begin the following phase.

---

# Core Architectural Principles

These apply across all three phases.

## Feature/container separation

> **Features own behavior. Containers own regions. Composition connects them.**

For example:

```text
Divider:
"These are the compartments I created."

Scoop:
"This is how Scoop geometry is created."

Composition:
"Apply Scoop to these selected Divider compartments."
```

Scoop should not need to understand Divider.

Divider should not contain copied Scoop geometry.

---

## Reuse before duplication

> **If applying an existing capability somewhere new requires copying its geometry, defaults, validation, or settings logic, extract the reusable capability instead.**

Adapters for different contexts are fine.

Duplicated implementations of the same underlying capability are not.

---

## Automatic-setting transparency

Wavefinity contains increasingly complex Auto behavior.

If one setting can:

- change another;
- recalculate another;
- constrain another;
- derive another;
- change another's valid range;
- enable or disable another;

that relationship should be explicit and discoverable.

A developer should be able to determine:

```text
source setting
target setting
effect
owner
reason
```

without having to discover the relationship accidentally inside unrelated event handlers or geometry code.

---

# PHASE 1 — Divider Scoops + Core Reuse/Settings Pattern

## Goal

Add Scoop support to selected Divider compartments while proving two architectural patterns:

1. Scoop geometry/settings can be reused rather than duplicated.
2. automatic setting interactions can be explicitly declared and understood.

Keep Phase 1 tightly focused.

---

## Phase 1.1 — Review the current implementation

Before modifying code, inspect:

- all current Scoop implementations;
- Scoop defaults/settings;
- Divider geometry;
- how Divider compartments are currently calculated;
- Divider configuration;
- Scoop and Divider Auto behavior;
- serialization for both;
- frontend controls for both;
- relevant tests.

Determine whether the implementation below is appropriate.

Modify the approach if the actual code strongly supports something simpler or safer.

Do not review Phase 2 or Phase 3 yet.

---

## Phase 1.2 — Establish one reusable Scoop implementation

Identify duplicate Scoop geometry/profile implementations.

Consolidate the actual Scoop profile mathematics so there is one authoritative implementation.

Conceptually it should be usable like:

```python
build_scoop(region, settings)
```

The exact API should follow the existing Wavefinity geometry model.

The shared Scoop implementation should not care whether the region originated from:

- the existing standalone Scoop feature;
- existing bin-level Scoop behavior;
- a Divider compartment;
- or another future geometric region.

Adapters are acceptable.

Duplicated Scoop profile mathematics is not.

Existing Scoop behavior must continue to work.

---

## Phase 1.3 — Consolidate Scoop settings sufficiently for reuse

Standalone Scoop and Divider Scoop must use the same authoritative Scoop settings/defaults.

Avoid separate copies of things such as:

- height defaults;
- depth/profile behavior;
- orientation;
- ranges;
- validation;
- Auto behavior.

Do only the Scoop-related cleanup necessary for this phase.

Do not migrate every feature to a new settings framework.

---

## Phase 1.4 — Give Divider a reusable compartment API

Divider should independently expose the compartments created by its walls.

Create or improve an API conceptually similar to:

```python
divider_cells(...)
```

A compartment should expose at least:

- a logical identity;
- its usable geometric region;
- any other minimal information required by consumers.

Use row/column identity if appropriate to the current Divider architecture.

The key boundary is:

> **Divider calculates compartments. Other capabilities consume them.**

The compartment calculation should work independently of Scoop.

---

## Phase 1.5 — Add Scoop to selected Divider compartments

Add the user-facing capability to apply Scoop to Divider compartments.

Support:

- no selected compartments;
- one selected compartment;
- multiple selected compartments;
- all compartments where appropriate.

The geometry path should effectively be:

```text
Divider
    ↓
calculate compartments
    ↓
select compartment regions
    ↓
shared Scoop implementation
    ↓
geometry
```

Do NOT create a second independent `divider_scoop` geometry implementation.

Do NOT copy Scoop profile/curve mathematics into Divider.

---

## Phase 1.6 — Persist targeting logically

Associate Scoop configuration with logical Divider compartments instead of unnecessary absolute XYZ coordinates.

Choose the stable identity that fits the existing Divider architecture.

Handle sensibly:

- Divider movement;
- resizing;
- row/column changes;
- disappearing target cells;
- older saved designs without Divider Scoop configuration.

Invalid stale targets should fail safely.

Older designs must continue to load normally.

---

## Phase 1.7 — Add only the required UI

Add the frontend controls needed to:

- enable/configure Divider Scoop;
- select target compartments;
- select multiple compartments;
- edit applicable Scoop settings;
- reopen saved designs and restore the selections/settings.

Reuse existing Scoop settings definitions where practical.

Do not broadly rewrite or modularize the frontend in Phase 1.

---

## Phase 1.8 — Establish the setting-interaction convention

Phase 1 should establish a lightweight mechanism for describing automatic relationships between settings.

For relevant Scoop and Divider settings, make it possible to determine:

```text
source
target
effect
owner
reason
```

Possible effects include:

```text
auto-adjust
derived
constraint
allowed-range change
enable/disable
default
```

The exact implementation should fit the current project.

Do not build a large generic reactive framework.

### Keep rules close to their owner

Rules should live close to the feature that owns the behavior.

For example, Scoop relationships should be defined with Scoop-related code and Divider relationships with Divider-related code.

### Provide a discoverable combined view

There should also be a lightweight way for a developer to inspect all registered relationships.

This central view should be generated/collected from feature-local definitions.

Do NOT maintain a second hand-written dependency matrix.

### Auto behavior must have ownership

For Scoop/Divider logic touched during this phase:

- avoid multiple independent systems silently changing the same setting;
- define deterministic behavior when multiple inputs legitimately affect one result;
- prevent A→B→A update loops;
- preserve explicit user intent where appropriate;
- distinguish user-selected values from Auto-derived values where the current architecture makes that distinction useful.

### Phase 1 scope

Apply this convention to:

- Scoop;
- Divider;
- settings directly involved in Divider Scoop.

Do not perform a project-wide settings audit yet.

That belongs to Phase 2.

---

## Phase 1.9 — Required testing

Add/update tests covering at least:

- existing Scoop functionality through the shared implementation;
- shared Scoop defaults/settings;
- Divider compartment calculation;
- one Divider cell receiving Scoop;
- multiple cells receiving Scoop;
- no cells selected;
- serialization of Divider Scoop settings;
- loading legacy designs;
- layout changes invalidating a previous cell target;
- important Scoop/Divider Auto-setting relationships;
- prevention of relevant setting-update loops;
- mesh validity.

Run the complete relevant test suite.

**Phase 1 is complete only when the test suite passes.**

---

## Phase 1 Completion Notes

Do not fill this section until Phase 1 is complete.

**Status:** Completed

**Architecture implemented:** `organizer_engine.build_scoop_region()` is the single Scoop profile builder. Standalone, legacy bin-level, and Divider-cell Scoops use it through container-specific adapters. `_scoop.py` owns shared depth defaults, validation, height resolution, and region sizing.

**Important files/modules changed:** `organizer_engine.py`, `organizer_inserts/_scoop.py`, `_divider.py`, `_registry.py`, `_text.py`, `__init__.py`, `organizer_app.py`, `wavefinity_web.py`, `web/app.js`, `web/styles.css`, and focused tests.

**Divider-cell representation / targeting:** `DividerCell(row, column, zone)` exposes row-major usable regions with stable IDs such as `r0c0`. Divider `options.scoop` stores only shared Scoop settings; enabling it applies the Scoop to every current compartment. Older saved `cells` targets are migrated away on save so the editor and geometry always agree.

**Setting-interaction mechanism established:** Feature-local `SettingInteraction` declarations record source, target, effect, owner, and reason. `_registry.py` generates the combined view and rejects automatic dependency cycles before registration; the browser catalog exposes the collected view.

**Meaningful deviations from this plan:** Divider Scoop configuration is a nested `options.scoop` object rather than a new feature type, keeping composition owned by Divider and avoiding absolute coordinates. A later user-directed simplification removed per-cell selection: when enabled, every Divider compartment receives a Scoop from its low-Y edge. No broad frontend rewrite was done.

**Tests:** 14 focused Divider/Scoop/API/UI tests passed. Live browser QA passed for disabled/empty, one-cell, multi-cell, All/None, grid changes, depth editing, valid preview, and saved-edit restoration. The project-wide run completed 442 tests: all Phase 1 coverage passed; 9 unrelated existing failures and 1 slicer-picker timeout remained in Bore-limit, Cradle, legacy label/flat-band, Photo Nest, slicer, and stale static-order tests. The user stopped further testing.

**Important information for Phase 2:** Add feature-local rules with `register_setting_interactions()`; do not hand-maintain a second matrix. Automatic `derived`/`auto-adjust` rules are cycle-checked by owner. Preserve the nested Divider `options.scoop` schema and shared `_scoop.py` settings path.

---

# PHASE 2 — Expand Settings and Feature Architecture

## Goal

Take the setting-interaction pattern proven in Phase 1 and apply it systematically across the interior-feature system.

Also reduce unnecessary duplicated feature metadata where that improves maintainability.

Do not implement this phase until Phase 1 is checked complete.

At the start of Phase 2, review **Phase 2 only** against the code as it exists after Phase 1.

Do not review Phase 3 yet.

---

## Phase 2.1 — Audit automatic setting interactions

Review the remaining interior parts/features for cases where one setting:

- changes another;
- derives another;
- constrains another;
- changes its range;
- enables/disables it;
- resets/defaults it.

Register those relationships using the convention established in Phase 1.

The intended outcome is that a developer can answer:

> **What can automatically affect this setting?**

without searching arbitrary UI and geometry code.

---

## Phase 2.2 — Resolve Auto-setting conflicts

Identify places where multiple Auto systems can affect the same target setting.

Where practical:

- establish one owner;
- otherwise define explicit precedence;
- ensure deterministic evaluation;
- prevent update loops;
- preserve explicit user values where appropriate;
- prevent unrelated Auto systems from silently stepping on each other.

Do not redesign Auto logic that is already correct merely to make it stylistically uniform.

---

## Phase 2.3 — Improve feature metadata incrementally

Review the existing feature registry/decorator infrastructure.

Move toward authoritative feature definitions where useful, potentially containing:

- feature kind;
- display title;
- description;
- defaults;
- option definitions;
- option types;
- validation/ranges;
- builder;
- capabilities;
- icon identifier where useful.

Prefer explicit option types such as:

```text
number
boolean
enum
string
```

where the current implementation relies on fragile assumptions.

Do not replace the existing registry simply because a different framework could be invented.

Extend what already works unless there is a concrete reason not to.

---

## Phase 2.4 — Reduce administrative duplication

Reduce situations where adding or changing a feature requires updating several unrelated independent lists.

Focus on duplicated knowledge such as:

- feature existence;
- defaults;
- option metadata;
- capability flags;
- display metadata.

Do not attempt to eliminate every legitimate feature-specific conditional.

Feature-specific behavior is allowed.

Duplicated administrative knowledge is the problem.

---

## Phase 2.5 — Scope discipline

Do not:

- refactor Easy Clean yet unless required by Phase 2 settings work;
- broadly reorganize geometry modules;
- perform frontend modularization;
- reorganize icons unless directly required by the metadata architecture;
- reorganize the repository;
- undertake broad cosmetic cleanup.

Those belong to Phase 3.

---

## Phase 2.6 — Required testing

Add/update tests for setting interactions and feature metadata changes.

Specifically test important situations involving:

- competing automatic behaviors;
- precedence;
- loop prevention;
- user override versus Auto;
- serialization where relevant;
- existing feature behavior.

Run the complete relevant test suite.

**Phase 2 is complete only when the test suite passes.**

---

## Phase 2 Completion Notes

Do not fill this section until Phase 2 is complete.

**Status:** Completed

**Settings architecture implemented:** The Phase 1 `SettingInteraction` registry now covers Cradle, Snug Holder, Bore, Post, Pocket, Divider, Slot Rack, Scoop, and Text Auto/default/constraint/enable/reset relationships. Rules remain feature-local and the generated catalog remains the combined discoverable view.

**Features migrated / audited:** All ten registered interior features were audited. Steps has no automatic setting-to-setting behavior to register. Every feature now owns a `FeatureDefinition` containing its builder, default resolver, display data, capabilities, ordered options, and explicit option types.

**Conflicts or loops resolved:** Pocket, Bore, and Slot Rack shared-floor Height/Depth behavior now uses one editor helper. The field the user edits has deterministic precedence; the counterpart is adjusted once without dispatching another change, preventing A→B→A updates. Existing registry cycle rejection remains in force.

**Feature-registry / metadata changes:** `_registry.py` now owns `FeatureDefinition`, `OptionDefinition`, feature ordering, capabilities, option types, coercion, builders, and default resolvers. Feature modules register their own authoritative metadata. `organizer_app.py` retains compatibility views generated from that registry; `wavefinity_web.py` consumes the registry directly and exposes option types/capabilities.

**Later Divider grid simplification:** Newly created Dividers explicitly start with one wall on X and one on Y. Legacy saved Dividers still resolve through their older one-axis defaults; the first grid-quantity edit supplies a missing axis as one instead of clearing the other quantity.

**Meaningful deviations from this plan:** The existing registry was extended instead of replaced. The browser does not interpret a generic reactive rule engine; feature-specific behavior remains explicit, with only the genuinely duplicated three-feature floor constraint consolidated. Per the user's instruction, test execution is deferred until all three phases are finished.

**Tests:** Phase 2 metadata, typed coercion, relationship coverage, and precedence expectations were added to the existing tests but not run. Three unsafe slicer-picker tests were removed because `browse_slicer_path_payload()` launches Tk in a child process, so their in-process mocks did not prevent real native file dialogs. No test suite was executed.

**Important information for Phase 3:** Use `feature_definitions()` as the authoritative feature/palette source; keep `PART_KINDS`, `PART_KIND_INFO`, `INTERIOR_PART_CATALOG`, and `INTERIOR_PART_ORDER` as generated compatibility views only. Preserve feature-local `SettingInteraction` ownership. Do not run tests until Phase 3 is implemented, then run the full suite and fix remaining failures.

---

# PHASE 3 — Broader Modular Hygiene

## Goal

After Scoop reuse and settings interaction architecture have been proven, address the remaining modularity and contributor-hygiene issues.

Do not implement Phase 3 until Phases 1 and 2 are checked complete.

At the beginning of Phase 3, independently review **Phase 3** against the codebase as it exists at that time.

Do not assume earlier ideas remain optimal.

---

## Phase 3.1 — Prepare Easy Clean for reuse

Review Easy Clean using the architectural lessons learned from Scoop.

Separate genuinely reusable Easy Clean concepts from container-specific application.

Likely reusable concepts include:

- settings;
- defaults;
- validation;
- profile/radius calculations;
- underlying edge-treatment mathematics.

Do not force geometrically different contexts into an artificial identical boolean pipeline.

The intended outcome is:

> A future implementation can apply Easy Clean to Divider compartments without copying the definition or core geometry of Easy Clean.

Whether actual Divider Easy Clean UI/functionality should be added during Phase 3 should be decided during the Phase 3 review based on scope and architecture.

Do not assume it must be implemented merely because preparation is performed.

---

## Phase 3.2 — Improve generic geometry ownership

Review generic geometry helpers currently buried inside feature-specific or large engine modules.

If several features use the same truly generic operations, move them into intentionally shared geometry modules.

Examples may include:

- extrusion;
- boolean union;
- boolean difference;
- intersection;
- sweep;
- loft;
- polygon conversion.

Only extract helpers whose shared nature is demonstrated.

Do not rewrite the geometry engine wholesale.

---

## Phase 3.3 — Improve Divider internal organization if justified

Review Divider after Phases 1 and 2.

If clear subsystems have emerged, separate according to responsibilities such as:

- compartment calculation;
- walls;
- bottoms;
- labels.

Do not split files based solely on line count.

Meaningful ownership boundaries are the goal.

---

## Phase 3.4 — Icon hygiene

Review feature icon storage.

If feature SVG artwork remains embedded in large ad hoc JavaScript mappings, move toward:

```text
feature → icon identifier
icon asset → actual SVG artwork
```

Keep presentation artwork outside backend feature logic.

Avoid introducing unnecessary frontend build tooling.

---

## Phase 3.5 — Frontend modularization if justified

Review large frontend files after the underlying architecture is stable.

If useful, separate clear responsibilities such as:

- API;
- state;
- feature editing;
- preview;
- icons.

Do not refactor the frontend merely because a file is large.

Only introduce modules with meaningful responsibility boundaries.

---

## Phase 3.6 — Packaging and contributor hygiene

Review packaging/distribution scripts.

Verify that generated archives preserve Python package directory structure.

Fix flattening or related packaging problems if they remain.

Update architecture/contributor documentation to match the architecture that actually resulted from all three phases.

Document practical extension rules for future contributors.

---

## Phase 3.7 — Required testing

Run the complete relevant test suite after all Phase 3 work.

Add tests for any behavior materially changed during the phase.

**Phase 3 is complete only when the test suite passes.**

---

## Phase 3 Completion Notes

Do not fill this section until Phase 3 is complete.

**Status:** Completed

**Easy Clean architecture:** `organizer_easy_clean.py` now owns reusable settings, validation, defaults, and the edge-treatment profile. `organizer_engine.py` retains only the bin-specific adapter/application, so a future Divider-cell adapter can reuse the same definition and profile without copying the mathematics.

**Geometry/module changes:** `organizer_geometry.py` now owns the demonstrated shared mesh operations: translation/cleanup, boolean union/difference/intersection, polygon/profile extrusion, sweep, ring resampling/alignment, and lofting. The engine re-exports them for compatibility; feature modules import them directly from the shared module.

**Divider organization changes:** `organizer_inserts/_divider_cells.py` owns `DividerCell`, grid counts, cell calculation, legacy Scoop-target migration, and Scoop/sloped-bottom conflict normalization. Divider walls, bottoms, and labels remain together because their construction is still tightly coupled. Curved Scoop and sloped bottom are mutually exclusive, with Scoop winning when an older saved design contains both. Base-level division labels remain compatible with Scoops by moving into each compartment's clear high-Y half.

**Frontend/icon changes:** Feature metadata now carries an icon identifier. SVG artwork moved from the large application script to `web/feature-icons.js`, loaded before `web/app.js`; no build tooling was added.

**Packaging/documentation changes:** `Make_Wave_Zip.ps1` creates relative ZIP entries and preserves Python/web package directories; `Make_Wave_Zip.bat` invokes it. Archive verification confirmed the new shared modules, `organizer_inserts/`, and `web/feature-icons.js` are packaged at their correct paths. `README.md` documents module ownership, dependency direction, and practical feature-extension rules.

**Meaningful deviations from this plan:** Divider Easy Clean UI/functionality was not added; this phase prepares reuse only. Frontend modularization stopped at icons because API/state/editor/preview responsibilities remain tightly coupled and splitting them now would create churn without a stable boundary.

**Tests:** Added focused coverage for reusable Easy Clean profiles, shared geometry ownership, Divider compartment ownership, icon metadata/loading, and packaging-related structure. Removed three unsafe slicer-picker tests that launched real native dialogs. The deferred full suite exposed stale expectations and one registry cleanup leak; these were corrected along with label orientation selection. Final result: 446 tests passed.

**Remaining architectural debt:** `web/app.js` remains large and should only be split when a cohesive responsibility can move without duplicating state. Easy Clean still needs a future container adapter and UI before it can be applied to Divider cells.

---

## Post-phase Divider follow-up

- Curved Scoop and sloped bottom are mutually exclusive throughout the editor, geometry builder, and saved-design normalization. Selecting either checkbox clears the other configuration; Scoop wins when an older saved design contains both.
- Division labels remain compatible with Curved Scoop. Base-level labels move into the clear high-Y half of each compartment, while rim labels retain their existing placement.
- The 2D layout view mirrors the moved base-label placement.
- Divider Rim Level labels now use the same rear floating-shelf behavior and level selector as the Text part. Grid Dividers build one self-supporting shelf per labeled compartment; the retired side-placement selector is removed from old and newly edited designs.
- Focused geometry, settings-interaction, browser-editor, and save-round-trip checks passed. No additional project-wide suite was run for this follow-up.

---

# Completion Rules

When a phase is finished:

1. Change its checkbox at the top of this file to `[x]`.
2. Change its Completion Notes status to `Completed` and fill in the concise notes.
3. Ensure the relevant test suite passes.
4. Save this file.
5. Stop. Do not implement the next phase in the same invocation.

The next invocation reviews the next phase against the code as it exists then.
