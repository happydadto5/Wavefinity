"""Divider sloped bottoms and support crossbars."""

from __future__ import annotations

import math
import trimesh
from shapely.geometry import Polygon
from organizer_engine import BoxSpec
from organizer_geometry import _extrude_xz_profile, _extrude_yz_profile, intersection
from .._core import Feature, Zone
from .._divider_cells import DividerCell, divider_grid_edges

from ._consts import (
    BOTTOM_SLOPE_MAX,
    BOTTOM_EMBED,
    BOTTOM_CROSSBAR_THICKNESS,
    BOTTOM_CROSSBAR_CHAMFER,
    _option_flag,
)


def _divider_sloped_bottoms(
    box: BoxSpec, spec_feature: Feature, options: dict, along: str,
    centres: list[float], height: float, base_z: float,
    run_splits: list[float] | None = None,
) -> list[trimesh.Trimesh]:
    angle = float(options.get("bottom_angle", 0.0) or 0.0)
    # A saved design may carry the checkbox without the newer angle key.
    # Keep that design visibly sloped using the editor's 20-degree default.
    if angle == 0.0 and _option_flag(options.get("slope_base")):
        if spec_feature.options.get("bottom_angle") in (None, ""):
            angle = 20.0
    if not angle:
        return []
    raw_supports = options.get("bottom_supports", 3)
    supports = (
        int(round(float(raw_supports))) if raw_supports not in (None, "") else 3
    )
    solids = _divider_support_bottoms(
        box, spec_feature.zone, along, centres, height, base_z, angle,
        _option_flag(options.get("reverse_bottom")),
        _option_flag(options.get("alternate_bottom")),
        _option_flag(options.get("minimal_bottom")),
        supports, spec_feature.full_span, run_splits,
    )
    for solid in solids:
        solid.metadata["wavefinity_preview_kind"] = "slope"
    return solids


