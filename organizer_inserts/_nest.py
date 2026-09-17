"""Photo Nest feature defaults and geometry."""
from __future__ import annotations
import math
from dataclasses import dataclass, replace
import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from shapely.ops import unary_union
from organizer_engine import BoxSpec
from organizer_geometry import (
    _extrude_polygon, _extrude_xz_profile, _extrude_yz_profile,
    difference, union,
)
from ._core import Feature, Zone
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)

HOLDER_STYLES = {"raised_wall", "recessed"}
NEST_OUTER_FOOT_MIN = 2.0
NEST_OUTER_FOOT_MAX = 4.0
NEST_TOP_ROUND_OUTER = 1.0
NEST_TOP_ROUND_INNER = 0.5
NEST_INSIDE_RELIEF_MAX = 0.6
NEST_LEAD_IN_MAX = 0.8
# A design saved before holder_style existed must keep its exact old physical
# geometry when it regenerates - the old fixed 2 mm outside foot, the old
# shared top round, and the old fixed-axis finger-cutout placement - even
# though it now *resolves* to holder_style "raised_wall" for display and new
# defaults. Only an explicitly stored holder_style opts into the new adaptive
# buttress and the new tool-relative access planner.
LEGACY_NEST_CHAMFER = 2.0
LEGACY_NEST_TOP_ROUND = 1.0
NEST_FINGER_WIDTH = 25.0
NEST_AUTO_WIDTH_MIN = 18.0
NEST_AUTO_WIDTH_MAX = 30.0
NEST_CUSTOM_WIDTH_MIN = 12.0
NEST_CUSTOM_WIDTH_MAX = 40.0
# Minimum solid wall left below a finger cutter's floor.  The requested finger
# WIDTH is never shrunk to fit a short wall - only the cutter's vertical
# reach is, so a 25 mm-wide opening on an 8 mm wall still opens the full 25 mm
# across but stops 1.5 mm above the floor instead of cutting through it.
NEST_FINGER_BOTTOM_SKIN = 1.5
NEST_PUSH_AREA = 30.0
NEST_PUSH_DEPTH = 4.0
NEST_ASSISTS = {"auto", "none", "finger_grasp", "push_out"}
NEST_FINGER_POSITIONS = {"sides", "top_bottom", "both"}
NEST_PUSH_POSITIONS = {"left", "right", "top", "bottom"}


def _softened_outline(outline: Polygon, smoothing: float) -> Polygon:
    """Round off inward and outward details smaller than ``smoothing`` mm.

    A close (fill notches) then an open (shave nubs); either can be skipped if
    it would collapse the shape. Applied in the outline's own local scale,
    before any resize/rotation, so a fixed millimetre value reads the same
    however the nest is later scaled.
    """
    if not math.isfinite(smoothing) or smoothing < 0.0:
        raise ValueError("Soften outline must be zero or greater")
    if smoothing <= 0.0:
        return outline
    closed = outline.buffer(smoothing, join_style="round").buffer(
        -smoothing, join_style="round"
    )
    opened = closed.buffer(-smoothing, join_style="round").buffer(
        smoothing, join_style="round"
    )
    if not opened.is_empty and opened.area > 1e-6:
        return opened
    return outline


def nest_smoothed_contour(one: Feature) -> tuple[tuple[float, float], ...]:
    """The stored outline with the Soften-outline pass applied, still in the
    feature's own local millimetres - before resize, rotation and placement -
    so the 2D layout can draw exactly the silhouette the part will get."""
    if not one.contour:
        raise ValueError("upload a part photo before generating a Photo Nest")
    poly = _softened_outline(
        Polygon(one.contour), float(one.options.get("smoothing", 0.0))
    )
    return tuple(
        (round(float(x), 3), round(float(y), 3))
        for x, y in list(poly.exterior.coords)[:-1]
    )


def _nest_local_polygon(one: Feature, include_clearance: bool = False) -> Polygon:
    """The resized Photo Nest outline before editor rotation and placement."""
    if not one.contour:
        raise ValueError("upload a part photo before generating a Photo Nest")
    outline = _softened_outline(
        Polygon(one.contour), float(one.options.get("smoothing", 0.0))
    )
    outline = affinity.scale(outline, xfact=one.scale, yfact=one.scale, origin=(0, 0))
    if include_clearance:
        clearance = float(one.options.get("clearance", 0.6))
        if not math.isfinite(clearance) or clearance < 0.0:
            raise ValueError("Clearance must be zero or greater")
        outline = outline.buffer(clearance, join_style="round")
    return outline


def nest_contour_polygon(one: Feature, include_clearance: bool = False) -> Polygon:
    """The photo outline after proportional resize, rotation and placement."""
    outline = _nest_local_polygon(one, include_clearance)
    outline = affinity.rotate(outline, one.rotation, origin=(0, 0), use_radians=False)
    cx, cy = one.zone.centre
    return affinity.translate(outline, xoff=cx, yoff=cy)


# --- option resolution (works from the raw stored options alone, no BoxSpec
# needed - matches how ``rim`` has always been read directly) -----------------

def _is_legacy_nest(one: Feature) -> bool:
    """True for a design saved before holder_style existed. Its Raised Wall
    geometry and finger-cutout placement must stay exactly what they always
    were, not silently pick up the new adaptive buttress or access planner."""
    return "holder_style" not in one.options


# Public alias - the web layer needs this to keep legacy Z sizing exact too.
is_legacy_nest = _is_legacy_nest


def require_measured_tool_thickness(one: Feature) -> None:
    """A new-format Photo Nest (one that has ever had holder_style stored)
    with a traced contour must have a real, positive Tool thickness. The
    internal 8 mm fallback in _resolved_tool_thickness is only for a true
    legacy design (never had holder_style) or a new-format draft with no
    contour yet (nothing has been measured or built yet either way)."""
    if _is_legacy_nest(one) or not one.contour:
        return
    raw = one.options.get("tool_thickness", one.options.get("depth"))
    try:
        value = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        value = None
    if value is None or not math.isfinite(value) or value <= 0.0:
        raise ValueError("Enter Tool thickness before generating this Photo Nest.")


def _resolved_tool_thickness(one: Feature) -> float:
    """``tool_thickness``, falling back to the legacy ``depth`` key so an
    older Raised Wall design keeps its physical wall height unchanged."""
    value = one.options.get("tool_thickness")
    if value is None:
        value = one.options.get("depth")
    return float(value) if value is not None else 8.0


