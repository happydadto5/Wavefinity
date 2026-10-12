import subprocess
import sys
import unittest
from pathlib import Path

from organizer_engine import BASE_UNIT
from organizer_engine.product_rules import DRAWER_LAYER_MAX_USABLE_HEIGHT_MM, STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM
from organizer_drawer import blocking_problem_messages, drawer_report
from organizer_drawer._core import MAX_DRAWER_MM
from organizer_storage.drawers import (
    STORAGE_DRAWER_MAX_USABLE_HEIGHT_MM, new_drawer_descriptor,
    normalise_storage_drawers_definition, prepare_new_storage_drawers_definition,
    reconcile_storage_drawers_layout, reset_storage_drawers_definition,
    storage_drawers_defaults, storage_drawers_projection,
)
from wavefinity_web import catalog_payload

REPO_ROOT = Path(__file__).resolve().parent.parent
ERROR = "Drawer usable height must be at most 2000 mm"


def _fresh_import(module):
    return subprocess.run([sys.executable, "-c", f"import {module}"], cwd=REPO_ROOT,
                          capture_output=True, text=True, timeout=120)


def _space(height, fit):
    block = storage_drawers_defaults(1)
    block["drawer_fit_mm"] = fit
    block["drawers"][0]["height_mm"] = height
    return {"kind": "storage_drawers", "name": "Boundary cabinet",
            "x": 6 * BASE_UNIT, "y": 6 * BASE_UNIT, "storage_drawers": block}


class StorageDrawersHeightTests(unittest.TestCase):
    def assertAccepted(self, raw, height):
        canonical = normalise_storage_drawers_definition(raw)
        self.assertEqual(canonical["storage_drawers"]["drawers"][0]["height_mm"], height)
        return canonical

    def assertRejected(self, raw, normalizer=normalise_storage_drawers_definition):
        with self.assertRaises(ValueError) as caught:
            normalizer(raw)
        self.assertEqual(str(caught.exception), ERROR)

    def test_drawer_height_above_cap_rejected(self):
        self.assertRejected(_space(5000.0, 0.40))
        self.assertRejected(_space(5000.0, 0.40), prepare_new_storage_drawers_definition)

    def test_drawer_height_at_usable_boundary_accepted(self):
        self.assertAccepted(_space(1999.4, 0.60), 1999.4)

    def test_usable_boundary_reports_clean_downstream(self):
        canonical = self.assertAccepted(_space(1999.4, 0.60), 1999.4)
        reconciled = reconcile_storage_drawers_layout({}, canonical)
        projected = storage_drawers_projection(canonical)
        report = drawer_report(projected[0], [], layout=reconciled)
        self.assertEqual(blocking_problem_messages(report), [])

    def test_drawer_height_just_over_usable_rejected(self):
        self.assertRejected(_space(1999.5, 0.60))

    def test_tight_fit_allows_taller_clear_height(self):
        self.assertAccepted(_space(1999.7, 0.30), 1999.7)

    def test_loose_fit_rejects_same_clear_height(self):
        self.assertRejected(_space(1999.7, 0.60))

    def test_fit_change_to_tighter_accepted(self):
        raw = _space(1999.4, 0.60)
        self.assertAccepted(raw, 1999.4)
        raw["storage_drawers"]["drawer_fit_mm"] = 0.30
        self.assertAccepted(raw, 1999.4)

    def test_fit_change_to_looser_rejected(self):
        raw = _space(1999.7, 0.30)
        self.assertAccepted(raw, 1999.7)
        raw["storage_drawers"]["drawer_fit_mm"] = 0.60
        self.assertRejected(raw)

    def test_overheight_drawer_falls_back_to_default_on_reset(self):
        raw = _space(5000.0, 0.40)
        repaired = reset_storage_drawers_definition(raw)["storage_drawers"]["drawers"][0]
        self.assertEqual(repaired["id"], raw["storage_drawers"]["drawers"][0]["id"])
        self.assertEqual(repaired["height_mm"], STORAGE_DRAWERS_DEFAULT_USABLE_HEIGHT_MM - 0.40)

    def test_new_drawer_descriptor_rejects_overheight_for_fit(self):
        for height, fit in ((5000.0, 0.40), (1999.7, 0.60)):
            with self.subTest(height=height, fit=fit), self.assertRaises(ValueError) as caught:
                new_drawer_descriptor(height, fit)
            self.assertEqual(str(caught.exception), ERROR)
        self.assertEqual(new_drawer_descriptor(1999.7, 0.30)["height_mm"], 1999.7)

    def test_max_usable_height_derives_from_shared_product_rule(self):
        self.assertEqual(DRAWER_LAYER_MAX_USABLE_HEIGHT_MM, 2000.0)
        self.assertEqual(STORAGE_DRAWER_MAX_USABLE_HEIGHT_MM, DRAWER_LAYER_MAX_USABLE_HEIGHT_MM)
        self.assertEqual(MAX_DRAWER_MM, DRAWER_LAYER_MAX_USABLE_HEIGHT_MM)

    def assertFreshImport(self, module):
        result = _fresh_import(module)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("ImportError", result.stderr)

    def test_import_smoke_storage_drawers(self):
        self.assertFreshImport("organizer_storage.drawers")

    def test_import_smoke_inventory(self):
        self.assertFreshImport("organizer_inventory")

    def test_import_smoke_organizer_drawer(self):
        self.assertFreshImport("organizer_drawer")

    def test_rules_publish_max_usable_height(self):
        self.assertEqual(catalog_payload()["storage_drawers_rules"]["max_usable_height_mm"], 2000.0)


