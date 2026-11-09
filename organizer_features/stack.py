"""Stackable bins - a lid that carries the next bin, or a plain locating skirt.

Two same-mode interfaces:

``lid``     the bin is closed by its own printed lid.  A resting lid can carry
            a 2 mm rim on its top face; the next bin's stepped base drops into
            that rim.
``direct``  no lid at all - a straight-sided skirt under the bin's base drops
            into the mouth of the bin below and stops the stack sliding.  It
            only locates: nothing snaps, clicks or grips, and the receiving
            mouth stays plain.

Lid bins stack on lid bins and direct bins stack on direct bins.  The lid's
retention uses lighter lock-bump-style points near the rim.

A lid bin's typed height is the *stack module height* - the distance between
the seating datums of consecutive bins - and its stepped foot extends the
detached part's physical envelope by the engagement depth.  A direct bin's
skirt lives inside the typed height: the bin measures exactly what was typed,
and each bin added to a stack adds the typed height less the skirt depth,
because the skirt overlaps the top of the bin below.
"""

from __future__ import annotations

import math
from dataclasses import replace

import trimesh
from shapely.ops import unary_union
from shapely.geometry import LineString, MultiPolygon, Polygon, box as shapely_box

from organizer_engine import (
    BoxSpec,
    DEFAULT_BASE_THICKNESS,
    DEFAULT_WALL,
    LOCK_RUN,
    MIN_HEIGHT_ABOVE_BASE,
    StackSpec,
    TEXT_DEPTH,
    _lock_profile,
    direct_stack_enabled,
    LID_LABEL_SIZE_CAP_MM,
    LID_THICKNESSES,
    lid_alignment_mm,
    lid_enabled,
    lid_fit_mm,
    lid_has_flip,
    lid_has_handle,
    lid_label_relief_mm,
    lid_spec,
    lid_receives_stack,
    text_outline,
    text_prism,
    vertical_stack_enabled,
    wavy_cavity_polygon,
    wavy_outer_polygon,
)
from organizer_features.lid_handle import handle_height, handle_keepout, resolve_lid_handle
from organizer_features.lid_hinge import (
    HINGE_BARREL_RADIUS,
    HINGE_BORE_RADIUS,
    HINGE_PIN_DIAMETER,
    LidHinge,
    body_hinge_cutters,
    body_hinge_parts,
    hinge_layout,
    lid_hinge_parts,
    plate_hinge_cutter,
)
from organizer_geometry import (
    _align_ring,
    _extrude_polygon,
    _loft_cavity,
    _resampled_ring,
    difference,
    intersection,
    union,
)

# --------------------------------------------------------------------------- #
# tuning - conservative first-print values
# --------------------------------------------------------------------------- #
# The plate has to stay thicker than the seat cut into it, or the recess floor
# lands exactly on the plug's top face and the lid unions as two loose pieces
# instead of one - and the bin above would be standing on nothing.
STACK_LID_SKIN = 2.0      # minimum lid rise above the rim
STACK_SEAT_DEPTH = 2.0    # resting-lid stack rim height == the skirt depth of the bin that sits in it
STACK_LID_RIM_WIDTH = 1.2  # radial width of the resting-lid stack rim
STACK_PLUG_DEPTH = 3.0    # how far a lid plug reaches into the mouth it closes
STACK_INTERIOR_MARGIN = 0.5  # lidded bins: interior parts stop this far below the plug bottom
STACK_SKIRT_DEPTH = 2.0   # direct mode: how far the skirt drops into the bin below
STACK_LID_SKIRT_WIDTH = 1.6  # regular lids: radial width of the hollow locating skirt band
STACK_SKIRT_BEVEL = 1.0   # direct mode: 45 degree lead-in on the skirt's entering edge
STACK_PROFILE_POINTS = 192
STACK_FIT = 0.25          # clearance per side on every sliding face
STACK_MIN_FLOOR_SKIN = 0.8   # floor left under the stepped base
# A lid's retention clips and recess need wall behind them.
STACK_MIN_WALL = 1.2      # lid bins only; a plain skirt needs no extra wall

# Lid retention borrows the side connector's printable lock profile, but not
# its physical lock points.  These snaps sit above the connector locks and at
# wall centres, between their half-wave lattice positions.  Their 0.12 mm
# interference is intentionally much lighter than the connector's 0.35 mm.
LID_LOCK_INTERFERENCE = 0.12
LID_LOCK_CLEARANCE = 0.08
LID_LOCK_DROP = 1.5
LID_LOCK_EMBED = 0.20
LID_FOUR_SNAP_MIN_SPAN = 40.0
LID_LABEL_MARGIN = 2.0
LID_LABEL_MIN_CAP = 2.5
LID_LABEL_MIN_BACKING = 0.4   # lid left under an inlaid label pocket

_EPS = 1e-6
_PROFILE_EPS = 0.02


def stack_spec(box: BoxSpec) -> StackSpec:
    return getattr(box, "stack", None) or StackSpec()


def stack_enabled(box: BoxSpec) -> bool:
    return vertical_stack_enabled(box)


