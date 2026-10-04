"""Storage Box (B4B) hinge/latch hardware plan and carry-handle plan."""

from __future__ import annotations

from dataclasses import dataclass, replace
import math
import numpy as np
from shapely.geometry import Polygon
from organizer_engine import GRID_PITCH, WAVE_AMPLITUDE, BoxSpec
from organizer_product_rules import B4B_LATCHED_MIN_HEIGHT, B4B_MIN_FIELD_XY

from ._constants import (
    B4B_SCREW_MAX_TAIL,
    HardwareProfile,
    B4B_HW_CLEARANCE,
    B4B_LID_FITTING_DROP,
    B4B_HW_FILLET,
    B4B_HINGE_TWO_ABOVE_SPAN,
    B4B_LID_OPEN_ANGLE,
    B4B_SWEEP_STEP_DEG,
    B4B_LID_RELIEF_MAX,
    B4B_HINGE_AXIS_STEP,
    B4B_LATCH_TWO_ABOVE_FIELD_X,
    B4B_HANDLE_WALL_CLEAR,
    B4B_HANDLE_BOTTOM_MARGIN,
    B4B_HANDLE_RIM_DROP,
    B4B_HANDLE_STOP_ANGLE,
    B4B_HANDLE_DETENT,
    B4B_HANDLE_DETENT_BUMP,
    _EPS,
)
from ._layout import (
    B4BLayout,
    b4b_layout,
    b4b_hardware_family,
    _usable_front_span,
    _root_centres,
    b4b_handle_dimensions,
    b4b_handle_width_fit,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z_from_eff,
    b4b_rim_z_from_eff,
)


# --------------------------------------------------------------------------- #
# hardware plan
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BHardwarePlan:
    """Every hinge/latch dimension, resolved once from one hardware profile.

    Preview, export, BOM and validation all read this, so they cannot disagree
    about which family the case uses or where a pivot sits.
    """

    profile: HardwareProfile
    hinge_count: int
    hinge_centers_x: tuple[float, ...]
    hinge_width: float
    hinge_screw_length_mm: int
    hinge_axis_y: float
    hinge_axis_z: float
    hinge_rear_crest: float
    hinge_root_width: float
    hinge_root_top_z: float
    hinge_root_face_y: float
    lid_rear_relief: float
    latch_count_resolved: int
    latch_centers_x: tuple[float, ...]
    latch_screw_length_mm: int
    catch_screw_length_mm: int
    pivot_axis_y: float
    pivot_axis_z: float
    catch_axis_y: float
    catch_axis_z: float
    latch_front_crest: float
    latch_root_width: float
    latch_root_top_z: float
    latch_root_face_y: float
    fillet_radius: float = 0.0

    # -- derived reporting ------------------------------------------------- #
    @property
    def family(self) -> str:
        return self.profile.name

    @property
    def hinge_projection(self) -> float:
        """Rear projection of the uniform pivot envelope past the wall crest.

        Measured along Y, which is the direction the projection is in.  The
        support-free section has a *vertical face* at each Y extreme, so it
        reaches exactly its nominal radius there; ``_SUPPORT_FREE_CIRCUM``
        describes the diagonal to a facet join and would overstate this by
        about 6%.
        """
        return (
            self.hinge_axis_y - self.hinge_rear_crest + self.profile.pivot_radius
        )

    @property
    def latch_projection(self) -> float:
        """Closed front projection: the lever's pivot end is the outermost
        normal feature, and the hook sits inboard of it by design."""
        return (
            self.latch_front_crest - self.pivot_axis_y + self.profile.pivot_radius
        )

    def screw_bom(self) -> list[str]:
        lines: list[str] = []
        fam = self.profile.name
        if self.hinge_count:
            lines.append(
                f"{self.hinge_count} x {fam}x{self.hinge_screw_length_mm} hinge pins"
            )
        if self.latch_count_resolved:
            lines.append(
                f"{self.latch_count_resolved} x {fam}x{self.latch_screw_length_mm} "
                f"latch pivots"
            )
            lines.append(
                f"{self.latch_count_resolved} x {fam}x{self.catch_screw_length_mm} "
                f"catch pins"
            )
        lines.append("No nuts")
        return lines


