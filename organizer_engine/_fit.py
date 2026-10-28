"""Wavefinity engine mesh reports and installed-fit validation."""

from __future__ import annotations

import hashlib
import numpy as np
import trimesh
from shapely.geometry import Polygon
from organizer_geometry import translated

from ._specs import BoxSpec, ConnectorSpec
from ._wave import _sample_count
from ._boxes import make_box, connector_bin_heights, _connector_corridor_polygon


def mesh_report(name: str, mesh: trimesh.Trimesh) -> dict[str, object]:
    report = {
        "name": name,
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "positive_volume": bool(mesh.volume > 0),
        "components": len(mesh.split(only_watertight=False)),
        "bounds_mm": np.round(mesh.bounds, 3).tolist(),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "triangles": int(len(mesh.faces)),
    }
    if not all(
        (
            report["watertight"], report["winding_consistent"],
            report["positive_volume"], report["components"] == 1,
        )
    ):
        raise RuntimeError(f"{name} failed mesh validation: {report}")
    return report


def mesh_fingerprint(mesh: trimesh.Trimesh) -> str:
    return hashlib.sha256(mesh.export(file_type="stl")).hexdigest().upper()


def intersection_volume(a: trimesh.Trimesh, b: trimesh.Trimesh) -> float:
    overlap = trimesh.boolean.intersection([a, b], engine="manifold")
    if overlap is None or len(overlap.faces) == 0:
        return 0.0
    triangles = overlap.triangles
    signed = np.einsum(
        "ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])
    )
    return float(abs(signed.sum()) / 6.0)


def installed_boxes(
    box: BoxSpec, along_axis: str = "y"
) -> list[trimesh.Trimesh]:
    mesh = make_box(box)
    if along_axis.lower() == "y":
        return [
            translated(mesh, (-box.x / 2.0, 0.0, 0.0)),
            translated(mesh, (box.x / 2.0, 0.0, 0.0)),
        ]
    return [
        translated(mesh, (0.0, -box.y / 2.0, 0.0)),
        translated(mesh, (0.0, box.y / 2.0, 0.0)),
    ]


def installed_side_boxes(
    box: BoxSpec, along_axis: str, bin_a_height: float, bin_b_height: float,
) -> list[trimesh.Trimesh]:
    """Two adjacent boxes with independently specified rim heights."""
    a = BoxSpec(
        box.x, box.y, bin_a_height, box.wall, box.corner_fillet, box.flat_inside,
        box.base_thickness,
    )
    b = BoxSpec(
        box.x, box.y, bin_b_height, box.wall, box.corner_fillet, box.flat_inside,
        box.base_thickness,
    )
    if along_axis.lower() == "y":
        return [
            translated(make_box(a), (-box.x / 2.0, 0.0, 0.0)),
            translated(make_box(b), (box.x / 2.0, 0.0, 0.0)),
        ]
    return [
        translated(make_box(a), (0.0, -box.y / 2.0, 0.0)),
        translated(make_box(b), (0.0, box.y / 2.0, 0.0)),
    ]


def seat_transform(
    box: BoxSpec, connector: ConnectorSpec, position: float, axis: str,
    cap_height: float | None = None,
):
    z = (box.z if cap_height is None else cap_height) - connector.arm_depth
    return (position, 0.0, z) if axis == "x" else (0.0, position, z)


def validate_side_fit(
    box: BoxSpec,
    connector: ConnectorSpec,
    clip: trimesh.Trimesh,
    along_axis: str = "y",
    position: float = 0.0,
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
) -> float:
    """Overlap of the seated connector with the two boxes it joins."""
    axis = along_axis.lower()
    heights = connector_bin_heights(box, bin_a_height, bin_b_height)
    boxes = installed_side_boxes(box, axis, *heights)
    seated = translated(clip, seat_transform(box, connector, position, axis, max(heights)))
    overlap = sum(intersection_volume(seated, item) for item in boxes)
    if overlap > 0.01:
        raise RuntimeError(
            f"side connector collides with installed boxes: {overlap:.6f} mm^3"
        )
    return overlap


def _plain_corridor(
    box: BoxSpec, axis: str, position: float, samples: np.ndarray, half_width: float
) -> Polygon:
    """Unnotched fit sampler following the actual eroded interior faces."""
    dense = np.linspace(
        samples[0], samples[-1], _sample_count(float(samples[-1] - samples[0]))
    )
    return _connector_corridor_polygon(axis, dense, position, half_width, box.wall_depth)
