"""Pure printer build-volume normalization shared by structural outputs."""
from __future__ import annotations

import math

DEFAULT_PRINTER_BUILD_MM = (256.0, 256.0, 256.0)
_PREF_KEYS = ("printer_build_x_mm", "printer_build_y_mm", "printer_build_z_mm")
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
    explicit = any(key in prefs for key in _PREF_KEYS)
    if explicit and not all(key in prefs for key in _PREF_KEYS):
        raise ValueError("Printer build volume is incomplete")
    raw = dict(zip(_AXES, (prefs[key] for key in _PREF_KEYS))) if explicit else dict(zip(_AXES, DEFAULT_PRINTER_BUILD_MM))
    return {"profile": normalise_printer_profile(raw), "explicit": explicit}


def printer_profile_from_preferences(prefs: dict) -> dict:
    return printer_profile_state(prefs)["profile"]


def apply_printer_profile_to_preferences(prefs: dict, raw: object) -> dict:
    profile = normalise_printer_profile(raw)
    result = dict(prefs)
    result.update({key: profile[axis] for key, axis in zip(_PREF_KEYS, _AXES)})
    return result


def component_fit(bounds_xyz: tuple[float, float, float], allowed_orientations: tuple[str, ...], profile: dict) -> dict:
    profile = normalise_printer_profile(profile)
    if len(bounds_xyz) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in bounds_xyz):
        raise ValueError("Component bounds must be three positive dimensions")
    bed = (profile["x_mm"], profile["y_mm"], profile["z_mm"])
    transforms = {"flat": (0, 1, 2), "bed_90": (1, 0, 2), "side_x": (2, 1, 0), "side_y": (0, 2, 1)}
    for name in allowed_orientations:
        axes = transforms.get(name)
        if axes is None:
            raise ValueError(f"Unsupported print orientation: {name}")
        oriented = tuple(bounds_xyz[i] for i in axes)
        if all(size <= limit + 1e-6 for size, limit in zip(oriented, bed)):
            return {"fits": True, "orientation": name, "reason": ""}
    return {"fits": False, "orientation": "", "reason": f"Component {tuple(round(v, 2) for v in bounds_xyz)} mm exceeds printer {bed} mm"}
