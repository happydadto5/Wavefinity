"""Divider feature defaults and geometry."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    BoxSpec, LOCK_SAFE_SKIN, TEXT_DEPTH, TOP_LABEL_CAP_HEIGHT, TOP_LABEL_LEDGE_DEPTH,
    TOP_LABEL_MARGIN, WAVE_AMPLITUDE, WAVE_LENGTH, _rounded, flat_cavity_polygon,
    require_text_backing, text_outline, text_prism, top_label_surface_z,
    wavy_cavity_polygon, wavy_outer_polygon, build_scoop_region, wall_depth_for, wave_value,
)
from organizer_geometry import (
    _extrude_polygon, _extrude_xz_profile, _extrude_yz_profile,
    difference, intersection, union,
)
from .._core import Feature, Zone, connector_keep_out
from .._text import preview_inlay_layer
from .._divider_cells import (
    DividerCell,
    _divider_cross_centres,
    _even_centres,
    divider_cells,
    divider_grid_counts,
    divider_grid_edges,
    divider_owner_matrix,
    divider_scoop_targets,
    normalize_divider_scoop,
    normalized_compartment_spans,
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
from .._scoop import scoop_default_depth, scoop_region, scoop_settings

import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box

from ._consts import (
    MAX_DIVIDER_ANGLE,
    MIN_WEDGE_EDGE,
    DIVIDER_CHAMFER,
    BOTTOM_SLOPE_MAX,
    BOTTOM_EMBED,
    BOTTOM_CROSSBAR_THICKNESS,
    BOTTOM_CROSSBAR_CHAMFER,
    RIB_THICKNESS,
    DIVISION_TEXT_DEPTH,
    DIVISION_TEXT_MARGIN,
    DIVISION_SHELF_DEPTH,
    DIVISION_SHELF_EMBED,
    DIVISION_SHELF_WALL_ROOT,
    DIVISION_SHELF_TEXT_MARGIN,
    DIVISION_CAP_MAX,
    DIVISION_SHELF_MIN_DEPTH,
    _option_flag,
)
from ._bottoms import (
    _divider_sloped_bottoms,
    _custom_divider_sloped_bottoms,
    _bottom_slot_bounds,
    _bottom_plane_z,
    _extrude_bottom,
    _divider_support_bottoms,
)
from ._shelf import (
    _divider_grid_texts,
    _shelf_edge_is_bin_wall,
    _division_shelf_solid,
    _divider_grid_rim_texts,
    _division_side_shelves,
    divider_division_texts,
)
from ._walls import (
    _divider_wall,
    _wavy_divider_profile,
    _full_span_leaning_divider,
    _trimmed_prism,
    _full_span_divider,
)
from ._build import (
    divider_defaults,
    divider_max_bottom_angle,
    _divider_scoops,
    build_divider,
    _build_divider_grid,
    _wall_runs,
    _clip_wall_to_runs,
    _custom_grid_wall,
    _build_custom_divider_grid,
    _one_grid_wall,
)

register_setting_interactions("divider", (
    SettingInteraction(
        "count", "cells", "derived", "divider",
        "Legacy single-direction wall count determines logical compartments.",
    ),
    SettingInteraction(
        "spacing", "cells", "derived", "divider",
        "Legacy wall spacing determines logical compartment boundaries.",
    ),
    SettingInteraction(
        "count_x", "cells", "derived", "divider",
        "Grid X wall count determines logical compartment columns.",
    ),
    SettingInteraction(
        "count_y", "cells", "derived", "divider",
        "Grid Y wall count determines logical compartment rows.",
    ),
    SettingInteraction(
        "thickness", "cells", "constraint", "divider",
        "Wall thickness reduces each compartment's usable floor region.",
    ),
    SettingInteraction(
        "scoop.enabled", "scoop.geometry", "enable/disable", "divider",
        "An enabled Divider Scoop builds one shared Scoop in every compartment.",
    ),
    SettingInteraction(
        "cells", "scoop.geometry", "derived", "divider",
        "Each Divider compartment receives one Scoop while the setting is enabled.",
    ),
    SettingInteraction(
        "scoop.depth", "scoop.height", "derived", "scoop",
        "Divider Scoops use the same depth-to-height rule as standalone Scoops.",
    ),
    SettingInteraction(
        "scoop.enabled", "slope_base", "reset", "divider-editor",
        "A curved Scoop and a sloped bottom cannot own the same compartment floor.",
    ),
    SettingInteraction(
        "slope_base", "scoop.enabled", "reset", "divider-editor",
        "Selecting a sloped bottom removes the mutually exclusive curved Scoop.",
    ),
    SettingInteraction(
        "scoop.enabled", "division_labels.region", "auto-adjust", "divider",
        "Base-level division labels move to the high-Y band left clear by the Scoop.",
    ),
    SettingInteraction(
        "count_x", "count", "reset", "divider-editor",
        "Entering either grid quantity retires the legacy single-axis count.",
    ),
    SettingInteraction(
        "count_y", "count", "reset", "divider-editor",
        "Entering either grid quantity retires the legacy single-axis count.",
    ),
    SettingInteraction(
        "thickness", "zone", "auto-adjust", "divider-sizing",
        "Wall width grows the Divider footprint when required.",
    ),
    SettingInteraction(
        "slope_base", "bottom_angle", "enable/disable", "divider-editor",
        "Bottom angle is active only while sloped bottoms are enabled.",
    ),
    SettingInteraction(
        "slope_base", "bottom_supports", "enable/disable", "divider-editor",
        "Crossbar controls are active only for sloped bottoms.",
    ),
    SettingInteraction(
        "minimal_bottom", "bottom_supports", "enable/disable", "divider-editor",
        "Crossbar count is shown only when support crossbars are selected.",
    ),
    SettingInteraction(
        "label_divisions", "division_labels", "enable/disable", "divider-editor",
        "Division label text is active only when compartment labels are enabled.",
    ),
    SettingInteraction(
        "division_level", "division_labels.shelf", "enable/disable", "divider",
        "Rim-level Divider labels use the Text part's selected-side shelf profile.",
    ),
    SettingInteraction(
        "wall_style", "wall_geometry", "auto-adjust", "divider",
        "Wall style changes wall path/thickness compensation while preserving logical compartments.",
    ),
))
