"""Wavefinity drawer connectors, pegboard report, blocking problems and drawer report."""

from __future__ import annotations

import math
from typing import Any, Iterable
import numpy as np
from organizer_engine import (
    DEFAULT_WALL,
    LOCKED_CONNECTOR_LENGTH,
    BoxSpec,
    ConnectorSpec,
    differing_connector_plan,
)
from organizer_inventory import design_specs
from organizer_stack import STACK_MIN_WALL
from organizer_pegboard import pegboard_layout_for_bin

from ._core import (
    UNIT,
    MIN_CONNECTOR_SEAM,
    SPACER_KINDS,
    normalise_drawer,
    find_drawer,
    drawer_grid,
    _per_unit,
    is_surface_layout,
    is_storage_box_layout,
    storage_box_height_cap,
    space_stack_metrics,
    surface_planning_heights,
    _key,
    _label,
    _overlaps,
    _support_trees,
    _physical_envelopes,
    _stack_item,
    _height_issues,
    _two_largest_empty,
)


def _connector_eligible(item: dict[str, Any]) -> bool:
    """Whether this footprint's seam can take a side connector at all.

    A Storage Box case has no bare wave wall to clip onto, a stackable bin's
    mouth is meant for the bin above, not a side clip, and any lid (handled
    or stackable) covers the rim a side connector would grip - so none of
    them should ever get one, no matter how long the shared seam runs."""
    if item["kind"] == "b4b":
        return False
    if item["top"].get("stack", "none") != "none":
        return False
    if item.get("has_lid"):
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


def _connectors(items: list[dict[str, Any]], step: float) -> tuple[list[dict[str, Any]], int, int]:
    """One connector per shared seam long enough to seat one, grouped by the
    two rim heights and wall thickness it joins.  Stacks join at their top
    bins.  Returns the groups, how many seams join incompatible bins -
    different wall thicknesses, which no printed connector fits - and how
    many shared seams are too short for even the smallest connector."""
    counts: dict[tuple[float, float, float], int] = {}
    mismatched = 0
    short_seams = 0
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
                short_seams += 1
                continue
            key = (*sorted((round(a["h"], 2), round(b["h"], 2)), reverse=True), wall_a)
            counts[key] = counts.get(key, 0) + 1
    groups = [
        {"heights": [key[0], key[1]], "wall": key[2], "count": count}
        for key, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    ]
    return groups, mismatched, short_seams


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
        "mounts": mounts,
        "pegboard": True,
    }


# Report severity: one owner. ``height`` (reach/accessibility), ``clearance``
# (unverified contents) and ``restraint`` (an interior bin group) advise only;
# every other problem type is a hard layout/stack problem that blocks printing.
ADVISORY_PROBLEM_TYPES = frozenset({"height", "clearance", "restraint"})
INTERIOR_COMPONENT_MESSAGE = (
    "This bin group is not against the Base Trim and may slide within the open Surface. "
    "Move or bridge it toward an edge if you want more restraint."
)


def problem_blocks_print(problem: dict[str, Any]) -> bool:
    """Whether one report problem must stop a combined print."""
    return problem.get("type") not in ADVISORY_PROBLEM_TYPES


def blocking_problem_messages(report: dict[str, Any]) -> list[str]:
    return [problem["message"] for problem in report.get("problems") or [] if problem_blocks_print(problem)]


def selected_blocking_problems(
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    selected_ids: Iterable[str],
) -> list[dict[str, Any]]:
    """Hard Space problems whose keys touch at least one selected placed bin."""
    selected = {str(one) for one in selected_ids}
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...], str]] = set()
    if not selected:
        return found
    for drawer in (layout or {}).get("drawers") or []:
        report = drawer_report(drawer, bins, layout=layout)
        for problem in report.get("problems") or []:
            if not problem_blocks_print(problem):
                continue
            affected = {
                str(key).rsplit(":", 1)[0]
                for key in problem.get("keys") or []
            }
            if not (affected & selected):
                continue
            identity = (
                str(problem.get("type") or ""),
                tuple(sorted(str(key) for key in problem.get("keys") or [])),
                str(problem.get("message") or ""),
            )
            if identity in seen:
                continue
            seen.add(identity)
            found.append(problem)
    return found


