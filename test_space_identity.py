"""Fix 006: portable Space identity, registry, canonical inventory, profile prefs."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import uuid

import wavefinity_web
from organizer_inventory import (
    INVENTORY_FILENAME,
    InventoryMigrationError,
    append_bin,
    configure_space,
    load_inventory,
    resolve_inventory_path,
    save_inventory,
)
from organizer_spaces import DuplicateSpaceError, MAX_RECENT, space_routes

V4 = {
    "version": 4, "setup_version": 1, "folder_mode": "space", "inventory": True,
    "space": {"kind": "drawer", "name": "Vanity", "x": 320, "y": 240, "z": 55},
    "keep_bin_defaults": True, "bin_defaults": {"marker": 1},
}


def make_routes(tmp: Path):
    prefs: dict = {}

    def load():
        return copy.deepcopy(prefs)

    def save(update):
        prefs.update(copy.deepcopy(update))
        return load()

    def mutate(mutator):
        current = load()
        result = mutator(current)
        prefs.clear()
        prefs.update(result if isinstance(result, dict) else current)
        return load()

    return space_routes(tmp, load, save, mutate), prefs


def make_v4_space(parent: Path, name: str = "Old Name") -> Path:
    """A configured v4 Space whose inventory still has the old folder-name file."""
    folder = parent / name
    folder.mkdir(parents=True)
    configure_space(folder, raw_def=dict(V4["space"]))
    append_bin(folder, file="Box 16 x 16 x 20.3mf", x=16, y=16, z=20, name="Nuts")
    (folder / INVENTORY_FILENAME).rename(folder / f"{name} bins.md")
    (folder / ".wavefinity.json").write_text(json.dumps(V4, indent=2), encoding="utf-8")
    return folder


def meta(folder: Path) -> dict:
    return json.loads((folder / ".wavefinity.json").read_text(encoding="utf-8"))


class SpaceIdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.routes, self.prefs = make_routes(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def call(self, route, **payload):
        return self.routes[route](payload)

    def test_v4_typed_open_upgrades_to_v5_without_setup(self):
        folder = make_v4_space(self.tmp)
        before = (folder / ".wavefinity.json").read_bytes()
        info = self.call("/api/space/inspect", output=str(folder))["folder"]
        self.assertFalse(info["needs_setup"])
        self.assertTrue(info["needs_identity_migration"])
        self.assertEqual((folder / ".wavefinity.json").read_bytes(), before)
        self.assertTrue((folder / "Old Name bins.md").is_file())
        self.assertFalse((folder / INVENTORY_FILENAME).exists())

        opened = self.call("/api/folder/use", output=str(folder))["folder"]
        data = meta(folder)
        self.assertEqual(data["version"], 5)
        self.assertEqual(str(uuid.UUID(data["space_id"])), data["space_id"])
        self.assertEqual(data["space"], V4["space"])
        self.assertEqual(data["bin_defaults"], {"marker": 1})
        self.assertEqual(opened["space_id"], data["space_id"])
        self.assertTrue((folder / INVENTORY_FILENAME).is_file())
        self.assertFalse((folder / "Old Name bins.md").exists())
        loaded = load_inventory(folder)
        self.assertEqual([b["name"] for b in loaded["bins"]], ["Nuts"])
        self.assertEqual(loaded["layout"]["space"]["name"], "Vanity")

    def test_space_id_survives_every_metadata_rewrite(self):
        folder = make_v4_space(self.tmp)
        self.call("/api/folder/use", output=str(folder))
        space_id = meta(folder)["space_id"]
        self.call("/api/space/update", output=str(folder), name="Renamed", x=320, y=240, z=55)
        self.assertEqual(meta(folder)["space_id"], space_id)
        self.assertEqual(meta(folder)["space"]["name"], "Renamed")
        self.call("/api/space/defaults", output=str(folder), keep_bin_defaults=False)
        self.assertEqual(meta(folder)["space_id"], space_id)
        self.call("/api/folder/use", output=str(folder))
        self.assertEqual(meta(folder)["space_id"], space_id)
        self.assertEqual(self.prefs["active_space_id"], space_id)

    def test_v5_typed_without_id_is_damaged_not_healed(self):
        folder = make_v4_space(self.tmp)
        self.call("/api/folder/use", output=str(folder))
        data = meta(folder)
        del data["space_id"]
        (folder / ".wavefinity.json").write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.call("/api/folder/use", output=str(folder))
        self.assertNotIn("space_id", meta(folder))

    def test_same_parent_rename_recovers_by_id(self):
        folder = make_v4_space(self.tmp)
        self.call("/api/folder/use", output=str(folder))
        space_id = meta(folder)["space_id"]
        renamed = folder.rename(self.tmp / "Master Bath Drawer")
        result = self.call("/api/space/startup")
        self.assertEqual(Path(result["folder"]["folder"]), renamed)
        self.assertEqual(result["folder"]["space_id"], space_id)
        self.assertEqual(result["folder"]["space"]["name"], "Vanity")
        self.assertEqual(Path(self.prefs["output"]), renamed)
        self.assertEqual(Path(self.prefs["space_registry"][space_id]["folder"]), renamed)
        self.assertEqual([b["name"] for b in load_inventory(renamed)["bins"]], ["Nuts"])
        self.assertEqual(result["recent"][0]["name"], "Vanity")

    def test_manual_move_and_duplicate_copy_rules(self):
        folder = make_v4_space(self.tmp)
        self.call("/api/folder/use", output=str(folder))
        space_id = meta(folder)["space_id"]

        copy_dir = self.tmp / "Copy"
        shutil.copytree(folder, copy_dir)
        with self.assertRaises(DuplicateSpaceError):
            self.call("/api/folder/use", output=str(copy_dir))
        self.assertEqual(Path(self.prefs["space_registry"][space_id]["folder"]), folder)
        self.assertEqual(Path(self.prefs["output"]), folder)
        shutil.rmtree(copy_dir)

        elsewhere = self.tmp / "other"
        elsewhere.mkdir()
        moved = Path(shutil.move(str(folder), str(elsewhere / "Moved")))
        result = self.call("/api/folder/use", output=str(moved))
        self.assertEqual(result["folder"]["space_id"], space_id)
        self.assertEqual(Path(self.prefs["space_registry"][space_id]["folder"]), moved)
        self.assertEqual(len(self.prefs["space_registry"]), 1)

    def test_untyped_folder_gets_no_id_and_clears_active_space(self):
        folder = make_v4_space(self.tmp)
        self.call("/api/folder/use", output=str(folder))
        plain = self.tmp / "Plain"
        plain.mkdir()
        self.call("/api/space/use-untyped", output=str(plain))
        self.assertNotIn("space_id", meta(plain))
        self.assertIsNone(self.prefs["active_space_id"])
        self.assertTrue(self.prefs["recent_folders"][0]["last_seen"])

    def test_registry_is_not_capped_but_recent_list_is(self):
        folders = {}
        for index in range(MAX_RECENT + 2):
            space_id = str(uuid.uuid4())
            folder = self.tmp / f"Space {index}"
            folder.mkdir()
            (folder / ".wavefinity.json").write_text(json.dumps({
                **V4, "version": 5, "space_id": space_id,
                "space": {**V4["space"], "name": f"Space {index}"},
            }), encoding="utf-8")
            folders[space_id] = folder
            self.prefs.setdefault("space_registry", {})[space_id] = {
                "name": f"Space {index}", "kind": "drawer", "folder": str(folder),
                "last_seen": f"2026-09-{10 + index:02d}T00:00:00+00:00",
            }
        recent = self.call("/api/space/inspect")["recent"]
        self.assertEqual(len(recent), MAX_RECENT)
        self.assertEqual(recent[0]["name"], f"Space {MAX_RECENT + 1}")
        self.assertEqual(len(self.prefs["space_registry"]), MAX_RECENT + 2)

        gone = next(iter(folders))
        self.call("/api/space/forget", space_id=gone, output=str(folders[gone]))
        self.assertNotIn(gone, self.prefs["space_registry"])
        self.assertEqual(len(self.prefs["space_registry"]), MAX_RECENT + 1)
        self.assertTrue((folders[gone] / ".wavefinity.json").is_file())


class InventoryResolverTests(unittest.TestCase):
    def test_resolver_is_read_only_then_migrates_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Renamed Folder"
            folder.mkdir()
            append_bin(folder, file="a.3mf", x=16, y=16, z=20, name="One")
            canonical = folder / INVENTORY_FILENAME
            legacy = folder / "Older bins.md"
            canonical.rename(legacy)

            self.assertEqual([b["name"] for b in load_inventory(folder)["bins"]], ["One"])
            self.assertTrue(legacy.is_file())
            self.assertFalse(canonical.exists())

            save_inventory(folder, bin_updates=[{"id": "B1", "qty": 2}])
            self.assertTrue(canonical.is_file())
            self.assertFalse(legacy.exists())
            self.assertEqual(load_inventory(folder)["bins"][0]["qty"], 2)

            # Identical leftover: removed on migrate, before canonical changes.
            legacy.write_bytes(canonical.read_bytes())
            resolve_inventory_path(folder, migrate=False)
            self.assertTrue(legacy.is_file())
            save_inventory(folder, bin_updates=[{"id": "B1", "qty": 3}])
            self.assertFalse(legacy.exists())

            # Differing leftover: hard stop, nothing modified.
            legacy.write_text("# something else\n", encoding="utf-8")
            before = canonical.read_bytes()
            with self.assertRaises(InventoryMigrationError):
                save_inventory(folder, bin_updates=[{"id": "B1", "qty": 4}])
            self.assertEqual(canonical.read_bytes(), before)
            self.assertEqual(legacy.read_text(encoding="utf-8"), "# something else\n")

    def test_two_legacy_files_never_create_a_blank_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "F"
            folder.mkdir()
            (folder / "A bins.md").write_text("a", encoding="utf-8")
            (folder / "B bins.md").write_text("b", encoding="utf-8")
            with self.assertRaises(InventoryMigrationError):
                append_bin(folder, file="x.3mf", x=8, y=8, z=8)
            self.assertFalse((folder / INVENTORY_FILENAME).exists())


class ProfilePreferenceTests(unittest.TestCase):
    def test_local_preference_file_migrates_to_user_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            legacy = Path(tmp) / "app" / "wavefinity_prefs.json"
            profile = Path(tmp) / "profile" / "Wavefinity" / "wavefinity_prefs.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"output": "X", "slicer_path": "S"}), encoding="utf-8")
            with patch.object(wavefinity_web, "LEGACY_PREFERENCES_FILE", legacy), \
                    patch.object(wavefinity_web, "PREFERENCES_FILE", profile):
                self.assertEqual(wavefinity_web.load_preferences()["output"], "X")
                wavefinity_web.save_preferences({"extra": 1})
                self.assertTrue(profile.is_file())
                saved = json.loads(profile.read_text(encoding="utf-8"))
                self.assertEqual(saved, {"output": "X", "slicer_path": "S", "extra": 1})
                self.assertEqual(json.loads(legacy.read_text(encoding="utf-8"))["output"], "X")
                legacy.write_text(json.dumps({"output": "STALE"}), encoding="utf-8")
                self.assertEqual(wavefinity_web.load_preferences()["output"], "X")


class ShowLogTests(unittest.TestCase):
    def test_show_log_uses_canonical_inventory_resolver(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Somewhere"
            folder.mkdir()
            append_bin(folder, file="a.3mf", x=16, y=16, z=20)
            (folder / INVENTORY_FILENAME).rename(folder / "Old bins.md")
            (folder / "notes.md").write_text("unrelated", encoding="utf-8")
            with patch.object(wavefinity_web, "HOSTED", False), \
                    patch.object(wavefinity_web, "open_log_with_wordpad") as opener:
                wavefinity_web.show_log_payload({"output": str(folder)})
            opened = Path(opener.call_args.args[0])
            self.assertEqual(opened.name, INVENTORY_FILENAME)
            self.assertTrue(opened.is_file())
            self.assertFalse((folder / "Old bins.md").exists())


if __name__ == "__main__":
    unittest.main()
