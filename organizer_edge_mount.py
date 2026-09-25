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

import numpy as np
import trimesh
from shapely.affinity import rotate as rotate_polygon, translate as translate_polygon
from shapely.geometry import LineString, MultiPolygon, Polygon

from organizer_engine import (
    BoxSpec,
    EdgeMountSpec,
    TEXT_MIN_BACKING,
    WAVE_AMPLITUDE,
    lock_z_levels,
    require_text_backing,
    text_outline,
    text_prism,
    wall_lock_receivers,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
    union,
)

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
EDGE_LABEL_CLIP_DEPTH_MM = 3.0
# The separate label's inside leg reaches this far past the bottom of the
# ordinary wall locks so it can seat over them. The outside leg, and the
# standoff ribs that stop under it, keep the shallow EDGE_LABEL_CLIP_DEPTH_MM.
EDGE_LABEL_INNER_LEG_SEAT_MARGIN_MM = 0.5
EDGE_LABEL_CLIP_FACE_CLEARANCE_MM = 0.25
EDGE_LABEL_CLIP_LEG_THICKNESS_MM = 1.0
EDGE_LABEL_CLIP_RETENTION_MM = 0.15
EDGE_LABEL_CLIP_RETENTION_SPAN_MM = 4.0
EDGE_LABEL_CLIP_RAMP_OVERLAP_MM = 0.75
# Keep the snap ribs' centres this far in from each end of the bin wall.
EDGE_LABEL_RIB_CORNER_KEEP_MM = 6.0

# Permanent bin-body fins that let a Separate-label saddle clip and the bin
# touch the same flat mounting surface.
EDGE_STANDOFF_CONTACT_WIDTH_MM = 2.0
EDGE_STANDOFF_AUTO_MAX_SPACING_MM = 20.0
EDGE_STANDOFF_EDGE_CLEARANCE_MM = 2.0
EDGE_STANDOFF_CLIP_GAP_MM = 0.25
EDGE_STANDOFF_MIN_COUNT = 1
EDGE_STANDOFF_MAX_COUNT = 20

EDGE_HOLE_DEFAULT_SCREW_DIAMETER = 4.0
EDGE_HOLE_DEFAULT_ACCESS_DIAMETER = 8.0
EDGE_HOLE_DEFAULT_TOP_OFFSET = 12.7
EDGE_HOLE_AUTO_MAX_SPACING = 20.0
EDGE_HOLE_EDGE_CLEARANCE = 2.0
EDGE_HOLE_VERTICAL_CLEARANCE = 1.0
EDGE_HOLE_BETWEEN_CLEARANCE = 2.0

EDGE_BOOLEAN_OVERTRAVEL = 0.5
EDGE_BOOLEAN_EPSILON = 0.05
# Trimesh's 3MF writer emits six decimal places for mesh coordinates.
EDGE_3MF_DECIMALS = 6

EDGE_HOLE_PROFILE_SECTIONS = 64

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
    if spec.label_type not in ("separate", "integrated"):
        raise ValueError("Edge Mount label type must be 'separate' or 'integrated'")
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
        "label_type": spec.label_type,
    }


def edge_mount_inner_leg_depth_mm(box: BoxSpec | None = None) -> float:
    """How far below the rim the separate label's inside leg reaches.

    Derived from the shared wall-lock profile: past the bottom of the lock
    chamfers plus a small seated margin (about 5.5 mm with today's locks). A
    bin too shallow to hold that keeps the leg above its floor instead.
    """
    bottom, _, _, _ = lock_z_levels(0.0)
    depth = -bottom + EDGE_LABEL_INNER_LEG_SEAT_MARGIN_MM
    if box is not None:
        depth = min(depth, max(EDGE_LABEL_CLIP_DEPTH_MM, box.z - box.base_thickness - 0.3))
    return depth


def edge_mount_clip_outer_standoff_mm() -> float:
    """Distance from the wavy envelope to the separate clip's outside face."""
    return EDGE_LABEL_CLIP_FACE_CLEARANCE_MM + EDGE_LABEL_CLIP_LEG_THICKNESS_MM


def _edge_mount_contact_plane(box: BoxSpec, side: str) -> float:
    """One absolute flat mounting plane for the selected wall's clip and ribs."""
    ox0, oy0, ox1, oy1 = wavy_outer_polygon(box).bounds
    standoff = edge_mount_clip_outer_standoff_mm()
    if side == "front":
        return oy0 - standoff
    if side == "back":
        return oy1 + standoff
    if side == "left":
        return ox0 - standoff
    return ox1 + standoff