def blocking_problem_copy(
    bins: list[dict[str, Any]],
    problems: list[dict[str, Any]],
) -> str:
    by_id = {str(one["id"]): one for one in bins}
    lines = []
    for problem in problems:
        ids = []
        for key in problem.get("keys") or []:
            row_id = str(key).rsplit(":", 1)[0]
            if row_id in by_id and row_id not in ids:
                ids.append(row_id)
        labels = ", ".join(_label(by_id[row_id]) for row_id in ids)
        prefix = f"{labels}: " if labels else ""
        lines.append(f"• {prefix}{problem.get('message') or 'Space problem'}")
    return "Bulk print blocked — these Space problems affect the selected bins:\n" + "\n".join(lines)


def _interior_components(items: list[dict[str, Any]], cols: int, rows: int) -> list[list[str]]:
    """Report keys of each connected base-footprint group with no shared edge
    against the field boundary. Only bottom footprints count (never the
    projecting label envelope); a stack is its bottom footprint; corner-only
    contact neither joins two footprints nor touches the boundary."""
    parent = list(range(len(items)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def span(a0: int, a1: int, b0: int, b1: int) -> int:
        return min(a1, b1) - max(a0, b0)

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            x_span = span(a["gx"], a["gx"] + a["w"], b["gx"], b["gx"] + b["w"])
            y_span = span(a["gy"], a["gy"] + a["d"], b["gy"], b["gy"] + b["d"])
            shares_edge = (
                (y_span > 0 and (a["gx"] + a["w"] == b["gx"] or b["gx"] + b["w"] == a["gx"]))
                or (x_span > 0 and (a["gy"] + a["d"] == b["gy"] or b["gy"] + b["d"] == a["gy"]))
            )
            if shares_edge or (x_span > 0 and y_span > 0):
                parent[find(i)] = find(j)

    def on_boundary(item: dict[str, Any]) -> bool:
        x0, x1, y0, y1 = item["gx"], item["gx"] + item["w"], item["gy"], item["gy"] + item["d"]
        return bool(
            (span(y0, y1, 0, rows) > 0 and (x0 == 0 or x1 == cols))
            or (span(x0, x1, 0, cols) > 0 and (y0 == 0 or y1 == rows))
        )

    groups: dict[int, list[int]] = {}
    for index in range(len(items)):
        groups.setdefault(find(index), []).append(index)
    result = []
    for members in groups.values():
        if any(on_boundary(items[index]) for index in members):
            continue
        result.append([key for index in members for key in items[index]["keys"]])
    return result


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
    storage_box = is_storage_box_layout(layout)
    surface = is_surface_layout(layout)
    plans = space_stack_metrics(layout, bins) if storage_box else surface_planning_heights(layout, bins)
    specs = design_specs(layout)
    physical_envelopes = _physical_envelopes(layout, bins, drawer)
    owner = np.full((rows, cols), -1, dtype=int)
    problems: list[dict[str, Any]] = []
    for placement in drawer["placements"]:
        if placement.get("bin") not in by_id:
            problems.append({"type": "missing", "keys": [_key(placement)], "message": f"{placement.get('bin')} is no longer in the inventory"})
    roots, loose = _support_trees(drawer, by_id)
    for placement in loose:
        problems.append({"type": "floating", "keys": [_key(placement)], "message": f"{_label(by_id[placement['bin']])} is stacked on nothing"})
    items = [
        _stack_item(
            root, drawer, by_id, plans, specs, physical_envelopes, storage_box, surface
        )
        for root in roots
    ]
    per_unit = _per_unit(drawer)
    for index, item in enumerate(items):
        label = _label(by_id[item["bin"]])
        if len(item["layers"]) > 1:
            label = f"The stack of {len(item['layers'])} on {label}"
        for issue in item["issues"]:
            problems.append({"type": "stack", "keys": item["keys"], "message": issue})
        for note in item["notes"]:
            problems.append({"type": "clearance", "keys": item["keys"], "message": note})
        height_cap = storage_box_height_cap(layout) if storage_box else drawer["height"]
        if not is_surface_layout(layout) and item["h"] > height_cap + 1e-6:
            problems.append({"type": "too_tall", "keys": item["keys"], "message": f"{label} is {item['h']:g} mm tall; this Space takes {height_cap:g} mm"})
        base = item["chain"][0]
        if per_unit == 1 and (float(base["gx"]) % 1 or float(base["gy"]) % 1):
            problems.append({"type": "outside", "keys": item["keys"], "message": f"{label} sits off the 8 mm grid - move it to snap it back"})
        x0, y0, x1, y1 = item["rect"]
        if x0 < 0 or y0 < 0 or x1 > cols or y1 > rows:
            problems.append({"type": "outside", "keys": item["keys"], "message": f"{label} sticks out of the Surface" if surface else f"{label} sticks out of the drawer"})
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
    # Fix 111 N10: one eligibility contract - a lid makes ordinary side
    # connectors unavailable everywhere, matching the Designer's
    # connectorsUnavailable(). Stamp lid rows from their canonical design
    # specs so _connector_eligible sees the same rule the UI applies.
    lid_rows = {
        row_id for row_id, spec in specs.items()
        if isinstance(spec, dict) and isinstance(spec.get("box"), dict)
        and bool((spec["box"].get("lid") or {}).get("enabled"))
    }
    for item in items:
        item["has_lid"] = item["bin"] in lid_rows
    connectors, mismatched, short_seams = _connectors(items, step)
    if surface:
        for component in _interior_components(items, cols, rows):
            problems.append({"type": "restraint", "keys": component, "message": INTERIOR_COMPONENT_MESSAGE})
    for problem in problems:
        problem["severity"] = "advisory" if problem["type"] in ADVISORY_PROBLEM_TYPES else "hard"
    return {
        "grid": grid,
        "physical_envelopes": physical_envelopes,
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
        "connector_short_seams": short_seams,
        "problems": problems,
        "height_issues": len(issues),
        "placed": sum(len(item["layers"]) for item in items),
        "stacks": sum(1 for item in items if len(item["layers"]) > 1),
        "planning_heights": plans,
        "edge_spacers": sum(1 for p in drawer["placements"] if "gx" not in p and "on" not in p),
    }


def _problem_signature(problem: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    return problem["type"], tuple(sorted(problem.get("keys") or ()))


def _bin_names(keys: Iterable[str], by_id: dict[str, dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for key in keys:
        row = by_id.get(str(key).rsplit(":", 1)[0])
        label = _label(row) if row else str(key)
        if label not in names:
            names.append(label)
    return names


def surface_reconfigure_problem(
    current_bins: list[dict[str, Any]], current_layout: dict[str, Any] | None,
    proposed_bins: list[dict[str, Any]], proposed_layout: dict[str, Any],
) -> str | None:
    """Why a proposed Surface would strand a placed bin, or None if it fits.

    Pure and shared by the local and hosted Surface edit: it runs the ordinary
    report over the *proposed* Surface with the current placements untouched.
    Geometry problems (outside / overlap, which include the accepted projecting
    label envelope) always refuse. Stack or floating problems refuse only when
    the edit introduces them, so an old unrelated problem never traps an edit.
    """
    baseline: set[tuple[str, tuple[str, ...]]] = set()
    if is_surface_layout(current_layout):
        baseline = {
            _problem_signature(one) for one in drawer_report(
                find_drawer(current_layout), current_bins, layout=current_layout)["problems"]
        }
    report = drawer_report(find_drawer(proposed_layout), proposed_bins, layout=proposed_layout)
    by_id = {one["id"]: one for one in proposed_bins}
    stranded: list[str] = []
    for problem in report["problems"]:
        kind = problem["type"]
        if kind in ("outside", "overlap") or (
                kind in ("stack", "floating") and _problem_signature(problem) not in baseline):
            for name in _bin_names(problem.get("keys") or (), by_id):
                if name not in stranded:
                    stranded.append(name)
    if not stranded:
        return None
    shown = ", ".join(stranded[:5]) + (f" and {len(stranded) - 5} more" if len(stranded) > 5 else "")
    return (
        f"This Surface change would leave placed bins outside or overlapping: {shown}. "
        "Nothing was changed. Move those bins first, or choose a larger maximum size."
    )
