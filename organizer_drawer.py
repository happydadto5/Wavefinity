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
* Stacked: ``on`` names the one placement it stands on (``"B3:0"``) and
  ``ox``/``oy`` are its offset in 8 mm units from that placement's front-left
  corner (missing means 0, which is what older same-footprint stacks carry).
  Only a stackable bin of the same stacking style can snap onto another; direct
  and Storage Box stacking need the same footprint, while a snap-on lid can
  carry any number of smaller bins that sit fully inside it and clear of each
  other - partial coverage is normal.  A placement may carry several children
  and a child may carry its own; each one adds its requested module height
  above its direct parent.  The exposed top interlock remains part of the
  stack's physical drawer-height envelope.
* Free, for an edge-facing spacer: ``x``/``y``/``w``/``d`` in mm from the
  drawer's inside front-left corner, plus the ``side`` it lines.  Its width
  across the wall is the drawer's real leftover play, not rounded to a grid
  unit - a physically genuine residual, not a whole-8-mm footprint.

An ordinary bin row is one placement identity: at most one placement per
row. Its print state is the row's own ``status``, never the placement. A
spacer row is the exception: it is a repeated filler part and may be placed
several times (``copy`` counts those placements).

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
from typing import Any, Callable, Iterable

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Polygon
from shapely.geometry import box as shape_box
from shapely.ops import unary_union
import trimesh

from organizer_app import bore_reference_envelope_extensions, connector_filename, design_from_dict, design_source_payload, design_to_dict, generate_side_file, object_height_plan
from organizer_stack import stack_summary
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
    INVENTORY_FILENAME,
    INVENTORY_LOCK,
    design_specs,
    duplicate_design_source as _duplicate_design_source_row,
    duplicate_design_source_text as _duplicate_design_source_row_text,
    change_design_status as _change_design_status_row,
    change_design_status_text as _change_design_status_row_text,
    legacy_layout_space,
    load_inventory,
    load_inventory_text,
    mark_printed_rows,
    normalise_storage_box,
    storage_box_defaults,
    next_bin_id,
    save_design_source as _save_design_source_row,
    save_design_source_text as _save_design_source_row_text,
    save_inventory,
    save_inventory_text,
    update_bin_file,
)
from organizer_inserts import Layout
from organizer_b4b import B4B_STACK_RECESS_DEPTH, b4b_summary
from organizer_product_rules import DRAWER_HARD_CLEARANCE_MM, SURFACE_TRIM_HEIGHTS
from organizer_stack import STACK_MIN_WALL, STACK_PLUG_DEPTH, STACK_SEAT_DEPTH
from organizer_pegboard import pegboard_layout_for_bin, pegboard_standard
from organizer_edge_mount import edge_mount_projection_envelope
from organizer_slicer import slicer_display_name

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
    elif side == "left":
        # Fix 088 S88-1: mirror of "right" - the component's own minimum x
        # edge per row.
        for item in comp:
            edge = item["gx"]
            for row in range(item["gy"], item["gy"] + item["d"]):
                span[row] = min(span.get(row, edge), edge)
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


_SPACER_PLAN_BIN_FIELDS = (
    "id", "kind", "x", "y", "z", "wall", "object_height_mm", "stack",
)


