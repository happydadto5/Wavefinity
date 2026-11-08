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
import organizer_features.lid_handle as handles
import organizer_features.stack as st
from organizer_drawer import stack_part_height
from organizer_engine import (
    BoxSpec, LID_FIT_MM, LidSpec, StackSpec, lid_has_handle, wavy_cavity_polygon, wavy_outer_polygon,
)
from organizer_geometry import intersection
from organizer_inserts import Layout
from wavefinity_web import (
    catalog_payload, inventory_preview_payload, preview_payload,
)

ROOT = Path(__file__).resolve().parent.parent


def lid_box(**lid_fields) -> BoxSpec:
    fields = {"enabled": True, "stackable": False}
    fields.update(lid_fields)
    return BoxSpec(48, 48, 50, lid=LidSpec(**fields))


def big_parts(mesh, minimum=0.5):
    return [part for part in mesh.split(only_watertight=False) if abs(part.volume) > minimum]


class HandleTests(unittest.TestCase):
    SIZES = ("small", "medium", "large")

    OUTER_BOUNDS = (-24.0, -24.0, 24.0, 24.0)
    # Knob mesh recorded from the unmodified builder before the teardrop change.
    KNOB_BASELINE = {
        "small": (2400, 1202, ((-4.2, -4.2, -0.8), (4.2, 4.2, 4.0))),
        "medium": (2400, 1202, ((-4.62, -4.62, -0.8), (4.62, 4.62, 4.0))),
        "large": (2400, 1202, ((-6.06, -6.06, -0.8), (6.06, 6.06, 5.016))),
    }

    def test_pull_has_no_exposed_overhang_beyond_45_degrees(self):
        for size in self.SIZES:
            for position in ("middle", "front", "left"):
                with self.subTest(size=size, position=position):
                    mesh = handles.resolve_lid_handle(self.OUTER_BOUNDS, "pull", size, position)
                    self.assertTrue(mesh.is_watertight)
                    self.assertGreater(mesh.volume, 0.0)
                    # Exposed faces only: the buried root caps sit at the root plane
                    # (the tolerance absorbs float noise in their centroid height).
                    exposed = mesh.triangles_center[:, 2] > -handles.LID_HANDLE_ROOT_EMBED + 1e-6
                    normals = mesh.face_normals
                    down = exposed & (normals[:, 2] < 0.0)
                    self.assertTrue(down.any())
                    angle = np.degrees(np.arccos(np.clip(normals[down, 2], -1.0, 1.0)))
                    overhang = np.abs(90.0 - angle)
                    self.assertEqual(int((overhang > 45.0 + 1e-6).sum()), 0)

    def test_pull_bounds_match_the_round_tube_envelope(self):
        # Bounds recorded from the even-arch builder (3x finger clearance).
        recorded = {
            "small": ((-8.55, -2.0, -0.8), (8.55, 2.0, 22.0)),
            "medium": ((-11.4, -2.4, -0.8), (11.4, 2.4, 28.8)),
            "large": ((-14.25, -2.8, -0.8), (14.25, 2.8, 35.6)),
        }
        for size, bounds in recorded.items():
            with self.subTest(size=size):
                mesh = handles.resolve_lid_handle(self.OUTER_BOUNDS, "pull", size, "middle")
                np.testing.assert_allclose(mesh.bounds, np.asarray(bounds), atol=1e-6)

    def test_knob_mesh_is_unchanged_by_the_pull_redesign(self):
        for size, (faces, vertices, bounds) in self.KNOB_BASELINE.items():
            with self.subTest(size=size):
                mesh = handles.resolve_lid_handle(self.OUTER_BOUNDS, "knob", size, "middle", "dome")
                self.assertEqual(len(mesh.faces), faces)
                self.assertEqual(len(mesh.vertices), vertices)
                np.testing.assert_allclose(mesh.bounds, np.asarray(bounds), atol=1e-6)








class OptionalHandleTests(unittest.TestCase):
    def test_mushroom_underside_is_printable_and_inside_the_envelope(self):
        for size in HandleTests.SIZES:
            with self.subTest(size=size):
                mesh = handles.resolve_lid_handle(HandleTests.OUTER_BOUNDS, "knob", size, "middle", "mushroom")
                self.assertTrue(mesh.is_watertight)
                top = handles.handle_height(mesh)
                self.assertLessEqual(top, handles.LID_KNOB_HEIGHT_LIMITS[1] + 1e-6)
                extent = mesh.bounds[1][0] - mesh.bounds[0][0]
                self.assertLessEqual(extent, handles.LID_MUSHROOM_DIAMETER_LIMITS[1] + 1e-6)
                stem = handles._mushroom_stem_radius(extent)
                self.assertLess(stem * 2.0, extent)
                # Cap underside: at most 1 mm outward per mm of rise.
                self.assertGreaterEqual(handles.LID_MUSHROOM_FLARE_RUN, 1.0)

    def test_oversize_knob_on_a_small_lid_is_refused_naming_the_shape(self):
        for shape, name in (("mushroom", "Mushroom knob"), ("dome", "Dome knob")):
            with self.subTest(shape=shape):
                with self.assertRaisesRegex(ValueError, name):
                    handles.resolve_lid_handle((0.0, 0.0, 12.0, 12.0), "knob", "large", "middle", shape)

    def test_unknown_knob_shape_is_rejected(self):
        with self.assertRaises(ValueError):
            LidSpec(enabled=True, stackable=False, knob_shape="cube")


if __name__ == "__main__":
    unittest.main()
