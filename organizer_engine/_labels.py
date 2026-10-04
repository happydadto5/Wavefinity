"""Wavefinity engine text, top-label, scoop and label-placement geometry."""

from __future__ import annotations

from functools import cache
from dataclasses import dataclass
import math
from typing import Iterable
import numpy as np
import trimesh
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath
from shapely.affinity import rotate as rotate_polygon, translate as translate_polygon
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from shapely.ops import unary_union
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
    intersection,
    union,
)

from ._specs import (
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_CAP_HEIGHT_MIN,
    TEXT_DEPTH,
    TEXT_MIN_BACKING,
    TEXT_MARGIN,
    TEXT_FONT_FAMILY,
    TEXT_FONT_WEIGHT,
    TOP_LABEL_LEDGE_DEPTH,
    TOP_LABEL_CAP_HEIGHT,
    TOP_LABEL_CAP_HEIGHT_WARNING,
    TOP_LABEL_MARGIN,
    TOP_LABEL_RIM_CLEARANCE,
    SCOOP_HEIGHT_FRACTION,
    SCOOP_FLOOR_TOLERANCE,
    SCOOP_CURVE_SEGMENTS,
    BoxSpec,
)
from ._wave import wavy_outer_polygon
from ._boxes import make_box


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# floor label
# --------------------------------------------------------------------------- #
def _font() -> FontProperties:
    return FontProperties(family=TEXT_FONT_FAMILY, weight=TEXT_FONT_WEIGHT)


@cache
def _cap_ratio() -> float:
    """Cap height per unit of font size, for this font.

    ``TextPath`` takes a font size, but a letter's height is what matters here,
    so every size is expressed as a cap height and converted through this.
    """
    reference = TextPath((0.0, 0.0), "X", size=100.0, prop=_font())
    bounds = reference.get_extents()
    return (bounds.y1 - bounds.y0) / 100.0


def text_outline(label: str, cap_height: float) -> Polygon | MultiPolygon:
    """Filled outline of ``label``, centred on the origin, letters ``cap_height`` tall.

    Glyph contours arrive as a flat list of rings with no nesting information,
    so a ring's depth - how many larger rings enclose it - decides whether it is
    a shell or a hole.  That is what keeps the middle of an O open.
    """
    if not label.strip():
        raise ValueError("label is empty")
    if cap_height <= 0:
        raise ValueError("cap height must be positive")

    path = TextPath(
        (0.0, 0.0), label, size=cap_height / _cap_ratio(), prop=_font()
    )
    rings = []
    for ring in path.to_polygons():
        if len(ring) < 3:
            continue
        polygon = Polygon(ring)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.area <= 0:
            continue
        rings.append(polygon)
    if not rings:
        raise ValueError(f"'{label}' has no printable outline")

    rings.sort(key=lambda item: item.area, reverse=True)
    shells, holes = [], []
    for index, ring in enumerate(rings):
        probe = ring.representative_point()
        depth = sum(1 for bigger in rings[:index] if bigger.contains(probe))
        (holes if depth % 2 else shells).append(ring)

    filled = unary_union(shells)
    if holes:
        filled = filled.difference(unary_union(holes))
    if filled.is_empty:
        raise ValueError(f"'{label}' has no printable outline")

    minx, miny, maxx, maxy = filled.bounds
    return translate_polygon(
        filled, xoff=-(minx + maxx) / 2.0, yoff=-(miny + maxy) / 2.0
    )


def _rim_label_side(side: str) -> str:
    value = str(side or "back").strip().lower()
    if value == "top":
        value = "back"
    if value not in ("front", "back", "left", "right"):
        raise ValueError("rim shelf must be at the front, back, left, or right")
    return value


def top_label_surface_z(box: BoxSpec) -> float:
    """Top of the rim-label shelf, just below the stack/lid mouth clearance."""
    return box.z - TOP_LABEL_RIM_CLEARANCE


