"""Focused tests for B4B (Bin for Bins)."""

import math
import unittest

import numpy as np
from shapely.geometry import Point, Polygon

from organizer_engine import (
    GRID_PITCH,
    WAVE_MATING_GAP,
    B4BSpec,
    BoxSpec,
    nested_clearance,
    wavy_outer_polygon,
)
from organizer_inserts import Layout
from organizer_app import (
    b4b_filename,
    design_from_dict,
    design_to_dict,
)
import organizer_b4b as b4b


CASE_WALLS = [0.4, 0.8, 1.2, 1.6, 2.0]


class B4BSpecTests(unittest.TestCase):
    def test_defaults_inert_on_ordinary_box(self):
        self.assertFalse(BoxSpec().b4b.enabled)
        self.assertEqual(BoxSpec(), BoxSpec())
        # positional construction unaffected by the new trailing field
        self.assertEqual(BoxSpec(64, 48, 40).units, (8, 6))

    def test_enum_and_snugness_validation(self):
        for bad in ("latch_count", "latch_strength", "label_location"):
            with self.assertRaises(ValueError):
                B4BSpec(**{bad: "nope"})
        with self.assertRaises(ValueError):
            B4BSpec(lid_headroom_mm=1.5)
        for good in (0.5, 1.0, 2.0):
            self.assertEqual(B4BSpec(lid_headroom_mm=good).lid_headroom_mm, good)

    def test_legacy_nolid_normalises_to_lid_only(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top", latch_count="2",
        ).normalised()
        self.assertTrue(n.lid)
        self.assertFalse(n.secure_lid)
        self.assertFalse(n.stacking)
        self.assertEqual(n.label_location, "top")
        self.assertEqual(n.latch_count, "auto")


class B4BCapacityTests(unittest.TestCase):
    def test_selected_dimensions_are_exact_child_field(self):
        for wall in CASE_WALLS:
            for ux in (2, 4, 6, 8, 10):
                for uy in (2, 6, 10):
                    box = BoxSpec(
                        x=ux * GRID_PITCH, y=uy * GRID_PITCH, z=40, wall=wall,
                        b4b=B4BSpec(enabled=True, secure_lid=False, lid=False,
                                    handle=False),
                    )
                    self.assertEqual(b4b.b4b_capacity_units(box), (ux, uy))
                    self.assertEqual(
                        b4b.b4b_capacity_mm(box),
                        (ux * GRID_PITCH, uy * GRID_PITCH),
                    )

    def test_32_by_48_means_four_by_six_child_field(self):
        # a passive lid asks nothing of the field, so 32x48 stays 32x48
        box = BoxSpec(x=32, y=48, z=40,
                      b4b=B4BSpec(enabled=True, secure_lid=False, handle=False))
        self.assertEqual(b4b.b4b_capacity_units(box), (4, 6))
        self.assertEqual(b4b.b4b_capacity_mm(box), (32, 48))

    def test_wall_thickness_changes_case_outside_not_capacity(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        thin = b4b.b4b_layout(BoxSpec(
            x=64, y=48, z=40, wall=0.4, b4b=B4BSpec(enabled=True)
        ))
        thick = b4b.b4b_layout(BoxSpec(
            x=64, y=48, z=40, wall=2.0, b4b=B4BSpec(enabled=True)
        ))
        self.assertEqual(b4b.b4b_capacity_units(box), (8, 6))
        self.assertGreater(thick.case_size[0], thin.case_size[0])
        self.assertGreater(thick.case_size[1], thin.case_size[1])

    def test_stacking_reinforces_base_only_when_on(self):
        plain = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True))
        stack = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True, stacking=True))
        self.assertEqual(b4b.b4b_effective_base_thickness(plain), plain.base_thickness)
        self.assertGreaterEqual(
            b4b.b4b_effective_base_thickness(stack),
            b4b.B4B_STACK_RECESS_DEPTH + b4b.B4B_MIN_FLOOR_SKIN,
        )


