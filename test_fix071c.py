"""Focused, non-browser checks for Fix 071C's saved geometry and API paths."""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from shapely.geometry import box as rectangle
from shapely.ops import unary_union

import organizer_app as app
import organizer_inserts as inserts
from organizer_engine import BoxSpec, top_label_surface_z
from organizer_inserts._bore import _join_tabs
from organizer_inserts._divider import divider_defaults, divider_division_texts
from organizer_inserts._text import canonical_text_feature, rim_text_geometry
from wavefinity_web import (
    apply_feature_payload, default_design, default_feature_payload,
    draft_payload, duplicate_feature_payload, preview_payload,
)


def text_feature(box: BoxSpec, *, level="base", side="back", raised=False,
                 depth=0.4, value="M3", cap=10.0):
    zone = inserts.Zone(-box.x / 2 + 2, -box.y / 2 + 2,
                        box.x / 2 - 2, box.y / 2 - 2)
    return canonical_text_feature(inserts.Feature("text", zone, options={
        "text": value, "level": level, "rim_side": side, "raised": raised,
        "depth": depth, "cap_height": cap, "quarter_turns": 0,
        "text_v2": True,
    }))


class TextContractTests(unittest.TestCase):
    def test_all_types_and_depths_use_one_physical_builder(self):
        box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)
        for level in ("base", "rim"):
            for raised in (False, True):
                for depth in (0.2, 0.4, 0.6, 0.8):
                    with self.subTest(level=level, raised=raised, depth=depth):
                        one = text_feature(box, level=level, raised=raised, depth=depth)
                        glyph = inserts.build_text(box, one, box.base_thickness)[0]
                        self.assertTrue(glyph.is_volume)
                        self.assertAlmostEqual(glyph.extents[2], depth, places=5)
                        if level == "rim":
                            ledge, same, cap, surface = rim_text_geometry(box, one)
                            self.assertTrue(ledge.is_volume)
                            self.assertAlmostEqual(same.bounds[1][2], glyph.bounds[1][2], places=5)
                            self.assertLessEqual(glyph.bounds[1][2], top_label_surface_z(box) + 1e-6)
                            self.assertGreater(surface - ledge.extents[2], box.base_thickness)
                        else:
                            expected_top = box.base_thickness + (depth if raised else 0)
                            self.assertAlmostEqual(glyph.bounds[1][2], expected_top, places=5)

    def test_new_text_and_legacy_save_are_canonical(self):
        design = default_design()
        design["box"].update(x=64, y=64, z=40)
        fresh = default_feature_payload({"design": design, "kind": "text"})["feature"]
        self.assertEqual(fresh["options"]["level"], "base")
        self.assertFalse(fresh["options"]["raised"])
        self.assertEqual(fresh["options"]["depth"], 0.4)
        self.assertNotIn("auto", fresh["options"])
        old = {**fresh, "zone": [-15, -8, 15, 8],
               "options": {"text": "M3", "auto": True, "quarter_turns": 1}}
        design["layout"]["features"] = [old]
        box, layout, *_ = app.design_from_dict(design)
        saved = app.design_to_dict(box, layout)
        options = saved["layout"]["features"][0]["options"]
        self.assertTrue(options["text_v2"])
        self.assertNotIn("auto", options)
        self.assertGreaterEqual(options["cap_height"], 0.1)
        self.assertIn(options["quarter_turns"], (0, 1, 2, 3))

    def test_real_text_routes_and_multiple_rim_pick_identity(self):
        design = default_design()
        design["box"].update(x=64, y=64, z=40, base_thickness=1.2, standard_base=False)
        new = default_feature_payload({"design": design, "kind": "text"})["feature"]
        new["options"].update(text="M3", cap_height=10, depth=0.6)
        draft = draft_payload({"design": design, "feature": new})
        self.assertEqual(draft["feature"]["options"]["level"], "base")
        self.assertTrue(draft["geometry"])
        applied = apply_feature_payload({"design": design, "feature": draft["feature"]})
        design = applied["design"]
        self.assertEqual(len(design["layout"]["features"]), 1)
        duplicated = duplicate_feature_payload({"design": design, "index": 0})
        design = duplicated["design"]
        self.assertEqual(design["layout"]["features"][1]["options"]["level"], "rim")
        second = duplicate_feature_payload({"design": design, "index": 1})
        design = second["design"]
        sides = [one["options"]["rim_side"] for one in design["layout"]["features"][1:]]
        self.assertEqual(sides, ["back", "front"])
        preview = json.loads(json.dumps(preview_payload({"design": design})))
        self.assertFalse(preview["feature_errors"])
        ids = {tuple(face["pick"].items()) for face in preview["geometry"] if face["pick"]}
        self.assertIn((("type", "saved"), ("index", 1)), ids)
        self.assertIn((("type", "saved"), ("index", 2)), ids)
        self.assertFalse(any(face["pick"] for face in preview["geometry"]
                             if face["kind"] == "preview_pick_proxy"))
        box, layout, label, name, location, scoop = app.design_from_dict(design)
        saved = app.design_to_dict(box, layout, label, name, location, scoop)
        self.assertEqual(saved["layout"]["features"], design["layout"]["features"])
        with tempfile.TemporaryDirectory() as folder:
            result = app.generate_organizer_files(box, layout, Path(folder))
            self.assertEqual(result["text_objects"], ["M3", "M3 2", "M3 3"])

    def test_destination_conflicts_and_floor_space(self):
        box = BoxSpec(64, 64, 40)
        base = text_feature(box)
        with self.assertRaisesRegex(ValueError, "Only one Text"):
            inserts.Layout((base, base), "fused").validate(box)
        back = text_feature(box, level="rim", side="back")
        with self.assertRaisesRegex(ValueError, "Only one Text"):
            inserts.Layout((back, back), "separate").validate(box)
        floor = inserts.Feature("post", inserts.Zone(-12, 4, 12, 20))
        for mode in ("fused", "separate", "cartridge"):
            with self.subTest(mode=mode):
                inserts.Layout((back, floor), mode).validate(box)


