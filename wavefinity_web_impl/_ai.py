"""Wavefinity web AI Design schema, prompt and candidate helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any
from organizer_inserts import FEATURE_DEFINITIONS, Feature, Layout
from organizer_inserts._bore import BORE_CLEARANCE, HEX_BIT_FIXED

from organizer_engine import GRID_PITCH, BoxSpec
from organizer_engine._specs import (
    ACCENT_COLORS,
    DEFAULT_ACCENT_COLOR,
    DEFAULT_CORNER_FEET,
    DEFAULT_HOLLOW_BASE,
    DEFAULT_MAGNET_HOLES,
    GRIDFINITY_MAGNET_HOLE_CHOICES,
    cross_grid_message,
    grid_hinged_lid_refusal,
    validate_grid,
)
from ._runtime import default_design
from ._designs import _is_base_trim_design, validate_design_payload


def grid_editor_catalog() -> list[dict[str, Any]]:
    """Shared editor/AI choices, with dimensions taken from the geometry model."""
    from organizer_engine._specs import GRID_PITCHES
    from organizer_engine._specs import BoxSpec
    from organizer_features.gridfinity import (
        HEIGHT_UNIT, MIN_GRID_BASE, assembled_lid_stack_height, assembled_stack_height, minimum_floor_build, floor_pocket_depth,
        rim_depth, BODY_CORNER_RADIUS, FOOT_HEIGHT, PERIMETER_GAP,
    )
    from organizer_b4b._constants import B4B_STACK_RECESS_DEPTH
    labels = {"wavefinity": "Wavefinity 7 mm", "gridfinity_half": "Gridfinity half 21 mm",
              "gridfinity": "Gridfinity 42 mm"}

    def seat_descent(grid: str, pitch: float, height_of) -> float | None:
        """How far an upper bin sinks into the one below, read from the engine's own
        assembled heights (Stories 2970/2971) so the layout never keeps a second copy."""
        if grid == "wavefinity":
            return None
        probe = BoxSpec(pitch, pitch, 2 * HEIGHT_UNIT)
        return round(probe.z + probe.z - height_of(probe, probe, grid), 9)

    return [{"value": grid, "label": labels[grid], "pitch_mm": pitch,
             "stack_seat_descent_mm": seat_descent(grid, pitch, assembled_stack_height),
             "lid_stack_seat_descent_mm": seat_descent(grid, pitch, assembled_lid_stack_height),
             "height_unit_mm": None if grid == "wavefinity" else HEIGHT_UNIT,
             "minimum_base_mm": 0 if grid == "wavefinity" else MIN_GRID_BASE,
             # Story 2975: a Storage Box with a Floor (its own raised socket grid)
             # needs this much base; None (plain cavity) has no such minimum.
             "container_floor_build_mm": 0 if grid == "wavefinity" else minimum_floor_build(grid),
             "container_floor_pocket_depth_mm": 0 if grid == "wavefinity" else floor_pocket_depth(grid),
             "container_floor_stacking_build_mm": (
                 0 if grid == "wavefinity" else minimum_floor_build(grid, B4B_STACK_RECESS_DEPTH)),
             "container_floor_choices": (
                 [{"value": "floor", "label": "Floor (raised socket grid)"},
                  {"value": "none", "label": "None (plain cavity for your own baseplate)"}]
                 if grid != "wavefinity" else None),
             "rim_depth_mm": 0 if grid == "wavefinity" else rim_depth(grid),
             "side_connectors": grid == "wavefinity",
             "side_openings": True,
             "perimeter_gap_mm": 0 if grid == "wavefinity" else PERIMETER_GAP,
             "side_opening_corner_radius_mm": 0 if grid == "wavefinity" else BODY_CORNER_RADIUS,
             "side_opening_foot_height_mm": 0 if grid == "wavefinity" else FOOT_HEIGHT,
             "edge_mount": grid == "wavefinity",
             # Story 3009: the hinged lid is listed only on a pitch whose envelope
             # assessment supports it; otherwise ``hinged_lid_refusal`` says why.
             "lid_choices": ([{"value": "none", "label": "No lid"},
                              {"value": "resting", "label": "Gridfinity Lid"},
                              {"value": "stacking", "label": "Gridfinity Lid for stacking"}]
                             + ([] if grid_hinged_lid_refusal(grid) else
                                [{"value": "hinged", "label": "Gridfinity Hinged lid"}])
                             if grid != "wavefinity" else None),
             "hinged_lid_refusal": grid_hinged_lid_refusal(grid)}
            for grid, pitch in GRID_PITCHES.items()]


def ai_context_grid(candidate: Any, grid: str) -> dict[str, Any]:
    """Check the candidate before supplying missing context metadata."""
    grid = validate_grid(grid)
    if not isinstance(candidate, dict):
        raise ValueError("The response has no design object.")
    if "grid" in candidate and validate_grid(candidate["grid"]) != grid:
        raise ValueError(cross_grid_message(candidate["grid"], grid, "The AI design"))
    return {**candidate, "grid": grid}


# ---------------------------------------------------------------- AI Help (Fix 073)
#
# These local helpers never call an AI provider. Browser-direct BYOK calls
# belong to ai-providers.js; manual copy/paste remains available. This module
# builds prompts and proves answers are legal ordinary bins. Nothing is stored:
# request ID / fingerprint are opaque, and the browser owns the runtime session.

AI_DESIGN_SCHEMA = "wavefinity-ai-design-v1"
# The public outside-AI reference (see ai-features.md). Supplemental only: the
# embedded prompt is always sufficient, so nothing here ever makes a network
# call - it just picks which URL to print, from the one already-known commit
# identity Wavefinity has (RENDER_GIT_COMMIT), falling back to the stable
# branch link when that is absent or not a real full SHA.
AI_FEATURE_REFERENCE_REPO = "happydadto5/Wavefinity"
AI_FEATURE_REFERENCE_PATH = "ai-features.md"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")


def ai_feature_reference_url() -> str:
    commit = os.environ.get("RENDER_GIT_COMMIT", "")
    ref = commit if _HEX40.fullmatch(commit) else "main"
    return f"https://raw.githubusercontent.com/{AI_FEATURE_REFERENCE_REPO}/{ref}/{AI_FEATURE_REFERENCE_PATH}"

AI_MAX_DESCRIPTION = 4000
AI_MAX_RESPONSE = 400_000
AI_SPACE_KINDS = ("drawer", "box", "surface", "portable", "pegboard", "storage_drawers")
# Capabilities a text-only AI cannot legally supply. They are offered to the
# person as a recommendation, never as something the returned JSON may contain.
AI_MEDIA_CAPABILITIES = ("photo",)
AI_MEDIA_REASON = (
    "Needs a photo or traced outline that a text answer cannot supply. "
    "Recommend the person add it themselves with Photo Nest inside Wavefinity; "
    "never put this part in the returned design."
)
_ACCENT_BAND_RULES: dict[str, Any] = {
    "accent_band": {"type": "boolean", "default": False},
    "accent_color": {"default": DEFAULT_ACCENT_COLOR, "choices": list(ACCENT_COLORS)},
    "band_height_mm": 1.0,
    "filament_slot": 2,
    "body_only": True,
}
AI_MODIFIER_BLOCKS = (
    ("accent_band", "Top 1 mm Accent",
     f"Set box.accent_band=true only when requested (default {str(_ACCENT_BAND_RULES['accent_band']['default']).lower()}). "
     f"box.accent_color defaults to {_ACCENT_BAND_RULES['accent_color']['default']}; "
     f"choices are {', '.join(_ACCENT_BAND_RULES['accent_color']['choices'])}. "
     f"Only the body's top {_ACCENT_BAND_RULES['band_height_mm']:g} mm, including an open stacking rim, "
     f"becomes named 3MF parts on filament slot {_ACCENT_BAND_RULES['filament_slot']}. "
     "Fit and lids are unchanged. The color is nominal; loaded filament determines the printed color. "
     "STL retains the full body without color separation.",
     ("box.accent_band", "box.accent_color")),
    ("lid_stacking", "Lid & Stacking",
     "Stackable Bin is box.stack = {\"mode\": \"direct\"} (its own base sits in the bin below); it may be combined with a lid. "
     "A Lid is box.lid; a resting lid (not flip_enabled) may set stack_rim=true (this is the \"Lid for stacking\" lid type; OFF by default, add it only when a bin is to stand on the lid) to carry a 2 mm rim on its top face that another stackable bin sits into. "
     "A lid with a handle (the handle is optional and OFF by default, so add handle_enabled=true only when one is asked for, with handle_type knob (the only handle), handle_size and handle_position), a Flip lid, or a lid with raised lettering cannot receive a stack, and neither can a lid that is not a Lid for stacking (stack_rim false). "
     "On a Gridfinity grid (gridfinity or gridfinity_half) a Flip lid is refused: its open swing overruns the one-cell envelope and the neighbour gap, so use a plain or stacking lid there; a Flip lid and stack_rim are never combined. "
     "Any lid may also be a Flip lid (Wavefinity grid only): flip_enabled=true (OFF by default; add it only when a hinged lid is asked for) hinges it on the back inside edge with a 1.75 mm filament pin, independent of the handle; optional alignment=\"off\"|\"thin\"|\"standard\"|\"thick\" (default off, only add when asked) adds front-corner alignment tabs 0/1/2/3 mm deep and makes the lid need support. "
     "",
     ("box.lid", "box.stack")),
    ("inside_handles", "Inside Grip",
     "A finger grip inside the bin (box.lift_grabbers).", ("box.lift_grabbers",)),
    ("side_openings", "Side Openings",
     "Finger-access cutouts through selected walls (box.side_openings), on all three grids. "
     "Gridfinity refuses cuts into the foot/base, open-bin stacking rim or corner-radius regions, "
     "or leaving a strip thinner than the chosen wall; never clips or shrinks. Physical fit unverified.",
     ("box.side_openings",)),
    ("edge_mount", "Edge Mount",
     "A label and/or screw mounting on one outside edge (box.edge_mount). "
     "Include the block only when the edge mount is wanted.",
     ("box.edge_mount",)),
)
_AI_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']*|(?:/[\w.\-]+){2,}")


def _ai_example_base() -> dict[str, Any]:
    """A roomy blank bin (a whole multiple of the 7 mm grid), so every example part and modifier is legal in it."""
    design = default_design()
    design["box"].update({"x": 70.0, "y": 70.0, "z": 60.0})
    return design


def _ai_legal_values(option: dict[str, Any]) -> str:
    """One readable line of what an option may hold, from its own metadata."""
    kind = option["type"]
    if "choices" in option:
        quote = "" if kind in ("number", "integer") else '"'
        return "one of: " + ", ".join(f'{quote}{one["value"]}{quote}' for one in option["choices"])
    if kind == "boolean":
        return "true or false"
    if kind in ("number", "integer"):
        low, high = option.get("minimum"), option.get("maximum")
        span = (f"{low:g} to {high:g}" if low is not None and high is not None
                else f"at least {low:g}" if low is not None
                else f"at most {high:g}" if high is not None else "any number")
        return ("whole number " if kind == "integer" else "number ") + span
    return {"string": "text", "json": "JSON value", "enum": "see note"}.get(kind, kind)


# Correction 3: a registry capability flag says a feature HAS this kind of
# control, not that today's Designer exposes it at the generic top-level field.
# Bore's lean direction moved to options.angle_towards (top-level `along` is a
# legacy fallback); Divider's quantities moved entirely to options.count_x /
# count_y (top-level `count`/`along` are legacy single-axis compatibility).
# This table is the one place that overrides the mechanical inference.
_AI_GENERIC_FIELD_EXCLUSIONS: dict[str, set[str]] = {
    "bore": {"along"},
    "divider": {"qty", "along"},
}


def _ai_generic_fields(part: dict[str, Any], starter: dict[str, Any],
                       item_rules: dict[str, Any]) -> dict[str, Any]:
    """The shared top-level feature fields (outside ``options``) this holder uses.

    Driven by the holder's capabilities, then narrowed by
    ``_AI_GENERIC_FIELD_EXCLUSIONS`` for the cases where the current Designer UI
    does not actually expose the generic control a capability flag implies (see
    Fix 073 Correction 3). ``full_span``/``wedge`` are never offered here: the
    current Designer only builds upright grid dividers and never lets a person
    edit either field, so they are canonical structure to copy from the example,
    not an AI-facing choice.
    """
    caps = set(part["capabilities"]) - _AI_GENERIC_FIELD_EXCLUSIONS.get(part["kind"], set())
    kind = part["kind"]
    zone_note = ("Label's zone is derived from its lettering: copy the example's zone and do not tune it."
                 if kind == "text" else
                 "Width is x1-x0 and depth is y1-y0; make it large enough for the count and item size.")
    fields: dict[str, Any] = {
        "zone": {
            "type": "array of 4 numbers", "form": "[x0, y0, x1, y1]",
            "rules": "millimetres from the bin centre; x1 > x0 and y1 > y0; must lie entirely inside "
                     "the interior of the design you RETURN (not the old size). " + zone_note,
            "example": starter["zone"],
        },
    }
    if "size" in caps:
        fields["size"] = {
            "rules": "This part's footprint is its zone: width = x1-x0, depth = y1-y0. There is no separate "
                     "size field, so choose a zone big enough for the requested quantity/shape.",
        }
    if "qty" in caps:
        auto = kind != "steps"
        fields["count"] = {
            "type": "whole number or null", "minimum": 1,
            "null_means": ("Auto: as many as fit the zone" if auto else
                           "not allowed for Steps: give the number of steps (default 3)"),
            "example": starter["count"],
            **({"note": "Use top-level count and along for Posts; do not use options.count_x / options.count_y."}
               if kind == "post" else {}),
        }
    if "along" in caps:
        fields["along"] = {
            "type": "text", "default": "x",
            "values": [
                {"value": "x", "meaning": "the part runs along the bin's X axis (its width, left to right)"},
                {"value": "y", "meaning": "the part runs along the bin's Y axis (its depth, front to back)"},
            ],
            **({"note": "A Bore's lean direction is options.angle_towards when present; along is the older control."}
               if kind == "bore" else {}),
        }
    if "alternate" in caps:
        fields["alternate_ends"] = {
            "type": "boolean", "default": False,
            "meaning": "false = every item faces the same way (Aligned); true = every second item is turned "
                       "end-for-end so neighbouring handles and shafts interleave (Alternate ends)",
        }
    if "item" in caps:
        profiles = [dict(one) for one in part["item_profiles"]]
        item: dict[str, Any] = {
            "type": "object",
            "shape": {"name": "non-empty text",
                      "profile": "one of the profile values below",
                      "clearance": "number, mm, 0 or more (slack around the item)",
                      "segments": "list of at least one {length, diameter}; both positive numbers in mm"},
            "profiles": profiles,
            "default_clearance_mm": item_rules["default_clearance_mm"],
            "example": starter["item"],
        }
        if kind == "bore":
            item["rules"] = (
                "Use one segment {length, diameter}; length is the item's length and diameter its width. "
                f"Set clearance to exactly {item_rules['bore_clearance_mm']:g} mm. "
                "Profile 'hex_bit_short' / 'hex_bit_long' are fixed 1/4 inch hex-bit presets: the item MUST be "
                "exactly the hex_bit entry below for that profile (single segment, its length_mm and diameter_mm, its clearance_mm), "
                "and the bore stands straight up, so leave options.angle at 0 and omit options.angle_towards. "
                "Its hole depth (options.depth) defaults to the entry's hole_depth_mm.")
            item["hex_bit"] = item_rules["hex_bit"]
        elif kind == "cradle":
            item["rules"] = ("A cradle is a half-round notch: profile is always 'round', clearance 0. Give one "
                             "segment {length, diameter} for the tool laid on its side.")
        fields["item"] = item
    if kind == "divider":
        fields["note"] = (
            "Quantities are options.count_x / options.count_y only; the top-level count/along "
            "fields are legacy and are not read for a grid divider. Copy full_span and wedge "
            "from the example unchanged - they are fixed structure, not choices."
        )
    return fields


def _ai_modifier_examples() -> dict[str, dict[str, Any]]:
    """One canonical example block per user-facing modifier.

    Each is produced by running a raw block through the same validator every
    design uses, so an example can never drift from the real serializer.
    """
    raw_blocks = {
        "accent_band": {"accent_band": True, "accent_color": DEFAULT_ACCENT_COLOR},
        "lid_with_handle": {"lid": {"enabled": True}},
        "stackable_bin": {"stack": {"mode": "direct"}},
        "inside_handles": {"lift_grabbers": {
            "enabled": True, "size": "medium", "location": "sides"}},
        "side_openings": {"side_openings": {
            "enabled": True, "shape": "curved", "sides": ["front"], "size": "medium",
            "from_bottom_percent": 0, "from_top_percent": 0,
            "percent_mode": "inset_v2"}},
        "edge_mount": {"edge_mount": {
            "side": "front", "label_enabled": True, "label_text": "Label",
            "holes_enabled": True}},
    }
    examples: dict[str, dict[str, Any]] = {}
    for name, blocks in raw_blocks.items():
        design = _ai_example_base()
        design["box"].update(blocks)
        design = validate_design_payload({"design": design})["design"]
        examples[name] = {key: design["box"][key] for key in blocks if key in design["box"]}
    return examples


def _ai_clean_text(text: str, limit: int = 600) -> str:
    """A short user-facing reason: no paths, no tracebacks."""
    text = re.sub(r"Traceback.*", "", text, flags=re.S)
    return _AI_PATH_RE.sub("[path]", text).strip()[:limit]


_AI_GRID_RE = re.compile(
    r"box ([XY]) must be a whole multiple of the (\d+) mm grid[^;]*;\s*([\d.]+) mm is not[^.]*")
_AI_AXIS_WORDS = {"X": "width", "Y": "depth"}


def _ai_plain_size_words(text: str) -> str:
    """Say a bin size problem in plain words: never "box X", never a "try N mm" fix."""
    text = _AI_GRID_RE.sub(
        lambda m: (f"The bin's {_AI_AXIS_WORDS[m.group(1)]} ({m.group(3)} mm) must be a whole "
                   f"multiple of {m.group(2)} mm so it interlocks with bins of other sizes"),
        text)
    return re.sub(r"\bbox ([XY])\b", lambda m: f"bin {_AI_AXIS_WORDS[m.group(1)]}", text)


def _ai_safe_message(error: BaseException) -> str:
    if isinstance(error, KeyError):
        key = error.args[0] if error.args else "a required field"
        return _ai_clean_text(f"The design is missing required field {key!s}.", 300)
    if isinstance(error, TypeError):
        return "The design has a value of the wrong type."
    if isinstance(error, ValueError):
        return _ai_plain_size_words(_ai_clean_text(str(error))) or "The design is not valid."
    return "The design could not be read as a Wavefinity bin design."


def _ai_bin_design(raw: Any) -> dict[str, Any]:
    """Canonical ordinary-bin design, or a safe ValueError."""
    if not isinstance(raw, dict):
        raise ValueError("The response has no design object.")
    box_raw = raw.get("box")
    b4b_raw = box_raw.get("b4b") if isinstance(box_raw, dict) else None
    if _is_base_trim_design(raw) or (isinstance(b4b_raw, dict) and b4b_raw.get("enabled")):
        raise ValueError("A Storage Box or Base Trim cannot be used as an AI bin design.")
    try:
        canonical = validate_design_payload({"design": raw})["design"]
    except Exception as error:  # every parse failure becomes one safe sentence
        raise ValueError(_ai_safe_message(error)) from None
    for feature in canonical["layout"]["features"]:
        if feature.get("kind") == "nest" or feature.get("contour") or feature.get("source_contour"):
            raise ValueError(
                "Photo Nest or traced outlines cannot come from an AI answer. "
                "Remove that part and add it in Wavefinity."
            )
    return canonical


def _ai_baseline_design(raw: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """(shape, checkable) for the open bin used by prompt generation.

    A Pegboard bin may legitimately be off the 7 mm grid.  Only that one check
    is relaxed here: ``checkable`` is the same design with width/depth rounded
    to the grid, used to measure the interior; ``shape`` keeps the real size.
    Every other baseline failure still raises as before.  Candidate proof
    (``_ai_bin_design``) is untouched and still enforces the grid.
    """
    try:
        shape = _ai_bin_design(raw)
        return shape, shape
    except ValueError:
        box = raw.get("box") if isinstance(raw, dict) else None
        snapped: dict[str, Any] = {}
        if isinstance(box, dict):
            for axis in ("x", "y"):
                value = _ai_num(box.get(axis))
                if value is None or not math.isfinite(value) or value <= 0:
                    continue
                units = value / GRID_PITCH
                if abs(units - round(units)) > 1e-6:
                    snapped[axis] = max(1, round(units)) * GRID_PITCH
        if not snapped:
            raise
        checkable = _ai_bin_design({**raw, "box": {**box, **snapped}})  # raises if anything else is wrong
        shape = json.loads(json.dumps(checkable))
        for axis in snapped:
            shape["box"][axis] = round(float(box[axis]), 3)
        return shape, checkable


def _ai_space_context(raw: Any) -> dict[str, Any]:
    """Only the user-relevant Space facts; nothing else from the browser."""
    if not isinstance(raw, dict) or raw.get("kind") not in AI_SPACE_KINDS:
        return {"typed_space": False}
    space: dict[str, Any] = {"typed_space": True, "kind": raw["kind"],
                             "grid": validate_grid(raw.get("grid", "wavefinity"))}
    # Fix 078: Drawer and Storage Box (current `portable`, legacy `box`) are a
    # hard vertical ceiling at their Space z; Surface and Pegboard are not.
    space["capped"] = raw["kind"] in ("drawer", "box", "portable", "storage_drawers")
    for axis in ("x", "y", "z"):
        value = raw.get(axis)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            space[f"{axis}_mm"] = round(float(value), 3)
    if raw["kind"] in ("portable", "box") and space["grid"] != "wavefinity":
        # Story 2975: a Gridfinity Storage Box is created with a Floor (its own
        # raised socket grid) or None (a plain cavity for the owner's baseplate).
        box = raw.get("storage_box") if isinstance(raw.get("storage_box"), dict) else {}
        chosen = raw.get("built_in_grid", box.get("built_in_grid", "floor"))
        space["floor"] = "external_plate" if chosen == "none" else "built_in"
        lift = box.get("seated_lift_mm")
        if space["floor"] == "external_plate" and isinstance(lift, (int, float)) \
                and not isinstance(lift, bool) and math.isfinite(lift) and lift >= 0:
            space["seated_lift_mm"] = round(float(lift), 3)
    if raw["kind"] == "storage_drawers" and space["grid"] != "wavefinity":
        cabinet = raw.get("storage_drawers") if isinstance(raw.get("storage_drawers"), dict) else {}
        chosen = raw.get("built_in_grid", cabinet.get("built_in_grid", "floor"))
        space["floor"] = "external_plate" if chosen == "none" else "built_in"
        from organizer_features.gridfinity import measured_seated_lift
        lift = measured_seated_lift(cabinet.get("seated_lift_mm", raw.get("seated_lift_mm")))
        if space["floor"] == "external_plate" and lift is not None:
            space["seated_lift_mm"] = lift
    if raw["kind"] == "surface" and isinstance(raw.get("trim_size"), str):
        space["trim_size"] = raw["trim_size"][:24]
    if raw["kind"] == "pegboard" and isinstance(raw.get("pegboard_standard"), str):
        space["pegboard_standard"] = raw["pegboard_standard"][:24]
    # The browser owns the Pegboard product minimums (the same ones New Bin uses).
    for key in ("min_x", "min_z"):
        value = raw.get(key)
        if raw["kind"] == "pegboard" and isinstance(value, (int, float))                 and not isinstance(value, bool) and math.isfinite(value) and value > 0:
            space[f"{key}_mm"] = round(float(value), 3)
    return space


def _capped_space_height(raw: Any) -> float | None:
    if not isinstance(raw, dict) or raw.get("kind") not in ("drawer", "portable", "box", "storage_drawers"):
        return None
    z = raw.get("z")
    return float(z) if isinstance(z, (int, float)) and not isinstance(z, bool) and math.isfinite(z) else None


def _ai_controlled_fields(space: dict[str, Any]) -> list[str]:
    kind = space.get("kind")
    if kind == "pegboard":
        return ["box.pegboard"]
    if kind == "surface":
        return ["box.base_thickness", "box.standard_base", "layout.surface_base_mode"]
    return []


def _ai_fingerprint(design: dict[str, Any], space: dict[str, Any]) -> str:
    text = json.dumps({"design": design, "space": space}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _ai_prompt_text(description: str, request_id: str, fingerprint: str,
                    context: dict[str, Any], manifest: dict[str, Any],
                    shape: dict[str, Any]) -> str:
    from organizer_engine._specs import grid_label

    def block(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    envelope = {
        "schema": AI_DESIGN_SCHEMA, "request_id": request_id,
        "context_fingerprint": fingerprint, "assumptions": [],
        "design": "<complete Wavefinity ordinary-bin design>",
    }
    # Fix 078: state the Space cap in plain language - do not expect the
    # outside AI to infer it merely from bin/Space dimensions.
    if context.get("typed_space"):
        z_mm = context.get("z_mm")
        cap_line = (
            f"- Active Space type: {context.get('kind')}. Hard object-height cap: {z_mm:g} mm - "
            "the full physical envelope of a Bore-held object, including tilt and width, must stay below this height."
            if context.get("capped") and isinstance(z_mm, (int, float))
            else f"- Active Space type: {context.get('kind')}. No hard vertical cap."
        )
    else:
        cap_line = "- No active typed Space. No hard vertical cap."
    container = "Storage Drawers cabinet" if context.get("kind") == "storage_drawers" else "Storage Box"
    if context.get("kind") == "storage_drawers":
        cap_line += (
            "\n- A Storage Drawers cabinet offers Wavefinity 7 mm, Gridfinity half 21 mm or Gridfinity 42 mm, "
            "one grid for every drawer. Gridfinity offers Floor (built-in raised pocket grid) or None "
            "(flat floor, clearanced for an owner-supplied baseplate). Both choices are immutable. "
            "Use pitch cells for bin width/depth and 7 mm height units for Gridfinity. The nominal grid "
            "field is distinct from the printed cavity. Gridfinity drawers have no side connectors or bin spacers. "
            "Return only an ordinary bin on the context grid; cabinet options are set in Wavefinity.")
    if context.get("floor") == "built_in":
        cap_line += (
            f"\n- This {container} uses {context.get('grid')} with a Floor: its own raised socket grid, so a bin seats "
            "in the container itself. Its Grid and Floor are fixed when the Space is created and are set in Wavefinity, "
            "not in the returned design; keep design.grid equal to the context grid.")
    elif context.get("floor") == "external_plate":
        lift = context.get("seated_lift_mm")
        cap_line += (
            f"\n- This {container} uses {grid_label(context.get('grid'))} with None: a flat floor and cavity for a baseplate the person supplies. "
            + (f"The baseplate's measured seated lift is {lift:g} mm. " if lift is not None
               else "The baseplate's seated lift is not measured, so height calculations cannot include it. ")
            + "Its Grid and Floor are fixed when the Space is created and are set in Wavefinity. The full seated stack, including measured lift, must fit the usable height; missing lift means the full seated height is unknown. These settings belong in Wavefinity, "
            "not in the returned design; keep design.grid equal to the context grid.")
    return "\n".join([
        "You are helping design ONE 3D-printable storage bin for the Wavefinity app.",
        "Read everything below. Ask the person questions if you need to. When you are",
        "sure, reply with the final answer exactly as described in RESPONSE CONTRACT.",
        "",
        "=== USER REQUEST ===",
        description,
        "=== END USER REQUEST ===",
        "",
        "=== HOW TO WORK ===",
        "- Browser AI Help uses the person's chosen provider and session key where browser access is permitted, or manual copy/paste. This prompt and its design/Space descriptors are shared with that provider; geometry, meshes and folder files remain on the PC. Never request or return API keys. Unsupported browsers offer temporary previews/downloads without Space autosave; recovery is the same site in Windows desktop Chrome/Edge with the original folder or a Space/preferences export. Browser handles/data do not transfer automatically.",
        "- Design exactly ONE object. If the request describes several, ask the person to narrow it to one BEFORE giving the final answer.",
        "- In the browser edition the person chooses the writable folder. Do not return local paths, folder handles, export URLs or preferences, or claim a design has been saved. Export prepares files locally for the chosen folder or a download (multiple downloaded files are together in a ZIP). Autosave requires granted folder access; folderless designs and imported recovery data need explicit export for a portable copy.",
        "- Browser drawer Print prepares a local 3MF for the person to open in Bambu Studio. Printed changes only after explicit confirmation for the same Space and unchanged design/inventory, never after saving or downloading alone. There is no persistent Prepared state. Never claim automatic slicer launch or set inventory print status in an AI design response.",
        "- If any critical measurement is missing, ambiguous, suspicious or has conflicting units, ASK the person first. Do not guess it and do not reinterpret the units they gave.",
        "- Width and depth must be whole cells of the selected grid pitch in the catalog-built CAPABILITY MANIFEST (7, 21 or 42 mm). Gridfinity height uses independent 7 mm units; Wavefinity height stays plain millimetres. The standalone editor offers these three grids; choose the grid there before requesting an AI design, then keep the context grid.",
        "- Grid selection is available for No-Space bins, Plain Drawers, Storage Box and Storage Drawers only. Space Grid is immutable. Storage Box and Storage Drawers also choose immutable Floor or None; Floor builds the raised socket floor, None leaves room for an owner-supplied baseplate. Nominal cells describe the field, not the printed cavity. Measured seated lift is the added seated height, not total plate thickness; zero is measured, missing lift is not recorded. Container settings stay in the Space, never BoxSpec. Side Openings are available on both Gridfinity pitches, with the foot/base, stacking rim, corner radii and selected minimum wall protected; illegal openings are refused without clipping or shrinking. Edge Mount is excluded on Gridfinity because it projects beyond the cell envelope. Physical fit is unverified. On ordinary 42 mm Gridfinity bins only, box.magnet_holes may be none (default) or 6x2 when requested; never use it on 21 mm, Wavefinity, or container floors.",
        "- Storage Box grid_stacking is a structural Space option, never an ordinary AI bin result: Gridfinity 21/42 mm, Lid Only from 1x1 cells or latched screw-hinge lids with one or two latches (42 mm from 2x2; 21 mm from 3x3). Piano hinges, zero-latch latched lids, top labels and peg stacking are refused. Fit, closure, mating and flipped-lid barrel print quality remain unverified pending Andrew's recorded prints; remove the upper box before opening. Do not return the case or alter these Space settings.",
        "- Ordinary 21 mm and 42 mm Gridfinity bins have box.hollow_base on by default; set it false if solid feet and base are requested. It has no effect on Wavefinity bins or container floors. Physical print performance is unverified.",
        "- Ordinary Gridfinity bins may set box.corner_feet=true when requested (default false). Only corner cells have feet and magnet pockets; built-in wavy supports trimmed to the standard foot outline carry the floor of the other cells, so the bin still seats in a baseplate and needs no slicer supports. On bins up to two cells each way, Corners only changes nothing because every cell already has a foot. box.hollow_base controls whether the corner feet are hollow. Wavefinity bins ignore this option.",
        "- Third-party stand-ins are external bins recorded in the Space Inventory for layout only. AI Design does not create or change stand-ins; it returns ordinary bins.",
        "- All values in the design are millimetres. Convert nothing silently; ask if unsure.",
        "- You may use any legal part, option or modifier in the CAPABILITY MANIFEST that best solves the request.",
        "- Parts marked recommend_only (for example Photo Nest) may be suggested to the person but must NEVER appear in the returned design.",
        "- Interior part zones are [x0,y0,x1,y1] in mm from the bin centre. current_baseline_layout_bounds_mm is only the interior of the CURRENT bin size. If you change box.x/box.y/box.z, the legal interior changes with it (each axis keeps about interior_margin_mm of shell in total): every zone you return must fit inside the interior of the design you RETURN, not the old one. Adjust the example zones, counts and sizes to the real item.",
        "- Keep every field listed in space_controlled_fields exactly as it is in the current design.",
        "- Keep design.grid equal to the context grid (wavefinity, gridfinity_half, or gridfinity). A missing grid inherits this context; a conflicting grid is refused. Gridfinity offers Stackable rim (box.stack.mode direct; off is none) and loose plain plate lids or stacking-socket lids (box.lid.enabled; box.lid.stack_rim) on both pitches: closed Z is nominal in whole 7 mm units with a 14 mm minimum, the body and interior shorten by the lid rise, and lids need at least two height units plus enough remaining body clearance for the floor and lid. Stack only the same footprint and pitch; lid-on-lid uses the standard rim seat descent. Hinged, label and handle lids are Wavefinity options and unavailable on grid bodies. Physical grid-lid fit is not yet print-confirmed.",
        cap_line,
        "- design.part_name must be a short, descriptive, non-blank name (1-80 characters) for what the bin holds - for example \"Lipstick\" or \"Hex Drivers\", never a generic \"Bin\" or dimensions-only text. Existing Inventory names, when supplied below, are advisory: avoid an obvious duplicate, but Wavefinity enforces final uniqueness itself, so do not invent your own numbering suffix.",
        "- A design may contain at most one rim Label in total, not one per rim side.",
        "- Bore: when Base - Straight Walls vs Base - Wavy Walls, or Straight Walls Only vs Wavy Walls Only, are otherwise equally suitable, prefer the wavy one. Choose the correct structural family (Base vs Walls Only) first; never switch families merely to get \"wavy\".",
        "- Bore: an object's length, its insertion depth (Base styles: options.depth; Walls Only: options.walls_depth), and the bin's own height are three different numbers - do not set the insertion depth equal to the object's full length just because that is the length you were given. For an upright hand-retrieved object, plan for roughly 30 mm of it to remain grippable above the bin rim; in a capped Space (see above) this preference never overrides the hard cap.",
        "- Bore angle: the Designer's user-facing \"Bore angle\" runs 90 (upright) down to 20 (steepest lean). This JSON's canonical options.angle is the same lean measured the other way: 0 (upright) up to 70 (steepest) - displayed_bore_angle = 90 - options.angle. When you lean a Bore with no object-specific reason for a direction, prefer options.angle_towards \"back\", or the side opposite the design's one rim Text's rim_side if the design has one.",
        "",
        "=== WAVEFINITY CONTEXT (JSON) ===",
        block(context),
        "",
        "=== CANONICAL DESIGN SHAPE (JSON; the current bin, a complete design) ===",
        block(shape),
        "",
        "=== CAPABILITY MANIFEST (JSON) ===",
        block(manifest),
        "",
        "=== OPTIONAL BACKGROUND (only if you can fetch web pages) ===",
        f"{ai_feature_reference_url()} explains these features in plain language. Everything above is",
        "already the exact current data for this request, so use that page only for background; if you",
        "cannot access it, ignore it and proceed. When it and this prompt ever disagree, the data above",
        "wins - the page can be newer than this running copy of Wavefinity.",
        "",
        "=== RESPONSE CONTRACT ===",
        "Your FINAL answer is exactly one JSON object and nothing else - no text before or after it:",
        block(envelope),
        f"- \"schema\" must be exactly \"{AI_DESIGN_SCHEMA}\".",
        f"- Copy \"request_id\" (\"{request_id}\") and \"context_fingerprint\" (\"{fingerprint}\") exactly.",
        "- \"design\" is a COMPLETE Wavefinity ordinary-bin design like the canonical shape - not a patch and not a list of UI steps.",
        "- \"assumptions\" may list only harmless, non-critical assumptions. It is never permission to invent critical dimensions.",
        "- Do not invent Photo Nest contour or photo data.",
        "- A single markdown ```json fence around the object is tolerated; prose around it is not.",
    ])


def _ai_num(value: Any) -> float | None:
    """Coerce a JSON-decoded value to float, or None when that is not sound."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _ai_item_profile_violation(kind: str, item: Any) -> str | None:
    """Item-profile defects a canonically valid design can still carry.

    Runs on the raw item dict, before canonicalization can round an odd hex-bit
    length/clearance into something that merely builds without complaint - the
    real bore/cradle geometry ignores a hex-bit item's own numbers entirely and
    always builds the fixed preset, so a wrong value would otherwise reach an
    accepted design silently instead of being rejected.
    """
    if not isinstance(item, dict):
        return None
    profile = item.get("profile", "round")
    definition = FEATURE_DEFINITIONS.get(kind)
    allowed = definition.item_profiles if definition else ()
    if allowed and profile not in allowed:
        return f"a {kind} may only use item profile {' / '.join(allowed)}, not {profile!r}"
    if kind == "cradle":
        if profile != "round":
            return "a cradle's item profile must be 'round'"
        if _ai_num(item.get("clearance")) != 0.0:
            return "a cradle's item clearance must be 0"
        return None
    if kind == "bore":
        fixed = HEX_BIT_FIXED.get(profile)
        if fixed is None:
            if _ai_num(item.get("clearance")) != BORE_CLEARANCE:
                return f"a bore item's clearance must be exactly {BORE_CLEARANCE:g}"
            return None
        segments = item.get("segments")
        segment = segments[0] if isinstance(segments, list) and len(segments) == 1 else None
        ok = (
            segment is not None
            and _ai_close(item.get("clearance"), fixed["clearance_mm"])
            and _ai_close(segment.get("length"), fixed["length_mm"])
            and _ai_close(segment.get("diameter"), fixed["diameter_mm"])
        )
        if not ok:
            return (
                f"{profile} must use exactly the fixed preset: one segment "
                f"{{length: {fixed['length_mm']:g}, diameter: {fixed['diameter_mm']:g}}}, "
                f"clearance {fixed['clearance_mm']:g}"
            )
    return None


