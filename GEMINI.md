# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** Commit and push to `origin/main` after every completed task.
- **Authority:** Read and follow [README.md](README.md) before coding. It is the single shared rulebook for ChatGPT, Codex, Gemini, Anthropic, and human contributors.
- **Testing:** Strict default of **NO TESTING** as defined in [README.md](README.md). Routine work (Class A & B) requires zero tests, no test design, no dev server, no browser checks, and no screenshots. Minimal risk-directed checks are only permitted for rare Class C high-blast-radius changes.
- **Scope:** Implement the requested change, inspect the affected path and diff once, then commit and push. Do not add process, plans, tests, logs, or cleanup unless the user asks or README Class C rules require it.
