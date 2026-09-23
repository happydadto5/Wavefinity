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
* Stacked: ``on`` names the placement directly below (``"B3:0"``).  Only a
  stackable bin of the same footprint and the same stacking style can snap
  onto another; each one adds its requested module height.  The exposed top
  interlock remains part of the stack's physical drawer-height envelope.
* Free, for an edge-facing spacer: ``x``/``y``/``w``/``d`` in mm from the
  drawer's inside front-left corner, plus the ``side`` it lines.  Its width
  across the wall is the drawer's real leftover play, not rounded to a grid
  unit - a physically genuine residual, not a whole-8-mm footprint.

A copy numbered past its row's printed Qty is *planned*: placed before it is
printed, so a drawer can be designed first and printed to.

Legacy inventories used a separate ``kind: "shim"`` for the edge-facing
piece; ``organizer_inventory._normalise`` migrates it to ``spacer`` with
``boundary: "edge"`` the moment a file is read, so nothing below this line
ever sees the old kind.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Callable

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry import box as shape_box
from shapely.ops import unary_union
import trimesh

from organizer_app import connector_filename, design_source_payload, design_to_dict, generate_side_file, object_height_plan
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
    INVENTORY_LOCK,
    MAX_QTY,
    design_specs,
    legacy_layout_space,
    load_inventory,
    load_inventory_text,
    next_bin_id,
    save_design_source as _save_design_source_row,
    save_design_source_text as _save_design_source_row_text,
    save_inventory,
    save_inventory_text,
    update_bin_file,
)
from organizer_inserts import Layout
from organizer_b4b import B4B_STACK_RECESS_DEPTH
from organizer_product_rules import DRAWER_HARD_CLEARANCE_MM, SURFACE_TRIM_HEIGHTS
from organizer_stack import STACK_MIN_WALL, STACK_PLUG_DEPTH, STACK_SEAT_DEPTH
from organizer_pegboard import pegboard_layout_for_bin, pegboard_standard

UNIT = BASE_UNIT
SNAPS = (8.0, 4.0)
# How far a bin's wave crests stand past its grid footprint on each side.
CREST = WAVE_AMPLITUDE - WAVE_MATING_GAP / 2.0
# Total slack per axis a drawer needs just to take the crests at both walls.
MIN_CLEARANCE = DRAWER_HARD_CLEARANCE_MM
MIN_EDGE_SPACER = 1.2           # thinnest edge spacer worth printing, at a wave trough
MIN_SPACER_HEIGHT = 6.0         # a spacer frame still needs room for its lock bumps
DEFAULT_SPACER_HEIGHT = 15.0
SPACER_CONTACT_TARGET = 28.0    # target contact width of a back/right spacer, mm
RIB_WIDTH = 1.6                 # the X brace inside a spacer: four 0.4 mm lines
MIN_RIB_SPAN = 10.0             # narrower than this inside, a frame needs no brace
MIN_CONNECTOR_SEAM = 16.0       # mm of shared wall a connector needs
HEIGHT_TOLERANCE = 0.5          # mm; "taller" means taller by more than this
# How far a stacked bin's foot sinks into the one below, by stacking style.
STACK_STEPS = {
    "lid": STACK_SEAT_DEPTH,
    "direct": STACK_PLUG_DEPTH,
    "b4b": B4B_STACK_RECESS_DEPTH,
}

DRAWER_DEFAULTS: dict[str, Any] = {
    "name": "Drawer", "width": 400.0, "depth": 300.0, "height": 60.0,
    "clearance": 1.0, "anchor": "front-left", "bin_axis": "x", "snap": 8.0,
    "boundary": "wall",
}
ANCHORS = ("front-left", "center")
# A drawer's four sides are a real hard wall (the normal case, needing slack
# for the outermost bins' wave crests) or a B4B/Box's own Wavefinity-mating
# boundary, which is already the correct interlocking surface and needs no
# extra hard-wall slack added on top of it.
BOUNDARIES = ("wall", "mating", "pegboard")
HEIGHT_RULES = ("strict", "prefer", "ignore")
HEIGHT_REACHES = ("column", "adjacent")
SIDES = ("left", "right", "front", "back")
# Low filler nobody reaches for: spacers take room but are never counted for
# or against the height rule.  A 1-tuple because inventories are migrated to
# the unified "spacer" kind the moment they load (organizer_inventory); kept
# as a tuple, not a bare comparison, since every call site already reads
# ``in SPACER_KINDS``.
SPACER_KINDS = ("spacer",)


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
    if drawer.get("boundary") not in BOUNDARIES:
        drawer["boundary"] = "wall"
    requested_clearance = float(drawer.get("clearance") or 0.0)
    # A hard drawer wall always gets the slack the outermost bins' wave
    # crests need. A B4B/Box's own mating boundary is already the correct
    # interlocking surface - flooring its clearance the same way would
    # silently eat a real 8 mm row or column from its exact interior.
    drawer["clearance"] = (
        requested_clearance if drawer["boundary"] in ("mating", "pegboard") else max(MIN_CLEARANCE, requested_clearance)
    )
    if drawer["anchor"] not in ANCHORS:
        drawer["anchor"] = "front-left"
    if drawer["bin_axis"] not in ("x", "y"):
        drawer["bin_axis"] = "x"
    drawer["snap"] = 4.0 if float(drawer.get("snap") or 8.0) == 4.0 else 8.0
    drawer.pop("keepouts", None)  # the old Keep-out Zone feature is gone
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
    if drawer.get("boundary") == "pegboard":
        standard = pegboard_standard(drawer.get("pegboard_standard"))
        cols = max(1, int(drawer.get("pegboard_holes_x") or math.floor(drawer["width"] / standard.pitch_x_mm)))
        rows = max(1, int(drawer.get("pegboard_holes_y") or math.floor(drawer["depth"] / standard.pitch_y_mm)))
        residual_x = max(0.0, float(drawer.get("pegboard_residual_x") or drawer["width"] - cols * standard.pitch_x_mm))
        residual_y = max(0.0, float(drawer.get("pegboard_residual_y") or drawer["depth"] - rows * standard.pitch_y_mm))
        return {
            "step": standard.pitch_x_mm,
            "step_x": standard.pitch_x_mm,
            "step_y": standard.pitch_y_mm,
            "cols": cols,
            "rows": rows,
            "ox": residual_x / 2.0,
            "oy": residual_y / 2.0,
            "gap_left": residual_x / 2.0,
            "gap_right": residual_x / 2.0,
            "gap_front": residual_y / 2.0,
            "gap_back": residual_y / 2.0,
            "standard": standard.id,
            "opening_shape": standard.opening_shape,
            "opening_width_mm": standard.opening_width_mm,
            "opening_height_mm": standard.opening_height_mm,
            "stagger_x_mm": standard.stagger_x_mm,
        }
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
    if drawer.get("boundary") == "pegboard":
        standard = pegboard_standard(drawer.get("pegboard_standard"))
        return (
            max(1, math.ceil(float(one["x"]) / standard.pitch_x_mm - 1e-6)),
            max(1, math.ceil(float(one["z"]) / standard.pitch_y_mm - 1e-6)),
        )
    step = drawer["snap"]
    cx = max(1, math.ceil(float(one["x"]) / step - 1e-6))
    cy = max(1, math.ceil(float(one["y"]) / step - 1e-6))
    return (cy, cx) if drawer["bin_axis"] == "y" else (cx, cy)


def stack_pitch(one: dict[str, Any]) -> float:
    """What a bin adds between consecutive stack seating datums."""
    if one.get("stack") == "b4b":
        return float(one["z"]) - B4B_STACK_RECESS_DEPTH
    return float(one["z"])


def stack_part_height(one: dict[str, Any]) -> float:
    """Detached physical height, including the interlocking foot depth."""
    if one.get("stack") == "b4b":
        return float(one["z"])
    return float(one["z"]) + STACK_STEPS.get(one.get("stack", "none"), 0.0)