def _resolved_holder_style(one: Feature) -> str:
    style = str(one.options.get("holder_style", "raised_wall"))
    return style if style in HOLDER_STYLES else "raised_wall"


def _resolved_cavity_depth(one: Feature, tool_thickness: float) -> float:
    mode = str(one.options.get("cavity_depth_mode", "auto"))
    if mode != "manual":
        return 0.6 * tool_thickness
    stored = one.options.get("cavity_depth")
    depth = float(stored) if stored is not None else 0.6 * tool_thickness
    if not math.isfinite(depth) or depth <= 0.0:
        return 0.6 * tool_thickness
    return min(depth, tool_thickness)


def _resolved_finger_settings(one: Feature) -> tuple[str, str, float | None]:
    # A legacy design's own historical default was "Finger grasp" (there was
    # no Automatic yet); only a design that has ever seen holder_style
    # defaults to the new "auto".
    default_assist = "finger_grasp" if _is_legacy_nest(one) else "auto"
    assist = str(one.options.get("lift_assist", default_assist))
    locations = str(one.options.get("finger_position", "sides"))
    width = one.options.get("finger_width")
    width = float(width) if width is not None else None
    return assist, locations, width


def _line_coordinates(geometry, axis: int) -> list[float]:
    """Coordinates from any Shapely line/boundary intersection - used only by
    the legacy finger-cutout placement, which predates the access planner."""
    if geometry.is_empty:
        return []
    if hasattr(geometry, "geoms"):
        values: list[float] = []
        for part in geometry.geoms:
            values.extend(_line_coordinates(part, axis))
        return values
    if hasattr(geometry, "coords"):
        return [float(point[axis]) for point in geometry.coords]
    return []


def _nest_access_mode(assist: str) -> str:
    if assist == "auto":
        return "auto"
    if assist == "finger_grasp":
        return "custom"
    return "off"


def _min_rotated_rect_axes(polygon: Polygon) -> tuple[np.ndarray, np.ndarray, float, float]:
    """``(short_dir, long_dir, short_span, long_span)`` of the polygon's
    minimum rotated rectangle - unit vectors and side lengths."""
    mrr = polygon.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]
    if len(coords) != 4:
        min_x, min_y, max_x, max_y = polygon.bounds
        coords = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    p0, p1, p2 = np.array(coords[0]), np.array(coords[1]), np.array(coords[2])
    edge_a, edge_b = p1 - p0, p2 - p1
    len_a, len_b = float(np.linalg.norm(edge_a)), float(np.linalg.norm(edge_b))
    if len_a <= 1e-9 or len_b <= 1e-9:
        raise ValueError("this outline is too thin to plan finger access")
    if len_a >= len_b:
        return edge_b / len_b, edge_a / len_a, len_b, len_a
    return edge_a / len_a, edge_b / len_b, len_a, len_b


def _automatic_finger_width_for(polygon: Polygon) -> float:
    _short_dir, _long_dir, short_span, _long_span = _min_rotated_rect_axes(polygon)
    return min(NEST_AUTO_WIDTH_MAX, max(NEST_AUTO_WIDTH_MIN, 0.75 * short_span))


def _automatic_finger_width(one: Feature) -> float:
    return _automatic_finger_width_for(_nest_local_polygon(one, include_clearance=True))


def _raised_wall_outer_foot(wall_height: float) -> float:
    """Adaptive structural buttress: bigger on a taller wall, clamped to a
    sane printable range, and never taller than the wall itself - a very
    thin Raised Wall does not need (or have room for) a 2 mm buttress."""
    target = min(NEST_OUTER_FOOT_MAX, max(NEST_OUTER_FOOT_MIN, 0.35 * wall_height))
    return min(target, wall_height)


# --- the one authoritative Nest access planner --------------------------------
#
# Works entirely in local tool coordinates, before editor rotation and
# placement. Raised Wall notches, Recessed scoops, required-footprint sizing
# and the 2D preview all resolve access through this one search.

@dataclass(frozen=True)
class AccessPoint:
    position: tuple[float, float]
    tangent: tuple[float, float]
    normal: tuple[float, float]     # outward, away from the polygon's interior
    chord: float                    # local straight-line safety margin achieved


@dataclass(frozen=True)
class NestAccessPlan:
    style: str                      # "finger_grasp" | "none"
    width: float
    points: tuple[AccessPoint, ...]
    footprint: Polygon              # union of local access circles, for sizing/preview
    warning: str | None


def _sample_at(polygon: Polygon, s: float) -> np.ndarray:
    length = polygon.exterior.length
    point = polygon.exterior.interpolate(s % length)
    return np.array([point.x, point.y])


def _validate_access_point(
    polygon: Polygon, s: float, width: float, origin: np.ndarray,
) -> AccessPoint | None:
    """One candidate boundary location: sample the exterior a half-width
    either side and require the straight chord between them to be at least
    70% of the requested opening, so a sharp or narrow spot is rejected."""
    a = _sample_at(polygon, s - width / 2.0)
    b = _sample_at(polygon, s + width / 2.0)
    chord_vec = b - a
    chord = float(np.linalg.norm(chord_vec))
    if chord < 0.70 * width or chord < 1e-6:
        return None
    tangent = chord_vec / chord
    normal = np.array([tangent[1], -tangent[0]])
    centre = _sample_at(polygon, s)
    if np.dot(normal, centre - origin) < 0.0:
        normal = -normal
    return AccessPoint(
        (float(centre[0]), float(centre[1])),
        (float(tangent[0]), float(tangent[1])),
        (float(normal[0]), float(normal[1])),
        chord,
    )


def _segment_through_point(
    polygon: Polygon, line: LineString, near: Point,
) -> tuple[np.ndarray, np.ndarray] | None:
    """The one chord of ``line`` clipped to the polygon interior that actually
    passes through ``near`` - the segment a candidate axis line forms across
    the lobe containing the outline's own representative point."""
    clipped = line.intersection(polygon)
    if clipped.is_empty:
        return None
    segments = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
    best, best_distance = None, None
    for segment in segments:
        if not hasattr(segment, "coords") or len(segment.coords) < 2:
            continue
        distance = segment.distance(near)
        if best_distance is None or distance < best_distance:
            best_distance, best = distance, segment
    if best is None:
        return None
    coords = list(best.coords)
    return np.array(coords[0]), np.array(coords[-1])


