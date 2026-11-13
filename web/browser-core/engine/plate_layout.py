"""Browser plate layout: side-by-side placement and combined-plate packaging.

Separate from the ordinary 3MF export in ``three_mf``: the combined plate is
deliberately a four-member package with no Bambu attachment relationship and no
Application/Title stamp. Package validation/reading of the *source* design files
reuses ``three_mf._read``; no native lib3mf or trimesh 3MF loader is involved.
Structure and meaning follow the native module; byte identity is not claimed.
"""
from io import BytesIO
import re
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

from organizer_engine._export import unique_object_names
from wf_browser_core import three_mf

PLATE_GAP_MM = 10.0
PLATE_EDGE_MM = 3.0

_CORE = three_mf.CORE
_ITEM_RE = re.compile(r"<(?:\w+:)?item\b[^>]*?/?>")
_TRANSFORM_RE = re.compile(r'\btransform\s*=\s*"([^"]*)"')
_PLATE_MEMBERS = ("3D/3dmodel.model", "Metadata/model_settings.config",
                  "[Content_Types].xml", "_rels/.rels")


def _tag(name):
    return f"{{{_CORE}}}{name}"


def _file_bounds(path: Path) -> np.ndarray:
    """Bounds of every actual build instance, after validating the package."""
    per_mesh = three_mf._read(Path(path).read_bytes())[4]
    return np.array([per_mesh[:, 0].min(axis=0), per_mesh[:, 1].max(axis=0)], dtype=float)


def plan_plate(sizes, bed, gap=PLATE_GAP_MM, edge=PLATE_EDGE_MM, names=None):
    """Shelf-pack footprints. Returns ([(x, y, rotated)], error or None).

    A footprint that only fits the bed turned a quarter is turned. ``x, y`` is
    the lower corner of the placed (possibly turned) footprint.
    """
    usable_x, usable_y = bed[0] - 2 * edge, bed[1] - 2 * edge
    placed, cursor_x, cursor_y, row_depth = [], 0.0, 0.0, 0.0
    for index, (w, d) in enumerate(sizes):
        label = names[index] if names else f"part {index + 1}"
        turned = (w > usable_x + 1e-6 or d > usable_y + 1e-6) and (
            d <= usable_x + 1e-6 and w <= usable_y + 1e-6)
        pw, pd = (d, w) if turned else (w, d)
        if pw > usable_x + 1e-6 or pd > usable_y + 1e-6:
            return [], f"{label} ({w:.1f} x {d:.1f} mm) exceeds printer X/Y ({bed[0]:g} x {bed[1]:g} mm)"
        if cursor_x > 0 and cursor_x + pw > usable_x + 1e-6:
            cursor_x, cursor_y, row_depth = 0.0, cursor_y + row_depth + gap, 0.0
        if cursor_y + pd > usable_y + 1e-6:
            return [], (f"Cannot place {label} and the remaining parts {names[index + 1:] if names else len(sizes) - index - 1}: printer X/Y exhausted "
                        f"({bed[0]:.0f} x {bed[1]:.0f} mm) with a {gap:.0f} mm gap")
        placed.append((edge + cursor_x, edge + cursor_y, turned))
        cursor_x += pw + gap
        row_depth = max(row_depth, pd)
    return placed, None


def _plan_bounds(bounds, names, profile):
    from organizer_outputs.printer_profile import component_fit
    sizes = [(float(b[1][0] - b[0][0]), float(b[1][1] - b[0][1])) for b in bounds]
    for name, b in zip(names, bounds):
        fit = component_fit(tuple(float(v) for v in b[1] - b[0]), ("flat", "bed_90"), profile)
        if fit["fits"] is False:
            return [], f"{name}: {fit['reason']}"
    if profile.get("configured", True):
        bed = (float(profile["x_mm"]), float(profile["y_mm"]))
    else:
        # A layout canvas, not an invented printer-fit guarantee.
        bed = (sum(w + PLATE_GAP_MM for w, _ in sizes) + 2 * PLATE_EDGE_MM,
               max((d for _, d in sizes), default=0) + 2 * PLATE_EDGE_MM)
    placed, error = plan_plate(sizes, bed, names=names)
    if error:
        return [], error
    combined = (max(x + (d if turned else w) for (x, y, turned), (w, d) in zip(placed, sizes)),
                max(y + (w if turned else d) for (x, y, turned), (w, d) in zip(placed, sizes)),
                max(float(b[1][2] - b[0][2]) for b in bounds))
    fit = component_fit(combined, ("flat",), profile)
    return ([], f"Combined plate ({', '.join(names)}): {fit['reason']}") if fit["fits"] is False else (placed, None)


