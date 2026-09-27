"""Fix 053: Space preference memory, exact bin autosave and Parts UI cleanup."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from organizer_spaces import FolderMetadataError
from test_space_identity import make_routes, make_v4_space, meta

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
SPACES_JS = (WEB / "spaces.js").read_text(encoding="utf-8")

PREFERENCE_MARKER = "// ------------------------------------------------ Space preference memory (Fix 053)"


def function_source(name: str, source: str = APP_JS) -> str:
    start = source.index(f"function {name}(")
    if source[max(0, start - 6):start] == "async ":
        start -= 6
    return source[start:source.index("\n}\n", start) + 3]


def block(start_marker: str, end_marker: str, source: str = APP_JS) -> str:
    start = source.index(start_marker)
    return source[start:source.index(end_marker, start)]


PRELUDE = "\n".join([
    "const clone = v => JSON.parse(JSON.stringify(v));",
    "const plainObject = v => Boolean(v) && typeof v === 'object' && !Array.isArray(v);",
    "const number = (v, f = 0) => { const n = Number(v); return Number.isFinite(n) ? n : f; };",
    "const partInfo = () => ({ flags: {} });",
    "const toasts = []; const toast = (...a) => toasts.push(a);",
    "const queued = []; const SP = { queueDefaults: c => queued.push(clone(c)) };",
    "const state = { folderMode: 'space', activeSpace: { kind: 'drawer', x: 320, y: 240, z: 55 },",
    "  spaceBinDefaults: null, spacePartDefaults: {} };",
    block("const BOX_MODIFIER_KINDS", "]);\n") + "]);",
    function_source("modifierIsActive"),
    function_source("isStructuralDesign"),
    block(PREFERENCE_MARKER, "function drawerHardClearance() {"),
])

BIN = {
    "version": 6,
    "box": {
        "x": 32, "y": 32, "z": 40, "wall": 1.2, "base_thickness": 0.6, "corner_fillet": 1,
        "flat_inside": False, "standard_base": True, "standard_walls": False,
    },
    "label": "Rim text", "label_position": "bottom", "scoop": True, "part_name": "My named bin",
    "layout": {
        "version": 1, "mode": "removable", "snap": 1, "object_height_mm": 25,
        "surface_base_mode": "custom", "surface_lightweight_base": False, "features": [],
    },
}


def node_run(script: str):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("Node.js is required for this browser-state regression")
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
            handle.write(script)
            path = handle.name
        done = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
        if done.returncode != 0:
            raise AssertionError(done.stderr)
        return json.loads(done.stdout)
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


def js(template: str, **values) -> str:
    for key, value in values.items():
        template = template.replace(f"__{key}__", json.dumps(value))
    return template


class SpacePreferenceSeedTests(unittest.TestCase):
    def test_edge_mount_settings_are_remembered_without_presence_or_text(self):
        design = json.loads(json.dumps(BIN))
        design["box"]["edge_mount"] = {
            "side": "front", "label_enabled": True, "label_text": "SECRET", "label_type": "separate",
            "label_projection_mm": 30, "label_thickness_mm": 3.7, "holes_enabled": False,
            "screw_diameter_mm": 4,
        }
        previous = json.loads(json.dumps(BIN))
        out = node_run(PRELUDE + js("""
const design = __DESIGN__; const previous = __PREVIOUS__;
rememberSpacePreferences(design, previous);
const seed = spaceModifierDefaults('edge_mount');
process.stdout.write(JSON.stringify({ queued, seed, bin: state.spaceBinDefaults }));
""", DESIGN=design, PREVIOUS=previous))
        settings = out["queued"][0]["part_defaults"]["edge_mount"]["settings"]
        self.assertEqual(settings["label_thickness_mm"], 3.7)
        self.assertEqual(settings["label_text"], "")
        self.assertNotIn("label_enabled", settings)
        self.assertNotIn("holes_enabled", settings)
        self.assertEqual(out["seed"]["label_thickness_mm"], 3.7)
        self.assertEqual(out["seed"]["label_text"], "")
        bin_defaults = out["bin"]
        self.assertNotIn("edge_mount", bin_defaults["box"])
        self.assertEqual(bin_defaults["part_name"], "")
        self.assertEqual(bin_defaults["label"], "")
        self.assertEqual(bin_defaults["layout"]["features"], [])
        self.assertEqual(bin_defaults["box"]["x"], 32)
        self.assertEqual(bin_defaults["box"]["wall"], 1.2)

    def test_unchanged_modifier_of_an_old_bin_does_not_replace_newer_preferences(self):
        design = json.loads(json.dumps(BIN))
        design["box"]["edge_mount"] = {
            "side": "front", "label_enabled": True, "label_text": "", "label_thickness_mm": 2.0,
        }
        out = node_run(PRELUDE + js("""
