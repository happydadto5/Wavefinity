"""Wavefinity web slicer discovery, export cleanup and cabinet/surface request helpers."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
from organizer_inventory import normalise_storage_box
from organizer_product_rules import surface_maximums
from organizer_space_outputs import BASE_TRIM, STORAGE_DRAWERS, structural_kind
from organizer_inventory import storage_drawers_mutate_text
from organizer_printer_profile import component_fit, normalise_printer_profile
from organizer_storage_drawers import (
    normalise_storage_drawers_definition,
    reset_storage_drawers_definition,
    storage_drawers_definition_problem,
)
from organizer_storage_drawer_geometry import resolve_storage_drawers_plan
from organizer_app import _mesh_preview_geometry, design_source_payload
from organizer_slicer import slicer_display_name

from ._runtime import DEFAULT_OUTPUT, GEOMETRY_LOCK, EXPORTS


def slicer_name(slicer_path: Path | None) -> str:
    return slicer_display_name(slicer_path) or "Bambu Studio"


def _find_bambu_studio_windows() -> Path | None:
    # 1. Standard installation locations
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Bambu Studio" / "bambu-studio.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Bambu Studio" / "bambu-studio.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    # 2. PATH
    which = shutil.which("bambu-studio") or shutil.which("bambu-studio.exe")
    if which:
        return Path(which).resolve()

    # 3. Windows Registry
    try:
        import winreg

        # App Paths
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\bambu-studio.exe") as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val and Path(str(val)).is_file():
                        return Path(str(val)).resolve()
            except OSError:
                pass

        # Uninstall keys
        for root, subkey in (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ):
            try:
                with winreg.OpenKey(root, subkey) as ukey:
                    for i in range(winreg.QueryInfoKey(ukey)[0]):
                        try:
                            subkey_name = winreg.EnumKey(ukey, i)
                            with winreg.OpenKey(ukey, subkey_name) as app_key:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                if "bambu studio" in str(display_name).lower():
                                    try:
                                        icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                        icon_path = Path(str(icon).strip('"'))
                                        if icon_path.is_file() and icon_path.name.lower() == "bambu-studio.exe":
                                            return icon_path.resolve()
                                    except OSError:
                                        pass
                                    try:
                                        loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                        loc_exe = Path(str(loc).strip('"')) / "bambu-studio.exe"
                                        if loc_exe.is_file():
                                            return loc_exe.resolve()
                                    except OSError:
                                        pass
                        except OSError:
                            continue
            except OSError:
                pass
    except Exception:
        pass
    return None


def _find_bambu_studio_darwin() -> Path | None:
    candidates = [
        Path("/Applications/BambuStudio.app/Contents/MacOS/BambuStudio"),
        Path.home() / "Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    which = shutil.which("BambuStudio") or shutil.which("bambu-studio")
    return Path(which).resolve() if which else None


def _find_bambu_studio_linux() -> Path | None:
    which = shutil.which("bambu-studio")
    return Path(which).resolve() if which else None


# Fix 096 C8: how long a freshly spawned slicer GUI gets to prove it started.
# Still running after this bound = accepted handoff (a GUI takes longer than a
# second to show itself, but a broken launch fails fast). A nonzero quick exit
# = launch failure. A zero quick exit = accepted handoff: single-instance GUI
# launchers may exit at once after handing off to an already-running process.
SLICER_HANDOFF_TIMEOUT_S = 1.0


def open_log_with_wordpad(file_path: Path) -> None:
    """Open a file with WordPad, falling back to os.startfile / default editor if WordPad is missing."""
    target = str(file_path.resolve())
    wordpad_candidates = [
        shutil.which("wordpad.exe") or shutil.which("wordpad"),
        shutil.which("write.exe") or shutil.which("write"),
        r"C:\Program Files\Windows NT\Accessories\wordpad.exe",
        r"C:\Program Files (x86)\Windows NT\Accessories\wordpad.exe",
        r"C:\Windows\write.exe",
        r"C:\Windows\System32\write.exe",
    ]
    for exe in wordpad_candidates:
        if exe and (Path(exe).is_file() or shutil.which(exe)):
            try:
                subprocess.Popen([exe, target])
                return
            except Exception:
                pass
    if sys.platform == "win32":
        try:
            os.startfile(target)
            return
        except Exception:
            pass
    fallback = shutil.which("notepad.exe") or shutil.which("notepad") or "notepad"
    subprocess.Popen([fallback, target])


class _PartialConnectorBundleError(Exception):
    """An automatic connector bundle failed unexpectedly after one or more
    connectors already generated successfully. Carries those completed
    connector results so the caller can report them truthfully instead of
    losing them behind the exception."""

    def __init__(
        self, error: Exception, completed: dict[str, Any], output: Path | None = None,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.completed = completed
        self.output = output


def _remove_export(record: dict[str, Any]) -> None:
    shutil.rmtree(record["directory"], ignore_errors=True)


def _clean_expired_exports() -> None:
    now = time.monotonic()
    expired = [token for token, record in EXPORTS.items() if record["expires"] <= now]
    for token in expired:
        _remove_export(EXPORTS.pop(token))


def _extract_generated_files(result_data: Any) -> list[Path]:
    paths: list[Path] = []
    if isinstance(result_data, dict):
        if "output" in result_data and isinstance(result_data["output"], (str, Path)):
            paths.append(Path(result_data["output"]))
        for v in result_data.values():
            paths.extend(_extract_generated_files(v))
    elif isinstance(result_data, (list, tuple)):
        for item in result_data:
            paths.extend(_extract_generated_files(item))
    seen: set[Path] = set()
    deduped: list[Path] = []
    for p in paths:
        try:
            res = p.resolve()
            if res not in seen and res.is_file():
                seen.add(res)
                deduped.append(res)
        except Exception:
            continue
    return deduped


def _printed_reuse_files(payload: dict[str, Any]) -> tuple[Path, list[Path]] | None:
    """Existing Wavefinity-owned bin file(s) of an unchanged Printed row, else None.

    The browser only asks; this proves it under Inventory authority. Any failed
    proof returns None so the normal timestamped generation runs instead.
    """
    if payload.get("reuse_printed_file") is not True:
        return None
    row_id = str(payload.get("design_row_id") or "")
    if not row_id or not isinstance(payload.get("design"), dict):
        return None
    try:
        from organizer_drawer import inventory_row_files
        from organizer_inventory import INVENTORY_LOCK, design_specs, load_inventory

        canonical, _record = design_source_payload(payload["design"])
        folder = Path(payload.get("output") or DEFAULT_OUTPUT).expanduser().resolve()
        with INVENTORY_LOCK:
            current = load_inventory(folder)
            row = next((one for one in current["bins"] if one.get("id") == row_id), None)
            if row is None or row.get("kind") not in ("bin", "b4b") or row.get("status") != "printed":
                return None
            if not str(row.get("file") or "").strip():
                return None
            if design_specs(current["layout"]).get(row_id) != canonical:
                return None
            files = inventory_row_files(folder, row)
        if not files or not all(path.suffix.lower() == ".3mf" and path.is_file() for path in files):
            return None
        return folder, files
    except Exception:
        return None


def _is_storage_drawers_request(payload: dict[str, Any]) -> bool:
    space = payload.get("space")
    return structural_kind(space if isinstance(space, dict) else None) == STORAGE_DRAWERS


def storage_drawers_mutate_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted twin of the cabinet mutation: pure over the supplied Inventory text."""
    return storage_drawers_mutate_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or "Wavefinity"),
        operation=str(payload.get("operation") or ""),
        drawer_id=payload.get("drawer_id"), proposed=payload.get("space"),
    )


