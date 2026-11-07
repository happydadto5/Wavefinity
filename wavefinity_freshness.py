"""Wavefinity launcher core and source freshness report (Fix 096 A6, Story 2647).

Two jobs share this module:

* Launcher mode. activate_wavefinity_launcher.ps1 installs this file beside
  Launch_Organizer_UI.bat in %LOCALAPPDATA%/Wavefinity/Launcher/versions/<id>,
  and ``--launch`` then maintains a dedicated runtime checkout at
  C:/Projects/Wavefinity-Runtime: it verifies origin/main, stages the approved
  commit in a sibling folder, hands the port over only from a process it can
  prove it started, promotes by rename, starts the server and opens the
  browser only after the server's own health answer matches. Nothing is ever
  reset, cleaned, stashed, rebased, force-updated or deleted inside a runtime
  tree: a tree that is not a clean, current main is moved aside whole.
* Checkout mode. ``python wavefinity_web.py --check`` imports check_report to
  describe the checkout it runs from. It changes nothing.

Launcher outcomes are READY, OFFLINE_UNVERIFIED (running, but the remote could
not be checked) or STOPPED (with the specific action that recovers). Exit
codes: 0 = Wavefinity is running, 2 = stopped (plain instructions printed),
1 = unexpected error (also reported as STOPPED).

Only the standard library is used so the launcher runs before the application's
own dependencies are known to be present.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EXPECTED_BRANCH = "main"
EXPECTED_UPSTREAM = "origin/main"
EXPECTED_ORIGIN = "https://github.com/happydadto5/Wavefinity.git"

# The one server this launcher manages: a dedicated checkout, never a working
# checkout, on the loopback address and the port the app has always used.
RUNTIME_DIR = Path("C:/Projects/Wavefinity-Runtime")
HOST = "127.0.0.1"
PORT = 8765

OWNER_NAME = "wavefinity-launcher"
MARKER_NAME = "wavefinity-runtime-owner.json"
STAMP_NAME = "wavefinity-build-stamp.json"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

READY = "READY"
OFFLINE_UNVERIFIED = "OFFLINE_UNVERIFIED"
STOPPED = "STOPPED"

LOCK_WAIT_SECONDS = 120
SERVER_READY_SECONDS = 120

REQUIRED_MODULES = ("cv2", "lib3mf", "lxml", "manifold3d", "mapbox_earcut",
                    "matplotlib", "networkx", "numpy", "shapely", "trimesh")
DEPENDENCY_PINS = (
    "opencv-python-headless==5.0.0.93", "lib3mf==2.5.0", "lxml==6.1.2",
    "manifold3d==3.5.2", "mapbox-earcut==2.0.0", "matplotlib==3.11.1",
    "networkx==3.6.1", "numpy==2.5.2", "shapely==2.1.2", "trimesh==5.0.0",
)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_POWERSHELL = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                           "System32", "WindowsPowerShell", "v1.0", "powershell.exe")


class Stop(Exception):
    """A state the launcher will not act in. ``action`` says how to recover."""

    def __init__(self, message: str, action: str = "") -> None:
        super().__init__(message)
        self.action = action


class UpdateFailed(Exception):
    """Staging the approved commit failed before anything was changed."""


# ---------------------------------------------------------------- basics

def _run(cmd: list[str], *, cwd: str | None = None, timeout: int = 60,
         env: dict | None = None) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return 127, "", str(error)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _git(*args: str, timeout: int = 30, cwd: Path | None = None) -> tuple[int, str]:
    code, out, _ = _run(["git", "-C", str(cwd or ROOT), *args], timeout=timeout, env=_GIT_ENV)
    return code, out


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _unique_suffix() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)


def _local_text(iso: str) -> str:
    try:
        moment = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return str(iso)
    return moment.astimezone().strftime("%Y-%m-%d %H:%M local time")


def _norm(path: object) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _home() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise Stop("LOCALAPPDATA is not set, so the launcher cannot find its folders.",
                   "Start Wavefinity from a normal Windows user session.")
    return Path(base) / "Wavefinity"


def _state_dir() -> Path:
    return _home() / "State"


def _data_dir() -> Path:
    return _home() / "Data"


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    temp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _log_event(kind: str, **fields: object) -> None:
    """Append one line of deployment evidence; failure to log never blocks."""
    try:
        path = _state_dir() / "launcher-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": _now_iso(), "event": kind, **fields}) + "\n")
    except OSError:
        pass


def _launcher_version() -> str:
    marker = _read_json(ROOT / "launcher.json")
    return str(marker.get("version")) if marker and marker.get("version") else "unversioned"


def _same_origin(url: str) -> bool:
    def clean(value: str) -> str:
        return re.sub(r"(\.git)?/*$", "", value.strip().lower())
    return clean(url) == clean(EXPECTED_ORIGIN)


# ---------------------------------------------------------------- processes

def _processes(pid: int | None = None) -> list[dict]:
    """Running processes with creation time, executable and command line."""
    where = f" -Filter 'ProcessId={int(pid)}'" if pid is not None else ""
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
        f"Get-CimInstance Win32_Process{where} | ForEach-Object {{ [pscustomobject]@{{ "
        "pid=[int]$_.ProcessId; ppid=[int]$_.ParentProcessId; "
        "created=$(if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {''}); "
        "exe=$_.ExecutablePath; cmd=$_.CommandLine } } | ConvertTo-Json -Compress"
    )
    code, out, err = _run([_POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", script], timeout=60)
    if code != 0:
        raise Stop("Windows would not list running processes, so process identity cannot be proven "
                   f"({err or 'no detail'}). Nothing was touched.",
                   "Run the launcher again; if it repeats, restart Windows Management Instrumentation.")
    if not out:
        return []
    try:
        data = json.loads(out)
    except ValueError:
        raise Stop("Windows returned an unreadable process list; nothing was touched.",
                   "Run the launcher again.")
    return data if isinstance(data, list) else [data]


def _process_info(pid: int) -> dict | None:
    found = _processes(pid)
    return found[0] if found else None


def _listening_pids(port: int) -> list[int]:
    code, out, err = _run(["netstat", "-ano"], timeout=20)
    if code != 0:
        raise Stop(f"netstat failed ({err or 'no detail'}), so the owner of port {port} cannot be determined.",
                   "Run the launcher again.")
    found: set[int] = set()
    for line in out.splitlines():
        parts = line.split()
        if (len(parts) >= 5 and parts[0] == "TCP" and parts[3] == "LISTENING"
                and parts[1].rsplit(":", 1)[-1] == str(port)):
            with contextlib.suppress(ValueError):
                found.add(int(parts[4]))
    return sorted(found)


def _health(timeout: float = 2.0) -> dict | None:
    try:
        with _OPENER.open(f"http://{HOST}:{PORT}/api/health", timeout=timeout) as response:
            data = json.loads(response.read())
    except Exception:
        return None
    return data if isinstance(data, dict) and data.get("ok") else None


def _instance_path() -> Path:
    return _state_dir() / "instance.json"


def inspect_listener() -> dict:
    """Classify whatever listens on the Wavefinity port. Changes nothing.

    "owned" requires the whole chain to agree: exactly one listener; the
    launcher's own record names that PID *and* its creation time, executable
    and command line; the command line is the runtime's server with the
    recorded token; and /api/health reports the same token, commit and path.
    A PID file or a health answer alone proves nothing.
    """
    pids = _listening_pids(PORT)
    if not pids:
        return {"kind": "free"}
    if len(pids) > 1:
        return {"kind": "foreign", "pid": pids[0],
                "reason": "several processes listen on port %d (%s)" % (PORT, ", ".join(map(str, pids)))}
    pid = pids[0]
    info = _process_info(pid)
    health = _health()
    record = _read_json(_instance_path())

    def foreign(reason: str) -> dict:
        return {"kind": "foreign", "pid": pid, "reason": reason,
                "exe": (info or {}).get("exe"), "source_root": (health or {}).get("source_root")}

    if info is None:
        return foreign("its process details could not be read")
    if health is None:
        return foreign("it does not answer as Wavefinity")
    if not record:
        return foreign("the launcher has no record of starting it")
    if record.get("pid") != pid or record.get("created") != info.get("created"):
        return foreign("its process id and start time do not match the launcher's record")
    if _norm(record.get("exe") or "") != _norm(info.get("exe") or "") or record.get("cmd") != info.get("cmd"):
        return foreign("its program or command line differs from the launcher's record")
    cmd = (info.get("cmd") or "").lower().replace("/", "\\")
    script = str(RUNTIME_DIR / "wavefinity_web.py").lower().replace("/", "\\")
    token = str(record.get("token") or "")
    if not token or token.lower() not in cmd or script not in cmd:
        return foreign("its command line is not the runtime server started by the launcher")
    if (health.get("launch_token") != token or health.get("commit") != record.get("commit")
            or _norm(health.get("runtime_path") or "") != _norm(RUNTIME_DIR)):
        return foreign("its health answer does not carry the launcher's token, commit and path")
    return {"kind": "owned", "pid": pid, "info": info, "record": record, "health": health}


def _stop_owned(listener: dict) -> None:
    """Stop a launcher-owned server, re-proving ownership immediately before."""
    again = inspect_listener()
    if again.get("kind") != "owned" or again["pid"] != listener["pid"]:
        raise Stop("The running Wavefinity server could not be re-confirmed as started by this launcher "
                   "just before replacing it, so it was left running.",
                   "Close that Wavefinity server yourself, then launch again.")
    _run(["taskkill", "/PID", str(listener["pid"]), "/T", "/F"], timeout=30)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if not _listening_pids(PORT) and _health(0.5) is None:
            _log_event("stopped-owned-server", pid=listener["pid"], commit=listener["record"].get("commit"))
            with contextlib.suppress(OSError):
                _instance_path().replace(_state_dir() / "instance.stopped.json")
            return
        time.sleep(0.3)
    raise Stop("The old Wavefinity server did not stop within 20 seconds.",
               "End the Wavefinity process in Task Manager, then launch again.")


def _runtime_users() -> list[str]:
    """Processes whose program or command line mention the runtime folder."""
    needle = re.compile(re.escape(str(RUNTIME_DIR).lower().replace("/", "\\")) + r"(?![\w.\-])")
    users = []
    for proc in _processes():
        if proc.get("pid") == os.getpid():
            continue
        for text in (proc.get("exe"), proc.get("cmd")):
            if text and needle.search(str(text).lower().replace("/", "\\")):
                users.append(f"pid {proc.get('pid')}: {proc.get('cmd') or proc.get('exe')}")
                break
    return users


def _wait_runtime_free(seconds: int = 15) -> list[str]:
    """Users of the runtime folder, after giving just-stopped processes time to exit."""
    deadline = time.monotonic() + seconds
    while True:
        users = _runtime_users()
        if not users or time.monotonic() >= deadline:
            return users
        time.sleep(1)


# ---------------------------------------------------------------- launch lock

class _LaunchLock:
    """Cross-process launch lock shared with activate_wavefinity_launcher.ps1.

    Exclusion is an OS byte-range lock, so it is released the moment the
    owner dies and can never be stolen while the owner lives. The owner's PID,
    start time and role are written alongside for validation and for the
    message shown to anyone who has to wait. Waiting longer than
    LOCK_WAIT_SECONDS stops the launch; it never breaks a live lock.
    """

    OFFSET = 1_000_000
    BLOCK = 4096

    def __init__(self, path: Path, role: str) -> None:
        self.path, self.role, self.fd = path, role, None

    def _try_lock(self, fd: int) -> bool:
        try:
            if os.name == "nt":
                import msvcrt
                os.lseek(fd, self.OFFSET, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _owner_text(self) -> str:
        try:
            owner = json.loads(self.path.read_bytes()[: self.BLOCK].decode("utf-8", "replace").strip() or "{}")
        except (OSError, ValueError):
            return "an unknown process"
        if not isinstance(owner, dict) or "pid" not in owner:
            return "an unknown process"
        try:
            info = _process_info(int(owner["pid"]))
            alive = bool(info and info.get("created") == owner.get("created"))
        except (Stop, ValueError):
            alive = None
        state = {True: "running", False: "no longer running; the lock is still held by an inherited handle",
                 None: "state unknown"}[alive]
        return f"{owner.get('role', 'a launcher task')} (pid {owner.get('pid')}, started {owner.get('started')}, {state})"

    def __enter__(self) -> "_LaunchLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
            if self._try_lock(fd):
                break
            os.close(fd)
            if time.monotonic() >= deadline:
                raise Stop("Another Wavefinity launch or launcher update is in progress: " + self._owner_text() + ".",
                           "Wait for it to finish and launch again. If it is stuck, close it yourself; "
                           "the launcher never takes over a live lock.")
            time.sleep(1)
        info = next(iter(_processes(os.getpid())), {})
        owner = {"pid": os.getpid(), "created": info.get("created", ""), "role": self.role, "started": _now_iso()}
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, json.dumps(owner).encode("utf-8").ljust(self.BLOCK))
        self.fd = fd
        return self

    def __exit__(self, *exc: object) -> None:
        if self.fd is None:
            return
        with contextlib.suppress(OSError):
            if os.name == "nt":
                import msvcrt
                os.lseek(self.fd, self.OFFSET, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        os.close(self.fd)
        self.fd = None


# ---------------------------------------------------------------- environment

def _check_environment() -> None:
    if os.name != "nt":
        raise Stop("The Wavefinity launcher runs on Windows only.")
    if shutil.which("git") is None:
        raise Stop("Git was not found.", "Install Git for Windows, then launch again.")
    env_root = _home() / "Env"
    if _norm(Path(sys.executable).parent.parent) != _norm(env_root):
        raise Stop(f"The launcher is not running from its managed Python environment ({env_root}).",
                   "Run activate_wavefinity_launcher.ps1 from the approved Wavefinity checkout.")
    if not Path(sys.executable).with_name("pythonw.exe").is_file():
        raise Stop("The managed Python environment has no pythonw.exe.",
                   "Run activate_wavefinity_launcher.ps1 again to rebuild it.")
    code, _, err = _run([sys.executable, "-I", "-c", "import " + ", ".join(REQUIRED_MODULES)],
                        cwd=str(_home()), timeout=120)
    if code != 0:
        raise Stop("Required Python packages are missing from the managed environment "
                   f"({err.splitlines()[-1] if err else 'import failed'}).",
                   "Run activate_wavefinity_launcher.ps1 again; it reinstalls the pinned packages.")
    mapping = _read_json(_data_dir() / "data-map.json")
    if not _data_dir().is_dir() or not mapping or _norm(mapping.get("runtime_data_dir") or "") != _norm(_data_dir()):
        raise Stop("Wavefinity's data folder mapping is missing or does not match this machine, so existing "
                   "documents and settings cannot be accounted for.",
                   "Run activate_wavefinity_launcher.ps1 again; it inventories and maps the legacy data.")


# ---------------------------------------------------------------- runtime checkout

def _marker_path(tree: Path) -> Path:
    return tree / ".git" / MARKER_NAME


def inspect_runtime() -> dict:
    """Classify the runtime folder. Changes nothing.

    Returns {"kind": "absent"} or {"kind": "owned", head, branch, problems}.
    Anything not provably this launcher's own checkout raises Stop and is not
    touched. ``problems`` lists why an owned tree cannot simply be updated.
    """
    path = RUNTIME_DIR
    if not os.path.lexists(path):
        return {"kind": "absent"}
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    if os.path.islink(path) or attributes & 0x400:
        raise Stop(f"{path} is a link or junction, not a real folder; it was left untouched.",
                   "Remove the link yourself or move it away, then launch again.")
    if not path.is_dir():
        raise Stop(f"{path} exists but is not a folder; it was left untouched.",
                   "Rename or remove it yourself, then launch again.")
    if _norm(os.path.realpath(path)) != _norm(path):
        raise Stop(f"{path} does not resolve to its own canonical path; it was left untouched.",
                   "Fix the folder redirection yourself, then launch again.")
    marker = _read_json(_marker_path(path))
    if not marker or marker.get("owner") != OWNER_NAME or not _same_origin(str(marker.get("origin") or "")):
        raise Stop(f"{path} exists but is not marked as a Wavefinity launcher runtime; it was left untouched.",
                   "Rename or move that folder yourself, then launch again. The launcher never moves "
                   "a folder it did not create.")
    code, url = _git("config", "--get", "remote.origin.url", cwd=path)
    if code != 0 or not _same_origin(url):
        raise Stop(f"{path} has origin '{url or 'none'}', not {EXPECTED_ORIGIN}; it was left untouched.",
                   "Rename or move that folder yourself, then launch again.")
    branch_code, branch = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=path)
    head_code, head = _git("rev-parse", "HEAD", cwd=path)
    status_code, porcelain = _git("status", "--porcelain", "--untracked-files=all", cwd=path, timeout=120)
    if branch_code or head_code or status_code or not _HEX40.fullmatch(head):
        raise Stop(f"Git could not read the state of {path}; it was left untouched.",
                   "Check that folder with Git by hand, or rename it, then launch again.")
    problems = []
    if branch == "HEAD":
        problems.append("it has a detached HEAD")
    elif branch != EXPECTED_BRANCH:
        problems.append(f"it is on branch '{branch}' instead of {EXPECTED_BRANCH}")
    if porcelain:
        problems.append("it has uncommitted or untracked files")
    return {"kind": "owned", "head": head, "branch": branch, "problems": problems}


def _trusted_stamp(runtime: dict) -> dict | None:
    """The previous launch's build stamp, if it truly describes this tree."""
    stamp = _read_json(RUNTIME_DIR / ".git" / STAMP_NAME)
    if (stamp and runtime["kind"] == "owned" and stamp.get("commit") == runtime["head"]
            and stamp.get("branch") == EXPECTED_BRANCH and stamp.get("verified_at")
            and _norm(stamp.get("runtime_path") or "") == _norm(RUNTIME_DIR)):
        return stamp
    return None


