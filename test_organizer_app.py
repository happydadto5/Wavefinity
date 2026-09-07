"""External-behavior regression tests for the organizer generator."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import math
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile
from unittest import mock

import numpy as np
import trimesh
from shapely.geometry import Point

import organizer_app
import organizer_inserts
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
    connector_fits,
    connector_half_widths,
    generate_sampler,
    make_sampler_scene,
    flat_cavity_polygon,
    _extrude_polygon,
    difference,
    preview_rings,
    make_floor_label,
    make_labelled_box,
    make_scoop,
    make_top_label,
    make_top_label_ledge,
    make_top_labelled_box,
    placed_label_outline,
    label_layout,
    label_report,
    top_label_outline,
    top_label_report,
    top_label_zone,
    SCOOP_FLOOR_TOLERANCE,
    scoop_dimensions,
    scoop_floor_zone,
    scoop_keep_out,
    text_outline,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_CAP_HEIGHT_MIN,
    TEXT_MARGIN,
    TEXT_DEPTH,
    TOP_LABEL_CAP_HEIGHT,
    TOP_LABEL_LEDGE_DEPTH,
    connector_for_print,
    differing_connector_plan,
    differing_drop_fraction,
    differing_web_reach,
    installed_boxes,
    installed_side_boxes,
    intersection_volume,
    lock_positions,
    make_box,
    mating_clearance,
    nested_clearance,
    placed_outline,
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
from organizer_inserts import (
    build_features,
    make_cartridge_insert,
    make_fitted_insert,
    resolved_options,
)


REFERENCE_FINGERPRINTS = {
    # Re-pinned when the floor became its own setting and its default dropped
    # from 0.8 to 0.6 mm. Only the floor moved: the connector's fingerprint is
    # byte-identical either side of that change, which is what says the wave,
    # the mating and the lock were not touched.
    "box": "884CE0CA18924E23054376E9DC6457DA6EF22AD11A62606DE58DA61AC7CB5A19",
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
    def test_base_thickness_changes_only_the_floor_material(self) -> None:
        thin = BoxSpec(32.0, 32.0, 24.0, base_thickness=0.6)
        thick = replace(thin, base_thickness=1.0)

        thin_mesh = make_box(thin)
        thick_mesh = make_box(thick)

        # The outside, walls, rim and locks do not move.  The only added
        # material is the 0.4 mm slice beneath the unchanged cavity.
        np.testing.assert_allclose(thick_mesh.bounds, thin_mesh.bounds, atol=1e-6)
        self.assertAlmostEqual(
            thick_mesh.volume - thin_mesh.volume,
            wavy_cavity_polygon(thin).area * 0.4,
            places=4,
        )

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

    def test_mixed_sizes_mate_left_to_right_and_top_to_bottom(self) -> None:
        square = make_box(BoxSpec(24.0, 24.0, 40.0))

        tall = make_box(BoxSpec(24.0, 48.0, 40.0))
        left = translated(tall, (-12.0, 0.0, 0.0))
        right_bottom = translated(square, (12.0, -12.0, 0.0))
        right_top = translated(square, (12.0, 12.0, 0.0))

        wide = make_box(BoxSpec(48.0, 24.0, 40.0))
        bottom = translated(wide, (0.0, -12.0, 0.0))
        top_left = translated(square, (-12.0, 12.0, 0.0))
        top_right = translated(square, (12.0, 12.0, 0.0))

        for first, second in (
            (left, right_bottom), (left, right_top),
            (bottom, top_left), (bottom, top_right),
        ):
            self.assertEqual(intersection_volume(first, second), 0.0)

    def test_a_mixed_size_seam_clears_exactly_as_much_as_a_matched_one(self) -> None:
        """The point of the 8 mm grid: size has no say in how walls mate.

        Zero overlap is not enough to prove that - two bins parked a mile apart
        also fail to overlap.  Every shared wall has to measure the *same* gap
        as a matched pair, or the wave is out of phase and the bins are only
        pretending to nest.
        """
        square = BoxSpec(24.0, 24.0, 40.0)
        matched = mating_clearance(square, (-12.0, 0.0), square, (12.0, 0.0))
        self.assertAlmostEqual(matched, nested_clearance(), places=3)

        tall, wide, thin, small = (
            BoxSpec(24.0, 48.0, 40.0), BoxSpec(48.0, 24.0, 40.0),
            BoxSpec(8.0, 24.0, 40.0), BoxSpec(16.0, 16.0, 40.0),
        )
        seams = (
            # left wall to right wall, one bin against two shorter ones
            ((tall, (-12.0, 0.0)), (square, (12.0, -12.0))),
            ((tall, (-12.0, 0.0)), (square, (12.0, 12.0))),
            # top wall to bottom wall, same story turned 90 degrees
            ((wide, (0.0, -12.0)), (square, (-12.0, 12.0))),
            ((wide, (0.0, -12.0)), (square, (12.0, 12.0))),
            # the extremes of the size range against each other
            ((thin, (-4.0, 0.0)), (wide, (24.0, 0.0))),
            ((small, (-8.0, 8.0)), (tall, (12.0, 0.0))),
        )
        for (first, first_at), (second, second_at) in seams:
            with self.subTest(a=first.footprint, b=second.footprint):
                self.assertAlmostEqual(
                    mating_clearance(first, first_at, second, second_at),
                    matched, places=3,
                )

    def test_corners_stay_behind_the_wave_so_they_never_decide_the_fit(self) -> None:
        """The two long corner flats are cosmetic, not a mating surface.

        The odd wave leaves one diagonal's walls ending on a crest and the
        other's on a trough, so two of the four corner chords come out roughly
        twice as long as the other two.  That asymmetry is fine as long as
        every chord cuts *inward* from the wave envelope: a corner that stands
        back can only add clearance, never take it away.
        """
        square = BoxSpec(24.0, 24.0, 40.0)
        outline = placed_outline(square)
        for corner in ((12.0, 12.0), (12.0, -12.0), (-12.0, -12.0), (-12.0, 12.0)):
            standoff = min(
                math.dist(corner, point) for point in outline.exterior.coords
            )
            with self.subTest(corner=corner):
                self.assertGreater(standoff, WAVE_AMPLITUDE)
                self.assertLess(standoff, CORNER_INSET * 2.0)

        # Diagonal neighbours meet corner to corner and nothing else, so they
        # have to clear by more than a shared wall does.
        diagonal = mating_clearance(square, (-12.0, -12.0), square, (12.0, 12.0))
        self.assertGreater(diagonal, nested_clearance() * 4.0)

    def test_a_packed_drawer_of_seven_different_sizes_has_no_collisions(self) -> None:
        tiles = (
            (BoxSpec(24.0, 48.0, 40.0), (-12.0, 0.0)),
            (BoxSpec(24.0, 24.0, 40.0), (12.0, 12.0)),
            (BoxSpec(24.0, 24.0, 40.0), (12.0, -12.0)),
            (BoxSpec(16.0, 16.0, 40.0), (32.0, 16.0)),
            (BoxSpec(16.0, 8.0, 40.0), (32.0, 4.0)),
            (BoxSpec(8.0, 8.0, 40.0), (28.0, -4.0)),
            (BoxSpec(48.0, 24.0, 40.0), (0.0, -36.0)),
        )
        for index, (spec, centre) in enumerate(tiles):
            for other, other_centre in tiles[index + 1:]:
                with self.subTest(a=centre, b=other_centre):
                    gap = mating_clearance(spec, centre, other, other_centre)
                    self.assertGreaterEqual(gap, nested_clearance() - 1e-3)

    def test_an_off_lattice_placement_is_refused_rather_than_measured(self) -> None:
        square = BoxSpec(24.0, 24.0, 40.0)
        with self.assertRaisesRegex(ValueError, "wave lattice"):
            placed_outline(square, (2.0, 0.0))
        with self.assertRaisesRegex(ValueError, "wave lattice"):
            mating_clearance(square, (0.0, 0.0), square, (0.0, 26.0))

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


class PreviewRingDensityTests(unittest.TestCase):
    """The browser preview's coarse wall outline, not the exported mesh.

    ``preview_rings`` used to spend a fixed point budget on every wall
    regardless of its length, so on a non-square box the longer pair read
    as a smooth curve only if it happened to be short enough - a 45 mm
    wall got the same ~22 points as a 13 mm one, roughly two points per
    4 mm wave cycle, which looks like straight segments meeting at angles
    rather than a wave. Sampling by density instead of by a fixed total
    fixes that; these pin the density is actually constant, not just "more
    points on a bigger box."
    """

    def test_a_longer_wall_gets_proportionally_more_preview_points(self) -> None:
        square = BoxSpec(32.0, 32.0, 40.0)
        elongated = BoxSpec(16.0, 96.0, 40.0)
        outer_square, _ = preview_rings(square)
        outer_elongated, _ = preview_rings(elongated)
        # before the fix this ratio was ~1 - a fixed per-wall budget didn't
        # care how much longer the elongated box's long walls actually were
        self.assertGreater(len(outer_elongated), len(outer_square) * 1.5)

    def test_the_short_and_long_wall_pair_sample_at_the_same_density(self) -> None:
        spec = BoxSpec(16.0, 48.0, 40.0)
        density = 7.0
        tangent_x = spec.half_x - CORNER_INSET
        tangent_y = spec.half_y - CORNER_INSET
        count_x = max(4, round(density * 2.0 * tangent_x / WAVE_LENGTH))
        count_y = max(4, round(density * 2.0 * tangent_y / WAVE_LENGTH))
        outer, _ = preview_rings(spec, density)
        self.assertEqual(len(outer), 2 * count_x + 2 * count_y)
        # points per mm of wall length - close between the short (x) and
        # long (y) wall pair is exactly what "equally smooth" means here
        density_x = count_x / (2.0 * tangent_x)
        density_y = count_y / (2.0 * tangent_y)
        self.assertAlmostEqual(density_x, density_y, delta=0.05)


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

    def test_one_connector_locks_a_tall_bin_to_a_short_neighbour(self) -> None:
        """The case the grid exists for: a 24 x 48 sharing a wall with two
        24 x 24s, and one universal clip that grips whichever pair it lands on.

        ``measure_lock`` only ever stands two identical bins side by side, so
        nothing else in the suite covers a seam where the two neighbours are
        different sizes.  A clip that seats free and then bites when lifted is
        the whole contract, and it has to hold at every legal position along
        the seam - including one straddling the joint between the two short
        bins, where the arm is gripping two separate solids at once.
        """
        tall, short = BoxSpec(24.0, 48.0, 40.0), BoxSpec(24.0, 24.0, 40.0)
        connector = ConnectorSpec()
        neighbours = [
            translated(make_box(tall), (-12.0, 0.0, 0.0)),
            translated(make_box(short), (12.0, -12.0, 0.0)),
            translated(make_box(short), (12.0, 12.0, 0.0)),
        ]
        clip = make_side_connector(tall, connector, "y", 0.0)
        seated_z = tall.z - connector.arm_depth

        def overlap(position, lift=0.0):
            seated = translated(clip, (0.0, position, seated_z + lift))
            return sum(intersection_volume(seated, one) for one in neighbours)

        # Every step the seam has room for, except the two nearest the joint
        # where the two short bins butt: their end walls stand in the arm's way,
        # which is a placement rule, not a fault in the geometry.
        for position in (-16.0, -12.0, -8.0, 8.0, 12.0, 16.0):
            self.assertTrue(connector_fits(tall, "y", position))
            with self.subTest(position=position):
                self.assertLess(overlap(position), 1e-3)
                self.assertGreater(overlap(position, lift=0.5), 0.05)

    def test_a_clip_will_not_straddle_the_joint_between_two_short_bins(self) -> None:
        """A clip has to sit against one neighbour, not across two of them.

        Where two short bins butt end to end, the far side of the seam is not
        an open cavity - it is those bins' end walls, full height.  An arm
        lowered there lands on solid material.  The clip has to clear the joint
        by half its own length, which on the 4 mm lattice means the first legal
        spot is 8 mm away.
        """
        tall, short = BoxSpec(24.0, 48.0, 40.0), BoxSpec(24.0, 24.0, 40.0)
        connector = ConnectorSpec()
        neighbours = [
            translated(make_box(tall), (-12.0, 0.0, 0.0)),
            translated(make_box(short), (12.0, -12.0, 0.0)),
            translated(make_box(short), (12.0, 12.0, 0.0)),
        ]
        clip = make_side_connector(tall, connector, "y", 0.0)
        seated_z = tall.z - connector.arm_depth

        def overlap(position):
            seated = translated(clip, (0.0, position, seated_z))
            return sum(intersection_volume(seated, one) for one in neighbours)

        self.assertGreater(overlap(0.0), 1.0)     # straddling the joint: blocked
        self.assertGreater(overlap(4.0), 1.0)     # still catching an end wall
        self.assertLess(overlap(8.0), 1e-3)       # clear of it by half a clip
        self.assertLess(overlap(-8.0), 1e-3)

    def test_neighbouring_bins_of_any_size_share_one_bump_lattice(self) -> None:
        # Two 24 mm bins stacked against one 48 mm bin put their bumps on the
        # same run of odd millimetres, which is why a clip straddling the joint
        # engages both of them.
        seam = {}
        for spec, centre in (
            (BoxSpec(24.0, 48.0, 40.0), 0.0),
            (BoxSpec(24.0, 24.0, 40.0), -12.0),
            (BoxSpec(24.0, 24.0, 40.0), 12.0),
        ):
            reach = spec.half_y - CORNER_INSET - LOCK_CORNER_CLEAR
            seam[centre] = {round(centre + p, 6) for p in lock_positions(reach)}
        self.assertTrue(seam[-12.0] < seam[0.0])
        self.assertTrue(seam[12.0] < seam[0.0])
        self.assertFalse(seam[-12.0] & seam[12.0])


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

    def test_a_shorter_bin_gets_an_extended_locking_arm(self) -> None:
        box, connector = BoxSpec(32.0, 32.0, 40.0), ConnectorSpec()
        clip = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=40.0,
            bin_b_height=24.0,
        )
        self.assertAlmostEqual(clip.bounds[0][2], -16.0, places=5)
        self.assertTrue(clip.is_watertight)
        self.assertLess(
            validate_side_fit(
                box, connector, clip, "y", 0.0, bin_a_height=40.0,
                bin_b_height=24.0,
            ),
            1e-3,
        )
        self.assertGreater(
            measure_lock(
                box, connector, "y", 0.0, bin_a_height=40.0,
                bin_b_height=24.0,
            )["lift_0.5_mm3"],
            0.1,
        )

    def test_a_big_rim_difference_fattens_and_lengthens_the_clip(self) -> None:
        """A 50 -> 20 mm pair: the arm over the short bin spans 30 mm with no
        wall beside it.  A plain 1.0 mm arm there is an unbraced blade, so it
        is grown into a web and the whole part is run longer - while still
        seating free, still biting when lifted, and not fouling either bin.
        """
        box, connector = BoxSpec(40.0, 40.0, 50.0), ConnectorSpec()
        plain = make_side_connector(box, connector, "y", 0.0, 12.0)
        clip = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=50.0, bin_b_height=20.0,
        )
        self.assertTrue(clip.is_watertight)
        # +50% length at the full 30 mm drop, and thicker across the seam
        self.assertAlmostEqual(differing_drop_fraction(30.0), 1.0, places=6)
        self.assertAlmostEqual(clip.extents[1], 18.0, places=2)
        self.assertGreater(clip.extents[0], plain.extents[0])
        # z envelope is still just the cap plus the 30 mm extension
        self.assertAlmostEqual(clip.extents[2], connector.height + 30.0, places=3)
        # Cap covers the entire gusset width at top z so there is no hollow shelf
        top_verts = clip.vertices[clip.vertices[:, 2] > connector.height - 0.05]
        self.assertAlmostEqual(top_verts[:, 0].max(), clip.bounds[1][0], places=3)
        # seats without touching the two installed bins, and locks on lift
        self.assertLess(
            validate_side_fit(
                box, connector, clip, "y", 0.0, bin_a_height=50.0, bin_b_height=20.0,
            ),
            1e-3,
        )
        self.assertGreater(
            measure_lock(
                box, connector, "y", 0.0, bin_a_height=50.0, bin_b_height=20.0,
            )["lift_0.5_mm3"],
            0.1,
        )

    def test_the_web_runs_on_the_taller_wall_where_the_short_one_is_missing(
        self,
    ) -> None:
        """The whole point of the web, and the thing a width check misses.

        Over the drop the seam holds one wall, not two: the short bin's has not
        started yet.  The channel is cut for two, so half of it is empty air and
        the clip would bear on nothing for the entire span - locked at its two
        ends and free to rock everywhere between.  The web has to reach back
        across and run on the taller bin's outer face.
        """
        tall, short = 50.0, 20.0
        box, connector = BoxSpec(40.0, 40.0, tall), ConnectorSpec()
        clip = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=tall, bin_b_height=short,
        )
        seated = translated(
            clip, seat_transform(box, connector, 0.0, "y", tall)
        )
        tall_bin = installed_side_boxes(box, "y", tall, short)[0]

        def span_at(mesh, z):
            """x-interval of solid across the seam at height ``z``."""
            knife = trimesh.creation.box(extents=(20.0, 0.05, 0.05))
            knife.apply_translation((0.0, 0.0, z))
            hit = knife.intersection(mesh)
            if hit.is_empty or hit.volume < 1e-9:
                return None
            return float(hit.bounds[0][0]), float(hit.bounds[1][0])

        # Between the taller bin's arm (which stops arm_depth below its rim) and
        # the taper into the short bin, the web is all there is across the seam.
        arm_bottom = tall - connector.arm_depth
        for z in (arm_bottom - 1.0, 35.0, 30.0, 27.0):
            clip_span, wall_span = span_at(seated, z), span_at(tall_bin, z)
            self.assertIsNotNone(clip_span, z)
            self.assertIsNotNone(wall_span, z)
            gap = clip_span[0] - wall_span[1]
            # Runs on that wall rather than floating a whole wall-width away.
            self.assertGreater(gap, 0.0, f"web fouls the taller wall at z={z}")
            self.assertLess(gap, 0.25, f"web is not bearing on anything at z={z}")

    def test_every_rim_difference_makes_one_sound_solid(self) -> None:
        """Sweep the drop, not a couple of favourite pairs.

        The web ramps in steps and its inner face tracks the channel closely
        for the whole drop, so particular drops used to land a near-parallel
        pair of surfaces inside the vertex-weld tolerance and hand back a leaky
        mesh - silently, and only at some heights.
        """
        connector = ConnectorSpec()
        tall = 50.0
        for drop in range(0, 41):
            box = BoxSpec(40.0, 40.0, tall)
            clip = make_side_connector(
                box, connector, "y", 0.0, 12.0,
                bin_a_height=tall, bin_b_height=tall - drop,
            )
            self.assertTrue(clip.is_watertight, f"leaky mesh at a {drop} mm drop")
            self.assertTrue(clip.is_winding_consistent, f"bad winding at {drop} mm")
            self.assertGreater(clip.volume, 0.0, f"empty at a {drop} mm drop")

    def test_the_tallest_drop_still_seats_locks_and_prints_flat(self) -> None:
        """A 60 -> 20 pair, past the drop the ramps are maxed at.

        The web bears on the taller wall the whole way down, so a span this
        long is guided rather than cantilevered, and the whole part still has
        to come off the plate without support with its cap face down.
        """
        tall, short = 60.0, 20.0
        box, connector = BoxSpec(40.0, 40.0, tall), ConnectorSpec()
        clip = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=tall, bin_b_height=short,
        )
        self.assertTrue(clip.is_watertight)
        self.assertLess(
            validate_side_fit(
                box, connector, clip, "y", 0.0, bin_a_height=tall, bin_b_height=short,
            ),
            1e-3,
        )
        self.assertGreater(
            measure_lock(
                box, connector, "y", 0.0, bin_a_height=tall, bin_b_height=short,
            )["lift_0.5_mm3"],
            0.1,
        )
        # Cap down, nothing overhangs: no downward-facing face clear of the
        # build plate may lean past 45 degrees off vertical.
        printed = connector_for_print(clip)
        plate = float(printed.bounds[0][2])
        normals, centres = printed.face_normals, printed.triangles_center
        airborne = (
            (normals[:, 2] < -1e-6)
            & (centres[:, 2] > plate + 0.5)
            & (printed.area_faces > 0.05)
        )
        if airborne.any():
            off_vertical = np.degrees(
                np.arcsin(np.clip(-normals[airborne][:, 2], 0.0, 1.0))
            ).max()
            self.assertLessEqual(
                off_vertical, 45.0, "the printed clip needs support"
            )

    def test_the_plan_reports_the_web_that_is_actually_built(self) -> None:
        """The readout has to include the fixed inward reach.

        The reach does not scale with the drop, so at small drops the web is
        thicker than the drop-scaled target alone would suggest - and that is
        the number a person is shown before they print.
        """
        box, connector = BoxSpec(40.0, 40.0, 50.0), ConnectorSpec()
        reach = differing_web_reach(box, connector)
        self.assertGreater(reach, 0.0)
        for drop in (4.0, 10.0, 16.0):
            plan = differing_connector_plan(connector, 12.0, 50.0, 50.0 - drop, box)
            self.assertAlmostEqual(
                plan["web_thickness_mm"], connector.arm_thickness + reach, places=6
            )
        # At the full drop the drop-scaled growth is the wider of the two.
        full = differing_connector_plan(connector, 12.0, 50.0, 20.0, box)
        self.assertAlmostEqual(full["web_thickness_mm"], 3.0, places=6)

    def test_a_tiny_rim_difference_leaves_the_clip_plain(self) -> None:
        box, connector = BoxSpec(32.0, 32.0, 40.0), ConnectorSpec()
        plain = make_side_connector(box, connector, "y", 0.0, 12.0)
        near = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=40.0, bin_b_height=38.5,
        )
        self.assertEqual(differing_drop_fraction(1.5), 0.0)
        self.assertAlmostEqual(near.extents[1], plain.extents[1], places=5)
        self.assertAlmostEqual(near.extents[0], plain.extents[0], places=5)

    def test_a_too_shallow_short_bin_is_refused_with_a_clear_message(self) -> None:
        # Pair a 40 mm bin with one shorter than the arms are deep: the arm
        # would punch into that bin's base slab and the clip could not seat on
        # either side.  Say so plainly, not as a bare fit-check collision.
        box, connector = BoxSpec(32.0, 32.0, 40.0), ConnectorSpec()
        with self.assertRaisesRegex(ValueError, "too shallow for this connector"):
            make_side_connector(
                box, connector, "y", 0.0, 12.0, bin_a_height=40.0, bin_b_height=8.5,
            )
        # One that just clears the base slab still builds and seats cleanly.
        ok = make_side_connector(
            box, connector, "y", 0.0, 12.0, bin_a_height=40.0, bin_b_height=12.0,
        )
        self.assertLess(
            validate_side_fit(
                box, connector, ok, "y", 0.0, bin_a_height=40.0, bin_b_height=12.0,
            ),
            1e-3,
        )

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
            (BoxSpec(24.0, 72.0, 40.0), 4.0),      # the closest legal step
        ):
            other = make_side_connector(spec, connector, "y", position)
            self.assertAlmostEqual(other.volume, reference.volume, places=4)
            shared = intersection_volume(reference, other)
            self.assertAlmostEqual(shared / reference.volume, 1.0, places=5)

    def test_the_printed_clip_still_seats_when_slid_to_another_lattice_step(
        self,
    ) -> None:
        """Universality means the *printed* part, not a freshly generated one.

        Every other check regenerates the clip for the position it is testing,
        which cannot catch a part that is only correct where it was made.  This
        one prints once and slides it, which is what actually happens on a
        drawer full of bins.
        """
        box, connector = BoxSpec(24.0, 72.0, 40.0), ConnectorSpec()
        boxes = installed_boxes(box, "y")
        printed = make_side_connector(box, connector, "y", 0.0)
        seat_z = box.z - connector.arm_depth
        for position in (-16.0, -8.0, -4.0, 0.0, 4.0, 8.0, 16.0):
            seated = translated(printed, (0.0, position, seat_z))
            lifted = translated(printed, (0.0, position, seat_z + 0.5))
            with self.subTest(position=position):
                self.assertLess(
                    sum(intersection_volume(seated, one) for one in boxes), 1e-3
                )
                self.assertGreater(
                    sum(intersection_volume(lifted, one) for one in boxes), 0.05
                )

    def test_off_lattice_connector_position_is_rejected(self) -> None:
        spec = BoxSpec(24.0, 48.0, 40.0)
        make_side_connector(spec, ConnectorSpec(), "y", 4.0)   # one whole wave: fine
        for bad in (1.0, 2.0, 2.5, 3.0, 6.0):
            with self.subTest(position=bad):
                with self.assertRaisesRegex(ValueError, "whole multiple"):
                    make_side_connector(spec, ConnectorSpec(), "y", bad)

    def test_a_half_wave_along_the_seam_needs_a_mirrored_clip_nobody_prints(
        self,
    ) -> None:
        """Why the rule is a whole wave and not half of one.

        The wave inverts every half cycle, so the clip a half-wave along wants
        is this one reflected in the seam - same volume, and a shape no amount
        of turning a printed part over will produce.  Slide the real part there
        and it meets the wall crest to crest.  The rule used to allow half
        waves, and every fixed position the suite checked happened to land on a
        whole one, so nothing ever said so.
        """
        box, connector = BoxSpec(24.0, 72.0, 40.0), ConnectorSpec()
        boxes = installed_boxes(box, "y")
        printed = make_side_connector(box, connector, "y", 0.0)
        seat_z = box.z - connector.arm_depth

        mirrored = printed.copy()
        mirrored.apply_transform(np.diag([-1.0, 1.0, 1.0, 1.0]))
        self.assertAlmostEqual(mirrored.volume, printed.volume, places=4)
        self.assertLess(
            intersection_volume(printed, mirrored) / printed.volume, 0.7
        )

        def overlap(mesh, position):
            seated = translated(mesh, (0.0, position, seat_z))
            return sum(intersection_volume(seated, one) for one in boxes)

        self.assertGreater(overlap(printed, 2.0), 1.0)     # the real part jams
        self.assertLess(overlap(mirrored, 2.0), 1e-3)      # only a mirror fits
        self.assertGreater(overlap(mirrored, 0.0), 1.0)    # and only there

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
                ["Box 16 x 48 x 40.3mf", "Connector - Same height.3mf"],
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
    def test_exported_connector_is_flipped_flat_side_down(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "Connector.3mf"
            result = organizer_app.generate_side_file(
                BoxSpec(32.0, 32.0, 40.0), ConnectorSpec(), output,
                bin_a_height=40.0, bin_b_height=24.0,
            )
            printed = trimesh.load(output, force="mesh")
            self.assertAlmostEqual(float(printed.bounds[0][2]), 0.0, places=5)
            self.assertAlmostEqual(float(printed.extents[2]), 25.6, places=5)
            self.assertEqual(result["fit"]["print_orientation"], "flat cap down")

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
            for filename in ("Box 32 x 24 x 45.3mf", "Connector - Tol 0.06mm Height 12mm.3mf"):
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
                mesh.bounds[0][2], spec.base_thickness - TEXT_DEPTH, places=6
            )
            self.assertAlmostEqual(mesh.bounds[1][2], spec.base_thickness, places=6)

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

    def test_connector_filename_defaults_and_custom_options(self) -> None:
        self.assertEqual(
            organizer_app.connector_filename(),
            "Connector - Same height.3mf",
        )
        self.assertEqual(
            organizer_app.connector_filename(ConnectorSpec()),
            "Connector - Same height.3mf",
        )
        # Equal heights with different_heights=True should still be same height
        self.assertEqual(
            organizer_app.connector_filename(different_heights=True, bin_a_height=40.0, bin_b_height=40.0),
            "Connector - Same height.3mf",
        )
        # Different heights
        self.assertEqual(
            organizer_app.connector_filename(different_heights=True, bin_a_height=40.0, bin_b_height=20.0),
            "Connector - 40mm to 20mm.3mf",
        )
        # Custom tolerance
        self.assertEqual(
            organizer_app.connector_filename(ConnectorSpec(tolerance=0.06)),
            "Connector - Tol 0.06mm.3mf",
        )
        # Custom height
        self.assertEqual(
            organizer_app.connector_filename(ConnectorSpec(height=12.0)),
            "Connector - Height 12mm.3mf",
        )
        # Custom length
        self.assertEqual(
            organizer_app.connector_filename(length=16.0),
            "Connector - Len 16mm.3mf",
        )
        # Custom arm thickness
        self.assertEqual(
            organizer_app.connector_filename(arm_thickness=1.5),
            "Connector - Arm 1.5mm.3mf",
        )
        # Multiple non-default variables combined
        self.assertEqual(
            organizer_app.connector_filename(
                ConnectorSpec(tolerance=0.05, height=14.0),
                length=18.0,
                bin_a_height=50.0,
                bin_b_height=30.0,
                arm_thickness=1.2,
                different_heights=True,
            ),
            "Connector - 50mm to 30mm Tol 0.05mm Height 14mm Len 18mm Arm 1.2mm.3mf",
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


class BinCustomizationTests(unittest.TestCase):
    def test_top_label_is_fixed_five_mm_on_a_seven_mm_ledge(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        report = top_label_report(spec, "M3")
        outline = top_label_outline(spec, "M3")
        zone = top_label_zone(spec)
        self.assertEqual(report["cap_height_mm"], TOP_LABEL_CAP_HEIGHT)
        self.assertEqual(report["ledge_depth_mm"], TOP_LABEL_LEDGE_DEPTH)
        self.assertEqual(report["ledge_underside_degrees"], 45.0)
        self.assertAlmostEqual(zone.bounds[3] - zone.bounds[1], 7.0)
        self.assertTrue(zone.covers(outline))

    def test_top_label_ledge_and_inlay_are_clean_flush_solids(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        ledge = make_top_label_ledge(spec)
        inlay = make_top_label(spec, "M3")
        pocketed, installed = make_top_labelled_box(spec, "M3")
        self.assertTrue(ledge.is_volume)
        self.assertAlmostEqual(ledge.bounds[0][2], spec.z - 7.0)
        self.assertAlmostEqual(ledge.bounds[1][2], spec.z)
        self.assertAlmostEqual(inlay.bounds[1][2], spec.z)
        self.assertTrue(pocketed.is_volume)
        self.assertLess(intersection_volume(pocketed, installed), 0.01)

    def test_scoop_is_full_width_and_rises_halfway_up_the_inside_wall(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        scoop = make_scoop(spec)
        height, run = scoop_dimensions(spec)
        inside_x, inside_y = spec.usable_inside
        self.assertTrue(scoop.is_volume)
        self.assertAlmostEqual(scoop.extents[0], inside_x)
        self.assertAlmostEqual(scoop.bounds[0][2], spec.base_thickness)
        self.assertAlmostEqual(scoop.bounds[1][2], spec.base_thickness + height)
        self.assertAlmostEqual(
            scoop_floor_zone(spec).bounds[3] - scoop_floor_zone(spec).bounds[1], run
        )

    def test_scoop_sits_against_the_front_wall_opposite_the_top_label(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        _height, run = scoop_dimensions(spec)
        _inside_x, inside_y = spec.usable_inside
        zone = scoop_floor_zone(spec)
        # front wall is -Y; the strip starts at the wall and reaches `run` in
        self.assertAlmostEqual(zone.bounds[1], -inside_y / 2.0)
        self.assertAlmostEqual(zone.bounds[3], -inside_y / 2.0 + run)
        self.assertLess(make_scoop(spec).bounds[1][1], 0.0)
        # the top-label ledge is on the opposite (+Y) wall
        self.assertGreater(top_label_zone(spec).bounds[1], 0.0)

    def test_floor_label_is_kept_out_of_the_scoop_strip(self) -> None:
        spec = BoxSpec(40.0, 40.0, 40.0)
        occupied = [scoop_floor_zone(spec)]
        placed = organizer_app.placed_label_outline(spec, "M8", occupied)
        self.assertFalse(placed.intersects(scoop_floor_zone(spec)))
        # unobstructed it would centre; the scoop pushes it back
        self.assertGreater(
            organizer_app.label_placement(spec, "M8", occupied).y,
            organizer_app.label_placement(spec, "M8").y,
        )

    def test_top_label_and_scoop_export_as_a_strict_multipart_box(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "custom.3mf"
            result = organizer_app.generate_box_file(
                spec, output, "M3", "top", True
            )
            self.assertEqual(result["label"]["position"], "top")
            self.assertEqual(result["customizations"]["scoop"], True)
            self.assertEqual(validate_3mf(output, 2, multipart=("M3",))["warnings"], 0)

    def test_preview_shows_and_reserves_both_customizations(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        geometry = organizer_app.preview_geometry(spec, "M3", (), "fused", "top", True)
        kinds = [kind for _points, kind, _normal, _layer in geometry["geometry"]]
        self.assertIn("top_label_ledge", kinds)
        self.assertIn("scoop", kinds)
        self.assertEqual(
            [name for name, _zone in geometry["customization_zones"]],
            ["top label ledge", "scoop"],
        )

    def test_supports_cannot_collide_with_fixed_customizations(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        zone = organizer_app.Zone(*scoop_floor_zone(spec).bounds)
        support = organizer_app.Feature("pocket", zone)
        with self.assertRaisesRegex(ValueError, "overlaps the scoop"):
            organizer_app.validate_customization_clearance(
                spec, [support], scoop=True
            )

    def test_the_scoop_only_reserves_the_floor_it_actually_lifts(self) -> None:
        # The curve meets the floor tangentially, so its last few millimetres
        # are microns high; reserving them rejected supports that sit flat.
        spec = BoxSpec(40.0, 48.0, 40.0)
        height, run = scoop_dimensions(spec)
        footprint = scoop_floor_zone(spec)
        keep_out = scoop_keep_out(spec)
        self.assertAlmostEqual(keep_out.bounds[1], footprint.bounds[1])
        self.assertLess(keep_out.bounds[3], footprint.bounds[3])
        angle = math.asin((footprint.bounds[3] - keep_out.bounds[3]) / run)
        self.assertAlmostEqual(
            height * (1.0 - math.cos(angle)), SCOOP_FLOOR_TOLERANCE
        )

        def divider(y0: float, y1: float) -> object:
            return organizer_app.Feature(
                "divider", organizer_app.Zone(-8.0, y0, 8.0, y1)
            )

        # a bar across the middle of the bin clears the scoop; 8 mm of it used
        # to be called a collision because the ramp was 0.03 mm proud there
        organizer_app.validate_customization_clearance(
            spec, [divider(-4.0, 4.0)], scoop=True
        )
        self.assertEqual(
            organizer_app.preview_geometry(
                spec, "", [divider(-4.0, 4.0)], "fused", "bottom", True
            )["feature_errors"],
            (),
        )
        with self.assertRaisesRegex(ValueError, "overlaps the scoop"):
            organizer_app.validate_customization_clearance(
                spec, [divider(-18.0, -10.0)], scoop=True
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
            (BoxSpec(48.0, 48.0, 24.0), -8.0),   # whole waves only, see above
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

        top = spec.base_thickness + spec.flat_inside
        for z in (spec.base_thickness + 0.05, spec.base_thickness + 0.5, top - 0.05):
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
            just_under = self._cavity_area_at(spec, mesh, spec.base_thickness + flat - 0.05)
            just_over = self._cavity_area_at(spec, mesh, spec.base_thickness + flat + 0.05)
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


class InsertEditorTests(unittest.TestCase):
    def test_label_moves_clear_of_a_holder_zone(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        occupied = organizer_app.Zone(-8.0, -8.0, 8.0, 8.0).polygon
        placement = organizer_app.label_placement(spec, "M3", [occupied])
        outline = placed_label_outline(spec, "M3", [occupied])
        self.assertNotEqual((placement.x, placement.y), (0.0, 0.0))
        self.assertFalse(outline.intersects(occupied.buffer(TEXT_MARGIN)))

    def test_preview_uses_finished_holder_meshes_not_solid_placeholders(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        feature = organizer_app.default_feature(spec, "bore")
        geometry = organizer_app.preview_geometry(spec, features=[feature])
        faces = [
            points for points, kind, _normal, _layer in geometry["geometry"]
            if kind == "feature_bore"
        ]
        self.assertGreater(len(faces), 5)
        actual = organizer_app.FEATURE_BUILDERS["bore"](spec, feature, spec.base_thickness)[0]
        self.assertAlmostEqual(
            max(point[2] for face in faces for point in face),
            actual.bounds[1][2],
            places=5,
        )

    def test_preview_identifies_the_exact_support_with_invalid_settings(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        invalid = organizer_app.Feature(
            "post", organizer_app.Zone(-8, -8, 8, 8),
            options={"diameter": 30.0},
        )
        geometry = organizer_app.preview_geometry(spec, features=[invalid])
        self.assertEqual(geometry["invalid_feature_indexes"], (0,))
        self.assertTrue(geometry["feature_errors"])
        self.assertIn(
            "feature_invalid",
            [kind for _points, kind, _normal, _layer in geometry["geometry"]],
        )

    def test_every_guided_interior_part_choice_starts_with_valid_geometry(self) -> None:
        spec = BoxSpec(128.0, 88.0, 40.0)
        for kind in organizer_app.INTERIOR_PART_ORDER:
            item = "hex_driver" if kind == "cradle" else "nozzle"
            feature = organizer_app.default_feature(spec, kind, item)
            if kind == "nest":
                self.assertIsNone(feature.contour)
                continue
            geometry = organizer_app.preview_geometry(spec, features=[feature])
            self.assertFalse(geometry["feature_errors"], kind)
            self.assertTrue(
                any(face_kind == f"feature_{kind}"
                    for _points, face_kind, _normal, _layer in geometry["geometry"]),
                kind,
            )

    def test_a_new_cradle_is_a_single_holder(self) -> None:
        # A cradle starts like a post - one lane - so "auto" stays opt-in.
        spec = BoxSpec(64.0, 184.0, 30.0)
        self.assertEqual(organizer_app.default_feature(spec, "cradle").count, 1)

    def test_cradle_quantity_and_direction_all_build_when_there_is_room(self) -> None:
        # Regression: a cradle zone sized to N lanes used to be snapped to the
        # nearest grid line, landing just under what the engine needs, so
        # Quantity 2+ was refused in a bin with room to spare. The editor now
        # rounds every cradle edge up to the grid; mirror that here and confirm
        # the whole Quantity x direction matrix builds.
        spec = BoxSpec(96.0, 200.0, 30.0)
        item = organizer_inserts.Item.simple("Driver", 40.0, 6.0)
        rib = organizer_inserts._cradle_wall(item.widest)
        spacing = 0.0   # default: neighbours share a wall
        base = organizer_app.base_height(spec, "fused")
        inside_x, inside_y = spec.usable_inside
        for count in (1, 2, 3, 5):
            for along in ("x", "y"):
                run_room, across_room = (
                    (inside_x, inside_y) if along == "x" else (inside_y, inside_x)
                )
                run = min(run_room, math.ceil(item.length))
                across = min(
                    across_room,
                    math.ceil(item.widest + rib
                              + (count - 1) * (item.widest + spacing + rib / 2)),
                )
                w, d = (run, across) if along == "x" else (across, run)
                zone = organizer_app.snapped_zone(
                    organizer_app.Zone(-w / 2, -d / 2, w / 2, d / 2), spec, "fused"
                )
                feature = organizer_app.Feature(
                    "cradle", zone, item, count=count, along=along
                )
                built = build_features(spec, [feature], base)
                self.assertTrue(built, (count, along))

    def test_default_cradle_hugs_tool_length_without_ghost_rib_margin(self) -> None:
        spec = BoxSpec(96.0, 96.0, 30.0)
        item = organizer_inserts.Item.simple("Driver", 40.0, 6.0)
        feature = organizer_app.default_feature(spec, "cradle", item=item, along="x")
        self.assertEqual(feature.zone.width, 40.0)

    def test_cradle_part_kind_flags_has_size_false(self) -> None:
        cradle_info = organizer_app.PART_KIND_INFO["cradle"]
        flags = cradle_info[2]
        self.assertFalse(flags["size"])

    def test_cradle_feature_height_ignores_item_clearance(self) -> None:
        spec = BoxSpec(96.0, 96.0, 30.0)
        item = organizer_inserts.Item.simple("Driver", 40.0, 6.0, clearance=2.0)
        feature = organizer_app.default_feature(spec, "cradle", item=item)
        base_z = 0.8
        height = organizer_app._feature_height(spec, feature, base_z)
        expected = base_z + 2.0 + item.widest / 2.0
        self.assertAlmostEqual(height, expected, places=5)

    def test_default_post_adapts_to_a_one_cell_wide_cartridge(self) -> None:
        spec = BoxSpec(16.0, 48.0, 40.0)
        feature = organizer_app.default_feature(spec, "post", mode="cartridge")
        self.assertEqual(feature.zone.width, 8.0)
        self.assertEqual(feature.options["diameter"], 8.0)
        built = build_features(
            spec,
            [feature],
            organizer_app.base_height(spec, "cartridge"),
            organizer_app.layout_zone(spec, "cartridge"),
        )
        self.assertTrue(built)

    def test_switching_to_cartridge_resnaps_existing_supports(self) -> None:
        spec = BoxSpec(64.0, 64.0, 40.0)
        original = organizer_app.Feature("pocket", organizer_app.Zone(-8, -8, 8, 8))
        converted = organizer_app.convert_layout_mode(spec, [original], "cartridge")
        converted.validate(spec)
        self.assertNotEqual(converted.features[0].zone, original.zone)

    def test_saved_design_round_trip_includes_customizations(self) -> None:
        spec = BoxSpec(48.0, 48.0, 35.0, flat_inside=0.5)
        # A bore up in the +Y half, clear of the front-wall scoop strip.
        feature = replace(
            organizer_app.default_feature(spec, "bore"),
            zone=organizer_app.snapped_zone(
                organizer_app.Zone(-8.0, 4.0, 8.0, 20.0), spec, "separate"
            ),
        )
        layout = organizer_app.Layout((feature,), "separate")
        box, rebuilt, label, part_name, location, scoop = organizer_app.design_from_dict(
            organizer_app.design_to_dict(spec, layout, "M3", "Nozzles", "top", True)
        )
        self.assertEqual((box, label, part_name, location), (spec, "M3", "Nozzles", "top"))
        # The retired scoop checkbox reopens as an editable scoop interior part,
        # and the hidden flag is gone.
        self.assertFalse(scoop)
        self.assertEqual([one.kind for one in rebuilt.features], ["bore", "scoop"])
        self.assertEqual(rebuilt.features[0], feature)
        # Saving the migrated design and reopening it is stable.
        again = organizer_app.design_from_dict(
            organizer_app.design_to_dict(spec, rebuilt, label, part_name, location, scoop)
        )
        self.assertEqual(again, (spec, rebuilt, "M3", "Nozzles", "top", False))

    def test_old_saved_design_defaults_to_bottom_label_without_scoop(self) -> None:
        spec = BoxSpec(48.0, 48.0, 35.0)
        data = organizer_app.design_to_dict(spec, organizer_app.Layout())
        data.pop("label_position")
        data.pop("scoop")
        self.assertEqual(
            organizer_app.design_from_dict(data)[4:], ("bottom", False)
        )

    def test_organizer_cli_uses_saved_design_values_unless_overridden(self) -> None:
        spec = BoxSpec(48.0, 32.0, 35.0, flat_inside=0.5)
        layout = organizer_app.Layout(mode="separate")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.wavefinity.json"
            path.write_text(
                organizer_app.json.dumps(
                    organizer_app.design_to_dict(
                        spec, layout, "M3", "Nozzles", "top"
                    )
                ),
                encoding="utf-8",
            )
            args = organizer_app.build_parser().parse_args([
                "organizer", "--layout", str(path), "--z", "50",
                "--output-dir", directory,
            ])
            with mock.patch.object(
                organizer_app, "generate_organizer_files", return_value={}
            ) as generate:
                organizer_app.run_command(args)
            (used_box, used_layout, _, used_label, used_part,
             used_label_location, used_scoop) = generate.call_args.args
            self.assertEqual((used_box.x, used_box.y, used_box.z), (48.0, 32.0, 50.0))
            self.assertEqual(used_layout, layout)
            self.assertEqual((used_label, used_part), ("M3", "Nozzles"))
            self.assertEqual((used_label_location, used_scoop), ("top", False))

    def test_a_floor_label_on_the_command_line_becomes_a_text_part(self) -> None:
        """``--label`` with no position is sugar for a self-placing text part."""
        spec = BoxSpec(48.0, 32.0, 35.0)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.wavefinity.json"
            path.write_text(
                organizer_app.json.dumps(
                    organizer_app.design_to_dict(spec, organizer_app.Layout())
                ),
                encoding="utf-8",
            )
            args = organizer_app.build_parser().parse_args([
                "organizer", "--layout", str(path), "--label", "BOLTS",
                "--output-dir", directory,
            ])
            with mock.patch.object(
                organizer_app, "generate_organizer_files", return_value={}
            ) as generate:
                organizer_app.run_command(args)
            (_box, used_layout, _out, used_label, used_part,
             used_location, _scoop) = generate.call_args.args
            self.assertEqual([one.kind for one in used_layout.features], ["text"])
            said = used_layout.features[0]
            self.assertEqual(said.options["text"], "BOLTS")
            self.assertTrue(said.options["auto"])
            # The rim label stays empty, and the part name is seeded once.
            self.assertEqual((used_label, used_location), ("", "bottom"))
            self.assertEqual(used_part, "BOLTS")

    def test_a_size_like_label_never_seeds_the_part_name(self) -> None:
        for size in ("8", "12mm", " 6.5 mm "):
            self.assertEqual(organizer_app.part_name_seed(size), "")
        for real in ("M3", "BOLTS", "8mm hex"):
            self.assertEqual(organizer_app.part_name_seed(real), real.strip())

    def test_organizer_cli_can_override_saved_customizations(self) -> None:
        spec = BoxSpec(48.0, 32.0, 35.0)
        layout = organizer_app.Layout()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "saved.wavefinity.json"
            path.write_text(
                organizer_app.json.dumps(
                    organizer_app.design_to_dict(
                        spec, layout, "M3", "Nozzles", "top", True
                    )
                ),
                encoding="utf-8",
            )
            args = organizer_app.build_parser().parse_args([
                "organizer", "--layout", str(path), "--label-position", "bottom",
                "--no-scoop", "--output-dir", directory,
            ])
            with mock.patch.object(
                organizer_app, "generate_organizer_files", return_value={}
            ) as generate:
                organizer_app.run_command(args)
            self.assertEqual(generate.call_args.args[-2:], ("bottom", False))

    def test_photo_nest_exports_a_bare_cutter_with_no_bin(self) -> None:
        spec = BoxSpec(96.0, 64.0, 40.0)
        one = organizer_inserts.fitted_nest_feature(
            organizer_app.Feature(
                "nest", organizer_app.Zone(-1, -1, 1, 1),
                options={"clearance": 0.6, "depth": 8.0, "rim": 3.0, "smoothing": 0.0},
                contour=((-30, -12), (30, -12), (28, 12), (-30, 12)),
            )
        )
        layout = organizer_app.Layout((one,), "fused")
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), label="IGNORED", scoop=True
            )
            self.assertEqual(result["mode"], "fused")
            self.assertNotIn("insert", result)
            self.assertNotIn("label", result)
            self.assertEqual(result["customizations"]["scoop"], False)
            files = sorted(Path(directory).glob("*.3mf"))
            self.assertEqual(len(files), 1)
            self.assertEqual(validate_3mf(files[0], 1)["warnings"], 0)
        body = organizer_inserts.union(build_features(spec, [one], 0.0))
        self.assertTrue(body.is_watertight)
        # Stands on the bed and rises only the cutter height - no bin walls.
        self.assertAlmostEqual(float(body.bounds[0][2]), 0.0, places=5)
        self.assertAlmostEqual(float(body.bounds[1][2]), 8.0, places=5)
        # A traced wall, nowhere near the volume of a filled block.
        self.assertLess(
            float(body.volume), one.zone.width * one.zone.depth * 8.0 * 0.5
        )

    def test_separate_export_writes_a_box_and_a_removable_insert(self) -> None:
        spec = BoxSpec(16.0, 24.0, 20.0)
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout(mode="separate"), Path(directory),
                part_name="Test",
            )
            files = sorted(Path(directory).glob("*.3mf"))
            self.assertEqual(
                [path.name for path in files],
                ["Box 16 x 24 x 20 Test.3mf", "Insert 16 x 24 Test.3mf"],
            )
            self.assertEqual(result["mode"], "separate")
            for path in files:
                self.assertEqual(validate_3mf(path, 1)["warnings"], 0)

    def test_separate_top_label_stays_on_box_and_scoop_goes_on_insert(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout(mode="separate"), Path(directory),
                label="M3", label_location="top", scoop=True,
            )
            self.assertEqual(result["label"]["position"], "top")
            self.assertEqual(result["customizations"]["scoop"], True)
            self.assertEqual(
                validate_3mf(Path(result["box"]["output"]), 2, multipart=("M3",))["warnings"],
                0,
            )
            self.assertEqual(
                validate_3mf(Path(result["insert"]["output"]), 1)["warnings"], 0
            )

    def test_failed_removable_text_preflight_leaves_no_partial_box(self) -> None:
        spec = BoxSpec(32.0, 32.0, 40.0)
        too_long = organizer_app.Feature(
            "text", organizer_app.Zone(-12.0, -4.0, 12.0, 4.0),
            options={"text": "THIS LABEL IS MUCH TOO LONG"},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            with self.assertRaisesRegex(ValueError, "will not fit"):
                organizer_app.generate_organizer_files(
                    spec,
                    organizer_app.Layout((too_long,), "separate"),
                    output,
                )
            self.assertFalse(output.exists())

    def test_a_floor_label_reaching_the_exporter_says_to_use_a_text_part(self) -> None:
        """The one place the old bottom-label API could fail silently."""
        spec = BoxSpec(32.0, 32.0, 40.0)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "text.*interior part"):
                organizer_app.generate_organizer_files(
                    spec, organizer_app.Layout(mode="separate"), Path(directory),
                    label="M3", label_location="bottom",
                )

    def test_failed_removable_support_preflight_leaves_no_partial_box(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        invalid = organizer_app.Feature(
            "post", organizer_app.Zone(-8, -8, 8, 8),
            options={"diameter": 30.0},
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            with self.assertRaisesRegex(ValueError, "zone gives"):
                organizer_app.generate_organizer_files(
                    spec, organizer_app.Layout((invalid,), "separate"), output
                )
            self.assertFalse(output.exists())


class InsertFormPreviewTests(unittest.TestCase):
    """The 3D preview has to make fused and removable look different."""

    spec = BoxSpec(80.0, 80.0, 40.0)

    def kinds(self, mode: str) -> dict[str, int]:
        counted: dict[str, int] = {}
        for _points, kind, _normal, _layer in organizer_app.preview_geometry(
            self.spec, "", (), mode
        )["geometry"]:
            counted[kind] = counted.get(kind, 0) + 1
        return counted

    def test_a_removable_insert_draws_a_plate_the_fused_form_has_not(self) -> None:
        self.assertNotIn("insert_base", self.kinds("fused"))
        for mode in ("separate", "cartridge"):
            self.assertGreater(self.kinds(mode).get("insert_base", 0), 0, mode)

    def test_the_plate_in_the_preview_is_the_plate_that_gets_exported(self) -> None:
        # Preview and export must share the fitted plate outline.
        for mode, build in (
            ("separate", make_fitted_insert), ("cartridge", make_cartridge_insert)
        ):
            drawn = organizer_app.insert_plate_solid(self.spec, mode)
            exported = build(self.spec, ())
            for axis in (0, 1):
                # single-precision mesh vertices, so compare to microns
                self.assertAlmostEqual(
                    float(drawn.bounds[0][axis]), float(exported.bounds[0][axis]), 4
                )
                self.assertAlmostEqual(
                    float(drawn.bounds[1][axis]), float(exported.bounds[1][axis]), 4
                )
            if mode == "separate":
                # The removable plate now reaches into the cavity's waves,
                # beyond the conservative straight-sided layout area.
                whole = organizer_app.layout_zone(self.spec, mode)
                self.assertLess(float(drawn.bounds[0][0]), whole.x0)
                self.assertGreater(float(drawn.bounds[1][0]), whole.x1)
            else:
                # A reusable cartridge remains inset from its cell rectangle.
                whole = organizer_app.layout_zone(self.spec, mode)
                self.assertGreater(float(drawn.bounds[0][0]), whole.x0)
                self.assertLess(float(drawn.bounds[1][0]), whole.x1)

    def test_holders_take_the_colour_of_the_part_they_print_as(self) -> None:
        one = organizer_app.default_feature(self.spec, "post")
        for mode, prefix in (("fused", "feature_"), ("separate", "insert_")):
            kinds = {
                kind for _p, kind, _n, _l in organizer_app.preview_geometry(
                    self.spec, "", (one,), mode
                )["geometry"]
            }
            self.assertIn(f"{prefix}post", kinds, mode)


class ResolvedOptionTests(unittest.TestCase):
    """A parameter box that sits blank cannot be seen to change."""

    spec = BoxSpec(80.0, 80.0, 40.0)

    def photo_nest(self, **options):
        values = {"clearance": 0.6, "depth": 8.0, "rim": 3.0, "smoothing": 0.0}
        values.update(options)
        one = organizer_app.Feature(
            "nest", organizer_app.Zone(-1, -1, 1, 1), options=values,
            contour=((-20, -8), (20, -8), (18, 8), (-20, 8)),
        )
        return organizer_inserts.fitted_nest_feature(one)

    def test_every_parameter_of_every_shape_resolves_to_a_number(self) -> None:
        for kind, _title, _blurb, _flags, fields in organizer_app.PART_KINDS:
            one = organizer_app.default_feature(self.spec, kind)
            shown = resolved_options(
                self.spec, one, organizer_app.base_height(self.spec, "fused")
            )
            for _label, option, _default in fields:
                self.assertIn(option, shown, (kind, option))
                self.assertTrue(math.isfinite(shown[option]), (kind, option))

    def test_a_default_still_follows_the_value_it_depends_on(self) -> None:
        # a pocket's recess is "its height less a floor", and setting the
        # height by hand has to keep dragging the recess with it
        one = organizer_app.default_feature(self.spec, "pocket")
        base = organizer_app.base_height(self.spec, "fused")
        self.assertEqual(resolved_options(self.spec, one, base)["depth"], 18.0)
        taller = replace(one, options={"height": 25.0})
        self.assertEqual(resolved_options(self.spec, taller, base)["depth"], 23.0)

    def test_pocket_height_and_rounding_rules(self) -> None:
        base = organizer_app.base_height(self.spec, "fused")
        # 20mm bin: full bin height
        box_20 = BoxSpec(64.0, 64.0, 20.0)
        feat_20 = organizer_app.default_feature(box_20, "pocket")
        self.assertEqual(resolved_options(box_20, feat_20, base)["height"], 20.0)
        self.assertEqual(resolved_options(box_20, feat_20, base)["depth"], 18.0)

        # 40mm bin: 40% is 16mm < 20mm minimum -> 20mm
        box_40 = BoxSpec(64.0, 64.0, 40.0)
        feat_40 = organizer_app.default_feature(box_40, "pocket")
        self.assertEqual(resolved_options(box_40, feat_40, base)["height"], 20.0)

        # 60mm bin: 40% of 60mm = 24mm > 20mm -> 24mm
        box_60 = BoxSpec(64.0, 64.0, 60.0)
        feat_60 = organizer_app.default_feature(box_60, "pocket")
        self.assertEqual(resolved_options(box_60, feat_60, base)["height"], 24.0)
        self.assertEqual(resolved_options(box_60, feat_60, base)["depth"], 22.0)

        # insertion rounding proportional to pocket side
        self.assertAlmostEqual(resolved_options(box_40, feat_40, base)["rounding"], 0.8, places=1)

    def test_the_resolved_numbers_are_the_ones_the_builder_uses(self) -> None:
        one = self.photo_nest()
        base = organizer_app.base_height(self.spec, "fused")
        shown = resolved_options(self.spec, one, base)
        built = build_features(self.spec, [one], base)[0]
        self.assertAlmostEqual(float(built.bounds[1][2]), base + 8.0, 4)
        self.assertEqual(shown["depth"], 8.0)

    def test_changing_a_nest_parameter_changes_the_solid(self) -> None:
        base = organizer_app.base_height(self.spec, "fused")
        shallow = build_features(self.spec, [self.photo_nest(depth=2.0)], base)[0]
        deep = build_features(self.spec, [self.photo_nest(depth=6.0)], base)[0]
        self.assertGreater(float(deep.volume), float(shallow.volume))
        self.assertGreater(float(deep.bounds[1][2]), float(shallow.bounds[1][2]))

    def test_a_refused_parameter_says_which_numbers_disagree(self) -> None:
        one = self.photo_nest(depth=40.0)
        with self.assertRaises(ValueError) as caught:
            build_features(
                self.spec,
                [one],
                organizer_app.base_height(self.spec, "fused"),
            )
        message = str(caught.exception)
        self.assertIn("40", message)
        # The room actually left above the floor, not a hard-coded number -
        # the floor's thickness is its own setting now, separate from the wall.
        headroom = self.spec.z - organizer_app.base_height(self.spec, "fused")
        self.assertIn(f"{headroom:g}", message)


class DividerBottomSlopePaletteTests(unittest.TestCase):
    """The guided-editor palette entry for a divider's sloped bottoms."""

    spec = BoxSpec(80.0, 80.0, 40.0)

    def _divider_fields(self):
        for kind, _title, _blurb, _flags, fields in organizer_app.PART_KINDS:
            if kind == "divider":
                return fields
        self.fail("no divider palette entry")

    def test_lean_is_relabelled_and_bottom_slope_fields_exist(self) -> None:
        fields = self._divider_fields()
        labels = {label for label, _key, _default in fields}
        keys = {key for _label, key, _default in fields}
        self.assertIn("Wall lean °", labels)
        self.assertNotIn("Angle °", labels)
        self.assertIn("bottom_angle", keys)
        self.assertIn("bottom_supports", keys)

    def test_defaults_resolve_to_a_flat_bottom(self) -> None:
        one = organizer_app.default_feature(self.spec, "divider")
        base = organizer_app.base_height(self.spec, "fused")
        shown = resolved_options(self.spec, one, base)
        self.assertEqual(shown["bottom_angle"], 0.0)
        self.assertEqual(shown["reverse_bottom"], 0)
        self.assertEqual(shown["alternate_bottom"], 0)
        self.assertEqual(shown["minimal_bottom"], 0)
        self.assertEqual(shown["bottom_supports"], 3)
        # nothing extra is built at the flat default
        plain = build_features(self.spec, [one], base)
        sloped = build_features(
            self.spec,
            [replace(one, options={"bottom_angle": 0.0})],
            base,
        )
        self.assertEqual(len(plain), len(sloped))

    def test_a_divider_with_bottom_slope_builds_from_the_app_base_height(self) -> None:
        base = organizer_app.base_height(self.spec, "fused")
        one = organizer_app.Feature(
            "divider", organizer_app.Zone(-20.0, -20.0, 20.0, 20.0),
            along="x", count=2,
            options={"bottom_angle": 18.0, "minimal_bottom": True,
                     "bottom_supports": 3},
        )
        built = build_features(self.spec, [one], base)
        self.assertGreater(len(built), 2)  # 2 walls + crossbars
        for solid in built:
            self.assertTrue(solid.is_watertight)

    def test_a_legacy_divider_design_still_loads_and_builds_flat(self) -> None:
        data = {
            "version": 1,
            "box": {"x": 80.0, "y": 80.0, "z": 40.0, "wall": 0.8,
                    "base_thickness": 0.6, "flat_inside": 0.0},
            "mode": "fused",
            "layout": {
                "version": 1, "mode": "fused", "snap": 1.0,
                "features": [{
                    "kind": "divider",
                    "zone": [-20.0, -20.0, 20.0, 20.0],
                    "along": "x", "count": 2, "options": {},
                }],
            },
        }
        box, layout, *_ = organizer_app.design_from_dict(data)
        feature = layout.features[0]
        for key in ("bottom_angle", "reverse_bottom", "alternate_bottom",
                    "minimal_bottom", "bottom_supports"):
            self.assertNotIn(key, feature.options)
        built = build_features(box, list(layout.features), box.base_thickness)
        plain = build_features(
            box,
            [organizer_app.Feature("divider",
                                   organizer_app.Zone(-20.0, -20.0, 20.0, 20.0),
                                   along="x", count=2)],
            box.base_thickness,
        )
        self.assertEqual(len(built), len(plain))


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


