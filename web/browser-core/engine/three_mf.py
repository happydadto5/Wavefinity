"""Browser ordinary-export 3MF OPC writer and runtime integrity reader.

Only the core mesh/components subset emitted here is accepted. No native
lib3mf, trimesh format exporter, or plate-layout packaging is used.
"""
from io import BytesIO
import hashlib
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import trimesh

from organizer_engine._fit import mesh_report, intersection_volume
from organizer_engine._export import (
    BAMBU_PACKAGE_REL, TEXT_PART_FILAMENT, label_mesh_report,
    unique_object_names, accent_body_parts, assigned_filaments,
    _model_settings_config, _object_groups_model_settings_config,
)

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
MODEL_REL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
MODEL_TYPE = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
IDENTITY = "1 0 0 0 1 0 0 0 1 0 0 0"


def _q(name):
    return f"{{{CORE}}}{name}"


def _xml(root):
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _new_model():
    root = ET.Element(_q("model"), {"unit": "millimeter", "xml:lang": "en-US"})
    return root, ET.SubElement(root, _q("resources")), ET.SubElement(root, _q("build"))


def _stamp_identity(model, title=""):
    seen = {node.get("name") for node in model.findall(_q("metadata"))}
    for name, value in (("Application", "Wavefinity"), ("Title", title)):
        if value and name not in seen:
            node = ET.Element(_q("metadata"), {"name": name})
            node.text = value
            model.insert(len(model.findall(_q("metadata"))), node)


def _mesh(resources, name, mesh):
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    faces = np.asarray(mesh.faces)
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
            or not np.isfinite(vertices).all() or faces.ndim != 2
            or faces.shape[1] != 3 or not len(faces)
            or not np.issubdtype(faces.dtype, np.integer)
            or faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError(f"Invalid mesh arrays for {name}")
    object_id = len(resources) + 1
    obj = ET.SubElement(resources, _q("object"), id=str(object_id), type="model", name=name)
    node = ET.SubElement(obj, _q("mesh"))
    verts = ET.SubElement(node, _q("vertices"))
    for vertex in vertices:
        ET.SubElement(verts, _q("vertex"), dict(zip(("x", "y", "z"), (format(float(v), ".17g") for v in vertex))))
    triangles = ET.SubElement(node, _q("triangles"))
    for face in faces:
        ET.SubElement(triangles, _q("triangle"), dict(zip(("v1", "v2", "v3"), (str(int(v)) for v in face))))
    return object_id


def _components(resources, name, children):
    object_id = len(resources) + 1
    obj = ET.SubElement(resources, _q("object"), id=str(object_id), type="model", name=name)
    node = ET.SubElement(obj, _q("components"))
    for child in children:
        ET.SubElement(node, _q("component"), objectid=str(child), transform=IDENTITY)
    return object_id


def _item(build, object_id):
    ET.SubElement(build, _q("item"), objectid=str(object_id), transform=IDENTITY)


def _strict_write(model, wrapper, output):
    """Serialize then read the actual archive before installing any output.

    ``wrapper`` is the optional Bambu config bytes (native signature retained).
    This is a strict reader for our supported core subset, not lib3mf parity.
    """
    content = ET.Element(f"{{{CT}}}Types")
    ET.SubElement(content, f"{{{CT}}}Default", Extension="rels", ContentType="application/vnd.openxmlformats-package.relationships+xml")
    ET.SubElement(content, f"{{{CT}}}Override", PartName="/3D/3dmodel.model", ContentType=MODEL_TYPE)
    rels = ET.Element(f"{{{REL}}}Relationships")
    ET.SubElement(rels, f"{{{REL}}}Relationship", Id="model", Target="/3D/3dmodel.model", Type=MODEL_REL)
    if wrapper is not None:
        ET.SubElement(content, f"{{{CT}}}Override", PartName="/Metadata/model_settings.config", ContentType="application/xml")
        ET.SubElement(rels, f"{{{REL}}}Relationship", Id="settings", Target="/Metadata/model_settings.config", Type=BAMBU_PACKAGE_REL)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xml(content))
        archive.writestr("_rels/.rels", _xml(rels))
        archive.writestr("3D/3dmodel.model", _xml(model))
        if wrapper is not None:
            archive.writestr("Metadata/model_settings.config", wrapper)
    raw = buffer.getvalue()
    _read(raw)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)


