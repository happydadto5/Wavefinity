"""Text feature defaults, placement, and geometry."""
from __future__ import annotations
import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import Polygon
from organizer_engine import BoxSpec, TEXT_CAP_HEIGHT_FLOOR, TEXT_CAP_HEIGHT_IDEAL, TEXT_DEPTH, text_outline, text_prism
from ._core import EDITOR_SNAP, Feature, Zone, layout_zone, snapped_zone
from ._registry import defaults, feature, resolved_options
TEXT_KIND = "text"
TEXT_ZONE_EPSILON = 0.01
NON_NUMERIC_OPTIONS = {"text", "font", "raised", "auto", "quarter_turns"}
#
# Lettering is an interior part like any other: it owns a zone, it is dragged,
# resized and turned in the same editor, and it keeps its neighbours out of its
# own floor.  What makes it different is only how it is assembled - a recessed
# text is subtracted from the body it sits in rather than added to it, and
# either way it stays its own object in the 3MF so a slicer can give it its own
# filament.  ``build_features`` therefore builds it (so its errors surface with
# every other feature's) but leaves it out of the additive union; the exporter
# collects it through ``build_texts``.

TEXT_KIND = "text"
TEXT_ZONE_EPSILON = 0.01     # glyph bounds land exactly on the zone; see _feature_reach

# Every other holder's options are numbers, and the browser layer converts
# them as such. Text brought the first that are not: what it says, and two
# yes/no choices. Naming them here keeps that conversion honest instead of
# letting it guess from the value it happens to receive.
NON_NUMERIC_OPTIONS = {
    "text": "string", "auto": "flag", "raised": "flag", "level": "string",
    "lift_assist": "string", "finger_position": "string",
    "push_position": "string",
    # A divider's sloped-bottom yes/no choices - kept flags so a browser or
    # API round-trip does not turn them into 0.0 / 1.0 floats.
    "reverse_bottom": "flag", "alternate_bottom": "flag", "minimal_bottom": "flag",
    "slope_base": "flag", "label_divisions": "flag", "division_level": "string",
    "division_side": "string", "division_labels": "json",
    # Browser footprint ownership: true while a contents-driven axis remains
    # automatic, false after the user sizes it. Persisted so reopening a design
    # never loses that intent.
    "auto_width": "flag", "auto_depth": "flag",
}


def option_value(key: str, value: object) -> object:
    """One option as its declared type, or a float like every other one."""
    kind = NON_NUMERIC_OPTIONS.get(key)
    if kind == "string":
        return str(value)
    if kind == "flag":
        if isinstance(value, str):
            return value.strip().lower() not in {"", "false", "0", "no", "off"}
        return bool(value)
    if kind == "json":
        if isinstance(value, str):
            import json
            try:
                return json.loads(value)
            except Exception:
                return [s.strip() for s in value.split(",") if s.strip()]
        return value
    return float(value)


def is_text(one: Feature) -> bool:
    return one.kind == TEXT_KIND


def text_of(one: Feature) -> str:
    """The lettering a text feature carries, stripped."""
    return str(one.options.get("text", "") or "").strip()


def _oriented_text(label: str, cap_height: float, quarter_turns: int):
    """``label`` at ``cap_height``, turned in 90-degree steps, centred on origin."""
    outline = text_outline(label, cap_height)
    turns = int(quarter_turns) % 4
    if turns:
        outline = affinity.rotate(outline, 90.0 * turns, origin=(0.0, 0.0),
                                  use_radians=False)
    minx, miny, maxx, maxy = outline.bounds
    return affinity.translate(outline, xoff=-(minx + maxx) / 2.0,
                              yoff=-(miny + maxy) / 2.0)


