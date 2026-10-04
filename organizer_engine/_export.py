"""Wavefinity engine 3MF export and validation, and the fit sampler."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree
import lib3mf
import numpy as np
import trimesh
from organizer_geometry import translated

from ._specs import (
    WAVE_LENGTH,
    WAVE_AMPLITUDE,
    GRID_PITCH,
    BASE_UNIT,
    DEFAULT_WALL,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_SIDE_LENGTH,
    BoxSpec,
    ConnectorSpec,
)
from ._boxes import make_box, make_side_connector, connector_for_print
from ._fit import mesh_report, intersection_volume, validate_side_fit


# --------------------------------------------------------------------------- #
# export
# --------------------------------------------------------------------------- #

# The relationship type Bambu Studio / OrcaSlicer use to find the part-level
# settings sidecar inside a 3MF. Attaching the file under this type is what
# lets the slicer pick up per-part names and filament assignments.
BAMBU_PACKAGE_REL = "http://schemas.bambulab.com/package/2021"
TEXT_PART_FILAMENT = 2   # lettering opens pre-assigned to this filament slot


def _xml_attr(value: str) -> str:
    """Escape a string for use inside an XML attribute."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _stamp_identity(model, title: str = "") -> None:
    """Name the file so a slicer shows something better than 'Unsaved'.

    No print profile is embedded, so an opened file still uses the slicer's
    current printer and process - this only labels it.
    """
    group = model.GetMetaDataGroup()
    seen = set()
    for index in range(group.GetMetaDataCount()):
        try:
            seen.add(group.GetMetaData(index).GetName())
        except Exception:  # pragma: no cover - defensive against binding quirks
            pass
    if "Application" not in seen:
        group.AddMetaData("", "Application", "Wavefinity", "xs:string", False)
    if title and "Title" not in seen:
        group.AddMetaData("", "Title", title, "xs:string", False)


def _strict_write(model, wrapper, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = model.QueryWriter("3mf")
    writer.SetStrictModeActive(True)
    writer.WriteToFile(str(output.resolve()))
    if writer.GetWarningCount() != 0:
        raise RuntimeError(f"strict 3MF writer reported {writer.GetWarningCount()} warnings")


def export_bambu_compatible_3mf(scene: trimesh.Scene, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    generic = scene.export(file_type="3mf")
    if not isinstance(generic, bytes):
        raise RuntimeError("intermediate 3MF export did not return binary data")
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(False)
    reader.ReadFromBuffer(generic)
    _stamp_identity(model, output.stem)
    _strict_write(model, wrapper, output)


def _model_settings_config(
    title: str, object_id: int, parts: Iterable[tuple[int, str, int]]
) -> bytes:
    """Bambu ``model_settings.config``: the assembly's name plus, per part, its
    name and which filament slot it opens on.

    ``parts`` is ``(part resource id, part name, filament slot)``. A slot of 1
    is the default and is left off the part so only the deliberate second-colour
    assignment is written.
    """
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<config>",
        f'  <object id="{object_id}">',
        f'    <metadata key="name" value="{_xml_attr(title)}"/>',
        '    <metadata key="extruder" value="1"/>',
    ]
    for part_id, name, filament in parts:
        lines.append(f'    <part id="{part_id}" subtype="normal_part">')
        lines.append(f'      <metadata key="name" value="{_xml_attr(name)}"/>')
        lines.append(
            '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
        )
        if filament != 1:
            lines.append(f'      <metadata key="extruder" value="{filament}"/>')
        lines.append("    </part>")
    lines += ["  </object>", "</config>", ""]
    return "\n".join(lines).encode("utf-8")


def _object_groups_model_settings_config(
    objects: Iterable[tuple[int, str, Iterable[tuple[int, str, int]]]],
) -> bytes:
    """Bambu settings for several independently placeable top-level objects.

    A singleton has no ``part`` entries.  A registered multi-part object lists
    its child resources so Bambu keeps them together and honours their slots.
    """
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<config>"]
    for object_id, name, parts in objects:
        parts = list(parts)
        lines += [
            f'  <object id="{object_id}">',
            f'    <metadata key="name" value="{_xml_attr(name)}"/>',
            '    <metadata key="extruder" value="1"/>',
        ]
        for part_id, part_name, filament in parts:
            lines.append(f'    <part id="{part_id}" subtype="normal_part">')
            lines.append(
                f'      <metadata key="name" value="{_xml_attr(part_name)}"/>'
            )
            lines.append(
                '      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>'
            )
            if filament != 1:
                lines.append(f'      <metadata key="extruder" value="{filament}"/>')
            lines.append("    </part>")
        lines.append("  </object>")
    lines += ["</config>", ""]
    return "\n".join(lines).encode("utf-8")


def assigned_filaments(path: Path) -> dict[str, int]:
    """``{part name: filament slot}`` read back from a 3MF's model_settings.config.

    Empty when the file carries no such sidecar (a plain single-mesh export).
    """
    with zipfile.ZipFile(path) as archive:
        try:
            raw = archive.read("Metadata/model_settings.config").decode("utf-8")
        except KeyError:
            return {}
    root = ElementTree.fromstring(raw)
    out: dict[str, int] = {}
    for part in root.iter("part"):
        name = None
        slot = 1
        for meta in part.findall("metadata"):
            if meta.get("key") == "name":
                name = meta.get("value")
            elif meta.get("key") == "extruder":
                slot = int(meta.get("value", "1"))
        if name is not None:
            out[name] = slot
    return out


def label_mesh_report(name: str, mesh: trimesh.Trimesh) -> dict[str, object]:
    """Like ``mesh_report`` but a label is legitimately several solids - one per
    disconnected letter - so the single-component rule does not apply."""
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
        (report["watertight"], report["winding_consistent"], report["positive_volume"])
    ):
        raise RuntimeError(f"{name} failed mesh validation: {report}")
    return report


