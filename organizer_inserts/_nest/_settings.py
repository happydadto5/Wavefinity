"""Nest previews, sizing, defaults and settings resolution."""

from __future__ import annotations

import math
from dataclasses import replace
from shapely import affinity
from shapely.geometry import Polygon
from shapely.ops import unary_union
from organizer_engine import BoxSpec
from .._core import Feature, Zone
from .._registry import defaults, resolved_options

from ._base import (
    HOLDER_STYLES,
    LEGACY_NEST_CHAMFER,
    NEST_FINGER_WIDTH,
    NEST_PUSH_AREA,
    NEST_PUSH_DEPTH,
    NestOccurrence,
    _nest_local_polygon,
    _is_legacy_nest,
    _resolved_tool_thickness,
    _resolved_holder_style,
    _resolved_cavity_depth,
    _resolved_finger_settings,
    _nest_access_mode,
    _automatic_finger_width,
    _raised_wall_outer_foot,
    nest_quantity,
    nest_repeat_spacing_percent,
    nest_repeat_gap,
)
from ._access import resolve_nest_access_plan, _legacy_finger_positions


def nest_access_preview(one: Feature) -> dict | None:
    """Lightweight, informational 2D metadata for the resolved access plan -
    world-space points only; the browser draws no geometry from this."""
    if not one.contour:
        return None
    holder_style = _resolved_holder_style(one)
    legacy = _is_legacy_nest(one)
    assist, locations, width = _resolved_finger_settings(one)
    def to_world(local_points: list[tuple[float, float]], occurrence: NestOccurrence) -> list[dict]:
        radians = math.radians(occurrence.rotation)
        cos_r, sin_r = math.cos(radians), math.sin(radians)
        return [
            {"x": x * cos_r - y * sin_r + occurrence.x,
             "y": x * sin_r + y * cos_r + occurrence.y}
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
                "points": [point for occurrence in nest_occurrences(one)
                           for point in to_world(local_points, occurrence)],
                "warning": None,
            }

    local = _nest_local_polygon(one, include_clearance=True)
    plan = resolve_nest_access_plan(local, _nest_access_mode(assist), locations, width)
    return {
        "style": plan.style,
        "holder_style": holder_style,
        "width": plan.width,
        "points": [point for occurrence in nest_occurrences(one)
                   for point in to_world([point.position for point in plan.points], occurrence)],
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


def _nest_single_required_footprint(one: Feature, rotation: float) -> Polygon:
    """The exact local finished-holder envelope before group placement."""
    rim = float(one.options.get("rim", 3.0))
    if not math.isfinite(rim) or rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    local_cleared = _nest_local_polygon(one, include_clearance=True)
    if _resolved_holder_style(one) == "recessed":
        assist, locations, width = _resolved_finger_settings(one)
        plan = resolve_nest_access_plan(local_cleared, _nest_access_mode(assist), locations, width)
        footprint = unary_union([local_cleared, plan.footprint]) if (
            plan.style == "finger_grasp" and not plan.footprint.is_empty
        ) else local_cleared
        outer = footprint.buffer(rim, join_style="round")
    else:
        outer_foot = LEGACY_NEST_CHAMFER if _is_legacy_nest(one) else _raised_wall_outer_foot(
            _raised_wall_height_for_sizing(one)
        )
        outer = local_cleared.buffer(rim, join_style="round").buffer(outer_foot, join_style="round")
    return affinity.rotate(outer, rotation, origin=(0, 0), use_radians=False)


def nest_occurrences(one: Feature) -> tuple[NestOccurrence, ...]:
    """Derive one straight row while retaining safe finished-envelope gaps."""
    quantity = nest_quantity(one)
    base_rotation = float(one.rotation)
    base = _nest_single_required_footprint(one, base_rotation)
    min_x, min_y, max_x, max_y = base.bounds
    axis_x = (max_x - min_x) <= (max_y - min_y)
    gap = nest_repeat_gap(one)
    raw: list[tuple[int, float, float, float, Polygon]] = []
    previous = None
    for index in range(quantity):
        rotation = (base_rotation + (180.0 if one.alternate_ends and index % 2 else 0.0)) % 360.0
        footprint = _nest_single_required_footprint(one, rotation)
        lo_x, lo_y, hi_x, hi_y = footprint.bounds
        if previous is None:
            x = y = 0.0
        elif axis_x:
            x = previous[1] + previous[4].bounds[2] - lo_x + gap
            y = 0.0
        else:
            x = 0.0
            y = previous[2] + previous[4].bounds[3] - lo_y + gap
        raw.append((index, x, y, rotation, footprint))
        previous = raw[-1]
    joined = unary_union([affinity.translate(footprint, xoff=x, yoff=y)
                          for _index, x, y, _rotation, footprint in raw])
    lo_x, lo_y, hi_x, hi_y = joined.bounds
    correction_x, correction_y = -(lo_x + hi_x) / 2.0, -(lo_y + hi_y) / 2.0
    cx, cy = one.zone.centre
    return tuple(NestOccurrence(index, x + correction_x + cx, y + correction_y + cy, rotation)
                 for index, x, y, rotation, _footprint in raw)


def nest_occurrence_preview(one: Feature) -> list[dict[str, float]]:
    return [{"index": occurrence.index, "x": round(occurrence.x, 6),
             "y": round(occurrence.y, 6), "rotation": round(occurrence.rotation, 6)}
            for occurrence in nest_occurrences(one)]


def nest_required_zone(one: Feature) -> Zone:
    """Tight axis-aligned footprint enclosing the finished holder.

    Raised Wall: the cleared cavity, its wall and its outside foot - the old
    fixed 2 mm foot for a legacy design, the new adaptive buttress for an
    explicit one. Recessed: the cleared cavity together with any finger
    scoops, since a scoop can reach past the plain contour, buffered by the
    structural rim.
    """
    outer = unary_union([
        affinity.translate(_nest_single_required_footprint(one, occurrence.rotation),
                           xoff=occurrence.x, yoff=occurrence.y)
        for occurrence in nest_occurrences(one)
    ])
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
        "repeat_spacing_percent": nest_repeat_spacing_percent(one),
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