def spacer_plan_signature(
    raw_drawer: dict[str, Any],
    bins: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> str:
    """CAS token for exactly the durable state that can change a spacer plan.

    Print status, Qty and generated filenames are intentionally excluded:
    they do not change the physical gaps. Any drawer geometry/placement change,
    any relevant placed-row geometry change, or any requested spacer setting
    change changes the token.
    """
    drawer = copy.deepcopy(raw_drawer or {})
    placed_ids = {
        str(one.get("bin"))
        for one in drawer.get("placements") or []
        if isinstance(one, dict) and one.get("bin") is not None
    }
    rows = []
    for one in bins or []:
        if str(one.get("id")) not in placed_ids:
            continue
        rows.append({
            key: one.get(key)
            for key in _SPACER_PLAN_BIN_FIELDS
        })
    rows.sort(key=lambda one: str(one.get("id") or ""))
    body = {
        "drawer": drawer,
        "bins": rows,
        "options": copy.deepcopy(options or {}),
    }
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_spacers(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    flexible = options.get("flexible", True)
    by_id = {one["id"]: one for one in bins}
    placed_spacer_count = sum(
        1 for placement in drawer.get("placements") or []
        if (by_id.get(placement.get("bin")) or {}).get("kind") in SPACER_KINDS)
    # Fix 088 S88-2: Auto height is the default - half the tallest bin's
    # height, clamped like a manual height. A manual height is honoured only
    # when Auto is off.
    if options.get("height_auto", True):
        # Fix 090: "tallest bin" means the tallest non-spacer bin actually
        # placed in THIS drawer - not the whole Space inventory (which also
        # holds unplaced bins and other drawers' bins).
        tallest = 0.0
        if rows and cols:
            for placement in drawer.get("placements") or []:
                one = by_id.get(placement.get("bin"))
                if one and one.get("kind") not in SPACER_KINDS:
                    tallest = max(tallest, float(one.get("z") or 0.0))
        auto_height = round(tallest / 2) if tallest > 0 else DEFAULT_SPACER_HEIGHT
        height = min(drawer["height"], max(MIN_SPACER_HEIGHT, auto_height))
    else:
        height = min(drawer["height"], max(MIN_SPACER_HEIGHT, float(options.get("height") or DEFAULT_SPACER_HEIGHT)))
    # Fix 088 S88-1: per-wall toggles, persisted under the layout's spacer
    # settings. There is deliberately no front-wall option.
    raw_walls = options.get("walls") or {}
    walls = {
        "left": bool(raw_walls.get("left", True)),
        "back": bool(raw_walls.get("back", True)),
        "right": bool(raw_walls.get("right", True)),
    }
    notes: list[str] = []

    candidates = []
    selected = []
    run_count = 0
    run_count_total = 0
    proposal_cap_applied = False

    if rows and cols:
        if not any(walls.values()):
            notes.append("All spacer walls are off.")
            return {"drawer": drawer, "height": height, "resolved_height": height,
                    "candidates": [], "selected": [], "notes": notes,
                    "run_count": 0, "run_count_total": 0,
                    "proposal_cap_applied": False,
                    "placed_spacer_count": placed_spacer_count}
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
                # Fix 088 S88-3: distribute along long runs - one candidate
                # per ~100 mm of exposed run. Each is still a short,
                # deterministic, strategically placed contact piece - not the
                # whole exposed run - per Fix 004: target ~28 mm of contact
                # width, clipped to its sub-segment when shorter, centred
                # within it. Returns a list (possibly empty).
                # A left/right run is vertical (spans rows, measured from the
                # y origin); a back run is horizontal (spans columns).
                vertical = side in ("right", "left")
                seg_lo = (grid["oy"] if vertical else grid["ox"]) + start * step
                seg_hi = (grid["oy"] if vertical else grid["ox"]) + end * step
                seg_len = seg_hi - seg_lo
                count = max(1, round(seg_len / SPACER_DISTRIBUTE_EVERY))
                made = []
                for k in range(count):
                    sub_lo = seg_lo + seg_len * k / count
                    sub_hi = seg_lo + seg_len * (k + 1) / count
                    sub_len = sub_hi - sub_lo
                    contact = min(sub_len, SPACER_CONTACT_TARGET)
                    contact_start = sub_lo + (sub_len - contact) / 2.0
                    if side == "right":
                        gap = (drawer["width"] - grid["ox"] - (edge * step)) - wall
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        px, py, w, d = grid["ox"] + edge * step, contact_start, gap, contact
                        cid = f"right-{edge}-{start}-{end}-{k}"
                    elif side == "left":
                        # Fix 088 S88-1: mirror of "right" against the left wall.
                        gap = (grid["ox"] + edge * step) - wall
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        px, py, w, d = wall, contact_start, gap, contact
                        cid = f"left-{edge}-{start}-{end}-{k}"
                    else:
                        gap = (drawer["depth"] - grid["oy"] - (edge * step)) - wall
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        px, py, w, d = contact_start, grid["oy"] + edge * step, contact, gap
                        cid = f"back-{edge}-{start}-{end}-{k}"
                    placement = {"bin": "spacer", "x": px, "y": py, "w": w, "d": d, "side": side}
                    area = w * d
                    score = comp_area / area if area > 0 else 0
                    # Fix 090: run identity - one exposed segment before
                    # distribution. A run's candidates are selected or
                    # skipped as a unit so the cap never chops a run in half.
                    run_id = f"{side}-{comp_idx}-{edge}-{start}-{end}"
                    made.append({"id": cid, "placements": [placement], "score": score,
                                 "axis": "x" if vertical else "y", "comp": comp_idx, "edge": edge,
                                 "run_id": run_id})
                return made

            for side in ("left", "back", "right"):
                if not walls[side]:
                    continue
                for edge, start, end in _exposed_segments(comp, side):
                    candidates.extend(_make_candidate(side, edge, start, end))

        # Reject a candidate that overlaps another bin/component along its
        # own physical path to the wall (never bridge through something real
        # to reach it).
        item_boxes = [
            {"x": grid["ox"] + i["gx"] * step, "y": grid["oy"] + i["gy"] * step, "w": i["w"] * step, "d": i["d"] * step}
            for i in items
        ]
        placed_spacer_boxes = []
        for placement in drawer.get("placements") or []:
            row = by_id.get(placement.get("bin"))
            if not row or row.get("kind") not in SPACER_KINDS:
                continue
            if not all(key in placement for key in ("x", "y", "w", "d")):
                continue
            placed_spacer_boxes.append({
                "side": str(placement.get("side") or ""),
                "x": float(placement["x"]),
                "y": float(placement["y"]),
                "w": float(placement["w"]),
                "d": float(placement["d"]),
            })

        def _candidate_already_satisfied(cand: dict[str, Any]) -> bool:
            p = cand["placements"][0]
            box = {"x": p["x"], "y": p["y"], "w": p["w"], "d": p["d"]}
            return any(
                placed["side"] == p.get("side") and _overlaps(box, placed)
                for placed in placed_spacer_boxes
            )
        valid_cands = []
        for cand in candidates:
            p = cand["placements"][0]
            edge = {"x": p["x"], "y": p["y"], "w": p["w"], "d": p["d"]}
            if any(_overlaps(edge, box) for box in item_boxes):
                continue
            if _candidate_already_satisfied(cand):
                continue
            valid_cands.append(cand)
        candidates = valid_cands
        
        candidates.sort(key=lambda c: c["score"], reverse=True)
        # Fix 088 S88-3: keep the per-(component, axis) best-edge rule, but
        # select every candidate on the winning edge - the sub-segments of one
        # logical run - not just the best one.
        # Fix 090: the cap is applied per candidate, best scores first, and
        # is defined explicitly: a run MAY be partially selected when the
        # cap binds. The survivors within a chopped run are its
        # highest-scoring candidates - the end-clipped pieces first, so a
        # truncated run keeps its ends covered. Whole-run-or-nothing was
        # rejected: a small high-scoring run could starve a major run
        # entirely (1 spacer placed where 8 gaps need them).
        winning_edge = {}
        for cand in candidates:
            key = (cand["comp"], cand["axis"])
            if key not in winning_edge:
                winning_edge[key] = cand["edge"]
        for comp_idx in range(len(components)):
            left = any(
                cand["comp"] == comp_idx and cand["axis"] == "x" and
                cand["id"].startswith("left-")
                for cand in candidates
            )
            right = any(
                cand["comp"] == comp_idx and cand["axis"] == "x" and
                cand["id"].startswith("right-")
                for cand in candidates
            )
            if walls["left"] and walls["right"] and left and right:
                chosen_edge = winning_edge.get((comp_idx, "x"))
                if chosen_edge is not None:
                    notes.append(
                        "A bin group is braced against only one side wall; "
                        "the opposite side is not braced."
                    )
        winning = [
            cand for cand in candidates
            if winning_edge.get((cand["comp"], cand["axis"])) == cand["edge"]
        ]
        run_count_total = len({cand["run_id"] for cand in winning})
        proposal_cap_applied = len(winning) > SPACER_SELECTED_CAP
        chosen = winning[:SPACER_SELECTED_CAP]
        selected = [{"id": cand["id"]} for cand in chosen]
        run_count = len({cand["run_id"] for cand in chosen})

        for cand in candidates:
            cand.pop("score", None)
            cand.pop("axis", None)
            cand.pop("comp", None)
            cand.pop("edge", None)
            cand.pop("run_id", None)

    return {"drawer": drawer, "height": height, "resolved_height": height,
            "candidates": candidates, "selected": selected, "notes": notes,
            "run_count": run_count, "run_count_total": run_count_total,
            "proposal_cap_applied": proposal_cap_applied,
            "placed_spacer_count": placed_spacer_count}

def _serpentine_flexure(
    w, d, side, flexible=True, *, phase_x=0.0, phase_y=0.0,
):
    web = 1.5
    pad_bin = 3.0
    pad_wall = 2.0

    if side == "left":
        mirrored, built_flexible = _serpentine_flexure(
            w, d, "right", flexible, phase_x=phase_x, phase_y=phase_y,
        )
        minx, _miny, maxx, _maxy = mirrored.bounds
        return affinity.scale(mirrored, -1, 1, origin=((minx + maxx) / 2, 0)), built_flexible

    if side == "right":
        if flexible:
            w += 0.5  # accepted flexible preload
        if not flexible or w < pad_bin + pad_wall + web * 3:
            measured_w = w - (0.5 if flexible else 0.0)
            relief = min(RIGID_SPACER_CLEARANCE_MM, max(0.0, measured_w - 0.2))
            return shape_box(
                relief / 2.0, 0,
                measured_w - relief / 2.0, d,
            ), False

        # Bin-facing wave: preserve the accepted shape construction but phase
        # it from this off-lattice spacer's actual Y centre.
        bin_profile = wavy_rect_outer(10.0, d / 2.0, phase_y=phase_y)
        bin_profile = affinity.translate(bin_profile, -bin_profile.bounds[0], d / 2.0)
        left_pad = bin_profile.intersection(shape_box(0, 0, pad_bin, d))

        # Drawer-wall pad uses the same canonical wave, aligned to the opposite
        # side of this measured gap instead of remaining flat.
        wall_profile = wavy_rect_outer(10.0, d / 2.0, phase_y=phase_y)
        wall_profile = affinity.translate(wall_profile, w - wall_profile.bounds[2], d / 2.0)
        right_pad = wall_profile.intersection(shape_box(w - pad_wall, 0, w, d))

        mid_y = d / 2.0
        top_web = shape_box(pad_bin, d - web, w - pad_wall, d)
        bot_web = shape_box(pad_bin, 0, w - pad_wall, web)
        mid_web = shape_box(pad_bin, mid_y - web / 2, w - pad_wall, mid_y + web / 2)
        vert1 = shape_box(pad_bin, web, pad_bin + web, mid_y)
        vert2 = shape_box(w - pad_wall - web, mid_y, w - pad_wall, d - web)
        return unary_union([left_pad, right_pad, top_web, bot_web, mid_web, vert1, vert2]), True

    if flexible:
        d += 0.5  # accepted flexible preload
    if not flexible or d < pad_bin + pad_wall + web * 3:
        measured_d = d - (0.5 if flexible else 0.0)
        relief = min(RIGID_SPACER_CLEARANCE_MM, max(0.0, measured_d - 0.2))
        return shape_box(
            0, relief / 2.0,
            w, measured_d - relief / 2.0,
        ), False

    bin_profile = wavy_rect_outer(w / 2.0, 10.0, phase_x=phase_x)
    bin_profile = affinity.translate(bin_profile, w / 2.0, -bin_profile.bounds[1])
    bot_pad = bin_profile.intersection(shape_box(0, 0, w, pad_bin))

    wall_profile = wavy_rect_outer(w / 2.0, 10.0, phase_x=phase_x)
    wall_profile = affinity.translate(wall_profile, w / 2.0, d - wall_profile.bounds[3])
    top_pad = wall_profile.intersection(shape_box(0, d - pad_wall, w, d))

    mid_x = w / 2.0
    left_web = shape_box(0, pad_bin, web, d - pad_wall)
    right_web = shape_box(w - web, pad_bin, w, d - pad_wall)
    mid_web = shape_box(mid_x - web / 2, pad_bin, mid_x + web / 2, d - pad_wall)
    horiz1 = shape_box(web, pad_bin, mid_x, pad_bin + web)
    horiz2 = shape_box(mid_x, d - pad_wall - web, w - web, d - pad_wall)
    return unary_union([bot_pad, top_pad, left_web, right_web, mid_web, horiz1, horiz2]), True
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

            phase_x = p["x"] + gap_w / 2.0
            phase_y = p["y"] + gap_d / 2.0
            poly, built_flexible = _serpentine_flexure(
                gap_w, gap_d, side, flexible,
                phase_x=phase_x, phase_y=phase_y,
            )
            # printed physical part size: the actual generated mesh target,
            # including the accepted 0.5 mm preload only for a true flexure.
            minx, miny, maxx, maxy = poly.bounds
            part_w, part_d = maxx - minx, maxy - miny
            is_flexible = flexible and built_flexible
            if flexible and not built_flexible:
                notes.append(f"Gap too short for flexure; generated rigid spacer for {side}.")

            mesh = _extrude_polygon(poly, height)
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
    if report["connector_short_seams"]:
        notes.append(
            f"{report['connector_short_seams']} shared seam(s) are too short for a connector; "
            "those bins print without connectors."
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
    # Preflight the authoritative slicer before any connector file is written.
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name = slicer_display_name(slicer) or "the slicer"
    counts: dict[str, int] = {}
    for placement in drawer.get("placements") or []:
        one = by_id.get(placement.get("bin"))
        if one and one.get("kind") in SPACER_KINDS and one.get("file"):
            counts[one["file"]] = counts.get(one["file"], 0) + 1
    connectors = generate_connectors(output_dir, layout, bins, drawer_id)
    for made in connectors["connectors"]:
        counts[made["file"]] = counts.get(made["file"], 0) + made["count"]
    files = [output_dir / name for name in counts if (output_dir / name).is_file()]
    omitted = sorted(name for name in counts if not (output_dir / name).is_file())
    if not files:
        raise ValueError("this drawer has no spacers or connectors to print yet")
    # Each file is repeated once per physical copy so the slicer project holds
    # the real number of parts.
    launch_files = [path for path in files for _ in range(max(1, counts[path.name]))]
    try:
        launch_slicer(Path(slicer), launch_files)
    except Exception as error:
        # The connector files above are real and kept; say so plainly.
        return {
            "partial": True,
            "partial_stage": "slicer",
            "error": f"Files were prepared, but {name} did not open: {error}",
            "files": [str(path) for path in files],
            "counts": counts,
            "omitted": omitted,
            "notes": connectors["notes"],
        }
    return {"files": [str(path) for path in files], "counts": counts, "omitted": omitted, "notes": connectors["notes"]}


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
    """Generate every drawer's connector set once: file name -> copies, notes."""
    counts: dict[str, int] = {}
    notes: list[str] = []
    for drawer in (layout or {}).get("drawers") or []:
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

    Printed status changes only after the slicer launch succeeds. Rows without
    current files but with a canonical ``design_specs`` entry are generated
    first by the shared ``prepare_inventory_bins`` step (the same one batch
    Save uses); each is recorded Saved / Qty 0 as soon as it is made. Any
    failure before the launch - a bin, the connectors, or the slicer - returns
    a structured partial result with the refreshed Inventory and never marks
    anything Printed.
    """
    output_dir = Path(output_dir).expanduser().resolve()
    # Preflight the authoritative slicer before any on-demand bin generation,
    # Inventory File-cell write or connector generation.
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name_cap = slicer_display_name(slicer) or "The slicer"
    by_id = {one["id"]: one for one in bins}
    counts: dict[str, int] = {}
    for bin_id, raw_count in (selection or {}).items():
        one = by_id.get(str(bin_id))
        if one is None:
            raise ValueError(f"no bin {bin_id!r} in the inventory")
        _copy_count(one, raw_count)
        if one.get("kind") not in ("bin", "b4b"):
            raise ValueError(f"{_label(one)} is not a generated bin and cannot be printed here")
        counts[one["id"]] = 1
    if not counts:
        raise ValueError("Select at least one bin to print.")

    blocked = selected_blocking_problems(layout, bins, counts)
    if blocked:
        raise ValueError(blocking_problem_copy(bins, blocked))

    prepared = prepare_inventory_bins(output_dir, list(counts), generate_from_design)
    if prepared["failed"]:
        slicer_label = slicer_display_name(slicer) or "The slicer"
        return _batch_partial(
            prepared, "generate", _prepare_failure_text(prepared, slicer_label), selection=counts)
    rows_files = prepared["files"]
    specs = prepared["specs"]
    inventory = prepared["inventory"]

    connector_counts: dict[str, int] = {}
    notes: list[str] = []
    if include_connectors:
        try:
            connector_counts, notes = _space_connectors(output_dir, layout, inventory["bins"])
        except Exception as error:
            return _batch_partial(
                prepared, "connectors",
                f"The bins were saved, but the Space connectors could not be made: {error}. "
                f"{name_cap} was not opened.", selection=counts)

    launch_files: list[Path] = []
    for bin_id in counts:
        launch_files.extend(rows_files[bin_id])
    for name, count in connector_counts.items():
        launch_files.extend([output_dir / name] * count)

    result_counts = {
        "selection": counts,
        "bin_copies": sum(counts.values()),
        "connector_counts": connector_counts,
        "connector_copies": sum(connector_counts.values()),
        "notes": notes,
    }
    try:
        launch_slicer(Path(slicer), launch_files)
    except Exception as error:
        # Files and connectors written above are kept; rows stay Saved (never
        # Printed). Return the refreshed Inventory so the browser matches disk.
        return _batch_partial(
            prepared, "slicer",
            f"{name_cap} did not open: {error}. Any files made during this attempt were kept.",
            **result_counts)

    try:
        # A row is one bin. Placement copy numbers are not print bookkeeping.
        saved = mark_printed_rows(output_dir, counts, specs)
    except Exception as error:
        return _batch_partial(
            prepared, "status",
            f"{name_cap} opened, but the printed status could not be recorded: {error}. "
            "Check the selected rows in Inventory.", **result_counts)
    return {**saved, **result_counts}


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
        return {**result, "stack_steps": STACK_STEPS,
                "stack_metrics": space_stack_metrics(result.get("layout"), result.get("bins") or []),
                "storage_box_headroom_default_mm": storage_box_defaults()["lid_headroom_mm"]}

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
            # Fix 096 A2: specs parallel to new_bins, attached atomically with
            # their rows by _merge_inventory.
            "new_bin_specs": payload.get("new_bin_specs") or (),
            "delete_ids": payload.get("delete_ids") or (),
        }
        if "layout" in payload and payload["layout"] is not None:
            changes["layout"] = payload["layout"]
        if hosted:
            return with_rules(save_inventory_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                available_filenames=payload.get("available_filenames") or (),
                **changes,
            ))
        return with_rules(save_inventory(folder(payload), **changes))

    def save_design_source(payload):
        """Canonicalize and save one editable Inventory design source."""
        design, record = design_source_payload(payload["design"])
        row_id = str(payload.get("row_id") or "") or None
        if hosted:
            result = _save_design_source_row_text(
                payload.get("inventory_text") or "",
                title=str(payload.get("inventory_title") or "Wavefinity"),
                design=design, record=record, row_id=row_id,
                available_filenames=payload.get("available_filenames") or (),
            )
        else:
            result = _save_design_source_row(folder(payload), design=design, record=record, row_id=row_id)
        return with_rules(result)

    def duplicate_design_source(payload):
        row_id = str(payload.get("row_id") or "")
        if hosted:
            result = _duplicate_design_source_row_text(
                payload.get("inventory_text") or "", row_id,
                title=str(payload.get("inventory_title") or "Wavefinity"),
            )
        else:
            result = _duplicate_design_source_row(folder(payload), row_id)
        return with_rules(result)

    def change_design_status(payload):
        row_id = str(payload.get("row_id") or "")
        action = str(payload.get("action") or "")
        file_text = payload.get("file")
        expected_design = payload.get("design")
        if file_text is not None and not isinstance(file_text, str):
            raise ValueError("file names must be text")
        if expected_design is not None and not isinstance(expected_design, dict):
            raise ValueError("expected design must be an object")
        if hosted:
            result = _change_design_status_row_text(
                payload.get("inventory_text") or "", row_id, action, file_text,
                title=str(payload.get("inventory_title") or "Wavefinity"),
                expected_design=expected_design,
            )
        else:
            result = _change_design_status_row(folder(payload), row_id, action, file_text, expected_design)
        return with_rules(result)

    def report(payload):
        return drawer_report(
            find_drawer(payload["layout"], payload.get("drawer_id")),
            payload.get("bins") or [], payload.get("height_reach") or "column",
            payload["layout"],
        )

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
        with geometry_lock:
            inv = (
                load_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                )
                if hosted else load_inventory(folder(payload))
            )
            layout = inv["layout"]
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            result = plan_spacers(drawer, inv["bins"], options)
            result["plan_signature"] = spacer_plan_signature(
                drawer, inv["bins"], options,
            )
            return result

    def spacers_generate(payload):
        if hosted:
            import base64
            import tempfile
            with geometry_lock, INVENTORY_LOCK:
                inv = load_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                )
                layout = copy.deepcopy(inv["layout"])
                drawer = find_drawer(layout, payload.get("drawer_id"))
                options = payload.get("options") or {}
                current_signature = spacer_plan_signature(drawer, inv["bins"], options)
                if current_signature != str(payload.get("plan_signature") or ""):
                    raise ValueError(
                        "Spacers changed while you were planning — refresh the Space and plan again. "
                        "Your unsaved spacer plan was discarded; nothing was merged."
                    )
                request_for_gen = {
                    "drawer": drawer,
                    "bins": inv["bins"],
                    "options": options,
                    "selected": payload.get("selected", []),
                }
                with tempfile.TemporaryDirectory(prefix="wavefinity-hosted-spacers-") as tmp:
                    tmpdir = Path(tmp)
                    def generate_file(name, mesh):
                        out = tmpdir / name
                        mesh.export(str(out))
                        return out
                    result = generate_spacers(request_for_gen, tmpdir, generate_file)
                    files_base64 = {}
                    for gen in result.get("generated", []):
                        files_base64[gen["file"]] = base64.b64encode(
                            (tmpdir / gen["file"]).read_bytes()).decode("ascii")
                new_bins: list[dict[str, Any]] = []
                bins_so_far = list(inv["bins"])
                for gen in result.get("generated", []):
                    new_id = next_bin_id(bins_so_far)
                    row = {
                        "id": new_id,
                        "kind": "spacer",
                        "boundary": "edge",
                        # Inventory x/y/z are physical mm, never Wavefinity unit counts.
                        "name": "Flexible Spacer" if gen.get("flexible") else "Rigid Spacer",
                        "x": gen["w"], "y": gen["d"], "z": gen["h"],
                        "qty": 1,
                        "file": gen["file"],
                        "flexible": bool(gen.get("flexible")),
                    }
                    new_bins.append(row)
                    bins_so_far.append(row)
                    for p in gen["placements"]:
                        p_copy = dict(p)
                        p_copy["bin"] = new_id
                        p_copy.setdefault("copy", 0)
                        drawer.setdefault("placements", []).append(p_copy)
                saved = save_inventory_text(
                    payload.get("inventory_text") or "",
                    title=str(payload.get("inventory_title") or "Wavefinity"),
                    layout=layout, new_bins=new_bins,
                )
                result["layout"] = saved["layout"]
                result["bins"] = saved["bins"]
                result["inventory_text"] = saved["inventory_text"]
                result["files_base64"] = files_base64
                return result
        with geometry_lock, INVENTORY_LOCK:
            def generate_file(name, mesh):
                out = folder(payload) / name
                mesh.export(str(out))
                return out

            inv = load_inventory(folder(payload))
            layout = copy.deepcopy(inv["layout"])
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            current_signature = spacer_plan_signature(drawer, inv["bins"], options)
            if current_signature != str(payload.get("plan_signature") or ""):
                raise ValueError(
                    "Spacers changed while you were planning — refresh the Space and plan again. "
                    "Your unsaved spacer plan was discarded; nothing was merged."
                )

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
                    "flexible": bool(gen.get("flexible")),
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

    def spacers_refresh(payload):
        """Replace the active drawer's spacer set in one Inventory commit."""
        import base64
        import tempfile

        with geometry_lock, INVENTORY_LOCK:
            if hosted:
                inventory_text = payload.get("inventory_text") or ""
                inventory_title = str(payload.get("inventory_title") or "Wavefinity")
                inv = load_inventory_text(inventory_text, title=inventory_title)
                root = None
            else:
                inventory_text = ""
                inventory_title = "Wavefinity"
                root = folder(payload)
                inv = load_inventory(root)

            layout = copy.deepcopy(inv["layout"])
            bins = list(inv["bins"])
            drawer = find_drawer(layout, payload.get("drawer_id"))
            options = payload.get("options") or {}
            plan = plan_spacers(drawer, bins, options)
            selected_ids = [
                str(one.get("id"))
                for one in plan.get("selected") or []
                if one.get("id") is not None
            ]
            request_for_gen = {
                "drawer": drawer,
                "bins": bins,
                "options": options,
                "selected": selected_ids,
            }

            active_id = str(drawer.get("id") or "")
            by_id = {str(one["id"]): one for one in bins}
            old_spacer_ids = {
                str(placement.get("bin"))
                for placement in drawer.get("placements") or []
                if (
                    str(placement.get("bin")) in by_id
                    and by_id[str(placement.get("bin"))].get("kind") in SPACER_KINDS
                )
            }

            if root is not None:
                root.mkdir(parents=True, exist_ok=True)
                stage_context = tempfile.TemporaryDirectory(
                    prefix=".wavefinity-spacer-stage-",
                    dir=root,
                )
            else:
                stage_context = tempfile.TemporaryDirectory(
                    prefix="wavefinity-hosted-spacer-refresh-",
                )

            with stage_context as tmp:
                stage = Path(tmp).resolve()

                def generate_file(name, mesh):
                    out = stage / name
                    mesh.export(str(out))
                    return out

                generated = generate_spacers(
                    request_for_gen,
                    stage,
                    generate_file,
                )

                new_bins: list[dict[str, Any]] = []
                bins_so_far = list(bins)
                new_placements: list[dict[str, Any]] = []
                for gen in generated.get("generated") or []:
                    new_id = next_bin_id(bins_so_far)
                    row = {
                        "id": new_id,
                        "kind": "spacer",
                        "boundary": "edge",
                        "name": "Flexible Spacer" if gen.get("flexible") else "Rigid Spacer",
                        "x": gen["w"],
                        "y": gen["d"],
                        "z": gen["h"],
                        "qty": 1,
                        "file": gen["file"],
                    }
                    new_bins.append(row)
                    bins_so_far.append(row)
                    for placement in gen.get("placements") or []:
                        placed = dict(placement)
                        placed["bin"] = new_id
                        placed.setdefault("copy", 0)
                        new_placements.append(placed)

                for one in layout.get("drawers") or []:
                    if str(one.get("id") or "") != active_id:
                        continue
                    one["placements"] = [
                        placement
                        for placement in one.get("placements") or []
                        if str(placement.get("bin")) not in old_spacer_ids
                    ]
                    one["placements"].extend(new_placements)
                    break

                still_used = {
                    str(placement.get("bin"))
                    for one in layout.get("drawers") or []
                    for placement in one.get("placements") or []
                }
                delete_ids = sorted(old_spacer_ids - still_used)
                new_names = list(dict.fromkeys(
                    str(one["file"])
                    for one in generated.get("generated") or []
                ))

                if hosted:
                    files_base64 = {
                        name: base64.b64encode((stage / name).read_bytes()).decode("ascii")
                        for name in new_names
                    }
                    saved = save_inventory_text(
                        inventory_text,
                        title=inventory_title,
                        layout=layout,
                        new_bins=new_bins,
                        delete_ids=delete_ids,
                        available_filenames=payload.get("available_filenames") or (),
                        protected_files=new_names,
                    )
                    return {
                        **generated,
                        "layout": saved["layout"],
                        "bins": saved["bins"],
                        "inventory_text": saved["inventory_text"],
                        "cleanup_files": saved.get("cleanup_files", []),
                        "files_base64": files_base64,
                        "removed": len(old_spacer_ids),
                    }

                backups: dict[str, Path | None] = {}
                installed: list[Path] = []
                try:
                    backups, installed = _promote_spacer_stage(
                        root,
                        stage,
                        new_names,
                    )
                    saved = save_inventory(
                        root,
                        layout=layout,
                        new_bins=new_bins,
                        delete_ids=delete_ids,
                        protected_files=new_names,
                    )
                except Exception as error:
                    if installed or backups:
                        try:
                            _rollback_spacer_stage(root, backups, installed)
                        except Exception as rollback_error:
                            raise RuntimeError(
                                f"{error} Spacer rollback also failed: {rollback_error}"
                            ) from error
                    raise

                return {
                    **generated,
                    "layout": saved["layout"],
                    "bins": saved["bins"],
                    "cleanup_failed": saved.get("cleanup_failed", []),
                    "removed": len(old_spacer_ids),
                }

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
                raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
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

    def print_complete(payload):
        """One local complete Space handoff: bins + placed spacers + connectors
        under one truthful preflight and ONE slicer launch. (Fix 096 C11.)

        Sequence (fixed):
          1. Slicer preflight — before any file is written.
          2. One truthful preflight: C6's selected_blocking_problems over
             every placed bin in the drawer.
          3. Bin files via prepare_inventory_bins (only rows without current
             files are generated from their design source).
          4. Placed spacer files already on disk. The literal eligibility
             predicate: a spacer-kind row referenced by a placement in this
             drawer whose "file" names a real .3mf directly inside the Space
             folder. Rows whose file is missing are named in notes and
             skipped — they are NOT generated here.
          5. The Space's required connectors via _space_connectors.
          6. ONE launch_slicer call with every file.
          7. Promotion (one authority, consistent with C1): every bin row and
             every spacer row handed to the slicer becomes Printed via
             mark_printed_rows. Anything not handed off stays as it was.
        """
        if hosted:
            raise ValueError("Hosted Wavefinity saves files to your folder instead of opening a local slicer.")
        if detect_slicer is None or launch_slicer is None:
            raise ValueError("printing is not available here")
        with geometry_lock:
            out_dir = folder(payload)
            inv = load_inventory(out_dir)
            layout, bins = inv["layout"], inv["bins"]
            drawer = find_drawer(layout, payload.get("drawer_id"))
            # 1. Slicer preflight first.
            slicer = detect_slicer(payload.get("slicer_path"))
            if slicer is None or not Path(slicer).is_file():
                raise ValueError("Bambu Studio was not found. Locate it with Change slicer in the bin view.")
            # 2. One truthful preflight over every placed bin in the drawer.
            by_id = {one["id"]: one for one in bins}
            counts: dict[str, int] = {}
            for placement in drawer.get("placements") or []:
                one = by_id.get(placement.get("bin"))
                if one is not None and one.get("kind") in ("bin", "b4b"):
                    counts[one["id"]] = counts.get(one["id"], 0) + 1
            if not counts:
                raise ValueError("This drawer has no placed bins to print.")
            blocked = selected_blocking_problems(layout, bins, counts)
            if blocked:
                raise ValueError(blocking_problem_copy(bins, blocked))
            # 3. Bin files.
            prepared = prepare_inventory_bins(out_dir, list(counts), generate_from_design)
            if prepared["failed"]:
                raise ValueError(
                    "The bins could not be prepared: "
                    + _prepare_failure_text(prepared, slicer=True)
                    + " Bambu Studio was not opened.")
            rows_files = prepared["files"]
            specs = prepared["specs"]
            inventory = prepared["inventory"]
            # 4. Placed spacer copies already on disk. One Inventory spacer
            # row may have several physical placements; launch one file per
            # placement while promoting the row identity only once.
            current_drawer = find_drawer(
                inventory["layout"],
                payload.get("drawer_id"),
            )
            current_by_id = {
                str(one["id"]): one
                for one in inventory["bins"]
            }
            spacer_rows_printed: set[str] = set()
            skipped_spacers: set[str] = set()
            spacer_copies = 0
            launch_files: list[Path] = []
            for bin_id in counts:
                launch_files.extend(rows_files[bin_id])
            for placement in current_drawer.get("placements") or []:
                row_id = str(placement.get("bin") or "")
                one = current_by_id.get(row_id)
                if one is None or one.get("kind") not in SPACER_KINDS:
                    continue
                safe = _safe_row_file(out_dir, one.get("file") or "")
                if safe is None:
                    skipped_spacers.add(_label(one))
                    continue
                launch_files.append(safe)
                spacer_rows_printed.add(row_id)
                spacer_copies += 1
            # 5. Space connectors.
            try:
                connector_counts, notes = _space_connectors(out_dir, inventory["layout"], inventory["bins"])
            except Exception as error:
                return _batch_partial(
                    prepared, "connectors",
                    f"Bin and spacer files were prepared, but the Space connectors could not be made: {error}. "
                    "Bambu Studio was not opened.",
                    notes=[
                        f"Spacer {name} has no file yet and was skipped — "
                        "open Spacers and choose Generate to remake it."
                        for name in sorted(skipped_spacers)
                    ],
                )
            for name, count in connector_counts.items():
                launch_files.extend([out_dir / name] * count)
            if skipped_spacers:
                notes.extend(
                    f"Spacer {name} has no file yet and was skipped — "
                    "open Spacers and choose Generate to remake it."
                    for name in sorted(skipped_spacers)
                )
            # 6. One launch.
            try:
                project_path = launch_slicer(Path(slicer), launch_files)
            except Exception as error:
                return _batch_partial(
                    prepared, "slicer",
                    f"Files were prepared, but Bambu Studio did not open: {error}. The files were kept.",
                    notes=notes)
            # 7. One promotion authority (C1's rule): handed off == Printed.
            try:
                saved = mark_printed_rows(
                    out_dir,
                    [*counts, *sorted(spacer_rows_printed)],
                    specs,
                )
            except Exception as error:
                return _batch_partial(
                    prepared, "status",
                    f"Bambu Studio opened, but the printed status could not be recorded: {error}. "
                    "Check the Inventory rows.",
                    notes=notes)
            return {
                **saved,
                "files": [str(path) for path in launch_files],
                "bin_copies": sum(counts.values()),
                "spacer_copies": spacer_copies,
                "connector_counts": connector_counts,
                "connector_copies": sum(connector_counts.values()),
                "notes": notes,
                "slicer": str(slicer),
                "project": str(project_path) if project_path else None,
            }

    def save_bins(payload):
        if hosted:
            raise ValueError("Saving bin files in bulk is available in local Wavefinity.")
        selection = payload.get("selection") or []
        row_ids = list(selection.keys()) if isinstance(selection, dict) else list(selection)
        with geometry_lock:
            return with_rules(save_inventory_bins(
                folder(payload), row_ids, bool(payload.get("include_connectors", False)),
                generate_from_design,
            ))

    def connectors(payload):
        if hosted:
            import base64
            import tempfile
            with geometry_lock, tempfile.TemporaryDirectory(prefix="wavefinity-hosted-connectors-") as tmp:
                result = generate_connectors(
                    Path(tmp), payload["layout"], payload.get("bins") or [],
                    payload.get("drawer_id"))
                files_base64 = {}
                for one in result.get("connectors", []):
                    files_base64[one["file"]] = base64.b64encode(
                        (Path(tmp) / one["file"]).read_bytes()).decode("ascii")
                result["files_base64"] = files_base64
                return result
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))
        with geometry_lock:
            return generate_connectors(folder(payload), payload["layout"], payload.get("bins") or [], payload.get("drawer_id"))


    return {
        "/api/drawer/load": load,
        "/api/drawer/save": save,
        "/api/drawer/design-source/save": save_design_source,
        "/api/drawer/design-source/duplicate": duplicate_design_source,
        "/api/drawer/design-source/status": change_design_status,
        "/api/drawer/report": report,
        "/api/drawer/surface-fill": surface_fill,
        "/api/drawer/surface-fill/create": surface_fill_create,
        "/api/drawer/spacers": spacers,
        "/api/drawer/spacers/generate": spacers_generate,
        "/api/drawer/spacers/refresh": spacers_refresh,
        "/api/drawer/connectors": connectors,
        "/api/drawer/print-complete": print_complete,
        "/api/drawer/print-spacers": print_spacers_only,
        "/api/drawer/print-bins": print_bins,
        "/api/drawer/save-bins": save_bins,
    }
