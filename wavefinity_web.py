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
    divider_division_texts,
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
    _space_connectors, _prepare_failure_text,
)
from organizer_inventory import (
    append_bin, configure_space_text, design_specs, load_inventory, mark_printed_rows,
    resolve_inventory_path,
)
from organizer_engine.product_rules import (
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    STORAGE_DRAWERS_MIN_USABLE_HEIGHT_MM,
    surface_maximums,
)
from organizer_outputs.space import (
    BASE_TRIM, STORAGE_BOX, STORAGE_DRAWERS, structural_design, structural_kind,
)
from organizer_inventory import storage_drawers_mutate_text
from organizer_outputs.printer_profile import (
    DEFAULT_PRINTER_BUILD_MM,
    component_fit,
    normalise_printer_profile,
    print_file_fit_issues,
    printer_profile_from_preferences,
    current_export_profile, export_printer_profile, fit_status,
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
    normalise_storage_drawers_definition,
    reset_storage_drawers_definition,
    storage_drawers_definition_problem,
)
from organizer_storage.drawer_geometry import resolve_storage_drawers_plan, storage_drawers_summary
from organizer_base_trim.outputs import (
    BASE_TRIM_OUTPUT_KEY,
    base_trim_plan,
    base_trim_status,
    export_base_trim,
    materialize_base_trim,
    public_plan as base_trim_public_plan,
)
from organizer_storage.drawer_outputs import (
    STRUCTURAL_OUTPUT_KEY,
    materialize_storage_drawers,
    structural_manifest_plan,
    structural_signature,
    structural_status,
    sweep_cabinet_debris,
)
from organizer_engine.product_rules import STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
from organizer_spaces import (
    commit_structural_output,
    default_space_parent,
    describe as describe_space_folder,
    effective_space_root,
    other_spaces as other_spaces_list,
    inventory_enabled,
    space_routes,
    storage_startup_state,
    structural_output_manifest,
)
from organizer_app_impl._design_io import MODULE_MARKER_KEY, MODULE_MARKER_MM
from organizer_app_impl._filenames import BIN_SERIAL
from organizer_app_impl._generation import next_bin_serial
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
    default_feature,
    design_from_dict,
    design_source_payload,
    design_to_dict,
    generate_organizer_files,
    generate_organizer_files_transactional,
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
from organizer_features.stack import (
    STACK_MIN_WALL,
    make_lid_parts,
    stack_base_minimum,
    stack_effective_box,
    stack_enabled,
    stack_summary,
    validate_stack_design,
)
from organizer_outputs.slicer import slicer_display_name
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
from organizer_engine import export_object_groups_3mf
from organizer_features.pegboard import (
    make_pegboard_hooks,
    pegboard_catalog,
    pegboard_hook_count,
    pegboard_layout_for_bin,
    pegboard_standard,
)

from dataclasses import replace
import ipaddress
import json
import copy
import math
import mimetypes
import os
from pathlib import Path
import re
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
from urllib.request import Request, urlopen
from photo_nest import photo_outline_from_data
from plate_layout import space_out_for_plate, combine_for_plate
from bambu_handoff import (
    _validate_settings_safe,
    is_bambu_studio_executable,
    validate_bambu_handoff,
)

