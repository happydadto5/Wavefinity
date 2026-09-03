"""External-behavior regression tests for the organizer generator."""

from __future__ import annotations

import contextlib
import io
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import numpy as np
import trimesh
from shapely.geometry import Point

import organizer_app
from organizer_engine import (
    BoxSpec,
    CORNER_INSET,
    ConnectorSpec,
    GRID_PITCH,
    LOCK_CORNER_CLEAR,
    MIN_BOX_SIZE,
    lock_lattice,
    LOCK_PROTRUSION,
    LOCK_RUN,
    lock_z_levels,
    BASE_UNIT,
    LOCKED_TOLERANCE,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    MIN_JOINABLE_SIZE,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    connector_half_widths,
    generate_sampler,
    make_sampler_scene,
    flat_cavity_polygon,
    _extrude_polygon,
    difference,
    preview_rings,
    make_floor_label,
    make_labelled_box,
    placed_label_outline,
    label_layout,
    label_report,
    text_outline,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_CAP_HEIGHT_MIN,
    TEXT_MARGIN,
    TEXT_DEPTH,
    installed_boxes,
    intersection_volume,
    lock_positions,
    make_box,
    make_side_connector,
    make_wall_lock_bumps,
    measure_lock,
    mesh_fingerprint,
    mesh_report,
    seat_transform,
    translated,
    validate_3mf,
    validate_side_fit,
    wave_cycles,
    wave_value,
    wavy_cavity_polygon,
    wavy_outer_polygon,
    _wall_points,
)


REFERENCE_FINGERPRINTS = {
    "box": "80F09E19A9422D66ED44BD051702CF70089D487FCA2CE575C7F5D25E3CF2E707",
    "connector": "B192E6A9FA4D486A9E491F84778497738264CBC063B62D34E179D46C02E6BC13",
}


class WaveTests(unittest.TestCase):
    def test_full_cycle_is_four_mm_out_and_back(self) -> None:
        self.assertEqual(WAVE_LENGTH, 4.0)
        self.assertEqual(WAVE_AMPLITUDE, 0.4)
        # leaves the wall centre at zero, out at a quarter, back at a half
        self.assertAlmostEqual(wave_value(0.0), 0.0, places=9)
        self.assertAlmostEqual(wave_value(1.0), 0.4, places=9)
        self.assertAlmostEqual(wave_value(3.0), -0.4, places=9)
        for s in (-6.0, -1.7, 0.0, 2.3, 6.1):
            self.assertAlmostEqual(wave_value(s), wave_value(s + WAVE_LENGTH), places=9)

    def test_wave_is_odd_about_the_wall_centre(self) -> None:
        # what lets a box be turned round: spun 180 degrees the +X wall lands
        # where -X was, and an odd wave means the two carry the same shape
        for s in (0.4, 1.3, 2.5, 4.9, 8.1, 12.7):
            self.assertAlmostEqual(wave_value(-s), -wave_value(s), places=12)

    def test_wave_keeps_full_amplitude_into_the_corner(self) -> None:
        half = BoxSpec().half_x
        extrema = [
            s for s in np.arange(WAVE_LENGTH / 4.0, half, WAVE_LENGTH / 2.0)
            if abs(abs(wave_value(float(s))) - WAVE_AMPLITUDE) < 1e-9
        ]
        self.assertTrue(extrema)
        self.assertGreater(max(extrema), half - WAVE_LENGTH)

    def test_fixed_pitch_adds_cycles_without_stretching(self) -> None:
        counts = []
        for width in (24.0, 32.0, 48.0):
            spec = BoxSpec(x=width, y=24.0, z=40.0)
            half = spec.half_x
            crests = []
            index = 0
            while True:
                position = (
                    -math.floor(half / WAVE_LENGTH) * WAVE_LENGTH
                    + WAVE_LENGTH / 4.0
                    + index * WAVE_LENGTH
                )
                if position > half:
                    break
                crests.append(position)
                self.assertAlmostEqual(wave_value(position), WAVE_AMPLITUDE, places=9)
                index += 1
            for first, second in zip(crests, crests[1:]):
                self.assertAlmostEqual(second - first, WAVE_LENGTH, places=9)
            counts.append(len(crests))
            self.assertAlmostEqual(wave_cycles(2.0 * half), 2.0 * half / WAVE_LENGTH)
        self.assertEqual(counts, sorted(counts))
        self.assertGreater(counts[2], counts[0])


