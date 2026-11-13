"""Browser preview route using the canonical geometry and server response contract.

B14 registers ROUTES after installing the browser manifold bridge.
"""
from typing import Any
import math
from organizer_engine import BoxSpec, lid_enabled, wavy_cavity_polygon
from organizer_inserts import (Feature, Layout, layout_zone, normalize_bore_modes,
    nest_contour_polygon, nest_smoothed_contour, nest_occurrence_preview, nest_access_preview)
from organizer_inserts._bore import bore_reference_top
from organizer_drawer import stack_part_height
from organizer_app import (base_height, design_to_dict, inventory_bin_record,
    object_height_plan, preview_geometry, lid_label_regions, _mesh_preview_geometry)
from organizer_features.stack import (make_lid_parts, stack_effective_box, stack_enabled,
    stack_summary, validate_stack_design)
from organizer_geometry import build_scope, checkpoint, stage
from wavefinity_web_impl._runtime import (_register_preview_request, _real_preview_active,
    _token_superseded, _SupersededGeometry, _preview_geometry_lock, _interior_work_box)
from wavefinity_web_impl._nest import _feature_from_json
from wavefinity_web_impl._designs._preview import (_design, _is_base_trim_design,
    _base_trim_preview_payload, _b4b_preview_payload, _footprint_bounds)
from wavefinity_web_impl._ai import _capped_space_height, _ai_space_context

def preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    token = _register_preview_request(payload, "preview")
    try:
        with _real_preview_active(), build_scope(lambda: _token_superseded(token)) as timings:
            result = _preview_payload(payload, token)
            checkpoint()   # a result a newer request already replaced is not sent
            # Where this build's time went, in ms per stage (self time): wait
            # (queued), outline_wave, shell, features, lid, booleans,
            # conversion, other, and the build's total. Cheap enough to keep.
            result["build_timings_ms"] = timings.report()
            return result
    except _SupersededGeometry:
        return {"superseded": True}


def _preview_payload(payload: dict[str, Any], token) -> dict[str, Any]:
    if _is_base_trim_design(payload.get("design")):
        return _base_trim_preview_payload(payload, token)
    if isinstance(payload.get("design"), dict):
        box_raw = payload["design"].get("box", {})
        b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
        if isinstance(b4b_raw, dict) and b4b_raw.get("enabled"):
            return _b4b_preview_payload(payload, token)
    box, layout, label, part_name, label_location, scoop = _design(payload["design"])
    from organizer_inserts._walljoin import build_grid
    with build_grid(layout.design_grid):
        return _preview_bin_payload(
            payload, token, box, layout, label, part_name, label_location, scoop,
        )


