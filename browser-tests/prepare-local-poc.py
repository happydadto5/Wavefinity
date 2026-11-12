"""Prepare the pinned, offline comparison data; never called by the web server.

Run with Wavefinity's existing Python environment. No dependency installation.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import shapely
import trimesh
from shapely.affinity import translate
from shapely.geometry import LineString
from organizer_engine import BoxSpec, make_box, mesh_report
from organizer_engine._wave import (
    nested_clearance, wave_value, wavy_outer_polygon, wavy_cavity_polygon,
)

SOURCES = [
    "organizer_engine/_specs.py", "organizer_engine/_wave.py",
    "organizer_engine/_boxes.py", "organizer_engine/_lift_grabbers.py",
    "organizer_engine/_fit.py", "organizer_features/pegboard.py",
    "organizer_geometry/__init__.py", "organizer_geometry/_nearest.py",
    "organizer_geometry/_stages.py",
]


def main():
    baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if subprocess.check_output(["git", "diff", "HEAD", "--", *SOURCES], cwd=ROOT):
        raise RuntimeError("Canonical sources must be committed before pinning")
    destination = ROOT / "web/browser-local-poc"
    destination.mkdir(parents=True, exist_ok=True)
    archive = io.BytesIO()
    hashes = {}
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in SOURCES:
            body = (ROOT / name).read_bytes()
            hashes[name] = hashlib.sha256(body).hexdigest()
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, body)
    source_bytes = archive.getvalue()
    (destination / "canonical.zip").write_bytes(source_bytes)
    spec = BoxSpec(x=42, y=42, z=28)
    started = time.perf_counter()
    mesh = make_box(spec)
    build_ms = (time.perf_counter() - started) * 1000
    report = mesh_report("42x42x28 ordinary Wavefinity bin", mesh)
    # Preserve the actual float64 mesh, rather than using STL's float32 storage.
    np.savez_compressed(ROOT / "browser-tests/reference-42x42x28.npz",
                        vertices=mesh.vertices, faces=mesh.faces)
    outer, cavity = wavy_outer_polygon(spec), wavy_cavity_polygon(spec)
    neighbor = translate(outer, xoff=42)
    seam = []
    for y in np.linspace(-18, 18, 145):
        line = LineString([(-30, y), (70, y)])
        seam.append(neighbor.intersection(line).bounds[0] - outer.intersection(line).bounds[2])
    result = {
        "baseline_commit": baseline, "source_sha256": hashes,
        "archive_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "spec": {"x": 42, "y": 42, "z": 28, "wall": spec.wall,
                 "base_thickness": spec.base_thickness},
        "versions": {"numpy": np.__version__, "shapely": shapely.__version__,
                     "geos": shapely.geos_version_string, "trimesh": trimesh.__version__},
        "build_ms": build_ms, "mesh_report": report,
        "bounds_mm": mesh.bounds.tolist(), "volume_mm3": float(mesh.volume),
        "outer_xy": list(outer.exterior.coords), "cavity_xy": list(cavity.exterior.coords),
        "wave_samples": [[float(y), wave_value(float(y))] for y in np.linspace(-7, 7, 225)],
        "seam": {"nominal_across_mm": 0.25, "normal_lower_bound_mm": nested_clearance(),
                 "sample_min_mm": min(seam), "sample_max_mm": max(seam)},
        "tolerances": {"profile_hausdorff_mm": 1e-7, "bounds_mm": 1e-7,
                       "relative_volume": 1e-7, "seam_mm": 1e-7},
    }
    (destination / "reference.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"baseline": baseline, "build_ms": build_ms, "mesh": report,
                      "archive_bytes": len(source_bytes), "seam": result["seam"]}))


if __name__ == "__main__":
    main()
