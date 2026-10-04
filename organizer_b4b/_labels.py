"""Storage Box (B4B) top and front label geometry."""

from __future__ import annotations

import math
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.affinity import translate as translate_polygon
from organizer_engine import (
    TEXT_CAP_HEIGHT_MIN,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    BoxSpec,
    _sample_count,
    text_outline,
    text_prism,
    wave_value,
)
from organizer_geometry import (
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    translated,
    union,
)

from ._constants import (
    B4B_STACK_BOSS_DIAMETER,
    B4B_STACK_FEMALE_RADIAL_CLEARANCE,
    B4B_LABEL_KEEPOUT,
)
from ._layout import b4b_layout, b4b_lid_skin, b4b_effective_box, b4b_lid_underside_z
from ._plans import _front_span, _wall_extreme_y, b4b_hardware_plan, b4b_handle_plan
from ._geometry import _stack_locator_centres, _weld


# --------------------------------------------------------------------------- #
# labels
# --------------------------------------------------------------------------- #
B4B_TOP_LABEL_CAP_IDEAL = 8.0
B4B_TOP_LABEL_MARGIN = 2.5

# Compact top-loading front label.  The plate is sized from the lettering,
# not from a fixed footprint, so most of these are targets and margins
# rather than dimensions: ``b4b_front_label_geometry`` measures the actual
# text outline and builds the plate only slightly larger than it.  The
# plate drops in from above and rides down between two side channels onto
# a closed, ramped bottom stop, and lifts straight back out the same way -
# there is no end-stop, snap detent, or finger notch, and no retention
# feature of any kind.  It relies on gravity, the bottom stop and the side
# channels alone; it is meant to slide in and back out freely, not to seat
# once and stay.
B4B_FRONT_LABEL_CAP_IDEAL = 10.0        # preferred cap height - never grown past this
B4B_FRONT_LABEL_PLATE_T = 1.0           # plate thickness
B4B_FRONT_LABEL_MARGIN_X = 2.0          # plate margin each side of the text
B4B_FRONT_LABEL_MARGIN_Y = 1.75         # plate margin above/below the text
# Running clearance between the plate and the channel it rides in, defined
# once as a *per-side* value: the plate sits centred with this much air to
# the flat wall behind it and to the retaining lip in front of it.  This is
# ordinary running clearance, not a fit meant to compensate for the absence
# of a retention feature.
B4B_FRONT_LABEL_CLEAR = 0.25
# Total outward projection of the whole holder, measured from the locally
# flattened wall face - not derived from the plate/clearance stack, so the
# holder never balloons just because the plate got thinner or thicker.
B4B_FRONT_LABEL_HOLDER_DEPTH = 3.0
# Side channel: a structural leg attached to the flattened wall, with a
# front lip overlapping the plate's edge so it must be lifted clear of the
# lip rather than pulled straight out the front.
B4B_FRONT_LABEL_SIDE_LEG_W = 2.0        # total X width of one side channel
B4B_FRONT_LABEL_SIDE_OVERLAP = 1.0      # how far its lip reaches onto the plate
B4B_FRONT_LABEL_MAX_WIDTH_FRACTION = 0.5  # holder <= this fraction of the case width
# Clear vertical gap that must exist above the plate's fully-inserted top edge
# so it can be dropped straight in without fouling the latch/handle hardware
# above it - just the plate's own height of travel to slide it into place,
# not a whole extra plate height on top of that. See
# ``_b4b_front_label_bottom_z``.
B4B_FRONT_LABEL_INSERT_CLEARANCE = 2.0
B4B_FRONT_LABEL_PREFERRED_HEIGHT_FRACTION = 1.0 / 3.0
                                         # normal resting position: about a third of the
                                         # way up the inside height - purely a visual
                                         # preference, given up first (dropping toward
                                         # the floor) whenever the insertion corridor
                                         # needs the room
B4B_FRONT_LABEL_BOTTOM_MIN = 0.0        # the case floor itself - the holder may sit
                                         # flush with it when the corridor needs the room
# The flat, planar border every removable front label style keeps around its
# whole rectangular perimeter, so both Flat and Wavy slide into the exact same
# holder: the side channels, bottom stop and running clearance above only ever
# see a plain flat-sided rectangle, whatever the visible face does in the
# middle. See ``_b4b_wavy_label_blank``.
B4B_FRONT_LABEL_FLAT_BORDER = 1.5
B4B_FRONT_LABEL_WAVE_BLEND = 0.85        # transition width between flat border and full wave


