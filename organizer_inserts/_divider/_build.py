"""Divider builders: defaults, grid layouts and wall runs."""

from __future__ import annotations

import math
from dataclasses import replace
import trimesh
from shapely.geometry import Polygon
from organizer_engine import BoxSpec, WAVE_AMPLITUDE, build_scoop_region, wall_depth_for
from organizer_geometry import _extrude_xz_profile, _extrude_yz_profile, intersection
from .._core import Feature, Zone, connector_keep_out
from .._divider_cells import (
    _divider_cross_centres,
    _even_centres,
    divider_cells,
    divider_grid_counts,
    divider_grid_edges,
    divider_owner_matrix,
    divider_scoop_targets,
    normalize_divider_scoop,
    normalized_compartment_spans,
)
from .._registry import (
    OptionDefinition,
    SIDE_CHOICES,
    defaults,
    feature,
    resolved_options,
)
from .._scoop import scoop_default_depth, scoop_region, scoop_settings

from ._consts import MAX_DIVIDER_ANGLE, MIN_WEDGE_EDGE, BOTTOM_SLOPE_MAX, RIB_THICKNESS
from ._bottoms import _divider_sloped_bottoms, _custom_divider_sloped_bottoms
from ._shelf import divider_division_texts
from ._walls import _divider_wall, _full_span_leaning_divider, _full_span_divider