def _axis_pair(
    polygon: Polygon, direction: np.ndarray, representative: Point, width: float,
) -> tuple[AccessPoint, AccessPoint] | None:
    """Both ends of the candidate line's chord through the representative
    point, only if both independently pass the local-chord safety check."""
    min_x, min_y, max_x, max_y = polygon.bounds
    reach = math.hypot(max_x - min_x, max_y - min_y) + 10.0
    origin = np.array([representative.x, representative.y])
    line = LineString([origin - direction * reach, origin + direction * reach])
    ends = _segment_through_point(polygon, line, representative)
    if ends is None:
        return None
    points: list[AccessPoint] = []
    for end in ends:
        s = polygon.exterior.project(Point(end))
        point = _validate_access_point(polygon, s, width, origin)
        if point is None:
            return None
        points.append(point)
    return points[0], points[1]


def _single_axis_points(
    polygon: Polygon, direction: np.ndarray, representative: Point, width: float,
) -> list[AccessPoint]:
    """Whichever end(s) of the candidate line's chord individually validate -
    used for an explicit Custom side/end request, where using only the valid
    one is preferred over rejecting the whole Nest."""
    min_x, min_y, max_x, max_y = polygon.bounds
    reach = math.hypot(max_x - min_x, max_y - min_y) + 10.0
    origin = np.array([representative.x, representative.y])
    line = LineString([origin - direction * reach, origin + direction * reach])
    ends = _segment_through_point(polygon, line, representative)
    if ends is None:
        return []
    found = []
    for end in ends:
        s = polygon.exterior.project(Point(end))
        point = _validate_access_point(polygon, s, width, origin)
        if point is not None:
            found.append(point)
    return found


def _boundary_fallback_pair(
    polygon: Polygon, width: float, representative: Point,
) -> tuple[AccessPoint, AccessPoint] | None:
    """Sample the whole exterior at ~5 mm steps for an irregular outline the
    centre-line search could not pair, and score the candidate pairs."""
    length = polygon.exterior.length
    count = max(8, int(length // 5.0))
    origin = np.array([representative.x, representative.y])
    samples: list[AccessPoint] = []
    for index in range(count):
        point = _validate_access_point(polygon, length * index / count, width, origin)
        if point is not None:
            samples.append(point)
    best_pair, best_score = None, None
    opposite_limit = math.cos(math.radians(150.0))  # within ~30 deg of opposite
    for i, a in enumerate(samples):
        for b in samples[i + 1:]:
            cos_angle = float(np.dot(np.array(a.normal), np.array(b.normal)))
            if cos_angle > opposite_limit:
                continue
            pa, pb = np.array(a.position), np.array(b.position)
            if float(np.linalg.norm(pb - pa)) < width:
                continue
            # A cheap stand-in for "resulting Nest bounding area": the two
            # points' own bounding box, without recomputing the whole footprint.
            proxy_area = abs(pa[0] - pb[0]) * abs(pa[1] - pb[1])
            centre_distance = float(np.linalg.norm((pa + pb) / 2.0 - origin))
            score = (proxy_area, centre_distance, -min(a.chord, b.chord))
            if best_score is None or score < best_score:
                best_score, best_pair = score, (a, b)
    return best_pair


def resolve_nest_access_plan(
    polygon: Polygon, mode: str, locations: str = "sides", width: float | None = None,
) -> NestAccessPlan:
    """The one authoritative access search: Automatic, Off, or Custom, all in
    the tool's own local coordinates. Never raises for a difficult outline -
    it falls back to a single location, then to none, always with a warning."""
    mode = mode if mode in {"auto", "off", "custom"} else "auto"
    if mode == "off":
        return NestAccessPlan("none", 0.0, (), Polygon(), None)

    representative = polygon.representative_point()
    short_dir, long_dir, _short_span, _long_span = _min_rotated_rect_axes(polygon)

    if mode == "custom":
        resolved_width = min(NEST_CUSTOM_WIDTH_MAX, max(
            NEST_CUSTOM_WIDTH_MIN,
            float(width) if width else _automatic_finger_width_for(polygon),
        ))
        wanted = {
            "sides": (short_dir,), "top_bottom": (long_dir,), "both": (short_dir, long_dir),
        }.get(locations, (short_dir,))
        points: list[AccessPoint] = []
        requested = 0
        for direction in wanted:
            requested += 2
            points.extend(_single_axis_points(polygon, direction, representative, resolved_width))
        if not points:
            return NestAccessPlan(
                "none", resolved_width, (), Polygon(),
                "No safe finger opening location was found for the requested sides; "
                "generated without one.",
            )
        warning = (
            "Some requested finger openings did not fit safely on this outline "
            "and were skipped." if len(points) < requested else None
        )
        footprint = unary_union([
            Point(p.position).buffer(resolved_width / 2.0, quad_segs=32) for p in points
        ])
        return NestAccessPlan("finger_grasp", resolved_width, tuple(points), footprint, warning)

    # Automatic: try the short axis, the long axis, then 15-degree increments,
    # in that order, then an irregular-shape fallback, then a single location.
    resolved_width = _automatic_finger_width_for(polygon)
    candidates = [short_dir, long_dir]
    for degrees in range(0, 180, 15):
        radians = math.radians(degrees)
        direction = np.array([math.cos(radians), math.sin(radians)])
        if any(abs(float(np.dot(direction, existing))) > 0.999 for existing in candidates):
            continue
        candidates.append(direction)

    for direction in candidates:
        pair = _axis_pair(polygon, direction, representative, resolved_width)
        if pair is not None:
            footprint = unary_union([
                Point(pair[0].position).buffer(resolved_width / 2.0, quad_segs=32),
                Point(pair[1].position).buffer(resolved_width / 2.0, quad_segs=32),
            ])
            return NestAccessPlan("finger_grasp", resolved_width, pair, footprint, None)

    fallback = _boundary_fallback_pair(polygon, resolved_width, representative)
    if fallback is not None:
        footprint = unary_union([
            Point(fallback[0].position).buffer(resolved_width / 2.0, quad_segs=32),
            Point(fallback[1].position).buffer(resolved_width / 2.0, quad_segs=32),
        ])
        return NestAccessPlan("finger_grasp", resolved_width, fallback, footprint, None)

    length = polygon.exterior.length
    origin = np.array([representative.x, representative.y])
    steps = max(8, int(length // 5.0))
    best_single, best_chord = None, -1.0
    for index in range(steps):
        point = _validate_access_point(polygon, length * index / steps, resolved_width, origin)
        if point is not None and point.chord > best_chord:
            best_single, best_chord = point, point.chord
    if best_single is not None:
        footprint = Point(best_single.position).buffer(resolved_width / 2.0, quad_segs=32)
        return NestAccessPlan(
            "finger_grasp", resolved_width, (best_single,), footprint,
            "Only one finger opening could be placed safely on this outline.",
        )
    return NestAccessPlan(
        "none", resolved_width, (), Polygon(),
        "No safe finger-opening location was found on this outline; generated without one.",
    )


def _legacy_finger_positions(opening: Polygon, position: str) -> list[tuple[float, float]]:
    """The old fixed local-axis crossing placement, preview-only re-creation
    (no tangent/normal, no cutter geometry) so a legacy design's 2D indicator
    still shows roughly where its notches actually fall."""
    min_x, min_y, max_x, max_y = opening.bounds
    inside = opening.representative_point()
    reach = max(max_x - min_x, max_y - min_y) + 10.0
    points: list[tuple[float, float]] = []
    if position in {"sides", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (min_x - reach, inside.y), (max_x + reach, inside.y)
        ]))
        xs = _line_coordinates(crossing, 0)
        if len(xs) >= 2:
            points.append((min(xs), float(inside.y)))
            points.append((max(xs), float(inside.y)))
    if position in {"top_bottom", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (inside.x, min_y - reach), (inside.x, max_y + reach)
        ]))
        ys = _line_coordinates(crossing, 1)
        if len(ys) >= 2:
            points.append((float(inside.x), min(ys)))
            points.append((float(inside.x), max(ys)))
    return points


