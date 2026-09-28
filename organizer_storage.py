"""The primary Wavefinity storage root: Documents discovery and safe relocation.

Filesystem-only helpers. The preference/registry rewrite that makes a
relocation official lives with the Space routes in ``organizer_spaces``; this
module never reads or writes preferences.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import sys
from typing import Any, Callable
import uuid

_LOG = logging.getLogger("wavefinity.storage")

STAGING_PREFIX = ".Wavefinity-moving-"


# ------------------------------------------------------- Documents discovery


def _windows_known_documents() -> Path | None:
    """The OS Documents known folder (follows OneDrive/enterprise redirection)."""
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8),
            ]

        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        folder_id = GUID(
            0xFDD39AD0, 0x238F, 0x46AF,
            (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7),
        )
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        buffer = ctypes.c_void_p()
        try:
            status = shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(buffer),
            )
            text = ctypes.wstring_at(buffer.value) if status == 0 and buffer.value else ""
        finally:
            if buffer.value:
                ole32.CoTaskMemFree(buffer.value)
        if text and Path(text).is_dir():
            return Path(text).resolve()
    except Exception:
        _LOG.exception("Windows Documents folder lookup failed")
    return None


def documents_folder() -> Path:
    """The user's real Documents folder; ``~/Documents`` only if the OS cannot say."""
    fallback = (Path.home() / "Documents").resolve()
    if sys.platform == "win32":
        found = _windows_known_documents()
        if found is not None:
            return found
        _LOG.warning("Documents known folder unavailable; falling back to %s", fallback)
    return fallback


# ------------------------------------------------------------- path helpers


def _parts(path: Any) -> tuple[str, ...]:
    return tuple(os.path.normcase(part) for part in Path(os.path.normpath(str(path))).parts)


def same_path(a: Any, b: Any) -> bool:
    return _parts(a) == _parts(b)


def is_within(child: Any, root: Any) -> bool:
    """True when ``child`` is ``root`` itself or anything beneath it."""
    if not child or not root:
        return False
    if not os.path.isabs(str(child)):
        return False
    inner, outer = _parts(child), _parts(root)
    return len(inner) >= len(outer) and inner[:len(outer)] == outer


def rebase_path(value: Any, old_root: Path, new_root: Path) -> str | None:
    """``value`` moved from under ``old_root`` to the same place under ``new_root``."""
    if not isinstance(value, str) or not is_within(value, old_root):
        return None
    tail = Path(os.path.normpath(value)).parts[len(Path(os.path.normpath(str(old_root))).parts):]
    return str(Path(new_root).joinpath(*tail))


def rebase_value(node: Any, old_root: Path, new_root: Path) -> Any:
    """Rewrite every path string under ``old_root`` anywhere in a JSON-like tree.

    Dicts are edited in place; lists/strings return their replacement.
    """
    if isinstance(node, dict):
        for key in list(node):
            node[key] = rebase_value(node[key], old_root, new_root)
        return node
    if isinstance(node, list):
        return [rebase_value(item, old_root, new_root) for item in node]
    if isinstance(node, str):
        return rebase_path(node, old_root, new_root) or node
    return node


def destination_conflict(dst: Path) -> bool:
    """Anything already at ``dst`` other than a genuinely empty folder."""
    try:
        if not os.path.lexists(dst):
            return False
        if dst.is_dir() and not dst.is_symlink():
            return any(True for _ in dst.iterdir())
        return True
    except OSError:
        return True


# --------------------------------------------------------------- relocation


def _raise(error: OSError) -> None:
    raise error


def tree_manifest(root: Path) -> dict[str, tuple]:
    """Every entry beneath ``root`` (relative path -> kind/size/link target)."""
    entries: dict[str, tuple] = {}
    for current, dirs, files in os.walk(root, followlinks=False, onerror=_raise):
        base = Path(current)
        for name in [*dirs, *files]:
            full = base / name
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                entries[rel] = ("l", os.readlink(full))
            elif full.is_dir():
                entries[rel] = ("d",)
            else:
                entries[rel] = ("f", full.stat().st_size)
    return entries


def _remove_owned_staging(staging: Path) -> None:
    try:
        shutil.rmtree(staging)
    except FileNotFoundError:
        pass
    except OSError:
        _LOG.warning("Could not remove partial copy %s", staging)


def remove_stale_staging(staging: Any, dst_parent: Any) -> None:
    """Discard a partial copy left by an interrupted move - only our own folder."""
    if not staging:
        return
    path = Path(str(staging))
    if path.name.startswith(STAGING_PREFIX) and same_path(path.parent, dst_parent):
        _remove_owned_staging(path)


def transfer_tree(
    src: Path, dst: Path, record: Callable[[dict[str, Any] | None], None],
) -> tuple[str, dict[str, tuple] | None]:
    """Bring the whole ``src`` tree to ``dst`` without ever touching ``src``'s content.

    Same-volume: one atomic rename. Otherwise copy into a sibling staging
    folder, verify it against ``src``, then rename it into place. ``src`` is left
    intact in the copy case (the caller removes it only after the switch is
    committed). ``record`` durably notes an in-progress move before any change.
    Returns ("renamed", None) or ("copied", verified manifest of src). On any
    failure ``dst`` is left absent and ``src`` untouched.
    """
    if not src.is_dir():
        raise ValueError("The current Wavefinity folder could not be found. Nothing was moved.")
    if destination_conflict(dst):
        raise ValueError("A Wavefinity folder already exists there. Nothing was moved.")
    staging = dst.parent / f"{STAGING_PREFIX}{uuid.uuid4().hex[:8]}"
    record({"src": str(src), "dst": str(dst), "staging": str(staging), "stage": "pending"})
    try:
        if dst.is_dir():
            dst.rmdir()  # only ever an empty folder (checked above)
        try:
            os.rename(src, dst)
            return "renamed", None
        except OSError:
            if not src.is_dir() or os.path.lexists(dst):
                raise
        before = tree_manifest(src)
        shutil.copytree(src, staging, symlinks=True)
        if tree_manifest(staging) != before or tree_manifest(src) != before:
            raise ValueError(
                "Wavefinity data changed while it was being copied. Nothing was moved. "
                "Try again when nothing is being edited."
            )
        os.rename(staging, dst)
        return "copied", before
    except ValueError:
        _remove_owned_staging(staging)
        record(None)
        raise
    except (OSError, shutil.Error) as error:
        _remove_owned_staging(staging)
        record(None)
        raise ValueError(
            "Wavefinity could not move its folder to that location. "
            "Nothing was changed and your current folder is still in use."
        ) from error


def undo_transfer(src: Path, dst: Path, mode: str) -> None:
    """Put things back after a transfer whose switch could not be committed."""
    try:
        if mode == "renamed":
            os.rename(dst, src)
        else:
            shutil.rmtree(dst)  # our own verified copy; src is intact
    except OSError:
        _LOG.exception("Could not undo relocation of %s", src)


def discard_old_tree(src: Path, expected: dict[str, tuple] | None) -> bool:
    """Remove the old root after a committed copy - only if nothing new appeared."""
    if expected is None:
        return True
    try:
        if not src.is_dir() or tree_manifest(src) != expected:
            return False
        shutil.rmtree(src)
        return True
    except (OSError, shutil.Error):
        return False
