"""Wavefinity web design, preview-geometry and layout payload helpers."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any
import numpy as np
from organizer_engine import (
    BASE_UNIT,
    MAX_BOX_SIZE,
    MIN_BOX_SIZE,
    MIN_HEIGHT_ABOVE_BASE,
    BoxSpec,
)
from organizer_inserts import (
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    build_features,
    connector_keep_out,
    cradle_min_footprint,
    divider_cells,
    divider_scoop_targets,
    feature_definition,
    feature_min_footprint,
    fitted_nest_feature,
    resolve_nest_settings,
    layout_zone,
    normalize_bore_modes,
    moved_feature,
    occupied_zones,
    normalize_divider_scoop,
    resized_feature,
    bore_bin_minimum,
    scoop_zone,
    resolve_text_features,
    resolved_options,
    snapped_zone,
)
from organizer_inserts._core import feature_touches_wall
from organizer_drawer import stack_part_height
from organizer_inventory import configure_space_text
from organizer_product_rules import ORDINARY_BIN_MIN_HEIGHT_MM
from organizer_app import (
    _customization_zones,
    base_height,
    convert_layout_mode,
    default_feature,
    design_from_dict,
    design_to_dict,
    inventory_bin_record,
    object_height_plan,
    preview_geometry,
    validate_customization_clearance,
)
from organizer_b4b import (
    b4b_effective_box,
    b4b_mating_polygon,
    b4b_preview_meshes,
    b4b_summary,
    validate_b4b_design,
    b4b_divider_solids,
    b4b_divider_work_box,
    b4b_divider_zone,
    normalize_b4b_divider,
)
from organizer_base_trim import (
    base_trim_design_to_dict,
    base_trim_from_design,
    base_trim_inner_polygon,
    base_trim_summary,
    make_base_trim_pieces,
)
from organizer_pegboard import pegboard_layout_for_bin

from ._runtime import (
    GEOMETRY_LOCK,
    _SupersededGeometry,
    _register_preview_request,
    _preview_geometry_lock,
    _interior_work_box,
)
from ._nest import (
    feature_to_dict,
    _item_from_json,
    _feature_from_json,
    _auto_size_photo_nest_layout_box,
    _resolve_photo_nest_edit,
    _first_open_position,
)


def _design(raw: dict[str, Any]) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    return design_from_dict(raw)


def _is_base_trim_design(raw: Any) -> bool:
    return isinstance(raw, dict) and raw.get("design_kind") == "base_trim"


def _base_trim_preview_meshes(spec) -> list[dict[str, Any]]:
    """Compact assembled-position mesh transport for every physical piece."""
    positions: list[float] = []
    normals: list[float] = []
    for _piece, mesh in make_base_trim_pieces(spec):
        triangles = np.asarray(mesh.triangles, dtype=float)
        if not len(triangles):
            continue
        keep = np.asarray(mesh.area_faces, dtype=float) > 1e-4
        positions.extend(np.round(triangles[keep], 3).reshape(-1).tolist())
        normals.extend(np.round(np.asarray(mesh.face_normals)[keep], 3).reshape(-1).tolist())
    if not positions:
        return []
    return [{
        "kind": "base_trim",
        "owner": "bin",
        "layer": 0,
        "positions": positions,
        "normals": normals,
    }]


def _base_trim_preview_payload(payload: dict[str, Any], token=None) -> dict[str, Any]:
    raw = payload["design"]
    spec = base_trim_from_design(raw)
    part_name = str(raw.get("part_name") or "")
    canonical = base_trim_design_to_dict(spec, part_name)
    canonical["base_trim"]["auto_size"] = bool(
        isinstance(raw.get("base_trim"), dict) and raw["base_trim"].get("auto_size")
    )
    with _preview_geometry_lock(token):
        summary = base_trim_summary(spec)
        meshes = _base_trim_preview_meshes(spec)
    inner = base_trim_inner_polygon(spec)
    outer_x, outer_y = summary["outer_mm"]
    return {
        "design": canonical,
        "base_trim": summary,
        "label_outline": [],
        "label_meta": None,
        "text_meta": [],
        "geometry": [],
        "meshes": meshes,
        "fits": True,
        "message": "",
        "feature_errors": [],
        "invalid_feature_indexes": [],
        "draft_error": None,
        "dimensions": {
            "size": (
                f"{outer_x:g} X {outer_y:g} X {spec.height_mm:g} mm Base Trim; "
                f"field {spec.units[0]}U x {spec.units[1]}U"
            ),
            "inside_x": spec.field_x,
            "inside_y": spec.field_y,
        },
        "layout_bounds": [-outer_x / 2.0, -outer_y / 2.0, outer_x / 2.0, outer_y / 2.0],
        "cavity_outline": [[float(x), float(y)] for x, y in inner.exterior.coords],
        "customization_zones": [],
        "feature_footprints": [],
        "draft_footprint": None,
        "feature_outlines": [],
        "nest_soft_contours": [],
        "draft_soft_contour": None,
        "nest_access": [],
        "draft_nest_access": None,
    }


def _reject_if_b4b(payload: dict[str, Any], what: str) -> None:
    """Guard routes that assume a normal box + interior layout."""
    design = payload.get("design")
    if not isinstance(design, dict):
        return
    box_raw = design.get("box", {})
    b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
    if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
        raise ValueError(
            f"{what} is not available while Storage Box is enabled - Storage Box "
            "Parts & options supports Dividers only"
        )


def _footprint_bounds(
    box: BoxSpec, one: Feature | None, mode: str
) -> list[float] | None:
    """One support's covered floor for the 2D layout, or ``None`` when it is
    simply its whole zone and the browser has nothing extra to draw."""
    if one is None:
        return None
    zone = occupied_zones(box, [one], base_height(box, mode), mode)[0]
    if zone == one.zone:
        return None
    return [zone.x0, zone.y0, zone.x1, zone.y1]


def _resolved_text(
    box: BoxSpec, features: tuple, mode: str,
    label: str, label_location: str, scoop: bool,
) -> tuple:
    """Canonical Text, resolving old auto-placement once on import."""
    return resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, label, label_location, scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )

def _b4b_preview_payload(payload: dict[str, Any], token=None) -> dict[str, Any]:
    """Preview for a Storage Box design: body/lid/latch/label meshes plus the
    authoritative capacity + hardware readout.  Shares the ordinary response
    shape so the frontend needs no special case to render it."""
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    eff = b4b_effective_box(box)
    adopted = replace(box, x=eff.x, y=eff.y, z=eff.z)
    message = ""
    feature_errors: list[str] = []
    invalid_feature_indexes: list[int] = []
    draft_error: str | None = None

    normalized_saved = []
    saved_indexes: list[int] = []
    for idx, feat in enumerate(layout.features):
        try:
            normalized_saved.append(normalize_b4b_divider(box, feat))
            saved_indexes.append(idx)
        except Exception as err:
            feature_errors.append(str(err))
            invalid_feature_indexes.append(idx)

    saved_layout = Layout(tuple(normalized_saved), "fused", layout.snap)
    display_features = list(normalized_saved)

    draft_raw = payload.get("draft")
    selected = payload.get("selected")
    draft_feature = None
    showing_draft = False
    if draft_raw and isinstance(draft_raw, dict):
        try:
            one = _feature_from_json(draft_raw, "fused")
            one = normalize_b4b_divider(box, one)
            draft_feature = one
            if selected == 0:
                display_features = [one]
                showing_draft = True
            elif selected is None and not normalized_saved:
                display_features = [one]
                showing_draft = True
            else:
                draft_error = "Storage Box supports one Divider layout."
        except Exception as err:
            draft_error = str(err)

    meshes: list[dict[str, Any]] = []
    b4b_block: dict[str, Any] | None = None
    try:
        with _preview_geometry_lock(token):
            validate_b4b_design(
                box,
                layout_feature_kinds=tuple(f.kind for f in display_features),
            )
            b4b_block = b4b_summary(box)
            meshes = b4b_preview_meshes(box, features=display_features)
    except _SupersededGeometry:
        raise
    except Exception as error:
        if draft_feature is not None and display_features == [draft_feature]:
            draft_error = str(error)
            showing_draft = False
            try:
                with _preview_geometry_lock(token):
                    validate_b4b_design(
                        box,
                        layout_feature_kinds=tuple(f.kind for f in normalized_saved),
                    )
                    b4b_block = b4b_summary(box)
                    meshes = b4b_preview_meshes(box, features=normalized_saved)
            except _SupersededGeometry:
                raise
            except Exception as saved_err:
                if not feature_errors and normalized_saved:
                    feature_errors.append(str(saved_err))
                    invalid_feature_indexes.extend(range(len(normalized_saved)))
                try:
                    with _preview_geometry_lock(token):
                        validate_b4b_design(box)
                        b4b_block = b4b_summary(box)
                        meshes = b4b_preview_meshes(box, features=())
                except _SupersededGeometry:
                    raise
                except Exception as base_err:
                    message = str(base_err)
        else:
            if display_features and not feature_errors:
                feature_errors.append(str(error))
                invalid_feature_indexes.extend(range(len(display_features)))
            try:
                with _preview_geometry_lock(token):
                    validate_b4b_design(box)
                    b4b_block = b4b_summary(box)
                    meshes = b4b_preview_meshes(box, features=())
            except _SupersededGeometry:
                raise
            except Exception as base_err:
                message = str(base_err)

    if not b4b_block:
        try:
            b4b_block = b4b_summary(box)
        except Exception:
            b4b_block = None

    bounds = b4b_divider_zone(box)
    cavity = b4b_mating_polygon(box)
    divider_pick = ({"type": "draft"} if showing_draft else
                    {"type": "saved", "index": saved_indexes[0]}
                    if saved_indexes else None)
    pick_meshes = [
        {"mesh_index": index, "pick": divider_pick}
        for index, mesh in enumerate(meshes)
        if divider_pick and mesh.get("kind") == "feature_divider"
    ]
    return {
        "design": design_to_dict(
            adopted, saved_layout, label, part_name, label_location, False
        ),
        "b4b": b4b_block,
        "label_outline": [],
        "label_meta": None,
        "text_meta": [],
        "geometry": [],
        "meshes": meshes,
        "pick_meshes": pick_meshes,
        "fits": not message and not feature_errors and not draft_error,
        "message": message,
        "feature_errors": feature_errors,
        "invalid_feature_indexes": invalid_feature_indexes,
        "draft_error": draft_error,
        "dimensions": {
            "size": (f"{eff.x:g} X {eff.y:g} X {eff.z:g} mm Storage Box child field - "
                     f"case outside {b4b_block['case_outer_mm'][0]:g} x "
                     f"{b4b_block['case_outer_mm'][1]:g} mm"
                     if b4b_block else f"{eff.x:g} X {eff.y:g} X {eff.z:g} mm Storage Box"),
            "inside_x": b4b_block["capacity_mm"][0] if b4b_block else None,
            "inside_y": b4b_block["capacity_mm"][1] if b4b_block else None,
        },
        "layout_bounds": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        "cavity_outline": [[float(x), float(y)] for x, y in cavity.exterior.coords],
        "customization_zones": [],
        "feature_footprints": [None] * len(saved_layout.features),
        "draft_footprint": None,
        "feature_outlines": [],
        "nest_soft_contours": [],
        "draft_soft_contour": None,
        "nest_access": [],
        "draft_nest_access": None,
    }


def validate_design_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload["design"]
    if _is_base_trim_design(raw):
        spec = base_trim_from_design(raw)
        design = base_trim_design_to_dict(spec, str(raw.get("part_name") or ""))
        design["base_trim"]["auto_size"] = bool(
            isinstance(raw.get("base_trim"), dict) and raw["base_trim"].get("auto_size")
        )
        return {"design": design}
    return {"design": design_to_dict(*_design(raw))}


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


def expand_layout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "auto-expanding the layout")
    """Resize the bin - on the 8 mm grid, both axes - to the smallest size that
    fits every interior support at the footprint it actually needs, then trim
    back any axis that overshot. A cradle footprint is recomputed from its
    tool, and a bore / post / slot zone is grown (never shrunk) to hold the
    hole grid, peg row or slot bank it was given - so an explicit X/Y quantity
    that overflowed the drawn zone still makes the bin grow instead of erroring.
    Other supports keep the size the user drew. Supports that now overlap - a
    grown block crowding its neighbour - are slid apart along the floor: the
    ``payload["anchor"]`` part (the one just edited) holds still and the rest
    move outward from it, with the bin growing to take in whatever ends up past
    its edge. Nothing is re-sized to make room; only moved.

    The current size is always the floor: this operation only grows. A larger
    bin is valid user intent and is never silently tightened around its parts.

    ``payload["fit"] = True`` switches to a true smallest-fit search instead:
    the current X/Y are no longer a floor, and the bin may shrink as well as
    grow to the smallest legal footprint that still holds the layout. Z is
    never touched either way.
    """
    request_box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    box = _interior_work_box(request_box)
    mode = layout.mode
    originals = list(layout.features)
    if not originals:
        raise ValueError("there are no interior supports to fit")
    # The part the user was editing when the fit gave out. It stays where it is
    # and the others move around it; without one, the biggest block anchors.
    anchor = payload.get("anchor")
    anchor = int(anchor) if anchor is not None and 0 <= int(anchor) < len(originals) else None
    fit = bool(payload.get("fit", False))

    if payload.get("fit_height_to_bore"):
        if anchor is None or originals[anchor].kind != "bore":
            raise ValueError("select a Bore before sizing the bin height")
        bore = originals[anchor]
        candidate_z = _bore_required_bin_z(request_box, box, mode, bore)
        max_height = payload.get("max_height")
        if max_height is not None and candidate_z > float(max_height) + 1e-9:
            raise ValueError(
                f"the Bore needs a {candidate_z:g} mm bin, above this Space's "
                f"{float(max_height):g} mm maximum height"
            )

        candidate_request = replace(request_box, z=candidate_z)
        candidate_design = design_to_dict(
            candidate_request, replace(layout, features=tuple(originals), mode=mode),
            label, part_name, label_location, scoop,
        )
        (validated_request, validated_layout, validated_label, validated_name,
         validated_location, validated_scoop) = _design(candidate_design)
        validated_box = _interior_work_box(validated_request)
        validate_customization_clearance(
            validated_box, validated_layout.features, validated_label,
            validated_location, validated_scoop, validated_layout.mode,
        )
        with GEOMETRY_LOCK:
            preview_geometry(
                validated_box, validated_label, validated_layout.features,
                validated_layout.mode, validated_location, validated_scoop,
            )
        canonical = design_to_dict(
            validated_request, validated_layout, validated_label,
            validated_name, validated_location, validated_scoop,
        )
        return {
            "design": canonical,
            "box": {
                "x": validated_request.x,
                "y": validated_request.y,
                "z": validated_request.z,
            },
            "grew": validated_request.z > request_box.z,
            "changed": validated_request.z != request_box.z,
        }

    def sized(one: Feature, trial: BoxSpec) -> Feature:
        if one.kind == "text":
            return one  # Text has no user-sized floor footprint.
        exact = False
        if one.kind == "bore":
            # A Bore's persisted sizing modes are re-resolved against each trial
            # bin: bore_to_bin follows the trial's usable floor exactly, and
            # bin_to_bore holds the Bore at its own minimum footprint.
            one = normalize_bore_modes(trial, one, base_height(trial, mode), mode)
            if one.options.get("xy_size_mode") == "bore_to_bin":
                return one
            exact = one.options.get("xy_size_mode") == "bin_to_bore"
        if one.kind == "nest" and one.contour:
            return fitted_nest_feature(one)
        if one.kind == "cradle" and one.item is not None:
            min_width, min_depth = cradle_min_footprint(one)
            if one.count is None:
                if one.along == "x":
                    width = min_width
                    depth = max(one.zone.depth, min_depth)
                else:
                    width = max(one.zone.width, min_width)
                    depth = min_depth
            else:
                width, depth = min_width, min_depth
        else:
            width, depth = one.zone.width, one.zone.depth
            grown = feature_min_footprint(trial, one, base_height(trial, mode))
            if grown is not None:
                # Round the grown footprint up to the editor grid, exactly as
                # "Fit to contents" does - otherwise the zone snap can leave it
                # a hair under what a leaned grid's reach needs.
                snap = layout.snap or EDITOR_SNAP
                grown = tuple(math.ceil(v / snap - 1e-6) * snap for v in grown)
                width, depth = (grown if exact else (max(width, grown[0]), max(depth, grown[1])))
                return resized_feature(one, trial, (width, depth), mode, layout.snap)
        cx, cy = one.zone.centre
        raw = Zone(cx - width / 2.0, cy - depth / 2.0,
                   cx + width / 2.0, cy + depth / 2.0)
        return replace(one, zone=snapped_zone(raw, trial, mode))

    def spread_apart(placed: list[Feature], trial: BoxSpec) -> list[Feature]:
        """Slide parts along the floor until none overlap, holding the anchor
        still and pushing the rest outward from it. Movement is clamped to the
        trial bin, so a size that cannot separate them just fails this trial and
        the search grows the bin one grid step and tries again."""
        if len(placed) < 2:
            return placed
        base_z = base_height(trial, mode)
        covered = lambda feat: occupied_zones(trial, [feat], base_z, mode)[0]
        zones = [covered(f) for f in placed]
        pivot = anchor
        if pivot is None:
            pivot = max(range(len(placed)),
                        key=lambda i: zones[i].width * zones[i].depth)
        ax, ay = zones[pivot].centre
        order = sorted((i for i in range(len(placed)) if i != pivot),
                       key=lambda i: (zones[i].centre[0] - ax) ** 2
                       + (zones[i].centre[1] - ay) ** 2)
        out = list(placed)
        settled = [pivot]
        def rim_text(one: Feature) -> bool:
            return one.kind == "text" and one.options.get("level") == "rim"
        for i in order:
            feat = out[i]
            if rim_text(feat):
                settled.append(i)
                continue
            for _ in range(80):
                here = covered(feat)
                clash = next((j for j in settled
                              if not rim_text(out[j])
                              and here.overlaps(covered(out[j]), MIN_FEATURE_GAP)),
                             None)
                if clash is None:
                    break
                if feat.kind == "text":
                    break  # A centered Text feature cannot be slid.
                other = covered(out[clash])
                # One editor grid step of slack on top of the bare overlap, so
                # the centre snap in ``moved_feature`` can't round it back into
                # a sub-gap touch and stall the loop.
                slack = (layout.snap or EDITOR_SNAP) + MIN_FEATURE_GAP
                over_x = min(here.x1, other.x1) - max(here.x0, other.x0) + slack
                over_y = min(here.y1, other.y1) - max(here.y0, other.y0) + slack
                cx, cy = here.centre
                if over_x <= over_y:
                    step = over_x if cx >= other.centre[0] else -over_x
                    moved = moved_feature(feat, trial, (cx + step, cy), mode, layout.snap)
                else:
                    step = over_y if cy >= other.centre[1] else -over_y
                    moved = moved_feature(feat, trial, (cx, cy + step), mode, layout.snap)
                if moved.zone.centre == feat.zone.centre:
                    break        # pinned against the bin wall - this trial is too small
                feat = moved
            out[i] = feat
            settled.append(i)
        return out

    def fits(x: float, y: float):
        try:
            trial = replace(box, x=float(x), y=float(y))
            placed = spread_apart(
                [sized(one, trial) for one in originals], trial
            )
            updated = replace(layout, features=tuple(placed), mode=mode)
            updated.validate(trial)
            validate_customization_clearance(
                trial, updated.features, label, label_location, scoop, mode
            )
        except ValueError:
            return None
        return trial, updated

    start_x, start_y = box.x, box.y
    ceiling = math.floor(MAX_BOX_SIZE / BASE_UNIT) * BASE_UNIT

    if fit:
        # Smallest legal footprint that fits the whole current layout: every
        # X/Y pair on the grid, tried in deterministic increasing order of
        # area, then max side, then side sum, then X, then Y.
        floor_units = int(round(MIN_BOX_SIZE / BASE_UNIT))
        ceiling_units = int(round(ceiling / BASE_UNIT))
        legal = [round(units * BASE_UNIT) for units in range(floor_units, ceiling_units + 1)]
        pairs = sorted(
            ((xv, yv) for xv in legal for yv in legal),
            key=lambda pair: (pair[0] * pair[1], max(pair), pair[0] + pair[1], pair[0], pair[1]),
        )
        x = y = None
        for xv, yv in pairs:
            if fits(xv, yv) is not None:
                x, y = xv, yv
                break
        if x is None:
            raise ValueError(
                "this layout will not fit within Wavefinity's maximum "
                f"{ceiling:g} mm bin size - remove or shrink a support"
            )
    else:
        floor_x, floor_y = start_x, start_y
        x, y = floor_x, floor_y
        result = fits(x, y)
        while result is None:
            x = round(x + BASE_UNIT)
            y = round(y + BASE_UNIT)
            if x > ceiling:
                raise ValueError(
                    "this layout will not fit within Wavefinity's maximum "
                    f"{ceiling:g} mm bin size - remove or shrink a support"
                )
            result = fits(x, y)

        # First fit found by growing both axes; give back any step that was not
        # actually needed (down to the floor).
        for _ in range(200):
            trimmed = False
            if x - BASE_UNIT >= floor_x and fits(x - BASE_UNIT, y) is not None:
                x = round(x - BASE_UNIT)
                trimmed = True
            if y - BASE_UNIT >= floor_y and fits(x, y - BASE_UNIT) is not None:
                y = round(y - BASE_UNIT)
                trimmed = True
            if not trimmed:
                break

    trial, updated = fits(x, y)
    with GEOMETRY_LOCK:
        build_features(
            trial, updated.features, base_height(trial, mode),
            layout_zone(trial, mode), mode,
        )
    # Growth here is X/Y only - the saved design keeps the requested module Z,
    # never the effective work box's printable Z.
    saved_box = replace(request_box, x=trial.x, y=trial.y)
    return {
        "design": design_to_dict(
            saved_box, updated, label, part_name, label_location, scoop,
        ),
        "box": {"x": saved_box.x, "y": saved_box.y, "z": saved_box.z},
        "grew": (trial.x > start_x or trial.y > start_y),
        "changed": (trial.x != start_x or trial.y != start_y),
    }


def inventory_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The planning record Space shows for the design being edited.

    Read-only: the same ``inventory_bin_record`` a generated bin would log, so
    Space sees the exact same x/y/z/kind/stack/wall envelope, but nothing is
    written, counted or claimed to exist as a file. Interior parts need not be
    generation-valid; only the container envelope matters here.
    """
    raw_design = payload["design"]
    if _is_base_trim_design(raw_design):
        raise ValueError("Base Trim is not a bin, so it has no place to plan in Space.")
    box, layout, label, part_name, _location, scoop = design_from_dict(
        raw_design, validate_layout=False,
    )
    with GEOMETRY_LOCK:
        record = inventory_bin_record(box, layout, None, label, part_name, scoop)
    record["file"] = ""
    plan = object_height_plan(raw_design, record.get("object_height_mm"))
    record["planning"] = {**plan, "physical_mm": stack_part_height(record),
                          "effective_mm": max(stack_part_height(record), plan["object_top_mm"] or 0.0)}
    return {"bin": record}


def pegboard_layouts_payload(payload: dict[str, Any]) -> dict[str, Any]:
    standard = payload.get("standard") or "standard"
    layouts: dict[str, Any] = {}
    for one in payload.get("bins") or []:
        if not isinstance(one, dict):
            continue
        key = str(one.get("id") or "")
        try:
            layouts[key] = pegboard_layout_for_bin(one, standard)
        except (TypeError, ValueError, KeyError) as error:
            layouts[key] = {"error": str(error), "compatible": False}
    return {"standard": standard, "layouts": layouts}


def create_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted equivalent of a genuinely new typed Space - never accepts
    legacy "box"; that only ever comes from configure_space_text_payload's
    migration path (see Fix 004 Correction 7.H)."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    for key in ("max_x_mm", "max_y_mm"):
        if key in payload:
            raw_def[key] = payload[key]
    for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
        if key in payload:
            raw_def[key] = payload[key]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="create",
    )


def configure_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted Configure Existing / migration: never rejected merely because
    the browser-owned inventory text already carries a layout.space."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    for key in ("max_x_mm", "max_y_mm"):
        if key in payload:
            raw_def[key] = payload[key]
    for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
        if key in payload:
            raw_def[key] = payload[key]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="update", allow_legacy=True,
    )
