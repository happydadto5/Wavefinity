"""Command-line and desktop application for the wavy organizer generator."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
import sys
from typing import Iterable

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
    make_labelled_box,
    placed_label_outline,
    preview_rings,
    make_box,
    make_side_connector,
    measure_lock,
    mesh_report,
    validate_side_fit,
)
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    EDITOR_SNAP,
    FEATURE_BUILDERS,
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
    insert_report,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    make_cartridge_insert,
    make_fitted_insert,
    make_fused_box,
    moved_feature,
    resized_feature,
    snapped_zone,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm

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
        help="sunk floor inlay, as a second object for a second colour",
    )
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


def preview_geometry(
    box: BoxSpec, label: str = "", features: Iterable[Feature] = (),
    mode: str = "fused",
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

    if mode != "fused":
        geometry.extend(_prism_geometry(
            layout_zone(box, mode), box.wall, box.wall + BASE_PLATE, "insert_base"
        ))
    base_z = box.wall if mode == "fused" else box.wall + BASE_PLATE
    feature_errors = []
    invalid_feature_indexes = []
    for feature_index, one in enumerate(features):
        try:
            for solid in build_features(
                box, [one], base_z, layout_zone(box, mode)
            ):
                geometry.extend(_mesh_preview_geometry(solid, f"feature_{one.kind}"))
        except Exception as error:
            feature_errors.append(f"{one.kind}: {error}")
            invalid_feature_indexes.append(feature_index)
            geometry.extend(_prism_geometry(
                one.zone,
                base_z,
                min(box.z - 0.25, _feature_height(box, one, base_z)),
                "feature_invalid",
            ))

    fits, message = True, ""
    tidy = clean_label(label)
    if tidy:
        occupied = [one.zone.polygon for one in features]
        if mode == "cartridge":
            occupied.append(Zone.whole(box).polygon.difference(cartridge_zone(box).polygon))
        try:
            outline = placed_label_outline(box, tidy, occupied)
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
            label_z = floor_z if mode == "fused" else box.wall + BASE_PLATE
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
) -> dict[str, object]:
    """The box as 3D faces ordered far to near, plus its dimension text.

    Built outside the widget code so the layout can be checked without opening
    a window.  Faces pointing away from the camera are dropped first - painting
    order alone cannot hide the far outside wall, because from above its top
    edge is genuinely nearer the camera than the floor is.
    """
    return project_preview(preview_geometry(box, label, features, mode), camera)


def preview_transform(
    box: BoxSpec, size: int = PREVIEW_SIZE, pad: int = PREVIEW_PAD,
    camera: PreviewCamera | None = None,
):
    """Millimetres to canvas pixels: isometric, centred, scaled to fit."""
    corners = [
        iso_point((sx * box.x / 2.0, sy * box.y / 2.0, z), camera)
        for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, box.z)
    ]
    us = [u for u, _ in corners]
    vs = [v for _, v in corners]
    span = max(max(us) - min(us), max(vs) - min(vs)) or 1.0
    camera = (camera or PreviewCamera()).normalized()
    scale = (size - 2 * pad) / span * camera.zoom
    mid_u = (max(us) + min(us)) / 2.0
    mid_v = (max(vs) + min(vs)) / 2.0

    def to_canvas(point: tuple[float, float, float]) -> tuple[float, float]:
        u, v = iso_point(point, camera)
        return size / 2.0 + (u - mid_u) * scale, size / 2.0 + (v - mid_v) * scale

    return to_canvas


def generate_box_file(
    box: BoxSpec, output: Path, label: str = ""
) -> dict[str, object]:
    """Write the box, plus a sunk floor label as a second object if asked.

    An empty label changes nothing: one object, and the plain filename.
    """
    tidy = clean_label(label)
    if not tidy:
        mesh = make_box(box)
        report = mesh_report("wavy_box", mesh)
        export_mesh(mesh, output, "wavy_box")
        return _part_result(output, report)

    pocketed, inlay = make_labelled_box(box, tidy)
    report = mesh_report("wavy_box", pocketed)
    export_labelled_box(pocketed, inlay, output, box_filename(box, suffix=""), tidy)
    result = _part_result(output, report)
    result["label"] = label_report(box, tidy)
    return result


def _label_obstacles(box: BoxSpec, layout: Layout) -> list:
    occupied = [one.zone.polygon for one in layout.features]
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
) -> dict[str, object]:
    """Export an editor design as fused, fitted-removable, or cartridge parts."""
    layout.validate(box)
    tidy = clean_label(label)
    obstacles = _label_obstacles(box, layout)
    label_info = label_report(box, tidy, obstacles) if tidy else None

    if layout.mode == "fused":
        body = make_fused_box(box, layout.features, make_box(box))
        output = output_dir / box_filename(box, tidy, part=part_name)
        if tidy:
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
        box_output = output_dir / box_filename(box, part=part_name)
        plain_box = make_box(box)
        insert = (
            make_cartridge_insert(box, layout.features)
            if layout.mode == "cartridge"
            else make_fitted_insert(box, layout.features)
        )
        insert_output = output_dir / insert_filename(
            box, tidy, part_name, layout.mode == "cartridge"
        )
        if tidy:
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
        export_mesh(plain_box, box_output, "wavy_box")
        if tidy:
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
            "box": _part_result(box_output, mesh_report("wavy_box", plain_box)),
            "insert": _part_result(
                insert_output, mesh_report("organizer_insert", reported_insert)
            ),
            "layout": insert_report("organizer_insert", layout.features, insert),
        }
    if label_info is not None:
        result["label"] = label_info
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
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "box": generate_box_file(box, output_dir / box_filename(box, label), label),
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
        return generate_box_file(_box_spec(args), args.output, args.label)
    if args.command == "organizer":
        raw = json.loads(args.layout.read_text(encoding="utf-8"))
        if "box" in raw:
            saved_box, layout, saved_label, saved_part = design_from_dict(raw)
        else:
            saved_box, layout, saved_label, saved_part = BoxSpec(), layout_from_dict(raw), "", ""
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
) -> Feature:
    """A useful, valid starting rectangle for a newly-added holder."""
    if kind not in FEATURE_BUILDERS:
        raise ValueError(f"unknown holder {kind!r}")
    bounds = layout_zone(box, mode)
    item = LIBRARY[item_key] if kind in {"cradle", "bore", "nest"} else None
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
    base_z = box.wall if mode == "fused" else box.wall + BASE_PLATE
    build_features(box, converted, base_z, layout_zone(box, mode))
    return layout


def design_to_dict(
    box: BoxSpec, layout: Layout, label: str = "", part_name: str = ""
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
        "part_name": part_name,
        "layout": layout_to_dict(layout),
    }


def design_from_dict(data: dict) -> tuple[BoxSpec, Layout, str, str]:
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
    return box, layout, str(data.get("label", "")), str(data.get("part_name", ""))


MIN_UNITS = int(round(MIN_BOX_SIZE / BASE_UNIT))
BASIC_FIELDS = (
    (f"Box width X (units of {BASE_UNIT:.0f} mm)", "x_units", 1.0, MIN_UNITS),
    (f"Box depth Y (units of {BASE_UNIT:.0f} mm)", "y_units", 1.0, MIN_UNITS),
    ("Box height Z (mm)", "z", None, None),
    ("Floor label (blank for none)", "label", None, None),
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
    root.title("Wavy Drawer Organizer Generator")
    root.minsize(1060, 790)

    BODY = ("Segoe UI", 10)
    VALUE = ("Segoe UI", 12)
    STEP = ("Segoe UI", 13, "bold")

    style = ttk.Style(root)
    style.configure("TLabel", font=BODY)
    style.configure("TCheckbutton", font=BODY)
    style.configure("TRadiobutton", font=BODY)
    style.configure("Head.TLabel", font=("Segoe UI", 17, "bold"))
    style.configure("Note.TLabel", font=("Segoe UI", 9), foreground="#666666")
    style.configure("Field.TEntry", padding=4)
    # A number gets a big obvious stepper either side of it rather than the
    # pinhead arrows a Spinbox draws.
    style.configure("Step.TButton", font=STEP, padding=(0, 0), width=3)
    style.configure("Go.TButton", font=("Segoe UI", 11, "bold"), padding=(10, 9))
    style.configure("Small.TButton", font=("Segoe UI", 9), padding=(8, 4))

    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame, text="Wavy Drawer Organizer Generator", style="Head.TLabel"
    ).grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(
        frame,
        text=(
            f"X and Y step in {GRID_PITCH:.0f} mm from {MIN_BOX_SIZE:.0f} mm up, so any "
            f"two boxes interlock.  Connector locked at {LOCKED_TOLERANCE:.2f} mm, "
            f"{LOCKED_CONNECTOR_LENGTH:.0f} x {LOCKED_CONNECTOR_HEIGHT:.1f} mm."
        ),
        style="Note.TLabel",
    ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 14))

    values = {
        "x_units": tk.StringVar(value="2"),
        "y_units": tk.StringVar(value="6"),
        "z": tk.StringVar(value="40"),
        "label": tk.StringVar(value=""),
        "part": tk.StringVar(value=""),
        "wall": tk.StringVar(value="0.8"),
        "flat_inside": tk.StringVar(value="0"),
        "tolerance": tk.StringVar(value=f"{LOCKED_TOLERANCE:g}"),
        "height": tk.StringVar(value=f"{LOCKED_CONNECTOR_HEIGHT:g}"),
        "side_length": tk.StringVar(value=f"{LOCKED_CONNECTOR_LENGTH:g}"),
        "side_axis": tk.StringVar(value="y"),
        "side_position": tk.StringVar(value="0"),
        "mode": tk.StringVar(value="fused"),
        "feature_kind": tk.StringVar(value=support_display("cradle")),
        "support_help": tk.StringVar(value=support_help("cradle")),
        "feature_item": tk.StringVar(value="nozzle"),
        "feature_along": tk.StringVar(value="x"),
        "feature_count": tk.StringVar(value="auto"),
        "feature_x": tk.StringVar(value="0"),
        "feature_y": tk.StringVar(value="0"),
        "feature_width": tk.StringVar(value="13"),
        "feature_depth": tk.StringVar(value="8"),
        "item_name": tk.StringVar(value="Printer nozzle"),
        "item_segments": tk.StringVar(value="13x6"),
        "item_profile": tk.StringVar(value="round"),
        "item_clearance": tk.StringVar(value="0.4"),
        "feature_options": tk.StringVar(value=""),
        "output": tk.StringVar(value=str(APP_DIR / "generated")),
    }
    show_advanced = tk.BooleanVar(value=False)
    features: list[Feature] = []
    selected = {"index": None}
    mode_state = {"value": "fused"}
    camera = {"value": PreviewCamera(), "drag": None}
    preview_cache = {"spec": None, "geometry": None}

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

    form = ttk.Frame(frame)
    form.grid(row=2, column=0, columnspan=2, sticky="nw")

    add_number(form, 0, f"Width X  (units of {BASE_UNIT:.0f} mm)", "x_units", 1.0, MIN_UNITS)
    add_number(form, 1, f"Depth Y  (units of {BASE_UNIT:.0f} mm)", "y_units", 1.0, MIN_UNITS)
    add_number(form, 2, "Height Z  (mm)", "z", 5.0, 5.0)
    add_text(form, 3, "Floor label", "label")
    add_text(form, 4, "Part name", "part")
    ttk.Label(form, text="Insert form").grid(row=5, column=0, sticky="w", pady=3)
    mode_row = ttk.Frame(form)
    mode_row.grid(row=5, column=1, sticky="w", padx=(10, 0), pady=3)
    for text, value in (
        ("Fused", "fused"), ("Removable", "separate"), ("8 mm cartridge", "cartridge")
    ):
        ttk.Radiobutton(
            mode_row, text=text, variable=values["mode"], value=value,
            command=lambda: change_mode_action(),
        ).pack(side="left", padx=(0, 8))

    views = ttk.Notebook(frame)
    views.grid(row=2, column=2, rowspan=3, sticky="ne", padx=(24, 0))
    preview_tab = ttk.Frame(views)
    layout_tab = ttk.Frame(views)
    views.add(preview_tab, text="3D preview")
    views.add(layout_tab, text="2D layout")

    preview = tk.Canvas(
        preview_tab, width=PREVIEW_SIZE, height=PREVIEW_SIZE,
        background="white", highlightthickness=1, highlightbackground="#cccccc",
    )
    preview.pack(fill="both", expand=True)
    layout_canvas = tk.Canvas(
        layout_tab, width=PREVIEW_SIZE, height=PREVIEW_SIZE,
        background="white", highlightthickness=1, highlightbackground="#cccccc",
    )
    layout_canvas.pack(fill="both", expand=True)

    FACE_COLOURS = {
        "outside": "#8fb8cc",
        "rim": "#bcd6e1",
        "inside": "#6b93a8",
        "floor": "#e8f0f4",
        "label": "#d9544d",
        "label_hole": "#e8f0f4",
        "insert_base": "#d9e4e8",
        "feature_cradle": "#e59f54",
        "feature_nest": "#df8d5b",
        "feature_bore": "#6fb98f",
        "feature_post": "#51a5a1",
        "feature_divider": "#9d86c8",
        "feature_pocket": "#d4778c",
        "feature_slot": "#d5b84d",
        "feature_invalid": "#d9534f",
    }

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

    def draw_preview() -> None:
        preview.delete("all")
        spec = preview_cache["spec"]
        geometry = preview_cache["geometry"]
        if spec is None or geometry is None:
            preview.create_text(
                PREVIEW_SIZE / 2, PREVIEW_SIZE / 2,
                text="-", fill="#999999", font=("Segoe UI", 11),
            )
            return

        scene = project_preview(geometry, camera["value"])
        to_canvas = preview_transform(spec, camera=camera["value"])
        for points, kind in scene["faces"]:
            colour = FACE_COLOURS.get(kind, "#d99b62")
            outline = "" if kind in ("label", "label_hole") else colour
            preview.create_polygon(
                [c for point in points for c in to_canvas(point)],
                fill=colour, outline=outline,
            )

        dimension = ("Segoe UI", 11, "bold")
        preview.create_text(
            PREVIEW_SIZE / 2, PREVIEW_SIZE - 12,
            text=scene["x_text"], font=dimension, fill="#333333",
        )
        preview.create_text(
            14, PREVIEW_SIZE / 2, text=scene["y_text"],
            font=dimension, fill="#333333", angle=90,
        )
        preview.create_text(
            PREVIEW_SIZE - 10, 14, text=scene["z_text"],
            font=("Segoe UI", 10), fill="#666666", anchor="ne",
        )
        if not scene["fits"]:
            preview.create_text(
                PREVIEW_SIZE / 2, 28, text="label will not fit",
                fill="#c0392b", font=("Segoe UI", 10, "bold"),
            )
        if scene["feature_errors"]:
            preview.create_text(
                PREVIEW_SIZE / 2,
                44 if not scene["fits"] else 28,
                text="selected support settings are invalid",
                fill="#c0392b",
                font=("Segoe UI", 9, "bold"),
            )
        preview.create_text(
            PREVIEW_SIZE / 2, 12,
            text="drag to rotate  •  wheel to zoom  •  double-click to reset",
            fill="#777777", font=("Segoe UI", 8),
        )

    def draw_layout() -> None:
        layout_canvas.delete("all")
        try:
            spec = current_box()
            bounds = layout_zone(spec, values["mode"].get())
        except Exception:
            layout_canvas.create_text(
                PREVIEW_SIZE / 2, PREVIEW_SIZE / 2, text="-", fill="#999999"
            )
            return
        scale = (PREVIEW_SIZE - 2 * PREVIEW_PAD) / max(bounds.width, bounds.depth)

        def point(x: float, y: float) -> tuple[float, float]:
            return PREVIEW_SIZE / 2 + x * scale, PREVIEW_SIZE / 2 - y * scale

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
        for index, one in enumerate(features):
            if (one.zone.x0 < bounds.x0 - 1e-6 or one.zone.x1 > bounds.x1 + 1e-6
                    or one.zone.y0 < bounds.y0 - 1e-6 or one.zone.y1 > bounds.y1 + 1e-6):
                collision_indexes.add(index)
            for other_index, other in enumerate(features[index + 1:], index + 1):
                if one.zone.overlaps(other.zone, MIN_FEATURE_GAP):
                    collision_indexes.update((index, other_index))
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
                placement = label_placement(spec, tidy, _label_obstacles(spec, current_layout()))
                lx, ly = point(placement.x, placement.y)
                layout_canvas.create_text(
                    lx, ly, text=tidy, fill="#b83934", font=("Segoe UI", 9, "bold"),
                    angle=90 if placement.rotated else 0,
                )
            except ValueError:
                layout_canvas.create_text(
                    PREVIEW_SIZE / 2, 13, text="label will not fit",
                    fill="#c0392b", font=("Segoe UI", 9, "bold"),
                )
        inside_x, inside_y = spec.usable_inside
        layout_canvas.create_text(
            PREVIEW_SIZE / 2, PREVIEW_SIZE - 12,
            text=f"{spec.x:g}mm ({math.floor(inside_x):g} inside)",
            font=("Segoe UI", 9, "bold"), fill="#333333",
        )
        layout_canvas.create_text(
            13, PREVIEW_SIZE / 2,
            text=f"{spec.y:g}mm ({math.floor(inside_y):g} inside)", angle=90,
            font=("Segoe UI", 9, "bold"), fill="#333333",
        )
        layout_canvas.create_text(
            PREVIEW_SIZE - 8, 8, text=f"{spec.z:g}mm tall", anchor="ne",
            font=("Segoe UI", 8), fill="#666666",
        )
        layout_canvas._world = (point, scale, bounds)  # transient interaction state

    def refresh_translation(*_args) -> None:
        try:
            spec = current_box()
            preview_cache["spec"] = spec
            preview_cache["geometry"] = preview_geometry(
                spec, values["label"].get(), features, values["mode"].get()
            )
        except Exception:
            preview_cache["spec"] = preview_cache["geometry"] = None
            draw_preview()
            draw_layout()
            return
        draw_preview()
        draw_layout()

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

    preview.bind("<ButtonPress-1>", preview_press)
    preview.bind("<B1-Motion>", preview_drag)
    preview.bind("<ButtonRelease-1>", lambda _event: camera.update(drag=None))
    preview.bind("<MouseWheel>", preview_zoom)
    preview.bind("<Button-4>", preview_zoom)
    preview.bind("<Button-5>", preview_zoom)
    preview.bind("<Double-Button-1>", preview_reset)

    for key in ("x_units", "y_units", "z", "wall", "flat_inside", "label"):
        values[key].trace_add("write", refresh_translation)

    ttk.Checkbutton(
        frame, text="Advanced settings", variable=show_advanced,
        command=lambda: toggle_advanced(),
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(14, 2))

    advanced = ttk.Frame(frame)
    advanced.grid(row=4, column=0, columnspan=2, sticky="nw")
    for index, (label, key, step, lowest) in enumerate(ADVANCED_FIELDS):
        add_number(advanced, index, label, key, step or 0.1, lowest or 0.0)
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

    # --- insert layout editor -------------------------------------------------
    editor = ttk.LabelFrame(
        frame,
        text="Interior supports — drag to move, drag the blue corner to resize (1 mm snap)",
        padding=8,
    )
    editor.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(14, 0))

    tools_row = ttk.Frame(editor)
    tools_row.pack(fill="x")
    ttk.Label(tools_row, text="Interior support").pack(side="left")
    support_choices = tuple(
        support_display(kind)
        for kind in (*SUPPORT_ORDER, *sorted(set(FEATURE_BUILDERS) - set(SUPPORT_ORDER)))
        if kind in FEATURE_BUILDERS
    )
    kind_combo = ttk.Combobox(
        tools_row, textvariable=values["feature_kind"],
        values=support_choices, state="readonly", width=34,
    )
    kind_combo.pack(side="left", padx=(5, 10))

    support_note = ttk.Label(
        editor, textvariable=values["support_help"], style="Note.TLabel",
        wraplength=920, justify="left",
    )
    support_note.pack(fill="x", pady=(5, 0))

    def sync_feature_fields() -> None:
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
            return
        one = features[index]
        cx, cy = one.zone.centre
        values["feature_kind"].set(support_display(one.kind))
        if one.item is not None:
            key = next((key for key, item in LIBRARY.items() if item == one.item), None)
            if key:
                values["feature_item"].set(key)
            values["item_name"].set(one.item.name)
            values["item_segments"].set(format_segments(one.item))
            values["item_profile"].set(one.item.profile)
            values["item_clearance"].set(f"{one.item.clearance:g}")
        values["feature_along"].set(one.along)
        values["feature_count"].set("auto" if one.count is None else str(one.count))
        values["feature_x"].set(f"{cx:g}")
        values["feature_y"].set(f"{cy:g}")
        values["feature_width"].set(f"{one.zone.width:g}")
        values["feature_depth"].set(f"{one.zone.depth:g}")
        values["feature_options"].set(format_feature_options(one.options))
        refresh_support_controls()

    def choose_library_item(_event=None) -> None:
        item = LIBRARY[values["feature_item"].get()]
        values["item_name"].set(item.name)
        values["item_segments"].set(format_segments(item))
        values["item_profile"].set(item.profile)
        values["item_clearance"].set(f"{item.clearance:g}")

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
        for centre in candidates:
            placed = moved_feature(one, spec, centre, mode)
            if all(
                not placed.zone.overlaps(other.zone, MIN_FEATURE_GAP)
                for other in features
            ):
                return placed
        raise ValueError("there is no open floor area large enough for that holder")

    def add_feature_action() -> None:
        try:
            spec = current_box()
            one = default_feature(
                spec, support_kind(values["feature_kind"].get()),
                values["feature_item"].get(),
                values["feature_along"].get(), values["mode"].get(),
            )
            one = first_open_position(one, spec, values["mode"].get())
            features.append(one)
            selected["index"] = len(features) - 1
            sync_feature_fields()
            refresh_translation()
        except Exception as error:
            messagebox.showerror("Could not add support", str(error))

    def delete_feature_action() -> None:
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
            return
        del features[index]
        selected["index"] = min(index, len(features) - 1) if features else None
        sync_feature_fields()
        refresh_translation()

    def apply_feature_action() -> None:
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
            return
        try:
            spec = current_box()
            kind = support_kind(values["feature_kind"].get())
            item = (
                Item(
                    values["item_name"].get().strip() or "Custom item",
                    parse_segments(values["item_segments"].get()),
                    values["item_profile"].get(),
                    float(values["item_clearance"].get()),
                )
                if kind in {"cradle", "nest", "bore"} else None
            )
            count_text = values["feature_count"].get().strip().lower()
            count = None if count_text in {"", "auto"} else int(count_text)
            one = replace(
                features[index], kind=kind, item=item, count=count,
                along=values["feature_along"].get(),
                options=parse_feature_options(values["feature_options"].get()),
            )
            one = resized_feature(
                one, spec,
                (float(values["feature_width"].get()), float(values["feature_depth"].get())),
                values["mode"].get(),
            )
            one = moved_feature(
                one, spec,
                (float(values["feature_x"].get()), float(values["feature_y"].get())),
                values["mode"].get(),
            )
            features[index] = one
            sync_feature_fields()
            refresh_translation()
        except Exception as error:
            messagebox.showerror("Could not update support", str(error))

    def rotate_feature_action() -> None:
        index = selected["index"]
        if index is None or not 0 <= index < len(features):
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

    ttk.Button(tools_row, text="Add support", command=add_feature_action).pack(side="left")
    ttk.Button(tools_row, text="Update selected", command=apply_feature_action).pack(side="left", padx=(6, 0))
    ttk.Button(tools_row, text="Rotate", command=rotate_feature_action).pack(side="left", padx=(6, 0))
    ttk.Button(tools_row, text="Delete", command=delete_feature_action).pack(side="left", padx=(6, 0))

    props = ttk.Frame(editor)
    props.pack(fill="x", pady=(7, 0))
    for label, key, width in (
        ("Center X", "feature_x", 7), ("Center Y", "feature_y", 7),
        ("Width", "feature_width", 7), ("Depth", "feature_depth", 7),
        ("Count", "feature_count", 7),
    ):
        ttk.Label(props, text=label).pack(side="left", padx=(0, 3))
        ttk.Entry(props, textvariable=values[key], width=width).pack(side="left", padx=(0, 9))
    ttk.Label(props, text="Runs along").pack(side="left")
    ttk.Radiobutton(props, text="X", variable=values["feature_along"], value="x").pack(side="left")
    ttk.Radiobutton(props, text="Y", variable=values["feature_along"], value="y").pack(side="left")

    item_props = ttk.Frame(editor)
    item_props.pack(fill="x", pady=(6, 0))
    ttk.Label(item_props, text="Item preset").pack(side="left", padx=(0, 3))
    item_combo = ttk.Combobox(
        item_props, textvariable=values["feature_item"],
        values=tuple(sorted(LIBRARY)), state="readonly", width=13,
    )
    item_combo.pack(side="left", padx=(0, 9))
    for label, key, width in (
        ("Item name", "item_name", 14),
        ("Segments LxD", "item_segments", 18),
        ("Clearance", "item_clearance", 6),
    ):
        ttk.Label(item_props, text=label).pack(side="left", padx=(0, 3))
        ttk.Entry(item_props, textvariable=values[key], width=width).pack(side="left", padx=(0, 9))
    ttk.Label(item_props, text="Profile").pack(side="left", padx=(0, 3))
    ttk.Combobox(
        item_props, textvariable=values["item_profile"],
        values=("round", "hex", "square"), state="readonly", width=7,
    ).pack(side="left", padx=(0, 9))

    options_row = ttk.Frame(editor)
    options_row.pack(fill="x", pady=(6, 0))
    ttk.Label(options_row, text="Options  (key=value)").pack(side="left", padx=(0, 6))
    ttk.Entry(options_row, textvariable=values["feature_options"], width=48).pack(
        side="left", fill="x", expand=True
    )

    def refresh_support_controls(_event=None) -> None:
        try:
            kind = support_kind(values["feature_kind"].get())
        except ValueError:
            return
        values["support_help"].set(support_help(kind))
        if kind in {"cradle", "nest", "bore"}:
            item_props.pack(fill="x", pady=(6, 0), before=options_row)
        else:
            item_props.pack_forget()

    kind_combo.bind("<<ComboboxSelected>>", refresh_support_controls)
    item_combo.bind("<<ComboboxSelected>>", choose_library_item)
    refresh_support_controls()

    layout_drag = {"mode": None, "index": None, "offset": (0.0, 0.0)}

    def canvas_world(event) -> tuple[float, float]:
        _point, scale, _bounds = layout_canvas._world
        return ((event.x - PREVIEW_SIZE / 2.0) / scale,
                (PREVIEW_SIZE / 2.0 - event.y) / scale)

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
            path = filedialog.asksaveasfilename(
                defaultextension=".wavefinity.json",
                filetypes=(("Wavefinity layout", "*.wavefinity.json"), ("JSON", "*.json")),
            )
            if path:
                Path(path).write_text(
                    json.dumps(design_to_dict(
                        spec, layout, values["label"].get(),
                        values["part"].get(),
                    ), indent=2) + "\n",
                    encoding="utf-8",
                )
        except Exception as error:
            messagebox.showerror("Could not save layout", str(error))

    def open_design_action() -> None:
        try:
            path = filedialog.askopenfilename(
                filetypes=(("Wavefinity layout", "*.wavefinity.json"), ("JSON", "*.json"))
            )
            if not path:
                return
            box, loaded, label, part = design_from_dict(
                json.loads(Path(path).read_text(encoding="utf-8"))
            )
            features[:] = loaded.features
            selected["index"] = None
            values["x_units"].set(f"{box.x / BASE_UNIT:g}")
            values["y_units"].set(f"{box.y / BASE_UNIT:g}")
            values["z"].set(f"{box.z:g}")
            values["wall"].set(f"{box.wall:g}")
            values["flat_inside"].set(f"{box.flat_inside:g}")
            values["label"].set(label)
            values["part"].set(part)
            values["mode"].set(loaded.mode)
            mode_state["value"] = loaded.mode
            refresh_translation()
        except Exception as error:
            messagebox.showerror("Could not open layout", str(error))

    ttk.Button(tools_row, text="Open layout", command=open_design_action).pack(side="right")
    ttk.Button(tools_row, text="Save layout", command=save_design_action).pack(side="right", padx=(0, 6))

    refresh_translation()

    # --- output folder --------------------------------------------------------
    out_row = ttk.Frame(frame)
    out_row.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(14, 0))
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
        root.after(1500, lambda: button.configure(text=original))

    def box_action():
        box, _, output = specs()
        return generate_organizer_files(
            box, current_layout(), output, values["label"].get(), values["part"].get()
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
    buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(14, 0))
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

    frame.columnconfigure(1, weight=1)
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
