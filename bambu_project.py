"""Turn a list of Wavefinity 3MF files into one Bambu Studio project.

Wavefinity's generated 3MFs are portable model files, not Bambu projects.
At print time Bambu Studio's own command line arranges the requested copies
and exports one real project, which is then opened in the GUI. No slicing and
no printer/process/filament profile is ever passed on.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

BAMBU_EXECUTABLE_NAMES = {
    "bambu-studio.exe", "bambu-studio", "bambustudio.exe", "bambustudio",
}
CLI_TIMEOUT_SECONDS = 300
_LOG_TAIL_CHARS = 1500
_REQUIRED_MEMBERS = (
    "Metadata/project_settings.config",
    "Metadata/model_settings.config",
)
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
            if name.lstrip("/") == "Metadata/model_settings.config":
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


def _tail(text: str | None) -> str:
    return (text or "").strip()[-_LOG_TAIL_CHARS:]


def _discard(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def build_bambu_project(
    slicer_path: Path,
    files: list[Path],
    *,
    project_root: Path | None = None,
) -> Path:
    """Export one arranged Bambu project containing every listed occurrence."""
    slicer_path = Path(slicer_path)
    if not files:
        raise ValueError("No files to open in slicer")
    sources: list[Path] = []
    for f in files:
        p = Path(f).resolve()
        if not p.is_file():
            raise ValueError(f"File not found for Bambu Studio: {p}")
        if p.suffix.lower() != ".3mf":
            raise ValueError(f"Bambu projects need .3mf files, not {p.name}")
        sources.append(p)

    root = Path(project_root) if project_root else (
        Path(tempfile.gettempdir()) / "Wavefinity" / "Bambu Projects"
    )
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    project = (root / f"Wavefinity Print {stamp}.3mf").resolve()

    wants_second_colour = any(_second_colour_assignment_count(s) > 0 for s in sources)

    with tempfile.TemporaryDirectory() as staging:
        staged: list[Path] = []
        for i, src in enumerate(sources, 1):
            dest = Path(staging) / f"{i:04d}.3mf"
            shutil.copyfile(src, dest)
            staged.append(dest)
        args = [
            str(slicer_path.resolve()),
            "--arrange", "1",
            "--export-3mf", str(project),
            *[str(p.resolve()) for p in staged],
        ]
        try:
            done = subprocess.run(
                args,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=CLI_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            _discard(project)
            raise RuntimeError(
                "Bambu Studio took too long to build the project. Nothing was marked printed."
            ) from exc
        if done.returncode != 0:
            _discard(project)
            raise RuntimeError(
                f"Bambu Studio could not build the project (exit {done.returncode}). "
                f"Nothing was marked printed. {_tail(done.stderr) or _tail(done.stdout)}"
            )

    if not project.is_file() or project.stat().st_size == 0:
        _discard(project)
        raise RuntimeError(
            "Bambu Studio did not create a project file. Nothing was marked printed."
        )
    try:
        names = _normalised_zip_names(project)
    except zipfile.BadZipFile:
        names = set()
    if not all(m in names for m in _REQUIRED_MEMBERS):
        _discard(project)
        raise RuntimeError(
            "Bambu Studio did not create a complete project file. Nothing was marked printed."
        )
    if wants_second_colour and _second_colour_assignment_count(project) == 0:
        _discard(project)
        raise RuntimeError(
            "Bambu Studio created the project but dropped Wavefinity's second-color "
            "assignments. Nothing was marked printed."
        )
    return project
