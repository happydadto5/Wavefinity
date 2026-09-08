# User Communication Preferences

- Operate in "caveman mode".
- Keep messages simple, plain, and short.
- User is NOT a programmer: avoid code jargon, technical implementation details, and long explanations unless explicitly asked.
- Focus directly on results, status, and what the user needs to know.
- All code gets committed and pushed to the cloud after every change.

# Testing & Verification Policy

- DO NOT BE OBSESSED WITH TESTING. STOP ALL THE UNNECESSARY TESTING.
- For tweaks to existing code, UI tweaks, styling, wording, defaults, bug fixes, or small refactors: NEVER run tests, NEVER start the dev server, NEVER do browser checks. Read the change and reason it through.
- For genuinely new code or logic: do only ONE small, targeted test to verify the new code works. Do not run the full suite or browser check.
- We NO LONGER keep or update the TESTING.md log. It is archived in the untracked `archive/` folder.
- When in doubt, treat work as a tweak and DO NOT test.
