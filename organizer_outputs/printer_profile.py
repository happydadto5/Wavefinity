"""Pure printer build-volume normalization shared by structural outputs."""
from __future__ import annotations

import math
from contextlib import contextmanager
from contextvars import ContextVar

import numpy as np

DEFAULT_PRINTER_BUILD_MM = (256.0, 256.0, 256.0)
_PREF_KEYS = ("printer_build_x_mm", "printer_build_y_mm", "printer_build_z_mm")
PRINTER_PREF_KEYS = _PREF_KEYS
_AXES = ("x_mm", "y_mm", "z_mm")


_EXPORT_PROFILE = ContextVar("export_printer_profile", default=None)


def current_export_profile() -> dict:
    return _EXPORT_PROFILE.get() or {**dict(zip(_AXES, DEFAULT_PRINTER_BUILD_MM)), "configured": False}


@contextmanager
def export_printer_profile(profile: dict):
    token = _EXPORT_PROFILE.set(normalise_printer_profile(profile))
    try:
        yield
    finally:
        _EXPORT_PROFILE.reset(token)


def fit_status(profile: dict) -> str:
    return "fit checked" if profile.get("configured", True) else "fit unverified"


_AXIS_NAMES = {"x_mm": "width", "y_mm": "depth", "z_mm": "height"}


def normalise_printer_profile(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Printer build volume must be an object")
    result = {}
    for axis in _AXES:
        value = raw.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Printer {_AXIS_NAMES.get(axis, axis)} must be between 10 and 1000 mm.")
        value = float(value)
        if not math.isfinite(value) or value < 10 or value > 1000:
            raise ValueError(f"Printer {_AXIS_NAMES.get(axis, axis)} must be between 10 and 1000 mm.")
        result[axis] = value
    if "configured" in raw:
        result["configured"] = raw["configured"] is True
    return result


def printer_profile_state(prefs: dict) -> dict:
    if not isinstance(prefs, dict):
        prefs = {}
    explicit = all(key in prefs for key in _PREF_KEYS)
    raw = dict(zip(_AXES, (prefs[key] for key in _PREF_KEYS))) if explicit else dict(zip(_AXES, DEFAULT_PRINTER_BUILD_MM))
    return {"profile": normalise_printer_profile(raw), "explicit": explicit}


def default_printer_profile_state(malformed: str = "") -> dict:
    state = {"profile": dict(zip(_AXES, DEFAULT_PRINTER_BUILD_MM)), "explicit": False}
    if malformed:
        state["malformed"] = malformed
    return state


def printer_profile_from_preferences(prefs: dict) -> dict:
    state = printer_profile_state(prefs)
    return {**state["profile"], "configured": state["explicit"]}


def apply_printer_profile_to_preferences(prefs: dict, raw: object) -> dict:
    profile = normalise_printer_profile(raw)
    result = dict(prefs)
    result.update({key: profile[axis] for key, axis in zip(_PREF_KEYS, _AXES)})
    return result


# One authority for print orientations. Each name is an axis order: the
# oriented bounds are ``tuple(bounds[i] for i in axes)`` - so oriented axis k is
# the component's own axis ``axes[k]``. ``component_fit`` reads bounds through
# it; ``orientation_transform`` builds the matching real rotation for meshes.
PRINT_ORIENTATION_AXES = {
    "flat": (0, 1, 2), "bed_90": (1, 0, 2),
    "broad_yz": (2, 1, 0), "broad_yz_90": (1, 2, 0),
    "broad_xz": (0, 2, 1), "broad_xz_90": (2, 0, 1),
}


def orientation_axes(name: str) -> tuple[int, int, int]:
    axes = PRINT_ORIENTATION_AXES.get(name)
    if axes is None:
        raise ValueError(f"Unsupported print orientation: {name}")
    return axes


def orientation_transform(name: str, *, flip_up: bool = False) -> np.ndarray:
    """A proper (determinant +1, never mirrored) 4x4 rotation for ``name``.

    A pure axis swap can be a reflection. Whenever it is, one axis is negated
    so the result is a real rotation. The axis chosen is the print-up (new Z)
    only when the caller wants the part turned over (``flip_up``); otherwise a
    horizontal axis absorbs the sign so the part's own +axis stays up.
    """
    axes = orientation_axes(name)
    matrix = np.zeros((3, 3), dtype=float)
    for row, source in enumerate(axes):
        matrix[row, source] = 1.0
    if flip_up:
        matrix[2] *= -1.0
    if np.linalg.det(matrix) < 0:
        matrix[1 if flip_up else 0] *= -1.0
    result = np.eye(4)
    result[:3, :3] = matrix
    return result


def orient_mesh(mesh, name: str, *, flip_up: bool = False, origin: bool = True):
    """A copy of ``mesh`` rotated into print orientation ``name``.

    ``trimesh`` compensates winding for a negative-determinant transform on its
    own, so nothing here flips faces by hand. With ``origin`` the copy is
    translated so its bounding box starts at (0, 0, 0): a sane, nonnegative
    print-bed origin.
    """
    oriented = mesh.copy()
    oriented.apply_transform(orientation_transform(name, flip_up=flip_up))
    if origin:
        oriented.apply_translation(-oriented.bounds[0])
    return oriented


def oriented_bounds(bounds_xyz: tuple[float, float, float], name: str) -> tuple[float, float, float]:
    return tuple(bounds_xyz[i] for i in orientation_axes(name))


def component_fit(bounds_xyz: tuple[float, float, float], allowed_orientations: tuple[str, ...], profile: dict) -> dict:
    profile = normalise_printer_profile(profile)
    if len(bounds_xyz) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in bounds_xyz):
        raise ValueError("Component bounds must be three positive dimensions")
    if not allowed_orientations:
        raise ValueError("A component must have an allowed print orientation")
    if not profile.get("configured", True):
        return {"fits": None, "orientation": allowed_orientations[0], "reason": "fit unverified"}
    bed = (profile["x_mm"], profile["y_mm"], profile["z_mm"])
    for name in allowed_orientations:
        oriented = oriented_bounds(bounds_xyz, name)
        if all(size <= limit + 1e-6 for size, limit in zip(oriented, bed)):
            return {"fits": True, "orientation": name, "reason": ""}
    failures = []
    for name in allowed_orientations:
        oriented = oriented_bounds(bounds_xyz, name)
        axes = ", ".join(f"{axis} {size:.2f} > {limit:g} mm"
                         for axis, size, limit in zip(("X (width)", "Y (depth)", "Z (height)"), oriented, bed)
                         if size > limit + 1e-6)
        failures.append(f"{name}: {axes}")
    return {"fits": False, "orientation": "", "reason":
            f"Exceeds configured printer ({bed[0]:g} x {bed[1]:g} x {bed[2]:g} mm); " + "; ".join(failures)}


