"""Space-owned structural outputs and the Storage Box case settings (Fix 048C)."""

from __future__ import annotations

import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from space_source import spaces_source
from unittest.mock import patch

import trimesh

import organizer_drawer
import wavefinity_web
from organizer_inventory import (
    append_bin,
    save_inventory,
    configure_space,
    configure_space_text,
    load_inventory,
    load_inventory_text,
    normalise_space_definition,
    normalise_storage_box,
    storage_box_defaults,
)
from organizer_outputs.space import (
    STORAGE_BOX,
    BASE_TRIM,
    base_trim_design,
    storage_box_design,
    structural_kind,
)
from organizer_spaces import _write_metadata, describe
import organizer_storage.drawer_outputs as cabinet_outputs
from organizer_engine import BASE_UNIT
from organizer_storage.drawer_geometry import _make_datum, resolve_storage_drawers_plan
from organizer_storage.drawers import prepare_new_storage_drawers_definition

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
        spaces_js = spaces_source(Path(__file__).resolve().parent.parent / "web")
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



class StructuralOutputTests(unittest.TestCase):

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



    def test_save_writes_files_but_never_an_inventory_row(self):
        for space in (CASE, SURFACE):
            with self.subTest(kind=space["kind"]), tempfile.TemporaryDirectory() as tmp:
                folder = Path(tmp) / "Space"
                made = configure_space(folder, raw_def=space)
                payload = {"space": space, "output": str(folder)}
                if space["kind"] == "surface":
                    # Base Trim Save records its manifest under the typed Space's identity,
                    # so it is only supported for a real typed Surface folder.
                    _write_metadata(folder, "space", made["layout"]["space"])
                    payload["space_id"] = describe(folder, {})["space_id"]
                before = load_inventory(folder)
                with patch.object(wavefinity_web, "load_preferences", return_value={}):
                    result = wavefinity_web.structural_generate_payload(payload)
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



def _cabinet(style="full", frame=14.0, **extra):
    block = {"drawers": [{"id": "00000000-0000-4000-8000-000000000001", "height_mm": 20}], "cabinet_style": style, "open_frame_width_mm": frame,
             "drawer_handles": False, **extra}
    return prepare_new_storage_drawers_definition({
        "kind": "storage_drawers", "name": "Hardening", "x": 6 * BASE_UNIT, "y": 6 * BASE_UNIT,
        "storage_drawers": block})


