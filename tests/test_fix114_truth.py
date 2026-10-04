"""Fix 114 targeted proof: usable height, Box fit by printed object, and the
static UI/guide truth that has no cheaper runtime mechanism. No browser."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from organizer_product_rules import STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
from space_source import app_source
from organizer_storage_drawers import (
    STORAGE_DRAWER_FIT_CHOICES, STORAGE_DRAWER_FIT_DEFAULT,
    new_drawer_descriptor, prepare_new_storage_drawers_definition,
    reset_storage_drawers_definition, storage_drawers_defaults,
)
from organizer_storage_drawer_geometry import storage_drawers_summary


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def cabinet(fit, height=20.0):
    return prepare_new_storage_drawers_definition({
        "kind": "storage_drawers", "name": "Proof", "x": 96, "y": 96,
        "storage_drawers": {"drawers": [{"height_mm": height}], "drawer_fit_mm": fit}})


class UsableHeightTests(unittest.TestCase):
    def test_summary_usable_height_is_stored_height_plus_fit(self):
        for fit in STORAGE_DRAWER_FIT_CHOICES:
            row = storage_drawers_summary(cabinet(fit))["drawers"][0]
            with self.subTest(fit=fit):
                self.assertAlmostEqual(row["usable_height_mm"], row["height_mm"] + fit)

    def test_defaults_publish_the_usable_default_under_standard_fit(self):
        defaults = storage_drawers_defaults()
        self.assertEqual(defaults["drawer_fit_mm"], STORAGE_DRAWER_FIT_DEFAULT)
        for row in defaults["drawers"]:
            self.assertAlmostEqual(row["height_mm"] + STORAGE_DRAWER_FIT_DEFAULT,
                                   STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM)
        self.assertAlmostEqual(new_drawer_descriptor()["height_mm"] + STORAGE_DRAWER_FIT_DEFAULT,
                               STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM)
        self.assertEqual(new_drawer_descriptor(33.0)["height_mm"], 33.0)

    def test_reset_recovers_the_usable_default_for_the_recovered_fit(self):
        for fit in STORAGE_DRAWER_FIT_CHOICES:
            raw = prepare_new_storage_drawers_definition(
                {"kind": "storage_drawers", "name": "R", "x": 96, "y": 96,
                 "storage_drawers": {"drawers": [{"height_mm": 30}], "drawer_fit_mm": fit}})
            raw["storage_drawers"]["drawers"][0]["height_mm"] = "bad"
            repaired = reset_storage_drawers_definition(raw)["storage_drawers"]
            with self.subTest(fit=fit):
                self.assertEqual(repaired["drawer_fit_mm"], fit)
                self.assertAlmostEqual(repaired["drawers"][0]["height_mm"] + fit,
                                       STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM)

    def test_valid_saved_rows_are_never_rewritten(self):
        kept = reset_storage_drawers_definition(cabinet(.6, 27.0))["storage_drawers"]["drawers"][0]
        self.assertEqual(kept["height_mm"], 27.0)


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

    def test_summary_failure_and_timeout_settle_into_an_editable_error(self):
        self.assertIn("Cabinet check timed out", self.form)
        self.assertIn('summaryState = "error"', self.form)
        self.assertIn("destroy() { live = false; mountSerial += 1; clearTimeout(timer); events.abort(); markSettled();", self.form)


class NavigatorAndGrammarTests(unittest.TestCase):
    def test_navigator_has_no_add_or_delete_drawer(self):
        nav = source("web/storage-drawers-workspace.js")
        self.assertNotIn("Add Drawer", nav)
        self.assertNotIn("sd-drawer-delete", nav)
        self.assertNotIn("deleteDrawer", nav)
        self.assertNotIn("addDrawer", source("web/spaces/14-drawers-cabinet.js"))
        self.assertIn("Add Drawer", source("web/storage-drawers-form.js"))

    def test_structural_host_is_one_column_and_help_sits_outside_values(self):
        css = source("web/storage-drawers.css")
        block = css[css.index("#structural-editor-host .sd-form"):]
        self.assertRegex(block, r"\.sd-summary-group\s*\{\s*grid-column:\s*1;")
        form = source("web/storage-drawers-form.js")
        self.assertNotIn("mm inside", form)
        self.assertIn("Will save as", form)
        self.assertNotIn("whole units", form)


class StorageBoxFitTests(unittest.TestCase):
    FEATURES = {"stacking": True, "handle": True, "label_enabled": True,
                "label_text": "HI", "label_location": "front"}

    def setUp(self):
        from organizer_app import design_from_dict
        from organizer_b4b import b4b_summary
        from organizer_space_outputs import storage_box_design
        import wavefinity_web
        self.fit = wavefinity_web._storage_box_printer_fit
        self.design_from_dict, self.storage_box_design = design_from_dict, storage_box_design

        def summary(x=240, y=200, z=60, **extra):
            space = {"kind": "portable", "name": "Box", "x": x, "y": y, "z": z,
                     "storage_box": {"secure_lid": True, **extra}}
            return b4b_summary(design_from_dict(storage_box_design(space))[0])
        self.summary = summary

    def test_every_exported_object_has_a_fit_row(self):
        names = [one["name"] for one in self.summary(**self.FEATURES)["print_objects_mm"]]
        self.assertEqual(names, ["Storage Box Body", "Storage Box Lid", "Storage Box Handle",
                                 "Storage Box Latch 1", "Storage Box Latch 2",
                                 *(f"Storage Box Stacking Peg {i}" for i in range(1, 5)),
                                 "Storage Box Front Label"])

    def test_each_printed_object_is_checked_not_the_assembled_envelope(self):
        summary = self.summary(stacking=True)
        objects = {one["name"]: one["bounds_mm"] for one in summary["print_objects_mm"]}
        envelope_z = summary["assembled_envelope_mm"][2]
        body_z = objects["Storage Box Body"][2]
        self.assertLess(body_z, envelope_z)
        # A printer exactly between the two heights: the assembled case would
        # not fit, but every object that is actually printed does.
        profile = {"x_mm": 256.0, "y_mm": 256.0, "z_mm": (body_z + envelope_z) / 2}
        self.assertEqual(self.fit(summary, profile), (True, None))

    def test_an_oversized_body_names_itself(self):
        fits, message = self.fit(self.summary(), {"x_mm": 200.0, "y_mm": 200.0, "z_mm": 256.0})
        self.assertFalse(fits)
        self.assertTrue(message.startswith("Storage Box Body is"))

    def test_a_non_body_object_can_be_the_failing_object(self):
        summary = self.summary(**self.FEATURES)
        for row in summary["print_objects_mm"]:
            if row["name"] == "Storage Box Handle":
                row["bounds_mm"] = [300.0, 40.0, 6.0]  # longer than any bed edge
        fits, message = self.fit(summary, {"x_mm": 256.0, "y_mm": 256.0, "z_mm": 256.0})
        self.assertFalse(fits)
        self.assertTrue(message.startswith("Storage Box Handle is"), message)

    def test_unreadable_object_bounds_do_not_block(self):
        self.assertEqual(self.fit({}, {"x_mm": 100.0, "y_mm": 100.0, "z_mm": 100.0}), (True, None))
        self.assertEqual(self.fit({"print_objects_mm": [{"name": "x", "bounds_mm": [1, "a", 2]}]},
                                  {"x_mm": 100.0, "y_mm": 100.0, "z_mm": 100.0}), (True, None))

    def test_fit_bounds_match_the_real_export_objects(self):
        """One real build (about 40 s): the fit rows name exactly the exported
        objects, are exact for the cheap objects and never understate Body/Lid."""
        import numpy as np
        from organizer_b4b import b4b_build_print_objects, b4b_print_object_bounds
        box = self.design_from_dict(self.storage_box_design(
            {"kind": "portable", "name": "Box", "x": 176, "y": 104, "z": 64,
             "storage_box": {"secure_lid": True, **self.FEATURES}}))[0]
        rows = b4b_print_object_bounds(box)
        built = b4b_build_print_objects(box)
        self.assertEqual([r["name"] for r in rows], [name for name, _parts in built])
        for row, (name, parts) in zip(rows, built):
            real = (np.max([m.bounds[1] for _n, m in parts], axis=0)
                    - np.min([m.bounds[0] for _n, m in parts], axis=0))
            with self.subTest(name=name):
                if name in ("Storage Box Body", "Storage Box Lid"):
                    for planned, actual in zip(row["bounds_mm"], real):
                        self.assertGreaterEqual(planned + 1e-3, actual)
                else:
                    for planned, actual in zip(row["bounds_mm"], real):
                        self.assertAlmostEqual(planned, actual, places=2)


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