def stack_lid_rise(box: BoxSpec) -> float:
    """How far the lid rises above the body rim.

    A thick custom body wall moves the mouth farther from the outside face.
    The lid grows vertically when needed so a 45 degree or shallower flare
    still fits.  The exterior itself meets the rim flush: there is no shoulder
    or flare above the rim to recess it.
    """
    if not lid_enabled(box):
        return 0.0
    plate = float(lid_spec(box).thickness)
    # A rimmed resting lid is its plate (the chosen thickness) plus the rim
    # standing on it. The rim's height is counted here, once, and every stack
    # height and fit check is built from this rise.
    return plate + (STACK_SEAT_DEPTH if lid_receives_stack(box) else 0.0)


def stack_step_depth(box: BoxSpec) -> float:
    """How far the bin's own stepped base drops into whatever is below it.

    It is the skirt, which drops into the mouth of the bin below or into the
    stack seat of that bin's lid (the seat is cut as deep as the skirt).
    """
    return STACK_SKIRT_DEPTH if direct_stack_enabled(box) else 0.0


def stack_foot_growth(box: BoxSpec) -> float:
    """How far the body grows past the typed height to hold its stepped foot.

    Always zero: a lid bin's stepped foot and a direct bin's skirt are both
    formed inside the typed height, so the part measures exactly what was typed.
    """
    return 0.0


def _stack_wall_box(box: BoxSpec) -> BoxSpec:
    """``box`` with the wall its stack hardware needs: a lid's clips and recess
    want ``STACK_MIN_WALL``; a plain skirt asks nothing of the wall."""
    if not lid_enabled(box):
        return box
    return replace(box, wall=max(box.wall, STACK_MIN_WALL), standard_walls=False)


def stack_base_minimum(box: BoxSpec) -> float:
    """Visible/saved base thickness required by the selected stack foot.

    Direct skirts need only their depth and floor skin. Lid feet also need
    room for their flare inside the solid base.
    """
    if not vertical_stack_enabled(box):
        return DEFAULT_BASE_THICKNESS
    if direct_stack_enabled(box):
        return STACK_SKIRT_DEPTH + STACK_MIN_FLOOR_SKIN
    flare = stack_foot_flare_height(_stack_wall_box(box))
    return stack_step_depth(box) + max(STACK_MIN_FLOOR_SKIN, flare)


def normalize_stack_settings(box: BoxSpec) -> BoxSpec:
    """Return legal, user-visible wall/base settings for stacking.

    The browser writes these values itself.  This remains the backend safety
    net for old files, API callers and command-line construction.
    """
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return box
    changes: dict = {}
    if lid_enabled(box):
        changes.update(wall=max(box.wall, STACK_MIN_WALL), standard_walls=False)
    if vertical_stack_enabled(box):
        changes.update(
            base_thickness=max(box.base_thickness, stack_base_minimum(box)),
            standard_base=False,
        )
    return replace(box, **changes)


def stack_effective_box(box: BoxSpec) -> BoxSpec:
    """The BoxSpec the body and its interior parts are actually built from.

    Settings are normalized defensively.  Consecutive bodies are placed one
    stack pitch apart, so the foot overlaps without falsifying the pitch.  A
    direct bin's skirt and a lid bin's foot sit inside the typed height, so
    the body plus its lid rise is exactly that tall.  Any lidded bin is
    shortened once by its lid's rise (plate plus the stack seat's rise): the
    typed height is the total.
    """
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return box
    normalized = normalize_stack_settings(box)
    body_z = box.z + stack_foot_growth(box) - stack_lid_rise(normalized)
    return replace(normalized, z=body_z)


def stack_seated_height(eff: BoxSpec) -> float:
    """Height of the bin as it seats (body plus lid rise) from its effective box."""
    return eff.z + stack_lid_rise(eff)


def stack_grew(box: BoxSpec) -> bool:
    """Whether stacking had to change what the user entered."""
    eff = stack_effective_box(box)
    return not (
        math.isclose(eff.wall, box.wall)
        and math.isclose(eff.z, box.z)
        and math.isclose(eff.base_thickness, box.base_thickness)
    )


# --------------------------------------------------------------------------- #
# shared outlines
# --------------------------------------------------------------------------- #
def _plug_polygon(eff: BoxSpec, fit: float = STACK_FIT) -> Polygon:
    """Outline of anything that plugs into the bin mouth at ``fit`` per side.

    Three interfaces share this shape, but only the first two must keep the
    accepted 0.25 mm stack fit: the bin stepped base (direct foot) and a
    lid top stack seat, so a base always fits a seat.  The removable
    lid bottom plug asks for its own fit through ``_lid_plug_polygon``.
    """
    plug = wavy_cavity_polygon(eff).buffer(-fit)
    if plug.is_empty or not isinstance(plug, Polygon):
        raise ValueError(
            "this bin is too small to stack - widen it or turn stacking off"
        )
    return plug


def _lid_plug_polygon(eff: BoxSpec) -> Polygon:
    """Outline of the removable lid bottom plug: Tight / Standard / Loose."""
    return _plug_polygon(eff, lid_fit_mm(eff))


# --------------------------------------------------------------------------- #
# flip lid (all of it gated on the option; a plain lid never reaches here)
# --------------------------------------------------------------------------- #
_FLIP_HINGES: dict = {}