def top_label_zone(box: BoxSpec, side: str = "back") -> Polygon:
    """Floor-plan area reserved by a rim-label ledge."""
    side = _rim_label_side(side)
    inside_x, inside_y = box.usable_inside
    across = inside_y if side in ("front", "back") else inside_x
    if across < TOP_LABEL_LEDGE_DEPTH - 1e-9:
        raise ValueError(
            f"a rim label needs at least {TOP_LABEL_LEDGE_DEPTH:g} mm of usable "
            f"room; this bin has {across:.1f} mm"
        )
    if side == "back":
        return shapely_box(-inside_x / 2.0, inside_y / 2.0 - TOP_LABEL_LEDGE_DEPTH,
                           inside_x / 2.0, inside_y / 2.0)
    if side == "front":
        return shapely_box(-inside_x / 2.0, -inside_y / 2.0,
                           inside_x / 2.0, -inside_y / 2.0 + TOP_LABEL_LEDGE_DEPTH)
    if side == "left":
        return shapely_box(-inside_x / 2.0, -inside_y / 2.0,
                           -inside_x / 2.0 + TOP_LABEL_LEDGE_DEPTH, inside_y / 2.0)
    return shapely_box(inside_x / 2.0 - TOP_LABEL_LEDGE_DEPTH, -inside_y / 2.0,
                       inside_x / 2.0, inside_y / 2.0)


def _top_label_fit(
    box: BoxSpec, label: str, side: str = "back"
) -> tuple[float, Polygon | MultiPolygon]:
    """Return the largest rim-label cap height and outline that fit its shelf."""
    side = _rim_label_side(side)
    surface_z = top_label_surface_z(box)
    if surface_z - TOP_LABEL_LEDGE_DEPTH < box.base_thickness - 1e-9:
        raise ValueError(
            f"this bin is too short for a rim label: the shelf needs "
            f"{TOP_LABEL_LEDGE_DEPTH:g} mm below the rim clearance "
            f"at the rim, and this bin does not leave that much above its floor"
        )
    top_label_zone(box, side)
    probe = text_outline(label, TOP_LABEL_CAP_HEIGHT)
    minx, miny, maxx, maxy = probe.bounds
    inside_x, inside_y = box.usable_inside
    room_x = (inside_x if side in ("front", "back") else inside_y) - 2.0 * TOP_LABEL_MARGIN
    room_y = TOP_LABEL_LEDGE_DEPTH - 2.0 * TOP_LABEL_MARGIN
    width, height = maxx - minx, maxy - miny
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"'{label}' has no printable outline")
    cap_height = TOP_LABEL_CAP_HEIGHT * min(1.0, room_x / width, room_y / height)
    if cap_height <= 0.0:
        raise ValueError(f"'{label}' has no room on the rim label ledge")
    outline = text_outline(label, cap_height)
    turn = {"back": 0.0, "front": 180.0, "left": 90.0, "right": -90.0}[side]
    if turn:
        outline = rotate_polygon(outline, turn, origin=(0.0, 0.0))
    offsets = {
        "back": (0.0, inside_y / 2.0 - TOP_LABEL_LEDGE_DEPTH / 2.0),
        "front": (0.0, -inside_y / 2.0 + TOP_LABEL_LEDGE_DEPTH / 2.0),
        "left": (-inside_x / 2.0 + TOP_LABEL_LEDGE_DEPTH / 2.0, 0.0),
        "right": (inside_x / 2.0 - TOP_LABEL_LEDGE_DEPTH / 2.0, 0.0),
    }
    xoff, yoff = offsets[side]
    return cap_height, translate_polygon(outline, xoff=xoff, yoff=yoff)


def top_label_outline(
    box: BoxSpec, label: str, side: str = "back"
) -> Polygon | MultiPolygon:
    """Rim-label text, reduced from 5 mm only when its shelf needs it."""
    _cap_height, outline = _top_label_fit(box, label, side)
    return outline


