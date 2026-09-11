# speed.md — Wavefinity Fast Vibe-Coding Policy

## Purpose

Wavefinity development has accumulated too much process around testing, test design, repeated verification, large acceptance matrices, and multi-pass review. That work often consumes more time than the implementation and has not been a reliable predictor of the defects that later matter.

This plan changes the default workflow:

> **Implement first, reason carefully about the changed code, inspect the diff, and move on. Do not test unless the change is a genuine high-blast-radius heavy lift.**

Existing tests stay in the repository. They are not deleted merely to make development faster. Tests may be updated when an intentional behavior change knowingly makes an existing expectation obsolete. The key change is that routine work no longer triggers test execution or new-test creation.

---

## Why this policy is appropriate for Wavefinity

The current project already recognizes that testing has become excessive, but the existing README/GEMINI guidance still asks for a targeted test whenever code is genuinely new. That is still too broad for the way this project is being developed.

Observed project history supports tightening the rule:

- The suite has grown into hundreds of tests; recent full-suite runs have taken roughly 6–6.5 minutes each.
- The organizer-inserts split repeatedly ran the full suite at multiple checkpoints even though the work was staged specifically to preserve behavior.
- The initial B4B implementation reported 495 passing tests, yet immediate follow-up review still found important real defects in UI state flow, print-bed packing, top-inlay registration, latch hardware geometry, recess geometry, validation semantics, and collision handling.
- A large amount of prior QA was spent on test matrices, browser checks, screenshots, test-result reports, and speculative edge cases. Some of that found useful issues, but its cost was disproportionate and it did not eliminate the need for focused reasoning/review of the actual implementation.

Conclusion: **a green blanket test run is not enough to prove correctness, and repeatedly obtaining that green run is not a good use of vibe-coding time.** Verification effort should be proportional to blast radius, not to whether code happens to be new.

---

# 1. The default rule: NO TESTING

Unless the task qualifies as a **Major / Heavy-Lift / High-Blast-Radius** change under Section 3, the coding agent should NOT:

- run the unit-test suite;
- run a targeted unit test;
- create a new regression test;
- start the development server merely to check the change;
- perform browser automation or manual browser click-throughs;
- take screenshots for visual verification;
- create acceptance matrices;
- perform random-input sweeps;
- perform exhaustive parameter combinations;
- create a test plan;
- create or update a testing log/report;
- perform repeated “one more verification” passes after the implementation is already understood.

For normal work, **static reasoning is the verification method**:

1. read the relevant existing implementation;
2. make the smallest correct change;
3. inspect the changed code and surrounding call path;
4. inspect the diff for unintended edits;
5. update directly affected documentation only when needed;
6. commit/push the completed unit of work;
7. stop.

Do not invent testing work to fill time or increase confidence cosmetically.

---

# 2. Change classification

## Class A — Small/localized change: NO TESTING

Examples:

- wording, labels, tooltips, descriptions;
- CSS/layout/spacing/appearance;
- moving or hiding a UI control;
- changing a default;
- changing a field range or step when the effect is local and understood;
- a known bug fix with a clear cause and narrow fix;
- a small local refactor;
- changing one feature's local geometry/math without altering shared primitives;
- a contained frontend handler fix;
- documentation changes;
- removing dead local code;
- renaming a variable/function/control;
- adding a small contained option to one feature;
- changing B4B-only behavior that remains inside the B4B path and does not alter shared Wavefinity behavior.

**Action:** implement, inspect, commit. No tests. No browser. No server.

## Class B — Moderate but bounded change: STILL NO TESTING

Examples:

- adding genuinely new logic that is confined to one feature;
- changing a feature plus its directly paired UI/API wiring;
- adding a new setting with serialization that is contained to one feature and has obvious defaults/backward behavior;
- several-file work where every changed file belongs to one coherent feature path;
- a new geometry helper used only by one feature;
- a new UI interaction whose state flow is local and directly traceable;
- a meaningful bug fix that touches multiple functions but does not alter shared project contracts.

The fact that code is **new** does NOT make testing necessary.

**Action:** implement, trace the affected path, inspect the diff, commit. No tests by default.

If the agent feels uncertain, the first response is **more careful code reading/reasoning**, not automatic test creation.

---

# 3. Class C — Major / Heavy-Lift / High-Blast-Radius change: TESTING PERMITTED

Testing is justified only when the change creates a realistic possibility of breaking significant portions of Wavefinity **outside the feature being worked on**.

A change normally qualifies when it touches one or more shared contracts and has broad consumers, especially when several of these are true:

