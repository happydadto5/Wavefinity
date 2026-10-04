"""The folder's inventory file: ``Wavefinity bins.md`` in the save folder.

A persistent save folder keeps this by default - a normal untyped Design
folder may explicitly opt out, independently of whether it is a typed Space.
Every generated bin/B4B is appended here when inventory is enabled. A typed
Drawer, Surface, Portable, or Pegboard Space stores its layout in this same file rather
than a separate one; a Space requires inventory, but inventory does not
require a Space. Legacy Box metadata remains readable as migration input
only - see ``normalise_space_definition``'s ``allow_legacy``. The file has
two parts:

* a Markdown table, one row per bin. ``Status`` tracks its current printable
  files; ``Qty`` remains a 0/1 bridge for older layout callers.
* a ``## Drawer layout`` section holding one fenced JSON block: the drawers,
  where each printed copy sits, and the layout settings.  The Layout view owns
  that block and rewrites it on save.  The table above it stays hand-editable.

Rows are keyed by a stable ``ID`` (B1, B2, ...) so placements survive the table
being re-sorted or edited by hand.  A file from before the Layout view (seven
columns, no ID or Qty) is read as-is and upgraded the first time it is written,
with a one-off ``.bak`` copy left beside it.

Every write re-reads the file under a lock and merges, so the generator logging
a new bin while the Layout view is open never loses either change.
"""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    B4B_FRONT_LABEL_STYLES,
    B4B_LABEL_LOCATIONS,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
    B4B_LID_HEADROOM_CHOICES,
    BASE_UNIT,
    MIN_HEIGHT_ABOVE_BASE,
)
from organizer_product_rules import (
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    SURFACE_TRIM_HEIGHTS,
    surface_maximums,
)
from organizer_pegboard import normalise_pegboard_space
from organizer_storage_drawers import (
    normalise_storage_drawers_definition,
    plan_add_drawer,
    plan_delete_drawer,
    plan_reconfigure,
    prepare_new_storage_drawers_definition,
    reconcile_storage_drawers_layout,
    reset_storage_drawers_definition,
)

from datetime import datetime
import copy
import json
import math
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Iterable

from ._rows import (
    INVENTORY_LOCK,
    INVENTORY_FILENAME,
    LAYOUT_HEADING,
    COLUMNS,
    KINDS,
    STACK_MODES,
    EDITABLE,
    MAX_QTY,
    DEFAULT_NEW_BIN_QTY,
    SPACE_KINDS,
    LEGACY_SPACE_KINDS,
    _HEADER_KEYS,
    _KEEP,
    inventory_path,
    InventoryMigrationError,
    resolve_inventory_path,
    _cells,
    _header_key,
    _text,
    _number,
    _object_height,
    infer_kind,
    infer_name,
    _normalise,
    _assign_ids,
    next_bin_id,
    _migrate_drawer_boundaries,
    parse_inventory,
    _cell,
    _row,
    _compact_json,
    render_inventory,
    _read,
    _title,
    _unit_offset,
    _prune_layout,
    design_specs,
    _next_simple_bin_name,
    _duplicate_name,
    _duplicate_design_source,
    _change_design_status,
)
from ._merge import (
    save_design_source_text,
    duplicate_design_source_text,
    change_design_status_text,
    _row_file_names,
    _claimed_names,
    _referenced_names,
    _stale_files,
    _reap_superseded,
    _reap_superseded_names,
    _delete_files,
    _deletion_file_names,
    _merge_design_source,
    _payload,
    _text_payload,
    load_inventory,
    load_inventory_text,
    _clean_bin,
    _keep_current_cabinet,
    _merge_inventory,
    save_inventory_text,
)
from ._space import (
    legacy_layout_space,
    STORAGE_BOX_LABEL_LIMIT,
    STORAGE_BOX_MIN_MATERIAL_MM,
    STORAGE_BOX_MAX_MATERIAL_MM,
    storage_box_defaults,
    _storage_box_flag,
    _storage_box_choice,
    _storage_box_material,
    normalise_storage_box,
    normalise_space_definition,
    _setup_space_layout,
    _reconcile_surface_bases,
    _carry_storage_box,
    _configured_space_definition,
    _refuse_stranding_surface_change,
    _plan_cabinet_mutation,
    storage_drawers_mutate_text,
    configure_space_text,
)

def _write(path: Path, bins: list[dict[str, Any]], layout: dict | None, legacy: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".bak")
    if legacy and path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(render_inventory(_title(path, layout), bins, layout), encoding="utf-8")
    temp.replace(path)