def _lid_hinge(eff: BoxSpec) -> LidHinge | None:
    """The resolved hinge of an effective box, or None when the lid is loose."""
    if not (lid_enabled(eff) and lid_has_flip(eff)):
        return None
    rise = stack_lid_rise(eff)
    seat = STACK_SEAT_DEPTH if lid_receives_stack(eff) else 0.0
    key = (eff.half_x, eff.half_y, eff.wall_depth, eff.corner_fillet, eff.wall,
           eff.z, eff.base_thickness, rise, seat)
    hinge = _FLIP_HINGES.get(key)
    if hinge is None:
        hinge = hinge_layout(wavy_cavity_polygon(eff), eff.z, rise, seat,
                             STACK_PLUG_DEPTH, eff.base_thickness,
                             outer=wavy_outer_polygon(eff))
        if len(_FLIP_HINGES) > 32:
            _FLIP_HINGES.clear()
        _FLIP_HINGES[key] = hinge
    return hinge


def _lid_skirt(eff: BoxSpec, rim: float) -> trimesh.Trimesh:
    """Regular lid underside: a shallow perimeter band on the plug outline, open in the middle."""
    outline = _lid_plug_polygon(eff)
    inner = outline.buffer(-STACK_LID_SKIRT_WIDTH)
    band = outline if inner.is_empty else outline.difference(inner)
    skirt = _extrude_polygon(band, STACK_SKIRT_DEPTH)
    skirt.apply_translation((0.0, 0.0, rim - STACK_SKIRT_DEPTH))
    return skirt


LID_ALIGNMENT_REACH = 0.2    # each tab leg runs this fraction of the lid length from its corner
LID_ALIGNMENT_WALL = 1.2     # radial thickness of an alignment tab leg


def _lid_alignment_tabs(eff: BoxSpec, rim: float) -> list[trimesh.Trimesh]:
    """L-shaped tabs under a hinged lid at the two front corners (opposite the hinge).

    Each tab is the mouth outline (at the stack locating clearance) cut to a thin
    band and kept within one fifth of the lid length of its corner, so its legs
    follow the inside of the front wall and of the adjoining side wall.  Off
    returns nothing.
    """
    depth = lid_alignment_mm(eff)
    if depth <= 0.0:
        return []
    outline = _plug_polygon(eff)
    band = outline.difference(outline.buffer(-LID_ALIGNMENT_WALL))
    if band.is_empty:
        band = outline
    min_x, min_y, max_x, _ = outline.bounds
    reach = LID_ALIGNMENT_REACH * 2.0 * eff.half_y
    tabs: list[trimesh.Trimesh] = []
    for x0, x1 in ((min_x - 1.0, min_x + reach), (max_x - reach, max_x + 1.0)):
        piece = band.intersection(shapely_box(x0, min_y - 1.0, x1, min_y + reach))
        geoms = getattr(piece, "geoms", [piece])
        for part in geoms:
            if isinstance(part, Polygon) and not part.is_empty and part.area > 1e-6:
                # Run 0.2 mm up into the plate so the tab unions as one solid.
                tab = _extrude_polygon(part, depth + 0.2)
                tab.apply_translation((0.0, 0.0, rim - depth))
                tabs.append(tab)
    return tabs


def _clip_back(polygon: Polygon, back_y: float) -> Polygon:
    """The part of ``polygon`` that lies in front of ``back_y``."""
    min_x, min_y, max_x, _ = polygon.bounds
    kept = polygon.intersection(shapely_box(min_x - 1.0, min_y - 1.0, max_x + 1.0, back_y))
    if isinstance(kept, MultiPolygon):
        kept = max(kept.geoms, key=lambda one: one.area)
    if kept.is_empty or not isinstance(kept, Polygon):
        raise ValueError("this bin is too shallow for a flip lid - turn Flip lid off")
    return kept


def _lid_top_polygon(eff: BoxSpec, hinge: LidHinge | None) -> Polygon:
    """Plan outline of the lid plate: the bin's outline, less the hinge strip."""
    outer = wavy_outer_polygon(eff)
    return outer if hinge is None else _clip_back(outer, hinge.plate_back_y)


def _profile_loft(polygons: list[Polygon], heights: list[float]) -> trimesh.Trimesh:
    """Loft matched wavy outlines into one watertight support-free profile."""
    reference = _resampled_ring(polygons[0], STACK_PROFILE_POINTS)
    rings = [reference]
    rings.extend(
        _align_ring(reference, _resampled_ring(one, STACK_PROFILE_POINTS))
        for one in polygons[1:]
    )
    return _loft_cavity(rings, heights)


def _outline_run(inner: Polygon, outer: Polygon) -> float:
    """Maximum XY growth between two nested outlines."""
    return float(inner.exterior.hausdorff_distance(outer.exterior))


def stack_foot_flare_height(eff: BoxSpec) -> float:
    """Vertical run needed for a <=45 degree foot/lid flare."""
    run = _outline_run(_plug_polygon(eff), wavy_outer_polygon(eff))
    return math.ceil((run + _EPS) * 100.0) / 100.0


