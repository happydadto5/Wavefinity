"""Base Trim geometry, splitting, joints, saved design, and export.

A Base Trim is an open-centre perimeter ring around a nominal Wavefinity field.
It deliberately does not use ``BoxSpec``: field X/Y are the child-bin field,
and every physical trim dimension grows outward from that field.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Point, Polygon, box as polygon_box
from shapely.ops import unary_union

from organizer_app import clean_label
from organizer_engine import (
    BASE_UNIT,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    export_mesh,
    mesh_report,
    wavy_rect_outer,
)
from organizer_geometry import (
    _extrude_polygon,
    _loft_cavity,
    difference,
    intersection,
    union,
)


BASE_TRIM_SCHEMA_VERSION = 1

BASE_TRIM_JOIN_TYPES = ("snap", "dovetail", "puzzle")
BASE_TRIM_DEFAULT_JOIN = "snap"
BASE_TRIM_JOIN_LABELS = {
    "snap": "Snap tabs",
    "dovetail": "Sliding dovetail",
    "puzzle": "Puzzle joint",
}

BASE_TRIM_DEFAULT_WIDTH = 6.0
BASE_TRIM_DEFAULT_HEIGHT = 6.0
BASE_TRIM_MIN_WIDTH = 4.0
BASE_TRIM_MAX_WIDTH = 20.0
BASE_TRIM_MIN_HEIGHT = 4.0
BASE_TRIM_MAX_HEIGHT = 20.0
BASE_TRIM_OUTER_TAPER = 1.0

BASE_TRIM_DEFAULT_BED_X = 256.0
BASE_TRIM_DEFAULT_BED_Y = 256.0
BASE_TRIM_BED_EDGE_MARGIN = 10.0
BASE_TRIM_MAX_FIELD = 1200.0

BASE_TRIM_JOINT_LENGTH = 4.0
BASE_TRIM_JOINT_CLEARANCE = 0.20
BASE_TRIM_JOINT_SKIN = 1.0


@dataclass(frozen=True)
class BaseTrimSpec:
    field_x: float
    field_y: float
    height_mm: float = BASE_TRIM_DEFAULT_HEIGHT
    width_mm: float = BASE_TRIM_DEFAULT_WIDTH
    join_type: str = BASE_TRIM_DEFAULT_JOIN
    bed_x_mm: float = BASE_TRIM_DEFAULT_BED_X
    bed_y_mm: float = BASE_TRIM_DEFAULT_BED_Y

    @property
    def units(self) -> tuple[int, int]:
        return round(self.field_x / BASE_UNIT), round(self.field_y / BASE_UNIT)

    @property
    def effective_bed(self) -> tuple[float, float]:
        reserve = 2.0 * BASE_TRIM_BED_EDGE_MARGIN
        return self.bed_x_mm - reserve, self.bed_y_mm - reserve

    @property
    def inner_half_extents(self) -> tuple[float, float]:
        return (
            self.field_x / 2.0 + WAVE_MATING_GAP / 2.0,
            self.field_y / 2.0 + WAVE_MATING_GAP / 2.0,
        )

    @property
    def outer_bottom_size(self) -> tuple[float, float]:
        inner_x, inner_y = self.inner_half_extents
        return 2.0 * (inner_x + self.width_mm), 2.0 * (inner_y + self.width_mm)

    @property
    def outer_top_size(self) -> tuple[float, float]:
        outer_x, outer_y = self.outer_bottom_size
        inset = 2.0 * BASE_TRIM_OUTER_TAPER
        return outer_x - inset, outer_y - inset


@dataclass(frozen=True)
class BaseTrimSeam:
    side: str
    coordinate: float


@dataclass(frozen=True)
class BaseTrimPiece:
    index: int
    kind: str
    label: str
    clip_bounds: tuple[float, float, float, float] | None
    start_seam: BaseTrimSeam | None = None
    end_seam: BaseTrimSeam | None = None


def base_trim_enabled(data: dict) -> bool:
    return isinstance(data, dict) and data.get("design_kind") == "base_trim"


def _number(raw: object, label: str) -> float:
    if isinstance(raw, bool):
        raise ValueError(f"{label} must be a number.")
    try:
        value = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a number.") from error
    if not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number.")
    return value


def base_trim_from_design(data: dict) -> BaseTrimSpec:
    if not isinstance(data, dict):
        raise ValueError("Base Trim design data must be an object.")
    if data.get("design_kind") != "base_trim":
        raise ValueError("This is not a Base Trim design.")
    if data.get("version") != 6:
        raise ValueError("Base Trim designs must use saved-design version 6.")
    raw_box = data.get("box")
    raw_trim = data.get("base_trim")
    if not isinstance(raw_box, dict):
        raise ValueError("Base Trim field dimensions are missing.")
    if not isinstance(raw_trim, dict):
        raise ValueError("Base Trim settings are missing.")
    if raw_trim.get("version") != BASE_TRIM_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported Base Trim version {raw_trim.get('version')!r}; "
            f"expected {BASE_TRIM_SCHEMA_VERSION}."
        )
    raw_layout = data.get("layout")
    if not isinstance(raw_layout, dict) or (
        raw_layout.get("version") != 1
        or raw_layout.get("mode") != "fused"
        or raw_layout.get("features") != []
    ):
        raise ValueError("Base Trim layout must be the empty fused layout.")
    if "auto_size" in raw_trim and not isinstance(raw_trim["auto_size"], bool):
        raise ValueError("Base Trim auto_size must be true or false.")
    if "part_name" in data and not isinstance(data["part_name"], str):
        raise ValueError("Base Trim name must be text.")
    spec = BaseTrimSpec(
        field_x=_number(raw_box.get("x"), "Field width"),
        field_y=_number(raw_box.get("y"), "Field length"),
        height_mm=_number(raw_box.get("z"), "Trim height"),
        width_mm=_number(raw_trim.get("width_mm"), "Trim width"),
        join_type=str(raw_trim.get("join_type", "")),
        bed_x_mm=_number(raw_trim.get("bed_x_mm"), "Bed X"),
        bed_y_mm=_number(raw_trim.get("bed_y_mm"), "Bed Y"),
    )
    validate_base_trim(spec)
    return spec


def base_trim_design_to_dict(spec: BaseTrimSpec, part_name: str = "") -> dict:
    validate_base_trim(spec)
    return {
        "version": 6,
        "design_kind": "base_trim",
        "box": {"x": spec.field_x, "y": spec.field_y, "z": spec.height_mm},
        "base_trim": {
            "version": BASE_TRIM_SCHEMA_VERSION,
            "width_mm": spec.width_mm,
            "join_type": spec.join_type,
            "bed_x_mm": spec.bed_x_mm,
            "bed_y_mm": spec.bed_y_mm,
            "auto_size": False,
        },
        "part_name": str(part_name or ""),
        "layout": {"version": 1, "mode": "fused", "snap": 1, "features": []},
    }


def _fits(size: tuple[float, float], bed: tuple[float, float]) -> bool:
    x, y = size
    bed_x, bed_y = bed
    return (
        (x <= bed_x + 1e-6 and y <= bed_y + 1e-6)
        or (x <= bed_y + 1e-6 and y <= bed_x + 1e-6)
    )


def _one_piece(spec: BaseTrimSpec) -> bool:
    return _fits(spec.outer_bottom_size, spec.effective_bed)


def _validate_values(spec: BaseTrimSpec) -> None:
    for value, label in (
        (spec.field_x, "Field width"),
        (spec.field_y, "Field length"),
        (spec.width_mm, "Trim width"),
        (spec.height_mm, "Trim height"),
        (spec.bed_x_mm, "Bed X"),
        (spec.bed_y_mm, "Bed Y"),
    ):
        if not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number.")
    for value, label in ((spec.field_x, "Field width"), (spec.field_y, "Field length")):
        if value < BASE_UNIT - 1e-9:
            raise ValueError(f"{label} must be at least one Wavefinity unit ({BASE_UNIT:g} mm).")
        if value > BASE_TRIM_MAX_FIELD + 1e-9:
            raise ValueError(f"{label} cannot exceed {BASE_TRIM_MAX_FIELD:g} mm.")
        units = value / BASE_UNIT
        if not math.isclose(units, round(units), abs_tol=1e-9):
            raise ValueError(
                f"{label} must be a whole {BASE_UNIT:g} mm Wavefinity unit; "
                f"{value:g} mm is not."
            )
    if not BASE_TRIM_MIN_WIDTH <= spec.width_mm <= BASE_TRIM_MAX_WIDTH:
        raise ValueError(
            f"Trim width must be {BASE_TRIM_MIN_WIDTH:g}-{BASE_TRIM_MAX_WIDTH:g} mm."
        )
    if not BASE_TRIM_MIN_HEIGHT <= spec.height_mm <= BASE_TRIM_MAX_HEIGHT:
        raise ValueError(
            f"Trim height must be {BASE_TRIM_MIN_HEIGHT:g}-{BASE_TRIM_MAX_HEIGHT:g} mm."
        )
    for value, label in ((spec.width_mm, "Trim width"), (spec.height_mm, "Trim height")):
        if not math.isclose(value * 2.0, round(value * 2.0), abs_tol=1e-9):
            raise ValueError(f"{label} must change in 0.5 mm steps.")
    if spec.join_type not in BASE_TRIM_JOIN_TYPES:
        raise ValueError("Section joint must be Snap tabs, Sliding dovetail, or Puzzle joint.")
    if spec.bed_x_mm <= 2.0 * BASE_TRIM_BED_EDGE_MARGIN:
        raise ValueError("Bed X must leave a positive printable area after the 10 mm edge clearance.")
    if spec.bed_y_mm <= 2.0 * BASE_TRIM_BED_EDGE_MARGIN:
        raise ValueError("Bed Y must leave a positive printable area after the 10 mm edge clearance.")


def _validate_split_joint(spec: BaseTrimSpec) -> None:
    if _one_piece(spec):
        return
    if _joint_max_profile_width(spec) < 1.6 - 1e-9:
        joint = BASE_TRIM_JOIN_LABELS[spec.join_type]
        raise ValueError(
            f"The {spec.width_mm:g} mm-wide Base Trim is too narrow for {joint} when "
            "the trim is split. Increase Trim width, choose another joint, or use a "
            "larger printer bed."
        )


def validate_base_trim(spec: BaseTrimSpec) -> None:
    _validate_values(spec)
    _validate_split_joint(spec)


def base_trim_inner_polygon(spec: BaseTrimSpec) -> Polygon:
    _validate_values(spec)
    half_x, half_y = spec.inner_half_extents
    return wavy_rect_outer(half_x, half_y)


def _outer_loft(spec: BaseTrimSpec) -> trimesh.Trimesh:
    bottom_x, bottom_y = spec.outer_bottom_size
    top_x, top_y = spec.outer_top_size
    rings = [
        np.asarray([
            [-bottom_x / 2.0, -bottom_y / 2.0],
            [bottom_x / 2.0, -bottom_y / 2.0],
            [bottom_x / 2.0, bottom_y / 2.0],
            [-bottom_x / 2.0, bottom_y / 2.0],
        ], dtype=float),
        np.asarray([
            [-top_x / 2.0, -top_y / 2.0],
            [top_x / 2.0, -top_y / 2.0],
            [top_x / 2.0, top_y / 2.0],
            [-top_x / 2.0, top_y / 2.0],
        ], dtype=float),
    ]
    return _loft_cavity(rings, [0.0, spec.height_mm])


def make_base_trim_ring(spec: BaseTrimSpec) -> trimesh.Trimesh:
    validate_base_trim(spec)
    inner = _extrude_polygon(base_trim_inner_polygon(spec), spec.height_mm + 0.2)
    inner.apply_translation((0.0, 0.0, -0.1))
    ring = difference([_outer_loft(spec), inner])
    ring.metadata["wavefinity_preview_kind"] = "base_trim"
    return ring


def _perimeter_point(
    distance: float, outer_x: float, outer_y: float,
) -> tuple[float, float, BaseTrimSeam, tuple[float, float]]:
    """Return a point, seam, and clockwise tangent on the outer perimeter."""
    perimeter = 2.0 * (outer_x + outer_y)
    distance %= perimeter
    half_x, half_y = outer_x / 2.0, outer_y / 2.0
    if distance < outer_x:
        return -half_x + distance, -half_y, BaseTrimSeam("front", -half_x + distance), (1.0, 0.0)
    distance -= outer_x
    if distance < outer_y:
        return half_x, -half_y + distance, BaseTrimSeam("right", -half_y + distance), (0.0, 1.0)
    distance -= outer_y
    if distance < outer_x:
        return half_x - distance, half_y, BaseTrimSeam("back", half_x - distance), (-1.0, 0.0)
    distance -= outer_x
    return -half_x, half_y - distance, BaseTrimSeam("left", half_y - distance), (0.0, -1.0)


def _perimeter_piece(
    start: float, end: float, outer_x: float, outer_y: float,
) -> tuple[tuple[float, float, float, float], BaseTrimSeam, BaseTrimSeam, tuple[float, float]]:
    """Make one contiguous perimeter arc's clipping box and seam details."""
    perimeter = 2.0 * (outer_x + outer_y)
    start_point = _perimeter_point(start, outer_x, outer_y)
    end_point = _perimeter_point(end, outer_x, outer_y)
    points = [start_point[:2], end_point[:2]]
    for corner in (0.0, outer_x, outer_x + outer_y, 2.0 * outer_x + outer_y):
        shifted = corner
        while shifted <= start + 1e-9:
            shifted += perimeter
        if shifted < end - 1e-9:
            points.append(_perimeter_point(shifted, outer_x, outer_y)[:2])
    xs, ys = zip(*points)
    margin = 1.0
    bounds = (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)
    return bounds, start_point[2], end_point[2], end_point[3]


