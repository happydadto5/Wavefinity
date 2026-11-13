"""B08 browser Print preparation route (Print stays Print, separate from Export).

Builds the ordinary files with the B06 builders (``build_outputs``), arranges
them side by side into ONE true multipart 3MF with the B07 plate packaging
(``plate_layout.combine_for_plate``), and hands that file to the browser as a
local file. Nothing is launched: a browser cannot start a slicer, so the reply
says so (``handoff.opened_automatically`` is always False) and the user opens
the file in Bambu Studio themselves. Printed status is NOT decided here; the
page records it only after the user's explicit "I opened it" confirmation.
No Prepared state exists. Pyodide MEMFS only; no paths cross the boundary.
"""
import tempfile
from pathlib import Path

from organizer_engine import lid_enabled
from organizer_geometry import build_scope
from organizer_app import design_from_dict
from organizer_base_trim import base_trim_from_design, generate_base_trim_joint_test_file
from organizer_outputs.printer_profile import (
    current_export_profile, normalise_printer_profile, export_printer_profile,
    print_file_fit_issues,
)
from . import build_outputs as _bo
from . import plate_layout
from .editor_routes import entry_route

_TARGETS = ("bin", "all", "connector", "sampler", "base_trim_joint_test")


def _is_base_trim(design):
    return isinstance(design, dict) and design.get("design_kind") == "base_trim"


def _connectors_apply(design):
    """Only the explicit with-connectors print carries the Side connector, and
    never for a B4B, a lidded bin or a Base Trim design (as in native Print)."""
    if _is_base_trim(design):
        return False
    box, *_ = design_from_dict(design)
    return not box.b4b.enabled and not lid_enabled(box)


def _names(directory):
    return {p.name for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() == ".3mf"}


def _read_files(paths):
    """Read and validate the whole set before anything is emitted."""
    buffers = []
    for path in paths:
        data = path.read_bytes()
        if not data:
            raise RuntimeError("A generated file is missing or empty, so nothing was prepared.")
        buffers.append((path.name, data))
    if len({name for name, _ in buffers}) != len(buffers):
        raise RuntimeError("Generated files have duplicate names.")
    return buffers


def _emit(buffers):
    return [{"name": name, "local_file_id": _bo._emit_file(data, name, "model/3mf")}
            for name, data in buffers]


def _partial(stage, error, directory, design_paths, extra_paths, timings, result):
    """Files are real but Print could not finish: deliver them, never claim a
    handoff, and let the page keep the Printed state untouched."""
    emitted = _emit(_read_files(list(dict.fromkeys(design_paths + extra_paths))))
    return {"partial": True, "partial_stage": stage, "error": error, "design_reused": False,
            "result": _bo._safe_result(result, directory),
            "design_files": [p.name for p in design_paths],
            "files": emitted, "build_timings_ms": timings.report(),
            "handoff": None}


def _prepare(payload, output, handoff_dir, profile, timings):
    target = str(payload.get("target", "bin"))
    if target not in _TARGETS:
        raise ValueError(f"Unsupported print target: {target}")
    design = payload.get("design")
    if not isinstance(design, dict):
        raise ValueError("A design is required to print.")

    result, extra_paths, design_paths = None, [], []
    before = _names(output)
    if target == "connector":
        result, _ = _bo._connector(payload, output)
        design_paths = sorted(output / n for n in _names(output) - before)
    elif target == "sampler":
        result, _ = _bo._sampler(payload, output)
        design_paths = sorted(output / n for n in _names(output) - before)
    elif target == "base_trim_joint_test":
        if not _is_base_trim(design):
            raise ValueError("The physical joint-fit sample needs a Base Trim design.")
        result = generate_base_trim_joint_test_file(
            base_trim_from_design(design), output, auto_timestamp=True)
        design_paths = sorted(output / n for n in _names(output) - before)
    else:
        # Native Print always auto-timestamps so a name is never overwritten.
        result, _ = _bo._generate(dict(payload, auto_timestamp=True, keep_log=False), output)
        design_paths = sorted(output / n for n in _names(output) - before)
    if not design_paths:
        raise RuntimeError("No 3MF files were generated to print.")

    if target == "all" and _connectors_apply(design):
        mark = _names(output)
        try:
            _bo._connector(payload, output)
        except Exception as error:
            # The bin file already exists: report it truthfully as a partial.
            extra_paths = sorted(output / n for n in _names(output) - mark)
            return _partial("connectors",
                            f"Bin files were saved, but connectors could not be generated: {error}",
                            output, design_paths, extra_paths, timings, result)
        extra_paths = sorted(output / n for n in _names(output) - mark)

    files = design_paths + extra_paths
    # Printer limits and geometry: every file must fit, and all parts must sit
    # on one bed. Failures keep the saved files and are reported before handoff.
    issues = []
    for path in files:
        issues.extend(print_file_fit_issues(path, profile))
    if issues:
        return _partial("preflight", "A file does not fit the active printer:\n" + "\n".join(issues),
                        output, design_paths, extra_paths, timings, result)

    if len(files) == 1:
        arranged = files[0]
    else:
        handoff_dir.mkdir(parents=True, exist_ok=True)
        arranged = handoff_dir / f"{design_paths[0].stem} plate.3mf"
        arranged, layout_issues = plate_layout.combine_for_plate(files, profile, arranged)
        if layout_issues:
            return _partial("preflight",
                            "The parts do not fit the active printer:\n" + "\n".join(layout_issues),
                            output, design_paths, extra_paths, timings, result)
    buffers = _read_files([Path(arranged)])
    name = buffers[0][0]
    return {
        "result": _bo._safe_result(result, output),
        "output": None,
        "files": _emit(buffers),
        "design_files": [name],
        "design_reused": False,
        "build_timings_ms": timings.report(),
        # The browser cannot launch Bambu Studio. The page shows this file name
        # as the next step and records Printed only after the user confirms.
        "handoff": {"filename": name, "opened_automatically": False,
                    "confirmation_required": True},
    }


def print_payload(payload):
    if _bo._emit_file is None:
        raise RuntimeError("Local output file delivery is not configured.")
    raw_profile = payload.get("printer_profile")
    profile = current_export_profile() if raw_profile is None else normalise_printer_profile(raw_profile)
    if raw_profile is not None:
        profile["configured"] = payload.get("printer_profile_configured") is True
    with tempfile.TemporaryDirectory(prefix="wf-print-") as directory:
        root = Path(directory)
        output, handoff_dir = root / "parts", root / "plate"
        output.mkdir()
        with export_printer_profile(profile), \
                build_scope(preview=False, listener=_bo._progress) as timings:
            return _prepare(payload, output, handoff_dir, profile, timings)


ROUTES = {"/api/print": entry_route(print_payload)}
