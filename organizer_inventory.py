"""The folder's inventory file: ``Wavefinity bins.md`` in the save folder.

A persistent save folder keeps this by default - a normal untyped Design
folder may explicitly opt out, independently of whether it is a typed Space.
Every generated bin/B4B is appended here when inventory is enabled. A typed
Drawer, Surface, Portable, or Pegboard Space stores its layout in this same file rather
than a separate one; a Space requires inventory, but inventory does not
require a Space. Legacy Box metadata remains readable as migration input
only - see ``normalise_space_definition``'s ``allow_legacy``. The file has
two parts:

* a Markdown table, one row per bin design.  ``Qty`` is how many copies were
  actually printed - 0 means generated but never printed, or superseded by a
  later version.
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

from datetime import datetime
import json
import math
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Iterable

from organizer_engine import BASE_UNIT, MIN_HEIGHT_ABOVE_BASE
from organizer_product_rules import (
    B4B_LATCHED_MIN_HEIGHT,
    B4B_MIN_FIELD_XY,
    DRAWER_HARD_CLEARANCE_MM,
    ORDINARY_BIN_MIN_HEIGHT_MM,
    SURFACE_TRIM_HEIGHTS,
)
from organizer_pegboard import normalise_pegboard_space

INVENTORY_LOCK = threading.RLock()
INVENTORY_FILENAME = "Wavefinity bins.md"
LAYOUT_HEADING = "## Drawer layout"
COLUMNS = (
    ("id", "ID"), ("date", "Date"), ("kind", "Kind"), ("name", "Name"),
    ("x", "X (mm)"), ("y", "Y (mm)"), ("z", "Z (mm)"), ("stack", "Stack"),
    ("wall", "Wall (mm)"), ("object_height_mm", "Object height (mm)"),
    ("qty", "Qty"), ("file", "File"), ("label", "Label"), ("interior", "Interior Part(s)"),
    ("boundary", "Boundary"),
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
# A Space is one physical drawer, surface, portable case, or pegboard. Its inventory
# is stored in the selected Wavefinity save folder. Legacy "box" is read for
# migration only (see normalise_space_definition's allow_legacy) - it must
# never be a normal writable current kind, or every caller that omits
# allow_legacy (the default) would still silently accept and persist it.
SPACE_KINDS = ("drawer", "surface", "portable", "pegboard")
LEGACY_SPACE_KINDS = ("box",)

_HEADER_KEYS = {
    "id": "id", "date": "date", "kind": "kind", "name": "name",
    "x": "x", "y": "y", "z": "z", "stack": "stack", "stacking": "stack",
    "wall": "wall", "object height": "object_height_mm",
    "qty": "qty", "quantity": "qty",
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
        "qty": max(0, min(MAX_QTY, int(_number(qty, 1)))) if _text(qty) else 1,
        "file": file,
        "label": label,
        "interior": interior,
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
        "stack": "" if one.get("stack", "none") == "none" else one["stack"],
        "wall": f"{float(wall):g}" if wall else "",
        "object_height_mm": (f"{float(one['object_height_mm']):g}"
                             if one.get("object_height_mm") is not None else ""),
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
        "One row per bin design. **Qty** is how many copies you have printed "
        "(0 = not printed). Edit rows freely, but keep each row's ID.\n",
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


def _write(path: Path, bins: list[dict[str, Any]], layout: dict | None, legacy: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".bak")
    if legacy and path.is_file() and not backup.exists():
        shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(render_inventory(_title(path, layout), bins, layout), encoding="utf-8")
    temp.replace(path)


def _prune_layout(layout: dict | None, bins: list[dict[str, Any]]) -> dict | None:
    """Drop placements and design sources whose bin row is gone.

    A copy numbered past the printed Qty stays: it is a *planned* bin, placed
    before it is printed.  A bin stacked on a dropped one takes its place, so a
    stack closes up instead of floating.
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
                    above.pop("on", None)
                    for field in ("on", "gx", "gy", "locked"):
                        if field in gone:
                            above[field] = gone[field]
        drawer["placements"] = [one for one in placements if one.get("bin") in known]
    specs = layout.get("design_specs")
    if isinstance(specs, dict):
        pruned = {row_id: spec for row_id, spec in specs.items() if row_id in known}
        if len(pruned) != len(specs):
            layout["design_specs"] = pruned
    return layout


