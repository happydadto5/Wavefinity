"""Fix 114 targeted proof: usable height, Box fit by printed object, and the
static UI/guide truth that has no cheaper runtime mechanism. No browser."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organizer_engine.product_rules import STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
from space_source import app_source
from organizer_storage.drawers import (
    STORAGE_DRAWER_FIT_CHOICES, STORAGE_DRAWER_FIT_DEFAULT,
    new_drawer_descriptor, prepare_new_storage_drawers_definition,
    reset_storage_drawers_definition, storage_drawers_defaults,
)
from organizer_storage.drawer_geometry import storage_drawers_summary


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def cabinet(fit, height=20.0):
    return prepare_new_storage_drawers_definition({
        "kind": "storage_drawers", "name": "Proof", "x": 96, "y": 96,
        "storage_drawers": {"drawers": [{"height_mm": height}], "drawer_fit_mm": fit}})


class UsableHeightTests(unittest.TestCase):
    def test_defaults_publish_the_usable_default_under_standard_fit(self):
        defaults = storage_drawers_defaults()
        self.assertEqual(defaults["drawer_fit_mm"], STORAGE_DRAWER_FIT_DEFAULT)
        for row in defaults["drawers"]:
            self.assertAlmostEqual(row["height_mm"] + STORAGE_DRAWER_FIT_DEFAULT,
                                   STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM)
        self.assertAlmostEqual(new_drawer_descriptor()["height_mm"] + STORAGE_DRAWER_FIT_DEFAULT,
                               STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM)
        self.assertEqual(new_drawer_descriptor(33.0)["height_mm"], 33.0)

class UsableHeightStaticTests(unittest.TestCase):
    form = source("web/storage-drawers-form.js")

    def test_height_render_path_has_no_summary_basis_gate(self):
        self.assertNotRegex(self.form, r"\bbasis\b|rowBasis|checking…")
        self.assertIn("const usableOf = row => roundMm(row.height_mm + getDrawerFitMm());", self.form)
        self.assertNotIn("Math.max(wanted", self.form)
        self.assertNotIn("Math.round(wanted)", self.form)

    def test_defaults_and_fit_change_preserve_usable_height(self):
        self.assertIn("height_mm: rules.defaultHeight - rules.defaultFit", self.form)
        self.assertIn("rules.defaultHeight - Number(fit.value)", self.form)
        change = self.form[self.form.index("fit.addEventListener"):]
        self.assertIn("roundMm(row.height_mm + previousFit)", change)
        self.assertIn("roundMm(oldUsable - nextFit)", change)
        self.assertIn("event.target !== fit", self.form)

    def test_browser_projection_and_limits_expose_usable_height(self):
        js = source("web/storage-drawers.js")
        self.assertEqual(js.count("row.height_mm + space.storage_drawers.drawer_fit_mm"), 2)

class NavigatorAndGrammarTests(unittest.TestCase):
    def test_navigator_has_no_add_or_delete_drawer(self):
        nav = source("web/storage-drawers-workspace.js")
        self.assertNotIn("Add Drawer", nav)
        self.assertNotIn("sd-drawer-delete", nav)
        self.assertNotIn("deleteDrawer", nav)
        self.assertNotIn("addDrawer", source("web/spaces/14-drawers-cabinet.js"))
        self.assertIn("Add Drawer", source("web/storage-drawers-form.js"))

class StorageBoxFitTests(unittest.TestCase):
    FEATURES = {"stacking": True, "handle": True, "label_enabled": True,
                "label_text": "HI", "label_location": "front"}

    def setUp(self):
        from organizer_app import design_from_dict
        from organizer_b4b import b4b_summary
        from organizer_outputs.space import storage_box_design
        import wavefinity_web
        self.fit = wavefinity_web._storage_box_printer_fit
        self.design_from_dict, self.storage_box_design = design_from_dict, storage_box_design

        def summary(x=240, y=200, z=60, **extra):
            space = {"kind": "portable", "name": "Box", "x": x, "y": y, "z": z,
                     "storage_box": {"secure_lid": True, **extra}}
            return b4b_summary(design_from_dict(storage_box_design(space))[0])
        self.summary = summary

    def test_unreadable_object_bounds_do_not_block(self):
        self.assertEqual(self.fit({}, {"x_mm": 100.0, "y_mm": 100.0, "z_mm": 100.0}), (True, None))
        self.assertEqual(self.fit({"print_objects_mm": [{"name": "x", "bounds_mm": [1, "a", 2]}]},
                                  {"x_mm": 100.0, "y_mm": 100.0, "z_mm": 100.0}), (True, None))

class GuideAndPreviewTruthTests(unittest.TestCase):
    guide = source("web/storage-drawers-guide.html")

    def test_drawers_guide_makes_no_blanket_support_or_spring_arm_claims(self):
        self.assertNotRegex(self.guide, r"(?i)leave supports off|spring arm|reprint only the drawers")
        self.assertIn("designed to print without supports in the specified orientation", self.guide)
        self.assertIn("not only the drawers", self.guide)
        self.assertIn("not a slicer or physical-print guarantee", self.guide)

    def test_stale_structural_preview_is_labelled(self):
        js = source("web/structural-design.js")
        self.assertIn("Last valid preview", js)
        invalid = js[js.index("if (!draft.ok) {"):js.index("// Currentness tuple")]
        self.assertIn("state.structuralPreviewStale = Boolean(state.structuralPreview?.meshes?.length)", invalid)
        self.assertIn("state.structuralPreviewStale = false;", js[js.index("// Currentness tuple"):])


class EdgeMountTruthTests(unittest.TestCase):
    app = app_source(ROOT / "web")
    html = source("web/index.html")

    def test_integrated_choice_is_labelled_requires_support(self):
        self.assertIn('<option value="integrated">Integrated — Requires support</option>', self.html)
        self.assertRegex(self.html, r'id="edge-mount-integrated-support-warning"[^>]*><strong>Requires support\.</strong>')

    def test_invalid_thickness_and_depth_are_reported_not_rewritten(self):
        read = self.app[self.app.index("function readEdgeMountForm"):self.app.index("function edgeMountInputProblems")]
        self.assertNotIn("Math.min(6, Math.max(0.8", read)
        self.assertNotRegex(read, r"Math\.min\(requestedTextDepth")
        self.assertIn("const labelTextDepth = requestedTextDepth;", read)
        problems = self.app[self.app.index("function edgeMountInputProblems"):self.app.index("function edgeMountLegalInlayDepth")]
        self.assertIn("Label thickness must be", problems)
        self.assertIn("Inlay depth cannot exceed", problems)
        self.assertIn('id="edge-mount-thickness-error"', self.html)
        self.assertIn('id="edge-mount-depth-error"', self.html)


if __name__ == "__main__":
    unittest.main()
