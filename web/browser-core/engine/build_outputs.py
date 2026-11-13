"""B06 ordinary output routes; canonical builders run in Pyodide's MEMFS.

B14 can register ROUTES in the Python dispatcher. The worker supplies file
and progress delivery for the active job; no path/token crosses that boundary.
"""
from dataclasses import replace
from pathlib import Path
import math
import json
import tempfile

from organizer_engine import (
    ConnectorSpec, DEFAULT_ARM_THICKNESS, LOCKED_TOLERANCE,
    LOCKED_CONNECTOR_HEIGHT, LOCKED_CONNECTOR_LENGTH, lid_enabled,
    differing_connector_plan, differing_web_reach, generate_sampler,
)
from organizer_app import (
    design_from_dict, design_to_dict, inventory_bin_record,
    generate_organizer_files_transactional, generate_side_file,
    connector_filename, parse_sizes, DEFAULT_SAMPLE_BOXES,
)
from organizer_geometry import build_scope
from organizer_features.stack import stack_effective_box, stack_enabled, stack_summary
from organizer_drawer import stack_part_height
from organizer_base_trim import base_trim_from_design, generate_base_trim_files
from organizer_outputs.printer_profile import (
    current_export_profile, normalise_printer_profile, export_printer_profile,
)
from .editor_routes import entry_route

_emit_file = None
_progress = None


def configure_delivery(emit_file, progress=None):
    """Worker callback: (bytes, basename, MIME) -> opaque local file ID."""
    global _emit_file, _progress
    _emit_file, _progress = emit_file, progress


def dispatch_output_json(path, payload_json, emit_file, progress, dispatch=None):
    """B14 worker binding: callbacks are its existing ctx.file/ctx.progress.

    `dispatch` is the central route_dispatch.dispatch; without it only this
    module's own ROUTES are reachable.

    Transfers use Uint8Array through Pyodide FFI, never JSON/base64 file data.
    This binding does not register routes or mutate the central dispatcher.
    """
    from pyodide.ffi import to_js
    from js import Object
    previous = (_emit_file, _progress)
    words = {"checks": "Checking the design", "shell": "Building the bin walls",
             "features": "Adding the inside parts", "extras": "Adding the extra parts",
             "lid": "Building the lid", "export": "Checking and writing the file",
             "promote": "Preparing the files"}
    configure_delivery(lambda data, name, mime: emit_file(to_js(data), name, mime),
                       lambda name: progress(to_js({"stage": name, "stage_text": words.get(name, "Working")},
                                                   dict_converter=Object.fromEntries)))
    try:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise TypeError("Local route payload must be a JSON object.")
        if dispatch is not None:
            return json.dumps({"result": dispatch(path, payload)}, allow_nan=False)
        if path not in ROUTES:
            raise ValueError("Unsupported local output route")
        return json.dumps({"result": ROUTES[path](payload)}, allow_nan=False)
    except Exception as error:
        return json.dumps({"status": getattr(error, "status", 400 if isinstance(error, (ValueError, KeyError, TypeError)) else 500),
                           "error": {"kind": getattr(error, "kind", type(error).__name__),
                                     "type": type(error).__name__, "message": str(error)}})
    finally:
        configure_delivery(*previous)


def _safe_result(value, directory):
    if isinstance(value, dict):
        return {key: _safe_result(item, directory) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_result(item, directory) for item in value]
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str) and str(directory) in value:
        # Canonical result reports retain output names, never MEMFS paths.
        return value.replace(str(directory) + "/", "").replace(str(directory), "")
    return value


def _run(payload, builder):
    if _emit_file is None:
        raise RuntimeError("Local output file delivery is not configured.")
    profile = payload.get("printer_profile")
    profile = current_export_profile() if profile is None else normalise_printer_profile(profile)
    if payload.get("printer_profile") is not None:
        profile["configured"] = payload.get("printer_profile_configured") is True
    with tempfile.TemporaryDirectory(prefix="wf-output-") as directory:
        output = Path(directory)
        with export_printer_profile(profile), build_scope(preview=False, listener=_progress) as timings:
            result, extra = builder(payload, output)
        paths = sorted(p for p in output.iterdir() if p.is_file() and p.suffix.lower() in (".3mf", ".stl"))
        if not paths:
            raise RuntimeError("No files were generated.")
        # Read and validate the entire set before emitting a single file.
        buffers = [(p.name, p.read_bytes()) for p in paths]
        if len({name for name, _ in buffers}) != len(buffers) or any(not data for _, data in buffers):
            raise RuntimeError("Generated files have duplicate names or empty contents.")
        reply = {"result": _safe_result(result, output), "build_timings_ms": timings.report(), **extra}
        reply["files"] = [{"name": name, "local_file_id": _emit_file(data, name,
                           "model/3mf" if name.lower().endswith(".3mf") else "model/stl")}
                          for name, data in buffers]
        return reply