def unique_object_names(names: Iterable[str], taken: Iterable[str] = ()) -> list[str]:
    """``names`` made unique for a 3MF scene, in order, keeping ``taken`` clear.

    Two text parts reading the same thing are perfectly reasonable - "M3" over
    each of two bore clusters - but a 3MF object name has to be unique or the
    second silently replaces the first in the scene.
    """
    used = set(taken)
    out: list[str] = []
    for name in names:
        base = name.strip() or "text"
        candidate, suffix = base, 2
        while candidate in used:
            candidate, suffix = f"{base} {suffix}", suffix + 1
        used.add(candidate)
        out.append(candidate)
    return out


def export_text_body_3mf(
    body_mesh: trimesh.Trimesh,
    texts: Iterable[tuple[str, trimesh.Trimesh]],
    output: Path,
    body_name: str = "box",
    part_filament: int = TEXT_PART_FILAMENT,
) -> list[str]:
    """Write a body plus any number of text solids as one 3MF **assembly**.

    Every mesh becomes a named part of a single object, so the file opens in
    Bambu Studio / OrcaSlicer directly as one object with parts - no "load as
    a single object with multiple parts?" prompt to answer. A
    ``model_settings.config`` sidecar carries the part names and opens the
    lettering on filament slot ``part_filament`` while the body stays on 1, so
    the two-colour intent is already set. No print profile is embedded: an
    opened file still uses the slicer's current printer and process.

    A recessed text has already been subtracted from ``body_mesh``, so the two
    share faces and nothing else; a raised one stands on the surface and
    touches it the same way. Returns the part names actually written.
    """
    texts = list(texts)
    mesh_report(body_name, body_mesh)
    names = unique_object_names((name for name, _ in texts), taken=(body_name,))

    scene = trimesh.Scene()
    scene.units = "mm"
    scene.add_geometry(body_mesh, node_name=body_name, geom_name=body_name)
    for name, (_raw, mesh) in zip(names, texts):
        label_mesh_report(name, mesh)
        if intersection_volume(body_mesh, mesh) > 0.01:
            raise RuntimeError(
                f"the text '{name}' overlaps the body instead of sitting in "
                "its own pocket"
            )
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    generic = scene.export(file_type="3mf")
    if not isinstance(generic, bytes):
        raise RuntimeError("intermediate 3MF export did not return binary data")
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(False)
    reader.ReadFromBuffer(generic)

    by_name: dict[str, object] = {}
    iterator = model.GetMeshObjects()
    while iterator.MoveNext():
        obj = iterator.GetCurrentMeshObject()
        by_name[obj.GetName()] = obj
    try:
        ordered = [by_name[body_name]] + [by_name[name] for name in names]
    except KeyError as missing:  # pragma: no cover - trimesh contract change
        raise RuntimeError(f"3MF export dropped object {missing}") from None

    stale = []
    build_items = model.GetBuildItems()
    while build_items.MoveNext():
        stale.append(build_items.GetCurrent())
    for item in stale:
        model.RemoveBuildItem(item)

    title = output.stem or body_name
    assembly = model.AddComponentsObject()
    assembly.SetName(title)
    identity = wrapper.GetIdentityTransform()
    for obj in ordered:
        assembly.AddComponent(obj, identity)
    model.AddBuildItem(assembly, identity)

    parts = [(ordered[0].GetResourceID(), body_name, 1)]
    for obj, name in zip(ordered[1:], names):
        parts.append((obj.GetResourceID(), name, part_filament))
    config = _model_settings_config(title, assembly.GetResourceID(), parts)
    attachment = model.AddAttachment(
        "/Metadata/model_settings.config", BAMBU_PACKAGE_REL
    )
    attachment.ReadFromBuffer(bytearray(config))

    _stamp_identity(model, title)
    _strict_write(model, wrapper, output)
    return names


