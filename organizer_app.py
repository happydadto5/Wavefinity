"""Shared geometry/export services and command-line tools for Wavefinity."""

from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable

import numpy as np
import trimesh

from organizer_engine import (
    BASE_UNIT,
    B4BSpec,
    BoxSpec,
    ConnectorSpec,
    StackSpec,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_WALL,
    EASY_CLEAN_RADIUS,
    GRID_PITCH,
    MAX_WALL,
    MIN_WALL,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    DEFAULT_ARM_THICKNESS,
    export_labelled_box,
    export_text_body_3mf,
    export_mesh,
    connector_for_print,
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
    max_wave_slope,
    mesh_report,
    scoop_floor_zone,
    scoop_keep_out,
    top_label_outline,
    top_label_report,
    top_label_zone,
    translated,
    union,
    validate_side_fit,
    validate_3mf,
    export_assembly_3mf,
)
from organizer_b4b import (
    b4b_build_parts,
    b4b_effective_box,
    b4b_summary,
    validate_b4b_design,
)
from organizer_stack import (
    make_stack_lid,
    normalize_stack_settings,
    stack_effective_box,
    stack_enabled,
    stack_spec,
    stack_step_depth,
    stack_summary,
    validate_stack_design,
)
from organizer_inventory import append_bin
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    EDITOR_SNAP,
    FEATURE_BUILDERS,
    INSERT_CLEARANCE,
    TEXT_KIND,
    _cradle_rib_thickness,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Zone,
    apply_texts,
    bore_hole_axes,
    build_features,
    build_texts,
    connector_keep_out,
    feature_footprint,
    feature_definitions,
    insert_footprint,
    insert_report,
    is_text,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    make_cartridge_insert,
    make_fitted_insert,
    make_fused_box,
    fitted_nest_feature,
    make_insert_plate,
    normalize_divider_scoop,
    resolve_text_features,
    snapped_zone,
    scoop_zone,
    text_depth,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm

_FEATURE_DEFINITIONS = feature_definitions()
INTERIOR_PART_CATALOG = {
    definition.kind: (definition.display, definition.description)
    for definition in _FEATURE_DEFINITIONS
}
INTERIOR_PART_ORDER = tuple(
    definition.kind for definition in _FEATURE_DEFINITIONS
)
# The rim label is the one piece of lettering that is not an interior part: it
# lives on a shelf at the selected rim side, not on the floor, so it has no zone to
# drag. "bottom" now simply means there is no rim label - floor lettering is a
# text interior part.
LABEL_POSITIONS = ("bottom", "top", "front", "back", "left", "right")


def label_position(value: str) -> str:
    position = str(value).strip().lower()
    if position not in LABEL_POSITIONS:
        raise ValueError("label position must be on the base or a rim side")
    return position


def rim_label_side(value: str) -> str | None:
    position = label_position(value)
    if position == "bottom":
        return None
    return "back" if position == "top" else position


# --- guided part palette ---------------------------------------------------
#
# Compatibility views for existing CLI/browser callers. Their source of truth
# is the feature-local registry populated by each feature module.
PART_KINDS = tuple(
    (
        definition.kind,
        definition.title,
        definition.description,
        definition.flags,
        tuple(
            (option.label, option.key, option.default)
            for option in definition.options if option.editor
        ),
    )
    for definition in _FEATURE_DEFINITIONS
)
PART_KIND_INFO = {
    kind: (title, blurb, flags, fields)
    for kind, title, blurb, flags, fields in PART_KINDS
}


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
        f"--{option}wall", dest=f"{destination}wall", type=float, default=DEFAULT_WALL
    )
    parser.add_argument(
        f"--{option}base-thickness", dest=f"{destination}base_thickness",
        type=float, default=DEFAULT_BASE_THICKNESS,
    )
    parser.add_argument(
        f"--{option}flat-inside", dest=f"{destination}flat_inside",
        type=float, default=0.0,
        help="0-1 mm: height of a flat-walled band rising from the floor",
    )
    parser.add_argument(
        f"--{option}easy-clean", dest=f"{destination}easy_clean",
        action="store_true", default=False,
    )
    parser.add_argument(
        f"--{option}easy-clean-style", dest=f"{destination}easy_clean_style",
        choices=("bevel", "curve"), default="bevel",
    )
    parser.add_argument(
        f"--{option}easy-clean-radius", dest=f"{destination}easy_clean_radius",
        type=float, default=EASY_CLEAN_RADIUS,
    )


def add_connector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tolerance", type=float, default=LOCKED_TOLERANCE)
    parser.add_argument("--height", type=float, default=LOCKED_CONNECTOR_HEIGHT)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate fixed-pitch wavy organizer boxes and their side connectors. "
            "Use Launch_Organizer_UI.bat for the browser interface."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

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
        help=(
            "connector center from the wall center, in whole "
            f"{WAVE_LENGTH:g} mm waves"
        ),
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
    layout_parser.add_argument("--base-thickness", type=float)
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
    sampler_parser.add_argument("--wall", type=float, default=DEFAULT_WALL)
    sampler_parser.add_argument(
        "--base-thickness", type=float, default=DEFAULT_BASE_THICKNESS
    )
    sampler_parser.add_argument("--flat-inside", type=float, default=0.0)
    sampler_parser.add_argument("--clips", type=int, default=5)
    sampler_parser.add_argument("--tolerance", type=float, default=LOCKED_TOLERANCE)
    sampler_parser.add_argument("--output", type=Path, required=True)

    return parser


