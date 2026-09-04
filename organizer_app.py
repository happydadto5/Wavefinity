"""Command-line and desktop application for the wavy organizer generator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
import trimesh

from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    ConnectorSpec,
    GRID_PITCH,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    MIN_BOX_SIZE,
    WAVE_LENGTH,
    export_labelled_box,
    export_mesh,
    generate_sampler,
    label_report,
    label_placement,
    make_scoop,
    make_top_label_ledge,
    make_top_labelled_box,
    make_labelled_box,
    placed_label_outline,
    preview_rings,
    make_box,
    make_side_connector,
    measure_lock,
    mesh_report,
    scoop_floor_zone,
    scoop_keep_out,
    top_label_outline,
    top_label_report,
    top_label_zone,
    translated,
    union,
    validate_side_fit,
)
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    FEATURE_BUILDERS,
    INSERT_CLEARANCE,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    build_features,
    cartridge_zone,
    connector_keep_out,
    insert_footprint,
    insert_report,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    make_cartridge_insert,
    make_fitted_insert,
    make_fused_box,
    make_insert_plate,
    moved_feature,
    resized_feature,
    resolved_options,
    snapped_zone,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm
RESUME_ENV = "WAVEFINITY_RESUME"       # temp file the "Reload code" restart resumes from

SUPPORT_CATALOG = {
    "cradle": (
        "Cradle — tools laid down",
        "Open scalloped ribs for screwdrivers, markers and other handled tools.",
    ),
    "nest": (
        "Contour nest — snug tool recess",
        "A shallow recess following each length × diameter segment of the item.",
    ),
    "bore": (
        "Bore — upright tools",
        "Snug round, hex or square holes for nozzles, drivers and small tools.",
    ),
    "post": (
        "Center post — rolls and rings",
        "A lightly tapered peg for tape rolls, spools, sockets and ring-shaped parts.",
    ),
    "pocket": (
        "Pocket — loose small parts",
        "A raised tray for fasteners, adapters and other loose pieces.",
    ),
    "slot": (
        "Slots — cards and blades",
        "Parallel grooves for cards, blades, files and thin flat objects.",
    ),
    "divider": (
        "Divider — split the bin",
        "A straight wall that divides the usable floor into compartments.",
    ),
}
SUPPORT_ORDER = ("cradle", "nest", "bore", "post", "pocket", "slot", "divider")
LABEL_POSITIONS = ("bottom", "top")


def label_position(value: str) -> str:
    position = str(value).strip().lower()
    if position not in LABEL_POSITIONS:
        raise ValueError("label position must be 'bottom' or 'top'")
    return position


def support_display(kind: str) -> str:
    return SUPPORT_CATALOG.get(kind, (kind.replace("_", " ").title(), "Custom support."))[0]


def support_kind(choice: str) -> str:
    for kind in FEATURE_BUILDERS:
        if choice in {kind, support_display(kind)}:
            return kind
    raise ValueError(f"unknown interior support {choice!r}")


def support_help(kind: str) -> str:
    description = SUPPORT_CATALOG.get(kind, ("", "Custom registered support."))[1]
    if kind in {"cradle", "nest", "bore"}:
        return description + " Choose an item preset or enter its measured segments below."
    if kind == "post":
        return description + " Set diameter, height and taper in Options."
    return description + " Fine-tune it with the size, count and Options fields below."


# --- guided part palette ---------------------------------------------------
#
# Each entry drives the visual "pick a shape, then set its parameters" editor.
# ``flags`` say which of the shared controls (quantity / footprint / run axis /
# stored-item description) apply; ``fields`` are the parameters unique to that
# shape, as (label, builder-option key, default-or-blank).  A blank default
# means "let the builder choose".
PART_KINDS = (
    ("divider", "Divider", "A straight wall that splits the floor into compartments.",
     {"qty": False, "size": True, "along": True, "item": False},
     (("Height mm", "height", ""), ("Wall mm", "thickness", "1.6"))),
    ("post", "Post", "A tapered peg for tape rolls, spools, sockets and rings.",
     {"qty": True, "size": False, "along": True, "item": False},
     (("Height mm", "height", "16"), ("Diameter mm", "diameter", "12"),
      ("Taper mm", "taper", "0.4"), ("Gap mm", "spacing", "4"))),
    ("pocket", "Pocket", "A raised open tray for loose small parts.",
     {"qty": False, "size": True, "along": False, "item": False},
     (("Height mm", "height", "12"), ("Wall mm", "wall", "1.6"),
      ("Recess mm", "depth", ""))),
    ("slot", "Slots", "Parallel grooves for cards, blades and thin flat things.",
     {"qty": True, "size": True, "along": True, "item": False},
     (("Height mm", "height", "12"), ("Slot mm", "width", "2"),
      ("Cut mm", "depth", ""), ("Wall mm", "wall", "1.6"))),
    ("bore", "Bore", "A block of snug upright holes for tools stood on end.",
     {"qty": True, "size": True, "along": True, "item": True},
     (("Height mm", "height", ""), ("Hole depth mm", "depth", ""),
      ("Wall mm", "wall", "1.6"))),
    ("cradle", "Cradle", "Scalloped ribs that hold a handled tool on its side.",
     {"qty": True, "size": True, "along": True, "item": True},
     (("Floor gap mm", "floor_gap", "2"), ("Rib mm", "rib_thickness", "1.6"))),
    ("nest", "Nest", "A shallow snug recess following a tool's stepped outline.",
     {"qty": True, "size": True, "along": True, "item": True},
     (("Height mm", "height", ""), ("Recess mm", "depth", ""),
      ("Wall mm", "wall", "1.6"))),
)
PART_KIND_INFO = {
    kind: (title, blurb, flags, fields)
    for kind, title, blurb, flags, fields in PART_KINDS
}


def draw_part_icon(canvas, kind: str, colour: str = "#33566a") -> None:
    """Sketch a small glyph for one part kind onto a square Tk canvas."""
    canvas.delete("all")
    size = int(canvas.cget("width"))
    m = 5.0
    if kind == "divider":
        canvas.create_rectangle(m, m, size - m, size - m, outline=colour)
        canvas.create_line(size / 2, m, size / 2, size - m, fill=colour, width=2)
    elif kind == "post":
        canvas.create_oval(m, m, size - m, size - m, outline=colour)
        canvas.create_oval(size / 2 - 3, size / 2 - 3, size / 2 + 3, size / 2 + 3,
                           fill=colour, outline=colour)
    elif kind == "pocket":
        canvas.create_rectangle(m, m, size - m, size - m, outline=colour)
        canvas.create_rectangle(m + 4, m + 4, size - m - 4, size - m - 4, outline=colour)
    elif kind == "slot":
        for i in range(3):
            x = m + 3 + i * (size - 2 * m - 6) / 2
            canvas.create_line(x, m, x, size - m, fill=colour, width=2)
    elif kind == "bore":
        for gx in (0.32, 0.68):
            for gy in (0.32, 0.68):
                cx, cy = size * gx, size * gy
                canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, outline=colour)
    elif kind == "cradle":
        canvas.create_arc(m, m, size - m, 2 * size - m, start=0, extent=180,
                          style="arc", outline=colour)
        canvas.create_line(m, size / 2, size - m, size / 2, fill=colour)
    elif kind == "nest":
        canvas.create_oval(m, size * 0.32, size - m, size - m, outline=colour)
        canvas.create_oval(size * 0.4, size * 0.2, size * 0.6, size * 0.45, outline=colour)
    else:
        canvas.create_text(size / 2, size / 2, text="?", fill=colour)


# --- the part diagram ------------------------------------------------------
#
# Picking a shape draws a labelled sketch of that shape instead of a bare row
# of fields, and every parameter sits beside the feature of the part it
# actually changes, joined to it by a leader line.  The sketch is normalized -
# x, y and z each run 0..1 across the part - so it scales to whatever space the
# window happens to give it rather than growing off the screen.

DIAGRAM_TONE = {
    "top": "#d7e6ed",
    "front": "#aecbd8",
    "side": "#8eb2c4",
    "cavity": "#eff5f8",
    "hole": "#54727f",
    "tool": "#e59f54",
    "tool_light": "#f0bd85",
    "tool_cap": "#f6d4ac",
    "tool_edge": "#a9662c",
    "edge": "#5c7a88",
    "leader": "#8fa7b2",
}


def _face(points, tone: str, edge: str | None = None):
    return ("face", tuple(points), tone, edge)


def _disc(cx: float, cy: float, cz: float, radius: float, tone: str, edge: str | None = None):
    return ("disc", (cx, cy, cz), radius, tone, edge)


def _prism(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float):
    """The three faces of a box that the diagram's viewpoint can actually see."""
    return [
        _face([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], DIAGRAM_TONE["top"]),
        _face([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], DIAGRAM_TONE["side"]),
        _face([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], DIAGRAM_TONE["front"]),
    ]


def _sketch_divider():
    return _prism(0.02, 0.02, 0.0, 0.98, 0.98, 0.05) + _prism(
        0.02, 0.46, 0.05, 0.98, 0.56, 0.62
    )


def _sketch_post():
    parts = _prism(0.02, 0.02, 0.0, 0.98, 0.98, 0.05)
    for cx in (0.34, 0.72):
        parts.append(_disc(cx, 0.5, 0.05, 0.15, DIAGRAM_TONE["side"]))
        parts.append(_face(
            [(cx - 0.15, 0.5, 0.05), (cx + 0.15, 0.5, 0.05),
             (cx + 0.11, 0.5, 0.60), (cx - 0.11, 0.5, 0.60)],
            DIAGRAM_TONE["front"],
        ))
        parts.append(_disc(cx, 0.5, 0.60, 0.11, DIAGRAM_TONE["top"]))
    return parts


def _sketch_pocket():
    top_z = 0.46
    parts = _prism(0.05, 0.05, 0.0, 0.95, 0.95, top_z)
    parts.append(_face(
        [(0.16, 0.16, 0.11), (0.84, 0.16, 0.11), (0.84, 0.84, 0.11), (0.16, 0.84, 0.11)],
        DIAGRAM_TONE["cavity"],
    ))
    parts.append(_face(
        [(0.16, 0.84, 0.11), (0.84, 0.84, 0.11), (0.84, 0.84, top_z), (0.16, 0.84, top_z)],
        DIAGRAM_TONE["side"],
    ))
    parts.append(_face(
        [(0.16, 0.16, 0.11), (0.16, 0.84, 0.11), (0.16, 0.84, top_z), (0.16, 0.16, top_z)],
        DIAGRAM_TONE["front"],
    ))
    return parts


def _sketch_slot():
    top_z = 0.44
    parts = _prism(0.05, 0.05, 0.0, 0.95, 0.95, top_z)
    for cx in (0.28, 0.5, 0.72):
        half = 0.045
        parts.append(_face(
            [(cx - half, 0.05, top_z), (cx + half, 0.05, top_z),
             (cx + half, 0.88, top_z), (cx - half, 0.88, top_z)],
            DIAGRAM_TONE["hole"],
        ))
        parts.append(_face(
            [(cx - half, 0.05, top_z), (cx + half, 0.05, top_z),
             (cx + half, 0.05, 0.16), (cx - half, 0.05, 0.16)],
            DIAGRAM_TONE["hole"],
        ))
    return parts


def _sketch_bore():
    top_z = 0.42
    parts = _prism(0.05, 0.05, 0.0, 0.95, 0.95, top_z)
    for cx, cy in ((0.30, 0.72), (0.66, 0.72), (0.66, 0.32), (0.30, 0.32)):
        parts.append(_disc(cx, cy, top_z, 0.11, DIAGRAM_TONE["hole"]))
    parts.append(_face(                                   # the tool stood in a hole
        [(0.22, 0.32, 0.36), (0.38, 0.32, 0.36), (0.38, 0.32, 0.72), (0.22, 0.32, 0.72)],
        DIAGRAM_TONE["tool"], DIAGRAM_TONE["tool_edge"],
    ))
    parts.append(_face(
        [(0.18, 0.32, 0.72), (0.42, 0.32, 0.72), (0.42, 0.32, 0.95), (0.18, 0.32, 0.95)],
        DIAGRAM_TONE["tool_light"], DIAGRAM_TONE["tool_edge"],
    ))
    parts.append(_disc(0.30, 0.32, 0.95, 0.12, DIAGRAM_TONE["tool_cap"], DIAGRAM_TONE["tool_edge"]))
    return parts


def _sketch_cradle():
    parts = _prism(0.02, 0.02, 0.0, 0.98, 0.98, 0.05)
    for x0 in (0.22, 0.66):                               # the ribs, notched
        parts += _prism(x0, 0.26, 0.05, x0 + 0.08, 0.74, 0.52)
        parts.append(_face(
            [(x0, 0.44, 0.52), (x0 + 0.08, 0.44, 0.52),
             (x0 + 0.08, 0.56, 0.52), (x0, 0.56, 0.52)],
            DIAGRAM_TONE["hole"],
        ))
    parts.append(_face(                                   # the tool lying in them
        [(0.08, 0.44, 0.34), (0.72, 0.44, 0.34), (0.72, 0.44, 0.50), (0.08, 0.44, 0.50)],
        DIAGRAM_TONE["tool"], DIAGRAM_TONE["tool_edge"],
    ))
    parts.append(_face(
        [(0.72, 0.40, 0.30), (0.96, 0.40, 0.30), (0.96, 0.40, 0.54), (0.72, 0.40, 0.54)],
        DIAGRAM_TONE["tool_light"], DIAGRAM_TONE["tool_edge"],
    ))
    return parts


def _sketch_nest():
    top_z = 0.36
    parts = _prism(0.05, 0.05, 0.0, 0.95, 0.95, top_z)
    parts.append(_face(
        [(0.12, 0.42, top_z), (0.62, 0.42, top_z), (0.62, 0.58, top_z), (0.12, 0.58, top_z)],
        DIAGRAM_TONE["hole"],
    ))
    parts.append(_face(
        [(0.62, 0.36, top_z), (0.90, 0.36, top_z), (0.90, 0.64, top_z), (0.62, 0.64, top_z)],
        DIAGRAM_TONE["hole"],
    ))
    parts.append(_face(
        [(0.15, 0.45, 0.31), (0.60, 0.45, 0.31), (0.60, 0.55, 0.31), (0.15, 0.55, 0.31)],
        DIAGRAM_TONE["tool"], DIAGRAM_TONE["tool_edge"],
    ))
    parts.append(_face(
        [(0.63, 0.39, 0.31), (0.88, 0.39, 0.31), (0.88, 0.61, 0.31), (0.63, 0.61, 0.31)],
        DIAGRAM_TONE["tool_light"], DIAGRAM_TONE["tool_edge"],
    ))
    return parts


PART_SKETCHES = {
    "divider": _sketch_divider,
    "post": _sketch_post,
    "pocket": _sketch_pocket,
    "slot": _sketch_slot,
    "bore": _sketch_bore,
    "cradle": _sketch_cradle,
    "nest": _sketch_nest,
}

