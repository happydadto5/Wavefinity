"""Shared geometry/export services and command-line tools for Wavefinity."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
from typing import Iterable

import trimesh

from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    ConnectorSpec,
    GRID_PITCH,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    export_labelled_box,
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
    _cradle_rib_thickness,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
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
    fitted_nest_feature,
    make_insert_plate,
    snapped_zone,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm

SUPPORT_CATALOG = {
    "cradle": (
        "Cradle — tools laid down",
        "A half-circle notch that holds a screwdriver, marker or other tool on its side.",
    ),
    "nest": (
        "Photo Nest — custom part cavity",
        "Upload a flat overhead photo on letter paper to create a scaled cavity for one part.",
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
}
SUPPORT_ORDER = ("cradle", "nest", "bore", "post", "pocket", "divider")
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
     (("Width mm", "thickness", "1.6"), ("Height mm", "height", ""),
      ("Angle °", "angle", "0"), ("Spacing mm", "spacing", ""))),
    ("post", "Post", "A tapered peg for tape rolls, spools, sockets and rings.",
     {"qty": True, "size": False, "along": True, "item": False, "lean": False},
     (("Height mm", "height", "16"), ("Diameter mm", "diameter", "12"),
      ("Taper mm", "taper", "0.4"), ("Gap mm", "spacing", "4"))),
    ("pocket", "Pocket", "A raised open tray for loose small parts.",
     {"qty": False, "size": True, "along": False, "item": False, "lean": False},
     (("Height mm", "height", "12"), ("Wall mm", "wall", "1.6"),
      ("Recess mm", "depth", ""))),
    ("bore", "Bore", "A block of snug upright holes for tools stood on end.",
     {"qty": True, "size": True, "along": True, "item": True, "lean": False},
     (("Height mm", "height", ""), ("Hole depth mm", "depth", ""),
      ("Wall mm", "wall", "1.6"))),
    ("cradle", "Cradle", "A half-circle notch that holds a tool on its side.",
     {"qty": True, "size": False, "along": True, "item": True, "lean": False,
      "alternate": True},
     (("Spacing mm", "spacing", "0"), ("Floor gap mm", "floor_gap", "2"))),
    ("nest", "Photo Nest", "Upload a flat overhead photo on letter paper to create a scaled cavity for one part.",
     {"qty": False, "size": False, "along": False, "item": False, "lean": False,
      "alternate": False, "photo": True},
     (("Fit clearance (mm)", "clearance", "0.6"),
      ("Soften outline (mm)", "smoothing", "0"))),
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
        make_scoop(box, _scoop_floor_bounds(box, mode)), (0.0, 0.0, -box.wall)
    )


def base_height(box: BoxSpec, mode: str) -> float:
    """The z a holder is built up from: the bin floor, or the insert's plate."""
    return box.wall if mode == "fused" else box.wall + BASE_PLATE


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
    draft: Feature | None = None,
) -> dict[str, object]:
    """Build camera-independent preview geometry once per design change.

    ``draft`` is the support currently being edited, not yet added to the
    layout - included in the same geometry, tagged ``draft_<kind>`` instead
    of ``feature_<kind>``/``insert_<kind>`` so the browser can highlight it
    in place, right where it will actually sit, instead of drawing it alone
    on its own tiny canvas. It never affects ``feature_errors`` or
    ``invalid_feature_indexes`` - those describe the real layout - and a
    draft that fails to build still falls back to the same placeholder
    prism a placed feature would, reported through ``draft_error`` instead.
    """
    features = tuple(features)
    # Bare-cutter preview for a Photo Nest, whether it is already placed or is
    # still the draft being positioned before it is applied.
    nest_design = is_photo_nest_design(features) or (
        not features and draft is not None
        and draft.kind == "nest" and bool(draft.contour)
    )
    outer, cavity = preview_rings(box)
    floor_z, rim_z = box.wall, box.z
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
            else translated(_removable_scoop(box, mode), (0.0, 0.0, box.wall))
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

    draft_error = None
    if draft is not None:
        conflict = next(
            (name for name, zone in reserved if draft.zone.overlaps(zone, MIN_FEATURE_GAP)),
            None,
        )
        if conflict is not None:
            draft_error = f"{draft.kind}: overlaps the {conflict}"
        try:
            for solid in build_features(box, [draft], base_z, layout_zone(box, mode)):
                geometry.extend(_mesh_preview_geometry(solid, f"draft_{draft.kind}"))
        except Exception as error:
            draft_error = f"{draft.kind}: {error}"
            geometry.extend(_prism_geometry(
                draft.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, draft, base_z)),
                "draft_invalid",
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
        "draft_error": draft_error,
        "customization_zones": tuple(reserved),
        "size_text": (
            f"{math.floor(inside_x):g} X {math.floor(inside_y):g} (Inside) - "
            f"{box.x:g} X {box.y:g} mm (Outside)"
        ),
    }


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
    nest_only = is_photo_nest_design(layout.features)
    if nest_only:
        # The bare cutter wall has no surface to carry a label or a scoop.
        label, scoop = "", False
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

    if nest_only:
        # A Photo Nest is one bare cutter wall standing on the bed: no wavy
        # bin, no floor, and nothing for a label or scoop to attach to.
        body = union(build_features(box, list(layout.features), 0.0))
        output = output_dir / box_filename(box, tidy, part=part_name)
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
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
) -> dict[str, object]:
    mesh = make_side_connector(
        box, connector, along, position, length, bin_a_height, bin_b_height
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


def run_command(args: argparse.Namespace) -> dict[str, object]:
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
    else:
        width, depth = min(16.0, bounds.width), min(16.0, bounds.depth)
    raw = Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    return Feature(
        kind,
        snapped_zone(raw, box, mode),
        item=item,
        # A cradle, like a post, starts as a single holder - Quantity "auto"
        # then fills the zone with lanes only when the user asks for it.
        count=1 if kind in {"post", "cradle"} else None,
        along=along,
        options=feature_options,
        full_span=(kind == "divider"),
    )


def convert_layout_mode(
    box: BoxSpec, features: Iterable[Feature], mode: str
) -> Layout:
    """Snap every support onto a new mode's grid and validate the result."""
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
    )
    layout = layout_from_dict(data.get("layout", {}))
    if validate_layout:
        layout.validate(box)
    return (
        box,
        layout,
        str(data.get("label", "")),
        str(data.get("part_name", "")),
        label_position(data.get("label_position", "bottom")),
        bool(data.get("scoop", False)),
    )


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
