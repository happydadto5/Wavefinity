"""Nest solid builders."""

from __future__ import annotations

import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box as shapely_box
from organizer_engine import BoxSpec
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
    union,
)
from .._core import Feature, Zone
from .._registry import OptionDefinition, feature

from ._base import (
    NEST_OUTER_FOOT_MAX,
    NEST_TOP_ROUND_OUTER,
    NEST_TOP_ROUND_INNER,
    NEST_INSIDE_RELIEF_MAX,
    NEST_LEAD_IN_MAX,
    LEGACY_NEST_CHAMFER,
    LEGACY_NEST_TOP_ROUND,
    NEST_CUSTOM_WIDTH_MIN,
    NEST_CUSTOM_WIDTH_MAX,
    NEST_FINGER_BOTTOM_SKIN,
    NEST_ASSISTS,
    NEST_FINGER_POSITIONS,
    NEST_PUSH_POSITIONS,
    _nest_local_polygon,
    nest_contour_polygon,
    _nest_occurrence_opening,
    _is_legacy_nest,
    require_measured_tool_thickness,
    _line_coordinates,
    _nest_access_mode,
    _raised_wall_outer_foot,
)
from ._access import AccessPoint, resolve_nest_access_plan
from ._settings import nest_occurrences, resolve_nest_settings


def _nest_transform_mesh(mesh: trimesh.Trimesh, one: Feature) -> trimesh.Trimesh:
    """Rotate a local nest detail with its outline, then place it in the layout."""
    if one.rotation:
        mesh.apply_transform(trimesh.transformations.rotation_matrix(
            math.radians(one.rotation), (0.0, 0.0, 1.0)
        ))
    cx, cy = one.zone.centre
    mesh.apply_translation((cx, cy, 0.0))
    return mesh


def _oriented_notch_cutter(
    point: AccessPoint, wall_height: float, width: float, rim: float, base_z: float,
) -> trimesh.Trimesh:
    """One elliptical U-shaped cutter, oriented along one access point's own
    local tangent and punched inward from its outward normal side."""
    horizontal_radius = width / 2.0
    vertical_radius = min(horizontal_radius, wall_height - NEST_FINGER_BOTTOM_SKIN)
    if vertical_radius <= 0.0:
        raise ValueError("Photo Nest wall is too short for a finger grasp")
    reach = rim + NEST_OUTER_FOOT_MAX + 8.0
    centre = (0.0, base_z + wall_height)
    profile = affinity.scale(
        Point(centre).buffer(1.0, quad_segs=32),
        xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
    )
    cutter = _extrude_yz_profile(profile, reach)
    # The cutter now extrudes along world X (the reach), its width along
    # world Y and its height along world Z. Shift so it starts 2 mm inside
    # the boundary and reaches well past the wall, then rotate about Z so
    # that reach direction points along this point's outward normal.
    cutter.apply_translation((reach / 2.0 - 2.0, 0.0, 0.0))
    angle = math.degrees(math.atan2(point.normal[1], point.normal[0]))
    cutter.apply_transform(trimesh.transformations.rotation_matrix(math.radians(angle), (0.0, 0.0, 1.0)))
    cutter.apply_translation((point.position[0], point.position[1], 0.0))
    return cutter