def _box_spec(args: argparse.Namespace, prefix: str = "") -> BoxSpec:
    key = f"{prefix}_" if prefix else ""
    return BoxSpec(
        x=getattr(args, f"{key}x"),
        y=getattr(args, f"{key}y"),
        z=getattr(args, f"{key}z"),
        wall=getattr(args, f"{key}wall"),
        flat_inside=getattr(args, f"{key}flat_inside"),
        base_thickness=getattr(args, f"{key}base_thickness"),
        easy_clean=getattr(args, f"{key}easy_clean", False),
        easy_clean_style=getattr(args, f"{key}easy_clean_style", "bevel"),
        easy_clean_radius=getattr(args, f"{key}easy_clean_radius", EASY_CLEAN_RADIUS),
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


ILLEGAL_IN_FILENAMES = r'<>:"/\|?*'


def clean_label(label: str) -> str:
    """The label with anything a filesystem would object to removed."""
    kept = "".join(
        " " if character in ILLEGAL_IN_FILENAMES else character
        for character in (label or "")
        if character.isprintable()
    )
    return " ".join(kept.split())


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


def stack_lid_filename(box: BoxSpec, part: str = "", suffix: str = ".3mf") -> str:
    """``Stack Lid 16 x 48 Driver Rack.3mf`` - the bin's own snap-in lid."""
    name = f"Stack Lid {box.x:g} x {box.y:g}"
    tidy = clean_label(part)
    if tidy:
        name += f" {tidy}"
    return name + suffix


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

def _feature_height(box: BoxSpec, one: Feature, base_z: float) -> float:
    options = one.options
    if one.kind == "cradle" and one.item is not None:
        return base_z + options.get("floor_gap", 2.0) + one.item.widest / 2.0
    if one.kind == "bore" and one.item is not None:
        depth = options.get("depth", min(one.item.length * 0.4, box.z - base_z - 2.0))
        return base_z + options.get("height", depth + 2.0)
    if one.kind == "nest":
        depth = float(options.get("depth", 8.0))
        lift = (
            float(options.get("push_depth", 4.0))
            if options.get("lift_assist", "finger_grasp") == "push_out"
            else 0.0
        )
        return base_z + depth + lift
    if one.kind == "divider":
        return base_z + options.get("height", connector_keep_out(box) - base_z)
    return base_z + options.get("height", 12.0)


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


def _bore_axis_geometry(
    box: BoxSpec, one: Feature, base_z: float, kind: str
) -> list[tuple]:
    """Centre-line polylines for a leaned bore, so the preview can draw an arrow
    up each hole showing which way it points. Empty for anything but an angled
    bore, and silent if the bore itself will not resolve."""
    if one.kind != "bore":
        return []
    try:
        axes = bore_hole_axes(box, one, base_z)
    except Exception:
        return []
    return [
        ([tuple(float(v) for v in point) for point in polyline],
         kind, (0.0, 0.0, 1.0), 9)
        for polyline in axes
    ]


# A preview pixel covers roughly a tenth of a millimetre of model even at full
# zoom, so a micron is far below anything the browser can draw.  Rounding there
# costs nothing visible and makes the payload it has to parse much smaller.
PREVIEW_DECIMALS = 3
# A triangle this small is a boolean sliver, not a surface: a millionth of a
# preview pixel.  Its neighbours already tile the shape it sits in.
PREVIEW_MIN_FACE_AREA = 1e-4


def _mesh_preview_geometry(mesh, kind: str) -> list[tuple]:
    """Convert a finished holder mesh into camera-independent preview faces.

    A B4B case runs to well over a hundred thousand triangles, so this works in
    numpy rather than per vertex in Python, drops slivers too small to paint,
    and rounds to the micron.  Same picture; a fraction of the build time and of
    the JSON the browser then has to parse.
    """
    preview_kind = mesh.metadata.get("wavefinity_preview_kind")
    if preview_kind and "invalid" not in kind and "conflict" not in kind:
        kind = f"{kind}_{preview_kind}"
    triangles = np.asarray(mesh.triangles, dtype=float)
    if not len(triangles):
        return []
    keep = np.asarray(mesh.area_faces, dtype=float) > PREVIEW_MIN_FACE_AREA
    corners = np.round(triangles[keep], PREVIEW_DECIMALS).tolist()
    normals = np.round(
        np.asarray(mesh.face_normals, dtype=float)[keep], PREVIEW_DECIMALS
    ).tolist()
    # numpy has already produced plain lists; re-wrapping several hundred
    # thousand of them in tuples costs more than everything else here put
    # together, and nothing downstream needs them to be tuples.
    return [
        (triangle, kind, normal, 0)
        for triangle, normal in zip(corners, normals)
    ]


def _customization_zones(
    box: BoxSpec,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> list[tuple[str, Zone]]:
    """Floor-plan keep-outs for fixed bin customizations."""
    zones: list[tuple[str, Zone]] = []
    side = rim_label_side(label_location)
    if clean_label(label) and side:
        zones.append(("rim label ledge", Zone(*top_label_zone(box, side).bounds)))
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
        make_scoop(box, _scoop_floor_bounds(box, mode)),
        (0.0, 0.0, -box.base_thickness),
    )


def base_height(box: BoxSpec, mode: str) -> float:
    """The z a holder is built up from: the bin floor, or the insert's plate."""
    return (
        box.base_thickness
        if mode == "fused"
        else box.base_thickness + BASE_PLATE
    )


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
    return translated(
        make_insert_plate(box, mode), (0.0, 0.0, box.base_thickness)
    )


def validate_customization_clearance(
    box: BoxSpec,
    features: Iterable[Feature],
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    mode: str = "fused",
) -> None:
    features = list(features)
    rim_feature = next((one for one in features if is_text(one) and one.options.get("level") == "rim"), None)
    if rim_feature is not None:
        label = text_of(rim_feature)
        label_location = str(rim_feature.options.get("rim_side", "back"))
    for index, one in enumerate(features):
        if is_text(one) and one.options.get("level") == "rim":
            continue
        for name, zone in _customization_zones(
            box, label, label_location, scoop, mode
        ):
            if one.zone.overlaps(zone, MIN_FEATURE_GAP):
                raise ValueError(
                    f"interior part {index + 1} ({one.kind}) overlaps the {name}; "
                    "move or resize the part in the 2D layout"
                )


def preview_geometry(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused", label_location: str = "bottom", scoop: bool = False,
    draft: Feature | None = None, selected: int | None = None,
) -> dict[str, object]:
    """Build camera-independent preview geometry once per design change.

    ``draft`` is the interior part currently being edited, not yet added to
    the layout - included in the same geometry, tagged ``draft_<kind>``
    instead of ``feature_<kind>``/``insert_<kind>`` so the browser can
    highlight it in place, right where it will actually sit, instead of
    drawing it alone on its own tiny canvas. It never affects
    ``feature_errors`` or ``invalid_feature_indexes`` - those describe the
    real layout - and a draft that fails to build still falls back to the
    same placeholder prism a placed feature would, reported through
    ``draft_error`` instead.
    """
    features = tuple(features)
    rim_feature = next((one for one in features if is_text(one) and one.options.get("level") == "rim"), None)
    if rim_feature is None and draft is not None and is_text(draft) and draft.options.get("level") == "rim":
        rim_feature = draft
    if rim_feature is not None:
        label = text_of(rim_feature)
        label_location = str(rim_feature.options.get("rim_side", "back"))

    features = resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, clean_label(label), label_position(label_location), scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )
    outer, cavity = preview_rings(box)
    floor_z, rim_z = box.base_thickness, box.z
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
    rim_side = rim_label_side(location)
    if tidy and rim_side:
        geometry.extend(_mesh_preview_geometry(make_top_label_ledge(box, rim_side), "top_label_ledge"))
    if scoop:
        scoop_mesh = (
            make_scoop(box)
            if mode == "fused"
            else translated(
                _removable_scoop(box, mode),
                (0.0, 0.0, box.base_thickness),
            )
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
    conflicting_feature_indexes = []
    reserved = _customization_zones(box, tidy, location, scoop, mode)

    occupied = [
        None if (is_text(one) and one.options.get("level") == "rim")
        else (feature_footprint(box, one, base_z) if mode == "fused" else one.zone)
        for one in features
    ]

    draft_error = None
    if draft is not None:
        if not (is_text(draft) and draft.options.get("level") == "rim"):
            conflict = next(
                (name for name, zone in reserved if draft.zone.overlaps(zone, MIN_FEATURE_GAP)),
                None,
            )
            if conflict is not None:
                draft_error = f"{draft.kind}: overlaps the {conflict}"
            else:
                try:
                    draft_occ = feature_footprint(box, draft, base_z) if mode == "fused" else draft.zone
                    for idx, one_occ in enumerate(occupied):
                        if one_occ is None:
                            continue
                        if selected is not None and idx == selected:
                            continue
                        if draft_occ.overlaps(one_occ, MIN_FEATURE_GAP):
                            conflicting_feature_indexes.append(idx)
                            if draft_error is None:
                                draft_error = (
                                    f"a {draft.kind} and a {features[idx].kind} overlap; "
                                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                                )
                except Exception:
                    pass

    for i, one_occ in enumerate(occupied):
        if one_occ is None:
            continue
        if selected is not None and i == selected and draft is not None:
            continue
        for j in range(i + 1, len(occupied)):
            if occupied[j] is None:
                continue
            if selected is not None and j == selected and draft is not None:
                continue
            if one_occ.overlaps(occupied[j], MIN_FEATURE_GAP):
                feature_errors.append(
                    f"a {features[i].kind} and a {features[j].kind} overlap; "
                    f"leave at least {MIN_FEATURE_GAP:g} mm between features"
                )
                if i not in invalid_feature_indexes:
                    invalid_feature_indexes.append(i)
                if j not in invalid_feature_indexes:
                    invalid_feature_indexes.append(j)

    for feature_index, one in enumerate(features):
        if is_text(one) and one.options.get("level") == "rim":
            continue
        if selected is not None and feature_index == selected and draft is not None:
            continue
        conflict = next(
            (name for name, zone in reserved if one.zone.overlaps(zone, MIN_FEATURE_GAP)),
            None,
        )
        if conflict is not None:
            feature_errors.append(f"{one.kind}: overlaps the {conflict}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)

        is_conflicting = feature_index in conflicting_feature_indexes
        is_invalid = feature_index in invalid_feature_indexes

        if is_invalid:
            tag = f"{part_kind}_invalid"
        elif is_conflicting:
            tag = f"{part_kind}_conflict_{one.kind}"
        else:
            tag = f"{part_kind}_{one.kind}"

        try:
            for solid in build_features(
                box, [one], base_z, layout_zone(box, mode), include_text=True
            ):
                geometry.extend(
                    _mesh_preview_geometry(solid, tag)
                )
        except Exception as error:
            feature_errors.append(f"{one.kind}: {error}")
            if feature_index not in invalid_feature_indexes:
                invalid_feature_indexes.append(feature_index)
            geometry.extend(_prism_geometry(
                one.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, one, base_z)),
                f"{part_kind}_invalid",
            ))
        geometry.extend(_bore_axis_geometry(
            box, one, base_z, f"{part_kind}_bore_axis"
        ))

    if draft is not None:
        if draft_error is not None:
            built = False
            try:
                solids = build_features(box, [draft], base_z, layout_zone(box, mode),
                                        include_text=True)
                for solid in solids:
                    geometry.extend(_mesh_preview_geometry(solid, "draft_invalid"))
                built = True
            except Exception:
                pass
            if not built:
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
        else:
            try:
                for solid in build_features(box, [draft], base_z, layout_zone(box, mode),
                                            include_text=True):
                    geometry.extend(_mesh_preview_geometry(solid, f"draft_{draft.kind}"))
            except Exception as error:
                draft_error = f"{draft.kind}: {error}"
                geometry.extend(_prism_geometry(
                    draft.zone,
                    base_z,
                    min(box.z - 0.25, _feature_height(box, draft, base_z)),
                    "draft_invalid",
                ))
        geometry.extend(_bore_axis_geometry(box, draft, base_z, "draft_bore_axis"))

    # The rim label is the only lettering left that is not an interior part:
    # it sits on a shelf at the selected rim side and has no zone to drag, so the
    # preview still draws it here. Floor text drew itself above, with every
    # other interior part.
    fits, message = True, ""
    label_outline_coords = []
    label_meta = None
    side = rim_label_side(location)
    if tidy and side:
        try:
            outline = top_label_outline(box, tidy, side)
            label_meta = {"location": location, "side": side}
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
            label_outline_coords = [
                [[float(x), float(y)] for x, y in piece.exterior.coords]
                for piece in pieces
            ]
            for piece in pieces:
                geometry.append(([(x, y, box.z) for x, y in piece.exterior.coords],
                                 "label", (0.0, 0.0, 1.0), 2))
                for ring in piece.interiors:
                    geometry.append(([(x, y, box.z) for x, y in ring.coords],
                                     "label_hole", (0.0, 0.0, 1.0), 3))

    inside_x, inside_y = box.usable_inside
    return {
        "geometry": geometry,
        "fits": fits,
        "message": message,
        "feature_errors": tuple(feature_errors),
        "invalid_feature_indexes": tuple(invalid_feature_indexes),
        "conflicting_feature_indexes": tuple(conflicting_feature_indexes),
        "draft_error": draft_error,
        "customization_zones": tuple(reserved),
        "label_outline": label_outline_coords,
        "label_meta": label_meta,
        # Where each text interior part ended up, so the browser can show the
        # resolved letter height an auto or zone-fitted one landed on.
        "text_meta": tuple(
            {
                "index": index,
                "text": text_of(one),
                "auto": bool(one.options.get("auto")),
                "cap_height": round(text_fitted(one)[0], 3),
            }
            for index, one in enumerate(features)
            if is_text(one) and _text_fits(one)
        ),
        "features": layout_to_dict(Layout(features, mode))["features"],
        "inside_x": math.floor(inside_x),
        "inside_y": math.floor(inside_y),
        "size_text": (
            f"{math.floor(inside_x):g} X {math.floor(inside_y):g} (Inside) - "
            f"{box.x:g} X {box.y:g} mm (Outside)"
        ),
    }