def edge_mount_standoff_plan(box: BoxSpec) -> dict[str, object] | None:
    """Resolve the authoritative Separate-label rib layout and contact plane."""
    spec = box.edge_mount
    if not (spec.label_enabled and spec.label_type == "separate" and spec.standoff_ribs_enabled):
        return None
    side = _normalize_side(spec.side)
    contact_width = EDGE_STANDOFF_CONTACT_WIDTH_MM
    clip_standoff = edge_mount_clip_outer_standoff_mm()
    max_outward_depth = clip_standoff + 2.0 * WAVE_AMPLITUDE
    contact_half = contact_width / 2.0
    base_half = contact_half + max_outward_depth
    base_width = 2.0 * base_half
    wall_span = _wall_tangential_span(box, side)
    center_limit = wall_span / 2.0 - EDGE_STANDOFF_EDGE_CLEARANCE_MM - base_half
    if center_limit < -1e-9:
        raise ValueError(
            f"This {wall_span:g} mm Edge Mount wall is too narrow for one Standoff Rib. "
            "Use a wider bin."
        )
    center_limit = max(0.0, center_limit)
    z0 = 0.0
    z1 = box.z - EDGE_LABEL_CLIP_DEPTH_MM - EDGE_STANDOFF_CLIP_GAP_MM
    if z1 <= z0 + EDGE_BOOLEAN_EPSILON:
        raise ValueError("The bin is too short for Edge Mount Standoff Ribs below the label clip.")

    requested = spec.standoff_rib_count
    auto = requested is None
    if auto:
        # Two end ribs are useful only when their full bases can remain apart.
        if 2.0 * center_limit < base_width - 1e-9:
            count = 1
        else:
            usable_center_span = 2.0 * center_limit
            count = max(2, math.ceil(usable_center_span / EDGE_STANDOFF_AUTO_MAX_SPACING_MM) + 1)
            max_nonoverlapping = math.floor(usable_center_span / base_width + 1e-9) + 1
            count = min(count, max_nonoverlapping, EDGE_STANDOFF_MAX_COUNT)
    else:
        if isinstance(requested, bool) or int(requested) != requested:
            raise ValueError("Edge Mount Standoff Rib Quantity must be a whole number.")
        count = int(requested)
        if not (EDGE_STANDOFF_MIN_COUNT <= count <= EDGE_STANDOFF_MAX_COUNT):
            raise ValueError(
                f"Edge Mount Standoff Rib Quantity must be between "
                f"{EDGE_STANDOFF_MIN_COUNT} and {EDGE_STANDOFF_MAX_COUNT}"
            )
        if count > 1 and (2.0 * center_limit / (count - 1)) < base_width - 1e-9:
            raise ValueError(
                "Standoff Rib Quantity makes rib bases overlap. Reduce Quantity or use a wider bin."
            )

    centers = (0.0,) if count == 1 else tuple(np.linspace(-center_limit, center_limit, count))
    return {
        "side": side,
        "enabled": True,
        "auto": auto,
        "count": count,
        "centers_mm": centers,
        "contact_plane_mm": _edge_mount_contact_plane(box, side),
        "contact_width_mm": contact_width,
        "base_width_mm": base_width,
        "base_half_mm": base_half,
        "max_outward_depth_mm": max_outward_depth,
        "clip_standoff_mm": clip_standoff,
        "z0_mm": z0,
        "z1_mm": z1,
    }


def _build_edge_mount_standoff_rib(
    box: BoxSpec, plan: dict[str, object], tangent: float,
) -> trimesh.Trimesh:
    """One vertical 45-degree-or-gentler trapezoidal fin on the real shell."""
    side = str(plan["side"])
    contact = float(plan["contact_plane_mm"])
    contact_half = float(plan["contact_width_mm"]) / 2.0
    base_half = float(plan["base_half_mm"])
    outward = -1.0 if side in ("front", "left") else 1.0
    # Extend a hair past the deepest wavy trough to make a robust boolean
    # overlap with the real shell; this also makes the taper slightly gentler.
    base_plane = contact - outward * (float(plan["max_outward_depth_mm"]) + EDGE_BOOLEAN_EPSILON)
    if side in ("front", "back"):
        footprint = Polygon([
            (tangent - base_half, base_plane),
            (tangent + base_half, base_plane),
            (tangent + contact_half, contact),
            (tangent - contact_half, contact),
        ])
    else:
        footprint = Polygon([
            (base_plane, tangent - base_half),
            (base_plane, tangent + base_half),
            (contact, tangent + contact_half),
            (contact, tangent - contact_half),
        ])
    return _extrude_polygon(footprint, float(plan["z1_mm"]))


