"""Bore feature defaults and geometry."""

from __future__ import annotations

import math
from dataclasses import replace

import trimesh

from shapely.affinity import translate
from shapely.geometry import Polygon, box as shapely_box
from shapely.ops import unary_union

from organizer_engine import (
    WAVE_AMPLITUDE, WAVE_LENGTH, BoxSpec, wall_depth_for, wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, difference, union

from ._core import Feature, Zone, _fit_count, _need_item, connector_keep_out, feature_touches_wall, layout_zone
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)

BORE_WALL = 1.6            # material around a bore
BORE_CLEARANCE = 0.25      # automatic fit clearance on bore diameters
HEX_BIT_FLATS = 6.35      # 1/4" hex driver bit, measured across the flats
HEX_BIT_SHORT_LENGTH = 25.0  # a nominal 1" insert bit
HEX_BIT_LONG_LENGTH = 38.0   # a nominal 1.5" power bit
HEX_BIT_CLEARANCE = 0.25  # snug in the hex hole but still slides in and out freely
# Hole depth per hex-bit type: holds roughly half the bit so it stands well proud
# and stays easy to pinch out.
HEX_BIT_HOLD = {"hex_bit_short": 12.0, "hex_bit_long": 16.0}
HEX_BIT_LENGTH = {
    "hex_bit_short": HEX_BIT_SHORT_LENGTH,
    "hex_bit_long": HEX_BIT_LONG_LENGTH,
}
BORE_MOUTH_CHAMFER = 0.6  # 45-degree lead-in at each hole mouth
BORE_MAX_TILT = 70.0      # steepest lean off vertical the hole geometry still allows
BORE_TILTED_WALL = 3.0    # thicker default wall once a bore is leaned


def bore_direction(spec_feature: Feature) -> tuple[str, float]:
    """Return the lean axis and the direction the bore points toward.

    Old designs used ``along`` as their only direction control.  Keep that
    meaning when no new direction is stored, so existing designs do not turn.
    """
    toward = str(spec_feature.options.get("angle_towards", "")).lower()
    directions = {
        "right": ("x", 1.0), "left": ("x", -1.0),
        "back": ("y", 1.0), "front": ("y", -1.0),
    }
    return directions.get(toward, (spec_feature.along, -1.0))

BORE_STYLES = ("full_base", "wall_only", "wavy_base")
# Styles that stand upright and are sized by their sleeves' true outer envelope.
ENVELOPE_STYLES = ("wall_only", "wavy_base")
# Set by the fused assembler on a Bore whose geometry may fuse into the bin wall.
WALL_JOIN_FLAG = "_wall_join"
JOIN_TOUCH = 0.05             # envelope this close to a wall counts as reaching it
JOIN_BAND = 1.2               # wall-only material this close to the wall is blended in
JOIN_SKIN = 0.15              # a joined blend never comes closer than this to the outside
WALL_STYLES = ("wavy", "straight")
WAVE_NOISE_FLOOR = 1e-4       # trough sits a hair outside the clear opening, so
                              # float noise cannot fold the outline back on itself
WAVE_SAMPLES_PER_CYCLE = 32   # keeps a wavy sleeve smooth in the STL and preview


def _is_hex_bit(profile: str) -> bool:
    return profile in HEX_BIT_HOLD


def _hole_sides(profile: str) -> int:
    """Polygon sides for a bore hole of this profile - round is a fine circle,
    a hex bit is a six-sided socket."""
    return {
        "round": 48, "hex": 6, "square": 4, "square_axis": 4,
        "hex_bit_short": 6, "hex_bit_long": 6,
    }[profile]


def _axis_square(profile: str) -> bool:
    return profile == "square_axis"


def bore_minimum_pitches(
    profile: str, held: float, wall: float, angle: float, lean_axis: str,
) -> tuple[float, float]:
    """Smallest X/Y centre pitches that retain the requested wall thickness."""
    sides = _hole_sides(profile)
    if _axis_square(profile):
        cross_pitch = held + wall
    else:
        radius = held / 2.0 / (math.cos(math.pi / sides) if sides < 8 else 1.0)
        cross_pitch = 2.0 * radius + wall
    lean_pitch = cross_pitch / math.cos(math.radians(angle)) if angle > 1e-9 else cross_pitch
    return (lean_pitch, cross_pitch) if lean_axis == "x" else (cross_pitch, lean_pitch)


def _wall_only_shell_reach(wall: float, wall_style: str) -> float:
    """How far a Wall Only sleeve reaches past its clear opening, per side.

    A wavy inner wall runs from 0 to ``2 * WAVE_AMPLITUDE`` outward of the
    clear profile; the outer face adds Wavefinity's wall depth on top.
    """
    if wall_style == "wavy":
        return 2.0 * WAVE_AMPLITUDE + wall_depth_for(wall) + WAVE_NOISE_FLOOR
    return wall


def _round_clear_sides(held: float, wall_style: str) -> int:
    """Sides of the polygon that stands in for a round clear opening."""
    if wall_style == "wavy":
        cycles = max(1, round(math.pi * held / WAVE_LENGTH))
        return max(256, WAVE_SAMPLES_PER_CYCLE * cycles)
    return 256


