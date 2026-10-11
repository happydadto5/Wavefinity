"""Preview helpers: feature geometry, reference meshes, clearance validation and surface base."""

from __future__ import annotations

from typing import Iterable
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import box as shape_box
from organizer_engine import (
    BoxSpec,
    make_scoop,
    lift_grabber_collision_volumes,
    lid_stackable,
    flat_cavity_polygon,
    scoop_keep_out,
    top_label_zone,
    translated,
    difference,
)
from organizer_stack import stack_enabled
from organizer_inserts._bore import bore_reference_meshes
from organizer_inserts import (
    CRADLE_FLOOR_GAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    bore_hole_axes,
    build_features,
    connector_keep_out,
    divider_division_texts,
    feature_footprint,
    insert_footprint,
    is_text,
    layout_zone,
    make_insert_plate,
    text_is_raised,
    text_of,
    text_placed_outline,
)
from .._common import (
    SURFACE_BASE_CELL_MM,
    SURFACE_BASE_TOP_SKIN_MM,
    SURFACE_BASE_CELL_INSET_MM,
    SURFACE_BASE_MIN_OPENING_MM,
    SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM,
    rim_label_side,
    clean_label,
    base_height,
)


def _feature_height(box: BoxSpec, one: Feature, base_z: float) -> float:
    options = one.options
    if one.kind == "cradle" and one.item is not None:
        # Fixed clearance: a legacy saved floor_gap is ignored, as in the geometry.
        return base_z + CRADLE_FLOOR_GAP + one.item.widest / 2.0
    if one.kind == "bore" and one.item is not None:
        depth = options.get("depth", min(one.item.length * 0.4, box.z - base_z - 2.0))
        return base_z + options.get("height", depth + 2.0)
    if one.kind == "nest":
        tool_thickness = float(options.get("tool_thickness", options.get("depth", 8.0)))
        if options.get("holder_style", "raised_wall") == "recessed":
            cavity_depth = (
                float(options.get("cavity_depth", 0.6 * tool_thickness))
                if options.get("cavity_depth_mode", "auto") == "manual"
                else 0.6 * tool_thickness
            )
            return base_z + min(cavity_depth, tool_thickness)
        lift = (
            float(options.get("push_depth", 4.0))
            if options.get("lift_assist", "auto") == "push_out"
            else 0.0
        )
        return base_z + tool_thickness + lift
    if one.kind == "divider":
        return base_z + options.get("height", connector_keep_out(box) - base_z)
    return base_z + options.get("height", 12.0)


def _prism_geometry(zone: Zone, z0: float, z1: float, kind: str) -> list[tuple]:
    a = (zone.x0, zone.y0)
    b = (zone.x1, zone.y0)
    c = (zone.x1, zone.y1)
    d = (zone.x0, zone.y1)
    return [
        ([(*a, z0), (*b, z0), (*b, z1), (*a, z1)], kind, (0.0, -1.0, 0.0), 0, None),
        ([(*b, z0), (*c, z0), (*c, z1), (*b, z1)], kind, (1.0, 0.0, 0.0), 0, None),
        ([(*c, z0), (*d, z0), (*d, z1), (*c, z1)], kind, (0.0, 1.0, 0.0), 0, None),
        ([(*d, z0), (*a, z0), (*a, z1), (*d, z1)], kind, (-1.0, 0.0, 0.0), 0, None),
        ([(*a, z1), (*b, z1), (*c, z1), (*d, z1)], kind, (0.0, 0.0, 1.0), 0, None),
    ]


def _bore_axis_geometry(
    box: BoxSpec, one: Feature, base_z: float, kind: str
) -> list[tuple]:
    """Centre-line polylines for a leaned bore, so the preview can draw an arrow
    up each hole showing which way it points. Empty for anything but an angled
    bore, and silent if the bore itself will not resolve."""
    if one.kind != "bore":
        return []
    try:
        axes = bore_hole_axes(box, one, base_z)
    except Exception:
        return []
    return [
        ([tuple(float(v) for v in point) for point in polyline],
         kind, (0.0, 0.0, 1.0), 9, None)
        for polyline in axes
    ]