class B4BWallTests(unittest.TestCase):
    def test_outer_wall_is_derived_outward_from_inner_mating_face(self):
        for wall in CASE_WALLS:
            box = BoxSpec(x=80, y=64, z=40, wall=wall, b4b=B4BSpec(enabled=True))
            layout = b4b.b4b_layout(box)
            self.assertTrue(
                layout.outer_structural_polygon.buffer(1e-6).contains(
                    layout.inner_mating_polygon
                )
            )
            self.assertGreater(
                layout.outer_structural_polygon.difference(
                    layout.inner_mating_polygon
                ).area,
                1.0,
            )

    def test_perimeter_child_field_mates_at_the_wavefinity_gap(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        cx, cy = b4b.b4b_capacity_units(box)
        child_field = BoxSpec(x=cx * GRID_PITCH, y=cy * GRID_PITCH, z=20)
        child_outer = wavy_outer_polygon(child_field)
        mating = b4b.b4b_mating_polygon(box)
        # the child field's outer wave sits inside the mating outline, sharing
        # phase - it barely pokes past it only where corner rounding differs
        self.assertLess(child_outer.difference(mating).area, 1.0)
        # boundary-to-boundary separation is the ordinary Wavefinity mating gap
        gap = child_outer.exterior.distance(mating.exterior)
        self.assertGreater(gap, nested_clearance() - 0.05)
        self.assertLess(gap, WAVE_MATING_GAP + 0.05)

    def test_body_has_flat_floor_and_full_height_perimeter_wall(self):
        box = BoxSpec(x=32, y=48, z=30, base_thickness=0.8,
                      b4b=B4BSpec(enabled=True, secure_lid=False))
        body = b4b.make_b4b_body(box)
        layout = b4b.b4b_layout(box)
        self.assertAlmostEqual(body.bounds[0][2], 0.0, places=5)
        # The cavity begins at one flat Z plane; the perimeter is structural
        # wall all the way up rather than a short raised floor ring.
        wall_band = layout.outer_structural_polygon.difference(
            layout.inner_mating_polygon
        )
        p = wall_band.representative_point()
        self.assertTrue(body.contains([[p.x, p.y, box.z - 1.0]])[0])


class B4BLidHeadroomTests(unittest.TestCase):
    def test_lid_underside_tracks_snugness(self):
        for snug in (0.5, 1.0, 2.0):
            box = BoxSpec(
                x=64, y=48, z=40,
                b4b=B4BSpec(enabled=True, lid_headroom_mm=snug),
            )
            eff = b4b.b4b_effective_box(box)
            self.assertAlmostEqual(
                b4b.b4b_lid_underside_z(box),
                eff.base_thickness + eff.z + snug,
            )
            self.assertEqual(b4b.b4b_max_child_height(box), eff.z)


class B4BGeometryTests(unittest.TestCase):
    def test_body_and_lid_do_not_touch_when_closed(self):
        from organizer_engine import intersection_volume

        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        body = b4b.make_b4b_body(box)
        lid = b4b.make_b4b_lid(box)
        # the lid seats on its rim; the interleaved knuckles run on clearance
        self.assertLess(intersection_volume(body, lid) / 1000.0, 0.05)

    def test_lid_plate_never_exceeds_body_footprint(self):
        box = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(enabled=True))
        eff = b4b.b4b_effective_box(box)
        body_outline = b4b.b4b_layout(eff).outer_structural_polygon
        skirt_outer, skirt_inner = b4b._skirt_polygons(eff)
        # The plate is what must stay on the lattice footprint.  Hinge knuckles
        # and latch ears stand proud of it in Y on both body and lid by design,
        # so measuring the whole lid mesh in Y measures the hardware, not the
        # plate.  X is the axis B4Bs sit side by side on, and nothing may widen
        # the lid there.
        lid = b4b.make_b4b_lid(box)
        self.assertAlmostEqual(lid.bounds[0][0], body_outline.bounds[0], places=5)
        self.assertAlmostEqual(lid.bounds[1][0], body_outline.bounds[2], places=5)
        self.assertTrue(body_outline.buffer(1e-6).contains(skirt_outer))
        self.assertTrue(skirt_outer.buffer(1e-6).contains(skirt_inner))


