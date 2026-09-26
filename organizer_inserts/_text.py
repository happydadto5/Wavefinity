"""Text feature defaults, placement, and geometry."""
from __future__ import annotations
import math
from dataclasses import replace
import trimesh
from shapely import affinity
from shapely.geometry import Polygon
from organizer_engine import (
    BoxSpec, TEXT_CAP_HEIGHT_FLOOR, TEXT_CAP_HEIGHT_IDEAL, TEXT_DEPTH,
    TOP_LABEL_CAP_HEIGHT, TOP_LABEL_LEDGE_DEPTH, TOP_LABEL_MARGIN,
    make_top_label_ledge, require_text_backing, text_outline, text_prism,
    top_label_surface_z, top_label_zone,
)
from ._core import EDITOR_SNAP, Feature, Zone, layout_zone, snapped_zone
from ._registry import (
    OPTION_TYPES, OptionDefinition, SettingInteraction, defaults, feature,
    option_value, register_setting_interactions, resolved_options,
)
#
# Lettering keeps a derived zone for selection and old-design migration. Its
# physical footprint is the glyph outline, and its position is not editable.
# A recessed
# text is subtracted from the body it sits in rather than added to it, and
# either way it stays its own object in the 3MF so a slicer can give it its own
# filament.  ``build_features`` therefore builds it (so its errors surface with
# every other feature's) but leaves it out of the additive union; the exporter
# collects it through ``build_texts``.

TEXT_KIND = "text"
# Preview-only draw order. Inlaid lettering ends flush with the surface it is
# cut into, so the WebGL painter would otherwise hide it behind that surface.
# The mesh that gets exported is never moved; only this note rides along.
PREVIEW_INLAY_LAYER = 2


def preview_inlay_layer(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh.metadata["wavefinity_preview_layer"] = PREVIEW_INLAY_LAYER
    return mesh
TEXT_ZONE_EPSILON = 0.01     # glyph bounds land exactly on the zone; see _feature_reach
TEXT_INTERACTION_MARGIN = 0.25
TEXT_DEPTH_CHOICES = (0.2, 0.4, 0.6, 0.8)

# Every other holder's options are numbers, and the browser layer converts
# them as such. Text brought the first that are not: what it says, and two
# yes/no choices. Naming them here keeps that conversion honest instead of
# letting it guess from the value it happens to receive.
# Compatibility name for older callers; types now come from feature metadata.
NON_NUMERIC_OPTIONS = OPTION_TYPES


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

    Legacy missing heights resolve against the old saved zone once. Canonical
    features store their explicit height and a derived interaction zone.
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
    wanted = one.options.get("cap_height")
    if one.options.get("text_v2") and wanted not in (None, ""):
        cap = float(wanted)
        if not math.isfinite(cap) or cap < TEXT_CAP_HEIGHT_FLOOR:
            raise ValueError("Letter height is below the minimum readable size")
        return cap, _oriented_text(label, cap, turns)
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


def canonical_text_feature(one: Feature) -> Feature:
    """Turn old footprint/auto state into stable glyph size and derived bounds."""
    if not is_text(one):
        return one
    options = dict(one.options)
    canonical = options.get("text_v2") is True
    options["level"] = "rim" if options.get("level") == "rim" else "base"
    options["raised"] = bool(options.get("raised", False))
    options["depth"] = text_depth(one)
    options.pop("auto", None)
    options.pop("retarget", None)
    if options["level"] == "rim":
        options["rim_side"] = str(options.get("rim_side") or "back").lower()
        options["quarter_turns"] = 0
        if options.get("cap_height") in (None, ""):
            options["cap_height"] = TOP_LABEL_CAP_HEIGHT
        options["text_v2"] = True
        return replace(one, options=options)
    if not canonical:
        try:
            options["cap_height"] = text_fitted(one)[0]
        except ValueError:
            options["cap_height"] = TEXT_CAP_HEIGHT_IDEAL
    options["text_v2"] = True
    one = replace(one, options=options)
    try:
        _cap, glyph = text_fitted(one)
    except ValueError:
        return one
    x0, y0, x1, y1 = glyph.bounds
    cx, cy = one.zone.centre
    margin = TEXT_INTERACTION_MARGIN
    zone = Zone(cx + x0 - margin, cy + y0 - margin,
                cx + x1 + margin, cy + y1 + margin)
    return replace(one, zone=zone)


def retargeted_text(box: BoxSpec, one: Feature, mode: str = "fused") -> Feature:
    """Re-centre a Text whose Text Type just moved it between base and rim.

    The browser marks the change with ``retarget``. The destination seeds its own
    Letter height (a fitting 15 mm on the base, the rim default on a rim) and the
    Text is centred there; the marker is consumed and never saved.
    """
    options = {key: value for key, value in one.options.items()
               if key not in ("retarget", "cap_height", "text_v2", "auto")}
    if options.get("level") == "rim":
        side = str(options.get("rim_side") or "back").lower()
        return canonical_text_feature(replace(
            one, zone=Zone(*top_label_zone(box, side).bounds), options=options))
    zone = layout_zone(box, mode)
    seeded = replace(one, zone=zone, options=options)
    try:
        cap = min(TEXT_CAP_HEIGHT_IDEAL, text_fitted(seeded)[0])
    except ValueError:
        cap = TEXT_CAP_HEIGHT_IDEAL
    options["cap_height"] = cap
    return canonical_text_feature(replace(one, zone=zone, options=options))


def rim_text_geometry(box: BoxSpec, one: Feature):
    """The shelf and separate glyph for one feature-owned rim label."""
    side = str(one.options.get("rim_side") or "back").lower()
    label = text_of(one)
    if not label:
        raise ValueError("rim Text needs lettering")
    shelf_zone = top_label_zone(box, side)
    turns = {"back": 0, "front": 2, "left": 1, "right": 3}[side]
    wanted = float(one.options.get("cap_height") or TOP_LABEL_CAP_HEIGHT)
    probe = _oriented_text(label, wanted, turns)
    x0, y0, x1, y1 = probe.bounds
    available_x = shelf_zone.bounds[2] - shelf_zone.bounds[0] - 2 * TOP_LABEL_MARGIN
    available_y = shelf_zone.bounds[3] - shelf_zone.bounds[1] - 2 * TOP_LABEL_MARGIN
    scale = min(1.0, available_x / (x1 - x0), available_y / (y1 - y0))
    cap = wanted * scale
    if cap <= 0:
        raise ValueError("rim Text does not fit its selected side")
    glyph = _oriented_text(label, cap, turns)
    cx, cy = shelf_zone.centroid.coords[0]
    glyph = affinity.translate(glyph, xoff=cx, yoff=cy)
    depth = text_depth(one)
    if depth not in TEXT_DEPTH_CHOICES:
        if depth <= 0:
            raise ValueError("Text depth or height must be positive")
    raised = text_is_raised(one)
    safe_top = top_label_surface_z(box)
    surface = safe_top - depth if raised else safe_top
    if surface - TOP_LABEL_LEDGE_DEPTH < box.base_thickness:
        raise ValueError("rim Text needs more shelf backing; increase bin height")
    ledge = make_top_label_ledge(box, side)
    if raised:
        ledge.apply_translation((0, 0, -depth))
    text = preview_inlay_layer(text_prism(glyph, surface, depth, raised))
    return ledge, text, cap, surface


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
    }
    if one.options.get("level") == "rim":
        # What the shelf really lets the lettering be, not just what was asked.
        try:
            resolved["cap_height"] = round(rim_text_geometry(box, one)[2], 3)
        except ValueError:
            resolved["cap_height"] = float(one.options.get("cap_height") or TOP_LABEL_CAP_HEIGHT)
        return resolved
    try:
        resolved["cap_height"] = round(text_fitted(one)[0], 3)
    except ValueError:
        resolved["cap_height"] = TEXT_CAP_HEIGHT_IDEAL
    return resolved


