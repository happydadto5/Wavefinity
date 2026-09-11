"""Drawer layout: fitting printed bins into a real drawer.

Pure 2D planning on the 8 mm grid, plus the one piece of geometry it owns - the
spacers that fill whatever the bins leave.  Drawer coordinates: x runs left to
right, y runs from the front (0) to the back, z is height.  The Layout view
draws the front at the bottom of the screen.

Bins never turn a quarter turn inside a drawer.  Left walls mate with right
walls and front with back; a bin turned 90 degrees meets its neighbours crest
to crest (every mixed pair collides when checked with the engine's own
outlines).  A drawer may instead run *every* bin's X front-to-back
(``bin_axis = "y"``), which turns the whole grid together and keeps each seam
matched.

A placement is either on the grid (``gx``/``gy`` in whole units from the grid's
front-left cell) or, for an edge shim, free (``x``/``y``/``w``/``d`` in mm from
the drawer's inside front-left corner).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import trimesh

from organizer_engine import (
    BASE_UNIT,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    BoxSpec,
    export_mesh,
    make_box,
)
from organizer_inventory import INVENTORY_LOCK, load_inventory, next_bin_id, save_inventory

UNIT = BASE_UNIT
# How far a bin's wave crests stand past its grid footprint on each side.
CREST = WAVE_AMPLITUDE - WAVE_MATING_GAP / 2.0
# Total slack per axis a drawer needs just to take the crests at both walls.
MIN_CLEARANCE = 2.0 * CREST
SHIM_BIN_GAP = CREST + 0.1      # flat shim face to the bins' footprint line
MIN_SHIM = 1.2                  # thinnest shim worth printing (three perimeters)
SHIM_SPLIT_GAP = 0.4            # between the pieces of a shim longer than the bed
MIN_SPACER_HEIGHT = 6.0         # a spacer bin still needs room for its lock bumps
MIN_CONNECTOR_SEAM = 2          # units: 16 mm, the shortest wall a connector seats on
HEIGHT_TOLERANCE = 0.5          # mm; "taller" means taller by more than this

DRAWER_DEFAULTS: dict[str, Any] = {
    "name": "Drawer", "width": 400.0, "depth": 300.0, "height": 60.0,
    "clearance": 1.0, "anchor": "front-left", "bin_axis": "x",
}
ANCHORS = ("front-left", "center")
HEIGHT_RULES = ("strict", "prefer", "ignore")
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
    """Where the 8 mm grid sits in the drawer and what it leaves at the edges.

    The clearance is total slack per axis: half of it sits at each wall so the
    wave crests of the outermost bins clear the drawer sides.
    """
    slack = drawer["clearance"]
    usable_x = drawer["width"] - slack
    usable_y = drawer["depth"] - slack
    cols = max(0, int(math.floor(usable_x / UNIT + 1e-6)))
    rows = max(0, int(math.floor(usable_y / UNIT + 1e-6)))
    spare_x = usable_x - cols * UNIT
    spare_y = usable_y - rows * UNIT
    ox = slack / 2.0 + (spare_x / 2.0 if drawer["anchor"] == "center" else 0.0)
    oy = slack / 2.0 + (spare_y / 2.0 if drawer["anchor"] == "center" else 0.0)
    return {
        "cols": cols, "rows": rows, "ox": ox, "oy": oy,
        "gap_left": ox,
        "gap_right": drawer["width"] - ox - cols * UNIT,
        "gap_front": oy,
        "gap_back": drawer["depth"] - oy - rows * UNIT,
    }


def bin_units(one: dict[str, Any], drawer: dict[str, Any]) -> tuple[int, int]:
    """A bin's footprint in grid units, as it stands in this drawer."""
    ux = max(1, math.ceil(float(one["x"]) / UNIT - 1e-6))
    uy = max(1, math.ceil(float(one["y"]) / UNIT - 1e-6))
    return (uy, ux) if drawer["bin_axis"] == "y" else (ux, uy)


