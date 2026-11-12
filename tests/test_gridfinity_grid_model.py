"""Story 2968: grid identity and atomic entry refusal; no geometry builds."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from organizer_engine import BoxSpec
from organizer_engine._specs import GRID_PITCHES
from organizer_inserts import Layout
from organizer_app_impl._design_io import design_from_dict, design_to_dict, design_source_payload
from organizer_inventory import configure_space_text, duplicate_design_source_text, save_design_source_text
from organizer_inventory._rows import (
    checked_design_entry, parse_inventory, render_inventory, resolve_source_grid,
)
from organizer_inventory._space import normalise_space_definition, storage_box_defaults
from organizer_inventory._merge import _merge_inventory
from organizer_spaces._core import _space, METADATA_FILE, _metadata_resume
from organizer_spaces import _write_metadata, space_routes
from organizer_storage.drawers import storage_drawers_defaults, normalise_storage_drawers_definition, plan_reconfigure
from wavefinity_web_impl._designs._layout import copy_space_text_payload, create_space_text_payload
from wavefinity_web_impl._ai import ai_context_grid
import wavefinity_web as web


def design(grid=None):
    result = design_to_dict(BoxSpec(x=42.0, y=42.0, z=40.0), Layout(), part_name="Tools")
    if grid is None:
        result.pop("grid")
    else:
        result["grid"] = grid
    return result


def space(grid=None, kind="drawer"):
    result = {"name": "Tools", "kind": kind, "x": 210, "y": 210, "z": 70}
    if grid is not None:
        result["grid"] = grid
    if kind == "surface":
        result.update(trim_size="small", z=4)
    return result


def inventory(grid, nested_grid=None):
    spec = design(nested_grid)
    _, row = design_source_payload(spec)
    row.update(id="B1", name="Tools", qty=0)
    layout = {"version": 1, "space": space(grid), "design_specs": {"B1": spec},
              "drawers": [], "active": None}
    return render_inventory("Tools", [row], layout)


class GridModelTests(unittest.TestCase):
    def test_space_defaults_and_invalid_values(self):
        self.assertEqual(GRID_PITCHES, {"wavefinity": 7.0, "gridfinity_half": 21.0, "gridfinity": 42.0})
        for grid in GRID_PITCHES:
            self.assertEqual(normalise_space_definition(space(grid))["grid"], grid)
            self.assertEqual(_space(space(grid))["grid"], grid)
        self.assertEqual(normalise_space_definition(space())["grid"], "wavefinity")
        for invalid in (None, "", "Gridfinity", "other", [], 42):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                normalise_space_definition(space(invalid) | {"grid": invalid})

    def test_design_round_trip_keeps_all_existing_values(self):
        legacy = design()
        restored = design_to_dict(*design_from_dict(legacy))
        self.assertEqual(restored.pop("grid"), "wavefinity")
        self.assertEqual(json.dumps(restored, separators=(",", ":")), json.dumps(legacy, separators=(",", ":")))
        legacy_space = {"kind": "drawer", "name": "Tools", "x": 210.0, "y": 210.0, "z": 70.0}
        restored_space = _space(legacy_space)
        self.assertEqual(restored_space.pop("grid"), "wavefinity")
        self.assertEqual(json.dumps(restored_space), json.dumps(legacy_space))
        for grid in GRID_PITCHES:
            self.assertEqual(design_to_dict(*design_from_dict(design(grid)))["grid"], grid)
        for invalid in (None, "", "bad", [], 21):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                design_from_dict(design() | {"grid": invalid})

    def test_printed_container_defaults_only(self):
        self.assertEqual(storage_box_defaults()["built_in_grid"], "floor")
        self.assertEqual(storage_drawers_defaults()["built_in_grid"], "floor")
        self.assertNotIn("built_in_grid", normalise_space_definition(space()))
        portable = normalise_space_definition(space("gridfinity", "portable"))
        self.assertEqual(portable["built_in_grid"], "floor")
        self.assertEqual(portable["storage_box"]["grid"], "gridfinity")
        cabinet = space("gridfinity_half", "storage_drawers")
        block = storage_drawers_defaults(1)
        block["grid"] = "gridfinity_half"
        cabinet["storage_drawers"] = block
        canonical = normalise_storage_drawers_definition(cabinet)
        self.assertEqual(canonical["built_in_grid"], "floor")
        proposed = copy.deepcopy(canonical)
        proposed.pop("grid")
        self.assertEqual(plan_reconfigure(canonical, {"space": canonical}, proposed, [])[0]["grid"], "gridfinity_half")
        proposed["grid"] = "wavefinity"
        with self.assertRaises(ValueError):
            plan_reconfigure(canonical, {"space": canonical}, proposed, [])

    def test_configure_immutable_but_ordinary_edits_work(self):
        for grid in ("gridfinity_half", "gridfinity"):
            created = configure_space_text("", title="Tools", raw_def=space(grid, "portable"))
            text = created["inventory_text"]
            edited = space(kind="portable") | {"name": "Renamed", "x": 252}
            result = configure_space_text(text, title="Tools", raw_def=edited, mode="update")
            saved = result["layout"]["space"]
            self.assertEqual((saved["grid"], saved["x"], saved["built_in_grid"]), (grid, 252, "floor"))
            # Story 2975: the floor is fixed at creation, like the grid.
            with self.assertRaisesRegex(ValueError, "floor is immutable"):
                configure_space_text(text, title="Tools", raw_def=edited | {"built_in_grid": "none"}, mode="update")
            for bad in ("wavefinity", "invalid"):
                with self.assertRaises(ValueError):
                    configure_space_text(text, title="Tools", raw_def=edited | {"grid": bad}, mode="update")
            self.assertEqual(created["inventory_text"], text)

    def test_inherited_duplicate_copy_and_export_at_both_pitches(self):
        for grid in ("gridfinity_half", "gridfinity"):
            text = inventory(grid)
            duplicate = duplicate_design_source_text(text, "B1")
            self.assertEqual(duplicate["design"]["grid"], grid)
            self.assertEqual(len(duplicate["bins"]), 2)
            copied = copy_space_text_payload({"inventory_text": text, "name": "Copy"})
            parsed = parse_inventory(copied["inventory_text"])
            self.assertEqual(parsed["layout"]["space"]["grid"], grid)
            self.assertEqual(parsed["bins"][0]["grid"], grid)
            exported = design_to_dict(*design_from_dict(parsed["layout"]["design_specs"]["B1"]))
            self.assertEqual(exported["grid"], grid)

    def test_contradictory_nested_metadata_refused(self):
        for grid in ("gridfinity_half", "gridfinity"):
            text = inventory(grid, "wavefinity")
            for operation in (
                lambda: parse_inventory(text),
                lambda: duplicate_design_source_text(text, "B1"),
                lambda: copy_space_text_payload({"inventory_text": text, "name": "Copy"}),
            ):
                with self.assertRaises(ValueError):
                    operation()

    def test_source_and_destination_resolve_separately(self):
        for grid in ("gridfinity_half", "gridfinity"):
            source = parse_inventory(inventory(grid))
            raw = source["layout"]["design_specs"]["B1"]
            before = copy.deepcopy(source)
            with self.assertRaises(ValueError):
                checked_design_entry(raw, space("wavefinity"), source=source, row_id="B1")
            self.assertEqual(source, before)
            self.assertEqual(checked_design_entry(raw, space(grid), source=source, row_id="B1")["grid"], grid)
            with self.assertRaises(ValueError):
                resolve_source_grid(raw, source, "B999")
            with self.assertRaises(ValueError):
                resolve_source_grid(design() | {"space": space(grid)})
            with self.assertRaises(ValueError):
                checked_design_entry(design(), space(grid))

    def test_save_and_insertion_refuse_without_partial_mutation(self):
        for grid in ("gridfinity_half", "gridfinity"):
            text = inventory(grid)
            current = parse_inventory(text)
            before = copy.deepcopy(current)
            raw, row = design_source_payload(design())
            with self.assertRaises(ValueError):
                save_design_source_text(text, design=raw, record=row)
            with self.assertRaises(ValueError):
                _merge_inventory(current, new_bins=[row], new_bin_specs=[raw])
            self.assertEqual(current, before)
            changed_layout = copy.deepcopy(current["layout"])
            changed_layout["space"]["grid"] = "wavefinity"
            with self.assertRaises(ValueError):
                _merge_inventory(current, layout=changed_layout)
            with self.assertRaises(ValueError):
                _merge_inventory(current, layout=None)
            self.assertEqual(current, before)
            untyped = parse_inventory(inventory("wavefinity"))
            untyped["layout"].pop("space")
            untyped_text = render_inventory("Tools", untyped["bins"], untyped["layout"])
            with self.assertRaises(ValueError):
                configure_space_text(untyped_text, title="Tools", raw_def=space(grid))

    def test_api_open_load_import_restore_and_writers_reject(self):
        routes = ("/api/design/validate", "/api/drawer/design-source/save", "/api/drawer/save",
                  "/api/generate", "/api/print", "/api/layout/expand")
        for grid in ("gridfinity_half", "gridfinity"):
            text = inventory(grid)
            for route in routes:
                payload = {"inventory_text": text, "design": design()}
                with self.subTest(grid=grid, route=route), patch.object(web, "HOSTED", True), self.assertRaises(ValueError):
                    web.POST_ROUTES[route](payload)
                self.assertEqual(payload["inventory_text"], text)
            for key in ("design", "resume_design"):
                with patch.object(web, "HOSTED", True), self.assertRaises(ValueError):
                    web._checked_entry_payload({"inventory_text": text, key: design()})

    def test_api_checks_verified_source_before_destination(self):
        source = inventory("gridfinity")
        target = inventory("wavefinity")
        payload = {"inventory_text": target, "source_inventory_text": source,
                   "source_row_id": "B1", "design": design()}
        before = copy.deepcopy(payload)
        with patch.object(web, "HOSTED", True), self.assertRaises(ValueError):
            web._checked_entry_payload(payload)
        self.assertEqual(payload, before)
        with patch.object(web, "HOSTED", True), self.assertRaises(ValueError):
            web._checked_entry_payload(payload | {"source_row_id": "B999"})
        # A raw Space object cannot make an external legacy bin inherit a grid.
        with patch.object(web, "HOSTED", True), self.assertRaises(ValueError):
            web._checked_entry_payload({"inventory_text": source, "space": space("gridfinity"), "design": design()})
        for grid in ("gridfinity_half", "gridfinity"):
            text = inventory(grid)
            with patch.object(web, "HOSTED", True):
                result = web._checked_entry_payload({"inventory_text": text, "source_inventory_text": text,
                                                     "source_row_id": "B1", "design": design()})
            self.assertEqual(result["design"]["grid"], grid)

    def test_ai_checks_explicit_grid_before_context_stamping(self):
        for grid in ("gridfinity_half", "gridfinity"):
            self.assertEqual(ai_context_grid(design(), grid)["grid"], grid)
            self.assertEqual(ai_context_grid(design(grid), grid)["grid"], grid)
            for bad in ("wavefinity", "invalid", None):
                with self.assertRaises(ValueError):
                    ai_context_grid(design() | {"grid": bad}, grid)
            with patch.object(web, "_grid_inventory", return_value=({}, space(grid))), \
                 patch.object(web, "preview_payload") as preview:
                with self.assertRaises(ValueError):
                    web.ai_candidate_payload({"design": design("wavefinity")})
                preview.assert_not_called()
                preview.side_effect = lambda request: {"design": request["design"], "fits": True}
                self.assertEqual(web.ai_candidate_payload({"design": design()})["design"]["grid"], grid)
                self.assertEqual(web.ai_candidate_payload({"design": design(grid)})["design"]["grid"], grid)

    def test_local_metadata_and_checkpoint_retain_grid(self):
        for grid in ("gridfinity_half", "gridfinity"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                definition = normalise_space_definition(space(grid, "portable"))
                _write_metadata(root, "space", definition)
                path = root / METADATA_FILE
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    _write_metadata(root, "space", definition | {"grid": "wavefinity"})
                self.assertEqual(path.read_bytes(), before)
                with self.assertRaises(ValueError):
                    _write_metadata(root, "space", definition, resume_design=design())
                self.assertEqual(path.read_bytes(), before)
                _write_metadata(root, "space", definition, resume_design=design(grid), resume_pending=True)
                metadata = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(_space(metadata["space"])["grid"], grid)
                metadata["resume_design"].pop("grid")
                self.assertEqual(_metadata_resume(metadata, metadata["version"])[0]["grid"], grid)

    def test_local_api_uses_disk_and_refuses_without_writes(self):
        from organizer_inventory._rows import INVENTORY_FILENAME
        for grid in ("gridfinity_half", "gridfinity"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source, target = root / "Source", root / "Target"
                source.mkdir()
                target.mkdir()
                for folder, tag in ((source, grid), (target, "wavefinity")):
                    (folder / INVENTORY_FILENAME).write_text(inventory(tag), encoding="utf-8")
                    _write_metadata(folder, "space", normalise_space_definition(space(tag)))
                before = {path: path.read_bytes() for folder in (source, target) for path in folder.iterdir()}
                with patch.object(web, "HOSTED", False), patch.object(web, "load_preferences", return_value={}):
                    # A client snapshot cannot override the destination's disk record.
                    with self.assertRaises(ValueError):
                        web.POST_ROUTES["/api/drawer/design-source/save"]({
                            "output": str(source), "inventory_text": inventory("wavefinity"), "design": design()})
                    with self.assertRaises(ValueError):
                        web._validate_design_open_guard({"output": str(target), "source_output": str(source),
                                                         "source_row_id": "B1", "design": design()})
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_local_whole_space_copy_preserves_inherited_bins(self):
        from organizer_inventory._rows import INVENTORY_FILENAME
        for grid in ("gridfinity_half", "gridfinity"):
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "Tools"
                source.mkdir()
                inv = source / INVENTORY_FILENAME
                inv.write_text(inventory(grid), encoding="utf-8")
                _write_metadata(source, "space", normalise_space_definition(space(grid)))
                source_id = json.loads((source / METADATA_FILE).read_text(encoding="utf-8"))["space_id"]
                prefs = {"active_space_id": source_id,
                         "space_registry": {source_id: {"folder": str(source), "name": "Tools"}}}
                def save_prefs(update):
                    prefs.clear()
                    prefs.update(update)
                    return copy.deepcopy(prefs)
                routes = space_routes(source, lambda: copy.deepcopy(prefs), save_prefs, space_root=root)
                before = inv.read_bytes()
                with patch("organizer_spaces.other_spaces", return_value=[]):
                    routes["/api/space/copy"]({"output": str(source), "space_id": source_id})
                copied = next(folder for folder in root.iterdir() if folder != source)
                parsed = parse_inventory((copied / INVENTORY_FILENAME).read_text(encoding="utf-8"))
                self.assertEqual(parsed["layout"]["space"]["grid"], grid)
                self.assertEqual(parsed["layout"]["design_specs"]["B1"]["grid"], grid)
                self.assertEqual(inv.read_bytes(), before)

    def test_hosted_creation_accepts_grid_and_floor_choice(self):
        result = create_space_text_payload(space("gridfinity_half", "portable") | {"built_in_grid": "none"})
        self.assertEqual(result["layout"]["space"]["grid"], "gridfinity_half")
        self.assertEqual(result["layout"]["space"]["built_in_grid"], "none")


if __name__ == "__main__":
    unittest.main()