def _ai_close(value: Any, target: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value - target) < 1e-6


def _ai_semantic_violation(raw: Any) -> str | None:
    """Reject-with-repair defects the canonical/geometry validators would not
    themselves catch: an AI answer that uses a field this Fix's manifest never
    offered as a configurable control, or an item that violates its feature's
    fixed rules. Runs on the raw candidate, before canonicalization can erase or
    mask the conflict (Fix 073 Correction 3).
    """
    if not isinstance(raw, dict):
        return None
    # Fix 078: the AI must return a short, descriptive, non-blank bin name -
    # Wavefinity normalizes/dedupes it on adoption, but a missing or garbled
    # name is the AI's own answer defect and is repairable like any other.
    part_name = raw.get("part_name")
    if not isinstance(part_name, str) or not part_name.strip():
        return "design.part_name must be a short, non-blank name describing the bin's intended contents"
    if len(part_name.strip()) > 80:
        return "design.part_name must be 80 characters or fewer"
    features = raw.get("layout", {}).get("features") if isinstance(raw.get("layout"), dict) else None
    if not isinstance(features, list):
        return None
    rim_text_count = 0
    for feature in features:
        if not isinstance(feature, dict):
            continue
        kind = feature.get("kind")

        options = feature.get("options") if isinstance(feature.get("options"), dict) else {}
        if kind == "text" and options.get("level") == "rim":
            rim_text_count += 1
            # Fix 078: a design may contain at most one rim Text total.
            if rim_text_count > 1:
                return "a design may contain at most one rim Label; remove the extra rim Label"
        violation = _ai_item_profile_violation(kind, feature.get("item"))
        if violation:
            return violation
        if kind == "bore":
            profile = feature.get("item", {}).get("profile") if isinstance(feature.get("item"), dict) else None
            if profile in HEX_BIT_FIXED and (_ai_num(options.get("angle")) or 0.0) != 0.0:
                return f"{profile} stands upright; its angle must be 0, not editable by lean"
        if kind == "steps" and "count" in options:
            return "a Steps part's Number of steps is top-level feature.count, not options.count"
        if kind == "post" and ("count_x" in options or "count_y" in options):
            return "a Post part's layout is top-level feature.count/along, not options.count_x/count_y"
        if kind == "divider" and feature.get("count") is not None:
            return "a Divider's grid is options.count_x/options.count_y, not top-level feature.count"
    return None


