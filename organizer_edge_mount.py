"""Edge Mount: an optional modifier that lets an ordinary Wavefinity bin
mount vertically to the outside face of a cart, table, shelf or workbench.

This is not a new bin type and not a new body architecture. It adds, to an
otherwise ordinary bin body:

* a thin horizontal **Projecting Label** plate cantilevered outward from the
  top of one selected wall (like a diving board), with optional inlaid or
  raised lettering reusing the existing text engine; and/or
* **Screw Mounting**: small round screw holes through that same selected
  wall, plus larger round screwdriver/driver-access passages that open from
  the *opposite* wall and cross the bin interior to reach them.

Everything here operates on a finished ``trimesh.Trimesh`` bin body and the
box's own wavy outlines (:func:`organizer_engine.wavy_outer_polygon` /
:func:`organizer_engine.wavy_cavity_polygon`), so it stays correct regardless
of where a hole or the label plate lands relative to a wave crest or trough.
"""

from __future__ import annotations

import math

import trimesh
from shapely.affinity import rotate as rotate_polygon, translate as translate_polygon
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry import box as shapely_box

from organizer_engine import (
    BoxSpec,
    EdgeMountSpec,
    TEXT_MIN_BACKING,
    WAVE_AMPLITUDE,
    require_text_backing,
    text_outline,
    text_prism,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, difference, union

EDGE_MOUNT_SIDES = ("front", "back", "left", "right")

EDGE_LABEL_PROJECTION_PRESETS = (
    (25.0, "Short"),
    (50.0, "Medium"),
    (75.0, "Long"),
)

EDGE_LABEL_DEFAULT_PROJECTION = 50.0

EDGE_LABEL_THICKNESS_PRESETS = (
    (1.2, "Thin"),
    (2.0, "Medium"),
    (3.0, "Thick"),
)

EDGE_LABEL_DEFAULT_THICKNESS = 2.0

EDGE_LABEL_TEXT_MARGIN = 2.0
EDGE_LABEL_TARGET_CAP_HEIGHT = 12.0
EDGE_LABEL_MIN_CAP_HEIGHT = 6.0
EDGE_LABEL_FRONT_CHAMFER_MM = 1.0

EDGE_HOLE_DEFAULT_SCREW_DIAMETER = 4.0
EDGE_HOLE_DEFAULT_ACCESS_DIAMETER = 8.0
EDGE_HOLE_DEFAULT_TOP_OFFSET = 12.7
EDGE_HOLE_AUTO_MAX_SPACING = 20.0
EDGE_HOLE_EDGE_CLEARANCE = 2.0
EDGE_HOLE_VERTICAL_CLEARANCE = 1.0
EDGE_HOLE_BETWEEN_CLEARANCE = 2.0

EDGE_BOOLEAN_OVERTRAVEL = 0.5
EDGE_BOOLEAN_EPSILON = 0.05

# Input ranges (validation/resource limits - never silently clamped).
EDGE_LABEL_MIN_PROJECTION = 5.0
EDGE_LABEL_MAX_PROJECTION = 200.0
EDGE_LABEL_MIN_THICKNESS = 0.8
EDGE_LABEL_MAX_THICKNESS = 6.0
EDGE_LABEL_MIN_TEXT_DEPTH = 0.2
EDGE_LABEL_MAX_TEXT_DEPTH = 2.0
EDGE_HOLE_MIN_SCREW_DIAMETER = 1.0
EDGE_HOLE_MAX_SCREW_DIAMETER = 12.0
EDGE_HOLE_MIN_ACCESS_DIAMETER = 2.0
EDGE_HOLE_MAX_ACCESS_DIAMETER = 20.0
EDGE_HOLE_MIN_COUNT = 1
EDGE_HOLE_MAX_COUNT = 4

_EDGE_MOUNT_WALL_NAME = {"front": "-y", "back": "+y", "left": "-x", "right": "+x"}
_EDGE_MOUNT_OPPOSITE_SIDE = {"front": "back", "back": "front", "left": "right", "right": "left"}
_EDGE_MOUNT_ROTATION = {"back": 0.0, "front": 180.0, "left": 90.0, "right": -90.0}


def _normalize_side(side: str) -> str:
    value = str(side or "front").strip().lower()
    if value not in EDGE_MOUNT_SIDES:
        raise ValueError(f"Edge Mount side must be one of {', '.join(EDGE_MOUNT_SIDES)}")
    return value


def _wall_normal_axis(side: str) -> str:
    return "y" if side in ("front", "back") else "x"


def _wall_tangential_span(box: BoxSpec, side: str) -> float:
    return box.x if side in ("front", "back") else box.y


def _validate_lift_grabber_conflict(box: BoxSpec, side: str) -> None:
    grabbers = getattr(box, "lift_grabbers", None)
    if grabbers is None or not grabbers.enabled:
        return
    mounting_wall = _EDGE_MOUNT_WALL_NAME[side]
    opposite_wall = _EDGE_MOUNT_WALL_NAME[_EDGE_MOUNT_OPPOSITE_SIDE[side]]
    if mounting_wall in grabbers.walls or opposite_wall in grabbers.walls:
        raise ValueError(
            "Edge Mount screw access conflicts with an Inside Handle on the "
            "mounting or access wall. Move the Inside Handles to the other "
            "walls or turn them off."
        )


def resolved_access_diameter(spec: EdgeMountSpec) -> float:
    """The actual driver-access diameter this spec will cut.

    ``None`` means Auto: ``max(8.0, screw_diameter_mm * 2.0)``.
    """
    if spec.access_diameter_mm is not None:
        return float(spec.access_diameter_mm)
    return max(EDGE_HOLE_DEFAULT_ACCESS_DIAMETER, spec.screw_diameter_mm * 2.0)


def _validate_hole_ranges(spec: EdgeMountSpec) -> float:
    """Validate screw-mounting inputs and return the resolved access diameter."""
    if not (EDGE_HOLE_MIN_COUNT <= spec.hole_count <= EDGE_HOLE_MAX_COUNT):
        raise ValueError(
            f"Edge Mount screw count must be between {EDGE_HOLE_MIN_COUNT} and "
            f"{EDGE_HOLE_MAX_COUNT}"
        )
    if not (EDGE_HOLE_MIN_SCREW_DIAMETER <= spec.screw_diameter_mm <= EDGE_HOLE_MAX_SCREW_DIAMETER):
        raise ValueError(
            f"Edge Mount screw diameter must be between {EDGE_HOLE_MIN_SCREW_DIAMETER:g} "
            f"and {EDGE_HOLE_MAX_SCREW_DIAMETER:g} mm"
        )
    access = resolved_access_diameter(spec)
    if not (EDGE_HOLE_MIN_ACCESS_DIAMETER <= access <= EDGE_HOLE_MAX_ACCESS_DIAMETER):
        raise ValueError(
            f"Edge Mount screwdriver access diameter of {access:g} mm is outside the "
            f"{EDGE_HOLE_MIN_ACCESS_DIAMETER:g}-{EDGE_HOLE_MAX_ACCESS_DIAMETER:g} mm "
            "range. Use a smaller screw diameter or set another access diameter."
        )
    if access < spec.screw_diameter_mm - 1e-9:
        raise ValueError(
            "Edge Mount screwdriver access must be at least the screw diameter"
        )
    if spec.hole_orientation not in ("horizontal", "vertical"):
        raise ValueError("Edge Mount hole pattern must be horizontal or vertical")
    if spec.top_offset_mm <= 0:
        raise ValueError("Edge Mount distance below top must be positive")
    if spec.hole_spacing_mm is not None and spec.hole_spacing_mm <= 0:
        raise ValueError("Edge Mount hole spacing must be positive")
    return access


def _validate_label_ranges(spec: EdgeMountSpec) -> None:
    if not (EDGE_LABEL_MIN_PROJECTION <= spec.label_projection_mm <= EDGE_LABEL_MAX_PROJECTION):
        raise ValueError(
            f"Edge Mount label projection must be between {EDGE_LABEL_MIN_PROJECTION:g} "
            f"and {EDGE_LABEL_MAX_PROJECTION:g} mm"
        )
    if not (EDGE_LABEL_MIN_THICKNESS <= spec.label_thickness_mm <= EDGE_LABEL_MAX_THICKNESS):
        raise ValueError(
            f"Edge Mount label thickness must be between {EDGE_LABEL_MIN_THICKNESS:g} "
            f"and {EDGE_LABEL_MAX_THICKNESS:g} mm"
        )
    if not (EDGE_LABEL_MIN_TEXT_DEPTH <= spec.label_text_depth_mm <= EDGE_LABEL_MAX_TEXT_DEPTH):
        raise ValueError(
            f"Edge Mount label text depth must be between {EDGE_LABEL_MIN_TEXT_DEPTH:g} "
            f"and {EDGE_LABEL_MAX_TEXT_DEPTH:g} mm"
        )
    if spec.label_length_mode not in ("full", "text"):
        raise ValueError("Edge Mount plate length mode must be 'full' or 'text'")
    if not spec.label_raised:
        require_text_backing(
            spec.label_thickness_mm, spec.label_text_depth_mm, what="Edge Mount label"
        )


def _fit_edge_label_text(text: str, room_along: float, room_depth: float) -> float:
    probe = text_outline(text, EDGE_LABEL_TARGET_CAP_HEIGHT)
    minx, miny, maxx, maxy = probe.bounds
    width, height = maxx - minx, maxy - miny
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"'{text}' has no printable outline")
    scale = min(1.0, room_along / width if room_along > 0 else 0.0,
                room_depth / height if room_depth > 0 else 0.0)
    cap_height = EDGE_LABEL_TARGET_CAP_HEIGHT * scale
    if cap_height < EDGE_LABEL_MIN_CAP_HEIGHT - 1e-9:
        raise ValueError(
            f'The Edge Mount label is too small for "{text}" at the '
            f"{EDGE_LABEL_MIN_CAP_HEIGHT:g} mm minimum letter height. Shorten "
            "the text, increase Projection, or use Full Side Length."
        )
    return cap_height