def make_top_label_ledge(box: BoxSpec, side: str = "back") -> trimesh.Trimesh:
    """Rim label shelf with a 45-degree self-supporting underside.

    The shelf runs the full selected wall span. It is cut across the whole
    outer envelope and then trimmed back to the wavy walls.
    """
    side = _rim_label_side(side)
    inside_x, inside_y = box.usable_inside
    envelope_polygon = wavy_outer_polygon(box)
    minx, miny, maxx, maxy = envelope_polygon.bounds
    top_z = top_label_surface_z(box)
    low_z = top_z - TOP_LABEL_LEDGE_DEPTH
    if side in ("front", "back"):
        wall = (inside_y / 2.0) if side == "back" else (-inside_y / 2.0)
        inward = -1.0 if side == "back" else 1.0
        outer = maxy if side == "back" else miny
        profile = Polygon([
            (wall + inward * TOP_LABEL_LEDGE_DEPTH, top_z),
            (outer, top_z), (outer, low_z), (wall, low_z),
        ])
        ledge = _extrude_yz_profile(profile, maxx - minx)
    else:
        wall = (-inside_x / 2.0) if side == "left" else (inside_x / 2.0)
        inward = 1.0 if side == "left" else -1.0
        outer = minx if side == "left" else maxx
        profile = Polygon([
            (wall + inward * TOP_LABEL_LEDGE_DEPTH, top_z),
            (outer, top_z), (outer, low_z), (wall, low_z),
        ])
        ledge = _extrude_xz_profile(profile, maxy - miny)
    # Trim the ends back to just inside the wavy side walls.  Cutting a hair
    # shy of the real wall surface keeps the shelf buried in wall material -
    # it merges with the body cleanly instead of leaving coincident faces.
    trim = _extrude_polygon(envelope_polygon.buffer(-0.1), box.z + 2.0)
    trim.apply_translation((0.0, 0.0, -1.0))
    ledge = intersection([ledge, trim])
    ledge.remove_unreferenced_vertices()
    ledge.merge_vertices()
    return ledge


def make_top_label(box: BoxSpec, label: str, side: str = "back") -> trimesh.Trimesh:
    """The separate-colour inlay that finishes flush with the shelf surface."""
    return text_prism(top_label_outline(box, label, side), top_label_surface_z(box))


