# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For a Help Code Fix/correction, fetch the current coder protocol and assignment from `happydadto5/Wavefinity-Help-Code`. For work explicitly not a Help Code task, follow the generic repository workflow in `README.md`.
- **Authority:** Read [README.md](README.md) for product guidance. Current Help Code coder protocol and assignments live in the helper repository.
- **Testing:** For explicitly non-Help-Code work, the README's generic testing guidance applies.
- **Scope:** Implement the requested change, inspect the affected path and diff, use the cheapest useful verification, then commit and push. Avoid testing bureaucracy, verbose logs, and browser-driving unless the README policy says the risk justifies it.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.

## Help Code coder wake-up (Codex)
If the user's entire or near-entire message is `code chat`, `chat code`, or an obvious short near-match such as `hat code` or `check code`, treat it as the Help Code coder wake-up, not a generic request to inspect the current directory.

Before judging the workspace, fetch the helper repository's current default branch and read `CODER.md` and `reviews/code-chat.md` fresh. Follow only the Current instruction and explicitly referenced Fix/child contracts. Resolve the product repository from `help-code.config.json`; recover from a wrong, empty, unrelated, or stale cwd. Memory, old chats, local copies, and this file are never substitutes for the fresh helper read.

Do not answer “What code?” or “No code exists here” merely because the starting cwd is wrong or empty. Ask Andrew for a path only if authoritative repository access actually fails.
