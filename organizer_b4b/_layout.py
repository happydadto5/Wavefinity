"""Storage Box (B4B) layout, capacity, effective-box and height/z helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import math
from shapely.geometry import LineString, Point, Polygon
from organizer_engine import (
    CORNER_INSET,
    GRID_PITCH,
    SAMPLES_PER_MM,
    WAVE_MATING_GAP,
    BoxSpec,
    _rounded,
    _wall_points,
    wall_wave_value,
)
from organizer_engine._wave import wall_wave_slope
from organizer_engine.product_rules import B4B_LATCHED_MIN_HEIGHT, B4B_MIN_FIELD_XY

from ._constants import (
    B4B_WALL_CORNER_FILLET,
    B4B_STACK_MIN_BASE,
    _SUPPORT_FREE_INSCRIBED,
    B4B_RUNNING_GAP,
    B4B_HEAD_RECESS_DEPTH,
    HardwareProfile,
    B4B_HW_M2,
    B4B_HW_M3,
    B4B_HW_M2_MAX_FIELD_XY,
    B4B_HW_M2_MAX_FIELD_Z,
    B4B_MIN_WALL,
    B4B_ROOT_CORNER_CLEARANCE,
    B4B_HINGE_CENTRE_GAP,
    B4B_HANDLE_SCALE_X_MIN,
    B4B_HANDLE_SCALE_X_MAX,
    B4B_HANDLE_BAND_MIN,
    B4B_HANDLE_BAND_MAX,
    B4B_HANDLE_THICKNESS_MIN,
    B4B_HANDLE_THICKNESS_MAX,
    B4B_HANDLE_GRIP_FRACTION,
    B4B_HANDLE_GRIP_ABS_MIN,
    B4B_HANDLE_GRIP_ABS_MAX,
    B4B_HANDLE_CORNER_FRACTION,
    B4B_HANDLE_CORNER_MIN,
    B4B_HANDLE_CORNER_MAX,
    B4B_HANDLE_DROP_FRACTION,
    B4B_HANDLE_DROP_ABS_MIN,
    B4B_HANDLE_DROP_ABS_MAX,
    B4B_HANDLE_MIN_DROP_FLOOR,
    B4B_HANDLE_MIN_DROP_BAND_FACTOR,
    B4B_HANDLE_EYE_RADIAL_SHELL,
    B4B_HANDLE_TAPER_RUN_FACTOR,
    B4B_HANDLE_TAPER_RUN_MIN,
    B4B_HANDLE_TAPER_RUN_MAX,
    _EPS,
)


# --------------------------------------------------------------------------- #
# child-field semantics + derived physical case
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class B4BLayout:
    """One source of truth for every derived Storage Box plan-view datum."""

    target_child_x: float
    target_child_y: float
    inner_half_x: float
    inner_half_y: float
    outer_half_x: float
    outer_half_y: float
    inner_mating_polygon: Polygon
    outer_structural_polygon: Polygon
    case_bounds: tuple[float, float, float, float]

    @property
    def case_size(self) -> tuple[float, float]:
        x0, y0, x1, y1 = self.case_bounds
        return x1 - x0, y1 - y0

    def front_wall_y(self, x: float) -> float:
        return -self.outer_half_y + wall_wave_value(x, "x")

    def rear_wall_y(self, x: float) -> float:
        return self.outer_half_y + wall_wave_value(x, "x")


def _outer_rounded_outline(half_x: float, half_y: float, radius: float) -> Polygon:
    """Join unchanged wave runs with circular, outside-only corner arcs."""
    corners = []
    for sx, sy in ((1, -1), (1, 1), (-1, 1), (-1, -1)):
        # Locate a circle tangent to both waves. The circle centre travels
        # along the inward normal to the horizontal wave; its first contact
        # with the vertical wave is the corner transition.
        reach = 2.0 * radius + 3.0
        count = max(2, math.ceil(reach * 128))
        vertical = LineString([
            (sx * half_x + wall_wave_value(sy * (half_y - reach * i / count), "y"),
             sy * (half_y - reach * i / count))
            for i in range(count + 1)
        ])

        def circle(distance: float):
            x = sx * (half_x - distance)
            y = sy * half_y + wall_wave_value(x, "x")
            slope = wall_wave_slope(x, "x")
            scale = radius / math.sqrt(1.0 + slope * slope)
            return (x, y), (x + sy * slope * scale, y - sy * scale)

        def gap(distance: float) -> float:
            return vertical.distance(Point(*circle(distance)[1])) - radius

        previous = reach
        for i in range(1, count + 1):
            current = reach * (1.0 - i / count)
            if gap(current) <= 0.0:
                break
            previous = current
        else:
            raise RuntimeError("Storage Box corner cannot join its wall waves")
        for _ in range(40):
            middle = (previous + current) / 2.0
            if gap(middle) > 0.0:
                previous = middle
            else:
                current = middle
        horizontal_point, centre = circle((previous + current) / 2.0)
        vertical_point = tuple(vertical.interpolate(vertical.project(Point(*centre))).coords[0])
        corners.append((horizontal_point, vertical_point, centre))

    def arc(start, end, centre):
        a = math.atan2(start[1] - centre[1], start[0] - centre[0])
        b = math.atan2(end[1] - centre[1], end[0] - centre[0])
        sweep = (b - a) % (2.0 * math.pi)
        steps = max(2, math.ceil(sweep / math.radians(2.0)))
        return [(centre[0] + radius * math.cos(a + sweep * i / steps),
                 centre[1] + radius * math.sin(a + sweep * i / steps))
                for i in range(1, steps)]

    def run(start, end, axis, face):
        along = 0 if axis == "x" else 1
        lo, hi = start[along], end[along]
        steps = max(1, math.ceil(abs(hi - lo) * SAMPLES_PER_MM))
        points = []
        for i in range(steps + 1):
            value = lo + (hi - lo) * i / steps
            across = face + wall_wave_value(value, axis)
            points.append((value, across) if axis == "x" else (across, value))
        # Retain the exact projected tangent at either end.
        points[0], points[-1] = start, end
        return points

    ring = []
    # Four runs and the next corner, counter-clockwise from the front wall.
    for index, (axis, face) in enumerate((("x", -half_y), ("y", half_x),
                                          ("x", half_y), ("y", -half_x))):
        before = corners[(index - 1) % 4]
        after = corners[index]
        start = before[0] if axis == "x" else before[1]
        end = after[0] if axis == "x" else after[1]
        next_end = after[1] if axis == "x" else after[0]
        ring.extend(run(start, end, axis, face))
        ring.extend(arc(end, next_end, after[2]))
    outline = Polygon(ring)
    if not outline.is_valid or outline.is_empty:
        raise RuntimeError("Storage Box rounded outer outline is not a valid single polygon")
    return outline


@lru_cache(maxsize=64)
def b4b_layout(box: BoxSpec) -> B4BLayout:
    """Resolve the exact child field and its outward-built case wall."""
    eff = b4b_effective_box(box)
    inner_half_x = eff.x / 2.0 + WAVE_MATING_GAP / 2.0
    inner_half_y = eff.y / 2.0 + WAVE_MATING_GAP / 2.0
    inner_tx = inner_half_x - CORNER_INSET
    inner_ty = inner_half_y - CORNER_INSET
    inner = Polygon(_wall_points(inner_half_x, inner_half_y, inner_tx, inner_ty))
    if not inner.is_valid:
        inner = inner.buffer(0)
    if not isinstance(inner, Polygon) or not inner.is_valid:
        raise RuntimeError("Storage Box inner mating outline is not a valid single polygon")
    inner = _rounded(inner, B4B_WALL_CORNER_FILLET)

    outer_half_x = inner_half_x + eff.wall_depth
    outer_half_y = inner_half_y + eff.wall_depth
    outer = _outer_rounded_outline(outer_half_x, outer_half_y, min(eff.wall, 3.5))
    if not outer.buffer(_EPS).contains(inner):
        raise RuntimeError("Storage Box outward wall does not contain its inner mating face")
    return B4BLayout(
        target_child_x=eff.x,
        target_child_y=eff.y,
        inner_half_x=inner_half_x,
        inner_half_y=inner_half_y,
        outer_half_x=outer_half_x,
        outer_half_y=outer_half_y,
        inner_mating_polygon=inner,
        outer_structural_polygon=outer,
        case_bounds=tuple(float(v) for v in outer.bounds),
    )


def b4b_capacity_units(box: BoxSpec) -> tuple[int, int]:
    """Exact requested child-field units after any visible auto-growth."""
    eff = b4b_effective_box(box)
    return round(eff.x / GRID_PITCH), round(eff.y / GRID_PITCH)


def b4b_capacity_mm(box: BoxSpec) -> tuple[float, float]:
    eff = b4b_effective_box(box)
    return eff.x, eff.y


def b4b_effective_base_thickness(box: BoxSpec) -> float:
    """Base thickness Storage Box geometry actually uses.

    ``max(requested, B4B_STACK_MIN_BASE)`` when stacking is on, otherwise the
    requested value.  Never redefines the normal Standard Base.
    """
    b4b = box.b4b.normalised()
    requested = box.base_thickness
    if b4b.stacking and b4b.lid:
        return max(requested, B4B_STACK_MIN_BASE)
    return requested


def b4b_hardware_family(box: BoxSpec) -> HardwareProfile:
    """The one hardware family this whole case uses.

    Deterministic and consulted from a single place, so the preview, the
    exported geometry, the validation report and the BOM can never disagree
    about which kit the user needs.  Compact B4Bs through 120 x 120 x 64 use
    M2; larger B4Bs use M3.  One family is used across hinges, latches and
    handle, so handle on or off does not change the family.
    """
    if (
        box.x <= B4B_HW_M2_MAX_FIELD_XY + _EPS
        and box.y <= B4B_HW_M2_MAX_FIELD_XY + _EPS
        and box.z <= B4B_HW_M2_MAX_FIELD_Z + _EPS
    ):
        return B4B_HW_M2
    return B4B_HW_M3


def b4b_required_min_wall(box: BoxSpec) -> float:
    """The wall a mode *requires*, never a reduction of a thicker choice.

    One helper so the promotion rule lives in a single place: B4B and the
    stacking load paths need real material, an ordinary non-stacking bin does
    not, and nothing here may ever push a user's thicker wall back down.
    """
    if box.b4b.enabled:
        return B4B_MIN_WALL
    stack = getattr(box, "stack", None)
    if stack is not None and getattr(stack, "mode", "none") != "none":
        return B4B_MIN_WALL
    return 0.0


def b4b_min_field(box: BoxSpec) -> tuple[float, float]:
    """Smallest child field Storage Box will build, per axis.

    A flat product rule, not a hardware-fit search: below this the hinges,
    latches and handle would *be* the product.  B4B is refused rather than
    grown, so the entered field always survives into the geometry.
    """
    return B4B_MIN_FIELD_XY, B4B_MIN_FIELD_XY


def b4b_secure_min_height() -> float:
    """Smallest entered child height a secure lid is offered on."""
    return B4B_LATCHED_MIN_HEIGHT


def _usable_front_span(layout: "B4BLayout") -> float:
    """Straight run of the front wall between the two corner tangents."""
    return 2.0 * (layout.outer_half_x - CORNER_INSET)


def _root_centres(
    layout: "B4BLayout", nominal: float, root_width: float, count: int
) -> tuple[float, ...]:
    """Symmetric hardware centres at ``+/- nominal``, pulled *inward* only.

    Hardware never shifts outward and never breaks symmetry: the only reason a
    centre moves at all is to keep its root clear of the wall's corner tangent.
    """
    if count == 1:
        return (0.0,)
    limit = (
        layout.outer_half_x - CORNER_INSET
        - B4B_ROOT_CORNER_CLEARANCE - root_width / 2.0
    )
    centre = min(nominal, limit)
    if centre <= root_width / 2.0 + B4B_HINGE_CENTRE_GAP / 2.0:
        centre = root_width / 2.0 + B4B_HINGE_CENTRE_GAP / 2.0
    return (-centre, centre)


def _lerp(lo: float, hi: float, t: float) -> float:
    return lo + (hi - lo) * t


def _clamp01(t: float) -> float:
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def b4b_handle_grip_target(child_x: float) -> float:
    """Clear grip this case *wants*, before asking whether it fits.

    Purely proportional to the child field between an absolute floor and an
    ergonomic ceiling - no fixed adult-hand minimum, so a small case gets a
    small, honestly-scaled handle instead of a full-size one; past the
    ceiling a larger B4B keeps the same grip instead of spreading the bail to
    the corners.
    """
    return min(
        B4B_HANDLE_GRIP_ABS_MAX,
        max(B4B_HANDLE_GRIP_ABS_MIN, B4B_HANDLE_GRIP_FRACTION * child_x),
    )


def _handle_pivot_stack(profile: HardwareProfile) -> tuple[float, float, float]:
    """``(near_ear, eye_band, far_lug)`` for the handle's own pivot stack.

    Not the ordinary hinge/latch stack: the rotating member here is the
    handle eye, sized from the resolved family's own clearance bore, not from
    that family's ``mid_member`` (a lid ear or latch lever).  A compact M2
    handle gets a compact M2-specific stack; M3 keeps the original
    proven handle stack.
    """
    if profile.name == "M2":
        return 2.20, 3.20, 2.60
    return 2.60, 5.40, 3.40


def _handle_root_dims(profile: HardwareProfile) -> tuple[float, float, float, float]:
    """``(root_width, root_above, root_below, root_depth)`` for the body fork
    root, scaled to match the resolved handle hardware family."""
    if profile.name == "M2":
        return 12.0, 4.5, 9.0, 2.6
    return 16.0, 6.0, 12.0, 3.0


@dataclass(frozen=True)
class HandleDimensions:
    """Every folding-handle dimension, resolved once from the child field and
    hardware family.  Every handle builder reads this instead of recomputing
    its own scale, so the geometry cannot drift out of proportion with itself.
    """

    band: float
    thickness: float
    eye_band: float
    eye_radius: float
    corner_radius: float
    target_grip: float
    target_drop: float
    min_drop: float
    near_ear: float
    far_lug: float
    fork_width: float
    fork_clear_span: float
    root_width: float
    root_above: float
    root_below: float
    root_depth: float
    taper_run: float


def b4b_handle_dimensions(box: BoxSpec, profile: HardwareProfile) -> HandleDimensions:
    """Resolve every handle dimension for this case and hardware family.

    Child-field X is the stable scaling input - a few millimetres of exterior
    wall growth must not make the handle unexpectedly jump in size.  Below
    ``B4B_HANDLE_SCALE_X_MIN`` the handle is at its smallest; at or above
    ``B4B_HANDLE_SCALE_X_MAX`` it is at its largest; ordinary linear
    interpolation in between.
    """
    eff = b4b_effective_box(box)
    scale = _clamp01(
        (eff.x - B4B_HANDLE_SCALE_X_MIN)
        / (B4B_HANDLE_SCALE_X_MAX - B4B_HANDLE_SCALE_X_MIN)
    )
    band = _lerp(B4B_HANDLE_BAND_MIN, B4B_HANDLE_BAND_MAX, scale)
    thickness = _lerp(B4B_HANDLE_THICKNESS_MIN, B4B_HANDLE_THICKNESS_MAX, scale)
    corner_radius = min(
        B4B_HANDLE_CORNER_MAX,
        max(B4B_HANDLE_CORNER_MIN, B4B_HANDLE_CORNER_FRACTION * band),
    )
    target_drop = min(
        B4B_HANDLE_DROP_ABS_MAX,
        max(B4B_HANDLE_DROP_ABS_MIN, B4B_HANDLE_DROP_FRACTION * eff.x),
    )
    min_drop = max(B4B_HANDLE_MIN_DROP_FLOOR, B4B_HANDLE_MIN_DROP_BAND_FACTOR * band)
    taper_run = min(
        B4B_HANDLE_TAPER_RUN_MAX,
        max(B4B_HANDLE_TAPER_RUN_MIN, B4B_HANDLE_TAPER_RUN_FACTOR * band),
    )
    near_ear, eye_band, far_lug = _handle_pivot_stack(profile)
    fork_width = near_ear + eye_band + far_lug + 2.0 * B4B_RUNNING_GAP
    fork_clear_span = (
        near_ear - B4B_HEAD_RECESS_DEPTH + eye_band + 2.0 * B4B_RUNNING_GAP
    )
    eye_radius = (
        profile.clear_bore / 2.0
        + B4B_HANDLE_EYE_RADIAL_SHELL
    ) / _SUPPORT_FREE_INSCRIBED
    root_width, root_above, root_below, root_depth = _handle_root_dims(profile)
    return HandleDimensions(
        band=band,
        thickness=thickness,
        eye_band=eye_band,
        eye_radius=eye_radius,
        corner_radius=corner_radius,
        target_grip=b4b_handle_grip_target(eff.x),
        target_drop=target_drop,
        min_drop=min_drop,
        near_ear=near_ear,
        far_lug=far_lug,
        fork_width=fork_width,
        fork_clear_span=fork_clear_span,
        root_width=root_width,
        root_above=root_above,
        root_below=root_below,
        root_depth=root_depth,
        taper_run=taper_run,
    )


def b4b_handle_width_fit(box: BoxSpec) -> tuple[bool, float, float]:
    """``(fits, required_pivot_span, max_pivot_span)`` for the front bail.

    Pure geometry against the real front wall, not a hard-coded width rule: the
    two pivot forks each need half their axial envelope plus a corner keep-out,
    and what is left has to span the target clear grip plus one band width.
    """
    layout = b4b_layout(box)
    eff = b4b_effective_box(box)
    profile = b4b_hardware_family(eff)
    dims = b4b_handle_dimensions(box, profile)
    max_pivot_span = _usable_front_span(layout) - 2.0 * (
        dims.fork_width / 2.0 + B4B_ROOT_CORNER_CLEARANCE
    )
    required = dims.target_grip + dims.band
    return max_pivot_span + _EPS >= required, required, max_pivot_span


def b4b_lid_skin_from_eff(eff: BoxSpec) -> float:
    """Storage Box lid top plate matches the effective Storage Box base."""
    return eff.base_thickness


def b4b_lid_skin(box: BoxSpec) -> float:
    return b4b_lid_skin_from_eff(b4b_effective_box(box))


def b4b_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec every Storage Box builder uses.

    An effective-*material* normaliser, not a dimension mutator.  The entered
    child field is authoritative and survives untouched: X, Y and Z are never
    grown to make a hinge, a latch or a handle fit.  A field that cannot carry
    the hardware is reported by validation and gated in the UI instead.

    The only thing that still moves is base thickness, and only far enough to
    leave a printable floor skin under a stacking recess - which changes no
    child dimension.  The flat-inside band is forced off because it alters
    the floor and perimeter the child bins seat on.
    """
    b4b = box.b4b.normalised()
    return replace(
        box,
        base_thickness=b4b_effective_base_thickness(box),
        flat_inside=0.0,
        b4b=b4b,
    )


