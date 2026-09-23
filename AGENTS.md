# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For a Help Code Fix/correction, fetch the current active fix from `happydadto5/Wavefinity-Help-Code`, obey its branch, and never implement or merge directly on target `main`. Outside chat-LLM completion review owns acceptance/integration. For work explicitly not a Help Code task, follow the generic repository workflow in `README.md`.
- **Authority:** Read and follow [README.md](README.md) before coding. It is the single shared rulebook for ChatGPT, Codex, Gemini, Anthropic, and human contributors.
- **Testing:** For a Help Code task, the active cloud fix's testing disposition wins completely. Do not infer tests from the repository's generic Class A/B/C guidance when the active Fix says no tests. For explicitly non-Help-Code work, the README's generic testing guidance applies.
- **Scope:** Implement the requested change, inspect the affected path and diff, use the cheapest useful verification, then commit and push. Avoid testing bureaucracy, verbose logs, and browser-driving unless the README policy says the risk justifies it.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.