def storage_drawers_preview_meshes(space: dict[str, Any]) -> dict[str, Any] | None:
    """Compact GPU-ready 3D preview for a Storage Drawers cabinet (Fix 103, Section D).

    Builds the actual production meshes via resolve_storage_drawers_plan
    (assembled coordinates, NOT print-bed export orientations), serializes
    each through _mesh_preview_geometry (numpy, sliver-dropping, micron-
    rounded), and groups by (kind, owner, layer) exactly like
    b4b_preview_meshes. No output folder is needed and no files are written,
    so this works identically hosted and local.

    Owner keys are the production component keys (stable across requests),
    including "drawer:<stable-id>" for drawer components, so the client can
    highlight the active drawer. Known printer oversize does NOT block the
    preview (it is a non-blocking warning at the Space-definition level).

    Returns None if the meshes cannot be built (caller treats a missing
    preview as "not ready", not as a fatal error).
    """
    groups: dict[tuple[str, str, int], dict[str, list[float]]] = {}
    components: list[dict[str, str]] = []
    try:
        # The production mesh makers / CSG and the serialization below both run
        # under the one geometry lock (an RLock), never before it.
        with GEOMETRY_LOCK:
            plan = resolve_storage_drawers_plan(space, build_meshes=True)
            for component in plan.components:
                kind = "drawer" if component.key.startswith("drawer:") else "cabinet"
                owner = component.key
                components.append({"key": component.key, "name": component.display_name, "owner": owner, "kind": kind})
                parts = []
                if component.mesh is not None:
                    parts.append(component.mesh)
                for _label, part in component.object_groups or ():
                    parts.append(part)
                for mesh in parts:
                    # _mesh_preview_geometry yields (triangle, kind, normal, layer, owner).
                    for points, _k, normal, layer, _o in _mesh_preview_geometry(mesh, kind, owner):
                        bucket = groups.setdefault((kind, owner, layer), {"positions": [], "normals": []})
                        for corner in points:
                            bucket["positions"].extend(corner)
                        bucket["normals"].extend(normal)
    except Exception:
        return None
    meshes = [
        {"kind": kind, "owner": owner, "layer": layer,
         "positions": bucket["positions"], "normals": bucket["normals"]}
        for (kind, owner, layer), bucket in groups.items()
    ]
    ox, oy, oz = plan.outside_xyz
    return {
        "meshes": meshes,
        "bounds": {"x": ox, "y": oy, "z": oz},
        "components": components,
        # Response-shape compatibility with ordinary previews.
        "geometry": [],
    }


