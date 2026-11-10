import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import trimesh

import bambu_handoff as bh
from plate_layout import combine_for_plate
from organizer_engine._export import export_object_groups_3mf

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





    def test_extruder_slot_mismatch_is_rejected_before_launch_and_cleaned_up(self):
        # Fix 058 Correction 1, C1.3: simulate a staged copy that failed to
        # preserve its non-default extruder-slot assignment(s) by returning a
        # different count for the staged path than for the source path. The
        # handoff must fail before Bambu is ever launched, and the
        # now-incomplete handoff directory must be cleaned up - neither the
        # source nor the staged package may be mutated to "fix" it.
        import unittest.mock as mock

        real_count = bh._second_colour_assignment_count

        def fake_count(path):
            n = real_count(path)
            if Path(path).name.startswith("0001 -"):
                return 0  # staged copy reports a mismatch vs. the source's 1
            return n

        with mock.patch.object(bh, "_second_colour_assignment_count", side_effect=fake_count):
            with self.assertRaises(ValueError) as ctx:
                bh.stage_bambu_inputs([self.b], handoff_root=self.root)
        self.assertIn("extruder-slot", str(ctx.exception))
        # The incomplete handoff directory created for this launch is removed.
        self.assertEqual(list(self.root.iterdir()) if self.root.is_dir() else [], [])


    def test_executable_detection(self):
        self.assertTrue(bh.is_bambu_studio_executable(Path("C:/x/Bambu-Studio.exe")))
        self.assertFalse(bh.is_bambu_studio_executable(Path("C:/x/orca-slicer.exe")))


class CombinedPlateTests(unittest.TestCase):
    def test_both_launch_paths_hand_bambu_one_layout_in_output_folder(self):
        from unittest.mock import patch
        import wavefinity_web as web
        from plate_layout import space_out_for_plate

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "bin.3mf"
            export_object_groups_3mf(
                [("Bin", [("Body", trimesh.creation.box(extents=(20, 30, 5)))])], source)
            slicer = root / "bambu-studio.exe"
            slicer.touch()
            profile = {"x_mm": 256, "y_mm": 256}
            spaced, issues = space_out_for_plate([source, source], profile, root / "spacing")
            self.assertEqual(issues, [])
            with patch.object(web, "_printer_profile_for", return_value=profile), \
                    patch.object(web.subprocess, "Popen") as popen:
                popen.return_value.wait.return_value = 0
                web.launch_slicer(slicer, [source, source])
                self.assertEqual(popen.call_args.args[0],
                                 [str(slicer.resolve()), str((root / "Last Print Layout.3mf").resolve())])
                web.launch_slicer(slicer, spaced, already_on_plate=True, output_dir=root)
                self.assertEqual(popen.call_args.args[0],
                                 [str(slicer.resolve()), str((root / "Last Print Layout.3mf").resolve())])
                with patch.object(web, "validate_bambu_handoff", side_effect=ValueError("rejected")):
                    popen.reset_mock()
                    with self.assertRaises(ValueError):
                        web.launch_slicer(slicer, [source])
                    popen.assert_not_called()

    def test_combined_spacing_registered_parts_slots_and_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            box = trimesh.creation.box(extents=(20, 30, 5))
            label = trimesh.creation.box(extents=(5, 5, 1))
            label.apply_translation((0, 0, 3))
            a, b = root / "a.3mf", root / "b.3mf"
            export_object_groups_3mf([("Bin", [("Body", box), ("Label", label)])], a,
                                     filaments={"Label": 2})
            export_object_groups_3mf([("Bin", [("Body", box)])], b)
            originals = [p.read_bytes() for p in (a, b)]
            dest = root / "Last Print Layout.3mf"
            result, issues = combine_for_plate([a, b, a], {"x_mm": 256, "y_mm": 256}, dest)
            self.assertEqual((result.name, issues), ("Last Print Layout.3mf", []))
            ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
            with zipfile.ZipFile(dest) as archive:
                model = ET.fromstring(archive.read("3D/3dmodel.model"))
                config = ET.fromstring(archive.read("Metadata/model_settings.config"))
            items = model.findall("m:build/m:item", ns)
            self.assertEqual(len(items), 3)
            objects = model.findall("m:resources/m:object", ns)
            by_id = {obj.get("id"): obj for obj in objects}
            self.assertEqual(len(by_id), len(objects))
            self.assertEqual(len({obj.get("name") for obj in objects}), len(objects))
            for index in (0, 2):
                parent = by_id[items[index].get("objectid")]
                self.assertEqual(len(parent.findall("m:components/m:component", ns)), 2)
            for obj in config.findall("object"):
                self.assertIn(obj.get("id"), by_id)
                for part in obj.findall("part"):
                    self.assertIn(part.get("id"), by_id)
                    if by_id[part.get("id")].get("name").startswith("Label"):
                        self.assertEqual(part.find("metadata[@key='extruder']").get("value"), "2")
            bh.validate_bambu_handoff(dest, [a, b, a])
            self.assertEqual(bh._second_colour_assignment_count(dest), 2)
            scene = trimesh.load(dest, force="scene")
            # Each registered occurrence has two meshes sharing one footprint.
            footprints = []
            for node in scene.graph.nodes_geometry:
                transform, geom = scene.graph[node]
                points = trimesh.transform_points(scene.geometry[geom].vertices, transform)
                if np.ptp(points[:, 0]) > 10:
                    footprints.append(np.array([points.min(axis=0), points.max(axis=0)]))
            footprints.sort(key=lambda bounds: bounds[0, 0])
            self.assertEqual(len(footprints), 3)
            for left, right in zip(footprints, footprints[1:]):
                self.assertGreaterEqual(right[0, 0] - left[1, 0], 10 - 1e-6)
            for bounds in footprints:
                self.assertAlmostEqual(bounds[0, 2], 0)
            combine_for_plate([b], {"x_mm": 256, "y_mm": 256}, dest)
            with zipfile.ZipFile(dest) as archive:
                model = ET.fromstring(archive.read("3D/3dmodel.model"))
            self.assertEqual(len(model.findall("m:build/m:item", ns)), 1)
            self.assertEqual([p.read_bytes() for p in (a, b)], originals)

    def test_fit_error_keeps_previous_layout(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, dest = root / "part.3mf", root / "Last Print Layout.3mf"
            export_object_groups_3mf(
                [("Bin", [("Body", trimesh.creation.box(extents=(20, 30, 5)))])], source)
            dest.write_bytes(b"previous layout")
            _, issues = combine_for_plate([source, source], {"x_mm": 30, "y_mm": 40}, dest)
            self.assertTrue(issues)
            self.assertEqual(dest.read_bytes(), b"previous layout")


if __name__ == "__main__":
    unittest.main()
