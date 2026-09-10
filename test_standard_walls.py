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
    MAX_WALL,
    MIN_WALL,
    BoxSpec,
    ConnectorSpec,
    make_sampler_scene,
    make_box,
    make_side_connector,
    make_wall_lock_bumps,
    validate_side_fit,
    wavy_outer_polygon,
)
from organizer_inserts import Layout


class StandardWallsTests(unittest.TestCase):
    def test_defaults_and_supported_range(self) -> None:
        default = BoxSpec()
        self.assertTrue(default.standard_walls)
        self.assertEqual(default.wall, DEFAULT_WALL)
        self.assertEqual(BoxSpec(wall=MIN_WALL).wall, MIN_WALL)
        self.assertEqual(BoxSpec(wall=MAX_WALL).wall, MAX_WALL)
        for bad in (MIN_WALL - 0.01, MAX_WALL + 0.01):
            with self.assertRaisesRegex(ValueError, "wall thickness"):
                BoxSpec(wall=bad)
        with self.assertRaisesRegex(ValueError, "positive finite"):
            BoxSpec(wall=math.nan)

    def test_wall_changes_cavity_not_exterior(self) -> None:
        outlines = [wavy_outer_polygon(BoxSpec(wall=wall)) for wall in (0.4, 0.8, 1.2, 2.0)]
        for outline in outlines[1:]:
            self.assertTrue(outlines[0].equals_exact(outline, 1e-12))
        self.assertGreater(BoxSpec(wall=0.4).usable_inside[0], BoxSpec(wall=2.0).usable_inside[0])

    def test_thin_wall_lock_roots_stay_inside_exterior(self) -> None:
        spec = BoxSpec(x=24.0, y=24.0, wall=MIN_WALL, standard_walls=False)
        exterior = wavy_outer_polygon(spec).buffer(1e-6)
        for bump in make_wall_lock_bumps(spec):
            for x, y in bump.vertices[:, :2]:
                self.assertTrue(exterior.covers(Point(float(x), float(y))))

    def test_min_and_max_wall_boxes_and_connectors_are_valid(self) -> None:
        for wall in (MIN_WALL, MAX_WALL):
            spec = BoxSpec(32.0, 48.0, 24.0, wall=wall, standard_walls=False)
            self.assertTrue(make_box(spec).is_watertight)
            connector = ConnectorSpec()
            clip = make_side_connector(spec, connector, "y", 0.0, 12.0)
            self.assertLessEqual(validate_side_fit(spec, connector, clip, "y"), 0.01)

    def test_save_open_and_legacy_migration(self) -> None:
        custom = BoxSpec(wall=1.2, standard_walls=False)
        saved = design_to_dict(custom, Layout())
        reopened, *_ = design_from_dict(saved)
        self.assertFalse(reopened.standard_walls)
        self.assertEqual(reopened.wall, 1.2)

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

    def test_standard_flag_normalizes_wall_and_bad_input_is_rejected(self) -> None:
        saved = design_to_dict(BoxSpec(), Layout())
        saved["box"].update({"standard_walls": True, "wall": 1.2})
        reopened, *_ = design_from_dict(saved)
        self.assertEqual(reopened.wall, DEFAULT_WALL)
        saved["box"]["wall"] = 2.1
        with self.assertRaisesRegex(ValueError, "wall thickness"):
            design_from_dict(saved)

    def test_custom_filenames_are_identifiable(self) -> None:
        standard = BoxSpec()
        custom = BoxSpec(wall=1.2, standard_walls=False)
        self.assertEqual(box_filename(standard), "Box 16 x 16 x 40.3mf")
        self.assertEqual(connector_filename(), "Connector - Same height.3mf")
        self.assertIn("Wall 1.2mm", box_filename(custom))
        self.assertIn("Wall 1.2mm", insert_filename(custom))
        self.assertIn("Wall 1.2mm", connector_filename(wall=custom.wall))

    def test_sampler_connector_uses_requested_wall(self) -> None:
        with patch("organizer_engine.make_side_connector", wraps=__import__(
            "organizer_engine"
        ).make_side_connector) as make_connector:
            make_sampler_scene(
                sizes=((16.0, 48.0),), wall=2.0, clips=1,
                connector=ConnectorSpec(),
            )
        self.assertEqual(make_connector.call_args.args[0].wall, 2.0)


if __name__ == "__main__":
    unittest.main()