def update_bin_file(output_dir: Path | str, row_id: str, file_text: str,
                    expected_design: dict | None = None) -> dict[str, Any]:
    """Set one row's File cell directly, outside the normal hand-editable fields.

    Used only when Generate/Print resolves a spec-only row's files on demand
    (Fix 034 F2): the row keeps its Qty 0 until the slicer handoff succeeds,
    but the generated file names are persisted immediately so a retry does
    not regenerate needlessly.
    """
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins = current["bins"]
        target = next((one for one in bins if one["id"] == row_id), None)
        if target is None:
            raise ValueError(f"no bin {row_id!r} in the inventory")
        if expected_design is not None and design_specs(current["layout"]).get(row_id) != expected_design:
            raise ValueError("This bin changed while its files were being prepared")
        target.update({"file": file_text, "status": "saved", "qty": 0})
        layout, superseded = _reap_superseded(path.parent, bins, current["layout"], row_id)
        _write(path, bins, layout, current["legacy"])
        _delete_files(superseded)
        return _payload(path, _read(path))


def save_design_source(
    output_dir: Path | str, *, design: dict[str, Any], record: dict[str, Any], row_id: str | None = None,
) -> dict[str, Any]:
    """Atomically create/update one canonical design source row + its ``design_specs`` entry.

    ``record`` is the caller-derived Inventory row fields (already validated
    server-side) for the design being saved; ``design`` is the exact canonical
    design JSON to store as that row's editable source. ``row_id`` updates that
    existing row in place, including a Printed row. Returns the fresh inventory/layout payload
    plus the ``row_id`` actually used.
    """
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins, layout, used_id, stale = _merge_design_source(
            current, design=design, record=record, row_id=row_id, folder=path.parent)
        _write(path, bins, layout, current["legacy"])
        result = _payload(path, _read(path))
        return {**result, "row_id": used_id, "design": design_specs(result["layout"])[used_id],
                "files_became_stale": stale}


def duplicate_design_source(output_dir: Path | str, row_id: str) -> dict[str, Any]:
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins, layout, used_id, design = _duplicate_design_source(current, row_id)
        _write(path, bins, layout, current["legacy"])
        return {**_payload(path, _read(path)), "row_id": used_id, "design": design}


def change_design_status(output_dir: Path | str, row_id: str, action: str,
                         file_text: str | None = None, expected_design: dict | None = None) -> dict[str, Any]:
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins, layout = _change_design_status(current, row_id, action, file_text, expected_design)
        if action == "mark_not_printed":
            target = next(one for one in bins if one["id"] == row_id)
            if target["file"]:
                try:
                    from organizer_drawer import inventory_row_files
                    inventory_row_files(path.parent, target)
                except ValueError:
                    target.update({"file": "", "status": "in_design", "qty": 0})
        superseded: list[Path] = []
        # A real Save or successful slicer Print establishes a new current file
        # set and may retire this row's tracked superseded outputs. Manual
        # mark_printed only changes Inventory bookkeeping and owns no file work.
        if action in ("saved", "printed"):
            layout, superseded = _reap_superseded(path.parent, bins, layout, row_id)
        _write(path, bins, layout, current["legacy"])
        _delete_files(superseded)
        return _payload(path, _read(path))


def mark_printed_rows(output_dir: Path | str, row_ids: Iterable[str],
                      expected_specs: dict[str, Any]) -> dict[str, Any]:
    """Mark a successful bulk slicer handoff in one Inventory write."""
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins = current["bins"]
        by_id = {one["id"]: one for one in bins}
        specs = design_specs(current["layout"])
        for row_id in row_ids:
            target = by_id.get(row_id)
            if target is None:
                raise ValueError(f"no bin {row_id!r} in the inventory")
            if row_id in expected_specs and specs.get(row_id) != expected_specs[row_id]:
                raise ValueError(f"bin {row_id} changed while its files were being prepared")
            target.update({"status": "printed", "qty": 1})
        _write(path, bins, current["layout"], current["legacy"])
        return _payload(path, _read(path))