def _text_fits(one: Feature) -> bool:
    try:
        text_fitted(one)
        return True
    except ValueError:
        return False


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

    side = rim_label_side(location)
    if side:
        pocketed, inlay = make_top_labelled_box(box, tidy, body, side)
        label_info = top_label_report(box, tidy, side)
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


def text_report(box: BoxSpec, one: Feature, surface: float) -> dict[str, object]:
    """What one text interior part came out as, for the export report."""
    cap, _outline = text_fitted(one)
    placed = text_placed_outline(one)
    minx, miny, maxx, maxy = placed.bounds
    centre_x, centre_y = one.zone.centre
    return {
        "text": text_of(one),
        "cap_height_mm": round(cap, 3),
        "quarter_turns": int(one.options.get("quarter_turns", 0) or 0) % 4,
        "auto": bool(one.options.get("auto")),
        "raised": text_is_raised(one),
        "position_mm": [round(centre_x, 3), round(centre_y, 3)],
        "footprint_mm": [round(maxx - minx, 3), round(maxy - miny, 3)],
        "depth_mm": round(text_depth(one), 3),
        "surface_z_mm": round(surface, 3),
    }


def b4b_filename(box: BoxSpec, part_name: str = "", suffix: str = ".3mf") -> str:
    """``B4B 64x48x40 - Fasteners.3mf`` - distinct from an ordinary bin file of
    the same dimensions."""
    eff = b4b_effective_box(box)
    name = f"B4B {eff.x:g}x{eff.y:g}x{eff.z:g}"
    tidy = clean_label(part_name) or clean_label(box.b4b.label_text)
    if tidy:
        name += f" - {tidy}"
    return name + suffix