@feature(
    TEXT_KIND, title="Text", display="Text — centered lettering",
    description="Centered lettering on the base or rim, Inlaid or Raised.",
    capabilities=("text",),
    options=(
        OptionDefinition("Letter height", "cap_height", ""),
        OptionDefinition("Inlay depth / Raised height", "depth", "0.4"),
        OptionDefinition("Text", "text", "", "string", False),
        OptionDefinition("Font", "font", "", "string", False),
        OptionDefinition("Raised", "raised", False, "boolean", False),
        OptionDefinition("Quarter turns", "quarter_turns", 0, "integer", False),
        OptionDefinition("Base or rim", "level", "base", "enum", False),
        OptionDefinition("Retarget", "retarget", "", "string", False),
        OptionDefinition("Rim side", "rim_side", "back", "enum", False),
    ), order=100,
)
def build_text(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """The lettering solid, sunk into (or standing on) the surface at ``base_z``.

    Recessed - the default - it occupies the depth immediately below the floor
    it sits in, so the exporter subtracts it and the finished floor stays flat
    with the letters as an inlay.
    """
    if spec_feature.options.get("level") == "rim":
        return [rim_text_geometry(box, spec_feature)[1]]
    outline = text_placed_outline(spec_feature)
    depth = text_depth(spec_feature)
    raised = text_is_raised(spec_feature)
    if depth <= 0.0:
        raise ValueError("text depth must be positive")
    if not raised:
        require_text_backing(base_z, depth, what="sunk text")
    if raised and base_z + depth > box.z + 1e-9:
        raise ValueError("raised text must stay inside the bin")
    return [preview_inlay_layer(text_prism(outline, base_z, depth, raised))]


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


register_setting_interactions(TEXT_KIND, (
    SettingInteraction("cap_height", "zone", "derived", "text-fit",
                       "Letter height derives the glyph outline and its interaction bounds."),
    SettingInteraction("text", "zone", "derived", "text-fit",
                       "Changing the lettering re-derives the glyph outline and its bounds."),
    SettingInteraction("quarter_turns", "zone", "derived", "text-fit",
                       "Turning base Text re-derives its bounds around the same centre."),
    SettingInteraction("level", "zone", "auto-adjust", "text-editor",
                       "Changing Text Type recenters the Text in its new base or rim destination."),
    SettingInteraction("level", "quarter_turns", "enable/disable", "text-editor",
                       "Rim Text follows its rim side's readable orientation and has no Turn."),
))