def save_inventory(
    output_dir: Path | str, *, layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    new_bin_specs: Iterable[Any] = (),
    delete_ids: Iterable[str] = (),
    protected_files: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into the file on disk and return the fresh contents."""
    delete_ids = tuple(delete_ids or ())
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        ids = {str(one) for one in delete_ids or ()}
        root = path.parent.resolve()
        available = [entry.name for entry in root.iterdir() if entry.is_file() and
                     entry.resolve().parent == root] if ids else []
        protected = {str(one) for one in protected_files or ()}
        cleanup = [
            name for name in (_deletion_file_names(current, ids, available) if ids else [])
            if name not in protected
        ]
        bins, chosen = _merge_inventory(
            current, layout=layout, bin_updates=bin_updates,
            new_bins=new_bins, new_bin_specs=new_bin_specs, delete_ids=delete_ids,
        )
        _write(path, bins, chosen, current["legacy"])
        failed = []
        if cleanup:
            from organizer_drawer import _safe_row_file
            for name in cleanup:
                found = _safe_row_file(root, name)
                if found is None:
                    continue  # Already removed, or no longer a safe direct child.
                try:
                    found.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    failed.append(name)
        result = _payload(path, _read(path))
        if failed:
            result["cleanup_failed"] = failed
        return result


def append_bin(
    output_dir: Path | str,
    *,
    file: str,
    x: float,
    y: float,
    z: float,
    label: str = "",
    interior: str = "",
    name: str = "",
    kind: str = "bin",
    stack: str = "none",
    wall: float | None = None,
    object_height_mm: float | None = None,
    qty: int | None = None,
    pegboard_standard: str = "",
    cleat_x: str | int = "auto",
    cleat_y: str | int = "auto",
    design_spec: dict[str, Any] | None = None,
) -> Path:
    """Log one generated bin as a new row, keeping everything else intact.

    An omitted ``qty`` means generated but not printed: 0. A real print path
    must pass ``qty=1`` (or another explicit physical count). A generate call
    that also has the canonical design (Fix 034's Generate/Print source
    preservation) passes ``design_spec`` so the new row's editable source is
    written atomically alongside the row itself.
    """
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins = current["bins"]
        if qty is None:
            qty = DEFAULT_NEW_BIN_QTY
        object_height_mm = _object_height(object_height_mm)
        if design_spec is not None:
            design_spec = {**design_spec, "layout": dict(design_spec.get("layout") or {})}
            if object_height_mm is None:
                object_height_mm = _object_height(design_spec["layout"].get("object_height_mm"))
            if int(qty) > 0 and design_spec["layout"].get("surface_base_mode") == "edge":
                design_spec["layout"]["surface_base_mode"] = "custom"
        new_id = next_bin_id(bins)
        # Fix 096 A2: an ordinary bin or B4B row must never be recorded without
        # its canonical editable source - a missing source is an operation
        # failure, not a silent gap.
        row_kind = kind if kind in KINDS else "bin"
        if row_kind in ("bin", "b4b") and design_spec is None:
            raise ValueError(
                "a new bin row needs its editable design source; nothing was recorded")
        bins.append({
            "id": new_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kind": row_kind,
            "name": name,
            "x": float(x), "y": float(y), "z": float(z),
            "stack": stack if stack in STACK_MODES else "none",
            "wall": float(wall) if wall and float(wall) > 0 else None,
            "object_height_mm": object_height_mm,
            "qty": min(1, max(0, int(qty))),
            "status": "printed" if int(qty) > 0 else "saved" if file else "in_design",
            "file": file,
            "label": label,
            "interior": interior,
            "pegboard_standard": str(pegboard_standard or "").lower(),
            "cleat_x": str(cleat_x or "auto").lower(),
            "cleat_y": str(cleat_y or "auto").lower(),
        })
        layout = current["layout"]
        if design_spec is not None:
            layout = layout if isinstance(layout, dict) else {}
            layout = {**layout, "design_specs": {**design_specs(layout), new_id: design_spec}}
        _write(path, bins, layout, current["legacy"])
    return path


def configure_space(
    output_dir: Path | str, *, raw_def: dict[str, Any], mode: str = "create", allow_legacy: bool = False
) -> dict[str, Any]:
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        layout = current["layout"] if isinstance(current["layout"], dict) else {}
        if mode == "create" and isinstance(layout.get("space"), dict):
            raise ValueError(f"this folder already holds the space {layout['space'].get('name')!r}")
        space_def = _configured_space_definition(raw_def, layout, mode, allow_legacy)
        _refuse_stranding_surface_change(current["bins"], layout, space_def, mode)
        _setup_space_layout(layout, space_def)
        if mode == "update" and space_def["kind"] == "surface":
            _reconcile_surface_bases(current["bins"], layout, space_def["z"])
        _write(path, current["bins"], layout, current["legacy"])
        return _payload(path, _read(path))


def storage_drawers_mutate(
    output_dir: Path | str, operation: str, *, drawer_id: Any = None, proposed: Any = None,
    space: Any = None,
) -> dict[str, Any]:
    """Serialized cabinet Add/Delete/Reconfigure on a local folder's Inventory."""
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        canonical, updated = _plan_cabinet_mutation(current, operation, drawer_id, proposed, space)
        _write(path, current["bins"], updated, current["legacy"])
        return {**_payload(path, _read(path)), "space": canonical}