from organizer_geometry import build_scope, checkpoint, stage
from wavefinity_web_impl._runtime import (
    WEB_ROOT,
    IMAGE_ROOT,
    DEFAULT_OUTPUT,
    SERVER_VERSION,
    API_COMPAT_VERSION,
    SERVER_INSTANCE,
    SERVER_BUILD as FALLBACK_BUILD,
    SOURCE_FILES,
    source_fingerprint,
    SOURCE_ROOT,
    SOURCE_FINGERPRINT,
    GEOMETRY_LOCK,
    _PREVIEW_REQUEST_LOCK,
    _PREVIEW_REQUESTS,
    _SupersededGeometry,
    _register_preview_request,
    _token_superseded,
    _preview_geometry_lock,
    _real_preview_active,
    _real_preview_busy,
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
    operation_progress,
    OUTPUT_LOCK,
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
    duplicate_feature_payload,
    delete_feature_payload,
    mode_payload,
    expand_layout_payload,
    inventory_preview_payload,
    pegboard_layouts_payload,
    create_space_text_payload,
    configure_space_text_payload,
    copy_space_text_payload,
    copy_space_name_payload,
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
    _ai_baseline_design,
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


# The launcher (wavefinity_freshness.py) writes this stamp inside the runtime
# checkout's .git directory before it starts the server, so it never shows up
# as a working-tree change and is not rewritten while the server runs.
BUILD_STAMP_FILE = APP_DIR / ".git" / "wavefinity-build-stamp.json"
_HEX40_RE = re.compile(r"[0-9a-f]{40}")


def load_build_identity(stamp_file: Path = BUILD_STAMP_FILE, root: Path = APP_DIR) -> dict[str, Any]:
    """The build this process was started from, as the launcher stamped it.

    A missing, unreadable or mismatched stamp yields "unknown" values - never
    a made-up version - so a server started any other way cannot pass for a
    verified launcher build.
    """
    identity: dict[str, Any] = {
        "build": FALLBACK_BUILD, "commit": "unknown", "branch": "unknown",
        "verified_at": "unknown", "runtime_path": "unknown",
        "launch_token": "unknown", "stamp": "missing",
    }
    try:
        data = json.loads(stamp_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return identity
    identity["stamp"] = "invalid"
    if not isinstance(data, dict):
        return identity
    commit = data.get("commit")
    path = data.get("runtime_path")
    token = data.get("token")
    fields = (data.get("branch"), data.get("verified_at"))
    if not (isinstance(commit, str) and _HEX40_RE.fullmatch(commit)
            and isinstance(path, str) and isinstance(token, str) and token
            and all(isinstance(one, str) and one for one in fields)):
        return identity
    # A stamp copied from another checkout does not describe this one.
    if os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.realpath(root)):
        return identity
    identity.update({
        "build": commit[:12], "commit": commit, "branch": fields[0],
        "verified_at": fields[1], "runtime_path": str(Path(root).resolve()),
        "launch_token": token, "stamp": "present",
    })
    return identity


BUILD_IDENTITY = load_build_identity()
SERVER_BUILD = BUILD_IDENTITY["build"]


def health_payload(client_address: str, *, hosted: bool = HOSTED) -> dict[str, Any]:
    result = {
        "ok": True, "version": SERVER_VERSION, "instance": SERVER_INSTANCE,
        "api_compat": API_COMPAT_VERSION, "build": SERVER_BUILD,
        "commit": BUILD_IDENTITY["commit"], "branch": BUILD_IDENTITY["branch"],
        "verified_at": BUILD_IDENTITY["verified_at"],
        "stamp": BUILD_IDENTITY["stamp"],
        "source_fingerprint": SOURCE_FINGERPRINT,
    }
    try:
        loopback = ipaddress.ip_address(client_address).is_loopback
    except ValueError:
        loopback = False
    if not hosted and loopback:
        result["source_root"] = SOURCE_ROOT
        result["runtime_path"] = BUILD_IDENTITY["runtime_path"]
        result["launch_token"] = BUILD_IDENTITY["launch_token"]
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
            return {key: value for key, value in prefs.items() if key != "ai_connection"}

        legacy = prefs.get("connector_settings")
        if not path.exists() and isinstance(legacy, dict):
            try:
                _write_connector_settings_path(path, legacy)
            except OSError:
                return {key: value for key, value in prefs.items() if key != "ai_connection"}

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
        return {key: value for key, value in prefs.items() if key != "ai_connection"}


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
    from wavefinity_web_impl._catalog import catalog_payload as canonical_catalog
    import sys
    slicer_exe = None if HOSTED else detect_bambu_studio()
    return canonical_catalog(environment={
        "platform": sys.platform, "version": SERVER_VERSION,
        "instance": SERVER_INSTANCE, "api_compat": API_COMPAT_VERSION,
        "build": SERVER_BUILD, "hosted": HOSTED, "output": str(DEFAULT_OUTPUT),
        "preferences": {} if HOSTED else served_preferences(),
        "slicer": {"available": slicer_exe is not None,
                   "path": str(slicer_exe) if slicer_exe else None,
                   "name": "Bambu Studio" if HOSTED else slicer_name(slicer_exe)},
    })


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


def launch_slicer(slicer_path: Path, files: list[Path], *, already_on_plate: bool = False,
                  output_dir: Path | None = None) -> Path | None:
    """Open ``files`` directly in the slicer.

    Fix 058: Wavefinity never manufactures a Bambu project for handoff.
    Bambu Studio gets every requested physical occurrence in one combined,
    profile-free Last Print Layout.3mf - no ``--export-3mf``, ``--arrange``,
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
    output_dir = Path(output_dir) if output_dir is not None else Path(files[0]).parent
    if not already_on_plate:
        # Every launch path comes through here, so parts are never handed over
        # stacked at their assembled spots. Copies are laid out side by side;
        # a single file is returned untouched. A layout that cannot fit raises
        # before anything is staged or opened.
        files, layout_issues = space_out_for_plate(list(files), _printer_profile_for({}))
        if layout_issues:
            raise ValueError("The parts do not fit the active printer:\n" + "\n".join(layout_issues))
    if is_bambu_studio_executable(slicer_path):
        for source in files:
            _validate_settings_safe(source)
        combined, layout_issues = combine_for_plate(
            files, _printer_profile_for({}), output_dir / "Last Print Layout.3mf")
        if layout_issues:
            raise ValueError("The parts do not fit the active printer:\n" + "\n".join(layout_issues))
        validate_bambu_handoff(combined, files)
        args = [str(slicer_path.resolve()), str(combined.resolve())]
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
    save_preferences(update)
    return {"preferences": served_preferences()}


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
        with _real_preview_active(), build_scope(lambda: _token_superseded(token)) as timings:
            result = _preview_payload(payload, token)
            checkpoint()   # a result a newer request already replaced is not sent
            # Where this build's time went, in ms per stage (self time): wait
            # (queued), outline_wave, shell, features, lid, booleans,
            # conversion, other, and the build's total. Cheap enough to keep.
            result["build_timings_ms"] = timings.report()
            return result
    except _SupersededGeometry:
        return {"superseded": True}


_WARM_LOCK = threading.Lock()
_WARM_DONE: set[str] = set()
_WARM_RUNNING = False


def _warm_build(payload: dict[str, Any]) -> None:
    """One warming build, only while no real preview is being asked for."""
    while _real_preview_busy():
        time.sleep(0.05)
    try:
        if payload.get("space") is not None:
            _storage_drawers_structural_design(payload)
        else:
            _preview_payload(payload, None)
    except Exception:
        pass  # a Space that cannot build is skipped, exactly as a click would fail


def _warm_space(folder: Path, prefs: dict[str, Any]) -> None:
    """Read-only: build the previews a click on this Space would build. Never
    opens, selects or remembers the Space and writes nothing."""
    info = describe_space_folder(folder, prefs)
    space = info.get("space")
    if info.get("folder_mode") != "space" or not isinstance(space, dict) or info.get("needs_setup"):
        return
    kind = structural_kind(space)
    if kind == STORAGE_DRAWERS:
        _warm_build({"space": space, "include_preview": True})
    elif kind is not None:
        try:
            design = structural_design(space, bed_x_mm=_printer_profile_for({})["x_mm"],
                                       bed_y_mm=_printer_profile_for({})["y_mm"])
        except Exception:
            design = None
        if design:
            _warm_build({"design": design, "client_id": "warm-structural", "generation": 0})
    for one in design_specs(load_inventory(folder).get("layout")).values():
        if isinstance(one, dict):
            _warm_build({"design": one})


def _warm_run(folders: list[Path]) -> None:
    global _WARM_RUNNING
    try:
        prefs = load_preferences()
        for folder in folders:
            try:
                _warm_space(folder, prefs)
            except Exception:
                pass
            with _WARM_LOCK:
                _WARM_DONE.add(str(folder))
    finally:
        with _WARM_LOCK:
            _WARM_RUNNING = False


def warm_spaces_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Start quiet background pre-building of the listed Spaces' previews."""
    global _WARM_RUNNING
    if HOSTED:
        return {"started": False}
    prefs = load_preferences()
    listed: dict[str, Path] = {}
    for one in other_spaces_list(prefs):
        if not one.get("invalid") and one.get("folder"):
            listed[os.path.normcase(str(one["folder"]))] = Path(one["folder"])
    for one in prefs.get("recent_folders") or []:
        if isinstance(one, dict) and one.get("folder"):
            listed.setdefault(os.path.normcase(str(one["folder"])), Path(one["folder"]))
    with _WARM_LOCK:
        if _WARM_RUNNING:
            return {"started": False}
        todo = [p for k, p in listed.items() if str(p) not in _WARM_DONE and p.is_dir()]
        if not todo:
            return {"started": False}
        _WARM_RUNNING = True
    threading.Thread(target=_warm_run, args=(todo,), daemon=True, name="space-preview-warm").start()
    return {"started": True}


def _preview_payload(payload: dict[str, Any], token) -> dict[str, Any]:
    if _is_base_trim_design(payload.get("design")):
        return _base_trim_preview_payload(payload, token)
    if isinstance(payload.get("design"), dict):
        box_raw = payload["design"].get("box", {})
        b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
        if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
            return _b4b_preview_payload(payload, token)
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    from organizer_inserts._walljoin import build_grid
    with build_grid(layout.design_grid):
        return _preview_bin_payload(
            payload, token, box, layout, label, part_name, label_location, scoop,
        )


def _preview_bin_payload(payload, token, box, layout, label, part_name, label_location, scoop):
    """Preview body, inserts and lid under the existing design-grid context."""
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
            with stage("lid"):
                lid, lid_texts = make_lid_parts(
                    stack_request, lid_label_regions(stack_request, layout),
                )
            scene["geometry"].extend(_mesh_preview_geometry(lid, "lid"))
            for _text, mesh, _raised in lid_texts:
                scene["geometry"].extend(_mesh_preview_geometry(mesh, "lid_label"))
    bounds = layout_zone(box, layout.mode)
    with stage("conversion"):
        geometry = [
            {"points": points, "kind": kind, "normal": normal,
             "layer": layer, "owner": owner,
             "pick": scene.get("pick_faces", {}).get(index)}
            for index, (points, kind, normal, layer, owner) in enumerate(scene["geometry"])
        ]
    with stage("outline_wave"):
        cavity = wavy_cavity_polygon(box)
    resolved = layout
    canonical = design_to_dict(stack_request, resolved, label, part_name, label_location, scoop)
    planning_record = inventory_bin_record(stack_request, resolved, None, label, part_name, scoop)
    planning = object_height_plan(canonical, resolved.object_height_mm)
    planning["effective_mm"] = max(stack_part_height(planning_record), planning["object_top_mm"] or 0.0)
    storage_box_height_warning = None
    raw_space = payload.get("space")
    if isinstance(raw_space, dict) and raw_space.get("kind") in ("portable", "box"):
        cap = float(raw_space["z"])
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


def _block_storage_box_overheight(raw_space, box, layout, label, part_name, scoop) -> None:
    """Fix 1069: hard legality gate for direct STL generation in a Storage Box Space.

    Raises ValueError when the bin/closed stack's actual physical top exceeds the
    Space's interior Z (space.z) - the same threshold the preview warning uses.
    The measured top is the physical envelope of the ONE generated design:
    closed_height_mm from stack_summary for stack/lid designs (the documented
    detached physical envelope: interlocking foot depth plus the tallest thing
    above the lid), or stack_part_height() ("detached physical height,
    including the interlocking foot depth") for a single part - the system's
    physical model of what the generator builds, not raw box.z. The two-bin
    sum (closed_height_mm + pitch_mm) is a planning height, not the one
    design's envelope: it stays only in the preview "would two of these
    stack?" copy (Change 5), never in this legality gate.
    Lid headroom is lid-fit geometry, never payload. Non-Storage-Box Spaces and
    standalone designs (no Space) are unaffected. Fail-closed: if the physical
    envelope cannot be computed for a Storage Box payload, generation is blocked
    rather than silently allowed.
    """
    if not isinstance(raw_space, dict) or raw_space.get("kind") not in ("portable", "box"):
        return
    cap_z = float(raw_space["z"])
    try:
        stack_block = stack_summary(box) if (stack_enabled(box) or lid_enabled(box)) else None
        if stack_block is not None and stack_block["enabled"]:
            # G2M-0322: legality measures the ONE generated design's physical
            # envelope - closed_height_mm alone. Never add pitch_mm here: the
            # two-bin sum is a planning height, not one design's envelope.
            top = stack_block["closed_height_mm"]
            kind = "stack"
        else:
            record = inventory_bin_record(box, layout, None, label, part_name, scoop)
            if stack_block is not None and lid_enabled(box):
                top = stack_block["closed_height_mm"]
            else:
                top = stack_part_height(record)
            kind = "bin"
        top = float(top)
        if not math.isfinite(top):
            raise ValueError("Physical height is not finite")
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        # Fix 1069 (G2M-0320): fail closed - an unverifiable envelope in a
        # Storage Box Space blocks generation instead of slipping through.
        raise ValueError(
            f"Cannot verify this design fits in the {cap_z:.3f} mm Storage Box interior; "
            "generation blocked."
        ) from exc
    if top is not None and top > cap_z + 1e-6:
        raise ValueError(
            f"This {kind} is {top:.3f} mm tall, but this Storage Box is {cap_z:.3f} mm inside. "
            "Shorten it so it fits under the lid."
        )


def _bin_serial_for(payload: dict[str, Any], output: Path, will_log: bool) -> str:
    """The unique id every file of this bin ends with, else "" (plain names).

    A bin bound to an Inventory row in this folder uses that row's id. A bin
    about to be logged as a new row reserves the id the row will take. Nothing
    else (hosted, unlogged, unbound) carries a serial.
    """
    if HOSTED:
        return ""
    row_id = str(payload.get("design_row_id") or "")
    try:
        if row_id:
            row = next((one for one in load_inventory(output)["bins"] if one.get("id") == row_id), None)
            return row_id if row is not None and row.get("kind") == "bin" and BIN_SERIAL.fullmatch(row_id) else ""
        return next_bin_serial(output) if will_log else ""
    except (OSError, ValueError):
        return ""


def generate_payload(
    payload: dict[str, Any],
    *,
    suppress_local_inventory: bool = False,
) -> dict[str, Any]:
    # Timed like a preview (build_timings_ms per stage: wait, checks, shell,
    # features, booleans, extras, lid, validation, export, promote, other,
    # total), but never a preview build: preview=False keeps the written files
    # exactly what they were. Each stage it enters is reported to the running
    # operation, with an honest estimate, for the Export status line.
    progress = _GenerateProgress(payload.get("design"))
    with export_printer_profile(_printer_profile_for(payload)), build_scope(preview=False, listener=progress.stage) as timings:
        reply = _generate_payload(payload, suppress_local_inventory=suppress_local_inventory,
                                  progress=progress)
    report = timings.report()
    progress.finished(report)
    reply["build_timings_ms"] = report
    return reply


# Stages of an ordinary bin's Export that build geometry and so hold
# GEOMETRY_LOCK. Writing/validating the already-built meshes ("export") and
# installing the staged set ("promote") run with it released, so editor
# actions that need it wait only for the build itself (OUTPUT_LOCK still keeps
# two Exports from interleaving their file work).
_GEOMETRY_STAGES = frozenset({"checks", "shell", "features", "extras", "lid"})
_FILE_STAGES = frozenset({"export", "promote"})

# Export time model for an ordinary bin, from the README profile (2026-11-11):
# seconds = BASE + PER_MM2 * footprint; a lid multiplies it. _GENERATE_SPEED
# learns this computer's ratio to the model from each finished Export, so the
# estimate follows the machine it runs on.
_GENERATE_BASE_S = 3.0
_GENERATE_PER_MM2_S = 0.00013
_GENERATE_LID_FACTOR = 3.0
_GENERATE_SPEED = [1.0]
# Share of the total already spent when each stage starts (plain bin / lid).
_GENERATE_STAGE_SHARE = {"features": 0.25, "export": 0.45, "extras": 0.98, "promote": 0.99}
_GENERATE_LID_STAGE_SHARE = {"features": 0.09, "export": 0.16, "extras": 0.27, "lid": 0.27, "promote": 0.99}


class _GenerateProgress:
    """Stage, elapsed time and a plain estimate for one Export, reported to
    its running operation (read back through /api/operation-status). Also
    takes GEOMETRY_LOCK for the build stages only."""

    _WORDS = {
        "wait": "Waiting for the export before it", "checks": "Checking the design", "shell": "Building the bin walls",
        "features": "Adding the inside parts", "extras": "Adding the extra parts",
        "lid": "Building the lid", "export": "Checking and writing the file",
        "promote": "Saving the files",
    }

    def __init__(self, design: Any) -> None:
        self.started = time.monotonic()
        self.lid = False
        self.model_s: float | None = None
        try:
            box = (design or {}).get("box") or {}
            area = float(box["x"]) * float(box["y"])
            self.lid = bool((box.get("lid") or {}).get("enabled"))
            self.model_s = (_GENERATE_BASE_S + _GENERATE_PER_MM2_S * area) * (
                _GENERATE_LID_FACTOR if self.lid else 1.0)
        except (KeyError, TypeError, ValueError, AttributeError):
            self.model_s = None
        self.estimate_s = self.model_s * _GENERATE_SPEED[0] if self.model_s else None
        # None: the caller owns GEOMETRY_LOCK already; leave it alone.
        self.lock_held: bool | None = False
        self._seen: set[str] = set()
        self._publish(None)

    def _publish(self, name: str | None) -> None:
        fields: dict[str, Any] = {}
        if name is not None:
            fields["stage"] = name
            fields["stage_text"] = self._WORDS.get(name, "Working")
        if self.estimate_s:
            fields["estimate_s"] = [round(self.estimate_s * 0.8, 1), round(self.estimate_s * 1.25, 1)]
        operation_progress(**fields)

    def stage(self, name: str) -> None:
        elapsed = time.monotonic() - self.started
        share = (_GENERATE_LID_STAGE_SHARE if self.lid else _GENERATE_STAGE_SHARE).get(name)
        if self.estimate_s and share and name not in self._seen and elapsed > 0.5:
            # A stage boundary with a known share of the whole: move the
            # estimate halfway toward what this pace implies.
            self.estimate_s = 0.5 * self.estimate_s + 0.5 * (elapsed / share)
        self._seen.add(name)
        self._publish(name)
        if self.lock_held is None:
            return
        if name in _GEOMETRY_STAGES and not self.lock_held:
            with stage("wait"):
                GEOMETRY_LOCK.acquire()
            self.lock_held = True
        elif name in _FILE_STAGES and self.lock_held:
            GEOMETRY_LOCK.release()
            self.lock_held = False

    def release(self) -> None:
        if self.lock_held:
            GEOMETRY_LOCK.release()
            self.lock_held = False

    def finished(self, report: dict[str, float]) -> None:
        total = report.get("total")
        if self.model_s and total and total > 1000.0:
            ratio = (total / 1000.0) / self.model_s
            _GENERATE_SPEED[0] = 0.5 * _GENERATE_SPEED[0] + 0.5 * max(0.1, min(10.0, ratio))


def _generate_payload(
    payload: dict[str, Any],
    *,
    suppress_local_inventory: bool = False,
    progress: _GenerateProgress | None = None,
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
    # Fix 1069: in a Storage Box Space, direct Save/Generate/Print STL is
    # hard-blocked when the bin/closed stack's physical top exceeds the
    # interior Z. Standalone designs (no Space) are unaffected.
    _block_storage_box_overheight(payload.get("space"), box, layout, label, part_name, scoop)
    output = _generation_output(payload)
    auto_timestamp = bool(payload.get("auto_timestamp", False))
    requested_inventory = bool(payload.get("keep_log", False))
    if HOSTED:
        keep_log = requested_inventory
    elif suppress_local_inventory:
        keep_log = False
    else:
        keep_log = requested_inventory and inventory_enabled(output, load_preferences())
    # One Export's file work runs whole under OUTPUT_LOCK; GEOMETRY_LOCK is
    # held for the build stages only (see _GenerateProgress.stage). A caller
    # that already holds GEOMETRY_LOCK keeps it throughout, as before.
    narrow = progress is not None and not GEOMETRY_LOCK._is_owned()
    if progress is not None and not narrow:
        progress.lock_held = None
    with stage("wait"):
        if narrow:
            OUTPUT_LOCK.acquire()
            GEOMETRY_LOCK.acquire()
            progress.lock_held = True
        else:
            GEOMETRY_LOCK.acquire()
    try:
        serial = "" if box.b4b.enabled else _bin_serial_for(
            payload, output,
            will_log=requested_inventory and not HOSTED and (
                keep_log or inventory_enabled(output, load_preferences())),
        )
        # Fix 096 A1: the whole ordinary-bin file set installs as one unit -
        # staged, validated, then promoted - and inventory logging runs only
        # after the complete set promoted, so a row is never recorded for a
        # partial set.
        result = generate_organizer_files_transactional(
            box, layout, output, label, part_name, label_location, scoop,
            auto_timestamp=auto_timestamp,
            keep_log=keep_log and not HOSTED,
            pegboard_thickness_mm=(payload.get("space") or {}).get("pegboard_thickness_mm", 3.2),
            serial=serial,
        )
    finally:
        if narrow:
            progress.release()
            OUTPUT_LOCK.release()
        else:
            GEOMETRY_LOCK.release()
    reply = _generation_reply(
        result=result, output=output,
        extra={"bin_serial": serial} if serial and not HOSTED else None,
    )
    if HOSTED and requested_inventory:
        record = inventory_bin_record(
            box, layout, _extract_generated_files(result), label,
            part_name, scoop,
        )
        record["qty"] = 0
        reply["inventory_bin"] = record
        reply["inventory_design_spec"] = design_to_dict(box, layout, label, part_name, label_location, scoop)
    return reply


from wavefinity_web_impl._designs._layout import division_label_fit_payload


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
    plan = {
        "mode": "auto",
        "types": ["side"],
        "different_heights": False,
        "wall_mm": side_plan.get("wall_mm"),
        "requires_same_wall": True,
    }
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


def pegboard_hooks_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate N printable Pegboard hooks (Standard or SKÅDIS) as one 3MF."""
    if not payload.get("standard"):
        raise ValueError("Choose a Pegboard standard (standard or skadis).")
    standard = pegboard_standard(payload["standard"]).id
    count = pegboard_hook_count(payload.get("count"))
    output = _generation_output(payload)
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"Pegboard hooks - {standard} x{count}.3mf"
    with GEOMETRY_LOCK:
        hooks = make_pegboard_hooks(standard, count, thickness_mm=payload.get("thickness_mm", 3.2))
        export_object_groups_3mf([(name, [(name, mesh)]) for name, mesh in hooks], target)
    result = {
        "pegboard_hooks": {
            "output": str(target.resolve()),
            "count": count,
            "standard": standard,
        }
    }
    return _generation_reply(result=result, output=output)


def _generate_bin_from_design_spec(
    output_dir: Path, design_spec: dict[str, Any], row_id: str | None = None,
) -> list[Path]:
    """Fix 034 F2: generate a spec-only Inventory row's files on demand.

    Uses the same generator as a normal Generate action, with Inventory
    append/logging suppressed - ``print_inventory_bins`` owns persisting the
    resolved File cell itself, still at Qty 0.
    """
    box, layout, label, part_name, label_location, scoop = design_from_dict(design_spec)
    inventory_layout = load_inventory(output_dir).get("layout") or {}
    space = inventory_layout.get("space") or {}
    with GEOMETRY_LOCK, export_printer_profile(_printer_profile_for({})):
        # Background builds also read the current saved printer, independently
        # of the request thread. Hosted builds inherit their request's profile.
        # Fix 096 A1: on-demand batch generation installs as one unit too -
        # a row is recorded Saved only after its whole file set promoted.
        result = generate_organizer_files_transactional(
            box, layout, output_dir, label, part_name, label_location, scoop,
            auto_timestamp=False, keep_log=False,
            pegboard_thickness_mm=space.get("pegboard_thickness_mm", 3.2),
            serial=(row_id or "") if not box.b4b.enabled and BIN_SERIAL.fullmatch(row_id or "") else "",
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
    # Side connector bundle. A bin-only print never generates
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

    # The slicer is handed the parts side by side on the plate, each resting on
    # the bed, never stacked at their assembled spots. The saved design files
    # are untouched; only the handoff copies move. Parts that cannot all fit
    # the bed are reported here, before launch.
    try:
        handoff_files, layout_issues = space_out_for_plate(list(files), profile)
    except Exception as error:
        handoff_files, layout_issues = list(files), [f"the parts could not be laid out on the plate ({error})"]
    if layout_issues:
        return {
            "partial": True, "partial_stage": "preflight",
            "error": "The parts do not fit the active printer:\n" + "\n".join(layout_issues),
            "design_reused": design_reused,
            "design_files": [str(f) for f in design_files],
            "files": [str(f) for f in files],
        }

    try:
        project_path = launch_slicer(slicer_path, handoff_files, already_on_plate=True,
                                     output_dir=Path(files[0]).parent)
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
                row_id=gen_result.get("bin_serial") or None,
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
        if raw is None:
            return current_export_profile()
        profile = normalise_printer_profile(raw)
        profile["configured"] = payload.get("printer_profile_configured") is True
        return profile
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
        # Fix 1106 (Astra AD-005): the hosted status check compares the stored
        # manifest against the exact expected component set — key and filename
        # multiplicities — so a partial/duplicate manifest is never "saved".
        reply["expected_components"] = [{"key": one["key"], "filename": one["filename"]} for one in plan["components"]]
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
                         + _prepare_failure_text(prepared, slicer_name=slicer_display_name(slicer_path) or "the slicer"),
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
            if one.get("kind") in ("spacer", "manual", "standin") or one.get("status") == "printed":
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


def ai_capability_manifest(grid: str = "wavefinity") -> dict[str, Any]:
    from wavefinity_web_impl._ai import ai_capability_manifest as canonical
    return canonical(grid, catalog_payload=catalog_payload)


def _ai_connection(payload: dict[str, Any]) -> dict[str, str]:
    from urllib.parse import urlsplit
    if HOSTED:
        raise ValueError("Automatic AI is available only in the local app.")
    values = {key: str(payload.get(key, "")).strip() for key in ("name", "url", "model", "key")}
    parts = urlsplit(values["url"])
    if not values["name"] or not values["model"] or parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError("Enter a connection name, a valid endpoint address, and a model name.")
    values["url"] = values["url"].rstrip("/")
    return values


def ai_connection_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        return {"configured": False}
    action = payload.get("action")
    saved = load_preferences().get("ai_connection")
    if action == "status":
        if not isinstance(saved, dict):
            return {"configured": False}
        return {"configured": True, "name": saved.get("name", ""), "url": saved.get("url", ""),
                "model": saved.get("model", ""), "has_key": bool(saved.get("key"))}
    if action in ("save", "test"):
        connection = _ai_connection(payload)
        if payload.get("keep_key") and isinstance(saved, dict) and not connection["key"]:
            connection["key"] = saved.get("key", "")
        if action == "save":
            save_preferences({"ai_connection": connection})
            return {"configured": True}
        _ai_chat(connection, "Reply with OK.")
        return {"ok": True}
    raise ValueError("Choose an action for the AI connection.")


def _ai_chat(connection: dict[str, str], prompt: str) -> str:
    import urllib.error
    import urllib.request
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    request = urllib.request.Request(connection["url"] + "/chat/completions",
        data=json.dumps({"model": connection["model"], "messages": [{"role": "user", "content": prompt}]}).encode("utf-8"),
        headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + connection["key"]} if connection["key"] else {})})
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=120) as response:
            result = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
        answer = result["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError()
        return answer
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise ValueError("The AI service refused the key. Check your API key.") from None
        if error.code == 404:
            raise ValueError("The endpoint or model was not found. Check the address and model name.") from None
        raise ValueError("The AI service could not complete the request. Check the address and model name.") from None
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        raise ValueError("The AI endpoint did not answer properly. Check that it is running and the address and model are correct.") from None


def ai_ask_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        raise ValueError("Automatic AI is available only in the local app.")
    saved = load_preferences().get("ai_connection")
    if not isinstance(saved, dict):
        raise ValueError("Configure an AI connection first.")
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Generate a prompt first.")
    return {"answer": _ai_chat(_ai_connection(saved), prompt)}


def ai_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from wavefinity_web_impl._ai import ai_prompt_payload as canonical
    return canonical(payload, read_inventory=_grid_inventory, catalog_payload=catalog_payload)


def ai_candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from wavefinity_web_impl._ai import ai_candidate_payload as canonical
    return canonical(payload, read_inventory=_grid_inventory, preview_payload=preview_payload)


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


from wavefinity_web_impl._entry import OLD_MODULE_NOTICE


def _grid_inventory(payload: dict[str, Any], *, source: bool = False) -> tuple[dict, dict | None]:
    """Read authority from stored records, including browser-folder snapshots.

    A client-supplied Space object is never ownership or destination evidence.
    Reading here never migrates or rewrites a folder.
    """
    from organizer_inventory._rows import parse_inventory, owned_design_grid
    from organizer_spaces._core import _json_file, _space, METADATA_FILE
    prefix = "source_" if source else ""
    text_key, output_key = prefix + "inventory_text", prefix + "output"
    if HOSTED and text_key in payload:
        current = parse_inventory(str(payload[text_key] or ""))
        expected = payload.get(prefix + "space_id")
        if expected and expected != (current.get("layout") or {}).get("space_id"):
            raise ValueError("The saved Space ownership could not be verified.")
        return current, (current.get("layout") or {}).get("space")
    if HOSTED:
        return {"bins": [], "layout": None}, None
    prefs = load_preferences()
    output = payload.get(output_key)
    if source and not output:
        raise ValueError("The source Space's saved records are missing.")
    root = Path(str(output or prefs.get("output") or DEFAULT_OUTPUT)).expanduser().resolve()
    current = load_inventory(root)
    stored = (current.get("layout") or {}).get("space")
    metadata = _json_file(root / METADATA_FILE, strict=True)
    if metadata and metadata.get("folder_mode") == "space":
        canonical = _space(metadata.get("space"))
        if canonical is None:
            raise ValueError("The saved Space definition could not be read.")
        if isinstance(stored, dict) and owned_design_grid({}, stored) != owned_design_grid({}, canonical):
            raise ValueError("The saved Space records disagree about its grid.")
        stored = canonical
        current = {**current, "layout": {**(current.get("layout") or {}), "space": stored}}
        expected = payload.get(prefix + "space_id")
        if expected and expected != metadata.get("space_id"):
            raise ValueError("The saved Space ownership could not be verified.")
    elif payload.get(prefix + "space_id"):
        raise ValueError("The saved Space ownership could not be verified.")
    return current, stored


def _editor_context_grid(payload: dict, space: dict | None) -> str:
    from organizer_engine._specs import validate_grid
    if isinstance(space, dict):
        return validate_grid(space.get("grid", "wavefinity"))
    if isinstance(payload.get("space"), dict) and payload["space"].get("kind"):
        raise ValueError("Open the saved Space before generating an AI bin for it.")
    return validate_grid(payload.get("editor_grid", payload.get("grid", "wavefinity")))


def _ai_grid_space(payload: dict, current: dict, space: dict | None) -> dict | None:
    if not isinstance(space, dict):
        return None
    result = dict(space)
    if space.get("kind") == "storage_drawers":
        from organizer_storage.drawers import storage_drawers_active_limits
        result.update(storage_drawers_active_limits(space, (current.get("layout") or {}).get("active")))
    if space.get("kind") == "pegboard" and isinstance(payload.get("space"), dict):
        # Existing board-specific starter hints are independent of grid identity.
        result.update({key: payload["space"][key] for key in ("min_x", "min_z") if key in payload["space"]})
    return result


def _checked_entry_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from wavefinity_web_impl._entry import checked_entry_payload
    return checked_entry_payload(payload, read_inventory=_grid_inventory)


def _printer_output_route(handler):
    def guarded(payload):
        profile = _printer_profile_for(payload)
        with export_printer_profile(profile):
            reply = handler(payload)
        if isinstance(reply, dict):
            reply["printer_fit"] = fit_status(profile)
        return reply
    return guarded


def _grid_entry_route(handler):
    def guarded(payload):
        from organizer_inventory._rows import INVENTORY_LOCK
        with INVENTORY_LOCK:
            request = _checked_entry_payload(payload)
        return handler(request)
    return guarded


def _validate_design_open_guard(payload: dict[str, Any]) -> dict[str, Any]:
    from wavefinity_web_impl._entry import validate_design_open_guard
    return validate_design_open_guard(payload, read_inventory=_grid_inventory)


POST_ROUTES = {
    "/api/preview": preview_payload,
    "/api/space/warm": warm_spaces_payload,
    "/api/design/validate": _validate_design_open_guard,
    "/api/ai/connection": ai_connection_payload,
    "/api/ai/ask": ai_ask_payload,
    "/api/ai/prompt": ai_prompt_payload,
    "/api/ai/candidate": ai_candidate_payload,
    "/api/ai/repair-prompt": ai_repair_prompt_payload,
    "/api/design/inventory-preview": inventory_preview_payload,
    "/api/design/division-label-fit": division_label_fit_payload,
    "/api/pegboard/layouts": pegboard_layouts_payload,
    "/api/pegboard/hooks": pegboard_hooks_payload,
    "/api/feature/default": default_feature_payload,
    "/api/feature/draft": draft_payload,
    "/api/feature/fit": feature_fit_payload,
    "/api/feature/apply": apply_feature_payload,
    "/api/feature/duplicate": duplicate_feature_payload,
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
    "/api/space/copy-text": copy_space_text_payload,
    "/api/space/copy-name": copy_space_name_payload,
}
POST_ROUTES.update({
    **drawer_routes(
        GEOMETRY_LOCK, DEFAULT_OUTPUT, detect_bambu_studio, launch_slicer,
        hosted=HOSTED, generate_from_design=_generate_bin_from_design_spec,
        printer_profile_for=_printer_profile_for,
    ),
})
POST_ROUTES["/api/drawer/generate-bin"] = _printer_output_route(POST_ROUTES["/api/drawer/generate-bin"])
# Every editor/load/import/restore uses design/validate; row insertion and Save
# also need the destination check before their handlers can write or build.
for _grid_entry_path in (
    "/api/drawer/save", "/api/drawer/design-source/save", "/api/drawer/design-source/duplicate",
    "/api/drawer/design-source/status", "/api/drawer/generate-bin",
    "/api/generate", "/api/print", "/api/layout/expand",
):
    if _grid_entry_path in POST_ROUTES:
        POST_ROUTES[_grid_entry_path] = _grid_entry_route(POST_ROUTES[_grid_entry_path])
# (Fix 096 A5) Read-only operation status, plus the side-effecting route set.
# Reads keep ordinary timeout/retry behavior: the wrapper is a pure
# pass-through unless the client supplied an operation_id. structural_design
# is deliberately absent (its own docstring: "Read-only: never touches an
# Inventory"), as is the 15-second drawer summary route.
POST_ROUTES["/api/operation-status"] = operation_status_payload
_OUTPUT_PATHS = {
    "/api/generate", "/api/print", "/api/space/structural-generate",
    "/api/space/structural-print", "/api/space/structural-print-combined",
    "/api/space/storage-box-print", "/api/space/surface-print",
    "/api/drawer/print-complete", "/api/drawer/print-bins", "/api/drawer/save-bins",
}
for _side_effect_path in (
    "/api/generate",
    "/api/connector",
    "/api/pegboard/hooks",
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
    _handler = POST_ROUTES[_side_effect_path]
    if _side_effect_path in _OUTPUT_PATHS:
        _handler = _printer_output_route(_handler)
    POST_ROUTES[_side_effect_path] = _idempotent_operation(_handler)
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
    POST_ROUTES["/api/space/resume"] = _grid_entry_route(POST_ROUTES["/api/space/resume"])


# Anonymous submissions are serialized so concurrent requests cannot exceed the caps.
SUGGESTION_LOCK = threading.Lock()
SUGGESTION_SOURCES: dict[str, float] = {}
SUGGESTION_CREATED: list[float] = []
SUGGESTION_BODY_LIMIT = 16_384


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
        # Only the opt-in experiment may load its pinned browser runtimes.
        # Production pages retain the original same-origin policy.
        browser_poc = resolved_root == WEB_ROOT.resolve() and candidate in {
            resolved_root / "browser-local-poc.html",
            resolved_root / "browser-local-poc-worker.js",
        }
        policy = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        if browser_poc:
            # The pinned WASM binding creates JS wrappers with Function().
            # Permit that only inside the experiment's dedicated worker.
            worker_eval = " 'unsafe-eval'" if candidate.name == "browser-local-poc-worker.js" else ""
            policy = (
                "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'"
                + worker_eval + " https://cdn.jsdelivr.net; "
                "style-src 'self'; worker-src 'self'; "
                "connect-src 'self' https://cdn.jsdelivr.net https://files.pythonhosted.org; "
                "img-src 'self' data: blob:; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'"
            )
        self.send_header("Content-Security-Policy", policy)
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

    def _post_suggestion(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > SUGGESTION_BODY_LIMIT or self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            self._send_json({"error": "Request is too large or invalid."}, HTTPStatus.BAD_REQUEST)
            return
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin not in {f"http://{host}", f"https://{host}"}:
            self.close_connection = True
            self._send_json({"error": "Cross-origin requests are not allowed."}, HTTPStatus.FORBIDDEN)
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.close_connection = True
            self._send_json({"error": "Please submit the form again."}, HTTPStatus.BAD_REQUEST)
            return
        raw = self.rfile.read(length)
        with SUGGESTION_LOCK:
            now = time.monotonic()
            SUGGESTION_CREATED[:] = [t for t in SUGGESTION_CREATED if now - t < 86400]
            for source, last in list(SUGGESTION_SOURCES.items()):
                if now - last >= 60:
                    del SUGGESTION_SOURCES[source]
            source = self.client_address[0]
            if (source in SUGGESTION_SOURCES or
                    sum(now - t < 3600 for t in SUGGESTION_CREATED) >= 20 or
                    len(SUGGESTION_CREATED) >= 100):
                self._send_json({"error": "Too many suggestions right now - please try again later."}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            SUGGESTION_SOURCES[source] = now
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError()
                kind, title, description = (payload.get(k) for k in ("kind", "title", "description"))
                if (kind not in ("bug", "suggestion") or
                        not isinstance(title, str) or not title.strip() or len(title) > 200 or
                        not isinstance(description, str) or not description.strip() or len(description) > 8000):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                self._send_json({"error": "Please choose a kind and provide a title and description."}, HTTPStatus.BAD_REQUEST)
                return
            token = os.environ.get("WAVEFINITY_GITHUB_TOKEN")
            if not token:
                self._send_json({"error": "Suggestions are unavailable right now."}, HTTPStatus.SERVICE_UNAVAILABLE)
                return
            issue = {"title": f"[{kind.capitalize()}] {title}", "body": description, "labels": [kind]}
            request = Request(
                "https://api.github.com/repos/happydadto5/Wavefinity/issues",
                data=json.dumps(issue).encode("utf-8"), method="POST",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                         "Content-Type": "application/json", "User-Agent": "Wavefinity-suggestions",
                         "X-GitHub-Api-Version": "2022-11-28"},
            )
            # Reserve the slot before the call: a timeout may still create an issue.
            SUGGESTION_CREATED.append(time.monotonic())
            try:
                with urlopen(request, timeout=15) as response:
                    created = json.load(response)
                number = created["number"]
                if not isinstance(number, int) or number < 1:
                    raise ValueError()
                self._send_json({"number": number, "url": f"https://github.com/happydadto5/Wavefinity/issues/{number}"})
            except Exception:
                self._send_json({"error": "Could not create the issue. Please try again later."}, HTTPStatus.BAD_GATEWAY)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/suggestions":
            self._post_suggestion()
            return
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
        # Replacing a running server is the launcher's job, and only for an
        # instance it has proven it owns; this process never kills a listener.
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
            "(this process did not replace it - close that window by hand, "
            "or use the Wavefinity launcher, to pick up code changes)"
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
