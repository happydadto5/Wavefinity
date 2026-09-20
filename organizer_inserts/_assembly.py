"""Feature building, insert assembly, text coordination, and reports."""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

import trimesh
from shapely.geometry import Polygon, box as shapely_box

from organizer_geometry import _extrude_polygon, difference, intersection, union

from organizer_engine import (
    BoxSpec,
    LOCK_PROTRUSION,
    _rounded,
    flat_cavity_polygon,
    label_placement,
    lid_enabled,
    top_label_surface_z,
    wavy_cavity_polygon,
)

from ._core import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    INSERT_CLEARANCE,
    Feature,
    Zone,
    cartridge_zone,
    connector_keep_out,
    layout_zone,
)
from ._layout import _feature_reach, check_layout, feature_footprint
from ._registry import FEATURE_BUILDERS
from ._text import (
    _oriented_text,
    build_text,
    is_text,
    text_is_raised,
    text_of,
    text_placed_outline,
)
from ._divider import divider_division_texts
from ._nest import build_recessed_nest_group, resolve_nest_settings

# Physical assembly policy, not a user-facing capability: only these feature
# kinds may legitimately rise above the bin rim, and only when fused directly
# into the bin with no stacking interface or lid to collide with. A shallow
# vanity-style bin still needs its wall height to mean wall height - it is the
# *interior* geometry of these specific holders that is allowed to be taller.
_FUSED_ABOVE_RIM_KINDS = frozenset({
    "cradle",
    "bore",
    "post",
    "pocket",
    "slot",
    "steps",
})


def _allows_above_rim(one: Feature, mode: str) -> bool:
    if mode != "fused":
        return False
    if one.kind == "nest":
        return (
            one.contour is not None
            and str(one.options.get("holder_style", "raised_wall")).lower()
                == "raised_wall"
        )
    return one.kind in _FUSED_ABOVE_RIM_KINDS


def _nest_recessed_deck_footprint(box: BoxSpec, mode: str) -> Polygon:
    """Physical area a Recessed Photo Nest deck should fill."""
    if mode == "fused":
        return (
            flat_cavity_polygon(box)
            if box.flat_inside > 0.0
            else wavy_cavity_polygon(box)
        )
    if mode == "separate":
        return insert_footprint(box, "separate")
    if mode == "cartridge":
        return insert_footprint(box, "cartridge")
    raise ValueError(f"unknown layout mode {mode!r}")


