"""Drawer layout: fitting printed bins into a real drawer.

Pure 2D planning on the bin grid, plus the geometry it owns - the spacers
that fill whatever the bins leave, and the connectors a layout needs.  There
is one filler part, the Spacer: an open X-braced frame for a whole empty
patch of grid, or (when it instead lines the strip between the grid and the
drawer wall) a solid piece that is wavy on its bin-facing side and flat on
its wall-facing side.  Both are ``kind: "spacer"``; only the placement shape
and an internal ``boundary`` tag ("" or "edge") tell them apart.  Drawer
coordinates: x runs left to right, y runs from the front (0) to the back, z
is height.  The Layout view draws the front at the bottom.

Bins never turn a quarter turn inside a drawer.  Left walls mate with right
walls and front with back; a bin turned 90 degrees meets its neighbours crest
to crest (every mixed pair collides when checked with the engine's own
outlines).  A drawer may instead run *every* bin's X front-to-back
(``bin_axis = "y"``), which turns the whole grid together and keeps each seam
matched.

Placements
----------
* On the grid: ``gx``/``gy`` in 8 mm units from the grid's front-left corner.
  A drawer that snaps to 4 mm (``snap = 4``) allows half units: the wave
  repeats every 4 mm, so a bin shifted half a unit along a seam still nests.
* Stacked: ``on`` names the one placement it stands on (``"B3:0"``) and
  ``ox``/``oy`` are its offset in 8 mm units from that placement's front-left
  corner (missing means 0, which is what older same-footprint stacks carry).
  Only a stackable bin of the same stacking style can snap onto another; direct
  and Storage Box stacking need the same footprint, while a snap-on lid can
  carry any number of smaller bins that sit fully inside it and clear of each
  other - partial coverage is normal.  A placement may carry several children
  and a child may carry its own; each one adds its requested module height
  above its direct parent.  The exposed top interlock remains part of the
  stack's physical drawer-height envelope.
* Free, for an edge-facing spacer: ``x``/``y``/``w``/``d`` in mm from the
  drawer's inside front-left corner, plus the ``side`` it lines.  Its width
  across the wall is the drawer's real leftover play, not rounded to a grid
  unit - a physically genuine residual, not a whole-8-mm footprint.

An ordinary bin row is one placement identity: at most one placement per
row. Its print state is the row's own ``status``, never the placement. A
spacer row is the exception: it is a repeated filler part and may be placed
several times (``copy`` counts those placements).

Legacy inventories used a separate ``kind: "shim"`` for the edge-facing
piece; ``organizer_inventory._normalise`` migrates it to ``spacer`` with
``boundary: "edge"`` the moment a file is read, so nothing below this line
ever sees the old kind.
"""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_app import bore_reference_envelope_extensions, connector_filename, design_from_dict, design_source_payload, design_to_dict, generate_side_file, object_height_plan
from organizer_stack import stack_summary
from organizer_engine import (
    BASE_UNIT,
    MAX_BOX_SIZE,
    MIN_HEIGHT_ABOVE_BASE,
    DEFAULT_WALL,
    LOCKED_CONNECTOR_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    BoxSpec,
    ConnectorSpec,
    differing_connector_plan,
    export_mesh,
    make_wall_lock_bumps_raw,
    placed_outline,
    wall_depth_for,
    wavy_rect_cavity,
    wavy_rect_outer,
)
from organizer_geometry import _extrude_polygon
from organizer_inventory import (
    INVENTORY_FILENAME,
    INVENTORY_LOCK,
    design_specs,
    duplicate_design_source as _duplicate_design_source_row,
    duplicate_design_source_text as _duplicate_design_source_row_text,
    change_design_status as _change_design_status_row,
    change_design_status_text as _change_design_status_row_text,
    legacy_layout_space,
    load_inventory,
    load_inventory_text,
    mark_printed_rows,
    normalise_storage_box,
    storage_box_defaults,
    next_bin_id,
    save_design_source as _save_design_source_row,
    save_design_source_text as _save_design_source_row_text,
    save_inventory,
    save_inventory_text,
    update_bin_file,
)
from organizer_inserts import Layout
from organizer_b4b import B4B_STACK_RECESS_DEPTH, b4b_summary
from organizer_product_rules import DRAWER_HARD_CLEARANCE_MM, SURFACE_TRIM_HEIGHTS
from organizer_stack import STACK_MIN_WALL, STACK_PLUG_DEPTH, STACK_SEAT_DEPTH
from organizer_pegboard import pegboard_layout_for_bin, pegboard_standard
from organizer_edge_mount import edge_mount_projection_envelope
from organizer_slicer import slicer_display_name
from organizer_printer_profile import (
    DEFAULT_PRINTER_BUILD_MM,
    normalise_printer_profile,
    print_file_fit_issues,
)

import copy
from pathlib import Path
from typing import Any, Callable

