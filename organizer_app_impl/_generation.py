"""Wavefinity staged file generation, inventory logging and kit/side/corner files."""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import trimesh
from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    LOCKED_CONNECTOR_LENGTH,
    export_labelled_box,
    export_mesh,
    connector_for_print,
    label_report,
    make_scoop,
    make_top_labelled_box,
    make_labelled_box,
    make_box,
    make_side_connector,
    make_corner_connector,
    label_mesh_report,
    export_bambu_compatible_3mf,
    measure_lock,
    mesh_report,
    scoop_floor_zone,
    top_label_report,
    union,
    validate_side_fit,
    validate_corner_fit,
)
from organizer_b4b import b4b_effective_box
from organizer_inventory import append_bin
from organizer_inserts import (
    Feature,
    Layout,
    text_depth,
    text_fitted,
    text_is_raised,
    text_of,
    text_placed_outline,
)

from ._common import (
    label_position,
    rim_label_side,
    validate_scoop_lift_grabbers,
    clean_label,
)
from ._filenames import (
    _part_result,
    box_filename,
    connector_filename,
    CORNER_WAYS_NAMES,
    validate_corner_quantity,
    arrange_connector_copies,
)
from ._design_io import inventory_bin_record


def generate_box_file(
    box: BoxSpec,
    output: Path,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict[str, object]:
    """Write a customized box, plus a flush label as a second object if asked.

    An empty label changes nothing: one object, and the plain filename.
    """
    tidy = clean_label(label)
    location = label_position(label_location)
    validate_scoop_lift_grabbers(box, scoop)
    body = make_box(box)
    if scoop:
        body = union([body, make_scoop(box)])
    if not tidy:
        report = mesh_report("wavy_box", body)
        export_mesh(body, output, "wavy_box")
        result = _part_result(output, report)
        result["customizations"] = {"scoop": scoop, "label_position": location}
        return result

    side = rim_label_side(location)
    if side:
        pocketed, inlay = make_top_labelled_box(box, tidy, body, side)
        label_info = top_label_report(box, tidy, side)
    else:
        occupied = [scoop_floor_zone(box)] if scoop else []
        pocketed, inlay = make_labelled_box(box, tidy, occupied, body)
        label_info = label_report(box, tidy, occupied)
    report = mesh_report("wavy_box", pocketed)
    export_labelled_box(pocketed, inlay, output, box_filename(box, suffix=""), tidy)
    result = _part_result(output, report)
    result["label"] = label_info
    result["customizations"] = {"scoop": scoop, "label_position": location}
    return result


def text_report(box: BoxSpec, one: Feature, surface: float) -> dict[str, object]:
    """What one text interior part came out as, for the export report."""
    if one.options.get("level") == "rim":
        from organizer_inserts._text import rim_text_geometry
        _ledge, glyph, cap, receiving_z = rim_text_geometry(box, one)
        return {
            "text": text_of(one), "text_type": "At rim — raised" if text_is_raised(one) else "At rim — inlaid",
            "rim_side": str(one.options.get("rim_side") or "back"),
            "cap_height_mm": round(cap, 3),
            "depth_mm": round(text_depth(one), 3),
            "surface_z_mm": round(receiving_z, 3),
            "raised": text_is_raised(one),
            "glyph_bounds_mm": [round(float(value), 3) for value in glyph.bounds.flatten()],
        }
    cap, _outline = text_fitted(one)
    placed = text_placed_outline(one)
    minx, miny, maxx, maxy = placed.bounds
    centre_x, centre_y = one.zone.centre
    return {
        "text": text_of(one),
        "text_type": "On base — raised" if text_is_raised(one) else "On base — inlaid",
        "cap_height_mm": round(cap, 3),
        "quarter_turns": int(one.options.get("quarter_turns", 0) or 0) % 4,
        "auto": bool(one.options.get("auto")),
        "raised": text_is_raised(one),
        "position_mm": [round(centre_x, 3), round(centre_y, 3)],
        "footprint_mm": [round(maxx - minx, 3), round(maxy - miny, 3)],
        "depth_mm": round(text_depth(one), 3),
        "surface_z_mm": round(surface, 3),
    }


def b4b_filename(box: BoxSpec, part_name: str = "", suffix: str = ".3mf") -> str:
    """``Storage Box 64x48x40 - Fasteners.3mf`` - distinct from an ordinary bin file of
    the same dimensions."""
    eff = b4b_effective_box(box)
    name = f"Storage Box {eff.x:g}x{eff.y:g}x{eff.z:g}"
    tidy = clean_label(part_name) or clean_label(box.b4b.label_text)
    if tidy:
        name += f" - {tidy}"
    return name + suffix


# The exact app-owned namespace for staged ordinary-bin output files and
# promotion backups. Staged files live in a BIN_STAGE_PREFIX* directory inside
# the output folder; backups of replaced finals use BIN_BACKUP_PREFIX* names.
# The transaction machinery below only ever removes names in these two
# namespaces, plus the finals it just installed - unrelated user files are
# never deleted.
BIN_STAGE_PREFIX = ".wavefinity-bin-stage-"
BIN_BACKUP_PREFIX = ".wavefinity-bin-backup-"


def _validate_staged_file(path: Path) -> None:
    """A staged candidate is only promotable as a real, non-empty 3MF file."""
    if path.suffix.lower() != ".3mf" or not path.is_file():
        raise RuntimeError(f"a generated file was not saved: {path.name}")
    if path.stat().st_size == 0:
        raise RuntimeError(f"a generated file is empty: {path.name}")


def _promote_staged_set(output_dir: Path, staged: list[Path], *, auto_timestamp: bool,
                        part_name: str) -> list[Path]:
    """Promote a complete staged file set over the final names.

    Every staged file is validated BEFORE any final is replaced. A final that
    already exists is moved to an app-owned backup name first; if any promotion
    step then fails, installed files are removed and every backup is put back,
    leaving the folder exactly as it was. Only staged files, their backups,
    and the finals this call installed are ever touched.
    Returns the final paths in staged order.
    """
    output_dir = Path(output_dir)
    for path in staged:
        _validate_staged_file(path)
    # auto_timestamp naming is decided against the real output directory here,
    # exactly where _resolve_file inside generate_organizer_files would have
    # decided it during a direct generation.
    finals: list[Path] = []
    seen: set[str] = set()
    for path in staged:
        final = output_dir / path.name
        if auto_timestamp:
            has_name = bool(clean_label(part_name))
            if not has_name or final.exists() or final.name in seen:
                stamp = datetime.now().strftime("%m%d%y%H%M%S")
                final = output_dir / f"{final.stem} {stamp}{final.suffix}"
        if final.name in seen:
            raise RuntimeError(f"generated filenames collide: {final.name}")
        seen.add(final.name)
        finals.append(final)
    backups: dict[str, Path] = {}
    installed: list[Path] = []
    try:
        for staged_path, final in zip(staged, finals):
            if final.exists():
                if not final.is_file():
                    raise RuntimeError(f"cannot replace {final.name}: not a regular file")
                backup = output_dir / f"{BIN_BACKUP_PREFIX}{final.name}"
                if backup.exists():
                    backup.unlink()
                os.replace(final, backup)
                backups[final.name] = backup
            os.replace(staged_path, final)
            installed.append(final)
    except Exception:
        for final in reversed(installed):
            if final.exists():
                final.unlink()
        for name, backup in list(backups.items()):
            if backup.exists():
                os.replace(backup, output_dir / name)
            del backups[name]
        raise
    for backup in backups.values():
        if backup.exists():
            backup.unlink()
    return finals


def _rewrite_staged_paths(node, mapping: dict[str, str]):
    """Rewrite staging-dir paths to their promoted finals inside a result value."""
    if isinstance(node, dict):
        return {key: _rewrite_staged_paths(value, mapping) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_rewrite_staged_paths(value, mapping) for value in node]
    if isinstance(node, Path):
        hit = mapping.get(str(node))
        return Path(hit) if hit is not None else node
    if isinstance(node, str):
        return mapping.get(node, node)
    return node


def log_bin_to_folder(
    output_dir: Path,
    box: BoxSpec,
    layout: Layout,
    generated_files: list[Path] | None = None,
    label: str = "",
    part_name: str = "",
    scoop: bool = False,
    b4b_note: str = "",
    physical_size_mm: tuple[float, float, float] | None = None,
    design_spec: dict[str, Any] | None = None,
) -> Path:
    """Record a generated bin in the save folder's inventory.

    ``design_spec`` is the canonical design JSON (see ``design_source_payload``)
    for the *original* box the user configured - distinct from ``box`` here,
    which may already be an effective/stack-adjusted variant used for the
    physical inventory row. Passing it means Generate/Print, even without an
    explicit Save to Space first, still leaves the new row reloadable.
    """
    return append_bin(output_dir, design_spec=design_spec, **inventory_bin_record(
        box, layout, generated_files, label, part_name, scoop, b4b_note,
        physical_size_mm,
    ))



def generate_side_file(
    box: BoxSpec,
    connector: ConnectorSpec,
    output: Path,
    along: str = "y",
    position: float = 0.0,
    length: float = LOCKED_CONNECTOR_LENGTH,
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
    web_thickness: float | None = None,
    auto_adjust: bool = True,
) -> dict[str, object]:
    mesh = make_side_connector(
        box, connector, along, position, length, bin_a_height, bin_b_height,
        web_thickness=web_thickness, auto_adjust=auto_adjust,
    )
    report = mesh_report("side_connector", mesh)
    overlap = validate_side_fit(
        box, connector, mesh, along, position, bin_a_height, bin_b_height
    )
    fit = {"seated_overlap_mm3": round(overlap, 6)}
    fit.update(measure_lock(
        box, connector, along, position, bin_a_height=bin_a_height,
        bin_b_height=bin_b_height,
    ))
    print_mesh = connector_for_print(mesh)
    export_mesh(print_mesh, output, "side_connector")
    fit.update({
        "bin_a_height_mm": bin_a_height if bin_a_height is not None else box.z,
        "bin_b_height_mm": bin_b_height if bin_b_height is not None else box.z,
        "print_orientation": "flat cap down",
    })
    return _part_result(output, report, fit)


def generate_corner_file(
    box: BoxSpec,
    connector: ConnectorSpec,
    output: Path,
    ways: int,
    quantity: int = 1,
) -> dict[str, object]:
    if ways not in CORNER_WAYS_NAMES:
        raise ValueError("corner connector must be 3-way or 4-way")
    quantity = validate_corner_quantity(quantity)
    mesh = make_corner_connector(box, connector, ways)
    report = mesh_report("corner_connector", mesh)
    overlap = validate_corner_fit(box, connector, mesh, ways)
    print_mesh = arrange_connector_copies(connector_for_print(mesh), quantity)
    if quantity == 1:
        export_mesh(print_mesh, output, "corner_connector")
    else:
        # Separate identical pieces on one plate: several solids by design.
        copies = label_mesh_report("corner_connector", print_mesh)["components"]
        if copies != quantity:
            raise RuntimeError(f"expected {quantity} corner connector copies, got {copies}")
        scene = trimesh.Scene()
        scene.units = "mm"
        scene.add_geometry(print_mesh, node_name="corner_connector", geom_name="corner_connector")
        export_bambu_compatible_3mf(scene, output)
    fit = {
        "seated_overlap_mm3": round(overlap, 6),
        "ways": ways,
        "quantity": quantity,
        "wall_mm": box.wall,
        "print_orientation": "flat cap down",
    }
    return _part_result(output, report, fit)


def generate_kit_files(
    box: BoxSpec,
    connector: ConnectorSpec,
    output_dir: Path,
    side_along: str = "y",
    side_position: float = 0.0,
    label: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "box": generate_box_file(
            box, output_dir / box_filename(box), label, label_location, scoop
        ),
        "side": generate_side_file(
            box,
            connector,
            output_dir / connector_filename(connector, wall=box.wall),
            side_along,
            side_position,
        ),
    }
