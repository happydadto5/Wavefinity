"""Nest constants, outlines and quantity/spacing helpers."""

from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np
from shapely import affinity
from shapely.geometry import Polygon
from .._core import Feature


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
NEST_REPEAT_AUTO_GAP = 2.0
NEST_REPEAT_SPACING_CHOICES = frozenset({-100, -75, -50, -25, 0, 25, 50, 75, 100})
NEST_REPEAT_MAX = 20


@dataclass(frozen=True)
class NestOccurrence:
    """One derived copy of a saved Photo Nest group."""
    index: int
    x: float
    y: float
    rotation: float


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


def _nest_occurrence_opening(one: Feature, occurrence: NestOccurrence) -> Polygon:
    """One softened, scaled opening at its derived world transform."""
    opening = _nest_local_polygon(one, include_clearance=True)
    opening = affinity.rotate(opening, occurrence.rotation, origin=(0, 0), use_radians=False)
    return affinity.translate(opening, xoff=occurrence.x, yoff=occurrence.y)


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


def nest_quantity(one: Feature) -> int:
    quantity = 1 if one.count is None else int(one.count)
    if quantity < 1 or quantity > NEST_REPEAT_MAX:
        raise ValueError("Photo Nest Quantity must be between 1 and 20")
    return quantity


def nest_repeat_spacing_percent(one: Feature) -> int:
    raw = one.options.get("repeat_spacing_percent", 0)
    try:
        number = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("Photo Nest spacing must be a whole-number preset") from error
    if not math.isfinite(number) or abs(number - round(number)) > 1e-9:
        raise ValueError("Photo Nest spacing must be a whole-number preset")
    value = int(round(number))
    if value not in NEST_REPEAT_SPACING_CHOICES:
        raise ValueError(
            "Photo Nest spacing must be Minimum, -75%, -50%, -25%, Auto, +25%, +50%, +75%, or +100%"
        )
    return value


def nest_repeat_gap(one: Feature) -> float:
    return NEST_REPEAT_AUTO_GAP * (1.0 + nest_repeat_spacing_percent(one) / 100.0)
