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


class DividerLabelOrientationTests(unittest.TestCase):
    """Fix 1132: base-label orientation (Side to side / Front to back)."""

    box = BoxSpec(56, 56, 40)

    def label_bounds(self, along=None, grid=True, **extra):
        base_z = app.base_height(self.box, "fused")
        one = app.default_feature(self.box, "divider")
        options = {**one.options, "label_divisions": True, "division_level": "base",
                   "division_labels": ["ABCDEF", "GHIJKL"], **extra}
        if grid:
            options.update(count_x=1, count_y=0)
        else:
            options.pop("count_x", None)
            options.pop("count_y", None)
        one = replace(one, options=options, **({"along": along, "count": 1} if along else {}))
        return [mesh.bounds for _n, mesh, _r in divider_division_texts(self.box, one, base_z)]

    @staticmethod
    def extent(bounds):
        return bounds[1][0] - bounds[0][0], bounds[1][1] - bounds[0][1]

    def test_option_value_keeps_the_enum_string(self):
        from organizer_inserts._registry import option_value
        self.assertEqual(option_value("division_label_orientation", "front_to_back", "divider"),
                         "front_to_back")

    def test_divider_defaults_carry_side_to_side(self):
        self.assertEqual(divider_defaults(
            self.box, app.default_feature(self.box, "divider"), app.base_height(self.box, "fused")
        )["division_label_orientation"], "side_to_side")

    def test_grid_front_to_back_rotates_the_lettering(self):
        side = self.label_bounds(division_label_orientation="side_to_side")
        front = self.label_bounds(division_label_orientation="front_to_back")
        self.assertTrue(side and front)
        wx, wy = self.extent(side[0])
        self.assertGreater(wx, wy)
        fx, fy = self.extent(front[0])
        self.assertGreater(fy, fx)

    def test_grid_absent_orientation_matches_side_to_side(self):
        absent = self.label_bounds()
        side = self.label_bounds(division_label_orientation="side_to_side")
        for a, b in zip(absent, side):
            self.assertTrue((abs(a - b) < 1e-9).all())

    def test_legacy_slot_absent_keeps_run_lettering_and_cap(self):
        # Legacy along == "y": lettering follows the run (rotated); an explicit
        # "front_to_back" matches that rotation, so the cap must not change.
        absent = self.label_bounds(along="y", grid=False)
        rotated = self.label_bounds(along="y", grid=False, division_label_orientation="front_to_back")
        self.assertTrue(absent)
        for a, b in zip(absent, rotated):
            self.assertTrue((abs(a - b) < 1e-9).all())
        ax, ay = self.extent(absent[0])
        self.assertGreater(ay, ax)

    def test_legacy_slot_explicit_side_to_side_unrotates(self):
        absent = self.label_bounds(along="y", grid=False)
        flat = self.label_bounds(along="y", grid=False, division_label_orientation="side_to_side")
        self.assertTrue(flat)
        fx, fy = self.extent(flat[0])
        self.assertGreater(fx, fy)
        self.assertNotEqual(self.extent(absent[0]), (fx, fy))


if __name__ == "__main__":
    unittest.main()