def _clear_spans(profile: str, held: float, wall_style: str) -> tuple[float, float]:
    """X/Y span of one upright clear opening - exactly what the builder cuts.

    A round opening is a polygon circumscribing the requested circle, so its
    span is a hair over ``held``.
    """
    if profile == "round":
        span = held / math.cos(math.pi / _round_clear_sides(held, wall_style))
        return span, span
    if _axis_square(profile):
        return held, held
    sides = _hole_sides(profile)
    radius = held / 2.0 / math.cos(math.pi / sides)
    if sides == 4:                      # diamond: corners on both axes
        return 2.0 * radius, 2.0 * radius
    return 2.0 * radius, held           # hex: corners on X, flats on Y


def wall_only_envelope(
    profile: str, held: float, wall: float, wall_style: str,
) -> dict[str, float]:
    """Shared Wall Only spacing/size numbers (backend build, layout, Auto Grid).

    Pitch keeps today's "clear opening + requested web" rule at upright angle;
    the physical one-hole span is the clear span plus the shell on both sides.
    """
    pitch_x, pitch_y = bore_minimum_pitches(profile, held, wall, 0.0, "x")
    clear_x, clear_y = _clear_spans(profile, held, wall_style)
    reach = _wall_only_shell_reach(wall, wall_style)
    return {
        "pitch_x": pitch_x, "pitch_y": pitch_y,
        "clear_x": clear_x, "clear_y": clear_y, "reach": reach,
        "span_x": clear_x + 2.0 * reach, "span_y": clear_y + 2.0 * reach,
    }


def _clear_profile_points(profile: str, held: float, wall_style: str) -> list[tuple[float, float]]:
    """Counter-clockwise outline of one upright clear opening.

    Round openings are a fine polygon circumscribing the true circle so the
    opening is never smaller than requested.
    """
    if profile == "round":
        sides = _round_clear_sides(held, wall_style)
        radius = held / 2.0 / math.cos(math.pi / sides)
        return [
            (radius * math.cos(2.0 * math.pi * i / sides),
             radius * math.sin(2.0 * math.pi * i / sides))
            for i in range(sides)
        ]
    if _axis_square(profile):
        half = held / 2.0
        return [(half, half), (-half, half), (-half, -half), (half, -half)]
    sides = _hole_sides(profile)
    radius = held / 2.0 / math.cos(math.pi / sides)
    return [
        (radius * math.cos(2.0 * math.pi * i / sides),
         radius * math.sin(2.0 * math.pi * i / sides))
        for i in range(sides)
    ]


def _wavy_outline(
    clear: list[tuple[float, float]], thickness: float,
) -> list[tuple[float, float]]:
    """Displace the clear outline outward by a whole-cycle sine.

    Each edge is walked by arc length and pushed along its own outward normal by
    ``WAVE_AMPLITUDE * (1 + sin(phase)) + thickness``. The
    displacement is never negative, so the outline never enters the clear
    profile; at corners the neighbouring displaced edge ends simply join.
    """
    count = len(clear)
    edges = [(clear[i], clear[(i + 1) % count]) for i in range(count)]
    lengths = [math.dist(a, b) for a, b in edges]
    perimeter = sum(lengths)
    cycles = max(1, round(perimeter / WAVE_LENGTH))
    step = WAVE_LENGTH / WAVE_SAMPLES_PER_CYCLE
    points: list[tuple[float, float]] = []
    travelled = 0.0
    for (a, b), length in zip(edges, lengths):
        nx, ny = (b[1] - a[1]) / length, -(b[0] - a[0]) / length   # CCW: outward is right
        pieces = max(1, math.ceil(length / step))
        for k in range(pieces + 1):
            t = k / pieces
            s = travelled + t * length
            push = (thickness + WAVE_NOISE_FLOOR
                    + WAVE_AMPLITUDE * (1.0 + math.sin(2.0 * math.pi * cycles * s / perimeter)))
            points.append((a[0] + (b[0] - a[0]) * t + nx * push,
                           a[1] + (b[1] - a[1]) * t + ny * push))
        travelled += length
    return points


def _wall_only_ring(
    profile: str, held: float, wall: float, wall_style: str,
) -> tuple[Polygon, Polygon, Polygon]:
    """(outer, inner, clear) outlines of one upright Wall Only sleeve at 0, 0.

    ``inner`` is the sleeve's bore wall, which hugs or waves outward of the
    ``clear`` opening the user asked for.
    """
    outline = _clear_profile_points(profile, held, wall_style)
    clear = Polygon(outline)
    if wall_style == "wavy":
        inner = Polygon(_wavy_outline(outline, 0.0))
        outer = Polygon(_wavy_outline(outline, wall_depth_for(wall)))
    else:
        inner = clear
        outer = clear.buffer(wall, join_style="round")
    if (not outer.is_valid or not inner.is_valid or not outer.contains(inner)
            or not inner.buffer(1e-7).contains(clear)):
        raise ValueError("bore wall profile could not be built; try another wall or shape")
    return outer, inner, clear


