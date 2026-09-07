"""Slot feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh

from organizer_engine import BoxSpec, difference, union

from ._core import Feature
from ._registry import defaults, feature, resolved_options


@defaults("slot")
def slot_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    hole = min(14.0, max(2.0, box.z - base_z - 4.0))
    height = one.options.get("depth", hole) + 2.0
    return {"depth": hole, "thickness": 4.0, "wall": 1.6, "angle": 20.0, "height": height}


@feature("slot")
def build_slot(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of angled, backward-leaning slots for bits, cards, and tools."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    depth, thickness, wall, height = (options["depth"], options["thickness"], options["wall"], options["height"])
    angle = options.get("angle", 20.0)
    if (depth <= 0.0 or thickness <= 0.0 or wall <= 0.0 or height <= 0.0
            or depth >= height or abs(angle) > 45.0):
        raise ValueError("slot depth, thickness, wall and height must be positive, depth must be less than height, and angle <= 45°")
    if base_z + height > box.z + 1e-9:
        raise ValueError("slot height must fit inside the bin")
    along = spec_feature.along
    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width
    if 2.0 * wall >= run or 2.0 * wall >= across:
        raise ValueError("zone is too small for a slot rack with the given wall thickness")
    slot_len = run - 2.0 * wall
    rad, cos_a, sin_a = math.radians(angle), math.cos(math.radians(angle)), math.sin(math.radians(angle))
    pitch = (thickness + wall) / cos_a
    count = spec_feature.count
    if count is None:
        count = max(1, int((across - 2.0 * wall - thickness / cos_a) // pitch) + 1)
    if count < 1:
        raise ValueError(f"no room for slot rack: {across:.1f} mm across needs at least {pitch + 2.0 * wall:.1f} mm")
    used_across = (count - 1) * pitch + (thickness / cos_a) + 2.0 * wall
    if used_across > across + 1e-9:
        raise ValueError(f"{count} slots need {used_across:.1f} mm across but zone gives {across:.1f} mm")
    centre_x, centre_y = zone.centre
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))
    cutter_len = (depth + 4.0) / cos_a
    d_mid = cutter_len / 2.0 - 2.0
    cut_mid_z = base_z + height - d_mid * cos_a
    cut_shift = -d_mid * sin_a
    centre_cross = centre_y if along == "x" else centre_x
    first = centre_cross - ((count - 1) * pitch) / 2.0
    cutters = []
    for i in range(count):
        c_cross = first + i * pitch
        cutter = trimesh.creation.box(extents=(slot_len if along == "x" else thickness, thickness if along == "x" else slot_len, cutter_len))
        cutter.apply_transform(trimesh.transformations.rotation_matrix(rad, (1, 0, 0) if along == "x" else (0, 1, 0)))
        cutter.apply_translation((centre_x, c_cross + cut_shift, cut_mid_z) if along == "x" else (c_cross + cut_shift, centre_y, cut_mid_z))
        cutters.append(cutter)
    return [difference([block, union(cutters) if len(cutters) > 1 else cutters[0]])]
