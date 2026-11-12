"""Story 2973: grid-aware Plain Drawer layout, server twin and browser model.

Both pitches (42 mm and half 21 mm), 1x1 and 2x3 bins, stacking at the engine's
assembled height, an overheight stack, overlap, the hatched far-edge strip,
cross-grid refusal, the unverified/recorded seated lift, and the Wavefinity
drawer behaving exactly as before.
"""

from __future__ import annotations

import json
import unittest

from organizer_drawer import drawer_report, plan_spacers
from organizer_engine._specs import GRID_PITCHES
from organizer_features.gridfinity import SEAT_DESCENT
from organizer_inventory import normalise_space_definition
from organizer_inventory._space import configure_space_text
from organizer_inventory._rows import checked_design_entry
from wavefinity_web_impl._ai import ai_context_grid, grid_editor_catalog
from tests.test_space_simplification import run_node

GRIDFINITY = ("gridfinity", "gridfinity_half")


def row(index, x, y, z, grid, stack="direct"):
    return {"id": f"B{index}", "name": f"B{index}", "kind": "bin", "stack": stack, "qty": 0,
            "wall": 1.2, "grid": grid, "x": x, "y": y, "z": z}


def layout(grid, width, depth, height, placements, **space):
    return {"space": {"kind": "drawer", "grid": grid, "x": width, "y": depth, "z": height, **space},
            "active": "d1",
            "drawers": [{"id": "d1", "width": width, "depth": depth, "height": height,
                         "boundary": "wall", "placements": placements}]}


def report(lay, bins):
    return drawer_report(lay["drawers"][0], bins, layout=lay)


def messages(result):
    return [problem["message"] for problem in result["problems"]]