def ai_repair_prompt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    request_id = payload.get("request_id")
    fingerprint = payload.get("context_fingerprint")
    if not isinstance(request_id, str) or not isinstance(fingerprint, str) \
            or not request_id or not fingerprint:
        raise ValueError("A repair prompt needs the original request and fingerprint.")
    response = payload.get("response")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("There is no response to repair.")
    error = _ai_clean_text(str(payload.get("error") or "")) or "The answer was not valid."
    prompt = "\n".join([
        "Your previous Wavefinity answer could not be used. Fix it and answer again.",
        "",
        f"schema: {AI_DESIGN_SCHEMA}",
        f"request_id: {request_id}",
        f"context_fingerprint: {fingerprint}",
        "",
        "=== PROBLEM ===",
        error,
        "",
        "=== YOUR PREVIOUS ANSWER ===",
        response.strip()[:AI_MAX_RESPONSE],
        "=== END PREVIOUS ANSWER ===",
        "",
        f"(Background, optional: {ai_feature_reference_url()} - only if you can fetch it; the exact",
        "schema/request/fingerprint/error above are authoritative either way.)",
        "",
        "Return exactly ONE corrected JSON object and nothing else. It must keep",
        f"\"schema\": \"{AI_DESIGN_SCHEMA}\", the same request_id and context_fingerprint,",
        "and a complete Wavefinity ordinary-bin \"design\" that fixes the problem above.",
    ])
    return {"prompt": prompt}