def build_features(
    box: BoxSpec, features: Iterable[Feature], base_z: float,
    bounds: Zone | None = None, mode: str = "fused",
    include_text: bool = False,
) -> list[trimesh.Trimesh]:
    """Every holder's solids, ready to be added to the body.

    Text is built too - so a bad one reports its error alongside every other
    feature's - but left out of the returned solids unless ``include_text`` is
    set, because a recessed text has to be subtracted from the body rather
    than added to it. The exporter collects it through :func:`build_texts`;
    the preview asks for it here so it can draw it in place.
    """
    from organizer_stack import STACK_PLUG_DEPTH, stack_enabled

    features = list(features)
    check_layout(box, features, bounds, base_z, mode)
    max_feature_z = box.z
    if stack_enabled(box):
        max_feature_z = box.z - STACK_PLUG_DEPTH
    solids: list[trimesh.Trimesh] = []
    recessed_nests = [
        one for one in features
        if one.kind == "nest" and one.contour
        and str(resolve_nest_settings(box, one, base_z)["holder_style"]) == "recessed"
    ]
    if recessed_nests:
        shared_deck = _nest_recessed_deck_footprint(box, mode)
        made = [build_recessed_nest_group(box, recessed_nests, base_z, shared_deck)]
        # A shared deck deliberately spans the physical insert/bin footprint,
        # not any one Nest zone.
        solids.extend(made)
    for one in features:
        if one in recessed_nests:
            continue
        recessed_deck_footprint = None

        if (
            one.kind == "nest"
            and one.contour
            and one.options.get("holder_style") == "recessed"
        ):
            recessed_deck_footprint = _nest_recessed_deck_footprint(box, mode)
            made = FEATURE_BUILDERS[one.kind](
                box,
                one,
                base_z,
                deck_footprint=recessed_deck_footprint,
            )
        else:
            made = FEATURE_BUILDERS[one.kind](box, one, base_z)

        reach = _feature_reach(box, one, base_z)

        if recessed_deck_footprint is not None:
            x0, y0, x1, y1 = recessed_deck_footprint.bounds
            epsilon = 0.01
            reach = Zone(
                float(x0) - epsilon,
                float(y0) - epsilon,
                float(x1) + epsilon,
                float(y1) + epsilon,
            )
        for solid in made:
            if (
                solid.bounds[0][0] < reach.x0 - 1e-5
                or solid.bounds[1][0] > reach.x1 + 1e-5
                or solid.bounds[0][1] < reach.y0 - 1e-5
                or solid.bounds[1][1] > reach.y1 + 1e-5
            ):
                raise ValueError(
                    f"a {one.kind} exceeds its layout zone; reduce its size "
                    "or thickness option"
                )
        for solid in made:
            top = solid.bounds[1][2]
            if stack_enabled(box):
                if top > max_feature_z + 1e-6:
                    raise ValueError(
                        f"a {one.kind} rises into the stacking interface; keep "
                        f"interior parts below {max_feature_z:.1f} mm, reduce its "
                        "height, or make the bin taller"
                    )
            elif lid_enabled(box):
                if top > box.z + 1e-6:
                    raise ValueError(
                        f"a {one.kind} rises above the bin rim and conflicts with "
                        "the lid; reduce its height, remove the lid, or make the "
                        "bin taller"
                    )
            elif top > box.z + 1e-6 and not _allows_above_rim(one, mode):
                raise ValueError(
                    f"a {one.kind} rises above the bin rim; reduce its height "
                    "or make the bin taller"
                )
        whole = Zone.whole(box)
        touches_wall = (
            one.zone.x0 <= whole.x0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.x1 >= whole.x1 - CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y0 <= whole.y0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y1 >= whole.y1 - CONNECTOR_EDGE_KEEP_OUT
        )
        # A Divider's rim-label shelf follows the same near-rim clearance as a
        # Text shelf. It may enter the connector band, but never the stack/lid
        # plug space; ordinary wall-touching features keep the connector rule.
        divider_rim_shelf = (
            one.kind == "divider"
            and str(one.options.get("division_level", "base")).lower() == "rim"
        )
        clears_stack_lid = all(
            solid.bounds[1][2] <= top_label_surface_z(box) + 1e-6
            for solid in made
        )
        if (
            touches_wall
            and not (one.kind == "nest" and one.contour)
            # A full-height Auto Bore deliberately reaches the rim.
            and not (one.kind == "bore" and one.options.get("auto_height"))
            and any(solid.bounds[1][2] > connector_keep_out(box) + 1e-6 for solid in made)
            and not (divider_rim_shelf and clears_stack_lid)
        ):
            raise ValueError(
                f"a {one.kind} touching the wall must stay below "
                f"{connector_keep_out(box):.1f} mm so a connector can seat"
            )
        if is_text(one) and not include_text:
            continue
        solids.extend(made)
    return solids


def build_texts(
    box: BoxSpec, features: Iterable[Feature], base_z: float,
    limit: Polygon | None = None,
) -> list[tuple[str, trimesh.Trimesh, bool]]:
    """``(what it says, its solid, whether it stands proud)`` for each text part.

    The caller subtracts every recessed solid from the body to cut its pocket,
    leaves the raised ones alone, and writes all of them as their own objects.

    ``limit`` is the surface the lettering has to stay on - a removable
    insert's plate is pulled in from the wall, so text that would hang over
    its edge is refused here rather than quietly clipped mid-letter the way
    trimming a holder to the same outline safely can be.
    """
    made: list[tuple[str, trimesh.Trimesh, bool]] = []
    for one in features:
        if one.kind == "divider":
            for text_label, text_solid, raised in divider_division_texts(box, one, base_z):
                made.append((text_label, text_solid, raised))
            continue
        if not is_text(one) or one.options.get("level") == "rim":
            continue
        if limit is not None and not limit.covers(text_placed_outline(one)):
            raise ValueError(
                f"the text '{text_of(one)}' hangs over the edge of the insert "
                "plate; move it further from the wall"
            )
        made.append((text_of(one), build_text(box, one, base_z)[0],
                     text_is_raised(one)))
    return made


