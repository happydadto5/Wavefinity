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





class TextMigrationTests(unittest.TestCase):
    def setUp(self):
        self.box = BoxSpec(64, 64, 40, base_thickness=1.2, standard_base=False)

    def legacy(self, **options):
        return inserts.Feature("text", inserts.Zone(-14, -5, 6, 9),
                               options={"text": "M3", "quarter_turns": 1, **options})



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


if __name__ == "__main__":
    unittest.main()
