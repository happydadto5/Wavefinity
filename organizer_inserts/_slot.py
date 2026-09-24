"""Slot feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh
from shapely.geometry import Polygon

from organizer_engine import BoxSpec, WAVE_AMPLITUDE, WAVE_LENGTH, wave_value
from organizer_geometry import _extrude_polygon, difference, union

from ._core import Feature
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)


@defaults("slot")
def slot_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    hole = min(14.0, max(2.0, box.z - base_z - 4.0))
    height = one.options.get("depth", hole) + 2.0
    return {"depth": hole, "thickness": 4.0, "wall": 1.6, "angle": 20.0,
            "height": height, "wall_style": "straight"}


@feature(
    "slot", title="Slot Rack", display="Slot Rack — tilted tools",
    description="Angled slots for driver bits, cards, and small tools.",
    capabilities=("qty", "size", "along"),
    options=(
        OptionDefinition("Height", "height", ""),
        OptionDefinition("Depth", "depth", ""),
        OptionDefinition("Thickness", "thickness", "4"),
        OptionDefinition("Angle °", "angle", "20"),
        OptionDefinition("Wall", "wall", "1.6"),
        OptionDefinition("Walls", "wall_style", "straight", "enum"),
    ), order=70,
)
def build_slot(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of angled, backward-leaning slots for bits, cards, and tools."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    depth, thickness, wall, height = (options["depth"], options["thickness"], options["wall"], options["height"])
    angle = options.get("angle", 20.0)
    style = str(options.get("wall_style", "straight"))
    if style not in {"straight", "wavy"}:
        raise ValueError("slot walls must be straight or wavy")
    wave_margin = WAVE_AMPLITUDE if style == "wavy" else 0.0
    if (depth <= 0.0 or thickness <= 0.0 or wall <= 0.0 or height <= 0.0
            or depth >= height or abs(angle) > 45.0):
        raise ValueError("slot depth, thickness, wall and height must be positive, depth must be less than height, and angle <= 45°")
    along = spec_feature.along
    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width
    if 2.0 * wall >= run or 2.0 * (wall + wave_margin) >= across:
        raise ValueError("zone is too small for a slot rack with the given wall thickness")
    slot_len = run - 2.0 * wall
    rad, cos_a, sin_a = math.radians(angle), math.cos(math.radians(angle)), math.sin(math.radians(angle))
    pitch = (thickness + wall) / cos_a
    count = spec_feature.count
    if count is None:
        count = max(1, int((across - 2.0 * (wall + wave_margin) - thickness / cos_a) // pitch) + 1)
    if count < 1:
        raise ValueError(f"no room for slot rack: {across:.1f} mm across needs at least {pitch + 2.0 * wall:.1f} mm")
    used_across = (count - 1) * pitch + (thickness / cos_a) + 2.0 * (wall + wave_margin)
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
        if style == "wavy":
            steps = max(2, math.ceil(slot_len / (WAVE_LENGTH / 8)))
            runs = [-slot_len / 2.0 + slot_len * j / steps for j in range(steps + 1)]
            centre_run = centre_x if along == "x" else centre_y
            low = [wave_value(run + centre_run) - thickness / 2.0 for run in runs]
            high = [wave_value(run + centre_run) + thickness / 2.0 for run in runs]
            if along == "x":
                outline = [(run, cross) for run, cross in zip(runs, low)] + [
                    (run, cross) for run, cross in zip(reversed(runs), reversed(high))]
            else:
                outline = [(cross, run) for run, cross in zip(runs, high)] + [
                    (cross, run) for run, cross in zip(reversed(runs), reversed(low))]
            cutter = _extrude_polygon(Polygon(outline), cutter_len)
            cutter.apply_translation((0.0, 0.0, -cutter_len / 2.0))
        else:
            cutter = trimesh.creation.box(extents=(slot_len if along == "x" else thickness, thickness if along == "x" else slot_len, cutter_len))
        cutter.apply_transform(trimesh.transformations.rotation_matrix(rad, (1, 0, 0) if along == "x" else (0, 1, 0)))
        cutter.apply_translation((centre_x, c_cross + cut_shift, cut_mid_z) if along == "x" else (c_cross + cut_shift, centre_y, cut_mid_z))
        cutters.append(cutter)
    return [difference([block, union(cutters) if len(cutters) > 1 else cutters[0]])]


register_setting_interactions("slot", (
    SettingInteraction("depth", "height", "constraint", "slot-shell",
                       "A user-edited Depth wins and raises Height to keep a 2 mm floor."),
    SettingInteraction("height", "depth", "constraint", "slot-shell",
                       "A user-edited Height wins and lowers Depth to keep a 2 mm floor."),
    SettingInteraction("count", "zone.run", "auto-adjust", "slot-sizing",
                       "Quantity grows the Slot Rack run on its selected axis."),
    SettingInteraction("thickness", "zone.run", "auto-adjust", "slot-sizing",
                       "Slot thickness changes the pitch and required run length."),
    SettingInteraction("wall", "zone", "auto-adjust", "slot-sizing",
                       "Wall thickness changes the bank footprint."),
    SettingInteraction("angle", "zone.run", "auto-adjust", "slot-sizing",
                       "Slot angle changes the projected pitch and required run length."),
))
