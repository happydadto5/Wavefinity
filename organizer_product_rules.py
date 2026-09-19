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
