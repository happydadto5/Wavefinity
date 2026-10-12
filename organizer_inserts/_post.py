"""Post feature defaults and geometry."""

from __future__ import annotations

import math

import trimesh

from organizer_engine import BoxSpec

from ._core import MAX_DIVIDER_COUNT, Feature, _fit_count
from ._registry import (
    OptionDefinition, SettingInteraction, defaults, feature,
    register_setting_interactions, resolved_options,
)


#: Maximum total number of posts (X × Y) per post feature. Each post is a
#: 48-section ``trimesh.creation.revolve`` mesh. 10,000 is the explicit
#: contract value under Andrew's product authority (Fix 1044, FINAL decision
#: 2026-10-12 — benchmark gate withdrawn). The Breaker's ~300k-op hang is
#: recorded as the demonstrated failure point that motivated this cap.
MAX_POST_COUNT = 10000
#: Cumulative Post geometry budget per layout/request (Fix 1044, "Response to
#: GPT HOLD (G2M-0278)", Andrew's FINAL decision 2026-10-12): the sum of
#: effective final post counts (``count_x × count_y`` per Post feature,
#: resolved via ``post_effective_counts`` across the manual, legacy, and auto
#: paths, with no geometry built) across ALL Post features in the layout must
#: not exceed this. Andrew's product decision: it matches the per-feature cap
#: so the two rules are coherent (a single 100×100 = 10,000-post feature is
#: already blessed). Only Andrew can change it.
MAX_CUMULATIVE_POST_COUNT = 10000
#: Maximum Post-feature count per layout/request (Fix 1044, Andrew's FINAL
#: decision 2026-10-12): caps the Post fragmentation dimension — under the
#: 10,000 cumulative post budget an adversarial request could otherwise spend
#: the budget as up to 10,000 one-post features, magnifying fixed per-feature
#: work (the preview route builds build_features(box, [one]) once per feature).
#: 150 is Andrew's product decision (the app freezes with too many items).
#: Post-specific: counts only features with kind == "post"; other feature types
#: are unaffected. Enforced in check_layout (Change 13) before any geometry.
#: Only Andrew can change it.
MAX_POST_FEATURE_COUNT = 150


@defaults("post")
def post_defaults(box: BoxSpec, one: Feature, base_z: float) -> dict[str, float]:
    return {"diameter": 12.0, "height": 16.0, "spacing": 4.0, "taper": 0.4}


def post_grid_counts(options: dict) -> tuple[int | None, int | None]:
    """Return manual X/Y post quantities, ``None`` per axis when unset.

    Mirrors ``organizer_inserts._divider_cells.divider_grid_counts``
    (Fix 1041): each set axis is capped at ``MAX_DIVIDER_COUNT`` and, when
    both axes are set, their product is capped at ``MAX_POST_COUNT`` so a
    client cannot request tens of thousands of revolve operations via a
    large two-axis combination (e.g. 200 × 200 = 40,000) that still fits the
    zone (Fix 1044, G2M-0269). Lenient for non-numeric junk (treated as 0,
    same as dividers); strict for non-finite and huge integers that would
    otherwise escape as HTTP 500.
    """
    def one(value: object, name: str) -> int | None:
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0
        except OverflowError:
            raise ValueError(f"{name} must be a valid number")
        if not math.isfinite(number):
            raise ValueError(f"{name} must be a valid number")
        parsed = max(0, int(round(number)))
        if parsed > MAX_DIVIDER_COUNT:
            raise ValueError(f"{name} must be at most {MAX_DIVIDER_COUNT}")
        return parsed
    count_x, count_y = one(options.get("count_x"), "X quantity"), one(options.get("count_y"), "Y quantity")
    if count_x is not None and count_y is not None and count_x * count_y > MAX_POST_COUNT:
        raise ValueError(f"Total posts (X × Y) must be at most {MAX_POST_COUNT}")
    return count_x, count_y


