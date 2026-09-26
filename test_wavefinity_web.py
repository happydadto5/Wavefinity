"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

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
    def test_b4b_blank_label_preference_keeps_preview_intact(self):
        for location in ("top", "front"):
            with self.subTest(location=location):
                design = default_design()
                design["box"].update({
                    "x": 64.0, "y": 48.0, "z": 40.0,
                    # B4B's minimum wall (a carried, latched case starts at
                    # "Strong") is above the ordinary-bin default of 0.8 mm;
                    # standard_walls=False is needed too, or the custom wall
                    # value below is overridden back to the 0.8 mm default.
                    "wall": 1.2,
                    "standard_walls": False,
                    "b4b": {
                        "enabled": True, "lid": True, "secure_lid": True,
                        "latch_count": "auto", "latch_strength": "standard",
                        "lid_headroom_mm": 1.0, "label_text": "",
                        "label_location": location, "stacking": False,
                    },
                })
                preview = preview_payload({"design": design})
                self.assertTrue(preview["fits"], preview["message"])
                # B4B previews ship the compact grouped-flat-array transport
                # ("meshes") instead of the per-face "geometry" ordinary bins
                # use - "geometry" is always [] for a B4B preview by design.
                self.assertTrue(preview["meshes"])
                self.assertEqual(preview["b4b"]["label_location"], "none")

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
        self.assertIn(
            {"key": "angle_towards", "type": "enum"},
            parts["bore"]["options"],
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

    def test_catalog_exposes_side_opening_constants_presets_and_defaults(self):
        rules = catalog_payload()["side_openings"]
        self.assertEqual(rules["min_side_mm"], 16.0)
        self.assertEqual(rules["corner_margin_mm"], 4.0)
        self.assertEqual(rules["top_bridge_mm"], 4.0)
        self.assertEqual(rules["default_shape"], "curved")
        self.assertEqual(rules["default_size"], "medium")
        self.assertEqual(rules["default_from_bottom_percent"], 0)
        self.assertEqual(rules["default_from_top_percent"], 0)
        self.assertEqual(rules["arch_curve"], 0.5)
        self.assertEqual(
            {(row["value"], row["width_mm"]) for row in rules["sizes"]},
            {("small", 8.0), ("medium", 10.0), ("large", 15.0), ("xl", 20.0)},
        )
        self.assertEqual(
            {row["value"] for row in rules["sides"]}, {"front", "back", "left", "right"}
        )

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

    def test_b4b_and_base_trim_do_not_surface_side_openings(self):
        design = default_design()
        design["box"].update({
            "x": 64.0, "y": 48.0, "z": 40.0, "wall": 1.4, "standard_walls": False,
            "b4b": {
                "enabled": True, "lid": True, "secure_lid": True,
                "latch_count": "auto", "latch_strength": "standard",
                "lid_headroom_mm": 1.0, "label_text": "",
                "label_location": "none", "stacking": False,
            },
            "side_openings": {
                "enabled": True, "shape": "curved", "sides": ["front"],
                "size": "small", "from_bottom_percent": 0.0,
                "from_top_percent": 0.0, "percent_mode": "inset_v2",
            },
        })
        with self.assertRaises(ValueError):
            design_from_dict(design)

    def test_default_design_is_unchanged_by_side_openings(self):
        design = default_design()
        self.assertNotIn("side_openings", design["box"])
        box, *_ = design_from_dict(design)
        self.assertFalse(box.side_openings.enabled)

    def test_side_opening_resize_replaces_or_removes_ineligible_sides(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for the focused browser-state regression")
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index("// BEGIN SIDE_OPENING_SELECTION_HELPER")
        end = source.index("// END SIDE_OPENING_SELECTION_HELPER")
        helper = source[start:end]

        def reconcile(selected, eligible):
            script = (
                helper + "\nprocess.stdout.write(JSON.stringify("
                f"reconcileSideOpeningSelection({json.dumps(selected)}, {json.dumps(eligible)})));"
            )
            result = subprocess.run(
                [node, "-e", script], check=True, capture_output=True, text=True,
            )
            return json.loads(result.stdout)

        # 3U x 3U, Front selected, then X shrinks to 1U: the invalid Front
        # side is removed and the first eligible Y-running wall replaces it.
        self.assertEqual(
            reconcile(["front"], ["left", "right"]),
            {"sides": ["left"], "removed": ["front"], "replacement": "left"},
        )
        # With no eligible axis, no selected side survives or gets invented;
        # the caller disables the option rather than sending invalid data.
        self.assertEqual(
            reconcile(["front"], []),
            {"sides": [], "removed": ["front"], "replacement": None},
        )
        reconcile_start = source.index("function reconcileSideOpeningsAfterResize(design)")
        reconcile_end = source.index("// Python remains authoritative", reconcile_start)
        self.assertIn(
            "design.box.side_openings = { ...SIDE_OPENING_DEFAULTS };",
            source[reconcile_start:reconcile_end],
        )

        update_start = source.index("function updateDesignFromForm()")
        update_end = source.index("const saveOutputPreference", update_start)
        update_source = source[update_start:update_end]
        self.assertLess(
            update_source.index("reconcileSideOpeningsAfterResize(design)"),
            update_source.index("readSideOpeningForm(design)"),
        )

    def test_bore_catalog_exposes_the_grid_and_angle_and_drops_quantity(self):
        parts = {part["kind"]: part for part in catalog_payload()["parts"]}
        bore = parts["bore"]
        self.assertFalse(bore["flags"]["qty"])
        labels = [field["label"] for field in bore["fields"]]
        self.assertIn("X quantity", labels)
        self.assertIn("Y quantity", labels)
        self.assertIn("Angle °", labels)

    def test_bore_catalog_exposes_style_and_sizing_mode_enums(self):
        parts = {part["kind"]: part for part in catalog_payload()["parts"]}
        fields = {field["key"]: field for field in parts["bore"]["fields"]}
        self.assertEqual(fields["bore_style"]["type"], "enum")
        # The two sizing modes are stored words, not editor number fields.
        self.assertEqual(inserts._registry.OPTION_TYPES["xy_size_mode"], "enum")
        self.assertEqual(inserts._registry.OPTION_TYPES["height_size_mode"], "enum")
        # Fix 068: the redundant Bore wall style and the Auto booleans are gone.
        for retired in ("wall_style", "auto_base", "auto_height", "auto_grid"):
            self.assertNotIn(retired, fields)
        self.assertFalse(parts["bore"]["flags"]["qty"])

    def test_bore_resolved_defaults_are_base_straight(self):
        design = default_design()
        item = {"name": "tube", "profile": "round",
                "segments": [{"length": 40, "diameter": 6}], "clearance": 0.25}
        plain = default_feature_payload({"design": design, "kind": "bore", "item": item})
        self.assertEqual(plain["resolved_options"]["bore_style"], "base_straight")
        self.assertEqual(plain["resolved_options"]["wall"], 1.6)
        self.assertEqual(plain["resolved_options"]["xy_size_mode"], "manual")
        self.assertEqual(plain["resolved_options"]["height_size_mode"], "manual")
        self.assertNotIn("wall_style", plain["resolved_options"])

    def test_walls_only_bore_default_wall_comes_from_the_bin_wall(self):
        design = default_design()
        design["box"].update({"wall": 2.4, "standard_walls": False, "x": 64.0, "y": 64.0})
        item = {"name": "tube", "profile": "round",
                "segments": [{"length": 40, "diameter": 6}], "clearance": 0.25}
        full = default_feature_payload({"design": design, "kind": "bore", "item": item})
        self.assertEqual(full["resolved_options"]["wall"], 1.6)
        feature = full["feature"]
        feature["options"] = {**feature.get("options", {}), "bore_style": "walls_wavy"}
        feature["options"].pop("wall", None)
        feature["zone"] = [-20.0, -20.0, 20.0, 20.0]
        design["layout"]["features"] = [feature]
        result = draft_payload({"design": design, "feature": feature})
        self.assertEqual(result["resolved_options"]["bore_style"], "walls_wavy")
        self.assertEqual(result["resolved_options"]["wall"], design["box"]["wall"])
        # Walls Only sizes the bin around itself by default.
        self.assertEqual(result["resolved_options"]["xy_size_mode"], "bin_to_bore")
        self.assertEqual(result["feature"]["options"]["xy_size_mode"], "bin_to_bore")

    def test_bore_editor_source_has_four_styles_and_persistent_sizing_modes(self):
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = app_js.index("    if (isBore) {")
        renderer = app_js[start:app_js.index('    } else if (isPocket || one.kind === "slot") {', start)]
        # Exactly four Style labels, one owner, no secondary Bore Walls selector.
        for label in ("Base - Straight Walls", "Base - Wavy Walls",
                      "Straight Walls Only", "Wavy Walls Only"):
            self.assertIn(label, app_js)
        self.assertEqual(renderer.count('data-draft="option:bore_style"'), 1)
        self.assertNotIn("option:wall_style", renderer)
        self.assertNotIn("wallStyleField", renderer)
        # Persistent sizing modes replace the toggle buttons and one-shot buttons.
        for text in ('data-action="bore-auto"', 'data-action="bore-xy-to-bin"',
                     'data-action="bore-xy-to-bore"', 'data-action="bore-height-to-bin"',
                     'data-action="bore-height-to-bore"', "bore-one-shot", 'value="Auto"',
                     "autoButton", "autoField"):
            self.assertNotIn(text, renderer, text)
        for name in ("sizeBoreBaseToBinOnce", "sizeBoreHeightToBinOnce",
                     "sizeBinHeightToBoreOnce", "enableBoreAuto", "manualizeBoreAuto",
                     "applyBoreAuto", "boreSizingControlsFor", "finishBoreAutoChange"):
            self.assertNotIn(name, app_js, name)
        self.assertNotIn("result.wavy_base_bin", app_js)
        for text in ("Set base width / length", "Set height", "Auto size bore to bin",
                     "Auto size bin to bore", '"xy_size_mode"', '"height_size_mode"'):
            self.assertIn(text, renderer, text)
        # Counts are always explicit fields, never an Auto pair.
        self.assertIn('gridField("columns", "X count")', renderer)
        self.assertIn('gridField("rows", "Y count")', renderer)
        # Walls Only: no Base Width / Length, thickness only there, depth only for Base.
        self.assertIn("const showXy = !wallsOnly && xyMode === \"manual\";", renderer)
        self.assertIn('${wallsOnly ? "" : optionField("depth"', renderer)
        self.assertIn('${wallsOnly ? dividerThicknessField(boreWallShown, "option:wall") : ""}', renderer)
        self.assertNotIn('optionField("wall"', renderer)
        # The persistent bin-to-bore pass reuses the one expand endpoint.
        recon = app_js[app_js.index("async function reconcileBoreBin(result) {"):]
        recon = recon[:recon.index("\n}\n")]
        self.assertIn("sizeBinHeightToBore({ silent: true, guard: isCurrent })", recon)
        self.assertIn("keepDraft: true, silent: true, fit: true, guard: isCurrent", recon)
        self.assertIn("state.boreFitPending", recon)
        self.assertIn("state.boreFitDone", recon)
        self.assertNotIn("boreFitSignature", app_js)
        self.assertIn("fit_height_to_bore: true", app_js)
        # Style words never go through the numeric option path.
        self.assertIn('"bore_style", "wall_style", "xy_size_mode", "height_size_mode", "holder_style"', app_js)
        # Walls Only -> Base keeps a floor-reaching cavity by taking the Height as depth.
        style_change = app_js[app_js.index('if (changed === "option:bore_style") {'):]
        style_change = style_change[:style_change.index('if (changed === "option:xy_size_mode")')]
        self.assertIn("one.options.depth = resolvedHeight;", style_change)
        self.assertIn('one.options.xy_size_mode = "bin_to_bore";', style_change)
        self.assertIn("delete one.options.angle_towards;", style_change)
        # Sizing mirrors the backend shell reach from the catalog's wave values.
        sizing = app_js[app_js.index("function sizeBoreToGrid(one) {"):]
        sizing = sizing[:sizing.index("function sizePostToRow")] if "function sizePostToRow" in sizing else sizing
        self.assertIn("wave_amplitude_mm", sizing)
        self.assertIn("wall_depth_factor", sizing)
        self.assertIn("waveNoiseFloor = 1e-4", sizing)
        self.assertIn("2 * amplitude + wall * depthFactor + waveNoiseFloor", sizing)
        # Round profiles use a conservative circumscribed clear span (256 sides).
        self.assertIn("held / Math.cos(Math.PI / 256)", sizing)
        # The Walls Only base foot (WALL_ONLY_FOOT) counts on both outside sides,
        # for Walls Only only - never Base - Wavy Walls.
        self.assertIn("wallOnlyFoot = walls ? 0.5 : 0", sizing)
        self.assertIn("2 * shellReach + 2 * wallOnlyFoot", sizing)
        # Old Auto booleans are no longer state owners anywhere in the browser.
        for text in ("options.auto_base", "options.auto_height", "options.auto_grid",
                     "opts.auto_base", "opts.auto_height", "opts.auto_grid"):
            self.assertNotIn(text, app_js, text)

    def test_bore_pocket_slot_floor_gap_rule_is_kept_only_for_pocket_and_slot(self):
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        body = app_js[app_js.index("function keepCutBelowHeight("):]
        body = body[:body.index("\nfunction updateDraftFromFields")]
        self.assertIn('if (one.kind === "bore") {', body)
        self.assertIn("gap = 0;", body)
        self.assertIn("gap = 2", body)          # the Pocket / Slot default is unchanged

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

    def test_obsolete_easy_clean_keys_are_ignored(self):
        design = default_design()
        design["box"].update({
            "easy_clean": True,
            "easy_clean_style": "curve",
            "easy_clean_radius": 4.0,
        })
        box, layout, label, part, location, scoop = design_from_dict(design)
        self.assertFalse(hasattr(box, "easy_clean"))
        saved = wavefinity_web.design_to_dict(box, layout, label, part, location, scoop)
        self.assertNotIn("easy_clean", saved["box"])

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

    def test_new_divider_starts_with_one_wall_on_x_axis(self):
        response = default_feature_payload({"design": default_design(), "kind": "divider"})
        options = response["feature"]["options"]
        self.assertEqual(options["count_x"], 1)
        self.assertEqual(options["count_y"], 0)
        self.assertEqual(options["wall_style"], "wavy")
        self.assertEqual(response["resolved_options"]["count_x"], 1)
        self.assertEqual(response["resolved_options"]["count_y"], 0)

    def test_photo_nest_defaults_include_automatic_lift_assist(self):
        design = default_design()
        response = default_feature_payload({
            "design": design, "kind": "nest",
        })
        feature = response["feature"]
        # A brand-new (not yet photographed) Photo Nest shows the new-scan
        # defaults immediately, so the editor never displays a holder style
        # the upload it is about to trigger will not actually build - see
        # organizer_app.default_feature()'s "nest" branch.
        self.assertEqual(feature["options"], {
            "holder_style": "recessed", "cavity_depth_mode": "auto",
            "auto_size": True, "lift_assist": "auto",
        })
        self.assertIsNone(feature["contour"])
        resolved = response["resolved_options"]
        # A non-legacy nest's new-scan default is the literal "auto" choice
        # (not a concrete "finger_grasp"/"push_out" pick) - only a legacy
        # design predating the Automatic option defaults to "finger_grasp".
        self.assertEqual(resolved["lift_assist"], "auto")
        self.assertEqual(resolved["finger_position"], "sides")
        self.assertEqual(resolved["finger_width"], 25.0)
        self.assertEqual(resolved["push_position"], "right")
        self.assertEqual(resolved["push_area"], 30.0)
        self.assertEqual(resolved["push_depth"], 4.0)

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

    def test_photo_nest_apply_refits_a_client_placeholder_zone(self):
        """Changing a nest setting must never save the browser's rough zone."""
        outline = PhotoOutline(
            ((-5, -3), (5, -3), (5, 3), (-5, 3)), 10.0, 6.0,
            ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            made = _traced_photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {"depth": 2.0},
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
            made = _traced_photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {"depth": 5.0},
            })
        original = made["design"]
        feature = original["layout"]["features"][0]
        feature["rotation"] = 90.0
        rotated = apply_feature_payload({"design": original, "feature": feature, "index": 0})["design"]
        # A 90-degree rotation swaps which axis the contour's long/short
        # sides run along, so auto-sizing swaps box x/y to match - it does
        # not just grow y while leaving x as it was.
        self.assertEqual(rotated["box"]["y"], original["box"]["x"])
        self.assertEqual(rotated["box"]["x"], original["box"]["y"])
        self.assertGreater(rotated["box"]["y"], original["box"]["y"])
        feature = rotated["layout"]["features"][0]
        feature["scale"] = 1.5
        scaled = apply_feature_payload({"design": rotated, "feature": feature, "index": 0})["design"]
        self.assertGreaterEqual(scaled["box"]["x"], rotated["box"]["x"])
        self.assertGreater(scaled["box"]["y"], rotated["box"]["y"])

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

    def test_photo_nest_outline_mode_and_shared_preview_are_explicit(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        preview_source = (root / "organizer_app.py").read_text(encoding="utf-8")
        self.assertIn("&& state.nestOutlineEditing === true\n    && (hasPhotoSession", app_js)
        self.assertIn('feature.contour && isNestEditWorkspaceActive()\n        && (state.nestOutlineTool', app_js)
        self.assertIn("effective_recessed", preview_source)
        self.assertIn("draft_in_recessed_group", preview_source)

    def test_fix21_multi_nest_apply_edit_and_non_nest_exclusion(self):
        first = _fix21_photo_design()["design"]
        duplicated = wavefinity_web.duplicate_feature_payload({"design": first, "index": 0})
        design = duplicated["design"]
        original_first = json.loads(json.dumps(design["layout"]["features"][0]))
        edited = json.loads(json.dumps(design["layout"]["features"][1]))
        edited["rotation"] = 180.0
        edited_result = apply_feature_payload({
            "design": design, "feature": edited, "index": 1,
        })
        features = edited_result["design"]["layout"]["features"]
        self.assertEqual(len(features), 2)
        self.assertEqual(features[0], original_first)
        self.assertEqual(features[1]["rotation"], 180.0)

        post = default_feature_payload({
            "design": edited_result["design"], "kind": "post",
        })["feature"]
        with self.assertRaisesRegex(ValueError, "Photo Nest designs"):
            apply_feature_payload({
                "design": edited_result["design"], "feature": post, "index": None,
            })

    def test_fix21_replace_photo_targets_one_index_and_requires_an_index(self):
        made = _fix21_photo_design()
        duplicated = wavefinity_web.duplicate_feature_payload({
            "design": made["design"], "index": 0,
        })
        design = duplicated["design"]
        before_first = json.loads(json.dumps(design["layout"]["features"][0]))
        before_second = json.loads(json.dumps(design["layout"]["features"][1]))
        replacement = [[-12.0, -6.0], [12.0, -6.0], [12.0, 6.0], [-12.0, 6.0]]
        replaced = photo_nest_payload({
            "design": design, "contour": replacement, "index": 1,
        })
        features = replaced["design"]["layout"]["features"]
        self.assertEqual(features[0], before_first)
        self.assertNotEqual(features[1]["contour"], before_second["contour"])
        self.assertEqual(features[1]["contour"], replacement)
        with self.assertRaisesRegex(ValueError, "Duplicate an existing Photo Nest first"):
            photo_nest_payload({"design": design, "contour": replacement})

    def test_fix21_single_and_multi_auto_sizing_preserve_required_centres(self):
        made = _fix21_photo_design()
        design = made["design"]
        one = design["layout"]["features"][0]
        self.assertAlmostEqual((one["zone"][0] + one["zone"][2]) / 2.0, 0.0)
        self.assertAlmostEqual((one["zone"][1] + one["zone"][3]) / 2.0, 0.0)
        self.assertEqual(design["box"]["x"] % 8.0, 0.0)
        self.assertEqual(design["box"]["y"] % 8.0, 0.0)

        duplicated = wavefinity_web.duplicate_feature_payload({"design": design, "index": 0})
        multi = duplicated["design"]
        centres_before = [
            ((one["zone"][0] + one["zone"][2]) / 2.0,
             (one["zone"][1] + one["zone"][3]) / 2.0)
            for one in multi["layout"]["features"]
        ]
        edited = json.loads(json.dumps(multi["layout"]["features"][1]))
        edited["options"]["repeat_spacing_percent"] = 100
        resized = apply_feature_payload({"design": multi, "feature": edited, "index": 1})["design"]
        centres_after = [
            ((one["zone"][0] + one["zone"][2]) / 2.0,
             (one["zone"][1] + one["zone"][3]) / 2.0)
            for one in resized["layout"]["features"]
        ]
        self.assertEqual(centres_after, centres_before)

    def test_fix21_manual_never_grows_and_legacy_auto_only_grows(self):
        made = _fix21_photo_design()["design"]
        made["box"]["x"] = made["box"]["y"] = 192.0
        made["layout"]["features"][0]["options"]["auto_size"] = False
        duplicate = wavefinity_web.duplicate_feature_payload({"design": made, "index": 0})
        self.assertEqual(duplicate["design"]["box"]["x"], 192.0)
        self.assertEqual(duplicate["design"]["box"]["y"], 192.0)

        legacy = _fix21_photo_design()["design"]
        old_size = (legacy["box"]["x"], legacy["box"]["y"])
        legacy_one = legacy["layout"]["features"][0]
        legacy_one["options"].pop("auto_size")
        legacy_one["count"] = 4
        grown = apply_feature_payload({
            "design": legacy, "feature": legacy_one, "index": 0,
        })["design"]
        self.assertGreaterEqual(grown["box"]["x"], old_size[0])
        self.assertGreaterEqual(grown["box"]["y"], old_size[1])
        self.assertTrue(
            grown["box"]["x"] > old_size[0] or grown["box"]["y"] > old_size[1]
        )

    def test_fix21_duplicate_copies_all_fields_selects_and_auto_grows(self):
        design = _fix21_photo_design()["design"]
        source = design["layout"]["features"][0]
        source["count"] = 2
        source["alternate_ends"] = True
        source["rotation"] = 90.0
        source["scale"] = 1.2
        source["options"].update({
            "repeat_spacing_percent": 75, "smoothing": 1.5,
            "finger_position": "both", "push_area": 25.0,
        })
        saved = apply_feature_payload({"design": design, "feature": source, "index": 0})["design"]
        old_area = saved["box"]["x"] * saved["box"]["y"]
        duplicated = wavefinity_web.duplicate_feature_payload({"design": saved, "index": 0})
        self.assertEqual(duplicated["selected"], 1)
        first, second = duplicated["design"]["layout"]["features"]
        for key in ("contour", "source_contour", "scale", "rotation", "count", "alternate_ends"):
            self.assertEqual(second[key], first[key])
        self.assertEqual(second["options"], first["options"])
        second["options"]["clearance"] = 99
        self.assertNotEqual(second["options"]["clearance"], first["options"]["clearance"])
        new_box = duplicated["design"]["box"]
        self.assertGreater(new_box["x"] * new_box["y"], old_area)

    def test_fix21_duplicate_manual_failure_is_exact_and_non_mutating(self):
        design = _fix21_photo_design()["design"]
        design["layout"]["features"][0]["options"]["auto_size"] = False
        before = json.dumps(design, sort_keys=True)
        with self.assertRaises(ValueError) as caught:
            wavefinity_web.duplicate_feature_payload({"design": design, "index": 0})
        self.assertEqual(
            str(caught.exception),
            "No room to duplicate this Photo Nest. Turn Automatic footprint sizing on or enlarge the bin.",
        )
        self.assertEqual(json.dumps(design, sort_keys=True), before)

    def test_fix21_occurrence_preview_and_new_scan_repeat_defaults(self):
        made = _fix21_photo_design()
        feature = made["design"]["layout"]["features"][0]
        self.assertEqual(feature["count"], 1)
        self.assertFalse(feature["alternate_ends"])
        self.assertNotIn("repeat_spacing_percent", feature["options"])
        feature["count"] = 4
        feature["rotation"] = 90.0
        feature["alternate_ends"] = True
        changed = apply_feature_payload({
            "design": made["design"], "feature": feature, "index": 0,
        })["design"]
        preview = preview_payload({"design": changed})
        occurrences = preview["nest_occurrences"][0]
        self.assertEqual(len(occurrences), 4)
        self.assertEqual([one["rotation"] for one in occurrences], [90.0, 270.0, 90.0, 270.0])

    def test_fix21_duplicate_then_replace_changes_only_the_copy(self):
        made = _fix21_photo_design()
        duplicated = wavefinity_web.duplicate_feature_payload({
            "design": made["design"], "index": 0,
        })["design"]
        original = json.loads(json.dumps(duplicated["layout"]["features"][0]))
        replacement = [[-9.0, -4.0], [9.0, -4.0], [9.0, 4.0], [-9.0, 4.0]]
        result = photo_nest_payload({
            "design": duplicated, "contour": replacement, "index": 1,
        })["design"]
        self.assertEqual(result["layout"]["features"][0], original)
        self.assertEqual(result["layout"]["features"][1]["contour"], replacement)

    def test_fix21_recessed_to_raised_draft_replaces_saved_group_member(self):
        duplicated = wavefinity_web.duplicate_feature_payload({
            "design": _fix21_photo_design()["design"], "index": 0,
        })["design"]
        box, layout, *_ = design_from_dict(duplicated)
        selected = layout.features[0]
        raised_options = dict(selected.options)
        raised_options["holder_style"] = "raised_wall"
        raised_options["lift_assist"] = "none"
        raised = replace(selected, options=raised_options)
        with patch.object(organizer_app, "build_features", return_value=[]) as build:
            organizer_app.preview_geometry(
                box, features=layout.features, draft=raised, selected=0,
            )
        groups = [list(call.args[1]) for call in build.call_args_list]
        self.assertIn([layout.features[1]], groups)
        self.assertIn([raised], groups)
        self.assertFalse(any(selected in group for group in groups))

    def test_fix21_grouped_recessed_preview_keeps_customization_and_grip_validation(self):
        design = _fix21_photo_design()["design"]
        box, layout, *_ = design_from_dict(design)
        feature = layout.features[0]
        with patch.object(
            organizer_app, "_customization_zones", return_value=[("scoop", feature.zone)],
        ):
            scene = organizer_app.preview_geometry(box, features=layout.features)
        self.assertIn(0, scene["invalid_feature_indexes"])
        self.assertTrue(any("overlaps the scoop" in error for error in scene["feature_errors"]))

        with patch.object(organizer_app, "inside_handle_conflict", return_value="inside grip"):
            scene = organizer_app.preview_geometry(box, features=layout.features)
        self.assertIn(0, scene["invalid_feature_indexes"])
        self.assertTrue(any("inside grip" in error for error in scene["feature_errors"]))

    def test_fix21_frontend_and_shared_preview_source_contracts(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        app_py = (root / "organizer_app.py").read_text(encoding="utf-8")

        render_start = app_js.index("function renderDraftFields() {")
        render_end = app_js.index("function updateDraftFromFields(event) {", render_start)
        nest_render = app_js[render_start:render_end]
        self.assertNotIn('changed === "nest-', nest_render)
        self.assertNotIn('get("nest-', nest_render)

        for label in ("Minimum", "-75%", "-50%", "-25%", "Auto", "+25%", "+50%", "+75%", "+100%"):
            self.assertIn(label, app_js)
        self.assertIn('[[0, "As Scanned"], [90, "90°"], [180, "180°"], [270, "270°"]]', app_js)
        self.assertIn('plainCheckbox("nest-alternate", "Flip every other one"', app_js)
        self.assertIn('data-action="duplicate-nest"', app_js)
        self.assertIn("Math.round(raw / 90) * 90", app_js)
        self.assertIn("state.preview.draft_nest_occurrences", app_js)
        self.assertIn("state.preview.nest_occurrences", app_js)
        self.assertIn("isNestEditWorkspaceActive()", app_js)
        self.assertIn("state.nestOutlineEditing === true", app_js)
        self.assertIn('feature.contour && isNestEditWorkspaceActive()', app_js)
        self.assertIn('filter(one => one.kind === "nest").length === 1', app_js)

        help_start = app_js.index("function updatePreviewHelp(view) {")
        help_end = app_js.index("async function maybeWarnSpaceWallMismatch", help_start)
        help_source = app_js[help_start:help_end]
        self.assertIn("source-outline point", help_source)
        self.assertIn("whole repeated Photo Nest group", help_source)
        sync_start = app_js.index("function syncNest2DWorkspace() {")
        sync_end = app_js.index("function renderNestPaperOutline", sync_start)
        self.assertIn('updatePreviewHelp("2d")', app_js[sync_start:sync_end])

        selection_start = app_js.index("function updateSelectionButtons() {")
        selection_end = app_js.index("function updateDraftStatusColor", selection_start)
        selection_source = app_js[selection_start:selection_end]
        self.assertIn("button.disabled = busy || (hasPhotoNest && !isModifier);", selection_source)
        self.assertNotIn("replacingPhotoNest", selection_source)
        pick_start = app_js.index("function pickKind(kind) {")
        pick_end = app_js.index("async function selectEdgeMount", pick_start)
        self.assertIn("if (!isModifier && state.design", app_js[pick_start:pick_end])

        selected_start = app_js.index("async function selectedFeature(index, force = false) {")
        selected_end = app_js.index("function field(", selected_start)
        self.assertIn('selected?.kind === "nest") resetNestPhotoSession()', app_js[selected_start:selected_end])
        blank_start = app_js.index("if (index === null) {", app_js.index("function wireLayoutInteraction()"))
        self.assertIn("resetNestPhotoSession();", app_js[blank_start:blank_start + 420])
        modifier_start = app_js.index("async function openModifier(")
        self.assertIn("resetNestPhotoSession();", app_js[modifier_start:modifier_start + 500])

        duplicate_start = app_js.index("async function duplicateNest() {")
        duplicate_end = app_js.index("async function resetNestOutline", duplicate_start)
        duplicate_source = app_js[duplicate_start:duplicate_end]
        self.assertLess(duplicate_source.index("await commitVisibleDraft();"),
                        duplicate_source.index("previousDesign = clone(state.design);"))
        self.assertIn("state.draftSourceIndex = previousSelected;", duplicate_source)

        # Fix 053: partDefaultsFromFeature/seedFeatureFromPartDefaults are back
        # (always-on Space preference memory); their behaviour is covered in
        # test_space_preferences.py.

        self.assertIn('geometry_owner=f"{one.kind} feature"', app_py)
        self.assertIn('geometry_owner=f"{draft.kind} draft"', app_py)
        self.assertIn("solid = apply_side_openings(box, solid)", app_py)
        shared_start = app_py.index("if effective_recessed:")
        loop_start = app_py.index("for feature_index, one in enumerate(features):", shared_start)
        shared_source = app_py[shared_start:loop_start]
        self.assertIn("apply_edge_mount_hole_cuts", shared_source)
        self.assertIn("apply_side_openings", shared_source)

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

    def test_grid_divider_preview_marks_sloped_bases_separately(self):
        design = default_design()
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        feature["options"].update({
            "count_x": 1, "count_y": 1, "slope_base": True,
            "bottom_angle": 20.0,
        })
        design["layout"]["features"] = [feature]
        preview = preview_payload({"design": design})
        kinds = {face["kind"] for face in preview["geometry"]}
        self.assertIn("feature_divider", kinds)
        self.assertIn("feature_divider_slope", kinds)

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

    def test_legacy_divider_without_scoop_configuration_still_loads(self):
        design = default_design()
        feature = default_feature_payload({
            "design": design, "kind": "divider",
        })["feature"]
        self.assertNotIn("scoop", feature["options"])
        design["layout"]["features"] = [feature]
        box, layout, *_ = design_from_dict(design)
        self.assertNotIn("scoop", layout.features[0].options)
        self.assertTrue(build_features(
            box, layout.features, base_height(box, layout.mode),
        ))

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

    def test_auto_expand_gives_alternating_auto_cradles_their_full_run(self):
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
        feature["alternate_ends"] = True
        feature["zone"] = [-6.5, -20.0, 6.5, 20.0]
        design["layout"]["features"] = [feature]

        expanded = expand_layout_payload({"design": design})
        self.assertTrue(expanded["grew"])
        box, layout, *_ = design_from_dict(expanded["design"])
        self.assertGreaterEqual(layout.features[0].zone.width, 50.0)
        preview = preview_payload({"design": expanded["design"]})
        self.assertFalse(preview["feature_errors"])

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

    def test_text_part_rim_shelf_uses_its_selected_side(self):
        design = default_design()
        design["box"].update({"x": 64.0, "y": 48.0})
        design["layout"]["features"] = [
            _text_feature("M3", level="rim", rim_side="right")
        ]
        preview = preview_payload({"design": design})
        self.assertEqual(preview["label_meta"]["side"], "right")
        xs = [point[0] for ring in preview["label_outline"] for point in ring]
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

    def test_generate_payload_suppression_and_hosted_qty_zero(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            box = Path(temp_dir) / "Box.3mf"
            box.touch()
            made = {"box": {"output": str(box)}}
            with (
                patch.object(wavefinity_web, "_generation_output", return_value=Path(temp_dir)),
                patch.object(wavefinity_web, "inventory_enabled", return_value=True),
                patch.object(wavefinity_web, "generate_organizer_files", return_value=made) as gen,
            ):
                wavefinity_web.generate_payload({"design": default_design(), "keep_log": True})
                self.assertTrue(gen.call_args.kwargs["keep_log"])
                wavefinity_web.generate_payload(
                    {"design": default_design(), "keep_log": True}, suppress_local_inventory=True)
                self.assertFalse(gen.call_args.kwargs["keep_log"])
            with (
                patch.object(wavefinity_web, "HOSTED", True),
                patch.object(wavefinity_web, "_generation_output", return_value=Path(temp_dir)),
                patch.object(wavefinity_web, "generate_organizer_files", return_value=made),
                patch.object(wavefinity_web, "_generation_reply", return_value={}),
            ):
                reply = wavefinity_web.generate_payload(
                    {"design": default_design(), "keep_log": True})
            self.assertEqual(reply["inventory_bin"]["qty"], 0)

    def test_bulk_print_web_source_contract(self):
        root = Path(__file__).resolve().parent / "web"
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        model = (root / "drawer-model.js").read_text(encoding="utf-8")
        css = (root / "drawer.css").read_text(encoding="utf-8")
        self.assertNotIn("dl-new-printed", panel + css)
        self.assertNotIn("new_bins_printed: false", model)
        for ident in ("dl-batch-select-all", "dl-batch-clear", "dl-batch-delete", "dl-batch-save", "dl-batch-print"):
            self.assertIn(f'id="{ident}"', panel)
        self.assertNotIn("Print Spacers + Connectors", panel)
        self.assertNotIn('id="dl-batch-connectors"', panel)
        # Session-only selection: never written into the layout or storage.
        defaults = model[model.index("DL.defaultSettings"):model.index("DL.canonicalLayoutRules")]
        self.assertNotIn("print", defaults)
        self.assertNotIn("localStorage", panel[panel.index("DP.printSelected ="):][:200])
        self.assertIn('one.status !== "printed"', panel)
        self.assertIn("DL.printCount(one)", panel)
        self.assertIn('$("#dl-batch-delete").disabled', panel)
        self.assertIn('$("#dl-batch-save").hidden = hosted;', panel)
        fn = model[model.index("DL.printSelectedBins ="):]
        fn = fn[:fn.index("DL.printDrawer =")]
        self.assertLess(fn.index("await DL.save()"), fn.index("/api/drawer/print-bins"))
        self.assertIn("DL.adoptBatchResult(result)", fn)
        self.assertIn("DL.adopt(result);", model[model.index("DL.adoptBatchResult ="):][:200])
        self.assertIn("DP.renderInventory(true)", fn)
        self.assertNotIn("set copies to", model)
        node = shutil.which("node")
        if node:
            for name in ("drawer-model.js", "drawer-panel.js"):
                done = subprocess.run([node, "--check", str(root / name)], capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)

    def test_fix067_inventory_selection_numbers_and_spacers(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parent / "web"
        script = r'''
const vm = require("vm"), fs = require("fs");
const ctx = { console, Math, JSON, Number, Set, Map, Date,
  debounce: fn => fn, clone: v => JSON.parse(JSON.stringify(v)),
  drawerHardClearance: () => 0.6, fmt: v => String(v),
  localStorage: { getItem: () => null }, $: () => null,
  state: { activeSpaceId: "A", output: "folder", runtime: { hosted: true }, activeSpace: { kind: "drawer" } } };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + ";this.DL=DL", ctx);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8") + ";this.DP=DP", ctx);
const { DL, DP } = ctx;
DL.bins = [
  { id: "B7", kind: "bin", name: "Alpha", x: 16, y: 16, z: 20, status: "in_design" },
  { id: "S1", kind: "spacer", name: "Spacer", x: 8, y: 8, z: 12, status: "saved" },
  { id: "B9", kind: "manual", name: "Beta", x: 16, y: 16, z: 30, status: "saved" },
];
DL.normaliseLayout({ settings: { show_empty: false }, drawers: [{ id: "d1", placements: [] }] });
DP.filter.sort = "name";
DP.filter.show = "printed";
DP.printSelected = new Set(["B9"]);
const filtered = DP.filteredBins().map(one => one.id);
const selectedScope = DP.batchScope();
DP.printSelected.clear();
const emptyScope = DP.batchScope();
DL.bins = DL.bins.filter(one => one.id !== "B7");
console.log(JSON.stringify({
  numbers: [DL.binNumberLabel({ id: "B9", kind: "manual" })],
  status: DL.statusLabel({ status: "in_design" }),
  filtered, selectedSubset: selectedScope.subset, selectedSave: selectedScope.save.length,
  emptySubset: emptyScope.subset, showEmptyRetired: !("show_empty" in DL.layout.settings),
}));
'''
        done = subprocess.run([node, "-e", script, str(root / "drawer-model.js"),
                               str(root / "drawer-panel.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out, {"numbers": ["Bin 1"], "status": "In Space", "filtered": ["S1"],
                               "selectedSubset": True, "selectedSave": 0,
                               "emptySubset": False, "showEmptyRetired": True})

    def test_fix067_saved_file_question_waits_for_focus_exit(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        gate = source[source.index("const staleFileRefreshQueue = new Map();"):
                      source.index("function queueSpaceDesignAutosave()")]
        script = r'''
const vm = require("vm"), fs = require("fs");
const code = fs.readFileSync(process.argv[1], "utf8");
const calls = { prompts: [], generated: [] };
let choice = "cancel", switchSpace = false, success = true;
const state = { runtime: { hosted: false }, activeSpaceId: "A", designInventoryId: "B1" };
const DL = { layout: { settings: {} }, folder: () => "folder", bin: id => ({ id, name: "A", file: "" }),
  label: row => row.name, spaceContext: () => ({ output: "folder", spaceId: state.activeSpaceId }),
  spaceContextCurrent: c => c.spaceId === state.activeSpaceId,
  change: fn => fn(), save: async () => true, isStaleSpaceError: () => false };
const appConfirm = async opts => {
  calls.prompts.push(opts.message);
  appConfirm.checked = false;
  if (switchSpace) state.activeSpaceId = "B";
  return choice;
};
const ctx = { state, DL, appConfirm, Map, Set, JSON,
  designerGenerateInventoryRow: async id => { calls.generated.push(id); return success; },
  toast: () => {} };
vm.createContext(ctx);
vm.runInContext(code + ";this.queue=queueStaleFileRefresh;this.settle=settleStaleFileRefresh", ctx);
(async () => {
  ctx.queue({ output: "folder", spaceId: "A" }, "B1", true);
  const before = calls.prompts.length;
  const declinedNavigation = await ctx.settle();
  ctx.queue({ output: "folder", spaceId: "A" }, "B1", true);
  choice = "primary";
  const updated = await ctx.settle();
  ctx.queue({ output: "folder", spaceId: "A" }, "B1", false);
  const beforeOutput = calls.generated.length;
  const outputApproved = await ctx.settle({ materialize: true });
  const afterOutput = calls.generated.length;
  ctx.queue({ output: "folder", spaceId: "A" }, "B1", false);
  switchSpace = true;
  const switched = await ctx.settle();
  console.log(JSON.stringify({ before, declinedNavigation, updated, outputApproved,
    beforeOutput, afterOutput, switched, prompts: calls.prompts,
    generated: calls.generated, space: state.activeSpaceId }));
})();
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gate.js"
            path.write_text(gate, encoding="utf-8")
            done = subprocess.run([node, "-e", script, str(path)], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["before"], 0)
        self.assertTrue(out["declinedNavigation"])
        self.assertTrue(out["updated"])
        self.assertTrue(out["outputApproved"])
        self.assertEqual(out["beforeOutput"], out["afterOutput"])
        self.assertFalse(out["switched"])
        self.assertEqual(out["space"], "B")
        self.assertEqual(out["generated"], ["B1"])
        self.assertIn("was saved and printed", out["prompts"][1])

    def test_fix067_row_open_commits_selection_only_after_success(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        root = Path(__file__).resolve().parent / "web"
        script = r'''
const vm = require("vm"), fs = require("fs");
const calls = { edits: [], opens: [], selected: [], prompts: 0, flushes: 0 };
let editSuccess = true;
const state = { designInventoryId: "B1", design: { box: {} }, cleanDesign: {}, runtime: { hosted: true } };
const rows = ["B1", "B2"].map(id => ({ id, kind: "bin", name: id }));
const DL = { bins: rows, isOrdinary: row => !!row && row.kind !== "spacer",
  bin: id => rows.find(row => row.id === id), placedCount: id => id === "B1" ? 1 : 0,
  spaceContext: () => ({ spaceId: "A" }), spaceContextCurrent: c => c.spaceId === "A",
  editBins: async payload => { calls.edits.push(payload); return true; },
  markPrinted: () => {}, markNotPrinted: () => {}, printCount: () => 1,
  selectRow: id => { calls.selected.push(id); DL.selectedRow = id; }, selectedRow: "B1" };
const ctx = { console, Date, Set, Map, Math, JSON, Number, state, DL,
  localStorage: { getItem: () => null }, $: () => null,
  appConfirmAction: async () => { calls.prompts++; return true; },
  flushSpaceDesignAutosave: async () => { calls.flushes++; return true; },
  designerEditInventoryRow: async id => { calls.opens.push(id); return editSuccess; },
  clearTimeout: () => {}, spaceAutosaveTimer: null,
  clone: value => JSON.parse(JSON.stringify(value)),
  discardStaleFileRefreshRows: () => {},
  toast: () => {}, fmt: value => String(value) };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + ";this.DP=DP", ctx);
const DP = ctx.DP;
DP.renderInventory = () => {};
DP.renderBatch = () => {};
DP.setMode = () => {};
DP.duplicateRow = () => {};
DL.printSelectedBins = () => {};
const event = (id, editable, child = "none") => ({ target: { closest: selector => {
  if (selector === "[data-bin]") return { dataset: { bin: id, editable: String(editable) } };
  if (selector === ".dl-print-select") return child === "checkbox" ? {} : null;
  if (selector === "[data-act]" && ["more", "duplicate", "print", "printed", "not-printed"].includes(child))
    return { dataset: { act: child } };
  if (selector === "button, input, select, a, textarea, .dl-bin-details" &&
      ["field", "link", "checkbox"].includes(child)) return {};
  return null;
} } });
(async () => {
  await DP.onInventoryClick(event("B2", true, false));
  const mouseSuccess = DL.selectedRow;
  DL.selectedRow = "B1"; editSuccess = false;
  await DP.onInventoryClick(event("B2", true, false));
  const mouseFailure = DL.selectedRow;
  editSuccess = true; DL.selectedRow = "B1";
  await DP.openInventoryRow("B2");
  const keyboardSuccess = DL.selectedRow;
  editSuccess = false; DL.selectedRow = "B1";
  await DP.openInventoryRow("B2");
  const keyboardFailure = DL.selectedRow;
  editSuccess = true;
  const opensBeforeChildren = calls.opens.length;
  for (const child of ["checkbox", "more", "duplicate", "print", "printed", "not-printed", "field", "link"])
    await DP.onInventoryClick(event("B2", true, child));
  DP.draggingRow = true;
  await DP.onInventoryClick(event("B2", true, false));
  DP.draggingRow = false;
  const childAndDragOpens = calls.opens.length - opensBeforeChildren;
  DL.selectedRow = "B1"; state.designInventoryId = "B1";
  DP.printSelected = new Set(["B1", "B2"]);
  await DP.deleteSelected();
  console.log(JSON.stringify({ calls, mouseSuccess, mouseFailure, keyboardSuccess, keyboardFailure,
    childAndDragOpens, bound: state.designInventoryId, selection: [...DP.printSelected] }));
})();
'''
        done = subprocess.run([node, "-e", script, str(root / "drawer-panel.js")],
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual(out["mouseSuccess"], "B2")
        self.assertEqual(out["mouseFailure"], "B1")
        self.assertEqual(out["keyboardSuccess"], "B2")
        self.assertEqual(out["keyboardFailure"], "B1")
        self.assertEqual(out["childAndDragOpens"], 0)
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        keyboard = panel[panel.index('list.addEventListener("keydown"'):panel.index('list.addEventListener("dragstart"')]
        self.assertIn("DP.openInventoryRow(row.dataset.bin)", keyboard)
        self.assertEqual(out["calls"]["edits"], [{"delete_ids": ["B1", "B2"]}])
        self.assertEqual(out["calls"]["prompts"], 1)
        self.assertEqual(out["calls"]["flushes"], 1)
        self.assertIsNone(out["bound"])
        self.assertEqual(out["selection"], [])

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

    def test_print_payload_sends_bundle_for_ordinary_bin_and_ignores_join_mode(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.touch()
            fake_gen_result = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }
            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake_gen_result),
                patch.object(wavefinity_web, "connector_payload", return_value={"result": {}, "output": str(temp_dir)}) as mock_connector,
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                patch.object(wavefinity_web, "launch_slicer"),
            ):
                # A leftover/garbage join_mode value must be silently ignored -
                # it is no longer read or validated anywhere in this path.
                wavefinity_web.print_payload({
                    "design": default_design(),
                    "output": temp_dir,
                    "target": "all",
                    "join_mode": "base_trim",
                })
                mock_connector.assert_called_once()

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

    def test_print_payload_skips_connector_bundle_for_b4b_lid_and_base_trim(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_exe = Path(temp_dir) / "bambu-studio.exe"
            fake_exe.touch()
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.touch()
            fake_gen_result = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }

            b4b_design = default_design()
            b4b_design["box"]["b4b"] = {"enabled": True}
            lid_design = default_design()
            lid_design["box"]["lid"] = {"enabled": True}
            base_trim_design = {"design_kind": "base_trim"}

            for design in (b4b_design, lid_design, base_trim_design):
                with self.subTest(design=design.get("design_kind", "bin")):
                    with (
                        patch.object(wavefinity_web, "generate_payload", return_value=fake_gen_result),
                        patch.object(wavefinity_web, "connector_payload") as mock_connector,
                        patch.object(wavefinity_web, "detect_bambu_studio", return_value=fake_exe),
                        patch.object(wavefinity_web, "launch_slicer"),
                        patch.object(wavefinity_web, "inventory_enabled", return_value=False),
                    ):
                        # target "all" is connector-inclusive Print's real
                        # request; only the b4b/lid/base-trim exclusion below
                        # should keep connector_payload from being called.
                        wavefinity_web.print_payload({"design": design, "output": temp_dir, "target": "all"})
                        mock_connector.assert_not_called()

    def _node_or_skip(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for this browser-state regression")
        return node

    def test_current_design_shadow_helpers_are_gone(self):
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("WORKING_DESIGN_HELPERS", source)
        for name in ("workingDesignForSpace", "markWorkingDesignPending", "markWorkingDesignReconciled",
                     "workingPending", "workingGeneratedKey"):
            self.assertNotIn(name, source)

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

    def test_removed_inside_handles_stay_removed_after_form_read(self):
        code = self._app_js_functions("readLiftGrabberForm", "syncLiftGrabberControls")

        def script(resync_value):
            return "\n".join([
                "const LIFT_GRABBER_DEFAULTS = { enabled: false, size: 'medium', location: 'sides' };",
                "const els = { '#lift-grabber-size': { value: 'large' },"
                " '#lift-grabber-location': { value: 'sides' },"
                " '#lift-grabber-location-setting': { hidden: false } };",
                "const $ = sel => els[sel];",
                code,
                "const design = { box: { lift_grabbers: { enabled: false, size: 'medium', location: 'sides' } } };",
                f"els['#lift-grabber-size'].value = {resync_value};",
                "syncLiftGrabberControls();",
                "readLiftGrabberForm(design);",
                "process.stdout.write(JSON.stringify(design.box.lift_grabbers.enabled));",
            ])

        # What syncForm() does for this control after a delete: 'no'.
        self.assertFalse(self._run_node(script("'no'")))
        # Without the resync the stale 'large' value would resurrect handles.
        self.assertTrue(self._run_node(script("'large'")))

    def test_removed_side_openings_stay_removed_after_form_read(self):
        code = self._app_js_functions(
            "sideOpeningState", "sideOpeningPartActive", "readSideOpeningForm", "syncSideOpeningControls",
        )
        script = "\n".join([
            "const SIDE_OPENING_DEFAULTS = { enabled: false, shape: 'curved', sides: [], size: 'medium',"
            " from_bottom_percent: 100, from_top_percent: 100 };",
            "const SIDE_OPENING_SIDE_IDS = ['front', 'back', 'left', 'right'];",
            "const els = { '#side-openings-panel': { hidden: false }, '#side-opening-shape': { value: 'square' },"
            " '#side-opening-from-bottom': { value: '60' }, '#side-opening-from-top': { value: '90' },"
            " '#side-opening-size': { value: 'small', options: [] } };",
            "for (const side of SIDE_OPENING_SIDE_IDS) {"
            " const attrs = { 'aria-pressed': side === 'front' ? 'true' : 'false' };"
            " els['#side-opening-' + side] = { disabled: false,"
            "  getAttribute: k => attrs[k], setAttribute: (k, v) => { attrs[k] = v; },"
            "  classList: { toggle() {} } }; }",
            "const $ = sel => els[sel];",
            "const state = { design: { box: { side_openings: { ...SIDE_OPENING_DEFAULTS } } } };",
            "const b4bEnabled = () => false, baseTrimEnabled = () => false;",
            "const sideOpeningLidStackForced = () => false, clampSideOpeningTopForLid = () => {};",
            "const sideOpeningEligibleSide = () => true, sideOpeningAllowedSizes = () => [];",
            "const sideOpeningAdjustmentNote = '', fmt = v => String(v), flashField = () => {};",
            "const number = (v, f) => (Number.isFinite(Number(v)) ? Number(v) : f);",
            code,
            "syncSideOpeningControls();",
            "const design = JSON.parse(JSON.stringify(state.design)); readSideOpeningForm(design);",
            "process.stdout.write(JSON.stringify([els['#side-openings-panel'].hidden,"
            " els['#side-opening-front'].getAttribute('aria-pressed'), design.box.side_openings.enabled]));",
        ])
        self.assertEqual(self._run_node(script), [True, "false", False])

    def test_square_bore_pitch_matches_backend_profiles(self):
        code = self._app_js_functions("boreCrossPitch")
        script = "\n".join([
            code,
            "process.stdout.write(JSON.stringify(['square_axis', 'square', 'hex', 'round']"
            ".map(p => boreCrossPitch(p, 6.25, 1.6))));",
        ])
        axis, square, hexagon, rnd = self._run_node(script)
        held, wall = 6.25, 1.6
        self.assertAlmostEqual(axis, held + wall)
        self.assertAlmostEqual(square, held / math.cos(math.pi / 4) + wall)
        self.assertAlmostEqual(hexagon, held / math.cos(math.pi / 6) + wall)
        self.assertAlmostEqual(rnd, held + wall, places=1)

    def test_surface_outside_size_resolves_down_to_whole_units(self):
        node = self._node_or_skip()
        source = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        code = source[source.index("SP.surfacePresetRows = "):source.index("// Show the resolved finished size")]
        rules = {key: catalog_payload()["base_trim_rules"][key] for key in
                 ("unit_mm", "mating_gap_mm", "max_field_mm", "size_presets")}
        script = "\n".join([
            "const SP = {}; const fmt = v => String(Math.round(v * 100) / 100);",
            "const state = { catalog: { base_unit: 8, base_trim_rules: " + json.dumps(rules) + " } };",
            code,
            "const r = (x, y, t) => SP.resolveSurface(x, y, t);",
            "process.stdout.write(JSON.stringify([r(300, 250, 'medium'), r(295.25, 247.25, 'medium'),"
            " r(295.24, 247.25, 'medium'), r(10, 10, 'medium'), r(5000, 250, 'medium')]));",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        first, exact, just_under, tiny, huge = json.loads(done.stdout)
        self.assertEqual((first["fieldX"], first["fieldY"]), (280, 232))
        self.assertEqual((first["outerX"], first["outerY"]), (295.25, 247.25))
        self.assertEqual(exact["fieldX"], 280)
        self.assertEqual(just_under["fieldX"], 272)   # never rounds up
        self.assertFalse(tiny["ok"])
        self.assertFalse(huge["ok"])

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
        self.assertIn('DP.setMode("design")', first[:first.index("};")])
        self.assertNotIn("markWorking", first[:first.index("};")])
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

    def test_space_workspace_separates_editor_mode_from_preview(self):
        # Fix 024: preview and editor choices are synchronized without a
        # second state machine.
        root = Path(__file__).resolve().parent / "web"
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        index_html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-space-mode="space"', index_html)
        self.assertIn('data-space-mode="design"', index_html)
        observer = panel[panel.index("new MutationObserver"):]
        observer = observer[:observer.index("attributeFilter")]
        self.assertIn('DP.enter("space")', observer)
        self.assertNotIn("DP.leave()", observer)
        self.assertNotIn("DP.mode =", observer)
        enter = panel[panel.index("DP.enter = "):panel.index("DP.leave = ")]
        self.assertIn('preferredMode === "design" ? "design" : "space"', enter)
        self.assertNotIn("workingDesignForSpace", enter)
        setter = panel[panel.index("DP.setMode = "):panel.index("DP.selectMode = ")]
        self.assertNotIn("activatePreviewView", setter)
        app = (root / "app.js").read_text(encoding="utf-8")
        preview = app[app.index("function activatePreviewView(view)"):app.index("\nfunction wireControls", app.index("function activatePreviewView(view)"))]
        self.assertIn('view === "2d" || view === "3d"', preview)
        self.assertIn('DP.setMode("design")', preview)
        self.assertIn('DP.enter("space")', preview)
        self.assertIn('DP.setMode("space")', preview)
        self.assertIn('role="tablist"', index_html)
        mode_toggle = index_html[index_html.index('id="space-mode-toggle"'):index_html.index("</div>", index_html.index('id="space-mode-toggle"'))]
        self.assertEqual(mode_toggle.count('role="tab"'), 2)
        self.assertIn("aria-selected", index_html)
        apply_mode = panel[panel.index("DP.applyMode = "):panel.index("DP.setMode = ")]
        self.assertIn('setAttribute("aria-selected", String(on))', apply_mode)
        self.assertIn("button.tabIndex = on ? 0 : -1", apply_mode)
        select_mode = panel[panel.index("DP.selectMode = "):panel.index("// Open the Space workspace")]
        self.assertIn('activatePreviewView("drawer")', select_mode)
        self.assertIn('activatePreviewView("3d")', select_mode)

    def test_space_settings_lost_their_user_choices(self):
        root = Path(__file__).resolve().parent / "web"
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        for gone in ("Snap to", "Grid sits", "Width direction", "Fit clearance",
                     "dl-snap", "dl-anchor", "dl-axis", "dl-clearance",
                     "Spacers &amp; connectors", "dl-connectors", "Drawer settings"):
            self.assertNotIn(gone, panel)
        self.assertIn("<summary>Spacers</summary>", panel)
        self.assertIn("Drawer details", panel)
        self.assertNotIn("Advanced Settings", panel)

    def test_existing_space_edit_is_inline_with_edit_only_buttons(self):
        root = Path(__file__).resolve().parent / "web"
        spaces = (root / "spaces.js").read_text(encoding="utf-8")
        index_html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="space-save-changes"', index_html)
        self.assertIn('id="space-cancel-edit"', index_html)
        self.assertNotIn('id="space-info-block"', index_html)
        mode = spaces[spaces.index("SP.setFormMode = "):]
        mode = mode[:mode.index("};")]
        self.assertIn('$("#space-back").hidden = edit;', mode)
        self.assertIn('$("#space-create").hidden = edit;', mode)
        self.assertIn('$("#space-save-changes").hidden = !edit;', mode)
        setup = spaces[spaces.index("SP.showSetup = "):]
        setup = setup[:setup.index("SP.startUntyped")]
        self.assertIn("SP.mountInlineEdit()", setup)

    def test_legacy_layout_settings_normalise_to_the_canonical_rules(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        model = Path(__file__).resolve().parent / "web" / "drawer-model.js"
        script = """
const vm = require("vm"), fs = require("fs");
const ctx = { debounce: f => f, state: { activeSpaceId: "A", output: "" }, console, Math, JSON, Number, Set, Map,
  clone: value => JSON.parse(JSON.stringify(value)), drawerHardClearance: () => 0.6, fmt: value => String(value) };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8") + " ;this.DL = DL;", ctx);
const DL = ctx.DL;
const layout = DL.normaliseLayout({ active: "d1", settings: { autosave: false }, drawers: [
  { id: "d1", width: 400, depth: 300, height: 60, snap: 4, anchor: "center", bin_axis: "y", clearance: 5,
    placements: [{ bin: "b1", gx: 1.5, gy: 3 }, { bin: "b2", x: 1, y: 2, w: 3, d: 4 }] },
  { id: "d2", width: 100, depth: 100, height: 60, boundary: "mating", clearance: 1, placements: [] },
] });
console.log(JSON.stringify({ layout, grid: DL.grid(layout.drawers[0]), cells: DL.cells({ x: 20, y: 40 }, layout.drawers[0]) }));
"""
        result = subprocess.run([node, "-e", script, str(model)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        legacy, mating = out["layout"]["drawers"]
        self.assertEqual((legacy["snap"], legacy["anchor"], legacy["bin_axis"], legacy["clearance"]), (8, "front-left", "x", 0.6))
        self.assertEqual((legacy["placements"][0]["gx"], legacy["placements"][0]["gy"]), (2, 3))
        self.assertNotIn("gx", legacy["placements"][1])
        self.assertEqual(mating["clearance"], 0)
        self.assertEqual(out["grid"]["step"], 8)
        self.assertEqual(out["cells"], [3, 5])
        # Fix 034 K1: autosave has no off state - a legacy autosave:false
        # layout normalises to the always-on runtime value.
        self.assertTrue(out["layout"]["settings"]["autosave"])

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

    def test_connector_choosers_are_removed_from_browser_source(self):
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        spaces_js = (root / "web" / "spaces.js").read_text(encoding="utf-8")
        self.assertNotIn("bin-join-mode", index_html)
        self.assertNotIn("connector-type", index_html)
        self.assertNotIn("corner-connector-quantity", index_html)
        for source in (app_js, spaces_js):
            self.assertNotIn("joinMode", source)
            self.assertNotIn("join_mode", source)
            self.assertNotIn("default_join_mode", source)

    def test_hosted_connector_bundle_exposes_all_files_without_duplicate_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            side_file = Path(temp_dir) / "side.3mf"
            side_file.touch()
            three_file = Path(temp_dir) / "three.3mf"
            three_file.touch()
            four_file = Path(temp_dir) / "four.3mf"
            four_file.touch()
            with (
                patch.object(wavefinity_web, "HOSTED", True),
                patch.object(wavefinity_web, "_generation_output", return_value=Path(temp_dir)),
                patch.object(wavefinity_web, "generate_side_file", return_value={"output": str(side_file)}),
                patch.object(wavefinity_web, "generate_corner_file", side_effect=[
                    {"output": str(three_file)}, {"output": str(four_file)},
                ]),
            ):
                result = wavefinity_web.connector_payload({"design": default_design()})
        names = {entry["name"] for entry in result["files"]}
        self.assertEqual(names, {"side.3mf", "three.3mf", "four.3mf"})
        self.assertEqual(len(result["files"]), 3)

    def test_no_pseudo_folder_remains_in_web_code(self):
        # Fix 009: a hosted persistent-folder action must never fabricate a
        # handle-less "folder" that quietly turns Space writes into downloads.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        spaces_js = (root / "web" / "spaces.js").read_text(encoding="utf-8")
        self.assertNotIn("Browser downloads", app_js)
        self.assertNotIn("Browser downloads", spaces_js)
        self.assertNotIn("fallback: true", app_js)
        self.assertNotIn("fallback: true", spaces_js)

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

    def test_divider_scoop_editor_applies_to_every_compartment(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles_css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        # Flat/Sloped/Curved-scoop bottom is one unified "Bottom" dropdown
        # now, not a separate Slope base checkbox plus a separate
        # scoop-enabled checkbox.
        self.assertIn('data-draft="option:bottom_mode"', app_js)
        self.assertIn(">Flat</option>", app_js)
        self.assertIn(">Sloped</option>", app_js)
        self.assertIn(">Curved scoop</option>", app_js)
        self.assertIn('dataAttribute: "data-divider-scoop-depth"', app_js)
        self.assertIn('plainCheckbox("option:label_divisions", "Label divisions"', app_js)
        self.assertNotIn("Slot bottoms", app_js)
        self.assertNotIn("Compartment scoops", app_js)
        # Fix 061 F1.6: the label controls are now one visible "Division labels"
        # group, owner checkbox first - not the old separate scoop/label grid.
        self.assertIn('editor-group-label">Division labels<', app_js)
        self.assertNotIn("data-divider-scoop-cell", app_js)
        self.assertNotIn("data-divider-scoop-all", app_js)
        self.assertNotIn("data-divider-scoop-none", app_js)
        self.assertNotIn("data-divider-scoop-enabled", app_js)
        self.assertNotIn("divider-scoop-grid", styles_css)
        self.assertIn('one.options.slope_base = true;', app_js)
        self.assertIn('delete one.options.scoop;', app_js)
        self.assertIn('"bottom_supports", "scoop"]) delete one.options[key];', app_js)
        self.assertIn('textPlacementFields(', app_js)
        self.assertIn('>On base</option>', app_js)
        self.assertIn('>Rim level</option>', app_js)
        self.assertIn('>Rim shelf<select', app_js)
        self.assertNotIn('name="draft-division-side"', app_js)
        self.assertIn("divider-slope-toggles", styles_css)
        self.assertIn('divider_slope: "#1f6b45"', app_js)
        self.assertNotIn('changed === "option:bottom_angle" ||', app_js)

    def test_auto_layout_candidate_cards_are_removed(self):
        root = Path(__file__).resolve().parent
        drawer_panel_js = (root / "web" / "drawer-panel.js").read_text(encoding="utf-8")
        self.assertNotIn("data-candidate", drawer_panel_js)
        self.assertNotIn("stats.placed", drawer_panel_js)
        self.assertNotIn("drawThumb", drawer_panel_js)

    def test_feature_icons_are_separate_and_loaded_before_the_app(self):
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        icons_js = (root / "web" / "feature-icons.js").read_text(encoding="utf-8")
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn("WavefinityFeatureIcons", icons_js)
        self.assertNotIn('divider: \'<rect x="4"', app_js)
        self.assertLess(index_html.index("/feature-icons.js"), index_html.index("/app.js"))

    def test_3d_preview_has_ordinary_and_b4b_mode_controls_and_a_gl_renderer(self):
        # fix3d.md: B4B gets its own All/Base/Lid group instead of Standard/
        # Xray/Bin/Interior, the two groups never share a name, and the
        # shared WebGL renderer loads before app.js can reference it.
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        gl_js = (root / "web" / "preview3d-webgl.js").read_text(encoding="utf-8")
        self.assertIn('id="ordinary-preview-modes"', index_html)
        # The Designer only holds ordinary bins now: no Storage Box All/Base/Lid group.
        self.assertNotIn('id="b4b-preview-modes"', index_html)
        # The four mutually-exclusive camera modes were replaced by three
        # independently toggleable Bin/Interior/Xray buttons - there is no
        # separate "standard" mode any more.
        for mode in ("bin", "interior", "xray"):
            self.assertIn(f'data-camera-toggle="{mode}"', index_html)
        for view in ("all", "base", "lid"):
            self.assertNotIn(f'data-b4b-view="{view}"', index_html)
        self.assertLess(
            index_html.index("/preview3d-webgl.js"), index_html.index("/app.js")
        )
        self.assertIn("window.Preview3DGL", gl_js)
        self.assertIn("Preview3DGL.init", app_js)
        self.assertIn("drawGeometryLegacy2D", app_js)

    def test_compact_support_choice_cards_and_zoomed_icon_viewbox(self):
        # Fix 010 Part A: the normal Interior Parts / Parts & options choice
        # cards are ~30% shorter (48px -> 34px) without shrinking the 34x34
        # SVG artwork, and the icon viewBox is tightened so the glyph fills
        # more of the icon tile.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        styles_css = (root / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("min-height: 34px; max-height: 34px", styles_css)
        self.assertNotIn("min-height: 48px; max-height: 48px", styles_css)
        self.assertIn("width: 34px; height: 34px", styles_css)
        self.assertIn('viewBox="2 2 28 28"', app_js)
        self.assertNotIn('viewBox="0 0 32 32"', app_js)

    def test_new_space_replaces_new_drawer_space_and_routes_through_type_cards(self):
        # Fix 010 Parts B & C: "New Drawer Space" is renamed to "New Space"
        # everywhere and always returns to the three-image type chooser
        # instead of jumping straight into Drawer setup, carrying dimensions
        # forward only for a same-type repeat.
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        drawer_panel_js = (root / "web" / "drawer-panel.js").read_text(encoding="utf-8")
        spaces_js = (root / "web" / "spaces.js").read_text(encoding="utf-8")

        self.assertIn("New Space</button>", index_html)
        self.assertIn('id="space-head-new-space"', index_html)
        self.assertNotIn("New Drawer Space", index_html)

        self.assertNotIn("New Drawer Space", drawer_panel_js)

        self.assertNotIn("New Drawer Space", spaces_js)
        self.assertNotIn("SP.newDrawerSpace", spaces_js)
        self.assertIn("SP.newSpace = () => {", spaces_js)
        self.assertIn("SP.showTypeCards();", spaces_js)
        self.assertNotIn('SP.showSetup("drawer", state.activeSpace)', spaces_js)

        # The template clears the name and is only ever offered to its own
        # matching type card - the existing prefill guard stays in place.
        self.assertIn('template.name = "";', spaces_js)
        self.assertIn(
            "const candidateKind =\n"
            "            candidate?.kind === \"box\" ? \"portable\" : candidate?.kind;",
            spaces_js,
        )
        self.assertIn("SP.showSetup(kind, candidateKind === kind ? candidate : null);", spaces_js)

        # New Space is offered for every typed Space, not only Drawer.
        self.assertIn(
            'const btnNew = document.getElementById("space-head-new-space");\n    if (btnNew) btnNew.hidden = false;',
            spaces_js,
        )

    # ------------------------------------------------------------ Fix 019

    def test_space_activation_resets_design_session_state(self):
        # Item 1/5: one authoritative activation path resets every session-
        # only Current-design/editor/Surface-first-run flag before installing
        # the new Space's starter design - and applyFolder always routes a
        # typed-Space activation through it.
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        reset = spaces_js[spaces_js.index("SP.resetDesignSession = () => {"):]
        reset = reset[:reset.index("\n};\n")]
        for flag in (
            "state.designInventoryId = null", "state.spaceStarterPreviewPending = false",
            "state.lastOrdinaryDesign = null",
            "state.drafts = {}", "state.history = []", "state.future = []",
            "resetNestPhotoSession()", "clearDraftSelection()",
        ):
            self.assertIn(flag, reset)
        for retired in ("workingPending", "workingGeneratedKey", "surfaceEdgeHandled",
                        "baseTrimSourceLayout", "lastBaseTrimDesign"):
            self.assertNotIn(retired, reset)

        init = spaces_js[spaces_js.index("SP.initializeDesignForActiveSpace = async () => {"):]
        init = init[:init.index("\n};\n")]
        self.assertIn("SP.resetDesignSession();", init)
        self.assertIn("SP.installSpaceStarterDesign();", init)
        # Opening/switching alone must never mark the starter as pending.
        self.assertNotIn("markWorkingDesignPending", init)

        apply_folder = spaces_js[spaces_js.index("SP.applyFolder = async"):]
        apply_folder = apply_folder[:apply_folder.index("\n};\n")]
        self.assertIn(
            'if (initDesign && info.folder_mode === "space") await SP.initializeDesignForActiveSpace();',
            apply_folder,
        )

    def test_starter_design_matches_space_kind(self):
        # The Designer always starts an ordinary Bin, whatever the Space type:
        # a Storage Box or Base Trim is a structural output of its Space.
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        installer = spaces_js[spaces_js.index("SP.installSpaceStarterDesign = async"):]
        installer = installer[:installer.index("\n};\n")]
        self.assertIn("state.design = freshDesignForCurrentFolder();", installer)
        self.assertNotIn("makeBaseTrimDesign", installer)
        self.assertNotIn("toggleB4B", installer)
        self.assertNotIn("b4b", installer)

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

    def test_initialize_design_for_active_space_resumes_before_starter_fallback(self):
        # Fix 032: opening a typed Space must restore its exact saved design
        # before ever falling back to SP.installSpaceStarterDesign() - and a
        # restore must bypass the starter/sizing path entirely.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        init_fn = self._spaces_slice(spaces_js, "SP.initializeDesignForActiveSpace = async () => {")

        script = "\n".join([
            "const clone = v => JSON.parse(JSON.stringify(v));",
            "async function run(scenario) {",
            "  const calls = [];",
            "  const toasts = [];",
            "  const toast = msg => toasts.push(msg);",
            "  const state = {",
            "    folderMode: scenario.folderMode ?? 'space',",
            "    activeSpace: scenario.activeSpace ?? { kind: 'drawer', name: 'S' },",
            "    catalog: scenario.noCatalog ? null : {},",
            "    spaceResumeDesign: scenario.resumeDesign ?? null,",
            "    spaceResumePending: scenario.resumePending ?? false,",
            "    design: null, cleanDesign: null,",
            "  };",
            "  const api = async (path, payload) => {",
            "    calls.push(['api', path, clone(payload)]);",
            "    if (scenario.validateFails) throw new Error('schema rejected');",
            "    return { design: { ...clone(payload.design), validated: true } };",
            "  };",
            "  const SP = {",
            "    resetDesignSession: () => calls.push(['resetDesignSession']),",
            "    installSpaceStarterDesign: async space => calls.push(['installSpaceStarterDesign', space]),",
            "  };",
            "  const bindLidMemoryForDesign = () => calls.push(['bindLidMemoryForDesign']);",
            "  const syncForm = () => calls.push(['syncForm']);",
            init_fn,
            "  await SP.initializeDesignForActiveSpace();",
            "  return { calls, toasts, design: state.design, cleanDesign: state.cleanDesign };",
            "}",
            "(async () => {",
            "  const out = {};",
            "  out.noResume = await run({});",
            "  out.withValidResume = await run({ resumeDesign: { box: { x: 1 } }, resumePending: true });",
            "  out.withReconciledResume = await run({ resumeDesign: { box: { x: 2 } }, resumePending: false });",
            "  out.invalidResumeFallsBack = await run({ resumeDesign: { box: { x: 1 } }, resumePending: true, validateFails: true });",
            "  out.notASpace = await run({ folderMode: 'design' });",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        no_resume = out["noResume"]
        self.assertIn(["resetDesignSession"], no_resume["calls"])
        self.assertTrue(any(c[0] == "installSpaceStarterDesign" for c in no_resume["calls"]))
        self.assertIn(["syncForm"], no_resume["calls"])
        self.assertEqual(no_resume["toasts"], [])

        with_resume = out["withValidResume"]
        self.assertTrue(any(c[0] == "api" and c[1] == "/api/design/validate" for c in with_resume["calls"]))
        self.assertFalse(any(c[0] == "installSpaceStarterDesign" for c in with_resume["calls"]))
        self.assertEqual(with_resume["design"], {"box": {"x": 1}, "validated": True})
        self.assertEqual(with_resume["cleanDesign"], with_resume["design"])

        # A resume checkpoint is recovery only: it restores the same exact design.
        reconciled = out["withReconciledResume"]
        self.assertFalse(any(c[0] == "installSpaceStarterDesign" for c in reconciled["calls"]))
        self.assertEqual(reconciled["design"], {"box": {"x": 2}, "validated": True})

        fallback = out["invalidResumeFallsBack"]
        self.assertTrue(any(c[0] == "installSpaceStarterDesign" for c in fallback["calls"]))
        self.assertEqual(len(fallback["toasts"]), 1)

        not_space = out["notASpace"]
        self.assertEqual(not_space["calls"], [])

    def test_hosted_write_metadata_serializes_resume_against_other_writes(self):
        # Fix 032 Correction 1, item 4: hosted SP.writeMetadata() must
        # serialize its read/preserve/write transactions - a resume save and
        # a defaults/rename update racing the same slow read must not both
        # read the old file and then overwrite each other's fields.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")

        start = "SP._metadataWriteQueue = Promise.resolve();"
        end = "  return metadata;\n};"
        write_module = spaces_js[spaces_js.index(start):]
        write_module = write_module[:write_module.index(end) + len(end)]

        script = "\n".join([
            "const FOLDER_METADATA = '.wavefinity.json';",
            "const FOLDER_METADATA_VERSION = 8;",
            "const SPACE_SETUP_VERSION = 1;",
            "let fileText = JSON.stringify({",
            "  version: 8, setup_version: 1, folder_mode: 'space',",
            "  space_id: 'sid', space: { kind: 'drawer', name: 'S', x: 320, y: 240, z: 55 },",
            "  keep_bin_defaults: true, bin_defaults: null, part_defaults: {},",
            "  resume_design: { box: { x: 1 } }, resume_pending: true,",
            "});",
            "const writeCalls = [];",
            "const WFFileSystem = {",
            "  writeText: async (handle, name, text) => { writeCalls.push(text); fileText = text; },",
            "};",
            "const crypto = { randomUUID: () => 'unused' };",
            "const SP = {",
            "  readMetadata: async () => {",
            "    // The slow read: both callers see the SAME pre-write snapshot if",
            "    // they are not serialized against each other.",
            "    await new Promise(r => setTimeout(r, 20));",
            "    return { current: { exists: true, data: JSON.parse(fileText) } };",
            "  },",
            "  classifyMetadata: record => {",
            "    const d = record.data;",
            "    return {",
            "      status: 'space', space_id: d.space_id,",
            "      keep_bin_defaults: d.keep_bin_defaults, bin_defaults: d.bin_defaults,",
            "      part_defaults: d.part_defaults, resume_design: d.resume_design, resume_pending: d.resume_pending,",
            "    };",
            "  },",
            "  metadataError: () => new Error('bad metadata'),",
            "};",
            write_module,
            "(async () => {",
            "  const space = { kind: 'drawer', name: 'Renamed', x: 320, y: 240, z: 55 };",
            "  const [resumeResult, renameResult] = await Promise.all([",
            "    SP.writeMetadata('handle', 'space', space, true, { resume_design: { box: { x: 2 } }, resume_pending: false }),",
            "    SP.writeMetadata('handle', 'space', space, true, { keep_bin_defaults: false }),",
            "  ]);",
            "  const finalMetadata = JSON.parse(fileText);",
            "  process.stdout.write(JSON.stringify({ writeCount: writeCalls.length, resumeResult, renameResult, finalMetadata }));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        # Two serialized writes, not two concurrent ones stepping on each other.
        self.assertEqual(out["writeCount"], 2)
        final = out["finalMetadata"]
        # Whichever write landed last, it must carry BOTH the resume change
        # from one call AND the keep_bin_defaults change from the other -
        # each write reads the other's already-applied result, not a stale
        # shared snapshot.
        self.assertFalse(final["keep_bin_defaults"])
        self.assertEqual(final["resume_design"], {"box": {"x": 2}})
        self.assertFalse(final["resume_pending"])

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

    def test_generate_and_print_flush_semantics_match_correction_1_contract(self):
        # Fix 032 Correction 1, item 2: the pre-operation flush must gate the
        # actual network call (throwing stops Generate/Print before it sends
        # anything), while the post-success flush must not turn a successful
        # generate/print into a reported failure merely because the
        # checkpoint save failed. These are structural, not behavioral,
        # checks - full DOM execution of generateParts()/printModel() is not
        # practical to harness here, and the ordering/throw-vs-report shape
        # is what Correction 1 specifically required.
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")

        def slice_fn(name):
            start = app_js.index(f"async function {name}(")
            end = app_js.index("\nasync function ", start + 1)
            return app_js[start:end]

        generate_parts = slice_fn("generateParts")
        print_model = slice_fn("printModel")

        for label, source in (("generateParts", generate_parts), ("printModel", print_model)):
            pre_flush_idx = source.index("SP.flushResumeCheckpoint(payload.design, false)")
            api_call = 'api("/api/generate"' if label == "generateParts" else 'api("/api/print"'
            api_idx = source.index(api_call)
            self.assertLess(
                pre_flush_idx, api_idx,
                f"{label}: the pre-operation checkpoint flush must happen before {api_call} is called",
            )
            # The pre-operation flush's own catch must throw (stop the
            # operation), not merely toast.
            pre_flush_catch = source[pre_flush_idx:source.index("catch (error)", pre_flush_idx) + 400]
            self.assertIn("throw new Error", pre_flush_catch)

            # The post-success flush (pending=false) must NOT stop/refuse the
            # already-produced output on a checkpoint-save failure.
            post_flush_idx = source.rindex("SP.flushResumeCheckpoint(payload.design, false)")
            self.assertGreater(post_flush_idx, pre_flush_idx)
            post_flush_catch = source[post_flush_idx:source.index("catch (error)", post_flush_idx) + 400]
            self.assertNotIn("throw", post_flush_catch)

    def test_refresh_preview_only_queues_checkpoint_on_a_fully_valid_preview(self):
        # Fix 032 Correction 1, item 4: an HTTP-200 preview that still
        # reports fit/feature/draft errors must not replace the last valid
        # resume checkpoint.
        app_js = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = app_js.index("async function refreshPreview(")
        end = app_js.index("\nasync function ", start + 1)
        source = app_js[start:end]

        previews_has_errors_idx = source.index("const previewHasErrors =")
        queue_idx = source.index("SP.queueResumeCheckpoint(")
        self.assertLess(previews_has_errors_idx, queue_idx)
        guard = source[previews_has_errors_idx:queue_idx]
        self.assertIn("if (!previewHasErrors", guard)
        self.assertIn('state.folderMode === "space"', guard)

    def test_space_name_heading_is_materially_larger_than_prior_hierarchy(self):
        # Fix 032 item 8: the Space name is the strongest heading in the left
        # panel - the prior hierarchy had it at 16px, level with everything
        # else. Type/size stay secondary (unchanged, small/muted).
        css = (Path(__file__).resolve().parent / "web" / "drawer.css").read_text(encoding="utf-8")
        match = re.search(r"\.space-head-title strong\s*,\s*\.space-head-type\s*\{([^}]*)\}", css)
        self.assertIsNotNone(match, "expected a .space-head-title strong rule in drawer.css")
        size_match = re.search(r"font-size:\s*(\d+(?:\.\d+)?)px", match.group(1))
        self.assertIsNotNone(size_match)
        self.assertGreater(float(size_match.group(1)), 16)

    def test_local_folder_switch_preflight_blocks_backend_mutation_on_cancel(self):
        # Fix 019 correction C1.2: the local (non-hosted) Save/Discard/
        # Cancel preflight must resolve BEFORE the backend's active-folder
        # mutation, not after - a Cancel must mean the mutating endpoint is
        # never called at all. Covers SP.afterPick(), SP.useUntypedFolder()
        # and SP.create() (create and migrate/configure).
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")

        after_pick = self._spaces_slice(spaces_js, "SP.afterPick = async folder => {")
        use_untyped = self._spaces_slice(spaces_js, "SP.useUntypedFolder = async () => {")
        create = self._spaces_slice(spaces_js, "SP.create = async () => {")

        script = "\n".join([
            "const calls = [];",
            "let leaveOk = false; // simulate Cancel",
            "const state = { runtime: { hosted: false } };",
            "const SP = {",
            "  isUpdate: false,",
            "  configureData: null,",
            "  readSetupValues: () => ({ kind: 'drawer', name: 'N', x: 1, y: 1, z: 1, trimSize: null }),",
            "  pickFolder: async () => 'the-folder',",
            "  leaveDrawerLayoutSafely: async () => leaveOk,",
            "  resetDrawer: async () => { calls.push('resetDrawer'); return true; },",
            "  applyFolder: async () => { calls.push('applyFolder'); return true; },",
            "  close: () => { calls.push('close'); },",
            "  enterSetupFor: () => { calls.push('enterSetupFor'); },",
            "  designPortable: async () => { calls.push('designPortable'); },",
            "  designSurface: async () => { calls.push('designSurface'); },",
            "};",
            "const toast = () => {};",
            "function loadFreshOrdinaryDesignForCurrentFolder() { calls.push('loadFreshOrdinaryDesignForCurrentFolder'); }",
            "const api = async (path, body) => {",
            "  calls.push(path);",
            "  if (path === '/api/space/inspect') return { folder: { needs_setup: false, folder_mode: 'none', exists: false } };",
            "  if (path === '/api/folder/use') return { folder: { folder_mode: 'design', folder_name: 'N' }, recent: [] };",
            "  if (path === '/api/space/use-untyped') return { folder: { folder_mode: 'design', folder_name: 'N' }, recent: [] };",
            "  if (path === '/api/space/create') return { folder: { folder_mode: 'space', folder_name: 'N', space: {} }, recent: [] };",
            "  return {};",
            "};",
            after_pick,
            use_untyped,
            create,
            "(async () => {",
            "  const out = {};",
            "",
            "  leaveOk = false;",
            "  calls.length = 0;",
            "  await SP.afterPick('the-folder');",
            "  out.afterPickCancel = calls.slice();",
            "",
            "  leaveOk = false;",
            "  calls.length = 0;",
            "  SP.configureData = 'the-folder';",
            "  await SP.useUntypedFolder();",
            "  out.useUntypedCancel = calls.slice();",
            "",
            "  leaveOk = false;",
            "  calls.length = 0;",
            "  SP.configureData = null;",
            "  await SP.create();",
            "  out.createCancel = calls.slice();",
            "",
            "  // Sanity: with leaveOk = true the mutating endpoints DO run, so the",
            "  // above really is the preflight blocking them, not a broken stub.",
            "  leaveOk = true;",
            "  calls.length = 0;",
            "  await SP.afterPick('the-folder');",
            "  out.afterPickAllowed = calls.slice();",
            "",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        # Cancel: the mutating endpoint must never be called.
        self.assertNotIn("/api/folder/use", out["afterPickCancel"])
        self.assertNotIn("/api/space/use-untyped", out["useUntypedCancel"])
        self.assertNotIn("/api/space/create", out["createCancel"])
        self.assertNotIn("/api/space/configure", out["createCancel"])
        # And the switch never proceeded to reset/apply the new folder.
        self.assertNotIn("resetDrawer", out["afterPickCancel"])
        self.assertNotIn("applyFolder", out["afterPickCancel"])

        # Sanity: an allowed switch does call the mutating endpoint.
        self.assertIn("/api/folder/use", out["afterPickAllowed"])

    def test_hosted_folder_switch_preflight_blocks_target_writes_on_cancel(self):
        # Fix 019 correction C1.3: the hosted Save/Discard/Cancel preflight
        # must resolve BEFORE any write to the target folder (inventory
        # migration, metadata upgrade) or adoption of it as the active
        # folder/handle. A Cancel must leave the target folder untouched and
        # must not change state.browserFolder or the saved active handle.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")

        use_hosted = self._spaces_slice(spaces_js, "SP.useHostedFolder = async (folder")

        script = "\n".join([
            "const calls = [];",
            "let leaveOk = false; // simulate Cancel",
            "const state = { browserFolder: 'OLD_FOLDER' };",
            "const SP = {",
            "  inspectHosted: async () => ({",
            "    needs_setup: false, folder_mode: 'space', inventory: true,",
            "    needs_identity_migration: false, metadata_version: 999, space: { name: 'S' }, space_id: 'sid',",
            "    keep_bin_defaults: true, bin_defaults: null, part_defaults: {},",
            "  }),",
            "  assertExpectedHostedIdentity: () => {},",
            "  leaveDrawerLayoutSafely: async () => leaveOk,",
            "  resetDrawer: async () => { calls.push('resetDrawer'); return true; },",
            "  readInventoryFor: async () => { calls.push('readInventoryFor:migrate'); return ''; },",
            "  writeMetadata: async () => { calls.push('writeMetadata'); return {}; },",
            "  applyFolder: async () => { calls.push('applyFolder'); return true; },",
            "  close: () => { calls.push('close'); },",
            "};",
            "const FOLDER_METADATA_VERSION = 1;",
            "const toast = () => {};",
            "const WFFileSystem = { save: async () => { calls.push('WFFileSystem.save(active)'); } };",
            use_hosted,
            "(async () => {",
            "  const out = {};",
            "  const folder = { handle: {}, name: 'NewFolder' };",
            "",
            "  leaveOk = false;",
            "  calls.length = 0;",
            "  state.browserFolder = 'OLD_FOLDER';",
            "  const result = await SP.useHostedFolder(folder);",
            "  out.result = result;",
            "  out.cancelCalls = calls.slice();",
            "  out.browserFolderAfterCancel = state.browserFolder;",
            "",
            "  leaveOk = true;",
            "  calls.length = 0;",
            "  await SP.useHostedFolder(folder);",
            "  out.allowedCalls = calls.slice();",
            "",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)

        self.assertIsNone(out["result"])  # aborted
        # No write to the target folder, and no adoption as active.
        for forbidden in (
            "readInventoryFor:migrate", "writeMetadata", "resetDrawer",
            "WFFileSystem.save(active)", "applyFolder", "close",
        ):
            self.assertNotIn(forbidden, out["cancelCalls"])
        self.assertEqual(out["browserFolderAfterCancel"], "OLD_FOLDER")

        # Sanity: an allowed switch does perform the target writes/adoption.
        self.assertIn("readInventoryFor:migrate", out["allowedCalls"])
        self.assertIn("WFFileSystem.save(active)", out["allowedCalls"])

    def test_hosted_drawer_actions_stay_disabled_every_render(self):
        # Item 3: hosted capability is part of the normal render-state
        # calculation (DP.renderStats), not only a one-time DP.build() patch.
        root = Path(__file__).resolve().parent / "web"
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        stats = panel[panel.index("DP.renderStats = () => {"):]
        stats = stats[:stats.index("\n};")]
        self.assertIn("const hosted = Boolean(state.runtime.hosted);", stats)
        for selector in ('"#dl-sp-plan"', '"#dl-sp-generate"', '"#dl-sp-print"'):
            self.assertIn(selector, stats)
        self.assertNotIn('"#dl-print"', stats)
        self.assertIn("if (hosted) {", stats)
        self.assertIn("DP.HOSTED_UNSUPPORTED_TOOLTIP", panel)

    def test_generate_selected_spacers_disabled_without_a_selected_plan(self):
        # Item 4: never an enabled silent no-op - needs a current plan AND a
        # selected candidate, not merely "not busy and something is placed".
        root = Path(__file__).resolve().parent / "web"
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        stats = panel[panel.index("DP.renderStats = () => {"):]
        stats = stats[:stats.index("\n};")]
        self.assertIn("const hasPlan = Boolean(DL.spacerPlan);", stats)
        self.assertIn("DL.spacerSelected && DL.spacerSelected.size > 0", stats)
        self.assertIn('"Plan spacers first."', stats)
        self.assertIn('"Select at least one planned spacer."', stats)

    def test_startup_errors_reach_welcome_with_visible_text(self):
        # Item 6: a real metadata/identity/read exception must show up on
        # Welcome, not be silently swallowed into an ordinary-looking screen.
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        index_html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="welcome-startup-error"', index_html)
        show_home = spaces_js[spaces_js.index("SP.showHome = (message"):]
        show_home = show_home[:show_home.index("\n};\n")]
        self.assertIn("welcome-startup-error", show_home)
        launch = spaces_js[spaces_js.index("SP.launch = async () => {"):]
        launch = launch[:launch.index("\nSP.wire = ")]
        self.assertIn("SP.showHome(error.message)", launch)
        # The quiet, expected non-error paths (no remembered folder /
        # permission not granted) still fall back with no message.
        self.assertIn("if (!hasPermission) { SP.showHome(); return; }", launch)

    def test_hosted_startup_thrown_read_failure_is_visible(self):
        # Fix 019 correction C1.5: no remembered folder, or permission
        # simply not (yet) granted, are quiet/expected - Welcome with no
        # message. A thrown exception while actually reading the saved
        # record or querying permission is a real startup/read failure and
        # must reach the visible Welcome recovery message instead of being
        # swallowed into an ordinary-looking Welcome screen.
        node = self._node_or_skip()
        root = Path(__file__).resolve().parent / "web"
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        launch = spaces_js[spaces_js.index("SP.launch = async () => {"):]
        launch = launch[:launch.index("\nSP.wire = ")]

        script = "\n".join([
            "const SP = {};",
            "let loadResult = null, loadThrows = false, permResult = false, permThrows = false;",
            "const homeCalls = [];",
            "SP.showHome = (message) => { homeCalls.push(message); };",
            "const WFFileSystem = {",
            "  load: async () => { if (loadThrows) throw new Error('storage read failed'); return loadResult; },",
            "  queryReadWritePermission: async () => { if (permThrows) throw new Error('permission query failed'); return permResult; },",
            "};",
            "const api = async () => ({});",
            "const state = { runtime: { hosted: true } };",
            launch,
            "(async () => {",
            "  const out = {};",
            "  // No saved record at all - quiet Welcome, no message.",
            "  loadResult = null; loadThrows = false; permResult = false; permThrows = false;",
            "  await SP.launch();",
            "  out.noRecord = homeCalls.slice();",
            "  homeCalls.length = 0;",
            "  // Saved record, but permission simply not granted - quiet Welcome.",
            "  loadResult = { handle: { name: 'x' }, space_id: null }; permResult = false; permThrows = false;",
            "  await SP.launch();",
            "  out.permNotGranted = homeCalls.slice();",
            "  homeCalls.length = 0;",
            "  // The saved-record read itself throws - a real read failure, must be visible.",
            "  loadThrows = true;",
            "  await SP.launch();",
            "  out.loadThrew = homeCalls.slice();",
            "  homeCalls.length = 0;",
            "  // The permission query itself throws - also a real read failure.",
            "  loadThrows = false; permThrows = true;",
            "  await SP.launch();",
            "  out.permThrew = homeCalls.slice();",
            "  process.stdout.write(JSON.stringify(out));",
            "})();",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        out = json.loads(done.stdout)
        # Quiet, expected outcomes call SP.showHome() with no message.
        self.assertEqual(out["noRecord"], [None])
        self.assertEqual(out["permNotGranted"], [None])
        # A thrown exception must call SP.showHome(<a real message>).
        self.assertEqual(len(out["loadThrew"]), 1)
        self.assertTrue(out["loadThrew"][0])
        self.assertEqual(len(out["permThrew"]), 1)
        self.assertTrue(out["permThrew"][0])

    def test_connector_action_labels_match_bundle(self):
        # Item 7 (Fix 048B wording): same height -> "Save Connectors"/"Save Bin
        # + Connectors"; different heights -> "Save Side Connector"/
        # "Save Bin + Side Connector" - synced on height-mode change
        # and during normal syncForm(), not fixed at first render.
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")
        labels = app_js[app_js.index("function syncConnectorActionLabels() {"):]
        labels = labels[:labels.index("\n}\n")]
        self.assertIn('"Save Bin + Side Connector"', labels)
        self.assertIn('"Save Bin + Connectors"', labels)
        self.assertIn('"Save Side Connector"', labels)
        self.assertIn('"Save Connectors"', labels)
        self.assertIn("syncConnectorActionLabels();", app_js[app_js.index("function syncConnectorHeightControls"):])
        self.assertIn("syncConnectorActionLabels();", app_js[app_js.index("function syncConnectorSectionVisibility"):])

    def test_fix48b_designer_interaction_simplification(self):
        root = Path(__file__).resolve().parent / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        app_js = (root / "app.js").read_text(encoding="utf-8")
        # 1-2: Bin Actions owner sits before the bin definition controls.
        actions = html.index('id="bin-actions"')
        self.assertLess(actions, html.index('id="part-name"'))
        self.assertNotIn('id="bin-type"', html)
        block = html[actions:html.index("</div>", actions)]
        self.assertIn(">New Bin</button>", block)
        self.assertIn(">Duplicate Bin</button>", block)
        output = html[html.index('class="output-panel"'):html.index('id="drawer-panel"')]
        self.assertNotIn("designer-new-bin", output)
        self.assertNotIn("designer-duplicate", output)
        self.assertEqual(html.count('id="designer-new-bin"'), 1)
        self.assertEqual(html.count('id="designer-duplicate"'), 1)
        # 3-5: manual Space Save/Load workflow is gone; file controls remain.
        for token in ("designer-save-space", "designer-load-space", "designer-load-dialog",
                      "designer-load-list", "designer-load-other", "designer-load-cancel"):
            self.assertNotIn(token, html)
            self.assertNotIn(token, app_js)
        for token in ("designerSaveToSpace", "chooseDesignerSource",
                      "designerLoadFromSpace", "designerLoadFromAnotherSpace"):
            self.assertNotIn(token, app_js)
        self.assertIn('id="designer-save-file"', html)
        self.assertIn('id="designer-open-file"', html)
        vis = app_js[app_js.index("function applyDesignerLifecycleVisibility() {"):]
        vis = vis[:vis.index("\n}\n")]
        self.assertIn('hide("#designer-save-file", typed)', vis)
        self.assertIn('hide("#designer-open-file-label", typed)', vis)
        self.assertNotIn("designer-new-bin", vis)
        self.assertIn("async function designerEditInventoryRow(", app_js)
        self.assertIn("async function flushSpaceDesignAutosave(", app_js)
        # 6: Save wording.
        for text in (">Save Bin + Connectors<", ">Save Bin<", ">Save Connectors<", "Saving Parts…"):
            self.assertIn(text, html)
        self.assertNotIn(">Generate Bin", html)
        for text in ('"Save Bin + Lid"', '"Save Bin"',
                     '"Saving Failed"', '"Saved — design save needs attention"'):
            self.assertIn(text, app_js)
        # Base Trim is saved from its Space, not the Designer.
        self.assertNotIn('"Save Base Trim"', app_js)
        self.assertNotIn('"Generate Bin', app_js)
        self.assertNotIn('"Generate to Folder"', app_js)
        # 7-9: browse/edit palette, selected-row-only Done/Delete.
        self.assertNotIn('id="draft-actions"', html)
        self.assertNotIn('id="save-part"', html)
        self.assertNotIn('id="delete-part"', html)
        sel = app_js[app_js.index("function updateSelectionButtons() {"):]
        sel = sel[:sel.index("\n}\n")]
        self.assertIn('$("#support-palette").hidden = editing;', sel)
        markup = app_js[app_js.index("function placedRowsMarkup("):]
        markup = markup[:markup.index("\n}\n")]
        self.assertIn("actions && row.editing", markup)
        renderer = app_js[app_js.index("function renderPlaced() {"):]
        renderer = renderer[:renderer.index("\n}\n")]
        self.assertIn("placedRowsMarkup(rows, { actions: true })", renderer)
        self.assertIn("placedRowsMarkup(previewRows)", renderer)
        self.assertNotIn("actions: true", renderer.replace("placedRowsMarkup(rows, { actions: true })", ""))
        # 9: temporary selected row for an uncommitted draft; never persisted.
        data = app_js[app_js.index("function placedRowData() {"):]
        data = data[:data.index("\n}\n")]
        self.assertIn('type: "draft"', data)
        self.assertNotIn("features.push", data)
        # 10-11: Done / Delete route through the existing owners.
        wiring = app_js[app_js.index("function wirePlacedRows("):]
        wiring = wiring[:wiring.index("\n}\n")]
        self.assertIn('"click", saveCurrentPart', wiring)
        self.assertIn('"click", deleteCurrentPart', wiring)
        # 12: a sole remaining feature no longer auto-opens.
        self.assertNotIn("selectedFeature(0);", renderer)
        # 13: direct selection still uses the existing owners.
        self.assertIn("await selectedFeature(Number(button.dataset.index));", wiring)
        self.assertIn("openModifier(button.dataset.kind, true)", wiring)

    def test_native_confirms_replaced_with_app_dialog(self):
        # Item 8: the five listed native confirm() sites are gone; the
        # reusable dialog helper (and the three-way Save/Discard/Cancel
        # variant Item 2 needs) exist instead.
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")
        panel = (root / "drawer-panel.js").read_text(encoding="utf-8")
        spaces_js = (root / "spaces.js").read_text(encoding="utf-8")
        index_html = (root / "index.html").read_text(encoding="utf-8")

        open_design = app_js[app_js.index("async function openDesign("):app_js.index("async function newDesign(")]
        self.assertNotIn("window.confirm(", open_design)
        new_design = app_js[app_js.index("async function newDesign("):]
        new_design = new_design[:new_design.index("\nlet isGenerating")]
        self.assertNotIn("window.confirm(", new_design)

        self.assertNotIn("confirm(`Delete ${drawer.name}", panel)
        self.assertNotIn("confirm(`Remove ${DL.label(one)}", panel)
        self.assertIn("appConfirmAction({", panel)

        show_folder = spaces_js[spaces_js.index("SP.showFolder = async"):]
        show_folder = show_folder[:show_folder.index("\n};\n")]
        self.assertNotIn("confirm(", show_folder)
        self.assertIn("appConfirmAction({", show_folder)

        self.assertIn('id="app-confirm-dialog"', index_html)
        self.assertIn("function appConfirm(", app_js)
        # Fix 034 K1: the three-way Save & Switch / Discard & Switch / Cancel
        # dialog (appConfirmSaveDiscardCancel) existed only for the now-
        # retired Autosave-Off path - SP.leaveDrawerLayoutSafely always just
        # flushes and aborts on failure, so that helper is gone too.
        self.assertNotIn("appConfirmSaveDiscardCancel", app_js)

    def test_native_confirms_replaced_regressions_leave_class_confirms_alone(self):
        # Sanity check that the sweep did not touch confirm() usage outside
        # the five listed sites (e.g. the unrelated B4B interior-parts
        # confirm stays a plain window.confirm(), out of Item 8's scope).
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")
        # The Designer no longer converts a bin into a Storage Box, so that
        # interior-parts confirm left with the conversion.
        self.assertNotIn("Turning on Storage Box removes all interior parts", app_js)

    def test_primary_bin_y_axis_reads_depth(self):
        # Item 9B: the main bin/Space Y axis is "Depth", not "Length" -
        # part-specific Length fields (Base width/length, slot/screw/label
        # length) are untouched.
        root = Path(__file__).resolve().parent / "web"
        index_html = (root / "index.html").read_text(encoding="utf-8")
        app_js = (root / "app.js").read_text(encoding="utf-8")
        self.assertIn('<span id="y-size-label">Depth</span>', index_html)
        self.assertNotIn("Depth (Inside)", app_js)
        # Untouched part-specific Length fields.
        self.assertIn('field("Length", "item_length"', app_js)
        self.assertIn('field("Length", "depth", fmt(shownDepth)', app_js)

    def test_responsive_workspace_height_is_viewport_aware(self):
        # Item 9A: no more hard-coded 720px on every <=980px viewport - a
        # capped, viewport-aware rule with a useful minimum instead.
        root = Path(__file__).resolve().parent / "web"
        styles = (root / "styles.css").read_text(encoding="utf-8")
        start = styles.index("@media (max-width: 980px)")
        block = styles[start:styles.index("@media (max-width: 620px)", start)]
        self.assertNotIn(".workspace { height: 720px; }", block)
        self.assertIn("svh", block)
        self.assertIn("min(720px", block)

    def test_edge_mount_label_selector_browser_contract(self):
        # Fix 058 Correction 1, C1.4: the former top-level Label/Screw
        # Mounting enable checkboxes and separate "Label Type" dropdown are
        # gone, replaced by one always-visible Label: None/Separate
        # Part/Integrated selector, with Screw Mounting's checkbox living in
        # its own section header.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn('id="edge-mount-label-type"', index)
        self.assertNotIn('id="edge-mount-label-enabled"', index)
        self.assertIn('id="edge-mount-label-mode"', index)
        self.assertIn('value="none">None', index)
        self.assertIn('value="separate">Separate Part', index)
        self.assertIn('value="integrated">Integrated', index)
        # Screw Mounting's checkbox lives inside its own section header, not
        # floating above both sections.
        holes_panel = index[index.index('id="edge-mount-holes-panel"'):index.index('id="edge-mount-holes-details"')]
        self.assertIn('id="edge-mount-holes-enabled"', holes_panel)
        self.assertIn(">Screw Mounting<", holes_panel)

        read = app_js[app_js.index("function readEdgeMountForm(design) {"):app_js.index("function resolvedEdgeMountAccessDiameter")]
        self.assertIn('$("#edge-mount-label-mode")', read)
        self.assertIn("label_type:", read)

    def test_edge_mount_label_mode_default_and_mapping(self):
        # C1.4B: a new Edge Mount defaults to Label=None + Screw Mounting
        # off; existing saved states map back to the correct selector value.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        mode_fn = app_js[app_js.index("function edgeMountLabelMode("):app_js.index("function readEdgeMountForm(")]
        self.assertIn('return "none"', mode_fn)
        self.assertIn('"integrated" : "separate"', mode_fn)
        add_start = app_js.index('if (kind === "edge_mount") {', app_js.index("async function addModifier("))
        add_end = app_js.index("recordHistory(previous);", add_start)
        add_source = app_js[add_start:add_end]
        self.assertIn("label_enabled: false,", add_source)
        self.assertIn("holes_enabled: false,", add_source)

    def test_edge_mount_separate_part_cannot_be_raised_in_browser(self):
        # C1.4C: Separate Part forces label_raised false and hides the Label
        # style control entirely, both when read from the form and when
        # syncing the DOM from state.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="edge-mount-label-style-row"', index)
        read = app_js[app_js.index("function readEdgeMountForm(design) {"):app_js.index("function resolvedEdgeMountAccessDiameter")]
        self.assertIn('labelType === "separate"\n    ? false', read)
        sync = app_js[app_js.index("function syncEdgeMountControls() {"):app_js.index("function syncEdgeMountEditorVisibility() {")]
        self.assertIn('labelMode !== "integrated"', sync)

    def test_edge_mount_text_depth_default_is_edge_mount_scoped(self):
        # C1.4D: 0.6 mm is Edge Mount's own new/missing-value default and
        # must never rewrite the shared, global TEXT_DEPTH constant.
        root = Path(__file__).resolve().parent
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        app_py = (root / "organizer_app.py").read_text(encoding="utf-8")
        engine_py = (root / "organizer_engine.py").read_text(encoding="utf-8")
        self.assertIn("EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM = 0.6", app_js)
        self.assertIn("label_text_depth_mm: EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM", app_js)
        self.assertIn("EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM = 0.6", engine_py)
        self.assertIn("TEXT_DEPTH = 0.4", engine_py)  # unchanged global default
        self.assertIn(
            'edge_mount_raw.get("label_text_depth_mm", EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM)', app_py,
        )

    def test_edge_mount_removed_and_relocated_help_text(self):
        # C1.4A/D/E: the redundant opened-editor instruction and the two
        # permanent help paragraphs are gone; the screwdriver-path
        # explanation survives as hover/title help on Screw Mounting.
        root = Path(__file__).resolve().parent
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("Projects from the top of the mounting wall", index)
        self.assertNotIn(
            "<p class=\"inline-help\">The small holes go through the mounting wall.", index,
        )
        self.assertIn(
            'title="The small holes go through the mounting wall. Larger round '
            'access passages come from the opposite wall so a screwdriver can '
            'reach each screw."', index,
        )
        app_py = (root / "wavefinity_web.py").read_text(encoding="utf-8")
        self.assertIn("Add a label and/or screw mounting for an outside edge.", app_py)
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn(
            'description.hidden = isNest || kind === "edge_mount" || kind === "lid_stacking";', app_js,
        )

    def test_edge_mount_field_grouping_and_compact_sizing(self):
        # C1.4D/F: Flip text sits on the Text row, Standoff Ribs/Quantity are
        # grouped after the core label fields and only for Separate Part,
        # and compact sizing is scoped under #edge-mount-editor.
        root = Path(__file__).resolve().parent
        index = (root / "web" / "index.html").read_text(encoding="utf-8")
        text_group = index[index.index('edge-mount-text-group'):index.index('id="edge-mount-integrated-support-warning"')]
        self.assertIn('id="edge-mount-label-text"', text_group)
        self.assertIn('id="edge-mount-label-flip"', text_group)
        details = index[index.index('id="edge-mount-label-details"'):index.index('id="edge-mount-holes-panel"')]
        self.assertLess(details.index('id="edge-mount-label-text"'), details.index('id="edge-mount-standoff-rib-controls"'))
        styles = (root / "web" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("#edge-mount-editor .edge-mount-compact-number input", styles)
        self.assertIn("#edge-mount-editor .edge-mount-compact-select select", styles)
        self.assertIn("width: 90px", styles)


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

    def test_space_card_images_are_served_from_image_root(self):
        for name in ("Drawer.png", "Vanity.png", "B4B.png", "Pegboard.png"):
            status, headers, body = self.get(f"/images/{name}")
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"], "image/png")
            self.assertTrue(body)

        with self.assertRaises(HTTPError) as caught:
            self.get("/images/%2e%2e%2fweb%2findex.html")
        self.assertEqual(caught.exception.code, 404)

    def test_health_catalog_and_static_application_are_served(self):
        status, headers, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cross-Origin-Resource-Policy"], "same-origin")
        health = json.loads(body)
        self.assertTrue(health["ok"])
        self.assertTrue(health["instance"])
        self.assertEqual(health["api_compat"], 2)
        self.assertEqual(health["instance"], catalog_payload()["instance"])
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertNotIn(b"Design a:", body)
        self.assertNotIn(b'id="bin-type"', body)
        self.assertNotIn(b'id="advanced-settings"', body)
        self.assertNotIn(b'id="advanced-build-settings"', body)
        self.assertIn(b"Base thickness", body)
        self.assertIn(b'id="base-thickness"', body)
        self.assertNotIn(b"Advanced bin settings", body)
        self.assertNotIn(b"Wall / floor", body)
        self.assertNotIn(b"Flat wall band", body)
        self.assertNotIn(b"Label your bin", body)
        self.assertNotIn(b"Rim label", body)
        self.assertIn(b"Parts &amp; options", body)
        self.assertIn(b'id="part-name"', body)
        self.assertIn(b"Connectors", body)
        self.assertIn(b">Save folder</label>", body)
        self.assertIn(b'id="print-with-connectors"', body)
        self.assertIn(b">Print with Connectors</button>", body)
        self.assertIn(b'id="print-without-connectors"', body)
        self.assertIn(b">Print without Connectors</button>", body)
        self.assertIn(b'id="generate-all"', body)
        self.assertIn(b"Save Bin + Connectors", body)
        self.assertIn(b'id="generate-bin"', body)
        self.assertIn(b">Save Bin</button>", body)
        self.assertIn(b'id="generate-connector"', body)
        self.assertIn(b">Save Connectors</button>", body)
        self.assertNotIn(b"generate-sampler", body)
        self.assertNotIn(b"Generate sampler", body)
        self.assertIn(b'id="generation-dialog"', body)
        self.assertIn(b"Bin heights", body)
        self.assertIn(b'id="connector-height-mode"', body)
        self.assertIn(b'id="base-thickness"', body)
        self.assertIn(b'id="wall-thickness"', body)
        self.assertIn(b'id="lift-grabber-size"', body)
        self.assertIn(b'id="side-openings-option"', body)
        self.assertIn(b'id="side-openings-panel"', body)
        self.assertIn(b'id="side-opening-shape"', body)
        self.assertIn(b'id="side-opening-front"', body)
        self.assertIn(b'id="side-opening-back"', body)
        self.assertIn(b'id="side-opening-left"', body)
        self.assertIn(b'id="side-opening-right"', body)
        self.assertIn(b'id="side-opening-size"', body)
        self.assertIn(b'id="side-opening-from-bottom"', body)
        self.assertIn(b'id="side-opening-from-top"', body)
        self.assertIn(b'id="side-opening-note"', body)
        # The Side Openings card sits with Lid & Stacking, before the
        # interior-part palette - not inside it.
        self.assertLess(
            body.index(b"<h2>Parts &amp; options</h2>"),
            body.index(b'id="side-openings-option"'),
        )
        self.assertLess(
            body.index(b'id="side-openings-option"'),
            body.index(b'id="support-palette"'),
        )
        self.assertNotIn(b'id="standard-base"', body)
        self.assertNotIn(b'id="standard-walls"', body)
        self.assertNotIn(b'id="different-height-bins"', body)
        self.assertNotIn(b'id="easy-clean"', body)
        self.assertIn(b"connector-bin-a-height", body)
        self.assertIn(b"connector-arm-thickness", body)
        self.assertIn(b">A height <", body)
        self.assertIn(b">B height <", body)
        self.assertNotIn(b"This bin (A)", body)
        self.assertNotIn(b"connector-position", body)
        self.assertNotIn(b"connector-axis", body)
        self.assertIn(b"support-layout-dialog", body)
        self.assertNotIn(b"Add curved scoop", body)
        self.assertNotIn(b"Fixed 5 mm lettering on a shelf", body)
        # Bin type comes first: it decides what every control under it means,
        # so it sits above the size fields and everything else.
        self.assertLess(body.index(b'id="part-name"'), body.index(b'id="x-size"'))
        self.assertLess(body.index(b'id="x-size"'), body.index(b'id="mode-select"'))
        self.assertLess(body.index(b'id="mode-select"'), body.index(b"<h2>Parts &amp; options</h2>"))
        self.assertLess(body.index(b"<h2>Parts &amp; options</h2>"), body.index(b"Connectors"))
        self.assertLess(body.index(b"Connectors"), body.index(b">Save folder</label>"))
        # Part name now lives right with Bin type at the very top - naming the
        # bin is the first thing a person does, not something buried with the
        # output controls further down.
        self.assertLess(body.index(b'id="designer-new-bin"'), body.index(b'id="part-name"'))
        self.assertLess(body.index(b'id="part-name"'), body.index(b'id="x-size"'))
        # The palette itself is the "add another part" affordance now - there is
        # no separate button. Editing a part shows Done / Delete on its selected
        # Added row.
        self.assertNotIn(b'id="add-support"', body)
        self.assertLess(body.index(b'id="support-palette"'), body.index(b'id="draft-fields"'))
        self.assertLess(body.index(b'id="added-parts-list"'), body.index(b'id="draft-fields"'))
        self.assertIn(b'id="mode-select"', body)
        # Print mode and 2D orientation are selects; preview filters are buttons.
        self.assertIn(b'id="ordinary-preview-modes"', body)
        self.assertIn(b'id="layout-orientation-controls"', body)
        # The four mutually-exclusive camera modes were replaced by three
        # independently toggleable Bin/Interior/Xray buttons.
        for value in (b"bin", b"interior", b"xray"):
            self.assertIn(b'data-camera-toggle="%s"' % value, body)
        # 2D orientation (Match 3D / Top Up) is its own toggle group, using
        # this same per-button attribute pattern.
        self.assertIn(b'data-layout-orientation="match3d"', body)
        self.assertIn(b'data-layout-orientation="topup"', body)
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
        self.assertIn(b"syncNest2DWorkspace", body)
        self.assertIn(b'"rotate"', body)
        # The part name is seeded once from the first real piece of lettering,
        # and the bespoke floor-label drag is gone - text is an interior part.
        self.assertIn(b"seedPartNameFromText", body)
        self.assertIn(b"SIZE_LIKE_TEXT", body)
        self.assertIn(b"selectKind(kind);", body)
        self.assertIn(b"kindRequest", body)
        self.assertIn(b"fitRequest", body)
        # The old single photo-upload request counter is now the two-phase
        # trace/retrace request counters, matching the backend's own split
        # of tracing (nest_trace_payload) from finalizing (photo_nest_payload).
        self.assertIn(b"nestTraceRequest", body)
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
        # Process identity remains observable, but the frontend only asks for
        # a reload when API_COMPAT_VERSION changes.
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


class Fix20SpaceFormTests(unittest.TestCase):
    """Tests for Item 2, 3, 4: Space form, dimensions, and local folder auto-creation."""

    def test_space_form_type_and_dimension_row_markup(self):
        root = Path(__file__).resolve().parent / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        self.assertIn('<p id="space-form-type"', html)
        # Six for the type/dimension rows plus four for the Storage Box case settings.
        self.assertEqual(html.count('class="space-dimension-row"'), 10)
        self.assertIn(
            'id="space-create" class="button primary" type="button"',
            html,
        )
        self.assertIn(
            'id="space-save-changes" class="button primary" type="button"',
            html,
        )

    def test_space_form_submit_event_and_button_clicks(self):
        import re
        root = Path(__file__).resolve().parent / "web"
        spaces = (root / "spaces.js").read_text(encoding="utf-8")
        self.assertIn(
            'spaceForm.addEventListener("submit", event => event.preventDefault());',
            spaces,
        )
        self.assertIn(
            'document.getElementById("space-create")',
            spaces,
        )
        self.assertIn(
            '?.addEventListener("click", () => SP.run(SP.create));',
            spaces,
        )
        self.assertIn(
            'document.getElementById("space-save-changes")',
            spaces,
        )
        self.assertIn(
            '?.addEventListener("click", () => SP.run(SP.updateSpace));',
            spaces,
        )
        wire_start = spaces.index("SP.wire = () => {")
        wire_end = spaces.index("\n};", wire_start)
        wire_body = spaces[wire_start:wire_end]
        self.assertFalse(re.search(r'addEventListener\(["\']submit["\'].*(?:create|updateSpace)', wire_body))

    def test_space_setup_button_labels_and_help(self):
        root = Path(__file__).resolve().parent / "web"
        spaces = (root / "spaces.js").read_text(encoding="utf-8")
        self.assertIn('createButton.textContent = state.runtime.hosted', spaces)
        self.assertIn('? "Choose Folder & Create"', spaces)
        self.assertIn(': "Create Space";', spaces)
        self.assertIn('Wavefinity will save this Space under Documents\\\\Wavefinity using the Space name.', spaces)

    def test_local_create_does_not_call_pick_folder_or_inspect(self):
        root = Path(__file__).resolve().parent / "web"
        spaces = (root / "spaces.js").read_text(encoding="utf-8")
        self.assertIn('if (!migrating && state.runtime.hosted) {', spaces)
        self.assertIn('folder = await SP.pickFolder({ stayOnSetup: true });', spaces)
        self.assertIn('data = await SP.inspectHosted(folder);', spaces)


class Fix20InsideGripTests(unittest.TestCase):
    """Tests for Item 5: Inside Grip terminology and visibility."""

    def test_catalog_and_ui_labels(self):
        root = Path(__file__).resolve().parent / "web"
        html = (root / "index.html").read_text(encoding="utf-8")
        app_js = (root / "app.js").read_text(encoding="utf-8")
        catalog = catalog_payload()
        inside_handles = next(p for p in catalog["parts"] if p["kind"] == "inside_handles")
        self.assertEqual(inside_handles["title"], "Inside Grip")
        self.assertEqual(inside_handles["description"], "A finger grip inside the bin so it is easier to lift.")
        self.assertIn("Inside Grip size", html)
        self.assertIn("Inside Grip location", html)
        self.assertIn("INSIDE_HANDLES_REMOVABLE_MESSAGE", app_js)
        self.assertIn("Inside Grip is built into the bin wall", app_js)

    def test_b4b_and_app_validation_messages(self):
        import organizer_b4b as b4b
        from organizer_engine import BoxSpec, B4BSpec, LiftGrabberSpec
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True), lift_grabbers=LiftGrabberSpec(enabled=True))
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box)
        self.assertIn("Inside Grip is not available on Storage Box", str(ctx.exception))

    def test_mode_visibility_does_not_force_show_modifier_panels(self):
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")
        self.assertNotIn('hide("#inside-handles-option", on)', app_js)
        self.assertNotIn("function applyB4BVisibility", app_js)
        self.assertNotIn("function applyBaseTrimVisibility", app_js)


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

    def test_app_js_b4b_divider_and_guard_contracts(self):
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")
        self.assertIn("function b4bPartAllowed(kind) {\n  return kind === \"divider\";\n}", app_js)

        pick_start = app_js.index("function pickKind(kind) {")
        pick_end = app_js.index("async function selectEdgeMount(", pick_start)
        pick = app_js[pick_start:pick_end]
        self.assertLess(
            pick.index("if (b4bEnabled() && !b4bPartAllowed(kind)) return;"),
            pick.index("state.paletteBrowsing = false;"),
        )
        self.assertIn("if (b4bEnabled() && kind === \"divider\") {", pick)

        select_start = app_js.index("async function selectKind(kind, reset = false) {")
        select_end = app_js.index("async function selectedFeature(", select_start)
        select = app_js[select_start:select_end]
        self.assertLess(
            select.index("if (b4bEnabled() && !b4bPartAllowed(kind)) return;"),
            select.index("state.draftKind = kind;"),
        )

        open_mod_start = app_js.index("async function openModifier(kind, fromPlaced = false) {")
        open_mod_end = app_js.index("async function addModifier(", open_mod_start)
        open_mod = app_js[open_mod_start:open_mod_end]
        self.assertLess(
            open_mod.index("if (b4bEnabled()) return;"),
            open_mod.index("if (!BOX_MODIFIER_KINDS.has(kind)"),
        )

        add_mod_start = app_js.index("async function addModifier(kind) {")
        add_mod_end = app_js.index("async function removeModifier(", add_mod_start)
        add_mod = app_js[add_mod_start:add_mod_end]
        self.assertLess(
            add_mod.index("if (b4bEnabled()) return;"),
            add_mod.index("if (kind === \"inside_handles\""),
        )

        div_ext_start = app_js.index("function dividerLayoutExtent(box = state.design?.box) {")
        div_ext_end = app_js.index("function stackMode() {", div_ext_start)
        div_ext = app_js[div_ext_start:div_ext_end]
        self.assertIn("if (box?.b4b?.enabled) {\n    return [number(box.x), number(box.y)];\n  }", div_ext)

        elig_start = app_js.index("function eligibleGridDividerIndexes() {")
        elig_end = app_js.index("function updateDividerEditBreadcrumb() {", elig_start)
        elig = app_js[elig_start:elig_end]
        self.assertNotIn("b4bEnabled()", elig)

        render_start = app_js.index("function renderDraftFields() {")
        render_end = app_js.index("function syncNest2DWorkspace(", render_start)
        render_code = app_js[render_start:render_end]
        self.assertIn(
            "if (!b4bEnabled()) {\n      const hasLabels = opt.label_divisions === true;",
            render_code,
        )

        # The Storage Box panel left the Designer with the type switch.
        self.assertNotIn("function applyB4BVisibility", app_js)

    def test_default_feature_payload_for_b4b_divider(self):
        design = self._b4b_design()
        result = default_feature_payload({"design": design, "kind": "divider"})
        feat = result["feature"]
        self.assertEqual(feat["kind"], "divider")
        self.assertEqual(feat["zone"], [-32.0, -24.0, 32.0, 24.0])
        self.assertTrue(feat["full_span"])
        self.assertEqual(result["resolved_options"]["height"], 40.0)

        # Duplicate divider is rejected
        design_with_div = self._b4b_design(features=[feat])
        with self.assertRaises(ValueError) as ctx:
            default_feature_payload({"design": design_with_div, "kind": "divider"})
        self.assertIn("one Divider layout", str(ctx.exception))

        # Non-divider is rejected
        with self.assertRaises(ValueError) as ctx:
            default_feature_payload({"design": design, "kind": "bore"})
        self.assertIn("Dividers only", str(ctx.exception))

    def test_apply_and_delete_feature_payload_for_b4b(self):
        design = self._b4b_design()
        default_res = default_feature_payload({"design": design, "kind": "divider"})
        feat = default_res["feature"]

        applied = apply_feature_payload({"design": design, "feature": feat})
        self.assertEqual(applied["selected"], 0)
        self.assertEqual(len(applied["design"]["layout"]["features"]), 1)
        self.assertEqual(applied["design"]["layout"]["features"][0]["kind"], "divider")

        # Delete returns layout with 0 features
        deleted = delete_feature_payload({"design": applied["design"], "index": 0})
        self.assertEqual(len(deleted["design"]["layout"]["features"]), 0)

    def test_b4b_preview_payload_with_divider_and_draft(self):
        design = self._b4b_design()
        default_res = default_feature_payload({"design": design, "kind": "divider"})
        feat = default_res["feature"]
        design["layout"]["features"] = [feat]

        preview = preview_payload({"design": design})
        self.assertIn("meshes", preview)
        self.assertTrue(any(
            mesh.get("kind") == "feature_divider"
            for mesh in preview["meshes"]
        ))
        self.assertEqual(preview["layout_bounds"], [-32.0, -24.0, 32.0, 24.0])
        self.assertEqual(len(preview["design"]["layout"]["features"]), 1)

        # Live draft preview
        draft_feat = dict(feat)
        draft_feat["options"] = {"count_x": 2, "count_y": 1}
        draft_prev = preview_payload({"design": design, "draft": draft_feat, "selected": 0})
        self.assertTrue(any(
            mesh.get("kind") == "feature_divider"
            for mesh in draft_prev["meshes"]
        ))
        # Preview never commits live draft to saved design
        self.assertEqual(draft_prev["design"]["layout"]["features"][0]["options"], feat.get("options"))

        # Invalid draft sets draft_error while meshes still generate
        bad_draft = dict(feat)
        bad_draft["options"] = {"label_divisions": True}
        bad_prev = preview_payload({"design": design, "draft": bad_draft, "selected": 0})
        self.assertTrue(bad_prev["draft_error"])
        self.assertTrue(any(
            mesh.get("kind") == "b4b_body" and mesh.get("owner") == "base"
            for mesh in bad_prev["meshes"]
        ))


class Fix20StorageBoxMaterialsTests(unittest.TestCase):
    """Tests for Item 7: Storage Box material presets, defaults, and lid thickness."""

    def test_catalog_b4b_rules(self):
        catalog = catalog_payload()
        rules = catalog["b4b_rules"]
        self.assertEqual(rules["default_wall_mm"], 1.6)
        self.assertEqual(rules["default_base_mm"], 1.6)
        expected_ladder = [
            {"value": 0.8, "label": "Super thin / light duty"},
            {"value": 1.2, "label": "Thin"},
            {"value": 1.6, "label": "Standard"},
            {"value": 2.0, "label": "Strong"},
            {"value": 2.4, "label": "Extra strong / maximum"},
        ]
        self.assertEqual(rules["wall_choices"], expected_ladder)
        self.assertEqual(rules["base_choices"], expected_ladder)

    def test_app_js_material_functions_and_fallbacks(self):
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")

        # b4bMinWall helper
        self.assertIn("function b4bMinWall() {\n  return number(state.catalog?.b4b_rules?.min_wall_mm, 0.8);\n}", app_js)

        # populateWallChoices numericChoices preservation for B4B
        wall_fn_start = app_js.index("function populateWallChoices(box, select = $(\"#wall-thickness\")) {")
        wall_fn_end = app_js.index("function baseRequiredMin(", wall_fn_start)
        wall_fn = app_js[wall_fn_start:wall_fn_end]
        self.assertIn("const numericChoices = isB4B\n    ? choices\n    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);", wall_fn)

        # populateBaseChoices numericChoices preservation for B4B
        base_fn_start = app_js.index("function populateBaseChoices(box, select = $(\"#base-thickness\")) {")
        base_fn_end = app_js.index("function syncBaseControls() {", base_fn_start)
        base_fn = app_js[base_fn_start:base_fn_end]
        self.assertIn("const numericChoices = isB4B\n    ? choices\n    : choices.filter(choice => fmt(choice.value) !== ordinaryDefaultValue);", base_fn)

        # The Storage Box wall/base defaults belong to the Space (space.storage_box),
        # not to a Designer type switch.
        for gone in ("function applyB4BMaterialDefaults", "async function toggleB4B",
                     "function normalizeB4BBaseForStacking", "function visibleB4B", "b4bPreStackBase"):
            self.assertNotIn(gone, app_js)
        spaces_js = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        self.assertIn('SP.fillMaterialSelect("portable-wall"', spaces_js)
        self.assertIn('SP.fillMaterialSelect("portable-base"', spaces_js)
        self.assertIn("b4b_rules?.default_wall_mm", spaces_js)
        self.assertIn("b4b_rules?.default_base_mm", spaces_js)

        # visibleDesignSnapshot / updateDesignFromForm are ordinary-bin only.
        vsnap_start = app_js.index("function visibleDesignSnapshot() {")
        vsnap_end = app_js.index("function designHasChanges() {", vsnap_start)
        self.assertNotIn("visibleB4B", app_js[vsnap_start:vsnap_end])
        self.assertNotIn("readB4BForm", app_js)

        # syncWallControls uses wallPresetChoices and B4B super-thin warning
        sync_wall_start = app_js.index("function syncWallControls() {")
        sync_wall_end = app_js.index("function syncForm() {", sync_wall_start)
        sync_wall = app_js[sync_wall_start:sync_wall_end]
        self.assertIn("const choices = wallPresetChoices(state.design?.box);", sync_wall)
        self.assertIn("Super thin / light duty — reduced case strength.", sync_wall)


    def test_fix060_lid_and_stacking_grouped_by_concept_and_state(self):
        # Fix 060 A: Lid & Stacking reads as Configuration / Lid / Handle /
        # Label groups instead of one mixed grid, Handle is hidden entirely
        # (not merely disabled) outside Handled Lid, Stackable Lid hides the
        # one-choice Style control, and the redundant opened-editor
        # description is suppressed while the palette description remains.
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        app_js = (root / "web" / "app.js").read_text(encoding="utf-8")

        self.assertNotIn('id="lid-physical-options"', index_html)
        self.assertIn('id="lid-group-lid"', index_html)
        self.assertIn('id="lid-group-handle"', index_html)
        self.assertIn('id="lid-group-label"', index_html)
        self.assertIn('id="lid-label-details"', index_html)
        # Handle group and its own fields still exist, just regrouped.
        for handle_id in ("lid-handle-type-row", "lid-handle-size-row", "lid-handle-position-row"):
            self.assertIn(f'id="{handle_id}"', index_html)

        sync_start = app_js.index("function syncLidForm() {")
        sync_end = app_js.index("function stackRuleValues(", sync_start)
        sync_lid_form = app_js[sync_start:sync_end]
        self.assertIn('$("#lid-group-lid").hidden = !hasLid;', sync_lid_form)
        self.assertIn('$("#lid-group-handle").hidden = !handled;', sync_lid_form)
        self.assertIn('$("#lid-group-label").hidden = !hasLid;', sync_lid_form)
        self.assertIn('$("#lid-label-details").hidden = !labelOn;', sync_lid_form)
        # Style is hidden (not just disabled) unless the config is Handled Lid.
        self.assertIn('$("#lid-label-style-row").hidden = !labelOn || !handled;', sync_lid_form)
        # Handle rows are hidden by config state, never erased/reset here.
        self.assertIn('["#lid-handle-type-row", "#lid-handle-size-row", "#lid-handle-position-row"].forEach(selector => {\n    $(selector).hidden = !handled;\n  });', sync_lid_form)

        self.assertIn('kind === "lid_stacking"', app_js)

    def test_fix060_storage_box_case_settings_grouped_by_concept(self):
        # Fix 060 B: #portable-case reads as Lid / Case options / Label /
        # Material sections, with the Label owner selector, Label text and
        # Front label style contiguous inside one group, instead of split
        # across generic three-column rows.
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")

        case_start = index_html.index('id="portable-case"')
        case_end = index_html.index('id="space-fields-pegboard"', case_start)
        case_html = index_html[case_start:case_end]

        for group_id in ("portable-case-lid-group", "portable-case-options-group",
                          "portable-case-label-group", "portable-case-material-group"):
            self.assertIn(f'id="{group_id}"', case_html)

        # Label owner selector, Label text and Front label style must be
        # contiguous inside the Label group, not split across rows.
        label_group_start = case_html.index('id="portable-case-label-group"')
        label_group_end = case_html.index("</div>\n            </div>\n            <div id=\"portable-case-material-group\"")
        label_group_html = case_html[label_group_start:label_group_end]
        self.assertIn('id="portable-label-location"', label_group_html)
        self.assertIn('id="portable-label-text-row"', label_group_html)
        self.assertIn('id="portable-front-label-style-row"', label_group_html)

        # Latch count lives with the Lid group; carrying handle with Case options.
        lid_group_start = case_html.index('id="portable-case-lid-group"')
        lid_group_end = case_html.index('id="portable-case-options-group"')
        self.assertIn('id="portable-latch-count-row"', case_html[lid_group_start:lid_group_end])
        options_group_end = case_html.index('id="portable-case-label-group"')
        self.assertIn('id="portable-handle-row"', case_html[lid_group_end:options_group_end])

        # All persisted keys/ids driving Storage Box case state are unchanged.
        for field_id in ("portable-lid-type", "portable-lid-snugness", "portable-latch-count",
                          "portable-stacking", "portable-handle", "portable-label-location",
                          "portable-label-text", "portable-front-label-style",
                          "portable-wall", "portable-base"):
            self.assertIn(f'id="{field_id}"', case_html)

    def test_fix060_pegboard_hides_physical_help_and_residual_border_in_hole_mode(self):
        # Fix 060 C: the physical-size help text and the Residual border
        # readout are Physical-size-only; Hole/slot-count mode hides both
        # instead of leaking them alongside a meaningless always-0 residual.
        root = Path(__file__).resolve().parent
        index_html = (root / "web" / "index.html").read_text(encoding="utf-8")
        spaces_js = (root / "web" / "spaces.js").read_text(encoding="utf-8")

        self.assertIn('id="pegboard-physical-help"', index_html)
        self.assertIn('id="pegboard-border-row"', index_html)
        # The dt/dd pair stays inside the derived-readout dt/dd grid, wrapped
        # so both id'd pieces hide together.
        self.assertIn(
            '<div id="pegboard-border-row" class="pegboard-border-row">'
            '<dt>Residual border</dt><dd id="pegboard-border-readout"></dd></div>',
            index_html,
        )
        self.assertNotIn('<dt>Residual border</dt><dd id="pegboard-border-readout"></dd>\n          </div>', index_html)

        self.assertIn('const isPhysical = mode === "physical";', spaces_js)
        self.assertIn('if (physicalHelp) physicalHelp.hidden = !isPhysical;', spaces_js)
        self.assertIn('if (borderRow) borderRow.hidden = !isPhysical;', spaces_js)
        # Sizing math itself is untouched by this fix.
        self.assertIn("residualX = width - holesX * standard.pitch_x_mm;", spaces_js)
        self.assertIn("residualY = height - holesY * standard.pitch_y_mm;", spaces_js)

    def test_fix060_correction1_lid_hidden_values_survive_configuration_changes(self):
        # Fix 060 Correction 1: Stackable Bin deletes design.box.lid (so the
        # backend/output and Divider label lock keep seeing no active lid),
        # but the outgoing Lid/Handle/Label values are cached in session-only
        # state.lidMemory and read back through lidState() when the editor
        # rebuilds design.box.lid for Handled/Stackable Lid, so they are not
        # erased merely because Stackable Bin hides them.
        root = Path(__file__).resolve().parent / "web"
        app_js = (root / "app.js").read_text(encoding="utf-8")

        self.assertIn("lidMemory: null,", app_js)

        # lidState() falls back to the remembered values while design.box.lid
        # is absent, but `enabled` always reflects the real design, never the
        # memory - a hidden/inactive lid must never read back as active.
        state_fn_start = app_js.index("function lidState(design = state.design) {")
        state_fn_end = app_js.index("function lidPartActive(")
        lid_state_fn = app_js[state_fn_start:state_fn_end]
        self.assertIn(
            "return { ...LID_DEFAULTS, ...(state.lidMemory || {}), ...(boxLid || {}), "
            "enabled: Boolean(boxLid?.enabled) };",
            lid_state_fn,
        )

        # Switching to Stackable Bin caches the outgoing lid before deleting
        # it, rather than just discarding it. (Fix 060 Correction 2 moved the
        # capture to rememberedLidSnapshot(), called unconditionally before
        # any mutation, so the same call also feeds the Stackable Lid path.)
        stack_form_start = app_js.index("function readStackForm(design) {")
        stack_form_end = app_js.index("function normalizeBinDimension(", stack_form_start)
        read_stack_form = app_js[stack_form_start:stack_form_end]
        self.assertIn('if (design.box.lid) state.lidMemory = rememberedLidSnapshot(design);', read_stack_form)
        self.assertIn("delete design.box.lid;", read_stack_form)

        # Fix 060 Correction 3 moved the reseed/clear boundary off of every
        # syncForm() call (many of which are routine same-design refreshes)
        # and onto explicit bindLidMemoryForDesign() calls at genuine design-
        # replacement sites only - see test_fix060_correction3_* for that
        # call-site closure.
        sync_form_start = app_js.index("function syncForm() {")
        sync_form_end = app_js.index("\nfunction ", sync_form_start + 1)
        self.assertNotIn("state.lidMemory =", app_js[sync_form_start:sync_form_end])

        # Divider label locking still reads design.box.lid directly (never
        # lidState()/memory), so it stays inactive while Stackable Bin hides
        # the lid.
        self.assertIn(
            "function dividerLockedByLidLabels(design = state.design) {\n"
            "  return lidDivisionLabelsMeaningful(design);\n}",
            app_js,
        )
        self.assertIn(
            "return Boolean(design?.box?.lid?.enabled && design.box.lid.label_enabled && lidDivider(design) &&",
            app_js,
        )

    def test_fix060_correction2_label_style_survives_stackable_lid_detour(self):
        # Fix 060 Correction 2: label_style is a real, unforced preference
        # only while Handled Lid is active - Stackable Lid always forces the
        # authoritative value to Flush. This traces the actual state
        # transitions through readStackForm()/rememberedLidSnapshot(),
        # rather than only asserting source text, per the correction's
        # required transition-level verification.
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for this browser-state regression")
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index("const LID_DEFAULTS = {")
        end = source.index("function applyDivisionGridLayout(")
        lid_helpers = source[start:end]
        rs_start = source.index("function readStackForm(design) {")
        rs_end = source.index("\n}\n", rs_start) + 3
        read_stack_form = source[rs_start:rs_end]

        script = "\n".join([
            "const state = { design: null, lidMemory: null };",
            "const fields = {",
            "  '#lid-configuration': 'handled_lid', '#lid-thickness': 'thin',",
            "  '#lid-handle-type': 'knob', '#lid-handle-size': 'medium', '#lid-handle-position': 'middle',",
            "  '#lid-label-enabled': 'true', '#lid-label-orientation': 'horizontal',",
            "  '#lid-label-style': 'raised', '#lid-label-text': 'PARTS',",
            "};",
            "const $ = sel => ({ get value() { return fields[sel]; }, set value(v) { fields[sel] = v; } });",
            lid_helpers,
            read_stack_form,
            # Mirrors what syncLidForm() does in the real app: after every
            # readStackForm() call it unconditionally resyncs every DOM field
            # (even hidden ones) from lidState(), which is exactly why a
            # forced/remembered value can end up live in the DOM regardless
            # of visibility - the same behavior this test must reproduce.
            "function resyncFieldsFromLidState(design) {",
            "  const lid = lidState(design);",
            "  fields['#lid-thickness'] = lid.thickness;",
            "  fields['#lid-handle-type'] = lid.handle_type;",
            "  fields['#lid-handle-size'] = lid.handle_size;",
            "  fields['#lid-handle-position'] = lid.handle_position;",
            "  fields['#lid-label-enabled'] = String(Boolean(lid.label_enabled));",
            "  fields['#lid-label-orientation'] = lid.label_orientation;",
            "  fields['#lid-label-style'] = lid.label_style;",
            "  fields['#lid-label-text'] = lid.label_text || '';",
            "}",
            "function apply(design, configValue, styleValue) {",
            "  fields['#lid-configuration'] = configValue;",
            "  if (styleValue !== undefined) fields['#lid-label-style'] = styleValue;",
            "  readStackForm(design);",
            "  resyncFieldsFromLidState(design);",
            "  return design;",
            "}",
            "const steps = [];",
            # 1. Handled Lid with Raised. (lidPartActive() requires the Lid &
            # Stacking feature to already be active, as it would be once the
            # user has placed it - seed a minimal active Handled Lid.)
            "let design = { box: { lid: { ...LID_DEFAULTS, enabled: true } } };",
            "design = apply(design, 'handled_lid', 'raised');",
            "steps.push({ step: 'handled_raised',",
            "  active: design.box.lid.label_style, memory: state.lidMemory?.label_style });",
            # 2. -> Stackable Lid: active must be Flush, memory must keep Raised.
            "design = apply(design, 'stackable_lid');",
            "steps.push({ step: 'to_stackable_lid',",
            "  active: design.box.lid.label_style, memory: state.lidMemory?.label_style,",
            "  dividerLockActive: dividerLockedByLidLabels(design) });",
            # 3. -> back to Handled Lid: style must restore to Raised.
            "design = apply(design, 'handled_lid');",
            "steps.push({ step: 'back_to_handled',",
            "  active: design.box.lid.label_style, memory: state.lidMemory?.label_style });",
            # 4. Handled Lid with Flush -> Stackable Lid -> Handled Lid: stays Flush.
            "design = apply(design, 'handled_lid', 'flush');",
            "design = apply(design, 'stackable_lid');",
            "design = apply(design, 'handled_lid');",
            "steps.push({ step: 'flush_roundtrip', active: design.box.lid.label_style });",
            # 5. Custom Handle/thickness/label values -> Stackable Bin -> Handled: still restore.
            "design = apply(design, 'handled_lid', 'raised');",
            "fields['#lid-handle-type'] = 'pull'; fields['#lid-handle-size'] = 'large';",
            "fields['#lid-handle-position'] = 'front'; fields['#lid-thickness'] = 'thick';",
            "design = apply(design, 'handled_lid');",
            "design = apply(design, 'stackable_bin');",
            "steps.push({ step: 'stackable_bin_no_lid', hasLid: Boolean(design.box.lid),",
            "  stackMode: design.box.stack.mode, dividerLockActive: dividerLockedByLidLabels(design) });",
            # No manual field reset here: resyncFieldsFromLidState() inside
            # apply() already put the DOM fields back to whatever
            # rememberedLidSnapshot() cached (mirroring syncLidForm() in the
            # real app), so this proves the restoration path itself, not a
            # scripted field value.
            "design = apply(design, 'handled_lid');",
            "steps.push({ step: 'restored_from_stackable_bin',",
            "  handleType: design.box.lid.handle_type, handleSize: design.box.lid.handle_size,",
            "  handlePosition: design.box.lid.handle_position, thickness: design.box.lid.thickness,",
            "  labelStyle: design.box.lid.label_style });",
            # 6. A fresh/different design reseeds memory (no leak).
            "state.design = design; syncFormReseed();",
            "function syncFormReseed() { state.lidMemory = rememberedLidSnapshot(state.design); }",
            "const freshDesign = { box: {} };",
            "state.design = freshDesign; syncFormReseed();",
            "steps.push({ step: 'fresh_design_reseed', memory: state.lidMemory });",
            "process.stdout.write(JSON.stringify(steps));",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        steps = {entry["step"]: entry for entry in json.loads(done.stdout)}

        self.assertEqual(steps["handled_raised"]["active"], "raised")
        self.assertEqual(steps["to_stackable_lid"]["active"], "flush")
        self.assertEqual(steps["to_stackable_lid"]["memory"], "raised")
        self.assertFalse(steps["to_stackable_lid"]["dividerLockActive"])
        self.assertEqual(steps["back_to_handled"]["active"], "raised")
        self.assertEqual(steps["flush_roundtrip"]["active"], "flush")
        self.assertFalse(steps["stackable_bin_no_lid"]["hasLid"])
        self.assertEqual(steps["stackable_bin_no_lid"]["stackMode"], "direct")
        self.assertFalse(steps["stackable_bin_no_lid"]["dividerLockActive"])
        restored = steps["restored_from_stackable_bin"]
        self.assertEqual(restored["handleType"], "pull")
        self.assertEqual(restored["handleSize"], "large")
        self.assertEqual(restored["handlePosition"], "front")
        self.assertEqual(restored["thickness"], "thick")
        self.assertEqual(restored["labelStyle"], "raised")
        self.assertIsNone(steps["fresh_design_reseed"]["memory"])

    def test_fix060_correction3_routine_refresh_preserves_lid_memory(self):
        # Fix 060 Correction 3: syncForm() is called for routine same-design
        # refreshes (modifier apply/rollback, Nest operations, preview
        # auto-grow, and more), not only when a different design is bound to
        # the editor. It must never itself touch state.lidMemory - only the
        # explicit bindLidMemoryForDesign() call at a genuine design-
        # replacement site (New/Open/Duplicate/Undo-Redo/Space activation/
        # bootstrap) may reseed or clear it. This traces that a routine
        # refresh (simulated here as simply NOT calling
        # bindLidMemoryForDesign - exactly what syncForm() now does) leaves
        # memory untouched, while an explicit bind reseeds/clears it.
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required for this browser-state regression")
        source = (Path(__file__).resolve().parent / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index("const LID_DEFAULTS = {")
        end = source.index("function applyDivisionGridLayout(")
        lid_helpers = source[start:end]
        rs_start = source.index("function readStackForm(design) {")
        rs_end = source.index("\n}\n", rs_start) + 3
        read_stack_form = source[rs_start:rs_end]

        # syncForm() itself must contain no lidMemory assignment: Correction 3
        # moved every reseed/clear to the explicit bindLidMemoryForDesign()
        # call sites below, never to the routine full-form refresh itself.
        sync_form_start = source.index("function syncForm() {")
        sync_form_end = source.index("\nfunction ", sync_form_start + 1)
        self.assertNotIn("state.lidMemory =", source[sync_form_start:sync_form_end])
        self.assertIn("function bindLidMemoryForDesign(design = state.design) {\n"
                       "  state.lidMemory = rememberedLidSnapshot(design);\n}", source)

        # Every real design-replacement call site classified for this
        # correction explicitly reseeds/clears memory before syncForm() runs.
        replacement_sites = [
            ("function loadFreshOrdinaryDesignForCurrentFolder() {", "web/app.js: New Bin / Space activation starter"),
            ("async function installLoadedDesignSource(", "web/app.js: Inventory Edit / Duplicate (typed Space)"),
            ("async function designerDuplicate() {", "web/app.js: Duplicate (ordinary Designer)"),
            ("async function restoreHistory(", "web/app.js: Undo/Redo"),
            ("async function newDesign() {", "web/app.js: New (ordinary Designer)"),
            ("async function init() {", "web/app.js: app bootstrap"),
        ]
        def next_boundary(text, after):
            candidates = [i for i in (text.find("\nasync function ", after), text.find("\nfunction ", after)) if i != -1]
            return min(candidates) if candidates else len(text)

        for needle, label in replacement_sites:
            fn_start = source.index(needle)
            fn_end = next_boundary(source, fn_start + 1)
            self.assertIn("bindLidMemoryForDesign()", source[fn_start:fn_end], label)
        spaces_js = (Path(__file__).resolve().parent / "web" / "spaces.js").read_text(encoding="utf-8")
        init_space_start = spaces_js.index("SP.initializeDesignForActiveSpace = async () => {")
        init_space_end = spaces_js.index("\n};", init_space_start)
        self.assertIn("bindLidMemoryForDesign()", spaces_js[init_space_start:init_space_end],
                       "web/spaces.js: typed Space activation/resume")

        # Also find the Open-from-file handler (an anonymous/local function,
        # not matched by name above) and confirm it binds too.
        open_start = source.index('"A Storage Box or Base Trim is saved from its Space, not opened in the Designer."')
        open_end = source.index("toast(`Opened", open_start)
        self.assertIn("bindLidMemoryForDesign()", source[open_start:open_end], "web/app.js: Open from file")

        script = "\n".join([
            "const state = { design: null, lidMemory: null };",
            "const fields = {",
            "  '#lid-configuration': 'handled_lid', '#lid-thickness': 'thin',",
            "  '#lid-handle-type': 'knob', '#lid-handle-size': 'medium', '#lid-handle-position': 'middle',",
            "  '#lid-label-enabled': 'true', '#lid-label-orientation': 'horizontal',",
            "  '#lid-label-style': 'raised', '#lid-label-text': 'PARTS',",
            "};",
            "const $ = sel => ({ get value() { return fields[sel]; }, set value(v) { fields[sel] = v; } });",
            lid_helpers,
            read_stack_form,
            "function resyncFieldsFromLidState(design) {",
            "  const lid = lidState(design);",
            "  fields['#lid-thickness'] = lid.thickness;",
            "  fields['#lid-handle-type'] = lid.handle_type;",
            "  fields['#lid-handle-size'] = lid.handle_size;",
            "  fields['#lid-handle-position'] = lid.handle_position;",
            "  fields['#lid-label-enabled'] = String(Boolean(lid.label_enabled));",
            "  fields['#lid-label-orientation'] = lid.label_orientation;",
            "  fields['#lid-label-style'] = lid.label_style;",
            "  fields['#lid-label-text'] = lid.label_text || '';",
            "}",
            "function apply(design, configValue, styleValue) {",
            "  fields['#lid-configuration'] = configValue;",
            "  if (styleValue !== undefined) fields['#lid-label-style'] = styleValue;",
            "  readStackForm(design);",
            "  resyncFieldsFromLidState(design);",
            "  return design;",
            "}",
            # A routine same-design syncForm() refresh does nothing to
            # memory now - simulate it as a no-op, exactly what the real
            # syncForm() does after this correction.
            "function routineSyncFormRefresh() {}",
            "const steps = [];",
            # 1. Handled custom values -> Stackable Bin -> routine refresh -> Handled.
            "let design = { box: { lid: { ...LID_DEFAULTS, enabled: true } } };",
            "design = apply(design, 'handled_lid', 'raised');",
            "fields['#lid-handle-type'] = 'pull'; fields['#lid-thickness'] = 'thick';",
            "design = apply(design, 'handled_lid');",
            "design = apply(design, 'stackable_bin');",
            "routineSyncFormRefresh();",
            "routineSyncFormRefresh();",
            "design = apply(design, 'handled_lid');",
            "steps.push({ step: 'survives_routine_refresh_stackable_bin',",
            "  handleType: design.box.lid.handle_type, thickness: design.box.lid.thickness });",
            # 2. Handled Raised -> Stackable Lid -> routine refresh -> Handled.
            "design = apply(design, 'handled_lid', 'raised');",
            "design = apply(design, 'stackable_lid');",
            "const activeDuringStackableLid = design.box.lid.label_style;",
            "routineSyncFormRefresh();",
            "design = apply(design, 'handled_lid');",
            "steps.push({ step: 'survives_routine_refresh_stackable_lid',",
            "  activeDuringStackableLid, restoredStyle: design.box.lid.label_style });",
            # 3. A genuine design replacement with no lid clears memory.
            "state.design = design; bindLidMemoryForDesign(state.design);",
            "const noLidDesign = { box: {} };",
            "state.design = noLidDesign; bindLidMemoryForDesign(state.design);",
            "steps.push({ step: 'replacement_no_lid', memory: state.lidMemory });",
            # 4. A genuine design replacement with its own lid reseeds memory
            # from THAT design, not the previous one.
            "const otherDesign = { box: { lid: { ...LID_DEFAULTS, enabled: true, stackable: false,",
            "  handle_type: 'pull', thickness: 'thick', label_style: 'flush' } } };",
            "state.design = otherDesign; bindLidMemoryForDesign(state.design);",
            "steps.push({ step: 'replacement_with_lid',",
            "  handleType: state.lidMemory.handle_type, thickness: state.lidMemory.thickness,",
            "  labelStyle: state.lidMemory.label_style });",
            "process.stdout.write(JSON.stringify(steps));",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        steps = {entry["step"]: entry for entry in json.loads(done.stdout)}

        survived_bin = steps["survives_routine_refresh_stackable_bin"]
        self.assertEqual(survived_bin["handleType"], "pull")
        self.assertEqual(survived_bin["thickness"], "thick")
        survived_lid = steps["survives_routine_refresh_stackable_lid"]
        self.assertEqual(survived_lid["activeDuringStackableLid"], "flush")
        self.assertEqual(survived_lid["restoredStyle"], "raised")
        self.assertIsNone(steps["replacement_no_lid"]["memory"])
        replacement_with_lid = steps["replacement_with_lid"]
        self.assertEqual(replacement_with_lid["handleType"], "pull")
        self.assertEqual(replacement_with_lid["thickness"], "thick")
        self.assertEqual(replacement_with_lid["labelStyle"], "flush")


if __name__ == "__main__":
    unittest.main()
