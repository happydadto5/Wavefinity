"""Divider division texts and side shelves."""

from __future__ import annotations

import trimesh
from shapely import affinity
from shapely.geometry import Polygon
from organizer_engine import (
    BoxSpec,
    LOCK_SAFE_SKIN,
    require_text_backing,
    text_outline,
    text_prism,
    wavy_outer_polygon,
)
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    intersection,
)
from .._core import Feature, Zone, connector_keep_out
from .._text import preview_inlay_layer
from .._divider_cells import (
    DividerCell,
    _divider_cross_centres,
    divider_cells,
    divider_grid_counts,
)

from ._consts import (
    RIB_THICKNESS,
    DIVISION_TEXT_DEPTH,
    DIVISION_TEXT_MARGIN,
    DIVISION_SHELF_DEPTH,
    DIVISION_SHELF_EMBED,
    DIVISION_SHELF_WALL_ROOT,
    DIVISION_SHELF_TEXT_MARGIN,
    DIVISION_CAP_MAX,
    DIVISION_SHELF_MIN_DEPTH,
    _option_flag,
)
from ._bottoms import _bottom_slot_bounds


def _divider_grid_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float, labels: list,
    grid_x: int, grid_y: int,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """One label per grid-divider cell, row-major from the low (front-left)
    corner: cell ``(row, col)`` takes ``labels[row * (grid_x + 1) + col]``.
    """
    options = spec_feature.options or {}
    n_cols = grid_x + 1
    level = str(options.get("division_level", "base")).strip().lower()
    if level == "rim":
        return _divider_grid_rim_texts(box, spec_feature, base_z, labels)
    z = base_z

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for cell in divider_cells(box, spec_feature, base_z):
        idx = cell.row * n_cols + cell.column
        if idx >= len(labels):
            continue
        text = str(labels[idx] or "").strip()
        if not text:
            continue
        x0, x1 = cell.zone.x0 + DIVISION_TEXT_MARGIN, cell.zone.x1 - DIVISION_TEXT_MARGIN
        y0, y1 = cell.zone.y0 + DIVISION_TEXT_MARGIN, cell.zone.y1 - DIVISION_TEXT_MARGIN
        if level == "base" and isinstance(options.get("scoop"), dict):
            y0 = (y0 + y1) / 2.0
        cell_w, cell_d = max(1.0, x1 - x0), max(1.0, y1 - y0)
        try:
            probe = text_outline(text, 10.0)
        except Exception:
            continue
        bx0, by0, bx1, by1 = probe.bounds
        pw, ph = bx1 - bx0, by1 - by0
        if pw <= 0 or ph <= 0:
            continue
        avail_w = max(0.5, cell_w - 0.4)
        avail_d = max(0.5, cell_d - 0.4)
        cap = max(2.5, min(avail_d, avail_w / (pw / 10.0)))
        try:
            outline = text_outline(text, cap)
        except Exception:
            continue
        outline = affinity.translate(
            outline, xoff=(x0 + x1) / 2.0, yoff=(y0 + y1) / 2.0
        )
        require_text_backing(z, DIVISION_TEXT_DEPTH, what="division label")
        try:
            solid = preview_inlay_layer(text_prism(outline, z, depth=DIVISION_TEXT_DEPTH))
        except Exception:
            continue
        results.append((text, solid, False))
    return results


def _shelf_edge_is_bin_wall(
    box: BoxSpec, zone: Zone, edge: float, edge_axis: str, inward: float,
) -> bool:
    """Whether a shelf edge is the bin's own wall rather than a divider crest."""
    whole = Zone.whole(box)
    if edge_axis == "x":
        wall, whole_edge = (zone.y1, whole.y1) if inward < 0 else (zone.y0, whole.y0)
    else:
        wall, whole_edge = (zone.x1, whole.x1) if inward < 0 else (zone.x0, whole.x0)
    return abs(edge - wall) < 1e-6 and abs(wall - whole_edge) < 0.05