def export_bambu_compatible_3mf(scene, output):
    root, resources, build = _new_model()
    # Scene graph instances/transforms are real geometry, not just dictionary
    # entries. Bake each instance so sampler translations survive export.
    nodes = list(scene.graph.nodes_geometry)
    names = unique_object_names(scene.graph[node][1] for node in nodes)
    for node, name in zip(nodes, names):
        transform, key = scene.graph[node]
        mesh = scene.geometry[key].copy()
        mesh.apply_transform(transform)
        label_mesh_report(name, mesh)
        _item(build, _mesh(resources, name, mesh))
    if not nodes:
        raise ValueError("3MF needs at least one mesh")
    _stamp_identity(root, Path(output).stem)
    _strict_write(root, None, output)


def export_assembly_3mf(parts, output, filaments=None):
    parts = list(parts)
    if not parts:
        raise ValueError("an assembly needs at least one part")
    names = unique_object_names(name for name, _ in parts)
    root, resources, build = _new_model()
    ids = []
    for name, (_, mesh) in zip(names, parts):
        label_mesh_report(name, mesh)
        ids.append(_mesh(resources, name, mesh))
    title = Path(output).stem or names[0]
    parent = _components(resources, title, ids)
    _item(build, parent)
    slots = filaments or {}
    config = _model_settings_config(title, parent, [(i, name, slots.get(name, 1)) for i, name in zip(ids, names)])
    _stamp_identity(root, title)
    _strict_write(root, config, output)
    return names


def export_text_body_3mf(body_mesh, texts, output, body_name="box",
                         part_filament=TEXT_PART_FILAMENT, *, accent_color=None, accent_top=None):
    texts = list(texts)
    mesh_report(body_name, body_mesh)
    names = unique_object_names((name for name, _ in texts), taken=(body_name,))
    for name, (_, mesh) in zip(names, texts):
        label_mesh_report(name, mesh)
        if intersection_volume(body_mesh, mesh) > 0.01:
            raise RuntimeError(f"the text '{name}' overlaps the body instead of sitting in its own pocket")
    parts, slots = ([(body_name, body_mesh)], {})
    if accent_color is not None:
        parts, slots = accent_body_parts(body_name, body_mesh, accent_color, accent_top, taken=names)
    slots.update({name: part_filament for name in names})
    export_assembly_3mf(parts + list(zip(names, (mesh for _, mesh in texts))), output, slots)
    return names


def export_object_groups_3mf(objects, output, filaments=None):
    groups = [(name, list(parts)) for name, parts in objects]
    if not groups or any(not parts for _, parts in groups):
        raise ValueError("each 3MF print object needs at least one part")
    names = unique_object_names(name for name, _ in groups)
    part_names = iter(unique_object_names(name for _, parts in groups for name, _ in parts))
    root, resources, build = _new_model()
    configs = []
    slots = filaments or {}
    for name, (_, parts) in zip(names, groups):
        children = []
        for _, mesh in parts:
            part_name = next(part_names)
            label_mesh_report(part_name, mesh)
            child = _mesh(resources, name if len(parts) == 1 else part_name, mesh)
            children.append((child, part_name, slots.get(part_name, 1)))
        parent = children[0][0] if len(parts) == 1 else _components(resources, name, [c[0] for c in children])
        _item(build, parent)
        configs.append((parent, name, [] if len(parts) == 1 else children))
    _stamp_identity(root, Path(output).stem or names[0])
    _strict_write(root, _object_groups_model_settings_config(configs), output)
    return names


def _parse_xml(raw):
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("3MF XML declarations are not supported")
    return ET.fromstring(raw)


def _transform(node):
    values = np.asarray([float(v) for v in node.get("transform", IDENTITY).split()])
    if len(values) != 12 or not np.isfinite(values).all():
        raise ValueError("Invalid 3MF transform")
    matrix = np.eye(4)
    matrix[:3, :] = values.reshape(4, 3).T
    if abs(np.linalg.det(matrix[:3, :3])) < 1e-12:
        raise ValueError("Singular 3MF transform")
    return matrix


