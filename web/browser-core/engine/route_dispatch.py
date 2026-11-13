"""Central Python local dispatcher. B14 alone assembles later package ROUTES.

No HTTP fallback exists here. Import after installing the MeshGL64 bridge.
Each package exports a path-to-callable mapping, registered atomically once.
"""
import json
from collections.abc import Mapping
from pathlib import Path

from . import (ai_routes, build_outputs, drawer_routes, editor_routes, nest_routes,
               preview_routes, print_routes, structural_routes)


class LocalRouteError(Exception):
    kind = "LOCAL_ROUTE_ERROR"
    status = 500


class DuplicateLocalRoute(LocalRouteError):
    kind = "DUPLICATE_LOCAL_ROUTE"


class UnsupportedLocalOperation(LocalRouteError):
    kind = "UNSUPPORTED_LOCAL_OPERATION"
    status = 404

    def __init__(self, path):
        self.path = path
        super().__init__("This feature is unavailable in the browser edition.")


_handlers = {}
_registered_maps = []
# The flat final declaration (contracts/route-declaration.json, packaged beside
# this file) is what this runtime dispatches from. Retired and JavaScript paths
# are absent from it, so they can never become Python handlers by accident.
_declaration = json.loads((Path(__file__).parent / "route_declaration.json").read_text(encoding="utf-8"))
_declared = {row["path"]: row for row in _declaration["routes"] if row["runtime"] == "python"}
_python_paths = set(_declared)


def register_routes(routes, module=None):
    """Register a module's ROUTES once; reject collisions without partial writes.

    With `module` (its file stem) every path must also be declared for that
    exact module, so ownership drift is refused at load rather than served.
    """
    if any(routes is registered for registered in _registered_maps):
        return
    if not isinstance(routes, Mapping):
        raise TypeError("Python ROUTES must be a path-to-callable mapping.")
    pending = dict(routes)
    for path, handler in pending.items():
        if not isinstance(path, str) or not path.startswith("/api/") or not callable(handler):
            raise TypeError("Python routes require /api/ paths and callable handlers.")
        if path not in _python_paths:
            raise UnsupportedLocalOperation(path)
        if module is not None and _declared[path]["module"] != f"web/browser-core/engine/{module}.py":
            raise LocalRouteError(f"Route {path} is declared for {_declared[path]['module']}, not {module}.py")
        if path in _handlers:
            raise DuplicateLocalRoute(f"Duplicate local route: {path}")
    _handlers.update(pending)
    _registered_maps.append(routes)


def dispatch(path, payload=None):
    handler = _handlers.get(path)
    if handler is None:
        raise UnsupportedLocalOperation(path)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise TypeError("Local route payload must be a JSON object.")
    return handler(payload)


def dispatch_json(path, payload_json="{}"):
    """JSON boundary for B14's worker: result or a typed B03 error envelope.

    Canonical exception classes/messages survive as type/message; direct
    dispatch leaves the original Python exception intact.
    """
    try:
        result = dispatch(path, json.loads(payload_json))
        return json.dumps({"result": result}, allow_nan=False)
    except Exception as error:
        kind = getattr(error, "kind", type(error).__name__)
        status = getattr(error, "status", 400 if isinstance(error, (KeyError, TypeError, ValueError)) else 500)
        return json.dumps({"status": status, "error": {
            "kind": kind, "message": str(error), "type": type(error).__name__,
        }})


# B14 final assembly: each package's Python ROUTES, registered exactly once.
# JavaScript maps (B09, B13 browser part) are attached in local-api.js instead.
for _name, _module in (
    ("editor_routes", editor_routes), ("preview_routes", preview_routes),
    ("build_outputs", build_outputs), ("structural_routes", structural_routes),
    ("print_routes", print_routes), ("drawer_routes", drawer_routes),
    ("nest_routes", nest_routes), ("ai_routes", ai_routes),
):
    register_routes(_module.ROUTES, _name)

_missing = sorted(_python_paths - set(_handlers))
if _missing:
    raise LocalRouteError(f"Declared Python routes have no handler: {_missing}")


def dispatch_worker_json(path, payload_json, emit_file, progress):
    """Worker entry point: every route, with the active job's file/progress delivery."""
    return build_outputs.dispatch_output_json(path, payload_json, emit_file, progress, dispatch=dispatch)