def _union(meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    return meshes[0] if len(meshes) == 1 else union(meshes)


def _polygons(shape) -> list[Polygon]:
    """The area pieces of a shapely result, ignoring stray lines and points."""
    if shape.is_empty:
        return []
    if isinstance(shape, Polygon):
        return [shape]
    return [piece for piece in getattr(shape, "geoms", ())
            if isinstance(piece, Polygon) and not piece.is_empty]


def _join_tabs(
    box: BoxSpec, material, keep_clear, fill: float,
) -> list[Polygon]:
    """Blends that carry ``material`` straight into any bin wall it reaches.

    ``material`` is the Bore's plan-view footprint and ``keep_clear`` the area
    that must stay open (every hole and its wavy wall). Each side of the usable
    floor that the material touches gets a tab running from ``fill`` inside the
    wall out through the bin's wavy inner face, so the sleeve fuses into the
    wall instead of stopping a hair short of it. Tabs never come within
    ``JOIN_SKIN`` of the bin's outside face, so the exterior stays as it was.
    """
    whole = Zone.whole(box)
    limit = wavy_outer_polygon(box).buffer(-JOIN_SKIN)
    reach = box.wall_depth + 2.0 * WAVE_AMPLITUDE
    x0, y0, x1, y1 = material.bounds
    big = 1.0e3
    sides = (
        (x1 >= whole.x1 - JOIN_TOUCH,
         shapely_box(whole.x1 - JOIN_BAND, -big, whole.x1 + big, big),
         lambda b: shapely_box(whole.x1 - fill, b[1], whole.x1 + reach, b[3])),
        (x0 <= whole.x0 + JOIN_TOUCH,
         shapely_box(-big, -big, whole.x0 + JOIN_BAND, big),
         lambda b: shapely_box(whole.x0 - reach, b[1], whole.x0 + fill, b[3])),
        (y1 >= whole.y1 - JOIN_TOUCH,
         shapely_box(-big, whole.y1 - JOIN_BAND, big, whole.y1 + big),
         lambda b: shapely_box(b[0], whole.y1 - fill, b[2], whole.y1 + reach)),
        (y0 <= whole.y0 + JOIN_TOUCH,
         shapely_box(-big, -big, big, whole.y0 + JOIN_BAND),
         lambda b: shapely_box(b[0], whole.y0 - reach, b[2], whole.y0 + fill)),
    )
    tabs: list[Polygon] = []
    for touching, band, make in sides:
        if not touching:
            continue
        for piece in _polygons(material.intersection(band)):
            tab = make(piece.bounds).difference(keep_clear).intersection(limit)
            tabs.extend(part for part in _polygons(tab) if part.area > 1e-6)
    return tabs


def _tab_meshes(
    tabs: list[Polygon], height: float, base_z: float,
) -> list[trimesh.Trimesh]:
    meshes = []
    for tab in tabs:
        mesh = _extrude_polygon(tab, height)
        mesh.apply_translation((0.0, 0.0, base_z))
        meshes.append(mesh)
    return meshes


def _build_wall_only_bore(
    grid: dict, count: int | None, box: BoxSpec | None = None, join: bool = False,
) -> trimesh.Trimesh:
    """Perimeter sleeves rising from the base; no raised rectangular block."""
    profile = grid["item"].profile
    outer, inner, clear = _wall_only_ring(
        profile, grid["held"], grid["wall"], grid["wall_style"])
    height, base_z = grid["height"], grid["base_z"]
    # Cut the inner wall out of the outer body with a boolean; that is sturdier
    # than triangulating a ring with a hole.
    bore = _extrude_polygon(inner, height + 2.0)
    bore.apply_translation((0.0, 0.0, -1.0))
    sleeve = difference([_extrude_polygon(outer, height), bore])
    opening = _extrude_polygon(clear, height + 2.0)
    opening.apply_translation((0.0, 0.0, -1.0))
    sleeves, openings = [], []
    centres = list(_bore_hole_centres(grid, count))
    for x, y in centres:
        one = sleeve.copy()
        one.apply_translation((x, y, base_z))
        sleeves.append(one)
        cut = opening.copy()
        cut.apply_translation((x, y, base_z))
        openings.append(cut)
    tabs: list[trimesh.Trimesh] = []
    if join and box is not None:
        material = unary_union([translate(outer, x, y) for x, y in centres])
        keep_clear = unary_union([translate(inner, x, y) for x, y in centres])
        tabs = _tab_meshes(
            _join_tabs(box, material, keep_clear, JOIN_BAND), height, base_z)
    if len(sleeves) == 1 and not tabs:
        return sleeves[0]
    # Touching sleeves merge for strength; every opening is then cut again so a
    # neighbour's wall (or a wall-joining blend) can never close it.
    merged = _union(sleeves + tabs)
    return difference([merged, _union(openings)])


def _build_wavy_base_bore(
    grid: dict, count: int | None, box: BoxSpec | None = None, join: bool = False,
) -> trimesh.Trimesh:
    """A solid raised Base whose holes have Wall Only's wavy walls."""
    outer, inner, clear = _wall_only_ring(
        grid["item"].profile, grid["held"], grid["wall"], "wavy")
    ring = outer.difference(inner)
    height, depth, base_z = grid["height"], grid["depth"], grid["base_z"]
    centres = list(_bore_hole_centres(grid, count))
    cx, cy = grid["centre_x"], grid["centre_y"]
    half_x, half_y = grid["needed_x"] / 2.0, grid["needed_y"] / 2.0
    # A neighbour's wall may reach into this hole's wavy cavity, so it is kept;
    # only the requested clear opening is then re-opened in full.
    walls = unary_union([translate(ring, x, y) for x, y in centres])
    cavity = unary_union([translate(inner, x, y) for x, y in centres]).difference(walls)
    cavity = cavity.union(unary_union([translate(clear, x, y) for x, y in centres]))
    body = trimesh.creation.box(extents=(2.0 * half_x, 2.0 * half_y, height))
    body.apply_translation((cx, cy, base_z + height / 2.0))
    cuts = []
    for piece in _polygons(cavity):
        mesh = _extrude_polygon(piece, depth + 1.0)
        mesh.apply_translation((0.0, 0.0, base_z + height - depth))
        cuts.append(mesh)
    result = difference([body, _union(cuts)])
    if join and box is not None:
        footprint = shapely_box(cx - half_x, cy - half_y, cx + half_x, cy + half_y)
        tabs = _tab_meshes(_join_tabs(box, footprint, cavity, 0.0), height, base_z)
        if tabs:
            result = union([result] + tabs)
    return result


@defaults("bore")
def bore_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    auto_height = bool(one.options.get("auto_height"))
    if _is_hex_bit(item.profile):
        hole = min(HEX_BIT_HOLD[item.profile], box.z - base_z - 2.0)
        held = HEX_BIT_FLATS + HEX_BIT_CLEARANCE
    else:
        hole = min(item.length * 0.4, box.z - base_z - 2.0)
        held = item.held(item.widest)
    style = str(one.options.get("bore_style", "full_base"))
    wall_style = str(one.options.get("wall_style", "wavy"))
    if style == "wavy_base":
        wall_style = "wavy"       # Wavy Base is Wavy by definition
    wall_only = style == "wall_only"
    envelope = style in ENVELOPE_STYLES
    try:
        angle = max(0.0, float(one.options.get("angle", 0.0) or 0.0))
    except (TypeError, ValueError):
        angle = 0.0
    if envelope:
        angle = 0.0      # Wall Only and Wavy Base always stand upright
    tilted = angle > 1e-9
    default_wall = box.wall if envelope else BORE_TILTED_WALL if tilted else BORE_WALL
    wall = float(one.options.get("wall", default_wall))
    try:
        depth = float(one.options.get("depth", hole))
    except (TypeError, ValueError):
        depth = hole
    reach = max(0.0, depth) * math.sin(math.radians(angle)) if tilted else 0.0
    if auto_height:
        # Fix 034 G1: Auto Height must resolve to a height that is actually
        # legal, not just the full bin - a wall-touching Bore is capped at
        # the connector keep-out exactly like a manual height would be.
        top_limit = box.z - base_z
        if feature_touches_wall(box, one):
            top_limit = min(top_limit, connector_keep_out(box) - base_z)
        minimum_height = (hole if wall_only else depth) + 2.0
        if top_limit + 1e-6 < minimum_height:
            raise ValueError(
                "Auto Height cannot fit a legal Bore here - the connector keep-out "
                "leaves too little room; make the bin taller or move the Bore away from the wall"
            )
        resolved_height = top_limit
    elif wall_only:
        resolved_height = hole + 2.0
    else:
        resolved_height = one.options.get("depth", hole) + 2.0
    resolved_grid: dict[str, float] = {}
    # A saved Auto Grid stays on record but is dormant while Wavy Base is active.
    if one.options.get("auto_grid") and style != "wavy_base":
        # Auto Grid fills the current Base: the most holes that fit on each
        # axis at the real wall/lean pitch, never a stored quantity.
        lean_axis, _ = bore_direction(one)
        pitch_x, pitch_y = bore_minimum_pitches(item.profile, held, wall, angle, lean_axis)
        if envelope:
            env = wall_only_envelope(item.profile, held, wall, wall_style)
            resolved_grid = {
                "columns": float(_fit_count(one.zone.width, env["pitch_x"], env["span_x"])),
                "rows": float(_fit_count(one.zone.depth, env["pitch_y"], env["span_y"])),
            }
        else:
            resolved_grid = {
                "columns": float(_fit_count(
                    one.zone.width - (reach if lean_axis == "x" else 0.0), pitch_x, pitch_x)),
                "rows": float(_fit_count(
                    one.zone.depth - (reach if lean_axis == "y" else 0.0), pitch_y, pitch_y)),
            }
    return {
        "depth": hole,
        # A leaned bore takes a thicker wall by default so the extra material
        # between slanting holes still prints; an explicit Wall overrides it.
        "wall": default_wall,
        "height": resolved_height,
        # A new Bore is one hole. X/Y quantities grow the Base and then the
        # bin; they never begin by filling whatever space happened to exist.
        # Only the persisted Auto Grid mode fills the Base instead.
        "columns": 1.0,
        "rows": 1.0,
        **resolved_grid,
        # 0 is straight up; a positive angle leans the holes off vertical so
        # tubes rest at a slant. Any grid may lean.
        "angle": 0.0,
        "bore_style": style,
        "wall_style": wall_style,
    }


def normalize_bore_auto(
    box: BoxSpec, one: Feature, base_z: float, mode: str = "fused",
) -> Feature:
    """Make a Bore's persisted Auto modes authoritative over stale manual values.

    Base Auto takes the current usable layout area, Height Auto and Grid Auto
    drop their manual numbers (defaults then derive them from the current bin
    and Base). Anything that is not an Auto Bore is returned untouched.
    """
    if one.kind != "bore":
        return one
    options = dict(one.options)
    zone = one.zone
    # Auto Base / Auto Grid are dormant (kept untouched) while Wavy Base is
    # active, so switching back to another style restores them.
    dormant = str(options.get("bore_style", "")) == "wavy_base"
    if options.get("auto_base") and not dormant:
        zone = layout_zone(box, mode)
    if options.get("auto_height"):
        options.pop("height", None)
    if options.get("auto_grid") and not dormant:
        options.pop("columns", None)
        options.pop("rows", None)
    if zone is one.zone and options == one.options:
        return one
    return replace(one, zone=zone, options=options)


def _envelope_counts(
    env: dict, zone, spec_feature: Feature, options: dict, name: str,
) -> tuple[int, int]:
    """Whole-number columns/rows of an envelope-sized (upright) Bore grid."""
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width, env["pitch_x"], env["span_x"])
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth, env["pitch_y"], env["span_y"])
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {name}: zone is too small for a bore")
    return columns, rows