class BoxTests(unittest.TestCase):
    def test_outline_keeps_the_wave_and_rounds_only_the_corners(self) -> None:
        spec = BoxSpec()
        outline = wavy_outer_polygon(spec)
        self.assertTrue(outline.is_valid)
        ring = outline.exterior
        raw = _wall_points(
            spec.half_x, spec.half_y,
            spec.half_x - CORNER_INSET, spec.half_y - CORNER_INSET,
        )
        corners = [
            (sx * spec.half_x, sy * spec.half_y)
            for sx in (-1, 1) for sy in (-1, 1)
        ]
        away = [
            ring.distance(Point(p)) for p in raw
            if min(math.dist(p, c) for c in corners) > 3.0
        ]
        self.assertTrue(away)
        self.assertLess(max(away), 0.005)         # wave untouched
        self.assertLess(max(ring.distance(Point(p)) for p in raw), 0.25)  # corners eased

    def test_cavity_runs_parallel_to_the_outer_wall(self) -> None:
        spec = BoxSpec()
        outer = wavy_outer_polygon(spec)
        cavity = wavy_cavity_polygon(spec)
        self.assertTrue(cavity.within(outer))
        # perpendicular wall never thinner than the requested value
        ring = outer.exterior
        for y in np.linspace(-5.0, 5.0, 41):
            probe = Point(spec.half_x - spec.wall_depth + wave_value(float(y)), y)
            self.assertGreaterEqual(ring.distance(probe), spec.wall - 1e-6)

    def test_boxes_tile_on_the_grid_without_touching(self) -> None:
        spec = BoxSpec()
        left, right = installed_boxes(spec, "y")
        self.assertEqual(intersection_volume(left, right), 0.0)
        # and the pitch really is the nominal size
        self.assertAlmostEqual(
            right.bounds[0][0] - left.bounds[0][0], spec.x, places=6
        )

    def test_scaled_boxes_remain_watertight_and_exact_height(self) -> None:
        for dimensions in ((24.0, 24.0, 40.0), (32.0, 24.0, 45.0), (24.0, 48.0, 30.0)):
            spec = BoxSpec(*dimensions)
            mesh = make_box(spec)
            report = mesh_report(f"box_{dimensions}", mesh)
            self.assertEqual(report["components"], 1)
            self.assertAlmostEqual(mesh.extents[2], dimensions[2], places=5)

    def test_sizes_must_sit_on_the_grid(self) -> None:
        for good in (8.0, 16.0, 24.0, 96.0):
            BoxSpec(x=good, y=24.0)          # must not raise
            self.assertEqual(BoxSpec(x=good, y=24.0).grid_steps[0], round(good / 8))
        for bad in (20.0, 25.0, 22.0, 24.5):
            with self.assertRaisesRegex(ValueError, "whole multiple"):
                BoxSpec(x=bad, y=24.0)
        for small in (4.0, 6.0, 2.0):
            with self.assertRaisesRegex(ValueError, "at least"):
                BoxSpec(x=small, y=24.0)
        self.assertEqual(GRID_PITCH, 8.0)
        self.assertEqual(MIN_BOX_SIZE, 8.0)
        self.assertEqual(BASE_UNIT, 8.0)
        self.assertEqual(MIN_JOINABLE_SIZE, 16.0)

    def test_a_one_unit_side_is_legal_and_joins_on_its_long_sides(self) -> None:
        from organizer_engine import joinable_sides, connector_fits

        narrow = BoxSpec(x=BASE_UNIT, y=6.0 * BASE_UNIT, z=40.0)   # 1 x 6 units
        mesh = make_box(narrow)
        report = mesh_report("narrow", mesh)
        self.assertEqual(report["components"], 1)
        # the short walls take neither a bump nor a connector; the long ones do
        self.assertEqual(
            lock_positions(narrow.half_x - CORNER_INSET - LOCK_CORNER_CLEAR), []
        )
        self.assertTrue(
            lock_positions(narrow.half_y - CORNER_INSET - LOCK_CORNER_CLEAR)
        )
        self.assertEqual(joinable_sides(narrow), (False, True))
        connector = ConnectorSpec()
        clip = make_side_connector(narrow, connector, "y")
        self.assertLess(validate_side_fit(narrow, connector, clip, "y"), 1e-3)
        with self.assertRaisesRegex(ValueError, "does not fit between"):
            make_side_connector(narrow, connector, "x")
        self.assertFalse(connector_fits(narrow, "x"))

    def test_off_grid_sizes_would_actually_have_collided(self) -> None:
        # Why the grid rule exists: shift a box by half a wave along a shared
        # wall - what an off-grid size does - and the walls foul badly.
        spec = BoxSpec()
        mesh = make_box(spec)
        pitch = spec.x
        left = translated(mesh, (-pitch / 2.0, 0.0, 0.0))
        aligned = translated(mesh, (pitch / 2.0, 0.0, 0.0))
        shifted = translated(mesh, (pitch / 2.0, WAVE_LENGTH / 2.0, 0.0))
        self.assertEqual(intersection_volume(left, aligned), 0.0)
        self.assertGreater(intersection_volume(left, shifted), 10.0)

    def test_invalid_parameters_fail_before_export(self) -> None:
        with self.assertRaises(ValueError):
            BoxSpec(x=5.0)
        with self.assertRaises(ValueError):
            ConnectorSpec(tolerance=-0.01)
        with self.assertRaises(ValueError):
            ConnectorSpec(height=1.0, cap_thickness=1.2)
        with self.assertRaises(ValueError):
            ConnectorSpec(arm_thickness=0.4)
        with self.assertRaises(ValueError):
            make_side_connector(BoxSpec(), ConnectorSpec(), position=16.0)


class LockTests(unittest.TestCase):
    def test_two_chamfered_bumps_per_wall(self) -> None:
        spec = BoxSpec()
        bumps = make_wall_lock_bumps(spec)
        self.assertEqual(len(bumps) % 4, 0)          # the same count on all four walls
        self.assertGreaterEqual(len(bumps), 8)
        for bump in bumps:
            self.assertTrue(bump.is_watertight)
            self.assertTrue(bump.is_winding_consistent)
            self.assertGreater(bump.volume, 0.0)

    def test_bump_stands_exactly_the_stated_amount_proud(self) -> None:
        spec = BoxSpec()
        mesh = make_box(spec)
        centre = lock_positions(spec.half_x - CORNER_INSET - LOCK_CORNER_CLEAR)[0]
        face_x = spec.half_x - spec.wall_depth + wave_value(centre)
        low, _, _, high = lock_z_levels(spec.z)

        def probe(inset: float) -> float:
            block = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
            block.apply_translation((face_x - inset, centre, (low + high) / 2.0))
            return intersection_volume(mesh, block)

        self.assertGreater(probe(LOCK_PROTRUSION / 2.0), 0.0)   # bump material
        self.assertEqual(probe(LOCK_PROTRUSION + 0.15), 0.0)    # open air past it

    def test_finished_box_has_no_overhang_at_the_bumps(self) -> None:
        # Boxes print open side up. In the bump band every downward-facing face
        # must sit at 45 degrees or shallower, so nothing inside needs support.
        spec = BoxSpec()
        mesh = make_box(spec)
        low, _, _, high = lock_z_levels(spec.z)
        centroids = mesh.triangles.mean(axis=1)
        band = (centroids[:, 2] > low - 0.01) & (centroids[:, 2] < high + 0.01)
        normals = mesh.face_normals[band]
        downward = normals[normals[:, 2] < -1e-6]
        self.assertTrue(len(downward))
        # the sweep's ruled faces tilt a hair where the wave curves, so allow a
        # fraction of a degree past 45
        worst = max(abs(n[2]) - math.hypot(n[0], n[1]) for n in downward)
        self.assertLessEqual(worst, 0.01)

    def test_bumps_sit_on_every_wave_extremum_clear_of_the_corners(self) -> None:
        for spec in (BoxSpec(), BoxSpec(x=48, y=24, z=40)):
            reach = spec.half_x - CORNER_INSET - LOCK_CORNER_CLEAR
            positions = lock_positions(reach)
            self.assertTrue(positions)
            for centre in positions:
                # crest or trough, but always an extremum
                self.assertAlmostEqual(
                    abs(wave_value(centre)), WAVE_AMPLITUDE, places=6
                )
                self.assertLess(
                    abs(centre) + LOCK_RUN / 2.0, spec.half_x - CORNER_INSET
                )
            # every half cycle, which is what makes the connector reversible
            for first, second in zip(positions, positions[1:]):
                self.assertAlmostEqual(second - first, WAVE_LENGTH / 2.0, places=6)

    def test_every_box_puts_its_bumps_on_one_shared_lattice(self) -> None:
        # A box packed on the grid has its centre on a multiple of WAVE_LENGTH,
        # so its bumps always land at 2.5 mm modulo 5 in drawer coordinates -
        # the same lattice for every box, whatever it measures.
        for size, centre in ((24.0, -12.0), (24.0, 12.0), (48.0, 0.0), (72.0, 36.0)):
            spec = BoxSpec(x=24.0, y=size, z=40.0)
            reach = spec.half_y - CORNER_INSET - LOCK_CORNER_CLEAR
            for local in lock_positions(reach):
                self.assertAlmostEqual(
                    (centre + local) % (WAVE_LENGTH / 2.0), WAVE_LENGTH / 4.0, places=6
                )

    def test_connector_seats_free_then_locks_when_lifted(self) -> None:
        box = BoxSpec()
        for tolerance in (0.02, 0.06, 0.10):
            connector = ConnectorSpec(tolerance=tolerance)
            report = measure_lock(box, connector)
            self.assertLess(report["lift_0.0_mm3"], 1e-3)     # seated: free
            self.assertGreater(report["lift_0.5_mm3"], 0.05)  # lifting: locked
            self.assertGreater(report["lift_1.5_mm3"], report["lift_0.5_mm3"])
            # the bumps really do stand in a plain arm's path
            self.assertGreater(report["no_notch_mm3"], 0.1)

    def test_notches_line_up_with_the_bumps_on_both_axes(self) -> None:
        box = BoxSpec()
        connector = ConnectorSpec(tolerance=0.06)
        for axis in ("x", "y"):
            clip = make_side_connector(box, connector, axis)
            self.assertLess(validate_side_fit(box, connector, clip, axis), 1e-3)


