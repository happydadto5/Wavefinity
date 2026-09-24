"""Space-owned structural outputs and the Storage Box case settings (Fix 048C)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import wavefinity_web
from organizer_inventory import (
    configure_space,
    configure_space_text,
    load_inventory,
    load_inventory_text,
    normalise_space_definition,
    normalise_storage_box,
    storage_box_defaults,
)
from organizer_space_outputs import (
    STORAGE_BOX,
    BASE_TRIM,
    base_trim_design,
    storage_box_design,
    structural_kind,
)
from organizer_spaces import describe

CASE = {"name": "Screw case", "kind": "portable", "x": 96, "y": 96, "z": 40}
SURFACE = {"name": "Bench", "kind": "surface", "x": 200, "y": 160, "z": 7.5, "trim_size": "medium"}


class FourSpaceTypeTests(unittest.TestCase):
    def test_all_four_user_facing_types_create_edit_and_load(self):
        cases = [
            {"name": "Utensils", "kind": "drawer", "x": 200, "y": 200, "z": 60},
            CASE,
            SURFACE,
            {"name": "Tool wall", "kind": "pegboard", "x": 500, "y": 300, "z": 350,
             "pegboard_standard": "standard", "pegboard_size_mode": "physical"},
        ]
        for raw in cases:
            with self.subTest(kind=raw["kind"]), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / raw["name"]
                made = configure_space(folder, raw_def=raw)
                self.assertEqual(made["layout"]["space"]["kind"], raw["kind"])
                edited = configure_space(folder, raw_def={**raw, "name": raw["name"] + " 2"}, mode="update")
                self.assertEqual(edited["layout"]["space"]["name"], raw["name"] + " 2")
                self.assertEqual(load_inventory(folder)["layout"]["space"]["kind"], raw["kind"])
        names = sorted({"Drawer", "Storage Box", "Surface", "Pegboard"})
        spaces_js = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        kinds = spaces_js[spaces_js.index("const SP_KINDS = {"):spaces_js.index("const FOLDER_METADATA")]
        for name in names:
            self.assertIn(f'label: "{name}"', kinds)


class StorageBoxBlockTests(unittest.TestCase):
    def test_defaults_are_complete_and_carry_no_redundant_flags(self):
        block = normalise_storage_box(None)
        self.assertEqual(block, storage_box_defaults())
        for key in ("secure_lid", "latch_count", "latch_strength", "lid_headroom_mm", "label_enabled",
                    "label_text", "label_location", "front_label_style", "stacking", "handle",
                    "wall_mm", "base_mm"):
            self.assertIn(key, block)
        self.assertNotIn("enabled", block)
        self.assertNotIn("lid", block)

    def test_values_are_validated(self):
        ok = normalise_storage_box({"secure_lid": False, "lid_headroom_mm": 2, "wall_mm": 2.0,
                                    "label_enabled": True, "label_text": " M3 ", "label_location": "front"})
        self.assertFalse(ok["secure_lid"])
        self.assertEqual(ok["label_text"], "M3")
        self.assertEqual(ok["wall_mm"], 2.0)
        for bad in ({"lid_headroom_mm": 3}, {"latch_count": "9"}, {"label_location": "side"},
                    {"wall_mm": 0.01}, {"base_mm": "x"}, {"stacking": "yes"}, {"handle": 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalise_storage_box(bad)
        with self.assertRaises(ValueError):
            normalise_storage_box("nope")

    def test_only_storage_box_spaces_carry_the_block(self):
        self.assertIn("storage_box", normalise_space_definition(CASE))
        self.assertNotIn("storage_box", normalise_space_definition(SURFACE))
        drawer = normalise_space_definition({"name": "D", "kind": "drawer", "x": 200, "y": 200, "z": 60})
        self.assertNotIn("storage_box", drawer)
        legacy = normalise_space_definition({**CASE, "kind": "box"}, allow_legacy=True)
        self.assertEqual(legacy["kind"], "portable")
        self.assertIn("storage_box", legacy)


class StorageBoxRoundTripTests(unittest.TestCase):
    def test_local_create_update_and_describe_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Case"
            box = {**storage_box_defaults(), "stacking": True, "wall_mm": 2.0, "base_mm": 2.0}
            made = configure_space(folder, raw_def={**CASE, "storage_box": box})
            self.assertEqual(made["layout"]["space"]["storage_box"], normalise_storage_box(box))
            # The metadata/describe path reads the same block back.
            from organizer_spaces import _write_metadata
            _write_metadata(folder, "space", made["layout"]["space"])
            info = describe(folder, {})
            self.assertEqual(info["space"]["storage_box"], normalise_storage_box(box))
            # A resize that does not send the block keeps the saved settings.
            updated = configure_space(folder, raw_def={**CASE, "x": 104}, mode="update")
            self.assertEqual(updated["layout"]["space"]["x"], 104.0)
            self.assertEqual(updated["layout"]["space"]["storage_box"], normalise_storage_box(box))
            # Sending a new block replaces it.
            changed = configure_space(folder, raw_def={**CASE, "storage_box": {"handle": True}}, mode="update")
            self.assertTrue(changed["layout"]["space"]["storage_box"]["handle"])
            self.assertFalse(changed["layout"]["space"]["storage_box"]["stacking"])

    def test_hosted_text_round_trip_matches_local(self):
        box = {**storage_box_defaults(), "label_enabled": True, "label_text": "Bits", "label_location": "top"}
        made = configure_space_text("", title="Case", raw_def={**CASE, "storage_box": box})
        text = made["inventory_text"]
        self.assertEqual(made["layout"]["space"]["storage_box"], normalise_storage_box(box))
        reloaded = load_inventory_text(text, title="Case")
        self.assertEqual(reloaded["layout"]["space"]["storage_box"], normalise_storage_box(box))
        kept = configure_space_text(text, title="Case", raw_def={**CASE, "y": 104}, mode="update")
        self.assertEqual(kept["layout"]["space"]["storage_box"], normalise_storage_box(box))
        self.assertEqual(kept["layout"]["space"]["y"], 104.0)

    def test_a_legacy_portable_space_without_the_block_reads_defaults_without_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Legacy"
            folder.mkdir()
            from organizer_spaces import _write_metadata
            _write_metadata(folder, "space", {"kind": "portable", "name": "Old", "x": 96.0, "y": 96.0, "z": 40.0},
                            keep_bin_defaults=True)
            info = describe(folder, {})
            self.assertEqual(info["space"]["storage_box"], storage_box_defaults())
            self.assertFalse((folder / "Wavefinity bins.md").exists())


class StructuralOutputTests(unittest.TestCase):
    def test_kind_ownership(self):
        self.assertEqual(structural_kind(CASE), STORAGE_BOX)
        self.assertEqual(structural_kind({**CASE, "kind": "box"}), STORAGE_BOX)
        self.assertEqual(structural_kind(SURFACE), BASE_TRIM)
        self.assertIsNone(structural_kind({"kind": "drawer"}))
        self.assertIsNone(structural_kind({"kind": "pegboard"}))
        self.assertIsNone(structural_kind(None))

    def test_storage_box_design_is_an_empty_layout_b4b_from_space_and_settings(self):
        design = storage_box_design({**CASE, "storage_box": {"stacking": True, "wall_mm": 2.0, "base_mm": 2.4}})
        self.assertTrue(design["box"]["b4b"]["enabled"])
        self.assertTrue(design["box"]["b4b"]["stacking"])
        self.assertEqual((design["box"]["x"], design["box"]["y"], design["box"]["z"]), (96.0, 96.0, 40.0))
        self.assertEqual(design["box"]["wall"], 2.0)
        self.assertEqual(design["box"]["base_thickness"], 2.4)
        self.assertEqual(design["layout"]["features"], [])
        self.assertEqual(design["part_name"], "Screw case")

    def test_base_trim_design_comes_from_the_surface_definition(self):
        design = base_trim_design(SURFACE, bed_x_mm=300, bed_y_mm=280)
        self.assertEqual(design["design_kind"], "base_trim")
        self.assertEqual((design["box"]["x"], design["box"]["y"]), (200.0, 160.0))
        self.assertEqual(design["base_trim"]["width_mm"], 7.5)
        self.assertEqual((design["base_trim"]["bed_x_mm"], design["base_trim"]["bed_y_mm"]), (300.0, 280.0))
        with self.assertRaises(ValueError):
            base_trim_design(SURFACE, bed_x_mm=-1)
        with self.assertRaises(ValueError):
            base_trim_design(CASE)
        with self.assertRaises(ValueError):
            storage_box_design(SURFACE)

    def test_design_payload_summarises_and_wrong_types_are_refused(self):
        box = wavefinity_web.structural_design_payload({"space": CASE})
        self.assertEqual(box["kind"], "storage_box")
        self.assertIn("assembled_envelope_mm", box["summary"])
        trim = wavefinity_web.structural_design_payload({"space": SURFACE})
        self.assertEqual(trim["kind"], "base_trim")
        with self.assertRaises(ValueError):
            wavefinity_web.structural_design_payload({"space": {"name": "D", "kind": "drawer", "x": 200, "y": 200, "z": 60}})

    def test_routes_are_registered(self):
        for path in ("/api/space/structural-design", "/api/space/structural-generate",
                     "/api/space/structural-print"):
            self.assertIn(path, wavefinity_web.POST_ROUTES)

    def test_save_writes_files_but_never_an_inventory_row(self):
        for space in (CASE, SURFACE):
            with self.subTest(kind=space["kind"]), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "Space"
                configure_space(folder, raw_def=space)
                before = load_inventory(folder)
                result = wavefinity_web.structural_generate_payload({"space": space, "output": str(folder)})
                self.assertTrue(list(folder.glob("*.3mf")))
                self.assertNotIn("inventory_bin", result)
                after = load_inventory(folder)
                self.assertEqual(after["bins"], before["bins"])
                self.assertEqual(after["layout"].get("design_specs", {}), before["layout"].get("design_specs", {}))

    def test_print_hands_off_to_the_slicer_and_never_logs_an_inventory_row(self):
        for space in (CASE, SURFACE):
            with self.subTest(kind=space["kind"]), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "Space"
                configure_space(folder, raw_def=space)
                before = load_inventory(folder)
                fake_exe = Path(tmp) / "slicer.exe"
                fake_exe.write_text("x")
                with patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe), \
                        patch.object(wavefinity_web, "launch_slicer", return_value=None) as launch, \
                        patch.object(wavefinity_web, "append_bin") as append:
                    result = wavefinity_web.structural_print_payload({"space": space, "output": str(folder)})
                append.assert_not_called()
                launch.assert_called_once()
                self.assertTrue(result["design_files"])
                self.assertEqual(load_inventory(folder)["bins"], before["bins"])

    def test_an_ordinary_bin_print_still_logs_but_structural_flag_suppresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_exe = Path(tmp) / "slicer.exe"
            fake_exe.write_text("x")
            design = wavefinity_web.default_design()
            with patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe), \
                    patch.object(wavefinity_web, "launch_slicer", return_value=None), \
                    patch.object(wavefinity_web, "inventory_enabled", return_value=True), \
                    patch.object(wavefinity_web, "append_bin") as append:
                wavefinity_web.print_payload({"design": design, "output": tmp, "structural_output": True})
                append.assert_not_called()
                wavefinity_web.print_payload({"design": design, "output": tmp})
                append.assert_called_once()


if __name__ == "__main__":
    unittest.main()
