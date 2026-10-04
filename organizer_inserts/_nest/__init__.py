"""Photo Nest feature defaults and geometry."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import BoxSpec
from organizer_geometry import (
    _extrude_polygon, _extrude_xz_profile, _extrude_yz_profile,
    difference, union,
)
from .._core import Feature, Zone
from .._registry import (
    OptionDefinition,
    SettingInteraction,
    defaults,
    feature,
    register_setting_interactions,
    resolved_options,
)

import math
from dataclasses import dataclass, replace
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.ops import unary_union

from ._base import (
    HOLDER_STYLES,
    NEST_OUTER_FOOT_MIN,
    NEST_OUTER_FOOT_MAX,
    NEST_TOP_ROUND_OUTER,
    NEST_TOP_ROUND_INNER,
    NEST_INSIDE_RELIEF_MAX,
    NEST_LEAD_IN_MAX,
    LEGACY_NEST_CHAMFER,
    LEGACY_NEST_TOP_ROUND,
    NEST_FINGER_WIDTH,
    NEST_AUTO_WIDTH_MIN,
    NEST_AUTO_WIDTH_MAX,
    NEST_CUSTOM_WIDTH_MIN,
    NEST_CUSTOM_WIDTH_MAX,
    NEST_FINGER_BOTTOM_SKIN,
    NEST_PUSH_AREA,
    NEST_PUSH_DEPTH,
    NEST_ASSISTS,
    NEST_FINGER_POSITIONS,
    NEST_PUSH_POSITIONS,
    NEST_REPEAT_AUTO_GAP,
    NEST_REPEAT_SPACING_CHOICES,
    NEST_REPEAT_MAX,
    NestOccurrence,
    _softened_outline,
    nest_smoothed_contour,
    _nest_local_polygon,
    nest_contour_polygon,
    _nest_occurrence_opening,
    _is_legacy_nest,
    is_legacy_nest,
    require_measured_tool_thickness,
    _resolved_tool_thickness,
    _resolved_holder_style,
    _resolved_cavity_depth,
    _resolved_finger_settings,
    _line_coordinates,
    _nest_access_mode,
    _min_rotated_rect_axes,
    _automatic_finger_width_for,
    _automatic_finger_width,
    _raised_wall_outer_foot,
    nest_quantity,
    nest_repeat_spacing_percent,
    nest_repeat_gap,
)
from ._access import (
    AccessPoint,
    NestAccessPlan,
    _sample_at,
    _validate_access_point,
    _segment_through_point,
    _axis_pair,
    _single_axis_points,
    _boundary_fallback_pair,
    resolve_nest_access_plan,
    _legacy_finger_positions,
)
from ._settings import (
    nest_access_preview,
    _raised_wall_height_for_sizing,
    _nest_single_required_footprint,
    nest_occurrences,
    nest_occurrence_preview,
    nest_required_zone,
    fitted_nest_feature,
    nest_defaults,
    resolve_nest_settings,
    clamp_nest_feature_options,
)
from ._build import (
    _nest_transform_mesh,
    _oriented_notch_cutter,
    _legacy_nest_finger_cutters,
    _legacy_nest_rounded_wall,
    _nest_rounded_wall,
    _nest_push_support,
    _nest_recessed_deck,
    _nest_recessed_cavity_cutter,
    _nest_finger_scoops,
    build_nest,
    build_recessed_nest_group,
)

register_setting_interactions("nest", (
    SettingInteraction("count", "zone", "auto-adjust", "nest-repeat",
                       "The repeated group footprint is recalculated."),
    SettingInteraction("rotation", "zone", "auto-adjust", "nest-repeat",
                       "The repeated group footprint is recalculated."),
    SettingInteraction("alternate_ends", "zone", "auto-adjust", "nest-repeat",
                       "The repeated group footprint is recalculated."),
    SettingInteraction("repeat_spacing_percent", "zone", "auto-adjust", "nest-repeat",
                       "The repeated group footprint is recalculated."),
    SettingInteraction("holder_style", "lift_assist", "auto-adjust", "nest",
                       "Switching to Recessed Cavity turns off Push Out and resolves "
                       "Automatic finger access instead."),
    SettingInteraction("lift_assist", "finger_position", "enable/disable", "nest-editor",
                       "Finger locations are active only for Custom finger access."),
    SettingInteraction("lift_assist", "finger_width", "enable/disable", "nest-editor",
                       "Finger width is active only for Custom finger access."),
    SettingInteraction("lift_assist", "push_position", "enable/disable", "nest-editor",
                       "Push position is active only for Push Out."),
    SettingInteraction("lift_assist", "push_area", "enable/disable", "nest-editor",
                       "Push area is active only for Push Out."),
    SettingInteraction("lift_assist", "push_depth", "enable/disable", "nest-editor",
                       "Push depth is active only for Push Out."),
    SettingInteraction("tool_thickness", "cavity_depth", "auto-adjust", "nest",
                       "Cavity depth recalculates to 60% of tool thickness while it is set to Auto."),
    SettingInteraction("clearance", "zone", "auto-adjust", "nest-sizing",
                       "Fit clearance grows the contour footprint without shrinking the bin."),
    SettingInteraction("rim", "zone", "auto-adjust", "nest-sizing",
                       "Outline wall grows the contour footprint."),
    SettingInteraction("smoothing", "zone", "auto-adjust", "nest-sizing",
                       "Outline smoothing recalculates the fitted contour bounds."),
    SettingInteraction("push_depth", "height", "constraint", "nest",
                       "Push Out adds its deck depth to the required wall height."),
    SettingInteraction("cavity_depth", "height", "constraint", "nest",
                       "Recessed Cavity's deck depth must fit above the printable floor."),
))
