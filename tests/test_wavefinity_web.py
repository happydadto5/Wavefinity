"""Contract tests for the local Wavefinity browser application."""

from __future__ import annotations

import inspect
import hashlib
import json
import math
import os
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

from space_source import app_source, spaces_source
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


class RuntimeIdentityTests(unittest.TestCase):
    def test_fingerprint_missing_marker_and_health_address_boundary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "web").mkdir()
            (root / "web" / "app.js").write_bytes(b"first source")
            first = wavefinity_web.source_fingerprint(root)
            self.assertEqual(first, wavefinity_web.source_fingerprint(root))
            digest = hashlib.sha256()
            for relative in wavefinity_web.SOURCE_FILES:
                path = root / relative
                digest.update(relative.encode("utf-8") + b"\0")
                digest.update(b"<present>" + path.read_bytes() if path.is_file() else b"<missing>")
                digest.update(b"\0")
            self.assertEqual(first, digest.hexdigest()[:12])
            (root / "web" / "app.js").unlink()
            self.assertNotEqual(first, wavefinity_web.source_fingerprint(root))
        local = wavefinity_web.health_payload("127.0.0.1", hosted=False)
        self.assertEqual(local["source_root"], str(wavefinity_web.APP_DIR.resolve()))
        self.assertEqual(local["source_fingerprint"], wavefinity_web.SOURCE_FINGERPRINT)
        self.assertIn("source_root", wavefinity_web.health_payload("::1", hosted=False))
        self.assertNotIn("source_root", wavefinity_web.health_payload("192.0.2.1", hosted=False))
        self.assertNotIn("source_root", wavefinity_web.health_payload("127.0.0.1", hosted=True))


class FirstBinCapabilityTests(unittest.TestCase):
    def test_edit_capability_depends_on_source_not_row_position(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable")
        script = r"""
          const fs = require('fs');
          const vm = require('vm');
          const source = fs.readFileSync('web/drawer-panel.js', 'utf8');
          const fn = source.match(/DP\.editableSourceFor = one => \{[\s\S]*?\n\};/)[0];
          const context = { DP: {}, DL: { layout: { design_specs: {
            first: { part_name: 'First' }, later: { part_name: 'Later' },
            structural: { structural: true }
          } } }, isStructuralDesign: spec => Boolean(spec.structural) };
          vm.runInNewContext(fn, context);
          const rows = ['first', 'later', 'missing', 'structural'].map(id =>
            context.DP.editableSourceFor({ id, kind: 'bin' }));
          rows.push(context.DP.editableSourceFor({ id: 'first', kind: 'manual' }));
          process.stdout.write(JSON.stringify(rows));
        """
        result = subprocess.run(
            [node, "-e", script], cwd=ROOT,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [True, True, False, False, False])


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

    def test_invalid_1u_side_selection_is_rejected(self):
        design = default_design()
        design["box"]["x"] = 7.0
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


    def test_connector_payload_rejects_base_trim_design_not_join_preference(self):
        with self.assertRaises(ValueError) as ctx:
            wavefinity_web.connector_payload({"design": {"design_kind": "base_trim"}})
        self.assertIn("Base Trim", str(ctx.exception))

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

    def _sized_bore(self, design, **options):
        feature = default_feature_payload({
            "design": design, "kind": "bore",
            "item": {"name": "tube", "profile": "round", "clearance": 0.25,
                     "segments": [{"length": 40.0, "diameter": 20.0}]},
        })["feature"]
        feature["options"] = {"height": 20.0, "depth": 14.0, **options}
        return feature

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

    def _print_setup(self, temp_dir):
        fake_exe = Path(temp_dir) / "bambu-studio.exe"
        fake_exe.touch()
        box = Path(temp_dir) / "Box.3mf"
        box.write_bytes(b"3mf")  # the print path refuses missing or empty files
        connector = Path(temp_dir) / "Connector.3mf"
        connector.write_bytes(b"3mf")
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
                patch.object(wavefinity_web, "print_file_fit_issues", return_value=[]),
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
                patch.object(wavefinity_web, "print_file_fit_issues", return_value=[]),
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

    def test_print_payload_raises_when_no_slicer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake_3mf = Path(temp_dir) / "Box.3mf"
            fake_3mf.write_bytes(b"3mf")
            fake_gen_result = {
                "result": {"box": {"output": str(fake_3mf)}},
                "output": str(temp_dir),
            }

            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake_gen_result),
                patch.object(wavefinity_web, "connector_payload", return_value={"result": {}, "output": str(temp_dir)}),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=None),
                patch.object(wavefinity_web, "print_file_fit_issues", return_value=[]),
            ):
                with self.assertRaises(ValueError) as ctx:
                    wavefinity_web.print_payload({
                        "design": default_design(),
                        "output": temp_dir,
                    })
                self.assertIn("A slicer was not found", str(ctx.exception))


    def test_typed_space_print_handoff_does_not_append_another_row(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            slicer = Path(temp_dir) / "bambu-studio.exe"
            slicer.touch()
            bin_file = Path(temp_dir) / "A.3mf"
            bin_file.write_bytes(b"3mf")
            fake = {"result": {"box": {"output": str(bin_file)}}, "output": temp_dir}
            with (
                patch.object(wavefinity_web, "generate_payload", return_value=fake),
                patch.object(wavefinity_web, "connector_payload", return_value={"result": {}, "output": temp_dir}),
                patch.object(wavefinity_web, "detect_bambu_studio", return_value=slicer),
                patch.object(wavefinity_web, "print_file_fit_issues", return_value=[]),
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


    def test_hosted_inventory_writes_share_one_file_queue(self):
        source = spaces_source(ROOT / "web")
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
        source = spaces_source(ROOT / "web")
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
            "const DP = {};",
            owner,
            "(async()=>{await SP.initializeDesignForActiveSpace();",
            "process.stdout.write(JSON.stringify(state.designInventoryId));})();",
        ])
        self.assertEqual(self._run_node(script), "B2")

    def _app_js_functions(self, *names):
        source = app_source(ROOT / "web")
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


    def test_current_design_position_does_not_leak_between_spaces(self):
        # The session-only Current-design position is gone with the shadow
        # owner; nothing about an unplaced bin is kept as coordinates.
        model = (ROOT / "web" / "drawer-model.js").read_text(encoding="utf-8")
        for name in ("workingFit", "moveWorkingTo", "workingContext", "fitStamp"):
            self.assertNotIn(name, model)


    def test_inventory_preview_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            wavefinity_web.inventory_preview_payload({"design": default_design(), "output": directory})
            self.assertEqual(os.listdir(directory), [])

    # ------------------------------------------------------------ Fix 019


    def test_drawer_save_reports_success_or_failure(self):
        # Item 2's implementation detail: DL.save() must let callers know
        # whether persistence actually succeeded.
        node = self._node_or_skip()
        model = ROOT / "web" / "drawer-model.js"
        script = """
const vm = require("vm"), fs = require("fs");
let shouldFail = false;
const ctx = {
  debounce: f => f, console, Math, JSON, Number, Set, Map, setTimeout, clearTimeout,
  state: { runtime: { hosted: false }, output: "out" },
  toast: () => {}, friendlyError: e => String((e && e.message) || e),
  api: async () => { if (shouldFail) throw new Error("boom"); return {}; },
};
ctx.apiSideEffect = (...args) => ctx.api(...args);
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
        model = ROOT / "web" / "drawer-model.js"
        script = """