def _wall_only_grid(
    item, zone, spec_feature: Feature, held: float, wall: float, height: float,
    angle: float, wall_style: str, where: tuple[BoxSpec, float], options: dict,
    style: str = "wall_only", depth: float = 0.0,
) -> dict:
    """Grid for an upright envelope-sized Bore (Wall Only or Wavy Base); its
    footprint is the sleeves' outer envelope."""
    _, base_z = where
    if height <= 0.0 or wall <= 0.0:
        raise ValueError(f"{item.name}: bore height and wall must be positive")
    if not math.isfinite(angle) or abs(angle) > 1e-9:
        label = "Wall Only" if style == "wall_only" else "Wavy Base"
        raise ValueError(f"a {label} bore stands upright; its angle must be 0")
    env = wall_only_envelope(item.profile, held, wall, wall_style)
    columns, rows = _envelope_counts(env, zone, spec_feature, options, item.name)
    needed_x = env["span_x"] + (columns - 1) * env["pitch_x"]
    needed_y = env["span_y"] + (rows - 1) * env["pitch_y"]
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )
    centre_x, centre_y = zone.centre
    return {
        "item": item, "zone": zone, "held": held, "depth": depth, "wall": wall,
        "height": height, "angle": 0.0, "tilted": False, "lean": 0.0,
        "lean_axis": "x", "lean_sign": 1.0, "reach": 0.0, "drop": 0.0,
        "lean_shift": 0.0, "pitch": min(env["pitch_x"], env["pitch_y"]),
        "pitch_x": env["pitch_x"], "pitch_y": env["pitch_y"],
        "columns": columns, "rows": rows, "centre_x": centre_x, "centre_y": centre_y,
        "bore_style": style, "wall_style": wall_style, "base_z": base_z,
        "needed_x": needed_x, "needed_y": needed_y, "envelope": env,
    }


