# Wavefinity AI Instructions

Working rules for AI agents and coders working on Wavefinity. [README.md](README.md) is the product and architecture authority — what the project is, how it behaves, and how it is built and run. These rules govern how work is done; the product facts live in the README.

> **OWNER POLICY (2026-11-12) — WAVEFINITY IS USER-TESTED.** Coders validate their logic by reading code, callers and diffs. Do **not** write, update, repair or run automated tests; do **not** manually test the application; do **not** create user testing instructions, QA checklists or manual test plans. Implement, inspect code, commit/push and hand off. Applies to Help-Code assignments as well as direct work; request correction of any conflicting assignment rather than running tests. See '3. Owner-mandated user-tested development policy — NO CODER TESTING' under Testing below.

## Before changing code

1. Read [README.md](README.md) for project architecture and product behaviour.
2. Read the relevant contract for the task — the assigned Help Code Fix, or the plan documents under `Future plans/`.
3. Respect existing design decisions — README's Design notes record the settled numbers, what was already tried and rejected, and the traps.
4. Do not change unrelated code.

Also worth knowing before editing: the **traps** section below, and that
`.venv/`, `__pycache__/` and `generated/` are gitignored and should stay that
way.

**When given an implementation plan, review it first.** Understand what it
does and confirm that the execution is sound before beginning. If it is sound,
implement the plan and commit the completed code.

### Feature documentation contract

- `features.md` is the broad user-facing product feature catalog.
- `ai-features.md` is the compact public reference for outside AI systems used with Wavefinity AI Design.
- Any change that adds, removes, renames, or materially changes a user-facing feature must update `features.md`.
- If that change affects something an outside AI could legally choose, configure, return, or must avoid, the same change must also update `ai-features.md`.
- These documentation files explain capabilities; exact geometry constants, validation limits, and canonical schema remain code/catalog-owned.

AI Design uses [ai-features.md](ai-features.md) as its reference. Any change that adds, removes, or alters a design option must update that reference in the same change. The embedded prompt and the reference must never disagree; if they do, the change is not finished.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For a Help Code Fix/correction, fetch the current coder protocol and assignment from `happydadto5/Help-Code`. For work explicitly not a Help Code task, follow the generic repository workflow below in this file.
- **Authority:** Read [README.md](README.md) for product guidance. Current Help Code coder protocol and assignments live in the helper repository.
- **Testing:** None by coders. No automated test execution or creation, manual application checks or user test plans. The owner handles actual application testing regardless of task size.
- **Scope:** Implement the requested code change, reason carefully through affected logic, inspect callers and the changed diff, commit and push. Do not test or write a testing plan.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.

## Communication

### 1. User communication preferences
- **Operate in "caveman mode"**: keep messages simple, plain, and short.
- **User is NOT a programmer**: avoid code jargon and long technical explanations unless asked.
- **Show progress**: give a clear, general sense of progress in layman's terms.

## Scope

**One prompt may become one cohesive commit.** Keep all product code and documentation needed to complete the request together; do not split a request into artificial commits. When implementation is logically complete, inspect the changes and commit/push them. **Do not write or execute tests or produce a manual test plan for the owner, including for Help-Code assignments.** If older helper instructions demand tests, request that the assignment be corrected. Separate unrelated prompts into separate commits where practical. No feature branches or pull requests are needed for explicitly non-Help-Code local work. Help Code follows its current protocol for routing and review:

```powershell
git add -A
git commit -m "short description of what changed"
git push
```

## Testing

### 3. Owner-mandated user-tested development policy — NO CODER TESTING

**Authoritative product-wide instruction, November 12, 2026. Applies to ALL Wavefinity coders, agents, development Stories, direct work, reviews and migrations.** Older testing guidance in this README, archived discussions, developer prompts, repository tests and generic Help-Code instructions is superseded. If an incoming assignment contradicts this rule, flag the conflict and have the assignment corrected; do not silently perform tests.

**Wavefinity is a user-tested application. The owner is the application tester, not the coding LLM.**

