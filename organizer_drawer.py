"""Drawer layout: fitting printed bins into a real drawer.

Pure 2D planning on the bin grid, plus the geometry it owns - the spacers and
shims that fill whatever the bins leave, and the connectors a layout needs.
Drawer coordinates: x runs left to right, y runs from the front (0) to the
back, z is height.  The Layout view draws the front at the bottom.

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
* Stacked: ``on`` names the placement directly below (``"B3:0"``).  Only a
  stackable bin of the same footprint and the same stacking style can snap
  onto another; each one adds its requested module height.  The exposed top
  interlock remains part of the stack's physical drawer-height envelope.
* Free, for an edge shim: ``x``/``y``/``w``/``d`` in mm from the drawer's
  inside front-left corner, plus the ``side`` it lines.

A copy numbered past its row's printed Qty is *planned*: placed before it is
printed, so a drawer can be designed first and printed to.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry import box as shape_box
import trimesh

from organizer_app import connector_filename, generate_side_file
from organizer_engine import (
    BASE_UNIT,
    DEFAULT_ARM_THICKNESS,
    DEFAULT_WALL,
    LOCKED_CONNECTOR_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    BoxSpec,
    ConnectorSpec,
    export_mesh,
    make_wall_lock_bumps,
    placed_outline,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_geometry import _extrude_polygon, difference, union
from organizer_inventory import INVENTORY_LOCK, load_inventory, next_bin_id, save_inventory
from organizer_stack import STACK_MIN_WALL, STACK_PLUG_DEPTH, STACK_SEAT_DEPTH

UNIT = BASE_UNIT
SNAPS = (8.0, 4.0)
# How far a bin's wave crests stand past its grid footprint on each side.
CREST = WAVE_AMPLITUDE - WAVE_MATING_GAP / 2.0
# Total slack per axis a drawer needs just to take the crests at both walls.
MIN_CLEARANCE = 2.0 * CREST
MIN_SHIM = 1.2                  # thinnest shim worth printing, at a wave trough
MIN_SPACER_HEIGHT = 6.0         # a spacer frame still needs room for its lock bumps
DEFAULT_SPACER_HEIGHT = 15.0
RIB_WIDTH = 1.6                 # the X brace inside a spacer: four 0.4 mm lines
MIN_RIB_SPAN = 10.0             # narrower than this inside, a frame needs no brace
MIN_CONNECTOR_SEAM = 16.0       # mm of shared wall a connector needs
HEIGHT_TOLERANCE = 0.5          # mm; "taller" means taller by more than this
# How far a stacked bin's foot sinks into the one below, by stacking style.
STACK_STEPS = {"lid": STACK_SEAT_DEPTH, "direct": STACK_PLUG_DEPTH}

DRAWER_DEFAULTS: dict[str, Any] = {
    "name": "Drawer", "width": 400.0, "depth": 300.0, "height": 60.0,
    "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "snap": 8.0,
}
ANCHORS = ("front-left", "center")
HEIGHT_RULES = ("strict", "prefer", "ignore")
HEIGHT_REACHES = ("column", "adjacent")
SPACER_FILLS = ("all", "edges", "cells")
SIDES = ("left", "right", "front", "back")
# Low filler nobody reaches for: spacers take room but are never counted for
# or against the height rule.
SPACER_KINDS = ("spacer", "shim")


# ---------------------------------------------------------------- drawer model


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"drawer {name} must be a number of mm") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"drawer {name} must be a positive number of mm")
    return number


def normalise_drawer(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("a drawer must be an object")
    drawer = {**DRAWER_DEFAULTS, **raw}
    for key in ("width", "depth", "height"):
        drawer[key] = _positive(drawer[key], key)
    drawer["clearance"] = max(MIN_CLEARANCE, float(drawer.get("clearance") or 0.0))
    if drawer["anchor"] not in ANCHORS:
        drawer["anchor"] = "front-left"
    if drawer["bin_axis"] not in ("x", "y"):
        drawer["bin_axis"] = "x"
    drawer["snap"] = 4.0 if float(drawer.get("snap") or 8.0) == 4.0 else 8.0
    keepouts = []
    for one in drawer.get("keepouts") or []:
        try:
            box = {key: float(one[key]) for key in ("x", "y", "w", "d")}
        except (KeyError, TypeError, ValueError):
            continue
        if box["w"] > 0 and box["d"] > 0:
            keepouts.append(box)
    drawer["keepouts"] = keepouts
    drawer["placements"] = [one for one in drawer.get("placements") or [] if isinstance(one, dict)]
    return drawer


def find_drawer(layout: dict[str, Any], drawer_id: str | None = None) -> dict[str, Any]:
    """The raw drawer dict inside ``layout`` (not a copy)."""
    drawers = [one for one in (layout or {}).get("drawers") or [] if isinstance(one, dict)]
    if not drawers:
        raise ValueError("the layout has no drawers")
    wanted = drawer_id or (layout or {}).get("active")
    return next((one for one in drawers if one.get("id") == wanted), drawers[0])


def drawer_grid(drawer: dict[str, Any]) -> dict[str, Any]:
    """Where the grid sits in the drawer and what it leaves at the edges.

    ``cols``/``rows`` count snap cells (8 mm, or 4 mm on a fine drawer).  The
    clearance is total slack per axis: half of it sits at each wall so the wave
    crests of the outermost bins clear the drawer sides.
    """
    step = drawer["snap"]
    slack = drawer["clearance"]
    usable_x = drawer["width"] - slack
    usable_y = drawer["depth"] - slack
    cols = max(0, int(math.floor(usable_x / step + 1e-6)))
    rows = max(0, int(math.floor(usable_y / step + 1e-6)))
    spare_x = usable_x - cols * step
    spare_y = usable_y - rows * step
    ox = slack / 2.0 + (spare_x / 2.0 if drawer["anchor"] == "center" else 0.0)
    oy = slack / 2.0 + (spare_y / 2.0 if drawer["anchor"] == "center" else 0.0)
    return {
        "step": step, "cols": cols, "rows": rows, "ox": ox, "oy": oy,
        "gap_left": ox,
        "gap_right": drawer["width"] - ox - cols * step,
        "gap_front": oy,
        "gap_back": drawer["depth"] - oy - rows * step,
    }


def _per_unit(drawer: dict[str, Any]) -> int:
    """Grid cells per 8 mm unit: 1, or 2 on a drawer that snaps to 4 mm."""
    return int(round(UNIT / drawer["snap"]))


def _cell(units: Any, drawer: dict[str, Any]) -> int:
    return int(round(float(units) * _per_unit(drawer)))


def _units(cell: int, drawer: dict[str, Any]) -> float | int:
    value = cell / _per_unit(drawer)
    return int(value) if float(value).is_integer() else value


def bin_cells(one: dict[str, Any], drawer: dict[str, Any]) -> tuple[int, int]:
    """A bin's footprint in grid cells, as it stands in this drawer."""
    step = drawer["snap"]
    cx = max(1, math.ceil(float(one["x"]) / step - 1e-6))
    cy = max(1, math.ceil(float(one["y"]) / step - 1e-6))
    return (cy, cx) if drawer["bin_axis"] == "y" else (cx, cy)