def bore_envelope_zone(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """Physical footprint of an upright envelope-sized Bore, centred on its
    zone - the smallest rectangle holding every sleeve. ``None`` for any other
    holder (or one that cannot resolve yet)."""
    if one.kind != "bore" or one.item is None:
        return None
    try:
        options = resolved_options(box, one, base_z)
        style = str(options.get("bore_style", "full_base"))
        if style not in ENVELOPE_STYLES:
            return None
        item = one.item
        held = (HEX_BIT_FLATS + HEX_BIT_CLEARANCE
                if _is_hex_bit(item.profile) else item.held(item.widest))
        wall_style = "wavy" if style == "wavy_base" else str(options.get("wall_style", "wavy"))
        env = wall_only_envelope(item.profile, held, float(options["wall"]), wall_style)
        columns, rows = _envelope_counts(env, one.zone, one, options, item.name)
    except (ValueError, KeyError, TypeError):
        return None
    need_x = env["span_x"] + (columns - 1) * env["pitch_x"]
    need_y = env["span_y"] + (rows - 1) * env["pitch_y"]
    cx, cy = one.zone.centre
    return Zone(cx - need_x / 2.0, cy - need_y / 2.0, cx + need_x / 2.0, cy + need_y / 2.0)


def _bore_grid(box: BoxSpec, spec_feature: Feature, base_z: float) -> dict:
    """Resolve and validate a bore's grid once, for both the mesh builder and
    the preview's lean indicator. Raises the same errors ``build_bore`` used to
    raise inline, so nothing about validation changes."""
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)

    if _is_hex_bit(item.profile):
        held = HEX_BIT_FLATS + HEX_BIT_CLEARANCE
    else:
        held = item.held(item.widest)
    depth = options["depth"]
    wall = options["wall"]
    height = options["height"]
    angle = options.get("angle", 0.0)
    style = str(options.get("bore_style", "full_base"))
    wall_style = str(options.get("wall_style", "wavy"))
    if style not in BORE_STYLES:
        raise ValueError(f"bore style must be one of {', '.join(BORE_STYLES)}")
    if wall_style not in WALL_STYLES:
        raise ValueError(f"bore wall style must be one of {', '.join(WALL_STYLES)}")
    if style == "wall_only":
        return _wall_only_grid(
            item, zone, spec_feature, held, wall, height, angle, wall_style,
            (box, base_z), options,
        )
    if style == "wavy_base":
        if depth <= 0.0 or height <= 0.0 or wall <= 0.0 or depth >= height:
            raise ValueError(
                f"{item.name}: bore depth must be below its positive height and wall"
            )
        return _wall_only_grid(
            item, zone, spec_feature, held, wall, height, angle, "wavy",
            (box, base_z), options, style="wavy_base", depth=depth,
        )
    if depth <= 0.0 or height <= 0.0 or wall <= 0.0 or depth >= height:
        raise ValueError(
            f"{item.name}: bore depth must be below its positive height and wall"
        )
    if not math.isfinite(angle) or not (-1e-9 <= angle <= BORE_MAX_TILT + 1e-9):
        raise ValueError(
            f"bore lean angle must be between 0 and {BORE_MAX_TILT:g} degrees off vertical"
        )

    # Every hole leans the same way by the same amount, tilting about its own
    # mouth on the flat top face. The pitch on the lean axis grows by
    # 1 / cos(angle), preserving the wall between the parallel holes.
    tilted = angle > 1e-9
    lean = math.radians(angle) if tilted else 0.0
    lean_axis, lean_sign = bore_direction(spec_feature)
    reach = depth * math.sin(lean)           # sideways travel of the hole bottom
    drop = depth * math.cos(lean)            # how far the bottom sits below the mouth
    pitch_x, pitch_y = bore_minimum_pitches(item.profile, held, wall, angle, lean_axis)
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width - (reach if lean_axis == "x" else 0.0), pitch_x, pitch_x
    )
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth - (reach if lean_axis == "y" else 0.0), pitch_y, pitch_y
    )
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {item.name}: zone is too small for a bore")

    # An angled blind hole needs the block tall enough to keep its bottom
    # buried. Grow the auto height to suit; a hand-set height that is too
    # short is an error rather than a silent breakthrough.
    if tilted:
        need_height = drop + 2.0
        if spec_feature.options.get("height") is not None:
            if height < need_height - 1e-6:
                raise ValueError(
                    f"an angled bore needs at least {need_height:.1f} mm of height "
                    f"but {height:.1f} mm is set"
                )
        else:
            height = max(height, need_height)

    needed_x = columns * pitch_x + (reach if lean_axis == "x" else 0.0)
    needed_y = rows * pitch_y + (reach if lean_axis == "y" else 0.0)
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )

    # Keep holes on their minimum printable pitch. Extra Base material remains
    # a centred outer margin; only Wall changes the gap between holes.

    centre_x, centre_y = zone.centre
    sections = _hole_sides(item.profile)
    hole_radius = held / 2.0 / (math.cos(math.pi / sections) if sections < 8 else 1.0)
    over = max(2.0, held)                    # stub above the top face for a clean mouth
    chamfer = min(BORE_MOUTH_CHAMFER, depth / 3.0, wall / 3.0)
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = lean_sign * reach / 2.0
    return {
        "item": item, "zone": zone, "held": held, "depth": depth, "wall": wall,
        "height": height, "angle": angle, "tilted": tilted, "lean": lean,
        "lean_axis": lean_axis, "lean_sign": lean_sign, "reach": reach, "drop": drop,
        "lean_shift": lean_shift, "pitch": min(pitch_x, pitch_y), "pitch_x": pitch_x,
        "pitch_y": pitch_y, "columns": columns,
        "rows": rows, "centre_x": centre_x, "centre_y": centre_y,
        "sections": sections, "hole_radius": hole_radius, "over": over,
        "chamfer": chamfer,
    }