def edge_mount_label_plan(box: BoxSpec) -> dict[str, object] | None:
    """Resolve the Projecting Label's side, size, text fit and orientation.

    Returns ``None`` when the label is off. Raises ``ValueError`` when the
    requested label cannot fit.
    """
    spec = box.edge_mount
    if not spec.label_enabled:
        return None
    side = _normalize_side(spec.side)
    _validate_label_ranges(spec)
    projection = spec.label_projection_mm
    outer = wavy_outer_polygon(box)
    ox0, oy0, ox1, oy1 = outer.bounds
    full_length = (ox1 - ox0) if side in ("front", "back") else (oy1 - oy0)
    room_along = max(0.0, full_length - 2.0 * EDGE_LABEL_TEXT_MARGIN)
    room_depth = max(0.0, projection - 2.0 * EDGE_LABEL_TEXT_MARGIN)
    text = spec.label_text.strip()
    cap_height: float | None = None
    text_width = 0.0
    if text:
        cap_height = _fit_edge_label_text(text, room_along, room_depth)
        tminx, tminy, tmaxx, tmaxy = text_outline(text, cap_height).bounds
        text_width = tmaxx - tminx
    if spec.label_length_mode == "text":
        if not text:
            raise ValueError(
                "Text Length plate mode needs label text; add text or switch "
                "to Full Side."
            )
        plate_length = min(full_length, text_width + 2.0 * EDGE_LABEL_TEXT_MARGIN)
    else:
        plate_length = full_length
    rotation = _EDGE_MOUNT_ROTATION[side]
    if spec.label_flip:
        rotation += 180.0
    rotation = ((rotation + 180.0) % 360.0) - 180.0
    return {
        "side": side,
        "projection_mm": projection,
        "plate_length_mm": plate_length,
        "thickness_mm": spec.label_thickness_mm,
        "cap_height_mm": cap_height,
        "text": text,
        "raised": bool(spec.label_raised),
        "text_depth_mm": spec.label_text_depth_mm,
        "rotation_deg": rotation,
    }


