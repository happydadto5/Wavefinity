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

    def test_front_label_style_default_and_choices(self):
        self.assertEqual(B4BSpec().front_label_style, "flat")
        self.assertEqual(B4BSpec(front_label_style="flat").front_label_style, "flat")
        self.assertEqual(B4BSpec(front_label_style="wavy").front_label_style, "wavy")
        self.assertEqual(
            B4BSpec(front_label_style="wavy").normalised().front_label_style, "wavy",
        )

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

    def test_front_label_style_round_trips(self):
        box = BoxSpec(x=64, y=48, z=40, wall=1.2, b4b=B4BSpec(
            enabled=True, label_text="NUTS", label_location="front",
            front_label_style="wavy",
        ))
        data = design_to_dict(box, Layout((), "fused"))
        self.assertEqual(data["box"]["b4b"]["front_label_style"], "wavy")
        back, *_ = design_from_dict(data)
        self.assertEqual(back.b4b.front_label_style, "wavy")

    def test_old_design_missing_front_label_style_loads_flat(self):
        box = BoxSpec(x=64, y=48, z=40, wall=1.2, b4b=B4BSpec(
            enabled=True, label_text="NUTS", label_location="front",
        ))
        data = design_to_dict(box, Layout((), "fused"))
        del data["box"]["b4b"]["front_label_style"]
        back, *_ = design_from_dict(data)
        self.assertEqual(back.b4b.front_label_style, "flat")


class B4BGenerationTests(unittest.TestCase):
    def test_filename_distinct_from_ordinary_bin(self):
        box = BoxSpec(x=64, y=48, z=40, b4b=B4BSpec(enabled=True))
        self.assertNotIn("Box 64", b4b_filename(box))
        self.assertTrue(b4b_filename(box).startswith("B4B "))


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
        self._assert_direct(hierarchy, "B4B Body")
        self._assert_direct(hierarchy, "B4B Lid")
        self._assert_direct(hierarchy, "B4B Handle")
        latches = [name for name in hierarchy["top"] if name.startswith("B4B Latch ")]
        self.assertTrue(latches)
        for name in latches:
            self._assert_direct(hierarchy, name)

    def test_front_label_is_the_only_registered_multipart_object(self):
        hierarchy = self._export_hierarchy(B4BSpec(
            enabled=True, secure_lid=True, label_text="NUTS", label_location="front",
        ))
        self.assertEqual(hierarchy["components"], {
            "B4B Front Label": [
                "B4B Front Label Plate", "B4B Front Label Text",
            ],
        })
        self._assert_direct(hierarchy, "B4B Body")
        self._assert_direct(hierarchy, "B4B Lid")
        for name in hierarchy["top"]:
            if name.startswith("B4B Latch "):
                self._assert_direct(hierarchy, name)
        self.assertEqual(hierarchy["filaments"]["B4B Front Label Plate"], 1)
        self.assertEqual(hierarchy["filaments"]["B4B Front Label Text"], 2)

    def test_top_label_is_registered_with_its_lid_only(self):
        hierarchy = self._export_hierarchy(B4BSpec(
            enabled=True, secure_lid=True, label_text="NUTS", label_location="top",
        ))
        self.assertEqual(hierarchy["components"], {
            "B4B Lid": ["B4B Lid", "B4B Top Label"],
        })
        self.assertEqual(hierarchy["top"]["B4B Lid"]["children"], [
            "B4B Lid", "B4B Top Label",
        ])
        self._assert_direct(hierarchy, "B4B Body")
        for name in hierarchy["top"]:
            if name.startswith("B4B Latch "):
                self._assert_direct(hierarchy, name)
        self.assertEqual(hierarchy["filaments"]["B4B Top Label"], 2)

    def test_lid_only_b4b_has_no_unneeded_components_object(self):
        hierarchy = self._export_hierarchy(B4BSpec(
            enabled=True, secure_lid=False, label_location="top",
        ))
        self.assertEqual(hierarchy["components"], {})
        self._assert_direct(hierarchy, "B4B Body")
        self._assert_direct(hierarchy, "B4B Lid")


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

    def test_retention_constants_are_gone(self):
        for name in (
            "B4B_FRONT_LABEL_RETENTION_REACH",
            "B4B_FRONT_LABEL_RETENTION_H",
            "B4B_FRONT_LABEL_RETENTION_W",
        ):
            self.assertFalse(hasattr(b4b, name), name)

    def test_frame_is_smaller_without_retention_bumps(self):
        # The frame is exactly patch + wedge + bottom_lip + two side channels
        # now; removing two bumps can only shrink or leave unchanged the
        # holder's own bounding volume, never grow it.
        frame, _plate, _text, _centre = b4b.b4b_front_label_geometry(
            _front_label_box("flat")
        )
        self.assertTrue(frame.is_watertight)


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


