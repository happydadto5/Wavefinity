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
    def test_defaults_inert_on_ordinary_box(self):
        self.assertFalse(BoxSpec().b4b.enabled)
        self.assertEqual(BoxSpec(), BoxSpec())
        # positional construction unaffected by the new trailing field
        self.assertEqual(BoxSpec(64, 48, 40).units, (8, 6))

    def test_enum_and_snugness_validation(self):
        for bad in ("latch_count", "latch_strength", "label_location", "front_label_style"):
            with self.assertRaises(ValueError):
                B4BSpec(**{bad: "nope"})
        with self.assertRaises(ValueError):
            B4BSpec(lid_headroom_mm=1.5)
        for good in (0.5, 1.0, 2.0):
            self.assertEqual(B4BSpec(lid_headroom_mm=good).lid_headroom_mm, good)




class B4BCapacityTests(unittest.TestCase):


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



class B4BValidationTests(unittest.TestCase):
    def test_rejects_interior_features_except_single_divider(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        # Zero features accepted
        b4b.validate_b4b_design(box, layout_feature_kinds=())
        # Single divider accepted
        b4b.validate_b4b_design(box, layout_feature_kinds=("divider",))
        # Non-divider rejected
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box, layout_feature_kinds=("post",))
        self.assertIn("Dividers only", str(ctx.exception))
        # Multiple features rejected
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box, layout_feature_kinds=("divider", "divider"))
        self.assertIn("one Divider layout", str(ctx.exception))

    def test_rejects_incompatible_settings(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, layout_mode="separate")
        with self.assertRaises(ValueError):
            b4b.validate_b4b_design(box, flat_inside=0.5)

    def test_rejects_ordinary_modifiers(self):
        from organizer_engine import LiftGrabberSpec, EdgeMountSpec, SideOpeningSpec
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True), lift_grabbers=LiftGrabberSpec(enabled=True))
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box)
        self.assertIn("Inside Grip is not available", str(ctx.exception))

        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True), edge_mount=EdgeMountSpec(side="front", label_enabled=True))
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box)
        self.assertIn("Edge Mount is not available", str(ctx.exception))

        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True), side_openings=SideOpeningSpec(enabled=True, sides=("front",)))
        with self.assertRaises(ValueError) as ctx:
            b4b.validate_b4b_design(box)
        self.assertIn("Side Openings are not available", str(ctx.exception))



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

    def test_front_label_style_round_trips(self):
        box = BoxSpec(x=64, y=48, z=40, wall=1.2, b4b=B4BSpec(
            enabled=True, label_text="NUTS", label_location="front",
            front_label_style="wavy",
        ))
        data = design_to_dict(box, Layout((), "fused"))
        self.assertEqual(data["box"]["b4b"]["front_label_style"], "wavy")
        back, *_ = design_from_dict(data)
        self.assertEqual(back.b4b.front_label_style, "wavy")



