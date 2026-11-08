"""Lay a Print handoff's parts out side by side on the plate.

Designed files keep their assembled coordinates (the bin, the insert sitting in
it, the lid on top, ...). Handing those straight to a slicer stacks every part
on the same spot, so the handoff gets *copies* whose 3MF build-item transforms
move each part to its own clear spot on the bed, resting at z = 0. The saved
design files are never modified.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import numpy as np
import trimesh

PLATE_GAP_MM = 10.0
PLATE_EDGE_MM = 3.0

_ITEM_RE = re.compile(r"<(?:\w+:)?item\b[^>]*?/?>")
_TRANSFORM_RE = re.compile(r'\btransform\s*=\s*"([^"]*)"')


def _file_bounds(path: Path) -> np.ndarray:
    scene = trimesh.load(path, force="scene")
    return np.asarray(scene.bounds, dtype=float)


def plan_plate(sizes: list[tuple[float, float]], bed: tuple[float, float],
               gap: float = PLATE_GAP_MM, edge: float = PLATE_EDGE_MM):
    """Shelf-pack footprints. Returns ([(x, y, rotated)], error or None).

    A footprint that only fits the bed turned a quarter is turned. ``x, y`` is
    the lower corner of the placed (possibly turned) footprint.
    """
    usable_x, usable_y = bed[0] - 2 * edge, bed[1] - 2 * edge
    placed, cursor_x, cursor_y, row_depth = [], 0.0, 0.0, 0.0
    for index, (w, d) in enumerate(sizes):
        turned = (w > usable_x + 1e-6 or d > usable_y + 1e-6) and (
            d <= usable_x + 1e-6 and w <= usable_y + 1e-6)
        pw, pd = (d, w) if turned else (w, d)
        if pw > usable_x + 1e-6 or pd > usable_y + 1e-6:
            return [], f"part {index + 1} ({w:.1f} x {d:.1f} mm) is larger than the printer bed"
        if cursor_x > 0 and cursor_x + pw > usable_x + 1e-6:
            cursor_x, cursor_y, row_depth = 0.0, cursor_y + row_depth + gap, 0.0
        if cursor_y + pd > usable_y + 1e-6:
            return [], ("the parts cannot all sit side by side on the printer bed "
                        f"({bed[0]:.0f} x {bed[1]:.0f} mm) with a {gap:.0f} mm gap")
        placed.append((edge + cursor_x, edge + cursor_y, turned))
        cursor_x += pw + gap
        row_depth = max(row_depth, pd)
    return placed, None


def _row_matrix(values: list[float]) -> np.ndarray:
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3], m[3, :3] = values[0:3], values[3:6], values[6:9], values[9:12]
    return m


def _format_matrix(m: np.ndarray) -> str:
    flat = [*m[0, :3], *m[1, :3], *m[2, :3], *m[3, :3]]
    return " ".join(repr(round(float(v), 6) + 0.0) for v in flat)


def _move_file(source: Path, dest: Path, bounds: np.ndarray, x: float, y: float, turned: bool) -> None:
    low = bounds[0]
    w, d = bounds[1][0] - low[0], bounds[1][1] - low[1]
    # Row-vector convention (3MF): p' = p @ M. Bring the lower corner to the
    # origin, optionally quarter-turn about z, then slide to the placed spot.
    move = np.eye(4)
    move[3, :3] = -low
    if turned:
        turn = np.eye(4)
        turn[0, :2], turn[1, :2] = (0.0, 1.0), (-1.0, 0.0)   # (x, y) -> (-y, x)
        move = move @ turn
        move[3, 0] += d
    move[3, 0] += x
    move[3, 1] += y

    def patch_item(match: re.Match) -> str:
        tag = match.group(0)
        found = _TRANSFORM_RE.search(tag)
        existing = np.eye(4)
        if found:
            values = [float(v) for v in found.group(1).split()]
            if len(values) == 12:
                existing = _row_matrix(values)
        combined = _format_matrix(existing @ move)
        if found:
            return tag[:found.start()] + f'transform="{combined}"' + tag[found.end():]
        closing = "/>" if tag.endswith("/>") else ">"
        return tag[: -len(closing)].rstrip() + f' transform="{combined}"' + closing

    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        patched = False
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.lstrip("/").lower() == "3d/3dmodel.model":
                text = data.decode("utf-8")
                build = text.find("<build")
                if build >= 0:
                    head, tail = text[:build], text[build:]
                    tail, count = _ITEM_RE.subn(patch_item, tail)
                    patched = patched or count > 0
                    data = (head + tail).encode("utf-8")
            zout.writestr(info, data)
        if not patched:
            raise ValueError(f"{source.name}: no build item to place on the plate")


def space_out_for_plate(files: list[Path], profile: dict,
                        root: Path | None = None) -> tuple[list[Path], list[str]]:
    """Copies of ``files`` laid side by side on the plate, plus any fit problems.

    One file needs no spacing and is returned untouched. If the parts cannot all
    sit on the bed the problem is returned (and no copies are made) so the
    caller reports it before launching the slicer.
    """
    files = [Path(f) for f in files]
    if len(files) < 2:
        return files, []
    bounds = [_file_bounds(f) for f in files]
    sizes = [(float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1])) for b in bounds]
    placed, error = plan_plate(sizes, (float(profile["x_mm"]), float(profile["y_mm"])))
    if error:
        return files, [error]
    base = root or Path(tempfile.gettempdir()) / "Wavefinity" / "Plate Layouts"
    folder = base / uuid.uuid4().hex
    folder.mkdir(parents=True)
    out: list[Path] = []
    try:
        for source, b, (x, y, turned) in zip(files, bounds, placed):
            dest = folder / source.name
            if dest.exists():
                dest = folder / f"{len(out):02d} {source.name}"
            _move_file(source, dest, b, x, y, turned)
            out.append(dest)
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return out, []