def make_edge_mount_standoff_ribs(box: BoxSpec) -> trimesh.Trimesh | None:
    """Permanent vertical ribs for a selected Separate Edge Mount label."""
    plan = edge_mount_standoff_plan(box)
    if plan is None:
        return None
    ribs = [_build_edge_mount_standoff_rib(box, plan, float(tangent)) for tangent in plan["centers_mm"]]
    return union(ribs) if len(ribs) > 1 else ribs[0]


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
    # The access profile (pointed-roof, print-safe) always controls required
    # room, since the access diameter is always >= the screw diameter; this
    # is the actual cutter envelope validation is checked against, not the
    # raw requested radius.
    access_profile_r = _print_safe_profile_radius(access_r)
    access_roof = _print_safe_hole_roof_rise(access_r)
    access_profile_height = access_profile_r + access_roof
    access_profile_width = 2.0 * access_profile_r
    count = spec.hole_count
    span = _wall_tangential_span(box, side)
    top_offset = spec.top_offset_mm
    if top_offset < access_roof + 1.0 - 1e-9:
        raise ValueError(
            f"Distance below top must be at least {access_roof + 1.0:.1f} mm for a "
            f"{access_d:g} mm screwdriver access hole. Increase it, or reduce the "
            "access diameter."
        )
    min_spacing_horizontal = access_profile_width + EDGE_HOLE_BETWEEN_CLEARANCE
    min_spacing_vertical = access_profile_height + EDGE_HOLE_BETWEEN_CLEARANCE
    holes: list[dict[str, float]] = []
    if count == 1:
        holes.append({"tangent_mm": 0.0, "z_mm": box.z - top_offset})
    elif spec.hole_orientation == "vertical":
        z_first = box.z - top_offset
        if spec.hole_spacing_mm is not None:
            spacing = spec.hole_spacing_mm
        else:
            z_min = box.base_thickness + access_profile_r + EDGE_HOLE_VERTICAL_CLEARANCE
            available_drop = z_first - z_min
            spacing = (
                min(EDGE_HOLE_AUTO_MAX_SPACING, available_drop / (count - 1))
                if available_drop > 0 else 0.0
            )
        if spacing < min_spacing_vertical - 1e-9:
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
            edge_clearance = access_profile_r + EDGE_HOLE_EDGE_CLEARANCE
            available_span = span - 2.0 * edge_clearance
            spacing = (
                min(EDGE_HOLE_AUTO_MAX_SPACING, available_span / (count - 1))
                if available_span > 0 else 0.0
            )
        if spacing < min_spacing_horizontal - 1e-9:
            raise ValueError(
                f"{count} {access_d:g} mm screwdriver access holes do not fit side by side "
                f"on this {span:g} mm wall. Use one screw, reduce the access "
                "diameter, or use a larger bin."
            )
        for i in range(count):
            offset = (i - (count - 1) / 2.0) * spacing
            holes.append({"tangent_mm": offset, "z_mm": z})

    max_tangent = max(abs(hole["tangent_mm"]) for hole in holes)
    if max_tangent + access_profile_r + 2.0 > span / 2.0 + 1e-9:
        raise ValueError(
            f"The screw pattern is too wide for this {span:g} mm wall. Reduce "
            "the hole count, spacing, or access diameter."
        )
    min_z = min(hole["z_mm"] for hole in holes)
    if min_z - box.base_thickness < access_profile_r + EDGE_HOLE_VERTICAL_CLEARANCE - 1e-9:
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
        standoffs = edge_mount_standoff_plan(box)
    except ValueError as error:
        standoffs = None
        summary["standoff_ribs_error"] = str(error)
    if standoffs is not None:
        summary["standoff_ribs"] = {
            "enabled": True,
            "auto": standoffs["auto"],
            "count": standoffs["count"],
            "contact_plane_mm": standoffs["contact_plane_mm"],
            "projection_mm": standoffs["clip_standoff_mm"],
        }
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