def edge_mount_hole_plan(box: BoxSpec) -> tuple[dict[str, float], ...]:
    """Resolve every screw-mounting hole's tangential position and height.

    Returns an empty tuple when Screw Mounting is off. Raises ``ValueError``
    when the requested pattern does not fit.
    """
    spec = box.edge_mount
    if not spec.holes_enabled:
        return ()
    side = _normalize_side(spec.side)
    access_d = _validate_hole_ranges(spec)
    _validate_lift_grabber_conflict(box, side)
    access_r = access_d / 2.0
    count = spec.hole_count
    span = _wall_tangential_span(box, side)
    top_offset = spec.top_offset_mm
    if top_offset < access_r + 1.0 - 1e-9:
        raise ValueError(
            f"Distance below top must be at least {access_r + 1.0:.1f} mm for a "
            f"{access_d:g} mm screwdriver access hole. Increase it, or reduce the "
            "access diameter."
        )
    min_spacing = access_d + EDGE_HOLE_BETWEEN_CLEARANCE
    holes: list[dict[str, float]] = []
    if count == 1:
        holes.append({"tangent_mm": 0.0, "z_mm": box.z - top_offset})
    elif spec.hole_orientation == "vertical":
        z_first = box.z - top_offset
        if spec.hole_spacing_mm is not None:
            spacing = spec.hole_spacing_mm
        else:
            z_min = box.base_thickness + access_r + EDGE_HOLE_VERTICAL_CLEARANCE
            available_drop = z_first - z_min
            spacing = (
                min(EDGE_HOLE_AUTO_MAX_SPACING, available_drop / (count - 1))
                if available_drop > 0 else 0.0
            )
        if spacing < min_spacing - 1e-9:
            raise ValueError(
                f"{count} vertical {access_d:g} mm screwdriver access holes do not fit "
                "with this distance below top. Reduce the hole count, increase the "
                "bin height, or raise the distance below top."
            )
        for i in range(count):
            holes.append({"tangent_mm": 0.0, "z_mm": z_first - i * spacing})
    else:
        z = box.z - top_offset
        if spec.hole_spacing_mm is not None:
            spacing = spec.hole_spacing_mm
        else:
            edge_clearance = access_r + EDGE_HOLE_EDGE_CLEARANCE
            available_span = span - 2.0 * edge_clearance
            spacing = (
                min(EDGE_HOLE_AUTO_MAX_SPACING, available_span / (count - 1))
                if available_span > 0 else 0.0
            )
        if spacing < min_spacing - 1e-9:
            raise ValueError(
                f"Two {access_d:g} mm screwdriver access holes do not fit side by side "
                f"on this {span:g} mm wall. Use one screw, reduce the access "
                "diameter, or use a larger bin."
            )
        for i in range(count):
            offset = (i - (count - 1) / 2.0) * spacing
            holes.append({"tangent_mm": offset, "z_mm": z})

    max_tangent = max(abs(hole["tangent_mm"]) for hole in holes)
    if max_tangent + access_r + 2.0 > span / 2.0 + 1e-9:
        raise ValueError(
            f"The screw pattern is too wide for this {span:g} mm wall. Reduce "
            "the hole count, spacing, or access diameter."
        )
    min_z = min(hole["z_mm"] for hole in holes)
    if min_z - box.base_thickness < access_r + EDGE_HOLE_VERTICAL_CLEARANCE - 1e-9:
        raise ValueError(
            "The screw pattern extends into the bin floor. Reduce the hole "
            "count, spacing, or distance below the top."
        )
    return tuple(
        {**hole, "screw_diameter_mm": spec.screw_diameter_mm, "access_diameter_mm": access_d}
        for hole in holes
    )