class B4BPreviewOwnershipTests(unittest.TestCase):
    """The 3D preview's All/Base/Lid split relies on every B4B preview face
    carrying an explicit ``owner`` - "base" or "lid" - rather than being
    guessed client-side from its ``kind``. See fix3d.md."""

    def test_every_face_is_owned_and_both_groups_are_non_empty(self):
        box = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(
            enabled=True, lid=True, secure_lid=True, stacking=True,
        ))
        parts = b4b.b4b_preview_parts(box)
        self.assertTrue(parts)
        owners = {owner for _points, _kind, _normal, _layer, owner in parts}
        self.assertEqual(owners, {"base", "lid"})
        by_owner: dict[str, int] = {"base": 0, "lid": 0}
        for _points, _kind, _normal, _layer, owner in parts:
            by_owner[owner] += 1
        self.assertGreater(by_owner["base"], 0)
        self.assertGreater(by_owner["lid"], 0)

    def test_front_label_is_base_owned_top_label_is_lid_owned(self):
        front = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(
            enabled=True, lid=True, label_text="ABC", label_location="front",
        ))
        front_owners = {
            owner for _points, kind, _normal, _layer, owner
            in b4b.b4b_preview_parts(front) if kind == "b4b_label"
        }
        self.assertEqual(front_owners, {"base"})

        top = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(
            enabled=True, lid=True, label_text="ABC", label_location="top",
        ))
        top_owners = {
            owner for _points, kind, _normal, _layer, owner
            in b4b.b4b_preview_parts(top) if kind == "b4b_label"
        }
        self.assertEqual(top_owners, {"lid"})

    def test_latches_are_lid_owned_body_is_base_owned(self):
        box = BoxSpec(x=80, y=64, z=40, b4b=B4BSpec(
            enabled=True, lid=True, secure_lid=True,
        ))
        parts = b4b.b4b_preview_parts(box)
        self.assertTrue(any(kind == "b4b_latch" for _p, kind, _n, _l, _o in parts))
        for _points, kind, _normal, _layer, owner in parts:
            if kind == "b4b_latch":
                self.assertEqual(owner, "lid")
            if kind == "b4b_body":
                self.assertEqual(owner, "base")


class B4BPrintabilityTests(unittest.TestCase):
    """b4b_build_parts must emit parts that print as they stand: the body
    upright, the lid rolled onto its flat top, the levers on their broad face,
    and no supports anywhere."""

    SIZES = ((64, 48, 40, 0.8), (64, 48, 16, 0.2), (80, 64, 50, 2.0))

    def test_closed_lid_rests_on_its_rim_and_touches_nothing_else(self):
        from organizer_engine import intersection_volume

        for x, y, z, wall in self.SIZES:
            box = BoxSpec(x=x, y=y, z=z, wall=wall, b4b=B4BSpec(enabled=True))
            with self.subTest(size=(x, y, z, wall)):
                overlap = intersection_volume(
                    b4b.make_b4b_body(box), b4b.make_b4b_lid(box)
                ) / 1000.0
                self.assertLess(overlap, 0.05)


class B4BFilletTests(unittest.TestCase):
    """Hardware is filleted where it grows out of the lid plate or the body
    root web - a square internal corner is where a printed bracket cracks."""

    def test_fillet_helper_adds_material_only_in_internal_corners(self):
        ell = Polygon([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
        rounded = b4b._filleted(ell, 1.0)
        self.assertGreater(rounded.area, ell.area)
        # the internal corner is filled...
        self.assertTrue(rounded.contains(Point(4.2, 4.2)))
        # ...with an arc, not a square block
        self.assertFalse(rounded.contains(Point(4.9, 4.9)))
        # and every external corner survives untouched
        for corner in ((0.01, 0.01), (9.99, 0.01), (9.99, 3.99), (0.01, 9.99)):
            self.assertTrue(rounded.contains(Point(*corner)))


class B4BValidationTests(unittest.TestCase):
    def test_rejects_interior_features(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, layout_feature_count=1)

    def test_rejects_incompatible_settings(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, layout_mode="separate")
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, easy_clean=True)
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, flat_inside=0.5)

    def test_legacy_nolid_normalisation_keeps_lid_only(self):
        n = B4BSpec(
            enabled=True, lid=False, secure_lid=True, stacking=True,
            label_location="top",
        ).normalised()
        self.assertTrue(n.lid)
        self.assertEqual(n.label_location, "top")
        self.assertFalse(n.secure_lid)
        self.assertFalse(n.stacking)


class B4BSerializationTests(unittest.TestCase):
    def test_v1_without_b4b_loads_disabled(self):
        data = design_to_dict(BoxSpec(x=16, y=48, z=40), Layout((), "fused"))
        self.assertEqual(data["version"], 1)
        self.assertNotIn("b4b", data["box"])
        back, *_ = design_from_dict(data)
        self.assertFalse(back.b4b.enabled)

    def test_enabling_b4b_bumps_version(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertEqual(design_to_dict(box, Layout((), "fused"))["version"], 3)


class B4BGenerationTests(unittest.TestCase):
    def test_filename_distinct_from_ordinary_bin(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertNotIn("Box 64", b4b_filename(box))
        self.assertTrue(b4b_filename(box).startswith("B4B "))


if __name__ == "__main__":
    unittest.main()
