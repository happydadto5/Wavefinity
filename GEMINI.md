# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

> **OWNER POLICY (2026-11-12) — WAVEFINITY IS USER-TESTED.** Coders validate their logic by reading code, callers and diffs. Do **not** write, update, repair or run automated tests; do **not** manually test the application; do **not** create user testing instructions, QA checklists or manual test plans. Implement, inspect code, commit/push and hand off. Applies to Help-Code assignments as well as direct work; request correction of any conflicting assignment rather than running tests. See README.md section 3.

AI Design uses [ai-features.md](ai-features.md) as its reference. Any change that adds, removes, or alters a design option must update that reference in the same change. The embedded prompt and the reference must never disagree; if they do, the change is not finished.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For a Help Code Fix/correction, fetch the current active fix from `happydadto5/Wavefinity-Help-Code`, obey its branch, and never implement or merge directly on target `main`. Outside chat-LLM completion review owns acceptance/integration. For work explicitly not a Help Code task, follow the generic repository workflow in `README.md`.
- **Authority:** Read and follow [README.md](README.md) before coding. It is the single shared rulebook for ChatGPT, Codex, Gemini, Anthropic, and human contributors.
- **Testing:** None by coders. No automated test execution or creation, manual application checks or user test plans. The owner handles actual application testing regardless of task size.
- **Scope:** Implement the requested code change, reason carefully through affected logic, inspect callers and the changed diff, commit and push. Do not test or write a testing plan.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.