def _read(raw):
    """Validate OPC, references, mesh arrays, transforms and Bambu sidecar.

    Read-back topology uses the original multipart mesh validator; callers
    additionally enforce single-component rules where the part requires it.
    Unknown structures fail closed rather than being silently dropped.
    """
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        entries = archive.namelist()
        required = {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        if len(set(entries)) != len(entries) or not required.issubset(entries):
            raise ValueError("3MF has duplicate or missing OPC members")
        if set(entries) - required - {"Metadata/model_settings.config"}:
            raise ValueError("Unsupported ordinary-export 3MF members")
        if archive.testzip() is not None:
            raise ValueError("3MF ZIP integrity failure")
        types = _parse_xml(archive.read("[Content_Types].xml"))
        rels = _parse_xml(archive.read("_rels/.rels"))
        root = _parse_xml(archive.read("3D/3dmodel.model"))
        if types.tag != f"{{{CT}}}Types" or rels.tag != f"{{{REL}}}Relationships":
            raise ValueError("Invalid OPC namespace")
        overrides = {n.get("PartName"): n.get("ContentType") for n in types.findall(f"{{{CT}}}Override")}
        if len(overrides) != len(types.findall(f"{{{CT}}}Override")):
            raise ValueError("Duplicate OPC content types")
        if overrides.get("/3D/3dmodel.model") != MODEL_TYPE:
            raise ValueError("3MF model content type missing")
        relationships = list(rels)
        expected_targets = {MODEL_REL: "/3D/3dmodel.model"}
        if "Metadata/model_settings.config" in entries:
            expected_targets[BAMBU_PACKAGE_REL] = "/Metadata/model_settings.config"
        if (len(relationships) != len(expected_targets) or
                any(n.tag != f"{{{REL}}}Relationship" or
                    expected_targets.get(n.get("Type")) != n.get("Target") or
                    n.get("TargetMode", "Internal") != "Internal" for n in relationships)):
            raise ValueError("Unsupported OPC relationship")
        if len({n.get("Id") for n in relationships}) != len(relationships):
            raise ValueError("Duplicate OPC relationship IDs")
        if not any(n.get("Type") == MODEL_REL and n.get("Target") == "/3D/3dmodel.model" and n.get("TargetMode", "Internal") == "Internal" for n in relationships):
            raise ValueError("3MF model relationship missing")
        config = None
        if "Metadata/model_settings.config" in entries:
            config = _parse_xml(archive.read("Metadata/model_settings.config"))
            if overrides.get("/Metadata/model_settings.config") != "application/xml" or not any(n.get("Type") == BAMBU_PACKAGE_REL and n.get("Target") == "/Metadata/model_settings.config" for n in relationships):
                raise ValueError("3MF Bambu attachment declaration missing")
    if root.tag != _q("model") or root.get("unit") != "millimeter" or root.get("requiredextensions"):
        raise ValueError("Unsupported 3MF model namespace, units or extensions")
    if any(n.tag not in {_q("metadata"), _q("resources"), _q("build")} for n in root):
        raise ValueError("Unsupported 3MF model structure")
    metadata = {n.get("name"): n.text for n in root.findall(_q("metadata"))}
    if metadata.get("Application") != "Wavefinity" or not metadata.get("Title"):
        raise ValueError("3MF identity metadata missing")
    if len(root.findall(_q("resources"))) != 1 or len(root.findall(_q("build"))) != 1:
        raise ValueError("3MF needs one resources and build section")
    objects, meshes, components = {}, {}, {}
    for obj in root.find(_q("resources")):
        object_id = int(obj.get("id", "0"))
        if obj.tag != _q("object") or object_id <= 0 or object_id in objects or obj.get("type") != "model":
            raise ValueError("Invalid or duplicate 3MF object")
        objects[object_id] = obj
        if set(obj.attrib) - {"id", "type", "name"}:
            raise ValueError("Unsupported 3MF object attributes")
        if len(obj) != 1:
            raise ValueError("3MF object needs exactly one mesh or components section")
        node = obj[0]
        if node.tag == _q("mesh"):
            if [n.tag for n in node] != [_q("vertices"), _q("triangles")]:
                raise ValueError("Invalid 3MF mesh structure")
            vertices = np.asarray([[float(v.attrib[a]) for a in ("x", "y", "z")] for v in node[0]], dtype=float)
            faces = np.asarray([[int(f.attrib[a]) for a in ("v1", "v2", "v3")] for f in node[1]], dtype=np.int64)
            if (vertices.ndim != 2 or vertices.shape[1] != 3 or not len(vertices)
                    or not np.isfinite(vertices).all() or faces.ndim != 2 or faces.shape[1] != 3
                    or not len(faces) or faces.min() < 0 or faces.max() >= len(vertices)
                    or any(len(set(face)) != 3 for face in faces)):
                raise ValueError("Invalid 3MF vertices or triangle indices")
            if any(v.tag != _q("vertex") for v in node[0]) or any(f.tag != _q("triangle") for f in node[1]):
                raise ValueError("Unsupported 3MF mesh data")
            if any(set(v.attrib) != {"x", "y", "z"} for v in node[0]) or any(set(f.attrib) != {"v1", "v2", "v3"} for f in node[1]):
                raise ValueError("Unsupported 3MF mesh attributes")
            meshes[object_id] = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        elif node.tag == _q("components") and len(node):
            if any(c.tag != _q("component") or set(c.attrib) - {"objectid", "transform"} for c in node):
                raise ValueError("Unsupported 3MF component")
            components[object_id] = [(int(c.attrib["objectid"]), _transform(c)) for c in node]
        else:
            raise ValueError("Unsupported 3MF object content")
    items = []
    for node in root.find(_q("build")):
        if (node.tag != _q("item") or node.get("printable", "1") != "1"
                or set(node.attrib) - {"objectid", "transform", "printable"}):
            raise ValueError("Unsupported 3MF build item")
        items.append((int(node.attrib["objectid"]), _transform(node)))
    if not items:
        raise ValueError("3MF has no build items")
    visited = set()
    bounds = []

    def visit(key, transform, parents):
        if key not in objects or key in parents:
            raise ValueError("Dangling or cyclic 3MF object reference")
        visited.add(key)
        if key in meshes:
            mesh = meshes[key].copy()
            mesh.apply_transform(transform)
            if not np.isfinite(mesh.bounds).all():
                raise ValueError("Non-finite transformed 3MF bounds")
            bounds.append(mesh.bounds)
        else:
            for child, move in components[key]:
                visit(child, transform @ move, parents | {key})

    for key, transform in items:
        visit(key, transform, set())
    if visited != set(objects):
        raise ValueError("3MF has unreferenced objects")
    names = [objects[key].get("name", "") for key in meshes]
    if any(not name for name in names) or len(set(names)) != len(names):
        raise ValueError("3MF mesh names are empty or duplicated")
    for key, mesh in meshes.items():
        label_mesh_report(objects[key].get("name"), mesh)
    if config is not None:
        _validate_config(config, objects, components, items)
    return objects, meshes, components, items, np.asarray(bounds), config


def _validate_config(config, objects, components, items):
    if config.tag != "config":
        raise ValueError("Invalid Bambu settings root")
    build_ids = [key for key, _ in items]
    config_ids = [int(n.attrib["id"]) for n in config.findall("object")]
    if config_ids != build_ids:
        raise ValueError("Bambu object IDs do not match build items")
    for obj in config.findall("object"):
        key = int(obj.attrib["id"])
        meta = {m.get("key"): m.get("value") for m in obj.findall("metadata")}
        if meta.get("name") != objects[key].get("name") or meta.get("extruder") != "1":
            raise ValueError("Bambu object name or filament changed")
        expected = [child for child, _ in components.get(key, [])]
        parts = obj.findall("part")
        if [int(p.attrib["id"]) for p in parts] != expected:
            raise ValueError("Bambu part IDs do not match component resources")
        for part in parts:
            meta = {m.get("key"): m.get("value") for m in part.findall("metadata")}
            slot = int(meta.get("extruder", "1"))
            if (part.get("subtype") != "normal_part" or slot < 1
                    or meta.get("name") != objects[int(part.attrib["id"])].get("name")
                    or meta.get("matrix") != "1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"):
                raise ValueError("Invalid Bambu part name, matrix or filament")


def scene_for_fit(path):
    """Read every actual build instance for the existing printer fit guard."""
    objects, meshes, components, items, _, _ = _read(Path(path).read_bytes())
    scene = trimesh.Scene()
    scene.units = "mm"

    def add(key, transform):
        if key in meshes:
            mesh = meshes[key].copy()
            mesh.apply_transform(transform)
            name = unique_object_names([objects[key].get("name")], taken=scene.geometry)[0]
            scene.add_geometry(mesh, node_name=name, geom_name=name)
        else:
            for child, move in components[key]:
                add(child, transform @ move)

    for key, transform in items:
        add(key, transform)
    return scene


def validate_3mf(path, expected_objects, multipart=()):
    raw = Path(path).read_bytes()
    objects, meshes, components, items, bounds, config = _read(raw)
    assembly = bool(multipart)
    if (len(meshes) != expected_objects or len(objects) != expected_objects + int(assembly)
            or len(items) != (1 if assembly else expected_objects)
            or len(components) != int(assembly)):
        raise RuntimeError("3MF object/build counts do not match the generated output")
    if assembly:
        parent = items[0][0]
        if parent not in components or [key for key, _ in components[parent]] != list(meshes) or config is None:
            raise RuntimeError("3MF assembly lost its parts or Bambu settings")
    names = []
    for key, mesh in meshes.items():
        name = objects[key].get("name")
        (label_mesh_report if name in multipart else mesh_report)(name, mesh)
        names.append(name)
    result = {"objects": expected_objects, "names": sorted(names),
              "bounds_mm": np.round([bounds[:, 0].min(axis=0), bounds[:, 1].max(axis=0)], 3).tolist(),
              "warnings": 0, "sha256": hashlib.sha256(raw).hexdigest().upper()}
    if assembly:
        result["filaments"] = assigned_filaments(path)
    return result


def validate_object_groups_3mf(path, objects, filaments=None):
    groups = [(name, list(parts)) for name, parts in objects]
    if not groups or any(not parts for _, parts in groups):
        raise ValueError("each expected 3MF print object needs at least one part")
    raw = Path(path).read_bytes()
    resources, meshes, components, items, _, config = _read(raw)
    if (len(meshes) != sum(len(parts) for _, parts in groups)
            or len(components) != sum(len(parts) > 1 for _, parts in groups)
            or len(items) != len(groups) or config is None):
        raise RuntimeError("3MF object group counts or settings changed")
    slots = assigned_filaments(path)
    for (name, parts), (key, _) in zip(groups, items):
        if resources[key].get("name") != name:
            raise RuntimeError("3MF print object name changed")
        if len(parts) == 1:
            if key not in meshes:
                raise RuntimeError("3MF singleton is not a direct mesh build item")
            children = [key]
        else:
            children = [child for child, _ in components.get(key, [])]
            if [resources[c].get("name") for c in children] != [n for n, _ in parts]:
                raise RuntimeError("3MF group has the wrong child meshes")
        for child, (part_name, expected) in zip(children, parts):
            actual = meshes[child]
            label_mesh_report(resources[child].get("name"), actual)
            if not np.array_equal(actual.faces, expected.faces) or not np.array_equal(actual.vertices, expected.vertices):
                raise RuntimeError("3MF group mesh geometry changed")
            if len(parts) > 1 and slots.get(part_name) != (filaments or {}).get(part_name, 1):
                raise RuntimeError("3MF part has the wrong filament slot")
    return {"objects": len(meshes), "build_items": len(items), "components": len(components),
            "names": sorted(resources[k].get("name") for k in meshes),
            "filaments": {**{name: 1 for name, _ in groups}, **slots},
            "warnings": 0, "sha256": hashlib.sha256(raw).hexdigest().upper()}