def b4b_grew(box: BoxSpec) -> bool:
    """Whether anything about the effective box differs from the request.

    The child field is authoritative and is never touched, so the only thing
    this can still report is the stacking base: a recessed underside needs a
    printable floor skin beneath it.  That changes no child dimension and no
    capacity, and it is reported as what it is rather than as the box having
    been resized.
    """
    eff = b4b_effective_box(box)
    if not (
        math.isclose(eff.x, box.x)
        and math.isclose(eff.y, box.y)
        and math.isclose(eff.z, box.z)
    ):
        raise RuntimeError(
            "Storage Box changed the requested child field - the effective box must "
            "never resize X, Y or Z"
        )
    return not math.isclose(eff.base_thickness, box.base_thickness)


def b4b_max_child_height(box: BoxSpec) -> float:
    """Tallest child bin that fits under a closed lid.

    A child rests on the effective B4B floor; the lid underside sits
    ``lid_headroom_mm`` above a child whose nominal height equals the entered
    ``box.z``.  So the promised maximum child height is simply ``box.z`` - the
    headroom is realised above it by the lid riser, never by shrinking this.
    """
    return b4b_effective_box(box).z


# --------------------------------------------------------------------------- #
# authoritative inner mating wall
# --------------------------------------------------------------------------- #
def b4b_mating_polygon(box: BoxSpec) -> Polygon:
    """Inward-facing wave the child field's perimeter bins mate to.

    Built with the *same* ``wave_value`` phase/amplitude/wavelength as every
    Wavefinity wall (via :func:`_wall_points`), not a Shapely buffer of the
    child field - a perpendicular buffer would break the phase relationship.
    Baseline half-extent per axis is ``C*G/2 + gap/2``, exactly one axis gap
    outside a child field whose perimeter wall baseline is ``C*G/2 - gap/2``.
    """
    return b4b_layout(box).inner_mating_polygon


