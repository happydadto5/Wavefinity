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
    make_server,
    mode_payload,
    photo_nest_payload,
    preview_payload,
)
from photo_nest import PhotoOutline


class WebApplicationTests(unittest.TestCase):
    def test_catalog_exposes_every_support_and_safe_default_design(self):
        catalog = catalog_payload()
        parts = {part["kind"]: part for part in catalog["parts"]}
        self.assertEqual(
            set(parts),
            {"divider", "post", "pocket", "bore", "cradle", "nest"},
        )
        self.assertTrue(parts["cradle"]["flags"]["alternate"])
        self.assertFalse(parts["nest"]["flags"]["alternate"])
        self.assertTrue(parts["nest"]["flags"]["photo"])
        self.assertEqual(parts["nest"]["title"], "Photo Nest")
        self.assertEqual(
            [field["label"] for field in parts["nest"]["fields"]],
            ["Fit clearance (mm)", "Soften outline (mm)"],
        )
        box, layout, *_ = design_from_dict(catalog["defaults"]["design"])
        self.assertEqual((box.x, box.y, box.z), (16.0, 48.0, 40.0))
        self.assertEqual(layout.mode, "fused")

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

    def test_default_draft_changes_real_geometry_when_height_changes(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        low = draft_payload({"design": design, "feature": feature})
        low_top = max(point[2] for face in low["geometry"] for point in face["points"])
        feature["options"]["height"] = 18.0
        high = draft_payload({"design": design, "feature": feature})
        high_top = max(point[2] for face in high["geometry"] for point in face["points"])
        self.assertGreater(high_top, low_top + 4.0)

    def test_photo_nest_defaults_have_only_the_three_new_measurements(self):
        design = default_design()
        response = default_feature_payload({
            "design": design, "kind": "nest",
        })
        feature = response["feature"]
        self.assertEqual(feature["options"], {})
        self.assertIsNone(feature["contour"])
        self.assertEqual(set(response["resolved_options"]), {"clearance", "depth", "rim", "smoothing"})

    def test_photo_upload_creates_one_contour_and_smallest_grid_bin(self):
        outline = PhotoOutline(
            ((-40, -10), (40, -10), (35, 10), (-40, 10)),
            80.0, 20.0, ((0, 0), (1, 0), (1, 1), (0, 1)),
        )
        with patch.object(wavefinity_web, "photo_outline_from_data", return_value=outline):
            result = photo_nest_payload({
                "design": default_design(), "image": "unused", "mime_type": "image/png",
                "options": {"clearance": 1.0, "depth": 9.0, "rim": 4.0},
            })
        design = result["design"]
        feature = design["layout"]["features"][0]
        self.assertEqual(len(design["layout"]["features"]), 1)
        self.assertEqual(feature["kind"], "nest")
        self.assertIsNone(feature["item"])
        self.assertEqual(feature["contour"], [list(point) for point in outline.contour])
        self.assertNotIn("image", json.dumps(design).lower())
        self.assertEqual(design["box"]["x"] % 8.0, 0.0)
        self.assertEqual(design["box"]["y"] % 8.0, 0.0)
        box, layout, *_ = design_from_dict(design)
        one = layout.features[0]
        if box.x > 8.0:
            narrower = type(box)(box.x - 8.0, box.y, box.z, box.wall,
                                 box.corner_fillet, box.flat_inside)
            with self.assertRaisesRegex(ValueError, "outside the bin"):
                layout.validate(narrower)
        if box.y > 8.0:
            shallower = type(box)(box.x, box.y - 8.0, box.z, box.wall,
                                  box.corner_fillet, box.flat_inside)
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
        self.assertTrue(any(face["kind"] == "feature_divider" for face in preview["geometry"]))
        self.assertTrue(any(face["kind"] == "draft_invalid" for face in preview["geometry"]))


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
        self.assertNotIn(b"Advanced bin settings", body)
        self.assertNotIn(b"Wall / floor", body)
        self.assertNotIn(b"Flat wall band", body)
        self.assertNotIn(b"Label your bin", body)
        self.assertIn(b"Label position", body)
        self.assertIn(b"Part Name (For file)", body)
        self.assertIn(b"Connect bins", body)
        self.assertIn(b"Generate STLs", body)
        self.assertIn(b"Different height bins?", body)
        self.assertIn(b"connector-bin-a-height", body)
        self.assertNotIn(b"connector-position", body)
        self.assertNotIn(b"connector-axis", body)
        self.assertIn(b"support-layout-dialog", body)
        self.assertNotIn(b"Center X", body)
        self.assertLess(body.index(b"Label position"), body.index(b"Add curved scoop"))
        self.assertLess(body.index(b"Add curved scoop"), body.index(b"Interior supports"))
        self.assertLess(body.index(b"Interior supports"), body.index(b"Connect bins"))
        self.assertLess(body.index(b"Connect bins"), body.index(b"Generate STLs"))
        self.assertLess(body.index(b"How should the interior print?"), body.index(b"Connect bins"))
        self.assertIn(b"Fused", body)
        status, _headers, body = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"refreshPreview", body)
        self.assertIn(b"designMutationBusy", body)
        self.assertIn(b"beginDesignMutation", body)
        self.assertIn(b"finishDesignMutation", body)
        self.assertIn(b"previewSupportPolygons", body)
        self.assertIn(b"Upload part photo", body)
        self.assertIn(b".jpg,.jpeg,.png,.webp", body)
        self.assertIn(b"Camera directly overhead", body)
        self.assertIn(b"syncNestZone", body)
        self.assertIn(b'"rotate"', body)
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
            patch.object(wavefinity_web.time, "sleep"),
        ):
            self.assertTrue(wavefinity_web._replace_stale_process(
                "http://127.0.0.1:8765/", "127.0.0.1", 8765
            ))
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
