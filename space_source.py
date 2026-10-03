"""Test helper: the whole Space front-end source (Fix 112 split it across files)."""
from __future__ import annotations

from pathlib import Path


def spaces_source(web: Path) -> str:
    """``web/spaces/*.js`` in load order, then the root ``web/spaces.js`` boot file."""
    web = Path(web)
    parts = [one.read_text(encoding="utf-8") for one in sorted((web / "spaces").glob("*.js"))]
    parts.append((web / "spaces.js").read_text(encoding="utf-8"))
    return "\n".join(parts)
