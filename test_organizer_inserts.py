"""Tests for the in-bin holders."""

from __future__ import annotations

import math
import unittest

import numpy as np
import trimesh

from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    intersection_volume,
    make_box,
    translated,
    wavy_cavity_polygon,
)
import organizer_inserts as inserts
from organizer_inserts import (
    EDITOR_SNAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    build_features,
    check_layout,
    insert_footprint,
    layout_from_dict,
    layout_to_dict,
    make_fitted_insert,
    make_fused_box,
)

BIN = BoxSpec(128.0, 88.0, 40.0)
DRIVER = inserts.LIBRARY["hex_driver"]
ROD = Item.simple("Rod", 60.0, 8.0)
PEN = Item.simple("Pen", 90.0, 12.0)
BIT = Item.simple("Bit", 36.0, 6.0)


PHOTO_CONTOUR = ((-30.0, -10.0), (30.0, -10.0), (30.0, 0.0),
                 (5.0, 0.0), (5.0, 10.0), (-30.0, 10.0))


def photo_nest(**changes) -> Feature:
    options = {"clearance": 0.6, "depth": 8.0, "rim": 3.0}
    options.update(changes.pop("options", {}))
    one = Feature(
        "nest", Zone(-1, -1, 1, 1), options=options,
        contour=changes.pop("contour", PHOTO_CONTOUR), **changes,
    )
    return inserts.fitted_nest_feature(one)


def _cradle_wall(diameter: float) -> float:
    """The trough wall a cradle picks for a tool of this diameter."""
    return min(
        max(diameter * inserts.CRADLE_RIB_FRACTION, inserts.RIB_THICKNESS),
        inserts.CRADLE_RIB_MAX,
    )


# spacing wide enough that a row builds as separate trough bodies, not one
# merged piece - the common driver-rack case the multi-cradle tests check.
SPLIT_SPACING = 4.0


def _cradle_pitch(diameter: float, spacing: float = SPLIT_SPACING) -> float:
    return diameter + _cradle_wall(diameter) / 2.0 + spacing


def _lane_centres(solids, axis: int) -> list[float]:
    """Distinct cross-axis positions of a set of built cradle solids."""
    seen = sorted({round(float(solid.bounds[:, axis].mean()), 3) for solid in solids})
    return seen


def _material_at(solid, x: float, y: float, z0: float, z1: float) -> float:
    """Volume of ``solid`` inside a 1 mm column between two heights."""
    probe = trimesh.creation.box(extents=(1.0, 1.0, z1 - z0))
    probe.apply_translation((x, y, (z0 + z1) / 2.0))
    return intersection_volume(solid, probe)


class ItemTests(unittest.TestCase):
    def test_an_item_measures_itself_end_to_end(self) -> None:
        self.assertEqual(DRIVER.length, 80.0)
        self.assertEqual(DRIVER.widest, 18.0)
        self.assertEqual(len(DRIVER.segments), 2)

    def test_segment_centres_are_midpoints_along_the_object(self) -> None:
        centres = [round(c, 3) for c, _ in DRIVER.segment_centres()]
        self.assertEqual(centres, [25.0, 65.0])       # 50 long, then 30 long

    def test_segment_centres_can_be_measured_from_the_other_end(self) -> None:
        centres = [round(c, 3) for c, _ in DRIVER.segment_centres(True)]
        diameters = [segment.diameter for _, segment in DRIVER.segment_centres(True)]
        self.assertEqual(centres, [15.0, 55.0])
        self.assertEqual(diameters, [18.0, 6.0])

    def test_a_simple_item_is_one_segment(self) -> None:
        stick = Item.simple("Glue", 100.0, 11.0)
        self.assertEqual(len(stick.segments), 1)
        self.assertEqual(stick.length, 100.0)

    def test_bad_items_are_refused(self) -> None:
        with self.assertRaises(ValueError):
            Segment(-1.0, 5.0)
        with self.assertRaises(ValueError):
            Item("nothing", ())
        with self.assertRaisesRegex(ValueError, "profile"):
            Item("odd", (Segment(10.0, 5.0),), profile="triangle")
        with self.assertRaisesRegex(ValueError, "clearance"):
            Item.simple("tight", 10.0, 5.0, clearance=-0.1)
        with self.assertRaisesRegex(ValueError, "finite"):
            Segment(float("nan"), 5.0)

    def test_clearance_is_added_to_the_diameter(self) -> None:
        self.assertAlmostEqual(DRIVER.held(18.0), 18.0 + inserts.ITEM_CLEARANCE)


class ZoneTests(unittest.TestCase):
    def test_the_whole_zone_is_the_usable_rectangle(self) -> None:
        whole = Zone.whole(BIN)
        clear_x, clear_y = BIN.usable_inside
        self.assertAlmostEqual(whole.width, clear_x)
        self.assertAlmostEqual(whole.depth, clear_y)

    def test_an_end_zone_leaves_the_rest_of_the_bin_alone(self) -> None:
        whole = Zone.whole(BIN)
        low = Zone.end(BIN, "x", 88.0, at="low")
        high = Zone.end(BIN, "x", 88.0, at="high")
        self.assertAlmostEqual(low.width, 88.0)
        self.assertAlmostEqual(low.x0, whole.x0)
        self.assertAlmostEqual(high.x1, whole.x1)
        self.assertLess(low.x1, whole.x1)          # something is left over

    def test_a_zone_that_does_not_fit_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not fit"):
            Zone.end(BIN, "x", 500.0)

    def test_overlap_detection(self) -> None:
        first = Zone(0.0, 0.0, 10.0, 10.0)
        self.assertTrue(first.overlaps(Zone(5.0, 5.0, 15.0, 15.0)))
        self.assertFalse(first.overlaps(Zone(10.5, 0.0, 20.0, 10.0)))
        self.assertTrue(first.overlaps(Zone(10.5, 0.0, 20.0, 10.0), gap=0.8))