def post_effective_counts(box: BoxSpec, one: Feature, base_z: float) -> tuple[int, int]:
    """Effective final ``(count_x, count_y)`` for a Post feature, without building geometry.

    Single source of truth for Post counts (Fix 1044, G2M-0278): ``build_post``
    resolves its counts through this helper (Change 12), and the cumulative
    budget pre-pass (:func:`check_post_geometry_budget`) sums through it, so
    the budget can never diverge from what the builder will build. Covers the
    three paths: manual (``post_grid_counts`` over the resolved options, which
    enforces the per-axis and per-feature total caps), legacy
    (``Feature.count``/``along``, already capped at ``MAX_DIVIDER_COUNT`` by
    ``Feature.__post_init__``, Change 1), auto (zone fit from the resolved
    diameter/spacing). Anything unresolvable raises ``ValueError`` —
    fail-closed; callers must let it propagate, never catch-and-continue.
    Dimension validation is intentionally NOT duplicated here: it can only
    ever raise, never change a count, so there is no input where this helper
    undercounts what the builder builds.
    """
    options = resolved_options(box, one, base_z)
    raw_cx = options.get("count_x")
    raw_cy = options.get("count_y")
    if raw_cx not in (None, "") or raw_cy not in (None, ""):
        manual_x, manual_y = post_grid_counts(options)
        count_x = manual_x if manual_x is not None else 1
        count_y = manual_y if manual_y is not None else 1
    elif one.count is not None:
        try:
            legacy_count = max(1, int(round(one.count)))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("feature count must be a valid number") from exc
        count_x = legacy_count if one.along == "x" else 1
        count_y = 1 if one.along == "x" else legacy_count
    else:
        try:
            diameter = options["diameter"]
            spacing = options["spacing"]
            count_x = max(1, _fit_count(one.zone.width, diameter + spacing, diameter))
            count_y = max(1, _fit_count(one.zone.depth, diameter + spacing, diameter))
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise ValueError("post diameter and spacing must be valid numbers") from exc
    return count_x, count_y


def check_post_geometry_budget(box: BoxSpec, features: list[Feature], base_z: float) -> None:
    """Enforce the cumulative Post geometry budget for one layout/request.

    Sums effective counts via :func:`post_effective_counts` across every Post
    feature and refuses the layout before any Post geometry is built if the
    total exceeds ``MAX_CUMULATIVE_POST_COUNT`` (Fix 1044, G2M-0278).
    Fail-closed: computation errors propagate and are never treated as zero.
    """
    total = 0
    for one in features:
        if one.kind != "post":
            continue
        count_x, count_y = post_effective_counts(box, one, base_z)
        total += count_x * count_y
        if total > MAX_CUMULATIVE_POST_COUNT:
            raise ValueError(
                "Total posts across all Post features must be at most "
                f"{MAX_CUMULATIVE_POST_COUNT}"
            )


@feature(
    "post", title="Post", display="Center post — rolls and rings",
    description="A peg for tape rolls, spools, sockets and rings; add taper to hold contents snugly.",
    capabilities=("qty", "along"),
    options=(
        OptionDefinition("Height", "height", "16", minimum=0.1, note="mm; must fit inside the bin above the base"),
        OptionDefinition("Diameter", "diameter", "12", minimum=0.1, note="mm at the base; must fit the zone"),
        OptionDefinition("Taper", "taper", "0.4", minimum=0.0, note="mm the peg narrows over its height; must be smaller than the diameter"),
        OptionDefinition("Spacing", "spacing", "4", minimum=0.0, note="mm between neighbouring posts"),
        OptionDefinition("X quantity", "count_x", "", "integer", False, minimum=0, maximum=MAX_DIVIDER_COUNT, note="posts across X; 0 = none"),
        OptionDefinition("Y quantity", "count_y", "", "integer", False, minimum=0, maximum=MAX_DIVIDER_COUNT, note="posts across Y; 0 = none"),
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

    # Single source of truth for counts (Fix 1044, G2M-0278): the cumulative
    # budget pre-pass in check_layout resolves through this same helper, so
    # the budget can never diverge from what is built here. The per-feature
    # parsing (Change 5, via post_grid_counts) and the per-feature total guard
    # (Change 5b, below, unchanged) are preserved: the helper calls
    # post_grid_counts for the manual path, and the 5b guard still covers
    # legacy/auto.
    count_x, count_y = post_effective_counts(box, spec_feature, base_z)

    # Total-cap guard: reject an unsafe two-axis combination before any
    # geometry is built. Placed here (not only in post_grid_counts) so the
    # legacy-count and auto-fit paths are covered too (G2M-0269).
    if count_x * count_y > MAX_POST_COUNT:
        raise ValueError(f"Total posts (X × Y) must be at most {MAX_POST_COUNT}")
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
    from ._walljoin import (
        _join_tabs, _tab_meshes, _footprint_from_solids, _joined_sides,
    )
    from ._bore._consts import JOIN_BAND, WALL_JOIN_FLAG
    from shapely.geometry import Polygon
    if spec_feature.options.get(WALL_JOIN_FLAG):
        # Fuse the posts into any side wall they reach.
        # Keep-clear: empty (posts are solid).
        _wj_material = _footprint_from_solids(posts)
        _wj_keep_clear = Polygon()  # empty
        _wj_tabs = _join_tabs(
            box, _wj_material, _wj_keep_clear, JOIN_BAND,
            sides=_joined_sides(box, _wj_material, "post",
                                spec_feature.along),
        )
        posts.extend(_tab_meshes(_wj_tabs, height, base_z))
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
