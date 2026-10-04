"""Inventory merge/save helpers: file reaping, merge rules and text payload wrappers."""

from __future__ import annotations

from datetime import datetime
import copy
from pathlib import Path
import re
from typing import Any, Iterable

from ._rows import (
    INVENTORY_LOCK,
    KINDS,
    STACK_MODES,
    EDITABLE,
    MAX_QTY,
    _KEEP,
    resolve_inventory_path,
    _text,
    _number,
    _object_height,
    next_bin_id,
    parse_inventory,
    render_inventory,
    _read,
    _prune_layout,
    design_specs,
    _next_simple_bin_name,
    _duplicate_design_source,
    _change_design_status,
)


def save_design_source_text(
    text: str, *, title: str = "Wavefinity", design: dict[str, Any], record: dict[str, Any],
    row_id: str | None = None, available_filenames: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into browser-owned text and return replacement text, per ``save_design_source``."""
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        bins, layout, used_id, stale = _merge_design_source(
            current, design=design, record=record, row_id=row_id,
            available_filenames=available_filenames)
        rendered = render_inventory(str(title or "Wavefinity"), bins, layout)
        result = _text_payload(rendered, str(title or "Wavefinity"), parse_inventory(rendered))
        return {**result, "row_id": used_id, "design": design_specs(result["layout"])[used_id],
                "files_became_stale": stale}


def duplicate_design_source_text(text: str, row_id: str, *, title: str = "Wavefinity") -> dict[str, Any]:
    with INVENTORY_LOCK:
        current = parse_inventory(str(text or ""))
        bins, layout, used_id, design = _duplicate_design_source(current, row_id)
        rendered = render_inventory(title, bins, layout)
        return {**_text_payload(rendered, title, parse_inventory(rendered)), "row_id": used_id, "design": design}


def change_design_status_text(text: str, row_id: str, action: str,
                              file_text: str | None = None, *, title: str = "Wavefinity",
                              expected_design: dict | None = None,
                              available_filenames: Iterable[str] | None = None) -> dict[str, Any]:
    with INVENTORY_LOCK:
        current = parse_inventory(str(text or ""))
        bins, layout = _change_design_status(current, row_id, action, file_text, expected_design)
        cleanup_files: list[str] = []
        # A real Save or successful slicer Print establishes a new current file
        # set. Manual mark_printed is bookkeeping-only and owns no file cleanup.
        if action in ("saved", "printed"):
            layout, cleanup_files = _reap_superseded_names(
                bins, layout, row_id, available_filenames)
        rendered = render_inventory(title, bins, layout)
        return {
            **_text_payload(rendered, title, parse_inventory(rendered)),
            "cleanup_files": cleanup_files,
        }


def _row_file_names(folder: Path | None, row: dict[str, Any]) -> list[str]:
    """The real generated file names a row's File cell owns, else none.

    Only names that resolve to real .3mf files directly in ``folder`` are
    trusted; an unverifiable File cell is never turned into delete targets.
    """
    text = str(row.get("file") or "").strip()
    if not text or folder is None:
        return []
    from organizer_drawer import inventory_row_files
    try:
        return [path.name for path in inventory_row_files(folder, row)]
    except ValueError:
        # Ownership is unprovable (missing/ambiguous); ", " may be part of a
        # legal file name, so never guess by splitting. Preserve the files.
        return []


def _claimed_names(folder: Path | None, row: dict[str, Any]) -> set[str]:
    """Every file name a row's File cell may be claiming, never fewer than it owns.

    A resolvable cell contributes exactly the files ``inventory_row_files``
    resolves (which understands names that themselves contain ", "). A cell
    that cannot be resolved - ambiguous, or naming a missing file - is treated
    conservatively: every contiguous ", "-joined run of its pieces counts as
    claimed, so cleanup can never delete something the row might still own.
    """
    text = str(row.get("file") or "").strip()
    if not text:
        return set()
    names = {text}
    if folder is not None:
        from organizer_drawer import inventory_row_files
        try:
            names.update(path.name for path in inventory_row_files(folder, row))
            return names
        except ValueError:
            pass
    pieces = text.split(", ")
    for start in range(len(pieces)):
        for end in range(start + 1, len(pieces) + 1):
            names.add(", ".join(pieces[start:end]).strip())
    return names


def _referenced_names(folder: Path | None, bins: list[dict[str, Any]], skip_id: str) -> set[str]:
    """Every file name any other row could still be using."""
    names: set[str] = set()
    for one in bins:
        if one["id"] != skip_id:
            names |= _claimed_names(folder, one)
    return names


def _stale_files(layout: dict[str, Any] | None) -> dict[str, list[str]]:
    """Old generated files per row that an edit made non-current (Fix 061 F6)."""
    raw = layout.get("stale_files") if isinstance(layout, dict) else None
    if not isinstance(raw, dict):
        return {}
    return {str(key): [str(name) for name in value if isinstance(name, str)]
            for key, value in raw.items() if isinstance(value, list)}


def _reap_superseded(
    folder: Path, bins: list[dict[str, Any]], layout: dict[str, Any] | None, row_id: str,
) -> tuple[dict[str, Any] | None, list[Path]]:
    """Retire a row's tracked stale files once it has a new current file set.

    Returns the layout with that row's stale entry dropped and the physical
    files that are safe to delete: tracked as this row's old outputs, not part
    of its new set, and not referenced by any other Inventory row.
    """
    if not isinstance(layout, dict):
        return layout, []
    stale = _stale_files(layout)
    if row_id not in stale:
        return layout, []
    tracked = stale.pop(row_id)
    target = next((one for one in bins if one["id"] == row_id), None)
    current = _claimed_names(folder, target) if target is not None else set()
    referenced = _referenced_names(folder, bins, row_id)
    from organizer_drawer import _safe_row_file
    root = Path(folder).expanduser().resolve()
    doomed: list[Path] = []
    for name in dict.fromkeys(tracked):
        if name in current or name in referenced:
            continue
        found = _safe_row_file(root, name)
        if found is not None:
            doomed.append(found)
    layout = {**layout}
    if stale:
        layout["stale_files"] = stale
    else:
        layout.pop("stale_files", None)
    return layout, doomed


def _reap_superseded_names(
    bins: list[dict[str, Any]], layout: dict[str, Any] | None,
    row_id: str, available_filenames: Iterable[str] | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Hosted equivalent of _reap_superseded: plan conservative browser deletes.

    ``available_filenames`` None means no folder snapshot was supplied, so
    nothing is proven gone; an explicit (even empty) list is a known snapshot.
    """
    if not isinstance(layout, dict):
        return layout, []
    stale = _stale_files(layout)
    if row_id not in stale:
        return layout, []
    tracked = list(dict.fromkeys(stale.pop(row_id)))
    availability_known = available_filenames is not None
    available = {
        name for name in (available_filenames or ())
        if isinstance(name, str) and name == name.strip()
        and Path(name).name == name and not Path(name).is_absolute()
        and "/" not in name and "\\" not in name and name.lower().endswith(".3mf")
    }
    target = next((one for one in bins if one["id"] == row_id), None)
    current = _claimed_names(None, target) if target is not None else set()
    referenced = _referenced_names(None, bins, row_id)
    cleanup = [
        name for name in tracked
        if name in available and name not in current and name not in referenced
    ]
    # The cleanup plan is only a plan: the browser may not have deleted
    # anything. Forget only names reclaimed as current or proven gone by a
    # known snapshot; everything else (including referenced names) stays tracked.
    remaining = [
        name for name in tracked
        if name not in current and (name in available or not availability_known)
    ]
    if remaining:
        stale[row_id] = remaining
    next_layout = {**layout}
    # Keep stale_files authoritative even when empty. DL.adopt (D-7) sees the
    # explicit key and clears its cached stale map after this exact status response.
    next_layout["stale_files"] = stale
    return next_layout, cleanup


def _delete_files(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass  # a locked or already-removed old file must never fail the save


def _deletion_file_names(current: dict[str, Any], ids: set[str], available: Iterable[str]) -> list[str]:
    """Plan only proven row-owned files from the pre-delete folder snapshot."""
    from organizer_drawer import inventory_row_file_names

    rows = {row["id"]: row for row in current["bins"]}
    for row_id in ids:
        if row_id not in rows:
            raise ValueError(f"no bin {row_id!r} in the inventory")
    names = {name for name in available if isinstance(name, str) and name == name.strip()
             and Path(name).name == name and not Path(name).is_absolute()
             and "/" not in name and "\\" not in name and name.lower().endswith(".3mf")}
    stale = _stale_files(current["layout"])
    protected: set[str] = set()
    candidates: set[str] = set()
    for row_id, row in rows.items():
        if row_id in ids:
            try:
                candidates.update(inventory_row_file_names(names, row))
            except ValueError:
                pass
            candidates.update(name for name in stale.get(row_id, []) if name in names)
        else:
            # A survivor's unresolved cell may still claim any contiguous
            # comma-joined run. Never turn that uncertainty into deletion.
            text = str(row.get("file") or "").strip()
            if text:
                protected.add(text)
                try:
                    protected.update(inventory_row_file_names(names, row))
                except ValueError:
                    parts = text.split(", ")
                    for start in range(len(parts)):
                        for end in range(start + 1, len(parts) + 1):
                            protected.add(", ".join(parts[start:end]).strip())
            protected.update(stale.get(row_id, []))
    return sorted(candidates - protected)


def _merge_design_source(
    current: dict[str, Any], *, design: dict[str, Any], record: dict[str, Any], row_id: str | None,
    folder: Path | None = None, available_filenames: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any], str, bool]:
    bins = current["bins"]
    by_id = {one["id"]: one for one in bins}
    target = by_id.get(row_id) if row_id else None
    layout = current["layout"] if isinstance(current["layout"], dict) else {}
    canonical = copy.deepcopy(design)
    name = _text(record.get("name"))
    if target is None and not name:
        name = _next_simple_bin_name(bins)
        canonical["part_name"] = name
    row_fields = {
        "kind": record.get("kind", "bin"),
        "name": name,
        "x": float(record["x"]), "y": float(record["y"]), "z": float(record["z"]),
        "stack": record.get("stack", "none"),
        "wall": record.get("wall"),
        "object_height_mm": _object_height(record.get("object_height_mm")),
        "label": record.get("label", ""),
        "interior": record.get("interior", ""),
        "pegboard_standard": record.get("pegboard_standard", ""),
        "cleat_x": record.get("cleat_x", "auto"),
        "cleat_y": record.get("cleat_y", "auto"),
    }
    previous = design_specs(layout).get(target["id"]) if target is not None else None
    changed = previous != canonical
    def printable_design(value):
        if not isinstance(value, dict):
            return value
        result = copy.deepcopy(value)
        for feature in result.get("layout", {}).get("features", []):
            if isinstance(feature, dict):
                feature.pop("reference_object", None)
        return result
    printable_changed = printable_design(previous) != printable_design(canonical)
    files_became_stale = False
    stale = _stale_files(layout)
    if target is not None:
        if changed and printable_changed:
            if str(target.get("file") or "").strip():
                files_became_stale = True
                # Remember the old outputs so a later successful refresh can
                # retire them; until then they are never treated as current.
                kept = stale.get(target["id"], [])
                if folder is not None:
                    proven = _row_file_names(folder, target)
                else:
                    from organizer_drawer import inventory_row_file_names
                    try:
                        proven = inventory_row_file_names(available_filenames, target)
                    except ValueError:
                        proven = []
                if proven or kept:
                    stale[target["id"]] = list(dict.fromkeys(kept + proven))
            target.update(row_fields)
            target.update({"file": "", "status": "in_design", "qty": 0})
        used_id = target["id"]
    else:
        used_id = next_bin_id(bins)
        bins.append({
            "id": used_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "boundary": "",
            "qty": 0,
            "status": "in_design",
            "file": "",
            **row_fields,
        })
    layout = {**layout, "design_specs": {**design_specs(layout), used_id: canonical}}
    if stale:
        layout["stale_files"] = stale
    layout = _prune_layout(layout, bins)
    return bins, layout, used_id, files_became_stale


def _payload(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": str(path),
        "folder": str(path.parent),
        "exists": path.is_file(),
        "bins": data["bins"],
        "layout": data["layout"],
        "warnings": data["warnings"],
    }


def _text_payload(text: str, title: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": "",
        "folder": "",
        "exists": bool(str(text or "").strip()),
        "bins": data["bins"],
        "layout": data["layout"],
        "warnings": data["warnings"],
        "inventory_text": render_inventory(title, data["bins"], data["layout"]),
    }


def load_inventory(output_dir: Path | str) -> dict[str, Any]:
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=False)
        return _payload(path, _read(path))


