"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen, Request

import wavefinity_web
from organizer_app import design_from_dict
from organizer_inserts import layout_zone
from wavefinity_web import (
    apply_feature_payload,
    auto_size_payload,
    catalog_payload,
    default_design,
    default_feature_payload,
    delete_feature_payload,
    draft_payload,
    make_server,
    mode_payload,
    preview_payload,
)


class WebApplicationTests(unittest.TestCase):
    def test_catalog_exposes_every_support_and_safe_default_design(self):
        catalog = catalog_payload()
        self.assertEqual(
            {part["kind"] for part in catalog["parts"]},
            {"divider", "post", "pocket", "bore", "cradle", "nest"},
        )
        box, layout, *_ = design_from_dict(catalog["defaults"]["design"])
        self.assertEqual((box.x, box.y, box.z), (16.0, 48.0, 40.0))
        self.assertEqual(layout.mode, "fused")

    def test_default_draft_changes_real_geometry_when_height_changes(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        low = draft_payload({"design": design, "feature": feature})
        low_top = max(point[2] for face in low["geometry"] for point in face["points"])
        feature["options"]["height"] = 18.0
        high = draft_payload({"design": design, "feature": feature})
        high_top = max(point[2] for face in high["geometry"] for point in face["points"])
        self.assertGreater(high_top, low_top + 4.0)

    def test_resolved_defaults_are_display_only_until_the_user_edits_them(self):
        design = default_design()
        item = {
            "name": "test tool",
            "profile": "round",
            "clearance": 0.4,
            "segments": [{"length": 8.0, "diameter": 6.0}],
        }
        response = default_feature_payload({
            "design": design, "kind": "nest", "item": item,
        })
        feature = response["feature"]
        self.assertEqual(feature["options"], {})
        self.assertEqual(
            set(response["resolved_options"]), {"wall", "depth", "height"}
        )

        applied = apply_feature_payload({
            "design": design, "feature": feature, "index": None,
        })
        stored = applied["design"]["layout"]["features"][0]
        self.assertEqual(stored["options"], {})

        # Enlarge the zone so a thicker tool still fits, then prove the
        # automatic depth and height follow it without becoming stored values.
        feature["zone"][1], feature["zone"][3] = -8.0, 8.0
        feature["item"]["segments"][0]["diameter"] = 8.0
        changed = draft_payload({"design": design, "feature": feature})
        self.assertGreater(
            changed["resolved_options"]["depth"],
            response["resolved_options"]["depth"],
        )
        self.assertEqual(changed["feature"]["options"], {})

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

    def test_fit_to_bin_grows_a_divider_only_along_its_run_axis(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        cross = feature["zone"][3] - feature["zone"][1]
        feature["zone"] = [-2.0, feature["zone"][1], 2.0, feature["zone"][3]]
        grown = auto_size_payload({
            "design": design, "feature": feature, "index": None,
        })["feature"]
        box, layout, *_ = design_from_dict(design)
        whole = layout_zone(box, layout.mode)
        self.assertGreater(grown["zone"][2] - grown["zone"][0], 4.0)
        self.assertLessEqual(grown["zone"][2] - grown["zone"][0], whole.width + 1e-6)
        self.assertAlmostEqual(grown["zone"][3] - grown["zone"][1], cross, delta=0.05)

    def test_fit_to_bin_stops_short_of_a_neighbouring_support(self):
        design = default_design()
        neighbour = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        neighbour["zone"] = [3.0, -1.0, 6.0, 1.0]
        placed = apply_feature_payload({"design": design, "feature": neighbour, "index": None})
        design = placed["design"]
        divider = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        divider["zone"] = [-2.0, -1.0, 2.0, 1.0]
        grown = auto_size_payload({
            "design": design, "feature": divider, "index": None,
        })["feature"]
        self.assertLess(grown["zone"][2], 3.0)

    def test_fit_to_bin_leaves_count_and_the_run_direction_untouched(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "divider"})["feature"]
        feature["zone"] = [-2.0, feature["zone"][1], 2.0, feature["zone"][3]]
        feature["count"] = 3
        grown = auto_size_payload({
            "design": design, "feature": feature, "index": None,
        })["feature"]
        self.assertEqual(grown["count"], 3)
        self.assertEqual(grown["along"], "x")

    def test_fit_to_bin_is_refused_for_a_kind_other_than_divider(self):
        design = default_design()
        feature = default_feature_payload({"design": design, "kind": "pocket"})["feature"]
        with self.assertRaises(ValueError):
            auto_size_payload({"design": design, "feature": feature, "index": None})

    def test_mode_conversion_preserves_valid_layout(self):
        design = default_design()
        converted = mode_payload({"design": design, "mode": "separate"})["design"]
        self.assertEqual(converted["layout"]["mode"], "separate")
        preview = preview_payload(converted)
        self.assertTrue(preview["geometry"])
        self.assertEqual(preview["design"]["layout"]["mode"], "separate")

    def test_preview_returns_camera_independent_geometry_and_uniform_bounds(self):
        preview = preview_payload(default_design())
        self.assertTrue(preview["geometry"])
        self.assertIn("normal", preview["geometry"][0])
        x0, y0, x1, y1 = preview["layout_bounds"]
        self.assertGreater(x1, x0)
        self.assertGreater(y1, y0)
        self.assertIn("inside", preview["dimensions"]["x"])


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
        self.assertTrue(json.loads(body)["ok"])
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Build your bin", body)
        self.assertIn(b"Advanced bin settings", body)
        self.assertIn(b"Label your bin", body)
        self.assertIn(b"Fused", body)
        status, _headers, body = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"refreshPreview", body)
        self.assertIn(b"designMutationBusy", body)
        self.assertIn(b"beginDesignMutation", body)
        self.assertIn(b"finishDesignMutation", body)
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

        replaced = wavefinity_web._replace_stale_process(f"http://127.0.0.1:{port}/")
        self.assertTrue(replaced)
        self.assertIsNotNone(proc.wait(timeout=5))  # actually terminated, not just unresponsive

        fresh = wavefinity_web.make_server("127.0.0.1", port)  # the port is genuinely free again
        fresh.server_close()

    def test_a_service_with_no_recorded_pid_is_left_running(self):
        # a health-check that succeeds with no PID file on record - an
        # older server predating this feature, or an unrelated program -
        # must never be touched
        server = wavefinity_web.make_server("127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            self.assertFalse(self.pid_file.exists())
            replaced = wavefinity_web._replace_stale_process(f"http://127.0.0.1:{port}/")
            self.assertFalse(replaced)
            with urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                self.assertTrue(json.loads(response.read())["ok"])
        finally:
            server.shutdown()
            server.server_close()

    def test_nothing_answering_the_port_is_reported_as_not_replaced(self):
        port = _free_port()
        self.pid_file.write_text("999999", encoding="utf-8")
        replaced = wavefinity_web._replace_stale_process(f"http://127.0.0.1:{port}/")
        self.assertFalse(replaced)


if __name__ == "__main__":
    unittest.main()