from ._core import (
    _default_printer_profile,
    UNIT,
    SNAPS,
    CREST,
    MIN_CLEARANCE,
    MIN_EDGE_SPACER,
    RIGID_SPACER_CLEARANCE_MM,
    MIN_SPACER_HEIGHT,
    DEFAULT_SPACER_HEIGHT,
    SPACER_CONTACT_TARGET,
    SPACER_DISTRIBUTE_EVERY,
    SPACER_SELECTED_CAP,
    RIB_WIDTH,
    MIN_RIB_SPAN,
    MIN_CONNECTOR_SEAM,
    HEIGHT_TOLERANCE,
    STACK_STEPS,
    DRAWER_DEFAULTS,
    ANCHORS,
    BOUNDARIES,
    SIDES,
    SPACER_KINDS,
    _positive,
    normalise_drawer,
    find_drawer,
    drawer_grid,
    _per_unit,
    _cell,
    _units,
    bin_cells,
    stack_pitch,
    stack_part_height,
    is_surface_layout,
    is_storage_box_layout,
    storage_box_height_cap,
    stack_wall,
    stack_compatibility_issue,
    space_stack_metrics,
    storage_box_stack_metrics,
    surface_planning_heights,
    _key,
    _label,
    _close,
    _overlaps,
    _offset,
    _support_trees,
    _physical_envelopes,
    _stack_item,
    _grid_items,
    _height_issues,
    _two_largest_empty,
    _largest_empty,
    surface_fill_plan,
)
from ._report import (
    _connector_eligible,
    _top_wall,
    _connectors,
    _pegboard_report,
    ADVISORY_PROBLEM_TYPES,
    INTERIOR_COMPONENT_MESSAGE,
    problem_blocks_print,
    blocking_problem_messages,
    selected_blocking_problems,
    blocking_problem_copy,
    _interior_components,
    drawer_report,
    _problem_signature,
    _bin_names,
    surface_reconfigure_problem,
)
from ._spacers import (
    _exposed_segments,
    _SPACER_PLAN_BIN_FIELDS,
    spacer_plan_signature,
    plan_spacers,
    _serpentine_flexure,
    spacer_filename,
    generate_spacers,
    generate_connectors,
    print_spacers_and_connectors,
)
from ._inventory import (
    _safe_row_file,
    inventory_row_file_names,
    inventory_row_files,
    _copy_count,
    prepare_inventory_bins,
    _space_connectors,
    _batch_partial,
    _prepare_failure_text,
    _plural,
    save_inventory_bins,
    _rollback_spacer_stage,
    _promote_spacer_stage,
)