def _b4b_front_label_bottom_z(
    insertion_ceiling_z: float, plate_h: float, case_z: float
) -> float | None:
    """The ``bottom_z`` to seat a ``plate_h``-tall plate at: about a third of
    the way up ``case_z`` (``B4B_FRONT_LABEL_PREFERRED_HEIGHT_FRACTION``) if
    that already leaves the required insertion corridor above the holder,
    otherwise as low as the case floor allows - down to
    ``B4B_FRONT_LABEL_BOTTOM_MIN`` - to buy back headroom. ``None`` if even
    the lowest position can't clear the corridor, i.e. the plate must shrink
    further before a position exists at all.

    The plate slides straight down into the holder from above, so the
    corridor only has to fit the plate's own height of travel plus
    ``B4B_FRONT_LABEL_INSERT_CLEARANCE`` of working clearance above the
    seated position - not a second plate height on top of that for a full
    lift-out."""
    preferred_bottom = case_z * B4B_FRONT_LABEL_PREFERRED_HEIGHT_FRACTION
    required_span = (
        B4B_FRONT_LABEL_HOLDER_DEPTH + plate_h
        + B4B_FRONT_LABEL_INSERT_CLEARANCE
    )
    bottom_z = min(preferred_bottom, insertion_ceiling_z - required_span)
    return bottom_z if bottom_z >= B4B_FRONT_LABEL_BOTTOM_MIN else None


def _fit_text_outline(text: str, avail_w: float, avail_h: float, ideal_cap: float):
    """Largest ``text_outline`` that fits ``avail_w`` x ``avail_h``, scaling the
    cap height down toward the readable minimum.  Raises a clear error if even
    the minimum will not fit."""
    text = text.strip()
    if not text:
        raise ValueError("label text is empty")
    cap = ideal_cap
    while cap >= TEXT_CAP_HEIGHT_MIN - 1e-6:
        outline = text_outline(text, cap)
        minx, miny, maxx, maxy = outline.bounds
        if (maxx - minx) <= avail_w and (maxy - miny) <= avail_h:
            return outline
        cap -= 0.5
    raise ValueError(
        f"the label '{text}' does not fit the available "
        f"{avail_w:.0f} x {avail_h:.0f} mm area even at the minimum size"
    )


def _top_surface_keepouts(eff: BoxSpec) -> list[Polygon]:
    """Plan-view regions on the lid top the label must avoid: every stacking
    boss (all four, not one row) plus a margin.

    Hinge knuckles and latch ears sit outboard at the rim, below the top plate,
    and the carrying handle now folds against the front wall rather than
    straddling the lid, so the bosses are the only real keep-outs left."""
    keepouts: list[Polygon] = []
    if eff.b4b.stacking and eff.b4b.lid:
        r = (
            B4B_STACK_BOSS_DIAMETER / 2.0
            + B4B_STACK_FEMALE_RADIAL_CLEARANCE
            + B4B_TOP_LABEL_MARGIN
        )
        keepouts.extend(
            Point(cx, cy).buffer(r, quad_segs=24)
            for cx, cy in _stack_locator_centres(eff)
        )
    return keepouts


def b4b_top_label_outline(box: BoxSpec):
    """Placed outline for the lid-top label: centred in X, ~one third back from
    the front (front is -Y), fitted inside a rectangle that clears every
    stacking boss keep-out."""
    eff = b4b_effective_box(box)
    if not eff.b4b.lid:
        raise ValueError("a top label needs the lid enabled")
    # The label lives on the derived lid footprint, not the child field.
    case_x, case_y = b4b_layout(box).case_size
    avail_w = case_x - 2.0 * B4B_TOP_LABEL_MARGIN
    avail_h = case_y / 3.0
    label_cy = -case_y / 6.0
    keepouts = _top_surface_keepouts(eff)

    def clear_rect(w: float, h: float) -> bool:
        rect = Polygon([
            (-w / 2.0, label_cy - h / 2.0), (w / 2.0, label_cy - h / 2.0),
            (w / 2.0, label_cy + h / 2.0), (-w / 2.0, label_cy + h / 2.0),
        ])
        return not any(rect.intersects(k) for k in keepouts)

    # Shrink height first (label band is wide and short), then width, until the
    # placed rectangle clears every boss.
    for _ in range(40):
        if clear_rect(avail_w, avail_h):
            break
        if avail_h > 4.0:
            avail_h = max(4.0, avail_h - 1.0)
        elif avail_w > 10.0:
            avail_w -= 2.0
        else:
            raise ValueError(
                "the top label cannot be placed clear of the stacking bosses; "
                "shorten the label, disable stacking, or use a larger Storage Box"
            )
    outline = _fit_text_outline(
        eff.b4b.label_text, avail_w, avail_h, B4B_TOP_LABEL_CAP_IDEAL
    )
    placed = translate_polygon(outline, 0.0, label_cy)
    # Hard guarantee: the pocket is never cut through a boss.
    for k in keepouts:
        if placed.intersects(k):
            raise ValueError(
                "the top label overlaps a stacking boss keep-out; shorten the "
                "label or disable stacking"
            )
    return placed


