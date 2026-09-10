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

    def test_extreme_wall_connectors_handle_height_and_bin_size(self) -> None:
        connector = ConnectorSpec()
        for wall in (MIN_WALL, MAX_WALL):
            source = BoxSpec(32.0, 48.0, 40.0, wall=wall, standard_walls=False)
            other = BoxSpec(48.0, 48.0, 40.0, wall=wall, standard_walls=False)
            equal = make_side_connector(source, connector, "y", 0.0, 12.0)
            self.assertLessEqual(validate_side_fit(other, connector, equal, "y"), 0.01)
            differing = make_side_connector(
                source, connector, "y", 0.0, 12.0, 40.0, 24.0,
            )
            self.assertLessEqual(validate_side_fit(
                source, connector, differing, "y",
                bin_a_height=40.0, bin_b_height=24.0,
            ), 0.01)

    def test_easy_clean_extremes_stay_watertight_and_inside_envelope(self) -> None:
        for wall in (MIN_WALL, MAX_WALL):
            for style in ("bevel", "curve"):
                spec = BoxSpec(
                    32.0, 48.0, 24.0, wall=wall, standard_walls=False,
                    easy_clean=True, easy_clean_style=style,
                )
                exterior = wavy_outer_polygon(spec).buffer(1e-5)
                for mesh in (
                    make_box(spec),
                    make_box(spec, (("+x", -3.0, 3.0),)),
                ):
                    self.assertTrue(mesh.is_watertight)
                    self.assertTrue(all(
                        exterior.covers(Point(float(x), float(y)))
                        for x, y in mesh.vertices[:, :2]
                    ))

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

    def test_snug_holder_growth_preserves_custom_wall(self) -> None:
        box = BoxSpec(16.0, 16.0, 40.0, wall=MAX_WALL, standard_walls=False)
        nest = Feature(
            "nest", Zone(-20.0, -10.0, 20.0, 10.0),
            contour=((-20.0, -10.0), (20.0, -10.0), (20.0, 10.0), (-20.0, 10.0)),
        )
        grown = _fit_photo_nest_box(box, nest, "fused")
        self.assertGreater(grown.x, box.x)
        self.assertEqual(grown.wall, MAX_WALL)
        self.assertFalse(grown.standard_walls)

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

    def test_standard_flag_normalizes_wall_and_bad_input_is_rejected(self) -> None:
        saved = design_to_dict(BoxSpec(), Layout())
        saved["box"].update({"standard_walls": True, "wall": 1.2})
        reopened, *_ = design_from_dict(saved)
        self.assertEqual(reopened.wall, DEFAULT_WALL)
        saved["box"]["wall"] = MAX_WALL + 0.1
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
                sizes=((16.0, 48.0),), wall=MAX_WALL, clips=1,
                connector=ConnectorSpec(),
            )
        self.assertEqual(make_connector.call_args.args[0].wall, MAX_WALL)

    def test_catalog_exposes_discrete_wall_choices(self) -> None:
        rules = catalog_payload()["wall_rules"]
        self.assertEqual(
            (rules["min_mm"], rules["max_mm"], rules["step_mm"]),
            (MIN_WALL, MAX_WALL, WALL_STEP),
        )
        self.assertEqual(tuple(choice["value"] for choice in rules["choices"]), WALL_CHOICES)
        self.assertEqual(rules["choices"][0]["label"], "Very thin (experimental)")
        self.assertEqual(rules["choices"][-1]["label"], "Maximum thickness")


if __name__ == "__main__":
    unittest.main()