def stack_pitch(one: dict[str, Any]) -> float:
    """What a bin adds between consecutive stack seating datums."""
    return float(one["z"])


def stack_part_height(one: dict[str, Any]) -> float:
    """Detached physical height, including the interlocking foot depth."""
    return float(one["z"]) + STACK_STEPS.get(one.get("stack", "none"), 0.0)


def _key(placement: dict[str, Any]) -> str:
    return f"{placement.get('bin')}:{int(placement.get('copy', 0))}"


def _label(one: dict[str, Any]) -> str:
    return one.get("name") or f"{float(one['x']):g} x {float(one['y']):g}"


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.05


def _blocked(drawer: dict[str, Any], grid: dict[str, Any]) -> np.ndarray:
    step = grid["step"]
    blocked = np.zeros((grid["rows"], grid["cols"]), dtype=bool)
    for zone in drawer["keepouts"]:
        x0 = (zone["x"] - grid["ox"]) / step
        y0 = (zone["y"] - grid["oy"]) / step
        x1 = x0 + zone["w"] / step
        y1 = y0 + zone["d"] / step
        c0, c1 = max(0, math.floor(x0 + 1e-6)), min(grid["cols"], math.ceil(x1 - 1e-6))
        r0, r1 = max(0, math.floor(y0 + 1e-6)), min(grid["rows"], math.ceil(y1 - 1e-6))
        if c1 > c0 and r1 > r0:
            blocked[r0:r1, c0:c1] = True
    return blocked


def _chains(drawer: dict[str, Any], by_id: dict[str, dict]) -> tuple[list[list[dict]], list[dict]]:
    """The drawer's grid placements grouped into stacks, bottom first, plus
    any stacked placement whose support is missing."""
    placements = [p for p in drawer["placements"] if p.get("bin") in by_id]
    keyed = {_key(p): p for p in placements}
    above: dict[str, dict] = {}
    loose = []
    for p in placements:
        if "on" in p:
            if p["on"] in keyed and p["on"] not in above:
                above[p["on"]] = p
            else:
                loose.append(p)
    chains, used = [], set()
    for base in placements:
        if "gx" not in base or "on" in base:
            continue
        chain = [base]
        used.add(_key(base))
        while _key(chain[-1]) in above and _key(above[_key(chain[-1])]) not in used:
            chain.append(above[_key(chain[-1])])
            used.add(_key(chain[-1]))
        chains.append(chain)
    loose += [p for p in placements if "on" in p and _key(p) not in used and p not in loose]
    return chains, loose


def _stack_item(chain: list[dict], drawer: dict[str, Any], by_id: dict[str, dict]) -> dict[str, Any]:
    """One grid footprint: a single bin, or a stack of them."""
    base = chain[0]
    first = by_id[base["bin"]]
    w, d = bin_cells(first, drawer)
    layers, issues, top = [], [], 0.0
    for index, placement in enumerate(chain):
        one = by_id[placement["bin"]]
        bottom = 0.0
        if index:
            below = by_id[chain[index - 1]["bin"]]
            mode, under = one.get("stack", "none"), below.get("stack", "none")
            if mode == "none":
                issues.append(f"{_label(one)} was not printed to stack")
            elif under != mode:
                issues.append(f"{_label(one)} ({mode} stacking) cannot snap onto {_label(below)} ({'not stackable' if under == 'none' else under + ' stacking'})")
            if not (_close(one["x"], below["x"]) and _close(one["y"], below["y"])):
                issues.append(f"{_label(one)} is not the same size as {_label(below)} under it")
            bottom = top - STACK_STEPS.get(mode, 0.0)
        top = bottom + stack_part_height(one)
        layers.append({
            "key": _key(placement), "bin": placement["bin"], "copy": int(placement.get("copy", 0)),
            "z0": bottom, "z1": top, "planned": int(placement.get("copy", 0)) >= int(one["qty"]),
        })
    return {
        "key": _key(base), "keys": [layer["key"] for layer in layers],
        "bin": base["bin"], "copy": int(base.get("copy", 0)),
        "gx": _cell(base["gx"], drawer), "gy": _cell(base["gy"], drawer),
        "w": w, "d": d, "h": top,
        "kind": first.get("kind", "bin"), "name": first.get("name", ""),
        "locked": bool(base.get("locked", False)),
        "chain": chain, "layers": layers, "top": by_id[chain[-1]["bin"]], "issues": issues,
    }


def _grid_items(drawer: dict[str, Any], by_id: dict[str, dict]) -> list[dict[str, Any]]:
    return [_stack_item(chain, drawer, by_id) for chain in _chains(drawer, by_id)[0]]


def _height_issues(items: list[dict[str, Any]], reach: str = "column") -> list[tuple[dict, dict]]:
    """(front, behind) pairs where a taller bin or stack stands in front of a
    shorter one it overlaps across the drawer - the short one is hidden and
    hard to reach.  ``adjacent`` counts only one standing right against it."""
    issues = []
    for front in items:
        for back in items:
            if (front is not back
                    and front.get("kind") not in SPACER_KINDS
                    and back.get("kind") not in SPACER_KINDS
                    and (back["gy"] == front["gy"] + front["d"] if reach == "adjacent"
                         else back["gy"] >= front["gy"] + front["d"])
                    and back["gx"] < front["gx"] + front["w"]
                    and front["gx"] < back["gx"] + back["w"]
                    and front["h"] > back["h"] + HEIGHT_TOLERANCE):
                issues.append((front, back))
    return issues


def _largest_empty(free: np.ndarray) -> tuple[int, int, int, int, int]:
    """(area, gx, gy, w, d) of the largest all-True rectangle."""
    rows, cols = free.shape
    best = (0, 0, 0, 0, 0)
    heights = [0] * cols
    for row in range(rows):
        for col in range(cols):
            heights[col] = heights[col] + 1 if free[row, col] else 0
        stack: list[tuple[int, int]] = []
        for col in range(cols + 1):
            height = heights[col] if col < cols else 0
            start = col
            while stack and stack[-1][1] >= height:
                left, tall = stack.pop()
                area = tall * (col - left)
                if area > best[0]:
                    best = (area, left, row - tall + 1, col - left, tall)
                start = left
            stack.append((start, height))
    return best


