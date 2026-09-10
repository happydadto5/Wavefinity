"""Divider-owned logical compartment calculation and target persistence."""

from __future__ import annotations

from dataclasses import dataclass, replace

from organizer_engine import BoxSpec

from ._core import Feature, Zone
from ._registry import resolved_options


@dataclass(frozen=True)
class DividerCell:
    row: int
    column: int
    zone: Zone

    @property
    def identity(self) -> str:
        return f"r{self.row}c{self.column}"


def divider_grid_counts(options: dict) -> tuple[int, int]:
    """Return grid wall counts; ``(0, 0)`` means legacy single-axis mode."""
    def one(value: object) -> int:
        if value in (None, ""):
            return 0
        try:
            return max(0, int(round(float(value))))
        except (TypeError, ValueError):
            return 0
    return one(options.get("count_x")), one(options.get("count_y"))


def even_centres(lo: float, hi: float, count: int) -> list[float]:
    """Return equally spaced fence-post positions inside an interval."""
    if count < 1:
        return []
    gap = (hi - lo) / (count + 1)
    return [lo + (index + 1) * gap for index in range(count)]


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
    cells: list[DividerCell] = []
    for row in range(len(y_edges) - 1):
        for column in range(len(x_edges) - 1):
            x0 = x_edges[column] + (thickness / 2.0 if column else 0.0)
            x1 = x_edges[column + 1] - (
                thickness / 2.0 if column < len(x_edges) - 2 else 0.0
            )
            y0 = y_edges[row] + (thickness / 2.0 if row else 0.0)
            y1 = y_edges[row + 1] - (
                thickness / 2.0 if row < len(y_edges) - 2 else 0.0
            )
            if x1 <= x0 or y1 <= y0:
                raise ValueError("divider walls leave no usable compartment")
            cells.append(DividerCell(row, column, Zone(x0, y0, x1, y1)))
    return tuple(cells)


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

    A curved Scoop and a sloped floor both own the compartment floor, so an
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