- **Coders implement and validate their logic by reasoning and inspecting the source and diff.** Read relevant callers and data contracts; inspect types, control flow, preconditions, numerical formulas, error paths, async/state ownership, file operations, and affected call sites. Correct problems apparent from code analysis.
- **Coders DO NOT WRITE, GENERATE, MODIFY, REPAIR, OR RUN AUTOMATED TESTS.** No Python unittest/pytest, JavaScript/Node test runners, Playwright, browser automation, geometry comparison harnesses, fixture snapshots, regression sweeps, CI test gates or test-only scripts. Do not run existing test suites just because the repository contains them. Do not treat a test result as a completion requirement.
- **Coders DO NOT RUN MANUAL APPLICATION TESTS.** Do not drive browsers, simulate user interactions, click through UI flows, produce test prints, load slicers to experiment, or perform acceptance walkthroughs. The owner performs real-world application testing when and how they choose.
- **Coders DO NOT WRITE MANUAL TEST PLANS, STEP-BY-STEP QA CHECKLISTS, OR TEST REQUESTS FOR THE OWNER.** Do not append a "How to test" section, list user click sequences or ask the owner to execute a scripted acceptance matrix. The handoff should say what changed and any known limitations; the owner will try the app naturally and report issues.
- **Do not add testing scaffolding.** No new `tests/`, `browser-tests/`, `fixtures/`, `TESTING.md`, test-status logs, mock servers, throwaway harnesses or testing-only dependencies. Previously existing tests are historical artifacts, not instructions to run or expand them.
- **Do not promise that changes are proven or fully tested.** A coder may state that the implementation is logically reviewed, built/committed/pushed, and describe known unverified limitations. If logic is ambiguous, reason through it from the existing code and product rules; surface only genuine blocked decisions.
- **Code correctness still matters.** Keep runtime input validation, mesh validity checks used by the product, file-format constraints, safety boundaries, error reporting, integrity hashes, and production diagnostic output. These are application behaviors, not test suites. Avoid deleting legitimate runtime validation merely because it contains the word "validate."
- **Build steps are permitted to produce shipping assets.** Compile WASM, bundle the static site, generate required manifests and run tools needed for actual implementation. Do not turn builds into test runs, test suites or scripted acceptance checks.
- **No partial-app operability requirement during the browser-only migration.** Implement all assigned components directly and complete one final cutover. Do not add dual-mode compatibility code, interim tests or releases only to keep a partly migrated app working.

**Default coder workflow:** Understand the request and existing implementation -> reason through the exact code changes and integration points -> implement -> review the changed source/diff logically -> commit and publish safely -> report changed behavior, affected files, commit and known limitations. **Stop.** Do not add a test phase. The owner reports application bugs after using the result.

**Conflict handling:** This explicit owner instruction governs Wavefinity product development even when a generic reviewer rubric or older Fix requests automated tests. Correct the assignment or escalate a genuinely mandatory conflict. Do not infer permission to add testing from the risk or size of the change.

**No automated tests, no manual application tests and no user test plans, without exceptions based on change size.** Review code logic and changed diffs instead. The owner will use and evaluate the application.

## Browser work

There is no coder browser testing on this project: the owner policy under Testing forbids driving browsers, Playwright and manual UI walkthroughs, so there are no screenshots or test results to produce or verify. How the browser UI itself behaves is product documentation — see README.md, "Using the browser UI" and "The browser service".

## Implementation & reporting

This project is developed locally, mostly by prompting an LLM. GitHub is a
**backup, public contribution point, and record of what changed**. Outside
contributions use pull requests; the repository owner gives final approval.

Project moderators are **@happydadto5** and trusted collaborator
**@xdkaplan (adkaplan)**. The protected `main` rules keep @happydadto5 as the
final approval authority.

**After completing an implementation, commit all changes and push them to
GitHub before reporting that the work is finished.** For Help Code, follow
the freshly fetched helper coder protocol; explicitly non-Help-Code work
follows the local workflow below.

### Development handoff workflow