def _screw_for_stack(
    profile: HardwareProfile, clear_span_mm: float, lug_thickness_mm: float, what: str
) -> int:
    """Authoritative kit-screw choice for one pivot.

    The screw enters at the head-bearing face, crosses ``clear_span_mm`` of
    clearance-bored material (ears and running gaps), then thread-forms into a
    terminal lug ``lug_thickness_mm`` thick.  Returns the shortest permitted
    length for the family that reaches the minimum engagement without leaving
    more than ``B4B_SCREW_MAX_TAIL`` past the far face.

    The exact stacks in the profiles are designed so the answer is a zero-tail
    screw - M2x8, M3x10, M3x12 for the handle.  This still *derives* that
    rather than hard-coding it, so a later change to an ear thickness cannot
    silently leave the BOM wrong.

    Real thread engagement can never exceed the lug, so a lug thinner than the
    family minimum is a geometry bug and is rejected here rather than papered
    over with a longer screw.
    """
    if lug_thickness_mm + _EPS < profile.engage_min:
        raise ValueError(
            f"the {what} terminal lug is only {lug_thickness_mm:.2f} mm thick - "
            f"less than the {profile.engage_min:.1f} mm minimum {profile.name} "
            f"thread engagement; widen the hardware"
        )
    for length in profile.lengths:
        beyond = length - clear_span_mm
        if beyond + _EPS < profile.engage_min:
            continue
        if beyond - lug_thickness_mm <= B4B_SCREW_MAX_TAIL + _EPS:
            return length
        break
    allowed = ", ".join(f"{profile.name}x{n}" for n in profile.lengths)
    raise ValueError(
        f"no kit screw ({allowed}) fits the {what} pivot: a "
        f"{clear_span_mm:.2f} mm clearance stack into a {lug_thickness_mm:.2f} mm "
        f"lug needs at least {profile.engage_min:.1f} mm of thread with no more "
        f"than {B4B_SCREW_MAX_TAIL:.1f} mm of tail"
    )


def _front_span(box: BoxSpec) -> float:
    """Usable straight run of the front wall between corner tangents."""
    return _usable_front_span(b4b_layout(box))


def _wall_extreme_y(
    layout: B4BLayout, x0: float, x1: float, outward_sign: float
) -> float:
    """Outermost Y the named wall reaches anywhere across ``[x0, x1]``.

    Hardware roots sit across a run of a wavy wall, so they have to be
    referenced to the wall's crest over that whole run, not to the wave value
    at one sample point.
    """
    steps = max(9, int(abs(x1 - x0) * 4.0) + 1)
    xs = np.linspace(x0, x1, steps)
    if outward_sign > 0.0:
        return max(layout.rear_wall_y(float(v)) for v in xs)
    return min(layout.front_wall_y(float(v)) for v in xs)


def _local_wall_crest_for_ear(
    layout: B4BLayout, x_centre: float, ear_thickness: float, outward_sign: float
) -> float:
    """Wall crest over one ear's true axial width, not its whole root span."""
    half = ear_thickness / 2.0
    return _wall_extreme_y(layout, x_centre - half, x_centre + half, outward_sign)


def _ear_wall_anchor_y(
    layout: B4BLayout, x_centre: float, ear_thickness: float,
    outward_sign: float, wall_depth: float,
) -> float:
    """Anchor a gusset inside its local structural wall band.

    The cavity trim remains authoritative. This deliberate bite therefore
    gives every ear a real wall load path without spending child-bin capacity.
    """
    crest = _local_wall_crest_for_ear(
        layout, x_centre, ear_thickness, outward_sign
    )
    bite = min(0.7, 0.5 * wall_depth)
    return crest - outward_sign * bite


def _root_outward(profile_depth: float, wall_depth: float) -> float:
    """How far a root's outer face stands beyond the local wall crest.

    The profile states a *total* structural depth measured from the inner
    mating face, so the reinforcement is whatever that target has left over
    after the user's wall - and it grows outward only, never into the field.
    """
    return max(0.0, profile_depth - wall_depth)


def _lid_rear_section(
    layout: B4BLayout, underside_z: float, skin: float, relief: float
) -> Polygon:
    """Y/Z outline of the lid's rear edge band, with its relief chamfer.

    Only the plate matters for the opening sweep: the lid's own hinge ear is
    centred on the axis and therefore cannot move relative to the body.
    """
    crest = layout.outer_half_y + WAVE_AMPLITUDE
    inner = -crest
    top = underside_z + skin
    if relief <= 0.0:
        return Polygon([
            (inner, underside_z), (crest, underside_z),
            (crest, top), (inner, top),
        ])
    # a 45-degree support-free relief taken off the rear-bottom corner
    r = min(relief, skin - 0.4)
    return Polygon([
        (inner, underside_z), (crest - r, underside_z),
        (crest, underside_z + r), (crest, top), (inner, top),
    ])