def _division_shelf_solid(
    edge: float, edge_axis: str, span_lo: float, span_hi: float,
    inward: float, z_top: float, depth: float, embed: float,
    wall_box: BoxSpec | None = None,
) -> trimesh.Trimesh:
    """A rim-height label ledge welded along one edge of a compartment.

    ``edge`` is the fixed cross coordinate of that edge - a ``y`` value when
    the edge runs along ``x``, an ``x`` value when it runs along ``y``.
    ``inward`` is +1 or -1, the way the compartment lies off it. The ledge
    keeps a flat top at ``z_top`` and a 45-degree self-supporting underside
    that falls ``depth`` back to the edge line, with a short buried lip so it
    fuses cleanly to the divider crest (or bin wall) it sits on.
    """
    far = edge + inward * depth           # inner top lip, over the compartment
    if wall_box is not None:
        # Bin wall: keep the same 45-degree underside going on into the wall
        # instead of stopping in a flat ledge that could hang in air where the
        # wall ripples away from the compartment edge.
        root = DIVISION_SHELF_WALL_ROOT
        near = edge - inward * root
        profile = Polygon([
            (near, z_top),
            (far, z_top),
            (edge, z_top - depth),
            (near, z_top - depth - root),
        ])
    else:
        near = edge - inward * embed      # buried, inside the crest
        profile = Polygon([
            (near, z_top),
            (far, z_top),
            (edge, z_top - depth),
            (near, z_top - depth),
        ])
    if not profile.is_valid:
        profile = profile.buffer(0)
    length = span_hi - span_lo
    centre = (span_lo + span_hi) / 2.0
    if edge_axis == "x":
        solid = _extrude_yz_profile(profile, length)
        solid.apply_translation((centre, 0.0, 0.0))
    else:
        solid = _extrude_xz_profile(profile, length)
        solid.apply_translation((0.0, centre, 0.0))
    if wall_box is not None:
        # Never let the deeper root reach the outside: stay inside the wall's
        # exterior safety skin.
        safe = wavy_outer_polygon(wall_box).buffer(-LOCK_SAFE_SKIN)
        low = max(0.0, z_top - depth - DIVISION_SHELF_WALL_ROOT - 0.5)
        limit = _extrude_polygon(safe, z_top + 0.5 - low)
        limit.apply_translation((0.0, 0.0, low))
        solid = intersection([solid, limit])
    return solid


