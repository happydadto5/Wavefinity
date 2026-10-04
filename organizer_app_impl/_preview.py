"""Wavefinity preview geometry and customization validation."""

from __future__ import annotations

import math
from typing import Iterable
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import box as shape_box
from organizer_engine import (
    BoxSpec,
    make_scoop,
    make_top_label_ledge,
    make_lift_grabbers,
    lift_grabber_collision_volumes,
    lid_stackable,
    preview_rings,
    make_box,
    flat_cavity_polygon,
    scoop_keep_out,
    top_label_outline,
    top_label_report,
    top_label_surface_z,
    top_label_zone,
    translated,
    difference,
)
from organizer_edge_mount import (
    apply_edge_mount_hole_cuts,
    apply_edge_mount_structure,
    edge_mount_summary,
    edge_mount_text_object,
    make_edge_mount_label_part,
)
from organizer_side_openings import (
    apply_side_openings,
    side_opening_summary,
    validate_side_openings,
)
from organizer_pegboard import apply_pegboard_mount_structure, receiver_layout
from organizer_stack import stack_enabled
from organizer_inserts._bore import bore_reference_meshes, bore_tool_clearance_zone
from organizer_inserts._cradle import cradle_reference_meshes
from organizer_inserts import (
    CRADLE_FLOOR_GAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    apply_texts,
    bore_hole_axes,
    build_features,
    connector_keep_out,
    divider_division_texts,
    feature_footprint,
    insert_footprint,
    is_text,
    layout_to_dict,
    layout_zone,
    make_insert_plate,
    occupied_zones,
    nest_contour_polygon,
    resolve_nest_settings,
    resolve_text_features,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)

from ._common import (
    SURFACE_BASE_CELL_MM,
    SURFACE_BASE_TOP_SKIN_MM,
    SURFACE_BASE_CELL_INSET_MM,
    SURFACE_BASE_MIN_OPENING_MM,
    SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM,
    label_position,
    rim_label_side,
    validate_scoop_lift_grabbers,
    validate_side_opening_label,
    validate_edge_mount_label_conflicts,
    clean_label,
    base_height,
    _text_fits,
    _canonical_rim_label,
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
    if one.kind == "cradle" and one.item is not None:
        return cradle_reference_meshes(box, one, base_z)
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
                    f"rim Text on {one.options.get('rim_side', 'back')} overlaps the "
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
                        "rim Text overlaps a Divider rim label shelf; move the Text "
                        "to another rim side or turn off one label system"
                    )


