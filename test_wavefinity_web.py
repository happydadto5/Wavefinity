"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

import inspect
import json
import math
import os
from dataclasses import replace
from pathlib import Path
import re
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
import organizer_app
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
    nest_trace_payload,
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


class ObjectReferenceWebTests(unittest.TestCase):
    def test_reference_edit_endpoint_changes_only_reference(self):
        design = default_design()
        design["box"].update({"x": 64, "y": 64, "z": 40})
        feature = default_feature_payload({"design": design, "kind": "post"})["feature"]
        design["layout"]["features"] = [feature]
        edited = json.loads(json.dumps(feature))
        edited["reference_object"] = {"width": 6, "depth": 8, "height": 60}
        result = wavefinity_web.apply_reference_payload({"design": design, "feature": edited, "index": 0})
        self.assertEqual(result["design"]["layout"]["features"][0]["reference_object"], edited["reference_object"])
        removed = json.loads(json.dumps(edited))
        removed.pop("reference_object")
        after = wavefinity_web.apply_reference_payload({"design": result["design"],
                                                        "feature": removed, "index": 0})
        self.assertNotIn("reference_object", after["design"]["layout"]["features"][0])
        bad = json.loads(json.dumps(edited))
        bad["zone"] = [-12, -12, 12, 12]
        with self.assertRaisesRegex(ValueError, "printable holder"):
            wavefinity_web.apply_reference_payload({"design": design, "feature": bad, "index": 0})

    def test_ai_reference_rules_are_explicit_and_reject_wrong_kind(self):
        manifest = wavefinity_web.ai_capability_manifest()
        allowed = {part["kind"] for part in manifest["features"]
                   if "reference_object" in part.get("generic_fields", {})}
        self.assertEqual(allowed, {"pocket", "post", "slot", "steps"})
        design = default_design()
        design["part_name"] = "Tools"
        bore = default_feature_payload({"design": design, "kind": "bore"})["feature"]
        bore["reference_object"] = {"width": 1, "depth": 1, "height": 1}
        design["layout"]["features"] = [bore]
        self.assertIn("reference_object", wavefinity_web._ai_semantic_violation(design))

    def test_generic_preview_is_draft_owned_and_reference_does_not_print(self):
        design = default_design()
        design["box"].update({"x": 64, "y": 64, "z": 40})
        feature = default_feature_payload({"design": design, "kind": "post"})["feature"]
        feature["reference_object"] = {"width": 6, "depth": 8, "height": 60}
        design["layout"]["features"] = [feature]
        saved = preview_payload({"design": design, "client_id": "reference-test", "generation": 1})
        saved_faces = [face for face in saved["geometry"] if face["kind"] == "reference_object"]
        self.assertTrue(saved_faces)
        self.assertTrue(all(face["pick"] is None for face in saved_faces))
        draft = json.loads(json.dumps(feature))
        draft["reference_object"]["height"] = 80
        live = preview_payload({"design": design, "draft": draft, "selected": 0,
                                "client_id": "reference-test", "generation": 2})
        reference_z = max(point[2] for face in live["geometry"]
                          if face["kind"] == "reference_object" for point in face["points"])
        self.assertAlmostEqual(reference_z, design["box"]["base_thickness"] + 80)
        self.assertEqual(live["design"]["layout"]["features"][0]["reference_object"]["height"], 60)

    def test_tilted_bore_radius_crosses_cap_for_manual_and_ai_only(self):
        from organizer_inserts._bore import bore_reference_top
        design = default_design()
        design["box"].update({"x": 128, "y": 128, "z": 80})
        feature = default_feature_payload({"design": design, "kind": "bore"})["feature"]
        feature["zone"] = [-22, -22, 22, 22]
        feature["item"]["segments"] = [{"length": 50, "diameter": 16}]
        feature["options"] = {"bore_style": "base_straight", "height": 28,
                              "depth": 20, "angle": 35, "columns": 1, "rows": 1}
        design["layout"]["features"] = [feature]
        box, layout, *_ = design_from_dict(design)
        top = bore_reference_top(box, layout.features[0], base_height(box, layout.mode))
        centreline = box.base_thickness + 28 + 30 * math.cos(math.radians(35))
        cap = (centreline + top) / 2
        result = preview_payload({"design": design, "space": {"kind": "drawer", "z": cap},
                                  "client_id": "cap-test", "generation": 1})
        self.assertGreater(result["bore_ceiling_warning"]["top_mm"], cap)
        self.assertTrue(result["fits"])
        self.assertFalse(result["draft_error"])
        self.assertIsNotNone(wavefinity_web._ai_space_cap_violation(result["design"], {"kind": "drawer", "z": cap}))
        self.assertIsNone(wavefinity_web._ai_space_cap_violation(result["design"], {"kind": "surface", "z": cap}))
        self.assertIsNone(wavefinity_web._ai_space_cap_violation(result["design"], {"kind": "pegboard", "z": cap}))
        self.assertIsNone(wavefinity_web._ai_space_cap_violation(
            result["design"], {"kind": "drawer", "z": math.ceil(top * 1000) / 1000}))

    def test_stacked_bore_manual_and_ai_use_the_same_physical_body(self):
        from organizer_stack import stack_effective_box
        design = default_design()
        design["box"].update({"x": 128, "y": 128, "z": 80, "stack": {"mode": "direct"}})
        feature = default_feature_payload({"design": design, "kind": "bore"})["feature"]
        feature["zone"] = [-22, -22, 22, 22]
        feature["item"]["segments"] = [{"length": 50, "diameter": 16}]
        feature["options"] = {"bore_style": "base_straight", "height_size_mode": "bore_to_bin",
                              "depth": 20, "angle": 35, "columns": 1, "rows": 1}
        design["layout"]["features"] = [feature]
        box, layout, *_ = design_from_dict(design)
        physical_box = stack_effective_box(box)
        # The existing tilted-Bore test covers mesh-top geometry. Here a
        # lightweight top spy isolates which physical box each caller passes.
        raw_top = box.z + 10
        physical_top = physical_box.z + 10
        self.assertGreater(physical_top, raw_top)
        cap = (raw_top + physical_top) / 2
        space = {"kind": "drawer", "z": cap}
        with patch.object(wavefinity_web, "bore_reference_top", side_effect=lambda box, *_: box.z + 10):
            warning = wavefinity_web._capped_bore_warning(box, layout, layout.features, space)
        self.assertAlmostEqual(warning["top_mm"], math.ceil(physical_top * 1000) / 1000)
        with patch.object(wavefinity_web, "bore_reference_top", side_effect=lambda box, *_: box.z + 10):
            self.assertIn(f"{physical_top:.3f}", wavefinity_web._ai_space_cap_violation(design, space))
        clear_space = {"kind": "drawer", "z": math.ceil(physical_top * 1000) / 1000}
        with patch.object(wavefinity_web, "bore_reference_top", side_effect=lambda box, *_: box.z + 10):
            self.assertIsNone(wavefinity_web._capped_bore_warning(box, layout, layout.features, clear_space))
        with patch.object(wavefinity_web, "bore_reference_top", side_effect=lambda box, *_: box.z + 10):
            self.assertIsNone(wavefinity_web._ai_space_cap_violation(design, clear_space))

    def test_text_duplicate_endpoint_now_serves_photo_nest_only(self):
        # Fix 082 J retires Text's own Duplicate to rim; the shared endpoint
        # rejects a Text index instead of cloning it to a rim side.
        design = default_design()
        design["box"].update({"x": 64, "y": 64, "z": 40})
        design["layout"]["features"] = [_text_feature("Tools")]
        preview = preview_payload({"design": design, "client_id": "duplicate-test", "generation": 1})
        self.assertNotIn("duplicate_text_indexes", preview)
        with self.assertRaisesRegex(ValueError, "Photo Nest"):
            wavefinity_web.duplicate_feature_payload({"design": design, "index": 0})


def _traced_photo_nest_payload(payload):
    """photo_nest_payload() now only finalizes an already-traced contour
    (see nest_trace_payload) - it never decodes/retraces a photo itself.
    This runs both phases together, as the browser's own two-step flow
    would, for tests that mock photo_outline_from_data and just want the
    finished result."""
    traced = nest_trace_payload({
        "image": payload.get("image", ""),
        "mime_type": payload.get("mime_type", ""),
    })
    finalize = {**payload, "contour": traced["contour"]}
    result = photo_nest_payload(finalize)
    result["reference"] = traced.get("reference")
    result["trace_outline"] = traced["outline"]
    return result


def _fix21_photo_design(*, contour=None, options=None):
    contour = contour or ((-20.0, -8.0), (20.0, -8.0), (20.0, 8.0), (-20.0, 8.0))
    return photo_nest_payload({
        "design": default_design(),
        "contour": [list(point) for point in contour],
        "options": {"depth": 5.0, **(options or {})},
    })