def nest_access_preview(one: Feature) -> dict | None:
    """Lightweight, informational 2D metadata for the resolved access plan -
    world-space points only; the browser draws no geometry from this."""
    if not one.contour:
        return None
    holder_style = _resolved_holder_style(one)
    legacy = _is_legacy_nest(one)
    assist, locations, width = _resolved_finger_settings(one)
    radians = math.radians(one.rotation)
    cos_r, sin_r = math.cos(radians), math.sin(radians)
    cx, cy = one.zone.centre

    def to_world(local_points: list[tuple[float, float]]) -> list[dict]:
        return [
            {"x": x * cos_r - y * sin_r + cx, "y": x * sin_r + y * cos_r + cy}
            for x, y in local_points
        ]

    if holder_style == "raised_wall":
        tool_thickness = _resolved_tool_thickness(one)
        push_depth = float(one.options.get("push_depth", NEST_PUSH_DEPTH)) if assist == "push_out" else 0.0
        wall_height = tool_thickness + push_depth
        empty = {"style": "none", "holder_style": holder_style, "width": 0.0,
                 "points": [], "warning": None}
        if assist in {"push_out", "none"}:
            return empty
        # Spec section 21: a very low Automatic Raised Wall may resolve to no
        # notch at all - the preview must agree, or it would promise a notch
        # the actual builder never cuts. This rule is new architecture only;
        # a legacy design's old behaviour never skipped for a short wall.
        if not legacy and assist == "auto" and wall_height <= 4.0:
            return empty
        if legacy:
            local_opening = _nest_local_polygon(one, include_clearance=True)
            local_points = _legacy_finger_positions(local_opening, locations)
            return {
                "style": "finger_grasp" if local_points else "none",
                "holder_style": holder_style,
                "width": width if width is not None else NEST_FINGER_WIDTH,
                "points": to_world(local_points),
                "warning": None,
            }

    local = _nest_local_polygon(one, include_clearance=True)
    plan = resolve_nest_access_plan(local, _nest_access_mode(assist), locations, width)
    return {
        "style": plan.style,
        "holder_style": holder_style,
        "width": plan.width,
        "points": to_world([point.position for point in plan.points]),
        "warning": plan.warning,
    }


def _raised_wall_height_for_sizing(one: Feature) -> float:
    """The same effective wall height the builder itself will use - Tool
    thickness, plus Push Out's own deck depth when that assist is active -
    so the footprint used for fitting/auto-sizing never falls short of what
    build_nest actually constructs (spec/finding: Push Out's adaptive
    buttress must be sized from wall_height, not raw tool_thickness)."""
    tool_thickness = _resolved_tool_thickness(one)
    assist, _locations, _width = _resolved_finger_settings(one)
    push_depth = float(one.options.get("push_depth", NEST_PUSH_DEPTH)) if assist == "push_out" else 0.0
    return tool_thickness + push_depth


def nest_required_zone(one: Feature) -> Zone:
    """Tight axis-aligned footprint enclosing the finished holder.

    Raised Wall: the cleared cavity, its wall and its outside foot - the old
    fixed 2 mm foot for a legacy design, the new adaptive buttress for an
    explicit one. Recessed: the cleared cavity together with any finger
    scoops, since a scoop can reach past the plain contour, buffered by the
    structural rim.
    """
    rim = float(one.options.get("rim", 3.0))
    if not math.isfinite(rim) or rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    holder_style = _resolved_holder_style(one)
    if holder_style == "recessed":
        local_cleared = _nest_local_polygon(one, include_clearance=True)
        assist, locations, width = _resolved_finger_settings(one)
        plan = resolve_nest_access_plan(local_cleared, _nest_access_mode(assist), locations, width)
        local_footprint = (
            unary_union([local_cleared, plan.footprint])
            if plan.style == "finger_grasp" and not plan.footprint.is_empty
            else local_cleared
        )
        footprint = affinity.rotate(local_footprint, one.rotation, origin=(0, 0), use_radians=False)
        cx, cy = one.zone.centre
        footprint = affinity.translate(footprint, xoff=cx, yoff=cy)
        outer = footprint.buffer(rim, join_style="round")
    else:
        cavity = nest_contour_polygon(one, include_clearance=True)
        if _is_legacy_nest(one):
            outer_foot = LEGACY_NEST_CHAMFER
        else:
            outer_foot = _raised_wall_outer_foot(_raised_wall_height_for_sizing(one))
        outer = cavity.buffer(rim, join_style="round").buffer(outer_foot, join_style="round")
    min_x, min_y, max_x, max_y = outer.bounds
    return Zone(float(min_x), float(min_y), float(max_x), float(max_y))


