"""Dependency-light slicer display-name helpers."""

from __future__ import annotations

from pathlib import Path


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