def _top_wall(item: dict[str, Any]) -> float:
    """The wall a connector meets at the top of this footprint: stacking
    raises a bin's wall to hold its snap groove."""
    return STACK_MIN_WALL if item["top"].get("stack", "none") != "none" else DEFAULT_WALL


def _connectors(items: list[dict[str, Any]], step: float) -> tuple[list[dict[str, Any]], int]:
    """One connector per shared seam long enough to seat one, grouped by the
    two rim heights it joins.  Stacks join at their top bins.  Returns the
    groups and how many seams join walls of different thickness, which no
    printed connector fits."""
    counts: dict[tuple[float, float, float], int] = {}
    mismatched = 0
    need = math.ceil(MIN_CONNECTOR_SEAM / step - 1e-9)
    for index, a in enumerate(items):
        for b in items[index + 1:]:
            # X spacers nest by their waves alone; they never need a clip.
            if a["kind"] in SPACER_KINDS or b["kind"] in SPACER_KINDS:
                continue
            if a["gx"] + a["w"] == b["gx"] or b["gx"] + b["w"] == a["gx"]:
                overlap = min(a["gy"] + a["d"], b["gy"] + b["d"]) - max(a["gy"], b["gy"])
            elif a["gy"] + a["d"] == b["gy"] or b["gy"] + b["d"] == a["gy"]:
                overlap = min(a["gx"] + a["w"], b["gx"] + b["w"]) - max(a["gx"], b["gx"])
            else:
                continue
            if overlap < need:
                continue
            wall_a, wall_b = _top_wall(a), _top_wall(b)
            if not math.isclose(wall_a, wall_b):
                mismatched += 1
                continue
            key = (*sorted((round(a["h"], 2), round(b["h"], 2)), reverse=True), wall_a)
            counts[key] = counts.get(key, 0) + 1
    groups = [
        {"heights": [key[0], key[1]], "wall": key[2], "count": count}
        for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return groups, mismatched


def drawer_report(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], reach: str = "column") -> dict[str, Any]:
    """Everything the Layout view says about one drawer: fill, what is left,
    what is wrong, what is still to print, and the connectors it needs."""
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    by_id = {one["id"]: one for one in bins}
    blocked = _blocked(drawer, grid)
    owner = np.full((rows, cols), -1, dtype=int)
    problems: list[dict[str, Any]] = []
    for placement in drawer["placements"]:
        if placement.get("bin") not in by_id:
            problems.append({"type": "missing", "keys": [_key(placement)], "message": f"{placement.get('bin')} is no longer in the inventory"})
    chains, loose = _chains(drawer, by_id)
    for placement in loose:
        problems.append({"type": "floating", "keys": [_key(placement)], "message": f"{_label(by_id[placement['bin']])} is stacked on nothing"})
    # Edge shims were cut for the drawer as it was; resizing it, moving the
    # grid or changing the snap can leave one across the grid or the wall.
    inset = CREST + 0.05
    grid_box = {"x": grid["ox"] + inset, "y": grid["oy"] + inset, "w": cols * step - 2 * inset, "d": rows * step - 2 * inset}
    for placement in drawer["placements"]:
        if "gx" in placement or "on" in placement or placement.get("bin") not in by_id:
            continue
        shim = {key: float(placement.get(key, 0.0)) for key in ("x", "y", "w", "d")}
        if (_overlaps(shim, grid_box) or shim["x"] < -0.1 or shim["y"] < -0.1
                or shim["x"] + shim["w"] > drawer["width"] + 0.1 or shim["y"] + shim["d"] > drawer["depth"] + 0.1):
            problems.append({"type": "shim", "keys": [_key(placement)], "message": "An edge shim no longer fits this drawer - take the spacers out and make them again"})
    items = [_stack_item(chain, drawer, by_id) for chain in chains]
    per_unit = _per_unit(drawer)
    for index, item in enumerate(items):
        label = _label(by_id[item["bin"]])
        if len(item["layers"]) > 1:
            label = f"The stack of {len(item['layers'])} on {label}"
        for issue in item["issues"]:
            problems.append({"type": "stack", "keys": item["keys"], "message": issue})
        if item["h"] > drawer["height"] + 1e-6:
            problems.append({"type": "too_tall", "keys": item["keys"], "message": f"{label} is {item['h']:g} mm tall; the drawer takes {drawer['height']:g} mm"})
        base = item["chain"][0]
        if per_unit == 1 and (float(base["gx"]) % 1 or float(base["gy"]) % 1):
            problems.append({"type": "outside", "keys": item["keys"], "message": f"{label} sits off the 8 mm grid - move it to snap it back"})
        x0, y0 = item["gx"], item["gy"]
        x1, y1 = x0 + item["w"], y0 + item["d"]
        if x0 < 0 or y0 < 0 or x1 > cols or y1 > rows:
            problems.append({"type": "outside", "keys": item["keys"], "message": f"{label} sticks out of the drawer"})
        cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(cols, x1), min(rows, y1)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        if blocked[cy0:cy1, cx0:cx1].any():
            problems.append({"type": "keepout", "keys": item["keys"], "message": f"{label} sits on a keep-out zone"})
        region = owner[cy0:cy1, cx0:cx1]
        for other in sorted({int(v) for v in region[region >= 0]}):
            problems.append({"type": "overlap", "keys": items[other]["keys"] + item["keys"], "message": f"{_label(by_id[items[other]['bin']])} and {_label(by_id[item['bin']])} overlap"})
        region[region < 0] = index
    issues = _height_issues(items, reach)
    for front, back in issues:
        problems.append({
            "type": "height", "keys": back["keys"],
            "message": f"{_label(by_id[back['bin']])} ({back['h']:g} mm) is behind taller {_label(by_id[front['bin']])} ({front['h']:g} mm)",
        })
    used = int((owner >= 0).sum())
    blocked_cells = int(blocked.sum())
    usable = rows * cols - blocked_cells
    free = (owner < 0) & ~blocked
    area, lx, ly, lw, ld = _largest_empty(free) if rows and cols else (0, 0, 0, 0, 0)
    shim_area = sum(
        float(p.get("w", 0)) * float(p.get("d", 0))
        for p in drawer["placements"] if "gx" not in p and "on" not in p and p.get("bin") in by_id
    )
    connectors, mismatched = _connectors(items, step)
    planned: dict[str, int] = {}
    for placement in drawer["placements"]:
        one = by_id.get(placement.get("bin"))
        if one and int(placement.get("copy", 0)) >= int(one["qty"]):
            planned[one["id"]] = planned.get(one["id"], 0) + 1
    return {
        "grid": grid,
        "cells": {"total": usable, "used": used, "free": int(free.sum()), "blocked": blocked_cells},
        "fill": round(100.0 * used / usable, 1) if usable else 0.0,
        "free_mm2": round(float(free.sum()) * step * step),
        "edge_mm2": round(max(0.0, drawer["width"] * drawer["depth"] - rows * cols * step * step - shim_area)),
        "largest": {"gx": lx, "gy": ly, "w": lw, "d": ld, "w_mm": lw * step, "d_mm": ld * step} if area else None,
        "connectors": connectors,
        "connector_total": sum(one["count"] for one in connectors),
        "connector_mismatched": mismatched,
        "problems": problems,
        "height_issues": len(issues),
        "placed": sum(len(item["layers"]) for item in items),
        "stacks": sum(1 for item in items if len(item["layers"]) > 1),
        "planned": planned,
        "shims": sum(1 for p in drawer["placements"] if "gx" not in p and "on" not in p),
    }