def _legacy_nest_finger_cutters(
    one: Feature, opening: Polygon, wall_height: float, width: float,
    position: str, base_z: float, rim: float,
) -> list[trimesh.Trimesh]:
    """The exact pre-holder_style U-shaped notch placement: fixed local-axis
    crossings through the outline's representative point, not the newer
    tool-relative access planner. Kept unchanged so a legacy design's
    physical geometry never moves."""
    min_x, min_y, max_x, max_y = opening.bounds
    inside = opening.representative_point()
    reach = rim + LEGACY_NEST_CHAMFER + 3.0
    horizontal_radius = width / 2.0
    vertical_radius = min(horizontal_radius, wall_height - NEST_FINGER_BOTTOM_SKIN)
    if vertical_radius <= 0.0:
        raise ValueError("Photo Nest wall is too short for a finger grasp")
    cutters: list[trimesh.Trimesh] = []

    if position in {"sides", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (min_x - reach, inside.y), (max_x + reach, inside.y)
        ]))
        xs = _line_coordinates(crossing, 0)
        if len(xs) < 2:
            raise ValueError("Finger grasps could not find both sides of this outline")
        centre = (float(inside.y), base_z + wall_height)
        profile = affinity.scale(
            Point(centre).buffer(1.0, quad_segs=32),
            xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
        )
        for boundary, direction in ((min(xs), -1.0), (max(xs), 1.0)):
            start = boundary + direction * (rim + LEGACY_NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_yz_profile(profile, abs(end - start))
            cutter.apply_translation(((start + end) / 2.0, 0.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))

    if position in {"top_bottom", "both"}:
        crossing = opening.boundary.intersection(LineString([
            (inside.x, min_y - reach), (inside.x, max_y + reach)
        ]))
        ys = _line_coordinates(crossing, 1)
        if len(ys) < 2:
            raise ValueError("Finger grasps could not find both ends of this outline")
        centre = (float(inside.x), base_z + wall_height)
        profile = affinity.scale(
            Point(centre).buffer(1.0, quad_segs=32),
            xfact=horizontal_radius, yfact=vertical_radius, origin=centre,
        )
        for boundary, direction in ((min(ys), -1.0), (max(ys), 1.0)):
            start = boundary + direction * (rim + LEGACY_NEST_CHAMFER + 1.0)
            end = boundary - direction * 2.0
            cutter = _extrude_xz_profile(profile, abs(end - start))
            cutter.apply_translation((0.0, (start + end) / 2.0, 0.0))
            cutters.append(_nest_transform_mesh(cutter, one))
    return cutters


def _legacy_nest_rounded_wall(
    opening: Polygon, rim: float, height: float, base_z: float,
) -> trimesh.Trimesh:
    """The exact pre-holder_style Raised Wall: a fixed 2 mm outside foot and
    one shared top round, applied to both faces alike. Kept unchanged so a
    legacy design's physical geometry never moves."""
    outer = opening.buffer(rim, join_style="round")
    top_round = min(LEGACY_NEST_TOP_ROUND, rim * 0.4, height * 0.25)
    straight_height = height - top_round
    outside: list[trimesh.Trimesh] = []

    straight = _extrude_polygon(outer, straight_height)
    straight.apply_translation((0.0, 0.0, base_z))
    outside.append(straight)

    chamfer_steps = 8
    layer = LEGACY_NEST_CHAMFER / chamfer_steps
    for index in range(chamfer_steps):
        grow = LEGACY_NEST_CHAMFER - index * layer
        disk = _extrude_polygon(outer.buffer(grow, join_style="round"), layer)
        disk.apply_translation((0.0, 0.0, base_z + index * layer))
        outside.append(disk)

    inside: list[trimesh.Trimesh] = []
    bore = _extrude_polygon(opening, height + 2.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    inside.append(bore)
    top_steps = 8
    layer = top_round / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer
        inset = top_round - math.sqrt(max(0.0, top_round ** 2 - rise ** 2))
        top_outer = outer.buffer(-inset, join_style="round")
        top_inner = opening.buffer(inset, join_style="round")
        if top_outer.is_empty or top_inner.is_empty or not top_outer.contains(top_inner):
            raise ValueError("Outline wall is too thin for its rounded top")
        disk = _extrude_polygon(top_outer, layer)
        disk.apply_translation((0.0, 0.0, base_z + straight_height + index * layer))
        outside.append(disk)
        cut = _extrude_polygon(top_inner, layer + 0.02)
        cut.apply_translation((
            0.0, 0.0, base_z + straight_height + index * layer - 0.01
        ))
        inside.append(cut)
    return difference([union(outside), union(inside)])


def _nest_rounded_wall(
    opening: Polygon, rim: float, height: float, base_z: float,
) -> trimesh.Trimesh:
    """One Raised Wall: an adaptive structural buttress at the floor, a small
    removal-only relief easing the inside base, and a top rounded broader on
    the outside than the inside."""
    outer_foot = _raised_wall_outer_foot(height)
    outer = opening.buffer(rim, join_style="round")
    top_round_outer = min(NEST_TOP_ROUND_OUTER, rim * 0.4, height * 0.25)
    top_round_inner = min(NEST_TOP_ROUND_INNER, rim * 0.4, height * 0.25)
    inside_relief = min(NEST_INSIDE_RELIEF_MAX, rim * 0.3, height * 0.2)
    straight_height = height - top_round_outer
    outside: list[trimesh.Trimesh] = []

    straight = _extrude_polygon(outer, straight_height)
    straight.apply_translation((0.0, 0.0, base_z))
    outside.append(straight)

    # An adaptive 45-degree-or-gentler outside buttress, scaled to the
    # wall's own height rather than a fixed foot.
    foot_steps = 8
    layer = outer_foot / foot_steps
    for index in range(foot_steps):
        grow = outer_foot - index * layer
        disk = _extrude_polygon(outer.buffer(grow, join_style="round"), layer)
        disk.apply_translation((0.0, 0.0, base_z + index * layer))
        outside.append(disk)

    inside: list[trimesh.Trimesh] = []
    bore = _extrude_polygon(opening, height + 2.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    inside.append(bore)

    # A small removal-only relief at the base of the inside face - it only
    # ever widens the opening a little, never narrows the tool's clearance.
    if inside_relief > 0.02:
        relief_steps = 6
        layer = inside_relief / relief_steps
        for index in range(relief_steps):
            grow = inside_relief - index * layer
            disk = _extrude_polygon(opening.buffer(grow, join_style="round"), layer)
            disk.apply_translation((0.0, 0.0, base_z + index * layer))
            inside.append(disk)

    # A fine layered quarter-round eases both top edges - a broader crown
    # outside, a lighter ease inside.
    top_steps = 8
    layer = top_round_outer / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer
        inset = top_round_outer - math.sqrt(max(0.0, top_round_outer ** 2 - rise ** 2))
        top_outer = outer.buffer(-inset, join_style="round")
        if top_outer.is_empty:
            raise ValueError("Outline wall is too thin for its rounded top")
        disk = _extrude_polygon(top_outer, layer)
        disk.apply_translation((0.0, 0.0, base_z + straight_height + index * layer))
        outside.append(disk)

    inner_top_start = height - top_round_inner
    layer_inner = top_round_inner / top_steps
    for index in range(top_steps):
        rise = (index + 1) * layer_inner
        inset = top_round_inner - math.sqrt(max(0.0, top_round_inner ** 2 - rise ** 2))
        top_inner = opening.buffer(inset, join_style="round")
        if top_inner.is_empty or not outer.contains(top_inner):
            raise ValueError("Outline wall is too thin for its rounded top")
        cut = _extrude_polygon(top_inner, layer_inner + 0.02)
        cut.apply_translation((0.0, 0.0, base_z + inner_top_start + index * layer_inner - 0.01))
        inside.append(cut)

    return difference([union(outside), union(inside)])


def _nest_push_support(
    one: Feature, opening: Polygon, position: str, area: float,
    depth: float, base_z: float,
) -> trimesh.Trimesh:
    """Raised tool-shaped deck, leaving one selected end low for push-to-lift."""
    min_x, min_y, max_x, max_y = opening.bounds
    fraction = area / 100.0
    if position == "left":
        support = opening.intersection(shapely_box(
            min_x + (max_x - min_x) * fraction, min_y - 1.0,
            max_x + 1.0, max_y + 1.0,
        ))
    elif position == "right":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x - (max_x - min_x) * fraction, max_y + 1.0,
        ))
    elif position == "bottom":
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y + (max_y - min_y) * fraction,
            max_x + 1.0, max_y + 1.0,
        ))
    else:  # top
        support = opening.intersection(shapely_box(
            min_x - 1.0, min_y - 1.0,
            max_x + 1.0, max_y - (max_y - min_y) * fraction,
        ))
    if support.is_empty or support.area < opening.area * 0.5:
        raise ValueError("Push area leaves too little of the tool supported")
    deck = _extrude_polygon(support, depth)
    deck.apply_translation((0.0, 0.0, base_z))
    return _nest_transform_mesh(deck, one)