def _apply_top_label(box: BoxSpec, lid: trimesh.Trimesh):
    """Sink the top label flush into the lid; return ``(lid, inlay)`` where the
    inlay is a separate object that fills the pocket.  ``b4b_top_label_outline``
    has already proven the outline clears every stacking boss."""
    outline = b4b_top_label_outline(box)
    top_z = b4b_lid_underside_z(box) + b4b_lid_skin(box)
    pocket = text_prism(outline, top_z, depth=TEXT_DEPTH)
    inlay = text_prism(outline, top_z, depth=TEXT_DEPTH)
    return _weld(difference([lid, pocket])), inlay


def b4b_front_label_fit(box: BoxSpec) -> tuple[bool, float, float, float]:
    """``(fits, avail_w, insertion_ceiling_z, bottom_z)`` - the clear
    front-wall envelope the top-loading label holder may occupy, computed
    against the same real hardware geometry ``b4b_front_label_geometry``
    builds from, so the UI's eligibility check and the actual build can
    never disagree.

    ``avail_w`` already carries the <= 50% of the case width cap.
    ``insertion_ceiling_z`` is the lowest obstruction above the holder (latch
    catch/root, its underside taper, or a folded handle's root) - the plate
    plus its whole vertical travel must clear this on the way in or out.
    ``bottom_z`` is where the holder's closed bottom channel sits - normally
    about a third of the way up the inside height
    (``B4B_FRONT_LABEL_PREFERRED_HEIGHT_FRACTION``), but dropped as low as
    ``B4B_FRONT_LABEL_BOTTOM_MIN`` when the box needs the extra headroom;
    the holder is never grown to fill this envelope - the text shrinks to
    fit it instead, per ``b4b_front_label_geometry``.
    """
    eff = b4b_effective_box(box)
    plan = b4b_hardware_plan(box)
    layout = b4b_layout(box)
    span = _front_span(box)
    case_x, _case_y = layout.case_size

    avail_w = min(span - 4.0, B4B_FRONT_LABEL_MAX_WIDTH_FRACTION * case_x)
    # lowest obstruction above: the latch pads (or the rim if passive)
    if plan.latch_count_resolved:
        receiver_r = plan.profile.catch_radius
        # clear of the catch ears and of the root's 45-degree underside taper
        insertion_ceiling_z = min(
            plan.catch_axis_z - receiver_r - B4B_LABEL_KEEPOUT,
            plan.latch_root_top_z - plan.profile.latch_root_height
            - B4B_LABEL_KEEPOUT,
        )
    else:
        insertion_ceiling_z = eff.z - 4.0
    handle = b4b_handle_plan(box)
    if handle is not None:
        # The folded U frames the label rather than covering it: the readable
        # area is the clear opening between the arms, under the pivot forks.
        avail_w = min(avail_w, handle.clear_grip - 2.0 * B4B_LABEL_KEEPOUT)
        # The folded horizontal grip bar itself crosses the front wall lower
        # than the pivot root does on a short handle - the holder has to clear
        # that too, not just the root.
        grip_bottom_z = handle.grip_z - handle.band / 2.0 - B4B_LABEL_KEEPOUT
        insertion_ceiling_z = min(
            insertion_ceiling_z,
            handle.root_bottom_z - B4B_LABEL_KEEPOUT,
            grip_bottom_z,
        )
    side_margin = B4B_FRONT_LABEL_SIDE_LEG_W - B4B_FRONT_LABEL_SIDE_OVERLAP
    # Generic placeholders (not the actual label text) used only to answer
    # "could any readable label ever fit here", so the UI can gate the
    # control before the user has typed anything.
    min_plate_w = 6.0 + 2.0 * B4B_FRONT_LABEL_MARGIN_X
    min_plate_h = TEXT_CAP_HEIGHT_MIN + 2.0 * B4B_FRONT_LABEL_MARGIN_Y
    min_w = min_plate_w + 2.0 * side_margin
    bottom_z = _b4b_front_label_bottom_z(insertion_ceiling_z, min_plate_h, eff.z)
    fits = avail_w >= min_w and bottom_z is not None
    return fits, avail_w, insertion_ceiling_z, (
        bottom_z if bottom_z is not None else B4B_FRONT_LABEL_BOTTOM_MIN
    )


