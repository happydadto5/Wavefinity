"""Parametric geometry engine for the wavy-wall drawer organizer system.

All dimensions are millimetres.  This module is the single source of truth for
the browser app, command-line tools, fit sampler, and automated tests.

Design summary
--------------
* Boxes tile on a plain ``x`` by ``y`` grid.  Their solid outline is smaller
  than that pitch by ``WAVE_MATING_GAP`` so neighbouring wavy walls interlock
  with a constant gap.
* The wave is a fixed-pitch sine: ``WAVE_LENGTH`` mm per full cycle (out and
  back) and ``WAVE_AMPLITUDE`` mm of deviation each way.  It runs at full
  amplitude the whole length of every wall, straight into the corners; there
  is no corner blend.  Corners are a short chamfer rounded to
  ``CORNER_FILLET``.
* Connectors: the **side connector**, a staple that drops over the seam
  between two boxes, plus compact **3-Way / 4-Way Corner** connectors.  All share
  the same wall-following fit profile; the compact corner types deliberately do
  not use the side connector's variable-height web.
* Each wall carries small chamfered **lock bumps** on its interior face; the
  connector arms have matching notches so the clip locks in.  Every bump and
  notch face is chamfered at 45 degrees or shallower, so both parts print
  without supports.
"""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_geometry import (
    _cleaned,
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    _sweep_profile,
    difference,
    intersection,
    translated,
    union,
)
from organizer_pegboard import PegboardMountSpec

from pathlib import Path
import numpy as np
import trimesh

