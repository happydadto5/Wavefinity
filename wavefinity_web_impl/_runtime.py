"""Wavefinity web server constants, locks, user-config and preference file helpers."""

from __future__ import annotations

import argparse
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid
import weakref
from http.server import ThreadingHTTPServer
from typing import Any
from organizer_engine import (
    BASE_UNIT,
    MAX_WALL,
    MIN_WALL,
    WALL_STEP,
    BoxSpec,
    LidSpec,
    StackSpec,
    lid_enabled,
)
from organizer_geometry import BuildAbandoned, build_scope, checkpoint, stage
from organizer_inserts import EDITOR_SNAP, Layout
from organizer_app import APP_DIR, design_to_dict
from organizer_features.stack import (
    STACK_MIN_WALL,
    stack_base_minimum,
    stack_effective_box,
    stack_enabled,
    validate_stack_design,
)


WEB_ROOT = APP_DIR / "web"
IMAGE_ROOT = APP_DIR / "images"
# The launcher keeps generated output and the legacy preferences file outside
# the (replaceable) runtime checkout by pointing WAVEFINITY_DATA_DIR at them.
DATA_DIR = (
    Path(os.environ["WAVEFINITY_DATA_DIR"]).expanduser().resolve()
    if os.environ.get("WAVEFINITY_DATA_DIR") else APP_DIR
)
DEFAULT_OUTPUT = DATA_DIR / "generated"
SERVER_VERSION = "1"
API_COMPAT_VERSION = 2
SERVER_INSTANCE = uuid.uuid4().hex
# Hosted builds know their commit from the platform; everything else learns it
# from the launcher's build stamp (see wavefinity_web.load_build_identity).
SERVER_BUILD = os.environ.get("RENDER_GIT_COMMIT", "unknown")[:12]
SOURCE_FILES = (
    "wavefinity_web.py", "web/index.html", "web/app.js", "web/spaces.js",
    "web/styles.css", "web/drawer-panel.js", "web/drawer-model.js",
    "web/storage-drawers.js", "web/storage-drawers-form.js",
    "web/storage-drawers-workspace.js", "web/storage-box-form.js",
    "web/structural-design.js", "web/workspace.js", "web/workspace.css",
    "images/Drawer.png",
    "images/StorageDrawers.png",
)


def source_fingerprint(root: Path = APP_DIR) -> str:
    digest = hashlib.sha256()
    for relative in SOURCE_FILES:
        path = root / relative
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(b"<present>")
            digest.update(path.read_bytes())
        else:
            digest.update(b"<missing>")
        digest.update(b"\0")
    return digest.hexdigest()[:12]


SOURCE_ROOT = str(APP_DIR.resolve())
SOURCE_FINGERPRINT = source_fingerprint()

GEOMETRY_LOCK = threading.RLock()
_PREVIEW_REQUEST_LOCK = threading.Lock()
_PREVIEW_REQUESTS: OrderedDict[tuple[str, str], tuple[int, float]] = OrderedDict()


# A superseded build stops at its next stage boundary by raising this. It is a
# BaseException (see organizer_geometry._stages) so the builders' own
# ``except Exception`` handlers never mistake it for a feature error.
_SupersededGeometry = BuildAbandoned


# Real (user-asked) preview builds in flight. Background warming waits for this
# to read zero before it starts each build, so a click is never queued behind
# a run of warming builds (Story 2720).
_REAL_PREVIEWS = 0
_REAL_PREVIEWS_LOCK = threading.Lock()


@contextmanager
def _real_preview_active():
    global _REAL_PREVIEWS
    with _REAL_PREVIEWS_LOCK:
        _REAL_PREVIEWS += 1
    try:
        yield
    finally:
        with _REAL_PREVIEWS_LOCK:
            _REAL_PREVIEWS -= 1


def _real_preview_busy() -> bool:
    return _REAL_PREVIEWS > 0