# Shared canonical payloads; callers supply saved-record, catalog and preview
# owners so browser code never imports the HTTP server or its filesystem state.
import secrets
from organizer_app import LABEL_POSITIONS, base_height
from organizer_inserts import layout_zone
from organizer_inserts._bore import bore_reference_top
from ._runtime import _interior_work_box
from ._designs._preview import _design
from ._designs._features import default_feature_payload

def ai_capability_manifest(grid: str = "wavefinity", *, catalog_payload) -> dict[str, Any]:
    """The AI's authoritative list of what it may put in a design.

    Everything is read from the catalog, the feature registry, rule constants and
    the canonical serializer - there is no second copy of any range or choice.
    """
    catalog = catalog_payload()
    grid_rules = next(row for row in catalog["grids"] if row["value"] == grid)
    base = _ai_example_base()
    features: list[dict[str, Any]] = []
    for part in catalog["parts"]:
        if not part["palette_visible"] or "box_modifier" in part["capabilities"]:
            continue
        entry: dict[str, Any] = {
            "kind": part["kind"], "title": part["title"],
            "description": part["description"],
            "capabilities": part["capabilities"],
        }
        if any(cap in AI_MEDIA_CAPABILITIES for cap in part["capabilities"]):
            entry["ai"] = "recommend_only"
            entry["reason"] = AI_MEDIA_REASON
        else:
            entry["ai"] = "configurable"
            starter = default_feature_payload({"design": base, "kind": part["kind"]})
            labels = {one["key"]: one["label"] for one in part["fields"]}
            entry["options"] = [
                {**option, **({"label": labels[option["key"]]} if option["key"] in labels else {}),
                 "legal_values": _ai_legal_values(option)}
                for option in part["options"]
                if not option.get("internal") and not option.get("legacy")
            ]
            entry["generic_fields"] = _ai_generic_fields(part, starter["feature"], catalog["item_rules"])

            # What Wavefinity fills in for a blank option in the example bin.
            entry["resolved_defaults"] = starter["resolved_options"]
            entry["example"] = starter["feature"]
        features.append(entry)
    examples = _ai_modifier_examples()
    modifier_examples = {
        "accent_band": examples["accent_band"],
        "lid_stacking": {
            "stackable_bin": examples["stackable_bin"],
            "lid_with_handle": examples["lid_with_handle"],
        },
        "inside_handles": examples["inside_handles"],
        "side_openings": examples["side_openings"],
        "edge_mount": examples["edge_mount"],
    }
    modifier_rules = {
        "accent_band": _ACCENT_BAND_RULES,
        "lid_stacking": {
            "lid_rules": catalog["lid_rules"], "stack_rules": catalog["stack_rules"],
        },
        "inside_handles": {"lift_grabbers": catalog["lift_grabbers"]},
        "side_openings": {"side_openings": catalog["side_openings"]},
        "edge_mount": {"edge_mount": catalog["edge_mount"]},
    }
    modifiers = [
        {
            "kind": kind, "title": title, "description": description,
            "design_paths": list(paths), "ai": "configurable",
            "rules": modifier_rules[kind], "example": modifier_examples[kind],
        }
        for kind, title, description, paths in AI_MODIFIER_BLOCKS
    ]
    if grid != "wavefinity":
        modifiers = [row for row in modifiers if row["kind"] != "edge_mount"]
        openings = next(row for row in modifiers if row["kind"] == "side_openings")
        openings["rules"] = {"side_openings": catalog["side_openings"], "grid": grid_rules}
        openings["example"] = {"side_openings": {"enabled": True, "shape": "square",
                              "sides": ["front"], "size": "small", "percent_mode": "inset_v2",
                              "from_bottom_percent": 0, "from_top_percent": 0}}
        stacking = next(row for row in modifiers if row["kind"] == "lid_stacking")
        stacking.update(
            description="Stackable rim: box.stack.mode=direct without a lid; or Gridfinity Lid, optionally with stack_rim=true. No hinged, handle or label variants; no side connectors. All heights use whole 7 mm units.",
            rules={"grid": grid_rules},
            example={"stackable_rim": {"box.stack": {"mode": "direct"}},
                     "grid_lid": {"box.lid": {"enabled": True, "stack_rim": True,
                                                "flip_enabled": False, "handle_enabled": False,
                                                "label_enabled": False}}})
    return {
        "features": features,
        "box_modifiers": modifiers,
        "bin_controls": {
            "grid_choices": catalog["grids"],
            "active_grid": grid_rules,
            "units_are": "millimetres",
            "base_unit_mm": grid_rules["pitch_mm"],
            "max_box_size_mm": catalog["max_box_size"],
            "min_height_above_base_mm": catalog["min_height_above_base_mm"],
            "ordinary_bin_min_height_mm": catalog["drawer_rules"]["ordinary_bin_min_height_mm"],
            "wall_rules": catalog["wall_rules"],
            "base_rules": catalog["base_rules"],
            "scoop_rules": catalog["scoop_rules"],
            "layout_modes": catalog["modes"],
            "label_positions": list(LABEL_POSITIONS),
            "design_fields": {
                "grid": "the selected context grid from grid_choices; choose it in the standalone editor before AI Design",
                "box.x / box.y": "footprint, whole multiples of base_unit_mm",
                "box.z": "height in whole millimetres" if grid == "wavefinity" else "height in whole 7 mm units, satisfying the floor/rim/lid minimum",
                "box.wall / box.base_thickness": "use the wall_rules / base_rules choices",
                "box.magnet_holes": {
                    "type": "string",
                    "choices": list(GRIDFINITY_MAGNET_HOLE_CHOICES),
                    "default": DEFAULT_MAGNET_HOLES,
                    "available_on_grids": ["gridfinity"],
                    "rules": "ordinary 42 mm Gridfinity bins only; never on 21 mm, Wavefinity, or container floors",
                },
                "box.hollow_base": {
                    "type": "boolean",
                    "default": DEFAULT_HOLLOW_BASE,
                    "available_on_grids": ["gridfinity", "gridfinity_half"],
                    "rules": "ordinary 21 mm and 42 mm Gridfinity bins only (true = hollow feet and base, false = solid); ignored on Wavefinity and container floors",
                },
                "box.corner_feet": {
                    "type": "boolean",
                    "default": DEFAULT_CORNER_FEET,
                    "available_on_grids": ["gridfinity", "gridfinity_half"],
                    "rules": "ordinary 21 mm and 42 mm Gridfinity bins only (true = corner-cell feet only with built-in wavy floor supports; on bins up to two cells each way, every cell already has a foot so this changes nothing); ignored on Wavefinity",
                },
                "scoop": "true adds the front finger scoop (also available as an interior part)",
                "label / label_position": "rim ledge label text and its side",
                "part_name": "the bin name",
            },
        },
        "setting_interactions": catalog["setting_interactions"],
        "space_restrictions": {
            "drawer": "X/Y must fit the drawer opening in whole base units; height must not exceed the drawer height.",
            "box": "Height must not exceed the Space height; X/Y must fit the Space.",
            "portable": "Height must not exceed the Space height; X/Y must fit the Space.",
            "storage_drawers": "The Space values are the selected physical drawer's usable X/Y/height; the bin must fit inside it. Never design or return cabinet structure.",
            "surface": "Base thickness and base mode are Space-controlled; keep them exactly as given.",
            "pegboard": "Keep box.pegboard exactly as given (it is the Space's mounting); stay at or above the pegboard minimum height.",
            "pegboard_rules": catalog["pegboard_rules"],
        },
        "never_offer": [
            "Storage Box designs (box.b4b) or Base Trim designs (design_kind = base_trim)",
            "Photo Nest / traced contours (recommend only)",
            "hidden, internal or legacy-only part kinds (including Pocket)",
        ],
    }