def b4b_front_label_eligibility(box: BoxSpec) -> tuple[bool, str]:
    """``(eligible, reason)`` - whether this case's front wall can carry a
    top-loading label, mirroring ``b4b_handle_eligibility``'s shape so the UI
    can gate both controls the same way."""
    fits, _avail_w, _ceiling_z, _bottom_z = b4b_front_label_fit(box)
    if fits:
        return True, ""
    if b4b_handle_plan(box) is not None:
        return False, (
            "Not enough size for a front label: the folded handle's grip "
            "leaves too little clear wall below it."
        )
    return False, "Not enough size for a front label."


# --------------------------------------------------------------------------- #
# front label styles: flat / wavy
# --------------------------------------------------------------------------- #
def _b4b_wave_mask_1d(t: float, half_span: float, flat_border: float, blend: float) -> float:
    """0 within ``flat_border`` of +/-``half_span``, 1.0 once ``blend`` past
    that, eased smoothly in between - one axis of the 2D mask that keeps the
    Wavy label's whole rectangular perimeter flat."""
    edge_dist = half_span - abs(t)
    if edge_dist <= flat_border:
        return 0.0
    if edge_dist >= flat_border + blend:
        return 1.0
    frac = (edge_dist - flat_border) / blend
    return 0.5 - 0.5 * math.cos(math.pi * frac)


def _b4b_wavy_front_y(plate_w: float, plate_h: float, plate_t: float):
    """The Wavy style's front-face height function ``front_y(x, z)``.

    Exactly the Storage Box/Wavefinity front-wall wave (``wave_value``, unmodified)
    in the centre of the plate, blending out within
    ``B4B_FRONT_LABEL_FLAT_BORDER`` of every edge to the same flat face the
    Flat style uses - so, viewed straight on, the Wavy label's outline is the
    identical rectangle and its side/top/bottom edges are perfectly flat,
    exactly where the side channels and bottom lip touch it.  The plate is
    centred on the case's own X=0, the same datum ``wave_value`` measures
    from, so the wave picked up here is in true phase with the surrounding
    front wall - never a restarted cycle at the label's own edge.
    """
    half_w, half_h = plate_w / 2.0, plate_h / 2.0
    border = B4B_FRONT_LABEL_FLAT_BORDER
    blend = B4B_FRONT_LABEL_WAVE_BLEND
    base_y = -plate_t / 2.0

    def front_y(x: float, z: float) -> float:
        mask = (
            _b4b_wave_mask_1d(x, half_w, border, blend)
            * _b4b_wave_mask_1d(z, half_h, border, blend)
        )
        return base_y + wave_value(x) * mask

    return front_y


def _b4b_wavy_label_z_samples(plate_h: float) -> np.ndarray:
    """Z rows needed to describe the Wavy label's flat borders and cosine
    blend transitions (see ``_b4b_wave_mask_1d``) - unlike X, where the wave
    itself varies and needs ``_sample_count``'s full per-mm density, the face
    is Z-invariant everywhere except the two ``B4B_FRONT_LABEL_WAVE_BLEND``
    bands just inside each edge: exactly flat within
    ``B4B_FRONT_LABEL_FLAT_BORDER`` of the edge, and exactly the constant
    full-wave shape for the rest of the middle.  Only those two blend bands
    need intermediate samples to approximate their cosine ease."""
    half_h = plate_h / 2.0
    border = B4B_FRONT_LABEL_FLAT_BORDER
    blend = B4B_FRONT_LABEL_WAVE_BLEND
    # Distances in from the edge where the mask has a breakpoint: right at
    # the edge, at the flat-border/blend boundary, through the blend in
    # sixths, and at the blend's inner edge (mask == 1.0 from there on in).
    edge_distances = (
        [0.0, border]
        + [border + blend * k / 6.0 for k in range(1, 6)]
        + [border + blend]
    )
    offsets = sorted({min(max(half_h - d, 0.0), half_h) for d in edge_distances})
    samples = sorted({-half_h, 0.0, half_h} | {o for o in offsets} | {-o for o in offsets})
    return np.array(samples, dtype=float)


