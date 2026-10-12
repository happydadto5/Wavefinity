"""Structural cabinet output planning and manifest-owned file replacement."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

import numpy as np
import trimesh

from organizer_app import clean_label
from organizer_engine import export_mesh, export_text_body_3mf, validate_3mf
from organizer_outputs.printer_profile import component_fit, normalise_printer_profile, orientation_transform
from organizer_storage.drawers import normalise_storage_drawers_definition
from organizer_storage.drawer_geometry import resolve_storage_drawers_plan

STRUCTURAL_OUTPUT_KEY = "storage_drawers"
# Version 4: Fix 1113 — Fix 114 changed runner, dovetail, pull, top-retention and
# support geometry, so pre-114 saved manifests must report needs-update.
STRUCTURAL_GENERATOR_VERSION = 4
# The exact app-owned namespace for temp files and rollback backups in a Space folder.
CABINET_DEBRIS_PREFIX = ".wavefinity-cabinet-"
# (Fix 096 A7) The local transaction namespace: only files under this prefix
# are ever written by the local save path, so only they may be swept. Hosted
# recovery backups (".wavefinity-cabinet-backup-…") live under a different
# prefix and can never match, even before the journal check below.
CABINET_LOCAL_DEBRIS_PREFIX = ".wavefinity-cabinet-local-"
# The hosted recovery journal filename (written by the browser; read here only
# to protect live backups). Mirrors SP.CABINET_JOURNAL in web/spaces.js.
HOSTED_CABINET_JOURNAL_NAME = ".wavefinity-cabinet-journal.json"
# The local recovery journal filename (Fix 1103). Written by _materialize
# before any owned file is replaced and cleared once the save (or a rollback)
# settles. The ".json" suffix keeps it outside the debris sweeper's "*.3mf"
# pattern, so the journal itself is never swept.
LOCAL_CABINET_JOURNAL_NAME = ".wavefinity-cabinet-local-journal.json"
# Held for a whole local save (stage, install, manifest commit, cleanup) so debris
# sweeping can never remove files an active transaction still owns.
_TRANSACTION_LOCK = threading.RLock()


def effective_structural_state(space: dict) -> dict:
    canonical = normalise_storage_drawers_definition(space)
    block = canonical["storage_drawers"]
    plan = resolve_storage_drawers_plan(canonical, build_meshes=False)
    state = {
        "version": STRUCTURAL_GENERATOR_VERSION, "name": canonical["name"],
        "field": [canonical["x"], canonical["y"]],
        "drawers": [{"id": row["id"], "height_mm": row["height_mm"],
                     **({"label_text": row["label_text"]} if block["drawer_labels_enabled"] and row["label_text"] else {})}
                    for row in block["drawers"]],
        "cabinet_style": block["cabinet_style"], "rear_support": block["rear_support"],
        "wall_mounting": block["wall_mounting"],
        "wall_mount_keyholes_per_drawer": block["wall_mount_keyholes_per_drawer"],
        "drawer_fit_mm": block["drawer_fit_mm"], "drawer_handles": block["drawer_handles"],
        "stacking": block["stacking"], "unit_label_enabled": block["unit_label_enabled"],
        "drawer_labels_enabled": block["drawer_labels_enabled"],
        "material": {key: block[key] for key in ("cabinet_wall_mm", "cabinet_base_mm", "cabinet_top_mm", "drawer_wall_mm", "drawer_base_mm")},
        "effective_base_mm": plan.effective_base_mm, "effective_top_mm": plan.effective_top_mm,
    }
    # Only Open geometry depends on the frame width. Full stays independent of a
    # hidden Open selection, in geometry and in this freshness signature.
    if block["cabinet_style"] == "open":
        state["open_frame_width_mm"] = block["open_frame_width_mm"]
        state["resolved_frame_width_mm"] = plan.resolved_frame_width_mm
    if block["drawer_handles"]:
        state["drawer_handle_size"] = block["drawer_handle_size"]
    if block["unit_label_enabled"]:
        state["unit_label_text"] = block["unit_label_text"]
    if block["drawer_labels_enabled"]:
        state["drawer_label_style"] = block["drawer_label_style"]
    return state


def structural_signature(space: dict) -> str:
    encoded = json.dumps(effective_structural_state(space), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _filename(space_name: str, component_name: str) -> str:
    safe = clean_label(space_name)
    if not safe:
        raise ValueError("Space name does not make a valid filename")
    return f"{safe} - {component_name}.3mf"


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_path(folder: Path, filename: str) -> Path:
    if Path(filename).name != filename or filename in (".", "..") or not filename.lower().endswith(".3mf"):
        raise ValueError("Invalid cabinet component filename")
    return folder / filename


def structural_manifest_plan(space: dict, output_dir: Path, printer_profile: dict) -> dict:
    plan = resolve_storage_drawers_plan(space, build_meshes=False)
    profile = normalise_printer_profile(printer_profile)
    components = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            fit = {**fit, "reason": f"{component.display_name}: {fit['reason']}"}
        filename = _filename(plan.space["name"], component.display_name)
        _safe_path(Path(output_dir), filename)
        components.append({"key": component.key, "filename": filename,
                           "bounds_xyz": list(component.bounds_xyz), **fit})
    return {"signature": structural_signature(plan.space), "generator_version": STRUCTURAL_GENERATOR_VERSION,
            "components": components, "fits_printer": all(one["fits"] for one in components),
            "first_fit_error": next((one["reason"] for one in components if not one["fits"]), None)}


def _valid_manifest_components(manifest) -> list | None:
    """The manifest's component rows if it has the right shape, else None."""
    if not isinstance(manifest, dict):
        return None
    rows = manifest.get("components")
    if not isinstance(rows, list) or not rows:
        return None
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("filename"), str)
                or not isinstance(item.get("sha256"), str) or not isinstance(item.get("key"), str)):
            return None
    return rows


