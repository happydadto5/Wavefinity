"""Inventory file rows: constants, parsing, rendering and design-source row edits."""

from __future__ import annotations

from datetime import datetime
import copy
import json
import math
from pathlib import Path
import re
import threading
from typing import Any, Iterable


INVENTORY_LOCK = threading.RLock()
INVENTORY_FILENAME = "Wavefinity bins.md"
LAYOUT_HEADING = "## Drawer layout"
COLUMNS = (
    ("id", "ID"), ("date", "Date"), ("kind", "Kind"), ("name", "Name"),
    ("x", "X (mm)"), ("y", "Y (mm)"), ("z", "Z (mm)"), ("stack", "Stack"),
    ("wall", "Wall (mm)"), ("object_height_mm", "Object height (mm)"),
    ("qty", "Qty"), ("status", "Status"), ("file", "File"), ("label", "Label"), ("interior", "Interior Part(s)"),
    ("boundary", "Boundary"), ("flexible", "Flexible"),
    ("pegboard_standard", "Pegboard"),
    ("cleat_x", "Cleat X"), ("cleat_y", "Cleat Y"),
)
# bin: generated here.  b4b: a Bin for Bins case.  spacer: made by the Layout
# view to take up the measured back/right gap left by the placed grid - a
# flexible serpentine flexure with printed preload where there is room for
# one, or a rigid spacer where the gap is too short to flex.  manual: typed in
# for a bin printed elsewhere.  Older inventories used a separate "shim" kind
# for what is now an edge-facing spacer; see the migration in ``_normalise``.
KINDS = ("bin", "b4b", "spacer", "manual")
# How the bin was printed to stack: not at all, with a snap-on lid, or snapping
# straight into the bin below. For stackable bins Z is the requested module
# contribution; the drawer derives the detached envelope from the interface.
STACK_MODES = ("none", "lid", "direct", "b4b")
EDITABLE = ("name", "qty", "x", "y", "z", "stack", "wall", "object_height_mm")
MAX_QTY = 999
# A generated bin is not a printed one.  Until the Layout view's setting says
# otherwise, new rows start at Qty 0 and are marked printed by hand.
DEFAULT_NEW_BIN_QTY = 0
# A Space is one physical drawer, Storage Box (kind ``portable``), surface, or pegboard. Its inventory
# is stored in the selected Wavefinity save folder. Legacy "box" is read for
# migration only (see normalise_space_definition's allow_legacy) - it must
# never be a normal writable current kind, or every caller that omits
# allow_legacy (the default) would still silently accept and persist it.
SPACE_KINDS = ("drawer", "surface", "portable", "pegboard", "storage_drawers")
LEGACY_SPACE_KINDS = ("box",)

_HEADER_KEYS = {
    "id": "id", "date": "date", "kind": "kind", "name": "name",
    "x": "x", "y": "y", "z": "z", "stack": "stack", "stacking": "stack",
    "wall": "wall", "object height": "object_height_mm",
    "qty": "qty", "quantity": "qty", "status": "status",
    "file": "file", "label": "label", "interior part(s)": "interior",
    "interior": "interior", "boundary": "boundary",
    "pegboard": "pegboard_standard", "cleat x": "cleat_x", "cleat y": "cleat_y",
}
_KEEP = object()


def inventory_path(output_dir: Path | str) -> Path:
    """The canonical inventory path only; runtime code uses the resolver."""
    return Path(output_dir).expanduser().resolve() / INVENTORY_FILENAME


class InventoryMigrationError(ValueError):
    """More than one plausible inventory file exists; nothing was changed."""


def resolve_inventory_path(output_dir: Path | str, *, migrate: bool) -> Path:
    """The folder's inventory file, independent of the folder's name.

    The canonical file is ``Wavefinity bins.md``. A pre-canonical folder may
    hold one ``<any name> bins.md``; with ``migrate`` it is renamed to the
    canonical name, without it the old file is returned so read-only callers
    can still read it. Several different candidates are never guessed at.
    """
    folder = Path(output_dir).expanduser().resolve()
    canonical = folder / INVENTORY_FILENAME
    legacy: list[Path] = []
    if folder.is_dir():
        preferred = folder / f"{folder.name} bins.md"
        if preferred.name != INVENTORY_FILENAME and preferred.is_file():
            legacy.append(preferred)
        for path in folder.glob("* bins.md"):
            if path.name != INVENTORY_FILENAME and path.is_file() and path not in legacy:
                legacy.append(path)
    conflict = InventoryMigrationError(
        "Multiple Wavefinity inventory files were found; nothing was changed."
    )
    with INVENTORY_LOCK:
        if canonical.is_file():
            if any(one.read_bytes() != canonical.read_bytes() for one in legacy):
                raise conflict
            if migrate:
                # Identical leftovers go before the canonical file next
                # changes, or the next write would look like a conflict.
                for one in legacy:
                    one.unlink()
            return canonical
        if not legacy:
            return canonical
        if len(legacy) != 1:
            raise conflict
        source = legacy[0]
        if not migrate:
            return source
        source.replace(canonical)
        return canonical


