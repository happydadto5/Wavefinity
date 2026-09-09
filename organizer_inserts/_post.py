"""Post feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh

from organizer_engine import BoxSpec

from ._core import Feature, _fit_count
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)


@defaults("post")
def post_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {"diameter": 12.0, "height": 16.0, "spacing": 4.0, "taper": 0.4}


@feature(
    "post", title="Post", display="Center post — rolls and rings",
    description="A tapered peg for tape rolls, spools, sockets and rings.",
    capabilities=("qty", "along"),
    options=(
        OptionDefinition("Height", "height", "16"),
        OptionDefinition("Diameter", "diameter", "12"),
        OptionDefinition("Taper", "taper", "0.4"),
        OptionDefinition("Spacing", "spacing", "4"),
        OptionDefinition("X quantity", "count_x", "", "integer", False),
        OptionDefinition("Y quantity", "count_y", "", "integer", False),
    ), order=40,
)
def build_post(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """Lightly tapered pegs for rolls, spools, rings and sockets arranged in X and Y."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    diameter = options["diameter"]
    height = options["height"]
    spacing = options["spacing"]
    taper = options["taper"]
    if (
        not all(math.isfinite(value) for value in (diameter, height, spacing, taper))
        or diameter <= 0.0
        or height <= 0.0
        or spacing < 0.0
        or taper < 0.0
        or taper >= diameter
    ):
        raise ValueError(
            "post diameter and height must be positive; spacing and taper must "
            "be non-negative, with taper smaller than the diameter"
        )

    raw_cx = options.get("count_x")
    raw_cy = options.get("count_y")
    if raw_cx is not None or raw_cy is not None:
        count_x = max(1, int(round(float(raw_cx)))) if raw_cx is not None else 1
        count_y = max(1, int(round(float(raw_cy)))) if raw_cy is not None else 1
    elif spec_feature.count is not None:
        legacy_count = max(1, int(round(spec_feature.count)))
        count_x = legacy_count if spec_feature.along == "x" else 1
        count_y = 1 if spec_feature.along == "x" else legacy_count
    else:
        count_x = max(1, _fit_count(zone.width, diameter + spacing, diameter))
        count_y = max(1, _fit_count(zone.depth, diameter + spacing, diameter))

    used_x = count_x * diameter + (count_x - 1) * spacing
    used_y = count_y * diameter + (count_y - 1) * spacing
    if used_x > zone.width + 1e-9 or used_y > zone.depth + 1e-9:
        raise ValueError(
            f"{count_x}x{count_y} posts need {used_x:.1f} x {used_y:.1f} mm but the zone "
            f"gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )

    centre_x, centre_y = zone.centre
    first_x = -(count_x - 1) * (diameter + spacing) / 2.0
    first_y = -(count_y - 1) * (diameter + spacing) / 2.0
    posts = []
    for ix in range(count_x):
        offset_x = first_x + ix * (diameter + spacing)
        for iy in range(count_y):
            offset_y = first_y + iy * (diameter + spacing)
            post = trimesh.creation.revolve(
                [
                    (0.0, 0.0),
                    (diameter / 2.0, 0.0),
                    ((diameter - taper) / 2.0, height),
                    (0.0, height),
                ],
                sections=48,
            )
            post.apply_translation((centre_x + offset_x, centre_y + offset_y, base_z))
            posts.append(post)
    return posts


register_setting_interactions("post", (
    SettingInteraction("count", "zone.run", "auto-adjust", "post-sizing",
                       "Quantity grows the Post row on its run axis."),
    SettingInteraction("diameter", "zone", "auto-adjust", "post-sizing",
                       "Post diameter grows the footprint needed by each peg."),
    SettingInteraction("spacing", "zone.run", "auto-adjust", "post-sizing",
                       "Spacing grows the row without shrinking a manual Base size."),
    SettingInteraction("along", "zone", "auto-adjust", "post-sizing",
                       "Changing orientation swaps which footprint axis the row uses."),
))