def fitted_nest_feature(one: Feature, centre: tuple[float, float] | None = None) -> Feature:
    """Recompute a Photo Nest zone after contour or fit changes."""
    if centre is None:
        centre = one.zone.centre
    cx, cy = centre
    local = replace(one, zone=Zone(-0.5, -0.5, 0.5, 0.5))
    needed = nest_required_zone(local)
    return replace(one, zone=Zone(
        cx - needed.width / 2.0, cy - needed.depth / 2.0,
        cx + needed.width / 2.0, cy + needed.depth / 2.0,
    ))


@defaults("nest")
def nest_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, object]:
    tool_thickness = _resolved_tool_thickness(one)
    holder_style = _resolved_holder_style(one)
    cavity_mode = str(one.options.get("cavity_depth_mode", "auto"))
    cavity_depth = _resolved_cavity_depth(one, tool_thickness)
    assist, locations, width = _resolved_finger_settings(one)
    # A legacy design's own historical default finger width was the fixed
    # 25 mm constant, never the newer tool-relative automatic formula - an
    # old nest that never explicitly stored finger_width must keep exactly
    # the notch size it always had.
    if _is_legacy_nest(one):
        auto_width = NEST_FINGER_WIDTH
    else:
        auto_width = _automatic_finger_width(one) if one.contour else NEST_FINGER_WIDTH
    return {
        "clearance": 0.6,
        "tool_thickness": tool_thickness,
        "rim": 3.0,
        "smoothing": 0.0,
        "holder_style": holder_style,
        "cavity_depth_mode": cavity_mode,
        "cavity_depth": cavity_depth,
        # ``None`` (no stored key at all) means legacy grow-only sizing - a
        # third state distinct from True/False, so it is passed straight
        # through rather than defaulted to either.
        "auto_size": one.options.get("auto_size", None),
        "lift_assist": assist,
        "finger_position": locations,
        "finger_width": width if width is not None else auto_width,
        "push_position": "right",
        "push_area": NEST_PUSH_AREA,
        "push_depth": NEST_PUSH_DEPTH,
    }


def resolve_nest_settings(box: BoxSpec, one: Feature, base_z: float) -> dict[str, object]:
    """Every Photo Nest option as a concrete, legal value - the authoritative
    read used by both geometry generation and the browser's own display, so
    a clamp Python has to apply (a manual cavity depth exceeding a thinner
    Tool thickness, Push Out on a Recessed Cavity) is reported once here
    rather than recomputed differently in each caller."""
    options = dict(resolved_options(box, one, base_z))
    warnings: list[str] = []
    tool_thickness = float(options["tool_thickness"])
    holder_style = str(options["holder_style"])
    if holder_style not in HOLDER_STYLES:
        holder_style = "raised_wall"
    cavity_mode = str(options["cavity_depth_mode"])
    cavity_depth = float(options["cavity_depth"])
    if cavity_mode == "auto":
        cavity_depth = 0.6 * tool_thickness
    elif cavity_depth > tool_thickness:
        cavity_depth = tool_thickness
        warnings.append("Cavity depth was reduced to match the thinner tool thickness.")
    assist = str(options["lift_assist"])
    if assist == "push_out" and holder_style == "recessed":
        assist = "auto"
        warnings.append(
            "Push Out is available only for Raised Wall holders. "
            "Finger access was changed to Automatic."
        )
    options["holder_style"] = holder_style
    options["cavity_depth_mode"] = cavity_mode
    options["cavity_depth"] = cavity_depth
    options["lift_assist"] = assist
    options["warnings"] = warnings
    return options


def clamp_nest_feature_options(one: Feature) -> tuple[Feature, list[str]]:
    """Persist any clamp that would otherwise only be resolved in memory - a
    Manual cavity depth now exceeding a thinner Tool thickness, or Push Out
    left set while switching to Recessed - into the Feature's own stored
    options, with a plain-language warning to show once. Without this, the
    stored (un-clamped) value would spring back the moment Tool thickness
    increases again."""
    if one.kind != "nest" or not one.contour:
        return one, []
    warnings: list[str] = []
    options = dict(one.options)
    tool_thickness = _resolved_tool_thickness(one)
    holder_style = _resolved_holder_style(one)
    cavity_mode = str(options.get("cavity_depth_mode", "auto"))
    if cavity_mode == "manual" and options.get("cavity_depth") is not None:
        stored = float(options["cavity_depth"])
        if math.isfinite(stored) and stored > tool_thickness > 0.0:
            options["cavity_depth"] = tool_thickness
            warnings.append("Cavity depth was reduced to match the thinner tool thickness.")
    default_assist = "finger_grasp" if _is_legacy_nest(one) else "auto"
    assist = str(options.get("lift_assist", default_assist))
    if assist == "push_out" and holder_style == "recessed":
        options["lift_assist"] = "auto"
        warnings.append(
            "Push Out is available only for Raised Wall holders. "
            "Finger access was changed to Automatic."
        )
    if not warnings:
        return one, []
    return replace(one, options=options), warnings


def _nest_transform_mesh(mesh: trimesh.Trimesh, one: Feature) -> trimesh.Trimesh:
    """Rotate a local nest detail with its outline, then place it in the layout."""
    if one.rotation:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(one.rotation), (0.0, 0.0, 1.0)
        ))
    cx, cy = one.zone.centre
    mesh.apply_translation((cx, cy, 0.0))
    return mesh


def _oriented_notch_cutter(
    point: AccessPoint, wall_height: float, width: float, rim: float, base_z: float,
) -> trimesh.Trimesh:
    """One elliptical U-shaped cutter, oriented along one access point's own
    local tangent and punched inward from its outward normal side."""
    horizontal_radius = width / 2.0
    vertical_radius = min(horizontal_radius, wall_height - NEST_FINGER_BOTTOM_SKIN)
    if vertical_radius <= 0.0:
        raise ValueError("Photo Nest wall is too short for a finger grasp")
    reach = rim + NEST_OUTER_FOOT_MAX + 8.0
    centre = (0.0, base_z + wall_height)
    profile = affinity.scale(
        Point(centre).buffer(1.0, quad_segs=32),
        xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
    )
    cutter = _extrude_yz_profile(profile, reach)
    # The cutter now extrudes along world X (the reach), its width along
    # world Y and its height along world Z. Shift so it starts 2 mm inside
    # the boundary and reaches well past the wall, then rotate about Z so
    # that reach direction points along this point's outward normal.
    cutter.apply_translation((reach / 2.0 - 2.0, 0.0, 0.0))
    angle = math.degrees(math.atan2(point.normal[1], point.normal[0]))
    cutter.apply_transform(trimesh.transformations.rotation_matrix(math.radians(angle), (0.0, 0.0, 1.0)))
    cutter.apply_translation((point.position[0], point.position[1], 0.0))
    return cutter