class CradleTests(unittest.TestCase):
    def _feature(self, span: float = 88.0, item: Item = ROD, count: int | None = 1) -> Feature:
        return Feature("cradle", Zone.end(BIN, "x", span), item, along="x", count=count)

    def test_a_cradle_is_one_continuous_trough_the_length_of_the_tool(self) -> None:
        solids = build_features(BIN, [self._feature()], BIN.wall)
        self.assertEqual(len(solids), 1)                 # one body, not two ribs
        trough = solids[0]
        self.assertTrue(trough.is_watertight)
        run = trough.bounds[1][0] - trough.bounds[0][0]
        self.assertAlmostEqual(run, ROD.length, places=3)  # spans the whole tool
        centre = self._feature().zone.centre[0]
        self.assertAlmostEqual(float(trough.bounds[:, 0].mean()), centre, places=3)

    def test_the_trough_sits_on_the_floor_with_a_level_top(self) -> None:
        trough = build_features(BIN, [self._feature()], BIN.wall)[0]
        self.assertAlmostEqual(trough.bounds[0][2], BIN.wall, places=6)
        axis_z = BIN.wall + inserts.CRADLE_FLOOR_GAP + ROD.widest / 2.0
        self.assertAlmostEqual(trough.bounds[1][2], axis_z, places=6)  # rests level

    def test_a_short_tool_still_gets_one_full_length_trough(self) -> None:
        stub = Item.simple("Stub", 3.0, 6.0)
        solids = build_features(
            BIN,
            [Feature("cradle", Zone(-20.0, -20.0, 20.0, 20.0), stub, count=1)],
            BIN.wall,
        )
        self.assertEqual(len(solids), 1)
        self.assertAlmostEqual(float(solids[0].bounds[:, 0].mean()), 0.0, places=3)
        run = solids[0].bounds[1][0] - solids[0].bounds[0][0]
        self.assertAlmostEqual(run, stub.length, places=3)

    def test_the_channel_mouth_sits_on_the_top_face_so_a_tool_can_drop_in(self) -> None:
        # any lower and the opening would be narrower than the tool
        trough = build_features(BIN, [self._feature()], BIN.wall)[0]
        axis_z = BIN.wall + inserts.CRADLE_FLOOR_GAP + ROD.widest / 2.0
        self.assertAlmostEqual(trough.bounds[1][2], axis_z, places=6)

    def test_a_cradle_ignores_fit_clearance(self) -> None:
        # A cradle is an open channel the tool drops into - no fit slack - so
        # the tool's stated clearance changes nothing about the trough.
        loose = Item.simple("Loose", 60.0, 8.0, clearance=2.0)
        snug = build_features(BIN, [self._feature(item=ROD)], BIN.wall)[0]
        wide = build_features(BIN, [self._feature(item=loose)], BIN.wall)[0]
        np.testing.assert_allclose(wide.bounds, snug.bounds, atol=1e-6)

    def test_a_multi_segment_item_is_held_as_one_plain_cylinder(self) -> None:
        solids = build_features(BIN, [self._feature(span=124.0, item=DRIVER)], BIN.wall)
        self.assertEqual(len(solids), 1)   # one trough, not one per segment
        axis_z = BIN.wall + inserts.CRADLE_FLOOR_GAP + DRIVER.widest / 2.0
        self.assertAlmostEqual(solids[0].bounds[1][2], axis_z, places=6)  # widest dia

    def test_an_explicit_count_that_will_not_fit_is_refused(self) -> None:
        crowded = Feature("cradle", Zone.end(BIN, "x", 88.0), ROD, count=40)
        with self.assertRaisesRegex(ValueError, "across"):
            build_features(BIN, [crowded], BIN.wall)

    def test_an_item_longer_than_its_zone_is_refused(self) -> None:
        cramped = Feature("cradle", Zone.end(BIN, "x", 40.0), PEN)
        with self.assertRaisesRegex(ValueError, "long"):
            build_features(BIN, [cramped], BIN.wall)

    def test_a_subminimum_floor_gap_that_leaves_unprintable_material_below_is_refused(self) -> None:
        for bad_gap in (-1.0, 0.0, 0.1, 0.35):
            buried = Feature(
                "cradle", Zone.end(BIN, "x", 88.0), ROD, options={"floor_gap": bad_gap}
            )
            with self.assertRaisesRegex(ValueError, "clearance under it"):
                build_features(BIN, [buried], BIN.wall)
        valid = Feature(
            "cradle", Zone.end(BIN, "x", 88.0), ROD, options={"floor_gap": inserts.CRADLE_MIN_FLOOR_GAP}
        )
        solids = build_features(BIN, [valid], BIN.wall)
        self.assertTrue(solids[0].is_watertight)

    def test_alternate_ends_places_troughs_near_opposite_run_ends(self) -> None:
        one = Feature(
            "cradle", Zone.end(BIN, "x", 124.0), ROD,
            count=4, along="x", alternate_ends=True,
        )
        troughs = build_features(BIN, [one], BIN.wall)
        self.assertEqual(len(troughs), 4)           # one body per tool
        self.assertTrue(all(t.is_watertight for t in troughs))
        centre_along = one.zone.centre[0]
        mids = [
            float(t.bounds[:, 0].mean()) - centre_along
            for t in sorted(troughs, key=lambda t: t.bounds[:, 1].mean())
        ]
        # Trough ends sit 10% in from each end of the run, not around its middle.
        run = one.zone.width
        margin = inserts.CRADLE_ALTERNATE_END_MARGIN * run
        self.assertAlmostEqual(mids[0] - ROD.length / 2.0, -run / 2.0 + margin, places=3)
        self.assertAlmostEqual(mids[1] + ROD.length / 2.0, run / 2.0 - margin, places=3)
        self.assertAlmostEqual(mids[0], mids[2], places=3)
        self.assertAlmostEqual(mids[1], mids[3], places=3)
        self.assertAlmostEqual(mids[1] - mids[0], run * 0.8 - ROD.length, places=3)

    def test_alternate_ends_needs_room_for_end_clearance(self) -> None:
        snug = Feature(
            "cradle", Zone.end(BIN, "x", 70.0), ROD, count=4, alternate_ends=True
        )
        self.assertEqual(inserts.cradle_min_footprint(snug)[0], 75.0)
        with self.assertRaisesRegex(ValueError, "end clearance"):
            build_features(BIN, [snug], BIN.wall)

    def test_alternate_ends_does_not_change_a_single_cradle(self) -> None:
        plain = Feature("cradle", Zone.end(BIN, "x", 88.0), ROD, count=1)
        alternate = Feature(
            "cradle", plain.zone, ROD, count=1, alternate_ends=True,
        )
        for expected, actual in zip(
            build_features(BIN, [plain], BIN.wall),
            build_features(BIN, [alternate], BIN.wall),
            strict=True,
        ):
            np.testing.assert_allclose(actual.bounds, expected.bounds, atol=1e-6)


