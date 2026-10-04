"""Wavefinity drawer inventory row files, preparation, saving and spacer staging."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Iterable
from organizer_inventory import design_specs, load_inventory, update_bin_file

from ._core import _label
from ._spacers import generate_connectors


# ---------------------------------------------------------------- bulk bin print


def _safe_row_file(root: Path, name: str) -> Path | None:
    """The real .3mf directly inside ``root`` called ``name``, else None."""
    if (not name or name != name.strip() or Path(name).name != name
            or Path(name).is_absolute() or "/" in name or "\\" in name
            or not name.lower().endswith(".3mf")):
        return None
    path = (root / name).resolve()
    return path if path.parent == root and path.is_file() else None


def inventory_row_file_names(available: Iterable[str], row: dict[str, Any]) -> list[str]:
    """Resolve a File cell only when one partition matches safe folder filenames."""
    names = {name for name in available if isinstance(name, str) and
             name == name.strip() and Path(name).name == name and
             not Path(name).is_absolute() and "/" not in name and "\\" not in name and
             name.lower().endswith(".3mf")}
    label = f"{_label(row)} ({row.get('id')})"
    text = str(row.get("file") or "").strip()
    if not text:
        raise ValueError(f"{label} has no generated file to print")
    if text in names:
        return [text]

    pieces = text.split(", ")
    partitions: list[list[str]] = []

    def walk(start: int, chosen: list[str]) -> None:
        if len(partitions) > 1:
            return
        if start == len(pieces):
            partitions.append(list(chosen))
            return
        for end in range(start + 1, len(pieces) + 1):
            found = ", ".join(pieces[start:end])
            if found in names:
                walk(end, chosen + [found])

    walk(0, [])
    unique = {tuple(part) for part in partitions}
    if len(unique) == 1:
        return partitions[0]
    if len(unique) > 1:
        raise ValueError(
            f"{label}: the File list can be read more than one way, so it cannot be printed safely")
    for token in pieces:
        token = token.strip()
        if not token:
            continue
        if (Path(token).name != token or Path(token).is_absolute()
                or "/" in token or "\\" in token):
            raise ValueError(f"{label}: unsafe file name {token!r}")
        if not token.lower().endswith(".3mf"):
            raise ValueError(f"{label}: {token} is not a .3mf file")
    raise ValueError(f"{label}: a recorded file is missing from the Space folder ({text})")


def inventory_row_files(output_dir: Path | str, row: dict[str, Any]) -> list[Path]:
    """The real generated files recorded by one row, using the shared resolver."""
    root = Path(output_dir).expanduser().resolve()
    available = [path.name for path in root.iterdir() if _safe_row_file(root, path.name)] if root.is_dir() else []
    return [root / name for name in inventory_row_file_names(available, row)]


def _copy_count(one: dict[str, Any], raw: Any) -> int:
    """A selected copy count: a whole number of at least 1, nothing looser."""
    label = _label(one)
    if isinstance(raw, bool) or isinstance(raw, float):
        raise ValueError(f"{label}: copies must be a whole number of 1 or more")
    if isinstance(raw, str):
        if not re.fullmatch(r"[0-9]+", raw.strip()):
            raise ValueError(f"{label}: copies must be a whole number of 1 or more")
        raw = int(raw.strip())
    if not isinstance(raw, int) or raw < 1:
        raise ValueError(f"{label}: copies must be a whole number of 1 or more")
    return raw


def prepare_inventory_bins(
    output_dir: Path | str,
    row_ids: Iterable[str],
    generate_from_design: Callable[[Path, dict[str, Any]], list[Path]] | None = None,
) -> dict[str, Any]:
    """The one "make these bins' files current" step behind batch Save and Print.

    Re-reads the Inventory from disk, reuses each row's current tracked files
    when they are present and valid, and generates only rows without current
    files from their canonical ``design_specs`` entry. Every newly generated
    row is recorded Saved / Qty 0 immediately, so work that already succeeded
    survives a later failure. Generation stops at the first row that fails and
    reports it; nothing after it is touched. Selection problems (unknown row,
    not a generated bin, no file and no design source) are raised before any
    file is written.
    """
    root = Path(output_dir).expanduser().resolve()
    inventory = load_inventory(root)
    by_id = {one["id"]: one for one in inventory["bins"]}
    specs = design_specs(inventory["layout"])
    plan: list[tuple[dict[str, Any], list[Path] | None, dict[str, Any] | None]] = []
    for row_id in dict.fromkeys(str(one) for one in row_ids):
        one = by_id.get(row_id)
        if one is None:
            raise ValueError(f"no bin {row_id!r} in the inventory")
        if one.get("kind") not in ("bin", "b4b"):
            raise ValueError(f"{_label(one)} is not a generated bin and cannot be printed here")
        spec = specs.get(row_id)
        files: list[Path] | None = None
        if str(one.get("file") or "").strip():
            try:
                files = inventory_row_files(root, one)
            except ValueError:
                # Recorded files that are missing/unreadable are not current.
                # With no design source to rebuild them from, say so plainly.
                if spec is None:
                    raise
        if files is None and (spec is None or generate_from_design is None):
            raise ValueError(f"{_label(one)} has no generated file to print")
        plan.append((one, files, spec))

    rows_files: dict[str, list[Path]] = {}
    row_specs: dict[str, dict[str, Any]] = {}
    generated: list[str] = []
    reused: list[str] = []
    failed: dict[str, Any] | None = None
    for one, files, spec in plan:
        row_id = one["id"]
        if spec is not None:
            row_specs[row_id] = spec
        if files is not None:
            rows_files[row_id] = files
            reused.append(row_id)
            continue
        try:
            made = generate_from_design(root, spec)
            if not made:
                raise ValueError("generating its files did not produce any")
            if any(not Path(path).is_file() for path in made):
                raise ValueError("a generated file was not saved")
            file_text = ", ".join(dict.fromkeys(path.name for path in made))
            update_bin_file(root, row_id, file_text, expected_design=spec)
        except Exception as error:
            failed = {"id": row_id, "name": _label(one), "error": str(error)}
            break
        rows_files[row_id] = [Path(path) for path in made]
        generated.append(row_id)
    return {
        "root": root,
        "inventory": load_inventory(root),
        "files": rows_files,
        "specs": row_specs,
        "generated": generated,
        "reused": reused,
        "failed": failed,
        "unfinished": [one["id"] for one, _files, _spec in plan if one["id"] not in rows_files],
    }


def _space_connectors(
    output_dir: Path, layout: dict[str, Any] | None, bins: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str]]:
    """Generate every drawer's connector set once: file name -> copies, notes.

    A Pegboard drawer has no Space side-connector bundle (Fix 111 R3-A), so
    the batch connector path skips it instead of entering a connector report
    that assumes ordinary drawer fields."""
    counts: dict[str, int] = {}
    notes: list[str] = []
    for drawer in (layout or {}).get("drawers") or []:
        if drawer.get("boundary") == "pegboard":
            continue
        made = generate_connectors(output_dir, layout, bins, drawer.get("id"))
        for item in made["connectors"]:
            counts[item["file"]] = counts.get(item["file"], 0) + int(item["count"])
        for note in made["notes"]:
            if note not in notes:
                notes.append(note)
    return counts, notes


def _batch_partial(
    prepared: dict[str, Any], stage: str, error: str, **extra: Any,
) -> dict[str, Any]:
    """A structured "some of it worked" result that still carries the fresh Inventory."""
    return {
        **load_inventory(prepared["root"]),
        "partial": True,
        "partial_stage": stage,
        "error": error,
        "saved_rows": [*prepared["reused"], *prepared["generated"]],
        "generated_rows": prepared["generated"],
        "failed_row": prepared["failed"],
        "unfinished": prepared["unfinished"],
        **extra,
    }


def _prepare_failure_text(prepared: dict[str, Any], slicer_name: str | None = None) -> str:
    failed = prepared["failed"]
    done = len(prepared["generated"])
    text = f"Could not prepare {failed['name']}: {failed['error']}."
    text += f" {_plural(done, 'bin')} saved before it stopped." if done else " Nothing new was saved."
    if slicer_name:
        text += f" {slicer_name} was not opened."
    return text + " Retry to finish the rest."


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def save_inventory_bins(
    output_dir: Path | str,
    row_ids: Iterable[str],
    include_connectors: bool,
    generate_from_design: Callable[[Path, dict[str, Any]], list[Path]] | None = None,
) -> dict[str, Any]:
    """Batch Save: make the selected bins' files current, never opening a slicer.

    Only rows without current files are generated; rows that already have
    them are reused. Qty / Printed status is never touched. Optional Space
    connectors are Space-wide output and never belong to a bin row.
    """
    root = Path(output_dir).expanduser().resolve()
    ids = list(dict.fromkeys(str(one) for one in row_ids))
    if not ids:
        raise ValueError("Select at least one bin to save.")
    prepared = prepare_inventory_bins(root, ids, generate_from_design)
    if prepared["failed"]:
        return _batch_partial(prepared, "generate", _prepare_failure_text(prepared))
    inventory = prepared["inventory"]
    connector_counts: dict[str, int] = {}
    notes: list[str] = []
    if include_connectors:
        try:
            connector_counts, notes = _space_connectors(root, inventory["layout"], inventory["bins"])
        except Exception as error:
            return _batch_partial(
                prepared, "connectors",
                f"The bins were saved, but the Space connectors could not be made: {error}")
    return {
        **load_inventory(root),
        "saved_rows": ids,
        "generated_rows": prepared["generated"],
        "reused_rows": prepared["reused"],
        "connector_counts": connector_counts,
        "connector_copies": sum(connector_counts.values()),
        "notes": notes,
    }


# ---------------------------------------------------------------- web routes


def _rollback_spacer_stage(
    root: Path,
    backups: dict[str, Path | None],
    installed: list[Path],
) -> None:
    import os

    errors: list[str] = []
    for final in reversed(installed):
        try:
            if final.exists():
                final.unlink()
        except OSError as error:
            errors.append(f"{final.name}: {error}")
    for name, backup in backups.items():
        if backup is None or not backup.exists():
            continue
        try:
            os.replace(backup, root / name)
        except OSError as error:
            errors.append(f"{name}: {error}")
    if errors:
        raise RuntimeError(
            "Spacer rollback could not fully restore the previous files: "
            + "; ".join(errors)
        )


def _promote_spacer_stage(
    root: Path,
    stage: Path,
    names: list[str],
) -> tuple[dict[str, Path | None], list[Path]]:
    import os

    root = root.expanduser().resolve()
    stage = stage.expanduser().resolve()
    if stage.parent != root:
        raise ValueError("spacer stage must be inside the Space folder")

    backups: dict[str, Path | None] = {}
    installed: list[Path] = []

    for name in names:
        if Path(name).name != name or not name.lower().endswith(".3mf"):
            raise ValueError(f"unsafe spacer file name {name!r}")
        staged = (stage / name).resolve()
        if staged.parent != stage or not staged.is_file() or staged.stat().st_size <= 0:
            raise ValueError(f"Spacer file {name} was not generated correctly.")

    try:
        for index, name in enumerate(names):
            staged = stage / name
            final = root / name
            backup: Path | None = None
            if final.exists():
                backup = stage / f".backup-{index:03d}-{name}"
                os.replace(final, backup)
            backups[name] = backup
            os.replace(staged, final)
            installed.append(final)
    except Exception:
        _rollback_spacer_stage(root, backups, installed)
        raise

    return backups, installed