class ConnectorTests(unittest.TestCase):
    def test_arms_are_two_perimeters_thick(self) -> None:
        box, connector = BoxSpec(), ConnectorSpec()
        inner, outer = connector_half_widths(box, connector)
        self.assertAlmostEqual(outer - inner, connector.arm_thickness, places=9)
        self.assertAlmostEqual(connector.arm_thickness, 1.0, places=9)
        self.assertAlmostEqual(
            inner, box.wall_depth + WAVE_MATING_GAP / 2.0 + connector.tolerance
        )

    def test_scaled_connectors_fit(self) -> None:
        for dimensions in ((32.0, 24.0, 45.0), (40.0, 32.0, 60.0), (24.0, 48.0, 40.0)):
            box = BoxSpec(*dimensions)
            connector = ConnectorSpec(tolerance=0.06, height=12.0)
            clip = make_side_connector(box, connector, "y")
            mesh_report("scaled side", clip)
            self.assertLess(validate_side_fit(box, connector, clip, "y"), 1e-3)

    def test_connector_height_is_adjustable(self) -> None:
        box = BoxSpec()
        for height in (7.2, 9.6, 14.0):
            connector = ConnectorSpec(tolerance=0.06, height=height)
            clip = make_side_connector(box, connector)
            self.assertAlmostEqual(clip.extents[2], height, places=5)

    def test_orientation_and_position_are_explicit(self) -> None:
        box = BoxSpec(x=32.0, y=48.0, z=40.0)
        connector = ConnectorSpec()
        x_clip = make_side_connector(box, connector, "x", position=4.0)
        y_clip = make_side_connector(box, connector, "y", position=-4.0)
        self.assertAlmostEqual(x_clip.extents[0], 12.0, places=5)
        self.assertAlmostEqual(y_clip.extents[1], 12.0, places=5)
        self.assertLess(validate_side_fit(box, connector, x_clip, "x", 4.0), 1e-3)
        self.assertLess(validate_side_fit(box, connector, y_clip, "y", -4.0), 1e-3)

    def test_mixed_sizes_share_a_seam_and_the_clip_locks_both_sides(self) -> None:
        # The whole point: a 20x40 beside two 20x20s. They must nest, and a
        # connector on that seam must engage the big box AND the small one.
        big, small = BoxSpec(24.0, 48.0, 40.0), BoxSpec(24.0, 24.0, 40.0)
        connector = ConnectorSpec(tolerance=0.06)
        left = translated(make_box(big), (-12.0, 0.0, 0.0))
        lower = translated(make_box(small), (12.0, -12.0, 0.0))
        upper = translated(make_box(small), (12.0, 12.0, 0.0))
        for a, b in ((left, lower), (left, upper), (lower, upper)):
            self.assertEqual(intersection_volume(a, b), 0.0)

        seat_z = big.z - connector.arm_depth
        for position in (-12.0, 12.0):
            clip = make_side_connector(big, connector, "y", position)
            seated = translated(clip, (0.0, position, seat_z))
            lifted = translated(clip, (0.0, position, seat_z + 0.5))
            boxes = (left, lower, upper)
            self.assertLess(sum(intersection_volume(seated, m) for m in boxes), 1e-3)
            self.assertGreater(sum(intersection_volume(lifted, m) for m in boxes), 0.1)

    def test_one_connector_part_fits_every_box_and_lattice_position(self) -> None:
        connector = ConnectorSpec(tolerance=0.06)
        reference = make_side_connector(BoxSpec(), connector, "y", 0.0)
        for spec, position in (
            (BoxSpec(24.0, 48.0, 40.0), -12.0),
            (BoxSpec(48.0, 48.0, 30.0), 16.0),
            (BoxSpec(24.0, 72.0, 40.0), 20.0),
        ):
            other = make_side_connector(spec, connector, "y", position)
            self.assertAlmostEqual(other.volume, reference.volume, places=4)
            shared = intersection_volume(reference, other)
            self.assertAlmostEqual(shared / reference.volume, 1.0, places=5)

    def test_off_lattice_connector_position_is_rejected(self) -> None:
        spec = BoxSpec(24.0, 48.0, 40.0)
        make_side_connector(spec, ConnectorSpec(), "y", 2.0)   # half a wave: fine
        for bad in (1.0, 3.0, 2.5):
            with self.assertRaisesRegex(ValueError, "whole multiple"):
                make_side_connector(spec, ConnectorSpec(), "y", bad)

    def test_there_is_no_corner_connector(self) -> None:
        import organizer_engine

        for gone in (
            "make_corner_connector",
            "corner_connector_footprints",
            "validate_corner_fit",
        ):
            self.assertFalse(hasattr(organizer_engine, gone), gone)


