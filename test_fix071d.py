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

    def test_direct_foot_and_stackable_seat_geometry_are_unchanged(self):
        # Reference numbers measured on the accepted pre-071D geometry.
        direct = st.stack_effective_box(BoxSpec(48, 48, 50, stack=StackSpec(mode="direct")))
        self.assertAlmostEqual(sum(float(m.volume) for m in st.stack_body_cutters(direct)), 1334.411, delta=0.01)
        self.assertAlmostEqual(sum(float(m.volume) for m in st.stack_body_adders(direct)), 93.339, delta=0.01)
        self.assertAlmostEqual(st._plug_polygon(direct).area, 1968.6831, delta=0.01)
        for fit in ("tight", "standard", "loose"):
            eff = st.stack_effective_box(lid_box(stackable=True, fit=fit))
            self.assertAlmostEqual(sum(float(m.volume) for m in st.stack_body_cutters(eff)), 608.934, delta=0.01, msg=fit)
        self.assertEqual(direct.z, 53.0)

    def test_standard_bottom_plug_and_lock_reproduce_the_old_geometry(self):
        for stackable in (False, True):
            eff = st.stack_effective_box(lid_box(stackable=stackable))
            self.assertAlmostEqual(st._lid_plug_polygon(eff).area, 1968.6831, delta=0.01)
            # The bump is now measured from the cavity wall (so its tip is fit
            # independent); Standard stays within a tenth of a cubic millimetre.
            self.assertAlmostEqual(sum(float(m.volume) for m in st._lid_lock_bumps(eff, eff.z)), 4.8738, delta=0.1)
            self.assertAlmostEqual(sum(float(m.volume) for m in st._lid_lock_notches(eff)), 7.1734, delta=0.001)

    def test_generated_lid_plug_follows_the_preset_and_the_top_recess_does_not(self):
        for fit, mm in LID_FIT_MM.items():
            with self.subTest(fit=fit):
                box = lid_box(stackable=True, fit=fit)
                eff = st.stack_effective_box(box)
                lid, _labels = st.make_lid_parts(box)
                cavity = wavy_cavity_polygon(eff)
                # Plug section clear of the lock bumps: just above its bottom face.
                low = lid.vertices[lid.vertices[:, 2] < eff.z - st.STACK_PLUG_DEPTH + 0.05]
                lo, hi = low[:, :2].min(axis=0), low[:, :2].max(axis=0)
                cav = cavity.bounds
                self.assertAlmostEqual(float(lo[0]), cav[0] + mm, delta=0.02)
                self.assertAlmostEqual(float(hi[1]), cav[3] - mm, delta=0.02)
                # Top recess: a point just inside the cavity wall is empty, just
                # outside it is solid, whatever the plug fit is.
                z = eff.z + st.stack_lid_rise(box) - 0.5
                from shapely.geometry import LineString
                x = cavity.intersection(LineString([(0, 0), (cav[2] + 5, 0)])).bounds[2]
                inside = lid.contains([[x - 0.12, 0.0, z]])[0]
                outside = lid.contains([[x + 0.12, 0.0, z]])[0]
                self.assertFalse(inside)
                self.assertTrue(outside)

    def test_lock_interference_is_independent_of_the_fit_preset(self):
        tips = []
        notches = []
        for fit in ("tight", "standard", "loose"):
            eff = st.stack_effective_box(lid_box(fit=fit))
            bump = max(st._lid_lock_bumps(eff, eff.z), key=lambda m: m.bounds[1][0])
            tips.append(float(bump.bounds[1][0]))
            notches.append(sum(float(m.volume) for m in st._lid_lock_notches(eff)))
        self.assertLess(max(tips) - min(tips), 0.02)        # tip ends the same distance past the wall
        self.assertLess(max(notches) - min(notches), 1e-6)   # receiver does not follow the fit
        for fit in ("tight", "loose"):
            st.validate_stack_design(lid_box(fit=fit))       # lock still viable

    def test_lid_fit_does_not_touch_direct_stacking_or_thickness(self):
        base = st.stack_lid_rise(lid_box())
        for fit in ("tight", "loose"):
            self.assertEqual(st.stack_lid_rise(lid_box(fit=fit)), base)


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

    def test_old_lid_loads_as_standard_and_legacy_label_depths(self):
        box, *_ = app.design_from_dict(self.legacy_design())
        self.assertEqual(box.lid.fit, "standard")
        self.assertIsNone(box.lid.label_depth_mm)
        inlaid = app.design_from_dict(self.legacy_design(label_enabled=True, label_style="flush"))[0].lid
        raised = app.design_from_dict(self.legacy_design(label_enabled=True, label_style="raised"))[0].lid
        from organizer_engine import lid_label_relief_mm
        self.assertEqual(lid_label_relief_mm(inlaid), 0.4)
        self.assertEqual(lid_label_relief_mm(raised), 0.6)

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

    def test_no_lid_and_direct_designs_keep_their_versions_and_never_gain_a_lid(self):
        plain = app.design_to_dict(BoxSpec(48, 48, 40), Layout())
        self.assertEqual(plain["version"], 1)
        self.assertNotIn("lid", plain["box"])
        box, *_ = app.design_from_dict(plain)
        self.assertFalse(box.lid.enabled)
        direct = app.design_to_dict(BoxSpec(48, 48, 50, stack=StackSpec(mode="direct")), Layout())
        self.assertEqual(direct["version"], 6)
        self.assertNotIn("lid", direct["box"])

    def test_legacy_stack_mode_lid_is_a_standard_stackable_lid_then_rewritten(self):
        box = BoxSpec(48, 48, 50, stack=StackSpec(mode="lid"))
        from organizer_engine import lid_spec
        spec = lid_spec(box)
        self.assertTrue(spec.enabled and spec.stackable)
        self.assertEqual(spec.fit, "standard")
        self.assertEqual(st.stack_pitch(box), 50)
        saved = app.design_to_dict(box, Layout())
        self.assertEqual(saved["version"], 7)
        self.assertNotIn("stack", saved["box"])
        self.assertEqual(saved["box"]["lid"]["fit"], "standard")
        self.assertTrue(saved["box"]["lid"]["stackable"])

    def test_all_fits_serialize_and_reject_unknown_values(self):
        for fit in ("tight", "standard", "loose"):
            saved = app.design_to_dict(lid_box(fit=fit), Layout())
            self.assertEqual(saved["box"]["lid"]["fit"], fit)
            self.assertEqual(app.design_from_dict(saved)[0].lid.fit, fit)
        with self.assertRaises(ValueError):
            LidSpec(enabled=True, fit="sloppy")
        with self.assertRaises(ValueError):
            LidSpec(enabled=True, label_depth_mm=0.5)

    def test_catalog_owns_the_fit_and_relief_tables(self):
        rules = catalog_payload()["lid_rules"]
        self.assertEqual([one["mm"] for one in rules["fits"]], [0.15, 0.25, 0.35])
        self.assertIn("Tight", rules["fits"][0]["label"])
        self.assertEqual([one["value"] for one in rules["label_reliefs"]], [0.2, 0.4, 0.6, 0.8])
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for mm in ("0.15", "0.35"):
            self.assertNotIn(mm, script.split("function populateLidChoices")[1].split("function syncLidForm")[0])