class B4BGenerationTests(unittest.TestCase):
    def test_filename_distinct_from_ordinary_bin(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertFalse(b4b_filename(box).startswith("Box "))
        self.assertTrue(b4b_filename(box).startswith("Storage Box "))


class B4B3MFHierarchyTests(unittest.TestCase):
    """B4B exports retain only deliberate multi-part Bambu objects."""

    @staticmethod
    def _local(node) -> str:
        return node.tag.rsplit("}", 1)[-1]

    def _export_hierarchy(
        self, b4b_spec: B4BSpec, x: float = 128, y: float = 80, z: float = 64,
    ) -> dict[str, object]:
        box = BoxSpec(x=x, y=y, z=z, wall=1.2, b4b=b4b_spec)
        with tempfile.TemporaryDirectory() as directory:
            result = generate_b4b_files(box, Path(directory), "Hierarchy")
            with zipfile.ZipFile(result["output"]) as archive:
                model_file = next(
                    name for name in archive.namelist()
                    if name.lower().endswith(".model")
                )
                root = ElementTree.fromstring(archive.read(model_file))
                config = ElementTree.fromstring(
                    archive.read("Metadata/model_settings.config")
                )

        resources = next(node for node in root if self._local(node) == "resources")
        build = next(node for node in root if self._local(node) == "build")
        objects = {
            node.get("id"): node
            for node in resources
            if self._local(node) == "object"
        }
        top: dict[str, dict[str, object]] = {}
        for item in build:
            if self._local(item) != "item":
                continue
            obj = objects[item.get("objectid")]
            children = [
                objects[child.get("objectid")].get("name")
                for child in obj.iter()
                if self._local(child) == "component"
            ]
            top[obj.get("name")] = {
                "mesh": any(self._local(child) == "mesh" for child in obj),
                "children": children,
            }

        components = {
            node.get("name"): [
                objects[child.get("objectid")].get("name")
                for child in node.iter()
                if self._local(child) == "component"
            ]
            for node in objects.values()
            if any(self._local(child) == "components" for child in node)
        }
        filaments: dict[str, int] = {}
        for config_object in config.iter():
            if self._local(config_object) != "object":
                continue
            default_slot = 1
            for meta in config_object:
                if self._local(meta) == "metadata" and meta.get("key") == "extruder":
                    default_slot = int(meta.get("value", "1"))
            for part in config_object:
                if self._local(part) != "part":
                    continue
                name, slot = "", default_slot
                for meta in part:
                    if self._local(meta) != "metadata":
                        continue
                    if meta.get("key") == "name":
                        name = meta.get("value", "")
                    elif meta.get("key") == "extruder":
                        slot = int(meta.get("value", "1"))
                if name:
                    filaments[name] = slot
        return {"top": top, "components": components, "filaments": filaments}

    def _assert_direct(self, hierarchy, name: str) -> None:
        part = hierarchy["top"][name]
        self.assertTrue(part["mesh"], name)
        self.assertEqual(part["children"], [], name)

    def test_secure_unlabelled_b4b_has_only_direct_print_objects(self):
        hierarchy = self._export_hierarchy(B4BSpec(
            enabled=True, secure_lid=True, handle=True, label_location="top",
        ), x=200, y=120, z=80)
        self.assertGreater(len(hierarchy["top"]), 1)
        self.assertEqual(hierarchy["components"], {})
        self._assert_direct(hierarchy, "Storage Box Body")
        self._assert_direct(hierarchy, "Storage Box Lid")
        self._assert_direct(hierarchy, "Storage Box Handle")
        latches = [name for name in hierarchy["top"] if name.startswith("Storage Box Latch ")]
        self.assertTrue(latches)
        for name in latches:
            self._assert_direct(hierarchy, name)





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




class B4BFrontLabelInsertCorridorTests(unittest.TestCase):
    """With no retention feature, the plate must be free to lift all the way
    out, not just drop in once - see ``_b4b_front_label_bottom_z``."""

    def test_geometry_succeeds_exactly_when_eligibility_says_so(self):
        for z in (16, 20, 24, 30, 40, 55):
            box = _front_label_box("flat", z=z)
            eligible, _reason = b4b.b4b_front_label_eligibility(box)
            if eligible:
                b4b.b4b_front_label_geometry(box)  # must not raise
            else:
                with self.assertRaises(ValueError):
                    b4b.b4b_front_label_geometry(box)


class B4BFrontLabelWavyGeometryTests(unittest.TestCase):
    def setUp(self):
        self.box = _front_label_box("wavy")
        self.frame, self.plate, self.text, self.centre = b4b.b4b_front_label_geometry(
            self.box
        )

    def test_watertight_and_positive_volume(self):
        self.assertTrue(self.plate.is_watertight)
        self.assertGreater(self.plate.volume, 0.0)
        self.assertTrue(self.frame.is_watertight)



    def test_centre_face_carries_the_exact_wavefinity_wave(self):
        plate_w = self.plate.bounds[1][0] - self.plate.bounds[0][0]
        plate_h = self.plate.bounds[1][2] - self.plate.bounds[0][2]
        front_y = b4b._b4b_wavy_front_y(plate_w, plate_h, b4b.B4B_FRONT_LABEL_PLATE_T)
        flat_y = -b4b.B4B_FRONT_LABEL_PLATE_T / 2.0
        for x in np.linspace(-plate_w / 4.0, plate_w / 4.0, 7):
            self.assertAlmostEqual(
                front_y(float(x), 0.0), flat_y + wave_value(float(x)), places=6,
            )



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



class B4BDividerAndMaterialTests(unittest.TestCase):



    def test_b4b_divider_round_trip(self):
        from organizer_inserts import Feature, Zone
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        feat = Feature("divider", Zone(-32, -24, 32, 24), full_span=True, options={"count_x": 1, "count_y": 1})
        data = design_to_dict(box, Layout((feat,), "fused"))
        back_box, back_layout, *_ = design_from_dict(data)
        self.assertEqual(len(back_layout.features), 1)
        self.assertEqual(back_layout.features[0].kind, "divider")
        self.assertEqual(back_layout.features[0].zone, Zone(-32, -24, 32, 24))







    def test_b4b_build_print_objects_with_divider(self):
        from organizer_inserts import Feature, Zone
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True, lid=False))
        feat = Feature("divider", Zone(-32, -24, 32, 24), full_span=True, options={"count_x": 1, "count_y": 1})
        objs_no_div = b4b.b4b_build_print_objects(box, ())
        objs_with_div = b4b.b4b_build_print_objects(box, (feat,))
        self.assertEqual(len(objs_no_div), len(objs_with_div))
        body_no_parts = next(
            parts for object_name, parts in objs_no_div
            if object_name == "Storage Box Body"
        )
        body_with_parts = next(
            parts for object_name, parts in objs_with_div
            if object_name == "Storage Box Body"
        )
        body_no = next(
            mesh for part_name, mesh in body_no_parts
            if part_name == "Storage Box Body"
        )
        body_with = next(
            mesh for part_name, mesh in body_with_parts
            if part_name == "Storage Box Body"
        )

        self.assertGreater(body_with.volume, body_no.volume)
        self.assertFalse(any(
            object_name == "Divider"
            for object_name, _parts in objs_with_div
        ))


if __name__ == "__main__":
    unittest.main()