def generate_b4b_files(
    box: BoxSpec,
    output_dir: Path,
    part_name: str = "",
    auto_timestamp: bool = False,
    keep_log: bool = False,
) -> dict[str, object]:
    """Dedicated B4B export: one assembly 3MF holding every printable object
    (body, lid, latches, labels) already in print orientation.  Never routed
    through ``make_fused_box`` and never carries a side connector."""
    validate_b4b_design(box)
    summary = b4b_summary(box)
    parts = b4b_build_parts(box)

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / b4b_filename(box, part_name)
    if auto_timestamp and (target.exists() or not clean_label(part_name)):
        ts = datetime.now().strftime("%m%d%y%H%M%S")
        target = target.with_name(f"{target.stem} {ts}{target.suffix}")

    # non-label parts must each be one clean solid; labels are one prism per
    # letter, so they get the relaxed check
    for name, mesh in parts:
        if "Label" not in name:
            mesh_report(name, mesh)

    # lettering parts open on the second filament slot
    filaments = {
        name: 2 for name, _ in parts
        if name in ("B4B Top Label", "B4B Front Label")
    }
    written = export_assembly_3mf(parts, target, filaments)
    # every B4B file is an assembly (one grouping object, one build item), so
    # pass all names as ``multipart`` to get the assembly-aware structural check
    report = validate_3mf(target, len(parts), multipart=tuple(written))

    result: dict[str, object] = {
        "mode": "b4b",
        "b4b": summary,
        "output": str(target),
        "box": _part_result(target, {"name": "B4B Body", **report}),
        "parts": [
            {"name": name, "mesh": mesh_report(name, mesh) if "Label" not in name
             else {"name": name}}
            for name, mesh in parts
        ],
        "object_names": written,
        "hardware_bom": summary.get("hardware_bom", []),
    }
    if keep_log:
        log_file = log_bin_to_folder(
            output_dir, b4b_effective_box(box), Layout((), "fused", EDITOR_SNAP),
            generated_files=[target], label="", part_name=part_name,
            b4b_note=_b4b_log_note(summary),
        )
        result["log_file"] = str(log_file)
    return result


def _b4b_log_note(summary: dict) -> str:
    cx, cy = summary["capacity_units"]
    bits = [f"B4B {cx}x{cy} units"]
    if summary["lid"]:
        bits.append("secure lid" if summary["secure_lid"] else "passive lid")
    else:
        bits.append("no lid")
    if summary["secure_lid"]:
        # Latch count and hardware family are both derived from the case now,
        # so report what was resolved rather than a setting nobody chose.
        count = summary["latch_count"]
        bits.append(
            f"{count} latch" if count == 1 else f"{count} latches"
        )
        family = summary.get("hardware_family")
        if family:
            bits.append(f"{family} hardware")
        bom = summary.get("hardware_bom", [])
        if bom:
            bits.append("; ".join(bom))
    if summary["stacking"]:
        bits.append("stacking")
    if summary["label_location"] != "none":
        bits.append(f"{summary['label_location']} label")
    return ", ".join(bits)