def edge_mount_summary(box: BoxSpec) -> dict[str, object]:
    """Authoritative report used by preview/API/debug information."""
    spec = box.edge_mount
    if not spec.active:
        return {"active": False}
    summary: dict[str, object] = {"active": True, "side": _normalize_side(spec.side)}
    try:
        label_plan = edge_mount_label_plan(box)
    except ValueError as error:
        label_plan = None
        summary["label_error"] = str(error)
    if label_plan is not None:
        summary["label"] = label_plan
    try:
        holes = edge_mount_hole_plan(box)
    except ValueError as error:
        holes = ()
        summary["holes_error"] = str(error)
    if holes:
        summary["holes"] = list(holes)
        summary["resolved_access_diameter_mm"] = holes[0]["access_diameter_mm"]
    elif spec.holes_enabled:
        summary["resolved_access_diameter_mm"] = resolved_access_diameter(spec)
    return summary


def _all_points(geom) -> list[tuple[float, float]]:
    if geom is None or geom.is_empty:
        return []
    if hasattr(geom, "geoms"):
        points: list[tuple[float, float]] = []
        for part in geom.geoms:
            points.extend(_all_points(part))
        return points
    if geom.geom_type == "Point":
        return [(geom.x, geom.y)]
    if hasattr(geom, "coords"):
        return list(geom.coords)
    return []


def _wall_surface_coords(
    box: BoxSpec, side: str, tangent: float
) -> tuple[float, float, float, float]:
    """``(outer_selected, cavity_selected, cavity_opposite, outer_opposite)``.

    Found by intersecting an axis line through the bin at ``tangent`` with
    the box's real wavy outlines, so the answer is correct regardless of
    where ``tangent`` falls relative to a wave crest or trough.
    """
    axis = _wall_normal_axis(side)
    span = 2.0 * max(box.x, box.y) + 100.0
    line = (
        LineString([(tangent, -span), (tangent, span)]) if axis == "y"
        else LineString([(-span, tangent), (span, tangent)])
    )
    coord_index = 1 if axis == "y" else 0
    outer_vals = sorted(p[coord_index] for p in _all_points(line.intersection(wavy_outer_polygon(box).exterior)))
    cavity_vals = sorted(p[coord_index] for p in _all_points(line.intersection(wavy_cavity_polygon(box).exterior)))
    if len(outer_vals) < 2 or len(cavity_vals) < 2:
        raise ValueError(
            "an Edge Mount hole position does not cross both walls; move it "
            "away from the corner"
        )
    outer_lo, outer_hi = outer_vals[0], outer_vals[-1]
    cavity_lo, cavity_hi = cavity_vals[0], cavity_vals[-1]
    if side in ("front", "left"):
        return outer_lo, cavity_lo, cavity_hi, outer_hi
    return outer_hi, cavity_hi, cavity_lo, outer_lo