def _nest_recessed_deck(
    footprint: Polygon,
    cavity_depth: float,
    base_z: float,
) -> trimesh.Trimesh:
    """Solid Recessed deck filling the bin/insert's physical usable footprint."""
    deck = _extrude_polygon(footprint, cavity_depth)
    deck.apply_translation((0.0, 0.0, base_z))
    return deck


def _nest_recessed_cavity_cutter(
    world_opening: Polygon, cavity_depth: float, base_z: float,
) -> trimesh.Trimesh:
    """The tool-shaped hole through the deck to the normal printable floor,
    flared at the deck top by the automatic lead-in so the tool drops in
    without catching an edge."""
    lead_in = min(NEST_LEAD_IN_MAX, cavity_depth / 3.0)
    parts: list[trimesh.Trimesh] = []
    straight_height = max(0.02, cavity_depth - lead_in)
    bore = _extrude_polygon(world_opening, straight_height + 1.0)
    bore.apply_translation((0.0, 0.0, base_z - 1.0))
    parts.append(bore)
    if lead_in > 0.02:
        flare_steps = 8
        layer = lead_in / flare_steps
        flare_start_z = base_z + max(0.0, cavity_depth - lead_in)
        for index in range(flare_steps):
            grow = lead_in * (index + 1) / flare_steps
            disk = _extrude_polygon(world_opening.buffer(grow, join_style="round"), layer + 0.02)
            disk.apply_translation((0.0, 0.0, flare_start_z + index * layer - 0.01))
            parts.append(disk)
    return union(parts)


