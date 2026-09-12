"""Divider feature defaults and geometry."""
from __future__ import annotations
import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from organizer_engine import (
    BoxSpec, TOP_LABEL_CAP_HEIGHT, TOP_LABEL_LEDGE_DEPTH, TOP_LABEL_MARGIN,
    WAVE_AMPLITUDE, _rounded, flat_cavity_polygon, text_outline, text_prism,
    wavy_cavity_polygon, build_scoop_region,
)
from organizer_geometry import (
    _extrude_polygon, _extrude_xz_profile, _extrude_yz_profile,
    difference, intersection, union,
)
from ._core import Feature, Zone, connector_keep_out
from ._divider_cells import (
    DividerCell,
    _divider_cross_centres,
    _even_centres,
    divider_cells,
    divider_grid_counts,
    divider_scoop_targets,
    normalize_divider_scoop,
)
from ._registry import (
    OptionDefinition,
    SettingInteraction,
    defaults,
    feature,
    register_setting_interactions,
    resolved_options,
)
from ._scoop import scoop_region, scoop_settings
MAX_DIVIDER_ANGLE = 45.0
MIN_WEDGE_EDGE = 0.4
DIVIDER_CHAMFER = 1.0
BOTTOM_SLOPE_MAX = 75.0
BOTTOM_EMBED = 0.4
BOTTOM_CROSSBAR_THICKNESS = 2.4
BOTTOM_CROSSBAR_CHAMFER = 1.0
RIB_THICKNESS = 1.6
DIVISION_TEXT_DEPTH = 0.6
# Clear gap kept between a base-level (floor) division label and whatever bounds
# its compartment - a divider wall face, or the bin's own wall. The bin side
# includes the wave's inward swing so a full-span divider's label still clears
# the crest, not just the safe rectangle.
DIVISION_TEXT_MARGIN = TOP_LABEL_MARGIN + WAVE_AMPLITUDE
# Rim-level division labels can ride on a real shelf welded to the divider, the
# same self-supporting ledge the box's own rim label uses: flat top at the
# divider height, a 45-degree underside so it prints without support, and the
# lettering inlaid flush for its own filament colour.
DIVISION_SHELF_DEPTH = TOP_LABEL_LEDGE_DEPTH
DIVISION_SHELF_EMBED = 0.6
DIVISION_SHELF_TEXT_MARGIN = TOP_LABEL_MARGIN
DIVISION_CAP_MAX = TOP_LABEL_CAP_HEIGHT
DIVISION_CAP_MIN = 2.5


@defaults("divider")
def divider_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    zone = one.zone
    along = one.along
    count = one.count or 1
    span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
    return {
        "thickness": RIB_THICKNESS,
        "height": connector_keep_out(box) - base_z,
        "angle": 0.0,
        # Fence-post spacing: this many equal gaps fill the zone's cross
        # axis, including from each end divider to its side of the zone -
        # so at count == 1 it lands the one divider exactly on the zone's
        # own centre. An explicit value overrides this and is used as-is
        # (see build_divider), which only stays centred if it happens to
        # equal this same auto value.
        "spacing": span / (count + 1),
        # Sloped tool-slot bottoms - see _divider_support_bottoms. A zero
        # angle adds nothing, so an older design with none of these keys
        # keeps exactly the geometry it always had.
        "bottom_angle": 0.0,
        "slope_base": 0,
        "reverse_bottom": 0,
        "alternate_bottom": 0,
        "minimal_bottom": 0,
        "bottom_supports": 3,
        "label_divisions": 0,
        "division_level": "base",
        # Which bin wall a rim-level label shelf faces.
        "division_side": "back",
        # Grid dividers: this many walls across X and across Y. Both zero (the
        # default) keeps the legacy single-direction divider driven by
        # ``along``/``count``; set either and the divider becomes a grid.
        "count_x": 0,
        "count_y": 0,
    }


def _divider_scoops(
    box: BoxSpec, spec_feature: Feature, base_z: float
) -> list[trimesh.Trimesh]:
    """Compose the shared Scoop profile into every Divider cell when enabled."""
    config = spec_feature.options.get("scoop")
    targets = divider_scoop_targets(box, spec_feature, base_z)
    if not isinstance(config, dict) or not targets:
        return []
    settings = scoop_settings(box, config, base_z, allow_legacy_height=False)
    by_identity = {
        cell.identity: cell for cell in divider_cells(box, spec_feature, base_z)
    }
    solids = []
    for identity in targets:
        region = scoop_region(by_identity[identity].zone, settings, "x")
        solids.append(build_scoop_region(
            (region.x0, region.y0, region.x1, region.y1),
            base_z, settings.height, "x",
        ))
    return solids


