"""Test helper: the whole Space front-end source (Fix 112 split it across files)."""
from __future__ import annotations

from pathlib import Path


def spaces_source(web: Path) -> str:
    """``web/spaces/*.js`` in load order, then the root ``web/spaces.js`` boot file."""
    web = Path(web)
    parts = [one.read_text(encoding="utf-8") for one in sorted((web / "spaces").glob("*.js"))]
    parts.append((web / "spaces.js").read_text(encoding="utf-8"))
    return "\n".join(parts)


_STRICT = '"use strict";'


def app_source(web: Path) -> str:
    """The whole editor script: ``web/app/*.js`` in load order, then the root ``web/app.js`` boot file.

    Each split file after the first opens with its own ``"use strict";`` line; it is
    dropped here so the result is the original single-file ``app.js`` text exactly.
    """
    web = Path(web)
    files = sorted((web / "app").glob("*.js")) + [web / "app.js"]
    parts = []
    for index, one in enumerate(files):
        text = one.read_text(encoding="utf-8")
        parts.append(text if index == 0 else text.removeprefix(_STRICT))
    return "".join(parts)