def ai_prompt_payload(payload: dict[str, Any], *, read_inventory, catalog_payload) -> dict[str, Any]:
    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Describe the object first.")
    description = description.strip()
    if len(description) > AI_MAX_DESCRIPTION:
        raise ValueError(f"Keep the description under {AI_MAX_DESCRIPTION} characters.")
    _current, stored_space = read_inventory(payload)
    from wavefinity_web_impl._ai import ai_context_grid
    context_grid = _editor_context_grid(payload, stored_space)
    stored_space = _ai_grid_space(payload, _current, stored_space)
    design, checkable = _ai_baseline_design(ai_context_grid(payload.get("design"), context_grid))
    space = _ai_space_context(stored_space)
    space["grid"] = context_grid
    request_id = "wf-ai-" + secrets.token_hex(6)
    fingerprint = _ai_fingerprint(design, space)
    box, layout, *_ = _design(checkable)
    bounds = layout_zone(box, layout.mode)
    # Fix 078: existing Inventory names are advisory context only for the
    # prompt, so they are added after the fingerprint - an unrelated
    # Inventory change must not make an otherwise-current prompt go stale.
    raw_names = payload.get("existing_names")
    existing_names = [str(name).strip()[:80] for name in raw_names
                       if isinstance(name, str) and name.strip()][:200] if isinstance(raw_names, list) else []
    context = {
        **space,
        "space_controlled_fields": _ai_controlled_fields(space),
        "current_baseline_layout_bounds_mm": [bounds.x0, bounds.y0, bounds.x1, bounds.y1],
        "interior_margin_mm": [round(box.x - bounds.width, 3), round(box.y - bounds.depth, 3)],
        "base_unit_mm": next(row["pitch_mm"] for row in catalog_payload()["grids"] if row["value"] == context_grid),
        "existing_bin_names": existing_names,
    }
    prompt = _ai_prompt_text(
        description, request_id, fingerprint, context, ai_capability_manifest(context_grid, catalog_payload=catalog_payload), design)
    return {"request_id": request_id, "context_fingerprint": fingerprint, "prompt": prompt}


