"""Wavefinity engine box and connector builders."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import Polygon, box as shapely_box
from organizer_geometry import (
    _cleaned,
    _extrude_polygon,
    _sweep_profile,
    difference,
    translated,
    union,
)

from ._specs import (
    WAVE_LENGTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    CORNER_INSET,
    MIN_JOINABLE_SIZE,
    CORNER_CONNECTOR_ARM_START,
    CORNER_CONNECTOR_END,
    DEFAULT_SIDE_LENGTH,
    DIFFERING_MIN_DROP,
    DIFFERING_WEB_THICKNESS,
    DIFFERING_WEB_TAPER,
    differing_drop_fraction,
    differing_web_reach,
    differing_connector_plan,
    LOCK_PROTRUSION,
    LOCK_RUN,
    LOCK_NOTCH_CLEARANCE,
    lid_enabled,
    vertical_stack_enabled,
    BoxSpec,
    ConnectorSpec,
)
from ._wave import (
    wave_value,
    lock_lattice,
    _sample_count,
    _rounded,
    wavy_outer_polygon,
    wavy_cavity_polygon,
    _lock_profile,
    make_wall_lock_bumps,
)
from ._lift_grabbers import make_lift_grabbers


# --------------------------------------------------------------------------- #
# parts
# --------------------------------------------------------------------------- #
def flat_cavity_polygon(spec: BoxSpec) -> Polygon:
    """Straight-sided cavity profile for the flat band at the bottom.

    Sized to the innermost the wavy cavity ever reaches, so the band adds
    material against the wall and never cuts into it.  It is exactly the
    rectangle ``usable_inside`` reports, which is why turning the band on does
    not change how much straight-sided room the box has.
    """
    half_x = spec.half_x - spec.wall_depth - WAVE_AMPLITUDE
    half_y = spec.half_y - spec.wall_depth - WAVE_AMPLITUDE
    if half_x <= 0.0 or half_y <= 0.0:
        raise ValueError("box is too small for a flat-walled band")
    return _rounded(
        shapely_box(-half_x, -half_y, half_x, half_y),
        max(0.2, spec.corner_fillet - spec.wall),
    )


def make_box(spec: BoxSpec) -> trimesh.Trimesh:
    # Architecture guard: a B4B has its own body builder (organizer_b4b.
    # make_b4b_body).  If a B4B spec reaches the ordinary path a route was
    # missed - fail loudly rather than silently print a plain box.
    if getattr(getattr(spec, "b4b", None), "enabled", False):
        raise ValueError(
            "Storage Box BoxSpec must use the dedicated Storage Box builder, not make_box()"
        )
    envelope = _extrude_polygon(wavy_outer_polygon(spec), spec.z)
    if spec.flat_inside > 0.0:
        # The cavity is two stacked prisms: a straight-sided one sitting on the
        # floor, and the wavy one above it.  What that leaves behind is a band
        # of wall with flat faces for the first flat_inside mm, which is the
        # point - the wave carries on unchanged above it.
        band = _extrude_polygon(flat_cavity_polygon(spec), spec.flat_inside)
        band.apply_translation((0.0, 0.0, spec.base_thickness))
        above = _extrude_polygon(
            wavy_cavity_polygon(spec),
            spec.z - spec.base_thickness - spec.flat_inside + 1.0,
        )
        above.apply_translation((0.0, 0.0, spec.base_thickness + spec.flat_inside))
        cavity = union([band, above])
    else:
        cavity = _extrude_polygon(
            wavy_cavity_polygon(spec), spec.z - spec.base_thickness + 1.0
        )
        cavity.apply_translation((0.0, 0.0, spec.base_thickness))
    shell = difference([envelope, cavity])
    bumps = make_wall_lock_bumps(spec)
    grabbers = make_lift_grabbers(spec)
    additions = [*bumps, *grabbers]
    result = union([shell, *additions]) if additions else shell
    if vertical_stack_enabled(spec) or lid_enabled(spec):
        # Imported here: organizer_stack builds on the engine, not the other way
        # round, so importing it at module scope would close a cycle.
        from organizer_stack import stack_body_adders, stack_body_cutters

        cutters = stack_body_cutters(spec)
        # Manifold handles the tapered, segmented cuts more reliably one at a
        # time.  A cutter that tapers to the exterior can leave zero-volume
        # triangulation scraps; the printable body is the sole volume.
        for cutter in cutters:
            result = difference([result, cutter])
        if cutters:
            solids = [
                one for one in result.split(only_watertight=False)
                if len(one.faces) > 12
            ]
            if len(solids) != 1:
                raise RuntimeError("stack body cuts did not leave one printable solid")
            result = solids[0]
        adders = stack_body_adders(spec)
        if adders:
            result = union([result, *adders])
            solids = [
                one for one in result.split(only_watertight=False)
                if len(one.faces) > 12
            ]
            if len(solids) != 1:
                raise RuntimeError("stack snap detents did not join the body")
            result = solids[0]
    result.remove_unreferenced_vertices()
    if not vertical_stack_enabled(spec) and not lid_enabled(spec):
        result.merge_vertices()
    return result


def connector_half_widths(box: BoxSpec, connector: ConnectorSpec) -> tuple[float, float]:
    """``(inner, outer)`` half widths of the connector corridor, measured from
    the seam centre-line."""
    inner = box.wall_depth + WAVE_MATING_GAP / 2.0 + connector.tolerance
    return inner, inner + connector.arm_thickness


def connector_bin_heights(
    box: BoxSpec, bin_a_height: float | None = None, bin_b_height: float | None = None,
) -> tuple[float, float]:
    """Resolve and validate the two rim heights used by a side connector."""
    heights = (
        box.z if bin_a_height is None else float(bin_a_height),
        box.z if bin_b_height is None else float(bin_b_height),
    )
    for name, height in zip(("bin A height", "bin B height"), heights):
        if not math.isfinite(height) or height <= box.base_thickness:
            raise ValueError(f"{name} must be greater than the base thickness")
    return heights


def connector_fits(
    box: BoxSpec,
    along_axis: str = "y",
    length: float = DEFAULT_SIDE_LENGTH,
    position: float = 0.0,
) -> bool:
    """Whether a connector of this length seats on that wall at all."""
    wave_half = box.half_x if along_axis.lower() == "x" else box.half_y
    return abs(position) + length / 2.0 <= wave_half - CORNER_INSET


def joinable_sides(
    box: BoxSpec, length: float = DEFAULT_SIDE_LENGTH
) -> tuple[bool, bool]:
    """``(x_walls, y_walls)`` - whether each pair of walls can take a connector.

    A wall running along X is the one whose length is the box's X dimension.
    """
    return connector_fits(box, "x", length), connector_fits(box, "y", length)


def _connector_corridor_polygon(
    axis: str, geometry_coordinates, phase_offset: float, half_width: float
) -> Polygon:
    """Wall-following corridor polygon shared by every connector type.

    ``geometry_coordinates`` are where the polygon is drawn; ``phase_offset`` is
    added only when evaluating the wave.
    """
    coordinates = geometry_coordinates
    low = high = [wave_value(phase_offset + float(v)) for v in coordinates]
    if axis == "y":
        near = [(o - half_width, float(v)) for v, o in zip(coordinates, low)]
        far = [
            (o + half_width, float(v))
            for v, o in zip(coordinates[::-1], high[::-1])
        ]
    else:
        near = [(float(v), o - half_width) for v, o in zip(coordinates, low)]
        far = [
            (float(v), o + half_width)
            for v, o in zip(coordinates[::-1], high[::-1])
        ]
    polygon = Polygon(near + far)
    if not polygon.is_valid:
        raise RuntimeError("side-connector corridor is not a valid polygon")
    return polygon


def _validate_connector_arm_clearance(
    box: BoxSpec, connector: ConnectorSpec, heights
) -> None:
    # The base slab, and any flat band on top of it, sit on the floor; the arms
    # hang from the rim.  On a normal bin the two are nowhere near each other.
    # On a very shallow one - easy to ask for as the short side of a
    # differing-height pair - the arm drives into the band, or into the base
    # slab itself, and the clip cannot seat on either bin.  Say so plainly
    # rather than letting the fit check report a bare collision volume.
    band_top = box.base_thickness + box.flat_inside
    for bin_height in heights:
        arm_bottom = bin_height - connector.arm_depth
        if arm_bottom >= band_top:
            continue
        min_height = band_top + connector.arm_depth
        if box.flat_inside > 0.0:
            room = bin_height - connector.arm_depth - box.base_thickness
            raise ValueError(
                f"the flat band reaches {band_top:.2f} mm up but the connector's arms "
                f"hang down to {arm_bottom:.2f} mm, so they would collide. On a "
                f"{bin_height:g} mm box the band can be at most {max(room, 0.0):.2f} mm, or "
                f"make the box at least {min_height:.2f} mm tall"
            )
        raise ValueError(
            f"a {bin_height:g} mm bin is too shallow for this connector: the arms hang "
            f"{connector.arm_depth:.2f} mm below the rim, down to {arm_bottom:.2f} mm, so "
            f"they would collide with the {box.base_thickness:.2f} mm base and the clip "
            f"could not seat. Make that bin at least {min_height:.2f} mm tall"
        )


def make_side_connector(
    box: BoxSpec,
    connector: ConnectorSpec,
    along_axis: str = "y",
    position: float = 0.0,
    length: float = DEFAULT_SIDE_LENGTH,
    bin_a_height: float | None = None,
    bin_b_height: float | None = None,
    web_thickness: float | None = None,
    auto_adjust: bool = True,
) -> trimesh.Trimesh:
    """Make a connector for two bins whose rims may be at different heights.

    Bin A is the negative side of the seam and bin B is the positive side.  The
    cap sits on the taller rim; only the arm over a shorter bin is extended.

    When the two rims differ by more than ``DIFFERING_MIN_DROP`` the clip is
    also made sturdier in step with the difference: ``length`` grows by up to
    ``DIFFERING_LENGTH_GAIN``, and the extended arm is fattened into a tapered
    web over the unbraced span (see ``unbraced_web``).  Equal rims give exactly
    the part they always did.
    """
    axis = along_axis.lower()
    if axis not in {"x", "y"}:
        raise ValueError("along_axis must be 'x' or 'y'")
    if length <= 0:
        raise ValueError("side connector length must be positive")
    heights = connector_bin_heights(box, bin_a_height, bin_b_height)
    # A different-height pair gets a beefier clip: the arm over the shorter bin
    # spans an unbraced gap, so past a small drop it is both fattened (below)
    # and lengthened here, in step with the drop, for more bumps to share the
    # load.  Equal heights leave the part exactly as it was.
    if auto_adjust:
        plan = differing_connector_plan(
            connector, length, heights[0], heights[1], box
        )
        drop_fraction = plan["drop_fraction"]
        length = plan["length_mm"]
    else:
        drop_fraction = differing_drop_fraction(abs(heights[0] - heights[1]))
    wave_half = box.half_x if axis == "x" else box.half_y
    if abs(position) + length / 2.0 > wave_half - CORNER_INSET:
        shortest = 2.0 * (length / 2.0 + CORNER_INSET) + WAVE_MATING_GAP
        raise ValueError(
            f"a {length:g} mm connector does not fit between this wall's corners: "
            f"that wall runs {2.0 * (wave_half - CORNER_INSET):.2f} mm and needs "
            f"{length:g}. A wall this short joins nothing - use the box's other "
            f"side, or make this one at least {shortest:.2f} mm"
        )
    _validate_connector_arm_clearance(box, connector, heights)

    # A whole wave, not half of one.  The corridor between the arms is cut to
    # the wall's wave at this position, and the wave inverts every half cycle:
    # a clip made half a wave away is the *mirror* of this one, same volume and
    # a shape no amount of turning it over will recover.  Slid onto this seam it
    # meets the wall crest-to-crest.  Whole cycles are the only offsets at which
    # one printed part really is the universal part.
    step = WAVE_LENGTH
    steps = position / step
    if abs(steps - round(steps)) > 1e-6:
        raise ValueError(
            f"connector position must be a whole multiple of {step:g} mm - one "
            f"whole wave - so one connector part fits every seam and drops on "
            f"either way round; {position:g} mm is not - try "
            f"{round(steps) * step:g} mm"
        )

    inner_hw, outer_hw = connector_half_widths(box, connector)
    samples = np.linspace(-length / 2.0, length / 2.0, _sample_count(length))
    cavity_samples = np.linspace(
        -length / 2.0 - 0.5, length / 2.0 + 0.5, _sample_count(length + 1.0)
    )

    def corridor(half_width: float, coordinates: np.ndarray) -> Polygon:
        return _connector_corridor_polygon(axis, coordinates, position, half_width)

    def arm_strip(sign: float, coordinates: np.ndarray) -> Polygon:
        offsets = [wave_value(position + float(v)) for v in coordinates]
        if axis == "y":
            if sign < 0:
                near = [(o - outer_hw, float(v)) for v, o in zip(coordinates, offsets)]
                far = [(o - inner_hw, float(v)) for v, o in zip(coordinates[::-1], offsets[::-1])]
            else:
                near = [(o + inner_hw, float(v)) for v, o in zip(coordinates, offsets)]
                far = [(o + outer_hw, float(v)) for v, o in zip(coordinates[::-1], offsets[::-1])]
        else:
            if sign < 0:
                near = [(float(v), o - outer_hw) for v, o in zip(coordinates, offsets)]
                far = [(float(v), o - inner_hw) for v, o in zip(coordinates[::-1], offsets[::-1])]
            else:
                near = [(float(v), o + inner_hw) for v, o in zip(coordinates, offsets)]
                far = [(float(v), o + outer_hw) for v, o in zip(coordinates[::-1], offsets[::-1])]
        return Polygon(near + far)

    def offset_strip(
        sign: float, half_near: float, half_far: float, coordinates: np.ndarray
    ) -> Polygon:
        """One arm's footprint with its two faces set explicitly, ``half_near``
        and ``half_far`` measured from the seam centre-line (near < far)."""
        offsets = [wave_value(position + float(v)) for v in coordinates]
        if axis == "y":
            near = [(o + sign * half_near, float(v)) for v, o in zip(coordinates, offsets)]
            far = [(o + sign * half_far, float(v)) for v, o in zip(coordinates[::-1], offsets[::-1])]
        else:
            near = [(float(v), o + sign * half_near) for v, o in zip(coordinates, offsets)]
            far = [(float(v), o + sign * half_far) for v, o in zip(coordinates[::-1], offsets[::-1])]
        return Polygon(near + far)

    def unbraced_web(sign: float, drop: float) -> list[trimesh.Trimesh]:
        """The fattened, tapered arm over the shorter bin's missing wall.

        Spans from the shorter bin's rim (``z_rim``) up to the cap.  Over that
        run the channel holds only the taller bin's wall, so the web reaches
        back across the seam until it runs on that wall's outer face - a fixed
        distance, not a fraction of the drop - and grows outward on top of that,
        by the drop-scaled amount, into the space the absent wall would occupy.
        It ramps back to a plain arm over the last few millimetres so the part
        that actually enters the bin, and every notch, is unchanged.  Built as
        thin stacked slabs: with the cap flipped down to print, each slab sits
        inside the one below it, so the whole taper is a support-free overhang.
        """
        if drop_fraction <= 0.0 or drop <= DIFFERING_MIN_DROP:
            return []
        z_rim = connector.arm_depth - drop
        if web_thickness is not None:
            web_t = web_thickness
        else:
            web_t = connector.arm_thickness + (
                DIFFERING_WEB_THICKNESS - connector.arm_thickness
            ) * drop_fraction
        grow = max(0.0, web_t - connector.arm_thickness)
        # Inward: cross the empty half of the channel and stop a running
        # clearance short of the taller bin's outer face.  A fact about the
        # seam, so it does not scale with the drop - scaling it was what left
        # the web short of that wall at every drop, with the clip bearing on
        # nothing for the whole span.
        move_in = differing_web_reach(box, connector)
        # Outward: whatever stiffening the drop asks for beyond that.
        move_out = max(0.0, grow - move_in)
        # The taper is what lets the web ramp back to a plain arm before it
        # reaches the shorter bin's wall, so it is dead length as far as bearing
        # on the taller wall goes.  The stretch that actually needs the web is
        # the one below the taller bin's own arm, ``drop - arm_depth``; a fixed
        # 6 mm ramp swallowed most of that at moderate drops.  Never give up
        # more than half of it, and never ramp in less than 2 mm.
        unbraced = max(0.0, drop - connector.arm_depth)
        taper = min(DIFFERING_WEB_TAPER, drop * 0.5, max(2.0, unbraced * 0.5))
        span = drop
        slabs: list[trimesh.Trimesh] = []
        steps = max(4, int(round(span / 1.5)))
        h = span / steps
        for k in range(steps):
            z0 = z_rim + k * h
            z1 = z0 + h
            ramp = 1.0 if z1 >= z_rim + taper else (z1 - z_rim) / taper
            slab = _extrude_polygon(
                offset_strip(
                    sign, inner_hw - move_in * ramp, outer_hw + move_out * ramp, samples
                ),
                h + 0.02,
            )
            slab.apply_translation((0.0, 0.0, z0))
            slabs.append(slab)
        # A brace in the inside corner where the long arm meets the cap - the
        # most worked point - added on the outer face, which is clear here.
        # Only when the web actually grew outward: with nothing past the plain
        # arm's outer face there is no corner to brace, and a zero-width strip
        # is not a solid.
        if move_out > 1e-9:
            gusset_h = min(drop, DIFFERING_WEB_TAPER)
            gsteps = max(3, int(round(gusset_h / 1.5)))
            gh = gusset_h / gsteps
            for k in range(gsteps):
                reach = move_out * (gsteps - k) / gsteps
                slab = _extrude_polygon(
                    offset_strip(sign, outer_hw, outer_hw + move_out + reach, samples),
                    gh + 0.02,
                )
                slab.apply_translation((0.0, 0.0, connector.arm_depth - (k + 1) * gh))
                slabs.append(slab)
            # Continue the widened cap over the top of the gusset so the
            # connector top is full across its entire width rather than
            # leaving a hollow shelf.
            cap_slab = _extrude_polygon(
                offset_strip(sign, outer_hw, outer_hw + move_out * 2, samples),
                connector.cap_thickness + 0.01,
            )
            cap_slab.apply_translation((0.0, 0.0, connector.arm_depth - 0.01))
            slabs.append(cap_slab)
        return slabs

    body = _extrude_polygon(corridor(outer_hw, samples), connector.height)
    channel = _extrude_polygon(corridor(inner_hw, cavity_samples), connector.arm_depth)
    result = difference([body, channel])

    cap_height = max(heights)
    arm_extensions = ((-1.0, cap_height - heights[0]), (1.0, cap_height - heights[1]))
    extensions = []
    for sign, extension_depth in arm_extensions:
        if extension_depth > 1e-6:
            extension = _extrude_polygon(arm_strip(sign, samples), extension_depth + 0.01)
            extension.apply_translation((0.0, 0.0, -extension_depth))
            extensions.append(extension)
            extensions.extend(unbraced_web(sign, extension_depth))
    if extensions:
        result = union([result, *extensions])

    notches = _arm_notches(
        box, connector, axis, position, length, inner_hw,
        {-1.0: -arm_extensions[0][1], 1.0: -arm_extensions[1][1]},
    )
    if notches:
        result = difference([result, *notches])
    # Through ``_cleaned``, not a bare merge: on a differing-height clip the
    # web's inner face and the channel it reaches into run close and near
    # parallel for the whole drop, which is exactly the case where welding by
    # tolerance can turn a sound manifold into a leaky one.
    return _cleaned(result)


def _arm_notches(
    box: BoxSpec,
    connector: ConnectorSpec,
    axis: str,
    position: float,
    length: float,
    inner_hw: float,
    z_offsets: dict[float, float] | None = None,
) -> list[trimesh.Trimesh]:
    """Side-connector notches: the arm interval is centred on ``position``."""
    return _connector_arm_notches(
        connector, axis, -length / 2.0, length / 2.0, position, inner_hw, z_offsets
    )


def _connector_arm_notches(
    connector: ConnectorSpec,
    axis: str,
    geometry_start: float,
    geometry_end: float,
    phase_offset: float,
    inner_hw: float,
    z_offsets: dict[float, float] | None = None,
    signs: tuple[float, ...] = (1.0, -1.0),
) -> list[trimesh.Trimesh]:
    """Recesses in the arms that receive the walls' lock bumps.

    The connector is modelled with its cap on top, so the arms hang from
    ``arm_depth`` down to 0 and the notches sit at the same distance below the
    rim as the bumps do.  ``geometry_start``/``geometry_end`` are coordinates in
    the returned mesh; ``phase_offset`` maps them onto the global lock lattice.

    A notch is cut at **every** lattice point under the connector, not only at
    the ones the box it was generated for happens to carry.  The neighbour
    across the seam may be a different size, and a missing notch would foul its
    bump; a notch with no bump behind it costs nothing.
    """
    profile = _lock_profile(LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE)
    # Any bump that reaches under the connector at all needs a notch, including
    # one only half covered at an end - otherwise the solid arm end fouls it.
    notches: list[trimesh.Trimesh] = []
    for centre in lock_lattice(
        geometry_start + phase_offset - LOCK_RUN / 2.0,
        geometry_end + phase_offset + LOCK_RUN / 2.0,
    ):
        local = centre - phase_offset
        lo, hi = local - LOCK_RUN / 2.0, local + LOCK_RUN / 2.0
        ss = np.linspace(lo, hi, _sample_count(LOCK_RUN))
        offsets = [wave_value(phase_offset + float(s)) for s in ss]
        for sign in signs:
            # The arm's wall-facing face is its inner one; the notch is cut from
            # there outward into the arm, matching the bump that pokes in.
            if axis == "y":
                path = [(o + sign * inner_hw, float(s)) for s, o in zip(ss, offsets)]
                lateral = (sign, 0.0)
            else:
                path = [(float(s), o + sign * inner_hw) for s, o in zip(ss, offsets)]
                lateral = (0.0, sign)
            notches.append(
                translated(
                    _sweep_profile(path, lateral, profile),
                    (0.0, 0.0, connector.arm_depth + (z_offsets or {}).get(sign, 0.0)),
                )
            )
    return notches


def _corner_connector_direction(
    box: BoxSpec,
    connector: ConnectorSpec,
    axis: str,
    direction: int,
    include_grip: bool = True,
) -> trimesh.Trimesh:
    """One corner branch: always a cap bridge, optionally a locked grip arm."""
    if axis not in {"x", "y"} or direction not in (-1, 1):
        raise ValueError("corner leg needs axis x/y and direction -1/+1")
    inner_hw, outer_hw = connector_half_widths(box, connector)
    end = CORNER_CONNECTOR_END
    start = CORNER_CONNECTOR_ARM_START

    def span(a: float, b: float, extra: float = 0.0) -> np.ndarray:
        lo, hi = (a, b) if direction > 0 else (-b, -a)
        lo, hi = lo - extra, hi + extra
        return np.linspace(lo, hi, _sample_count(hi - lo))

    cap = _extrude_polygon(
        _connector_corridor_polygon(axis, span(0.0, end), 0.0, outer_hw),
        connector.cap_thickness,
    )
    cap.apply_translation((0.0, 0.0, connector.arm_depth))
    if not include_grip:
        return _cleaned(cap)

    arm_coords = span(start, end)
    body = _extrude_polygon(
        _connector_corridor_polygon(axis, arm_coords, 0.0, outer_hw),
        connector.arm_depth + 0.01,
    )
    channel = _extrude_polygon(
        _connector_corridor_polygon(axis, span(start, end, 0.5), 0.0, inner_hw),
        connector.arm_depth,
    )
    arm = difference([body, channel])
    lo, hi = float(arm_coords[0]), float(arm_coords[-1])
    notches = _connector_arm_notches(connector, axis, lo, hi, 0.0, inner_hw)
    if notches:
        arm = difference([arm, *notches])
    return union([arm, cap])


def _corner_connector_branches(ways: int) -> tuple[tuple[str, int, bool], ...]:
    """Installed-seam topology for the compact corner connectors."""
    if ways == 3:
        # NW, NE and SW bins are installed.  East completes the T cap, but the
        # empty SE quadrant means it cannot honestly carry a two-wall grip.
        return (("y", 1, True), ("x", -1, True), ("x", 1, False))
    if ways == 4:
        return (("y", 1, True), ("y", -1, True), ("x", 1, True), ("x", -1, True))
    raise ValueError("corner connector must be 3-way or 4-way")


def make_corner_connector(
    box: BoxSpec, connector: ConnectorSpec, ways: int
) -> trimesh.Trimesh:
    """A compact 3-way or 4-way top connector for equal-height, same-wall bins.

    The 3-way cap is a T: north and west have real two-bin grip channels,
    while east is cap-only because the south-east quadrant is open. Rotate it
    to suit. The 4-way part has four full-grip branches.
    """
    branches = _corner_connector_branches(ways)
    if box.x < MIN_JOINABLE_SIZE - 1e-9 or box.y < MIN_JOINABLE_SIZE - 1e-9:
        raise ValueError(
            "Corner connectors need at least 16 mm (2 Wavefinity units) in both X "
            "and Y so the clip can clear the corners and engage the wall locks."
        )
    _validate_connector_arm_clearance(box, connector, (box.z,))
    parts = [
        _corner_connector_direction(box, connector, axis, direction, include_grip)
        for axis, direction, include_grip in branches
    ]
    return _cleaned(union(parts))


def connector_for_print(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Turn a connector over so its broad, flat cap is on the build plate."""
    result = mesh.copy()
    result.apply_transform(
        trimesh.transformations.rotation_matrix(math.pi, (1.0, 0.0, 0.0))
    )
    result.apply_translation((0.0, 0.0, -float(result.bounds[0][2])))
    return result
