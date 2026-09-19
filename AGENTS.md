# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For Help Code fixes, never implement directly on `main`. First run the README's mandatory remote-state gate, prove local `main` exactly equals `origin/main`, prove `origin/main:fixes/fix-###.md` exists and Fix Master is ready, then create/use the assigned `fixN` branch. Only the outside ChatGPT completion review integrates accepted fix work back to `main`.
- **Authority:** Read and follow [README.md](README.md) before coding. It is the single shared rulebook for ChatGPT, Codex, Gemini, Anthropic, and human contributors.
- **Testing:** Maximize confidence per token as defined in [README.md](README.md). Existing automated tests are encouraged when they are cheap and high-signal; targeted tests are preferred, and a fast/concise full suite is allowed when useful. Browser-driving/UI tests remain sparse and should be used only for behavior cheaper tests cannot establish.
- **Scope:** Implement the requested change, inspect the affected path and diff, use the cheapest useful verification, then commit and push. Avoid testing bureaucracy, verbose logs, and browser-driving unless the README policy says the risk justifies it.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.
