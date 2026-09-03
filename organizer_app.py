"""Command-line and desktop application for the wavy organizer generator."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

from organizer_engine import (
    BASE_UNIT,
    BoxSpec,
    ConnectorSpec,
    GRID_PITCH,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    LOCKED_TOLERANCE,
    MIN_BOX_SIZE,
    MIN_JOINABLE_SIZE,
    WAVE_LENGTH,
    export_labelled_box,
    export_mesh,
    generate_sampler,
    label_report,
    make_labelled_box,
    placed_label_outline,
    preview_rings,
    wavy_cavity_polygon,
    wavy_outer_polygon,
    make_box,
    make_side_connector,
    measure_lock,
    mesh_report,
    validate_side_fit,
)


APP_DIR = Path(__file__).resolve().parent
DEFAULT_SAMPLE_BOXES = "2x6,4x6,6x6"   # 16x48, 32x48, 48x48 mm


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
        help="raised text on the floor, as a second object for a second colour",
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

PREVIEW_SIZE = 330
PREVIEW_PAD = 34

# Seen from 45 degrees round and PREVIEW_ELEVATION up.  A shallow angle looks
# more dramatic but a deep bin then hides its own floor completely, and the
# floor is where the label is, so the view is steep enough to see in while
# still showing two outer faces and the wall thickness.
PREVIEW_ELEVATION = 76.0
_YAW = 0.7071067811865476                                  # cos 45
_LIFT = _YAW * math.sin(math.radians(PREVIEW_ELEVATION))
_DROP = math.cos(math.radians(PREVIEW_ELEVATION))
# unit vector from the scene toward the camera
_TO_CAMERA = (-_YAW * _DROP, -_YAW * _DROP, math.sin(math.radians(PREVIEW_ELEVATION)))


def iso_point(point: tuple[float, float, float]) -> tuple[float, float]:
    """One 3D point in screen coordinates, before scaling.

    Screen Y grows downward, so both world axes and Z are negated: +X, +Y and
    +Z all travel up the canvas, which is what keeps floor text the right way
    up instead of mirrored or upside down.
    """
    x, y, z = point
    return (x - y) * _YAW, -(x + y) * _LIFT - z * _DROP


def _towards_camera(normal: tuple[float, float, float]) -> float:
    return sum(n * c for n, c in zip(normal, _TO_CAMERA))


def preview_scene(box: BoxSpec, label: str = "") -> dict[str, object]:
    """The box as 3D faces ordered far to near, plus its dimension text.

    Built outside the widget code so the layout can be checked without opening
    a window.  Faces pointing away from the camera are dropped first - painting
    order alone cannot hide the far outside wall, because from above its top
    edge is genuinely nearer the camera than the floor is.
    """
    outer, cavity = preview_rings(box)
    floor_z, rim_z = box.wall, box.z
    faces: list[tuple[float, list[tuple[float, float, float]], str]] = []

    def depth(points) -> float:
        return sum(_towards_camera(point) for point in points) / len(points)

    def add(points, kind, normal, key=None) -> None:
        if _towards_camera(normal) <= 0.0:
            return
        faces.append((depth(points) if key is None else key, points, kind))

    count = len(outer)
    for index in range(count):
        a, b = outer[index], outer[(index + 1) % count]
        c, d = cavity[index], cavity[(index + 1) % count]
        # the rings run anticlockwise, so (dy, -dx) points out of the box
        run = (b[0] - a[0], b[1] - a[1])
        outward = (run[1], -run[0], 0.0)
        inward = (-run[1], run[0], 0.0)
        add([(*a, 0.0), (*b, 0.0), (*b, rim_z), (*a, rim_z)], "outside", outward)
        add(
            [(*c, floor_z), (*d, floor_z), (*d, rim_z), (*c, rim_z)],
            "inside", inward,
        )
        add(
            [(*a, rim_z), (*b, rim_z), (*d, rim_z), (*c, rim_z)],
            "rim", (0.0, 0.0, 1.0),
        )

    floor = [(*point, floor_z) for point in cavity]
    floor_depth = depth(floor)
    add(floor, "floor", (0.0, 0.0, 1.0))

    fits, message = True, ""
    tidy = clean_label(label)
    if tidy:
        try:
            outline = placed_label_outline(box, tidy)
        except ValueError as error:
            fits, message, outline = False, str(error), None
        if outline is not None:
            pieces = (
                list(outline.geoms)
                if outline.geom_type == "MultiPolygon"
                else [outline]
            )
            # The label lies on the floor, so it is pinned just in front of the
            # floor's own depth rather than taking each glyph's position: a
            # letter on the far side would otherwise sort behind the floor and
            # be painted over by it.
            for piece in pieces:
                add(
                    [(x, y, floor_z) for x, y in piece.exterior.coords],
                    "label", (0.0, 0.0, 1.0), floor_depth + 0.001,
                )
                for ring in piece.interiors:
                    add(
                        [(x, y, floor_z) for x, y in ring.coords],
                        "label_hole", (0.0, 0.0, 1.0), floor_depth + 0.002,
                    )

    faces.sort(key=lambda item: item[0])
    inside_x, inside_y = box.usable_inside
    return {
        "faces": [(points, kind) for _, points, kind in faces],
        "fits": fits,
        "message": message,
        "x_text": f"{box.x:g}mm ({math.floor(inside_x):g} inside)",
        "y_text": f"{box.y:g}mm ({math.floor(inside_y):g} inside)",
        "z_text": f"{box.z:g}mm tall",
    }


def preview_transform(box: BoxSpec, size: int = PREVIEW_SIZE, pad: int = PREVIEW_PAD):
    """Millimetres to canvas pixels: isometric, centred, scaled to fit."""
    corners = [
        iso_point((sx * box.x / 2.0, sy * box.y / 2.0, z))
        for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, box.z)
    ]
    us = [u for u, _ in corners]
    vs = [v for _, v in corners]
    span = max(max(us) - min(us), max(vs) - min(vs)) or 1.0
    scale = (size - 2 * pad) / span
    mid_u = (max(us) + min(us)) / 2.0
    mid_v = (max(vs) + min(vs)) / 2.0

    def to_canvas(point: tuple[float, float, float]) -> tuple[float, float]:
        u, v = iso_point(point)
        return size / 2.0 + (u - mid_u) * scale, size / 2.0 + (v - mid_v) * scale

    return to_canvas


def generate_box_file(
    box: BoxSpec, output: Path, label: str = ""
) -> dict[str, object]:
    """Write the box, plus a raised floor label as a second object if asked.

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
    root.minsize(920, 560)

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
        "output": tk.StringVar(value=str(APP_DIR / "generated")),
    }
    show_advanced = tk.BooleanVar(value=False)

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

    preview = tk.Canvas(
        frame, width=PREVIEW_SIZE, height=PREVIEW_SIZE,
        background="white", highlightthickness=1, highlightbackground="#cccccc",
    )
    preview.grid(row=2, column=2, rowspan=3, sticky="ne", padx=(24, 0))

    FACE_COLOURS = {
        "outside": "#8fb8cc",
        "rim": "#bcd6e1",
        "inside": "#6b93a8",
        "floor": "#e8f0f4",
        "label": "#d9544d",
        "label_hole": "#e8f0f4",
    }

    def refresh_preview(spec: BoxSpec | None) -> None:
        preview.delete("all")
        if spec is None:
            preview.create_text(
                PREVIEW_SIZE / 2, PREVIEW_SIZE / 2,
                text="-", fill="#999999", font=("Segoe UI", 11),
            )
            return

        scene = preview_scene(spec, values["label"].get())
        to_canvas = preview_transform(spec)
        for points, kind in scene["faces"]:
            colour = FACE_COLOURS[kind]
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
                PREVIEW_SIZE / 2, 16, text="label will not fit",
                fill="#c0392b", font=("Segoe UI", 10, "bold"),
            )

    def refresh_translation(*_args) -> None:
        try:
            spec = BoxSpec(
                x=float(values["x_units"].get()) * BASE_UNIT,
                y=float(values["y_units"].get()) * BASE_UNIT,
                z=float(values["z"].get()),
                wall=float(values["wall"].get()),
                flat_inside=float(values["flat_inside"].get()),
            )
        except Exception:
            refresh_preview(None)
            return
        refresh_preview(spec)

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
    refresh_translation()

    # --- output folder --------------------------------------------------------
    out_row = ttk.Frame(frame)
    out_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(18, 0))
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
        box = BoxSpec(
            x=float(values["x_units"].get()) * BASE_UNIT,
            y=float(values["y_units"].get()) * BASE_UNIT,
            z=float(values["z"].get()),
            wall=float(values["wall"].get()),
            flat_inside=float(values["flat_inside"].get()),
        )
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
        label = values["label"].get()
        name = box_filename(box, label, part=values["part"].get())
        return generate_box_file(box, output / name, label)

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
    buttons.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(20, 0))
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