def remote_head() -> tuple[str | None, str]:
    """origin/main as GitHub reports it now, or (None, reason) when unreachable."""
    home = _home()
    home.mkdir(parents=True, exist_ok=True)
    code, out, err = _run(["git", "ls-remote", "--exit-code", EXPECTED_ORIGIN, "refs/heads/main"],
                          cwd=str(home), timeout=45, env=_GIT_ENV)
    if code == 0:
        match = re.match(r"([0-9a-f]{40})\s+refs/heads/main$", out.splitlines()[0] if out else "")
        if match:
            return match.group(1), ""
    elif code == 2:
        raise Stop(f"{EXPECTED_ORIGIN} answered but has no main branch.",
                   "Check the repository on GitHub; the launcher will not guess another branch.")
    return None, (err.splitlines()[-1] if err else "no answer from GitHub")


def _discard_stage(stage: Path) -> None:
    """Delete a staging folder this launcher created itself; nothing else."""
    if stage.parent != RUNTIME_DIR.parent or not stage.name.startswith(RUNTIME_DIR.name + ".staging-"):
        return

    def writable(func, path, _error):
        os.chmod(path, 0o700)
        func(path)

    option = "onexc" if sys.version_info >= (3, 12) else "onerror"
    with contextlib.suppress(OSError):
        shutil.rmtree(stage, **{option: writable})