class ServerLayoutTests(unittest.TestCase):
    def test_real_dimensions_whole_cell_field_and_both_footprints(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            with self.subTest(grid=grid):
                # 5.5 cells across, 4.25 deep: the partial strip is the leftover.
                width, depth = pitch * 5.5, pitch * 4.25
                bins = [row(0, pitch, pitch, 49.0, grid), row(1, 2 * pitch, 3 * pitch, 49.0, grid)]
                lay = layout(grid, width, depth, 100,
                             [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "gx": 1, "gy": 0}])
                result = report(lay, bins)
                self.assertEqual((result["grid"]["cols"], result["grid"]["rows"], result["grid"]["step"]),
                                 (5, 4, pitch))
                self.assertEqual((result["grid"]["ox"], result["grid"]["oy"]), (0, 0))
                self.assertAlmostEqual(result["grid"]["gap_right"], pitch / 2)
                self.assertAlmostEqual(result["grid"]["gap_back"], pitch / 4)
                self.assertEqual(result["problems"], [])

    def test_strip_and_overlap_are_refused(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            with self.subTest(grid=grid):
                bins = [row(0, pitch, pitch, 49.0, grid), row(1, 2 * pitch, 3 * pitch, 49.0, grid)]
                width, depth = pitch * 3.5, pitch * 4.5
                strip = report(layout(grid, width, depth, 100, [{"bin": "B0", "gx": 3, "gy": 0}]), bins)
                self.assertEqual([p["type"] for p in strip["problems"]], ["outside"])
                overlap = report(layout(grid, width, depth, 100,
                                        [{"bin": "B0", "gx": 1, "gy": 0}, {"bin": "B1", "gx": 1, "gy": 0}]), bins)
                self.assertEqual([p["type"] for p in overlap["problems"]], ["overlap"])

    def test_stack_height_is_assembled_and_overheight_is_refused(self):
        for grid in GRIDFINITY:
            pitch = GRID_PITCHES[grid]
            for cells in ((1, 1), (2, 3)):
                with self.subTest(grid=grid, cells=cells):
                    x, y = cells[0] * pitch, cells[1] * pitch
                    bins = [row(0, x, y, 49.0, grid), row(1, x, y, 49.0, grid)]
                    stack = [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "on": "B0:0"}]
                    assembled = 2 * 49.0 - SEAT_DESCENT[grid]
                    roomy = report(layout(grid, 300, 300, assembled + 0.01, stack), bins)
                    self.assertEqual(roomy["problems"], [])
                    tight = report(layout(grid, 300, 300, assembled - 0.01, stack), bins)
                    self.assertEqual([p["type"] for p in tight["problems"]], ["too_tall"])
                    self.assertIn(f"{assembled:g} mm tall", messages(tight)[0])

    def test_only_a_same_footprint_bin_stacks(self):
        bins = [row(0, 42, 42, 49.0, "gridfinity"), row(1, 84, 42, 49.0, "gridfinity")]
        lay = layout("gridfinity", 300, 300, 200, [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "on": "B0:0"}])
        self.assertTrue(any("same-footprint" in text for text in messages(report(lay, bins))))

    def test_seated_lift_is_added_when_recorded_and_unverified_otherwise(self):
        bins = [row(0, 42, 42, 49.0, "gridfinity"), row(1, 42, 42, 49.0, "gridfinity")]
        stack = [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "on": "B0:0"}]
        assembled = 2 * 49.0 - SEAT_DESCENT["gridfinity"]
        bare = report(layout("gridfinity", 300, 300, assembled + 1, stack), bins)
        self.assertEqual(bare["height_fit"]["verified"], False)
        self.assertIsNone(bare["height_fit"]["seated_lift_mm"])
        lifted = report(layout("gridfinity", 300, 300, assembled + 1, stack, seated_lift_mm=3.0), bins)
        self.assertEqual(lifted["height_fit"]["verified"], True)
        self.assertEqual([p["type"] for p in lifted["problems"]], ["too_tall"])  # 3 mm lift pushes it over

    def test_gridfinity_has_no_connectors_spacers_or_cross_grid_bins(self):
        bins = [row(0, 42, 42, 20.0, "gridfinity", stack="none"), row(1, 42, 42, 20.0, "gridfinity", stack="none")]
        side_by_side = layout("gridfinity", 300, 300, 100, [{"bin": "B0", "gx": 0, "gy": 0}, {"bin": "B1", "gx": 1, "gy": 0}])
        self.assertEqual(report(side_by_side, bins)["connector_total"], 0)
        with self.assertRaisesRegex(ValueError, "no bin-to-bin spacers"):
            plan_spacers({"id": "d1", "width": 300, "depth": 300, "height": 100, "boundary": "wall",
                          "grid": "gridfinity", "placements": []}, bins)
        wrong = [row(0, 42, 42, 20.0, "gridfinity_half", stack="none")]
        text = messages(report(layout("gridfinity", 300, 300, 100, [{"bin": "B0", "gx": 0, "gy": 0}]), wrong))
        self.assertEqual(len(text), 1)
        self.assertIn("Gridfinity half 21 mm", text[0])
        self.assertIn("Gridfinity 42 mm", text[0])

    def test_wavefinity_drawer_is_unchanged(self):
        bins = [row(0, 14, 14, 20.0, "wavefinity", stack="none")]
        lay = layout("wavefinity", 100, 100, 60, [{"bin": "B0", "gx": 0, "gy": 0}])
        result = report(lay, bins)
        self.assertEqual(result["grid"], {"step": 7.0, "cols": 14, "rows": 14, "ox": 0.5, "oy": 0.5,
                                          "gap_left": 0.5, "gap_right": 1.5, "gap_front": 0.5, "gap_back": 1.5})
        self.assertNotIn("height_fit", result)
        self.assertEqual(result["problems"], [])