@feature(
    "divider", title="Divider", display="Divider — split the bin",
    description="A straight wall that splits the floor into compartments.",
    capabilities=("qty", "along"),
    options=(
        OptionDefinition("Width", "thickness", "1.6"),
        OptionDefinition("Height", "height", ""),
        OptionDefinition("Spacing", "spacing", ""),
        OptionDefinition("Degree °", "bottom_angle", "0"),
        OptionDefinition("Number of crossbars", "bottom_supports", "3", "integer"),
        OptionDefinition("X quantity", "count_x", 0, "integer", False),
        OptionDefinition("Y quantity", "count_y", 0, "integer", False),
        OptionDefinition("Wall angle", "angle", 0, "number", False),
        OptionDefinition("Use sloped base", "slope_base", False, "boolean", False),
        OptionDefinition("Reverse bottom", "reverse_bottom", False, "boolean", False),
        OptionDefinition("Alternate bottom", "alternate_bottom", False, "boolean", False),
        OptionDefinition("Minimal bottom", "minimal_bottom", False, "boolean", False),
        OptionDefinition("Label divisions", "label_divisions", False, "boolean", False),
        OptionDefinition("Division level", "division_level", "base", "enum", False),
        OptionDefinition("Division side", "division_side", "back", "enum", False),
        OptionDefinition("Division labels", "division_labels", (), "json", False),
        OptionDefinition("Compartment Scoop", "scoop", {}, "json", False),
    ), order=60,
)
def build_divider(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """One or more evenly spaced parallel walls subdividing the bin."""
    spec_feature = normalize_divider_scoop(box, spec_feature, base_z)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        solids = _build_divider_grid(box, spec_feature, base_z, options, grid_x, grid_y)
        solids.extend(_divider_scoops(box, spec_feature, base_z))
        return solids
    thickness = options["thickness"]
    height = options["height"]
    angle = options.get("angle", 0.0)
    if thickness <= 0.0 or height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("divider thickness and height must fit inside the bin")
    along = spec_feature.along
    count = spec_feature.count or 1
    if count < 1:
        raise ValueError("divider count must be positive or automatic")
    spacing = options["spacing"]
    if spacing <= 0.0:
        raise ValueError("divider spacing must be positive")
    if count > 1:
        lean = height * math.tan(math.radians(angle)) if angle else 0.0
        needed_gap = thickness + 2.0 * abs(lean)
        if spacing < needed_gap:
            raise ValueError(
                f"{count} dividers {spacing:.1f} mm apart need at least "
                f"{needed_gap:.1f} mm between centres - increase spacing, "
                "reduce thickness, or reduce the angle"
            )
    span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
    needed_span = spacing * (count + 1)
    if needed_span > span + 1e-9:
        raise ValueError(
            f"{count} dividers {spacing:.1f} mm apart need {needed_span:.1f} mm "
            f"across but the zone gives {span:.1f} mm"
        )
    centres = _divider_cross_centres(zone, along, count, spacing)
    solids: list[trimesh.Trimesh] = []
    for cross_centre in centres:
        shift = cross_centre - (zone.centre[1] if along == "x" else zone.centre[0])
        one_zone = (
            Zone(zone.x0, zone.y0 + shift, zone.x1, zone.y1 + shift) if along == "x"
            else Zone(zone.x0 + shift, zone.y0, zone.x1 + shift, zone.y1)
        )
        one = replace(spec_feature, zone=one_zone)
        if angle != 0.0 and one.full_span:
            solids.extend(_full_span_leaning_divider(box, one, thickness, height, angle, base_z))
        elif one.full_span:
            solids.extend(_full_span_divider(box, along, cross_centre, thickness, base_z, height))
        else:
            solids.extend(_divider_wall(box, one, thickness, height, angle, base_z))
    solids.extend(_divider_sloped_bottoms(
        box, spec_feature, options, along, centres, height, base_z,
    ))
    # A rim-level label rides on its own welded shelf, which has to be fused
    # to the divider here to print as one piece. A base-level label is an
    # inlay sunk into the floor instead - build_texts/apply_texts cut its
    # pocket and write it as its own object, so it is left out of this list.
    for _text_label, text_solid, raised in divider_division_texts(box, spec_feature, base_z):
        if raised:
            solids.append(text_solid)
    solids.extend(_divider_scoops(box, spec_feature, base_z))
    return solids


def _build_divider_grid(
    box: BoxSpec, spec_feature: Feature, base_z: float, options: dict,
    grid_x: int, grid_y: int,
) -> list[trimesh.Trimesh]:
    """A grid of dividers - ``grid_x`` walls across X, ``grid_y`` across Y -
    cutting the zone into a ``(grid_x + 1) x (grid_y + 1)`` set of cells.

    Each wall is built by the same helpers a single-direction divider uses, so
    a full-span grid still hugs the box's true wavy wall and every wall still
    gets its base chamfer. Division labels, when on, drop one per cell.
    """
    zone = spec_feature.zone
    thickness = options["thickness"]
    height = options["height"]
    angle = float(options.get("angle", 0.0) or 0.0)
    if thickness <= 0.0 or height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("divider thickness and height must fit inside the bin")
    full_span = spec_feature.full_span
    solids: list[trimesh.Trimesh] = []
    # Walls that divide X run along Y; walls that divide Y run along X.
    for centre in _even_centres(zone.x0, zone.x1, grid_x):
        solids.extend(_one_grid_wall(
            box, spec_feature, "y", centre, thickness, height, angle, base_z, full_span,
        ))
    for centre in _even_centres(zone.y0, zone.y1, grid_y):
        solids.extend(_one_grid_wall(
            box, spec_feature, "x", centre, thickness, height, angle, base_z, full_span,
        ))
    slope_along = spec_feature.along if spec_feature.along in ("x", "y") else "x"
    slope_centres = (
        _even_centres(zone.y0, zone.y1, grid_y)
        if slope_along == "x"
        else _even_centres(zone.x0, zone.x1, grid_x)
    )
    # The dividers running the same way as the slope cut the ramp into cells;
    # each cell restarts its own slope from the floor rather than one unbroken
    # ramp sweeping across them.
    slope_run_splits = (
        _even_centres(zone.x0, zone.x1, grid_x)
        if slope_along == "x"
        else _even_centres(zone.y0, zone.y1, grid_y)
    )
    solids.extend(_divider_sloped_bottoms(
        box, spec_feature, options, slope_along, slope_centres, height, base_z,
        run_splits=slope_run_splits,
    ))
    # See build_divider: only a rim-level label's welded shelf belongs in the
    # divider's own solids. A base-level label is a floor inlay left for
    # build_texts/apply_texts to cut and write as its own object.
    for _label, text_solid, raised in divider_division_texts(box, spec_feature, base_z):
        if raised:
            solids.append(text_solid)
    return solids


def _one_grid_wall(
    box: BoxSpec, spec_feature: Feature, along: str, centre: float,
    thickness: float, height: float, angle: float, base_z: float, full_span: bool,
) -> list[trimesh.Trimesh]:
    """One wall of a grid divider, centred on ``centre`` of its cross axis."""
    if full_span and angle == 0.0:
        return _full_span_divider(box, along, centre, thickness, base_z, height)
    zone = spec_feature.zone
    half_t = thickness / 2.0
    if along == "y":
        wall_zone = Zone(centre - half_t, zone.y0, centre + half_t, zone.y1)
    else:
        wall_zone = Zone(zone.x0, centre - half_t, zone.x1, centre + half_t)
    one = replace(spec_feature, zone=wall_zone, along=along)
    if full_span and angle != 0.0:
        return _full_span_leaning_divider(box, one, thickness, height, angle, base_z)
    return _divider_wall(box, one, thickness, height, angle, base_z)


def _option_flag(value: object) -> bool:
    """A yes/no option however it arrived - real bool, or a browser string."""
    if isinstance(value, str):
        return value.strip().lower() not in {"", "false", "0", "no", "off"}
    return bool(value)


def _divider_sloped_bottoms(
    box: BoxSpec, spec_feature: Feature, options: dict, along: str,
    centres: list[float], height: float, base_z: float,
    run_splits: list[float] | None = None,
) -> list[trimesh.Trimesh]:
    angle = float(options.get("bottom_angle", 0.0) or 0.0)
    # A saved design may carry the checkbox without the newer angle key.
    # Keep that design visibly sloped using the editor's 20-degree default.
    if angle == 0.0 and _option_flag(options.get("slope_base")):
        if spec_feature.options.get("bottom_angle") in (None, ""):
            angle = 20.0
    if not angle:
        return []
    raw_supports = options.get("bottom_supports", 3)
    supports = (
        int(round(float(raw_supports))) if raw_supports not in (None, "") else 3
    )
    solids = _divider_support_bottoms(
        box, spec_feature.zone, along, centres, height, base_z, angle,
        _option_flag(options.get("reverse_bottom")),
        _option_flag(options.get("alternate_bottom")),
        _option_flag(options.get("minimal_bottom")),
        supports, spec_feature.full_span, run_splits,
    )
    for solid in solids:
        solid.metadata["wavefinity_preview_kind"] = "slope"
    return solids


def _bottom_slot_bounds(
    zone: Zone, along: str, centres: Iterable[float],
) -> list[tuple[float, float]]:
    """The N+1 tool slots a divider's N wall centres cut its zone into.

    Boundaries are the wall centres plus the zone's own two cross-axis edges
    (see the task's "slot boundaries from the divider centers and the divider
    zone's two cross-axis boundaries"), ordered low to high so ``Alternate
    slopes`` can walk them in a stable order.
    """
    if along == "x":
        edges = sorted([zone.y0, *centres, zone.y1])
    else:
        edges = sorted([zone.x0, *centres, zone.x1])
    return [(edges[index], edges[index + 1]) for index in range(len(edges) - 1)]


def _divider_grid_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float, labels: list,
    grid_x: int, grid_y: int,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """One label per grid-divider cell, row-major from the low (front-left)
    corner: cell ``(row, col)`` takes ``labels[row * (grid_x + 1) + col]``.
    """
    options = spec_feature.options or {}
    zone = spec_feature.zone
    thickness = float(options.get("thickness", RIB_THICKNESS) or RIB_THICKNESS)
    height = float(options.get("height", connector_keep_out(box) - base_z)
                   or (connector_keep_out(box) - base_z))
    x_edges = [zone.x0, *_even_centres(zone.x0, zone.x1, grid_x), zone.x1]
    y_edges = [zone.y0, *_even_centres(zone.y0, zone.y1, grid_y), zone.y1]
    n_cols, n_rows = len(x_edges) - 1, len(y_edges) - 1
    level = str(options.get("division_level", "base")).strip().lower()
    if level == "rim":
        return _divider_grid_rim_texts(box, spec_feature, base_z, labels)
    z = base_z

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for row in range(n_rows):
        for col in range(n_cols):
            idx = row * n_cols + col
            if idx >= len(labels):
                continue
            text = str(labels[idx] or "").strip()
            if not text:
                continue
            x0 = x_edges[col] + (0.0 if col == 0 else thickness / 2.0) + DIVISION_TEXT_MARGIN
            x1 = x_edges[col + 1] - (0.0 if col == n_cols - 1 else thickness / 2.0) - DIVISION_TEXT_MARGIN
            y0 = y_edges[row] + (0.0 if row == 0 else thickness / 2.0) + DIVISION_TEXT_MARGIN
            y1 = y_edges[row + 1] - (0.0 if row == n_rows - 1 else thickness / 2.0) - DIVISION_TEXT_MARGIN
            if level == "base" and isinstance(options.get("scoop"), dict):
                # Every Divider Scoop occupies the low-Y half (or less) of its
                # compartment. Keep floor lettering wholly in the guaranteed
                # untouched high-Y band.
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
            try:
                solid = text_prism(outline, z, depth=DIVISION_TEXT_DEPTH)
            except Exception:
                continue
            results.append((text, solid, False))
    return results


def _division_shelf_solid(
    edge: float, edge_axis: str, span_lo: float, span_hi: float,
    inward: float, z_top: float, depth: float, embed: float,
) -> trimesh.Trimesh:
    """A rim-height label ledge welded along one edge of a compartment.

    ``edge`` is the fixed cross coordinate of that edge - a ``y`` value when
    the edge runs along ``x``, an ``x`` value when it runs along ``y``.
    ``inward`` is +1 or -1, the way the compartment lies off it. The ledge
    keeps a flat top at ``z_top`` and a 45-degree self-supporting underside
    that falls ``depth`` back to the edge line, with a short buried lip so it
    fuses cleanly to the divider crest (or bin wall) it sits on.
    """
    near = edge - inward * embed          # buried, inside the crest / wall
    far = edge + inward * depth           # inner top lip, over the compartment
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
    return solid


def _divider_grid_rim_texts(
    box: BoxSpec, spec_feature: Feature, base_z: float, labels: list,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """One rim-level label shelf per grid compartment.

    This is the Divider-cell adapter for the Text part's Rim Level behavior:
    a 7 mm shelf, 45-degree underside, flush inlay, and letters no larger than
    the same fixed 5 mm rim-label size.
    """
    options = spec_feature.options or {}
    side = str(options.get("division_side", "back")).strip().lower()
    side = {"front": "bottom", "back": "top"}.get(side, side)
    if side not in ("left", "right", "top", "bottom"):
        side = "top"
    height = float(options.get("height", connector_keep_out(box) - base_z)
                   or (connector_keep_out(box) - base_z))
    z_top = base_z + height
    cells = divider_cells(box, spec_feature, base_z)
    max_depth = min(DIVISION_SHELF_DEPTH, max(2.0, height - 1.0))

    picked: list[tuple[str, DividerCell, float]] = []
    shared_cap = DIVISION_CAP_MAX
    for idx, cell in enumerate(cells):
        if idx >= len(labels):
            break
        text = str(labels[idx] or "").strip()
        if not text:
            continue
        across = cell.zone.depth if side in ("top", "bottom") else cell.zone.width
        along = cell.zone.width if side in ("top", "bottom") else cell.zone.depth
        depth_here = min(max_depth, across - 1.0)
        if depth_here < DIVISION_CAP_MIN:
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
    shared_cap = max(DIVISION_CAP_MIN, min(DIVISION_CAP_MAX, shared_cap))

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, cell, depth_here in picked:
        if side in ("top", "bottom"):
            edge = cell.zone.y1 if side == "top" else cell.zone.y0
            edge_axis = "x"
            lo = cell.zone.x0 + DIVISION_SHELF_TEXT_MARGIN
            hi = cell.zone.x1 - DIVISION_SHELF_TEXT_MARGIN
            inward = -1.0 if side == "top" else 1.0
            cx = (cell.zone.x0 + cell.zone.x1) / 2.0
            cy = edge + inward * depth_here / 2.0
            turn = 0.0 if side == "top" else 180.0
        else:
            edge = cell.zone.x0 if side == "left" else cell.zone.x1
            edge_axis = "y"
            lo = cell.zone.y0 + DIVISION_SHELF_TEXT_MARGIN
            hi = cell.zone.y1 - DIVISION_SHELF_TEXT_MARGIN
            inward = 1.0 if side == "left" else -1.0
            cx = edge + inward * depth_here / 2.0
            cy = (cell.zone.y0 + cell.zone.y1) / 2.0
            turn = 90.0 if side == "left" else -90.0
        if hi <= lo:
            continue
        try:
            shelf = _division_shelf_solid(
                edge, edge_axis, lo, hi, inward, z_top, depth_here,
                DIVISION_SHELF_EMBED,
            )
            outline = text_outline(text, shared_cap)
            if turn:
                outline = affinity.rotate(
                    outline, turn, origin=(0.0, 0.0), use_radians=False,
                )
            outline = affinity.translate(outline, xoff=cx, yoff=cy)
            inlay = text_prism(outline, z_top)
        except Exception:
            continue
        try:
            shelf = difference([shelf, inlay])
        except Exception:
            pass
        results.append((text, shelf, True))
        results.append((text, inlay, True))
    return results


def _division_side_shelves(
    box: BoxSpec, along: str, zone: Zone, slots: list[tuple[float, float]],
    labels: list, thickness: float, base_z: float, height: float, side: str,
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
    z_top = base_z + height
    max_depth = min(DIVISION_SHELF_DEPTH, max(2.0, height - 1.0))
    # Whether this side's edge runs the same way as the divider walls (so the
    # shelf lands right on a crest) or across them (so it bridges crest to
    # crest). Only the on-crest case buries a lip past the edge.
    on_crest = (
        (along == "x" and side in ("top", "bottom"))
        or (along == "y" and side in ("left", "right"))
    )
    embed = DIVISION_SHELF_EMBED if on_crest else 0.0

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
        if depth_here < DIVISION_CAP_MIN:
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
    shared_cap = max(DIVISION_CAP_MIN, min(DIVISION_CAP_MAX, shared_cap))

    results: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, slot_lo, slot_hi, depth_here in picked:
        edge, edge_axis, span_lo, span_hi, inward = geom(slot_lo, slot_hi)
        if on_crest:
            lo = span_lo + DIVISION_SHELF_TEXT_MARGIN
            hi = span_hi - DIVISION_SHELF_TEXT_MARGIN
        else:
            # Weld the bridging ledge into the walls it spans between.
            lo = span_lo - thickness / 2.0
            hi = span_hi + thickness / 2.0
        try:
            shelf = _division_shelf_solid(
                edge, edge_axis, lo, hi, inward, z_top, depth_here, embed,
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
            inlay = text_prism(outline, z_top)
        except Exception:
            results.append((text, shelf, True))
            continue
        try:
            shelf = difference([shelf, inlay])
        except Exception:
            pass
        results.append((text, shelf, True))
        results.append((text, inlay, True))
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

        try:
            solid = text_prism(outline, z, depth=DIVISION_TEXT_DEPTH)
            results.append((text, solid, False))
        except Exception:
            continue

    return results


def _bottom_plane_z(r: float, r0: float, r1: float, rise: float,
                    base_z: float, reverse: bool) -> float:
    """Height of the theoretical sloped plane at run coordinate ``r``.

    Low end at ``base_z`` (the existing support surface); the high end
    ``rise`` above it, toward +run unless ``reverse`` flips it toward -run.
    """
    frac = (r - r0) / (r1 - r0)
    return base_z + (1.0 - frac if reverse else frac) * rise


def _extrude_bottom(
    profile: Polygon, along: str, cross_lo: float, cross_hi: float,
) -> trimesh.Trimesh:
    """Extrude a ``(run, z)`` profile across one slot's cross-axis span.

    The shape varies along the run, so - unlike a divider wall, whose section
    is constant along its length - the profile is the run/z plane and the
    extrusion is across the slot width.
    """
    width = cross_hi - cross_lo
    centre = (cross_lo + cross_hi) / 2.0
    if along == "x":
        solid = _extrude_xz_profile(profile, width)
        solid.apply_translation((0.0, centre, 0.0))
    else:
        solid = _extrude_yz_profile(profile, width)
        solid.apply_translation((centre, 0.0, 0.0))
    return solid


def _divider_support_bottoms(
    box: BoxSpec, zone: Zone, along: str, centres: list[float], height: float,
    base_z: float, angle: float, reverse: bool, alternate: bool,
    minimal: bool, supports: int, full_span: bool = False,
    run_splits: list[float] | None = None,
) -> list[trimesh.Trimesh]:
    """Sloped support under each tool slot so a tool rests tilted, not flat.

    ``angle`` is signed: positive rises along the divider/tool direction - +X
    (to the right) for a divider that runs along x, +Y (to the back) along y -
    and negative rises the other way, toward the left or front. ``reverse``
    flips that whole pattern once more (kept for older saved designs that set
    it as a separate flag); ``alternate`` flips every second slot, ordered
    across the divider zone. A full bottom is one continuous wedge per slot;
    ``minimal`` replaces it with ``supports`` evenly spaced crossbars and uses
    materially less plastic.

    A crossbar hangs off the walls at the height it carries the tool, never
    reaching the floor. Its underside is an inverted V: a 45-degree corbel
    grows inward from the wall on each side of the slot until the two meet at
    a central ridge, and a full bar rides the slope on top of that ridge. The
    whole underside is at 45 degrees and the top faces up, so it prints with
    no support. Where the corbels have no room to meet before the floor - a
    wide slot, or a crossbar down near the low end of the slope - or the slot
    has no wall to hang from (an open end of a divider set into bare floor,
    never a ``full_span`` divider, which has the bin's own side walls), it
    falls back to a floor-standing stem with 45-degree gusset feet. The normal
    bin or insert floor is untouched; this is only the material above it.
    Solids sink ``BOTTOM_EMBED`` into the floor (or into a wall) for a clean
    union.
    """
    if not math.isfinite(angle) or abs(angle) > BOTTOM_SLOPE_MAX:
        raise ValueError(
            f"the slope must be within {BOTTOM_SLOPE_MAX:g} degrees either way; "
            "reduce the slope"
        )
    if angle == 0.0:
        return []
    # A negative slope just points the rise the other way - same wedge,
    # mirrored - so fold its sign into ``reverse`` and work with a magnitude.
    reverse = bool(reverse) ^ (angle < 0.0)
    angle = abs(angle)
    if minimal and supports < 1:
        raise ValueError("number of crossbars must be a positive whole number")
    run = zone.width if along == "x" else zone.depth
    r0, r1 = (zone.x0, zone.x1) if along == "x" else (zone.y0, zone.y1)
    # A grid divider crosses the run with perpendicular walls. Split the run at
    # those wall centres so every cell between them carries its own ramp,
    # starting again from the floor, instead of one ramp sweeping unbroken from
    # one end of the zone to the other. With no splits this is a single segment
    # spanning the whole run - exactly the legacy single-direction behaviour.
    splits = sorted(s for s in (run_splits or []) if r0 + 1e-6 < s < r1 - 1e-6)
    seg_bounds = [r0, *splits, r1]
    segments = list(zip(seg_bounds, seg_bounds[1:]))
    rise = max(hi - lo for lo, hi in segments) * math.tan(math.radians(angle))
    if rise > height + 1e-6 or base_z + rise > box.z + 1e-6:
        raise ValueError(
            "the bottom slope's high end rises past the divider height or the "
            "bin: reduce the bottom slope, shorten the run, or increase the "
            "bin height"
        )
    half_t = BOTTOM_CROSSBAR_THICKNESS / 2.0
    bar_min = 0.8                  # thinnest the "full bar" above the ridge may be
    edge_lo, edge_hi = (zone.y0, zone.y1) if along == "x" else (zone.x0, zone.x1)
    wall_line = box.half_y if along == "x" else box.half_x
    solids: list[trimesh.Trimesh] = []
    for index, (c_lo, c_hi) in enumerate(_bottom_slot_bounds(zone, along, centres)):
        flip = reverse ^ (alternate and index % 2 == 1)
        # Each run segment is one compartment's ramp, rising over its own length.
        for seg_r0, seg_r1 in segments:
            seg_run = seg_r1 - seg_r0
            seg_rise = seg_run * math.tan(math.radians(angle))
            if not minimal:
                if not flip:
                    pts = [(seg_r0, base_z - BOTTOM_EMBED), (seg_r1, base_z - BOTTOM_EMBED),
                           (seg_r1, base_z + seg_rise), (seg_r0, base_z)]
                else:
                    pts = [(seg_r0, base_z - BOTTOM_EMBED), (seg_r1, base_z - BOTTOM_EMBED),
                           (seg_r1, base_z), (seg_r0, base_z + seg_rise)]
                solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
                continue
            # Which side of this slot has a wall to hang a crossbar from. A
            # full-span divider always does on both sides (its own wall, and the
            # bin's); a bare-floor divider's outermost slot has an open end.
            lo_is_edge = math.isclose(c_lo, edge_lo, abs_tol=1e-6)
            hi_is_edge = math.isclose(c_hi, edge_hi, abs_tol=1e-6)
            floating = full_span or (not lo_is_edge and not hi_is_edge)
            # Weld a floating crossbar into the bin's side wall where the slot
            # ends at the zone edge instead of at a divider wall.
            span_lo = -wall_line if (lo_is_edge and full_span) else c_lo
            span_hi = wall_line if (hi_is_edge and full_span) else c_hi
            span_mid = (span_lo + span_hi) / 2.0
            half_span = (span_hi - span_lo) / 2.0
            for step in range(supports):
                centre = seg_r0 + (step + 1) * seg_run / (supports + 1)
                z_left = _bottom_plane_z(centre - half_t, seg_r0, seg_r1, seg_rise, base_z, flip)
                z_right = _bottom_plane_z(centre + half_t, seg_r0, seg_r1, seg_rise, base_z, flip)
                low = min(z_left, z_right)
                # A floating crossbar is a 45-degree corbel growing inward from
                # the wall on each side of the slot; the two meet at a central
                # ridge and a full bar rides the slope on top of it. Its whole
                # underside is at 45 degrees so it prints support-free, and it
                # never reaches the floor. That needs head-room: the corbels
                # climb half the slot's width to meet. Where there isn't room -
                # a wide slot, or a crossbar down near the low end of the slope
                # - fall back to the old floor-standing stem, which prints fine
                # on its own gusset feet.
                z_ridge = low - bar_min
                z_base = z_ridge - half_span
                if not (floating and z_base >= base_z - BOTTOM_EMBED - 1e-9):
                    top_left = max(z_left, base_z + 0.2)
                    top_right = max(z_right, base_z + 0.2)
                    # 45-degree gusset feet, never taller than the stem they brace.
                    chamfer = max(0.0, min(BOTTOM_CROSSBAR_CHAMFER,
                                           top_left - base_z - 0.1,
                                           top_right - base_z - 0.1))
                    pts = [
                        (centre - half_t - chamfer, base_z - BOTTOM_EMBED),
                        (centre + half_t + chamfer, base_z - BOTTOM_EMBED),
                        (centre + half_t, base_z + chamfer),
                        (centre + half_t, top_right),
                        (centre - half_t, top_left),
                        (centre - half_t, base_z + chamfer),
                    ]
                    solids.append(_extrude_bottom(Polygon(pts), along, c_lo, c_hi))
                    continue
                # Inverted-V underside spanning wall to wall, capped by the slope.
                z_ceiling = max(z_left, z_right) + 5.0
                v_profile = Polygon([
                    (span_lo, z_base), (span_mid, z_ridge), (span_hi, z_base),
                    (span_hi, z_ceiling), (span_lo, z_ceiling),
                ])
                cap_profile = Polygon([
                    (centre - half_t, z_base - 5.0), (centre + half_t, z_base - 5.0),
                    (centre + half_t, z_right), (centre - half_t, z_left),
                ])
                if along == "x":
                    under = _extrude_yz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                    under.apply_translation((centre, 0.0, 0.0))
                    cap = _extrude_xz_profile(cap_profile, span_hi - span_lo)
                    cap.apply_translation((0.0, span_mid, 0.0))
                else:
                    under = _extrude_xz_profile(v_profile, BOTTOM_CROSSBAR_THICKNESS)
                    under.apply_translation((0.0, centre, 0.0))
                    cap = _extrude_yz_profile(cap_profile, span_hi - span_lo)
                    cap.apply_translation((span_mid, 0.0, 0.0))
                bar = intersection([under, cap])
                if bar.faces.shape[0] == 0:
                    continue
                solids.append(bar)
    return solids


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
    half_t = thickness / 2.0
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
    if along == "x":
        wall = _extrude_yz_profile(profile, run)
        wall.apply_translation((centre_x, 0.0, 0.0))
    else:
        wall = _extrude_xz_profile(profile, run)
        wall.apply_translation((0.0, centre_y, 0.0))
    return [wall]


def _full_span_leaning_divider(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
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
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
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
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    half_thick = thickness / 2.0
    strip = (
        shapely_box(-half_run, cross_centre - half_thick, half_run, cross_centre + half_thick)
        if along == "x" else
        shapely_box(cross_centre - half_thick, -half_run, cross_centre + half_thick, half_run)
    )
    z0, z1 = base_z, base_z + height
    flat_top = box.base_thickness + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        pieces.append(_trimmed_prism(strip, flat_cavity_polygon(box), z0, min(z1, flat_top)))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        pieces.append(_trimmed_prism(strip, wavy_cavity_polygon(box), wavy_z0, z1))
    if not pieces:
        raise ValueError("divider height leaves nothing to build")
    return pieces


register_setting_interactions("divider", (
    SettingInteraction(
        "count", "cells", "derived", "divider",
        "Legacy single-direction wall count determines logical compartments.",
    ),
    SettingInteraction(
        "spacing", "cells", "derived", "divider",
        "Legacy wall spacing determines logical compartment boundaries.",
    ),
    SettingInteraction(
        "count_x", "cells", "derived", "divider",
        "Grid X wall count determines logical compartment columns.",
    ),
    SettingInteraction(
        "count_y", "cells", "derived", "divider",
        "Grid Y wall count determines logical compartment rows.",
    ),
    SettingInteraction(
        "thickness", "cells", "constraint", "divider",
        "Wall thickness reduces each compartment's usable floor region.",
    ),
    SettingInteraction(
        "scoop.enabled", "scoop.geometry", "enable/disable", "divider",
        "An enabled Divider Scoop builds one shared Scoop in every compartment.",
    ),
    SettingInteraction(
        "cells", "scoop.geometry", "derived", "divider",
        "Each Divider compartment receives one Scoop while the setting is enabled.",
    ),
    SettingInteraction(
        "scoop.depth", "scoop.height", "derived", "scoop",
        "Divider Scoops use the same depth-to-height rule as standalone Scoops.",
    ),
    SettingInteraction(
        "scoop.enabled", "slope_base", "reset", "divider-editor",
        "A curved Scoop and a sloped bottom cannot own the same compartment floor.",
    ),
    SettingInteraction(
        "slope_base", "scoop.enabled", "reset", "divider-editor",
        "Selecting a sloped bottom removes the mutually exclusive curved Scoop.",
    ),
    SettingInteraction(
        "scoop.enabled", "division_labels.region", "auto-adjust", "divider",
        "Base-level division labels move to the high-Y band left clear by the Scoop.",
    ),
    SettingInteraction(
        "count_x", "count", "reset", "divider-editor",
        "Entering either grid quantity retires the legacy single-axis count.",
    ),
    SettingInteraction(
        "count_y", "count", "reset", "divider-editor",
        "Entering either grid quantity retires the legacy single-axis count.",
    ),
    SettingInteraction(
        "thickness", "zone", "auto-adjust", "divider-sizing",
        "Wall width grows the Divider footprint when required.",
    ),
    SettingInteraction(
        "slope_base", "bottom_angle", "enable/disable", "divider-editor",
        "Bottom angle is active only while sloped bottoms are enabled.",
    ),
    SettingInteraction(
        "slope_base", "bottom_supports", "enable/disable", "divider-editor",
        "Crossbar controls are active only for sloped bottoms.",
    ),
    SettingInteraction(
        "minimal_bottom", "bottom_supports", "enable/disable", "divider-editor",
        "Crossbar count is shown only when support crossbars are selected.",
    ),
    SettingInteraction(
        "label_divisions", "division_labels", "enable/disable", "divider-editor",
        "Division label text is active only when compartment labels are enabled.",
    ),
    SettingInteraction(
        "division_level", "division_labels.shelf", "enable/disable", "divider",
        "Rim-level Divider labels use the Text part's selected-side shelf profile.",
    ),
))
