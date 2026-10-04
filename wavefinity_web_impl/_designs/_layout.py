"""Layout expansion, inventory preview and Space text payloads."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Any
from organizer_engine import BASE_UNIT, MAX_BOX_SIZE, MIN_BOX_SIZE, BoxSpec
from organizer_inserts import (
    EDITOR_SNAP,
    MIN_FEATURE_GAP,
    Feature,
    Zone,
    build_features,
    cradle_min_footprint,
    feature_min_footprint,
    fitted_nest_feature,
    layout_zone,
    normalize_bore_modes,
    moved_feature,
    occupied_zones,
    resized_feature,
    snapped_zone,
)
from organizer_drawer import stack_part_height
from organizer_inventory import configure_space_text
from organizer_app import (
    base_height,
    design_from_dict,
    design_to_dict,
    inventory_bin_record,
    object_height_plan,
    preview_geometry,
    validate_customization_clearance,
)
from organizer_pegboard import pegboard_layout_for_bin
from .._runtime import GEOMETRY_LOCK, _interior_work_box

from ._preview import _design, _is_base_trim_design, _reject_if_b4b
from ._features import _bore_required_bin_z


def expand_layout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    _reject_if_b4b(payload, "auto-expanding the layout")
    """Resize the bin - on the 8 mm grid, both axes - to the smallest size that
    fits every interior support at the footprint it actually needs, then trim
    back any axis that overshot. A cradle footprint is recomputed from its
    tool, and a bore / post / slot zone is grown (never shrunk) to hold the
    hole grid, peg row or slot bank it was given - so an explicit X/Y quantity
    that overflowed the drawn zone still makes the bin grow instead of erroring.
    Other supports keep the size the user drew. Supports that now overlap - a
    grown block crowding its neighbour - are slid apart along the floor: the
    ``payload["anchor"]`` part (the one just edited) holds still and the rest
    move outward from it, with the bin growing to take in whatever ends up past
    its edge. Nothing is re-sized to make room; only moved.

    The current size is always the floor: this operation only grows. A larger
    bin is valid user intent and is never silently tightened around its parts.

    ``payload["fit"] = True`` switches to a true smallest-fit search instead:
    the current X/Y are no longer a floor, and the bin may shrink as well as
    grow to the smallest legal footprint that still holds the layout. Z is
    never touched either way.
    """
    request_box, layout, label, part_name, label_location, scoop = design_from_dict(
        payload["design"], validate_layout=False
    )
    box = _interior_work_box(request_box)
    mode = layout.mode
    originals = list(layout.features)
    if not originals:
        raise ValueError("there are no interior supports to fit")
    # The part the user was editing when the fit gave out. It stays where it is
    # and the others move around it; without one, the biggest block anchors.
    anchor = payload.get("anchor")
    anchor = int(anchor) if anchor is not None and 0 <= int(anchor) < len(originals) else None
    fit = bool(payload.get("fit", False))

    if payload.get("fit_height_to_bore"):
        if anchor is None or originals[anchor].kind != "bore":
            raise ValueError("select a Bore before sizing the bin height")
        bore = originals[anchor]
        candidate_z = _bore_required_bin_z(request_box, box, mode, bore)
        max_height = payload.get("max_height")
        if max_height is not None and candidate_z > float(max_height) + 1e-9:
            raise ValueError(
                f"the Bore needs a {candidate_z:g} mm bin, above this Space's "
                f"{float(max_height):g} mm maximum height"
            )

        candidate_request = replace(request_box, z=candidate_z)
        candidate_design = design_to_dict(
            candidate_request, replace(layout, features=tuple(originals), mode=mode),
            label, part_name, label_location, scoop,
        )
        (validated_request, validated_layout, validated_label, validated_name,
         validated_location, validated_scoop) = _design(candidate_design)
        validated_box = _interior_work_box(validated_request)
        validate_customization_clearance(
            validated_box, validated_layout.features, validated_label,
            validated_location, validated_scoop, validated_layout.mode,
        )
        with GEOMETRY_LOCK:
            preview_geometry(
                validated_box, validated_label, validated_layout.features,
                validated_layout.mode, validated_location, validated_scoop,
            )
        canonical = design_to_dict(
            validated_request, validated_layout, validated_label,
            validated_name, validated_location, validated_scoop,
        )
        return {
            "design": canonical,
            "box": {
                "x": validated_request.x,
                "y": validated_request.y,
                "z": validated_request.z,
            },
            "grew": validated_request.z > request_box.z,
            "changed": validated_request.z != request_box.z,
        }

    def sized(one: Feature, trial: BoxSpec) -> Feature:
        if one.kind == "text":
            return one  # Text has no user-sized floor footprint.
        exact = False
        if one.kind == "bore":
            # A Bore's persisted sizing modes are re-resolved against each trial
            # bin: bore_to_bin follows the trial's usable floor exactly, and
            # bin_to_bore holds the Bore at its own minimum footprint.
            one = normalize_bore_modes(trial, one, base_height(trial, mode), mode)
            if one.options.get("xy_size_mode") == "bore_to_bin":
                return one
            exact = one.options.get("xy_size_mode") == "bin_to_bore"
        if one.kind == "nest" and one.contour:
            return fitted_nest_feature(one)
        if one.kind == "cradle" and one.item is not None:
            min_width, min_depth = cradle_min_footprint(one)
            if one.count is None:
                if one.along == "x":
                    width = min_width
                    depth = max(one.zone.depth, min_depth)
                else:
                    width = max(one.zone.width, min_width)
                    depth = min_depth
            else:
                width, depth = min_width, min_depth
        else:
            width, depth = one.zone.width, one.zone.depth
            grown = feature_min_footprint(trial, one, base_height(trial, mode))
            if grown is not None:
                # Round the grown footprint up to the editor grid, exactly as
                # "Fit to contents" does - otherwise the zone snap can leave it
                # a hair under what a leaned grid's reach needs.
                snap = layout.snap or EDITOR_SNAP
                grown = tuple(math.ceil(v / snap - 1e-6) * snap for v in grown)
                width, depth = (grown if exact else (max(width, grown[0]), max(depth, grown[1])))
                return resized_feature(one, trial, (width, depth), mode, layout.snap)
        cx, cy = one.zone.centre
        raw = Zone(cx - width / 2.0, cy - depth / 2.0,
                   cx + width / 2.0, cy + depth / 2.0)
        return replace(one, zone=snapped_zone(raw, trial, mode))

    def spread_apart(placed: list[Feature], trial: BoxSpec) -> list[Feature]:
        """Slide parts along the floor until none overlap, holding the anchor
        still and pushing the rest outward from it. Movement is clamped to the
        trial bin, so a size that cannot separate them just fails this trial and
        the search grows the bin one grid step and tries again."""
        if len(placed) < 2:
            return placed
        base_z = base_height(trial, mode)
        covered = lambda feat: occupied_zones(trial, [feat], base_z, mode)[0]
        zones = [covered(f) for f in placed]
        pivot = anchor
        if pivot is None:
            pivot = max(range(len(placed)),
                        key=lambda i: zones[i].width * zones[i].depth)
        ax, ay = zones[pivot].centre
        order = sorted((i for i in range(len(placed)) if i != pivot),
                       key=lambda i: (zones[i].centre[0] - ax) ** 2
                       + (zones[i].centre[1] - ay) ** 2)
        out = list(placed)
        settled = [pivot]
        def rim_text(one: Feature) -> bool:
            return one.kind == "text" and one.options.get("level") == "rim"
        for i in order:
            feat = out[i]
            if rim_text(feat):
                settled.append(i)
                continue
            for _ in range(80):
                here = covered(feat)
                clash = next((j for j in settled
                              if not rim_text(out[j])
                              and here.overlaps(covered(out[j]), MIN_FEATURE_GAP)),
                             None)
                if clash is None:
                    break
                if feat.kind == "text":
                    break  # A centered Text feature cannot be slid.
                other = covered(out[clash])
                # One editor grid step of slack on top of the bare overlap, so
                # the centre snap in ``moved_feature`` can't round it back into
                # a sub-gap touch and stall the loop.
                slack = (layout.snap or EDITOR_SNAP) + MIN_FEATURE_GAP
                over_x = min(here.x1, other.x1) - max(here.x0, other.x0) + slack
                over_y = min(here.y1, other.y1) - max(here.y0, other.y0) + slack
                cx, cy = here.centre
                if over_x <= over_y:
                    step = over_x if cx >= other.centre[0] else -over_x
                    moved = moved_feature(feat, trial, (cx + step, cy), mode, layout.snap)
                else:
                    step = over_y if cy >= other.centre[1] else -over_y
                    moved = moved_feature(feat, trial, (cx, cy + step), mode, layout.snap)
                if moved.zone.centre == feat.zone.centre:
                    break        # pinned against the bin wall - this trial is too small
                feat = moved
            out[i] = feat
            settled.append(i)
        return out

    def fits(x: float, y: float):
        try:
            trial = replace(box, x=float(x), y=float(y))
            placed = spread_apart(
                [sized(one, trial) for one in originals], trial
            )
            updated = replace(layout, features=tuple(placed), mode=mode)
            updated.validate(trial)
            validate_customization_clearance(
                trial, updated.features, label, label_location, scoop, mode
            )
        except ValueError:
            return None
        return trial, updated

    start_x, start_y = box.x, box.y
    ceiling = math.floor(MAX_BOX_SIZE / BASE_UNIT) * BASE_UNIT

    if fit:
        # Smallest legal footprint that fits the whole current layout: every
        # X/Y pair on the grid, tried in deterministic increasing order of
        # area, then max side, then side sum, then X, then Y.
        floor_units = int(round(MIN_BOX_SIZE / BASE_UNIT))
        ceiling_units = int(round(ceiling / BASE_UNIT))
        legal = [round(units * BASE_UNIT) for units in range(floor_units, ceiling_units + 1)]
        pairs = sorted(
            ((xv, yv) for xv in legal for yv in legal),
            key=lambda pair: (pair[0] * pair[1], max(pair), pair[0] + pair[1], pair[0], pair[1]),
        )
        x = y = None
        for xv, yv in pairs:
            if fits(xv, yv) is not None:
                x, y = xv, yv
                break
        if x is None:
            raise ValueError(
                "this layout will not fit within Wavefinity's maximum "
                f"{ceiling:g} mm bin size - remove or shrink a support"
            )
    else:
        floor_x, floor_y = start_x, start_y
        x, y = floor_x, floor_y
        result = fits(x, y)
        while result is None:
            x = round(x + BASE_UNIT)
            y = round(y + BASE_UNIT)
            if x > ceiling:
                raise ValueError(
                    "this layout will not fit within Wavefinity's maximum "
                    f"{ceiling:g} mm bin size - remove or shrink a support"
                )
            result = fits(x, y)

        # First fit found by growing both axes; give back any step that was not
        # actually needed (down to the floor).
        for _ in range(200):
            trimmed = False
            if x - BASE_UNIT >= floor_x and fits(x - BASE_UNIT, y) is not None:
                x = round(x - BASE_UNIT)
                trimmed = True
            if y - BASE_UNIT >= floor_y and fits(x, y - BASE_UNIT) is not None:
                y = round(y - BASE_UNIT)
                trimmed = True
            if not trimmed:
                break

    trial, updated = fits(x, y)
    with GEOMETRY_LOCK:
        build_features(
            trial, updated.features, base_height(trial, mode),
            layout_zone(trial, mode), mode,
        )
    # Growth here is X/Y only - the saved design keeps the requested module Z,
    # never the effective work box's printable Z.
    saved_box = replace(request_box, x=trial.x, y=trial.y)
    return {
        "design": design_to_dict(
            saved_box, updated, label, part_name, label_location, scoop,
        ),
        "box": {"x": saved_box.x, "y": saved_box.y, "z": saved_box.z},
        "grew": (trial.x > start_x or trial.y > start_y),
        "changed": (trial.x != start_x or trial.y != start_y),
    }


def inventory_preview_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """The planning record Space shows for the design being edited.

    Read-only: the same ``inventory_bin_record`` a generated bin would log, so
    Space sees the exact same x/y/z/kind/stack/wall envelope, but nothing is
    written, counted or claimed to exist as a file. Interior parts need not be
    generation-valid; only the container envelope matters here.
    """
    raw_design = payload["design"]
    if _is_base_trim_design(raw_design):
        raise ValueError("Base Trim is not a bin, so it has no place to plan in Space.")
    box, layout, label, part_name, _location, scoop = design_from_dict(
        raw_design, validate_layout=False,
    )
    with GEOMETRY_LOCK:
        record = inventory_bin_record(box, layout, None, label, part_name, scoop)
    record["file"] = ""
    plan = object_height_plan(raw_design, record.get("object_height_mm"))
    record["planning"] = {**plan, "physical_mm": stack_part_height(record),
                          "effective_mm": max(stack_part_height(record), plan["object_top_mm"] or 0.0)}
    return {"bin": record}


def pegboard_layouts_payload(payload: dict[str, Any]) -> dict[str, Any]:
    standard = payload.get("standard") or "standard"
    layouts: dict[str, Any] = {}
    for one in payload.get("bins") or []:
        if not isinstance(one, dict):
            continue
        key = str(one.get("id") or "")
        try:
            layouts[key] = pegboard_layout_for_bin(one, standard)
        except (TypeError, ValueError, KeyError) as error:
            layouts[key] = {"error": str(error), "compatible": False}
    return {"standard": standard, "layouts": layouts}


def create_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted equivalent of a genuinely new typed Space - never accepts
    legacy "box"; that only ever comes from configure_space_text_payload's
    migration path (see Fix 004 Correction 7.H)."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    for key in ("max_x_mm", "max_y_mm"):
        if key in payload:
            raw_def[key] = payload[key]
    for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
        if key in payload:
            raw_def[key] = payload[key]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="create",
    )


def configure_space_text_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Hosted Configure Existing / migration: never rejected merely because
    the browser-owned inventory text already carries a layout.space."""
    raw_def = {
        "name": payload.get("name"), "kind": payload.get("kind"),
        "x": payload.get("x"), "y": payload.get("y"), "z": payload.get("z"),
    }
    if "trim_size" in payload:
        raw_def["trim_size"] = payload["trim_size"]
    for key in ("max_x_mm", "max_y_mm"):
        if key in payload:
            raw_def[key] = payload[key]
    for key in ("pegboard_standard", "pegboard_size_mode", "pegboard_holes_x", "pegboard_holes_y", "storage_box", "storage_drawers"):
        if key in payload:
            raw_def[key] = payload[key]
    return configure_space_text(
        payload.get("inventory_text") or "",
        title=str(payload.get("inventory_title") or payload.get("name") or "Wavefinity"),
        raw_def=raw_def, mode="update", allow_legacy=True,
    )
