"""The drawer inventory file: ``<folder name> bins.md`` in the save folder.

Every bin Wavefinity generates is appended here, and the Drawer layout view
reads and writes the same file, so one place records what has been printed and
where it lives.  The file has two parts:

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
from pathlib import Path
import re
import shutil
import threading
from typing import Any, Iterable

INVENTORY_LOCK = threading.RLock()
LAYOUT_HEADING = "## Drawer layout"
COLUMNS = (
    ("id", "ID"), ("date", "Date"), ("kind", "Kind"), ("name", "Name"),
    ("x", "X (mm)"), ("y", "Y (mm)"), ("z", "Z (mm)"), ("stack", "Stack"),
    ("qty", "Qty"), ("file", "File"), ("label", "Label"), ("interior", "Interior Part(s)"),
)
# bin: generated here.  b4b: a Bin for Bins case.  spacer/shim: made by the
# Layout view to fill a drawer.  manual: typed in for a bin printed elsewhere.
KINDS = ("bin", "b4b", "spacer", "shim", "manual")
# How the bin was printed to stack: not at all, with a snap-on lid, or snapping
# straight into the bin below. For stackable bins Z is the requested module
# contribution; the drawer derives the detached envelope from the interface.
STACK_MODES = ("none", "lid", "direct")
EDITABLE = ("name", "qty", "x", "y", "z", "stack")
MAX_QTY = 999
# A generated bin is not a printed one.  Until the Layout view's setting says
# otherwise, new rows start at Qty 0 and are marked printed by hand.
DEFAULT_NEW_BIN_QTY = 0
# A space is one save folder: a drawer the bins are fitted into, or a box - a
# Bin for Bins case whose inside is the space.
SPACE_KINDS = ("drawer", "box")

_HEADER_KEYS = {
    "id": "id", "date": "date", "kind": "kind", "name": "name",
    "x": "x", "y": "y", "z": "z", "stack": "stack", "stacking": "stack",
    "qty": "qty", "quantity": "qty",
    "file": "file", "label": "label", "interior part(s)": "interior",
    "interior": "interior",
}
_KEEP = object()


def inventory_path(output_dir: Path | str) -> Path:
    output_dir = Path(output_dir).expanduser().resolve()
    return output_dir / f"{output_dir.name} bins.md"


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
    stem = re.sub(rf"^B4B\s+{size}x{size}x{size}", "", stem, flags=re.I)
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
    if kind not in KINDS:
        kind = infer_kind(file, interior)
    name = _text(raw.get("name")) if "name" in raw else infer_name(file, label)
    qty = raw.get("qty")
    stack = _text(raw.get("stack")).lower()
    return {
        "id": _text(raw.get("id")),
        "date": _text(raw.get("date")),
        "kind": kind,
        "name": name,
        "x": x, "y": y, "z": z,
        "stack": stack if stack in STACK_MODES else "none",
        "qty": max(0, min(MAX_QTY, int(_number(qty, 1)))) if _text(qty) else 1,
        "file": file,
        "label": label,
        "interior": interior,
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
                legacy = legacy or "id" not in mapped or "qty" not in mapped
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
    return {"bins": bins, "layout": layout, "warnings": warnings, "legacy": legacy}


# ---------------------------------------------------------------- writing


def _cell(value: Any) -> str:
    text = str(value).replace("|", "/").replace("\r", " ").replace("\n", " ").strip()
    return text or "-"


def _row(one: dict[str, Any]) -> str:
    values = {
        **one,
        "x": f"{float(one['x']):g}", "y": f"{float(one['y']):g}", "z": f"{float(one['z']):g}",
        "qty": str(int(one["qty"])),
        "stack": "" if one.get("stack", "none") == "none" else one["stack"],
    }
    return "| " + " | ".join(_cell(values.get(key, "")) for key, _ in COLUMNS) + " |"


def _compact_json(value: Any, level: int = 0) -> str:
    """JSON that keeps each placement or keep-out on one line, so the block
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
    """Drop placements whose bin row is gone.

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
    return layout


def _payload(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "file": str(path),
        "folder": str(path.parent),
        "exists": path.is_file(),
        "bins": data["bins"],
        "layout": data["layout"],
        "warnings": data["warnings"],
    }


def load_inventory(output_dir: Path | str) -> dict[str, Any]:
    path = inventory_path(output_dir)
    with INVENTORY_LOCK:
        return _payload(path, _read(path))


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


def save_inventory(
    output_dir: Path | str,
    *,
    layout: Any = _KEEP,
    bin_updates: Iterable[dict[str, Any]] = (),
    new_bins: Iterable[dict[str, Any]] = (),
    delete_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge changes into the file on disk and return the fresh contents.

    Only the named rows change; rows added by the generator in the meantime
    survive.  ``layout`` replaces the layout block when given.
    """
    path = inventory_path(output_dir)
    if layout is not _KEEP and layout is not None and not isinstance(layout, dict):
        raise ValueError("drawer layout must be an object")
    with INVENTORY_LOCK:
        current = _read(path)
        bins = current["bins"]
        by_id = {one["id"]: one for one in bins}
        for update in bin_updates or ():
            target = by_id.get(str(update.get("id", "")))
            if target is None:
                raise ValueError(f"no bin {update.get('id')!r} in the inventory")
            target.update(_clean_bin(update, partial=True))
        gone = {str(one) for one in delete_ids or ()}
        bins = [one for one in bins if one["id"] not in gone]
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for raw in new_bins or ():
            clean = _clean_bin(raw, partial=False)
            kind = str(raw.get("kind") or "manual")
            # A caller may choose the ID up front (spacers are placed before
            # they are saved); any clash falls back to the next free one.
            wanted = str(raw.get("id") or "")
            taken = {one["id"] for one in bins}
            bins.append({
                "id": wanted if re.fullmatch(r"B\d+", wanted) and wanted not in taken else next_bin_id(bins),
                "date": now,
                "kind": kind if kind in KINDS else "manual",
                "name": clean.get("name", ""),
                "x": clean["x"], "y": clean["y"], "z": clean["z"],
                "stack": clean.get("stack", "none"),
                "qty": clean.get("qty", 1),
                "file": str(raw.get("file") or ""),
                "label": str(raw.get("label") or ""),
                "interior": str(raw.get("interior") or ""),
            })
        chosen = current["layout"] if layout is _KEEP else layout
        chosen = _prune_layout(chosen, bins)
        _write(path, bins, chosen, current["legacy"])
        return _payload(path, _read(path))


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
    qty: int | None = None,
) -> Path:
    """Log one generated bin as a new row, keeping everything else intact.

    Without an explicit ``qty`` the row takes the Layout view's *new bins
    count as printed* setting, stored in the file's layout block.
    """
    path = inventory_path(output_dir)
    with INVENTORY_LOCK:
        current = _read(path)
        bins = current["bins"]
        if qty is None:
            settings = (current["layout"] or {}).get("settings") or {}
            qty = 1 if settings.get("new_bins_printed", DEFAULT_NEW_BIN_QTY) else 0
        bins.append({
            "id": next_bin_id(bins),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "kind": kind if kind in KINDS else "bin",
            "name": name,
            "x": float(x), "y": float(y), "z": float(z),
            "stack": stack if stack in STACK_MODES else "none",
            "qty": max(0, int(qty)),
            "file": file,
            "label": label,
            "interior": interior,
        })
        _write(path, bins, current["layout"], current["legacy"])
    return path