def _print_safe_profile_radius(
    requested_radius: float, sections: int = EDGE_HOLE_PROFILE_SECTIONS,
) -> float:
    """The faceted polygon radius that circumscribes ``requested_radius``.

    A regular polygon whose vertices sit on the requested radius is
    inscribed and slightly smaller than the true circle between vertices;
    dividing by ``cos(pi / sections)`` makes the polygon circumscribe the
    requested circle instead, so a round tool/screw of the requested
    diameter is never pinched by mesh faceting.
    """
    return requested_radius / math.cos(math.pi / sections)


def _print_safe_hole_roof_rise(
    requested_radius: float, sections: int = EDGE_HOLE_PROFILE_SECTIONS,
) -> float:
    profile_r = _print_safe_profile_radius(requested_radius, sections)
    return math.sqrt(2.0) * profile_r


def _print_safe_hole_profile(
    requested_radius: float, sections: int = EDGE_HOLE_PROFILE_SECTIONS,
) -> Polygon:
    """A round hole profile capped with a 45-degree pointed roof.

    The circular clearance of ``requested_radius`` is fully preserved (the
    faceted circle circumscribes it); only the upper boundary is replaced
    with two 45-degree faces meeting at a +Z apex, so the cut prints without
    horizontal-roof support.
    """
    profile_r = _print_safe_profile_radius(requested_radius, sections)
    # Construct one boundary. Unioning a faceted circle with a triangle at
    # tangent points creates tiny split edges that earcut extrudes as an open
    # mesh, which Manifold correctly refuses as a boolean cutter.
    arc_sections = max(6, math.ceil(0.75 * sections))
    theta = np.linspace(3.0 * math.pi / 4.0, 9.0 * math.pi / 4.0,
                        arc_sections + 1)
    profile = Polygon([
        (profile_r * math.cos(t), profile_r * math.sin(t)) for t in theta
    ] + [(0.0, math.sqrt(2.0) * profile_r)])
    if not isinstance(profile, Polygon) or not profile.is_valid or profile.area <= 0.0:
        raise ValueError("invalid Edge Mount print-safe hole profile")
    return profile


def _axis_print_safe_hole(
    axis: str, coord_a: float, coord_b: float, tangent: float, z: float,
    radius: float,
) -> trimesh.Trimesh:
    """A pointed-roof hole cutter swept along the wall-normal ``axis``.

    The profile's apex always points toward +Z, independent of which wall
    (Front/Back/Left/Right) it cuts.
    """
    height = abs(coord_b - coord_a)
    if height <= 1e-6:
        raise ValueError("an Edge Mount hole cutter has no length")
    center = (coord_a + coord_b) / 2.0
    profile = translate_polygon(_print_safe_hole_profile(radius), xoff=tangent, yoff=z)
    if axis == "y":
        solid = _extrude_xz_profile(profile, height)
        solid.apply_translation((0.0, center, 0.0))
    else:
        solid = _extrude_yz_profile(profile, height)
        solid.apply_translation((center, 0.0, 0.0))
    return solid


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
    standoffs = edge_mount_standoff_plan(box)
    if standoffs is not None:
        # A rib can project beyond a local wavy crest. Cut through its shared
        # flat contact plane, not merely through the original wall skin.
        screw_a = float(standoffs["contact_plane_mm"]) - sign * EDGE_BOOLEAN_OVERTRAVEL
    screw_b = cavity_sel + sign * EDGE_BOOLEAN_OVERTRAVEL
    cutters = [_axis_print_safe_hole(axis, screw_a, screw_b, tangent, z, screw_r)]
    if cut_driver_passage:
        access_far = outer_opp + sign * EDGE_BOOLEAN_OVERTRAVEL
        cutters.append(_axis_print_safe_hole(axis, cavity_sel, access_far, tangent, z, access_r))
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


def _build_label_plate_mesh(box: BoxSpec, plan: dict[str, object], *, top_z: float | None = None) -> trimesh.Trimesh:
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
    top_z = box.z if top_z is None else top_z
    solid.apply_translation((0.0, 0.0, top_z - thickness))
    solid.remove_unreferenced_vertices()
    solid.merge_vertices()
    return solid


def _extrude_parts(footprint, height: float, z: float) -> list[trimesh.Trimesh]:
    pieces = list(footprint.geoms) if isinstance(footprint, MultiPolygon) else [footprint]
    solids = []
    for piece in pieces:
        if not piece.is_empty and piece.area > 1e-7:
            solid = _extrude_polygon(piece, height)
            solid.apply_translation((0.0, 0.0, z))
            solids.append(solid)
    return solids