def stage_runtime(source: Path | None) -> tuple[Path, str]:
    """Build a clean checkout of the fetched origin/main in a sibling folder.

    Cloning from the existing runtime reuses its objects but copies none of
    its working files; the clone's origin is reset to the real remote and
    fetched, so the pinned commit is exactly what this fetch resolved.
    """
    stage = RUNTIME_DIR.with_name(f"{RUNTIME_DIR.name}.staging-{_unique_suffix()}")
    if os.path.lexists(stage):
        raise Stop(f"{stage} already exists; nothing was changed.", "Launch again.")
    steps = [
        ["git", "clone", "--no-checkout", "--quiet", str(source or EXPECTED_ORIGIN), str(stage)],
        ["git", "-C", str(stage), "remote", "set-url", "origin", EXPECTED_ORIGIN],
        ["git", "-C", str(stage), "fetch", "--quiet", "origin", "main"],
    ]
    try:
        for step in steps:
            code, _, err = _run(step, timeout=900, env=_GIT_ENV)
            if code != 0:
                raise UpdateFailed(f"Fetching origin/main failed ({err.splitlines()[-1] if err else 'no detail'}).")
        code, commit = _git("rev-parse", "refs/remotes/origin/main", cwd=stage)
        if code or not _HEX40.fullmatch(commit):
            raise UpdateFailed("The fetch did not produce origin/main.")
        code, _, err = _run(["git", "-C", str(stage), "checkout", "--quiet", "-B", EXPECTED_BRANCH, "origin/main"],
                            timeout=600, env=_GIT_ENV)
        head_code, head = _git("rev-parse", "HEAD", cwd=stage)
        _, dirt = _git("status", "--porcelain", "--untracked-files=all", cwd=stage, timeout=120)
        if code or head_code or head != commit or dirt:
            raise UpdateFailed("The staged checkout is not a clean copy of origin/main.")
        _write_json_atomic(_marker_path(stage), {"owner": OWNER_NAME, "origin": EXPECTED_ORIGIN,
                                                 "schema": 1, "created": _now_iso()})
    except BaseException:
        _discard_stage(stage)
        raise
    return stage, commit


