"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import wavefinity_web
import organizer_inserts as inserts
from organizer_app import base_height, design_from_dict
from organizer_inserts import build_features
from wavefinity_web import (
    apply_feature_payload,
    catalog_payload,
    default_design,
    default_feature_payload,
    delete_feature_payload,
    draft_payload,
    expand_layout_payload,
    feature_fit_payload,
    make_server,
    mode_payload,
    photo_nest_payload,
    preview_payload,
)
from photo_nest import PhotoOutline


def _text_feature(said, auto=False, zone=(-20.0, -6.0, 20.0, 6.0), **options):
    """One ``text`` interior part, as the browser would send it."""
    return {
        "kind": "text",
        "zone": list(zone),
        "item": None,
        "count": None,
        "along": "x",
        "options": {"text": said, "auto": auto, **options},
        "full_span": False,
        "wedge": True,
        "alternate_ends": False,
        "contour": None,
        "rotation": 0.0,
        "scale": 1.0,
    }


class WebApplicationTests(unittest.TestCase):
    def test_catalog_exposes_every_interior_part_and_safe_default_design(self):
        catalog = catalog_payload()
        parts = {part["kind"]: part for part in catalog["parts"]}
        self.assertEqual(
            set(parts),
            {"divider", "post", "pocket", "bore", "cradle", "nest", "slot",
             "steps", "scoop", "text"},
        )
        self.assertEqual(parts["scoop"]["title"], "Curved Scoop")
        self.assertFalse(parts["scoop"]["flags"]["size"])
        self.assertFalse(parts["scoop"]["flags"]["along"])
        self.assertEqual(
            [(field["label"], field["key"], field["default"])
             for field in parts["scoop"]["fields"]],
            [("Depth", "depth", "60")],
        )
        self.assertTrue(parts["text"]["flags"]["text"])
        self.assertEqual(parts["text"]["title"], "Text")
        self.assertTrue(parts["cradle"]["flags"]["alternate"])
        self.assertFalse(parts["nest"]["flags"]["alternate"])
        self.assertTrue(parts["nest"]["flags"]["photo"])
        self.assertEqual(parts["nest"]["title"], "Photo Nest")
        self.assertEqual(
            [field["label"] for field in parts["nest"]["fields"]],
            ["Fit clearance", "Soften outline"],
        )
        box, layout, *_ = design_from_dict(catalog["defaults"]["design"])
        self.assertEqual((box.x, box.y, box.z), (16.0, 48.0, 40.0))
        self.assertEqual(box.base_thickness, 0.6)
        self.assertEqual(layout.mode, "fused")

    def test_bore_catalog_exposes_the_grid_and_angle_and_drops_quantity(self):
        parts = {part["kind"]: part for part in catalog_payload()["parts"]}
        bore = parts["bore"]
        self.assertFalse(bore["flags"]["qty"])
        labels = [field["label"] for field in bore["fields"]]
        self.assertIn("X quantity", labels)
        self.assertIn("Y quantity", labels)
        self.assertIn("Angle °", labels)

    def test_hex_bit_bore_default_holds_the_bit_and_stands_upright(self):
        design = default_design()
        response = default_feature_payload({
            "design": design,
            "kind": "bore",
            "item": {
                "name": "bit",
                "profile": "hex_bit_long",
                "segments": [{"length": 38, "diameter": 6.35}],
                "clearance": 0.25,
            },
        })
        resolved = response["resolved_options"]
        self.assertEqual(resolved["depth"], inserts.HEX_BIT_HOLD["hex_bit_long"])
        self.assertEqual(resolved["angle"], 0.0)

    def test_feature_fit_snaps_a_bore_zone_down_to_its_hole_grid(self):
        design = default_design()
        design["box"]["x"], design["box"]["y"] = 200.0, 200.0
        feature = {
            "kind": "bore",
            "zone": [-60.0, -60.0, 60.0, 60.0],
            "item": {"name": "n", "profile": "round", "clearance": 0.4,
                     "segments": [{"length": 20, "diameter": 6}]},
            "count": None, "along": "x",
            "options": {"columns": "3", "rows": "2"},
            "full_span": False, "wedge": True, "alternate_ends": False,
            "contour": None, "rotation": 0.0, "scale": 1.0,
        }
        fitted = feature_fit_payload({"design": design, "feature": feature})["feature"]
        z = fitted["zone"]
        self.assertAlmostEqual(z[2] - z[0], 24.0, places=3)   # 3 * (6.4 + 1.6)
        self.assertAlmostEqual(z[3] - z[1], 16.0, places=3)   # 2 * (6.4 + 1.6)
        self.assertAlmostEqual((z[0] + z[2]) / 2, 0.0, places=3)   # stays centred

    def test_feature_fit_refuses_a_kind_with_no_contents(self):
        design = default_design()
        feature = {
            "kind": "pocket", "zone": [-30.0, -30.0, 30.0, 30.0], "item": None,
            "count": None, "along": "x", "options": {}, "full_span": False,
            "wedge": True, "alternate_ends": False, "contour": None,
            "rotation": 0.0, "scale": 1.0,
        }
        with self.assertRaises(ValueError):
            feature_fit_payload({"design": design, "feature": feature})

    def test_base_thickness_round_trips_and_legacy_designs_keep_their_floor(self):
        design = default_design()
        design["box"]["base_thickness"] = 1.1
        box, layout, label, part, location, scoop = design_from_dict(design)
        saved = wavefinity_web.design_to_dict(
            box, layout, label, part, location, scoop
        )
        self.assertEqual(saved["box"]["base_thickness"], 1.1)

        legacy = default_design()
        legacy["box"].pop("base_thickness")
        legacy["box"]["wall"] = 0.8
        legacy_box, *_ = design_from_dict(legacy)
        self.assertEqual(legacy_box.base_thickness, 0.8)

    def test_brief_interior_sizing_designs_migrate_back_to_the_modular_grid(self):
        design = default_design()
        design["box"].update({"x": 18.93962, "y": 50.93962, "interior_sizing": True})
        box, *_ = design_from_dict(design)
        self.assertEqual((box.x, box.y), (16.0, 48.0))

        design["box"].update({"x": 19.88442, "y": 51.88442, "wall": 1.2})
        box, *_ = design_from_dict(design)
        self.assertEqual((box.x, box.y), (16.0, 48.0))

    def test_connector_uses_two_heights_only_when_requested(self):
        with patch.object(wavefinity_web, "generate_side_file", return_value={}) as generate:
            wavefinity_web.connector_payload({
                "design": default_design(),
                "connector": {"bin_a_height": 40.0, "bin_b_height": 20.0},
            })
            self.assertEqual(generate.call_args.args[-2:], (40.0, 40.0))

            wavefinity_web.connector_payload({
                "design": default_design(),
                "connector": {
                    "different_heights": True, "bin_a_height": 40.0,
                    "bin_b_height": 20.0,
                },
            })
            self.assertEqual(generate.call_args.args[-2:], (40.0, 20.0))

    def test_connector_payload_names_file_appropriately(self):
        with patch.object(wavefinity_web, "generate_side_file", return_value={}) as generate:
            wavefinity_web.connector_payload({
                "design": default_design(),
                "output": "/fake/output",
            })
            self.assertEqual(generate.call_args.args[2].name, "Connector - Same height.3mf")

            wavefinity_web.connector_payload({
                "design": default_design(),
                "output": "/fake/output",
                "connector": {
                    "different_heights": True,
                    "bin_a_height": 50.0,
                    "bin_b_height": 20.0,
                    "tolerance": 0.05,
                },
            })
            self.assertEqual(generate.call_args.args[2].name, "Connector - 50mm to 20mm Tol 0.05mm.3mf")

    def test_bin_a_height_accepts_custom_height_from_payload(self):
        design = default_design()
        design["box"]["z"] = 30.0
        with patch.object(wavefinity_web, "generate_side_file", return_value={}) as generate:
            result = wavefinity_web.connector_payload({
                "design": design,
                "connector": {
                    "different_heights": True, "bin_a_height": 45.0,
                    "bin_b_height": 20.0,
                },
            })
        self.assertEqual(generate.call_args.args[6:8], (45.0, 20.0))
        plan = result["connector_plan"]
        self.assertEqual(plan["drop_mm"], 25.0)
        self.assertEqual(plan["shorter_bin"], "B")

    def test_default_draft_changes_real_geometry_when_height_changes(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        low = draft_payload({"design": design, "feature": feature})
        low_top = max(point[2] for face in low["geometry"] for point in face["points"])
        feature["options"]["height"] = 28.0
        high = draft_payload({"design": design, "feature": feature})
        high_top = max(point[2] for face in high["geometry"] for point in face["points"])
        self.assertGreater(high_top, low_top + 4.0)

    def test_photo_nest_defaults_include_finger_grasp_lift_assist(self):
        design = default_design()
        response = default_feature_payload({
            "design": design, "kind": "nest",
        })
        feature = response["feature"]
        self.assertEqual(feature["options"], {})
        self.assertIsNone(feature["contour"])
        resolved = response["resolved_options"]
        self.assertEqual(resolved["lift_assist"], "finger_grasp")
        self.assertEqual(resolved["finger_position"], "sides")
        self.assertEqual(resolved["finger_width"], 25.4)
        self.assertEqual(resolved["push_position"], "right")
        self.assertEqual(resolved["push_area"], 30.0)
        self.assertEqual(resolved["push_depth"], 4.0)

    def test_photo_upload_creates_one_contour_and_smallest_grid_bin(self):
        outline = PhotoOutline(
            ((-40, -10), (40, -10), (35, 10), (-40, 10)),
            80.0, 20.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            result = photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {
                    "clearance": 1.0, "depth": 9.0, "rim": 4.0,
                    "lift_assist": "push_out", "push_position": "left",
                    "push_area": 25.0, "push_depth": 5.0,
                },
            })
        design = result["design"]
        feature = design["layout"]["features"][0]
        self.assertEqual(len(design["layout"]["features"]), 1)
        self.assertEqual(feature["kind"], "nest")
        self.assertIsNone(feature["item"])
        self.assertEqual(feature["options"]["lift_assist"], "push_out")
        self.assertEqual(feature["options"]["push_position"], "left")
        self.assertEqual(feature["options"]["push_area"], 25.0)
        self.assertEqual(feature["options"]["push_depth"], 5.0)
        self.assertEqual(feature["contour"], [list(point) for point in outline.contour])
        self.assertNotIn("image", json.dumps(design).lower())
        self.assertEqual(design["box"]["x"] % 8.0, 0.0)
        self.assertEqual(design["box"]["y"] % 8.0, 0.0)
        box, layout, *_ = design_from_dict(design)
        one = layout.features[0]
        if box.x > 8.0:
            narrower = type(box)(box.x - 8.0, box.y, box.z, box.wall,
                                 box.corner_fillet, box.flat_inside,
                                 box.base_thickness)
            with self.assertRaisesRegex(ValueError, "outside the bin"):
                layout.validate(narrower)
        if box.y > 8.0:
            shallower = type(box)(box.x, box.y - 8.0, box.z, box.wall,
                                  box.corner_fillet, box.flat_inside,
                                  box.base_thickness)
            with self.assertRaisesRegex(ValueError, "outside the bin"):
                layout.validate(shallower)
        preview = preview_payload({"design": design})
        self.assertFalse(preview["feature_errors"])
        self.assertTrue(preview["feature_outlines"][0])
        self.assertTrue(preview["nest_soft_contours"][0])

    def test_preview_softened_contour_follows_the_soften_outline_value(self):
        notched = PhotoOutline(
            ((-20, -8), (-4, -8), (-4, -1), (4, -1), (4, -8),
             (20, -8), (20, 8), (-20, 8)),
            40.0, 16.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=notched):
            design = photo_nest_payload({
                "design": default_design(), "image": "x", "mime_type": "image/png",
            })["design"]
        sharp = preview_payload({"design": design})["nest_soft_contours"][0]
        self.assertEqual(len(sharp), len(notched.contour))
        self.assertEqual({tuple(p) for p in sharp},
                         {tuple(map(float, p)) for p in notched.contour})

        design["layout"]["features"][0]["options"]["smoothing"] = 3.0
        softened = preview_payload({"design": design})["nest_soft_contours"][0]
        self.assertGreater(len(softened), len(sharp) + 10)

    def test_photo_nest_clearance_recomputes_bin_footprint(self):
        outline = PhotoOutline(
            ((-38, -10), (38, -10), (38, 10), (-38, 10)),
            76.0, 20.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            made = photo_nest_payload({"design": default_design(), "image": "unused", "mime_type": "image/png"})
        feature = made["design"]["layout"]["features"][0]
        old_x = made["design"]["box"]["x"]
        feature["options"]["clearance"] = 5.0
        changed = apply_feature_payload({"design": made["design"], "feature": feature, "index": 0})
        self.assertGreater(changed["design"]["box"]["x"], old_x)

    def test_photo_nest_apply_refits_a_client_placeholder_zone(self):
        """Changing a nest setting must never save the browser's rough zone."""
        outline = PhotoOutline(
            ((-5, -3), (5, -3), (5, 3), (-5, 3)), 10.0, 6.0,
            ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            made = photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
            })
        feature = made["design"]["layout"]["features"][0]
        feature["options"]["clearance"] = 1.0
        cx = (feature["zone"][0] + feature["zone"][2]) / 2.0
        cy = (feature["zone"][1] + feature["zone"][3]) / 2.0
        feature["zone"] = [cx - .5, cy - .5, cx + .5, cy + .5]
        saved = apply_feature_payload({
            "design": made["design"], "feature": feature, "index": 0,
        })["design"]["layout"]["features"][0]
        self.assertGreater(saved["zone"][2] - saved["zone"][0], 15.0)

    def test_photo_nest_rotation_and_proportional_scale_recompute_footprint(self):
        outline = PhotoOutline(
            ((-38, -9), (38, -9), (38, 9), (-38, 9)),
            76.0, 18.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            made = photo_nest_payload({"design": default_design(), "image": "unused", "mime_type": "image/png"})
        original = made["design"]
        feature = original["layout"]["features"][0]
        feature["rotation"] = 90.0
        rotated = apply_feature_payload({"design": original, "feature": feature, "index": 0})["design"]
        self.assertLess(rotated["box"]["x"], original["box"]["x"])
        self.assertGreater(rotated["box"]["y"], original["box"]["y"])
        feature = rotated["layout"]["features"][0]
        feature["scale"] = 1.5
        scaled = apply_feature_payload({"design": rotated, "feature": feature, "index": 0})["design"]
        self.assertGreaterEqual(scaled["box"]["x"], rotated["box"]["x"])
        self.assertGreater(scaled["box"]["y"], rotated["box"]["y"])

    def test_draft_geometry_identifies_the_part_it_will_print_with(self):
        for mode, prefix in (("fused", "feature_"), ("separate", "insert_")):
            design = default_design()
            design["layout"]["mode"] = mode
            feature = default_feature_payload({
                "design": design, "kind": "pocket",
            })["feature"]
            draft = draft_payload({"design": design, "feature": feature})
            self.assertEqual(
                {face["kind"] for face in draft["geometry"]},
                {f"{prefix}pocket"},
            )

    def test_add_update_delete_round_trip_uses_design_schema(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        added = apply_feature_payload({"design": design, "feature": feature, "index": None})
        self.assertEqual(added["selected"], 0)
        self.assertEqual(len(added["design"]["layout"]["features"]), 1)
        updated_feature = added["design"]["layout"]["features"][0]
        updated_feature["zone"] = [-5.0, -1.0, 5.0, 1.0]
        updated = apply_feature_payload({
            "design": added["design"], "feature": updated_feature, "index": 0,
        })
        saved = updated["design"]["layout"]["features"][0]
        self.assertEqual(saved["zone"][2] - saved["zone"][0], 10.0)
        deleted = delete_feature_payload({"design": updated["design"], "index": 0})
        self.assertEqual(deleted["design"]["layout"]["features"], [])

    def test_changing_a_placed_part_type_reuses_its_list_slot(self):
        design = default_design()
        design["box"]["x"] = 48.0
        design["box"]["y"] = 48.0
        post = default_feature_payload({"design": design, "kind": "post"})["feature"]
        design = apply_feature_payload({
            "design": design, "feature": post, "index": None,
        })["design"]
        second = default_feature_payload({"design": design, "kind": "post"})["feature"]
        design = apply_feature_payload({
            "design": design, "feature": second, "index": None,
        })["design"]

        cradle = default_feature_payload({
            "design": design, "kind": "cradle",
            "item": {
                "name": "Driver", "profile": "round", "clearance": 0.4,
                "segments": [{"length": 40.0, "diameter": 6.0}],
            },
        })["feature"]
        changed = apply_feature_payload({
            "design": design, "feature": cradle, "index": 1,
        })

        self.assertEqual(changed["selected"], 1)
        self.assertEqual(
            [one["kind"] for one in changed["design"]["layout"]["features"]],
            ["post", "cradle"],
        )
        self.assertTrue(preview_payload({"design": changed["design"]})["fits"])

    def test_alternate_ends_survives_the_browser_api_round_trip(self):
        design = default_design()
        design["box"]["x"] = 96.0
        design["box"]["y"] = 96.0
        item = {
            "name": "driver", "profile": "round", "clearance": 0.4,
            "segments": [{"length": 50.0, "diameter": 8.0}],
        }
        feature = default_feature_payload({
            "design": design, "kind": "cradle", "item": item,
        })["feature"]
        feature["zone"] = [-40.0, -44.0, 40.0, 44.0]
        feature["count"] = 4
        feature["alternate_ends"] = True
        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        saved = applied["design"]["layout"]["features"][0]
        self.assertTrue(saved["alternate_ends"])
        self.assertTrue(draft_payload({
            "design": design, "feature": saved,
        })["geometry"])

    def test_divider_bottom_slope_options_survive_the_browser_api_round_trip(self):
        design = default_design()
        design["box"]["x"] = 96.0
        design["box"]["y"] = 96.0
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["zone"] = [-24.0, -24.0, 24.0, 24.0]
        feature["count"] = 2
        # exactly as the browser sends them: a numeric slope, whole-number
        # crossbar count, and three yes/no flags as real booleans
        feature["options"] = {
            "bottom_angle": 20.0,
            "reverse_bottom": True,
            "alternate_bottom": True,
            "minimal_bottom": True,
            "bottom_supports": 4,
        }
        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        saved = applied["design"]["layout"]["features"][0]["options"]
        self.assertEqual(saved["bottom_angle"], 20.0)
        self.assertIs(saved["reverse_bottom"], True)
        self.assertIs(saved["alternate_bottom"], True)
        self.assertIs(saved["minimal_bottom"], True)
        self.assertEqual(saved["bottom_supports"], 4)
        # and the round-tripped design still previews with real geometry
        drafted = draft_payload({
            "design": design,
            "feature": applied["design"]["layout"]["features"][0],
        })
        self.assertTrue(drafted["geometry"])
        self.assertEqual(drafted["resolved_options"]["bottom_angle"], 20.0)

    def test_divider_bottom_flags_sent_as_strings_stay_flags_not_floats(self):
        design = default_design()
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["options"] = {
            "bottom_angle": "15",
            "minimal_bottom": "true",
            "reverse_bottom": "false",
        }
        one = wavefinity_web._feature_from_json(feature, "fused")
        self.assertEqual(one.options["bottom_angle"], 15.0)
        self.assertIs(one.options["minimal_bottom"], True)
        self.assertIs(one.options["reverse_bottom"], False)

    def test_a_divider_design_with_no_bottom_keys_still_loads(self):
        design = default_design()
        design["box"]["x"] = 96.0
        design["box"]["y"] = 96.0
        design["layout"]["features"] = [{
            "kind": "divider",
            "zone": [-20.0, -20.0, 20.0, 20.0],
            "item": None, "count": 2, "along": "x", "options": {},
            "full_span": False, "wedge": True, "alternate_ends": False,
            "contour": None, "rotation": 0.0, "scale": 1.0,
        }]
        drafted = draft_payload({
            "design": design,
            "feature": design["layout"]["features"][0],
        })
        self.assertTrue(drafted["geometry"])
        self.assertEqual(drafted["resolved_options"]["bottom_angle"], 0.0)

    def _long_cradle_design(self, mode):
        """A bin barely longer than one cradle zone, whose trough fills well
        under half of it - the rest is open floor a fused support may use."""
        design = default_design()
        design["layout"]["mode"] = mode
        design["box"]["x"] = 40.0
        design["box"]["y"] = 176.0
        item = {
            "name": "driver", "profile": "round", "clearance": 0.4,
            "segments": [{"length": 60.0, "diameter": 22.0}],
        }
        cradle = default_feature_payload({
            "design": design, "kind": "cradle", "item": item, "along": "y",
        })["feature"]
        cradle["zone"] = [-14.0, -78.0, 14.0, 78.0]
        cradle["count"] = 1
        return apply_feature_payload({
            "design": design, "feature": cradle, "index": None,
        })["design"]

    def test_a_fused_support_may_use_the_floor_a_cradle_zone_leaves_open(self):
        design = self._long_cradle_design("fused")
        cradle_zone = design["layout"]["features"][0]["zone"]
        pocket = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        added = apply_feature_payload({
            "design": design, "feature": pocket, "index": None,
        })
        placed = added["design"]["layout"]["features"][1]["zone"]
        # Nowhere else to go: it lands inside the cradle's zone, past its trough.
        self.assertLess(placed[1], cradle_zone[3])
        self.assertGreater(placed[3], cradle_zone[1])
        self.assertTrue(preview_payload({"design": added["design"]})["fits"])

    def test_a_removable_insert_still_keeps_a_cradle_whole_zone_clear(self):
        design = self._long_cradle_design("separate")
        pocket = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        with self.assertRaisesRegex(ValueError, "no open floor area"):
            apply_feature_payload({
                "design": design, "feature": pocket, "index": None,
            })

    def test_the_preview_reports_the_floor_a_cradle_really_covers(self):
        design = self._long_cradle_design("fused")
        covered = preview_payload({"design": design})["feature_footprints"][0]
        zone = design["layout"]["features"][0]["zone"]
        self.assertIsNotNone(covered)
        # Shorter than its zone along the run, and inside it.
        self.assertLess(covered[3] - covered[1], zone[3] - zone[1])
        self.assertGreaterEqual(covered[1], zone[1])
        self.assertLessEqual(covered[3], zone[3])
        # A pocket fills its zone exactly, so there is nothing extra to draw.
        pocket = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        added = apply_feature_payload({
            "design": design, "feature": pocket, "index": None,
        })["design"]
        self.assertIsNone(preview_payload({"design": added})["feature_footprints"][1])

    def test_delete_can_recover_a_layout_after_the_bin_is_shrunk(self):
        design = default_design()
        design["box"]["x"] = 48.0
        feature = default_feature_payload({"design": design, "kind": "post"})["feature"]
        feature["zone"] = [10.0, -8.0, 22.0, 8.0]
        feature["options"] = {"diameter": 8.0, "height": 16.0}
        design = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })["design"]
        design["box"]["x"] = 16.0
        recovered = delete_feature_payload({"design": design, "index": 0})
        self.assertEqual(recovered["design"]["layout"]["features"], [])

    def test_auto_expand_grows_the_bin_to_fit_a_clamped_cradle(self):
        # a 40 mm tool in a 16 mm-wide bin: the cradle's zone was clamped to
        # 13 mm and would not build. Auto Expand grows the bin and gives the
        # cradle its real 40 mm footprint back.
        design = default_design()
        design["box"]["x"] = 16.0
        design["box"]["y"] = 48.0
        item = {
            "name": "Driver", "profile": "round", "clearance": 0.0,
            "segments": [{"length": 40.0, "diameter": 6.0}],
        }
        feature = default_feature_payload({
            "design": design, "kind": "cradle", "item": item,
        })["feature"]
        feature["along"] = "x"
        feature["count"] = 3
        feature["zone"] = [-6.5, -13.0, 6.5, 13.0]
        design["layout"]["features"] = [feature]

        expanded = expand_layout_payload({"design": design})
        self.assertTrue(expanded["grew"])
        self.assertGreaterEqual(expanded["box"]["x"], 48.0)
        box, layout, *_ = design_from_dict(expanded["design"])
        one = layout.features[0]
        self.assertAlmostEqual(one.zone.width, 40.0, delta=1.0)   # tool length back
        # the whole layout now builds
        preview = preview_payload({"design": expanded["design"]})
        self.assertFalse(preview["feature_errors"])
        self.assertIsNone(preview["draft_error"])

    def test_auto_expand_preserves_auto_count_cradle_across_dimension(self):
        design = default_design()
        design["box"]["x"] = 16.0
        design["box"]["y"] = 48.0
        item = {
            "name": "Driver", "profile": "round", "clearance": 0.0,
            "segments": [{"length": 40.0, "diameter": 6.0}],
        }
        feature = default_feature_payload({
            "design": design, "kind": "cradle", "item": item,
        })["feature"]
        feature["along"] = "x"
        feature["count"] = None
        feature["zone"] = [-6.5, -20.0, 6.5, 20.0]  # 40 mm across in y
        design["layout"]["features"] = [feature]

        expanded = expand_layout_payload({"design": design})
        self.assertTrue(expanded["grew"])
        self.assertGreaterEqual(expanded["box"]["x"], 48.0)
        box, layout, *_ = design_from_dict(expanded["design"])
        one = layout.features[0]
        self.assertAlmostEqual(one.zone.width, 40.0, delta=1.0)
        self.assertGreaterEqual(one.zone.depth, 38.0)
        base_z = base_height(box, layout.mode)
        single = build_features(box, [replace(one, count=1)], base_z)[0]
        multi = build_features(box, [one], base_z)[0]
        self.assertGreater(multi.volume, 1.5 * single.volume)

    def test_auto_expand_clears_an_angled_bore_tool_from_the_bin_side(self):
        design = default_design()
        design["box"]["x"] = 80.0
        design["box"]["y"] = 96.0
        feature = default_feature_payload({
            "design": design, "kind": "bore",
            "item": {
                "name": "Angled cylinder", "profile": "round", "clearance": 0.4,
                "segments": [{"length": 80.0, "diameter": 12.0}],
            },
        })["feature"]
        feature["along"] = "y"
        # This is a valid 2 x 2 base placed close to the -Y side. Its
        # cylinders lean farther towards that wall once they leave the bore.
        feature["zone"] = [-16.0, -46.0, 16.0, -2.0]
        feature["options"] = {"columns": 2, "rows": 2, "depth": 16.0,
                              "wall": 3.0, "angle": 45.0}
        design["layout"]["features"] = [feature]

        # The infinite tool ray reaches the -Y wall before it rises above the
        # rim, even though the bore block itself fits on the floor.
        with self.assertRaisesRegex(ValueError, "tool reaches the side"):
            draft_payload({"design": design, "feature": feature, "index": 0})

        expanded = expand_layout_payload({"design": design, "anchor": 0})
        self.assertTrue(expanded["grew"])
        self.assertGreater(expanded["box"]["y"], 96.0)
        preview = preview_payload({"design": expanded["design"]})
        self.assertFalse(preview["feature_errors"])
        self.assertIsNone(preview["draft_error"])

    def test_auto_expand_leaves_a_layout_that_already_fits_alone(self):
        design = default_design()
        design["box"]["x"] = 120.0
        design["box"]["y"] = 120.0
        divider = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        design["layout"]["features"] = [divider]
        result = expand_layout_payload({"design": design})
        self.assertFalse(result["grew"])
        self.assertEqual(result["box"]["x"], 120.0)
        self.assertEqual(result["box"]["y"], 120.0)

    def test_auto_expand_with_no_supports_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no interior supports"):
            expand_layout_payload({"design": default_design()})

    def test_mode_conversion_preserves_valid_layout(self):
        design = default_design()
        converted = mode_payload({"design": design, "mode": "separate"})["design"]
        self.assertEqual(converted["layout"]["mode"], "separate")
        preview = preview_payload({"design": converted})
        self.assertTrue(preview["geometry"])
        self.assertEqual(preview["design"]["layout"]["mode"], "separate")

    def test_preview_returns_camera_independent_geometry_and_uniform_bounds(self):
        preview = preview_payload({"design": default_design()})
        self.assertTrue(preview["geometry"])
        self.assertIn("normal", preview["geometry"][0])
        x0, y0, x1, y1 = preview["layout_bounds"]
        self.assertGreater(x1, x0)
        self.assertGreater(y1, y0)
        self.assertRegex(
            preview["dimensions"]["size"],
            r"\d+ X \d+ \(Inside\) - \d+ X \d+ mm \(Outside\)",
        )

    def test_preview_renders_the_rim_label_on_its_ledge(self):
        design = default_design()
        design["label"] = "M3"
        design["label_position"] = "top"
        preview = preview_payload({"design": design})
        self.assertTrue(preview["label_outline"])
        self.assertEqual(preview["label_meta"]["location"], "top")

    def test_preview_draws_a_text_part_like_any_other_interior_part(self):
        design = default_design()
        design["box"].update({"x": 120.0, "y": 80.0})
        design["layout"]["features"] = [_text_feature("DEBURR", auto=True)]
        preview = preview_payload({"design": design})
        self.assertTrue(preview["fits"])
        self.assertFalse(preview["feature_errors"])
        self.assertTrue(any(
            face["kind"] == "feature_text" for face in preview["geometry"]
        ))
        # No rim label, so the label channels stay empty - text is a feature.
        self.assertEqual(preview["label_outline"], [])
        self.assertIsNone(preview["label_meta"])
        said = preview["text_meta"][0]
        self.assertEqual(said["text"], "DEBURR")
        self.assertTrue(said["auto"])
        self.assertGreater(said["cap_height"], 0.0)

    def test_an_auto_text_part_comes_back_where_the_engine_put_it(self):
        design = default_design()
        design["box"].update({"x": 120.0, "y": 80.0})
        design["layout"]["features"] = [
            _text_feature("M3", auto=True, zone=[-4.0, -4.0, 4.0, 4.0])
        ]
        preview = preview_payload({"design": design})
        placed = preview["design"]["layout"]["features"][0]["zone"]
        self.assertNotEqual(placed, [-4.0, -4.0, 4.0, 4.0])
        # It fills the room it found rather than the placeholder it started in.
        self.assertGreater(placed[2] - placed[0], 8.0)

    def test_a_hand_placed_text_part_keeps_the_zone_it_was_given(self):
        design = default_design()
        design["box"].update({"x": 120.0, "y": 80.0})
        zone = [-20.0, 5.0, 20.0, 17.0]
        design["layout"]["features"] = [_text_feature("M3", auto=False, zone=zone)]
        preview = preview_payload({"design": design})
        self.assertEqual(preview["design"]["layout"]["features"][0]["zone"], zone)
        self.assertFalse(preview["text_meta"][0]["auto"])

    def test_a_second_auto_text_places_itself_instead_of_being_refused(self):
        """Apply has to resolve before it judges overlaps.

        Every new text starts on the same placeholder zone in the middle of
        the bin, so judging the raw submission refuses the second one for
        sitting on the first - which auto placement would have moved.
        """
        design = default_design()
        design["box"]["x"] = 48.0
        for said in ("M3", "M4"):
            feature = default_feature_payload(
                {"design": design, "kind": "text", "along": "x", "item": None}
            )["feature"]
            feature["options"]["text"] = said
            design = apply_feature_payload(
                {"design": design, "feature": feature, "index": None}
            )["design"]
        placed = design["layout"]["features"]
        self.assertEqual([one["options"]["text"] for one in placed], ["M3", "M4"])
        self.assertNotEqual(placed[0]["zone"], placed[1]["zone"])

    def test_a_draft_auto_text_is_drawn_where_it_will_actually_go(self):
        """The draft endpoint has to resolve too, and must return geometry.

        Text is left out of ``build_features``'s solids by default because a
        recessed inlay is subtracted rather than added; the draft preview has
        to ask for it, or the shape being edited draws nothing at all.
        """
        design = default_design()
        design["box"]["x"] = 48.0
        design["layout"]["features"] = [_text_feature("M3", auto=True)]
        design = preview_payload({"design": design})["design"]
        draft = default_feature_payload(
            {"design": design, "kind": "text", "along": "x", "item": None}
        )["feature"]
        draft["options"]["text"] = "M4"
        result = draft_payload({"design": design, "feature": draft})
        self.assertTrue(result["geometry"])
        # Moved clear of the one already placed, not left on the placeholder.
        self.assertNotEqual(result["feature"]["zone"], draft["zone"])
        placed = design["layout"]["features"][0]["zone"]
        self.assertNotEqual(result["feature"]["zone"], placed)

    def test_draft_text_part_auto_grows_width_when_text_added(self):
        design = default_design()
        design["box"].update({"x": 120.0, "y": 80.0})
        zone = [-8.0, -5.0, 8.0, 5.0]
        feature = _text_feature("M3 BOLTS AND NUTS", auto=False, zone=zone)
        result = draft_payload({"design": design, "feature": feature})
        grown_zone = result["feature"]["zone"]
        self.assertGreater(grown_zone[2] - grown_zone[0], 16.0)

    def test_auto_text_replacing_a_part_does_not_avoid_that_part(self):
        design = default_design()
        scoop = default_feature_payload({"design": design, "kind": "scoop"})["feature"]
        design = apply_feature_payload({
            "design": design, "feature": scoop, "index": None,
        })["design"]
        text = default_feature_payload({"design": design, "kind": "text"})["feature"]
        result = draft_payload({"design": design, "feature": text, "index": 0})
        self.assertTrue(result["geometry"])

    def test_legacy_scoop_becomes_an_editable_interior_part(self):
        design = default_design()
        design["scoop"] = True
        _box, layout, _label, _part, _location, scoop = design_from_dict(design)
        self.assertFalse(scoop)
        self.assertEqual([one.kind for one in layout.features], ["scoop"])

    def test_preview_has_no_label_outline_without_a_label(self):
        preview = preview_payload({"design": default_design()})
        self.assertEqual(preview["label_outline"], [])
        self.assertIsNone(preview["label_meta"])
        self.assertEqual(preview["text_meta"], ())
        self.assertNotIn("label_placement", preview["design"])

    def test_preview_reports_a_text_part_that_will_not_fit_its_box(self):
        design = default_design()
        design["layout"]["features"] = [
            _text_feature("MUCH TOO LONG FOR THIS", auto=False,
                          zone=[-5.0, -2.0, 5.0, 2.0])
        ]
        preview = preview_payload({"design": design})
        self.assertEqual(preview["invalid_feature_indexes"], (0,))
        self.assertTrue(
            any("will not fit" in message for message in preview["feature_errors"])
        )

    def test_preview_includes_a_highlighted_draft_not_yet_placed(self):
        design = default_design()
        draft = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        with_draft = preview_payload({"design": design, "draft": draft})
        without_draft = preview_payload({"design": design})
        self.assertIsNone(with_draft["draft_error"])
        self.assertTrue(any(face["kind"].startswith("draft_") for face in with_draft["geometry"]))
        self.assertFalse(any(face["kind"].startswith("draft_") for face in without_draft["geometry"]))
        # the draft never touches the real (empty) layout
        self.assertEqual(with_draft["design"]["layout"]["features"], [])

    def test_an_invalid_draft_does_not_break_the_rest_of_the_preview(self):
        design = default_design()
        placed_divider = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        placed = apply_feature_payload({
            "design": design, "feature": placed_divider, "index": None,
        })["design"]
        broken_draft = default_feature_payload({"design": placed, "kind": "pocket"})["feature"]
        broken_draft["options"] = {"height": -5.0}
        preview = preview_payload({"design": placed, "draft": broken_draft})
        self.assertIsNotNone(preview["draft_error"])
        self.assertIn("pocket", preview["draft_error"])
        # the already-placed divider still renders normally despite the bad draft
        self.assertTrue(any(face["kind"] in ("feature_divider", "feature_conflict_divider") for face in preview["geometry"]))
        self.assertTrue(any(face["kind"] == "draft_invalid" for face in preview["geometry"]))

    def test_preview_ignores_the_saved_part_when_it_is_the_open_draft(self):
        design = default_design()
        divider = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        placed = apply_feature_payload({
            "design": design, "feature": divider, "index": None,
        })["design"]
        draft = placed["layout"]["features"][0]
        preview = preview_payload({"design": placed, "draft": draft, "selected": 0})
        self.assertIsNone(preview["draft_error"])
        self.assertFalse(preview["feature_errors"])

    def test_catalog_exposes_slicer_info(self):
        catalog = catalog_payload()
        self.assertIn("slicer", catalog)
        slicer = catalog["slicer"]
        self.assertIn("available", slicer)
        self.assertIn("path", slicer)
        self.assertIn("name", slicer)
        self.assertIsInstance(slicer["available"], bool)

    def test_detect_bambu_studio_finds_configured_and_custom_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()

            # Custom path explicitly supplied
            found = wavefinity_web.detect_bambu_studio(str(fake_exe))
            self.assertEqual(found, fake_exe.resolve())

            # Preferences path
            with patch.object(wavefinity_web, "load_preferences", return_value={"slicer_path": str(fake_exe)}):
                found = wavefinity_web.detect_bambu_studio()
                self.assertEqual(found, fake_exe.resolve())

    def test_launch_slicer_validates_file_and_launches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()
            fake_3mf = Path(temp_dir) / "test.3mf"
            fake_3mf.touch()

            # Empty files list raises ValueError
            with self.assertRaises(ValueError):
                wavefinity_web.launch_slicer(fake_exe, [])

            # Missing executable raises FileNotFoundError
            missing_exe = Path(temp_dir) / "missing.exe"
            with self.assertRaises(FileNotFoundError):
                wavefinity_web.launch_slicer(missing_exe, [fake_3mf])

            # Successful launch
            with patch("subprocess.Popen") as mock_popen:
                wavefinity_web.launch_slicer(fake_exe, [fake_3mf])
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args[0], str(fake_exe.resolve()))
                self.assertEqual(args[1], str(fake_3mf.resolve()))

    def test_print_payload_generates_and_opens_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.touch()
            fake_connector = Path(temp_dir) / "Connector.3mf"
            fake_connector.touch()

            fake_gen_result = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }
            fake_connector_result = {
                "result": {"output": str(fake_connector)},
                "output": str(temp_dir),
            }

            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake_gen_result),
                patch.object(wavefinity_web, "connector_payload", return_value=fake_connector_result),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                patch.object(wavefinity_web, "launch_slicer") as mock_launch,
            ):
                response = wavefinity_web.print_payload({
                    "design": default_design(),
                    "output": temp_dir,
                })
                self.assertEqual(response["output"], str(temp_dir))
                second_connector = fake_connector.with_name("Connector 2.3mf")
                self.assertEqual(response["files"], [
                    str(fake_3mf.resolve()),
                    str(fake_connector.resolve()),
                    str(second_connector.resolve()),
                ])
                self.assertTrue(second_connector.is_file())
                self.assertEqual(response["slicer"], str(fake_exe.resolve()))
                mock_launch.assert_called_once_with(fake_exe, [
                    fake_3mf.resolve(),
                    fake_connector.resolve(),
                    second_connector.resolve(),
                ])

    def test_print_payload_raises_when_no_slicer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.touch()
            fake_gen_result = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }

            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake_gen_result),
                patch.object(wavefinity_web, "connector_payload", return_value={"result": {}, "output": str(temp_dir)}),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=None),
            ):
                with self.assertRaises(ValueError) as ctx:
                    wavefinity_web.print_payload({
                        "design": default_design(),
                        "output": temp_dir,
                    })
                self.assertIn("Bambu Studio was not found", str(ctx.exception))

    def test_browse_slicer_path_saves_preference_and_returns_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "orca-slicer.exe"
            fake_exe.touch()
            with (
                patch("tkinter.Tk"),
                patch("tkinter.filedialog.askopenfilename", return_value=str(fake_exe)),
                patch.object(wavefinity_web, "save_preferences") as mock_save,
            ):
                result = wavefinity_web.browse_slicer_path_payload({"current": str(fake_exe)})
                self.assertEqual(result["slicer_path"], str(fake_exe))
                mock_save.assert_called_once_with({"slicer_path": str(fake_exe)})

    def test_browse_slicer_path_handles_cancel(self):
        with (
            patch("tkinter.Tk"),
            patch("tkinter.filedialog.askopenfilename", return_value=""),
            patch.object(wavefinity_web, "save_preferences") as mock_save,
        ):
            result = wavefinity_web.browse_slicer_path_payload({})
            self.assertIsNone(result["slicer_path"])
            mock_save.assert_not_called()

    def test_2d_layout_arrow_keys_and_movement_hints(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        styles_css = (root / "web" / "styles.css").read_text(encoding="utf-8")

        self.assertIn("Use Arrow keys or drag to move", index_html)
        self.assertIn("handleLayoutArrowKeys", app_js)
        self.assertIn("ArrowUp", app_js)
        self.assertIn("ArrowDown", app_js)
        self.assertIn("ArrowLeft", app_js)
        self.assertIn("ArrowRight", app_js)
        # Shift 10mm, Ctrl 0.1mm, default 1mm
        self.assertIn("step = 10", app_js)
        self.assertIn("step = 0.1", app_js)
        self.assertIn("step = 1", app_js)
        self.assertIn("Shift: 10 mm", app_js)
        self.assertIn("Ctrl: 0.1 mm", app_js)
        self.assertIn("layout-hint", styles_css)

    def test_undo_redo_keyboard_shortcuts_and_titles(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('title="Undo last design change (Ctrl+Z)"', index_html)
        self.assertIn('title="Redo last undone design change (Ctrl+Y or Ctrl+Shift+Z)"', index_html)
        self.assertIn("restoreHistory(event.shiftKey)", app_js)
        self.assertIn("restoreHistory(true)", app_js)
        self.assertIn('event.key.toLowerCase() === "z"', app_js)
        self.assertIn('event.key.toLowerCase() === "y"', app_js)


class WebServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = make_server("127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get(self, path):
        with urlopen(self.base + path, timeout=20) as response:
            return response.status, response.headers, response.read()

    def post(self, path, payload):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())

    def test_health_catalog_and_static_application_are_served(self):
        status, headers, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
        health = json.loads(body)
        self.assertTrue(health["ok"])
        self.assertTrue(health["instance"])
        self.assertEqual(health["instance"], catalog_payload()["instance"])
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Build your bin", body)
        self.assertNotIn(b'id="advanced-settings"', body)
        self.assertNotIn(b'id="advanced-build-settings"', body)
        self.assertIn(b"Base thickness", body)
        self.assertIn(b'id="base-thickness"', body)
        self.assertNotIn(b"Advanced bin settings", body)
        self.assertNotIn(b"Wall / floor", body)
        self.assertNotIn(b"Flat wall band", body)
        self.assertNotIn(b"Label your bin", body)
        self.assertNotIn(b"Rim label", body)
        self.assertIn(b"Interior parts", body)
        self.assertIn(b"Part Name (For file)", body)
        self.assertIn(b"Connect bins", body)
        self.assertIn(b"Save Location:", body)
        self.assertIn(b'id="print-bin"', body)
        self.assertIn(b">Print to Bambu Studio</button>", body)
        self.assertIn(b'id="generate-all"', body)
        self.assertIn(b"Generate Bin and Connectors", body)
        self.assertIn(b'id="generate-bin"', body)
        self.assertIn(b">Generate Bin</button>", body)
        self.assertIn(b'id="generate-connector"', body)
        self.assertIn(b">Generate Connector</button>", body)
        self.assertNotIn(b"generate-sampler", body)
        self.assertNotIn(b"Generate sampler", body)
        self.assertIn(b'id="generation-dialog"', body)
        self.assertIn(b"Different height bins?", body)
        self.assertIn(b"connector-bin-a-height", body)
        self.assertIn(b"connector-arm-thickness", body)
        self.assertIn(b">Bin A <", body)
        self.assertIn(b">Bin B <", body)
        self.assertNotIn(b"This bin (A)", body)
        self.assertNotIn(b"connector-position", body)
        self.assertNotIn(b"connector-axis", body)
        self.assertIn(b"support-layout-dialog", body)
        self.assertNotIn(b"Add curved scoop", body)
        self.assertNotIn(b"Fixed 5 mm lettering on a shelf", body)
        # The interior print-mode dropdown is a universal setting: it sits above
        # the Part Name, which in turn sits above the interior parts section.
        self.assertLess(body.index(b'id="mode-select"'), body.index(b"Part Name (For file)"))
        self.assertLess(body.index(b"Part Name (For file)"), body.index(b"<h2>Interior parts</h2>"))
        self.assertLess(body.index(b"<h2>Interior parts</h2>"), body.index(b"Connect bins"))
        self.assertLess(body.index(b"Connect bins"), body.index(b"Save Location:"))
        # The palette itself is the "add another part" affordance now - there is
        # no separate button. Editing a part shows Save / Delete Part below its
        # settings.
        self.assertNotIn(b'id="add-support"', body)
        self.assertLess(body.index(b'id="support-palette"'), body.index(b'id="draft-fields"'))
        self.assertLess(body.index(b'id="draft-fields"'), body.index(b'id="save-part"'))
        self.assertLess(body.index(b'id="save-part"'), body.index(b'id="delete-part"'))
        self.assertIn(b'id="mode-select"', body)
        self.assertIn(b'data-preview-mode="standard"', body)
        self.assertIn(b'data-preview-mode="xray"', body)
        self.assertIn(b'data-preview-mode="bin"', body)
        self.assertIn(b'data-preview-mode="interior"', body)
        status, _headers, body = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"refreshPreview", body)
        # The page uses a select for print mode. The startup renderer must
        # target that select rather than the retired radio-button container,
        # or initialization aborts before it can request a preview.
        self.assertIn(b'const modes = $("#mode-select")', body)
        self.assertNotIn(b"mode-options", body)
        self.assertIn(b"designMutationBusy", body)
        self.assertIn(b"beginDesignMutation", body)
        self.assertIn(b"finishDesignMutation", body)
        self.assertIn(b"generateParts", body)
        self.assertIn(b"wireGenerationDialog", body)
        self.assertIn(b"previewSupportPolygons", body)
        self.assertIn(b"Upload part photo", body)
        self.assertIn(b".jpg,.jpeg,.png,.webp", body)
        self.assertIn(b"Camera directly overhead", body)
        self.assertIn(b"syncNestZone", body)
        self.assertIn(b'"rotate"', body)
        # The part name is seeded once from the first real piece of lettering,
        # and the bespoke floor-label drag is gone - text is an interior part.
        self.assertIn(b"seedPartNameFromText", body)
        self.assertIn(b"SIZE_LIKE_TEXT", body)
        self.assertIn(b"selectKind(kind);", body)
        self.assertIn(b"kindRequest", body)
        self.assertIn(b"fitRequest", body)
        self.assertIn(b"nestPhotoRequest", body)
        self.assertIn(b"function clearDraftSelection", body)
        self.assertIn(b"placed-item-icon", body)
        self.assertNotIn(b"${index + 1}. ${title}", body)
        self.assertNotIn(b"drawMovableLabel", body)
        self.assertNotIn(b"label_placement", body)
        # Text is inlaid flush with the floor, so the painter sort has only the
        # layer left to break the tie - and a holder arrives under the floor's
        # own layer. Without this lift the lettering is painted over and
        # vanishes, which no Python test can see.
        self.assertIn(b"isLettering", body)
        self.assertIn(b"face.layer = 2", body)
        status, health = self.post("/api/design/validate", {"design": default_design()})
        self.assertEqual(status, 200)
        self.assertEqual(health["design"]["version"], 1)

    def test_bad_design_is_a_clear_400(self):
        request = Request(
            self.base + "/api/preview",
            data=b'{"design":{}}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=20)
        self.assertEqual(caught.exception.code, 400)
        payload = json.loads(caught.exception.read())
        caught.exception.close()
        self.assertIn("error", payload)

    def test_cross_origin_posts_are_refused_before_file_writing_routes(self):
        request = Request(
            self.base + "/api/generate",
            data=json.dumps({"design": default_design()}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Origin": "https://untrusted.example",
            },
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=20)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_print_endpoint_accessible_via_http(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.touch()

            fake_connector = Path(temp_dir) / "Connector.3mf"
            fake_connector.touch()

            fake_gen = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }

            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake_gen),
                patch.object(
                    wavefinity_web, "connector_payload",
                    return_value={"result": {"output": str(fake_connector)}, "output": str(temp_dir)},
                ),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                patch.object(wavefinity_web, "launch_slicer"),
            ):
                status, response = self.post("/api/print", {"design": default_design()})
                self.assertEqual(status, 200)
                self.assertIn("files", response)
                self.assertIn("slicer", response)

    def test_browse_slicer_path_serves_get_and_post(self):
        with (
            patch("tkinter.Tk"),
            patch("tkinter.filedialog.askopenfilename", return_value=r"C:\fake.exe"),
            patch.object(wavefinity_web, "save_preferences"),
        ):
            get_status, _, get_raw = self.get("/api/browse-slicer-path")
            self.assertEqual(get_status, 200)
            self.assertEqual(json.loads(get_raw)["slicer_path"], r"C:\fake.exe")

            post_status, post_body = self.post("/api/browse-slicer-path", {})
            self.assertEqual(post_status, 200)
            self.assertEqual(post_body["slicer_path"], r"C:\fake.exe")