def _blocked(drawer: dict[str, Any], grid: dict[str, Any]) -> np.ndarray:
    blocked = np.zeros((grid["rows"], grid["cols"]), dtype=bool)
    for zone in drawer["keepouts"]:
        x0 = (zone["x"] - grid["ox"]) / UNIT
        y0 = (zone["y"] - grid["oy"]) / UNIT
        x1 = x0 + zone["w"] / UNIT
        y1 = y0 + zone["d"] / UNIT
        c0, c1 = max(0, math.floor(x0 + 1e-6)), min(grid["cols"], math.ceil(x1 - 1e-6))
        r0, r1 = max(0, math.floor(y0 + 1e-6)), min(grid["rows"], math.ceil(y1 - 1e-6))
        if c1 > c0 and r1 > r0:
            blocked[r0:r1, c0:c1] = True
    return blocked


def _grid_items(drawer: dict[str, Any], by_id: dict[str, dict]) -> list[dict[str, Any]]:
    items = []
    for placement in drawer["placements"]:
        if "gx" not in placement:
            continue
        one = by_id.get(placement.get("bin"))
        if one is None:
            continue
        w, d = bin_units(one, drawer)
        items.append({
            "key": f"{placement['bin']}:{int(placement.get('copy', 0))}",
            "bin": placement["bin"], "copy": int(placement.get("copy", 0)),
            "gx": int(placement["gx"]), "gy": int(placement["gy"]),
            "w": w, "d": d, "h": float(one["z"]),
            "kind": one.get("kind", "bin"), "name": one.get("name", ""),
            "locked": bool(placement.get("locked", False)),
            "placement": placement,
        })
    return items