def _preview_bin_payload(payload, token, box, layout, label, part_name, label_location, scoop):
    """Preview body, inserts and lid under the existing design-grid context."""
    draft_raw = payload.get("draft")
    draft = _feature_from_json(draft_raw, layout.mode) if draft_raw else None
    if draft is not None:
        draft = normalize_bore_modes(
            _interior_work_box(box), draft,
            base_height(_interior_work_box(box), layout.mode), layout.mode,
        )
    selected = payload.get("selected")
    if not isinstance(selected, int) or isinstance(selected, bool):
        selected = None
    # Stacking derives the printable body from the visible legal settings and
    # the requested module-height datum.
    stack_request = box
    stack_block = None
    if stack_enabled(box) or lid_enabled(box):
        validate_stack_design(box)
        stack_block = stack_summary(box)
        box = stack_effective_box(box)
    with _preview_geometry_lock(token):
        scene = preview_geometry(
            box, label, layout.features, layout.mode, label_location, scoop, draft,
            selected=selected, layout=layout,
        )
        if lid_enabled(stack_request):
            with stage("lid"):
                lid, lid_texts = make_lid_parts(
                    stack_request, lid_label_regions(stack_request, layout),
                )
            scene["geometry"].extend(_mesh_preview_geometry(lid, "lid"))
            for _text, mesh, _raised in lid_texts:
                scene["geometry"].extend(_mesh_preview_geometry(mesh, "lid_label"))
    bounds = layout_zone(box, layout.mode)
    with stage("conversion"):
        geometry = [
            {"points": points, "kind": kind, "normal": normal,
             "layer": layer, "owner": owner,
             "pick": scene.get("pick_faces", {}).get(index)}
            for index, (points, kind, normal, layer, owner) in enumerate(scene["geometry"])
        ]
    with stage("outline_wave"):
        cavity = wavy_cavity_polygon(box)
    resolved = layout
    canonical = design_to_dict(stack_request, resolved, label, part_name, label_location, scoop)
    planning_record = inventory_bin_record(stack_request, resolved, None, label, part_name, scoop)
    planning = object_height_plan(canonical, resolved.object_height_mm)
    planning["effective_mm"] = max(stack_part_height(planning_record), planning["object_top_mm"] or 0.0)
    storage_box_height_warning = None
    raw_space = payload.get("space")
    if isinstance(raw_space, dict) and raw_space.get("kind") in ("portable", "box"):
        cap = float(raw_space["z"])
        if stack_block is not None and stack_block["enabled"]:
            height = stack_block["closed_height_mm"] + stack_block["pitch_mm"]
            warning_kind = "two_bins"
        else:
            height = stack_block["closed_height_mm"] if lid_enabled(stack_request) else stack_part_height(planning_record)
            warning_kind = "one_bin"
        if height > cap + 1e-6:
            storage_box_height_warning = {
                "kind": warning_kind, "height_mm": round(height, 3), "cap_mm": round(cap, 3),
            }
    effective = list(layout.features)
    if draft is not None:
        if selected is not None and 0 <= selected < len(effective):
            effective[selected] = draft
        else:
            effective.append(draft)
    bore_warning = _capped_bore_warning(stack_request, layout, effective, payload.get("space"))
    return {
        "design": canonical,
        "planning": planning,
        "bore_ceiling_warning": bore_warning,
        "storage_box_height_warning": storage_box_height_warning,
        "stack": stack_block,
        "label_outline": scene["label_outline"],
        "label_meta": scene["label_meta"],
        "text_meta": scene["text_meta"],
        "geometry": geometry,
        "pick_proxies": scene.get("pick_proxies", []),
        "fits": scene["fits"],
        "message": scene["message"],
        "feature_errors": scene["feature_errors"],
        "invalid_feature_indexes": scene["invalid_feature_indexes"],
        "draft_error": scene["draft_error"],
        "feature_overhang_mm": scene["feature_overhang_mm"],
        "draft_overhang_mm": scene["draft_overhang_mm"],
        "dimensions": {
            "size": scene["size_text"],
            "inside_x": scene.get("inside_x"),
            "inside_y": scene.get("inside_y"),
        },
        "layout_bounds": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        # The true, wavy interior wall - Z-invariant, so one outline covers
        # the whole cavity - shown in the 2D layout so a full-span divider's
        # fit against the real wall is visible, not just against the flat
        # placement rectangle every other support is confined to.
        "cavity_outline": [[float(x), float(y)] for x, y in cavity.exterior.coords],
        "customization_zones": [
            {"name": name, "zone": [zone.x0, zone.y0, zone.x1, zone.y1]}
            for name, zone in scene["customization_zones"]
        ],
        # The floor each support actually covers, which for a fused cradle,
        # post or divider is smaller than the zone it is drawn in. The 2D
        # layout fills this and outlines the zone around it, so the open floor
        # a neighbour may now use is visible rather than implied.
        "feature_footprints": [
            _footprint_bounds(box, one, layout.mode) for one in layout.features
        ],
        "draft_footprint": _footprint_bounds(box, draft, layout.mode),
        "feature_outlines": [
            ([[float(x), float(y)] for x, y in nest_contour_polygon(one).exterior.coords]
             if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        # The Soften-outline result in each nest's own local millimetres, so the
        # 2D layout can apply its own cheap move/rotate/resize and still draw
        # the exact silhouette the printed cutter gets.
        "nest_soft_contours": [
            ([list(point) for point in nest_smoothed_contour(one)]
             if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        "draft_soft_contour": (
            [list(point) for point in nest_smoothed_contour(draft)]
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
        "nest_occurrences": [
            nest_occurrence_preview(one) if one.kind == "nest" and one.contour else None
            for one in layout.features
        ],
        "draft_nest_occurrences": (
            nest_occurrence_preview(draft)
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
        # Informational-only 2D indicators for the resolved finger-access plan
        # - a notch location on Raised Wall, a scoop footprint on Recessed.
        "nest_access": [
            (nest_access_preview(one) if one.kind == "nest" and one.contour else None)
            for one in layout.features
        ],
        "draft_nest_access": (
            nest_access_preview(draft)
            if draft is not None and draft.kind == "nest" and draft.contour else None
        ),
    }


def _capped_bore_violation(
    box: BoxSpec, layout: Layout, features: list[Feature] | tuple[Feature, ...], cap_z: float,
) -> tuple[int, float] | None:
    """Evaluate Bore objects against the same physical body used by preview."""
    physical_box = _interior_work_box(box)
    base_z = base_height(physical_box, layout.mode)
    for index, feature in enumerate(features):
        if feature.kind != "bore" or feature.item is None:
            continue
        try:
            top = bore_reference_top(physical_box, feature, base_z)
        except (KeyError, TypeError, ValueError):
            continue
        if top > cap_z + 1e-6:
            return index, top
    return None


def _capped_bore_warning(
    box: BoxSpec, layout: Layout, features: list[Feature] | tuple[Feature, ...], raw_space: Any,
) -> dict[str, Any] | None:
    cap_z = _capped_space_height(raw_space)
    if cap_z is None:
        return None
    violation = _capped_bore_violation(box, layout, features, cap_z)
    if violation is None:
        return None
    _index, top = violation
    return {"top_mm": math.ceil(top * 1000) / 1000, "cap_mm": cap_z,
            "space_kind": _ai_space_context(raw_space)["kind"]}


ROUTES = {"/api/preview": preview_payload}