def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class StaleProcessReplacementTests(unittest.TestCase):
    """Relaunching must replace an old process holding the port, not
    silently reattach to it and go on serving whatever code that process
    happened to start with - see TESTING.md, 2026-09-04, "unknown API
    route"."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.pid_file = self.tmp_dir / "wavefinity.pid"
        self.original_pid_file = wavefinity_web.PID_FILE
        wavefinity_web.PID_FILE = self.pid_file
        self.procs: list[subprocess.Popen] = []

    def tearDown(self):
        wavefinity_web.PID_FILE = self.original_pid_file
        for proc in self.procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _spawn_real_server(self, port: int) -> subprocess.Popen:
        script = Path(wavefinity_web.__file__).resolve()
        env = dict(os.environ, WAVEFINITY_PID_FILE=str(self.pid_file))
        proc = subprocess.Popen(
            [sys.executable, str(script), "--port", str(port), "--no-browser"],
            cwd=str(script.parent), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(proc)
        url = f"http://127.0.0.1:{port}/"
        for _ in range(100):
            try:
                with urlopen(url + "api/health", timeout=0.3) as response:
                    if json.loads(response.read()).get("ok"):
                        return proc
            except Exception:
                pass
            time.sleep(0.1)
        self.fail("spawned Wavefinity process never answered its health check")

    def test_a_process_this_launcher_started_is_replaced_not_reattached_to(self):
        port = _free_port()
        proc = self._spawn_real_server(port)
        # on Windows, python.exe under a venv is itself a small launcher
        # that execs a child running the real interpreter, so the pid this
        # app records (its own os.getpid(), from inside that child) need
        # not equal subprocess.Popen's pid for the launcher - only that a
        # real pid was recorded at all.
        self.assertGreater(int(self.pid_file.read_text(encoding="utf-8").strip()), 0)

        replaced = wavefinity_web._replace_stale_process(f"http://127.0.0.1:{port}/", "127.0.0.1", port)
        self.assertTrue(replaced)
        self.assertIsNotNone(proc.wait(timeout=5))  # actually terminated, not just unresponsive

        fresh = wavefinity_web.make_server("127.0.0.1", port)  # the port is genuinely free again
        fresh.server_close()

    def test_a_stale_pid_file_cannot_target_an_unrelated_process(self):
        self.pid_file.write_text("456", encoding="utf-8")
        response = MagicMock()
        response.read.return_value = b'{"ok": true}'
        response.__enter__.return_value = response
        with (
            patch.object(wavefinity_web, "urlopen", side_effect=[response, OSError()]),
            patch.object(wavefinity_web, "_pid_on_port", return_value=123),
            patch.object(wavefinity_web.os, "kill") as kill,
            patch.object(wavefinity_web.subprocess, "run") as run,
            patch.object(wavefinity_web.time, "sleep"),
        ):
            self.assertTrue(wavefinity_web._replace_stale_process(
                "http://127.0.0.1:8765/", "127.0.0.1", 8765
            ))
            if os.name == "nt":
                self.assertIn("123", run.call_args[0][0])
            else:
                self.assertEqual(kill.call_args.args[0], 123)

    def test_a_service_with_no_recorded_pid_is_still_found_and_replaced(self):
        # An older server predating wavefinity.pid, or one started some
        # other way, never wrote this test's PID_FILE - the OS-level
        # fallback in _pid_on_port must still find and safely replace it.
        # A real subprocess, not an in-thread server: the fallback finds
        # whatever the OS says holds the port, so an in-thread server would
        # have this very test process's own pid killed instead.
        port = _free_port()
        script = Path(wavefinity_web.__file__).resolve()
        decoy_pid_file = self.tmp_dir / "a-different-process-wrote-this.pid"
        env = dict(os.environ, WAVEFINITY_PID_FILE=str(decoy_pid_file))
        proc = subprocess.Popen(
            [sys.executable, str(script), "--port", str(port), "--no-browser"],
            cwd=str(script.parent), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(proc)
        url = f"http://127.0.0.1:{port}/"
        for _ in range(100):
            try:
                with urlopen(url + "api/health", timeout=0.3) as response:
                    if json.loads(response.read()).get("ok"):
                        break
            except Exception:
                pass
            time.sleep(0.1)
        else:
            self.fail("spawned Wavefinity process never answered its health check")
        self.assertFalse(self.pid_file.exists())  # this test's own PID_FILE, untouched

        replaced = wavefinity_web._replace_stale_process(url, "127.0.0.1", port)
        self.assertTrue(replaced)
        self.assertIsNotNone(proc.wait(timeout=5))

    def test_an_unrelated_service_on_the_port_is_left_alone(self):
        # Something real answers, but not as a Wavefinity service - the
        # health-check schema is what draws the actual safety line, not
        # merely "does anything respond."
        port = _free_port()
        proc = subprocess.Popen(
            [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self.procs.append(proc)
        url = f"http://127.0.0.1:{port}/"
        for _ in range(50):
            try:
                urlopen(url, timeout=0.3)
                break
            except Exception:
                time.sleep(0.1)
        replaced = wavefinity_web._replace_stale_process(url, "127.0.0.1", port)
        self.assertFalse(replaced)
        self.assertIsNone(proc.poll())  # still running, untouched

    def test_nothing_answering_the_port_is_reported_as_not_replaced(self):
        port = _free_port()
        self.pid_file.write_text("999999", encoding="utf-8")
        replaced = wavefinity_web._replace_stale_process(f"http://127.0.0.1:{port}/", "127.0.0.1", port)
        self.assertFalse(replaced)

    def test_two_separately_started_processes_report_different_instances(self):
        # SERVER_INSTANCE is regenerated per process, not per code version, so
        # the frontend's staleness banner (web/app.js watchServerVersion)
        # fires on *any* restart, not just ones that bumped SERVER_VERSION.
        first_port, second_port = _free_port(), _free_port()
        first = self._spawn_real_server(first_port)
        second = self._spawn_real_server(second_port)
        with urlopen(f"http://127.0.0.1:{first_port}/api/health", timeout=2) as response:
            first_instance = json.loads(response.read())["instance"]
        with urlopen(f"http://127.0.0.1:{second_port}/api/health", timeout=2) as response:
            second_instance = json.loads(response.read())["instance"]
        self.assertTrue(first_instance)
        self.assertTrue(second_instance)
        self.assertNotEqual(first_instance, second_instance)


if __name__ == "__main__":
    unittest.main()
