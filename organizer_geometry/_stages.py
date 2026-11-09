"""Cheap per-build stage timing and cooperative abandonment of a stale build.

A build (one preview request) opens :func:`build_scope`. Code inside it names
the stage it is in with :func:`stage`; time is attributed to the innermost
open stage only ("self" time), so a boolean inside a feature build counts as
``booleans`` and not twice. Time outside any named stage is ``other``.

:func:`checkpoint` is the stage-boundary hook: when the scope was given a
``superseded`` callable and it says the build is stale, the build is
abandoned by raising :class:`BuildAbandoned`. It derives from
``BaseException`` on purpose: the geometry builders turn ``Exception`` into
per-feature errors, and an abandoned build must not be reported as one.

Everything is thread-local, so concurrent builds never see each other. With no
open scope every call is a no-op.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
import functools
from typing import Callable, Iterator, TypeVar

_STATE = threading.local()
_clock = time.perf_counter


class BuildAbandoned(BaseException):
    """The build was superseded by a newer request and stopped early."""


class _Build:
    __slots__ = ("totals", "stack", "mark", "started", "superseded")

    def __init__(self, superseded: Callable[[], bool] | None) -> None:
        self.totals: dict[str, float] = {}
        self.stack: list[str] = []
        self.started = self.mark = _clock()
        self.superseded = superseded

    def _charge(self, now: float) -> None:
        name = self.stack[-1] if self.stack else "other"
        self.totals[name] = self.totals.get(name, 0.0) + (now - self.mark)
        self.mark = now

    def report(self) -> dict[str, float]:
        now = _clock()
        self._charge(now)
        stages = {name: round(seconds * 1000.0, 1) for name, seconds in self.totals.items()}
        stages["total"] = round((now - self.started) * 1000.0, 1)
        return stages


def _current() -> _Build | None:
    return getattr(_STATE, "build", None)


class BuildTimings:
    """Live view of the open build's stage totals, in milliseconds."""

    def __init__(self, build: _Build) -> None:
        self._build = build
        self._final: dict[str, float] | None = None

    def report(self) -> dict[str, float]:
        return dict(self._final) if self._final is not None else self._build.report()


@contextmanager
def build_scope(superseded: Callable[[], bool] | None = None) -> Iterator[BuildTimings]:
    """Open (or join) this thread's build. A nested scope reuses the outer
    build's clock, so its stages roll into the same report."""
    outer = _current()
    if outer is not None:
        if superseded is not None and outer.superseded is None:
            outer.superseded = superseded
        yield BuildTimings(outer)
        return
    build = _Build(superseded)
    _STATE.build = build
    handle = BuildTimings(build)
    try:
        yield handle
    finally:
        handle._final = build.report()
        _STATE.build = None


@contextmanager
def stage(name: str) -> Iterator[None]:
    """Attribute the time spent inside to ``name`` (self time)."""
    build = _current()
    if build is None:
        yield
        return
    build._charge(_clock())
    build.stack.append(name)
    try:
        yield
    finally:
        build._charge(_clock())
        build.stack.pop()


def in_preview_build() -> bool:
    """True while this thread is inside a preview build scope. Print and export
    never open one, so code that offers a faster-but-not-bit-identical route
    for the preview (same shape to ~1e-13 mm) takes it only when this is true."""
    return _current() is not None


def checkpoint() -> None:
    """Stage boundary: abandon the build if a newer request replaced it."""
    build = _current()
    if build is not None and build.superseded is not None and build.superseded():
        raise BuildAbandoned()


@contextmanager
def uninterruptible() -> Iterator[None]:
    """Let the work inside finish even if a newer request replaces the build.

    For a shared, cached piece (e.g. the snap fingers): abandoning it half way
    throws the work away, so every later edit would start it again from nothing.
    The abandon takes effect at the first checkpoint after this block.
    """
    build = _current()
    if build is None or build.superseded is None:
        yield
        return
    saved, build.superseded = build.superseded, None
    try:
        yield
    finally:
        build.superseded = saved


_F = TypeVar("_F", bound=Callable)


def staged(name: str) -> Callable[[_F], _F]:
    """Decorator form of :func:`stage` for a whole function."""
    def wrap(function: _F) -> _F:
        @functools.wraps(function)
        def inner(*args, **kwargs):
            with stage(name):
                return function(*args, **kwargs)
        return inner  # type: ignore[return-value]
    return wrap