@defaults("divider")
def divider_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    zone = one.zone
    along = one.along
    count = one.count or 1
    span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
    maximum_bottom_angle = divider_max_bottom_angle(box, one, base_z)
    try:
        curved_default_depth = scoop_default_depth(box, base_z)
    except ValueError:
        curved_default_depth = 0.0
    return {
        "wall_style": "straight",
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
        "bottom_default_angle": min(45.0, maximum_bottom_angle),
        "bottom_max_angle": maximum_bottom_angle,
        "curved_default_depth": curved_default_depth,
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


def divider_max_bottom_angle(box: BoxSpec, one: Feature, base_z: float) -> float:
    """Maximum slope from the same longest-run/height rule as the builder."""
    options = one.options or {}
    height = float(options.get("height") or connector_keep_out(box) - base_z)
    run = one.zone.width if one.along == "x" else one.zone.depth
    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        x_edges, y_edges = divider_grid_edges(one.zone, grid_x, grid_y)
        edges = x_edges if one.along == "x" else y_edges
        spans = normalized_compartment_spans(
            options.get("compartment_spans"), len(y_edges) - 1, len(x_edges) - 1,
        )
        if spans:
            run = max([max(hi - lo for lo, hi in zip(edges, edges[1:]))] + [
                (x_edges[col + col_span] - x_edges[col]) if one.along == "x"
                else (y_edges[row + row_span] - y_edges[row])
                for row, col, row_span, col_span in spans
            ])
        else:
            run = max(hi - lo for lo, hi in zip(edges, edges[1:]))
    if run <= 0 or height <= 0:
        return 0.0
    limit = min(height, box.z - base_z)
    return max(0.0, min(BOTTOM_SLOPE_MAX,
                        math.degrees(math.atan(limit / run)) - 1e-6))


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
    "divider", title="Dividers", display="Dividers — split the bin",
    description="Interior walls that split the bin into compartments.",
    capabilities=("qty", "along"),
    options=(
        OptionDefinition("Width", "thickness", "1.6", minimum=MIN_WEDGE_EDGE, note="mm thickness of each divider wall; must fit inside the bin"),
        OptionDefinition("Walls", "wall_style", "straight", "enum", choices=(("straight", "Straight"), ("wavy", "Wavy"))),
        OptionDefinition("Height", "height", "", minimum=0.1, note="mm; blank = full interior height"),
        OptionDefinition("Spacing", "spacing", "", minimum=0.1, note="mm between dividers; blank = even split of the count"),
        OptionDefinition("Degree °", "bottom_angle", "0", minimum=-BOTTOM_SLOPE_MAX, maximum=BOTTOM_SLOPE_MAX, note="degrees of bottom slope either way; any non-zero value gives the divider a sloped bottom"),
        OptionDefinition("Number of crossbars", "bottom_supports", "3", "integer", minimum=1, note="whole number of bottom crossbars"),
        OptionDefinition("X quantity", "count_x", 0, "integer", False, minimum=0, note="dividers running across X; 0 = none"),
        OptionDefinition("Y quantity", "count_y", 0, "integer", False, minimum=0, note="dividers running across Y; 0 = none"),
        OptionDefinition("Wall angle", "angle", 0, "number", False, legacy=True, minimum=-MAX_DIVIDER_ANGLE, maximum=MAX_DIVIDER_ANGLE, note="the current Designer only builds upright grid dividers; leaning walls are not a current control"),
        OptionDefinition("Use sloped base", "slope_base", False, "boolean", False, note="older checkbox: true with bottom_angle 0 means the default 20 degree slope; prefer setting bottom_angle"),
        OptionDefinition("Reverse bottom", "reverse_bottom", False, "boolean", False, legacy=True, note="the current Designer reverses slope direction with a negative bottom_angle instead; not a current control"),
        OptionDefinition("Alternate bottom", "alternate_bottom", False, "boolean", False, note="true alternates the slope direction between neighbouring compartments"),
        OptionDefinition("Minimal bottom", "minimal_bottom", False, "boolean", False, note="true keeps only the supports the slope needs"),
        OptionDefinition("Label divisions", "label_divisions", False, "boolean", False, note="true adds a label to each compartment (see division_labels, division_level, division_side)"),
        OptionDefinition("Division level", "division_level", "base", "enum", False, choices=(("base", "Base"), ("rim", "Rim")), note="where division labels sit"),
        OptionDefinition("Division side", "division_side", "back", "enum", False, choices=SIDE_CHOICES, note="rim side that carries division labels (division_level = rim)"),
        OptionDefinition("Division labels", "division_labels", (), "json", False, note="list of label texts, one per compartment, when label_divisions is true"),
        OptionDefinition("Compartment spans", "compartment_spans", (), "json", False, note="optional list describing merged compartments; leave empty unless merging"),
        OptionDefinition("Compartment Scoop", "scoop", {}, "json", False, note="optional object {enabled, ...} adding a scoop to every compartment; leave empty for none"),
    ), order=60,
)
def build_divider(
    box: BoxSpec,
    spec_feature: Feature,
    base_z: float,
    *,
    full_span_cavity: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """One or more evenly spaced parallel walls subdividing the bin."""
    spec_feature = normalize_divider_scoop(box, spec_feature, base_z)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    wall_style = str(options.get("wall_style", "straight"))
    if wall_style not in {"straight", "wavy"}:
        raise ValueError("divider walls must be straight or wavy")
    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        solids = _build_divider_grid(
            box, spec_feature, base_z, options, grid_x, grid_y,
            full_span_cavity=full_span_cavity,
        )
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
        needed_gap = ((wall_depth_for(thickness) + 2.0 * WAVE_AMPLITUDE)
                      if wall_style == "wavy" else thickness) + 2.0 * abs(lean)
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
        if one.full_span and (angle != 0.0 or wall_style == "wavy"):
            solids.extend(_full_span_leaning_divider(
                box, one, thickness, height, angle, base_z,
                full_span_cavity=full_span_cavity,
            ))
        elif one.full_span:
            solids.extend(_full_span_divider(
                box, along, cross_centre, thickness, base_z, height,
                full_span_cavity=full_span_cavity,
            ))
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
    *,
    full_span_cavity: Polygon | None = None,
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
    custom_spans = normalized_compartment_spans(
        options.get("compartment_spans"), grid_y + 1, grid_x + 1,
    )
    if custom_spans:
        return _build_custom_divider_grid(
            box, spec_feature, base_z, options, grid_x, grid_y,
            thickness, height, angle,
            full_span_cavity=full_span_cavity,
        )
    full_span = spec_feature.full_span
    solids: list[trimesh.Trimesh] = []
    # Walls that divide X run along Y; walls that divide Y run along X.
    for centre in _even_centres(zone.x0, zone.x1, grid_x):
        solids.extend(_one_grid_wall(
            box, spec_feature, "y", centre, thickness, height, angle, base_z, full_span,
            full_span_cavity=full_span_cavity,
        ))
    for centre in _even_centres(zone.y0, zone.y1, grid_y):
        solids.extend(_one_grid_wall(
            box, spec_feature, "x", centre, thickness, height, angle, base_z, full_span,
            full_span_cavity=full_span_cavity,
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


def _wall_runs(present: list[bool]) -> list[tuple[int, int]]:
    """Return start/end edge indexes for contiguous surviving segments."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, survives in enumerate([*present, False]):
        if survives and start is None:
            start = index
        elif not survives and start is not None:
            runs.append((start, index))
            start = None
    return runs


def _clip_wall_to_runs(
    walls: list[trimesh.Trimesh], along: str,
    runs: list[tuple[float, float, float, float]],
    outer_bounds: tuple[float, float], base_z: float, height: float,
) -> list[trimesh.Trimesh]:
    """Clip a complete wall, letting joined endpoints follow crossing lean."""
    pieces: list[trimesh.Trimesh] = []
    for wall in walls:
        bounds = wall.bounds
        run_axis = 0 if along == "x" else 1
        cross_axis = 1 if along == "x" else 0
        cross_width = bounds[1][cross_axis] - bounds[0][cross_axis] + 1.0
        cross_centre = (bounds[0][cross_axis] + bounds[1][cross_axis]) / 2.0
        for lo, hi, lo_shift, hi_shift in runs:
            if math.isclose(lo, outer_bounds[0]):
                lo, lo_shift = bounds[0][run_axis] - 0.5, 0.0
            if math.isclose(hi, outer_bounds[1]):
                hi, hi_shift = bounds[1][run_axis] + 0.5, 0.0
            if hi <= lo:
                continue
            z0, z1 = base_z, base_z + height
            profile = Polygon([
                (lo, z0 - 0.5), (hi, z0 - 0.5), (hi, z0),
                (hi + hi_shift, z1), (hi + hi_shift, z1 + 0.5),
                (lo + lo_shift, z1 + 0.5), (lo + lo_shift, z1), (lo, z0),
            ])
            if along == "x":
                clip = _extrude_xz_profile(profile, cross_width)
                clip.apply_translation((0.0, cross_centre, 0.0))
            else:
                clip = _extrude_yz_profile(profile, cross_width)
                clip.apply_translation((cross_centre, 0.0, 0.0))
            piece = intersection([wall.copy(), clip])
            if piece.faces.shape[0]:
                pieces.append(piece)
    return pieces


def _custom_grid_wall(
    whole: list[trimesh.Trimesh], along: str,
    runs: list[tuple[float, float, float, float]],
    outer_bounds: tuple[float, float], base_z: float, height: float,
) -> list[trimesh.Trimesh]:
    """Clip one cached complete grid wall to its surviving runs."""
    return _clip_wall_to_runs(
        whole, along, runs, outer_bounds, base_z, height,
    ) if runs else []


def _build_custom_divider_grid(
    box: BoxSpec, spec_feature: Feature, base_z: float, options: dict,
    grid_x: int, grid_y: int, thickness: float, height: float, angle: float,
    *,
    full_span_cavity: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """Build only boundaries between the saved logical rectangles."""
    cells = divider_cells(box, spec_feature, base_z)
    rows, columns = grid_y + 1, grid_x + 1
    owner = divider_owner_matrix(cells, rows, columns)
    x_edges, y_edges = divider_grid_edges(spec_feature.zone, grid_x, grid_y)
    solids: list[trimesh.Trimesh] = []
    vertical_present = {
        line: [owner[row][line - 1] != owner[row][line] for row in range(rows)]
        for line in range(1, columns)
    }
    horizontal_present = {
        line: [
            owner[line - 1][column] != owner[line][column]
            for column in range(columns)
        ]
        for line in range(1, rows)
    }
    vertical_walls = {
        line: _one_grid_wall(
            box, spec_feature, "y", x_edges[line], thickness, height, angle,
            base_z, spec_feature.full_span,
            full_span_cavity=full_span_cavity,
        )
        for line in range(1, columns)
        if any(vertical_present[line])
    }
    horizontal_walls = {
        line: _one_grid_wall(
            box, spec_feature, "x", y_edges[line], thickness, height, angle,
            base_z, spec_feature.full_span,
            full_span_cavity=full_span_cavity,
        )
        for line in range(1, rows)
        if any(horizontal_present[line])
    }
    lean = height * math.tan(math.radians(angle)) if angle else 0.0

    def horizontal_touches(row_line: int, column_line: int) -> bool:
        present = horizontal_present[row_line]
        return present[column_line - 1] or present[column_line]

    def vertical_touches(column_line: int, row_line: int) -> bool:
        present = vertical_present[column_line]
        return present[row_line - 1] or present[row_line]

    for line in range(1, columns):
        runs = [
            (
                y_edges[start], y_edges[end],
                lean if start > 0 and horizontal_touches(start, line) else 0.0,
                lean if end < rows and horizontal_touches(end, line) else 0.0,
            )
            for start, end in _wall_runs(vertical_present[line])
        ]
        if runs:
            solids.extend(_custom_grid_wall(
                vertical_walls[line], "y", runs,
                (spec_feature.zone.y0, spec_feature.zone.y1), base_z, height,
            ))
    for line in range(1, rows):
        runs = [
            (
                x_edges[start], x_edges[end],
                lean if start > 0 and vertical_touches(start, line) else 0.0,
                lean if end < columns and vertical_touches(end, line) else 0.0,
            )
            for start, end in _wall_runs(horizontal_present[line])
        ]
        if runs:
            solids.extend(_custom_grid_wall(
                horizontal_walls[line], "x", runs,
                (spec_feature.zone.x0, spec_feature.zone.x1), base_z, height,
            ))

    solids.extend(_custom_divider_sloped_bottoms(
        box, spec_feature, options, cells, rows, columns, height, base_z,
    ))
    for _label, text_solid, raised in divider_division_texts(
        box, spec_feature, base_z,
    ):
        if raised:
            solids.append(text_solid)
    return solids


def _one_grid_wall(
    box: BoxSpec, spec_feature: Feature, along: str, centre: float,
    thickness: float, height: float, angle: float, base_z: float, full_span: bool,
    *,
    full_span_cavity: Polygon | None = None,
) -> list[trimesh.Trimesh]:
    """One wall of a grid divider, centred on ``centre`` of its cross axis."""
    if full_span and angle == 0.0 and spec_feature.options.get("wall_style") != "wavy":
        return _full_span_divider(
            box, along, centre, thickness, base_z, height,
            full_span_cavity=full_span_cavity,
        )
    zone = spec_feature.zone
    half_t = thickness / 2.0
    if along == "y":
        wall_zone = Zone(centre - half_t, zone.y0, centre + half_t, zone.y1)
    else:
        wall_zone = Zone(zone.x0, centre - half_t, zone.x1, centre + half_t)
    one = replace(spec_feature, zone=wall_zone, along=along)
    if full_span and (angle != 0.0 or spec_feature.options.get("wall_style") == "wavy"):
        return _full_span_leaning_divider(
            box, one, thickness, height, angle, base_z,
            full_span_cavity=full_span_cavity,
        )
    return _divider_wall(box, one, thickness, height, angle, base_z)
