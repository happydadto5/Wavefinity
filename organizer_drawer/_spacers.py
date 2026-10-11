"""Wavefinity drawer spacer planning and spacer/connector file generation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable
from shapely import affinity
from shapely.geometry import Polygon, box as shape_box
from shapely.ops import unary_union
import trimesh
from organizer_app import connector_filename, generate_side_file
from organizer_engine import (
    LOCKED_CONNECTOR_LENGTH,
    BoxSpec,
    ConnectorSpec,
    differing_connector_plan,
    wavy_rect_outer,
)
from organizer_geometry import _extrude_polygon
from organizer_slicer import slicer_display_name

from ._core import (
    UNIT,
    MIN_EDGE_SPACER,
    MAX_SPACER_GAP,
    FLEX_PRELOAD_MM,
    FLEX_MIN_GAP_MM,
    FLEX_MIN_CONTACT_MM,
    RIGID_SPACER_CLEARANCE_MM,
    MIN_SPACER_HEIGHT,
    DEFAULT_SPACER_HEIGHT,
    SPACER_CONTACT_TARGET,
    SPACER_DISTRIBUTE_EVERY,
    SPACER_SELECTED_CAP,
    SPACER_KINDS,
    normalise_drawer,
    find_drawer,
    drawer_grid,
    _overlaps,
    _grid_items,
)
from ._report import drawer_report


# ---------------------------------------------------------------- spacers


def _exposed_segments(comp: list[dict[str, Any]], side: str) -> list[tuple[int, int, int]]:
    """Contiguous exposed boundary segments for one side of a connected
    component, in grid cells: ``(edge, start, end)`` - the component's own
    outer edge coordinate (x for "right", y for "back") and the
    perpendicular ``[start, end)`` cell range it spans.

    A row/column is only ever grouped with its neighbour when both share the
    exact same edge, so a candidate can never bridge across a step in an
    L-shaped or notched component - each genuinely separate run of the
    boundary becomes its own segment.
    """
    span: dict[int, int] = {}
    if side == "right":
        for item in comp:
            edge = item["gx"] + item["w"]
            for row in range(item["gy"], item["gy"] + item["d"]):
                span[row] = max(span.get(row, edge), edge)
    elif side == "left":
        # Fix 088 S88-1: mirror of "right" - the component's own minimum x
        # edge per row.
        for item in comp:
            edge = item["gx"]
            for row in range(item["gy"], item["gy"] + item["d"]):
                span[row] = min(span.get(row, edge), edge)
    else:
        for item in comp:
            edge = item["gy"] + item["d"]
            for col in range(item["gx"], item["gx"] + item["w"]):
                span[col] = max(span.get(col, edge), edge)
    if not span:
        return []
    ordered = sorted(span)
    segments: list[tuple[int, int, int]] = []
    start = prev = ordered[0]
    edge = span[ordered[0]]
    for pos in ordered[1:]:
        if pos == prev + 1 and span[pos] == edge:
            prev = pos
            continue
        segments.append((edge, start, prev + 1))
        start = prev = pos
        edge = span[pos]
    segments.append((edge, start, prev + 1))
    return segments


_SPACER_PLAN_BIN_FIELDS = (
    "id", "kind", "x", "y", "z", "wall", "object_height_mm", "stack",
)


def spacer_plan_signature(
    raw_drawer: dict[str, Any],
    bins: list[dict[str, Any]],
    options: dict[str, Any] | None = None,
) -> str:
    """CAS token for exactly the durable state that can change a spacer plan.

    Print status, Qty and generated filenames are intentionally excluded:
    they do not change the physical gaps. Any drawer geometry/placement change,
    any relevant placed-row geometry change, or any requested spacer setting
    change changes the token.
    """
    drawer = copy.deepcopy(raw_drawer or {})
    placed_ids = {
        str(one.get("bin"))
        for one in drawer.get("placements") or []
        if isinstance(one, dict) and one.get("bin") is not None
    }
    rows = []
    for one in bins or []:
        if str(one.get("id")) not in placed_ids:
            continue
        rows.append({
            key: one.get(key)
            for key in _SPACER_PLAN_BIN_FIELDS
        })
    rows.sort(key=lambda one: str(one.get("id") or ""))
    body = {
        "drawer": drawer,
        "bins": rows,
        "options": copy.deepcopy(options or {}),
    }
    encoded = json.dumps(
        body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def plan_spacers(raw_drawer: dict[str, Any], bins: list[dict[str, Any]], options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    drawer = normalise_drawer(raw_drawer)
    grid = drawer_grid(drawer)
    rows, cols, step = grid["rows"], grid["cols"], grid["step"]
    flexible = options.get("flexible", True)
    by_id = {one["id"]: one for one in bins}
    placed_spacer_count = sum(
        1 for placement in drawer.get("placements") or []
        if (by_id.get(placement.get("bin")) or {}).get("kind") in SPACER_KINDS)
    # Fix 088 S88-2: Auto height is the default - half the tallest bin's
    # height, clamped like a manual height. A manual height is honoured only
    # when Auto is off.
    if options.get("height_auto", True):
        # Fix 090: "tallest bin" means the tallest non-spacer bin actually
        # placed in THIS drawer - not the whole Space inventory (which also
        # holds unplaced bins and other drawers' bins).
        tallest = 0.0
        if rows and cols:
            for placement in drawer.get("placements") or []:
                one = by_id.get(placement.get("bin"))
                if one and one.get("kind") not in SPACER_KINDS:
                    tallest = max(tallest, float(one.get("z") or 0.0))
        auto_height = round(tallest / 2) if tallest > 0 else DEFAULT_SPACER_HEIGHT
        height = min(drawer["height"], max(MIN_SPACER_HEIGHT, auto_height))
    else:
        height = min(drawer["height"], max(MIN_SPACER_HEIGHT, float(options.get("height") or DEFAULT_SPACER_HEIGHT)))
    # Fix 088 S88-1: per-wall toggles, persisted under the layout's spacer
    # settings. There is deliberately no front-wall option.
    raw_walls = options.get("walls") or {}
    walls = {
        "left": bool(raw_walls.get("left", True)),
        "back": bool(raw_walls.get("back", True)),
        "right": bool(raw_walls.get("right", True)),
    }
    notes: list[str] = []

    candidates = []
    selected = []
    run_count = 0
    run_count_total = 0
    proposal_cap_applied = False

    if rows and cols:
        if not any(walls.values()):
            notes.append("All spacer walls are off.")
            return {"drawer": drawer, "height": height, "resolved_height": height,
                    "candidates": [], "selected": [], "notes": notes,
                    "run_count": 0, "run_count_total": 0,
                    "proposal_cap_applied": False,
                    "placed_spacer_count": placed_spacer_count}
        wall = drawer["clearance"] / 2.0
        
        items = [i for i in _grid_items(drawer, by_id) if i["kind"] not in SPACER_KINDS]
        
        adj = {i: set() for i in range(len(items))}
        for i, a in enumerate(items):
            for j, b in enumerate(items[i+1:], i+1):
                if max(a["gx"], b["gx"]) < min(a["gx"]+a["w"], b["gx"]+b["w"]) and (a["gy"]+a["d"] == b["gy"] or b["gy"]+b["d"] == a["gy"]):
                    adj[i].add(j)
                    adj[j].add(i)
                elif max(a["gy"], b["gy"]) < min(a["gy"]+a["d"], b["gy"]+b["d"]) and (a["gx"]+a["w"] == b["gx"] or b["gx"]+b["w"] == a["gx"]):
                    adj[i].add(j)
                    adj[j].add(i)
        
        seen = set()
        components = []
        for i in range(len(items)):
            if i not in seen:
                comp = []
                queue = [i]
                seen.add(i)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in adj[curr]:
                        if neighbor not in seen:
                            seen.add(neighbor)
                            queue.append(neighbor)
                components.append([items[idx] for idx in comp])
                
        for comp_idx, comp in enumerate(components):
            comp_area = sum(i["w"] * i["d"] for i in comp)

            def _note_max_gap():
                # Fix 1042: deterministic, deduplicated plan note - one note
                # no matter how many candidates are skipped for this reason.
                # Uses the exact promised copy.
                msg = f"Gap too large for a spacer (max {MAX_SPACER_GAP:.0f}mm)."
                if msg not in notes:
                    notes.append(msg)

            def _make_candidate(side, edge, start, end):
                # Fix 088 S88-3: distribute along long runs - one candidate
                # per ~100 mm of exposed run. Each is still a short,
                # deterministic, strategically placed contact piece - not the
                # whole exposed run - per Fix 004: target ~28 mm of contact
                # width, clipped to its sub-segment when shorter, centred
                # within it. Returns a list (possibly empty).
                # A left/right run is vertical (spans rows, measured from the
                # y origin); a back run is horizontal (spans columns).
                vertical = side in ("right", "left")
                seg_lo = (grid["oy"] if vertical else grid["ox"]) + start * step
                seg_hi = (grid["oy"] if vertical else grid["ox"]) + end * step
                seg_len = seg_hi - seg_lo
                count = max(1, round(seg_len / SPACER_DISTRIBUTE_EVERY))
                made = []
                for k in range(count):
                    sub_lo = seg_lo + seg_len * k / count
                    sub_hi = seg_lo + seg_len * (k + 1) / count
                    sub_len = sub_hi - sub_lo
                    contact = min(sub_len, SPACER_CONTACT_TARGET)
                    contact_start = sub_lo + (sub_len - contact) / 2.0
                    if side == "right":
                        gap = (drawer["width"] - grid["ox"] - (edge * step))
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        if gap > MAX_SPACER_GAP:
                            _note_max_gap()
                            continue
                        px, py, w, d = grid["ox"] + edge * step, contact_start, gap, contact
                        cid = f"right-{edge}-{start}-{end}-{k}"
                    elif side == "left":
                        # Fix 088 S88-1: mirror of "right" against the left wall.
                        # Fix 1042: removed -wall (spacer must reach the wall);
                        # px=0 places the spacer against the left wall (was
                        # floating 0.5mm off).
                        gap = (grid["ox"] + edge * step)
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        if gap > MAX_SPACER_GAP:
                            _note_max_gap()
                            continue
                        px, py, w, d = 0, contact_start, gap, contact
                        cid = f"left-{edge}-{start}-{end}-{k}"
                    else:
                        gap = (drawer["depth"] - grid["oy"] - (edge * step))
                        if gap < MIN_EDGE_SPACER or contact < MIN_EDGE_SPACER:
                            continue
                        if gap > MAX_SPACER_GAP:
                            _note_max_gap()
                            continue
                        px, py, w, d = contact_start, grid["oy"] + edge * step, contact, gap
                        cid = f"back-{edge}-{start}-{end}-{k}"
                    placement = {"bin": "spacer", "x": px, "y": py, "w": w, "d": d, "side": side}
                    area = w * d
                    score = comp_area / area if area > 0 else 0
                    # Fix 090: run identity - one exposed segment before
                    # distribution. A run's candidates are selected or
                    # skipped as a unit so the cap never chops a run in half.
                    run_id = f"{side}-{comp_idx}-{edge}-{start}-{end}"
                    # Fix 1042: pre-generation truth - resolve the spacer type
                    # here, on the UNPRELOADED measured gap, with the same
                    # authority generation uses. The UI shows this before
                    # Save; generation cannot disagree.
                    resolved = resolve_spacer_type(gap, contact, flexible)
                    will_fallback = bool(flexible) and resolved == "rigid"
                    # Fix 1042 (review): the reason comes from the single
                    # helper (Change 6b), not inline formatting - planning and
                    # generation cannot word it differently.
                    fallback_reason = spacer_fallback_reason(gap, contact) if will_fallback else ""
                    if resolved == "flexible":
                        printed_axis = gap + FLEX_PRELOAD_MM
                    else:
                        printed_axis = gap - RIGID_SPACER_CLEARANCE_MM
                    if side in ("right", "left"):
                        printed_w, printed_d = printed_axis, contact
                    else:
                        printed_w, printed_d = contact, printed_axis
                    made.append({"id": cid, "placements": [placement], "score": score,
                                 "axis": "x" if vertical else "y", "comp": comp_idx, "edge": edge,
                                 "run_id": run_id,
                                 "measured_gap": gap, "resolved_type": resolved,
                                 "will_fallback": will_fallback,
                                 "fallback_reason": fallback_reason,
                                 "printed_w": printed_w, "printed_d": printed_d})
                return made

            for side in ("left", "back", "right"):
                if not walls[side]:
                    continue
                for edge, start, end in _exposed_segments(comp, side):
                    candidates.extend(_make_candidate(side, edge, start, end))

        # Reject a candidate that overlaps another bin/component along its
        # own physical path to the wall (never bridge through something real
        # to reach it).
        item_boxes = [
            {"x": grid["ox"] + i["gx"] * step, "y": grid["oy"] + i["gy"] * step, "w": i["w"] * step, "d": i["d"] * step}
            for i in items
        ]
        placed_spacer_boxes = []
        for placement in drawer.get("placements") or []:
            row = by_id.get(placement.get("bin"))
            if not row or row.get("kind") not in SPACER_KINDS:
                continue
            if not all(key in placement for key in ("x", "y", "w", "d")):
                continue
            placed_spacer_boxes.append({
                "side": str(placement.get("side") or ""),
                "x": float(placement["x"]),
                "y": float(placement["y"]),
                "w": float(placement["w"]),
                "d": float(placement["d"]),
            })

        def _candidate_already_satisfied(cand: dict[str, Any]) -> bool:
            p = cand["placements"][0]
            box = {"x": p["x"], "y": p["y"], "w": p["w"], "d": p["d"]}
            return any(
                placed["side"] == p.get("side") and _overlaps(box, placed)
                for placed in placed_spacer_boxes
            )
        valid_cands = []
        for cand in candidates:
            p = cand["placements"][0]
            edge = {"x": p["x"], "y": p["y"], "w": p["w"], "d": p["d"]}
            if any(_overlaps(edge, box) for box in item_boxes):
                continue
            if _candidate_already_satisfied(cand):
                continue
            valid_cands.append(cand)
        candidates = valid_cands
        
        candidates.sort(key=lambda c: c["score"], reverse=True)
        # Fix 088 S88-3: keep the per-(component, axis) best-edge rule, but
        # select every candidate on the winning edge - the sub-segments of one
        # logical run - not just the best one.
        # Fix 090: the cap is applied per candidate, best scores first, and
        # is defined explicitly: a run MAY be partially selected when the
        # cap binds. The survivors within a chopped run are its
        # highest-scoring candidates - the end-clipped pieces first, so a
        # truncated run keeps its ends covered. Whole-run-or-nothing was
        # rejected: a small high-scoring run could starve a major run
        # entirely (1 spacer placed where 8 gaps need them).
        winning_edge = {}
        for cand in candidates:
            key = (cand["comp"], cand["axis"])
            if key not in winning_edge:
                winning_edge[key] = cand["edge"]
        for comp_idx in range(len(components)):
            left = any(
                cand["comp"] == comp_idx and cand["axis"] == "x" and
                cand["id"].startswith("left-")
                for cand in candidates
            )
            right = any(
                cand["comp"] == comp_idx and cand["axis"] == "x" and
                cand["id"].startswith("right-")
                for cand in candidates
            )
            if walls["left"] and walls["right"] and left and right:
                chosen_edge = winning_edge.get((comp_idx, "x"))
                if chosen_edge is not None:
                    notes.append(
                        "A bin group is braced against only one side wall; "
                        "the opposite side is not braced."
                    )
        winning = [
            cand for cand in candidates
            if winning_edge.get((cand["comp"], cand["axis"])) == cand["edge"]
        ]
        run_count_total = len({cand["run_id"] for cand in winning})
        proposal_cap_applied = len(winning) > SPACER_SELECTED_CAP
        chosen = winning[:SPACER_SELECTED_CAP]
        selected = [{"id": cand["id"]} for cand in chosen]
        run_count = len({cand["run_id"] for cand in chosen})

        for cand in candidates:
            cand.pop("score", None)
            cand.pop("axis", None)
            cand.pop("comp", None)
            cand.pop("edge", None)
            cand.pop("run_id", None)

    return {"drawer": drawer, "height": height, "resolved_height": height,
            "candidates": candidates, "selected": selected, "notes": notes,
            "run_count": run_count, "run_count_total": run_count_total,
            "proposal_cap_applied": proposal_cap_applied,
            "placed_spacer_count": placed_spacer_count}

def resolve_spacer_type(measured_gap: float, contact: float, flexible_requested: bool) -> str:
    """Fix 1042: THE single authority for the flexible/rigid cutoff.

    Evaluated on the UNPRELOADED measured gap. Planning (_make_candidate) and
    generation (_serpentine_flexure) call this directly; the user-facing reason
    comes from spacer_fallback_reason (below), which uses the same named
    constants - no duplicated thresholds, no magic numbers anywhere.
    A flexible spacer needs measured_gap >= FLEX_MIN_GAP_MM (9.0): the pads
    take 3+2=5mm and the serpentine needs >=6mm of span for its minimum two
    half-waves (3mm pitch at the boundary - the tightest that keeps 1mm webs
    manufacturable; larger gaps use ~8mm pitch); the 2.0mm preload supplies
    2mm of that span, so 5 + 6 - 2 = 9.0mm measured. It also needs contact >=
    FLEX_MIN_CONTACT_MM (6.0) so the zigzag has room for its amplitude.
    """
    if (flexible_requested
            and measured_gap >= FLEX_MIN_GAP_MM
            and contact >= FLEX_MIN_CONTACT_MM):
        return "flexible"
    return "rigid"


def spacer_fallback_reason(measured_gap: float, contact: float) -> str:
    """Fix 1042: plain-language reason for a flexible->rigid fallback.

    Single source for the message - planning (Change 10) and generation
    (Change 10a) both call this, so the copy cannot desync from the cutoff.
    Uses the same named constants as resolve_spacer_type. No backend
    thresholds, no jargon ("contact" is not user vocabulary), consistent
    "5.0 mm" spacing throughout.
    """
    if measured_gap < FLEX_MIN_GAP_MM:
        return f"Gap {measured_gap:.1f} mm is too small for the flexible zigzag."
    return (f"Only {contact:.1f} mm of bin edge to hold — "
            f"too short for the flexible zigzag.")


def _collapse_spikes(poly):
    """Drop consecutive exterior-ring vertices closer than 1e-9 mm.

    Fix 1043: clipping a wavy pad at exactly its wall's extreme x can leave
    a degenerate spike - two ring vertices ~1e-14 apart where the clip edge
    passes a hair outside a wall vertex (the back pad's bottom-right corner
    at contacts >= 16 mm). The spike is OGC-valid (is_valid stays True) but
    earcut triangulates it into a non-watertight mesh, and buffer(0) does
    not remove it because the spike tip sits on the boundary. The first
    vertex in ring order is the clip-edge crossing, exactly on the intended
    boundary, so collapsing keeps the printed envelope bit-identical.
    """
    if not isinstance(poly, Polygon):
        return poly
    ring = list(poly.exterior.coords)[:-1]
    kept = [ring[0]]
    for coord in ring[1:]:
        if math.hypot(coord[0] - kept[-1][0], coord[1] - kept[-1][1]) > 1e-9:
            kept.append(coord)
    if len(kept) > 1 and math.hypot(kept[-1][0] - kept[0][0],
                                    kept[-1][1] - kept[0][1]) <= 1e-9:
        kept.pop()
    return Polygon(kept)


def _serpentine_flexure(
    w, d, side, flexible=True, *, phase_x=0.0, phase_y=0.0,
):
    # Fix 1042: thinner webs (1.0mm) bend instead of crushing; the 2.0mm
    # preload ("a couple mm" - Andrew) is added only on the flexible branch,
    # AFTER the cutoff authority above has run on the unpreloaded measurement.
    web = 1.0
    pad_bin = 3.0
    pad_wall = 2.0

    if side == "left":
        # Fix 1042: negate phase_y to compensate for the X-mirror, which
        # otherwise leaves the wave anti-phase (up to 0.7mm interference).
        mirrored, built_flexible = _serpentine_flexure(
            w, d, "right", flexible, phase_x=phase_x, phase_y=-phase_y,
        )
        minx, _miny, maxx, _maxy = mirrored.bounds
        return affinity.scale(mirrored, -1, 1, origin=((minx + maxx) / 2, 0)), built_flexible

    if side == "right":
        # Fix 1042: the cutoff runs on the UNPRELOADED measured gap via the
        # single authority - the preload is added only after it resolves.
        resolved_flexible = resolve_spacer_type(w, d, flexible) == "flexible"
        if resolved_flexible:
            w += FLEX_PRELOAD_MM  # Fix 1042: 2.0mm preload for hand-insertable flex
        if not resolved_flexible:
            relief = min(RIGID_SPACER_CLEARANCE_MM, max(0.0, w - 0.2))
            return shape_box(
                relief / 2.0, 0,
                w - relief / 2.0, d,
            ), False

        # Bin-facing wave: preserve the accepted shape construction but phase
        # it from this off-lattice spacer's actual Y centre.
        bin_profile = wavy_rect_outer(10.0, d / 2.0, phase_y=phase_y)
        bin_profile = affinity.translate(bin_profile, -bin_profile.bounds[0], d / 2.0)
        left_pad = bin_profile.intersection(shape_box(0, 0, pad_bin, d))

        # Drawer-wall pad uses the same canonical wave, aligned to the opposite
        # side of this measured gap instead of remaining flat.
        wall_profile = wavy_rect_outer(10.0, d / 2.0, phase_y=phase_y)
        wall_profile = affinity.translate(wall_profile, w - wall_profile.bounds[2], d / 2.0)
        right_pad = wall_profile.intersection(shape_box(w - pad_wall, 0, w, d))

        # Fix 1042: true serpentine - the compression direction (x) has no
        # straight axial bridge. Diagonal members zigzag between the pads at
        # a constant ~8mm pitch, so x-compression bends them instead of
        # loading them axially. Constant pitch keeps the member angle ~56
        # degrees at every gap size: stiffness is roughly gap-independent
        # and no member gets long/shallow enough to buckle.
        x0, x1 = pad_bin, w - pad_wall
        mid_y = d / 2.0
        amp = min(6.0, d / 2.0 - web)
        y_lo, y_hi = mid_y - amp, mid_y + amp
        n_half = max(2, int(round((x1 - x0) / 8.0)))
        parts = []
        for i in range(n_half):
            xa = x0 + (x1 - x0) * i / n_half
            xb = x0 + (x1 - x0) * (i + 1) / n_half
            ya = y_lo if i % 2 == 0 else y_hi
            yb = y_hi if i % 2 == 0 else y_lo
            dx, dy = xb - xa, yb - ya
            length = math.hypot(dx, dy)
            angle = math.degrees(math.atan2(dy, dx))
            # Each bar runs web past its endpoints along its own axis so
            # neighbours overlap solidly at the vertices and the end bars
            # bite into the pads.
            bar = shape_box(-length / 2.0 - web, -web / 2.0,
                            length / 2.0 + web, web / 2.0)
            bar = affinity.rotate(bar, angle, origin=(0, 0), use_radians=False)
            parts.append(affinity.translate(bar, (xa + xb) / 2.0, (ya + yb) / 2.0))
            # 2x2mm gusset at each vertex keeps the chain one connected solid.
            parts.append(shape_box(xa - web, ya - web, xa + web, ya + web))
        parts.append(shape_box(xb - web, yb - web, xb + web, yb + web))
        # Fix 1042 (review): clip to the contact band. The rotated end bars
        # otherwise poke up to ~0.12mm past the contact height at steep member
        # angles, which would falsify the plan-time printed envelope. The pads
        # already bound the part; this only trims bar-tip overshoot.
        return _collapse_spikes(unary_union([left_pad, right_pad] + parts).intersection(
            shape_box(0, 0, w, d))), True

    # Fix 1042: the cutoff runs on the UNPRELOADED measured gap via the
    # single authority - the preload is added only after it resolves.
    resolved_flexible = resolve_spacer_type(d, w, flexible) == "flexible"
    if resolved_flexible:
        d += FLEX_PRELOAD_MM  # Fix 1042: 2.0mm preload for hand-insertable flex
    if not resolved_flexible:
        relief = min(RIGID_SPACER_CLEARANCE_MM, max(0.0, d - 0.2))
        return shape_box(
            0, relief / 2.0,
            w, d - relief / 2.0,
        ), False

    bin_profile = wavy_rect_outer(w / 2.0, 10.0, phase_x=phase_x)
    bin_profile = affinity.translate(bin_profile, w / 2.0, -bin_profile.bounds[1])
    bot_pad = bin_profile.intersection(shape_box(0, 0, w, pad_bin))

    wall_profile = wavy_rect_outer(w / 2.0, 10.0, phase_x=phase_x)
    wall_profile = affinity.translate(wall_profile, w / 2.0, d - wall_profile.bounds[3])
    top_pad = wall_profile.intersection(shape_box(0, d - pad_wall, w, d))

    # Fix 1042: true serpentine - the compression direction (y) has no
    # straight axial bridge. Diagonal members zigzag between the pads at a
    # constant ~8mm pitch so y-compression bends them instead of loading
    # them axially (mirror of the right-side construction).
    y0, y1 = pad_bin, d - pad_wall
    mid_x = w / 2.0
    amp = min(6.0, w / 2.0 - web)
    x_lo, x_hi = mid_x - amp, mid_x + amp
    n_half = max(2, int(round((y1 - y0) / 8.0)))
    parts = []
    for i in range(n_half):
        ya = y0 + (y1 - y0) * i / n_half
        yb = y0 + (y1 - y0) * (i + 1) / n_half
        xa = x_lo if i % 2 == 0 else x_hi
        xb = x_hi if i % 2 == 0 else x_lo
        dx, dy = xb - xa, yb - ya
        length = math.hypot(dx, dy)
        angle = math.degrees(math.atan2(dy, dx))
        bar = shape_box(-length / 2.0 - web, -web / 2.0,
                        length / 2.0 + web, web / 2.0)
        bar = affinity.rotate(bar, angle, origin=(0, 0), use_radians=False)
        parts.append(affinity.translate(bar, (xa + xb) / 2.0, (ya + yb) / 2.0))
        parts.append(shape_box(xa - web, ya - web, xa + web, ya + web))
    parts.append(shape_box(xb - web, yb - web, xb + web, yb + web))
    # Fix 1042 (review): clip to the contact band - see the right branch above.
    # Trims the rotated-bar tip overshoot so the printed envelope is exact.
    return _collapse_spikes(unary_union([bot_pad, top_pad] + parts).intersection(
        shape_box(0, 0, w, d))), True


def spacer_filename(side: str, w: float, d: float, height: float, flexible: bool) -> str:
    """Deterministic from the real, unsnapped geometry - two decimals so
    distinct gaps (12.1 vs 12.9 mm) never collide, and Flexible/Rigid never
    share a name merely because their envelope came out the same size."""
    # Fix 1042 (acceptance gate): while the mechanical acceptance record is
    # PENDING, a flexible filename carries the non-performance-bearing
    # qualifier "Unvalidated". The "Spacer Flex " prefix is kept on purpose:
    # the Print Spacers UI detects flex from filenames with ^Spacer Flex ,
    # and legacy bare "Spacer Flex ..." files must keep classifying as
    # flexible (they are unvalidated too). Do not shorten or reorder.
    variant = "Flex Unvalidated" if flexible else "Rigid"
    return f"Spacer {variant} {side.capitalize()} {w:.2f}x{d:.2f}x{height:.2f}.3mf"


def generate_spacers(request: dict[str, Any], output_dir: Path | str, generate_file: Callable[[str, trimesh.Trimesh], Path]) -> dict[str, Any]:
    options = request.get("options") or {}
    plan = plan_spacers(request.get("drawer") or {}, request.get("bins") or [], options)
    requested_ids = set(request.get("selected") or [])
    height = plan["height"]
    drawer = plan["drawer"]
    flexible = bool(options.get("flexible", True))

    generated = []
    notes = []

    for cand in plan["candidates"]:
        cid = cand["id"]
        if cid in requested_ids:
            p = cand["placements"][0]
            side = p["side"]
            # placement envelope/gap: where the measured gap lies in the
            # drawer - the free placement x/y/w/d keeps describing this.
            gap_w = p["w"]
            gap_d = p["d"]

            phase_x = p["x"] + gap_w / 2.0
            phase_y = p["y"] + gap_d / 2.0
            poly, built_flexible = _serpentine_flexure(
                gap_w, gap_d, side, flexible,
                phase_x=phase_x, phase_y=phase_y,
            )
            # printed physical part size: the actual generated mesh target,
            # including the accepted 0.5 mm preload only for a true flexure.
            minx, miny, maxx, maxy = poly.bounds
            part_w, part_d = maxx - minx, maxy - miny
            is_flexible = flexible and built_flexible
            if flexible and not built_flexible:
                # Fix 1042: backstop note - plan-time truth already showed the
                # resolved type before Save. The reason comes from the same
                # helper as the plan-time message (Change 6b), so the two
                # cannot desync; no duplicated thresholds.
                axis_len = gap_w if side in ("left", "right") else gap_d
                contact_len = gap_d if side in ("left", "right") else gap_w
                reason = spacer_fallback_reason(axis_len, contact_len)
                notes.append(
                    f"{reason} Printed a rigid spacer for the {side} side instead."
                )

            mesh = _extrude_polygon(poly, height)
            file_name = spacer_filename(side, part_w, part_d, height, is_flexible)
            out_path = generate_file(file_name, mesh)

            generated.append({
                "id": cid,
                "file": file_name,
                "placements": cand["placements"],
                # actual printed part size - what inventory x/y/z records.
                "w": part_w, "d": part_d, "h": height, "side": side,
                "flexible": is_flexible,
            })

    return {"generated": generated, "notes": notes}


# ---------------------------------------------------------------- connectors


def generate_connectors(
    output_dir: Path | str,
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None = None,
) -> dict[str, Any]:
    """Print files for every connector a drawer's layout needs: one file per
    pair of rim heights, with how many of it to print."""
    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    # Fix 111 N10: pass the authoritative layout so lid rows are stamped from
    # their canonical design specs (drawer_report needs it for specs).
    report = drawer_report(find_drawer(layout, drawer_id), bins, layout=layout)
    made, notes = [], []
    connector = ConnectorSpec()
    for group in report["connectors"]:
        high, low = group["heights"]
        wall = group["wall"]
        different = abs(high - low) > 1e-6
        plan = differing_connector_plan(
            connector, LOCKED_CONNECTOR_LENGTH, high, low,
            BoxSpec(2 * UNIT, 6 * UNIT, high, wall=wall),
        )
        length = plan["length_mm"]
        name = connector_filename(
            connector, length=length, bin_a_height=high, bin_b_height=low,
            different_heights=different, wall=wall,
        )
        try:
            generate_side_file(
                BoxSpec(2 * UNIT, 6 * UNIT, high, wall=wall), connector, output_dir / name,
                "y", 0.0, length, high, low,
                web_thickness=plan["web_thickness_mm"] if different else None, auto_adjust=False,
            )
        except ValueError as error:
            notes.append(f"{high:g} → {low:g} mm: {error}")
            continue
        made.append({"file": name, "count": group["count"], "heights": [high, low]})
    if report["connector_mismatched"]:
        notes.append(
            f"{report['connector_mismatched']} seam(s) join bins with different wall "
            "thicknesses; no single connector fits both."
        )
    if report["connector_short_seams"]:
        notes.append(
            f"{report['connector_short_seams']} shared seam(s) are too short for a connector; "
            "those bins print without connectors."
        )
    return {"connectors": made, "notes": notes}


def print_spacers_and_connectors(
    output_dir: Path | str,
    layout: dict[str, Any],
    bins: list[dict[str, Any]],
    drawer_id: str | None,
    detect_slicer: Callable,
    launch_slicer: Callable,
    slicer_path: str | None = None,
) -> dict[str, Any]:
    """Open one drawer's spacers and connectors in the slicer together."""
    output_dir = Path(output_dir).expanduser().resolve()
    drawer = find_drawer(layout, drawer_id)
    by_id = {one["id"]: one for one in bins}
    # Preflight the authoritative slicer before any connector file is written.
    slicer = detect_slicer(slicer_path)
    if slicer is None or not Path(slicer).is_file():
        raise ValueError("A slicer was not found. Locate it with Change slicer in the bin view.")
    # Fix 096 F11: user-facing copy names the detected slicer, never a hardcoded brand.
    name = slicer_display_name(slicer) or "the slicer"
    counts: dict[str, int] = {}
    for placement in drawer.get("placements") or []:
        one = by_id.get(placement.get("bin"))
        if one and one.get("kind") in SPACER_KINDS and one.get("file"):
            counts[one["file"]] = counts.get(one["file"], 0) + 1
    connectors = generate_connectors(output_dir, layout, bins, drawer_id)
    for made in connectors["connectors"]:
        counts[made["file"]] = counts.get(made["file"], 0) + made["count"]
    files = [output_dir / name for name in counts if (output_dir / name).is_file()]
    omitted = sorted(name for name in counts if not (output_dir / name).is_file())
    if not files:
        raise ValueError("this drawer has no spacers or connectors to print yet")
    # Each file is repeated once per physical copy so the slicer project holds
    # the real number of parts.
    launch_files = [path for path in files for _ in range(max(1, counts[path.name]))]
    try:
        launch_slicer(Path(slicer), launch_files)
    except Exception as error:
        # The connector files above are real and kept; say so plainly.
        return {
            "partial": True,
            "partial_stage": "slicer",
            "error": f"Files were prepared, but {name} did not open: {error}",
            "files": [str(path) for path in files],
            "counts": counts,
            "omitted": omitted,
            "notes": connectors["notes"],
        }
    return {"files": [str(path) for path in files], "counts": counts, "omitted": omitted, "notes": connectors["notes"]}