class RimTextInteractionTests(unittest.TestCase):
    def setUp(self):
        self.box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)

    def rim(self, side="back", **kw):
        return text_feature(self.box, level="rim", side=side, cap=5.0, **kw)

    def test_same_wall_side_opening_and_edge_mount_block_only_that_wall(self):
        from organizer_engine import EdgeMountSpec, SideOpeningSpec
        opened = replace(self.box, side_openings=SideOpeningSpec(True, "curved", ("back",)))
        blocked = inserts.Layout((self.rim("back"),), "fused")
        with self.assertRaisesRegex(ValueError, "Side Opening"):
            app.preview_geometry(opened, "", blocked.features, "fused")
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "Side Opening"):
            app.generate_organizer_files(opened, blocked, Path(folder))
        legal = inserts.Layout((self.rim("left"),), "fused")
        app.preview_geometry(opened, "", legal.features, "fused")
        mount = replace(self.box, edge_mount=EdgeMountSpec(side="front", label_enabled=True,
                                                           label_type="separate", label_text="X"))
        with self.assertRaisesRegex(ValueError, "Edge Mount"):
            app.preview_geometry(mount, "", (self.rim("front"),), "fused")
        app.preview_geometry(mount, "", (self.rim("back"),), "fused")

    def test_inside_handle_blocks_only_real_overlap(self):
        from organizer_engine import LiftGrabberSpec
        handled = BoxSpec(48, 48, 40, wall=1.0, lift_grabbers=LiftGrabberSpec(enabled=True, location="sides"))
        with self.assertRaisesRegex(ValueError, "handle"):
            app.preview_geometry(handled, "", (text_feature(handled, level="rim", side="left", cap=5.0),), "fused")
        # The handle sits on the X walls; a Front/Back label is a different wall.
        app.preview_geometry(handled, "", (text_feature(handled, level="rim", side="back", cap=5.0),), "fused")

    def test_rim_text_reserves_no_floor_in_any_layout_mode(self):
        rim = self.rim("back")
        for mode, zone in (("fused", inserts.Zone(-12, 4, 12, 20)),
                           ("separate", inserts.Zone(-12, 4, 12, 20)),
                           ("cartridge", inserts.Zone(-28, 20, -20, 28))):
            with self.subTest(mode=mode):
                floor = inserts.Feature("post", zone)
                inserts.Layout((rim, floor), mode).validate(self.box)

    def test_removable_mode_keeps_rim_text_on_the_shell(self):
        rim = self.rim("back")
        base = text_feature(self.box, cap=8.0)
        with tempfile.TemporaryDirectory() as folder:
            result = app.generate_organizer_files(
                self.box, inserts.Layout((rim, base), "separate"), Path(folder))
        self.assertEqual(result["box_text_objects"], ["M3"])
        self.assertEqual(result["text_objects"], ["M3"])
        self.assertNotIn("Text", app.summarize_interior_parts(inserts.Layout((rim,), "separate")))

    def test_raised_rim_text_never_rises_above_the_safe_datum(self):
        safe = top_label_surface_z(self.box)
        for depth in (0.2, 0.4, 0.6, 0.8):
            with self.subTest(depth=depth):
                one = self.rim("back", raised=True, depth=depth)
                ledge, glyph, _cap, surface = rim_text_geometry(self.box, one)
                self.assertAlmostEqual(surface, safe - depth, places=5)
                self.assertAlmostEqual(float(ledge.bounds[1][2]), surface, places=4)
                self.assertLessEqual(float(glyph.bounds[1][2]), safe + 1e-6)
                self.assertAlmostEqual(float(glyph.bounds[0][2]), surface, places=4)

    def test_rim_text_and_divider_rim_shelf_overlap_is_refused(self):
        divider = app.default_feature(self.box, "divider")
        divider = replace(divider, options={**divider.options, "label_divisions": True,
                                            "division_level": "rim", "division_side": "back",
                                            "division_labels": ["A", "B"]})
        with self.assertRaisesRegex(ValueError, "Divider rim label"):
            app.preview_geometry(self.box, "", (divider, self.rim("back")), "fused")

    def test_inventory_and_report_understand_rim_text(self):
        layout = inserts.Layout((self.rim("back"), self.rim("left", value="A1"),
                                 text_feature(self.box, value="B2")), "fused")
        row = app.inventory_bin_record(self.box, layout)
        self.assertIn("M3 (rim back)", row["label"])
        self.assertIn("A1 (rim left)", row["label"])
        self.assertIn("B2 (base)", row["label"])
        self.assertNotIn("floor", row["label"])
        report = app.text_report(self.box, self.rim("left", raised=True, depth=0.6), 0.0)
        self.assertEqual(report["text_type"], "At rim — Raised")
        self.assertEqual(report["rim_side"], "left")
        self.assertAlmostEqual(report["surface_z_mm"], top_label_surface_z(self.box) - 0.6, places=3)

    def test_legacy_global_rim_label_migrates_once(self):
        design = default_design()
        design["box"].update(x=64, y=64, z=40)
        design["label"] = "M3"
        design["label_position"] = "left"
        box, layout, label, _name, location, _scoop = app.design_from_dict(design)
        rims = [one for one in layout.features if one.kind == "text" and one.options["level"] == "rim"]
        self.assertEqual(len(rims), 1)
        self.assertEqual(rims[0].options["rim_side"], "left")
        self.assertEqual(label, "")
        saved = app.design_to_dict(box, layout, label, "", location, False)
        again = app.design_from_dict(saved)
        self.assertEqual(len([one for one in again[1].features if one.kind == "text"]), 1)
        self.assertEqual(app.design_to_dict(*again), saved)