# Where each parameter points, as (x, y, z, side).  ``side`` is the margin the
# field sits in: quantity and the run axis go above the part, the footprint
# below it, and everything else beside the feature it sizes.
PART_DIAGRAM_ANCHORS = {
    "divider": {
        "feature_along": (0.50, 0.51, 0.62, "top"),
        "thickness": (0.30, 0.46, 0.62, "left"),
        "height": (0.98, 0.51, 0.34, "right"),
        "feature_depth": (0.98, 0.85, 0.05, "right"),
        "feature_width": (0.50, 0.02, 0.05, "bottom"),
    },
    "post": {
        "feature_count": (0.53, 0.50, 0.62, "top"),
        "feature_along": (0.34, 0.50, 0.60, "top"),
        "taper": (0.72, 0.50, 0.60, "top"),
        "spacing": (0.53, 0.50, 0.30, "left"),
        "height": (0.83, 0.50, 0.32, "right"),
        "diameter": (0.72, 0.50, 0.05, "bottom"),
    },
    "pocket": {
        "wall": (0.10, 0.50, 0.46, "left"),
        "depth": (0.16, 0.50, 0.28, "left"),
        "height": (0.95, 0.50, 0.23, "right"),
        "feature_depth": (0.95, 0.90, 0.00, "right"),
        "feature_width": (0.50, 0.05, 0.00, "bottom"),
    },
    "slot": {
        "feature_count": (0.50, 0.50, 0.44, "top"),
        "feature_along": (0.28, 0.50, 0.44, "top"),
        "wall": (0.16, 0.50, 0.44, "left"),
        "depth": (0.28, 0.05, 0.28, "left"),
        "height": (0.95, 0.50, 0.22, "right"),
        "feature_depth": (0.95, 0.90, 0.00, "right"),
        "feature_width": (0.50, 0.05, 0.00, "bottom"),
        "width": (0.50, 0.05, 0.44, "bottom"),
    },
    "bore": {
        "feature_count": (0.50, 0.72, 0.42, "top"),
        "feature_along": (0.30, 0.72, 0.42, "top"),
        "item_profile": (0.66, 0.32, 0.42, "top"),
        # Every measurement of the stored tool gathers on one side. Five
        # leaders converging on the same small drawing from four different
        # edges cross each other no matter how the tags are ordered.
        "wall": (0.08, 0.50, 0.42, "left"),
        "item_clearance": (0.30, 0.32, 0.42, "left"),
        "item_thickness": (0.22, 0.32, 0.60, "left"),
        # A length runs along the tool, so it reads under the drawing; on the
        # left it sat in the same 60 px band as five other tool measurements
        # and its leader had to climb across them.
        "item_length": (0.38, 0.32, 0.66, "bottom"),
        "item_handle_length": (0.30, 0.32, 0.80, "left"),
        "item_handle_thickness": (0.42, 0.32, 0.86, "left"),
        "depth": (0.66, 0.32, 0.30, "right"),
        "height": (0.95, 0.50, 0.21, "right"),
        "feature_depth": (0.95, 0.90, 0.00, "right"),
        "feature_width": (0.50, 0.05, 0.00, "bottom"),
    },
    "cradle": {
        "feature_count": (0.50, 0.50, 0.52, "top"),
        "feature_along": (0.26, 0.50, 0.52, "top"),
        "item_clearance": (0.50, 0.42, 0.56, "top"),
        "item_profile": (0.70, 0.50, 0.52, "top"),
        "floor_gap": (0.50, 0.44, 0.20, "bottom"),
        "item_thickness": (0.10, 0.44, 0.42, "left"),
        "feature_depth": (0.26, 0.74, 0.30, "bottom"),
        "rib_thickness": (0.70, 0.30, 0.52, "right"),
        "item_handle_thickness": (0.96, 0.40, 0.42, "right"),
        "feature_width": (0.50, 0.02, 0.05, "bottom"),
        "item_length": (0.40, 0.44, 0.34, "bottom"),
        "item_handle_length": (0.84, 0.40, 0.30, "bottom"),
    },
    "nest": {
        "feature_count": (0.40, 0.58, 0.36, "top"),
        "feature_along": (0.20, 0.50, 0.36, "top"),
        "item_clearance": (0.62, 0.64, 0.36, "top"),
        "item_profile": (0.86, 0.64, 0.36, "top"),
        "wall": (0.08, 0.50, 0.36, "left"),
        "depth": (0.12, 0.50, 0.26, "left"),
        "item_thickness": (0.14, 0.44, 0.30, "left"),
        "height": (0.95, 0.50, 0.18, "right"),
        "item_handle_thickness": (0.88, 0.38, 0.30, "right"),
        "feature_width": (0.50, 0.05, 0.00, "bottom"),
        "feature_depth": (0.95, 0.92, 0.00, "right"),
        "item_length": (0.37, 0.44, 0.30, "bottom"),
        "item_handle_length": (0.75, 0.38, 0.30, "bottom"),
    },
}

# The shared controls, plus the stored-item description, named the way they are
# labelled on the diagram.
SHARED_CALLOUTS = (
    ("qty", "feature_count", "Qty", "entry"),
    ("along", "feature_along", "Runs along", "axis"),
    ("size", "feature_width", "Width mm", "entry"),
    ("size", "feature_depth", "Depth mm", "entry"),
)
ITEM_CALLOUTS = (
    ("item_length", "Length mm", "entry"),
    ("item_thickness", "Thickness mm", "entry"),
    ("item_handle_length", "Handle length mm", "entry"),
    ("item_handle_thickness", "Handle thickness mm", "entry"),
    ("item_clearance", "Fit gap mm", "entry"),
    ("item_profile", "Hole shape", "choice"),
)


def diagram_callouts(kind: str) -> tuple[tuple[str, str, str], ...]:
    """Every parameter one shape uses, as (key, label, control kind)."""
    _title, _blurb, flags, fields = PART_KIND_INFO[kind]
    callouts = [
        (key, label, control)
        for flag, key, label, control in SHARED_CALLOUTS if flags[flag]
    ]
    callouts.extend((option, label, "option") for label, option, _default in fields)
    if flags["item"]:
        callouts.extend(ITEM_CALLOUTS)
    return tuple(callouts)


def diagram_projector(area: tuple[float, float, float, float]):
    """Normalized part space to canvas pixels, as a shallow oblique view."""
    x0, y0, x1, y1 = area
    width = x1 - x0
    height = y1 - y0
    across, back = width * 0.62, width * 0.38
    up, lift = height * 0.34, height * 0.44
    base = y1 - height * 0.11

    def project(point: tuple[float, float, float]) -> tuple[float, float]:
        x, y, z = point
        return x0 + x * across + y * back, base - y * lift - z * up

    project.spans = (across, back, up, lift)   # for round shapes on a plane
    return project


def draw_part_diagram(canvas, kind: str, area, tags=("sketch",)):
    """Paint one shape's schematic into ``area`` and return its projector."""
    project = diagram_projector(area)
    across, back, _up, lift = project.spans
    for shape in PART_SKETCHES.get(kind, list)():
        if shape[0] == "face":
            _name, points, tone, edge = shape
            canvas.create_polygon(
                [value for point in points for value in project(point)],
                fill=tone, outline=edge or DIAGRAM_TONE["edge"], tags=tags,
            )
        else:
            _name, centre, radius, tone, edge = shape
            u, v = project(centre)
            # A circle lying on a level plane comes out as an ellipse: this is
            # how far its rim swings sideways and up the screen.
            wide = radius * math.hypot(across, back)
            tall = max(2.5, radius * lift)
            canvas.create_oval(
                u - wide, v - tall, u + wide, v + tall,
                fill=tone, outline=edge or DIAGRAM_TONE["edge"], tags=tags,
            )
    return project


def parse_sizes(text: str) -> tuple[tuple[float, float], ...]:
    """Parse ``2x6,4x6,6x6`` (units) or ``16x48mm`` (millimetres).

    One unit is ``BASE_UNIT``.  Bare numbers are units; append ``mm`` to give
    millimetres instead.  Guessing from magnitude would be ambiguous now that a
    unit is 8 mm - ``8x8`` could plausibly mean either - so it is explicit.
    """
    sizes: list[tuple[float, float]] = []
    for chunk in text.split(","):
        chunk = chunk.strip().lower()
        if not chunk:
            continue
        millimetres = chunk.endswith("mm")
        if millimetres:
            chunk = chunk[:-2].strip()
        if "x" not in chunk:
            raise ValueError(f"'{chunk}' is not a WxH size")
        left, right = (part.strip() for part in chunk.split("x", 1))
        a, b = float(left), float(right)
        if not millimetres:
            a, b = a * BASE_UNIT, b * BASE_UNIT
        sizes.append((a, b))
    if not sizes:
        raise ValueError("no sizes given")
    return tuple(sizes)


def add_box_arguments(parser: argparse.ArgumentParser, prefix: str = "") -> None:
    option = f"{prefix}-" if prefix else ""
    destination = f"{prefix}_" if prefix else ""
    parser.add_argument(
        f"--{option}x", dest=f"{destination}x", type=float, default=BASE_UNIT
    )
    parser.add_argument(
        f"--{option}y", dest=f"{destination}y", type=float, default=BASE_UNIT
    )
    parser.add_argument(f"--{option}z", dest=f"{destination}z", type=float, default=40.0)
    parser.add_argument(
        f"--{option}wall", dest=f"{destination}wall", type=float, default=0.8
    )
    parser.add_argument(
        f"--{option}flat-inside", dest=f"{destination}flat_inside",
        type=float, default=0.0,
        help="0-1 mm: height of a flat-walled band rising from the floor",
    )


def add_connector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tolerance", type=float, default=LOCKED_TOLERANCE)
    parser.add_argument("--height", type=float, default=LOCKED_CONNECTOR_HEIGHT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate fixed-pitch wavy organizer boxes and their side connectors. "
            "Run without a command to open the desktop UI."
        )
    )
    subparsers = parser.add_subparsers(dest="command")

    box_parser = subparsers.add_parser("box", help="generate one adjustable box")
    add_box_arguments(box_parser)
    box_parser.add_argument(
        "--label",
        default="",
        help="flush inlay, as a second object for a second colour",
    )
    box_parser.add_argument("--label-position", choices=LABEL_POSITIONS, default="bottom")
    box_parser.add_argument("--scoop", action="store_true")
    box_parser.add_argument("--output", type=Path, required=True)

    side_parser = subparsers.add_parser("side", help="generate one side connector")
    add_box_arguments(side_parser, "box")
    add_connector_arguments(side_parser)
    side_parser.add_argument("--along", choices=("x", "y"), default="y")
    side_parser.add_argument(
        "--position",
        type=float,
        default=0.0,
        help="connector center from the wall center, in steps of the wave",
    )
    side_parser.add_argument("--length", type=float, default=LOCKED_CONNECTOR_LENGTH)
    side_parser.add_argument("--output", type=Path, required=True)

    kit_parser = subparsers.add_parser(
        "kit", help="generate one box and one matching side connector"
    )
    add_box_arguments(kit_parser)
    add_connector_arguments(kit_parser)
    kit_parser.add_argument("--side-along", choices=("x", "y"), default="y")
    kit_parser.add_argument("--side-position", type=float, default=0.0)
    kit_parser.add_argument("--label", default="")
    kit_parser.add_argument("--label-position", choices=LABEL_POSITIONS, default="bottom")
    kit_parser.add_argument("--scoop", action="store_true")
    kit_parser.add_argument("--output-dir", type=Path, required=True)

    layout_parser = subparsers.add_parser(
        "organizer", help="generate a fused or removable organizer from a layout JSON"
    )
    layout_parser.add_argument("--x", type=float)
    layout_parser.add_argument("--y", type=float)
    layout_parser.add_argument("--z", type=float)
    layout_parser.add_argument("--wall", type=float)
    layout_parser.add_argument("--flat-inside", type=float)
    layout_parser.add_argument("--layout", type=Path, required=True)
    layout_parser.add_argument("--mode", choices=("fused", "separate", "cartridge"))
    layout_parser.add_argument("--label")
    layout_parser.add_argument("--label-position", choices=LABEL_POSITIONS)
    scoop_group = layout_parser.add_mutually_exclusive_group()
    scoop_group.add_argument("--scoop", dest="scoop", action="store_true")
    scoop_group.add_argument("--no-scoop", dest="scoop", action="store_false")
    layout_parser.set_defaults(scoop=None)
    layout_parser.add_argument("--part-name")
    layout_parser.add_argument("--output-dir", type=Path, required=True)

    sampler_parser = subparsers.add_parser(
        "sampler", help="assembly sample: a set of boxes plus a row of connectors"
    )
    sampler_parser.add_argument(
        "--boxes",
        default=DEFAULT_SAMPLE_BOXES,
        help="comma separated sizes, in units (2x6) or millimetres (16x48mm)",
    )
    sampler_parser.add_argument("--z", type=float, default=40.0)
    sampler_parser.add_argument("--wall", type=float, default=0.8)
    sampler_parser.add_argument("--flat-inside", type=float, default=0.0)
    sampler_parser.add_argument("--clips", type=int, default=5)
    sampler_parser.add_argument("--tolerance", type=float, default=LOCKED_TOLERANCE)
    sampler_parser.add_argument("--output", type=Path, required=True)

    subparsers.add_parser("ui", help="open the desktop generator")
    return parser


def _box_spec(args: argparse.Namespace, prefix: str = "") -> BoxSpec:
    key = f"{prefix}_" if prefix else ""
    return BoxSpec(
        x=getattr(args, f"{key}x"),
        y=getattr(args, f"{key}y"),
        z=getattr(args, f"{key}z"),
        wall=getattr(args, f"{key}wall"),
        flat_inside=getattr(args, f"{key}flat_inside"),
    )


def _connector_spec(args: argparse.Namespace) -> ConnectorSpec:
    return ConnectorSpec(tolerance=args.tolerance, height=args.height)


def _part_result(output: Path, report: dict, fit: object = None) -> dict[str, object]:
    result: dict[str, object] = {"output": str(output.resolve()), "mesh": report}
    if fit is not None:
        result["fit"] = fit
    return result


ILLEGAL_IN_FILENAMES = r'<>:"/\|?*'


def clean_label(label: str) -> str:
    """The label with anything a filesystem would object to removed."""
    kept = "".join(
        " " if character in ILLEGAL_IN_FILENAMES else character
        for character in (label or "")
        if character.isprintable()
    )
    return " ".join(kept.split())


def box_filename(
    box: BoxSpec, label: str = "", suffix: str = ".3mf", part: str = ""
) -> str:
    """``Box 16 x 48 x 40 BOLTS Driver Rack.3mf``.

    The floor label and the part name are both optional and are simply
    appended, in that order. The part name is decoration for the filename and
    changes nothing about the geometry.
    """
    name = f"Box {box.x:g} x {box.y:g} x {box.z:g}"
    for extra in (clean_label(label), clean_label(part)):
        if extra:
            name += f" {extra}"
    return name + suffix


def insert_filename(
    box: BoxSpec,
    label: str = "",
    part: str = "",
    cartridge: bool = False,
    suffix: str = ".3mf",
) -> str:
    prefix = "Cartridge" if cartridge else "Insert"
    name = f"{prefix} {box.x:g} x {box.y:g}"
    for extra in (clean_label(label), clean_label(part)):
        if extra:
            name += f" {extra}"
    return name + suffix

PREVIEW_SIZE = 330
PREVIEW_PAD = 34

# A holder fused to the bin is the same piece of plastic as the bin, and a
# holder on a removable insert is not.  The preview says so by shifting the
# whole insert - its plate and every holder standing on it - towards one warm
# tint, away from the bin's cool blues.  The shift is partial on purpose:
# enough that the insert reads as one separate part at a glance, gentle enough
# that a cradle still looks orange and a bore still looks green.
INSERT_TINT = "#c2a075"
INSERT_TINT_MIX = 0.3

