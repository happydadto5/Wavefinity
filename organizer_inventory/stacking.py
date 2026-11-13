"""Storage Box Gridfinity stacking: eligibility, geometry and nominal datums.

S2-00 sections 4-6 govern this separate option; printed fit is unverified.
The body datum remains zero. Feet extend down; the ridge extends up from
the unchanged lid top. No ordinary-bin height normalisation applies.
"""

from __future__ import annotations

import math


def validate_grid_stacking(settings, x=None, y=None, z=None) -> None:
    """Refuse unsupported requests without changing the user's choices."""
    if not settings.get("grid_stacking", False):
        return
    from organizer_engine._specs import GRID_PITCHES

    grid = settings.get("grid", "wavefinity")
    if grid not in ("gridfinity", "gridfinity_half"):
        raise ValueError("Grid stacking needs a 21 mm or 42 mm Gridfinity Storage Box.")
    if not settings.get("lid", True):
        raise ValueError("Grid stacking needs a lid with a receiving grid.")
    if settings.get("stacking", False):
        raise ValueError("Grid stacking cannot be combined with the Wavefinity stacking recess and pegs. Turn one off.")
    if settings.get("label_location", "top") == "top":
        raise ValueError("Grid stacking cannot use a lid-top label. Choose Front or No label.")
    secure = settings.get("secure_lid", True)
    if secure and settings.get("hinge_type", "screw") != "screw":
        raise ValueError("Grid stacking is unavailable with a piano hinge. Choose screw hinges or Lid only.")
    if secure and str(settings.get("latch_count", "1")) not in ("1", "2"):
        raise ValueError("Grid stacking with a latched lid needs one or two latches. Choose a latch count or Lid only.")
    if secure and str(settings.get("hinge_count", "2")) not in ("1", "2"):
        raise ValueError("Grid stacking with a latched lid needs one or two screw hinges.")
    headroom = settings.get("lid_headroom_mm", 1.0)
    if not any(math.isclose(headroom, value, abs_tol=1e-6) for value in (0.5, 1.0, 2.0)):
        raise ValueError("Grid stacking needs lid head-room of 0.5, 1.0 or 2.0 mm.")
    if x is not None and y is not None:
        from organizer_features.gridfinity import floor_cell_counts

        counts = floor_cell_counts(grid, x, y)
        minimum = (2 if grid == "gridfinity" else 3) if secure else 1
        if min(counts) < minimum:
            pitch = GRID_PITCHES[grid]
            raise ValueError(f"Grid stacking with this lid needs at least {minimum} by {minimum} cells at {pitch:g} mm pitch. Use Lid only for a smaller box.")
    from organizer_engine.product_rules import B4B_LATCHED_MIN_HEIGHT
    if secure and z is not None and z < B4B_LATCHED_MIN_HEIGHT:
        raise ValueError("Grid stacking with a latched lid needs at least 16 mm of interior height.")


def validate_box(box) -> None:
    if not box.b4b.grid_stacking:
        return
    from dataclasses import asdict
    from organizer_engine._specs import B4B_LATCH_TWO_ABOVE_FIELD_X

    settings = asdict(box.b4b)
    if settings["latch_count"] == "auto":
        settings["latch_count"] = "2" if box.x > B4B_LATCH_TWO_ABOVE_FIELD_X else "1"
    validate_grid_stacking(settings, box.x, box.y, box.z)


def stacking_feet(box):
    """Pitch-centred standard feet below the existing body, with a fuse cap."""
    from organizer_features.gridfinity import FOOT_HEIGHT, foot_solid

    validate_box(box)
    feet = foot_solid(box, box.b4b.grid)
    feet.apply_translation((0.0, 0.0, -FOOT_HEIGHT))
    return feet


def stacking_ridge(box):
    """Perimeter only, wholly on the lid flat; cut the ridge, never the lid."""
    from organizer_b4b._layout import (
        b4b_effective_box, b4b_layout, b4b_lid_skin_from_eff, b4b_lid_underside_z,
    )
    from organizer_engine._specs import B4B_EDGE_BEVEL_MM
    from organizer_features.gridfinity import rim_depth, rim_mouth_polygon, rim_socket_cutter
    from organizer_geometry import _extrude_polygon, difference

    validate_box(box)
    eff = b4b_effective_box(box)
    grid = eff.b4b.grid
    top = b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff)
    chamfer = min(B4B_EDGE_BEVEL_MM[eff.b4b.edge_bevel], b4b_lid_skin_from_eff(eff) / 2.0)
    # U10: an extra 0.10 mm inside the chamfer's inner boundary. This also
    # excludes every ear arm behind the crest, including the hinge X-bands.
    outline = b4b_layout(box).outer_structural_polygon.buffer(-chamfer - 0.1)
    band = outline.difference(rim_mouth_polygon(eff, grid))
    if band.is_empty or band.geom_type != "Polygon":
        raise ValueError("The lid flat cannot hold a continuous grid ridge. Increase the wall thickness or reduce the edge bevel.")
    # Only this addition overlaps the plate by 0.10 mm to fuse. The socket
    # cutter acts on the addition in isolation, leaving the plate untouched.
    ridge = _extrude_polygon(band, rim_depth(grid) + 0.1)
    ridge.apply_translation((0.0, 0.0, top - 0.1))
    return difference([ridge, rim_socket_cutter(eff, grid, top)])


def stacking_record(box, plan) -> dict:
    """S2-00 model M1/M2; dimensions are nominal, never evidence of fit."""
    from organizer_b4b._layout import b4b_effective_box, b4b_lid_skin_from_eff, b4b_lid_underside_z
    from organizer_features.gridfinity import FOOT_HEIGHT, SEAT_DESCENT, rim_depth

    eff = b4b_effective_box(box)
    grid = eff.b4b.grid
    r, f, d = rim_depth(grid), FOOT_HEIGHT, SEAT_DESCENT[grid]
    h0 = b4b_lid_underside_z(box) + b4b_lid_skin_from_eff(eff)
    hf, hr = f + h0, f + h0 + r
    record = {
        "fit_status": "unverified",
        "foot_height_mm": f, "ridge_height_mm": r, "seat_descent_mm": d,
        "closed_without_grid_mm": h0, "closed_with_feet_mm": hf,
        "closed_with_grid_mm": hr,
        "two_boxes_upper_without_ridge_mm": hr + hf - d,
        "two_boxes_upper_with_ridge_mm": 2.0 * hr - d,
        "shell_gap_above_ridge_mm": f - d,
        "shell_gap_above_hardware_mm": r + f - d,
        "open_only_when_unoccupied": True,
        "mating_rule": "Keep the upper cell field inside the lower field and align pitch centres; odd cell-count differences need a half-pitch offset.",
    }
    if eff.b4b.secure_lid:
        s = plan.hinge_axis_y - plan.hinge_rear_crest
        record["open_lid_rear_reach_mm"] = s + math.hypot(s, plan.profile.pivot_radius + r)
    return record
