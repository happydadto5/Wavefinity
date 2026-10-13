"""Divider-owned logical compartment calculation and target persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import math

from organizer_engine import BoxSpec

from ._core import MAX_DIVIDER_COUNT, Feature, Zone
from ._registry import resolved_options
from ._scoop import scoop_region, scoop_settings


@dataclass(frozen=True)
class DividerCell:
    row: int
    column: int
    zone: Zone
    row_span: int = 1
    column_span: int = 1

    @property
    def identity(self) -> str:
        return f"r{self.row}c{self.column}"

    @property
    def row_end(self) -> int:
        return self.row + self.row_span

    @property
    def column_end(self) -> int:
        return self.column + self.column_span


def divider_grid_counts(options: dict) -> tuple[int, int]:
    """Return grid wall counts; ``(0, 0)`` means legacy single-axis mode."""
    def one(value: object, name: str) -> int:
        if value in (None, ""):
            return 0
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        except OverflowError:
            # float() itself overflows for huge JSON integers (e.g. 10**400:
            # "int too large to convert to float") before math.isfinite is ever
            # consulted. OverflowError is not a ValueError subclass, so without
            # this it would escape as HTTP 500. Attack-shaped input -> reject.
            raise ValueError(f"{name} must be a valid number")
        if not math.isfinite(number):
            raise ValueError(f"{name} must be a valid number")
        parsed = max(0, int(round(number)))
        if parsed > MAX_DIVIDER_COUNT:
            raise ValueError(f"{name} must be at most {MAX_DIVIDER_COUNT}")
        return parsed
    return one(options.get("count_x"), "X count"), one(options.get("count_y"), "Y count")


def even_centres(lo: float, hi: float, count: int) -> list[float]:
    """Return equally spaced fence-post positions inside an interval."""
    if count < 1:
        return []
    gap = (hi - lo) / (count + 1)
    return [lo + (index + 1) * gap for index in range(count)]


def divider_grid_edges(
    zone: Zone, grid_x: int, grid_y: int,
) -> tuple[list[float], list[float]]:
    """Return atomic column/row edges in low-X, low-Y order."""
    return (
        [zone.x0, *even_centres(zone.x0, zone.x1, grid_x), zone.x1],
        [zone.y0, *even_centres(zone.y0, zone.y1, grid_y), zone.y1],
    )


def normalized_compartment_spans(
    raw_spans: object, rows: int, columns: int,
) -> tuple[tuple[int, int, int, int], ...]:
    """Validate saved rectangular spans and return deterministic tuples."""
    if raw_spans in (None, ""):
        return ()
    if isinstance(raw_spans, str):
        try:
            raw_spans = json.loads(raw_spans)
        except Exception as exc:
            raise ValueError("divider compartment_spans must be valid JSON") from exc
    if not isinstance(raw_spans, (list, tuple)):
        raise ValueError("divider compartment_spans must be a list")

    spans: list[tuple[int, int, int, int]] = []
    claimed: set[tuple[int, int]] = set()
    keys = ("row", "column", "row_span", "column_span")
    for raw in raw_spans:
        if not isinstance(raw, dict):
            raise ValueError("each divider compartment span must be an object")
        values = tuple(raw.get(key) for key in keys)
        if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
            raise ValueError("divider compartment span values must be whole numbers")
        row, column, row_span, column_span = values
        if row < 0 or column < 0 or row_span < 1 or column_span < 1:
            raise ValueError("divider compartment spans must use positive sizes")
        if row + row_span > rows or column + column_span > columns:
            raise ValueError("divider compartment span falls outside the grid")
        if row_span == 1 and column_span == 1:
            continue
        cells = {
            (one_row, one_column)
            for one_row in range(row, row + row_span)
            for one_column in range(column, column + column_span)
        }
        if claimed.intersection(cells):
            raise ValueError("divider compartment spans must not overlap")
        claimed.update(cells)
        spans.append((row, column, row_span, column_span))
    return tuple(sorted(spans))


def divider_owner_matrix(
    cells: tuple[DividerCell, ...], rows: int, columns: int,
) -> list[list[DividerCell]]:
    """Map every original atomic cell to its logical rectangle."""
    owner: list[list[DividerCell | None]] = [
        [None for _column in range(columns)] for _row in range(rows)
    ]
    for cell in cells:
        for row in range(cell.row, cell.row_end):
            for column in range(cell.column, cell.column_end):
                if owner[row][column] is not None:
                    raise ValueError("divider logical compartments overlap")
                owner[row][column] = cell
    if any(item is None for row in owner for item in row):
        raise ValueError("divider logical compartments do not cover the grid")
    return owner  # type: ignore[return-value]


def divider_cross_centres(
    zone: Zone, along: str, count: int, spacing: float
) -> list[float]:
    """Return legacy single-axis wall positions from the low edge."""
    low = zone.y0 if along == "x" else zone.x0
    return [low + (index + 1) * spacing for index in range(count)]


def divider_cells(
    box: BoxSpec, spec_feature: Feature, base_z: float = 0.0
) -> tuple[DividerCell, ...]:
    """Return Divider-owned compartments in front-to-back row-major order."""
    if spec_feature.kind != "divider":
        raise ValueError("divider cells require a divider feature")
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    thickness = float(options["thickness"])
    if thickness <= 0.0:
        raise ValueError("divider thickness must be positive")
    grid_x, grid_y = divider_grid_counts(options)
    if grid_x or grid_y:
        x_centres = even_centres(zone.x0, zone.x1, grid_x)
        y_centres = even_centres(zone.y0, zone.y1, grid_y)
    else:
        count = spec_feature.count or 1
        spacing = float(options["spacing"])
        centres = divider_cross_centres(
            zone, spec_feature.along, count, spacing
        )
        x_centres = centres if spec_feature.along == "y" else []
        y_centres = centres if spec_feature.along == "x" else []

    x_edges = [zone.x0, *x_centres, zone.x1]
    y_edges = [zone.y0, *y_centres, zone.y1]
    rows = len(y_edges) - 1
    columns = len(x_edges) - 1
    spans = normalized_compartment_spans(
        options.get("compartment_spans"), rows, columns,
    )
    claimed = {
        (one_row, one_column)
        for row, column, row_span, column_span in spans
        for one_row in range(row, row + row_span)
        for one_column in range(column, column + column_span)
    }
    rectangles = [*spans, *(
        (row, column, 1, 1)
        for row in range(rows)
        for column in range(columns)
        if (row, column) not in claimed
    )]
    cells: list[DividerCell] = []
    for row, column, row_span, column_span in sorted(rectangles):
        row_end = row + row_span
        column_end = column + column_span
        x0 = x_edges[column] + (thickness / 2.0 if column else 0.0)
        x1 = x_edges[column_end] - (thickness / 2.0 if column_end < columns else 0.0)
        y0 = y_edges[row] + (thickness / 2.0 if row else 0.0)
        y1 = y_edges[row_end] - (thickness / 2.0 if row_end < rows else 0.0)
        if x1 <= x0 or y1 <= y0:
            raise ValueError("divider walls leave no usable compartment")
        cells.append(DividerCell(
            row, column, Zone(x0, y0, x1, y1), row_span, column_span,
        ))
    return tuple(sorted(cells, key=lambda cell: (cell.row, cell.column)))


# Fix 1143: the Divider Scoop side picker. The scoop curves up from one
# compartment side - front (the historical default), back, left, right -
# or from all four sides at once ("all"), curving all the way around.
DIVIDER_SCOOP_SIDES = ("front", "back", "left", "right", "all")

# Fix 1143 round 2 (G2M-0470 HOLD): the base-division-label safe region is
# derived from the ACTUAL per-axis Scoop run - never a hardcoded half of the
# compartment.
DIVIDER_SCOOP_LABEL_CLEARANCE = 1.5  # mm kept clear between a scoop strip and the label rect
DIVIDER_SCOOP_MIN_LABEL_W = 4.0  # mm; a narrower remaining rect counts as collapsed
DIVIDER_SCOOP_MIN_LABEL_H = 3.0  # mm; a shorter remaining rect counts as collapsed
# The 4.0/3.0 collapse thresholds sit just above the label pipeline's 2.5 mm
# minimum glyph cap (cap = max(2.5, ...) in _shelf.py), so a collapsed rect
# could never hold legible text anyway.


def divider_scoop_side(config) -> str:
    """The compartment side carrying the Divider Scoop; 'front' unless chosen."""
    side = config.get("side", "front") if isinstance(config, dict) else "front"
    return side if side in DIVIDER_SCOOP_SIDES else "front"


def divider_scoop_run_lengths(zone, settings):
    """Actual per-axis Scoop strip run inside one compartment, in mm.

    Derived from the real Scoop geometry: runs scoop_region() - the same
    function the geometry pass builds the scoop solids from - on each axis
    and measures the strip it returns (run = min(settings.height, dim/2),
    capped by scoop_region itself). Returns (run_x, run_y). A regression
    proves these runs match the real built solids' measured extents within
    1e-6 mm, so the label region below is never a hardcoded half.
    """
    strip_x = scoop_region(zone, settings, "y")
    strip_y = scoop_region(zone, settings, "x")
    return (strip_x.x1 - strip_x.x0, strip_y.y1 - strip_y.y0)


def divider_scoop_label_rect(zone, settings, side):
    """Safe base-division-label rect for one compartment.

    Derived from the actual Scoop run (divider_scoop_run_lengths), not a
    hardcoded half: the rect is the compartment zone minus the scoop
    strip(s) for ``side``, shrunk by DIVIDER_SCOOP_LABEL_CLEARANCE on every
    side. The clearance also absorbs the <= thickness/2 wall-inset difference
    between slot bounds and cell zones in the non-grid label path, so the
    label can never touch a scoop strip there either.

    Returns (x0, y0, x1, y1, collapsed). ``collapsed`` is True when the
    remaining rect is narrower than DIVIDER_SCOOP_MIN_LABEL_W or shorter
    than DIVIDER_SCOOP_MIN_LABEL_H - including the zero-area max-run "all"
    case, where opposing strips meet at the compartment midlines. Callers
    must suppress the label when collapsed, never emit overlapping text.
    Unknown sides behave as "front".
    """
    run_x, run_y = divider_scoop_run_lengths(zone, settings)
    x0, y0, x1, y1 = zone.x0, zone.y0, zone.x1, zone.y1
    if side == "back":
        y1 -= run_y
    elif side == "left":
        x0 += run_x
    elif side == "right":
        x1 -= run_x
    elif side == "all":
        x0 += run_x
        y0 += run_y
        x1 -= run_x
        y1 -= run_y
    else:  # "front", and any unknown value
        y0 += run_y
    c = DIVIDER_SCOOP_LABEL_CLEARANCE
    rx0, ry0, rx1, ry1 = x0 + c, y0 + c, x1 - c, y1 - c
    collapsed = (
        (rx1 - rx0) < DIVIDER_SCOOP_MIN_LABEL_W
        or (ry1 - ry0) < DIVIDER_SCOOP_MIN_LABEL_H
    )
    return (rx0, ry0, rx1, ry1, collapsed)


def divider_scoop_label_placement(box, zone, config, base_z):
    """((x0, y0, x1, y1), collapsed) for one compartment's base label.

    Resolves the real scoop settings exactly as the geometry pass does
    (scoop_settings(..., allow_legacy_height=False)) and derives the safe
    rect from the actual per-axis Scoop run.
    """
    settings = scoop_settings(box, config, base_z, allow_legacy_height=False)
    x0, y0, x1, y1, collapsed = divider_scoop_label_rect(
        zone, settings, divider_scoop_side(config)
    )
    return ((x0, y0, x1, y1), collapsed)


def divider_scoop_targets(
    box: BoxSpec, spec_feature: Feature, base_z: float = 0.0
) -> tuple[str, ...]:
    """Return every Divider cell when its shared Scoop is enabled."""
    config = spec_feature.options.get("scoop")
    if not isinstance(config, dict):
        return ()
    return tuple(cell.identity for cell in divider_cells(box, spec_feature, base_z))


def normalize_divider_scoop(
    box: BoxSpec, spec_feature: Feature, base_z: float = 0.0
) -> Feature:
    """Normalize Scoop targeting and retire incompatible sloped bottoms.

    A Scoop and a sloped floor both own the compartment floor, so an
    old design containing both resolves in favour of its Scoop.
    """
    config = spec_feature.options.get("scoop")
    options = dict(spec_feature.options)
    if not isinstance(config, dict):
        return (
            replace(spec_feature, options=options)
            if options != spec_feature.options else spec_feature
        )
    normalized = dict(config)
    normalized.pop("cells", None)
    # Fix 1143: the scoop side picker. Unknown values fall back to the
    # historical front default at build time; drop them so saved designs
    # stay clean.
    if normalized.get("side") not in DIVIDER_SCOOP_SIDES:
        normalized.pop("side", None)
    options["scoop"] = normalized
    for key in (
        "slope_base", "bottom_angle", "reverse_bottom", "alternate_bottom",
        "minimal_bottom", "bottom_supports",
    ):
        options.pop(key, None)
    return replace(spec_feature, options=options)


# Compatibility aliases used by older imports and Divider's geometry module.
_even_centres = even_centres
_divider_cross_centres = divider_cross_centres