def _divider_grid_rim_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float, labels: list,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """One rim-level label shelf per grid compartment.

    This is the Divider-cell adapter for the Text part's Rim Level behavior:
    a 7 mm shelf, 45-degree underside, flush inlay, and letters no larger than
    the same 5 mm target size.
    """
    options = spec_feature.options or {}
    side = str(options.get("division_side", "back")).strip().lower()
    side = {"front": "bottom", "back": "top"}.get(side, side)
    if side not in ("left", "right", "top", "bottom"):
        side = "top"
    height = float(options.get("height", connector_keep_out(box) - base_z)
                   or (connector_keep_out(box) - base_z))
    cells = divider_cells(box, spec_feature, base_z)
    max_depth = min(DIVISION_SHELF_DEPTH, max(2.0, height - 1.0))

    picked: list[tuple[str, DividerCell, float]] = []
    shared_cap = DIVISION_CAP_MAX
    grid_x, _grid_y = divider_grid_counts(options)
    for cell in cells:
        label_index = cell.row * (grid_x + 1) + cell.column
        if label_index >= len(labels):
            continue
        text = str(labels[label_index] or "").strip()
        if not text:
            continue
        across = cell.zone.depth if side in ("top", "bottom") else cell.zone.width
        along = cell.zone.width if side in ("top", "bottom") else cell.zone.depth
        depth_here = min(max_depth, across - 1.0)
        if depth_here < DIVISION_SHELF_MIN_DEPTH:
            continue
        try:
            probe = text_outline(text, 10.0)
        except Exception:
            continue
        bx0, by0, bx1, by1 = probe.bounds
        pw, ph = bx1 - bx0, by1 - by0
        if pw <= 0 or ph <= 0:
            continue
        avail_width = max(0.5, along - 2.0 * DIVISION_SHELF_TEXT_MARGIN)
        avail_depth = max(
            0.5, depth_here - 2.0 * DIVISION_SHELF_TEXT_MARGIN
        )
        shared_cap = min(
            shared_cap,
            avail_width * 10.0 / pw,
            avail_depth * 10.0 / ph,
        )
        picked.append((text, cell, depth_here))
    if not picked:
        return []
    shared_cap = min(DIVISION_CAP_MAX, shared_cap)
    if shared_cap <= 0.0:
        return []

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, cell, depth_here in picked:
        if side in ("top", "bottom"):
            edge = cell.zone.y1 if side == "top" else cell.zone.y0
            edge_axis = "x"
            lo = cell.zone.x0
            hi = cell.zone.x1
            inward = -1.0 if side == "top" else 1.0
            cx = (cell.zone.x0 + cell.zone.x1) / 2.0
            cy = edge + inward * depth_here / 2.0
            turn = 0.0 if side == "top" else 180.0
        else:
            edge = cell.zone.x0 if side == "left" else cell.zone.x1
            edge_axis = "y"
            lo = cell.zone.y0
            hi = cell.zone.y1
            inward = 1.0 if side == "left" else -1.0
            cx = edge + inward * depth_here / 2.0
            cy = (cell.zone.y0 + cell.zone.y1) / 2.0
            turn = 90.0 if side == "left" else -90.0
        if hi <= lo:
            continue
        z_top = base_z + height
        try:
            shelf = _division_shelf_solid(
                edge, edge_axis, lo, hi, inward, z_top, depth_here,
                DIVISION_SHELF_EMBED,
                box if spec_feature.full_span and _shelf_edge_is_bin_wall(
                    box, spec_feature.zone, edge, edge_axis, inward) else None,
            )
            outline = text_outline(text, shared_cap)
            if turn:
                outline = affinity.rotate(
                    outline, turn, origin=(0.0, 0.0), use_radians=False,
                )
            outline = affinity.translate(outline, xoff=cx, yoff=cy)
            inlay = preview_inlay_layer(text_prism(outline, z_top))
        except Exception:
            continue
        # The shelf is plain body material. The lettering is its own recessed
        # object: the exporter cuts the pocket out of the body and writes the
        # inlay flush in it, exactly like floor Text.
        results.append((text, shelf, True))
        results.append((text, inlay, False))
    return results


