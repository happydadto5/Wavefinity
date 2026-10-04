"""Wavefinity output file naming and part-spec helpers."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import re
import trimesh
from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    DEFAULT_WALL,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    DEFAULT_ARM_THICKNESS,
    lid_spec,
    lid_stackable,
)
from organizer_pegboard import pegboard_standard
from organizer_stack import stack_effective_box
from organizer_inserts import Layout, divider_cells

from ._common import clean_label, base_height


def _box_spec(args: argparse.Namespace, prefix: str = "") -> BoxSpec:
    key = f"{prefix}_" if prefix else ""
    return BoxSpec(
        x=getattr(args, f"{key}x"),
        y=getattr(args, f"{key}y"),
        z=getattr(args, f"{key}z"),
        wall=getattr(args, f"{key}wall"),
        flat_inside=getattr(args, f"{key}flat_inside"),
        base_thickness=getattr(args, f"{key}base_thickness"),
        standard_walls=math.isclose(
            getattr(args, f"{key}wall"), DEFAULT_WALL, abs_tol=1e-9
        ),
    )


def _connector_spec(args: argparse.Namespace) -> ConnectorSpec:
    return ConnectorSpec(tolerance=args.tolerance, height=args.height)


def _part_result(output: Path, report: dict, fit: object = None) -> dict[str, object]:
    result: dict[str, object] = {"output": str(output.resolve()), "mesh": report}
    if fit is not None:
        result["fit"] = fit
    return result


def box_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    """``Box 16 x 48 x 40 Driver Rack.3mf``.

    The part name is the only thing that names a file. Lettering on the part
    is an interior part in its own right - there can be several, and which of
    them would stand for the whole file is not a question with an answer - so
    text no longer appears here. Seed the part name from the first label if
    you want the old behaviour; the editor offers to do exactly that.
    """
    name = f"Box {box.x:g} x {box.y:g} x {box.z:g}"
    if not math.isclose(box.wall, DEFAULT_WALL, abs_tol=1e-9):
        name += f" Wall {box.wall:g}mm"
    tidy = clean_label(part)
    if tidy:
        name += f" {tidy}"
    return name + suffix


def edge_mount_label_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    name = f"Edge Mount Label {box.x:g} x {box.y:g}"
    tidy = clean_label(part)
    return (f"{name} {tidy}" if tidy else name) + suffix


def pegboard_adapter_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    name = f"Pegboard Adapters {pegboard_standard(box.pegboard.standard).name} {box.x:g} x {box.z:g}"
    tidy = clean_label(part)
    return (f"{name} {tidy}" if tidy else name) + suffix


def lid_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    """The ordinary bin's matching removable lid."""
    effective = stack_effective_box(box)
    name = f"{'Stack Lid' if lid_stackable(box) else 'Handled Lid'} {box.x:g} x {box.y:g}"
    if not math.isclose(effective.wall, DEFAULT_WALL, abs_tol=1e-9):
        name += f" Wall {effective.wall:g}mm"
    tidy = clean_label(part)
    if tidy:
        name += f" {tidy}"
    return name + suffix


def stack_lid_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    """Compatibility name for callers of the former stack-only helper."""
    return lid_filename(box, part, suffix)


def lid_label_regions(
    box: BoxSpec, layout: Layout,
) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Resolve lid labels from the Divider's authoritative compartments."""
    spec = lid_spec(box)
    if not spec.label_enabled:
        return []
    divider = next((one for one in layout.features if one.kind == "divider"), None)
    if divider is None:
        return []
    cells = divider_cells(stack_effective_box(box), divider, base_height(stack_effective_box(box), layout.mode))
    columns = max((cell.column_end for cell in cells), default=0)
    labels = list(spec.division_labels)
    regions: list[tuple[str, tuple[float, float, float, float]]] = []
    for cell in cells:
        index = cell.row * columns + cell.column
        text = labels[index] if index < len(labels) else ""
        regions.append((str(text or ""), (
            cell.zone.x0, cell.zone.y0, cell.zone.x1, cell.zone.y1,
        )))
    return regions