def _planned_piece_fits(
    bounds: tuple[float, float, float, float], tangent: tuple[float, float],
    bed: tuple[float, float],
) -> bool:
    """Reserve the male key's outward projection before making the mesh."""
    min_x, min_y, max_x, max_y = bounds
    # The one-millimetre clipping margin is not part of the printed ring.
    width = max_x - min_x - 2.0
    depth = max_y - min_y - 2.0
    if tangent[0]:
        width += BASE_TRIM_JOINT_LENGTH
    else:
        depth += BASE_TRIM_JOINT_LENGTH
    return _fits((width, depth), bed)


def _partition_score(
    cuts: list[float], outer_x: float, outer_y: float,
) -> tuple[float, ...]:
    """Prefer cuts on straight runs and as far as possible from corners."""
    perimeter = 2.0 * (outer_x + outer_y)
    corners = (0.0, outer_x, outer_x + outer_y, 2.0 * outer_x + outer_y)
    clearances = [
        min(min(abs(cut - corner), perimeter - abs(cut - corner)) for corner in corners)
        for cut in cuts
    ]
    spans = [cuts[index + 1] - cuts[index] for index in range(len(cuts) - 1)]
    return (min(clearances), min(spans), -max(spans))


def plan_base_trim_pieces(spec: BaseTrimSpec) -> list[BaseTrimPiece]:
    _validate_values(spec)
    _validate_split_joint(spec)
    if _one_piece(spec):
        return [BaseTrimPiece(1, "whole", "Complete Base Trim", None)]

    outer_x, outer_y = spec.outer_bottom_size
    perimeter = 2.0 * (outer_x + outer_y)
    # A piece must leave room for one 4 mm male key. This is a lower bound,
    # not an edge-by-edge slicing rule; candidates below use their real XY box.
    smallest_bed_side = min(spec.effective_bed)
    if smallest_bed_side <= BASE_TRIM_JOINT_LENGTH + 1e-6:
        raise ValueError("The declared printable area is too small for a Base Trim joint.")

    max_count = max(2, math.ceil(perimeter / (smallest_bed_side - BASE_TRIM_JOINT_LENGTH)) + 4)
    for count in range(2, max_count + 1):
        best: tuple[tuple[float, ...], list[BaseTrimPiece]] | None = None
        # Equal-length perimeter arcs avoid tiny remainders. Shift their common
        # origin through one arc so the deterministic search can move cuts away
        # from corners without independently chopping each edge.
        for phase_index in range(32):
            phase = perimeter * phase_index / (32.0 * count)
            cuts = [phase + perimeter * index / count for index in range(count + 1)]
            planned: list[BaseTrimPiece] = []
            for index, (start, end) in enumerate(zip(cuts, cuts[1:]), 1):
                bounds, start_seam, end_seam, tangent = _perimeter_piece(start, end, outer_x, outer_y)
                if not _planned_piece_fits(bounds, tangent, spec.effective_bed):
                    break
                planned.append(BaseTrimPiece(
                    index, "perimeter", f"Perimeter section {index}", bounds,
                    start_seam, end_seam,
                ))
            if len(planned) != count:
                continue
            score = _partition_score(cuts[:-1], outer_x, outer_y)
            if best is None or score > best[0]:
                best = score, planned
        if best is not None:
            return best[1]
    raise ValueError(
        "The Base Trim cannot be divided into printable perimeter sections for the declared bed. "
        "Increase the printer bed size."
    )