FEATURE_COLOURS = {
    "cradle": "#e59f54",
    "nest": "#df8d5b",
    "bore": "#6fb98f",
    "post": "#51a5a1",
    "divider": "#9d86c8",
    "pocket": "#d4778c",
    "slot": "#d5b84d",
}


def blended(colour: str, towards: str, amount: float) -> str:
    """``colour`` moved ``amount`` of the way towards ``towards``."""
    start = tuple(int(colour[at:at + 2], 16) for at in (1, 3, 5))
    end = tuple(int(towards[at:at + 2], 16) for at in (1, 3, 5))
    return "#" + "".join(
        f"{round(one + (other - one) * amount):02x}"
        for one, other in zip(start, end)
    )


FACE_COLOURS = {
    "outside": "#8fb8cc",
    "rim": "#bcd6e1",
    "inside": "#6b93a8",
    "floor": "#e8f0f4",
    "label": "#d9544d",
    "label_hole": "#e8f0f4",
    "top_label_ledge": "#c9dce4",
    "scoop": "#b7d4df",
    "insert_base": INSERT_TINT,
    "feature_invalid": "#d9534f",
    "insert_invalid": "#d9534f",
    "section_cut": "#7f97a3",
    "section_hole": "#e8f0f4",
}
FACE_COLOURS.update(
    {f"feature_{kind}": colour for kind, colour in FEATURE_COLOURS.items()}
)
FACE_COLOURS.update({
    f"insert_{kind}": blended(colour, INSERT_TINT, INSERT_TINT_MIX)
    for kind, colour in FEATURE_COLOURS.items()
})

# The parameter diagram's design size.  It grows with the window; this is only
# what it asks for before anyone has resized anything.
DIAGRAM_WIDTH = 620
DIAGRAM_HEIGHT = 330
# A part drawn much wider than it is tall flattens into a smear, so the sketch
# never stretches past this much of its own height however wide the panel gets.
# On a wide screen the old 1.35 left the drawing marooned in the middle of a
# mostly empty panel, with every callout crowded into the same narrow band.
DIAGRAM_ASPECT = 1.9

# Seen from 45 degrees round and PREVIEW_ELEVATION up.  A shallow angle looks
# more dramatic but a deep bin then hides its own floor completely, and the
# floor is where the label is, so the view is steep enough to see in while
# still showing two outer faces and the wall thickness.
PREVIEW_ELEVATION = 76.0


@dataclass(frozen=True)
class PreviewCamera:
    yaw: float = 45.0
    elevation: float = PREVIEW_ELEVATION
    zoom: float = 1.0

    def normalized(self) -> "PreviewCamera":
        return PreviewCamera(
            self.yaw % 360.0,
            min(89.0, max(8.0, self.elevation)),
            min(4.0, max(0.35, self.zoom)),
        )


def iso_point(
    point: tuple[float, float, float], camera: PreviewCamera | None = None
) -> tuple[float, float]:
    """One 3D point in screen coordinates, before scaling.

    Screen Y grows downward, so both world axes and Z are negated: +X, +Y and
    +Z all travel up the canvas, which is what keeps floor text the right way
    up instead of mirrored or upside down.
    """
    camera = (camera or PreviewCamera()).normalized()
    x, y, z = point
    yaw = math.radians(camera.yaw)
    elevation = math.radians(camera.elevation)
    side = x * math.cos(yaw) - y * math.sin(yaw)
    forward = x * math.sin(yaw) + y * math.cos(yaw)
    return side, -forward * math.sin(elevation) - z * math.cos(elevation)


def _towards_camera(
    normal: tuple[float, float, float], camera: PreviewCamera | None = None
) -> float:
    camera = (camera or PreviewCamera()).normalized()
    yaw = math.radians(camera.yaw)
    elevation = math.radians(camera.elevation)
    vector = (
        -math.sin(yaw) * math.cos(elevation),
        -math.cos(yaw) * math.cos(elevation),
        math.sin(elevation),
    )
    return sum(n * c for n, c in zip(normal, vector))


def _feature_height(box: BoxSpec, one: Feature, base_z: float) -> float:
    options = one.options
    if one.kind == "cradle" and one.item is not None:
        return base_z + options.get("floor_gap", 2.0) + one.item.held(one.item.widest) / 2.0
    if one.kind == "bore" and one.item is not None:
        depth = options.get("depth", min(one.item.length * 0.4, box.z - base_z - 2.0))
        return base_z + options.get("height", depth + 2.0)
    if one.kind == "divider":
        return base_z + options.get("height", connector_keep_out(box) - base_z)
    return base_z + options.get("height", 12.0)


def spread_callouts(
    wanted: list[float], sizes: list[float], gap: float, low: float, high: float
) -> list[float]:
    """Tag positions as close to ``wanted`` as fitting side by side allows.

    A tag would rather sit level with the point it labels: that draws the
    shortest, straightest leader.  Where two tags would collide they are pushed
    apart in order, so they stay in the same sequence as their targets - which
    is what stops one leader line from crossing another.  Spreading them evenly
    across the whole panel instead, as this used to, guarantees the opposite:
    the outermost tag reaches right across the drawing to a point in the middle.
    """
    if not wanted:
        return []
    spots = list(wanted)
    for at in range(1, len(spots)):
        floor = spots[at - 1] + (sizes[at - 1] + sizes[at]) / 2.0 + gap
        spots[at] = max(spots[at], floor)
    spots[-1] = min(spots[-1], high - sizes[-1] / 2.0)
    for at in range(len(spots) - 2, -1, -1):
        ceiling = spots[at + 1] - (sizes[at + 1] + sizes[at]) / 2.0 - gap
        spots[at] = min(spots[at], ceiling)
    # A run too long for the panel overflows the near end after that pass, so
    # clamp it back and let the overflow show at the far end instead.
    spots[0] = max(spots[0], low + sizes[0] / 2.0)
    for at in range(1, len(spots)):
        spots[at] = max(
            spots[at],
            spots[at - 1] + (sizes[at - 1] + sizes[at]) / 2.0 + gap,
        )
    return spots


def _prism_geometry(zone: Zone, z0: float, z1: float, kind: str) -> list[tuple]:
    a = (zone.x0, zone.y0)
    b = (zone.x1, zone.y0)
    c = (zone.x1, zone.y1)
    d = (zone.x0, zone.y1)
    return [
        ([(*a, z0), (*b, z0), (*b, z1), (*a, z1)], kind, (0.0, -1.0, 0.0), 0),
        ([(*b, z0), (*c, z0), (*c, z1), (*b, z1)], kind, (1.0, 0.0, 0.0), 0),
        ([(*c, z0), (*d, z0), (*d, z1), (*c, z1)], kind, (0.0, 1.0, 0.0), 0),
        ([(*d, z0), (*a, z0), (*a, z1), (*d, z1)], kind, (-1.0, 0.0, 0.0), 0),
        ([(*a, z1), (*b, z1), (*c, z1), (*d, z1)], kind, (0.0, 0.0, 1.0), 0),
    ]


def _mesh_preview_geometry(mesh, kind: str) -> list[tuple]:
    """Convert a finished holder mesh into camera-independent preview faces."""
    geometry = []
    for triangle, normal in zip(mesh.triangles, mesh.face_normals):
        geometry.append((
            [tuple(float(value) for value in point) for point in triangle],
            kind,
            tuple(float(value) for value in normal),
            0,
        ))
    return geometry


