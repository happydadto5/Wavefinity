"""Structural outputs a Space owns: its Storage Box case and its Surface Base Trim.

Neither is an Inventory row or a Designer object. Each is built here as a
transient, validated design from the authoritative Space definition, then
generated/printed through the ordinary generator with Inventory logging
suppressed by the caller. Nothing in this module reads or writes an Inventory.

* Storage Box (internal Space kind ``portable``; legacy ``box`` behaves the
  same): Space X/Y/Z are the usable child-bin field width, depth and height;
  the outer case is derived by the B4B geometry. ``space.storage_box`` carries
  the case settings. The case has an empty interior layout - dividers and other
  interior parts are never part of it.
* Surface: Space X/Y are the physical field; ``trim_size`` names the Base Trim
  height/width. The Base Trim is built from the Space alone.
"""

from __future__ import annotations

import math
from typing import Any

from organizer_app import design_from_dict, design_to_dict
from organizer_base_trim import (
    BASE_TRIM_DEFAULT_BED_X,
    BASE_TRIM_DEFAULT_BED_Y,
    BaseTrimSpec,
    base_trim_design_to_dict,
)
from organizer_engine import B4BSpec, BoxSpec
from organizer_inserts import EDITOR_SNAP, Layout
from organizer_inventory import normalise_space_definition
from organizer_product_rules import SURFACE_TRIM_HEIGHTS

STORAGE_BOX = "storage_box"
BASE_TRIM = "base_trim"
STORAGE_BOX_KINDS = ("portable", "box")


def structural_kind(space: dict[str, Any] | None) -> str | None:
    """Which structural output this Space owns, or None (Drawer/Pegboard)."""
    kind = (space or {}).get("kind")
    if kind in STORAGE_BOX_KINDS:
        return STORAGE_BOX
    if kind == "surface":
        return BASE_TRIM
    return None


def _space_definition(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("a Space definition is required")
    return normalise_space_definition(raw, allow_legacy=True)


def storage_box_design(space: dict[str, Any]) -> dict[str, Any]:
    """The empty-layout B4B case design for a Storage Box Space."""
    definition = _space_definition(space)
    if structural_kind(definition) != STORAGE_BOX:
        raise ValueError("Only a Storage Box Space has a Storage Box case to save or print.")
    settings = definition["storage_box"]
    b4b = B4BSpec(
        enabled=True,
        lid=True,
        secure_lid=settings["secure_lid"],
        latch_count=settings["latch_count"] if settings["secure_lid"] else "auto",
        latch_strength=settings["latch_strength"],
        lid_headroom_mm=settings["lid_headroom_mm"],
        label_enabled=settings["label_enabled"],
        label_text=settings["label_text"] if settings["label_enabled"] else "",
        label_location=settings["label_location"],
        front_label_style=settings["front_label_style"],
        stacking=settings["stacking"],
        handle=settings["handle"] and settings["secure_lid"],
    )
    box = BoxSpec(
        x=definition["x"], y=definition["y"], z=definition["z"],
        wall=settings["wall_mm"], base_thickness=settings["base_mm"],
        standard_walls=False, standard_base=False, b4b=b4b,
    )
    design = design_to_dict(box, Layout((), "fused", EDITOR_SNAP), part_name=definition["name"])
    design_from_dict(design)  # the case must be valid before it is offered
    return design


def base_trim_design(
    space: dict[str, Any], *, bed_x_mm: Any = None, bed_y_mm: Any = None,
) -> dict[str, Any]:
    """The Base Trim design for a Surface Space, at the given printer bed."""
    definition = _space_definition(space)
    if structural_kind(definition) != BASE_TRIM:
        raise ValueError("Only a Surface Space has a Base Trim to save or print.")
    trim = SURFACE_TRIM_HEIGHTS[definition["trim_size"]]

    def bed(raw: Any, fallback: float, label: str) -> float:
        if raw is None or raw == "":
            return fallback
        if isinstance(raw, bool):
            raise ValueError(f"{label} must be a number in mm")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be a number in mm") from error
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{label} must be a positive number in mm")
        return value

    spec = BaseTrimSpec(
        field_x=definition["x"], field_y=definition["y"],
        height_mm=trim, width_mm=trim,
        bed_x_mm=bed(bed_x_mm, BASE_TRIM_DEFAULT_BED_X, "Bed X"),
        bed_y_mm=bed(bed_y_mm, BASE_TRIM_DEFAULT_BED_Y, "Bed Y"),
    )
    return base_trim_design_to_dict(spec, definition["name"])


def structural_design(space: dict[str, Any], **options: Any) -> dict[str, Any]:
    """The transient design for whatever structural output this Space owns."""
    kind = structural_kind(_space_definition(space))
    if kind == STORAGE_BOX:
        return storage_box_design(space)
    if kind == BASE_TRIM:
        return base_trim_design(space, **options)
    raise ValueError("This Space type has no structural output.")