class FlushSeatTests(unittest.TestCase):
    def check_seat(self, box):
        eff = st.stack_effective_box(box)
        lid, _labels = st.make_lid_parts(box)
        outer = wavy_outer_polygon(eff)
        cavity = wavy_cavity_polygon(eff)
        rim = eff.z
        ring = np.asarray(outer.exterior.coords)
        step = max(1, len(ring) // 240)
        edge = ring[::step]
        centre = np.array(outer.centroid.coords[0])
        toward = (centre - edge) / np.linalg.norm(centre - edge, axis=1, keepdims=True)
        # Exterior silhouette at the seating datum matches the bin outline.
        just_in = edge + toward * 0.05
        just_out = edge - toward * 0.05
        z = rim + 0.2
        self.assertTrue(lid.contains(np.c_[just_in, np.full(len(just_in), z)]).all(),
                        "lid exterior must reach the bin outer wall at the rim")
        self.assertFalse(lid.contains(np.c_[just_out, np.full(len(just_out), z)]).any())
        # The underside bears on the wall top: a point in the wall ring is solid
        # immediately above the rim and there is no air gap above the rim.
        self.assertTrue(lid.contains(np.c_[just_in, np.full(len(just_in), rim + 0.02)]).all())
        # The plug stays inset by its fit below the rim, clear of the lock bumps.
        mm = st.lid_fit_mm(eff)
        plug = st._lid_plug_polygon(eff)

        def ring_points(polygon):
            pts = np.asarray(polygon.exterior.coords)
            pts = pts[::max(1, len(pts) // 200)]
            return np.array([p for p in pts if abs(p[0]) > 12 and abs(p[1]) > 12])

        inside_plug = ring_points(plug.buffer(-0.2))
        in_gap = ring_points(plug.buffer(mm / 2.0))
        self.assertGreater(len(inside_plug), 10)
        self.assertGreater(len(in_gap), 10)
        self.assertTrue(lid.contains(np.c_[inside_plug, np.full(len(inside_plug), rim - 1.0)]).all())
        self.assertFalse(lid.contains(np.c_[in_gap, np.full(len(in_gap), rim - 1.0)]).any())
        # No unsupported lip: the widest horizontal underside stays a short bridge.
        self.assertLess(st._outline_run(st._lid_plug_polygon(eff), outer), 4.0)
        self.assertEqual(len(big_parts(lid)), 1)
        self.assertTrue(lid.is_watertight)

    def test_handled_and_stackable_lids_seat_flush_for_every_fit(self):
        for stackable in (False, True):
            for fit in ("tight", "standard", "loose"):
                with self.subTest(stackable=stackable, fit=fit):
                    self.check_seat(lid_box(stackable=stackable, fit=fit))

    def test_flush_seat_is_real_geometry_not_a_preview_offset(self):
        box = lid_box()
        eff = st.stack_effective_box(box)
        lid, _ = st.make_lid_parts(box)
        self.assertAlmostEqual(float(lid.bounds[0][2]), eff.z - st.STACK_PLUG_DEPTH, places=3)
        preview = preview_payload({"design": app.design_to_dict(box, Layout())})
        faces = [face for face in preview["geometry"] if face["kind"] == "lid"]
        self.assertTrue(faces)
        preview_min = min(point[2] for face in faces for point in face["points"])
        self.assertAlmostEqual(preview_min, float(lid.bounds[0][2]), places=2)

    def test_stack_module_height_and_pitch_are_unchanged(self):
        for stackable in (False, True):
            box = lid_box(stackable=stackable)
            self.assertEqual(st.stack_pitch(box), box.z)
        self.assertEqual(st.stack_effective_box(lid_box(stackable=True)).z, 49.0)
        direct = BoxSpec(48, 48, 50, stack=StackSpec(mode="direct"))
        self.assertEqual(st.stack_pitch(direct), 50)
        self.assertEqual(st.stack_effective_box(direct).z, 53.0)


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

    def test_thickness_measurements_follow_the_real_design_change_wiring(self):
        """Fix 071D Correction 1 (C1.1): the actual changedDesign() path, not a
        direct call to the renderer, stops old measurements showing as current."""
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required")
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        key = source[source.index("function lidThicknessKey("):source.index("// Inlay depth / Raised height as shown")]
        render = source[source.index("function renderLidThicknessOptions() {"):source.index("function syncLidForm() {")]
        changed = source[source.index("function changedDesign("):source.index("function markBinAxisManual(")]
        reject = source[source.index("function rejectModifierConflict("):source.index("function applyLiveFormWithModifierConflictGuard(")]
        script = "\n".join([
            "const fmt = v => String(Math.round(v * 10) / 10);",
            "const clone = v => JSON.parse(JSON.stringify(v));",
            "const options = ['thin','medium','thick'].map(v => ({ value: v, textContent: '' }));",
            "const select = { options };",
            "const fields = { '#x-size': '48', '#y-size': '48', '#wall-thickness': '0.8', '#lid-configuration': 'handled_lid' };",
            "const $ = sel => sel === '#lid-thickness' ? select",
            "  : { get value() { return fields[sel]; }, set value(v) { fields[sel] = v; } };",
            "const state = { design: { box: { x: 48, y: 48, wall: 0.8, corner_fillet: 0, flat_inside: 0,",
            "  lid: { enabled: true, stackable: false } } }, lidThicknessReport: null,",
            "  lidThicknessEpoch: 0, lidThicknessFormKey: null, canGenerate: true };",
            "let pendingDesignHistory = null;",
            "let queuedPreviews = 0;",
            "const applyChangedDesign = () => { queuedPreviews += 1; };",   # the debounced preview path
            "let sideOpeningAdjustmentNote = '';",
            "const syncForm = () => renderLidThicknessOptions();",
            "const updateGenerateAvailability = () => {};",
            "const toast = () => {};",
            key, render, changed, reject,
            "const labels = () => options.map(o => o.textContent);",
            "const land = (values, epoch = state.lidThicknessEpoch) => applyLidThicknessReport(",
            "  { design: clone(state.design), stack: { lid_thickness_mm: values } }, epoch);",
            "const out = {};",
            # 1. a matching report is visible
            "changedDesign(); const firstEpoch = state.lidThicknessEpoch;",
            "land({ thin: 2, medium: 2.8, thick: 3.6 });",
            "out.shown = labels();",
            # 2. a real Width edit through changedDesign(): old millimetres go away at once
            "fields['#x-size'] = '64'; changedDesign();",
            "out.afterWidth = labels(); out.queued = queuedPreviews;",
            "const requestEpoch = state.lidThicknessEpoch;",
            # 3. an older response (requested before the edit) cannot restore them
            "land({ thin: 2, medium: 2.8, thick: 3.6 }, firstEpoch);",
            "out.staleResponse = labels();",
            # 4. the newest matching response restores measurement-first labels
            "state.design.box.x = 64;",
            "land({ thin: 2.4, medium: 3.2, thick: 4 }, requestEpoch);",
            "out.newest = labels();",
            # 5. an edit unrelated to the lid rise does not blank the labels
            "changedDesign(); out.unrelated = labels();",
            # 6. wall edit
            "fields['#wall-thickness'] = '1.6'; changedDesign(); out.afterWall = labels();",
            # 7. Length edit (dimension-handle drags set the field and the design, then call changedDesign)
            "land({ thin: 2, medium: 2.8, thick: 3.6 });",
            "state.design.box.y = 80; fields['#y-size'] = '80'; changedDesign(clone(state.design));",
            "out.afterLength = labels();",
            # 8. Stacking Method edit
            "land({ thin: 2, medium: 2.8, thick: 3.6 });",
            "fields['#lid-configuration'] = 'stackable_lid'; state.design.box.lid.stackable = true; changedDesign();",
            "out.afterMethod = labels();",
            # 9. a failed replacement preview never leaves old millimetres visible
            "land({ thin: 2, medium: 2.8, thick: 3.6 });",
            "const before = labels();",
            "fields['#x-size'] = '96'; changedDesign();",
            "clearLidThicknessReport();",
            "out.failed = labels(); out.beforeFailed = before;",
            # 10. a rolled-back edit restores the design the last preview measured
            "const measured = clone(state.design);",
            "land({ thin: 2.2, medium: 3, thick: 3.8 });",
            "fields['#x-size'] = '112'; state.design.box.x = 112; changedDesign();",
            "out.beforeRollback = labels();",
            "rejectModifierConflict(measured, true, { message: 'no' });",
            "out.afterRollback = labels();",
            "process.stdout.write(JSON.stringify(out));",
        ])
        done = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
        out = json.loads(done.stdout)
        plain = ["Thin", "Medium", "Thick"]
        self.assertEqual(out["shown"], ["2 mm \u2014 Thin", "2.8 mm \u2014 Medium", "3.6 mm \u2014 Thick"])
        self.assertEqual(out["afterWidth"], plain)          # gone the moment the edit happens
        self.assertEqual(out["queued"], 2)                  # and the normal debounced preview path was queued
        self.assertEqual(out["staleResponse"], plain)       # an older response cannot bring them back
        self.assertEqual(out["newest"], ["2.4 mm \u2014 Thin", "3.2 mm \u2014 Medium", "4 mm \u2014 Thick"])
        self.assertEqual(out["unrelated"], out["newest"])   # no flicker for edits that do not move the lid rise
        self.assertEqual(out["afterWall"], plain)
        self.assertEqual(out["afterLength"], plain)
        self.assertEqual(out["afterMethod"], plain)
        self.assertEqual(out["beforeFailed"], ["2 mm \u2014 Thin", "2.8 mm \u2014 Medium", "3.6 mm \u2014 Thick"])
        self.assertEqual(out["failed"], plain)
        self.assertEqual(out["beforeRollback"], plain)
        self.assertEqual(out["afterRollback"], ["2.2 mm \u2014 Thin", "3 mm \u2014 Medium", "3.8 mm \u2014 Thick"])

    def test_every_lid_rise_input_path_shares_the_one_invalidation_owner(self):
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        # changedDesign() is the single owner and calls it first.
        changed = source[source.index("function changedDesign("):source.index("function markBinAxisManual(")]
        self.assertTrue(changed.lstrip().split("\n", 1)[1].lstrip().startswith("noteLidThicknessEdit();"))
        # Typed Width / Length / Height and wall edits.
        typed = source[source.index('["#x-size", "#y-size", "#z", "#base-thickness", "#wall-thickness", "#part-name"]'):
                       source.index('["#surface-base-mode"')]
        self.assertIn("changedDesign();", typed)
        # Width / Length dimension-handle drags.
        drag = source[source.index("function commitDimensionDrag("):source.index("function cancelDimensionDrag(")]
        self.assertIn("changedDesign(previousDesign);", drag)
        # Stacking Method (and every other lid control).
        method = source[source.index('["#lid-configuration", "#lid-thickness", "#lid-fit"'):
                        source.index('$("#lid-label-text").addEventListener("input"')]
        self.assertIn("changedDesign(previous);", method)
        # The preview lifecycle: requested at an epoch, cleared on failure, and
        # never a browser-owned millimetre table.
        preview = source[source.index("async function refreshPreview("):source.index("function updateAutoExpandButton()")]
        self.assertIn("const lidEpochAtRequest = state.lidThicknessEpoch;", preview)
        self.assertIn("applyLidThicknessReport(result, lidEpochAtRequest);", preview)
        self.assertIn("clearLidThicknessReport();", preview)

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

    def test_stackable_lid_inlay_keeps_backing_and_never_allows_raised(self):
        thin = lid_box(stackable=True, label_enabled=True, label_text="A", label_depth_mm=0.6)
        st.make_lid_parts(thin)                                   # 0.6 leaves enough under the seat
        deep = replace(thin, lid=replace(thin.lid, label_depth_mm=0.8))
        with self.assertRaisesRegex(ValueError, "Inlay depth"):
            st.make_lid_parts(deep)
        with self.assertRaisesRegex(ValueError, "Inlay depth"):
            st.validate_stack_design(deep)
        with self.assertRaises(ValueError):
            LidSpec(enabled=True, stackable=True, label_enabled=True, label_style="raised")
        thick = replace(deep, lid=replace(deep.lid, thickness="thick"))
        st.make_lid_parts(thick)                                  # a thicker lid allows 0.8

    def test_raised_lettering_feeds_the_closed_height_only_when_it_is_the_tallest(self):
        plain = lid_box(handle_type="knob", handle_size="small")
        raised = lid_box(handle_type="knob", handle_size="small", label_enabled=True,
                         label_style="raised", label_text="A", label_depth_mm=0.8)
        self.assertEqual(st.lid_label_height(raised), 0.8)
        self.assertEqual(st.lid_above_top_height(raised), max(st.lid_handle_height(raised), 0.8))
        self.assertEqual(st.stack_closed_height(raised), st.stack_closed_height(plain))
        lid, labels = st.make_lid_parts(raised)
        self.assertAlmostEqual(float(lid.bounds[1][2]), st.stack_closed_height(raised), places=3)


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

    def test_reports_keepout_and_closed_height_agree_with_the_mesh(self):
        for handle_type in ("knob", "pull"):
            for size in self.SIZES:
                for position in ("middle", "back", "right"):
                    with self.subTest(handle=handle_type, size=size, position=position):
                        box = lid_box(handle_type=handle_type, handle_size=size, handle_position=position)
                        eff = st.stack_effective_box(box)
                        mesh = st._lid_handle_mesh(box)
                        x0, y0, x1, y1 = st._lid_handle_keepout(box)
                        m = handles.LID_HANDLE_KEEPOUT_MARGIN
                        self.assertAlmostEqual(x0, float(mesh.bounds[0][0]) - m, places=6)
                        self.assertAlmostEqual(y1, float(mesh.bounds[1][1]) + m, places=6)
                        self.assertAlmostEqual(st.lid_handle_height(box), float(mesh.bounds[1][2]), places=6)
                        lid, _ = st.make_lid_parts(box)
                        self.assertAlmostEqual(st.stack_closed_height(box), float(lid.bounds[1][2]), places=3)
                        self.assertAlmostEqual(
                            st.stack_closed_height(box),
                            eff.z + st.stack_lid_rise(box) + st.lid_handle_height(box), places=6)

    def test_changing_handle_settings_recomputes_the_planning_height(self):
        heights = {(t, s): st.stack_closed_height(lid_box(handle_type=t, handle_size=s))
                   for t in ("knob", "pull") for s in self.SIZES}
        for handle_type in ("knob", "pull"):
            self.assertGreater(heights[(handle_type, "large")], heights[(handle_type, "small")])
        self.assertNotEqual(heights[("knob", "medium")], heights[("pull", "medium")])
        self.assertGreater(len(set(round(v, 3) for v in heights.values())), 4)

    def test_knob_is_a_rounded_dome_without_a_cone_apex_or_undercut(self):
        mesh = handles.resolve_lid_handle((-25, -25, 25, 25), "knob", "large", "middle")
        radii = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
        z = mesh.vertices[:, 2]
        levels = np.linspace(0.2, float(z.max()) - 0.05, 40)
        widest = [radii[z >= level].max() for level in levels]
        self.assertTrue(all(b <= a + 1e-6 for a, b in zip(widest, widest[1:])))     # never undercuts
        crown = mesh.vertices[z > z.max() - 0.03]
        self.assertLessEqual(float(np.hypot(crown[:, 0], crown[:, 1]).max()), 1.0)    # flat rounded crown
        near_top = radii[z > z.max() - 0.6].max()
        self.assertGreater(near_top, 1.5)                                            # blunt, not a cone tip
        self.assertGreater(float(radii[z < 0.5].max()), float(radii[(z > 1.5) & (z < 2.0)].max()))   # broad blended base

    def test_pull_is_an_open_arch_with_blended_roots(self):
        for size in self.SIZES:
            with self.subTest(size=size):
                mesh = handles.resolve_lid_handle((-25, -25, 25, 25), "pull", size, "middle")
                top = float(mesh.bounds[1][2])
                half = float(mesh.bounds[1][0])
                self.assertFalse(mesh.contains([[0.0, 0.0, top * 0.4]])[0])           # open under the grip
                self.assertTrue(mesh.contains([[0.0, 0.0, top - 1.0]])[0])            # solid crown
                foot = handles.LID_PULL_TUBE_RADIUS[size] * (1 + handles.LID_PULL_FOOT_FLARE)
                self.assertTrue(mesh.contains([[half - foot, 0.0, 0.2]])[0])         # root under the leg
                width_low = np.ptp(mesh.vertices[np.abs(mesh.vertices[:, 2] - 0.1) < 0.15][:, 1])
                width_high = np.ptp(mesh.vertices[np.abs(mesh.vertices[:, 2] - top * 0.5) < 0.6][:, 1])
                self.assertGreater(width_low, width_high)                             # legs flare into the lid

    def test_tiny_lid_blocks_every_path_instead_of_shrinking_the_handle(self):
        tiny = BoxSpec(16, 16, 30, lid=LidSpec(enabled=True, handle_type="pull", handle_size="large"))
        for call in (
            lambda: st.validate_stack_design(tiny),
            lambda: st.make_lid_parts(tiny),
            lambda: st.stack_closed_height(tiny),
            lambda: app.inventory_bin_record(tiny, Layout()),
            lambda: inventory_preview_payload({"design": app.design_to_dict(tiny, Layout())}),
            lambda: preview_payload({"design": app.design_to_dict(tiny, Layout())}),
        ):
            with self.assertRaisesRegex(ValueError, "smaller handle size or a larger lid"):
                call()
        self.assertEqual(tiny.lid.handle_size, "large")                       # intent untouched

    def test_label_regions_avoid_the_real_handle_envelope(self):
        box = lid_box(handle_type="pull", handle_size="medium", handle_position="middle",
                      label_enabled=True, label_text="TOOLS")
        eff = st.stack_effective_box(box)
        _lid, labels = st.make_lid_parts(box)
        keep = st._lid_handle_keepout(box)
        bounds = labels[0][1].bounds
        clear = (bounds[1][0] < keep[0] or bounds[0][0] > keep[2]
                 or bounds[1][1] < keep[1] or bounds[0][1] > keep[3])
        self.assertTrue(clear)


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

    def test_local_generate_saves_the_requested_design_not_the_effective_body(self):
        for box in (lid_box(stackable=True, fit="loose"),
                    lid_box(handle_type="pull", handle_size="large", handle_position="front",
                            label_enabled=True, label_text="A", label_depth_mm=0.6)):
            with self.subTest(stackable=box.lid.stackable):
                captured = self.generate(box)
                spec = captured["spec"]
                self.assertEqual(spec["box"]["z"], 50)                    # requested, not the shortened body
                self.assertEqual(spec["box"]["lid"]["stackable"], box.lid.stackable)
                self.assertEqual(spec["box"]["lid"]["fit"], box.lid.fit)
                self.assertEqual(spec["box"]["lid"]["handle_type"], box.lid.handle_type)
                reopened, *_ = app.design_from_dict(spec)
                self.assertEqual(reopened.z, 50)
                self.assertEqual(reopened.lid, app.design_from_dict(app.design_to_dict(box, Layout()))[0].lid)
                # Hosted and local sources are the same canonical design.
                self.assertEqual(spec, app.design_to_dict(box, Layout(), "", "", "bottom", False))

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

    def test_direct_stack_and_stackable_lid_records_keep_their_pitch_rules(self):
        direct = app.inventory_bin_record(BoxSpec(48, 48, 50, stack=StackSpec(mode="direct")), Layout())
        stackable = app.inventory_bin_record(lid_box(stackable=True), Layout())
        self.assertEqual(direct["stack"], "direct")
        self.assertEqual(stackable["stack"], "lid")
        self.assertEqual(float(direct["z"]), 50)
        self.assertEqual(float(stackable["z"]), 50)

    def test_preview_summary_matches_geometry_and_generation(self):
        box = lid_box(handle_type="pull", handle_size="medium", fit="tight")
        summary = preview_payload({"design": app.design_to_dict(box, Layout())})["stack"]
        self.assertAlmostEqual(summary["closed_height_mm"], st.stack_closed_height(box), places=2)
        self.assertEqual(summary["lid_fit_mm"], 0.15)
        with tempfile.TemporaryDirectory() as folder:
            result = app.generate_organizer_files(box, Layout(), Path(folder))
        self.assertIn("lid", result)


class StaticContractTests(unittest.TestCase):
    def test_stacking_method_ui_and_conditional_controls(self):
        html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        script = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for text in ("Stacking Method", "Stackable bin on bin", "Stackable bin on lid",
                     "Lid with handle — non-stackable"):
            self.assertIn(text, html)
        self.assertNotIn(">Configuration", html)
        self.assertNotIn("Level with top", html)
        self.assertIn('id="lid-fit"', html)
        self.assertIn('id="lid-label-depth"', html)
        self.assertNotIn('value="none">No lid', html)                     # no fourth choice
        sync = script[script.index("function syncLidForm() {"):script.index("function stackRuleValues(")]
        for line in ('$("#lid-group-lid").hidden = !hasLid;',
                     '$("#lid-group-handle").hidden = !handled;',
                     '$("#lid-group-label").hidden = !hasLid;',
                     '$("#lid-label-style-row").hidden = !labelOn || !handled;',
                     'raisedActive ? "Raised height" : "Inlay depth"'):
            self.assertIn(line, sync)
        self.assertIn('fit: $("#lid-fit")?.value', script)

    def test_hidden_lid_state_survives_a_method_detour_in_the_browser_model(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is required")
        source = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        helpers = source[source.index("const LID_DEFAULTS = {"):source.index("function applyDivisionGridLayout(")]
        read_form = source[source.index("function readStackForm(design) {"):]
        read_form = read_form[:read_form.index("\n}\n") + 3]
        script = "\n".join([
            "const state = { design: null, lidMemory: null, catalog: { lid_rules: {} } };",
            "const fields = { '#lid-configuration': 'handled_lid', '#lid-thickness': 'thick', '#lid-fit': 'loose',",
            "  '#lid-handle-type': 'pull', '#lid-handle-size': 'large', '#lid-handle-position': 'front',",
            "  '#lid-label-enabled': 'true', '#lid-label-orientation': 'vertical', '#lid-label-style': 'raised',",
            "  '#lid-label-text': 'PARTS', '#lid-label-depth': '0.6' };",
            "const $ = sel => ({ get value() { return fields[sel]; }, set value(v) { fields[sel] = v; } });",
            helpers, read_form,
            "function resync(design) { const lid = lidState(design); fields['#lid-fit'] = lid.fit;",
            "  fields['#lid-handle-type'] = lid.handle_type; fields['#lid-handle-size'] = lid.handle_size;",
            "  fields['#lid-handle-position'] = lid.handle_position; fields['#lid-label-orientation'] = lid.label_orientation;",
            "  fields['#lid-label-style'] = lid.label_style; fields['#lid-label-depth'] = String(lid.label_depth_mm ?? ''); }",
            "function apply(design, config) { fields['#lid-configuration'] = config; readStackForm(design); resync(design); return design; }",
            "let design = { box: { lid: { ...LID_DEFAULTS, enabled: true } } };",
            "design = apply(design, 'handled_lid');",
            "const first = JSON.parse(JSON.stringify(design.box.lid));",
            "design = apply(design, 'stackable_lid');",
            "const stackable = JSON.parse(JSON.stringify(design.box.lid));",
            "design = apply(design, 'stackable_bin');",
            "const noLid = Boolean(design.box.lid);",
            "design = apply(design, 'handled_lid');",
            "process.stdout.write(JSON.stringify({ first, stackable, noLid, back: design.box.lid }));",
        ])
        out = json.loads(subprocess.run([node, "-e", script], check=True, capture_output=True, text=True).stdout)
        self.assertEqual(out["first"]["fit"], "loose")
        self.assertEqual(out["first"]["label_depth_mm"], 0.6)
        self.assertEqual(out["stackable"]["label_style"], "flush")          # Raised inactive on a stack seat
        self.assertEqual(out["stackable"]["fit"], "loose")
        self.assertFalse(out["noLid"])                                      # bin-on-bin: no lid output at all
        for key in ("handle_type", "handle_size", "handle_position", "label_orientation",
                    "label_style", "fit", "label_depth_mm"):
            self.assertEqual(out["back"][key], out["first"][key], key)


if __name__ == "__main__":
    unittest.main()
