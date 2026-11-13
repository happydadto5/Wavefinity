"""Side Openings: an optional bin-level modifier that cuts centered finger-
access slots through selected bin walls, so a stack of contents (sticky-note
pads, for example) can be gripped and lifted straight out.

This is not an interior part and not a new body architecture. Exactly like
Lid & Stacking, it modifies the bin body itself: the ordinary Wavefinity
shell is built first (outer wall, cavity, floor, wave, lock bumps, any fused
features, the scoop, the rim ledge, Edge Mount), and Side Openings then
subtract negative cutter solids through the selected wall(s). Nothing here
rewrites, forks, or approximates the normal wall/cavity/wave geometry.
"""

from __future__ import annotations

import math

import numpy as np
import trimesh
from shapely.geometry import Polygon

from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    LOCK_TOP_BELOW_RIM,
    SIDE_OPENING_SIDES,
    SIDE_OPENING_WIDTHS,
    WAVE_AMPLITUDE,
    lid_enabled,
)
from organizer_geometry import _extrude_xz_profile, _extrude_yz_profile, difference, union

# A wall shorter than this simply cannot take a Side Opening at all.
SIDE_OPENING_MIN_SIDE_MM = 2.0 * BASE_UNIT       # 14 mm
# Solid corner shoulder kept at each end of an opening, from the Wavefinity
# grid rather than an unrelated magic number.
SIDE_OPENING_CORNER_MARGIN_MM = BASE_UNIT / 2.0  # 3.5 mm
# The fixed continuous bridge Top Support leaves across the top of the wall.
# Deliberately the same 4 mm as the existing lock geometry's upper chamfer.
SIDE_OPENING_TOP_BRIDGE_MM = LOCK_TOP_BELOW_RIM
SIDE_OPENING_ARCH_CURVE = 0.5
SIDE_OPENING_CURVE_SEGMENTS = 32
# Extra slack, beyond the wave's own amplitude, so an extruded cutter fully
# crosses the most-inward and most-outward possible wavy wall surface
# whatever the wall thickness or where the opening lands on the wave.
SIDE_OPENING_BOOLEAN_OVERTRAVEL = 0.5
# How far above the rim an open-top (Top Support off) cutter reaches, so the
# notch is unambiguously open at the top rather than meeting the rim exactly.
SIDE_OPENING_TOP_OVERTRAVEL_MM = 1.0

SIDE_OPENING_WALL_NAME = {"front": "-y", "back": "+y", "left": "-x", "right": "+x"}


def _design_grid(grid: str | None) -> str:
    if grid is None:
        from organizer_inserts._walljoin import BUILD_GRID
        return BUILD_GRID.get()
    from organizer_engine._specs import validate_grid
    return validate_grid(grid)


def gridfinity_opening_refusal(box: BoxSpec, grid: str) -> str:
    """Reject the requested cutter bounds, without resizing or making meshes."""
    from organizer_features.gridfinity import side_opening_limits, nominal_extent
    from organizer_engine._specs import vertical_stack_enabled
    limits = side_opening_limits(box, grid)
    spec = box.side_openings
    _, _, bottom, top = _vertical_geometry(box, spec.from_bottom_percent, spec.from_top_percent, grid)
    if box.edge_mount.active:
        return "Edge Mount is unavailable on Gridfinity: it projects beyond the cell envelope."
    if bottom < limits["floor_z"] - 1e-9:
        return "Side Opening enters the Gridfinity foot zone (4.75 mm) or its base; raise the lower edge."
    rim = limits["rim_depth"] if vertical_stack_enabled(box) and not lid_enabled(box) else 0.0
    if rim and top > box.z - rim + 1e-9:
        return "Side Opening enters the Gridfinity stacking rim zone; lower the upper edge."
    # A nonzero strip left below/above the cut must be at least the chosen wall.
    bottom_strip = bottom - limits["floor_z"]
    top_strip = box.z - rim - top
    if (1e-9 < bottom_strip < box.wall - 1e-9
            or (spec.from_top_percent > 1e-9 or rim) and top_strip < box.wall - 1e-9):
        return "Side Opening leaves a wall segment thinner than the selected wall thickness; move the opening edge."
    extents = nominal_extent(box, grid)
    for side in spec.sides:
        span = extents[0 if side in ("front", "back") else 1]
        shoulder = (span - spec.width_mm) / 2.0
        if shoulder < limits["corner_radius"] - 1e-9:
            return f"Side Opening enters the {side} wall's foot-carrying corner-radius region; choose a smaller opening."
        if shoulder < box.wall - 1e-9:
            return f"Side Opening leaves the {side} wall segment thinner than the selected wall thickness."
    return ""