class StorageDrawersHardeningTests(unittest.TestCase):
    """Fix 086: the hard-to-prove Storage Drawers behaviours, in one selection."""

    # Base and Top only fit rotated on this bed, so the export must apply it.
    PROFILE = {"x_mm": 62.0, "y_mm": 75.0, "z_mm": 30.0}

    @classmethod
    def setUpClass(cls):
        cls.space = _cabinet(unit_label_enabled=True, unit_label_text="Hi")
        cls.real = resolve_storage_drawers_plan(cls.space, build_meshes=True)
        cls.nominal = resolve_storage_drawers_plan(cls.space, build_meshes=False)

    def _install_plan(self):
        real = self.real
        original = cabinet_outputs.resolve_storage_drawers_plan

        def cached(space, *, build_meshes=True):
            return real if build_meshes else original(space, build_meshes=False)
        patcher = patch.object(cabinet_outputs, "resolve_storage_drawers_plan", cached)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_full_and_open_core_components_are_printable_solids(self):
        for style in ("full", "open"):
            plan = self.real if style == "full" else resolve_storage_drawers_plan(_cabinet("open"), build_meshes=True)
            core = [c for c in plan.components if not c.key.startswith(("drawer:", "stack_peg"))]
            self.assertEqual(len(core), 5, style)
            for component in core:
                mesh = component.mesh
                with self.subTest(style=style, part=component.key):
                    self.assertTrue(mesh.is_watertight)
                    self.assertTrue(mesh.is_winding_consistent)
                    self.assertGreater(mesh.volume, 0)
                    self.assertEqual(len(mesh.split(only_watertight=False)), 1)
        # The summary's nominal bounds may never promise less than the real build.
        for nominal, real in zip(self.nominal.components, self.real.components):
            self.assertEqual(nominal.key, real.key)
            for want, got in zip(nominal.bounds_xyz, real.bounds_xyz):
                self.assertGreaterEqual(want + 1e-3, got, real.key)

    def test_stop_root_is_flush_and_bump_stays_attached(self):
        drawers = [{"id": f"00000000-0000-4000-8000-{i:012d}", "height_mm": 20}
                   for i in range(1, 4)]
        for style in ("full", "open"):
            for fit in (0.30, 0.40, 0.60):
                space = _cabinet(style, drawers=drawers, drawer_fit_mm=fit)
                datum = _make_datum(space)
                self.assertAlmostEqual(datum.fit, fit)
                plan = resolve_storage_drawers_plan(space, build_meshes=True)
                for left in (True, False):
                    key = ("side_" if style == "full" else "frame_") + ("left" if left else "right")
                    mesh = next(c.mesh for c in plan.components if c.key == key)
                    field_left = (datum.outer_x-datum.field_x)/2
                    body_edge = (field_left-datum.drawer_wall if left else
                                 field_left+datum.field_x+datum.drawer_wall)
                    stop_a, stop_b = ((body_edge-1.4+fit, body_edge-0.2) if left else
                                      (body_edge+0.2, body_edge+1.4-fit))
                    inner = datum.track_reach if left else datum.outer_x-datum.track_reach
                    gap_x = (inner + (stop_a if left else stop_b))/2
                    bump_x = (stop_a+stop_b)/2
                    with self.subTest(style=style, fit=fit, side=key):
                        self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                        for interior_floor in datum.floors:
                            z = interior_floor-datum.drawer_base-fit+0.1
                            y = datum.front+3+12+4
                            self.assertEqual(mesh.contains([[gap_x, y, z], [bump_x, y, z]]).tolist(),
                                             [False, True])

    def test_export_applies_the_orientation_the_fit_check_chose(self):
        self._install_plan()
        with tempfile.TemporaryDirectory() as tmp:
            result = cabinet_outputs.materialize_storage_drawers(self.space, Path(tmp), self.PROFILE, None)
            by_key = {item["key"]: item for item in result["manifest"]["components"]}
            self.assertEqual(by_key["cabinet_base"]["orientation"], "bed_90")
            self.assertEqual(by_key["cabinet_top"]["orientation"], "bed_90")
            bed = (self.PROFILE["x_mm"], self.PROFILE["y_mm"], self.PROFILE["z_mm"])
            for path, item in zip(result["files"], result["manifest"]["components"]):
                scene = trimesh.load(path, force="scene")
                self.assertTrue(all(size <= limit + 1e-6 for size, limit in zip(scene.extents, bed)), item["key"])
                self.assertTrue(all(abs(v) < 1e-3 for v in scene.bounds[0]), item["key"])
            top = next(c for c in self.real.components if c.key == "cabinet_top")
            self.assertTrue(top.object_groups)  # the unit label rotates with its body
            self.assertGreater(top.bounds_xyz[0], self.PROFILE["x_mm"])  # unrotated it would not fit

    def test_local_commit_failure_restores_pre_attempt_files_and_is_not_poisoned(self):
        self._install_plan()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)

            def fail(_manifest):
                raise RuntimeError("metadata write failed")
            with self.assertRaises(RuntimeError):
                cabinet_outputs.materialize_storage_drawers(self.space, folder, self.PROFILE, None, commit=fail)
            self.assertEqual(list(folder.iterdir()), [])
            saved = {}
            first = cabinet_outputs.materialize_storage_drawers(
                self.space, folder, self.PROFILE, None, commit=lambda manifest: saved.update(manifest))
            before = {path.name: path.read_bytes() for path in folder.glob("*.3mf")}
            self.assertEqual(len(before), len(first["files"]))
            with self.assertRaises(RuntimeError):
                cabinet_outputs.materialize_storage_drawers(self.space, folder, self.PROFILE, saved, commit=fail)
            self.assertEqual({p.name: p.read_bytes() for p in folder.glob("*.3mf")}, before)
            self.assertEqual({p.name for p in folder.iterdir()}, set(before))
            # Not a false "changed outside Wavefinity" conflict: the next save succeeds.
            cabinet_outputs.materialize_storage_drawers(self.space, folder, self.PROFILE, saved, commit=lambda m: None)

    def test_saved_status_checks_manifest_shape_and_file_hashes(self):
        self._install_plan()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            manifest = cabinet_outputs.materialize_storage_drawers(self.space, folder, self.PROFILE, None)["manifest"]

            def status(stored):
                return cabinet_outputs.structural_status(self.space, stored, folder, self.PROFILE)["status"]
            self.assertEqual(status(manifest), "saved")
            target = folder / manifest["components"][0]["filename"]
            target.write_bytes(target.read_bytes() + b"x")
            self.assertEqual(status(manifest), "need_save")
            self.assertEqual(status({**manifest, "components": None}), "need_save")
            with self.assertRaises(ValueError) as caught:
                cabinet_outputs.materialize_storage_drawers(self.space, folder, self.PROFILE, {"components": None})
            self.assertIn("Previous cabinet manifest is invalid", str(caught.exception))

    def test_saved_status_requires_exact_plan_set_with_or_without_profile(self):
        self._install_plan()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            manifest = cabinet_outputs.materialize_storage_drawers(
                self.space, source, self.PROFILE, None)["manifest"]
            expected = cabinet_outputs.structural_manifest_plan(
                self.space, source, self.PROFILE)["components"]

            def copied_folder(name):
                folder = root / name
                shutil.copytree(source, folder)
                return folder

            complete = copied_folder("complete")
            self.assertEqual(cabinet_outputs.structural_status(
                self.space, manifest, complete)["status"], "saved")

            for index, row in enumerate(manifest["components"]):
                with self.subTest(missing=row["key"]):
                    damaged = [dict(item) for item in manifest["components"] if item["key"] != row["key"]]
                    folder = copied_folder(f"missing-{index}")
                    (folder / row["filename"]).unlink()
                    stored = {**manifest, "components": damaged}
                    self.assertEqual(cabinet_outputs.structural_status(
                        self.space, stored, folder)["status"], "need_save")

            duplicate = [dict(item) for item in manifest["components"]]
            duplicate[-1] = dict(duplicate[0])
            folder = copied_folder("duplicate")
            self.assertEqual(cabinet_outputs.structural_status(
                self.space, {**manifest, "components": duplicate}, folder)["status"], "need_save")

            mismatch = [dict(item) for item in manifest["components"]]
            target = next((i for i, row in enumerate(mismatch) if row["key"] == "drawer-2"), None)
            if target is None:
                target = 0
            foreign = dict(mismatch[target])
            foreign["key"] = "foreign-component"
            mismatch[target] = foreign
            folder = copied_folder("foreign-key")
            self.assertEqual(cabinet_outputs.structural_status(
                self.space, {**manifest, "components": mismatch}, folder)["status"], "need_save")

            mismatch = [dict(item) for item in manifest["components"]]
            source_row = mismatch[0]
            other_row = next(item for item in mismatch if item["key"] != source_row["key"])
            altered = dict(source_row)
            altered["filename"] = other_row["filename"]
            altered["sha256"] = cabinet_outputs._hash(source / other_row["filename"])
            mismatch[0] = altered
            folder = copied_folder("key-filename-mismatch")
            self.assertEqual(cabinet_outputs.structural_status(
                self.space, {**manifest, "components": mismatch}, folder)["status"], "need_save")

            # Profile-free checks still compare expected key/filename pairs and
            # must preserve the ordinary complete-manifest saved result.
            self.assertEqual(len(expected), len(manifest["components"]))

    def test_full_ignores_the_hidden_open_frame_width_and_open_uses_it(self):
        narrow, wide = _cabinet("full", 10.0), _cabinet("full", 18.0)
        self.assertEqual(_make_datum(narrow).frame, _make_datum(wide).frame)
        self.assertEqual(cabinet_outputs.structural_signature(narrow), cabinet_outputs.structural_signature(wide))
        self.assertEqual(cabinet_outputs.effective_structural_state(narrow), cabinet_outputs.effective_structural_state(wide))
        open_narrow, open_wide = _cabinet("open", 10.0), _cabinet("open", 18.0)
        self.assertLess(_make_datum(open_narrow).frame, _make_datum(open_wide).frame)
        self.assertNotEqual(cabinet_outputs.structural_signature(open_narrow), cabinet_outputs.structural_signature(open_wide))