def _seam_frame(
    spec: BaseTrimSpec, seam: BaseTrimSeam,
) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    inner_x, inner_y = spec.inner_half_extents
    top_width = spec.width_mm - BASE_TRIM_OUTER_TAPER
    # The inner face swings a full +/- wave across every 4 mm seam. Centre the
    # joint in the guaranteed material between the fixed outside face and the
    # most outward inner crest, rather than in the nominal straight band.
    wave_offset = WAVE_AMPLITUDE / 2.0
    if seam.side == "front":
        return (seam.coordinate, -inner_y - top_width / 2.0 - wave_offset), (1.0, 0.0), (0.0, 1.0)
    if seam.side == "right":
        return (inner_x + top_width / 2.0 + wave_offset, seam.coordinate), (0.0, 1.0), (-1.0, 0.0)
    if seam.side == "back":
        return (seam.coordinate, inner_y + top_width / 2.0 + wave_offset), (-1.0, 0.0), (0.0, -1.0)
    return (-inner_x - top_width / 2.0 - wave_offset, seam.coordinate), (0.0, -1.0), (1.0, 0.0)


def _joint_max_profile_width(spec: BaseTrimSpec) -> float:
    """Width left after the wave, female clearance, and both structural skins."""
    safe_width = spec.width_mm - BASE_TRIM_OUTER_TAPER - WAVE_AMPLITUDE
    return safe_width - 2.0 * BASE_TRIM_JOINT_SKIN - 2.0 * BASE_TRIM_JOINT_CLEARANCE