def update_bin_file(output_dir: Path | str, row_id: str, file_text: str) -> dict[str, Any]:
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
        target["file"] = file_text
        _write(path, bins, current["layout"], current["legacy"])
        return _payload(path, _read(path))


def design_specs(layout: dict[str, Any] | None) -> dict[str, Any]:
    """The saved canonical design source per Inventory row ID, else empty."""
    specs = layout.get("design_specs") if isinstance(layout, dict) else None
    return specs if isinstance(specs, dict) else {}


def save_design_source(
    output_dir: Path | str, *, design: dict[str, Any], record: dict[str, Any], row_id: str | None = None,
) -> dict[str, Any]:
    """Atomically create/update one canonical design source row + its ``design_specs`` entry.

    ``record`` is the caller-derived Inventory row fields (already validated
    server-side) for the design being saved; ``design`` is the exact canonical
    design JSON to store as that row's editable source. ``row_id`` updates that
    existing row in place only while it is still Qty 0 - an immutable Qty>0
    printed row instead forks a new Qty-0 row, so printed history is never
    silently redefined underneath. Returns the fresh inventory/layout payload
    plus the ``row_id`` actually used.
    """
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins, layout, used_id = _merge_design_source(current, design=design, record=record, row_id=row_id)
        _write(path, bins, layout, current["legacy"])
        return {**_payload(path, _read(path)), "row_id": used_id}


def save_design_source_text(
    text: str, *, title: str = "Wavefinity", design: dict[str, Any], record: dict[str, Any],
    row_id: str | None = None,
) -> dict[str, Any]:
    """Merge changes into browser-owned text and return replacement text, per ``save_design_source``."""
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        bins, layout, used_id = _merge_design_source(current, design=design, record=record, row_id=row_id)
        rendered = render_inventory(str(title or "Wavefinity"), bins, layout)
        return {**_text_payload(rendered, str(title or "Wavefinity"), parse_inventory(rendered)), "row_id": used_id}


def _merge_design_source(
    current: dict[str, Any], *, design: dict[str, Any], record: dict[str, Any], row_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
    bins = current["bins"]
    by_id = {one["id"]: one for one in bins}
    target = by_id.get(row_id) if row_id else None
    row_fields = {
        "kind": record.get("kind", "bin"),
        "name": record.get("name", ""),
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
    if target is not None and int(target.get("qty") or 0) == 0:
        target.update(row_fields)
        if record.get("clear_file"):
            target["file"] = ""
        used_id = target["id"]
    else:
        used_id = next_bin_id(bins)
        bins.append({
            "id": used_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "boundary": "",
            "qty": 0,
            "file": "",
            **row_fields,
        })
    layout = current["layout"] if isinstance(current["layout"], dict) else {}
    layout = {**layout, "design_specs": {**design_specs(layout), used_id: design}}
    layout = _prune_layout(layout, bins)
    return bins, layout, used_id


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


def _merge_inventory(
    current: dict[str, Any], *,
    layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    delete_ids: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], dict | None]:
    if layout is not _KEEP and layout is not None and not isinstance(layout, dict):
        raise ValueError("drawer layout must be an object")
    bins = current["bins"]
    chosen = current["layout"] if layout is _KEEP else layout
    if isinstance(chosen, dict):
        chosen = {**chosen, "design_specs": dict(design_specs(chosen))}
    by_id = {one["id"]: one for one in bins}
    for update in bin_updates or ():
        target = by_id.get(str(update.get("id", "")))
        if target is None:
            raise ValueError(f"no bin {update.get('id')!r} in the inventory")
        clean = _clean_bin(update, partial=True)
        old_qty = int(target.get("qty") or 0)
        target.update(clean)
        spec = design_specs(chosen).get(target["id"])
        if isinstance(spec, dict) and ("object_height_mm" in clean or
                                       (old_qty == 0 and int(target["qty"]) > 0)):
            spec = {**spec, "layout": dict(spec.get("layout") or {})}
            if "object_height_mm" in clean:
                spec["layout"]["object_height_mm"] = clean["object_height_mm"]
            if old_qty == 0 and int(target["qty"]) > 0 and spec["layout"].get("surface_base_mode") == "edge":
                spec["layout"]["surface_base_mode"] = "custom"
            chosen["design_specs"][target["id"]] = spec
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
            "qty": clean.get("qty", 1),
            "file": str(raw.get("file") or ""),
            "label": str(raw.get("label") or ""),
            "interior": str(raw.get("interior") or ""),
            "pegboard_standard": str(raw.get("pegboard_standard") or "").lower(),
            "cleat_x": str(raw.get("cleat_x") or "auto").lower(),
            "cleat_y": str(raw.get("cleat_y") or "auto").lower(),
        })
    return bins, _prune_layout(chosen, bins)