def _legacy_nest_finger_cutters(
    one: Feature, opening: Polygon, wall_height: float, width: float,
    position: str, base_z: float, rim: float,
) -> list[trimesh.Trimesh]:
    """The exact pre-holder_style U-shaped notch placement: fixed local-axis
    crossings through the outline's representative point, not the newer
    tool-relative access planner. Kept unchanged so a legacy design's
    physical geometry never moves."""
    min_x, min_y, max_x, max_y = opening.bounds
    inside = opening.representative_point()
    reach = rim + LEGACY_NEST_CHAMFER + 3.0
    horizontal_radius = width / 2.0
    vertical_radius = min(horizontal_radius, wall_height - NEST_FINGER_BOTTOM_SKIN)
    if vertical_radius <= 0.0:
        raise ValueError("Photo Nest wall is too short for a finger grasp")
    cutters: list[trimesh.Trimesh] = []

    if position in {"sides", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (min_x - reach, inside.y), (max_x + reach, inside.y)
        ]))
        xs = _line_coordinates(crossing, 0)
        if len(xs) < 2:
            raise ValueError("Finger grasps could not find both sides of this outline")
        centre = (float(inside.y), base_z + wall_height)
        profile = affinity.scale(
            Point(centre).buffer(1.0, quad_segs=32),
            xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
        )
        for boundary, direction in ((min(xs), -1.0), (max(xs), 1.0)):
            start = boundary + direction * (rim + LEGACY_NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_yz_profile(profile, abs(end - start))
            cutter.apply_translation(((start + end) / 2.0, 0.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))

    if position in {"top_bottom", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (inside.x, min_y - reach), (inside.x, max_y + reach)
        ]))
        ys = _line_coordinates(crossing, 1)
        if len(ys) < 2:
            raise ValueError("Finger grasps could not find both ends of this outline")
        centre = (float(inside.x), base_z + wall_height)
        profile = affinity.scale(
            Point(centre).buffer(1.0, quad_segs=32),
            xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
        )
        for boundary, direction in ((min(ys), -1.0), (max(ys), 1.0)):
            start = boundary + direction * (rim + LEGACY_NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_xz_profile(profile, abs(end - start))
            cutter.apply_translation((0.0, (start + end) / 2.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))
    return cutters


def _legacy_nest_rounded_wall(
    opening: Polygon, rim: float, height: float, base_z: float,
) -> trimesh.Trimesh:
    """The exact pre-holder_style Raised Wall: a fixed 2 mm outside foot and
    one shared top round, applied to both faces alike. Kept unchanged so a
    legacy design's physical geometry never moves."""
    outer = opening.buffer(rim, join_style="round")
    top_round = min(LEGACY_NEST_TOP_ROUND, rim * 0.4, height * 0.25)
    straight_height = height - top_round
    outside: list[trimesh.Trimesh] = []

    straight = _extrude_polygon(outer, straight_height)
    straight.apply_translation((0.0, 0.0, base_z))
    outside.append(straight)

    chamfer_steps = 8
    layer = LEGACY_NEST_CHAMFER / chamfer_steps
    for index in range(chamfer_steps):
        grow = LEGACY_NEST_CHAMFER - index * layer
        disk = _extrude_polygon(outer.buffer(grow, join_style="round"), layer)
        disk.apply_translation((0.0, 0.0, base_z + index * layer))
        outside.append(disk)

    inside: list[trimesh.Trimesh] = []
    bore = _extrude_polygon(opening, height + 2.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    inside.append(bore)
    top_steps = 8
    layer = top_round / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer
        inset = top_round - math.sqrt(max(0.0, top_round ** 2 - rise ** 2))
        top_outer = outer.buffer(-inset, join_style="round")
        top_inner = opening.buffer(inset, join_style="round")
        if top_outer.is_empty or top_inner.is_empty or not top_outer.contains(top_inner):
            raise ValueError("Outline wall is too thin for its rounded top")
        disk = _extrude_polygon(top_outer, layer)
        disk.apply_translation((0.0, 0.0, base_z + straight_height + index * layer))
        outside.append(disk)
        cut = _extrude_polygon(top_inner, layer + 0.02)
        cut.apply_translation((
            0.0, 0.0, base_z + straight_height + index * layer - 0.01
        ))
        inside.append(cut)
    return difference([union(outside), union(inside)])


def _nest_rounded_wall(
    opening: Polygon, rim: float, height: float, base_z: float,
) -> trimesh.Trimesh:
    """One Raised Wall: an adaptive structural buttress at the floor, a small
    removal-only relief easing the inside base, and a top rounded broader on
    the outside than the inside."""
    outer_foot = _raised_wall_outer_foot(height)
    outer = opening.buffer(rim, join_style="round")
    top_round_outer = min(NEST_TOP_ROUND_OUTER, rim * 0.4, height * 0.25)
    top_round_inner = min(NEST_TOP_ROUND_INNER, rim * 0.4, height * 0.25)
    inside_relief = min(NEST_INSIDE_RELIEF_MAX, rim * 0.3, height * 0.2)
    straight_height = height - top_round_outer
    outside: list[trimesh.Trimesh] = []

    straight = _extrude_polygon(outer, straight_height)
    straight.apply_translation((0.0, 0.0, base_z))
    outside.append(straight)

    # An adaptive 45-degree-or-gentler outside buttress, scaled to the
    # wall's own height rather than a fixed foot.
    foot_steps = 8
    layer = outer_foot / foot_steps
    for index in range(foot_steps):
        grow = outer_foot - index * layer
        disk = _extrude_polygon(outer.buffer(grow, join_style="round"), layer)
        disk.apply_translation((0.0, 0.0, base_z + index * layer))
        outside.append(disk)

    inside: list[trimesh.Trimesh] = []
    bore = _extrude_polygon(opening, height + 2.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    inside.append(bore)

    # A small removal-only relief at the base of the inside face - it only
    # ever widens the opening a little, never narrows the tool's clearance.
    if inside_relief > 0.02:
        relief_steps = 6
        layer = inside_relief / relief_steps
        for index in range(relief_steps):
            grow = inside_relief - index * layer
            disk = _extrude_polygon(opening.buffer(grow, join_style="round"), layer)
            disk.apply_translation((0.0, 0.0, base_z + index * layer))
            inside.append(disk)

    # A fine layered quarter-round eases both top edges - a broader crown
    # outside, a lighter ease inside.
    top_steps = 8
    layer = top_round_outer / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer
        inset = top_round_outer - math.sqrt(max(0.0, top_round_outer ** 2 - rise ** 2))
        top_outer = outer.buffer(-inset, join_style="round")
        if top_outer.is_empty:
            raise ValueError("Outline wall is too thin for its rounded top")
        disk = _extrude_polygon(top_outer, layer)
        disk.apply_translation((0.0, 0.0, base_z + straight_height + index * layer))
        outside.append(disk)

    inner_top_start = height - top_round_inner
    layer_inner = top_round_inner / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer_inner
        inset = top_round_inner - math.sqrt(max(0.0, top_round_inner ** 2 - rise ** 2))
        top_inner = opening.buffer(inset, join_style="round")
        if top_inner.is_empty or not outer.contains(top_inner):
            raise ValueError("Outline wall is too thin for its rounded top")
        cut = _extrude_polygon(top_inner, layer_inner + 0.02)
        cut.apply_translation((0.0, 0.0, base_z + inner_top_start + index * layer_inner - 0.01))
        inside.append(cut)

    return difference([union(outside), union(inside)])


def _nest_push_support(
    one: Feature, opening: Polygon, position: str, area: float,
    depth: float, base_z: float,
) -> trimesh.Trimesh:
    """Raised tool-shaped deck, leaving one selected end low for push-to-lift."""
    min_x, min_y, max_x, max_y = opening.bounds
    fraction = area / 100.0
    if position == "left":
        support = opening.intersection(shapely_box(
            min_x + (max_x - min_x) * fraction, min_y - 1.0,
            max_x + 1.0, max_y + 1.0,
        ))
    elif position == "right":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x - (max_x - min_x) * fraction, max_y + 1.0,
        ))
    elif position == "bottom":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y + (max_y - min_y) * fraction,
            max_x + 1.0, max_y + 1.0,
        ))
    else:  # top
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x + 1.0, max_y - (max_y - min_y) * fraction,
        ))
    if support.is_empty or support.area < opening.area * 0.5:
        raise ValueError("Push area leaves too little of the tool supported")
    deck = _extrude_polygon(support, depth)
    deck.apply_translation((0.0, 0.0, base_z))
    return _nest_transform_mesh(deck, one)