def ai_candidate_payload(payload: dict[str, Any], *, read_inventory, preview_payload) -> dict[str, Any]:
    """Prove an AI design in the real geometry path without changing anything.

    A semantic preflight against the manifest's public-control contract runs
    first, on the raw candidate, then canonical validation, structural/media
    rejection, and finally the exact preview owner. The preview rides its own
    client lane so it can never supersede, or be superseded by, the Designer's
    own preview requests.
    """
    violation = _ai_semantic_violation(payload.get("design"))
    if violation:
        raise ValueError(f"That design is not legal: {violation}.")
    from wavefinity_web_impl._ai import ai_context_grid
    _current, stored_space = read_inventory(payload)
    candidate = ai_context_grid(payload.get("design"), _editor_context_grid(payload, stored_space))
    stored_space = _ai_grid_space(payload, _current, stored_space)
    canonical = _ai_bin_design(candidate)
    request: dict[str, Any] = {"design": canonical}
    if isinstance(payload.get("client_id"), str):
        request["client_id"] = payload["client_id"]
        request["generation"] = payload.get("generation")
    try:
        preview = preview_payload(request)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(_ai_safe_message(error)) from None
    if preview.get("superseded"):
        return {"superseded": True}
    problems = [
        text for text in (
            preview.get("message"), *preview.get("feature_errors", []), preview.get("draft_error"),
        ) if text
    ]
    if not preview.get("fits") and not problems:
        problems.append("The design does not fit.")
    if not problems:
        cap_problem = _ai_space_cap_violation(preview["design"], stored_space)
        if cap_problem:
            problems.append(cap_problem)
    return {"design": preview["design"], "preview": preview, "problems": problems}


