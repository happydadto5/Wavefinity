"""Post feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh

from organizer_engine import BoxSpec

from ._core import Feature, _fit_count
from ._registry import defaults, feature, resolved_options


@defaults("post")
def post_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {"diameter": 12.0, "height": 16.0, "spacing": 4.0, "taper": 0.4}


@feature("post")
def build_post(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """One or more lightly tapered pegs for rolls, spools, rings and sockets."""
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

    run = zone.width if spec_feature.along == "x" else zone.depth
    across = zone.depth if spec_feature.along == "x" else zone.width
    count = (spec_feature.count if spec_feature.count is not None
             else _fit_count(run, diameter + spacing, diameter))
    used = count * diameter + (count - 1) * spacing
    if count < 1 or diameter > across + 1e-9 or used > run + 1e-9:
        raise ValueError(
            f"{count} posts need {used:.1f} x {diameter:.1f} mm but the zone "
            f"gives {run:.1f} x {across:.1f} mm"
        )

    centre_x, centre_y = zone.centre
    first = -(count - 1) * (diameter + spacing) / 2.0
    posts = []
    for index in range(count):
        offset = first + index * (diameter + spacing)
        post = trimesh.creation.revolve(
            [
                (0.0, 0.0),
                (diameter / 2.0, 0.0),
                ((diameter - taper) / 2.0, height),
                (0.0, height),
            ],
            sections=48,
        )
        post.apply_translation(
            (centre_x + offset, centre_y, base_z)
            if spec_feature.along == "x"
            else (centre_x, centre_y + offset, base_z)
        )
        posts.append(post)
    return posts