def _check_space_height(space, box, layout, label, name, scoop):
    if not isinstance(space, dict) or space.get("kind") not in ("portable", "box"):
        return
    cap = float(space["z"])
    try:
        summary = stack_summary(box) if stack_enabled(box) or lid_enabled(box) else None
        top = summary["closed_height_mm"] if summary is not None and (summary["enabled"] or lid_enabled(box)) else stack_part_height(inventory_bin_record(box, layout, None, label, name, scoop))
        top = float(top)
        if not math.isfinite(top) or not math.isfinite(cap):
            raise ValueError("Physical height is not finite")
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Cannot verify this design fits in the {cap:.3f} mm Storage Box interior; generation blocked.") from error
    if top > cap + 1e-6:
        kind = "stack" if summary is not None and summary["enabled"] else "bin"
        raise ValueError(f"This {kind} is {top:.3f} mm tall, but this Storage Box is {cap:.3f} mm inside. Shorten it so it fits under the lid.")


def _generate(payload, output):
    raw = payload["design"]
    if raw.get("design_kind") == "base_trim":
        return generate_base_trim_files(base_trim_from_design(raw), output, str(raw.get("part_name") or ""),
                                        auto_timestamp=bool(payload.get("auto_timestamp", False))), {}
    box, layout, label, name, location, scoop = design_from_dict(raw)
    _check_space_height(payload.get("space"), box, layout, label, name, scoop)
    result = generate_organizer_files_transactional(
        box, layout, output, label, name, location, scoop,
        auto_timestamp=bool(payload.get("auto_timestamp", False)), keep_log=False,
        pegboard_thickness_mm=(payload.get("space") or {}).get("pegboard_thickness_mm", 3.2),
    )
    extra = {}
    if payload.get("keep_log"):
        paths = sorted(output.glob("*.3mf"))
        record = inventory_bin_record(box, layout, paths, label, name, scoop)
        record["qty"] = 0
        # Inventory belongs to B09; save only after the browser saves all files.
        extra = {"inventory_bin": _safe_result(record, output),
                 "inventory_design_spec": design_to_dict(box, layout, label, name, location, scoop)}
    return result, extra


def _connector(payload, output):
    raw = payload["design"]
    if raw.get("design_kind") == "base_trim":
        raise ValueError("Connectors are generated from a bin design, not from a Base Trim design.")
    box, *_ = design_from_dict(raw)
    if box.b4b.enabled:
        raise ValueError("Connectors are unavailable for a B4B bin.")
    if lid_enabled(box):
        raise ValueError("Connectors are unavailable while this bin has a lid.")
    options = payload.get("connector", {})
    spec = ConnectorSpec(tolerance=float(options.get("tolerance", LOCKED_TOLERANCE)),
                         height=float(options.get("height", LOCKED_CONNECTOR_HEIGHT)),
                         arm_thickness=float(options.get("arm_thickness", DEFAULT_ARM_THICKNESS)))
    different = bool(options.get("different_heights", False))
    a = float(options.get("bin_a_height", box.z)) if different else box.z
    b = float(options.get("bin_b_height", box.z)) if different else box.z
    length = float(options.get("length", LOCKED_CONNECTOR_LENGTH))
    effective = stack_effective_box(box) if box.stack.mode == "direct" else box
    rim_a = stack_effective_box(replace(box, z=a)).z if box.stack.mode == "direct" else a
    rim_b = stack_effective_box(replace(box, z=b)).z if box.stack.mode == "direct" else b
    name = connector_filename(spec, length=length, bin_a_height=a, bin_b_height=b,
                              arm_thickness=spec.arm_thickness, different_heights=different, wall=effective.wall)
    result = generate_side_file(effective, spec, output / name, "y", 0.0, length, rim_a, rim_b,
                                web_thickness=spec.arm_thickness if different else None, auto_adjust=False)
    plan = differing_connector_plan(spec, length, rim_a, rim_b, effective) if different else {}
    if different:
        plan["length_mm"] = length
        plan["web_thickness_mm"] = max(spec.arm_thickness, spec.arm_thickness + differing_web_reach(effective, spec)) if plan["webbed"] else spec.arm_thickness
        plan.update(type="side", quantity=1)
    plan.update(mode="auto", types=["side"], different_heights=different,
                wall_mm=effective.wall, requires_same_wall=True)
    return {"side": result}, {"connector_plan": {k: round(v, 3) if isinstance(v, float) else v for k, v in plan.items()}}


def _sampler(payload, output):
    box, *_ = design_from_dict(payload["design"])
    options = payload.get("connector", {})
    spec = ConnectorSpec(tolerance=float(options.get("tolerance", LOCKED_TOLERANCE)),
                         height=float(options.get("height", LOCKED_CONNECTOR_HEIGHT)))
    result = generate_sampler(output / "Wavefinity fit sampler.3mf",
                              sizes=parse_sizes(str(payload.get("boxes", DEFAULT_SAMPLE_BOXES))),
                              height=box.z, wall=box.wall, base_thickness=box.base_thickness,
                              connector=spec, side_length=float(options.get("length", LOCKED_CONNECTOR_LENGTH)),
                              flat_inside=box.flat_inside)
    return result, {}


def generate_payload(payload):
    return _run(payload, _generate)


def connector_save_payload(payload):
    return _run(payload, _connector)


def sampler_payload(payload):
    return _run(payload, _sampler)


ROUTES = {"/api/generate": entry_route(generate_payload),
          "/api/connector": connector_save_payload, "/api/sampler": sampler_payload}