def _bore_hole_centres(grid: dict, count: int | None):
    """(x, y) mouth centres for every hole in a resolved grid, in order."""
    columns, rows = grid["columns"], grid["rows"]
    pitch_x, pitch_y = grid["pitch_x"], grid["pitch_y"]
    centre_x, centre_y = grid["centre_x"], grid["centre_y"]
    lean_axis, lean_shift = grid["lean_axis"], grid["lean_shift"]
    made = 0
    for row in range(rows):
        for column in range(columns):
            if count is not None and made >= count:
                return
            x = centre_x + (column - (columns - 1) / 2.0) * pitch_x
            y = centre_y + (row - (rows - 1) / 2.0) * pitch_y
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift
            yield x, y
            made += 1


def bore_hole_axes(
    box: BoxSpec, spec_feature: Feature, base_z: float
) -> list[tuple[tuple[float, float, float], ...]]:
    """Centre-line polylines for a leaned bore's holes, in world coordinates:
    ``(bottom, mouth, tip)`` where ``tip`` is a short stub above the mouth that
    carries the preview arrow. Empty for an upright grid - nothing to point out.
    """
    grid = _bore_grid(box, spec_feature, base_z)
    if not grid["tilted"]:
        return []
    lean, lean_axis, lean_sign = grid["lean"], grid["lean_axis"], grid["lean_sign"]
    depth, held = grid["depth"], grid["held"]
    height = grid["height"]
    stub = max(10.0, held)
    # Unit vector up the hole and out of the block - opposite the way the buried
    # bottom shifts. Mirrors the per-hole tilt in ``build_bore``; the block
    # itself never rotates, so these points need no further transform.
    if lean_axis == "x":
        up = (lean_sign * math.sin(lean), 0.0, math.cos(lean))
    else:
        up = (0.0, lean_sign * math.sin(lean), math.cos(lean))
    mouth_z = base_z + height
    axes = []
    for x, y in _bore_hole_centres(grid, spec_feature.count):
        mouth = (x, y, mouth_z)
        bottom = (x - up[0] * depth, y - up[1] * depth, mouth_z - up[2] * depth)
        tip = (x + up[0] * stub, y + up[1] * stub, mouth_z + up[2] * stub)
        axes.append((bottom, mouth, tip))
    return axes


