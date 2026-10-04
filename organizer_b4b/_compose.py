"""Storage Box (B4B) divider handling, assembled body and preview meshes."""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
import trimesh
from organizer_engine import B4BSpec, BoxSpec
from organizer_geometry import translated, union

from ._layout import b4b_effective_box, b4b_mating_polygon
from ._geometry import (
    make_b4b_body,
    make_b4b_lid,
    _stack_pegs,
    _weld,
    make_b4b_latches,
    make_b4b_handle,
)
from ._labels import _apply_top_label, b4b_front_label_geometry


def b4b_divider_zone(box: BoxSpec):
    from organizer_inserts import Zone
    eff = b4b_effective_box(box)
    return Zone(
        -eff.x / 2.0, -eff.y / 2.0,
         eff.x / 2.0,  eff.y / 2.0,
    )


def b4b_divider_work_box(box: BoxSpec) -> BoxSpec:
    eff = b4b_effective_box(box)
    return replace(
        eff,
        z=eff.base_thickness + eff.z,
        b4b=B4BSpec(),
    )


def _b4b_divider_labels_enabled(feature) -> bool:
    raw = (feature.options or {}).get("label_divisions")
    if isinstance(raw, str):
        return raw.strip().lower() not in {"", "false", "0", "no", "off"}
    return bool(raw)


def normalize_b4b_divider(box: BoxSpec, feature):
    from organizer_inserts import normalize_divider_scoop

    if feature.kind != "divider":
        raise ValueError("Storage Box supports Dividers only in Parts & options.")
    if _b4b_divider_labels_enabled(feature) or (feature.options or {}).get("division_labels"):
        raise ValueError("Divider division labels are not available on Storage Box.")

    eff = b4b_effective_box(box)
    work = b4b_divider_work_box(eff)
    options = dict(feature.options or {})
    if options.get("height") in (None, ""):
        # Storage Box has no ordinary connector band. Default to full child height.
        options["height"] = eff.z

    one = replace(
        feature,
        zone=b4b_divider_zone(eff),
        full_span=True,
        options=options,
    )
    one = normalize_divider_scoop(work, one, work.base_thickness)
    return replace(one, zone=b4b_divider_zone(eff), full_span=True)


def b4b_divider_solids(box: BoxSpec, features):
    from organizer_inserts import build_divider

    features = tuple(features)
    if len(features) > 1:
        raise ValueError("Storage Box supports one Divider layout.")
    if not features:
        return []

    eff = b4b_effective_box(box)
    work = b4b_divider_work_box(eff)
    one = normalize_b4b_divider(eff, features[0])
    return build_divider(
        work,
        one,
        work.base_thickness,
        full_span_cavity=b4b_mating_polygon(eff),
    )


def b4b_body_with_features(box: BoxSpec, features=()) -> trimesh.Trimesh:
    """The Storage Box body exactly as it will print: flat floor + wall + hardware, plus the
    top-loading front-label channel frame when that label is selected and any fused Dividers.

    Preview and export both go through here so they can never disagree about
    whether the frame is present.
    """
    body = make_b4b_body(box)
    dividers = b4b_divider_solids(box, features)
    if dividers:
        body = _weld(union([body, *dividers]))
    b4b = b4b_effective_box(box).b4b
    if b4b.label_location == "front" and b4b.label_text.strip():
        frame, _plate, _text, _centre = b4b_front_label_geometry(box)
        body = _weld(union([body, frame]))
    return body


@lru_cache(maxsize=32)
def _b4b_preview_geometry(box: BoxSpec) -> tuple:
    """Cached: identical Storage Box designs reuse the same preview mesh walk instead of
    re-running the booleans on every keystroke."""
    from organizer_app import _mesh_preview_geometry  # local: avoid import cycle

    geometry: list = []
    eff = b4b_effective_box(box)
    body = b4b_body_with_features(box)
    geometry.extend(_mesh_preview_geometry(body, "b4b_body", owner="base"))
    if eff.b4b.label_location == "front" and eff.b4b.label_text.strip():
        # Plugs into the body's front channel frame - a base part.  Shown
        # installed in its holder, not laid flat as it prints.
        _frame, front_plate, front_text, front_centre = b4b_front_label_geometry(box)
        geometry.extend(
            _mesh_preview_geometry(
                translated(front_plate, front_centre), "b4b_label", owner="base"
            )
        )
        geometry.extend(
            _mesh_preview_geometry(
                translated(front_text, front_centre), "b4b_label_text", owner="base"
            )
        )
    if eff.b4b.lid:
        lid = make_b4b_lid(box)
        if eff.b4b.label_location == "top" and eff.b4b.label_text.strip():
            lid, inlay = _apply_top_label(box, lid)
            # Fused into the lid mesh itself - a lid part.
            geometry.extend(_mesh_preview_geometry(inlay, "b4b_label", owner="lid"))
        geometry.extend(_mesh_preview_geometry(lid, "b4b_lid", owner="lid"))
    handle = make_b4b_handle(box)
    if handle is not None:
        # Folds against the front wall - body-mounted hardware.
        geometry.extend(_mesh_preview_geometry(handle, "b4b_handle", owner="base"))
    if eff.b4b.secure_lid:
        for lever in make_b4b_latches(box):
            # Lid-mounted moving parts.
            geometry.extend(_mesh_preview_geometry(lever, "b4b_latch", owner="lid"))
    if eff.b4b.stacking:
        for peg in _stack_pegs(box):
            # Locating pegs stand proud of the lid's own top surface.
            geometry.extend(_mesh_preview_geometry(peg, "b4b_stack", owner="lid"))
    return tuple(geometry)


def b4b_preview_parts(box: BoxSpec, features=()) -> list[tuple[list, str, tuple, int, str]]:
    """Preview geometry in the ``preview_geometry`` tuple format:
    ``(points, kind, normal, layer, owner)``, where ``owner`` is ``"base"`` or
    ``"lid"``.  Dimensionally true; microdetail such as thread pilots is
    omitted."""
    from organizer_app import _mesh_preview_geometry  # local: avoid import cycle
    parts = list(_b4b_preview_geometry(box))
    for mesh in b4b_divider_solids(box, features):
        parts.extend(_mesh_preview_geometry(mesh, "feature_divider", owner="base"))
    return parts


def b4b_preview_meshes(box: BoxSpec, features=()) -> list[dict]:
    """Compact GPU-ready preview transport: one entry per (kind, owner,
    layer) group, carrying flat ``positions``/``normals`` arrays instead of
    one JSON object per triangle.

    A B4B case routinely runs past 100k triangles, where serialising and
    parsing ``b4b_preview_parts``'s one-dict-per-face format is itself most
    of the preview's load cost - repeating ``kind``/``normal``/``layer``/
    ``owner`` on every triangle instead of once per group. ``normals`` holds
    one normal per triangle (not per vertex): every B4B preview face is
    mesh-derived and already a flat-shaded triangle, so the three corners in
    ``positions`` at index ``9*i .. 9*i+9`` all share ``normals[3*i .. 3*i+3]``
    and the browser expands it per vertex when building its GPU buffer.
    """
    groups: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    for points, kind, normal, layer, owner in b4b_preview_parts(box, features):
        bucket = groups.setdefault((kind, owner, layer), {"positions": [], "normals": []})
        for corner in points:
            bucket["positions"].extend(corner)
        bucket["normals"].extend(normal)
    return [
        {
            "kind": kind, "owner": owner, "layer": layer,
            "positions": bucket["positions"], "normals": bucket["normals"],
        }
        for (kind, owner, layer), bucket in groups.items()
    ]
