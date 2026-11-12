"""Dependency-light slicer display-name helpers."""

from __future__ import annotations

from pathlib import Path

from .printer_profile import current_export_profile, fit_status, print_file_fit_issues


def require_export_fit(files, profile: dict | None = None) -> str:
    """One export verdict, used before staged files are installed or handed off."""
    profile = current_export_profile() if profile is None else profile
    issues = [issue for path in files for issue in print_file_fit_issues(path, profile)]
    if issues:
        raise ValueError("Export refused:\n" + "\n".join(issues))
    return fit_status(profile)


def slicer_display_name(slicer_path: str | Path | None) -> str | None:
    """Return a friendly name for a known slicer executable; None if unknown."""
    if not slicer_path:
        return None
    path = Path(slicer_path)
    name = path.stem.replace("-", " ").replace("_", " ").strip().title()
    lower = name.lower()
    if "bambu" in lower:
        return "Bambu Studio"
    if "orca" in lower:
        return "OrcaSlicer"
    return name or None
