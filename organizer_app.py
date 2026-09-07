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

import trimesh

from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    ConnectorSpec,
    DEFAULT_BASE_THICKNESS,
    GRID_PITCH,
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
)
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
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
    build_features,
    build_texts,
    connector_keep_out,
    feature_footprint,
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
    resolve_text_features,
    snapped_zone,
    text_depth,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm

INTERIOR_PART_CATALOG = {
    "cradle": (
        "Cradle — tools laid down",
        "A half-circle notch that holds a screwdriver, marker or other tool on its side.",
    ),
    "nest": (
        "Photo Nest — custom part cavity",
        "Snug holder based on photo.",
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
    "divider": (
        "Divider — split the bin",
        "A straight wall that divides the usable floor into compartments.",
    ),
    "slot": (
        "Slot Rack — tilted tools",
        "Angled slots for driver bits, cards, and small tools.",
    ),
    "steps": (
        "Steps — tiered riser",
        "Stepped shelves rising from front to back.",
    ),
    "scoop": (
        "Curved Scoop — retrieval ramp",
        "A curved ramp rising up the wall for easy access to small parts.",
    ),
    TEXT_KIND: (
        "Text — a label on the floor",
        "Lettering sunk flush into the floor as its own colour.",
    ),
}
INTERIOR_PART_ORDER = (
    "cradle", "nest", "bore", "post", "pocket", "divider", "slot", "steps",
    "scoop",
    TEXT_KIND,
)
# The rim label is the one piece of lettering that is not an interior part: it
# lives on a shelf at the rear rim, not on the floor, so it has no zone to
# drag. "bottom" now simply means there is no rim label - floor lettering is a
# text interior part.
LABEL_POSITIONS = ("bottom", "top")


def label_position(value: str) -> str:
    position = str(value).strip().lower()
    if position not in LABEL_POSITIONS:
        raise ValueError("label position must be 'bottom' or 'top'")
    return position


# --- guided part palette ---------------------------------------------------
#
# Each entry drives the visual "pick a shape, then set its parameters" editor.
# ``flags`` say which of the shared controls (quantity / footprint / run axis /
# stored-item description) apply; ``fields`` are the parameters unique to that
# shape, as (label, builder-option key, default-or-blank).  A blank default
# means "let the builder choose".
PART_KINDS = (
    ("divider", "Divider", "A straight wall that splits the floor into compartments.",
     {"qty": True, "size": False, "along": True, "item": False, "lean": True},
     (("Width", "thickness", "1.6"), ("Height", "height", ""),
      ("Spacing", "spacing", ""),
      ("Slope °(±)", "bottom_angle", "0"),
      ("Number of crossbars", "bottom_supports", "3"),
      ("Wall lean °", "angle", "0"))),
    ("post", "Post", "A tapered peg for tape rolls, spools, sockets and rings.",
     {"qty": True, "size": False, "along": True, "item": False, "lean": False},
     (("Height", "height", "16"), ("Diameter", "diameter", "12"),
      ("Taper", "taper", "0.4"), ("Gap", "spacing", "4"))),
    ("pocket", "Pocket", "A raised open tray for loose small parts.",
     {"qty": False, "size": True, "along": False, "item": False, "lean": False},
     (("Height", "height", "12"), ("Wall", "wall", "1.6"),
      ("Recess", "depth", ""))),
    ("bore", "Bore", "A block of snug upright holes for tools stood on end.",
     {"qty": False, "size": True, "along": True, "item": True, "lean": False},
     (("Height", "height", ""), ("Hole depth", "depth", ""),
      ("Wall", "wall", "1.6"), ("X quantity", "columns", ""),
      ("Y quantity", "rows", ""), ("Angle °", "angle", "0"))),
    ("cradle", "Cradle", "A half-circle notch that holds a tool on its side.",
     {"qty": True, "size": False, "along": True, "item": True, "lean": False,
      "alternate": True},
     (("Spacing", "spacing", "0"), ("Floor gap", "floor_gap", "2"),
      ("% from ends", "end_margin", "10"))),
    ("nest", "Photo Nest", "Snug holder based on photo.",
     {"qty": False, "size": False, "along": False, "item": False, "lean": False,
      "alternate": False, "photo": True},
     (("Fit clearance", "clearance", "0.6"),
      ("Soften outline", "smoothing", "0"))),
    ("slot", "Slot Rack", "Angled slots for driver bits, cards, and small tools.",
     {"qty": True, "size": True, "along": True, "item": False, "lean": False},
     (("Height", "height", ""), ("Depth", "depth", ""),
      ("Thickness", "thickness", "4"), ("Angle °", "angle", "20"),
      ("Wall", "wall", "1.6"))),
    ("steps", "Steps", "Stepped shelves rising from front to back.",
     {"qty": True, "size": True, "along": True, "item": False, "lean": False},
     (("Height", "height", ""), ("Lip", "lip", "1"))),
    ("scoop", "Curved Scoop", "A curved retrieval ramp for easy access to small parts.",
     {"qty": False, "size": True, "along": True, "item": False, "lean": False},
     (("Height", "height", ""),)),
    (TEXT_KIND, "Text",
     "Lettering sunk into the base floor or rim level as its own colour.",
     {"qty": False, "size": True, "along": False, "item": False, "lean": False,
      "text": True},
     (("Letter height", "cap_height", ""), ("Depth", "depth", "0.4"))),
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
        f"--{option}wall", dest=f"{destination}wall", type=float, default=0.8
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
    sampler_parser.add_argument("--wall", type=float, default=0.8)
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
) -> str:
    tolerance = LOCKED_TOLERANCE if connector is None else connector.tolerance
    height = LOCKED_CONNECTOR_HEIGHT if connector is None else connector.height
    effective_arm = (
        arm_thickness
        if arm_thickness is not None
        else (DEFAULT_ARM_THICKNESS if connector is None else connector.arm_thickness)
    )

    diff = []
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


def is_photo_nest_design(features: Iterable[Feature]) -> bool:
    """True when the layout is a single Photo Nest with an uploaded outline.

    A Photo Nest prints on its own as a bare cutter wall - no wavy bin, no
    floor - so both the preview and the exporter skip the box shell for it and
    stand the wall straight on the print bed.
    """
    features = tuple(features)
    return (
        len(features) == 1
        and features[0].kind == "nest"
        and bool(features[0].contour)
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
        label_location = "top"
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
        label_location = "top"

    features = resolve_text_features(
        box, features,
        reserved=[
            zone.polygon for _name, zone in _customization_zones(
                box, clean_label(label), label_position(label_location), scoop, mode
            )
        ],
        base_z=base_height(box, mode), mode=mode,
    )
    # Bare-cutter preview for a Photo Nest, whether it is already placed or is
    # still the draft being positioned before it is applied.
    nest_design = is_photo_nest_design(features) or (
        not features and draft is not None
        and draft.kind == "nest" and bool(draft.contour)
    )
    outer, cavity = preview_rings(box)
    floor_z, rim_z = box.base_thickness, box.z
    geometry: list[tuple[list[tuple[float, float, float]], str,
                         tuple[float, float, float], int]] = []

    # A Photo Nest prints as a bare cutter wall standing on the bed, so its
    # preview omits the wavy bin shell and floor entirely.
    if not nest_design:
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
            else translated(
                _removable_scoop(box, mode),
                (0.0, 0.0, box.base_thickness),
            )
        )
        geometry.extend(_mesh_preview_geometry(scoop_mesh, "scoop"))

    plate = None if nest_design else insert_plate_solid(box, mode)
    if plate is not None:
        geometry.extend(_mesh_preview_geometry(plate, "insert_base"))
    base_z = 0.0 if nest_design else base_height(box, mode)
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

    # The rim label is the only lettering left that is not an interior part:
    # it sits on a shelf at the rear rim and has no zone to drag, so the
    # preview still draws it here. Floor text drew itself above, with every
    # other interior part.
    fits, message = True, ""
    label_outline_coords = []
    label_meta = None
    if tidy and location == "top":
        try:
            outline = top_label_outline(box, tidy)
            label_meta = {"location": "top"}
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
    rim_feature = next((one for one in layout.features if is_text(one) and one.options.get("level") == "rim"), None)
    if rim_feature is not None:
        label = text_of(rim_feature)
        label_location = "top"
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
    nest_only = is_photo_nest_design(layout.features)
    if nest_only:
        # The bare cutter wall has no surface to carry a label or a scoop.
        label, scoop = "", False
    tidy = clean_label(label)
    location = label_position(label_location)
    if tidy and location != "top":
        # Floor lettering is a text interior part now, so a label arriving here
        # for the floor is a caller mistake - say so rather than dropping it.
        raise ValueError(
            f"'{label}' is a floor label, and floor lettering is a text "
            "interior part now. Add one to the layout, or set the label "
            "position to 'top' for the rim ledge"
        )
    validate_customization_clearance(
        box, layout.features, tidy, location, scoop, layout.mode
    )
    label_info = top_label_report(box, tidy) if tidy else None
    text_surface = (
        box.base_thickness if layout.mode == "fused" and not nest_only
        else BASE_PLATE
    )
    text_limit = (
        None if layout.mode == "fused" or nest_only
        else insert_footprint(box, layout.mode)
    )
    texts = (
        [] if nest_only
        else build_texts(box, layout.features, text_surface, text_limit)
    )

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

    if nest_only:
        # A Photo Nest is one bare cutter wall standing on the bed: no wavy
        # bin, no floor, and nothing for a label or scoop to attach to.
        body = union(build_features(box, list(layout.features), 0.0))
        output = _resolve_file(box_filename, box, part_name)
        output_dir.mkdir(parents=True, exist_ok=True)
        export_mesh(body, output, "fused_organizer")
        result: dict[str, object] = {
            "mode": layout.mode,
            "box": _part_result(output, mesh_report("fused_organizer", body)),
            "layout": insert_report("fused_organizer", layout.features, body),
        }
    elif layout.mode == "fused":
        body = make_fused_box(box, layout.features, make_box(box))
        if scoop:
            body = union([body, make_scoop(box)])
        output = _resolve_file(box_filename, box, part_name)
        # The rim label's ledge is part of the body, so it goes on before the
        # floor text is sunk into it.
        inlays = list(texts)
        if tidy:
            body, ledge_inlay = make_top_labelled_box(box, tidy, body)
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
        box_output = _resolve_file(box_filename, box, part_name)
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
            pocketed_box, box_inlay = make_top_labelled_box(box, tidy, plain_box)
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
    if keep_log:
        out_files: list[Path] = []
        if "box" in result and isinstance(result["box"], dict) and "output" in result["box"]:
            out_files.append(Path(str(result["box"]["output"])))
        if "insert" in result and isinstance(result["insert"], dict) and "output" in result["insert"]:
            out_files.append(Path(str(result["insert"]["output"])))
        log_file = log_bin_to_folder(
            output_dir,
            box,
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
            name = "Photo Nest" if is_photo else "Nest"
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
) -> Path:
    """Record a generated/printed bin in '<folder name> bins.md' in output_dir."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    folder_name = output_dir.name
    log_file = output_dir / f"{folder_name} bins.md"

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

    interior_text = summarize_interior_parts(layout, scoop=scoop)

    file_names = file_names.replace("|", "/")
    label_text = label_text.replace("|", "/")
    interior_text = interior_text.replace("|", "/")

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    row = f"| {now_str} | {file_names} | {box.x:g} | {box.y:g} | {box.z:g} | {label_text} | {interior_text} |\n"

    header = (
        f"# {folder_name} Bins\n\n"
        "| Date | File | X (mm) | Y (mm) | Z (mm) | Label | Interior Part(s) |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
    )

    if not log_file.exists():
        log_file.write_text(header + row, encoding="utf-8")
    else:
        content = log_file.read_text(encoding="utf-8")
        if "| Date |" not in content or "| --- |" not in content:
            if not content.endswith("\n"):
                content += "\n"
            content += "\n" + header + row
            log_file.write_text(content, encoding="utf-8")
        else:
            if not content.endswith("\n"):
                content += "\n"
            content += row
            log_file.write_text(content, encoding="utf-8")

    return log_file



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
            output_dir / connector_filename(connector),
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
    elif kind == "post":
        # A one-cell-wide cartridge cannot hold the normal 12 mm starter peg.
        # Size the starter diameter to both axes, then give it as much of the
        # usual 16 mm editing footprint as the layout has. Wider bins retain
        # the established 12 mm default unchanged.
        run_limit = bounds.width if along == "x" else bounds.depth
        across_limit = bounds.depth if along == "x" else bounds.width
        diameter = min(12.0, run_limit, across_limit)
        run = min(16.0, run_limit)
        across = min(16.0, across_limit)
        width, depth = ((run, across) if along == "x" else (across, run))
        feature_options = {"diameter": diameter, "height": 16.0, "taper": 0.4}
    elif kind == "slot":
        run = min(32.0, bounds.width if along == "x" else bounds.depth)
        across = min(24.0, bounds.depth if along == "x" else bounds.width)
        width, depth = ((run, across) if along == "x" else (across, run))
    elif kind == "steps":
        run = min(32.0, bounds.width if along == "x" else bounds.depth)
        across = min(32.0, bounds.depth if along == "x" else bounds.width)
        width, depth = ((run, across) if along == "x" else (across, run))
    elif kind == "scoop":
        run = min(16.0, bounds.depth if along == "x" else bounds.width)
        across = bounds.width if along == "x" else bounds.depth
        width, depth = ((across, run) if along == "x" else (run, across))
    elif kind == TEXT_KIND:
        # Wide and short, the shape lettering actually wants, and starting
        # life placed for itself rather than dumped in the middle.
        width = min(max(16.0, bounds.width * 0.6), bounds.width)
        depth = min(max(8.0, TEXT_CAP_HEIGHT_IDEAL + 2.0), bounds.depth)
        feature_options = {"text": "label", "auto": True, "quarter_turns": 0,
                           "raised": False, "depth": TEXT_DEPTH}
    else:
        width, depth = min(16.0, bounds.width), min(16.0, bounds.depth)
    raw = Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    return Feature(
        kind,
        snapped_zone(raw, box, mode),
        item=item,
        # A cradle, like a post, starts as a single holder - Quantity "auto"
        # then fills the zone with lanes only when the user asks for it.
        count=3 if kind == "steps" else (1 if kind in {"post", "cradle"} else None),
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
    ``label_position`` is ``"top"``. Floor lettering lives in the layout as
    ``text`` interior parts - one per label, any number of them - so there is
    nothing for it here.
    """
    return {
        "version": 1,
        "box": {
            "x": box.x,
            "y": box.y,
            "z": box.z,
            "wall": box.wall,
            "base_thickness": box.base_thickness,
            "corner_fillet": box.corner_fillet,
            "flat_inside": box.flat_inside,
        },
        "label": label,
        "label_position": label_position(label_location),
        "scoop": bool(scoop),
        "part_name": part_name,
        "layout": layout_to_dict(layout),
    }


def design_from_dict(
    data: dict, *, validate_layout: bool = True
) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    if data.get("version", 1) != 1:
        raise ValueError(f"unsupported design version {data.get('version')!r}")
    raw = data["box"]
    x, y = float(raw["x"]), float(raw["y"])
    # Brief browser builds stored a requested usable size plus the wall
    # allowance. Recover the user's 8 mm modular choice when those designs are
    # reopened; every BoxSpec remains grid-locked after migration.
    if bool(raw.get("interior_sizing", False)):
        wall = float(raw.get("wall", 0.8))
        wall_depth = wall * math.sqrt(1.0 + max_wave_slope() ** 2)
        allowance = WAVE_MATING_GAP + 2.0 * wall_depth + 2.0 * WAVE_AMPLITUDE
        x = max(GRID_PITCH, round((x - allowance) / GRID_PITCH) * GRID_PITCH)
        y = max(GRID_PITCH, round((y - allowance) / GRID_PITCH) * GRID_PITCH)
    box = BoxSpec(
        x, y, float(raw["z"]),
        float(raw.get("wall", 0.8)),
        float(raw.get("corner_fillet", 0.6)),
        flat_inside=float(raw.get("flat_inside", 0.0)),
        base_thickness=float(raw.get("base_thickness", raw.get("wall", 0.8))),
    )
    layout = layout_from_dict(data.get("layout", {}))
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