def generate_organizer_files(
    box: BoxSpec,
    layout: Layout,
    output_dir: Path,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
    auto_timestamp: bool = False,
    keep_log: bool = False,
) -> dict[str, object]:
    """Export an editor design as fused, fitted-removable, or cartridge parts.

    ``label`` is the rim-ledge label only. Floor lettering rides in ``layout``
    as ``text`` interior parts and is written as one extra 3MF object each, so
    every piece can take its own filament.
    """
    if box.b4b.enabled:
        # B4B is a container mode, not an interior layout: dedicated path.
        # A caller that hands a B4B box a non-empty or non-fused Layout is
        # passing conflicting intent - reject it rather than quietly ignoring
        # the layout argument.
        validate_b4b_design(
            box,
            layout_feature_count=len(layout.features),
            layout_mode=layout.mode,
            easy_clean=box.easy_clean,
            flat_inside=box.flat_inside,
        )
        return generate_b4b_files(
            box, output_dir, part_name,
            auto_timestamp=auto_timestamp, keep_log=keep_log,
        )
    # Stacking rewrites the box before anything is built: a thicker wall to hold
    # the snap groove, a floor deep enough to contain the stepped base, and - in
    # lid mode - a body shortened so the closed bin is the height that was
    # typed.  Everything downstream, interior parts included, sees that box.
    # The request is kept for anything the user should recognise - the reported
    # height and the filename are the height they asked for, not the body the
    # lid is bolted onto.
    validate_stack_design(box)
    stack_request = box
    box = stack_effective_box(box)
    rim_feature = next((one for one in layout.features if is_text(one) and one.options.get("level") == "rim"), None)
    if rim_feature is not None:
        label = text_of(rim_feature)
        label_location = str(rim_feature.options.get("rim_side", "back"))
    layout = replace(
        layout,
        features=resolve_text_features(
            box, layout.features,
            reserved=[zone.polygon for _name, zone in
                      _customization_zones(box, clean_label(label),
                                           label_position(label_location),
                                           scoop, layout.mode)],
            base_z=base_height(box, layout.mode), mode=layout.mode,
        ),
    )
    layout.validate(box)
    tidy = clean_label(label)
    location = label_position(label_location)
    side = rim_label_side(location)
    if tidy and not side:
        # Floor lettering is a text interior part now, so a label arriving here
        # for the floor is a caller mistake - say so rather than dropping it.
        raise ValueError(
            f"'{label}' is a floor label, and floor lettering is a text "
            "interior part now. Add one to the layout, or set the label "
            "position to a rim side for the rim ledge"
        )
    validate_customization_clearance(
        box, layout.features, tidy, location, scoop, layout.mode
    )
    label_info = top_label_report(box, tidy, side) if tidy and side else None
    text_surface = box.base_thickness if layout.mode == "fused" else BASE_PLATE
    text_limit = (
        None if layout.mode == "fused"
        else insert_footprint(box, layout.mode)
    )
    texts = build_texts(box, layout.features, text_surface, text_limit)

    def _resolve_file(filename_fn, *args, **kwargs) -> Path:
        base_name = filename_fn(*args, **kwargs)
        target = output_dir / base_name
        if auto_timestamp:
            has_name = bool(clean_label(part_name))
            if not has_name or target.exists():
                ts = datetime.now().strftime("%m%d%y%H%M%S")
                stem = target.stem
                target = output_dir / f"{stem} {ts}{target.suffix}"
        return target

    if layout.mode == "fused":
        body = make_fused_box(box, layout.features, make_box(box))
        if scoop:
            body = union([body, make_scoop(box)])
        output = _resolve_file(box_filename, stack_request, part_name)
        # The rim label's ledge is part of the body, so it goes on before the
        # floor text is sunk into it.
        inlays = list(texts)
        if tidy:
            body, ledge_inlay = make_top_labelled_box(box, tidy, body, side)
            inlays.append((tidy, ledge_inlay, False))
        reported = apply_texts(body, texts)
        output_dir.mkdir(parents=True, exist_ok=True)
        if inlays:
            written = export_text_body_3mf(
                reported, [(name, mesh) for name, mesh, _raised in inlays],
                output, "fused_organizer",
            )
        else:
            written = []
            export_mesh(body, output, "fused_organizer")
        result: dict[str, object] = {
            "mode": layout.mode,
            "box": _part_result(output, mesh_report("fused_organizer", reported)),
            "layout": insert_report("fused_organizer", layout.features, body),
            "text_objects": written,
        }
    else:
        box_output = _resolve_file(box_filename, stack_request, part_name)
        plain_box = make_box(box)
        insert = (
            make_cartridge_insert(box, layout.features)
            if layout.mode == "cartridge"
            else make_fitted_insert(box, layout.features)
        )
        if scoop:
            insert = union([insert, _removable_scoop(box, layout.mode)])
        insert_output = _resolve_file(
            insert_filename, box, part_name, layout.mode == "cartridge"
        )
        reported_insert = apply_texts(insert, texts)
        output_dir.mkdir(parents=True, exist_ok=True)
        # The rim label belongs to the box; the floor text belongs to the
        # insert it is sunk into.
        if tidy:
            pocketed_box, box_inlay = make_top_labelled_box(box, tidy, plain_box, side)
            export_labelled_box(
                pocketed_box, box_inlay, box_output,
                box_output.stem, tidy,
            )
            reported_box = pocketed_box
        else:
            export_mesh(plain_box, box_output, "wavy_box")
            reported_box = plain_box
        if texts:
            written = export_text_body_3mf(
                reported_insert, [(name, mesh) for name, mesh, _raised in texts],
                insert_output, "organizer_insert",
            )
        else:
            written = []
            export_mesh(insert, insert_output, "organizer_insert")
        result = {
            "mode": layout.mode,
            "box": _part_result(box_output, mesh_report("wavy_box", reported_box)),
            "insert": _part_result(
                insert_output, mesh_report("organizer_insert", reported_insert)
            ),
            "layout": insert_report("organizer_insert", layout.features, insert),
            "text_objects": written,
        }
    if label_info is not None:
        result["label"] = label_info
    result["texts"] = [
        text_report(box, one, text_surface) for one in layout.features if is_text(one)
    ]
    result["customizations"] = {"scoop": scoop, "label_position": location}
    if stack_spec(stack_request).mode == "lid":
        lid_output = _resolve_file(stack_lid_filename, stack_request, part_name)
        export_mesh(make_stack_lid(stack_request), lid_output, "stack_lid")
        result["stack_lid"] = _part_result(lid_output, None)
    if stack_enabled(stack_request):
        result["stack"] = stack_summary(stack_request)
    if keep_log:
        out_files: list[Path] = []
        if "box" in result and isinstance(result["box"], dict) and "output" in result["box"]:
            out_files.append(Path(str(result["box"]["output"])))
        if "insert" in result and isinstance(result["insert"], dict) and "output" in result["insert"]:
            out_files.append(Path(str(result["insert"]["output"])))
        # Inventory stores the requested stack-module height.  The drawer adds
        # the exposed top engagement depth when checking physical clearance.
        log_file = log_bin_to_folder(
            output_dir,
            stack_request,
            layout,
            generated_files=out_files,
            label=label,
            part_name=part_name,
            scoop=scoop,
        )
        result["log_file"] = str(log_file)
    return result


def summarize_interior_parts(layout: Layout, scoop: bool = False) -> str:
    """Return a short human-readable description of interior parts for logging."""
    counts: dict[str, int] = {}
    for feature in layout.features:
        kind = getattr(feature, "kind", "part")
        if kind == "divider":
            name = "Full-span Divider" if getattr(feature, "full_span", False) else "Divider"
        elif kind == "cradle":
            item = getattr(feature, "item", None)
            name = f"Cradle ({item.name})" if item and getattr(item, "name", None) else "Cradle"
        elif kind == "nest":
            opts = getattr(feature, "options", {}) or {}
            is_photo = bool(opts.get("photo") or getattr(feature, "contour", None) is not None)
            name = "Snug Holder" if is_photo else "Nest"
        elif kind == "pocket":
            name = "Pocket"
        elif kind == "bore":
            name = "Bore"
        elif kind == "slot":
            name = "Slot"
        elif kind == "steps":
            name = "Steps"
        elif kind == "post":
            name = "Post"
        elif kind == "text":
            opts = getattr(feature, "options", {}) or {}
            txt = str(opts.get("text", "")).strip()
            name = f'Text ("{txt}")' if txt else "Text"
        else:
            name = kind.capitalize()
        counts[name] = counts.get(name, 0) + 1

    parts: list[str] = []
    for name, cnt in counts.items():
        if cnt > 1:
            parts.append(f"{cnt}x {name}")
        else:
            parts.append(name)
    if scoop:
        parts.append("Scoop")

    return ", ".join(parts) if parts else "None"


def log_bin_to_folder(
    output_dir: Path,
    box: BoxSpec,
    layout: Layout,
    generated_files: list[Path] | None = None,
    label: str = "",
    part_name: str = "",
    scoop: bool = False,
    b4b_note: str = "",
) -> Path:
    """Record a generated bin as a new row of the drawer inventory,
    '<folder name> bins.md' in output_dir (see organizer_inventory).

    ``b4b_note``, when set, replaces the Interior Part(s) cell and marks the
    row as a B4B case.
    """
    if generated_files:
        file_names = ", ".join(dict.fromkeys(p.name for p in generated_files))
    else:
        file_names = box_filename(box, part_name)

    tidy_label = clean_label(label)
    floor_texts = [
        str(f.options.get("text", "")).strip()
        for f in layout.features
        if getattr(f, "kind", "") == "text" and str(f.options.get("text", "")).strip()
    ]
    if tidy_label and floor_texts:
        label_text = f"{tidy_label} (rim), {', '.join(floor_texts)} (floor)"
    elif tidy_label:
        label_text = tidy_label
    elif floor_texts:
        label_text = f"{', '.join(floor_texts)} (floor)"
    else:
        label_text = "-"

    interior_text = b4b_note or summarize_interior_parts(layout, scoop=scoop)

    return append_bin(
        output_dir,
        file=file_names,
        x=box.x, y=box.y, z=box.z,
        label="" if label_text == "-" else label_text,
        interior=interior_text,
        name=clean_label(part_name) or tidy_label or (floor_texts[0] if floor_texts else ""),
        kind="b4b" if b4b_note else "bin",
        stack=getattr(getattr(box, "stack", None), "mode", "none"),
    )