def make_top_labelled_box(
    box: BoxSpec,
    label: str,
    body: trimesh.Trimesh | None = None,
    side: str = "back",
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Add the rim shelf and return its pocketed body plus flush text inlay."""
    with_ledge = union([
        make_box(box) if body is None else body,
        make_top_label_ledge(box, side),
    ])
    inlay = make_top_label(box, label, side)
    pocketed = difference([with_ledge, inlay])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed, inlay


def _scoop_bounds(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float, float]:
    if floor_bounds is None:
        inside_x, inside_y = box.usable_inside
        return -inside_x / 2.0, -inside_y / 2.0, inside_x / 2.0, inside_y / 2.0
    x0, y0, x1, y1 = floor_bounds
    if not all(math.isfinite(value) for value in floor_bounds) or x1 <= x0 or y1 <= y0:
        raise ValueError("scoop floor bounds must have positive finite width and depth")
    return x0, y0, x1, y1


def scoop_dimensions(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> tuple[float, float]:
    """Return the scoop's vertical rise and front-to-back run."""
    _x0, y0, _x1, y1 = _scoop_bounds(box, floor_bounds)
    height = (box.z - box.base_thickness) * SCOOP_HEIGHT_FRACTION
    # Normal bins get a circular quarter curve.  Very shallow floor plans keep
    # the requested half-wall rise with an elliptical curve that still leaves
    # usable floor in front of it.
    run = min(height, (y1 - y0) * 0.5)
    if height <= 0.0 or run <= 0.0:
        raise ValueError("this box is too small for a scoop")
    return height, run


def scoop_floor_zone(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> Polygon:
    """Floor-plan strip occupied by the front scoop."""
    x0, y0, x1, _y1 = _scoop_bounds(box, floor_bounds)
    _height, run = scoop_dimensions(box, floor_bounds)
    return shapely_box(x0, y0, x1, y0 + run)


def scoop_keep_out(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
    tolerance: float = SCOOP_FLOOR_TOLERANCE,
) -> Polygon:
    """The part of the scoop strip a support genuinely cannot stand on.

    The curve meets the floor tangentially, so its innermost millimetres are
    only microns proud of it - on a 40 mm bin the scoop is 0.03 mm high one
    millimetre in.  Reserving the whole run as if it were a wall rejected
    supports that in fact sit flat, so the strip stops where the curve has
    risen ``tolerance`` above the floor.  The profile is
    ``rise = height * (1 - cos(phi))`` at ``run * sin(phi)`` in from that
    meeting point, which inverts to the offset below.
    """
    x0, y0, x1, _y1 = _scoop_bounds(box, floor_bounds)
    height, run = scoop_dimensions(box, floor_bounds)
    inner = y0 + run
    if tolerance > 0.0:
        gained = min(1.0, max(0.0, tolerance / height))
        inner -= run * math.sin(math.acos(1.0 - gained))
    return shapely_box(x0, y0, x1, max(y0 + min(run, 0.5), inner))


def make_scoop(
    box: BoxSpec,
    floor_bounds: tuple[float, float, float, float] | None = None,
) -> trimesh.Trimesh:
    """Full-width curved retrieval ramp rising halfway up the front wall.

    The concave face looks back into the bin, so a part can be swept forward
    and lifted out over the low front lip.
    """
    x0, wall_y, x1, _y1 = _scoop_bounds(box, floor_bounds)
    height, run = scoop_dimensions(box, floor_bounds)
    return build_scoop_region(
        (x0, wall_y, x1, wall_y + run), box.base_thickness, height, "x"
    )


def build_scoop_region(
    bounds: tuple[float, float, float, float],
    floor_z: float,
    height: float,
    along: str = "x",
) -> trimesh.Trimesh:
    """Build the authoritative curved Scoop profile inside one floor region.

    ``along`` is the direction of the wall edge: ``x`` rises from the region's
    low-Y edge and ``y`` rises from its low-X edge. Containers decide which
    region receives the Scoop; this function owns the shared profile math.
    """
    x0, y0, x1, y1 = bounds
    if (
        not all(math.isfinite(value) for value in (*bounds, floor_z, height))
        or x1 <= x0 or y1 <= y0 or height <= 0.0
    ):
        raise ValueError("a scoop needs positive finite bounds and height")
    if along not in {"x", "y"}:
        raise ValueError("scoop orientation must be 'x' or 'y'")

    centre_z = floor_z + height
    if along == "x":
        wall, inner, run = y0, y1, y1 - y0
    else:
        wall, inner, run = x0, x1, x1 - x0
    curve = [
        (
            inner - run * math.cos(theta),
            centre_z + height * math.sin(theta),
        )
        for theta in np.linspace(0.0, -math.pi / 2.0, SCOOP_CURVE_SEGMENTS + 1)
    ]
    profile = Polygon([
        (inner, floor_z),
        (wall, floor_z),
        (wall, centre_z),
        *curve[1:-1],
    ])
    if not profile.is_valid:
        raise ValueError("invalid scoop profile generated")
    if along == "x":
        scoop = _extrude_yz_profile(profile, x1 - x0)
        scoop.apply_translation(((x0 + x1) / 2.0, 0.0, 0.0))
    else:
        scoop = _extrude_xz_profile(profile, y1 - y0)
        scoop.apply_translation((0.0, (y0 + y1) / 2.0, 0.0))
    scoop.remove_unreferenced_vertices()
    scoop.merge_vertices()
    return scoop


@dataclass(frozen=True)
class LabelPlacement:
    cap_height: float
    rotated: bool
    x: float = 0.0
    y: float = 0.0
    quarter_turns: int = 0


def _label_candidates(
    room: Polygon, occupied: tuple[Polygon, ...], width: float, height: float
) -> Iterable[tuple[float, float]]:
    """Useful positions beside obstacle edges, then a complete 1 mm fallback."""
    minx, miny, maxx, maxy = room.bounds
    low_x, high_x = minx + width / 2.0, maxx - width / 2.0
    low_y, high_y = miny + height / 2.0, maxy - height / 2.0
    if low_x > high_x + 1e-9 or low_y > high_y + 1e-9:
        return

    xs = {0.0, low_x, high_x}
    ys = {0.0, low_y, high_y}
    for obstacle in occupied:
        ox0, oy0, ox1, oy1 = obstacle.bounds
        xs.update((ox0 - width / 2.0, ox1 + width / 2.0, (ox0 + ox1) / 2.0))
        ys.update((oy0 - height / 2.0, oy1 + height / 2.0, (oy0 + oy1) / 2.0))
    xs = {min(max(value, low_x), high_x) for value in xs}
    ys = {min(max(value, low_y), high_y) for value in ys}
    candidates = {(x, y) for x in xs for y in ys}
    ordered = sorted(
        candidates,
        key=lambda point: (point[0] ** 2 + point[1] ** 2,
                           abs(point[1]), abs(point[0]), point[1], point[0]),
    )
    yield from ordered

    # Obstacles can make a useful location unrelated to another edge (for
    # example a narrow corridor). Cover the remaining floor at the editor's
    # one-millimetre resolution. Typical bins are only a few thousand points.
    x = math.ceil(low_x)
    while x <= high_x + 1e-9:
        y = math.ceil(low_y)
        while y <= high_y + 1e-9:
            candidate = (float(x), float(y))
            if candidate not in candidates:
                yield candidate
            y += 1
        x += 1


def _oriented_outline(
    label: str, cap_height: float, quarter_turns: int
) -> Polygon | MultiPolygon:
    """``label`` at ``cap_height`` turned ``quarter_turns`` x 90 deg, centred."""
    outline = text_outline(label, cap_height)
    if quarter_turns % 4:
        outline = rotate_polygon(outline, 90.0 * (quarter_turns % 4),
                                 origin=(0.0, 0.0), use_radians=False)
    minx, miny, maxx, maxy = outline.bounds
    return translate_polygon(
        outline, xoff=-(minx + maxx) / 2.0, yoff=-(miny + maxy) / 2.0
    )


def _cap_steps(max_cap: float, floor: float = TEXT_CAP_HEIGHT_MIN) -> list[float]:
    """Cap heights from ``max_cap`` down to ``floor``, always ending exactly at
    ``floor``."""
    caps: list[float] = []
    cap = max_cap
    while cap >= floor - 1e-9:
        caps.append(max(cap, floor))
        cap -= 0.25
    if not caps or caps[-1] > floor + 1e-9:
        caps.append(floor)
    return caps


def label_placement(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
) -> LabelPlacement:
    """Largest legal label position, automatically moved around insert zones.

    Text stays centred when it can, then moves beside the obstacles, then turns,
    and finally shrinks - never below ``TEXT_CAP_HEIGHT_MIN``.  This is what a
    ``text`` interior part with ``auto`` set uses to find its own spot, and what
    the plain ``box --label`` command uses for its single centred floor label.
    """
    inside_x, inside_y = box.usable_inside
    room_x = inside_x - 2.0 * TEXT_MARGIN
    room_y = inside_y - 2.0 * TEXT_MARGIN
    if room_x <= 0 or room_y <= 0:
        raise ValueError("this box has no floor area to label")

    room = shapely_box(-room_x / 2.0, -room_y / 2.0,
                       room_x / 2.0, room_y / 2.0)
    obstacles = tuple(
        polygon.buffer(TEXT_MARGIN, join_style="mitre")
        for polygon in occupied if not polygon.is_empty
    )

    ideal = text_outline(label, TEXT_CAP_HEIGHT_IDEAL)
    minx, miny, maxx, maxy = ideal.bounds
    ideal_width, ideal_height = maxx - minx, maxy - miny

    orientations: list[tuple[bool, float]] = []
    for rotated in (False, True):
        across, up = ((ideal_height, ideal_width) if rotated
                      else (ideal_width, ideal_height))
        max_cap = min(TEXT_CAP_HEIGHT_IDEAL,
                      TEXT_CAP_HEIGHT_IDEAL * room_x / across,
                      TEXT_CAP_HEIGHT_IDEAL * room_y / up)
        if max_cap < TEXT_CAP_HEIGHT_MIN - 1e-9:
            continue
        orientations.append((rotated, max_cap))

    if orientations and not obstacles:
        # Pick the direction that keeps the letters largest. Prefer the natural
        # reading direction only when both orientations are equally good.
        rotated, max_cap = max(
            orientations, key=lambda choice: (choice[1], not choice[0])
        )
        return LabelPlacement(max_cap, rotated, quarter_turns=1 if rotated else 0)

    # Try both directions at each available size before shrinking further.
    # Including each orientation's exact maximum avoids throwing away useful
    # fractions of a millimetre merely because the two maxima differ.
    cap_steps = sorted({
        cap for _rotated, max_cap in orientations for cap in _cap_steps(max_cap)
    }, reverse=True)
    for cap in cap_steps:
        for rotated, max_cap in orientations:
            if cap > max_cap + 1e-9:
                continue
            turns = 1 if rotated else 0
            outline = text_outline(label, cap)
            if rotated:
                outline = rotate_polygon(outline, 90.0, origin=(0.0, 0.0),
                                         use_radians=False)
            bx0, by0, bx1, by1 = outline.bounds
            width, height = bx1 - bx0, by1 - by0
            footprint = shapely_box(-width / 2.0, -height / 2.0,
                                    width / 2.0, height / 2.0)
            for x, y in _label_candidates(room, obstacles, width, height):
                placed = translate_polygon(footprint, xoff=x, yoff=y)
                if room.covers(placed) and all(not placed.intersects(o) for o in obstacles):
                    return LabelPlacement(cap, rotated, x, y, turns)

    longest = max(room_x, room_y)
    needed = ideal_width * (TEXT_CAP_HEIGHT_MIN / TEXT_CAP_HEIGHT_IDEAL)
    obstacle_note = " around the insert features" if obstacles else ""
    raise ValueError(
        f"'{label}' will not fit on this floor{obstacle_note} either way round: it needs "
        f"{needed:.1f} mm at the {TEXT_CAP_HEIGHT_MIN:.0f} mm minimum letter "
        f"height and the floor gives {longest:.1f} mm. Use a shorter label or "
        f"a bigger box"
    )


def label_layout(box: BoxSpec, label: str) -> tuple[float, bool]:
    """Backward-compatible size/orientation result for an unobstructed floor."""
    placement = label_placement(box, label)
    return placement.cap_height, placement.rotated


def placed_label_outline(
    box: BoxSpec, label: str, occupied: Iterable[Polygon] = (),
) -> Polygon | MultiPolygon:
    """The label's final 2D shape, turned and moved clear of insert features."""
    placement = label_placement(box, label, occupied)
    outline = _oriented_outline(label, placement.cap_height, placement.quarter_turns)
    return translate_polygon(outline, xoff=placement.x, yoff=placement.y)


def require_text_backing(
    surface_thickness: float, depth: float, what: str = "recessed text",
) -> None:
    """Reject a recessed label that would leave no material behind it.

    Shared by the floor label, the general text feature and divider labels so
    the same rule applies everywhere text is sunk into a surface rather than
    stood proud on it.
    """
    remaining = surface_thickness - depth
    if remaining < TEXT_MIN_BACKING - 1e-9:
        raise ValueError(
            f"{what} {depth:g} mm deep leaves only {remaining:.2f} mm behind it "
            f"on a {surface_thickness:.2f} mm surface; needs at least "
            f"{TEXT_MIN_BACKING:g} mm of backing. Make it shallower, thicken "
            f"the surface, or stand it proud instead"
        )


def text_prism(
    outline: Polygon | MultiPolygon,
    top_z: float,
    depth: float = TEXT_DEPTH,
    raised: bool = False,
) -> trimesh.Trimesh:
    """Lettering turned into a solid, referenced to the surface it sits on.

    ``top_z`` is that surface - a bin floor, an insert plate, a rim ledge.
    Recessed (the default) the solid occupies the ``depth`` immediately below
    it, so it fills a pocket cut to match and the finished surface stays flat.
    Raised, it stands on the surface instead.  Either way it stays a separate
    object in the 3MF, which is what lets a slicer give it its own filament.

    This is the one place glyph outlines become geometry: the plain floor
    label, the rim ledge label and every ``text`` interior part share it.
    """
    if depth <= 0.0:
        raise ValueError("text depth must be positive")
    pieces = list(outline.geoms) if isinstance(outline, MultiPolygon) else [outline]
    if not pieces:
        raise ValueError("this text has no printable outline")
    solid = union([_extrude_polygon(piece, depth) for piece in pieces])
    solid.apply_translation((0.0, 0.0, top_z if raised else top_z - depth))
    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return solid


def make_floor_label(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
    top_z: float | None = None,
) -> trimesh.Trimesh:
    """The solid that fills the label pocket, flush with the floor.

    It sits in the top ``TEXT_DEPTH`` of the floor rather than standing on it,
    so the finished floor is flat and the lettering is an inlay.  It is a
    separate object in the 3MF so a slicer can give it its own filament.
    """
    outline = placed_label_outline(box, label, occupied)
    top_z = box.base_thickness if top_z is None else top_z
    require_text_backing(top_z, TEXT_DEPTH, what="floor label")
    return text_prism(outline, top_z)


def make_labelled_box(
    box: BoxSpec,
    label: str,
    occupied: Iterable[Polygon] = (),
    body: trimesh.Trimesh | None = None,
    top_z: float | None = None,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """``(box with the label pocket cut, the solid that fills it)``.

    The two share faces and nothing else, which is exactly what a slicer wants
    from a two-material part.
    """
    inlay = make_floor_label(box, label, occupied, top_z)
    pocketed = difference([make_box(box) if body is None else body, inlay])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed, inlay


def label_report(
    box: BoxSpec, label: str, occupied: Iterable[Polygon] = (),
) -> dict[str, object]:
    placement = label_placement(box, label, occupied)
    outline = _oriented_outline(label, placement.cap_height, placement.quarter_turns)
    minx, miny, maxx, maxy = outline.bounds
    across, up = maxx - minx, maxy - miny
    return {
        "label": label,
        "cap_height_mm": round(placement.cap_height, 3),
        "rotated": placement.rotated,
        "quarter_turns": placement.quarter_turns,
        "position_mm": [round(placement.x, 3), round(placement.y, 3)],
        "footprint_mm": [round(across, 3), round(up, 3)],
        "depth_mm": TEXT_DEPTH,
    }


def top_label_report(box: BoxSpec, label: str, side: str = "back") -> dict[str, object]:
    normalized_side = _rim_label_side(side)
    cap_height, outline = _top_label_fit(box, label, normalized_side)
    minx, miny, maxx, maxy = outline.bounds
    report = {
        "label": label,
        "position": "top" if normalized_side == "back" else normalized_side,
        "side": normalized_side,
        "cap_height_mm": round(cap_height, 3),
        "rotated": normalized_side in ("left", "right"),
        "footprint_mm": [round(maxx - minx, 3), round(maxy - miny, 3)],
        "ledge_depth_mm": TOP_LABEL_LEDGE_DEPTH,
        "ledge_surface_z_mm": round(top_label_surface_z(box), 3),
        "ledge_underside_degrees": 45.0,
        "depth_mm": TEXT_DEPTH,
    }
    if cap_height < TOP_LABEL_CAP_HEIGHT_WARNING - 1e-9:
        report["warning"] = (
            f"'{label}' was reduced to {cap_height:.1f} mm letters. "
            f"Below {TOP_LABEL_CAP_HEIGHT_WARNING:g} mm may be hard to read."
        )
    return report