def side_opening_side_span(box: BoxSpec, side: str, grid: str | None = None) -> float:
    """The wall length a Side Opening's width is measured against.

    Front/Back openings run along X; Left/Right openings run along Y.
    """
    if side not in SIDE_OPENING_SIDES:
        raise ValueError(f"side opening side must be one of {', '.join(SIDE_OPENING_SIDES)}")
    grid = _design_grid(grid)
    if grid != "wavefinity":
        from organizer_features.gridfinity import nominal_extent
        extents = nominal_extent(box, grid)
        return extents[0 if side in ("front", "back") else 1]
    return box.x if side in ("front", "back") else box.y


def _vertical_geometry(
    box: BoxSpec, from_bottom_percent: float, from_top_percent: float, grid: str | None = None,
) -> tuple[float, float, float, float]:
    """``(floor_z, rim_z, bottom_z, top_z)`` for the saved percentages.

    Fix 034 H inset_v2 semantics: 0% means that edge - ``bottom_z`` reaches
    ``floor_z``, ``top_z`` reaches ``rim_z``. A higher percentage pulls that
    edge inward. ``bottom_z`` never goes below ``floor_z``, so a Side Opening
    never removes base material.
    """
    grid = _design_grid(grid)
    if grid != "wavefinity":
        from organizer_features.gridfinity import effective_base
        floor_z = effective_base(box, grid)
    else:
        floor_z = box.base_thickness
    rim_z = box.z
    usable_h = rim_z - floor_z
    bottom_z = floor_z + usable_h * (from_bottom_percent / 100.0)
    top_z = rim_z - usable_h * (from_top_percent / 100.0)
    return floor_z, rim_z, bottom_z, top_z


def _vertical_fits(box: BoxSpec, spec, width_mm: float, grid: str | None = None) -> bool:
    r = width_mm / 2.0
    floor_z, rim_z, bottom_z, top_z = _vertical_geometry(
        box, spec.from_bottom_percent, spec.from_top_percent, grid
    )
    if bottom_z < floor_z - 1e-9:
        return False
    if top_z <= bottom_z + 1e-9:
        return False
    if spec.from_top_percent <= 1e-9:
        if spec.shape == "curved":
            return (rim_z - bottom_z) >= r - 1e-9
        return True
    if spec.shape == "curved":
        return (top_z - bottom_z) >= 2.5 * r - 1e-9
    return (top_z - bottom_z) >= r - 1e-9


def side_opening_allowed_sizes(box: BoxSpec, spec, grid: str | None = None) -> tuple[str, ...]:
    """Size presets that fit every side ``spec.sides`` names, at ``spec``'s
    current shape/depth/top-support combination.

    ``spec.sides`` empty means no wall is chosen yet, so only the vertical
    (shape/depth/top-support) feasibility filters the list.
    """
    grid = _design_grid(grid)
    if grid != "wavefinity":
        from dataclasses import replace
        return tuple(size for size in SIDE_OPENING_WIDTHS
                     if not gridfinity_opening_refusal(replace(box, side_openings=replace(spec, size=size)), grid)
                     and _vertical_fits(box, spec, SIDE_OPENING_WIDTHS[size], grid))
    sides = tuple(spec.sides)
    spans = [side_opening_side_span(box, side, grid) for side in sides]
    allowed = []
    for size in ("small", "medium", "large", "xl"):
        width = SIDE_OPENING_WIDTHS[size]
        if spans and any(
            width > span - 2.0 * SIDE_OPENING_CORNER_MARGIN_MM + 1e-9 for span in spans
        ):
            continue
        if not _vertical_fits(box, spec, width):
            continue
        allowed.append(size)
    return tuple(allowed)