def _body_rear_section(
    layout: B4BLayout, rim_z: float, root_face_y: float, root_top_z: float,
    root_bottom_z: float,
) -> Polygon:
    """Y/Z outline of everything on the body the opening lid could strike."""
    crest = layout.outer_half_y + WAVE_AMPLITUDE
    shell = Polygon([
        (-crest - 10.0, 0.0), (crest, 0.0), (crest, rim_z), (-crest - 10.0, rim_z),
    ])
    if root_face_y <= crest + _EPS or root_top_z <= root_bottom_z:
        return shell
    rib = Polygon([
        (crest, root_bottom_z), (root_face_y, root_bottom_z),
        (root_face_y, root_top_z), (crest, root_top_z),
    ])
    merged = shell.union(rib)
    return merged if isinstance(merged, Polygon) else shell


def _sweep_clear_2d(
    moving: Polygon, fixed: Polygon, axis_y: float, axis_z: float,
    angles_deg: tuple[float, ...],
) -> bool:
    """Whether ``moving`` clears ``fixed`` at every sampled opening angle.

    A cheap plan-space proof used to *place* the hinge axis.  The full
    mesh-level sweep in :func:`_validate_b4b_mechanics` still runs at
    generation time; this only has to be right enough to choose a datum.
    """
    from shapely.affinity import rotate as rotate_polygon

    for deg in angles_deg:
        if deg == 0.0:
            continue
        turned = rotate_polygon(
            moving, -deg, origin=(axis_y, axis_z), use_radians=False
        )
        if turned.intersection(fixed).area > 1e-4:
            return False
    return True


def _sweep_angles(limit: float, step: float = B4B_SWEEP_STEP_DEG) -> tuple[float, ...]:
    """``0, step, 2*step, ... limit`` inclusive of both ends."""
    n = int(math.ceil(limit / step))
    out = [min(i * step, limit) for i in range(n + 1)]
    if abs(out[-1] - limit) > _EPS:
        out.append(limit)
    return tuple(out)


def _solve_hinge_axis(
    layout: B4BLayout, profile: HardwareProfile, *, rear_crest: float,
    underside_z: float, skin: float, axis_z: float, root_face_y: float,
    root_top_z: float, root_bottom_z: float,
) -> tuple[float, float]:
    """``(axis_y, rear_lid_relief)`` for a collision-free 120-degree opening.

    Relief first, axis movement last: a small support-free chamfer on the rear
    lid edge is always preferable to pushing the whole hinge further behind the
    case, which is what made the old hardware look like a backpack.  The axis
    only moves if the full permitted relief is still not enough, and then by
    the smallest quantised step that clears the sweep.
    """
    angles = _sweep_angles(B4B_LID_OPEN_ANGLE)
    axis_y = rear_crest + profile.hinge_standoff
    body = _body_rear_section(
        layout, underside_z, root_face_y, root_top_z, root_bottom_z
    )
    relief = 0.0
    while relief <= B4B_LID_RELIEF_MAX + _EPS:
        lid = _lid_rear_section(layout, underside_z, skin, relief)
        if _sweep_clear_2d(lid, body, axis_y, axis_z, angles):
            return axis_y, relief
        relief += 0.2
    relief = B4B_LID_RELIEF_MAX
    lid = _lid_rear_section(layout, underside_z, skin, relief)
    limit = rear_crest + profile.hinge_standoff + 4.0
    while axis_y <= limit:
        if _sweep_clear_2d(lid, body, axis_y, axis_z, angles):
            return axis_y, relief
        axis_y += B4B_HINGE_AXIS_STEP
    raise ValueError(
        "the Storage Box lid cannot be opened to "
        f"{B4B_LID_OPEN_ANGLE:g} degrees without striking the body; the rear "
        "hinge geometry needs design review"
    )


def _inactive_plan(profile: HardwareProfile) -> B4BHardwarePlan:
    return B4BHardwarePlan(
        profile=profile,
        hinge_count=0,
        hinge_centers_x=(),
        hinge_width=0.0,
        hinge_screw_length_mm=0,
        hinge_axis_y=0.0,
        hinge_axis_z=0.0,
        hinge_rear_crest=0.0,
        hinge_root_width=0.0,
        hinge_root_top_z=0.0,
        hinge_root_face_y=0.0,
        lid_rear_relief=0.0,
        latch_count_resolved=0,
        latch_centers_x=(),
        latch_screw_length_mm=0,
        catch_screw_length_mm=0,
        pivot_axis_y=0.0,
        pivot_axis_z=0.0,
        catch_axis_y=0.0,
        catch_axis_z=0.0,
        latch_front_crest=0.0,
        latch_root_width=0.0,
        latch_root_top_z=0.0,
        latch_root_face_y=0.0,
    )