def bore_tool_clearance_zone(
    box: BoxSpec, spec_feature: Feature, base_z: float,
) -> "Zone | None":
    """Tool envelope from each bore mouth to the bin rim.

    The tool is an infinite cylinder on its bore axis.  A bin side exists only
    below the rim, and that part of a straight ray is bounded by its mouth and
    rim endpoints.  The returned rectangle includes the held-tool radius.
    """
    # Avoid making the bore geometry module depend on layout validation at
    # import time.
    from ._core import Zone

    grid = _bore_grid(box, spec_feature, base_z)
    if not grid["tilted"]:
        return None
    rise_to_rim = box.z - (base_z + grid["height"])
    if rise_to_rim <= 1e-9:
        return None

    outward = rise_to_rim * math.tan(grid["lean"])
    radius = grid["held"] / 2.0
    xs: list[float] = []
    ys: list[float] = []
    for x, y in _bore_hole_centres(grid, spec_feature.count):
        rim_x = x + grid["lean_sign"] * outward if grid["lean_axis"] == "x" else x
        rim_y = y + grid["lean_sign"] * outward if grid["lean_axis"] == "y" else y
        xs.extend((x - radius, x + radius, rim_x - radius, rim_x + radius))
        ys.extend((y - radius, y + radius, rim_y - radius, rim_y + radius))
    return Zone(min(xs), min(ys), max(xs), max(ys))