def _b4b_wavy_label_slab(plate_w: float, plate_h: float, outer_fn, inner_fn) -> trimesh.Trimesh:
    """A watertight solid between two ``(x, z) -> y`` height functions over the
    rectangular ``plate_w`` x ``plate_h`` footprint: ``outer_fn`` toward -Y,
    ``inner_fn`` toward +Y.  One shared builder for the plain-backed plate
    blank (``inner_fn`` constant) and the thin wavy-faced text inlay/pocket
    shells (``inner_fn`` riding the same wave as ``outer_fn``, offset by a
    fixed depth) - both need the identical grid/side-wall topology.
    """
    half_w = plate_w / 2.0
    nx = max(2, _sample_count(plate_w))
    xs = np.linspace(-half_w, half_w, nx)
    zs = _b4b_wavy_label_z_samples(plate_h)
    nz = len(zs)

    outer = np.empty((nx, nz, 3))
    inner = np.empty((nx, nz, 3))
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            outer[i, j] = (x, outer_fn(float(x), float(z)), z)
            inner[i, j] = (x, inner_fn(float(x), float(z)), z)

    def idx(surface: int, i: int, j: int) -> int:
        return surface * nx * nz + i * nz + j

    vertices = np.concatenate([outer.reshape(-1, 3), inner.reshape(-1, 3)])
    faces: list[tuple[int, int, int]] = []

    def quad(a: int, b: int, c: int, d: int) -> None:
        faces.append((a, b, c))
        faces.append((a, c, d))

    for i in range(nx - 1):
        for j in range(nz - 1):
            quad(idx(0, i, j), idx(0, i + 1, j), idx(0, i + 1, j + 1), idx(0, i, j + 1))
            quad(idx(1, i, j), idx(1, i, j + 1), idx(1, i + 1, j + 1), idx(1, i + 1, j))
    for j in range(nz - 1):
        quad(idx(0, 0, j), idx(0, 0, j + 1), idx(1, 0, j + 1), idx(1, 0, j))
        quad(idx(0, nx - 1, j), idx(1, nx - 1, j), idx(1, nx - 1, j + 1), idx(0, nx - 1, j + 1))
    for i in range(nx - 1):
        quad(idx(0, i, 0), idx(1, i, 0), idx(1, i + 1, 0), idx(0, i + 1, 0))
        quad(idx(0, i, nz - 1), idx(0, i + 1, nz - 1), idx(1, i + 1, nz - 1), idx(1, i, nz - 1))

    mesh = trimesh.Trimesh(
        vertices=vertices, faces=np.asarray(faces, dtype=np.int64), process=True,
    )
    mesh.merge_vertices()
    trimesh.repair.fix_winding(mesh)
    if mesh.volume < 0:
        mesh.invert()
    if not (mesh.is_watertight and mesh.is_winding_consistent):
        raise RuntimeError("wavy label slab is not a clean solid")
    return mesh


def _b4b_wavy_label_blank(plate_w: float, plate_h: float) -> trimesh.Trimesh:
    """The Wavy plate blank, before its text pocket: a flat rectangular back,
    the exact Wavefinity wave in the centre of the front face, and a flat
    rectangular perimeter everywhere else - see ``_b4b_wavy_front_y``."""
    plate_t = B4B_FRONT_LABEL_PLATE_T
    front_y = _b4b_wavy_front_y(plate_w, plate_h, plate_t)
    return _b4b_wavy_label_slab(plate_w, plate_h, front_y, lambda _x, _z: plate_t / 2.0)


def _b4b_text_extrusion_mask(outline, y_lo: float, y_hi: float) -> trimesh.Trimesh:
    """A solid spanning ``[y_lo, y_hi]`` in Y over ``outline``'s glyph
    footprint, centred at local (x=0, z=0) - identical placement to the Flat
    style's lettering (see ``_b4b_flat_front_label_plate_and_text``), just
    extruded deep enough to cut all the way through a thin wavy shell."""
    depth = y_hi - y_lo
    letters = text_prism(outline, top_z=0.0, depth=depth)  # z in [-depth, 0]
    # +90 deg about X: extrude axis (-Z) -> +Y, glyph height (+Y) -> +Z upright
    letters.apply_transform(
        trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
    )
    centre = letters.bounds.mean(axis=0)
    letters.apply_translation((-centre[0], 0.0, -centre[2]))
    y_min = float(letters.bounds[0][1])
    return translated(letters, (0.0, y_lo - y_min, 0.0))