**Wavefinity contains the product. [Help-Code](https://github.com/happydadto5/Help-Code) contains the development protocol and Fix records.** The helper repository is private and requires authenticated access. A missing local `/fixes` directory is intentional, not evidence that a Fix is missing. Never copy, restore, or commit helper Fix records into this product repository.

| Authority | Where it lives |
| --- | --- |
| Product behavior, architecture, code and project guidance | This Wavefinity repository and README |
| Help Code workflow and role boundaries | Helper `README.md`, `help-code-state.json` and its declared overrides; Wavefinity's no-testing rule in this file (see Testing) governs product implementation |
| Current coder assignment and startup rules | Helper `reviews/code-chat.md` and `CODER.md` |
| Exact implementation behavior and evidence | Assigned active Fix or fixlet in helper `fixes/`; its master controls shared ordering/status |
| Permanent lifecycle ledger | Helper `fixes/Fix Master.md`, maintained by reviewers; coders neither read nor edit it |
| Reviewer coordination | Helper `REVIEWER-CHAT.md`; use its current transport, not an old channel path |

Use the helper's **current default branch**, freshly resolved through authenticated GitHub access. Read related authorities from the same resolved commit and record that SHA. Memory, old branches, copied plans, and unverified local files are not authority.

- **`code chat` / `chat code`** (including obvious standalone near-matches such as `hat code` or `check code`) wakes the coder: fetch the helper's current default branch and read `CODER.md` and `reviews/code-chat.md` fresh. Follow only the current instruction and explicitly referenced contract.
- **`chat`** wakes a reviewer: read helper state and `REVIEWER-CHAT.md`, then perform the reviewer work. It does not authorize coder implementation.
- **`read fix 4`** means read helper `fixes/fix-004.md`; `Fix 35A` ordinarily uses `fixes/fix-035a.md`. For fixlet bundles, follow the current assignment/master's exact paths rather than inventing names. A read/review request does not itself start implementation.
- An empty or unrelated cwd requires safe repository recovery, not a request for the PM to locate the code. If authoritative helper access actually fails, report **HELPER REPO ACCESS FAILED** with the concrete failure; never implement from a stale copy.

The helper protocol governs Help Code orchestration; the README governs product facts and project constraints; the active contract governs the assigned change within those rules. Generic non-Help-Code guidance cannot broaden a Help Code task, but the owner's no-coder-testing rule in this file applies to Wavefinity work in either workflow. If the active assignment mandates testing, request correction rather than running it.

### 2. Help Code implementation handoff

The helper repository's fresh `CODER.md` and `reviews/code-chat.md` define the coder workflow and current assignment. This product README supplies product facts and generic project guidance; it does not select a Fix or define a parallel coder protocol. The coder resolves this repository from `help-code.config.json`, preserves unrelated local work, and follows the fresh helper protocol for preparing, editing, committing, pushing, outbriefing, and reporting. Reviewers perform acceptance and closure. A historical READY file or stale ledger label never selects the coder's next job.

**Write commit messages that say why.** The history is the record. A message
that explains the reasoning is worth more here than a tidy branch structure.

### If more than one person is working in the repo

For explicitly non-Help-Code work, everyone commits to `main`, so the only rule
that matters is: **pull before you start, push as soon as you are done.** Help
Code work follows the fresh helper protocol and outside review workflow above.

```powershell
git pull --rebase        # before starting
git push                 # right after committing
```

Long-lived uncommitted work is the thing to avoid — two sessions editing
`organizer_engine.py` for a day will conflict, and geometry conflicts are
unpleasant to resolve by hand. Small, frequent, pushed commits keep that from
happening.

If a non-Help-Code push is rejected because someone else pushed first, `git pull
--rebase` then push again. If that surfaces a real conflict, resolve it and inspect
the reconciled diff carefully. No test run is called for, even after rebasing. Help Code
corrections follow current routing instructions while retaining the owner-tested policy.

## Help Code coder wake-up (Codex)
If the user's entire or near-entire message is `code chat`, `chat code`, or an obvious short near-match such as `hat code` or `check code`, treat it as the Help Code coder wake-up, not a generic request to inspect the current directory.

Before judging the workspace, fetch the helper repository's current default branch and read `CODER.md` and `reviews/code-chat.md` fresh. Follow only the Current instruction and explicitly referenced Fix/child contracts. Resolve the product repository from `help-code.config.json`; recover from a wrong, empty, unrelated, or stale cwd. Memory, old chats, local copies, and this file are never substitutes for the fresh helper read. Local checkouts are caches and GitHub `main` is authoritative: CODER.md's REMOTE FRESHNESS RULE (fetch before acting, before product edits, and again immediately before publishing; never force-push) governs.

Do not answer “What code?” or “No code exists here” merely because the starting cwd is wrong or empty. Ask Andrew for a path only if authoritative repository access actually fails.