# ---------------------------------------------------------------- reading


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def _header_key(text: str) -> str | None:
    key = re.sub(r"\s*\(mm\)$", "", text.strip().lower())
    return _HEADER_KEYS.get(key)


def _text(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text == "-" else text


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return fallback
    return number if number == number and abs(number) != float("inf") else fallback


def _object_height(value: Any) -> float | None:
    if value is None or str(value).strip() in ("", "-"):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Object height must be a positive number of mm") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError("Object height must be a positive number of mm")
    return number


def infer_kind(file: str, interior: str = "") -> str:
    lead = file.strip().lower()
    if lead.startswith("b4b") or interior.strip().lower().startswith("b4b"):
        return "b4b"
    if lead.startswith("spacer"):
        return "spacer"
    if lead.startswith("shim"):
        return "shim"
    return "bin" if lead else "manual"


def infer_name(file: str, label: str = "") -> str:
    """The name a person would call a logged bin: its label, else whatever the
    part name added to the file name after the size (timestamps dropped)."""
    if label:
        first = re.sub(r"\s*\((rim|floor)\)$", "", label.split(",")[0]).strip()
        if first:
            return first
    stem = re.sub(r"\.(3mf|stl)$", "", file.split(",")[0].strip(), flags=re.I)
    size = r"\d+(?:\.\d+)?"
    stem = re.sub(rf"^(Box|Insert)\s+{size}\s*x\s*{size}(\s*x\s*{size})?", "", stem, flags=re.I)
    stem = re.sub(rf"^(?:Storage Box|B4B)\s+{size}x{size}x{size}", "", stem, flags=re.I)
    stem = re.sub(r"^\s*-\s*", "", stem)
    stem = re.sub(r"\s*\b\d{12}\b\s*$", "", stem)  # the auto timestamp, mmddyyHHMMSS
    return stem.strip()


def _normalise(raw: dict[str, str]) -> dict[str, Any] | None:
    x, y, z = (_number(raw.get(axis)) for axis in ("x", "y", "z"))
    if min(x, y, z) <= 0:
        return None
    file = _text(raw.get("file"))
    label = _text(raw.get("label"))
    interior = _text(raw.get("interior"))
    kind = _text(raw.get("kind")).lower()
    boundary = _text(raw.get("boundary")).lower()
    if kind != "shim" and kind not in KINDS:
        kind = infer_kind(file, interior)
    if kind == "shim":
        # Legacy inventories used a separate "shim" kind for what is now an
        # edge-facing Spacer. Fold it into the unified kind on load, so
        # nothing downstream ever sees "shim" again and the next save writes
        # a plain spacer row instead.
        kind, boundary = "spacer", "edge"
    if boundary not in ("", "edge"):
        boundary = ""
    name = _text(raw.get("name")) if "name" in raw else infer_name(file, label)
    qty = raw.get("qty")
    normal_qty = max(0, min(MAX_QTY, int(_number(qty, 0)))) if _text(qty) else 0
    derived_status = "printed" if normal_qty > 0 else ("saved" if file else "in_design")
    status = _text(raw.get("status")).lower()
    if status not in ("in_design", "saved", "printed"):
        status = derived_status
    else:
        normal_qty = 1 if status == "printed" else 0
    stack = _text(raw.get("stack")).lower()
    wall_text = _text(raw.get("wall"))
    wall = _number(wall_text) if wall_text else None
    if wall is not None and wall <= 0:
        wall = None
    return {
        "id": _text(raw.get("id")),
        "date": _text(raw.get("date")),
        "kind": kind,
        "boundary": boundary,
        "name": name,
        "x": x, "y": y, "z": z,
        "stack": stack if stack in STACK_MODES else "none",
        "wall": wall,
        "object_height_mm": _object_height(raw.get("object_height_mm")),
        "qty": normal_qty,
        "status": status,
        "file": file,
        "label": label,
        "interior": interior,
        # Spacer print variant. Blank (legacy rows, non-spacer rows, or any
        # other text) parses to None so the dialog can apply its filename
        # fallback; only an explicit yes/no becomes a boolean.
        "flexible": {"yes": True, "no": False}.get(_text(raw.get("flexible")).lower()),
        "pegboard_standard": _text(raw.get("pegboard_standard")).lower(),
        "cleat_x": _text(raw.get("cleat_x")).lower() or "auto",
        "cleat_y": _text(raw.get("cleat_y")).lower() or "auto",
    }


def _assign_ids(bins: list[dict[str, Any]]) -> None:
    taken: set[str] = set()
    numbers = [0]
    for one in bins:
        match = re.fullmatch(r"B(\d+)", one["id"])
        if match and one["id"] not in taken:
            taken.add(one["id"])
            numbers.append(int(match.group(1)))
        else:
            one["id"] = ""
    following = max(numbers) + 1
    for one in bins:
        if not one["id"]:
            one["id"] = f"B{following}"
            following += 1


def next_bin_id(bins: Iterable[dict[str, Any]]) -> str:
    numbers = [0]
    for one in bins:
        match = re.fullmatch(r"B(\d+)", str(one.get("id", "")))
        if match:
            numbers.append(int(match.group(1)))
    return f"B{max(numbers) + 1}"


def _migrate_drawer_boundaries(layout: dict[str, Any] | None) -> None:
    """Fill in a missing drawer ``boundary`` from the authoritative Space kind.

    A Space's ``boundary`` ("wall" or "mating") was added after Box Spaces
    already existed, and organizer_drawer.normalise_drawer defaults an absent
    one to "wall" - a hard-wall clearance floor that silently shrinks an old
    Box/Storage Box's exact interior (see organizer_drawer.BOUNDARIES). Migrate only
    the Space's own primary drawer from ``layout.space.kind``; any other
    drawer in the layout, and any drawer that already carries an explicit
    valid boundary, is left untouched. The mutation is in place, so a save
    right after loading persists it.

    ``layout.active`` is deliberately NOT used to find that drawer - it is
    just whichever one the UI last had selected, and can point anywhere in a
    multi-drawer layout. Instead: the drawer ``create_space`` always creates
    a Box/Drawer Space with (``id == "d1"``) if it still exists, else the one
    drawer whose own width/depth/height still match the Space's own recorded
    size, else - deterministically, not UI state - the first drawer.
    """
    if not isinstance(layout, dict):
        return
    space = layout.get("space")
    drawers = [d for d in (layout.get("drawers") or []) if isinstance(d, dict)]
    if not isinstance(space, dict) or not drawers:
        return
    if space.get("kind") == "storage_drawers":
        return  # every cabinet drawer is always mating/zero-clearance
    target = (
        "pegboard" if space.get("kind") == "pegboard"
        else "mating" if space.get("kind") == "box"
        else "wall"
    )
    primary = next((d for d in drawers if d.get("id") == "d1"), None)
    if primary is None:
        want = tuple(_number(space.get(axis), float("nan")) for axis in ("x", "y", "z"))
        if all(math.isfinite(value) for value in want):
            primary = next(
                (d for d in drawers if all(
                    math.isfinite(_number(d.get(key), float("nan")))
                    and abs(_number(d.get(key)) - value) < 0.05
                    for key, value in zip(("width", "depth", "height"), want)
                )),
                None,
            )
    primary = primary or drawers[0]
    if primary.get("boundary") not in ("wall", "mating", "pegboard"):
        primary["boundary"] = target


def parse_inventory(text: str) -> dict[str, Any]:
    """Split the file into bin rows and the layout block.

    Tolerant of hand edits: columns are found by header name, any number of
    tables are read, rows without a usable size are skipped, and an unreadable
    layout block is reported rather than raised.
    """
    lines = text.splitlines()
    heading = next(
        (index for index, line in enumerate(lines) if line.strip() == LAYOUT_HEADING),
        len(lines),
    )
    bins: list[dict[str, Any]] = []
    warnings: list[str] = []
    legacy = False
    keys: list[str | None] | None = None
    for line in lines[:heading]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            keys = None
            continue
        cells = _cells(stripped)
        if keys is None:
            mapped = [_header_key(cell) for cell in cells]
            if "x" in mapped and ("date" in mapped or "id" in mapped):
                keys = mapped
                legacy = legacy or "id" not in mapped or "qty" not in mapped or "wall" not in mapped
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells if cell):
            continue
        raw = {key: cells[i] for i, key in enumerate(keys) if key and i < len(cells)}
        one = _normalise(raw)
        if one is None:
            warnings.append(f"skipped a row with no usable size: {stripped[:60]}")
            continue
        bins.append(one)
    _assign_ids(bins)

    layout = None
    if heading < len(lines):
        block = "\n".join(lines[heading:])
        match = re.search(r"```json[^\n]*\n(.*?)\n```", block, re.S)
        if match:
            try:
                parsed = json.loads(match.group(1))
                layout = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError as error:
                warnings.append(f"the drawer layout block could not be read ({error.msg}); it will be rewritten on the next save")
    _migrate_drawer_boundaries(layout)
    return {"bins": bins, "layout": layout, "warnings": warnings, "legacy": legacy}


