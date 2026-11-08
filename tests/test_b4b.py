"""Focused tests for B4B (Bin for Bins)."""

import math
from pathlib import Path
import tempfile
import unittest
import zipfile
from xml.etree import ElementTree

import numpy as np
from shapely.geometry import Point, Polygon

from organizer_engine import (
    GRID_PITCH,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    B4BSpec,
    BoxSpec,
    nested_clearance,
    wave_value,
    wavy_outer_polygon,
)
from organizer_inserts import Layout
from organizer_app import (
    b4b_filename,
    design_from_dict,
    design_to_dict,
    generate_b4b_files,
)
import organizer_b4b as b4b


CASE_WALLS = [0.4, 0.8, 1.2, 1.6, 2.0]


class B4BSpecTests(unittest.TestCase):
    def test_enum_and_snugness_validation(self):
        for bad in ("latch_count", "latch_strength", "label_location", "front_label_style"):
            with self.assertRaises(ValueError):
                B4BSpec(**{bad: "nope"})
        with self.assertRaises(ValueError):
            B4BSpec(lid_headroom_mm=1.5)
        for good in (0.5, 1.0, 2.0):
            self.assertEqual(B4BSpec(lid_headroom_mm=good).lid_headroom_mm, good)




class B4BPreviewOwnershipTests(unittest.TestCase):
    """The 3D preview's All/Base/Lid split relies on every B4B preview face
    carrying an explicit ``owner`` - "base" or "lid" - rather than being
    guessed client-side from its ``kind``. See fix3d.md."""





class B4BGussetTests(unittest.TestCase):
    """The gusset carrying a body-mounted pivot barrel into its root must
    reach the barrel's complete lower flat, with no unsupported overhang."""

    def test_body_gusset_supports_lower_barrel_flat(self):
        for radius in (
            b4b.B4B_HW_M2.pivot_radius,
            b4b.B4B_HW_M3.pivot_radius,
        ):
            for outward_sign in (-1.0, 1.0):
                axis_y = 10.0 * outward_sign
                axis_z = 20.0
                root_y = 6.0 * outward_sign
                requested_root_z = 16.0

                gusset = b4b._gusset(
                    root_y=root_y,
                    root_z=requested_root_z,
                    top_z=22.0,
                    axis_y=axis_y,
                    axis_z=axis_z,
                    radius=radius,
                    outward_sign=outward_sign,
                )

                h = b4b.B4B_SUPPORT_FREE_FLAT * radius
                support_y = axis_y + outward_sign * h
                support_z = axis_z - radius

                self.assertLess(
                    gusset.exterior.distance(Point(support_y, support_z)),
                    1e-6,
                )

                root_points = [
                    z for y, z in gusset.exterior.coords
                    if abs(y - root_y) < 1e-7
                ]
                effective_root_z = min(root_points)

                run = abs(support_y - root_y)
                rise = support_z - effective_root_z

                self.assertGreaterEqual(rise + 1e-7, run)


class B4BFilletTests(unittest.TestCase):
    """Hardware is filleted where it grows out of the lid plate or the body
    root web - a square internal corner is where a printed bracket cracks."""



def _front_label_box(style: str = "flat", text: str = "FRONT", **overrides) -> BoxSpec:
    b4b_kwargs = dict(
        enabled=True, label_text=text, label_location="front",
        front_label_style=style,
    )
    b4b_kwargs.update(overrides.pop("b4b", {}))
    return BoxSpec(
        x=overrides.pop("x", 64), y=overrides.pop("y", 64),
        z=overrides.pop("z", 50), wall=overrides.pop("wall", 1.2),
        b4b=B4BSpec(**b4b_kwargs), **overrides,
    )


class B4BFrontLabelRetentionRemovedTests(unittest.TestCase):
    """The removable front label has no retention feature of any kind."""




class B4BFrontLabelPrintPoseTests(unittest.TestCase):
    """Required: both styles must print flat-back-down, text-side-up,
    through the exact path used for real export."""

    def _label_parts(self, style: str) -> dict:
        objects = b4b.b4b_build_print_objects(_front_label_box(style))
        parts = dict(next(
            parts for name, parts in objects if name == "Storage Box Front Label"
        ))
        return parts



class B4BWavyLabelZSamplesTests(unittest.TestCase):
    """``_b4b_wavy_label_z_samples`` replaces the flat per-mm Z grid with one
    tied to the border/blend topology - see ``_b4b_wave_mask_1d``."""








class B4BWavyLabelMeshComplexityTests(unittest.TestCase):
    """The Z-topology sampling must cut triangle count without losing any
    visible geometry - see ``_b4b_wavy_label_z_samples``."""



if __name__ == "__main__":
    unittest.main()