def text_fitted(one: Feature) -> tuple[float, object]:
    """``(cap height, outline centred on the origin)`` fitted into the zone.

    The zone is what the editor drags and resizes, so it is authoritative: a
    blank ``cap_height`` fills it, and a hand-set one is honoured but never
    allowed to overflow it.  That is what makes dragging a corner scale the
    lettering, exactly the way resizing any other interior part scales it.
    """
    label = text_of(one)
    if not label:
        raise ValueError("this text part has no text; type what it should say")
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    probe = _oriented_text(label, TEXT_CAP_HEIGHT_IDEAL, turns)
    bx0, by0, bx1, by1 = probe.bounds
    width, height = bx1 - bx0, by1 - by0
    if width <= 0.0 or height <= 0.0:
        raise ValueError(f"'{label}' has no printable outline")
    zone = one.zone
    fits = TEXT_CAP_HEIGHT_IDEAL * min(zone.width / width, zone.depth / height)
    if fits < TEXT_CAP_HEIGHT_FLOOR - 1e-9:
        needed_x = width * TEXT_CAP_HEIGHT_FLOOR / TEXT_CAP_HEIGHT_IDEAL
        needed_y = height * TEXT_CAP_HEIGHT_FLOOR / TEXT_CAP_HEIGHT_IDEAL
        raise ValueError(
            f"'{label}' will not fit its box: at the {TEXT_CAP_HEIGHT_FLOOR:g} mm "
            f"minimum letter height it needs {needed_x:.1f} x {needed_y:.1f} mm "
            f"and the box is {zone.width:.1f} x {zone.depth:.1f} mm. Make it "
            f"bigger, turn it, or use shorter text"
        )
    wanted = one.options.get("cap_height")
    cap = min(float(wanted), fits) if wanted else fits
    cap = max(cap, TEXT_CAP_HEIGHT_FLOOR)
    return cap, _oriented_text(label, cap, turns)


def text_placed_outline(one: Feature):
    """A text feature's real 2D ink, centred in its zone."""
    _cap, outline = text_fitted(one)
    centre_x, centre_y = one.zone.centre
    return affinity.translate(outline, xoff=centre_x, yoff=centre_y)


def text_is_raised(one: Feature) -> bool:
    return bool(one.options.get("raised", False))


def text_depth(one: Feature) -> float:
    depth = one.options.get("depth")
    return TEXT_DEPTH if depth in (None, "") else float(depth)


@defaults(TEXT_KIND)
def text_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    """Resolved numbers the editor shows in its own fields.

    ``cap_height`` reports what the zone currently produces, so the field can
    sit blank and still read ``auto (8.5)`` rather than empty.
    """
    resolved: dict[str, float] = {
        "depth": TEXT_DEPTH,
        "quarter_turns": 0,
        "raised": 0,
        "auto": 0,
    }
    if one.options.get("level") == "rim":
        return resolved
    try:
        resolved["cap_height"] = round(text_fitted(one)[0], 3)
    except ValueError:
        resolved["cap_height"] = TEXT_CAP_HEIGHT_IDEAL
    return resolved


