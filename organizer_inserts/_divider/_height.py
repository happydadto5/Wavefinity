"""Divider height as a percentage pick of the bin's usable height."""

from __future__ import annotations

from .._core import connector_keep_out

# (percent, label) - the only choices a divider's height offers.
DIVIDER_HEIGHT_CHOICES = (
    (90, "90%"),
    (75, "75% - Partial"),
    (50, "50% - Half way"),
    (25, "25% - Short"),
)
DIVIDER_HEIGHT_DEFAULT = 90


def _closest_percent(percent: float) -> int:
    return min((value for value, _label in DIVIDER_HEIGHT_CHOICES),
               key=lambda value: (abs(value - percent), -value))


def divider_full_height(box, base_z: float) -> float:
    """The bin height a divider's percentage is taken from (inside the bin)."""
    return connector_keep_out(box) - base_z


def divider_height_percent(box, options, base_z: float) -> int:
    """The chosen percentage; an older millimetre height maps to the closest pick."""
    options = options or {}
    full = divider_full_height(box, base_z)
    raw = options.get("height_percent")
    try:
        if raw not in (None, ""):
            return _closest_percent(float(raw))
        legacy = options.get("height")
        if legacy not in (None, "") and full > 0.0:
            return _closest_percent(float(legacy) / full * 100.0)
    except (TypeError, ValueError):
        pass
    return DIVIDER_HEIGHT_DEFAULT


def divider_height(box, options, base_z: float) -> float:
    """The built divider height in mm: the chosen percentage of the bin height."""
    return divider_full_height(box, base_z) * divider_height_percent(
        box, options, base_z) / 100.0