def save_inventory(
    output_dir: Path | str, *, layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    delete_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into the file on disk and return the fresh contents."""
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        bins, chosen = _merge_inventory(
            current, layout=layout, bin_updates=bin_updates,
            new_bins=new_bins, delete_ids=delete_ids,
        )
        _write(path, bins, chosen, current["legacy"])
        return _payload(path, _read(path))


def save_inventory_text(
    text: str, *, title: str = "Wavefinity", layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    delete_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into browser-owned text and return replacement text."""
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        bins, chosen = _merge_inventory(
            current, layout=layout, bin_updates=bin_updates,
            new_bins=new_bins, delete_ids=delete_ids,
        )
        rendered = render_inventory(str(title or "Wavefinity"), bins, chosen)
        return _text_payload(rendered, str(title or "Wavefinity"), parse_inventory(rendered))


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
        bins.append({
            "id": new_id,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kind": kind if kind in KINDS else "bin",
            "name": name,
            "x": float(x), "y": float(y), "z": float(z),
            "stack": stack if stack in STACK_MODES else "none",
            "wall": float(wall) if wall and float(wall) > 0 else None,
            "object_height_mm": object_height_mm,
            "qty": max(0, int(qty)),
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


def legacy_layout_space(layout: dict[str, Any] | None) -> dict[str, Any] | None:
    """Recover a Space's identity from a pre-``layout.space`` drawer layout.

    Older inventories held drawers, an active drawer and placements without
    the newer top-level ``space`` block. That is still a real Space: derive
    one from its drawer (the active one when there is a choice), so the
    folder is recognized without losing or re-entering anything.
    """
    if not isinstance(layout, dict):
        return None
    drawers = layout.get("drawers")
    if not isinstance(drawers, list) or not drawers:
        return None
    active_id = layout.get("active")
    chosen = next(
        (one for one in drawers if isinstance(one, dict) and one.get("id") == active_id),
        None,
    ) or next((one for one in drawers if isinstance(one, dict)), None)
    if not isinstance(chosen, dict):
        return None
    try:
        size = [float(chosen[axis]) for axis in ("width", "depth", "height")]
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(value) and value > 0 for value in size):
        return None
    name = str(chosen.get("name") or "").strip()[:80] or "Drawer"
    return {"kind": "drawer", "name": name, "x": size[0], "y": size[1], "z": size[2]}



def normalise_space_definition(raw: dict[str, Any], *, allow_legacy: bool = False) -> dict[str, Any]:
    name = str(raw.get("name") or "").strip()[:80]
    if not name:
        raise ValueError("a space needs a name")
    kind = str(raw.get("kind") or "")
    if kind not in SPACE_KINDS and not (allow_legacy and kind in LEGACY_SPACE_KINDS):
        raise ValueError(f"a space is one of {', '.join(SPACE_KINDS)}")
    if kind in LEGACY_SPACE_KINDS:
        # Legacy box is read for migration only - this function persists,
        # so the migration wizard's own box -> Portable mapping is enforced
        # here too, not left to every caller to remember - see Fix 004
        # Correction 8.D.
        kind = "portable"

    if kind == "pegboard":
        resolved = normalise_pegboard_space(raw)
        return {"name": name, "kind": kind, **resolved}

    x, y, z = (_number(raw.get(axis)) for axis in ("x", "y", "z"))
    if min(x, y, z) <= 0:
        raise ValueError("a space needs its inside X, Y and Z in mm")

    if kind == "drawer":
        minimum_xy = BASE_UNIT + DRAWER_HARD_CLEARANCE_MM
        if x + 1e-9 < minimum_xy or y + 1e-9 < minimum_xy:
            raise ValueError(
                f"a drawer space needs at least {minimum_xy:g} mm width and depth"
            )
        if z + 1e-9 < ORDINARY_BIN_MIN_HEIGHT_MM:
            raise ValueError(
                f"a drawer space needs at least {ORDINARY_BIN_MIN_HEIGHT_MM:g} mm usable height"
            )

    elif kind == "portable":
        if x + 1e-9 < B4B_MIN_FIELD_XY or y + 1e-9 < B4B_MIN_FIELD_XY:
            raise ValueError(
                f"portable storage needs at least {B4B_MIN_FIELD_XY:g} mm in X and Y"
            )
        if z + 1e-9 < B4B_LATCHED_MIN_HEIGHT:
            raise ValueError(
                f"portable storage needs at least {B4B_LATCHED_MIN_HEIGHT:g} mm usable height"
            )
        for axis_name, value in (("X", x), ("Y", y)):
            units = value / BASE_UNIT
            if not math.isclose(units, round(units), abs_tol=1e-6):
                raise ValueError(
                    f"portable storage {axis_name} must be a whole Wavefinity unit"
                )

    elif kind == "surface":
        for axis_name, value in (("X", x), ("Y", y)):
            units = value / BASE_UNIT
            if units < 1 or not math.isclose(units, round(units), abs_tol=1e-6):
                raise ValueError(
                    f"surface {axis_name} must be a positive whole Wavefinity unit"
                )

        trim_size = str(raw.get("trim_size") or "").strip().lower()
        expected_z = SURFACE_TRIM_HEIGHTS.get(trim_size)
        if expected_z is None:
            raise ValueError("surface trim size must be small, medium, or large")
        if not math.isclose(z, expected_z, abs_tol=1e-6):
            raise ValueError(
                f"surface trim size {trim_size!r} requires Z={expected_z:g} mm"
            )

    result = {"name": name, "kind": kind, "x": x, "y": y, "z": z}
    if kind == "surface":
        result["trim_size"] = trim_size
    return result

def _setup_space_layout(layout: dict[str, Any], space_def: dict[str, Any]) -> None:
    layout["version"] = 1
    layout["space"] = space_def

    kind = space_def["kind"]
    x, y, z = space_def["x"], space_def["y"], space_def["z"]

    drawers = layout.setdefault("drawers", [])
    active_id = layout.get("active")
    primary = next(
        (
            drawer for drawer in drawers
            if isinstance(drawer, dict) and drawer.get("id") == active_id
        ),
        None,
    )

    if primary is None and drawers:
        primary = next(
            (drawer for drawer in drawers if isinstance(drawer, dict)),
            None,
        )

    if primary is None:
        primary = {
            "id": "d1",
            "placements": [],
        }
        drawers.append(primary)

    layout["active"] = primary["id"]

    if kind == "drawer":
        boundary = "wall"
        try:
            previous_clearance = float(primary.get("clearance", DRAWER_HARD_CLEARANCE_MM))
        except (TypeError, ValueError):
            previous_clearance = DRAWER_HARD_CLEARANCE_MM
        clearance = max(DRAWER_HARD_CLEARANCE_MM, previous_clearance)
    elif kind == "pegboard":
        boundary = "pegboard"
        clearance = 0.0
    else:
        boundary = "mating"
        clearance = 0.0

    primary["name"] = space_def["name"]
    primary["width"] = x
    primary["depth"] = y
    primary["height"] = z
    primary["clearance"] = clearance
    primary["boundary"] = boundary
    if kind == "pegboard":
        primary["pegboard_standard"] = space_def["pegboard_standard"]
        primary["pegboard_holes_x"] = space_def["pegboard_holes_x"]
        primary["pegboard_holes_y"] = space_def["pegboard_holes_y"]
        primary["pegboard_residual_x"] = space_def["pegboard_residual_x"]
        primary["pegboard_residual_y"] = space_def["pegboard_residual_y"]


def _reconcile_surface_bases(bins: list[dict[str, Any]], layout: dict[str, Any],
                             edge: float) -> None:
    """Keep unprinted Auto platforms on the Surface edge in this transaction."""
    rows = {one["id"]: one for one in bins}
    for row_id, source in design_specs(layout).items():
        row = rows.get(row_id)
        if row is None or not isinstance(source, dict):
            continue
        metadata = source.get("layout")
        if not isinstance(metadata, dict) or metadata.get("surface_base_mode") != "edge":
            continue
        if int(row.get("qty") or 0) > 0:
            metadata["surface_base_mode"] = "custom"
            continue
        box = source.get("box")
        if not isinstance(box, dict):
            continue
        old_base, old_z = float(box["base_thickness"]), float(box["z"])
        headroom = max(MIN_HEIGHT_ABOVE_BASE, old_z - old_base)
        box["base_thickness"] = edge
        box["standard_base"] = False
        box["z"] = edge + headroom
        row["z"] = box["z"]
        if not math.isclose(edge, old_base, abs_tol=1e-9):
            row["file"] = ""


def configure_space(
    output_dir: Path | str, *, raw_def: dict[str, Any], mode: str = "create", allow_legacy: bool = False
) -> dict[str, Any]:
    space_def = normalise_space_definition(raw_def, allow_legacy=allow_legacy)
    with INVENTORY_LOCK:
        path = resolve_inventory_path(output_dir, migrate=True)
        current = _read(path)
        layout = current["layout"] if isinstance(current["layout"], dict) else {}
        if mode == "create" and isinstance(layout.get("space"), dict):
            raise ValueError(f"this folder already holds the space {layout['space'].get('name')!r}")
        _setup_space_layout(layout, space_def)
        if mode == "update" and space_def["kind"] == "surface":
            _reconcile_surface_bases(current["bins"], layout, space_def["z"])
        _write(path, current["bins"], layout, current["legacy"])
        return _payload(path, _read(path))


def configure_space_text(
    text: str, *, title: str, raw_def: dict[str, Any], mode: str = "create", allow_legacy: bool = False
) -> dict[str, Any]:
    space_def = normalise_space_definition(raw_def, allow_legacy=allow_legacy)
    raw = str(text or "")
    with INVENTORY_LOCK:
        current = parse_inventory(raw)
        layout = current["layout"] if isinstance(current["layout"], dict) else {}
        if mode == "create" and isinstance(layout.get("space"), dict):
            raise ValueError(f"this folder already holds the space {layout['space'].get('name')!r}")
        _setup_space_layout(layout, space_def)
        if mode == "update" and space_def["kind"] == "surface":
            _reconcile_surface_bases(current["bins"], layout, space_def["z"])
        rendered = render_inventory(str(title or space_def["name"]), current["bins"], layout)
        return _text_payload(rendered, str(title or space_def["name"]), parse_inventory(rendered))