def _narrowest_mouth(cavity: Polygon, across: str) -> float:
    """Half-width of the mouth at its wave crests along one axis.

    Probes a band of the straight run clear of the corners, a full wave long
    wherever the bin is big enough to have one.
    """
    min_x, min_y, max_x, max_y = cavity.bounds
    half_run = (max_y if across == "x" else max_x)
    reach = max(0.0, half_run - 3.0)
    count = int(2.0 * reach / 0.25) + 1
    least = (max_x if across == "x" else max_y)
    for index in range(count):
        at = 0.0 if count == 1 else -reach + 2.0 * reach * index / (count - 1)
        if across == "x":
            probe = LineString([(min_x - 1.0, at), (max_x + 1.0, at)])
        else:
            probe = LineString([(at, min_y - 1.0), (at, max_y + 1.0)])
        hit = cavity.intersection(probe)
        if hit.is_empty:
            continue
        bx0, by0, bx1, by1 = hit.bounds
        low, high = (bx0, bx1) if across == "x" else (by0, by1)
        least = min(least, -low, high)
    return least


_SKIRTS: dict = {}


def _skirt_polygon(eff: BoxSpec) -> Polygon:
    """Plan outline of the direct-stack skirt: straight sided, centred.

    The mouth it drops into is wavy; a straight skirt can only touch it on the
    wave crests, so it is sized to the narrowest the mouth ever gets, less the
    sliding fit.  Intersecting with the fitted mouth keeps the rounded corners
    inside it too.
    """
    key = (eff.half_x, eff.half_y, eff.wall_depth, eff.corner_fillet, eff.wall)
    cached = _SKIRTS.get(key)
    if cached is not None:
        return cached
    too_small = "this bin is too small to stack - widen it or turn stacking off"
    cavity = wavy_cavity_polygon(eff)
    half_x = _narrowest_mouth(cavity, "x") - STACK_FIT
    half_y = _narrowest_mouth(cavity, "y") - STACK_FIT
    if half_x <= 0.0 or half_y <= 0.0:
        raise ValueError(too_small)
    skirt = shapely_box(-half_x, -half_y, half_x, half_y).intersection(
        cavity.buffer(-STACK_FIT)
    )
    if (skirt.is_empty or not isinstance(skirt, Polygon)
            or skirt.buffer(-STACK_SKIRT_BEVEL).is_empty):
        raise ValueError(too_small)
    if len(_SKIRTS) > 32:
        _SKIRTS.clear()
    _SKIRTS[key] = skirt
    return skirt


def _skirt_keep(eff: BoxSpec) -> trimesh.Trimesh:
    """Straight skirt with a small bevel on its entering edge."""
    skirt = _skirt_polygon(eff)
    return _profile_loft(
        [skirt.buffer(-STACK_SKIRT_BEVEL), skirt, skirt],
        [-2.0 * _PROFILE_EPS, STACK_SKIRT_BEVEL, stack_step_depth(eff) + _PROFILE_EPS],
    )


def _lid_lock_masks(eff: BoxSpec) -> list[Polygon]:
    """Two centred points on small lids, one per side on larger lids.

    Sized from the bin cavity alone, so the lock positions - and the body
    notches cut with the same masks - never move with the lid fit preset.
    """
    plug = _plug_polygon(eff)
    outer = wavy_outer_polygon(eff)
    min_x, min_y, max_x, max_y = plug.bounds
    out_min_x, out_min_y, out_max_x, out_max_y = outer.bounds
    half_run = LOCK_RUN / 2.0
    overlap = 1.0
    pad = STACK_FIT + LID_LOCK_INTERFERENCE + LID_LOCK_CLEARANCE + 0.5

    horizontal = [
        shapely_box(-half_run, max_y - overlap, half_run, out_max_y + pad),
        shapely_box(-half_run, out_min_y - pad, half_run, min_y + overlap),
    ]
    vertical = [
        shapely_box(max_x - overlap, -half_run, out_max_x + pad, half_run),
        shapely_box(out_min_x - pad, -half_run, min_x + overlap, half_run),
    ]
    if max(eff.x, eff.y) >= LID_FOUR_SNAP_MIN_SPAN:
        return [*horizontal, *vertical]
    return horizontal if eff.x >= eff.y else vertical


def _lid_lock_profile(
    protrusion: float, rim: float, clearance: float = 0.0,
) -> list[tuple[float, float]]:
    """The connector lock's 45-degree profile moved to the lid snap height."""
    profile = _lock_profile(
        protrusion, clearance=clearance, embed=LID_LOCK_EMBED,
    )
    flat_centre = (profile[1][1] + profile[2][1]) / 2.0
    shift = rim - LID_LOCK_DROP - flat_centre
    return [(t, z + shift) for t, z in profile]


def _clip_lid_locks(
    solid: trimesh.Trimesh,
    eff: BoxSpec,
    profile: list[tuple[float, float]],
    floor: float | None = None,
) -> list[trimesh.Trimesh]:
    z0 = min(z for _, z in profile)
    if floor is not None:
        z0 = max(z0, floor) + _PROFILE_EPS     # mask starts z0 - eps: exactly at ``floor``
    z1 = max(z for _, z in profile)
    pieces: list[trimesh.Trimesh] = []
    for polygon in _lid_lock_masks(eff):
        mask = _extrude_polygon(polygon, z1 - z0 + 2.0 * _PROFILE_EPS)
        mask.apply_translation((0.0, 0.0, z0 - _PROFILE_EPS))
        piece = intersection([solid, mask])
        if len(piece.faces):
            pieces.append(piece)
    return pieces