def pack_mesh_objects(objects, profile):
    """Pack registered mesh groups by their generated bounds, keeping inlays together."""
    bounds = [np.array([np.min([m.bounds[0] for _, m in parts], axis=0),
                        np.max([m.bounds[1] for _, m in parts], axis=0)]) for _, parts in objects]
    placed, error = _plan_bounds(bounds, [name for name, _ in objects], profile)
    if error:
        raise ValueError(error)
    packed = []
    for (name, parts), b, (x, y, turned) in zip(objects, bounds, placed):
        moved = []
        for part, mesh in parts:
            mesh = mesh.copy()
            mesh.apply_transform(_placement_move(b, x, y, turned).T)
            moved.append((part, mesh))
        packed.append((name, moved))
    return packed


def _row_matrix(values):
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3], m[3, :3] = values[0:3], values[3:6], values[6:9], values[9:12]
    return m


def _format_matrix(m):
    flat = [*m[0, :3], *m[1, :3], *m[2, :3], *m[3, :3]]
    return " ".join(repr(round(float(v), 6) + 0.0) for v in flat)


def _placement_move(bounds, x, y, turned):
    low = bounds[0]
    d = bounds[1][1] - low[1]
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
    return move


def _move_file(source, dest, bounds, x, y, turned):
    """Copy ``source`` member-for-member, changing only build-item transforms."""
    source, dest = Path(source), Path(dest)
    move = _placement_move(bounds, x, y, turned)

    def patch_item(match):
        tag = match.group(0)
        found = _TRANSFORM_RE.search(tag)
        existing = np.eye(4)
        if found:
            values = [float(v) for v in found.group(1).split()]
            if len(values) != 12 or not np.isfinite(values).all():
                raise ValueError(f"{source.name}: invalid build item transform")
            existing = _row_matrix(values)
        combined = _format_matrix(existing @ move)
        if found:
            return tag[:found.start()] + f'transform="{combined}"' + tag[found.end():]
        closing = "/>" if tag.endswith("/>") else ">"
        return tag[: -len(closing)].rstrip() + f' transform="{combined}"' + closing

    buffer = BytesIO()
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zout:
        patched = False
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename.lstrip("/").lower() == "3d/3dmodel.model":
                text = data.decode("utf-8")
                build = text.find("<build")
                if build < 0:
                    build = text.find(":build")
                    build = text.rfind("<", 0, build) if build >= 0 else -1
                if build >= 0:
                    head, tail = text[:build], text[build:]
                    tail, count = _ITEM_RE.subn(patch_item, tail)
                    patched = patched or count > 0
                    data = (head + tail).encode("utf-8")
            zout.writestr(info, data)
        if not patched:
            raise ValueError(f"{source.name}: no build item to place on the plate")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(buffer.getvalue())


def space_out_for_plate(files, profile, root=None):
    """Copies of ``files`` laid side by side on the plate, plus any fit problems.

    One file needs no spacing and is returned untouched. If the parts cannot all
    sit on the bed the problem is returned (and no copies are made).
    """
    files = [Path(f) for f in files]
    if not files:
        return files, []
    if len(files) == 1:
        from organizer_outputs.printer_profile import print_file_fit_issues
        return files, print_file_fit_issues(files[0], profile)
    bounds = [_file_bounds(f) for f in files]
    placed, error = _plan_bounds(bounds, [f.name for f in files], profile)
    if error:
        return files, [error]
    base = Path(root) if root else Path(tempfile.gettempdir()) / "Wavefinity" / "Plate Layouts"
    folder = base / uuid.uuid4().hex
    folder.mkdir(parents=True)
    out = []
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


