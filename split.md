# Execution Plan: Split `organizer_inserts.py` Safely

## Recommendation

Use a **sequential Sol/Terra handoff**, with only one active executor at a time:

| Work | Model | Thinking |
|---|---|---|
| Git checkpoint, compatibility tests, and intact file-to-package move (Phases 1–2) | Terra | `high` |
| Core/registry dependency extraction (Phase 3) | Sol | `xhigh` |
| Repetitive one-feature-at-a-time extraction (Phase 4) | Terra | `high` |
| Cross-feature layout and assembly extraction (Phase 5) | Sol | `xhigh` |
| Final full verification, diff audit, documentation, and push (Phases 6–7) | Sol | `high` |

This is safe only if each model stops at the end of its assigned phase, commits a green checkpoint, updates this document, and fully exits before the next model starts in the same checkout. Never run the models concurrently.

- Sol is reserved for the two places where circular imports, registry initialization, or cross-feature behavior can fail subtly.
- Terra is appropriate for bounded mechanical moves whose imports and tests are already specified.
- Do not use Luna for this refactor. Its savings are not worth the additional risk on a 3,000-line compatibility-sensitive change.
- Escalate a Terra phase to Sol `high` if it encounters anything beyond a direct move/import/re-export problem.
- Escalate Sol from `high` to `xhigh` during final review only if tests, registry checks, or the diff expose an unresolved inconsistency.
- Do not use `max`.

Higher reasoning effort can consume more reasoning tokens, but OpenAI publishes no fixed token multiplier for `high` versus `xhigh`. This staged recommendation limits `xhigh` to the two highest-risk phases.