def b4b_hardware_plan(box: BoxSpec) -> B4BHardwarePlan:
    eff = b4b_effective_box(box)
    profile = b4b_hardware_family(eff)
    if not eff.b4b.secure_lid:
        return _inactive_plan(profile)

    layout = b4b_layout(box)
    skin = b4b_lid_skin_from_eff(eff)
    underside_z = b4b_lid_underside_z_from_eff(eff)
    lid_top_z = underside_z + skin
    fillet = min(B4B_HW_FILLET, 0.5 * B4B_LID_FITTING_DROP, 0.3 * profile.pivot_radius)
    wall_depth = eff.wall_depth

    # ---- rear hinges: one or two based on width, nominally at +/- child_x/4 -- #
    hinge_count = 2 if max(eff.x, eff.y) > B4B_HINGE_TWO_ABOVE_SPAN else 1
    hinge_centers_x = _root_centres(
        layout, eff.x / 4.0, profile.hinge_root_width, hinge_count
    )
    hinge_half = profile.hinge_root_width / 2.0
    rear_crest = max(
        _wall_extreme_y(layout, cx - hinge_half, cx + hinge_half, +1.0)
        for cx in hinge_centers_x
    )
    hinge_root_out = _root_outward(profile.hinge_root_depth, wall_depth)
    hinge_root_face_y = rear_crest + hinge_root_out
    # The axis sits at the lid plate band so the knuckle's upper flat lands on
    # the bed when the lid is printed upside down.
    hinge_axis_z = lid_top_z - profile.pivot_radius
    # The root has to stop short of wherever the lid-side knuckle reaches back
    # over it, or the closed lid would rest on its own reinforcement.
    inboard = max(0.0, profile.hinge_standoff - hinge_root_out)
    reach_down = math.sqrt(
        max(0.0, profile.pivot_radius ** 2 - inboard ** 2)
    )
    hinge_root_top_z = min(
        underside_z - 1.0, hinge_axis_z - reach_down - B4B_HW_CLEARANCE
    )
    hinge_root_bottom_z = max(1.0, hinge_root_top_z - profile.hinge_root_height)
    hinge_axis_y, lid_relief = _solve_hinge_axis(
        layout, profile,
        rear_crest=rear_crest,
        underside_z=underside_z,
        skin=skin,
        axis_z=hinge_axis_z,
        root_face_y=hinge_root_face_y,
        root_top_z=hinge_root_top_z,
        root_bottom_z=hinge_root_bottom_z,
    )
    hinge_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "hinge"
    )

    # ---- front latches: user override, else one authoritative width threshold #
    if eff.b4b.latch_count == "1":
        latch_count = 1
    elif eff.b4b.latch_count == "2":
        latch_count = 2
    else:
        latch_count = 1 if eff.x <= B4B_LATCH_TWO_ABOVE_FIELD_X + _EPS else 2
    latch_centers_x = _root_centres(
        layout, eff.x / 6.0, profile.latch_root_width, latch_count
    )
    latch_half = profile.latch_root_width / 2.0
    front_crest = min(
        _wall_extreme_y(layout, cx - latch_half, cx + latch_half, -1.0)
        for cx in latch_centers_x
    )
    pivot_axis_z = lid_top_z - profile.pivot_radius
    catch_axis_z = pivot_axis_z - profile.latch_draw
    pivot_axis_y = front_crest - profile.pivot_standoff
    catch_axis_y = front_crest - profile.catch_standoff
    latch_root_out = _root_outward(profile.latch_root_depth, wall_depth)
    latch_root_face_y = front_crest - latch_root_out
    # Same rule as the hinge: the root stops below the lid's pivot ear so the
    # lever swings on running clearance instead of rubbing its own receiver.
    pivot_inboard = max(0.0, profile.pivot_standoff - latch_root_out)
    pivot_down = math.sqrt(
        max(0.0, profile.pivot_radius ** 2 - pivot_inboard ** 2)
    )
    latch_root_top_z = min(
        underside_z - 1.0, pivot_axis_z - pivot_down - B4B_HW_CLEARANCE
    )
    if latch_root_top_z - profile.latch_root_height < 0.5:
        raise ValueError(
            f"a {eff.z:g} mm Storage Box is too short for a secure lid: the latch "
            f"receiver needs {profile.latch_root_height:.0f} mm of front wall "
            f"below the lid seam; use at least "
            f"{B4B_LATCHED_MIN_HEIGHT:g} mm of bin height"
        )
    latch_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "latch pivot"
    )
    catch_screw = _screw_for_stack(
        profile, profile.clear_span, profile.far_lug, "catch"
    )

    return B4BHardwarePlan(
        profile=profile,
        hinge_count=hinge_count,
        hinge_centers_x=hinge_centers_x,
        hinge_width=profile.group_width,
        hinge_screw_length_mm=hinge_screw,
        hinge_axis_y=hinge_axis_y,
        hinge_axis_z=hinge_axis_z,
        hinge_rear_crest=rear_crest,
        hinge_root_width=profile.hinge_root_width,
        hinge_root_top_z=hinge_root_top_z,
        hinge_root_face_y=hinge_root_face_y,
        lid_rear_relief=lid_relief,
        latch_count_resolved=latch_count,
        latch_centers_x=latch_centers_x,
        latch_screw_length_mm=latch_screw,
        catch_screw_length_mm=catch_screw,
        pivot_axis_y=pivot_axis_y,
        pivot_axis_z=pivot_axis_z,
        catch_axis_y=catch_axis_y,
        catch_axis_z=catch_axis_z,
        latch_front_crest=front_crest,
        latch_root_width=profile.latch_root_width,
        latch_root_top_z=latch_root_top_z,
        latch_root_face_y=latch_root_face_y,
        fillet_radius=fillet,
    )


