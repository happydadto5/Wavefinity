"""Feature payloads: defaults, draft, apply, duplicate and delete."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any
from organizer_engine import MIN_HEIGHT_ABOVE_BASE, BoxSpec
from organizer_inserts import (
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    build_features,
    connector_keep_out,
    divider_cells,
    divider_scoop_targets,
    feature_definition,
    feature_min_footprint,
    resolve_nest_settings,
    layout_zone,
    normalize_bore_modes,
    moved_feature,
    normalize_divider_scoop,
    resized_feature,
    bore_bin_minimum,
    scoop_zone,
    resolved_options,
)
from organizer_inserts._core import feature_touches_wall
from organizer_product_rules import ORDINARY_BIN_MIN_HEIGHT_MM
from organizer_app import (
    base_height,
    convert_layout_mode,
    default_feature,
    design_from_dict,
    design_to_dict,
    validate_customization_clearance,
)
from organizer_b4b import (
    validate_b4b_design,
    b4b_divider_solids,
    b4b_divider_work_box,
    normalize_b4b_divider,
)
from .._runtime import (
    GEOMETRY_LOCK,
    _SupersededGeometry,
    _register_preview_request,
    _preview_geometry_lock,
    _interior_work_box,
)
from .._nest import (
    feature_to_dict,
    _item_from_json,
    _feature_from_json,
    _auto_size_photo_nest_layout_box,
    _resolve_photo_nest_edit,
    _first_open_position,
)

from ._preview import _design, _reject_if_b4b, _resolved_text


def default_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, *_ = _design(payload["design"])
    kind = str(payload["kind"])
    if box.b4b.enabled:
        if kind != "divider":
            raise ValueError(
                "adding interior parts is not available while Storage Box is enabled - "
                "Storage Box Parts & options supports Dividers only"
            )
        if any(f.kind == "divider" for f in layout.features):
            raise ValueError("Storage Box supports one Divider layout.")
        work = b4b_divider_work_box(box)
        one = default_feature(
            work,
            "divider",
            along=str(payload.get("along", "x")),
            mode="fused",
        )
        one = normalize_b4b_divider(box, one)
        return {
            "feature": feature_to_dict(one, "fused"),
            "resolved_options": resolved_options(work, one, work.base_thickness),
            "divider_cells": _divider_cells_payload(work, one, "fused"),
        }
    _reject_if_b4b(payload, "adding interior parts")
    box = _interior_work_box(box)
    try:
        definition = feature_definition(kind)
    except KeyError:
        raise ValueError(f"unknown interior part {kind!r}")
    item = (_item_from_json(payload.get("item"))
            if definition.flags["item"] else None)
    one = default_feature(
        box,
        kind,
        along=str(payload.get("along", "x")),
        mode=layout.mode,
        item=item,
    )
    if one.kind == "nest":
        # A fresh draft is new-format, not a legacy Raised Wall waiting to be
        # upgraded after upload. Seed the choices the UI already promises so
        # the before-photo controls and the generated holder cannot disagree.
        one = replace(one, options={
            **one.options,
            "holder_style": "recessed",
            "cavity_depth_mode": "auto",
            "auto_size": True,
            "lift_assist": "auto",
        })
    # Ordinary defaults are display values, not explicit choices. Keeping them
    # out of ``one.options`` preserves dependency cascades; Nest is the one
    # exception because holder_style also separates new saves from legacy ones.
    result = {
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": resolved_options(
            box, one, base_height(box, layout.mode)
        ),
    }
    if one.kind == "divider":
        result["divider_cells"] = _divider_cells_payload(box, one, layout.mode)
    return result


def _divider_cells_payload(
    box: BoxSpec, one: Feature, mode: str
) -> list[dict[str, Any]]:
    base_z = base_height(box, mode)
    selected = set(divider_scoop_targets(box, one, base_z))
    return [
        {
            "id": cell.identity,
            "row": cell.row,
            "column": cell.column,
            "zone": [cell.zone.x0, cell.zone.y0, cell.zone.x1, cell.zone.y1],
            "scoop": cell.identity in selected,
        }
        for cell in divider_cells(box, one, base_z)
    ]


def _bore_required_bin_z(
    request_box: BoxSpec, box: BoxSpec, mode: str, bore: Feature,
) -> float:
    """The bin height (mm, whole) that holds a Bore at its own resolved Height.

    The one owner of "size the bin to the Bore": the expand endpoint uses it to
    resize, and the draft answer reports it so the browser knows whether the bin
    is already there.
    """
    current_base_z = base_height(box, mode)
    bore_height = float(resolved_options(box, bore, current_base_z)["height"])
    required_work_z = current_base_z + bore_height
    if feature_touches_wall(box, bore):
        required_work_z += box.z - connector_keep_out(box)
    effective_z_offset = box.z - request_box.z
    structural_minimum = max(
        ORDINARY_BIN_MIN_HEIGHT_MM,
        request_box.base_thickness + MIN_HEIGHT_ABOVE_BASE,
    )
    return float(math.ceil(max(
        structural_minimum,
        required_work_z - effective_z_offset,
    ) - 1e-9))


def _bore_height_bin(
    request_box: BoxSpec, mode: str, one: Feature, box: BoxSpec,
) -> float | None:
    """Bin height a Height "Auto size bin to bore" Bore asks for, else ``None``."""
    if one.kind != "bore" or one.options.get("height_size_mode") != "bin_to_bore":
        return None
    try:
        return _bore_required_bin_z(request_box, box, mode, one)
    except ValueError:
        return None


def draft_payload(payload: dict[str, Any]) -> dict[str, Any]:
    token = _register_preview_request(payload, "draft")
    try:
        return _draft_payload(payload, token)
    except _SupersededGeometry:
        return {"superseded": True}


def _draft_payload(payload: dict[str, Any], token) -> dict[str, Any]:
    box, layout, label, _part, label_location, scoop = _design(payload["design"])
    if box.b4b.enabled:
        one = _feature_from_json(payload["feature"], "fused")
        if one.kind != "divider":
            raise ValueError(
                "editing interior parts is not available while Storage Box is enabled - "
                "Storage Box Parts & options supports Dividers only"
            )
        one = normalize_b4b_divider(box, one)
        with _preview_geometry_lock(token):
            b4b_divider_solids(box, [one])
        work = b4b_divider_work_box(box)
        return {
            "feature": feature_to_dict(one, "fused"),
            "resolved_options": resolved_options(work, one, work.base_thickness),
            "divider_cells": _divider_cells_payload(work, one, "fused"),
        }
    _reject_if_b4b(payload, "editing interior parts")
    request_box = box
    box = _interior_work_box(request_box)
    one = _feature_from_json(payload["feature"], layout.mode)
    one = normalize_bore_modes(box, one, base_height(box, layout.mode), layout.mode)
    if one.kind == "text":
        one = _resolved_text(box, (one,), layout.mode, label, label_location, scoop)[0]
    nest_solids = None
    if one.kind == "nest":
        request_box, box, _updated, one, _warnings, nest_solids = _resolve_photo_nest_edit(
            request_box, layout, one, label, label_location, scoop, index=payload.get("index"),
            request_token=token,
        )
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
        if one.full_span:
            one = replace(one, zone=layout_zone(box, layout.mode))
    elif one.kind == "scoop":
        one = replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))
    if one.kind == "text" and one.options.get("level") == "rim":
        from organizer_inserts._text import rim_text_geometry
        _ledge, _glyph, effective_cap, _surface = rim_text_geometry(box, one)
        return {
            "feature": feature_to_dict(one, layout.mode),
            "resolved_options": {"cap_height": round(effective_cap, 3)},
        }
    shown = (
        resolve_nest_settings(box, one, base_height(box, layout.mode))
        if one.kind == "nest" else
        resolved_options(box, one, base_height(box, layout.mode))
    )
    if nest_solids is None:
        with _preview_geometry_lock(token):
            build_features(
                box, [one], base_height(box, layout.mode),
                layout_zone(box, layout.mode), layout.mode, include_text=True,
            )
    result = {
        "feature": feature_to_dict(one, layout.mode),
        "resolved_options": shown,
    }
    # A Bore that sizes the bin around itself (Auto size bin to bore) reports the
    # cheap smallest bin around it; the browser runs the exact fit when the bin
    # is not already there.
    bore_bin = bore_bin_minimum(box, [one], base_height(box, layout.mode), layout.mode)
    if bore_bin is not None:
        result["bore_bin"] = {"x": bore_bin[0], "y": bore_bin[1]}
    height_bin = _bore_height_bin(request_box, layout.mode, one, box)
    if height_bin is not None:
        result["bore_bin_height"] = height_bin
    if one.kind == "divider":
        result["divider_cells"] = _divider_cells_payload(box, one, layout.mode)
    return result


def feature_fit_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "fitting interior parts")
    """Resize one draft feature's zone to the smallest that still holds
    everything it builds - its hole grid, peg row, slot bank or tool. Keeps the
    zone centred and touches nothing else. Raises for a kind with no natural
    contents size (pocket, steps, photo nest, divider, text).
    """
    box, layout, *_ = _design(payload["design"])
    box = _interior_work_box(box)
    one = _feature_from_json(payload["feature"], layout.mode)
    base_z = base_height(box, layout.mode)
    size = feature_min_footprint(box, one, base_z)
    if size is None:
        raise ValueError("this interior part has no contents to fit its size to")
    # Round the exact footprint up to the editor grid so the snapped zone is
    # never a hair under what the part needs (a leaned grid's reach is rarely
    # a whole millimetre).
    snap = layout.snap or EDITOR_SNAP
    size = tuple(math.ceil(v / snap - 1e-6) * snap for v in size)
    fitted = resized_feature(one, box, size, layout.mode, layout.snap)
    with GEOMETRY_LOCK:
        build_features(
            box, (fitted,), base_z, layout_zone(box, layout.mode), layout.mode,
        )
    return {"feature": feature_to_dict(fitted, layout.mode)}


def apply_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    if box.b4b.enabled:
        one = _feature_from_json(payload["feature"], "fused")
        if one.kind != "divider":
            raise ValueError(
                "adding interior parts is not available while Storage Box is enabled - "
                "Storage Box Parts & options supports Dividers only"
            )
        index = payload.get("index")
        if index is None:
            if len(layout.features) > 0:
                raise ValueError("Storage Box supports one Divider layout.")
        else:
            if int(index) != 0 or len(layout.features) == 0 or layout.features[0].kind != "divider":
                raise ValueError("Storage Box supports one Divider layout.")
        one = normalize_b4b_divider(box, one)
        with GEOMETRY_LOCK:
            validate_b4b_design(box, layout_feature_kinds=("divider",), deep=True)
            b4b_divider_solids(box, [one])
        updated = Layout((one,), "fused", layout.snap)
        return {
            "design": design_to_dict(
                box, updated, label, part_name, label_location, False
            ),
            "selected": 0,
            "warnings": [],
        }
    _reject_if_b4b(payload, "adding interior parts")
    request_box = box
    box = _interior_work_box(request_box)
    one = _feature_from_json(payload["feature"], layout.mode)
    one = normalize_bore_modes(box, one, base_height(box, layout.mode), layout.mode)
    if one.kind == "divider":
        one = normalize_divider_scoop(
            box, one, base_height(box, layout.mode)
        )
        if one.full_span:
            one = replace(one, zone=layout_zone(box, layout.mode))
    if one.kind == "nest":
        existing = list(layout.features)
        index = payload.get("index")
        if index is None:
            if existing:
                # Fix 111 R4-3: duplicate only when a Photo Nest already
                # exists; ordinary parts get the can-contain-only message.
                if any(item.kind != "nest" for item in existing):
                    raise ValueError("Photo Nest designs can contain Photo Nests only.")
                raise ValueError("Duplicate an existing Photo Nest first, then use Replace Photo on that copy.")
        else:
            selected = int(index)
            if not 0 <= selected < len(existing):
                raise ValueError("the selected interior part no longer exists")
            if existing[selected].kind != "nest" or any(item.kind != "nest" for item in existing):
                raise ValueError("Photo Nest designs can contain Photo Nests only.")
        request_box, _box, updated, one, nest_warnings, _solids = _resolve_photo_nest_edit(
            request_box, layout, one, label, label_location, scoop,
            index=(int(index) if index is not None else None),
        )
        return {
            "design": design_to_dict(
                request_box, updated, label, part_name, label_location, scoop,
            ),
            "selected": (int(index) if index is not None else 0),
            "warnings": nest_warnings,
        }
    if one.kind == "text":
        from organizer_inserts._text import canonical_text_feature
        one = canonical_text_feature(one)
    if one.kind == "scoop":
        one = replace(one, zone=scoop_zone(
            box, one, base_height(box, layout.mode), layout.mode, layout.snap
        ))

    # Full-span Dividers and Curved Scoops are derived from the bin, not from
    # a user-draggable footprint. Keep their exact normalized zone instead of
    # passing it through ordinary 1 mm resize/move snapping.
    if not (one.kind in {"scoop", "text"} or (one.kind == "divider" and one.full_span)
            or (one.kind == "bore" and one.options.get("xy_size_mode") == "bore_to_bin")):
        width, depth = one.zone.width, one.zone.depth
        cx, cy = one.zone.centre
        one = resized_feature(one, box, (width, depth), layout.mode, layout.snap)
        one = moved_feature(one, box, (cx, cy), layout.mode, layout.snap)
    index = payload.get("index")
    existing = list(layout.features)
    if any(item.kind == "nest" and item.contour for item in existing):
        raise ValueError("Photo Nest designs can contain scanned Photo Nests only.")
    if index is None:
        if one.kind != "text":
            one = _first_open_position(
                one, box, layout, label, label_location, scoop
            )
        existing.append(one)
        selected = len(existing) - 1
    else:
        selected = int(index)
        if not 0 <= selected < len(existing):
            raise ValueError("the selected interior part no longer exists")
        if one.kind != existing[selected].kind:
            remaining = existing[:selected] + existing[selected + 1:]
            if one.kind != "text":
                one = _first_open_position(
                    one, box, replace(layout, features=tuple(remaining)),
                    label, label_location, scoop,
                )
        existing[selected] = one
    # Auto-placed text finds its own spot, so resolve before judging overlaps -
    # otherwise a second one is refused for sitting on the first at the
    # placeholder zone it has not been moved out of yet.
    existing = list(_resolved_text(box, tuple(existing), layout.mode,
                                   label, label_location, scoop))
    updated = replace(layout, features=tuple(existing))
    updated.validate(box)
    validate_customization_clearance(
        box, updated.features, label, label_location, scoop, updated.mode
    )
    with GEOMETRY_LOCK:
        build_features(
            box, updated.features, base_height(box, updated.mode),
            layout_zone(box, updated.mode), updated.mode,
        )
    return {
        "design": design_to_dict(
            request_box, updated, label, part_name, label_location, scoop,
        ),
        "selected": selected,
        "warnings": [],
    }


def apply_reference_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Commit preview/planning data without running holder sizing owners."""
    _reject_if_b4b(payload, "editing a reference object")
    request_box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    one = _feature_from_json(payload["feature"], layout.mode)
    features = list(layout.features)
    index = payload.get("index")
    if index is None:
        if one.reference_object is None:
            raise ValueError("a new reference edit needs a reference object")
        features.append(one)
        selected = len(features) - 1
    else:
        selected = int(index)
        if not 0 <= selected < len(features):
            raise ValueError("the selected interior part no longer exists")
        if replace(one, reference_object=features[selected].reference_object) != features[selected]:
            raise ValueError("Reference edit also changed printable holder settings")
        features[selected] = one
    updated = replace(layout, features=tuple(features))
    box = _interior_work_box(request_box)
    updated.validate(box)
    validate_customization_clearance(box, updated.features, label, label_location, scoop, updated.mode)
    return {"design": design_to_dict(request_box, updated, label, part_name, label_location, scoop),
            "selected": selected}