class WebApplicationTests(unittest.TestCase):

    def test_catalog_exposes_every_interior_part_and_safe_default_design(self):
        catalog = catalog_payload()
        parts = {part["kind"]: part for part in catalog["parts"]}
        self.assertEqual(
            set(parts),
            {"divider", "post", "pocket", "bore", "cradle", "nest", "slot",
             "steps", "scoop", "text", "lid_stacking", "inside_handles",
             "side_openings", "edge_mount"},
        )
        self.assertTrue(all("max_instances" in part for part in parts.values()))
        self.assertTrue(all("palette_visible" in part for part in parts.values()))
        self.assertFalse(parts["pocket"]["palette_visible"])
        for kind in ("lid_stacking", "inside_handles", "side_openings", "edge_mount"):
            self.assertEqual(parts[kind]["max_instances"], 1)
            self.assertTrue(parts[kind]["palette_visible"])
            self.assertIn("box_modifier", parts[kind]["capabilities"])
        self.assertEqual(parts["scoop"]["title"], "Curved Scoop")
        self.assertEqual(parts["scoop"]["icon"], "scoop")
        self.assertFalse(parts["scoop"]["flags"]["size"])
        self.assertFalse(parts["scoop"]["flags"]["along"])
        self.assertEqual(
            [(field["label"], field["key"], field["default"])
             for field in parts["scoop"]["fields"]],
            [("Depth", "depth", "60")],
        )
        self.assertEqual(parts["scoop"]["fields"][0]["type"], "number")
        self.assertIn("item", parts["bore"]["capabilities"])
        # Options may also carry legal-value metadata (choices/range/note); the key
        # and type stay exactly as declared.
        self.assertIn(
            ("angle_towards", "enum"),
            [(one["key"], one["type"]) for one in parts["bore"]["options"]],
        )
        interactions = catalog["setting_interactions"]
        self.assertTrue(all(rule["feature"] for rule in interactions))
        self.assertTrue(any(
            rule["source"] == "scoop.depth"
            and rule["target"] == "scoop.height"
            and rule["owner"] == "scoop"
            for rule in interactions
        ))
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
        # Box modifiers share the catalog lifecycle but do not become Layout features.
        self.assertIn("side_openings", parts)


    def test_side_opening_validation_round_trips_the_block(self):
        design = default_design()
        design["box"]["x"] = design["box"]["y"] = 48.0
        design["box"]["side_openings"] = {
            "enabled": True, "shape": "curved", "sides": ["front", "left"],
            "size": "medium", "from_bottom_percent": 0.0,
            "from_top_percent": 0.0, "percent_mode": "inset_v2",
        }
        preview = preview_payload({"design": design})
        self.assertTrue(preview["fits"], preview["message"])
        self.assertEqual(
            preview["design"]["box"]["side_openings"],
            design["box"]["side_openings"],
        )
        self.assertTrue(any(row["kind"] == "outside" for row in preview["geometry"]))

    def test_side_opening_preview_uses_real_cut_geometry(self):
        design = default_design()
        design["box"]["x"] = design["box"]["y"] = 48.0
        without = preview_payload({"design": design})
        design["box"]["side_openings"] = {
            "enabled": True, "shape": "curved", "sides": ["front"],
            "size": "medium", "from_bottom_percent": 0.0,
            "from_top_percent": 0.0, "percent_mode": "inset_v2",
        }
        with_opening = preview_payload({"design": design})
        self.assertTrue(with_opening["fits"], with_opening["message"])
        # A real cut body has far fewer "outside" triangles filling the flat
        # wall than the ordinary synthesized quad walls, and specifically
        # fewer than the same design without the opening.
        without_outside = sum(1 for row in without["geometry"] if row["kind"] == "outside")
        with_outside = sum(1 for row in with_opening["geometry"] if row["kind"] == "outside")
        self.assertGreater(without_outside, 0)
        self.assertGreater(with_outside, 0)
        self.assertNotEqual(without_outside, with_outside)

    def test_invalid_1u_side_selection_is_rejected(self):
        design = default_design()
        design["box"]["x"] = 8.0
        design["box"]["y"] = 48.0
        design["box"]["side_openings"] = {
            "enabled": True, "shape": "curved", "sides": ["front"],
            "size": "small", "from_bottom_percent": 0.0,
            "from_top_percent": 0.0, "percent_mode": "inset_v2",
        }
        with self.assertRaises(ValueError):
            preview_payload({"design": design})













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
        with (
            patch.object(wavefinity_web, "generate_side_file", return_value={}) as generate,
            patch.object(wavefinity_web, "generate_corner_file", return_value={}),
        ):
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
        with (
            patch.object(wavefinity_web, "generate_side_file", return_value={}) as generate,
            patch.object(wavefinity_web, "generate_corner_file", return_value={}),
        ):
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


    def test_same_height_connector_payload_generates_the_full_automatic_bundle(self):
        with (
            patch.object(wavefinity_web, "generate_side_file", return_value={"output": "side.3mf"}) as side,
            patch.object(wavefinity_web, "generate_corner_file", return_value={"output": "corner.3mf"}) as corner,
        ):
            result = wavefinity_web.connector_payload({"design": default_design()})
        side.assert_called_once()
        self.assertEqual(corner.call_count, 2)
        corner_ways = sorted(call.args[3] for call in corner.call_args_list)
        self.assertEqual(corner_ways, [3, 4])
        self.assertEqual(set(result["result"]), {"side", "three_way", "four_way"})
        plan = result["connector_plan"]
        self.assertEqual(plan["mode"], "auto")
        self.assertEqual(set(plan["types"]), {"side", "three_way", "four_way"})
        self.assertFalse(plan["different_heights"])
        self.assertNotIn("skipped_types", plan)

    def test_different_height_connector_payload_generates_side_only(self):
        with (
            patch.object(wavefinity_web, "generate_side_file", return_value={"output": "side.3mf"}),
            patch.object(wavefinity_web, "generate_corner_file") as corner,
        ):
            result = wavefinity_web.connector_payload({
                "design": default_design(),
                "connector": {"different_heights": True, "bin_a_height": 40.0, "bin_b_height": 20.0},
            })
        corner.assert_not_called()
        self.assertEqual(set(result["result"]), {"side"})
        plan = result["connector_plan"]
        self.assertEqual(plan["types"], ["side"])
        self.assertTrue(plan["different_heights"])

    def test_ineligible_corner_size_still_generates_side_and_reports_skipped_types(self):
        design = default_design()
        # 8 mm is one Wavefinity unit - below MIN_JOINABLE_SIZE (16 mm), so the
        # real corner geometry must refuse it while the Side connector, which
        # has no such minimum, still succeeds.
        design["box"]["x"] = 8.0
        with patch.object(wavefinity_web, "generate_side_file", return_value={"output": "side.3mf"}):
            result = wavefinity_web.connector_payload({"design": design})
        self.assertEqual(set(result["result"]), {"side"})
        plan = result["connector_plan"]
        self.assertEqual(plan["types"], ["side"])
        self.assertEqual(sorted(plan["skipped_types"]), ["four_way", "three_way"])

    def test_connector_payload_rejects_base_trim_design_not_join_preference(self):
        with self.assertRaises(ValueError) as ctx:
            wavefinity_web.connector_payload({"design": {"design_kind": "base_trim"}})
        self.assertIn("Base Trim", str(ctx.exception))

    def test_default_draft_changes_real_geometry_when_height_changes(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        low = draft_payload({"design": design, "feature": feature})
        low_top = max(point[2] for face in low["geometry"] for point in face["points"])
        feature["options"]["height"] = 28.0
        high = draft_payload({"design": design, "feature": feature})
        high_top = max(point[2] for face in high["geometry"] for point in face["points"])
        self.assertGreater(high_top, low_top + 4.0)



    def test_photo_upload_creates_one_contour_and_only_grows_the_grid_bin(self):
        outline = PhotoOutline(
            ((-40, -10), (40, -10), (35, 10), (-40, 10)),
            80.0, 20.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
            "data:image/jpeg;base64,dGVzdA==", (-50.0, -20.0, 50.0, 20.0),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            result = _traced_photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {
                    "clearance": 1.0, "depth": 9.0, "rim": 4.0,
                    # Push Out needs a Raised Wall holder - with the default
                    # Recessed style it is auto-corrected back to Automatic.
                    "holder_style": "raised_wall",
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
        # "depth" in the request maps to the stored "tool_thickness".
        self.assertEqual(feature["options"]["tool_thickness"], 9.0)
        self.assertEqual(feature["contour"], [list(point) for point in outline.contour])
        self.assertNotIn("image", json.dumps(design).lower())
        self.assertEqual(result["reference"]["bounds"], [-50.0, -20.0, 50.0, 20.0])
        self.assertEqual(design["box"]["x"] % 8.0, 0.0)
        self.assertEqual(design["box"]["y"] % 8.0, 0.0)
        # A from-scratch scan sizes the bin to what the traced photo actually
        # needs, not to the arbitrary blank template it started from - it can
        # shrink an axis the template overshot as freely as it grows one the
        # template undershot. The one real invariant is that the outline
        # (80 x 20 mm here) still fits inside the resulting grid bin.
        self.assertGreaterEqual(design["box"]["x"], 80.0)
        self.assertGreaterEqual(design["box"]["y"], 20.0)
        box, layout, *_ = design_from_dict(design)
        preview = preview_payload({"design": design})
        self.assertFalse(preview["feature_errors"])
        self.assertTrue(preview["feature_outlines"][0])
        self.assertTrue(preview["nest_soft_contours"][0])

        # Photo Nest auto-sizing now only grows the footprint (X/Y). A
        # Raised Wall holder is allowed to rise above a shallow bin's rim,
        # so Bin Height no longer auto-grows to fit a taller tool.
        feature["options"]["lift_assist"] = "none"
        feature["options"]["tool_thickness"] = 50.0
        taller = apply_feature_payload({
            "design": design, "feature": feature, "index": 0,
        })["design"]
        self.assertEqual(taller["box"]["z"], design["box"]["z"])

    def test_preview_softened_contour_follows_the_soften_outline_value(self):
        notched = PhotoOutline(
            ((-20, -8), (-4, -8), (-4, -1), (4, -1), (4, -8),
             (20, -8), (20, 8), (-20, 8)),
            40.0, 16.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=notched):
            design = _traced_photo_nest_payload({
                "design": default_design(), "image": "x", "mime_type": "image/png",
                "options": {"depth": 5.0},
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
            made = _traced_photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {"depth": 5.0},
            })
        feature = made["design"]["layout"]["features"][0]
        old_x = made["design"]["box"]["x"]
        feature["options"]["clearance"] = 5.0
        changed = apply_feature_payload({"design": made["design"], "feature": feature, "index": 0})
        self.assertGreater(changed["design"]["box"]["x"], old_x)



    def test_photo_nest_duplicate_creates_an_independent_second_copy(self):
        outline = PhotoOutline(
            ((-20, -8), (20, -8), (20, 8), (-20, 8)), 40.0, 16.0,
            ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            made = _traced_photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {"depth": 5.0},
            })
        duplicate = wavefinity_web.duplicate_feature_payload({
            "design": made["design"], "index": 0,
        })
        features = duplicate["design"]["layout"]["features"]
        self.assertEqual(len(features), 2)
        self.assertEqual(duplicate["selected"], 1)
        self.assertEqual(features[0]["contour"], features[1]["contour"])
        self.assertNotEqual(features[0]["zone"], features[1]["zone"])














    def test_add_update_delete_round_trip_uses_design_schema(self):
        # A "divider" is full_span: its saved zone always snaps back to the
        # bin's whole floor extent regardless of what is requested (it has
        # no user-sized footprint), so it cannot exercise a zone edit
        # surviving the round trip. "post" is an ordinary, user-sized part.
        design = default_design()
        design["box"]["x"] = 48.0
        design["box"]["y"] = 48.0
        feature = default_feature_payload({"design": design, "kind": "post"})["feature"]
        added = apply_feature_payload({"design": design, "feature": feature, "index": None})
        self.assertEqual(added["selected"], 0)
        self.assertEqual(len(added["design"]["layout"]["features"]), 1)
        updated_feature = added["design"]["layout"]["features"][0]
        updated_feature["zone"] = [-6.0, -6.0, 6.0, 6.0]
        updated = apply_feature_payload({
            "design": added["design"], "feature": updated_feature, "index": 0,
        })
        saved = updated["design"]["layout"]["features"][0]
        self.assertEqual(saved["zone"][2] - saved["zone"][0], 12.0)
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
        # A "divider" is full_span, so its saved zone always follows the
        # bin's whole floor extent (the assignment below is never honored) -
        # tall enough that a 20-degree slope across that full ~93 mm run
        # still fits under the divider's own resolved height.
        design["box"]["z"] = 60.0
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



    def test_enabled_divider_scoop_applies_to_every_cell_after_browser_round_trip(self):
        design = default_design()
        design["box"]["x"] = 48.0
        design["box"]["y"] = 48.0
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["options"] = {
            "count_x": 1,
            "count_y": 1,
            "scoop": {"depth": 45, "cells": ["r0c1", "r1c0"]},
        }
        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        saved = applied["design"]["layout"]["features"][0]
        self.assertEqual(saved["options"]["scoop"], {"depth": 45})
        drafted = draft_payload({"design": applied["design"], "feature": saved})
        self.assertEqual(len(drafted["divider_cells"]), 4)
        self.assertEqual(
            {cell["id"] for cell in drafted["divider_cells"] if cell["scoop"]},
            {"r0c0", "r0c1", "r1c0", "r1c1"},
        )
        self.assertTrue(drafted["geometry"])

    def test_old_divider_cell_targets_migrate_to_all_cells(self):
        design = default_design()
        design["box"]["x"] = 48.0
        design["box"]["y"] = 48.0
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["options"] = {
            "count_x": 1,
            "count_y": 0,
            "scoop": {"cells": ["r0c0", "r1c1"]},
        }
        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        saved = applied["design"]["layout"]["features"][0]
        self.assertEqual(saved["options"]["scoop"], {})

    def test_divider_scoop_and_sloped_bottom_are_mutually_exclusive_on_save(self):
        design = default_design()
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["options"].update({
            "scoop": {"depth": 50},
            "slope_base": True,
            "bottom_angle": 20,
            "alternate_bottom": True,
            "minimal_bottom": True,
            "bottom_supports": 3,
            "division_side": "left",
        })
        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        saved = applied["design"]["layout"]["features"][0]["options"]
        self.assertEqual(saved["scoop"], {"depth": 50})
        for key in (
            "slope_base", "bottom_angle", "alternate_bottom",
            "minimal_bottom", "bottom_supports",
        ):
            self.assertNotIn(key, saved)
        self.assertEqual(saved["division_side"], "left")


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
        feature["zone"] = [-16.0, -46.0, 16.0, 10.0]
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

    def _sized_bore(self, design, **options):
        feature = default_feature_payload({
            "design": design, "kind": "bore",
            "item": {"name": "tube", "profile": "round", "clearance": 0.25,
                     "segments": [{"length": 40.0, "diameter": 20.0}]},
        })["feature"]
        feature["options"] = {"height": 20.0, "depth": 14.0, **options}
        return feature

    def test_bin_to_bore_width_length_fits_the_smallest_bin_around_the_bore(self):
        for style in ("walls_wavy", "walls_straight", "base_straight", "base_wavy"):
            with self.subTest(style=style):
                design = default_design()
                design["box"].update({"x": 160.0, "y": 160.0})
                feature = self._sized_bore(
                    design, bore_style=style, xy_size_mode="bin_to_bore", columns=2, rows=1)
                feature["zone"] = [-40.0, -40.0, 40.0, 40.0]
                design["layout"]["features"] = [feature]
                # The browser holds a bin_to_bore zone at its minimum footprint.
                fitted = feature_fit_payload({"design": design, "feature": feature})["feature"]
                design["layout"]["features"] = [fitted]
                answer = draft_payload({"design": design, "feature": fitted, "index": 0})
                cheap = answer["bore_bin"]
                expanded = expand_layout_payload({"design": design, "anchor": 0, "fit": True})
                # The cheap answer the browser polls and the exact fit agree,
                # and the bin really shrank around the Bore.
                self.assertEqual((expanded["box"]["x"], expanded["box"]["y"]),
                                 (cheap["x"], cheap["y"]))
                self.assertLess(expanded["box"]["x"], 160.0)
                self.assertTrue(expanded["changed"])
                preview = preview_payload({"design": expanded["design"]})
                self.assertFalse(preview["feature_errors"])
                # A later Bore edit (more holes) grows the requested bin again.
                more = dict(fitted, options={**fitted["options"], "columns": 4})
                more = feature_fit_payload({"design": design, "feature": more})["feature"]
                design2 = {**design, "layout": {**design["layout"], "features": [more]}}
                bigger = draft_payload({"design": design2, "feature": more, "index": 0})["bore_bin"]
                self.assertGreater(bigger["x"], cheap["x"])
                # Manual Bores never ask for a bin.
                manual = dict(fitted, options={**fitted["options"], "xy_size_mode": "manual"})
                self.assertNotIn("bore_bin", draft_payload({
                    "design": design, "feature": manual, "index": 0}))

    def test_bin_to_bore_height_reports_and_resizes_the_bin_height(self):
        design = default_design()
        design["box"].update({"x": 96.0, "y": 96.0, "z": 60.0})
        feature = self._sized_bore(design, bore_style="base_straight", height=30.0, depth=20.0,
                                   height_size_mode="bin_to_bore")
        feature["zone"] = [-20.0, -20.0, 20.0, 20.0]
        design["layout"]["features"] = [feature]
        answer = draft_payload({"design": design, "feature": feature, "index": 0})
        self.assertEqual(answer["resolved_options"]["height"], 30.0)   # stored Height is authoritative
        wanted = answer["bore_bin_height"]
        expanded = expand_layout_payload({
            "design": design, "anchor": 0, "fit_height_to_bore": True})
        self.assertEqual(expanded["box"]["z"], wanted)
        self.assertLess(expanded["box"]["z"], 60.0)
        # A taller Bore asks for a taller bin, through the same Space maximum rule.
        tall = dict(feature, options={**feature["options"], "height": 50.0, "depth": 40.0})
        design["layout"]["features"] = [tall]
        self.assertGreater(
            draft_payload({"design": design, "feature": tall, "index": 0})["bore_bin_height"], wanted)
        with self.assertRaisesRegex(ValueError, "maximum height"):
            expand_layout_payload({"design": design, "anchor": 0,
                                   "fit_height_to_bore": True, "max_height": 40.0})
        # Other Height modes never report a bin height.
        for mode in ("manual", "bore_to_bin"):
            other = dict(feature, options={**feature["options"], "height_size_mode": mode})
            self.assertNotIn("bore_bin_height", draft_payload({
                "design": design, "feature": other, "index": 0}))

    def test_bore_to_bin_modes_follow_the_bin_through_the_payloads(self):
        design = default_design()
        design["box"].update({"x": 96.0, "y": 88.0, "z": 60.0})
        feature = self._sized_bore(design, bore_style="base_straight", xy_size_mode="bore_to_bin",
                                   height_size_mode="bore_to_bin", height=5.0)
        feature["zone"] = [-8.0, -8.0, 8.0, 8.0]
        design["layout"]["features"] = [feature]
        first = draft_payload({"design": design, "feature": feature, "index": 0})
        inside = first["feature"]["zone"]
        self.assertNotIn("height", first["feature"]["options"])      # hidden Height never wins
        self.assertGreater(inside[2] - inside[0], 80.0)
        # Growing the bin later grows the Base and lets the Height follow the new bin.
        design["box"].update({"x": 128.0, "y": 96.0, "z": 72.0})
        later = draft_payload({"design": design, "feature": first["feature"], "index": 0})
        self.assertGreater(later["feature"]["zone"][2] - later["feature"]["zone"][0],
                           inside[2] - inside[0] + 20.0)
        self.assertGreater(later["resolved_options"]["height"], first["resolved_options"]["height"])
        # Applying keeps the exact derived zone (no snapping shrink).
        applied = apply_feature_payload({"design": design, "feature": first["feature"], "index": 0})
        saved = applied["design"]["layout"]["features"][0]["zone"]
        self.assertAlmostEqual(saved[2] - saved[0], later["feature"]["zone"][2] - later["feature"]["zone"][0], places=6)



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
        self.assertEqual(preview["design"]["layout"]["features"][0]["options"]["level"], "rim")
        self.assertTrue(any(face["kind"] == "feature_text" for face in preview["geometry"]))
        self.assertEqual(preview["design"]["label"], "")

    def test_text_part_rim_shelf_uses_its_selected_side(self):
        design = default_design()
        design["box"].update({"x": 64.0, "y": 48.0})
        design["layout"]["features"] = [
            _text_feature("M3", level="rim", rim_side="right")
        ]
        preview = preview_payload({"design": design})
        self.assertEqual(preview["design"]["layout"]["features"][0]["options"]["rim_side"], "right")
        xs = [point[0] for face in preview["geometry"] if face["kind"] == "feature_text"
              for point in face["points"]]
        self.assertGreater(min(xs), 0.0)

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
        self.assertFalse(said["auto"])
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
        saved_zone = preview["design"]["layout"]["features"][0]["zone"]
        self.assertAlmostEqual((saved_zone[0] + saved_zone[2]) / 2, 0)
        self.assertAlmostEqual((saved_zone[1] + saved_zone[3]) / 2, 11)
        self.assertFalse(preview["text_meta"][0]["auto"])

    def test_a_second_base_text_is_refused(self):
        design = default_design()
        design["box"]["x"] = 48.0
        for said in ("M3",):
            feature = default_feature_payload(
                {"design": design, "kind": "text", "along": "x", "item": None}
            )["feature"]
            feature["options"]["text"] = said
            design = apply_feature_payload(
                {"design": design, "feature": feature, "index": None}
            )["design"]
        feature = default_feature_payload({"design": design, "kind": "text"})["feature"]
        feature["options"]["text"] = "M4"
        with self.assertRaisesRegex(ValueError, "Only one Text"):
            apply_feature_payload({"design": design, "feature": feature})

    def test_legacy_multiple_rim_texts_remain_loadable_but_preview_rejects_them(self):
        design = default_design()
        design["box"].update({"x": 48.0, "y": 48.0})
        design["layout"]["features"] = [
            _text_feature("A", zone=(-20, 6, 20, 15), level="rim", rim_side="back"),
            _text_feature("B", zone=(-20, -15, 20, -6), level="rim", rim_side="front"),
        ]
        before = json.dumps(design, sort_keys=True)
        _box, layout, *_rest = design_from_dict(design, validate_layout=False)
        self.assertEqual(len(layout.features), 2)
        self.assertEqual(json.dumps(design, sort_keys=True), before)
        with self.assertRaisesRegex(ValueError, "Only one rim Text"):
            preview_payload({"design": design})
        self.assertEqual(json.dumps(design, sort_keys=True), before)

    def test_a_draft_text_uses_canonical_geometry(self):
        design = default_design()
        design["box"]["x"] = 48.0
        design["layout"]["features"] = [_text_feature("M3", auto=True)]
        design = preview_payload({"design": design})["design"]
        draft = default_feature_payload(
            {"design": design, "kind": "text", "along": "x", "item": None}
        )["feature"]
        draft["options"].update(text="M4", level="rim", rim_side="back")
        result = draft_payload({"design": design, "feature": draft})
        self.assertTrue(result["geometry"])
        self.assertEqual(result["feature"]["options"]["level"], "rim")
        self.assertNotIn("auto", result["feature"]["options"])







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

            # Fix 058: Bambu Studio never gets a manufactured project - it
            # opens the staged, profile-free model files directly.
            staged = [Path(temp_dir) / "0001 - test.3mf", Path(temp_dir) / "0002 - test.3mf"]
            with (
                patch("subprocess.Popen") as mock_popen,
                patch.object(wavefinity_web, "stage_bambu_inputs", return_value=staged) as stage,
            ):
                result = wavefinity_web.launch_slicer(fake_exe, [fake_3mf, fake_3mf])
                stage.assert_called_once_with([fake_3mf, fake_3mf])
                mock_popen.assert_called_once()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args, [str(fake_exe.resolve()), str(staged[0]), str(staged[1])])
                for flag in ("--export-3mf", "--arrange", "--slice", "--load-settings", "--load-filaments"):
                    self.assertNotIn(flag, args)
                self.assertIsNone(result)

            # Other slicers keep the direct multi-file launch.
            orca = Path(temp_dir) / "orca-slicer.exe"
            orca.touch()
            with (
                patch("subprocess.Popen") as mock_popen,
                patch.object(wavefinity_web, "stage_bambu_inputs") as stage,
            ):
                result = wavefinity_web.launch_slicer(orca, [fake_3mf])
                stage.assert_not_called()
                args = mock_popen.call_args[0][0]
                self.assertEqual(args, [str(orca.resolve()), str(fake_3mf.resolve())])
                self.assertIsNone(result)

    def _print_setup(self, temp_dir):
        fake_exe = Path(temp_dir) / "bambu-studio.exe"
        fake_exe.touch()
        box = Path(temp_dir) / "Box.3mf"
        box.touch()
        connector = Path(temp_dir) / "Connector.3mf"
        connector.touch()
        gen = {"result": {"box": {"output": str(box)}}, "output": str(temp_dir)}
        conn = {"result": {"output": str(connector)}, "output": str(temp_dir)}
        return fake_exe, box, connector, gen, conn

    def test_print_payload_logs_qty_one_only_after_launch_and_excludes_connectors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe, box, connector, gen, conn = self._print_setup(temp_dir)
            project = Path(temp_dir) / "Wavefinity Print.3mf"
            with (
                patch.object(wavefinity_web, "generate_payload", return_value=gen) as generate,
                patch.object(wavefinity_web, "connector_payload", return_value=conn) as connector_gen,
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                patch.object(wavefinity_web, "launch_slicer", return_value=project),
                patch.object(wavefinity_web, "inventory_enabled", return_value=True),
                patch.object(wavefinity_web, "append_bin") as append,
            ):
                # No target means bin only: connectors are never generated.
                response = wavefinity_web.print_payload({"design": default_design(), "output": temp_dir})
            self.assertTrue(generate.call_args.kwargs["suppress_local_inventory"])
            connector_gen.assert_not_called()
            append.assert_called_once()
            self.assertEqual(append.call_args.kwargs["qty"], 1)
            self.assertEqual(append.call_args.kwargs["file"], "Box.3mf")
            self.assertEqual(response["project"], str(project))
            self.assertEqual(len(response["files"]), 1)

    def test_print_payload_launch_failure_reports_truthful_partial_save(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe, box, connector, gen, conn = self._print_setup(temp_dir)
            with (
                patch.object(wavefinity_web, "generate_payload", return_value=gen),
                patch.object(wavefinity_web, "connector_payload", return_value=conn) as connector_gen,
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                patch.object(wavefinity_web, "launch_slicer", side_effect=RuntimeError("no")),
                patch.object(wavefinity_web, "inventory_enabled", return_value=True),
                patch.object(wavefinity_web, "append_bin") as append,
            ):
                # The bin file already saved is a real side effect: a later
                # slicer failure must be reported as truthful partial success,
                # never as an ordinary exception that erases it.
                response = wavefinity_web.print_payload({"design": default_design(), "output": temp_dir})
            connector_gen.assert_not_called()
            self.assertTrue(response["partial"])
            self.assertEqual(response["partial_stage"], "slicer")
            self.assertEqual(response["design_files"], [str(box.resolve())])
            self.assertNotIn("slicer", response)
            append.assert_not_called()

    def test_connector_save_route_reports_completed_connectors_on_partial_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            side = Path(temp_dir) / "Side.3mf"
            side.touch()
            with (
                patch.object(wavefinity_web, "_generate_side_connector",
                             return_value=({"output": str(side)}, {"wall_mm": 1.2})),
                patch.object(wavefinity_web, "_generate_corner_connector",
                             side_effect=RuntimeError("corner boom")),
            ):
                response = wavefinity_web.connector_save_payload(
                    {"design": default_design(), "output": temp_dir})
            self.assertIs(wavefinity_web.POST_ROUTES["/api/connector"],
                          wavefinity_web.connector_save_payload)
            self.assertTrue(response["partial"])
            self.assertEqual(response["partial_stage"], "connectors")
            self.assertIn("corner boom", response["error"])
            self.assertEqual(response["result"], {"side": {"output": str(side)}})
            self.assertEqual(
                [f.name for f in wavefinity_web._extract_generated_files(response["result"])],
                ["Side.3mf"])
            self.assertTrue(side.is_file())






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
                    "target": "all",
                })
                self.assertEqual(response["output"], str(temp_dir))
                self.assertEqual(response["files"], [
                    str(fake_3mf.resolve()),
                    str(fake_connector.resolve()),
                ])
                self.assertEqual(response["slicer"], str(fake_exe.resolve()))
                mock_launch.assert_called_once_with(fake_exe, [
                    fake_3mf.resolve(),
                    fake_connector.resolve(),
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


    def test_typed_space_print_handoff_does_not_append_another_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            slicer = Path(temp_dir) / "bambu-studio.exe"
            slicer.touch()
            bin_file = Path(temp_dir) / "A.3mf"
            bin_file.touch()
            fake = {"result": {"box": {"output": str(bin_file)}}, "output": temp_dir}
            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake),
                patch.object(wavefinity_web, "connector_payload", return_value={"result": {}, "output": temp_dir}),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=slicer),
                patch.object(wavefinity_web, "launch_slicer"),
                patch.object(wavefinity_web, "append_bin") as append,
                patch.object(wavefinity_web, "inventory_enabled", return_value=True),
            ):
                result = wavefinity_web.print_payload({
                    "design": default_design(), "output": temp_dir, "design_row_id": "B1",
                })
                append.assert_not_called()
                self.assertEqual(result["design_files"], [str(bin_file)])


    def _node_or_skip(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for this browser-state regression")
        return node


    def test_typed_space_autosave_serializes_and_rejects_stale_completion(self):
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        owner = source[source.index("function typedSpaceOrdinaryBin() {"):
                       source.index("// Install a canonical design", source.index("function typedSpaceOrdinaryBin() {"))]
        script = "\n".join([
            "const clone = v => JSON.parse(JSON.stringify(v));",
            "const state = {folderMode:'space', design:{part_name:'',box:{b4b:{enabled:false}},v:0},",
            "  cleanDesign:{part_name:'',box:{b4b:{enabled:false}},v:0}, designInventoryId:null,",
            "  preview:{fits:true,feature_errors:[],draft_error:null}};",
            "state.previewDesignKey=JSON.stringify(state.design);",
            "const baseTrimEnabled = () => false;",
            "const writes = []; let epoch = 1; let release; const gate = new Promise(r => release = r);",
            "const DL = {loaded:true,spaceContext:() => ({epoch}), requireSpaceContext:c => {if(c.epoch!==epoch) throw Object.assign(new Error('stale'),{code:'STALE_SPACE_CONTEXT'});},",
            "  isStaleSpaceError:e => e.code==='STALE_SPACE_CONTEXT',",
            "  inventoryCall:async (_path,payload,options) => {writes.push({id:payload.row_id||null,v:payload.design.v}); if(payload.design.v===1) await gate; DL.requireSpaceContext(options.context); return {row_id:payload.row_id||'B1',design:clone(payload.design)};},",
            "  adopt:()=>{},emit:()=>{}};",
            "const toast = () => {}; const syncForm = () => {};",
            "const flushVisibleDesignEditsBeforeModeSwitch = async () => true;",
            "const refreshPreview = async () => {state.preview={fits:true,feature_errors:[],draft_error:null};};",
            owner,
            "(async () => {",
            "  await persistSpaceDesignSource(); const untouched = writes.length;",
            "  state.design.v=1; state.previewDesignKey=JSON.stringify(state.design);",
            "  const first=persistSpaceDesignSource();",
            "  await Promise.resolve(); state.design.v=2; state.previewDesignKey=JSON.stringify(state.design);",
            "  const second=persistSpaceDesignSource();",
            "  release(); await Promise.all([first,second]);",
            "  const serial = clone(writes); const id=state.designInventoryId;",
            "  state.design.v=3; state.previewDesignKey=JSON.stringify(state.design);",
            "  const stale=persistSpaceDesignSource(); await Promise.resolve(); epoch=2;",
            "  let rejected=false; try {await stale;} catch(e) {rejected=e.code==='STALE_SPACE_CONTEXT';}",
            "  process.stdout.write(JSON.stringify({untouched,serial,id,clean:state.cleanDesign.v,rejected}));",
            "})();",
        ])
        result = self._run_node(script)
        self.assertEqual(result["untouched"], 0)
        self.assertEqual(result["serial"], [{"id": None, "v": 1}, {"id": "B1", "v": 2}])
        self.assertEqual(result["id"], "B1")
        self.assertEqual(result["clean"], 2)
        self.assertTrue(result["rejected"])

    def test_hosted_inventory_writes_share_one_file_queue(self):
        source = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        owner = source[source.index("SP._inventoryWriteChain = Promise.resolve();"):
                       source.index("// Fix 034 F1", source.index("SP._inventoryWriteChain = Promise.resolve();"))]
        script = "\n".join([
            "const files = {name:'S', text:''};",
            "const state = {browserFolder:{name:'S',handle:files},activeSpace:{name:'S'}};",
            "const SP = {readInventoryFor:async folder => folder.handle.text};",
            "const INVENTORY_FILENAME = 'Wavefinity bins.md';",
            "const WFFileSystem = {writeText:async (handle,_name,text) => {handle.text=text;}};",
            "let release; const gate = new Promise(resolve => release=resolve); let calls=0;",
            "const api = async (_path,payload) => {calls++; if(calls===1) await gate;",
            "  return {inventory_text:payload.inventory_text+payload.mark};};",
            owner,
            "(async () => {const a=SP.inventoryRequest('/save',{mark:'A'});",
            " const b=SP.inventoryRequest('/save',{mark:'B'});",
            " await Promise.resolve(); release(); await Promise.all([a,b]);",
            " process.stdout.write(JSON.stringify({text:files.text,calls}));})();",
        ])
        self.assertEqual(self._run_node(script), {"text": "AB", "calls": 2})

    def test_resume_binds_existing_inventory_row_identity(self):
        source = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        start = source.index("SP.initializeDesignForActiveSpace = async () => {")
        owner = source[start:source.index("\n};", start) + 3]
        script = "\n".join([
            "const clone = v => JSON.parse(JSON.stringify(v));",
            "const state = {folderMode:'space',activeSpace:{kind:'drawer'},catalog:{},",
            "  spaceResumeDesign:{box:{x:16,b4b:{enabled:false}},part_name:'A'},spaceResumePending:false};",
            "const DL = {layout:{design_specs:{B2:clone(state.spaceResumeDesign)}},",
            "  ensureLoaded:async()=>{}};",
            "const SP = {resetDesignSession:()=>{state.designInventoryId=null;},",
            "  installSpaceStarterDesign:async()=>{throw Error('starter used');}};",
            "const api = async (_path,payload) => ({design:clone(payload.design)});",
            "const baseTrimEnabled = () => false; const syncForm = () => {};",
            "const bindLidMemoryForDesign = () => {};",
            "const refreshPreview = async () => {}; const toast = () => {};",
            owner,
            "(async()=>{await SP.initializeDesignForActiveSpace();",
            "process.stdout.write(JSON.stringify(state.designInventoryId));})();",
        ])
        self.assertEqual(self._run_node(script), "B2")

    def test_typed_space_replacement_and_output_boundaries_flush_autosave(self):
        root = Path(__file__).resolve().parent / "web"
        app = (root / "app.js").read_text(encoding="utf-8")
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        spaces = (root / "spaces.js").read_text(encoding="utf-8")
        for function in ("designerInstallInventorySpec", "designerNewBin", "designerDuplicate",
                         "generateParts", "printModel"):
            start = app.index(f"async function {function}(")
            end = app.find("\nasync function ", start + 1)
            body = app[start:end if end >= 0 else None]
            self.assertIn("flushSpaceDesignAutosave(", body, function)
        self.assertIn("flushSpaceDesignAutosave(", panel[panel.index("DP.selectMode = "):])
        self.assertIn("flushSpaceDesignAutosave(", spaces[spaces.index("SP.leaveDrawerLayoutSafely = "):])
        self.assertIn('action: "saved"', app[app.index("async function generateParts("):])
        self.assertIn('action: "printed"', app[app.index("async function printModel("):])

    def _app_js_functions(self, *names):
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        chunks = []
        for name in names:
            start = source.index(f"function {name}(")
            end = source.index("\n}\n", start) + 3
            chunks.append(source[start:end])
        return "\n".join(chunks)

    def _run_node(self, script):
        node = self._node_or_skip()
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        return json.loads(done.stdout)





    def test_first_bin_starter_waits_for_a_meaningful_edit(self):
        root = Path(__file__).resolve().parent / "web"
        app = (root / "app.js").read_text(encoding="utf-8")
        fresh = app[app.index("async function loadFreshOrdinaryDesignForCurrentFolder"):]
        fresh = fresh[:fresh.index("\n}\n")]
        self.assertIn('state.designInventoryId = null', fresh)
        # Showing a fresh starter does not create an Inventory row.
        self.assertIn("Showing a fresh starter does not create an Inventory row", fresh)
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        first = panel[panel.index("DP.designFirstBin = "):]
        self.assertIn("DP.newBinFromSpace()", first[:first.index("};")])
        self.assertNotIn("markWorking", first[:first.index("};")])
        transition = panel[panel.index("DP.newBinFromSpace = "):]
        transition = transition[:transition.index("};")]
        self.assertIn('DP.setMode("design")', transition)
        # The Surface first-run edge handoff is gone: Base Trim is a Space Action.
        self.assertNotIn("surfaceEdgeSucceeded", app)
        self.assertNotIn("DP.startBinNow", panel)
        # Inventory rows are only ever the real rows - never a pseudo row.
        model = (root / "drawer-model.js").read_text(encoding="utf-8")
        self.assertNotIn("DL.bins.push", model)
        self.assertNotIn("__current__", model + panel)

    def test_current_design_position_does_not_leak_between_spaces(self):
        # The session-only Current-design position is gone with the shadow
        # owner; nothing about an unplaced bin is kept as coordinates.
        model = (Path(__file__).resolve().parent / "web" / "drawer-model.js").read_text(encoding="utf-8")
        for name in ("workingFit", "moveWorkingTo", "workingContext", "fitStamp"):
            self.assertNotIn(name, model)





    def test_inventory_preview_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            wavefinity_web.inventory_preview_payload({"design": default_design(), "output": directory})
            self.assertEqual(os.listdir(directory), [])

    def test_inventory_preview_is_read_only_planning_envelope(self):
        ordinary = default_design()
        ordinary["part_name"] = "Screws"
        record = wavefinity_web.inventory_preview_payload({"design": ordinary})["bin"]
        self.assertEqual(record["kind"], "bin")
        self.assertEqual(record["file"], "")
        self.assertEqual(
            (record["x"], record["y"], record["z"]),
            (ordinary["box"]["x"], ordinary["box"]["y"], ordinary["box"]["z"]),
        )
        storage = default_design()
        storage["box"].update(x=64.0, y=48.0, z=40.0, wall=1.2, standard_walls=False)
        storage["box"]["b4b"] = {"enabled": True}
        self.assertEqual(
            wavefinity_web.inventory_preview_payload({"design": storage})["bin"]["kind"], "b4b",
        )
        with self.assertRaises(ValueError):
            wavefinity_web.inventory_preview_payload({"design": {"design_kind": "base_trim"}})











    # ------------------------------------------------------------ Fix 019



    def test_safe_drawer_switch_never_silently_saves_or_loses_work(self):
        # Fix 034 K1: autosave has no off state any more, so this always just
        # flushes a dirty layout and aborts the switch (keeping DL.layout/
        # DL.dirty intact) on a failed flush - never a confirm() dialog.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        leave = spaces_js[spaces_js.index("SP.leaveDrawerLayoutSafely = async () => {"):]
        leave = leave[:leave.index("SP.resetDrawer = async")]
        self.assertNotIn("window.confirm(", leave)
        self.assertNotIn(" confirm(", leave)
        self.assertNotIn("appConfirmSaveDiscardCancel", leave)

        script = "\n".join([
            "const SP = {};",
            "let saveResult = true;",
            "const toast = () => {};",
            "const DL = { dirty: true, layout: { settings: { autosave: true } }, output: 'x',"
            " saveError: 'boom', save: async () => saveResult };",
            leave,
            "(async () => {",
            "  const out = {};",
            "  out.flushSuccess = await SP.leaveDrawerLayoutSafely();",
            "  DL.dirty = true;",
            "  saveResult = false;",
            "  out.flushFailure = await SP.leaveDrawerLayoutSafely();",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        out = json.loads(done.stdout)
        self.assertTrue(out["flushSuccess"])
        self.assertFalse(out["flushFailure"])

    def test_drawer_save_reports_success_or_failure(self):
        # Item 2's implementation detail: DL.save() must let callers know
        # whether persistence actually succeeded.
        node = self._node_or_skip()
        model = Path(__file__).resolve().parent / "web" / "drawer-model.js"
        script = """
const vm = require("vm"), fs = require("fs");
let shouldFail = false;
const ctx = {
  debounce: f => f, console, Math, JSON, Number, Set, Map, setTimeout, clearTimeout,
  state: { runtime: { hosted: false }, output: "out" },
  toast: () => {},
  api: async () => { if (shouldFail) throw new Error("boom"); return {}; },
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + " ;this.DL = DL;", ctx);
const DL = ctx.DL;
DL.emit = () => {};
DL.output = "out";
DL.layout = { settings: {} };
DL.dirty = true;
(async () => {
  const out = {};
  out.successReturn = await DL.save();
  out.dirtyAfterSuccess = DL.dirty;
  DL.dirty = true;
  shouldFail = true;
  out.failureReturn = await DL.save();
  out.dirtyAfterFailure = DL.dirty;
  console.log(JSON.stringify(out));
})();
"""
        result = subprocess.run([node, "-e", script, str(model)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertTrue(out["successReturn"])
        self.assertFalse(out["dirtyAfterSuccess"])
        self.assertFalse(out["failureReturn"])
        self.assertTrue(out["dirtyAfterFailure"])  # a failed save never clears dirty

    def test_drawer_save_serializes_concurrent_callers(self):
        # Fix 019 correction C1.1: a caller that arrives while a save is
        # already in flight must never get an optimistic `true` back - it
        # has to await the SAME real, serialized result. Case 1: the
        # in-flight request fails - both the original caller and the
        # second, concurrent caller resolve false, and dirty stays true, and
        # no un-awaited/extra request is fired after the failure. Case 2: the
        # in-flight request succeeds but a second save was queued while it
        # ran - exactly one more serialized request goes out, and the
        # original (and every other) caller only resolves once that queued
        # request itself is finished.
        node = self._node_or_skip()
        model = Path(__file__).resolve().parent / "web" / "drawer-model.js"
        script = """
const vm = require("vm"), fs = require("fs");
function makeCtx() {
  const calls = [];
  const pending = [];
  const ctx = {
    debounce: f => f, console, Math, JSON, Number, Set, Map, Promise, setTimeout, clearTimeout, setImmediate,
    state: { runtime: { hosted: false }, output: "out" },
    toast: () => {},
    api: async () => {
      calls.push(1);
      return new Promise((resolve, reject) => { pending.push({ resolve, reject }); });
    },
  };
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + " ;this.DL = DL;", ctx);
  const DL = ctx.DL;
  DL.emit = () => {};
  DL.output = "out";
  DL.layout = { settings: {} };
  DL.dirty = true;
  return { DL, calls, pending };
}
const tick = () => new Promise(r => setImmediate(r));

(async () => {
  const out = {};

  // Case 1: concurrent caller during an in-flight save that then fails.
  {
    const { DL, calls, pending } = makeCtx();
    const p1 = DL.save();
    await tick();
    out.savingDuringFirst = DL.saving;
    const p2 = DL.save(); // arrives while DL.saving === true
    out.sameChainPromise = p1 === p2; // never a separate, optimistic promise
    out.callsBeforeSettle = calls.length;
    pending[0].reject(new Error("boom"));
    const [r1, r2] = await Promise.all([p1, p2]);
    out.failCase = {
      r1, r2, calls: calls.length, dirty: DL.dirty, saving: DL.saving,
    };
  }

  // Case 2: the in-flight save succeeds, but a second save was queued
  // while it ran - the queued save must actually run, serialized, and the
  // original caller (e.g. a safe-switch check) must not resolve until it
  // does.
  {
    const { DL, calls, pending } = makeCtx();
    const p1 = DL.save();
    await tick();
    const p2 = DL.save(); // queued: asks for one more save of the newest layout
    out.queuedCallsBeforeFirstSettles = calls.length; // still just 1 request so far
    pending[0].resolve({});
    await tick();
    await tick();
    out.queueCase = { callsAfterFirstResolves: calls.length }; // the queued 2nd request must now be in flight
    out.stillSavingBetween = DL.saving; // chain not over yet - 2nd request pending
    pending[1].resolve({});
    const [r1, r2] = await Promise.all([p1, p2]);
    out.queueCase.r1 = r1;
    out.queueCase.r2 = r2;
    out.queueCase.callsTotal = calls.length;
    out.queueCase.savingAfter = DL.saving;
  }

  process.stdout.write(JSON.stringify(out));
})();
"""
        result = subprocess.run([node, "-e", script, str(model)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)

        self.assertTrue(out["savingDuringFirst"])
        self.assertTrue(out["sameChainPromise"])
        self.assertEqual(out["callsBeforeSettle"], 1)
        fail_case = out["failCase"]
        self.assertFalse(fail_case["r1"])
        self.assertFalse(fail_case["r2"])
        self.assertEqual(fail_case["calls"], 1)  # a failed save must not silently retry
        self.assertTrue(fail_case["dirty"])       # dirty must remain true
        self.assertFalse(fail_case["saving"])     # the chain is over, not stuck "in flight"

        self.assertEqual(out["queuedCallsBeforeFirstSettles"], 1)
        queue_case = out["queueCase"]
        self.assertEqual(queue_case["callsAfterFirstResolves"], 2)
        self.assertTrue(out["stillSavingBetween"])
        self.assertTrue(queue_case["r1"])
        self.assertTrue(queue_case["r2"])
        self.assertEqual(queue_case["callsTotal"], 2)
        self.assertFalse(queue_case["savingAfter"])

    def _spaces_slice(self, spaces_js, start_marker, end_marker="\n};\n"):
        chunk = spaces_js[spaces_js.index(start_marker):]
        return chunk[:chunk.index(end_marker)] + "\n};\n"

    def test_classify_metadata_parses_and_validates_v8_resume_fields(self):
        # Fix 032: the exact resume checkpoint only exists from v8 on, and its
        # top-level shape (object-or-null design, boolean pending) is
        # validated the same way as keep_bin_defaults/bin_defaults already are.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")

        valid_space = self._spaces_slice(spaces_js, "SP.validSpace = raw => {")
        valid_uuid = self._spaces_slice(spaces_js, "SP.validUuid = raw => {")
        classify = self._spaces_slice(spaces_js, "SP.classifyMetadata = record => {")

        script = "\n".join([
            "const SP = {};",
            "const FOLDER_METADATA_VERSION = 8;",
            "const SPACE_ID_REQUIRED_VERSION = 5;",
            "const SPACE_SETUP_VERSION = 1;",
            "const RESUME_REQUIRED_VERSION = 8;",
            "const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;",
            valid_space,
            valid_uuid,
            classify,
            "const base = {",
            "  version: 8, setup_version: 1, folder_mode: 'space',",
            "  space: { kind: 'drawer', name: 'S', x: 320, y: 240, z: 55 },",
            "  space_id: '11111111-1111-1111-1111-111111111111',",
            "  keep_bin_defaults: true, bin_defaults: null, part_defaults: {},",
            "};",
            "const out = {};",
            "out.noResume = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: null, resume_pending: false } });",
            "out.withResume = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: { box: { x: 1 } }, resume_pending: true } });",
            "out.nullDesignForcesPendingFalse = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: null, resume_pending: true } });",
            "out.malformedDesign = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: ['nope'], resume_pending: false } });",
            "out.malformedPending = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: { box: {} }, resume_pending: 'yes' } });",
            "out.missingPending = SP.classifyMetadata({ exists: true, data: { ...base, resume_design: { box: {} } } });",
            "out.v7HasNoResumeConcept = SP.classifyMetadata({ exists: true, data: { ...base, version: 7 } });",
            "process.stdout.write(JSON.stringify(out));",
        ])
        out = self._run_node(script)
        self.assertIsNone(out["noResume"]["resume_design"])
        self.assertFalse(out["noResume"]["resume_pending"])
        self.assertEqual(out["withResume"]["resume_design"], {"box": {"x": 1}})
        self.assertTrue(out["withResume"]["resume_pending"])
        self.assertIsNone(out["nullDesignForcesPendingFalse"]["resume_design"])
        self.assertFalse(out["nullDesignForcesPendingFalse"]["resume_pending"])
        self.assertEqual(out["malformedDesign"]["status"], "invalid")
        self.assertEqual(out["malformedPending"]["status"], "invalid")
        self.assertEqual(out["missingPending"]["status"], "invalid")
        self.assertEqual(out["v7HasNoResumeConcept"]["status"], "space")
        self.assertIsNone(out["v7HasNoResumeConcept"]["resume_design"])
        self.assertFalse(out["v7HasNoResumeConcept"]["resume_pending"])

    def test_resume_checkpoint_queue_coalesces_serializes_and_gates_by_space_identity(self):
        # Fix 032: the resume-checkpoint queue is a single coalescing slot
        # (not a per-Space queue) - newest state for the active Space wins
        # while a write is in flight, a rejected write must not stop later
        # writes, and a completion for a Space that is no longer active must
        # never overwrite a different Space's in-memory checkpoint.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")

        start = "SP._resume = {"
        end = "SP.flushOutgoingResumeCheckpoint = () => SP._pumpResumeQueue();"
        resume_module = spaces_js[spaces_js.index(start):]
        resume_module = resume_module[:resume_module.index(end) + len(end)]

        script = "\n".join([
            "const clone = v => JSON.parse(JSON.stringify(v));",
            "const toasts = [];",
            "const toast = msg => toasts.push(msg);",
            "const writes = [];",
            "let apiBehavior = async () => ({});",
            "const api = async (path, payload) => {",
            "  writes.push({ path, payload: clone(payload) });",
            "  return apiBehavior();",
            "};",
            "const state = {",
            "  folderMode: 'space', activeSpace: { kind: 'drawer', name: 'A' }, activeSpaceId: 'sidA',",
            "  output: '/A', browserFolder: null, runtime: { hosted: false },",
            "  spaceResumeDesign: null, spaceResumePending: false,",
            "};",
            "const SP = { writeMetadata: async () => ({}) };",
            resume_module,
            "(async () => {",
            "  const out = {};",
            "",
            "  // 1) Coalescing: a second queue call while the first write is still",
            "  //    in flight must not start a second concurrent write - it replaces",
            "  //    the pending value, and the pump picks it up once the first",
            "  //    write settles.",
            "  apiBehavior = async () => { await new Promise(r => setTimeout(r, 15)); return {}; };",
            "  SP.queueResumeCheckpoint({ v: 1 }, false);",
            "  SP.queueResumeCheckpoint({ v: 2 }, true);",
            "  await new Promise(r => setTimeout(r, 80));",
            "  out.coalescedWriteCount = writes.length;",
            "  out.coalescedFinalDesign = state.spaceResumeDesign;",
            "  out.coalescedFinalPending = state.spaceResumePending;",
            "",
            "  // Re-queuing the exact same value that was actually saved must be a",
            "  // no-op - no extra write.",
            "  SP.queueResumeCheckpoint({ v: 2 }, true);",
            "  await new Promise(r => setTimeout(r, 30));",
            "  out.duplicateSkipped = writes.length === out.coalescedWriteCount;",
            "",
            "  // 2) A write for Space A that finishes AFTER the UI switched to",
            "  //    Space B must not overwrite Space B's in-memory checkpoint.",
            "  writes.length = 0;",
            "  apiBehavior = async () => { await new Promise(r => setTimeout(r, 30)); return {}; };",
            "  SP.flushResumeCheckpoint({ v: 'A-late' }, true); // fire and forget on purpose",
            "  state.activeSpaceId = 'sidB';",
            "  state.activeSpace = { kind: 'drawer', name: 'B' };",
            "  state.output = '/B';",
            "  state.spaceResumeDesign = { v: 'B-current' };",
            "  state.spaceResumePending = false;",
            "  await new Promise(r => setTimeout(r, 60));",
            "  out.staleCompletionDesign = state.spaceResumeDesign;",
            "",
            "  // 3) An explicit flush must observably reject on a failed write (so",
            "  //    Generate/Print can tell), but that rejection must not poison the",
            "  //    queue - a later write for the same Space must still go through.",
            "  let calls = 0;",
            "  apiBehavior = async () => { calls += 1; if (calls === 1) throw new Error('disk full'); return {}; };",
            "  let firstFlushRejected = false;",
            "  try { await SP.flushResumeCheckpoint({ v: 'first-fails' }, false); }",
            "  catch (error) { firstFlushRejected = error.message === 'disk full'; }",
            "  out.firstFlushRejected = firstFlushRejected;",
            "  out.toastsAfterFailure = toasts.length;",
            "  await SP.flushResumeCheckpoint({ v: 'second-succeeds' }, true);",
            "  out.recoveredDesign = state.spaceResumeDesign;",
            "  out.recoveredPending = state.spaceResumePending;",
            "",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        self.assertEqual(out["coalescedWriteCount"], 2)
        self.assertEqual(out["coalescedFinalDesign"], {"v": 2})
        self.assertTrue(out["coalescedFinalPending"])
        self.assertTrue(out["duplicateSkipped"])

        # Space A's stale, late-arriving completion did not clobber Space B.
        self.assertEqual(out["staleCompletionDesign"], {"v": "B-current"})

        # The failed flush was observable to its own caller (Correction 1)...
        self.assertTrue(out["firstFlushRejected"])
        # ...leaves the user-facing message to the explicit caller...
        self.assertEqual(out["toastsAfterFailure"], 0)
        # ...and did not stop the next write.
        self.assertEqual(out["recoveredDesign"], {"v": "second-succeeds"})
        self.assertTrue(out["recoveredPending"])



    def test_apply_folder_flushes_outgoing_checkpoint_before_changing_identity(self):
        # Fix 032 item 5 / Correction 1, item 4: SP.applyFolder() must flush
        # whatever is queued/in-flight for the OUTGOING Space before it
        # mutates state.output/state.activeSpaceId - not after.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        apply_folder = self._spaces_slice(spaces_js, "SP.applyFolder = async (info,")

        script = "\n".join([
            "const calls = [];",
            "const state = { output: 'OLD_OUTPUT', activeSpaceId: 'OLD_ID', folderSelected: false, previewRequest: 0 };",
            "const cancelPreviewWait = () => calls.push(['cancelPreviewWait', state.output, state.activeSpaceId]);",
            "const SP = {",
            "  resetDrawer: async () => { calls.push(['resetDrawer']); return true; },",
            "  flushOutgoingResumeCheckpoint: async () => {",
            "    calls.push(['flush', state.output, state.activeSpaceId]);",
            "  },",
            "  initializeDesignForActiveSpace: async () => { calls.push(['initializeDesignForActiveSpace']); },",
            "};",
            "const setFolderState = (...args) => calls.push(['setFolderState', state.output, state.activeSpaceId]);",
            "const syncForm = () => calls.push(['syncForm']);",
            apply_folder,
            "(async () => {",
            "  const info = {",
            "    folder: 'NEW_FOLDER', space_id: 'NEW_ID', folder_mode: 'space',",
            "    space: { kind: 'drawer', name: 'N' }, inventory: true,",
            "    keep_bin_defaults: true, bin_defaults: null, part_defaults: {},",
            "    resume_design: null, resume_pending: false,",
            "  };",
            "  await SP.applyFolder(info, { reset: false });",
            "  process.stdout.write(JSON.stringify({ calls, finalOutput: state.output, finalId: state.activeSpaceId }));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        flush_call = next(c for c in out["calls"] if c[0] == "flush")
        cancel_call = next(c for c in out["calls"] if c[0] == "cancelPreviewWait")
        self.assertEqual(cancel_call[1:], ["OLD_OUTPUT", "OLD_ID"])
        self.assertLess(out["calls"].index(cancel_call), out["calls"].index(flush_call))
        # The flush saw the OLD identity - it ran before the mutation below.
        self.assertEqual(flush_call[1:], ["OLD_OUTPUT", "OLD_ID"])
        set_folder_state_call = next(c for c in out["calls"] if c[0] == "setFolderState")
        # By the time setFolderState() runs, identity has already moved on.
        self.assertEqual(set_folder_state_call[1:], ["NEW_FOLDER", "NEW_ID"])
        self.assertEqual(out["finalOutput"], "NEW_FOLDER")
        self.assertEqual(out["finalId"], "NEW_ID")
        self.assertLess(out["calls"].index(flush_call), out["calls"].index(set_folder_state_call))


    def test_refresh_preview_only_queues_checkpoint_on_a_fully_valid_preview(self):
        # Fix 032 Correction 1, item 4: an HTTP-200 preview that still
        # reports fit/feature/draft errors must not replace the last valid
        # resume checkpoint.
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        # refreshPreview() adopts its result through adoptPreviewResult() (shared
        # with AI Help's already-proven candidate), which owns the checkpoint rule.
        start = app_js.index("async function refreshPreview(")
        self.assertIn("adoptPreviewResult(result,", app_js[start:app_js.index("\nasync function ", start + 1)])
        start = app_js.index("function adoptPreviewResult(")
        source = app_js[start:app_js.index("\n}\n", start)]

        previews_has_errors_idx = source.index("const previewHasErrors =")
        queue_idx = source.index("SP.queueResumeCheckpoint(")
        self.assertLess(previews_has_errors_idx, queue_idx)
        guard = source[previews_has_errors_idx:queue_idx]
        self.assertIn("if (!previewHasErrors", guard)
        self.assertIn('state.folderMode === "space"', guard)





















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

    def test_about_brochure_is_served_from_repo_root(self):
        brochure = Path(wavefinity_web.APP_DIR) / "Brochure.md"
        self.assertTrue(brochure.is_file())
        self.assertTrue(brochure.read_text(encoding="utf-8").startswith("# Introducing Wavefinity"))
        status, headers, body = self.get("/Brochure.md")
        self.assertEqual(status, 200)
        self.assertIn("text/markdown", headers["Content-Type"])
        self.assertTrue(body.decode("utf-8").startswith("# Introducing Wavefinity"))

    def post(self, path, payload):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())



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








class Fix20SpaceFormTests(unittest.TestCase):
    """Tests for Item 2, 3, 4: Space form, dimensions, and local folder auto-creation."""






class Fix20InsideGripTests(unittest.TestCase):
    """Tests for Item 5: Inside Grip terminology and visibility."""





class Fix20StorageBoxDividerTests(unittest.TestCase):
    """Tests for Item 6: Storage Box Divider support across web API and frontend rules."""

    def _b4b_design(self, x=64, y=48, z=40, features=()):
        design = default_design()
        design["box"]["x"] = x
        design["box"]["y"] = y
        design["box"]["z"] = z
        design["box"]["b4b"] = {"enabled": True, "lid": False}
        design["layout"]["mode"] = "fused"
        design["layout"]["features"] = list(features)
        return design






class Fix20StorageBoxMaterialsTests(unittest.TestCase):
    """Tests for Item 7: Storage Box material presets, defaults, and lid thickness."""











class AiHelpBackendTests(unittest.TestCase):
    """Fix 073: prompt/manifest, candidate proof and repair prompt (no AI provider)."""

    def _space(self):
        return {"kind": "pegboard", "x": 96.0, "y": 96.0, "z": 80.0, "pegboard_standard": "standard"}

    def test_manifest_covers_every_user_facing_capability_and_round_trips(self):
        manifest = wavefinity_web.ai_capability_manifest()
        catalog = catalog_payload()
        listed = {one["kind"]: one for one in manifest["features"]}
        visible = {p["kind"] for p in catalog["parts"]
                   if p["palette_visible"] and "box_modifier" not in p["capabilities"]}
        self.assertEqual(set(listed), visible)
        self.assertNotIn("pocket", listed)  # hidden/legacy kinds are never offered
        for kind, one in listed.items():
            expected = "recommend_only" if "photo" in one["capabilities"] else "configurable"
            self.assertEqual(one["ai"], expected, kind)
        self.assertEqual(listed["nest"]["ai"], "recommend_only")
        modifiers = {p["kind"] for p in catalog["parts"] if "box_modifier" in p["capabilities"]}
        self.assertEqual({one["kind"] for one in manifest["box_modifiers"]}, modifiers)
        # The rule tables are the catalog's own, not a second copy.
        by_kind = {one["kind"]: one for one in manifest["box_modifiers"]}
        self.assertEqual(by_kind["side_openings"]["rules"]["side_openings"], catalog["side_openings"])
        self.assertEqual(by_kind["lid_stacking"]["rules"]["lid_rules"], catalog["lid_rules"])
        # All three Lid & Stacking configurations have a canonical example.
        configs = by_kind["lid_stacking"]["example"]
        self.assertEqual(set(configs), {"stackable_bin", "stackable_lid", "lid_with_handle"})
        self.assertEqual(configs["stackable_bin"], {"stack": {"mode": "direct"}})
        self.assertTrue(configs["stackable_lid"]["lid"]["stackable"])
        self.assertFalse(configs["lid_with_handle"]["lid"]["stackable"])
        # Legal values, not just keys: every enum has its choices from the registry's
        # own constants, ranges are declared, and custom-UI (editor=false) options are included.
        from organizer_inserts import _bore, _text
        options = {one["kind"]: {o["key"]: o for o in one["options"]}
                   for one in manifest["features"] if one["ai"] == "configurable"}
        for kind, table in options.items():
            for key, option in table.items():
                self.assertTrue(option["legal_values"], (kind, key))
                if option["type"] == "enum":
                    self.assertTrue(option["choices"], (kind, key))
        self.assertEqual([c["value"] for c in options["bore"]["bore_style"]["choices"]], list(_bore.BORE_STYLES))
        self.assertEqual([c["value"] for c in options["bore"]["xy_size_mode"]["choices"]], list(_bore.XY_SIZE_MODES))
        self.assertEqual(options["bore"]["angle"]["maximum"], _bore.BORE_MAX_TILT)
        self.assertEqual([float(c["value"]) for c in options["text"]["depth"]["choices"]], list(_text.TEXT_DEPTH_CHOICES))
        self.assertEqual([c["value"] for c in options["text"]["level"]["choices"]], ["base", "rim"])
        self.assertIn("bore_style", {o["key"] for p in catalog["parts"] if p["kind"] == "bore" for o in p["options"] if "choices" in o})
        self.assertIn("height_size_mode", options["bore"])  # editor=False option still offered
        # Every example is legal in the canonical validator.
        for one in listed.values():
            if one["ai"] != "configurable":
                continue
            design = wavefinity_web._ai_example_base()
            design["layout"]["features"] = [one["example"]]
            wavefinity_web.validate_design_payload({"design": design})
        for one in manifest["box_modifiers"]:
            blocks = one["example"]
            for block in ([blocks] if "stackable_bin" not in blocks else blocks.values()):
                design = wavefinity_web._ai_example_base()
                design["box"].update(block)
                wavefinity_web.validate_design_payload({"design": design})

    def test_manifest_describes_every_shared_top_level_feature_field(self):
        from organizer_inserts import _bore
        from organizer_inserts._core import ITEM_PROFILES, Item
        manifest = wavefinity_web.ai_capability_manifest()
        catalog = catalog_payload()
        features = {one["kind"]: one for one in manifest["features"] if one["ai"] == "configurable"}
        for kind, one in features.items():
            self.assertIn("zone", one["generic_fields"], kind)
        # Public-control precedence matrix (Fix 073 Correction 3): a capability flag
        # says a feature HAS this kind of control, not that today's Designer UI
        # exposes it as this generic top-level field. Exact known exceptions:
        # Bore moved lean direction to options.angle_towards (top-level `along` is a
        # legacy fallback); Divider moved quantities entirely to options.count_x/
        # count_y (top-level `count`/`along` are legacy single-axis compatibility).
        self.assertNotIn("along", features["bore"]["generic_fields"])
        self.assertIn("angle_towards", {o["key"] for o in features["bore"]["options"]})
        self.assertNotIn("count", features["divider"]["generic_fields"])
        self.assertNotIn("along", features["divider"]["generic_fields"])
        self.assertEqual({o["key"] for o in features["divider"]["options"]} & {"count_x", "count_y"},
                         {"count_x", "count_y"})
        # Every other qty/along/item/alternate holder keeps its ordinary generic field.
        implied = {"qty": "count", "along": "along", "item": "item", "alternate": "alternate_ends"}
        for kind, one in features.items():
            if kind in ("bore", "divider"):
                continue
            fields = one["generic_fields"]
            for capability, field_name in implied.items():
                self.assertEqual(capability in one["capabilities"], field_name in fields, (kind, field_name))
        # full_span/wedge are current-UI-unreachable structure, never an AI choice.
        self.assertNotIn("full_span", features["divider"]["generic_fields"])
        self.assertNotIn("wedge", features["divider"]["generic_fields"])
        # Bore offers all six persisted profiles; Cradle never inherits Bore-only shapes.
        bore_item, cradle_item = features["bore"]["generic_fields"]["item"], features["cradle"]["generic_fields"]["item"]
        self.assertEqual([p["value"] for p in bore_item["profiles"]], [v for v, _ in ITEM_PROFILES])
        self.assertEqual(len(bore_item["profiles"]), 6)
        self.assertEqual([p["value"] for p in cradle_item["profiles"]], ["round"])
        self.assertNotIn("hex_bit", cradle_item)
        for value, _label in ITEM_PROFILES:  # the engine accepts exactly the advertised set
            Item.simple("x", 10.0, 5.0, profile=value)
        with self.assertRaises(ValueError):
            Item.simple("x", 10.0, 5.0, profile="triangle")
        # Fixed hex-bit dimensions come from the Bore constants, and the browser's own
        # literals (which cannot read them yet) must agree - this is the drift guard.
        self.assertEqual(bore_item["hex_bit"], _bore.HEX_BIT_FIXED)
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        labels = dict(ITEM_PROFILES)
        for profile, fixed in _bore.HEX_BIT_FIXED.items():
            match = re.search(
                rf'{profile}: \{{ label: "([^"]+)", length: ([\d.]+), diameter: ([\d.]+), clearance: ([\d.]+)', app_js)
            self.assertIsNotNone(match, profile)
            self.assertEqual(match.group(1), labels[profile])
            self.assertEqual([float(v) for v in match.groups()[1:]],
                             [fixed["length_mm"], fixed["diameter_mm"], fixed["clearance_mm"]])
        for value in ("round", "hex", "square", "square_axis"):
            self.assertIn(f'["{value}", "{labels[value]}"]', app_js)
        self.assertEqual(catalog["item_rules"]["hex_bit"], _bore.HEX_BIT_FIXED)
        # Count semantics: Auto where the editor has Auto, explicit for Steps.
        self.assertIn("Auto", features["post"]["generic_fields"]["count"]["null_means"])
        self.assertIn("not allowed", features["steps"]["generic_fields"]["count"]["null_means"])
        # Internal serialized helpers are never configurable.
        internal = {(p["kind"], o["key"]) for p in catalog["parts"] for o in p["options"] if o.get("internal")}
        self.assertEqual(internal, {("text", "retarget")})
        for kind, one in features.items():
            self.assertFalse({(kind, o["key"]) for o in one["options"]} & internal)
        # Legacy/derived serialized fields exist for round-tripping old designs but are
        # never advertised as an alternate AI control, on top of the public precedence above.
        legacy = {(p["kind"], o["key"]) for p in catalog["parts"] for o in p["options"] if o.get("legacy")}
        self.assertEqual(legacy, {
            ("post", "count_x"), ("post", "count_y"),
            ("cradle", "floor_gap"), ("cradle", "rib_thickness"),
            ("divider", "angle"), ("divider", "reverse_bottom"),
            ("text", "font"),
        })
        for kind, one in features.items():
            self.assertFalse({(kind, o["key"]) for o in one["options"]} & legacy, kind)

    def test_ai_public_contract_semantic_preflight_rejects_canonically_valid_defects(self):
        base = wavefinity_web._ai_example_base()
        base["box"].update({"x": 96.0, "y": 96.0, "z": 60.0})
        base["part_name"] = "Test Bin"  # Fix 078: part_name is itself now required

        def candidate(feature):
            design = json.loads(json.dumps(base))
            design["layout"]["features"] = [feature]
            return design

        rejections = {
            "cradle_bore_only_profile": candidate({
                "kind": "cradle", "zone": [-6, -6, 6, 6],
                "item": {"name": "x", "profile": "hex", "clearance": 0,
                         "segments": [{"length": 10, "diameter": 5}]},
            }),
            "cradle_nonzero_clearance": candidate({
                "kind": "cradle", "zone": [-6, -6, 6, 6],
                "item": {"name": "x", "profile": "round", "clearance": 0.4,
                         "segments": [{"length": 10, "diameter": 5}]},
            }),
            "bore_wrong_clearance": candidate({
                "kind": "bore", "zone": [-8, -8, 8, 8],
                "item": {"name": "x", "profile": "round", "clearance": 0.4,
                         "segments": [{"length": 10, "diameter": 5}]},
            }),
            "hex_bit_wrong_dimensions": candidate({
                "kind": "bore", "zone": [-8, -8, 8, 8],
                "item": {"name": "x", "profile": "hex_bit_short", "clearance": 0.25,
                         "segments": [{"length": 99, "diameter": 6.35}]},
            }),
            "hex_bit_nonzero_lean": candidate({
                "kind": "bore", "zone": [-8, -8, 8, 8],
                "item": {"name": "x", "profile": "hex_bit_short", "clearance": 0.25,
                         "segments": [{"length": 25.0, "diameter": 6.35}]},
                "options": {"angle": 10},
            }),
            "steps_options_count_conflict": candidate({
                "kind": "steps", "zone": [-8, -8, 8, 8], "count": 3, "options": {"count": 5},
            }),
            "post_legacy_grid_override": candidate({
                "kind": "post", "zone": [-8, -8, 8, 8], "count": 2, "along": "x",
                "options": {"count_x": 2, "count_y": 1},
            }),
            "divider_legacy_top_level_count": candidate({
                "kind": "divider", "zone": [-8, -8, 8, 8], "count": 2, "along": "x",
                "full_span": True, "wedge": True, "options": {},
            }),
        }
        for label, design in rejections.items():
            with self.assertRaises(ValueError, msg=label) as caught:
                wavefinity_web.ai_candidate_payload({"design": design})
            self.assertNotIn("Traceback", str(caught.exception), label)
        # The exact fixed hex-bit preset is accepted, upright, and preserved unmodified.
        good = candidate({
            "kind": "bore", "zone": [-8, -8, 8, 8],
            "item": {"name": "x", "profile": "hex_bit_short", "clearance": 0.25,
                     "segments": [{"length": 25.0, "diameter": 6.35}]},
            "options": {"angle": 0},
        })
        accepted = wavefinity_web.ai_candidate_payload({"design": good})
        self.assertEqual(accepted["problems"], [])

    def test_ai_candidate_requires_a_short_nonblank_part_name(self):
        # Fix 078: a missing/blank or over-80-character name is a repairable
        # answer defect, not silently accepted or silently renamed.
        base = wavefinity_web._ai_example_base()
        for bad_name in ("", "   ", "x" * 81):
            design = json.loads(json.dumps(base))
            design["part_name"] = bad_name
            with self.assertRaisesRegex(ValueError, "part_name", msg=repr(bad_name)):
                wavefinity_web.ai_candidate_payload({"design": design})
        good = json.loads(json.dumps(base))
        good["part_name"] = "Lipstick"
        self.assertEqual(wavefinity_web.ai_candidate_payload({"design": good})["problems"], [])

    def test_ai_candidate_rejects_more_than_one_rim_text(self):
        # Fix 078: at most one rim Text feature total, even on different sides.
        base = wavefinity_web._ai_example_base()
        base["part_name"] = "Test Bin"
        base["layout"]["features"] = [
            {"kind": "text", "zone": [-20, 6, 20, 15], "options": {"text": "A", "level": "rim", "rim_side": "back"}},
            {"kind": "text", "zone": [-20, -15, 20, -6], "options": {"text": "B", "level": "rim", "rim_side": "front"}},
        ]
        with self.assertRaisesRegex(ValueError, "one rim Text"):
            wavefinity_web.ai_candidate_payload({"design": base})

    def test_ai_candidate_enforces_the_capped_space_object_height_ceiling(self) -> None:
        # Fix 078: a Drawer/Storage Box Space is a hard ceiling for a Bore-held
        # object's top; Surface/Pegboard and no Space impose none.
        base = wavefinity_web._ai_example_base()
        base["box"].update({"x": 64.0, "y": 64.0, "z": 77.0})
        base["part_name"] = "Lipstick"
        base["layout"]["features"] = [{
            "kind": "bore", "zone": [-8, -8, 8, 8],
            "item": {"name": "lipstick", "profile": "round", "clearance": 0.25,
                     "segments": [{"length": 60.0, "diameter": 12.0}]},
            "options": {"bore_style": "base_straight", "height": 70.0, "depth": 20.0, "wall": 1.6},
        }]
        drawer_space = {"kind": "drawer", "x": 64.0, "y": 64.0, "z": 77.0}
        result = wavefinity_web.ai_candidate_payload({"design": base, "space": drawer_space})
        self.assertTrue(result["problems"])
        self.assertIn("77.0", " ".join(result["problems"]))
        # The identical design/object is legal without a capping Space.
        uncapped = wavefinity_web.ai_candidate_payload({"design": base, "space": {"kind": "surface", "x": 64.0, "y": 64.0, "z": 200.0}})
        self.assertEqual(uncapped["problems"], [])
        no_space = wavefinity_web.ai_candidate_payload({"design": base})
        self.assertEqual(no_space["problems"], [])

    def test_prompt_contract_context_and_privacy(self):
        design = wavefinity_web.default_design()
        first = wavefinity_web.ai_prompt_payload(
            {"description": "  A tray for three screwdrivers  ", "design": design, "space": self._space(),
             "inventory_id": "B7", "path": "C:\\Users\\someone\\secret"})
        second = wavefinity_web.ai_prompt_payload(
            {"description": "A tray for three screwdrivers", "design": design, "space": self._space()})
        self.assertNotEqual(first["request_id"], second["request_id"])
        self.assertEqual(first["context_fingerprint"], second["context_fingerprint"])
        prompt = first["prompt"]
        for needle in ("A tray for three screwdrivers", first["request_id"], first["context_fingerprint"],
                       "wavefinity-ai-design-v1", "recommend_only", "box.pegboard", "ASK the person"):
            self.assertIn(needle, prompt)
        for private in ("B7", "someone", str(Path(__file__).resolve().parent)):
            self.assertNotIn(private, prompt)
        # Old layout bounds are a reference for the current size only, and Pegboard minimums pass through.
        self.assertIn("current_baseline_layout_bounds_mm", prompt)
        self.assertIn("RETURN", prompt)
        self.assertIn('"min_z_mm":48.0', wavefinity_web.ai_prompt_payload({
            "description": "x", "design": design,
            "space": {**self._space(), "min_z": 48, "min_x": 0}})["prompt"])
        drawer = wavefinity_web.ai_prompt_payload({
            "description": "x", "design": design, "space": {"kind": "drawer", "x": 96, "y": 96, "z": 60, "min_z": 48}})
        self.assertNotIn("min_z_mm", drawer["prompt"])
        moved = json.loads(json.dumps(design))
        moved["box"]["z"] = 48.0
        third = wavefinity_web.ai_prompt_payload({"description": "x", "design": moved, "space": self._space()})
        self.assertNotEqual(third["context_fingerprint"], first["context_fingerprint"])
        for bad in ({"description": "  ", "design": design},
                    {"description": "x", "design": {"design_kind": "base_trim"}},
                    {"description": "x", "design": {"box": {"b4b": {"enabled": True}}}}):
            with self.assertRaises(ValueError):
                wavefinity_web.ai_prompt_payload(bad)

    def test_public_reference_link_is_optional_supplemental_and_never_fetched(self):
        design = wavefinity_web.default_design()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RENDER_GIT_COMMIT", None)
            stable = wavefinity_web.ai_feature_reference_url()
            self.assertEqual(
                stable, "https://raw.githubusercontent.com/happydadto5/Wavefinity/main/ai-features.md")
            os.environ["RENDER_GIT_COMMIT"] = "not-a-real-sha"
            self.assertEqual(wavefinity_web.ai_feature_reference_url(), stable)
            full_sha = "a" * 40
            os.environ["RENDER_GIT_COMMIT"] = full_sha
            pinned = wavefinity_web.ai_feature_reference_url()
            self.assertEqual(
                pinned, f"https://raw.githubusercontent.com/happydadto5/Wavefinity/{full_sha}/ai-features.md")
            os.environ.pop("RENDER_GIT_COMMIT", None)
            prompt = wavefinity_web.ai_prompt_payload(
                {"description": "x", "design": design, "space": {"kind": "drawer", "x": 80, "y": 80, "z": 50}})["prompt"]
            self.assertIn(stable, prompt)
            self.assertIn("the data above", prompt)
            self.assertIn("only if you can fetch", prompt.lower())
            repair = wavefinity_web.ai_repair_prompt_payload(
                {"request_id": "r", "context_fingerprint": "f", "response": "{}", "error": "bad"})["prompt"]
            self.assertIn(stable, repair)
        # Never an outbound call: no urlopen/requests/http.client symbol is even imported.
        self.assertNotIn("requests", dir(wavefinity_web))
        source = inspect.getsource(wavefinity_web.ai_feature_reference_url)
        for forbidden in ("urlopen", "requests.", "http.client", "subprocess", "socket"):
            self.assertNotIn(forbidden, source)

    def test_candidate_is_proven_in_real_geometry_without_side_effects(self):
        design = wavefinity_web.default_design()
        design["part_name"] = "Test Bin"  # Fix 078: part_name is itself now required
        before = json.dumps(design, sort_keys=True)
        registry = dict(wavefinity_web._PREVIEW_REQUESTS)
        good = wavefinity_web.ai_candidate_payload(
            {"design": design, "client_id": "ai-lane", "generation": 1})
        self.assertEqual(good["problems"], [])
        self.assertTrue(good["preview"]["fits"])
        self.assertEqual(good["design"], good["preview"]["design"])
        self.assertEqual(json.dumps(design, sort_keys=True), before)
        # Only its own lane was touched, so it can never supersede a Designer preview.
        self.assertEqual({k for k in wavefinity_web._PREVIEW_REQUESTS} - set(registry),
                         {("ai-lane", "preview")})
        # A geometry failure is reported, not applied.
        post = wavefinity_web.default_feature_payload({"design": design, "kind": "post"})["feature"]
        post["options"]["diameter"] = 60.0
        broken = json.loads(json.dumps(design))
        broken["layout"]["features"] = [post]
        self.assertTrue(wavefinity_web.ai_candidate_payload({"design": broken})["problems"])
        # Structural, media-derived and unreadable designs are refused with a safe reason.
        nest = json.loads(json.dumps(design))
        nest["layout"]["features"] = [{"kind": "nest", "zone": [-4, -4, 4, 4]}]
        for bad in (nest, {"version": 1}, {"design_kind": "base_trim"}, "not a design"):
            with self.assertRaises(ValueError) as caught:
                wavefinity_web.ai_candidate_payload({"design": bad})
            self.assertNotIn("Traceback", str(caught.exception))

    def test_repair_prompt_is_exact_and_safe(self):
        made = wavefinity_web.ai_repair_prompt_payload({
            "request_id": "wf-ai-1", "context_fingerprint": "abc123",
            "response": '{"schema": "oops"}',
            "error": "Could not read C:\\Users\\me\\Wavefinity\\x.json\nTraceback (most recent call last): boom",
        })["prompt"]
        for needle in ("wavefinity-ai-design-v1", "wf-ai-1", "abc123", '{"schema": "oops"}',
                       "exactly ONE corrected JSON object"):
            self.assertIn(needle, made)
        for private in ("Users", "Traceback", "boom"):
            self.assertNotIn(private, made)
        with self.assertRaises(ValueError):
            wavefinity_web.ai_repair_prompt_payload({"request_id": "", "context_fingerprint": "x", "response": "y"})


if __name__ == "__main__":
    unittest.main()
