import math
import unittest
from unittest.mock import patch

from shapely.geometry import Point

from organizer_app import (
    box_filename,
    connector_filename,
    design_from_dict,
    design_to_dict,
    insert_filename,
)
from organizer_engine import (
    DEFAULT_WALL,
    GRID_PITCH,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    MAX_WALL,
    MIN_WALL,
    WALL_PRESETS,
    WALL_STEP,
    WAVE_AMPLITUDE,
    WAVE_LENGTH,
    WAVE_MATING_GAP,
    BoxSpec,
    ConnectorSpec,
    mating_clearance,
    make_sampler_scene,
    make_box,
    make_side_connector,
    make_wall_lock_bumps,
    nested_clearance,
    validate_side_fit,
    wavy_outer_polygon,
)
from organizer_inserts import Feature, Layout, Zone, build_features, make_fitted_insert
from wavefinity_web import _fit_photo_nest_box, catalog_payload


WALL_CHOICES = tuple(
    round(MIN_WALL + index * WALL_STEP, 1)
    for index in range(round((MAX_WALL - MIN_WALL) / WALL_STEP) + 1)
)


class StandardWallsTests(unittest.TestCase):
    def test_defaults_and_supported_range(self) -> None:
        default = BoxSpec()
        self.assertTrue(default.standard_walls)
        self.assertEqual(default.wall, DEFAULT_WALL)
        self.assertEqual((MIN_WALL, MAX_WALL, WALL_STEP), (0.2, 2.4, 0.2))
        self.assertEqual(BoxSpec(wall=MIN_WALL).wall, MIN_WALL)
        self.assertEqual(BoxSpec(wall=MAX_WALL).wall, MAX_WALL)
        for bad in (MIN_WALL - 0.01, MAX_WALL + 0.01):
            with self.assertRaisesRegex(ValueError, "wall thickness"):
                BoxSpec(wall=bad)
        with self.assertRaisesRegex(ValueError, "positive finite"):
            BoxSpec(wall=math.nan)

    def test_wall_changes_cavity_not_exterior(self) -> None:
        outlines = [wavy_outer_polygon(BoxSpec(wall=wall)) for wall in WALL_CHOICES]
        for outline in outlines[1:]:
            self.assertTrue(outlines[0].equals_exact(outline, 1e-12))
        dimensions = [
            BoxSpec(wall=wall).usable_inside
            for wall in WALL_CHOICES
        ]
        for previous, current in zip(dimensions, dimensions[1:]):
            self.assertLess(current[0], previous[0])
            self.assertLess(current[1], previous[1])

    def test_lock_roots_stay_inside_exterior(self) -> None:
        spec = BoxSpec(x=24.0, y=24.0, wall=MIN_WALL, standard_walls=False)
        self.assertGreater(min(LOCK_EMBED, spec.wall_depth - LOCK_SAFE_SKIN), 0.0)
        exterior = wavy_outer_polygon(spec).buffer(1e-6)
        for bump in make_wall_lock_bumps(spec):
            for x, y in bump.vertices[:, :2]:
                self.assertTrue(exterior.covers(Point(float(x), float(y))))

    def test_extreme_walls_share_the_grid_wave_and_mating_clearance(self) -> None:
        self.assertEqual((WAVE_LENGTH, WAVE_AMPLITUDE, WAVE_MATING_GAP, GRID_PITCH),
                         (4.0, 0.4, 0.25, 8.0))
        thin = BoxSpec(wall=MIN_WALL, standard_walls=False)
        thick = BoxSpec(wall=MAX_WALL, standard_walls=False)
        self.assertAlmostEqual(
            mating_clearance(thin, (-8.0, 0.0), thick, (8.0, 0.0)),
            nested_clearance(),
            places=3,
        )

    def test_min_and_max_wall_boxes_and_connectors_are_valid(self) -> None:
        for wall in (MIN_WALL, MAX_WALL):
            spec = BoxSpec(32.0, 48.0, 24.0, wall=wall, standard_walls=False)
            self.assertTrue(make_box(spec).is_watertight)
            connector = ConnectorSpec()
            clip = make_side_connector(spec, connector, "y", 0.0, 12.0)
            self.assertLessEqual(validate_side_fit(spec, connector, clip, "y"), 0.01)


    def test_flat_divider_and_removable_insert_work_at_extremes(self) -> None:
        for wall in (MIN_WALL, MAX_WALL):
            flat = BoxSpec(
                40.0, 48.0, 40.0, wall=wall, standard_walls=False,
                flat_inside=0.6,
            )
            self.assertTrue(make_box(flat).is_watertight)
            whole = Zone.whole(flat)
            divider = Feature(
                "divider", Zone(whole.x0, -0.8, whole.x1, 0.8),
                along="x", full_span=True,
            )
            self.assertTrue(all(
                solid.is_watertight
                for solid in build_features(flat, [divider], flat.base_thickness)
            ))
            self.assertTrue(make_fitted_insert(flat, [divider]).is_watertight)


    def test_save_open_and_legacy_migration(self) -> None:
        custom = BoxSpec(wall=1.2)
        saved = design_to_dict(custom, Layout())
        self.assertFalse(saved["box"]["standard_walls"])
        reopened, *_ = design_from_dict(saved)
        self.assertFalse(reopened.standard_walls)
        self.assertEqual(reopened.wall, 1.2)

        explicit_custom_standard = BoxSpec(wall=DEFAULT_WALL, standard_walls=False)
        reopened, *_ = design_from_dict(design_to_dict(explicit_custom_standard, Layout()))
        self.assertFalse(reopened.standard_walls)
        self.assertEqual(reopened.wall, DEFAULT_WALL)

        legacy_standard = design_to_dict(BoxSpec(), Layout())
        del legacy_standard["box"]["standard_walls"]
        reopened, *_ = design_from_dict(legacy_standard)
        self.assertTrue(reopened.standard_walls)
        self.assertEqual(reopened.wall, DEFAULT_WALL)

        legacy_custom = design_to_dict(custom, Layout())
        del legacy_custom["box"]["standard_walls"]
        reopened, *_ = design_from_dict(legacy_custom)
        self.assertFalse(reopened.standard_walls)
        self.assertEqual(reopened.wall, 1.2)



    def test_sampler_connector_uses_requested_wall(self) -> None:
        with patch("organizer_engine.make_side_connector", wraps=__import__(
            "organizer_engine"
        ).make_side_connector) as make_connector:
            make_sampler_scene(
                sizes=((16.0, 48.0),), wall=MAX_WALL, clips=1,
                connector=ConnectorSpec(),
            )
        self.assertEqual(make_connector.call_args.args[0].wall, MAX_WALL)



if __name__ == "__main__":
    unittest.main()