def _promote(stage: Path, runtime: dict, problems: list[str]) -> None:
    """Move the old tree aside whole, then rename the staged tree into place."""
    users = _wait_runtime_free() if runtime["kind"] == "owned" else []
    if users:
        _discard_stage(stage)
        raise Stop("These processes still use the Wavefinity runtime folder, so it was not replaced:\n  "
                   + "\n  ".join(users),
                   "Close them (including any window or terminal opened inside that folder), then launch again.")
    aside = None
    if runtime["kind"] == "owned":
        kind = "preserved" if problems else "previous"
        aside = RUNTIME_DIR.with_name(f"{RUNTIME_DIR.name}.{kind}-{_unique_suffix()}")
        if os.path.lexists(aside):
            _discard_stage(stage)
            raise Stop(f"{aside} already exists; nothing was moved.", "Launch again.")
        try:
            os.rename(RUNTIME_DIR, aside)
        except OSError as error:
            _discard_stage(stage)
            raise Stop(f"The runtime folder could not be moved aside ({error}); it is still in place and "
                       "nothing was changed.",
                       "Close whatever is using C:/Projects/Wavefinity-Runtime, then launch again.")
        _log_event("runtime-moved-aside", preservation_kind=kind, source=str(RUNTIME_DIR), preserved_as=str(aside),
                   head=runtime.get("head"), branch=runtime.get("branch"), reasons=problems)
    try:
        for attempt in range(11):
            try:
                os.rename(stage, RUNTIME_DIR)
                break
            except PermissionError:
                if attempt == 10:
                    raise
                time.sleep(0.5)
    except OSError as error:
        if aside is not None:
            with contextlib.suppress(OSError):
                os.rename(aside, RUNTIME_DIR)
        raise Stop(f"The staged runtime could not be moved into place ({error}).",
                   f"The staged copy is at {stage}; the previous runtime was "
                   + ("restored." if aside is not None and RUNTIME_DIR.exists() else "not present."))
    if aside is not None and problems:
        print(f"Preserved the previous runtime folder intact at: {aside}")
        print("Reason: " + "; ".join(problems) + ". It was moved, not changed or deleted.")


