"""Shared geometry/export services and command-line tools for Wavefinity."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    BASE_UNIT,
    B4BSpec,
    BoxSpec,
    ConnectorSpec,
    EdgeMountSpec,
    EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
    LidSpec,
    StackSpec,
    LiftGrabberSpec,
    SideOpeningSpec,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_WALL,
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    GRID_PITCH,
    MAX_WALL,
    MIN_WALL,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    DEFAULT_ARM_THICKNESS,
    export_labelled_box,
    export_text_body_3mf,
    export_mesh,
    connector_for_print,
    generate_sampler,
    label_report,
    label_placement,
    make_scoop,
    make_top_label_ledge,
    make_top_labelled_box,
    make_labelled_box,
    make_lift_grabbers,
    lift_grabber_collision_volumes,
    lift_grabber_summary,
    lid_enabled,
    lid_label_relief_mm,
    lid_spec,
    lid_stackable,
    direct_stack_enabled,
    placed_label_outline,
    preview_rings,
    make_box,
    flat_cavity_polygon,
    make_side_connector,
    make_corner_connector,
    label_mesh_report,
    export_bambu_compatible_3mf,
    measure_lock,
    max_wave_slope,
    mesh_report,
    scoop_dimensions,
    scoop_floor_zone,
    scoop_keep_out,
    LIFT_GRABBER_RIM_CLEARANCE,
    top_label_outline,
    top_label_report,
    top_label_surface_z,
    top_label_zone,
    translated,
    union,
    difference,
    validate_side_fit,
    validate_corner_fit,
    validate_3mf,
    export_object_groups_3mf,
    validate_object_groups_3mf,
)
from organizer_edge_mount import (
    apply_edge_mount_hole_cuts,
    apply_edge_mount_structure,
    edge_mount_summary,
    edge_mount_text_object,
    make_edge_mount_label_part,
)
from organizer_side_openings import (
    SIDE_OPENING_TOP_BRIDGE_MM,
    apply_side_openings,
    side_opening_summary,
    validate_side_openings,
)
from organizer_pegboard import (
    PegboardMountSpec,
    apply_pegboard_mount_structure,
    make_board_adapters,
    normalise_mount_spec,
    pegboard_standard,
    receiver_layout,
)
from organizer_b4b import (
    b4b_build_print_objects,
    b4b_effective_box,
    b4b_summary,
    validate_b4b_design,
)
from organizer_stack import (
    make_lid_parts,
    make_stack_lid,
    normalize_stack_settings,
    stack_closed_height,
    stack_effective_box,
    stack_enabled,
    stack_spec,
    stack_step_depth,
    stack_summary,
    validate_stack_design,
)
from organizer_inventory import append_bin
from organizer_inserts._bore import bore_reference_meshes, bore_tool_clearance_zone
from organizer_inserts._cradle import cradle_reference_meshes
from organizer_inserts import (
    CRADLE_FLOOR_GAP,
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    EDITOR_SNAP,
    FEATURE_BUILDERS,
    HEX_BIT_HOLD,
    TEXT_KIND,
    _cradle_rib_thickness,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Zone,
    apply_texts,
    bore_hole_axes,
    normalize_bore_modes,
    build_features,
    build_texts,
    connector_keep_out,
    divider_cells,
    divider_division_texts,
    feature_footprint,
    feature_definitions,
    insert_footprint,
    insert_report,
    is_text,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    make_cartridge_insert,
    make_fitted_insert,
    make_fused_box,
    fitted_nest_feature,
    make_insert_plate,
    normalize_divider_scoop,
    occupied_zones,
    nest_contour_polygon,
    resolve_nest_settings,
    resolve_text_features,
    resolved_options,
    snapped_zone,
    scoop_zone,
    text_depth,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)

import argparse
from dataclasses import replace
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import sys
import tempfile
import trimesh

from organizer_app_impl._common import (
    SURFACE_BASE_CELL_MM,
    SURFACE_BASE_TOP_SKIN_MM,
    SURFACE_BASE_CELL_INSET_MM,
    SURFACE_BASE_MIN_OPENING_MM,
    SURFACE_BASE_BOOLEAN_OVERTRAVEL_MM,
    DEFAULT_SAMPLE_BOXES,
    _FEATURE_DEFINITIONS,
    INTERIOR_PART_CATALOG,
    INTERIOR_PART_ORDER,
    LABEL_POSITIONS,
    label_position,
    rim_label_side,
    validate_scoop_lift_grabbers,
    validate_side_opening_label,
    validate_edge_mount_label_conflicts,
    PART_KINDS,
    PART_KIND_INFO,
    ILLEGAL_IN_FILENAMES,
    clean_label,
    base_height,
    _text_fits,
    _canonical_rim_label,
)
from organizer_app_impl._preview import (
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
    preview_geometry,
)
from organizer_app_impl._filenames import (
    _box_spec,
    _connector_spec,
    _part_result,
    box_filename,
    edge_mount_label_filename,
    pegboard_adapter_filename,
    lid_filename,
    stack_lid_filename,
    lid_label_regions,
    insert_filename,
    connector_filename,
    CORNER_WAYS_NAMES,
    MAX_CORNER_QUANTITY,
    CORNER_COPY_GAP,
    corner_connector_filename,
    validate_corner_quantity,
    arrange_connector_copies,
    SIZE_LIKE,
    part_name_seed,
)
from organizer_app_impl._design_io import (
    _b4b_log_note,
    summarize_interior_parts,
    inventory_bin_record,
    object_height_plan,
    _starter_span,
    default_feature,
    auto_text_feature,
    convert_layout_mode,
    design_to_dict,
    design_from_dict,
    design_source_payload,
)
from organizer_app_impl._generation import (
    generate_box_file,
    text_report,
    b4b_filename,
    BIN_STAGE_PREFIX,
    BIN_BACKUP_PREFIX,
    _validate_staged_file,
    _promote_staged_set,
    _rewrite_staged_paths,
    log_bin_to_folder,
    generate_side_file,
    generate_corner_file,
    generate_kit_files,
)
from organizer_app_impl._cli import (
    parse_sizes,
    add_box_arguments,
    add_connector_arguments,
    build_parser,
)

APP_DIR = Path(__file__).resolve().parent


def generate_b4b_files(
    box: BoxSpec,
    output_dir: Path,
    part_name: str = "",
    auto_timestamp: bool = False,
    keep_log: bool = False,
    *,
    features=(),
) -> dict[str, object]:
    """Dedicated Storage Box export with independently placeable print objects.

    Registered two-colour geometry remains multi-part: the front label or the
    lid plus its top inlay.  Never routed through ``make_fused_box`` and never
    carries a side connector.
    """
    validate_b4b_design(
        box,
        layout_feature_kinds=tuple(one.kind for one in features),
        deep=True,
    )
    summary = b4b_summary(box)
    print_objects = b4b_build_print_objects(box, features=features)
    parts = [
        part
        for _object_name, object_parts in print_objects
        for part in object_parts
    ]

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / b4b_filename(box, part_name)
    if auto_timestamp and (target.exists() or not clean_label(part_name)):
        ts = datetime.now().strftime("%m%d%y%H%M%S")
        target = target.with_name(f"{target.stem} {ts}{target.suffix}")

    # non-label parts must each be one clean solid; labels are one prism per
    # letter, so they get the relaxed check
    for name, mesh in parts:
        if "Label" not in name:
            mesh_report(name, mesh)

    # lettering parts open on the second filament slot
    filaments = {
        name: 2 for name, _ in parts
        if name in ("Storage Box Top Label", "Storage Box Front Label Text")
    }
    written = export_object_groups_3mf(print_objects, target, filaments)
    report = validate_object_groups_3mf(target, print_objects, filaments)

    result: dict[str, object] = {
        "mode": "b4b",
        "b4b": summary,
        "output": str(target),
        "box": _part_result(target, {"name": "Storage Box Body", **report}),
        "parts": [
            {"name": name, "mesh": mesh_report(name, mesh) if "Label" not in name
             else {"name": name}}
            for name, mesh in parts
        ],
        "object_names": written,
        "hardware_bom": summary.get("hardware_bom", []),
    }
    if keep_log:
        envelope = summary["assembled_envelope_mm"]
        design_spec = design_to_dict(box, Layout(tuple(features), "fused", EDITOR_SNAP), "", part_name, "bottom", False)
        log_file = log_bin_to_folder(
            output_dir, b4b_effective_box(box), Layout((), "fused", EDITOR_SNAP),
            generated_files=[target], label="", part_name=part_name,
            b4b_note=_b4b_log_note(summary),
            physical_size_mm=(envelope[0], envelope[1], envelope[2]),
            design_spec=design_spec,
        )
        result["log_file"] = str(log_file)
    return result


def generate_organizer_files_transactional(
    box,
    layout,
    output_dir: Path,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    auto_timestamp: bool = False,
    keep_log: bool = False,
) -> dict[str, object]:
    """Build one ordinary-bin output set as a single install unit.

    The whole set (body, insert/cartridge, separate Edge Mount label, pegboard
    adapters, lid) is generated into an app-owned staging directory, validated
    as complete, then promoted over the final names. A build failure leaves the
    output folder untouched; a promotion failure rolls the folder back to
    exactly its prior files. Returns the same result shape as
    generate_organizer_files with every path rewritten to its final location.

    B4B keeps its existing direct path (out of scope for M09). When keep_log
    is true, the inventory row is recorded only AFTER the complete set
    promoted - a row is never recorded for a partial set.
    """
    if box.b4b.enabled:
        return generate_organizer_files(
            box, layout, output_dir, label, part_name, label_location, scoop,
            auto_timestamp=auto_timestamp, keep_log=keep_log,
        )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Canonicalize once here. The inner call re-runs _canonical_rim_label on
    # these already-canonical values, which is a no-op, so generation and the
    # logging below see identical values.
    canon_layout, canon_label, canon_location = _canonical_rim_label(
        box, layout, label, label_location)
    staging = Path(tempfile.mkdtemp(prefix=BIN_STAGE_PREFIX, dir=output_dir))
    try:
        result = generate_organizer_files(
            box, canon_layout, staging, canon_label, part_name, canon_location, scoop,
            auto_timestamp=False, keep_log=False,
        )
        staged = sorted(
            (one for one in staging.iterdir() if one.is_file() and one.suffix.lower() == ".3mf"),
            key=lambda one: one.name,
        )
        if not staged:
            raise RuntimeError("generating its files did not produce any")
        finals = _promote_staged_set(
            output_dir, staged, auto_timestamp=auto_timestamp, part_name=part_name)
        mapping: dict[str, str] = {}
        for staged_path, final in zip(staged, finals):
            mapping[str(staged_path.resolve())] = str(final.resolve())
            mapping[str(staged_path)] = str(final)
        result = _rewrite_staged_paths(result, mapping)
        if keep_log:
            # Same inventory block generate_organizer_files runs, but against
            # the promoted final paths, so the recorded row points at the
            # files that are actually installed.
            out_files: list[Path] = []
            if "box" in result and isinstance(result["box"], dict) and "output" in result["box"]:
                out_files.append(Path(str(result["box"]["output"])))
            if "insert" in result and isinstance(result["insert"], dict) and "output" in result["insert"]:
                out_files.append(Path(str(result["insert"]["output"])))
            if "lid" in result and isinstance(result["lid"], dict) and "output" in result["lid"]:
                out_files.append(Path(str(result["lid"]["output"])))
            if "edge_mount_label" in result and isinstance(result["edge_mount_label"], dict) and "output" in result["edge_mount_label"]:
                out_files.append(Path(str(result["edge_mount_label"]["output"])))
            if "pegboard_adapters" in result and isinstance(result["pegboard_adapters"], dict) and "output" in result["pegboard_adapters"]:
                out_files.append(Path(str(result["pegboard_adapters"]["output"])))
            log_file = log_bin_to_folder(
                output_dir,
                box,
                canon_layout,
                generated_files=out_files,
                label=canon_label,
                part_name=part_name,
                scoop=scoop,
                # The editable design is the request, never the shortened effective body.
                design_spec=design_to_dict(box, canon_layout, canon_label, part_name, canon_location, scoop),
            )
            result["log_file"] = str(log_file)
        return result
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def generate_organizer_files(
    box: BoxSpec,
    layout: Layout,
    output_dir: Path,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    auto_timestamp: bool = False,
    keep_log: bool = False,
) -> dict[str, object]:
    """Export an editor design as fused, fitted-removable, or cartridge parts.

    ``label`` is the rim-ledge label only. Floor lettering rides in ``layout``
    as ``text`` interior parts and is written as one extra 3MF object each, so
    every piece can take its own filament.
    """
    if box.b4b.enabled:
        validate_b4b_design(
            box,
            layout_feature_kinds=tuple(one.kind for one in layout.features),
            layout_mode=layout.mode,
            flat_inside=box.flat_inside,
        )
        return generate_b4b_files(
            box, output_dir, part_name,
            auto_timestamp=auto_timestamp,
            keep_log=keep_log,
            features=layout.features,
        )
    # Stacking rewrites the box before anything is built: a thicker wall to hold
    # the snap groove, a floor deep enough to contain the stepped base, and - in
    # lid mode - a body shortened so the closed bin is the height that was
    # typed.  Everything downstream, interior parts included, sees that box.
    # The request is kept for anything the user should recognise - the reported
    # height and the filename are the height they asked for, not the body the
    # lid is bolted onto.
    validate_stack_design(box)
    stack_request = box
    box = stack_effective_box(box)
    validate_inside_handles_mode(box, layout.mode)
    layout, label, label_location = _canonical_rim_label(box, layout, label, label_location)
    rim_features = tuple(one for one in layout.features if is_text(one) and one.options.get("level") == "rim")
    validate_scoop_lift_grabbers(box, scoop)
    validate_side_openings(box)
    for rim_text in rim_features:
        side = str(rim_text.options.get("rim_side") or "back")
        validate_side_opening_label(box, text_of(rim_text), side)
        validate_edge_mount_label_conflicts(box, text_of(rim_text), side)
    if not rim_features:
        validate_edge_mount_label_conflicts(box, "", "bottom")   # lid / stack rules need no label
    layout = replace(
        layout,
        features=resolve_text_features(
            box, layout.features,
            reserved=[zone.polygon for _name, zone in
                      _customization_zones(box, clean_label(label),
                                           label_position(label_location),
                                           scoop, layout.mode)],
            base_z=base_height(box, layout.mode), mode=layout.mode,
        ),
    )
    layout.validate(box)
    validate_rim_text_divider_clearance(box, layout.features, base_height(box, layout.mode))
    tidy = clean_label(label)
    location = label_position(label_location)
    side = rim_label_side(location)
    if tidy and not side:
        # Floor lettering is a text interior part now, so a label arriving here
        # for the floor is a caller mistake - say so rather than dropping it.
        raise ValueError(
            f"'{label}' is a floor label, and floor lettering is a text "
            "interior part now. Add one to the layout, or set the label "
            "position to a rim side for the rim ledge"
        )
    validate_customization_clearance(
        box, layout.features, tidy, location, scoop, layout.mode
    )
    label_info = top_label_report(box, tidy, side) if tidy and side else None
    text_surface = box.base_thickness if layout.mode == "fused" else BASE_PLATE
    text_limit = (
        None if layout.mode == "fused"
        else insert_footprint(box, layout.mode)
    )
    texts = build_texts(box, layout.features, text_surface, text_limit)
    from organizer_inserts._text import rim_text_geometry
    rim_parts = [rim_text_geometry(box, one) for one in rim_features]
    rim_texts = [(text_of(one), parts[1], text_is_raised(one))
                 for one, parts in zip(rim_features, rim_parts)]

    def _resolve_file(filename_fn, *args, **kwargs) -> Path:
        base_name = filename_fn(*args, **kwargs)
        target = output_dir / base_name
        if auto_timestamp:
            has_name = bool(clean_label(part_name))
            if not has_name or target.exists():
                ts = datetime.now().strftime("%m%d%y%H%M%S")
                stem = target.stem
                target = output_dir / f"{stem} {ts}{target.suffix}"
        return target

    if layout.mode == "fused":
        body = make_fused_box(box, layout.features, make_box(box))
        if scoop:
            body = union([body, make_scoop(box)])
        output = _resolve_file(box_filename, stack_request, part_name)
        # The rim label's ledge is part of the body, so it goes on before the
        # floor text is sunk into it.
        inlays = list(texts) + rim_texts
        if rim_parts:
            body = union([body, *(parts[0] for parts in rim_parts)])
        if tidy:
            body, ledge_inlay = make_top_labelled_box(box, tidy, body, side)
            inlays.append((tidy, ledge_inlay, False))
        # Edge Mount's plate and screw/access cuts apply to the completed
        # shell (fused features, scoop and the rim ledge already on it), so
        # the driver-access cut also clears any fused geometry blocking it.
        body = apply_edge_mount_structure(box, body)
        body = apply_pegboard_mount_structure(box, body)
        reported = apply_texts(body, texts + rim_texts)
        edge_text = edge_mount_text_object(box)
        if edge_text is not None and box.edge_mount.label_type == "integrated":
            _edge_label, edge_mesh, edge_raised = edge_text
            if not edge_raised:
                reported = difference([reported, edge_mesh])
                reported.remove_unreferenced_vertices()
                reported.merge_vertices()
            inlays.append(edge_text)
        reported = apply_surface_lightweight_base(reported, box, layout)
        # Re-applied last, to the fully completed body (fused features, scoop,
        # rim ledge, Edge Mount and floor text all already on it), so a later
        # body-level operation can never quietly fill a Side Opening back in.
        reported = apply_side_openings(box, reported)
        output_dir.mkdir(parents=True, exist_ok=True)
        if inlays:
            written = export_text_body_3mf(
                reported, [(name, mesh) for name, mesh, _raised in inlays],
                output, "fused_organizer",
            )
        else:
            written = []
            export_mesh(reported, output, "fused_organizer")
        result: dict[str, object] = {
            "mode": layout.mode,
            "box": _part_result(output, mesh_report("fused_organizer", reported)),
            "layout": insert_report("fused_organizer", layout.features, body),
            "text_objects": written,
        }
    else:
        box_output = _resolve_file(box_filename, stack_request, part_name)
        plain_box = make_box(box)
        insert_features = tuple(one for one in layout.features
                                if not (is_text(one) and one.options.get("level") == "rim"))
        insert = (
            make_cartridge_insert(box, insert_features)
            if layout.mode == "cartridge"
            else make_fitted_insert(box, insert_features)
        )
        if scoop:
            insert = union([insert, _removable_scoop(box, layout.mode)])
        insert_output = _resolve_file(
            insert_filename, box, part_name, layout.mode == "cartridge"
        )
        reported_insert = apply_texts(insert, texts)
        output_dir.mkdir(parents=True, exist_ok=True)
        # The rim label and Edge Mount belong to the box; the floor text
        # belongs to the insert it is sunk into. Edge Mount's plate/cuts
        # apply to the box shell only - never to the removable insert.
        body = plain_box
        box_inlays: list[tuple[str, trimesh.Trimesh, bool]] = []
        if rim_parts:
            body = union([body, *(parts[0] for parts in rim_parts)])
            body = apply_texts(body, rim_texts)
            box_inlays.extend(rim_texts)
        if tidy:
            body, box_inlay = make_top_labelled_box(box, tidy, body, side)
            box_inlays.append((tidy, box_inlay, False))
        body = apply_edge_mount_structure(box, body)
        body = apply_pegboard_mount_structure(box, body)
        edge_text = edge_mount_text_object(box)
        if edge_text is not None and box.edge_mount.label_type == "integrated":
            _edge_label, edge_mesh, edge_raised = edge_text
            if not edge_raised:
                body = difference([body, edge_mesh])
                body.remove_unreferenced_vertices()
                body.merge_vertices()
            box_inlays.append(edge_text)
        body = apply_surface_lightweight_base(body, box, layout)
        # Re-applied last, to the fully completed box shell, so a later
        # body-level operation can never quietly fill a Side Opening back in.
        body = apply_side_openings(box, body)
        reported_box = body
        if box_inlays:
            box_written = export_text_body_3mf(
                reported_box, [(name, mesh) for name, mesh, _raised in box_inlays],
                box_output, box_output.stem,
            )
        else:
            box_written = []
            export_mesh(reported_box, box_output, "wavy_box")
        if texts:
            written = export_text_body_3mf(
                reported_insert, [(name, mesh) for name, mesh, _raised in texts],
                insert_output, "organizer_insert",
            )
        else:
            written = []
            export_mesh(insert, insert_output, "organizer_insert")
        result = {
            "mode": layout.mode,
            "box": _part_result(box_output, mesh_report("wavy_box", reported_box)),
            "insert": _part_result(
                insert_output, mesh_report("organizer_insert", reported_insert)
            ),
            "layout": insert_report("organizer_insert", insert_features, insert),
            "text_objects": written,
            "box_text_objects": box_written,
        }
    if box.edge_mount.label_enabled and box.edge_mount.label_type == "separate":
        label_body = make_edge_mount_label_part(box)
        if label_body is not None:
            edge_text = edge_mount_text_object(box)
            inlays = []
            if edge_text is not None:
                name, mesh, raised = edge_text
                if not raised:
                    label_body = difference([label_body, mesh])
                inlays.append((name, mesh))
            axis = (1.0, 0.0, 0.0) if box.edge_mount.side in ("front", "back") else (0.0, 1.0, 0.0)
            transform = trimesh.transformations.rotation_matrix(math.pi, axis)
            printed_body = label_body.copy()
            printed_body.apply_transform(transform)
            offset = -float(printed_body.bounds[0][2])
            printed_body.apply_translation((0.0, 0.0, offset))
            printed_texts = []
            for name, mesh in inlays:
                printed = mesh.copy()
                printed.apply_transform(transform)
                printed.apply_translation((0.0, 0.0, offset))
                printed_texts.append((name, printed))
            label_output = _resolve_file(edge_mount_label_filename, box, part_name)
            if printed_texts:
                written = export_text_body_3mf(printed_body, printed_texts, label_output, "edge_mount_label")
            else:
                written = []
                export_mesh(printed_body, label_output, "edge_mount_label")
            result["edge_mount_label"] = _part_result(label_output, mesh_report("edge_mount_label", printed_body))
            result["edge_mount_label"]["text_objects"] = written
    if box.pegboard.enabled:
        adapters = make_board_adapters(box)
        adapter_output = _resolve_file(pegboard_adapter_filename, box, part_name)
        export_object_groups_3mf(
            [(name, [(name, mesh)]) for name, mesh in adapters], adapter_output
        )
        result["pegboard_adapters"] = {
            "output": str(adapter_output.resolve()),
            "count": len(adapters),
            "standard": box.pegboard.standard,
        }
        result["pegboard"] = receiver_layout(box)
    if label_info is not None:
        result["label"] = label_info
    result["texts"] = [
        text_report(box, one, text_surface) for one in layout.features if is_text(one)
    ]
    result["customizations"] = {"scoop": scoop, "label_position": location}
    if box.edge_mount.active:
        result["edge_mount"] = edge_mount_summary(box)
    if box.side_openings.enabled:
        result["side_openings"] = side_opening_summary(box)
    if lid_enabled(stack_request):
        lid_output = _resolve_file(lid_filename, stack_request, part_name)
        lid, lid_texts = make_lid_parts(
            stack_request, lid_label_regions(stack_request, layout),
        )
        if lid_texts:
            written = export_text_body_3mf(
                lid, [(text, mesh) for text, mesh, _raised in lid_texts],
                lid_output, "lid",
            )
        else:
            written = []
            export_mesh(lid, lid_output, "lid")
        result["lid"] = _part_result(lid_output, None)
        result["lid"]["text_objects"] = written
    if stack_enabled(stack_request):
        result["stack"] = stack_summary(stack_request)
    if keep_log:
        out_files: list[Path] = []
        if "box" in result and isinstance(result["box"], dict) and "output" in result["box"]:
            out_files.append(Path(str(result["box"]["output"])))
        if "insert" in result and isinstance(result["insert"], dict) and "output" in result["insert"]:
            out_files.append(Path(str(result["insert"]["output"])))
        if "lid" in result and isinstance(result["lid"], dict) and "output" in result["lid"]:
            out_files.append(Path(str(result["lid"]["output"])))
        if "edge_mount_label" in result and isinstance(result["edge_mount_label"], dict) and "output" in result["edge_mount_label"]:
            out_files.append(Path(str(result["edge_mount_label"]["output"])))
        if "pegboard_adapters" in result and isinstance(result["pegboard_adapters"], dict) and "output" in result["pegboard_adapters"]:
            out_files.append(Path(str(result["pegboard_adapters"]["output"])))
        # Inventory stores the requested stack-module height.  The drawer adds
        # the exposed top engagement depth when checking physical clearance.
        log_file = log_bin_to_folder(
            output_dir,
            stack_request,
            layout,
            generated_files=out_files,
            label=label,
            part_name=part_name,
            scoop=scoop,
            # The editable design is the request, never the shortened effective body.
            design_spec=design_to_dict(stack_request, layout, label, part_name, location, scoop),
        )
        result["log_file"] = str(log_file)
    return result


def run_command(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "sampler":
        return generate_sampler(
            output=args.output,
            sizes=parse_sizes(args.boxes),
            height=args.z,
            wall=args.wall,
            base_thickness=args.base_thickness,
            flat_inside=args.flat_inside,
            connector=ConnectorSpec(tolerance=args.tolerance),
            clips=args.clips,
        )
    if args.command == "box":
        return generate_box_file(
            _box_spec(args), args.output, args.label, args.label_position, args.scoop
        )
    if args.command == "organizer":
        raw = json.loads(args.layout.read_text(encoding="utf-8"))
        if "box" in raw:
            (saved_box, layout, saved_label, saved_part,
             saved_label_location, saved_scoop) = design_from_dict(raw)
        else:
            saved_box, layout, saved_label, saved_part = BoxSpec(), layout_from_dict(raw), "", ""
            saved_label_location, saved_scoop = "bottom", False
        box = BoxSpec(
            saved_box.x if args.x is None else args.x,
            saved_box.y if args.y is None else args.y,
            saved_box.z if args.z is None else args.z,
            saved_box.wall if args.wall is None else args.wall,
            saved_box.corner_fillet,
            saved_box.flat_inside if args.flat_inside is None else args.flat_inside,
            saved_box.base_thickness
            if args.base_thickness is None
            else args.base_thickness,
            standard_base=saved_box.standard_base,
            standard_walls=(
                saved_box.standard_walls
                if args.wall is None
                else math.isclose(args.wall, DEFAULT_WALL, abs_tol=1e-9)
            ),
            side_openings=saved_box.side_openings,
        )
        if args.mode:
            layout = replace(layout, mode=args.mode)
        label = saved_label if args.label is None else args.label
        location = (saved_label_location if args.label_position is None
                    else args.label_position)
        part = saved_part if args.part_name is None else args.part_name
        if clean_label(label) and label_position(location) == "bottom":
            # Sugar: a floor label from the command line is a text interior
            # part that finds its own spot, exactly as adding one in the
            # editor with "place it for me" left on would.
            layout = replace(
                layout,
                features=layout.features + (auto_text_feature(box, label, layout.mode),),
            )
            part = part or part_name_seed(label)
            label = ""
        # Fix 096 A1: CLI generation installs as one transactional unit too -
        # staged, validated, then promoted; a build failure leaves the output
        # folder untouched.
        return generate_organizer_files_transactional(
            box,
            layout,
            args.output_dir,
            label,
            part,
            location,
            saved_scoop if args.scoop is None else args.scoop,
        )
    if args.command == "side":
        return generate_side_file(
            _box_spec(args, "box"),
            _connector_spec(args),
            args.output,
            args.along,
            args.position,
            args.length,
        )
    if args.command == "kit":
        return generate_kit_files(
            _box_spec(args),
            _connector_spec(args),
            args.output_dir,
            args.side_along,
            args.side_position,
            args.label,
            args.label_position,
            args.scoop,
        )
    raise RuntimeError(f"unsupported command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_command(args)
    except Exception as error:
        parser.exit(2, f"error: {error}\n")
    if result is not None:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