class PreviewLayerTests(unittest.TestCase):
    def test_inlaid_text_is_drawn_above_its_flush_surface_without_moving_geometry(self):
        box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)
        one = text_feature(box, depth=0.4)
        glyph = inserts.build_text(box, one, box.base_thickness)[0]
        self.assertAlmostEqual(float(glyph.bounds[1][2]), box.base_thickness, places=4)
        design = app.design_to_dict(box, inserts.Layout((one,), "fused"))
        preview = preview_payload({"design": design})
        text_layers = {face["layer"] for face in preview["geometry"] if face["kind"].endswith("text")}
        floor_layers = {face["layer"] for face in preview["geometry"] if face["kind"] == "floor"}
        self.assertTrue(text_layers)
        self.assertGreater(min(text_layers), max(floor_layers))

    def test_divider_base_and_rim_labels_are_drawn_above_their_surfaces(self):
        box = BoxSpec(64, 64, 40)
        one = app.default_feature(box, "divider")
        for level in ("base", "rim"):
            with self.subTest(level=level):
                labelled = replace(one, options={**one.options, "label_divisions": True,
                                                 "division_level": level,
                                                 "division_labels": ["A", "B"]})
                design = app.design_to_dict(box, inserts.Layout((labelled,), "fused"))
                layers = {face["layer"] for face in preview_payload({"design": design})["geometry"]
                          if face["kind"].startswith("feature")}
                self.assertIn(2, layers)