# ---------------------------------------------------------------- auto layout


def _sat(grid: np.ndarray) -> np.ndarray:
    table = np.zeros((grid.shape[0] + 1, grid.shape[1] + 1), dtype=np.int32)
    table[1:, 1:] = grid.astype(np.int32).cumsum(0).cumsum(1)
    return table


def _window(sat: np.ndarray, y_off: int, x_off: int, h: int, w: int, ny: int, nx: int) -> np.ndarray:
    """Sum of every h x w window starting at (gy + y_off, gx + x_off), for all
    gy < ny and gx < nx at once."""
    y0, x0 = y_off, x_off
    return (
        sat[y0 + h:y0 + h + ny, x0 + w:x0 + w + nx]
        - sat[y0:y0 + ny, x0 + w:x0 + w + nx]
        - sat[y0 + h:y0 + h + ny, x0:x0 + nx]
        + sat[y0:y0 + ny, x0:x0 + nx]
    )


def _score_rows(gx, gy, contact, rows, cols):
    return gy * 1000.0 - gx * 10.0 + contact


def _score_tight(gx, gy, contact, rows, cols):
    return contact * 100.0 + gy / max(rows, 1) * 10.0 - gx / max(cols, 1)


def _score_columns(gx, gy, contact, rows, cols):
    return -gx * 1000.0 + gy * 10.0 + contact


def _by_height(item):
    return (-item["h"], -item["w"] * item["d"], -item["w"], item["name"], item["bin"], item["copy"])


def _by_height_then_depth(item):
    return (-item["h"], -item["d"], -item["w"], item["name"], item["bin"], item["copy"])


def _by_area(item):
    return (-item["w"] * item["d"], -item["h"], item["name"], item["bin"], item["copy"])


STRATEGIES: tuple[tuple[str, str, str, Callable, Callable], ...] = (
    ("rows", "Tidy rows", "Tallest at the back, filled in rows from the left.", _by_height, _score_rows),
    ("tight", "Tight fit", "Tallest at the back; each bin goes where it touches the most neighbours.", _by_height, _score_tight),
    ("columns", "Columns", "Tallest at the back, filled in columns from the left.", _by_height_then_depth, _score_columns),
    ("most", "Most bins", "Biggest bins first, packed for the fullest drawer.", _by_area, _score_tight),
)


def _pack(rows, cols, blocked, fixed, items, order, scorer, height_rule, reach="column"):
    occupied = blocked.copy()
    heights = np.zeros((rows, cols))
    has_bin = np.zeros((rows, cols), dtype=bool)

    def mark(item):
        x0, y0 = max(0, item["gx"]), max(0, item["gy"])
        x1, y1 = min(cols, item["gx"] + item["w"]), min(rows, item["gy"] + item["d"])
        if x1 > x0 and y1 > y0:
            occupied[y0:y1, x0:x1] = True
            if item.get("kind") not in SPACER_KINDS:
                has_bin[y0:y1, x0:x1] = True
                heights[y0:y1, x0:x1] = item["h"]

    for item in fixed:
        mark(item)
    placed, unplaced = [], []
    for item in sorted(items, key=order):
        w, d, h = item["w"], item["d"], item["h"]
        if w > cols or d > rows:
            unplaced.append({**item, "reason": "bigger than the drawer"})
            continue
        ny, nx = rows - d + 1, cols - w + 1
        free = _window(_sat(occupied), 0, 0, d, w, ny, nx) == 0
        if not free.any():
            unplaced.append({**item, "reason": "no room left"})
            continue
        padded = _sat(np.pad(occupied, 1, constant_values=True))
        contact = (
            _window(padded, 1, 0, d, 1, ny, nx) + _window(padded, 1, w + 1, d, 1, ny, nx)
            + _window(padded, 0, 1, 1, w, ny, nx) + _window(padded, d + 1, 1, 1, w, ny, nx)
        ) / (2.0 * (w + d))
        gy, gx = np.mgrid[0:ny, 0:nx]
        score = scorer(gx, gy, contact, rows, cols)
        allowed = free
        if height_rule != "ignore" and item.get("kind") not in SPACER_KINDS:
            behind_heights = np.where(has_bin, heights, np.inf)
            if reach == "adjacent":
                # front[r] is the row just in front of r; behind[r] is row r.
                front = np.vstack([np.zeros((1, cols)), heights])
                behind = np.vstack([behind_heights, np.full((1, cols), np.inf)])
            else:
                front = np.maximum.accumulate(np.vstack([np.zeros((1, cols)), heights]), axis=0)
                behind = np.minimum.accumulate(
                    np.vstack([behind_heights, np.full((1, cols), np.inf)])[::-1], axis=0
                )[::-1]
            taller_in_front = sliding_window_view(front[:ny], w, axis=1).max(axis=2) > h + HEIGHT_TOLERANCE
            shorter_behind = sliding_window_view(behind[d:d + ny], w, axis=1).min(axis=2) < h - HEIGHT_TOLERANCE
            violation = taller_in_front | shorter_behind
            if height_rule == "strict":
                allowed = free & ~violation
            else:
                score = score - violation * 1e6
        if not allowed.any():
            unplaced.append({**item, "reason": "no spot keeps taller bins behind it"})
            continue
        best = int(np.argmax(np.where(allowed, score, -np.inf)))
        row, col = divmod(best, nx)
        placed_item = {**item, "gx": int(col), "gy": int(row)}
        mark(placed_item)
        placed.append(placed_item)
    return placed, unplaced