state.spacePartDefaults = { edge_mount: { kind: 'edge_mount', settings: { label_thickness_mm: 3.7 } } };
const design = __DESIGN__;
rememberSpacePreferences(design, clone(design));
process.stdout.write(JSON.stringify({ parts: state.spacePartDefaults }));
""", DESIGN=design))
        self.assertEqual(out["parts"]["edge_mount"]["settings"]["label_thickness_mm"], 3.7)

    def test_bore_settings_seed_a_new_bore_but_not_position_and_survive_deletion(self):
        design = json.loads(json.dumps(BIN))
        design["layout"]["features"] = [{
            "kind": "bore", "zone": [8, 8, 40, 40], "count": 3, "along": "x", "full_span": False,
            "options": {"diameter": 6, "height": 20, "wall": 1.4, "text": "x", "xy_size_mode": "manual"},
        }, {
            "kind": "text", "zone": [1, 1, 9, 9], "count": None, "along": "x", "full_span": False,
            "options": {"text": "HELLO", "font_size": 5},
        }]
        previous = json.loads(json.dumps(BIN))
        out = node_run(PRELUDE + js("""
const design = __DESIGN__; const previous = __PREVIOUS__;
rememberSpacePreferences(design, previous);
const entry = state.spacePartDefaults.bore;
const seeded = seedFeatureFromPartDefaults(
  { kind: 'bore', zone: [0, 0, 10, 10], options: { diameter: 3 } }, entry);
const withoutBore = clone(design); withoutBore.layout.features = [];
rememberSpacePreferences(withoutBore, design);
process.stdout.write(JSON.stringify({
  entry, seeded, text: state.spacePartDefaults.text, kept: state.spacePartDefaults.bore,
  bin: state.spaceBinDefaults }));
""", DESIGN=design, PREVIOUS=previous))
        self.assertEqual(out["entry"]["zone_size"], [32, 32])
        self.assertEqual(out["entry"]["options"]["diameter"], 6)
        self.assertNotIn("text", out["entry"]["options"])
        self.assertEqual(out["seeded"]["options"]["diameter"], 6)
        self.assertEqual(out["seeded"]["options"]["height"], 20)
        self.assertEqual(out["seeded"]["count"], 3)
        self.assertEqual(out["seeded"]["zone"], [-11, -11, 21, 21])
        self.assertNotIn("text", out["text"]["options"])
        self.assertEqual(out["text"]["options"]["font_size"], 5)
        self.assertEqual(out["kept"], out["entry"])
        self.assertEqual(out["bin"]["layout"]["features"], [])


    def test_lid_labels_and_division_text_are_not_seeded(self):
        design = json.loads(json.dumps(BIN))
        design["box"]["lid"] = {
            "enabled": True, "stackable": True, "thickness": "thick", "label_enabled": True,
            "label_style": "flush", "label_orientation": "vertical", "label_text": "Screws",
            "division_labels": ["A", "B"], "handle_type": "knob", "handle_size": "large",
            "handle_position": "middle",
        }
        out = node_run(PRELUDE + js("""
rememberSpacePreferences(__DESIGN__, __PREVIOUS__);
process.stdout.write(JSON.stringify({ seed: spaceModifierDefaults('lid_stacking'), bin: state.spaceBinDefaults }));
""", DESIGN=design, PREVIOUS=BIN))
        lid = out["seed"]["lid"]
        self.assertEqual(lid["label_text"], "")
        self.assertEqual(lid["division_labels"], [])
        self.assertEqual(lid["thickness"], "thick")
        self.assertEqual(lid["handle_size"], "large")
        self.assertNotIn("lid", out["bin"]["box"])
        self.assertNotIn("stack", out["bin"]["box"])

    def test_legacy_defaults_cannot_add_parts_modifiers_or_text(self):
        legacy_bin = json.loads(json.dumps(BIN))
        legacy_bin["box"]["edge_mount"] = {
            "label_enabled": True, "label_text": "Old label", "label_thickness_mm": 2.5, "side": "left",
        }
        legacy_bin["box"]["lid"] = {"enabled": True, "label_text": "Old lid", "thickness": "thin"}
        legacy_bin["layout"]["features"] = [{"kind": "bore", "zone": [0, 0, 9, 9], "options": {}}]
        legacy_parts = {"bore": {
            "kind": "bore", "zone_size": [10, 10], "count": 2, "enabled": True,
            "options": {"text": "stale", "diameter": 5}, "features": [{"kind": "post"}],
            "item": {
                "name": "Grandma's chisel", "segments": [{"length": 40, "diameter": 6}],
                "profile": "round", "clearance": 0.3,
            },
        }}
        out = node_run(PRELUDE + js("""
