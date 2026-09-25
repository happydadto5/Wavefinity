import tempfile
import time
import unittest
import zipfile
from pathlib import Path

import bambu_handoff as bh

MODEL_SECOND = (
    '<config><object id="1"><metadata key="extruder" value="1"/>'
    '<part id="2"><metadata key="extruder" value="2"/></part></object></config>'
)
MODEL_ONE = '<config><object id="1"><metadata key="extruder" value="1"/></object></config>'


def make_3mf(path: Path, members: dict[str, str] | None = None) -> Path:
    members = members if members is not None else {
        "3D/3dmodel.model": "<model/>",
        "Metadata/model_settings.config": MODEL_ONE,
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, content in members.items():
            z.writestr(name, content)
    return path


class StageBambuInputsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "handoffs"
        self.a = make_3mf(self.dir / "Box.3mf")
        self.b = make_3mf(self.dir / "Connector.3mf", {
            "3D/3dmodel.model": "<model/>",
            "Metadata/model_settings.config": MODEL_SECOND,
        })

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_source_occurrence_gets_distinct_staged_path(self):
        staged = bh.stage_bambu_inputs([self.a, self.a, self.a], handoff_root=self.root)
        self.assertEqual(len(staged), 3)
        self.assertEqual(len(set(staged)), 3)
        for p in staged:
            self.assertTrue(p.is_file())

    def test_staged_safe_file_is_byte_identical_to_source(self):
        staged = bh.stage_bambu_inputs([self.a], handoff_root=self.root)
        self.assertEqual(staged[0].read_bytes(), self.a.read_bytes())

    def test_model_settings_config_survives(self):
        staged = bh.stage_bambu_inputs([self.b], handoff_root=self.root)
        with zipfile.ZipFile(staged[0]) as z:
            self.assertIn("Metadata/model_settings.config", z.namelist())

    def test_slot_two_assignment_survives(self):
        staged = bh.stage_bambu_inputs([self.b], handoff_root=self.root)
        self.assertEqual(bh._second_colour_assignment_count(self.b), 1)
        self.assertEqual(
            bh._second_colour_assignment_count(staged[0]),
            bh._second_colour_assignment_count(self.b),
        )

    def test_project_settings_source_is_rejected(self):
        unsafe = make_3mf(self.dir / "unsafe1.3mf", {
            "3D/3dmodel.model": "<model/>",
            "Metadata/project_settings.config": "{}",
        })
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([unsafe], handoff_root=self.root)
        self.assertFalse(self.root.is_dir())

    def test_embedded_process_preset_source_is_rejected(self):
        unsafe = make_3mf(self.dir / "unsafe2.3mf", {
            "3D/3dmodel.model": "<model/>",
            "Metadata/process_settings_1.config": "{}",
        })
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([unsafe], handoff_root=self.root)

    def test_embedded_filament_preset_source_is_rejected(self):
        unsafe = make_3mf(self.dir / "unsafe3.3mf", {
            "3D/3dmodel.model": "<model/>",
            "Metadata/filament_settings_1.config": "{}",
        })
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([unsafe], handoff_root=self.root)

    def test_embedded_machine_preset_source_is_rejected(self):
        unsafe = make_3mf(self.dir / "unsafe4.3mf", {
            "3D/3dmodel.model": "<model/>",
            "Metadata/machine_settings_1.config": "{}",
        })
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([unsafe], handoff_root=self.root)

    def test_missing_source_is_rejected(self):
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([self.dir / "nope.3mf"], handoff_root=self.root)

    def test_non_3mf_source_is_rejected(self):
        stl = self.dir / "x.stl"
        stl.write_bytes(b"x")
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([stl], handoff_root=self.root)

    def test_old_handoff_pruning_never_touches_the_new_one(self):
        old = self.root / "old-handoff"
        old.mkdir(parents=True)
        (old / "0001 - Box.3mf").write_bytes(b"x")
        old_time = time.time() - (bh.STALE_HANDOFF_AGE_SECONDS + 3600)
        import os
        os.utime(old, (old_time, old_time))

        staged = bh.stage_bambu_inputs([self.a], handoff_root=self.root)
        self.assertTrue(staged[0].is_file())
        self.assertFalse(old.exists())
        # The just-created handoff directory itself must never be pruned.
        self.assertTrue(staged[0].parent.is_dir())

    def test_recent_old_handoff_is_kept(self):
        recent = self.root / "recent-handoff"
        recent.mkdir(parents=True)
        (recent / "0001 - Box.3mf").write_bytes(b"x")

        staged = bh.stage_bambu_inputs([self.a], handoff_root=self.root)
        self.assertTrue(staged[0].is_file())
        self.assertTrue(recent.is_dir())

    def test_no_files_raises(self):
        with self.assertRaises(ValueError):
            bh.stage_bambu_inputs([], handoff_root=self.root)

    def test_executable_detection(self):
        self.assertTrue(bh.is_bambu_studio_executable(Path("C:/x/Bambu-Studio.exe")))
        self.assertFalse(bh.is_bambu_studio_executable(Path("C:/x/orca-slicer.exe")))


if __name__ == "__main__":
    unittest.main()