class TextMigrationTests(unittest.TestCase):
    def setUp(self):
        self.box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)

    def legacy(self, **options):
        return inserts.Feature("text", inserts.Zone(-14, -5, 6, 9),
                               options={"text": "M3", "quarter_turns": 1, **options})

    def test_legacy_off_centre_text_keeps_its_centre_and_size(self):
        old = self.legacy(auto=False, cap_height=8.0)
        canonical = canonical_text_feature(old)
        for got, wanted in zip(canonical.zone.centre, old.zone.centre):
            self.assertAlmostEqual(got, wanted, places=6)
        from organizer_inserts._text import text_fitted
        # Old boxes never let a hand-set height overflow; the size it really had is kept.
        self.assertAlmostEqual(canonical.options["cap_height"], text_fitted(old)[0], places=6)
        self.assertEqual(canonical.options["quarter_turns"], 1)
        self.assertTrue(canonical.options["text_v2"])
        self.assertNotIn("auto", canonical.options)
        again = canonical_text_feature(canonical)
        for got, wanted in zip(again.zone.polygon.bounds, canonical.zone.polygon.bounds):
            self.assertAlmostEqual(got, wanted, places=6)
        self.assertEqual(again.options, canonical.options)

    def test_legacy_text_without_height_resolves_its_effective_size_once(self):
        from organizer_inserts._text import text_fitted
        old = self.legacy()
        effective = text_fitted(old)[0]
        canonical = canonical_text_feature(old)
        self.assertAlmostEqual(canonical.options["cap_height"], effective, places=6)
        # The glyph, not the old rectangle, now sets the interaction bounds.
        glyph = inserts.text_placed_outline(canonical)
        bounds = glyph.bounds
        zone = canonical.zone
        self.assertLessEqual(zone.x0, bounds[0] + 1e-6)
        self.assertLessEqual(zone.width, old.zone.width + 1e-6)

    def test_save_and_reopen_do_not_move_or_resize_text(self):
        design = default_design()
        design["box"].update(x=64, y=64, z=40)
        legacy = default_feature_payload({"design": design, "kind": "text"})["feature"]
        legacy["zone"] = [-14, -5, 6, 9]
        legacy["options"] = {"text": "M3", "auto": False, "quarter_turns": 1}
        design["layout"]["features"] = [legacy]
        box, layout, *rest = app.design_from_dict(design)
        first = app.design_to_dict(box, layout, *rest)
        box2, layout2, *rest2 = app.design_from_dict(first)
        second = app.design_to_dict(box2, layout2, *rest2)
        self.assertEqual(first["layout"]["features"], second["layout"]["features"])
        saved = first["layout"]["features"][0]
        self.assertNotIn("auto", saved["options"])
        self.assertEqual(saved["options"]["quarter_turns"], 1)

    def test_duplicate_destinations_load_but_are_reported_not_dropped(self):
        design = default_design()
        design["box"].update(x=64, y=64, z=40)
        base = default_feature_payload({"design": design, "kind": "text"})["feature"]
        design["layout"]["features"] = [base, json.loads(json.dumps(base))]
        box, layout, *_ = app.design_from_dict(design)
        self.assertEqual(len(layout.features), 2)
        preview = preview_payload({"design": app.design_to_dict(box, layout)})
        self.assertTrue(any("Only one Text" in message for message in preview["feature_errors"]))
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError, "Only one Text"):
            app.generate_organizer_files(box, layout, Path(folder))

    def test_text_type_registry_text_matches_the_new_model(self):
        source = Path("organizer_inserts/_text.py").read_text(encoding="utf-8")
        for stale in ("label on the floor", "Stand proud", "Place it for me", '"Level"'):
            self.assertFalse(stale in source, f"stale Text metadata: {stale}")
        self.assertTrue("centered lettering" in source.lower())

    def test_browser_text_ui_has_one_type_control_and_no_footprint(self):
        script = Path("web/app.js").read_text(encoding="utf-8")
        for needed in ("Text Type", "On base — Inlaid", "On base — Raised",
                       "At rim — Inlaid", "At rim — Raised", "Inlay depth", "Raised height",
                       "Thin", "Thickest", "Letter height"):
            self.assertIn(needed, script)
        for gone in ("Place it for me", "Text style", "Text location", 'editorGroup("Footprint"',
                     'editorGroup("Placement"'):
            self.assertNotIn(gone, script)