def _nest_recessed_deck(
    footprint: Polygon,
    cavity_depth: float,
    base_z: float,
) -> trimesh.Trimesh:
    """Solid Recessed deck filling the bin/insert's physical usable footprint."""
    deck = _extrude_polygon(footprint, cavity_depth)
    deck.apply_translation((0.0, 0.0, base_z))
    return deck


def _nest_recessed_cavity_cutter(
    world_opening: Polygon, cavity_depth: float, base_z: float,
) -> trimesh.Trimesh:
    """The tool-shaped hole through the deck to the normal printable floor,
    flared at the deck top by the automatic lead-in so the tool drops in
    without catching an edge."""
    lead_in = min(NEST_LEAD_IN_MAX, cavity_depth / 3.0)
    parts: list[trimesh.Trimesh] = []
    straight_height = max(0.02, cavity_depth - lead_in)
    bore = _extrude_polygon(world_opening, straight_height + 1.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    parts.append(bore)
    if lead_in > 0.02:
        flare_steps = 8
        layer = lead_in / flare_steps
        flare_start_z = base_z + max(0.0, cavity_depth - lead_in)
        for index in range(flare_steps):
            grow = lead_in * (index + 1) / flare_steps
            disk = _extrude_polygon(world_opening.buffer(grow, join_style="round"), layer + 0.02)
            disk.apply_translation((0.0, 0.0, flare_start_z + index * layer - 0.01))
            parts.append(disk)
    return union(parts)


def _nest_finger_scoops(
    points: tuple[AccessPoint, ...], radius: float, scoop_z: float,
) -> list[trimesh.Trimesh]:
    """One spherical scoop per resolved access point, in local coordinates -
    the caller places each into the layout with ``_nest_transform_mesh``."""
    scoops = []
    for point in points:
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=radius)
        sphere.apply_translation((point.position[0], point.position[1], scoop_z))
        scoops.append(sphere)
    return scoops


