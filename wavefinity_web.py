"""Local browser interface for Wavefinity.

The HTTP layer is deliberately small and dependency-free. It translates JSON
to the immutable models shared with the command-line tools; every preview,
validation and export comes from the existing Python geometry engine.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import ipaddress
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import secrets
import subprocess
import sys
import threading
import time
import tempfile
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import quote, unquote, urlparse
from urllib.request import urlopen

import numpy as np

from organizer_engine import (
    BASE_UNIT,
    BASE_PRESETS,
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
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    MAX_BOX_SIZE,
    MAX_WALL,
    MIN_HEIGHT_ABOVE_BASE,
    MIN_WALL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    WALL_STEP,
    BoxSpec,
    ConnectorSpec,
    LidSpec,
    StackSpec,
    differing_connector_plan,
    differing_web_reach,
    lift_grabber_min_wall,
    lid_enabled,
    make_top_label,
    make_top_label_ledge,
    max_wave_slope,
    generate_sampler,
    wavy_cavity_polygon,
)
from organizer_inserts import (
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    auto_grow_text_feature,
    build_features,
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
    nest_contour_polygon,
    nest_smoothed_contour,
    require_measured_tool_thickness,
    resolve_nest_settings,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    moved_feature,
    occupied_zones,
    option_value,
    normalize_divider_scoop,
    resized_feature,
    scoop_zone,
    resolve_text_features,
    resolved_options,
    setting_interactions,
    snapped_zone,
    text_of,
)
from photo_nest import photo_outline_from_data, retrace_outline_from_rectified
from organizer_drawer import drawer_routes
from organizer_inventory import configure_space_text, resolve_inventory_path
from organizer_product_rules import (
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
)
from organizer_spaces import inventory_enabled, space_routes
from organizer_app import (
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
    design_to_dict,
    generate_organizer_files,
    generate_corner_file,
    generate_side_file,
    inventory_bin_record,
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
    EDGE_LABEL_PROJECTION_PRESETS,
    EDGE_LABEL_THICKNESS_PRESETS,
)


WEB_ROOT = APP_DIR / "web"
IMAGE_ROOT = APP_DIR / "images"
DEFAULT_OUTPUT = APP_DIR / "generated"
HOSTED = (
    os.environ.get("WAVEFINITY_DEPLOYMENT", "local").lower() == "hosted"
    or os.environ.get("RENDER", "").lower() == "true"
)
SERVER_VERSION = "1"
API_COMPAT_VERSION = 1
SERVER_INSTANCE = uuid.uuid4().hex
SERVER_BUILD = os.environ.get("RENDER_GIT_COMMIT", SERVER_VERSION)[:12]
GEOMETRY_LOCK = threading.RLock()
LEGACY_PREFERENCES_FILE = APP_DIR / "wavefinity_prefs.json"


def _user_config_dir() -> Path:
    """The current OS user's Wavefinity settings folder."""
    home = Path.home()
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return (Path(base) if base else home / "AppData" / "Roaming") / "Wavefinity"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Wavefinity"
    base = os.environ.get("XDG_CONFIG_HOME")
    return (Path(base) if base else home / ".config") / "Wavefinity"


# A hosted server is not the end user's profile; it keeps the old file.
PREFERENCES_FILE = (
    LEGACY_PREFERENCES_FILE if HOSTED else _user_config_dir() / "wavefinity_prefs.json"
)
PREFERENCES_LOCK = threading.RLock()
PID_FILE = Path(os.environ.get("WAVEFINITY_PID_FILE", str(APP_DIR / "wavefinity.pid")))
EXPORT_LOCK = threading.RLock()
EXPORT_TTL_SECONDS = 15 * 60
EXPORTS: dict[str, dict[str, Any]] = {}


def default_design() -> dict[str, Any]:
    box = BoxSpec(x=2 * BASE_UNIT, y=6 * BASE_UNIT, z=40.0)
    return design_to_dict(box, Layout((), "fused", EDITOR_SNAP))


def _stack_base_min_by_wall() -> dict[str, dict[str, float]]:
    """Required base thickness for every stacking wall step, by mode.

    Minimum base thickness depends on wall thickness (the foot's flare has to
    finish inside solid base material), so the browser cannot carry a fixed
    number here - it has to read the same geometry stack_base_minimum() uses.
    """
    probe = BoxSpec(x=2 * BASE_UNIT, y=6 * BASE_UNIT, z=100.0)
    table: dict[str, dict[str, float]] = {"lid": {}, "direct": {}}
    steps = round((MAX_WALL - STACK_MIN_WALL) / WALL_STEP)
    for i in range(steps + 1):
        wall = round(STACK_MIN_WALL + i * WALL_STEP, 3)
        for mode in ("lid", "direct"):
            box = replace(
                probe, wall=wall, standard_walls=False,
                stack=StackSpec(mode="direct") if mode == "direct" else StackSpec(),
                lid=LidSpec(enabled=True, stackable=True) if mode == "lid" else LidSpec(),
            )
            table[mode][f"{wall:g}"] = round(stack_base_minimum(box), 3)
    return table


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


def _read_preferences_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_preferences_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_suffix(".tmp")
    temp_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temp_file.replace(path)


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


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def feature_to_dict(one: Feature, mode: str = "fused") -> dict[str, Any]:
    return layout_to_dict(Layout((one,), mode, EDITOR_SNAP))["features"][0]


def _item_from_json(raw: dict[str, Any] | None) -> Item | None:
    if not raw:
        return None
    segments = tuple(
        Segment(float(segment["length"]), float(segment["diameter"]))
        for segment in raw.get("segments", [])
        if str(segment.get("length", "")).strip()
        and str(segment.get("diameter", "")).strip()
    )
    if not segments:
        raise ValueError("enter the stored item's length and thickness")
    return Item(
        str(raw.get("name", "Custom item")).strip() or "Custom item",
        segments,
        str(raw.get("profile", "round")),
        float(raw.get("clearance", 0.4)),
    )


def _feature_from_json(raw: dict[str, Any], mode: str) -> Feature:
    data = dict(raw)
    options = {
        str(key): option_value(str(key), value, str(data.get("kind", "")))
        for key, value in dict(data.get("options", {})).items()
        if str(value).strip() != ""
    }
    data["options"] = options
    if data.get("count") in {"", "auto", None}:
        data["count"] = None
    data["item"] = data.get("item") or None
    layout = layout_from_dict({
        "version": 1,
        "mode": mode,
        "snap": EDITOR_SNAP,
        "features": [data],
    })
    return layout.features[0]


NEST_TOOL_TOP_CLEARANCE = 1.0  # mm of clear air above the tool's own top


def _nest_effective_z_requirement(
    box: BoxSpec, mode: str, base_z: float, resolved: dict[str, Any],
) -> float:
    """The smallest interior work-box Z this Nest can legally use: enough for
    the printable structural minimum, 1 mm of air above the tool's own top,
    and whatever the resolved holder geometry itself rises to."""
    tool_thickness = float(resolved["tool_thickness"])
    if str(resolved["holder_style"]) == "recessed":
        geometry_top = base_z + float(resolved["cavity_depth"])
    else:
        push_depth = (
            float(resolved["push_depth"]) if str(resolved["lift_assist"]) == "push_out" else 0.0
        )
        geometry_top = base_z + tool_thickness + push_depth
    tool_top_requirement = base_z + tool_thickness + NEST_TOOL_TOP_CLEARANCE
    structural_minimum = base_z + MIN_HEIGHT_ABOVE_BASE
    return max(structural_minimum, tool_top_requirement, geometry_top)


def _legacy_nest_z_requirement(box: BoxSpec, mode: str, resolved: dict[str, Any]) -> float:
    """The exact historical grow-only Z requirement for a true legacy Nest
    (no stored holder_style): base_z + its depth, plus Push Out's own deck
    depth when active. No new 1 mm tool-top clearance, no structural-minimum
    floor beyond whatever the box already is - that policy is new-format
    only and must not change a legacy design's sizing just because it is
    edited or re-applied."""
    base_z = base_height(box, mode)
    tool_thickness = float(resolved["tool_thickness"])
    push_depth = float(resolved["push_depth"]) if str(resolved["lift_assist"]) == "push_out" else 0.0
    return base_z + tool_thickness + push_depth


