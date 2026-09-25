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
    def test_custom_parent_nests_under_its_own_wavefinity_folder(self):
        custom = self.home / "custom3"
        custom.mkdir()
        self.routes["/api/space/storage-parent"]({"parent": str(custom)})
        result = self.routes["/api/space/create"]({"name": "Bench", "kind": "drawer", "x": 320, "y": 240, "z": 55})
        created = Path(result["folder"]["folder"])
        self.assertEqual(created, (custom / "Wavefinity" / "Bench").resolve())

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
    def test_saving_space_parent_validates_but_does_not_create_child(self):
        with self.assertRaises(ValueError):
            self.routes["/api/space/storage-parent"]({"parent": str(self.home / "does-not-exist")})
        custom = self.home / "custom4"
        custom.mkdir()
        result = self.routes["/api/space/storage-parent"]({"parent": str(custom)})
        self.assertEqual(result["storage"]["parent"], str(custom.resolve()))
        self.assertFalse((custom / "Wavefinity").exists())

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

    def test_a_real_pick_saves_the_absolute_parent(self):
        custom = self.home / "picked"
        custom.mkdir()
        with mock.patch.object(wavefinity_web, "load_preferences", side_effect=self._prefs), \
             mock.patch.object(wavefinity_web, "save_preferences", side_effect=self._save), \
             mock.patch.object(wavefinity_web.subprocess, "run", return_value=mock.Mock(stdout=str(custom), stderr="")):
            result = wavefinity_web.browse_space_parent_payload({})
        self.assertEqual(result["folder"], str(custom.resolve()))
        self.assertEqual(self.saved["space_parent"], str(custom.resolve()))
        self.assertFalse((custom / "Wavefinity").exists())


if __name__ == "__main__":
    unittest.main()