def validate_side_openings(box: BoxSpec, grid: str | None = None) -> None:
    """Deterministic, actionable checks. No-op when Side Openings are off.

    Raises ``ValueError`` on the first problem found, so saved/imported JSON
    can never load an impossible combination silently.
    """
    spec = box.side_openings
    if not spec.enabled:
        return
    grid = _design_grid(grid)
    if grid != "wavefinity":
        refusal = gridfinity_opening_refusal(box, grid)
        if refusal:
            raise ValueError(refusal)
    for side in spec.sides:
        span = side_opening_side_span(box, side, grid)
        if span < SIDE_OPENING_MIN_SIDE_MM - 1e-9:
            raise ValueError(
                f"the {side} side is {span:g} mm, shorter than the "
                f"{SIDE_OPENING_MIN_SIDE_MM:g} mm minimum for a Side Opening"
            )
    width = spec.width_mm
    for side in spec.sides:
        span = side_opening_side_span(box, side, grid)
        if grid == "wavefinity" and width > span - 2.0 * SIDE_OPENING_CORNER_MARGIN_MM + 1e-9:
            raise ValueError(
                f"the {spec.size} ({width:g} mm) Side Opening does not fit the "
                f"{side} wall ({span:g} mm) with its {SIDE_OPENING_CORNER_MARGIN_MM:g} mm "
                "corner shoulders; choose a smaller size or a longer wall"
            )
    if not _vertical_fits(box, spec, width, grid):
        if spec.from_top_percent > 1e-9:
            raise ValueError(
                "the selected percentages leave too little height for this supported "
                "opening; increase the span or choose a smaller opening"
            )
        raise ValueError(
            "the selected percentages leave too little height for a curved opening; "
            "increase the span or choose a smaller opening"
        )
    if box.lift_grabbers.enabled:
        walls = {SIDE_OPENING_WALL_NAME[side] for side in spec.sides}
        if walls & set(box.lift_grabbers.walls):
            raise ValueError(
                "a Side Opening and an Inside Handle cannot share the same wall; "
                "move one to a different wall or turn one off"
            )
    if box.edge_mount.active and box.edge_mount.side in spec.sides:
        raise ValueError(
            "Edge Mount's mounting wall cannot also carry a Side Opening; "
            "choose a different wall for one of them"
        )
    if grid == "wavefinity" and (lid_enabled(box) or box.stack.enabled):
        usable_h = box.z - box.base_thickness
        min_from_top = 100.0 * SIDE_OPENING_TOP_BRIDGE_MM / usable_h
        if spec.from_top_percent < min_from_top - 1e-9:
            raise ValueError(
                "Side Openings need a top bridge while Lid & Stacking is enabled; "
                "raise % from top or disable Lid & Stacking"
            )


def _wall_normal_range(box: BoxSpec, side: str, grid: str) -> tuple[float, float]:
    """The cutter's span across the wall normal, ``(outward, inward)``.

    Overshoots the nominal outer/cavity positions by the wave's own
    amplitude plus a boolean epsilon each way, so the cutter fully crosses
    the real wavy wall surface regardless of where the opening lands on the
    wave, without assuming a flat wall thickness.
    """
    if grid != "wavefinity":
        from organizer_features.gridfinity import nominal_extent
        extents = nominal_extent(box, grid)
        half = extents[1 if side in ("front", "back") else 0] / 2.0
        # Cross the flat wall only; never reach the opposite wall of a small bin.
        slack = min(SIDE_OPENING_BOOLEAN_OVERTRAVEL, (half - box.wall) / 2.0)
        sign = -1 if side in ("front", "left") else 1
        return sign * (half + slack), sign * (half - box.wall - slack)
    slack = WAVE_AMPLITUDE + SIDE_OPENING_BOOLEAN_OVERTRAVEL
    depth = box.wall_depth
    if side == "front":
        return -box.half_y - slack, -box.half_y + depth + slack
    if side == "back":
        return box.half_y + slack, box.half_y - depth - slack
    if side == "left":
        return -box.half_x - slack, -box.half_x + depth + slack
    return box.half_x + slack, box.half_x - depth - slack


def _open_top_profile(shape: str, r: float, bottom_z: float, top_z: float) -> Polygon:
    if shape == "square":
        points = [(-r, top_z), (-r, bottom_z), (r, bottom_z), (r, top_z)]
    else:
        theta = np.linspace(math.pi, 2.0 * math.pi, SIDE_OPENING_CURVE_SEGMENTS + 1)
        arc = [(r * math.cos(t), bottom_z + r + r * math.sin(t)) for t in theta]
        points = [(-r, top_z), *arc, (r, top_z)]
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0.0:
        raise ValueError("invalid side opening profile generated")
    return polygon