def print_inventory_bins(
    output_dir: Path | str,
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    selection: dict[str, Any],
    include_connectors: bool,
    detect_slicer: Callable,
    launch_slicer: Callable,
    slicer_path: str | None = None,
    generate_from_design: Callable[[Path, dict[str, Any]], list[Path]] | None = None,
    printer_profile: dict | None = None,
) -> dict[str, Any]:
    """Send selected generated bins (and optional Space connectors) to the slicer.

    Printed status changes only after the slicer launch succeeds. Rows without
    current files but with a canonical ``design_specs`` entry are generated
    first by the shared ``prepare_inventory_bins`` step (the same one batch
    Save uses); each is recorded Saved / Qty 0 as soon as it is made. Any
    failure before the launch - a bin, the connectors, or the slicer - returns
    a structured partial result with the refreshed Inventory and never marks
    anything Printed.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    # Preflight the authoritative slicer before any on-demand bin generation,
    # Inventory File-cell write or connector generation.
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name_cap = slicer_display_name(slicer) or "The slicer"
    by_id = {one["id"]: one for one in bins}
    counts: dict[str, int] = {}
    for bin_id, raw_count in (selection or {}).items():
        one = by_id.get(str(bin_id))
        if one is None:
            raise ValueError(f"no bin {bin_id!r} in the inventory")
        _copy_count(one, raw_count)
        if one.get("kind") not in ("bin", "b4b"):
            raise ValueError(f"{_label(one)} is not a generated bin and cannot be printed here")
        counts[one["id"]] = 1
    if not counts:
        raise ValueError("Select at least one bin to print.")

    blocked = selected_blocking_problems(layout, bins, counts)
    if blocked:
        raise ValueError(blocking_problem_copy(bins, blocked))

    prepared = prepare_inventory_bins(output_dir, list(counts), generate_from_design)
    if prepared["failed"]:
        slicer_label = slicer_display_name(slicer) or "The slicer"
        return _batch_partial(
            prepared, "generate", _prepare_failure_text(prepared, slicer_label), selection=counts)
    rows_files = prepared["files"]
    specs = prepared["specs"]
    inventory = prepared["inventory"]

    connector_counts: dict[str, int] = {}
    notes: list[str] = []
    if include_connectors:
        try:
            # Fix 111 R4-10: consume the refreshed authoritative layout, not
            # the pre-prepare request layout, with the refreshed bins.
            connector_counts, notes = _space_connectors(output_dir, inventory["layout"], inventory["bins"])
        except Exception as error:
            return _batch_partial(
                prepared, "connectors",
                f"The bins were saved, but the Space connectors could not be made: {error}. "
                f"{name_cap} was not opened.", selection=counts)

    launch_files: list[Path] = []
    for bin_id in counts:
        launch_files.extend(rows_files[bin_id])
    for name, count in connector_counts.items():
        launch_files.extend([output_dir / name] * count)

    result_counts = {
        "selection": counts,
        "bin_copies": sum(counts.values()),
        "connector_counts": connector_counts,
        "connector_copies": sum(connector_counts.values()),
        "notes": notes,
    }
    # Every file handed to the slicer must fit the active printer; a fit
    # failure fails before launch so nothing is orphaned mid-print.
    fit_issues: list[str] = []
    for path in dict.fromkeys(launch_files):
        fit_issues.extend(print_file_fit_issues(path, printer_profile or _default_printer_profile()))
    if fit_issues:
        return _batch_partial(
            prepared, "preflight",
            "A file does not fit the active printer:\n" + "\n".join(fit_issues),
            **result_counts)
    try:
        launch_slicer(Path(slicer), launch_files)
    except Exception as error:
        # Files and connectors written above are kept; rows stay Saved (never
        # Printed). Return the refreshed Inventory so the browser matches disk.
        return _batch_partial(
            prepared, "slicer",
            f"{name_cap} did not open: {error}. Any files made during this attempt were kept.",
            **result_counts)

    try:
        # A row is one bin. Placement copy numbers are not print bookkeeping.
        saved = mark_printed_rows(output_dir, counts, specs)
    except Exception as error:
        return _batch_partial(
            prepared, "status",
            f"{name_cap} opened, but the printed status could not be recorded: {error}. "
            "Check the selected rows in Inventory.", **result_counts)
    return {**saved, **result_counts}


def drawer_routes(
    geometry_lock,
    default_output: Path,
    detect_slicer: Callable | None = None,
    launch_slicer: Callable | None = None,
    hosted: bool = False,
    generate_from_design: Callable[[Path, dict[str, Any]], list[Path]] | None = None,
    printer_profile_for: Callable[[dict], dict] | None = None,
) -> dict[str, Callable[[dict], dict]]:
    """POST handlers for the browser service, keyed by path."""

    def _printer_profile(payload: dict) -> dict:
        # organizer_drawer cannot import load_preferences (it lives in
        # wavefinity_web); the host injects its resolver instead.
        if printer_profile_for is not None:
            return printer_profile_for(payload)
        return _default_printer_profile()

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def with_rules(result: dict[str, Any]) -> dict[str, Any]:
        # The view needs the stacking steps for live stack heights while dragging.
        return {**result, "stack_steps": STACK_STEPS,
                "stack_metrics": space_stack_metrics(result.get("layout"), result.get("bins") or []),
                "storage_box_headroom_default_mm": storage_box_defaults()["lid_headroom_mm"]}

    def load(payload):
        if hosted:
            result = load_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
            )
            layout = result.get("layout")
            space_inferred = False
            if isinstance(layout, dict) and not isinstance(layout.get("space"), dict):
                inferred = legacy_layout_space(layout)
                if inferred:
                    # A lossy reconstruction from the drawer layout alone,
                    # which can only ever guess "drawer" - never let it look
                    # like an authoritative space to the caller (it must not
                    # outrank real Space metadata; see SP.inspectHosted).
                    result = {**result, "layout": {**layout, "space": inferred}}
                    space_inferred = True
            return {**with_rules(result), "space_inferred": space_inferred}
        return with_rules(load_inventory(folder(payload)))

    def save(payload):
        changes: dict[str, Any] = {
            "bin_updates": payload.get("bin_updates") or (),
            "new_bins": payload.get("new_bins") or (),
            # Fix 096 A2: specs parallel to new_bins, attached atomically with
            # their rows by _merge_inventory.
            "new_bin_specs": payload.get("new_bin_specs") or (),
            "delete_ids": payload.get("delete_ids") or (),
        }
        if "layout" in payload and payload["layout"] is not None:
            changes["layout"] = payload["layout"]
        if hosted:
            return with_rules(save_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                available_filenames=payload.get("available_filenames") or (),
                **changes,
            ))
        return with_rules(save_inventory(folder(payload), **changes))

    def save_design_source(payload):
        """Canonicalize and save one editable Inventory design source."""
        design, record = design_source_payload(payload["design"])
        row_id = str(payload.get("row_id") or "") or None
        if hosted:
            result = _save_design_source_row_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                design=design, record=record, row_id=row_id,
                available_filenames=payload.get("available_filenames") or (),
            )
        else:
            result = _save_design_source_row(folder(payload), design=design, record=record, row_id=row_id)
        return with_rules(result)

    def duplicate_design_source(payload):
        row_id = str(payload.get("row_id") or "")
        if hosted:
            result = _duplicate_design_source_row_text(
                payload.get("inventory_text") or "", row_id,
                title=str(payload.get("inventory_title") or "Wavefinity"),
            )
        else:
            result = _duplicate_design_source_row(folder(payload), row_id)
        return with_rules(result)

    def change_design_status(payload):
        row_id = str(payload.get("row_id") or "")
        action = str(payload.get("action") or "")
        file_text = payload.get("file")
        expected_design = payload.get("design")
        if file_text is not None and not isinstance(file_text, str):
            raise ValueError("file names must be text")
        if expected_design is not None and not isinstance(expected_design, dict):
            raise ValueError("expected design must be an object")
        if hosted:
            result = _change_design_status_row_text(
                payload.get("inventory_text") or "", row_id, action, file_text,
                title=str(payload.get("inventory_title") or "Wavefinity"),
                expected_design=expected_design,
                # Omitted = no folder snapshot (nothing proven gone); an
                # explicit [] = known-empty snapshot. Keep them distinct.
                available_filenames=(
                    payload.get("available_filenames")
                    if "available_filenames" in payload
                    else None
                ),
            )
        else:
            result = _change_design_status_row(folder(payload), row_id, action, file_text, expected_design)
        return with_rules(result)

    def report(payload):
        return drawer_report(
            find_drawer(payload["layout"], payload.get("drawer_id")),
            payload.get("bins") or [], payload.get("height_reach") or "column",
            payload["layout"],
        )

    def surface_fill(payload):
        with INVENTORY_LOCK:
            inventory = load_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
            ) if hosted else load_inventory(folder(payload))
            return surface_fill_plan(inventory)

    def surface_fill_create(payload):
        with INVENTORY_LOCK:
            inventory = load_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
            ) if hosted else load_inventory(folder(payload))
            plan = surface_fill_plan(inventory)
            if plan["signature"] != payload.get("signature"):
                raise ValueError("Surface changed — update the Fill Empty Space plan")
            by_candidate = {one["id"]: one for one in plan["candidates"]}
            selected = list(payload.get("selected") or [])
            if len(selected) != len(set(selected)) or any(one not in by_candidate for one in selected):
                raise ValueError("Surface changed — update the Fill Empty Space plan")
            layout = copy.deepcopy(inventory["layout"])
            edge = SURFACE_TRIM_HEIGHTS[layout["space"]["trim_size"]]
            starter_z = edge + MIN_HEIGHT_ABOVE_BASE
            rows = []
            allocated = list(inventory["bins"])
            specs = dict(design_specs(layout))
            drawer = find_drawer(layout)
            for candidate_id in selected:
                candidate = by_candidate[candidate_id]
                box = BoxSpec(candidate["x_mm"], candidate["y_mm"], starter_z,
                              base_thickness=edge, standard_base=False)
                source = design_to_dict(box, Layout(
                    object_height_mm=None, surface_base_mode="edge",
                    surface_lightweight_base=True,
                ))
                row_id = next_bin_id(allocated)
                row = {"id": row_id, "kind": "bin", "name": "",
                       "x": box.x, "y": box.y, "z": box.z, "wall": box.wall,
                       "object_height_mm": None, "qty": 0, "file": ""}
                rows.append(row)
                allocated.append(row)
                specs[row_id] = source
                drawer.setdefault("placements", []).append({
                    "bin": row_id, "copy": 0,
                    "gx": candidate["gx"], "gy": candidate["gy"],
                })
            layout["design_specs"] = specs
            if hosted:
                result = save_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                    layout=layout, new_bins=rows,
                )
            else:
                result = save_inventory(folder(payload), layout=layout, new_bins=rows)
            return with_rules({**result, "created": [one["id"] for one in rows]})

    def spacers(payload):
        with geometry_lock:
            inv = (
                load_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                )
                if hosted else load_inventory(folder(payload))
            )
            layout = inv["layout"]
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            result = plan_spacers(drawer, inv["bins"], options)
            result["plan_signature"] = spacer_plan_signature(
                drawer, inv["bins"], options,
            )
            return result

    def spacers_generate(payload):
        if hosted:
            import base64
            import tempfile
            with geometry_lock, INVENTORY_LOCK:
                inv = load_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                )
                layout = copy.deepcopy(inv["layout"])
                drawer = find_drawer(layout, payload.get("drawer_id"))
                options = payload.get("options") or {}
                current_signature = spacer_plan_signature(drawer, inv["bins"], options)
                if current_signature != str(payload.get("plan_signature") or ""):
                    raise ValueError(
                        "Spacers changed while you were planning — refresh the Space and plan again. "
                        "Your unsaved spacer plan was discarded; nothing was merged."
                    )
                request_for_gen = {
                    "drawer": drawer,
                    "bins": inv["bins"],
                    "options": options,
                    "selected": payload.get("selected", []),
                }
                with tempfile.TemporaryDirectory(prefix="wavefinity-hosted-spacers-") as tmp:
                    tmpdir = Path(tmp)
                    def generate_file(name, mesh):
                        out = tmpdir / name
                        mesh.export(str(out))
                        return out
                    result = generate_spacers(request_for_gen, tmpdir, generate_file)
                    files_base64 = {}
                    for gen in result.get("generated", []):
                        files_base64[gen["file"]] = base64.b64encode(
                            (tmpdir / gen["file"]).read_bytes()).decode("ascii")
                new_bins: list[dict[str, Any]] = []
                bins_so_far = list(inv["bins"])
                for gen in result.get("generated", []):
                    new_id = next_bin_id(bins_so_far)
                    row = {
                        "id": new_id,
                        "kind": "spacer",
                        "boundary": "edge",
                        # Inventory x/y/z are physical mm, never Wavefinity unit counts.
                        "name": "Flexible Spacer" if gen.get("flexible") else "Rigid Spacer",
                        "x": gen["w"], "y": gen["d"], "z": gen["h"],
                        "qty": 1,
                        "file": gen["file"],
                        "flexible": bool(gen.get("flexible")),
                    }
                    new_bins.append(row)
                    bins_so_far.append(row)
                    for p in gen["placements"]:
                        p_copy = dict(p)
                        p_copy["bin"] = new_id
                        p_copy.setdefault("copy", 0)
                        drawer.setdefault("placements", []).append(p_copy)
                saved = save_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                    layout=layout, new_bins=new_bins,
                )
                result["layout"] = saved["layout"]
                result["bins"] = saved["bins"]
                result["inventory_text"] = saved["inventory_text"]
                result["files_base64"] = files_base64
                return result
        with geometry_lock, INVENTORY_LOCK:
            def generate_file(name, mesh):
                out = folder(payload) / name
                mesh.export(str(out))
                return out

            inv = load_inventory(folder(payload))
            layout = copy.deepcopy(inv["layout"])
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            current_signature = spacer_plan_signature(drawer, inv["bins"], options)
            if current_signature != str(payload.get("plan_signature") or ""):
                raise ValueError(
                    "Spacers changed while you were planning — refresh the Space and plan again. "
                    "Your unsaved spacer plan was discarded; nothing was merged."
                )

            request_for_gen = {
                "drawer": drawer,
                "bins": inv["bins"],
                "options": options,
                "selected": payload.get("selected", []),
            }
            result = generate_spacers(request_for_gen, folder(payload), generate_file)

            new_bins: list[dict[str, Any]] = []
            bins_so_far = list(inv["bins"])
            for gen in result.get("generated", []):
                new_id = next_bin_id(bins_so_far)
                row = {
                    "id": new_id,
                    "kind": "spacer",
                    "boundary": "edge",
                    "name": "Flexible Spacer" if gen.get("flexible") else "Rigid Spacer",
                    # Inventory x/y/z are physical mm, never Wavefinity unit counts.
                    "x": gen["w"], "y": gen["d"], "z": gen["h"],
                    "qty": 1,
                    "file": gen["file"],
                    "flexible": bool(gen.get("flexible")),
                }
                new_bins.append(row)
                bins_so_far.append(row)
                for p in gen["placements"]:
                    p_copy = dict(p)
                    p_copy["bin"] = new_id
                    p_copy.setdefault("copy", 0)
                    drawer.setdefault("placements", []).append(p_copy)

            saved = save_inventory(folder(payload), layout=layout, new_bins=new_bins)

            result["layout"] = saved["layout"]
            result["bins"] = saved["bins"]

            return result

    def spacers_refresh(payload):
        """Replace the active drawer's spacer set in one Inventory commit."""
        import base64
        import tempfile

        with geometry_lock, INVENTORY_LOCK:
            if hosted:
                inventory_text = payload.get("inventory_text") or ""
                inventory_title = str(payload.get("inventory_title") or "Wavefinity")
                inv = load_inventory_text(inventory_text, title=inventory_title)
                root = None
            else:
                inventory_text = ""
                inventory_title = "Wavefinity"
                root = folder(payload)
                inv = load_inventory(root)

            layout = copy.deepcopy(inv["layout"])
            bins = list(inv["bins"])
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            plan = plan_spacers(drawer, bins, options)
            selected_ids = [
                str(one.get("id"))
                for one in plan.get("selected") or []
                if one.get("id") is not None
            ]
            request_for_gen = {
                "drawer": drawer,
                "bins": bins,
                "options": options,
                "selected": selected_ids,
            }

            active_id = str(drawer.get("id") or "")
            by_id = {str(one["id"]): one for one in bins}
            old_spacer_ids = {
                str(placement.get("bin"))
                for placement in drawer.get("placements") or []
                if (
                    str(placement.get("bin")) in by_id
                    and by_id[str(placement.get("bin"))].get("kind") in SPACER_KINDS
                )
            }

            if root is not None:
                root.mkdir(parents=True, exist_ok=True)
                stage_context = tempfile.TemporaryDirectory(
                    prefix=".wavefinity-spacer-stage-",
                    dir=root,
                )
            else:
                stage_context = tempfile.TemporaryDirectory(
                    prefix="wavefinity-hosted-spacer-refresh-",
                )

            with stage_context as tmp:
                stage = Path(tmp).resolve()

                def generate_file(name, mesh):
                    out = stage / name
                    mesh.export(str(out))
                    return out

                generated = generate_spacers(
                    request_for_gen,
                    stage,
                    generate_file,
                )

                new_bins: list[dict[str, Any]] = []
                bins_so_far = list(bins)
                new_placements: list[dict[str, Any]] = []
                for gen in generated.get("generated") or []:
                    new_id = next_bin_id(bins_so_far)
                    row = {
                        "id": new_id,
                        "kind": "spacer",
                        "boundary": "edge",
                        "name": "Flexible Spacer" if gen.get("flexible") else "Rigid Spacer",
                        "x": gen["w"],
                        "y": gen["d"],
                        "z": gen["h"],
                        "qty": 1,
                        "file": gen["file"],
                    }
                    new_bins.append(row)
                    bins_so_far.append(row)
                    for placement in gen.get("placements") or []:
                        placed = dict(placement)
                        placed["bin"] = new_id
                        placed.setdefault("copy", 0)
                        new_placements.append(placed)

                for one in layout.get("drawers") or []:
                    if str(one.get("id") or "") != active_id:
                        continue
                    one["placements"] = [
                        placement
                        for placement in one.get("placements") or []
                        if str(placement.get("bin")) not in old_spacer_ids
                    ]
                    one["placements"].extend(new_placements)
                    break

                still_used = {
                    str(placement.get("bin"))
                    for one in layout.get("drawers") or []
                    for placement in one.get("placements") or []
                }
                delete_ids = sorted(old_spacer_ids - still_used)
                new_names = list(dict.fromkeys(
                    str(one["file"])
                    for one in generated.get("generated") or []
                ))

                if hosted:
                    files_base64 = {
                        name: base64.b64encode((stage / name).read_bytes()).decode("ascii")
                        for name in new_names
                    }
                    saved = save_inventory_text(
                        inventory_text,
                        title=inventory_title,
                        layout=layout,
                        new_bins=new_bins,
                        delete_ids=delete_ids,
                        available_filenames=payload.get("available_filenames") or (),
                        protected_files=new_names,
                    )
                    return {
                        **generated,
                        "layout": saved["layout"],
                        "bins": saved["bins"],
                        "inventory_text": saved["inventory_text"],
                        "cleanup_files": saved.get("cleanup_files", []),
                        "files_base64": files_base64,
                        "removed": len(old_spacer_ids),
                    }

                backups: dict[str, Path | None] = {}
                installed: list[Path] = []
                try:
                    backups, installed = _promote_spacer_stage(
                        root,
                        stage,
                        new_names,
                    )
                    saved = save_inventory(
                        root,
                        layout=layout,
                        new_bins=new_bins,
                        delete_ids=delete_ids,
                        protected_files=new_names,
                    )
                except Exception as error:
                    if installed or backups:
                        try:
                            _rollback_spacer_stage(root, backups, installed)
                        except Exception as rollback_error:
                            raise RuntimeError(
                                f"{error} Spacer rollback also failed: {rollback_error}"
                            ) from error
                    raise

                return {
                    **generated,
                    "layout": saved["layout"],
                    "bins": saved["bins"],
                    "cleanup_failed": saved.get("cleanup_failed", []),
                    "removed": len(old_spacer_ids),
                }

    def print_spacers_only(payload):
        if hosted:
            raise ValueError("Hosted Wavefinity saves files to your folder instead of opening a local slicer.")
        if detect_slicer is None or launch_slicer is None:
            raise ValueError("printing is not available here")
        with geometry_lock:
            selection = payload.get("selection") or {}
            out_dir = folder(payload)
            inv = load_inventory(out_dir)
            files: list[Path] = []
            launch_files: list[Path] = []
            counts: dict[str, int] = {}
            # All-or-nothing preflight: every selected spacer must resolve to a
            # real file before anything launches; unresolved selections are named.
            unresolved: list[str] = []
            by_id = {str(b["id"]): b for b in inv["bins"]}
            for row_id, count in (selection or {}).items():
                if not count or int(count) <= 0:
                    continue
                one = by_id.get(str(row_id))
                if one is None:
                    unresolved.append(str(row_id))
                    continue
                safe = _safe_row_file(out_dir, one.get("file") or "")
                if safe is None:
                    unresolved.append(_label(one))
                    continue
                files.append(safe)
                launch_files.extend([safe] * int(count))
                counts[safe.name] = int(count)
            if unresolved:
                raise ValueError(
                    "These spacers have no printable file and were not sent: "
                    + ", ".join(sorted(set(unresolved)))
                    + ". Generate their files first, then print again.")
            if not files:
                raise ValueError("Select at least one spacer to print.")
            slicer = detect_slicer(payload.get("slicer_path"))
            if slicer is None or not Path(slicer).is_file():
                raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
            fit_issues: list[str] = []
            for path in dict.fromkeys(launch_files):
                fit_issues.extend(print_file_fit_issues(path, _printer_profile(payload)))
            if fit_issues:
                raise ValueError(
                    "A file does not fit the active printer:\n" + "\n".join(fit_issues))
            launch_slicer(Path(slicer), launch_files)
            return {"files": [str(path) for path in files], "counts": counts, "notes": []}

    def print_bins(payload):
        if hosted:
            raise ValueError("Bulk printing to a local slicer is available in local Wavefinity.")
        if detect_slicer is None or launch_slicer is None:
            raise ValueError("printing is not available here")
        with geometry_lock:
            out_dir = folder(payload)
            inv = load_inventory(out_dir)
            return with_rules(print_inventory_bins(
                out_dir, inv["layout"], inv["bins"],
                payload.get("selection") or {},
                bool(payload.get("include_connectors", True)),
                detect_slicer, launch_slicer, payload.get("slicer_path"),
                generate_from_design,
                _printer_profile(payload),
            ))

    def print_complete(payload):
        """One local complete Space handoff: bins + placed spacers + connectors
        under one truthful preflight and ONE slicer launch. (Fix 096 C11.)

        Sequence (fixed):
          1. Slicer preflight — before any file is written.
          2. One truthful preflight: C6's selected_blocking_problems over
             every placed bin in the drawer.
          3. Bin files via prepare_inventory_bins (only rows without current
             files are generated from their design source).
          4. Placed spacer files already on disk. The literal eligibility
             predicate: a spacer-kind row referenced by a placement in this
             drawer whose "file" names a real .3mf directly inside the Space
             folder. Rows whose file is missing are named in notes and
             skipped — they are NOT generated here.
          5. The Space's required connectors via _space_connectors.
          6. ONE launch_slicer call with every file.
          7. Promotion (one authority, consistent with C1): every bin row and
             every spacer row handed to the slicer becomes Printed via
             mark_printed_rows. Anything not handed off stays as it was.
        """
        if hosted:
            raise ValueError("Hosted Wavefinity saves files to your folder instead of opening a local slicer.")
        if detect_slicer is None or launch_slicer is None:
            raise ValueError("printing is not available here")
        with geometry_lock:
            out_dir = folder(payload)
            inv = load_inventory(out_dir)
            layout, bins = inv["layout"], inv["bins"]
            drawer = find_drawer(layout, payload.get("drawer_id"))
            # 1. Slicer preflight first.
            slicer = detect_slicer(payload.get("slicer_path"))
            if slicer is None or not Path(slicer).is_file():
                raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")
            # 2. One truthful preflight over every placed bin in the drawer.
            by_id = {one["id"]: one for one in bins}
            counts: dict[str, int] = {}
            for placement in drawer.get("placements") or []:
                one = by_id.get(placement.get("bin"))
                if (one is not None and one.get("kind") in ("bin", "b4b")
                        and one.get("status") != "printed"):
                    counts[one["id"]] = counts.get(one["id"], 0) + 1
            blocked = selected_blocking_problems(layout, bins, counts)
            if blocked:
                raise ValueError(blocking_problem_copy(bins, blocked))
            # 3. Bin files.
            prepared = prepare_inventory_bins(out_dir, list(counts), generate_from_design)
            if prepared["failed"]:
                raise ValueError(
                    "The bins could not be prepared: "
                    + _prepare_failure_text(prepared, slicer=True)
                    + " Bambu Studio was not opened.")
            rows_files = prepared["files"]
            specs = prepared["specs"]
            inventory = prepared["inventory"]
            # 4. Placed spacer copies already on disk. One Inventory spacer
            # row may have several physical placements; launch one file per
            # placement while promoting the row identity only once.
            current_drawer = find_drawer(
                inventory["layout"],
                payload.get("drawer_id"),
            )
            current_by_id = {
                str(one["id"]): one
                for one in inventory["bins"]
            }
            spacer_rows_printed: set[str] = set()
            skipped_spacers: set[str] = set()
            spacer_copies = 0
            launch_files: list[Path] = []
            for bin_id in counts:
                launch_files.extend(rows_files[bin_id])
            for placement in current_drawer.get("placements") or []:
                row_id = str(placement.get("bin") or "")
                one = current_by_id.get(row_id)
                if one is None or one.get("kind") not in SPACER_KINDS:
                    continue
                safe = _safe_row_file(out_dir, one.get("file") or "")
                if safe is None:
                    skipped_spacers.add(_label(one))
                    continue
                launch_files.append(safe)
                spacer_rows_printed.add(row_id)
                spacer_copies += 1
            # 5. Space connectors.
            try:
                connector_counts, notes = _space_connectors(out_dir, inventory["layout"], inventory["bins"])
            except Exception as error:
                return _batch_partial(
                    prepared, "connectors",
                    f"Bin and spacer files were prepared, but the Space connectors could not be made: {error}. "
                    "Bambu Studio was not opened.",
                    notes=[
                        f"Spacer {name} has no file yet and was skipped — "
                        "open Spacers and choose Generate to remake it."
                        for name in sorted(skipped_spacers)
                    ],
                )
            for name, count in connector_counts.items():
                launch_files.extend([out_dir / name] * count)
            if skipped_spacers:
                notes.extend(
                    f"Spacer {name} has no file yet and was skipped — "
                    "open Spacers and choose Generate to remake it."
                    for name in sorted(skipped_spacers)
                )
            # 6. Fit check, then one launch: every file handed to the slicer
            # must fit the active printer; a fit failure fails before launch.
            # Truthful count payload for the preflight branch (defined here so
            # the fit-failure partial cannot hit a NameError).
            result_counts = {
                "bin_copies": sum(counts.values()),
                "spacer_copies": spacer_copies,
                "connector_counts": connector_counts,
                "connector_copies": sum(connector_counts.values()),
            }
            if not launch_files:
                raise ValueError("There is nothing in this Space left to print.")
            fit_issues: list[str] = []
            for path in dict.fromkeys(launch_files):
                fit_issues.extend(print_file_fit_issues(path, _printer_profile(payload)))
            if fit_issues:
                return _batch_partial(
                    prepared, "preflight",
                    "A file does not fit the active printer:\n" + "\n".join(fit_issues),
                    **result_counts, notes=notes)
            try:
                project_path = launch_slicer(Path(slicer), launch_files)
            except Exception as error:
                return _batch_partial(
                    prepared, "slicer",
                    f"Files were prepared, but Bambu Studio did not open: {error}. The files were kept.",
                    notes=notes)
            # 7. One promotion authority (C1's rule): handed off == Printed.
            try:
                saved = mark_printed_rows(
                    out_dir,
                    [*counts, *sorted(spacer_rows_printed)],
                    specs,
                )
            except Exception as error:
                return _batch_partial(
                    prepared, "status",
                    f"Bambu Studio opened, but the printed status could not be recorded: {error}. "
                    "Check the Inventory rows.",
                    notes=notes)
            return {
                **saved,
                "files": [str(path) for path in launch_files],
                "bin_copies": sum(counts.values()),
                "spacer_copies": spacer_copies,
                "connector_counts": connector_counts,
                "connector_copies": sum(connector_counts.values()),
                "notes": notes,
                "slicer": str(slicer),
                "project": str(project_path) if project_path else None,
            }

    def save_bins(payload):
        if hosted:
            raise ValueError("Saving bin files in bulk is available in local Wavefinity.")
        selection = payload.get("selection") or []
        row_ids = list(selection.keys()) if isinstance(selection, dict) else list(selection)
        with geometry_lock:
            return with_rules(save_inventory_bins(
                folder(payload), row_ids, bool(payload.get("include_connectors", False)),
                generate_from_design,
            ))

    def connectors(payload):
        if hosted:
            import base64
            import tempfile
            with geometry_lock, tempfile.TemporaryDirectory(prefix="wavefinity-hosted-connectors-") as tmp:
                result = generate_connectors(
                    Path(tmp), payload["layout"], payload.get("bins") or [],
                    payload.get("drawer_id"))
                files_base64 = {}
                for one in result.get("connectors", []):
                    files_base64[one["file"]] = base64.b64encode(
                        (Path(tmp) / one["file"]).read_bytes()).decode("ascii")
                result["files_base64"] = files_base64
                return result
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))


    return {
        "/api/drawer/load": load,
        "/api/drawer/save": save,
        "/api/drawer/design-source/save": save_design_source,
        "/api/drawer/design-source/duplicate": duplicate_design_source,
        "/api/drawer/design-source/status": change_design_status,
        "/api/drawer/report": report,
        "/api/drawer/surface-fill": surface_fill,
        "/api/drawer/surface-fill/create": surface_fill_create,
        "/api/drawer/spacers": spacers,
        "/api/drawer/spacers/generate": spacers_generate,
        "/api/drawer/spacers/refresh": spacers_refresh,
        "/api/drawer/connectors": connectors,
        "/api/drawer/print-complete": print_complete,
        "/api/drawer/print-spacers": print_spacers_only,
        "/api/drawer/print-bins": print_bins,
        "/api/drawer/save-bins": save_bins,
    }
