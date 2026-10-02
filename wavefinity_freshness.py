"""Wavefinity source freshness gate (Fix 096 A6).

Used by Launch_Organizer_UI.bat before normal startup, and by
``python wavefinity_web.py --check``. Diagnoses the checkout and, when it is
a clean main branch that is merely behind its upstream, fast-forwards it.
Local work is never destroyed: this module never runs reset, clean, stash,
rebase, force, or checkout-overwrite.

Exit codes: 0 = launch may proceed, 2 = blocked (plain instructions already
printed), 1 = unexpected error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXPECTED_BRANCH = "main"
EXPECTED_UPSTREAM = "origin/main"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

# These exact root-level untracked files are known launcher/Git command debris,
# not Wavefinity source. They may be removed automatically; nothing else may be.
KNOWN_SAFE_ROOT_DEBRIS = {"FETCH_HEAD", "git"}


def _git(*args: str, timeout: int = 30) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    return proc.returncode, proc.stdout.strip()


def _remove_known_safe_root_debris() -> list[str]:
    """Remove only exact allowlisted untracked files at the repo root."""
    code, out = _git("ls-files", "--others", "--exclude-standard")
    if code != 0:
        return []
    untracked = {line.strip() for line in out.splitlines() if line.strip()}
    removed: list[str] = []
    for name in sorted(KNOWN_SAFE_ROOT_DEBRIS & untracked):
        path = ROOT / name
        # Never recurse into directories, and never touch anything outside ROOT.
        if not (path.is_file() or path.is_symlink()):
            continue
        try:
            path.unlink()
        except OSError:
            continue
        removed.append(name)
    return removed


def git_state() -> dict:
    """Diagnose the checkout. Changes nothing."""
    code, out = _git("rev-parse", "--is-inside-work-tree")
    if code != 0 or out != "true":
        return {"kind": "non-git", "freshness": "non-git"}
    _, toplevel = _git("rev-parse", "--show-toplevel")
    branch_code, branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    detached = branch_code != 0 or branch == "HEAD"
    head_code, head = _git("rev-parse", "HEAD")
    upstream_code, upstream = _git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    upstream = upstream if upstream_code == 0 else ""
    _, origin_url = _git("config", "--get", "remote.origin.url")
    is_wavefinity = "wavefinity" in origin_url.lower()
    status_code, porcelain = _git("status", "--porcelain")
    clean = status_code == 0 and not porcelain
    ahead = behind = 0
    if upstream:
        count_code, counts = _git("rev-list", "--left-right", "--count", "HEAD...@{u}")
        if count_code == 0 and counts:
            try:
                ahead_text, behind_text = counts.split()
                ahead, behind = int(ahead_text), int(behind_text)
            except ValueError:
                pass
    return {
        "kind": "git",
        "toplevel": toplevel or str(ROOT),
        "branch": None if detached else branch,
        "detached": detached,
        "head": head if head_code == 0 else "",
        "upstream": upstream,
        "is_wavefinity": is_wavefinity,
        "clean": clean,
        "ahead": ahead,
        "behind": behind,
    }


def _blocked(message: str) -> int:
    print(message)
    return EXIT_BLOCKED


def ensure_current() -> int:
    """Pre-launch gate. Returns a process exit code. Destroys nothing."""
    state = git_state()
    if state["kind"] == "non-git":
        print("Not a Git checkout; skipping the source update check.")
        return EXIT_OK
    if not state["is_wavefinity"]:
        print("This Git checkout is not Wavefinity; skipping the source update check.")
        return EXIT_OK

    removed = _remove_known_safe_root_debris()
    if removed:
        print("Removed known-safe launcher debris: " + ", ".join(removed))
        state = git_state()

    branch = state["branch"]
    if state["detached"]:
        head = state["head"][:12] or "unknown"
        return _blocked(
            "Wavefinity did not start: the checkout has a detached HEAD "
            f"({head}). Automatic updates are disabled for detached "
            "checkouts. Check out the main branch by hand if you want updates.")
    if not state["clean"]:
        return _blocked(
            "Wavefinity did not start: the checkout has uncommitted changes. "
            "Commit or set them aside by hand, then run the launcher again. "
            "The launcher never discards local changes.")
    upstream = state["upstream"]
    if not upstream:
        print("No upstream is configured for this branch; skipping the source update check.")
        return EXIT_OK
    if branch != EXPECTED_BRANCH or upstream != EXPECTED_UPSTREAM:
        print(f"On branch '{branch}' tracking '{upstream}'; automatic updates only "
              f"apply to {EXPECTED_BRANCH} tracking {EXPECTED_UPSTREAM}. Skipping.")
        return EXIT_OK
    fetch_code, _ = _git("fetch", "origin", timeout=90)
    if fetch_code != 0:
        print("Could not reach the update server (offline?). Launching with the "
              "current code; freshness could not be checked.")
        return EXIT_OK
    _, counts = _git("rev-list", "--left-right", "--count", "HEAD...@{u}")
    ahead = behind = 0
    if counts:
        try:
            ahead_text, behind_text = counts.split()
            ahead, behind = int(ahead_text), int(behind_text)
        except ValueError:
            pass
    if ahead and behind:
        return _blocked(
            "Wavefinity did not start: the local main branch has diverged from "
            f"origin/main ({ahead} ahead, {behind} behind). Resolve it by hand, "
            "then run the launcher again. The launcher never rebases or resets.")
    if ahead:
        return _blocked(
            "Wavefinity did not start: the local main branch is ahead of "
            f"origin/main by {ahead} commit(s). Push or set them aside by hand, "
            "then run the launcher again.")
    if not behind:
        return EXIT_OK
    merge_code, _ = _git("merge", "--ff-only", EXPECTED_UPSTREAM, timeout=90)
    if merge_code != 0:
        return _blocked(
            "Wavefinity did not start: the update could not be applied as a "
            "pure fast-forward. Resolve it by hand, then run the launcher again.")
    _, head = _git("rev-parse", "--short", "HEAD")
    print(f"Updated Wavefinity to {head} ({behind} commit(s) behind are now applied).")
    return EXIT_OK


def check_report() -> int:
    """Print the --check report. Returns a process exit code."""
    try:
        import wavefinity_web as w  # noqa: F401 (also imports organizer_app)
    except Exception as error:
        print(f"Organizer launcher NOT ready: {error}")
        return EXIT_ERROR
    print("Organizer launcher ready")
    state = git_state()
    remote_checked = True
    if state["kind"] == "git" and state["upstream"]:
        # (Fix 096 A6) --check must actually look at the remote: without a
        # fetch, "Freshness: current" would be claimed on stale data.
        # Read-only: fetch never touches the working tree.
        fetch_code, _ = _git("fetch", "origin", timeout=90)
        if fetch_code == 0:
            state = git_state()
        else:
            remote_checked = False
    if state["kind"] == "non-git":
        print("Source: " + str(ROOT))
        print("Branch: (not a Git checkout)")
        print("HEAD: (not a Git checkout)")
        print("Upstream: (not a Git checkout)")
        print("Freshness: non-git")
    else:
        # Classify only; the fetch above is read-only, nothing here changes
        # the working tree.
        if state["detached"]:
            freshness = "detached"
        elif not state["clean"]:
            freshness = "dirty"
        elif not state["upstream"]:
            freshness = "no-upstream"
        elif state["ahead"] and state["behind"]:
            freshness = "diverged"
        elif state["ahead"]:
            freshness = "ahead"
        elif state["behind"]:
            freshness = "behind"
        elif not remote_checked:
            freshness = "current (cached - remote not checked)"
        else:
            freshness = "current"
        print("Source: " + state["toplevel"])
        print("Branch: " + (state["branch"] or "(detached)"))
        print("HEAD: " + (state["head"] or "(unknown)"))
        print("Upstream: " + (state["upstream"] or "none"))
        print("Freshness: " + freshness)
    print("Fingerprint: " + w.SOURCE_FINGERPRINT)
    print("Build: " + w.SERVER_BUILD)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    if args == ["--check"]:
        return check_report()
    if args == ["--ensure-current"]:
        return ensure_current()
    print("usage: wavefinity_freshness.py [--check | --ensure-current]")
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