def _retention_ramp(
    box: BoxSpec, side: str, tangent: float, z0: float, z1: float,
) -> trimesh.Trimesh:
    """A short, printable 45-degree inner-leg snap rib at one wall location."""
    inward = 1.0 if side in ("front", "left") else -1.0
    samples = np.linspace(
        tangent - EDGE_LABEL_CLIP_RETENTION_SPAN_MM / 2.0,
        tangent + EDGE_LABEL_CLIP_RETENTION_SPAN_MM / 2.0,
        9,
    )
    cavity_samples = [_wall_surface_coords(box, side, float(one))[1] for one in samples]
    # A localized straight ramp is placed from the most inward real cavity
    # sample in its 4 mm span, so the wave can never turn a clearance into a
    # collision between samples.
    cavity = max(cavity_samples) if inward > 0 else min(cavity_samples)
    clearance = EDGE_LABEL_CLIP_FACE_CLEARANCE_MM
    interference = EDGE_LABEL_CLIP_RETENTION_MM
    overlap = EDGE_LABEL_CLIP_RAMP_OVERLAP_MM
    # Profile coordinates are inward distance from the real cavity surface
    # (horizontal) and Z (vertical).  Both slopes rise one Z mm per inward
    # mm, so the entry and release ramps are exactly 45 degrees.
    profile = Polygon([
        (clearance, z0),
        (clearance + overlap, z0),
        (clearance + overlap, z1),
        (clearance, z1),
        (clearance - interference, z1 - interference),
        (clearance - interference, z0 + interference),
    ])
    rib = _extrude_polygon(profile, EDGE_LABEL_CLIP_RETENTION_SPAN_MM)
    t0 = tangent - EDGE_LABEL_CLIP_RETENTION_SPAN_MM / 2.0
    transform = np.eye(4)
    if side == "front":
        transform[:3, :3] = ((0.0, 0.0, 1.0), (inward, 0.0, 0.0), (0.0, 1.0, 0.0))
        transform[:3, 3] = (t0, cavity, 0.0)
    elif side == "back":
        transform[:3, :3] = ((0.0, 0.0, 1.0), (inward, 0.0, 0.0), (0.0, 1.0, 0.0))
        transform[:3, 3] = (t0, cavity, 0.0)
    elif side == "left":
        transform[:3, :3] = ((inward, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
        transform[:3, 3] = (cavity, t0, 0.0)
    else:
        transform[:3, :3] = ((inward, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0))
        transform[:3, 3] = (cavity, t0, 0.0)
    rib.apply_transform(transform)
    return rib


def make_edge_mount_label_part(box: BoxSpec) -> trimesh.Trimesh | None:
    """The installed separate plate and continuous clip around the real wall."""
    plan = edge_mount_label_plan(box)
    if plan is None or plan["label_type"] != "separate":
        return None
    side = str(plan["side"])
    thickness = float(plan["thickness_mm"])
    rectangle = _plate_rectangle(box, side, float(plan["plate_length_mm"]) / 2.0, float(plan["projection_mm"]))
    outer = wavy_outer_polygon(box)
    cavity = wavy_cavity_polygon(box)
    clearance = EDGE_LABEL_CLIP_FACE_CLEARANCE_MM
    leg_thickness = EDGE_LABEL_CLIP_LEG_THICKNESS_MM
    # The legs begin clear of each real face.  The bridge lives only above the
    # rim, where it can straddle the wall without touching it.
    outer_leg = outer.buffer(clearance + leg_thickness).difference(
        outer.buffer(clearance)
    ).intersection(rectangle)
    inner_leg = cavity.buffer(-clearance).difference(
        cavity.buffer(-(clearance + leg_thickness))
    ).intersection(rectangle)
    bridge = outer.buffer(clearance + leg_thickness).difference(
        cavity.buffer(-(clearance + leg_thickness))
    ).intersection(rectangle)
    half = float(plan["plate_length_mm"]) / 2.0
    rib_half = EDGE_LABEL_CLIP_RETENTION_SPAN_MM / 2.0
    # The snap ribs sit near the label's ends but never out where a Full Side
    # label's ends wrap the bin corner, where they would bite into the wall.
    offset = max(0.0, min(half - 2.0 * rib_half,
                          _wall_tangential_span(box, side) / 2.0 - EDGE_LABEL_RIB_CORNER_KEEP_MM))
    low_z = box.z - EDGE_LABEL_CLIP_DEPTH_MM
    # The outside leg stays shallow. The inside leg is deeper so it can reach
    # the ordinary wall locks; where a lock sits under the label it is notched
    # with the shared lock receiver profile, so it seats over the bump without
    # touching and catches on its chamfers when pulled straight up.
    inner_depth = edge_mount_inner_leg_depth_mm(box)
    legs = _extrude_parts(outer_leg, EDGE_LABEL_CLIP_DEPTH_MM + thickness, low_z)
    inner_pieces = _extrude_parts(inner_leg, inner_depth + thickness, box.z - inner_depth)
    if inner_pieces:
        inner_solid = union(inner_pieces) if len(inner_pieces) > 1 else inner_pieces[0]
        # A Full Side label's leg also wraps into the corners, so any wall's
        # lock that reaches the leg needs its receiver, not only the label's
        # own wall. A lock the leg never comes near is left alone.
        lo, hi = inner_solid.bounds
        receivers = [
            cutter
            for wall in _EDGE_MOUNT_WALL_NAME.values()
            for cutter in wall_lock_receivers(box, wall, -math.inf, math.inf)
            if bool(np.all(cutter.bounds[0] <= hi) and np.all(cutter.bounds[1] >= lo))
        ]
        if receivers:
            inner_solid = difference([inner_solid, *receivers])
        legs.append(inner_solid)
    caps = _extrude_parts(bridge, thickness, box.z)
    rib_z0 = low_z + EDGE_LABEL_CLIP_RETENTION_MM
    rib_z1 = box.z - EDGE_LABEL_CLIP_RETENTION_MM
    ramp_ribs = [_retention_ramp(box, side, tangent, rib_z0, rib_z1) for tangent in (-offset, offset)]
    plate = _build_label_plate_mesh(box, plan, top_z=box.z + thickness)
    return union([plate, *legs, *caps, *ramp_ribs])


def apply_edge_mount_hole_cuts(
    box: BoxSpec,
    body: trimesh.Trimesh,
    *,
    cut_driver_passages: bool = True,
    geometry_owner: str = "Edge Mount body",
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
    if not cutter.is_volume:
        raise ValueError("Edge Mount screw/driver cutter is not a valid volume")
    # A cut whose bounds cannot reach this body is an exact no-op. In
    # particular, preview may contain independent non-volume helper meshes.
    tolerance = 1e-9
    if np.any(body.bounds[1] < cutter.bounds[0] - tolerance) or np.any(
        cutter.bounds[1] < body.bounds[0] - tolerance
    ):
        return body
    if not body.is_volume:
        raise ValueError(f"{geometry_owner} is not a valid volume for Edge Mount screw cutting")
    # difference() retains sub-micron vertex distinctions that the 3MF writer
    # rounds away. Weld on that writer's coordinate grid here, then validate:
    # otherwise a valid in-memory cut can export with a detached zero-area
    # triangle. This is limited to actual Edge Mount cuts; no-op bodies keep
    # their exact original vertices and identity.
    result = difference([body, cutter])
    result.vertices = np.round(result.vertices, EDGE_3MF_DECIMALS)
    result.merge_vertices()
    # A sub-micron triangle can collapse to zero area on that grid. Drop only
    # those collapsed faces; retaining them creates a detached two-face flap
    # when 3MF reloads the cut.
    result.update_faces(result.area_faces > 0.0)
    result.remove_unreferenced_vertices()
    if not result.is_volume:
        raise ValueError(f"{geometry_owner} Edge Mount cut is not a valid volume")
    return result


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
    if label_plan is not None and label_plan["label_type"] == "integrated":
        plate = _build_label_plate_mesh(box, label_plan)
        # union() already cleans up after itself (and only keeps the clean
        # copy when that does not break watertightness) - an extra unguarded
        # clean-up call here has, in practice, turned an otherwise-valid
        # solid non-watertight and failed the boolean cut that follows.
        result = union([result, plate])
    standoffs = make_edge_mount_standoff_ribs(box)
    if standoffs is not None:
        result = union([result, standoffs])
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
    top_z = box.z + float(plan["thickness_mm"]) if plan["label_type"] == "separate" else box.z
    mesh = text_prism(outline, top_z, depth=float(plan["text_depth_mm"]), raised=bool(plan["raised"]))
    return str(plan["text"]), mesh, bool(plan["raised"])