def _capped_bore_violation(
    box: BoxSpec, layout: Layout, features: list[Feature] | tuple[Feature, ...], cap_z: float,
) -> tuple[int, float] | None:
    """Evaluate Bore objects against the same physical body used by preview."""
    physical_box = _interior_work_box(box)
    base_z = base_height(physical_box, layout.mode)
    for index, feature in enumerate(features):
        if feature.kind != "bore" or feature.item is None:
            continue
        try:
            top = bore_reference_top(physical_box, feature, base_z)
        except (KeyError, TypeError, ValueError):
            continue
        if top > cap_z + 1e-6:
            return index, top
    return None


def _ai_space_cap_violation(design: dict[str, Any], raw_space: Any) -> str | None:
    """Fix 078: in a capped Space (Drawer/Storage Box), no Bore-held object's
    highest point may exceed the Space's own ``z`` - a hard legality rule, not
    merely the ~30 mm grip preference. Uncapped Spaces (Surface/Pegboard) and
    no active Space never gain an artificial ceiling here.
    """
    space = _ai_space_context(raw_space)
    if not space.get("capped"):
        return None
    cap_z = _capped_space_height(raw_space)
    if cap_z is None:
        return None
    try:
        box, layout, *_ = _design(design)
    except (KeyError, TypeError, ValueError):
        return None
    violation = _capped_bore_violation(box, layout, layout.features, cap_z)
    if violation is not None:
        _index, object_top_z = violation
        return (
            f"a Bore-held object's top would reach {object_top_z:.3f} mm, above this "
            f"capped Space's {cap_z:.3f} mm ceiling; use a shorter bin and/or a shallower "
            "insertion depth so useful grip stays below the cap"
        )
    return None


def _editor_context_grid(payload: dict, space: dict | None) -> str:
    from organizer_engine._specs import validate_grid
    if isinstance(space, dict):
        return validate_grid(space.get("grid", "wavefinity"))
    if isinstance(payload.get("space"), dict) and payload["space"].get("kind"):
        raise ValueError("Open the saved Space before generating an AI bin for it.")
    return validate_grid(payload.get("editor_grid", payload.get("grid", "wavefinity")))


def _ai_grid_space(payload: dict, current: dict, space: dict | None) -> dict | None:
    if not isinstance(space, dict):
        return None
    result = dict(space)
    if space.get("kind") == "storage_drawers":
        from organizer_storage.drawers import storage_drawers_active_limits
        result.update(storage_drawers_active_limits(space, (current.get("layout") or {}).get("active")))
    if space.get("kind") == "pegboard" and isinstance(payload.get("space"), dict):
        # Existing board-specific starter hints are independent of grid identity.
        result.update({key: payload["space"][key] for key in ("min_x", "min_z") if key in payload["space"]})
    return result