def _nest_finger_scoops(
    points: tuple[AccessPoint, ...], radius: float, scoop_z: float,
) -> list[trimesh.Trimesh]:
    """One spherical scoop per resolved access point, in local coordinates -
    the caller places each into the layout with ``_nest_transform_mesh``."""
    scoops = []
    for point in points:
        sphere = trimesh.creation.icosphere(subdivisions=3, radius=radius)
        sphere.apply_translation((point.position[0], point.position[1], scoop_z))
        scoops.append(sphere)
    return scoops


@feature(
    "nest", title="Photo Nest",
    display="Photo Nest — a custom holder built from your photo",
    description="A custom holder built from your photo.",
    capabilities=("photo",),
    options=(
        OptionDefinition("Fit clearance", "clearance", "0.6"),
        OptionDefinition("Soften outline", "smoothing", "0"),
        OptionDefinition("Tool thickness", "tool_thickness", "8", editor=False),
        OptionDefinition("Outline wall", "rim", "", editor=False),
        OptionDefinition("Holder style", "holder_style", "raised_wall", "enum", False),
        OptionDefinition("Cavity depth", "cavity_depth", "", editor=False),
        OptionDefinition("Cavity depth mode", "cavity_depth_mode", "auto", "enum", False),
        OptionDefinition("Automatic footprint sizing", "auto_size", True, "boolean", False),
        OptionDefinition("Repeat spacing", "repeat_spacing_percent", 0, "integer", False),
        OptionDefinition("Finger access", "lift_assist", "auto", "enum", False),
        OptionDefinition("Finger locations", "finger_position", "sides", "enum", False),
        OptionDefinition("Finger width", "finger_width", "25", editor=False),
        OptionDefinition("Push position", "push_position", "right", "enum", False),
        OptionDefinition("Push area", "push_area", "30", editor=False),
        OptionDefinition("Push depth", "push_depth", "4", editor=False),
        OptionDefinition("Photo marker", "photo", False, "boolean", False),
    ), order=20,
)
def build_nest(
    box: BoxSpec,
    spec_feature: Feature,
    base_z: float,
    *,
    deck_footprint: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """A finished holder that traces one photographed outline: a solid
    Recessed Cavity deck by default, or a Raised Wall on request.
    """
    require_measured_tool_thickness(spec_feature)
    options = resolve_nest_settings(box, spec_feature, base_z)
    clearance = options["clearance"]
    tool_thickness = float(options["tool_thickness"])
    rim = options["rim"]
    smoothing = options["smoothing"]
    holder_style = str(options["holder_style"])
    cavity_depth = float(options["cavity_depth"])
    assist = str(options["lift_assist"])
    finger_position = str(options["finger_position"])
    finger_width = float(options["finger_width"])
    push_position = str(options["push_position"])
    push_area = float(options["push_area"])
    push_depth = float(options["push_depth"])
    if not all(math.isfinite(value) for value in (
        clearance, tool_thickness, rim, smoothing, cavity_depth, finger_width, push_area, push_depth
    )):
        raise ValueError("Photo Nest measurements must be finite")
    if clearance < 0.0:
        raise ValueError("Clearance must be zero or greater")
    if rim <= 0.0:
        raise ValueError("Outline wall must be greater than zero")
    if smoothing < 0.0:
        raise ValueError("Soften outline must be zero or greater")
    if tool_thickness <= 0.0:
        raise ValueError("Tool thickness must be greater than zero")
    if assist not in NEST_ASSISTS:
        raise ValueError("Finger access must be Automatic, Off, or Custom")
    if assist == "finger_grasp":
        if finger_position not in NEST_FINGER_POSITIONS:
            raise ValueError("Finger grasp locations must be Sides, Ends, or Both")
        if finger_width < NEST_CUSTOM_WIDTH_MIN or finger_width > NEST_CUSTOM_WIDTH_MAX:
            raise ValueError("Finger opening width must be between 12 and 40 mm")
    if push_position not in NEST_PUSH_POSITIONS:
        raise ValueError("Push position must be left, right, top, or bottom")
    if push_area < 15.0 or push_area > 40.0:
        raise ValueError("Push area must be between 15% and 40%")
    if push_depth < 2.0 or push_depth > 8.0:
        raise ValueError("Push depth must be between 2 and 8 mm")

    local_opening = _nest_local_polygon(spec_feature, include_clearance=True)
    world_opening = nest_contour_polygon(spec_feature, include_clearance=True)
    available = box.z - base_z

    if holder_style == "recessed":
        if cavity_depth <= 0.0:
            raise ValueError("Cavity depth must be greater than zero")
        if cavity_depth > available + 1e-9:
            raise ValueError(
                f"Cavity depth {cavity_depth:g} mm must fit within {available:.1f} mm "
                f"above the printable floor"
            )
        physical_deck = deck_footprint if deck_footprint is not None else spec_feature.zone.polygon
        return [build_recessed_nest_group(box, (spec_feature,), base_z, physical_deck)]

    # Raised Wall. A design saved before holder_style existed keeps its exact
    # old wall (fixed foot, shared top round) and old finger-cutout placement
    # (fixed local-axis crossings) - only an explicit holder_style opts into
    # the new adaptive buttress and tool-relative access planner.
    legacy = _is_legacy_nest(spec_feature)
    wall_height = tool_thickness + (push_depth if assist == "push_out" else 0.0)
    # A fused Raised Wall may legitimately rise above the rim now - the
    # central assembly policy (_assembly.py's _allows_above_rim) is the one
    # that still bounds it in Separate/Cartridge mode or against a lid/stack.
    wall = (
        _legacy_nest_rounded_wall(world_opening, rim, wall_height, base_z) if legacy
        else _nest_rounded_wall(world_opening, rim, wall_height, base_z)
    )

    if assist == "push_out":
        deck = _nest_push_support(
            spec_feature, local_opening, push_position, push_area, push_depth, base_z,
        )
        wall = union([wall, deck])
    elif assist == "none":
        pass
    elif legacy:
        # The old code always attempted a cutout for "finger_grasp" and never
        # had an "auto" state; legacy's own default_assist already maps a
        # missing lift_assist to "finger_grasp" (see _resolved_finger_settings).
        if assist == "finger_grasp":
            cutters = _legacy_nest_finger_cutters(
                spec_feature, local_opening, wall_height, finger_width,
                finger_position, base_z, rim,
            )
            wall = difference([wall, union(cutters)])
    elif assist == "auto" and wall_height <= 4.0:
        pass  # A very low Raised Wall may resolve to no notch - that is valid.
    else:  # "finger_grasp" (Custom), or "auto" on a tall-enough wall.
        plan = resolve_nest_access_plan(
            local_opening, _nest_access_mode(assist), finger_position, finger_width,
        )
        if plan.style == "finger_grasp":
            cutters = [
                _nest_transform_mesh(
                    _oriented_notch_cutter(point, wall_height, plan.width, rim, base_z),
                    spec_feature,
                )
                for point in plan.points
            ]
            wall = difference([wall, union(cutters)])
    # Quantity uses the same holder geometry at every derived transform. The
    # first pass above retains the exact legacy geometry for Quantity 1.
    occurrences = nest_occurrences(spec_feature)
    if len(occurrences) == 1:
        return [wall]
    solids = []
    for occurrence in occurrences:
        temporary = replace(
            spec_feature,
            rotation=occurrence.rotation,
            zone=Zone(occurrence.x - 0.5, occurrence.y - 0.5,
                      occurrence.x + 0.5, occurrence.y + 0.5),
            count=1,
            alternate_ends=False,
        )
        # Re-enter with a one-copy temporary only; this is intentionally not
        # a recursive group build and preserves all existing wall paths.
        solids.extend(build_nest(box, temporary, base_z, deck_footprint=deck_footprint))
    return solids


def build_recessed_nest_group(
    box: BoxSpec, features: tuple[Feature, ...] | list[Feature], base_z: float,
    deck_footprint: Polygon,
) -> trimesh.Trimesh:
    """One physical deck for all recessed Photo Nest occurrences."""
    recessed = tuple(features)
    if not recessed:
        raise ValueError("at least one Recessed Photo Nest is required")
    resolved = []
    for one in recessed:
        require_measured_tool_thickness(one)
        options = resolve_nest_settings(box, one, base_z)
        if str(options["holder_style"]) != "recessed":
            raise ValueError("shared Photo Nest deck requires Recessed Cavity holders")
        depth = float(options["cavity_depth"])
        if not math.isfinite(depth) or depth <= 0.0:
            raise ValueError("Cavity depth must be greater than zero")
        resolved.append((one, options, depth))
    group_depth = max(depth for _one, _options, depth in resolved)
    if group_depth > box.z - base_z + 1e-9:
        raise ValueError(
            f"Cavity depth {group_depth:g} mm must fit within {box.z - base_z:.1f} mm above the printable floor"
        )
    deck = _nest_recessed_deck(deck_footprint, group_depth, base_z)
    cutters: list[trimesh.Trimesh] = []
    scoops: list[trimesh.Trimesh] = []
    for one, options, depth in resolved:
        floor_raise = group_depth - depth
        occurrence_base_z = base_z + floor_raise
        local_opening = _nest_local_polygon(one, include_clearance=True)
        assist = str(options["lift_assist"])
        plan = resolve_nest_access_plan(
            local_opening, _nest_access_mode(assist), str(options["finger_position"]),
            float(options["finger_width"]),
        )
        for occurrence in nest_occurrences(one):
            world_opening = _nest_occurrence_opening(one, occurrence)
            cutters.append(_nest_recessed_cavity_cutter(world_opening, depth, occurrence_base_z))
            if plan.style == "finger_grasp":
                temporary = replace(one, rotation=occurrence.rotation,
                                    zone=Zone(occurrence.x - .5, occurrence.y - .5,
                                              occurrence.x + .5, occurrence.y + .5))
                scoops.extend(_nest_transform_mesh(scoop, temporary) for scoop in
                             _nest_finger_scoops(plan.points, plan.width / 2.0,
                                                 base_z + group_depth))
    return difference([deck, union(cutters + scoops)]) if cutters or scoops else deck
