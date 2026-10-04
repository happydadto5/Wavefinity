"""Wavefinity web photo-nest request helpers and retrace payloads."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
from typing import Any
import numpy as np
from organizer_engine import BASE_UNIT, MIN_HEIGHT_ABOVE_BASE, BoxSpec
from organizer_inserts import (
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    build_features,
    clamp_nest_feature_options,
    fitted_nest_feature,
    is_legacy_nest,
    nest_access_preview,
    resolve_nest_settings,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    moved_feature,
    occupied_zones,
    option_value,
    scoop_zone,
)
from photo_nest import retrace_outline_from_rectified
from organizer_app import (
    _customization_zones,
    base_height,
    design_from_dict,
    design_to_dict,
    inside_handle_conflict,
    validate_customization_clearance,
)

from ._runtime import _preview_geometry_lock, _interior_work_box


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def feature_to_dict(one: Feature, mode: str = "fused") -> dict[str, Any]:
    return layout_to_dict(Layout((one,), mode, EDITOR_SNAP))["features"][0]


def _item_from_json(raw: dict[str, Any] | None) -> Item | None:
    if not raw:
        return None
    segments = tuple(
        Segment(float(segment["length"]), float(segment["diameter"]))
        for segment in raw.get("segments", [])
        if str(segment.get("length", "")).strip()
        and str(segment.get("diameter", "")).strip()
    )
    if not segments:
        raise ValueError("enter the stored item's length and thickness")
    return Item(
        str(raw.get("name", "Custom item")).strip() or "Custom item",
        segments,
        str(raw.get("profile", "round")),
        float(raw.get("clearance", 0.4)),
    )


def _feature_from_json(raw: dict[str, Any], mode: str) -> Feature:
    data = dict(raw)
    options = {
        str(key): option_value(str(key), value, str(data.get("kind", "")))
        for key, value in dict(data.get("options", {})).items()
        if str(value).strip() != ""
    }
    data["options"] = options
    if data.get("count") in {"", "auto", None}:
        data["count"] = None
    data["item"] = data.get("item") or None
    layout = layout_from_dict({
        "version": 1,
        "mode": mode,
        "snap": EDITOR_SNAP,
        "features": [data],
    })
    return layout.features[0]


NEST_TOOL_TOP_CLEARANCE = 1.0  # mm of clear air above the tool's own top


def _nest_effective_z_requirement(
    box: BoxSpec, mode: str, base_z: float, resolved: dict[str, Any],
) -> float:
    """The smallest interior work-box Z this Nest can legally use: enough for
    the printable structural minimum, 1 mm of air above the tool's own top,
    and whatever the resolved holder geometry itself rises to."""
    tool_thickness = float(resolved["tool_thickness"])
    if str(resolved["holder_style"]) == "recessed":
        geometry_top = base_z + float(resolved["cavity_depth"])
    else:
        push_depth = (
            float(resolved["push_depth"]) if str(resolved["lift_assist"]) == "push_out" else 0.0
        )
        geometry_top = base_z + tool_thickness + push_depth
    tool_top_requirement = base_z + tool_thickness + NEST_TOOL_TOP_CLEARANCE
    structural_minimum = base_z + MIN_HEIGHT_ABOVE_BASE
    return max(structural_minimum, tool_top_requirement, geometry_top)


def _legacy_nest_z_requirement(box: BoxSpec, mode: str, resolved: dict[str, Any]) -> float:
    """The exact historical grow-only Z requirement for a true legacy Nest
    (no stored holder_style): base_z + its depth, plus Push Out's own deck
    depth when active. No new 1 mm tool-top clearance, no structural-minimum
    floor beyond whatever the box already is - that policy is new-format
    only and must not change a legacy design's sizing just because it is
    edited or re-applied."""
    base_z = base_height(box, mode)
    tool_thickness = float(resolved["tool_thickness"])
    push_depth = float(resolved["push_depth"]) if str(resolved["lift_assist"]) == "push_out" else 0.0
    return base_z + tool_thickness + push_depth


def _fit_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> BoxSpec:
    """Legacy grow-only sizing, for a design saved before Auto-size existed.

    The current dimensions are floors: uploading or editing a smaller outline
    must not undo a larger bin the user deliberately chose.
    """
    resolved = resolve_nest_settings(box, one, base_height(box, mode))
    required_x = 2.0 * max(abs(one.zone.x0), abs(one.zone.x1))
    required_y = 2.0 * max(abs(one.zone.y0), abs(one.zone.y1))
    x = max(box.x, BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(box.y, BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    z_requirement = (
        _legacy_nest_z_requirement(box, mode, resolved) if is_legacy_nest(one)
        else _nest_effective_z_requirement(box, mode, base_height(box, mode), resolved)
    )
    z = max(box.z, z_requirement)
    for _attempt in range(200):
        trial = replace(box, x=float(x), y=float(y), z=float(z))
        bounds = layout_zone(trial, mode)
        grow_x = one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
        grow_y = one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
        if not grow_x and not grow_y:
            return trial
        if grow_x:
            x += BASE_UNIT
        if grow_y:
            y += BASE_UNIT
    raise ValueError("the photographed outline is too large for a printable bin")


def _auto_size_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> BoxSpec:
    """New Auto-size: the smallest legal X/Y footprint that holds the fitted,
    centred Nest - Width and Length may grow or shrink, but the box's existing
    Height is always preserved exactly. Height is user-controlled; a fused
    Raised Wall taller than the rim is a layout-mode policy decision made
    centrally in ``build_features``, not something footprint auto-sizing may
    resolve by growing Z."""
    trial: BoxSpec | None = None
    required_x = 2.0 * max(abs(one.zone.x0), abs(one.zone.x1))
    required_y = 2.0 * max(abs(one.zone.y0), abs(one.zone.y1))
    x = max(BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    for _attempt in range(400):
        trial = replace(box, x=float(x), y=float(y))
        bounds = layout_zone(trial, mode)
        grow_x = one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
        grow_y = one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
        if not grow_x and not grow_y:
            break
        if grow_x:
            x += BASE_UNIT
        if grow_y:
            y += BASE_UNIT
    else:
        raise ValueError("the photographed outline is too large for a printable bin")
    for axis in ("x", "y"):
        while True:
            try:
                candidate = replace(trial, **{axis: getattr(trial, axis) - BASE_UNIT})
            except ValueError:
                break
            bounds = layout_zone(candidate, mode)
            if (one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
                    or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6):
                break
            trial = candidate
    return trial


def _sized_photo_nest_box(box: BoxSpec, one: Feature, mode: str) -> tuple[BoxSpec, Feature]:
    """Apply this Nest's sizing policy: new Auto grows, shrinks and recentres
    around the fitted outline; Manual never resizes, and reports a plain fit
    error instead; legacy (no stored preference) only ever grows, unchanged
    from before Auto-size existed."""
    resolved = resolve_nest_settings(box, one, base_height(box, mode))
    auto_size = resolved.get("auto_size")
    if auto_size is True:
        one = fitted_nest_feature(one, (0.0, 0.0))
        return _auto_size_photo_nest_box(box, one, mode), one
    if auto_size is False:
        one = fitted_nest_feature(one, one.zone.centre)
        base_z = base_height(box, mode)
        bounds = layout_zone(box, mode)
        xy_fails = (
            one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
            or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6
        )
        # A fused Raised Wall is allowed to rise above the rim, so its own
        # height is not a fit failure there; Recessed always depends on real
        # material above the floor, and any non-fused mode still clips to the
        # bin, so both keep the Z check.
        must_fit_z = (
            mode != "fused"
            or str(resolved["holder_style"]) == "recessed"
        )
        z_fails = False
        if must_fit_z:
            z_required = _nest_effective_z_requirement(box, mode, base_z, resolved)
            z_fails = z_required > box.z + 1e-6
        if xy_fails:
            raise ValueError(
                "This Photo Nest no longer fits its bin. Use “Fit footprint to "
                "tool” below, or turn Automatic footprint sizing back on."
            )
        if z_fails:
            raise ValueError(
                "This Photo Nest's holder no longer fits the bin's Height. "
                "Increase Bin Height, or reduce the Tool thickness or other "
                "measurement that controls its height."
            )
        return box, one
    one = fitted_nest_feature(one, one.zone.centre)
    return _fit_photo_nest_box(box, one, mode), one


def _auto_size_photo_nest_layout_box(box: BoxSpec, features: list[Feature], mode: str,
                                     *, grow_only: bool = False) -> BoxSpec:
    """Smallest grid box holding every independently placed Nest group."""
    required_x = 2.0 * max(max(abs(one.zone.x0), abs(one.zone.x1)) for one in features)
    required_y = 2.0 * max(max(abs(one.zone.y0), abs(one.zone.y1)) for one in features)
    x = max(box.x if grow_only else BASE_UNIT, math.ceil(required_x / BASE_UNIT) * BASE_UNIT)
    y = max(box.y if grow_only else BASE_UNIT, math.ceil(required_y / BASE_UNIT) * BASE_UNIT)
    for _attempt in range(400):
        trial = replace(box, x=float(x), y=float(y))
        bounds = layout_zone(trial, mode)
        if all(bounds.x0 - 1e-6 <= one.zone.x0 and one.zone.x1 <= bounds.x1 + 1e-6
               and bounds.y0 - 1e-6 <= one.zone.y0 and one.zone.y1 <= bounds.y1 + 1e-6
               for one in features):
            break
        if any(one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6 for one in features):
            x += BASE_UNIT
        if any(one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6 for one in features):
            y += BASE_UNIT
    else:
        raise ValueError("the photographed outline is too large for a printable bin")
    if not grow_only:
        for axis in ("x", "y"):
            while getattr(trial, axis) - BASE_UNIT >= BASE_UNIT:
                candidate = replace(trial, **{axis: getattr(trial, axis) - BASE_UNIT})
                bounds = layout_zone(candidate, mode)
                if not all(bounds.x0 - 1e-6 <= one.zone.x0 and one.zone.x1 <= bounds.x1 + 1e-6
                           and bounds.y0 - 1e-6 <= one.zone.y0 and one.zone.y1 <= bounds.y1 + 1e-6
                           for one in features):
                    break
                trial = candidate
    return trial


def _resolve_photo_nest_edit(
    request_box: BoxSpec,
    layout: Layout,
    one: Feature,
    label: str,
    label_location: str,
    scoop: bool,
    *,
    index: int | None = None,
    request_token=None,
) -> tuple[BoxSpec, BoxSpec, Layout, Feature, list[str], list[Any]]:
    """Repair a live Nest edit before anything can reject stale dimensions."""
    if one.kind != "nest" or not one.contour:
        raise ValueError("upload a part photo before adding a Photo Nest")
    if any(existing.kind != "nest" for existing in layout.features):
        raise ValueError("Photo Nest designs can contain Photo Nests only.")
    one, warnings = clamp_nest_feature_options(one)
    box = _interior_work_box(request_box)
    features = list(layout.features)
    if index is None:
        if features:
            raise ValueError("Duplicate an existing Photo Nest first, then use Replace Photo on that copy.")
        selected = 0
        features.append(one)
    else:
        if not 0 <= index < len(features) or features[index].kind != "nest":
            raise ValueError("the selected Photo Nest no longer exists")
        selected = index
        features[selected] = one
    resolved = resolve_nest_settings(box, one, base_height(box, layout.mode))
    recenter = len(features) == 1 and resolved.get("auto_size") is True
    one = fitted_nest_feature(one, (0.0, 0.0) if recenter else one.zone.centre)
    features[selected] = one
    auto_size = resolved.get("auto_size")
    if auto_size is True:
        grown = _auto_size_photo_nest_layout_box(box, features, layout.mode)
    elif auto_size is None:
        grown = _auto_size_photo_nest_layout_box(box, features, layout.mode, grow_only=True)
    else:
        grown = box
        bounds = layout_zone(box, layout.mode)
        if not all(bounds.x0 - 1e-6 <= member.zone.x0 and member.zone.x1 <= bounds.x1 + 1e-6
                   and bounds.y0 - 1e-6 <= member.zone.y0 and member.zone.y1 <= bounds.y1 + 1e-6
                   for member in features):
            raise ValueError("This Photo Nest no longer fits its bin. Turn Automatic footprint sizing back on or enlarge the bin.")
    request_box = replace(
        request_box, x=grown.x, y=grown.y,
        z=request_box.z + (grown.z - box.z),
    )
    box = _interior_work_box(request_box)
    updated = replace(layout, features=tuple(features))
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with _preview_geometry_lock(request_token):
        solids = build_features(
            box, updated.features, base_height(box, updated.mode),
            layout_zone(box, updated.mode), updated.mode,
        )
    return request_box, box, updated, one, warnings, solids


def nest_retrace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Re-tune an already-rectified reference sheet without repeating paper
    detection or perspective correction. Purely informational: the caller
    decides whether/when to accept the candidate outline it returns."""
    outline = retrace_outline_from_rectified(
        str(payload.get("rectified_image", "")), str(payload.get("mime_type", "image/jpeg")),
        float(payload.get("sensitivity", 50.0)), float(payload.get("cleanup", 50.0)),
    )
    result = {
        "outline": {"width": outline.width, "depth": outline.depth},
        "contour": [list(point) for point in outline.contour],
        "trace_center_mm": list(outline.trace_center_mm) if outline.trace_center_mm else None,
    }
    if outline.reference_image and outline.reference_bounds:
        result["reference"] = {
            "image": outline.reference_image,
            "bounds": list(outline.reference_bounds),
        }
    return result