def _write_stamp(commit: str, branch: str, verified_at: str, token: str) -> None:
    _write_json_atomic(RUNTIME_DIR / ".git" / STAMP_NAME, {
        "commit": commit, "branch": branch, "verified_at": verified_at,
        "runtime_path": str(RUNTIME_DIR), "token": token, "created": _now_iso(),
        "launcher_version": _launcher_version(),
    })


def start_server(commit: str, branch: str, verified_at: str) -> dict:
    """Start the runtime server, then require its own health to match."""
    if _listening_pids(PORT):
        raise Stop(f"Port {PORT} is occupied; the server was not started.", "Launch again.")
    token = secrets.token_hex(16)
    _write_stamp(commit, branch, verified_at, token)
    script = RUNTIME_DIR / "wavefinity_web.py"
    state = _state_dir()
    state.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1",
               WAVEFINITY_DATA_DIR=str(_data_dir()), WAVEFINITY_PID_FILE=str(state / "server.pid"))
    env.pop("WAVEFINITY_STATUS_FILE", None)
    command = [str(Path(sys.executable).with_name("pythonw.exe")), str(script), "--no-browser",
               "--host", HOST, "--port", str(PORT), "--launch-token", token]
    with (state / "server.log").open("ab") as log:
        spawned = subprocess.Popen(
            command, cwd=str(RUNTIME_DIR), env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=0x00000008 | 0x00000200,  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
    spawned_info = _process_info(spawned.pid)

    def abandon(reason: str, action: str) -> Stop:
        # Only the process just spawned (same PID and start time) is ever ended here.
        if spawned_info and (_process_info(spawned.pid) or {}).get("created") == spawned_info.get("created"):
            _run(["taskkill", "/PID", str(spawned.pid), "/T", "/F"], timeout=30)
        return Stop(reason, action)

    deadline = time.monotonic() + SERVER_READY_SECONDS
    health = None
    while time.monotonic() < deadline:
        if spawned.poll() is not None:
            raise Stop(f"The Wavefinity server exited during startup (code {spawned.returncode}).",
                       f"Read {state / 'server.log'}, fix the cause, then launch again.")
        health = _health(1.5)
        if health and health.get("launch_token") == token:
            break
        time.sleep(0.5)
    else:
        raise abandon(f"The Wavefinity server did not answer within {SERVER_READY_SECONDS} seconds.",
                      f"Read {state / 'server.log'}, then launch again.")
    if (health.get("commit") != commit or health.get("branch") != branch
            or _norm(health.get("runtime_path") or "") != _norm(RUNTIME_DIR)):
        raise abandon("The server answered, but not as the intended build "
                      f"(commit {health.get('commit')}, path {health.get('runtime_path')}).",
                      "Launch again; if it repeats, the runtime folder needs inspection.")
    pids = _listening_pids(PORT)
    info = _process_info(pids[0]) if len(pids) == 1 else None
    cmd = ((info or {}).get("cmd") or "").lower().replace("/", "\\")
    if not info or token not in cmd or str(script).lower().replace("/", "\\") not in cmd:
        raise abandon("The process holding the port could not be matched to the server just started.",
                      "Launch again; if it repeats, close any other Wavefinity window first.")
    record = {
        "pid": info["pid"], "created": info["created"], "exe": info["exe"], "cmd": info["cmd"],
        "parent_pid": info.get("ppid"), "spawned_pid": spawned.pid, "token": token, "commit": commit,
        "branch": branch, "verified_at": verified_at, "runtime_path": str(RUNTIME_DIR), "port": PORT,
        "started_at": _now_iso(), "launcher_version": _launcher_version(),
    }
    _write_json_atomic(_instance_path(), record)
    _log_event("server-started", pid=record["pid"], commit=commit, token=token)
    return record


def _ensure_poller() -> None:
    """Fix 119 B2: best-effort, unwaited request that the NN Poller is running."""
    shim = RUNTIME_DIR / "Start_Wavefinity_Dispatch_Runner_Hidden.vbs"
    if not shim.is_file():
        return
    with contextlib.suppress(OSError):
        subprocess.Popen([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "wscript.exe"), str(shim)],
                         cwd=str(_home()), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)