def _joint_profile(spec: BaseTrimSpec) -> Polygon:
    length = BASE_TRIM_JOINT_LENGTH
    max_width = _joint_max_profile_width(spec)
    if spec.join_type == "snap":
        detent = 0.30
        width = min(3.0, spec.width_mm - 2.0, max_width - 2.0 * detent)
        base = polygon_box(0.0, -width / 2.0, length, width / 2.0)
        lead = 0.60
        bumps = [
            Polygon([(length - lead, sign * width / 2.0),
                     (length, sign * (width / 2.0 + detent)),
                     (length, sign * width / 2.0)])
            for sign in (-1.0, 1.0)
        ]
        return unary_union([base, *bumps])
    if spec.join_type == "dovetail":
        scale = min(1.0, max_width / 3.4)
        neck, head = 2.4 * scale, 3.4 * scale
        return Polygon([
            (0.0, -neck / 2.0), (length, -head / 2.0),
            (length, head / 2.0), (0.0, neck / 2.0),
        ])
    scale = min(1.0, max_width / 3.4)
    neck, head = 2.4 * scale, 3.4 * scale
    neck_shape = polygon_box(0.0, -neck / 2.0, length - head / 2.0, neck / 2.0)
    head_shape = Point(length - head / 2.0, 0.0).buffer(head / 2.0, quad_segs=16)
    return unary_union([neck_shape, head_shape])