def photo_nest_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Finalize (create or update) the Photo Nest from an ALREADY-TRACED
    contour - see nest_trace_payload for the separate, design-independent
    tracing phase this depends on. Never decodes or retraces a photo."""
    request_box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )

    contour_raw = payload.get("contour")
    if not isinstance(contour_raw, list) or len(contour_raw) < 3:
        raise ValueError("no traced outline was supplied")
    contour = tuple((float(point[0]), float(point[1])) for point in contour_raw)
    source_raw = payload.get("source_contour", contour_raw)
    source_contour = tuple((float(point[0]), float(point[1])) for point in source_raw)

    raw_index = payload.get("index")
    index = int(raw_index) if raw_index is not None else None
    if index is not None and not 0 <= index < len(layout.features):
        raise ValueError("the selected Photo Nest no longer exists")
    saved_existing = layout.features[index] if index is not None else None
    # Replace Photo: prefer the browser's own live draft over the last-saved
    # copy - a debounced auto-save may not have caught up with the newest
    # setting yet, and starting the photo operation must not lose it.
    live_raw = payload.get("feature")
    live_feature = None
    if isinstance(live_raw, dict):
        candidate = _feature_from_json(live_raw, layout.mode)
        if candidate.kind == "nest" and candidate.contour:
            live_feature = candidate
    existing = live_feature if live_feature is not None else saved_existing
    if index is None and layout.features:
        # Fix 111 R4-3: an existing Photo Nest is duplicated; ordinary
        # interior parts can never share a design with a Photo Nest.
        if any(one.kind != "nest" for one in layout.features):
            raise ValueError("Photo Nest designs can contain Photo Nests only.")
        raise ValueError("Duplicate an existing Photo Nest first, then use Replace Photo on that copy.")

    supplied = dict(payload.get("options", {}))
    if existing is None:
        # New scan: Tool thickness is the one measurement the user actually
        # has to supply, and must never be invented.
        measured = supplied.get("tool_thickness", supplied.get("depth"))
        if measured in (None, ""):
            raise ValueError("enter the tool's thickness before generating a Photo Nest")
        tool_thickness = float(measured)
        if not math.isfinite(tool_thickness) or tool_thickness <= 0.0:
            raise ValueError("Tool thickness must be a positive number")
        # A brand-new scan defaults to Recessed Cavity, automatic 60% cavity
        # depth, automatic finger access and automatic bin sizing (spec
        # section 2) - but ONLY when the user has not already chosen
        # otherwise on the draft before the scan finished.
        options = {
            "clearance": float(supplied.get("clearance", 0.6)),
            "tool_thickness": tool_thickness,
            "rim": 3.0,
            "smoothing": float(supplied.get("smoothing", 0.0)),
            "holder_style": str(supplied.get("holder_style", "recessed")),
            "cavity_depth_mode": str(supplied.get("cavity_depth_mode", "auto")),
            "auto_size": bool(supplied["auto_size"]) if "auto_size" in supplied else True,
            "lift_assist": str(supplied.get("lift_assist", "auto")),
            "finger_position": str(supplied.get("finger_position", "sides")),
            "push_position": str(supplied.get("push_position", "right")),
            "push_area": float(supplied.get("push_area", 30.0)),
            "push_depth": float(supplied.get("push_depth", 4.0)),
        }
        if supplied.get("cavity_depth") not in (None, ""):
            options["cavity_depth"] = float(supplied["cavity_depth"])
        if supplied.get("finger_width") not in (None, ""):
            options["finger_width"] = float(supplied["finger_width"])
        starter = Feature(
            "nest", Zone(-0.5, -0.5, 0.5, 0.5), options=options,
            count=1, contour=contour, source_contour=source_contour,
        )
    else:
        # Replace Photo: change only the outline. Holder style, cavity
        # depth/mode, finger access, Auto-size, Tool thickness, rotation and
        # scale all survive untouched, or replacing a blurry photo of the
        # same tool would silently reset choices the user already made
        # (including shrinking a manually sized bin back to Auto).
        starter = replace(existing, contour=contour, source_contour=source_contour)
    request_box, _box, updated, one, nest_warnings, _solids = _resolve_photo_nest_edit(
        request_box, layout, starter, label, label_location, scoop, index=index,
    )
    return {
        "design": design_to_dict(
            request_box, updated, label, part_name, label_location, scoop,
        ),
        "selected": index if index is not None else 0,
        "access": nest_access_preview(one),
        "warnings": nest_warnings,
    }


def _first_open_position(
    one: Feature,
    box: BoxSpec,
    layout: Layout,
    label: str,
    label_location: str,
    scoop: bool,
) -> Feature:
    # Auto-placed text does its own searching, over its real ink rather than a
    # placeholder rectangle, so hunting a slot for it here only produces a
    # zone that ``resolve_text_features`` immediately replaces - and a bad one,
    # since the placeholder is wider than the lettering it stands for.
    if one.kind == "text" and one.options.get("auto"):
        return one
    if one.kind == "scoop":
        return replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))
    bounds = layout_zone(box, layout.mode)
    pitch = 8.0 if layout.mode == "cartridge" else layout.snap
    xs = np.arange(
        bounds.x0 + one.zone.width / 2.0,
        bounds.x1 - one.zone.width / 2.0 + 1e-8,
        pitch,
    )
    ys = np.arange(
        bounds.y0 + one.zone.depth / 2.0,
        bounds.y1 - one.zone.depth / 2.0 + 1e-8,
        pitch,
    )
    candidates = [(float(x), float(y)) for y in ys for x in xs]
    candidates.sort(key=lambda point: point[0] ** 2 + point[1] ** 2)
    if not candidates:
        raise ValueError("there is no open floor area large enough for that interior part")
    reserved = _customization_zones(
        box, label, label_location, scoop, layout.mode
    )
    # Judged on the floor each support actually covers rather than on its zone,
    # so a new one can drop into the open end of a cradle's zone - see
    # ``occupied_zones``.
    base_z = base_height(box, layout.mode)
    taken = [zone for feature, zone in zip(
        layout.features, occupied_zones(box, layout.features, base_z, layout.mode)
    ) if not (feature.kind == "text" and feature.options.get("level") == "rim")]
    taken.extend(zone for _name, zone in reserved)
    # That covered floor sits at a fixed offset inside the support's own zone,
    # and moving the support moves both together, so it is worked out once here
    # instead of being rebuilt for every candidate centre on the grid.
    trial = moved_feature(one, box, candidates[0], layout.mode, layout.snap)
    covered = occupied_zones(box, [trial], base_z, layout.mode)[0]
    trial_x, trial_y = trial.zone.centre
    inset = (covered.x0 - trial_x, covered.y0 - trial_y,
             covered.x1 - trial_x, covered.y1 - trial_y)
    for centre in candidates:
        placed = moved_feature(one, box, centre, layout.mode, layout.snap)
        centre_x, centre_y = placed.zone.centre
        covers = Zone(centre_x + inset[0], centre_y + inset[1],
                      centre_x + inset[2], centre_y + inset[3])
        if (all(not covers.overlaps(zone, MIN_FEATURE_GAP) for zone in taken)
                and inside_handle_conflict(box, placed, base_z, layout.mode) is None):
            return placed
    raise ValueError("there is no open floor area large enough for that interior part")


def _option_payload(option) -> dict[str, Any]:
    """One option's key/type plus whatever legal-value metadata it declares."""
    entry: dict[str, Any] = {"key": option.key, "type": option.value_type}
    if option.choices:
        entry["choices"] = [{"value": value, "label": label} for value, label in option.choices]
    for name in ("minimum", "maximum", "step"):
        if getattr(option, name) is not None:
            entry[name] = getattr(option, name)
    if option.note:
        entry["note"] = option.note
    if option.internal:
        entry["internal"] = True
    if option.legacy:
        entry["legacy"] = True
    return entry