class DividerBottomAndShelfTests(unittest.TestCase):
    def test_rim_shelf_roots_into_the_real_wall_on_every_side(self):
        import numpy as np
        from organizer_engine import wavy_cavity_polygon, wavy_outer_polygon, LOCK_SAFE_SKIN
        from organizer_inserts._divider import DIVISION_SHELF_DEPTH
        box = BoxSpec(56, 56, 40)
        cavity = np.array(wavy_cavity_polygon(box).exterior.coords)
        safe = wavy_outer_polygon(box).buffer(-LOCK_SAFE_SKIN)
        base_z = app.base_height(box, "fused")
        for counts in ((1, 0), (1, 1)):
            for side, direction in (("back", (0, 1)), ("front", (0, -1)),
                                    ("left", (-1, 0)), ("right", (1, 0))):
                with self.subTest(counts=counts, side=side):
                    one = app.default_feature(box, "divider")
                    one = replace(one, options={**one.options, "count_x": counts[0],
                                                "count_y": counts[1], "label_divisions": True,
                                                "division_level": "rim", "division_side": side,
                                                "division_labels": ["A", "B", "C", "D"]})
                    shelves = [mesh for _n, mesh, _r in divider_division_texts(box, one, base_z)][::2]
                    z_top = float(shelves[0].bounds[1][2])
                    axis = 1 if direction[1] else 0
                    sign = direction[0] + direction[1]
                    face = cavity[(np.sign(cavity[:, axis]) == sign) & (np.abs(cavity[:, axis]) > 20)]
                    checked = 0
                    for shelf in shelves:
                        low, high = shelf.bounds[0], shelf.bounds[1]
                        reach = high[axis] if sign > 0 else low[axis]
                        if abs(reach) < 26.9:
                            continue                       # rests on a divider crest instead
                        along = 0 if axis else 1
                        pts = face[(face[:, along] > low[along] + 0.3) & (face[:, along] < high[along] - 0.3)]
                        inside_wall = pts + np.array(direction) * 0.03
                        top = np.c_[inside_wall, np.full(len(pts), z_top - 0.05)]
                        gap = np.abs(pts[:, axis]) - 26.53
                        slope = np.c_[inside_wall, z_top - DIVISION_SHELF_DEPTH - gap + 0.03]
                        self.assertTrue(shelf.contains(top).all(), "flat top must run into the wall")
                        self.assertTrue(shelf.contains(slope).all(), "sloped underside must run into the wall")
                        import shapely
                        outline = np.array(shelf.vertices)[:, :2]
                        self.assertTrue(shapely.contains_xy(safe.buffer(2e-3), outline[:, 0], outline[:, 1]).all(),
                                        "shelf must stay inside the outside safety skin")
                        checked += len(pts)
                    self.assertGreater(checked, 100)

    def test_80_degree_bottom_builds_in_every_supported_construction(self):
        box = BoxSpec(64, 64, 80)
        base_z = app.base_height(box, "fused")
        for name, options, full in (
            ("solid", {"count_x": 9, "count_y": 0}, True),
            ("crossbar", {"count_x": 9, "count_y": 0, "minimal_bottom": True, "bottom_supports": 2}, True),
            ("grid", {"count_x": 9, "count_y": 9}, True),
            ("partial span", {"count_x": 9, "count_y": 0}, False),
        ):
            with self.subTest(construction=name):
                one = app.default_feature(box, "divider")
                zone = one.zone if full else inserts.Zone(-24, -24, 24, 24)
                one = replace(one, zone=zone, full_span=full, options={
                    **one.options, **options, "slope_base": True, "bottom_angle": 80})
                solids = inserts.build_features(box, [one], base_z, inserts.layout_zone(box, "fused"))
                slopes = [s for s in solids if s.metadata.get("wavefinity_preview_kind") == "slope"]
                self.assertTrue(slopes)
                self.assertTrue(all(s.is_watertight and s.is_volume for s in slopes))
                if full:
                    body = inserts.make_fused_box(box, [one], app.make_box(box))
                    self.assertTrue(body.is_watertight and body.volume > 0)
        self.assertEqual(inserts.BOTTOM_SLOPE_MAX, 80.0)
        one = replace(app.default_feature(box, "divider"),
                      options={"count_x": 9, "slope_base": True, "bottom_angle": 81})
        with self.assertRaisesRegex(ValueError, "80"):
            inserts.build_features(box, [one], base_z)

    def test_legacy_slope_without_an_angle_keeps_the_old_20_degree_fallback(self):
        box = BoxSpec(64, 64, 40)
        base_z = app.base_height(box, "fused")
        one = app.default_feature(box, "divider")
        legacy = replace(one, options={**one.options, "slope_base": True})
        explicit = replace(one, options={**one.options, "slope_base": True, "bottom_angle": 20})
        forty_five = replace(one, options={**one.options, "slope_base": True, "bottom_angle": 45})
        volume = lambda item: sum(float(s.volume) for s in inserts.build_features(box, [item], base_z))
        self.assertAlmostEqual(volume(legacy), volume(explicit), places=3)
        self.assertNotAlmostEqual(volume(legacy), volume(forty_five), places=1)
        reopened = inserts.layout_from_dict(inserts.layout_to_dict(inserts.Layout((legacy,), "fused")))
        self.assertNotIn("bottom_angle", reopened.features[0].options)

    def test_browser_bottom_defaults_come_from_the_server_and_are_not_reseeded(self):
        script = Path("web/app.js").read_text(encoding="utf-8")
        self.assertIn("bottom_default_angle", script)
        self.assertIn("curved_default_depth", script)
        self.assertNotIn("one.options.bottom_angle = 45;\n    } else if", script)

    def test_divider_label_ui_is_one_label_type_with_coordinate_placeholders(self):
        script = Path("web/app.js").read_text(encoding="utf-8")
        for needed in ("Label Type", "No label", "On base", "Rim level", "placeholder=\"${cell.row + 1},${cell.column + 1}\""):
            self.assertIn(needed, script)
        self.assertNotIn("Division labels", script)
        self.assertNotIn('"Label divisions"', script)