# ---------------------------------------------------------------- launch flow

def _open_browser(record: dict, open_browser: bool) -> str:
    url = f"http://{HOST}:{PORT}/?build={str(record['commit'])[:12]}"
    if open_browser:
        webbrowser.open(url)
    return url


def _online(runtime: dict, listener: dict, remote: str, open_browser: bool) -> tuple[str, list[str]]:
    verified_at = _now_iso()
    problems = list(runtime.get("problems", []))
    if runtime["kind"] == "owned" and not problems and runtime["head"] == remote:
        if listener["kind"] == "owned" and listener["record"].get("commit") == remote:
            record = listener["record"]
        else:
            if listener["kind"] == "owned":
                _stop_owned(listener)
            record = start_server(remote, EXPECTED_BRANCH, verified_at)
        commit = remote
    else:
        stage, commit = stage_runtime(RUNTIME_DIR if runtime["kind"] == "owned" else None)
        if runtime["kind"] == "owned" and not problems and runtime["head"] != commit:
            code, _ = _git("merge-base", "--is-ancestor", runtime["head"], "refs/remotes/origin/main", cwd=stage)
            if code != 0:
                problems.append("it has commits that are not on origin/main, or its history cannot be compared")
        if listener["kind"] == "owned":
            _stop_owned(listener)
        _promote(stage, runtime, problems)
        record = start_server(commit, EXPECTED_BRANCH, verified_at)
    url = _open_browser(record, open_browser)
    _ensure_poller()
    return READY, [
        f"READY - Wavefinity {commit[:12]} ({EXPECTED_BRANCH}) is running.",
        f"Verified against origin/main on {_local_text(verified_at)}; later changes are not reflected until the next launch.",
        f"Runtime: {RUNTIME_DIR}",
        f"Address: {url}",
    ]


