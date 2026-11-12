"""Story 2975: Gridfinity Storage Box Spaces with an integrated or removable grid.

Both pitches x Floor/None, 1x1 and 2x3 fields and bins, immutability refusals,
cross-grid refusals, the measured and unverified lift readouts, and the Wavefinity
(wavy) box's generated output staying exactly as it was.
"""

from __future__ import annotations

import hashlib
import unittest

import numpy as np
import trimesh

from organizer_app_impl._design_io import design_from_dict
from organizer_b4b._geometry._body import make_b4b_body
from organizer_b4b._layout import b4b_layout
from organizer_b4b._outputs import b4b_summary
from organizer_drawer import drawer_report
from organizer_engine._specs import GRID_PITCHES
from organizer_features.gridfinity import (
    EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM, minimum_floor_build, socket_cutter, socket_surface_z,
)
from organizer_geometry import intersection, translated
from organizer_inventory._rows import checked_design_entry
from organizer_inventory._space import (
    configure_space_text, nearest_whole_cell_field, normalise_space_definition,
)
from organizer_outputs.space import storage_box_design
from wavefinity_web_impl._ai import _ai_space_context, ai_context_grid, grid_editor_catalog

GRIDFINITY = ("gridfinity", "gridfinity_half")
MODES = ("floor", "none")
FIELDS = ((1, 1), (2, 3))


def raw_box(grid, mode, nx, ny, z=35.0, lift=None, headroom=1.0):
    pitch = GRID_PITCHES[grid]
    box = {"secure_lid": False, "edge_bevel": "none", "lid_headroom_mm": headroom}
    if mode == "floor":
        box["base_mm"] = minimum_floor_build(grid)
    if lift is not None:
        box["seated_lift_mm"] = lift
    return {"name": "Box", "kind": "portable", "grid": grid, "built_in_grid": mode,
            "x": nx * pitch, "y": ny * pitch, "z": z, "storage_box": box}


def row(index, x, y, z, grid, stack="none"):
    return {"id": f"B{index}", "name": f"B{index}", "kind": "bin", "stack": stack, "qty": 0,
            "wall": 1.2, "grid": grid, "x": x, "y": y, "z": z}


def created_layout(raw):
    return configure_space_text("", title="Box", raw_def=raw)["layout"]


def report(lay, bins):
    return drawer_report(lay["drawers"][0], bins, layout=lay)


def problem_types(result):
    return [problem["type"] for problem in result["problems"]]