def _build_stacks(singles: list[dict[str, Any]], max_height: float) -> list[dict[str, Any]]:
    """Snap stackable bins of one footprint and one stacking style into
    stacks, tallest at the bottom, as high as the drawer allows."""
    groups: dict[tuple, list[dict]] = {}
    items = []
    for single in singles:
        one = single["row"]
        if one.get("stack", "none") in STACK_STEPS and one.get("kind") not in ("b4b", *SPACER_KINDS):
            groups.setdefault((round(float(one["x"]), 2), round(float(one["y"]), 2), one["stack"]), []).append(single)
        else:
            items.append(single)
    for members in groups.values():
        members.sort(key=lambda single: (-float(single["row"]["z"]), single["bin"], single["copy"]))
        current: list[dict] = []
        height = 0.0
        for single in members:
            added = stack_part_height(single["row"]) if not current else stack_pitch(single["row"])
            if current and height + added > max_height + 1e-6:
                items.append(_merge(current, height))
                current, height = [], 0.0
                added = stack_part_height(single["row"])
            current.append(single)
            height += added
        if current:
            items.append(_merge(current, height))
    return items


def _merge(members: list[dict[str, Any]], height: float) -> dict[str, Any]:
    if len(members) == 1:
        return members[0]
    base = members[0]
    return {**base, "h": height, "members": [(m["bin"], m["copy"]) for m in members]}