def _height_issues(items: list[dict[str, Any]]) -> list[tuple[dict, dict]]:
    """(front, behind) pairs where a taller bin stands in front of a shorter
    one it overlaps across the drawer - the short one is hidden and hard to
    reach."""
    issues = []
    for front in items:
        for back in items:
            if (front is not back
                    and front.get("kind") not in SPACER_KINDS
                    and back.get("kind") not in SPACER_KINDS
                    and back["gy"] >= front["gy"] + front["d"]
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


def _connectors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One connector per shared seam long enough to seat one, grouped by the
    two rim heights it joins (a mixed pair needs its own printed connector)."""
    counts: dict[tuple[float, float], int] = {}
    for index, a in enumerate(items):
        for b in items[index + 1:]:
            if a["gx"] + a["w"] == b["gx"] or b["gx"] + b["w"] == a["gx"]:
                overlap = min(a["gy"] + a["d"], b["gy"] + b["d"]) - max(a["gy"], b["gy"])
            elif a["gy"] + a["d"] == b["gy"] or b["gy"] + b["d"] == a["gy"]:
                overlap = min(a["gx"] + a["w"], b["gx"] + b["w"]) - max(a["gx"], b["gx"])
            else:
                continue
            if overlap >= MIN_CONNECTOR_SEAM:
                key = tuple(sorted((a["h"], b["h"]), reverse=True))
                counts[key] = counts.get(key, 0) + 1
    return [
        {"heights": list(key), "count": count}
        for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]


def drawer_report(raw_drawer: dict[str, Any], bins: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the Layout view says about one drawer: fill, what is left,
    what is wrong, and how many connectors the arrangement needs."""
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols = grid["rows"], grid["cols"]
    by_id = {one["id"]: one for one in bins}
    blocked = _blocked(drawer, grid)
    owner = np.full((rows, cols), -1, dtype=int)
    problems: list[dict[str, Any]] = []
    for placement in drawer["placements"]:
        one = by_id.get(placement.get("bin"))
        key = f"{placement.get('bin')}:{int(placement.get('copy', 0))}"
        if one is None:
            problems.append({"type": "missing", "keys": [key], "message": f"{placement.get('bin')} is no longer in the inventory"})
        elif int(placement.get("copy", 0)) >= int(one["qty"]):
            problems.append({"type": "missing", "keys": [key], "message": f"{_label(one)}: only {int(one['qty'])} printed"})
    items = _grid_items(drawer, by_id)
    for index, item in enumerate(items):
        label = _label(by_id[item["bin"]])
        if item["h"] > drawer["height"] + 1e-6:
            problems.append({"type": "too_tall", "keys": [item["key"]], "message": f"{label} is {item['h']:g} mm tall; the drawer is {drawer['height']:g} mm"})
        x0, y0 = item["gx"], item["gy"]
        x1, y1 = x0 + item["w"], y0 + item["d"]
        if x0 < 0 or y0 < 0 or x1 > cols or y1 > rows:
            problems.append({"type": "outside", "keys": [item["key"]], "message": f"{label} sticks out of the drawer"})
        cx0, cy0, cx1, cy1 = max(0, x0), max(0, y0), min(cols, x1), min(rows, y1)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        if blocked[cy0:cy1, cx0:cx1].any():
            problems.append({"type": "keepout", "keys": [item["key"]], "message": f"{label} sits on a keep-out zone"})
        region = owner[cy0:cy1, cx0:cx1]
        for other in sorted({int(v) for v in region[region >= 0]}):
            problems.append({"type": "overlap", "keys": [items[other]["key"], item["key"]], "message": f"{_label(by_id[items[other]['bin']])} and {label} overlap"})
        region[region < 0] = index
    issues = _height_issues(items)
    for front, back in issues:
        problems.append({
            "type": "height", "keys": [back["key"], front["key"]],
            "message": f"{_label(by_id[back['bin']])} ({back['h']:g} mm) is behind taller {_label(by_id[front['bin']])} ({front['h']:g} mm)",
        })
    used = int((owner >= 0).sum())
    blocked_cells = int(blocked.sum())
    usable = rows * cols - blocked_cells
    free = (owner < 0) & ~blocked
    area, lx, ly, lw, ld = _largest_empty(free) if rows and cols else (0, 0, 0, 0, 0)
    shim_area = sum(
        float(p.get("w", 0)) * float(p.get("d", 0))
        for p in drawer["placements"] if "gx" not in p and p.get("bin") in by_id
    )
    connectors = _connectors(items)
    return {
        "grid": grid,
        "cells": {"total": usable, "used": used, "free": int(free.sum()), "blocked": blocked_cells},
        "fill": round(100.0 * used / usable, 1) if usable else 0.0,
        "free_mm2": round(float(free.sum()) * UNIT * UNIT),
        "edge_mm2": round(max(0.0, drawer["width"] * drawer["depth"] - rows * cols * UNIT * UNIT - shim_area)),
        "largest": {"gx": lx, "gy": ly, "w": lw, "d": ld, "w_mm": lw * UNIT, "d_mm": ld * UNIT} if area else None,
        "connectors": connectors,
        "connector_total": sum(one["count"] for one in connectors),
        "problems": problems,
        "height_issues": len(issues),
        "placed": len(items),
        "shims": sum(1 for p in drawer["placements"] if "gx" not in p),
    }


def _label(one: dict[str, Any]) -> str:
    return one.get("name") or f"{float(one['x']):g} x {float(one['y']):g}"


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


def _pack(rows, cols, blocked, fixed, items, order, scorer, height_rule):
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
            front = np.maximum.accumulate(np.vstack([np.zeros((1, cols)), heights]), axis=0)
            behind_heights = np.where(has_bin, heights, np.inf)
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


def auto_layout(
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Several arrangements for one drawer, best first.

    Options: ``mode`` ``rearrange`` (move everything not locked) or ``fill``
    (only add bins around the current ones); ``height_rule`` ``strict`` (never a
    short bin behind a taller one), ``prefer`` or ``ignore``; ``keep_locked``;
    ``include_spacers``; ``only`` - a list of ``{bin, copy}`` to place, which
    is how the view drops one bin into the best free spot.
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
    keep_locked = bool(options.get("keep_locked", True))
    include_spacers = bool(options.get("include_spacers", False))
    only = {(str(one.get("bin")), int(one.get("copy", 0))) for one in options.get("only") or []}

    elsewhere = {
        (p.get("bin"), int(p.get("copy", 0)))
        for other in layout.get("drawers") or [] if isinstance(other, dict) and other is not raw
        for p in other.get("placements") or [] if isinstance(p, dict)
    }
    keep_placements, fixed = [], []
    dropped_spacers = 0
    grid_items = {item["key"]: item for item in _grid_items(drawer, by_id)}
    for placement in drawer["placements"]:
        key = f"{placement.get('bin')}:{int(placement.get('copy', 0))}"
        one = by_id.get(placement.get("bin"))
        if one is None:
            continue
        stays = (
            "gx" not in placement or mode == "fill" or bool(only)
            or (keep_locked and placement.get("locked"))
        )
        if stays:
            keep_placements.append(placement)
            if key in grid_items:
                fixed.append(grid_items[key])
        elif one.get("kind") == "spacer" and not include_spacers:
            dropped_spacers += 1
    kept = {(p.get("bin"), int(p.get("copy", 0))) for p in keep_placements}

    items, skipped = [], []
    for one in bins:
        if one.get("kind") == "shim" or int(one["qty"]) <= 0:
            continue
        if one.get("kind") == "spacer" and not include_spacers and not only:
            continue
        w, d = bin_units(one, drawer)
        for copy in range(int(one["qty"])):
            key = (one["id"], copy)
            if key in elsewhere or key in kept or (only and key not in only):
                continue
            item = {
                "key": f"{one['id']}:{copy}", "bin": one["id"], "copy": copy,
                "w": w, "d": d, "h": float(one["z"]), "name": one.get("name", ""),
                "kind": one.get("kind", "bin"),
            }
            if item["h"] > drawer["height"] + 1e-6:
                skipped.append({"bin": one["id"], "copy": copy, "reason": f"taller than the drawer ({item['h']:g} > {drawer['height']:g} mm)"})
            else:
                items.append(item)

    blocked = _blocked(drawer, grid)
    strategies = [s for s in STRATEGIES if s[0] == "tight"] if only else list(STRATEGIES)
    runs = [(s, height_rule) for s in strategies]
    candidates, seen = [], set()

    def run(strategy, rule, name=None, description=None):
        ident, title, blurb, order, scorer = strategy
        placed, unplaced = _pack(rows, cols, blocked, fixed, items, order, scorer, rule)
        signature = frozenset((p["bin"], p["copy"], p["gx"], p["gy"]) for p in placed)
        if signature in seen and placed:
            return None
        seen.add(signature)
        everything = fixed + placed
        used = sum(item["w"] * item["d"] for item in everything)
        usable = rows * cols - int(blocked.sum())
        candidate = {
            "id": ident if rule == height_rule else f"{ident}-{rule}",
            "name": name or title,
            "description": description or blurb,
            "placements": keep_placements + [
                {"bin": p["bin"], "copy": p["copy"], "gx": p["gx"], "gy": p["gy"], "locked": False}
                for p in placed
            ],
            "unplaced": [{"bin": u["bin"], "copy": u["copy"], "reason": u["reason"]} for u in unplaced],
            "stats": {
                "placed": len(placed),
                "wanted": len(items),
                "fill": round(100.0 * used / usable, 1) if usable else 0.0,
                "height_issues": len(_height_issues(everything)),
                "connectors": sum(one["count"] for one in _connectors(everything)),
            },
        }
        candidates.append(candidate)
        return candidate

    for strategy, rule in runs:
        run(strategy, rule)
    # When the height rule is what left bins out, offer the layout that bends it.
    if height_rule == "strict" and any(
        u["reason"].startswith("no spot keeps") for c in candidates for u in c["unplaced"]
    ):
        run(STRATEGIES[1], "prefer", "Fits more",
            "Bends the height rule where it has to, so more bins fit.")
    order = {id(c): index for index, c in enumerate(candidates)}
    candidates.sort(key=lambda c: (-c["stats"]["placed"], c["stats"]["height_issues"], order[id(c)]))
    notes = []
    if dropped_spacers:
        notes.append(f"{dropped_spacers} spacer bin{'s' if dropped_spacers != 1 else ''} taken out - make spacers again once the layout settles.")
    return {"candidates": candidates, "skipped": skipped, "notes": notes}


# ---------------------------------------------------------------- spacers


def plan_spacers(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
    """What it takes to fill a drawer: spacer bins for empty grid cells and
    flat shims for the strips between the grid and the drawer walls."""
    options = options or {}
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols = grid["rows"], grid["cols"]
    fill = options.get("fill", "all")
    if fill not in SPACER_FILLS:
        fill = "all"
    height = min(drawer["height"], max(MIN_SPACER_HEIGHT, float(options.get("height") or 20.0)))
    max_length = max(2 * UNIT, float(options.get("max_length") or 250.0))
    by_id = {one["id"]: one for one in bins}
    notes: list[str] = []

    cells = []
    if fill in ("all", "cells") and rows and cols:
        free = ~_blocked(drawer, grid)
        for item in _grid_items(drawer, by_id):
            free[max(0, item["gy"]):max(0, item["gy"] + item["d"]), max(0, item["gx"]):max(0, item["gx"] + item["w"])] = False
        longest = max(1, int(max_length // UNIT))
        while True:
            area, gx, gy, w, d = _largest_empty(free)
            if area <= 0:
                break
            w, d = min(w, longest), min(d, longest)
            free[gy:gy + d, gx:gx + w] = False
            cells.append({"gx": gx, "gy": gy, "w": w, "d": d})

    shims = []
    if fill in ("all", "edges"):
        wall = drawer["clearance"] / 2.0
        taken = {p.get("side") for p in drawer["placements"] if "gx" not in p and p.get("bin") in by_id}
        grid_x1 = grid["ox"] + cols * UNIT
        grid_y1 = grid["oy"] + rows * UNIT
        for side in SIDES:
            gap = grid[f"gap_{side}"]
            play = gap - wall
            if side in taken or play < 0.05:
                continue
            thickness = gap - SHIM_BIN_GAP - wall
            if thickness < MIN_SHIM:
                notes.append(f"{side.capitalize()} edge: {play:.1f} mm of play - too thin for a printed shim.")
                continue
            # Side shims run the full depth and own the corners; front and
            # back shims span only the grid between them.
            if side in ("left", "right"):
                start, length = wall, drawer["depth"] - 2.0 * wall
                fixed_at = wall if side == "left" else grid_x1 + SHIM_BIN_GAP
            else:
                start, length = grid["ox"], cols * UNIT
                fixed_at = wall if side == "front" else grid_y1 + SHIM_BIN_GAP
            pieces = max(1, math.ceil(length / max_length - 1e-9))
            piece = (length - (pieces - 1) * SHIM_SPLIT_GAP) / pieces
            for index in range(pieces):
                along = start + index * (piece + SHIM_SPLIT_GAP)
                if side in ("left", "right"):
                    box = {"x": fixed_at, "y": along, "w": thickness, "d": piece}
                else:
                    box = {"x": along, "y": fixed_at, "w": piece, "d": thickness}
                if any(_overlaps(box, zone) for zone in drawer["keepouts"]):
                    notes.append(f"{side.capitalize()} edge shim skipped - a keep-out zone is in the way.")
                    break
                shims.append({**box, "side": side, "thickness": round(thickness, 2), "length": round(piece, 1)})
    return {"drawer": drawer, "height": height, "cells": cells, "shims": shims, "notes": notes}


def _overlaps(a: dict[str, float], b: dict[str, float]) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["d"] and b["y"] < a["y"] + a["d"]


def spacer_filename(kind: str, x: float, y: float, z: float) -> str:
    return f"{'Spacer' if kind == 'spacer' else 'Shim'} {x:g} x {y:g} x {z:g}.3mf"


def _spacer_mesh(kind: str, x: float, y: float, z: float) -> trimesh.Trimesh:
    if kind == "spacer":
        # An ordinary open bin: it mates with its neighbours, takes connectors,
        # and holds things later if the drawer is rearranged.
        return make_box(BoxSpec(x, y, z))
    mesh = trimesh.creation.box(extents=(x, y, z))
    mesh.apply_translation((0.0, 0.0, z / 2.0))
    return mesh


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.05


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
        if not plan["cells"] and not plan["shims"]:
            return {**inventory, "layout": layout, "generated": [], "reused": 0,
                    "notes": plan["notes"] or ["Nothing left to fill."]}

        placed = {
            (p.get("bin"), int(p.get("copy", 0)))
            for one in layout.get("drawers") or [] if isinstance(one, dict)
            for p in one.get("placements") or [] if isinstance(p, dict)
        }
        groups: dict[tuple, list[dict]] = {}
        for cell in plan["cells"]:
            size = (cell["w"] * UNIT, cell["d"] * UNIT)
            bx, by = (size[1], size[0]) if drawer["bin_axis"] == "y" else size
            groups.setdefault(("spacer", bx, by, height), []).append(cell)
        for shim in plan["shims"]:
            groups.setdefault(("shim", shim["thickness"], shim["length"], height), []).append(shim)

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
                path = output_dir / name
                if not path.is_file():
                    export_mesh(_spacer_mesh(kind, bx, by, bz), path, "Spacer" if kind == "spacer" else "Shim")
                    generated.append(name)
                if matches:
                    target = matches[0]
                    start = int(target["qty"])
                    target["qty"] = start + shortfall
                    updates[target["id"]] = {"id": target["id"], "qty": target["qty"]}
                else:
                    target = {
                        "id": next_bin_id(rows), "kind": kind, "qty": shortfall,
                        "name": "Spacer" if kind == "spacer" else "Edge shim",
                        "x": bx, "y": by, "z": bz, "file": name,
                        "interior": "Spacer bin" if kind == "spacer" else "Edge shim",
                    }
                    start = 0
                    rows.append(target)
                    new_rows.append(target)
                copies += [(target["id"], start + n) for n in range(shortfall)]
            for spot, (bin_id, copy) in zip(spots, copies):
                if kind == "spacer":
                    new_placements.append({"bin": bin_id, "copy": copy, "gx": spot["gx"], "gy": spot["gy"], "locked": False})
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


# ---------------------------------------------------------------- web routes


def drawer_routes(geometry_lock, default_output: Path) -> dict[str, Callable[[dict], dict]]:
    """POST handlers for the browser service, keyed by path."""

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def load(payload):
        return load_inventory(folder(payload))

    def save(payload):
        changes: dict[str, Any] = {
            "bin_updates": payload.get("bin_updates") or (),
            "new_bins": payload.get("new_bins") or (),
            "delete_ids": payload.get("delete_ids") or (),
        }
        if "layout" in payload and payload["layout"] is not None:
            changes["layout"] = payload["layout"]
        return save_inventory(folder(payload), **changes)

    def report(payload):
        return drawer_report(find_drawer(payload["layout"], payload.get("drawer_id")), payload.get("bins") or [])

    def auto(payload):
        return auto_layout(payload["layout"], payload.get("bins") or [], payload.get("drawer_id"), payload.get("options"))

    def spacers(payload):
        with geometry_lock:
            return generate_spacers(folder(payload), payload["layout"], payload.get("drawer_id"), payload.get("options"))

    return {
        "/api/drawer/load": load,
        "/api/drawer/save": save,
        "/api/drawer/report": report,
        "/api/drawer/auto": auto,
        "/api/drawer/spacers": spacers,
    }
