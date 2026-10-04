"""Wavefinity drawer constants, grid/stack metrics, stack items and surface fill planning."""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any
import numpy as np
from organizer_app import (
    bore_reference_envelope_extensions,
    design_from_dict,
    object_height_plan,
)
from organizer_stack import stack_summary
from organizer_engine import BASE_UNIT, MAX_BOX_SIZE, WAVE_AMPLITUDE, WAVE_MATING_GAP
from organizer_inventory import design_specs, normalise_storage_box
from organizer_b4b import B4B_STACK_RECESS_DEPTH, b4b_summary
from organizer_product_rules import DRAWER_HARD_CLEARANCE_MM
from organizer_stack import STACK_PLUG_DEPTH, STACK_SEAT_DEPTH
from organizer_pegboard import pegboard_standard
from organizer_edge_mount import edge_mount_projection_envelope
from organizer_printer_profile import (
    DEFAULT_PRINTER_BUILD_MM,
    normalise_printer_profile,
)


def _default_printer_profile() -> dict[str, float]:
    return normalise_printer_profile(dict(zip(
        ("x_mm", "y_mm", "z_mm"), DEFAULT_PRINTER_BUILD_MM,
    )))

UNIT = BASE_UNIT
SNAPS = (8.0, 4.0)
# How far a bin's wave crests stand past its grid footprint on each side.
CREST = WAVE_AMPLITUDE - WAVE_MATING_GAP / 2.0
# Total slack per axis a drawer needs just to take the crests at both walls.
MIN_CLEARANCE = DRAWER_HARD_CLEARANCE_MM
MIN_EDGE_SPACER = 1.2           # thinnest edge spacer worth printing, at a wave trough
RIGID_SPACER_CLEARANCE_MM = 0.40
MIN_SPACER_HEIGHT = 6.0         # a spacer frame still needs room for its lock bumps
DEFAULT_SPACER_HEIGHT = 15.0
SPACER_CONTACT_TARGET = 28.0    # target contact width of a back/right spacer, mm
SPACER_DISTRIBUTE_EVERY = 100.0
SPACER_SELECTED_CAP = 8  # Fix 090: max selected spacer candidates, applied per run  # Fix 088 S88-3: one planned spacer per ~100 mm of exposed run
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


def is_storage_box_layout(layout: dict[str, Any] | None) -> bool:
    space = layout.get("space") if isinstance(layout, dict) else None
    return isinstance(space, dict) and space.get("kind") in ("portable", "box")


def storage_box_height_cap(layout: dict[str, Any]) -> float:
    space = layout["space"]
    return float(space["z"]) + normalise_storage_box(space.get("storage_box"))["lid_headroom_mm"]


def stack_wall(one: dict[str, Any], specs: dict[str, Any]) -> float | None:
    """Inventory wall is authoritative; old rows may inherit their source wall."""
    value = one.get("wall")
    if value is None:
        value = ((specs.get(one["id"]) or {}).get("box") or {}).get("wall")
    try:
        wall = float(value)
    except (TypeError, ValueError):
        return None
    return wall if math.isfinite(wall) and wall > 0 else None


def stack_compatibility_issue(upper: dict[str, Any], lower: dict[str, Any], specs: dict[str, Any]) -> str | None:
    """The same physical stack rule used by placement and report."""
    if upper.get("stack", "none") == "none" or lower.get("stack", "none") == "none":
        return "Both bins must be printed for stacking"
    if upper.get("stack") != lower.get("stack"):
        return "Stacking modes must match"
    same_footprint = _close(upper["x"], lower["x"]) and _close(upper["y"], lower["y"])
    # Only a lid carries a different footprint; whether the upper bin sits inside
    # the lid and clear of its siblings is decided where the offset is known.
    if not same_footprint and upper.get("stack") == "direct":
        return "Direct stacking requires bins with the same footprint"
    if not same_footprint and upper.get("stack") != "lid":
        return "Storage Box stacking requires bins with the same footprint"
    top_wall, bottom_wall = stack_wall(upper, specs), stack_wall(lower, specs)
    if top_wall is None or bottom_wall is None:
        return "Stacking wall thickness is unknown; save both bin designs before stacking"
    if not _close(top_wall, bottom_wall):
        return ("Bins need the same footprint and compatible stacking wall thickness" if same_footprint
                else "Bins need compatible stacking wall thickness")
    return None