def _offline(runtime: dict, listener: dict, reason: str, open_browser: bool) -> tuple[str, list[str]]:
    recover = "Connect to the internet and launch again."
    if runtime["kind"] != "owned":
        raise Stop(f"{reason} Wavefinity has not been installed yet, so there is nothing safe to run.", recover)
    if runtime["problems"]:
        raise Stop(f"{reason} The runtime checkout cannot be trusted without an update check: "
                   + "; ".join(runtime["problems"]) + ".", recover)
    stamp = _trusted_stamp(runtime)
    if not stamp:
        raise Stop(f"{reason} The runtime checkout has no trustworthy record of when it was last verified.", recover)
    if listener["kind"] == "owned" and listener["record"].get("commit") == runtime["head"]:
        record = listener["record"]
    else:
        if listener["kind"] == "owned":
            _stop_owned(listener)
        record = start_server(runtime["head"], EXPECTED_BRANCH, stamp["verified_at"])
    url = _open_browser(record, open_browser)
    _ensure_poller()
    return OFFLINE_UNVERIFIED, [
        f"RUNNING UNVERIFIED - {reason}",
        f"Wavefinity {runtime['head'][:12]} was last verified against origin/main on {_local_text(stamp['verified_at'])}. "
        "It may not be the newest version.",
        f"Address: {url}",
        "Action: connect to the internet and launch again to check for updates.",
    ]


def _check_report_lines(runtime: dict, listener: dict, remote: str | None, why: str) -> list[str]:
    lines = [f"Launcher: {_launcher_version()}", f"Runtime folder: {RUNTIME_DIR}"]
    if runtime["kind"] == "absent":
        lines.append("Runtime: not installed (the next launch creates it)")
    else:
        lines.append(f"Runtime: {runtime['head']} on {runtime['branch']}")
        lines.append("Runtime state: " + ("clean" if not runtime["problems"] else "; ".join(runtime["problems"])))
        stamp = _trusted_stamp(runtime)
        lines.append("Build stamp: " + (f"verified {_local_text(stamp['verified_at'])}" if stamp else "missing or untrusted"))
    lines.append("origin/main: " + (remote if remote else f"unreachable ({why})"))
    if listener["kind"] == "free":
        lines.append(f"Port {PORT}: free")
    elif listener["kind"] == "owned":
        lines.append(f"Port {PORT}: launcher-owned server pid {listener['pid']} running "
                     f"{str(listener['record'].get('commit'))[:12]}")
    else:
        lines.append(f"Port {PORT}: NOT launcher-owned (pid {listener.get('pid')}): {listener['reason']}")
    return lines