def _b4b_flat_front_label_plate_and_text(
    outline, plate_w: float, plate_h: float,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Flat style: today's plain rectangular plate with a flush two-part
    lettering inlay on its readable (-Y) face - unchanged geometry."""
    plate_t = B4B_FRONT_LABEL_PLATE_T
    plate = trimesh.creation.box(extents=(plate_w, plate_t, plate_h))

    front_face_y = -plate_t / 2.0
    inlay_overlap = 0.1
    letters = text_prism(outline, top_z=0.0, depth=TEXT_DEPTH)  # z in [-TEXT_DEPTH, 0]
    # +90 deg about X: extrude axis (-Z) -> +Y, glyph height (+Y) -> +Z upright
    letters.apply_transform(
        trimesh.transformations.rotation_matrix(math.pi / 2.0, (1.0, 0.0, 0.0))
    )
    centre = letters.bounds.mean(axis=0)
    letters.apply_translation((-centre[0], 0.0, -centre[2]))   # centre on the plate face
    y_min = float(letters.bounds[0][1])
    # The fill piece sits exactly flush with the plate's face; the cutter is
    # nudged 0.1 mm proud of it so the boolean always removes material cleanly.
    text_solid = translated(letters, (0.0, front_face_y - y_min, 0.0))
    pocket = translated(letters, (0.0, (front_face_y - inlay_overlap) - y_min, 0.0))
    plate = difference([plate, pocket])
    return plate, text_solid


def _b4b_wavy_front_label_plate_and_text(
    outline, plate_w: float, plate_h: float,
) -> tuple[trimesh.Trimesh, trimesh.Trimesh]:
    """Wavy style: the same flush two-part inlay as Flat, but both plate and
    text follow the exact B4B/Wavefinity wave in the centre of the visible
    face.  The text is cut from, and fills, that identical wavy surface (a
    thin shell intersected with the glyph outline), so it is flush wherever
    the wave actually sits - never floating over a crest or buried in a
    trough - and remains a separate flush inlay for two-colour printing."""
    plate_t = B4B_FRONT_LABEL_PLATE_T
    inlay_overlap = 0.1
    blank = _b4b_wavy_label_blank(plate_w, plate_h)
    front_y = _b4b_wavy_front_y(plate_w, plate_h, plate_t)
    # Comfortably spans every possible front_y() value (+/- WAVE_AMPLITUDE
    # around -plate_t/2) through the deepest pocket offset, with margin.
    y_lo = -plate_t / 2.0 - WAVE_AMPLITUDE - 0.2
    y_hi = plate_t / 2.0 + TEXT_DEPTH + inlay_overlap + 0.2
    text_mask = _b4b_text_extrusion_mask(outline, y_lo, y_hi)

    text_shell = _b4b_wavy_label_slab(
        plate_w, plate_h, front_y, lambda x, z: front_y(x, z) + TEXT_DEPTH,
    )
    pocket_shell = _b4b_wavy_label_slab(
        plate_w, plate_h,
        lambda x, z: front_y(x, z) - inlay_overlap,
        lambda x, z: front_y(x, z) + TEXT_DEPTH - inlay_overlap,
    )
    text_solid = _intersection([text_mask, text_shell])
    pocket = _intersection([text_mask, pocket_shell])
    plate = difference([blank, pocket])
    return plate, text_solid


def b4b_front_label_geometry(box: BoxSpec):
    """``(frame_solid, plate_solid, text_solid, plate_centre_xyz)`` for the
    compact top-loading front label.

    The frame (holder) is unioned into the body from a left channel, a right
    channel, and a ramped bottom stop - all built directly on a locally
    flattened patch of the real front wall, never a separate rectangular
    backing slab.  There is no continuous top member (the plate drops
    straight in) and no finger notch, snap detent, or retention feature of
    any kind: the plate is meant to slide freely in and back out, held only
    by gravity, the bottom stop and the side channels.  The plate and its
    lettering are sized from the actual text outline,
    never grown past ``B4B_FRONT_LABEL_CAP_IDEAL``, and the whole holder is
    capped at ``B4B_FRONT_LABEL_MAX_WIDTH_FRACTION`` of the case width: text
    shrinks to fit before the holder is ever allowed to grow.

    Before settling on a size, the fit is checked against the real vertical
    insertion corridor: the clear space above the holder's open top (up to
    ``insertion_ceiling_z``, the lowest latch/handle obstruction) must fit
    the plate's own height of travel to slide it into place, plus
    ``B4B_FRONT_LABEL_INSERT_CLEARANCE`` of working clearance.  The holder
    first tries its preferred resting height - about a third of the way up
    the inside height - and, if that alone doesn't leave enough headroom,
    drops as low as ``B4B_FRONT_LABEL_BOTTOM_MIN`` to buy back the
    difference - only once that's exhausted does the ideal 10 mm cap
    height give way, shrinking down to the project's minimum readable size,
    before the front label is rejected for this box.

    ``box.b4b.front_label_style`` picks the plate's visible face: ``"flat"``
    (default) is an ordinary flat rectangular plate; ``"wavy"`` carries the
    exact B4B/Wavefinity front-wall wave across the centre of its face while
    staying perfectly flat around its whole rectangular perimeter, so it
    slides into the exact same holder - see ``_b4b_wavy_front_label_plate_and_text``.
    Either way the lettering is a flush two-part inlay: ``plate_solid``
    carries a shallow pocket on its readable face and ``text_solid`` is the
    separate, identically-shaped object that fills it, so a slicer can print
    the two in different filaments.
    """
    eff = b4b_effective_box(box)
    layout = b4b_layout(box)
    fits, avail_w, insertion_ceiling_z, _bottom_z = b4b_front_label_fit(box)
    if not fits:
        raise ValueError(
            "not enough clear front-wall area for a top-loading label; use a "
            "top label, a taller box, or turn latches off"
        )
    text = eff.b4b.label_text.strip()
    if not text:
        raise ValueError("label text is empty")

    clear = B4B_FRONT_LABEL_CLEAR
    plate_t = B4B_FRONT_LABEL_PLATE_T
    leg_w = B4B_FRONT_LABEL_SIDE_LEG_W
    side_overlap = B4B_FRONT_LABEL_SIDE_OVERLAP
    side_margin = leg_w - side_overlap
    holder_depth = B4B_FRONT_LABEL_HOLDER_DEPTH

    # Fit the lettering to the widest space the envelope could ever offer,
    # then shrink the cap height step by step until the resulting plate
    # actually leaves a clear vertical insertion corridor above it - the
    # holder drops as low as ``_b4b_front_label_bottom_z`` allows, which is
    # always the best case for that corridor, so if it fails there it fails
    # everywhere and the text must shrink instead.
    max_plate_w = avail_w - 2.0 * side_margin
    max_text_w = max_plate_w - 2.0 * B4B_FRONT_LABEL_MARGIN_X
    cap = B4B_FRONT_LABEL_CAP_IDEAL
    solved = None
    while cap >= TEXT_CAP_HEIGHT_MIN - 1e-6:
        outline = text_outline(text, cap)
        tminx, tminy, tmaxx, tmaxy = outline.bounds
        text_w = tmaxx - tminx
        text_h = tmaxy - tminy
        if text_w <= max_text_w:
            plate_w = text_w + 2.0 * B4B_FRONT_LABEL_MARGIN_X
            plate_h = text_h + 2.0 * B4B_FRONT_LABEL_MARGIN_Y
            plate_bottom_z = _b4b_front_label_bottom_z(insertion_ceiling_z, plate_h, eff.z)
            if plate_bottom_z is not None:
                solved = (outline, plate_w, plate_h, plate_bottom_z)
                break
        cap -= 0.5
    if solved is None:
        raise ValueError(
            "no front label size leaves a clear vertical insertion path "
            "above the holder; use a top label, a taller box, or turn "
            "latches off"
        )
    outline, plate_w, plate_h, bottom_z = solved

    holder_w = plate_w + 2.0 * side_margin
    seat_z = bottom_z + holder_depth        # top of the bottom stop = plate's resting Z
    holder_top_z = seat_z + plate_h         # open top = top of the seated plate

    # The real B4B wall is wavy (a printable interlock texture); the label
    # needs a flat backing instead, so fill the wave valleys - only across
    # this holder's own footprint, never touching the child-bin mating face
    # or the rest of the wall - out to the most outward point the wave
    # reaches over that span.  Every other member below is built against
    # this flat reference, not the raw wavy exterior.
    flat_back_y = _wall_extreme_y(layout, -holder_w / 2.0, holder_w / 2.0, -1.0)
    # Guaranteed inside solid wall material for every x in the span (the
    # wave's shallowest possible point, plus a small margin) - never as deep
    # as the inner mating face, so child-bin capacity is untouched.
    wall_patch_inner_y = -layout.outer_half_y + WAVE_AMPLITUDE + 0.3
    # Nudge new-part-to-patch attachments a little past ``flat_back_y`` so
    # union() always finds real volumetric overlap, never a bare face touch.
    embed = min(0.8, max(0.3, eff.wall_depth * 0.5))

    plate_back_y = flat_back_y - clear
    plate_front_y = plate_back_y - plate_t
    capture_lip_back_y = plate_front_y - clear
    holder_front_y = flat_back_y - holder_depth
    channel_t = plate_back_y - plate_front_y + 2.0 * clear  # == 2*clear + plate_t

    patch = trimesh.creation.box(extents=(
        holder_w, wall_patch_inner_y - flat_back_y, holder_top_z - bottom_z,
    ))
    patch.apply_translation((
        0.0,
        (wall_patch_inner_y + flat_back_y) / 2.0,
        (holder_top_z + bottom_z) / 2.0,
    ))

    # Ramped bottom stop: a plain wedge, vertical against the flat patch and
    # rising outward at exactly 45 degrees to its front-top tip, so the
    # underside is a single self-supporting slope rather than a horizontal,
    # unsupported shelf - the body prints upright and this needs no support.
    wedge_profile = Polygon([
        (flat_back_y + embed, seat_z),
        (holder_front_y, seat_z),
        (flat_back_y + embed, bottom_z),
    ])
    wedge = _extrude_yz_profile(wedge_profile, holder_w)

    # The seat alone only stops the plate falling further down; a front lip
    # is needed too, so the plate's bottom edge can't bow or be pulled
    # straight out the front either.  It sits directly on the wedge's own
    # flat top, which already reaches out to ``holder_front_y``, so this
    # needs no support of its own.
    bottom_lip_h = side_overlap
    bottom_lip = trimesh.creation.box(extents=(
        holder_w, capture_lip_back_y - holder_front_y, bottom_lip_h,
    ))
    bottom_lip.apply_translation((
        0.0,
        (capture_lip_back_y + holder_front_y) / 2.0,
        seat_z + bottom_lip_h / 2.0,
    ))

    def _side_channel(side: float) -> trimesh.Trimesh:
        """One left/right channel: a leg attached to the flat patch with a
        front lip overlapping ``side_overlap`` of the plate's edge, so the
        plate must be lifted clear of it rather than pulled straight out the
        front - unlike a friction-fit slide, nothing depends on how snugly
        it happens to sit."""
        leg_centre_x = side * (plate_w / 2.0 - side_overlap + leg_w / 2.0)
        leg_depth = (flat_back_y + embed) - holder_front_y
        leg = trimesh.creation.box(extents=(leg_w, leg_depth, plate_h))
        leg.apply_translation((
            leg_centre_x,
            (flat_back_y + embed + holder_front_y) / 2.0,
            (seat_z + holder_top_z) / 2.0,
        ))
        slot_centre_x = side * (plate_w / 2.0 - side_overlap / 2.0)
        slot = trimesh.creation.box(extents=(side_overlap, channel_t, plate_h))
        slot.apply_translation((
            slot_centre_x,
            (flat_back_y + capture_lip_back_y) / 2.0,
            (seat_z + holder_top_z) / 2.0,
        ))
        return difference([leg, slot])

    frame = _weld(union([
        patch, wedge, bottom_lip, _side_channel(-1.0), _side_channel(1.0),
    ]))

    if eff.b4b.front_label_style == "wavy":
        plate, text_solid = _b4b_wavy_front_label_plate_and_text(outline, plate_w, plate_h)
    else:
        plate, text_solid = _b4b_flat_front_label_plate_and_text(outline, plate_w, plate_h)

    plate_centre = (
        0.0,
        flat_back_y - clear - plate_t / 2.0,
        seat_z + plate_h / 2.0,
    )
    return frame, plate, text_solid, plate_centre


def make_b4b_front_label_plate(box: BoxSpec) -> trimesh.Trimesh:
    """The top-loading plate alone (background only), positioned in assembly space."""
    _frame, plate, _text, centre = b4b_front_label_geometry(box)
    return translated(plate, centre)


def make_b4b_front_label_text(box: BoxSpec) -> trimesh.Trimesh:
    """The flush lettering inlay alone, registered to the plate's pocket."""
    _frame, _plate, text, centre = b4b_front_label_geometry(box)
    return translated(text, centre)
