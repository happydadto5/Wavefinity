"""Divider constants and the shared option-flag helper."""

from __future__ import annotations

from organizer_engine import (
    TEXT_DEPTH,
    TOP_LABEL_CAP_HEIGHT,
    TOP_LABEL_LEDGE_DEPTH,
    TOP_LABEL_MARGIN,
    WAVE_AMPLITUDE,
)


MAX_DIVIDER_ANGLE = 45.0
MIN_WEDGE_EDGE = 0.4
DIVIDER_CHAMFER = 1.0
BOTTOM_SLOPE_MAX = 80.0
BOTTOM_EMBED = 0.4
BOTTOM_CROSSBAR_THICKNESS = 2.4
BOTTOM_CROSSBAR_CHAMFER = 1.0
RIB_THICKNESS = 1.6
DIVISION_TEXT_DEPTH = TEXT_DEPTH
# Clear gap kept between a base-level (floor) division label and whatever bounds
# its compartment - a divider wall face, or the bin's own wall. The bin side
# includes the wave's inward swing so a full-span divider's label still clears
# the crest, not just the safe rectangle.
DIVISION_TEXT_MARGIN = TOP_LABEL_MARGIN + WAVE_AMPLITUDE
# Rim-level division labels can ride on a real shelf welded to the divider, the
# same self-supporting ledge the box's own rim label uses: flat top at the
# divider height, a 45-degree underside so it prints without support, and the
# lettering inlaid flush for its own filament colour.
DIVISION_SHELF_DEPTH = TOP_LABEL_LEDGE_DEPTH
DIVISION_SHELF_EMBED = 0.6
# A shelf that reaches the bin's own wavy wall roots this far past the flat
# compartment edge. That is more than the wall ripple plus the wall itself, so
# the flat top and the sloped underside both run into real wall material; the
# outside safety skin then trims it back so nothing can show through.
DIVISION_SHELF_WALL_ROOT = 2.0
DIVISION_SHELF_TEXT_MARGIN = TOP_LABEL_MARGIN
DIVISION_CAP_MAX = TOP_LABEL_CAP_HEIGHT
DIVISION_SHELF_MIN_DEPTH = 2.5


def _option_flag(value: object) -> bool:
    """A yes/no option however it arrived - real bool, or a browser string."""
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "off"}
    return bool(value)
