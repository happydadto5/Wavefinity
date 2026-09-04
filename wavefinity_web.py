"""Local browser interface for Wavefinity.

The HTTP layer is deliberately small and dependency-free. It translates JSON
to the immutable models shared with the command-line tools; every preview,
validation and export comes from the existing Python geometry engine.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import mimetypes
import os
from pathlib import Path
import signal
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
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    BoxSpec,
    ConnectorSpec,
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
    build_features,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    moved_feature,
    resized_feature,
    resolved_options,
    snapped_zone,
)
from organizer_app import (
    APP_DIR,
    DEFAULT_SAMPLE_BOXES,
    PART_KINDS,
    SUPPORT_CATALOG,
    SUPPORT_ORDER,
    _customization_zones,
    _mesh_preview_geometry,
    base_height,
    convert_layout_mode,
    default_feature,
    design_from_dict,
    design_to_dict,
    generate_organizer_files,
    generate_side_file,
    parse_sizes,
    preview_geometry,
    validate_customization_clearance,
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
        PREFERENCES_FILE.write_text(
            json.dumps(current, indent=2) + "\n", encoding="utf-8"
        )
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
        str(key): float(value)
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


def _first_open_position(
    one: Feature,
    box: BoxSpec,
    layout: Layout,
    label: str,
    label_location: str,
    scoop: bool,
) -> Feature:
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
    reserved = _customization_zones(
        box, label, label_location, scoop, layout.mode
    )
    for centre in candidates:
        placed = moved_feature(one, box, centre, layout.mode, layout.snap)
        if all(
            not placed.zone.overlaps(other.zone, MIN_FEATURE_GAP)
            for other in layout.features
        ) and all(
            not placed.zone.overlaps(zone, MIN_FEATURE_GAP)
            for _name, zone in reserved
        ):
            return placed
    raise ValueError("there is no open floor area large enough for that support")


def _grow_zone_to_fit(
    zone: Zone,
    bounds: Zone,
    obstacles: list[Zone],
    grow_x: bool,
    grow_y: bool,
    pitch: float,
) -> Zone:
    """Inflate a zone's active sides until each hits the layout bounds or an obstacle.

    Each of the four sides grows independently, ``pitch`` at a time, and stops
    the moment it would leave the usable floor or come within
    ``MIN_FEATURE_GAP`` of another support or a reserved scoop/label zone.
    That is a simple greedy fill, not a true maximal-rectangle solve, but it
    is enough to turn "make this as big as it can be" into one click.
    """
    x0, y0, x1, y1 = zone.x0, zone.y0, zone.x1, zone.y1
    active = {"x0": grow_x, "x1": grow_x, "y0": grow_y, "y1": grow_y}
    steps = int(max(bounds.width, bounds.depth) / pitch) + 4
    for _ in range(steps):
        moved = False
        for side in ("x0", "x1", "y0", "y1"):
            if not active[side]:
                continue
            trial = {"x0": x0, "y0": y0, "x1": x1, "y1": y1}
            trial[side] += -pitch if side in ("x0", "y0") else pitch
            if (trial["x0"] < bounds.x0 - 1e-6 or trial["y0"] < bounds.y0 - 1e-6
                    or trial["x1"] > bounds.x1 + 1e-6 or trial["y1"] > bounds.y1 + 1e-6):
                active[side] = False
                continue
            candidate = Zone(trial["x0"], trial["y0"], trial["x1"], trial["y1"])
            if any(candidate.overlaps(other, MIN_FEATURE_GAP) for other in obstacles):
                active[side] = False
                continue
            x0, y0, x1, y1 = trial["x0"], trial["y0"], trial["x1"], trial["y1"]
            moved = True
        if not moved:
            break
    return Zone(x0, y0, x1, y1)


def auto_size_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """"Fit to bin": grow a divider draft's zone to reach the usable floor.

    Only grows along the divider's own run axis - the other axis is its
    wall thickness, a separate setting entirely.
    """
    box, layout, label, _part_name, label_location, scoop = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    if one.kind != "divider":
        raise ValueError("fitting to the bin is only offered for a divider")
    index = payload.get("index")
    bounds = layout_zone(box, layout.mode)
    pitch = 8.0 if layout.mode == "cartridge" else layout.snap
    others = [
        feature.zone for position, feature in enumerate(layout.features)
        if index is None or position != int(index)
    ]
    reserved = [
        zone for _name, zone in _customization_zones(
            box, label, label_location, scoop, layout.mode
        )
    ]
    grow_x, grow_y = one.along == "x", one.along != "x"
    grown = _grow_zone_to_fit(one.zone, bounds, others + reserved, grow_x, grow_y, pitch)
    one = replace(one, zone=snapped_zone(grown, box, layout.mode, layout.snap))
    return {
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": resolved_options(box, one, base_height(box, layout.mode)),
    }


def catalog_payload() -> dict[str, Any]:
    parts = []
    indexed = {kind: (title, blurb, flags, fields)
               for kind, title, blurb, flags, fields in PART_KINDS}
    for kind in SUPPORT_ORDER:
        title, blurb, flags, fields = indexed[kind]
        parts.append({
            "kind": kind,
            "title": title,
            "display": SUPPORT_CATALOG[kind][0],
            "description": blurb,
            "flags": flags,
            "fields": [
                {"label": label, "key": key, "default": default}
                for label, key, default in fields
            ],
        })
    return {
        "version": SERVER_VERSION,
        "instance": SERVER_INSTANCE,
        "base_unit": BASE_UNIT,
        "modes": [
            {"value": "fused", "label": "Fused into box"},
            {"value": "separate", "label": "Removable insert"},
        ],
        "parts": parts,
        "defaults": {
            "design": default_design(),
            "output": str(DEFAULT_OUTPUT),
            "connector": {
                "tolerance": LOCKED_TOLERANCE,
                "height": LOCKED_CONNECTOR_HEIGHT,
                "length": LOCKED_CONNECTOR_LENGTH,
                "axis": "y",
                "position": 0.0,
            },
            "sampler_boxes": DEFAULT_SAMPLE_BOXES,
        },
        "preferences": load_preferences(),
    }


def preferences_payload(payload: dict[str, Any]) -> dict[str, Any]:
    update: dict[str, Any] = {}
    if "output" in payload:
        update["output"] = str(payload["output"])
    return {"preferences": save_preferences(update)}


def _design(raw: dict[str, Any]) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    return design_from_dict(raw)


def preview_payload(raw: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(raw)
    with GEOMETRY_LOCK:
        scene = preview_geometry(
            box, label, layout.features, layout.mode, label_location, scoop
        )
    bounds = layout_zone(box, layout.mode)
    geometry = [
        {"points": points, "kind": kind, "normal": normal, "layer": layer}
        for points, kind, normal, layer in scene["geometry"]
    ]
    cavity = wavy_cavity_polygon(box)
    return {
        "design": design_to_dict(
            box, layout, label, part_name, label_location, scoop
        ),
        "geometry": geometry,
        "fits": scene["fits"],
        "message": scene["message"],
        "feature_errors": scene["feature_errors"],
        "invalid_feature_indexes": scene["invalid_feature_indexes"],
        "dimensions": {
            "x": scene["x_text"],
            "y": scene["y_text"],
            "z": scene["z_text"],
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
    }


def default_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, *_ = _design(payload["design"])
    kind = str(payload["kind"])
    indexed = {entry[0]: entry for entry in PART_KINDS}
    if kind not in indexed:
        raise ValueError(f"unknown interior support {kind!r}")
    flags = indexed[kind][3]
    item = _item_from_json(payload.get("item")) if flags["item"] else None
    one = default_feature(
        box,
        kind,
        along=str(payload.get("along", "x")),
        mode=layout.mode,
        item=item,
    )
    # Defaults are values to display, not values the user explicitly chose.
    # Keeping them out of ``one.options`` preserves the builder's dependency
    # cascade: for example, an automatic nest depth continues to follow a
    # changed tool diameter and a pocket recess follows an edited height.
    return {
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": resolved_options(
            box, one, base_height(box, layout.mode)
        ),
    }


def draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, *_ = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    shown = resolved_options(box, one, base_height(box, layout.mode))
    with GEOMETRY_LOCK:
        solids = build_features(
            box, [one], base_height(box, layout.mode), layout_zone(box, layout.mode)
        )
    geometry = []
    part_kind = "feature" if layout.mode == "fused" else "insert"
    for solid in solids:
        geometry.extend(_mesh_preview_geometry(solid, f"{part_kind}_{one.kind}"))
    return {
        "geometry": [
            {"points": points, "kind": kind, "normal": normal, "layer": layer}
            for points, kind, normal, layer in geometry
        ],
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": shown,
    }


def apply_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    width, depth = one.zone.width, one.zone.depth
    cx, cy = one.zone.centre
    one = resized_feature(one, box, (width, depth), layout.mode, layout.snap)
    one = moved_feature(one, box, (cx, cy), layout.mode, layout.snap)
    index = payload.get("index")
    existing = list(layout.features)
    if index is None:
        one = _first_open_position(
            one, box, layout, label, label_location, scoop
        )
        existing.append(one)
        selected = len(existing) - 1
    else:
        selected = int(index)
        if not 0 <= selected < len(existing):
            raise ValueError("the selected support no longer exists")
        existing[selected] = one
    updated = Layout(tuple(existing), layout.mode, layout.snap)
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with GEOMETRY_LOCK:
        build_features(
            box, updated.features, base_height(box, updated.mode),
            layout_zone(box, updated.mode),
        )
    return {
        "design": design_to_dict(
            box, updated, label, part_name, label_location, scoop
        ),
        "selected": selected,
    }


def delete_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    index = int(payload["index"])
    existing = list(layout.features)
    if not 0 <= index < len(existing):
        raise ValueError("the selected support no longer exists")
    existing.pop(index)
    updated = replace(layout, features=tuple(existing))
    return {"design": design_to_dict(
        box, updated, label, part_name, label_location, scoop
    )}


def mode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    converted = convert_layout_mode(box, layout.features, str(payload["mode"]))
    validate_customization_clearance(
        box, converted.features, label, label_location, scoop, converted.mode
    )
    return {"design": design_to_dict(
        box, converted, label, part_name, label_location, scoop
    )}


def generate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    output = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    with GEOMETRY_LOCK:
        result = generate_organizer_files(
            box, layout, output, label, part_name, label_location, scoop
        )
    return {"result": result, "output": str(output)}


def connector_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, *_ = _design(payload["design"])
    options = payload.get("connector", {})
    connector = ConnectorSpec(
        tolerance=float(options.get("tolerance", LOCKED_TOLERANCE)),
        height=float(options.get("height", LOCKED_CONNECTOR_HEIGHT)),
    )
    output_dir = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with GEOMETRY_LOCK:
        result = generate_side_file(
            box,
            connector,
            output_dir / "Connector.3mf",
            str(options.get("axis", "y")),
            float(options.get("position", 0.0)),
            float(options.get("length", LOCKED_CONNECTOR_LENGTH)),
        )
    return {"result": result, "output": str(output_dir)}


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
            connector=connector,
            side_length=float(options.get("length", LOCKED_CONNECTOR_LENGTH)),
            flat_inside=box.flat_inside,
        )
    return {"result": result, "output": str(output_dir)}


POST_ROUTES = {
    "/api/preview": lambda payload: preview_payload(payload["design"]),
    "/api/design/validate": lambda payload: {
        "design": design_to_dict(*_design(payload["design"]))
    },
    "/api/feature/default": default_feature_payload,
    "/api/feature/autosize": auto_size_payload,
    "/api/feature/draft": draft_payload,
    "/api/feature/apply": apply_feature_payload,
    "/api/feature/delete": delete_feature_payload,
    "/api/layout/mode": mode_payload,
    "/api/generate": generate_payload,
    "/api/connector": connector_payload,
    "/api/sampler": sampler_payload,
    "/api/preferences": preferences_payload,
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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def _replace_stale_process(requested_url: str) -> bool:
    """Kill a previous run of this same launcher still holding the port.

    A relaunch during active development means "give me the code on disk
    now," not "reuse whatever is already listening" - that silently serves
    stale code with no visible sign anything is wrong, since the browser
    just talks to whichever process answers the port. Only ever kills a
    process this app itself recorded starting (``PID_FILE``), and only
    after confirming a genuine Wavefinity service - not some unrelated
    program - is the one holding the port.
    """
    try:
        with urlopen(requested_url + "api/health", timeout=1.5) as response:
            if not json.loads(response.read()).get("ok"):
                return False
    except Exception:
        return False
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError, OSError):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    for _ in range(30):
        time.sleep(0.1)
        try:
            with urlopen(requested_url + "api/health", timeout=0.3):
                continue
        except Exception:
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    requested_url = f"http://{args.host}:{args.port}/"
    try:
        server = make_server(args.host, args.port)
    except OSError:
        if _replace_stale_process(requested_url):
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
                "(started by something other than this launcher, or before "
                "this version added the ability to replace it - close that "
                "window and relaunch to pick up code changes)"
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
