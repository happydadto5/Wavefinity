"""Story 2969 (Gridfinity Stage 1): compatible 42 mm and independent 21 mm bases.

Sections are read from the final fused body with plane/mesh intersections, so
nothing here measures an isolated foot and nothing needs scipy.
"""

from dataclasses import replace
from unittest import mock
import unittest

import numpy as np
import trimesh
from shapely.geometry import Point, Polygon

from organizer_app_impl._design_io import default_feature, design_from_dict, design_to_dict
from organizer_app_impl import _preview
from organizer_engine import BoxSpec
from organizer_engine._boxes import make_box
from organizer_features import gridfinity as gf
from organizer_geometry import _extrude_polygon, difference, intersection, translated, union
from organizer_inserts import Layout, make_fused_box
from organizer_inserts._assembly import build_features

PITCHES = ("gridfinity", "gridfinity_half")
# grid -> 1x1 size, 2x3 size (BoxSpec mm), then the exact full-wall extents of each
EXTENTS = {
    "gridfinity": ((42.0, 42.0), (84.0, 126.0), (41.5, 41.5), (83.5, 125.5)),
    "gridfinity_half": ((21.0, 21.0), (42.0, 63.0), (20.5, 20.5), (41.5, 62.5)),
}
# per-cell foot widths at z = 0 / 0.4 / 1.7 / 3.7
FOOT_WIDTHS = {
    "gridfinity": (35.6, 36.4, 37.2, 39.4),
    "gridfinity_half": (14.6, 15.4, 16.2, 18.4),
}
SECTION_ZS = (1e-4, 0.4, 1.7, 3.7)   # z = 0 itself is the bottom face; 0.1 um above it
TOL = 0.05


def build(grid, x, y, z=42.0, **changes):
    box = gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=z, **changes), grid)
    return box, make_box(box, grid=grid)


def section_points(mesh, z):
    return trimesh.intersections.mesh_plane(
        mesh, (0.0, 0.0, 1.0), (0.0, 0.0, z)).reshape(-1, 3)


def crossings(mesh, z, axis, value):
    """Sorted coordinates along the other axis where the section crosses a line."""
    segments = trimesh.intersections.mesh_plane(mesh, (0.0, 0.0, 1.0), (0.0, 0.0, z))
    other = 1 - axis
    found = []
    for a, b in segments:
        lo, hi = sorted((a[axis], b[axis]))
        if lo <= value < hi:
            t = (value - a[axis]) / (b[axis] - a[axis])
            found.append(a[other] + t * (b[other] - a[other]))
    return sorted(found)


def cell_width(mesh, z, centre, pitch):
    points = section_points(mesh, z)
    near = points[(abs(points[:, 0] - centre[0]) < pitch / 2) & (abs(points[:, 1] - centre[1]) < pitch / 2)]
    return float(np.ptp(near[:, 0])), float(np.ptp(near[:, 1]))


def foot_width(grid, z):
    return gf.foot_polygon(grid, z).bounds[2] - gf.foot_polygon(grid, z).bounds[0]