def generate_side_file(
    box: BoxSpec,
    connector: ConnectorSpec,
    output: Path,
    along: str = "y",
    position: float = 0.0,
    length: float = LOCKED_CONNECTOR_LENGTH,
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
    web_thickness: float | None = None,
    auto_adjust: bool = True,
) -> dict[str, object]:
    mesh = make_side_connector(
        box, connector, along, position, length, bin_a_height, bin_b_height,
        web_thickness=web_thickness, auto_adjust=auto_adjust,
    )
    report = mesh_report("side_connector", mesh)
    overlap = validate_side_fit(
        box, connector, mesh, along, position, bin_a_height, bin_b_height
    )
    fit = {"seated_overlap_mm3": round(overlap, 6)}
    fit.update(measure_lock(
        box, connector, along, position, bin_a_height=bin_a_height,
        bin_b_height=bin_b_height,
    ))
    print_mesh = connector_for_print(mesh)
    export_mesh(print_mesh, output, "side_connector")
    fit.update({
        "bin_a_height_mm": bin_a_height if bin_a_height is not None else box.z,
        "bin_b_height_mm": bin_b_height if bin_b_height is not None else box.z,
        "print_orientation": "flat cap down",
    })
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
            box, output_dir / box_filename(box), label, label_location, scoop
        ),
        "side": generate_side_file(
            box,
            connector,
            output_dir / connector_filename(connector, wall=box.wall),
            side_along,
            side_position,
        ),
    }