def duplicate_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Duplicate a completed Photo Nest to another spot (Fix 082 J: Text's own
    Duplicate to rim is retired; this endpoint now serves Photo Nest only)."""
    request_box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    index = int(payload["index"])
    features = list(layout.features)
    if not 0 <= index < len(features) or features[index].kind != "nest" or not features[index].contour:
        raise ValueError("the selected Photo Nest no longer exists")
    if any(one.kind != "nest" for one in features):
        raise ValueError("Photo Nest designs can contain Photo Nests only.")
    box = _interior_work_box(request_box)
    source = features[index]
    clone = replace(source, options=dict(source.options))
    w, d = clone.zone.width, clone.zone.depth
    gap = MIN_FEATURE_GAP
    sx, sy = source.zone.centre
    candidates = [
        (source.zone.x1 + gap + w / 2, sy), (sx, source.zone.y1 + gap + d / 2),
        (source.zone.x0 - gap - w / 2, sy), (sx, source.zone.y0 - gap - d / 2),
    ]
    min_x = min(one.zone.x0 for one in features); max_x = max(one.zone.x1 for one in features)
    min_y = min(one.zone.y0 for one in features); max_y = max(one.zone.y1 for one in features)
    gcx, gcy = (min_x + max_x) / 2, (min_y + max_y) / 2
    candidates += [(max_x + gap + w / 2, gcy), (gcx, max_y + gap + d / 2),
                   (min_x - gap - w / 2, gcy), (gcx, min_y - gap - d / 2)]
    # Also try every existing legal grid centre, nearest first, for Manual.
    bounds = layout_zone(box, layout.mode)
    pitch = CARTRIDGE_PITCH if layout.mode == "cartridge" else layout.snap
    x = bounds.x0 + w / 2
    while x <= bounds.x1 - w / 2 + 1e-9:
        y = bounds.y0 + d / 2
        while y <= bounds.y1 - d / 2 + 1e-9:
            candidates.append((x, y)); y += pitch
        x += pitch
    unique: list[tuple[float, float]] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    auto = resolve_nest_settings(box, clone, base_height(box, layout.mode)).get("auto_size")
    choices = []
    for order, (cx, cy) in enumerate(unique):
        candidate = replace(clone, zone=Zone(cx - w / 2, cy - d / 2, cx + w / 2, cy + d / 2))
        proposed = features + [candidate]
        try:
            prospective = (_auto_size_photo_nest_layout_box(box, proposed, layout.mode,
                grow_only=(auto is None)) if auto is not False else box)
            bounds = layout_zone(prospective, layout.mode)
            if not all(bounds.x0 <= one.zone.x0 + 1e-6 and one.zone.x1 <= bounds.x1 + 1e-6
                       and bounds.y0 <= one.zone.y0 + 1e-6 and one.zone.y1 <= bounds.y1 + 1e-6
                       for one in proposed):
                continue
            updated = replace(layout, features=tuple(proposed))
            updated.validate(prospective)
            validate_customization_clearance(prospective, updated.features, label, label_location, scoop, updated.mode)
        except ValueError:
            continue
        choices.append(((prospective.x * prospective.y, max(prospective.x, prospective.y),
                         (cx - sx) ** 2 + (cy - sy) ** 2, order), prospective, updated))
    if not choices:
        if auto is False:
            raise ValueError("No room to duplicate this Photo Nest. Turn Automatic footprint sizing on or enlarge the bin.")
        raise ValueError("Could not find room for another copy of this Photo Nest.")
    _score, grown, updated = min(choices, key=lambda choice: choice[0])
    request_box = replace(request_box, x=grown.x, y=grown.y, z=request_box.z + (grown.z - box.z))
    box = _interior_work_box(request_box)
    with GEOMETRY_LOCK:
        build_features(box, updated.features, base_height(box, updated.mode),
                       layout_zone(box, updated.mode), updated.mode)
    return {"design": design_to_dict(request_box, updated, label, part_name, label_location, scoop),
            "selected": len(updated.features) - 1}


def delete_feature_payload(payload: dict[str, Any]) -> dict[str, Any]:
    box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    if box.b4b.enabled:
        index = int(payload["index"])
        if index != 0 or len(layout.features) == 0 or layout.features[0].kind != "divider":
            raise ValueError("the selected interior part no longer exists")
        updated = Layout((), "fused", layout.snap)
        return {"design": design_to_dict(
            box, updated, label, part_name, label_location, False,
        )}
    _reject_if_b4b(payload, "editing interior parts")
    # Deletion is the recovery path for a design made invalid by shrinking the
    # bin. Parse its schema and box, but defer layout validation until after
    # the unwanted support has been removed.
    index = int(payload["index"])
    existing = list(layout.features)
    if not 0 <= index < len(existing):
        raise ValueError("the selected interior part no longer exists")
    existing.pop(index)
    updated = replace(layout, features=tuple(existing))
    return {"design": design_to_dict(
        box, updated, label, part_name, label_location, scoop,
    )}


def mode_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "changing the interior-parts print mode")
    request_box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    box = _interior_work_box(request_box)
    new_mode = str(payload["mode"])
    converted = convert_layout_mode(box, layout.features, new_mode, layout)
    validate_customization_clearance(
        box, converted.features, label, label_location, scoop, converted.mode
    )
    return {"design": design_to_dict(
        request_box, converted, label, part_name, label_location, scoop,
    )}