# --------------------------------------------------------------------------- #
# folding front handle
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BHandlePlan:
    """Every folding-bail dimension, resolved once.

    The handle is a single printed U pivoted on two forks that grow out of the
    *body* front wall.  The lid carries none of its load, so a carried case
    hangs from the shell rather than from the lid, the latches and the rear
    hinges - and the lid top stays clear for stacking.
    """

    profile: HardwareProfile
    pivot_span: float          # between the two screw centres
    centers_x: tuple[float, float]
    clear_grip: float          # between the inner faces of the two arms
    drop: float                # pivot axis to grip centreline
    band: float                # in-plane band width of the lower U
    eye_band: float            # tapered band at the pivot eye
    thickness: float           # front-to-back, folded
    eye_radius: float
    corner_radius: float
    axis_y: float
    axis_z: float
    front_crest: float
    wall_clear: float
    stop_angle: float
    detent_interference: float
    detent_bump: float
    detent_centers_x: tuple[float, float]
    detent_z: float
    root_width: float
    root_face_y: float
    root_top_z: float
    root_bottom_z: float
    screw_length_mm: int
    near_ear: float
    far_lug: float
    fork_width: float
    fork_clear_span: float
    taper_run: float
    min_drop: float

    @property
    def projection(self) -> float:
        """Folded projection past the front wall crest, at the handle eye.

        Measured along Y like every other projection: the support-free section
        presents a vertical face at its Y extremes, so it reaches its nominal
        radius and no further.
        """
        return self.front_crest - self.axis_y + self.eye_radius

    @property
    def eye_projection(self) -> float:
        return self.front_crest - self.axis_y + self.eye_radius

    @property
    def grip_z(self) -> float:
        return self.axis_z - self.drop


def b4b_handle_min_width(box: BoxSpec) -> float:
    """Smallest valid child-field X (a whole GRID_PITCH multiple) that lets
    this Storage Box's front wall carry a handle.

    Scans the real front-wall fit check over legal grid widths rather than a
    hard-coded width rule, so it tracks wall thickness, latch layout, and
    every other geometry input the same way ``b4b_handle_width_fit`` does.
    Child-field X/Y live on the same GRID_PITCH lattice as BoxSpec enforces,
    so every probed width must be a whole GRID_PITCH multiple - never an
    arbitrary float - or BoxSpec's own grid validation rejects it.
    """
    first_units = max(1, math.ceil(B4B_MIN_FIELD_XY / GRID_PITCH))
    max_units = math.floor(5000.0 / GRID_PITCH)
    for units in range(first_units, max_units + 1):
        candidate = float(units) * GRID_PITCH
        if b4b_handle_width_fit(replace(box, x=candidate))[0]:
            return candidate
    raise ValueError("could not find a valid Storage Box width for the carrying handle")


