"""Design payload helpers: base-trim and B4B preview payloads."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
import numpy as np
from organizer_engine import BoxSpec
from organizer_inserts import Feature, Layout, occupied_zones, resolve_text_features
from organizer_app import (
    _customization_zones,
    base_height,
    design_from_dict,
    design_to_dict,
)
from organizer_b4b import (
    b4b_effective_box,
    b4b_mating_polygon,
    b4b_preview_meshes,
    b4b_summary,
    validate_b4b_design,
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
from .._runtime import _SupersededGeometry, _preview_geometry_lock
from .._nest import _feature_from_json


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
