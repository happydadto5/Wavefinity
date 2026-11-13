# Wavefinity — instructions for AI agents

These are **working rules**, not product documentation. [README.md](README.md) is a short product overview and links to detailed references. **Do not read the entire README, all reference documents or large source files for a greeting, simple question or screenshot.** Read only what the requested task needs.

## Work modes: never confuse them

**Implementation / Story:** Read the assigned contract and relevant source; reason through control flow, callers, data contracts and the changed diff. Implement the requested change, update relevant feature documentation, commit/push, then report. **No coder-run or coder-written automated tests, manual app tests, browser QA, test scripts or test plans for the owner.** Do not run legacy tests. Shipping builds/asset generation and production runtime validation remain allowed; don't remove necessary runtime checks. This applies to Help-Code Stories, direct coding tasks and migrations. If an assignment demands coder tests, seek correction rather than quietly testing.

**Separately owner-requested UI audit:** Only when explicitly requested, explore the app with **Microsoft Playwright MCP** in isolated Chromium, normally **1920×1080 CSS pixels**. The AI chooses navigation/actions based on observed screens, rather than following prewritten click scripts. Use the disposable test service (currently port **8766**) for changes, after verifying its settings and data separation; this is practical separation, **not a proven OS security sandbox**. Never write to production on port **8765** or saved user Spaces. Read-only production screenshots need explicit owner authorization. Keep screenshots/artifacts outside the repo (e.g. `C:\AI\BrowserAudit\WavefinityTest\Screenshots`); verify actual files and visual results. Report reproduction, expected/observed behavior, console evidence and uncertainties. No source fixes, physical prints or unattended external actions as part of an audit. Audits do **not** authorize implementation-coder testing.

## Before changing product code

1. Verify the actual workspace/Git root and preserve unrelated local changes. The normal development checkout is `C:\Projects\Wavefinity`; Poller's `C:\PollerRuntime\state\dispatch\repos\Wavefinity` is a separate managed checkout, not its substitute.
2. Read the current Story/contract or explicit owner request. For Help-Code work follow the **fresh** helper protocol; for independent work follow this repository's rules.
3. Read only relevant source and the **specific** reference sections linked by [README.md](README.md). [Design notes](docs/reference/design-notes.md) preserve geometry decisions and traps; consult them when those decisions matter.
4. Keep code and related documentation cohesive and scope-limited. Review the source/diff logically, not by executing tests.

**Feature docs:** Material changes to user-facing capabilities update [features.md](features.md). If an outside AI may choose, configure, return or avoid the changed feature, also update [ai-features.md](ai-features.md) and keep the embedded AI Design prompt aligned. The implementation/catalog owns exact schemas and numerical validation limits.

## Help-Code handoff

Wavefinity contains the product; [Help-Code](https://github.com/happydadto5/Help-Code) owns the current coder/reviewer protocol and assignments. Never restore helper Fix/Story records into this product repo.

- A near-entire user message of **`code chat` / `chat code`** (including clear near-matches) wakes the coder: fetch the helper's current default branch and read `CODER.md` and `reviews/code-chat.md` **fresh**, then follow the active instruction/contract. Resolve the product checkout from `help-code.config.json`; recover an incorrect cwd instead of assuming the wrong repo. Follow helper remote-freshness rules before edits/publishing; never force-push.
- **`chat`** alone wakes the reviewer: follow fresh helper reviewer state and `REVIEWER-CHAT.md`; do not start coding.
- A read/review request is not authorization to implement. Current helper state and live assignments outrank memories, stale local copies and prior sessions. On genuine access failure, report the specific missing authority rather than guessing.

## Communication, commits and boundaries

- Speak plainly and briefly, with useful progress and clear limitations; avoid unnecessary jargon.
- For explicitly **non-Help-Code** implementation, inspect existing changes, synchronize safely with `main`, commit the intended files and push. Keep one cohesive requested change together; do not blindly `git add -A`, force-push or overwrite collaborators' work. Help-Code work follows its fresh dispatch and publication protocol.
- No unrelated refactors, branch-changing surprises, generated artifacts or credentials committed. `local-temp/`, `.venv/`, `__pycache__/`, and `generated/` are disposable/ignored local output.
- Report the change, commit/push state and anything unverified. Do not claim a preview, export or interaction works unless the evidence actually establishes it.