def _fit_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> BoxSpec:
    """Legacy grow-only sizing, for a design saved before Auto-size existed.

    The current dimensions are floors: uploading or editing a smaller outline
    must not undo a larger bin the user deliberately chose.
    """
    resolved = resolve_nest_settings(box, one, base_height(box, mode))
    required_x = 2.0 * max(abs(one.zone.x0), abs(one.zone.x1))
    required_y = 2.0 * max(abs(one.zone.y0), abs(one.zone.y1))
    x = max(box.x, BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(box.y, BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    z_requirement = (
        _legacy_nest_z_requirement(box, mode, resolved) if is_legacy_nest(one)
        else _nest_effective_z_requirement(box, mode, base_height(box, mode), resolved)
    )
    z = max(box.z, z_requirement)
    for _attempt in range(200):
        trial = replace(box, x=float(x), y=float(y), z=float(z))
        bounds = layout_zone(trial, mode)
        grow_x = one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
        grow_y = one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
        if not grow_x and not grow_y:
            return trial
        if grow_x:
            x += BASE_UNIT
        if grow_y:
            y += BASE_UNIT
    raise ValueError("the photographed outline is too large for a printable bin")


def _auto_size_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> BoxSpec:
    """New Auto-size: the smallest legal bin that holds the fitted, centred
    Nest - X and Y may grow or shrink, then Z is set to exactly what the
    resolved holder geometry needs."""
    resolved = resolve_nest_settings(box, one, base_height(box, mode))
    required_x = 2.0 * max(abs(one.zone.x0), abs(one.zone.x1))
    required_y = 2.0 * max(abs(one.zone.y0), abs(one.zone.y1))
    x = max(BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    z = _nest_effective_z_requirement(box, mode, base_height(box, mode), resolved)
    trial: BoxSpec | None = None
    for _attempt in range(400):
        trial = replace(box, x=float(x), y=float(y), z=float(z))
        bounds = layout_zone(trial, mode)
        grow_x = one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
        grow_y = one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
        if not grow_x and not grow_y:
            break
        if grow_x:
            x += BASE_UNIT
        if grow_y:
            y += BASE_UNIT
    else:
        raise ValueError("the photographed outline is too large for a printable bin")
    for axis in ("x", "y"):
        while True:
            try:
                candidate = replace(trial, **{axis: getattr(trial, axis) - BASE_UNIT})
            except ValueError:
                break
            bounds = layout_zone(candidate, mode)
            if (one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
                    or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6):
                break
            trial = candidate
    return trial


def _sized_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> tuple[BoxSpec, Feature]:
    """Apply this Nest's sizing policy: new Auto grows, shrinks and recentres
    around the fitted outline; Manual never resizes, and reports a plain fit
    error instead; legacy (no stored preference) only ever grows, unchanged
    from before Auto-size existed."""
    resolved = resolve_nest_settings(box, one, base_height(box, mode))
    auto_size = resolved.get("auto_size")
    if auto_size is True:
        one = fitted_nest_feature(one, (0.0, 0.0))
        return _auto_size_photo_nest_box(box, one, mode), one
    if auto_size is False:
        one = fitted_nest_feature(one, one.zone.centre)
        base_z = base_height(box, mode)
        bounds = layout_zone(box, mode)
        z_required = _nest_effective_z_requirement(box, mode, base_z, resolved)
        if (one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
                or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
                or z_required > box.z + 1e-6):
            raise ValueError(
                "This Photo Nest no longer fits its bin. Use “Fit bin to tool” "
                "below, or turn Automatic bin sizing back on."
            )
        return box, one
    one = fitted_nest_feature(one, one.zone.centre)
    return _fit_photo_nest_box(box, one, mode), one


def _resolve_photo_nest_edit(
    request_box: BoxSpec,
    layout: Layout,
    one: Feature,
    label: str,
    label_location: str,
    scoop: bool,
) -> tuple[BoxSpec, BoxSpec, Layout, Feature, list[str], list[Any]]:
    """Repair a live Nest edit before anything can reject stale dimensions."""
    if one.kind != "nest" or not one.contour:
        raise ValueError("upload a part photo before adding a Photo Nest")
    one, warnings = clamp_nest_feature_options(one)
    box = _interior_work_box(request_box)
    grown, one = _sized_photo_nest_box(box, one, layout.mode)
    request_box = replace(
        request_box, x=grown.x, y=grown.y,
        z=request_box.z + (grown.z - box.z),
    )
    box = _interior_work_box(request_box)
    updated = Layout((one,), layout.mode, layout.snap)
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with GEOMETRY_LOCK:
        solids = build_features(
            box, updated.features, base_height(box, updated.mode),
            layout_zone(box, updated.mode), updated.mode,
        )
    return request_box, box, updated, one, warnings, solids


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


def nest_retrace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Re-tune an already-rectified reference sheet without repeating paper
    detection or perspective correction. Purely informational: the caller
    decides whether/when to accept the candidate outline it returns."""
    outline = retrace_outline_from_rectified(
        str(payload.get("rectified_image", "")), str(payload.get("mime_type", "image/jpeg")),
        float(payload.get("sensitivity", 50.0)), float(payload.get("cleanup", 50.0)),
    )
    result = {
        "outline": {"width": outline.width, "depth": outline.depth},
        "contour": [list(point) for point in outline.contour],
        "trace_center_mm": list(outline.trace_center_mm) if outline.trace_center_mm else None,
    }
    if outline.reference_image and outline.reference_bounds:
        result["reference"] = {
            "image": outline.reference_image,
            "bounds": list(outline.reference_bounds),
        }
    return result


def photo_nest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Finalize (create or update) the Photo Nest from an ALREADY-TRACED
    contour - see nest_trace_payload for the separate, design-independent
    tracing phase this depends on. Never decodes or retraces a photo."""
    request_box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )

    contour_raw = payload.get("contour")
    if not isinstance(contour_raw, list) or len(contour_raw) < 3:
        raise ValueError("no traced outline was supplied")
    contour = tuple((float(point[0]), float(point[1])) for point in contour_raw)
    source_raw = payload.get("source_contour", contour_raw)
    source_contour = tuple((float(point[0]), float(point[1])) for point in source_raw)

    saved_existing = next(
        (one for one in layout.features if one.kind == "nest" and one.contour), None
    )
    # Replace Photo: prefer the browser's own live draft over the last-saved
    # copy - a debounced auto-save may not have caught up with the newest
    # setting yet, and starting the photo operation must not lose it.
    live_raw = payload.get("feature")
    live_feature = None
    if isinstance(live_raw, dict):
        candidate = _feature_from_json(live_raw, layout.mode)
        if candidate.kind == "nest" and candidate.contour:
            live_feature = candidate
    existing = live_feature if live_feature is not None else saved_existing

    supplied = dict(payload.get("options", {}))
    if existing is None:
        # New scan: Tool thickness is the one measurement the user actually
        # has to supply, and must never be invented.
        measured = supplied.get("tool_thickness", supplied.get("depth"))
        if measured in (None, ""):
            raise ValueError("enter the tool's thickness before generating a Photo Nest")
        tool_thickness = float(measured)
        if not math.isfinite(tool_thickness) or tool_thickness <= 0.0:
            raise ValueError("Tool thickness must be a positive number")
        # A brand-new scan defaults to Recessed Cavity, automatic 60% cavity
        # depth, automatic finger access and automatic bin sizing (spec
        # section 2) - but ONLY when the user has not already chosen
        # otherwise on the draft before the scan finished.
        options = {
            "clearance": float(supplied.get("clearance", 0.6)),
            "tool_thickness": tool_thickness,
            "rim": 3.0,
            "smoothing": float(supplied.get("smoothing", 0.0)),
            "holder_style": str(supplied.get("holder_style", "recessed")),
            "cavity_depth_mode": str(supplied.get("cavity_depth_mode", "auto")),
            "auto_size": bool(supplied["auto_size"]) if "auto_size" in supplied else True,
            "lift_assist": str(supplied.get("lift_assist", "auto")),
            "finger_position": str(supplied.get("finger_position", "sides")),
            "push_position": str(supplied.get("push_position", "right")),
            "push_area": float(supplied.get("push_area", 30.0)),
            "push_depth": float(supplied.get("push_depth", 4.0)),
        }
        if supplied.get("cavity_depth") not in (None, ""):
            options["cavity_depth"] = float(supplied["cavity_depth"])
        if supplied.get("finger_width") not in (None, ""):
            options["finger_width"] = float(supplied["finger_width"])
        starter = Feature(
            "nest", Zone(-0.5, -0.5, 0.5, 0.5), options=options,
            contour=contour, source_contour=source_contour,
        )
    else:
        # Replace Photo: change only the outline. Holder style, cavity
        # depth/mode, finger access, Auto-size, Tool thickness, rotation and
        # scale all survive untouched, or replacing a blurry photo of the
        # same tool would silently reset choices the user already made
        # (including shrinking a manually sized bin back to Auto).
        starter = replace(existing, contour=contour, source_contour=source_contour)
    request_box, _box, updated, one, nest_warnings, _solids = _resolve_photo_nest_edit(
        request_box, layout, starter, label, label_location, scoop,
    )
    return {
        "design": design_to_dict(
            request_box, updated, label, part_name, label_location, scoop,
        ),
        "selected": 0,
        "access": nest_access_preview(one),
        "warnings": nest_warnings,
    }


def _first_open_position(
    one: Feature,
    box: BoxSpec,
    layout: Layout,
    label: str,
    label_location: str,
    scoop: bool,
) -> Feature:
    # Auto-placed text does its own searching, over its real ink rather than a
    # placeholder rectangle, so hunting a slot for it here only produces a
    # zone that ``resolve_text_features`` immediately replaces - and a bad one,
    # since the placeholder is wider than the lettering it stands for.
    if one.kind == "text" and one.options.get("auto"):
        return one
    if one.kind == "scoop":
        return replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))
    bounds = layout_zone(box, layout.mode)
    pitch = 8.0 if layout.mode == "cartridge" else layout.snap
    xs = np.arange(
        bounds.x0 + one.zone.width / 2.0,
        bounds.x1 - one.zone.width / 2.0 + 1e-8,
        pitch,
    )
    ys = np.arange(
        bounds.y0 + one.zone.depth / 2.0,
        bounds.y1 - one.zone.depth / 2.0 + 1e-8,
        pitch,
    )
    candidates = [(float(x), float(y)) for y in ys for x in xs]
    candidates.sort(key=lambda point: point[0] ** 2 + point[1] ** 2)
    if not candidates:
        raise ValueError("there is no open floor area large enough for that interior part")
    reserved = _customization_zones(
        box, label, label_location, scoop, layout.mode
    )
    # Judged on the floor each support actually covers rather than on its zone,
    # so a new one can drop into the open end of a cradle's zone - see
    # ``occupied_zones``.
    base_z = base_height(box, layout.mode)
    taken = occupied_zones(box, layout.features, base_z, layout.mode)
    taken.extend(zone for _name, zone in reserved)
    # That covered floor sits at a fixed offset inside the support's own zone,
    # and moving the support moves both together, so it is worked out once here
    # instead of being rebuilt for every candidate centre on the grid.
    trial = moved_feature(one, box, candidates[0], layout.mode, layout.snap)
    covered = occupied_zones(box, [trial], base_z, layout.mode)[0]
    trial_x, trial_y = trial.zone.centre
    inset = (covered.x0 - trial_x, covered.y0 - trial_y,
             covered.x1 - trial_x, covered.y1 - trial_y)
    for centre in candidates:
        placed = moved_feature(one, box, centre, layout.mode, layout.snap)
        centre_x, centre_y = placed.zone.centre
        covers = Zone(centre_x + inset[0], centre_y + inset[1],
                      centre_x + inset[2], centre_y + inset[3])
        if all(not covers.overlaps(zone, MIN_FEATURE_GAP) for zone in taken):
            return placed
    raise ValueError("there is no open floor area large enough for that interior part")


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
            "options": [
                {"key": option.key, "type": option.value_type}
                for option in definition.options
            ],
            "capabilities": list(definition.capabilities),
        }
        for definition in feature_definitions()
    ]
    parts.append({
        "kind": "edge_mount",
        "title": "Edge Mount",
        "display": "Edge Mount",
        "description": "Mount the bin to an edge using a projecting label and/or screw mounting.",
        "icon": "edge_mount",
        "flags": {
            "qty": False,
            "size": False,
            "along": False,
            "item": False,
            "lean": False,
            "alternate": False,
            "photo": False,
            "text": False,
        },
        "fields": [],
        "options": [],
        "capabilities": ["box_modifier"],
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
            "handle_min_grip_mm": B4B_HANDLE_GRIP_ABS_MIN,
            "stack_min_base_mm": B4B_STACK_MIN_BASE,
        },
        "base_trim_rules": {
            "unit_mm": BASE_UNIT,
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
            # Smallest wall thickness whose grabber root actually bites into
            # the wall; below this, the browser bumps a newly-enabled
            # grabber's wall up to the next preset that clears it.
            "min_wall_mm": round(lift_grabber_min_wall(), 3),
            "sizes": [
                {"value": "small", "label": "Small"},
                {"value": "medium", "label": "Medium"},
                {"value": "large", "label": "Large"},
                {"value": "xl", "label": "XL"},
            ],
            "locations": [
                {"value": "sides", "label": "Sides (left/right)"},
                {"value": "front_back", "label": "Front/back"},
                {"value": "both", "label": "Both"},
            ],
        },
        "edge_mount": {
            "sides": [
                {"value": "front", "label": "Front"},
                {"value": "back", "label": "Back"},
                {"value": "left", "label": "Left"},
                {"value": "right", "label": "Right"},
            ],
            "projection_choices": [
                {"value": value, "label": f"{value:g} mm — {name}"}
                for value, name in EDGE_LABEL_PROJECTION_PRESETS
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
                "label_text_depth_mm": TEXT_DEPTH,
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
        },
        "preferences": {} if HOSTED else load_preferences(),
        "slicer": {
            "available": False if HOSTED else (slicer_exe := detect_bambu_studio()) is not None,
            "path": None if HOSTED else str(slicer_exe) if slicer_exe else None,
            "name": "Bambu Studio" if HOSTED else slicer_name(slicer_exe),
        },
    }


def slicer_name(slicer_path: Path | None) -> str:
    if slicer_path is None:
        return "Bambu Studio"
    name = slicer_path.stem.replace("-", " ").replace("_", " ").title()
    if "bambu" in name.lower():
        return "Bambu Studio"
    if "orca" in name.lower():
        return "OrcaSlicer"
    return name or "Bambu Studio"


def _find_bambu_studio_windows() -> Path | None:
    # 1. Standard installation locations
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Bambu Studio" / "bambu-studio.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # 2. PATH
    which = shutil.which("bambu-studio") or shutil.which("bambu-studio.exe")
    if which:
        return Path(which).resolve()

    # 3. Windows Registry
    try:
        import winreg

        # App Paths
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\bambu-studio.exe") as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and Path(str(val)).is_file():
                        return Path(str(val)).resolve()
            except OSError:
                pass

        # Uninstall keys
        for root, subkey in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ):
            try:
                with winreg.OpenKey(root, subkey) as ukey:
                    for i in range(winreg.QueryInfoKey(ukey)[0]):
                        try:
                            subkey_name = winreg.EnumKey(ukey, i)
                            with winreg.OpenKey(ukey, subkey_name) as app_key:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                if "bambu studio" in str(display_name).lower():
                                    try:
                                        icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                        icon_path = Path(str(icon).strip('"'))
                                        if icon_path.is_file() and icon_path.name.lower() == "bambu-studio.exe":
                                            return icon_path.resolve()
                                    except OSError:
                                        pass
                                    try:
                                        loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                        loc_exe = Path(str(loc).strip('"')) / "bambu-studio.exe"
                                        if loc_exe.is_file():
                                            return loc_exe.resolve()
                                    except OSError:
                                        pass
                        except OSError:
                            continue
            except OSError:
                pass
    except Exception:
        pass
    return None


