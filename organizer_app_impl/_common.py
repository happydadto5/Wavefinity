"""Wavefinity app shared constants, label rules, validators and small helpers."""

from __future__ import annotations

from dataclasses import replace
from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    TEXT_DEPTH,
    lid_spec,
    direct_stack_enabled,
    scoop_dimensions,
    LIFT_GRABBER_RIM_CLEARANCE,
    top_label_zone,
)
from organizer_inserts import (
    BASE_PLATE,
    Feature,
    Layout,
    Zone,
    feature_definitions,
    is_text,
    text_fitted,
    text_of,
)


SURFACE_BASE_CELL_MM = BASE_UNIT
SURFACE_BASE_TOP_SKIN_MM = 1.0
SURFACE_BASE_CELL_INSET_MM = 1.0
SURFACE_BASE_MIN_OPENING_MM = 2.0
SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM = 0.05
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm

_FEATURE_DEFINITIONS = feature_definitions()
INTERIOR_PART_CATALOG = {
    definition.kind: (definition.display, definition.description)
    for definition in _FEATURE_DEFINITIONS
}
INTERIOR_PART_ORDER = tuple(
    definition.kind for definition in _FEATURE_DEFINITIONS
)
# The rim label is the one piece of lettering that is not an interior part: it
# lives on a shelf at the selected rim side, not on the floor, so it has no zone to
# drag. "bottom" now simply means there is no rim label - floor lettering is a
# text interior part.
LABEL_POSITIONS = ("bottom", "top", "front", "back", "left", "right")


def label_position(value: str) -> str:
    position = str(value).strip().lower()
    if position not in LABEL_POSITIONS:
        raise ValueError("label position must be on the base or a rim side")
    return position


def rim_label_side(value: str) -> str | None:
    position = label_position(value)
    if position == "bottom":
        return None
    return "back" if position == "top" else position


def validate_scoop_lift_grabbers(box: BoxSpec, scoop: bool) -> None:
    """A front scoop's rise and front-wall lift grabbers can occupy the same Z.

    Shared by preview and generation so they can never disagree. Side-only
    grabbers never conflict with the front scoop, so only the front wall
    ("-y") is checked. This is a real Z-axis collision, not the 2D floor
    footprint ``_customization_zones`` checks, so it has to be tested
    separately from that.
    """
    if not scoop or not box.lift_grabbers.enabled:
        return
    if "-y" not in box.lift_grabbers.walls:
        return
    scoop_top = box.base_thickness + scoop_dimensions(box)[0]
    grabber_bottom = (
        box.z - LIFT_GRABBER_RIM_CLEARANCE - box.lift_grabbers.dimensions.height
    )
    if scoop_top > grabber_bottom:
        raise ValueError(
            "the front scoop rises into the front-wall Inside Grip. Choose "
            "a smaller Inside Grip size, use side-only Inside Grip, make the bin "
            "taller, or disable the scoop"
        )


def validate_side_opening_label(box: BoxSpec, label: str, label_location: str) -> None:
    """A rim label may not occupy the same wall as a Side Opening.

    The rim label's text/side live outside ``BoxSpec`` (they are generation
    parameters, not saved box fields), so this conflict is checked here
    rather than inside ``organizer_side_openings.validate_side_openings``.
    """
    if not box.side_openings.enabled or not clean_label(label):
        return
    side = rim_label_side(label_position(label_location))
    if side is not None and side in box.side_openings.sides:
        raise ValueError(
            f"a rim label and a Side Opening cannot share the {side} wall; "
            "move the rim label to a different side or deselect that side"
        )


def validate_edge_mount_label_conflicts(box: BoxSpec, label: str, label_location: str) -> None:
    """A Separate Edge Mount label cannot share its clip space with other parts.

    Its deep inside leg (Fix 061) occupies the near-rim inside wall, so the
    combination cannot seat. Integrated labels are unaffected. Checked here
    (not in ``EdgeMountSpec``) so old saved designs still load and can be fixed.
    """
    edge = box.edge_mount
    if not (edge.label_enabled and edge.label_type == "separate"):
        return
    side = rim_label_side(label_location) if clean_label(label) else None
    edge_side = str(edge.side or "front").strip().lower()
    if side is not None and side == edge_side:
        raise ValueError(
            f"A Separate Edge Mount label and rim label cannot use the same {edge_side.title()} wall. "
            "Move the rim label, choose another Edge Mount wall, or use Integrated."
        )
    if lid_spec(box).enabled:
        raise ValueError(
            "A Separate Edge Mount label cannot be used with a lid. "
            "Use Integrated or remove the lid."
        )
    if direct_stack_enabled(box):
        raise ValueError(
            "A Separate Edge Mount label cannot be used with direct Stackable Bin because "
            "its inside clip occupies the stacking opening. Use Integrated or turn off direct stacking."
        )


# --- guided part palette ---------------------------------------------------
#
# Compatibility views for existing CLI/browser callers. Their source of truth
# is the feature-local registry populated by each feature module.
PART_KINDS = tuple(
    (
        definition.kind,
        definition.title,
        definition.description,
        definition.flags,
        tuple(
            (option.label, option.key, option.default)
            for option in definition.options if option.editor
        ),
    )
    for definition in _FEATURE_DEFINITIONS
)
PART_KIND_INFO = {
    kind: (title, blurb, flags, fields)
    for kind, title, blurb, flags, fields in PART_KINDS
}


ILLEGAL_IN_FILENAMES = r'<>:"/\|?*'


def clean_label(label: str) -> str:
    """The label with anything a filesystem would object to removed."""
    kept = "".join(
        " " if character in ILLEGAL_IN_FILENAMES else character
        for character in (label or "")
        if character.isprintable()
    )
    return " ".join(kept.split())


def base_height(box: BoxSpec, mode: str) -> float:
    """The z a holder is built up from: the bin floor, or the insert's plate."""
    return (
        box.base_thickness
        if mode == "fused"
        else box.base_thickness + BASE_PLATE
    )


def _text_fits(one: Feature) -> bool:
    try:
        text_fitted(one)
        return True
    except ValueError:
        return False


def _canonical_rim_label(
    box: BoxSpec, layout: Layout, label: str, location: str,
) -> tuple[Layout, str, str]:
    """Retire the one-label design field after importing it as a Text feature."""
    if box.b4b.enabled:
        return layout, label, location
    side = rim_label_side(label_position(location))
    if not clean_label(label) or not side:
        return layout, label, location
    if any(is_text(one) and one.options.get("level") == "rim"
           and one.options.get("rim_side", "back") == side
           and text_of(one) == clean_label(label) for one in layout.features):
        return layout, "", "bottom"
    try:
        zone = Zone(*top_label_zone(box, side).bounds)
    except ValueError:
        zone = Zone(-4.0, -4.0, 4.0, 4.0)
    feature = Feature("text", zone, options={
        "text": clean_label(label), "level": "rim", "rim_side": side,
        "raised": False, "depth": TEXT_DEPTH,
    })
    return replace(layout, features=layout.features + (feature,)), "", "bottom"