def _division_side_shelves(
    box: BoxSpec, along: str, zone: Zone, slots: list[tuple[float, float]],
    labels: list, thickness: float, base_z: float, height: float, side: str,
    full_span: bool = False,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """Rim-level division labels on self-supporting shelves lined up against
    one bin wall, with a single letter height shared by every label.

    ``side`` is ``left`` / ``right`` / ``top`` (back) / ``bottom`` (front).
    Where that edge of a compartment is a divider crest the shelf sits on it;
    where it is the bin's own wall the shelf welds into that instead. Each
    label is inlaid flush into its shelf as its own object.
    """
    side = {"front": "bottom", "back": "top"}.get(side, side)
    if side not in ("left", "right", "top", "bottom"):
        side = "top"
    max_depth = min(DIVISION_SHELF_DEPTH, max(2.0, height - 1.0))
    # Whether this side's edge runs the same way as the divider walls (so the
    # shelf lands right on a crest) or across them (so it bridges crest to
    # crest). Only the on-crest case buries a lip past the edge.
    on_crest = (
        (along == "x" and side in ("top", "bottom"))
        or (along == "y" and side in ("left", "right"))
    )
    # Both the flat crown and the sloped root need material past the wall
    # boundary. A coplanar cross-wall shelf is not a printable joint.
    embed = DIVISION_SHELF_EMBED

    def geom(slot_lo: float, slot_hi: float):
        """(edge, edge_axis, span_lo, span_hi, inward) for one compartment."""
        if along == "x":
            if side == "bottom":
                return slot_lo, "x", zone.x0, zone.x1, 1.0
            if side == "top":
                return slot_hi, "x", zone.x0, zone.x1, -1.0
            if side == "left":
                return zone.x0, "y", slot_lo, slot_hi, 1.0
            return zone.x1, "y", slot_lo, slot_hi, -1.0
        if side == "left":
            return slot_lo, "y", zone.y0, zone.y1, 1.0
        if side == "right":
            return slot_hi, "y", zone.y0, zone.y1, -1.0
        if side == "bottom":
            return zone.y0, "x", slot_lo, slot_hi, 1.0
        return zone.y1, "x", slot_lo, slot_hi, -1.0

    # First pass: the largest letter height that still fits the longest label
    # in the tightest compartment, then clamp it to the box rim label's size.
    picked: list[tuple[str, float, float, float]] = []
    shared_cap = DIVISION_CAP_MAX
    for idx, (slot_lo, slot_hi) in enumerate(slots):
        if idx >= len(labels):
            break
        text = str(labels[idx] or "").strip()
        if not text:
            continue
        _edge, _axis, span_lo, span_hi, _inward = geom(slot_lo, slot_hi)
        depth_here = min(max_depth, (slot_hi - slot_lo) - 1.0) if on_crest else max_depth
        if depth_here < DIVISION_SHELF_MIN_DEPTH:
            continue
        try:
            probe = text_outline(text, 10.0)
        except Exception:
            continue
        bx0, by0, bx1, by1 = probe.bounds
        pw, ph = bx1 - bx0, by1 - by0
        if pw <= 0 or ph <= 0:
            continue
        avail_along = max(0.5, (span_hi - span_lo) - 2.0 * DIVISION_SHELF_TEXT_MARGIN)
        avail_across = max(0.5, depth_here - 2.0 * DIVISION_SHELF_TEXT_MARGIN)
        cap_here = min(avail_along * 10.0 / pw, avail_across * 10.0 / ph)
        shared_cap = min(shared_cap, cap_here)
        picked.append((text, slot_lo, slot_hi, depth_here))
    if not picked:
        return []
    shared_cap = min(DIVISION_CAP_MAX, shared_cap)
    if shared_cap <= 0.0:
        return []

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, slot_lo, slot_hi, depth_here in picked:
        edge, edge_axis, span_lo, span_hi, inward = geom(slot_lo, slot_hi)
        if on_crest:
            lo = span_lo
            hi = span_hi
        else:
            # Weld the bridging ledge into the walls it spans between.
            lo = span_lo - thickness / 2.0
            hi = span_hi + thickness / 2.0
        z_top = base_z + height
        try:
            shelf = _division_shelf_solid(
                edge, edge_axis, lo, hi, inward, z_top, depth_here, embed,
                box if full_span and _shelf_edge_is_bin_wall(
                    box, zone, edge, edge_axis, inward) else None,
            )
        except Exception:
            continue
        try:
            outline = text_outline(text, shared_cap)
        except Exception:
            continue
        turn = {
            "top": 0.0, "bottom": 180.0, "left": 90.0, "right": -90.0,
        }[side]
        if turn:
            outline = affinity.rotate(
                outline, turn, origin=(0.0, 0.0), use_radians=False
            )
        if edge_axis == "x":
            cx = (span_lo + span_hi) / 2.0
            cy = edge + inward * depth_here / 2.0
        else:
            cx = edge + inward * depth_here / 2.0
            cy = (span_lo + span_hi) / 2.0
        outline = affinity.translate(outline, xoff=cx, yoff=cy)
        try:
            inlay = preview_inlay_layer(text_prism(outline, z_top))
        except Exception:
            results.append((text, shelf, True))
            continue
        # The shelf is plain body material. The lettering is its own recessed
        # object: the exporter cuts the pocket out of the body and writes the
        # inlay flush in it, exactly like floor Text.
        results.append((text, shelf, True))
        results.append((text, inlay, False))
    return results


def divider_division_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """(label, text_solid, raised) for each division label on a divider."""
    options = spec_feature.options or {}
    if not _option_flag(options.get("label_divisions")):
        return []
    raw_labels = options.get("division_labels")
    if not raw_labels:
        return []
    if isinstance(raw_labels, str):
        import json
        try:
            labels = json.loads(raw_labels)
        except Exception:
            labels = [s.strip() for s in raw_labels.split(",") if s.strip()]
    elif isinstance(raw_labels, (list, tuple)):
        labels = list(raw_labels)
    else:
        return []

    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        return _divider_grid_texts(box, spec_feature, base_z, labels, grid_x, grid_y)

    zone = spec_feature.zone
    along = spec_feature.along
    count = spec_feature.count or 1
    thickness = float(options.get("thickness", RIB_THICKNESS) or RIB_THICKNESS)
    height = float(options.get("height", connector_keep_out(box) - base_z) or (connector_keep_out(box) - base_z))
    spacing = float(options.get("spacing", 0.0) or 0.0)
    if spacing <= 0.0:
        span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
        spacing = span / (count + 1)

    centres = _divider_cross_centres(zone, along, count, spacing)
    slots = _bottom_slot_bounds(zone, along, centres)
    level = str(options.get("division_level", "base")).strip().lower()
    if level == "rim":
        return _division_side_shelves(
            box, along, zone, slots, labels, thickness, base_z, height,
            str(options.get("division_side", "back")),
            spec_feature.full_span,
        )
    z = base_z

    results = []
    for idx, (slot_low, slot_high) in enumerate(slots):
        if idx >= len(labels):
            break
        text = str(labels[idx] or "").strip()
        if not text:
            continue
        inner_low = slot_low + (0.0 if idx == 0 else thickness / 2.0)
        inner_high = slot_high - (0.0 if idx == len(slots) - 1 else thickness / 2.0)
        # Pull the label band in on every side: off the divider wall faces
        # across the compartment, and off the bin walls at the run-axis ends.
        inner_low += DIVISION_TEXT_MARGIN
        inner_high -= DIVISION_TEXT_MARGIN
        if along == "x":
            label_x0, label_x1 = zone.x0 + DIVISION_TEXT_MARGIN, zone.x1 - DIVISION_TEXT_MARGIN
            label_y0, label_y1 = inner_low, inner_high
        else:
            label_x0, label_x1 = inner_low, inner_high
            label_y0, label_y1 = zone.y0 + DIVISION_TEXT_MARGIN, zone.y1 - DIVISION_TEXT_MARGIN
        if level == "base" and isinstance(options.get("scoop"), dict):
            # Scoops always rise from low Y and use no more than half the
            # compartment depth. The back half is therefore a stable label band.
            label_y0 = (label_y0 + label_y1) / 2.0
        slot_across = max(
            1.0,
            (label_y1 - label_y0) if along == "x" else (label_x1 - label_x0),
        )
        slot_run = max(
            1.0,
            (label_x1 - label_x0) if along == "x" else (label_y1 - label_y0),
        )

        try:
            probe = text_outline(text, 10.0)
        except Exception:
            continue
        bx0, by0, bx1, by1 = probe.bounds
        pw, ph = bx1 - bx0, by1 - by0
        if pw <= 0 or ph <= 0:
            continue
        # The band is already inset by DIVISION_TEXT_MARGIN on every side, so
        # only a hair of slack is needed here to keep glyph edges off the line.
        avail_run = max(0.5, slot_run - 0.4)
        avail_across = max(0.5, slot_across - 0.4)
        cap_by_across = avail_across
        cap_by_run = avail_run / (pw / 10.0)
        cap = max(2.5, min(cap_by_across, cap_by_run))

        try:
            outline = text_outline(text, cap)
        except Exception:
            continue

        if along == "y":
            outline = affinity.rotate(outline, 90.0, origin=(0.0, 0.0), use_radians=False)

        cx = (label_x0 + label_x1) / 2.0
        cy = (label_y0 + label_y1) / 2.0
        outline = affinity.translate(outline, xoff=cx, yoff=cy)

        require_text_backing(z, DIVISION_TEXT_DEPTH, what="division label")
        try:
            solid = preview_inlay_layer(text_prism(outline, z, depth=DIVISION_TEXT_DEPTH))
            results.append((text, solid, False))
        except Exception:
            continue

    return results