@feature(
    "nest", title="Photo Nest",
    display="Photo Nest — a custom holder built from your photo",
    description="A custom holder built from your photo.",
    capabilities=("photo",),
    options=(
        OptionDefinition("Fit clearance", "clearance", "0.6"),
        OptionDefinition("Soften outline", "smoothing", "0"),
        OptionDefinition("Tool thickness", "tool_thickness", "8", editor=False),
        OptionDefinition("Outline wall", "rim", "", editor=False),
        OptionDefinition("Holder style", "holder_style", "raised_wall", "enum", False),
        OptionDefinition("Cavity depth", "cavity_depth", "", editor=False),
        OptionDefinition("Cavity depth mode", "cavity_depth_mode", "auto", "enum", False),
        OptionDefinition("Automatic footprint sizing", "auto_size", True, "boolean", False),
        OptionDefinition("Finger access", "lift_assist", "auto", "enum", False),
        OptionDefinition("Finger locations", "finger_position", "sides", "enum", False),
        OptionDefinition("Finger width", "finger_width", "25", editor=False),
        OptionDefinition("Push position", "push_position", "right", "enum", False),
        OptionDefinition("Push area", "push_area", "30", editor=False),
        OptionDefinition("Push depth", "push_depth", "4", editor=False),
        OptionDefinition("Photo marker", "photo", False, "boolean", False),
    ), order=20,
)
def build_nest(
    box: BoxSpec,
    spec_feature: Feature,
    base_z: float,
    *,
    deck_footprint: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """A finished holder that traces one photographed outline: a solid
    Recessed Cavity deck by default, or a Raised Wall on request.
    """
    require_measured_tool_thickness(spec_feature)
    options = resolve_nest_settings(box, spec_feature, base_z)
    clearance = options["clearance"]
    tool_thickness = float(options["tool_thickness"])
    rim = options["rim"]
    smoothing = options["smoothing"]
    holder_style = str(options["holder_style"])
    cavity_depth = float(options["cavity_depth"])
    assist = str(options["lift_assist"])
    finger_position = str(options["finger_position"])
    finger_width = float(options["finger_width"])
    push_position = str(options["push_position"])
    push_area = float(options["push_area"])
    push_depth = float(options["push_depth"])
    if not all(math.isfinite(value) for value in (
        clearance, tool_thickness, rim, smoothing, cavity_depth, finger_width, push_area, push_depth
    )):
        raise ValueError("Photo Nest measurements must be finite")
    if clearance < 0.0:
        raise ValueError("Clearance must be zero or greater")
    if rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    if smoothing < 0.0:
        raise ValueError("Soften outline must be zero or greater")
    if tool_thickness <= 0.0:
        raise ValueError("Tool thickness must be greater than zero")
    if assist not in NEST_ASSISTS:
        raise ValueError("Finger access must be Automatic, Off, or Custom")
    if assist == "finger_grasp":
        if finger_position not in NEST_FINGER_POSITIONS:
            raise ValueError("Finger grasp locations must be Sides, Ends, or Both")
        if finger_width < NEST_CUSTOM_WIDTH_MIN or finger_width > NEST_CUSTOM_WIDTH_MAX:
            raise ValueError("Finger opening width must be between 12 and 40 mm")
    if push_position not in NEST_PUSH_POSITIONS:
        raise ValueError("Push position must be left, right, top, or bottom")
    if push_area < 15.0 or push_area > 40.0:
        raise ValueError("Push area must be between 15% and 40%")
    if push_depth < 2.0 or push_depth > 8.0:
        raise ValueError("Push depth must be between 2 and 8 mm")

    local_opening = _nest_local_polygon(spec_feature, include_clearance=True)
    world_opening = nest_contour_polygon(spec_feature, include_clearance=True)
    available = box.z - base_z

    if holder_style == "recessed":
        if cavity_depth <= 0.0:
            raise ValueError("Cavity depth must be greater than zero")
        if cavity_depth > available + 1e-9:
            raise ValueError(
                f"Cavity depth {cavity_depth:g} mm must fit within {available:.1f} mm "
                f"above the printable floor"
            )
        plan = resolve_nest_access_plan(
            local_opening, _nest_access_mode(assist), finger_position, finger_width,
        )
        physical_deck = deck_footprint if deck_footprint is not None else spec_feature.zone.polygon
        deck = _nest_recessed_deck(physical_deck, cavity_depth, base_z)
        cutter = _nest_recessed_cavity_cutter(world_opening, cavity_depth, base_z)
        deck = difference([deck, cutter])
        if plan.style == "finger_grasp":
            scoops = _nest_finger_scoops(plan.points, plan.width / 2.0, base_z + cavity_depth)
            scoops = [_nest_transform_mesh(scoop, spec_feature) for scoop in scoops]
            deck = difference([deck, union(scoops)])
        return [deck]

    # Raised Wall. A design saved before holder_style existed keeps its exact
    # old wall (fixed foot, shared top round) and old finger-cutout placement
    # (fixed local-axis crossings) - only an explicit holder_style opts into
    # the new adaptive buttress and tool-relative access planner.
    legacy = _is_legacy_nest(spec_feature)
    wall_height = tool_thickness + (push_depth if assist == "push_out" else 0.0)
    wall = (
        _legacy_nest_rounded_wall(world_opening, rim, wall_height, base_z) if legacy
        else _nest_rounded_wall(world_opening, rim, wall_height, base_z)
    )

    if assist == "push_out":
        deck = _nest_push_support(
            spec_feature, local_opening, push_position, push_area, push_depth, base_z,
        )
        wall = union([wall, deck])
    elif assist == "none":
        pass
    elif legacy:
        # The old code always attempted a cutout for "finger_grasp" and never
        # had an "auto" state; legacy's own default_assist already maps a
        # missing lift_assist to "finger_grasp" (see _resolved_finger_settings).
        if assist == "finger_grasp":
            cutters = _legacy_nest_finger_cutters(
                spec_feature, local_opening, wall_height, finger_width,
                finger_position, base_z, rim,
            )
            wall = difference([wall, union(cutters)])
    elif assist == "auto" and wall_height <= 4.0:
        pass  # A very low Raised Wall may resolve to no notch - that is valid.
    else:  # "finger_grasp" (Custom), or "auto" on a tall-enough wall.
        plan = resolve_nest_access_plan(
            local_opening, _nest_access_mode(assist), finger_position, finger_width,
        )
        if plan.style == "finger_grasp":
            cutters = [
                _nest_transform_mesh(
                    _oriented_notch_cutter(point, wall_height, plan.width, rim, base_z),
                    spec_feature,
                )
                for point in plan.points
            ]
            wall = difference([wall, union(cutters)])
    return [wall]


register_setting_interactions("nest", (
    SettingInteraction("holder_style", "lift_assist", "auto-adjust", "nest",
                       "Switching to Recessed Cavity turns off Push Out and resolves "
                       "Automatic finger access instead."),
    SettingInteraction("lift_assist", "finger_position", "enable/disable", "nest-editor",
                       "Finger locations are active only for Custom finger access."),
    SettingInteraction("lift_assist", "finger_width", "enable/disable", "nest-editor",
                       "Finger width is active only for Custom finger access."),
    SettingInteraction("lift_assist", "push_position", "enable/disable", "nest-editor",
                       "Push position is active only for Push Out."),
    SettingInteraction("lift_assist", "push_area", "enable/disable", "nest-editor",
                       "Push area is active only for Push Out."),
    SettingInteraction("lift_assist", "push_depth", "enable/disable", "nest-editor",
                       "Push depth is active only for Push Out."),
    SettingInteraction("tool_thickness", "cavity_depth", "auto-adjust", "nest",
                       "Cavity depth recalculates to 60% of tool thickness while it is set to Auto."),
    SettingInteraction("clearance", "zone", "auto-adjust", "nest-sizing",
                       "Fit clearance grows the contour footprint without shrinking the bin."),
    SettingInteraction("rim", "zone", "auto-adjust", "nest-sizing",
                       "Outline wall grows the contour footprint."),
    SettingInteraction("smoothing", "zone", "auto-adjust", "nest-sizing",
                       "Outline smoothing recalculates the fitted contour bounds."),
    SettingInteraction("push_depth", "height", "constraint", "nest",
                       "Push Out adds its deck depth to the required wall height."),
    SettingInteraction("cavity_depth", "height", "constraint", "nest",
                       "Recessed Cavity's deck depth must fit above the printable floor."),
))