def run_command(args: argparse.Namespace) -> dict[str, object]:
    if args.command == "sampler":
        return generate_sampler(
            output=args.output,
            sizes=parse_sizes(args.boxes),
            height=args.z,
            wall=args.wall,
            base_thickness=args.base_thickness,
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
            saved_box.base_thickness
            if args.base_thickness is None
            else args.base_thickness,
            easy_clean=saved_box.easy_clean if getattr(args, "easy_clean", None) is None else args.easy_clean,
            standard_base=saved_box.standard_base,
            easy_clean_radius=saved_box.easy_clean_radius if getattr(args, "easy_clean_radius", None) is None else args.easy_clean_radius,
            easy_clean_style=saved_box.easy_clean_style if getattr(args, "easy_clean_style", None) is None else args.easy_clean_style,
            standard_walls=(
                saved_box.standard_walls
                if args.wall is None
                else math.isclose(args.wall, DEFAULT_WALL, abs_tol=1e-9)
            ),
        )
        if args.mode:
            layout = replace(layout, mode=args.mode)
        label = saved_label if args.label is None else args.label
        location = (saved_label_location if args.label_position is None
                    else args.label_position)
        part = saved_part if args.part_name is None else args.part_name
        if clean_label(label) and label_position(location) == "bottom":
            # Sugar: a floor label from the command line is a text interior
            # part that finds its own spot, exactly as adding one in the
            # editor with "place it for me" left on would.
            layout = replace(
                layout,
                features=layout.features + (auto_text_feature(box, label, layout.mode),),
            )
            part = part or part_name_seed(label)
            label = ""
        return generate_organizer_files(
            box,
            layout,
            args.output_dir,
            label,
            part,
            location,
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


def _starter_span(
    available: float, wanted: float, mode: str = "fused", snap: float = EDITOR_SNAP
) -> float:
    """Largest starter span that keeps a new holder out of the connector strip.

    A starter sized to fill a small bin lands in the edge strip a side
    connector's arms need, and the draft then fails the instant the part is
    added - the user gets an error for doing nothing but clicking Add, on a bin
    the app itself called valid.  Backing the starter off to the connector-safe
    span keeps it buildable; dragging it out to the wall afterwards is a
    deliberate act and still earns the same explanatory error.

    Cartridge mode is left alone: its grid is already inset clear of the strip,
    so insetting again would only shrink the cell the part is meant to fill.

    Bins too small for a useful connector-safe span are left alone too, so they
    still report why rather than starting with a part too small to see.
    """
    span = min(wanted, available)
    if mode == "cartridge":
        return span
    safe = available - 2.0 * CONNECTOR_EDGE_KEEP_OUT
    if span < safe - 1e-9:      # strictly clear, never sitting on the line
        return span
    stepped = math.floor(safe / snap) * snap
    if stepped >= safe - 1e-9:          # strictly inside, never on the line
        stepped -= snap
    return stepped if stepped >= 4.0 else span


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
    if kind in {"cradle", "bore"}:
        item = item if item is not None else LIBRARY[item_key]
    else:
        item = None
    feature_options = {}
    if item is not None and kind == "cradle":
        required_length = item.length
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
        cradle_across = item.widest + _cradle_rib_thickness(item.widest)
        wanted_across = max(
            8.0,
            cradle_across,
        )
        across = min(
            available_across,
            math.ceil((wanted_across - 1e-9) / pitch) * pitch,
        )
        width, depth = ((required_length, across) if along == "x"
                        else (across, required_length))
    elif kind == "nest":
        width, depth = min(8.0, bounds.width), min(8.0, bounds.depth)
    elif kind == "divider":
        # Wall to wall on its own run axis by default, and spread across
        # the bin's whole other axis too - room for count > 1 to divide the
        # bin evenly without the user having to widen it by hand first.
        width, depth = bounds.width, bounds.depth
        # New Dividers start with one wall on X and none on Y (X=1, Y=0). Older saved
        # Dividers have neither key and continue through the legacy one-axis
        # path in divider_defaults().
        feature_options = {"count_x": 1, "count_y": 0}
    elif kind == "post":
        # A one-cell-wide cartridge cannot hold the normal 12 mm starter peg.
        # Size the starter diameter to both axes, then give it as much of the
        # usual 16 mm editing footprint as the layout has. Wider bins retain
        # the established 12 mm default unchanged.
        run_limit = bounds.width if along == "x" else bounds.depth
        across_limit = bounds.depth if along == "x" else bounds.width
        run = _starter_span(run_limit, 16.0, mode)
        across = _starter_span(across_limit, 16.0, mode)
        # The peg has to fit the zone it actually got, not the bin, and needs
        # material around it - sizing it to the bare span left a 12 mm peg in a
        # 12 mm zone, or worse, a peg wider than the zone once that snapped
        # down.  A cartridge peg is meant to fill its cell, so it keeps the
        # bare span.
        margin = 0.0 if mode == "cartridge" else MIN_FEATURE_GAP
        diameter = min(12.0, run - margin, across - margin)
        width, depth = ((run, across) if along == "x" else (across, run))
        feature_options = {"diameter": diameter, "height": 16.0, "taper": 0.4}
    elif kind == "slot":
        run = _starter_span(bounds.width if along == "x" else bounds.depth, 32.0, mode)
        # One explicit starter slot with a snug 8 mm Base. Raising Quantity in
        # the editor grows this axis automatically.
        across = _starter_span(bounds.depth if along == "x" else bounds.width, 8.0, mode)
        width, depth = ((run, across) if along == "x" else (across, run))
    elif kind == "steps":
        run = _starter_span(bounds.width if along == "x" else bounds.depth, 32.0, mode)
        across = _starter_span(bounds.depth if along == "x" else bounds.width, 32.0, mode)
        width, depth = ((run, across) if along == "x" else (across, run))
    elif kind == "scoop":
        along = "x"
        scoop_height = (box.z - box.base_thickness) * 0.6
        width, depth = bounds.width, min(scoop_height, bounds.depth / 2.0)
    elif kind == TEXT_KIND:
        # Wide and short, the shape lettering actually wants, and starting
        # life placed for itself rather than dumped in the middle.
        width = min(max(16.0, bounds.width * 0.6), bounds.width)
        depth = min(max(8.0, TEXT_CAP_HEIGHT_IDEAL + 2.0), bounds.depth)
        feature_options = {"text": "label", "auto": True, "quarter_turns": 0,
                           "raised": False, "depth": TEXT_DEPTH}
    else:
        width = _starter_span(bounds.width, 16.0, mode)
        depth = _starter_span(bounds.depth, 16.0, mode)
    raw = Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    one_zone = snapped_zone(raw, box, mode)
    if kind == "scoop":
        one = Feature(kind, one_zone, along=along, options=feature_options)
        one_zone = scoop_zone(
            box, one,
            box.base_thickness if mode == "fused" else box.base_thickness + BASE_PLATE,
            mode,
        )
    return Feature(
        kind,
        one_zone,
        item=item,
        # A cradle, like a post, starts as a single holder - Quantity "auto"
        # then fills the zone with lanes only when the user asks for it.
        count=3 if kind == "steps" else (1 if kind in {"post", "cradle", "slot"} else None),
        along=along,
        options=feature_options,
        full_span=(kind == "divider"),
    )


def auto_text_feature(box: BoxSpec, label: str, mode: str = "fused") -> Feature:
    """A text interior part that places itself, from a plain string.

    Used by the ``--label`` command-line sugar and anywhere else a piece of
    lettering arrives without a zone of its own. ``resolve_text_features``
    replaces the provisional zone with the spot it actually finds.
    """
    one = default_feature(box, TEXT_KIND, mode=mode)
    options = dict(one.options)
    options["text"] = str(label).strip()
    return replace(one, options=options)


def convert_layout_mode(
    box: BoxSpec, features: Iterable[Feature], mode: str
) -> Layout:
    """Snap every interior part onto a new mode's grid and validate the result."""
    converted_items = []
    for one in features:
        if one.kind == "nest" and one.contour:
            converted_items.append(fitted_nest_feature(one))
            continue
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
    """The saved design.

    ``label`` is the rim-ledge label and means something only when
    ``label_position`` names a rim side. Floor lettering lives in the layout as
    ``text`` interior parts - one per label, any number of them - so there is
    nothing for it here.
    """
    box = normalize_stack_settings(box)
    b4b = box.b4b.normalised()
    box_block = {
        "x": box.x,
        "y": box.y,
        "z": box.z,
        "wall": box.wall,
        "base_thickness": box.base_thickness,
        "corner_fillet": box.corner_fillet,
        "flat_inside": box.flat_inside,
        "easy_clean": box.easy_clean,
        "easy_clean_style": box.easy_clean_style,
        "easy_clean_radius": box.easy_clean_radius,
        "standard_base": box.standard_base,
        "standard_walls": bool(box.standard_walls) and math.isclose(
            box.wall, DEFAULT_WALL, abs_tol=1e-9
        ),
    }
    if b4b.enabled:
        box_block["b4b"] = {
            "enabled": True,
            "lid": b4b.lid,
            "secure_lid": b4b.secure_lid,
            "latch_count": b4b.latch_count,
            "latch_strength": b4b.latch_strength,
            "lid_headroom_mm": b4b.lid_headroom_mm,
            "label_text": b4b.label_text,
            "label_location": b4b.label_location,
            "stacking": b4b.stacking,
            "handle": b4b.handle,
            "version": b4b.version,
        }
    stack = getattr(box, "stack", None) or StackSpec()
    if stack.enabled:
        box_block["stack"] = {"mode": stack.mode}
    return {
        # Version 3 only when B4B is on. Version 3 changes B4B x/y from the
        # physical outside to the exact requested child field, so older builds
        # reject a B4B design instead of silently loading it as an ordinary bin.
        # Version 4 carried stacking with Z as detached closed height. Version
        # 5 makes Z the authoritative stack-module/pitch height.
        "version": 5 if stack.enabled else (3 if b4b.enabled else 1),
        "box": box_block,
        "label": label,
        "label_position": label_position(label_location),
        "scoop": bool(scoop),
        "part_name": part_name,
        "layout": layout_to_dict(layout),
    }


def design_from_dict(
    data: dict, *, validate_layout: bool = True
) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    design_version = data.get("version", 1)
    if design_version not in (1, 2, 3, 4, 5):
        raise ValueError(f"unsupported design version {data.get('version')!r}")
    raw = data["box"]
    stack_raw = raw.get("stack")
    stack = StackSpec()
    if isinstance(stack_raw, dict) and stack_raw.get("mode"):
        stack = StackSpec(mode=str(stack_raw["mode"]))
    b4b_raw = raw.get("b4b")
    b4b = B4BSpec()
    if isinstance(b4b_raw, dict) and bool(b4b_raw.get("enabled", False)):
        # Build the spec exactly as supplied - do NOT normalise yet.  Saved and
        # imported v2 JSON is authoritative user data: validate_b4b_design must
        # see any impossible combination before normalised() would rewrite it.
        b4b = B4BSpec(
            enabled=True,
            lid=bool(b4b_raw.get("lid", True)),
            secure_lid=bool(b4b_raw.get("secure_lid", True)),
            latch_count=str(b4b_raw.get("latch_count", "auto")),
            latch_strength=str(b4b_raw.get("latch_strength", "standard")),
            lid_headroom_mm=float(b4b_raw.get("lid_headroom_mm", 1.0)),
            label_text=str(b4b_raw.get("label_text", "")),
            label_location=str(b4b_raw.get("label_location", "top")),
            stacking=bool(b4b_raw.get("stacking", False)),
            # A pre-v2 ``handle`` meant a fixed arch on the lid top, and it was
            # on by default.  The bail that replaced it is body hardware with
            # real size requirements, so an old file carries the *intent*
            # forward and validation decides whether this case can keep it -
            # never inferred from the dimensions themselves.
            handle=bool(b4b_raw.get("handle", False)),
            version=int(b4b_raw.get("version", 1)),
        )
    x, y = float(raw["x"]), float(raw["y"])
    if b4b.enabled and design_version == 2:
        # Deterministic schema migration: v2 stored physical case X/Y and used
        # the reduced old rail capacity.  v3 stores that exact old capacity as
        # the requested child field.  Never guess semantics from dimensions.
        old_wall = float(raw.get("wall", DEFAULT_WALL))
        old_wall_depth = old_wall * math.sqrt(1.0 + max_wave_slope() ** 2)
        old_slack = 2.0 * (WAVE_MATING_GAP + old_wall_depth) / GRID_PITCH
        x = max(
            GRID_PITCH,
            math.floor(round(x / GRID_PITCH) - old_slack + 1e-6) * GRID_PITCH,
        )
        y = max(
            GRID_PITCH,
            math.floor(round(y / GRID_PITCH) - old_slack + 1e-6) * GRID_PITCH,
        )
    # Brief browser builds stored a requested usable size plus the wall
    # allowance. Recover the user's 8 mm modular choice when those designs are
    # reopened; every BoxSpec remains grid-locked after migration.
    if bool(raw.get("interior_sizing", False)):
        wall = float(raw.get("wall", DEFAULT_WALL))
        wall_depth = wall * math.sqrt(1.0 + max_wave_slope() ** 2)
        allowance = WAVE_MATING_GAP + 2.0 * wall_depth + 2.0 * WAVE_AMPLITUDE
        x = max(GRID_PITCH, round((x - allowance) / GRID_PITCH) * GRID_PITCH)
        y = max(GRID_PITCH, round((y - allowance) / GRID_PITCH) * GRID_PITCH)
    easy_clean_style = str(raw.get("easy_clean_style", "bevel"))
    if easy_clean_style not in {"bevel", "curve"}:
        easy_clean_style = "bevel"
    raw_wall = float(raw.get("wall", DEFAULT_WALL))
    if not math.isfinite(raw_wall) or not MIN_WALL <= raw_wall <= MAX_WALL:
        raise ValueError(
            f"wall thickness must be between {MIN_WALL:g} and {MAX_WALL:g} mm"
        )
    standard_walls = (
        bool(raw["standard_walls"])
        if "standard_walls" in raw
        else math.isclose(raw_wall, DEFAULT_WALL, abs_tol=1e-9)
    )
    wall = DEFAULT_WALL if standard_walls else raw_wall
    requested_z = float(raw["z"])
    # Preserve v4 physical geometry exactly: its Z was the detached closed
    # height, which equals the v5 module height plus the engagement depth.
    if design_version == 4 and stack.enabled:
        requested_z -= stack_step_depth(BoxSpec(stack=stack))
    box = BoxSpec(
        x, y, requested_z,
        wall,
        float(raw.get("corner_fillet", 0.6)),
        flat_inside=float(raw.get("flat_inside", 0.0)),
        base_thickness=float(raw.get("base_thickness", raw.get("wall", DEFAULT_WALL))),
        easy_clean=bool(raw.get("easy_clean", False)),
        standard_base=bool(raw.get("standard_base", True)),
        easy_clean_radius=float(raw.get("easy_clean_radius", EASY_CLEAN_RADIUS)),
        easy_clean_style=easy_clean_style,
        standard_walls=standard_walls,
        b4b=b4b,
        stack=stack,
    )
    box = normalize_stack_settings(box)
    if b4b.enabled:
        # A B4B interior is reserved for child bins.  Imported/saved JSON is
        # authoritative user data: if it still carries interior features, a
        # non-fused mode, Easy Clean or the flat-inside band, that is a real
        # conflict and must fail with an actionable message - never a silent
        # discard.  The UI's own conversion clears these before saving, so
        # well-formed B4B JSON passes straight through.
        raw_layout = data.get("layout", {}) or {}
        raw_features = raw_layout.get("features", []) or []
        raw_mode = str(raw_layout.get("mode", "fused"))
        validate_b4b_design(
            box,
            layout_feature_count=len(raw_features),
            layout_mode=raw_mode,
            easy_clean=bool(raw.get("easy_clean", False)),
            flat_inside=float(raw.get("flat_inside", 0.0) or 0.0),
        )
        # Normalize legacy no-lid data and adopt any required child-field growth
        # so reopened and saved designs show the exact capacity that will print.
        box = replace(
            box, easy_clean=False, flat_inside=0.0, b4b=box.b4b.normalised()
        )
        from organizer_b4b import b4b_effective_box
        box = b4b_effective_box(box)
        layout = Layout((), "fused", EDITOR_SNAP)
        label = str(data.get("label", ""))
        location = label_position(data.get("label_position", "bottom"))
        return (box, layout, label, str(data.get("part_name", "")), location, False)
    layout = layout_from_dict(data.get("layout", {}))
    base_z = base_height(box, layout.mode)
    layout = replace(layout, features=tuple(
        normalize_divider_scoop(box, one, base_z)
        if one.kind == "divider" else one
        for one in layout.features
    ))
    label = str(data.get("label", ""))
    location = label_position(data.get("label_position", "bottom"))
    scoop = bool(data.get("scoop", False))
    # The retired scoop checkbox made a real ramp but was not represented in
    # the interior-parts list. Turn it into the equivalent editable feature
    # when an older design is reopened, then retire the hidden flag.
    if scoop:
        if (not any(one.kind == "scoop" for one in layout.features)
                and not any(one.kind == "nest" and one.contour for one in layout.features)):
            legacy_zone = Zone(*scoop_floor_zone(
                box, _scoop_floor_bounds(box, layout.mode)
            ).bounds)
            layout = replace(
                layout,
                features=layout.features + (Feature("scoop", legacy_zone),),
            )
        scoop = False
    if validate_layout:
        # An auto text's stored zone is a cache of where it last landed, not
        # the authority - the resolver is. Re-run it before validating, so a
        # design saved with a holder since moved onto that spot still opens:
        # the lettering simply finds somewhere else, exactly as it would have
        # on screen.
        layout = replace(
            layout,
            features=resolve_text_features(
                box, layout.features,
                reserved=[
                    zone.polygon for _name, zone in _customization_zones(
                        box, clean_label(label), location, scoop, layout.mode
                    )
                ],
                base_z=base_height(box, layout.mode), mode=layout.mode,
            ),
        )
        layout.validate(box)
    return (box, layout, label, str(data.get("part_name", "")), location, scoop)


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