class TextExportTests(unittest.TestCase):
    """Any number of text parts, each its own object for its own filament."""

    @staticmethod
    def _text(said, zone, **options):
        return organizer_app.Feature(
            "text", organizer_app.Zone(*zone), options={"text": said, **options}
        )

    def test_several_texts_export_as_one_object_each(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout((
            self._text("M3", (-20.0, 6.0, -2.0, 15.0)),
            self._text("M4", (2.0, 6.0, 20.0, 15.0)),
            self._text("M5", (-20.0, -15.0, -2.0, -6.0), raised=True),
        ), "fused")
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), part_name="Fasteners"
            )
            self.assertEqual(result["text_objects"], ["M3", "M4", "M5"])
            output = Path(result["box"]["output"])
            # The body plus one object per text, strict and warning-free.
            report = validate_3mf(output, 4, multipart=("M3", "M4", "M5"))
            self.assertEqual(report["warnings"], 0)
            self.assertEqual(
                report["names"], ["M3", "M4", "M5", "fused_organizer"]
            )

    def test_a_lettered_file_is_one_assembly_with_the_lettering_on_filament_2(self) -> None:
        """Opens with no multi-part prompt; the two-colour split is preset."""
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout((
            self._text("M3", (-20.0, 6.0, -2.0, 15.0)),
            self._text("M4", (2.0, 6.0, 20.0, 15.0)),
        ), "fused")
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), part_name="Fasteners"
            )
            output = Path(result["box"]["output"])
            report = validate_3mf(output, 3, multipart=("M3", "M4"))
            # One grouping object over the three meshes, a single build item.
            self.assertEqual(report["objects"], 3)
            self.assertEqual(
                report["filaments"],
                {"fused_organizer": 1, "M3": 2, "M4": 2},
            )
            # The sidecar Bambu/Orca reads is actually in the package.
            with zipfile.ZipFile(output) as archive:
                self.assertIn("Metadata/model_settings.config", archive.namelist())

    def test_a_plain_box_stays_a_single_object_with_no_sidecar(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout((), "fused"), Path(directory),
                part_name="Plain",
            )
            output = Path(result["box"]["output"])
            report = validate_3mf(output, 1)
            self.assertNotIn("filaments", report)
            with zipfile.ZipFile(output) as archive:
                self.assertNotIn(
                    "Metadata/model_settings.config", archive.namelist()
                )

    def test_two_texts_reading_the_same_thing_get_distinct_objects(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout((
            self._text("M3", (-20.0, 6.0, -2.0, 15.0)),
            self._text("M3", (2.0, 6.0, 20.0, 15.0)),
        ), "fused")
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), part_name="Twins"
            )
            self.assertEqual(result["text_objects"], ["M3", "M3 2"])
            self.assertEqual(
                validate_3mf(
                    Path(result["box"]["output"]), 3, multipart=("M3", "M3 2")
                )["warnings"],
                0,
            )

    def test_a_sunk_text_and_its_pocket_are_exact_complements(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        one = self._text("M3", (-20.0, 6.0, -2.0, 15.0))
        body = make_box(spec)
        inlay = organizer_inserts.build_text(spec, one, spec.base_thickness)[0]
        pocketed = organizer_inserts.apply_texts(body, [("M3", inlay, False)])
        # Nothing shared but faces, and putting them back gives the plain box.
        self.assertLess(intersection_volume(pocketed, inlay), 0.01)
        self.assertAlmostEqual(
            float(pocketed.volume) + float(inlay.volume),
            float(body.volume), places=3,
        )

    def test_a_raised_text_takes_nothing_out_of_the_body(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        one = self._text("M3", (-20.0, 6.0, -2.0, 15.0), raised=True)
        body = make_box(spec)
        inlay = organizer_inserts.build_text(spec, one, spec.base_thickness)[0]
        self.assertIs(
            organizer_inserts.apply_texts(body, [("M3", inlay, True)]), body
        )

    def test_text_is_inlaid_into_a_removable_insert_plate(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout(
            (self._text("M3", (-20.0, 6.0, -2.0, 15.0)),), "separate"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), part_name="Tray"
            )
            # The lettering rides on the insert, not the bare box.
            self.assertEqual(
                validate_3mf(Path(result["insert"]["output"]), 2, multipart=("M3",))["warnings"],
                0,
            )
            self.assertEqual(validate_3mf(Path(result["box"]["output"]), 1)["warnings"], 0)
            said = result["texts"][0]
            self.assertAlmostEqual(said["surface_z_mm"], organizer_app.BASE_PLATE)

    def test_text_hanging_off_the_insert_plate_is_refused(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        wide, deep = spec.usable_inside
        edge = self._text("M3", (-wide / 2.0, deep / 2.0 - 9.0, 0.0, deep / 2.0))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "hangs over the edge"):
                organizer_app.generate_organizer_files(
                    spec, organizer_app.Layout((edge,), "separate"), Path(directory)
                )

    def test_a_rim_label_and_floor_text_coexist_as_separate_objects(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout(
            (self._text("M3", (-20.0, -15.0, -2.0, -6.0)),), "fused"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), label="BOLTS",
                label_location="top", part_name="Both",
            )
            self.assertEqual(result["text_objects"], ["M3", "BOLTS"])
            self.assertEqual(result["label"]["position"], "top")
            self.assertEqual(
                validate_3mf(
                    Path(result["box"]["output"]), 3, multipart=("M3", "BOLTS")
                )["warnings"],
                0,
            )

    def test_a_design_whose_auto_text_went_stale_still_opens(self) -> None:
        """An auto text's stored zone is a cache; the resolver is the authority."""
        spec = BoxSpec(48.0, 48.0, 40.0)
        post = organizer_app.Feature("post", organizer_app.Zone(-10, -10, 10, 10))
        # Saved sitting right on top of the post - as it would be if a holder
        # were moved onto it and the design saved before the next preview.
        stale = self._text("BOLTS", (-16.0, -6.0, 16.0, 6.0), auto=True)
        saved = organizer_app.design_to_dict(
            spec, organizer_app.Layout((post, stale), "fused")
        )
        _box, layout, *_rest = organizer_app.design_from_dict(
            organizer_app.json.loads(organizer_app.json.dumps(saved))
        )
        moved = layout.features[1]
        self.assertEqual(moved.kind, "text")
        self.assertNotEqual(moved.zone, stale.zone)
        organizer_inserts.check_layout(
            spec, list(layout.features), base_z=spec.base_thickness
        )

    def test_a_hand_placed_overlap_is_still_reported_on_open(self) -> None:
        """Auto-resolution must not paper over a real mistake."""
        spec = BoxSpec(48.0, 48.0, 40.0)
        post = organizer_app.Feature("post", organizer_app.Zone(-10, -10, 10, 10))
        fixed = self._text("M3", (-10.0, -6.0, 10.0, 6.0))
        saved = organizer_app.design_to_dict(
            spec, organizer_app.Layout((post, fixed), "fused")
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            organizer_app.design_from_dict(saved)

    def test_preview_and_export_agree_on_where_an_auto_text_landed(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        features = (
            organizer_app.Feature("post", organizer_app.Zone(-10, -10, 10, 10)),
            self._text("BOLTS", (-16.0, -6.0, 16.0, 6.0), auto=True),
        )
        preview = organizer_app.preview_geometry(spec, features=features)
        zone = preview["features"][1]["zone"]
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout(features, "fused"), Path(directory),
                part_name="Agree",
            )
        said = result["texts"][0]
        self.assertEqual(
            [round((zone[0] + zone[2]) / 2, 3), round((zone[1] + zone[3]) / 2, 3)],
            said["position_mm"],
        )
        self.assertAlmostEqual(
            preview["text_meta"][0]["cap_height"], said["cap_height_mm"], places=6
        )

    def test_the_filename_comes_from_the_part_name_alone(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        self.assertEqual(
            organizer_app.box_filename(spec, "Driver rack"),
            "Box 48 x 48 x 40 Driver rack.3mf",
        )
        self.assertEqual(
            organizer_app.box_filename(spec), "Box 48 x 48 x 40.3mf"
        )
        self.assertEqual(
            organizer_app.insert_filename(spec, "Driver rack"),
            "Insert 48 x 48 Driver rack.3mf",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
