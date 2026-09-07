import tempfile
import unittest
from pathlib import Path

from organizer_engine import BoxSpec
from organizer_inserts import Feature, Item, Layout, Segment, Zone
from organizer_app import (
    generate_organizer_files,
    log_bin_to_folder,
    summarize_interior_parts,
)
import wavefinity_web


class TestBinLogging(unittest.TestCase):
    def test_summarize_interior_parts_empty(self):
        layout = Layout((), "fused", 1.0)
        self.assertEqual(summarize_interior_parts(layout), "None")
        self.assertEqual(summarize_interior_parts(layout, scoop=True), "Scoop")

    def test_summarize_interior_parts_features(self):
        f1 = Feature("divider", Zone(0, 0, 10, 10))
        f2 = Feature("divider", Zone(10, 0, 20, 10))
        layout = Layout((f1, f2), "fused", 1.0)
        self.assertEqual(summarize_interior_parts(layout), "2x Divider")

        item = Item("Pencil", (Segment(100.0, 7.0),))
        f3 = Feature("cradle", Zone(0, 0, 20, 20), item=item)
        layout2 = Layout((f1, f3), "fused", 1.0)
        summary = summarize_interior_parts(layout2, scoop=True)
        self.assertIn("Divider", summary)
        self.assertIn("Cradle (Pencil)", summary)
        self.assertIn("Scoop", summary)

    def test_log_bin_to_folder_creates_and_appends(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "My Drawer"
            out_dir.mkdir(parents=True, exist_ok=True)
            box = BoxSpec(40.0, 48.0, 40.0)
            layout = Layout((), "fused", 1.0)

            # 1. Create initial log
            log_file = log_bin_to_folder(
                out_dir,
                box,
                layout,
                generated_files=[out_dir / "Box 40 x 48 x 40.3mf"],
                label="TOOLS",
                part_name="Tools",
            )
            self.assertTrue(log_file.is_file())
            self.assertEqual(log_file.name, "My Drawer bins.md")

            content = log_file.read_text(encoding="utf-8")
            self.assertIn("# My Drawer Bins", content)
            self.assertIn("| Date | File | X (mm) | Y (mm) | Z (mm) | Label | Interior Part(s) |", content)
            self.assertIn("Box 40 x 48 x 40.3mf", content)
            self.assertIn("| 40 | 48 | 40 |", content)
            self.assertIn("| TOOLS |", content)
            self.assertIn("| None |", content)

            # 2. Append second bin to same log
            box2 = BoxSpec(32.0, 32.0, 24.0)
            f = Feature("divider", Zone(0, 0, 10, 10))
            layout2 = Layout((f,), "fused", 1.0)
            log_file2 = log_bin_to_folder(
                out_dir,
                box2,
                layout2,
                generated_files=[out_dir / "Box 32 x 32 x 24.3mf"],
                label="",
                part_name="",
                scoop=True,
            )
            self.assertEqual(log_file, log_file2)
            content2 = log_file2.read_text(encoding="utf-8")
            # Both entries must be present
            self.assertIn("Box 40 x 48 x 40.3mf", content2)
            self.assertIn("Box 32 x 32 x 24.3mf", content2)
            self.assertIn("| 32 | 32 | 24 |", content2)
            self.assertIn("Divider, Scoop", content2)

    def test_generate_organizer_files_keep_log(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "TestFolder"
            out_dir.mkdir(parents=True, exist_ok=True)
            box = BoxSpec(32.0, 32.0, 32.0)
            layout = Layout((), "fused", 1.0)

            # With keep_log=False
            res1 = generate_organizer_files(box, layout, out_dir, keep_log=False)
            self.assertNotIn("log_file", res1)
            self.assertFalse((out_dir / "TestFolder bins.md").exists())

            # With keep_log=True
            res2 = generate_organizer_files(
                box, layout, out_dir, label="TEST", label_location="top", keep_log=True
            )
            self.assertIn("log_file", res2)
            log_path = Path(str(res2["log_file"]))
            self.assertTrue(log_path.exists())
            self.assertEqual(log_path.name, "TestFolder bins.md")
            content = log_path.read_text(encoding="utf-8")
            self.assertIn("| TEST |", content)
            self.assertIn("| 32 | 32 | 32 |", content)

    def test_wavefinity_web_preferences_keep_log(self):
        res = wavefinity_web.preferences_payload({"keep_log": False})
        self.assertIn("preferences", res)
        self.assertFalse(res["preferences"].get("keep_log", True))

        # Restore
        wavefinity_web.preferences_payload({"keep_log": True})
        self.assertTrue(wavefinity_web.load_preferences().get("keep_log", True))


if __name__ == "__main__":
    unittest.main()