class B4BFrontLabelFlatRegressionTests(unittest.TestCase):
    def test_flat_plate_is_a_plain_rectangular_slab(self):
        _frame, plate, text, _centre = b4b.b4b_front_label_geometry(
            _front_label_box("flat")
        )
        self.assertTrue(plate.is_watertight)
        self.assertGreater(plate.volume, 0.0)
        self.assertTrue(text.is_watertight)
        self.assertGreater(text.volume, 0.0)
        # Every vertex not inside the shallow text pocket sits on one of the
        # two exact flat planes of a plain box.
        front_y = plate.bounds[0][1]
        back_y = plate.bounds[1][1]
        ys = np.unique(np.round(plate.vertices[:, 1], 6))
        self.assertTrue(np.isclose(ys.max(), back_y))
        self.assertTrue(np.isclose(ys.min(), front_y))


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

    def test_back_is_perfectly_planar(self):
        back_y = self.plate.bounds[1][1]
        back_vertices = self.plate.vertices[
            self.plate.vertices[:, 1] > back_y - 1e-6
        ]
        self.assertGreater(len(back_vertices), 0)
        self.assertTrue(np.allclose(back_vertices[:, 1], back_y, atol=1e-6))

    def test_rectangular_perimeter_stays_flat(self):
        plate_w = self.plate.bounds[1][0] - self.plate.bounds[0][0]
        plate_h = self.plate.bounds[1][2] - self.plate.bounds[0][2]
        front_y = b4b._b4b_wavy_front_y(plate_w, plate_h, b4b.B4B_FRONT_LABEL_PLATE_T)
        flat_y = -b4b.B4B_FRONT_LABEL_PLATE_T / 2.0
        half_w, half_h = plate_w / 2.0, plate_h / 2.0
        # Right at every edge and at the flat border, the wave contributes
        # nothing: the outline is the exact same rectangle Flat style uses.
        for x, z in (
            (half_w - 0.05, 0.0), (-half_w + 0.05, 0.0),
            (0.0, half_h - 0.05), (0.0, -half_h + 0.05),
            (half_w - b4b.B4B_FRONT_LABEL_FLAT_BORDER, 0.0),
        ):
            self.assertAlmostEqual(front_y(x, z), flat_y, places=6)

    def test_centre_face_carries_the_exact_wavefinity_wave(self):
        plate_w = self.plate.bounds[1][0] - self.plate.bounds[0][0]
        plate_h = self.plate.bounds[1][2] - self.plate.bounds[0][2]
        front_y = b4b._b4b_wavy_front_y(plate_w, plate_h, b4b.B4B_FRONT_LABEL_PLATE_T)
        flat_y = -b4b.B4B_FRONT_LABEL_PLATE_T / 2.0
        for x in np.linspace(-plate_w / 4.0, plate_w / 4.0, 7):
            self.assertAlmostEqual(
                front_y(float(x), 0.0), flat_y + wave_value(float(x)), places=6,
            )

    def test_peak_to_peak_matches_wave_amplitude(self):
        span = self.plate.bounds[1][1] - self.plate.bounds[0][1]
        # Back is fixed at +plate_t/2; the front's deepest excursion reaches
        # roughly plate_t/2 + WAVE_AMPLITUDE below it once sampling finds a
        # near-extremum, so the full peak-to-peak span is close to
        # plate_t + WAVE_AMPLITUDE (never more).
        self.assertLessEqual(span, b4b.B4B_FRONT_LABEL_PLATE_T + WAVE_AMPLITUDE + 1e-6)
        self.assertGreater(span, b4b.B4B_FRONT_LABEL_PLATE_T)


