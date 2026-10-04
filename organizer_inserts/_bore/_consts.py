"""Bore constants, style names and mode helpers."""

from __future__ import annotations

from .._core import ITEM_PROFILES, Feature


BORE_WALL = 1.6            # material around a bore
BORE_CLEARANCE = 0.25      # automatic fit clearance on bore diameters
HEX_BIT_FLATS = 6.35      # 1/4" hex driver bit, measured across the flats
HEX_BIT_SHORT_LENGTH = 25.0  # a nominal 1" insert bit
HEX_BIT_LONG_LENGTH = 38.0   # a nominal 1.5" power bit
HEX_BIT_CLEARANCE = 0.25  # snug in the hex hole but still slides in and out freely
# Hole depth per hex-bit type: holds roughly half the bit so it stands well proud
# and stays easy to pinch out.
HEX_BIT_HOLD = {"hex_bit_short": 12.0, "hex_bit_long": 16.0}
HEX_BIT_LENGTH = {
    "hex_bit_short": HEX_BIT_SHORT_LENGTH,
    "hex_bit_long": HEX_BIT_LONG_LENGTH,
}
# A Bore accepts every item profile. The two hex-bit profiles are fixed presets:
# the item is exactly this size with this fit, and the hole stands upright.
BORE_ITEM_PROFILES = tuple(value for value, _label in ITEM_PROFILES)
HEX_BIT_FIXED = {
    profile: {
        "length_mm": HEX_BIT_LENGTH[profile], "diameter_mm": HEX_BIT_FLATS,
        "clearance_mm": HEX_BIT_CLEARANCE, "hole_depth_mm": HEX_BIT_HOLD[profile],
    }
    for profile in HEX_BIT_HOLD
}
BORE_MOUTH_CHAMFER = 0.6  # 45-degree lead-in at each hole mouth
WALL_ONLY_FOOT = 0.5
BORE_MAX_TILT = 70.0      # steepest lean off vertical the hole geometry still allows
BORE_TILTED_WALL = 3.0    # thicker default wall once a bore is leaned


def bore_direction(spec_feature: Feature) -> tuple[str, float]:
    """Return the lean axis and the direction the bore points toward.

    Old designs used ``along`` as their only direction control.  Keep that
    meaning when no new direction is stored, so existing designs do not turn.
    """
    toward = str(spec_feature.options.get("angle_towards", "")).lower()
    directions = {
        "right": ("x", 1.0), "left": ("x", -1.0),
        "back": ("y", 1.0), "front": ("y", -1.0),
    }
    return directions.get(toward, (spec_feature.along, -1.0))


def normalize_bore_style(style: object, wall_style: object = None) -> str:
    """The one style word a Bore stores.

    Testing-era values are translated one way (``full_base`` -> Base - Straight,
    ``wavy_base`` -> Base - Wavy, ``wall_only`` + its separate wall style ->
    Straight / Wavy Walls Only). A missing style is Base - Straight Walls; any
    other word is left for validation to reject.
    """
    text = str(style or "")
    if text in BORE_STYLES:
        return text
    if text in LEGACY_STYLES:
        return LEGACY_STYLES[text]
    if text == "wall_only":
        return "walls_straight" if str(wall_style or "wavy") == "straight" else "walls_wavy"
    return text if text else "base_straight"


def is_walls_only(style: object) -> bool:
    return str(style) in WALLS_ONLY_STYLES


def is_wavy_style(style: object) -> bool:
    return str(style) in WAVY_STYLES


def default_xy_size_mode(style: object) -> str:
    """Walls Only sizes the bin to itself by default; Base is hand-sized."""
    return "bin_to_bore" if is_walls_only(style) else "manual"


def bore_xy_size_mode(options: dict, style: object) -> str:
    """The persisted Width / Length sizing mode, defaulting per style."""
    mode = str(options.get("xy_size_mode") or default_xy_size_mode(style))
    allowed = WALLS_XY_SIZE_MODES if is_walls_only(style) else XY_SIZE_MODES
    return mode if mode in allowed else default_xy_size_mode(style)


def bore_height_size_mode(options: dict) -> str:
    mode = str(options.get("height_size_mode") or "manual")
    return mode if mode in HEIGHT_SIZE_MODES else "manual"

# One persisted style owner. "Base" styles are a solid block the holes are cut
# into; "Walls Only" styles are just the perimeter sleeves rising from the floor.
BORE_STYLES = ("base_straight", "base_wavy", "walls_straight", "walls_wavy")
WALLS_ONLY_STYLES = ("walls_straight", "walls_wavy")
WAVY_STYLES = ("base_wavy", "walls_wavy")
# Styles that stand upright (only Base - Straight Walls may lean).
UPRIGHT_STYLES = ("base_wavy", "walls_straight", "walls_wavy")
# Styles sized by their sleeves' true outer envelope rather than a Base block.
ENVELOPE_STYLES = WALLS_ONLY_STYLES
# Styles whose geometry may fuse into the bin wall.
JOIN_STYLES = UPRIGHT_STYLES
# Testing-era style words, normalised one way at load boundaries.
LEGACY_STYLES = {"full_base": "base_straight", "wavy_base": "base_wavy"}
XY_SIZE_MODES = ("manual", "bore_to_bin", "bin_to_bore")
WALLS_XY_SIZE_MODES = ("manual", "bin_to_bore")
HEIGHT_SIZE_MODES = ("manual", "bore_to_bin", "bin_to_bore")
# Auto-sized Bore Height keeps its top this far below the lowest physical point
# of an Edge Mount screwdriver-access cutter.
ACCESS_CUTTER_CLEARANCE = 2.0
# Geometry-only boolean overtravel for a cavity that reaches the Bore's floor.
FLOOR_OVERTRAVEL = 0.05
# Set by the fused assembler on a Bore whose geometry may fuse into the bin wall.
WALL_JOIN_FLAG = "_wall_join"
# Set alongside WALL_JOIN_FLAG for a Walls Only Bore whose bin is sized around it:
# the sleeves then bridge the (under one grid step) gap to the bin wall.
WALL_HUG_FLAG = "_wall_hug"
JOIN_TOUCH = 0.05             # envelope this close to a wall counts as reaching it
JOIN_BAND = 1.2               # wall-only material this close to the wall is blended in
JOIN_SKIN = 0.15              # a joined blend never comes closer than this to the outside
HUG_REACH = 8.0               # bin_to_bore leaves under one 8 mm grid step to the wall
WAVE_NOISE_FLOOR = 1e-4       # trough sits a hair outside the clear opening, so
                              # float noise cannot fold the outline back on itself
WAVE_SAMPLES_PER_CYCLE = 32   # keeps a wavy sleeve smooth in the STL and preview