def _axis_cylinder(
    axis: str, coord_a: float, coord_b: float, tangent: float, z: float,
    radius: float, sections: int = 32,
) -> trimesh.Trimesh:
    height = abs(coord_b - coord_a)
    if height <= 1e-6:
        raise ValueError("an Edge Mount hole cutter has no length")
    center = (coord_a + coord_b) / 2.0
    cylinder = trimesh.creation.cylinder(radius=radius, height=height, sections=sections)
    if axis == "y":
        cylinder.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
        )
        cylinder.apply_translation((tangent, center, z))
    else:
        cylinder.apply_transform(
            trimesh.transformations.rotation_matrix(math.pi / 2.0, (0.0, 1.0, 0.0))
        )
        cylinder.apply_translation((center, tangent, z))
    return cylinder


def _hole_cutters(
    box: BoxSpec, side: str, hole: dict[str, float], cut_driver_passage: bool,
) -> list[trimesh.Trimesh]:
    axis = _wall_normal_axis(side)
    tangent = hole["tangent_mm"]
    z = hole["z_mm"]
    screw_r = hole["screw_diameter_mm"] / 2.0
    access_r = hole["access_diameter_mm"] / 2.0
    outer_sel, cavity_sel, cavity_opp, outer_opp = _wall_surface_coords(box, side, tangent)
    sign = 1.0 if cavity_sel >= outer_sel else -1.0
    screw_a = outer_sel - sign * EDGE_BOOLEAN_OVERTRAVEL
    screw_b = cavity_sel + sign * EDGE_BOOLEAN_OVERTRAVEL
    cutters = [_axis_cylinder(axis, screw_a, screw_b, tangent, z, screw_r)]
    if cut_driver_passage:
        access_far = outer_opp + sign * EDGE_BOOLEAN_OVERTRAVEL
        cutters.append(_axis_cylinder(axis, cavity_sel, access_far, tangent, z, access_r))
    return cutters


def _plate_rectangle(box: BoxSpec, side: str, half_length: float, projection: float) -> Polygon:
    outer = wavy_outer_polygon(box)
    ox0, oy0, ox1, oy1 = outer.bounds
    reach = box.wall_depth + 2.0 * WAVE_AMPLITUDE + 1.0
    plate_length = 2.0 * half_length
    c = min(EDGE_LABEL_FRONT_CHAMFER_MM, projection / 4.0, plate_length / 4.0)
    # Canonical plate: tangent is X, outward is +Y. Only the two free/outward
    # corners are chamfered; the wall-attached edge remains square.
    polygon = Polygon([
        (-half_length, -reach),
        (half_length, -reach),
        (half_length, projection - c),
        (half_length - c, projection),
        (-half_length + c, projection),
        (-half_length, projection - c),
    ])
    polygon = rotate_polygon(polygon, _EDGE_MOUNT_ROTATION[side], origin=(0.0, 0.0))
    if side == "back":
        return translate_polygon(polygon, yoff=oy1)
    if side == "front":
        return translate_polygon(polygon, yoff=oy0)
    if side == "left":
        return translate_polygon(polygon, xoff=ox0)
    return translate_polygon(polygon, xoff=ox1)


def _build_label_plate_mesh(box: BoxSpec, plan: dict[str, object]) -> trimesh.Trimesh:
    side = str(plan["side"])
    half = float(plan["plate_length_mm"]) / 2.0
    rectangle = _plate_rectangle(box, side, half, float(plan["projection_mm"]))
    footprint = rectangle.difference(wavy_cavity_polygon(box))
    if footprint.is_empty:
        raise ValueError(
            "The Edge Mount label plate has no material where it meets the "
            "wall. Increase the projection or plate length."
        )
    pieces = list(footprint.geoms) if isinstance(footprint, MultiPolygon) else [footprint]
    thickness = float(plan["thickness_mm"])
    solids = [_extrude_polygon(piece, thickness) for piece in pieces if not piece.is_empty]
    if not solids:
        raise ValueError(
            "The Edge Mount label plate has no material where it meets the "
            "wall. Increase the projection or plate length."
        )
    solid = union(solids) if len(solids) > 1 else solids[0]
    solid.apply_translation((0.0, 0.0, box.z - thickness))
    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return solid