class SamplerTests(unittest.TestCase):
    def test_sample_set_is_the_requested_boxes_plus_a_row_of_clips(self) -> None:
        sizes = ((16.0, 48.0), (32.0, 48.0), (48.0, 48.0))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sample.3mf"
            report = generate_sampler(output, sizes=sizes, clips=5)
            self.assertEqual(report["objects"], len(sizes) + 5)
            self.assertEqual(report["warnings"], 0)
            self.assertEqual(report["tolerance_mm"], LOCKED_TOLERANCE)
            self.assertEqual(report["connector_length_mm"], LOCKED_CONNECTOR_LENGTH)
            self.assertEqual(report["connector_height_mm"], LOCKED_CONNECTOR_HEIGHT)
            self.assertEqual(
                report["names"],
                sorted(
                    [f"connector_{i}" for i in range(1, 6)]
                    + ["box_2x6_16x48", "box_4x6_32x48", "box_6x6_48x48"]
                ),
            )

    def test_every_connector_on_the_plate_is_the_same_part(self) -> None:
        scene = make_sampler_scene(clips=5)
        prints = set()
        for name, geometry in scene.geometry.items():
            if not name.startswith("connector"):
                continue
            centred = translated(geometry, -geometry.bounds.mean(axis=0))
            prints.add(round(float(centred.volume), 4))
        self.assertEqual(len(prints), 1)

    def test_cli_generates_sample_set_from_unit_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli_sample.3mf"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    organizer_app.main(
                        ["sampler", "--boxes", "2x6,4x6,6x6", "--output", str(output)]
                    ),
                    0,
                )
            self.assertEqual(validate_3mf(output, 8)["warnings"], 0)

    def test_one_unit_is_the_same_number_everywhere(self) -> None:
        # the bug this guards: the sampler and the UI once disagreed on what a
        # unit was, so the same "3x3" gave two different boxes.

        self.assertEqual(BoxSpec(48.0, 48.0, 40.0).units, (6, 6))
        self.assertEqual(organizer_app.parse_sizes("6x6"), ((48.0, 48.0),))
        scene = make_sampler_scene()
        self.assertIn("box_6x6_48x48", scene.geometry)

    def test_generated_box_files_are_named_by_size(self) -> None:
        self.assertEqual(
            organizer_app.box_filename(BoxSpec(16.0, 48.0, 40.0)),
            "Box 16 x 48 x 40.3mf",
        )
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            organizer_app.generate_kit_files(
                BoxSpec(16.0, 48.0, 40.0), ConnectorSpec(), out
            )
            self.assertEqual(
                sorted(p.name for p in out.iterdir()),
                ["Box 16 x 48 x 40.3mf", "Connector.3mf"],
            )

    def test_unit_sizes_parse_to_grid_millimetres(self) -> None:
        self.assertEqual(
            organizer_app.parse_sizes("2x6,4x6"), ((16.0, 48.0), (32.0, 48.0))
        )
        self.assertEqual(organizer_app.parse_sizes("1x6"), ((8.0, 48.0),))
        # bare numbers are units; "mm" is explicit, so 8x8 is never ambiguous
        self.assertEqual(organizer_app.parse_sizes("8x8"), ((64.0, 64.0),))
        self.assertEqual(organizer_app.parse_sizes("8x8mm"), ((8.0, 8.0),))
        self.assertEqual(organizer_app.parse_sizes("16x48mm"), ((16.0, 48.0),))


class ExportAndCliTests(unittest.TestCase):
    def test_batch_launcher_bootstraps_and_checks_from_another_directory(self) -> None:
        batch = Path(__file__).resolve().with_name("Launch_Organizer_UI.bat")
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", str(batch), "--check"],
                cwd=directory, env=environment, capture_output=True,
                text=True, timeout=180, check=False,
            )
        combined = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, combined)
        self.assertIn("Organizer launcher ready", combined)

    def test_cli_generates_box_and_connector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    organizer_app.main(
                        ["kit", "--x", "32", "--y", "24", "--z", "45",
                         "--tolerance", "0.06", "--height", "12",
                         "--output-dir", str(output_dir)]
                    ),
                    0,
                )
            for filename in ("Box 32 x 24 x 45.3mf", "Connector.3mf"):
                path = output_dir / filename
                self.assertTrue(path.exists())
                self.assertEqual(validate_3mf(path, 1)["warnings"], 0)