def _register_preview_request(payload: dict[str, Any], lane: str) -> tuple[str, str, int] | None:
    if not isinstance(payload, dict):
        return None
    client = payload.get("client_id")
    generation = payload.get("generation")
    if (not isinstance(client, str) or not 0 < len(client) <= 128
            or type(generation) is not int or generation < 0):
        return None
    key = (client, lane)
    now = time.monotonic()
    with _PREVIEW_REQUEST_LOCK:
        previous = _PREVIEW_REQUESTS.get(key)
        _PREVIEW_REQUESTS[key] = (max(generation, previous[0]) if previous else generation, now)
        _PREVIEW_REQUESTS.move_to_end(key)
        while _PREVIEW_REQUESTS and (len(_PREVIEW_REQUESTS) > 256
                                     or now - next(iter(_PREVIEW_REQUESTS.values()))[1] > 600):
            _PREVIEW_REQUESTS.popitem(last=False)
    return client, lane, generation


def _token_superseded(token: tuple[str, str, int] | None) -> bool:
    """True once a newer request for the same client and lane was registered."""
    if token is None:
        return False
    with _PREVIEW_REQUEST_LOCK:
        latest = _PREVIEW_REQUESTS.get(token[:2])
    return latest is not None and token[2] < latest[0]


# Preview builds no longer share one global lock (Story 2731). Ordering is per
# design view: one re-entrant lock per (client, lane), so a view never gets an
# older result after a newer one, while builds for different views run side by
# side. A small pool caps how many build at once so a burst of views cannot
# thrash the CPU. GEOMETRY_LOCK still serialises print/export work among itself.
PREVIEW_BUILD_SLOTS = max(2, min(4, os.cpu_count() or 2))
_PREVIEW_SLOTS = threading.BoundedSemaphore(PREVIEW_BUILD_SLOTS)
_VIEW_LOCKS_GUARD = threading.Lock()
_VIEW_LOCKS: "weakref.WeakValueDictionary[tuple[str, str], Any]" = weakref.WeakValueDictionary()
_PREVIEW_HELD = threading.local()
_WAIT_POLL_SECONDS = 0.05


def _view_lock(key: tuple[str, str]):
    with _VIEW_LOCKS_GUARD:
        lock = _VIEW_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _VIEW_LOCKS[key] = lock
        return lock


def _acquire_unless_superseded(lock, token) -> None:
    """Acquire ``lock``; a queued request that gets replaced leaves the queue
    instead of waiting for its turn just to be discarded."""
    while not lock.acquire(timeout=_WAIT_POLL_SECONDS):
        if _token_superseded(token):
            raise _SupersededGeometry()
    if _token_superseded(token):
        lock.release()
        raise _SupersededGeometry()


@contextmanager
def _preview_geometry_lock(token: tuple[str, str, int] | None):
    """Run a preview geometry section: ordered per view, abandoned at its next
    stage boundary if a newer request for the view arrives."""
    held = getattr(_PREVIEW_HELD, "depth", 0)
    view = _view_lock(token[:2]) if token is not None else None
    slot_taken = False
    view_taken = False
    try:
        with stage("wait"):
            if view is not None:
                _acquire_unless_superseded(view, token)
                view_taken = True
            if held == 0:
                _acquire_unless_superseded(_PREVIEW_SLOTS, token)
                slot_taken = True
        _PREVIEW_HELD.depth = held + 1
        with build_scope(lambda: _token_superseded(token)):
            checkpoint()
            yield
            checkpoint()
    finally:
        _PREVIEW_HELD.depth = held
        if slot_taken:
            _PREVIEW_SLOTS.release()
        if view_taken:
            view.release()


LEGACY_PREFERENCES_FILE = DATA_DIR / "wavefinity_prefs.json"


def _user_config_dir() -> Path:
    """The current OS user's Wavefinity settings folder."""
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / "Wavefinity"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Wavefinity"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else home / ".config") / "Wavefinity"
PREFERENCES_LOCK = threading.RLock()
EXPORT_LOCK = threading.RLock()
EXPORT_TTL_SECONDS = 15 * 60
EXPORTS: dict[str, dict[str, Any]] = {}