def insert_filename(
    box: BoxSpec,
    part: str = "",
    cartridge: bool = False,
    suffix: str = ".3mf",
) -> str:
    prefix = "Cartridge" if cartridge else "Insert"
    name = f"{prefix} {box.x:g} x {box.y:g}"
    if not math.isclose(box.wall, DEFAULT_WALL, abs_tol=1e-9):
        name += f" Wall {box.wall:g}mm"
    tidy = clean_label(part)
    if tidy:
        name += f" {tidy}"
    return name + suffix


def connector_filename(
    connector: ConnectorSpec | None = None,
    length: float = LOCKED_CONNECTOR_LENGTH,
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
    arm_thickness: float | None = None,
    different_heights: bool = False,
    suffix: str = ".3mf",
    wall: float = DEFAULT_WALL,
) -> str:
    tolerance = LOCKED_TOLERANCE if connector is None else connector.tolerance
    height = LOCKED_CONNECTOR_HEIGHT if connector is None else connector.height
    effective_arm = (
        arm_thickness
        if arm_thickness is not None
        else (DEFAULT_ARM_THICKNESS if connector is None else connector.arm_thickness)
    )

    diff = []
    if not math.isclose(wall, DEFAULT_WALL, abs_tol=1e-9):
        diff.append(f"Wall {wall:g}mm")
    if different_heights and bin_a_height is not None and bin_b_height is not None:
        if abs(bin_a_height - bin_b_height) > 1e-6:
            diff.append(f"{bin_a_height:g}mm to {bin_b_height:g}mm")

    if abs(tolerance - LOCKED_TOLERANCE) > 1e-6:
        diff.append(f"Tol {tolerance:g}mm")
    if abs(height - LOCKED_CONNECTOR_HEIGHT) > 1e-6:
        diff.append(f"Height {height:g}mm")
    if abs(length - LOCKED_CONNECTOR_LENGTH) > 1e-6:
        diff.append(f"Len {length:g}mm")
    if abs(effective_arm - DEFAULT_ARM_THICKNESS) > 1e-6:
        diff.append(f"Arm {effective_arm:g}mm")

    if not diff:
        return f"Connector - Same height{suffix}"
    return f"Connector - {' '.join(diff)}{suffix}"


CORNER_WAYS_NAMES = {3: "3-Way Corner", 4: "4-Way Corner"}
MAX_CORNER_QUANTITY = 20
CORNER_COPY_GAP = 4.0


def corner_connector_filename(
    ways: int, quantity: int = 1, wall: float = DEFAULT_WALL, suffix: str = ".3mf"
) -> str:
    parts = [CORNER_WAYS_NAMES[ways]]
    if quantity > 1:
        parts[0] += f" x{quantity}"
    if not math.isclose(wall, DEFAULT_WALL, abs_tol=1e-9):
        parts.append(f"Wall {wall:g}mm")
    return f"Connector - {' - '.join(parts)}{suffix}"


def validate_corner_quantity(quantity) -> int:
    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or not 1 <= quantity <= MAX_CORNER_QUANTITY
    ):
        raise ValueError(
            f"corner connector quantity must be a whole number from 1 to {MAX_CORNER_QUANTITY}"
        )
    return quantity


def arrange_connector_copies(mesh: trimesh.Trimesh, quantity: int) -> trimesh.Trimesh:
    """Lay out ``quantity`` separate copies of a print-oriented connector."""
    if quantity == 1:
        return mesh
    size_x, size_y = (float(v) for v in mesh.extents[:2])
    columns = math.ceil(math.sqrt(quantity))
    copies = []
    for index in range(quantity):
        row, col = divmod(index, columns)
        copy = mesh.copy()
        copy.apply_translation((
            col * (size_x + CORNER_COPY_GAP),
            row * (size_y + CORNER_COPY_GAP),
            0.0,
        ))
        copies.append(copy)
    return trimesh.util.concatenate(copies)


SIZE_LIKE = re.compile(r"^\s*\d+(\.\d+)?\s*(mm)?\s*$", re.IGNORECASE)


def part_name_seed(text: str) -> str:
    """The part name a piece of lettering should seed, or ``""``.

    A label that is just a size - "8", "12mm" - names a compartment, not the
    part, so it is never promoted to the filename.
    """
    tidy = str(text or "").strip()
    if not tidy or SIZE_LIKE.match(tidy):
        return ""
    return tidy