# ---------------------------------------------------------------- writing


def _cell(value: Any) -> str:
    text = str(value).replace("|", "/").replace("\r", " ").replace("\n", " ").strip()
    return text or "-"


def _row(one: dict[str, Any]) -> str:
    wall = one.get("wall")
    values = {
        **one,
        "x": f"{float(one['x']):g}", "y": f"{float(one['y']):g}", "z": f"{float(one['z']):g}",
        "qty": str(int(one["qty"])),
        "status": one.get("status", "in_design"),
        "stack": "" if one.get("stack", "none") == "none" else one["stack"],
        "wall": f"{float(wall):g}" if wall else "",
        "object_height_mm": (f"{float(one['object_height_mm']):g}"
                             if one.get("object_height_mm") is not None else ""),
        "flexible": ("yes" if one.get("flexible") is True
                     else "no" if one.get("flexible") is False else ""),
    }
    return "| " + " | ".join(_cell(values.get(key, "")) for key, _ in COLUMNS) + " |"


def _compact_json(value: Any, level: int = 0) -> str:
    """JSON that keeps each placement on one line, so the block
    stays short enough to scroll past when the file is opened by hand."""
    flat = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or len(flat) + 2 * level <= 110:
        return flat
    pad, end = "  " * (level + 1), "  " * level
    if isinstance(value, dict):
        items = [f"{pad}{json.dumps(key)}: {_compact_json(item, level + 1)}" for key, item in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + end + "}"
    items = [pad + _compact_json(item, level + 1) for item in value]
    return "[\n" + ",\n".join(items) + "\n" + end + "]"


def render_inventory(title: str, bins: list[dict[str, Any]], layout: dict | None) -> str:
    parts = [
        f"# {title} Bins\n",
        "One row per bin. Status tracks its current print files; Qty is a compatibility field. "
        "Edit rows freely, but keep each row's ID.\n",
        "| " + " | ".join(title for _, title in COLUMNS) + " |",
        "| " + " | ".join("---" for _ in COLUMNS) + " |",
        *(_row(one) for one in bins),
    ]
    text = "\n".join(parts[:2]) + "\n" + "\n".join(parts[2:]) + "\n"
    if layout is not None:
        text += (
            f"\n{LAYOUT_HEADING}\n\n"
            "Written by Wavefinity's Drawer layout view. Edit the table above, not this block.\n\n"
            "```json\n" + _compact_json(layout) + "\n```\n"
        )
    return text


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"bins": [], "layout": None, "warnings": [], "legacy": False}
    return parse_inventory(path.read_text(encoding="utf-8"))