def _two_saved_rows(folder):
    """Create two real bin rows and place both in drawer 1. Returns (bin_a_id, bin_b_id)."""
    spec = {"layout": {}}
    append_bin(folder, file="bin-a.3mf", x=48, y=48, z=40, name="Bin A",
               design_spec=spec, object_height_mm=40.0)
    append_bin(folder, file="bin-b.3mf", x=48, y=48, z=40, name="Bin B",
               design_spec=spec, object_height_mm=40.0)
    inv = load_inventory(folder)
    rows = inv["bins"]
    assert len(rows) == 2, "fixture needs exactly two real rows"
    layout = inv["layout"]
    layout["drawers"][0]["placements"] = [{"bin": r["id"]} for r in rows]
    save_inventory(folder, layout=layout)
    rows = load_inventory(folder)["bins"]
    assert all(r["status"] == "saved" and r["qty"] == 0 for r in rows)
    return rows[0]["id"], rows[1]["id"]


def _failed_stub(folder, inv, bin_a, bin_b):
    return {
        "root": folder, "inventory": inv, "files": {}, "specs": {},
        "generated": [bin_a], "reused": [],
        "failed": {"id": bin_b, "name": "Bin B", "error": "export failed"},
        "unfinished": [bin_b],
    }


class _Fix1102Mixin:
    def _assert_rows_saved(self, folder, bin_a, bin_b):
        after = load_inventory(folder)["bins"]
        self.assertEqual(len(after), 2, "printed-state assertions need the two real rows")
        by_id = {r["id"]: r for r in after}
        for one in (bin_a, bin_b):
            self.assertEqual(by_id[one]["status"], "saved")
            self.assertEqual(by_id[one]["qty"], 0)
        self.assertFalse(any(r["status"] == "printed" for r in after))