def auto_layout(
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Several arrangements for one drawer, best first.

    Options: ``mode`` ``rearrange`` (move everything not locked) or ``fill``
    (only add bins around the current ones); ``height_rule`` ``strict`` (never a
    short bin behind a taller one), ``prefer`` or ``ignore``; ``height_reach``
    ``column`` (anything in front) or ``adjacent`` (only the bin right in
    front); ``keep_locked``; ``include_spacers``; ``stack_bins`` (snap
    stackable bins into stacks as tall as the drawer takes); ``only`` - a list
    of ``{bin, copy}`` to place, which is how the view drops one bin into the
    best free spot.  A copy past the printed Qty in ``only`` is placed as a
    planned bin.
    """
    options = options or {}
    raw = find_drawer(layout, drawer_id)
    drawer = normalise_drawer(raw)
    grid = drawer_grid(drawer)
    rows, cols = grid["rows"], grid["cols"]
    by_id = {one["id"]: one for one in bins}
    mode = options.get("mode", "rearrange")
    height_rule = options.get("height_rule", "strict")
    if height_rule not in HEIGHT_RULES:
        height_rule = "strict"
    reach = options.get("height_reach", "column")
    if reach not in HEIGHT_REACHES:
        reach = "column"
    keep_locked = bool(options.get("keep_locked", True))
    include_spacers = bool(options.get("include_spacers", False))
    stack_bins = bool(options.get("stack_bins", True))
    only = {(str(one.get("bin")), int(one.get("copy", 0))) for one in options.get("only") or []}

    elsewhere = {
        (p.get("bin"), int(p.get("copy", 0)))
        for other in layout.get("drawers") or [] if isinstance(other, dict) and other is not raw
        for p in other.get("placements") or [] if isinstance(p, dict)
    }
    chains, _ = _chains(drawer, by_id)
    keep_placements, fixed, loose_copies = [], [], []
    dropped_spacers = 0
    for placement in drawer["placements"]:
        if placement.get("bin") in by_id and "gx" not in placement and "on" not in placement:
            keep_placements.append(placement)          # edge shims stay where they are
    for chain in chains:
        base = chain[0]
        if mode == "fill" or only or (keep_locked and base.get("locked")):
            keep_placements += chain
            fixed.append(_stack_item(chain, drawer, by_id))
            continue
        for placement in chain:
            one = by_id[placement["bin"]]
            if one.get("kind") in SPACER_KINDS and not include_spacers:
                dropped_spacers += 1
            else:
                loose_copies.append((one["id"], int(placement.get("copy", 0))))
    kept = {(p.get("bin"), int(p.get("copy", 0))) for p in keep_placements}

    wanted: list[tuple[str, int]] = list(loose_copies)
    for one in bins:
        if one.get("kind") == "shim":
            continue
        if one.get("kind") == "spacer" and not include_spacers and not only:
            continue
        for copy in range(int(one["qty"])):
            key = (one["id"], copy)
            if key not in elsewhere and key not in kept and key not in wanted:
                wanted.append(key)
    for key in only:
        if key[0] in by_id and key not in wanted and key not in kept and key not in elsewhere:
            wanted.append(key)
    if only:
        wanted = [key for key in wanted if key in only]

    singles, skipped = [], []
    for bin_id, copy in wanted:
        one = by_id[bin_id]
        w, d = bin_cells(one, drawer)
        single = {
            "key": f"{bin_id}:{copy}", "bin": bin_id, "copy": copy, "row": one,
            "w": w, "d": d, "h": float(one["z"]), "name": one.get("name", ""),
            "kind": one.get("kind", "bin"),
        }
        if single["h"] > drawer["height"] + 1e-6:
            skipped.append({"bin": bin_id, "copy": copy, "reason": f"taller than the drawer ({single['h']:g} > {drawer['height']:g} mm)"})
        else:
            singles.append(single)
    items = _build_stacks(singles, drawer["height"]) if stack_bins else singles

    blocked = _blocked(drawer, grid)
    strategies = [s for s in STRATEGIES if s[0] == "tight"] if only else list(STRATEGIES)
    candidates, seen = [], set()
    usable = rows * cols - int(blocked.sum())

    def placements_for(item):
        members = item.get("members") or [(item["bin"], item["copy"])]
        out = [{"bin": members[0][0], "copy": members[0][1],
                "gx": _units(item["gx"], drawer), "gy": _units(item["gy"], drawer), "locked": False}]
        for (below_bin, below_copy), (bin_id, copy) in zip(members, members[1:]):
            out.append({"bin": bin_id, "copy": copy, "on": f"{below_bin}:{below_copy}"})
        return out

    def run(strategy, rule, name=None, description=None):
        ident, title, blurb, order, scorer = strategy
        placed, unplaced = _pack(rows, cols, blocked, fixed, items, order, scorer, rule, reach)
        signature = frozenset((p["bin"], p["copy"], p["gx"], p["gy"]) for p in placed)
        if signature in seen and placed:
            return
        seen.add(signature)
        everything = fixed + [{**p, "top": by_id[(p.get("members") or [(p["bin"],)])[-1][0]]} for p in placed]
        used = sum(item["w"] * item["d"] for item in everything)
        count = lambda group: sum(len(item.get("members") or [0]) for item in group)
        candidates.append({
            "id": ident if rule == height_rule else f"{ident}-{rule}",
            "name": name or title,
            "description": description or blurb,
            "placements": keep_placements + [p for item in placed for p in placements_for(item)],
            "unplaced": [
                {"bin": bin_id, "copy": copy, "reason": u["reason"]}
                for u in unplaced for bin_id, copy in (u.get("members") or [(u["bin"], u["copy"])])
            ],
            "stats": {
                "placed": count(placed),
                "wanted": count(items),
                "stacks": sum(1 for item in placed if item.get("members")),
                "fill": round(100.0 * used / usable, 1) if usable else 0.0,
                "height_issues": len(_height_issues(everything, reach)),
                "connectors": sum(one["count"] for one in _connectors(everything, grid["step"])[0]),
            },
        })

    for strategy in strategies:
        run(strategy, height_rule)
    # When the height rule is what left bins out, offer the layout that bends it.
    if height_rule == "strict" and any(
        u["reason"].startswith("no spot keeps") for c in candidates for u in c["unplaced"]
    ):
        run(STRATEGIES[1], "prefer", "Fits more", "Bends the height rule where it has to, so more bins fit.")
    order = {id(c): index for index, c in enumerate(candidates)}
    candidates.sort(key=lambda c: (-c["stats"]["placed"], c["stats"]["height_issues"], order[id(c)]))
    notes = []
    if dropped_spacers:
        notes.append(f"{dropped_spacers} spacer{'s' if dropped_spacers != 1 else ''} taken out - make spacers again once the layout settles.")
    return {"candidates": candidates, "skipped": skipped, "notes": notes}


# ---------------------------------------------------------------- spacers


def plan_spacers(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
    """What it takes to fill a drawer: X spacers for empty grid patches and
    wavy-faced shims for the strips between the grid and the drawer walls.

    ``leave_open`` (mm) keeps any gap at least that wide in both directions
    empty - room for a bin not printed yet.
    """
    options = options or {}
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    per_unit = _per_unit(drawer)
    fill = options.get("fill", "all")
    if fill not in SPACER_FILLS:
        fill = "all"
    height = min(drawer["height"], max(MIN_SPACER_HEIGHT, float(options.get("height") or DEFAULT_SPACER_HEIGHT)))
    max_length = max(2 * UNIT, float(options.get("max_length") or 250.0))
    leave_open = max(0.0, float(options.get("leave_open") or 0.0))
    by_id = {one["id"]: one for one in bins}
    notes: list[str] = []

    cells = []
    if fill in ("all", "cells") and rows and cols:
        free = ~_blocked(drawer, grid)
        for item in _grid_items(drawer, by_id):
            free[max(0, item["gy"]):max(0, item["gy"] + item["d"]), max(0, item["gx"]):max(0, item["gx"] + item["w"])] = False
        longest = max(1, int(max_length // UNIT)) * per_unit
        slivers = 0
        while True:
            area, gx, gy, w, d = _largest_empty(free)
            if area <= 0:
                break
            if leave_open and min(w, d) * step >= leave_open - 1e-6:
                free[gy:gy + d, gx:gx + w] = False
                notes.append(f"Left a {w * step:g} × {d * step:g} mm gap open.")
                continue
            # A spacer is a whole number of 8 mm units: on a 4 mm drawer an odd
            # cell left over is a sliver nothing printable fits.
            w, d = min(w - w % per_unit, longest), min(d - d % per_unit, longest)
            if not w or not d:
                free[gy:gy + max(d, 1), gx:gx + max(w, 1)] = False
                slivers += 1
                continue
            free[gy:gy + d, gx:gx + w] = False
            cells.append({"gx": gx, "gy": gy, "w": w, "d": d})
        if slivers:
            notes.append(f"{slivers} gap{'s' if slivers != 1 else ''} only 4 mm wide left open - no spacer is that thin.")

    shims = []
    if fill in ("all", "edges") and rows and cols:
        wall = drawer["clearance"] / 2.0
        taken = {p.get("side") for p in drawer["placements"] if "gx" not in p and "on" not in p and p.get("bin") in by_id}
        longest = max(1, int(max_length // UNIT))
        for side in SIDES:
            play = grid[f"gap_{side}"] - wall
            if side in taken or play < 0.05:
                continue
            pieces = _shim_outlines(drawer, grid, side, longest)
            across = 0 if side in ("left", "right") else 1
            # The bin-facing side is wavy, so the shim is thinnest at a trough.
            thinnest = min(
                (piece.bounds[2 + across] - piece.bounds[across] for piece in pieces), default=0.0,
            ) - 2.0 * WAVE_AMPLITUDE
            if thinnest < MIN_SHIM:
                notes.append(f"{side.capitalize()} edge: {play:.1f} mm of play - too thin for a printed shim.")
                continue
            boxes = []
            for piece in pieces:
                x0, y0, x1, y1 = piece.bounds
                boxes.append({"x": x0, "y": y0, "w": x1 - x0, "d": y1 - y0, "side": side, "outline": piece})
            if any(_overlaps(one, zone) for one in boxes for zone in drawer["keepouts"]):
                notes.append(f"{side.capitalize()} edge shim skipped - a keep-out zone is in the way.")
                continue
            shims.extend(boxes)
    return {"drawer": drawer, "height": height, "cells": cells, "shims": shims, "notes": notes}


def _shim_outlines(drawer: dict[str, Any], grid: dict[str, Any], side: str, longest: int) -> list[Polygon]:
    """One side's edge-shim pieces, as outlines in drawer coordinates.

    Each piece is cut from a virtual 16 mm bin standing just outside the grid,
    so its grid-facing side is the real wave and nests with the bins exactly
    as a neighbouring bin would; the far side is trimmed flat to the drawer
    wall.  Pieces are whole units long, so their ends nest with each other.
    """
    wall = drawer["clearance"] / 2.0
    step = grid["step"]
    right, back = grid["cols"] * step, grid["rows"] * step   # grid edges, grid coordinates
    ox, oy = grid["ox"], grid["oy"]
    far_x = drawer["width"] - wall - ox
    far_y = drawer["depth"] - wall - oy
    run = int((back if side in ("left", "right") else right) // UNIT)
    count = math.ceil(run / longest) if run else 0
    outlines, start = [], 0
    for index in range(count):
        units = run // count + (1 if index < run % count else 0)
        middle = (start + units / 2.0) * UNIT
        length = units * UNIT
        if side == "right":
            spec, centre, keep = BoxSpec(2 * UNIT, length), (right + UNIT, middle), shape_box(0, -1e4, far_x, 1e4)
        elif side == "left":
            spec, centre, keep = BoxSpec(2 * UNIT, length), (-UNIT, middle), shape_box(wall - ox, -1e4, UNIT, 1e4)
        elif side == "back":
            spec, centre, keep = BoxSpec(length, 2 * UNIT), (middle, back + UNIT), shape_box(-1e4, 0, 1e4, far_y)
        else:
            spec, centre, keep = BoxSpec(length, 2 * UNIT), (middle, -UNIT), shape_box(-1e4, wall - oy, 1e4, UNIT)
        piece = placed_outline(spec, centre).intersection(keep)
        if piece.geom_type != "Polygon" and not piece.is_empty:
            piece = max(piece.geoms, key=lambda part: part.area)
        if not piece.is_empty and piece.area > 0.01:
            outlines.append(affinity.translate(piece, ox, oy))
        start += units
    return outlines


def _overlaps(a: dict[str, float], b: dict[str, float]) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["d"] and b["y"] < a["y"] + a["d"]


def spacer_filename(kind: str, x: float, y: float, z: float) -> str:
    return f"{'Spacer' if kind == 'spacer' else 'Shim'} {x:g} x {y:g} x {z:g}.3mf"


def _rib(a: tuple[float, float], b: tuple[float, float]) -> Polygon:
    """A straight brace from a to b, run 2 mm past each end so it buries
    itself in the wall it meets."""
    (ax, ay), (bx, by) = a, b
    length = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / length * 2.0, (by - ay) / length * 2.0
    return LineString([(ax - ux, ay - uy), (bx + ux, by + uy)]).buffer(RIB_WIDTH / 2.0, cap_style="flat")


def spacer_frame(x: float, y: float, z: float) -> trimesh.Trimesh:
    """A bespoke spacer for one empty patch of grid.

    The outside is exactly a bin's wavy wall, so it nests with the bins on
    every side and takes a connector like one (the lock bumps are kept).  The
    inside is open - no floor - and braced by one big X, or a row of X's when
    the patch is long and thin so no brace runs at a shallow angle.
    """
    spec = BoxSpec(x, y, z)
    envelope = _extrude_polygon(wavy_outer_polygon(spec), z)
    opening = _extrude_polygon(wavy_cavity_polygon(spec), z + 2.0)
    opening.apply_translation((0.0, 0.0, -1.0))
    solids = [difference([envelope, opening])]
    solids += [_extrude_polygon(brace, z) for brace in spacer_braces(spec)]
    solids += make_wall_lock_bumps(spec)
    return union(solids)


def spacer_braces(spec: BoxSpec) -> list[Polygon]:
    """The X braces inside a spacer frame, each strip clipped to the outside
    wall.

    Kept as separate strips and fused in 3D: flattened into one outline, the
    X's would enclose the openings as holes, and a many-holed outline does not
    extrude to a reliable solid.
    """
    outer = wavy_outer_polygon(spec)
    x0, y0, x1, y1 = wavy_cavity_polygon(spec).bounds
    span_x, span_y = x1 - x0, y1 - y0
    if min(span_x, span_y) < MIN_RIB_SPAN:
        return []
    count = max(1, round(max(span_x, span_y) / min(span_x, span_y)))
    braces: list[Polygon] = []
    for index in range(count):
        if span_x >= span_y:
            a, b = x0 + span_x * index / count, x0 + span_x * (index + 1) / count
            ends = [((a, y0), (b, y1)), ((a, y1), (b, y0))]
        else:
            a, b = y0 + span_y * index / count, y0 + span_y * (index + 1) / count
            ends = [((x0, a), (x1, b)), ((x1, a), (x0, b))]
        for start, end in ends:
            piece = _rib(start, end).intersection(outer)
            braces += list(getattr(piece, "geoms", [piece]))
    return [one for one in braces if one.geom_type == "Polygon" and one.area > 0.01]


def shim_mesh(outline: Polygon, z: float) -> trimesh.Trimesh:
    """An edge shim: its outline extruded, centred on the origin for printing."""
    x0, y0, x1, y1 = outline.bounds
    return _extrude_polygon(affinity.translate(outline, -(x0 + x1) / 2.0, -(y0 + y1) / 2.0), z)


def generate_spacers(
    output_dir: Path | str,
    layout: dict[str, Any],
    drawer_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plan, print-file and inventory the spacers for one drawer, place them,
    and save.  Unplaced copies of a matching spacer already in the inventory
    are used before any new file is made."""
    if not isinstance(layout, dict):
        raise ValueError("drawer layout must be an object")
    output_dir = Path(output_dir).expanduser().resolve()
    with INVENTORY_LOCK:
        inventory = load_inventory(output_dir)
        bins = inventory["bins"]
        raw = find_drawer(layout, drawer_id)
        plan = plan_spacers(raw, bins, options)
        drawer, height = plan["drawer"], plan["height"]
        step = drawer["snap"]
        if not plan["cells"] and not plan["shims"]:
            return {**inventory, "layout": layout, "generated": [], "reused": 0, "placed": 0,
                    "notes": plan["notes"] or ["Nothing left to fill."]}

        placed = {
            (p.get("bin"), int(p.get("copy", 0)))
            for one in layout.get("drawers") or [] if isinstance(one, dict)
            for p in one.get("placements") or [] if isinstance(p, dict)
        }
        groups: dict[tuple, list[dict]] = {}
        for cell in plan["cells"]:
            size = (cell["w"] * step, cell["d"] * step)
            bx, by = (size[1], size[0]) if drawer["bin_axis"] == "y" else size
            groups.setdefault(("spacer", bx, by, height), []).append(cell)
        # A left and a right shim of the same size are one part turned round:
        # the odd wave makes opposite walls the same shape.
        for shim in plan["shims"]:
            groups.setdefault(("shim", round(shim["w"], 2), round(shim["d"], 2), height), []).append(shim)

        rows = [dict(one) for one in bins]
        updates: dict[str, dict] = {}
        new_rows: list[dict] = []
        generated, reused = [], 0
        new_placements = []
        output_dir.mkdir(parents=True, exist_ok=True)
        for (kind, bx, by, bz), spots in groups.items():
            matches = [
                one for one in rows
                if one.get("kind") == kind and _close(one["x"], bx) and _close(one["y"], by) and _close(one["z"], bz)
            ]
            copies = [
                (one["id"], copy) for one in matches for copy in range(int(one["qty"]))
                if (one["id"], copy) not in placed
            ]
            reused += min(len(copies), len(spots))
            shortfall = len(spots) - len(copies)
            if shortfall > 0:
                name = spacer_filename(kind, bx, by, bz)
                mesh = spacer_frame(bx, by, bz) if kind == "spacer" else shim_mesh(spots[0]["outline"], bz)
                export_mesh(mesh, output_dir / name, "Spacer" if kind == "spacer" else "Shim")
                generated.append(name)
                if matches:
                    target = matches[0]
                    start = int(target["qty"])
                    target["qty"] = start + shortfall
                    updates[target["id"]] = {"id": target["id"], "qty": target["qty"]}
                else:
                    target = {
                        "id": next_bin_id(rows), "kind": kind, "qty": shortfall,
                        "name": "X spacer" if kind == "spacer" else "Edge shim",
                        "x": bx, "y": by, "z": bz, "file": name,
                        "interior": "Open X-braced spacer frame" if kind == "spacer" else "Edge shim, wavy on the bin side",
                    }
                    start = 0
                    rows.append(target)
                    new_rows.append(target)
                copies += [(target["id"], start + n) for n in range(shortfall)]
            for spot, (bin_id, copy) in zip(spots, copies):
                if kind == "spacer":
                    new_placements.append({
                        "bin": bin_id, "copy": copy, "locked": False,
                        "gx": _units(spot["gx"], drawer), "gy": _units(spot["gy"], drawer),
                    })
                else:
                    new_placements.append({
                        "bin": bin_id, "copy": copy, "side": spot["side"],
                        **{key: round(spot[key], 3) for key in ("x", "y", "w", "d")},
                    })
        raw.setdefault("placements", []).extend(new_placements)
        result = save_inventory(
            output_dir, layout=layout,
            bin_updates=list(updates.values()), new_bins=new_rows,
        )
    return {**result, "generated": generated, "reused": reused,
            "placed": len(new_placements), "notes": plan["notes"]}


# ---------------------------------------------------------------- connectors


def generate_connectors(
    output_dir: Path | str,
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None = None,
) -> dict[str, Any]:
    """Print files for every connector a drawer's layout needs: one file per
    pair of rim heights, with how many of it to print."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report = drawer_report(find_drawer(layout, drawer_id), bins)
    made, notes = [], []
    connector = ConnectorSpec()
    for group in report["connectors"]:
        high, low = group["heights"]
        wall = group["wall"]
        different = abs(high - low) > 1e-6
        name = connector_filename(
            connector, length=LOCKED_CONNECTOR_LENGTH, bin_a_height=high, bin_b_height=low,
            different_heights=different, wall=wall,
        )
        try:
            generate_side_file(
                BoxSpec(2 * UNIT, 6 * UNIT, high, wall=wall), connector, output_dir / name,
                "y", 0.0, LOCKED_CONNECTOR_LENGTH, high, low,
                web_thickness=DEFAULT_ARM_THICKNESS if different else None, auto_adjust=False,
            )
        except ValueError as error:
            notes.append(f"{high:g} → {low:g} mm: {error}")
            continue
        made.append({"file": name, "count": group["count"], "heights": [high, low]})
    if report["connector_mismatched"]:
        notes.append(
            f"{report['connector_mismatched']} seam(s) join a stackable bin (1.2 mm wall) to an "
            "ordinary one (0.8 mm) - no connector fits both."
        )
    return {"connectors": made, "notes": notes}


def print_spacers_and_connectors(
    output_dir: Path | str,
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None,
    detect_slicer: Callable,
    launch_slicer: Callable,
    slicer_path: str | None = None,
) -> dict[str, Any]:
    """Open one drawer's spacers, shims and connectors in the slicer together."""
    output_dir = Path(output_dir).expanduser().resolve()
    drawer = find_drawer(layout, drawer_id)
    by_id = {one["id"]: one for one in bins}
    counts: dict[str, int] = {}
    for placement in drawer.get("placements") or []:
        one = by_id.get(placement.get("bin"))
        if one and one.get("kind") in SPACER_KINDS and one.get("file"):
            counts[one["file"]] = counts.get(one["file"], 0) + 1
    connectors = generate_connectors(output_dir, layout, bins, drawer_id)
    for made in connectors["connectors"]:
        counts[made["file"]] = counts.get(made["file"], 0) + made["count"]
    files = [output_dir / name for name in counts if (output_dir / name).is_file()]
    if not files:
        raise ValueError("this drawer has no spacers or connectors to print yet")
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")
    launch_slicer(Path(slicer), files)
    return {"files": [str(path) for path in files], "counts": counts, "notes": connectors["notes"]}


# ---------------------------------------------------------------- web routes


def drawer_routes(
    geometry_lock,
    default_output: Path,
    detect_slicer: Callable | None = None,
    launch_slicer: Callable | None = None,
) -> dict[str, Callable[[dict], dict]]:
    """POST handlers for the browser service, keyed by path."""

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def with_rules(result: dict[str, Any]) -> dict[str, Any]:
        # The view needs the stacking steps for live stack heights while dragging.
        return {**result, "stack_steps": STACK_STEPS}

    def load(payload):
        return with_rules(load_inventory(folder(payload)))

    def save(payload):
        changes: dict[str, Any] = {
            "bin_updates": payload.get("bin_updates") or (),
            "new_bins": payload.get("new_bins") or (),
            "delete_ids": payload.get("delete_ids") or (),
        }
        if "layout" in payload and payload["layout"] is not None:
            changes["layout"] = payload["layout"]
        return with_rules(save_inventory(folder(payload), **changes))

    def report(payload):
        return drawer_report(
            find_drawer(payload["layout"], payload.get("drawer_id")),
            payload.get("bins") or [], payload.get("height_reach") or "column",
        )

    def auto(payload):
        return auto_layout(payload["layout"], payload.get("bins") or [], payload.get("drawer_id"), payload.get("options"))

    def spacers(payload):
        with geometry_lock:
            return with_rules(generate_spacers(folder(payload), payload["layout"], payload.get("drawer_id"), payload.get("options")))

    def connectors(payload):
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))

    def send_to_slicer(payload):
        if detect_slicer is None or launch_slicer is None:
            raise ValueError("printing is not available here")
        with geometry_lock:
            return print_spacers_and_connectors(
                folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"),
                detect_slicer, launch_slicer, payload.get("slicer_path"),
            )

    return {
        "/api/drawer/load": load,
        "/api/drawer/save": save,
        "/api/drawer/report": report,
        "/api/drawer/auto": auto,
        "/api/drawer/spacers": spacers,
        "/api/drawer/connectors": connectors,
        "/api/drawer/print": send_to_slicer,
    }