def b4b_outer_polygon(box: BoxSpec) -> Polygon:
    return b4b_layout(box).outer_structural_polygon


# --------------------------------------------------------------------------- #
# lid datums
# --------------------------------------------------------------------------- #
def b4b_internal_floor_z(box: BoxSpec) -> float:
    return b4b_effective_box(box).base_thickness


def b4b_lid_underside_z_from_eff(eff: BoxSpec) -> float:
    return eff.base_thickness + eff.z + eff.b4b.lid_headroom_mm


def b4b_lid_underside_z(box: BoxSpec) -> float:
    """Z of the lid underside over the child field, from the Storage Box bottom datum.

    ``effective_floor_z + box.z + lid_headroom_mm`` - a child of nominal height
    ``box.z`` resting on the floor then has ``lid_headroom_mm`` clearance.
    """
    return b4b_lid_underside_z_from_eff(b4b_effective_box(box))


def b4b_rim_z_from_eff(eff: BoxSpec) -> float:
    """Z of the body's top rim.

    The rim *is* the lid seat: the wall rises to the lid underside datum so the
    lid plate lands flat on a full-perimeter rim.  A wall that stopped at
    ``eff.z`` would leave the lid floating on its hardware, with the locating
    skirt as the only thing bridging the gap - and no room inside the footprint
    for that skirt to bridge it without driving into the wall.
    """
    if eff.b4b.lid:
        return b4b_lid_underside_z_from_eff(eff)
    return eff.z


def b4b_rim_z(box: BoxSpec) -> float:
    return b4b_rim_z_from_eff(b4b_effective_box(box))