class BoreWebTests(unittest.TestCase):
    def hugging(self, style, size=48):
        from organizer_inserts import Item, Segment
        from organizer_inserts._bore import wall_only_envelope
        item = Item("tube", (Segment(25.0, 30.0),), profile="round", clearance=0.0)
        box = replace(BoxSpec(48, 48, 40), x=size, y=size)
        env = wall_only_envelope("round", 30.0, 1.6, "wavy" if style == "walls_wavy" else "straight", foot=True)
        zone = inserts.Zone(-env["span_x"] / 2, -env["span_y"] / 2, env["span_x"] / 2, env["span_y"] / 2)
        one = inserts.Feature("bore", zone, item, options={
            "bore_style": style, "xy_size_mode": "bin_to_bore", "height": 10.0, "wall": 1.6})
        return box, one

    def test_gap_supports_are_thin_and_much_lighter_than_the_old_blocks(self):
        import numpy as np
        for style in ("walls_wavy", "walls_straight"):
            with self.subTest(style=style):
                box, one = self.hugging(style)
                whole = inserts.Zone.whole(box)
                mesh = inserts.build_features(box, [one], box.base_thickness)[0]
                self.assertTrue(mesh.is_watertight)
                self.assertEqual(len(mesh.split(only_watertight=False)), 1)
                self.assertGreater(mesh.bounds[1][0], whole.x1 + 0.5)
                self.assertLess(mesh.bounds[0][1], whole.y0 - 0.5)
                radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
                self.assertGreaterEqual(radii[radii < 20.0].min(), 15.0 - 1e-6)
                # The old rectangular blocks came to about 4900 / 5300 mm3 here.
                self.assertLess(float(mesh.volume), 3000.0)

    def test_each_cluster_gets_at_most_one_web_per_reachable_wall(self):
        box = BoxSpec(32, 32, 40)
        whole = inserts.Zone.whole(box)
        opening = rectangle(-4, -4, 4, 4)
        joined = rectangle(-7, -7, 7, 7)               # one connected sleeve cluster
        webs = _join_tabs(box, joined, opening, 0.6, hug=True, web_width=1.2, wavy=False)
        self.assertEqual(len(webs), 4)                 # one per cardinal wall, never more
        for web in webs:
            self.assertAlmostEqual(min(web.bounds[2] - web.bounds[0], web.bounds[3] - web.bounds[1]),
                                   1.2, delta=0.05)    # slender: the Bore wall thickness
            self.assertLess(web.area, 1.3 * (whole.width / 2.0))
        self.assertTrue(unary_union(webs).intersection(opening).is_empty)
        two = rectangle(-9, -7, -2, 7).union(rectangle(2, -7, 9, 7))
        separate = _join_tabs(box, two, opening, 0.6, hug=True, web_width=1.2, wavy=False)
        self.assertEqual(len(separate), 6)             # each cluster: left/right + front + back only


    def test_a_side_that_already_touches_gets_no_gap_web(self):
        box = BoxSpec(56, 56, 40)
        whole = inserts.Zone.whole(box)
        touching = rectangle(whole.x1 - 6.0, -6, whole.x1 + 0.005, 6)
        opening = rectangle(whole.x1 - 4.0, -3.5, whole.x1 - 1.0, 3.5)
        webs = _join_tabs(box, touching, opening, 0.6, hug=True, web_width=1.2, wavy=False)
        self.assertFalse([web for web in webs if web.bounds[2] < 0])   # none toward the far wall
        self.assertTrue(webs)                           # the touching side keeps its local weld
        self.assertTrue(all(web.bounds[0] > whole.x1 - 6.5 for web in webs))

    def test_wavy_webs_follow_the_authoritative_wall_wave(self):
        from organizer_engine import WAVE_AMPLITUDE
        box = BoxSpec(24, 24, 40)
        material = rectangle(-6, -6, 6, 6)
        opening = rectangle(-2, -2, 2, 2)
        straight = unary_union(_join_tabs(box, material, opening, 0.6, hug=True, web_width=1.2, wavy=False))
        wavy = unary_union(_join_tabs(box, material, opening, 0.6, hug=True, web_width=1.2, wavy=True))
        right = lambda shape: rectangle(8, -20, 40, 20).intersection(shape)
        span_straight = right(straight).bounds[3] - right(straight).bounds[1]
        span_wavy = right(wavy).bounds[3] - right(wavy).bounds[1]
        self.assertAlmostEqual(span_straight, 1.2, delta=0.05)
        self.assertGreater(span_wavy, 1.2 + 0.5 * WAVE_AMPLITUDE)
        self.assertLess(span_wavy, 1.2 + 2.5 * WAVE_AMPLITUDE)