class FloorLabelTests(unittest.TestCase):
    def test_letters_keep_their_holes(self) -> None:
        # glyph contours arrive unnested, so the middle of an O has to be
        # worked out rather than assumed
        outline = text_outline("O", TEXT_CAP_HEIGHT_IDEAL)
        rings = list(outline.geoms) if outline.geom_type == "MultiPolygon" else [outline]
        self.assertEqual(len(rings), 1)
        self.assertEqual(len(rings[0].interiors), 1)
        solid = text_outline("I", TEXT_CAP_HEIGHT_IDEAL)
        self.assertEqual(len(solid.interiors), 0)

    def test_letter_height_is_what_was_asked_for(self) -> None:
        for cap in (7.0, 8.5, 10.0):
            outline = text_outline("XX", cap)
            minx, miny, maxx, maxy = outline.bounds
            self.assertAlmostEqual(maxy - miny, cap, places=6)

    def test_a_label_that_fits_stays_at_the_ideal_height(self) -> None:
        cap, rotated = label_layout(BoxSpec(48.0, 48.0, 40.0), "M3")
        self.assertAlmostEqual(cap, TEXT_CAP_HEIGHT_IDEAL, places=6)
        self.assertFalse(rotated)

    def test_a_long_label_shrinks_before_it_turns(self) -> None:
        # square floor: turning cannot help, so it must shrink and stay flat
        cap, rotated = label_layout(BoxSpec(48.0, 48.0, 40.0), "BOLTS")
        self.assertFalse(rotated)
        self.assertLess(cap, TEXT_CAP_HEIGHT_IDEAL)
        self.assertGreaterEqual(cap, TEXT_CAP_HEIGHT_MIN)

    def test_it_turns_only_when_across_will_not_do(self) -> None:
        narrow = BoxSpec(16.0, 48.0, 40.0)
        for label in ("M3", "BOLTS"):
            cap, rotated = label_layout(narrow, label)
            self.assertTrue(rotated, label)
            self.assertGreaterEqual(cap, TEXT_CAP_HEIGHT_MIN)

    def test_the_label_never_goes_below_the_minimum_height(self) -> None:
        with self.assertRaisesRegex(ValueError, "will not fit"):
            label_layout(BoxSpec(48.0, 48.0, 40.0), "Washers")
        with self.assertRaisesRegex(ValueError, "will not fit"):
            label_layout(BoxSpec(16.0, 48.0, 40.0), "LONG WASHERS")

    def test_the_label_fits_inside_the_floor_it_was_measured_against(self) -> None:
        for spec, label in (
            (BoxSpec(48.0, 48.0, 40.0), "BOLTS"),
            (BoxSpec(16.0, 48.0, 40.0), "M3"),
            (BoxSpec(24.0, 40.0, 30.0), "NUTS"),
        ):
            mesh = make_floor_label(spec, label)
            inside_x, inside_y = spec.usable_inside
            self.assertLessEqual(mesh.extents[0], inside_x - 2 * TEXT_MARGIN + 1e-6)
            self.assertLessEqual(mesh.extents[1], inside_y - 2 * TEXT_MARGIN + 1e-6)
            # centred on the floor, and standing on it rather than sunk into it
            centre = mesh.bounds.mean(axis=0)
            self.assertAlmostEqual(centre[0], 0.0, places=6)
            self.assertAlmostEqual(centre[1], 0.0, places=6)
            # sunk into the top of the floor, flush with it
            self.assertAlmostEqual(
                mesh.bounds[0][2], spec.wall - TEXT_DEPTH, places=6
            )
            self.assertAlmostEqual(mesh.bounds[1][2], spec.wall, places=6)

    def test_the_label_is_sunk_into_the_floor_not_standing_on_it(self) -> None:
        for spec, label in (
            (BoxSpec(48.0, 48.0, 40.0), "BOLTS"),
            (BoxSpec(16.0, 48.0, 40.0), "M3"),
        ):
            plain = make_box(spec)
            inlay = make_floor_label(spec, label)
            # it occupies floor material, so against a plain box it would clash
            self.assertGreater(intersection_volume(plain, inlay), 0.1)
            # and leaves floor beneath it rather than going through
            self.assertGreater(inlay.bounds[0][2], 0.0)
            self.assertLess(inlay.bounds[0][2], spec.wall)

    def test_the_inlay_exactly_fills_the_pocket_cut_for_it(self) -> None:
        for spec, label in (
            (BoxSpec(48.0, 48.0, 40.0), "BOLTS"),
            (BoxSpec(16.0, 48.0, 40.0), "M3"),
            (BoxSpec(24.0, 40.0, 30.0), "NUTS"),
        ):
            plain = make_box(spec)
            pocketed, inlay = make_labelled_box(spec, label)
            self.assertTrue(pocketed.is_watertight)
            self.assertEqual(len(pocketed.split(only_watertight=False)), 1)
            # the pocket is exactly the inlay's size
            self.assertAlmostEqual(
                plain.volume - pocketed.volume, inlay.volume, places=4
            )
            # the two meet at their faces and nowhere else
            self.assertLess(intersection_volume(pocketed, inlay), 0.01)
            # put them back together and the box is whole again
            from organizer_engine import union as mesh_union

            self.assertAlmostEqual(
                mesh_union([pocketed, inlay]).volume, plain.volume, places=4
            )

    def test_turning_is_always_the_same_way_round(self) -> None:
        # so a row of printed boxes reads consistently: 90 degrees anticlockwise,
        # which puts the first letter at the bottom
        spec = BoxSpec(16.0, 48.0, 40.0)
        flat = text_outline("LJ", TEXT_CAP_HEIGHT_MIN)
        turned = make_floor_label(spec, "LJ")
        # "L" is left of "J" flat, and below it once turned
        self.assertLess(flat.bounds[0], flat.bounds[2])
        pieces = turned.split(only_watertight=False)
        self.assertEqual(len(pieces), 2)
        lowest = min(pieces, key=lambda part: part.bounds.mean(axis=0)[1])
        self.assertLess(lowest.extents[0], lowest.extents[1])

    def test_a_blank_label_changes_nothing(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        for blank in ("", "   ", None):
            self.assertEqual(
                organizer_app.box_filename(spec, blank or ""),
                "Box 48 x 48 x 40.3mf",
            )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / organizer_app.box_filename(spec)
            result = organizer_app.generate_box_file(spec, output, "   ")
            self.assertNotIn("label", result)
            self.assertEqual(validate_3mf(output, 1)["warnings"], 0)

    def test_a_labelled_box_is_two_objects_named_for_the_label(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        name = organizer_app.box_filename(spec, "BOLTS")
        self.assertEqual(name, "Box 48 x 48 x 40 BOLTS.3mf")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / name
            result = organizer_app.generate_box_file(spec, output, "BOLTS")
            self.assertEqual(result["label"]["label"], "BOLTS")
            self.assertEqual(result["label"]["depth_mm"], TEXT_DEPTH)
            report = validate_3mf(output, 2, multipart=("BOLTS",))
            self.assertEqual(report["warnings"], 0)
            self.assertEqual(
                report["names"], ["BOLTS", "Box 48 x 48 x 40"]
            )

    def test_labels_are_cleaned_for_the_filename(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        self.assertEqual(organizer_app.clean_label("  M3 / M4  "), "M3 M4")
        self.assertEqual(
            organizer_app.box_filename(spec, "M3/M4"), "Box 48 x 48 x 40 M3 M4.3mf"
        )

    def test_cli_labels_a_box(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "cli.3mf"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    organizer_app.main(
                        ["box", "--x", "48", "--y", "48", "--z", "40",
                         "--label", "NUTS", "--output", str(output)]
                    ),
                    0,
                )
            self.assertEqual(
                validate_3mf(output, 2, multipart=("NUTS",))["warnings"], 0
            )




class ReversibilityTests(unittest.TestCase):
    """A staple can only be set down one of two ways round; both must work."""

    @staticmethod
    def _spin(mesh, degrees=180.0):
        turned = mesh.copy()
        centre = mesh.bounds.mean(axis=0)
        turned.apply_translation(-centre)
        turned.apply_transform(
            trimesh.transformations.rotation_matrix(math.radians(degrees), (0, 0, 1))
        )
        turned.apply_translation(centre)
        return turned

    def test_the_connector_drops_on_either_way_round(self) -> None:
        connector = ConnectorSpec()
        for spec, position in (
            (BoxSpec(32.0, 32.0, 40.0), 0.0),
            (BoxSpec(16.0, 48.0, 40.0), 0.0),
            (BoxSpec(24.0, 48.0, 40.0), 4.0),
            (BoxSpec(48.0, 48.0, 24.0), -6.0),
        ):
            boxes = installed_boxes(spec, "y")
            seat_z = spec.z - connector.arm_depth
            clip = make_side_connector(spec, connector, "y", position)

            def fit(mesh, lift=0.0):
                placed = translated(mesh, (0.0, position, seat_z + lift))
                return sum(intersection_volume(placed, b) for b in boxes)

            for mesh, way in ((clip, "as made"), (self._spin(clip), "spun")):
                self.assertLess(fit(mesh), 1e-3, way)          # seats free
                self.assertGreater(fit(mesh, 0.5), 0.1, way)   # and locks

    def test_a_box_still_tiles_when_it_is_turned_round(self) -> None:
        for spec in (BoxSpec(32.0, 32.0, 40.0), BoxSpec(16.0, 48.0, 40.0)):
            mesh = make_box(spec)
            left = translated(mesh, (-spec.x / 2.0, 0.0, 0.0))
            for neighbour, way in (
                (mesh, "as printed"),
                (self._spin(mesh), "turned 180"),
            ):
                self.assertEqual(
                    intersection_volume(
                        left, translated(neighbour, (spec.x / 2.0, 0.0, 0.0))
                    ),
                    0.0,
                    way,
                )

    def test_a_turned_box_is_the_same_shape(self) -> None:
        mesh = make_box(BoxSpec(32.0, 32.0, 40.0))
        shared = intersection_volume(mesh, self._spin(mesh))
        self.assertAlmostEqual(shared / mesh.volume, 1.0, places=4)

    def test_the_lock_notches_mirror_about_the_connector_centre(self) -> None:
        # the reason it is reversible: bumps every half wave put the notches at
        # matching distances either side of the middle
        spec = BoxSpec(48.0, 48.0, 40.0)
        reach = spec.half_y - CORNER_INSET - LOCK_CORNER_CLEAR
        for centre in (0.0, 2.0, -4.0):
            under = [b - centre for b in lock_positions(reach)
                     if abs(b - centre) <= 6.6]
            self.assertTrue(under)
            self.assertEqual(sorted(under), sorted(-v for v in under))



class FlatInsideTests(unittest.TestCase):
    """An optional 0-1 mm band at the bottom whose walls are flat, not wavy."""

    @staticmethod
    def _cavity_area_at(spec, mesh, z, thickness=0.02):
        """Cross-section of the hole at height z, measured with a thin slab."""
        slab = _extrude_polygon(wavy_outer_polygon(spec), thickness)
        slab.apply_translation((0.0, 0.0, z))
        return difference([slab, mesh]).volume / thickness

    def test_off_by_default_and_range_checked(self) -> None:
        self.assertEqual(BoxSpec().flat_inside, 0.0)
        for good in (0.0, 0.35, 1.0):
            BoxSpec(32.0, 32.0, 40.0, flat_inside=good)
        for bad in (-0.1, 1.5):
            with self.assertRaisesRegex(ValueError, "between 0 and 1"):
                BoxSpec(32.0, 32.0, 40.0, flat_inside=bad)

    def test_the_band_is_flat_and_the_wave_carries_on_above_it(self) -> None:
        spec = BoxSpec(32.0, 32.0, 40.0, flat_inside=1.0)
        mesh = make_box(spec)
        flat = flat_cavity_polygon(spec).area
        wavy = wavy_cavity_polygon(spec).area
        self.assertLess(flat, wavy)          # the band adds material

        top = spec.wall + spec.flat_inside
        for z in (spec.wall + 0.05, spec.wall + 0.5, top - 0.05):
            self.assertAlmostEqual(
                self._cavity_area_at(spec, mesh, z), flat, delta=0.5, msg=f"z={z}"
            )
        # stay clear of the lock bumps, which sit in the top 5 mm
        for z in (top + 0.05, top + 2.0, spec.z - 12.0):
            self.assertAlmostEqual(
                self._cavity_area_at(spec, mesh, z), wavy, delta=0.5, msg=f"z={z}"
            )

    def test_the_band_height_follows_the_setting(self) -> None:
        # it is a height, not an on/off switch: half the number, half the band
        for flat in (0.4, 0.8):
            spec = BoxSpec(32.0, 32.0, 40.0, flat_inside=flat)
            mesh = make_box(spec)
            straight = flat_cavity_polygon(spec).area
            just_under = self._cavity_area_at(spec, mesh, spec.wall + flat - 0.05)
            just_over = self._cavity_area_at(spec, mesh, spec.wall + flat + 0.05)
            self.assertAlmostEqual(just_under, straight, delta=0.5)
            self.assertGreater(just_over, straight + 1.0)

    def test_no_band_at_all_when_it_is_off(self) -> None:
        spec = BoxSpec(32.0, 32.0, 40.0)
        mesh = make_box(spec)
        wavy = wavy_cavity_polygon(spec).area
        self.assertAlmostEqual(
            self._cavity_area_at(spec, mesh, spec.wall + 0.05), wavy, delta=0.5
        )

    def test_the_band_only_adds_material(self) -> None:
        plain = make_box(BoxSpec(32.0, 32.0, 40.0)).volume
        for flat in (0.5, 1.0):
            filled = make_box(BoxSpec(32.0, 32.0, 40.0, flat_inside=flat))
            self.assertEqual(mesh_report(f"flat_{flat}", filled)["components"], 1)
            self.assertGreater(filled.volume, plain)

    def test_the_band_never_cuts_into_the_wall(self) -> None:
        # it is sized to the innermost the wave reaches, so it cannot
        for flat in (0.5, 1.0):
            spec = BoxSpec(32.0, 32.0, 40.0, flat_inside=flat)
            straight = flat_cavity_polygon(spec)
            self.assertTrue(wavy_cavity_polygon(spec).contains(straight))

    def test_the_outside_and_the_wave_are_untouched(self) -> None:
        plain = wavy_outer_polygon(BoxSpec(32.0, 32.0, 40.0))
        banded = wavy_outer_polygon(BoxSpec(32.0, 32.0, 40.0, flat_inside=1.0))
        self.assertAlmostEqual(plain.area, banded.area, places=6)

    def test_the_connector_is_unaffected_on_a_normal_box(self) -> None:
        # the band sits on the floor, the arms hang from the rim
        connector = ConnectorSpec()
        for flat in (0.0, 0.5, 1.0):
            spec = BoxSpec(32.0, 32.0, 40.0, flat_inside=flat)
            clip = make_side_connector(spec, connector, "y")
            self.assertLess(validate_side_fit(spec, connector, clip, "y"), 1e-3)
            self.assertGreater(measure_lock(spec, connector)["lift_0.5_mm3"], 0.1)

    def test_a_shallow_box_says_why_the_band_will_not_work(self) -> None:
        with self.assertRaisesRegex(ValueError, "would collide"):
            make_side_connector(
                BoxSpec(32.0, 32.0, 10.0, flat_inside=1.0), ConnectorSpec(), "y"
            )
        # and the same box is fine without the band
        spec = BoxSpec(32.0, 32.0, 10.0)
        clip = make_side_connector(spec, ConnectorSpec(), "y")
        self.assertLess(validate_side_fit(spec, ConnectorSpec(), clip, "y"), 1e-3)

    def test_too_shallow_for_a_band_at_all_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "too shallow"):
            BoxSpec(32.0, 32.0, 1.5, flat_inside=1.0)

    def test_usable_inside_is_unchanged(self) -> None:
        # the band is exactly the rectangle usable_inside already reported
        plain = BoxSpec(32.0, 32.0, 40.0).usable_inside
        for flat in (0.5, 1.0):
            self.assertEqual(
                BoxSpec(32.0, 32.0, 40.0, flat_inside=flat).usable_inside, plain
            )

    def test_a_banded_box_still_tiles_and_still_turns(self) -> None:
        for flat in (0.5, 1.0):
            spec = BoxSpec(32.0, 32.0, 40.0, flat_inside=flat)
            mesh = make_box(spec)
            left = translated(mesh, (-spec.x / 2.0, 0.0, 0.0))
            for neighbour in (mesh, ReversibilityTests._spin(mesh)):
                self.assertEqual(
                    intersection_volume(
                        left, translated(neighbour, (spec.x / 2.0, 0.0, 0.0))
                    ),
                    0.0,
                )

    def test_cli_takes_the_band(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "flat.3mf"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    organizer_app.main(
                        ["box", "--x", "32", "--y", "32", "--z", "40",
                         "--flat-inside", "1.0", "--output", str(output)]
                    ),
                    0,
                )
            self.assertEqual(validate_3mf(output, 1)["warnings"], 0)


class PreviewTests(unittest.TestCase):
    def _kinds(self, scene):
        return [kind for _, kind in scene["faces"]]

    def test_preview_builds_a_solid_box_out_of_3d_faces(self) -> None:
        scene = organizer_app.preview_scene(BoxSpec(32.0, 32.0, 40.0))
        kinds = self._kinds(scene)
        for expected in ("outside", "inside", "rim", "floor"):
            self.assertIn(expected, kinds)
        self.assertEqual(kinds.count("floor"), 1)
        for points, _ in scene["faces"]:
            for point in points:
                self.assertEqual(len(point), 3)

    def test_preview_drops_faces_that_point_away_from_the_camera(self) -> None:
        # painting order alone cannot hide the far outside wall, so it has to be
        # culled: from above, its top edge really is nearer than the floor
        spec = BoxSpec(32.0, 32.0, 40.0)
        scene = organizer_app.preview_scene(spec)
        outer, _ = preview_rings(spec)
        self.assertLess(self._kinds(scene).count("outside"), len(outer))
        self.assertGreater(self._kinds(scene).count("outside"), 0)

    def test_preview_orders_faces_far_to_near(self) -> None:
        scene = organizer_app.preview_scene(BoxSpec(32.0, 32.0, 40.0))
        depths = [
            sum(organizer_app._towards_camera(p) for p in points) / len(points)
            for points, kind in scene["faces"]
            if kind not in ("label", "label_hole")
        ]
        self.assertEqual(depths, sorted(depths))

    def test_preview_keeps_floor_text_upright_and_unmirrored(self) -> None:
        # world +X must go right on the canvas and +Y must go up, or the label
        # comes out upside down or mirrored
        origin = organizer_app.iso_point((0.0, 0.0, 0.0))
        along_x = organizer_app.iso_point((10.0, 0.0, 0.0))
        along_y = organizer_app.iso_point((0.0, 10.0, 0.0))
        up_z = organizer_app.iso_point((0.0, 0.0, 10.0))
        self.assertGreater(along_x[0], origin[0])          # +X to the right
        self.assertLess(along_x[1], origin[1])             # and up the canvas
        self.assertLess(along_y[0], origin[0])             # +Y to the left
        self.assertLess(along_y[1], origin[1])             # and up
        self.assertLess(up_z[1], origin[1])                # taller is higher
        # a positive turn from +X to +Y keeps the drawing unmirrored
        ux, uy = along_x[0] - origin[0], -(along_x[1] - origin[1])
        vx, vy = along_y[0] - origin[0], -(along_y[1] - origin[1])
        self.assertGreater(ux * vy - uy * vx, 0.0)

    def test_preview_draws_the_label_on_the_floor(self) -> None:
        scene = organizer_app.preview_scene(BoxSpec(48.0, 48.0, 40.0), "BOLTS")
        self.assertTrue(scene["fits"])
        self.assertEqual(self._kinds(scene).count("label"), 5)       # B O L T S
        self.assertEqual(self._kinds(scene).count("label_hole"), 3)  # two in B, one in O
        for points, kind in scene["faces"]:
            if kind.startswith("label"):
                for point in points:
                    self.assertAlmostEqual(point[2], 0.8, places=6)

    def test_preview_never_lets_the_floor_paint_over_the_label(self) -> None:
        # each glyph used to carry its own depth, so letters on the far side
        # sorted behind the floor and vanished
        scene = organizer_app.preview_scene(BoxSpec(48.0, 48.0, 40.0), "BOLTS")
        kinds = self._kinds(scene)
        floor_at = kinds.index("floor")
        for index, kind in enumerate(kinds):
            if kind.startswith("label"):
                self.assertGreater(index, floor_at)

    def test_preview_has_no_label_faces_without_a_label(self) -> None:
        for blank in ("", "   "):
            scene = organizer_app.preview_scene(BoxSpec(48.0, 48.0, 40.0), blank)
            self.assertTrue(scene["fits"])
            self.assertNotIn("label", self._kinds(scene))

    def test_preview_says_so_when_the_label_will_not_fit(self) -> None:
        scene = organizer_app.preview_scene(BoxSpec(48.0, 48.0, 40.0), "Washers")
        self.assertFalse(scene["fits"])
        self.assertIn("will not fit", scene["message"])
        self.assertNotIn("label", self._kinds(scene))

    def test_preview_reports_outside_and_inside_together(self) -> None:
        scene = organizer_app.preview_scene(BoxSpec(32.0, 32.0, 40.0))
        self.assertEqual(scene["x_text"], "32mm (29 inside)")
        self.assertEqual(scene["y_text"], "32mm (29 inside)")
        self.assertEqual(scene["z_text"], "40mm tall")
        wide = organizer_app.preview_scene(BoxSpec(16.0, 48.0, 24.0))
        self.assertEqual(wide["x_text"], "16mm (13 inside)")
        self.assertEqual(wide["y_text"], "48mm (45 inside)")
        self.assertEqual(wide["z_text"], "24mm tall")

    def test_preview_transform_fits_the_whole_box_on_the_canvas(self) -> None:
        size = organizer_app.PREVIEW_SIZE
        for spec in (BoxSpec(32.0, 32.0, 40.0), BoxSpec(8.0, 48.0, 24.0)):
            to_canvas = organizer_app.preview_transform(spec)
            corners = [
                to_canvas((sx * spec.x / 2.0, sy * spec.y / 2.0, z))
                for sx in (-1, 1) for sy in (-1, 1) for z in (0.0, spec.z)
            ]
            for x, y in corners:
                self.assertGreaterEqual(x, 0.0)
                self.assertLessEqual(x, size)
                self.assertGreaterEqual(y, 0.0)
                self.assertLessEqual(y, size)


class DesktopUiTests(unittest.TestCase):
    def test_generating_does_not_pop_a_confirmation_dialog(self) -> None:
        # Success reports on the status line; only failures get a dialog.
        import inspect

        source = inspect.getsource(organizer_app.launch_ui)
        self.assertNotIn("showinfo", source)
        self.assertIn("showerror", source)

    def test_generate_actions_report_a_one_line_summary(self) -> None:
        box = BoxSpec(16.0, 48.0, 40.0)
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            organizer_app.generate_kit_files(box, ConnectorSpec(), out)
            self.assertEqual(
                sorted(p.name for p in out.iterdir()),
                ["Box 16 x 48 x 40.3mf", "Connector.3mf"],
            )

    def test_the_window_draws_a_populated_preview_and_full_readout(self) -> None:
        # both of these were claimed working once while silently doing nothing,
        # so assert the widgets actually have content
        import tkinter as tk

        found = {}

        def capture(root: tk.Tk, _n: int = 0) -> None:
            texts, drawn = [], 0
            stack = list(root.winfo_children())
            while stack:
                widget = stack.pop()
                try:
                    text = widget.cget("text")
                except tk.TclError:
                    text = ""
                if text:
                    texts.append(str(text))
                if isinstance(widget, tk.Canvas):
                    drawn += len(widget.find_all())
                    found["canvas_text"] = [
                        widget.itemcget(item, "text")
                        for item in widget.find_all()
                        if widget.type(item) == "text"
                    ]
                stack.extend(widget.winfo_children())
            found["texts"] = texts
            found["drawn"] = drawn
            root.destroy()

        with mock.patch.object(tk.Tk, "mainloop", capture):
            organizer_app.launch_ui()

        self.assertGreater(found["drawn"], 0)          # the preview drew something
        # the dimensions live on the preview now, not in a text block
        self.assertFalse(any("Grid footprint" in text for text in found["texts"]))
        self.assertFalse(any("take a connector" in text for text in found["texts"]))
        self.assertIn("16mm (13 inside)", found["canvas_text"])
        self.assertIn("40mm tall", found["canvas_text"])

    def test_ui_contains_the_sampler_button(self) -> None:
        import tkinter as tk

        labels: list[str] = []

        def capture_widgets(root: tk.Tk, _n: int = 0) -> None:
            stack = list(root.winfo_children())
            while stack:
                widget = stack.pop()
                try:
                    text = widget.cget("text")
                except tk.TclError:
                    text = ""
                if text:
                    labels.append(str(text))
                stack.extend(widget.winfo_children())
            root.destroy()

        with mock.patch.object(tk.Tk, "mainloop", capture_widgets):
            organizer_app.launch_ui()
        self.assertIn("Generate Sampler", labels)
        self.assertIn("Generate Box", labels)
        self.assertIn("Generate Connector", labels)
        self.assertIn("Advanced settings", labels)
        self.assertTrue(any("units of 8 mm" in l for l in labels))
        self.assertIn("Floor label", labels)
        self.assertIn("Part name", labels)
        self.assertIn("Flat wall band from base (0-1 mm)", labels)
        self.assertNotIn("Generate Corner", labels)
        # the sample plate is fixed, and there is no status bar
        self.assertFalse(any("Sample plate boxes" in l for l in labels))
        self.assertNotIn("Ready", labels)


class CompatibilityTests(unittest.TestCase):
    def test_default_meshes_match_their_reference_fingerprints(self) -> None:
        self.assertEqual(
            mesh_fingerprint(make_box(BoxSpec())), REFERENCE_FINGERPRINTS["box"]
        )
        self.assertEqual(
            mesh_fingerprint(make_side_connector(BoxSpec(), ConnectorSpec(), "y")),
            REFERENCE_FINGERPRINTS["connector"],
        )

    def test_the_connector_specification_is_locked(self) -> None:
        connector = ConnectorSpec()
        self.assertEqual(connector.tolerance, 0.02)
        self.assertEqual(connector.height, 9.6)
        self.assertEqual(LOCKED_CONNECTOR_LENGTH, 12.0)


class DimensionReadoutTests(unittest.TestCase):
    def test_outside_extent_matches_the_real_mesh(self) -> None:
        for units in (2, 3, 6, 9):
            spec = BoxSpec(x=units * GRID_PITCH, y=units * GRID_PITCH, z=40.0)
            mesh = make_box(spec)
            claimed = spec.outside_extent
            self.assertAlmostEqual(mesh.extents[0], claimed[0], delta=0.02)
            self.assertAlmostEqual(mesh.extents[1], claimed[1], delta=0.02)
            self.assertEqual(spec.footprint, (spec.x, spec.y))

    def test_usable_inside_is_the_largest_rectangle_that_fits(self) -> None:
        from shapely.geometry import box as shapely_box

        for units in (2, 3, 6, 9):
            spec = BoxSpec(x=units * GRID_PITCH, y=units * GRID_PITCH, z=40.0)
            cavity = wavy_cavity_polygon(spec)
            wide, deep = spec.usable_inside

            def rect(w: float, d: float):
                return shapely_box(-w / 2.0, -d / 2.0, w / 2.0, d / 2.0)

            self.assertTrue(rect(wide, deep).within(cavity))          # fits
            self.assertFalse(rect(wide + 0.3, deep + 0.3).within(cavity))  # tight


if __name__ == "__main__":
    unittest.main(verbosity=2)
