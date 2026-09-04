"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from organizer_app import design_from_dict
from wavefinity_web import (
    apply_feature_payload,
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
            {"divider", "post", "pocket", "slot", "bore", "cradle", "nest"},
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
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"Build your bin", body)
        status, _headers, body = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertIn(b"refreshPreview", body)
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


if __name__ == "__main__":
    unittest.main()
