"""Pocket feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from organizer_engine import (
    BoxSpec, WAVE_AMPLITUDE, WAVE_LENGTH, wall_depth_for, wave_value,
)
from organizer_geometry import _extrude_polygon, difference, union

from ._core import Feature
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)


POCKET_CHAMFER = 0.5       # 45-degree chamfer on pocket outside edges for strength
POCKET_FLOOR = 2.0         # solid floor thickness under a pocket recess
WAVE_NOISE_FLOOR = 1e-4


def pocket_wall_reach(wall: float, style: str) -> float:
    """One outward envelope for both the editor's inside size and the shell."""
    return (2.0 * WAVE_AMPLITUDE + wall_depth_for(wall) + WAVE_NOISE_FLOOR
            if style == "wavy" else wall)


def _wavy_clear_outline(hx: float, hy: float, cx: float, cy: float) -> Polygon:
    """The clear rectangle only gains space; phase follows world X/Y."""
    points = []
    corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
    for start, end, normal in zip(corners, corners[1:] + corners[:1],
                                   ((0, -1), (1, 0), (0, 1), (-1, 0))):
        length = math.dist(start, end)
        steps = max(2, math.ceil(length / (WAVE_LENGTH / 8)))
        for index in range(steps + 1):
            t = index / steps
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            run = (x + cx) if normal[1] else (y + cy)
            push = WAVE_AMPLITUDE + wave_value(run) + WAVE_NOISE_FLOOR
            points.append((x + normal[0] * push, y + normal[1] * push))
    outline = Polygon(points)
    if not outline.is_valid:
        raise ValueError("pocket wavy wall profile could not be built")
    return outline


@defaults("pocket")
def pocket_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    available_height = box.z - base_z
    if box.z <= 20.0:
        target_height = box.z
    else:
        target_height = max(20.0, round(0.40 * box.z, 1))
    default_height = min(available_height, target_height)
    height = one.options.get("height", default_height)
    if "depth" in one.options and "height" not in one.options:
        height = max(height, one.options["depth"] + POCKET_FLOOR)
    wall = one.options.get("wall", 1.6)
    zone = one.zone
    side = min(zone.width, zone.depth)
    default_rounding = round(max(0.0, min(side * 0.05, wall - 0.4)), 1)
    return {
        "wall_style": "straight",
        "height": default_height,
        "wall": 1.6,
        "depth": max(0.1, height - POCKET_FLOOR),
        "rounding": default_rounding,
    }


@feature(
    "pocket", title="Pocket", display="Pocket — loose small parts",
    description="A raised open tray for loose small parts.",
    capabilities=("size",),
    options=(
        OptionDefinition("Height", "height", "12"),
        OptionDefinition("Wall", "wall", "1.6"),
        OptionDefinition("Walls", "wall_style", "straight", "enum"),
        OptionDefinition("Recess", "depth", ""),
        OptionDefinition("Rounding", "rounding", "", editor=False),
    ), order=50, palette_visible=False,
)
def build_pocket(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A raised block with a rectangular recess in it, chamfered on outside edges for strength."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    wall = options["wall"]
    style = str(options.get("wall_style", "straight"))
    if style not in {"straight", "wavy"}:
        raise ValueError("pocket walls must be straight or wavy")
    reach = pocket_wall_reach(wall, style)
    depth = options.get("depth", max(0.1, height - POCKET_FLOOR))
    rounding = max(0.0, options.get("rounding", 0.0))
    if (height <= 0.0 or wall <= 0.0 or depth <= 0.0 or depth >= height
            or 2 * reach >= zone.width or 2 * reach >= zone.depth):
        raise ValueError("pocket wall and depth must leave a positive shell")
    centre_x, centre_y = zone.centre
    c = min(POCKET_CHAMFER, wall / 2.0, zone.width / 4.0, zone.depth / 4.0)
    w, d = zone.width, zone.depth
    hx, hy = w / 2.0, d / 2.0
    pts = [
        (-hx + c, -hy), (hx - c, -hy),
        (hx, -hy + c), (hx, hy - c),
        (hx - c, hy), (-hx + c, hy),
        (-hx, hy - c), (-hx, -hy + c),
    ]
    inner_w = zone.width - 2 * reach
    inner_d = zone.depth - 2 * reach
    inner_hx, inner_hy = inner_w / 2.0, inner_d / 2.0
    if style == "wavy":
        inner_poly = _wavy_clear_outline(inner_hx, inner_hy, centre_x, centre_y)
        poly = inner_poly.buffer(wall_depth_for(wall), join_style="round")
    else:
        poly = Polygon(pts)
        inner_poly = Polygon([
            (-inner_hx, -inner_hy), (inner_hx, -inner_hy),
            (inner_hx, inner_hy), (-inner_hx, inner_hy),
        ])
    column = _extrude_polygon(poly, height)
    column.apply_translation((centre_x, centre_y, base_z))
    block = [column]
    if c > 0.0 and height > c:
        steps = 4
        layer = c / steps
        for index in range(steps):
            grow = c * (steps - index) / steps
            foot = _extrude_polygon(poly.buffer(
                grow, join_style="round" if style == "wavy" else "mitre"), layer)
            foot.apply_translation((centre_x, centre_y, base_z + index * layer))
            block.append(foot)
    outer_solid = union(block) if len(block) > 1 else column
    cavity_parts = []
    col = _extrude_polygon(inner_poly, depth + 1.0)
    col.apply_translation((centre_x, centre_y, base_z + height - depth))
    cavity_parts.append(col)

    r = min(rounding, wall - 0.2, depth - 0.2, inner_hx - 0.1, inner_hy - 0.1)
    if r > 1e-4:
        steps = 6
        layer = r / steps
        for i in range(steps):
            t = (i + 1) / steps
            grow = r * (1.0 - math.sqrt(max(0.0, 1.0 - t * t)))
            slice_poly = inner_poly.buffer(grow, join_style="round")
            sl = _extrude_polygon(slice_poly, layer)
            sl.apply_translation((centre_x, centre_y, base_z + height - r + i * layer))
            cavity_parts.append(sl)
        top_poly = inner_poly.buffer(r, join_style="round")
        top_cut = _extrude_polygon(top_poly, 2.0)
        top_cut.apply_translation((centre_x, centre_y, base_z + height))
        cavity_parts.append(top_cut)

    inner = union(cavity_parts) if len(cavity_parts) > 1 else col
    pocket = difference([outer_solid, inner])
    return [pocket]


register_setting_interactions("pocket", (
    SettingInteraction("depth", "height", "constraint", "pocket-shell",
                       "A user-edited Recess wins and raises Height to keep a 2 mm floor."),
    SettingInteraction("height", "depth", "constraint", "pocket-shell",
                       "A user-edited Height wins and lowers Recess to keep a 2 mm floor."),
    SettingInteraction("wall", "zone", "auto-adjust", "pocket-sizing",
                       "Wall changes preserve entered inside size by resizing the outside zone."),
    SettingInteraction("zone", "rounding", "default", "pocket",
                       "Automatic rounding follows the smaller pocket side and wall."),
))
