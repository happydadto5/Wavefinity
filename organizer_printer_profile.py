"""Pure printer build-volume normalization shared by structural outputs."""
from __future__ import annotations

import math

import numpy as np

DEFAULT_PRINTER_BUILD_MM = (256.0, 256.0, 256.0)
_PREF_KEYS = ("printer_build_x_mm", "printer_build_y_mm", "printer_build_z_mm")
PRINTER_PREF_KEYS = _PREF_KEYS
_AXES = ("x_mm", "y_mm", "z_mm")


def normalise_printer_profile(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Printer build volume must be an object")
    result = {}
    for axis in _AXES:
        value = raw.get(axis)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Printer {axis} must be a positive number")
        value = float(value)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"Printer {axis} must be a positive number")
        result[axis] = value
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
    return printer_profile_state(prefs)["profile"]


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
    bed = (profile["x_mm"], profile["y_mm"], profile["z_mm"])
    for name in allowed_orientations:
        oriented = oriented_bounds(bounds_xyz, name)
        if all(size <= limit + 1e-6 for size, limit in zip(oriented, bed)):
            return {"fits": True, "orientation": name, "reason": ""}
    return {"fits": False, "orientation": "", "reason": f"Component {tuple(round(v, 2) for v in bounds_xyz)} mm exceeds printer {bed} mm"}