# (Fix 096 A5) Side-effecting operations registry. The browser's timeout only
# aborts its own wait: Python keeps running the Generate / Save / Print to
# completion in the handler thread. Every side-effecting route registered in
# A5-b runs through _idempotent_operation below: the client supplies one
# operation_id per logical operation and the registry guarantees the route
# body executes at most once per id. A duplicate id while the first request
# is running returns {"operation_status": "running"}; after completion it
# returns the stored result (or re-raises the stored error). The read-only
# /api/operation-status endpoint lets the UI poll the first request until it
# is terminal instead of showing a generic "try again".
OPERATION_LOCK = threading.RLock()
OPERATION_REGISTRY: dict[str, dict[str, Any]] = {}
OPERATION_TTL_SECONDS = 60 * 60
OPERATION_MAX_ENTRIES = 500


def _prune_operations(now: float) -> None:
    # (Fix 096 A5) Never evict a running operation: its id must keep mapping
    # to the in-flight execution until it reaches a terminal state, otherwise
    # a retried request with the same id could start a second execution.
    # Only terminal (done/error) entries are pruned.
    stale = [key for key, entry in OPERATION_REGISTRY.items()
             if entry["status"] != "running"
             and now - entry["finished_at"] > OPERATION_TTL_SECONDS]
    for key in stale:
        del OPERATION_REGISTRY[key]
    while len(OPERATION_REGISTRY) > OPERATION_MAX_ENTRIES:
        terminal = [key for key in OPERATION_REGISTRY
                    if OPERATION_REGISTRY[key]["status"] != "running"]
        if not terminal:
            break
        oldest = min(terminal,
                     key=lambda key: OPERATION_REGISTRY[key]["finished_at"])
        del OPERATION_REGISTRY[oldest]


def _idempotent_operation(route):
    """Run a side-effecting POST route at most once per client operation_id.

    The id rides inside the request payload as "operation_id". A request with
    no id, a non-string id, or an id longer than 128 characters runs exactly
    as today (pass-through): reads and legacy callers are unaffected.
    """
    def wrapped(payload):
        operation_id = payload.get("operation_id") if isinstance(payload, dict) else None
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 128:
            return route(payload)
        with OPERATION_LOCK:
            _prune_operations(time.time())
            entry = OPERATION_REGISTRY.get(operation_id)
            if entry is not None:
                if entry["status"] == "running":
                    return {"operation_id": operation_id, "operation_status": "running"}
                if entry["status"] == "done":
                    return entry["result"]
                # A stored failure re-raises in the same status class the first
                # attempt produced, so a duplicate sees the same HTTP status
                # (400 for client errors, 500 otherwise).
                if entry["error_kind"] == "client":
                    raise ValueError(entry["error"])
                raise RuntimeError(entry["error"])
            OPERATION_REGISTRY[operation_id] = {
                "status": "running", "result": None,
                "error": None, "error_kind": None, "finished_at": time.time(),
            }
        try:
            result = route(payload)
        except Exception as error:
            with OPERATION_LOCK:
                OPERATION_REGISTRY[operation_id] = {
                    "status": "error", "result": None,
                    "error": str(error) or "The earlier request failed.",
                    "error_kind": "client" if isinstance(error, (KeyError, TypeError, ValueError)) else "server",
                    "finished_at": time.time(),
                }
            raise
        with OPERATION_LOCK:
            OPERATION_REGISTRY[operation_id] = {
                "status": "done", "result": result,
                "error": None, "error_kind": None, "finished_at": time.time(),
            }
        return result
    wrapped.__name__ = getattr(route, "__name__", "operation")
    return wrapped


