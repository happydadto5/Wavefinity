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
    def test_knob_has_no_exposed_overhang_beyond_45_degrees(self):
        for size in self.SIZES:
            for position in ("middle", "front", "left"):
                with self.subTest(size=size, position=position):
                    mesh = handles.resolve_lid_handle(self.OUTER_BOUNDS, "knob", size, position)
                    self.assertTrue(mesh.is_watertight)
                    exposed = mesh.triangles_center[:, 2] > 1e-6
                    normals = mesh.face_normals
                    down = exposed & (normals[:, 2] < 0.0)
                    self.assertTrue(down.any())
                    angle = np.degrees(np.arccos(np.clip(-normals[down, 2], -1.0, 1.0)))
                    self.assertGreaterEqual(float(angle.min()), 45.0 - 1e-6)

    def test_every_handle_type_builds_the_one_knob(self):
        for size in self.SIZES:
            with self.subTest(size=size):
                knob = handles.resolve_lid_handle(self.OUTER_BOUNDS, "knob", size, "middle")
                saved_pull = handles.resolve_lid_handle(self.OUTER_BOUNDS, "pull", size, "middle")
                np.testing.assert_allclose(knob.bounds, saved_pull.bounds)


class OptionalHandleTests(unittest.TestCase):
    def test_oversize_knob_on_a_small_lid_is_refused(self):
        with self.assertRaisesRegex(ValueError, "knob"):
            handles.resolve_lid_handle((0.0, 0.0, 12.0, 12.0), "knob", "large", "middle")


if __name__ == "__main__":
    unittest.main()