def space_stack_metrics(layout: dict[str, Any] | None, bins: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Transient physical heights from the canonical design, never Inventory schema.

    Storage Box and Surface share this one authority. A Surface row whose saved
    design is unavailable or unreadable falls back to the Inventory row.
    """
    surface = is_surface_layout(layout)
    if not (surface or is_storage_box_layout(layout)):
        return {}
    specs = design_specs(layout)
    metrics = {}
    for one in bins:
        source = specs.get(one["id"])
        if one.get("kind") not in ("bin", "b4b") or not isinstance(source, dict):
            continue
        try:
            box = design_from_dict(source)[0]
            if one.get("kind") == "b4b" and box.b4b.enabled:
                height = b4b_summary(box)["assembled_envelope_mm"][2]
                metrics[one["id"]] = {
                    "physical_mm": height,
                    "pitch_mm": height - (B4B_STACK_RECESS_DEPTH if box.b4b.stacking else 0),
                }
            else:
                summary = stack_summary(box)
                metrics[one["id"]] = {
                    "physical_mm": summary["closed_height_mm"],
                    "pitch_mm": summary["pitch_mm"],
                }
        except (ValueError, TypeError, KeyError, OverflowError):
            if not surface:
                raise
    return metrics


storage_box_stack_metrics = space_stack_metrics


def surface_planning_heights(layout: dict[str, Any] | None, bins: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not is_surface_layout(layout):
        return {}
    specs = design_specs(layout)
    metrics = space_stack_metrics(layout, bins)
    plans = {}
    for one in bins:
        height = one.get("object_height_mm")
        plan = object_height_plan(specs.get(one["id"]), height)
        metric = metrics.get(one["id"], {})
        physical = metric.get("physical_mm", stack_part_height(one))
        pitch = metric.get("pitch_mm", stack_pitch(one))
        plans[one["id"]] = {**plan, "physical_mm": physical, "pitch_mm": pitch,
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


def _offset(value: Any) -> float:
    """A saved stacked-placement offset in units; anything that is not a finite
    number reads as 0, so a malformed layout still opens and reports."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def _support_trees(drawer: dict[str, Any], by_id: dict[str, dict]) -> tuple[list[dict], list[dict]]:
    """The drawer's grid placements as rooted support trees, plus any stacked
    placement that no floor placement reaches (stacked on nothing, or in a
    loop).  A root stands on the floor at its own ``gx``/``gy``; every other
    placement names exactly one parent in ``on``, and a parent may carry any
    number of children.  Each node is ``{"p", "key", "parent", "children"}``."""
    placements = [p for p in drawer["placements"] if p.get("bin") in by_id]
    nodes = [{"p": p, "key": _key(p), "parent": None, "children": []} for p in placements]
    by_key: dict[str, dict] = {}
    for node in nodes:
        by_key.setdefault(node["key"], node)
    roots, loose = [], []
    for node in nodes:
        p = node["p"]
        if "on" in p:
            parent = by_key.get(p["on"])
            if parent is not None and parent is not node:
                node["parent"] = parent
                parent["children"].append(node)
            else:
                loose.append(p)
        elif "gx" in p:
            roots.append(node)
    reached: set[int] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        reached.add(id(node))
        stack.extend(node["children"])
    loose += [n["p"] for n in nodes if "on" in n["p"] and id(n) not in reached and n["p"] not in loose]
    return roots, loose


def _physical_envelopes(
    layout: dict[str, Any] | None,
    bins: list[dict[str, Any]],
    drawer: dict[str, Any],
) -> dict[str, dict[str, int]]:
    """Per-bin physical XY extension in Space grid cells.

    Edge Mount and leaned-Bore stored-object reach are combined here once. The
    same returned map is used by backend report collision and the browser.
    """
    grid = drawer_grid(drawer)
    step_x = grid.get("step_x", grid["step"])
    step_y = grid.get("step_y", grid["step"])
    specs = design_specs(layout)
    result: dict[str, dict[str, int]] = {}
    for one in bins:
        millimetres = {"l": 0.0, "t": 0.0, "r": 0.0, "b": 0.0}
        source = specs.get(one["id"])
        if isinstance(source, dict):
            box_source = source.get("box") if isinstance(source.get("box"), dict) else {}
            edge = edge_mount_projection_envelope(box_source.get("edge_mount"))
            if edge:
                side = {"front": "t", "back": "b", "left": "l", "right": "r"}[edge["side"]]
                millimetres[side] = max(millimetres[side], float(edge["projection_mm"]))
            try:
                box, source_layout, *_ = design_from_dict(source, validate_layout=False)
                bore = bore_reference_envelope_extensions(box, source_layout)
            except (ValueError, TypeError, KeyError, OverflowError):
                bore = {}
            for side in ("l", "t", "r", "b"):
                millimetres[side] = max(millimetres[side], float(bore.get(side, 0.0)))
        result[one["id"]] = {
            "l": math.ceil(millimetres["l"] / step_x),
            "t": math.ceil(millimetres["t"] / step_y),
            "r": math.ceil(millimetres["r"] / step_x),
            "b": math.ceil(millimetres["b"] / step_y),
        }
    return result


def _stack_item(root: dict, drawer: dict[str, Any], by_id: dict[str, dict],
                plans: dict[str, dict[str, Any]] | None = None,
                specs: dict[str, Any] | None = None,
                envelopes: dict[str, dict[str, int]] | None = None,
                storage_box: bool = False,
                surface: bool = False) -> dict[str, Any]:
    """One grid footprint: a single bin, or a support tree of them.

    ``root`` is a ``_support_trees`` node.  Every layer carries its own absolute
    footprint (a child sits at its parent's origin plus its offset) and seats on
    its direct parent, never on a sibling.  ``storage_box`` / ``surface`` both
    read seating pitch and physical height from ``plans`` (the shared canonical
    stack metrics); a Surface also checks installed Object height against the
    next seating plane.  ``layers`` is the flattened tree, parent first.
    """
    metrics = storage_box or surface
    pegboard = drawer.get("boundary") == "pegboard"
    per_unit = _per_unit(drawer)
    base = root["p"]
    first = by_id[base["bin"]]
    layers: list[dict[str, Any]] = []
    placements: list[dict[str, Any]] = []
    issues: list[str] = []
    notes: list[str] = []
    seen: set[int] = set()

    def visit(node: dict, parent: dict[str, Any] | None) -> None:
        seen.add(id(node))
        placement = node["p"]
        one = by_id[placement["bin"]]
        w, d = bin_cells(one, drawer)
        if parent is None:
            gx, gy, bottom, depth = _cell(placement["gx"], drawer), _cell(placement["gy"], drawer), 0.0, 0
        else:
            below = by_id[parent["bin"]]
            gx = parent["gx"] + _cell(_offset(placement.get("ox")), drawer)
            gy = parent["gy"] + _cell(_offset(placement.get("oy")), drawer)
            depth = parent["depth"] + 1
            issue = stack_compatibility_issue(one, below, specs or {})
            if issue:
                issues.append(f"{_label(one)} cannot stack on {_label(below)}: {issue}")
            if (gx < parent["gx"] or gy < parent["gy"]
                    or gx + w > parent["gx"] + parent["w"] or gy + d > parent["gy"] + parent["d"]):
                issues.append(f"{_label(one)} sticks out past the edge of {_label(below)}")
            if per_unit == 1 and (_offset(placement.get("ox")) % 1 or _offset(placement.get("oy")) % 1):
                issues.append(f"{_label(one)} sits off the 8 mm grid on {_label(below)}")
            below_plan = (plans or {}).get(below["id"], {})
            pitch = below_plan.get("pitch_mm", stack_pitch(below))
            bottom = (parent["z0"] + pitch
                      if metrics else parent["z1"] - STACK_STEPS.get(one.get("stack", "none"), 0.0))
            if surface:
                # The upper bin seats at z0 + pitch of its direct parent. A known
                # installed object that rises past that plane blocks the stack; an
                # unknown one is allowed but never called verified.
                object_top = below_plan.get("object_top_mm")
                if object_top is None:
                    note = f"Contents clearance not verified — Object height is not set for {_label(below)}."
                    if note not in notes:
                        notes.append(note)
                elif float(object_top) > pitch + 1e-6:
                    issue = f"The object in {_label(below)} reaches above the next stack seating plane."
                    if issue not in issues:
                        issues.append(issue)
        physical = ((plans or {}).get(one["id"], {}).get("physical_mm", stack_part_height(one))
                    if metrics else stack_part_height(one))
        layer = {
            "key": node["key"], "bin": placement["bin"], "copy": int(placement.get("copy", 0)),
            "z0": bottom, "z1": bottom + physical,
            "plan_z1": bottom + ((plans or {}).get(one["id"], {}).get("effective_mm", physical)),
            "gx": gx, "gy": gy, "w": w, "d": d,
            "parent": parent["key"] if parent else None, "depth": depth,
        }
        layers.append(layer)
        placements.append(placement)
        for child in node["children"]:
            if id(child) not in seen:
                visit(child, layer)

    visit(root, None)
    # Siblings on one support share its seating plane, so they may not overlap.
    children: dict[str, list[dict[str, Any]]] = {}
    for layer in layers:
        if layer["parent"] is not None:
            children.setdefault(layer["parent"], []).append(layer)
    layer_by_key = {layer["key"]: layer for layer in layers}
    for parent_key, group in children.items():
        for index, a in enumerate(group):
            for b in group[index + 1:]:
                if (a["gx"] < b["gx"] + b["w"] and b["gx"] < a["gx"] + a["w"]
                        and a["gy"] < b["gy"] + b["d"] and b["gy"] < a["gy"] + a["d"]):
                    issues.append(
                        f"{_label(by_id[a['bin']])} and {_label(by_id[b['bin']])} overlap on "
                        f"{_label(by_id[layer_by_key[parent_key]['bin']])}")
    ex = {"l": 0, "t": 0, "r": 0, "b": 0}
    rect = [min(layer["gx"] for layer in layers), min(layer["gy"] for layer in layers),
            max(layer["gx"] + layer["w"] for layer in layers), max(layer["gy"] + layer["d"] for layer in layers)]
    if not pegboard:
        # Each layer's physical reach is measured from its own footprint.
        rect = [math.inf, math.inf, -math.inf, -math.inf]
        for layer in layers:
            envelope = (envelopes or {}).get(layer["bin"]) or {}
            reach = {side: int(envelope.get(side, 0)) for side in ("l", "t", "r", "b")}
            for side in ex:
                ex[side] = max(ex[side], reach[side])
            rect = [min(rect[0], layer["gx"] - reach["l"]), min(rect[1], layer["gy"] - reach["t"]),
                    max(rect[2], layer["gx"] + layer["w"] + reach["r"]),
                    max(rect[3], layer["gy"] + layer["d"] + reach["b"])]
    top_layer = max(layers, key=lambda layer: layer["z1"])
    return {
        "key": root["key"], "keys": [layer["key"] for layer in layers],
        "bin": base["bin"], "copy": int(base.get("copy", 0)),
        "gx": layers[0]["gx"], "gy": layers[0]["gy"],
        "w": layers[0]["w"], "d": layers[0]["d"],
        "h": top_layer["z1"], "plan_h": max(layer["plan_z1"] for layer in layers),
        "ex": ex, "rect": rect,
        "kind": first.get("kind", "bin"), "name": first.get("name", ""),
        "chain": placements, "layers": layers, "top": by_id[top_layer["bin"]], "issues": issues,
        "notes": notes,
    }


def _grid_items(drawer: dict[str, Any], by_id: dict[str, dict]) -> list[dict[str, Any]]:
    return [_stack_item(root, drawer, by_id) for root in _support_trees(drawer, by_id)[0]]


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
        # Floor occupancy is the floor placements only; a stacked bin never
        # takes floor of its own.
        if "gx" not in placement or "on" in placement or placement.get("bin") not in by_id:
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