def operation_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only: report one side-effecting operation's state. (Fix 096 A5)"""
    operation_id = payload.get("operation_id") if isinstance(payload, dict) else None
    with OPERATION_LOCK:
        entry = OPERATION_REGISTRY.get(operation_id) if isinstance(operation_id, str) else None
    if entry is None:
        return {"operation_id": operation_id, "operation_status": "unknown"}
    if entry["status"] == "running":
        return {"operation_id": operation_id, "operation_status": "running"}
    if entry["status"] == "done":
        return {"operation_id": operation_id, "operation_status": "done", "result": entry["result"]}
    return {"operation_id": operation_id, "operation_status": "error", "error": entry["error"]}


def default_design() -> dict[str, Any]:
    box = BoxSpec(x=2 * BASE_UNIT, y=6 * BASE_UNIT, z=40.0)
    return design_to_dict(box, Layout((), "fused", EDITOR_SNAP))


def _stack_base_min_by_wall() -> dict[str, dict[str, float]]:
    """Required base thickness for every stacking wall step, by mode.

    Minimum base thickness depends on wall thickness (the foot's flare has to
    finish inside solid base material), so the browser cannot carry a fixed
    number here - it has to read the same geometry stack_base_minimum() uses.
    """
    probe = BoxSpec(x=2 * BASE_UNIT, y=6 * BASE_UNIT, z=100.0)
    table: dict[str, dict[str, float]] = {"lid": {}, "direct": {}}
    # A lid wants the lid minimum wall; a plain skirt works with any wall.
    for mode, lowest in (("lid", STACK_MIN_WALL), ("direct", MIN_WALL)):
        steps = round((MAX_WALL - lowest) / WALL_STEP)
        for i in range(steps + 1):
            wall = round(lowest + i * WALL_STEP, 3)
            box = replace(
                probe, wall=wall, standard_walls=False,
                stack=StackSpec(mode="direct") if mode == "direct" else StackSpec(),
                lid=LidSpec(enabled=True, stackable=True) if mode == "lid" else LidSpec(),
            )
            table[mode][f"{wall:g}"] = round(stack_base_minimum(box), 3)
    return table


def _read_preferences_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_preferences_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temp_file.replace(path)


CONNECTOR_SETTINGS_FILENAME = "connector_settings.json"


def _write_connector_settings_path(path: Path, settings: dict[str, Any]) -> None:
    """Atomic JSON write that never creates the parent Wavefinity folder."""
    if not path.parent.is_dir():
        raise FileNotFoundError(path.parent)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    temp_file.replace(path)


def _drop_legacy_connector_settings(current: dict[str, Any]) -> None:
    current.pop("connector_settings", None)


def _interior_work_box(box: BoxSpec) -> BoxSpec:
    """The printable body interior-feature math should size against.

    A stackable request's module-height ``box`` is not what gets printed: lid
    stacking makes the body shorter; direct stacking keeps the typed height.
    preview/export already build against ``stack_effective_box`` - every
    editor path that fits or validates interior geometry has to use the same
    body, or a part can pass Add/Edit/Fit and then fail preview/export.
    """
    if not stack_enabled(box) and not lid_enabled(box):
        return box
    validate_stack_design(box)
    return stack_effective_box(box)


class WavefinityServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a socket bind a port another process is
    # still actively LISTENing on, which would make a second launcher split
    # requests with the stale one unpredictably - so it stays off there.
    # On POSIX, SO_REUSEADDR carries no such risk: it only permits binding
    # over a socket of this launcher's own past connections still winding
    # down in TIME_WAIT, which is exactly what the launcher's own health-check
    # requests leave behind, and a bare bind() without it can otherwise
    # refuse the immediate relaunch for up to a minute.
    allow_reuse_address = os.name != "nt"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wavefinity local browser app")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--launch-token", default="",
                        help="launcher-assigned token; carried on the command line so "
                             "the launcher can correlate this process with its record")
    parser.add_argument("--check", action="store_true",
                        help="print source freshness and build identity, then exit")
    return parser