def b4b_handle_eligibility(box: BoxSpec) -> tuple[bool, str]:
    """``(eligible, reason)`` - why this case can or cannot carry a bail.

    Derived from the actual front wall every time, never from a remembered
    width rule, and it never asks for the case to grow: a B4B that cannot take
    a handle is still a perfectly good B4B.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.secure_lid:
        return False, "Handle requires a secure lid."
    fits, required, available = b4b_handle_width_fit(box)
    if not fits:
        min_width = b4b_handle_min_width(box)
        return False, f"Minimum width must be {min_width:g} mm."
    profile = b4b_hardware_family(eff)
    dims = b4b_handle_dimensions(box, profile)
    axis_z = b4b_rim_z_from_eff(eff) - B4B_HANDLE_RIM_DROP
    available_drop = axis_z - B4B_HANDLE_BOTTOM_MARGIN - dims.band / 2.0
    if min(dims.target_drop, available_drop) + _EPS < dims.min_drop:
        return False, "Handle needs more front-wall height."
    return True, ""


def b4b_handle_plan(box: BoxSpec) -> B4BHandlePlan | None:
    """Resolve the bail, or ``None`` when this design has none.

    Raises with an actionable message when a handle is asked for on a case that
    cannot carry one, rather than quietly leaving it off a design that says it
    has one.
    """
    eff = b4b_effective_box(box)
    if not eff.b4b.handle:
        return None
    eligible, reason = b4b_handle_eligibility(box)
    if not eligible:
        raise ValueError(
            f"this Storage Box cannot take a carrying handle: {reason.rstrip('.')}; "
            f"turn the handle off, or use a wider or taller Storage Box"
        )

    layout = b4b_layout(box)
    profile = b4b_hardware_family(eff)
    dims = b4b_handle_dimensions(box, profile)
    clear_grip = dims.target_grip
    pivot_span = clear_grip + dims.band
    half = pivot_span / 2.0

    fork_half = dims.fork_width / 2.0
    front_crest = min(
        _wall_extreme_y(layout, -half - fork_half, half + fork_half, -1.0),
        _wall_extreme_y(layout, -half, half, -1.0),
    )
    axis_y = front_crest - (dims.eye_radius + B4B_HANDLE_WALL_CLEAR)
    axis_z = b4b_rim_z_from_eff(eff) - B4B_HANDLE_RIM_DROP
    available_drop = axis_z - B4B_HANDLE_BOTTOM_MARGIN - dims.band / 2.0
    drop = min(dims.target_drop, available_drop)

    root_out = _root_outward(dims.root_depth, eff.wall_depth)
    root_face_y = front_crest - root_out
    root_top_z = axis_z + dims.root_above
    root_bottom_z = max(1.0, axis_z - dims.root_below)

    # Stow detents sit near the lower corners of the folded U, where the arms
    # are long enough to flex over them at a light finger force.
    detent_z = axis_z - drop + dims.corner_radius
    detent_cx = half - dims.band / 2.0

    screw = _screw_for_stack(
        profile, dims.fork_clear_span, dims.far_lug, "handle pivot"
    )
    return B4BHandlePlan(
        profile=profile,
        pivot_span=pivot_span,
        centers_x=(-half, half),
        clear_grip=clear_grip,
        drop=drop,
        band=dims.band,
        eye_band=dims.eye_band,
        thickness=dims.thickness,
        eye_radius=dims.eye_radius,
        corner_radius=dims.corner_radius,
        axis_y=axis_y,
        axis_z=axis_z,
        front_crest=front_crest,
        wall_clear=B4B_HANDLE_WALL_CLEAR,
        stop_angle=B4B_HANDLE_STOP_ANGLE,
        detent_interference=B4B_HANDLE_DETENT,
        detent_bump=B4B_HANDLE_DETENT_BUMP,
        detent_centers_x=(-detent_cx, detent_cx),
        detent_z=detent_z,
        root_width=dims.root_width,
        root_face_y=root_face_y,
        root_top_z=root_top_z,
        root_bottom_z=root_bottom_z,
        screw_length_mm=screw,
        near_ear=dims.near_ear,
        far_lug=dims.far_lug,
        fork_width=dims.fork_width,
        fork_clear_span=dims.fork_clear_span,
        taper_run=dims.taper_run,
        min_drop=dims.min_drop,
    )