def _custom_divider_sloped_bottoms(
    box: BoxSpec, spec_feature: Feature, options: dict,
    cells: tuple[DividerCell, ...], rows: int, columns: int,
    height: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """Give each logical rectangle one slope with only its real edge supports."""
    angle = float(options.get("bottom_angle", 0.0) or 0.0)
    if angle == 0.0 and _option_flag(options.get("slope_base")):
        if spec_feature.options.get("bottom_angle") in (None, ""):
            angle = 20.0
    if not angle:
        return []
    raw_supports = options.get("bottom_supports", 3)
    supports = int(round(float(raw_supports))) if raw_supports not in (None, "") else 3
    reverse = _option_flag(options.get("reverse_bottom"))
    alternate = _option_flag(options.get("alternate_bottom"))
    minimal = _option_flag(options.get("minimal_bottom"))
    along = spec_feature.along if spec_feature.along in ("x", "y") else "x"
    x_edges, y_edges = divider_grid_edges(spec_feature.zone, columns - 1, rows - 1)
    solids: list[trimesh.Trimesh] = []
    for index, cell in enumerate(cells):
        slope_zone = Zone(
            x_edges[cell.column], y_edges[cell.row],
            x_edges[cell.column_end], y_edges[cell.row_end],
        )
        if along == "x":
            edge_walls = (
                cell.row > 0 or spec_feature.full_span,
                cell.row_end < rows or spec_feature.full_span,
            )
            wall_extensions = (
                cell.row == 0 and spec_feature.full_span,
                cell.row_end == rows and spec_feature.full_span,
            )
        else:
            edge_walls = (
                cell.column > 0 or spec_feature.full_span,
                cell.column_end < columns or spec_feature.full_span,
            )
            wall_extensions = (
                cell.column == 0 and spec_feature.full_span,
                cell.column_end == columns and spec_feature.full_span,
            )
        pieces = _divider_support_bottoms(
            box, slope_zone, along, [], height, base_z, angle,
            reverse ^ (alternate and index % 2 == 1), False, minimal,
            supports, False, None, edge_walls, wall_extensions,
        )
        for solid in pieces:
            solid.metadata["wavefinity_preview_kind"] = "slope"
        solids.extend(pieces)
    return solids


def _bottom_slot_bounds(
    zone: Zone, along: str, centres: Iterable[float],
) -> list[tuple[float, float]]:
    """The N+1 tool slots a divider's N wall centres cut its zone into.

    Boundaries are the wall centres plus the zone's own two cross-axis edges
    (see the task's "slot boundaries from the divider centers and the divider
    zone's two cross-axis boundaries"), ordered low to high so ``Alternate
    slopes`` can walk them in a stable order.
    """
    if along == "x":
        edges = sorted([zone.y0, *centres, zone.y1])
    else:
        edges = sorted([zone.x0, *centres, zone.x1])
    return [(edges[index], edges[index + 1]) for index in range(len(edges) - 1)]


def _bottom_plane_z(r: float, r0: float, r1: float, rise: float,
                    base_z: float, reverse: bool) -> float:
    """Height of the theoretical sloped plane at run coordinate ``r``.

    Low end at ``base_z`` (the existing support surface); the high end
    ``rise`` above it, toward +run unless ``reverse`` flips it toward -run.
    """
    frac = (r - r0) / (r1 - r0)
    return base_z + (1.0 - frac if reverse else frac) * rise


def _extrude_bottom(
    profile: Polygon, along: str, cross_lo: float, cross_hi: float,
) -> trimesh.Trimesh:
    """Extrude a ``(run, z)`` profile across one slot's cross-axis span.

    The shape varies along the run, so - unlike a divider wall, whose section
    is constant along its length - the profile is the run/z plane and the
    extrusion is across the slot width.
    """
    width = cross_hi - cross_lo
    centre = (cross_lo + cross_hi) / 2.0
    if along == "x":
        solid = _extrude_xz_profile(profile, width)
        solid.apply_translation((0.0, centre, 0.0))
    else:
        solid = _extrude_yz_profile(profile, width)
        solid.apply_translation((centre, 0.0, 0.0))
    return solid


def _divider_support_bottoms(
    box: BoxSpec, zone: Zone, along: str, centres: list[float], height: float,
    base_z: float, angle: float, reverse: bool, alternate: bool,
    minimal: bool, supports: int, full_span: bool = False,
    run_splits: list[float] | None = None,
    cross_edge_walls: tuple[bool, bool] | None = None,
    cross_wall_extensions: tuple[bool, bool] | None = None,
) -> list[trimesh.Trimesh]:
    """Sloped support under each tool slot so a tool rests tilted, not flat.

    ``angle`` is signed: positive rises along the divider/tool direction - +X
    (to the right) for a divider that runs along x, +Y (to the back) along y -
    and negative rises the other way, toward the left or front. ``reverse``
    flips that whole pattern once more (kept for older saved designs that set
    it as a separate flag); ``alternate`` flips every second slot, ordered
    across the divider zone. A full bottom is one continuous wedge per slot;
    ``minimal`` replaces it with ``supports`` evenly spaced crossbars and uses
    materially less plastic.

    A crossbar hangs off the walls at the height it carries the tool, never
    reaching the floor. Its underside is an inverted V: a 45-degree corbel
    grows inward from the wall on each side of the slot until the two meet at
    a central ridge, and a full bar rides the slope on top of that ridge. The
    whole underside is at 45 degrees and the top faces up, so it prints with
    no support. Where the corbels have no room to meet before the floor - a
    wide slot, or a crossbar down near the low end of the slope - or the slot
    has no wall to hang from (an open end of a divider set into bare floor,
    never a ``full_span`` divider, which has the bin's own side walls), it
    falls back to a floor-standing stem with 45-degree gusset feet. The normal
    bin or insert floor is untouched; this is only the material above it.
    Solids sink ``BOTTOM_EMBED`` into the floor (or into a wall) for a clean
    union.
    """
    if not math.isfinite(angle) or abs(angle) > BOTTOM_SLOPE_MAX:
        raise ValueError(
            f"the slope must be within {BOTTOM_SLOPE_MAX:g} degrees either way; "
            "reduce the slope"
        )
    if angle == 0.0:
        return []
    # A negative slope just points the rise the other way - same wedge,
    # mirrored - so fold its sign into ``reverse`` and work with a magnitude.
    reverse = bool(reverse) ^ (angle < 0.0)
    angle = abs(angle)
    if minimal and supports < 1:
        raise ValueError("number of crossbars must be a positive whole number")
    run = zone.width if along == "x" else zone.depth
    r0, r1 = (zone.x0, zone.x1) if along == "x" else (zone.y0, zone.y1)
    # A grid divider crosses the run with perpendicular walls. Split the run at
    # those wall centres so every cell between them carries its own ramp,
    # starting again from the floor, instead of one ramp sweeping unbroken from
    # one end of the zone to the other. With no splits this is a single segment
    # spanning the whole run - exactly the legacy single-direction behaviour.
    splits = sorted(s for s in (run_splits or []) if r0 + 1e-6 < s < r1 - 1e-6)
    seg_bounds = [r0, *splits, r1]
    segments = list(zip(seg_bounds, seg_bounds[1:]))
    rise = max(hi - lo for lo, hi in segments) * math.tan(math.radians(angle))
    if rise > height + 1e-6 or base_z + rise > box.z + 1e-6:
        raise ValueError(
            "the bottom slope's high end rises past the divider height or the "
            "bin: reduce the bottom slope, shorten the run, or increase the "
            "bin height"
        )
    half_t = BOTTOM_CROSSBAR_THICKNESS / 2.0
    bar_min = 0.8                  # thinnest the "full bar" above the ridge may be
    edge_lo, edge_hi = (zone.y0, zone.y1) if along == "x" else (zone.x0, zone.x1)
    wall_line = box.half_y if along == "x" else box.half_x
    solids: list[trimesh.Trimesh] = []
    for index, (c_lo, c_hi) in enumerate(_bottom_slot_bounds(zone, along, centres)):
        flip = reverse ^ (alternate and index % 2 == 1)
        # Each run segment is one compartment's ramp, rising over its own length.
        for seg_r0, seg_r1 in segments:
            seg_run = seg_r1 - seg_r0
            seg_rise = seg_run * math.tan(math.radians(angle))
            if not minimal:
                if not flip:
                    pts = [(seg_r0, base_z - BOTTOM_EMBED), (seg_r1, base_z - BOTTOM_EMBED),
                           (seg_r1, base_z + seg_rise), (seg_r0, base_z)]
                else:
                    pts = [(seg_r0, base_z - BOTTOM_EMBED), (seg_r1, base_z - BOTTOM_EMBED),
                           (seg_r1, base_z), (seg_r0, base_z + seg_rise)]
                solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
                continue
            # Which side of this slot has a wall to hang a crossbar from. A
            # full-span divider always does on both sides (its own wall, and the
            # bin's); a bare-floor divider's outermost slot has an open end.
            lo_is_edge = math.isclose(c_lo, edge_lo, abs_tol=1e-6)
            hi_is_edge = math.isclose(c_hi, edge_hi, abs_tol=1e-6)
            if cross_edge_walls is None:
                lo_has_wall = full_span or not lo_is_edge
                hi_has_wall = full_span or not hi_is_edge
            else:
                lo_has_wall, hi_has_wall = cross_edge_walls
            floating = lo_has_wall and hi_has_wall
            # Weld a floating crossbar into the bin's side wall where the slot
            # ends at the zone edge instead of at a divider wall.
            extend_lo, extend_hi = cross_wall_extensions or (
                lo_is_edge and full_span, hi_is_edge and full_span,
            )
            span_lo = -wall_line if extend_lo else c_lo
            span_hi = wall_line if extend_hi else c_hi
            span_mid = (span_lo + span_hi) / 2.0
            half_span = (span_hi - span_lo) / 2.0
            for step in range(supports):
                centre = seg_r0 + (step + 1) * seg_run / (supports + 1)
                z_left = _bottom_plane_z(centre - half_t, seg_r0, seg_r1, seg_rise, base_z, flip)
                z_right = _bottom_plane_z(centre + half_t, seg_r0, seg_r1, seg_rise, base_z, flip)
                low = min(z_left, z_right)
                # A floating crossbar is a 45-degree corbel growing inward from
                # the wall on each side of the slot; the two meet at a central
                # ridge and a full bar rides the slope on top of it. Its whole
                # underside is at 45 degrees so it prints support-free, and it
                # never reaches the floor. That needs head-room: the corbels
                # climb half the slot's width to meet. Where there isn't room -
                # a wide slot, or a crossbar down near the low end of the slope
                # - fall back to the old floor-standing stem, which prints fine
                # on its own gusset feet.
                z_ridge = low - bar_min
                z_base = z_ridge - half_span
                if not (floating and z_base >= base_z - BOTTOM_EMBED - 1e-9):
                    top_left = max(z_left, base_z + 0.2)
                    top_right = max(z_right, base_z + 0.2)
                    # 45-degree gusset feet, never taller than the stem they brace.
                    chamfer = max(0.0, min(BOTTOM_CROSSBAR_CHAMFER,
                                           top_left - base_z - 0.1,
                                           top_right - base_z - 0.1))
                    pts = [
                        (centre - half_t - chamfer, base_z - BOTTOM_EMBED),
                        (centre + half_t + chamfer, base_z - BOTTOM_EMBED),
                        (centre + half_t, base_z + chamfer),
                        (centre + half_t, top_right),
                        (centre - half_t, top_left),
                        (centre - half_t, base_z + chamfer),
                    ]
                    solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
                    continue
                # Inverted-V underside spanning wall to wall, capped by the slope.
                z_ceiling = max(z_left, z_right) + 5.0
                v_profile = Polygon([
                    (span_lo, z_base), (span_mid, z_ridge), (span_hi, z_base),
                    (span_hi, z_ceiling), (span_lo, z_ceiling),
                ])
                cap_profile = Polygon([
                    (centre - half_t, z_base - 5.0), (centre + half_t, z_base - 5.0),
                    (centre + half_t, z_right), (centre - half_t, z_left),
                ])
                if along == "x":
                    under = _extrude_yz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                    under.apply_translation((centre, 0.0, 0.0))
                    cap = _extrude_xz_profile(cap_profile, span_hi - span_lo)
                    cap.apply_translation((0.0, span_mid, 0.0))
                else:
                    under = _extrude_xz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                    under.apply_translation((0.0, centre, 0.0))
                    cap = _extrude_yz_profile(cap_profile, span_hi - span_lo)
                    cap.apply_translation((span_mid, 0.0, 0.0))
                bar = intersection([under, cap])
                if bar.faces.shape[0] == 0:
                    continue
                solids.append(bar)
    return solids