class SetupAndRecordTests(unittest.TestCase):
    def test_record_names_grid_floor_and_distinct_nominal_and_physical_areas(self):
        clearance = EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            for mode in MODES:
                for nx, ny in FIELDS:
                    with self.subTest(grid=grid, mode=mode, cells=(nx, ny)):
                        saved = normalise_space_definition(raw_box(grid, mode, nx, ny))
                        self.assertEqual((saved["grid"], saved["built_in_grid"]), (grid, mode))
                        self.assertEqual(saved["storage_box"]["built_in_grid"], mode)
                        self.assertEqual(saved["nominal_grid_mm"], [nx * pitch, ny * pitch])
                        self.assertEqual(saved["floor_grid"], grid if mode == "floor" else None)
                        grown = 0.0 if mode == "floor" else 2 * clearance
                        self.assertEqual(saved["physical_cavity_mm"], [nx * pitch + grown, ny * pitch + grown])
                        self.assertIsNone(saved["seated_lift_mm"])

    def test_legacy_and_wavefinity_boxes_have_no_floor_mode(self):
        legacy = {"name": "Old", "kind": "portable", "x": 84, "y": 70, "z": 40}
        saved = normalise_space_definition(legacy)
        self.assertEqual(saved["grid"], "wavefinity")
        for key in ("built_in_grid", "floor_grid", "floor_mode", "nominal_grid_mm", "physical_cavity_mm"):
            self.assertNotIn(key, saved)
        # A floor choice means nothing on the Wavefinity grid: it is cleared.
        cleared = normalise_space_definition({**legacy, "built_in_grid": "none",
                                              "storage_box": {"seated_lift_mm": 2.0}})
        self.assertEqual(cleared, saved)

    def test_field_is_nearest_whole_cells_and_never_invented(self):
        self.assertEqual(nearest_whole_cell_field("gridfinity", 100, 200), (84.0, 210.0))
        self.assertEqual(nearest_whole_cell_field("gridfinity_half", 31, 32), (21.0, 42.0))
        self.assertEqual(nearest_whole_cell_field("gridfinity", 1, 1), (42.0, 42.0))        # positive cells only
        self.assertEqual(nearest_whole_cell_field("gridfinity", 20, 20, 48.0), (84.0, 84.0))  # the minimum field
        self.assertEqual(nearest_whole_cell_field("gridfinity", 63, 63), (84.0, 84.0))      # halves round up
        for grid in GRIDFINITY:
            with self.assertRaises(ValueError) as caught:
                normalise_space_definition({**raw_box(grid, "floor", 2, 3), "x": 100.0})
            self.assertIn(f"{GRID_PITCHES[grid]:g} mm cells", str(caught.exception))
            self.assertIn("nearest legal field", str(caught.exception))
        # A latched box (the default) needs the minimum field: 1 cell of 42 is too small.
        latched = {"name": "Box", "kind": "portable", "grid": "gridfinity", "x": 42.0, "y": 126.0, "z": 40.0}
        with self.assertRaisesRegex(ValueError, "nearest legal field is 84 x 126 mm"):
            normalise_space_definition(latched)
        self.assertEqual(normalise_space_definition({**latched, "x": 84.0})["nominal_grid_mm"], [84.0, 126.0])

    def test_grid_and_floor_are_immutable_but_ordinary_edits_work(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            for mode in MODES:
                with self.subTest(grid=grid, mode=mode):
                    created = configure_space_text("", title="Box", raw_def=raw_box(grid, mode, 2, 3))
                    text = created["inventory_text"]
                    other_mode = "none" if mode == "floor" else "floor"
                    same = {**raw_box(grid, mode, 3, 4), "name": "Renamed"}
                    edited = configure_space_text(text, title="Box", raw_def=same, mode="update")["layout"]["space"]
                    self.assertEqual((edited["name"], edited["x"], edited["y"]), ("Renamed", 3 * pitch, 4 * pitch))
                    self.assertEqual((edited["grid"], edited["built_in_grid"]), (grid, mode))
                    for change in ({"built_in_grid": other_mode},
                                   {"storage_box": {**raw_box(grid, mode, 2, 3)["storage_box"],
                                                    "built_in_grid": other_mode}}):
                        with self.assertRaisesRegex(ValueError, "floor is immutable"):
                            configure_space_text(text, title="Box", raw_def={**raw_box(grid, mode, 2, 3), **change},
                                                 mode="update")
                    other_grid = next(one for one in (*GRIDFINITY, "wavefinity") if one != grid)
                    with self.assertRaisesRegex(ValueError, "immutable"):
                        configure_space_text(text, title="Box", raw_def={**raw_box(grid, mode, 2, 3),
                                                                         "grid": other_grid}, mode="update")
                    # An update that does not restate the choices keeps them.
                    bare = {key: value for key, value in same.items() if key not in ("grid", "built_in_grid")}
                    kept = configure_space_text(text, title="Box", raw_def=bare, mode="update")["layout"]["space"]
                    self.assertEqual((kept["grid"], kept["built_in_grid"]), (grid, mode))
                    self.assertEqual(created["inventory_text"], text)


class GenerationTests(unittest.TestCase):
    def assert_single_solid(self, mesh):
        self.assertTrue(mesh.is_watertight)
        self.assertTrue(mesh.is_volume)
        self.assertEqual(len(mesh.split(only_watertight=False)), 1)

    def assert_no_hit(self, a, b):
        hit = intersection([a, b])
        if len(hit.faces):
            volume = abs(np.einsum("ij,ij->i", hit.triangles[:, 0],
                         np.cross(hit.triangles[:, 1], hit.triangles[:, 2])).sum() / 6)
            self.assertLess(volume, 1e-6)

    def built(self, grid, mode, nx, ny):
        saved = normalise_space_definition(raw_box(grid, mode, nx, ny))
        box = design_from_dict(storage_box_design(saved))[0]
        return saved, box, make_b4b_body(box)

    def test_floor_prints_the_socket_grid_and_none_a_clearanced_plain_cavity(self):
        clearance = EXTERNAL_PLATE_CLEARANCE_PER_SIDE_MM
        for grid in GRIDFINITY:
            for mode in MODES:
                for nx, ny in FIELDS:
                    with self.subTest(grid=grid, mode=mode, cells=(nx, ny)):
                        saved, box, body = self.built(grid, mode, nx, ny)
                        self.assert_single_solid(body)
                        self.assertEqual((box.b4b.grid, box.b4b.built_in_grid), (grid, mode))
                        floor = box.base_thickness
                        if mode == "floor":
                            void = translated(socket_cutter(grid, nx, ny), (0, 0, floor - socket_surface_z(grid)))
                            self.assert_no_hit(body, void)
                            inner = b4b_layout(box).inner_mating_polygon.bounds
                            np.testing.assert_allclose(inner, [-box.x / 2, -box.y / 2, box.x / 2, box.y / 2])
                        else:
                            inner = b4b_layout(box).inner_mating_polygon.bounds
                            np.testing.assert_allclose(inner, [-box.x / 2 - clearance, -box.y / 2 - clearance,
                                                               box.x / 2 + clearance, box.y / 2 + clearance])
                            plate = trimesh.creation.box(extents=(box.x, box.y, 5))
                            plate.apply_translation((0, 0, floor + 2.5))
                            self.assert_no_hit(body, plate)
                            slab = trimesh.creation.box(extents=(box.x, box.y, 0.2))
                            slab.apply_translation((0, 0, floor - 0.1))
                            self.assertAlmostEqual(intersection([body, slab]).volume, slab.volume, places=5)
                        # The readout tells the nominal grid from the printed cavity.
                        text = b4b_summary(box)["capacity_text"]
                        self.assertIn("Nominal grid", text)
                        self.assertIn("physical cavity", text)

    def test_wavefinity_box_output_is_unchanged(self):
        """The spec section 8 fingerprint of a wavy box, pinned from the tree before this story."""
        space = {"name": "Wavy", "kind": "portable", "x": 84, "y": 70, "z": 40,
                 "storage_box": {"secure_lid": False, "edge_bevel": "none"}}
        box = design_from_dict(storage_box_design(normalise_space_definition(space)))[0]
        self.assertEqual(box.b4b.grid, "wavefinity")
        mesh = make_b4b_body(box)
        vertices = np.round(mesh.vertices, 3)
        ordered = np.ascontiguousarray(vertices[np.lexsort(vertices.T[::-1])])
        self.assertEqual((len(mesh.vertices), len(mesh.faces)), (21116, 42228))
        self.assertAlmostEqual(float(mesh.volume), 42454.753, delta=0.01)
        self.assertAlmostEqual(float(mesh.area), 43282.648, delta=0.01)
        np.testing.assert_allclose(mesh.bounds, [[-44.9704, -37.9704, 0.0], [44.9704, 37.9704, 42.6]], atol=1e-3)
        self.assertEqual(hashlib.sha256(ordered.tobytes()).hexdigest(),
                         "82f3af1c3d35a6a82bd120717d4d1e69fbec1bc5f09b84efc823e7ba039d1148")


class LayoutTests(unittest.TestCase):
    def test_bins_lay_out_on_the_box_pitch_inside_its_interior(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            for mode in MODES:
                with self.subTest(grid=grid, mode=mode):
                    lay = created_layout(raw_box(grid, mode, 3, 4))
                    drawer = lay["drawers"][0]
                    self.assertEqual((drawer["boundary"], drawer["grid"], drawer["clearance"]), ("mating", grid, 0.0))
                    bins = [row(0, pitch, pitch, 30.0, grid), row(1, 2 * pitch, 3 * pitch, 30.0, grid)]
                    drawer["placements"] = [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "gx": 1, "gy": 0}]
                    result = report(lay, bins)
                    self.assertEqual((result["grid"]["step"], result["grid"]["cols"], result["grid"]["rows"]),
                                     (pitch, 3, 4))
                    self.assertEqual(result["problems"], [])
                    drawer["placements"] = [{"bin": "B0", "gx": 0.5, "gy": 0}]
                    self.assertEqual(problem_types(report(lay, bins)), ["outside"])
                    drawer["placements"] = [{"bin": "B0", "gx": 3, "gy": 0}]
                    self.assertEqual(problem_types(report(lay, bins)), ["outside"])
                    drawer["placements"] = [{"bin": "B1", "gx": 2, "gy": 0}]
                    self.assertEqual(problem_types(report(lay, bins)), ["outside"])

    def test_cross_grid_entry_is_refused_naming_both_grids_on_every_path(self):
        grid, other = "gridfinity", "gridfinity_half"
        lay = created_layout(raw_box(grid, "floor", 3, 4))
        lay["drawers"][0]["placements"] = [{"bin": "B0", "gx": 0, "gy": 0}]
        wrong = report(lay, [row(0, 21, 21, 20.0, other)])
        self.assertEqual(problem_types(wrong), ["grid"])
        paths = (
            lambda: checked_design_entry({"grid": other}, {"grid": grid}),
            lambda: ai_context_grid({"grid": other}, grid),
        )
        for call in paths:
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertIn("Gridfinity half 21 mm", str(caught.exception))
            self.assertIn("Gridfinity 42 mm", str(caught.exception))
        for text in (wrong["problems"][0]["message"],):
            self.assertIn("Gridfinity half 21 mm", text)
            self.assertIn("Gridfinity 42 mm", text)
        # A Wavefinity design is refused by a Gridfinity box as well.
        wavy = report(lay, [row(0, 42, 42, 20.0, "wavefinity")])
        self.assertEqual(problem_types(wavy), ["grid"])

    def test_headroom_is_interior_plus_lid_headroom(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            for headroom in (1.0, 2.0):
                with self.subTest(grid=grid, headroom=headroom):
                    lay = created_layout(raw_box(grid, "floor", 3, 3, z=35.0, headroom=headroom))
                    lay["drawers"][0]["placements"] = [{"bin": "B0", "gx": 0, "gy": 0}]
                    fits = report(lay, [row(0, pitch, pitch, 35.0 + headroom, grid)])
                    self.assertEqual(fits["problems"], [])
                    self.assertEqual(fits["headroom"]["cap_mm"], 35.0 + headroom)
                    tall = report(lay, [row(0, pitch, pitch, 35.5 + headroom, grid)])
                    self.assertEqual(problem_types(tall), ["too_tall"])
                    self.assertIn(f"takes {35.0 + headroom:g} mm", tall["problems"][0]["message"])

    def test_measured_and_unverified_lift_readouts_never_fabricate_a_verified_fit(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            bins = [row(0, pitch, pitch, 34.0, grid)]
            placed = [{"bin": "B0", "gx": 0, "gy": 0}]
            with self.subTest(grid=grid, lift="unrecorded"):
                lay = created_layout(raw_box(grid, "none", 3, 3))
                lay["drawers"][0]["placements"] = placed
                result = report(lay, bins)
                self.assertEqual(result["headroom"]["seated_lift_status"], "unverified")
                self.assertIs(result["headroom"]["verified"], False)
                self.assertIs(result["height_fit"]["verified"], False)
                self.assertIsNone(result["height_fit"]["seated_lift_mm"])
                self.assertEqual(result["headroom"]["tallest_mm"], 34.0)
                self.assertEqual(result["headroom"]["remaining_mm"], 2.0)
                self.assertEqual(result["problems"], [])
            with self.subTest(grid=grid, lift="measured"):
                lay = created_layout(raw_box(grid, "none", 3, 3, lift=3.0))
                lay["drawers"][0]["placements"] = placed
                result = report(lay, bins)
                self.assertEqual(result["headroom"]["seated_lift_status"], "measured")
                self.assertIs(result["headroom"]["verified"], True)
                self.assertIs(result["height_fit"]["verified"], True)
                self.assertEqual(result["headroom"]["tallest_mm"], 37.0)   # 3 mm lift + 34 mm bin
                self.assertEqual(result["headroom"]["remaining_mm"], -1.0)
                self.assertEqual(problem_types(result), ["too_tall"])      # the recorded lift changes the readout
            with self.subTest(grid=grid, lift="floor"):
                lay = created_layout(raw_box(grid, "floor", 3, 3))
                lay["drawers"][0]["placements"] = placed
                result = report(lay, bins)
                self.assertEqual(result["headroom"]["floor"], "built_in")
                self.assertEqual(result["headroom"]["seated_lift_status"], "not_applicable")
                self.assertIs(result["headroom"]["verified"], False)
                self.assertIs(result["height_fit"]["verified"], False)
                self.assertEqual(result["headroom"]["tallest_mm"], 34.0)

    def test_wavefinity_box_layout_is_unchanged(self):
        lay = created_layout({"name": "Old", "kind": "portable", "x": 84, "y": 70, "z": 40})
        drawer = lay["drawers"][0]
        self.assertNotIn("grid", drawer)
        drawer["placements"] = [{"bin": "B0", "gx": 0, "gy": 0}]
        result = report(lay, [row(0, 14, 14, 40.0, "wavefinity")])
        self.assertEqual(result["grid"]["step"], 7.0)
        self.assertNotIn("headroom", result)
        self.assertNotIn("height_fit", result)
        self.assertEqual(result["problems"], [])
        tall = report(lay, [row(0, 14, 14, 40.5, "wavefinity")])
        self.assertEqual(problem_types(tall), ["too_tall"])   # cap is the interior height alone


class AiDescriptionTests(unittest.TestCase):
    def test_catalog_describes_the_floor_choices_it_supports(self):
        catalog = {row["value"]: row for row in grid_editor_catalog()}
        self.assertIsNone(catalog["wavefinity"]["container_floor_choices"])
        for grid in GRIDFINITY:
            self.assertEqual([one["value"] for one in catalog[grid]["container_floor_choices"]], ["floor", "none"])
            self.assertEqual(catalog[grid]["container_floor_build_mm"], minimum_floor_build(grid))

    def test_space_context_carries_the_floor_and_only_a_measured_lift(self):
        base = {"kind": "portable", "grid": "gridfinity", "x": 84, "y": 126, "z": 35}
        built_in = _ai_space_context({**base, "built_in_grid": "floor"})
        self.assertEqual(built_in["floor"], "built_in")
        self.assertNotIn("seated_lift_mm", built_in)
        unmeasured = _ai_space_context({**base, "built_in_grid": "none", "storage_box": {"seated_lift_mm": None}})
        self.assertEqual(unmeasured["floor"], "external_plate")
        self.assertNotIn("seated_lift_mm", unmeasured)
        measured = _ai_space_context({**base, "built_in_grid": "none", "storage_box": {"seated_lift_mm": 2.5}})
        self.assertEqual(measured["seated_lift_mm"], 2.5)
        wavy = _ai_space_context({"kind": "portable", "x": 84, "y": 70, "z": 40})
        self.assertNotIn("floor", wavy)


if __name__ == "__main__":
    unittest.main()
