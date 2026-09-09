"""Reusable Easy Clean settings and floor-to-wall profile mathematics."""

from __future__ import annotations

from dataclasses import dataclass
import math


EASY_CLEAN_RADIUS = 2.0
EASY_CLEAN_STYLES = ("bevel", "curve")


@dataclass(frozen=True)
class EasyCleanSettings:
    radius: float = EASY_CLEAN_RADIUS
    style: str = "bevel"

    def __post_init__(self) -> None:
        if not math.isfinite(self.radius) or self.radius <= 0.0:
            raise ValueError("easy clean radius must be positive")
        if self.style not in EASY_CLEAN_STYLES:
            raise ValueError("easy clean style must be 'bevel' or 'curve'")


def easy_clean_settings(style: object, radius: object) -> EasyCleanSettings:
    """Normalize one container's stored Easy Clean values."""
    return EasyCleanSettings(float(radius), str(style))


def easy_clean_profile(
    floor_z: float,
    settings: EasyCleanSettings,
    wall_embed: float,
    *,
    curve_steps: int = 16,
) -> list[tuple[float, float]]:
    """Material profile for any exposed straight floor-to-wall joint.

    Containers supply the floor height and enough inward wall embed to cover
    their own wall variation. The radius/style math is container-independent.
    """
    if not math.isfinite(floor_z):
        raise ValueError("easy clean floor height must be finite")
    if not math.isfinite(wall_embed) or wall_embed <= 0.0:
        raise ValueError("easy clean wall embed must be positive")
    if curve_steps < 1:
        raise ValueError("easy clean curve needs at least one step")
    radius = settings.radius
    centre_z = floor_z + radius
    points = [(-wall_embed, floor_z), (-wall_embed, centre_z), (0.0, centre_z)]
    if settings.style == "bevel":
        points.append((radius, floor_z))
        return points
    for index in range(1, curve_steps + 1):
        angle = math.pi + (math.pi / 2.0) * index / curve_steps
        points.append((
            radius + radius * math.cos(angle),
            centre_z + radius * math.sin(angle),
        ))
    return points
