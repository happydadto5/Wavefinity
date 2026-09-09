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
        "height": min(16.0, max(4.0, box.z - base_z - 2.0)),
        "lip": 1.0,
    }


@feature(
    "steps", title="Steps", display="Steps — tiered riser",
    description="Stepped shelves rising from front to back.",
    capabilities=("qty", "size", "along"),
    options=(
        OptionDefinition("Height", "height", ""),
        OptionDefinition("Lip", "lip", "1"),
        OptionDefinition("Count", "count", "3", "integer", False),
    ), order=80,
)
def build_steps(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A stepped stadium-riser platform stepping up across the zone."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    lip = max(0.0, float(options.get("lip", 1.0)))
    count = spec_feature.count or int(options.get("count", 3))

    if count < 1:
        raise ValueError("steps count must be at least 1")
    if height <= 0.0 or base_z + height + lip > box.z + 1e-9:
        raise ValueError("steps height must fit inside the bin")

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

        if lip > 0.0:
            pts.append((u_start, z_tread + lip))
            lip_run = min(lip, step_run * 0.25)
            pts.append((u_start + lip_run, z_tread))
            pts.append((u_end, z_tread))
        else:
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

    return [solid]
