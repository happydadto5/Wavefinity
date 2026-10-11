"""Steps feature defaults and geometry."""

from __future__ import annotations

import trimesh
from shapely.geometry import Polygon

from organizer_engine import BoxSpec
from organizer_geometry import _extrude_xz_profile, _extrude_yz_profile

from ._core import Feature
from ._registry import OptionDefinition, defaults, feature, resolved_options


@defaults("steps")
def steps_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {
        "height": max(4.0, (box.z - base_z) / 2.0),
    }


@feature(
    "steps", title="Steps", display="Steps — tiered riser",
    description="Stepped shelves rising from front to back.",
    capabilities=("qty", "size", "along"),
    options=(
        OptionDefinition("Step height", "height", "", minimum=0.1, note="mm of the tallest step; blank = half the bin height"),
        OptionDefinition("Count", "count", "3", "integer", False, minimum=1, note="number of steps"),
    ), order=80,
)
def build_steps(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A stepped stadium-riser platform stepping up across the zone."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    count = spec_feature.count or int(options.get("count", 3))

    if count < 1:
        raise ValueError("steps count must be at least 1")
    if height <= 0.0:
        raise ValueError("steps height must be positive")

    along = spec_feature.along
    if along == "x":
        span = zone.depth
        width = zone.width
        u0, u1 = zone.y0, zone.y1
    else:
        span = zone.width
        width = zone.depth
        u0, u1 = zone.x0, zone.x1

    step_run = span / count
    step_rise = height / count

    pts = [(u0, base_z)]
    for i in range(count):
        u_start = u0 + i * step_run
        u_end = u0 + (i + 1) * step_run
        z_tread = base_z + (i + 1) * step_rise

        pts.append((u_start, z_tread))
        pts.append((u_end, z_tread))

    pts.append((u1, base_z))

    poly = Polygon(pts)
    if not poly.is_valid:
        raise ValueError("invalid step profile generated")

    if along == "x":
        solid = _extrude_yz_profile(poly, width)
        solid.apply_translation((zone.centre[0], 0.0, 0.0))
    else:
        solid = _extrude_xz_profile(poly, width)
        solid.apply_translation((0.0, zone.centre[1], 0.0))

    _wj_solids = [solid]
    from ._walljoin import (
        _join_tabs, _tab_meshes, _footprint_from_solids, _joined_sides,
    )
    from ._bore._consts import JOIN_BAND, WALL_JOIN_FLAG
    if spec_feature.options.get(WALL_JOIN_FLAG):
        # Fuse the steps into the wall at their high end only. The staircase
        # rises from the low end (at base_z) to the high end (at full height);
        # a full-height tab at the low end would bury the low steps. The high
        # end meets the wall at full height, so the tab matches the part.
        # along="x": steps rise along y from front (low) to back (high).
        # along="y": steps rise along x from left (low) to right (high).
        # Keep-clear: empty (treads are horizontal; tabs are vertical at the wall).
        _wj_material = _footprint_from_solids(_wj_solids)
        _wj_keep_clear = Polygon()  # empty
        _wj_tabs = _join_tabs(
            box, _wj_material, _wj_keep_clear, JOIN_BAND,
            sides=_joined_sides(box, _wj_material, "steps", along),
        )
        _wj_solids.extend(_tab_meshes(_wj_tabs, height, base_z))
    return _wj_solids
