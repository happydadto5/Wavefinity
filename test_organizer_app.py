"""External-behavior regression tests for the organizer generator."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

import numpy as np
import trimesh
from shapely.geometry import Point

import organizer_app
import organizer_b4b
import organizer_edge_mount
import organizer_engine
import organizer_geometry
import organizer_inserts
import organizer_side_openings
from organizer_side_openings import (
    SIDE_OPENING_CORNER_MARGIN_MM,
    SIDE_OPENING_MIN_SIDE_MM,
    SIDE_OPENING_TOP_BRIDGE_MM,
    apply_side_openings,
    side_opening_allowed_sizes,
    validate_side_openings,
)
from organizer_engine import (
    BoxSpec,
    B4BSpec,
    CORNER_INSET,
    ConnectorSpec,
    EdgeMountSpec,
    LidSpec,
    LiftGrabberSpec,
    SideOpeningSpec,
    SIDE_OPENING_WIDTHS,
    StackSpec,
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
    WALL_PRESETS,
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
    make_corner_connector,
    make_wall_lock_bumps,
    measure_lock,
    mesh_fingerprint,
    mesh_report,
    seat_transform,
    translated,
    validate_3mf,
    validate_side_fit,
    validate_corner_fit,
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
    # Re-pinned when the floor's default moved 0.8 -> 0.6 mm, and again (Fix 096
    # B) when it returned to 0.8 mm. Only the floor moved: the connector's
    # fingerprint is byte-identical either side of those changes, which is what
    # says the wave, the mating and the lock were not touched. (The box hash
    # for a 0.6 mm floor is 884CE0CA...; the default 0.8 mm floor is below.)
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
        # _loft_cavity is no longer part of organizer_engine's re-export
        # surface - organizer_stack.py / organizer_base_trim.py now import
        # it straight from organizer_geometry.

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


    def test_scaled_boxes_remain_watertight_and_exact_height(self) -> None:
        for dimensions in ((24.0, 24.0, 40.0), (32.0, 24.0, 45.0), (24.0, 48.0, 30.0)):
            spec = BoxSpec(*dimensions)
            mesh = make_box(spec)
            report = mesh_report(f"box_{dimensions}", mesh)
            self.assertEqual(report["components"], 1)
            self.assertAlmostEqual(mesh.extents[2], dimensions[2], places=5)





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


    def test_corner_connectors_fit_every_wall_preset(self) -> None:
        connector = ConnectorSpec()
        volumes = {}
        cap_volumes = {}
        for wall, _label in WALL_PRESETS:
            box = BoxSpec(24.0, 24.0, 40.0, wall=wall)
            inner, outer = connector_half_widths(box, connector)
            self.assertAlmostEqual(outer - inner, connector.arm_thickness, places=9)
            for ways in (3, 4):
                with self.subTest(wall=wall, ways=ways):
                    mesh = make_corner_connector(box, connector, ways)
                    report = mesh_report(f"{ways}-way wall {wall}", mesh)
                    self.assertTrue(mesh.is_watertight)
                    self.assertEqual(report["components"], 1)
                    self.assertLess(validate_corner_fit(box, connector, mesh, ways), 1e-3)
                    volumes[wall, ways] = mesh.volume
            cap_volumes[wall] = organizer_engine._corner_connector_direction(
                box, connector, "x", 1, include_grip=False
            ).volume
        for ways in (3, 4):
            self.assertNotEqual(
                volumes[WALL_PRESETS[0][0], ways],
                volumes[WALL_PRESETS[-1][0], ways],
            )
        self.assertNotEqual(cap_volumes[WALL_PRESETS[0][0]], cap_volumes[WALL_PRESETS[-1][0]])


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



    def test_one_unit_is_the_same_number_everywhere(self) -> None:
        # the bug this guards: the sampler and the UI once disagreed on what a
        # unit was, so the same "3x3" gave two different boxes.

        self.assertEqual(BoxSpec(48.0, 48.0, 40.0).units, (6, 6))
        self.assertEqual(organizer_app.parse_sizes("6x6"), ((48.0, 48.0),))
        scene = make_sampler_scene()
        self.assertIn("box_6x6_48x48", scene.geometry)




class ExportAndCliTests(unittest.TestCase):


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



    def test_a_long_label_shrinks_before_it_turns(self) -> None:
        # square floor: turning cannot help, so it must shrink and stay flat
        cap, rotated = label_layout(BoxSpec(48.0, 48.0, 40.0), "BOLTS")
        self.assertFalse(rotated)
        self.assertLess(cap, TEXT_CAP_HEIGHT_IDEAL)
        self.assertGreaterEqual(cap, TEXT_CAP_HEIGHT_MIN)



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






class BinCustomizationTests(unittest.TestCase):

    def test_top_label_ledge_and_inlay_are_clean_flush_solids(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        report = top_label_report(spec, "M3")
        ledge = make_top_label_ledge(spec)
        inlay = make_top_label(spec, "M3")
        pocketed, installed = make_top_labelled_box(spec, "M3")
        self.assertTrue(ledge.is_volume)
        # places=3: mesh bounds come from float32 vertices.
        self.assertAlmostEqual(ledge.bounds[0][2], report["ledge_surface_z_mm"] - 7.0, places=3)
        self.assertAlmostEqual(ledge.bounds[1][2], report["ledge_surface_z_mm"], places=3)
        self.assertAlmostEqual(inlay.bounds[1][2], report["ledge_surface_z_mm"], places=3)
        self.assertTrue(pocketed.is_volume)
        self.assertLess(intersection_volume(pocketed, installed), 0.01)

    def test_rim_label_location_can_use_any_wall(self) -> None:
        spec = BoxSpec(64.0, 48.0, 40.0)
        expected_edges = {
            "front": (1, -1), "back": (1, 1),
            "left": (0, -1), "right": (0, 1),
        }
        for side, (axis, sign) in expected_edges.items():
            zone = top_label_zone(spec, side)
            outline = top_label_outline(spec, "M3", side)
            self.assertTrue(zone.covers(outline))
            edge = zone.bounds[axis] if sign < 0 else zone.bounds[axis + 2]
            inside = spec.usable_inside[axis]
            self.assertAlmostEqual(edge, sign * inside / 2.0, places=6)
        self.assertTrue(make_top_label_ledge(spec, "left").is_volume)

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


    def test_supports_cannot_collide_with_fixed_customizations(self) -> None:
        spec = BoxSpec(48.0, 48.0, 40.0)
        zone = organizer_app.Zone(*scoop_floor_zone(spec).bounds)
        support = organizer_app.Feature("pocket", zone)
        with self.assertRaisesRegex(ValueError, "overlaps the scoop"):
            organizer_app.validate_customization_clearance(
                spec, [support], scoop=True
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



    def test_the_band_only_adds_material(self) -> None:
        plain = make_box(BoxSpec(32.0, 32.0, 40.0)).volume
        for flat in (0.5, 1.0):
            filled = make_box(BoxSpec(32.0, 32.0, 40.0, flat_inside=flat))
            self.assertEqual(mesh_report(f"flat_{flat}", filled)["components"], 1)
            self.assertGreater(filled.volume, plain)


    def test_the_outside_and_the_wave_are_untouched(self) -> None:
        plain = wavy_outer_polygon(BoxSpec(32.0, 32.0, 40.0))
        banded = wavy_outer_polygon(BoxSpec(32.0, 32.0, 40.0, flat_inside=1.0))
        self.assertAlmostEqual(plain.area, banded.area, places=6)





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



class InsertEditorTests(unittest.TestCase):
    def test_inside_handles_are_rejected_for_a_removable_insert(self) -> None:
        spec = BoxSpec(
            48.0, 48.0, 40.0,
            lift_grabbers=LiftGrabberSpec(enabled=True, location="sides"),
        )
        with self.assertRaisesRegex(ValueError, "cannot be used with Removable insert"):
            organizer_app.preview_geometry(spec, mode="separate")

    def test_inside_handle_collision_uses_the_parts_actual_height(self) -> None:
        spec = BoxSpec(
            48.0, 48.0, 40.0,
            lift_grabbers=LiftGrabberSpec(enabled=True, location="sides"),
        )
        zone = organizer_app.Zone(18.0, -2.0, 22.0, 2.0)
        low = organizer_app.Feature(
            "post", zone, count=1,
            options={"diameter": 4.0, "height": 10.0, "spacing": 0.0},
        )
        tall = replace(low, options={**low.options, "height": 30.0})
        self.assertIsNone(
            organizer_app.inside_handle_conflict(
                spec, low, spec.base_thickness, "fused"
            )
        )
        self.assertIn(
            "inside handle",
            organizer_app.inside_handle_conflict(
                spec, tall, spec.base_thickness, "fused"
            ),
        )

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
            points for points, kind, _normal, _layer, _owner in geometry["geometry"]
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
            [kind for _points, kind, _normal, _layer, _owner in geometry["geometry"]],
        )

    def test_every_guided_interior_part_choice_starts_with_valid_geometry(self) -> None:
        spec = BoxSpec(128.0, 88.0, 40.0)
        for kind in organizer_app.INTERIOR_PART_ORDER:
            item = "hex_driver" if kind == "cradle" else "nozzle"
            feature = organizer_app.default_feature(spec, kind, item)
            if kind == "nest":
                self.assertIsNone(feature.contour)
                continue
            if kind == "text":
                # A new Text part starts empty by design; it needs wording to build.
                feature = replace(feature, options={**feature.options, "text": "M3"})
            geometry = organizer_app.preview_geometry(spec, features=[feature])
            self.assertFalse(geometry["feature_errors"], kind)
            self.assertTrue(
                any(face_kind == f"feature_{kind}"
                    for _points, face_kind, _normal, _layer, _owner
                    in geometry["geometry"]),
                kind,
            )










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
        # The old one-label fields are migration input: the rim label reopens as
        # one At-rim Text feature on the same wall.
        self.assertEqual((box, label, part_name, location), (spec, "", "Nozzles", "bottom"))
        # The retired scoop checkbox reopens as an editable scoop interior part,
        # and the hidden flag is gone.
        self.assertFalse(scoop)
        self.assertEqual(sorted(one.kind for one in rebuilt.features), ["bore", "scoop", "text"])
        bore = next(one for one in rebuilt.features if one.kind == "bore")
        self.assertEqual((bore.kind, bore.zone), (feature.kind, feature.zone))
        rim = next(one for one in rebuilt.features if one.kind == "text")
        self.assertEqual((rim.options["text"], rim.options["level"], rim.options["rim_side"]),
                         ("M3", "rim", "back"))
        # Saving the migrated design and reopening it is stable.
        again = organizer_app.design_from_dict(
            organizer_app.design_to_dict(spec, rebuilt, label, part_name, location, scoop)
        )
        self.assertEqual(again, (spec, rebuilt, "", "Nozzles", "bottom", False))


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
                organizer_app, "generate_organizer_files_transactional", return_value={}
            ) as generate:
                organizer_app.run_command(args)
            (used_box, used_layout, _, used_label, used_part,
             used_label_location, used_scoop) = generate.call_args.args
            self.assertEqual((used_box.x, used_box.y, used_box.z), (48.0, 32.0, 50.0))
            # The old one-label fields are migration input: the label comes back
            # as one canonical At-rim Text feature on the same wall.
            self.assertEqual([one.kind for one in used_layout.features], ["text"])
            rim = used_layout.features[0]
            self.assertEqual((rim.options["text"], rim.options["level"], rim.options["rim_side"]),
                             ("M3", "rim", "back"))
            self.assertEqual((used_label, used_part), ("", "Nozzles"))
            self.assertEqual((used_label_location, used_scoop), ("bottom", False))





    def test_photo_nest_exports_on_the_bin_floor_or_removable_insert(self) -> None:
        spec = BoxSpec(96.0, 64.0, 40.0)
        one = organizer_inserts.fitted_nest_feature(
            organizer_app.Feature(
                "nest", organizer_app.Zone(-1, -1, 1, 1),
                options={
                    "clearance": 0.6, "depth": 8.0, "rim": 3.0,
                    "smoothing": 0.0, "lift_assist": "finger_grasp",
                },
                contour=((-30, -12), (30, -12), (28, 12), (-30, 12)),
            )
        )
        with tempfile.TemporaryDirectory() as directory:
            fused = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout((one,), "fused"), Path(directory)
            )
            separate = organizer_app.generate_organizer_files(
                spec, organizer_app.Layout((one,), "separate"), Path(directory),
                part_name="Removable Nest",
            )
            self.assertNotIn("insert", fused)
            self.assertIn("insert", separate)
            self.assertEqual(validate_3mf(Path(fused["box"]["output"]), 1)["warnings"], 0)
            self.assertEqual(validate_3mf(Path(separate["box"]["output"]), 1)["warnings"], 0)
            self.assertEqual(validate_3mf(Path(separate["insert"]["output"]), 1)["warnings"], 0)
        body = organizer_inserts.make_fused_box(spec, [one], organizer_app.make_box(spec))
        insert = organizer_inserts.make_fitted_insert(spec, [one])
        self.assertTrue(body.is_watertight)
        self.assertTrue(insert.is_watertight)
        self.assertAlmostEqual(float(body.bounds[0][2]), 0.0, places=5)
        self.assertAlmostEqual(float(body.bounds[1][2]), spec.z, places=5)
        self.assertAlmostEqual(float(insert.bounds[0][2]), 0.0, places=5)
        self.assertGreater(float(insert.volume), float(build_features(
            spec, [one], organizer_app.base_height(spec, "separate"), mode="separate"
        )[0].volume))





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
        for _points, kind, _normal, _layer, _owner in organizer_app.preview_geometry(
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
                kind for _p, kind, _n, _l, _o in organizer_app.preview_geometry(
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

    def test_every_parameter_of_every_shape_resolves_to_its_declared_type(self) -> None:
        for kind, _title, _blurb, _flags, fields in organizer_app.PART_KINDS:
            one = organizer_app.default_feature(self.spec, kind)
            shown = resolved_options(
                self.spec, one, organizer_app.base_height(self.spec, "fused")
            )
            option_types = {
                field.key: field.value_type
                for field in organizer_inserts.feature_definition(kind).options
            }
            for _label, option, _default in fields:
                self.assertIn(option, shown, (kind, option))
                if option_types.get(option) in ("string", "enum"):
                    self.assertIsInstance(shown[option], str, (kind, option))
                    self.assertTrue(shown[option], (kind, option))
                else:
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
        # 20mm bin, fused mode: a fused pocket is now allowed to rise above
        # the bin's rim, so its natural (unclamped) 20mm height is seeded
        # directly rather than being capped by the floor-limited available
        # space.
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
        # A Raised Wall taller than the rim is a legitimate Fused holder now
        # (spec: shallow-fused-above-rim); a Recessed Cavity still genuinely
        # depends on the material actually above the floor in every mode, so
        # it remains the one that reports the disagreeing numbers here.
        one = self.photo_nest(
            holder_style="recessed", cavity_depth_mode="manual",
            tool_thickness=40.0, cavity_depth=40.0,
        )
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
        self.assertNotIn("Wall lean °", labels)
        self.assertIn("Degree °", labels)
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
    """One base and independent rim Text parts export as separate objects."""

    @staticmethod
    def _text(said, zone, **options):
        return organizer_app.Feature(
            "text", organizer_app.Zone(*zone), options={"text": said, **options}
        )

    def test_several_texts_export_as_one_object_each(self) -> None:
        # Fix 078: a design may hold at most one base Text and one rim Text
        # total, so "several" here is the legal maximum of two.
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout((
            self._text("M3", (-20.0, 6.0, -2.0, 15.0)),
            self._text("M4", (2.0, 6.0, 20.0, 15.0), level="rim", rim_side="back", raised=True),
        ), "fused")
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                spec, layout, Path(directory), part_name="Fasteners"
            )
            self.assertEqual(result["text_objects"], ["M3", "M4"])
            output = Path(result["box"]["output"])
            # The body plus one object per text, strict and warning-free.
            report = validate_3mf(output, 3, multipart=("M3", "M4"))
            self.assertEqual(report["warnings"], 0)
            self.assertEqual(
                report["names"], ["M3", "M4", "fused_organizer"]
            )

    def test_a_lettered_file_is_one_assembly_with_the_lettering_on_filament_2(self) -> None:
        """Opens with no multi-part prompt; the two-colour split is preset."""
        spec = BoxSpec(48.0, 48.0, 40.0)
        layout = organizer_app.Layout((
            self._text("M3", (-20.0, 6.0, -2.0, 15.0)),
            self._text("M4", (2.0, 6.0, 20.0, 15.0), level="rim", rim_side="back"),
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
            self.assertEqual(result["texts"][1]["rim_side"], "back")
            self.assertEqual(
                validate_3mf(
                    Path(result["box"]["output"]), 3, multipart=("M3", "BOLTS")
                )["warnings"],
                0,
            )



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



def _wall_midpoint(box: BoxSpec, side: str, z: float) -> tuple[float, float, float]:
    """A point at ``tangent=0`` (a wave zero-crossing), halfway through the
    wall thickness of ``side``, at height ``z``. Inside a solid bin body,
    this is real wall material away from any Side Opening cut."""
    half = box.wall_depth / 2.0
    if side == "front":
        return (0.0, -(box.half_y - half), z)
    if side == "back":
        return (0.0, box.half_y - half, z)
    if side == "left":
        return (-(box.half_x - half), 0.0, z)
    return (box.half_x - half, 0.0, z)


class SideOpeningTests(unittest.TestCase):
    def _box(self, **kwargs) -> BoxSpec:
        defaults = dict(x=40.0, y=40.0, z=40.0)
        defaults.update(kwargs)
        return BoxSpec(**defaults)

    def test_default_off_matches_default_box_fingerprint(self) -> None:
        # Off/default SideOpeningSpec must leave the existing default box
        # fingerprint/geometry completely unchanged.
        self.assertEqual(
            mesh_fingerprint(make_box(BoxSpec())), REFERENCE_FINGERPRINTS["box"]
        )
        self.assertFalse(BoxSpec().side_openings.enabled)

    def test_0_percent_curved_reaches_floor_not_below(self) -> None:
        box = replace(self._box(), side_openings=SideOpeningSpec(
            enabled=True, sides=("front",), shape="curved", size="medium",
            from_bottom_percent=0.0, from_top_percent=0.0,
        ))
        floor_z, rim_z, bottom_z, top_z = organizer_side_openings._vertical_geometry(
            box, box.side_openings.from_bottom_percent,
            box.side_openings.from_top_percent,
        )
        self.assertAlmostEqual(bottom_z, floor_z)
        self.assertAlmostEqual(top_z, rim_z)
        cut = apply_side_openings(box, make_box(box))
        self.assertTrue(cut.is_watertight)
        # The deepest point of the cutter meets the floor top; it must not
        # remove base material below it.
        self.assertGreaterEqual(round(float(cut.bounds[0][2]), 6), 0.0)
        self.assertFalse(bool(cut.contains([_wall_midpoint(box, "front", floor_z + 3.0)])[0]))
        # A point actually inside the base slab, directly under the
        # opening, must still be solid.
        self.assertTrue(bool(cut.contains([(0.0, -box.half_y + 1.0, floor_z / 2.0)])[0]))






    def test_each_side_cuts_only_its_own_wall(self) -> None:
        for side in ("front", "back", "left", "right"):
            with self.subTest(side=side):
                box = replace(self._box(), side_openings=SideOpeningSpec(
                    enabled=True, sides=(side,), shape="curved", size="medium",
                    from_bottom_percent=0.0, from_top_percent=0.0,
                ))
                cut = apply_side_openings(box, make_box(box))
                self.assertTrue(cut.is_watertight)
                probe_z = box.base_thickness + 3.0
                for other in ("front", "back", "left", "right"):
                    contained = bool(cut.contains([_wall_midpoint(box, other, probe_z)])[0])
                    if other == side:
                        self.assertFalse(contained, f"{side} wall was not cut")
                    else:
                        self.assertTrue(contained, f"{other} wall was cut but should not be")

    def test_multiple_sides_and_shapes_stay_one_printable_solid(self) -> None:
        combos = [
            ("curved", 0.0, 0.0), ("square", 0.0, 0.0),
            ("curved", 25.0, 25.0), ("square", 25.0, 25.0),
            ("curved", 50.0, 0.0),
        ]
        for shape, from_bottom, from_top in combos:
            with self.subTest(shape=shape, from_bottom=from_bottom, from_top=from_top):
                box = replace(self._box(z=50.0), side_openings=SideOpeningSpec(
                    enabled=True, sides=("front", "back", "left", "right"),
                    shape=shape, size="medium",
                    from_bottom_percent=from_bottom,
                    from_top_percent=from_top,
                ))
                cut = apply_side_openings(box, make_box(box))
                self.assertTrue(cut.is_watertight)
                self.assertEqual(len(cut.split(only_watertight=False)), 1)



    def test_illegal_combinations_are_rejected(self) -> None:
        box = self._box(z=20.0)
        # A wall shorter than the 2U minimum.
        with self.assertRaises(ValueError):
            validate_side_openings(replace(box, x=8.0, side_openings=SideOpeningSpec(
                enabled=True, sides=("front",),
            )))
        # A width that does not fit the corner shoulders.
        with self.assertRaises(ValueError):
            validate_side_openings(replace(box, x=16.0, side_openings=SideOpeningSpec(
                enabled=True, sides=("front",), size="xl",
            )))
        # Vertically impossible: too shallow a depth for a curved cut of
        # this width.
        with self.assertRaises(ValueError):
            validate_side_openings(replace(box, side_openings=SideOpeningSpec(
                enabled=True, sides=("front",), shape="curved", size="xl",
                from_bottom_percent=1.0, from_top_percent=100.0,
            )))

    def test_percentages_are_bounded_and_must_overlap(self) -> None:
        saved = organizer_app.design_to_dict(self._box(), organizer_app.Layout())
        saved["box"]["side_openings"] = {
            "enabled": True,
            "shape": "square",
            "sides": ["front"],
            "size": "small",
            "from_bottom_percent": -0.5,
            "from_top_percent": 100.0,
        }
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            organizer_app.design_from_dict(saved)
        saved["box"]["side_openings"]["from_bottom_percent"] = 50.0
        saved["box"]["side_openings"]["from_top_percent"] = 50.0
        with self.assertRaisesRegex(ValueError, "top must be above"):
            organizer_app.design_from_dict(saved)


    def _legacy_top_support(self, **box_changes):
        saved = organizer_app.design_to_dict(self._box(), organizer_app.Layout())
        saved["box"].update(box_changes)
        saved["box"]["side_openings"] = {
            "enabled": True, "shape": "square", "sides": ["front"],
            "size": "small", "depth_percent": 60.0, "top_support": True,
        }
        return saved

    def _assert_bridge(self, box) -> None:
        usable = box.z - box.base_thickness
        # Fix 034 H inset_v2: bridge = rim_z - top_z = usable * top_percent/100.
        bridge = usable * (box.side_openings.from_top_percent / 100.0)
        self.assertAlmostEqual(bridge, organizer_app.SIDE_OPENING_TOP_BRIDGE_MM, places=6)





    def test_save_load_round_trips_exactly(self) -> None:
        spec = self._box(x=48.0, y=48.0, z=40.0)
        spec = replace(spec, side_openings=SideOpeningSpec(
            enabled=True, sides=("front", "left"), shape="square",
            size="large", from_bottom_percent=30.0, from_top_percent=20.0,
        ))
        layout = organizer_app.Layout()
        box, rebuilt, label, part_name, location, scoop = organizer_app.design_from_dict(
            organizer_app.design_to_dict(spec, layout)
        )
        self.assertEqual(box, spec)
        self.assertEqual(box.side_openings, spec.side_openings)







    def test_exported_body_retains_cut_after_later_body_operations(self) -> None:
        # A scoop is fused into the shell after make_box() but before the
        # Side Opening cutter is (re)applied - the export must still show
        # the requested opening, not have it filled back in.
        box = self._box(side_openings=SideOpeningSpec(
            enabled=True, sides=("front",), shape="curved", size="medium",
            from_bottom_percent=0.0, from_top_percent=0.0,
        ))
        with tempfile.TemporaryDirectory() as tmp:
            result = organizer_app.generate_organizer_files(
                box, organizer_app.Layout(), Path(tmp), scoop=True,
            )
            out_path = next(Path(tmp).glob("*.3mf"))
            scene = trimesh.load(str(out_path))
            mesh = list(scene.geometry.values())[0]
            self.assertTrue(mesh.is_watertight)
            probe_z = box.base_thickness + 3.0
            self.assertFalse(bool(mesh.contains([_wall_midpoint(box, "front", probe_z)])[0]))
            self.assertTrue(bool(mesh.contains([_wall_midpoint(box, "back", probe_z)])[0]))


class EdgeMountTests(unittest.TestCase):
    def test_screw_cutters_are_closed_volumes(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, edge_mount=EdgeMountSpec(
            side="front", holes_enabled=True, label_enabled=True,
            label_text="A", label_type="separate", standoff_ribs_enabled=False,
        ))
        cutters = [cutter for hole in organizer_edge_mount.edge_mount_hole_plan(box)
                   for cutter in organizer_edge_mount._hole_cutters(box, "front", hole, True)]
        for index, cutter in enumerate(cutters):
            with self.subTest(index=index):
                self.assertTrue(cutter.is_volume, (cutter.bounds, cutter.is_watertight,
                                                   cutter.is_winding_consistent))
        combined = organizer_geometry.union(cutters)
        self.assertTrue(combined.is_volume)
        self.assertTrue(combined.is_watertight)
        self.assertTrue(combined.is_winding_consistent)


    def test_wall_only_bore_screw_cut_preview_and_export(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, edge_mount=EdgeMountSpec(
            side="front", holes_enabled=True, label_enabled=True,
            label_text="A", label_type="separate", standoff_ribs_enabled=False,
        ))
        for style in ("straight", "wavy"):
            one = organizer_app.Feature(
                "bore", organizer_app.Zone(-20.0, -20.0, 20.0, 20.0),
                organizer_inserts.Item.simple("tube", 30.0, 25.0),
                options={"bore_style": f"walls_{style}",
                         "height": 30.0, "wall": 1.6},
            )
            with self.subTest(style=style):
                body = organizer_inserts.build_features(
                    box, [one], organizer_app.base_height(box, "fused"))[0]
                self.assertTrue(body.is_volume, (body.bounds, body.is_watertight,
                                                 body.is_winding_consistent))
                cut = organizer_edge_mount.apply_edge_mount_hole_cuts(box, body)
                self.assertTrue(cut.is_volume)
                self.assertLess(cut.volume, body.volume)
                for kwargs in ({"features": [one]}, {"draft": one}):
                    preview = organizer_app.preview_geometry(box, mode="fused", **kwargs)
                    self.assertFalse(preview["feature_errors"])
                    self.assertIsNone(preview["draft_error"])
                if style == "wavy":
                    import wavefinity_web
                    saved_design = organizer_app.design_to_dict(
                        box, organizer_app.Layout((one,), "fused"))
                    saved = wavefinity_web.preview_payload({"design": saved_design})
                    draft_design = organizer_app.design_to_dict(
                        box, organizer_app.Layout((), "fused"))
                    draft = wavefinity_web.preview_payload({
                        "design": draft_design,
                        "draft": wavefinity_web.feature_to_dict(one),
                    })
                    self.assertFalse(saved["feature_errors"])
                    self.assertIsNone(draft["draft_error"])
                with tempfile.TemporaryDirectory() as directory:
                    result = organizer_app.generate_organizer_files(
                        box, organizer_app.Layout((one,), "fused"), Path(directory))
                    self.assertIn("edge_mount_label", result)
                    self.assertTrue(result["box"]["mesh"]["watertight"])
                    self.assertTrue(result["box"]["mesh"]["positive_volume"])
                    self.assertEqual(validate_3mf(Path(result["box"]["output"]), 1)["warnings"], 0)
                    self.assertEqual(validate_3mf(
                        Path(result["edge_mount_label"]["output"]), 2,
                        multipart=("A",))["warnings"], 0)



    def test_screw_cut_covers_shell_rim_ledge_and_fused_scoop(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, edge_mount=EdgeMountSpec(
            holes_enabled=True, hole_count=1, top_offset_mm=12.7))
        shell = organizer_engine.make_box(box)
        cut_shell = organizer_edge_mount.apply_edge_mount_structure(box, shell)
        self.assertTrue(cut_shell.is_volume)
        self.assertLess(cut_shell.volume, shell.volume)
        scene = organizer_app.preview_geometry(
            box, "M3", (), "fused", "top", True)
        self.assertFalse(scene["feature_errors"])
        kinds = {kind for _points, kind, _normal, _layer, _owner in scene["geometry"]}
        self.assertIn("top_label_ledge", kinds)
        self.assertIn("scoop", kinds)
        with tempfile.TemporaryDirectory() as directory:
            shell_result = organizer_app.generate_organizer_files(
                box, organizer_app.Layout(), Path(directory))
            self.assertEqual(validate_3mf(
                Path(shell_result["box"]["output"]), 1)["warnings"], 0)
            result = organizer_app.generate_organizer_files(
                box, organizer_app.Layout(), Path(directory),
                label="M3", label_location="top", scoop=True)
            self.assertTrue(result["box"]["mesh"]["positive_volume"])


    def test_label_type_migrates_and_separate_clip_is_watertight(self) -> None:
        self.assertEqual(EdgeMountSpec().label_type, "separate")
        box = BoxSpec(48.0, 56.0, 40.0, edge_mount=EdgeMountSpec(label_enabled=True, label_text="TOOLS"))
        saved = organizer_app.design_to_dict(box, organizer_app.Layout())
        self.assertEqual(saved["box"]["edge_mount"]["label_type"], "separate")
        del saved["box"]["edge_mount"]["label_type"]
        loaded, *_ = organizer_app.design_from_dict(saved)
        self.assertEqual(loaded.edge_mount.label_type, "integrated")
        label = organizer_edge_mount.make_edge_mount_label_part(box)
        self.assertTrue(label.is_watertight)
        self.assertEqual(len(label.split()), 1)



    def test_separate_label_is_not_fused_and_exports_separately(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, edge_mount=EdgeMountSpec(
            label_enabled=True, label_text="TOOLS", standoff_ribs_enabled=False,
        ))
        bare = organizer_engine.make_box(box)
        self.assertAlmostEqual(
            organizer_edge_mount.apply_edge_mount_structure(box, bare).volume, bare.volume, places=4
        )
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(box, organizer_app.Layout(), Path(directory))
        self.assertTrue(result["edge_mount_label"]["mesh"]["watertight"])


    def test_separate_label_inner_leg_seats_over_and_catches_the_wall_locks(self) -> None:
        # Fix 061 U1: the outside leg stays 3 mm; the inside leg reaches past
        # the ordinary wall locks, is notched to seat over them without
        # touching, and catches on them when pulled straight up.
        for mode, sides in (("text", ("front", "back", "left", "right")),
                            ("full", ("front", "left"))):
            for side in sides:
                for wall in (0.8, 1.2):
                    label = f"{mode}/{side}/{wall}"
                    box = BoxSpec(
                        48.0, 56.0, 40.0, wall=wall,
                        edge_mount=EdgeMountSpec(
                            side=side, label_enabled=True, label_text="A",
                            label_length_mode=mode,
                        ),
                    )
                    clip = organizer_edge_mount.make_edge_mount_label_part(box)
                    self.assertTrue(clip.is_watertight, label)
                    self.assertEqual(len(clip.split()), 1, label)
                    depth = organizer_edge_mount.edge_mount_inner_leg_depth_mm(box)
                    lock_bottom = organizer_engine.lock_z_levels(box.z)[0]
                    self.assertAlmostEqual(depth, 5.5, places=6, msg=label)
                    self.assertLess(clip.bounds[0][2], lock_bottom, label)
                    self.assertAlmostEqual(clip.bounds[0][2], box.z - depth, places=3, msg=label)

                    # Only the inside leg is deep: below the shallow outer
                    # clip depth nothing lies outside the bin's outer face.
                    ox0, oy0, ox1, oy1 = organizer_engine.wavy_outer_polygon(box).bounds
                    axis, outward_min = {"front": (1, True), "back": (1, False),
                                         "left": (0, True), "right": (0, False)}[side]
                    edge = (oy0, oy1, ox0, ox1)[(0 if outward_min else 1) if axis == 1
                                                else (2 if outward_min else 3)]

                    def outside(z: float) -> bool:
                        segments = trimesh.intersections.mesh_plane(
                            clip, (0.0, 0.0, 1.0), (0.0, 0.0, z))
                        coords = segments.reshape(-1, 3)[:, axis]
                        return bool((coords < edge - 1e-6).any() if outward_min
                                    else (coords > edge + 1e-6).any())

                    self.assertTrue(outside(box.z - 1.5), label)
                    self.assertFalse(outside(box.z - 4.0), label)

                    locks = organizer_geometry.union(organizer_engine.make_wall_lock_bumps(box))
                    self.assertLess(intersection_volume(clip, make_box(box)), 1e-3, label)
                    self.assertLess(intersection_volume(clip, locks), 1e-6, label)
                    raised = clip.copy()
                    raised.apply_translation((0.0, 0.0, 0.3))
                    self.assertGreater(intersection_volume(raised, locks), 1e-3, label)





    def test_driver_access_preserves_legacy_auto_and_rejects_too_small(self) -> None:
        auto = EdgeMountSpec(holes_enabled=True, screw_diameter_mm=5.0)
        self.assertEqual(organizer_edge_mount.resolved_access_diameter(auto), 10.0)
        bad = BoxSpec(
            48.0, 48.0, 40.0,
            edge_mount=replace(auto, access_diameter_mm=4.0),
        )
        with self.assertRaisesRegex(ValueError, "at least the screw diameter"):
            organizer_edge_mount.edge_mount_hole_plan(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