class ServerRefusalTests(unittest.TestCase):
    def test_grid_is_recorded_at_setup_and_immutable(self):
        for grid in GRID_PITCHES:
            self.assertEqual(normalise_space_definition(
                {"name": "Tools", "kind": "drawer", "x": 210, "y": 210, "z": 70, "grid": grid})["grid"], grid)
        created = configure_space_text("", title="Tools", mode="create", raw_def={
            "name": "Tools", "kind": "drawer", "x": 210, "y": 210, "z": 70, "grid": "gridfinity"})
        self.assertEqual(created["layout"]["space"]["grid"], "gridfinity")
        self.assertEqual(created["layout"]["drawers"][0]["clearance"], 0.0)
        with self.assertRaisesRegex(ValueError, "immutable"):
            configure_space_text(created["inventory_text"], title="Tools", mode="update", raw_def={
                "name": "Tools", "kind": "drawer", "x": 210, "y": 210, "z": 70, "grid": "gridfinity_half"})

    def test_unsupported_grid_and_too_small_gridfinity_drawer_are_refused(self):
        with self.assertRaises(ValueError):
            normalise_space_definition({"name": "T", "kind": "drawer", "x": 210, "y": 210, "z": 70, "grid": "gridfinity43"})
        with self.assertRaisesRegex(ValueError, "at least 42 mm"):
            normalise_space_definition({"name": "T", "kind": "drawer", "x": 41, "y": 210, "z": 70, "grid": "gridfinity"})

    def test_cross_grid_entry_names_both_grids_on_the_server_paths(self):
        design = {"grid": "gridfinity_half"}
        for call in (
            lambda: checked_design_entry(design, {"grid": "gridfinity"}),
            lambda: ai_context_grid({"grid": "gridfinity_half"}, "gridfinity"),
        ):
            with self.assertRaises(ValueError) as caught:
                call()
            self.assertIn("Gridfinity half 21 mm", str(caught.exception))
            self.assertIn("Gridfinity 42 mm", str(caught.exception))


MODEL_BODY = r"""
ctx.state.catalog = { grids: %(grids)s };
const gbin = (id, grid, x, y, z, o = {}) => ({ id, kind: "bin", name: id, x, y, z, qty: 0, status: "in_design",
  stack: "direct", file: "", wall: 1.2, grid, ...o });
const space = (grid, extra = {}) => ({ kind: "drawer", grid, x: 300, y: 300, z: 100, ...extra });
const dwr = (width, depth, height, placements = []) => ({ id: "d1", name: "Drawer", width, depth, height, boundary: "wall", placements });
const load = (grid, bins, placements, width, depth, height, extra = {}) => {
  DL.bins = bins; DL.loaded = true; DL.active = true;
  DL.normaliseLayout({ version: 1, active: "d1", drawers: [dwr(width, depth, height, placements)],
    design_specs: {}, space: space(grid, extra) });
  return DL.drawer();
};
"""


