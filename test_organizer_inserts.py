"""Tests for the in-bin holders."""

from __future__ import annotations

import unittest

import trimesh

from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    intersection_volume,
    make_box,
    translated,
)
import organizer_inserts as inserts
from organizer_inserts import (
    Feature,
    Item,
    Segment,
    Zone,
    build_features,
    check_layout,
    make_fitted_insert,
    make_fused_box,
)

BIN = BoxSpec(128.0, 88.0, 40.0)
DRIVER = inserts.LIBRARY["hex_driver"]


class ItemTests(unittest.TestCase):
    def test_an_item_measures_itself_end_to_end(self) -> None:
        self.assertEqual(DRIVER.length, 80.0)
        self.assertEqual(DRIVER.widest, 18.0)
        self.assertEqual(len(DRIVER.segments), 2)

    def test_segment_centres_are_midpoints_along_the_object(self) -> None:
        centres = [round(c, 3) for c, _ in DRIVER.segment_centres()]
        self.assertEqual(centres, [25.0, 65.0])       # 50 long, then 30 long

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


class CradleTests(unittest.TestCase):
    def _feature(self, span: float = 88.0) -> Feature:
        return Feature("cradle", Zone.end(BIN, "x", span), DRIVER, along="x")

    def test_one_rib_per_segment_of_the_item(self) -> None:
        ribs = build_features(BIN, [self._feature()], BIN.wall)
        self.assertEqual(len(ribs), len(DRIVER.segments))
        for rib in ribs:
            self.assertTrue(rib.is_watertight)

    def test_ribs_sit_on_the_floor_and_share_one_axis_height(self) -> None:
        ribs = build_features(BIN, [self._feature()], BIN.wall)
        for rib in ribs:
            self.assertAlmostEqual(rib.bounds[0][2], BIN.wall, places=6)
        tops = [round(rib.bounds[1][2], 6) for rib in ribs]
        self.assertEqual(len(set(tops)), 1)   # a handled tool rests level

    def test_the_handle_rib_is_cut_deeper_than_the_shaft_rib(self) -> None:
        # same outside size, so the bigger notch removes more material
        shaft, handle = build_features(BIN, [self._feature()], BIN.wall)
        self.assertLess(handle.volume, shaft.volume)

    def test_notches_are_half_circles_so_a_tool_can_drop_in(self) -> None:
        # the notch centre sits on the rib's top edge; any lower and the
        # opening would be narrower than the tool
        ribs = build_features(BIN, [self._feature()], BIN.wall)
        held = DRIVER.held(DRIVER.widest)
        axis_z = BIN.wall + inserts.CRADLE_FLOOR_GAP + held / 2.0
        for rib in ribs:
            self.assertAlmostEqual(rib.bounds[1][2], axis_z, places=6)

    def test_it_fits_as_many_as_the_zone_allows(self) -> None:
        wide = build_features(BIN, [self._feature()], BIN.wall)
        self.assertEqual(len(wide), 2)
        narrow = Feature("cradle", Zone(-60.0, -20.0, 28.0, 20.0), DRIVER, along="x")
        self.assertTrue(build_features(BIN, [narrow], BIN.wall))

    def test_an_explicit_count_that_will_not_fit_is_refused(self) -> None:
        crowded = Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER, count=20)
        with self.assertRaisesRegex(ValueError, "across"):
            build_features(BIN, [crowded], BIN.wall)

    def test_an_item_longer_than_its_zone_is_refused(self) -> None:
        cramped = Feature("cradle", Zone.end(BIN, "x", 40.0), DRIVER)
        with self.assertRaisesRegex(ValueError, "long"):
            build_features(BIN, [cramped], BIN.wall)


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

    def test_a_standalone_insert_clears_the_bin_walls(self) -> None:
        insert = make_fitted_insert(BIN, [self._feature()])
        self.assertTrue(insert.is_watertight)
        clear_x, clear_y = BIN.usable_inside
        # trimmed to the plate footprint, so it clears the wall on every side
        self.assertLessEqual(
            insert.bounds[1][0], clear_x / 2.0 - inserts.INSERT_CLEARANCE + 1e-6
        )
        self.assertLessEqual(
            insert.bounds[1][1], clear_y / 2.0 - inserts.INSERT_CLEARANCE + 1e-6
        )
        self.assertGreaterEqual(
            insert.bounds[0][1], -clear_y / 2.0 + inserts.INSERT_CLEARANCE - 1e-6
        )
        # it is built standing on z=0 so it prints flat on the bed; dropped
        # onto the bin floor it clears the box entirely
        seated = translated(insert, (0.0, 0.0, BIN.wall))
        self.assertLess(intersection_volume(seated, make_box(BIN)), 0.01)

    def test_a_standalone_insert_stands_on_its_own_plate(self) -> None:
        insert = make_fitted_insert(BIN, [self._feature()])
        self.assertAlmostEqual(insert.bounds[0][2], 0.0, places=6)


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

    def test_an_unknown_holder_names_the_ones_that_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown holder"):
            check_layout(BIN, [Feature("teleporter", Zone.whole(BIN))])


class RegistryTests(unittest.TestCase):
    def test_every_holder_is_registered_and_callable(self) -> None:
        for kind in ("cradle", "bore", "divider", "pocket", "slot"):
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
            Feature("divider", Zone(-10.0, -20.0, 10.0, 20.0), along="y"),
            Feature("pocket", Zone(20.0, -20.0, 60.0, 20.0)),
            Feature("slot", Zone(-60.0, 24.0, -20.0, 40.0)),
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


class KeepOutTests(unittest.TestCase):
    def test_a_cradle_stays_clear_of_the_connector_arms(self) -> None:
        limit = inserts.connector_keep_out(BIN)
        self.assertAlmostEqual(limit, BIN.z - ConnectorSpec().arm_depth)
        ribs = build_features(
            BIN, [Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER)], BIN.wall
        )
        for rib in ribs:
            self.assertLess(rib.bounds[1][2], limit)


if __name__ == "__main__":
    unittest.main()