def storage_drawers_validate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure: the canonical normalizer over a raw Storage Drawers Space. Hosted
    inspection and setup use it so browser and desktop accept the same cabinets."""
    return {"space": normalise_storage_drawers_definition(payload.get("space"))}


def storage_drawers_reset_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Pure: what Reset cabinet settings would leave, plus why it is needed."""
    raw = payload.get("space")
    return {
        "space": reset_storage_drawers_definition(raw),
        "message": storage_drawers_definition_problem(raw) or "",
    }


def _storage_box_printer_fit(summary: dict[str, Any], profile: dict[str, float]) -> tuple[bool, str | None]:
    """Drawers-style printer verdict for a Storage Box case.

    Each separately printed object (body, lid) is checked on its own, flat and
    rotated 90 degrees on the bed, in the pose it is exported in. The assembled
    envelope is never the test: a body and lid that each fit are not refused
    because the closed case is taller or wider than the bed. Unreadable bounds
    mean "cannot check": no warning, and creation is never blocked.
    """
    objects = summary.get("print_objects_mm")
    if not isinstance(objects, list) or not objects:
        return True, None
    profile = normalise_printer_profile(profile)
    bed = f"{profile['x_mm']:g} × {profile['y_mm']:g} × {profile['z_mm']:g}"
    for one in objects:
        try:
            bounds = tuple(float(value) for value in one["bounds_mm"])
            name = str(one["name"])
        except (KeyError, TypeError, ValueError):
            return True, None
        if len(bounds) != 3 or any(value <= 0 for value in bounds):
            return True, None
        if not component_fit(bounds, ("flat", "bed_90"), profile)["fits"]:
            size = " × ".join(f"{value:.1f}" for value in bounds)
            return False, f"{name} is {size} mm and does not fit the {bed} mm printer in any orientation."
    return True, None


def _is_base_trim_request(payload: dict[str, Any]) -> bool:
    space = payload.get("space")
    return structural_kind(space if isinstance(space, dict) else None) == BASE_TRIM


def _storage_box_arrangement_issue(arranged: dict[str, Any], space: dict[str, Any]) -> str | None:
    if any(abs(float(arranged.get(axis, 0)) - float(space[axis])) > 1e-6 for axis in ("x", "y", "z")) \
            or normalise_storage_box(arranged.get("storage_box")) != normalise_storage_box(space.get("storage_box")):
        return "Storage Box settings and saved arrangement disagree. Reopen this Space and try again."
    return None


def _surface_arrangement_issue(arranged: dict[str, Any], space: dict[str, Any]) -> str | None:
    if any(abs(float(arranged.get(axis, 0)) - float(space[axis])) > 1e-6 for axis in ("x", "y", "z")) \
            or arranged.get("trim_size") != space.get("trim_size"):
        return "Surface settings and saved arrangement disagree. Reopen this Space and try again."
    # Canonical maximums: a legacy layout with none seeds to its current finished
    # footprint, so it only disagrees when a real maximum differs.
    try:
        saved = surface_maximums(arranged, float(arranged["x"]), float(arranged["y"]), arranged["trim_size"], strict=False)
        authoritative = surface_maximums(space, float(space["x"]), float(space["y"]), space["trim_size"], strict=False)
    except (KeyError, TypeError, ValueError):
        return "Surface settings and saved arrangement disagree. Reopen this Space and try again."
    if any(abs(one - other) > 1e-6 for one, other in zip(saved, authoritative)):
        return "Surface settings and saved arrangement disagree. Reopen this Space and try again."
    return None