def export_labelled_box(
    box_mesh: trimesh.Trimesh,
    label_mesh: trimesh.Trimesh,
    output: Path,
    box_name: str = "box",
    label_name: str = "label",
) -> None:
    """One body and one label - the rim-ledge and plain ``box --label`` case."""
    export_text_body_3mf(box_mesh, [(label_name, label_mesh)], output, box_name)


def export_assembly_3mf(
    parts: Iterable[tuple[str, trimesh.Trimesh]],
    output: Path,
    filaments: dict[str, int] | None = None,
) -> list[str]:
    """Write several distinct solids as one 3MF **assembly**.

    Unlike ``export_text_body_3mf`` the parts here are independent printable
    objects (a B4B body, its lid, its latches), each already transformed into
    its own print orientation.  They become named parts of a single grouping
    object with one build item, so the file opens directly without the
    "load as a single object with multiple parts?" prompt.  ``filaments`` maps
    a part name to a slot for any part that should not open on slot 1.

    Returns the unique part names written, in order.
    """
    parts = list(parts)
    if not parts:
        raise ValueError("an assembly needs at least one part")
    names = unique_object_names(name for name, _ in parts)
    for name, mesh in zip(names, (mesh for _, mesh in parts)):
        label_mesh_report(name, mesh)

    scene = trimesh.Scene()
    scene.units = "mm"
    for name, (_raw, mesh) in zip(names, parts):
        scene.add_geometry(mesh, node_name=name, geom_name=name)

    generic = scene.export(file_type="3mf")
    if not isinstance(generic, bytes):
        raise RuntimeError("intermediate 3MF export did not return binary data")
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(False)
    reader.ReadFromBuffer(generic)

    by_name: dict[str, object] = {}
    iterator = model.GetMeshObjects()
    while iterator.MoveNext():
        obj = iterator.GetCurrentMeshObject()
        by_name[obj.GetName()] = obj
    try:
        ordered = [by_name[name] for name in names]
    except KeyError as missing:  # pragma: no cover - trimesh contract change
        raise RuntimeError(f"3MF export dropped object {missing}") from None

    stale = []
    build_items = model.GetBuildItems()
    while build_items.MoveNext():
        stale.append(build_items.GetCurrent())
    for item in stale:
        model.RemoveBuildItem(item)

    title = output.stem or names[0]
    assembly = model.AddComponentsObject()
    assembly.SetName(title)
    identity = wrapper.GetIdentityTransform()
    for obj in ordered:
        assembly.AddComponent(obj, identity)
    model.AddBuildItem(assembly, identity)

    slots = filaments or {}
    config = _model_settings_config(
        title,
        assembly.GetResourceID(),
        [(obj.GetResourceID(), name, slots.get(name, 1))
         for obj, name in zip(ordered, names)],
    )
    attachment = model.AddAttachment(
        "/Metadata/model_settings.config", BAMBU_PACKAGE_REL
    )
    attachment.ReadFromBuffer(bytearray(config))

    _stamp_identity(model, title)
    _strict_write(model, wrapper, output)
    return names


