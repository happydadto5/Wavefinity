"""Fix 058 K: first-run local Space storage location.

Local-only: the default Space hierarchy stays ``<space parent>/Wavefinity/
<Space Name>`` with Documents as the default parent. ``space_parent`` is the
one explicit preference that overrides just the parent - never the
``Wavefinity`` child name - and is resolved fresh from preferences at every
Space-creation call, never captured once at startup.
"""

from __future__ import annotations

import tempfile
import unittest
import copy
import json
import shutil
from pathlib import Path
from unittest import mock

import organizer_spaces
import wavefinity_web
from test_space_identity import make_routes


class SpaceStorageStartupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name).resolve()
        self.docs = self.home / "Documents"
        self.tmp = self.home / "designs"
        self.routes, self.prefs = make_routes(self.tmp)
        self._patch = mock.patch.object(organizer_spaces, "default_space_parent", return_value=self.docs)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_other_spaces_discovers_only_healthy_direct_siblings_without_writes(self):
        first = self.routes["/api/space/create"]({
            "name": "Kitchen", "kind": "drawer", "x": 320, "y": 240, "z": 55,
        })
        second = self.routes["/api/space/create"]({
            "name": "Garage", "kind": "drawer", "x": 320, "y": 240, "z": 55,
        })
        root = self.docs / "Wavefinity"
        kitchen = Path(first["folder"]["folder"])
        garage = Path(second["folder"]["folder"])
        self.prefs["recent_folders"] = []
        self.prefs["space_registry"] = {}
        nested = root / "Nested" / "Deep"
        shutil.copytree(kitchen, nested)
        (root / "Arbitrary").mkdir()
        design = root / "Design"
        design.mkdir()
        (design / ".wavefinity.json").write_text(json.dumps({
            "version": 9, "setup_version": 1, "folder_mode": "design", "inventory": True,
        }), encoding="utf-8")
        newer = root / "Newer"
        newer.mkdir()
        (newer / ".wavefinity.json").write_text(json.dumps({"version": 999}), encoding="utf-8")
        setup = root / "Setup"
        shutil.copytree(kitchen, setup)
        setup_meta = json.loads((setup / ".wavefinity.json").read_text(encoding="utf-8"))
        setup_meta["setup_version"] = 0
        setup_meta["space_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        (setup / ".wavefinity.json").write_text(json.dumps(setup_meta), encoding="utf-8")
        before_prefs = copy.deepcopy(self.prefs)
        before_files = {p: p.read_bytes() for p in root.rglob(".wavefinity.json")}
        result = self.routes["/api/space/other-spaces"]({})["other_spaces"]
        self.assertEqual([one["name"] for one in result], ["Kitchen"])
        self.assertEqual(self.prefs, before_prefs)
        self.assertEqual({p: p.read_bytes() for p in root.rglob(".wavefinity.json")}, before_files)
        self.assertEqual(result, self.routes["/api/space/startup"]({})["other_spaces"])
        duplicate = root / "Kitchen copy"
        shutil.copytree(kitchen, duplicate)
        self.assertEqual(self.routes["/api/space/other-spaces"]({})["other_spaces"], [])
        self.assertEqual(Path(self.prefs["output"]), garage)

    def test_other_spaces_re_resolves_changed_root_without_creating_it(self):
        missing = self.docs / "Wavefinity"
        self.assertEqual(self.routes["/api/space/other-spaces"]({})["other_spaces"], [])
        self.assertFalse(missing.exists())
        first = self.routes["/api/space/create"]({
            "name": "Kitchen", "kind": "drawer", "x": 320, "y": 240, "z": 55,
        })
        self.prefs["active_space_id"] = None
        self.prefs["output"] = None
        custom = self.home / "custom-discovery"
        (custom / "Wavefinity").mkdir(parents=True)
        shutil.copytree(Path(first["folder"]["folder"]), custom / "Wavefinity" / "Kitchen")
        self.prefs["space_parent"] = str(custom)
        result = self.routes["/api/space/startup"]({})["other_spaces"]
        self.assertEqual([one["name"] for one in result], ["Kitchen"])
        self.assertEqual(Path(result[0]["folder"]).parent, custom / "Wavefinity")

    # 1. no saved parent + missing Documents/Wavefinity => first-run choice,
    #    Documents/default effective root, and the root is never created.
    def test_first_run_when_no_saved_parent_and_no_default_root(self):
        state = organizer_spaces.storage_startup_state(self.prefs)
        self.assertTrue(state["first_run"])
        self.assertFalse(state["explicit"])
        self.assertFalse(state["unavailable"])
        self.assertEqual(state["parent"], str(self.docs))
        self.assertEqual(state["root"], str(self.docs / "Wavefinity"))
        self.assertFalse((self.docs / "Wavefinity").exists())
        # Startup itself must not create it either.
        self.routes["/api/space/startup"]({})
        self.assertFalse((self.docs / "Wavefinity").exists())

    # 2. no saved parent + existing Documents/Wavefinity => no first-run
    #    choice, and default creation remains there.
    def test_no_first_run_when_default_root_already_established(self):
        (self.docs / "Wavefinity").mkdir(parents=True)
        state = organizer_spaces.storage_startup_state(self.prefs)
        self.assertFalse(state["first_run"])
        self.assertEqual(state["root"], str(self.docs / "Wavefinity"))

    # 3. an explicit custom parent wins even if Documents/Wavefinity exists.
    def test_explicit_custom_parent_wins_over_existing_default_root(self):
        (self.docs / "Wavefinity").mkdir(parents=True)
        custom = self.home / "custom"
        custom.mkdir()
        self.prefs["space_parent"] = str(custom)
        state = organizer_spaces.storage_startup_state(self.prefs)
        self.assertFalse(state["first_run"])
        self.assertTrue(state["explicit"])
        self.assertEqual(state["parent"], str(custom.resolve()))
        self.assertEqual(state["root"], str(custom.resolve() / "Wavefinity"))

    # 4. changing space_parent affects the very next auto-created Space,
    #    without any server restart (no re-construction of space_routes).
    def test_changing_space_parent_affects_next_auto_created_space(self):
        result = self.routes["/api/space/create"]({"name": "Kitchen", "kind": "drawer", "x": 320, "y": 240, "z": 55})
        self.assertEqual(Path(result["folder"]["folder"]).parent, (self.docs / "Wavefinity").resolve())

        custom = self.home / "custom2"
        custom.mkdir()
        self.routes["/api/space/storage-parent"]({"parent": str(custom)})

        result2 = self.routes["/api/space/create"]({"name": "Garage", "kind": "drawer", "x": 320, "y": 240, "z": 55})
        self.assertEqual(Path(result2["folder"]["folder"]).parent, (custom / "Wavefinity").resolve())

    # 5. a custom parent creates <parent>/Wavefinity/<Space Name>, not
    #    <parent>/<Space Name>.

    # 6. opening or cancelling the Open Existing chooser never creates
    #    Documents/Wavefinity.
    def test_open_existing_chooser_creates_no_wavefinity_root(self):
        with mock.patch.object(wavefinity_web, "load_preferences", return_value=dict(self.prefs)), \
             mock.patch.object(wavefinity_web.subprocess, "run", return_value=mock.Mock(stdout="", stderr="")):
            wavefinity_web.browse_output_folder_payload({"space_root": True})
        self.assertFalse((self.docs / "Wavefinity").exists())
        # A real selection still creates nothing on its own - only an actual
        # Space-creation call may create the effective root.
        with mock.patch.object(wavefinity_web, "load_preferences", return_value=dict(self.prefs)), \
             mock.patch.object(wavefinity_web.subprocess, "run", return_value=mock.Mock(stdout=str(self.docs), stderr="")):
            wavefinity_web.browse_output_folder_payload({"space_root": True})
        self.assertFalse((self.docs / "Wavefinity").exists())

    # 7. saving space_parent validates an existing directory but never
    #    creates its Wavefinity child.

    # 8. an unavailable saved custom parent is reported for user repair
    #    rather than silently reset to Documents.
    def test_unavailable_saved_parent_is_reported_not_silently_reset(self):
        self.prefs["space_parent"] = str(self.home / "vanished")
        state = organizer_spaces.storage_startup_state(self.prefs)
        self.assertTrue(state["unavailable"])
        self.assertFalse(state["explicit"])
        # Falls back to Documents as the *reported* effective parent, but the
        # saved preference itself is left untouched (not silently reset).
        self.assertEqual(state["parent"], str(self.docs))
        self.assertEqual(self.prefs["space_parent"], str(self.home / "vanished"))

    # 9. Fix 058 Correction 1, C1.2: an unavailable explicit saved parent
    #    blocks automatic Create - it must never silently fall back to
    #    Documents - and the saved preference is left unchanged. Once a
    #    valid parent is set, the very next Create uses it, no restart.
    def test_create_blocks_on_unavailable_saved_parent_without_documents_fallback(self):
        custom = self.home / "custom-gone"
        custom.mkdir()
        self.routes["/api/space/storage-parent"]({"parent": str(custom)})
        custom.rmdir()  # the saved parent now no longer exists/is unavailable

        with self.assertRaises(ValueError) as ctx:
            self.routes["/api/space/create"]({"name": "Kitchen", "kind": "drawer", "x": 320, "y": 240, "z": 55})
        self.assertIn("Change on Welcome", str(ctx.exception))
        self.assertFalse((self.docs / "Wavefinity").exists())
        self.assertEqual(self.prefs["space_parent"], str(custom.resolve()))

        valid = self.home / "custom-valid"
        valid.mkdir()
        self.routes["/api/space/storage-parent"]({"parent": str(valid)})
        result = self.routes["/api/space/create"]({"name": "Kitchen", "kind": "drawer", "x": 320, "y": 240, "z": 55})
        self.assertEqual(Path(result["folder"]["folder"]).parent, (valid / "Wavefinity").resolve())


class BrowseSpaceParentChooserTests(unittest.TestCase):
    """The Welcome "Change" chooser: browses, and on a real pick saves."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name).resolve()
        self.docs = self.home / "Documents"
        self.docs.mkdir(parents=True)
        self.saved: dict = {}
        self._patch = mock.patch.object(organizer_spaces, "default_space_parent", return_value=self.docs)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def _prefs(self):
        return dict(self.saved)

    def _save(self, update):
        self.saved.update(update)
        return dict(self.saved)

    def test_cancel_creates_nothing_and_leaves_preference_unchanged(self):
        with mock.patch.object(wavefinity_web, "load_preferences", side_effect=self._prefs), \
             mock.patch.object(wavefinity_web, "save_preferences", side_effect=self._save), \
             mock.patch.object(wavefinity_web.subprocess, "run", return_value=mock.Mock(stdout="", stderr="")):
            result = wavefinity_web.browse_space_parent_payload({})
        self.assertIsNone(result["folder"])
        self.assertNotIn("space_parent", self.saved)
        self.assertFalse((self.docs / "Wavefinity").exists())



if __name__ == "__main__":
    unittest.main()
