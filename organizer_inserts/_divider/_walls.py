"""Divider wall and full-span divider solids."""

from __future__ import annotations

import math
from dataclasses import replace
import trimesh
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from organizer_engine import (
    BoxSpec,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    flat_cavity_polygon,
    wavy_cavity_polygon,
    wall_depth_for,
    wave_value,
)
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    intersection,
    union,
)
from .._core import Feature, Zone

from ._consts import MAX_DIVIDER_ANGLE, MIN_WEDGE_EDGE, DIVIDER_CHAMFER


def _divider_wall(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """A straight or leaning divider, up to ``MAX_DIVIDER_ANGLE`` off vertical.

    A thin wall sheared over bodily at an angle is an unsupported FDM
    overhang with no more material at its base than anywhere else along its
    height - exactly the shape that snaps off under the sideways load of
    whatever is leaning against it. The default instead builds a wedge: the
    top keeps the asked-for ``thickness`` and leans over by ``lean``, while
    the base widens on the trailing side to a vertical face, so the wall is
    thickest right where that load actually bears - at the floor - and
    slims to the asked-for thickness at the top, the shape a physical gusset
    or bracket would use. ``wedge=False`` gets the plain sheared wall
    instead: uniform thickness throughout, for the rare case that is
    genuinely wanted.

    Every divider - wedge, straight or plain vertical - also gets a
    ``DIVIDER_CHAMFER`` 45-degree foot where it meets the floor: the two
    long faces flare out by that much at ``base_z`` and taper back to the
    wall's own line by ``DIVIDER_CHAMFER`` above it. It is a pure addition
    below the wall's nominal profile, not a substitute for any of it, so
    the lean and thickness above that point are exactly what was asked for.
    """
    if not math.isfinite(angle) or abs(angle) > MAX_DIVIDER_ANGLE:
        raise ValueError(
            f"a divider's angle must be within {MAX_DIVIDER_ANGLE:g} degrees of vertical"
        )
    if height <= DIVIDER_CHAMFER:
        raise ValueError(
            f"a divider must stand taller than its {DIVIDER_CHAMFER:g} mm base chamfer"
        )
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
    along = spec_feature.along
    cross_centre = centre_y if along == "x" else centre_x
    lean = height * math.tan(math.radians(angle))
    wavy = spec_feature.options.get("wall_style", "straight") == "wavy"
    half_t = (wall_depth_for(thickness) if wavy else thickness) / 2.0
    base_low, base_high = cross_centre - half_t, cross_centre + half_t
    if thickness < MIN_WEDGE_EDGE:
        raise ValueError(
            f"a divider must be at least {MIN_WEDGE_EDGE:g} mm thick"
        )
    if spec_feature.wedge:
        # The top slab keeps the asked-for thickness but leans over by
        # ``lean``; the base holds one face vertical and widens on the
        # trailing side to meet it, so the wedge is thick at the floor.
        top_low, top_high = base_low + lean, base_high + lean
        if lean >= 0.0:
            base_high = top_high
        else:
            base_low = top_low
    else:
        top_low, top_high = base_low + lean, base_high + lean
    # Where the wall's own (un-chamfered) line would sit at chamfer height -
    # the chamfer's inner edge lands exactly here, so the taper above it is
    # untouched.
    frac = DIVIDER_CHAMFER / height
    chamfer_low = base_low + frac * (top_low - base_low)
    chamfer_high = base_high + frac * (top_high - base_high)
    chamfer_z = base_z + DIVIDER_CHAMFER
    profile = Polygon([
        (base_low - DIVIDER_CHAMFER, base_z), (base_high + DIVIDER_CHAMFER, base_z),
        (chamfer_high, chamfer_z), (top_high, base_z + height),
        (top_low, base_z + height), (chamfer_low, chamfer_z),
    ])
    if not profile.is_valid:
        raise ValueError("that divider angle and thickness do not form a valid wall")
    run = zone.width if along == "x" else zone.depth
    if wavy:
        run_centre = centre_x if along == "x" else centre_y
        return [_wavy_divider_profile(profile, along, run_centre, run)]
    if along == "x":
        wall = _extrude_yz_profile(profile, run)
        wall.apply_translation((centre_x, 0.0, 0.0))
    else:
        wall = _extrude_xz_profile(profile, run)
        wall.apply_translation((0.0, centre_y, 0.0))
    return [wall]


def _wavy_divider_profile(
    profile: Polygon, along: str, centre: float, run: float,
) -> trimesh.Trimesh:
    """Sweep the existing lean/wedge/foot profile on the global wave phase."""
    ring = list(profile.exterior.coords)[:-1]
    count = len(ring)
    steps = max(2, math.ceil(run / (WAVE_LENGTH / 8)))
    runs = [centre - run / 2.0 + run * index / steps for index in range(steps + 1)]
    def vertex(run_coordinate: float, cross: float, z: float):
        shifted = cross + wave_value(run_coordinate)
        return ((run_coordinate, shifted, z) if along == "x"
                else (shifted, run_coordinate, z))
    vertices = [vertex(position, cross, z) for position in runs for cross, z in ring]
    faces = []
    for section in range(steps):
        low, high = section * count, (section + 1) * count
        for index in range(count):
            after = (index + 1) % count
            faces.append((low + index, low + after, high + after))
            faces.append((low + index, high + after, high + index))
    cap_vertices, cap_faces = trimesh.creation.triangulate_polygon(profile, engine="earcut")
    for position, reverse in ((runs[0], True), (runs[-1], False)):
        offset = len(vertices)
        vertices.extend(vertex(position, cross, z) for cross, z in cap_vertices)
        for face in cap_faces:
            triangle = tuple(offset + int(index) for index in face)
            faces.append(triangle[::-1] if reverse else triangle)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not mesh.is_watertight:
        raise ValueError("wavy divider wall did not form a closed volume")
    return mesh


def _full_span_leaning_divider(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
    *,
    full_span_cavity: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """A leaning divider that also reaches the box's true wavy wall.

    Full span and a lean each bend one of the same assumption in a
    different place: a full-span divider's run-axis reach is the wave, not
    the safe rectangle; a leaning divider's cross-axis position shifts with
    height instead of staying put. Together, the divider's own end face is
    no longer flat, or even the same shape at every height, so the 2D
    polygon-clip the plain full-span divider uses no longer applies on its
    own. This instead builds the oversized leaning wedge as a real 3D solid
    - exactly what ``_divider_wall`` already builds (base chamfer included),
    just wider - and intersects it against the box's actual interior
    volume, the same boolean a standalone insert is already trimmed to its
    footprint with.
    """
    along = spec_feature.along
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre

    if full_span_cavity is not None:
        minx, miny, maxx, maxy = full_span_cavity.bounds
        half_span_x = (maxx - minx) / 2.0 + 2.0
        half_span_y = (maxy - miny) / 2.0 + 2.0
        half_run = half_span_x if along == "x" else half_span_y
        oversized_zone = (
            Zone(centre_x - half_run, zone.y0, centre_x + half_run, zone.y1)
            if along == "x" else
            Zone(zone.x0, centre_y - half_run, zone.x1, centre_y + half_run)
        )
        wedge = _divider_wall(
            box, replace(spec_feature, zone=oversized_zone), thickness, height,
            angle, base_z,
        )[0]
        prism = _extrude_polygon(full_span_cavity, height)
        prism.apply_translation((0.0, 0.0, base_z))
        piece = intersection([wedge, prism])
        if piece is None or len(piece.faces) == 0:
            raise ValueError("no room for a leaning full-width divider at this position")
        return [piece]

    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    oversized_zone = (
        Zone(centre_x - half_run, zone.y0, centre_x + half_run, zone.y1)
        if along == "x" else
        Zone(zone.x0, centre_y - half_run, zone.x1, centre_y + half_run)
    )
    wedge = _divider_wall(
        box, replace(spec_feature, zone=oversized_zone), thickness, height,
        angle, base_z,
    )[0]

    z0, z1 = base_z, base_z + height
    flat_top = box.base_thickness + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        band = _extrude_polygon(flat_cavity_polygon(box), min(z1, flat_top) - z0)
        band.apply_translation((0.0, 0.0, z0))
        pieces.append(intersection([wedge, band]))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        above = _extrude_polygon(wavy_cavity_polygon(box), z1 - wavy_z0)
        above.apply_translation((0.0, 0.0, wavy_z0))
        pieces.append(intersection([wedge, above]))
    if not pieces or any(len(piece.faces) == 0 for piece in pieces):
        raise ValueError("no room for a leaning full-width divider at this position")
    return pieces


def _trimmed_prism(strip: Polygon, cavity: Polygon, z0: float, z1: float) -> trimesh.Trimesh:
    """``strip`` cut back to wherever ``cavity`` actually allows it, then extruded."""
    trimmed = strip.intersection(cavity)
    if trimmed.is_empty:
        raise ValueError("no room for a full-width divider at this position")
    if isinstance(trimmed, MultiPolygon):
        trimmed = max(trimmed.geoms, key=lambda item: item.area)
    prism = _extrude_polygon(trimmed, z1 - z0)
    prism.apply_translation((0.0, 0.0, z0))
    return prism


def _full_span_divider(
    box: BoxSpec, along: str, cross_centre: float, thickness: float,
    base_z: float, height: float,
    *,
    full_span_cavity: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """A divider that runs edge to edge, hugging the box's true interior wall.

    A straight rib sized to the safe usable rectangle - the only rectangle
    guaranteed to clear the wave at *every* position - still leaves the
    wave's own swing as a gap at most positions, because that rectangle is
    pulled in by a full amplitude just to stay valid everywhere. A divider
    only has to be right at its own position, so instead it is built
    oversized and trimmed back against the box's real interior outline: the
    flat, straight-sided band near the floor if the box has one, the wavy
    profile above it - exactly the same outlines the wall itself is built
    from, so the two can never disagree.
    """
    if height <= DIVIDER_CHAMFER:
        raise ValueError("a divider must stand taller than its base chamfer")
    half_thick = thickness / 2.0
    z0, z1 = base_z, base_z + height
    pieces: list[trimesh.Trimesh] = []

    def foot_layers(cavity: Polygon, low: float, high: float) -> list[trimesh.Trimesh]:
        # The regular wall profile already owns this foot. This clip-and-extrude
        # path is its sole missing case. Keep the foot just inside the real
        # cavity edge: the main rib makes the wall join, while coincident
        # stepped foot edges there leave zero-volume boolean slivers.
        steps = 5
        layers = []
        foot_cavity = cavity.buffer(-0.1)
        if foot_cavity.is_empty:
            return layers
        for index in range(steps):
            foot_z0 = z0 + index * DIVIDER_CHAMFER / steps
            foot_z1 = z0 + (index + 1) * DIVIDER_CHAMFER / steps
            lo, hi = max(low, foot_z0), min(high, foot_z1)
            if hi <= lo:
                continue
            grow = DIVIDER_CHAMFER * (steps - index) / steps
            half = half_thick + grow
            bounds = cavity.bounds
            expanded = (
                shapely_box(bounds[0] - 1.0, cross_centre - half,
                            bounds[2] + 1.0, cross_centre + half)
                if along == "x" else
                shapely_box(cross_centre - half, bounds[1] - 1.0,
                            cross_centre + half, bounds[3] + 1.0)
            )
            layers.append(_trimmed_prism(expanded, foot_cavity, lo, hi))
        return layers

    def band(strip: Polygon, cavity: Polygon, low: float, high: float) -> trimesh.Trimesh:
        main = _trimmed_prism(strip, cavity, low, high)
        return union([main, *foot_layers(cavity, low, high)])

    if full_span_cavity is not None:
        minx, miny, maxx, maxy = full_span_cavity.bounds
        if along == "x":
            strip = shapely_box(minx - 1.0, cross_centre - half_thick, maxx + 1.0, cross_centre + half_thick)
        else:
            strip = shapely_box(cross_centre - half_thick, miny - 1.0, cross_centre + half_thick, maxy + 1.0)
        pieces.append(band(strip, full_span_cavity, z0, z1))
        return pieces

    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    strip = (
        shapely_box(-half_run, cross_centre - half_thick, half_run, cross_centre + half_thick)
        if along == "x" else
        shapely_box(cross_centre - half_thick, -half_run, cross_centre + half_thick, half_run)
    )
    flat_top = box.base_thickness + box.flat_inside
    if box.flat_inside > 0.0 and z0 < flat_top:
        cavity = flat_cavity_polygon(box)
        pieces.append(band(strip, cavity, z0, min(z1, flat_top)))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        cavity = wavy_cavity_polygon(box)
        pieces.append(band(strip, cavity, wavy_z0, z1))
    if not pieces:
        raise ValueError("divider height leaves nothing to build")
    return pieces
