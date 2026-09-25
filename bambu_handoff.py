"""Stage Wavefinity's profile-free model 3MFs for a direct Bambu Studio handoff.

Fix 058: Wavefinity never builds a Bambu *project* for the live Print path.
Bambu Studio's own GUI accepts ordinary model files directly, so each
requested physical occurrence (repeated source paths are repeated physical
copies, never deduplicated) is copied into its own file in a persistent
handoff directory and opened directly - no ``--export-3mf``, no
``--arrange``, no ``--slice``, no ``--load-settings``/``--load-filaments``,
and no printer/process/filament preset of any kind. Bambu Studio and the
user remain entirely authoritative for those settings.

Wavefinity's generated 3MFs are already settings-safe (see
``organizer_engine._stamp_identity``), but every source is still validated
here before staging, so a future regression cannot silently reintroduce a
project/process/filament preset into the handoff.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

BAMBU_EXECUTABLE_NAMES = {
    "bambu-studio.exe", "bambu-studio", "bambustudio.exe", "bambustudio",
}

# A handoff directory is pruned once it is at least this old, and never the
# one just created for the current launch.
STALE_HANDOFF_AGE_SECONDS = 24 * 60 * 60

# Bambu Studio's own project/preset members. Any of these on a source 3MF
# means the file carries an embedded printer/process/filament preset, which
# Wavefinity must never hand to Bambu Studio.
_UNSAFE_MEMBER_PATTERNS = (
    re.compile(r"^Metadata/project_settings\.config$", re.IGNORECASE),
    re.compile(r"^Metadata/print_profile\.config$", re.IGNORECASE),
    re.compile(r"^Metadata/print_setting_.*", re.IGNORECASE),
    re.compile(r"^Metadata/process_settings_.*\.config$", re.IGNORECASE),
    re.compile(r"^Metadata/filament_settings_.*\.config$", re.IGNORECASE),
    re.compile(r"^Metadata/machine_settings_.*\.config$", re.IGNORECASE),
)

# The one project-metadata member Wavefinity's own model files are allowed to
# carry: object/part names and deliberate per-part extruder-slot assignment.
_SAFE_MEMBER = "metadata/model_settings.config"

_EXTRUDER_RE = re.compile(
    r'key\s*=\s*"extruder"\s+value\s*=\s*"(\d+)"'
    r'|value\s*=\s*"(\d+)"\s+key\s*=\s*"extruder"'
)


def is_bambu_studio_executable(path: Path) -> bool:
    return Path(path).name.lower() in BAMBU_EXECUTABLE_NAMES


def _normalised_zip_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as z:
        return {name.lstrip("/") for name in z.namelist()}


def _second_colour_assignment_count(path: Path) -> int:
    """Number of object/part entries assigned to a filament slot other than 1."""
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.lstrip("/").lower() == _SAFE_MEMBER:
                text = z.read(name).decode("utf-8", errors="replace")
                break
        else:
            return 0
    count = 0
    for match in _EXTRUDER_RE.finditer(text):
        slot = int(match.group(1) or match.group(2))
        if slot != 1:
            count += 1
    return count


def _unsafe_members(names: set[str]) -> list[str]:
    return sorted(
        name for name in names
        if any(pattern.match(name) for pattern in _UNSAFE_MEMBER_PATTERNS)
    )


def _validate_settings_safe(path: Path) -> None:
    """Reject a source 3MF that carries an embedded slicer/profile preset.

    Never silently strips or rewrites the file - a settings-bearing source is
    refused outright, with a clear reason, and is never staged.
    """
    try:
        names = _normalised_zip_names(path)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"'{path.name}' is not a valid 3MF package.") from exc
    unsafe = _unsafe_members(names)
    if unsafe:
        raise ValueError(
            f"Wavefinity stopped the Bambu handoff because {path.name} contains "
            f"embedded slicer/profile settings ({', '.join(unsafe)})."
        )


def _default_handoff_root() -> Path:
    return Path(tempfile.gettempdir()) / "Wavefinity" / "Bambu Handoffs"


def prune_stale_handoffs(root: Path, keep: Path | None = None) -> None:
    """Best-effort removal of old handoff directories.

    ``keep`` (the handoff just created, if any) is never touched, and any
    directory younger than ``STALE_HANDOFF_AGE_SECONDS`` is left alone too -
    Bambu Studio may still be reading it. Failures here are never fatal to a
    Print; a stale directory left behind by a permissions problem is not
    worth failing the current launch over.
    """
    if not root.is_dir():
        return
    cutoff = time.time() - STALE_HANDOFF_AGE_SECONDS
    for child in root.iterdir():
        if keep is not None and child.resolve() == keep.resolve():
            continue
        if not child.is_dir():
            continue
        try:
            if child.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(child, ignore_errors=True)
        except OSError:
            pass


def stage_bambu_inputs(
    files: list[Path],
    *,
    handoff_root: Path | None = None,
) -> list[Path]:
    """Copy each requested occurrence into its own file, ready to hand to Bambu.

    Repeated source paths are meaningful physical copies and are never
    deduplicated. Every source must already exist, be a regular ``.3mf``
    file, and pass the settings-safe check above - a rejection here means
    nothing is staged and nothing is opened.

    The returned paths live under a persistent handoff directory (never a
    ``TemporaryDirectory``, which would vanish as soon as this function
    returns): Bambu Studio may still be reading the files asynchronously
    after its process is launched. Old handoff directories are pruned
    opportunistically - conservatively, and never the one just created.
    """
    if not files:
        raise ValueError("No files to open in slicer")
    sources: list[Path] = []
    for f in files:
        p = Path(f).resolve()
        if not p.is_file():
            raise ValueError(f"File not found for Bambu Studio: {p}")
        if p.suffix.lower() != ".3mf":
            raise ValueError(f"Bambu Studio needs .3mf files, not {p.name}")
        _validate_settings_safe(p)
        sources.append(p)

    root = Path(handoff_root) if handoff_root else _default_handoff_root()
    root.mkdir(parents=True, exist_ok=True)
    handoff_dir = (root / uuid.uuid4().hex).resolve()
    handoff_dir.mkdir(parents=True)

    staged: list[Path] = []
    try:
        for i, src in enumerate(sources, 1):
            dest = handoff_dir / f"{i:04d} - {src.stem}.3mf"
            shutil.copyfile(src, dest)
            # Fix 058 E / Correction 1 C1.3: if the source has non-default
            # (not slot 1) extruder assignments - e.g. a two-color part -
            # confirm the staged copy carries the same count before Bambu is
            # ever launched. Staged files are byte-for-byte copies, so this
            # never rewrites either file; a mismatch means the handoff is
            # incomplete and must be refused, not silently accepted.
            source_slots = _second_colour_assignment_count(src)
            if source_slots:
                staged_slots = _second_colour_assignment_count(dest)
                if staged_slots != source_slots:
                    raise ValueError(
                        f"Wavefinity stopped the Bambu handoff because the staged "
                        f"copy of {src.name} does not preserve its "
                        f"{source_slots} extruder-slot assignment(s) "
                        f"({staged_slots} found)."
                    )
            staged.append(dest)
    except Exception:
        shutil.rmtree(handoff_dir, ignore_errors=True)
        raise

    prune_stale_handoffs(root, keep=handoff_dir)
    return staged