def export_object_groups_3mf(
    objects: Iterable[tuple[str, Iterable[tuple[str, trimesh.Trimesh]]]],
    output: Path,
    filaments: dict[str, int] | None = None,
) -> list[str]:
    """Write mixed independent and registered multi-part 3MF print objects.

    A one-part group becomes its own top-level build item.  A multi-part group
    becomes one ComponentsObject build item, preserving only the deliberately
    registered meshes inside it.  Existing assembly exports retain their
    single-object behaviour through :func:`export_assembly_3mf`.
    """
    raw_objects = [(name, list(parts)) for name, parts in objects]
    if not raw_objects or any(not parts for _name, parts in raw_objects):
        raise ValueError("each 3MF print object needs at least one part")

    object_names = unique_object_names(name for name, _parts in raw_objects)
    part_names = unique_object_names(
        part_name for _object_name, parts in raw_objects for part_name, _mesh in parts
    )
    named_objects: list[tuple[str, list[tuple[str, trimesh.Trimesh]]]] = []
    name_iter = iter(part_names)
    for object_name, (_raw_name, parts) in zip(object_names, raw_objects):
        named_parts = [(next(name_iter), mesh) for _part_name, mesh in parts]
        for part_name, mesh in named_parts:
            label_mesh_report(part_name, mesh)
        named_objects.append((object_name, named_parts))

    scene = trimesh.Scene()
    scene.units = "mm"
    for _object_name, parts in named_objects:
        for part_name, mesh in parts:
            scene.add_geometry(mesh, node_name=part_name, geom_name=part_name)
    generic = scene.export(file_type="3mf")
    if not isinstance(generic, bytes):
        raise RuntimeError("intermediate 3MF export did not return binary data")
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(False)
    reader.ReadFromBuffer(generic)

    by_name: dict[str, object] = {}
    iterator = model.GetMeshObjects()
    while iterator.MoveNext():
        obj = iterator.GetCurrentMeshObject()
        by_name[obj.GetName()] = obj
    try:
        resolved = [
            (object_name, [(part_name, by_name[part_name]) for part_name, _mesh in parts])
            for object_name, parts in named_objects
        ]
    except KeyError as missing:  # pragma: no cover - trimesh contract change
        raise RuntimeError(f"3MF export dropped object {missing}") from None

    stale = []
    build_items = model.GetBuildItems()
    while build_items.MoveNext():
        stale.append(build_items.GetCurrent())
    for item in stale:
        model.RemoveBuildItem(item)

    slots = filaments or {}
    identity = wrapper.GetIdentityTransform()
    config_objects: list[tuple[int, str, list[tuple[int, str, int]]]] = []
    for object_name, parts in resolved:
        if len(parts) == 1:
            part_name, mesh_object = parts[0]
            mesh_object.SetName(object_name)
            model.AddBuildItem(mesh_object, identity)
            config_objects.append((mesh_object.GetResourceID(), object_name, []))
            continue
        parent = model.AddComponentsObject()
        parent.SetName(object_name)
        for _part_name, mesh_object in parts:
            parent.AddComponent(mesh_object, identity)
        model.AddBuildItem(parent, identity)
        config_objects.append((
            parent.GetResourceID(),
            object_name,
            [
                (mesh_object.GetResourceID(), part_name, slots.get(part_name, 1))
                for part_name, mesh_object in parts
            ],
        ))

    config = _object_groups_model_settings_config(config_objects)
    attachment = model.AddAttachment(
        "/Metadata/model_settings.config", BAMBU_PACKAGE_REL
    )
    attachment.ReadFromBuffer(bytearray(config))
    title = output.stem or object_names[0]
    _stamp_identity(model, title)
    _strict_write(model, wrapper, output)
    return object_names


