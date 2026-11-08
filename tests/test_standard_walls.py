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



if __name__ == "__main__":
    unittest.main()
