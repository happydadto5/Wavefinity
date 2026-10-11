"""Tests for the in-bin holders."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import unittest

import numpy as np
import trimesh
from shapely import affinity
from shapely.geometry import Point, box as shapely_box

import organizer_inserts._nest as nest_impl
import organizer_inserts._divider as divider_impl

from organizer_engine import (
    BoxSpec,
    SideOpeningSpec,
    ConnectorSpec,
    LOCK_PROTRUSION,
    WAVE_AMPLITUDE,
    intersection_volume,
    make_box,
    top_label_surface_z,
    translated,
    wall_depth_for,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
import organizer_inserts as inserts
from organizer_side_openings import apply_side_openings
from organizer_inserts._bore import (
    JOIN_SKIN, _bore_grid, _round_clear_sides, _wall_only_shell_reach,
    bore_envelope_zone, bore_minimum_pitches, wall_only_envelope,
)
from organizer_inserts._bore import bore_reference_meshes, bore_reference_top
from organizer_inserts._cradle import cradle_reference_meshes
from organizer_inserts._core import ReferenceObject
from organizer_inserts import (
    EDITOR_SNAP,
    Feature,
    Item,
    Layout,
    Segment,
    Zone,
    build_features,
    check_layout,
    feature_footprint,
    insert_footprint,
    layout_from_dict,
    layout_to_dict,
    make_fitted_insert,
    make_fused_box,
    bore_bin_minimum,
)

BIN = BoxSpec(128.0, 88.0, 40.0)
DRIVER = inserts.LIBRARY["hex_driver"]
ROD = Item.simple("Rod", 60.0, 8.0)
PEN = Item.simple("Pen", 90.0, 12.0)
BIT = Item.simple("Bit", 36.0, 6.0)


PHOTO_CONTOUR = ((-30.0, -10.0), (30.0, -10.0), (30.0, 0.0),
                 (5.0, 0.0), (5.0, 10.0), (-30.0, 10.0))


class ReferenceObjectTests(unittest.TestCase):
    def test_optional_reference_round_trips_and_never_changes_holder_mesh(self):
        plain = Feature("post", Zone(-12, -12, 12, 12))
        referenced = replace(plain, reference_object=ReferenceObject(18, 12, 70))
        saved = layout_to_dict(Layout((referenced,), "fused"))
        self.assertEqual(layout_from_dict(saved).features[0].reference_object, referenced.reference_object)
        self.assertNotIn("reference_object", layout_to_dict(Layout((plain,), "fused"))["features"][0])
        saved["features"][0]["reference_object"] = None
        self.assertIsNone(layout_from_dict(saved).features[0].reference_object)
        saved["features"][0]["reference_object"] = {"width": True, "depth": 12, "height": 70}
        with self.assertRaises(ValueError):
            layout_from_dict(saved)
        self.assertEqual(build_features(BIN, [plain], BIN.base_thickness)[0].volume,
                         build_features(BIN, [referenced], BIN.base_thickness)[0].volume)
        for bad in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                ReferenceObject(bad, 12, 70)
        with self.assertRaises(ValueError):
            replace(Feature("bore", plain.zone), reference_object=ReferenceObject(1, 1, 1))

    def test_bore_reference_top_includes_tilted_radius_and_segments(self):
        item = Item("Tool", (Segment(20, 4), Segment(30, 16)))
        one = Feature("bore", Zone(-20, -20, 20, 20), item, count=1,
                      options={"bore_style": "base_straight", "height": 28,
                               "depth": 20, "angle": 35, "columns": 1, "rows": 1})
        top = bore_reference_top(BIN, one, BIN.base_thickness)
        centreline = BIN.base_thickness + 28 + (item.length - 20) * math.cos(math.radians(35))
        self.assertGreater(top, centreline)
        self.assertEqual(top, max(mesh.bounds[1][2] for mesh in bore_reference_meshes(BIN, one, BIN.base_thickness)))
        upright = replace(one, options={**one.options, "angle": 0})
        self.assertAlmostEqual(bore_reference_top(BIN, upright, BIN.base_thickness),
                               BIN.base_thickness + 28 + item.length - 20)

    def test_cradle_reference_segments_share_trough_seats(self):
        item = Item("Tool", (Segment(20, 4), Segment(10, 12)))
        one = Feature("cradle", Zone(-30, -20, 30, 20), item, count=2,
                      options={"spacing": 2, "run_offset": 50})
        meshes = cradle_reference_meshes(BIN, one, BIN.base_thickness)
        self.assertEqual(len(meshes), 4)
        self.assertEqual(len(build_features(BIN, [one], BIN.base_thickness)), 2)
        self.assertAlmostEqual(min(mesh.bounds[0][2] for mesh in meshes),
                               BIN.base_thickness + 2 + item.widest / 2 - item.widest / 2)


# Exact facade names referenced outside organizer_inserts.py on 2026-09-07.
# The package refactor must preserve every one of these direct imports and
# module attributes, including compatibility aliases used by existing tests.
REQUIRED_FACADE_NAMES = frozenset({
    "BASE_PLATE", "BORE_MOUTH_CHAMFER", "BOTTOM_EMBED", "CARTRIDGE_PITCH",
    "CRADLE_ALTERNATE_END_MARGIN", "CRADLE_FLOOR_GAP", "CRADLE_MIN_FLOOR_GAP",
    "CRADLE_RIB_FRACTION", "CRADLE_RIB_MAX", "DIVIDER_CHAMFER", "EDITOR_SNAP",
    "FEATURE_BUILDERS", "Feature", "HEX_BIT_CLEARANCE", "HEX_BIT_FLATS",
    "HEX_BIT_HOLD", "INSERT_CLEARANCE", "ITEM_CLEARANCE", "Item", "LIBRARY",
    "Layout", "MIN_FEATURE_GAP", "NEST_PUSH_DEPTH", "RIB_THICKNESS", "Segment",
    "TEXT_CAP_HEIGHT_FLOOR", "TEXT_DEPTH", "TEXT_KIND", "Zone",
    "_cradle_rib_thickness", "_cradle_wall", "apply_texts", "auto_grow_text_feature",
    "build_features", "build_text", "build_texts", "cartridge_zone", "check_layout",
    "connector_keep_out", "cradle_min_footprint", "feature", "feature_footprint",
    "feature_min_footprint", "fitted_nest_feature", "flat_cavity_polygon",
    "insert_footprint", "insert_report", "is_text", "layout_from_dict",
    "layout_to_dict", "layout_zone", "make_cartridge_insert", "make_fitted_insert",
    "make_fused_box", "make_insert_plate", "moved_feature", "nest_contour_polygon",
    "nest_smoothed_contour", "occupied_zones", "option_value", "resized_feature",
    "resolve_text_features", "resolved_options", "scoop_zone", "snapped_zone",
    "text_depth", "text_fitted", "text_is_raised", "text_of", "text_placed_outline",
    "union", "wavy_cavity_polygon",
})
EXPECTED_REGISTRY_KEYS = frozenset({
    "bore", "cradle", "divider", "nest", "pocket", "post", "scoop", "slot",
    "steps", "text",
})


class OrganizerInsertsCompatibilityContractTests(unittest.TestCase):
    def test_recorded_direct_imports_and_attributes_remain_available(self) -> None:
        self.assertTrue(all(hasattr(inserts, name) for name in REQUIRED_FACADE_NAMES))
        namespace: dict[str, object] = {}
        exec(
            "from organizer_inserts import " + ", ".join(sorted(REQUIRED_FACADE_NAMES)),
            namespace,
        )
        self.assertTrue(all(name in namespace for name in REQUIRED_FACADE_NAMES))



    def test_saved_layouts_still_round_trip_and_legacy_defaults_survive(self) -> None:
        layout = Layout((Feature(
            "cradle", Zone(-24.0, -12.0, 24.0, 12.0),
            Item.simple("Driver", 40.0, 6.0),
            options={"spacing": 0.0},
        ),), "fused")
        saved = layout_to_dict(layout)
        self.assertEqual(layout_from_dict(saved), layout)
        legacy = json.loads(json.dumps(saved))
        legacy["features"][0].pop("alternate_ends")
        self.assertFalse(layout_from_dict(legacy).features[0].alternate_ends)


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
        solids = build_features(BIN, [self._feature()], BIN.base_thickness)
        self.assertEqual(len(solids), 1)                 # one body, not two ribs
        trough = solids[0]
        self.assertTrue(trough.is_watertight)
        run = trough.bounds[1][0] - trough.bounds[0][0]
        self.assertAlmostEqual(run, ROD.length, places=3)  # spans the whole tool
        centre = self._feature().zone.centre[0]
        self.assertAlmostEqual(float(trough.bounds[:, 0].mean()), centre, places=3)






    def test_an_explicit_count_that_will_not_fit_is_refused(self) -> None:
        crowded = Feature("cradle", Zone.end(BIN, "x", 88.0), ROD, count=40)
        with self.assertRaisesRegex(ValueError, "across"):
            build_features(BIN, [crowded], BIN.base_thickness)


    def test_an_item_longer_than_its_zone_is_refused(self) -> None:
        cramped = Feature("cradle", Zone.end(BIN, "x", 40.0), PEN)
        with self.assertRaisesRegex(ValueError, "long"):
            build_features(BIN, [cramped], BIN.base_thickness)


    def test_alternate_ends_places_troughs_near_opposite_run_ends(self) -> None:
        one = Feature(
            "cradle", Zone.end(BIN, "x", 124.0), ROD,
            count=4, along="x", alternate_ends=True,
        )
        troughs = build_features(BIN, [one], BIN.base_thickness)
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
            build_features(BIN, [snug], BIN.base_thickness)



class BuildTests(unittest.TestCase):
    def _feature(self) -> Feature:
        return Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER, along="x")

    def test_a_fused_box_is_one_watertight_solid(self) -> None:
        fused = make_fused_box(BIN, [self._feature()], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)



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




    def test_auto_count_fills_the_zone_without_overrunning_it(self) -> None:
        one = self._row(count=None)
        troughs = build_features(BIN, [one], BIN.base_thickness)
        across = one.zone.depth
        span = (max(t.bounds[1][1] for t in troughs)
                - min(t.bounds[0][1] for t in troughs))
        self.assertLessEqual(span, across + 1e-3)
        # one more trough than auto chose would not have fit
        crowded = self._row(count=len(troughs) + 1)
        with self.assertRaises(ValueError):
            build_features(BIN, [crowded], BIN.base_thickness)





    def test_a_fatter_tool_fits_fewer_lanes(self) -> None:
        thin = build_features(
            BIN, [self._row(count=None, item=ROD, spacing=8.0)], BIN.base_thickness
        )
        fat = build_features(
            BIN,
            [self._row(count=None, item=Item.simple("Fat", 60.0, 20.0), spacing=8.0)],
            BIN.base_thickness,
        )
        self.assertLess(len(fat), len(thin))   # one solid per lane at this spacing




    def test_a_fused_row_of_many_cradles_is_one_solid(self) -> None:
        fused = make_fused_box(BIN, [self._row(count=5)], make_box(BIN))
        self.assertTrue(fused.is_watertight)
        self.assertEqual(len(fused.split(only_watertight=False)), 1)

    def test_a_removable_row_of_many_cradles_stands_on_one_plate(self) -> None:
        insert = make_fitted_insert(BIN, [self._row(count=5)])
        self.assertTrue(insert.is_watertight)
        self.assertAlmostEqual(insert.bounds[0][2], 0.0, places=6)
        self.assertEqual(len(insert.split(only_watertight=False)), 1)





class CradleAndDividerLayoutTests(unittest.TestCase):
    """Cradles and dividers sharing one bin - placement and assembly."""


    def test_a_cradle_overlapping_a_divider_is_refused(self) -> None:
        # Zones that overlap where the parts inside them do too: the bit's
        # trough runs the whole zone here, straight through the wall.
        cradle = Feature("cradle", Zone(-40.0, -20.0, 20.0, 20.0), BIT, count=1)
        wall = Feature("divider", Zone(-20.0, -20.0, 20.0, 20.0), along="y")
        self.assertTrue(
            feature_footprint(BIN, cradle, BIN.base_thickness)
            .overlaps(feature_footprint(BIN, wall, BIN.base_thickness))
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(BIN, [cradle, wall])

    def test_a_fused_divider_may_stand_in_a_cradle_zone_the_tool_leaves_open(self) -> None:
        # A 36 mm bit in a 60 mm zone leaves real floor past its trough, and
        # the wall stands clear of it, so fused to the floor this is fine.
        cradle = Feature("cradle", Zone(-40.0, -20.0, 20.0, 20.0), BIT)
        wall = Feature("divider", Zone(10.0, -20.0, 40.0, 20.0), along="y")
        self.assertTrue(cradle.zone.overlaps(wall.zone))
        check_layout(BIN, [cradle, wall], mode="fused")
        fused = make_fused_box(BIN, [cradle, wall], make_box(BIN))
        self.assertTrue(fused.is_watertight)

    def test_a_removable_insert_still_reserves_the_whole_zone(self) -> None:
        # Its base plate spans the bin floor, so a support keeps its zone.
        cradle = Feature("cradle", Zone(-40.0, -20.0, 20.0, 20.0), BIT)
        wall = Feature("divider", Zone(10.0, -20.0, 40.0, 20.0), along="y")
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(BIN, [cradle, wall], mode="separate")





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



    def test_an_unknown_holder_names_the_ones_that_exist(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown holder"):
            check_layout(BIN, [Feature("teleporter", Zone.whole(BIN))])


class FullSpanDividerTests(unittest.TestCase):
    """A divider that hugs the box's true wavy wall, not the safe rectangle."""


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
            solid = build_features(box, [one], box.base_thickness)[0]
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


    def test_the_base_gets_a_45_degree_chamfer_for_strength(self) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height = 8.0
        one = Feature("divider", zone, along="x",
                      options={"thickness": self.thickness, "height": height})
        mesh = build_features(self.box, [one], self.box.base_thickness)[0]
        self.assertTrue(mesh.is_watertight)
        from organizer_inserts import DIVIDER_CHAMFER
        floor = self.box.base_thickness
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
            build_features(self.box, [one], self.box.base_thickness)

    def test_a_straight_sloped_wall_keeps_uniform_thickness_while_it_leans(
        self,
    ) -> None:
        zone = Zone(-15.0, -self.thickness / 2.0, 15.0, self.thickness / 2.0)
        height, angle = 8.0, 20.0
        one = Feature(
            "divider", zone, along="x", wedge=False,
            options={"angle": angle, "thickness": self.thickness, "height": height},
        )
        mesh = build_features(self.box, [one], self.box.base_thickness)[0]
        self.assertTrue(mesh.is_watertight)
        lean = height * math.tan(math.radians(angle))
        # fractions kept above the base chamfer (DIVIDER_CHAMFER / height =
        # 0.125 here), which is a deliberate local exception to "uniform
        # thickness" covered by its own test below
        for frac in (0.2, 0.5, 0.95):
            z = self.box.base_thickness + frac * height
            lo, hi = self._cross_section(mesh, z, "x")
            self.assertAlmostEqual(hi - lo, self.thickness, places=3)
            # both faces slide together, proportionally to height
            self.assertAlmostEqual(lo, -self.thickness / 2.0 + frac * lean, places=2)
        from organizer_inserts import DIVIDER_CHAMFER
        # the shear does not change the area the chamfer's two 45-degree
        # corners add (Cavalieri's principle), so it is just chamfer^2 * run
        chamfer_volume = DIVIDER_CHAMFER ** 2 * 30.0
        self.assertAlmostEqual(mesh.volume, self.thickness * height * 30.0 + chamfer_volume, places=1)




    def test_an_angle_past_the_printable_limit_is_refused(self) -> None:
        zone = Zone(-15.0, -1.0, 15.0, 1.0)
        for bad in (46.0, -46.0, math.nan):
            one = Feature("divider", zone, along="x", options={"angle": bad})
            with self.assertRaisesRegex(ValueError, "45 degrees"):
                build_features(self.box, [one], self.box.base_thickness)



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


    def test_three_dividers_split_the_zone_into_four_equal_gaps(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        walls = build_features(
            self.box,
            [Feature("divider", zone, along="x", count=3,
                      options={"thickness": 1.0})],
            self.box.base_thickness,
        )
        self.assertEqual(len(walls), 3)
        centres = sorted((wall.bounds[0][1] + wall.bounds[1][1]) / 2.0 for wall in walls)
        gaps = [b - a for a, b in zip(centres, centres[1:])]
        self.assertAlmostEqual(gaps[0], gaps[1], places=3)
        # the outer gaps to the zone edges match the inner gap between walls
        self.assertAlmostEqual(centres[0] - zone.y0, gaps[0], places=3)
        self.assertAlmostEqual(zone.y1 - centres[-1], gaps[0], places=3)



    def test_an_explicit_spacing_too_tight_for_the_zone_is_refused(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        one = Feature(
            "divider", zone, along="x", count=3,
            options={"thickness": 1.0, "spacing": 100.0},
        )
        with self.assertRaisesRegex(ValueError, "need .* mm.*but the zone gives"):
            build_features(self.box, [one], self.box.base_thickness)

    def test_too_many_dividers_for_the_zone_is_refused(self) -> None:
        zone = Zone(-15.0, -2.0, 15.0, 2.0)
        one = Feature("divider", zone, along="x", count=5, options={"thickness": 2.0})
        with self.assertRaisesRegex(ValueError, "need at least"):
            build_features(self.box, [one], self.box.base_thickness)



class DividerScoopTests(unittest.TestCase):
    box = BoxSpec(48.0, 48.0, 40.0)
    base_z = box.base_thickness

    def divider(self, scoop=False, **options) -> Feature:
        values = {"count_x": 1, "count_y": 1, **options}
        if scoop:
            values["scoop"] = {"depth": 60.0}
        return Feature(
            "divider", Zone.whole(self.box), options=values, full_span=True,
        )

    def test_divider_exposes_stable_row_column_cells_and_usable_regions(self) -> None:
        cells = inserts.divider_cells(self.box, self.divider(), self.base_z)
        self.assertEqual(
            [cell.identity for cell in cells],
            ["r0c0", "r0c1", "r1c0", "r1c1"],
        )
        self.assertTrue(all(cell.zone.width > 0 and cell.zone.depth > 0 for cell in cells))
        self.assertLess(cells[0].zone.x1, cells[1].zone.x0)
        self.assertLess(cells[0].zone.y1, cells[2].zone.y0)




    def test_enabled_scoop_uses_shared_geometry_in_every_cell(self) -> None:
        solids = build_features(self.box, [self.divider(True)], self.base_z)
        cells = inserts.divider_cells(self.box, self.divider(), self.base_z)
        self.assertEqual(len(solids), 2 + len(cells))
        settings = inserts.scoop_settings(self.box, {"depth": 60.0}, self.base_z)
        for scoop, cell in zip(solids[-len(cells):], cells):
            region = inserts.scoop_region(cell.zone, settings)
            shared = inserts.build_scoop_region(
                (region.x0, region.y0, region.x1, region.y1),
                self.base_z, settings.height, "x",
            )
            self.assertTrue(np.allclose(scoop.bounds, shared.bounds))
            self.assertTrue(scoop.is_volume)

    def test_enabled_scoops_are_valid_in_the_finished_insert(self) -> None:
        solids = build_features(self.box, [self.divider(True)], self.base_z)
        self.assertEqual(len(solids), 6)
        self.assertTrue(all(solid.is_volume and solid.is_watertight for solid in solids))
        assembled = make_fitted_insert(
            self.box, [self.divider(True)],
        )
        self.assertTrue(assembled.is_volume)
        self.assertTrue(assembled.is_watertight)




    def test_divider_scoop_settings_round_trip_without_cell_targets(self) -> None:
        layout = Layout((self.divider(True),))
        rebuilt = layout_from_dict(layout_to_dict(layout))
        self.assertEqual(rebuilt.features[0].options["scoop"], {"depth": 60.0})




    def test_automatic_setting_cycles_are_rejected(self) -> None:
        rule = inserts.SettingInteraction
        with self.assertRaisesRegex(ValueError, "automatic setting loop"):
            inserts.register_setting_interactions("_loop_probe", (
                rule("a", "b", "auto-adjust", "probe", "first"),
                rule("b", "a", "derived", "probe", "second"),
            ))


class DividerBottomSlopeTests(unittest.TestCase):
    """Sloped tool-slot bottoms under a divider - see _divider_support_bottoms."""

    box = BoxSpec(80.0, 80.0, 40.0)

    def _walls_and_bottoms(self, zone, **kw):
        """(wall solids, added support-bottom solids) for one divider."""
        options = dict(kw.pop("options", {}))
        base = build_features(
            self.box,
            [Feature("divider", zone, count=kw.get("count"), along=kw.get("along", "x"),
                     full_span=kw.get("full_span", False),
                     options={k: v for k, v in options.items()
                              if not k.startswith(("bottom_", "reverse_", "alternate_",
                                                   "minimal_"))})],
            self.box.base_thickness,
        )
        full = build_features(
            self.box,
            [Feature("divider", zone, count=kw.get("count"), along=kw.get("along", "x"),
                     full_span=kw.get("full_span", False), options=options)],
            self.box.base_thickness,
        )
        return full[:len(base)], full[len(base):]

    @staticmethod
    def _ends(solid, axis):
        """Max z at the low and high face of ``solid`` along ``axis`` (0=x,1=y)."""
        verts = solid.vertices
        lo = verts[:, axis].min()
        hi = verts[:, axis].max()
        low_z = verts[np.isclose(verts[:, axis], lo, atol=1e-6)][:, 2].max()
        high_z = verts[np.isclose(verts[:, axis], hi, atol=1e-6)][:, 2].max()
        return low_z, high_z

    def test_legacy_and_explicit_zero_are_unchanged(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        legacy = build_features(
            self.box, [Feature("divider", zone, along="x", count=2)],
            self.box.base_thickness,
        )
        explicit = build_features(
            self.box,
            [Feature("divider", zone, along="x", count=2,
                     options={"bottom_angle": 0.0, "reverse_bottom": False,
                              "alternate_bottom": False, "minimal_bottom": False,
                              "bottom_supports": 3})],
            self.box.base_thickness,
        )
        self.assertEqual(len(legacy), len(explicit))
        for a, b in zip(legacy, explicit):
            self.assertTrue((a.bounds == b.bounds).all())
            self.assertAlmostEqual(a.volume, b.volume, places=6)



    def test_reverse_mirrors_the_slope(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        _w, plain = self._walls_and_bottoms(
            zone, count=1, along="x", options={"bottom_angle": 20.0})
        _w, flipped = self._walls_and_bottoms(
            zone, count=1, along="x",
            options={"bottom_angle": 20.0, "reverse_bottom": True})
        for solid in plain:
            low_z, high_z = self._ends(solid, 0)
            self.assertGreater(high_z, low_z + 1.0)
        for solid in flipped:
            low_z, high_z = self._ends(solid, 0)
            self.assertGreater(low_z, high_z + 1.0)

    def test_alternate_opposes_neighbouring_slots(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        _w, bottoms = self._walls_and_bottoms(
            zone, count=2, along="x",
            options={"bottom_angle": 20.0, "alternate_bottom": True})
        self.assertEqual(len(bottoms), 3)
        # ordered low to high across y (the divider's cross axis)
        bottoms = sorted(bottoms, key=lambda s: s.vertices[:, 1].mean())
        signs = []
        for solid in bottoms:
            low_z, high_z = self._ends(solid, 0)
            signs.append(1 if high_z > low_z else -1)
        self.assertEqual(signs, [1, -1, 1])



    def test_full_bottom_is_one_continuous_solid_per_slot(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        _w, bottoms = self._walls_and_bottoms(
            zone, count=2, along="x", options={"bottom_angle": 20.0})
        from organizer_inserts import BOTTOM_EMBED
        run, rise = 40.0, 40.0 * math.tan(math.radians(20.0))
        for solid in bottoms:
            # spans the whole tool-slot length with no break
            self.assertAlmostEqual(solid.bounds[0][0], zone.x0, places=6)
            self.assertAlmostEqual(solid.bounds[1][0], zone.x1, places=6)
            slot_width = solid.bounds[1][1] - solid.bounds[0][1]
            # a single continuous wedge: its volume is exactly the sloped prism
            # plus the thin slab embedded into the floor, nothing missing
            expected = slot_width * (0.5 * run * rise + BOTTOM_EMBED * run)
            self.assertAlmostEqual(solid.volume, expected, delta=expected * 0.01)


    def test_crossbar_tops_sit_on_the_requested_slope_plane(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        angle = 25.0
        _w, bars = self._walls_and_bottoms(
            zone, count=1, along="x",
            options={"bottom_angle": angle, "minimal_bottom": True,
                     "bottom_supports": 3})
        span, rise = 40.0, 40.0 * math.tan(math.radians(angle))
        for bar in bars:
            verts = bar.vertices
            top = verts[:, 2].max()
            centre = verts[:, 0].mean()
            frac = (centre - zone.x0) / span
            plane_z = self.box.base_thickness + frac * rise
            # top follows the plane, give or take half a bar's own run of slope
            self.assertAlmostEqual(top, plane_z, delta=1.0)






    def test_over_80_and_non_finite_values_fail_clearly(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        for bad in (80.5, -80.5, math.nan):
            one = Feature("divider", zone, along="x", count=1,
                          options={"bottom_angle": bad})
            with self.assertRaisesRegex(ValueError, "within 80 degrees either way"):
                build_features(self.box, [one], self.box.base_thickness)



    def test_options_survive_the_saved_design_schema(self) -> None:
        zone = Zone(-15.0, -20.0, 15.0, 20.0)
        layout = Layout(
            (Feature("divider", zone, along="x", count=2,
                     options={"bottom_angle": 22.5, "reverse_bottom": True,
                              "alternate_bottom": True, "minimal_bottom": True,
                              "bottom_supports": 5}),),
            "fused", EDITOR_SNAP,
        )
        data = layout_to_dict(layout)
        self.assertEqual(data["version"], 1)
        restored = layout_from_dict(data).features[0].options
        self.assertEqual(restored["bottom_angle"], 22.5)
        self.assertIs(restored["reverse_bottom"], True)
        self.assertIs(restored["alternate_bottom"], True)
        self.assertIs(restored["minimal_bottom"], True)
        self.assertEqual(restored["bottom_supports"], 5)


    def test_fused_and_removable_outputs_are_one_watertight_component(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        for minimal in (False, True):
            options = {"bottom_angle": 22.0, "minimal_bottom": minimal}
            feature = Feature("divider", zone, along="x", count=2, options=options)
            fused = make_fused_box(self.box, [feature], make_box(self.box))
            self.assertTrue(fused.is_watertight)
            self.assertEqual(fused.split(only_watertight=False).__len__(), 1)
            removable = make_fitted_insert(self.box, [feature])
            self.assertTrue(removable.is_watertight)
            self.assertEqual(
                removable.split(only_watertight=False).__len__(), 1)





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
        solid = build_features(self.box, [one], self.box.base_thickness)[0]
        self.assertTrue(solid.is_watertight)
        lean = self.height * math.tan(math.radians(self.angle))
        half_t = self.thickness / 2.0
        worst = 0.0
        for frac in (0.02, 0.3, 0.6, 0.98):
            z = self.box.base_thickness + frac * self.height
            # the wedge keeps its width up top and widens at the floor: the
            # leaning face sweeps from -half_t at the base to -half_t + lean
            # at the top, while the trailing face sits vertical at half_t + lean
            y_low, y_high = -half_t + frac * lean, half_t + lean
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
            solid = build_features(self.box, [one], self.box.base_thickness)[0]
            self.assertTrue(solid.is_watertight, overrides)



    def test_still_refuses_an_angle_past_the_limit_and_a_paper_thin_wall(self) -> None:
        with self.assertRaisesRegex(ValueError, "45 degrees"):
            build_features(
                self.box, [self._feature(options={"angle": 46.0})], self.box.base_thickness
            )
        with self.assertRaisesRegex(ValueError, "0.4 mm thick"):
            build_features(
                self.box,
                [self._feature(options={"thickness": 0.3, "height": 30.0, "angle": 30.0})],
                self.box.base_thickness,
            )

    def test_inside_a_removable_insert_it_clips_flush_to_the_straight_plate_edge(
        self,
    ) -> None:
        insert = make_fitted_insert(self.box, [self._feature()])
        footprint = insert_footprint(self.box, "separate")
        self.assertAlmostEqual(insert.bounds[1][0], footprint.bounds[2], places=3)
        self.assertAlmostEqual(insert.bounds[0][0], footprint.bounds[0], places=3)



class RegistryTests(unittest.TestCase):


    def test_feature_definitions_are_complete_and_authoritative(self) -> None:
        definitions = inserts.feature_definitions()
        self.assertEqual(
            {one.kind for one in definitions},
            {"cradle", "nest", "bore", "post", "pocket", "divider",
             "slot", "steps", "scoop", "text"},
        )
        for definition in definitions:
            self.assertIs(definition.builder, inserts.FEATURE_BUILDERS[definition.kind])
            self.assertIs(definition.default_resolver, inserts.FEATURE_DEFAULTS[definition.kind])
            self.assertTrue(definition.title)
            self.assertTrue(definition.display)
            self.assertTrue(definition.description)
            self.assertTrue(definition.icon)
            self.assertTrue(all(option.value_type for option in definition.options))

    def test_registry_carries_instance_limits_and_palette_visibility(self) -> None:
        @inserts.feature("test_hidden_single", max_instances=1, palette_visible=False)
        def build(box, spec_feature, base_z):
            return []

        try:
            definition = inserts.feature_definition("test_hidden_single")
            self.assertEqual(definition.max_instances, 1)
            self.assertFalse(definition.palette_visible)
        finally:
            inserts.FEATURE_BUILDERS.pop("test_hidden_single", None)
            inserts.FEATURE_DEFINITIONS.pop("test_hidden_single", None)
        with self.assertRaisesRegex(ValueError, "at least 1"):
            inserts.feature("test_bad_limit", max_instances=0)


    def test_remaining_auto_setting_relationships_are_registered(self) -> None:
        for kind in ("cradle", "nest", "bore", "post", "pocket", "divider",
                     "slot", "scoop", "text"):
            self.assertTrue(inserts.setting_interactions(kind), kind)
        bore_rules = inserts.setting_interactions("bore")
        self.assertTrue(any(
            rule.source == "item.profile" and rule.target == "angle"
            and rule.effect == "reset" for rule in bore_rules
        ))
        for kind in ("pocket", "bore", "slot"):
            shell_rules = inserts.setting_interactions(kind)
            self.assertTrue(any(
                rule.source == "depth" and rule.target == "height"
                and rule.effect == "constraint" for rule in shell_rules
            ))
            self.assertTrue(any(
                rule.source == "height" and rule.target == "depth"
                and rule.effect == "constraint" for rule in shell_rules
            ))
        self.assertTrue(inserts.setting_interactions("bore", "height"))

    def test_registered_option_types_drive_browser_value_coercion(self) -> None:
        self.assertIs(inserts.option_value("minimal_bottom", "false", "divider"), False)
        self.assertEqual(inserts.option_value("division_level", "rim", "divider"), "rim")
        self.assertEqual(inserts.option_value("columns", "3", "bore"), 3)
        self.assertEqual(
            inserts.option_value("scoop", '{"depth":45,"cells":["r0c0"]}', "divider"),
            {"depth": 45, "cells": ["r0c0"]},
        )


class OtherHoldersTests(unittest.TestCase):
    def test_fix21_quantity_defaults_limits_and_occurrence_count(self) -> None:
        legacy = photo_nest()
        self.assertIsNone(legacy.count)
        self.assertEqual(len(inserts.nest_occurrences(legacy)), 1)
        repeated = photo_nest(count=4)
        self.assertEqual([one.index for one in inserts.nest_occurrences(repeated)], list(range(4)))
        with self.assertRaises(ValueError):
            photo_nest(count=0)
        with self.assertRaisesRegex(ValueError, "between 1 and 20"):
            photo_nest(count=21)




    def test_fix21_required_zone_contains_every_finished_occurrence_envelope(self) -> None:
        one = photo_nest(count=4, rotation=90.0, alternate_ends=True,
                         options={"repeat_spacing_percent": 75})
        required = inserts.nest_required_zone(one)
        for occurrence in inserts.nest_occurrences(one):
            footprint = affinity.translate(
                nest_impl._nest_single_required_footprint(one, occurrence.rotation),
                xoff=occurrence.x, yoff=occurrence.y,
            )
            x0, y0, x1, y1 = footprint.bounds
            self.assertLessEqual(required.x0, x0 + 1e-7)
            self.assertLessEqual(required.y0, y0 + 1e-7)
            self.assertGreaterEqual(required.x1, x1 - 1e-7)
            self.assertGreaterEqual(required.y1, y1 - 1e-7)




    def test_fix21_serialization_and_old_save_defaults_preserve_behavior(self) -> None:
        one = photo_nest(
            count=3, rotation=37.0, alternate_ends=True,
            options={"repeat_spacing_percent": 50},
        )
        rebuilt = layout_from_dict(layout_to_dict(Layout((one,)))).features[0]
        self.assertEqual(rebuilt.count, 3)
        self.assertTrue(rebuilt.alternate_ends)
        self.assertEqual(rebuilt.rotation, 37.0)
        self.assertEqual(rebuilt.options["repeat_spacing_percent"], 50)

        old_data = layout_to_dict(Layout((photo_nest(rotation=27.0),)))
        old = old_data["features"][0]
        old.pop("count", None)
        old.pop("alternate_ends", None)
        old["options"].pop("repeat_spacing_percent", None)
        legacy = layout_from_dict(old_data).features[0]
        self.assertIsNone(legacy.count)
        self.assertFalse(legacy.alternate_ends)
        self.assertEqual(legacy.rotation, 27.0)
        self.assertAlmostEqual(inserts.nest_repeat_gap(legacy), 2.0)
        self.assertEqual(len(inserts.nest_occurrences(legacy)), 1)


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
            for solid in build_features(BIN, [one], BIN.base_thickness):
                self.assertTrue(solid.is_watertight, one.kind)
                self.assertGreater(solid.volume, 0.0, one.kind)

    def test_a_bore_makes_holes(self) -> None:
        pencil = inserts.LIBRARY["pencil"]
        zone = Zone(-60.0, -20.0, -20.0, 20.0)
        bored = build_features(BIN, [Feature("bore", zone, pencil)], BIN.base_thickness)[0]
        height = bored.bounds[1][2] - bored.bounds[0][2]
        solid = trimesh.creation.box(extents=(zone.width, zone.depth, height))
        self.assertLess(bored.volume, solid.volume)

    def test_pocket_interior_cavity_and_chamfer(self) -> None:
        zone = Zone(-10.0, -15.0, 10.0, 15.0)
        pocket = Feature("pocket", zone, options={"height": 10.0, "wall": 2.0})
        mesh = build_features(BIN, [pocket], BIN.base_thickness)[0]
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][0], zone.x0 - 0.5, places=2)
        self.assertAlmostEqual(mesh.bounds[1][0], zone.x1 + 0.5, places=2)
        self.assertAlmostEqual(mesh.bounds[0][1], zone.y0 - 0.5, places=2)
        self.assertAlmostEqual(mesh.bounds[1][1], zone.y1 + 0.5, places=2)
        self.assertAlmostEqual(mesh.bounds[1][2] - mesh.bounds[0][2], 10.0, places=3)

    def test_photo_nest_uses_the_true_outside_contour(self) -> None:
        shaped = photo_nest()
        rectangle = photo_nest(contour=((-30, -10), (30, -10), (30, 10), (-30, 10)))
        shaped_mesh = build_features(BIN, [shaped], BIN.base_thickness)[0]
        rectangle_mesh = build_features(BIN, [rectangle], BIN.base_thickness)[0]
        self.assertNotAlmostEqual(shaped_mesh.volume, rectangle_mesh.volume, places=3)
        self.assertTrue(shaped_mesh.is_watertight)


    def test_cavity_depth_leaves_printable_base(self) -> None:
        one = photo_nest(options={"clearance": 0.0, "rim": 3.0, "depth": 12.0})
        meshes = build_features(BIN, [one], BIN.base_thickness)
        mesh = inserts.union(meshes)
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][2], BIN.base_thickness, places=5)
        self.assertAlmostEqual(mesh.bounds[1][2], BIN.base_thickness + 12.0, places=5)
        self.assertLess(mesh.volume, one.zone.width * one.zone.depth * 12.0)
        too_deep = photo_nest(options={
            "clearance": 0.0, "rim": 3.0,
            "depth": BIN.z - BIN.base_thickness + 0.1,
        })
        # A Raised Wall taller than the rim is a legitimate Fused-mode holder
        # now (spec: shallow-fused-above-rim) - the central assembly policy,
        # not this builder, is the one that still bounds it outside Fused.
        with self.assertRaisesRegex(ValueError, "rises above the bin rim"):
            build_features(BIN, [too_deep], BIN.base_thickness, mode="separate")







    def test_push_out_builds_a_low_press_end_and_four_mm_raised_support(self) -> None:
        one = photo_nest(
            contour=((-30, -10), (30, -10), (30, 10), (-30, 10)),
            options={"lift_assist": "push_out"},
        )
        mesh = build_features(BIN, [one], BIN.base_thickness)[0]
        support_top = BIN.base_thickness + inserts.NEST_PUSH_DEPTH
        support_faces = [
            face for face in mesh.triangles
            if all(abs(float(point[2]) - support_top) < 1e-4 for point in face)
            and float(np.cross(face[1] - face[0], face[2] - face[0])[2]) > 0.0
        ]
        self.assertTrue(support_faces)
        support_centres = np.asarray([face.mean(axis=0) for face in support_faces])
        self.assertLess(float(support_centres[:, 0].max()), 15.0)
        self.assertLess(float(support_centres[:, 0].min()), -25.0)
        self.assertAlmostEqual(
            mesh.bounds[1][2], BIN.base_thickness + 8.0 + inserts.NEST_PUSH_DEPTH,
            places=3,
        )
        self.assertTrue(mesh.is_watertight)



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
                build_features(BIN, [oversized], BIN.base_thickness)



class BoreEnhancementTests(unittest.TestCase):
    ZONE = Zone(-40.0, -40.0, 40.0, 40.0)

    def _bore(self, item, **options):
        one = Feature("bore", self.ZONE, item, options=options)
        return build_features(BIN, [one], BIN.base_thickness)[0]

    def test_hex_bit_profiles_size_hole_and_depth_for_the_bit(self) -> None:
        for profile, hold in inserts.HEX_BIT_HOLD.items():
            item = Item.simple("bit", 25.0, 6.35, profile=profile)
            mesh = self._bore(item)
            self.assertTrue(mesh.is_watertight, profile)
            # Height is the hold depth plus the standard 2 mm floor under it.
            self.assertAlmostEqual(
                mesh.bounds[1][2] - mesh.bounds[0][2], hold + 2.0, places=3
            )

    def test_hex_bit_hole_is_a_hex_socket_not_a_round_one(self) -> None:
        flats = inserts.HEX_BIT_FLATS + inserts.HEX_BIT_CLEARANCE
        hold = inserts.HEX_BIT_HOLD["hex_bit_short"]
        hex_bit = self._bore(Item.simple("bit", 25.0, 6.35, profile="hex_bit_short"))
        # A hex socket reaches past the inscribed circle at its six corners, so
        # it removes more than a round hole of the same across-flats size.
        round_hole = self._bore(
            Item("nozzle", (Segment(25.0, flats),), profile="round", clearance=0.0),
            depth=hold, height=hold + 2.0,
        )
        self.assertLess(hex_bit.volume, round_hole.volume)

    def test_explicit_columns_and_rows_make_that_many_holes(self) -> None:
        item = Item.simple("nozzle", 20.0, 6.0)
        few = self._bore(item, columns=2, rows=2)
        many = self._bore(item, columns=4, rows=3)
        self.assertLess(few.volume, trimesh.creation.box(
            extents=(self.ZONE.width, self.ZONE.depth,
                     few.bounds[1][2] - few.bounds[0][2])).volume)
        # More holes remove more material.
        self.assertGreater(few.volume, many.volume)


    def _bottom_hole_centre_x(self, mesh):
        """Mean x of the hole-surface vertices in the lowest slice of the block -
        the part of a leaning hole that has walked furthest sideways."""
        verts = mesh.vertices
        near_axis = np.hypot(verts[:, 0], verts[:, 1]) < 12.0
        low = verts[:, 2] < BIN.base_thickness + 4.0
        picked = verts[near_axis & low]
        self.assertGreater(len(picked), 0)
        return float(picked[:, 0].mean())

    def test_an_angle_leans_the_holes(self) -> None:
        item = Item.simple("tube", 20.0, 6.0)
        straight = self._bore(item, columns=1, rows=1, angle=0)
        leaned = self._bore(item, columns=1, rows=1, angle=35)
        self.assertTrue(leaned.is_watertight)
        # Deep in the block the hole has walked sideways once it leans.
        self.assertAlmostEqual(self._bottom_hole_centre_x(straight), 0.0, delta=0.3)
        self.assertGreater(self._bottom_hole_centre_x(leaned), 0.8)



    def test_a_lean_past_the_printable_limit_is_refused(self) -> None:
        item = Item.simple("tube", 20.0, 6.0)
        with self.assertRaises(ValueError):
            self._bore(item, rows=1, angle=71)


    def test_square_and_diamond_profiles_keep_their_distinct_orientation(self) -> None:
        zone = Zone(-10.0, -10.0, 10.0, 10.0)
        meshes = {}
        for profile in ("square", "square_axis"):
            item = Item.simple("tool", 20.0, 6.0, profile=profile)
            meshes[profile] = build_features(
                BIN,
                [Feature("bore", zone, item, options={"columns": 1, "rows": 1})],
                BIN.base_thickness,
            )[0]
        legacy_xy = np.asarray(meshes["square"].vertices)[:, :2]
        axis_xy = np.asarray(meshes["square_axis"].vertices)[:, :2]
        legacy_near = legacy_xy[np.max(np.abs(legacy_xy), axis=1) < 6.0]
        axis_near = axis_xy[np.max(np.abs(axis_xy), axis=1) < 6.0]
        self.assertTrue(any(abs(x) < 1e-6 and abs(y) > 4.0 for x, y in legacy_near))
        self.assertTrue(any(abs(x) > 3.0 and abs(y) > 3.0 for x, y in axis_near))



class FeatureMinFootprintTests(unittest.TestCase):
    """``feature_min_footprint`` - the size the editor's 'fit this part to its
    contents' button resizes a zone to."""

    def mn(self, one):
        return inserts.feature_min_footprint(BIN, one, BIN.base_thickness)

    def test_bore_grid_is_columns_by_rows_at_pitch(self) -> None:
        item = Item("n", (Segment(20.0, 6.0),), profile="round")
        one = Feature("bore", Zone(-60.0, -60.0, 60.0, 60.0), item,
                      options={"columns": 3, "rows": 2, "wall": 1.6})
        pitch = item.held(6.0) + 1.6            # 6.4 + 1.6 = 8
        self.assertEqual(self.mn(one), (3 * pitch, 2 * pitch))

    def test_bore_auto_grid_wraps_what_currently_fits(self) -> None:
        item = Item("n", (Segment(20.0, 6.0),), profile="round")
        one = Feature("bore", Zone(-20.0, -12.0, 20.0, 12.0), item,
                      options={"wall": 1.6})
        width, depth = self.mn(one)
        self.assertLessEqual(width, 40.0 + 1e-6)
        self.assertLessEqual(depth, 24.0 + 1e-6)
        self.assertGreater(width, 0.0)




    def test_slot_tightens_the_across_axis_keeps_the_run(self) -> None:
        one = Feature("slot", Zone(-40.0, -30.0, 40.0, 30.0), count=3,
                      along="x")
        width, depth = self.mn(one)
        self.assertEqual(width, 80.0)           # run axis untouched
        self.assertLess(depth, 60.0)            # across axis trimmed to 3 slots


    def test_kinds_with_no_contents_return_none(self) -> None:
        cases = [
            Feature("pocket", Zone(-20.0, -20.0, 20.0, 20.0)),
            Feature("steps", Zone(-20.0, -20.0, 20.0, 20.0)),
            Feature("divider", Zone(-20.0, -2.0, 20.0, 2.0)),
            Feature("text", Zone(-20.0, -6.0, 20.0, 6.0), options={"text": "M3"}),
        ]
        for one in cases:
            self.assertIsNone(self.mn(one), one.kind)


class KeepOutTests(unittest.TestCase):
    def test_a_cradle_stays_clear_of_the_connector_arms(self) -> None:
        limit = inserts.connector_keep_out(BIN)
        self.assertAlmostEqual(limit, BIN.z - ConnectorSpec().arm_depth)
        ribs = build_features(
            BIN, [Feature("cradle", Zone.end(BIN, "x", 88.0), DRIVER)], BIN.base_thickness
        )
        for rib in ribs:
            self.assertLess(rib.bounds[1][2], limit)

    def test_a_tall_wall_edge_feature_is_refused_but_an_interior_one_is_not(self) -> None:
        whole = Zone.whole(BIN)
        edge = Feature(
            "divider", Zone(whole.x0, -10.0, whole.x0 + 2.0, 10.0),
            along="y", options={"height": BIN.z - BIN.base_thickness - 1.0},
        )
        with self.assertRaisesRegex(ValueError, "connector can seat"):
            build_features(BIN, [edge], BIN.base_thickness)
        interior = Feature(
            "divider", Zone(-1.0, -10.0, 1.0, 10.0),
            along="y", options={"height": BIN.z - BIN.base_thickness - 1.0},
        )
        self.assertTrue(build_features(BIN, [interior], BIN.base_thickness))

    def test_a_removable_edge_divider_is_sized_at_its_installed_height(self) -> None:
        whole = Zone.whole(BIN)
        edge = Feature(
            "divider", Zone(whole.x0, -10.0, whole.x0 + 2.0, 10.0), along="y"
        )
        insert = make_fitted_insert(BIN, [edge])
        seated_top = insert.bounds[1][2] + BIN.base_thickness
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



from organizer_inserts._bore import WALL_ONLY_FOOT


class BoreWallOnlyTests(unittest.TestCase):
    ZONE = Zone(-40.0, -30.0, 40.0, 30.0)
    PROFILES = ("round", "hex", "square", "square_axis", "hex_bit_short", "hex_bit_long")

    def _item(self, profile="round"):
        return Item("tube", (Segment(25.0, 30.0),), profile=profile, clearance=0.0)

    def _build(self, item=None, zone=None, **options):
        # ``wall_style`` picks Straight / Wavy Walls Only (the two styles).
        wall_style = options.pop("wall_style", "wavy")
        options = {"bore_style": f"walls_{wall_style}", "height": 10.0, "wall": 1.6, **options}
        one = Feature("bore", zone or self.ZONE, item or self._item(), options=options)
        return build_features(BIN, [one], BIN.base_thickness)[0]

    def test_missing_style_is_base_straight_and_matches_explicit(self) -> None:
        item = self._item()
        legacy = build_features(BIN, [Feature("bore", self.ZONE, item)], BIN.base_thickness)[0]
        explicit = build_features(
            BIN, [Feature("bore", self.ZONE, item, options={"bore_style": "base_straight"})],
            BIN.base_thickness)[0]
        np.testing.assert_allclose(legacy.bounds, explicit.bounds)
        self.assertAlmostEqual(legacy.volume, explicit.volume, places=3)
        self.assertAlmostEqual(legacy.bounds[1][0] - legacy.bounds[0][0], self.ZONE.width)

    def test_wall_only_is_a_sleeve_from_base_z_not_a_block(self) -> None:
        mesh = self._build(depth=500.0)     # stale Full Base depth is ignored
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][2], BIN.base_thickness, places=4)
        self.assertAlmostEqual(mesh.bounds[1][2], BIN.base_thickness + 10.0, places=4)
        self.assertLess(mesh.bounds[1][0] - mesh.bounds[0][0], self.ZONE.width / 2.0)
        block = self.ZONE.width * self.ZONE.depth * 10.0
        self.assertLess(mesh.volume, block / 10.0)

    def test_walls_depth_creates_a_raised_local_stop(self) -> None:
        # Fix 078: an explicit Depth shorter than Height stops the open
        # cavity there, leaving a solid support-free pedestal below it.
        through_floor = self._build(wall_style="straight", height=20.0, walls_depth=20.0)
        shallow = self._build(wall_style="straight", height=20.0, walls_depth=6.0)
        self.assertTrue(shallow.is_watertight)
        self.assertGreater(shallow.volume, through_floor.volume)
        pedestal_point = np.array([[0.0, 0.0, shallow.bounds[0][2] + 1.0]])
        self.assertTrue(shallow.contains(pedestal_point)[0])
        self.assertFalse(through_floor.contains(pedestal_point)[0])

    def test_multiple_walls_only_holes_keep_each_raised_stop_and_open_top(self) -> None:
        zone = Zone(-60.0, -25.0, 60.0, 25.0)
        for wall_style in ("straight", "wavy"):
            with self.subTest(wall_style=wall_style):
                mesh = self._build(zone=zone, columns=3, rows=1, wall_style=wall_style,
                                   height=20.0, walls_depth=6.0)
                self.assertTrue(mesh.is_watertight)
                for x in (-31.6, 0.0, 31.6):
                    self.assertTrue(mesh.contains([[x, 0.0, BIN.base_thickness + 1.0]])[0])
                    self.assertFalse(mesh.contains([[x, 0.0, BIN.base_thickness + 18.0]])[0])

    def test_missing_walls_depth_keeps_legacy_through_floor(self) -> None:
        legacy = self._build(wall_style="straight", height=20.0)  # no walls_depth at all
        explicit = self._build(wall_style="straight", height=20.0, walls_depth=20.0)
        np.testing.assert_allclose(legacy.bounds, explicit.bounds, atol=1e-4)
        self.assertAlmostEqual(legacy.volume, explicit.volume, places=2)

    def test_walls_depth_out_of_range_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Depth"):
            self._build(wall_style="straight", height=10.0, walls_depth=15.0)
        with self.assertRaisesRegex(ValueError, "Depth"):
            self._build(wall_style="straight", height=10.0, walls_depth=0.0)
        with self.assertRaisesRegex(ValueError, "Depth"):
            self._build(wall_style="straight", height=10.0, walls_depth=float("nan"))

    def test_clear_opening_is_never_reduced(self) -> None:
        for wall_style in ("straight", "wavy"):
            mesh = self._build(wall_style=wall_style)
            radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
            self.assertGreaterEqual(radii.min(), 15.0 - 1e-6, wall_style)
            # The wavy trough reaches the clear envelope, it never digs in.
            self.assertLess(radii.min(), 15.01, wall_style)

    def test_wavy_varies_and_uses_wavefinity_constants(self) -> None:
        wavy = self._build(wall_style="wavy")
        straight = self._build(wall_style="straight")
        radii = lambda mesh: np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
        # Upright sleeve only (above the strengthening foot) uses the wall constants.
        upright = lambda mesh: np.hypot(
            *mesh.vertices[mesh.vertices[:, 2] > mesh.bounds[0][2] + WALL_ONLY_FOOT + 0.05, :2].T
        ).max()
        outer = lambda mesh: radii(mesh).max()
        self.assertAlmostEqual(
            upright(wavy), 15.0 + 2.0 * WAVE_AMPLITUDE + wall_depth_for(1.6), delta=0.02)
        self.assertAlmostEqual(upright(straight), 15.0 + 1.6, delta=0.02)
        # The whole mesh reaches one extra WALL_ONLY_FOOT at the base.
        self.assertAlmostEqual(outer(wavy), upright(wavy) + WALL_ONLY_FOOT, delta=0.02)
        self.assertAlmostEqual(outer(straight), upright(straight) + WALL_ONLY_FOOT, delta=0.02)
        inner = lambda mesh: radii(mesh)[radii(mesh) < 15.0 + 2.0 * WAVE_AMPLITUDE + 0.05]
        self.assertGreater(inner(wavy).max() - inner(wavy).min(), WAVE_AMPLITUDE)
        self.assertLess(inner(straight).max() - inner(straight).min(), 0.01)



    def test_wall_thickness_grows_the_sleeve_and_defaults_to_the_bin_wall(self) -> None:
        thin = self._build(wall=0.8, wall_style="straight")
        thick = self._build(wall=2.4, wall_style="straight")
        self.assertGreater(thick.bounds[1][0], thin.bounds[1][0])
        one = Feature("bore", self.ZONE, self._item(),
                      options={"bore_style": "walls_wavy", "height": 10.0})
        self.assertEqual(inserts.resolved_options(BIN, one, BIN.base_thickness)["wall"], BIN.wall)
        full = Feature("bore", self.ZONE, self._item())
        self.assertEqual(inserts.resolved_options(BIN, full, BIN.base_thickness)["wall"], 1.6)

    def test_touching_sleeves_merge_and_every_opening_stays_open(self) -> None:
        zone = Zone(-60.0, -25.0, 60.0, 25.0)
        for wall_style in ("straight", "wavy"):
            mesh = self._build(zone=zone, columns=3, rows=1, wall_style=wall_style)
            self.assertTrue(mesh.is_watertight)
            pitch = 30.0 + 1.6
            for column in (-1, 0, 1):
                centre = np.array([column * pitch, 0.0])
                vertices = mesh.vertices[:, :2] - centre
                inside = np.hypot(vertices[:, 0], vertices[:, 1]) < 15.0 - 1e-6
                self.assertFalse(inside.any(), (wall_style, column))





    def test_minimum_footprint_and_explicit_counts_use_the_true_outer_shell(self) -> None:
        for wall_style in ("straight", "wavy"):
            one = Feature("bore", self.ZONE, self._item(), options={
                "bore_style": f"walls_{wall_style}", "wall": 1.6})
            width, depth = inserts.feature_min_footprint(BIN, one, BIN.base_thickness)
            reach = 1.6 if wall_style == "straight" else 2.0 * WAVE_AMPLITUDE + wall_depth_for(1.6)
            reach += WALL_ONLY_FOOT     # Wall Only's strengthening foot
            self.assertAlmostEqual(width, 30.0 + 2.0 * reach, delta=0.01)
            self.assertAlmostEqual(depth, 30.0 + 2.0 * reach, delta=0.01)
        # Two sleeves need 31.6 more; a zone a hair short of that fits only one.
        env = wall_only_envelope("round", 30.0, 1.6, "wavy", foot=True)
        two = env["zone_span_x"] + env["pitch_x"]
        tight = Zone(-(two - 0.2) / 2.0, -25.0, (two - 0.2) / 2.0, 25.0)
        one = Feature("bore", tight, self._item(), options={
            "bore_style": "walls_wavy", "wall": 1.6, "height": 10.0})
        # Counts are always explicit; an unset count is one hole, never a fill.
        self.assertEqual(inserts.resolved_options(BIN, one, BIN.base_thickness)["columns"], 1.0)
        roomy = Zone(-(two + 0.2) / 2.0, -25.0, (two + 0.2) / 2.0, 25.0)
        self.assertEqual(_bore_grid(BIN, replace(
            one, zone=roomy, options={**one.options, "columns": 2}), BIN.base_thickness)["columns"], 2)
        with self.assertRaises(ValueError):
            self._build(zone=tight, columns=2, rows=1)


class BoreWavyBaseTests(unittest.TestCase):
    """Fix 030 / Fix 068: Base - Wavy Walls, bin sizing, and automatic bin-wall joining."""

    def _item(self, diameter=30.0):
        return Item("tube", (Segment(25.0, diameter),), profile="round", clearance=0.0)

    def _one(self, zone, style="base_wavy", diameter=30.0, **options):
        options = {"bore_style": style, "height": 10.0, "wall": 1.6, **options}
        if style == "base_wavy":
            options.setdefault("depth", 6.0)
        return Feature("bore", zone, self._item(diameter), options=options)

    def _touching(self, size=40.0, foot=False):
        """A bin and a hole whose outer envelope exactly meets the usable floor."""
        box = replace(BIN, x=size, y=size)
        inside = box.usable_inside[0]
        reach = _wall_only_shell_reach(1.6, "wavy") + (WALL_ONLY_FOOT if foot else 0.0)
        clear = inside - 2.0 * reach
        diameter = clear * math.cos(math.pi / _round_clear_sides(clear, "wavy"))
        env = wall_only_envelope("round", diameter, 1.6, "wavy", foot=foot)
        self.assertAlmostEqual(env["span_x"], inside, places=6)
        return box, diameter, Zone.whole(box)

    def test_wavy_base_is_a_solid_base_with_wavy_holes(self) -> None:
        env = wall_only_envelope("round", 30.0, 1.6, "wavy")
        zone = Zone(-env["span_x"] / 2.0, -env["span_y"] / 2.0,
                    env["span_x"] / 2.0, env["span_y"] / 2.0)
        mesh = build_features(BIN, [self._one(zone)], BIN.base_thickness)[0]
        extent = mesh.bounds[1] - mesh.bounds[0]
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(extent[0], env["span_x"], places=4)
        self.assertAlmostEqual(extent[1], env["span_y"], places=4)
        self.assertAlmostEqual(mesh.bounds[0][2], BIN.base_thickness, places=4)
        self.assertAlmostEqual(mesh.bounds[1][2], BIN.base_thickness + 10.0, places=4)
        radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
        self.assertGreaterEqual(radii[radii < 20.0].min(), 15.0 - 1e-6)   # opening stays open
        self.assertLess(mesh.volume, extent[0] * extent[1] * 10.0)         # a hole was cut
        self.assertGreater(mesh.volume, 0.5 * extent[0] * extent[1] * 10.0)  # but it is a block

    def test_the_four_styles_and_their_default(self) -> None:
        self.assertEqual(inserts._bore.BORE_STYLES, (
            "base_straight", "base_wavy", "walls_straight", "walls_wavy"))
        zone = Zone(-30.0, -30.0, 30.0, 30.0)
        one = Feature("bore", zone, self._item())
        self.assertEqual(
            inserts.resolved_options(BIN, one, BIN.base_thickness)["bore_style"], "base_straight")
        self.assertEqual(_bore_grid(BIN, self._one(zone), BIN.base_thickness)["wall_style"], "wavy")
        self.assertEqual(
            _bore_grid(BIN, self._one(zone, style="walls_straight"),
                       BIN.base_thickness)["wall_style"], "straight")


    def test_bin_is_the_smallest_legal_size_around_the_whole_grid(self) -> None:
        for columns, rows in ((1, 1), (3, 2)):
            zone = Zone(-60.0, -50.0, 60.0, 50.0)
            one = self._one(zone, style="walls_wavy", columns=columns, rows=rows,
                            xy_size_mode="bin_to_bore")
            envelope = bore_envelope_zone(BIN, one, BIN.base_thickness)
            env = wall_only_envelope("round", 30.0, 1.6, "wavy", foot=True)
            self.assertAlmostEqual(
                envelope.width, env["span_x"] + (columns - 1) * env["pitch_x"], places=6)
            x, y = bore_bin_minimum(BIN, [one], BIN.base_thickness)
            self.assertGreaterEqual(replace(BIN, x=x).usable_inside[0], envelope.width - 1e-6)
            self.assertGreaterEqual(replace(BIN, y=y).usable_inside[1], envelope.depth - 1e-6)
            if x > 8.0:
                self.assertLess(replace(BIN, x=x - 8.0).usable_inside[0], envelope.width)
            if y > 8.0:
                self.assertLess(replace(BIN, y=y - 8.0).usable_inside[1], envelope.depth)



    def test_wavy_base_joins_every_wall_it_reaches_without_touching_the_outside(self) -> None:
        outer = wavy_outer_polygon(self._touching()[0]).bounds
        # Wall Only's physical envelope includes the base foot, so it is sized
        # (and joins the wall) by that foot-inclusive reach.
        for style in ("base_wavy", "walls_wavy"):
            box, diameter, whole = self._touching(foot=style == "walls_wavy")
            one = self._one(whole, style=style, diameter=diameter)
            mesh = build_features(box, [one], box.base_thickness)[0]
            self.assertGreater(mesh.bounds[1][0], whole.x1 + 0.5, style)
            self.assertLess(mesh.bounds[0][0], whole.x0 - 0.5, style)
            if style == "base_wavy":
                # A round wavy sleeve only touches where its wave peaks line up;
                # the Base block itself touches every side.
                self.assertGreater(mesh.bounds[1][1], whole.y1 + 0.5, style)
                self.assertLess(mesh.bounds[0][1], whole.y0 - 0.5, style)
            self.assertLessEqual(mesh.bounds[1][0], outer[2] - JOIN_SKIN + 1e-6, style)
            self.assertGreaterEqual(mesh.bounds[0][0], outer[0] + JOIN_SKIN - 1e-6, style)
            radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
            self.assertGreaterEqual(
                radii[radii < diameter / 2.0 + 0.5].min(), diameter / 2.0 - 1e-6, style)


    def test_base_straight_now_joins_the_wall_it_touches(self) -> None:
        # Fix 078: Base - Straight Walls was previously excluded from wall-join
        # eligibility (JOIN_STYLES = UPRIGHT_STYLES); a fused Bore that touches
        # the bin wall now follows the real interior wall contour there too.
        box = replace(BIN, x=64.0, y=48.0)
        inside_x = box.usable_inside[0]
        zone = Zone(-inside_x / 2.0, -15.0, inside_x / 2.0, 15.0)
        one = self._one(zone, style="base_straight", diameter=10.0, depth=6.0)
        outer = wavy_outer_polygon(box).bounds
        mesh = build_features(box, [one], box.base_thickness)[0]
        # The block reaches past its own nominal zone toward both touched
        # walls, but never past the true outside face (JOIN_SKIN margin).
        self.assertGreater(mesh.bounds[1][0], zone.x1 + 0.5)
        self.assertLess(mesh.bounds[0][0], zone.x0 - 0.5)
        self.assertLessEqual(mesh.bounds[1][0], outer[2] - JOIN_SKIN + 1e-3)
        self.assertGreaterEqual(mesh.bounds[0][0], outer[0] + JOIN_SKIN - 1e-3)
        # The hole itself stays fully open where the join material was added
        # (excluding the mouth chamfer's own single apex vertex on the axis).
        radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
        near_hole = radii[(radii > 1.0) & (radii < 5.5)]
        self.assertGreaterEqual(near_hole.min(), 5.0 - 1e-6)

    def test_fused_base_fills_true_cavity_strip_only_on_touched_sides(self) -> None:
        box = replace(BIN, x=64.0, y=48.0)
        whole = Zone.whole(box)
        cavity = wavy_cavity_polygon(box)
        mid_z = box.base_thickness + 5.0

        def strip_probes(zone, side):
            # Probe the actual cavity outside the nominal Base rectangle, not
            # just its bounds. Multiple samples per wave catch scalloped gaps.
            nominal = shapely_box(zone.x0, zone.y0, zone.x1, zone.y1)
            strip = cavity.difference(nominal)
            x0, y0, x1, y1 = cavity.bounds
            points = []
            for x in np.arange(x0 + 0.1, x1, 0.3):
                for y in np.arange(y0 + 0.1, y1, 0.5):
                    if side == "right" and not (x > zone.x1 + 0.05 and zone.y0 + 1 < y < zone.y1 - 1):
                        continue
                    if side == "left" and not (x < zone.x0 - 0.05 and zone.y0 + 1 < y < zone.y1 - 1):
                        continue
                    if side == "back" and not (y > zone.y1 + 0.05 and zone.x0 + 1 < x < zone.x1 - 1):
                        continue
                    if side == "front" and not (y < zone.y0 - 0.05 and zone.x0 + 1 < x < zone.x1 - 1):
                        continue
                    point = Point(float(x), float(y))
                    if strip.contains(point) and cavity.boundary.distance(point) > 0.05:
                        points.append((float(x), float(y), mid_z))
            self.assertGreater(len(points), 10, side)
            return np.asarray(points)

        # Both Base families must fill all four true-wall strips, with the
        # central Bore still open at a safe mid-height.
        for style in ("base_straight", "base_wavy"):
            with self.subTest(style=style):
                one = self._one(whole, style=style, diameter=10.0, depth=6.0)
                mesh = build_features(box, [one], box.base_thickness)[0]
                for side in ("right", "left", "back", "front"):
                    probes = strip_probes(whole, side)
                    self.assertTrue(mesh.contains(probes).all(), (style, side))
                self.assertFalse(mesh.contains([[0.0, 0.0, mid_z]])[0])

        # Reaching only right/back may not broaden the left/front edges.
        partial = Zone(-15.0, -12.0, whole.x1, whole.y1)
        one = self._one(partial, style="base_straight", diameter=10.0, depth=6.0)
        mesh = build_features(box, [one], box.base_thickness)[0]
        for side in ("right", "back"):
            self.assertTrue(mesh.contains(strip_probes(partial, side)).all(), side)
        self.assertGreater(mesh.bounds[0][0], whole.x0 + 1.0)
        self.assertGreater(mesh.bounds[0][1], whole.y0 + 1.0)
        right_only = Zone(-15.0, -12.0, whole.x1, 12.0)
        one = self._one(right_only, style="base_straight", diameter=10.0, depth=6.0)
        mesh = build_features(box, [one], box.base_thickness)[0]
        self.assertTrue(mesh.contains(strip_probes(right_only, "right")).all())
        self.assertLess(mesh.bounds[1][1], whole.y1 - 1.0)
        self.assertGreater(mesh.bounds[0][0], whole.x0 + 1.0)

    def test_final_side_opening_cut_wins_over_joined_base(self) -> None:
        box = replace(BIN, x=48.0, y=48.0, side_openings=SideOpeningSpec(
            enabled=True, sides=("front",), shape="square", size="medium"))
        one = self._one(Zone.whole(box), style="base_straight", diameter=10.0, depth=6.0)
        joined = make_fused_box(box, [one], make_box(box))
        cut = apply_side_openings(box, joined)
        opening = [[0.0, -box.half_y + box.wall_depth / 2.0, box.base_thickness + 5.0]]
        self.assertTrue(joined.contains(opening)[0])
        self.assertFalse(cut.contains(opening)[0])

    def test_removable_insert_never_claims_to_join_the_bin_wall(self) -> None:
        box, diameter, whole = self._touching()
        mesh = build_features(
            box, [self._one(whole, diameter=diameter)],
            box.base_thickness + inserts.BASE_PLATE, mode="separate")[0]
        self.assertLessEqual(mesh.bounds[1][0], whole.x1 + 1e-5)
        self.assertGreaterEqual(mesh.bounds[0][0], whole.x0 - 1e-5)


    def test_joined_bore_in_the_connector_band_is_a_clear_error(self) -> None:
        box, diameter, whole = self._touching()
        one = self._one(whole, diameter=diameter, height=box.z - 1.0, depth=8.0)
        with self.assertRaisesRegex(ValueError, "touching the wall"):
            build_features(box, [one], box.base_thickness)


class BoreAutoModeTests(unittest.TestCase):
    def _bore(self, **options):
        return inserts.Feature(
            "bore", inserts.Zone(-12.0, -12.0, 12.0, 12.0),
            item=inserts.LIBRARY["hex_driver"], options=options,
        )

    def test_legacy_bore_without_flags_stays_one_by_one(self):
        grid = _bore_grid(BIN, self._bore(), BIN.base_thickness)
        self.assertEqual((grid["columns"], grid["rows"]), (1, 1))

    def test_counts_are_explicit_and_never_fill_the_base(self):
        # Fix 068: Auto Grid is retired. A big Base still holds the counts it
        # was given, and a retired flag is dropped instead of filling it.
        one = inserts.Feature(
            "bore", inserts.Zone(-40.0, -30.0, 40.0, 30.0),
            item=inserts.LIBRARY["hex_driver"], options={"auto_grid": True},
        )
        one = inserts.normalize_bore_modes(BIN, one, BIN.base_thickness)
        self.assertNotIn("auto_grid", one.options)
        grid = _bore_grid(BIN, one, BIN.base_thickness)
        self.assertEqual((grid["columns"], grid["rows"]), (1, 1))
        grid = _bore_grid(BIN, replace(one, options={**one.options, "columns": 3, "rows": 2}),
                          BIN.base_thickness)
        self.assertEqual((grid["columns"], grid["rows"]), (3, 2))

    def test_bore_to_bin_modes_follow_the_bin(self):
        # Fix 034 G1: a Base Bore filling the bin touches every wall, so
        # Auto Height resolves to the connector keep-out limit exactly like a
        # manual height must. In a bin tall enough for that cap, it fills it.
        one = self._bore(xy_size_mode="bore_to_bin", height_size_mode="bore_to_bin", height=5.0)
        box = BoxSpec(160.0, 88.0, 56.0)
        fixed = inserts.normalize_bore_modes(box, one, box.base_thickness)
        whole = inserts.layout_zone(box)
        self.assertEqual(fixed.zone, whole)
        self.assertNotIn("height", fixed.options)          # the hidden manual height never wins
        height = inserts.resolved_options(box, fixed, box.base_thickness)["height"]
        expected_top = inserts.connector_keep_out(box)
        self.assertAlmostEqual(height, expected_top - box.base_thickness, places=6)
        inserts.build_features(
            box, [fixed], box.base_thickness, whole, "fused",
        )

    def test_height_bore_to_bin_refuses_when_the_legal_cap_is_too_short(self):
        # Fix 034 G1: when the connector keep-out leaves too little room for
        # this Bore's minimum geometry, Auto Height raises a clear,
        # actionable error instead of silently building an illegal bin.
        one = self._bore(xy_size_mode="bore_to_bin", height_size_mode="bore_to_bin")
        fixed = inserts.normalize_bore_modes(BIN, one, BIN.base_thickness)
        with self.assertRaisesRegex(ValueError, "make the bin taller or move the Bore"):
            inserts.resolved_options(BIN, fixed, BIN.base_thickness)


class BoreAutoBaseZoneTests(unittest.TestCase):
    def test_mode_conversion_keeps_exact_derived_zone(self):
        from organizer_app import convert_layout_mode
        # Fix 034 G1: bore_to_bin fills the whole Base, so this Bore touches
        # every wall and Auto Height's connector keep-out cap applies - use a
        # box tall enough for that legal cap to hold the hex driver's hole.
        box = BoxSpec(128.0, 88.0, 60.0)
        one = inserts.Feature(
            "bore", inserts.Zone(-8.0, -8.0, 8.0, 8.0),
            item=inserts.LIBRARY["hex_driver"],
            options={"xy_size_mode": "bore_to_bin", "height_size_mode": "bore_to_bin"},
        )
        for mode in ("fused", "cartridge"):
            layout = convert_layout_mode(box, [one], mode)
            self.assertEqual(layout.features[0].zone, inserts.layout_zone(box, mode))


class BoreFix068Tests(unittest.TestCase):
    """Fix 068: four styles, persistent sizing modes, access clearance, floor-reaching cavity."""

    ITEM = Item("tube", (Segment(25.0, 12.0),), profile="round", clearance=0.0)
    ZONE = Zone(-14.0, -14.0, 14.0, 14.0)

    def _bore(self, zone=None, **options):
        return Feature("bore", zone or self.ZONE, self.ITEM, options=options)

    # -- Edge Mount screwdriver-access clearance ---------------------------------

    def _edge_box(self, z=80.0, **edge):
        from organizer_engine import EdgeMountSpec
        spec = EdgeMountSpec(side="front", holes_enabled=True, label_enabled=False,
                             standoff_ribs_enabled=False, **edge)
        return BoxSpec(64.0, 64.0, z, edge_mount=spec)

    def _auto_height_top(self, box, bore=None):
        normalize_bore_modes = inserts.normalize_bore_modes
        base_z = box.base_thickness
        one = normalize_bore_modes(box, bore or self._bore(
            bore_style="base_straight", height_size_mode="bore_to_bin", depth=10.0), base_z)
        return base_z + inserts.resolved_options(box, one, base_z)["height"]

    def test_auto_height_ends_two_mm_below_the_lowest_access_cutter(self) -> None:
        from organizer_edge_mount import (
            _print_safe_profile_radius, edge_mount_access_lowest_z, edge_mount_hole_plan)
        box = self._edge_box()
        holes = edge_mount_hole_plan(box)
        lowest = min(h["z_mm"] - _print_safe_profile_radius(h["access_diameter_mm"] / 2.0)
                     for h in holes)
        self.assertAlmostEqual(edge_mount_access_lowest_z(box), lowest, places=9)
        # The access cutter crosses the interior, so the Bore need not touch the wall.
        self.assertAlmostEqual(self._auto_height_top(box), lowest - 2.0, places=6)
        # No screw access -> the normal limit (the bin rim for an interior Bore).
        plain = BoxSpec(64.0, 64.0, 80.0)
        self.assertAlmostEqual(self._auto_height_top(plain), plain.z, places=6)


    def test_auto_height_uses_the_larger_access_diameter(self) -> None:
        from organizer_edge_mount import _print_safe_profile_radius
        box = self._edge_box(access_diameter_mm=12.0)
        lowest = (box.z - box.edge_mount.top_offset_mm) - _print_safe_profile_radius(6.0)
        self.assertAlmostEqual(self._auto_height_top(box), lowest - 2.0, places=6)

    def test_manual_height_is_not_capped_by_the_access_rule(self) -> None:
        box = self._edge_box()
        one = self._bore(bore_style="base_straight", height=box.z - box.base_thickness - 1.0,
                         depth=10.0)
        resolved = inserts.resolved_options(box, one, box.base_thickness)
        self.assertAlmostEqual(resolved["height"], box.z - box.base_thickness - 1.0)

    def test_auto_height_rejects_clearly_when_the_access_hole_leaves_no_room(self) -> None:
        box = self._edge_box(z=34.0)
        with self.assertRaisesRegex(ValueError, "screwdriver access"):
            self._auto_height_top(box, self._bore(
                bore_style="base_straight", height_size_mode="bore_to_bin", depth=20.0))

    # -- floor-reaching Base cavity ----------------------------------------------



    # -- style / mode contract ---------------------------------------------------


    def test_counts_resize_the_minimum_footprint(self) -> None:
        for style in ("base_straight", "base_wavy", "walls_straight", "walls_wavy"):
            sizes = [inserts.feature_min_footprint(
                BIN, self._bore(bore_style=style, columns=c, rows=1), BIN.base_thickness)
                for c in (1, 3)]
            self.assertGreater(sizes[1][0], sizes[0][0] + 1.0, style)
            self.assertAlmostEqual(sizes[1][1], sizes[0][1], places=6, msg=style)

    def test_bin_to_bore_bin_holds_the_base_zone_and_follows_edits(self) -> None:
        one = self._bore(bore_style="base_straight", xy_size_mode="bin_to_bore", columns=3)
        need = inserts.feature_min_footprint(BIN, one, BIN.base_thickness)
        zone = Zone(-need[0] / 2.0, -need[1] / 2.0, need[0] / 2.0, need[1] / 2.0)
        small = inserts.bore_bin_minimum(BIN, [replace(one, zone=zone)], BIN.base_thickness)
        wide = replace(one, zone=zone, options={**one.options, "columns": 8})
        wider_need = inserts.feature_min_footprint(BIN, wide, BIN.base_thickness)
        wide = replace(wide, zone=Zone(-wider_need[0] / 2.0, -wider_need[1] / 2.0,
                                        wider_need[0] / 2.0, wider_need[1] / 2.0))
        bigger = inserts.bore_bin_minimum(BIN, [wide], BIN.base_thickness)
        self.assertGreater(bigger[0], small[0])
        for (x, y), feature in ((small, replace(one, zone=zone)), (bigger, wide)):
            inside = replace(BIN, x=x, y=y).usable_inside
            self.assertGreaterEqual(inside[0], feature.zone.width - 1e-6)
            self.assertLess(replace(BIN, x=x - 8.0, y=y).usable_inside[0], feature.zone.width)
        # Manual Bores never ask the bin to resize.
        self.assertIsNone(inserts.bore_bin_minimum(BIN, [self._bore(bore_style="base_straight")],
                                                   BIN.base_thickness))

    # -- Walls Only hugs the bin on every side -----------------------------------



class SlotRackTests(unittest.TestCase):
    def test_slot_rack_builds_watertight_mesh_inside_bounds(self) -> None:
        zone = Zone(-20.0, -15.0, 20.0, 15.0)
        one = Feature("slot", zone, options={"height": 16.0, "depth": 12.0, "thickness": 4.0, "angle": 20.0})
        base = BIN.base_thickness
        solids = build_features(BIN, [one], base)
        self.assertEqual(len(solids), 1)
        mesh = solids[0]
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][2], base, places=3)
        self.assertAlmostEqual(mesh.bounds[1][2], base + 16.0, places=3)


    def test_slot_rack_rejects_excessive_angle_or_depth(self) -> None:
        zone = Zone(-15.0, -15.0, 15.0, 15.0)
        with self.assertRaisesRegex(ValueError, "angle <= 45"):
            build_features(BIN, [Feature("slot", zone, options={"angle": 50.0})], BIN.base_thickness)
        with self.assertRaisesRegex(ValueError, "depth must be less than height"):
            build_features(BIN, [Feature("slot", zone, options={"depth": 16.0, "height": 16.0})], BIN.base_thickness)


class TieredStepsTests(unittest.TestCase):
    def test_steps_builds_watertight_mesh(self) -> None:
        zone = Zone(-20.0, -20.0, 20.0, 20.0)
        one = Feature("steps", zone, count=3, along="x", options={"height": 15.0})
        base = BIN.base_thickness
        solids = build_features(BIN, [one], base)
        self.assertEqual(len(solids), 1)
        mesh = solids[0]
        self.assertTrue(mesh.is_watertight)
        self.assertAlmostEqual(mesh.bounds[0][2], base, places=3)
        self.assertAlmostEqual(mesh.bounds[1][2], base + 15.0, places=3)


    def test_steps_rejects_invalid_count(self) -> None:
        zone = Zone(-10.0, -10.0, 10.0, 10.0)
        with self.assertRaisesRegex(ValueError, "count must be positive"):
            Feature("steps", zone, count=0)


def text_part(said="M3", zone=Zone(-20.0, -6.0, 20.0, 6.0), **options):
    return Feature("text", zone, options={"text": said, **options})


class TextPartTests(unittest.TestCase):
    """Legacy Text remains readable while canonical Text owns a destination."""

    def test_text_is_sunk_into_the_floor_it_stands_on(self) -> None:
        base = BIN.base_thickness
        mesh = inserts.build_text(BIN, text_part(), base)[0]
        self.assertTrue(mesh.is_watertight)
        # Flush with the floor, filling the depth immediately beneath it.
        self.assertAlmostEqual(mesh.bounds[1][2], base, places=6)
        self.assertAlmostEqual(mesh.bounds[0][2], base - inserts.TEXT_DEPTH, places=6)

    def test_raised_text_stands_on_the_floor_instead(self) -> None:
        base = BIN.base_thickness
        mesh = inserts.build_text(BIN, text_part(raised=True), base)[0]
        self.assertAlmostEqual(mesh.bounds[0][2], base, places=6)
        self.assertAlmostEqual(mesh.bounds[1][2], base + inserts.TEXT_DEPTH, places=6)



    def test_a_hand_set_letter_height_is_honoured_but_never_overflows(self) -> None:
        roomy = Zone(-40.0, -15.0, 40.0, 15.0)
        self.assertAlmostEqual(
            inserts.text_fitted(text_part(zone=roomy, cap_height=6.0))[0], 6.0,
            places=6,
        )
        # Asking for more than the zone holds shrinks to what fits.
        tight = Zone(-12.0, -5.0, 12.0, 5.0)
        self.assertLess(
            inserts.text_fitted(text_part(zone=tight, cap_height=20.0))[0], 20.0
        )

    def test_neighbours_are_judged_on_the_ink_not_the_whole_box(self) -> None:
        """A short word in a wide box should not push a holder away."""
        one = text_part("I", zone=Zone(-30.0, -6.0, 30.0, 6.0))
        ink = feature_footprint(BIN, one, BIN.base_thickness)
        self.assertLess(ink.width, 30.0)
        self.assertLess(ink.width, one.zone.width)

    def test_two_base_text_parts_cannot_share_a_bin(self) -> None:
        left = text_part("M3", zone=Zone(-40.0, 4.0, -10.0, 16.0))
        right = text_part("M4", zone=Zone(10.0, 4.0, 40.0, 16.0))
        with self.assertRaisesRegex(ValueError, "Only one Label"):
            check_layout(BIN, [left, right], base_z=BIN.base_thickness)

    def test_two_rim_text_parts_on_different_sides_cannot_share_a_bin(self) -> None:
        # Fix 078: at most one rim Text total, not one per rim side.
        back = text_part("M3", zone=Zone(-20.0, 6.0, 20.0, 15.0), level="rim", rim_side="back")
        front = text_part("M4", zone=Zone(-20.0, -15.0, 20.0, -6.0), level="rim", rim_side="front")
        with self.assertRaisesRegex(ValueError, "Only one rim Label"):
            check_layout(BIN, [back, front], base_z=BIN.base_thickness)

    def test_overlapping_text_and_holder_is_refused(self) -> None:
        said = text_part("M3", zone=Zone(-20.0, -6.0, 20.0, 6.0))
        post = Feature("post", Zone(-8.0, -8.0, 8.0, 8.0))
        with self.assertRaisesRegex(ValueError, "overlap"):
            check_layout(BIN, [said, post], base_z=BIN.base_thickness)

    def test_text_survives_a_json_round_trip(self) -> None:
        one = text_part("BOLTS", auto=True, quarter_turns=1, raised=True)
        back = layout_from_dict(layout_to_dict(Layout((one,), "fused"))).features[0]
        self.assertEqual(back.kind, "text")
        self.assertEqual(back.options["text"], "BOLTS")
        self.assertNotIn("auto", back.options)
        self.assertTrue(back.options["text_v2"])
        self.assertEqual(back.options["quarter_turns"], 1)
        self.assertTrue(back.options["raised"])
        self.assertEqual(back.zone.centre, one.zone.centre)










if __name__ == "__main__":
    unittest.main()
