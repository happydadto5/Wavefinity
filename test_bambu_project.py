import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import bambu_project as bp

MODEL_SECOND = (
    '<config><object id="1"><metadata key="extruder" value="1"/>'
    '<part id="2"><metadata key="extruder" value="2"/></part></object></config>'
)
MODEL_ONE = '<config><object id="1"><metadata key="extruder" value="1"/></object></config>'


def make_3mf(path: Path, model_settings: str = MODEL_ONE) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
        z.writestr("Metadata/model_settings.config", model_settings)
    return path


def fake_run(members=None, returncode=0, write=True, calls=None):
    members = members if members is not None else {
        "Metadata/project_settings.config": "{}",
        "Metadata/model_settings.config": MODEL_SECOND,
    }

    def run(args, **kwargs):
        if calls is not None:
            calls.append(args)
        if write:
            out = Path(args[args.index("--export-3mf") + 1])
            with zipfile.ZipFile(out, "w") as z:
                for k, v in members.items():
                    z.writestr(k, v)
        return mock.Mock(returncode=returncode, stdout="", stderr="boom")
    return run


class BuildProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.root = self.dir / "out"
        self.a = make_3mf(self.dir / "a.3mf")
        self.b = make_3mf(self.dir / "b.3mf", MODEL_SECOND)
        self.slicer = self.dir / "bambu-studio.exe"
        self.slicer.write_bytes(b"")

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, run, files=None):
        with mock.patch.object(bp.subprocess, "run", run):
            return bp.build_bambu_project(
                self.slicer, files or [self.a, self.b], project_root=self.root)

    def test_command_flags(self):
        calls = []
        self.build(fake_run(calls=calls))
        args = calls[0]
        self.assertEqual(args[args.index("--arrange") + 1], "1")
        self.assertIn("--export-3mf", args)
        for bad in ("--slice", "--load-settings", "--load-filaments"):
            self.assertNotIn(bad, args)

    def test_duplicates_get_distinct_staged_paths(self):
        calls = []
        self.build(fake_run(calls=calls), [self.a, self.a, self.a])
        staged = calls[0][5:]
        self.assertEqual(len(staged), 3)
        self.assertEqual(len(set(staged)), 3)

    def test_nonzero_exit_raises_and_removes_output(self):
        with self.assertRaises(RuntimeError):
            self.build(fake_run(returncode=1))
        self.assertEqual(list(self.root.glob("*.3mf")), [])

    def test_missing_output_raises(self):
        with self.assertRaises(RuntimeError):
            self.build(fake_run(write=False))

    def test_missing_project_settings_raises(self):
        run = fake_run({"Metadata/model_settings.config": MODEL_SECOND})
        with self.assertRaises(RuntimeError):
            self.build(run)
        self.assertEqual(list(self.root.glob("*.3mf")), [])

    def test_second_colour_lost_raises(self):
        run = fake_run({
            "Metadata/project_settings.config": "{}",
            "Metadata/model_settings.config": MODEL_ONE,
        })
        with self.assertRaises(RuntimeError):
            self.build(run)
        self.assertEqual(list(self.root.glob("*.3mf")), [])

    def test_second_colour_kept_succeeds(self):
        self.assertTrue(self.build(fake_run()).is_file())

    def test_success_survives_staging_cleanup(self):
        project = self.build(fake_run(), [self.a])
        self.assertTrue(project.is_file())
        self.assertEqual(project.parent, self.root.resolve())

    def test_rejects_non_3mf(self):
        stl = self.dir / "x.stl"
        stl.write_bytes(b"x")
        with self.assertRaises(ValueError):
            self.build(fake_run(), [stl])

    def test_executable_detection(self):
        self.assertTrue(bp.is_bambu_studio_executable(Path("C:/x/Bambu-Studio.exe")))
        self.assertFalse(bp.is_bambu_studio_executable(Path("C:/x/orca-slicer.exe")))


if __name__ == "__main__":
    unittest.main()