from ._specs import (
    WAVE_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    SAMPLES_PER_MM,
    GRID_PITCH,
    MIN_BOX_SIZE,
    MAX_BOX_SIZE,
    BASE_UNIT,
    DEFAULT_WALL,
    MIN_WALL,
    MAX_WALL,
    WALL_STEP,
    WALL_PRESETS,
    B4B_MATERIAL_PRESETS,
    B4B_WALL_PRESETS,
    B4B_BASE_PRESETS,
    B4B_DEFAULT_WALL,
    B4B_DEFAULT_BASE,
    DEFAULT_BASE_THICKNESS,
    BASE_PRESETS,
    DEFAULT_CORNER_FILLET,
    CORNER_INSET,
    LOCKED_TOLERANCE,
    LOCKED_CONNECTOR_HEIGHT,
    LOCKED_CONNECTOR_LENGTH,
    MIN_JOINABLE_SIZE,
    CORNER_CONNECTOR_ARM_START,
    CORNER_CONNECTOR_END,
    DEFAULT_CONNECTOR_HEIGHT,
    DEFAULT_CAP_THICKNESS,
    DEFAULT_ARM_THICKNESS,
    DEFAULT_SIDE_LENGTH,
    DIFFERING_MIN_DROP,
    DIFFERING_FULL_DROP,
    DIFFERING_WEB_THICKNESS,
    DIFFERING_LENGTH_GAIN,
    DIFFERING_WEB_TAPER,
    DIFFERING_WEB_RUN_CLEARANCE,
    differing_drop_fraction,
    differing_web_reach,
    differing_connector_plan,
    LOCK_PROTRUSION,
    LOCK_FLAT,
    LOCK_CHAMFER,
    LOCK_RUN,
    LOCK_SPACING,
    LOCK_CORNER_CLEAR,
    LOCK_TOP_BELOW_RIM,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    LOCK_NOTCH_CLEARANCE,
    connector_arm_thickness_floor,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_CAP_HEIGHT_MIN,
    TEXT_CAP_HEIGHT_FLOOR,
    TEXT_DEPTH,
    EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
    TEXT_MIN_BACKING,
    TEXT_MARGIN,
    TEXT_FONT_FAMILY,
    TEXT_FONT_WEIGHT,
    TOP_LABEL_LEDGE_DEPTH,
    TOP_LABEL_CAP_HEIGHT,
    TOP_LABEL_CAP_HEIGHT_WARNING,
    TOP_LABEL_MARGIN,
    TOP_LABEL_RIM_CLEARANCE,
    SCOOP_HEIGHT_FRACTION,
    SCOOP_FLOOR_TOLERANCE,
    SCOOP_CURVE_SEGMENTS,
    B4B_LID_HEADROOM_CHOICES,
    B4B_LATCH_COUNTS,
    B4B_LATCH_STRENGTHS,
    B4B_LABEL_LOCATIONS,
    B4B_FRONT_LABEL_STYLES,
    B4B_SCHEMA_VERSION,
    STACK_MODES,
    StackSpec,
    LID_THICKNESSES,
    LID_LABEL_STYLES,
    LID_LABEL_ORIENTATIONS,
    LID_HANDLE_TYPES,
    LID_HANDLE_SIZES,
    LID_HANDLE_POSITIONS,
    LID_FITS,
    LID_FIT_MM,
    LID_FIT_NAMES,
    LID_LABEL_RELIEFS,
    LID_LABEL_RELIEF_NAMES,
    LID_LABEL_LEGACY_INLAY_MM,
    LID_LABEL_LEGACY_RAISED_MM,
    LidSpec,
    lid_fit_mm,
    lid_label_relief_mm,
    lid_spec,
    lid_enabled,
    lid_stackable,
    lid_has_handle,
    direct_stack_enabled,
    vertical_stack_enabled,
    B4BSpec,
    LIFT_GRABBER_SIZES,
    LIFT_GRABBER_LOCATIONS,
    LIFT_GRABBER_RIM_CLEARANCE,
    LIFT_GRABBER_FLOOR_CLEARANCE,
    LIFT_GRABBER_WALL_MARGIN,
    LIFT_GRABBER_MIN_ROOT_BITE,
    LiftGrabberDimensions,
    LIFT_GRABBER_DIMENSIONS,
    LiftGrabberSpec,
    MIN_HEIGHT_ABOVE_BASE,
    EdgeMountSpec,
    SIDE_OPENING_SHAPES,
    SIDE_OPENING_SIZES,
    SIDE_OPENING_WIDTHS,
    SIDE_OPENING_SIDES,
    SideOpeningSpec,
    BoxSpec,
    ConnectorSpec,
    max_wave_slope,
    wall_depth_for,
)
from ._wave import (
    nested_clearance,
    wave_value,
    wave_cycles,
    lock_positions,
    lock_lattice,
    _sample_count,
    _wall_points,
    _rounded,
    preview_rings,
    wavy_rect_outer,
    wavy_outer_polygon,
    wavy_rect_cavity,
    wavy_cavity_polygon,
    placed_outline,
    mating_clearance,
    lock_z_levels,
    _lock_profile,
    _rect_wall_lock_paths,
    _wall_lock_paths,
    make_wall_lock_bumps_raw,
    make_wall_lock_bumps,
    wall_lock_receivers,
    _LIFT_GRABBER_WALL_LABELS,
    _wall_face_table,
)
from ._lift_grabbers import (
    _lift_grabber_height_curve,
    _lift_grabber_profile,
    _lift_grabber_width_ease,
    _lift_grabber_bulge_mesh,
    _place_lift_grabber,
    _lift_grabber_embed_depth,
    lift_grabber_min_wall,
    validate_lift_grabbers,
    make_lift_grabbers,
    lift_grabber_keep_outs,
    lift_grabber_collision_volumes,
    lift_grabber_summary,
)
from ._boxes import (
    flat_cavity_polygon,
    make_box,
    connector_half_widths,
    connector_bin_heights,
    connector_fits,
    joinable_sides,
    _connector_corridor_polygon,
    _validate_connector_arm_clearance,
    make_side_connector,
    _arm_notches,
    _connector_arm_notches,
    _corner_connector_direction,
    _corner_connector_branches,
    make_corner_connector,
    connector_for_print,
)
from ._fit import (
    mesh_report,
    mesh_fingerprint,
    intersection_volume,
    installed_boxes,
    installed_side_boxes,
    seat_transform,
    validate_side_fit,
    installed_corner_boxes,
    validate_corner_fit,
    _plain_corridor,
)
from ._export import (
    BAMBU_PACKAGE_REL,
    TEXT_PART_FILAMENT,
    _xml_attr,
    _stamp_identity,
    _strict_write,
    export_bambu_compatible_3mf,
    _model_settings_config,
    _object_groups_model_settings_config,
    assigned_filaments,
    label_mesh_report,
    unique_object_names,
    export_text_body_3mf,
    export_labelled_box,
    export_assembly_3mf,
    export_object_groups_3mf,
    export_mesh,
    validate_3mf,
    validate_object_groups_3mf,
)
from ._labels import (
    _font,
    _cap_ratio,
    text_outline,
    _rim_label_side,
    top_label_surface_z,
    top_label_zone,
    _top_label_fit,
    top_label_outline,
    make_top_label_ledge,
    make_top_label,
    make_top_labelled_box,
    _scoop_bounds,
    scoop_dimensions,
    scoop_floor_zone,
    scoop_keep_out,
    make_scoop,
    build_scoop_region,
    LabelPlacement,
    _label_candidates,
    _oriented_outline,
    _cap_steps,
    label_placement,
    label_layout,
    placed_label_outline,
    require_text_backing,
    text_prism,
    make_floor_label,
    make_labelled_box,
    label_report,
    top_label_report,
)