def export_mesh(mesh: trimesh.Trimesh, output: Path, name: str) -> None:
    mesh_report(name, mesh)
    suffix = output.suffix.lower()
    output.parent.mkdir(parents=True, exist_ok=True)
    if suffix == ".stl":
        mesh.export(output, file_type="stl")
        return
    if suffix == ".3mf":
        scene = trimesh.Scene()
        scene.units = "mm"
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        export_bambu_compatible_3mf(scene, output)
        return
    raise ValueError("output filename must end in .stl or .3mf")


def validate_3mf(
    path: Path,
    expected_objects: int,
    multipart: tuple[str, ...] = (),
) -> dict[str, object]:
    """Check a written 3MF is strict, watertight and shaped as expected.

    ``expected_objects`` is the mesh count, as a slicer sees it. Names listed
    in ``multipart`` may be several disconnected solids - a label is one per
    letter - so they get the relaxed mesh check.

    A non-empty ``multipart`` also means the file is an **assembly**: every
    mesh is a part of one grouping object with a single build item, so the
    strict model then holds ``expected_objects + 1`` objects and 1 build item.
    The returned ``filaments`` maps each part name to the slot it opens on.
    """
    assembly = bool(multipart)
    scene = trimesh.load(path, force="scene")
    if len(scene.geometry) != expected_objects:
        raise RuntimeError(
            f"3MF contains {len(scene.geometry)} objects instead of {expected_objects}"
        )
    for name, geometry in scene.geometry.items():
        if name in multipart:
            label_mesh_report(name, geometry)
        else:
            mesh_report(name, geometry)
    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(path.resolve()))
    if reader.GetWarningCount() != 0:
        raise RuntimeError(f"strict 3MF reader reported {reader.GetWarningCount()} warnings")
    want_objects = expected_objects + 1 if assembly else expected_objects
    want_items = 1 if assembly else expected_objects
    if model.GetObjects().Count() != want_objects:
        raise RuntimeError(
            f"strict 3MF has {model.GetObjects().Count()} objects, expected {want_objects}"
        )
    if model.GetBuildItems().Count() != want_items:
        raise RuntimeError(
            f"strict 3MF has {model.GetBuildItems().Count()} build items, expected {want_items}"
        )
    result: dict[str, object] = {
        "objects": expected_objects,
        "names": sorted(scene.geometry.keys()),
        "bounds_mm": np.round(scene.bounds, 3).tolist(),
        "warnings": 0,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
    }
    if assembly:
        result["filaments"] = assigned_filaments(path)
    return result


