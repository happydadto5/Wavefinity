"""Canonical catalog; environment identity and desktop capabilities are supplied by callers."""

from __future__ import annotations
from typing import Any

from organizer_engine import (
    TEXT_MIN_BACKING,
    connector_arm_thickness_floor,
    BASE_UNIT,
    BASE_PRESETS,
    B4B_BASE_PRESETS,
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
    B4B_FRONT_LABEL_STYLES,
    B4B_LABEL_LOCATIONS,
    B4B_LID_HEADROOM_CHOICES,
    B4B_SCHEMA_VERSION,
    B4B_WALL_PRESETS,
    WALL_PRESETS,
    GRID_PITCH,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_WALL,
    DEFAULT_ARM_THICKNESS,
    DIFFERING_FULL_DROP,
    DIFFERING_LENGTH_GAIN,
    DIFFERING_MIN_DROP,
    DIFFERING_WEB_RUN_CLEARANCE,
    DIFFERING_WEB_THICKNESS,
    EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    MAX_BOX_SIZE,
    MAX_WALL,
    MIN_HEIGHT_ABOVE_BASE,
    MIN_WALL,
    SIDE_OPENING_WIDTHS,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    WALL_STEP,
    LID_ALIGNMENT_MM,
    LID_ALIGNMENT_NAMES,
    LID_ALIGNMENTS,
    LID_FIT_MM,
    LID_FIT_NAMES,
    LID_THICKNESSES,
    LID_THICKNESS_NAMES,
    LID_FITS,
    LID_LABEL_LEGACY_RAISED_MM,
    LID_LABEL_RELIEF_NAMES,
    LID_LABEL_RELIEFS,
    lift_grabber_min_wall,
    LIFT_GRABBER_DIMENSIONS,
    LIFT_GRABBER_RIM_CLEARANCE,
    SCOOP_HEIGHT_FRACTION,
    max_wave_slope,
)
from organizer_inserts import (
    BASE_PLATE,
    feature_definitions,
    setting_interactions,
)
from organizer_inserts._bore import (
    BORE_CLEARANCE,
    HEX_BIT_FIXED,
)
from organizer_inserts._core import (
    ITEM_CLEARANCE,
    ITEM_PROFILES,
)
from organizer_engine.product_rules import (
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM,
)
from organizer_outputs.printer_profile import (
    DEFAULT_PRINTER_BUILD_MM,
)
from organizer_storage.drawers import (
    STORAGE_DRAWER_FIT_CHOICES,
    STORAGE_DRAWER_FIT_DEFAULT,
    STORAGE_DRAWER_FRAME_WIDTH_CHOICES,
    STORAGE_DRAWER_FRAME_WIDTH_DEFAULT,
    STORAGE_DRAWER_LABEL_LIMIT,
    STORAGE_DRAWER_MAX_USABLE_HEIGHT_MM,
    STORAGE_DRAWERS_MAX_DRAWERS,
    STORAGE_DRAWERS_MAX_UNITS,
    STORAGE_DRAWERS_MIN_DRAWERS,
    STORAGE_DRAWERS_MIN_UNITS,
    STORAGE_DRAWERS_DEFAULT_FIELD_MM,
)
from organizer_engine.product_rules import (
    STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM,
)
from organizer_app import (
    DEFAULT_SAMPLE_BOXES,
)
from organizer_b4b import (
    B4B_HANDLE_GRIP_ABS_MIN,
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    B4B_MIN_WALL,
    B4B_STACK_MIN_BASE,
)
from organizer_base_trim import (
    BASE_TRIM_BED_EDGE_MARGIN,
    BASE_TRIM_DEFAULT_BED_X,
    BASE_TRIM_DEFAULT_BED_Y,
    BASE_TRIM_DEFAULT_HEIGHT,
    BASE_TRIM_DEFAULT_WIDTH,
    BASE_TRIM_JOIN_LABELS,
    BASE_TRIM_JOIN_TYPES,
    BASE_TRIM_MAX_HEIGHT,
    BASE_TRIM_MAX_FIELD,
    BASE_TRIM_MAX_WIDTH,
    BASE_TRIM_MIN_HEIGHT,
    BASE_TRIM_MIN_WIDTH,
    BASE_TRIM_OUTER_TAPER,
    BASE_TRIM_SIZE_PRESETS,
)
from organizer_features.stack import (
    STACK_MIN_WALL,
)
from organizer_features.edge_mount import (
    EDGE_HOLE_DEFAULT_SCREW_DIAMETER,
    EDGE_HOLE_DEFAULT_TOP_OFFSET,
    EDGE_HOLE_MAX_ACCESS_DIAMETER,
    EDGE_HOLE_MAX_COUNT,
    EDGE_HOLE_MAX_SCREW_DIAMETER,
    EDGE_HOLE_MIN_ACCESS_DIAMETER,
    EDGE_HOLE_MIN_COUNT,
    EDGE_HOLE_MIN_SCREW_DIAMETER,
    EDGE_LABEL_DEFAULT_PROJECTION,
    EDGE_LABEL_DEFAULT_THICKNESS,
    EDGE_LABEL_MAX_PROJECTION,
    EDGE_LABEL_MAX_TEXT_DEPTH,
    EDGE_LABEL_MAX_THICKNESS,
    EDGE_LABEL_MIN_PROJECTION,
    EDGE_LABEL_MIN_TEXT_DEPTH,
    EDGE_LABEL_MIN_THICKNESS,
    EDGE_LABEL_THICKNESS_PRESETS,
)
from organizer_features.side_openings import (
    SIDE_OPENING_ARCH_CURVE,
    SIDE_OPENING_CORNER_MARGIN_MM,
    SIDE_OPENING_MIN_SIDE_MM,
    SIDE_OPENING_TOP_BRIDGE_MM,
)
from organizer_features.pegboard import (
    pegboard_catalog,
)
import math
from wavefinity_web_impl._runtime import (
    default_design,
    _stack_base_min_by_wall,
)
from wavefinity_web_impl._nest import (
    _option_payload,
)


