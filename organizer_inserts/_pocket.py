"""Pocket feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from organizer_engine import BoxSpec
from organizer_geometry import _extrude_polygon, difference, union

from ._core import Feature
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)


POCKET_CHAMFER = 0.5       # 45-degree chamfer on pocket outside edges for strength
POCKET_FLOOR = 2.0         # solid floor thickness under a pocket recess


@defaults("pocket")
def pocket_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    if box.z <= 20.0:
        default_height = box.z
    else:
        default_height = min(box.z, max(20.0, round(0.40 * box.z, 1)))
    height = one.options.get("height", default_height)
    if "depth" in one.options and "height" not in one.options:
        height = max(height, one.options["depth"] + POCKET_FLOOR)
    wall = one.options.get("wall", 1.6)
    zone = one.zone
    side = min(zone.width, zone.depth)
    default_rounding = round(max(0.0, min(side * 0.05, wall - 0.4)), 1)
    return {
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
        OptionDefinition("Recess", "depth", ""),
        OptionDefinition("Rounding", "rounding", "", editor=False),
    ), order=50,
)
def build_pocket(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A raised block with a rectangular recess in it, chamfered on outside edges for strength."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    wall = options["wall"]
    depth = options.get("depth", max(0.1, height - POCKET_FLOOR))
    rounding = max(0.0, options.get("rounding", 0.0))
    if (height <= 0.0 or wall <= 0.0 or depth <= 0.0 or depth >= height
            or 2 * wall >= zone.width or 2 * wall >= zone.depth):
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
    poly = Polygon(pts)
    column = _extrude_polygon(poly, height)
    column.apply_translation((centre_x, centre_y, base_z))
    block = [column]
    if c > 0.0 and height > c:
        steps = 4
        layer = c / steps
        for index in range(steps):
            grow = c * (steps - index) / steps
            foot = _extrude_polygon(poly.buffer(grow, join_style="mitre"), layer)
            foot.apply_translation((centre_x, centre_y, base_z + index * layer))
            block.append(foot)
    outer_solid = union(block) if len(block) > 1 else column
    inner_w = zone.width - 2 * wall
    inner_d = zone.depth - 2 * wall
    inner_hx, inner_hy = inner_w / 2.0, inner_d / 2.0
    inner_poly = Polygon([
        (-inner_hx, -inner_hy), (inner_hx, -inner_hy),
        (inner_hx, inner_hy), (-inner_hx, inner_hy)
    ])
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