- changes shared box/wave/grid geometry used by many features;
- changes the global mating/interlock rules or dimensions;
- changes `BoxSpec` or another central data model in a way that affects many consumers;
- changes saved-design schema/versioning or broad save/load compatibility;
- changes core generation/export behavior used across normal bins and multiple feature types;
- changes shared layout/assembly/registry infrastructure;
- restructures module/package boundaries, imports, facade compatibility, or registry initialization;
- replaces a major subsystem or performs a large architectural split/merge;
- changes automatic-setting behavior shared by many unrelated features;
- changes security/request boundaries used by most browser operations;
- changes shared frontend state/design synchronization used across many independent controls;
- touches many otherwise unrelated feature paths because of one underlying architectural change;
- has a realistic failure mode where a mistake could silently corrupt saved designs, generate broadly incorrect geometry, or break multiple established workflows.

### High-risk Wavefinity areas

These are not automatically “major” for every edit, but changes to their shared behavior deserve special scrutiny:

- `organizer_engine.py` shared wave/grid/box primitives and central specs;
- `organizer_inserts/_core.py`;
- `organizer_inserts/_layout.py`;
- `organizer_inserts/_assembly.py`;
- `organizer_inserts/_registry.py`;
- broad save/load/generation paths in `organizer_app.py`;
- broad API contracts in `wavefinity_web.py`;
- global state/design synchronization in `web/app.js`;
- common 3MF/export placement logic;
- versioned design serialization.

A large number of changed lines does **not** by itself make work major. A 500-line isolated feature can still be Class B. Conversely, a five-line modification to a shared grid/wave invariant can be Class C.

---

# 4. Testing rules for a qualifying major change

Even when testing is justified, keep it small and risk-directed.

## 4.1 Do not begin with a giant test plan

Before coding, identify the few **cross-project contracts actually at risk**. Usually 3–8 concrete risks are enough.

Examples:

- ordinary bins remain unchanged;
- old saved designs still load;
- global wave phase remains compatible;
- all registered feature kinds still initialize;
- export still preserves relative transforms;
- shared layout validation still accepts prior valid designs.

Do not turn this into dozens of speculative edge cases.

## 4.2 Prefer existing tests

If existing tests already cover the threatened contract, use them. Do not create duplicate tests merely because the implementation changed.

Add a new test only when BOTH are true:

1. the change is Class C; and
2. an important cross-project invariant is not already covered, or a known substantive defect demonstrated that the existing coverage was wrong/incomplete.

## 4.3 Full-suite limit

For most Class C work:

- focused/shared-contract tests during implementation if truly useful;
- **one full-suite run at the end, maximum.**

For a behavior-preserving structural refactor where comparing before/after is genuinely important:

- one baseline full-suite run before changes;
- one final full-suite run after changes;
- **maximum two full-suite runs.**

Do not run the full suite after every phase, module extraction, checkpoint, or minor correction.

## 4.4 Browser/manual verification

Only perform browser/manual verification when the risky behavior actually lives in the browser and cannot be established reasonably from code/state-flow inspection.

When needed, do a **small surgical check of the changed behavior**, not a general browser tour.

No screenshot QA for routine styling/layout changes.

## 4.5 Mechanical/geometry sweeps

Collision sweeps, parameter sweeps, mesh inspections, and other expensive geometry verification are reserved for Class C changes where those mechanics are central to the change.

Do not run broad geometry sweeps on ordinary local geometry edits.

---

# 5. Existing tests: preserve them, but stop serving them

Existing tests remain useful as a dormant safety net for true heavy lifts.

Rules:

- Do not delete existing tests simply because they are not routinely run.
- Do not update tests after every normal implementation change unless the intended behavior knowingly invalidates the old assertion.
- If a planned change intentionally breaks an old expectation, update that test to the new intended contract as part of the implementation. **Do not run it unless the overall task qualifies as Class C.**
- Do not weaken a test merely to make an unexpected failure disappear.
- If a Class C test run exposes an unrelated pre-existing failure, record it briefly and continue unless it blocks the changed contract. Do not launch an unrelated cleanup campaign.
- Do not expand coverage because a coverage percentage, line count, or test count looks low.

The test suite is a tool, not the project manager.

---

# 6. Stop producing test bureaucracy

Wavefinity should not generate or maintain routine artifacts such as:

- `TESTING.md`;
- per-session test logs;
- “final testing summaries”;
- screenshots proving each control works;
- 40/60/100-case matrices;
- exhaustive lists of hypothetical validation cases;
- test-count bragging in normal commit messages;
- lengthy completion notes centered on which tests were run.

For Class C work, the final report needs only a short statement of what meaningful verification was performed and whether it passed.

---

# 7. Faster design and implementation behavior for coding agents

Testing is only one source of wasted time. Apply these rules to the entire vibe-coding workflow.

## 7.1 Do not write a plan for routine work

For Class A and most Class B tasks, inspect the relevant code and implement directly.

Create a detailed implementation plan only when:

- the user explicitly asks for one; or
- the work is Class C and architecture/sequence genuinely matters.

Do not spend a full coding turn designing a change that can safely be implemented in one pass.

## 7.2 Read proportionally to the task

Do not re-review the entire repository for every small change.

Read:

- the affected file/function;
- its direct callers/consumers when relevant;
- the authoritative documentation for the specific behavior being changed.

Perform a project-wide audit only for Class C work or when the user explicitly requests one.

## 7.3 Prefer the smallest implementation

- Reuse existing patterns and helpers.
- Avoid new frameworks for one problem.
- Avoid abstractions with only one plausible consumer unless they simplify the code immediately.
- Do not generalize for hypothetical future features.
- Do not add validation for impossible or purely theoretical states unless there is a real boundary where those states can enter.
- Do not “harden” unrelated code while implementing a contained request.

## 7.4 Known bug beats hypothetical bug

When given a concrete defect:

1. identify its actual cause;
2. fix that cause;
3. inspect directly related consequences;
4. stop.

Do not use every bug fix as permission to invent a broad regression suite or audit unrelated edge cases.

## 7.5 No endless review loops

One strong implementation/review pass should normally be enough.

A second review pass is warranted when:

- the first pass uncovered a real architectural contradiction;
- the implementation changed materially during the first review;
- the change is Class C;
- the user explicitly asks for another review.

Do not repeatedly ask another model to re-audit the same stable code “just in case.”

## 7.6 Make low-level decisions and continue

If a low-level implementation choice is not a product decision and does not materially affect user behavior, choose a sensible option consistent with existing Wavefinity patterns and proceed.

Do not stop for user approval on minor naming, helper placement, internal data structures, or conservative printable constants unless the tradeoff is meaningful to the product.

## 7.7 Keep scope closed

Do not perform unsolicited cleanup, refactoring, formatting, documentation expansion, or neighboring feature improvements.

When the requested change works by inspection and its known requirements are satisfied, the task is done.

---

# 8. Commit/push workflow

Keep the project's cloud-first behavior, but reduce micro-checkpoint churn.

Default:

- make all edits needed for one coherent user-requested task;
- review the final diff once;
- commit once for that coherent task;
- push once.

Do not create a commit after every tiny internal edit made during the same task.

For Class C work, use checkpoint commits only at meaningful architectural recovery points. A checkpoint does not automatically trigger testing.

The objective is easy rollback without turning Git into another source of ceremony.

---

# 9. Documentation workflow

Wavefinity has useful documentation, but some older implementation plans contain historical mandatory-test instructions that should not control future routine work.

After this policy is adopted:

- `speed.md` should be treated as the authoritative development-speed/testing policy.
- Update `GEMINI.md` and the README testing section to point to or mirror this blast-radius rule.
- Historical plans such as `clean wave.md`, `split.md`, and prior B4B implementation/fix documents remain useful records of those projects, but their old “mandatory test/full suite” language is **historical**, not a standing command for future work.
- Future implementation plans should not automatically contain a “Testing” phase. Include testing only if the planned change itself meets the Class C definition.
- Keep changelog entries concise and focused on durable user-visible or architectural changes. Do not turn the changelog into a test diary.

When old instructions conflict with this policy, **the newer explicit task instructions and `speed.md` win.**

---

# 10. Quick decision rule for an LLM

Before doing any testing, ask:

> **Could this change realistically break multiple unrelated existing parts of Wavefinity outside the feature I am changing?**

- **No** → DO NOT TEST.
- **Maybe, but only because the code is new** → DO NOT TEST. Read/reason more carefully.
- **Yes, because I am changing a shared project contract or architecture with broad consumers** → Class C; perform minimal risk-directed testing.

When in doubt, default to **NO TESTING** unless you can name the specific broad existing behavior at risk.

---

# 11. Examples

### No testing

- Change a button label.
- Improve preview lighting/shadows.
- Change a default divider quantity.
- Fix one checkbox handler.
- Adjust one B4B lid dimension.
- Add one B4B-only option.
- Correct one local calculation with an obvious cause.
- Change a CSS layout.
- Add a tooltip.
- Add a local feature setting.
- Modify a test expectation because the intentionally changed behavior makes the old assertion wrong.

### Testing justified

- Change the shared wave profile or 8 mm interlock phase.
- Change `BoxSpec` semantics used by ordinary bins, B4B, preview, and export.
- Replace saved-design schema handling for all designs.
- Restructure the interior-feature package/registry/facade again.
- Rewrite shared assembly/export transforms for every generated part.
- Change a global frontend state model used by most controls.
- Replace shared layout validation used by all feature types.

---

# 12. Definition of done

For Class A/B work, done means:

- requested behavior is implemented;
- code path has been reasoned through;
- final diff contains only intended changes;
- directly affected docs are updated only if needed;
- coherent task is committed and pushed;
- **no tests were run merely for reassurance.**

For Class C work, done means the above plus the smallest verification set necessary to cover the named broad-risk contracts, within the testing limits in this document.

> **Wavefinity's development priority is fast, thoughtful iteration. Testing is an exception for broad risk, not a ritual attached to coding.**
