"""Wavefinity web design, preview-geometry and layout payload helpers."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    BASE_UNIT,
    MAX_BOX_SIZE,
    MIN_BOX_SIZE,
    MIN_HEIGHT_ABOVE_BASE,
    BoxSpec,
)
from organizer_inserts import (
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    build_features,
    connector_keep_out,
    cradle_min_footprint,
    divider_cells,
    divider_scoop_targets,
    feature_definition,
    feature_min_footprint,
    fitted_nest_feature,
    resolve_nest_settings,
    layout_zone,
    normalize_bore_modes,
    moved_feature,
    occupied_zones,
    normalize_divider_scoop,
    resized_feature,
    bore_bin_minimum,
    scoop_zone,
    resolve_text_features,
    resolved_options,
    snapped_zone,
)
from organizer_inserts._core import feature_touches_wall
from organizer_drawer import stack_part_height
from organizer_inventory import configure_space_text
from organizer_product_rules import ORDINARY_BIN_MIN_HEIGHT_MM
from organizer_app import (
    _customization_zones,
    base_height,
    convert_layout_mode,
    default_feature,
    design_from_dict,
    design_to_dict,
    inventory_bin_record,
    object_height_plan,
    preview_geometry,
    validate_customization_clearance,
)
from organizer_b4b import (
    b4b_effective_box,
    b4b_mating_polygon,
    b4b_preview_meshes,
    b4b_summary,
    validate_b4b_design,
    b4b_divider_solids,
    b4b_divider_work_box,
    b4b_divider_zone,
    normalize_b4b_divider,
)
from organizer_base_trim import (
    base_trim_design_to_dict,
    base_trim_from_design,
    base_trim_inner_polygon,
    base_trim_summary,
    make_base_trim_pieces,
)
from organizer_pegboard import pegboard_layout_for_bin
from .._runtime import (
    GEOMETRY_LOCK,
    _SupersededGeometry,
    _register_preview_request,
    _preview_geometry_lock,
    _interior_work_box,
)
from .._nest import (
    feature_to_dict,
    _item_from_json,
    _feature_from_json,
    _auto_size_photo_nest_layout_box,
    _resolve_photo_nest_edit,
    _first_open_position,
)

from dataclasses import replace
import math
from typing import Any
import numpy as np

from ._preview import (
    _design,
    _is_base_trim_design,
    _base_trim_preview_meshes,
    _base_trim_preview_payload,
    _reject_if_b4b,
    _footprint_bounds,
    _resolved_text,
    _b4b_preview_payload,
    validate_design_payload,
)
from ._features import (
    default_feature_payload,
    _divider_cells_payload,
    _bore_required_bin_z,
    _bore_height_bin,
    draft_payload,
    _draft_payload,
    feature_fit_payload,
    apply_feature_payload,
    apply_reference_payload,
    duplicate_feature_payload,
    delete_feature_payload,
    mode_payload,
)
from ._layout import (
    expand_layout_payload,
    inventory_preview_payload,
    pegboard_layouts_payload,
    create_space_text_payload,
    configure_space_text_payload,
)