def _title(path: Path, layout: dict | None) -> str:
    """The space's name, else the folder's."""
    space = layout.get("space") if isinstance(layout, dict) else None
    name = str(space.get("name") or "").strip() if isinstance(space, dict) else ""
    return name or path.parent.name


def _unit_offset(value: Any) -> float | int:
    """A stacked placement's saved offset in units; anything not finite is 0."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return int(number) if number.is_integer() else number


def _prune_layout(layout: dict | None, bins: list[dict[str, Any]]) -> dict | None:
    """Drop placements and design sources whose bin row is gone.

    A bin stacked directly on a dropped one takes its place, so a stack closes
    up instead of floating: it moves up to the dropped bin's own support (or onto
    the floor where a dropped floor bin stood), keeping its absolute spot, so the
    two offsets add.
    """
    if not isinstance(layout, dict):
        return layout
    known = {one["id"] for one in bins}
    for drawer in layout.get("drawers", []) or []:
        if not isinstance(drawer, dict):
            continue
        placements = [one for one in drawer.get("placements", []) or [] if isinstance(one, dict)]
        for gone in [one for one in placements if one.get("bin") not in known]:
            key = f"{gone.get('bin')}:{int(gone.get('copy', 0))}"
            for above in placements:
                if above.get("on") == key:
                    ox = _unit_offset(gone.get("ox")) + _unit_offset(above.get("ox"))
                    oy = _unit_offset(gone.get("oy")) + _unit_offset(above.get("oy"))
                    carries = any(field in item for item in (gone, above) for field in ("ox", "oy"))
                    for field in ("on", "ox", "oy"):
                        above.pop(field, None)
                    if "on" in gone:
                        above["on"] = gone["on"]
                        if carries:
                            above["ox"], above["oy"] = ox, oy
                    else:
                        for field, offset in (("gx", ox), ("gy", oy)):
                            if field in gone:
                                above[field] = gone[field] + offset
        drawer["placements"] = [one for one in placements if one.get("bin") in known]
    specs = layout.get("design_specs")
    if isinstance(specs, dict):
        pruned = {row_id: spec for row_id, spec in specs.items() if row_id in known}
        if len(pruned) != len(specs):
            layout["design_specs"] = pruned
    stale = layout.get("stale_files")
    if isinstance(stale, dict):
        kept = {row_id: names for row_id, names in stale.items() if row_id in known}
        if kept != stale:
            if kept:
                layout["stale_files"] = kept
            else:
                layout.pop("stale_files", None)
    return layout


def design_specs(layout: dict[str, Any] | None) -> dict[str, Any]:
    """The saved canonical design source per Inventory row ID, else empty."""
    specs = layout.get("design_specs") if isinstance(layout, dict) else None
    return specs if isinstance(specs, dict) else {}


def _next_simple_bin_name(bins: list[dict[str, Any]]) -> str:
    names = {str(one.get("name") or "").casefold() for one in bins}
    number = 1
    while f"bin {number}" in names:
        number += 1
    return f"Bin {number}"


def _duplicate_name(bins: list[dict[str, Any]], source: str) -> str:
    root = re.sub(r" \(\d+\)$", "", str(source or "").strip()).strip()
    if not root or root == "-":
        return _next_simple_bin_name(bins)
    names = {str(one.get("name") or "").casefold() for one in bins}
    number = 2
    while f"{root} ({number})".casefold() in names:
        number += 1
    return f"{root} ({number})"


def _duplicate_design_source(current: dict[str, Any], row_id: str) -> tuple[list[dict[str, Any]], dict, str, dict]:
    bins = current["bins"]
    source = next((one for one in bins if one["id"] == row_id), None)
    layout = current["layout"] if isinstance(current["layout"], dict) else {}
    spec = design_specs(layout).get(row_id)
    if source is None or not isinstance(spec, dict):
        raise ValueError(f"no canonical design source for {row_id!r}")
    name = _duplicate_name(bins, source.get("name", ""))
    design = copy.deepcopy(spec)
    design["part_name"] = name
    new_id = next_bin_id(bins)
    bins.append({**copy.deepcopy(source), "id": new_id, "name": name,
                 "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "file": "", "status": "in_design", "qty": 0})
    layout = {**layout, "design_specs": {**design_specs(layout), new_id: design}}
    return bins, layout, new_id, design


def _change_design_status(current: dict[str, Any], row_id: str, action: str,
                          file_text: str | None, expected_design: dict | None = None) -> tuple[list[dict[str, Any]], dict]:
    bins = current["bins"]
    layout = current["layout"] if isinstance(current["layout"], dict) else {}
    target = next((one for one in bins if one["id"] == row_id), None)
    if target is None or row_id not in design_specs(layout):
        raise ValueError(f"no canonical design source for {row_id!r}")
    if expected_design is not None and design_specs(layout)[row_id] != expected_design:
        raise ValueError("This bin changed while its files were being prepared")
    if action not in ("saved", "printed", "mark_printed", "mark_not_printed", "in_design"):
        raise ValueError("unsupported print status action")
    if action == "saved":
        if not file_text or not file_text.strip():
            raise ValueError("Saved requires current file names")
        target["file"] = file_text.strip()
    elif action == "printed" and file_text is not None:
        target["file"] = file_text.strip()
    elif action == "in_design":
        target["file"] = ""
    target["status"] = ("printed" if action in ("printed", "mark_printed") else
                        "saved" if action == "saved" or (action == "mark_not_printed" and target["file"]) else
                        "in_design")
    target["qty"] = 1 if target["status"] == "printed" else 0
    return bins, layout