class BuildTests(unittest.TestCase):
    def _feature(self) -> Feature:
        return Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER, along="x")

    def test_a_fused_box_is_one_watertight_solid(self) -> None:
        fused = make_fused_box(BIN, [self._feature()], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_fusing_only_adds_material(self) -> None:
        plain = make_box(BIN)
        fused = make_fused_box(BIN, [self._feature()], plain)
        self.assertGreater(fused.volume, plain.volume)

    def test_no_features_leaves_the_box_alone(self) -> None:
        plain = make_box(BIN)
        self.assertIs(make_fused_box(BIN, [], plain), plain)

    def test_alternating_cradles_assemble_into_valid_fused_and_removable_parts(self) -> None:
        one = Feature(
            "cradle", Zone.end(BIN, "x", 124.0), DRIVER,
            count=3, alternate_ends=True,
        )
        fused = make_fused_box(BIN, [one], make_box(BIN))
        fitted = make_fitted_insert(BIN, [one])
        for part in (fused, fitted):
            self.assertTrue(part.is_watertight)
            self.assertEqual(len(part.split(only_watertight=False)), 1)

    def test_a_standalone_insert_clears_the_bin_walls(self) -> None:
        insert = make_fitted_insert(BIN, [self._feature()])
        self.assertTrue(insert.is_watertight)
        footprint = insert_footprint(BIN, "separate")
        expected = inserts.wavy_cavity_polygon(BIN).buffer(-inserts.INSERT_CLEARANCE)
        self.assertLess(footprint.hausdorff_distance(expected), 1e-6)
        # Following the waves covers more floor than the former safe rectangle.
        clear_x, clear_y = BIN.usable_inside
        old_rectangle_area = (
            clear_x - 2.0 * inserts.INSERT_CLEARANCE
        ) * (clear_y - 2.0 * inserts.INSERT_CLEARANCE)
        self.assertGreater(footprint.area, old_rectangle_area)
        # it is built standing on z=0 so it prints flat on the bed; dropped
        # onto the bin floor it clears the box entirely
        seated = translated(insert, (0.0, 0.0, BIN.wall))
        self.assertLess(intersection_volume(seated, make_box(BIN)), 0.01)

    def test_a_standalone_insert_stands_on_its_own_plate(self) -> None:
        insert = make_fitted_insert(BIN, [self._feature()])
        self.assertAlmostEqual(insert.bounds[0][2], 0.0, places=6)


class MultipleCradleTests(unittest.TestCase):
    """A row of cradles side by side - the common case for a driver rack."""

    def _row(self, count=None, item=ROD, along="x", alternate=False, span=124.0,
             spacing=SPLIT_SPACING):
        zone = (Zone.end(BIN, "x", span) if along == "x"
                else Zone.end(BIN, "y", min(span, 85.0)))
        return Feature("cradle", zone, item, count=count, along=along,
                       alternate_ends=alternate, options={"spacing": spacing})

    def test_a_row_of_lanes_is_evenly_pitched(self) -> None:
        ribs = build_features(BIN, [self._row(count=5, alternate=True)], BIN.wall)
        centres = _lane_centres(ribs, 1)
        self.assertEqual(len(centres), 5)
        gaps = np.diff(centres)
        np.testing.assert_allclose(gaps, gaps[0], atol=1e-6)
        self.assertAlmostEqual(float(gaps[0]), _cradle_pitch(ROD.widest), places=6)

    def test_the_row_is_centred_across_the_zone(self) -> None:
        ribs = build_features(BIN, [self._row(count=4, alternate=True)], BIN.wall)
        centres = _lane_centres(ribs, 1)
        self.assertAlmostEqual((centres[0] + centres[-1]) / 2.0, 0.0, places=6)

    def test_every_lane_holds_the_tool_at_the_same_height(self) -> None:
        ribs = build_features(BIN, [self._row(count=5, alternate=True)], BIN.wall)
        tops = {round(float(r.bounds[1][2]), 6) for r in ribs}
        floors = {round(float(r.bounds[0][2]), 6) for r in ribs}
        self.assertEqual(len(tops), 1)
        self.assertEqual(len(floors), 1)

    def test_auto_count_fills_the_zone_without_overrunning_it(self) -> None:
        one = self._row(count=None)
        troughs = build_features(BIN, [one], BIN.wall)
        across = one.zone.depth
        span = (max(t.bounds[1][1] for t in troughs)
                - min(t.bounds[0][1] for t in troughs))
        self.assertLessEqual(span, across + 1e-3)
        # one more trough than auto chose would not have fit
        crowded = self._row(count=len(troughs) + 1)
        with self.assertRaises(ValueError):
            build_features(BIN, [crowded], BIN.wall)

    def test_more_lanes_place_more_troughs(self) -> None:
        two = build_features(BIN, [self._row(count=2)], BIN.wall)
        five = build_features(BIN, [self._row(count=5)], BIN.wall)
        self.assertEqual(len(two), 2)
        self.assertEqual(len(five), 5)
        self.assertGreater(sum(t.volume for t in five), sum(t.volume for t in two))

    def test_neighbouring_troughs_have_clear_air_between_them(self) -> None:
        troughs = sorted(
            build_features(BIN, [self._row(count=2)], BIN.wall),
            key=lambda t: t.bounds[:, 1].mean(),
        )
        axis_z = BIN.wall + inserts.CRADLE_FLOOR_GAP + ROD.widest / 2.0
        x = float(troughs[0].bounds[:, 0].mean())
        seat_a = float(troughs[0].bounds[:, 1].mean())
        seat_b = float(troughs[1].bounds[:, 1].mean())
        wall_of_a = _material_at(troughs[0], x, seat_a - ROD.widest / 2.0 - 0.4,
                                 axis_z - 2.0, axis_z - 0.1)
        gap = _material_at(troughs[0], x, (seat_a + seat_b) / 2.0,
                           axis_z - 2.0, axis_z - 0.1)
        self.assertGreater(wall_of_a, gap)     # a solid wall beside the channel
        self.assertLess(gap, 0.05)             # nothing but air between troughs

    def test_along_y_puts_the_lanes_across_x(self) -> None:
        x_ribs = build_features(
            BIN, [self._row(count=4, along="x", alternate=True, item=BIT)], BIN.wall
        )
        y_ribs = build_features(
            BIN, [self._row(count=4, along="y", alternate=True, span=80.0, item=BIT)],
            BIN.wall,
        )
        # a row's lanes sit on its cross axis: exactly `count` evenly spaced seats
        self.assertEqual(len(_lane_centres(x_ribs, 1)), 4)   # x-row lanes across y
        self.assertEqual(len(_lane_centres(y_ribs, 0)), 4)   # y-row lanes across x
        for ribs, axis in ((x_ribs, 1), (y_ribs, 0)):
            gaps = np.diff(_lane_centres(ribs, axis))
            np.testing.assert_allclose(gaps, gaps[0], atol=1e-6)

    def test_a_single_lane_matches_an_explicit_count_of_one(self) -> None:
        auto = build_features(
            BIN, [Feature("cradle", Zone(-40, -6, 40, 6), ROD)], BIN.wall
        )
        one = build_features(
            BIN, [Feature("cradle", Zone(-40, -6, 40, 6), ROD, count=1)], BIN.wall
        )
        for a, b in zip(auto, one, strict=True):
            np.testing.assert_allclose(a.bounds, b.bounds, atol=1e-6)

    def test_a_fatter_tool_fits_fewer_lanes(self) -> None:
        thin = build_features(
            BIN, [self._row(count=None, item=ROD, spacing=8.0)], BIN.wall
        )
        fat = build_features(
            BIN,
            [self._row(count=None, item=Item.simple("Fat", 60.0, 20.0), spacing=8.0)],
            BIN.wall,
        )
        self.assertLess(len(fat), len(thin))   # one solid per lane at this spacing

    def test_each_trough_of_a_row_is_its_own_watertight_solid(self) -> None:
        for alternate in (False, True):
            troughs = build_features(
                BIN, [self._row(count=6, alternate=alternate)], BIN.wall
            )
            self.assertEqual(len(troughs), 6, alternate)
            for trough in troughs:
                self.assertTrue(trough.is_watertight)
                self.assertEqual(len(trough.split(only_watertight=False)), 1)

    def test_spacing_zero_joins_the_row_into_one_shared_body(self) -> None:
        # Facing side walls fully overlap: the middle joint is only as thick
        # as one exposed side, not the double-thick joint that abutting blocks
        # would create.
        solids = build_features(BIN, [self._row(count=5, spacing=0.0)], BIN.wall)
        self.assertEqual(len(solids), 1)
        self.assertTrue(solids[0].is_watertight)
        self.assertEqual(len(solids[0].split(only_watertight=False)), 1)
        wall = _cradle_wall(ROD.widest)
        expected = 5 * ROD.widest + 6 * wall / 2.0
        self.assertAlmostEqual(
            float(solids[0].bounds[1][1] - solids[0].bounds[0][1]), expected, places=6
        )

    def test_raising_spacing_past_a_side_wall_splits_the_row(self) -> None:
        side_wall = _cradle_wall(ROD.widest) / 2.0
        merged = build_features(BIN, [self._row(count=4, spacing=side_wall)], BIN.wall)
        split = build_features(BIN, [self._row(count=4, spacing=side_wall + 2.0)], BIN.wall)
        self.assertEqual(len(merged), 1)          # side walls still touch
        self.assertEqual(len(split), 4)           # beyond that, clear air
        gap = _lane_centres(split, 1)
        self.assertAlmostEqual(
            float(np.diff(gap)[0]), _cradle_pitch(ROD.widest, side_wall + 2.0), places=6
        )

    def test_a_fused_row_of_many_cradles_is_one_solid(self) -> None:
        fused = make_fused_box(BIN, [self._row(count=5)], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_a_removable_row_of_many_cradles_stands_on_one_plate(self) -> None:
        insert = make_fitted_insert(BIN, [self._row(count=5)])
        self.assertTrue(insert.is_watertight)
        self.assertAlmostEqual(insert.bounds[0][2], 0.0, places=6)
        self.assertEqual(len(insert.split(only_watertight=False)), 1)

    def test_an_alternating_removable_row_is_also_one_solid(self) -> None:
        insert = make_fitted_insert(BIN, [self._row(count=5, alternate=True)])
        self.assertTrue(insert.is_watertight)
        self.assertEqual(len(insert.split(only_watertight=False)), 1)

    def test_two_separate_cradle_groups_in_one_bin(self) -> None:
        left = Feature("cradle", Zone(-60.0, -40.0, -6.0, 40.0), BIT, along="x")
        right = Feature("cradle", Zone(6.0, -40.0, 60.0, 40.0), BIT, along="x", count=4)
        check_layout(BIN, [left, right])
        fused = make_fused_box(BIN, [left, right], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_a_crowded_explicit_count_names_the_across_dimension(self) -> None:
        crowded = self._row(count=40)
        with self.assertRaisesRegex(ValueError, "across"):
            build_features(BIN, [crowded], BIN.wall)


class CradleAndDividerLayoutTests(unittest.TestCase):
    """Cradles and dividers sharing one bin - placement and assembly."""

    def test_a_divider_between_two_cradle_groups_is_accepted(self) -> None:
        left = Feature("cradle", Zone(-60.0, -40.0, -12.0, 40.0), BIT)
        wall = Feature("divider", Zone(-6.0, -40.0, 6.0, 40.0), along="y")
        right = Feature("cradle", Zone(12.0, -40.0, 60.0, 40.0), BIT)
        check_layout(BIN, [left, wall, right])
        fused = make_fused_box(BIN, [left, wall, right], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_a_cradle_overlapping_a_divider_is_refused(self) -> None:
        cradle = Feature("cradle", Zone(-40.0, -20.0, 20.0, 20.0), BIT)
        wall = Feature("divider", Zone(10.0, -20.0, 40.0, 20.0), along="y")
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(BIN, [cradle, wall])

    def test_a_removable_insert_carries_cradles_and_a_divider(self) -> None:
        cradle = Feature("cradle", Zone(-58.0, -40.0, -6.0, 40.0), BIT, count=3)
        wall = Feature("divider", Zone(6.0, -40.0, 58.0, 40.0), along="x", count=2)
        insert = make_fitted_insert(BIN, [cradle, wall])
        self.assertTrue(insert.is_watertight)
        self.assertAlmostEqual(insert.bounds[0][2], 0.0, places=6)
        self.assertEqual(len(insert.split(only_watertight=False)), 1)

    def test_a_full_span_divider_beside_a_cradle_row(self) -> None:
        box = BoxSpec(96.0, 96.0, 40.0)
        whole = Zone.whole(box)
        cradle = Feature(
            "cradle", Zone(whole.x0, -30.0, whole.x0 + 70.0, 30.0), BIT, count=3
        )
        wall = Feature(
            "divider", Zone(whole.x1 - 12.0, whole.y0, whole.x1, whole.y1),
            along="y", full_span=True,
        )
        fused = make_fused_box(box, [cradle, wall], make_box(box))
        self.assertTrue(fused.is_watertight)

    def test_a_mixed_cradle_and_divider_layout_round_trips_through_json(self) -> None:
        layout = Layout((
            Feature("cradle", Zone(-58.0, -40.0, -6.0, 40.0), BIT, count=3,
                    alternate_ends=True),
            Feature("divider", Zone(6.0, -40.0, 58.0, 40.0), along="x", count=2),
        ), "separate")
        rebuilt = layout_from_dict(layout_to_dict(layout))
        self.assertEqual(rebuilt, layout)


class LayoutCheckTests(unittest.TestCase):
    def test_a_feature_reaching_outside_the_bin_is_refused(self) -> None:
        outside = Feature("cradle", Zone(-200.0, -20.0, -100.0, 20.0), DRIVER)
        with self.assertRaisesRegex(ValueError, "outside the bin"):
            check_layout(BIN, [outside])

    def test_overlapping_features_are_refused(self) -> None:
        cradle = Feature("cradle", Zone(-60.0, -20.0, 28.0, 20.0), DRIVER)
        wall = Feature("divider", Zone(0.0, -20.0, 40.0, 20.0))
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(BIN, [cradle, wall])

    def test_separated_features_are_allowed(self) -> None:
        cradle = Feature("cradle", Zone(-60.0, -20.0, 20.0, 20.0), DRIVER)
        wall = Feature("divider", Zone(24.0, -20.0, 40.0, 20.0))
        check_layout(BIN, [cradle, wall])

    def test_shallow_overlap_and_subminimum_gap_are_refused(self) -> None:
        first = Feature("pocket", Zone(-20.0, -10.0, -10.0, 10.0))
        overlap = Feature("pocket", Zone(-10.5, -10.0, -0.5, 10.0))
        too_close = Feature("pocket", Zone(-9.5, -10.0, 0.5, 10.0))
        for second in (overlap, too_close):
            with self.assertRaisesRegex(ValueError, "leave at least"):
                check_layout(BIN, [first, second])

    def test_an_unknown_holder_names_the_ones_that_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown holder"):
            check_layout(BIN, [Feature("teleporter", Zone.whole(BIN))])


class FullSpanDividerTests(unittest.TestCase):
    """A divider that hugs the box's true wavy wall, not the safe rectangle."""

    def test_only_a_divider_may_span_the_full_wall(self) -> None:
        with self.assertRaisesRegex(ValueError, "only a divider"):
            Feature("post", Zone(-5.0, -5.0, 5.0, 5.0), full_span=True)

    def test_the_edge_touches_the_true_wall_everywhere_along_its_thickness(self) -> None:
        # Not just at the centreline: the wave shifts the wall as a function
        # of position, so a straight-sided rib sized to the safe rectangle
        # leaves a gap at most points along its own thickness. Slice the
        # actual built solid at several points across the band and demand
        # its true cross-section matches the wall's, not just its bounding box.
        import numpy as np
        from shapely.geometry import LineString
        from trimesh.intersections import mesh_plane

        box = BoxSpec(40.0, 48.0, 40.0)
        cavity = wavy_cavity_polygon(box)
        thickness = 1.6
        whole = Zone.whole(box)
        for cy in (0.0, 3.0, -7.0):
            zone = Zone(whole.x0, cy - thickness / 2.0, whole.x1, cy + thickness / 2.0)
            one = Feature("divider", zone, along="x", full_span=True)
            solid = build_features(box, [one], box.wall)[0]
            self.assertTrue(solid.is_watertight)
            for y in np.linspace(
                cy - thickness / 2.0 + 1e-6, cy + thickness / 2.0 - 1e-6, 9
            ):
                lines = mesh_plane(
                    solid, plane_normal=np.array([0.0, 1.0, 0.0]),
                    plane_origin=np.array([0.0, y, 0.0]),
                )
                built_xs = lines[:, :, 0].ravel()
                probe = LineString([(-30.0, y), (30.0, y)])
                true_xs = [point[0] for point in probe.intersection(cavity).coords]
                self.assertAlmostEqual(
                    float(built_xs.min()), min(true_xs), places=3, msg=(cy, y, "left")
                )
                self.assertAlmostEqual(
                    float(built_xs.max()), max(true_xs), places=3, msg=(cy, y, "right")
                )

    def test_a_full_span_divider_reaches_further_than_the_safe_rectangle(self) -> None:
        # This is the point of the feature: it should not be equivalent to
        # the plain, conservative full-width sizing.
        box = BoxSpec(40.0, 48.0, 40.0)
        whole = Zone.whole(box)
        zone = Zone(whole.x0, -0.8, whole.x1, 0.8)
        plain = build_features(
            box, [Feature("divider", zone, along="x")], box.wall
        )[0]
        full = build_features(
            box, [Feature("divider", zone, along="x", full_span=True)], box.wall
        )[0]
        self.assertGreater(full.bounds[1][0] - full.bounds[0][0],
                            plain.bounds[1][0] - plain.bounds[0][0])

    def test_flat_inside_gives_two_stacked_pieces_that_meet_at_the_seam(self) -> None:
        box = BoxSpec(40.0, 48.0, 40.0, flat_inside=0.6)
        whole = Zone.whole(box)
        zone = Zone(whole.x0, -0.8, whole.x1, 0.8)
        pieces = build_features(
            box, [Feature("divider", zone, along="x", full_span=True,
                           options={"height": 20.0})],
            box.wall,
        )
        self.assertEqual(len(pieces), 2)
        flat, wavy = sorted(pieces, key=lambda solid: solid.bounds[0][2])
        self.assertAlmostEqual(flat.bounds[0][2], box.wall, places=6)
        self.assertAlmostEqual(flat.bounds[1][2], box.wall + box.flat_inside, places=6)
        self.assertAlmostEqual(wavy.bounds[0][2], flat.bounds[1][2], places=6)
        for solid in pieces:
            self.assertTrue(solid.is_watertight)

    def test_inside_a_removable_insert_it_clips_flush_to_the_wavy_plate_edge(
        self,
    ) -> None:
        # A full-span divider meets the removable plate's fitted wavy edge.
        box = BoxSpec(40.0, 48.0, 40.0)
        whole = Zone.whole(box)
        zone = Zone(whole.x0, -0.8, whole.x1, 0.8)
        insert = make_fitted_insert(
            box, [Feature("divider", zone, along="x", full_span=True)]
        )
        footprint = insert_footprint(box, "separate")
        self.assertAlmostEqual(
            insert.bounds[1][0], footprint.bounds[2], places=3
        )
        self.assertAlmostEqual(
            insert.bounds[0][0], footprint.bounds[0], places=3
        )

    def test_flat_lower_wall_band_uses_its_actual_straight_profile(self) -> None:
        box = BoxSpec(40.0, 48.0, 40.0, flat_inside=0.6)
        footprint = insert_footprint(box, "separate")
        expected = inserts.flat_cavity_polygon(box).buffer(-inserts.INSERT_CLEARANCE)
        self.assertLess(footprint.hausdorff_distance(expected), 1e-6)
        seated = translated(make_fitted_insert(box, []), (0.0, 0.0, box.wall))
        self.assertLess(intersection_volume(seated, make_box(box)), 0.01)

    def test_full_span_round_trips_through_the_saved_design_schema(self) -> None:
        box = BoxSpec(40.0, 48.0, 40.0)
        whole = Zone.whole(box)
        zone = Zone(whole.x0, -0.8, whole.x1, 0.8)
        layout = Layout(
            (Feature("divider", zone, along="x", full_span=True),),
            "fused", EDITOR_SNAP,
        )
        data = layout_to_dict(layout)
        self.assertTrue(data["features"][0]["full_span"])
        restored = layout_from_dict(data)
        self.assertTrue(restored.features[0].full_span)

        # an older saved design with no "full_span" key still loads
        del data["features"][0]["full_span"]
        legacy = layout_from_dict(data)
        self.assertFalse(legacy.features[0].full_span)


class AngledDividerTests(unittest.TestCase):
    """A divider that leans, to hold what it stores at an angle."""

    box = BoxSpec(80.0, 80.0, 40.0)
    thickness = 4.0

    def _cross_section(self, mesh, z, along: str):
        from trimesh.intersections import mesh_plane
        lines = mesh_plane(
            mesh, plane_normal=np.array([0.0, 0.0, 1.0]),
            plane_origin=np.array([0.0, 0.0, z]),
        )
        axis = 1 if along == "x" else 0
        values = lines[:, :, axis].ravel()
        return float(values.min()), float(values.max())

    def test_zero_angle_is_pixel_identical_to_a_plain_divider(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        plain = build_features(
            self.box, [Feature("divider", zone, along="x")], self.box.wall
        )[0]
        explicit_zero = build_features(
            self.box,
            [Feature("divider", zone, along="x", options={"angle": 0.0})],
            self.box.wall,
        )[0]
        self.assertTrue((plain.bounds == explicit_zero.bounds).all())
        self.assertAlmostEqual(plain.volume, explicit_zero.volume, places=6)

    def test_the_base_gets_a_45_degree_chamfer_for_strength(self) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height = 8.0
        one = Feature("divider", zone, along="x",
                      options={"thickness": self.thickness, "height": height})
        mesh = build_features(self.box, [one], self.box.wall)[0]
        self.assertTrue(mesh.is_watertight)
        from organizer_inserts import DIVIDER_CHAMFER
        floor = self.box.wall
        # flared by the full chamfer at the very floor - 45 degrees means the
        # horizontal flare equals the 1 mm rise
        lo, hi = self._cross_section(mesh, floor + 1e-4, "x")
        self.assertAlmostEqual(hi - lo, self.thickness + 2.0 * DIVIDER_CHAMFER, delta=0.02)
        # and back to the nominal thickness exactly at chamfer height
        lo, hi = self._cross_section(mesh, floor + DIVIDER_CHAMFER, "x")
        self.assertAlmostEqual(hi - lo, self.thickness, places=3)

    def test_a_divider_shorter_than_its_own_chamfer_is_refused(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        one = Feature("divider", zone, along="x", options={"height": 0.5})
        with self.assertRaisesRegex(ValueError, "chamfer"):
            build_features(self.box, [one], self.box.wall)

    def test_a_straight_sloped_wall_keeps_uniform_thickness_while_it_leans(
        self,
    ) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height, angle = 8.0, 20.0
        one = Feature(
            "divider", zone, along="x", wedge=False,
            options={"angle": angle, "thickness": self.thickness, "height": height},
        )
        mesh = build_features(self.box, [one], self.box.wall)[0]
        self.assertTrue(mesh.is_watertight)
        lean = height * math.tan(math.radians(angle))
        # fractions kept above the base chamfer (DIVIDER_CHAMFER / height =
        # 0.125 here), which is a deliberate local exception to "uniform
        # thickness" covered by its own test below
        for frac in (0.2, 0.5, 0.95):
            z = self.box.wall + frac * height
            lo, hi = self._cross_section(mesh, z, "x")
            self.assertAlmostEqual(hi - lo, self.thickness, places=3)
            # both faces slide together, proportionally to height
            self.assertAlmostEqual(lo, -self.thickness / 2.0 + frac * lean, places=2)
        from organizer_inserts import DIVIDER_CHAMFER
        # the shear does not change the area the chamfer's two 45-degree
        # corners add (Cavalieri's principle), so it is just chamfer^2 * run
        chamfer_volume = DIVIDER_CHAMFER ** 2 * 30.0
        self.assertAlmostEqual(mesh.volume, self.thickness * height * 30.0 + chamfer_volume, places=1)

    def test_the_default_wedge_is_thick_at_the_floor_and_tapers_as_it_rises(
        self,
    ) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height, angle = 8.0, 20.0
        one = Feature(
            "divider", zone, along="x",
            options={"angle": angle, "thickness": self.thickness, "height": height},
        )
        self.assertTrue(one.wedge)  # the default
        mesh = build_features(self.box, [one], self.box.wall)[0]
        self.assertTrue(mesh.is_watertight)
        lean = height * math.tan(math.radians(angle))
        back = None
        for frac in (0.2, 0.5, 0.95):
            z = self.box.wall + frac * height
            lo, hi = self._cross_section(mesh, z, "x")
            # the back face never moves
            back = lo if back is None else back
            self.assertAlmostEqual(lo, back, places=3)
            # the leaning face narrows the cross-section as height increases
            self.assertAlmostEqual(hi - lo, self.thickness - frac * lean, places=2)
        # strictly less material than the straight wall covering the same lean
        straight = build_features(
            self.box,
            [Feature("divider", zone, along="x", wedge=False,
                      options={"angle": angle, "thickness": self.thickness,
                               "height": height})],
            self.box.wall,
        )[0]
        self.assertLess(mesh.volume, straight.volume)

    def test_a_negative_angle_leans_the_wedge_the_other_way(self) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height, angle = 8.0, -20.0
        one = Feature(
            "divider", zone, along="x",
            options={"angle": angle, "thickness": self.thickness, "height": height},
        )
        mesh = build_features(self.box, [one], self.box.wall)[0]
        front = None
        for frac in (0.2, 0.95):
            z = self.box.wall + frac * height
            lo, hi = self._cross_section(mesh, z, "x")
            front = hi if front is None else front
            # this time the *high* face stays put and the low face sweeps up
            self.assertAlmostEqual(hi, front, places=3)

    def test_along_y_mirrors_along_x(self) -> None:
        zone = Zone(-self.thickness / 2.0, -15.0, self.thickness / 2.0, 15.0)
        height, angle = 8.0, 20.0
        one = Feature(
            "divider", zone, along="y",
            options={"angle": angle, "thickness": self.thickness, "height": height},
        )
        mesh = build_features(self.box, [one], self.box.wall)[0]
        back = None
        for frac in (0.2, 0.95):
            z = self.box.wall + frac * height
            lo, hi = self._cross_section(mesh, z, "y")
            back = lo if back is None else back
            self.assertAlmostEqual(lo, back, places=3)

    def test_an_angle_past_the_printable_limit_is_refused(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        for bad in (46.0, -46.0, math.nan):
            one = Feature("divider", zone, along="x", options={"angle": bad})
            with self.assertRaisesRegex(ValueError, "45 degrees"):
                build_features(self.box, [one], self.box.wall)

    def test_a_wedge_tapered_past_its_own_thickness_is_refused(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        one = Feature(
            "divider", zone, along="x",
            options={"angle": 44.0, "thickness": 2.0, "height": 30.0},
        )
        with self.assertRaisesRegex(ValueError, "taper"):
            build_features(self.box, [one], self.box.wall)

    def test_wedge_round_trips_through_the_saved_design_schema(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        layout = Layout(
            (Feature("divider", zone, along="x", wedge=False,
                      options={"angle": 15.0}),),
            "fused", EDITOR_SNAP,
        )
        data = layout_to_dict(layout)
        self.assertFalse(data["features"][0]["wedge"])
        restored = layout_from_dict(data)
        self.assertFalse(restored.features[0].wedge)

        # an older saved design with no "wedge" key still loads, defaulting
        # to the strong shape
        del data["features"][0]["wedge"]
        legacy = layout_from_dict(data)
        self.assertTrue(legacy.features[0].wedge)


class MultiDividerTests(unittest.TestCase):
    """A divider's ``count`` builds several evenly spaced parallel walls."""

    box = BoxSpec(80.0, 80.0, 40.0)

    def test_count_one_is_identical_to_no_count_at_all(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        auto = build_features(self.box, [Feature("divider", zone, along="x")], self.box.wall)
        explicit = build_features(
            self.box, [Feature("divider", zone, along="x", count=1)], self.box.wall
        )
        self.assertEqual(len(auto), 1)
        self.assertEqual(len(explicit), 1)
        self.assertTrue((auto[0].bounds == explicit[0].bounds).all())

    def test_three_dividers_split_the_zone_into_four_equal_gaps(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        walls = build_features(
            self.box,
            [Feature("divider", zone, along="x", count=3,
                      options={"thickness": 1.0})],
            self.box.wall,
        )
        self.assertEqual(len(walls), 3)
        centres = sorted((wall.bounds[0][1] + wall.bounds[1][1]) / 2.0 for wall in walls)
        gaps = [b - a for a, b in zip(centres, centres[1:])]
        self.assertAlmostEqual(gaps[0], gaps[1], places=3)
        # the outer gaps to the zone edges match the inner gap between walls
        self.assertAlmostEqual(centres[0] - zone.y0, gaps[0], places=3)
        self.assertAlmostEqual(zone.y1 - centres[-1], gaps[0], places=3)

    def test_along_y_spaces_dividers_across_x_instead(self) -> None:
        zone = Zone(-20.0, -15.0, 20.0, 15.0)
        walls = build_features(
            self.box,
            [Feature("divider", zone, along="y", count=3,
                      options={"thickness": 1.0})],
            self.box.wall,
        )
        centres = sorted((wall.bounds[0][0] + wall.bounds[1][0]) / 2.0 for wall in walls)
        self.assertAlmostEqual(centres[1], 0.0, places=3)  # zone is centred on x=0

    def test_an_explicit_spacing_overrides_the_computed_even_gap(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        walls = build_features(
            self.box,
            [Feature("divider", zone, along="x", count=3,
                      options={"thickness": 1.0, "spacing": 5.0})],
            self.box.wall,
        )
        self.assertEqual(len(walls), 3)
        centres = sorted((wall.bounds[0][1] + wall.bounds[1][1]) / 2.0 for wall in walls)
        gaps = [b - a for a, b in zip(centres, centres[1:])]
        self.assertAlmostEqual(gaps[0], 5.0, places=3)
        self.assertAlmostEqual(gaps[1], 5.0, places=3)
        # anchored from the zone's low edge, not necessarily centred, since
        # an explicit spacing need not equal the auto (evenly-filling) value
        self.assertAlmostEqual(centres[0] - zone.y0, 5.0, places=3)

    def test_an_explicit_spacing_too_tight_for_the_zone_is_refused(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        one = Feature(
            "divider", zone, along="x", count=3,
            options={"thickness": 1.0, "spacing": 100.0},
        )
        with self.assertRaisesRegex(ValueError, "need .* mm.*but the zone gives"):
            build_features(self.box, [one], self.box.wall)

    def test_too_many_dividers_for_the_zone_is_refused(self) -> None:
        zone = Zone(-15.0, -2.0, 15.0, 2.0)
        one = Feature("divider", zone, along="x", count=5, options={"thickness": 2.0})
        with self.assertRaisesRegex(ValueError, "need at least"):
            build_features(self.box, [one], self.box.wall)

    def test_count_also_works_full_span_and_leaning(self) -> None:
        zone = Zone(-15.0, -30.0, 15.0, 30.0)
        one = Feature(
            "divider", zone, along="x", count=3, full_span=True,
            options={"angle": 10.0, "thickness": 3.0, "height": 10.0},
        )
        walls = build_features(self.box, [one], self.box.wall)
        self.assertEqual(len(walls), 3)
        for wall in walls:
            self.assertTrue(wall.is_watertight)


class FullSpanLeaningDividerTests(unittest.TestCase):
    """A leaning divider that also hugs the box's true wavy wall."""

    box = BoxSpec(40.0, 48.0, 40.0)
    thickness, height, angle = 4.0, 8.0, 20.0

    def _feature(self, along: str = "x", **overrides) -> Feature:
        whole = Zone.whole(self.box)
        half_t = self.thickness / 2.0
        zone = (
            Zone(whole.x0, -half_t, whole.x1, half_t) if along == "x" else
            Zone(-half_t, whole.y0, half_t, whole.y1)
        )
        options = {"thickness": self.thickness, "height": self.height, "angle": self.angle}
        options.update(overrides.pop("options", {}))
        return Feature("divider", zone, along=along, full_span=True, options=options, **overrides)

    def test_the_edge_touches_the_true_wall_at_every_point_across_the_lean(
        self,
    ) -> None:
        # Not just close at each height's overall extent (its bounding box),
        # but exactly zero gap at every point the wedge's own cross-section
        # actually covers, which itself shifts sideways as it rises.
        from trimesh.intersections import mesh_plane
        from shapely.geometry import LineString

        cavity = wavy_cavity_polygon(self.box)
        one = self._feature()
        solid = build_features(self.box, [one], self.box.wall)[0]
        self.assertTrue(solid.is_watertight)
        lean = self.height * math.tan(math.radians(self.angle))
        half_t = self.thickness / 2.0
        worst = 0.0
        for frac in (0.02, 0.3, 0.6, 0.98):
            z = self.box.wall + frac * self.height
            y_low, y_high = -half_t, half_t - frac * lean
            lines = mesh_plane(
                solid, plane_normal=np.array([0.0, 0.0, 1.0]),
                plane_origin=np.array([0.0, 0.0, z]),
            )
            for y in np.linspace(y_low + 1e-4, y_high - 1e-4, 5):
                probe = LineString([(-30.0, y), (30.0, y)])
                true_xs = [point[0] for point in probe.intersection(cavity).coords]
                at_y = []
                for (x0, py0, _z0), (x1, py1, _z1) in lines:
                    if (py0 - y) * (py1 - y) <= 0 and py0 != py1:
                        t = (y - py0) / (py1 - py0)
                        at_y.append(x0 + t * (x1 - x0))
                if not at_y:
                    continue
                worst = max(
                    worst, abs(min(at_y) - min(true_xs)), abs(max(true_xs) - max(at_y))
                )
        self.assertLess(worst, 1e-3)  # mesh vertex precision, not a real gap

    def test_a_negative_angle_and_a_straight_wall_still_build(self) -> None:
        for overrides in ({"options": {"angle": -self.angle}}, {"wedge": False}):
            one = self._feature(**overrides)
            solid = build_features(self.box, [one], self.box.wall)[0]
            self.assertTrue(solid.is_watertight, overrides)

    def test_along_y_mirrors_along_x(self) -> None:
        solid = build_features(self.box, [self._feature(along="y")], self.box.wall)[0]
        self.assertTrue(solid.is_watertight)

    def test_flat_inside_still_gives_two_stacked_pieces(self) -> None:
        box = BoxSpec(40.0, 48.0, 40.0, flat_inside=0.6)
        whole = Zone.whole(box)
        half_t = self.thickness / 2.0
        zone = Zone(whole.x0, -half_t, whole.x1, half_t)
        one = Feature(
            "divider", zone, along="x", full_span=True,
            options={"thickness": self.thickness, "height": self.height, "angle": self.angle},
        )
        pieces = build_features(box, [one], box.wall)
        self.assertEqual(len(pieces), 2)
        flat, wavy = sorted(pieces, key=lambda solid: solid.bounds[0][2])
        self.assertAlmostEqual(flat.bounds[0][2], box.wall, places=6)
        self.assertAlmostEqual(flat.bounds[1][2], box.wall + box.flat_inside, places=6)
        self.assertAlmostEqual(wavy.bounds[0][2], flat.bounds[1][2], places=6)
        for solid in pieces:
            self.assertTrue(solid.is_watertight)

    def test_still_refuses_an_angle_past_the_limit_and_a_collapsed_wedge(self) -> None:
        with self.assertRaisesRegex(ValueError, "45 degrees"):
            build_features(
                self.box, [self._feature(options={"angle": 46.0})], self.box.wall
            )
        with self.assertRaisesRegex(ValueError, "taper"):
            build_features(
                self.box,
                [self._feature(options={"thickness": 1.6, "height": 30.0, "angle": 30.0})],
                self.box.wall,
            )

    def test_inside_a_removable_insert_it_clips_flush_to_the_straight_plate_edge(
        self,
    ) -> None:
        insert = make_fitted_insert(self.box, [self._feature()])
        footprint = insert_footprint(self.box, "separate")
        self.assertAlmostEqual(insert.bounds[1][0], footprint.bounds[2], places=3)
        self.assertAlmostEqual(insert.bounds[0][0], footprint.bounds[0], places=3)


class RegistryTests(unittest.TestCase):
    def test_every_holder_is_registered_and_callable(self) -> None:
        for kind in ("cradle", "nest", "bore", "post", "divider", "pocket"):
            self.assertIn(kind, inserts.FEATURE_BUILDERS)
            self.assertTrue(callable(inserts.FEATURE_BUILDERS[kind]))

    def test_a_new_holder_needs_nothing_but_a_function(self) -> None:
        # the point of the registry: holders are add- and remove-able
        @inserts.feature("test_slab")
        def build(box, spec_feature, base_z):
            slab = trimesh.creation.box(extents=(10.0, 10.0, 5.0))
            slab.apply_translation((0.0, 0.0, base_z + 2.5))
            return [slab]

        try:
            made = build_features(
                BIN, [Feature("test_slab", Zone(-10.0, -10.0, 10.0, 10.0))], BIN.wall
            )
            self.assertEqual(len(made), 1)
        finally:
            del inserts.FEATURE_BUILDERS["test_slab"]
        self.assertNotIn("test_slab", inserts.FEATURE_BUILDERS)


class OtherHoldersTests(unittest.TestCase):
    def test_each_holder_builds_a_watertight_solid(self) -> None:
        pencil = inserts.LIBRARY["pencil"]
        cases = [
            Feature("bore", Zone(-60.0, -20.0, -20.0, 20.0), pencil),
            photo_nest(),
            Feature("post", Zone(-20.0, -20.0, 20.0, 20.0), count=2),
            Feature("divider", Zone(-10.0, -20.0, 10.0, 20.0), along="y"),
            Feature("pocket", Zone(20.0, -20.0, 60.0, 20.0)),
        ]
        for one in cases:
            for solid in build_features(BIN, [one], BIN.wall):
                self.assertTrue(solid.is_watertight, one.kind)
                self.assertGreater(solid.volume, 0.0, one.kind)

    def test_a_bore_makes_holes(self) -> None:
        pencil = inserts.LIBRARY["pencil"]
        zone = Zone(-60.0, -20.0, -20.0, 20.0)
        bored = build_features(BIN, [Feature("bore", zone, pencil)], BIN.wall)[0]
        height = bored.bounds[1][2] - bored.bounds[0][2]
        solid = trimesh.creation.box(extents=(zone.width, zone.depth, height))
        self.assertLess(bored.volume, solid.volume)

    def test_photo_nest_uses_the_true_outside_contour(self) -> None:
        shaped = photo_nest()
        rectangle = photo_nest(contour=((-30, -10), (30, -10), (30, 10), (-30, 10)))
        shaped_mesh = build_features(BIN, [shaped], BIN.wall)[0]
        rectangle_mesh = build_features(BIN, [rectangle], BIN.wall)[0]
        self.assertNotAlmostEqual(shaped_mesh.volume, rectangle_mesh.volume, places=3)
        self.assertTrue(shaped_mesh.is_watertight)

    def test_clearance_and_rim_control_cavity_and_footprint(self) -> None:
        tight = photo_nest(options={"clearance": 0.0, "rim": 2.0, "depth": 8.0})
        loose = photo_nest(options={"clearance": 1.0, "rim": 4.0, "depth": 8.0})
        self.assertAlmostEqual(loose.zone.width - tight.zone.width, 6.0, places=5)
        self.assertAlmostEqual(loose.zone.depth - tight.zone.depth, 6.0, places=5)
        tight_mesh = build_features(BIN, [tight], BIN.wall)[0]
        loose_same_zone = inserts.fitted_nest_feature(
            Feature("nest", tight.zone, options={"clearance": 1.0, "rim": 1.0, "depth": 8.0},
                    contour=PHOTO_CONTOUR)
        )
        loose_mesh = build_features(BIN, [loose_same_zone], BIN.wall)[0]
        self.assertLess(loose_mesh.volume, tight_mesh.volume)

    def test_cavity_depth_leaves_printable_base(self) -> None:
        one = photo_nest(options={"clearance": 0.0, "rim": 3.0, "depth": 12.0})
        meshes = build_features(BIN, [one], BIN.wall)
        mesh = inserts.union(meshes)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][2], BIN.wall, places=5)
        self.assertAlmostEqual(mesh.bounds[1][2], BIN.wall + 12.0, places=5)
        self.assertLess(mesh.volume, one.zone.width * one.zone.depth * 12.0)
        too_deep = photo_nest(options={
            "clearance": 0.0, "rim": 3.0,
            "depth": BIN.z - BIN.wall + 0.1,
        })
        with self.assertRaisesRegex(ValueError, "printable floor"):
            build_features(BIN, [too_deep], BIN.wall)

    def test_smoothing_removes_small_outline_details(self) -> None:
        detailed = photo_nest(contour=((-20, -8), (-4, -8), (-4, -2), (4, -2),
                                       (4, -8), (20, -8), (20, 8), (4, 8),
                                       (4, 2), (-4, 2), (-4, 8), (-20, 8)),
                              options={"smoothing": 3.0})
        raw_area = inserts.nest_contour_polygon(
            photo_nest(contour=detailed.contour), include_clearance=False
        ).area
        smooth_area = inserts.nest_contour_polygon(detailed, include_clearance=False).area
        self.assertNotAlmostEqual(raw_area, smooth_area, places=3)

    def test_smoothed_local_contour_matches_the_built_silhouette(self) -> None:
        # what the 2D layout draws (local, pre-transform) must be the same
        # softening the builder bakes into the printed wall
        shape = ((-20, -8), (-4, -8), (-4, -2), (4, -2), (4, -8),
                 (20, -8), (20, 8), (-20, 8))
        sharp = photo_nest(contour=shape, options={"smoothing": 0.0})
        soft = photo_nest(contour=shape, options={"smoothing": 3.0})
        self.assertEqual(len(inserts.nest_smoothed_contour(sharp)), len(shape))
        soft_local = inserts.nest_smoothed_contour(soft)
        self.assertGreater(len(soft_local), len(shape))
        from shapely.geometry import Polygon as _P
        # the local softened ring, scaled/placed by hand, lands on the same
        # outline nest_contour_polygon produces for the builder
        built = inserts.nest_contour_polygon(soft, include_clearance=False)
        placed = _P([(x * soft.scale + soft.zone.centre[0],
                      y * soft.scale + soft.zone.centre[1]) for x, y in soft_local])
        self.assertAlmostEqual(placed.area, built.area, delta=built.area * 0.02)

    def test_photo_nest_is_a_raised_cutter_not_a_filled_block(self) -> None:
        one = photo_nest(options={"clearance": 0.0, "rim": 3.0, "depth": 8.0})
        cutter = inserts.union(build_features(BIN, [one], BIN.wall))
        outer_area = inserts.nest_contour_polygon(one, True).buffer(3.0).area
        self.assertLess(cutter.volume, outer_area * 8.0)
        self.assertTrue(cutter.is_watertight)
        self.assertGreater(cutter.bounds[0][2], 0.0)

    def test_posts_are_tapered_and_repeat_along_the_selected_axis(self) -> None:
        feature = Feature(
            "post", Zone(-30.0, -10.0, 30.0, 10.0), count=3, along="x",
            options={"diameter": 12.0, "height": 16.0, "spacing": 4.0, "taper": 0.4},
        )
        posts = build_features(BIN, [feature], BIN.wall)
        self.assertEqual(len(posts), 3)
        self.assertEqual(len({round(post.centroid[1], 6) for post in posts}), 1)
        post = posts[0]
        low = post.vertices[abs(post.vertices[:, 2] - BIN.wall) < 1e-5]
        high = post.vertices[abs(post.vertices[:, 2] - (BIN.wall + 16.0)) < 1e-5]
        low_radius = max((vertex[0] - post.centroid[0]) ** 2 + vertex[1] ** 2 for vertex in low)
        high_radius = max((vertex[0] - post.centroid[0]) ** 2 + vertex[1] ** 2 for vertex in high)
        self.assertGreater(low_radius, high_radius)

    def test_a_builder_cannot_escape_the_zone_claimed_by_the_editor(self) -> None:
        # A divider is a deliberate, documented exception to this (its
        # thickness option, not its zone, decides how wide it actually
        # builds - see test_a_thicker_wall_than_the_zone_widens_to_match
        # below) - so prove the general safety net still holds with a kind
        # that has no such exception, by making its builder misbehave.
        from unittest.mock import patch

        oversized = Feature("pocket", Zone(-10.0, -10.0, 10.0, 10.0))
        runaway = lambda box, one, base_z: [
            trimesh.creation.box(extents=(40.0, 40.0, 5.0))
        ]
        with patch.dict(inserts.FEATURE_BUILDERS, {"pocket": runaway}):
            with self.assertRaisesRegex(ValueError, "exceeds its layout zone"):
                build_features(BIN, [oversized], BIN.wall)

    def test_a_thicker_wall_than_the_zone_widens_to_match(self) -> None:
        # A divider is built from its own thickness option on the cross
        # axis, not from the zone's stored footprint there - the two are
        # allowed to disagree, and the wider one wins rather than the
        # builder being refused for a footprint that was only ever a
        # convenience the editor drew, never the wall's real thickness.
        thicker = Feature(
            "divider", Zone(-20.0, -0.5, 20.0, 0.5),
            options={"thickness": 5.0},
        )
        wall = build_features(BIN, [thicker], BIN.wall)[0]
        # the built wall's overall footprint also carries the base chamfer's
        # flare on top of the 5 mm thickness (see
        # AngledDividerTests.test_the_base_gets_a_45_degree_chamfer_for_strength)
        from organizer_inserts import DIVIDER_CHAMFER
        self.assertAlmostEqual(
            wall.bounds[1][1] - wall.bounds[0][1], 5.0 + 2.0 * DIVIDER_CHAMFER, places=6
        )
        self.assertTrue(wall.is_watertight)


class KeepOutTests(unittest.TestCase):
    def test_a_cradle_stays_clear_of_the_connector_arms(self) -> None:
        limit = inserts.connector_keep_out(BIN)
        self.assertAlmostEqual(limit, BIN.z - ConnectorSpec().arm_depth)
        ribs = build_features(
            BIN, [Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER)], BIN.wall
        )
        for rib in ribs:
            self.assertLess(rib.bounds[1][2], limit)

    def test_a_tall_wall_edge_feature_is_refused_but_an_interior_one_is_not(self) -> None:
        whole = Zone.whole(BIN)
        edge = Feature(
            "divider", Zone(whole.x0, -10.0, whole.x0 + 2.0, 10.0),
            along="y", options={"height": BIN.z - BIN.wall - 1.0},
        )
        with self.assertRaisesRegex(ValueError, "connector can seat"):
            build_features(BIN, [edge], BIN.wall)
        interior = Feature(
            "divider", Zone(-1.0, -10.0, 1.0, 10.0),
            along="y", options={"height": BIN.z - BIN.wall - 1.0},
        )
        self.assertTrue(build_features(BIN, [interior], BIN.wall))

    def test_a_removable_edge_divider_is_sized_at_its_installed_height(self) -> None:
        whole = Zone.whole(BIN)
        edge = Feature(
            "divider", Zone(whole.x0, -10.0, whole.x0 + 2.0, 10.0), along="y"
        )
        insert = make_fitted_insert(BIN, [edge])
        seated_top = insert.bounds[1][2] + BIN.wall
        self.assertAlmostEqual(seated_top, inserts.connector_keep_out(BIN), places=5)


class LayoutModelTests(unittest.TestCase):
    def test_normal_dragging_snaps_to_one_millimetre_and_clamps(self) -> None:
        one = Feature("pocket", Zone(-8.0, -8.0, 8.0, 8.0))
        moved = inserts.moved_feature(one, BIN, (999.4, -13.6))
        bounds = inserts.layout_zone(BIN)
        self.assertAlmostEqual(moved.zone.x1, bounds.x1)
        self.assertEqual(moved.zone.centre[1], -14.0)

    def test_cartridge_area_is_whole_eight_millimetre_cells(self) -> None:
        zone = inserts.cartridge_zone(BIN)
        self.assertEqual((zone.width, zone.depth), (120.0, 80.0))
        self.assertAlmostEqual(
            1.0 - zone.width * zone.depth / (Zone.whole(BIN).width * Zone.whole(BIN).depth),
            0.098,
            places=3,
        )

    def test_cartridge_features_snap_from_the_cartridge_origin(self) -> None:
        one = Feature("pocket", Zone(-7.0, -7.0, 8.0, 8.0))
        snapped = inserts.resized_feature(one, BIN, (16.0, 16.0), "cartridge")
        layout = inserts.Layout((snapped,), "cartridge")
        layout.validate(BIN)
        bounds = inserts.cartridge_zone(BIN)
        self.assertAlmostEqual((snapped.zone.x0 - bounds.x0) % 8.0, 0.0)
        self.assertAlmostEqual((snapped.zone.y0 - bounds.y0) % 8.0, 0.0)

    def test_a_non_cell_cartridge_layout_is_refused(self) -> None:
        bad = inserts.Layout((Feature("pocket", Zone(-5, -5, 5, 5)),), "cartridge")
        with self.assertRaisesRegex(ValueError, "8 mm cells"):
            bad.validate(BIN)

    def test_layout_json_round_trip_preserves_custom_items_and_options(self) -> None:
        layout = inserts.Layout((Feature(
            "cradle", Zone(-40, -20, 40, 20), DRIVER, 3, "x", {"floor_gap": 3.0},
            alternate_ends=True,
        ),), "separate")
        rebuilt = inserts.layout_from_dict(inserts.layout_to_dict(layout))
        self.assertEqual(rebuilt, layout)

    def test_old_layouts_default_to_non_alternating_ends(self) -> None:
        data = inserts.layout_to_dict(Layout((Feature(
            "cradle", Zone(-40, -20, 40, 20), DRIVER, 2,
        ),)))
        del data["features"][0]["alternate_ends"]
        self.assertFalse(layout_from_dict(data).features[0].alternate_ends)

    def test_only_cradles_can_alternate_ends(self) -> None:
        with self.assertRaisesRegex(ValueError, "only a cradle"):
            Feature("bore", Zone(-10, -10, 10, 10), DRIVER, alternate_ends=True)

    def test_photo_nest_json_round_trip_preserves_contour_transform(self) -> None:
        one = photo_nest(rotation=27.0, scale=1.2)
        rebuilt = layout_from_dict(layout_to_dict(Layout((one,)))).features[0]
        self.assertEqual(rebuilt.contour, one.contour)
        self.assertEqual(rebuilt.rotation, 27.0)
        self.assertEqual(rebuilt.scale, 1.2)

    def test_retired_segment_nest_is_rejected_explicitly(self) -> None:
        legacy = {
            "version": 1, "mode": "fused", "snap": 1.0,
            "features": [{
                "kind": "nest", "zone": [-20, -10, 20, 10],
                "item": {"name": "Old", "profile": "round", "clearance": .4,
                         "segments": [{"length": 30, "diameter": 8}]},
                "count": 1, "along": "x", "options": {},
            }],
        }
        with self.assertRaisesRegex(ValueError, "retired measured Nest"):
            layout_from_dict(legacy)

    def test_empty_standalone_and_cartridge_inserts_are_valid_base_plates(self) -> None:
        for mesh in (inserts.make_fitted_insert(BIN, []),
                     inserts.make_cartridge_insert(BIN, [])):
            self.assertTrue(mesh.is_watertight)
            self.assertAlmostEqual(mesh.bounds[0][2], 0.0)
            self.assertAlmostEqual(mesh.bounds[1][2], inserts.BASE_PLATE)


if __name__ == "__main__":
    unittest.main()