const vm = require("vm"), fs = require("fs");
function makeCtx() {
  const calls = [];
  const pending = [];
  const ctx = {
    debounce: f => f, console, Math, JSON, Number, Set, Map, Promise, setTimeout, clearTimeout, setImmediate,
    state: { runtime: { hosted: false }, output: "out" },
    toast: () => {}, friendlyError: e => String((e && e.message) || e),
    api: async () => {
      calls.push(1);
      return new Promise((resolve, reject) => { pending.push({ resolve, reject }); });
    },
  };
  ctx.apiSideEffect = (...args) => ctx.api(...args);
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
        root = ROOT / "web"
        spaces_js = spaces_source(root)

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

    def test_ai_candidate_rejects_more_than_one_rim_text(self):
        # Fix 078: at most one rim Text feature total, even on different sides.
        base = wavefinity_web._ai_example_base()
        base["part_name"] = "Test Bin"
        base["layout"]["features"] = [
            {"kind": "text", "zone": [-20, 6, 20, 15], "options": {"text": "A", "level": "rim", "rim_side": "back"}},
            {"kind": "text", "zone": [-20, -15, 20, -6], "options": {"text": "B", "level": "rim", "rim_side": "front"}},
        ]
        with self.assertRaisesRegex(ValueError, "one rim Label"):
            wavefinity_web.ai_candidate_payload({"design": base})

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


class Fix1069StorageBoxGenerateBlockTests(unittest.TestCase):
    def _ctx(self, z, headroom=1.0, kind="box", stack=None):
        from organizer_engine import BoxSpec
        from organizer_inserts import Layout
        box = BoxSpec(48, 48, z) if stack is None else BoxSpec(48, 48, z, stack=stack)
        space = {"kind": kind, "z": 40, "storage_box": {"lid_headroom_mm": headroom}}
        return space, box, Layout()

    def _block(self, space, box, layout):
        return wavefinity_web._block_storage_box_overheight(space, box, layout, None, "t", None)

    def test_uncomputable_envelope_fails_closed(self):
        # G2M-0320: a Storage Box payload whose physical envelope cannot be
        # computed blocks generation instead of slipping through.
        from organizer_engine import BoxSpec
        from organizer_inserts import Layout
        space = {"kind": "box", "z": 40, "storage_box": {"lid_headroom_mm": 1.0}}
        with self.assertRaises(ValueError) as ctx:
            wavefinity_web._block_storage_box_overheight(
                space, "not-a-box", Layout(), None, "t", None)
        self.assertIn("Cannot verify", str(ctx.exception))


class AutocompleteSuppressionTests(unittest.TestCase):
    """Fix 1121: browser autocomplete suppression via shared helper."""

    HELPER_START = "const AUTOCOMPLETE_SUPPRESS_SELECTOR"
    HELPER_END = "// Run on initial load"

    def _helper_block(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        start = source.index(self.HELPER_START)
        block = source[start:source.index(self.HELPER_END, start)]
        self.assertIn("function suppressBrowserAutocomplete(root)", block)
        return block

    def test_helper_selector_covers_text_number_textarea(self):
        block = self._helper_block()
        for token in ('input[type="text"]', 'input[type="number"]', "input:not([type])", "textarea"):
            self.assertIn(token, block)

    def test_observer_wraps_helper_call(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        self.assertIn("new MutationObserver(() => suppressBrowserAutocomplete())", source)

    def test_space_form_carries_autocomplete_off(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        match = re.search(r'<form[^>]*id="space-form"[^>]*>', html)
        self.assertIsNotNone(match)
        self.assertIn('autocomplete="off"', match.group(0))

    def test_helper_sets_off_on_eligible_and_respects_opt_out(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js unavailable")
        block = self._helper_block()
        harness = r"""
const log = [];
function makeEl(tag, typeAttr, existing) {
  const attrs = {};
  if (existing !== undefined) attrs.autocomplete = existing;
  const el = {
    tagName: tag.toUpperCase(),
    typeAttr: typeAttr,
    hasAttribute: (n) => n === "type" ? typeAttr !== null
      : Object.prototype.hasOwnProperty.call(attrs, n),
    setAttribute: (n, v) => {
      attrs[n] = v;
      log.push(tag + ":" + (typeAttr === null ? "(none)" : typeAttr) + ":" + n + "=" + v);
    },
    matches: (sel) => selMatch(el, sel),
    querySelectorAll: (sel) => [],
  };
  return el;
}
// Minimal emulation of the exact selector grammar in
// AUTOCOMPLETE_SUPPRESS_SELECTOR (pinned by the static token test above).
function selMatch(el, selector) {
  return selector.split(",").map((s) => s.trim()).some((part) => {
    if (part === "textarea") return el.tagName === "TEXTAREA";
    const m = part.match(/^input(\[type="([^"]+)"\]|:not\(\[type\]\))?$/);
    if (!m || el.tagName !== "INPUT") return false;
    if (m[1] === ":not([type])") return el.typeAttr === null;
    if (m[2]) return el.typeAttr === m[2];
    return true;
  });
}
const document = { querySelectorAll: (sel) => docEls.filter((el) => selMatch(el, sel)) };
const els = [
  makeEl("input", "text"),        // eligible
  makeEl("input", "number"),      // eligible
  makeEl("input", null),          // eligible (typeless input defaults to text)
  makeEl("textarea", null),       // eligible
  makeEl("input", "checkbox"),    // excluded
  makeEl("input", "radio"),       // excluded
  makeEl("input", "range"),       // excluded
  makeEl("input", "file"),        // excluded
  makeEl("input", "button"),      // excluded
  makeEl("select", null),         // excluded
  makeEl("input", "text", "on"),  // opt-out: existing attribute must be kept
];
const container = { querySelectorAll: (sel) => els.filter((el) => selMatch(el, sel)) };
suppressBrowserAutocomplete(container);   // container-root path
const solo = makeEl("input", "text");
suppressBrowserAutocomplete(solo);        // self-root path (matches() on the root itself)
const docEls = [makeEl("input", "number")];
suppressBrowserAutocomplete();            // default path (document)
process.stdout.write(JSON.stringify(log));
"""
        result = subprocess.run(
            [node, "-e", block + "\n" + harness], cwd=ROOT,
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(result.stdout), [
            "input:text:autocomplete=off",
            "input:number:autocomplete=off",
            "input:(none):autocomplete=off",
            "textarea:(none):autocomplete=off",
            "input:text:autocomplete=off",
            "input:number:autocomplete=off",
        ])


if __name__ == "__main__":
    unittest.main()
