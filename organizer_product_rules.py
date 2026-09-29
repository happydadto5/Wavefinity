"""Shared Space/product constants used by Space setup and geometry modules.

No imports from ``organizer_inventory``, ``organizer_app``, ``organizer_b4b``,
or ``organizer_base_trim`` - this module is a dependency-light single source
of truth so those modules can import from it without a circular import.
"""

from __future__ import annotations

import math

from organizer_engine import (
    BASE_UNIT,
    DEFAULT_BASE_THICKNESS,
    MIN_HEIGHT_ABOVE_BASE,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
)

DRAWER_HARD_CLEARANCE_MM = 2.0 * (
    WAVE_AMPLITUDE - WAVE_MATING_GAP / 2.0
)

ORDINARY_BIN_MIN_HEIGHT_MM = math.ceil(
    DEFAULT_BASE_THICKNESS + MIN_HEIGHT_ABOVE_BASE
)

B4B_MIN_FIELD_XY = 48.0
B4B_LATCHED_MIN_HEIGHT = 16.0
STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM = 40.0

SURFACE_TRIM_PRESETS = (
    ("small", 6.5, "Small"),
    ("medium", 7.5, "Medium"),
    ("large", 10.0, "Large"),
)

SURFACE_TRIM_HEIGHTS = {
    key: value for key, value, _label in SURFACE_TRIM_PRESETS
}


def surface_trim_key_for_height(value: float, *, tolerance: float = 1e-6) -> str | None:
    for key, height in SURFACE_TRIM_HEIGHTS.items():
        if math.isclose(float(value), height, abs_tol=tolerance):
            return key
    return None


# Surface maximum organizer footprint (Fix 095). ``space.x/y`` stay the resolved
# whole-unit interior field; ``max_x_mm/max_y_mm`` keep the user's maximum
# finished OUTSIDE rectangle. outside = field + mating gap + 2 * trim width.
SURFACE_MAX_EPSILON = 1e-6


def surface_outside_extra_mm(trim_size: str) -> float:
    return WAVE_MATING_GAP + 2.0 * SURFACE_TRIM_HEIGHTS[trim_size]


def surface_field_units_for_max(max_mm: float, trim_size: str) -> int:
    """Largest whole-unit field that fits inside ``max_mm`` (never rounds up)."""
    return math.floor(
        (float(max_mm) - surface_outside_extra_mm(trim_size) + SURFACE_MAX_EPSILON) / BASE_UNIT
    )


def surface_maximums(raw, x: float, y: float, trim_size: str, *, strict: bool) -> tuple[float, float]:
    """The (max_x_mm, max_y_mm) of a Surface with field ``x`` by ``y``.

    A missing maximum is seeded in memory from the current finished outside
    footprint, so it can reproduce the current field exactly and never grow it.
    An invalid stored maximum raises when ``strict`` (a write) and is reseeded
    otherwise (a read of old or hand-edited data).
    """
    extra = surface_outside_extra_mm(trim_size)
    result = []
    for label, key, field in (("width", "max_x_mm", x), ("length", "max_y_mm", y)):
        outside = field + extra
        value = raw.get(key) if isinstance(raw, dict) else None
        if value is None or value == "":
            result.append(outside)
            continue
        problem = None
        try:
            if isinstance(value, bool):
                raise TypeError
            number = float(value)
        except (TypeError, ValueError):
            number, problem = 0.0, f"surface maximum {label} must be a number of mm"
        if problem is None and (not math.isfinite(number) or number <= 0):
            problem = f"surface maximum {label} must be a positive number of mm"
        if problem is None and number + SURFACE_MAX_EPSILON < outside:
            problem = f"surface maximum {label} is smaller than the finished Surface"
        if problem is None and surface_field_units_for_max(number, trim_size) != round(field / BASE_UNIT):
            problem = f"surface maximum {label} does not match the Surface field"
        if problem is not None:
            if strict:
                raise ValueError(problem)
            number = outside
        result.append(number)
    return result[0], result[1]
