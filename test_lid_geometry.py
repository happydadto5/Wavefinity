"""Focused, non-browser checks for Fix 071D: ordinary Lid & Stacking fit, handles."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

import numpy as np
from shapely.geometry import Point

import organizer_app as app
import organizer_lid_handle as handles
import organizer_stack as st
from organizer_drawer import stack_part_height
from organizer_engine import (
    BoxSpec, LID_FIT_MM, LidSpec, StackSpec, wavy_cavity_polygon, wavy_outer_polygon,
)
from organizer_geometry import intersection
from organizer_inserts import Layout
from wavefinity_web import (
    catalog_payload, inventory_preview_payload, preview_payload,
)

ROOT = Path(__file__).resolve().parent


def lid_box(**lid_fields) -> BoxSpec:
    fields = {"enabled": True, "stackable": False}
    fields.update(lid_fields)
    return BoxSpec(48, 48, 50, lid=LidSpec(**fields))


def big_parts(mesh, minimum=0.5):
    return [part for part in mesh.split(only_watertight=False) if abs(part.volume) > minimum]


class FitOwnershipTests(unittest.TestCase):
    def test_only_the_lid_plug_follows_the_lid_fit(self):
        for fit, mm in LID_FIT_MM.items():
            with self.subTest(fit=fit):
                eff = st.stack_effective_box(lid_box(fit=fit))
                cavity = wavy_cavity_polygon(eff)
                plug = st._lid_plug_polygon(eff)
                self.assertLess(plug.symmetric_difference(cavity.buffer(-mm)).area, 1e-3)
                # The shared foot / top-recess outline never moves.
                self.assertLess(st._plug_polygon(eff).symmetric_difference(
                    cavity.buffer(-st.STACK_FIT)).area, 1e-3)







class SchemaMigrationTests(unittest.TestCase):
    def legacy_design(self, **lid):
        design = app.design_to_dict(lid_box(), Layout())
        block = {"enabled": True, "stackable": False, "thickness": "thin", "label_enabled": False,
                 "label_style": "flush", "label_orientation": "horizontal", "label_text": "",
                 "division_labels": [], "handle_type": "knob", "handle_size": "medium",
                 "handle_position": "middle", **lid}
        design["version"] = 6
        design["box"]["lid"] = block
        return design


    def test_canonical_save_is_version_7_explicit_and_round_trips(self):
        for style, expected in (("flush", 0.4), ("raised", 0.6)):
            with self.subTest(style=style):
                box, layout, *rest = app.design_from_dict(
                    self.legacy_design(label_enabled=True, label_style=style, label_text="A"))
                saved = app.design_to_dict(box, layout, *rest)
                self.assertEqual(saved["version"], 7)
                self.assertEqual(saved["box"]["lid"]["fit"], "standard")
                self.assertEqual(saved["box"]["lid"]["label_depth_mm"], expected)
                again = app.design_to_dict(*app.design_from_dict(saved))
                self.assertEqual(again, saved)











class ThicknessAndLabelTests(unittest.TestCase):
    def test_thickness_choices_come_from_the_backend_for_the_current_bin(self):
        small = lid_box(thickness="thick")
        wide = replace(lid_box(), wall=2.4, standard_walls=False)
        for box in (small, wide):
            report = st.lid_thickness_options(box)
            self.assertEqual(set(report), {"thin", "medium", "thick"})
            for name, value in report.items():
                cloned = replace(box, lid=replace(box.lid, thickness=name))
                self.assertEqual(value, round(st.stack_lid_rise(cloned), 3))
            self.assertEqual(box.lid.thickness, "thick" if box is small else "thin")   # read-only
        self.assertNotEqual(st.lid_thickness_options(small), st.lid_thickness_options(wide))
        preview = preview_payload({"design": app.design_to_dict(small, Layout())})
        self.assertEqual(preview["stack"]["lid_thickness_mm"], st.lid_thickness_options(small))



    def test_lid_label_depth_and_height_match_preview_and_export(self):
        for style, raised in (("flush", False), ("raised", True)):
            for depth in (0.2, 0.4, 0.6, 0.8):
                with self.subTest(style=style, depth=depth):
                    box = lid_box(label_enabled=True, label_style=style, label_text="AB",
                                  label_depth_mm=depth, label_orientation="vertical")
                    _lid, labels = st.make_lid_parts(box)
                    self.assertEqual(len(labels), 1)
                    mesh = labels[0][1]
                    self.assertEqual(labels[0][2], raised)
                    self.assertAlmostEqual(float(mesh.bounds[1][2] - mesh.bounds[0][2]), depth, places=3)
                    eff = st.stack_effective_box(box)
                    top = eff.z + st.stack_lid_rise(box)
                    self.assertAlmostEqual(float(mesh.bounds[1][2]), top + (depth if raised else 0.0), places=3)
                    saved = app.design_to_dict(box, Layout())
                    self.assertEqual(saved["box"]["lid"]["label_depth_mm"], depth)
                    self.assertEqual(saved["box"]["lid"]["label_orientation"], "vertical")




class HandleTests(unittest.TestCase):
    SIZES = ("small", "medium", "large")

    def test_handles_are_one_connected_watertight_lid_with_positive_root_overlap(self):
        for handle_type in ("knob", "pull"):
            for size in self.SIZES:
                for position in ("middle", "left", "front"):
                    with self.subTest(handle=handle_type, size=size, position=position):
                        box = lid_box(handle_type=handle_type, handle_size=size, handle_position=position)
                        eff = st.stack_effective_box(box)
                        lid, _ = st.make_lid_parts(box)
                        self.assertTrue(lid.is_watertight)
                        self.assertEqual(len(big_parts(lid)), 1)
                        top = eff.z + st.stack_lid_rise(box)
                        mesh = st._lid_handle_mesh(box)
                        mesh.apply_translation((0.0, 0.0, top))
                        plate = wavy_outer_polygon(eff)
                        from organizer_geometry import _extrude_polygon
                        slab = _extrude_polygon(plate, st.stack_lid_rise(box))
                        slab.apply_translation((0.0, 0.0, eff.z))
                        self.assertGreater(float(intersection([slab, mesh]).volume), 0.5)








class PersistenceAndPlanningTests(unittest.TestCase):
    def generate(self, box):
        captured = {}

        def fake_log(output_dir, request, layout, **kwargs):
            captured["request"] = request
            captured["spec"] = kwargs["design_spec"]
            return Path(output_dir) / "log.md"

        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(app, "log_bin_to_folder", side_effect=fake_log):
            app.generate_organizer_files(box, Layout(), Path(folder), keep_log=True)
        return captured


    def test_inventory_z_is_the_closed_envelope_once_and_requested_z_is_untouched(self):
        for handle_type, size in (("knob", "small"), ("pull", "large")):
            box = lid_box(handle_type=handle_type, handle_size=size)
            record = app.inventory_bin_record(box, Layout())
            self.assertEqual(record["stack"], "none")
            self.assertAlmostEqual(float(record["z"]), st.stack_closed_height(box), places=3)
            self.assertAlmostEqual(stack_part_height(record), st.stack_closed_height(box), places=3)
            self.assertEqual(app.design_to_dict(box, Layout())["box"]["z"], 50)
        raised = lid_box(handle_type="knob", handle_size="small", label_enabled=True,
                         label_style="raised", label_text="A", label_depth_mm=0.8)
        record = app.inventory_bin_record(raised, Layout())
        self.assertAlmostEqual(float(record["z"]), st.stack_closed_height(raised), places=3)




if __name__ == "__main__":
    unittest.main()