def catalog_payload(*, environment: dict[str, Any]) -> dict[str, Any]:
    from wavefinity_web_impl._ai import grid_editor_catalog
    parts = [
        {
            "kind": definition.kind,
            "title": definition.title,
            "display": definition.display,
            "description": definition.description,
            "icon": definition.icon,
            "flags": definition.flags,
            "fields": [
                {
                    "label": option.label,
                    "key": option.key,
                    "default": option.default,
                    "type": option.value_type,
                }
                for option in definition.options if option.editor
            ],
            "options": [_option_payload(option) for option in definition.options],
            "item_profiles": [
                {"value": value, "label": dict(ITEM_PROFILES)[value]}
                for value in definition.item_profiles
            ],
            "capabilities": list(definition.capabilities),
            "max_instances": definition.max_instances,
            "palette_visible": definition.palette_visible,
        }
        for definition in feature_definitions()
    ]
    empty_flags = {
        "qty": False, "size": False, "along": False, "item": False,
        "lean": False, "alternate": False, "photo": False, "text": False,
    }
    for kind, title, description in (
        ("lid_stacking", "Lid & Stacking",
         "Add a lid or make matching bins stack together."),
        ("inside_handles", "Inside Grip",
         "A finger grip inside the bin so it is easier to lift."),
        ("side_openings", "Side Openings",
         "Finger-access cutouts through selected bin walls."),
        ("edge_mount", "Edge Mount",
         "Add a label and/or screw mounting for an outside edge."),
    ):
        parts.append({
            "kind": kind,
            "title": title,
            "display": title,
            "description": description,
            "icon": kind,
            "flags": dict(empty_flags),
            "fields": [],
            "options": [],
            "capabilities": ["box_modifier"],
            "max_instances": 1,
            "palette_visible": True,
        })
    return {
        "platform": environment["platform"],
        "version": environment["version"],
        "instance": environment["instance"],
        "api_compat": environment["api_compat"],
        "build": environment["build"],
        "base_unit": BASE_UNIT,
        "grids": grid_editor_catalog(),
        "max_box_size": MAX_BOX_SIZE,
        "min_height_above_base_mm": MIN_HEIGHT_ABOVE_BASE,
        "drawer_rules": {
            "hard_wall_clearance_mm": DRAWER_HARD_CLEARANCE_MM,
            "ordinary_bin_min_height_mm": ORDINARY_BIN_MIN_HEIGHT_MM,
            "min_usable_drawer_height_mm": STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM,
        },
        "pegboard_rules": pegboard_catalog(),
        "item_rules": {
            "profiles": [{"value": value, "label": label} for value, label in ITEM_PROFILES],
            "default_clearance_mm": ITEM_CLEARANCE,
            "bore_clearance_mm": BORE_CLEARANCE,
            "hex_bit": HEX_BIT_FIXED,
        },
        "text_depth_rules": {
            "min_backing_mm": TEXT_MIN_BACKING,
            "removable_base_plate_mm": BASE_PLATE,
        },
        "modes": [
            {"value": "fused", "label": "Printed into the bin"},
            {"value": "separate", "label": "Separate insert (lifts out)"},
        ],
        "parts": parts,
        "wall_rules": {
            "default_mm": DEFAULT_WALL,
            "min_mm": MIN_WALL,
            "max_mm": MAX_WALL,
            "step_mm": WALL_STEP,
            # What a *new* design may be given.  MIN_WALL/WALL_STEP stay as
            # the validation floor and quantum, so a saved design carrying a
            # non-preset wall still loads and regenerates unchanged.
            "choices": [
                {"value": value, "label": label} for value, label in WALL_PRESETS
            ],
            "wall_depth_factor": math.sqrt(1.0 + max_wave_slope() ** 2),
            "wave_amplitude_mm": WAVE_AMPLITUDE,
            "mating_gap_mm": WAVE_MATING_GAP,
        },
        "base_rules": {
            "default_mm": DEFAULT_BASE_THICKNESS,
            # What a *new* design may be given.  A saved design carrying a
            # non-preset value still loads and regenerates unchanged; the UI
            # shows it as a legacy value until the user picks a current preset.
            "choices": [
                {"value": value, "label": label} for value, label in BASE_PRESETS
            ],
        },
        "stack_rules": {
            "min_wall_mm": STACK_MIN_WALL,
            "default_wall_mm": DEFAULT_WALL,
            "default_base_mm": DEFAULT_BASE_THICKNESS,
            "base_min_by_wall_mm": _stack_base_min_by_wall(),
        },
        "lid_rules": {
            "thicknesses": [
                {"value": name, "mm": float(name), "name": LID_THICKNESS_NAMES.get(name, "")}
                for name in LID_THICKNESSES
            ],
            "default_thickness": "1.2",
            # A handle is opt-in: handle_enabled defaults to false and a
            # stackable lid never has one. There is one handle: the knob.
            "handle_default_enabled": False,
            "handle_types": ["knob"],
            "handle_sizes": ["small", "medium", "large"],
            "handle_positions": ["left", "right", "front", "back", "middle"],
            "label_styles": ["flush", "raised"],
            "label_orientations": ["horizontal", "vertical"],
            # Backend-owned: the browser builds its choices from these, it
            # carries no mm table of its own.
            "fits": [
                {"value": name, "mm": LID_FIT_MM[name],
                 "label": f"{LID_FIT_NAMES[name]} — {LID_FIT_MM[name]:g} mm per side"}
                for name in LID_FITS
            ],
            "default_fit": "standard",
            "alignments": [
                {"value": name, "mm": LID_ALIGNMENT_MM[name],
                 "label": (LID_ALIGNMENT_NAMES[name] if name == "off"
                           else f"{LID_ALIGNMENT_NAMES[name]} — {LID_ALIGNMENT_MM[name]:.1f} mm")}
                for name in LID_ALIGNMENTS
            ],
            "default_alignment": "off",
            "label_reliefs": [
                {"value": value, "name": LID_LABEL_RELIEF_NAMES[value],
                 "label": f"{LID_LABEL_RELIEF_NAMES[value]} {value:g} mm"}
                for value in LID_LABEL_RELIEFS
            ],
            "default_label_relief_mm": 0.4,
            "legacy_raised_label_relief_mm": LID_LABEL_LEGACY_RAISED_MM,
        },
        "storage_drawers_rules": {
            "default_usable_height_mm": STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM,
            "default_field_mm": list(STORAGE_DRAWERS_DEFAULT_FIELD_MM),
            "min_units": STORAGE_DRAWERS_MIN_UNITS,
            "max_units": STORAGE_DRAWERS_MAX_UNITS,
            "min_drawers": STORAGE_DRAWERS_MIN_DRAWERS,
            "max_drawers": STORAGE_DRAWERS_MAX_DRAWERS,
            "drawer_fit_choices_mm": list(STORAGE_DRAWER_FIT_CHOICES),
            "default_drawer_fit_mm": STORAGE_DRAWER_FIT_DEFAULT,
            "frame_width_choices_mm": list(STORAGE_DRAWER_FRAME_WIDTH_CHOICES),
            "default_frame_width_mm": STORAGE_DRAWER_FRAME_WIDTH_DEFAULT,
            "label_limit": STORAGE_DRAWER_LABEL_LIMIT,
            "max_usable_height_mm": STORAGE_DRAWER_MAX_USABLE_HEIGHT_MM,
            "default_printer_build_mm": list(DEFAULT_PRINTER_BUILD_MM),
        },
        "b4b_rules": {
            "grid_pitch_mm": GRID_PITCH,
            "lid_headroom_choices_mm": list(B4B_LID_HEADROOM_CHOICES),
            # Latch count and strength are derived from the case; both lists
            # remain only so an older saved design still parses.
            "latch_counts": list(B4B_LATCH_COUNTS),
            "latch_strengths": list(B4B_LATCH_STRENGTHS),
            "label_locations": list(B4B_LABEL_LOCATIONS),
            "front_label_styles": list(B4B_FRONT_LABEL_STYLES),
            "schema_version": B4B_SCHEMA_VERSION,
            "min_field_mm": B4B_MIN_FIELD_XY,
            "min_secure_height_mm": B4B_LATCHED_MIN_HEIGHT,
            "min_wall_mm": B4B_MIN_WALL,
            "default_wall_mm": B4B_DEFAULT_WALL,
            "wall_choices": [
                {"value": value, "label": label} for value, label in B4B_WALL_PRESETS
            ],
            "default_base_mm": B4B_DEFAULT_BASE,
            "base_choices": [
                {"value": value, "label": label} for value, label in B4B_BASE_PRESETS
            ],
            "handle_min_grip_mm": B4B_HANDLE_GRIP_ABS_MIN,
            "stack_min_base_mm": B4B_STACK_MIN_BASE,
        },
        "base_trim_rules": {
            "unit_mm": BASE_UNIT,
            "mating_gap_mm": WAVE_MATING_GAP,
            "max_field_mm": BASE_TRIM_MAX_FIELD,
            "default_width_mm": BASE_TRIM_DEFAULT_WIDTH,
            "default_height_mm": BASE_TRIM_DEFAULT_HEIGHT,
            "min_width_mm": BASE_TRIM_MIN_WIDTH,
            "max_width_mm": BASE_TRIM_MAX_WIDTH,
            "min_height_mm": BASE_TRIM_MIN_HEIGHT,
            "max_height_mm": BASE_TRIM_MAX_HEIGHT,
            "outer_taper_mm": BASE_TRIM_OUTER_TAPER,
            "default_bed_x_mm": BASE_TRIM_DEFAULT_BED_X,
            "default_bed_y_mm": BASE_TRIM_DEFAULT_BED_Y,
            "bed_edge_margin_mm": BASE_TRIM_BED_EDGE_MARGIN,
            "join_types": [
                {"value": value, "label": BASE_TRIM_JOIN_LABELS[value]}
                for value in BASE_TRIM_JOIN_TYPES
            ],
            "size_presets": [
                {"key": key, "value_mm": value, "label": label}
                for key, value, label in BASE_TRIM_SIZE_PRESETS
            ],
        },
        "lift_grabbers": {
            "default_size": "medium",
            "default_location": "sides",
            "min_wall_mm": round(lift_grabber_min_wall(), 3),
            "rim_clearance_mm": LIFT_GRABBER_RIM_CLEARANCE,
            "sizes": [
                {
                    "value": value,
                    "label": label,
                    "height_mm": LIFT_GRABBER_DIMENSIONS[value].height,
                }
                for value, label in (
                    ("small", "Small"),
                    ("medium", "Medium"),
                    ("large", "Large"),
                    ("xl", "XL"),
                )
            ],
            "locations": [
                {"value": "sides", "label": "Sides (left/right)"},
                {"value": "front_back", "label": "Front/back"},
                {"value": "both", "label": "Both"},
            ],
        },
        "scoop_rules": {
            "height_fraction": SCOOP_HEIGHT_FRACTION,
        },
        "edge_mount": {
            "sides": [
                {"value": "front", "label": "Front"},
                {"value": "back", "label": "Back"},
                {"value": "left", "label": "Left"},
                {"value": "right", "label": "Right"},
            ],
            "thickness_choices": [
                {"value": value, "label": f"{value:g} mm — {name}"}
                for value, name in EDGE_LABEL_THICKNESS_PRESETS
            ],
            "defaults": {
                "side": "front",
                "label_enabled": False,
                "label_text": "",
                "label_projection_mm": EDGE_LABEL_DEFAULT_PROJECTION,
                "label_length_mode": "full",
                "label_thickness_mm": EDGE_LABEL_DEFAULT_THICKNESS,
                "label_raised": False,
                "label_text_depth_mm": EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
                "label_flip": False,
                "holes_enabled": False,
                "hole_count": 2,
                "hole_orientation": "horizontal",
                "screw_diameter_mm": EDGE_HOLE_DEFAULT_SCREW_DIAMETER,
                "access_diameter_mm": None,
                "top_offset_mm": EDGE_HOLE_DEFAULT_TOP_OFFSET,
                "hole_spacing_mm": None,
            },
            "min_projection_mm": EDGE_LABEL_MIN_PROJECTION,
            "max_projection_mm": EDGE_LABEL_MAX_PROJECTION,
            "min_thickness_mm": EDGE_LABEL_MIN_THICKNESS,
            "max_thickness_mm": EDGE_LABEL_MAX_THICKNESS,
            "min_text_depth_mm": EDGE_LABEL_MIN_TEXT_DEPTH,
            "max_text_depth_mm": EDGE_LABEL_MAX_TEXT_DEPTH,
            "min_screw_diameter_mm": EDGE_HOLE_MIN_SCREW_DIAMETER,
            "max_screw_diameter_mm": EDGE_HOLE_MAX_SCREW_DIAMETER,
            "min_access_diameter_mm": EDGE_HOLE_MIN_ACCESS_DIAMETER,
            "max_access_diameter_mm": EDGE_HOLE_MAX_ACCESS_DIAMETER,
            "min_hole_count": EDGE_HOLE_MIN_COUNT,
            "max_hole_count": EDGE_HOLE_MAX_COUNT,
        },
        "side_openings": {
            "min_side_mm": SIDE_OPENING_MIN_SIDE_MM,
            "corner_margin_mm": SIDE_OPENING_CORNER_MARGIN_MM,
            "top_bridge_mm": SIDE_OPENING_TOP_BRIDGE_MM,
            "arch_curve": SIDE_OPENING_ARCH_CURVE,
            "default_shape": "curved",
            "default_size": "medium",
            "default_from_bottom_percent": 0,
            "default_from_top_percent": 0,
            "sides": [
                {"value": "front", "label": "Front"},
                {"value": "back", "label": "Back"},
                {"value": "left", "label": "Left"},
                {"value": "right", "label": "Right"},
            ],
            "shapes": [
                {"value": "curved", "label": "Curved"},
                {"value": "square", "label": "Square"},
            ],
            "sizes": [
                {"value": key, "label": label, "width_mm": SIDE_OPENING_WIDTHS[key]}
                for key, label in (
                    ("small", "Small — 8 mm"),
                    ("medium", "Medium — 10 mm"),
                    ("large", "Large — 15 mm"),
                    ("xl", "XL — 20 mm"),
                )
            ],
        },
        "setting_interactions": [
            {
                "feature": definition.kind,
                "source": rule.source,
                "target": rule.target,
                "effect": rule.effect,
                "owner": rule.owner,
                "reason": rule.reason,
            }
            for definition in feature_definitions()
            for rule in setting_interactions(definition.kind)
        ],
        "runtime": {
            "hosted": environment["hosted"],
            "filesystem": "browser" if environment["hosted"] else "server",
        },
        "defaults": {
            "design": default_design(),
            # A Render path is implementation detail, never a user's folder.
            "output": "" if environment["hosted"] else environment["output"],
            "connector": {
                "tolerance": LOCKED_TOLERANCE,
                "height": LOCKED_CONNECTOR_HEIGHT,
                "length": LOCKED_CONNECTOR_LENGTH,
                "arm_thickness": DEFAULT_ARM_THICKNESS,
                "axis": "y",
                "position": 0.0,
                "bin_a_height": 40.0,
                "bin_b_height": 40.0,
                "different_heights": False,
                "type": "side",
                "quantity": 1,
            },
            "sampler_boxes": DEFAULT_SAMPLE_BOXES,
        },
        # The differing-clip rules, so the UI can show the self-adjusting
        # length / web thickness / printed height live without a round-trip.
        "connector_rules": {
            "min_drop_mm": DIFFERING_MIN_DROP,
            "full_drop_mm": DIFFERING_FULL_DROP,
            "web_thickness_mm": DIFFERING_WEB_THICKNESS,
            "length_gain": DIFFERING_LENGTH_GAIN,
            "arm_thickness_mm": DEFAULT_ARM_THICKNESS,
            "base_height_mm": LOCKED_CONNECTOR_HEIGHT,
            # The web's fixed inward reach is not a fraction of the drop, so
            # the browser cannot get it from the ramp alone. These are its
            # inputs, served rather than hard-coded so the live readout and
            # the generated part can never disagree.
            "mating_gap_mm": WAVE_MATING_GAP,
            "web_run_clearance_mm": DIFFERING_WEB_RUN_CLEARANCE,
            "wall_depth_factor": math.sqrt(1.0 + max_wave_slope() ** 2),
            "arm_thickness_floor_mm": connector_arm_thickness_floor(),
        },
        "preferences": {} if environment["hosted"] else environment["preferences"],
        "slicer": {
            "available": False if environment["hosted"] else environment["slicer"]["available"],
            "path": None if environment["hosted"] else environment["slicer"]["path"],
            "name": "Bambu Studio" if environment["hosted"] else environment["slicer"]["name"],
        },
    }
