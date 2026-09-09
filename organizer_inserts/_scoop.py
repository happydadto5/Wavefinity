"""Scoop feature defaults, layout zone, and geometry."""

from __future__ import annotations

from dataclasses import dataclass
import math

import trimesh

from organizer_engine import (
    BoxSpec,
    SCOOP_HEIGHT_FRACTION,
    build_scoop_region,
)

from ._core import EDITOR_SNAP, Feature, Zone, layout_zone, snapped_zone
from ._registry import (
    OptionDefinition,
    SettingInteraction,
    defaults,
    feature,
    register_setting_interactions,
)


SCOOP_DEFAULT_DEPTH = SCOOP_HEIGHT_FRACTION * 100.0
SCOOP_MIN_DEPTH = 1.0
SCOOP_MAX_DEPTH = 100.0


@dataclass(frozen=True)
class ScoopSettings:
    depth: float
    height: float


def scoop_settings(
    box: BoxSpec, options: dict, base_z: float, *, allow_legacy_height: bool = True
) -> ScoopSettings:
    """Resolve and validate the shared Scoop settings for any container."""
    available = box.z - base_z
    if available <= 0.0:
        raise ValueError("scoop height must fit inside the bin")
    if "depth" in options:
        depth = float(options["depth"])
        if (
            not math.isfinite(depth)
            or depth < SCOOP_MIN_DEPTH or depth > SCOOP_MAX_DEPTH
        ):
            raise ValueError("scoop depth must be between 1 and 100 percent")
        height = available * depth / 100.0
    elif allow_legacy_height and "height" in options:
        height = float(options["height"])
        depth = height / available * 100.0
    else:
        depth = SCOOP_DEFAULT_DEPTH
        height = available * depth / 100.0
    if (
        not math.isfinite(height)
        or height <= 0.0 or base_z + height > box.z + 1e-9
    ):
        raise ValueError("scoop height must fit inside the bin")
    return ScoopSettings(depth, height)


def scoop_region(container: Zone, settings: ScoopSettings, along: str = "x") -> Zone:
    """The half-depth strip a Scoop occupies inside a container region."""
    if along not in {"x", "y"}:
        raise ValueError("scoop orientation must be 'x' or 'y'")
    if along == "x":
        run = min(settings.height, container.depth / 2.0)
        return Zone(container.x0, container.y0, container.x1, container.y0 + run)
    run = min(settings.height, container.width / 2.0)
    return Zone(container.x0, container.y0, container.x0 + run, container.y1)


def scoop_zone(
    box: BoxSpec,
    one: Feature,
    base_z: float,
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Zone:
    """The scoop is always full-width and starts at the front wall."""
    bounds = layout_zone(box, mode)
    try:
        depth_percent = float(one.options.get("depth", SCOOP_DEFAULT_DEPTH))
    except (TypeError, ValueError):
        depth_percent = SCOOP_DEFAULT_DEPTH
    height = (box.z - base_z) * depth_percent / 100.0
    run = min(max(height, snap), bounds.depth / 2.0)
    return snapped_zone(
        Zone(bounds.x0, bounds.y0, bounds.x1, bounds.y0 + run),
        box, mode, snap,
    )


@defaults("scoop")
def scoop_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {
        "depth": SCOOP_DEFAULT_DEPTH,
    }


@feature(
    "scoop", title="Curved Scoop", display="Curved Scoop — retrieval ramp",
    description="A curved retrieval ramp for easy access to small parts.",
    options=(OptionDefinition("Depth", "depth", f"{SCOOP_DEFAULT_DEPTH:g}"),),
    order=90,
)
def build_scoop(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A full-zone curved retrieval ramp rising up the wall."""
    zone = spec_feature.zone
    settings = scoop_settings(box, spec_feature.options, base_z)
    return [build_scoop_region(
        (zone.x0, zone.y0, zone.x1, zone.y1), base_z, settings.height,
        spec_feature.along,
    )]


register_setting_interactions("scoop", (
    SettingInteraction(
        "depth", "height", "derived", "scoop",
        "Depth percent determines the Scoop rise within the available bin height.",
    ),
    SettingInteraction(
        "depth", "region", "auto-adjust", "scoop",
        "Depth percent determines the floor run while the container owns placement.",
    ),
))