state.spaceBinDefaults = __LEGACY__; state.spacePartDefaults = __PARTS__;
const preferences = spaceBinPreferences();
const seeded = seedFeatureFromPartDefaults(
  { kind: 'bore', zone: [0, 0, 20, 20], options: {} }, state.spacePartDefaults.bore);
process.stdout.write(JSON.stringify({
  preferences, edge: spaceModifierDefaults('edge_mount'), seeded,
  cleaned: cleanedSpacePartDefaults(state.spacePartDefaults) }));
""", LEGACY=legacy_bin, PARTS=legacy_parts))
        preferences = out["preferences"]
        self.assertNotIn("features", preferences["layout"])
        self.assertNotIn("edge_mount", preferences["box"])
        self.assertNotIn("lid", preferences["box"])
        self.assertNotIn("part_name", preferences)
        self.assertEqual(preferences["box"]["wall"], 1.2)
        self.assertEqual(out["edge"]["label_text"], "")
        self.assertEqual(out["edge"]["label_thickness_mm"], 2.5)
        self.assertNotIn("label_enabled", out["edge"])
        self.assertEqual(out["seeded"]["options"], {"diameter": 5})
        # The old user's item name is neutralized; its measurements survive.
        self.assertEqual(out["seeded"]["item"]["name"], "Custom item")
        self.assertEqual(out["seeded"]["item"]["segments"], [{"length": 40, "diameter": 6}])
        self.assertEqual(out["seeded"]["item"]["clearance"], 0.3)
        self.assertEqual(out["cleaned"]["bore"]["item"]["name"], "Custom item")
        self.assertEqual(
            out["cleaned"]["bore"].keys() - {"kind", "zone_size", "options", "count", "item"}, set())



class SpaceSizingTests(unittest.TestCase):
    SCRIPT = "\n".join([
        PRELUDE,
        function_source("drawerHardClearance"),
        function_source("drawerSpaceCapacity"),
        function_source("normalizeBinDimension"),
        function_source("snapToUnit"),
        function_source("isSurfaceBinDesign"),
        function_source("applySpaceSizingDefaults"),
        function_source("freshDesignForCurrentFolder"),
        "const baseTrimEnabled = () => false;",
        """
state.catalog = {
  base_unit: 8, max_box_size: 350, drawer_rules: { hard_wall_clearance_mm: 0 },
  min_height_above_base_mm: 5, base_rules: { default_mm: 0.6 },
  defaults: { design: {
    version: 1,
    box: { x: 32, y: 32, z: 40, wall: 0.8, base_thickness: 0.6, corner_fillet: 0, flat_inside: false,
           standard_base: true, standard_walls: true },
    label: '', label_position: 'bottom', scoop: false, part_name: '',
    layout: { version: 1, mode: 'fused', snap: 1, object_height_mm: null,
              surface_base_mode: 'custom', surface_lightweight_base: false, features: [] } } },
};
state.design = { box: { base_thickness: 0.6 } };
""",
    ])

    def run_fresh(self, remembered):
        return node_run(self.SCRIPT + js("""