def create_space(
    output_dir: Path | str, *, name: str, kind: str, x: float, y: float, z: float,
) -> dict[str, Any]:
    """Start a folder's inventory as a named space.

    The space goes in the layout block with one drawer the size of its inside,
    so the Layout view opens ready to fill it.  A box's inside is a B4B child
    field the bins sit in wall to wall, so it asks for no extra clearance.
    """
    name = str(name or "").strip()[:80]
    if not name:
        raise ValueError("a space needs a name")
    if kind not in SPACE_KINDS:
        raise ValueError(f"a space is one of {', '.join(SPACE_KINDS)}")
    size = [_number(value) for value in (x, y, z)]
    if min(size) <= 0:
        raise ValueError("a space needs its inside X, Y and Z in mm")
    path = inventory_path(output_dir)
    with INVENTORY_LOCK:
        current = _read(path)
        layout = current["layout"] if isinstance(current["layout"], dict) else {}
        if isinstance(layout.get("space"), dict):
            raise ValueError(f"this folder already holds the space {layout['space'].get('name')!r}")
        layout["version"] = 1
        layout["space"] = {"name": name, "kind": kind, "x": size[0], "y": size[1], "z": size[2]}
        if not layout.get("drawers"):
            layout["drawers"] = [{
                "id": "d1", "name": name, "width": size[0], "depth": size[1], "height": size[2],
                "clearance": 0.0 if kind == "box" else 1.0, "keepouts": [], "placements": [],
            }]
            layout["active"] = "d1"
        _write(path, current["bins"], layout, current["legacy"])
        return _payload(path, _read(path))
