"""Public compatibility facade for organizer inserts."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

import trimesh
from shapely import affinity
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box as shapely_box
from shapely.ops import unary_union

from organizer_engine import (
    BoxSpec,
    SCOOP_CURVE_SEGMENTS,
    SCOOP_HEIGHT_FRACTION,
    TEXT_CAP_HEIGHT_FLOOR,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    _rounded,
    difference,
    flat_cavity_polygon,
    intersection,
    label_placement,
    text_outline,
    text_prism,
    union,
    wavy_cavity_polygon,
)

from ._core import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    EDITOR_SNAP,
    INSERT_CLEARANCE,
    ITEM_CLEARANCE,
    LAYOUT_MODES,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    _fit_count,
    _item_dict,
    _need_item,
    cartridge_zone,
    connector_keep_out,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    load_layout,
    moved_feature,
    resized_feature,
    save_layout,
    snap_value,
    snapped_zone,
)
from ._registry import (
    Builder,
    Defaults,
    FEATURE_BUILDERS,
    FEATURE_DEFAULTS,
    defaults,
    feature,
    resolved_options,
)

# Keep this order stable: importing each feature populates the shared registries.
from ._post import build_post, post_defaults
from ._cradle import (
    CRADLE_ALTERNATE_END_MARGIN,
    CRADLE_ALTERNATE_END_MARGIN_MAX,
    CRADLE_FLOOR_GAP,
    CRADLE_MIN_FLOOR_GAP,
    CRADLE_RIB_FRACTION,
    CRADLE_RIB_MAX,
    CRADLE_RUN_OFFSET_MAX,
    MAX_NOTCH_FRACTION,
    RIB_THICKNESS,
    _cradle_end_margin,
    _cradle_offset,
    _cradle_rib_thickness,
    _cradle_wall,
    build_cradle,
    cradle_defaults,
    cradle_min_footprint,
)
from ._divider import (
    BOTTOM_CROSSBAR_CHAMFER,
    BOTTOM_CROSSBAR_THICKNESS,
    BOTTOM_EMBED,
    BOTTOM_SLOPE_MAX,
    DIVIDER_CHAMFER,
    MAX_DIVIDER_ANGLE,
    MIN_WEDGE_EDGE,
    _divider_cross_centres,
    _divider_support_bottoms,
    _divider_wall,
    build_divider,
    divider_defaults,
)
from ._nest import (
    NEST_ASSISTS,
    NEST_CHAMFER,
    NEST_FINGER_POSITIONS,
    NEST_FINGER_WIDTH,
    NEST_PUSH_AREA,
    NEST_PUSH_DEPTH,
    NEST_PUSH_POSITIONS,
    NEST_TOP_ROUND,
    build_nest,
    fitted_nest_feature,
    nest_contour_polygon,
    nest_defaults,
    nest_required_zone,
    nest_smoothed_contour,
)
from ._pocket import POCKET_CHAMFER, POCKET_FLOOR, build_pocket, pocket_defaults
from ._bore import (
    BORE_MAX_TILT,
    BORE_MOUTH_CHAMFER,
    BORE_TILTED_WALL,
    BORE_WALL,
    HEX_BIT_CLEARANCE,
    HEX_BIT_FLATS,
    HEX_BIT_HOLD,
    HEX_BIT_LENGTH,
    HEX_BIT_LONG_LENGTH,
    HEX_BIT_SHORT_LENGTH,
    _is_hex_bit,
    build_bore,
    bore_defaults,
)
from ._scoop import build_scoop, scoop_defaults, scoop_zone
from ._slot import build_slot, slot_defaults
from ._text import (
    NON_NUMERIC_OPTIONS,
    TEXT_KIND,
    TEXT_ZONE_EPSILON,
    _oriented_text,
    _text_footprint,
    auto_grow_text_feature,
    build_text,
    is_text,
    option_value,
    text_defaults,
    text_depth,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)
from ._steps import build_steps, steps_defaults

from ._layout import (
    _FOOTPRINT_BUILDERS,
    _cradle_footprint,
    _divider_footprint,
    _feature_reach,
    _post_footprint,
    check_layout,
    feature_footprint,
    feature_min_footprint,
    occupied_zones,
)
from ._assembly import (
    apply_texts,
    build_features,
    build_texts,
    insert_footprint,
    insert_report,
    make_cartridge_insert,
    make_fitted_insert,
    make_fused_box,
    make_insert_plate,
    resolve_text_features,
)
