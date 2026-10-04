"""Wavefinity preview geometry and customization validation."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    BoxSpec,
    make_scoop,
    make_top_label_ledge,
    make_lift_grabbers,
    lift_grabber_collision_volumes,
    lid_stackable,
    preview_rings,
    make_box,
    flat_cavity_polygon,
    scoop_keep_out,
    top_label_outline,
    top_label_report,
    top_label_surface_z,
    top_label_zone,
    translated,
    difference,
)
from organizer_edge_mount import (
    apply_edge_mount_hole_cuts,
    apply_edge_mount_structure,
    edge_mount_summary,
    edge_mount_text_object,
    make_edge_mount_label_part,
)
from organizer_side_openings import (
    apply_side_openings,
    side_opening_summary,
    validate_side_openings,
)
from organizer_pegboard import apply_pegboard_mount_structure, receiver_layout
from organizer_stack import stack_enabled
from organizer_inserts._bore import bore_reference_meshes, bore_tool_clearance_zone
from organizer_inserts._cradle import cradle_reference_meshes
from organizer_inserts import (
    CRADLE_FLOOR_GAP,
    MIN_FEATURE_GAP,
    Feature,
    Layout,
    Zone,
    apply_texts,
    bore_hole_axes,
    build_features,
    connector_keep_out,
    divider_division_texts,
    feature_footprint,
    insert_footprint,
    is_text,
    layout_to_dict,
    layout_zone,
    make_insert_plate,
    occupied_zones,
    nest_contour_polygon,
    resolve_nest_settings,
    resolve_text_features,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)
from .._common import (
    SURFACE_BASE_CELL_MM,
    SURFACE_BASE_TOP_SKIN_MM,
    SURFACE_BASE_CELL_INSET_MM,
    SURFACE_BASE_MIN_OPENING_MM,
    SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM,
    label_position,
    rim_label_side,
    validate_scoop_lift_grabbers,
    validate_side_opening_label,
    validate_edge_mount_label_conflicts,
    clean_label,
    base_height,
    _text_fits,
    _canonical_rim_label,
)

import math
from typing import Iterable
import numpy as np
import trimesh
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry import box as shape_box

from ._helpers import (
    _feature_height,
    _prism_geometry,
    _bore_axis_geometry,
    _valid_preview_floor_ring,
    _floor_faces_with_text_pockets,
    PREVIEW_DECIMALS,
    PREVIEW_MIN_FACE_AREA,
    _mesh_preview_geometry,
    _reference_preview_meshes,
    bore_reference_envelope_extensions,
    _customization_zones,
    validate_inside_handles_mode,
    _feature_z_range,
    inside_handle_conflict,
    _scoop_floor_bounds,
    _removable_scoop,
    _surface_base_cutter,
    apply_surface_lightweight_base,
    _preview_base_texts,
    insert_plate_solid,
    validate_customization_clearance,
    validate_rim_text_divider_clearance,
)

def preview_geometry(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused", label_location: str = "bottom", scoop: bool = False,
    draft: Feature | None = None, selected: int | None = None,
    layout: Layout | None = None,
) -> dict[str, object]:
    """Build camera-independent preview geometry once per design change.

    ``draft`` is the interior part currently being edited, not yet added to
    the layout - included in the same geometry, tagged ``draft_<kind>``
    instead of ``feature_<kind>``/``insert_<kind>`` so the browser can
    highlight it in place, right where it will actually sit, instead of
    drawing it alone on its own tiny canvas. It never affects
    ``feature_errors`` or ``invalid_feature_indexes`` - those describe the
    real layout - and a draft that fails to build still falls back to the
    same placeholder prism a placed feature would, reported through
    ``draft_error`` instead.
    """
    migrated, label, label_location = _canonical_rim_label(
        box, Layout(tuple(features), mode), label, label_location,
    )
    features = migrated.features
    effective_features = list(features)
    if draft is not None:
        if selected is not None and 0 <= selected < len(effective_features):
            effective_features[selected] = draft
        else:
            effective_features.append(draft)
    active_rim = tuple(one for one in effective_features if is_text(one) and one.options.get("level") == "rim")
    validate_inside_handles_mode(box, mode)
    validate_scoop_lift_grabbers(box, scoop)
    validate_side_openings(box)
    for rim_text in active_rim:
        side = str(rim_text.options.get("rim_side") or "back")
        validate_side_opening_label(box, text_of(rim_text), side)
        validate_edge_mount_label_conflicts(box, text_of(rim_text), side)
        handle_conflict = inside_handle_conflict(box, rim_text, base_height(box, mode), mode)
        if handle_conflict:
            raise ValueError(f"rim Text on {side} overlaps the {handle_conflict}; choose another rim side")
    if not active_rim:
        validate_edge_mount_label_conflicts(box, "", "bottom")   # lid / stack rules need no label

    features = resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, clean_label(label), label_position(label_location), scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )
    validate_rim_text_divider_clearance(box, effective_features, base_height(box, mode))
    outer, cavity = preview_rings(box)
    floor_cavity = _valid_preview_floor_ring(cavity)
    floor_z, rim_z = box.base_thickness, box.z
    geometry: list[tuple[list[tuple[float, float, float]], str,
                          tuple[float, float, float], int, str | None]] = []
    # Preview-only identities. Geometry keeps its physical base/lid owner.
    pick_faces: dict[int, dict[str, object]] = {}
    pick_proxies: list[dict[str, object]] = []

    tidy = clean_label(label)
    location = label_position(label_location)
    rim_side = rim_label_side(location)
    # A fused feature, the scoop, the rim ledge and a live draft each get cut
    # by this below wherever they cross a Screw Mounting hole, so together
    # they show the same physical result as export - without merging any of
    # them into the bin shell's own "outside" geometry, which would misclass
    # interior-part geometry as Bin geometry and break Bin/Interior/Xray.
    cut_fused_pieces = mode == "fused" and box.edge_mount.holes_enabled
    cut_side_opening_pieces = mode == "fused" and box.side_openings.enabled

    # Inlaid base Text: the solids that pocket the receiving surface in preview,
    # exactly as export cuts them (bin shell when fused, insert plate otherwise).
    from organizer_inserts._text import build_text
    base_inlay_meshes = []
    text_pocket_error = None
    for one in _preview_base_texts(features, draft, selected):
        try:
            base_inlay_meshes.extend(build_text(box, one, base_height(box, mode)))
        except Exception:
            continue

    if (box.edge_mount.active or box.side_openings.enabled or box.pegboard.enabled
            or (layout is not None and layout.surface_lightweight_base)):
        # make_box() already includes Lift Grabbers; Edge Mount also adds the
        # Projecting Label plate and cuts the shell's own small screw holes
        # and driver-access openings. Side Openings cut the finished shell
        # last, so the real cut body - not a synthesized wall - is what
        # shows in preview here.
        shell_body = make_box(box)
        if box.edge_mount.active:
            shell_body = apply_edge_mount_structure(box, shell_body)
        if box.pegboard.enabled:
            shell_body = apply_pegboard_mount_structure(box, shell_body)
        if mode == "fused" and base_inlay_meshes:
            try:
                shell_body = apply_texts(
                    shell_body, [("", mesh, False) for mesh in base_inlay_meshes])
            except Exception as error:
                text_pocket_error = f"text pocket: {error}"
        if layout is not None:
            shell_body = apply_surface_lightweight_base(shell_body, box, layout)
        if box.side_openings.enabled:
            shell_body = apply_side_openings(box, shell_body)
        geometry.extend(_mesh_preview_geometry(shell_body, "outside"))
    else:
        count = len(outer)
        for index in range(count):
            a, b = outer[index], outer[(index + 1) % count]
            c, d = cavity[index], cavity[(index + 1) % count]
            run = (b[0] - a[0], b[1] - a[1])
            outward = (run[1], -run[0], 0.0)
            inward = (-run[1], run[0], 0.0)
            geometry.append(([(a[0], a[1], 0.0), (b[0], b[1], 0.0),
                              (b[0], b[1], rim_z), (a[0], a[1], rim_z)],
                             "outside", outward, 0, None))
            geometry.append(([(c[0], c[1], floor_z), (d[0], d[1], floor_z),
                              (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                             "inside", inward, 0, None))
            geometry.append(([(a[0], a[1], rim_z), (b[0], b[1], rim_z),
                              (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                             "rim", (0.0, 0.0, 1.0), 0, None))
        floor_outlines = []
        if mode == "fused":
            for one in _preview_base_texts(features, draft, selected):
                try:
                    floor_outlines.append(text_placed_outline(one))
                except Exception:
                    continue
        if floor_outlines:
            geometry.extend(_floor_faces_with_text_pockets(
                floor_cavity, floor_z, floor_outlines))
        else:
            geometry.append(([(*point, floor_z) for point in floor_cavity],
                             "floor", (0.0, 0.0, 1.0), 1, None))

    if tidy and rim_side:
        ledge_mesh = make_top_label_ledge(box, rim_side)
        if cut_fused_pieces:
            ledge_mesh = apply_edge_mount_hole_cuts(box, ledge_mesh, geometry_owner="rim-label ledge")
        if cut_side_opening_pieces:
            ledge_mesh = apply_side_openings(box, ledge_mesh)
        geometry.extend(_mesh_preview_geometry(ledge_mesh, "top_label_ledge"))
    if scoop:
        scoop_mesh = (
            make_scoop(box)
            if mode == "fused"
            else translated(
                _removable_scoop(box, mode),
                (0.0, 0.0, box.base_thickness),
            )
        )
        # The scoop is fused into the shell, so a hole crossing it should show
        # cut here too. A removable-mode scoop belongs to the insert, which
        # Edge Mount never drills and Side Openings never cut.
        if cut_fused_pieces:
            scoop_mesh = apply_edge_mount_hole_cuts(box, scoop_mesh, geometry_owner="fused scoop")
        if cut_side_opening_pieces:
            scoop_mesh = apply_side_openings(box, scoop_mesh)
        geometry.extend(_mesh_preview_geometry(scoop_mesh, "scoop"))
    # make_box() already bakes lift grabbers into the shell it returns, so
    # only draw them separately when the Edge Mount/Side Openings shell above
    # did not already include them.
    if box.lift_grabbers.enabled and not box.edge_mount.active and not box.side_openings.enabled:
        for grabber_mesh in make_lift_grabbers(box):
            geometry.extend(_mesh_preview_geometry(grabber_mesh, "lift_grabber"))

    plate = insert_plate_solid(box, mode)
    if plate is not None:
        if mode != "fused" and base_inlay_meshes:
            try:
                plate = apply_texts(
                    plate, [("", mesh, False) for mesh in base_inlay_meshes])
            except Exception as error:
                if text_pocket_error is None:
                    text_pocket_error = f"text pocket: {error}"
        geometry.extend(_mesh_preview_geometry(plate, "insert_base"))
    base_z = base_height(box, mode)
    # Holders belong to whichever part they are printed as: the bin when fused,
    # the insert otherwise.  The prefix picks the colour family.
    part_kind = "feature" if mode == "fused" else "insert"
    feature_errors = []
    if text_pocket_error is not None:
        feature_errors.append(text_pocket_error)
    invalid_feature_indexes = []
    conflicting_feature_indexes = []
    feature_overhang_mm = [0.0 for _ in features]
    draft_overhang_mm = 0.0
    draft_error = None
    destinations = {}
    for index, one in enumerate(features):
        if not is_text(one):
            continue
        destination = "rim" if one.options.get("level") == "rim" else "base"
        if destination in destinations:
            feature_errors.append(
                "Only one rim Text is allowed; remove a duplicate" if destination == "rim"
                else "Only one Text is allowed on the base; remove a duplicate"
            )
            invalid_feature_indexes.extend((destinations[destination], index))
        destinations[destination] = index
    if draft is not None and is_text(draft):
        destination = "rim" if draft.options.get("level") == "rim" else "base"
        if destination in destinations and destinations[destination] != selected:
            draft_error = (
                "Only one rim Text is allowed; change the existing rim Text or use Base Text" if destination == "rim"
                else "Only one Text is allowed on the base; change Style or remove the other Text"
            )
    reserved = _customization_zones(box, tidy, location, scoop, mode)

    occupied = [
        None if (is_text(one) and one.options.get("level") == "rim") else zone
        for one, zone in zip(features, occupied_zones(box, features, base_z, mode))
    ]
    preview_bore_tool_paths: dict[int, Zone | None] = {}

    def preview_bore_tool_path(one: Feature) -> Zone | None:
        if one.kind != "bore":
            return None
        key = id(one)
        if key not in preview_bore_tool_paths:
            preview_bore_tool_paths[key] = bore_tool_clearance_zone(box, one, base_z)
        return preview_bore_tool_paths[key]

    def floor_overlap(a: Feature, a_zone: Zone, b: Feature, b_zone: Zone) -> bool:
        if (
            a.kind == "bore"
            and b.kind in ("divider", "post")
            and preview_bore_tool_path(a) is not None
            and preview_bore_tool_path(a).overlaps(feature_footprint(box, b, base_z))
        ) or (
            b.kind == "bore"
            and a.kind in ("divider", "post")
            and preview_bore_tool_path(b) is not None
            and preview_bore_tool_path(b).overlaps(feature_footprint(box, a, base_z))
        ):
            return True
        if mode == "fused" and (is_text(a) or is_text(b)):
            a_shape = text_placed_outline(a) if is_text(a) else a_zone.polygon
            b_shape = text_placed_outline(b) if is_text(b) else b_zone.polygon
            return a_shape.distance(b_shape) < MIN_FEATURE_GAP
        return a_zone.overlaps(b_zone, MIN_FEATURE_GAP)

    if draft is not None:
        if not (is_text(draft) and draft.options.get("level") == "rim"):
            draft_customization_footprint = feature_footprint(box, draft, base_z)
            conflict = next(
                (name for name, zone in reserved if
                 ((text_placed_outline(draft) if is_text(draft) else draft_customization_footprint.polygon)
                  .distance(zone.polygon) < MIN_FEATURE_GAP)),
                None,
            )
            if conflict is not None:
                draft_error = f"{draft.kind}: overlaps the {conflict}"
            else:
                handle_conflict = inside_handle_conflict(box, draft, base_z, mode)
                if handle_conflict is not None:
                    draft_error = f"{draft.kind}: overlaps the {handle_conflict}"
            if draft_error is None:
                try:
                    draft_occ = occupied_zones(box, (draft,), base_z, mode)[0]
                    for idx, one_occ in enumerate(occupied):
                        if one_occ is None:
                            continue
                        if selected is not None and idx == selected:
                            continue
                        if not floor_overlap(draft, draft_occ, features[idx], one_occ):
                            continue
                        conflicting_feature_indexes.append(idx)
                        if draft_error is None:
                            draft_error = (
                                    f"a {draft.kind} and a {features[idx].kind} overlap; "
                                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                                )
                except Exception:
                    pass

    for i, one_occ in enumerate(occupied):
        if one_occ is None:
            continue
        if selected is not None and i == selected and draft is not None:
            continue
        for j in range(i + 1, len(occupied)):
            if occupied[j] is None:
                continue
            if selected is not None and j == selected and draft is not None:
                continue
            if floor_overlap(features[i], one_occ, features[j], occupied[j]):
                feature_errors.append(
                    f"a {features[i].kind} and a {features[j].kind} overlap; "
                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                )
                if i not in invalid_feature_indexes:
                    invalid_feature_indexes.append(i)
                if j not in invalid_feature_indexes:
                    invalid_feature_indexes.append(j)

    # Recessed Photo Nests share one physical deck. Build every saved recessed
    # Nest plus a participating live draft as one effective group, so editing
    # a saved Nest cannot briefly refill the other Nest cavities with a second
    # deck and a new Recessed draft is visible before it is saved.
    grouped_recessed = {
        index for index, one in enumerate(features)
        if one.kind == "nest" and one.contour
        and str(resolve_nest_settings(box, one, base_z)["holder_style"]) == "recessed"
    }
    draft_in_recessed_group = (
        draft is not None and draft.kind == "nest" and bool(draft.contour)
        and str(resolve_nest_settings(box, draft, base_z)["holder_style"]) == "recessed"
    )
    effective_recessed = []
    represented_recessed = set()
    draft_in_group = False
    for index in sorted(grouped_recessed):
        if index == selected and draft is not None:
            if draft_in_recessed_group:
                effective_recessed.append(draft)
                represented_recessed.add(index)
                draft_in_group = True
            continue
        effective_recessed.append(features[index])
        represented_recessed.add(index)
    if draft_in_recessed_group and not draft_in_group:
        effective_recessed.append(draft)
        draft_in_group = True
    if effective_recessed:
        try:
            built = build_features(
                box, effective_recessed, base_z, layout_zone(box, mode), mode=mode,
                include_text=True,
            )
            if built:
                top_z = max(float(solid.bounds[1][2]) for solid in built)
                for index in represented_recessed:
                    feature_overhang_mm[index] = round(max(0.0, top_z - box.z), 3)
                if draft_in_group:
                    draft_overhang_mm = round(max(0.0, top_z - box.z), 3)
                # The deck is one shared solid; it cannot have one truthful
                # feature owner. Invisible contours give each Nest its own pick.
                for index in represented_recessed:
                    if index == selected and draft_in_group:
                        continue
                    polygon = nest_contour_polygon(features[index], include_clearance=True)
                    pick_proxies.append({
                        "points": [(float(x), float(y), top_z + 0.02)
                                   for x, y in polygon.exterior.coords[:-1]],
                        "pick": {"type": "saved", "index": index},
                    })
                if draft_in_group:
                    polygon = nest_contour_polygon(draft, include_clearance=True)
                    pick_proxies.append({
                        "points": [(float(x), float(y), top_z + 0.02)
                                   for x, y in polygon.exterior.coords[:-1]],
                        "pick": {"type": "draft"},
                    })
            for solid in built:
                if cut_fused_pieces:
                    solid = apply_edge_mount_hole_cuts(
                        box, solid, geometry_owner="recessed Photo Nest group")
                if cut_side_opening_pieces:
                    solid = apply_side_openings(box, solid)
                geometry.extend(_mesh_preview_geometry(solid, f"{part_kind}_nest"))
        except Exception as error:
            for index in represented_recessed:
                feature_errors.append(f"nest: {error}")
                if index not in invalid_feature_indexes:
                    invalid_feature_indexes.append(index)
                if index == selected and draft_in_group:
                    continue
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    features[index].zone, base_z,
                    min(box.z - 0.25, _feature_height(box, features[index], base_z)),
                    f"{part_kind}_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "saved", "index": index}
            if draft_in_group:
                draft_error = f"nest: {error}"
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone, base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}

    for feature_index, one in enumerate(features):
        if selected is not None and feature_index == selected and draft is not None:
            continue
        if is_text(one) and one.options.get("level") == "rim":
            try:
                from organizer_inserts._text import rim_text_geometry
                ledge, glyph, _cap, _surface = rim_text_geometry(box, one)
                if not text_is_raised(one):
                    try:
                        ledge = difference([ledge, glyph])
                    except Exception as pocket_error:
                        feature_errors.append(f"text pocket: {pocket_error}")
                for mesh, kind in ((ledge, "top_label_ledge"), (glyph, "feature_text")):
                    start = len(geometry)
                    faces = _mesh_preview_geometry(mesh, kind)
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "saved", "index": feature_index}
            except Exception as error:
                feature_errors.append(f"text: {error}")
                invalid_feature_indexes.append(feature_index)
            continue
        if selected is not None and feature_index == selected and draft is not None:
            continue
        # Same actual-footprint rule as validate_customization_clearance(): a
        # default divider's zone can span the floor even though its printed
        # wall is a narrow strip, so judge against what is really built.
        # Use the actual footprint regardless of mode (do not reuse ``occupied``
        # which intentionally keeps full zones in non-fused mode for feature-vs-
        # feature layout, not customization collision).
        customization_footprint = feature_footprint(box, one, base_z)
        conflict = next(
            (name for name, zone in reserved if
             ((text_placed_outline(one) if is_text(one) else customization_footprint.polygon)
              .distance(zone.polygon) < MIN_FEATURE_GAP)),
            None,
        )
        if conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {conflict}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)
        handle_conflict = inside_handle_conflict(box, one, base_z, mode)
        if handle_conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {handle_conflict}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)

        if feature_index in represented_recessed:
            continue

        is_conflicting = feature_index in conflicting_feature_indexes
        is_invalid = feature_index in invalid_feature_indexes

        if is_invalid:
            tag = f"{part_kind}_invalid"
        elif is_conflicting:
            tag = f"{part_kind}_conflict_{one.kind}"
        else:
            tag = f"{part_kind}_{one.kind}"

        try:
            built = build_features(
                box, [one], base_z, layout_zone(box, mode), mode=mode,
                include_text=True,
            )
            if built:
                top_z = max(float(solid.bounds[1][2]) for solid in built)
                feature_overhang_mm[feature_index] = round(
                    max(0.0, top_z - box.z), 3,
                )
            for solid in built:
                layer = solid.metadata.get("wavefinity_preview_layer")
                # Export never cuts a text object with the driver-access
                # tunnel (it is a separate part cut in only at its own
                # pocket), so leave text features out of this - every other
                # fused feature is real body material and gets cut exactly
                # like the shell, scoop and rim ledge above.
                if cut_fused_pieces and not is_text(one):
                    solid = apply_edge_mount_hole_cuts(
                        box, solid, geometry_owner=f"{one.kind} feature")
                if cut_side_opening_pieces and not is_text(one):
                    solid = apply_side_openings(box, solid)
                if layer:
                    solid.metadata["wavefinity_preview_layer"] = layer
                start = len(geometry)
                faces = _mesh_preview_geometry(solid, tag)
                geometry.extend(faces)
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "saved", "index": feature_index}
        except Exception as error:
            feature_errors.append(f"{one.kind}: {error}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)
            start = len(geometry)
            geometry.extend(_prism_geometry(
                one.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, one, base_z)),
                f"{part_kind}_invalid",
            ))
            for face_index in range(start, len(geometry)):
                pick_faces[face_index] = {"type": "saved", "index": feature_index}
        geometry.extend(_bore_axis_geometry(
            box, one, base_z, f"{part_kind}_bore_axis"
        ))

    if draft is not None and not draft_in_group:
        cut_draft = cut_fused_pieces and not is_text(draft)
        cut_draft_side_opening = cut_side_opening_pieces and not is_text(draft)
        if draft_error is not None:
            built = False
            try:
                solids = build_features(box, [draft], base_z, layout_zone(box, mode),
                                        mode=mode, include_text=True)
                if is_text(draft) and draft.options.get("level") == "rim":
                    from organizer_inserts._text import rim_text_geometry
                    draft_ledge, draft_glyph, _cap, _surface = rim_text_geometry(box, draft)
                    if not text_is_raised(draft):
                        try:
                            draft_ledge = difference([draft_ledge, draft_glyph])
                        except Exception as pocket_error:
                            # Only the pocket boolean failed; record it on the
                            # draft-error channel, keep any primary error, and
                            # still draw the uncut ledge.
                            if draft_error is None:
                                draft_error = f"text pocket: {pocket_error}"
                    solids = [draft_ledge, *solids]
                if solids:
                    draft_overhang_mm = round(max(
                        0.0, max(float(s.bounds[1][2]) for s in solids) - box.z,
                    ), 3)
                for solid in solids:
                    layer = solid.metadata.get("wavefinity_preview_layer")
                    if cut_draft:
                        solid = apply_edge_mount_hole_cuts(
                            box, solid, geometry_owner=f"{draft.kind} draft")
                    if cut_draft_side_opening:
                        solid = apply_side_openings(box, solid)
                    if layer:
                        solid.metadata["wavefinity_preview_layer"] = layer
                    start = len(geometry)
                    faces = _mesh_preview_geometry(solid, "draft_invalid")
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "draft"}
                built = True
            except Exception:
                pass
            if not built:
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}
        else:
            try:
                solids = build_features(box, [draft], base_z, layout_zone(box, mode),
                                        mode=mode, include_text=True)
                if is_text(draft) and draft.options.get("level") == "rim":
                    from organizer_inserts._text import rim_text_geometry
                    draft_ledge, draft_glyph, _cap, _surface = rim_text_geometry(box, draft)
                    if not text_is_raised(draft):
                        try:
                            draft_ledge = difference([draft_ledge, draft_glyph])
                        except Exception as pocket_error:
                            # Only the pocket boolean failed; record it on the
                            # draft-error channel, keep any primary error, and
                            # still draw the uncut ledge.
                            if draft_error is None:
                                draft_error = f"text pocket: {pocket_error}"
                    solids = [draft_ledge, *solids]
                if solids:
                    draft_overhang_mm = round(max(
                        0.0, max(float(s.bounds[1][2]) for s in solids) - box.z,
                    ), 3)
                for solid in solids:
                    layer = solid.metadata.get("wavefinity_preview_layer")
                    if cut_draft:
                        solid = apply_edge_mount_hole_cuts(
                            box, solid, geometry_owner=f"{draft.kind} draft")
                    if cut_draft_side_opening:
                        solid = apply_side_openings(box, solid)
                    if layer:
                        solid.metadata["wavefinity_preview_layer"] = layer
                    start = len(geometry)
                    faces = _mesh_preview_geometry(solid, f"draft_{draft.kind}")
                    geometry.extend(faces)
                    for face_index in range(start, len(geometry)):
                        pick_faces[face_index] = {"type": "draft"}
            except Exception as error:
                draft_error = f"{draft.kind}: {error}"
                start = len(geometry)
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
                for face_index in range(start, len(geometry)):
                    pick_faces[face_index] = {"type": "draft"}
        geometry.extend(_bore_axis_geometry(box, draft, base_z, "draft_bore_axis"))

    # The rim label is the only lettering left that is not an interior part:
    # it sits on a shelf at the selected rim side and has no zone to drag, so the
    # preview still draws it here. Floor text drew itself above, with every
    # other interior part.
    fits, message = True, ""
    label_outline_coords = []
    label_meta = None
    side = rim_label_side(location)
    if tidy and side:
        try:
            label_info = top_label_report(box, tidy, side)
            outline = top_label_outline(box, tidy, side)
            label_meta = {
                "location": location,
                "side": side,
                "cap_height": label_info["cap_height_mm"],
                "warning": label_info.get("warning"),
            }
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
            label_outline_coords = [
                [[float(x), float(y)] for x, y in piece.exterior.coords]
                for piece in pieces
            ]
            label_z = top_label_surface_z(box)
            for piece in pieces:
                geometry.append(([(x, y, label_z) for x, y in piece.exterior.coords],
                                 "label", (0.0, 0.0, 1.0), 2, None))
                for ring in piece.interiors:
                    geometry.append(([(x, y, label_z) for x, y in ring.coords],
                                     "label_hole", (0.0, 0.0, 1.0), 3, None))

    edge_mount_meta = None
    if box.edge_mount.active:
        edge_mount_meta = edge_mount_summary(box)
        if box.edge_mount.label_enabled and box.edge_mount.label_type == "separate":
            separate_label = make_edge_mount_label_part(box)
            if separate_label is not None:
                geometry.extend(_mesh_preview_geometry(separate_label, "edge_mount"))
        edge_text = edge_mount_text_object(box)
        if edge_text is not None:
            _edge_label, edge_mesh, _edge_raised = edge_text
            geometry.extend(_mesh_preview_geometry(edge_mesh, "label"))

    side_openings_meta = side_opening_summary(box) if box.side_openings.enabled else None
    pegboard_meta = receiver_layout(box) if box.pegboard.enabled else None

    # The effective list has already replaced a selected saved part with its
    # live draft. These faces never enter any printable builder or pick map.
    for one in effective_features:
        try:
            for mesh in _reference_preview_meshes(box, one, base_z):
                geometry.extend(_mesh_preview_geometry(mesh, "reference_object"))
        except Exception:
            pass

    inside_x, inside_y = box.usable_opening
    return {
        "geometry": geometry,
        "pick_faces": pick_faces,
        "pick_proxies": pick_proxies,
        "fits": fits,
        "message": message,
        "feature_errors": tuple(feature_errors),
        "invalid_feature_indexes": tuple(invalid_feature_indexes),
        "conflicting_feature_indexes": tuple(conflicting_feature_indexes),
        "draft_error": draft_error,
        "feature_overhang_mm": tuple(feature_overhang_mm),
        "draft_overhang_mm": draft_overhang_mm,
        "customization_zones": tuple(reserved),
        "label_outline": label_outline_coords,
        "label_meta": label_meta,
        "edge_mount": edge_mount_meta,
        "side_openings": side_openings_meta,
        "pegboard": pegboard_meta,
        # Where each text interior part ended up, so the browser can show the
        # resolved letter height an auto or zone-fitted one landed on.
        "text_meta": tuple(
            {
                "index": index,
                "text": text_of(one),
                "auto": bool(one.options.get("auto")),
                "cap_height": round(text_fitted(one)[0], 3),
            }
            for index, one in enumerate(features)
            if is_text(one) and _text_fits(one)
        ),
        "features": layout_to_dict(Layout(features, mode))["features"],
        "inside_x": math.floor(inside_x),
        "inside_y": math.floor(inside_y),
        "size_text": (
            f"{math.floor(inside_x):g} X {math.floor(inside_y):g} (Inside) - "
            f"{box.x:g} X {box.y:g} mm (Outside)"
        ),
    }
