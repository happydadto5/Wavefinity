"""Bore feature defaults and geometry."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    WAVE_AMPLITUDE, WAVE_LENGTH, BoxSpec, wall_depth_for, wave_value, wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, difference, union
from .._core import (
    ITEM_PROFILES,
    Feature,
    Zone,
    _fit_count,
    _need_item,
    connector_keep_out,
    feature_touches_wall,
    layout_zone,
)
from .._registry import (
    OptionDefinition,
    SIDE_CHOICES,
    SettingInteraction,
    defaults,
    feature,
    register_setting_interactions,
    resolved_options,
)

import math
from dataclasses import replace
import trimesh
from shapely.affinity import translate
import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.ops import unary_union

from ._consts import (
    BORE_WALL,
    BORE_CLEARANCE,
    HEX_BIT_FLATS,
    HEX_BIT_SHORT_LENGTH,
    HEX_BIT_LONG_LENGTH,
    HEX_BIT_CLEARANCE,
    HEX_BIT_HOLD,
    HEX_BIT_LENGTH,
    BORE_ITEM_PROFILES,
    HEX_BIT_FIXED,
    BORE_MOUTH_CHAMFER,
    WALL_ONLY_FOOT,
    BORE_MAX_TILT,
    BORE_TILTED_WALL,
    bore_direction,
    normalize_bore_style,
    is_walls_only,
    is_wavy_style,
    default_xy_size_mode,
    bore_xy_size_mode,
    bore_height_size_mode,
    BORE_STYLES,
    WALLS_ONLY_STYLES,
    WAVY_STYLES,
    UPRIGHT_STYLES,
    ENVELOPE_STYLES,
    JOIN_STYLES,
    LEGACY_STYLES,
    XY_SIZE_MODES,
    WALLS_XY_SIZE_MODES,
    HEIGHT_SIZE_MODES,
    ACCESS_CUTTER_CLEARANCE,
    FLOOR_OVERTRAVEL,
    WALL_JOIN_FLAG,
    WALL_HUG_FLAG,
    JOIN_TOUCH,
    JOIN_BAND,
    JOIN_SKIN,
    HUG_REACH,
    WAVE_NOISE_FLOOR,
    WAVE_SAMPLES_PER_CYCLE,
)
from ._walls import (
    _is_hex_bit,
    _hole_sides,
    _axis_square,
    bore_minimum_pitches,
    _wall_only_shell_reach,
    _round_clear_sides,
    _clear_spans,
    wall_only_envelope,
    _clear_profile_points,
    _wavy_outline,
    _wall_only_ring,
    _union,
    _polygons,
    WEB_COINCIDENCE_TOL,
    WEB_WIDTH_NUDGES,
    _ring_points,
    _web_is_clean,
    _web_polygon,
    _join_tabs,
    _tab_meshes,
    _access_top_limit,
)
from ._settings import (
    bore_defaults,
    normalize_bore_modes,
    _envelope_counts,
    _wall_only_grid,
    bore_envelope_zone,
)
from ._grid import _bore_grid, _bore_hole_centres
from ._shapes import _build_wall_only_bore, _build_wavy_base_bore
from ._build import (
    bore_reference_meshes,
    bore_reference_top,
    bore_hole_axes,
    bore_tool_clearance_zone,
    build_bore,
)

register_setting_interactions("bore", (
    SettingInteraction("depth", "height", "constraint", "bore-shell",
                       "A user-edited Hole depth wins and raises Height to at least that depth."),
    SettingInteraction("height", "depth", "constraint", "bore-shell",
                       "A user-edited Height wins and lowers Hole depth to no more than that height."),
    SettingInteraction("angle", "wall", "default", "bore",
                       "A leaned Bore uses a thicker wall unless Wall is explicitly set."),
    SettingInteraction("bore_style", "angle", "reset", "bore-editor",
                       "Base - Wavy Walls and both Walls Only styles stand upright, so choosing one "
                       "removes a stored lean."),
    SettingInteraction("bore_style", "wall", "default", "bore",
                       "Base - Wavy Walls and Walls Only take the bin wall; Base - Straight Walls "
                       "keeps its own internal wall."),
    SettingInteraction("bore_style", "zone", "auto-adjust", "bore-sizing",
                       "Walls Only sizes to the sleeves' outer envelope; Wavy walls reach further "
                       "than straight walls."),
    SettingInteraction("bore_style", "depth", "default", "bore-editor",
                       "Switching from Walls Only to a Base style keeps a floor-reaching cavity "
                       "by taking the Bore's Height as Hole depth."),
    SettingInteraction("xy_size_mode", "zone", "auto-adjust", "bore-sizing",
                       "Auto size bore to bin fills the usable bin; Auto size bin to bore fits the "
                       "bin around the Bore's minimum footprint."),
    SettingInteraction("height_size_mode", "height", "auto-adjust", "bore-sizing",
                       "Auto size bore to bin derives Height from the bin, connector keep-out and "
                       "Edge Mount screwdriver access; Auto size bin to bore keeps Height and "
                       "resizes the bin."),
    SettingInteraction("angle", "angle_towards", "enable/disable", "bore-editor",
                       "Direction is shown only for a Bore that is actually leaned."),
    SettingInteraction("item.profile", "angle", "reset", "bore-editor",
                       "Hex-bit presets stand upright and remove a stored lean."),
    SettingInteraction("item.profile", "item.diameter", "default", "bore",
                       "Hex-bit presets own their fixed across-flats diameter."),
    SettingInteraction("columns", "zone", "auto-adjust", "bore-sizing",
                       "X quantity grows the Bore Base to its minimum printable width."),
    SettingInteraction("rows", "zone", "auto-adjust", "bore-sizing",
                       "Y quantity grows the Bore Base to its minimum printable length."),
    SettingInteraction("item.diameter", "zone", "auto-adjust", "bore-sizing",
                       "Hole diameter grows the Base footprint."),
    SettingInteraction("wall", "zone", "auto-adjust", "bore-sizing",
                       "Wall thickness grows the Base footprint."),
    SettingInteraction("angle", "zone", "auto-adjust", "bore-sizing",
                       "Lean grows the Base along the selected direction."),
    SettingInteraction("angle_towards", "zone", "auto-adjust", "bore-sizing",
                       "Lean direction determines which Base axis receives the extra reach."),
))