def validate_object_groups_3mf(
    path: Path,
    objects: Iterable[tuple[str, Iterable[tuple[str, trimesh.Trimesh]]]],
    filaments: dict[str, int] | None = None,
) -> dict[str, object]:
    """Validate mixed 3MF object groups without relaxing normal assemblies.

    Singleton groups must be direct mesh build items.  Only multi-part groups
    may use ComponentsObjects, and each must contain exactly its declared mesh
    resources.  ``filaments`` names deliberate non-default part slots.
    """
    groups = [(name, list(parts)) for name, parts in objects]
    if not groups or any(not parts for _name, parts in groups):
        raise ValueError("each expected 3MF print object needs at least one part")
    expected_leaves = sum(len(parts) for _name, parts in groups)
    expected_components = sum(len(parts) > 1 for _name, parts in groups)

    wrapper = lib3mf.Wrapper()
    model = wrapper.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    reader.ReadFromFile(str(path.resolve()))
    if reader.GetWarningCount() != 0:
        raise RuntimeError(f"strict 3MF reader reported {reader.GetWarningCount()} warnings")
    if model.GetBuildItems().Count() != len(groups):
        raise RuntimeError(
            f"strict 3MF has {model.GetBuildItems().Count()} build items, expected {len(groups)}"
        )

    with zipfile.ZipFile(path) as archive:
        model_file = next(
            (name for name in archive.namelist() if name.lower().endswith(".model")),
            None,
        )
        if model_file is None:
            raise RuntimeError("3MF contains no model resource")
        root = ElementTree.fromstring(archive.read(model_file))
        config = ElementTree.fromstring(archive.read("Metadata/model_settings.config"))

    def local(node) -> str:
        return node.tag.rsplit("}", 1)[-1]

    resources = next((node for node in root if local(node) == "resources"), None)
    build = next((node for node in root if local(node) == "build"), None)
    if resources is None or build is None:
        raise RuntimeError("3MF model is missing resources or build items")
    resource_objects = {
        node.get("id", ""): node for node in resources if local(node) == "object"
    }
    mesh_ids = {
        object_id for object_id, node in resource_objects.items()
        if any(local(child) == "mesh" for child in node)
    }
    component_ids = {
        object_id: [child.get("objectid", "") for child in node.iter() if local(child) == "component"]
        for object_id, node in resource_objects.items()
        if any(local(child) == "components" for child in node)
    }
    build_ids = [node.get("objectid", "") for node in build if local(node) == "item"]
    if len(mesh_ids) != expected_leaves:
        raise RuntimeError(f"3MF has {len(mesh_ids)} leaf meshes, expected {expected_leaves}")
    if len(component_ids) != expected_components:
        raise RuntimeError(
            f"3MF has {len(component_ids)} ComponentsObjects, expected {expected_components}"
        )

    mesh_names = {
        node.get("name", ""): object_id
        for object_id, node in resource_objects.items()
        if object_id in mesh_ids
    }
    expected_slots = filaments or {}
    config_slots: dict[str, int] = {}
    for config_object in config.iter():
        if local(config_object) != "object":
            continue
        object_name = ""
        object_slot = 1
        for meta in config_object:
            if local(meta) != "metadata":
                continue
            if meta.get("key") == "name":
                object_name = meta.get("value", "")
            elif meta.get("key") == "extruder":
                object_slot = int(meta.get("value", "1"))
        if object_name:
            config_slots[object_name] = object_slot
        for part in config_object:
            if local(part) != "part":
                continue
            part_name, part_slot = "", object_slot
            for meta in part:
                if local(meta) != "metadata":
                    continue
                if meta.get("key") == "name":
                    part_name = meta.get("value", "")
                elif meta.get("key") == "extruder":
                    part_slot = int(meta.get("value", "1"))
            if part_name:
                config_slots[part_name] = part_slot

    for object_name, parts in groups:
        if len(parts) == 1:
            resource_id = mesh_names.get(object_name, "")
            if resource_id not in mesh_ids or resource_id not in build_ids:
                raise RuntimeError(f"3MF singleton '{object_name}' is not a direct mesh build item")
            if config_slots.get(object_name) != 1:
                raise RuntimeError(f"3MF singleton '{object_name}' is not on filament 1")
            continue
        resource_id = next(
            (
                object_id for object_id, node in resource_objects.items()
                if object_id in component_ids and node.get("name") == object_name
            ),
            "",
        )
        child_ids = [mesh_names.get(part_name, "") for part_name, _mesh in parts]
        if resource_id not in component_ids or resource_id not in build_ids:
            raise RuntimeError(f"3MF multipart '{object_name}' is not a ComponentsObject build item")
        if component_ids[resource_id] != child_ids:
            raise RuntimeError(f"3MF multipart '{object_name}' has the wrong child meshes")
        for part_name, _mesh in parts:
            if config_slots.get(part_name) != expected_slots.get(part_name, 1):
                raise RuntimeError(f"3MF part '{part_name}' has the wrong filament slot")

    return {
        "objects": expected_leaves,
        "build_items": len(build_ids),
        "components": len(component_ids),
        "names": sorted(mesh_names),
        "filaments": config_slots,
        "warnings": 0,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest().upper(),
    }