def structural_status(space: dict, stored_manifest: dict | None, output_dir: Path,
                      printer_profile: dict | None = None) -> dict:
    """Saved only when signature, shape, filenames, every file's SHA-256, and the
    exact component key/filename set of the current plan all agree."""
    rows = _valid_manifest_components(stored_manifest)
    if rows is None:
        return {"status": "need_save"}
    if stored_manifest.get("signature") != structural_signature(space):
        return {"status": "need_update"}
    try:
        files = [_safe_path(Path(output_dir), item["filename"]) for item in rows]
    except (TypeError, ValueError):
        return {"status": "need_save"}
    for path, item in zip(files, rows):
        try:
            if not path.is_file() or _hash(path) != item["sha256"]:
                return {"status": "need_save"}
        except OSError:
            return {"status": "need_save"}
    # Fix 1106 (Astra AD-005): a manifest is only "saved" when it IS the complete
    # current plan. The rows that remain can be fully self-consistent (right
    # signature, every file present with a matching hash) while a component is
    # missing, duplicated, or filed under a foreign key/filename — compare exact
    # key/filename multiplicities against the plan before anything is "saved".
    # The (key, filename) multiset is printer-profile independent (filenames are
    # minted from the space name + component display name via _filename), so
    # when no profile is given it is derived from the resolved plan without
    # requiring one — the optional-profile contract is preserved. Only
    # orientation/fit freshness needs a profile (checked below).
    if printer_profile is not None:
        plan_components = structural_manifest_plan(space, Path(output_dir), printer_profile)["components"]
    else:
        try:
            resolved = resolve_storage_drawers_plan(space, build_meshes=False)
            plan_components = [{"key": component.key,
                                "filename": _filename(resolved.space["name"], component.display_name)}
                               for component in resolved.components]
        except (ValueError, KeyError, TypeError, AttributeError):
            # The expected set is underivable, so completeness is unprovable:
            # not "saved". Re-saving regenerates the full set.
            return {"status": "need_save"}
    expected = sorted((one["key"], one["filename"]) for one in plan_components)
    actual = sorted((item["key"], item["filename"]) for item in rows)
    if actual != expected:
        return {"status": "need_save"}
    if printer_profile is not None:
        # Files exported for another printer orientation are stale, not saved.
        wanted = {one["key"]: one for one in plan_components}
        for item in rows:
            now = wanted.get(item["key"])
            if now is None or not now["fits"] or item.get("orientation") != now["orientation"]:
                return {"status": "need_update"}
    return {"status": "saved"}