def measure_lock(
    box: BoxSpec,
    connector: ConnectorSpec,
    along_axis: str = "y",
    position: float = 0.0,
    lifts: tuple[float, ...] = (0.0, 0.5, 1.5),
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
) -> dict[str, float]:
    """Seated clearance, and the interference met while lifting the clip out.

    A seated clip is free; raising it drives the arm notches onto the bumps,
    which is the lock.  Also reports what a notch-less arm would hit, proving
    the bumps stand in the arm's path at all.
    """
    axis = along_axis.lower()
    heights = connector_bin_heights(box, bin_a_height, bin_b_height)
    boxes = installed_side_boxes(box, axis, *heights)
    clip = make_side_connector(
        box, connector, axis, position, DEFAULT_SIDE_LENGTH, *heights
    )
    base = seat_transform(box, connector, position, axis, max(heights))

    result: dict[str, float] = {}
    for lift in lifts:
        placed = translated(clip, (base[0], base[1], base[2] + lift))
        result[f"lift_{lift:.1f}_mm3"] = round(
            sum(intersection_volume(placed, item) for item in boxes), 6
        )

    inner_hw, outer_hw = connector_half_widths(box, connector)
    samples = np.linspace(-DEFAULT_SIDE_LENGTH / 2.0, DEFAULT_SIDE_LENGTH / 2.0, 5)
    plain_body = _extrude_polygon(
        _plain_corridor(box, axis, position, samples, outer_hw), connector.height
    )
    plain_channel = _extrude_polygon(
        _plain_corridor(box, axis, position, samples, inner_hw), connector.arm_depth
    )
    plain = translated(difference([plain_body, plain_channel]), base)
    result["no_notch_mm3"] = round(
        sum(intersection_volume(plain, item) for item in boxes), 6
    )
    result["protrusion_mm"] = LOCK_PROTRUSION
    return result


# --------------------------------------------------------------------------- #
# sampler
# --------------------------------------------------------------------------- #
def make_sampler_scene(
    sizes: tuple[tuple[float, float], ...] = (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ),
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
    base_thickness: float = DEFAULT_BASE_THICKNESS,
) -> trimesh.Scene:
    """Assembly sample: one box per requested size, plus a row of connectors.

    The connector is a single locked part now, so the row is simply ``clips``
    copies of it rather than a tolerance sweep.
    """
    if clips < 1:
        raise ValueError("the sample needs at least one connector")
    scene = trimesh.Scene()
    scene.units = "mm"
    gap = 6.0

    boxes = []
    for size_x, size_y in sizes:
        spec = BoxSpec(
            x=size_x, y=size_y, z=height, wall=wall, flat_inside=flat_inside,
            base_thickness=base_thickness,
        )
        mesh = make_box(spec)
        mesh_report(f"sample box {size_x:g}x{size_y:g}", mesh)
        boxes.append((spec, mesh))

    cursor = 0.0
    depth = max(float(m.extents[1]) for _, m in boxes)
    for spec, mesh in boxes:
        centre = mesh.bounds.mean(axis=0)
        width = float(mesh.extents[0])
        placed = translated(
            mesh,
            (cursor + width / 2.0 - centre[0], -centre[1], -mesh.bounds[0][2]),
        )
        ux, uy = spec.units
        name = f"box_{ux:g}x{uy:g}_{spec.x:g}x{spec.y:g}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
        cursor += width + gap
    total_width = cursor - gap

    # Use a real sampler bin rather than a fresh default-size BoxSpec. Thick
    # walls leave less room at a 16 mm bin's rounded corners, even though the
    # same connector is valid on the sampler's longer wall.
    clip_box = max(boxes, key=lambda item: item[0].y)[0]
    clip = make_side_connector(clip_box, connector, "y", 0.0, side_length)
    validate_side_fit(
        clip_box, connector, clip, "y",
    )
    clip = connector_for_print(clip)
    mesh_report("sample connector", clip)
    cell = float(clip.extents[0]) + 6.0
    row_y = -depth / 2.0 - gap - float(clip.extents[1]) / 2.0
    for index in range(clips):
        centre = clip.bounds.mean(axis=0)
        target = total_width / 2.0 + (index - (clips - 1) / 2.0) * cell
        placed = translated(
            clip,
            (target - centre[0], row_y - centre[1], -clip.bounds[0][2]),
        )
        name = f"connector_{index + 1}"
        scene.add_geometry(placed, node_name=name, geom_name=name)
    return scene


def generate_sampler(
    output: Path,
    sizes: tuple[tuple[float, float], ...] | None = None,
    height: float = 40.0,
    wall: float = DEFAULT_WALL,
    connector: ConnectorSpec = ConnectorSpec(),
    clips: int = 5,
    side_length: float = DEFAULT_SIDE_LENGTH,
    flat_inside: float = 0.0,
    base_thickness: float = DEFAULT_BASE_THICKNESS,
) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "height": height, "wall": wall, "base_thickness": base_thickness,
        "connector": connector,
        "clips": clips, "side_length": side_length, "flat_inside": flat_inside,
    }
    if sizes is not None:
        kwargs["sizes"] = sizes
    scene = make_sampler_scene(**kwargs)
    export_bambu_compatible_3mf(scene, output)
    report = validate_3mf(output, len(scene.geometry))
    report["boxes"] = [f"{sx:g}x{sy:g}" for sx, sy in (sizes or (
        (2.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (4.0 * BASE_UNIT, 6.0 * BASE_UNIT),
        (6.0 * BASE_UNIT, 6.0 * BASE_UNIT),
    ))]
    report["connectors"] = clips
    report["tolerance_mm"] = connector.tolerance
    report["connector_height_mm"] = connector.height
    report["connector_length_mm"] = side_length
    report["wave_length_mm"] = WAVE_LENGTH
    report["wave_amplitude_mm"] = WAVE_AMPLITUDE
    report["grid_pitch_mm"] = GRID_PITCH
    return report