class GlyphCollisionAndExportTests(unittest.TestCase):
    def test_base_text_collides_by_its_real_glyphs_not_its_editor_box(self):
        box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)
        text = text_feature(box, value="L", cap=14.0)        # an L leaves a big empty corner
        outline = inserts.text_placed_outline(text)
        x0, y0, x1, y1 = outline.bounds
        # A post tucked into the empty corner of the L's rectangle, well clear of the ink.
        corner = inserts.Zone(x1 - 4.0, y1 - 4.0, x1 - 1.5, y1 - 1.5)
        post = inserts.Feature("post", corner, options={"diameter": 2.5, "height": 6.0})
        self.assertTrue(text.zone.overlaps(corner, 0.0))     # the box does overlap it
        self.assertGreater(outline.distance(corner.polygon), inserts.MIN_FEATURE_GAP)
        inserts.Layout((text, post), "fused").validate(box)  # so it is legal
        # A post that really touches the letter is still refused.
        touching = inserts.Zone(x0, y0, x0 + 3.0, y0 + 3.0)
        with self.assertRaisesRegex(ValueError, "overlap"):
            inserts.Layout((text, inserts.Feature("post", touching)), "fused").validate(box)

    def test_divider_base_and_rim_labels_export_as_their_own_objects(self):
        box = BoxSpec(56, 56, 40)
        one = app.default_feature(box, "divider")
        for level in ("base", "rim"):
            with self.subTest(level=level):
                labelled = replace(one, options={**one.options, "wall_style": "straight",
                                                 "label_divisions": True, "division_level": level,
                                                 "division_side": "back",
                                                 "division_labels": ["A", "B"]})
                with tempfile.TemporaryDirectory() as folder:
                    result = app.generate_organizer_files(
                        box, inserts.Layout((labelled,), "fused"), Path(folder))
                self.assertEqual(result["text_objects"], ["A", "B"])

    def test_rim_label_shelf_is_body_material_and_lettering_is_recessed(self):
        box = BoxSpec(56, 56, 40)
        one = app.default_feature(box, "divider")
        one = replace(one, options={**one.options, "label_divisions": True, "division_level": "rim",
                                    "division_side": "back", "division_labels": ["A", "B"]})
        base_z = app.base_height(box, "fused")
        parts = divider_division_texts(box, one, base_z)
        self.assertEqual([raised for _n, _m, raised in parts], [True, False, True, False])
        shelf, inlay = parts[0][1], parts[1][1]
        self.assertAlmostEqual(float(inlay.bounds[1][2]), float(shelf.bounds[1][2]), places=3)
        self.assertGreater(float(shelf.volume), float(inlay.volume))
        self.assertEqual([name for name, _m, _r in inserts.build_texts(box, [one], base_z)], ["A", "B"])