def _bridged_profile(shape: str, r: float, bottom_z: float, top_z: float) -> Polygon:
    if shape == "square":
        points = [
            (-r, bottom_z), (r, bottom_z),
            (r, top_z - r),
            (0.0, top_z),
            (-r, top_z - r),
        ]
    else:
        bottom_theta = np.linspace(math.pi, 2.0 * math.pi, SIDE_OPENING_CURVE_SEGMENTS + 1)
        bottom_arc = [
            (r * math.cos(t), bottom_z + r + r * math.sin(t)) for t in bottom_theta
        ]
        roof_x = np.linspace(r, -r, SIDE_OPENING_CURVE_SEGMENTS + 1)
        roof = [
            (float(x), top_z - abs(float(x))
             - SIDE_OPENING_ARCH_CURVE * (float(x) * float(x) / r))
            for x in roof_x
        ]
        points = [*bottom_arc, *roof]
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0.0:
        raise ValueError("invalid side opening profile generated")
    return polygon


def _side_opening_cutter(box: BoxSpec, side: str, grid: str) -> trimesh.Trimesh:
    spec = box.side_openings
    r = spec.width_mm / 2.0
    floor_z, rim_z, bottom_z, top_z = _vertical_geometry(
        box, spec.from_bottom_percent, spec.from_top_percent, grid
    )
    if spec.from_top_percent > 1e-9:
        profile = _bridged_profile(spec.shape, r, bottom_z, top_z)
    else:
        top_open_z = rim_z + SIDE_OPENING_TOP_OVERTRAVEL_MM
        profile = _open_top_profile(spec.shape, r, bottom_z, top_open_z)
    outer, inner = _wall_normal_range(box, side, grid)
    width = abs(outer - inner)
    center = (outer + inner) / 2.0
    if side in ("front", "back"):
        cutter = _extrude_xz_profile(profile, width)
        cutter.apply_translation((0.0, center, 0.0))
    else:
        cutter = _extrude_yz_profile(profile, width)
        cutter.apply_translation((center, 0.0, 0.0))
    cutter.remove_unreferenced_vertices()
    cutter.merge_vertices()
    return cutter


def side_opening_cutters(box: BoxSpec, grid: str | None = None) -> list[trimesh.Trimesh]:
    """One negative cutter solid per selected side. Empty when off."""
    spec = box.side_openings
    if not spec.enabled:
        return []
    grid = _design_grid(grid)
    validate_side_openings(box, grid)
    return [_side_opening_cutter(box, side, grid) for side in spec.sides]


def apply_side_openings(box: BoxSpec, body: trimesh.Trimesh, grid: str | None = None) -> trimesh.Trimesh:
    """Subtract every selected Side Opening from ``body``.

    Callers should apply this to the *completed* bin body - after fused
    features, the scoop, the rim ledge and Edge Mount are already on it - and
    again right before export, so a later body-level operation can never
    quietly fill an opening back in. Returns ``body`` unchanged when Side
    Openings are off. Raises if the requested cut would split the body into
    more than one printable piece.
    """
    spec = box.side_openings
    if not spec.enabled:
        return body
    cutters = side_opening_cutters(box, grid)
    if not cutters:
        return body
    cutter = union(cutters) if len(cutters) > 1 else cutters[0]
    result = difference([body, cutter])
    solids = [one for one in result.split(only_watertight=False) if len(one.faces) > 12]
    if len(solids) != 1:
        raise ValueError(
            "the requested Side Opening(s) split the bin body into more than "
            "one piece; reduce the opening size, change the shape, or choose "
            "different walls"
        )
    result = solids[0]
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    return result


def side_opening_summary(box: BoxSpec, grid: str | None = None) -> dict[str, object]:
    """Authoritative report used by preview/API/debug information."""
    spec = box.side_openings
    if not spec.enabled:
        return {"active": False}
    summary: dict[str, object] = {
        "active": True,
        "shape": spec.shape,
        "sides": list(spec.sides),
        "size": spec.size,
        "width_mm": spec.width_mm,
        "from_bottom_percent": spec.from_bottom_percent,
        "from_top_percent": spec.from_top_percent,
    }
    try:
        validate_side_openings(box, grid)
    except ValueError as error:
        summary["error"] = str(error)
    return summary