@feature(
    "bore", title="Bore", display="Bore — upright tools",
    description="Small pockets for your stuff of vary sizes/shapes.",
    capabilities=("size", "along", "item"),
    options=(
        OptionDefinition("Style", "bore_style", "full_base", "enum"),
        OptionDefinition("Wall style", "wall_style", "wavy", "enum"),
        OptionDefinition("Height", "height", ""),
        OptionDefinition("Hole depth", "depth", ""),
        OptionDefinition("Wall", "wall", "1.6"),
        OptionDefinition("X quantity", "columns", "", "integer"),
        OptionDefinition("Y quantity", "rows", "", "integer"),
        OptionDefinition("Angle °", "angle", "0"),
        OptionDefinition("Angle towards", "angle_towards", "front", "enum", False),
        OptionDefinition("Auto base size", "auto_base", False, "boolean", False),
        OptionDefinition("Auto height", "auto_height", False, "boolean", False),
        OptionDefinition("Auto X/Y count", "auto_grid", False, "boolean", False),
    ), order=30,
)
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
    grid = _bore_grid(box, spec_feature, base_z)
    join = bool(spec_feature.options.get(WALL_JOIN_FLAG))
    if grid.get("bore_style") == "wall_only":
        return [_build_wall_only_bore(grid, spec_feature.count, box, join)]
    if grid.get("bore_style") == "wavy_base":
        return [_build_wavy_base_bore(grid, spec_feature.count, box, join)]
    zone = grid["zone"]
    held = grid["held"]
    depth = grid["depth"]
    wall = grid["wall"]
    height = grid["height"]
    tilted = grid["tilted"]
    lean = grid["lean"]
    lean_axis = grid["lean_axis"]
    lean_sign = grid["lean_sign"]
    pitch_x = grid["pitch_x"]
    pitch_y = grid["pitch_y"]
    columns = grid["columns"]
    rows = grid["rows"]
    centre_x = grid["centre_x"]
    centre_y = grid["centre_y"]

    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))

    sections = grid["sections"]
    hole_radius = grid["hole_radius"]
    over = grid["over"]                      # stub above the top face for a clean mouth
    chamfer = grid["chamfer"]
    # Centre the lean in the zone's slack so the leaning bottoms stay balanced.
    lean_shift = grid["lean_shift"]

    holes = []
    made = 0
    for row in range(rows):
        for column in range(columns):
            if spec_feature.count is not None and made >= spec_feature.count:
                break
            x = centre_x + (column - (columns - 1) / 2.0) * pitch_x
            y = centre_y + (row - (rows - 1) / 2.0) * pitch_y
            if lean_axis == "x":
                x += lean_shift
            else:
                y += lean_shift

            shaft = trimesh.creation.cylinder(
                radius=hole_radius, height=depth + over, sections=sections,
            )
            if _axis_square(grid["item"].profile):
                shaft.apply_transform(
                    trimesh.transformations.rotation_matrix(math.pi / 4.0, (0.0, 0.0, 1.0))
                )
            shaft.apply_translation((0.0, 0.0, (over - depth) / 2.0))
            parts = [shaft]
            if chamfer > 1e-6:
                mouth = trimesh.creation.revolve(
                    [
                        (0.0, -chamfer),
                        (hole_radius, -chamfer),
                        (hole_radius + chamfer, 0.0),
                        (0.0, 0.0),
                    ],
                    sections=sections,
                )
                if _axis_square(grid["item"].profile):
                    mouth.apply_transform(
                        trimesh.transformations.rotation_matrix(
                            math.pi / 4.0, (0.0, 0.0, 1.0)
                        )
                    )
                parts.append(mouth)
            hole = union(parts) if len(parts) > 1 else parts[0]

            if tilted:
                # Rotate the hole toward the selected compass direction.
                axis = (0.0, 1.0, 0.0) if lean_axis == "x" else (1.0, 0.0, 0.0)
                sign = lean_sign if lean_axis == "x" else -lean_sign
                hole.apply_transform(
                    trimesh.transformations.rotation_matrix(sign * lean, axis)
                )
            hole.apply_translation((x, y, base_z + height))
            holes.append(hole)
            made += 1
    # The block stays an upright rectangular prism - flat top and bottom, plumb
    # sides. Only the holes lean inside it (each was tilted about its own mouth
    # above), and the zone was widened by ``reach`` to keep the leaning bottoms
    # buried. The whole block is never rotated.
    result = difference([block, union(holes)])
    return [result]


register_setting_interactions("bore", (
    SettingInteraction("depth", "height", "constraint", "bore-shell",
                       "A user-edited Hole depth wins and raises Height to keep a 2 mm floor."),
    SettingInteraction("height", "depth", "constraint", "bore-shell",
                       "A user-edited Height wins and lowers Hole depth to keep a 2 mm floor."),
    SettingInteraction("angle", "wall", "default", "bore",
                       "A leaned Bore uses a thicker wall unless Wall is explicitly set."),
    SettingInteraction("bore_style", "angle", "reset", "bore-editor",
                       "Wall Only and Wavy Base stand upright, so choosing one removes a stored lean."),
    SettingInteraction("bore_style", "wall", "default", "bore",
                       "Wall Only and Wavy Base take the bin wall unless Wall is explicitly set."),
    SettingInteraction("bore_style", "zone", "auto-adjust", "bore-sizing",
                       "Wall Only and Wavy Base size the Base to the sleeves' outer envelope; "
                       "Wavy Base also sizes the bin around it."),
    SettingInteraction("wall_style", "zone", "auto-adjust", "bore-sizing",
                       "Wavy walls reach further than straight walls."),
    SettingInteraction("angle", "angle_towards", "enable/disable", "bore-editor",
                       "Direction is shown only for a Bore that is actually leaned."),
    SettingInteraction("item.profile", "angle", "reset", "bore-editor",
                       "Hex-bit presets stand upright and remove a stored lean."),
    SettingInteraction("item.profile", "item.diameter", "default", "bore",
                       "Hex-bit presets own their fixed across-flats diameter."),
    SettingInteraction("columns", "zone", "auto-adjust", "bore-sizing",
                       "X quantity grows the Bore Base to its minimum printable width."),
    SettingInteraction("rows", "zone", "auto-adjust", "bore-sizing",
                       "Y quantity grows the Bore Base to its minimum printable length."),
    SettingInteraction("item.diameter", "zone", "auto-adjust", "bore-sizing",
                       "Hole diameter grows the Base footprint."),
    SettingInteraction("wall", "zone", "auto-adjust", "bore-sizing",
                       "Wall thickness grows the Base footprint."),
    SettingInteraction("angle", "zone", "auto-adjust", "bore-sizing",
                       "Lean grows the Base along the selected direction."),
    SettingInteraction("angle_towards", "zone", "auto-adjust", "bore-sizing",
                       "Lean direction determines which Base axis receives the extra reach."),
))
