"""Scoop feature defaults, layout zone, and geometry."""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from organizer_engine import (
    BoxSpec,
    SCOOP_CURVE_SEGMENTS,
    SCOOP_HEIGHT_FRACTION,
    _extrude_xz_profile,
    _extrude_yz_profile,
)

from ._core import EDITOR_SNAP, Feature, Zone, layout_zone, snapped_zone
from ._registry import defaults, feature, resolved_options


def scoop_zone(
    box: BoxSpec,
    one: Feature,
    base_z: float,
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Zone:
    """The scoop is always full-width and starts at the front wall."""
    bounds = layout_zone(box, mode)
    try:
        depth_percent = float(one.options.get("depth", 60.0))
    except (TypeError, ValueError):
        depth_percent = 60.0
    height = (box.z - base_z) * depth_percent / 100.0
    run = min(max(height, snap), bounds.depth / 2.0)
    return snapped_zone(
        Zone(bounds.x0, bounds.y0, bounds.x1, bounds.y0 + run),
        box, mode, snap,
    )


@defaults("scoop")
def scoop_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {
        "depth": SCOOP_HEIGHT_FRACTION * 100.0,
    }


@feature("scoop")
def build_scoop(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A full-zone curved retrieval ramp rising up the wall."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    if "depth" in spec_feature.options:
        depth_percent = float(options["depth"])
        if depth_percent <= 0.0 or depth_percent > 100.0:
            raise ValueError("scoop depth must be between 1 and 100 percent")
        height = (box.z - base_z) * depth_percent / 100.0
    else:
        # Keep older saved interior scoops usable. New designs use depth (%).
        height = float(options.get("height", (box.z - base_z) * SCOOP_HEIGHT_FRACTION))
    if height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("scoop height must fit inside the bin")

    along = spec_feature.along
    floor_z = base_z
    centre_z = floor_z + height

    if along == "x":
        wall_y = zone.y0
        run = zone.depth
        inner_y = zone.y1
        curve = [
            (
                inner_y - run * math.cos(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
                centre_z + height * math.sin(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
            )
            for i in range(SCOOP_CURVE_SEGMENTS + 1)
        ]
        profile = Polygon([
            (inner_y, floor_z),
            (wall_y, floor_z),
            (wall_y, centre_z),
            *curve[1:-1],
        ])
        if not profile.is_valid:
            raise ValueError("invalid scoop profile generated")
        solid = _extrude_yz_profile(profile, zone.width)
        solid.apply_translation((zone.centre[0], 0.0, 0.0))
    else:
        wall_x = zone.x0
        run = zone.width
        inner_x = zone.x1
        curve = [
            (
                inner_x - run * math.cos(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
                centre_z + height * math.sin(-math.pi / 2.0 * i / SCOOP_CURVE_SEGMENTS),
            )
            for i in range(SCOOP_CURVE_SEGMENTS + 1)
        ]
        profile = Polygon([
            (inner_x, floor_z),
            (wall_x, floor_z),
            (wall_x, centre_z),
            *curve[1:-1],
        ])
        if not profile.is_valid:
            raise ValueError("invalid scoop profile generated")
        solid = _extrude_xz_profile(profile, zone.depth)
        solid.apply_translation((0.0, zone.centre[1], 0.0))

    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return [solid]