def _valid_preview_floor_ring(
    cavity: Iterable[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Return a simple ring for triangulating the preview floor.

    preview_rings() intentionally returns matched coarse outer/cavity
    samples so the vertical wall quads can be stitched point-for-point.
    On narrow bins the raw cavity walk can make a tiny self-intersection
    at a corner.  That is harmless for the wall-strip preview but it must
    not be handed to the browser as one polygon for triangulation.
    """
    polygon = Polygon(cavity)

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if isinstance(polygon, MultiPolygon):
        polygon = max(polygon.geoms, key=lambda one: one.area)

    if (
        not isinstance(polygon, Polygon)
        or polygon.is_empty
        or not polygon.is_valid
    ):
        raise RuntimeError("preview floor did not produce a valid polygon")

    # Shapely closes exterior.coords by repeating the first point.
    # The browser triangulator expects an open vertex list.
    return [
        (float(x), float(y))
        for x, y in list(polygon.exterior.coords)[:-1]
    ]


def _floor_faces_with_text_pockets(floor_cavity, floor_z, outlines):
    """Floor faces with inlaid-Text glyph holes cut out (plain fused path).

    ``floor_cavity`` is the validated open ring from
    ``_valid_preview_floor_ring``; ``outlines`` are the 2D glyph outlines of
    the effective inlaid base-Text set, in the same preview coordinates.
    Returns face tuples ``(points, kind, normal, layer, owner)`` with kind
    ``"floor"``.

    Each resulting component is triangulated with a hole-respecting
    (constrained) earcut triangulation. Shapely's unconstrained Delaunay
    ``triangulate`` refills holes, and filtering its triangles with
    ``component.covers(tri)`` leaves gaps in the floor wherever the Delaunay
    edges do not follow the glyph outline, so it is not used. Triangles are
    the emission unit so the 2D painter and the GL renderer need no new
    polygon-with-holes support, and ``floorZ`` still resolves from the
    ``floor``-kind faces. If the triangulation ever fails its own area check,
    the helper returns the original uncut ring - today's rendering, never a
    new breakage.
    """
    plain = [([(*point, floor_z) for point in floor_cavity],
              "floor", (0.0, 0.0, 1.0), 1, None)]
    try:
        cut = Polygon(floor_cavity)
        for outline in outlines:
            cut = cut.difference(outline)
        if cut.is_empty:
            return plain
        components = cut.geoms if isinstance(cut, MultiPolygon) else [cut]
        faces = []
        area = 0.0
        for component in components:
            if not isinstance(component, Polygon) or component.is_empty:
                continue
            vertices, triangles = trimesh.creation.triangulate_polygon(component)
            for corner in triangles:
                (x0, y0), (x1, y1), (x2, y2) = (
                    (float(vertices[i][0]), float(vertices[i][1])) for i in corner)
                twice = (x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1)
                if abs(twice) / 2.0 < PREVIEW_MIN_FACE_AREA:
                    continue
                ring = [(x0, y0), (x1, y1), (x2, y2)]
                if twice < 0:
                    ring.reverse()
                area += abs(twice) / 2.0
                faces.append(([(x, y, floor_z) for x, y in ring],
                              "floor", (0.0, 0.0, 1.0), 1, None))
        if not faces or abs(area - cut.area) > 1e-4 * cut.area:
            return plain
        return faces
    except Exception:
        return plain


# A preview pixel covers roughly a tenth of a millimetre of model even at full
# zoom, so a micron is far below anything the browser can draw.  Rounding there
# costs nothing visible and makes the payload it has to parse much smaller.
PREVIEW_DECIMALS = 3
# A triangle this small is a boolean sliver, not a surface: a millionth of a
# preview pixel.  Its neighbours already tile the shape it sits in.
PREVIEW_MIN_FACE_AREA = 1e-4


def _mesh_preview_geometry(
    mesh, kind: str, owner: str | None = None
) -> list[tuple]:
    """Convert a finished holder mesh into camera-independent preview faces.

    A B4B case runs to well over a hundred thousand triangles, so this works in
    numpy rather than per vertex in Python, drops slivers too small to paint,
    and rounds to the micron.  Same picture; a fraction of the build time and of
    the JSON the browser then has to parse.

    ``owner`` is the physical part ("base"/"lid") a face belongs to. It is
    only ever passed by the B4B preview walk, which knows which source mesh
    each face came from; ordinary-bin geometry leaves it ``None``.
    """
    layer = int(mesh.metadata.get("wavefinity_preview_layer", 0) or 0)
    preview_kind = mesh.metadata.get("wavefinity_preview_kind")
    if preview_kind and "invalid" not in kind and "conflict" not in kind:
        kind = f"{kind}_{preview_kind}"
    triangles = np.asarray(mesh.triangles, dtype=float)
    if not len(triangles):
        return []
    keep = np.asarray(mesh.area_faces, dtype=float) > PREVIEW_MIN_FACE_AREA
    corners = np.round(triangles[keep], PREVIEW_DECIMALS).tolist()
    normals = np.round(
        np.asarray(mesh.face_normals, dtype=float)[keep], PREVIEW_DECIMALS
    ).tolist()
    # numpy has already produced plain lists; re-wrapping several hundred
    # thousand of them in tuples costs more than everything else here put
    # together, and nothing downstream needs them to be tuples.
    return [
        (triangle, kind, normal, layer, owner)
        for triangle, normal in zip(corners, normals)
    ]


def _reference_preview_meshes(box: BoxSpec, one: Feature, base_z: float) -> list[trimesh.Trimesh]:
    if one.kind == "bore" and one.item is not None:
        return bore_reference_meshes(box, one, base_z)
    if one.kind == "nest" and not one.contour:
        return []
    ref = one.reference_object
    if ref is None:
        return []
    x, y = one.zone.centre
    mesh = trimesh.creation.box(extents=(ref.width, ref.depth, ref.height))
    mesh.apply_translation((x, y, base_z + ref.height / 2.0))
    return [mesh]


def bore_reference_envelope_extensions(
    box: BoxSpec, layout: Layout,
) -> dict[str, float]:
    """Millimetres a leaned Bore's stored-object reference reaches past the bin.

    This deliberately measures the same `bore_reference_meshes()` that Preview
    draws. No angle, segment, or item geometry is re-derived here.
    """
    base_z = base_height(box, layout.mode)
    half_x, half_y = box.x / 2.0, box.y / 2.0
    result = {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}
    for one in layout.features:
        if one.kind != "bore" or one.item is None:
            continue
        for mesh in bore_reference_meshes(box, one, base_z):
            minx, miny = float(mesh.bounds[0][0]), float(mesh.bounds[0][1])
            maxx, maxy = float(mesh.bounds[1][0]), float(mesh.bounds[1][1])
            result["l"] = max(result["l"], -half_x - minx)
            result["t"] = max(result["t"], -half_y - miny)
            result["r"] = max(result["r"], maxx - half_x)
            result["b"] = max(result["b"], maxy - half_y)
    return {side: max(0.0, value) for side, value in result.items()}


def _customization_zones(
    box: BoxSpec,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> list[tuple[str, Zone]]:
    """Floor-plan keep-outs for fixed bin customizations."""
    zones: list[tuple[str, Zone]] = []
    side = rim_label_side(label_location)
    if clean_label(label) and side:
        zones.append(("rim label ledge", Zone(*top_label_zone(box, side).bounds)))
    if scoop:
        zones.append(
            ("scoop", Zone(*scoop_keep_out(box, _scoop_floor_bounds(box, mode)).bounds))
        )
    return zones


def validate_inside_handles_mode(box: BoxSpec, mode: str) -> None:
    if box.lift_grabbers.enabled and mode != "fused":
        raise ValueError(
            "Inside Grip is built into the bin wall and cannot be used "
            "with Removable insert. Choose Fused into box or remove Inside Grip."
        )


def _feature_z_range(
    box: BoxSpec, one: Feature, base_z: float, mode: str,
) -> tuple[float, float]:
    solids = build_features(
        box, [one], base_z, layout_zone(box, mode), mode=mode, include_text=True,
    )
    if not solids:
        return base_z, _feature_height(box, one, base_z)
    return (
        min(float(solid.bounds[0][2]) for solid in solids),
        max(float(solid.bounds[1][2]) for solid in solids),
    )


def inside_handle_conflict(
    box: BoxSpec, one: Feature, base_z: float, mode: str,
) -> str | None:
    if not box.lift_grabbers.enabled:
        return None
    if is_text(one) and one.options.get("level") == "rim":
        from organizer_inserts._text import rim_text_geometry
        ledge, glyph, _cap, _surface = rim_text_geometry(box, one)
        footprint = top_label_zone(box, one.options.get("rim_side", "back"))
        z0 = min(float(ledge.bounds[0][2]), float(glyph.bounds[0][2]))
        z1 = max(float(ledge.bounds[1][2]), float(glyph.bounds[1][2]))
    else:
        footprint = text_placed_outline(one) if is_text(one) else feature_footprint(box, one, base_z).polygon
        try:
            z0, z1 = _feature_z_range(box, one, base_z, mode)
        except Exception:
            return None
    for name, polygon, h0, h1 in lift_grabber_collision_volumes(box):
        xy_overlap = footprint.buffer(MIN_FEATURE_GAP).intersects(polygon)
        z_overlap = z1 + MIN_FEATURE_GAP > h0 and h1 + MIN_FEATURE_GAP > z0
        if xy_overlap and z_overlap:
            return name
    return None


def _scoop_floor_bounds(
    box: BoxSpec, mode: str
) -> tuple[float, float, float, float] | None:
    if mode == "fused":
        return None
    return insert_footprint(box, mode).bounds


def _removable_scoop(box: BoxSpec, mode: str):
    return translated(
        make_scoop(box, _scoop_floor_bounds(box, mode)),
        (0.0, 0.0, -box.base_thickness),
    )


def _surface_base_cutter(cx: float, cy: float, opening: float, roof_top: float) -> trimesh.Trimesh:
    """Open-bottom square cavity with a manifold 45 degree closing roof."""
    tip = 0.05
    roof_start = roof_top - (opening - tip) / 2.0
    rings = ((-SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM, opening),
             (roof_start, opening), (roof_top, tip))
    vertices = []
    for z, width in rings:
        half = width / 2.0
        vertices.extend(((cx - half, cy - half, z), (cx + half, cy - half, z),
                         (cx + half, cy + half, z), (cx - half, cy + half, z)))
    faces = [(0, 3, 2), (0, 2, 1), (8, 9, 10), (8, 10, 11)]
    for lower in (0, 4):
        for side in range(4):
            a, b = lower + side, lower + (side + 1) % 4
            faces.extend(((a, b, b + 4), (a, b + 4, a + 4)))
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def apply_surface_lightweight_base(body: trimesh.Trimesh, box: BoxSpec,
                                   layout: Layout) -> trimesh.Trimesh:
    """Remove hidden 8 mm cell cavities from a Surface platform only."""
    if not layout.surface_lightweight_base:
        return body
    if box.b4b.enabled or stack_enabled(box) or lid_stackable(box):
        raise ValueError("Lightweight base is unavailable with vertical stacking")
    roof_top = box.base_thickness - SURFACE_BASE_TOP_SKIN_MM
    max_opening = min(SURFACE_BASE_CELL_MM - 2 * SURFACE_BASE_CELL_INSET_MM,
                      2.0 * roof_top)
    if max_opening < SURFACE_BASE_MIN_OPENING_MM:
        return body
    safe = flat_cavity_polygon(box)
    protected = [shape_box(one.zone.x0, one.zone.y0, one.zone.x1, one.zone.y1).buffer(1.0)
                 for one in layout.features if not is_text(one)]
    cutters = []
    for ix in range(round(box.x / SURFACE_BASE_CELL_MM)):
        cx = -box.x / 2.0 + (ix + 0.5) * SURFACE_BASE_CELL_MM
        for iy in range(round(box.y / SURFACE_BASE_CELL_MM)):
            cy = -box.y / 2.0 + (iy + 0.5) * SURFACE_BASE_CELL_MM
            low, high = 0.0, max_opening
            for _ in range(18):
                width = (low + high) / 2.0
                half = width / 2.0
                square = shape_box(cx - half, cy - half, cx + half, cy + half)
                if safe.covers(square) and not any(square.intersects(zone) for zone in protected):
                    low = width
                else:
                    high = width
            if low >= SURFACE_BASE_MIN_OPENING_MM:
                cutters.append(_surface_base_cutter(cx, cy, low, roof_top))
    if not cutters:
        return body
    return difference([body, trimesh.util.concatenate(cutters)])


def _preview_base_texts(features, draft, selected):
    """The effective inlaid base-Text set for the preview pocket work.

    Resolved saved features with ``selected`` replaced by the live ``draft``
    (when a draft exists). Rim, raised, blank and non-Text features are
    excluded. Divider labels are not Text features and never enter this set.
    """
    effective = [
        one for index, one in enumerate(features)
        if not (draft is not None and selected is not None and index == selected)
    ]
    if draft is not None:
        effective.append(draft)
    return [
        one for one in effective
        if is_text(one)
        and one.options.get("level") != "rim"
        and not text_is_raised(one)
        and (text_of(one) or "").strip()
    ]


def insert_plate_solid(box: BoxSpec, mode: str):
    """The standalone insert's base plate, sitting on the bin floor.

    ``None`` in fused mode, where the holders grow out of the floor and there
    is no plate.  Built from the same footprint the exporter uses, so what the
    preview draws is the part that comes out of the printer - inset by
    ``INSERT_CLEARANCE`` all round, with rounded corners, rather than flush to
    the wall where its edges are invisible.
    """
    if mode == "fused":
        return None
    return translated(
        make_insert_plate(box, mode), (0.0, 0.0, box.base_thickness)
    )


def validate_customization_clearance(
    box: BoxSpec,
    features: Iterable[Feature],
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> None:
    features = list(features)
    base_z = base_height(box, mode)
    for index, one in enumerate(features):
        if is_text(one) and one.options.get("level") == "rim":
            handle_conflict = inside_handle_conflict(box, one, base_z, mode)
            if handle_conflict is not None:
                raise ValueError(
                    f"rim Label on {one.options.get('rim_side', 'back')} overlaps the "
                    f"{handle_conflict}; choose another rim side or move the handle"
                )
            continue
        # A default divider's zone can span most of the floor even though its
        # actual printed wall is a narrow strip - judge the customization
        # keep-outs against what is really built, not the editor's drag zone.
        # Always use the actual footprint, regardless of fused vs removable mode.
        footprint = feature_footprint(box, one, base_z)
        physical = text_placed_outline(one) if is_text(one) else footprint.polygon
        for name, zone in _customization_zones(
            box, label, label_location, scoop, mode
        ):
            if physical.distance(zone.polygon) < MIN_FEATURE_GAP:
                raise ValueError(
                    f"interior part {index + 1} ({one.kind}) overlaps the {name}; "
                    "move or resize the part in the 2D layout"
                )
        handle_conflict = inside_handle_conflict(box, one, base_z, mode)
        if handle_conflict is not None:
            raise ValueError(
                f"interior part {index + 1} ({one.kind}) overlaps the "
                f"{handle_conflict}; move, resize, or lower the part"
            )


def validate_rim_text_divider_clearance(box: BoxSpec, features: Iterable[Feature], base_z: float) -> None:
    """Keep independently built rim Text and Divider label shelves apart."""
    features = tuple(features)
    rims = [one for one in features if is_text(one) and one.options.get("level") == "rim"]
    dividers = [one for one in features if one.kind == "divider"
                and one.options.get("label_divisions")
                and one.options.get("division_level") == "rim"]
    if not rims or not dividers:
        return
    from organizer_inserts._text import rim_text_geometry
    for rim in rims:
        ledge, glyph, _cap, _surface = rim_text_geometry(box, rim)
        for divider in dividers:
            for _name, shelf_or_text, _raised in divider_division_texts(box, divider, base_z):
                a, b = ledge.bounds, shelf_or_text.bounds
                xy = (a[0][0] < b[1][0] and b[0][0] < a[1][0]
                      and a[0][1] < b[1][1] and b[0][1] < a[1][1])
                z = a[0][2] < b[1][2] and b[0][2] < a[1][2]
                if xy and z:
                    raise ValueError(
                        "rim Label overlaps a Divider rim label shelf; move the Label "
                        "to another rim side or turn off one label system"
                    )
