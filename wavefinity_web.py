"""Local browser interface for Wavefinity.

The HTTP layer is deliberately small and dependency-free. It translates JSON
to the immutable models shared with the command-line tools; every preview,
validation and export comes from the existing Python geometry engine.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
import mimetypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

import numpy as np

from organizer_engine import (
    BASE_UNIT,
    BASE_PRESETS,
    B4B_DEFAULT_WALL,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
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
    MAX_WALL,
    MIN_WALL,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    WALL_STEP,
    BoxSpec,
    ConnectorSpec,
    differing_connector_plan,
    differing_web_reach,
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
    fitted_nest_feature,
    nest_contour_polygon,
    nest_smoothed_contour,
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
from photo_nest import photo_outline_from_data
from organizer_drawer import drawer_routes
from organizer_spaces import space_routes
from organizer_app import (
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
    design_to_dict,
    generate_organizer_files,
    generate_side_file,
    parse_sizes,
    preview_geometry,
    validate_customization_clearance,
)
from organizer_b4b import (
    B4B_HANDLE_GRIP_MIN,
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    B4B_MIN_WALL,
    B4B_STACK_MIN_BASE,
    b4b_effective_box,
    b4b_mating_polygon,
    b4b_preview_parts,
    b4b_summary,
    validate_b4b_design,
)
from organizer_stack import (
    STACK_MIN_FLOOR_SKIN,
    STACK_MIN_WALL,
    STACK_PLUG_DEPTH,
    STACK_SEAT_DEPTH,
    stack_effective_box,
    stack_enabled,
    stack_summary,
    validate_stack_design,
)


WEB_ROOT = APP_DIR / "web"
DEFAULT_OUTPUT = APP_DIR / "generated"
SERVER_VERSION = "1"
# Regenerated every time the process starts, so the frontend can tell a
# fresh backend apart from the one it originally loaded against - even
# when SERVER_VERSION itself wasn't bumped for a given code change.
SERVER_INSTANCE = uuid.uuid4().hex
GEOMETRY_LOCK = threading.RLock()
PREFERENCES_FILE = APP_DIR / "wavefinity_prefs.json"
PREFERENCES_LOCK = threading.RLock()
PID_FILE = Path(os.environ.get("WAVEFINITY_PID_FILE", str(APP_DIR / "wavefinity.pid")))


def default_design() -> dict[str, Any]:
    box = BoxSpec(x=2 * BASE_UNIT, y=6 * BASE_UNIT, z=40.0)
    return design_to_dict(box, Layout((), "fused", EDITOR_SNAP))


def load_preferences() -> dict[str, Any]:
    """Small local settings that should survive between browser sessions.

    A plain JSON file next to the app, not browser storage - the output
    folder is a filesystem path the *server* writes to, so it belongs with
    the server, and stays put across a different browser or a cleared
    profile.
    """
    try:
        with PREFERENCES_LOCK:
            return json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_preferences(update: dict[str, Any]) -> dict[str, Any]:
    with PREFERENCES_LOCK:
        current = load_preferences()
        current.update(update)
        temp_file = PREFERENCES_FILE.with_suffix(".tmp")
        temp_file.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        temp_file.replace(PREFERENCES_FILE)
        return current


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


def _fit_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> BoxSpec:
    """Grow an 8 mm-grid bin until its floor contains the Photo Nest.

    The current dimensions are floors: uploading or editing a smaller outline
    must not undo a larger bin the user deliberately chose.
    """
    required_x = 2.0 * max(abs(one.zone.x0), abs(one.zone.x1))
    required_y = 2.0 * max(abs(one.zone.y0), abs(one.zone.y1))
    x = max(box.x, BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(box.y, BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    depth = float(one.options.get("depth", 8.0))
    assist = str(one.options.get("lift_assist", "finger_grasp"))
    push_depth = float(one.options.get("push_depth", 4.0)) if assist == "push_out" else 0.0
    z = max(box.z, base_height(box, mode) + depth + push_depth)
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


def photo_nest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract one contour and replace the design interior with its new bin."""
    box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    outline = photo_outline_from_data(
        str(payload.get("image", "")), str(payload.get("mime_type", ""))
    )
    supplied = dict(payload.get("options", {}))
    # Wall thickness, object thickness and retrieval choices are stored with
    # the outline so they survive later moves, turns and resizing.
    options = {
        "clearance": float(supplied.get("clearance", 0.6)),
        "depth": float(supplied.get("depth", 8.0)),
        "rim": 3.0,
        "smoothing": float(supplied.get("smoothing", 0.0)),
        "lift_assist": str(supplied.get("lift_assist", "finger_grasp")),
        "finger_position": str(supplied.get("finger_position", "sides")),
        "finger_width": float(supplied.get("finger_width", 25.0)),
        "push_position": str(supplied.get("push_position", "right")),
        "push_area": float(supplied.get("push_area", 30.0)),
        "push_depth": float(supplied.get("push_depth", 4.0)),
    }
    starter = Feature(
        "nest", Zone(-0.5, -0.5, 0.5, 0.5), options=options,
        contour=outline.contour,
    )
    one = fitted_nest_feature(starter, (0.0, 0.0))
    box = _fit_photo_nest_box(box, one, layout.mode)
    updated = Layout((one,), layout.mode, layout.snap)
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with GEOMETRY_LOCK:
        build_features(box, updated.features, base_height(box, layout.mode),
                       layout_zone(box, layout.mode), layout.mode)
    result = {
        "design": design_to_dict(
            box, updated, label, part_name, label_location, scoop,
        ),
        "selected": 0,
        "outline": {"width": outline.width, "depth": outline.depth},
    }
    if outline.reference_image and outline.reference_bounds:
        result["reference"] = {
            "image": outline.reference_image,
            "bounds": list(outline.reference_bounds),
        }
    return result


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
    return {
        "version": SERVER_VERSION,
        "instance": SERVER_INSTANCE,
        "base_unit": BASE_UNIT,
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
            "base_min_mm": {
                "lid": STACK_SEAT_DEPTH + STACK_MIN_FLOOR_SKIN,
                "direct": STACK_PLUG_DEPTH + STACK_MIN_FLOOR_SKIN,
            },
        },
        "b4b_rules": {
            "grid_pitch_mm": GRID_PITCH,
            "lid_headroom_choices_mm": list(B4B_LID_HEADROOM_CHOICES),
            # Latch count and strength are derived from the case; both lists
            # remain only so an older saved design still parses.
            "latch_counts": list(B4B_LATCH_COUNTS),
            "latch_strengths": list(B4B_LATCH_STRENGTHS),
            "label_locations": list(B4B_LABEL_LOCATIONS),
            "schema_version": B4B_SCHEMA_VERSION,
            "min_field_mm": B4B_MIN_FIELD_XY,
            "min_secure_height_mm": B4B_LATCHED_MIN_HEIGHT,
            "min_wall_mm": B4B_MIN_WALL,
            "default_wall_mm": B4B_DEFAULT_WALL,
            "wall_choices": [
                {"value": value, "label": label} for value, label in B4B_WALL_PRESETS
            ],
            "handle_min_grip_mm": B4B_HANDLE_GRIP_MIN,
            "stack_min_base_mm": B4B_STACK_MIN_BASE,
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
        "defaults": {
            "design": default_design(),
            "output": str(DEFAULT_OUTPUT),
            "keep_log": True,
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
        "preferences": load_preferences(),
        "slicer": {
            "available": (slicer_exe := detect_bambu_studio()) is not None,
            "path": str(slicer_exe) if slicer_exe else None,
            "name": slicer_name(slicer_exe),
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
    update: dict[str, Any] = {}
    if "output" in payload:
        update["output"] = str(payload["output"])
    if "slicer_path" in payload:
        update["slicer_path"] = str(payload["slicer_path"]) if payload["slicer_path"] else ""
    if "keep_log" in payload:
        update["keep_log"] = bool(payload["keep_log"])
    return {"preferences": save_preferences(update)}


def browse_slicer_path_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native file chooser to select a slicer executable."""
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


def browse_output_folder_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Open the native folder chooser for this local desktop app."""
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
    """Display the bins.md log in WordPad for the specified output folder."""
    output_dir = Path(str(payload.get("output") or DEFAULT_OUTPUT)).expanduser().resolve()
    folder_name = output_dir.name
    expected_log = output_dir / f"{folder_name} bins.md"

    log_file: Path | None = None
    if expected_log.is_file():
        log_file = expected_log
    elif output_dir.is_dir():
        candidates = list(output_dir.glob("*bins.md")) + list(output_dir.glob("*.md"))
        if candidates:
            log_file = candidates[0]

    if log_file is None or not log_file.is_file():
        raise FileNotFoundError(f"No log file found in '{output_dir}'. Generate a bin first with 'Keep log' enabled.")

    open_log_with_wordpad(log_file)
    return {"file": str(log_file)}


def _design(raw: dict[str, Any]) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    return design_from_dict(raw)


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
    geometry: list[dict[str, Any]] = []
    b4b_block: dict[str, Any] | None = None
    try:
        with GEOMETRY_LOCK:
            validate_b4b_design(box)
            b4b_block = b4b_summary(box)
            geometry = [
                {"points": points, "kind": kind, "normal": normal, "layer": layer}
                for points, kind, normal, layer in b4b_preview_parts(box)
            ]
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
                    geometry = [
                        {"points": points, "kind": kind, "normal": normal, "layer": layer}
                        for points, kind, normal, layer in b4b_preview_parts(label_free)
                    ]
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
        "geometry": geometry,
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
    }


def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
    if stack_enabled(box):
        validate_stack_design(box)
        stack_block = stack_summary(box)
        box = stack_effective_box(box)
    with GEOMETRY_LOCK:
        scene = preview_geometry(
            box, label, layout.features, layout.mode, label_location, scoop, draft,
            selected=selected,
        )
    bounds = layout_zone(box, layout.mode)
    geometry = [
        {"points": points, "kind": kind, "normal": normal, "layer": layer}
        for points, kind, normal, layer in scene["geometry"]
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
    }


def default_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "adding interior parts")
    box, layout, *_ = _design(payload["design"])
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
    # Defaults are values to display, not values the user explicitly chose.
    # Keeping them out of ``one.options`` preserves the builder's dependency
    # cascade: for example, a pocket depth continues to follow an edited height.
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
    box, layout, label, _part, label_location, scoop = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
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
                {"points": points, "kind": kind, "normal": normal, "layer": layer}
                for points, kind, normal, layer in geometry
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
    shown = resolved_options(box, one, base_height(box, layout.mode))
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
            {"points": points, "kind": kind, "normal": normal, "layer": layer}
            for points, kind, normal, layer in geometry
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
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
    if one.kind == "nest":
        if not one.contour:
            raise ValueError("upload a part photo before adding a Snug Holder")
        one = fitted_nest_feature(one, one.zone.centre)
        box = _fit_photo_nest_box(box, one, layout.mode)
    else:
        if one.kind == "text" and not one.options.get("auto"):
            one = auto_grow_text_feature(one, box, layout.mode)
        if one.kind == "scoop":
            one = replace(one, zone=scoop_zone(
                box, one, base_height(box, layout.mode), layout.mode, layout.snap
            ))

        width, depth = one.zone.width, one.zone.depth
        cx, cy = one.zone.centre
        one = resized_feature(one, box, (width, depth), layout.mode, layout.snap)
        one = moved_feature(one, box, (cx, cy), layout.mode, layout.snap)
    index = payload.get("index")
    existing = list(layout.features)
    if one.kind != "nest" and any(item.kind == "nest" and item.contour for item in existing):
        raise ValueError("a Snug Holder bin contains only its one custom cavity")
    if index is None:
        if one.kind == "nest" and existing:
            raise ValueError("a Snug Holder is one custom cavity; start a new photo bin to replace these interior parts")
        one = _first_open_position(
            one, box, layout, label, label_location, scoop
        )
        existing.append(one)
        selected = len(existing) - 1
    else:
        selected = int(index)
        if not 0 <= selected < len(existing):
            raise ValueError("the selected interior part no longer exists")
        if one.kind != existing[selected].kind and one.kind != "nest":
            remaining = existing[:selected] + existing[selected + 1:]
            one = _first_open_position(
                one, box, replace(layout, features=tuple(remaining)),
                label, label_location, scoop,
            )
        existing[selected] = one
    if one.kind == "nest" and len(existing) != 1:
        raise ValueError("a Snug Holder design can contain only its one custom cavity")
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
            box, updated, label, part_name, label_location, scoop,
        ),
        "selected": selected,
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
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    new_mode = str(payload["mode"])
    if new_mode != "fused" and box.easy_clean_style == "curve":
        box = replace(box, easy_clean_style="bevel")
    converted = convert_layout_mode(box, layout.features, new_mode)
    validate_customization_clearance(
        box, converted.features, label, label_location, scoop, converted.mode
    )
    return {"design": design_to_dict(
        box, converted, label, part_name, label_location, scoop,
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
    box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
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
    ceiling = 100.0 * BASE_UNIT
    floor_x, floor_y = start_x, start_y
    x, y = floor_x, floor_y
    result = fits(x, y)
    while result is None:
        x = round(x + BASE_UNIT)
        y = round(y + BASE_UNIT)
        if x > ceiling:
            raise ValueError(
                "this layout will not fit even in a very large bin - "
                "remove or shrink a support"
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
    return {
        "design": design_to_dict(
            trial, updated, label, part_name, label_location, scoop,
        ),
        "box": {"x": trial.x, "y": trial.y, "z": trial.z},
        "grew": (trial.x > start_x or trial.y > start_y),
        "changed": (trial.x != start_x or trial.y != start_y),
    }


def generate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    output = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    auto_timestamp = bool(payload.get("auto_timestamp", False))
    keep_log = bool(payload.get("keep_log", True))
    with GEOMETRY_LOCK:
        result = generate_organizer_files(
            box, layout, output, label, part_name, label_location, scoop,
            auto_timestamp=auto_timestamp,
            keep_log=keep_log,
        )
    return {"result": result, "output": str(output)}


def connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "the side connector")
    box, *_ = _design(payload["design"])
    options = payload.get("connector", {})
    tolerance = float(options.get("tolerance", LOCKED_TOLERANCE))
    height = float(options.get("height", LOCKED_CONNECTOR_HEIGHT))
    arm_thickness = float(options.get("arm_thickness", DEFAULT_ARM_THICKNESS))
    connector = ConnectorSpec(
        tolerance=tolerance,
        height=height,
        arm_thickness=DEFAULT_ARM_THICKNESS,
    )
    different_heights = bool(options.get("different_heights", False))
    bin_a_height = float(options.get("bin_a_height", box.z)) if different_heights else box.z
    bin_b_height = float(options.get("bin_b_height", box.z)) if different_heights else box.z
    length = float(options.get("length", LOCKED_CONNECTOR_LENGTH))
    output_dir = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = connector_filename(
        connector,
        length=length,
        bin_a_height=bin_a_height,
        bin_b_height=bin_b_height,
        arm_thickness=arm_thickness,
        different_heights=different_heights,
        wall=box.wall,
    )
    with GEOMETRY_LOCK:
        result = generate_side_file(
            box,
            connector,
            output_dir / filename,
            "y",
            0.0,
            length,
            bin_a_height,
            bin_b_height,
            web_thickness=arm_thickness if different_heights else None,
            auto_adjust=False,
        )
    plan = differing_connector_plan(
        connector, length, bin_a_height, bin_b_height, box
    )
    if different_heights:
        plan["length_mm"] = length
        # The web is never thinner than the inward reach, whatever the browser
        # asked for, so report what was actually built.
        plan["web_thickness_mm"] = max(
            arm_thickness, DEFAULT_ARM_THICKNESS + differing_web_reach(box, connector)
        )
    return {
        "result": result,
        "output": str(output_dir),
        "connector_plan": {
            k: (round(v, 3) if isinstance(v, float) else v) for k, v in plan.items()
        },
    }


def sampler_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, *_ = _design(payload["design"])
    options = payload.get("connector", {})
    connector = ConnectorSpec(
        tolerance=float(options.get("tolerance", LOCKED_TOLERANCE)),
        height=float(options.get("height", LOCKED_CONNECTOR_HEIGHT)),
    )
    output_dir = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
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
    return {"result": result, "output": str(output_dir)}


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
    target = str(payload.get("target", "bin"))
    if target == "connector":
        gen_result = connector_payload(payload)
    elif target == "sampler":
        gen_result = sampler_payload(payload)
    else:
        # For Bambu printing, always auto-save with timestamp if file exists or unnamed
        gen_result = generate_payload(dict(payload, auto_timestamp=True))

    files = _extract_generated_files(gen_result)

    # The default bin print also carries one side connector, so a fresh
    # build has the part on the plate to link bins together - but never for a
    # B4B, whose lid controls the rim and which does not use the connector.
    design = payload.get("design")
    is_b4b = (
        isinstance(design, dict)
        and isinstance(design.get("box"), dict)
        and isinstance(design["box"].get("b4b"), dict)
        and design["box"]["b4b"].get("enabled")
    )
    if target not in {"connector", "sampler"} and not is_b4b:
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
    "/api/design/validate": lambda payload: {
        "design": design_to_dict(*_design(payload["design"]))
    },
    "/api/feature/default": default_feature_payload,
    "/api/feature/draft": draft_payload,
    "/api/feature/fit": feature_fit_payload,
    "/api/feature/apply": apply_feature_payload,
    "/api/feature/delete": delete_feature_payload,
    "/api/nest/photo": photo_nest_payload,
    "/api/layout/mode": mode_payload,
    "/api/layout/expand": expand_layout_payload,
    "/api/generate": generate_payload,
    "/api/connector": connector_payload,
    "/api/sampler": sampler_payload,
    "/api/print": print_payload,
    "/api/preferences": preferences_payload,
    "/api/browse-output-folder": browse_output_folder_payload,
    "/api/browse-slicer-path": browse_slicer_path_payload,
    "/api/show-log": show_log_payload,
    # Drawer layout view: inventory file, auto layout, spacers.
    **drawer_routes(GEOMETRY_LOCK, DEFAULT_OUTPUT, detect_bambu_studio, launch_slicer),
    # Welcome screen: spaces, recent spaces, no-inventory folders.
    **space_routes(DEFAULT_OUTPUT, load_preferences, save_preferences),
}


class WavefinityServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR permits two live processes to bind the same
    # address, which makes a second launcher split requests unpredictably.
    allow_reuse_address = False


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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._send_json({"ok": True, "version": SERVER_VERSION, "instance": SERVER_INSTANCE})
            return
        if path == "/api/catalog":
            self._send_json(catalog_payload())
            return
        if path == "/api/browse-slicer-path":
            self._send_json(browse_slicer_path_payload({}))
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
        relative = "index.html" if path in {"", "/"} else unquote(path.lstrip("/"))
        candidate = (WEB_ROOT / relative).resolve()
        try:
            candidate.relative_to(WEB_ROOT.resolve())
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
