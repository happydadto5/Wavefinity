"""Local browser interface for Wavefinity.

The HTTP layer is deliberately small and dependency-free. It translates JSON
to the immutable models shared with the command-line tools; every preview,
validation and export comes from the existing Python geometry engine.
"""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
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
    MIN_BOX_SIZE,
    MIN_HEIGHT_ABOVE_BASE,
    MIN_WALL,
    SIDE_OPENING_WIDTHS,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    WALL_STEP,
    BoxSpec,
    ConnectorSpec,
    LID_FIT_MM,
    LID_FIT_NAMES,
    LID_FITS,
    LID_LABEL_LEGACY_RAISED_MM,
    LID_LABEL_RELIEF_NAMES,
    LID_LABEL_RELIEFS,
    LidSpec,
    StackSpec,
    differing_connector_plan,
    differing_web_reach,
    lift_grabber_min_wall,
    LIFT_GRABBER_DIMENSIONS,
    LIFT_GRABBER_RIM_CLEARANCE,
    SCOOP_HEIGHT_FRACTION,
    lid_enabled,
    make_top_label,
    make_top_label_ledge,
    max_wave_slope,
    generate_sampler,
    wavy_cavity_polygon,
)
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    FEATURE_DEFINITIONS,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    build_features,
    connector_keep_out,
    cradle_min_footprint,
    divider_cells,
    divider_scoop_targets,
    feature_definition,
    feature_definitions,
    feature_min_footprint,
    clamp_nest_feature_options,
    fitted_nest_feature,
    is_legacy_nest,
    nest_access_preview,
    nest_occurrence_preview,
    nest_quantity,
    nest_contour_polygon,
    nest_smoothed_contour,
    require_measured_tool_thickness,
    resolve_nest_settings,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    normalize_bore_modes,
    moved_feature,
    occupied_zones,
    option_value,
    normalize_divider_scoop,
    resized_feature,
    bore_bin_minimum,
    scoop_zone,
    resolve_text_features,
    resolved_options,
    setting_interactions,
    snapped_zone,
    text_of,
)
from organizer_inserts._bore import BORE_CLEARANCE, HEX_BIT_FIXED, is_walls_only, normalize_bore_style, bore_reference_top
from organizer_inserts._core import ITEM_CLEARANCE, ITEM_PROFILES, feature_touches_wall
from organizer_drawer import (
    blocking_problem_messages, blocking_problem_copy, drawer_report, drawer_routes, generate_connectors, inventory_row_files,
    prepare_inventory_bins, selected_blocking_problems, stack_part_height,
    _space_connectors,
)
from organizer_inventory import (
    append_bin, configure_space_text, design_specs, load_inventory, mark_printed_rows,
    normalise_storage_box, resolve_inventory_path,
)
from organizer_product_rules import (
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    surface_maximums,
)
from organizer_space_outputs import (
    BASE_TRIM, STORAGE_BOX, STORAGE_DRAWERS, structural_design, structural_kind,
)
from organizer_inventory import storage_drawers_mutate_text
from organizer_printer_profile import (
    DEFAULT_PRINTER_BUILD_MM,
    component_fit,
    normalise_printer_profile,
    print_file_fit_issues,
    printer_profile_from_preferences,
)
from organizer_storage_drawers import (
    STORAGE_DRAWER_FIT_CHOICES,
    STORAGE_DRAWER_FIT_DEFAULT,
    STORAGE_DRAWER_FRAME_WIDTH_CHOICES,
    STORAGE_DRAWER_FRAME_WIDTH_DEFAULT,
    STORAGE_DRAWER_LABEL_LIMIT,
    STORAGE_DRAWERS_MAX_DRAWERS,
    STORAGE_DRAWERS_MAX_UNITS,
    STORAGE_DRAWERS_MIN_DRAWERS,
    STORAGE_DRAWERS_MIN_UNITS,
    normalise_storage_drawers_definition,
    reset_storage_drawers_definition,
    storage_drawers_definition_problem,
)
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan, storage_drawers_summary
from organizer_base_trim_outputs import (
    BASE_TRIM_OUTPUT_KEY,
    base_trim_plan,
    base_trim_status,
    export_base_trim,
    materialize_base_trim,
    public_plan as base_trim_public_plan,
)
from organizer_storage_drawer_outputs import (
    STRUCTURAL_OUTPUT_KEY,
    materialize_storage_drawers,
    structural_manifest_plan,
    structural_signature,
    structural_status,
    sweep_cabinet_debris,
)
from organizer_product_rules import STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
from organizer_spaces import (
    commit_structural_output,
    default_space_parent,
    describe as describe_space_folder,
    effective_space_root,
    inventory_enabled,
    space_routes,
    storage_startup_state,
    structural_output_manifest,
)
from organizer_app import (
    LABEL_POSITIONS,
    APP_DIR,
    DEFAULT_SAMPLE_BOXES,
    _customization_zones,
    _mesh_preview_geometry,
    base_height,
    clean_label,
    convert_layout_mode,
    connector_filename,
    corner_connector_filename,
    default_feature,
    design_from_dict,
    design_source_payload,
    design_to_dict,
    generate_organizer_files,
    generate_organizer_files_transactional,
    generate_corner_file,
    generate_side_file,
    inside_handle_conflict,
    inventory_bin_record,
    object_height_plan,
    lid_label_regions,
    parse_sizes,
    preview_geometry,
    validate_customization_clearance,
)
from organizer_b4b import (
    B4B_HANDLE_GRIP_ABS_MIN,
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    B4B_MIN_WALL,
    B4B_STACK_MIN_BASE,
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
    base_trim_design_to_dict,
    base_trim_enabled,
    base_trim_from_design,
    base_trim_inner_polygon,
    base_trim_summary,
    generate_base_trim_files,
    generate_base_trim_joint_test_file,
    make_base_trim_pieces,
)
from organizer_stack import (
    STACK_MIN_WALL,
    make_lid_parts,
    stack_base_minimum,
    stack_effective_box,
    stack_enabled,
    stack_summary,
    validate_stack_design,
)
from organizer_slicer import slicer_display_name
from organizer_edge_mount import (
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
from organizer_side_openings import (
    SIDE_OPENING_ARCH_CURVE,
    SIDE_OPENING_CORNER_MARGIN_MM,
    SIDE_OPENING_MIN_SIDE_MM,
    SIDE_OPENING_TOP_BRIDGE_MM,
)
from organizer_pegboard import pegboard_catalog, pegboard_layout_for_bin

from dataclasses import replace
import ipaddress
import json
import math
import mimetypes
import os
from pathlib import Path
import shutil
import secrets
import subprocess
import sys
import threading
import time
import tempfile
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen
from photo_nest import photo_outline_from_data
from bambu_handoff import (
    _validate_settings_safe,
    is_bambu_studio_executable,
    stage_bambu_inputs,
)

from wavefinity_web_impl._runtime import (
    WEB_ROOT,
    IMAGE_ROOT,
    DEFAULT_OUTPUT,
    SERVER_VERSION,
    API_COMPAT_VERSION,
    SERVER_INSTANCE,
    SERVER_BUILD,
    SOURCE_FILES,
    source_fingerprint,
    SOURCE_ROOT,
    SOURCE_FINGERPRINT,
    GEOMETRY_LOCK,
    _PREVIEW_REQUEST_LOCK,
    _PREVIEW_REQUESTS,
    _SupersededGeometry,
    _register_preview_request,
    _preview_geometry_lock,
    LEGACY_PREFERENCES_FILE,
    _user_config_dir,
    PREFERENCES_LOCK,
    EXPORT_LOCK,
    EXPORT_TTL_SECONDS,
    EXPORTS,
    OPERATION_LOCK,
    OPERATION_REGISTRY,
    OPERATION_TTL_SECONDS,
    OPERATION_MAX_ENTRIES,
    _prune_operations,
    _idempotent_operation,
    operation_status_payload,
    default_design,
    _stack_base_min_by_wall,
    _read_preferences_file,
    _write_preferences_file,
    CONNECTOR_SETTINGS_FILENAME,
    _write_connector_settings_path,
    _drop_legacy_connector_settings,
    _interior_work_box,
    WavefinityServer,
    build_parser,
    _pid_on_port,
    _replace_stale_process,
)
from wavefinity_web_impl._nest import (
    _json_value,
    feature_to_dict,
    _item_from_json,
    _feature_from_json,
    NEST_TOOL_TOP_CLEARANCE,
    _nest_effective_z_requirement,
    _legacy_nest_z_requirement,
    _fit_photo_nest_box,
    _auto_size_photo_nest_box,
    _sized_photo_nest_box,
    _auto_size_photo_nest_layout_box,
    _resolve_photo_nest_edit,
    nest_retrace_payload,
    photo_nest_payload,
    _first_open_position,
    _option_payload,
)
from wavefinity_web_impl._designs import (
    _design,
    _is_base_trim_design,
    _base_trim_preview_meshes,
    _base_trim_preview_payload,
    _reject_if_b4b,
    _footprint_bounds,
    _resolved_text,
    _b4b_preview_payload,
    validate_design_payload,
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
    expand_layout_payload,
    inventory_preview_payload,
    pegboard_layouts_payload,
    create_space_text_payload,
    configure_space_text_payload,
)
from wavefinity_web_impl._ai import (
    AI_DESIGN_SCHEMA,
    AI_FEATURE_REFERENCE_REPO,
    AI_FEATURE_REFERENCE_PATH,
    _HEX40,
    ai_feature_reference_url,
    AI_MAX_DESCRIPTION,
    AI_MAX_RESPONSE,
    AI_SPACE_KINDS,
    AI_MEDIA_CAPABILITIES,
    AI_MEDIA_REASON,
    AI_MODIFIER_BLOCKS,
    _AI_PATH_RE,
    _ai_example_base,
    _ai_legal_values,
    _AI_GENERIC_FIELD_EXCLUSIONS,
    _ai_generic_fields,
    _ai_modifier_examples,
    _ai_clean_text,
    _ai_safe_message,
    _ai_bin_design,
    _ai_space_context,
    _capped_space_height,
    _ai_controlled_fields,
    _ai_fingerprint,
    _ai_prompt_text,
    _ai_num,
    _ai_item_profile_violation,
    _ai_close,
    _ai_semantic_violation,
    ai_repair_prompt_payload,
)
from wavefinity_web_impl._outputs import (
    slicer_name,
    _find_bambu_studio_windows,
    _find_bambu_studio_darwin,
    _find_bambu_studio_linux,
    SLICER_HANDOFF_TIMEOUT_S,
    open_log_with_wordpad,
    _PartialConnectorBundleError,
    _remove_export,
    _clean_expired_exports,
    _extract_generated_files,
    _printed_reuse_files,
    _is_storage_drawers_request,
    storage_drawers_mutate_text_payload,
    storage_drawers_preview_meshes,
    storage_drawers_validate_payload,
    storage_drawers_reset_payload,
    _storage_box_printer_fit,
    _is_base_trim_request,
    _storage_box_arrangement_issue,
    _surface_arrangement_issue,
)

HOSTED = (
    os.environ.get("WAVEFINITY_DEPLOYMENT", "local").lower() == "hosted"
    or os.environ.get("RENDER", "").lower() == "true"
)


def health_payload(client_address: str, *, hosted: bool = HOSTED) -> dict[str, Any]:
    result = {
        "ok": True, "version": SERVER_VERSION, "instance": SERVER_INSTANCE,
        "api_compat": API_COMPAT_VERSION, "build": SERVER_BUILD,
        "source_fingerprint": SOURCE_FINGERPRINT,
    }
    try:
        loopback = ipaddress.ip_address(client_address).is_loopback
    except ValueError:
        loopback = False
    if not hosted and loopback:
        result["source_root"] = SOURCE_ROOT
    return result


# A hosted server is not the end user's profile; it keeps the old file.
PREFERENCES_FILE = (
    LEGACY_PREFERENCES_FILE if HOSTED else _user_config_dir() / "wavefinity_prefs.json"
)
PID_FILE = Path(os.environ.get("WAVEFINITY_PID_FILE", str(APP_DIR / "wavefinity.pid")))


def load_preferences() -> dict[str, Any]:
    """Small local settings that should survive between browser sessions.

    A plain JSON file in the user's OS profile, not browser storage - the
    output folder is a filesystem path the *server* writes to, so it belongs
    with the server, and stays put across a different browser or a cleared
    profile. Until the profile file exists, the old app-local file is read as
    the starting point (never deleted, never merged over the profile file).
    """
    with PREFERENCES_LOCK:
        if PREFERENCES_FILE.exists() or PREFERENCES_FILE == LEGACY_PREFERENCES_FILE:
            return _read_preferences_file(PREFERENCES_FILE)
        return _read_preferences_file(LEGACY_PREFERENCES_FILE)


def mutate_preferences(mutator: Callable[[dict[str, Any]], Any]) -> dict[str, Any]:
    """Atomic read-modify-write of the preferences (nested data included).

    The mutator edits the dict in place, or returns a replacement.
    """
    with PREFERENCES_LOCK:
        current = load_preferences()
        replacement = mutator(current)
        if isinstance(replacement, dict):
            current = replacement
        _write_preferences_file(PREFERENCES_FILE, current)
        return current


def save_preferences(update: dict[str, Any]) -> dict[str, Any]:
    return mutate_preferences(lambda current: current.update(update))


def connector_settings_path(prefs: dict[str, Any] | None = None) -> Path | None:
    """Where desktop connector settings live: inside the Wavefinity folder.

    Returns None when hosted, when the configured storage parent is currently
    unavailable, or when the Wavefinity root does not exist yet. Callers then
    fall back to the legacy prefs location. Never create the Wavefinity folder
    just for settings (Fix 058 K).
    """
    if HOSTED:
        return None
    current = load_preferences() if prefs is None else prefs
    storage = storage_startup_state(current)
    if storage["unavailable"]:
        return None
    root = Path(storage["root"])
    return root / CONNECTOR_SETTINGS_FILENAME if root.is_dir() else None


def read_connector_settings_file(path: Path | None = None) -> dict[str, Any]:
    """Read the canonical folder file. Missing/malformed/unreadable means {}."""
    target = path if path is not None else connector_settings_path()
    if target is None:
        return {}
    with PREFERENCES_LOCK:
        return _read_preferences_file(target)


def write_connector_settings_file(settings: dict[str, Any]) -> bool:
    """Persist validated settings to the folder file when that root is usable.

    Returns True once the canonical folder file was written. A successful
    folder write also retires any legacy prefs copy. Returns False when there
    is nowhere to write it or the folder write itself fails.
    """
    with PREFERENCES_LOCK:
        prefs = load_preferences()
        path = connector_settings_path(prefs)
        if path is None:
            return False
        try:
            _write_connector_settings_path(path, settings)
        except OSError:
            return False
        if "connector_settings" in prefs:
            cleaned = dict(prefs)
            _drop_legacy_connector_settings(cleaned)
            try:
                _write_preferences_file(PREFERENCES_FILE, cleaned)
            except OSError:
                # The folder file is already canonical. served_preferences()
                # retries legacy cleanup on the next catalog load.
                pass
        return True


def served_preferences() -> dict[str, Any]:
    """Preferences as served to the browser, with connector settings resolved.

    One-time migration moves a legacy connector_settings object into the
    Wavefinity-folder file. If the folder file already exists, it wins and any
    stale legacy copy is retired. A malformed canonical file does not resurrect
    stale legacy data.
    """
    with PREFERENCES_LOCK:
        prefs = load_preferences()
        path = connector_settings_path(prefs)
        if path is None:
            return prefs

        legacy = prefs.get("connector_settings")
        if not path.exists() and isinstance(legacy, dict):
            try:
                _write_connector_settings_path(path, legacy)
            except OSError:
                return prefs

        if path.exists():
            if "connector_settings" in prefs:
                cleaned = dict(prefs)
                _drop_legacy_connector_settings(cleaned)
                try:
                    _write_preferences_file(PREFERENCES_FILE, cleaned)
                except OSError:
                    pass
                prefs = cleaned
            file_settings = read_connector_settings_file(path)
            prefs.pop("connector_settings", None)
            if file_settings:
                prefs["connector_settings"] = file_settings
        return prefs


def nest_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Trace-only phase (spec section 1): paper detection/correction,
    segmentation and contour extraction. Independent of any design - it does
    not require Tool thickness, and never modifies a design, resizes a bin,
    or builds Nest geometry. Manual paper-corner recovery also calls this,
    with explicit corners in place of automatic detection."""
    corners_raw = payload.get("paper_corners")
    corners = (
        [[float(v) for v in point] for point in corners_raw]
        if isinstance(corners_raw, list) and len(corners_raw) == 4 else None
    )
    outline = photo_outline_from_data(
        str(payload.get("image", "")), str(payload.get("mime_type", "")),
        str(payload.get("paper_size", "letter")),
        float(payload.get("sensitivity", 50.0)), float(payload.get("cleanup", 50.0)),
        corners,
    )
    result = {
        "contour": [list(point) for point in outline.contour],
        "outline": {"width": outline.width, "depth": outline.depth},
        "trace_center_mm": list(outline.trace_center_mm) if outline.trace_center_mm else None,
    }
    if outline.reference_image and outline.reference_bounds:
        result["reference"] = {
            "image": outline.reference_image,
            "bounds": list(outline.reference_bounds),
        }
    if outline.rectified_image:
        # Kept only in the browser's own session state for later retracing -
        # never written into the saved design.
        result["rectified_image"] = outline.rectified_image
    return result


def catalog_payload() -> dict[str, Any]:
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
    import sys
    return {
        "platform": sys.platform,
        "version": SERVER_VERSION,
        "instance": SERVER_INSTANCE,
        "api_compat": API_COMPAT_VERSION,
        "build": SERVER_BUILD,
        "base_unit": BASE_UNIT,
        "max_box_size": MAX_BOX_SIZE,
        "min_height_above_base_mm": MIN_HEIGHT_ABOVE_BASE,
        "drawer_rules": {
            "hard_wall_clearance_mm": DRAWER_HARD_CLEARANCE_MM,
            "ordinary_bin_min_height_mm": ORDINARY_BIN_MIN_HEIGHT_MM,
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
            {"value": "fused", "label": "Fused into box"},
            {"value": "separate", "label": "Removable insert"},
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
            "thicknesses": ["thin", "medium", "thick"],
            "handle_types": ["knob", "pull"],
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
            "min_units": STORAGE_DRAWERS_MIN_UNITS,
            "max_units": STORAGE_DRAWERS_MAX_UNITS,
            "min_drawers": STORAGE_DRAWERS_MIN_DRAWERS,
            "max_drawers": STORAGE_DRAWERS_MAX_DRAWERS,
            "drawer_fit_choices_mm": list(STORAGE_DRAWER_FIT_CHOICES),
            "default_drawer_fit_mm": STORAGE_DRAWER_FIT_DEFAULT,
            "frame_width_choices_mm": list(STORAGE_DRAWER_FRAME_WIDTH_CHOICES),
            "default_frame_width_mm": STORAGE_DRAWER_FRAME_WIDTH_DEFAULT,
            "label_limit": STORAGE_DRAWER_LABEL_LIMIT,
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
            "hosted": HOSTED,
            "filesystem": "browser" if HOSTED else "server",
        },
        "defaults": {
            "design": default_design(),
            # A Render path is implementation detail, never a user's folder.
            "output": "" if HOSTED else str(DEFAULT_OUTPUT),
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
        "preferences": {} if HOSTED else served_preferences(),
        "slicer": {
            "available": False if HOSTED else (slicer_exe := detect_bambu_studio()) is not None,
            "path": None if HOSTED else str(slicer_exe) if slicer_exe else None,
            "name": "Bambu Studio" if HOSTED else slicer_name(slicer_exe),
        },
    }


def detect_bambu_studio(custom_path: str | None = None) -> Path | None:
    if custom_path:
        p = Path(custom_path).expanduser().resolve()
        if p.is_file():
            return p
    prefs = load_preferences()
    if prefs.get("slicer_path"):
        p = Path(prefs["slicer_path"]).expanduser().resolve()
        if p.is_file():
            return p
    if sys.platform == "win32":
        return _find_bambu_studio_windows()
    elif sys.platform == "darwin":
        return _find_bambu_studio_darwin()
    else:
        return _find_bambu_studio_linux()


def launch_slicer(slicer_path: Path, files: list[Path]) -> Path | None:
    """Open ``files`` directly in the slicer.

    Fix 058: Wavefinity never manufactures a Bambu project for handoff.
    Bambu Studio gets each requested physical occurrence (repeated files mean
    repeated physical copies, never deduplicated) staged as a profile-free
    model file and opened directly - no ``--export-3mf``, ``--arrange``,
    ``--slice``, ``--load-settings`` or ``--load-filaments``, so Wavefinity
    can never introduce or select a printer/process/filament preset. Other
    slicers keep getting the files directly. Always returns ``None`` now:
    there is no manufactured project path to report. Fix 096 C8: the Popen
    handle is retained for a one-second startup handshake — still running
    after ``SLICER_HANDOFF_TIMEOUT_S`` is an accepted handoff, a nonzero
    quick exit raises ``RuntimeError``, and a zero quick exit is accepted
    (single-instance handoff to an already-running slicer).
    """
    if not slicer_path.is_file():
        raise FileNotFoundError(f"Slicer executable not found: {slicer_path}")
    if not files:
        raise ValueError("No files to open in slicer")
    if is_bambu_studio_executable(slicer_path):
        staged = stage_bambu_inputs(files)
        args = [str(slicer_path.resolve())] + [str(p) for p in staged]
    else:
        args = [str(slicer_path.resolve())] + [str(f.resolve()) for f in files]
    process = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    try:
        return_code = process.wait(timeout=SLICER_HANDOFF_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # Still running after one second: the GUI accepted the handoff.
        # (Do not kill it — it is the slicer the user asked for.)
        return None
    if return_code != 0:
        raise RuntimeError(
            f"The slicer exited immediately (code {return_code}) instead of opening. "
            "Your files were kept.")
    # Zero quick exit: a single-instance launcher handing off to the already
    # running slicer. Accepted as a successful handoff.
    return None


def preferences_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        return {"preferences": {}}
    update: dict[str, Any] = {}
    if "output" in payload:
        update["output"] = str(payload["output"])
    if "slicer_path" in payload:
        update["slicer_path"] = str(payload["slicer_path"]) if payload["slicer_path"] else ""
    for key, label in (
        ("base_trim_bed_x_mm", "Bed X"),
        ("base_trim_bed_y_mm", "Bed Y"),
    ):
        if key in payload:
            value = float(payload[key])
            if not math.isfinite(value) or value <= 2.0 * BASE_TRIM_BED_EDGE_MARGIN:
                raise ValueError(f"{label} must leave a positive printable area after edge clearance.")
            update[key] = value
    if "connector_settings" in payload:
        raw = payload["connector_settings"]
        if not isinstance(raw, dict):
            raise ValueError("Connector settings must be an object.")
        settings: dict[str, Any] = {}
        # Same legal ranges as the connector form fields.
        limits = {
            "tolerance": (0.0, 1.0), "length": (2.0, None), "arm_thickness": (0.5, 10.0),
            "bin_a_height": (2.0, None), "bin_b_height": (2.0, None),
        }
        for key, (low, high) in limits.items():
            value = raw.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("Connector settings must be numbers.")
            value = float(value)
            if not math.isfinite(value) or value < low or (high is not None and value > high):
                raise ValueError("Connector settings are outside the allowed range.")
            if key == "arm_thickness" and value <= connector_arm_thickness_floor():
                raise ValueError("Connector arm thickness is too thin to generate.")
            settings[key] = value
        if not isinstance(raw.get("different_heights"), bool):
            raise ValueError("Connector settings are incomplete.")
        settings["different_heights"] = raw["different_heights"]
        if not write_connector_settings_file(settings):
            # No usable Wavefinity folder yet: keep the legacy prefs location
            # rather than creating or redirecting a Wavefinity root for settings.
            update["connector_settings"] = settings
    return {"preferences": save_preferences(update)}


def browse_slicer_path_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native file chooser to select a slicer executable."""
    if HOSTED:
        raise ValueError("Slicer selection is available in the local Wavefinity app only.")
    try:
        filetypes = [
            ("Executable Files", "*.exe" if sys.platform == "win32" else "*"),
            ("All Files", "*.*"),
        ]
        current = payload.get("current") or payload.get("slicer_path")
        initialdir = "C:\\Program Files" if sys.platform == "win32" else "/"
        if current:
            cur_path = Path(str(current))
            if cur_path.is_file():
                initialdir = str(cur_path.parent)
            elif cur_path.is_dir():
                initialdir = str(cur_path)
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(filedialog.askopenfilename(parent=root, title="Select Slicer Executable (e.g. Bambu Studio)", initialdir={repr(initialdir)}, filetypes={repr(filetypes)}))
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        selected = result.stdout.strip()
    except Exception as error:
        raise RuntimeError("could not open the file chooser") from error
    # The chooser has no side effect; the browser saves through /api/preferences.
    return {"slicer_path": selected or None}


def show_folder_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native file explorer to the trusted current save folder."""
    if HOSTED:
        raise ValueError("Cannot open native folders in hosted mode.")
    prefs = load_preferences()
    folder_str = prefs.get("output")
    if not folder_str:
        raise ValueError("No active folder is set.")
    folder = Path(str(folder_str)).expanduser()
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {folder}")
    try:
        import sys
        import subprocess
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.run(["open", folder], check=False)
        else:
            subprocess.run(["xdg-open", folder], check=False)
    except Exception as e:
        raise RuntimeError(f"Could not open folder: {e}")
    return {"ok": True}


def browse_output_folder_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native folder chooser for this local desktop app.

    Fix 058 K "Critical no-side-effect rule": browsing, opening this chooser,
    or cancelling it must never create ``Documents/Wavefinity`` or any custom
    Wavefinity root. The effective Space root is only ever used here as an
    *initial directory* when it already exists; it is never created merely to
    have somewhere to point the picker.
    """
    if HOSTED:
        raise ValueError("Choose a folder in your browser instead.")
    try:
        space_root = bool(payload.get("space_root"))
        spaces_root = effective_space_root(load_preferences())
        current = Path(str(payload.get("current") or DEFAULT_OUTPUT)).expanduser()
        if space_root:
            initial = spaces_root if spaces_root.is_dir() else (
                default_space_parent() if default_space_parent().is_dir() else DEFAULT_OUTPUT
            )
        else:
            initial = current if current.is_dir() else DEFAULT_OUTPUT
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(filedialog.askdirectory(parent=root, initialdir={repr(str(initial))}))
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        selected = result.stdout.strip()
    except Exception as error:
        raise RuntimeError("could not open the output-folder chooser") from error
    return {"folder": selected}


def browse_space_parent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The Welcome "Change" chooser for the first-run Space storage location.

    Fix 058 K: opens the native directory chooser to pick the *parent*
    directory that will contain the Wavefinity folder. Opening or cancelling
    this chooser creates nothing; a real selection saves the absolute chosen
    parent in preferences immediately (the effective root becomes
    ``<selected parent>/Wavefinity``) - but only while there is no established
    Wavefinity folder to move. With ``pick_only`` (Fix 083 Change Location) it
    just returns the chosen parent and saves nothing.
    """
    if HOSTED:
        raise ValueError("Space storage location is available in the local Wavefinity app only.")
    pick_only = bool(payload.get("pick_only"))
    if not pick_only and storage_startup_state(load_preferences())["root_exists"]:
        # An established Wavefinity folder is only ever changed through
        # Change Location (move / switch), never by silently saving a parent.
        raise ValueError("Use Change Location to move or switch your existing Wavefinity folder.")
    try:
        prefs = load_preferences()
        saved_raw = prefs.get("space_parent")
        saved = Path(str(saved_raw)).expanduser() if saved_raw else None
        docs = default_space_parent()
        if saved is not None and saved.is_dir():
            initial = saved
        elif docs.is_dir():
            initial = docs
        else:
            initial = Path.home()
        script = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.attributes("-topmost", True)
print(filedialog.askdirectory(parent=root, initialdir={repr(str(initial))}))
"""
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        selected = result.stdout.strip()
    except Exception as error:
        raise RuntimeError("could not open the storage-location chooser") from error
    if not selected:
        # A cancel is silent and leaves the current/default choice unchanged.
        return {"folder": None, "storage": storage_startup_state(load_preferences())}
    candidate = Path(selected).expanduser()
    if not candidate.is_dir():
        raise ValueError("That folder could not be found. Choose an existing folder.")
    absolute = candidate.resolve()
    if pick_only:
        # Change Location validates and applies the choice itself.
        return {"folder": str(absolute)}
    save_preferences({"space_parent": str(absolute)})
    return {"folder": str(absolute), "storage": storage_startup_state(load_preferences())}


def show_log_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Display the Wavefinity bins.md inventory in WordPad for the specified output folder."""
    if HOSTED:
        raise ValueError("Logs are saved to your chosen browser folder in hosted mode.")
    output_dir = Path(str(payload.get("output") or DEFAULT_OUTPUT)).expanduser().resolve()
    log_file = resolve_inventory_path(output_dir, migrate=True) if output_dir.is_dir() else None
    if log_file is None or not log_file.is_file():
        raise FileNotFoundError(f"No inventory file found in '{output_dir}'. Generate a bin in this folder first.")

    open_log_with_wordpad(log_file)
    return {"file": str(log_file)}


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    token = _register_preview_request(payload, "preview")
    try:
        return _preview_payload(payload, token)
    except _SupersededGeometry:
        return {"superseded": True}


def _preview_payload(payload: dict[str, Any], token) -> dict[str, Any]:
    if _is_base_trim_design(payload.get("design")):
        return _base_trim_preview_payload(payload, token)
    if isinstance(payload.get("design"), dict):
        box_raw = payload["design"].get("box", {})
        b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
        if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
            return _b4b_preview_payload(payload, token)
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    draft_raw = payload.get("draft")
    draft = _feature_from_json(draft_raw, layout.mode) if draft_raw else None
    if draft is not None:
        draft = normalize_bore_modes(
            _interior_work_box(box), draft,
            base_height(_interior_work_box(box), layout.mode), layout.mode,
        )
    selected = payload.get("selected")
    if not isinstance(selected, int) or isinstance(selected, bool):
        selected = None
    # Stacking derives the printable body from the visible legal settings and
    # the requested module-height datum.
    stack_request = box
    stack_block = None
    if stack_enabled(box) or lid_enabled(box):
        validate_stack_design(box)
        stack_block = stack_summary(box)
        box = stack_effective_box(box)
    with _preview_geometry_lock(token):
        scene = preview_geometry(
            box, label, layout.features, layout.mode, label_location, scoop, draft,
            selected=selected, layout=layout,
        )
        if lid_enabled(stack_request):
            lid, lid_texts = make_lid_parts(
                stack_request, lid_label_regions(stack_request, layout),
            )
            scene["geometry"].extend(_mesh_preview_geometry(lid, "lid"))
            for _text, mesh, _raised in lid_texts:
                scene["geometry"].extend(_mesh_preview_geometry(mesh, "lid_label"))
    bounds = layout_zone(box, layout.mode)
    geometry = [
        {"points": points, "kind": kind, "normal": normal,
         "layer": layer, "owner": owner,
         "pick": scene.get("pick_faces", {}).get(index)}
        for index, (points, kind, normal, layer, owner) in enumerate(scene["geometry"])
    ]
    cavity = wavy_cavity_polygon(box)
    resolved = layout
    canonical = design_to_dict(stack_request, resolved, label, part_name, label_location, scoop)
    planning_record = inventory_bin_record(stack_request, resolved, None, label, part_name, scoop)
    planning = object_height_plan(canonical, resolved.object_height_mm)
    planning["effective_mm"] = max(stack_part_height(planning_record), planning["object_top_mm"] or 0.0)
    storage_box_height_warning = None
    raw_space = payload.get("space")
    if isinstance(raw_space, dict) and raw_space.get("kind") in ("portable", "box"):
        cap = float(raw_space["z"]) + normalise_storage_box(raw_space.get("storage_box"))["lid_headroom_mm"]
        if stack_block is not None and stack_block["enabled"]:
            height = stack_block["closed_height_mm"] + stack_block["pitch_mm"]
            warning_kind = "two_bins"
        else:
            height = stack_block["closed_height_mm"] if lid_enabled(stack_request) else stack_part_height(planning_record)
            warning_kind = "one_bin"
        if height > cap + 1e-6:
            storage_box_height_warning = {
                "kind": warning_kind, "height_mm": round(height, 3), "cap_mm": round(cap, 3),
            }
    effective = list(layout.features)
    if draft is not None:
        if selected is not None and 0 <= selected < len(effective):
            effective[selected] = draft
        else:
            effective.append(draft)
    bore_warning = _capped_bore_warning(stack_request, layout, effective, payload.get("space"))
    return {
        "design": canonical,
        "planning": planning,
        "bore_ceiling_warning": bore_warning,
        "storage_box_height_warning": storage_box_height_warning,
        "stack": stack_block,
        "label_outline": scene["label_outline"],
        "label_meta": scene["label_meta"],
        "text_meta": scene["text_meta"],
        "geometry": geometry,
        "pick_proxies": scene.get("pick_proxies", []),
        "fits": scene["fits"],
        "message": scene["message"],
        "feature_errors": scene["feature_errors"],
        "invalid_feature_indexes": scene["invalid_feature_indexes"],
        "draft_error": scene["draft_error"],
        "feature_overhang_mm": scene["feature_overhang_mm"],
        "draft_overhang_mm": scene["draft_overhang_mm"],
        "dimensions": {
            "size": scene["size_text"],
            "inside_x": scene.get("inside_x"),
            "inside_y": scene.get("inside_y"),
        },
        "layout_bounds": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        # The true, wavy interior wall - Z-invariant, so one outline covers
        # the whole cavity - shown in the 2D layout so a full-span divider's
        # fit against the real wall is visible, not just against the flat
        # placement rectangle every other support is confined to.
        "cavity_outline": [[float(x), float(y)] for x, y in cavity.exterior.coords],
        "customization_zones": [
            {"name": name, "zone": [zone.x0, zone.y0, zone.x1, zone.y1]}
            for name, zone in scene["customization_zones"]
        ],
        # The floor each support actually covers, which for a fused cradle,
        # post or divider is smaller than the zone it is drawn in. The 2D
        # layout fills this and outlines the zone around it, so the open floor
        # a neighbour may now use is visible rather than implied.
        "feature_footprints": [
            _footprint_bounds(box, one, layout.mode) for one in layout.features
        ],
        "draft_footprint": _footprint_bounds(box, draft, layout.mode),
        "feature_outlines": [
            ([[float(x), float(y)] for x, y in nest_contour_polygon(one).exterior.coords]
             if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        # The Soften-outline result in each nest's own local millimetres, so the
        # 2D layout can apply its own cheap move/rotate/resize and still draw
        # the exact silhouette the printed cutter gets.
        "nest_soft_contours": [
            ([list(point) for point in nest_smoothed_contour(one)]
             if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        "draft_soft_contour": (
            [list(point) for point in nest_smoothed_contour(draft)]
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
        "nest_occurrences": [
            nest_occurrence_preview(one) if one.kind == "nest" and one.contour else None
            for one in layout.features
        ],
        "draft_nest_occurrences": (
            nest_occurrence_preview(draft)
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
        # Informational-only 2D indicators for the resolved finger-access plan
        # - a notch location on Raised Wall, a scoop footprint on Recessed.
        "nest_access": [
            (nest_access_preview(one) if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        "draft_nest_access": (
            nest_access_preview(draft)
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
    }


def generate_payload(
    payload: dict[str, Any],
    *,
    suppress_local_inventory: bool = False,
) -> dict[str, Any]:
    raw_design = payload["design"]
    if _is_base_trim_design(raw_design):
        spec = base_trim_from_design(raw_design)
        output = _generation_output(payload)
        with GEOMETRY_LOCK:
            result = generate_base_trim_files(
                spec,
                output,
                str(raw_design.get("part_name") or ""),
                auto_timestamp=bool(payload.get("auto_timestamp", False)),
            )
        return _generation_reply(result=result, output=output)
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    output = _generation_output(payload)
    auto_timestamp = bool(payload.get("auto_timestamp", False))
    requested_inventory = bool(payload.get("keep_log", False))
    if HOSTED:
        keep_log = requested_inventory
    elif suppress_local_inventory:
        keep_log = False
    else:
        keep_log = requested_inventory and inventory_enabled(output, load_preferences())
    with GEOMETRY_LOCK:
        # Fix 096 A1: the whole ordinary-bin file set installs as one unit -
        # staged, validated, then promoted - and inventory logging runs only
        # after the complete set promoted, so a row is never recorded for a
        # partial set.
        result = generate_organizer_files_transactional(
            box, layout, output, label, part_name, label_location, scoop,
            auto_timestamp=auto_timestamp,
            keep_log=keep_log and not HOSTED,
        )
    reply = _generation_reply(result=result, output=output)
    if HOSTED and requested_inventory:
        record = inventory_bin_record(
            box, layout, _extract_generated_files(result), label,
            part_name, scoop,
        )
        record["qty"] = 0
        reply["inventory_bin"] = record
        reply["inventory_design_spec"] = design_to_dict(box, layout, label, part_name, label_location, scoop)
    return reply


def base_trim_joint_test_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_design = payload["design"]
    if not _is_base_trim_design(raw_design):
        raise ValueError("The physical joint-fit sample needs a Base Trim design.")
    spec = base_trim_from_design(raw_design)
    output = _generation_output(payload)
    with GEOMETRY_LOCK:
        result = generate_base_trim_joint_test_file(spec, output, auto_timestamp=True)
    return _generation_reply(result=result, output=output)


def _generate_side_connector(
    payload: dict[str, Any], box: Any, options: dict[str, Any], output_dir: Path,
) -> tuple[Any, dict[str, Any]]:
    tolerance = float(options.get("tolerance", LOCKED_TOLERANCE))
    height = float(options.get("height", LOCKED_CONNECTOR_HEIGHT))
    arm_thickness = float(options.get("arm_thickness", DEFAULT_ARM_THICKNESS))
    connector = ConnectorSpec(
        tolerance=tolerance,
        height=height,
        arm_thickness=arm_thickness,
    )
    different_heights = bool(options.get("different_heights", False))
    requested_a = float(options.get("bin_a_height", box.z)) if different_heights else box.z
    requested_b = float(options.get("bin_b_height", box.z)) if different_heights else box.z
    length = float(options.get("length", LOCKED_CONNECTOR_LENGTH))

    # Direct-stack bins print with a taller body rim than the module height the
    # user typed, because the stacking foot extends the body. Connector fit has
    # to be validated - and built - against that real rim, not the request.
    if box.stack.mode == "direct":
        connector_box = stack_effective_box(box)
        rim_a = stack_effective_box(replace(box, z=requested_a)).z
        rim_b = stack_effective_box(replace(box, z=requested_b)).z
    else:
        connector_box = box
        rim_a = requested_a
        rim_b = requested_b

    # The filename still speaks in the module heights the user knows the bins
    # by, not the physical rim heights.
    filename = connector_filename(
        connector,
        length=length,
        bin_a_height=requested_a,
        bin_b_height=requested_b,
        arm_thickness=arm_thickness,
        different_heights=different_heights,
        wall=connector_box.wall,
    )
    with GEOMETRY_LOCK:
        result = generate_side_file(
            connector_box,
            connector,
            output_dir / filename,
            "y",
            0.0,
            length,
            rim_a,
            rim_b,
            web_thickness=arm_thickness if different_heights else None,
            auto_adjust=False,
        )
    plan = differing_connector_plan(
        connector, length, rim_a, rim_b, connector_box
    )
    if different_heights:
        plan["length_mm"] = length
        # The web is never thinner than the inward reach, whatever the browser
        # asked for, so report what was actually built - but only when a web
        # was actually built. A 1-2 mm drop deliberately makes no web at all.
        if plan["webbed"]:
            plan["web_thickness_mm"] = max(
                arm_thickness,
                arm_thickness + differing_web_reach(connector_box, connector),
            )
        else:
            plan["web_thickness_mm"] = connector.arm_thickness
    plan.update({
        "type": "side",
        "quantity": 1,
        "wall_mm": connector_box.wall,
        "requires_same_wall": True,
    })
    plan = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in plan.items()}
    return result, plan


def _generate_corner_connector(
    box: Any, output_dir: Path, ways: int,
) -> tuple[Any, dict[str, Any]]:
    # Corner connectors are automatic bundle members: always quantity 1, with
    # fresh defaults, since hidden Side/Different settings never reach them.
    connector = ConnectorSpec()
    connector_box = stack_effective_box(box) if box.stack.mode == "direct" else box
    filename = corner_connector_filename(ways, 1, connector_box.wall)
    with GEOMETRY_LOCK:
        result = generate_corner_file(
            connector_box, connector, output_dir / filename, ways, 1
        )
    plan = {
        "type": "three_way" if ways == 3 else "four_way",
        "quantity": 1,
        "wall_mm": round(connector_box.wall, 3),
        "requires_equal_height": True,
        "requires_same_wall": True,
        "printed_height_mm": round(connector.height, 3),
        "webbed": False,
    }
    return result, plan


def connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _is_base_trim_design(payload.get("design")):
        raise ValueError(
            "Connectors are generated from a bin design, not from a Base Trim design."
        )
    _reject_if_b4b(payload, "connectors")
    box, *_ = _design(payload["design"])
    if lid_enabled(box):
        raise ValueError("Connectors are unavailable while this bin has a lid.")
    options = payload.get("connector", {})
    different_heights = bool(options.get("different_heights", False))

    output_dir = _generation_output(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    side_result, side_plan = _generate_side_connector(payload, box, options, output_dir)

    if different_heights:
        plan = dict(side_plan)
        plan.update({
            "mode": "auto",
            "types": ["side"],
            "different_heights": True,
        })
        reply = {"connector_plan": plan}
        return _generation_reply(result={"side": side_result}, output=output_dir, extra=reply)

    results: dict[str, Any] = {"side": side_result}
    types = ["side"]
    skipped_types: list[str] = []
    for ways, key in ((3, "three_way"), (4, "four_way")):
        try:
            corner_result, _corner_plan = _generate_corner_connector(box, output_dir, ways)
        except ValueError:
            skipped_types.append(key)
            continue
        except Exception as error:
            # An unfit corner is a normal ValueError skip, handled above.
            # Anything else is unexpected - the connectors already in
            # `results` (at least the Side connector) are real files on
            # disk and must not be lost behind this exception.
            raise _PartialConnectorBundleError(error, dict(results), output_dir) from error
        results[key] = corner_result
        types.append(key)

    plan = {
        "mode": "auto",
        "types": types,
        "different_heights": False,
        "wall_mm": side_plan.get("wall_mm"),
        "requires_same_wall": True,
    }
    if skipped_types:
        plan["skipped_types"] = skipped_types
        plan["skipped_reason"] = (
            "Corner connectors need at least 16 mm (2 Wavefinity units) in both "
            "X and Y so the clip can clear the corners and engage the wall locks."
        )
    reply = {"connector_plan": plan}
    return _generation_reply(result=results, output=output_dir, extra=reply)


def connector_save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Direct /api/connector route: like Print, an unexpected later connector
    failure must not hide the connector files that already completed."""
    try:
        return connector_payload(payload)
    except _PartialConnectorBundleError as error:
        reply: dict[str, Any] = {
            "partial": True,
            "partial_stage": "connectors",
            "error": (
                "Some connector files were saved, but the remaining connectors "
                f"could not be generated: {error.error}"
            ),
        }
        output = error.output
        if output is None:
            return {**reply, "result": error.completed}
        if HOSTED:
            # Exposes the completed files through the normal export mechanism
            # so the browser can still save them to the chosen folder.
            return {**_generation_reply(result=error.completed, output=output), **reply}
        return {**reply, "result": error.completed, "output": str(output)}


def sampler_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, *_ = _design(payload["design"])
    options = payload.get("connector", {})
    connector = ConnectorSpec(
        tolerance=float(options.get("tolerance", LOCKED_TOLERANCE)),
        height=float(options.get("height", LOCKED_CONNECTOR_HEIGHT)),
    )
    output_dir = _generation_output(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    with GEOMETRY_LOCK:
        result = generate_sampler(
            output_dir / "Wavefinity fit sampler.3mf",
            sizes=parse_sizes(str(payload.get("boxes", DEFAULT_SAMPLE_BOXES))),
            height=box.z,
            wall=box.wall,
            base_thickness=box.base_thickness,
            connector=connector,
            side_length=float(options.get("length", LOCKED_CONNECTOR_LENGTH)),
            flat_inside=box.flat_inside,
        )
    return _generation_reply(result=result, output=output_dir)


def _generation_output(payload: dict[str, Any]) -> Path:
    """A hosted export belongs in an isolated, short-lived server workspace."""
    if HOSTED:
        return Path(tempfile.mkdtemp(prefix="wavefinity-export-"))
    return Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()


def _generation_reply(*, result: Any, output: Path, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    if not HOSTED:
        return {"result": result, "output": str(output), **(extra or {})}
    files = _extract_generated_files(result)
    if not files:
        shutil.rmtree(output, ignore_errors=True)
        raise RuntimeError("No files were generated.")
    token = secrets.token_urlsafe(24)
    names: dict[str, Path] = {}
    for file_path in files:
        name = file_path.name
        if name in names:
            raise RuntimeError("Generated files have duplicate names.")
        names[name] = file_path
    with EXPORT_LOCK:
        _clean_expired_exports()
        EXPORTS[token] = {
            "directory": output,
            "files": names,
            "expires": time.monotonic() + EXPORT_TTL_SECONDS,
        }
    return {
        "result": result,
        "files": [
            {"name": name, "url": f"/api/export/{token}/{quote(name)}"}
            for name in names
        ],
        **(extra or {}),
    }


def _generate_bin_from_design_spec(output_dir: Path, design_spec: dict[str, Any]) -> list[Path]:
    """Fix 034 F2: generate a spec-only Inventory row's files on demand.

    Uses the same generator as a normal Generate action, with Inventory
    append/logging suppressed - ``print_inventory_bins`` owns persisting the
    resolved File cell itself, still at Qty 0.
    """
    box, layout, label, part_name, label_location, scoop = design_from_dict(design_spec)
    with GEOMETRY_LOCK:
        # Fix 096 A1: on-demand batch generation installs as one unit too -
        # a row is recorded Saved only after its whole file set promoted.
        result = generate_organizer_files_transactional(
            box, layout, output_dir, label, part_name, label_location, scoop,
            auto_timestamp=False, keep_log=False,
        )
    return _extract_generated_files(result)


def print_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        raise ValueError("Hosted Wavefinity saves generated files to your selected folder instead.")
    target = str(payload.get("target", "bin"))

    # Preflight: a missing/invalid slicer must fail before any generation
    # file is written, so a bin 3MF is never created only to be orphaned by
    # an avoidable slicer-not-found error.
    custom = payload.get("slicer_path")
    slicer_path = detect_bambu_studio(custom)
    if slicer_path is None or not slicer_path.is_file():
        raise ValueError(
            "A slicer was not found. Please locate your slicer executable in settings or install a slicer (Bambu Studio or OrcaSlicer)."
        )
    profile = _printer_profile_for(payload)

    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name = slicer_display_name(slicer_path) or "the slicer"
    name_cap = slicer_display_name(slicer_path) or "The slicer"

    design_reused = False
    files: list[Path] = []
    if target == "connector":
        gen_result = connector_payload(payload)
    elif target == "sampler":
        gen_result = sampler_payload(payload)
    elif target == "base_trim_joint_test":
        gen_result = base_trim_joint_test_payload(payload)
    else:
        reused = _printed_reuse_files(payload) if target in {"bin", "all"} else None
        if reused is not None:
            # Unchanged Printed bin: hand the existing file(s) to the slicer.
            design_reused = True
            gen_result = {"output": str(reused[0]), "result": None}
            files = list(reused[1])
        else:
            # For Bambu printing, always auto-save with timestamp if file exists or unnamed
            gen_result = generate_payload(
                dict(payload, auto_timestamp=True),
                suppress_local_inventory=True,
            )

    if not design_reused:
        files = _extract_generated_files(gen_result)
    design_files = list(files)
    if target not in {"connector", "sampler", "base_trim_joint_test"} and not design_files:
        raise RuntimeError(f"No bin files were generated to send to {name}.")
    # Fix 096 A1: a listed file that is missing or empty means the set is
    # incomplete - never hand a partial set to the slicer.
    for design_file in design_files:
        checked = Path(design_file)
        if not checked.is_file() or checked.stat().st_size == 0:
            raise RuntimeError(
                "A bin file is missing or empty, so the slicer was not opened."
            )

    # Only the explicit "with connectors" print (target "all") carries the
    # automatic connector bundle (a Side connector, plus 3-Way and 4-Way
    # corners when the bin is eligible). A bin-only print never generates
    # connectors. Never for a B4B, whose lid controls the rim and which does not use the
    # connector, nor for a lidded bin or a Base Trim design.
    design = payload.get("design")
    is_base_trim = _is_base_trim_design(design)
    is_b4b = (
        isinstance(design, dict)
        and isinstance(design.get("box"), dict)
        and isinstance(design["box"].get("b4b"), dict)
        and design["box"]["b4b"].get("enabled")
    )
    has_lid = (
        isinstance(design, dict)
        and isinstance(design.get("box"), dict)
        and isinstance(design["box"].get("lid"), dict)
        and design["box"]["lid"].get("enabled")
    )
    if (
        target == "all"
        and not is_b4b
        and not has_lid
        and not is_base_trim
    ):
        # The bin file already exists on disk at this point, a real external
        # side effect. A connector failure here must be reported truthfully
        # as a partial success, never erased by letting the exception escape.
        try:
            connector_files = _extract_generated_files(connector_payload(payload))
        except _PartialConnectorBundleError as error:
            # One or more connectors (at least the Side connector, if it
            # completed) already exist on disk - report them alongside the
            # bin files rather than only the bin files.
            completed_files = _extract_generated_files(error.completed)
            return {
                "partial": True,
                "error": f"{'The bin file was reused, but' if design_reused else 'Bin files were saved, but'} connectors could not be generated: {error.error}",
                "partial_stage": "connectors",
                "design_reused": design_reused,
                "design_files": [str(f) for f in design_files],
                "files": [str(f) for f in files + completed_files],
            }
        except Exception as error:
            return {
                "partial": True,
                "error": f"{'The bin file was reused, but' if design_reused else 'Bin files were saved, but'} connectors could not be generated: {error}",
                "partial_stage": "connectors",
                "design_reused": design_reused,
                "design_files": [str(f) for f in design_files],
                "files": [str(f) for f in files],
            }
        files.extend(connector_files)

    if not files:
        raise RuntimeError(f"No 3MF files were generated to send to {name}.")

    # Every file handed to the slicer must fit the active printer. A fit
    # failure is reported before launch; files already saved are kept.
    fit_issues: list[str] = []
    for path in dict.fromkeys(files):
        fit_issues.extend(print_file_fit_issues(Path(path), profile))
    if fit_issues:
        return {
            "partial": True, "partial_stage": "preflight",
            "error": "A file does not fit the active printer:\n" + "\n".join(fit_issues),
            "design_reused": design_reused,
            "design_files": [str(f) for f in design_files],
            "files": [str(f) for f in files],
        }

    try:
        project_path = launch_slicer(slicer_path, files)
    except Exception as error:
        return {
            "partial": True,
            "error": (f"{name_cap} did not open: {error}" if design_reused and not (len(files) > len(design_files))
                      else f"Files were saved, but {name} did not open: {error}"),
            "partial_stage": "slicer",
            "design_reused": design_reused,
            "design_files": [str(f) for f in design_files],
            "files": [str(f) for f in files],
        }

    # Printed means the slicer really opened it: log the copy only now.
    if (
        target not in {"connector", "sampler", "base_trim_joint_test"}
        and not is_base_trim
    ):
        output_dir = Path(gen_result["output"])
        if (
            not payload.get("design_row_id")
            and not payload.get("structural_output")
            and inventory_enabled(output_dir, load_preferences())
        ):
            box, layout, label, part_name, location, scoop = _design(design)
            record = inventory_bin_record(
                box, layout, design_files, label, part_name, scoop,
            )
            append_bin(
                output_dir, **record, qty=1,
                design_spec=design_to_dict(box, layout, label, part_name, location, scoop),
            )
    return {
        "result": gen_result.get("result"),
        "output": gen_result.get("output"),
        "files": [str(f) for f in files],
        "design_files": [str(f) for f in design_files],
        "design_reused": design_reused,
        "slicer": str(slicer_path),
        "project": str(project_path) if project_path else None,
    }


def _printer_profile_for(payload: dict[str, Any]) -> dict[str, float]:
    """The one printer build volume. Hosted servers do not own the user's
    profile, so the browser supplies it; local reads the saved preferences."""
    if HOSTED:
        raw = payload.get("printer_profile")
        return normalise_printer_profile(raw or dict(zip(("x_mm", "y_mm", "z_mm"), DEFAULT_PRINTER_BUILD_MM)))
    try:
        return printer_profile_from_preferences(load_preferences())
    except ValueError as error:
        raise ValueError("Printer Settings could not be read. Open Printer Settings and choose Reset Printer Settings.") from error


def _structural_request(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The kind and transient design for the Space definition in ``payload``."""
    space = payload.get("space")
    kind = structural_kind(space if isinstance(space, dict) else None)
    if kind is None or kind == STORAGE_DRAWERS:
        raise ValueError("This Space type has no structural output.")
    profile = _printer_profile_for(payload)
    design = structural_design(space, bed_x_mm=profile["x_mm"], bed_y_mm=profile["y_mm"])
    return kind, design


def storage_drawers_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Read-only cabinet summary for a draft or saved definition."""
    space = payload.get("space")
    if not isinstance(space, dict):
        raise ValueError("Storage Drawers settings are missing.")
    return storage_drawers_summary(space, _printer_profile_for(payload))


def _local_cabinet_folder(payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    """The real Space folder, its authoritative typed Space, and its identity.

    The Space identity is mandatory: cabinet output is never written into, or
    handed to a slicer from, a folder whose current Space ID was not confirmed.
    """
    folder = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    info = describe_space_folder(folder, load_preferences())
    space = info.get("space")
    if info["folder_mode"] != "space" or not isinstance(space, dict) or space.get("kind") != "storage_drawers":
        raise ValueError("This folder is not a Storage Drawers Space.")
    expected = payload.get("space_id")
    if not expected:
        raise ValueError("The cabinet's Space could not be confirmed. Reopen the Space and try again. Nothing was changed.")
    if info["space_id"] != expected:
        raise ValueError("This folder is not the Space that was open before. Nothing was changed.")
    if info.get("cabinet_recovery"):
        raise ValueError("The cabinet settings are damaged. Choose Reset cabinet settings first. "
                         + info["cabinet_recovery"]["message"])
    # Orphan app-owned temp/backup files from an interrupted earlier save.
    sweep_cabinet_debris(folder)
    return folder, space, info["space_id"]


def _storage_drawers_structural_design(payload: dict[str, Any]) -> dict[str, Any]:
    space = normalise_storage_drawers_definition(payload["space"])
    profile = _printer_profile_for(payload)
    # Fix 103 (Section D + R4): the 3D preview is built from production
    # meshes without an output folder, but ONLY when explicitly requested
    # via include_preview (structural Design preview). Ordinary summary/
    # status calls must not trigger mesh generation.
    include_preview = bool(payload.get("include_preview"))
    preview = storage_drawers_preview_meshes(space) if include_preview else None
    reply: dict[str, Any] = {
        "kind": STORAGE_DRAWERS, "design": None,
        "preview": preview,
        "summary": storage_drawers_summary(space, profile),
        "signature": structural_signature(space),
        "orientations": {},
        "printer_profile": profile,
    }
    # Orientations feed the hosted save/print currentness check, which passes
    # no output folder, so every existing caller keeps getting them exactly as
    # before. Only an explicit preview request (no output) skips the plan: it
    # needs the meshes, not the manifest.
    output = payload.get("output")
    if output or not include_preview:
        plan = structural_manifest_plan(space, Path(output or DEFAULT_OUTPUT), profile)
        reply["orientations"] = {one["key"]: one["orientation"] for one in plan["components"]}
    if not HOSTED and payload.get("output"):
        folder, _saved, _space_id = _local_cabinet_folder(payload)
        reply["status"] = structural_status(
            space, structural_output_manifest(folder, STRUCTURAL_OUTPUT_KEY), folder, profile,
        )
        reply["manifest_plan"] = structural_manifest_plan(space, folder, profile)
    return reply


def _materialize_local_cabinet(payload: dict[str, Any]) -> dict[str, Any]:
    """Write every cabinet file and commit the manifest as one rollback-safe
    transaction. The manifest is committed under the metadata lock and Space-ID
    check while the pre-attempt backups still exist."""
    folder, space, space_id = _local_cabinet_folder(payload)
    profile = _printer_profile_for(payload)

    def commit(manifest: dict[str, Any]) -> None:
        commit_structural_output(
            folder, STRUCTURAL_OUTPUT_KEY, manifest, expected_space_id=space_id,
        )

    with GEOMETRY_LOCK:
        result = materialize_storage_drawers(
            space, folder, profile, structural_output_manifest(folder, STRUCTURAL_OUTPUT_KEY),
            commit=commit,
        )
    return {
        "output": str(folder), "files": [str(one) for one in result["files"]],
        "manifest": result["manifest"], "warnings": result["warnings"],
        "status": {"status": "saved"},
    }


def _hosted_cabinet_export(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate every candidate file in a temporary export; the browser folder
    owns the final write and the manifest commit."""
    space = normalise_storage_drawers_definition(payload["space"])
    output = _generation_output(payload)
    try:
        with GEOMETRY_LOCK:
            result = materialize_storage_drawers(space, output, _printer_profile_for(payload), None)
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return _generation_reply(
        result={"components": [{"output": str(one)} for one in result["files"]]},
        output=output,
        extra={"manifest": result["manifest"], "warnings": result["warnings"]},
    )


def structural_design_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """A Space's structural output design and a plain size summary. Read-only:
    never touches an Inventory."""
    if _is_storage_drawers_request(payload):
        return _storage_drawers_structural_design(payload)
    kind, design = _structural_request(payload)
    if kind == STORAGE_BOX:
        box = design_from_dict(design)[0]
        summary = b4b_summary(box)
        # Fix 111 N3: drawers-style printer verdict for the warning at the
        # size input. Nonblocking: creation is never refused on fit.
        summary["fits_printer"], summary["first_fit_error"] = _storage_box_printer_fit(
            summary, _printer_profile_for(payload))
        return {"kind": kind, "design": design, "summary": summary}
    summary = base_trim_summary(base_trim_from_design(design))
    reply: dict[str, Any] = {"kind": kind, "design": design, "summary": summary}
    profile = _printer_profile_for(payload)
    plan = base_trim_plan(payload["space"], profile)
    reply["plan"] = base_trim_public_plan(plan)
    reply["signature"] = plan["signature"]
    reply["printer_profile"] = profile
    if not HOSTED and payload.get("output") and payload.get("space_id"):
        folder, saved, space_id = _local_surface_folder(payload)
        reply["status"] = base_trim_status(
            saved, structural_output_manifest(folder, BASE_TRIM_OUTPUT_KEY), folder, profile,
            space_id=space_id,
        )
    return reply


def _materialize_local_base_trim(payload: dict[str, Any]) -> dict[str, Any]:
    """Save every Base Trim piece and commit its manifest under the Space-ID guard."""
    folder, space, space_id = _local_surface_folder(payload)
    profile = _printer_profile_for(payload)

    def commit(manifest: dict[str, Any]) -> None:
        commit_structural_output(folder, BASE_TRIM_OUTPUT_KEY, manifest, expected_space_id=space_id)

    with GEOMETRY_LOCK:
        result = materialize_base_trim(
            space, folder, profile, structural_output_manifest(folder, BASE_TRIM_OUTPUT_KEY),
            space_id=space_id, commit=commit,
        )
    return {
        "output": str(folder), "files": [str(one) for one in result["files"]],
        "manifest": result["manifest"], "plan": result["plan"], "warnings": result["warnings"],
        "status": {"status": "current"},
    }


def _hosted_base_trim_export(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate every Base Trim piece in a temporary export and return the manifest
    for those exact bytes; the browser folder owns the final write and commit."""
    output = _generation_output(payload)
    try:
        with GEOMETRY_LOCK:
            result = export_base_trim(
                payload["space"], output, _printer_profile_for(payload), payload.get("space_id"),
            )
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise
    return _generation_reply(
        result={"components": [{"output": str(one)} for one in result["files"]]},
        output=output,
        extra={"manifest": result["manifest"], "plan": result["plan"]},
    )


def structural_generate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Save a Space's Storage Box, Base Trim or cabinet files. Never logs an Inventory row."""
    if _is_storage_drawers_request(payload):
        return _hosted_cabinet_export(payload) if HOSTED else _materialize_local_cabinet(payload)
    if _is_base_trim_request(payload):
        return _hosted_base_trim_export(payload) if HOSTED else _materialize_local_base_trim(payload)
    _kind, design = _structural_request(payload)
    return generate_payload(
        {
            "design": design, "output": payload.get("output"), "keep_log": False,
            "auto_timestamp": bool(payload.get("auto_timestamp", False)),
        },
        suppress_local_inventory=True,
    )


def structural_print_combined_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Print Cabinet + Bins: the cabinet and every placed bin under one truthful
    preflight and one slicer handoff. (Fix 096 C7.)

    File-collection sequence is fixed:
      1. Cabinet structural files via _materialize_local_cabinet.
      2. Bin files via prepare_inventory_bins — only rows without current
         files are generated from their design source.
      3. The Space's required connectors via _space_connectors (every drawer,
         once each).
    Preflight is C6's selected_blocking_problems literally: any hard Space
    problem touching a contained bin raises before any file is written.
    Per-component Printed promotion (consistent with C1's single authority):
    bin rows become Printed only after the single launch_slicer handoff
    succeeds; the cabinet itself never logs an Inventory row and has no Printed
    status; any failure before or during handoff leaves rows Saved (never
    Printed) and returns a structured partial result.
    """
    if not _is_storage_drawers_request(payload):
        raise ValueError("Print Cabinet + Bins is only available for a Storage Drawers Space.")
    if HOSTED:
        raise ValueError("Hosted Wavefinity saves generated files to your selected folder instead.")
    slicer_path = detect_bambu_studio(payload.get("slicer_path"))
    if slicer_path is None or not slicer_path.is_file():
        raise ValueError(
            "Bambu Studio was not found. Please locate your Bambu Studio executable in settings or install Bambu Studio.")
    printer_profile = _printer_profile_for(payload)
    folder, space, space_id = _local_cabinet_folder(payload)
    inventory = load_inventory(folder)
    layout, bins = inventory["layout"], inventory["bins"]
    by_id = {str(one["id"]): one for one in bins}
    # Combined Cabinet + Bins prints the cabinet every time, plus only ordinary
    # bin rows that still need printing. Already-Printed rows are omitted, but
    # an empty bin selection is valid because the cabinet itself is still a
    # printable component of this combined action.
    counts: dict[str, int] = {}
    for drawer in layout.get("drawers") or []:
        for placement in drawer.get("placements") or []:
            one = by_id.get(str(placement.get("bin")))
            if (one is not None and one.get("kind") in ("bin", "b4b")
                    and one.get("status") != "printed"):
                counts[one["id"]] = counts.get(one["id"], 0) + 1
    # One truthful preflight — C6's predicate, literally.
    blocked = selected_blocking_problems(layout, bins, counts)
    if blocked:
        raise ValueError(blocking_problem_copy(bins, blocked))
    with GEOMETRY_LOCK:
        cabinet = _materialize_local_cabinet(payload)
        cabinet_files = [Path(one) for one in cabinet["files"]]
        prepared = prepare_inventory_bins(folder, list(counts), _generate_bin_from_design_spec)
        if prepared["failed"]:
            return {
                **cabinet, **prepared["inventory"], "partial": True, "partial_stage": "generate",
                "error": "Cabinet files were saved, but the bins could not be prepared: "
                         + _prepare_failure_text(prepared, slicer=True),
            }
        rows_files = prepared["files"]
        specs = prepared["specs"]
        inventory = prepared["inventory"]
        try:
            connector_counts, notes = _space_connectors(folder, inventory["layout"], inventory["bins"])
        except Exception as error:
            return {
                **cabinet, **prepared["inventory"], "partial": True, "partial_stage": "connectors",
                "error": f"Cabinet and bin files were saved, but the Space connectors could not be made: {error}. "
                         "Bambu Studio was not opened.",
            }
        launch_files = list(cabinet_files)
        for bin_id in counts:
            launch_files.extend(rows_files[bin_id])
        for name, count in connector_counts.items():
            launch_files.extend([folder / name] * count)
        result_counts = {
            "selection": counts,
            "bin_copies": sum(counts.values()),
            "connector_counts": connector_counts,
            "connector_copies": sum(connector_counts.values()),
            "notes": notes,
            "files": [str(one) for one in launch_files],
        }
        # Every file handed to the slicer must fit the active printer: cabinet
        # files were already generated profile-aware; bin and connector files
        # are checked here before launch.
        fit_issues: list[str] = []
        for path in dict.fromkeys(launch_files):
            fit_issues.extend(print_file_fit_issues(Path(path), printer_profile))
        if fit_issues:
            return {
                **cabinet, **prepared["inventory"], "partial": True, "partial_stage": "preflight",
                "error": "A file does not fit the active printer:\n" + "\n".join(fit_issues),
                **result_counts,
            }
        try:
            project_path = launch_slicer(slicer_path, launch_files)
        except Exception as error:
            # Files above are kept; rows stay Saved (never Printed).
            return {
                **cabinet, **prepared["inventory"], "partial": True, "partial_stage": "slicer",
                "error": f"Bambu Studio did not open: {error}. Any files made during this attempt were kept.",
                **result_counts,
            }
        try:
            # A row is one bin. Placement copy numbers are not print bookkeeping.
            saved = mark_printed_rows(folder, counts, specs)
        except Exception as error:
            return {
                **cabinet, **prepared["inventory"], "partial": True, "partial_stage": "status",
                "error": f"Bambu Studio opened, but the printed status could not be recorded: {error}. "
                         "Check the Inventory rows.",
                **result_counts,
            }
        return {**cabinet, **saved, **result_counts,
                "slicer": str(slicer_path), "project": str(project_path) if project_path else None}
def structural_print_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a Space's Storage Box, Base Trim or cabinet to the slicer. Never logs an Inventory row.

    Fix 056 D: a hidden ``joint_test_sample`` flag (Ctrl+Shift+click on Print
    Base Trim) swaps in the existing production joint-fit sample instead of
    the full Base Trim. It only ever applies to a Base Trim - an impossible
    request for a Storage Box is ignored rather than routed to unrelated
    geometry.
    """
    if _is_storage_drawers_request(payload):
        if HOSTED:
            raise ValueError("Hosted Wavefinity saves generated files to your selected folder instead.")
        slicer_path = detect_bambu_studio(payload.get("slicer_path"))
        if slicer_path is None or not slicer_path.is_file():
            raise ValueError(
                "A slicer was not found. Please locate your slicer executable in settings or install a slicer (Bambu Studio or OrcaSlicer)."
            )
        # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
        name = slicer_display_name(slicer_path) or "the slicer"
        saved = _materialize_local_cabinet(payload)
        try:
            project_path = launch_slicer(slicer_path, [Path(one) for one in saved["files"]])
        except Exception as error:
            return {
                **saved, "partial": True, "partial_stage": "slicer",
                "error": f"Files were saved, but {name} did not open: {error}",
            }
        return {**saved, "slicer": str(slicer_path), "project": str(project_path) if project_path else None}
    kind, design = _structural_request(payload)
    joint_test = kind == BASE_TRIM and bool(payload.get("joint_test_sample"))
    return print_payload({
        "design": design, "output": payload.get("output"),
        "target": "base_trim_joint_test" if joint_test else "bin",
        "keep_log": False, "structural_output": True,
        "slicer_path": payload.get("slicer_path"),
    })


def _local_storage_box_print_folder(payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    """Bind a local print attempt to the typed Space's durable identity."""
    root = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    prefs = load_preferences()
    info = describe_space_folder(root, prefs)
    expected = payload.get("space_id")
    space = info.get("space")
    if not expected or info.get("space_id") != expected or info.get("folder_mode") != "space" \
            or not isinstance(space, dict) or space.get("kind") not in ("portable", "box"):
        raise ValueError("This is not the Storage Box Space that was open before. Nothing was printed.")
    if prefs.get("active_space_id") and prefs["active_space_id"] != expected:
        raise ValueError("You switched Spaces during this print attempt. Nothing was printed.")
    return root, space, expected


def _local_surface_folder(payload: dict[str, Any]) -> tuple[Path, dict[str, Any], str]:
    """The real Surface folder, its authoritative typed Space, and its identity."""
    root = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    prefs = load_preferences()
    info = describe_space_folder(root, prefs)
    expected = payload.get("space_id")
    space = info.get("space")
    if not expected or info.get("space_id") != expected or info.get("folder_mode") != "space" \
            or not isinstance(space, dict) or space.get("kind") != "surface":
        raise ValueError("This is not the Surface Space that was open before. Nothing was changed.")
    if prefs.get("active_space_id") and prefs["active_space_id"] != expected:
        raise ValueError("You switched Spaces during this attempt. Nothing was changed.")
    return root, space, expected


def _storage_box_structural_files(root: Path, space: dict[str, Any], _space_id: str) -> list[Path]:
    case = structural_generate_payload({"space": space, "output": str(root)})
    return _extract_generated_files(case)


def _surface_structural_files(root: Path, space: dict[str, Any], space_id: str) -> list[Path]:
    saved = _materialize_local_base_trim({"space": space, "output": str(root), "space_id": space_id})
    return [Path(one) for one in saved["files"]]


def _combined_space_print(payload: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """One authoritative structural + placed-bin + connector handoff.

    Shared by the Storage Box and Surface combined prints. ``cfg`` carries only
    what differs: the Space binder, the accepted Space kinds, the arrangement
    check and the structural file maker. Every preflight step runs before the
    single slicer launch; no row becomes Printed until that launch succeeds.
    """
    if HOSTED:
        raise ValueError("Hosted Wavefinity saves generated files to your selected folder instead.")
    slicer = detect_bambu_studio(payload.get("slicer_path"))
    if slicer is None or not slicer.is_file():
        raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name_cap = slicer_display_name(slicer) or "The slicer"
    profile = _printer_profile_for(payload)
    label = cfg["label"]
    bind = cfg["bind"]
    root, space, space_id = bind(payload)
    inventory = load_inventory(root)
    layout, bins = inventory["layout"], inventory["bins"]
    if not isinstance(layout, dict) or not isinstance(layout.get("space"), dict) \
            or layout["space"].get("kind") not in cfg["kinds"]:
        raise ValueError(f"The {label} arrangement is unavailable. Reopen its Space and try again.")
    by_id = {one["id"]: one for one in bins}
    source_specs = design_specs(layout)
    issues: list[str] = []
    mismatch = cfg["arrangement_issue"](layout["space"], space)
    if mismatch:
        issues.append(mismatch)
    selected: list[str] = []
    for drawer in layout.get("drawers") or []:
        report = drawer_report(drawer, bins, layout=layout)
        issues.extend(blocking_problem_messages(report))
        for placement in drawer.get("placements") or []:
            row_id = placement.get("bin")
            one = by_id.get(row_id)
            if one is None:
                continue  # report above names every missing placement
            if one.get("kind") in ("spacer", "manual") or one.get("status") == "printed":
                continue
            if one.get("kind") not in ("bin", "b4b"):
                issues.append(f"{one.get('name') or row_id}: this row cannot be printed")
                continue
            if row_id not in selected:
                selected.append(row_id)
    # Inspect every selection before making any new file; one bad row must not
    # conceal other already-knowable identity or file failures.
    eligible: list[str] = []
    for row_id in selected:
        one = by_id[row_id]
        source = source_specs.get(row_id)
        try:
            files = inventory_row_files(root, one) if str(one.get("file") or "").strip() else []
        except ValueError as error:
            files = []
            if not isinstance(source, dict):
                issues.append(f"{one.get('name') or row_id}: {error}")
        if not files and not isinstance(source, dict):
            issues.append(f"{one.get('name') or row_id}: no current file or editable design is available")
        elif not files:
            try:
                design_from_dict(source)
            except Exception as error:
                issues.append(f"{one.get('name') or row_id}: its saved design is invalid ({error})")
                continue
            eligible.append(row_id)
        else:
            eligible.append(row_id)
    prepared_files: dict[str, list[Path]] = {}
    prepared_specs: dict[str, dict[str, Any]] = {}
    errors: list[str] = list(dict.fromkeys(issues))

    def context_problem() -> str | None:
        try:
            bind(payload)
            return None
        except Exception as error:
            return str(error)

    stale_context = False
    for row_id in eligible:
        changed = context_problem()
        if changed:
            errors.append(changed)
            stale_context = True
            break
        try:
            prepared = prepare_inventory_bins(root, [row_id], _generate_bin_from_design_spec)
            if prepared["failed"]:
                failed = prepared["failed"]
                errors.append(f"{failed['name']}: {failed['error']}")
            else:
                prepared_files.update(prepared["files"])
                prepared_specs.update(prepared["specs"])
        except Exception as error:
            errors.append(f"{by_id[row_id].get('name') or row_id}: {error}")
        changed = context_problem()
        if changed:
            errors.append(changed)
            stale_context = True
            break

    structural_files: list[Path] = []
    if not stale_context:
        try:
            structural_files = cfg["structural_files"](root, space, space_id)
            if not structural_files:
                errors.append(f"{label}: no structural files were made")
        except Exception as error:
            errors.append(f"{label}: {error}")
        changed = context_problem()
        if changed:
            errors.append(changed)
            stale_context = True

    connector_files: list[Path] = []
    current = None
    if not stale_context:
        try:
            current = load_inventory(root)
        except Exception as error:
            errors.append(f"Inventory could not be re-read after generation: {error}")
    for drawer in ((layout.get("drawers") or []) if current is not None else []):
        changed = context_problem()
        if changed:
            errors.append(changed)
            stale_context = True
            break
        try:
            expected_count = drawer_report(drawer, current["bins"], layout=layout)["connector_total"]
            made = generate_connectors(root, layout, current["bins"], drawer.get("id"))
            made_count = sum(int(one["count"]) for one in made["connectors"])
            if made_count != expected_count:
                errors.append("Space connectors: " + "; ".join(made["notes"] or [
                    f"only {made_count} of {expected_count} required connectors could be made"]))
            for one in made["connectors"]:
                connector_files.extend([root / one["file"]] * int(one["count"]))
        except Exception as error:
            errors.append(f"Space connectors: {error}")
        changed = context_problem()
        if changed:
            errors.append(changed)
            stale_context = True
            break

    files = [*structural_files]
    for row_id in selected:
        files.extend(prepared_files.get(row_id, []))  # exactly one bin occurrence per row
    files.extend(connector_files)
    for path in dict.fromkeys(files):
        errors.extend(print_file_fit_issues(path, profile))
        try:
            _validate_settings_safe(path)
        except Exception as error:
            errors.append(f"{path.name}: {error}")

    def partial(stage: str, problems: list[str]) -> dict[str, Any]:
        return {**load_inventory(root), "partial": True, "partial_stage": stage,
                "error": "\n".join(problems), "errors": problems,
                "selected_rows": selected, "files": [str(path) for path in files]}

    if errors:
        return partial("context" if stale_context else "preflight", errors)
    # A Space switch or a concurrent layout edit cannot turn this request into
    # an implicit print of a different arrangement.
    try:
        _root, _space, confirmed_id = bind(payload)
        latest = load_inventory(root)

        def print_layout(value):
            return {key: item for key, item in value.items() if key != "stale_files"}
        if confirmed_id != space_id or print_layout(latest["layout"]) != print_layout(layout):
            return partial("context", [f"The {label} arrangement changed while files were prepared. Try again."])
        latest_by_id = {one["id"]: one for one in latest["bins"]}
        for row_id in selected:
            row = latest_by_id.get(row_id)
            if row is None or row.get("status") == "printed" or inventory_row_files(root, row) != prepared_files.get(row_id):
                return partial("context", [f"{row_id} changed while files were prepared. Try again."])
    except Exception as error:
        return partial("context", [str(error)])
    try:
        launch_slicer(slicer, files)
    except Exception as error:
        return partial("slicer", [f"{name_cap} did not open: {error}. Files were kept."])
    try:
        marked = mark_printed_rows(root, selected, prepared_specs) if selected else load_inventory(root)
    except Exception as error:
        return partial("status", [f"{name_cap} opened, but Printed status could not be recorded: {error}. Check Inventory."])
    return {**marked, "selected_rows": selected, "files": [str(path) for path in files],
            "slicer": str(slicer)}


def storage_box_print_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Preflight one authoritative case + placed-bin + connector handoff."""
    return _combined_space_print(payload, {
        "label": "Storage Box", "kinds": ("portable", "box"),
        "bind": _local_storage_box_print_folder,
        "arrangement_issue": _storage_box_arrangement_issue,
        "structural_files": _storage_box_structural_files,
    })


def surface_print_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Preflight one authoritative Base Trim + placed-bin + connector handoff."""
    return _combined_space_print(payload, {
        "label": "Surface", "kinds": ("surface",),
        "bind": _local_surface_folder,
        "arrangement_issue": _surface_arrangement_issue,
        "structural_files": _surface_structural_files,
    })


def ai_capability_manifest() -> dict[str, Any]:
    """The AI's authoritative list of what it may put in a design.

    Everything is read from the catalog, the feature registry, rule constants and
    the canonical serializer - there is no second copy of any range or choice.
    """
    catalog = catalog_payload()
    base = _ai_example_base()
    features: list[dict[str, Any]] = []
    for part in catalog["parts"]:
        if (not part["palette_visible"] and part["kind"] != "pocket") or "box_modifier" in part["capabilities"]:
            continue
        entry: dict[str, Any] = {
            "kind": part["kind"], "title": part["title"],
            "description": part["description"],
            "capabilities": part["capabilities"],
        }
        if any(cap in AI_MEDIA_CAPABILITIES for cap in part["capabilities"]):
            entry["ai"] = "recommend_only"
            entry["reason"] = AI_MEDIA_REASON
        else:
            entry["ai"] = "configurable"
            starter = default_feature_payload({"design": base, "kind": part["kind"]})
            labels = {one["key"]: one["label"] for one in part["fields"]}
            entry["options"] = [
                {**option, **({"label": labels[option["key"]]} if option["key"] in labels else {}),
                 "legal_values": _ai_legal_values(option)}
                for option in part["options"]
                if not option.get("internal") and not option.get("legacy")
            ]
            entry["generic_fields"] = _ai_generic_fields(part, starter["feature"], catalog["item_rules"])
            if part["kind"] in {"pocket", "post", "slot", "steps"}:
                entry["generic_fields"]["reference_object"] = {
                    "type": "optional object or null",
                    "shape": {"width": "positive finite mm", "depth": "positive finite mm",
                              "height": "positive finite mm"},
                    "rules": "Preview/planning only; never changes holder geometry. Include only measured dimensions supplied or confirmed by the person; never invent them.",
                }
            # What Wavefinity fills in for a blank option in the example bin.
            entry["resolved_defaults"] = starter["resolved_options"]
            entry["example"] = starter["feature"]
        features.append(entry)
    examples = _ai_modifier_examples()
    modifier_examples = {
        "lid_stacking": {
            "stackable_bin": examples["stackable_bin"],
            "stackable_lid": examples["stackable_lid"],
            "lid_with_handle": examples["lid_with_handle"],
        },
        "inside_handles": examples["inside_handles"],
        "side_openings": examples["side_openings"],
        "edge_mount": examples["edge_mount"],
    }
    modifier_rules = {
        "lid_stacking": {
            "lid_rules": catalog["lid_rules"], "stack_rules": catalog["stack_rules"],
        },
        "inside_handles": {"lift_grabbers": catalog["lift_grabbers"]},
        "side_openings": {"side_openings": catalog["side_openings"]},
        "edge_mount": {"edge_mount": catalog["edge_mount"]},
    }
    modifiers = [
        {
            "kind": kind, "title": title, "description": description,
            "design_paths": list(paths), "ai": "configurable",
            "rules": modifier_rules[kind], "example": modifier_examples[kind],
        }
        for kind, title, description, paths in AI_MODIFIER_BLOCKS
    ]
    return {
        "features": features,
        "box_modifiers": modifiers,
        "bin_controls": {
            "units_are": "millimetres",
            "base_unit_mm": catalog["base_unit"],
            "max_box_size_mm": catalog["max_box_size"],
            "min_height_above_base_mm": catalog["min_height_above_base_mm"],
            "ordinary_bin_min_height_mm": catalog["drawer_rules"]["ordinary_bin_min_height_mm"],
            "wall_rules": catalog["wall_rules"],
            "base_rules": catalog["base_rules"],
            "scoop_rules": catalog["scoop_rules"],
            "layout_modes": catalog["modes"],
            "label_positions": list(LABEL_POSITIONS),
            "design_fields": {
                "box.x / box.y": "footprint, whole multiples of base_unit_mm",
                "box.z": "height in whole millimetres",
                "box.wall / box.base_thickness": "use the wall_rules / base_rules choices",
                "scoop": "true adds the front finger scoop (also available as an interior part)",
                "label / label_position": "rim ledge label text and its side",
                "part_name": "the bin name",
            },
        },
        "setting_interactions": catalog["setting_interactions"],
        "space_restrictions": {
            "drawer": "X/Y must fit the drawer opening in whole base units; height must not exceed the drawer height.",
            "box": "Height must not exceed the Space height; X/Y must fit the Space.",
            "portable": "Height must not exceed the Space height; X/Y must fit the Space.",
            "storage_drawers": "The Space values are the selected physical drawer's usable X/Y/height; the bin must fit inside it. Never design or return cabinet structure.",
            "surface": "Base thickness and base mode are Space-controlled; keep them exactly as given.",
            "pegboard": "Keep box.pegboard exactly as given (it is the Space's mounting); stay at or above the pegboard minimum height.",
            "pegboard_rules": catalog["pegboard_rules"],
        },
        "never_offer": [
            "Storage Box designs (box.b4b) or Base Trim designs (design_kind = base_trim)",
            "Photo Nest / traced contours (recommend only)",
            "hidden, internal or legacy-only part kinds other than Pocket",
        ],
    }


def ai_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Describe the object first.")
    description = description.strip()
    if len(description) > AI_MAX_DESCRIPTION:
        raise ValueError(f"Keep the description under {AI_MAX_DESCRIPTION} characters.")
    design = _ai_bin_design(payload.get("design"))
    space = _ai_space_context(payload.get("space"))
    request_id = "wf-ai-" + secrets.token_hex(6)
    fingerprint = _ai_fingerprint(design, space)
    box, layout, *_ = _design(design)
    bounds = layout_zone(box, layout.mode)
    # Fix 078: existing Inventory names are advisory context only for the
    # prompt, so they are added after the fingerprint - an unrelated
    # Inventory change must not make an otherwise-current prompt go stale.
    raw_names = payload.get("existing_names")
    existing_names = [str(name).strip()[:80] for name in raw_names
                       if isinstance(name, str) and name.strip()][:200] if isinstance(raw_names, list) else []
    context = {
        **space,
        "space_controlled_fields": _ai_controlled_fields(space),
        "current_baseline_layout_bounds_mm": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        "interior_margin_mm": [round(box.x - bounds.width, 3), round(box.y - bounds.depth, 3)],
        "base_unit_mm": BASE_UNIT,
        "existing_bin_names": existing_names,
    }
    prompt = _ai_prompt_text(
        description, request_id, fingerprint, context, ai_capability_manifest(), design)
    return {"request_id": request_id, "context_fingerprint": fingerprint, "prompt": prompt}


def ai_candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Prove an AI design in the real geometry path without changing anything.

    A semantic preflight against the manifest's public-control contract runs
    first, on the raw candidate, then canonical validation, structural/media
    rejection, and finally the exact preview owner. The preview rides its own
    client lane so it can never supersede, or be superseded by, the Designer's
    own preview requests.
    """
    violation = _ai_semantic_violation(payload.get("design"))
    if violation:
        raise ValueError(f"That design is not legal: {violation}.")
    canonical = _ai_bin_design(payload.get("design"))
    request: dict[str, Any] = {"design": canonical}
    if isinstance(payload.get("client_id"), str):
        request["client_id"] = payload["client_id"]
        request["generation"] = payload.get("generation")
    try:
        preview = preview_payload(request)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(_ai_safe_message(error)) from None
    if preview.get("superseded"):
        return {"superseded": True}
    problems = [
        text for text in (
            preview.get("message"), *preview.get("feature_errors", []), preview.get("draft_error"),
        ) if text
    ]
    if not preview.get("fits") and not problems:
        problems.append("The design does not fit.")
    if not problems:
        cap_problem = _ai_space_cap_violation(preview["design"], payload.get("space"))
        if cap_problem:
            problems.append(cap_problem)
    return {"design": preview["design"], "preview": preview, "problems": problems}


def _capped_bore_violation(
    box: BoxSpec, layout: Layout, features: list[Feature] | tuple[Feature, ...], cap_z: float,
) -> tuple[int, float] | None:
    """Evaluate Bore objects against the same physical body used by preview."""
    physical_box = _interior_work_box(box)
    base_z = base_height(physical_box, layout.mode)
    for index, feature in enumerate(features):
        if feature.kind != "bore" or feature.item is None:
            continue
        try:
            top = bore_reference_top(physical_box, feature, base_z)
        except (KeyError, TypeError, ValueError):
            continue
        if top > cap_z + 1e-6:
            return index, top
    return None


def _capped_bore_warning(
    box: BoxSpec, layout: Layout, features: list[Feature] | tuple[Feature, ...], raw_space: Any,
) -> dict[str, Any] | None:
    cap_z = _capped_space_height(raw_space)
    if cap_z is None:
        return None
    violation = _capped_bore_violation(box, layout, features, cap_z)
    if violation is None:
        return None
    _index, top = violation
    return {"top_mm": math.ceil(top * 1000) / 1000, "cap_mm": cap_z,
            "space_kind": _ai_space_context(raw_space)["kind"]}


def _ai_space_cap_violation(design: dict[str, Any], raw_space: Any) -> str | None:
    """Fix 078: in a capped Space (Drawer/Storage Box), no Bore-held object's
    highest point may exceed the Space's own ``z`` - a hard legality rule, not
    merely the ~30 mm grip preference. Uncapped Spaces (Surface/Pegboard) and
    no active Space never gain an artificial ceiling here.
    """
    space = _ai_space_context(raw_space)
    if not space.get("capped"):
        return None
    cap_z = _capped_space_height(raw_space)
    if cap_z is None:
        return None
    try:
        box, layout, *_ = _design(design)
    except (KeyError, TypeError, ValueError):
        return None
    violation = _capped_bore_violation(box, layout, layout.features, cap_z)
    if violation is not None:
        _index, object_top_z = violation
        return (
            f"a Bore-held object's top would reach {object_top_z:.3f} mm, above this "
            f"capped Space's {cap_z:.3f} mm ceiling; use a shorter bin and/or a shallower "
            "insertion depth so useful grip stays below the cap"
        )
    return None


POST_ROUTES = {
    "/api/preview": preview_payload,
    "/api/design/validate": validate_design_payload,
    "/api/ai/prompt": ai_prompt_payload,
    "/api/ai/candidate": ai_candidate_payload,
    "/api/ai/repair-prompt": ai_repair_prompt_payload,
    "/api/design/inventory-preview": inventory_preview_payload,
    "/api/pegboard/layouts": pegboard_layouts_payload,
    "/api/feature/default": default_feature_payload,
    "/api/feature/draft": draft_payload,
    "/api/feature/fit": feature_fit_payload,
    "/api/feature/apply": apply_feature_payload,
    "/api/feature/duplicate": duplicate_feature_payload,
    "/api/feature/reference": apply_reference_payload,
    "/api/feature/delete": delete_feature_payload,
    "/api/nest/trace": nest_trace_payload,
    "/api/nest/photo": photo_nest_payload,
    "/api/nest/retrace": nest_retrace_payload,
    "/api/layout/mode": mode_payload,
    "/api/layout/expand": expand_layout_payload,
    "/api/generate": generate_payload,
    "/api/connector": connector_save_payload,
    "/api/sampler": sampler_payload,
    "/api/print": print_payload,
    "/api/space/structural-design": structural_design_payload,
    "/api/space/structural-generate": structural_generate_payload,
    "/api/space/structural-print": structural_print_payload,
    "/api/space/structural-print-combined": structural_print_combined_payload,
    "/api/space/storage-box-print": storage_box_print_payload,
    "/api/space/surface-print": surface_print_payload,
    "/api/space/storage-drawers-summary": storage_drawers_summary_payload,
    "/api/space/storage-drawers-validate": storage_drawers_validate_payload,
    "/api/space/storage-drawers-reset": storage_drawers_reset_payload,
    "/api/space/storage-drawers-mutate-text": storage_drawers_mutate_text_payload,
    "/api/preferences": preferences_payload,
    "/api/space/show-folder": show_folder_payload,
    "/api/browse-output-folder": browse_output_folder_payload,
    "/api/space/browse-storage-parent": browse_space_parent_payload,
    "/api/browse-slicer-path": browse_slicer_path_payload,
    "/api/show-log": show_log_payload,
    "/api/space/create-text": create_space_text_payload,
    "/api/space/configure-text": configure_space_text_payload,
}
POST_ROUTES.update({
    **drawer_routes(
        GEOMETRY_LOCK, DEFAULT_OUTPUT, detect_bambu_studio, launch_slicer,
        hosted=HOSTED, generate_from_design=_generate_bin_from_design_spec,
        printer_profile_for=_printer_profile_for,
    ),
})
# (Fix 096 A5) Read-only operation status, plus the side-effecting route set.
# Reads keep ordinary timeout/retry behavior: the wrapper is a pure
# pass-through unless the client supplied an operation_id. structural_design
# is deliberately absent (its own docstring: "Read-only: never touches an
# Inventory"), as is the 15-second drawer summary route.
POST_ROUTES["/api/operation-status"] = operation_status_payload
for _side_effect_path in (
    "/api/generate",
    "/api/connector",
    "/api/print",
    "/api/space/structural-generate",
    "/api/space/structural-print",
    "/api/space/structural-print-combined",
    "/api/space/storage-box-print",
    "/api/space/surface-print",
    "/api/space/storage-drawers-reset",
    "/api/space/storage-drawers-mutate-text",
    "/api/drawer/save",
    "/api/drawer/design-source/save",
    "/api/drawer/design-source/duplicate",
    "/api/drawer/design-source/status",
    "/api/drawer/surface-fill/create",
    "/api/drawer/spacers/generate",
    "/api/drawer/connectors",
    "/api/drawer/print-complete",
    "/api/drawer/print-spacers",
    "/api/drawer/print-bins",
    "/api/drawer/save-bins",
):
    POST_ROUTES[_side_effect_path] = _idempotent_operation(POST_ROUTES[_side_effect_path])
if not HOSTED:
    POST_ROUTES.update({
        # Local save-folder selection and optional Space setup.
        **space_routes(DEFAULT_OUTPUT, load_preferences, save_preferences, mutate_preferences),
    })
    # (Fix 096 A5) storage-drawers-mutate is side-effecting; it is registered
    # inside space_routes() above, so it cannot join the A5-b wrap loop — the
    # key does not exist yet at that point, and hosted mode never registers
    # it at all.
    POST_ROUTES["/api/space/storage-drawers-mutate"] = _idempotent_operation(
        POST_ROUTES["/api/space/storage-drawers-mutate"])


class WavefinityHandler(BaseHTTPRequestHandler):
    server_version = "Wavefinity/1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[Wavefinity] {self.address_string()} - {format % args}")

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(_json_value(payload), separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, error: Exception, status: HTTPStatus) -> None:
        self._send_json({"error": str(error), "type": type(error).__name__}, status)

    def _send_static_file(self, root: Path, relative: str) -> None:
        resolved_root = root.resolve()
        candidate = (resolved_root / relative).resolve()
        try:
            candidate.relative_to(resolved_root)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        body = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json(health_payload(self.client_address[0]))
            return
        if path == "/api/catalog":
            self._send_json(catalog_payload())
            return
        if path == "/api/browse-slicer-path":
            self._send_json(browse_slicer_path_payload({}))
            return
        if path.startswith("/api/export/"):
            pieces = path.split("/", 4)
            if len(pieces) != 5:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            token, encoded_name = pieces[3], pieces[4]
            name = unquote(encoded_name)
            if not name or Path(name).name != name:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            with EXPORT_LOCK:
                _clean_expired_exports()
                record = EXPORTS.get(token)
                file_path = record["files"].pop(name, None) if record else None
                if record and not record["files"]:
                    EXPORTS.pop(token, None)
            if file_path is None or not file_path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                body = file_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", mimetypes.guess_type(name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name)}")
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
            finally:
                if record and not record["files"]:
                    _remove_export(record)
            return
        if path in {"/Brochure.md", "/brochure.md"}:
            brochure_file = APP_DIR / "Brochure.md"
            if brochure_file.is_file():
                body = brochure_file.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(body)
                return
        # Space-card artwork lives in the repository's canonical images/
        # folder, not under web/. Serve it from its own root rather than
        # duplicating the files or exposing APP_DIR itself.
        if path.startswith("/images/"):
            self._send_static_file(
                IMAGE_ROOT,
                unquote(path.removeprefix("/images/")),
            )
            return
        relative = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
        self._send_static_file(WEB_ROOT, relative)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        route = POST_ROUTES.get(path)
        if route is None:
            self._send_error(ValueError("unknown API route"), HTTPStatus.NOT_FOUND)
            return
        try:
            origin = self.headers.get("Origin")
            host = self.headers.get("Host", "")
            if origin and origin not in {f"http://{host}", f"https://{host}"}:
                self._send_error(
                    PermissionError("cross-origin API requests are not allowed"),
                    HTTPStatus.FORBIDDEN,
                )
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0]
            if content_type != "application/json":
                raise ValueError("API requests must use application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if length > 25_000_000:
                raise ValueError("request is too large")
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            self._send_json(route(payload))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self._send_error(error, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            self._send_error(error, HTTPStatus.INTERNAL_SERVER_ERROR)


def make_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return WavefinityServer((host, port), WavefinityHandler)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        # (Fix 096 A6) Source freshness/build identity without starting the server.
        from wavefinity_freshness import check_report
        return check_report()
    try:
        loopback = args.host.lower() == "localhost" or ipaddress.ip_address(args.host).is_loopback
    except ValueError:
        loopback = False
    if not loopback and not HOSTED:
        raise RuntimeError(
            "refusing a public network bind outside hosted deployment mode"
        )
    requested_url = f"http://{args.host}:{args.port}/"
    try:
        server = make_server(args.host, args.port)
    except OSError:
        if _replace_stale_process(requested_url, args.host, args.port):
            try:
                server = make_server(args.host, args.port)
            except OSError as error:
                raise RuntimeError(
                    f"port {args.port} freed up but would not rebind"
                ) from error
        else:
            try:
                with urlopen(requested_url + "api/health", timeout=1.5) as response:
                    existing = json.loads(response.read())
                if not existing.get("ok"):
                    raise RuntimeError("another service is using the Wavefinity port")
            except Exception as error:
                raise RuntimeError(
                    f"port {args.port} is already in use and is not Wavefinity"
                ) from error
            print(
                f"Wavefinity is already running: {requested_url}\n"
                "(could not confirm which process to replace - close that "
                "window by hand and relaunch to pick up code changes)"
            )
            if not args.no_browser:
                webbrowser.open(requested_url)
            return 0
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    host, port = server.server_address[:2]
    url = f"http://{host}:{port}/"
    print(f"Wavefinity browser app: {url}")
    print("Close this window or press Ctrl+C to stop it.")
    if not args.no_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            if PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
                PID_FILE.unlink()
        except (FileNotFoundError, ValueError, OSError):
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