class Fix1102CombinedPrintFailureTests(_Fix1102Mixin, unittest.TestCase):
    def test_partial_result_names_slicer_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Space"
            space = _cabinet()
            made = configure_space(folder, raw_def=space)
            _write_metadata(folder, "space", made["layout"]["space"])
            bin_a, bin_b = _two_saved_rows(folder)
            payload = {"space": space, "output": str(folder)}
            payload["space_id"] = describe(folder, {})["space_id"]
            fake_exe = Path(tmp) / "bambu-studio.exe"
            fake_exe.write_text("x")
            stub = _failed_stub(folder, load_inventory(folder), bin_a, bin_b)
            with patch.object(wavefinity_web, "load_preferences", return_value={}),                  patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),                  patch.object(wavefinity_web, "selected_blocking_problems", return_value=[]),                  patch.object(wavefinity_web, "_materialize_local_cabinet", return_value={"files": []}),                  patch.object(wavefinity_web, "prepare_inventory_bins", return_value=stub),                  patch.object(wavefinity_web, "launch_slicer", return_value=None) as launch:
                result = wavefinity_web.structural_print_combined_payload(payload)
            self.assertIs(result["partial"], True)
            self.assertEqual(result["partial_stage"], "generate")
            self.assertEqual(
                result["error"],
                "Cabinet files were saved, but the bins could not be prepared: Could not prepare Bin B: "
                "export failed. 1 bin saved before it stopped. Bambu Studio was not opened. Retry to finish the rest.")
            self.assertIn("bins", result)
            self.assertIn("layout", result)
            launch.assert_not_called()
            self._assert_rows_saved(folder, bin_a, bin_b)

    def test_old_keyword_is_invalid(self):
        with self.assertRaises(TypeError):
            wavefinity_web._prepare_failure_text({}, slicer=True)

    def test_import_binding(self):
        from organizer_drawer._inventory import _prepare_failure_text
        self.assertIs(wavefinity_web._prepare_failure_text, _prepare_failure_text)


class Fix1102PrintCompleteFailureTests(_Fix1102Mixin, unittest.TestCase):
    def test_value_error_names_detected_slicer(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "Space"
            space = _cabinet()
            configure_space(folder, raw_def=space)
            bin_a, bin_b = _two_saved_rows(folder)
            inv = load_inventory(folder)
            fake_exe = Path(tmp) / "bambu-studio.exe"
            fake_exe.write_text("x")
            stub = _failed_stub(folder, inv, bin_a, bin_b)
            launched = []
            routes = organizer_drawer.drawer_routes(
                threading.Lock(), Path(tmp),
                detect_slicer=lambda p: fake_exe,
                launch_slicer=lambda *a: launched.append(a),
                hosted=False)
            print_complete = routes["/api/drawer/print-complete"]
            with patch.object(organizer_drawer, "selected_blocking_problems", return_value=[]),                  patch.object(organizer_drawer, "prepare_inventory_bins", return_value=stub):
                with self.assertRaises(ValueError) as ctx:
                    print_complete({"output": str(folder), "drawer_id": inv["layout"]["drawers"][0]["id"]})
            message = str(ctx.exception)
            self.assertEqual(
                message,
                "The bins could not be prepared: Could not prepare Bin B: export failed. "
                "1 bin saved before it stopped. Bambu Studio was not opened. Retry to finish the rest.")
            self.assertEqual(message.count("was not opened."), 1)
            self.assertEqual(launched, [])
            self._assert_rows_saved(folder, bin_a, bin_b)


if __name__ == "__main__":
    unittest.main()