@feature(TEXT_KIND)
def build_text(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """The lettering solid, sunk into (or standing on) the surface at ``base_z``.

    Recessed - the default - it occupies the depth immediately below the floor
    it sits in, so the exporter subtracts it and the finished floor stays flat
    with the letters as an inlay.
    """
    if spec_feature.options.get("level") == "rim":
        return []
    outline = text_placed_outline(spec_feature)
    depth = text_depth(spec_feature)
    raised = text_is_raised(spec_feature)
    if depth <= 0.0:
        raise ValueError("text depth must be positive")
    if not raised and depth > base_z + 1e-9:
        raise ValueError(
            f"sunk text {depth:g} mm deep needs {depth:g} mm of floor beneath it; "
            f"this one has {base_z:.2f} mm. Make it shallower, thicken the base, "
            f"or set it to stand proud instead"
        )
    if raised and base_z + depth > box.z + 1e-9:
        raise ValueError("raised text must stay inside the bin")
    return [text_prism(outline, base_z, depth, raised)]


def _text_footprint(box: BoxSpec, one: Feature, base_z: float) -> Zone | None:
    """The floor the lettering really covers - its ink, not its whole box.

    Text is usually a different shape from the rectangle it was dragged out to,
    so judging neighbours on the ink lets a label sit close beside a holder
    without the empty corners of its box pushing them apart.
    """
    if one.options.get("level") == "rim":
        return None
    outline = text_placed_outline(one)
    bx0, by0, bx1, by1 = outline.bounds
    if bx1 <= bx0 or by1 <= by0:
        return None
    return Zone(bx0, by0, bx1, by1)


def text_min_footprint(
    box: BoxSpec, one: Feature, base_z: float = 0.0
) -> tuple[float, float] | None:
    """The smallest ``(width, depth)`` mm needed to fit the text without squeezing."""
    label = text_of(one)
    if not label:
        return None
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    try:
        probe = _oriented_text(label, TEXT_CAP_HEIGHT_IDEAL, turns)
    except (ValueError, ZeroDivisionError):
        return None
    bx0, by0, bx1, by1 = probe.bounds
    text_w, text_h = bx1 - bx0, by1 - by0
    if text_w <= 0.0 or text_h <= 0.0:
        return None
    wanted = one.options.get("cap_height")
    target_cap = float(wanted) if wanted else TEXT_CAP_HEIGHT_IDEAL
    if turns % 2 == 0:
        cap_by_depth = TEXT_CAP_HEIGHT_IDEAL * (one.zone.depth / text_h)
        effective_cap = min(target_cap, max(TEXT_CAP_HEIGHT_FLOOR, cap_by_depth))
        needed_w = text_w * (effective_cap / TEXT_CAP_HEIGHT_IDEAL)
        needed_d = max(one.zone.depth, text_h * (effective_cap / TEXT_CAP_HEIGHT_IDEAL))
        return (math.ceil(needed_w), math.ceil(needed_d))
    else:
        cap_by_width = TEXT_CAP_HEIGHT_IDEAL * (one.zone.width / text_w)
        effective_cap = min(target_cap, max(TEXT_CAP_HEIGHT_FLOOR, cap_by_width))
        needed_w = max(one.zone.width, text_w * (effective_cap / TEXT_CAP_HEIGHT_IDEAL))
        needed_d = text_h * (effective_cap / TEXT_CAP_HEIGHT_IDEAL)
        return (math.ceil(needed_w), math.ceil(needed_d))


def auto_grow_text_feature(
    one: Feature, box: BoxSpec, mode: str = "fused"
) -> Feature:
    """Auto grow text part footprint if it needs more room and can fit inside the bin."""
    if not is_text(one):
        return one
    size = text_min_footprint(box, one)
    if size is None:
        return one
    bounds = layout_zone(box, mode)
    turns = int(one.options.get("quarter_turns", 0) or 0) % 4
    if turns % 2 == 0:
        needed_w = size[0]
        max_fit_w = bounds.width
        grow_w = min(needed_w, max_fit_w)
        if grow_w > one.zone.width:
            cx = one.zone.centre[0]
            cx = min(max(cx, bounds.x0 + grow_w / 2.0), bounds.x1 - grow_w / 2.0)
            new_zone = Zone(cx - grow_w / 2.0, one.zone.y0, cx + grow_w / 2.0, one.zone.y1)
            return replace(one, zone=snapped_zone(new_zone, box, mode))
    else:
        needed_d = size[1]
        max_fit_d = bounds.depth
        grow_d = min(needed_d, max_fit_d)
        if grow_d > one.zone.depth:
            cy = one.zone.centre[1]
            cy = min(max(cy, bounds.y0 + grow_d / 2.0), bounds.y1 - grow_d / 2.0)
            new_zone = Zone(one.zone.x0, cy - grow_d / 2.0, one.zone.x1, cy + grow_d / 2.0)
            return replace(one, zone=snapped_zone(new_zone, box, mode))
    return one