state.spaceBinDefaults = __REMEMBERED__;
process.stdout.write(JSON.stringify(freshDesignForCurrentFolder()));
""", REMEMBERED=remembered))

    def test_new_bin_inherits_bin_settings_but_not_composition_or_text(self):
        remembered = json.loads(json.dumps(BIN))
        remembered["box"].update({"x": 64, "y": 48, "z": 40})
        remembered["box"]["edge_mount"] = {"label_enabled": True, "label_thickness_mm": 3.7}
        remembered["box"]["lid"] = {"enabled": True}
        remembered["layout"]["features"] = [{"kind": "bore", "zone": [0, 0, 9, 9], "options": {}}]
        design = self.run_fresh(remembered)
        self.assertEqual((design["box"]["x"], design["box"]["y"], design["box"]["z"]), (64, 48, 40))
        self.assertEqual(design["box"]["wall"], 1.2)
        self.assertFalse(design["box"]["standard_walls"])
        self.assertEqual(design["layout"]["mode"], "removable")
        self.assertEqual(design["layout"]["features"], [])
        self.assertNotIn("edge_mount", design["box"])
        self.assertNotIn("lid", design["box"])
        self.assertEqual(design["part_name"], "")
        self.assertEqual(design["label"], "")
        self.assertFalse(design["scoop"])

    def test_oversized_remembered_dimensions_are_clamped_by_the_space(self):
        remembered = json.loads(json.dumps(BIN))
        remembered["box"].update({"x": 800, "y": 800, "z": 900})
        design = self.run_fresh(remembered)
        self.assertEqual((design["box"]["x"], design["box"]["y"], design["box"]["z"]), (320, 240, 55))



class SpaceDefaultsWriterTests(unittest.TestCase):
    SCRIPT = "\n".join([
        "const clone = v => JSON.parse(JSON.stringify(v));",
        "const state = { folderMode: 'space', activeSpace: { name: 'A' }, activeSpaceId: 'S1',",
        "  output: '/a', browserFolder: { handle: 'H1' }, runtime: { hosted: false } };",
        "const toasts = []; const toast = (...a) => toasts.push(a);",
        "const calls = [];",
        "const api = async (path, payload) => { calls.push(['api', path, clone(payload)]);"
        " if (state.failApi) throw new Error('disk full'); };",
        "const SP = {",
        "  _captureResumeTarget: () => state.activeSpaceId ? {",
        "    spaceId: state.activeSpaceId, space: clone(state.activeSpace), output: state.output,",
        "    browserFolder: state.browserFolder, hosted: Boolean(state.runtime.hosted) } : null,",
        "  writeMetadata: async (...args) => { calls.push(['metadata', args[0], args[4], args[5]]); },",
        "};",
        SPACES_JS[
            SPACES_JS.index("SP._defaults = { chain"):
            SPACES_JS.index("SP.flushDefaults = () => SP._defaults.chain;")
        ] + "SP.flushDefaults = () => SP._defaults.chain;",
    ])

    def test_local_write_names_its_space_and_never_crosses_spaces(self):
        out = node_run(self.SCRIPT + """
(async () => {
  SP.queueDefaults({ bin_defaults: { a: 1 } });
  state.activeSpaceId = 'S2'; state.output = '/b';
  SP.queueDefaults({ part_defaults: { b: 2 } });
  await SP.flushDefaults();
  process.stdout.write(JSON.stringify({ calls }));
})();
""")
        self.assertEqual(out["calls"], [
            ["api", "/api/space/defaults", {"output": "/a", "space_id": "S1", "bin_defaults": {"a": 1}}],
            ["api", "/api/space/defaults", {"output": "/b", "space_id": "S2", "part_defaults": {"b": 2}}],
        ])

    def test_hosted_write_preserves_space_identity(self):
        out = node_run(self.SCRIPT + """
(async () => {
  state.runtime.hosted = true;
  SP.queueDefaults({ bin_defaults: { a: 1 }, part_defaults: { p: 1 } });
  await SP.flushDefaults();
  process.stdout.write(JSON.stringify({ calls }));
})();
""")
        self.assertEqual(out["calls"], [[
            "metadata", "H1", {"bin_defaults": {"a": 1}, "part_defaults": {"p": 1}},
            {"preserveSpace": True, "expectedSpaceId": "S1"},
        ]])



class SpaceDefaultsRouteTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.routes, _prefs = make_routes(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()





class ExactBinAutosaveTests(unittest.TestCase):


    def test_autosave_adoption_never_rewrites_unfinished_form_fields(self):
        persist = function_source("persistSpaceDesignSource")
        self.assertNotRegex(persist, r"(?m)^\s*syncForm\(\);\s*$")
        self.assertIn("rememberSpacePreferences(data.design, previousClean)", persist)
        flush = function_source("flushSpaceDesignAutosave")
        self.assertIn("await SP.flushDefaults()", flush)


if __name__ == "__main__":
    unittest.main()