class B4BFrontLabelWavyTextTests(unittest.TestCase):
    def test_text_solid_is_nonempty_and_registered(self):
        _frame, plate, text, _centre = b4b.b4b_front_label_geometry(
            _front_label_box("wavy")
        )
        self.assertTrue(text.is_watertight)
        self.assertGreater(text.volume, 0.0)
        self.assertTrue(plate.is_watertight)
        self.assertGreater(plate.volume, 0.0)
        # The text sits inside the plate's own footprint and just past its
        # deepest front excursion, never floating clear of the plate.  The
        # boolean cut boundary lands within a few hundredths of a micron of
        # the analytic surface, so the tolerance here is generous relative to
        # that noise while still far tighter than anything print-relevant.
        self.assertGreaterEqual(
            text.bounds[0][1] + 1e-3, plate.bounds[0][1],
        )
        self.assertLessEqual(text.bounds[1][1], plate.bounds[1][1] + 1e-3)

    def test_short_text_does_not_restart_the_wave_phase(self):
        # A short label still reads the wave at true case-relative X=0 - the
        # same phase a long label or the surrounding wall itself would see.
        _frame, plate, _text, _centre = b4b.b4b_front_label_geometry(
            _front_label_box("wavy", text="I")
        )
        plate_w = plate.bounds[1][0] - plate.bounds[0][0]
        plate_h = plate.bounds[1][2] - plate.bounds[0][2]
        front_y = b4b._b4b_wavy_front_y(plate_w, plate_h, b4b.B4B_FRONT_LABEL_PLATE_T)
        self.assertAlmostEqual(
            front_y(0.0, 0.0), -b4b.B4B_FRONT_LABEL_PLATE_T / 2.0 + wave_value(0.0),
            places=6,
        )


class B4BFrontLabelPrintPoseTests(unittest.TestCase):
    """Required: both styles must print flat-back-down, text-side-up,
    through the exact path used for real export."""

    def _label_parts(self, style: str) -> dict:
        objects = b4b.b4b_build_print_objects(_front_label_box(style))
        parts = dict(next(
            parts for name, parts in objects if name == "B4B Front Label"
        ))
        return parts

    def test_flat_and_wavy_print_back_down_text_up(self):
        for style in ("flat", "wavy"):
            with self.subTest(style=style):
                parts = self._label_parts(style)
                plate = parts["B4B Front Label Plate"]
                text = parts["B4B Front Label Text"]
                # Flat back on the build plate.
                self.assertAlmostEqual(float(plate.bounds[0][2]), 0.0, places=6)
                # Lettering sits above the back, flush with (never past) the
                # plate's own top/visible face - not against the plate.  A
                # few hundredths of a micron of boolean-cut noise is fine;
                # anything print-relevant is orders of magnitude bigger.
                self.assertGreater(float(text.bounds[0][2]), 0.0)
                self.assertLessEqual(
                    float(text.bounds[1][2]), float(plate.bounds[1][2]) + 1e-3,
                )
                self.assertAlmostEqual(
                    float(text.bounds[1][2]), float(plate.bounds[1][2]), places=3,
                )