def _launch(open_browser: bool, check_only: bool) -> tuple[str, list[str]]:
    with _LaunchLock(_state_dir() / "launch.lock", "launch"):
        _check_environment()
        runtime = inspect_runtime()
        listener = inspect_listener()
        if listener["kind"] == "foreign":
            where = listener.get("exe") or listener.get("source_root") or "unknown program"
            if check_only:
                remote, why = remote_head()
                return STOPPED, _check_report_lines(runtime, listener, remote, why)
            raise Stop(f"Port {PORT} is held by process {listener.get('pid')} ({where}), and it is not a "
                       f"Wavefinity server this launcher started: {listener['reason']}. It was not touched.",
                       f"Close that program or Wavefinity window yourself (for example an older Wavefinity "
                       f"started from a checkout), then launch again.")
        remote, why = remote_head()
        if check_only:
            return READY, _check_report_lines(runtime, listener, remote, why)
        if remote:
            try:
                return _online(runtime, listener, remote, open_browser)
            except UpdateFailed as failure:
                why = str(failure)
        return _offline(runtime, listener, f"The update check did not complete: {why}", open_browser)


def _status_file() -> Path:
    given = os.environ.get("WAVEFINITY_STATUS_FILE")
    return Path(given) if given else _home() / "Launcher" / "status" / "last-launch.txt"


def _emit(state: str, lines: list[str], record_status: bool) -> None:
    for line in lines:
        print(line)
    if not record_status:
        return
    try:
        path = _status_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + ".tmp")
        temp.write_bytes(("\r\n".join([state, *lines]) + "\r\n").encode("ascii", "replace"))
        os.replace(temp, path)
    except OSError:
        pass


def launch(*, open_browser: bool = True, check_only: bool = False) -> int:
    try:
        state, lines = _launch(open_browser, check_only)
    except Stop as stop:
        lines = ["STOPPED - " + str(stop)]
        if stop.action:
            lines.append("Action: " + stop.action)
        _log_event("stopped", message=str(stop), action=stop.action)
        _emit(STOPPED, lines, not check_only)
        return EXIT_BLOCKED
    except Exception as error:  # reported, never swallowed silently
        _log_event("error", message=repr(error))
        _emit(STOPPED, [f"STOPPED - Unexpected launcher error: {error!r}",
                        "Action: launch again; if it repeats, report this message."], not check_only)
        return EXIT_ERROR
    _emit(state, lines, not check_only)
    return EXIT_BLOCKED if state == STOPPED else EXIT_OK


def ensure_dependencies() -> int:
    """Install the pinned packages into the running (managed) interpreter."""
    probe = [sys.executable, "-I", "-c", "import " + ", ".join(REQUIRED_MODULES)]
    if _run(probe, cwd=str(ROOT.parent), timeout=120)[0] == 0:
        print("Wavefinity dependencies are present.")
        return EXIT_OK
    print("Installing the pinned Wavefinity dependencies...")
    code = subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *DEPENDENCY_PINS])
    if code != 0 or _run(probe, cwd=str(ROOT.parent), timeout=120)[0] != 0:
        print("Wavefinity dependencies could not be installed.")
        return EXIT_ERROR
    return EXIT_OK


def self_check() -> int:
    print(f"Wavefinity launcher {_launcher_version()}: module loads under Python {sys.version.split()[0]}")
    return EXIT_OK


# ---------------------------------------------------------------- checkout report

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
    # Notes and reports (*.md) never block a launch; any other change does.
    def _counts(line: str) -> bool:
        paths = line[3:].split(" -> ")
        return not all(one.strip().strip('"').lower().endswith(".md") for one in paths)

    clean = status_code == 0 and not any(
        _counts(line) for line in porcelain.splitlines() if line.strip()
    )
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
    print("Commit: " + w.BUILD_IDENTITY["commit"])
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")
    in_checkout = (ROOT / "wavefinity_web.py").is_file()
    if args == ["--check"]:
        return check_report() if in_checkout else launch(check_only=True)
    if args in (["--launch"], ["--launch", "--no-browser"]):
        if in_checkout and not (ROOT / "launcher.json").is_file():
            print("This is a source checkout, not the installed launcher; it never starts a server. "
                  "Use the installed Wavefinity shortcut (activate_wavefinity_launcher.ps1 installs it).")
            return EXIT_BLOCKED
        return launch(open_browser="--no-browser" not in args)
    if args == ["--ensure-dependencies"]:
        return ensure_dependencies()
    if args == ["--self-check"]:
        return self_check()
    print("usage: wavefinity_freshness.py [--check | --launch [--no-browser] | --ensure-dependencies | --self-check]")
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