def print_file_fit_issues(path, profile: dict) -> list[str]:
    """Inspect the written model, including every transformed 3MF part."""
    from pathlib import Path
    import trimesh

    if not profile.get("configured", True):
        return []
    source = Path(path)
    if not source.is_file() or source.suffix.lower() != ".3mf":
        return [f"{source.name}: a current 3MF file is unavailable"]
    try:
        import sys
        if sys.platform == "emscripten":
            from wf_browser_core.three_mf import scene_for_fit
            scene = scene_for_fit(source)
        else:
            scene = trimesh.load(source, force="scene")
        nodes = list(scene.graph.nodes_geometry)
        if not nodes:
            return [f"{source.name}: the 3MF has no printable component"]
        candidates = [("complete file", scene.extents)]
        for node in nodes:
            transform, geometry = scene.graph[node]
            mesh = scene.geometry[geometry].copy()
            mesh.apply_transform(transform)
            candidates.append((str(node), mesh.extents))
        issues = []
        for label, extents in candidates:
            bounds = tuple(float(value) for value in extents)
            fit = component_fit(bounds, ("flat", "bed_90"), profile)
            if not fit["fits"]:
                issues.append(f"{source.name} {label}: {fit['reason']}")
        return issues
    except Exception as error:
        return [f"{source.name}: its 3MF print bounds could not be read ({error})"]