def preview_geometry(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused", label_location: str = "bottom", scoop: bool = False,
    draft: Feature | None = None, selected: int | None = None,
    layout: Layout | None = None,
) -> dict[str, object]:
    """Build camera-independent preview geometry once per design change.

    ``draft`` is the interior part currently being edited, not yet added to
    the layout - included in the same geometry, tagged ``draft_<kind>``
    instead of ``feature_<kind>``/``insert_<kind>`` so the browser can
    highlight it in place, right where it will actually sit, instead of
    drawing it alone on its own tiny canvas. It never affects
    ``feature_errors`` or ``invalid_feature_indexes`` - those describe the
    real layout - and a draft that fails to build still falls back to the
    same placeholder prism a placed feature would, reported through
    ``draft_error`` instead.
    """
    migrated, label, label_location = _canonical_rim_label(
        box, Layout(tuple(features), mode), label, label_location,
    )
    features = migrated.features
    effective_features = list(features)
    if draft is not None:
        if selected is not None and 0 <= selected < len(effective_features):
            effective_features[selected] = draft
        else:
            effective_features.append(draft)
    active_rim = tuple(one for one in effective_features if is_text(one) and one.options.get("level") == "rim")
    validate_inside_handles_mode(box, mode)
    validate_scoop_lift_grabbers(box, scoop)
    validate_side_openings(box)
    for rim_text in active_rim:
        side = str(rim_text.options.get("rim_side") or "back")
        validate_side_opening_label(box, text_of(rim_text), side)
        validate_edge_mount_label_conflicts(box, text_of(rim_text), side)
        handle_conflict = inside_handle_conflict(box, rim_text, base_height(box, mode), mode)
        if handle_conflict:
            raise ValueError(f"rim Text on {side} overlaps the {handle_conflict}; choose another rim side")
    if not active_rim:
        validate_edge_mount_label_conflicts(box, "", "bottom")   # lid / stack rules need no label

    features = resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, clean_label(label), label_position(label_location), scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )
    validate_rim_text_divider_clearance(box, effective_features, base_height(box, mode))
    outer, cavity = preview_rings(box)
    floor_cavity = _valid_preview_floor_ring(cavity)
    floor_z, rim_z = box.base_thickness, box.z
    geometry: list[tuple[list[tuple[float, float, float]], str,
                          tuple[float, float, float], int, str | None]] = []
    # Preview-only identities. Geometry keeps its physical base/lid owner.
    pick_faces: dict[int, dict[str, object]] = {}
    pick_proxies: list[dict[str, object]] = []

    tidy = clean_label(label)
    location = label_position(label_location)
    rim_side = rim_label_side(location)
    # A fused feature, the scoop, the rim ledge and a live draft each get cut
    # by this below wherever they cross a Screw Mounting hole, so together
    # they show the same physical result as export - without merging any of
    # them into the bin shell's own "outside" geometry, which would misclass
    # interior-part geometry as Bin geometry and break Bin/Interior/Xray.
    cut_fused_pieces = mode == "fused" and box.edge_mount.holes_enabled
    cut_side_opening_pieces = mode == "fused" and box.side_openings.enabled

    # Inlaid base Text: the solids that pocket the receiving surface in preview,
    # exactly as export cuts them (bin shell when fused, insert plate otherwise).
    from organizer_inserts._text import build_text
    base_inlay_meshes = []
    text_pocket_error = None
    for one in _preview_base_texts(features, draft, selected):
        try:
            base_inlay_meshes.extend(build_text(box, one, base_height(box, mode)))
        except Exception:
            continue

    if (box.edge_mount.active or box.side_openings.enabled or box.pegboard.enabled
            or (layout is not None and layout.surface_lightweight_base)):
        # make_box() already includes Lift Grabbers; Edge Mount also adds the
        # Projecting Label plate and cuts the shell's own small screw holes
        # and driver-access openings. Side Openings cut the finished shell
        # last, so the real cut body - not a synthesized wall - is what
        # shows in preview here.
        shell_body = make_box(box)
        if box.edge_mount.active:
            shell_body = apply_edge_mount_structure(box, shell_body)
        if box.pegboard.enabled:
            shell_body = apply_pegboard_mount_structure(box, shell_body)
        if mode == "fused" and base_inlay_meshes:
            try:
                shell_body = apply_texts(
                    shell_body, [("", mesh, False) for mesh in base_inlay_meshes])
            except Exception as error:
                text_pocket_error = f"text pocket: {error}"
        if layout is not None:
            shell_body = apply_surface_lightweight_base(shell_body, box, layout)
        if box.side_openings.enabled:
            shell_body = apply_side_openings(box, shell_body)
        geometry.extend(_mesh_preview_geometry(shell_body, "outside"))
    else:
        count = len(outer)
        for index in range(count):
            a, b = outer[index], outer[(index + 1) % count]
            c, d = cavity[index], cavity[(index + 1) % count]
            run = (b[0] - a[0], b[1] - a[1])
            outward = (run[1], -run[0], 0.0)
            inward = (-run[1], run[0], 0.0)
            geometry.append(([(a[0], a[1], 0.0), (b[0], b[1], 0.0),
                              (b[0], b[1], rim_z), (a[0], a[1], rim_z)],
                             "outside", outward, 0, None))
            geometry.append(([(c[0], c[1], floor_z), (d[0], d[1], floor_z),
                              (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                             "inside", inward, 0, None))
            geometry.append(([(a[0], a[1], rim_z), (b[0], b[1], rim_z),
                              (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                             "rim", (0.0, 0.0, 1.0), 0, None))
        floor_outlines = []
        if mode == "fused":
            for one in _preview_base_texts(features, draft, selected):
                try:
                    floor_outlines.append(text_placed_outline(one))
                except Exception:
                    continue
        if floor_outlines:
            geometry.extend(_floor_faces_with_text_pockets(
                floor_cavity, floor_z, floor_outlines))
        else:
            geometry.append(([(*point, floor_z) for point in floor_cavity],
                             "floor", (0.0, 0.0, 1.0), 1, None))

    if tidy and rim_side:
        ledge_mesh = make_top_label_ledge(box, rim_side)
        if cut_fused_pieces:
            ledge_mesh = apply_edge_mount_hole_cuts(box, ledge_mesh, geometry_owner="rim-label ledge")
        if cut_side_opening_pieces:
            ledge_mesh = apply_side_openings(box, ledge_mesh)
        geometry.extend(_mesh_preview_geometry(ledge_mesh, "top_label_ledge"))
    if scoop:
        scoop_mesh = (
            make_scoop(box)
            if mode == "fused"
            else translated(
                _removable_scoop(box, mode),
                (0.0, 0.0, box.base_thickness),
            )
        )
        # The scoop is fused into the shell, so a hole crossing it should show
        # cut here too. A removable-mode scoop belongs to the insert, which
        # Edge Mount never drills and Side Openings never cut.
        if cut_fused_pieces:
            scoop_mesh = apply_edge_mount_hole_cuts(box, scoop_mesh, geometry_owner="fused scoop")
        if cut_side_opening_pieces:
            scoop_mesh = apply_side_openings(box, scoop_mesh)
        geometry.extend(_mesh_preview_geometry(scoop_mesh, "scoop"))
    # make_box() already bakes lift grabbers into the shell it returns, so
    # only draw them separately when the Edge Mount/Side Openings shell above
    # did not already include them.
    if box.lift_grabbers.enabled and not box.edge_mount.active and not box.side_openings.enabled:
        for grabber_mesh in make_lift_grabbers(box):
            geometry.extend(_mesh_preview_geometry(grabber_mesh, "lift_grabber"))

    plate = insert_plate_solid(box, mode)
    if plate is not None:
        if mode != "fused" and base_inlay_meshes:
            try:
                plate = apply_texts(
                    plate, [("", mesh, False) for mesh in base_inlay_meshes])
            except Exception as error:
                if text_pocket_error is None:
                    text_pocket_error = f"text pocket: {error}"
        geometry.extend(_mesh_preview_geometry(plate, "insert_base"))
    base_z = base_height(box, mode)
    # Holders belong to whichever part they are printed as: the bin when fused,
    # the insert otherwise.  The prefix picks the colour family.
    part_kind = "feature" if mode == "fused" else "insert"
    feature_errors = []
    if text_pocket_error is not None:
        feature_errors.append(text_pocket_error)
    invalid_feature_indexes = []
    conflicting_feature_indexes = []
    feature_overhang_mm = [0.0 for _ in features]
    draft_overhang_mm = 0.0
    draft_error = None
    destinations = {}
    for index, one in enumerate(features):
        if not is_text(one):
            continue
        destination = "rim" if one.options.get("level") == "rim" else "base"
        if destination in destinations:
            feature_errors.append(
                "Only one rim Text is allowed; remove a duplicate" if destination == "rim"
                else "Only one Text is allowed on the base; remove a duplicate"
            )
            invalid_feature_indexes.extend((destinations[destination], index))
        destinations[destination] = index
    if draft is not None and is_text(draft):
        destination = "rim" if draft.options.get("level") == "rim" else "base"
        if destination in destinations and destinations[destination] != selected:
            draft_error = (
                "Only one rim Text is allowed; change the existing rim Text or use Base Text" if destination == "rim"
                else "Only one Text is allowed on the base; change Style or remove the other Text"
            )
    reserved = _customization_zones(box, tidy, location, scoop, mode)

    occupied = [
        None if (is_text(one) and one.options.get("level") == "rim") else zone
        for one, zone in zip(features, occupied_zones(box, features, base_z, mode))
    ]
    preview_bore_tool_paths: dict[int, Zone | None] = {}

    def preview_bore_tool_path(one: Feature) -> Zone | None:
        if one.kind != "bore":
            return None
        key = id(one)
        if key not in preview_bore_tool_paths:
            preview_bore_tool_paths[key] = bore_tool_clearance_zone(box, one, base_z)
        return preview_bore_tool_paths[key]

    def floor_overlap(a: Feature, a_zone: Zone, b: Feature, b_zone: Zone) -> bool:
        if (
            a.kind == "bore"
            and b.kind in ("divider", "post")
            and preview_bore_tool_path(a) is not None
            and preview_bore_tool_path(a).overlaps(feature_footprint(box, b, base_z))
        ) or (
            b.kind == "bore"
            and a.kind in ("divider", "post")
            and preview_bore_tool_path(b) is not None
            and preview_bore_tool_path(b).overlaps(feature_footprint(box, a, base_z))
        ):
            return True
        if mode == "fused" and (is_text(a) or is_text(b)):
            a_shape = text_placed_outline(a) if is_text(a) else a_zone.polygon
            b_shape = text_placed_outline(b) if is_text(b) else b_zone.polygon
            return a_shape.distance(b_shape) < MIN_FEATURE_GAP
        return a_zone.overlaps(b_zone, MIN_FEATURE_GAP)

    if draft is not None:
        if not (is_text(draft) and draft.options.get("level") == "rim"):
            draft_customization_footprint = feature_footprint(box, draft, base_z)
            conflict = next(
                (name for name, zone in reserved if
                 ((text_placed_outline(draft) if is_text(draft) else draft_customization_footprint.polygon)
                  .distance(zone.polygon) < MIN_FEATURE_GAP)),
                None,
            )
            if conflict is not None:
                draft_error = f"{draft.kind}: overlaps the {conflict}"
            else:
                handle_conflict = inside_handle_conflict(box, draft, base_z, mode)
                if handle_conflict is not None:
                    draft_error = f"{draft.kind}: overlaps the {handle_conflict}"
            if draft_error is None:
                try:
                    draft_occ = occupied_zones(box, (draft,), base_z, mode)[0]
                    for idx, one_occ in enumerate(occupied):
                        if one_occ is None:
                            continue
                        if selected is not None and idx == selected:
                            continue
                        if not floor_overlap(draft, draft_occ, features[idx], one_occ):
                            continue
                        conflicting_feature_indexes.append(idx)
                        if draft_error is None:
                            draft_error = (
                                    f"a {draft.kind} and a {features[idx].kind} overlap; "
                                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                                )
                except Exception:
                    pass

    for i, one_occ in enumerate(occupied):
        if one_occ is None:
            continue
        if selected is not None and i == selected and draft is not None:
            continue
        for j in range(i + 1, len(occupied)):
            if occupied[j] is None:
                continue
            if selected is not None and j == selected and draft is not None:
                continue
            if floor_overlap(features[i], one_occ, features[j], occupied[j]):
                feature_errors.append(
                    f"a {features[i].kind} and a {features[j].kind} overlap; "
                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                )
                if i not in invalid_feature_indexes:
                    invalid_feature_indexes.append(i)
                if j not in invalid_feature_indexes:
                    invalid_feature_indexes.append(j)

    # Recessed Photo Nests share one physical deck. Build every saved recessed
    # Nest plus a participating live draft as one effective group, so editing
    # a saved Nest cannot briefly refill the other Nest cavities with a second
    # deck and a new Recessed draft is visible before it is saved.
    grouped_recessed = {
        index for index, one in enumerate(features)
        if one.kind == "nest" and one.contour
        and str(resolve_nest_settings(box, one, base_z)["holder_style"]) == "recessed"
    }
    draft_in_recessed_group = (
        draft is not None and draft.kind == "nest" and bool(draft.contour)
        and str(resolve_nest_settings(box, draft, base_z)["holder_style"]) == "recessed"
    )
    effective_recessed = []
    represented_recessed = set()
    draft_in_group = False
    for index in sorted(grouped_recessed):
        if index == selected and draft is not None:
            if draft_in_recessed_group:
                effective_recessed.append(draft)
                represented_recessed.add(index)
                draft_in_group = True
            continue
        effective_recessed.append(features[index])
        represented_recessed.add(index)
    if draft_in_recessed_group and not draft_in_group:
        effective_recessed.append(draft)
        draft_in_group = True
    if effective_recessed:
        try:
            built = build_features(
                box, effective_recessed, base_z, layout_zone(box, mode), mode=mode,
                include_text=True,
            )
            if built:
                top_z = max(float(solid.bounds[1][2]) for solid in built)
                for index in represented_recessed:
                    feature_overhang_mm[index] = round(max(0.0, top_z - box.z), 3)
                if draft_in_group:
                    draft_overhang_mm = round(max(0.0, top_z - box.z), 3)
                # The deck is one shared solid; it cannot have one truthful
                # feature owner. Invisible contours give each Nest its own pick.
                for index in represented_recessed:
                    if index == selected and draft_in_group:
                        continue
                    polygon = nest_contour_polygon(features[index], include_clearance=True)
                    pick_proxies.append({
                        "points": [(float(x), float(y), top_z + 0.02)
                                   for x, y in polygon.exterior.coords[:-1]],
                        "pick": {"type": "saved", "index": index},
                    })
                if draft_in_group:
                    polygon = nest_contour_polygon(draft, include_clearance=True)
                    pick_proxies.append({
                        "points": [(float(x), float(y), top_z + 0.02)
                                   for x, y in polygon.exterior.coords[:-1]],
                        "pick": {"type": "draft"},
                    })
            for solid in built:
                if cut_fused_pieces:
                    solid = apply_edge_mount_hole_cuts(
                        box, solid, geometry_owner="recessed Photo Nest group")
                if cut_side_opening_pieces:
                    solid = apply_side_openings(box, solid)
                geometry.extend(_mesh_preview_geometry(solid, f"{part_kind}_nest"))
        except Exception as error:
            for index in represented_recessed:
                feature_errors.append(f"nest: {error}")
                if index not in invalid_feature_indexes:
                    invalid_feature_indexes.append(index)
                if index == selected and draft_in_group:
                    continue
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    features[index].zone, base_z,
                    min(box.z - 0.25, _feature_height(box, features[index], base_z)),
                    f"{part_kind}_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "saved", "index": index}
            if draft_in_group:
                draft_error = f"nest: {error}"
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone, base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}

    for feature_index, one in enumerate(features):
        if selected is not None and feature_index == selected and draft is not None:
            continue
        if is_text(one) and one.options.get("level") == "rim":
            try:
                from organizer_inserts._text import rim_text_geometry
                ledge, glyph, _cap, _surface = rim_text_geometry(box, one)
                if not text_is_raised(one):
                    try:
                        ledge = difference([ledge, glyph])
                    except Exception as pocket_error:
                        feature_errors.append(f"text pocket: {pocket_error}")
                for mesh, kind in ((ledge, "top_label_ledge"), (glyph, "feature_text")):
                    start = len(geometry)
                    faces = _mesh_preview_geometry(mesh, kind)
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "saved", "index": feature_index}
            except Exception as error:
                feature_errors.append(f"text: {error}")
                invalid_feature_indexes.append(feature_index)
            continue
        if selected is not None and feature_index == selected and draft is not None:
            continue
        # Same actual-footprint rule as validate_customization_clearance(): a
        # default divider's zone can span the floor even though its printed
        # wall is a narrow strip, so judge against what is really built.
        # Use the actual footprint regardless of mode (do not reuse ``occupied``
        # which intentionally keeps full zones in non-fused mode for feature-vs-
        # feature layout, not customization collision).
        customization_footprint = feature_footprint(box, one, base_z)
        conflict = next(
            (name for name, zone in reserved if
             ((text_placed_outline(one) if is_text(one) else customization_footprint.polygon)
              .distance(zone.polygon) < MIN_FEATURE_GAP)),
            None,
        )
        if conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {conflict}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)
        handle_conflict = inside_handle_conflict(box, one, base_z, mode)
        if handle_conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {handle_conflict}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)

        if feature_index in represented_recessed:
            continue

        is_conflicting = feature_index in conflicting_feature_indexes
        is_invalid = feature_index in invalid_feature_indexes

        if is_invalid:
            tag = f"{part_kind}_invalid"
        elif is_conflicting:
            tag = f"{part_kind}_conflict_{one.kind}"
        else:
            tag = f"{part_kind}_{one.kind}"

        try:
            built = build_features(
                box, [one], base_z, layout_zone(box, mode), mode=mode,
                include_text=True,
            )
            if built:
                top_z = max(float(solid.bounds[1][2]) for solid in built)
                feature_overhang_mm[feature_index] = round(
                    max(0.0, top_z - box.z), 3,
                )
            for solid in built:
                layer = solid.metadata.get("wavefinity_preview_layer")
                # Export never cuts a text object with the driver-access
                # tunnel (it is a separate part cut in only at its own
                # pocket), so leave text features out of this - every other
                # fused feature is real body material and gets cut exactly
                # like the shell, scoop and rim ledge above.
                if cut_fused_pieces and not is_text(one):
                    solid = apply_edge_mount_hole_cuts(
                        box, solid, geometry_owner=f"{one.kind} feature")
                if cut_side_opening_pieces and not is_text(one):
                    solid = apply_side_openings(box, solid)
                if layer:
                    solid.metadata["wavefinity_preview_layer"] = layer
                start = len(geometry)
                faces = _mesh_preview_geometry(solid, tag)
                geometry.extend(faces)
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "saved", "index": feature_index}
        except Exception as error:
            feature_errors.append(f"{one.kind}: {error}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)
            start = len(geometry)
            geometry.extend(_prism_geometry(
                one.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, one, base_z)),
                f"{part_kind}_invalid",
            ))
            for face_index in range(start, len(geometry)):
                pick_faces[face_index] = {"type": "saved", "index": feature_index}
        geometry.extend(_bore_axis_geometry(
            box, one, base_z, f"{part_kind}_bore_axis"
        ))

    if draft is not None and not draft_in_group:
        cut_draft = cut_fused_pieces and not is_text(draft)
        cut_draft_side_opening = cut_side_opening_pieces and not is_text(draft)
        if draft_error is not None:
            built = False
            try:
                solids = build_features(box, [draft], base_z, layout_zone(box, mode),
                                        mode=mode, include_text=True)
                if is_text(draft) and draft.options.get("level") == "rim":
                    from organizer_inserts._text import rim_text_geometry
                    draft_ledge, draft_glyph, _cap, _surface = rim_text_geometry(box, draft)
                    if not text_is_raised(draft):
                        try:
                            draft_ledge = difference([draft_ledge, draft_glyph])
                        except Exception as pocket_error:
                            # Only the pocket boolean failed; record it on the
                            # draft-error channel, keep any primary error, and
                            # still draw the uncut ledge.
                            if draft_error is None:
                                draft_error = f"text pocket: {pocket_error}"
                    solids = [draft_ledge, *solids]
                if solids:
                    draft_overhang_mm = round(max(
                        0.0, max(float(s.bounds[1][2]) for s in solids) - box.z,
                    ), 3)
                for solid in solids:
                    layer = solid.metadata.get("wavefinity_preview_layer")
                    if cut_draft:
                        solid = apply_edge_mount_hole_cuts(
                            box, solid, geometry_owner=f"{draft.kind} draft")
                    if cut_draft_side_opening:
                        solid = apply_side_openings(box, solid)
                    if layer:
                        solid.metadata["wavefinity_preview_layer"] = layer
                    start = len(geometry)
                    faces = _mesh_preview_geometry(solid, "draft_invalid")
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "draft"}
                built = True
            except Exception:
                pass
            if not built:
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}
        else:
            try:
                solids = build_features(box, [draft], base_z, layout_zone(box, mode),
                                        mode=mode, include_text=True)
                if is_text(draft) and draft.options.get("level") == "rim":
                    from organizer_inserts._text import rim_text_geometry
                    draft_ledge, draft_glyph, _cap, _surface = rim_text_geometry(box, draft)
                    if not text_is_raised(draft):
                        try:
                            draft_ledge = difference([draft_ledge, draft_glyph])
                        except Exception as pocket_error:
                            # Only the pocket boolean failed; record it on the
                            # draft-error channel, keep any primary error, and
                            # still draw the uncut ledge.
                            if draft_error is None:
                                draft_error = f"text pocket: {pocket_error}"
                    solids = [draft_ledge, *solids]
                if solids:
                    draft_overhang_mm = round(max(
                        0.0, max(float(s.bounds[1][2]) for s in solids) - box.z,
                    ), 3)
                for solid in solids:
                    layer = solid.metadata.get("wavefinity_preview_layer")
                    if cut_draft:
                        solid = apply_edge_mount_hole_cuts(
                            box, solid, geometry_owner=f"{draft.kind} draft")
                    if cut_draft_side_opening:
                        solid = apply_side_openings(box, solid)
                    if layer:
                        solid.metadata["wavefinity_preview_layer"] = layer
                    start = len(geometry)
                    faces = _mesh_preview_geometry(solid, f"draft_{draft.kind}")
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "draft"}
            except Exception as error:
                draft_error = f"{draft.kind}: {error}"
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}
        geometry.extend(_bore_axis_geometry(box, draft, base_z, "draft_bore_axis"))

    # The rim label is the only lettering left that is not an interior part:
    # it sits on a shelf at the selected rim side and has no zone to drag, so the
    # preview still draws it here. Floor text drew itself above, with every
    # other interior part.
    fits, message = True, ""
    label_outline_coords = []
    label_meta = None
    side = rim_label_side(location)
    if tidy and side:
        try:
            label_info = top_label_report(box, tidy, side)
            outline = top_label_outline(box, tidy, side)
            label_meta = {
                "location": location,
                "side": side,
                "cap_height": label_info["cap_height_mm"],
                "warning": label_info.get("warning"),
            }
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
            label_outline_coords = [
                [[float(x), float(y)] for x, y in piece.exterior.coords]
                for piece in pieces
            ]
            label_z = top_label_surface_z(box)
            for piece in pieces:
                geometry.append(([(x, y, label_z) for x, y in piece.exterior.coords],
                                 "label", (0.0, 0.0, 1.0), 2, None))
                for ring in piece.interiors:
                    geometry.append(([(x, y, label_z) for x, y in ring.coords],
                                     "label_hole", (0.0, 0.0, 1.0), 3, None))

    edge_mount_meta = None
    if box.edge_mount.active:
        edge_mount_meta = edge_mount_summary(box)
        if box.edge_mount.label_enabled and box.edge_mount.label_type == "separate":
            separate_label = make_edge_mount_label_part(box)
            if separate_label is not None:
                geometry.extend(_mesh_preview_geometry(separate_label, "edge_mount"))
        edge_text = edge_mount_text_object(box)
        if edge_text is not None:
            _edge_label, edge_mesh, _edge_raised = edge_text
            geometry.extend(_mesh_preview_geometry(edge_mesh, "label"))

    side_openings_meta = side_opening_summary(box) if box.side_openings.enabled else None
    pegboard_meta = receiver_layout(box) if box.pegboard.enabled else None

    # The effective list has already replaced a selected saved part with its
    # live draft. These faces never enter any printable builder or pick map.
    for one in effective_features:
        try:
            for mesh in _reference_preview_meshes(box, one, base_z):
                geometry.extend(_mesh_preview_geometry(mesh, "reference_object"))
        except Exception:
            pass

    inside_x, inside_y = box.usable_opening
    return {
        "geometry": geometry,
        "pick_faces": pick_faces,
        "pick_proxies": pick_proxies,
        "fits": fits,
        "message": message,
        "feature_errors": tuple(feature_errors),
        "invalid_feature_indexes": tuple(invalid_feature_indexes),
        "conflicting_feature_indexes": tuple(conflicting_feature_indexes),
        "draft_error": draft_error,
        "feature_overhang_mm": tuple(feature_overhang_mm),
        "draft_overhang_mm": draft_overhang_mm,
        "customization_zones": tuple(reserved),
        "label_outline": label_outline_coords,
        "label_meta": label_meta,
        "edge_mount": edge_mount_meta,
        "side_openings": side_openings_meta,
        "pegboard": pegboard_meta,
        # Where each text interior part ended up, so the browser can show the
        # resolved letter height an auto or zone-fitted one landed on.
        "text_meta": tuple(
            {
                "index": index,
                "text": text_of(one),
                "auto": bool(one.options.get("auto")),
                "cap_height": round(text_fitted(one)[0], 3),
            }
            for index, one in enumerate(features)
            if is_text(one) and _text_fits(one)
        ),
        "features": layout_to_dict(Layout(features, mode))["features"],
        "inside_x": math.floor(inside_x),
        "inside_y": math.floor(inside_y),
        "size_text": (
            f"{math.floor(inside_x):g} X {math.floor(inside_y):g} (Inside) - "
            f"{box.x:g} X {box.y:g} mm (Outside)"
        ),
    }