def _customization_zones(
    box: BoxSpec,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> list[tuple[str, Zone]]:
    """Floor-plan keep-outs for fixed bin customizations."""
    zones: list[tuple[str, Zone]] = []
    if clean_label(label) and label_position(label_location) == "top":
        zones.append(("top label ledge", Zone(*top_label_zone(box).bounds)))
    if scoop:
        zones.append(
            ("scoop", Zone(*scoop_keep_out(box, _scoop_floor_bounds(box, mode)).bounds))
        )
    return zones


def _scoop_floor_bounds(
    box: BoxSpec, mode: str
) -> tuple[float, float, float, float] | None:
    if mode == "fused":
        return None
    bounds = layout_zone(box, mode)
    return (
        bounds.x0 + INSERT_CLEARANCE,
        bounds.y0 + INSERT_CLEARANCE,
        bounds.x1 - INSERT_CLEARANCE,
        bounds.y1 - INSERT_CLEARANCE,
    )


def _removable_scoop(box: BoxSpec, mode: str):
    return translated(
        make_scoop(box, _scoop_floor_bounds(box, mode)), (0.0, 0.0, -box.wall)
    )


def base_height(box: BoxSpec, mode: str) -> float:
    """The z a holder is built up from: the bin floor, or the insert's plate."""
    return box.wall if mode == "fused" else box.wall + BASE_PLATE


def insert_plate_solid(box: BoxSpec, mode: str):
    """The standalone insert's base plate, sitting on the bin floor.

    ``None`` in fused mode, where the holders grow out of the floor and there
    is no plate.  Built from the same footprint the exporter uses, so what the
    preview draws is the part that comes out of the printer - inset by
    ``INSERT_CLEARANCE`` all round, with rounded corners, rather than flush to
    the wall where its edges are invisible.
    """
    if mode == "fused":
        return None
    return translated(make_insert_plate(box, mode), (0.0, 0.0, box.wall))


def validate_customization_clearance(
    box: BoxSpec,
    features: Iterable[Feature],
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> None:
    for index, one in enumerate(features):
        for name, zone in _customization_zones(
            box, label, label_location, scoop, mode
        ):
            if one.zone.overlaps(zone, MIN_FEATURE_GAP):
                raise ValueError(
                    f"interior support {index + 1} ({one.kind}) overlaps the {name}; "
                    "move or resize the support in the 2D layout"
                )


def preview_geometry(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused", label_location: str = "bottom", scoop: bool = False,
) -> dict[str, object]:
    """Build camera-independent preview geometry once per design change."""
    features = tuple(features)
    outer, cavity = preview_rings(box)
    floor_z, rim_z = box.wall, box.z
    geometry: list[tuple[list[tuple[float, float, float]], str,
                         tuple[float, float, float], int]] = []

    count = len(outer)
    for index in range(count):
        a, b = outer[index], outer[(index + 1) % count]
        c, d = cavity[index], cavity[(index + 1) % count]
        run = (b[0] - a[0], b[1] - a[1])
        outward = (run[1], -run[0], 0.0)
        inward = (-run[1], run[0], 0.0)
        geometry.append(([(a[0], a[1], 0.0), (b[0], b[1], 0.0),
                          (b[0], b[1], rim_z), (a[0], a[1], rim_z)],
                         "outside", outward, 0))
        geometry.append(([(c[0], c[1], floor_z), (d[0], d[1], floor_z),
                          (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                         "inside", inward, 0))
        geometry.append(([(a[0], a[1], rim_z), (b[0], b[1], rim_z),
                          (d[0], d[1], rim_z), (c[0], c[1], rim_z)],
                         "rim", (0.0, 0.0, 1.0), 0))
    geometry.append(([(*point, floor_z) for point in cavity],
                     "floor", (0.0, 0.0, 1.0), 1))

    tidy = clean_label(label)
    location = label_position(label_location)
    if tidy and location == "top":
        geometry.extend(_mesh_preview_geometry(make_top_label_ledge(box), "top_label_ledge"))
    if scoop:
        scoop_mesh = (
            make_scoop(box)
            if mode == "fused"
            else translated(_removable_scoop(box, mode), (0.0, 0.0, box.wall))
        )
        geometry.extend(_mesh_preview_geometry(scoop_mesh, "scoop"))

    plate = insert_plate_solid(box, mode)
    if plate is not None:
        geometry.extend(_mesh_preview_geometry(plate, "insert_base"))
    base_z = base_height(box, mode)
    # Holders belong to whichever part they are printed as: the bin when fused,
    # the insert otherwise.  The prefix picks the colour family.
    part_kind = "feature" if mode == "fused" else "insert"
    feature_errors = []
    invalid_feature_indexes = []
    reserved = _customization_zones(box, tidy, location, scoop, mode)
    for feature_index, one in enumerate(features):
        conflict = next(
            (name for name, zone in reserved if one.zone.overlaps(zone, MIN_FEATURE_GAP)),
            None,
        )
        if conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {conflict}")
            invalid_feature_indexes.append(feature_index)
        try:
            for solid in build_features(
                box, [one], base_z, layout_zone(box, mode)
            ):
                geometry.extend(
                    _mesh_preview_geometry(solid, f"{part_kind}_{one.kind}")
                )
        except Exception as error:
            feature_errors.append(f"{one.kind}: {error}")
            invalid_feature_indexes.append(feature_index)
            geometry.extend(_prism_geometry(
                one.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, one, base_z)),
                f"{part_kind}_invalid",
            ))

    fits, message = True, ""
    if tidy:
        try:
            if location == "top":
                outline = top_label_outline(box, tidy)
                label_z = box.z
            else:
                occupied = [one.zone.polygon for one in features]
                if scoop:
                    occupied.append(
                        scoop_floor_zone(box, _scoop_floor_bounds(box, mode))
                    )
                if mode == "cartridge":
                    occupied.append(Zone.whole(box).polygon.difference(cartridge_zone(box).polygon))
                outline = placed_label_outline(box, tidy, occupied)
                label_z = floor_z if mode == "fused" else box.wall + BASE_PLATE
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
            for piece in pieces:
                geometry.append(([(x, y, label_z) for x, y in piece.exterior.coords],
                                 "label", (0.0, 0.0, 1.0), 2))
                for ring in piece.interiors:
                    geometry.append(([(x, y, label_z) for x, y in ring.coords],
                                     "label_hole", (0.0, 0.0, 1.0), 3))

    inside_x, inside_y = box.usable_inside
    return {
        "geometry": geometry,
        "fits": fits,
        "message": message,
        "feature_errors": tuple(feature_errors),
        "invalid_feature_indexes": tuple(invalid_feature_indexes),
        "customization_zones": tuple(reserved),
        "x_text": f"{box.x:g}mm ({math.floor(inside_x):g} inside)",
        "y_text": f"{box.y:g}mm ({math.floor(inside_y):g} inside)",
        "z_text": f"{box.z:g}mm tall",
    }


def project_preview(geometry: dict[str, object], camera: PreviewCamera | None = None) -> dict[str, object]:
    """Cull and depth-sort a cached scene for the current camera."""
    camera = (camera or PreviewCamera()).normalized()
    faces = []
    floor_depth = None
    for points, kind, normal, layer in geometry["geometry"]:
        if _towards_camera(normal, camera) <= 0.0:
            continue
        depth = sum(_towards_camera(point, camera) for point in points) / len(points)
        if kind == "floor":
            floor_depth = depth
        faces.append([depth, layer, points, kind])
    if floor_depth is not None:
        label_z = next(
            (points[0][2] for _, _, points, kind in faces if kind == "label"),
            None,
        )
        floor_z = next(
            (points[0][2] for _, _, points, kind in faces if kind == "floor"),
            None,
        )
        surface_depth = floor_depth
        if label_z is not None and floor_z is not None:
            surface_depth += (label_z - floor_z) * _towards_camera(
                (0.0, 0.0, 1.0), camera
            )
        for face in faces:
            if face[3] in {"label", "label_hole"}:
                face[0] = surface_depth + face[1] * 0.001
    faces.sort(key=lambda item: item[0])
    result = dict(geometry)
    result.pop("geometry", None)
    result["faces"] = [(points, kind) for _, _, points, kind in faces]
    return result


def preview_scene(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused", camera: PreviewCamera | None = None,
    label_location: str = "bottom", scoop: bool = False,
) -> dict[str, object]:
    """The box as 3D faces ordered far to near, plus its dimension text.

    Built outside the widget code so the layout can be checked without opening
    a window.  Faces pointing away from the camera are dropped first - painting
    order alone cannot hide the far outside wall, because from above its top
    edge is genuinely nearer the camera than the floor is.
    """
    return project_preview(
        preview_geometry(box, label, features, mode, label_location, scoop), camera
    )


def preview_transform(
    box: BoxSpec, size: int = PREVIEW_SIZE, pad: int = PREVIEW_PAD,
    camera: PreviewCamera | None = None, height: int | None = None,
):
    """Millimetres to canvas pixels: isometric, centred, scaled to fit.

    ``size`` and ``height`` are the canvas the drawing has to land in, so a
    window stretched wide really does draw a bigger bin rather than the same
    small one floating in the middle.  Each axis is fitted separately and the
    tighter of the two wins, which is what keeps every corner on the canvas.
    """
    height = size if height is None else height
    corners = [
        iso_point((sx * box.x / 2.0, sy * box.y / 2.0, z), camera)
        for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, box.z)
    ]
    us = [u for u, _ in corners]
    vs = [v for _, v in corners]
    span_u = (max(us) - min(us)) or 1.0
    span_v = (max(vs) - min(vs)) or 1.0
    camera = (camera or PreviewCamera()).normalized()
    scale = min((size - 2 * pad) / span_u, (height - 2 * pad) / span_v) * camera.zoom
    mid_u = (max(us) + min(us)) / 2.0
    mid_v = (max(vs) + min(vs)) / 2.0

    def to_canvas(point: tuple[float, float, float]) -> tuple[float, float]:
        u, v = iso_point(point, camera)
        return size / 2.0 + (u - mid_u) * scale, height / 2.0 + (v - mid_v) * scale

    return to_canvas


def canvas_extent(canvas, fallback: int = PREVIEW_SIZE) -> tuple[int, int]:
    """The canvas as it is on screen now, or its design size before mapping."""
    width, height = canvas.winfo_width(), canvas.winfo_height()
    if width < 60 or height < 60:
        return fallback, fallback
    return width, height


# --- cut-section preview ----------------------------------------------------
#
# The preview is a painter's-order face list, so a section is done in two
# moves: clip every painted face to the half of the bin beyond the cut plane
# (a front-to-back plane at y = y_cut), then fill the exposed cross-section by
# slicing the real solids at the same plane and drawing those outlines on top.


def _clip_polygon_beyond_y(points, y_cut):
    """Sutherland-Hodgman clip of one face, keeping the part with y >= y_cut."""
    kept: list[tuple[float, float, float]] = []
    count = len(points)
    for index in range(count):
        cx, cy, cz = points[index]
        nx, ny, nz = points[(index + 1) % count]
        current_in = cy >= y_cut
        next_in = ny >= y_cut
        if current_in:
            kept.append((cx, cy, cz))
        if current_in != next_in and ny != cy:
            t = (y_cut - cy) / (ny - cy)
            kept.append((cx + t * (nx - cx), y_cut, cz + t * (nz - cz)))
    return kept


def clip_faces_beyond_y(faces, y_cut):
    """Drop each painted face, or its near part, in front of the cut plane."""
    clipped = []
    for points, kind in faces:
        piece = _clip_polygon_beyond_y(points, y_cut)
        if len(piece) >= 3:
            clipped.append((piece, kind))
    return clipped


def build_section_shell(box, mode, label, label_location, scoop):
    """The bin solid used to cap the cut: box plus its fixed customizations."""
    pieces = [make_box(box)]
    if clean_label(label) and label_position(label_location) == "top":
        pieces.append(make_top_label_ledge(box))
    if scoop:
        pieces.append(
            make_scoop(box) if mode == "fused"
            else translated(_removable_scoop(box, mode), (0.0, 0.0, box.wall))
        )
    if len(pieces) == 1:
        return pieces[0]
    try:
        return union(pieces)
    except Exception:
        return pieces[0]


def section_cap_faces(solids, y_cut):
    """Filled cross-section outlines where solids meet the plane y = y_cut.

    Each solid is sliced into loose plane/triangle segments, projected onto the
    x/z plane, noded and stitched into rings with shapely.  A ring nested inside
    another is a hollow (a bore hole) and is drawn back in the cavity colour.
    """
    from shapely.geometry import MultiLineString
    from shapely.ops import polygonize, unary_union

    from trimesh.intersections import mesh_plane

    solid_faces: list[list[tuple[float, float, float]]] = []
    hole_faces: list[list[tuple[float, float, float]]] = []
    for solid in solids:
        try:
            lines = mesh_plane(
                solid,
                plane_normal=np.array([0.0, 1.0, 0.0]),
                plane_origin=np.array([0.0, y_cut, 0.0]),
            )
        except Exception:
            continue
        if lines is None or len(lines) == 0:
            continue
        # mesh_plane returns loose, unordered fragments with sub-micron noise on
        # shared endpoints.  Snap to 0.01 mm so coincident ends actually match
        # and polygonize can stitch closed rings; drop anything that collapses.
        segments = []
        for a, b in lines:
            pa = (round(float(a[0]), 2), round(float(a[2]), 2))
            pb = (round(float(b[0]), 2), round(float(b[2]), 2))
            if pa != pb:
                segments.append((pa, pb))
        if not segments:
            continue
        try:
            rings = list(polygonize(unary_union(MultiLineString(segments))))
        except Exception:
            continue
        for index, ring in enumerate(rings):
            probe = ring.representative_point()
            nested = any(
                other is not ring and other.contains(probe)
                for other in rings
            )
            target = hole_faces if nested else solid_faces
            target.append(
                [(float(x), y_cut, float(z)) for x, z in ring.exterior.coords]
            )
    return (
        [(points, "section_cut") for points in solid_faces]
        + [(points, "section_hole") for points in hole_faces]
    )


def generate_box_file(
    box: BoxSpec,
    output: Path,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict[str, object]:
    """Write a customized box, plus a flush label as a second object if asked.

    An empty label changes nothing: one object, and the plain filename.
    """
    tidy = clean_label(label)
    location = label_position(label_location)
    body = make_box(box)
    if scoop:
        body = union([body, make_scoop(box)])
    if not tidy:
        report = mesh_report("wavy_box", body)
        export_mesh(body, output, "wavy_box")
        result = _part_result(output, report)
        result["customizations"] = {"scoop": scoop, "label_position": location}
        return result

    if location == "top":
        pocketed, inlay = make_top_labelled_box(box, tidy, body)
        label_info = top_label_report(box, tidy)
    else:
        occupied = [scoop_floor_zone(box)] if scoop else []
        pocketed, inlay = make_labelled_box(box, tidy, occupied, body)
        label_info = label_report(box, tidy, occupied)
    report = mesh_report("wavy_box", pocketed)
    export_labelled_box(pocketed, inlay, output, box_filename(box, suffix=""), tidy)
    result = _part_result(output, report)
    result["label"] = label_info
    result["customizations"] = {"scoop": scoop, "label_position": location}
    return result


def _label_obstacles(box: BoxSpec, layout: Layout, scoop: bool = False) -> list:
    occupied = [one.zone.polygon for one in layout.features]
    if scoop:
        occupied.append(scoop_floor_zone(box, _scoop_floor_bounds(box, layout.mode)))
    if layout.mode == "cartridge":
        occupied.append(
            Zone.whole(box).polygon.difference(cartridge_zone(box).polygon)
        )
    return occupied


def generate_organizer_files(
    box: BoxSpec,
    layout: Layout,
    output_dir: Path,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict[str, object]:
    """Export an editor design as fused, fitted-removable, or cartridge parts."""
    layout.validate(box)
    tidy = clean_label(label)
    location = label_position(label_location)
    validate_customization_clearance(
        box, layout.features, tidy, location, scoop, layout.mode
    )
    obstacles = _label_obstacles(box, layout, scoop)
    label_info = (
        top_label_report(box, tidy)
        if tidy and location == "top"
        else label_report(box, tidy, obstacles) if tidy else None
    )

    if layout.mode == "fused":
        body = make_fused_box(box, layout.features, make_box(box))
        if scoop:
            body = union([body, make_scoop(box)])
        output = output_dir / box_filename(box, tidy, part=part_name)
        if tidy:
            if location == "top":
                pocketed, inlay = make_top_labelled_box(box, tidy, body)
            else:
                pocketed, inlay = make_labelled_box(
                    box, tidy, occupied=obstacles, body=body
                )
            reported = pocketed
        else:
            reported = body
        output_dir.mkdir(parents=True, exist_ok=True)
        if tidy:
            export_labelled_box(
                pocketed,
                inlay,
                output,
                box_filename(box, part=part_name, suffix=""),
                tidy,
            )
        else:
            export_mesh(body, output, "fused_organizer")
        result: dict[str, object] = {
            "mode": layout.mode,
            "box": _part_result(output, mesh_report("fused_organizer", reported)),
            "layout": insert_report("fused_organizer", layout.features, body),
        }
    else:
        box_output = output_dir / box_filename(
            box, tidy if tidy and location == "top" else "", part=part_name
        )
        plain_box = make_box(box)
        insert = (
            make_cartridge_insert(box, layout.features)
            if layout.mode == "cartridge"
            else make_fitted_insert(box, layout.features)
        )
        if scoop:
            insert = union([insert, _removable_scoop(box, layout.mode)])
        insert_output = output_dir / insert_filename(
            box, tidy if location == "bottom" else "", part_name,
            layout.mode == "cartridge"
        )
        if tidy and location == "bottom":
            pocketed, inlay = make_labelled_box(
                box,
                tidy,
                occupied=obstacles,
                body=insert,
                top_z=BASE_PLATE,
            )
            reported_insert = pocketed
        else:
            reported_insert = insert
        output_dir.mkdir(parents=True, exist_ok=True)
        if tidy and location == "top":
            pocketed_box, box_inlay = make_top_labelled_box(box, tidy, plain_box)
            export_labelled_box(
                pocketed_box, box_inlay, box_output,
                box_filename(box, part=part_name, suffix=""), tidy,
            )
            reported_box = pocketed_box
        else:
            export_mesh(plain_box, box_output, "wavy_box")
            reported_box = plain_box
        if tidy and location == "bottom":
            export_labelled_box(
                pocketed,
                inlay,
                insert_output,
                insert_filename(
                    box,
                    part=part_name,
                    cartridge=layout.mode == "cartridge",
                    suffix="",
                ),
                tidy,
            )
        else:
            export_mesh(insert, insert_output, "organizer_insert")
        result = {
            "mode": layout.mode,
            "box": _part_result(box_output, mesh_report("wavy_box", reported_box)),
            "insert": _part_result(
                insert_output, mesh_report("organizer_insert", reported_insert)
            ),
            "layout": insert_report("organizer_insert", layout.features, insert),
        }
    if label_info is not None:
        result["label"] = label_info
    result["customizations"] = {"scoop": scoop, "label_position": location}
    return result


def generate_side_file(
    box: BoxSpec,
    connector: ConnectorSpec,
    output: Path,
    along: str = "y",
    position: float = 0.0,
    length: float = LOCKED_CONNECTOR_LENGTH,
) -> dict[str, object]:
    mesh = make_side_connector(box, connector, along, position, length)
    report = mesh_report("side_connector", mesh)
    overlap = validate_side_fit(box, connector, mesh, along, position)
    fit = {"seated_overlap_mm3": round(overlap, 6)}
    fit.update(measure_lock(box, connector, along, position))
    export_mesh(mesh, output, "side_connector")
    return _part_result(output, report, fit)


def generate_kit_files(
    box: BoxSpec,
    connector: ConnectorSpec,
    output_dir: Path,
    side_along: str = "y",
    side_position: float = 0.0,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "box": generate_box_file(
            box, output_dir / box_filename(box, label), label, label_location, scoop
        ),
        "side": generate_side_file(
            box,
            connector,
            output_dir / "Connector.3mf",
            side_along,
            side_position,
        ),
    }


def run_command(args: argparse.Namespace) -> dict[str, object] | None:
    if args.command in {None, "ui"}:
        launch_ui()
        return None
    if args.command == "sampler":
        return generate_sampler(
            output=args.output,
            sizes=parse_sizes(args.boxes),
            height=args.z,
            wall=args.wall,
            flat_inside=args.flat_inside,
            connector=ConnectorSpec(tolerance=args.tolerance),
            clips=args.clips,
        )
    if args.command == "box":
        return generate_box_file(
            _box_spec(args), args.output, args.label, args.label_position, args.scoop
        )
    if args.command == "organizer":
        raw = json.loads(args.layout.read_text(encoding="utf-8"))
        if "box" in raw:
            (saved_box, layout, saved_label, saved_part,
             saved_label_location, saved_scoop) = design_from_dict(raw)
        else:
            saved_box, layout, saved_label, saved_part = BoxSpec(), layout_from_dict(raw), "", ""
            saved_label_location, saved_scoop = "bottom", False
        box = BoxSpec(
            saved_box.x if args.x is None else args.x,
            saved_box.y if args.y is None else args.y,
            saved_box.z if args.z is None else args.z,
            saved_box.wall if args.wall is None else args.wall,
            saved_box.corner_fillet,
            saved_box.flat_inside if args.flat_inside is None else args.flat_inside,
        )
        if args.mode:
            layout = replace(layout, mode=args.mode)
        return generate_organizer_files(
            box,
            layout,
            args.output_dir,
            saved_label if args.label is None else args.label,
            saved_part if args.part_name is None else args.part_name,
            saved_label_location if args.label_position is None else args.label_position,
            saved_scoop if args.scoop is None else args.scoop,
        )
    if args.command == "side":
        return generate_side_file(
            _box_spec(args, "box"),
            _connector_spec(args),
            args.output,
            args.along,
            args.position,
            args.length,
        )
    if args.command == "kit":
        return generate_kit_files(
            _box_spec(args),
            _connector_spec(args),
            args.output_dir,
            args.side_along,
            args.side_position,
            args.label,
            args.label_position,
            args.scoop,
        )
    raise RuntimeError(f"unsupported command: {args.command}")


# --------------------------------------------------------------------------- #
# desktop UI
# --------------------------------------------------------------------------- #


def parse_segments(text: str) -> tuple[Segment, ...]:
    """Parse editor text such as ``50x6, 30x18`` as length/diameter segments."""
    segments = []
    for raw in text.split(","):
        raw = raw.strip().lower().replace("mm", "")
        if not raw:
            continue
        if "x" not in raw:
            raise ValueError("item segments use length x diameter, separated by commas")
        length, diameter = raw.split("x", 1)
        segments.append(Segment(float(length.strip()), float(diameter.strip())))
    if not segments:
        raise ValueError("an item needs at least one length x diameter segment")
    return tuple(segments)


def format_segments(item: Item) -> str:
    return ", ".join(f"{part.length:g}x{part.diameter:g}" for part in item.segments)


def parse_feature_options(text: str) -> dict[str, float]:
    """Parse the registry's open-ended ``key=value`` option field."""
    options = {}
    for raw in text.split(","):
        raw = raw.strip()
        if not raw:
            continue
        if "=" not in raw:
            raise ValueError("holder options use key=value, separated by commas")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key or not key.replace("_", "").isalnum():
            raise ValueError(f"invalid holder option name {key!r}")
        options[key] = float(value.strip())
    return options


def format_feature_options(options: dict) -> str:
    return ", ".join(f"{key}={value:g}" for key, value in sorted(options.items()))


def default_feature(
    box: BoxSpec,
    kind: str,
    item_key: str = "nozzle",
    along: str = "x",
    mode: str = "fused",
    item: Item | None = None,
) -> Feature:
    """A useful, valid starting rectangle for a newly-added holder.

    ``item`` describes the stored tool directly; when omitted, item-holding
    kinds fall back to a starter from ``LIBRARY[item_key]``.
    """
    if kind not in FEATURE_BUILDERS:
        raise ValueError(f"unknown holder {kind!r}")
    bounds = layout_zone(box, mode)
    if kind in {"cradle", "bore", "nest"}:
        item = item if item is not None else LIBRARY[item_key]
    else:
        item = None
    if item is not None and kind in {"cradle", "nest"}:
        required_length = item.length + (
            item.clearance + 2.0 * 1.6 if kind == "nest" else 0.0
        )
        pitch = CARTRIDGE_PITCH if mode == "cartridge" else EDITOR_SNAP
        required_length = math.ceil((required_length - 1e-9) / pitch) * pitch
        if along == "x" and required_length > bounds.width:
            along = "y"
        if along == "y" and required_length > bounds.depth:
            along = "x"
        run = bounds.width if along == "x" else bounds.depth
        if required_length > run:
            raise ValueError(
                f"{item.name} needs {required_length:g} mm; enlarge the bin first"
            )
        available_across = bounds.depth if along == "x" else bounds.width
        wanted_across = max(
            8.0, item.held(item.widest) + (3.2 if kind == "nest" else 1.6)
        )
        across = min(
            available_across,
            math.ceil((wanted_across - 1e-9) / pitch) * pitch,
        )
        width, depth = ((required_length, across) if along == "x"
                        else (across, required_length))
    elif kind == "divider":
        width, depth = ((bounds.width, 2.0) if along == "x"
                        else (2.0, bounds.depth))
    else:
        width, depth = min(16.0, bounds.width), min(16.0, bounds.depth)
    raw = Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    return Feature(
        kind,
        snapped_zone(raw, box, mode),
        item=item,
        count=1 if kind == "post" else None,
        along=along,
        options={"diameter": 12.0, "height": 16.0, "taper": 0.4}
        if kind == "post" else {},
    )


def convert_layout_mode(
    box: BoxSpec, features: Iterable[Feature], mode: str
) -> Layout:
    """Snap every support onto a new mode's grid and validate the result."""
    converted_items = []
    for one in features:
        zone = one.zone
        if mode == "cartridge":
            width = math.ceil((zone.width - 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            depth = math.ceil((zone.depth - 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            cx, cy = zone.centre
            zone = Zone(
                cx - width / 2.0, cy - depth / 2.0,
                cx + width / 2.0, cy + depth / 2.0,
            )
        converted_items.append(replace(one, zone=snapped_zone(zone, box, mode)))
    converted = tuple(converted_items)
    layout = Layout(converted, mode, EDITOR_SNAP)
    layout.validate(box)
    base_z = base_height(box, mode)
    build_features(box, converted, base_z, layout_zone(box, mode))
    return layout


def design_to_dict(
    box: BoxSpec,
    layout: Layout,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict:
    return {
        "version": 1,
        "box": {
            "x": box.x,
            "y": box.y,
            "z": box.z,
            "wall": box.wall,
            "corner_fillet": box.corner_fillet,
            "flat_inside": box.flat_inside,
        },
        "label": label,
        "label_position": label_position(label_location),
        "scoop": bool(scoop),
        "part_name": part_name,
        "layout": layout_to_dict(layout),
    }


def design_from_dict(data: dict) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    if data.get("version", 1) != 1:
        raise ValueError(f"unsupported design version {data.get('version')!r}")
    raw = data["box"]
    box = BoxSpec(
        float(raw["x"]), float(raw["y"]), float(raw["z"]),
        float(raw.get("wall", 0.8)),
        float(raw.get("corner_fillet", 0.6)),
        flat_inside=float(raw.get("flat_inside", 0.0)),
    )
    layout = layout_from_dict(data.get("layout", {}))
    layout.validate(box)
    return (
        box,
        layout,
        str(data.get("label", "")),
        str(data.get("part_name", "")),
        label_position(data.get("label_position", "bottom")),
        bool(data.get("scoop", False)),
    )


MIN_UNITS = int(round(MIN_BOX_SIZE / BASE_UNIT))
BASIC_FIELDS = (
    (f"Box width X (units of {BASE_UNIT:.0f} mm)", "x_units", 1.0, MIN_UNITS),
    (f"Box depth Y (units of {BASE_UNIT:.0f} mm)", "y_units", 1.0, MIN_UNITS),
    ("Box height Z (mm)", "z", None, None),
)
ADVANCED_FIELDS = (
    ("Wall / floor thickness (mm)", "wall", None, None),
    ("Flat wall band from base (0-1 mm)", "flat_inside", 0.1, 0.0),
    ("Connector tolerance (mm)", "tolerance", None, None),
    ("Connector height (mm)", "height", None, None),
    ("Connector length (mm)", "side_length", None, None),
    (
        f"Connector position (mm, steps of {WAVE_LENGTH / 2:.0f})",
        "side_position",
        WAVE_LENGTH / 2.0,
        -200.0,
    ),
)


def launch_ui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError as error:
        raise RuntimeError(
            "Tkinter is not installed in this Python runtime. Use the CLI or install Tk support."
        ) from error

    root = tk.Tk()
    root.title("Wavefinity")
    root.minsize(1080, 960)

    pending_jobs: set[str] = set()

    def later(delay: int, action):
        """``root.after`` that can be called off when the window closes.

        Tk tears down a callback's command as the window goes, so a timer
        still queued at that moment fires into nothing and reports an error
        against the dead interpreter.
        """
        def run() -> None:
            pending_jobs.discard(job)
            action()

        job = root.after(delay, run)
        pending_jobs.add(job)
        return job

    def cancel_later(job) -> None:
        if job is None:
            return
        pending_jobs.discard(job)
        try:
            root.after_cancel(job)
        except Exception:
            pass

    def cancel_pending(event=None) -> None:
        if event is not None and event.widget is not root:
            return
        for job in list(pending_jobs):
            cancel_later(job)

    root.bind("<Destroy>", cancel_pending, add="+")

    BODY = ("Segoe UI", 10)
    VALUE = ("Segoe UI", 12)
    STEP = ("Segoe UI", 13, "bold")

    style = ttk.Style(root)
    style.configure("TLabel", font=BODY)
    style.configure("TCheckbutton", font=BODY)
    style.configure("TRadiobutton", font=BODY)
    style.configure("Note.TLabel", font=("Segoe UI", 9), foreground="#666666")
    style.configure("Warn.TLabel", font=("Segoe UI", 9), foreground="#c0392b")
    style.configure("Panel.TLabelframe", borderwidth=3, relief="solid")
    # A parameter sitting out on the diagram reads as a tag pinned to the part.
    style.configure("Callout.TFrame", background="#f2f7fa",
                    relief="solid", borderwidth=1)
    style.configure("Callout.TLabel", font=("Segoe UI", 8),
                    background="#f2f7fa", foreground="#33566a")
    style.configure("Callout.TRadiobutton", font=("Segoe UI", 8),
                    background="#f2f7fa")
    style.configure("Field.TEntry", padding=4)
    # A number gets a big obvious stepper either side of it rather than the
    # pinhead arrows a Spinbox draws.
    style.configure("Step.TButton", font=STEP, padding=(0, 0), width=3)
    style.configure("Go.TButton", font=("Segoe UI", 11, "bold"), padding=(10, 9))
    style.configure("Small.TButton", font=("Segoe UI", 9), padding=(8, 4))

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text=(
            f"X and Y step in {GRID_PITCH:.0f} mm from {MIN_BOX_SIZE:.0f} mm up, so any "
            f"two boxes interlock.  Connector locked at {LOCKED_TOLERANCE:.2f} mm, "
            f"{LOCKED_CONNECTOR_LENGTH:.0f} x {LOCKED_CONNECTOR_HEIGHT:.1f} mm."
        ),
        style="Note.TLabel",
    ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

    values = {
        "x_units": tk.StringVar(value="2"),
        "y_units": tk.StringVar(value="6"),
        "z": tk.StringVar(value="40"),
        "label": tk.StringVar(value=""),
        "label_position": tk.StringVar(value="bottom"),
        "scoop": tk.BooleanVar(value=False),
        "part": tk.StringVar(value=""),
        "wall": tk.StringVar(value="0.8"),
        "flat_inside": tk.StringVar(value="0"),
        "tolerance": tk.StringVar(value=f"{LOCKED_TOLERANCE:g}"),
        "height": tk.StringVar(value=f"{LOCKED_CONNECTOR_HEIGHT:g}"),
        "side_length": tk.StringVar(value=f"{LOCKED_CONNECTOR_LENGTH:g}"),
        "side_axis": tk.StringVar(value="y"),
        "side_position": tk.StringVar(value="0"),
        "mode": tk.StringVar(value="fused"),
        "feature_along": tk.StringVar(value="x"),
        "feature_count": tk.StringVar(value="auto"),
        "feature_x": tk.StringVar(value="0"),
        "feature_y": tk.StringVar(value="0"),
        "feature_width": tk.StringVar(value="13"),
        "feature_depth": tk.StringVar(value="8"),
        "item_length": tk.StringVar(value="40"),
        "item_thickness": tk.StringVar(value="6"),
        "item_handle_length": tk.StringVar(value=""),
        "item_handle_thickness": tk.StringVar(value=""),
        "item_profile": tk.StringVar(value="round"),
        "item_clearance": tk.StringVar(value="0.4"),
        "output": tk.StringVar(value=str(APP_DIR / "generated")),
    }
    show_advanced = tk.BooleanVar(value=False)
    features: list[Feature] = []
    selected = {"index": None}
    # Set while the editor pushes a part's values into its own fields, so the
    # live-edit traces below can tell the user's typing from its own writing.
    syncing = {"on": False}
    mode_state = {"value": "fused"}
    camera = {"value": PreviewCamera(), "drag": None}
    preview_cache = {"spec": None, "geometry": None, "section_solids": None}
    section_state = {"t": 0.0}
    on_after_refresh = {"fn": lambda: None}

    def nudge(key: str, step: float, lowest: float) -> None:
        try:
            current = float(values[key].get())
        except ValueError:
            current = lowest
        moved = max(lowest, round((current + step) / step) * step if step >= 1 else current + step)
        values[key].set(f"{moved:g}")

    def add_number(parent, row, label, key, step, lowest):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        holder = ttk.Frame(parent)
        holder.grid(row=row, column=1, sticky="w", pady=3, padx=(10, 0))
        ttk.Button(
            holder, text="−", style="Step.TButton",
            command=lambda: nudge(key, -step, lowest),
        ).pack(side="left")
        tk.Entry(
            holder, textvariable=values[key], width=6, justify="center",
            font=VALUE, relief="solid", borderwidth=1,
        ).pack(side="left", padx=4, ipady=3)
        ttk.Button(
            holder, text="+", style="Step.TButton",
            command=lambda: nudge(key, step, lowest),
        ).pack(side="left")

    def add_text(parent, row, label, key, width=26):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        tk.Entry(
            parent, textvariable=values[key], width=width, font=VALUE,
            relief="solid", borderwidth=1,
        ).grid(row=row, column=1, sticky="w", pady=3, padx=(10, 0), ipady=3)

    left_column = ttk.Frame(frame)
    left_column.grid(row=2, column=0, columnspan=2, sticky="new")

    build_section = ttk.LabelFrame(
        left_column, text="Build your bin", padding=9, style="Panel.TLabelframe"
    )
    build_section.pack(fill="x")
    add_number(build_section, 0, f"Width X  (units of {BASE_UNIT:.0f} mm)", "x_units", 1.0, MIN_UNITS)
    add_number(build_section, 1, f"Depth Y  (units of {BASE_UNIT:.0f} mm)", "y_units", 1.0, MIN_UNITS)
    add_number(build_section, 2, "Height Z  (mm)", "z", 5.0, 5.0)
    ttk.Label(build_section, text="Insert form").grid(row=3, column=0, sticky="w", pady=3)
    mode_row = ttk.Frame(build_section)
    mode_row.grid(row=3, column=1, sticky="w", padx=(10, 0), pady=3)
    for text, value in (
        ("Fused", "fused"), ("Removable", "separate"), ("8 mm cartridge", "cartridge")
    ):
        ttk.Radiobutton(
            mode_row, text=text, variable=values["mode"], value=value,
            command=lambda: change_mode_action(),
        ).pack(side="left", padx=(0, 8))

    # The scoop and the advanced numbers used to sit in a panel of their own.
    # They are three lines of bin settings, and a second titled box around them
    # cost the interior-support editor below more height than it could spare.
    ttk.Separator(build_section, orient="horizontal").grid(
        row=4, column=0, columnspan=2, sticky="ew", pady=(9, 6)
    )
    ttk.Checkbutton(
        build_section,
        text="Add curved scoop (rises halfway up the front wall)",
        variable=values["scoop"],
    ).grid(row=5, column=0, columnspan=2, sticky="w")
    ttk.Checkbutton(
        build_section, text="Advanced settings",
        variable=show_advanced, command=lambda: toggle_advanced(),
    ).grid(row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))
    advanced = ttk.Frame(build_section)
    advanced.grid(row=7, column=0, columnspan=2, sticky="nw", pady=(5, 0))
    for index, (field_label, key, step, lowest) in enumerate(ADVANCED_FIELDS):
        add_number(advanced, index, field_label, key, step or 0.1, lowest or 0.0)
    axis_row = len(ADVANCED_FIELDS)
    ttk.Label(advanced, text="Connector runs along").grid(
        row=axis_row, column=0, sticky="w", pady=3
    )
    axis_frame = ttk.Frame(advanced)
    axis_frame.grid(row=axis_row, column=1, sticky="w", padx=(10, 0))
    ttk.Radiobutton(
        axis_frame, text="X wall", variable=values["side_axis"], value="x"
    ).pack(side="left")
    ttk.Radiobutton(
        axis_frame, text="Y wall", variable=values["side_axis"], value="y"
    ).pack(side="left", padx=(12, 0))

    def toggle_advanced() -> None:
        if show_advanced.get():
            advanced.grid()
        else:
            advanced.grid_remove()

    toggle_advanced()

    label_section = ttk.LabelFrame(
        left_column, text="Label your bin", padding=9, style="Panel.TLabelframe"
    )
    label_section.pack(fill="x", pady=(10, 0))
    ttk.Label(label_section, text="Label").grid(row=0, column=0, sticky="w", pady=3)
    tk.Entry(
        label_section, textvariable=values["label"], width=21, font=VALUE,
        relief="solid", borderwidth=1,
    ).grid(row=0, column=1, sticky="w", padx=(10, 8), pady=3, ipady=3)
    label_toggle = ttk.Frame(label_section)
    label_toggle.grid(row=0, column=2, sticky="w")
    ttk.Radiobutton(
        label_toggle, text="Bottom", variable=values["label_position"], value="bottom"
    ).pack(side="left")
    ttk.Radiobutton(
        label_toggle, text="Top", variable=values["label_position"], value="top"
    ).pack(side="left", padx=(8, 0))
    add_text(label_section, 1, "Part name", "part", width=21)
    ttk.Label(
        label_section,
        text="Top labels use fixed 5 mm letters on a 7 mm flush rim ledge.",
        style="Note.TLabel",
    ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(3, 0))

    views = ttk.Notebook(frame)
    views.grid(row=2, column=2, sticky="nsew", padx=(24, 0))
    preview_tab = ttk.Frame(views)
    layout_tab = ttk.Frame(views)
    views.add(preview_tab, text="3D preview")
    views.add(layout_tab, text="2D layout")

    preview = tk.Canvas(
        preview_tab, width=PREVIEW_SIZE, height=PREVIEW_SIZE - 40,
        background="white", highlightthickness=1, highlightbackground="#cccccc",
    )
    preview.pack(fill="both", expand=True)

    section_bar = ttk.Frame(preview_tab)
    section_bar.pack(fill="x", pady=(3, 0))
    ttk.Label(section_bar, text="Cut section", style="Note.TLabel").pack(
        side="left", padx=(2, 6)
    )
    section_slider = ttk.Scale(section_bar, from_=0.0, to=1.0, orient="horizontal")
    section_slider.pack(side="left", fill="x", expand=True, padx=(0, 4))

    def on_section_slider(_value=None) -> None:
        section_state["t"] = float(section_slider.get())
        draw_preview()

    def reset_section() -> None:
        section_slider.set(0.0)
        section_state["t"] = 0.0
        draw_preview()

    section_slider.configure(command=on_section_slider)
    ttk.Button(
        section_bar, text="Reset", style="Small.TButton", command=reset_section
    ).pack(side="left")

    layout_canvas = tk.Canvas(
        layout_tab, width=PREVIEW_SIZE, height=PREVIEW_SIZE - 40,
        background="white", highlightthickness=1, highlightbackground="#cccccc",
    )
    layout_canvas.pack(fill="both", expand=True)

    def section_solids(spec: BoxSpec):
        """Solids to slice for the cut-section cap, rebuilt once per design."""
        if preview_cache["section_solids"] is None:
            mode = values["mode"].get()
            shell = build_section_shell(
                spec, mode, values["label"].get(),
                values["label_position"].get(), values["scoop"].get(),
            )
            base_z = base_height(spec, mode)
            parts = []
            plate = insert_plate_solid(spec, mode)
            if plate is not None:
                parts.append(plate)
            for one in features:
                try:
                    parts.extend(
                        build_features(spec, [one], base_z, layout_zone(spec, mode))
                    )
                except Exception:
                    pass
            preview_cache["section_solids"] = (shell, *parts)
        return preview_cache["section_solids"]

    def current_box() -> BoxSpec:
        return BoxSpec(
            x=float(values["x_units"].get()) * BASE_UNIT,
            y=float(values["y_units"].get()) * BASE_UNIT,
            z=float(values["z"].get()),
            wall=float(values["wall"].get()),
            flat_inside=float(values["flat_inside"].get()),
        )

    def current_layout() -> Layout:
        return Layout(tuple(features), values["mode"].get(), EDITOR_SNAP)

    def draw_preview(_event=None) -> None:
        preview.delete("all")
        width, height = canvas_extent(preview)
        spec = preview_cache["spec"]
        geometry = preview_cache["geometry"]
        if spec is None or geometry is None:
            preview.create_text(
                width / 2, height / 2,
                text="-", fill="#999999", font=("Segoe UI", 11),
            )
            return

        scene = project_preview(geometry, camera["value"])
        to_canvas = preview_transform(
            spec, size=width, height=height, camera=camera["value"]
        )
        faces = scene["faces"]
        cut = section_state["t"]
        if cut > 1e-4:
            half_y = spec.outside_extent[1] / 2.0 + 0.5
            y_cut = -half_y + cut * (2.0 * half_y)
            faces = clip_faces_beyond_y(faces, y_cut)
            try:
                faces = faces + section_cap_faces(section_solids(spec), y_cut)
            except Exception:
                pass
        for points, kind in faces:
            colour = FACE_COLOURS.get(kind, "#d99b62")
            outline = "" if kind in ("label", "label_hole", "section_hole") else colour
            preview.create_polygon(
                [c for point in points for c in to_canvas(point)],
                fill=colour, outline=outline,
            )

        dimension = ("Segoe UI", 11, "bold")
        preview.create_text(
            width / 2, height - 12,
            text=scene["x_text"], font=dimension, fill="#333333",
        )
        preview.create_text(
            14, height / 2, text=scene["y_text"],
            font=dimension, fill="#333333", angle=90,
        )
        preview.create_text(
            width - 10, 14, text=scene["z_text"],
            font=("Segoe UI", 10), fill="#666666", anchor="ne",
        )
        if not scene["fits"]:
            preview.create_text(
                width / 2, 28, text="label will not fit",
                fill="#c0392b", font=("Segoe UI", 10, "bold"),
            )
        if scene["feature_errors"]:
            preview.create_text(
                width / 2,
                44 if not scene["fits"] else 28,
                text="selected support settings are invalid",
                fill="#c0392b",
                font=("Segoe UI", 9, "bold"),
            )
        preview.create_text(
            width / 2, 12,
            text="drag to rotate  •  wheel to zoom  •  slider below cuts a section  •  double-click resets",
            fill="#777777", font=("Segoe UI", 8),
        )

    def draw_layout(_event=None) -> None:
        layout_canvas.delete("all")
        width, height = canvas_extent(layout_canvas)
        try:
            spec = current_box()
            bounds = layout_zone(spec, values["mode"].get())
        except Exception:
            layout_canvas.create_text(
                width / 2, height / 2, text="-", fill="#999999"
            )
            return
        scale = min(
            (width - 2 * PREVIEW_PAD) / bounds.width,
            (height - 2 * PREVIEW_PAD) / bounds.depth,
        )

        def point(x: float, y: float) -> tuple[float, float]:
            return width / 2 + x * scale, height / 2 - y * scale

        x0, y1 = point(bounds.x0, bounds.y0)
        x1, y0 = point(bounds.x1, bounds.y1)
        layout_canvas.create_rectangle(x0, y0, x1, y1, fill="#f4f7f8", outline="#46616e", width=2)
        pitch = CARTRIDGE_PITCH if values["mode"].get() == "cartridge" else 5.0
        gx = math.ceil(bounds.x0 / pitch) * pitch
        while gx < bounds.x1:
            px, _ = point(gx, 0.0)
            layout_canvas.create_line(px, y0, px, y1, fill="#dce4e8")
            gx += pitch
        gy = math.ceil(bounds.y0 / pitch) * pitch
        while gy < bounds.y1:
            _, py = point(0.0, gy)
            layout_canvas.create_line(x0, py, x1, py, fill="#dce4e8")
            gy += pitch

        collision_indexes = set(
            preview_cache["geometry"].get("invalid_feature_indexes", ())
            if preview_cache["geometry"] is not None else ()
        )
        customization_zones = _customization_zones(
            spec,
            values["label"].get(),
            values["label_position"].get(),
            values["scoop"].get(),
            values["mode"].get(),
        )
        for name, zone in customization_zones:
            ax, ay = point(zone.x0, zone.y1)
            bx, by = point(zone.x1, zone.y0)
            layout_canvas.create_rectangle(
                ax, ay, bx, by, fill="#dbe9ee", outline="#6f929f",
                stipple="gray25",
            )
            layout_canvas.create_text(
                (ax + bx) / 2, (ay + by) / 2,
                text=name.title(), fill="#45636e", font=("Segoe UI", 8, "bold"),
            )
        for index, one in enumerate(features):
            if (one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
                    or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6):
                collision_indexes.add(index)
            for other_index, other in enumerate(features[index + 1:], index + 1):
                if one.zone.overlaps(other.zone, MIN_FEATURE_GAP):
                    collision_indexes.update((index, other_index))
            if any(
                one.zone.overlaps(zone, MIN_FEATURE_GAP)
                for _name, zone in customization_zones
            ):
                collision_indexes.add(index)
        colours = {
            "cradle": "#efb36f", "nest": "#ee9a68", "bore": "#7bc49a",
            "post": "#67b9b4", "divider": "#aa94d1", "pocket": "#df879a",
            "slot": "#dfc45e",
        }
        for index, one in enumerate(features):
            ax, ay = point(one.zone.x0, one.zone.y1)
            bx, by = point(one.zone.x1, one.zone.y0)
            chosen = selected["index"] == index
            outline = "#c0392b" if index in collision_indexes else ("#1666a8" if chosen else "#526a73")
            layout_canvas.create_rectangle(
                ax, ay, bx, by, fill=colours.get(one.kind, "#cccccc"),
                outline=outline, width=3 if chosen else 1,
                tags=(f"feature_{index}", "feature"),
            )
            layout_canvas.create_text(
                (ax + bx) / 2, (ay + by) / 2,
                text=(
                    f"{support_display(one.kind).split(' —', 1)[0]}\n"
                    f"{one.item.name if one.item else ''}"
                ).strip(),
                width=max(10, abs(bx - ax) - 4), font=("Segoe UI", 8),
                tags=(f"feature_{index}", "feature"),
            )
            if chosen:
                layout_canvas.create_rectangle(
                    bx - 5, by - 5, bx + 5, by + 5, fill="#1666a8", outline="white",
                    tags=("resize_handle",),
                )
        tidy = clean_label(values["label"].get())
        if tidy:
            try:
                if values["label_position"].get() == "top":
                    outline = top_label_outline(spec, tidy)
                    minx, miny, maxx, maxy = outline.bounds
                    lx, ly = point((minx + maxx) / 2.0, (miny + maxy) / 2.0)
                    angle = 0
                else:
                    placement = label_placement(
                        spec, tidy,
                        _label_obstacles(spec, current_layout(), values["scoop"].get()),
                    )
                    lx, ly = point(placement.x, placement.y)
                    angle = 90 if placement.rotated else 0
                layout_canvas.create_text(
                    lx, ly, text=tidy, fill="#b83934", font=("Segoe UI", 9, "bold"),
                    angle=angle,
                )
            except ValueError:
                layout_canvas.create_text(
                    width / 2, 13, text="label will not fit",
                    fill="#c0392b", font=("Segoe UI", 9, "bold"),
                )
        inside_x, inside_y = spec.usable_inside
        layout_canvas.create_text(
            width / 2, height - 12,
            text=f"{spec.x:g}mm ({math.floor(inside_x):g} inside)",
            font=("Segoe UI", 9, "bold"), fill="#333333",
        )
        layout_canvas.create_text(
            13, height / 2,
            text=f"{spec.y:g}mm ({math.floor(inside_y):g} inside)", angle=90,
            font=("Segoe UI", 9, "bold"), fill="#333333",
        )
        layout_canvas.create_text(
            width - 8, 8, text=f"{spec.z:g}mm tall", anchor="ne",
            font=("Segoe UI", 8), fill="#666666",
        )
        # transient interaction state: the canvas centre moves when it resizes
        layout_canvas._world = (point, scale, bounds, width, height)

    def refresh_translation(*_args) -> None:
        preview_cache["section_solids"] = None
        try:
            spec = current_box()
            preview_cache["spec"] = spec
            preview_cache["geometry"] = preview_geometry(
                spec, values["label"].get(), features, values["mode"].get(),
                values["label_position"].get(), values["scoop"].get(),
            )
        except Exception:
            preview_cache["spec"] = preview_cache["geometry"] = None
            draw_preview()
            draw_layout()
            on_after_refresh["fn"]()
            return
        draw_preview()
        draw_layout()
        on_after_refresh["fn"]()

    def change_mode_action() -> None:
        """Move existing supports onto the selected mode's coordinate grid."""
        target = values["mode"].get()
        previous = mode_state["value"]
        if target == previous:
            refresh_translation()
            return
        try:
            spec = current_box()
            converted = convert_layout_mode(spec, features, target)
        except Exception as error:
            values["mode"].set(previous)
            messagebox.showerror("Could not change insert form", str(error))
            refresh_translation()
            return
        features[:] = converted.features
        mode_state["value"] = target
        sync_feature_fields()
        refresh_translation()

    def preview_press(event) -> None:
        camera["drag"] = (event.x, event.y, camera["value"])

    def preview_drag(event) -> None:
        if camera["drag"] is None:
            return
        start_x, start_y, start = camera["drag"]
        camera["value"] = PreviewCamera(
            start.yaw + (event.x - start_x) * 0.7,
            start.elevation - (event.y - start_y) * 0.5,
            start.zoom,
        ).normalized()
        draw_preview()

    def preview_zoom(event) -> None:
        direction = 1 if getattr(event, "delta", 0) > 0 or getattr(event, "num", 0) == 4 else -1
        old = camera["value"]
        camera["value"] = replace(old, zoom=old.zoom * (1.12 if direction > 0 else 1 / 1.12)).normalized()
        draw_preview()

    def preview_reset(_event=None) -> None:
        camera["value"] = PreviewCamera()
        draw_preview()

    preview.bind("<Configure>", draw_preview)
    layout_canvas.bind("<Configure>", draw_layout)
    preview.bind("<ButtonPress-1>", preview_press)
    preview.bind("<B1-Motion>", preview_drag)
    preview.bind("<ButtonRelease-1>", lambda _event: camera.update(drag=None))
    preview.bind("<MouseWheel>", preview_zoom)
    preview.bind("<Button-4>", preview_zoom)
    preview.bind("<Button-5>", preview_zoom)
    preview.bind("<Double-Button-1>", preview_reset)

    for key in (
        "x_units", "y_units", "z", "wall", "flat_inside", "label",
        "label_position", "scoop",
    ):
        values[key].trace_add("write", refresh_translation)

    # --- insert layout editor -------------------------------------------------
    editor = ttk.LabelFrame(
        frame,
        text="Interior supports — drag to move, drag the blue corner to resize (1 mm snap)",
        padding=8,
        style="Panel.TLabelframe",
    )
    editor.grid(row=3, column=0, columnspan=3, sticky="nsew", pady=(14, 0))
    editor.columnconfigure(0, weight=1)
    editor.rowconfigure(4, weight=1)

    kind_state = {"value": PART_KINDS[0][0]}
    opt_vars: dict[str, dict[str, "tk.StringVar"]] = {}
    palette_cells: dict[str, tk.Widget] = {}
    callout_widgets: list = []
    diagram_state: dict[str, object] = {"kind": None, "size": None}

    tools_row = ttk.Frame(editor)
    tools_row.grid(row=0, column=0, sticky="ew")
    ttk.Label(tools_row, text="1.  Pick a shape").pack(side="left")

    palette_row = ttk.Frame(editor)
    palette_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
    for kind, title, _blurb, _flags, _fields in PART_KINDS:
        cell = tk.Frame(palette_row, bd=2, relief="groove",
                        highlightthickness=0, padx=4, pady=3)
        cell.pack(side="left", padx=(0, 5))
        icon = tk.Canvas(cell, width=34, height=34, highlightthickness=0)
        icon.pack()
        draw_part_icon(icon, kind)
        name = ttk.Label(cell, text=title, font=("Segoe UI", 8))
        name.pack()
        palette_cells[kind] = cell
        for widget in (cell, icon, name):
            widget.bind("<Button-1>", lambda _e, k=kind: select_kind(k))

    blurb_label = ttk.Label(editor, text="", style="Note.TLabel",
                            wraplength=920, justify="left")
    blurb_label.grid(row=2, column=0, sticky="ew", pady=(4, 0))

    params_row = ttk.Frame(editor)
    params_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Label(
        params_row, text="2.  Set parameters — each one points at the part it changes"
    ).pack(side="left")
    edit_note = ttk.Label(params_row, text="", style="Warn.TLabel")
    edit_note.pack(side="left", padx=(12, 0))

    def say_edit(message: str = "") -> None:
        """Why the part on screen is not the numbers in the fields.

        A parameter can be refused for a good reason - a recess deeper than the
        block holding it, a holder too big for its zone - and the old silence
        was indistinguishable from the value having no effect at all.
        """
        edit_note.configure(text=message)

    body = ttk.Frame(editor)
    body.grid(row=4, column=0, sticky="nsew", pady=(4, 0))
    body.columnconfigure(0, weight=3)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)

    diagram = tk.Canvas(
        body, width=DIAGRAM_WIDTH, height=DIAGRAM_HEIGHT, background="white",
        highlightthickness=1, highlightbackground="#cccccc",
    )
    diagram.grid(row=0, column=0, sticky="nsew")

    side_panel = ttk.Frame(body)
    side_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
    side_panel.rowconfigure(1, weight=1)

    parts_title = ttk.Label(side_panel, text="Placed parts")
    parts_title.grid(row=0, column=0, sticky="w")

    def say_parts(message: str = "") -> None:
        """Answer on the list's own heading, then fall quiet again."""
        parts_title.configure(text=message or "Placed parts")
        if message:
            later(2500, lambda: parts_title.configure(text="Placed parts"))
    parts_row = ttk.Frame(side_panel)
    parts_row.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
    parts_list = tk.Listbox(
        parts_row, height=6, width=32, exportselection=False, activestyle="dotbox",
        font=("Segoe UI", 9),
    )
    parts_list.pack(side="left", fill="both", expand=True)
    parts_scroll = ttk.Scrollbar(
        parts_row, orient="vertical", command=parts_list.yview
    )
    parts_scroll.pack(side="left", fill="y")
    parts_list.configure(yscrollcommand=parts_scroll.set)

    def describe_feature(index: int, one: Feature) -> str:
        name = PART_KIND_INFO.get(one.kind, (one.kind.title(),))[0]
        cx, cy = one.zone.centre
        held = ""
        if one.item is not None:
            shaft = one.item.segments[0]
            held = f"  ·  tool {shaft.length:g} x {shaft.diameter:g} mm"
        return (
            f"{index + 1}.  {name}   "
            f"{one.zone.width:g} x {one.zone.depth:g} mm  @ ({cx:g}, {cy:g}){held}"
        )

    def refresh_parts_list() -> None:
        parts_list.delete(0, "end")
        for index, one in enumerate(features):
            parts_list.insert("end", describe_feature(index, one))
        target = selected["index"]
        if target is not None and 0 <= target < len(features):
            parts_list.selection_clear(0, "end")
            parts_list.selection_set(target)
            parts_list.see(target)

    def on_parts_select(_event=None) -> None:
        picks = parts_list.curselection()
        if not picks:
            return
        selected["index"] = int(picks[0])
        sync_feature_fields()
        draw_layout()

    parts_list.bind("<<ListboxSelected>>", on_parts_select)
    on_after_refresh["fn"] = refresh_parts_list

    def sync_feature_fields() -> None:
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
            return
        syncing["on"] = True
        try:
            _sync_feature_fields(features[index])
        finally:
            syncing["on"] = False

    def _sync_feature_fields(one: Feature) -> None:
        cx, cy = one.zone.centre
        select_kind(one.kind, prime=False)
        if one.item is not None:
            shaft = one.item.segments[0]
            values["item_length"].set(f"{shaft.length:g}")
            values["item_thickness"].set(f"{shaft.diameter:g}")
            if len(one.item.segments) > 1:
                handle = one.item.segments[1]
                values["item_handle_length"].set(f"{handle.length:g}")
                values["item_handle_thickness"].set(f"{handle.diameter:g}")
            else:
                values["item_handle_length"].set("")
                values["item_handle_thickness"].set("")
            values["item_profile"].set(one.item.profile)
            values["item_clearance"].set(f"{one.item.clearance:g}")
        values["feature_along"].set(one.along)
        values["feature_count"].set("auto" if one.count is None else str(one.count))
        values["feature_x"].set(f"{cx:g}")
        values["feature_y"].set(f"{cy:g}")
        values["feature_width"].set(f"{one.zone.width:g}")
        values["feature_depth"].set(f"{one.zone.depth:g}")
        # Show the number the builder will really use, not a blank standing in
        # for "work it out yourself" - a parameter you cannot see is one you
        # cannot tell you have changed.
        try:
            mode = values["mode"].get()
            spec = current_box()
            shown = resolved_options(spec, one, base_height(spec, mode))
        except Exception:
            shown = dict(one.options)
        for _label, opt, _default in PART_KIND_INFO[one.kind][3]:
            current = shown.get(opt, one.options.get(opt))
            opt_vars[one.kind][opt].set("" if current is None else f"{current:g}")

    def editor_item() -> Item:
        """Describe the stored tool from the plain length/thickness fields."""
        segments = [Segment(
            float(values["item_length"].get()),
            float(values["item_thickness"].get()),
        )]
        handle_length = values["item_handle_length"].get().strip()
        handle_thickness = values["item_handle_thickness"].get().strip()
        if handle_length and handle_thickness:
            segments.append(Segment(float(handle_length), float(handle_thickness)))
        return Item(
            "Tool", tuple(segments), values["item_profile"].get(),
            float(values["item_clearance"].get()),
        )

    def first_open_position(one: Feature, spec: BoxSpec, mode: str) -> Feature:
        bounds = layout_zone(spec, mode)
        pitch = CARTRIDGE_PITCH if mode == "cartridge" else EDITOR_SNAP
        candidates = []
        x = bounds.x0 + one.zone.width / 2.0
        while x <= bounds.x1 - one.zone.width / 2.0 + 1e-9:
            y = bounds.y0 + one.zone.depth / 2.0
            while y <= bounds.y1 - one.zone.depth / 2.0 + 1e-9:
                candidates.append((x, y))
                y += pitch
            x += pitch
        candidates.sort(key=lambda p: p[0] ** 2 + p[1] ** 2)
        reserved = _customization_zones(
            spec, values["label"].get(), values["label_position"].get(),
            values["scoop"].get(), values["mode"].get(),
        )
        for centre in candidates:
            placed = moved_feature(one, spec, centre, mode)
            if all(
                not placed.zone.overlaps(other.zone, MIN_FEATURE_GAP)
                for other in features
            ) and all(
                not placed.zone.overlaps(zone, MIN_FEATURE_GAP)
                for _name, zone in reserved
            ):
                return placed
        raise ValueError("there is no open floor area large enough for that holder")

    def _num(text: str, fallback: float) -> float:
        try:
            return float(str(text).strip())
        except (TypeError, ValueError):
            return fallback

    def build_editor_feature(spec: BoxSpec, kind: str, mode: str) -> Feature:
        """Turn the palette selection plus the parameter fields into a Feature."""
        _title, _blurb, flags, fields = PART_KIND_INFO[kind]
        along = values["feature_along"].get() if flags["along"] else "x"
        item = editor_item() if flags["item"] else None
        one = default_feature(spec, kind, along=along, mode=mode, item=item)
        if flags["qty"]:
            qty = values["feature_count"].get().strip().lower()
            one = replace(one, count=None if qty in {"", "auto"} else int(qty))
        options = dict(one.options)
        for _label, opt, _default in fields:
            text = opt_vars[kind][opt].get().strip()
            if text:
                options[opt] = float(text)
        one = replace(one, options=options)
        if flags["size"]:
            one = resized_feature(
                one, spec,
                (_num(values["feature_width"].get(), one.zone.width),
                 _num(values["feature_depth"].get(), one.zone.depth)),
                mode,
            )
        return one

    def add_feature_action() -> None:
        try:
            spec = current_box()
            one = build_editor_feature(spec, kind_state["value"], values["mode"].get())
            one = first_open_position(one, spec, values["mode"].get())
            features.append(one)
            selected["index"] = len(features) - 1
            sync_feature_fields()
            refresh_translation()
        except Exception as error:
            messagebox.showerror("Could not add part", str(error))

    def target_index() -> int | None:
        """The placed part the edit buttons act on.

        ``selected`` is the editor's own record, but the highlighted row in the
        parts list is what the user is looking at.  When the two drift apart -
        a stray click on empty floor in the 2D layout clears one and not the
        other - trust the highlight, because that is what the button appeared
        to be aimed at.  Doing nothing at all, silently, is the one answer that
        cannot be right.
        """
        index = selected["index"]
        if index is None:
            picks = parts_list.curselection()
            index = int(picks[0]) if picks else None
        if index is None or not 0 <= index < len(features):
            say_parts("Pick a part in the list first")
            return None
        selected["index"] = index
        return index

    def delete_feature_action() -> None:
        index = target_index()
        if index is None:
            return
        del features[index]
        selected["index"] = min(index, len(features) - 1) if features else None
        # The list and the preview have to catch up even if re-filling the
        # parameter fields trips over the part that took its place; otherwise a
        # part really is deleted and nothing on screen says so.
        try:
            sync_feature_fields()
        finally:
            refresh_translation()

    def apply_feature_action() -> None:
        index = target_index()
        if index is None:
            return
        try:
            spec = current_box()
            mode = values["mode"].get()
            cx, cy = features[index].zone.centre
            one = build_editor_feature(spec, kind_state["value"], mode)
            one = moved_feature(
                one, spec,
                (_num(values["feature_x"].get(), cx), _num(values["feature_y"].get(), cy)),
                mode,
            )
            features[index] = one
            say_edit()
            sync_feature_fields()
            refresh_translation()
        except Exception as error:
            say_edit(str(error))
            messagebox.showerror("Could not update part", str(error))

    def rotate_feature_action() -> None:
        index = target_index()
        if index is None:
            return
        try:
            one = features[index]
            one = replace(one, along="y" if one.along == "x" else "x")
            one = resized_feature(
                one, current_box(), (one.zone.depth, one.zone.width), values["mode"].get()
            )
            features[index] = one
            sync_feature_fields()
            refresh_translation()
        except Exception as error:
            messagebox.showerror("Could not rotate holder", str(error))

    live_edit_job = {"id": None}

    def live_feature_edit(*_args) -> None:
        """Queue a rebuild of the selected part while its fields are edited."""
        if syncing["on"]:
            return
        cancel_later(live_edit_job["id"])
        # Rebuilding a holder is real geometry work, so wait out the rest of
        # the number rather than doing it once per keystroke.
        live_edit_job["id"] = later(180, apply_live_edit)

    def apply_live_edit() -> None:
        """Re-make the selected part from the fields as they now stand.

        "Update selected" stays the loud version: it explains why a value was
        refused.  Typing needs the quiet one - half-finished numbers are
        rejected on nearly every keystroke, and a dialog for each would be
        unusable - so a value that does not build yet simply leaves the last
        good part standing.
        """
        live_edit_job["id"] = None
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
            return
        # Picking a different shape from the palette is the start of a new
        # part, not an instruction to turn this one into that; only the
        # matching kind's own fields edit it in place.
        if kind_state["value"] != features[index].kind:
            return
        try:
            spec = current_box()
            mode = values["mode"].get()
            cx, cy = features[index].zone.centre
            one = build_editor_feature(spec, kind_state["value"], mode)
            one = moved_feature(
                one, spec,
                (_num(values["feature_x"].get(), cx),
                 _num(values["feature_y"].get(), cy)),
                mode,
            )
            rest = [f for at, f in enumerate(features) if at != index]
            Layout((*rest, one), mode, EDITOR_SNAP).validate(spec)
            build_features(spec, [one], base_height(spec, mode), layout_zone(spec, mode))
        except Exception as error:
            say_edit(str(error))
            return
        say_edit()
        features[index] = one
        refresh_translation()

    for key in (
        "feature_x", "feature_y", "feature_width", "feature_depth",
        "feature_count", "feature_along", "item_length", "item_thickness",
        "item_handle_length", "item_handle_thickness", "item_profile",
        "item_clearance",
    ):
        values[key].trace_add("write", live_feature_edit)

    centre_row = ttk.Frame(side_panel)
    centre_row.grid(row=2, column=0, sticky="w", pady=(8, 0))
    ttk.Label(centre_row, text="Center X").pack(side="left", padx=(0, 3))
    ttk.Entry(centre_row, textvariable=values["feature_x"], width=6).pack(side="left")
    ttk.Label(centre_row, text="Y").pack(side="left", padx=(8, 3))
    ttk.Entry(centre_row, textvariable=values["feature_y"], width=6).pack(side="left")

    add_row = ttk.Frame(side_panel)
    add_row.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Button(add_row, text="3.  Add part", command=add_feature_action).pack(side="left")
    ttk.Button(add_row, text="Update selected", command=apply_feature_action).pack(
        side="left", padx=(6, 0)
    )
    edit_row = ttk.Frame(side_panel)
    edit_row.grid(row=4, column=0, sticky="ew", pady=(5, 0))
    ttk.Button(edit_row, text="Rotate", style="Small.TButton",
               command=rotate_feature_action).pack(side="left")
    ttk.Button(edit_row, text="Delete", style="Small.TButton",
               command=delete_feature_action).pack(side="left", padx=(6, 0))

    def ensure_opt_vars(kind: str) -> dict:
        bucket = opt_vars.setdefault(kind, {})
        for _label, opt, default in PART_KIND_INFO[kind][3]:
            if opt not in bucket:
                var = tk.StringVar(value=default)
                var.trace_add("write", live_feature_edit)
                bucket[opt] = var
        return bucket

    def callout_widget(kind: str, key: str, label: str, control: str):
        """One parameter as a small tag that can be pinned onto the diagram."""
        holder = ttk.Frame(diagram, style="Callout.TFrame", padding=3)
        ttk.Label(holder, text=label, style="Callout.TLabel").pack(anchor="w")
        if control == "axis":
            axes = ttk.Frame(holder, style="Callout.TFrame")
            axes.pack(anchor="w")
            for text, value in (("X", "x"), ("Y", "y")):
                ttk.Radiobutton(
                    axes, text=text, value=value, style="Callout.TRadiobutton",
                    variable=values["feature_along"],
                ).pack(side="left")
        elif control == "choice":
            ttk.Combobox(
                holder, textvariable=values["item_profile"], width=7,
                values=("round", "hex", "square"), state="readonly",
            ).pack(anchor="w")
        else:
            var = ensure_opt_vars(kind)[key] if control == "option" else values[key]
            ttk.Entry(holder, textvariable=var, width=7).pack(anchor="w")
        return holder

    drawing_diagram = {"on": False, "again": False}

    def draw_diagram() -> None:
        """Sketch the selected shape and pin every parameter beside it.

        Measuring a tag needs ``update_idletasks``, which runs whatever events
        are pending - including the canvas ``<Configure>`` that asks for this
        very redraw.  Re-entering half way through leaves the outer pass adding
        leaders to a canvas the inner pass has already cleared, and touching
        tag widgets it has already destroyed, so the nested call is deferred to
        a second pass instead.
        """
        if drawing_diagram["on"]:
            drawing_diagram["again"] = True
            return
        drawing_diagram["on"] = True
        try:
            # The dropped call is usually a resize, and dropping it outright
            # would leave the tags laid out for the size before it, so run the
            # draw again rather than losing it.
            while True:
                drawing_diagram["again"] = False
                _draw_diagram()
                if not drawing_diagram["again"]:
                    break
        finally:
            drawing_diagram["on"] = False

    def _draw_diagram() -> None:
        for widget in callout_widgets:
            widget.destroy()
        callout_widgets.clear()
        diagram.delete("all")
        width, height = canvas_extent(diagram, DIAGRAM_WIDTH)
        if diagram.winfo_height() > 60:
            height = diagram.winfo_height()
        kind = kind_state["value"]
        diagram_state["kind"] = kind
        # The part is drawn as large as the panel allows without going so wide
        # that it flattens, and sits in the middle with the tags gathered
        # around it - a tag right out on the window edge is a long way from
        # the feature it is talking about.
        column = min(150.0, width * 0.22)
        band = 50.0                      # a tag row needs this much whatever
        sketch_h = max(56.0, height - 2 * band)
        sketch_w = max(80.0, min(width - 2 * column, sketch_h * DIAGRAM_ASPECT))
        middle = width / 2.0
        area = (middle - sketch_w / 2, band, middle + sketch_w / 2, height - band)
        project = draw_part_diagram(diagram, kind, area)
        anchors = PART_DIAGRAM_ANCHORS.get(kind, {})
        sides: dict[str, list] = {"top": [], "bottom": [], "left": [], "right": []}
        for key, label, control in diagram_callouts(kind):
            spot = anchors.get(key, (0.5, 0.05, 0.0, "bottom"))
            sides[spot[3]].append((key, label, control, project(spot[:3])))
        for side, pinned in sides.items():
            if not pinned:
                continue
            flat = side in ("top", "bottom")
            # Tags are laid out in their targets' own order along the row or
            # column: ``spread_callouts`` walks the list once and needs it
            # sorted, and keeping the two sequences the same is also what stops
            # neighbouring leaders from swapping over each other.
            pinned.sort(key=lambda row: row[3][0] if flat else row[3][1])
            made = []
            for key, label, control, target in pinned:
                tag = callout_widget(kind, key, label, control)
                tag.update_idletasks()
                made.append(
                    (key, tag, tag.winfo_reqwidth(), tag.winfo_reqheight(), target)
                )
            if flat:
                spots = spread_callouts(
                    [row[4][0] for row in made], [row[2] for row in made],
                    8.0, 2.0, width - 2.0,
                )
                row_y = band / 2 if side == "top" else height - band / 2
            else:
                spots = spread_callouts(
                    [row[4][1] for row in made], [row[3] for row in made],
                    6.0, 2.0, height - 2.0,
                )
            for (key, tag, tag_width, tag_height, target), spot in zip(made, spots):
                if flat:
                    diagram.create_window(spot, row_y, window=tag, anchor="center")
                    leader = (
                        spot,
                        row_y + tag_height / 2 if side == "top"
                        else row_y - tag_height / 2,
                    )
                elif side == "left":
                    edge = max(tag_width + 2.0, area[0] - 12.0)
                    diagram.create_window(edge, spot, window=tag, anchor="e")
                    leader = (edge, spot)
                else:
                    edge = min(width - tag_width - 2.0, area[2] + 12.0)
                    diagram.create_window(edge, spot, window=tag, anchor="w")
                    leader = (edge, spot)
                diagram.create_line(
                    leader[0], leader[1], target[0], target[1],
                    fill=DIAGRAM_TONE["leader"], tags=("leader", f"leader_{key}"),
                )
                diagram.create_oval(
                    target[0] - 2.5, target[1] - 2.5, target[0] + 2.5, target[1] + 2.5,
                    fill=DIAGRAM_TONE["leader"], outline="",
                )
                callout_widgets.append(tag)

    def on_diagram_resize(event) -> None:
        if diagram_state["size"] == (event.width, event.height):
            return
        diagram_state["size"] = (event.width, event.height)
        draw_diagram()

    diagram.bind("<Configure>", on_diagram_resize)

    def select_kind(kind: str, prime: bool = True) -> None:
        if kind not in PART_KIND_INFO:
            return
        kind_state["value"] = kind
        _title, blurb, flags, _fields = PART_KIND_INFO[kind]
        blurb_label.configure(text=blurb)
        for name, cell in palette_cells.items():
            active = name == kind
            cell.configure(relief="solid" if active else "groove",
                           bg="#cfe6f0" if active else "#f0f0f0")
        ensure_opt_vars(kind)
        # Rebuilding the tags steals focus, so only do it when the drawing
        # genuinely has to change - dragging a part around re-syncs the fields
        # many times a second and the entries follow their variables anyway.
        if diagram_state["kind"] != kind:
            draw_diagram()
        if prime:
            try:
                base = default_feature(
                    current_box(), kind,
                    along=values["feature_along"].get() if flags["along"] else "x",
                    mode=values["mode"].get(),
                    item=editor_item() if flags["item"] else None,
                )
                if flags["size"]:
                    values["feature_width"].set(f"{base.zone.width:g}")
                    values["feature_depth"].set(f"{base.zone.depth:g}")
                values["feature_count"].set("auto" if base.count is None else str(base.count))
                # Show what this shape would actually be built with. A blank
                # box hides the number the builder is going to use anyway, and
                # there is nothing to type over.
                index = selected["index"]
                editing = (
                    index is not None and 0 <= index < len(features)
                    and features[index].kind == kind
                )
                if not editing:
                    spec = current_box()
                    shown = resolved_options(
                        spec, base, base_height(spec, values["mode"].get())
                    )
                    for _label, opt, _default in PART_KIND_INFO[kind][3]:
                        if opt in shown:
                            opt_vars[kind][opt].set(f"{shown[opt]:g}")
            except Exception:
                pass

    select_kind(kind_state["value"])

    layout_drag = {"mode": None, "index": None, "offset": (0.0, 0.0)}

    def canvas_world(event) -> tuple[float, float]:
        _point, scale, _bounds, width, height = layout_canvas._world
        return ((event.x - width / 2.0) / scale,
                (height / 2.0 - event.y) / scale)

    def layout_press(event) -> None:
        tags = layout_canvas.gettags("current")
        index = None
        for tag in tags:
            if tag.startswith("feature_"):
                index = int(tag.split("_", 1)[1])
                break
        if "resize_handle" in tags:
            index = selected["index"]
            layout_drag["mode"] = "resize"
        elif index is not None:
            selected["index"] = index
            layout_drag["mode"] = "move"
        else:
            selected["index"] = None
            layout_drag["mode"] = None
        layout_drag["index"] = selected["index"]
        if selected["index"] is not None:
            wx, wy = canvas_world(event)
            cx, cy = features[selected["index"]].zone.centre
            layout_drag["offset"] = (cx - wx, cy - wy)
        sync_feature_fields()
        draw_layout()
        refresh_parts_list()

    def layout_motion(event) -> None:
        index = layout_drag["index"]
        if index is None or not 0 <= index < len(features):
            return
        try:
            wx, wy = canvas_world(event)
            one = features[index]
            if layout_drag["mode"] == "resize":
                cx, cy = one.zone.centre
                one = resized_feature(
                    one, current_box(),
                    (max(EDITOR_SNAP, 2 * abs(wx - cx)),
                     max(EDITOR_SNAP, 2 * abs(wy - cy))),
                    values["mode"].get(),
                )
            else:
                ox, oy = layout_drag["offset"]
                one = moved_feature(
                    one, current_box(), (wx + ox, wy + oy), values["mode"].get()
                )
            features[index] = one
            sync_feature_fields()
            refresh_translation()
        except ValueError:
            pass

    layout_canvas.bind("<ButtonPress-1>", layout_press)
    layout_canvas.bind("<B1-Motion>", layout_motion)
    layout_canvas.bind("<ButtonRelease-1>", lambda _event: layout_drag.update(mode=None))
    root.bind("<Delete>", lambda _event: delete_feature_action())

    def save_design_action() -> None:
        try:
            spec = current_box()
            layout = current_layout()
            layout.validate(spec)
            validate_customization_clearance(
                spec, layout.features, values["label"].get(),
                values["label_position"].get(), values["scoop"].get(), layout.mode,
            )
            path = filedialog.asksaveasfilename(
                defaultextension=".wavefinity.json",
                filetypes=(("Wavefinity layout", "*.wavefinity.json"), ("JSON", "*.json")),
            )
            if path:
                Path(path).write_text(
                    json.dumps(design_to_dict(
                        spec, layout, values["label"].get(),
                        values["part"].get(),
                        values["label_position"].get(),
                        values["scoop"].get(),
                    ), indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception as error:
            messagebox.showerror("Could not save layout", str(error))

    def apply_design_data(data: dict) -> None:
        box, loaded, label, part, loaded_label_location, loaded_scoop = design_from_dict(data)
        features[:] = loaded.features
        selected["index"] = None
        values["x_units"].set(f"{box.x / BASE_UNIT:g}")
        values["y_units"].set(f"{box.y / BASE_UNIT:g}")
        values["z"].set(f"{box.z:g}")
        values["wall"].set(f"{box.wall:g}")
        values["flat_inside"].set(f"{box.flat_inside:g}")
        values["label"].set(label)
        values["label_position"].set(loaded_label_location)
        values["scoop"].set(loaded_scoop)
        values["part"].set(part)
        values["mode"].set(loaded.mode)
        mode_state["value"] = loaded.mode
        refresh_translation()

    def open_design_action() -> None:
        try:
            path = filedialog.askopenfilename(
                filetypes=(("Wavefinity layout", "*.wavefinity.json"), ("JSON", "*.json"))
            )
            if not path:
                return
            apply_design_data(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as error:
            messagebox.showerror("Could not open layout", str(error))

    def reload_code_action() -> None:
        """Restart the process so edited modules take effect, keeping the design."""
        resume = APP_DIR / ".wavefinity_resume.json"
        try:
            resume.write_text(
                json.dumps(design_to_dict(
                    current_box(), current_layout(), values["label"].get(),
                    values["part"].get(), values["label_position"].get(),
                    values["scoop"].get(),
                )),
                encoding="utf-8",
            )
            os.environ[RESUME_ENV] = str(resume)
        except Exception:
            os.environ.pop(RESUME_ENV, None)
        root.destroy()
        os.execv(sys.executable, [sys.executable, *sys.argv])

    ttk.Button(
        frame, text="↻ Reload code", style="Small.TButton",
        command=reload_code_action,
    ).grid(row=0, column=2, sticky="e")

    ttk.Button(tools_row, text="Open layout", command=open_design_action).pack(side="right")
    ttk.Button(tools_row, text="Save layout", command=save_design_action).pack(side="right", padx=(0, 6))

    resume_file = os.environ.pop(RESUME_ENV, None)
    if resume_file:
        try:
            resume_path = Path(resume_file)
            apply_design_data(json.loads(resume_path.read_text(encoding="utf-8")))
            resume_path.unlink()
        except Exception:
            refresh_translation()
    else:
        refresh_translation()

    # --- output folder --------------------------------------------------------
    out_row = ttk.Frame(frame)
    out_row.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 0))
    ttk.Label(out_row, text="Output folder").pack(side="left")
    tk.Entry(
        out_row, textvariable=values["output"], font=BODY,
        relief="solid", borderwidth=1,
    ).pack(side="left", fill="x", expand=True, padx=(10, 6), ipady=3)

    def browse() -> None:
        selected = filedialog.askdirectory(initialdir=values["output"].get())
        if selected:
            values["output"].set(selected)

    ttk.Button(out_row, text="Browse...", style="Small.TButton", command=browse).pack(
        side="left"
    )

    def specs() -> tuple[BoxSpec, ConnectorSpec, Path]:
        box = current_box()
        connector = ConnectorSpec(
            tolerance=float(values["tolerance"].get()),
            height=float(values["height"].get()),
        )
        return box, connector, Path(values["output"].get()).expanduser()

    def perform(button, action) -> None:
        # The button reports on itself, so there is no status bar taking up a
        # line for the 99% of the time it says nothing. A failure still gets a
        # dialog, because it needs acting on.
        original = button.cget("text")
        try:
            button.configure(text="Working...")
            root.update_idletasks()
            action()
        except Exception as error:  # UI boundary: present validation errors cleanly.
            button.configure(text=original)
            messagebox.showerror("Could not generate part", str(error))
            return
        button.configure(text="Saved")
        later(1500, lambda: button.configure(text=original))

    def box_action():
        box, _, output = specs()
        return generate_organizer_files(
            box, current_layout(), output, values["label"].get(), values["part"].get(),
            values["label_position"].get(), values["scoop"].get(),
        )

    def side_action():
        box, connector, output = specs()
        return generate_side_file(
            box, connector, output / "Connector.3mf",
            values["side_axis"].get(), float(values["side_position"].get()),
            float(values["side_length"].get()),
        )

    def sampler_action():
        box, connector, output = specs()
        return generate_sampler(
            output=output / "WAVY_SAMPLE_SET.3mf",
            sizes=parse_sizes(DEFAULT_SAMPLE_BOXES),
            height=box.z, wall=box.wall, connector=connector,
        )

    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))
    box_button = ttk.Button(buttons, text="Generate Box", style="Go.TButton")
    box_button.configure(command=lambda: perform(box_button, box_action))
    box_button.pack(side="left", fill="x", expand=True)
    side_button = ttk.Button(buttons, text="Generate Connector", style="Go.TButton")
    side_button.configure(command=lambda: perform(side_button, side_action))
    side_button.pack(side="left", fill="x", expand=True, padx=(10, 0))
    sampler_button = ttk.Button(
        buttons, text="Generate Sampler", style="Small.TButton"
    )
    sampler_button.configure(command=lambda: perform(sampler_button, sampler_action))
    sampler_button.pack(side="left", padx=(16, 0))

    # Everything spare goes to the preview column and to the two canvas rows;
    # the settings on the left keep the width they asked for.
    frame.columnconfigure(2, weight=1)
    # The interior-support editor is the row that actually runs out of room -
    # it carries a diagram, a ring of parameter tags and the parts list - so
    # spare height goes mostly there and the preview keeps a generous floor.
    frame.rowconfigure(2, weight=1, minsize=420)
    frame.rowconfigure(3, weight=3, minsize=380)

    # Open at the size the window actually wants, but never bigger than the
    # screen it has to live on.
    root.update_idletasks()
    wanted_width = max(1120, frame.winfo_reqwidth() + 4)
    wanted_height = frame.winfo_reqheight() + 4
    root.geometry(
        f"{min(wanted_width, root.winfo_screenwidth() - 80)}"
        f"x{min(wanted_height, root.winfo_screenheight() - 120)}"
    )
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run_command(args)
    except Exception as error:
        parser.exit(2, f"error: {error}\n")
    if result is not None:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