def resolve_text_features(
    box: BoxSpec,
    features: Iterable[Feature],
    reserved: Iterable[Polygon] = (),
    base_z: float = 0.0,
    mode: str = "fused",
) -> tuple[Feature, ...]:
    """Give every ``auto`` text part the best spot left on the floor.

    This is the "blank config just works" case the plain floor label always
    had: stay centred if you can, otherwise move beside whatever is in the
    way, then turn, then shrink. Everything else keeps the zone it was
    dragged to. Never raises - a text that cannot be placed keeps the zone it
    already had, so the ordinary validation reports it in the usual way.
    """
    features = tuple(features)
    auto = [
        index for index, one in enumerate(features)
        if is_text(one) and one.options.get("auto") and one.options.get("level") != "rim"
    ]
    if not auto:
        return features
    resolved = list(features)
    # Each auto text has to dodge the others too, so they are placed one at a
    # time and every one already placed becomes an obstacle for the next.
    obstacles = [polygon for polygon in reserved if not polygon.is_empty]
    obstacles += [
        feature_footprint(box, one, base_z).polygon
        for index, one in enumerate(features)
        if index not in auto
    ]
    for index in auto:
        one = resolved[index]
        label = text_of(one)
        if not label:
            continue
        try:
            placement = label_placement(box, label, obstacles)
            outline = _oriented_text(label, placement.cap_height,
                                     placement.quarter_turns)
            bx0, by0, bx1, by1 = outline.bounds
            zone = Zone(bx0 + placement.x, by0 + placement.y,
                        bx1 + placement.x, by1 + placement.y)
        except (ValueError, ZeroDivisionError):
            obstacles.append(one.zone.polygon)
            continue
        options = dict(one.options)
        options["quarter_turns"] = placement.quarter_turns
        # The zone is now exactly the ink, so re-fitting into it lands back on
        # the cap height the search chose; leave the field free to say so.
        options.pop("cap_height", None)
        if mode == "cartridge":
            # A cartridge layout only accepts whole 8 mm cells and the ink
            # never lands on one, so grow the zone *outward* to the cells
            # around it - snapping to the nearest would cut the lettering off.
            # Pin the height the search chose so the bigger box does not
            # quietly enlarge the lettering to fill it either.
            cells = cartridge_zone(box)
            low_x = cells.x0 + math.floor((zone.x0 - cells.x0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            low_y = cells.y0 + math.floor((zone.y0 - cells.y0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            high_x = cells.x0 + math.ceil((zone.x1 - cells.x0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            high_y = cells.y0 + math.ceil((zone.y1 - cells.y0) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            if (low_x < cells.x0 - 1e-9 or low_y < cells.y0 - 1e-9
                    or high_x > cells.x1 + 1e-9 or high_y > cells.y1 + 1e-9):
                obstacles.append(one.zone.polygon)
                continue
            zone = Zone(low_x, low_y, high_x, high_y)
            options["cap_height"] = placement.cap_height
        resolved[index] = replace(one, zone=zone, options=options)
        obstacles.append(zone.polygon)
    return tuple(resolved)


def insert_footprint(box: BoxSpec, mode: str = "separate") -> Polygon:
    """The floor outline of a standalone insert.

    A removable insert follows the box's real cavity, including its waves, and
    is offset inward by ``INSERT_CLEARANCE`` so it can still slide in and out.
    A box with a flat lower wall band uses that lower profile because the plate
    sits inside the band.  Cartridge inserts retain their reusable rectangular
    cell footprint.

    Both removable modes pull in by ``INSERT_CLEARANCE + LOCK_PROTRUSION``: the
    lock bumps stand proud of the cavity line only in the upper wall band, so a
    removable part's passage has to clear their tips too, on top of its normal
    running clearance.
    """
    passage_clearance = INSERT_CLEARANCE + LOCK_PROTRUSION
    if mode == "separate":
        cavity = (
            flat_cavity_polygon(box)
            if box.flat_inside > 0.0
            else wavy_cavity_polygon(box)
        )
        footprint = cavity.buffer(-passage_clearance)
        if not isinstance(footprint, Polygon) or footprint.is_empty:
            raise ValueError("this bin is too small for a removable insert")
        return footprint
    bounds = layout_zone(box, mode)
    return _rounded(
        shapely_box(
            bounds.x0 + passage_clearance, bounds.y0 + passage_clearance,
            bounds.x1 - passage_clearance, bounds.y1 - passage_clearance,
        ),
        1.0,
    )


def make_insert_plate(box: BoxSpec, mode: str = "separate") -> trimesh.Trimesh:
    """The bare base plate of a standalone insert, sitting on z = 0."""
    return _extrude_polygon(insert_footprint(box, mode), BASE_PLATE)


def make_fitted_insert(
    box: BoxSpec, features: Iterable[Feature]
) -> trimesh.Trimesh:
    """A standalone insert that drops into this bin.

    It gets its own base plate and is pulled in by ``INSERT_CLEARANCE`` all
    round so it actually goes in, which is the cost of being able to lift it
    out and swap it.
    """
    footprint = insert_footprint(box, "separate")
    plate = make_insert_plate(box, "separate")
    # Validate and size holders at their installed height, then lower them by
    # the bin floor thickness so the removable insert still exports on z=0.
    parts = build_features(
        box, features, BASE_PLATE + box.base_thickness, mode="separate"
    )
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.base_thickness))
    body = union([plate] + parts) if parts else plate
    # A holder is built to its zone, which may run right out to the usable
    # rectangle - fine when fused to the box, but a standalone insert has to
    # clear the wall to go in at all. Trimming the assembled solid to the
    # plate's own footprint keeps that true for every holder, including any
    # added later.
    limit = _extrude_polygon(footprint, box.z * 2.0)
    return intersection([body, limit])


def make_cartridge_insert(
    box: BoxSpec, features: Iterable[Feature]
) -> trimesh.Trimesh:
    """Standalone insert on the optional centred 8 mm cartridge footprint."""
    bounds = cartridge_zone(box)
    footprint = insert_footprint(box, "cartridge")
    plate = make_insert_plate(box, "cartridge")
    parts = build_features(
        box, features, BASE_PLATE + box.base_thickness, bounds, "cartridge"
    )
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.base_thickness))
    body = union([plate] + parts) if parts else plate
    limit = _extrude_polygon(footprint, box.z * 2.0)
    return intersection([body, limit])


def make_fused_box(
    box: BoxSpec, features: Iterable[Feature], box_mesh: trimesh.Trimesh
) -> trimesh.Trimesh:
    """The bin with its holders grown straight out of the floor."""
    parts = build_features(box, features, box.base_thickness)
    if not parts:
        return box_mesh
    return union([box_mesh, *parts])


def apply_texts(
    body: trimesh.Trimesh,
    texts: Iterable[tuple[str, trimesh.Trimesh, bool]],
) -> trimesh.Trimesh:
    """Cut every recessed text's pocket out of ``body``.

    A raised text stands on the surface and takes nothing away, so it is left
    alone here and simply written as its own object beside the body.
    """
    sunk = [mesh for _label, mesh, raised in texts if not raised]
    if not sunk:
        return body
    pocketed = difference([body, union(sunk) if len(sunk) > 1 else sunk[0]])
    pocketed.remove_unreferenced_vertices()
    pocketed.merge_vertices()
    return pocketed


def insert_report(name: str, features: Iterable[Feature], mesh: trimesh.Trimesh) -> dict:
    features = list(features)
    return {
        "name": name,
        "features": len(features),
        "kinds": sorted({f.kind for f in features}),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "watertight": bool(mesh.is_watertight),
    }
