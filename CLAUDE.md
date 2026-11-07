# AI Developer Rules & Instructions

All authoritative developer and AI coding instructions are centralized in [README.md](README.md). All AI assistants (OpenAI, Anthropic, Google) follow those shared guidelines.

AI Design uses [ai-features.md](ai-features.md) as its reference. Any change that adds, removes, or alters a design option must update that reference in the same change. The embedded prompt and the reference must never disagree; if they do, the change is not finished.

## Quick Summary
- **Communication:** Operate in "caveman mode". Keep messages simple, plain, and short. User is not a programmer — avoid code jargon. Give a general sense of progress by showing steps in layman's terms.
- **Workflow:** For a Help Code Fix/correction, fetch the current coder protocol and assignment from `happydadto5/Wavefinity-Help-Code`. For work explicitly not a Help Code task, follow the generic repository workflow in `README.md`.
- **Authority:** Read [README.md](README.md) for product guidance. Current Help Code coder protocol and assignments live in the helper repository.
- **Testing:** For explicitly non-Help-Code work, the README's generic testing guidance applies.
- **Scope:** Implement the requested change, inspect the affected path and diff, use the cheapest useful verification, then commit and push. Avoid testing bureaucracy, verbose logs, and browser-driving unless the README policy says the risk justifies it.
- **Project notes:** Three coding tools (Claude, Codex/ChatGPT, Gemini) work this project. Keep project/task notes in [README.md](README.md) whenever possible so all three tools and the human see the same record. Put something in this file only if it is specific to this particular tool.

## Finishing code work
- Finish every code request by committing and pushing straight to `main`. No branch, no pull request, no asking first. Commit only your own files; leave other people's uncommitted edits alone.
- The push prints a "Changes must be made through a pull request" notice. That is a bypass-rule warning, not a failure. Check `git log origin/main --oneline -1` (or push again: "Everything up-to-date" means it landed). Only call the push failed if the new commit is missing from `origin/main`.
- End the reply by saying the commit is on `main`. Do not offer a branch or PR.

## Help Code coder wake-up
When the user's entire or near-entire message is `chat code`, `code chat`, or an obvious short typo variant such as `hat code` or `check code`, locate `happydadto5/Wavefinity-Help-Code` by repository identity. Fetch its current default branch and read `CODER.md` and `reviews/code-chat.md` fresh. Execute only the Current instruction and explicitly referenced Fix/child contracts. Resolve the product repository from `help-code.config.json` and recover from a wrong or empty starting directory. Memory, old chats, local copies, and this file are never authority for changing coder mechanics. `chat` alone is a reviewer command. Local checkouts are caches and GitHub `main` is authoritative: CODER.md's REMOTE FRESHNESS RULE (fetch before acting, before product edits, and again immediately before publishing; never force-push) governs.