class ModelTests(unittest.TestCase):
    def run_model(self, body):
        grids = json.dumps(grid_editor_catalog())
        return run_node(MODEL_BODY % {"grids": grids} + body)

    def test_cells_snapping_field_strip_overlap_and_cross_grid(self):
        out = self.run_model(r"""
for (const [grid, pitch] of [["gridfinity", 42], ["gridfinity_half", 21]]) {
  const one = gbin("B1", grid, pitch, pitch, 40), big = gbin("B2", grid, 2 * pitch, 3 * pitch, 40);
  const d = load(grid, [one, big], [], pitch * 5.5, pitch * 4.25, 100);
  const g = DL.grid(d);
  out[grid] = {
    cols: g.cols, rows: g.rows, step: g.step, ox: g.ox, oy: g.oy, unit: g.unit,
    cells1: DL.cells(one, d), cells2: DL.cells(big, d),
    fit1: DL.fitsAt(d, [one], 0, 0).ok, fit2: DL.fitsAt(d, [big], 3, 1).ok,
    strip: DL.fitsAt(d, [one], 5, 0), stripBack: DL.fitsAt(d, [one], 0, 4),
    cross: DL.fitsAt(d, [gbin("X", grid === "gridfinity" ? "gridfinity_half" : "gridfinity", pitch, pitch, 40)], 0, 0),
    wave: DL.fitsAt(d, [gbin("W", "wavefinity", 14, 14, 20)], 0, 0),
  };
  d.placements.push({ bin: "B1", copy: 0, gx: 1, gy: 1 });
  out[grid].overlap = DL.fitsAt(d, [big], 0, 0);
  out[grid].placedCells = DL.items(d)[0] && [DL.items(d)[0].gx, DL.items(d)[0].gy];
}
""")
        for grid, pitch in (("gridfinity", 42), ("gridfinity_half", 21)):
            got = out[grid]
            self.assertEqual((got["cols"], got["rows"], got["step"], got["ox"], got["oy"], got["unit"]),
                             (5, 4, pitch, 0, 0, pitch))
            self.assertEqual((got["cells1"], got["cells2"]), ([1, 1], [2, 3]))
            self.assertTrue(got["fit1"])
            self.assertTrue(got["fit2"])
            self.assertFalse(got["strip"]["ok"])
            self.assertIn("unused strip", got["strip"]["reason"])
            self.assertFalse(got["stripBack"]["ok"])
            self.assertFalse(got["cross"]["ok"])
            self.assertIn("Gridfinity", got["cross"]["reason"])
            self.assertFalse(got["wave"]["ok"])
            self.assertIn("Wavefinity 7 mm", got["wave"]["reason"])
            self.assertFalse(got["overlap"]["ok"])
            self.assertIn("overlaps", got["overlap"]["reason"])
            self.assertEqual(got["placedCells"], [1, 1])   # stored in whole cells of the Space's pitch

    def test_stack_height_same_footprint_overheight_and_lift(self):
        grids = {grid["value"]: grid for grid in grid_editor_catalog()}
        out = self.run_model(r"""
const descentOf = grid => ctx.state.catalog.grids.find(row => row.value === grid).stack_seat_descent_mm;
const run = (grid, pitch, cells, height, extra = {}) => {
  const lower = gbin("B1", grid, cells[0] * pitch, cells[1] * pitch, 49);
  const upper = gbin("B2", grid, cells[0] * pitch, cells[1] * pitch, 49);
  const other = gbin("B3", grid, pitch, pitch, 49);
  const d = load(grid, [lower, upper, other], [{ bin: "B1", copy: 0, gx: 0, gy: 0 }], 300, 300, height, extra);
  const item = DL.items(d)[0];
  const target = { item, layer: item.layers[0], cx: 0, cy: 0 };
  return { fit: DL.fitsOn(d, [upper], target), differs: DL.fitsOn(d, [other], target),
    fitState: DL.heightFit(d) };
};
for (const [grid, pitch] of [["gridfinity", 42], ["gridfinity_half", 21]]) {
  for (const cells of [[1, 1], [2, 3]]) {
    const assembled = 98 - descentOf(grid);
    out[`${grid}-${cells.join("x")}`] = {
      roomy: run(grid, pitch, cells, assembled + 0.01), tight: run(grid, pitch, cells, assembled - 0.01),
      lifted: run(grid, pitch, cells, assembled + 0.01, { seated_lift_mm: 3 }),
    };
  }
}
""")
        for grid in GRIDFINITY:
            descent = grids[grid]["stack_seat_descent_mm"]
            self.assertAlmostEqual(descent, SEAT_DESCENT[grid], places=6)   # one source of truth
            for cells in ("1x1", "2x3"):
                got = out[f"{grid}-{cells}"]
                self.assertTrue(got["roomy"]["fit"]["ok"], got["roomy"]["fit"])
                self.assertFalse(got["tight"]["fit"]["ok"])
                self.assertIn("tall", got["tight"]["fit"]["reason"])
                self.assertFalse(got["lifted"]["fit"]["ok"])      # the recorded 3 mm lift is added under the stack
                self.assertEqual(got["roomy"]["fitState"]["verified"], False)
                self.assertEqual(got["lifted"]["fitState"], {
                    "verified": True, "lift": 3, "note": "Heights include the recorded 3 mm seated lift."})
            self.assertFalse(out[f"{grid}-2x3"]["roomy"]["differs"]["ok"])
            self.assertRegex(out[f"{grid}-2x3"]["roomy"]["differs"]["reason"], "same.footprint")

    def test_wavefinity_drawer_layout_is_unchanged(self):
        out = self.run_model(r"""
const one = gbin("B1", "wavefinity", 16, 16, 30, { stack: "none" });
const d = load("wavefinity", [one], [], 200, 200, 60);
const g = DL.grid(d);
out.grid = [g.step, g.cols, g.rows, g.ox, g.oy, g.perUnit, g.unit];
out.fit = DL.fitsAt(d, [one], 0, 0).ok;
out.noFit = DL.heightFit(d);
out.spacers = DL.isGridfinity(d);
""")
        self.assertEqual(out["grid"], [7, 28, 28, 1, 1, 1, 7])   # 200 - 2 mm allowance = 198 / 7
        self.assertTrue(out["fit"])
        self.assertIsNone(out["noFit"])
        self.assertFalse(out["spacers"])


if __name__ == "__main__":
    unittest.main()