class Fix1117SideShellClearanceTests(unittest.TestCase):
    def fixture(self, fit, style="full"):
        from organizer_storage import drawer_geometry as geometry
        block = storage_drawers_defaults(3)
        block["drawer_fit_mm"] = fit
        block["cabinet_style"] = style
        space = normalise_storage_drawers_definition({
            "kind": "storage_drawers", "name": "Shell clearance",
            "x": 48.0, "y": 48.0, "storage_drawers": block})
        datum = geometry._make_datum(space)
        floor = datum.floors[1]
        height = space["storage_drawers"]["drawers"][1]["height_mm"]
        x0 = (datum.outer_x-datum.field_x)/2
        cavity = geometry.wavy_rect_cavity(
            datum.field_x/2 + geometry.WAVE_MATING_GAP/2,
            datum.field_y/2 + geometry.WAVE_MATING_GAP/2, 0.0, wall=0.0)
        shell = geometry._cosmetic_side_shell(cavity, x0, datum, floor, height)
        return geometry, space, datum, x0, floor, height, cavity, shell

    def test_shell_top_below_stop_root_all_fits(self):
        for fit in (0.30, 0.40, 0.60):
            with self.subTest(fit=fit):
                g, _, d, x0, floor, height, cavity, shell = self.fixture(fit)
                self.assertAlmostEqual(shell.bounds[1, 2],
                    floor+height-(g.SD_RAIL_LEDGE_MM+fit+0.3))
                short_height = 2*g.SD_RAIL_CAPTURE_MM+fit + g.SD_RAIL_LEDGE_MM+fit+0.3+2.4
                self.assertIsNone(g._cosmetic_side_shell(cavity, x0, d, floor, short_height-1e-8))
                from dataclasses import replace
                self.assertIsNone(g._cosmetic_side_shell(cavity, x0, replace(d, field_y=16.0), floor, height))

    def test_top_band_clipped_to_wall_plane(self):
        for fit in (0.30, 0.40, 0.60):
            with self.subTest(fit=fit):
                g, _, d, x0, floor, height, _, shell = self.fixture(fit)
                z1 = floor+height-(g.SD_RAIL_LEDGE_MM+fit+0.3)
                band = shell.vertices[shell.vertices[:, 2] >= z1-0.8-1e-8]
                self.assertGreater(len(band), 0)
                self.assertGreaterEqual(band[:, 0].min(), x0-d.drawer_wall-1e-8)
                self.assertLessEqual(band[:, 0].max(), x0+d.field_x+d.drawer_wall+1e-8)
                self.assertTrue(shell.is_watertight)

    def test_zero_contact_sweep(self):
        import trimesh
        for fit in (0.30, 0.40, 0.60):
            for style in ("full", "open"):
                g, space, d, x0, floor, height, _, shell = self.fixture(fit, style)
                definitions, _ = g._datum_components(space, d)
                # Use the production sides, restricted to the upper stop band.
                stop_bottom = d.floors[0]-d.drawer_base-g.SD_RAIL_LEDGE_MM-fit
                stop_y = d.front+g.SD_RAIL_LEADIN_MM+12.0
                region = g._box(-1, stop_y, stop_bottom, d.outer_x+1,
                                stop_y+g.SD_CATCH_LENGTH_MM, d.floors[0]+2)
                stops = [trimesh.boolean.intersection([maker(), region], engine="manifold")
                         for key, _, _, maker, _, _ in definitions
                         if key in ("side_left", "side_right", "frame_left", "frame_right")]
                for dx in (-fit, 0.0, fit):
                    for dz in (0.0, fit):
                        with self.subTest(fit=fit, style=style, dx=dx, dz=dz):
                            moved = shell.copy()
                            moved.apply_translation((dx, 0, dz))
                            for stop in stops:
                                contact = trimesh.boolean.intersection([moved, stop], engine="manifold")
                                self.assertLess(abs(contact.volume), 1e-7)


if __name__ == "__main__":
    unittest.main()