Official model descriptions: [OpenAI model catalog](https://developers.openai.com/api/docs/models).

## How to Launch and Hand Off the Work

Do not give one session a general instruction to "execute all of `split.md`." Use five sequential sessions. Start the next session only after the previous one has committed and pushed its green checkpoint, updated this document, reported completion, and fully stopped.

Use the saved Wavefinity project directly so every session continues in the same checkout and on the branch created by Session 1. Do not create a separate worktree for one of these phase handoffs.

### Session 1 — Terra, `high`

Start a new session with **GPT-5.6 Terra** and **high** thinking. Send:

```text
Read split.md completely. Execute only Phases 1 and 2, including every Git safety, compatibility, testing, commit, push, and documentation requirement. Do not begin Phase 3. When Phases 1 and 2 are green, update split.md with the checkpoint details, commit and push the phase, report the exact handoff state for Session 2, then stop.
```

### Session 2 — Sol, `xhigh`

After Session 1 has stopped, start a new session with **GPT-5.6 Sol** and **xhigh** thinking. Send:

```text
Read split.md completely and verify the current branch and Session 1 checkpoint. Execute only Phase 3. Do not begin Phase 4. When Phase 3 is green, update split.md, commit and push the phase, report the exact handoff state for Session 3, then stop.
```

### Session 3 — Terra, `high`

After Session 2 has stopped, start a new session with **GPT-5.6 Terra** and **high** thinking. Send:

```text
Read split.md completely and verify the current branch and Phase 3 checkpoint. Execute only Phase 4, one feature at a time, following every test and compatibility gate. Do not begin Phase 5. When Phase 4 is green, update split.md, commit and push the phase, report the exact handoff state for Session 4, then stop.
```

### Session 4 — Sol, `xhigh`

After Session 3 has stopped, start a new session with **GPT-5.6 Sol** and **xhigh** thinking. Send:

```text
Read split.md completely and verify the current branch and Phase 4 checkpoint. Execute only Phase 5. Do not begin Phase 6. When Phase 5 is green, update split.md, commit and push the phase, report the exact handoff state for Session 5, then stop.
```

### Session 5 — Sol, `high`

After Session 4 has stopped, start a new session with **GPT-5.6 Sol** and **high** thinking. Send:

```text
Read split.md completely and verify every prior checkpoint. Execute Phases 6 and 7 only. Complete the final full-suite verification, compatibility and diff audit, documentation, final commit, and push. Do not merge to main. Report the baseline tag, branch, test results, final commit, and restore instructions.
```

The stopping language is mandatory. If a session starts the next phase anyway, stop it and begin the intended phase in the correctly configured next session.

## Verified Starting Test Result

On 2026-09-07, before changing this plan:

```text
.venv\Scripts\python.exe -m unittest discover -v
Ran 416 tests in 388.723s
OK
```

The full test suite works. `node --check web\app.js` and `git diff --check` also passed.

Run the full suite again after all other work has stopped and immediately before creating the pre-refactor checkpoint. That gives the executing agent one stable, reproducible baseline to compare with the final result.

## Execution Checkpoints

### Baseline — 2026-09-07

- Green baseline commit: `01cfb58a55542c793df7b82ecafe9c7b94183143`
- Pushed annotated restore tag: `pre-organizer-inserts-split-2026-09-07`
- Implementation branch: `codex/split-organizer-inserts` (pushed from that tag)
- Full suite: `Ran 416 tests in 377.693s` — `OK`
- The prior uncommitted Photo Nest/editor work included three stale scoop/UI
  test expectations. They were corrected before this baseline was created;
  no organizer-inserts split code had been moved.

### Phase 1 — Compatibility Contract

- Recorded the 72 exact externally referenced `organizer_inserts` facade names
  in `test_organizer_inserts.py`.
- Recorded fresh-process builder/default registry keys: `bore`, `cradle`,
  `divider`, `nest`, `pocket`, `post`, `scoop`, `slot`, `steps`, and `text`.
- Added tests for direct imports and attributes, live shared registries,
  fresh-process registration, JSON round trips, and legacy saved-layout defaults.
- Focused suite: `Ran 186 tests in 81.571s` — `OK`.
- Commit: `b7ba7fa9dc1e8a5e32d14013927b4eca3e137a2f` (pushed).

### Phase 2 — Intact File-to-Package Move

- Performed a Git-recognized 100% rename:
  `organizer_inserts.py` → `organizer_inserts/__init__.py`.
- `__init__.py` is still the entire original implementation; no logic was edited.
- Fresh-process import resolves to `organizer_inserts/__init__.py` and sees the
  recorded complete builder/default registries.
- Compatibility suite: `Ran 4 tests in 0.888s` — `OK`.
- Insert suite: `Ran 186 tests in 83.013s` — `OK`.
- Full suite: `Ran 420 tests in 396.312s` — `OK` (416 baseline + 4 new
  compatibility tests).
- Commit: `a064853fe794e43bf025d43b853d07604a018d8c` (pushed).

### Session 2 Handoff

- Start from the clean, pushed `codex/split-organizer-inserts` branch at the
  checkpoint documentation commit that follows this entry.
- Verify the baseline tag and the Phase 1/2 commits above, then execute only
  Phase 3. Do not begin Phase 4.
- The next extraction must move shared data/layout/save/load helpers to
  `_core.py`, registries to `_registry.py`, and preserve the package facade and
  all Phase 1 compatibility tests.

### Phase 3 — Foundation Extraction

- Moved shared constants, data models, layout serialization, save/load,
  snapping, editor movement/resize helpers, item/count helpers, and
  `connector_keep_out()` into `organizer_inserts/_core.py`.
- Moved the builder/default type aliases, singleton registries, decorators,
  and `resolved_options()` into `organizer_inserts/_registry.py`.
- The package facade explicitly re-exports every moved name and both facade
  registries are the exact singleton objects owned by `_registry.py`.
- `_core.Layout.validate()` uses a narrow runtime import from the package
  facade until `_layout.py` is introduced in Phase 5; there is no module-level
  reverse dependency.
- Fresh-process registry/singleton check: all 10 builders and defaults present;
  both singleton identity checks passed.
- Compatibility suite: `Ran 4 tests in 0.913s` — `OK`.
- Insert suite: `Ran 186 tests in 79.861s` — `OK`.
- Full suite: `Ran 420 tests in 372.915s` — `OK`.
- `node --check web/app.js` and `git diff --check` passed.
- Commit: `e7535fbbafdc2f9e8ca3378708b48d900a66e75e`.

### Session 3 Handoff

- Start from the clean, pushed `codex/split-organizer-inserts` branch at the
  checkpoint documentation commit that follows this entry.
- Verify the Phase 3 commit and green results above, then execute only Phase 4.
  Do not begin Phase 5.
- No Phase 4 feature module exists yet. All feature implementations remain in
  `organizer_inserts/__init__.py`; extract them one at a time in the specified
  order, preserving explicit facade re-exports and the complete fresh-process
  registries after every feature.
- Do not replace the temporary runtime `Layout.validate()` bridge during Phase
  4; it is replaced with the `_layout.check_layout` local import in Phase 5.

### Phase 4 — Feature Extraction

- Extracted one feature module at a time, in the required order:
  `_post.py`, `_pocket.py`, `_steps.py`, `_scoop.py`, `_slot.py`, `_bore.py`,
  `_cradle.py`, `_nest.py`, `_divider.py`, and `_text.py`.
- Each module owns its feature defaults, builder, constants, and local helpers;
  `__init__.py` imports each module explicitly so decorators populate the same
  singleton registries and re-exports the pre-existing facade names.
- Focused compatibility, registry, and per-feature geometry/layout tests passed
  after every extraction. The full suite passed: `Ran 420 tests in 374.047s` —
  `OK`.
- `node --check web/app.js` and `git diff --check` passed.
- Feature extraction commits: `261f37e`, `db03afe`, `0fc5f43`, `8c73627`,
  `8799866`, `de71f3a`, `0c7a104`, `a881eab`, `09ff31e`, `24b0a13`, and
  `4759f54`.

### Session 4 Handoff

- Start from the clean, pushed `codex/split-organizer-inserts` branch at the
  Phase 4 documentation commit that follows this entry.
- Verify the Phase 4 checkpoint and complete only Phase 5. Do not begin Phase
  6.
- The temporary `Layout.validate()` bridge remains in `_core.py`. Phase 5 must
  move cross-feature footprint/validation work to `_layout.py`, replace that
  bridge with its narrow local `_layout.check_layout` import, then move assembly
  work to `_assembly.py` without changing the public facade or registry order.

### Phase 5 — Cross-Feature Layout and Assembly Extraction

- Moved footprint dispatch, minimum-footprint dispatch, feature reach,
  occupied-zone calculation, and layout validation into `_layout.py`.
- Replaced the temporary package-facade bridge in `Layout.validate()` with the
  required narrow local import of `_layout.check_layout`.
- Moved feature build dispatch, text coordination, insert footprints and
  plates, fused/removable/cartridge assembly, text application, and reporting
  into `_assembly.py`.
- Moved the starter item library into `_core.py`; `__init__.py` is now a
  185-line import-only compatibility facade with no function or class bodies.
- Fresh-process import checks preserved all 10 builders/defaults, their order,
  and both registry singleton identities. Every moved function's AST matched
  the Phase 4 checkpoint exactly, and the prior facade namespace was preserved.
- Focused layout/build/text suite: `Ran 58 tests in 42.297s` — `OK`.
- Focused export/preview suite: `Ran 39 tests in 56.104s` — `OK`.
- Full suite: `Ran 420 tests in 365.552s` — `OK`.
- `git diff --check` passed.
- Commit: `7d1257db1b66d71fc4f27bb6a77b752ff019cc6c`.

### Session 5 Handoff

- Start from the clean, pushed `codex/split-organizer-inserts` branch at the
  Phase 5 documentation commit that follows this entry.
- Verify the Phase 5 commit and green results above, then execute Phases 6 and
  7 only. Do not merge to `main`.
- The package split is structurally complete. Session 5 must perform the final
  full verification, fresh-process registry/import checks, facade and
  dependency-direction audit, complete diff review, documentation finalization,
  final commit, and push required by Phases 6 and 7.

### Phase 6 — Final Verification

- Verified the baseline tag and every Phase 1–5 implementation/checkpoint commit
  as ancestors of `codex/split-organizer-inserts`; the annotated tag resolves to
  baseline commit `01cfb58a55542c793df7b82ecafe9c7b94183143` locally and on
  `origin`.
- Final package map (physical lines):

  ```text
  organizer_inserts/
  ├── __init__.py        185
  ├── _assembly.py       313
  ├── _bore.py           204
  ├── _core.py           461
  ├── _cradle.py         274
  ├── _divider.py        487
  ├── _layout.py         328
  ├── _nest.py           340
  ├── _pocket.py         106
  ├── _post.py            73
  ├── _registry.py        57
  ├── _scoop.py          115
  ├── _slot.py            66
  ├── _steps.py           77
  └── _text.py           249
  ```

- Final full suite: `Ran 420 tests in 397.173s` — `OK`. This is the 416-test
  baseline plus the four Phase 1 compatibility-contract tests.
- The diff audit then found that feature imports had changed registry iteration
  order. The original order (`cradle`, `nest`, `bore`, `post`, `divider`,
  `pocket`, `slot`, `steps`, `scoop`, `text`) was restored. The four focused
  compatibility tests passed again in `0.804s`. A second full run remained green
  through the observed tests and was stopped by the user, who directed that the
  completed 420-test run be treated as the final green result.
- Fresh-process imports see all 10 builders and defaults in the original order;
  both facade registries are the exact `_registry.py` singleton objects; all 72
  recorded facade names import successfully.
- `organizer_app.py` and `wavefinity_web.py` are unchanged from the baseline and
  import through the same `organizer_inserts` facade.
- The facade is 185 lines with no function or class bodies. Feature modules have
  no forbidden feature-to-feature, layout, assembly, or facade imports. All 18
  functions moved in Phase 5 have AST-identical bodies to the Phase 4 checkpoint.
- The full suite covered the existing mesh fingerprints, watertightness,
  export/reload, saved-design round trips, and web API behavior without changed
  expectations. The old top-level `organizer_inserts.py` is absent.
- `node --check web/app.js`, working-tree `git diff --check`, and the complete
  baseline-to-final branch diff check passed. Five extracted modules had extra
  end-of-file blank lines; they were removed without logic changes.
- Final compatibility/diff correction commit:
  `becdc266df0255fbf61c24276011c387f540ce0e`.

### Phase 7 — Completion

- Updated `split.md`, `changelog.md`, and `TESTING.md` with the final package,
  verification, audit, and recovery record.
- Final documentation commit: `Document organizer inserts split completion`
  (the commit containing this section; its exact SHA is reported in the Session 5
  handoff).
- All implementation and documentation commits are pushed only to
  `origin/codex/split-organizer-inserts`; `main` remains at the baseline.
- Restore checkpoint: `pre-organizer-inserts-split-2026-09-07`.
- Inspect it with `git show pre-organizer-inserts-split-2026-09-07`.
- Create a safe recovery branch with
  `git switch -c codex/restore-pre-split pre-organizer-inserts-split-2026-09-07`.
- If this branch is later merged, revert its commits or merge commit; do not hard
  reset shared history.

## Goal

Turn `organizer_inserts.py` into a Python package of focused modules without changing behavior, saved-design compatibility, geometry, exports, UI behavior, or imports used elsewhere in the app.

This is a mechanical refactor only. Do not add features, redesign geometry, rename user-facing concepts, clean up unrelated code, or change defaults during this work.

## Mandatory Working Rules

1. Stop all other agents, editors, and processes that may write to this checkout before beginning. Use one agent in this working tree for the entire refactor.
2. Do not allow another session to edit even a different file in this checkout while tests are running.
3. Inspect `git status` before every commit and preserve any work that existed before this plan.
4. Never hide a failure by weakening, deleting, skipping, or broadly rewriting a test.
5. If an existing test exposes an import assumption, preserve the old behavior through the package facade unless the test is provably tied only to the old physical filename.
6. Use the repository virtual environment for every Python command.
7. Keep each extraction mechanical: move code, adjust imports, re-export it, and test it before moving on.

Splitting files reduces future edit conflicts, but it does not make simultaneous work in one checkout safe. Future parallel work must use separate Git worktrees or branches and be merged deliberately.

## Git Safety Checkpoint — Do This First

The executing agent must make the current state easy to identify and restore before moving any code.

1. Confirm all other work is finished and the working tree is no longer changing.
2. Review every modified and untracked file. Do not discard, overwrite, or accidentally absorb unrelated work.
3. Run the stable pre-refactor full suite:

   ```powershell
   .venv\Scripts\python.exe -m unittest discover -v
   ```

4. If the suite fails, stop the split and resolve or clearly isolate the pre-existing failure first. The split must start from a green commit.
5. Commit all intended pre-existing work as a cohesive baseline commit. Verify the staged diff before committing.
6. Push that baseline commit to `origin/main` so the restore point exists off the computer too.
7. Create and push an annotated tag on that exact green commit:

   ```powershell
   git tag -a pre-organizer-inserts-split-2026-09-07 -m "Green checkpoint before organizer_inserts package split"
   git push origin pre-organizer-inserts-split-2026-09-07
   ```

8. Create the implementation branch from that tagged commit and push it immediately:

   ```powershell
   git switch -c codex/split-organizer-inserts
   git push -u origin codex/split-organizer-inserts
   ```

9. Record the baseline commit ID, tag, test count, and test result in this document before moving code.

### How to Return to the Checkpoint

- Inspect it at any time: `git show pre-organizer-inserts-split-2026-09-07`
- Make a safe recovery branch from it: `git switch -c codex/restore-pre-split pre-organizer-inserts-split-2026-09-07`
- If the split is later merged and must be undone, revert the split commit or merge commit. Do not use a destructive hard reset on shared history.

## Problems in the Original Draft That Must Be Avoided

The original file-boundary idea was directionally good, but its stated circular-import risk was too low and its order of work was unsafe.

Known dependency knots in the current file include:

- `Layout.validate()` calls `check_layout()`, which currently appears much later in the file.
- `divider_defaults()` calls `connector_keep_out()`, which currently appears after all feature builders.
- Layout footprint and minimum-size logic calls feature-specific helpers from Cradle, Bore, Post, Divider, Slot, and Text.
- Decorated feature/default functions populate shared registries at import time. Missing or reordered imports can leave a valid-looking but incomplete registry.
- The rest of the app and tests import many names directly from `organizer_inserts`, including constants, registry dictionaries, helper functions, and the private compatibility alias `_cradle_rib_thickness`.
- Creating an `organizer_inserts/` directory beside `organizer_inserts.py` introduces ambiguous file-versus-package loading. Do not use that as an incremental transition state.

The statement "insert files do not import each other, so circular imports will not happen" is not sufficient. The final design must have an explicit one-way dependency direction.

## Final Package Structure

```text
organizer_inserts/
├── __init__.py       Public compatibility facade only
├── _core.py          Shared constants, data models, JSON/save/load, snapping, common helpers
├── _registry.py      Builder/default registries, decorators, and option resolution
├── _cradle.py        Cradle constants, defaults, builder, and footprint helpers
├── _nest.py          Photo Nest constants, transforms, defaults, and builder
├── _bore.py          Bore constants, defaults, builder, and sizing helpers
├── _post.py          Post defaults, builder, and footprint helper
├── _divider.py       Divider constants, defaults, slopes, walls, and footprint helpers
├── _pocket.py        Pocket constants, defaults, and builder
├── _slot.py          Slot defaults, builder, and sizing helper
├── _steps.py         Steps defaults and builder
├── _scoop.py         Scoop defaults and builder
├── _text.py          Text options, placement, defaults, builder, and footprint helpers
├── _layout.py        Cross-feature footprint dispatch, validation, and occupied-zone logic
└── _assembly.py      Build dispatch, insert plates, fused/removable assembly, text application, reports
```

`__init__.py` must stay small. It imports feature modules in an explicit order so their decorators run, then re-exports the old module API with named imports. Do not move approximately 600 lines of implementation into `__init__.py`; that merely creates another oversized file.

Type-specific constants belong with their type and are re-exported from `__init__.py` for compatibility. Only genuinely shared constants belong in `_core.py`.

### Required Dependency Direction

```text
_core
  ↓
_registry
  ↓
feature modules
  ↓
_layout
  ↓
_assembly
  ↓
__init__ compatibility facade
```

Feature modules may import `_core`, `_registry`, and `organizer_engine`. They must not import `__init__.py`, `_layout`, `_assembly`, or one another.

Move `connector_keep_out()` into an earlier shared layer because Divider defaults and assembly both need it.

`Layout.validate()` is the one expected reverse reference. Keep `Layout` in `_core.py`, but perform a narrow local import of `_layout.check_layout` inside `Layout.validate()` when the method runs. Do not introduce a module-level `_core` ↔ `_layout` cycle.

## Compatibility Contract to Capture Before Moving Code

Add focused tests before the split that lock down these facts:

1. Every current direct import in `organizer_app.py`, `wavefinity_web.py`, and the test modules still imports from `organizer_inserts` unchanged.
2. `FEATURE_BUILDERS` and `FEATURE_DEFAULTS` contain the same keys after a fresh Python process imports the package.
3. The registries exposed by `organizer_inserts` are the actual shared registry objects, not copied dictionaries.
4. Existing module-attribute access remains valid, including current constants, `LIBRARY`, builders, footprint helpers, text helpers, and `_cradle_rib_thickness`.
5. Existing JSON layout round trips and older saved designs remain unchanged.
6. A fresh-process import succeeds; passing in the already-imported test process is not enough to prove registration order.

Do not add a restrictive `__all__` unless it exactly preserves the old usable namespace. Explicit named re-exports are required even if `__all__` is omitted.

## Safe Execution Sequence

### Phase 1 — Record the Baseline Contract

1. Save the exact list of top-level names used outside `organizer_inserts.py`.
2. Save the exact feature/default registry keys from a fresh Python process.
3. Add the compatibility tests above and run them.
4. Run the existing `test_organizer_inserts` suite before moving code.
5. Commit the contract tests separately.

### Phase 2 — Convert the File to a Package Without Splitting It Yet

Do not create a competing package beside the module. Move the original file intact first:

```powershell
New-Item -ItemType Directory organizer_inserts
git mv organizer_inserts.py organizer_inserts\__init__.py
```

At this point, `organizer_inserts/__init__.py` must still contain the entire original implementation with no logic edits.

Verify immediately:

1. Import `organizer_inserts` in a fresh Python process.
2. Confirm the recorded public names and registry keys.
3. Run `test_organizer_inserts`.
4. Run the full 416-test suite.
5. Commit this pure file-to-package move separately so Git can preserve history clearly.

### Phase 3 — Extract the Foundation

1. Extract data classes, shared layout serialization, save/load, snapping, common constants, and common helpers into `_core.py`.
2. Extract the registry dictionaries, decorators, type aliases, and `resolved_options()` into `_registry.py`.
3. Keep registry dictionaries singletons. Every module and facade must reference the same objects.
4. Move `connector_keep_out()` to the appropriate shared layer before extracting Divider.
5. Re-export every moved compatibility name from `__init__.py` with explicit imports.
6. Run the compatibility tests, `test_organizer_inserts`, and the full suite.
7. Commit this phase separately.

### Phase 4 — Extract One Feature at a Time

Use this order, which starts with simpler leaf features and leaves the most connected features until their dependencies are ready:

1. `_post.py`
2. `_pocket.py`
3. `_steps.py`
4. `_scoop.py`
5. `_slot.py`
6. `_bore.py`
7. `_cradle.py`
8. `_nest.py`
9. `_divider.py`
10. `_text.py`

For each feature:

1. Move its constants, default resolver, builder, and private helpers together.
2. Import only from `_core`, `_registry`, and `organizer_engine`.
3. Add explicit re-exports in `__init__.py` before deleting the old definitions.
4. Import the feature module from `__init__.py` so decorators always register it.
5. Run its focused tests plus the compatibility/registry tests.
6. Confirm a fresh process sees all registry keys, not only the feature just moved.
7. Commit small logical groups; do not wait until every feature is moved before the next recoverable commit.

Do not change algorithms while moving them. If cleanup is desirable, write it down for a separate later change.

### Phase 5 — Extract Cross-Feature Layout and Assembly

1. Move footprint dispatch, minimum-footprint dispatch, `_feature_reach`, `feature_footprint`, `occupied_zones`, and `check_layout` into `_layout.py`.
2. `_layout.py` may import feature-specific footprint helpers. Feature modules must never import `_layout.py` at module load time.
3. Move `build_features`, text collection/resolution coordination, insert footprint/plate functions, fused/removable/cartridge assembly, `apply_texts`, and `insert_report` into `_assembly.py`.
4. Keep `__init__.py` as an import/compatibility facade only.
5. Run fresh-process import checks, focused layout/build/export tests, then the full suite.
6. Commit this phase separately.

### Phase 6 — Final Verification

All of the following must pass on the final branch:

```powershell
.venv\Scripts\python.exe -m unittest discover -v
node --check web\app.js
git diff --check
```

Also verify:

1. The final full suite reports at least the 416 baseline tests, with zero failures and zero errors. A higher count is expected only if compatibility tests were added; explain the difference.
2. A fresh Python process imports `organizer_inserts` and sees the complete expected registries.
3. `organizer_app.py` and `wavefinity_web.py` require no import-path changes.
4. Existing mesh fingerprints, watertightness checks, export/reload checks, saved-design round trips, and web API tests pass unchanged.
5. The old top-level `organizer_inserts.py` no longer exists.
6. `__init__.py` contains no substantial geometry or business logic.
7. Git recognizes moved code where practical; inspect the final diff for accidental rewrites or line-ending churn.
8. The working tree contains no unrelated files or generated artifacts staged for commit.

If a test fails, first distinguish a real behavior change from an import-path problem. Restore compatibility rather than changing the expected behavior.

### Phase 7 — Finish and Push

1. Update this document with the actual final file map, test count, duration, commit IDs, and any deviations from the plan.
2. Update normal repository documentation/test history if the project convention requires it.
3. Review the complete staged diff.
4. Create a final cohesive commit for the completed split.
5. Push every implementation commit to `origin/codex/split-organizer-inserts`.
6. Report the baseline tag, branch name, final test result, and final commit ID.
7. Do not merge the implementation branch into `main` unless explicitly requested.

## Stop Conditions

Stop and report instead of improvising if:

- another process changes repository files during the refactor or a test run;
- the stable pre-refactor suite is not green;
- preserving an old import would require a behavior change;
- circular imports cannot be removed while keeping the dependency direction above;
- a geometry, export, or compatibility test changes unexpectedly;
- the Git checkpoint or pushed tag cannot be verified.

## Completion Criteria

The work is complete only when:

- the green pre-split commit and pushed annotated tag exist;
- the implementation is on the pushed `codex/split-organizer-inserts` branch;
- all old imports work unchanged;
- all registries are complete in a fresh process;
- no user-visible or geometry behavior changed;
- the full suite passes before and after with at least 416 tests;
- JavaScript syntax and Git whitespace checks pass;
- the final diff and working tree contain no unrelated or generated changes;
- the final commit ID and restore instructions are recorded here.