def apply_edge_mount_hole_cuts(
    box: BoxSpec,
    body: trimesh.Trimesh,
    *,
    cut_driver_passages: bool = True,
) -> trimesh.Trimesh:
    """Subtract Screw Mounting's small mounting holes and (by default) their
    driver-access passages from ``body``.

    This is the one place that geometry is built, so a caller with more than
    one solid to cut - the bin shell, a fused holder, the scoop, the rim
    ledge, a live draft - can cut each of them with the exact same cutters
    export uses, rather than baking everything into one combined solid first.
    ``(A union B) minus C`` and ``(A minus C) union (B minus C)`` are the same
    shape for a shared cutter ``C``, so cutting each piece separately keeps
    every piece's own preview identity (bin vs. interior-feature, its own
    colour/category) while still showing exactly what export cuts away.

    Returns ``body`` unchanged when Screw Mounting is off.
    """
    spec = box.edge_mount
    if not spec.holes_enabled:
        return body
    side = _normalize_side(spec.side)
    holes = edge_mount_hole_plan(box)
    if not holes:
        return body
    cutters: list[trimesh.Trimesh] = []
    for hole in holes:
        cutters.extend(_hole_cutters(box, side, hole, cut_driver_passages))
    cutter = union(cutters) if len(cutters) > 1 else cutters[0]
    # difference() already cleans up after itself the safe way (organizer_
    # geometry._cleaned() only keeps the clean copy when that does not break
    # watertightness) - a further unguarded clean-up call here has, in
    # practice, turned an otherwise-valid cut solid non-watertight.
    return difference([body, cutter])


def apply_edge_mount_structure(
    box: BoxSpec,
    body: trimesh.Trimesh,
    *,
    cut_driver_passages: bool = True,
) -> trimesh.Trimesh:
    """Add the Projecting Label plate and cut Screw Mounting holes into ``body``.

    ``body`` should already be the finished bin body (fused features, scoop
    and any other shell customizations already applied), so the driver-access
    cut also clears any fused geometry that would otherwise block the
    screwdriver's path. Returns ``body`` unchanged when Edge Mount is off.
    """
    spec = box.edge_mount
    if not spec.active:
        return body
    result = body
    label_plan = edge_mount_label_plan(box)
    if label_plan is not None:
        plate = _build_label_plate_mesh(box, label_plan)
        # union() already cleans up after itself (and only keeps the clean
        # copy when that does not break watertightness) - an extra unguarded
        # clean-up call here has, in practice, turned an otherwise-valid
        # solid non-watertight and failed the boolean cut that follows.
        result = union([result, plate])
    return apply_edge_mount_hole_cuts(box, result, cut_driver_passages=cut_driver_passages)


def edge_mount_text_object(box: BoxSpec) -> tuple[str, trimesh.Trimesh, bool] | None:
    """``(label text, text mesh, raised?)`` for the Edge Mount label, or
    ``None`` when there is no label or it carries no text."""
    plan = edge_mount_label_plan(box)
    if plan is None or not plan["text"]:
        return None
    side = str(plan["side"])
    outer = wavy_outer_polygon(box)
    ox0, oy0, ox1, oy1 = outer.bounds
    projection = float(plan["projection_mm"])
    if side == "back":
        position = (0.0, oy1 + projection / 2.0)
    elif side == "front":
        position = (0.0, oy0 - projection / 2.0)
    elif side == "left":
        position = (ox0 - projection / 2.0, 0.0)
    else:
        position = (ox1 + projection / 2.0, 0.0)
    outline = text_outline(str(plan["text"]), float(plan["cap_height_mm"]))
    rotation = float(plan["rotation_deg"])
    if rotation:
        outline = rotate_polygon(outline, rotation, origin=(0.0, 0.0))
    outline = translate_polygon(outline, xoff=position[0], yoff=position[1])
    mesh = text_prism(
        outline, box.z, depth=float(plan["text_depth_mm"]), raised=bool(plan["raised"]),
    )
    return str(plan["text"]), mesh, bool(plan["raised"])
