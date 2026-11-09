"""Storage Box screw note: a 0.2 mm flat card listing the screws the case needs.

The totals are counted from the same hardware plan the BOM and the exported
hinge/latch/handle geometry read, so the card always matches the box printed.
The card is a plate with the lettering cut through it plus a matching text
inlay (second filament slot), exactly like the lid's top-label inlay; together
they are one flat 0.2 mm object.  A case that uses no screws gets no card.
"""

from __future__ import annotations

import re
from collections import Counter

import trimesh
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from shapely.affinity import translate as translate_polygon
from shapely.ops import unary_union

from organizer_engine import BoxSpec, text_outline, text_prism
from organizer_geometry import _extrude_polygon, union

from ._layout import b4b_effective_box
from ._plans import b4b_handle_plan, b4b_hardware_plan

B4B_NOTE_THICKNESS = 0.2
B4B_NOTE_CAP_HEIGHT = 5.0      # the project's minimum readable lettering
B4B_NOTE_LINE_PITCH = 9.0
B4B_NOTE_MARGIN = 4.0
B4B_NOTE_MAX_LINE_CHARS = 26


def b4b_screw_totals(box: BoxSpec) -> list[tuple[str, int, int]]:
    """``[(family, length_mm, count)]`` for every screw the case needs, sorted
    by family then longest first.  A piano hinge's pin is filament, not a screw."""
    eff = b4b_effective_box(box)
    if not eff.b4b.secure_lid:
        return []
    plan = b4b_hardware_plan(box)
    family = plan.profile.name
    totals: Counter = Counter()
    if plan.piano is None and plan.hinge_count:
        totals[(family, plan.hinge_screw_length_mm)] += plan.hinge_count
    if plan.latch_count_resolved:
        totals[(family, plan.latch_screw_length_mm)] += plan.latch_count_resolved
        totals[(family, plan.catch_screw_length_mm)] += plan.latch_count_resolved
    handle = b4b_handle_plan(box)
    if handle is not None:
        totals[(handle.profile.name, handle.screw_length_mm)] += 2
    return [
        (fam, length, count)
        for (fam, length), count in sorted(totals.items(), key=lambda kv: (kv[0][0], -kv[0][1]))
        if count > 0
    ]


def b4b_screw_note_lines(box: BoxSpec) -> list[str]:
    """The note text, e.g. ``["M2 X 10MM (2), M2 X 6MM (4)"]``, wrapped between entries."""
    entries = [f"{fam} X {length}MM ({count})" for fam, length, count in b4b_screw_totals(box)]
    lines: list[str] = []
    current = ""
    for entry in entries:
        candidate = f"{current}, {entry}" if current else entry
        if current and len(candidate) > B4B_NOTE_MAX_LINE_CHARS:
            lines.append(current + ",")
            current = entry
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def make_b4b_screw_note(box: BoxSpec) -> list[tuple[str, trimesh.Trimesh]] | None:
    """``[(card, plate), (text, inlay)]`` flat on z in [0, 0.2], or None if no screws."""
    lines = b4b_screw_note_lines(box)
    if not lines:
        return None
    glyph_rows: list[Polygon | MultiPolygon] = []
    top = 0.0
    for index, line in enumerate(lines):
        outline = text_outline(line, B4B_NOTE_CAP_HEIGHT)   # centred on the origin
        glyph_rows.append(translate_polygon(outline, yoff=top - index * B4B_NOTE_LINE_PITCH))
    glyphs = unary_union(glyph_rows)
    minx, miny, maxx, maxy = glyphs.bounds
    card = shapely_box(
        minx - B4B_NOTE_MARGIN, miny - B4B_NOTE_MARGIN,
        maxx + B4B_NOTE_MARGIN, maxy + B4B_NOTE_MARGIN,
    )
    plate_2d = card.difference(glyphs)
    pieces = list(plate_2d.geoms) if hasattr(plate_2d, "geoms") else [plate_2d]
    plate = union([_extrude_polygon(p, B4B_NOTE_THICKNESS) for p in pieces if p.area > 0])
    text = text_prism(glyphs, top_z=B4B_NOTE_THICKNESS, depth=B4B_NOTE_THICKNESS)
    return [("Storage Box Note Card", plate), ("Storage Box Note Text", text)]
