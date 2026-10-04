"""Space setup layered on ordinary Wavefinity save folders.

Every selected folder gets ``.wavefinity.json``. Inventory and Space are
independent: ``inventory`` (default ``true``) is whether generated bins/B4Bs
are logged to ``Wavefinity bins.md``, and ``folder_mode`` is ``design`` or
``space`` depending on whether the folder also represents one physical
Drawer, Storage Box (internal kind ``portable``), Surface, or Pegboard. A Space may also keep its own
sanitized bin-default snapshot. ``folder_mode=space`` always implies
``inventory=true`` - a Space cannot operate without the inventory its layout
depends on. Legacy markers (an old ``design`` marker with no ``inventory``
field, the historical ``no_inventory_folders`` preference,
``.wavefinity-space.json``, and the legacy ``box`` kind) remain readable and
are migrated additively.

A typed Space's permanent identity is ``space_id``, a UUID stored at the top
level of its ``.wavefinity.json`` - never its path, folder name or display
name. The per-user profile keeps a ``space_registry`` (id -> name, kind, last
known folder, last_seen) as an index only; the folder stays authoritative.
"""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_printer_profile import (
    PRINTER_PREF_KEYS,
    apply_printer_profile_to_preferences,
    default_printer_profile_state,
    printer_profile_state,
)
from organizer_inventory import (
    INVENTORY_FILENAME,
    INVENTORY_LOCK,
    configure_space,
    legacy_layout_space,
    load_inventory,
    normalise_space_definition,
    normalise_storage_box,
    resolve_inventory_path,
    storage_drawers_mutate,
)
from organizer_product_rules import SURFACE_TRIM_HEIGHTS, surface_maximums
from organizer_storage_drawers import (
    normalise_storage_drawers_definition,
    prepare_new_storage_drawers_definition,
    reset_storage_drawers_definition,
    storage_drawers_definition_problem,
    storage_drawers_recent_summary,
)

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
from typing import Any, Callable
import uuid
import organizer_storage

from ._core import (
    MAX_RECENT,
    METADATA_FILE,
    LEGACY_METADATA_FILE,
    SPACE_ID_REQUIRED_VERSION,
    RESUME_REQUIRED_VERSION,
    METADATA_VERSION,
    SPACE_SETUP_VERSION,
    SUPPORTED_METADATA_VERSIONS,
    _UNSET,
    FolderMetadataError,
    DuplicateSpaceError,
    DUPLICATE_MESSAGE,
    _INVALID_SPACE_FOLDER_CHARS,
    _RESERVED_SPACE_FOLDER_NAMES,
    _DUPLICATE_SPACE_NAME_MESSAGE,
    _SPACE_CREATE_LOCK,
    _METADATA_WRITE_LOCK,
    SPACE_PARENT_PREFERENCE_KEY,
    STORAGE_RELOCATION_KEY,
    STORAGE_LEFTOVER_KEY,
    _usable_directory,
    saved_parent_unavailable,
    _storage_plan,
    _forget_root_pointers,
    _space_folder_name,
    _new_space_target,
    _cleanup_failed_auto_space,
    _space_id,
    _utc_now,
    _same,
    _json_file,
    _space,
    _repairable_cabinet,
    _cabinet_recovery,
    _explicit_inventory,
    _default_inventory,
    _metadata_space_defaults,
    _metadata_resume,
    _folder_state,
    _identity_state,
    folder_mode,
    inventory_enabled,
    describe,
    _recent_entry,
    _space_registry,
    _read_folder_id,
    _registered_space_entry,
    _recover_registered_space,
    _resolve_registered,
    _check_not_duplicate,
    _metadata_version,
    _output_is_forgotten_typed_space,
    structural_output_manifest,
)

def default_space_parent() -> Path:
    """Where the Wavefinity folder goes when the user never chose a parent.

    The real OS Documents folder (OneDrive-redirected on some Windows setups).
    A Wavefinity folder already established under the old ``~/Documents``
    guess keeps winning until the user moves it, so nothing silently vanishes.
    """
    documents = organizer_storage.documents_folder()
    legacy = (Path.home() / "Documents").resolve()
    if (
        not organizer_storage.same_path(documents, legacy)
        and not (documents / "Wavefinity").is_dir()
        and (legacy / "Wavefinity").is_dir()
    ):
        return legacy
    return documents


def effective_space_parent(prefs: dict[str, Any]) -> Path:
    """The parent directory the *next* auto-created Space will use.

    Resolved fresh from current preferences every time - never captured once
    at server startup - so a Change made during this session affects the very
    next Create New Space without a restart.
    """
    explicit = _usable_directory(prefs.get(SPACE_PARENT_PREFERENCE_KEY))
    if explicit is not None:
        return explicit
    return default_space_parent()


def effective_space_root(prefs: dict[str, Any]) -> Path:
    return effective_space_parent(prefs) / "Wavefinity"


def storage_startup_state(prefs: dict[str, Any]) -> dict[str, Any]:
    """What Welcome needs to show (or not show) the first-run storage card.

    Order (Fix 058 K "Startup decision"):
    1. An explicit, usable saved ``space_parent`` wins - no first-run card.
    2. Otherwise, an already-established default ``Documents/Wavefinity``
       directory means no first-run card either - merely checking this must
       never create that folder.
    3. Otherwise this is the first-run/default-location case.
    """
    unavailable = saved_parent_unavailable(prefs)
    explicit = _usable_directory(prefs.get(SPACE_PARENT_PREFERENCE_KEY)) is not None
    parent = effective_space_parent(prefs)
    root = parent / "Wavefinity"
    first_run = False
    if not explicit and not unavailable:
        first_run = not root.is_dir()
    leftover = str(prefs.get(STORAGE_LEFTOVER_KEY) or "")
    return {
        "parent": str(parent),
        "root": str(root),
        "explicit": explicit,
        "first_run": first_run,
        "unavailable": unavailable,
        "root_exists": not unavailable and root.is_dir(),
        "leftover": leftover if leftover and Path(leftover).is_dir() else None,
    }


def _new_space_id() -> str:
    return str(uuid.uuid4())