def _joint_solid(spec: BaseTrimSpec, seam: BaseTrimSeam, female: bool) -> trimesh.Trimesh:
    profile = _joint_profile(spec)
    if female:
        profile = profile.buffer(BASE_TRIM_JOINT_CLEARANCE, join_style=2)
    else:
        # Let every male key overlap its parent section by a small root. A
        # face-only contact at the cut plane is not a dependable printable
        # union, while this does not increase the advertised 4 mm projection.
        min_x, min_y, _, max_y = profile.bounds
        profile = unary_union([
            profile,
            polygon_box(min_x - 0.25, min_y, min_x + 0.05, max_y),
        ])
    origin, tangent, lateral = _seam_frame(spec, seam)
    world = affinity.affine_transform(
        profile,
        [tangent[0], lateral[0], tangent[1], lateral[1], origin[0], origin[1]],
    )
    if spec.join_type == "snap":
        height = min(3.0, spec.height_mm - 2.0)
        z0 = (spec.height_mm - height) / 2.0
    elif spec.join_type == "dovetail":
        height = spec.height_mm - 2.0
        z0 = 1.0
    else:
        height = spec.height_mm
        z0 = 0.0
    if female:
        z0 -= BASE_TRIM_JOINT_CLEARANCE
        height += 2.0 * BASE_TRIM_JOINT_CLEARANCE
    solid = _extrude_polygon(world, height)
    solid.apply_translation((0.0, 0.0, z0))
    return solid


def _piece_clip(spec: BaseTrimSpec, piece: BaseTrimPiece) -> trimesh.Trimesh:
    if piece.clip_bounds is None:
        raise ValueError("A split Base Trim piece is missing its clipping bounds.")
    clip = _extrude_polygon(polygon_box(*piece.clip_bounds), spec.height_mm + 2.0)
    clip.apply_translation((0.0, 0.0, -1.0))
    return clip