class TextExportFileTests(unittest.TestCase):
    def test_all_four_text_types_write_valid_3mf_files_with_matching_objects(self):
        from organizer_engine import validate_3mf
        box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)
        for raised in (False, True):
            with self.subTest(raised=raised):
                layout = inserts.Layout((
                    text_feature(box, value="AB", cap=9.0, raised=raised, depth=0.6),
                    text_feature(box, level="rim", side="back", value="CD", cap=4.0,
                                 raised=raised, depth=0.4),
                ), "fused")
                with tempfile.TemporaryDirectory() as folder:
                    result = app.generate_organizer_files(box, layout, Path(folder))
                    self.assertEqual(result["text_objects"], ["AB", "CD"])
                    kinds = {(one["text_type"], round(one["depth_mm"], 3)) for one in result["texts"]}
                    label = "Raised" if raised else "Inlaid"
                    self.assertEqual(kinds, {(f"On base — {label}", 0.6), (f"At rim — {label}", 0.4)})
                    self.assertEqual(
                        validate_3mf(Path(result["box"]["output"]), 3, multipart=("AB", "CD"))["warnings"], 0)


class DividerBoreBottomTests(unittest.TestCase):
    def test_divider_labels_legacy_side_and_real_shelf(self):
        box = BoxSpec(64, 64, 40)
        one = app.default_feature(box, "divider")
        options = {**one.options, "label_divisions": True,
                   "division_level": "rim", "division_side": "front",
                   "division_labels": ["A", "B"]}
        one = replace(one, options=options)
        outputs = divider_division_texts(box, one, box.base_thickness)
        self.assertTrue(outputs)
        self.assertTrue(any(raised for _name, _mesh, raised in outputs))
        serialized = inserts.layout_to_dict(inserts.Layout((one,), "fused"))
        reopened = inserts.layout_from_dict(serialized).features[0]
        self.assertEqual(reopened.options["division_side"], "front")

    def test_bottom_defaults_and_legacy_custom_values(self):
        ordinary = BoxSpec(64, 64, 40)
        shallow = BoxSpec(64, 64, 12)
        one = app.default_feature(ordinary, "divider")
        normal = divider_defaults(ordinary, one, ordinary.base_thickness)
        small = divider_defaults(shallow, one, shallow.base_thickness)
        self.assertEqual(normal["curved_default_depth"], 60)
        self.assertEqual(normal["bottom_default_angle"], 45)
        self.assertLess(small["curved_default_depth"], 60)
        self.assertLess(small["bottom_default_angle"], 45)
        for angle in (17, 55):
            legacy = replace(one, options={**one.options, "slope_base": True, "bottom_angle": angle})
            reopened = inserts.layout_from_dict(inserts.layout_to_dict(inserts.Layout((legacy,), "fused")))
            self.assertEqual(reopened.features[0].options["bottom_angle"], angle)
        curved = replace(one, options={**one.options, "scoop": {"depth": 53}})
        reopened = inserts.layout_from_dict(inserts.layout_to_dict(inserts.Layout((curved,), "fused")))
        self.assertEqual(reopened.features[0].options["scoop"]["depth"], 53)

    def test_gap_webs_are_thin_straight_or_wavy(self):
        box = BoxSpec(48, 48, 40)
        material = rectangle(-21, -21, 21, 21)
        opening = rectangle(-2, -2, 2, 2)
        straight = _join_tabs(box, material, opening, 0.6, hug=True,
                              web_width=1.2, wavy=False)
        wavy = _join_tabs(box, material, opening, 0.6, hug=True,
                          web_width=1.2, wavy=True)
        self.assertLessEqual(len(straight), 4)
        self.assertLessEqual(len(wavy), 4)
        self.assertTrue(straight)
        self.assertTrue(wavy)
        self.assertTrue(unary_union(straight).intersection(opening).is_empty)
        self.assertTrue(unary_union(wavy).intersection(opening).is_empty)
        self.assertNotAlmostEqual(unary_union(straight).symmetric_difference(
            unary_union(wavy)).area, 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