def _check_plate(raw):
    """Read the merged archive back: exact members, unique IDs, valid references."""
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        names = archive.namelist()
        if sorted(names) != sorted(_PLATE_MEMBERS) or archive.testzip() is not None:
            raise ValueError("Combined plate must contain exactly the four plate members")
        model = three_mf._parse_xml(archive.read("3D/3dmodel.model"))
        config = three_mf._parse_xml(archive.read("Metadata/model_settings.config"))
        for member in ("[Content_Types].xml", "_rels/.rels"):
            three_mf._parse_xml(archive.read(member))
    resources = model.find(_tag("resources"))
    build = model.find(_tag("build"))
    ids = [int(n.attrib["id"]) for n in resources]
    if ids != list(range(1, len(ids) + 1)):
        raise ValueError("Combined plate resource IDs are not contiguous from 1")
    known = set(ids)
    object_names = [n.get("name") for n in resources if n.tag == _tag("object")]
    if any(not n for n in object_names) or len(set(object_names)) != len(object_names):
        raise ValueError("Combined plate object names are empty or duplicated")
    for node in resources.iter():
        for attr in ("objectid", "pid"):
            if attr in node.attrib and int(node.attrib[attr]) not in known:
                raise ValueError("Combined plate has a dangling resource reference")
    if not len(build) or any(int(i.attrib["objectid"]) not in known for i in build):
        raise ValueError("Combined plate build items are missing or dangling")
    by_id = {int(n.attrib["id"]): n.get("name") for n in resources}
    for obj in config.findall("object"):
        for node in [obj, *obj.findall("part")]:
            key = int(node.attrib["id"])
            meta = {m.get("key"): m.get("value") for m in node.findall("metadata")}
            if key not in known or ("name" in meta and meta["name"] != by_id[key]):
                raise ValueError("Combined plate Bambu config does not match resources")


def combine_for_plate(files, profile, dest):
    """Merge physical occurrences into one model, preserving registered parts.

    Fit is decided before writing. Only resource IDs, names and build transforms
    change; component transforms and mesh payloads remain intact. Output is
    exactly four members, with no Bambu attachment relationship and no
    Application/Title stamp (deliberately unlike the ordinary export).
    """
    files, dest = [Path(f) for f in files], Path(dest)
    if not files:
        raise ValueError("No files to open in slicer")
    bounds = [_file_bounds(f) for f in files]
    placed, error = _plan_bounds(bounds, [f.name for f in files], profile)
    if error:
        return dest, [error]

    model = ET.Element(_tag("model"), unit="millimeter")
    resources = ET.SubElement(model, _tag("resources"))
    build = ET.SubElement(model, _tag("build"))
    config = ET.Element("config")
    next_id, used_names = 1, []
    for source, b, (x, y, turned) in zip(files, bounds, placed):
        with zipfile.ZipFile(source) as archive:
            members = {n.lstrip("/").lower(): n for n in archive.namelist()}
            incoming = three_mf._parse_xml(archive.read(members["3d/3dmodel.model"]))
            source_config = (three_mf._parse_xml(archive.read(members["metadata/model_settings.config"]))
                             if "metadata/model_settings.config" in members else ET.Element("config"))
        if incoming.get("unit", "millimeter") != "millimeter":
            raise ValueError(f"{source.name}: expected millimetre model units")
        entries = list(incoming.find(_tag("resources")))
        ids, names = {}, {}
        for entry in entries:
            ids[entry.attrib["id"]] = str(next_id)
            next_id += 1
            if entry.tag == _tag("object"):
                name = unique_object_names([entry.get("name", source.stem)], taken=used_names)[0]
                used_names.append(name)
                entry.set("name", name)
                names[entry.attrib["id"]] = name
        for entry in entries:
            old_id = entry.attrib["id"]
            for node in entry.iter():
                for attr in ("objectid", "pid"):
                    if attr in node.attrib:
                        node.set(attr, ids[node.attrib[attr]])
            entry.set("id", ids[old_id])
            resources.append(entry)
        move = _placement_move(b, x, y, turned)
        items = list(incoming.find(_tag("build")))
        if not items:
            raise ValueError(f"{source.name}: no build item to place on the plate")
        for item in items:
            item.set("objectid", ids[item.attrib["objectid"]])
            existing = (_row_matrix([float(v) for v in item.attrib["transform"].split()])
                        if "transform" in item.attrib else np.eye(4))
            item.set("transform", _format_matrix(existing @ move))
            build.append(item)
        for obj in source_config.findall("object"):
            for node in [obj, *obj.findall("part")]:
                old_id = node.attrib["id"]
                node.set("id", ids[old_id])
                for meta in node.findall("metadata"):
                    if meta.get("key") == "name":
                        meta.set("value", names[old_id])
            config.append(obj)

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("3D/3dmodel.model", ET.tostring(model, encoding="utf-8", xml_declaration=True))
        archive.writestr("Metadata/model_settings.config", ET.tostring(config, encoding="utf-8", xml_declaration=True))
        archive.writestr("[Content_Types].xml", (
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>'
            '<Default Extension="config" ContentType="application/octet-stream"/></Types>'))
        archive.writestr("_rels/.rels", (
            '<?xml version="1.0"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" '
            'Target="/3D/3dmodel.model"/></Relationships>'))
    raw = buffer.getvalue()
    _check_plate(raw)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return dest, []