def _write_metadata(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
    *, keep_bin_defaults: Any = _UNSET, bin_defaults: Any = _UNSET,
    part_defaults: Any = _UNSET, resume_design: Any = _UNSET, resume_pending: Any = _UNSET,
    preserve_space: bool = False, expected_space_id: str | None = None,
    structural_output_updates: Any = _UNSET,
) -> None:
    # The whole read/preserve/write transaction - including the temp-file
    # replace - is one critical section, so a resume checkpoint write can
    # never race a rename/defaults/version-upgrade write (or another resume
    # write) into the same file and lose either one's fields. Serialization
    # alone is not ownership safety though (Fix 032 Correction 4, C4.1): a
    # caller that captured `space` (or any other field it does not actually
    # own) before acquiring this lock must not have that stale value written
    # back as authoritative. `preserve_space=True` tells this function to use
    # the CURRENT on-disk Space definition - read inside the lock, right
    # now - instead of the caller's `space` argument; `expected_space_id`
    # additionally refuses to write at all if the Space identity has moved
    # on since the caller captured it.
    with _METADATA_WRITE_LOCK:
        payload: dict[str, Any] = {
            "version": METADATA_VERSION,
            "setup_version": SPACE_SETUP_VERSION,
            "folder_mode": mode,
        }
        if mode == "space" and (space or preserve_space):
            payload["space_id"] = _new_space_id()
            saved_keep = True
            saved_defaults = None
            saved_part_defaults: dict[str, Any] = {}
            saved_resume_design: dict[str, Any] | None = None
            saved_resume_pending = False
            saved_space: dict[str, Any] | None = None
            saved_structural: dict[str, Any] = {}
            current_id: str | None = None
            target = folder / METADATA_FILE
            if target.exists():
                current = _json_file(target, strict=True)
                version = current.get("version")
                if isinstance(version, (int, float)) and version > METADATA_VERSION:
                    raise FolderMetadataError("This folder contains Wavefinity metadata from a newer version. The file was left unchanged.")
                if version not in SUPPORTED_METADATA_VERSIONS or current.get("folder_mode") not in {"design", "space"}:
                    raise FolderMetadataError("This folder contains Wavefinity metadata that this version cannot safely read. The file was left unchanged.")
                if current.get("folder_mode") == "space":
                    saved_keep, saved_defaults, saved_part_defaults = _metadata_space_defaults(
                        current, int(version)
                    )
                    saved_resume_design, saved_resume_pending = _metadata_resume(current, int(version))
                    saved_space = _space(current.get("space"))
                    if saved_space is None and _repairable_cabinet(current.get("space")) is not None:
                        # Damaged cabinet settings are preserved byte-for-byte by
                        # every ordinary write; only an explicit reset replaces them.
                        saved_space = current["space"]
                    if isinstance(current.get("structural_outputs"), dict):
                        saved_structural = dict(current["structural_outputs"])
                    # The one choke point that keeps a Space's identity: an
                    # existing valid ID is always preserved. Only pre-v5 metadata
                    # may gain one; damaged v5 must never be re-identified.
                    current_id = _space_id(current.get("space_id"))
                    # v2/v3 are setup inputs: any ID they carry is not trusted.
                    if int(version) >= 4 and current_id is not None:
                        payload["space_id"] = current_id
                    elif int(version) >= SPACE_ID_REQUIRED_VERSION:
                        raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
            # A caller asking to preserve the current Space, or to verify a
            # captured identity, needs an actual current typed Space to read
            # that from - there is nothing to preserve/verify against a
            # brand-new or non-Space file.
            if (preserve_space or expected_space_id is not None) and saved_space is None:
                raise FolderMetadataError("This folder is not the Space that was open before. Nothing was changed.")
            if expected_space_id is not None and current_id != expected_space_id:
                raise FolderMetadataError("This folder is not the Space that was open before. Nothing was changed.")
            resolved_space = saved_space if preserve_space else space
            if not resolved_space:
                raise FolderMetadataError("This folder is not the Space that was open before. Nothing was changed.")
            payload["inventory"] = True
            payload["space"] = resolved_space
            resolved_keep = saved_keep if keep_bin_defaults is _UNSET else bool(keep_bin_defaults)
            resolved_defaults = saved_defaults if bin_defaults is _UNSET else bin_defaults
            resolved_part_defaults = (
                saved_part_defaults if part_defaults is _UNSET else part_defaults
            )
            if resolved_defaults is not None and not isinstance(resolved_defaults, dict):
                raise ValueError("bin defaults must be an object or null")
            if not isinstance(resolved_part_defaults, dict):
                raise ValueError("part defaults must be an object")
            payload["keep_bin_defaults"] = resolved_keep
            payload["bin_defaults"] = resolved_defaults
            payload["part_defaults"] = resolved_part_defaults
            resolved_resume_design = (
                saved_resume_design if resume_design is _UNSET else resume_design
            )
            resolved_resume_pending = (
                saved_resume_pending if resume_pending is _UNSET else resume_pending
            )
            if resolved_resume_design is not None and not isinstance(resolved_resume_design, dict):
                raise ValueError("resume design must be an object or null")
            if not isinstance(resolved_resume_pending, bool):
                raise ValueError("resume pending must be a boolean")
            if resolved_resume_design is None:
                resolved_resume_pending = False
            payload["resume_design"] = resolved_resume_design
            payload["resume_pending"] = resolved_resume_pending
            # Fix 084B: materialized structural-output manifests live beside
            # (never inside) the Space definition and survive every write. An
            # explicit update merges/deletes only its named keys, here, under
            # the same lock as the read above.
            if structural_output_updates is not _UNSET:
                if not isinstance(structural_output_updates, dict):
                    raise ValueError("structural output updates must be an object")
                for key, value in structural_output_updates.items():
                    if value is None:
                        saved_structural.pop(key, None)
                    else:
                        saved_structural[key] = value
            if saved_structural:
                payload["structural_outputs"] = saved_structural
        else:
            payload["inventory"] = bool(inventory)
        target = folder / METADATA_FILE
        temp = folder / f"{METADATA_FILE}.tmp"
        temp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        temp.replace(target)