def make_base_trim_pieces(spec: BaseTrimSpec) -> list[tuple[BaseTrimPiece, trimesh.Trimesh]]:
    validate_base_trim(spec)
    plans = plan_base_trim_pieces(spec)
    ring = make_base_trim_ring(spec)
    if len(plans) == 1:
        return [(plans[0], ring)]
    result: list[tuple[BaseTrimPiece, trimesh.Trimesh]] = []
    for piece in plans:
        body = intersection([ring, _piece_clip(spec, piece)])
        if piece.end_seam is not None:
            body = union([body, _joint_solid(spec, piece.end_seam, False)])
        if piece.start_seam is not None:
            body = difference([body, _joint_solid(spec, piece.start_seam, True)])
        body.metadata["wavefinity_preview_kind"] = "base_trim"
        size = tuple(float(v) for v in (body.bounds[1] - body.bounds[0])[:2])
        if not _fits(size, spec.effective_bed):
            raise ValueError(
                f"Base Trim part {piece.index} cannot fit the declared printable area. "
                "Increase the printer bed size."
            )
        result.append((piece, body))
    return result


def base_trim_summary(spec: BaseTrimSpec) -> dict:
    validate_base_trim(spec)
    pieces = plan_base_trim_pieces(spec)
    outer = spec.outer_bottom_size
    outer_top = spec.outer_top_size
    inner_x, inner_y = spec.inner_half_extents
    seams = [] if len(pieces) == 1 else [
        {"side": one.end_seam.side, "coordinate": round(one.end_seam.coordinate, 3)}
        for one in pieces if one.end_seam is not None
    ]
    return {
        "field_mm": [spec.field_x, spec.field_y],
        "field_units": list(spec.units),
        "width_mm": spec.width_mm,
        "height_mm": spec.height_mm,
        "inner_half_mm": [inner_x, inner_y],
        "outer_mm": list(outer),
        "outer_top_mm": list(outer_top),
        "bed_mm": [spec.bed_x_mm, spec.bed_y_mm],
        "effective_bed_mm": list(spec.effective_bed),
        "edge_margin_mm": BASE_TRIM_BED_EDGE_MARGIN,
        "join_type": spec.join_type,
        "join_label": BASE_TRIM_JOIN_LABELS[spec.join_type],
        "piece_count": len(pieces),
        "one_piece": len(pieces) == 1,
        "seams": seams,
        "pieces": [
            {
                "number": one.index,
                "label": one.label,
                "kind": one.kind,
                "clip_bounds": list(one.clip_bounds) if one.clip_bounds else None,
            }
            for one in pieces
        ],
    }


def _dimension_text(value: float) -> str:
    return f"{value:g}"


def _base_filename(spec: BaseTrimSpec, part_name: str = "") -> str:
    units_x, units_y = spec.units
    name = (
        f"Base Trim {_dimension_text(spec.field_x)} x {_dimension_text(spec.field_y)} "
        f"({units_x}U x {units_y}U)"
    )
    tidy = clean_label(part_name)
    if tidy:
        name += f" {tidy}"
    return name


def generate_base_trim_files(
    spec: BaseTrimSpec,
    output_dir: Path,
    part_name: str = "",
    auto_timestamp: bool = False,
) -> dict:
    validate_base_trim(spec)
    made = make_base_trim_pieces(spec)
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _base_filename(spec, part_name)
    total = len(made)
    targets = [
        output_dir / (
            f"{stem}.3mf" if total == 1
            else f"{stem} Part {index:02d} of {total:02d}.3mf"
        )
        for index in range(1, total + 1)
    ]
    if auto_timestamp and (not clean_label(part_name) or any(path.exists() for path in targets)):
        timestamp = datetime.now().strftime("%m%d%y%H%M%S")
        targets = [path.with_name(f"{path.stem} {timestamp}{path.suffix}") for path in targets]
    parts = []
    for (plan, mesh), target in zip(made, targets):
        exported = mesh.copy()
        centre = (exported.bounds[0] + exported.bounds[1]) / 2.0
        exported.apply_translation((-centre[0], -centre[1], -exported.bounds[0][2]))
        export_mesh(exported, target, f"base_trim_part_{plan.index:02d}")
        parts.append({
            "number": plan.index,
            "name": plan.label,
            "output": str(target),
            "mesh": mesh_report(f"base_trim_part_{plan.index:02d}", exported),
        })
    return {
        "mode": "base_trim",
        "base_trim": base_trim_summary(spec),
        "output": str(targets[0]) if total == 1 else None,
        "parts": parts,
    }