def is_surface_layout(layout: dict[str, Any] | None) -> bool:
    space = layout.get("space") if isinstance(layout, dict) else None
    return isinstance(space, dict) and space.get("kind") == "surface"


def surface_planning_heights(layout: dict[str, Any] | None, bins: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not is_surface_layout(layout):
        return {}
    specs = design_specs(layout)
    plans = {}
    for one in bins:
        height = one.get("object_height_mm")
        plan = object_height_plan(specs.get(one["id"]), height)
        physical = stack_part_height(one)
        plans[one["id"]] = {**plan, "physical_mm": physical,
                            "effective_mm": max(physical, plan["object_top_mm"] or 0.0)}
    return plans


def _key(placement: dict[str, Any]) -> str:
    return f"{placement.get('bin')}:{int(placement.get('copy', 0))}"


def _label(one: dict[str, Any]) -> str:
    return one.get("name") or f"{float(one['x']):g} x {float(one['y']):g}"


def _close(a: float, b: float) -> bool:
    return abs(float(a) - float(b)) < 0.05


def _overlaps(a: dict[str, float], b: dict[str, float]) -> bool:
    return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["d"] and b["y"] < a["y"] + a["d"]


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


def _stack_item(chain: list[dict], drawer: dict[str, Any], by_id: dict[str, dict],
                plans: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    """One grid footprint: a single bin, or a stack of them."""
    base = chain[0]
    first = by_id[base["bin"]]
    w, d = bin_cells(first, drawer)
    layers, issues, top, plan_top = [], [], 0.0, 0.0
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
        layer_plan_top = bottom + ((plans or {}).get(one["id"], {}).get("effective_mm", stack_part_height(one)))
        plan_top = max(plan_top, layer_plan_top)
        layers.append({
            "key": _key(placement), "bin": placement["bin"], "copy": int(placement.get("copy", 0)),
            "z0": bottom, "z1": top, "plan_z1": layer_plan_top,
            "planned": int(placement.get("copy", 0)) >= int(one["qty"]),
        })
    return {
        "key": _key(base), "keys": [layer["key"] for layer in layers],
        "bin": base["bin"], "copy": int(base.get("copy", 0)),
        "gx": _cell(base["gx"], drawer), "gy": _cell(base["gy"], drawer),
        "w": w, "d": d, "h": top, "plan_h": plan_top,
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
                    and front.get("plan_h", front["h"]) > back.get("plan_h", back["h"]) + HEIGHT_TOLERANCE):
                issues.append((front, back))
    return issues


def _two_largest_empty(free: np.ndarray, min_cells: int = 1) -> list[tuple[int, int, int, int]]:
    """Up to two distinct, non-overlapping maximal empty rectangles that could
    actually take a normal bin - real bin-placement openings, largest first.

    The rectangle search itself is constrained to ``min_cells`` wide and
    tall (see ``_largest_empty``), so a genuinely large but too-narrow
    region - too small for even the smallest normal bin, which is always at
    least one Wavefinity unit - is never even a candidate. It is not found
    and then discarded: doing that first could zero out cells a real, valid,
    smaller opening elsewhere also needed before ever considering it. The
    second opening is the largest valid rectangle in whatever the first did
    not cover, so the pair can never overlap or be near-duplicates.
    """
    rects: list[tuple[int, int, int, int]] = []
    remaining = free.copy()
    for _ in range(2):
        area, gx, gy, w, d = _largest_empty(remaining, min_cells)
        if area <= 0:
            break
        rects.append((gx, gy, w, d))
        remaining[gy:gy + d, gx:gx + w] = False
    return rects


def _largest_empty(free: np.ndarray, min_cells: int = 1) -> tuple[int, int, int, int, int]:
    """(area, gx, gy, w, d) of the largest all-True rectangle at least
    ``min_cells`` wide AND tall - not simply the largest rectangle of any
    shape. A candidate narrower than that in either direction is never
    considered a candidate at all, so it can never be chosen over (or,
    if removed first, accidentally destroy) a smaller valid rectangle.
    """
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
                width = col - left
                if tall >= min_cells and width >= min_cells:
                    area = tall * width
                    if area > best[0]:
                        best = (area, left, row - tall + 1, width, tall)
                start = left
            stack.append((start, height))
    return best


def surface_fill_plan(inventory: dict[str, Any]) -> dict[str, Any]:
    """Partition the authoritative Surface's free 8 mm cells into legal bins."""
    layout = inventory.get("layout")
    if not is_surface_layout(layout):
        raise ValueError("Fill Empty Space is available only in Surface Space")
    drawer = normalise_drawer(find_drawer(layout))
    grid = drawer_grid(drawer)
    if grid["step"] != UNIT:
        raise ValueError("Surface Fill needs the 8 mm Surface grid")
    bins = inventory["bins"]
    by_id = {one["id"]: one for one in bins}
    footprint = sorted((one["id"], one["x"], one["y"]) for one in bins
                       if any(p.get("bin") == one["id"] for p in drawer["placements"]))
    signature_input = {
        "space": layout["space"], "drawer_id": drawer.get("id"),
        "grid": [grid["cols"], grid["rows"], grid["step"]],
        "placements": drawer["placements"], "footprints": footprint,
    }
    signature = hashlib.sha256(json.dumps(
        signature_input, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    free = np.ones((grid["rows"], grid["cols"]), dtype=bool)
    for placement in drawer["placements"]:
        if "gx" not in placement or placement.get("bin") not in by_id:
            continue
        gx, gy = _cell(placement["gx"], drawer), _cell(placement["gy"], drawer)
        w, d = bin_cells(by_id[placement["bin"]], drawer)
        free[max(0, gy):min(grid["rows"], gy + d),
             max(0, gx):min(grid["cols"], gx + w)] = False
    candidates = []
    max_cells = int(MAX_BOX_SIZE // UNIT)
    while free.any():
        area, gx, gy, w, d = _largest_empty(free)
        if not area:
            break
        w, d = min(w, max_cells), min(d, max_cells)
        candidates.append({"id": f"fill-{gx}-{gy}-{w}-{d}",
                           "gx": gx, "gy": gy, "w": w, "d": d,
                           "x_mm": w * UNIT, "y_mm": d * UNIT})
        free[gy:gy + d, gx:gx + w] = False
    candidates.sort(key=lambda c: (-(c["w"] * c["d"]), c["gy"], c["gx"], c["id"]))
    return {"signature": signature, "candidates": candidates}


def _connector_eligible(item: dict[str, Any]) -> bool:
    """Whether this footprint's seam can take a side connector at all.

    A Storage Box case has no bare wave wall to clip onto, and a stackable bin's
    mouth is meant for the bin above, not a side clip - so neither should
    ever get one, no matter how long the shared seam runs."""
    if item["kind"] == "b4b":
        return False
    if item["top"].get("stack", "none") != "none":
        return False
    if item["kind"] in SPACER_KINDS:
        return False
    return True


def _top_wall(item: dict[str, Any]) -> float:
    """The wall a connector meets at the top of this footprint.

    Reads the actual wall the printed bin has when the inventory row
    recorded it; only a legacy row with no Wall column falls back to the
    old stacking-vs-ordinary guess."""
    wall = item["top"].get("wall")
    if isinstance(wall, (int, float)) and wall > 0:
        return float(wall)
    return STACK_MIN_WALL if item["top"].get("stack", "none") != "none" else DEFAULT_WALL


def _connectors(items: list[dict[str, Any]], step: float) -> tuple[list[dict[str, Any]], int]:
    """One connector per shared seam long enough to seat one, grouped by the
    two rim heights and wall thickness it joins.  Stacks join at their top
    bins.  Returns the groups and how many seams join incompatible bins -
    different wall thicknesses, or a seam too short for the reinforced
    connector a height difference requires - which no printed connector
    fits."""
    counts: dict[tuple[float, float, float], int] = {}
    mismatched = 0
    need = math.ceil(MIN_CONNECTOR_SEAM / step - 1e-9)
    for index, a in enumerate(items):
        for b in items[index + 1:]:
            if not _connector_eligible(a) or not _connector_eligible(b):
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
            plan = differing_connector_plan(
                ConnectorSpec(), LOCKED_CONNECTOR_LENGTH, a["h"], b["h"],
                BoxSpec(2 * UNIT, 6 * UNIT, max(a["h"], b["h"]), wall=wall_a),
            )
            if overlap * step + 1e-9 < max(MIN_CONNECTOR_SEAM, plan["length_mm"]):
                continue
            key = (*sorted((round(a["h"], 2), round(b["h"], 2)), reverse=True), wall_a)
            counts[key] = counts.get(key, 0) + 1
    groups = [
        {"heights": [key[0], key[1]], "wall": key[2], "count": count}
        for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return groups, mismatched


def _pegboard_report(drawer: dict[str, Any], bins: list[dict[str, Any]]) -> dict[str, Any]:
    """Front-view occupancy for a Pegboard Space.

    Footprints and exact used board openings are independent checks. A layout
    is invalid if either one overlaps or leaves the board.
    """
    grid = drawer_grid(drawer)
    by_id = {one["id"]: one for one in bins}
    problems: list[dict[str, Any]] = []
    rectangles: list[dict[str, Any]] = []
    occupied_mounts: dict[tuple[float, int], str] = {}
    mounts: list[dict[str, Any]] = []
    used_cells: set[tuple[int, int]] = set()
    planned: dict[str, int] = {}

    for placement in drawer["placements"]:
        key = _key(placement)
        one = by_id.get(placement.get("bin"))
        if one is None:
            problems.append({"type": "missing", "keys": [key], "message": f"{placement.get('bin')} is no longer in the inventory"})
            continue
        if placement.get("on") is not None:
            problems.append({"type": "mount", "keys": [key], "message": "Pegboard bins cannot be stacked"})
            continue
        try:
            layout = pegboard_layout_for_bin(one, grid["standard"])
        except (TypeError, ValueError, KeyError) as error:
            problems.append({"type": "mount", "keys": [key], "message": str(error)})
            continue
        if not layout["compatible"]:
            problems.append({
                "type": "mount", "keys": [key],
                "message": (
                    f"{_label(one)} has no pegboard receiver"
                    if not one.get("pegboard_standard") else
                    f"{_label(one)} was generated for {one.get('pegboard_standard')}"
                ),
            })
        try:
            raw_gx, raw_gy = float(placement["gx"]), float(placement["gy"])
        except (KeyError, TypeError, ValueError):
            problems.append({"type": "outside", "keys": [key], "message": f"{_label(one)} is not snapped to a board opening"})
            continue
        if not math.isclose(raw_gx, round(raw_gx), abs_tol=1e-9) or not math.isclose(raw_gy, round(raw_gy), abs_tol=1e-9):
            problems.append({"type": "outside", "keys": [key], "message": f"{_label(one)} is not snapped to a board opening"})
            continue
        gx, gy = int(round(raw_gx)), int(round(raw_gy))
        if grid["standard"] == "skadis" and gy % 2:
            problems.append({
                "type": "mount", "keys": [key],
                "message": f"{_label(one)} must start on an aligned SKÅDIS slot row",
            })
            continue
        w, d = int(layout["cells_x"]), int(layout["cells_y"])
        rect = {"key": key, "x": gx, "y": gy, "w": w, "d": d, "one": one}
        if gx < 0 or gy < 0 or gx + w > grid["cols"] or gy + d > grid["rows"]:
            problems.append({"type": "outside", "keys": [key], "message": f"{_label(one)} sticks out of the pegboard"})
        for other in rectangles:
            if _overlaps(rect, other):
                problems.append({
                    "type": "overlap", "keys": [other["key"], key],
                    "message": f"{_label(other['one'])} and {_label(one)} overlap",
                })
        rectangles.append(rect)
        for row in range(max(0, gy), min(grid["rows"], gy + d)):
            for col in range(max(0, gx), min(grid["cols"], gx + w)):
                used_cells.add((col, row))
        for ox, oy in layout["mount_offsets"]:
            mount = (gx + float(ox), gy + int(oy))
            if not (0 <= mount[0] < grid["cols"] - 0.5 + 1e-9 and 0 <= mount[1] < grid["rows"]):
                problems.append({"type": "mount", "keys": [key], "message": f"{_label(one)} cannot reach enough valid board openings there"})
                continue
            other_key = occupied_mounts.get(mount)
            if other_key is not None:
                problems.append({"type": "mount_overlap", "keys": [other_key, key], "message": "Two adapters use the same pegboard opening"})
            occupied_mounts[mount] = key
            mounts.append({"gx": mount[0], "gy": mount[1], "key": key})
        if int(placement.get("copy", 0)) >= int(one.get("qty", 0)):
            planned[one["id"]] = planned.get(one["id"], 0) + 1

    total = grid["cols"] * grid["rows"]
    return {
        "grid": grid,
        "cells": {"total": total, "used": len(used_cells), "free": max(0, total - len(used_cells))},
        "fill": round(100.0 * len(used_cells) / total, 1) if total else 0.0,
        "free_mm2": round(max(0.0, drawer["width"] * drawer["depth"] - len(used_cells) * grid["step_x"] * grid["step_y"])),
        "edge_mm2": 0,
        "opens": [],
        "connectors": [],
        "connector_total": 0,
        "wall_mismatches": 0,
        "problems": problems,
        "planned": [{"id": key, "count": count} for key, count in planned.items()],
        "mounts": mounts,
        "pegboard": True,
    }


def drawer_report(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], reach: str = "column",
                  layout: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything the Layout view says about one drawer: fill, what is left,
    what is wrong, what is still to print, and the connectors it needs."""
    drawer = normalise_drawer(raw_drawer)
    if drawer.get("boundary") == "pegboard":
        return _pegboard_report(drawer, bins)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    by_id = {one["id"]: one for one in bins}
    plans = surface_planning_heights(layout, bins)
    owner = np.full((rows, cols), -1, dtype=int)
    problems: list[dict[str, Any]] = []
    for placement in drawer["placements"]:
        if placement.get("bin") not in by_id:
            problems.append({"type": "missing", "keys": [_key(placement)], "message": f"{placement.get('bin')} is no longer in the inventory"})
    chains, loose = _chains(drawer, by_id)
    for placement in loose:
        problems.append({"type": "floating", "keys": [_key(placement)], "message": f"{_label(by_id[placement['bin']])} is stacked on nothing"})
    items = [_stack_item(chain, drawer, by_id, plans) for chain in chains]
    per_unit = _per_unit(drawer)
    for index, item in enumerate(items):
        label = _label(by_id[item["bin"]])
        if len(item["layers"]) > 1:
            label = f"The stack of {len(item['layers'])} on {label}"
        for issue in item["issues"]:
            problems.append({"type": "stack", "keys": item["keys"], "message": issue})
        if not is_surface_layout(layout) and item["h"] > drawer["height"] + 1e-6:
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
        region = owner[cy0:cy1, cx0:cx1]
        for other in sorted({int(v) for v in region[region >= 0]}):
            problems.append({"type": "overlap", "keys": items[other]["keys"] + item["keys"], "message": f"{_label(by_id[items[other]['bin']])} and {_label(by_id[item['bin']])} overlap"})
        region[region < 0] = index
    # Edge-facing spacers were cut for the drawer as it was; resizing it,
    # moving the grid, changing the snap, or a since-placed bin can
    # leave one stuck outside the drawer or colliding with something real.
    # Checked against the actual occupied cells (not the whole grid
    # rectangle) - a back/right spacer legitimately reaches from a
    # component's own edge to the real wall, and empty grid along the way is
    # not a conflict.
    for placement in drawer["placements"]:
        if "gx" in placement or "on" in placement or placement.get("bin") not in by_id:
            continue
        edge = {key: float(placement.get(key, 0.0)) for key in ("x", "y", "w", "d")}
        outside = (edge["x"] < -0.1 or edge["y"] < -0.1
                   or edge["x"] + edge["w"] > drawer["width"] + 0.1 or edge["y"] + edge["d"] > drawer["depth"] + 0.1)
        collides = False
        if not outside:
            ex0 = max(0, math.floor((edge["x"] - grid["ox"]) / step + 1e-6))
            ey0 = max(0, math.floor((edge["y"] - grid["oy"]) / step + 1e-6))
            ex1 = min(cols, math.ceil((edge["x"] + edge["w"] - grid["ox"]) / step - 1e-6))
            ey1 = min(rows, math.ceil((edge["y"] + edge["d"] - grid["oy"]) / step - 1e-6))
            if ex1 > ex0 and ey1 > ey0:
                collides = bool((owner[ey0:ey1, ex0:ex1] >= 0).any())
        if outside or collides:
            problems.append({"type": "edge_spacer", "keys": [_key(placement)], "message": "An edge spacer no longer fits this drawer - take the spacers out and make them again"})
    issues = _height_issues(items, reach)
    for front, back in issues:
        problems.append({
            "type": "height", "keys": back["keys"],
            "message": f"{_label(by_id[back['bin']])} ({back['plan_h']:g} mm planning height) is behind taller {_label(by_id[front['bin']])} ({front['plan_h']:g} mm planning height)" if plans else f"{_label(by_id[back['bin']])} ({back['h']:g} mm) is behind taller {_label(by_id[front['bin']])} ({front['h']:g} mm)",
        })
    used = int((owner >= 0).sum())
    usable = rows * cols
    free = owner < 0
    opens = _two_largest_empty(free, _per_unit(drawer)) if rows and cols else []
    edge_area = sum(
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
        "cells": {"total": usable, "used": used, "free": int(free.sum())},
        "fill": round(100.0 * used / usable, 1) if usable else 0.0,
        "free_mm2": round(float(free.sum()) * step * step),
        "edge_mm2": round(max(0.0, drawer["width"] * drawer["depth"] - rows * cols * step * step - edge_area)),
        # Up to the two largest genuine bin-placement openings, largest
        # first - real usable rectangles, not a statistic. mm is authoritative;
        # the browser divides by 8 for the user-facing Wavefinity-unit line.
        "opens": [
            {"gx": gx, "gy": gy, "w": w, "d": d, "w_mm": w * step, "d_mm": d * step}
            for gx, gy, w, d in opens
        ],
        "connectors": connectors,
        "connector_total": sum(one["count"] for one in connectors),
        "connector_mismatched": mismatched,
        "problems": problems,
        "height_issues": len(issues),
        "placed": sum(len(item["layers"]) for item in items),
        "stacks": sum(1 for item in items if len(item["layers"]) > 1),
        "planned": planned,
        "planning_heights": plans,
        "edge_spacers": sum(1 for p in drawer["placements"] if "gx" not in p and "on" not in p),
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
    return (-item.get("plan_h", item["h"]), -item["w"] * item["d"], -item["w"], item["name"], item["bin"], item["copy"])


def _by_height_then_depth(item):
    return (-item.get("plan_h", item["h"]), -item["d"], -item["w"], item["name"], item["bin"], item["copy"])


def _by_area(item):
    return (-item["w"] * item["d"], -item.get("plan_h", item["h"]), item["name"], item["bin"], item["copy"])


STRATEGIES: tuple[tuple[str, str, str, Callable, Callable], ...] = (
    ("rows", "Tidy rows", "Tallest at the back, filled in rows from the left.", _by_height, _score_rows),
    ("tight", "Tight fit", "Tallest at the back; each bin goes where it touches the most neighbours.", _by_height, _score_tight),
    ("columns", "Columns", "Tallest at the back, filled in columns from the left.", _by_height_then_depth, _score_columns),
    ("most", "Most bins", "Biggest bins first, packed for the fullest drawer.", _by_area, _score_tight),
)

# Non-conclusive: a greedy/backtracked miss, not a proof the drawer is full.
AUTO_NO_SPOT = "Auto layout did not find a spot"
AUTO_NO_HEIGHT_SPOT = "Auto layout did not find a height-safe spot"


def _placement_options(
    rows, cols, occupied, heights, has_bin, item, scorer, height_rule, reach="column",
) -> list[tuple[int, int, float]]:
    """Every legal (row, col) an item may occupy against the given occupancy
    state, best-first: higher score, then lower row, then lower column."""
    w, d, h = item["w"], item["d"], item.get("plan_h", item["h"])
    if w > cols or d > rows:
        return []
    ny, nx = rows - d + 1, cols - w + 1
    free = _window(_sat(occupied), 0, 0, d, w, ny, nx) == 0
    if not free.any():
        return []
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
        return []
    rows_idx, cols_idx = np.where(allowed)
    scores = score[rows_idx, cols_idx]
    order = sorted(range(len(rows_idx)), key=lambda i: (-scores[i], rows_idx[i], cols_idx[i]))
    return [(int(rows_idx[i]), int(cols_idx[i]), float(scores[i])) for i in order]


def _pack(rows, cols, fixed, items, order, scorer, height_rule, reach="column"):
    occupied = np.zeros((rows, cols), dtype=bool)
    heights = np.zeros((rows, cols))
    has_bin = np.zeros((rows, cols), dtype=bool)

    def mark(item):
        x0, y0 = max(0, item["gx"]), max(0, item["gy"])
        x1, y1 = min(cols, item["gx"] + item["w"]), min(rows, item["gy"] + item["d"])
        if x1 > x0 and y1 > y0:
            occupied[y0:y1, x0:x1] = True
            if item.get("kind") not in SPACER_KINDS:
                has_bin[y0:y1, x0:x1] = True
                heights[y0:y1, x0:x1] = item.get("plan_h", item["h"])

    for item in fixed:
        mark(item)
    placed, unplaced = [], []
    for item in sorted(items, key=order):
        w, d = item["w"], item["d"]
        if w > cols or d > rows:
            unplaced.append({**item, "reason": "bigger than the drawer"})
            continue
        options = _placement_options(rows, cols, occupied, heights, has_bin, item, scorer, height_rule, reach)
        if not options:
            has_room = bool(_placement_options(rows, cols, occupied, heights, has_bin, item, scorer, "ignore", reach))
            unplaced.append({**item, "reason": AUTO_NO_HEIGHT_SPOT if has_room else AUTO_NO_SPOT})
            continue
        row, col, _ = options[0]
        placed_item = {**item, "gx": col, "gy": row}
        mark(placed_item)
        placed.append(placed_item)
    return placed, unplaced


# ------------------------------------------------------------- rescue search

AUTO_RESCUE_NODE_BUDGET = 20_000  # search-node cap, not a wall-clock timeout


def _rescue_item_order(rows, cols, fixed, items, scorer, height_rule, reach):
    """Movable items sorted hardest-to-place first, judged against the fixed
    placements only (no other movable item yet placed)."""
    occupied = np.zeros((rows, cols), dtype=bool)
    heights = np.zeros((rows, cols))
    has_bin = np.zeros((rows, cols), dtype=bool)

    def mark(item):
        x0, y0 = max(0, item["gx"]), max(0, item["gy"])
        x1, y1 = min(cols, item["gx"] + item["w"]), min(rows, item["gy"] + item["d"])
        if x1 > x0 and y1 > y0:
            occupied[y0:y1, x0:x1] = True
            if item.get("kind") not in SPACER_KINDS:
                has_bin[y0:y1, x0:x1] = True
                heights[y0:y1, x0:x1] = item.get("plan_h", item["h"])

    for item in fixed:
        mark(item)

    scored = [
        (len(_placement_options(rows, cols, occupied, heights, has_bin, item, scorer, height_rule, reach)), item)
        for item in items
    ]
    scored.sort(key=lambda pair: (
        pair[0],
        -(pair[1]["w"] * pair[1]["d"]),
        -pair[1].get("plan_h", pair[1]["h"]),
        -max(pair[1]["w"], pair[1]["d"]),
        pair[1]["name"], pair[1]["bin"], pair[1]["copy"],
    ))
    return [item for _, item in scored]


def _rescue_pack(rows, cols, fixed, items, height_rule, reach, budget=AUTO_RESCUE_NODE_BUDGET):
    """Deterministic bounded backtracking search for one complete legal
    arrangement of every item in ``items``.  Returns ``(placed, status,
    nodes)`` where ``status`` is ``"found"``, ``"budget"`` or ``"exhausted"``."""
    order = _rescue_item_order(rows, cols, fixed, items, _score_tight, height_rule, reach)
    occupied = np.zeros((rows, cols), dtype=bool)
    heights = np.zeros((rows, cols))
    has_bin = np.zeros((rows, cols), dtype=bool)

    def mark(item, on):
        x0, y0 = max(0, item["gx"]), max(0, item["gy"])
        x1, y1 = min(cols, item["gx"] + item["w"]), min(rows, item["gy"] + item["d"])
        if x1 > x0 and y1 > y0:
            occupied[y0:y1, x0:x1] = on
            if item.get("kind") not in SPACER_KINDS:
                has_bin[y0:y1, x0:x1] = on
                heights[y0:y1, x0:x1] = item.get("plan_h", item["h"]) if on else 0.0

    for item in fixed:
        mark(item, True)

    placements: list[dict] = []
    nodes = 0

    def recurse(index):
        nonlocal nodes
        if index == len(order):
            return True
        item = order[index]
        options = _placement_options(rows, cols, occupied, heights, has_bin, item, _score_tight, height_rule, reach)
        for row, col, _ in options:
            if nodes >= budget:
                return False
            nodes += 1
            placed_item = {**item, "gx": col, "gy": row}
            mark(placed_item, True)
            placements.append(placed_item)
            if recurse(index + 1):
                return True
            placements.pop()
            mark(placed_item, False)
        return False

    if recurse(0):
        return placements, "found", nodes
    if nodes >= budget:
        return None, "budget", nodes
    return None, "exhausted", nodes


def _build_stacks(singles: list[dict[str, Any]], max_height: float) -> list[dict[str, Any]]:
    """Snap stackable bins of one footprint and one stacking style into
    stacks, tallest at the bottom, as high as the drawer allows."""
    groups: dict[tuple, list[dict]] = {}
    items = []
    for single in singles:
        one = single["row"]
        if one.get("stack", "none") in STACK_STEPS and one.get("kind") not in SPACER_KINDS:
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
    bottom, plan_top = 0.0, 0.0
    for index, member in enumerate(members):
        if index:
            bottom += stack_pitch(members[index - 1]["row"])
        plan_top = max(plan_top, bottom + member.get("plan_h", member["h"]))
    return {**base, "h": height, "plan_h": plan_top,
            "members": [(m["bin"], m["copy"]) for m in members]}


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
    if drawer.get("boundary") == "pegboard":
        raise ValueError("Auto layout is not available for Pegboard Space; place bins on the visible openings.")
    grid = drawer_grid(drawer)
    rows, cols = grid["rows"], grid["cols"]
    by_id = {one["id"]: one for one in bins}
    surface = is_surface_layout(layout)
    plans = surface_planning_heights(layout, bins)
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
            keep_placements.append(placement)          # edge-facing spacers stay where they are
    for chain in chains:
        base = chain[0]
        if mode == "fill" or only or (keep_locked and base.get("locked")):
            keep_placements += chain
            fixed.append(_stack_item(chain, drawer, by_id, plans))
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
        # An edge-facing spacer has a free placement the grid packer below
        # cannot produce, so it is never a candidate here - it keeps the spot
        # plan_spacers cut it for, regardless of include_spacers.
        if one.get("kind") == "spacer" and one.get("boundary") == "edge":
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
            "w": w, "d": d, "h": stack_part_height(one),
            "plan_h": plans.get(bin_id, {}).get("effective_mm", stack_part_height(one)),
            "name": one.get("name", ""),
            "kind": one.get("kind", "bin"),
        }
        if not surface and single["h"] > drawer["height"] + 1e-6:
            skipped.append({"bin": bin_id, "copy": copy, "reason": f"taller than the drawer ({single['h']:g} > {drawer['height']:g} mm)"})
        else:
            singles.append(single)
    items = _build_stacks(singles, math.inf if surface else drawer["height"]) if stack_bins else singles

    strategies = [s for s in STRATEGIES if s[0] == "tight"] if only else list(STRATEGIES)
    candidates, seen = [], set()
    usable = rows * cols
    notes = []

    def placements_for(item):
        members = item.get("members") or [(item["bin"], item["copy"])]
        out = [{"bin": members[0][0], "copy": members[0][1],
                "gx": _units(item["gx"], drawer), "gy": _units(item["gy"], drawer), "locked": False}]
        for (below_bin, below_copy), (bin_id, copy) in zip(members, members[1:]):
            out.append({"bin": bin_id, "copy": copy, "on": f"{below_bin}:{below_copy}"})
        return out

    def make_candidate(ident, name, description, placed, unplaced_entries):
        everything = fixed + [{**p, "top": by_id[(p.get("members") or [(p["bin"],)])[-1][0]]} for p in placed]
        used = sum(item["w"] * item["d"] for item in everything)
        count = lambda group: sum(len(item.get("members") or [0]) for item in group)
        return {
            "id": ident,
            "name": name,
            "description": description,
            "placements": keep_placements + [p for item in placed for p in placements_for(item)],
            "unplaced": unplaced_entries,
            "stats": {
                "placed": count(placed),
                "wanted": count(items),
                "stacks": sum(1 for item in placed if item.get("members")),
                "fill": round(100.0 * used / usable, 1) if usable else 0.0,
                "height_issues": len(_height_issues(everything, reach)),
                "connectors": sum(one["count"] for one in _connectors(everything, grid["step"])[0]),
            },
        }

    def run(strategy, rule, name=None, description=None):
        ident, title, blurb, order, scorer = strategy
        placed, unplaced = _pack(rows, cols, fixed, items, order, scorer, rule, reach)
        signature = frozenset((p["bin"], p["copy"], p["gx"], p["gy"]) for p in placed)
        if signature in seen and placed:
            return
        seen.add(signature)
        unplaced_entries = [
            {"bin": bin_id, "copy": copy, "reason": u["reason"]}
            for u in unplaced for bin_id, copy in (u.get("members") or [(u["bin"], u["copy"])])
        ]
        candidates.append(make_candidate(
            ident if rule == height_rule else f"{ident}-{rule}",
            name or title, description or blurb, placed, unplaced_entries,
        ))

    for strategy in strategies:
        run(strategy, height_rule)

    # A deeper bounded search for a complete fit, when the fast layouts left
    # bins out and there is more than one movable bin to place around.
    if not only and not any(c["stats"]["placed"] == c["stats"]["wanted"] for c in candidates):
        rescued, status, _nodes = _rescue_pack(rows, cols, fixed, items, height_rule, reach, AUTO_RESCUE_NODE_BUDGET)
        if status == "found":
            candidates.append(make_candidate(
                "rescue", "Complete fit",
                "A deeper bounded search found a complete arrangement after the fast layouts did not.",
                rescued, [],
            ))
        elif status == "budget":
            notes.append("Auto layout reached its search limit. A complete fit may still exist; try moving or locking a bin and run Auto layout again.")
        else:
            notes.append("No complete fit was found under the current placement rules.")

    # When the height rule is what left bins out, offer the layout that bends it.
    if height_rule == "strict" and any(
        u["reason"] == AUTO_NO_HEIGHT_SPOT for c in candidates for u in c["unplaced"]
    ):
        run(STRATEGIES[1], "prefer", "Fits more", "Bends the height rule where it has to, so more bins fit.")
    order = {id(c): index for index, c in enumerate(candidates)}
    candidates.sort(key=lambda c: (-c["stats"]["placed"], c["stats"]["height_issues"], order[id(c)]))
    if dropped_spacers:
        notes.append(f"{dropped_spacers} spacer{'s' if dropped_spacers != 1 else ''} taken out - make spacers again once the layout settles.")
    return {"candidates": candidates, "skipped": skipped, "notes": notes}


# ---------------------------------------------------------------- spacers


def _exposed_segments(comp: list[dict[str, Any]], side: str) -> list[tuple[int, int, int]]:
    """Contiguous exposed boundary segments for one side of a connected
    component, in grid cells: ``(edge, start, end)`` - the component's own
    outer edge coordinate (x for "right", y for "back") and the
    perpendicular ``[start, end)`` cell range it spans.

    A row/column is only ever grouped with its neighbour when both share the
    exact same edge, so a candidate can never bridge across a step in an
    L-shaped or notched component - each genuinely separate run of the
    boundary becomes its own segment.
    """
    span: dict[int, int] = {}
    if side == "right":
        for item in comp:
            edge = item["gx"] + item["w"]
            for row in range(item["gy"], item["gy"] + item["d"]):
                span[row] = max(span.get(row, edge), edge)
    else:
        for item in comp:
            edge = item["gy"] + item["d"]
            for col in range(item["gx"], item["gx"] + item["w"]):
                span[col] = max(span.get(col, edge), edge)
    if not span:
        return []
    ordered = sorted(span)
    segments: list[tuple[int, int, int]] = []
    start = prev = ordered[0]
    edge = span[ordered[0]]
    for pos in ordered[1:]:
        if pos == prev + 1 and span[pos] == edge:
            prev = pos
            continue
        segments.append((edge, start, prev + 1))
        start = prev = pos
        edge = span[pos]
    segments.append((edge, start, prev + 1))
    return segments


def plan_spacers(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    flexible = options.get("flexible", True)
    height = min(drawer["height"], max(MIN_SPACER_HEIGHT, float(options.get("height") or DEFAULT_SPACER_HEIGHT)))
    by_id = {one["id"]: one for one in bins}
    notes: list[str] = []

    candidates = []
    selected = []

    if rows and cols:
        wall = drawer["clearance"] / 2.0
        
        items = [i for i in _grid_items(drawer, by_id) if i["kind"] not in SPACER_KINDS]
        
        adj = {i: set() for i in range(len(items))}
        for i, a in enumerate(items):
            for j, b in enumerate(items[i+1:], i+1):
                if max(a["gx"], b["gx"]) < min(a["gx"]+a["w"], b["gx"]+b["w"]) and (a["gy"]+a["d"] == b["gy"] or b["gy"]+b["d"] == a["gy"]):
                    adj[i].add(j)
                    adj[j].add(i)
                elif max(a["gy"], b["gy"]) < min(a["gy"]+a["d"], b["gy"]+b["d"]) and (a["gx"]+a["w"] == b["gx"] or b["gx"]+b["w"] == a["gx"]):
                    adj[i].add(j)
                    adj[j].add(i)
        
        seen = set()
        components = []
        for i in range(len(items)):
            if i not in seen:
                comp = []
                queue = [i]
                seen.add(i)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)
                components.append([items[idx] for idx in comp])
                
        for comp_idx, comp in enumerate(components):
            comp_area = sum(i["w"] * i["d"] for i in comp)

            def _make_candidate(side, edge, start, end):
                # A short, deterministic, strategically placed contact
                # piece - not the whole exposed run - per Fix 004: target
                # ~28 mm of contact width, clipped to the segment itself
                # when it is shorter, centred within it.
                seg_lo = (grid["oy"] if side == "right" else grid["ox"]) + start * step
                seg_hi = (grid["oy"] if side == "right" else grid["ox"]) + end * step
                seg_len = seg_hi - seg_lo
                contact = min(seg_len, SPACER_CONTACT_TARGET)
                contact_start = seg_lo + (seg_len - contact) / 2.0
                if side == "right":
                    gap = (drawer["width"] - grid["ox"] - (edge * step)) - wall
                    if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                        return None
                    px, py, w, d = grid["ox"] + edge * step, contact_start, gap, contact
                    cid = f"right-{edge}-{start}-{end}"
                else:
                    gap = (drawer["depth"] - grid["oy"] - (edge * step)) - wall
                    if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                        return None
                    px, py, w, d = contact_start, grid["oy"] + edge * step, contact, gap
                    cid = f"back-{edge}-{start}-{end}"
                placement = {"bin": "spacer", "x": px, "y": py, "w": w, "d": d, "side": side}
                area = w * d
                score = comp_area / area if area > 0 else 0
                return {"id": cid, "placements": [placement], "score": score, "axis": "x" if side == "right" else "y", "comp": comp_idx}

            for side in ("right", "back"):
                for edge, start, end in _exposed_segments(comp, side):
                    candidate = _make_candidate(side, edge, start, end)
                    if candidate is not None:
                        candidates.append(candidate)

        # Reject a candidate that overlaps another bin/component along its
        # own physical path to the wall (never bridge through something real
        # to reach it).
        item_boxes = [
            {"x": grid["ox"] + i["gx"] * step, "y": grid["oy"] + i["gy"] * step, "w": i["w"] * step, "d": i["d"] * step}
            for i in items
        ]
        valid_cands = []
        for cand in candidates:
            p = cand["placements"][0]
            edge = {"x": p["x"], "y": p["y"], "w": p["w"], "d": p["d"]}
            if any(_overlaps(edge, box) for box in item_boxes):
                continue
            valid_cands.append(cand)
        candidates = valid_cands
        
        candidates.sort(key=lambda c: c["score"], reverse=True)
        restrained_x = set()
        restrained_y = set()
        for cand in candidates:
            c_id = cand["comp"]
            if cand["axis"] == "x":
                if c_id not in restrained_x:
                    selected.append({"id": cand["id"]})
                    restrained_x.add(c_id)
            else:
                if c_id not in restrained_y:
                    selected.append({"id": cand["id"]})
                    restrained_y.add(c_id)
            if len(restrained_x) == len(components) and len(restrained_y) == len(components) and len(selected) >= 2:
                break
            if len(selected) >= 4:
                break
                
        for cand in candidates:
            cand.pop("score", None)
            cand.pop("axis", None)
            cand.pop("comp", None)

    return {"drawer": drawer, "height": height, "candidates": candidates, "selected": selected, "notes": notes}

def _serpentine_flexure(w, d, side, flexible=True):
    web = 1.5
    pad_bin = 3.0
    pad_wall = 2.0
    
    if side == "right":
        if flexible: w += 0.5
        if not flexible or w < pad_bin + pad_wall + web * 3:
            return shape_box(0, 0, w - (0.5 if flexible else 0), d)
        
        profile = wavy_rect_outer(10.0, d / 2.0)
        profile = affinity.translate(profile, -profile.bounds[0], d / 2.0)
        left_pad = profile.intersection(shape_box(0, 0, pad_bin, d))
        right_pad = shape_box(w - pad_wall, 0, w, d)
        
        mid_y = d / 2.0
        top_web = shape_box(pad_bin, d - web, w - pad_wall, d)
        bot_web = shape_box(pad_bin, 0, w - pad_wall, web)
        mid_web = shape_box(pad_bin, mid_y - web/2, w - pad_wall, mid_y + web/2)
        vert1 = shape_box(pad_bin, web, pad_bin + web, mid_y)
        vert2 = shape_box(w - pad_wall - web, mid_y, w - pad_wall, d - web)
        return unary_union([left_pad, right_pad, top_web, bot_web, mid_web, vert1, vert2])
    else:
        if flexible: d += 0.5
        if not flexible or d < pad_bin + pad_wall + web * 3:
            return shape_box(0, 0, w, d - (0.5 if flexible else 0))
            
        profile = wavy_rect_outer(w / 2.0, 10.0)
        profile = affinity.translate(profile, w / 2.0, -profile.bounds[1])
        bot_pad = profile.intersection(shape_box(0, 0, w, pad_bin))
        top_pad = shape_box(0, d - pad_wall, w, d)
        
        mid_x = w / 2.0
        left_web = shape_box(0, pad_bin, web, d - pad_wall)
        right_web = shape_box(w - web, pad_bin, w, d - pad_wall)
        mid_web = shape_box(mid_x - web/2, pad_bin, mid_x + web/2, d - pad_wall)
        horiz1 = shape_box(web, pad_bin, mid_x, pad_bin + web)
        horiz2 = shape_box(mid_x, d - pad_wall - web, w - web, d - pad_wall)
        return unary_union([bot_pad, top_pad, left_web, right_web, mid_web, horiz1, horiz2])

def spacer_filename(side: str, w: float, d: float, height: float, flexible: bool) -> str:
    """Deterministic from the real, unsnapped geometry - two decimals so
    distinct gaps (12.1 vs 12.9 mm) never collide, and Flexible/Rigid never
    share a name merely because their envelope came out the same size."""
    variant = "Flex" if flexible else "Rigid"
    return f"Spacer {variant} {side.capitalize()} {w:.2f}x{d:.2f}x{height:.2f}.3mf"


def generate_spacers(request: dict[str, Any], output_dir: Path | str, generate_file: Callable[[str, trimesh.Trimesh], Path]) -> dict[str, Any]:
    options = request.get("options") or {}
    plan = plan_spacers(request.get("drawer") or {}, request.get("bins") or [], options)
    requested_ids = set(request.get("selected") or [])
    height = plan["height"]
    drawer = plan["drawer"]
    flexible = bool(options.get("flexible", True))

    generated = []
    notes = []

    for cand in plan["candidates"]:
        cid = cand["id"]
        if cid in requested_ids:
            p = cand["placements"][0]
            side = p["side"]
            # placement envelope/gap: where the measured gap lies in the
            # drawer - the free placement x/y/w/d keeps describing this.
            gap_w = p["w"]
            gap_d = p["d"]

            poly = _serpentine_flexure(gap_w, gap_d, side, flexible)
            # printed physical part size: the actual generated mesh target,
            # including the flexible preload when a real flexure was built -
            # never the same thing as the measured gap above.
            minx, miny, maxx, maxy = poly.bounds
            part_w, part_d = maxx - minx, maxy - miny
            rigid_fallback = flexible and math.isclose(part_w, gap_w, abs_tol=1e-6) and math.isclose(part_d, gap_d, abs_tol=1e-6)
            if rigid_fallback:
                notes.append(f"Gap too short for flexure; generated rigid spacer for {side}.")

            mesh = _extrude_polygon(poly, height)
            is_flexible = flexible and not rigid_fallback
            file_name = spacer_filename(side, part_w, part_d, height, is_flexible)
            out_path = generate_file(file_name, mesh)

            generated.append({
                "id": cid,
                "file": file_name,
                "placements": cand["placements"],
                # actual printed part size - what inventory x/y/z records.
                "w": part_w, "d": part_d, "h": height, "side": side,
                "flexible": is_flexible,
            })

    return {"generated": generated, "notes": notes}


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
        plan = differing_connector_plan(
            connector, LOCKED_CONNECTOR_LENGTH, high, low,
            BoxSpec(2 * UNIT, 6 * UNIT, high, wall=wall),
        )
        length = plan["length_mm"]
        name = connector_filename(
            connector, length=length, bin_a_height=high, bin_b_height=low,
            different_heights=different, wall=wall,
        )
        try:
            generate_side_file(
                BoxSpec(2 * UNIT, 6 * UNIT, high, wall=wall), connector, output_dir / name,
                "y", 0.0, length, high, low,
                web_thickness=plan["web_thickness_mm"] if different else None, auto_adjust=False,
            )
        except ValueError as error:
            notes.append(f"{high:g} → {low:g} mm: {error}")
            continue
        made.append({"file": name, "count": group["count"], "heights": [high, low]})
    if report["connector_mismatched"]:
        notes.append(
            f"{report['connector_mismatched']} seam(s) join bins with different wall "
            "thicknesses; no single connector fits both."
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
    """Open one drawer's spacers and connectors in the slicer together."""
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
    # Each file is repeated once per physical copy so the slicer project holds
    # the real number of parts.
    launch_files = [path for path in files for _ in range(max(1, counts[path.name]))]
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")
    launch_slicer(Path(slicer), launch_files)
    return {"files": [str(path) for path in files], "counts": counts, "notes": connectors["notes"]}


# ---------------------------------------------------------------- bulk bin print


def _safe_row_file(root: Path, name: str) -> Path | None:
    """The real .3mf directly inside ``root`` called ``name``, else None."""
    if (not name or name != name.strip() or Path(name).name != name
            or Path(name).is_absolute() or "/" in name or "\\" in name
            or not name.lower().endswith(".3mf")):
        return None
    path = (root / name).resolve()
    return path if path.parent == root and path.is_file() else None


def inventory_row_files(output_dir: Path | str, row: dict[str, Any]) -> list[Path]:
    """The generated .3mf files an inventory row records, safely resolved.

    The File cell is user-editable text joined with ", ", but a generated file
    name may itself contain ", ". So the cell is resolved against the real
    files in the Space folder: the whole cell if it is one file, otherwise the
    one way of cutting it at ", " where every piece is a real .3mf file.
    """
    root = Path(output_dir).expanduser().resolve()
    label = f"{_label(row)} ({row.get('id')})"
    text = str(row.get("file") or "").strip()
    if not text:
        raise ValueError(f"{label} has no generated file to print")
    whole = _safe_row_file(root, text)
    if whole is not None:
        return [whole]

    pieces = text.split(", ")
    partitions: list[list[Path]] = []

    def walk(start: int, chosen: list[Path]) -> None:
        if len(partitions) > 1:
            return
        if start == len(pieces):
            partitions.append(list(chosen))
            return
        for end in range(start + 1, len(pieces) + 1):
            found = _safe_row_file(root, ", ".join(pieces[start:end]))
            if found is not None:
                walk(end, chosen + [found])

    walk(0, [])
    unique = {tuple(str(path) for path in part) for part in partitions}
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


def reconcile_printed_copies(
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    selection: dict[str, int],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Turn planned copies into printed ones for a batch that was just sent.

    Returns a copied layout whose promoted placements take copy numbers
    ``old_qty ...`` (stack ``on`` references follow the renames) and the exact
    new Qty for every selected row. Nothing is saved here.
    """
    layout = copy.deepcopy(layout) if layout else None
    by_id = {one["id"]: one for one in bins}
    rename: dict[str, str] = {}
    updates: list[dict[str, Any]] = []
    drawers = (layout or {}).get("drawers") or []
    for bin_id, count in selection.items():
        old_qty = int(by_id[bin_id].get("qty") or 0)
        planned = [
            placement
            for drawer in drawers
            for placement in drawer.get("placements") or []
            if placement.get("bin") == bin_id and int(placement.get("copy", 0)) >= old_qty
        ]
        planned.sort(key=lambda placement: int(placement.get("copy", 0)))
        for offset, placement in enumerate(planned[:count]):
            old_key, new_copy = _key(placement), old_qty + offset
            placement["copy"] = new_copy
            rename[old_key] = f"{bin_id}:{new_copy}"
        updates.append({"id": bin_id, "qty": old_qty + count})
    for drawer in drawers:
        for placement in drawer.get("placements") or []:
            if placement.get("on") in rename:
                placement["on"] = rename[placement["on"]]
    return layout, updates


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
) -> dict[str, Any]:
    """Send selected generated bins (and optional Space connectors) to the slicer.

    Qty and planned copies change only after the slicer launch succeeds. A
    selected row with no generated file but a canonical ``design_specs``
    entry (Fix 034 F2) is generated on demand via ``generate_from_design``
    first, and its resolved File cell is persisted immediately - still at
    Qty 0 - so a later print does not regenerate it.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    by_id = {one["id"]: one for one in bins}
    specs = design_specs(layout)
    counts: dict[str, int] = {}
    rows_files: dict[str, list[Path]] = {}
    for bin_id, raw_count in (selection or {}).items():
        one = by_id.get(str(bin_id))
        if one is None:
            raise ValueError(f"no bin {bin_id!r} in the inventory")
        count = _copy_count(one, raw_count)
        if one.get("kind") not in ("bin", "b4b"):
            raise ValueError(f"{_label(one)} is not a generated bin and cannot be printed here")
        if int(one.get("qty") or 0) + count > MAX_QTY:
            raise ValueError(f"{_label(one)}: Qty printed cannot go above {MAX_QTY}")
        if not str(one.get("file") or "").strip():
            spec = specs.get(one["id"])
            if spec is None or generate_from_design is None:
                raise ValueError(f"{_label(one)} has no generated file to print")
            generated = generate_from_design(output_dir, spec)
            if not generated:
                raise ValueError(f"{_label(one)}: generating its files did not produce any")
            file_text = ", ".join(dict.fromkeys(path.name for path in generated))
            update_bin_file(output_dir, one["id"], file_text)
            one["file"] = file_text
            rows_files[one["id"]] = list(generated)
        else:
            rows_files[one["id"]] = inventory_row_files(output_dir, one)
        counts[one["id"]] = count
    if not counts:
        raise ValueError("Select at least one bin to print.")

    connector_counts: dict[str, int] = {}
    notes: list[str] = []
    if include_connectors:
        for drawer in (layout or {}).get("drawers") or []:
            made = generate_connectors(output_dir, layout, bins, drawer.get("id"))
            for item in made["connectors"]:
                connector_counts[item["file"]] = connector_counts.get(item["file"], 0) + int(item["count"])
            for note in made["notes"]:
                if note not in notes:
                    notes.append(note)

    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")

    launch_files: list[Path] = []
    for bin_id, count in counts.items():
        for _copy in range(count):
            launch_files.extend(rows_files[bin_id])
    for name, count in connector_counts.items():
        launch_files.extend([output_dir / name] * count)

    reconciled, updates = reconcile_printed_copies(layout, bins, counts)

    project = launch_slicer(Path(slicer), launch_files)

    try:
        changes: dict[str, Any] = {"bin_updates": updates}
        if reconciled is not None:
            changes["layout"] = reconciled
        saved = save_inventory(output_dir, **changes)
    except Exception as error:
        raise RuntimeError(
            f"Bambu Studio opened, but saving the printed counts failed: {error}. "
            "Nothing was marked printed - fix Qty by hand if you print."
        ) from error
    return {
        **saved,
        "selection": counts,
        "bin_copies": sum(counts.values()),
        "connector_counts": connector_counts,
        "connector_copies": sum(connector_counts.values()),
        "notes": notes,
        "project": str(project) if project else None,
    }


# ---------------------------------------------------------------- web routes


def drawer_routes(
    geometry_lock,
    default_output: Path,
    detect_slicer: Callable | None = None,
    launch_slicer: Callable | None = None,
    hosted: bool = False,
    generate_from_design: Callable[[Path, dict[str, Any]], list[Path]] | None = None,
) -> dict[str, Callable[[dict], dict]]:
    """POST handlers for the browser service, keyed by path."""

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def with_rules(result: dict[str, Any]) -> dict[str, Any]:
        # The view needs the stacking steps for live stack heights while dragging.
        return {**result, "stack_steps": STACK_STEPS}

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
            "delete_ids": payload.get("delete_ids") or (),
        }
        if "layout" in payload and payload["layout"] is not None:
            changes["layout"] = payload["layout"]
        if hosted:
            return with_rules(save_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                **changes,
            ))
        return with_rules(save_inventory(folder(payload), **changes))

    def save_design_source(payload):
        """Save-to-Space: canonicalize the design, then create/update its
        editable source row + ``design_specs`` entry in one authoritative
        write. ``row_id`` targets an existing same-Space Qty-0 source row to
        update in place; a Qty>0 row (immutable printed history) or a missing
        row_id instead creates a fresh Qty-0 row."""
        design, record = design_source_payload(payload["design"])
        row_id = str(payload.get("row_id") or "") or None
        if hosted:
            result = _save_design_source_row_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                design=design, record=record, row_id=row_id,
            )
        else:
            result = _save_design_source_row(folder(payload), design=design, record=record, row_id=row_id)
        return with_rules(result)

    def report(payload):
        return drawer_report(
            find_drawer(payload["layout"], payload.get("drawer_id")),
            payload.get("bins") or [], payload.get("height_reach") or "column",
            payload["layout"],
        )

    def auto(payload):
        return auto_layout(payload["layout"], payload.get("bins") or [], payload.get("drawer_id"), payload.get("options"))

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
        if hosted:
            raise ValueError("Hosted spacer files are not available yet.")
        with geometry_lock:
            # Authoritative, like generation: the browser need not (and the
            # normal UI does not) send inventory rows for planning.
            inv = load_inventory(folder(payload))
            return plan_spacers(
                find_drawer(payload["layout"], payload.get("drawer_id")),
                inv["bins"], payload.get("options"),
            )

    def spacers_generate(payload):
        if hosted:
            raise ValueError("Hosted spacer files are not available yet.")
        with geometry_lock, INVENTORY_LOCK:
            def generate_file(name, mesh):
                out = folder(payload) / name
                mesh.export(str(out))
                return out

            layout = payload["layout"]
            drawer = find_drawer(layout, payload.get("drawer_id"))
            inv = load_inventory(folder(payload))
            options = payload.get("options") or {}

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
            for b in inv["bins"]:
                count = selection.get(b["id"])
                if count and int(count) > 0 and b.get("file"):
                    path = out_dir / b["file"]
                    if path.is_file():
                        files.append(path)
                        launch_files.extend([path] * int(count))
                        counts[b["file"]] = int(count)
            if not files:
                raise ValueError("Select at least one spacer to print.")
            slicer = detect_slicer(payload.get("slicer_path"))
            if slicer is None or not Path(slicer).is_file():
                raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")
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
            ))

    def connectors(payload):
        if hosted:
            raise ValueError("Hosted Space connectors are not available yet. Generate connectors from the normal designer.")
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))

    def send_to_slicer(payload):
        if hosted:
            raise ValueError("Hosted Wavefinity saves files to your folder instead of opening a local slicer.")
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
        "/api/drawer/design-source/save": save_design_source,
        "/api/drawer/report": report,
        "/api/drawer/auto": auto,
        "/api/drawer/surface-fill": surface_fill,
        "/api/drawer/surface-fill/create": surface_fill_create,
        "/api/drawer/spacers": spacers,
        "/api/drawer/spacers/generate": spacers_generate,
        "/api/drawer/connectors": connectors,
        "/api/drawer/print": send_to_slicer,
        "/api/drawer/print-spacers": print_spacers_only,
        "/api/drawer/print-bins": print_bins,
    }