class GridfinityBaseTests(unittest.TestCase):
    def test_profile_data_is_independent_per_pitch(self):
        from organizer_engine._specs import GRID_PITCHES
        self.assertEqual(gf.PROFILES["gridfinity"]["pitch"], GRID_PITCHES["gridfinity"])
        self.assertEqual(gf.PROFILES["gridfinity_half"]["pitch"], GRID_PITCHES["gridfinity_half"])
        self.assertEqual((gf.FOOT_HEIGHT, gf.FLOOR_SKIN, gf.MIN_GRID_BASE), (4.75, 1.0, 5.75))
        self.assertEqual(gf.PROFILES["gridfinity"]["foot_half"], 17.0)
        self.assertEqual(gf.PROFILES["gridfinity_half"]["foot_half"], 6.5)
        self.assertIs(gf.PROFILES["gridfinity"]["radii"], gf.PROFILES["gridfinity_half"]["radii"])
        # 21 mm is not half of 42 mm: same radii on closer centres.
        self.assertNotAlmostEqual(foot_width("gridfinity_half", 0.0) * 2, foot_width("gridfinity", 0.0))

    def test_extents_and_single_watertight_volume(self):
        for grid in PITCHES:
            one, big, one_extent, big_extent = EXTENTS[grid]
            for (x, y), (ex, ey) in ((one, one_extent), (big, big_extent)):
                with self.subTest(grid=grid, size=(x, y)):
                    box, mesh = build(grid, x, y)
                    self.assertEqual(gf.nominal_extent(box, grid), (ex, ey))
                    points = section_points(mesh, 20.0)
                    self.assertAlmostEqual(float(np.ptp(points[:, 0])), ex, delta=1e-6)
                    self.assertAlmostEqual(float(np.ptp(points[:, 1])), ey, delta=1e-6)
                    self.assertTrue(mesh.is_watertight and mesh.is_volume)
                    self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                    self.assertAlmostEqual(float(mesh.bounds[0][2]), 0.0, delta=1e-9)
                    self.assertAlmostEqual(float(mesh.bounds[1][2]), 42.0, delta=1e-9)

    def test_exposed_underside_sections_of_the_final_body(self):
        for grid in PITCHES:
            pitch = gf.PROFILES[grid]["pitch"]
            for size in (EXTENTS[grid][0], EXTENTS[grid][1]):
                box, mesh = build(grid, *size)
                nx, ny = gf.cell_counts(box, grid)
                for centre in gf._cell_centres(box, grid):
                    for z, expected in zip(SECTION_ZS, FOOT_WIDTHS[grid]):
                        with self.subTest(grid=grid, size=size, centre=centre, z=z):
                            width_x, width_y = cell_width(mesh, z, centre, pitch)
                            self.assertAlmostEqual(width_x, expected, delta=TOL)
                            self.assertAlmostEqual(width_y, expected, delta=TOL)

    def test_gutters_open_below_foot_top_and_bridged_above(self):
        for grid in PITCHES:
            pitch = gf.PROFILES[grid]["pitch"]
            box, mesh = build(grid, *EXTENTS[grid][1])
            nx, ny = gf.cell_counts(box, grid)
            (ex, ey) = gf.nominal_extent(box, grid)
            # probe lines through the first row / column of feet, nudged off
            # the vertices that sit exactly on a cell centre
            row_y = gf._cell_centres(box, grid)[0][1] + 0.0137
            col_x = gf._cell_centres(box, grid)[0][0] + 0.0137
            for z in (0.4, 2.0, 4.7):
                with self.subTest(grid=grid, z=z):
                    width = foot_width(grid, z)
                    along_x = crossings(mesh, z, 1, row_y)
                    along_y = crossings(mesh, z, 0, col_x)
                    # two edges per foot: the gutters between feet are empty
                    self.assertEqual(len(along_x), 2 * nx)
                    self.assertEqual(len(along_y), 2 * ny)
                    for a, b in zip(along_x[1:-1:2], along_x[2:-1:2]):
                        self.assertAlmostEqual(b - a, pitch - width, delta=1e-6)
            for z in (4.8, 5.2):
                with self.subTest(grid=grid, bridged_z=z):
                    # from 4.75 the shell is one slab: only the outer wall is crossed
                    self.assertEqual(len(crossings(mesh, z, 1, row_y)), 2)
                    self.assertEqual(len(crossings(mesh, z, 0, col_x)), 2)
            # the shell may not come down over the feet (the rejected z = 0 shell)
            self.assertEqual(len(crossings(mesh, 4.7, 1, row_y)), 2 * nx)

    def test_cap_overlap_is_a_positive_volume_single_union(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                box = gf.normalize_gridfinity_settings(BoxSpec(x=EXTENTS[grid][1][0], y=EXTENTS[grid][1][1], z=42.0), grid)
                feet = gf.foot_solid(box, grid)
                self.assertAlmostEqual(float(feet.bounds[1][2]), gf.FOOT_HEIGHT + gf.FOOT_CAP, delta=1e-9)
                slab = translated(
                    _extrude_polygon(gf.flat_outer_polygon(box, grid), 42.0 - gf.FOOT_HEIGHT),
                    (0.0, 0.0, gf.FOOT_HEIGHT))
                overlap = intersection([slab, feet])
                nx, ny = gf.cell_counts(box, grid)
                area = gf.foot_polygon(grid, gf.FOOT_HEIGHT).area
                self.assertAlmostEqual(overlap.volume, nx * ny * area * gf.FOOT_CAP, delta=0.5)
                fused = union([slab, feet])
                self.assertTrue(fused.is_watertight and fused.is_volume)
                self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_final_body_seats_in_its_socket_with_quarter_mm_clearance(self):
        plate_height = {"gridfinity": 5.0, "gridfinity_half": 4.7}
        for grid in PITCHES:
            pitch = gf.PROFILES[grid]["pitch"]
            seat = gf.PROFILES[grid]["seat_z"]
            for size in (EXTENTS[grid][0], EXTENTS[grid][1]):
                with self.subTest(grid=grid, size=size):
                    box, body = build(grid, *size)
                    nx, ny = gf.cell_counts(box, grid)
                    cutter = gf.socket_cutter(grid, nx, ny)
                    self.assertTrue(cutter.is_watertight and cutter.is_volume)
                    self.assertEqual(len(cutter.split(only_watertight=False)), 1)
                    half_x, half_y = pitch * nx / 2.0 - 4.0, pitch * ny / 2.0 - 4.0
                    slab = _extrude_polygon(
                        Polygon(gf._ring((0.0, 0.0), half_x, half_y, 4.0)), plate_height[grid])
                    plate = difference([slab, cutter])
                    seated = translated(body, (0.0, 0.0, seat))
                    clash = intersection([seated, plate])
                    self.assertLess(clash.volume if len(clash.faces) else 0.0, 1e-6)
                    # straight band, first cell: 0.25 per side
                    z = 2.0
                    centre = gf._cell_centres(box, grid)[0]
                    socket_w = cell_width(cutter, z, centre, pitch)
                    foot_w = cell_width(seated, z, centre, pitch)
                    for socket, foot in zip(socket_w, foot_w):
                        self.assertAlmostEqual((socket - foot) / 2.0, 0.25, delta=0.01)

    def test_fused_divider_builds_clean_at_the_effective_floor(self):
        for grid in PITCHES:
            with self.subTest(grid=grid):
                box, body = build(grid, *EXTENTS[grid][1], z=42.0)
                floor = gf.effective_base(box, grid)
                self.assertEqual(floor, 5.75)
                self.assertEqual(box.base_thickness, floor)
                divider = default_feature(box, "divider")
                fused = make_fused_box(box, [divider], body)
                self.assertTrue(fused.is_watertight and fused.is_volume)
                self.assertEqual(len(fused.split(only_watertight=False)), 1)
                self.assertGreater(fused.volume, body.volume + 1.0)
                # the divider stands on the effective floor and never reaches the feet
                parts = build_features(box, [divider], box.base_thickness)
                self.assertAlmostEqual(min(float(part.bounds[0][2]) for part in parts), floor, delta=1e-9)
                self.assertAlmostEqual(float(fused.bounds[0][2]), 0.0, delta=1e-9)
                self.assertAlmostEqual(float(fused.bounds[1][2]), 42.0, delta=1e-9)
                outer = gf.flat_outer_polygon(box, grid).exterior
                # floor: solid right up to the effective base, open cavity above it
                below = section_points(fused, floor - 0.05)
                self.assertTrue(all(outer.distance(Point(p[:2])) < 1e-3 for p in below))
                above = section_points(fused, floor + 0.5)
                inner = np.asarray([p for p in above if outer.distance(Point(p[:2])) > box.wall / 2.0])
                cavity = gf.flat_cavity_polygon(box, grid).bounds
                self.assertAlmostEqual(float(inner[:, 0].min()), cavity[0], delta=1e-6)
                self.assertAlmostEqual(float(inner[:, 0].max()), cavity[2], delta=1e-6)
                self.assertAlmostEqual(float(inner[:, 1].min()), cavity[1], delta=1e-6)
                self.assertAlmostEqual(float(inner[:, 1].max()), cavity[3], delta=1e-6)
                ext_x, ext_y = gf.nominal_extent(box, grid)
                self.assertAlmostEqual(cavity[2] - cavity[0], ext_x - 2 * box.wall, delta=1e-6)
                self.assertAlmostEqual(cavity[3] - cavity[1], ext_y - 2 * box.wall, delta=1e-6)

    def test_effective_base_normalization(self):
        for grid in PITCHES:
            x, y = EXTENTS[grid][0]
            raw = BoxSpec(x=x, y=y, z=42.0, base_thickness=2.0)
            self.assertEqual(gf.normalize_gridfinity_settings(raw, grid).base_thickness, 5.75)
            self.assertEqual(gf.effective_base(raw, grid), 5.75)
            thick = replace(raw, base_thickness=7.0)
            self.assertEqual(gf.normalize_gridfinity_settings(thick, grid).base_thickness, 7.0)
            saved = design_to_dict(raw, Layout())
            saved["grid"] = grid
            self.assertEqual(saved["box"]["base_thickness"], 2.0)
            self.assertEqual(design_from_dict(saved)[0].base_thickness, 5.75)
            written = design_to_dict(raw, replace(Layout(), design_grid=grid))
            self.assertEqual(written["box"]["base_thickness"], 5.75)
        # a wavefinity design is untouched
        raw = BoxSpec(x=42.0, y=42.0, z=40.0, base_thickness=2.0)
        self.assertIs(gf.normalize_gridfinity_settings(raw, "wavefinity"), raw)
        self.assertEqual(gf.effective_base(raw, "wavefinity"), 2.0)
        saved = design_to_dict(raw, Layout())
        self.assertEqual(saved["box"]["base_thickness"], 2.0)
        self.assertEqual(design_from_dict(saved)[0].base_thickness, 2.0)
        self.assertEqual(gf.gridfinity_base_minimum("wavefinity"), 0.0)
        self.assertEqual(gf.gridfinity_base_minimum("gridfinity"), 5.75)

    def test_preview_builds_the_real_shell_for_grid_designs_only(self):
        with mock.patch.object(_preview, "make_box", wraps=make_box) as spy:
            for grid in PITCHES:
                x, y = EXTENTS[grid][0]
                box = gf.normalize_gridfinity_settings(BoxSpec(x=x, y=y, z=42.0), grid)
                scene = _preview.preview_geometry(box, layout=replace(Layout(), design_grid=grid))
                self.assertEqual(spy.call_args.kwargs.get("grid"), grid)
                self.assertTrue(scene["geometry"])
            spy.reset_mock()
            _preview.preview_geometry(BoxSpec(x=42.0, y=42.0, z=40.0), layout=Layout())
            _preview.preview_geometry(BoxSpec(x=42.0, y=42.0, z=40.0))
            spy.assert_not_called()   # the wavefinity default keeps its thin-ring path

    def test_wavefinity_make_box_is_unchanged(self):
        box = BoxSpec(x=42.0, y=42.0, z=40.0)
        np.testing.assert_allclose(make_box(box).bounds, make_box(box, grid="wavefinity").bounds)
        with self.assertRaises(ValueError):
            make_box(box, grid="nonsense")


if __name__ == "__main__":
    unittest.main()