def _lid_lock_bumps(eff: BoxSpec, rim: float) -> list[trimesh.Trimesh]:
    """Small discrete bumps on the lid plug.

    The bump reaches the plug fit plus the retention interference, so its tip
    always ends the same distance past the cavity wall whatever the Tight /
    Standard / Loose plug fit is: the click strength does not change with it.
    """
    fit = lid_fit_mm(eff)
    profile = _lid_lock_profile(fit + LID_LOCK_INTERFERENCE, rim)
    cavity = wavy_cavity_polygon(eff)
    # ``t`` is measured from the plug edge; re-measured from the cavity wall it
    # is ``t - fit``, which puts the bump tip LID_LOCK_INTERFERENCE past the wall
    # for Tight, Standard and Loose alike.
    solid = _profile_loft(
        [cavity.buffer(t - fit) for t, _ in profile],
        [z for _, z in profile],
    )
    # The buried root of the chamfer dips below the skirt; keep the bump on the band.
    return _clip_lid_locks(solid, eff, profile, floor=rim - STACK_SKIRT_DEPTH)


def _lid_lock_notches(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Matching discrete recesses in the body wall."""
    profile = _lid_lock_profile(
        LID_LOCK_INTERFERENCE,
        eff.z,
        clearance=LID_LOCK_CLEARANCE,
    )
    cavity = wavy_cavity_polygon(eff)
    solid = _profile_loft(
        [cavity.buffer(t) for t, _ in profile],
        [z for _, z in profile],
    )
    return _clip_lid_locks(solid, eff, profile)


# --------------------------------------------------------------------------- #
# body features
# --------------------------------------------------------------------------- #
def stack_body_cutters(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """Solids subtracted from the bin body: base step and retention recesses.

    ``eff`` must already be the effective box - these are cut at its rim.
    """
    if not vertical_stack_enabled(eff) and not lid_enabled(eff):
        return []
    cutters: list[trimesh.Trimesh] = []
    if vertical_stack_enabled(eff):
        step = stack_step_depth(eff)
        # The insertion zone stays completely inside the receiver.  Only above
        # its seating datum does the outside grow back to full size.
        outer = wavy_outer_polygon(eff)
        if direct_stack_enabled(eff):
            shell = _extrude_polygon(outer, step + _PROFILE_EPS)
            keep = _skirt_keep(eff)
        else:
            flare = stack_foot_flare_height(eff)
            # Extend beyond the true outline: the resampled loft can otherwise
            # leave a detached sliver where it meets the outside wall.
            shell = _extrude_polygon(outer.buffer(_PROFILE_EPS), step + flare + 2.0 * _PROFILE_EPS)
            plug = _plug_polygon(eff)
            keep = _profile_loft(
                [plug, plug, outer, outer],
                [-2.0 * _PROFILE_EPS, step, step + flare, step + flare + 2.0 * _PROFILE_EPS],
            )
        shell.apply_translation((0.0, 0.0, -_PROFILE_EPS))
        cutters.append(difference([shell, keep]))

    if lid_enabled(eff):
        # A flip lid carries no lock bumps (see make_lid_parts), so no notches.
        if not lid_has_flip(eff):
            cutters.extend(_lid_lock_notches(eff))
        else:
            # The flip lid's knuckles swing in room cut from the back wall top,
            # and the pin bore runs out through both side walls.
            hinge = _lid_hinge(eff)
            if hinge is not None:
                cutters.extend(body_hinge_cutters(hinge))
    return cutters


def stack_body_adders(eff: BoxSpec) -> list[trimesh.Trimesh]:
    """What the body gains: a flip lid's knuckles."""
    hinge = _lid_hinge(eff)
    if hinge is not None:
        rail = union(body_hinge_parts(hinge, wavy_cavity_polygon(eff),
                                      wavy_outer_polygon(eff), eff.base_thickness))
        # A hinged lid never receives a stack, so the rail has no seat to
        # clear. Carry the roots into the wall, then restore the pin bore.
        # Exact contact with the cut wall can disconnect a ledge.
        root = rail.copy()
        root.apply_translation((0.0, 0.0, -0.05))
        rail = difference([union([rail, root]), body_hinge_cutters(hinge)[-1]])
        return [rail]
    return []


# --------------------------------------------------------------------------- #
# the lid
# --------------------------------------------------------------------------- #
def _lid_handle_mesh(box: BoxSpec) -> trimesh.Trimesh:
    """The one resolved handle for this lid, lid-top plane at ``z = 0``."""
    spec = lid_spec(box)
    eff = stack_effective_box(box)
    # A flip lid's plate stops short of the hinge strip; size and place the
    # handle on the plate that is actually there.
    outer = _lid_top_polygon(eff, _lid_hinge(eff))
    return resolve_lid_handle(outer.bounds, spec.handle_type, spec.handle_size,
                              spec.handle_position)


def _lid_has_lettering(spec) -> bool:
    return bool(str(spec.label_text or "").strip()
                or any(str(value or "").strip() for value in spec.division_labels))


def lid_handle_height(box: BoxSpec) -> float:
    """Height of the handle above the lid top - read from the real mesh."""
    if not lid_has_handle(box):
        return 0.0
    return handle_height(_lid_handle_mesh(box))


def lid_label_height(box: BoxSpec) -> float:
    """Height Raised lid lettering stands above the lid top (0 when none)."""
    spec = lid_spec(box)
    if not (spec.enabled and spec.label_enabled
            and spec.label_style == "raised" and _lid_has_lettering(spec)):
        return 0.0
    return lid_label_relief_mm(spec)


def lid_above_top_height(box: BoxSpec) -> float:
    """Tallest thing standing above the lid top: handle or Raised lettering."""
    return max(lid_handle_height(box), lid_label_height(box))


def _lid_handle_keepout(box: BoxSpec) -> tuple[float, float, float, float]:
    """XY rectangle labels must stay out of, from the real handle mesh."""
    return handle_keepout(_lid_handle_mesh(box))


def _regions_avoiding_handle(
    box: BoxSpec,
    regions: list[tuple[str, tuple[float, float, float, float]]],
) -> list[tuple[str, tuple[float, float, float, float]]]:
    if not lid_has_handle(box):
        return regions
    hx0, hy0, hx1, hy1 = _lid_handle_keepout(box)
    safe: list[tuple[str, tuple[float, float, float, float]]] = []
    for text, (x0, y0, x1, y1) in regions:
        if hx1 <= x0 or hx0 >= x1 or hy1 <= y0 or hy0 >= y1:
            safe.append((text, (x0, y0, x1, y1)))
            continue
        candidates = [
            (x0, y0, min(x1, hx0), y1),
            (max(x0, hx1), y0, x1, y1),
            (x0, y0, x1, min(y1, hy0)),
            (x0, max(y0, hy1), x1, y1),
        ]
        legal = [region for region in candidates if
                 region[2] - region[0] > 2.0 * LID_LABEL_MARGIN and
                 region[3] - region[1] > 2.0 * LID_LABEL_MARGIN]
        if not legal:
            raise ValueError(f"lid label '{text}' has no space beside the handle")
        best = max(legal, key=lambda region: (region[2] - region[0]) * (region[3] - region[1]))
        safe.append((text, best))
    return safe


def lid_label_backing(box: BoxSpec) -> float:
    """Lid material under an inlaid label's surface before the pocket is cut.

    A label on a lid that does not receive a stack sits on the lid top; on a
    rimmed lid it sits on the plate inside the rim.
    """
    return stack_lid_rise(box) - (STACK_SEAT_DEPTH if lid_receives_stack(box) else 0.0)


def _lid_text_parts(
    box: BoxSpec,
    top_z: float,
    regions: list[tuple[str, tuple[float, float, float, float]]],
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    spec = lid_spec(box)
    if not spec.label_enabled:
        return []
    raised = spec.label_style == "raised"
    depth = lid_label_relief_mm(spec)
    if not raised and lid_label_backing(box) - depth < LID_LABEL_MIN_BACKING - _EPS:
        raise ValueError(
            f"a {depth:g} mm Inlay depth would leave only "
            f"{max(0.0, lid_label_backing(box) - depth):.1f} mm under the lid label; "
            "choose a shallower depth or a thicker lid"
        )
    parts: list[tuple[str, trimesh.Trimesh, bool]] = []
    for text, (x0, y0, x1, y1) in regions:
        text = str(text or "").strip()
        if not text:
            continue
        avail_x = max(0.0, x1 - x0 - 2.0 * LID_LABEL_MARGIN)
        avail_y = max(0.0, y1 - y0 - 2.0 * LID_LABEL_MARGIN)
        probe = text_outline(text, 10.0)
        if spec.label_orientation == "vertical":
            from shapely import affinity
            probe = affinity.rotate(probe, 90.0, origin=(0.0, 0.0))
        bx0, by0, bx1, by1 = probe.bounds
        scale = min(avail_x / max(bx1 - bx0, _EPS), avail_y / max(by1 - by0, _EPS))
        # A fixed letter height by name; only the lid's own fit may make it smaller.
        cap = min(LID_LABEL_SIZE_CAP_MM[spec.label_size], 10.0 * scale)
        if cap < LID_LABEL_MIN_CAP:
            raise ValueError(f"lid label '{text}' cannot fit this compartment")
        outline = text_outline(text, cap)
        from shapely import affinity
        if spec.label_orientation == "vertical":
            outline = affinity.rotate(outline, 90.0, origin=(0.0, 0.0))
        outline = affinity.translate(outline, xoff=(x0 + x1) / 2.0, yoff=(y0 + y1) / 2.0)
        parts.append((text, text_prism(outline, top_z, depth=depth, raised=raised), raised))
    return parts


def _lid_stack_rim(eff: BoxSpec) -> trimesh.Trimesh:
    """The rim a resting lid carries: a ring on the plate top around the seat.

    Its inside is the mouth outline, so the skirt of the bin above drops in with
    the direct-foot fit; the bin's wall bottom bears on the rim top.
    """
    inner = _plug_polygon(eff).buffer(STACK_FIT)
    ring = inner.buffer(STACK_LID_RIM_WIDTH).intersection(wavy_outer_polygon(eff)).difference(inner)
    rim = _extrude_polygon(ring, STACK_SEAT_DEPTH + 0.2)       # 0.2 mm into the plate: one solid
    rim.apply_translation((0.0, 0.0, eff.z + stack_lid_rise(eff) - STACK_SEAT_DEPTH - 0.2))
    return rim


def make_lid_parts(
    box: BoxSpec,
    label_regions: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> tuple[trimesh.Trimesh, list[tuple[str, trimesh.Trimesh, bool]]]:
    """Build an ordinary-bin lid and its optional separate label objects."""
    eff = stack_effective_box(box)
    if not lid_enabled(eff):
        raise ValueError("this bin has no lid")

    rim = eff.z
    rise = stack_lid_rise(eff)
    # Flip lid only: the resolved hinge.  Its plate stops at the hinge strip and
    # it has no underside plug; without a hinge nothing below changes.
    hinge = _lid_hinge(eff)
    outer = wavy_outer_polygon(eff) if hinge is not None else _lid_top_polygon(eff, hinge)

    # Flush seat: the plate is the bin full outer outline from the rim up, so
    # its underside bears on the whole rim top and the exterior meets the wall
    # with no step.  The plug below it keeps its own running clearance, and the
    # lid lock bumps keep their own interference, both independent of the
    # plate.  Nothing here is a preview-only offset.
    # A flip plate is cleared behind the hinge pin and over each bin knuckle.
    # It has no lock bumps to resist the swing.
    plate = _extrude_polygon(outer, rise)
    plate.apply_translation((0.0, 0.0, rim))
    if hinge is not None:
        plate = difference([plate, plate_hinge_cutter(hinge, eff.half_x)])

    parts = [plate]
    if hinge is None:
        parts.append(_lid_skirt(eff, rim))

    bumps = [] if hinge is not None else _lid_lock_bumps(eff, rim)
    from organizer_features.lid_snap import snap_fingers
    lid = union([*parts, *bumps, *snap_fingers(eff), *_lid_alignment_tabs(eff, rim)])

    if lid_receives_stack(eff):
        # Rim the bin stacked on this one sits into. It keeps the direct-foot
        # fit, whatever the lid own plug fit is.
        lid = union([lid, _lid_stack_rim(eff)])
    elif lid_has_handle(eff):
        handle = _lid_handle_mesh(eff)
        handle.apply_translation((0.0, 0.0, rim + rise))
        lid = union([lid, handle])

    if hinge is not None:
        # Lid knuckles sit in the back-top corner, flush with the back face and
        # the lid top.
        lid = union([lid, *lid_hinge_parts(hinge, wavy_outer_polygon(eff))])

    regions = label_regions or []
    if lid_spec(eff).label_enabled and not regions:
        safe = _plug_polygon(eff) if lid_receives_stack(eff) else _lid_top_polygon(eff, hinge)
        regions = [(lid_spec(eff).label_text, tuple(float(v) for v in safe.bounds))]
    if hinge is not None:
        # Divider-provided label regions must also end on the moving plate.
        regions = [(text, (x0, y0, x1, min(y1, hinge.plate_back_y)))
                   for text, (x0, y0, x1, y1) in regions]
    regions = _regions_avoiding_handle(eff, regions)
    label_surface = rim + rise - (STACK_SEAT_DEPTH if lid_receives_stack(eff) else 0.0)
    labels = _lid_text_parts(eff, label_surface, regions)
    sunk = [mesh for _text, mesh, raised in labels if not raised]
    if sunk:
        lid = difference([lid, union(sunk) if len(sunk) > 1 else sunk[0]])
    if hinge is not None:
        # The plate's underside reaches into the top of the pin channel on a
        # thick lid; bore the assembled lid so the channel is clear end to end.
        lid = difference([lid, body_hinge_cutters(hinge)[-1]])
    lid.remove_unreferenced_vertices()
    return lid, labels


def make_stack_lid(box: BoxSpec) -> trimesh.Trimesh:
    """Compatibility wrapper for the former stack-lid-only builder."""
    return make_lid_parts(box)[0]


def lid_thickness_options(box: BoxSpec) -> dict[str, float]:
    """The plate thickness in mm of every lid thickness choice."""
    if not lid_enabled(box):
        return {}
    return {name: float(name) for name in LID_THICKNESSES}


def stack_closed_height(box: BoxSpec) -> float:
    """Detached physical envelope, including the interlocking foot depth and
    the tallest thing above the lid (handle or Raised lettering)."""
    return stack_effective_box(box).z + stack_lid_rise(box) + lid_above_top_height(box)


def stack_module_height(box: BoxSpec) -> float:
    """Contribution between consecutive stack seating datums.

    A direct bin's skirt and a lid bin's foot overlap the bin below (the
    skirt into its mouth or into its lid's stack seat), so each adds its
    typed height less that engagement depth.
    """
    return box.z - stack_step_depth(box)


def stack_pitch(box: BoxSpec) -> float:
    """Height one more bin adds to a stack: exactly the module height."""
    return stack_module_height(box)


def _flip_summary(eff: BoxSpec) -> dict | None:
    """Readout of the resolved hinge (None for a loose lid)."""
    try:
        hinge = _lid_hinge(eff)
    except ValueError:
        return None        # generation names the problem; the readout just omits it
    if hinge is None:
        return None
    return {
        "pin_diameter_mm": HINGE_PIN_DIAMETER,
        "channel_diameter_mm": round(2.0 * HINGE_BORE_RADIUS, 3),
        "knuckle_diameter_mm": round(2.0 * HINGE_BARREL_RADIUS, 3),
        "knuckles": len(hinge.knuckles),
        "span_mm": round(2.0 * hinge.span_half, 3),
        "interior_strip_mm": round(hinge.strip_mm, 3),
        "axis_below_rim_mm": round(hinge.axis_depth, 3),
        "open_angle_deg": round(hinge.open_angle_deg, 1),
    }


def stack_summary(box: BoxSpec) -> dict:
    """Readout for the preview panel and the generation result."""
    spec = stack_spec(box)
    eff = stack_effective_box(box)
    parts = ["Bin"] + (["Lid"] if lid_enabled(box) else [])
    summary = {
        "mode": spec.mode,
        "lid_receives_stack": lid_receives_stack(box),
        "enabled": vertical_stack_enabled(box),
        "module_height_mm": round(stack_module_height(box), 3),
        "closed_height_mm": round(stack_closed_height(box), 3),
        "pitch_mm": round(stack_pitch(box), 3),
        "engagement_mm": round(stack_step_depth(box), 3),
        "body_z_mm": round(eff.z, 3),
        "lid_rise_mm": round(stack_lid_rise(box), 3),
        "lid_thickness_mm": lid_thickness_options(box),
        "lid_label_backing_mm": (
            round(lid_label_backing(eff), 3) if lid_enabled(box) else None
        ),
        "lid_label_min_backing_mm": LID_LABEL_MIN_BACKING,
        "lid_fit_mm": round(lid_fit_mm(box), 3) if lid_enabled(box) else None,
        "lid_above_top_mm": round(lid_above_top_height(box), 3),
        "wall_mm": round(eff.wall, 3),
        "wall_raised": eff.wall > box.wall + _EPS,
        "base_mm": round(eff.base_thickness, 3),
        "base_raised": eff.base_thickness > box.base_thickness + _EPS,
        "parts": parts,
    }
    if lid_has_flip(box):
        summary["lid_flip"] = True
        summary["lid_flip_hinge"] = _flip_summary(eff)
    if lid_enabled(box) and lid_spec(eff).snap_enabled:
        from organizer_features.lid_snap import snap_status, snap_fingers
        summary["lid_snap_note"] = snap_status(eff) or (
            None if snap_fingers(eff) else "No reachable connector ridges; snap fit adds nothing on this bin.")
    return summary


def validate_stack_design(box: BoxSpec) -> None:
    """Actionable checks, raised before anything is built."""
    spec = stack_spec(box)
    if not vertical_stack_enabled(box) and not lid_enabled(box):
        return
    if getattr(getattr(box, "b4b", None), "enabled", False):
        raise ValueError(
            "a Storage Box already stacks on its own - turn Storage Box stacking on "
            "instead"
        )
    # Checked against the request, before the effective box is built: below
    # this the shortened body fails BoxSpec's own lock-bump minimum, and the
    # user would get told about lock bumps on a bin they never made short.
    if vertical_stack_enabled(box):
        floor = stack_base_minimum(box)
        minimum = (floor - stack_foot_growth(box)) + MIN_HEIGHT_ABOVE_BASE + stack_lid_rise(box)
        if box.z < minimum - _EPS:
            raise ValueError(
                f"a stackable bin needs at least {minimum:g} mm of height - "
                f"the {'skirt' if direct_stack_enabled(box) else 'foot'} and its "
                f"floor take up the bottom {floor:g} mm"
            )
    elif lid_enabled(box):
        minimum = box.base_thickness + MIN_HEIGHT_ABOVE_BASE + stack_lid_rise(box)
        if box.z < minimum - _EPS:
            raise ValueError(
                f"a bin with a lid needs at least {minimum:g} mm of total height - "
                f"the lid takes the top {stack_lid_rise(box):g} mm and the floor "
                f"the bottom {box.base_thickness:g} mm"
            )
    eff = stack_effective_box(box)
    if lid_enabled(box):
        if lid_receives_stack(box) and stack_lid_rise(eff) - STACK_SEAT_DEPTH < STACK_MIN_FLOOR_SKIN - _EPS:
            raise ValueError("the lid plate is too thin to carry its stack rim")
        if lid_has_flip(box):
            _lid_hinge(eff)        # raises if the bin is too small to hinge
        else:
            bump_profile = _lid_lock_profile(
                lid_fit_mm(eff) + LID_LOCK_INTERFERENCE, eff.z,
            )
            # Only the part standing proud of the skirt (t >= 0) must sit on it.
            if min(z for t, z in bump_profile if t >= 0.0) < eff.z - STACK_SKIRT_DEPTH - _EPS:
                raise ValueError("the stacking lid plug is too short for its lock points")
        if lid_has_handle(box):
            _lid_handle_mesh(box)         # raises if the chosen handle cannot fit
        spec = lid_spec(box)
        if spec.label_enabled and spec.label_style != "raised":
            depth = lid_label_relief_mm(spec)
            if lid_label_backing(eff) - depth < LID_LABEL_MIN_BACKING - _EPS:
                raise ValueError(
                    f"a {depth:g} mm Inlay depth would leave only "
                    f"{max(0.0, lid_label_backing(eff) - depth):.1f} mm under the lid label; "
                    "choose a shallower depth or a thicker lid"
                )
    elif direct_stack_enabled(box):
        _skirt_polygon(eff)
        return
    _plug_polygon(eff)