def _find_bambu_studio_darwin() -> Path | None:
    candidates = [
        Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"),
        Path.home() / "Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    which = shutil.which("BambuStudio") or shutil.which("bambu-studio")
    return Path(which).resolve() if which else None


def _find_bambu_studio_linux() -> Path | None:
    which = shutil.which("bambu-studio")
    return Path(which).resolve() if which else None


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


def launch_slicer(slicer_path: Path, files: list[Path]) -> None:
    if not slicer_path.is_file():
        raise FileNotFoundError(f"Slicer executable not found: {slicer_path}")
    if not files:
        raise ValueError("No files to open in slicer")
    args = [str(slicer_path.resolve())] + [str(f.resolve()) for f in files]
    subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


def preferences_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        return {"preferences": {}}
    update: dict[str, Any] = {}
    if "output" in payload:
        update["output"] = str(payload["output"])
    if "slicer_path" in payload:
        update["slicer_path"] = str(payload["slicer_path"]) if payload["slicer_path"] else ""
    if "default_join_mode" in payload:
        value = str(payload["default_join_mode"])
        if value not in {"side", "base_trim"}:
            raise ValueError("Join bins with must be Side connectors or Base Trim.")
        update["default_join_mode"] = value
    for key, label in (
        ("base_trim_bed_x_mm", "Bed X"),
        ("base_trim_bed_y_mm", "Bed Y"),
    ):
        if key in payload:
            value = float(payload[key])
            if not math.isfinite(value) or value <= 2.0 * BASE_TRIM_BED_EDGE_MARGIN:
                raise ValueError(f"{label} must leave a positive printable area after edge clearance.")
            update[key] = value
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
    if selected:
        save_preferences({"slicer_path": selected})
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
    """Open the native folder chooser for this local desktop app."""
    if HOSTED:
        raise ValueError("Choose a folder in your browser instead.")
    try:
        current = Path(str(payload.get("current") or DEFAULT_OUTPUT)).expanduser()
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


def open_log_with_wordpad(file_path: Path) -> None:
    """Open a file with WordPad, falling back to os.startfile / default editor if WordPad is missing."""
    target = str(file_path.resolve())
    wordpad_candidates = [
        shutil.which("wordpad.exe") or shutil.which("wordpad"),
        shutil.which("write.exe") or shutil.which("write"),
        r"C:\Program Files\Windows NT\Accessories\wordpad.exe",
        r"C:\Program Files (x86)\Windows NT\Accessories\wordpad.exe",
        r"C:\Windows\write.exe",
        r"C:\Windows\System32\write.exe",
    ]
    for exe in wordpad_candidates:
        if exe and (Path(exe).is_file() or shutil.which(exe)):
            try:
                subprocess.Popen([exe, target])
                return
            except Exception:
                pass
    if sys.platform == "win32":
        try:
            os.startfile(target)
            return
        except Exception:
            pass
    fallback = shutil.which("notepad.exe") or shutil.which("notepad") or "notepad"
    subprocess.Popen([fallback, target])


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


def _design(raw: dict[str, Any]) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    return design_from_dict(raw)


def _is_base_trim_design(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("design_kind") == "base_trim"


def _base_trim_preview_meshes(spec) -> list[dict[str, Any]]:
    """Compact assembled-position mesh transport for every physical piece."""
    positions: list[float] = []
    normals: list[float] = []
    for _piece, mesh in make_base_trim_pieces(spec):
        triangles = np.asarray(mesh.triangles, dtype=float)
        if not len(triangles):
            continue
        keep = np.asarray(mesh.area_faces, dtype=float) > 1e-4
        positions.extend(np.round(triangles[keep], 3).reshape(-1).tolist())
        normals.extend(np.round(np.asarray(mesh.face_normals)[keep], 3).reshape(-1).tolist())
    if not positions:
        return []
    return [{
        "kind": "base_trim",
        "owner": "bin",
        "layer": 0,
        "positions": positions,
        "normals": normals,
    }]


def _base_trim_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload["design"]
    spec = base_trim_from_design(raw)
    part_name = str(raw.get("part_name") or "")
    canonical = base_trim_design_to_dict(spec, part_name)
    canonical["base_trim"]["auto_size"] = bool(
        isinstance(raw.get("base_trim"), dict) and raw["base_trim"].get("auto_size")
    )
    with GEOMETRY_LOCK:
        summary = base_trim_summary(spec)
        meshes = _base_trim_preview_meshes(spec)
    inner = base_trim_inner_polygon(spec)
    outer_x, outer_y = summary["outer_mm"]
    return {
        "design": canonical,
        "base_trim": summary,
        "label_outline": [],
        "label_meta": None,
        "text_meta": [],
        "geometry": [],
        "meshes": meshes,
        "fits": True,
        "message": "",
        "feature_errors": [],
        "invalid_feature_indexes": [],
        "draft_error": None,
        "dimensions": {
            "size": (
                f"{outer_x:g} X {outer_y:g} X {spec.height_mm:g} mm Base Trim; "
                f"field {spec.units[0]}U x {spec.units[1]}U"
            ),
            "inside_x": spec.field_x,
            "inside_y": spec.field_y,
        },
        "layout_bounds": [-outer_x / 2.0, -outer_y / 2.0, outer_x / 2.0, outer_y / 2.0],
        "cavity_outline": [[float(x), float(y)] for x, y in inner.exterior.coords],
        "customization_zones": [],
        "feature_footprints": [],
        "draft_footprint": None,
        "feature_outlines": [],
        "nest_soft_contours": [],
        "draft_soft_contour": None,
        "nest_access": [],
        "draft_nest_access": None,
    }


def _interior_work_box(box: BoxSpec) -> BoxSpec:
    """The printable body interior-feature math should size against.

    A stackable request's module-height ``box`` is not what gets printed: lid
    stacking makes the body shorter, direct stacking makes it 3 mm taller.
    preview/export already build against ``stack_effective_box`` - every
    editor path that fits or validates interior geometry has to use the same
    body, or a part can pass Add/Edit/Fit and then fail preview/export.
    """
    if not stack_enabled(box) and not lid_enabled(box):
        return box
    validate_stack_design(box)
    return stack_effective_box(box)


def _reject_if_b4b(payload: dict[str, Any], what: str) -> None:
    """Guard routes that assume a normal box + interior layout.  A B4B interior
    is reserved for child bins and B4B v1 does not use the side connector."""
    design = payload.get("design")
    if not isinstance(design, dict):
        return
    box_raw = design.get("box", {})
    b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
    if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
        raise ValueError(
            f"{what} is not available while Bin for Bins is enabled - the B4B "
            "interior is reserved for child bins and its lid controls the rim"
        )


def _footprint_bounds(
    box: BoxSpec, one: Feature | None, mode: str
) -> list[float] | None:
    """One support's covered floor for the 2D layout, or ``None`` when it is
    simply its whole zone and the browser has nothing extra to draw."""
    if one is None:
        return None
    zone = occupied_zones(box, [one], base_height(box, mode), mode)[0]
    if zone == one.zone:
        return None
    return [zone.x0, zone.y0, zone.x1, zone.y1]


def _resolved_text(
    box: BoxSpec, features: tuple, mode: str,
    label: str, label_location: str, scoop: bool,
) -> tuple:
    """``features`` with every auto-placed text moved to where it really goes.

    Any endpoint that judges a layout has to do this first: an auto text's
    stored zone is only a cache of where it last landed, and a brand-new one
    starts on a placeholder in the middle of the bin.
    """
    return resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, label, label_location, scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )


def _features_from_preview(layout: Layout, scene: dict[str, Any]) -> tuple:
    """The layout's features as the preview resolved them.

    Only ``auto`` text moves, and only during the preview, so a scene that
    could not report its features leaves the layout exactly as it was.
    """
    raw = scene.get("features")
    if not raw:
        return layout.features
    try:
        return layout_from_dict({"mode": layout.mode, "features": raw}).features
    except (ValueError, KeyError, TypeError):
        return layout.features


def _b4b_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Preview for a B4B design: body/lid/latch/label meshes plus the
    authoritative capacity + hardware readout.  Shares the ordinary response
    shape (empty interior-feature fields) so the frontend needs no special
    case to render it."""
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    eff = b4b_effective_box(box)
    # The browser adopts every effective printable dimension so its fields
    # always match what will print and save.
    adopted = replace(box, x=eff.x, y=eff.y, z=eff.z)
    message = ""
    # B4B routinely runs past 100k triangles, where a per-face JSON object
    # (the "geometry" ordinary bins use) is itself most of what the browser
    # has to parse just to show a preview - so B4B ships the compact
    # grouped-flat-array transport instead (see b4b_preview_meshes) and
    # leaves "geometry" empty, only for response-shape compatibility with
    # the ordinary-bin payload.
    meshes: list[dict[str, Any]] = []
    b4b_block: dict[str, Any] | None = None
    try:
        with GEOMETRY_LOCK:
            validate_b4b_design(box)
            b4b_block = b4b_summary(box)
            meshes = b4b_preview_meshes(box)
    except Exception as error:  # surface the real, actionable message
        message = str(error)
        # A bad optional label must not erase the body/lid/latch preview.
        if box.b4b.label_text.strip() and box.b4b.label_location in {"top", "front"}:
            try:
                label_free = replace(
                    box,
                    b4b=replace(box.b4b, label_text="", label_location="none"),
                )
                with GEOMETRY_LOCK:
                    meshes = b4b_preview_meshes(label_free)
            except Exception:
                pass
        try:
            b4b_block = b4b_summary(box)
        except Exception:
            b4b_block = None

    # B4B x/y are the exact child field.  Its physical case outline is derived
    # separately and is reported in b4b_summary.
    bounds = Zone(-eff.x / 2.0, -eff.y / 2.0, eff.x / 2.0, eff.y / 2.0)
    cavity = b4b_mating_polygon(box)
    return {
        "design": design_to_dict(adopted, Layout((), "fused", EDITOR_SNAP),
                                 "", part_name, "bottom", False),
        "b4b": b4b_block,
        "label_outline": [],
        "label_meta": None,
        "text_meta": [],
        "geometry": [],
        "meshes": meshes,
        "fits": not message,
        "message": message,
        "feature_errors": [],
        "invalid_feature_indexes": [],
        "draft_error": None,
        "dimensions": {
            "size": (f"{eff.x:g} X {eff.y:g} X {eff.z:g} mm B4B child field - "
                     f"case outside {b4b_block['case_outer_mm'][0]:g} x "
                     f"{b4b_block['case_outer_mm'][1]:g} mm"
                     if b4b_block else f"{eff.x:g} X {eff.y:g} X {eff.z:g} mm B4B"),
            "inside_x": b4b_block["capacity_mm"][0] if b4b_block else None,
            "inside_y": b4b_block["capacity_mm"][1] if b4b_block else None,
        },
        "layout_bounds": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        "cavity_outline": [[float(x), float(y)] for x, y in cavity.exterior.coords],
        "customization_zones": [],
        "feature_footprints": [],
        "draft_footprint": None,
        "feature_outlines": [],
        "nest_soft_contours": [],
        "draft_soft_contour": None,
        "nest_access": [],
        "draft_nest_access": None,
    }


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if _is_base_trim_design(payload.get("design")):
        return _base_trim_preview_payload(payload)
    if isinstance(payload.get("design"), dict):
        box_raw = payload["design"].get("box", {})
        b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
        if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
            return _b4b_preview_payload(payload)
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    draft_raw = payload.get("draft")
    draft = _feature_from_json(draft_raw, layout.mode) if draft_raw else None
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
    with GEOMETRY_LOCK:
        scene = preview_geometry(
            box, label, layout.features, layout.mode, label_location, scoop, draft,
            selected=selected,
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
         "layer": layer, "owner": owner}
        for points, kind, normal, layer, owner in scene["geometry"]
    ]
    cavity = wavy_cavity_polygon(box)
    # An auto text part finds its own spot during the preview, so the design
    # that comes back carries the zone it actually landed on - otherwise the
    # browser would keep drawing it where it used to be.
    resolved = replace(layout, features=_features_from_preview(layout, scene))
    return {
        "design": design_to_dict(
            stack_request, resolved, label, part_name, label_location, scoop
        ),
        "stack": stack_block,
        "label_outline": scene["label_outline"],
        "label_meta": scene["label_meta"],
        "text_meta": scene["text_meta"],
        "geometry": geometry,
        "fits": scene["fits"],
        "message": scene["message"],
        "feature_errors": scene["feature_errors"],
        "invalid_feature_indexes": scene["invalid_feature_indexes"],
        "draft_error": scene["draft_error"],
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


def validate_design_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload["design"]
    if _is_base_trim_design(raw):
        spec = base_trim_from_design(raw)
        design = base_trim_design_to_dict(spec, str(raw.get("part_name") or ""))
        design["base_trim"]["auto_size"] = bool(
            isinstance(raw.get("base_trim"), dict) and raw["base_trim"].get("auto_size")
        )
        return {"design": design}
    return {"design": design_to_dict(*_design(raw))}


def default_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "adding interior parts")
    box, layout, *_ = _design(payload["design"])
    box = _interior_work_box(box)
    kind = str(payload["kind"])
    try:
        definition = feature_definition(kind)
    except KeyError:
        raise ValueError(f"unknown interior part {kind!r}")
    item = (_item_from_json(payload.get("item"))
            if definition.flags["item"] else None)
    one = default_feature(
        box,
        kind,
        along=str(payload.get("along", "x")),
        mode=layout.mode,
        item=item,
    )
    if one.kind == "nest":
        # A fresh draft is new-format, not a legacy Raised Wall waiting to be
        # upgraded after upload. Seed the choices the UI already promises so
        # the before-photo controls and the generated holder cannot disagree.
        one = replace(one, options={
            **one.options,
            "holder_style": "recessed",
            "cavity_depth_mode": "auto",
            "auto_size": True,
            "lift_assist": "auto",
        })
    # Ordinary defaults are display values, not explicit choices. Keeping them
    # out of ``one.options`` preserves dependency cascades; Nest is the one
    # exception because holder_style also separates new saves from legacy ones.
    result = {
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": resolved_options(
            box, one, base_height(box, layout.mode)
        ),
    }
    if one.kind == "divider":
        result["divider_cells"] = _divider_cells_payload(box, one, layout.mode)
    return result


def _divider_cells_payload(
    box: BoxSpec, one: Feature, mode: str
) -> list[dict[str, Any]]:
    base_z = base_height(box, mode)
    selected = set(divider_scoop_targets(box, one, base_z))
    return [
        {
            "id": cell.identity,
            "row": cell.row,
            "column": cell.column,
            "zone": [cell.zone.x0, cell.zone.y0, cell.zone.x1, cell.zone.y1],
            "scoop": cell.identity in selected,
        }
        for cell in divider_cells(box, one, base_z)
    ]


def draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "editing interior parts")
    request_box, layout, label, _part, label_location, scoop = _design(payload["design"])
    box = _interior_work_box(request_box)
    one = _feature_from_json(payload["feature"], layout.mode)
    nest_solids = None
    if one.kind == "nest":
        request_box, box, _updated, one, _warnings, nest_solids = _resolve_photo_nest_edit(
            request_box, layout, one, label, label_location, scoop,
        )
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
        if one.full_span:
            one = replace(one, zone=layout_zone(box, layout.mode))
    elif one.kind == "scoop":
        one = replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))
    if one.kind == "text" and one.options.get("level") == "rim":
        geometry = []
        tidy = clean_label(text_of(one))
        side = str(one.options.get("rim_side", "back"))
        geometry.extend(_mesh_preview_geometry(make_top_label_ledge(box, side), "top_label_ledge"))
        if tidy:
            try:
                geometry.extend(_mesh_preview_geometry(make_top_label(box, tidy, side), "top_label"))
            except ValueError:
                pass
        return {
            "geometry": [
                {"points": points, "kind": kind, "normal": normal,
                 "layer": layer, "owner": owner}
                for points, kind, normal, layer, owner in geometry
            ],
            "feature": feature_to_dict(one, layout.mode),
            "resolved_options": {},
        }
    # An auto text's stored zone is a placeholder until the resolver has had
    # the rest of the layout to look at, so resolve it here too - otherwise the
    # draft is judged, and drawn, somewhere it will never actually be.
    if one.kind == "text" and one.options.get("auto"):
        existing = list(layout.features)
        index = payload.get("index")
        if index is not None:
            index = int(index)
            if not 0 <= index < len(existing):
                raise ValueError("the selected interior part no longer exists")
            existing.pop(index)
        placed = _resolved_text(
            box, tuple(existing) + (one,), layout.mode,
            label, label_location, scoop,
        )
        one = placed[-1]
    elif one.kind == "text":
        one = auto_grow_text_feature(one, box, layout.mode)
    shown = (
        resolve_nest_settings(box, one, base_height(box, layout.mode))
        if one.kind == "nest" else
        resolved_options(box, one, base_height(box, layout.mode))
    )
    if nest_solids is not None:
        solids = nest_solids
    else:
        with GEOMETRY_LOCK:
            solids = build_features(
                box, [one], base_height(box, layout.mode),
                layout_zone(box, layout.mode), layout.mode, include_text=True,
            )
    geometry = []
    part_kind = "feature" if layout.mode == "fused" else "insert"
    for solid in solids:
        geometry.extend(_mesh_preview_geometry(solid, f"{part_kind}_{one.kind}"))
    result = {
        "geometry": [
            {"points": points, "kind": kind, "normal": normal,
             "layer": layer, "owner": owner}
            for points, kind, normal, layer, owner in geometry
        ],
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": shown,
    }
    if one.kind == "divider":
        result["divider_cells"] = _divider_cells_payload(box, one, layout.mode)
    return result


def feature_fit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "fitting interior parts")
    """Resize one draft feature's zone to the smallest that still holds
    everything it builds - its hole grid, peg row, slot bank or tool. Keeps the
    zone centred and touches nothing else. Raises for a kind with no natural
    contents size (pocket, steps, photo nest, divider, text).
    """
    box, layout, *_ = _design(payload["design"])
    box = _interior_work_box(box)
    one = _feature_from_json(payload["feature"], layout.mode)
    base_z = base_height(box, layout.mode)
    size = feature_min_footprint(box, one, base_z)
    if size is None:
        raise ValueError("this interior part has no contents to fit its size to")
    # Round the exact footprint up to the editor grid so the snapped zone is
    # never a hair under what the part needs (a leaned grid's reach is rarely
    # a whole millimetre).
    snap = layout.snap or EDITOR_SNAP
    size = tuple(math.ceil(v / snap - 1e-6) * snap for v in size)
    fitted = resized_feature(one, box, size, layout.mode, layout.snap)
    with GEOMETRY_LOCK:
        build_features(
            box, (fitted,), base_z, layout_zone(box, layout.mode), layout.mode,
        )
    return {"feature": feature_to_dict(fitted, layout.mode)}


def apply_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "adding interior parts")
    request_box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    box = _interior_work_box(request_box)
    one = _feature_from_json(payload["feature"], layout.mode)
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
        if one.full_span:
            one = replace(one, zone=layout_zone(box, layout.mode))
    if one.kind == "nest":
        existing = list(layout.features)
        index = payload.get("index")
        if index is None:
            if existing:
                raise ValueError("a Photo Nest is one custom cavity; start a new photo bin to replace these interior parts")
        else:
            selected = int(index)
            if not 0 <= selected < len(existing):
                raise ValueError("the selected interior part no longer exists")
            if len(existing) != 1:
                raise ValueError("a Photo Nest design can contain only its one custom cavity")
        request_box, _box, updated, one, nest_warnings, _solids = _resolve_photo_nest_edit(
            request_box, layout, one, label, label_location, scoop,
        )
        return {
            "design": design_to_dict(
                request_box, updated, label, part_name, label_location, scoop,
            ),
            "selected": 0,
            "warnings": nest_warnings,
        }
    if one.kind == "text" and not one.options.get("auto"):
        one = auto_grow_text_feature(one, box, layout.mode)
    if one.kind == "scoop":
        one = replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))

    # Full-span Dividers and Curved Scoops are derived from the bin, not from
    # a user-draggable footprint. Keep their exact normalized zone instead of
    # passing it through ordinary 1 mm resize/move snapping.
    if not (one.kind == "scoop" or (one.kind == "divider" and one.full_span)):
        width, depth = one.zone.width, one.zone.depth
        cx, cy = one.zone.centre
        one = resized_feature(one, box, (width, depth), layout.mode, layout.snap)
        one = moved_feature(one, box, (cx, cy), layout.mode, layout.snap)
    index = payload.get("index")
    existing = list(layout.features)
    if any(item.kind == "nest" and item.contour for item in existing):
        raise ValueError("a Photo Nest bin contains only its one custom cavity")
    if index is None:
        one = _first_open_position(
            one, box, layout, label, label_location, scoop
        )
        existing.append(one)
        selected = len(existing) - 1
    else:
        selected = int(index)
        if not 0 <= selected < len(existing):
            raise ValueError("the selected interior part no longer exists")
        if one.kind != existing[selected].kind:
            remaining = existing[:selected] + existing[selected + 1:]
            one = _first_open_position(
                one, box, replace(layout, features=tuple(remaining)),
                label, label_location, scoop,
            )
        existing[selected] = one
    # Auto-placed text finds its own spot, so resolve before judging overlaps -
    # otherwise a second one is refused for sitting on the first at the
    # placeholder zone it has not been moved out of yet.
    existing = list(_resolved_text(box, tuple(existing), layout.mode,
                                   label, label_location, scoop))
    updated = Layout(tuple(existing), layout.mode, layout.snap)
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with GEOMETRY_LOCK:
        build_features(
            box, updated.features, base_height(box, updated.mode),
            layout_zone(box, updated.mode), updated.mode,
        )
    return {
        "design": design_to_dict(
            request_box, updated, label, part_name, label_location, scoop,
        ),
        "selected": selected,
        "warnings": [],
    }


def delete_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "editing interior parts")
    # Deletion is the recovery path for a design made invalid by shrinking the
    # bin. Parse its schema and box, but defer layout validation until after
    # the unwanted support has been removed.
    box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    index = int(payload["index"])
    existing = list(layout.features)
    if not 0 <= index < len(existing):
        raise ValueError("the selected interior part no longer exists")
    existing.pop(index)
    updated = replace(layout, features=tuple(existing))
    return {"design": design_to_dict(
        box, updated, label, part_name, label_location, scoop,
    )}


def mode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "changing the interior-parts print mode")
    request_box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    box = _interior_work_box(request_box)
    new_mode = str(payload["mode"])
    converted = convert_layout_mode(box, layout.features, new_mode)
    validate_customization_clearance(
        box, converted.features, label, label_location, scoop, converted.mode
    )
    return {"design": design_to_dict(
        request_box, converted, label, part_name, label_location, scoop,
    )}


def expand_layout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "auto-expanding the layout")
    """Resize the bin - on the 8 mm grid, both axes - to the smallest size that
    fits every interior support at the footprint it actually needs, then trim
    back any axis that overshot. A cradle footprint is recomputed from its
    tool, and a bore / post / slot zone is grown (never shrunk) to hold the
    hole grid, peg row or slot bank it was given - so an explicit X/Y quantity
    that overflowed the drawn zone still makes the bin grow instead of erroring.
    Other supports keep the size the user drew. Supports that now overlap - a
    grown block crowding its neighbour - are slid apart along the floor: the
    ``payload["anchor"]`` part (the one just edited) holds still and the rest
    move outward from it, with the bin growing to take in whatever ends up past
    its edge. Nothing is re-sized to make room; only moved.

    The current size is always the floor: this operation only grows. A larger
    bin is valid user intent and is never silently tightened around its parts.
    """
    request_box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    box = _interior_work_box(request_box)
    mode = layout.mode
    originals = list(layout.features)
    if not originals:
        raise ValueError("there are no interior supports to fit")
    # The part the user was editing when the fit gave out. It stays where it is
    # and the others move around it; without one, the biggest block anchors.
    anchor = payload.get("anchor")
    anchor = int(anchor) if anchor is not None and 0 <= int(anchor) < len(originals) else None

    def sized(one: Feature, trial: BoxSpec) -> Feature:
        if one.kind == "nest" and one.contour:
            return fitted_nest_feature(one)
        if one.kind == "cradle" and one.item is not None:
            min_width, min_depth = cradle_min_footprint(one)
            if one.count is None:
                if one.along == "x":
                    width = min_width
                    depth = max(one.zone.depth, min_depth)
                else:
                    width = max(one.zone.width, min_width)
                    depth = min_depth
            else:
                width, depth = min_width, min_depth
        else:
            width, depth = one.zone.width, one.zone.depth
            grown = feature_min_footprint(trial, one, base_height(trial, mode))
            if grown is not None:
                # Round the grown footprint up to the editor grid, exactly as
                # "Fit to contents" does - otherwise the zone snap can leave it
                # a hair under what a leaned grid's reach needs.
                snap = layout.snap or EDITOR_SNAP
                grown = tuple(math.ceil(v / snap - 1e-6) * snap for v in grown)
                width, depth = max(width, grown[0]), max(depth, grown[1])
                return resized_feature(one, trial, (width, depth), mode, layout.snap)
        cx, cy = one.zone.centre
        raw = Zone(cx - width / 2.0, cy - depth / 2.0,
                   cx + width / 2.0, cy + depth / 2.0)
        return replace(one, zone=snapped_zone(raw, trial, mode))

    def spread_apart(placed: list[Feature], trial: BoxSpec) -> list[Feature]:
        """Slide parts along the floor until none overlap, holding the anchor
        still and pushing the rest outward from it. Movement is clamped to the
        trial bin, so a size that cannot separate them just fails this trial and
        the search grows the bin one grid step and tries again."""
        if len(placed) < 2:
            return placed
        base_z = base_height(trial, mode)
        covered = lambda feat: occupied_zones(trial, [feat], base_z, mode)[0]
        zones = [covered(f) for f in placed]
        pivot = anchor
        if pivot is None:
            pivot = max(range(len(placed)),
                        key=lambda i: zones[i].width * zones[i].depth)
        ax, ay = zones[pivot].centre
        order = sorted((i for i in range(len(placed)) if i != pivot),
                       key=lambda i: (zones[i].centre[0] - ax) ** 2
                       + (zones[i].centre[1] - ay) ** 2)
        out = list(placed)
        settled = [pivot]
        for i in order:
            feat = out[i]
            for _ in range(80):
                here = covered(feat)
                clash = next((j for j in settled
                              if here.overlaps(covered(out[j]), MIN_FEATURE_GAP)),
                             None)
                if clash is None:
                    break
                other = covered(out[clash])
                # One editor grid step of slack on top of the bare overlap, so
                # the centre snap in ``moved_feature`` can't round it back into
                # a sub-gap touch and stall the loop.
                slack = (layout.snap or EDITOR_SNAP) + MIN_FEATURE_GAP
                over_x = min(here.x1, other.x1) - max(here.x0, other.x0) + slack
                over_y = min(here.y1, other.y1) - max(here.y0, other.y0) + slack
                cx, cy = here.centre
                if over_x <= over_y:
                    step = over_x if cx >= other.centre[0] else -over_x
                    moved = moved_feature(feat, trial, (cx + step, cy), mode, layout.snap)
                else:
                    step = over_y if cy >= other.centre[1] else -over_y
                    moved = moved_feature(feat, trial, (cx, cy + step), mode, layout.snap)
                if moved.zone.centre == feat.zone.centre:
                    break        # pinned against the bin wall - this trial is too small
                feat = moved
            out[i] = feat
            settled.append(i)
        return out

    def fits(x: float, y: float):
        trial = replace(box, x=float(x), y=float(y))
        try:
            placed = spread_apart(
                [sized(one, trial) for one in originals], trial
            )
            updated = Layout(tuple(placed), mode, layout.snap)
            updated.validate(trial)
            validate_customization_clearance(
                trial, updated.features, label, label_location, scoop, mode
            )
        except ValueError:
            return None
        return trial, updated

    start_x, start_y = box.x, box.y
    ceiling = math.floor(MAX_BOX_SIZE / BASE_UNIT) * BASE_UNIT
    floor_x, floor_y = start_x, start_y
    x, y = floor_x, floor_y
    result = fits(x, y)
    while result is None:
        x = round(x + BASE_UNIT)
        y = round(y + BASE_UNIT)
        if x > ceiling:
            raise ValueError(
                "this layout will not fit within Wavefinity's maximum "
                f"{ceiling:g} mm bin size - remove or shrink a support"
            )
        result = fits(x, y)

    # First fit found by growing both axes; give back any step that was not
    # actually needed (down to the floor).
    for _ in range(200):
        trimmed = False
        if x - BASE_UNIT >= floor_x and fits(x - BASE_UNIT, y) is not None:
            x = round(x - BASE_UNIT)
            trimmed = True
        if y - BASE_UNIT >= floor_y and fits(x, y - BASE_UNIT) is not None:
            y = round(y - BASE_UNIT)
            trimmed = True
        if not trimmed:
            break

    trial, updated = fits(x, y)
    with GEOMETRY_LOCK:
        build_features(
            trial, updated.features, base_height(trial, mode),
            layout_zone(trial, mode), mode,
        )
    # Growth here is X/Y only - the saved design keeps the requested module Z,
    # never the effective work box's printable Z.
    saved_box = replace(request_box, x=trial.x, y=trial.y)
    return {
        "design": design_to_dict(
            saved_box, updated, label, part_name, label_location, scoop,
        ),
        "box": {"x": saved_box.x, "y": saved_box.y, "z": saved_box.z},
        "grew": (trial.x > start_x or trial.y > start_y),
        "changed": (trial.x != start_x or trial.y != start_y),
    }


def generate_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
    keep_log = requested_inventory if HOSTED else inventory_enabled(output, load_preferences())
    with GEOMETRY_LOCK:
        result = generate_organizer_files(
            box, layout, output, label, part_name, label_location, scoop,
            auto_timestamp=auto_timestamp,
            keep_log=keep_log and not HOSTED,
        )
    reply = _generation_reply(result=result, output=output)
    if HOSTED and requested_inventory:
        reply["inventory_bin"] = inventory_bin_record(
            box, layout, _extract_generated_files(result), label,
            part_name, scoop,
        )
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


def create_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted equivalent of a genuinely new typed Space - never accepts
    legacy "box"; that only ever comes from configure_space_text_payload's
    migration path (see Fix 004 Correction 7.H)."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="create",
    )


def configure_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted Configure Existing / migration: never rejected merely because
    the browser-owned inventory text already carries a layout.space."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="update", allow_legacy=True,
    )


def connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("join_mode") == "base_trim":
        raise ValueError("Connectors are turned off while bins are set to use a Base Trim.")
    _reject_if_b4b(payload, "connectors")
    box, *_ = _design(payload["design"])
    if lid_enabled(box):
        raise ValueError("Connectors are unavailable while this bin has a lid.")
    options = payload.get("connector", {})
    connector_type = str(options.get("type", "side"))
    if connector_type not in {"side", "three_way", "four_way"}:
        raise ValueError("Connector type must be side, three_way, or four_way.")
    if connector_type != "side":
        return _corner_connector_payload(payload, box, options, connector_type)
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

    output_dir = _generation_output(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
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
    reply = {
        "result": result,
        "connector_plan": {
            k: (round(v, 3) if isinstance(v, float) else v) for k, v in plan.items()
        },
    }
    return _generation_reply(result=result, output=output_dir, extra=reply)


def _corner_quantity(value: Any) -> int:
    """An actual whole number; never silently truncated."""
    if isinstance(value, bool):
        raise ValueError("Corner connector quantity must be a whole number from 1 to 20.")
    if isinstance(value, str):
        text = value.strip()
        value = int(text) if re.fullmatch(r"[0-9]+", text) else None
    elif isinstance(value, float) and value.is_integer():
        value = int(value)
    if not isinstance(value, int) or not 1 <= value <= 20:
        raise ValueError("Corner connector quantity must be a whole number from 1 to 20.")
    return value


def _corner_connector_payload(
    payload: dict[str, Any], box: Any, options: dict[str, Any], connector_type: str
) -> dict[str, Any]:
    if bool(options.get("different_heights", False)):
        raise ValueError("3-Way and 4-Way Corner connectors require equal-height bins.")
    ways = 3 if connector_type == "three_way" else 4
    quantity = _corner_quantity(options.get("quantity", 1))
    # Fresh defaults: hidden Side/Different settings never reach a corner part.
    connector = ConnectorSpec()
    connector_box = stack_effective_box(box) if box.stack.mode == "direct" else box
    output_dir = _generation_output(payload)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = corner_connector_filename(ways, quantity, connector_box.wall)
    with GEOMETRY_LOCK:
        result = generate_corner_file(
            connector_box, connector, output_dir / filename, ways, quantity
        )
    reply = {
        "result": result,
        "connector_plan": {
            "type": connector_type,
            "quantity": quantity,
            "wall_mm": round(connector_box.wall, 3),
            "requires_equal_height": True,
            "requires_same_wall": True,
            "printed_height_mm": round(connector.height, 3),
            "webbed": False,
        },
    }
    return _generation_reply(result=result, output=output_dir, extra=reply)


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


def _remove_export(record: dict[str, Any]) -> None:
    shutil.rmtree(record["directory"], ignore_errors=True)


def _clean_expired_exports() -> None:
    now = time.monotonic()
    expired = [token for token, record in EXPORTS.items() if record["expires"] <= now]
    for token in expired:
        _remove_export(EXPORTS.pop(token))


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


def _extract_generated_files(result_data: Any) -> list[Path]:
    paths: list[Path] = []
    if isinstance(result_data, dict):
        if "output" in result_data and isinstance(result_data["output"], (str, Path)):
            paths.append(Path(result_data["output"]))
        for v in result_data.values():
            paths.extend(_extract_generated_files(v))
    elif isinstance(result_data, (list, tuple)):
        for item in result_data:
            paths.extend(_extract_generated_files(item))
    seen: set[Path] = set()
    deduped: list[Path] = []
    for p in paths:
        try:
            res = p.resolve()
            if res not in seen and res.is_file():
                seen.add(res)
                deduped.append(res)
        except Exception:
            continue
    return deduped


def print_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if HOSTED:
        raise ValueError("Hosted Wavefinity saves generated files to your selected folder instead.")
    target = str(payload.get("target", "bin"))
    if target == "connector":
        gen_result = connector_payload(payload)
    elif target == "sampler":
        gen_result = sampler_payload(payload)
    elif target == "base_trim_joint_test":
        gen_result = base_trim_joint_test_payload(payload)
    else:
        # For Bambu printing, always auto-save with timestamp if file exists or unnamed
        gen_result = generate_payload(dict(payload, auto_timestamp=True))

    files = _extract_generated_files(gen_result)

    # The default bin print also carries one side connector, so a fresh
    # build has the part on the plate to link bins together - but never for a
    # B4B, whose lid controls the rim and which does not use the connector.
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
    join_mode = str(payload.get("join_mode") or "side")
    if join_mode not in {"side", "base_trim"}:
        raise ValueError("Join bins with must be Side connectors or Base Trim.")
    if (
        target not in {"connector", "sampler"}
        and not is_b4b
        and not has_lid
        and not is_base_trim
        and join_mode == "side"
    ):
        connector_files = _extract_generated_files(connector_payload(payload))
        files.extend(connector_files)

    if not files:
        raise RuntimeError("No 3MF files were generated to send to Bambu Studio.")

    custom = payload.get("slicer_path")
    slicer_path = detect_bambu_studio(custom)
    if slicer_path is None or not slicer_path.is_file():
        raise ValueError(
            "Bambu Studio was not found. Please locate your Bambu Studio executable in settings or install Bambu Studio."
        )

    launch_slicer(slicer_path, files)
    return {
        "result": gen_result.get("result"),
        "output": gen_result.get("output"),
        "files": [str(f) for f in files],
        "slicer": str(slicer_path),
    }


POST_ROUTES = {
    "/api/preview": preview_payload,
    "/api/design/validate": validate_design_payload,
    "/api/feature/default": default_feature_payload,
    "/api/feature/draft": draft_payload,
    "/api/feature/fit": feature_fit_payload,
    "/api/feature/apply": apply_feature_payload,
    "/api/feature/delete": delete_feature_payload,
    "/api/nest/trace": nest_trace_payload,
    "/api/nest/photo": photo_nest_payload,
    "/api/nest/retrace": nest_retrace_payload,
    "/api/layout/mode": mode_payload,
    "/api/layout/expand": expand_layout_payload,
    "/api/generate": generate_payload,
    "/api/connector": connector_payload,
    "/api/sampler": sampler_payload,
    "/api/print": print_payload,
    "/api/preferences": preferences_payload,
    "/api/space/show-folder": show_folder_payload,
    "/api/browse-output-folder": browse_output_folder_payload,
    "/api/browse-slicer-path": browse_slicer_path_payload,
    "/api/show-log": show_log_payload,
    "/api/space/create-text": create_space_text_payload,
    "/api/space/configure-text": configure_space_text_payload,
}
POST_ROUTES.update({
    **drawer_routes(
        GEOMETRY_LOCK, DEFAULT_OUTPUT, detect_bambu_studio, launch_slicer,
        hosted=HOSTED,
    ),
})
if not HOSTED:
    POST_ROUTES.update({
        # Local save-folder selection and optional Space setup.
        **space_routes(DEFAULT_OUTPUT, load_preferences, save_preferences, mutate_preferences),
    })


class WavefinityServer(ThreadingHTTPServer):
    # On Windows, SO_REUSEADDR lets a socket bind a port another process is
    # still actively LISTENing on, which would make a second launcher split
    # requests with the stale one unpredictably - so it stays off there.
    # On POSIX, SO_REUSEADDR carries no such risk: it only permits binding
    # over a socket of this launcher's own past connections still winding
    # down in TIME_WAIT, which is exactly what _replace_stale_process()'s
    # own health-check requests leave behind, and a bare bind() without it
    # can otherwise refuse the immediate relaunch for up to a minute.
    allow_reuse_address = os.name != "nt"


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
            self._send_json({
                "ok": True, "version": SERVER_VERSION,
                "instance": SERVER_INSTANCE, "api_compat": API_COMPAT_VERSION,
                "build": SERVER_BUILD,
            })
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wavefinity local browser app")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _pid_on_port(host: str, port: int) -> int | None:
    """Best-effort: whichever process the OS says is actually bound to this
    port right now, independent of anything this app wrote about itself.

    ``PID_FILE`` only names a process this launcher itself started; a
    process from before that file existed, or started some other way
    entirely, never wrote one - this is the fallback that finds it anyway,
    by asking the OS directly instead of relying on the process's own
    cooperation. Never trusted by itself: the caller still requires a real
    ``/api/health`` response before acting on whatever PID this returns.
    """
    try:
        if os.name == "nt":
            output = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True,
                timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
            ).stdout
            for line in output.splitlines():
                parts = line.split()
                if (len(parts) >= 5 and parts[0] == "TCP"
                        and parts[3] == "LISTENING"
                        and parts[1].rsplit(":", 1)[-1] == str(port)):
                    return int(parts[-1])
        else:
            output = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in output.splitlines():
                if line.strip():
                    return int(line.strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def _replace_stale_process(requested_url: str, host: str, port: int) -> bool:
    """Kill whatever previous process is still holding the port.

    A relaunch during active development means "give me the code on disk
    now," not "reuse whatever is already listening" - that silently serves
    stale code with no visible sign anything is wrong, since the browser
    just talks to whichever process answers the port. The only thing that
    licenses killing anything here is ``/api/health`` proving a genuine
    Wavefinity service - not some unrelated program - is what actually
    answers on this port; how its PID is found (this launcher's own record
    of a process it started, or failing that an OS-level lookup that does
    not depend on the target's cooperation at all) does not change that.
    """
    try:
        with urlopen(requested_url + "api/health", timeout=1.5) as response:
            if not json.loads(response.read()).get("ok"):
                return False
    except Exception as error:
        if hasattr(error, "close"):
            error.close()
        return False
    # A PID file can outlive its process and be reused by Windows. Only the
    # operating system's current port owner is safe to terminate.
    pid = _pid_on_port(host, port)
    if pid is None:
        return False
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        else:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    for _ in range(30):
        time.sleep(0.1)
        try:
            with urlopen(requested_url + "api/health", timeout=0.3):
                continue
        except Exception as error:
            if hasattr(error, "close"):
                error.close()
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