def _unused_migrate(
    folder: Path, mode: str, space: dict[str, Any] | None = None, inventory: bool = True,
) -> None:
    """Only rewrite metadata that does not already, positively, say what this
    resolves to - so a stale/incomplete record (a "design" marker a legacy
    Space has just outranked, or old "design" metadata silent about
    inventory) migrates once, deterministically, and an already-correct file
    is left untouched."""
    target = folder / METADATA_FILE
    if target.exists():
        try:
            metadata = _json_file(target, strict=True)
            if metadata.get("version") not in (2, METADATA_VERSION):
                return
            if metadata.get("folder_mode") not in {"design", "space"}:
                return
            if metadata.get("folder_mode") == "space" and not _space(metadata.get("space")):
                return
            if metadata.get("version") == 2:
                pass
            elif mode == "space":
                if metadata.get("folder_mode") == "space" and _space(metadata.get("space")) == space:
                    return
                # else: stored "design" (or a differing space) - a legacy
                # identity just took over, fall through and rewrite it.
            elif metadata.get("folder_mode") == "design" and _explicit_inventory(metadata) is not None:
                return
        except FolderMetadataError:
            return
    _write_metadata(folder, mode, space, inventory)


def other_spaces(
    prefs: dict[str, Any], exclude_space_id: str | None = None,
    exclude_folder: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Discover healthy direct-child Spaces without changing folder or profile state."""
    root = effective_space_root(prefs)
    if not root.is_dir():
        return []
    by_id: dict[str, list[dict[str, Any]]] = {}
    try:
        children = root.iterdir()
        for child in children:
            if child.is_symlink() or not child.is_dir():
                continue
            try:
                info = describe(child.resolve(), prefs)
            except (OSError, ValueError):
                continue
            sid = info.get("space_id")
            if (info["folder_mode"] != "space" or not sid or not info.get("space")
                    or info["needs_setup"] or info["needs_identity_migration"]):
                continue
            by_id.setdefault(sid, []).append(_recent_entry(info))
    except OSError:
        return []
    unique = [entries[0] for entries in by_id.values() if len(entries) == 1]
    excluded_id = _space_id(exclude_space_id)
    unique = [entry for entry in unique if not (
        (excluded_id and entry["space_id"] == excluded_id)
        or (not excluded_id and exclude_folder and _same(entry["folder"], exclude_folder))
    )]
    return sorted(unique, key=lambda entry: (entry["name"].casefold(), entry["folder"].casefold()))


def prepare_folder_for_open(target: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    """The narrow technical-maintenance step of opening a folder.

    Read-only classification first; a folder that still needs Fix-004 setup is
    returned untouched. Otherwise: duplicate-copy check, unambiguous inventory
    filename migration, then current metadata (typed Spaces gain/keep their
    ID). It never changes kind, name, dimensions, inventory choice or layout,
    and never touches the profile registry - the caller does that last.
    """
    info = describe(target, prefs)
    if info["needs_setup"]:
        return info
    typed = info["folder_mode"] == "space"
    had_space_id = bool(info.get("space_id"))
    if typed and had_space_id:
        _check_not_duplicate(info["space_id"], target, prefs)
    if info["inventory"]:
        resolve_inventory_path(target, migrate=True)
    if typed and (
        info["needs_identity_migration"]
        or (_metadata_version(target) or 0) < METADATA_VERSION
    ):
        # `info` was read by describe() just above, outside this write's own
        # lock - preserve_space re-reads the current Space definition (and
        # leaving keep/bin/part defaults _UNSET re-reads those too) inside
        # the lock instead of writing back this possibly-stale copy over a
        # concurrent rename/resize (Fix 032 Correction 4, C4.1).
        _write_metadata(target, "space", None, True, preserve_space=True)
    elif not typed and (_metadata_version(target) or METADATA_VERSION) < METADATA_VERSION \
            and (target / METADATA_FILE).exists():
        _write_metadata(target, "design", None, info["inventory"])
    else:
        return info
    info = describe(target, prefs)
    if typed:
        if not info["space_id"]:
            raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")
        if not had_space_id:
            # Final guard for a newly generated ID, before any registry change.
            _check_not_duplicate(info["space_id"], target, prefs)
    return info


def commit_structural_output(
    folder: Path, key: str, manifest: dict[str, Any] | None, *, expected_space_id: str | None,
) -> None:
    """Merge (or delete, with None) one manifest key under the metadata lock."""
    _write_metadata(
        Path(folder), "space", None, True, preserve_space=True,
        expected_space_id=expected_space_id,
        structural_output_updates={key: manifest},
    )


def space_routes(
    default_output: Path,
    load_preferences: Callable[[], dict[str, Any]],
    save_preferences: Callable[[dict[str, Any]], dict[str, Any]],
    mutate_preferences: Callable[[Callable[[dict[str, Any]], Any]], dict[str, Any]] | None = None,
    *,
    space_root: Path | None = None,
) -> dict[str, Callable[[dict], dict]]:
    """Local-folder handlers. Hosted folders remain owned by the browser.

    ``mutate_preferences`` is the atomic read-modify-write the app supplies;
    without it a plain load/save pair stands in.
    """
    fixed_space_root = Path(space_root).expanduser().resolve() if space_root is not None else None

    def current_space_root(prefs: dict[str, Any]) -> Path:
        # Fix 058 K: resolved fresh from current preferences at create time,
        # never captured once - a Change during this session must affect the
        # very next Create New Space without a restart. An explicit
        # ``space_root`` constructor override (used by callers that want a
        # fixed root) still wins over the preference.
        if fixed_space_root is not None:
            return fixed_space_root
        return effective_space_root(prefs)

    if mutate_preferences is None:
        def mutate_preferences(mutator):
            prefs = load_preferences()
            result = mutator(prefs)
            return save_preferences(result if isinstance(result, dict) else prefs)

    def folder(payload: dict[str, Any]) -> Path:
        return Path(str(payload.get("output") or default_output)).expanduser().resolve()

    def path_recents(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        saved = prefs.get("recent_folders")
        if not isinstance(saved, list):
            saved = prefs.get("recent_spaces") or []
        return [one for one in saved if isinstance(one, dict) and one.get("folder")]

    def recent(prefs: dict[str, Any]) -> list[dict[str, Any]]:
        registry = _space_registry(prefs)
        saved = path_recents(prefs)
        active = _space_id(prefs.get("active_space_id"))
        absorbed: dict[str, dict[str, Any]] = {}
        repairs: dict[str, dict[str, Any]] = {}

        # Legacy path-based entries that already carry an ID move into the
        # registry; ones without an ID stay shortcuts until upgraded.
        kept_paths = []
        for one in saved:
            try:
                info = describe(Path(one["folder"]), prefs)
            except ValueError:
                kept_paths.append(one)
                continue
            sid = info["space_id"]
            if info["folder_mode"] == "space" and sid:
                if sid not in registry:
                    registry[sid] = absorbed[sid] = _registered_space_entry(
                        info, one.get("last_seen") or None,
                    )
            else:
                kept_paths.append(one)

        items: list[tuple[str | None, dict[str, Any]]] = []
        for sid, entry in list(registry.items()):
            stamp = entry.get("last_seen")
            recorded = Path(str(entry.get("folder") or ""))
            base = {
                "folder": str(recorded), "name": entry.get("name") or recorded.name,
                "folder_mode": "space", "space_id": sid,
                "kind": entry.get("kind"), "size": None,
            }
            try:
                found = _resolve_registered(sid, entry)
            except DuplicateSpaceError as error:
                items.append((stamp, {**base, "missing": False, "invalid": True, "conflict": True, "error": str(error)}))
                continue
            if found is None:
                items.append((stamp, {**base, "missing": True}))
                continue
            try:
                info = describe(found, prefs)
            except ValueError:
                items.append((stamp, {**base, "folder": str(found), "missing": False, "invalid": True}))
                continue
            # Folder metadata wins over the cached name/kind/path.
            fresh = {
                key: value for key, value in _registered_space_entry(info, "").items()
                if key != "last_seen" and value
            }
            if any(entry.get(key) != value for key, value in fresh.items()):
                repairs[sid] = fresh
            items.append((stamp, _recent_entry(info)))

        if repairs or absorbed:
            def apply(current: dict[str, Any]) -> None:
                reg = _space_registry(current)
                for sid, entry in absorbed.items():
                    reg.setdefault(sid, entry)
                for sid, fresh in repairs.items():
                    if sid in reg:
                        reg[sid] = {**reg[sid], **fresh}
                        if sid == active and _space_id(current.get("active_space_id")) == sid:
                            current["output"] = fresh["folder"]
                current["space_registry"] = reg
                if absorbed:
                    current["recent_folders"] = [
                        one for one in path_recents(current)
                        if not any(_same(one.get("folder"), e["folder"]) for e in absorbed.values())
                    ]
            mutate_preferences(apply)

        for one in kept_paths:
            target = Path(one["folder"])
            try:
                entry = _recent_entry(describe(target, prefs))
            except ValueError:
                entry = {
                    "folder": str(target),
                    "name": one.get("name") or target.name,
                    "folder_mode": one.get("folder_mode"),
                    "space_id": None,
                    "kind": one.get("kind"),
                    "size": one.get("size"),
                    "missing": not target.is_dir(),
                    "invalid": True,
                }
            items.append((one.get("last_seen"), entry))

        # Newest first; legacy entries with no timestamp keep their order.
        stamped = sorted((x for x in items if x[0]), key=lambda x: x[0], reverse=True)
        plain = [x for x in items if not x[0]]
        return [entry for _stamp, entry in [*stamped, *plain]][:MAX_RECENT]

    def reply(target: Path | None) -> dict[str, Any]:
        prefs = load_preferences()
        info = describe(target, prefs) if target else None
        return {
            "folder": info,
            "space": info,
            "recent": recent(prefs),
        }

    def remember_or_warn(target: Path, action: str) -> dict[str, Any]:
        """Fix 096 A3: a failed remember() is a different failure class from a
        failed Space write. The Space files committed successfully, so the
        valid Space is preserved and the failure is reported truthfully -
        never as a failed create/update, and never by rolling back valid
        Space files merely because the convenience pointer failed."""
        try:
            remember(target)
        except Exception:
            result = reply(target)
            result["remember_warning"] = (
                f"The Space was {action}, but it could not be remembered as "
                "the current Space. Open it again from the Space list."
            )
            return result
        return reply(target)

    def remember_prepared(target: Path, info: dict[str, Any]) -> None:
        """Advance the profile last: only after folder maintenance succeeded."""
        stamp = _utc_now()
        typed = info["folder_mode"] == "space"
        space_id = info["space_id"]
        if typed and not space_id:
            raise FolderMetadataError("This folder's Space information is incomplete or damaged. Nothing was changed.")

        def apply(prefs: dict[str, Any]) -> None:
            others = [
                one for one in path_recents(prefs) if not _same(one.get("folder"), target)
            ]
            prefs["output"] = str(target)
            if typed:
                registry = _space_registry(prefs)
                registry[space_id] = _registered_space_entry(info, stamp)
                prefs["space_registry"] = registry
                prefs["active_space_id"] = space_id
                prefs["recent_folders"] = others[:MAX_RECENT]
            else:
                prefs["active_space_id"] = None
                prefs["recent_folders"] = [
                    {**_recent_entry(info), "last_seen": stamp}, *others,
                ][:MAX_RECENT]

        mutate_preferences(apply)

    def remember(target: Path) -> dict[str, Any]:
        info = prepare_folder_for_open(target, load_preferences())
        if info["needs_setup"]:
            raise ValueError("this folder must complete Space setup before it can be opened")
        remember_prepared(target, info)
        return info

    def startup(_payload):
        recover_relocation()
        prefs = load_preferences()
        # Fix 058 K: resolved once per startup call so the frontend never has
        # to reproduce filesystem heuristics - it only needs to know whether
        # to show the first-run storage card and what path it should read.
        storage = storage_startup_state(prefs)
        def welcome_spaces(current: dict[str, Any], active_folder: Path | None = None) -> list[dict[str, Any]]:
            return other_spaces(
                current, _space_id(current.get("active_space_id")),
                active_folder or current.get("output"),
            )
        target: Path | None = None
        space_id = _space_id(prefs.get("active_space_id"))
        if space_id:
            entry = _space_registry(prefs).get(space_id)
            try:
                target = _resolve_registered(space_id, entry) if entry else None
            except DuplicateSpaceError:
                target = None
            if target is not None and not _same(target, (entry or {}).get("folder") or ""):
                def repair(current: dict[str, Any]) -> None:
                    registry = _space_registry(current)
                    if space_id in registry:
                        registry[space_id]["folder"] = str(target)
                        current["space_registry"] = registry
                        current["output"] = str(target)
                mutate_preferences(repair)
        elif prefs.get("output"):
            target = Path(str(prefs["output"])).expanduser()
        if target is None or not target.is_dir():
            current = load_preferences()
            return {"folder": None, "space": None, "recent": recent(current), "storage": storage,
                    "other_spaces": welcome_spaces(current)}
        target = target.resolve()
        if not space_id and _output_is_forgotten_typed_space(target, prefs):
            current = load_preferences()
            return {"folder": None, "space": None, "recent": recent(current), "storage": storage,
                    "other_spaces": welcome_spaces(current)}
        info = describe(target, prefs)
        if not info["needs_setup"]:
            info = prepare_folder_for_open(target, prefs)
            if not info["needs_setup"]:
                remember_prepared(target, info)
        current = load_preferences()
        return {"folder": info, "space": info, "recent": recent(current), "storage": storage,
                "other_spaces": welcome_spaces(current, target)}

    def other_spaces_route(_payload):
        prefs = load_preferences()
        return {"other_spaces": other_spaces(
            prefs, _space_id(prefs.get("active_space_id")), prefs.get("output"),
        )}

    def inspect(payload):
        return reply(folder(payload))

    def use_folder(payload):
        # The explicit "use this folder without a Space type" choice. May
        # write v5/setup_version-1 Design metadata, but must never demote a
        # folder already classified as a Space - fully configured *or* still
        # needing its one-time setup pass. A Space that needs setup must go
        # through the explicit migration/setup flow instead, never straight
        # to Design - see Fix 004 Correction 8.B. Opening/remembering a
        # folder without changing it is /api/space/open (open_folder) /
        # /api/folder/use, not this.
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        (mode, space, inventory, _keep, _defaults, _part_defaults,
         needs_setup, source, _prefill) = _folder_state(target, load_preferences())
        # Only an authoritative typed Space is protected. An inventory-only or
        # inferred candidate is old Wavefinity content, not a committed type,
        # so the explicit exploration choice may commit Design metadata over
        # it - without deleting the inventory/layout it came from.
        if mode == "space" and source in {"metadata", "legacy_metadata"}:
            raise ValueError(f"this folder already holds the space {(space or {}).get('name')!r}")
        if needs_setup or mode != "design":
            _write_metadata(target, "design", None, inventory)
        remember(target)
        return reply(target)

    def configure(payload):
        raw_def = {
            "name": payload.get("name"),
            "kind": payload.get("kind"),
            "x": payload.get("x"),
            "y": payload.get("y"),
            "z": payload.get("z"),
        }
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]
        for key in ("max_x_mm", "max_y_mm"):
            if key in payload:
                raw_def[key] = payload[key]
        for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
            if key in payload:
                raw_def[key] = payload[key]

        auto_created = not payload.get("output")

        if auto_created:
            prefs_for_create = load_preferences()
            # Fix 058 Correction 1, C1.2: an explicit saved space_parent that is
            # no longer usable must block automatic Create rather than silently
            # falling back to Documents. The saved preference is left untouched
            # - only Change (via the Welcome repair state) may update it. A
            # brand-new user with no explicit space_parent is unaffected and
            # still gets the ordinary Documents default.
            if fixed_space_root is None and saved_parent_unavailable(prefs_for_create):
                raise ValueError(
                    "Your saved Space storage location is unavailable. "
                    "Use Change on Welcome to choose a folder."
                )
            # Validate the exact folder/display name before normalise_space_definition()
            # can apply its legacy 80-character truncation behavior.
            folder_name = _space_folder_name(raw_def["name"])
            raw_def["name"] = folder_name
            if raw_def.get("kind") == "storage_drawers":
                raw_def = prepare_new_storage_drawers_definition(raw_def)
            validated = normalise_space_definition(raw_def)
            target = _new_space_target(current_space_root(prefs_for_create), folder_name)
            try:
                result = configure_space(target, raw_def=validated, mode="create")
                space = result["layout"]["space"]
                _write_metadata(target, "space", space, keep_bin_defaults=True)
            except Exception:
                _cleanup_failed_auto_space(target)
                raise

            # A preference/registry write failure must not delete an already-valid
            # Space folder; the folder remains authoritative and recoverable.
            # Fix 096 A3: report it truthfully, never as a failed create.
            return remember_or_warn(target, "created")

        # Explicit-output callers keep the current create behavior.
        target = folder(payload)
        target.mkdir(parents=True, exist_ok=True)
        # Fix 096 A3: the Inventory layout.space write and the metadata write
        # are one logical commit - snapshot the prior Inventory so a metadata
        # failure restores it (a brand-new folder is cleaned up instead),
        # never leaving a half-applied new Space behind a reported failure.
        with INVENTORY_LOCK:
            inventory_path = resolve_inventory_path(target, migrate=True)
            prior_inventory = inventory_path.read_bytes() if inventory_path.is_file() else None
            try:
                result = configure_space(target, raw_def=raw_def, mode="create")
                space = result["layout"]["space"]
                _write_metadata(target, "space", space, keep_bin_defaults=True)
            except Exception:
                if prior_inventory is not None:
                    try:
                        inventory_path.write_bytes(prior_inventory)
                    except OSError as restore_error:
                        # Fix 096 A3: a failed restore is a partial commit, not
                        # a clean failure - say so explicitly instead of
                        # reporting the original error while the new Inventory
                        # may still be durable.
                        raise RuntimeError(
                            "The Space could not be created, and the previous "
                            "Inventory could not be restored either. The "
                            "Inventory may have changed - reopen the Space and "
                            "check it before continuing."
                        ) from restore_error
                else:
                    _cleanup_failed_auto_space(target)
                raise
        return remember_or_warn(target, "created")

    def configure_migrate(payload):
        # The user's explicit Configure Existing / migration choice for an
        # already-selected folder: a v2/v3/legacy/inventory-derived Space, or
        # a plain design/inventory folder. Never rejected merely because
        # layout.space already exists - configure_space(mode="update")
        # replaces the Space definition in place and preserves everything
        # else (inventory rows, quantities, placements, drawers, generated
        # parts). Existing keep_bin_defaults/bin_defaults are preserved
        # rather than reset. allow_legacy=True lets this path read a legacy
        # "box" kind during migration, but the actual persisted kind is
        # whatever the setup form chose (always "portable", never a new
        # "box" - see Fix 004 Correction 7.H).
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("save folder not found")
        (_mode, _space, inventory, _keep, _defaults, _part_defaults,
         _needs_setup, _source, _prefill) = _folder_state(target, load_preferences())
        raw_def = {"name": payload.get("name"), "kind": payload.get("kind"), "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]
        for key in ("max_x_mm", "max_y_mm"):
            if key in payload:
                raw_def[key] = payload[key]
        for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
            if key in payload:
                raw_def[key] = payload[key]

        # Fix 096 A3: the Inventory layout.space write and the metadata write
        # are one logical commit - snapshot the prior Inventory so a metadata
        # failure restores it instead of leaving a half-applied migration.
        with INVENTORY_LOCK:
            inventory_path = resolve_inventory_path(target, migrate=True)
            prior_inventory = inventory_path.read_bytes() if inventory_path.is_file() else None
            try:
                result = configure_space(target, raw_def=raw_def, mode="update", allow_legacy=True)
                space = result["layout"]["space"]
                # This route owns the new Space definition (just written above by
                # configure_space), but not keep_bin_defaults/bin_defaults/
                # part_defaults - leaving those _UNSET lets _write_metadata() read
                # the newest under-lock value instead of writing back this
                # possibly-stale pre-lock copy (Fix 032 Correction 4, C4.1).
                _write_metadata(target, "space", space, inventory)
            except Exception:
                if prior_inventory is not None:
                    try:
                        inventory_path.write_bytes(prior_inventory)
                    except OSError as restore_error:
                        # Fix 096 A3: a failed restore is a partial commit, not
                        # a clean failure - say so explicitly instead of
                        # reporting the original error while the new Inventory
                        # may still be durable.
                        raise RuntimeError(
                            "The Space could not be updated, and the previous "
                            "Inventory could not be restored either. The "
                            "Inventory may have changed - reopen the Space and "
                            "check it before continuing."
                        ) from restore_error
                raise
        return remember_or_warn(target, "updated")

    def update(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("save folder not found")
        (mode, existing_space, _inventory, _keep, _defaults, _part_defaults,
         needs_setup, _source, _prefill) = _folder_state(target, load_preferences())
        if mode != "space":
            raise ValueError("not a typed space")

        raw_def = {"name": payload.get("name"), "kind": existing_space["kind"], "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z")}
        if "trim_size" in payload:
            raw_def["trim_size"] = payload["trim_size"]
        for key in ("max_x_mm", "max_y_mm"):
            if key in payload:
                raw_def[key] = payload[key]
        for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
            if key in payload:
                raw_def[key] = payload[key]

        # Fix 095/096 A3: an edit is validated before either write (inside
        # configure_space) and never left half applied: if the metadata write
        # fails after the Inventory was replaced, the prior Inventory is put
        # back. Applies to every Space kind, not just Surface.
        with INVENTORY_LOCK:
            inventory_path = resolve_inventory_path(target, migrate=True)
            prior_inventory = (
                inventory_path.read_bytes()
                if inventory_path.is_file() else None
            )
            result = configure_space(target, raw_def=raw_def, mode="update")
            space = result["layout"]["space"]
            # This route owns the new Space definition, but not the bin/part
            # defaults - leave them _UNSET so _write_metadata() preserves the
            # newest under-lock value rather than this possibly-stale pre-lock
            # copy (Fix 032 Correction 4, C4.1).
            try:
                _write_metadata(target, "space", space)
            except Exception:
                if prior_inventory is not None:
                    try:
                        inventory_path.write_bytes(prior_inventory)
                    except OSError as restore_error:
                        # Fix 096 A3: a failed restore is a partial commit, not
                        # a clean failure - say so explicitly instead of
                        # reporting the original error while the new Inventory
                        # may still be durable.
                        raise RuntimeError(
                            "The Space could not be updated, and the previous "
                            "Inventory could not be restored either. The "
                            "Inventory may have changed - reopen the Space and "
                            "check it before continuing."
                        ) from restore_error
                raise
        return remember_or_warn(target, "updated")

    def set_inventory(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        prefs = load_preferences()
        (mode, space, _current, _keep, _defaults, _part_defaults,
         _needs_setup, _source, _prefill) = _folder_state(target, prefs)
        inventory = bool(payload.get("inventory", True))
        if mode == "space" and not inventory:
            raise ValueError("Space planning needs this folder's inventory turned on.")
        # A typed Space owns nothing here but `inventory` (which a Space
        # ignores anyway - it is always forced true) - preserve its current
        # Space definition and bin/part defaults from under the lock rather
        # than this route's pre-lock captures (Fix 032 Correction 4, C4.1).
        # An untyped design folder has no Space to preserve.
        if mode == "space":
            _write_metadata(target, mode, None, inventory, preserve_space=True)
        else:
            _write_metadata(target, mode, space, inventory)
        # Keep the legacy preference in step, in case anything still reads it.
        kept = [
            one for one in (prefs.get("no_inventory_folders") or [])
            if not _same(one, target)
        ]
        if not inventory:
            kept.append(str(target))
        save_preferences({"no_inventory_folders": kept})
        remember(target)
        return reply(target)

    def set_bin_defaults(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        (mode, _space, inventory, _keep, _defaults, _part_defaults,
         _needs_setup, _source, _prefill) = _folder_state(target, load_preferences())
        if mode != "space":
            raise ValueError("bin defaults belong to a Space folder")
        # Pass an explicit value only for a field this request is actually
        # changing; an absent field stays _UNSET so _write_metadata()
        # preserves the newest under-lock value instead of this route's
        # pre-lock capture of it (Fix 032 Correction 4, C4.1).
        write_kwargs: dict[str, Any] = {}
        if "keep_bin_defaults" in payload:
            write_kwargs["keep_bin_defaults"] = bool(payload["keep_bin_defaults"])
        if "bin_defaults" in payload:
            new_defaults = payload.get("bin_defaults")
            if new_defaults is not None and not isinstance(new_defaults, dict):
                raise ValueError("bin defaults must be an object or null")
            write_kwargs["bin_defaults"] = new_defaults
        if "part_defaults" in payload:
            new_part_defaults = payload.get("part_defaults")
            if not isinstance(new_part_defaults, dict):
                raise ValueError("part defaults must be an object")
            write_kwargs["part_defaults"] = new_part_defaults
        # A client that names the Space it queued this write for is refused
        # if the folder now holds a different Space.
        expected_space_id = None
        if payload.get("space_id"):
            expected_space_id = _space_id(payload.get("space_id"))
            if not expected_space_id:
                raise ValueError("space_id must be a valid Space ID")
        _write_metadata(
            target, mode, None, inventory, preserve_space=True,
            expected_space_id=expected_space_id, **write_kwargs,
        )
        remember(target)
        return reply(target)

    def resume(payload):
        # The local-server counterpart to hosted SP.writeMetadata(): persists
        # the exact editor design a typed Space should reopen to. It never
        # touches inventory, bin/part defaults, or Space identity, and never
        # builds a design from inventory rows - see Fix 032. It never rolls
        # back a concurrent rename/resize either (Correction 4, C4.1):
        # preserve_space re-reads the CURRENT Space definition from under
        # _write_metadata()'s own lock instead of writing back whatever was
        # captured here before it, and expected_space_id refuses to write at
        # all if the Space this checkpoint was queued for is no longer the
        # one on disk - the client must name which Space it means.
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        (mode, _space, _inventory, _keep, _defaults, _part_defaults,
         _needs_setup, _source, _prefill) = _folder_state(target, load_preferences())
        if mode != "space":
            raise ValueError("resume checkpoints belong to a Space folder")
        expected_space_id = _space_id(payload.get("space_id"))
        if not expected_space_id:
            raise ValueError("a resume checkpoint must name the Space it belongs to")
        resume_design = payload.get("resume_design")
        resume_pending = payload.get("resume_pending")
        if resume_design is not None and not isinstance(resume_design, dict):
            raise ValueError("resume design must be an object or null")
        if not isinstance(resume_pending, bool):
            raise ValueError("resume pending must be a boolean")
        _write_metadata(
            target, mode, None, True,
            resume_design=resume_design, resume_pending=resume_pending,
            preserve_space=True, expected_space_id=expected_space_id,
        )
        return reply(target)

    def open_folder(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        remember(target)
        return reply(target)

    def forget(payload):
        # Removes only the profile shortcut; the folder, its metadata, its
        # inventory and its Space ID are never touched.
        space_id = _space_id(payload.get("space_id"))
        target = folder(payload) if payload.get("output") else None

        def apply(prefs: dict[str, Any]) -> None:
            if space_id:
                registry = _space_registry(prefs)
                if registry.pop(space_id, None) is not None:
                    prefs["space_registry"] = registry
                if _space_id(prefs.get("active_space_id")) == space_id:
                    prefs["active_space_id"] = None
            elif target is not None:
                registry = _space_registry(prefs)
                for key, entry in list(registry.items()):
                    if _same(entry.get("folder") or "", target):
                        del registry[key]
                        if _space_id(prefs.get("active_space_id")) == key:
                            prefs["active_space_id"] = None
                if "space_registry" in prefs:
                    prefs["space_registry"] = registry
            if target is not None:
                prefs["recent_folders"] = [
                    one for one in path_recents(prefs)
                    if not _same(one.get("folder"), target)
                ]

        mutate_preferences(apply)
        return reply(None)

    def set_storage_parent(payload):
        # Fix 058 K: saves only the selected *parent* directory - never
        # creates its Wavefinity child, and never overwrites an existing
        # explicit custom parent merely because Documents/Wavefinity also
        # exists (this is only reached by an explicit Change/save call).
        raw = payload.get("parent")
        if not raw:
            raise ValueError("Choose a folder for Wavefinity's Space storage.")
        candidate = Path(str(raw)).expanduser()
        try:
            usable = candidate.is_dir()
        except OSError:
            usable = False
        if not usable:
            raise ValueError("That folder could not be found. Choose an existing folder.")
        absolute = candidate.resolve()

        def apply(prefs: dict[str, Any]) -> None:
            prefs[SPACE_PARENT_PREFERENCE_KEY] = str(absolute)

        prefs = mutate_preferences(apply)
        return {"storage": storage_startup_state(prefs)}

    def storage_state(_payload):
        recover_relocation()
        return {"storage": storage_startup_state(load_preferences())}

    def storage_plan(payload):
        prefs = load_preferences()
        plan = _storage_plan(prefs, payload.get("parent"), current_space_root(prefs))
        return {"plan": plan, "storage": storage_startup_state(prefs)}

    def journal_relocation(record):
        def apply(prefs: dict[str, Any]) -> None:
            if record is None:
                prefs.pop(STORAGE_RELOCATION_KEY, None)
            else:
                prefs[STORAGE_RELOCATION_KEY] = record
        mutate_preferences(apply)

    def commit_storage(
        old_root: Path, new_root: Path, *, moved: bool, leftover: Path | None = None,
    ) -> None:
        """The one atomic preference write that makes a new root official."""
        def apply(prefs: dict[str, Any]) -> None:
            # The journal holds the old path, so it goes before the path rewrite.
            prefs.pop(STORAGE_RELOCATION_KEY, None)
            if moved:
                organizer_storage.rebase_value(prefs, old_root, new_root)
            else:
                _forget_root_pointers(prefs, old_root)
            prefs[SPACE_PARENT_PREFERENCE_KEY] = str(new_root.parent)
            if leftover is not None:
                prefs[STORAGE_LEFTOVER_KEY] = str(leftover)
        mutate_preferences(apply)

    def clear_leftover() -> None:
        def apply(prefs: dict[str, Any]) -> None:
            prefs.pop(STORAGE_LEFTOVER_KEY, None)
        mutate_preferences(apply)

    def recover_relocation() -> None:
        """Resolve a relocation a crash or restart interrupted to exactly one root.

        Waits out any move still running in this process (same locks), so it
        can never mistake a live copy for a dead one.
        """
        with _SPACE_CREATE_LOCK, _METADATA_WRITE_LOCK:
            prefs = load_preferences()
            leftover = prefs.get(STORAGE_LEFTOVER_KEY)
            if leftover and not Path(str(leftover)).is_dir():
                clear_leftover()
            record = prefs.get(STORAGE_RELOCATION_KEY)
            if record is None:
                return
            src_raw = record.get("src") if isinstance(record, dict) else None
            dst_raw = record.get("dst") if isinstance(record, dict) else None
            if not src_raw or not dst_raw:
                journal_relocation(None)
                return
            src, dst = Path(str(src_raw)), Path(str(dst_raw))
            if src.is_dir():
                # The old root is intact, so it stays authoritative; only our
                # own partial copy is discarded. A finished copy at ``dst`` is
                # left alone and reported as a conflict if it is ever chosen.
                organizer_storage.remove_stale_staging(record.get("staging"), dst.parent)
                if dst.is_dir():
                    # A copy reached its final place before the switch was
                    # committed. Ownership/completeness can't be proven, so
                    # neither tree is touched; the extra one is reported.
                    def keep_and_report(prefs: dict[str, Any]) -> None:
                        prefs.pop(STORAGE_RELOCATION_KEY, None)
                        prefs[STORAGE_LEFTOVER_KEY] = str(dst)
                    mutate_preferences(keep_and_report)
                else:
                    journal_relocation(None)
            elif dst.is_dir():
                commit_storage(src, dst, moved=True)  # the rename finished; finish the switch
            else:
                journal_relocation(None)

    def change_storage(payload):
        """Change Location: Move existing data / Use new location / Use existing.

        Order is fixed: validate everything, bring the data across, then one
        atomic preference write. Nothing durable points at the new root until
        it is complete, and the old root is never removed before that write.
        """
        if fixed_space_root is not None:
            raise ValueError("This session's Wavefinity folder is fixed.")
        mode = payload.get("mode")
        if mode not in {"move", "switch", "use_existing"}:
            raise ValueError("Choose how to change the Wavefinity folder.")

        def done(leftover: str | None = None) -> dict[str, Any]:
            return {
                "status": "ok", "leftover": leftover,
                "storage": storage_startup_state(load_preferences()),
            }

        with _SPACE_CREATE_LOCK, _METADATA_WRITE_LOCK:
            prefs = load_preferences()
            old_root = current_space_root(prefs)
            plan = _storage_plan(prefs, payload.get("parent"), old_root)
            new_root = Path(plan["root"])
            if plan["same"]:
                return {"status": "unchanged", "storage": storage_startup_state(prefs)}

            if mode == "use_existing":
                if not new_root.is_dir():
                    raise ValueError("There is no Wavefinity folder in that location to use.")
                commit_storage(old_root, new_root, moved=False)
                return done()

            if plan["conflict"]:
                return {"status": "conflict", "root": plan["root"], "storage": storage_startup_state(prefs)}

            if mode == "move" and plan["source_exists"]:
                kind, expected = organizer_storage.transfer_tree(old_root, new_root, journal_relocation)
                try:
                    commit_storage(
                        old_root, new_root, moved=True,
                        leftover=old_root if kind == "copied" else None,
                    )
                except Exception as error:
                    organizer_storage.undo_transfer(old_root, new_root, kind)
                    try:
                        journal_relocation(None)
                    except Exception:
                        pass
                    raise ValueError(
                        "Wavefinity could not save the new location. "
                        "Nothing was changed and your current folder is still in use."
                    ) from error
                if kind == "copied":
                    if organizer_storage.discard_old_tree(old_root, expected):
                        clear_leftover()
                    else:
                        return done(str(old_root))
                return done()

            try:
                new_root.mkdir(exist_ok=True)
            except OSError as error:
                raise ValueError(
                    "Wavefinity could not create its folder there. Choose another location."
                ) from error
            commit_storage(old_root, new_root, moved=False)
            return done()

    def printer_profile_route(payload):
        if payload.get("reset") is True:
            # One-click recovery: only the printer-profile keys go back to defaults.
            def clear(prefs: dict[str, Any]) -> None:
                for key in PRINTER_PREF_KEYS:
                    prefs.pop(key, None)
            return printer_profile_state(mutate_preferences(clear))
        raw = payload.get("profile")
        if raw is None:
            try:
                return printer_profile_state(load_preferences())
            except ValueError:
                return default_printer_profile_state(
                    "Printer Settings could not be read. Choose Reset Printer Settings to use the defaults.")
        update = apply_printer_profile_to_preferences({}, raw)

        def apply(prefs: dict[str, Any]) -> None:
            prefs.update(update)
        return printer_profile_state(mutate_preferences(apply))

    def storage_drawers_mutate_route(payload):
        target = folder(payload)
        if not target.is_dir():
            raise ValueError("that save folder could not be found")
        prefs = load_preferences()
        info = describe(target, prefs)
        space = info.get("space")
        if info["folder_mode"] != "space" or not isinstance(space, dict) or space.get("kind") != "storage_drawers":
            raise ValueError("This folder is not a Storage Drawers Space.")
        expected = _space_id(payload.get("space_id"))
        if expected is None or info["space_id"] != expected:
            raise ValueError("This folder is not the Space that was open before. Nothing was changed.")
        operation = str(payload.get("operation") or "")
        recovery = info.get("cabinet_recovery")
        if recovery and operation != "reset":
            raise ValueError(f"Reset cabinet settings before changing the cabinet. {recovery['message']}")
        if operation == "reset" and not recovery:
            raise ValueError("The cabinet settings are not damaged.")
        # One semantic transaction: the rollback snapshot, the mutation, the
        # metadata commit and any rollback all sit inside the Inventory lock, so
        # a rollback can never overwrite newer Inventory work.
        with INVENTORY_LOCK:
            path = resolve_inventory_path(target, migrate=True)
            before = path.read_text(encoding="utf-8") if path.is_file() else None
            result = storage_drawers_mutate(
                target, operation, drawer_id=payload.get("drawer_id"),
                proposed=payload.get("space"), space=space,
            )
            try:
                _write_metadata(target, "space", result["space"], expected_space_id=expected)
            except Exception:
                # The typed definition stays authoritative: put the Inventory back.
                if before is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(before, encoding="utf-8")
                raise
        remember(target)
        return result

    return {
        "/api/space/inspect": inspect,
        # Local startup: resolves the active Space by ID, not just a path.
        "/api/space/startup": startup,
        "/api/space/other-spaces": other_spaces_route,
        # Open/remember only - never changes mode or rewrites metadata
        # beyond the technical identity/inventory upgrades in remember().
        "/api/folder/use": open_folder,
        # The explicit "use without a Space type" choice - may write.
        "/api/space/use-untyped": use_folder,
        "/api/space/create": configure,
        "/api/space/configure": configure_migrate,
        "/api/space/update": update,
        "/api/folder/inventory": set_inventory,
        "/api/space/defaults": set_bin_defaults,
        "/api/space/resume": resume,
        "/api/space/open": open_folder,
        "/api/space/no-inventory": lambda payload: set_inventory({**payload, "inventory": False}),
        "/api/space/forget": forget,
        "/api/space/storage-parent": set_storage_parent,
        "/api/space/storage-state": storage_state,
        "/api/space/storage-plan": storage_plan,
        "/api/space/storage-change": change_storage,
        "/api/space/printer-profile": printer_profile_route,
        "/api/space/storage-drawers-mutate": storage_drawers_mutate_route,
    }
