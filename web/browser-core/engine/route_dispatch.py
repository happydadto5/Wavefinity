"""Central Python local dispatcher. B14 alone assembles later package ROUTES.

No HTTP fallback exists here. Import after installing the MeshGL64 bridge.
Each package exports a path-to-callable mapping, registered atomically once.
"""
import json
from collections.abc import Mapping
from pathlib import Path

from .editor_routes import ROUTES


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
# Retired/JavaScript paths cannot become Python handlers by accident. This is
# runtime registration integrity; B14 owns the complete manifest assembly.
_manifest = json.loads((Path(__file__).parent / "route_manifest.json").read_text(encoding="utf-8"))
_python_paths = {row["path"] for row in _manifest["routes"]
                 if row["disposition"] == "local" and row["runtime"] == "python"}


def register_routes(routes):
    """Register a module's ROUTES once; reject collisions without partial writes."""
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


register_routes(ROUTES)