# --------------------------------------------------------------------------- #
# sampler
# --------------------------------------------------------------------------- #
def make_sampler_scene(
    sizes: tuple[tuple[float, float], ...] = (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ),
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
    base_thickness: float = DEFAULT_BASE_THICKNESS,
) -> trimesh.Scene:
    """Assembly sample: one box per requested size, plus a row of connectors.

    The connector is a single locked part now, so the row is simply ``clips``
    copies of it rather than a tolerance sweep.
    """
    if clips < 1:
        raise ValueError("the sample needs at least one connector")
    scene = trimesh.Scene()
    scene.units = "mm"
    gap = 6.0

    boxes = []
    for size_x, size_y in sizes:
        spec = BoxSpec(
            x=size_x, y=size_y, z=height, wall=wall, flat_inside=flat_inside,
            base_thickness=base_thickness,
        )
        mesh = make_box(spec)
        mesh_report(f"sample box {size_x:g}x{size_y:g}", mesh)
        boxes.append((spec, mesh))

    cursor = 0.0
    depth = max(float(m.extents[1]) for _, m in boxes)
    for spec, mesh in boxes:
        centre = mesh.bounds.mean(axis=0)
        width = float(mesh.extents[0])
        placed = translated(
            mesh,
            (cursor + width / 2.0 - centre[0], -centre[1], -mesh.bounds[0][2]),
        )
        ux, uy = spec.units
        name = f"box_{ux:g}x{uy:g}_{spec.x:g}x{spec.y:g}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
        cursor += width + gap
    total_width = cursor - gap

    # Use a real sampler bin rather than a fresh default-size BoxSpec. Thick
    # walls leave less room at a 16 mm bin's rounded corners, even though the
    # same connector is valid on the sampler's longer wall.
    clip_box = max(boxes, key=lambda item: item[0].y)[0]
    clip = make_side_connector(clip_box, connector, "y", 0.0, side_length)
    validate_side_fit(
        clip_box, connector, clip, "y",
    )
    clip = connector_for_print(clip)
    mesh_report("sample connector", clip)
    cell = float(clip.extents[0]) + 6.0
    row_y = -depth / 2.0 - gap - float(clip.extents[1]) / 2.0
    for index in range(clips):
        centre = clip.bounds.mean(axis=0)
        target = total_width / 2.0 + (index - (clips - 1) / 2.0) * cell
        placed = translated(
            clip,
            (target - centre[0], row_y - centre[1], -clip.bounds[0][2]),
        )
        name = f"connector_{index + 1}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
    return scene


def generate_sampler(
    output: Path,
    sizes: tuple[tuple[float, float], ...] | None = None,
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
    base_thickness: float = DEFAULT_BASE_THICKNESS,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "height": height, "wall": wall, "base_thickness": base_thickness,
        "connector": connector,
        "clips": clips, "side_length": side_length, "flat_inside": flat_inside,
    }
    if sizes is not None:
        kwargs["sizes"] = sizes
    scene = make_sampler_scene(**kwargs)
    export_bambu_compatible_3mf(scene, output)
    report = validate_3mf(output, len(scene.geometry))
    report["boxes"] = [f"{sx:g}x{sy:g}" for sx, sy in (sizes or (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ))]
    report["connectors"] = clips
    report["tolerance_mm"] = connector.tolerance
    report["connector_height_mm"] = connector.height
    report["connector_length_mm"] = side_length
    report["wave_length_mm"] = WAVE_LENGTH
    report["wave_amplitude_mm"] = WAVE_AMPLITUDE
    report["grid_pitch_mm"] = GRID_PITCH
    return report