def load_inventory_text(text: str, *, title: str = "Wavefinity") -> dict[str, Any]:
    """Read browser-owned inventory text without inventing a server path."""
    raw = str(text or "")
    with INVENTORY_LOCK:
        return _text_payload(raw, str(title or "Wavefinity"), parse_inventory(raw))


def _clean_bin(raw: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key in EDITABLE:
        if key not in raw:
            continue
        if key == "name":
            clean["name"] = str(raw["name"] or "").strip()[:80]
        elif key == "stack":
            mode = str(raw["stack"] or "none").strip().lower()
            if mode not in STACK_MODES:
                raise ValueError(f"stacking must be one of {', '.join(STACK_MODES)}")
            clean["stack"] = mode
        elif key == "qty":
            clean["qty"] = max(0, min(MAX_QTY, int(_number(raw["qty"], 0))))
        elif key == "object_height_mm":
            clean[key] = _object_height(raw[key])
        else:
            value = _number(raw[key])
            if value <= 0:
                raise ValueError(f"bin {key.upper()} must be a positive number of mm")
            clean[key] = value
    if not partial:
        for axis in ("x", "y", "z"):
            if axis not in clean:
                raise ValueError(f"a new bin needs its {axis.upper()} size")
    return clean


def _keep_current_cabinet(current: Any, submitted: dict[str, Any]) -> dict[str, Any]:
    """A Storage Drawers cabinet is changed only by its mutation owner.

    An ordinary layout save queued before an Add/Delete/Reconfigure must not
    resurrect the old drawer list or descriptors: a different drawer set is
    refused, and the saved cabinet definition/projection always wins.
    """
    space = current.get("space") if isinstance(current, dict) else None
    if not isinstance(space, dict) or space.get("kind") != "storage_drawers":
        return submitted
    saved = {one.get("id"): one for one in current.get("drawers") or [] if isinstance(one, dict)}
    sent = [one for one in submitted.get("drawers") or [] if isinstance(one, dict)]
    if [one.get("id") for one in sent] != [one.get("id") for one in current.get("drawers") or []]:
        raise ValueError("This cabinet changed since the layout was loaded. Reload the Space and try again.")
    drawers = []
    for one in sent:
        fixed = {key: saved[one["id"]].get(key) for key in ("name", "width", "depth", "height", "clearance", "boundary")}
        drawers.append({**one, **fixed})
    return {**submitted, "space": space, "drawers": drawers}


def _merge_inventory(
    current: dict[str, Any], *,
    layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    new_bin_specs: Iterable[Any] = (),
    delete_ids: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict | None]:
    if layout is not _KEEP and layout is not None and not isinstance(layout, dict):
        raise ValueError("drawer layout must be an object")
    bins = current["bins"]
    existing_ids = {one["id"] for one in bins}
    chosen = current["layout"] if layout is _KEEP else layout
    if layout is not _KEEP and isinstance(chosen, dict):
        chosen = _keep_current_cabinet(current["layout"], chosen)
    if isinstance(chosen, dict):
        # Layout saves may have been queued before a design autosave. The
        # Inventory source map always comes from the latest file transaction.
        submitted_specs = dict(design_specs(chosen))
        chosen = {**chosen, "design_specs": dict(design_specs(current["layout"]))}
        # Stale-file tracking is server-owned like the design sources.
        chosen.pop("stale_files", None)
        if _stale_files(current["layout"]):
            chosen["stale_files"] = _stale_files(current["layout"])
    by_id = {one["id"]: one for one in bins}
    for update in bin_updates or ():
        target = by_id.get(str(update.get("id", "")))
        if target is None:
            raise ValueError(f"no bin {update.get('id')!r} in the inventory")
        clean = _clean_bin(update, partial=True)
        if target["id"] in design_specs(chosen) and clean:
            raise ValueError("Edit this bin through its canonical Designer source")
        if "qty" in clean and target.get("kind") in ("bin", "b4b", "manual"):
            clean["qty"] = min(1, clean["qty"])
        target.update(clean)
        if "qty" in clean:
            target["status"] = "printed" if clean["qty"] > 0 else ("saved" if target.get("file") else "in_design")
    gone = {str(one) for one in delete_ids or ()}
    bins = [one for one in bins if one["id"] not in gone]
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for raw in new_bins or ():
        clean = _clean_bin(raw, partial=False)
        kind = str(raw.get("kind") or "manual")
        boundary = str(raw.get("boundary") or "")
        wanted = str(raw.get("id") or "")
        taken = {one["id"] for one in bins}
        raw_wall = _number(raw.get("wall")) if _text(raw.get("wall")) else None
        bins.append({
            "id": wanted if re.fullmatch(r"B\d+", wanted) and wanted not in taken else next_bin_id(bins),
            "date": now,
            "kind": kind if kind in KINDS else "manual",
            "boundary": boundary if boundary == "edge" else "",
            "name": clean.get("name", ""),
            "x": clean["x"], "y": clean["y"], "z": clean["z"],
            "stack": clean.get("stack", "none"),
            "wall": raw_wall if raw_wall and raw_wall > 0 else None,
            "object_height_mm": clean.get("object_height_mm"),
            "qty": min(1, clean.get("qty", 1)) if kind in ("bin", "b4b", "manual") else clean.get("qty", 1),
            "status": ("printed" if clean.get("qty", 1) > 0 else
                       "saved" if raw.get("file") else "in_design"),
            "file": str(raw.get("file") or ""),
            "label": str(raw.get("label") or ""),
            "interior": str(raw.get("interior") or ""),
            "pegboard_standard": str(raw.get("pegboard_standard") or "").lower(),
            "cleat_x": str(raw.get("cleat_x") or "auto").lower(),
            "cleat_y": str(raw.get("cleat_y") or "auto").lower(),
        })
    if isinstance(chosen, dict):
        for row in bins:
            if row["id"] not in existing_ids and row["id"] in submitted_specs:
                chosen["design_specs"][row["id"]] = submitted_specs[row["id"]]
    # Fix 096 A2: specs supplied alongside new rows (parallel to new_bins)
    # attach atomically here, and a new ordinary-bin or B4B row without its
    # canonical editable source is an operation failure, not a silent gap.
    # ("manual", "spacer" and other kinds never have a design source.)
    supplied = list(new_bin_specs or ())
    created = [row for row in bins if row["id"] not in existing_ids]
    if isinstance(chosen, dict):
        for row, spec in zip(created, supplied):
            if isinstance(spec, dict):
                chosen["design_specs"][row["id"]] = spec
    final_specs = design_specs(chosen) if isinstance(chosen, dict) else {}
    for row in created:
        if row.get("kind") in ("bin", "b4b") and not isinstance(final_specs.get(row["id"]), dict):
            raise ValueError(
                f"new row {row['id']} needs its editable design source; nothing was recorded")
    return bins, _prune_layout(chosen, bins)


def save_inventory_text(
    text: str, *, title: str = "Wavefinity", layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    new_bin_specs: Iterable[Any] = (),
    delete_ids: Iterable[str] = (),
    available_filenames: Iterable[str] = (),
    protected_files: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into browser-owned text and return replacement text."""
    delete_ids = tuple(delete_ids or ())
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        ids = {str(one) for one in delete_ids or ()}
        protected = {str(one) for one in protected_files or ()}
        cleanup = [
            name for name in (
                _deletion_file_names(current, ids, available_filenames) if ids else []
            )
            if name not in protected
        ]
        bins, chosen = _merge_inventory(
            current, layout=layout, bin_updates=bin_updates,
            new_bins=new_bins, new_bin_specs=new_bin_specs, delete_ids=delete_ids,
        )
        rendered = render_inventory(str(title or "Wavefinity"), bins, chosen)
        result = _text_payload(rendered, str(title or "Wavefinity"), parse_inventory(rendered))
        if ids:
            result["cleanup_files"] = cleanup
        return result