def _hosted_journal_backup_names(folder: Path) -> set[str]:
    """Backup filenames a live hosted recovery journal still references.

    (Fix 096 A7) The hosted save journal lives in the folder itself; a present
    journal means an interrupted hosted save whose backups must survive until
    the next hosted status/save settles it. Pattern matching alone is not
    ownership: these names are positively identified from the journal.
    """
    try:
        text = (folder / HOSTED_CABINET_JOURNAL_NAME).read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        journal = json.loads(text)
    except ValueError:
        return set()
    names: set[str] = set()
    files = journal.get("files") if isinstance(journal, dict) else None
    if isinstance(files, list):
        for one in files:
            if isinstance(one, dict) and isinstance(one.get("backup"), str):
                names.add(one["backup"])
    return names


def _write_local_journal(folder: Path, state: dict) -> None:
    """Atomically and durably write the local cabinet recovery journal (Fix 1103).

    The journal names every pre-install backup and every installed file, so a
    crash or a failed rollback leaves an exact, retryable recovery record. The
    temp+replace makes a torn write impossible: readers see the previous
    complete journal or the new complete journal, never a half-written one.
    The file fsync makes the content durable on disk before any destructive
    move that depends on it. (Round 5) The directory fsync after the replace
    makes the rename itself durable: the "committing"-phase record (with the
    new manifest's identity) must survive a kill before commit(manifest)
    executes, or the identity proof collapses. (Round 6) The directory fsync
    is platform-safe via _fsync_directory: os.O_DIRECTORY does not exist on
    Windows, so there the directory-fd step is a silent no-op and the write
    never crashes -- the fsync'ed journal payload is the durability-critical
    record on every platform.
    """
    folder = Path(folder)
    payload = json.dumps({"journal_version": 1, **state}, indent=2, sort_keys=True).encode("utf-8")
    fd, tmp_name = tempfile.mkstemp(prefix=CABINET_LOCAL_DEBRIS_PREFIX + "journal-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, folder / LOCAL_CABINET_JOURNAL_NAME)
        # Round 6 (Fix 1103): platform-safe directory fsync so the rename is
        # durable. os.O_DIRECTORY is absent on Windows -- opening a directory
        # fd there fails -- so this step is best-effort only and can never
        # crash the journal write. The payload fsync above is the
        # durability-critical write on every platform.
        _fsync_directory(folder)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _fsync_directory(folder: Path) -> None:
    """Best-effort fsync of a directory so a rename into it is durable.

    (Fix 1103, round 6) On POSIX the directory is opened with os.O_DIRECTORY
    and the fd is fsync'ed. os.O_DIRECTORY does not exist on Windows -- and a
    directory cannot be opened this way there -- so os.open raises OSError and
    this is a silent no-op. The journal payload itself is always fsync'ed by
    _write_local_journal; this step only hardens the rename, never the
    write's success.
    """
    open_flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
    try:
        dir_fd = os.open(folder, open_flags)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def _read_local_journal(folder: Path) -> dict | None:
    """The live local recovery journal, or None when absent/unparseable."""
    try:
        text = (Path(folder) / LOCAL_CABINET_JOURNAL_NAME).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        journal = json.loads(text)
    except ValueError:
        return None
    return journal if isinstance(journal, dict) else None


def _clear_local_journal(folder: Path) -> None:
    """Remove the local recovery journal; the save it described is settled."""
    try:
        (Path(folder) / LOCAL_CABINET_JOURNAL_NAME).unlink()
    except OSError:
        pass


def _local_journal_backup_names(folder: Path) -> set[str]:
    """Backup filenames a live local recovery journal still references.

    (Fix 1103) Mirrors _hosted_journal_backup_names for the local journal: a
    present journal means an unresolved local save, so every backup it names
    must survive sweeping — including after a process restart, when the
    in-process transaction lock can no longer protect them.
    """
    journal = _read_local_journal(folder)
    names: set[str] = set()
    backups = journal.get("backups") if isinstance(journal, dict) else None
    if isinstance(backups, dict):
        for backup_name in backups.values():
            if isinstance(backup_name, str) and Path(backup_name).name == backup_name:
                names.add(backup_name)
    return names


def _manifest_identity(manifest: dict) -> str:
    """Cryptographic identity of a manifest: SHA-256 over canonical JSON.

    (Fix 1103, round 5) The recovery promotion predicate compares this identity
    against the identity journaled BEFORE commit(manifest) executed. A match
    proves the NEW manifest (not a stale one) is the committed one; the
    round-4 file-agreement check could not distinguish the two cases.
    """
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def recover_interrupted_cabinet_save(folder: Path, stored_manifest=None) -> dict:
    """Restore cabinet files from an unresolved local recovery journal.

    (Fix 1103) Runs at the start of the next local save, inside the transaction
    lock. ``stored_manifest`` is the manifest currently recorded for the
    folder (the ``previous_manifest`` the new save was given). The journal's
    ``status`` selects the phase:

    - ``"installing"`` / ``"recovery-pending"``: roll back. Every journaled
      backup is moved back over its final target; every installed file that
      never had a backup (a new component from the interrupted save) is
      removed — including names in ``pending_install`` whose install never
      reached the per-install journal update (a kill between temp→final and
      that update). The ``backups`` mapping is immutable — a file listed there
      is a restored-or-restorable original, never a new install, even when its
      backup file is already gone (consumed by an earlier pass). The
      ``installed``/``pending_install`` cleanup therefore skips every name
      present in ``backups``.
    - ``"committed"``: the manifest already committed before the crash — finish
      cleanup only (delete any surviving named backups); never restore old
      bytes over committed output.

    (Fix 1103, round 5) Three-phase journal: a kill after ``commit(manifest)``
    returns but before the ``"committed"`` journal write leaves the durable
    journal at ``"committing"`` with the new manifest's cryptographic identity.
    Before trusting the journal status, recovery compares the stored manifest's
    identity against the journaled identity: only an exact match proves the
    NEW manifest (not a stale one) committed, so recovery runs the cleanup-only
    branch — rolling back would destroy committed output. Any mismatch, missing
    identity, or malformed manifest means the commit cannot be proven and
    recovery rolls back. This also covers a failed ``_clear_local_journal``
    after a successful commit: the stale journal is harmless because identity
    match — not journal status — is the commit authority.

    Recovery is idempotent: a backup that is gone while its target exists was
    consumed by an earlier pass and is skipped, never reported missing. When
    any backup is truly missing (neither backup nor target survives) or any
    step fails, the journal is rewritten — never cleared — and the result
    reports ``settled: False`` so the caller aborts the save with a
    recovery-specific error instead of continuing against a mixed file set.
    """
    folder = Path(folder)
    journal = _read_local_journal(folder)
    if journal is None:
        return {"recovered": False}
    # Round 5 (Fix 1103): promotion requires cryptographic proof. The
    # "committing" journal record holds the new manifest's identity, written
    # durably BEFORE commit(manifest) executed. Only a stored manifest with
    # the identical identity proves the new manifest committed.
    if journal.get("status") == "committing":
        journaled_identity = journal.get("new_manifest_identity")
        if (isinstance(journaled_identity, str) and journaled_identity
                and stored_manifest is not None
                and _manifest_identity(stored_manifest) == journaled_identity):
            # Proven: commit(manifest) executed with exactly this manifest.
            # Cleanup only — never roll back committed output.
            journal = {**journal, "status": "committed"}
        # else: not proven — commit did not execute (or the journal predates
        # it). Fall through to the rollback branch below.
    raw_backups = journal.get("backups")
    backups = raw_backups if isinstance(raw_backups, dict) else {}
    raw_installed = journal.get("installed")
    installed = raw_installed if isinstance(raw_installed, list) else []
    if journal.get("status") == "committed":
        cleaned: list[str] = []
        failed: list[str] = []
        for name, backup_name in backups.items():
            if not isinstance(backup_name, str) or Path(backup_name).name != backup_name:
                failed.append(str(name))
                continue
            try:
                if (folder / backup_name).is_file():
                    (folder / backup_name).unlink()
                    cleaned.append(name)
            except OSError:
                failed.append(str(name))
        if failed:
            remaining = {name: backup_name for name, backup_name in backups.items()
                         if str(name) in failed}
            _write_local_journal(folder, {**journal, "backups": remaining})
            return {"recovered": True, "settled": False, "phase": "committed",
                    "cleaned": cleaned, "failed": failed}
        _clear_local_journal(folder)
        return {"recovered": True, "settled": True, "phase": "committed",
                "cleaned": cleaned, "failed": []}
    restored: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    for name, backup_name in backups.items():
        if not isinstance(name, str) or not isinstance(backup_name, str) \
                or Path(backup_name).name != backup_name:
            failed.append(str(name))
            continue
        try:
            target = _safe_path(folder, name)
        except ValueError:
            failed.append(name)
            continue
        backup = folder / backup_name
        try:
            if backup.is_file():
                os.replace(backup, target)
                restored.append(name)
            elif not target.is_file():
                # Neither the backup nor the original survived: the old bytes
                # are unrecoverable and the save must not continue.
                missing.append(name)
            # else: the backup was already consumed by an earlier pass and the
            # target is in place — nothing to do.
        except OSError:
            failed.append(name)
    removed: list[str] = []
    # Fix 1103 (round 3): pending_install names the new components whose
    # install intent was journaled before the install loop. A kill between a
    # new component's temp→final and its per-install journal update leaves it
    # out of `installed` — without this, recovery would have no record telling
    # it to remove the uncommitted file. Removal is idempotent: a name whose
    # final was never moved simply has no file to remove.
    raw_pending = journal.get("pending_install")
    pending = [n for n in raw_pending if isinstance(n, str)] if isinstance(raw_pending, list) else []
    for name in installed + [n for n in pending if n not in installed]:
        if not isinstance(name, str) or name in backups or name in restored:
            continue
        try:
            target = _safe_path(folder, name)
        except ValueError:
            failed.append(name)
            continue
        try:
            if target.is_file():
                target.unlink()
                removed.append(name)
        except OSError:
            failed.append(name)
    if missing or failed:
        # Unresolved: keep the full immutable mapping plus the restored record
        # so the next attempt retries exactly what is left.
        raw_restored = journal.get("restored")
        prior = set(raw_restored) if isinstance(raw_restored, list) else set()
        _write_local_journal(folder, {
            "status": "recovery-pending",
            "backups": {name: backup_name for name, backup_name in backups.items()
                        if isinstance(backup_name, str)},
            "restored": sorted(prior | set(restored)),
            "installed": [name for name in installed if isinstance(name, str)],
            "pending_install": list(pending),
            "missing_backups": list(missing),
            "failed": list(failed),
        })
        return {"recovered": True, "settled": False, "phase": "rollback",
                "restored": restored, "missing_backups": missing,
                "removed_new": removed, "failed": failed}
    _clear_local_journal(folder)
    return {"recovered": True, "settled": True, "phase": "rollback",
            "restored": restored, "missing_backups": [], "removed_new": removed, "failed": []}


def sweep_cabinet_debris(folder: Path) -> list[str]:
    """Remove orphan app-owned temp/backup files from one Space folder.

    Only ``.wavefinity-cabinet-local-*.3mf`` regular files directly inside the
    folder - the local transaction namespace (Fix 096 A7). Hosted recovery
    backups use a different prefix and can never match; as a second ownership
    check, any backup name referenced by a live hosted recovery journal is
    never deleted. (Fix 1103) A third check: backups named by a live local
    recovery journal are never deleted, so an interrupted local save keeps its
    rollback originals across a process restart until the next save recovers.
    Skipped entirely while any save transaction is active.
    """
    folder = Path(folder)
    if not folder.is_dir() or not _TRANSACTION_LOCK.acquire(blocking=False):
        return []
    removed: list[str] = []
    try:
        # Fix 1103 (Astra AD-002 supplemental): a live local recovery journal
        # means an interrupted local save whose backups must survive until the
        # next save's recovery settles it — including after a process restart.
        protected = _hosted_journal_backup_names(folder) | _local_journal_backup_names(folder)
        for entry in folder.iterdir():
            name = entry.name
            if name in protected:
                continue
            if (name.startswith(CABINET_LOCAL_DEBRIS_PREFIX) and name.lower().endswith(".3mf")
                    and entry.is_file() and not entry.is_symlink()):
                try:
                    entry.unlink()
                    removed.append(name)
                except OSError:
                    pass
    finally:
        _TRANSACTION_LOCK.release()
    return removed


def _previous_owned(folder: Path, previous_manifest) -> dict[str, dict]:
    if previous_manifest is None:
        return {}
    rows = previous_manifest.get("components") if isinstance(previous_manifest, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Previous cabinet manifest is invalid")
    previous: dict[str, dict] = {}
    for item in rows:
        if (not isinstance(item, dict) or not isinstance(item.get("sha256"), str)
                or not isinstance(item.get("filename"), str)):
            raise ValueError("Previous cabinet manifest is invalid")
        path = _safe_path(folder, item["filename"])
        if path.name in previous:
            raise ValueError("Previous cabinet manifest has duplicate filenames")
        previous[path.name] = item
    return previous


def _oriented_parts(component, orientation: str):
    """Body and every object-group mesh rotated together (never mirrored) and
    moved to the print-bed origin."""
    transform = orientation_transform(orientation, flip_up=component.flip_up)
    body = component.mesh.copy()
    body.apply_transform(transform)
    groups = []
    for label, mesh in component.object_groups or ():
        copy = mesh.copy()
        copy.apply_transform(transform)
        groups.append((label, copy))
    low = np.min([one.bounds[0] for one in (body, *(mesh for _label, mesh in groups))], axis=0)
    body.apply_translation(-low)
    for _label, mesh in groups:
        mesh.apply_translation(-low)
    return body, tuple(groups)


def _check_exported_fit(path: Path, profile: dict, name: str) -> None:
    """The written file itself must fit the printer as exported."""
    extents = trimesh.load(path, force="scene").extents
    bed = (profile["x_mm"], profile["y_mm"], profile["z_mm"])
    if any(float(size) > limit + 1e-6 for size, limit in zip(extents, bed)):
        raise RuntimeError(f"{name}: the exported file does not fit the printer profile")


def materialize_storage_drawers(space: dict, output_dir: Path, printer_profile: dict,
                                previous_manifest: dict | None, *, commit=None) -> dict:
    """Write every cabinet file as one transaction.

    ``commit(manifest)`` (local saves) records the manifest in the Space metadata
    while the pre-attempt backups still exist. If staging, installation or the
    commit fails, every installed file is removed and every replaced owned file
    is put back exactly as it was. Backups and obsolete owned files are cleaned
    only after the commit succeeded.
    """
    with _TRANSACTION_LOCK:
        return _materialize(space, Path(output_dir), printer_profile, previous_manifest, commit)


def _materialize(space, folder, printer_profile, previous_manifest, commit) -> dict:
    # Fix 1103 (Astra AD-002 supplemental): an interrupted earlier save may have
    # left a mixed file set whose hashes no longer match the stored manifest.
    # Recover it BEFORE the ownership checks below, or the hash check would
    # refuse the replacement as an outside change. An unsettled recovery aborts
    # the save outright: its journal is preserved for the next attempt.
    # (Fix 1103, round 4) The stored manifest is passed so recovery can close
    # the commit/journal atomicity gap: if its hashes match the files on disk,
    # the previous save's commit demonstrably succeeded and recovery runs
    # cleanup-only even when the journal still says "installing".
    recovery = recover_interrupted_cabinet_save(Path(folder), previous_manifest)
    if recovery.get("recovered") and not recovery.get("settled", True):
        raise RuntimeError(
            "The previous cabinet save was interrupted and its files could not be fully "
            f"recovered (missing backups: {recovery.get('missing_backups') or []}; "
            f"failed: {recovery.get('failed') or []}). The recovery record was kept in "
            f"{LOCAL_CABINET_JOURNAL_NAME}; resolve the underlying file error and retry the save."
        )
    recovery_warnings = []
    if recovery.get("recovered"):
        parts = []
        for name in recovery.get("restored") or []:
            parts.append("restored " + name)
        for name in recovery.get("removed_new") or []:
            parts.append("removed uncommitted " + name)
        if recovery.get("phase") == "committed":
            parts.append("finished cleanup of an already-committed save")
        if parts:
            recovery_warnings.append("Recovered an interrupted cabinet save (" + "; ".join(parts) + ").")
    dry = structural_manifest_plan(space, folder, printer_profile)
    if not dry["fits_printer"]:
        raise ValueError(dry["first_fit_error"] or "Cabinet does not fit printer")
    previous = _previous_owned(folder, previous_manifest)
    desired = [item["filename"] for item in dry["components"]]
    if len(desired) != len(set(desired)):
        raise ValueError("Cabinet component filenames collide")
    for name in desired:
        path = _safe_path(folder, name)
        if path.exists() and (name not in previous or _hash(path) != previous[name]["sha256"]):
            raise ValueError(f"{name} changed outside Wavefinity; rename or move it before updating the cabinet.")
    # All output is staged on the final filesystem before any owned target changes.
    folder.mkdir(parents=True, exist_ok=True)
    plan = resolve_storage_drawers_plan(space, build_meshes=True)
    profile = normalise_printer_profile(printer_profile)
    fits = []
    for component in plan.components:
        fit = component_fit(component.bounds_xyz, component.allowed_orientations, profile)
        if not fit["fits"]:
            raise ValueError(f"{component.display_name}: {fit['reason']}")
        fits.append(fit)
    temporary: dict[str, Path] = {}
    backups: dict[str, Path] = {}
    installed: list[str] = []
    warnings = recovery_warnings + list(plan.warnings)
    committed = False
    recovery_pending = False
    pending_install: list[str] = []
    try:
        for component, item, fit in zip(plan.components, dry["components"], fits):
            fd, name = tempfile.mkstemp(prefix=CABINET_LOCAL_DEBRIS_PREFIX, suffix=".3mf", dir=folder)
            os.close(fd)
            temp = Path(name)
            temporary[item["filename"]] = temp
            if component.mesh is None:
                raise RuntimeError(f"Missing mesh for {component.display_name}")
            body, groups = _oriented_parts(component, fit["orientation"])
            if groups:
                export_text_body_3mf(body, groups, temp, component.display_name)
                validate_3mf(temp, 1 + len(groups), multipart=tuple(label for label, _mesh in groups))
            else:
                export_mesh(body, temp, component.display_name)
                validate_3mf(temp, 1)
            _check_exported_fit(temp, profile, component.display_name)
        # Fix 1103: pre-allocate every backup name and write the durable
        # recovery journal BEFORE the first destructive move. A kill anywhere
        # below then leaves a complete mapping: each moved original has a
        # journaled backup to restore from, and each not-yet-moved original is
        # still in place (its pre-allocated backup name has no file yet, so
        # recovery skips it without reporting it missing).
        for name in desired:
            final = _safe_path(folder, name)
            if final.exists():
                fd, backup_name = tempfile.mkstemp(prefix=CABINET_LOCAL_DEBRIS_PREFIX + "backup-", suffix=".3mf", dir=folder)
                os.close(fd)
                Path(backup_name).unlink()
                backups[name] = Path(backup_name)
        # Fix 1103 (round 3): components with no backup are new installs. Their
        # install intent is journaled BEFORE the install loop: a kill between a
        # new component's temp→final and its per-install journal update would
        # otherwise leave the new final on disk absent from both `backups` and
        # the journaled `installed` list, with nothing telling recovery to
        # remove the uncommitted file.
        pending_install = [name for name in desired if name not in backups]
        _write_local_journal(folder, {
            "status": "installing",
            "backups": {name: backup.name for name, backup in backups.items()},
            "installed": [],
            "pending_install": list(pending_install),
        })
        for name in desired:
            final = _safe_path(folder, name)
            if name in backups:
                os.replace(final, backups[name])
            os.replace(temporary[name], final)
            installed.append(name)
            _write_local_journal(folder, {
                "status": "installing",
                "backups": {name: backup.name for name, backup in backups.items()},
                "installed": list(installed),
                "pending_install": list(pending_install),
            })
        manifest = {"signature": dry["signature"], "generator_version": STRUCTURAL_GENERATOR_VERSION,
                    "components": [{"key": item["key"], "filename": item["filename"],
                                    "sha256": _hash(_safe_path(folder, item["filename"])),
                                    "size": _safe_path(folder, item["filename"]).stat().st_size,
                                    "orientation": fit["orientation"]}
                                   for item, fit in zip(dry["components"], fits)]}
        if commit is not None:
            # Round 5 (Fix 1103): durably journal the commit intent — including
            # the new manifest's cryptographic identity — BEFORE commit(manifest)
            # executes. This write is atomic (temp + replace) and fsynced (file
            # + directory), so a kill at any later point leaves a durable record.
            # Recovery promotes to committed ONLY when the stored manifest's
            # identity matches this journaled identity, proving the NEW manifest
            # (not a stale one) is the committed one.
            _write_local_journal(folder, {
                "status": "committing",
                "new_manifest_identity": _manifest_identity(manifest),
                "backups": {name: backup.name for name, backup in backups.items()},
                "installed": list(installed),
                "pending_install": list(pending_install),
            })
            # The backups still exist here; a failed commit rolls everything back.
            commit(manifest)
        committed = True
        # Fix 1103 (round 3): the committed-phase transition has its own guard.
        # commit(manifest) already succeeded, so a failure in the journal write
        # below must NEVER reach the rollback except above: restoring old bytes
        # over committed output would split files from the committed metadata.
        # (Round 5) If the committed-phase write fails or the process is killed
        # first, the durable "committing" record + identity match still proves
        # the commit: recovery promotes on identity match and runs cleanup-only.
        # Identity match — not the journal's absence — is the commit authority.
        # The write still happens BEFORE the finally below deletes the backups,
        # so the happy path keeps a durable committed-phase record across that
        # window.
        try:
            _write_local_journal(folder, {
                "status": "committed",
                "backups": {name: backup.name for name, backup in backups.items()},
                "installed": list(installed),
                "pending_install": list(pending_install),
            })
        except Exception:
            # Best-effort clear only.
            _clear_local_journal(folder)
    except Exception as save_error:
        # Fix 1103 (Astra AD-002): the backup mapping is never mutated — the
        # journal keeps the complete original mapping plus exactly which files
        # were restored, so a later recovery cannot misclassify a restored
        # file as a new uncommitted install.
        restored: list[str] = []
        restore_error: Exception | None = None
        try:
            for name in reversed(installed):
                final = _safe_path(folder, name)
                if final.exists():
                    final.unlink()
            for name, backup in backups.items():
                if backup.exists():
                    os.replace(backup, _safe_path(folder, name))
                    restored.append(name)
        except Exception as exc:
            restore_error = exc
        if restore_error is not None:
            # A failed restore must NEVER delete the surviving backups — they
            # may be the only remaining copy of the last good output. Keep
            # them, leave a durable recovery record, and let the finally below
            # clean only staging temps.
            recovery_pending = True
            _write_local_journal(folder, {
                "status": "recovery-pending",
                "reason": f"cabinet save failed ({save_error}); rollback restore failed ({restore_error})",
                "backups": {name: backup.name for name, backup in backups.items()},
                "restored": list(restored),
                "installed": list(installed),
                "pending_install": list(pending_install),
            })
            raise RuntimeError(
                "Cabinet save failed and the previous files could not be restored; "
                "the surviving backups were kept and a recovery record was written to "
                f"{LOCAL_CABINET_JOURNAL_NAME}. Retry the save to recover them."
            ) from restore_error
        _clear_local_journal(folder)
        raise
    finally:
        # Staging temps are always safe to clean. Backups are cleaned only when
        # no recovery is pending — never merely because rollback was attempted.
        for path in temporary.values():
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        if not recovery_pending:
            for path in backups.values():
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        pass
    if committed:
        # The new manifest is committed and the backups are gone (finally
        # above); the save is fully settled, so no recovery record remains.
        _clear_local_journal(folder)
        for name, old in previous.items():
            if name in desired:
                continue
            stale = _safe_path(folder, name)
            if stale.exists():
                if _hash(stale) == old["sha256"]:
                    try:
                        stale.unlink()
                    except OSError:
                        warnings.append(f"Could not remove old cabinet file {name}; remove it manually")
                else:
                    warnings.append(f"{name} changed outside Wavefinity; left in place without cabinet ownership")
    return {"files": [_safe_path(folder, name) for name in desired], "manifest": manifest, "warnings": warnings}
