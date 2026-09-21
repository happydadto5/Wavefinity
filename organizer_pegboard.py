"""Pegboard standards, mount layout, and printable mounting geometry.

The bin-side receiver is deliberately standard-neutral.  Only the board-side
adapter and board-grid rules vary by standard.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import numpy as np
import trimesh

from organizer_geometry import union


@dataclass(frozen=True)
class PegboardStandard:
    id: str
    name: str
    pitch_x_mm: float
    pitch_y_mm: float
    opening_width_mm: float
    opening_height_mm: float
    opening_shape: str
    stagger_x_mm: float
    adapter_strategy: str


PEGBOARD_STANDARDS: dict[str, PegboardStandard] = {
    "standard": PegboardStandard(
        "standard", "Standard Pegboard", 25.4, 25.4, 6.35, 6.35,
        "round", 0.0, "straight_and_hooked_pegs",
    ),
    "skadis": PegboardStandard(
        "skadis", "IKEA SKÅDIS", 40.0, 20.0, 5.0, 15.0,
        "rounded_slot", 20.0, "skadis_slots",
    ),
}

PEGBOARD_SIZE_MODES = ("physical", "holes")
PEGBOARD_MAX_CLEATS_X = 5
PEGBOARD_MAX_CLEATS_Y = 3
PEGBOARD_DEFAULT_DEPTH_MM = 350.0
PEGBOARD_RECEIVER_WIDTH = 14.0
PEGBOARD_RECEIVER_HEIGHT = 14.0
PEGBOARD_PROJECTION = 5.5
PEGBOARD_RIB_WIDTH = 2.0
PEGBOARD_MAX_UNSUPPORTED_GAP = 40.0
PEGBOARD_EDGE_INSET = 2.0
PEGBOARD_AUTO_SUPPORT_X = 72.0
PEGBOARD_AUTO_SUPPORT_Y = 64.0


@dataclass(frozen=True)
class PegboardMountSpec:
    enabled: bool = False
    standard: str = "standard"
    cleat_x: str | int = "auto"
    cleat_y: str | int = "auto"


def pegboard_catalog() -> dict[str, Any]:
    return {
        "standards": [
            {
                "id": one.id,
                "name": one.name,
                "pitch_x_mm": one.pitch_x_mm,
                "pitch_y_mm": one.pitch_y_mm,
                "opening_width_mm": one.opening_width_mm,
                "opening_height_mm": one.opening_height_mm,
                "opening_shape": one.opening_shape,
                "stagger_x_mm": one.stagger_x_mm,
                "adapter_strategy": one.adapter_strategy,
            }
            for one in PEGBOARD_STANDARDS.values()
        ],
        "size_modes": list(PEGBOARD_SIZE_MODES),
        "cleat_x": {"min": 1, "max": PEGBOARD_MAX_CLEATS_X},
        "cleat_y": {"min": 1, "max": PEGBOARD_MAX_CLEATS_Y},
        "receiver": {
            "width_mm": PEGBOARD_RECEIVER_WIDTH,
            "height_mm": PEGBOARD_RECEIVER_HEIGHT,
            "projection_mm": PEGBOARD_PROJECTION,
            "edge_inset_mm": PEGBOARD_EDGE_INSET,
            "max_unsupported_gap_mm": PEGBOARD_MAX_UNSUPPORTED_GAP,
        },
    }


def pegboard_standard(value: Any) -> PegboardStandard:
    key = str(value or "standard").strip().lower()
    try:
        return PEGBOARD_STANDARDS[key]
    except KeyError:
        raise ValueError("pegboard standard must be standard or skadis") from None


def _positive(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"pegboard {name} must be a number") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"pegboard {name} must be positive")
    return number


def _whole(value: Any, name: str) -> int:
    number = _positive(value, name)
    if not math.isclose(number, round(number), abs_tol=1e-9):
        raise ValueError(f"pegboard {name} must be a whole number")
    return int(round(number))


def resolve_pegboard_size(
    standard_id: Any,
    size_mode: Any,
    *,
    width_mm: Any = None,
    height_mm: Any = None,
    holes_x: Any = None,
    holes_y: Any = None,
) -> dict[str, Any]:
    standard = pegboard_standard(standard_id)
    mode = str(size_mode or "physical").strip().lower()
    if mode not in PEGBOARD_SIZE_MODES:
        raise ValueError("pegboard size mode must be physical or holes")
    if mode == "holes":
        count_x = _whole(holes_x, "holes across")
        count_y = _whole(holes_y, "holes high")
        width = count_x * standard.pitch_x_mm
        height = count_y * standard.pitch_y_mm
        residual_x = residual_y = 0.0
    else:
        width = _positive(width_mm, "width")
        height = _positive(height_mm, "height")
        count_x = int(math.floor(width / standard.pitch_x_mm + 1e-9))
        count_y = int(math.floor(height / standard.pitch_y_mm + 1e-9))
        if count_x < 1 or count_y < 1:
            raise ValueError(
                f"{standard.name} needs at least {standard.pitch_x_mm:g} mm width "
                f"and {standard.pitch_y_mm:g} mm height"
            )
        residual_x = width - count_x * standard.pitch_x_mm
        residual_y = height - count_y * standard.pitch_y_mm
    if count_x > 500 or count_y > 500:
        raise ValueError("pegboard hole counts cannot exceed 500 per axis")
    return {
        "standard": standard.id,
        "standard_name": standard.name,
        "size_mode": mode,
        "width_mm": round(width, 6),
        "height_mm": round(height, 6),
        "holes_x": count_x,
        "holes_y": count_y,
        "usable_width_mm": round(count_x * standard.pitch_x_mm, 6),
        "usable_height_mm": round(count_y * standard.pitch_y_mm, 6),
        "residual_x_mm": round(residual_x, 6),
        "residual_y_mm": round(residual_y, 6),
        "border_x_mm": round(residual_x / 2.0, 6),
        "border_y_mm": round(residual_y / 2.0, 6),
    }


def normalise_pegboard_space(raw: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_pegboard_size(
        raw.get("pegboard_standard", raw.get("standard", "standard")),
        raw.get("pegboard_size_mode", raw.get("size_mode", "physical")),
        width_mm=raw.get("x", raw.get("width_mm")),
        height_mm=raw.get("y", raw.get("height_mm")),
        holes_x=raw.get("pegboard_holes_x", raw.get("holes_x")),
        holes_y=raw.get("pegboard_holes_y", raw.get("holes_y")),
    )
    return {
        "x": resolved["width_mm"],
        "y": resolved["height_mm"],
        "z": PEGBOARD_DEFAULT_DEPTH_MM,
        "pegboard_standard": resolved["standard"],
        "pegboard_size_mode": resolved["size_mode"],
        "pegboard_holes_x": resolved["holes_x"],
        "pegboard_holes_y": resolved["holes_y"],
        "pegboard_usable_x": resolved["usable_width_mm"],
        "pegboard_usable_y": resolved["usable_height_mm"],
        "pegboard_residual_x": resolved["residual_x_mm"],
        "pegboard_residual_y": resolved["residual_y_mm"],
    }


def _count(value: Any, maximum: int, axis: str) -> str | int:
    if str(value or "auto").strip().lower() == "auto":
        return "auto"
    try:
        count = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Cleat Count {axis} must be Auto or 1–{maximum}") from None
    if count < 1 or count > maximum:
        raise ValueError(f"Cleat Count {axis} must be Auto or 1–{maximum}")
    return count


def normalise_mount_spec(raw: Any) -> PegboardMountSpec:
    if isinstance(raw, PegboardMountSpec):
        return raw
    if not isinstance(raw, dict) or not bool(raw.get("enabled", False)):
        return PegboardMountSpec()
    return PegboardMountSpec(
        enabled=True,
        standard=pegboard_standard(raw.get("standard")).id,
        cleat_x=_count(raw.get("cleat_x", "auto"), PEGBOARD_MAX_CLEATS_X, "X"),
        cleat_y=_count(raw.get("cleat_y", "auto"), PEGBOARD_MAX_CLEATS_Y, "Y"),
    )


def _auto_count(length: float, support: float, maximum: int) -> int:
    return min(maximum, max(1, int(math.ceil(length / support - 1e-9))))


def _axis_positions(
    length: float, pitch: float, count: int, receiver: float, axis: str,
    offset: float = 0.0, end_margin: float | None = None,
) -> list[float]:
    margin = PEGBOARD_EDGE_INSET + receiver / 2.0
    limit = length - (margin if end_margin is None else end_margin)
    candidates = [
        (index + 0.5) * pitch + offset
        for index in range(-1, int(math.ceil(length / pitch)) + 1)
        if margin - 1e-9 <= (index + 0.5) * pitch + offset <= limit + 1e-9
    ]
    if len(candidates) < count:
        raise ValueError(
            f"Cleat Count {axis} = {count} does not fit this {length:g} mm bin on the selected board grid"
        )
    if count == 1:
        return [min(candidates, key=lambda value: abs(value - length / 2.0))]
    indexes = [round(i * (len(candidates) - 1) / (count - 1)) for i in range(count)]
    return [candidates[index] for index in indexes]


def receiver_layout(box_or_x: Any, z: float | None = None, mount: PegboardMountSpec | None = None) -> dict[str, Any]:
    if hasattr(box_or_x, "x"):
        x = float(box_or_x.x)
        height = float(box_or_x.z)
        mount = normalise_mount_spec(getattr(box_or_x, "pegboard", mount))
    else:
        x = float(box_or_x)
        height = float(z)
        mount = normalise_mount_spec(mount)
    if not mount.enabled:
        return {"enabled": False, "receivers": [], "ribs": []}
    standard = pegboard_standard(mount.standard)
    count_x = _auto_count(x, PEGBOARD_AUTO_SUPPORT_X, PEGBOARD_MAX_CLEATS_X) \
        if mount.cleat_x == "auto" else int(mount.cleat_x)
    count_y = _auto_count(height, PEGBOARD_AUTO_SUPPORT_Y, PEGBOARD_MAX_CLEATS_Y) \
        if mount.cleat_y == "auto" else int(mount.cleat_y)
    # The standard adapter uses two vertically adjacent holes. Its upper
    # hooked peg and narrow plate must remain concealed behind the bin.
    end_margin = 30.4 if standard.id == "standard" else None
    if mount.cleat_y == "auto":
        while count_y > 1:
            try:
                _axis_positions(height, standard.pitch_y_mm, count_y,
                                PEGBOARD_RECEIVER_HEIGHT, "Y", end_margin=end_margin)
                break
            except ValueError:
                count_y -= 1
    zs = _axis_positions(height, standard.pitch_y_mm, count_y,
                         PEGBOARD_RECEIVER_HEIGHT, "Y", end_margin=end_margin)
    receivers = []
    for row, pz in enumerate(zs):
        grid_y = round(pz / standard.pitch_y_mm - 0.5)
        stagger = standard.stagger_x_mm if int(grid_y) % 2 else 0.0
        xs = _axis_positions(
            x, standard.pitch_x_mm, count_x, PEGBOARD_RECEIVER_WIDTH, "X", stagger,
        )
        for col, px in enumerate(xs):
            receivers.append({
                "x": round(px - x / 2.0, 6), "z": round(pz, 6),
                "row": row, "column": col,
                "grid_x": round(px / standard.pitch_x_mm - 0.5, 6),
                "grid_y": int(grid_y),
            })
    unique_x = sorted({float(one["x"]) for one in receivers})
    ribs: list[float] = []
    for left, right in zip(unique_x, unique_x[1:]):
        gap = right - left - PEGBOARD_RECEIVER_WIDTH
        if gap <= PEGBOARD_MAX_UNSUPPORTED_GAP + 1e-9:
            continue
        extras = int(math.ceil(gap / PEGBOARD_MAX_UNSUPPORTED_GAP)) - 1
        ribs.extend(left + (right - left) * i / (extras + 1) for i in range(1, extras + 1))
    return {
        "enabled": True,
        "standard": standard.id,
        "cleat_x": mount.cleat_x,
        "cleat_y": mount.cleat_y,
        "resolved_x": count_x,
        "resolved_y": count_y,
        "minimum_height_mm": round(max(one["z"] for one in receivers) +
                                   (30.4 if standard.id == "standard" else
                                    PEGBOARD_EDGE_INSET + PEGBOARD_RECEIVER_HEIGHT / 2), 6),
        "receivers": receivers,
        "ribs": [round(value, 6) for value in ribs],
        "projection_mm": PEGBOARD_PROJECTION,
        "contact_plane_y": round(PEGBOARD_PROJECTION, 6),
    }


def pegboard_layout_for_bin(one: dict[str, Any], standard_id: Any) -> dict[str, Any]:
    standard = pegboard_standard(standard_id)
    stored_standard = str(one.get("pegboard_standard") or "").strip().lower()
    requested_standard = stored_standard or standard.id
    if requested_standard not in PEGBOARD_STANDARDS:
        requested_standard = standard.id
    mount = PegboardMountSpec(
        True,
        requested_standard,
        _count(one.get("cleat_x", "auto"), PEGBOARD_MAX_CLEATS_X, "X"),
        _count(one.get("cleat_y", "auto"), PEGBOARD_MAX_CLEATS_Y, "Y"),
    )
    layout = receiver_layout(float(one["x"]), float(one["z"]), mount)
    cells_x = max(1, int(math.ceil(float(one["x"]) / standard.pitch_x_mm - 1e-9)))
    cells_y = max(1, int(math.ceil(float(one["z"]) / standard.pitch_y_mm - 1e-9)))
    mounts = []
    for receiver in layout["receivers"]:
        mounts.append([receiver["grid_x"], receiver["grid_y"]])
        if standard.id == "standard":
            # Its straight and hooked pegs engage adjacent 1-inch holes.
            mounts.append([receiver["grid_x"], receiver["grid_y"] + 1])
    return {
        **layout,
        "compatible": stored_standard == standard.id,
        "cells_x": cells_x,
        "cells_y": cells_y,
        "mount_offsets": mounts,
    }


def _box(extents: tuple[float, float, float], center: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.box(extents=np.asarray(extents, dtype=float))
    mesh.apply_translation(center)
    return mesh


def _prism_x(profile: list[tuple[float, float]], x0: float, x1: float) -> trimesh.Trimesh:
    """Extrude a convex Y/Z cleat profile across the bin width."""
    count = len(profile)
    vertices = np.asarray(
        [(x, y, z) for x in (x0, x1) for y, z in profile], dtype=float,
    )
    faces: list[tuple[int, int, int]] = []
    for index in range(1, count - 1):
        faces.extend([(0, index + 1, index), (count, count + index, count + index + 1)])
    for index in range(count):
        next_index = (index + 1) % count
        faces.extend([
            (index, next_index, count + next_index),
            (index, count + next_index, count + index),
        ])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


def _receiver_mesh(cx: float, back_y: float, cz: float) -> trimesh.Trimesh:
    rail = 3.0
    side = (PEGBOARD_RECEIVER_WIDTH - rail) / 2.0
    guide_depth = 4.5
    pieces = [
        _box((rail, guide_depth + 0.35, PEGBOARD_RECEIVER_HEIGHT),
             (cx - side, back_y + guide_depth / 2.0 - 0.175, cz)),
        _box((rail, guide_depth + 0.35, PEGBOARD_RECEIVER_HEIGHT),
             (cx + side, back_y + guide_depth / 2.0 - 0.175, cz)),
        # The underside rises outward at 45 degrees. Gravity pulls this
        # inverted hook against the mating sloped adapter, not a flat shelf.
        _prism_x([
            (back_y - 0.35, cz - 2.1),
            (back_y + PEGBOARD_PROJECTION, cz + 3.4),
            (back_y + PEGBOARD_PROJECTION, cz + 5.8),
            (back_y - 0.35, cz + 0.3),
        ], cx - PEGBOARD_RECEIVER_WIDTH / 2, cx + PEGBOARD_RECEIVER_WIDTH / 2),
    ]
    return union(pieces)


def apply_pegboard_mount_structure(box_spec: Any, body: trimesh.Trimesh) -> trimesh.Trimesh:
    layout = receiver_layout(box_spec)
    if not layout["enabled"]:
        return body
    back_y = float(box_spec.y) / 2.0
    pieces = [body]
    pieces.extend(_receiver_mesh(float(one["x"]), back_y, float(one["z"])) for one in layout["receivers"])
    for x in layout["ribs"]:
        pieces.append(_box(
            (PEGBOARD_RIB_WIDTH, PEGBOARD_PROJECTION + 0.35, max(1.0, float(box_spec.z) - 2.0)),
            (float(x), back_y + PEGBOARD_PROJECTION / 2.0 - 0.175, float(box_spec.z) / 2.0),
        ))
    return union(pieces)


def _cylinder_y(radius: float, length: float, center: tuple[float, float, float]) -> trimesh.Trimesh:
    mesh = trimesh.creation.cylinder(radius=radius, height=length, sections=24)
    mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0)))
    mesh.apply_translation(center)
    return mesh


def make_board_adapter(standard_id: Any) -> trimesh.Trimesh:
    standard = pegboard_standard(standard_id)
    # Board is on -Y; the universal male cleat faces +Y into the bin receiver.
    if standard.id == "standard":
        # The lower peg shares the male cleat's height. The upper peg is
        # exactly one board row above it, matching mount_offsets below.
        plate = _box((10.0, 3.0, 31.4), (0.0, 0.0, 29.7))
        straight = _cylinder_y(2.65, 8.0, (0.0, -5.5, 17.0))
        hooked = _cylinder_y(2.65, 8.0, (0.0, -5.5, 42.4))
        hook = _box((4.8, 3.0, 4.0), (0.0, -9.0, 40.2))
        back = union([plate, straight, hooked, hook])
    else:
        # A single vertical SKÅDIS slot holds the tab and its locking hook;
        # adjacent slot rows stagger sideways and cannot take two straight tabs.
        plate = _box((10.0, 3.0, 16.0), (0.0, 0.0, 8.0))
        tab = _box((4.4, 8.0, 12.0), (0.0, -5.5, 8.0))
        hook = _box((4.4, 3.0, 3.0), (0.0, -9.0, 3.0))
        back = union([plate, tab, hook])
    center = 17.0 if standard.id == "standard" else 8.0
    # One narrow sloped cleat, not a separate shelf. Its upper face and the
    # universal receiver underside have 0.2 mm of sliding clearance.
    male = _prism_x([
        (1.15, center - 5.3),
        (7.0, center - 5.3),
        (7.0, center - 2.3),
        (1.15, center + 3.2),
    ], -3.7, 3.7)
    return union([back, male])


def make_board_adapters(box_spec: Any) -> list[tuple[str, trimesh.Trimesh]]:
    layout = receiver_layout(box_spec)
    if not layout["enabled"]:
        return []
    result = []
    for index, _receiver in enumerate(layout["receivers"], 1):
        mesh = make_board_adapter(layout["standard"])
        # Lay the narrow side on the bed, as in the fit prototype. The board
        # peg and cleat profiles can then rise with minimal bridging.
        mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2.0, (0.0, 1.0, 0.0)))
        mesh.apply_translation((40.0 * ((index - 1) % 5),
                                25.0 * ((index - 1) // 5),
                                -float(mesh.bounds[0][2])))
        result.append((f"pegboard_adapter_{index}", mesh))
    return result