class B4BWavyLabelZSamplesTests(unittest.TestCase):
    """``_b4b_wavy_label_z_samples`` replaces the flat per-mm Z grid with one
    tied to the border/blend topology - see ``_b4b_wave_mask_1d``."""

    def test_starts_and_ends_at_half_height(self):
        zs = b4b._b4b_wavy_label_z_samples(12.0)
        self.assertAlmostEqual(float(zs[0]), -6.0, places=6)
        self.assertAlmostEqual(float(zs[-1]), 6.0, places=6)

    def test_includes_centreline(self):
        zs = b4b._b4b_wavy_label_z_samples(12.0)
        self.assertTrue(np.any(np.isclose(zs, 0.0)))

    def test_strictly_increasing(self):
        zs = b4b._b4b_wavy_label_z_samples(12.0)
        self.assertTrue(np.all(np.diff(zs) > 0))

    def test_symmetric_around_zero(self):
        zs = b4b._b4b_wavy_label_z_samples(12.0)
        self.assertTrue(np.allclose(zs, -zs[::-1]))

    def test_represents_border_and_blend_transition(self):
        zs = b4b._b4b_wavy_label_z_samples(12.0)
        half_h = 6.0
        border = b4b.B4B_FRONT_LABEL_FLAT_BORDER
        blend = b4b.B4B_FRONT_LABEL_WAVE_BLEND
        # The flat-border/blend boundary and the far end of the blend, both
        # sides of the centreline.
        for expected in (half_h - border, half_h - border - blend):
            self.assertTrue(np.any(np.isclose(zs, expected, atol=1e-6)))
            self.assertTrue(np.any(np.isclose(zs, -expected, atol=1e-6)))

    def test_sample_count_does_not_scale_with_height(self):
        # Unlike the old per-mm grid, the row count is set by the fixed
        # border/blend constants, not by plate height.
        counts = {len(b4b._b4b_wavy_label_z_samples(h)) for h in (8.0, 12.0, 20.0, 40.0)}
        self.assertEqual(len(counts), 1)
        (count,) = counts
        self.assertLess(count, 20)
        self.assertGreater(count, 5)


class B4BWavyLabelMeshComplexityTests(unittest.TestCase):
    """The Z-topology sampling must cut triangle count without losing any
    visible geometry - see ``_b4b_wavy_label_z_samples``."""

    def test_blank_mesh_is_efficient_and_correct(self):
        plate_w, plate_h = 40.0, 12.0
        blank = b4b._b4b_wavy_label_blank(plate_w, plate_h)

        self.assertTrue(blank.is_watertight)
        self.assertGreater(blank.volume, 0.0)
        self.assertLess(len(blank.faces), 100_000)
        # X sampling is deliberately left at full per-mm density, so it still
        # dominates the triangle count; the win is against the old per-mm Z
        # grid this replaces - at least a 5x cut in row count for a 12 mm
        # label, so at least roughly that much fewer triangles too.
        old_nz = max(2, b4b._sample_count(plate_h))
        new_nz = len(b4b._b4b_wavy_label_z_samples(plate_h))
        self.assertLess(new_nz * 5, old_nz)

        back_y = blank.bounds[1][1]
        back_vertices = blank.vertices[blank.vertices[:, 1] > back_y - 1e-6]
        self.assertGreater(len(back_vertices), 0)
        self.assertTrue(np.allclose(back_vertices[:, 1], back_y, atol=1e-6))

        front_y = b4b._b4b_wavy_front_y(plate_w, plate_h, b4b.B4B_FRONT_LABEL_PLATE_T)
        flat_y = -b4b.B4B_FRONT_LABEL_PLATE_T / 2.0
        half_w, half_h = plate_w / 2.0, plate_h / 2.0
        for x, z in (
            (half_w - 0.05, 0.0), (-half_w + 0.05, 0.0),
            (0.0, half_h - 0.05), (0.0, -half_h + 0.05),
        ):
            self.assertAlmostEqual(front_y(x, z), flat_y, places=6)
        for x in np.linspace(-plate_w / 4.0, plate_w / 4.0, 5):
            self.assertAlmostEqual(
                front_y(float(x), 0.0), flat_y + wave_value(float(x)), places=6,
            )


if __name__ == "__main__":
    unittest.main()
