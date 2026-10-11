"""Wavefinity web AI Design schema, prompt and candidate helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from typing import Any
from organizer_inserts import FEATURE_DEFINITIONS
from organizer_inserts._bore import BORE_CLEARANCE, HEX_BIT_FIXED

from ._runtime import default_design
from ._designs import _is_base_trim_design, validate_design_payload


# ---------------------------------------------------------------- AI Help (Fix 073)
#
# Wavefinity never calls an AI provider. This section only builds the prompt a
# person pastes into any outside AI, and proves a pasted answer is a legal
# ordinary bin before the browser installs it. Nothing here is stored: the
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
AI_MODIFIER_BLOCKS = (
    ("lid_stacking", "Lid & Stacking",
     "Choose ONE of three configurations (see example): Stackable Bin "
     "(box.stack = {\"mode\": \"direct\"}, no box.lid), Stackable Lid (box.lid with "
     "stackable=true; its label style is forced to flush) or Lid with Handle "
     "(box.lid with stackable=false, handle_type/size/position). "
     "Never combine a lid with direct stacking.",
     ("box.lid", "box.stack")),
    ("inside_handles", "Inside Grip",
     "A finger grip inside the bin (box.lift_grabbers).", ("box.lift_grabbers",)),
    ("side_openings", "Side Openings",
     "Finger-access cutouts through selected walls (box.side_openings).",
     ("box.side_openings",)),
    ("edge_mount", "Edge Mount",
     "A label and/or screw mounting on one outside edge (box.edge_mount). "
     "Include the block only when the edge mount is wanted.",
     ("box.edge_mount",)),
)
_AI_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"']*|(?:/[\w.\-]+){2,}")


def _ai_example_base() -> dict[str, Any]:
    """A roomy blank bin, so every example part and modifier is legal in it."""
    design = default_design()
    design["box"].update({"x": 64.0, "y": 64.0, "z": 60.0})
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
            **({"note": "Dividers are normally set with options.count_x / options.count_y; leave count null."}
               if kind == "divider" else
               {"note": "Posts may instead use options.count_x / options.count_y for a grid."}
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
        "lid_with_handle": {"lid": {"enabled": True}},
        "stackable_lid": {"lid": {"enabled": True, "stackable": True}},
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


def _ai_safe_message(error: BaseException) -> str:
    if isinstance(error, KeyError):
        key = error.args[0] if error.args else "a required field"
        return _ai_clean_text(f"The design is missing required field {key!s}.", 300)
    if isinstance(error, TypeError):
        return "The design has a value of the wrong type."
    if isinstance(error, ValueError):
        return _ai_clean_text(str(error)) or "The design is not valid."
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


def _ai_space_context(raw: Any) -> dict[str, Any]:
    """Only the user-relevant Space facts; nothing else from the browser."""
    if not isinstance(raw, dict) or raw.get("kind") not in AI_SPACE_KINDS:
        return {"typed_space": False}
    space: dict[str, Any] = {"typed_space": True, "kind": raw["kind"]}
    # Fix 078: Drawer and Storage Box (current `portable`, legacy `box`) are a
    # hard vertical ceiling at their Space z; Surface and Pegboard are not.
    space["capped"] = raw["kind"] in ("drawer", "box", "portable", "storage_drawers")
    for axis in ("x", "y", "z"):
        value = raw.get(axis)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            space[f"{axis}_mm"] = round(float(value), 3)
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
        "- Design exactly ONE object. If the request describes several, ask the person to narrow it to one BEFORE giving the final answer.",
        "- If any critical measurement is missing, ambiguous, suspicious or has conflicting units, ASK the person first. Do not guess it and do not reinterpret the units they gave.",
        "- All values in the design are millimetres. Convert nothing silently; ask if unsure.",
        "- You may use any legal part, option or modifier in the CAPABILITY MANIFEST that best solves the request.",
        "- Parts marked recommend_only (for example Photo Nest) may be suggested to the person but must NEVER appear in the returned design.",
        "- Optional reference_object {width, depth, height} is only for Pocket, Post, Slot and Steps. It is a preview/planning envelope, never holder geometry. Include it only when the person supplied or confirmed all three measurements; never invent them. Bore and Cradle use their existing item instead.",
        "- Interior part zones are [x0,y0,x1,y1] in mm from the bin centre. current_baseline_layout_bounds_mm is only the interior of the CURRENT bin size. If you change box.x/box.y/box.z, the legal interior changes with it (each axis keeps about interior_margin_mm of shell in total): every zone you return must fit inside the interior of the design you RETURN, not the old one. Adjust the example zones, counts and sizes to the real item.",
        "- Keep every field listed in space_controlled_fields exactly as it is in the current design.",
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
        if feature.get("reference_object") is not None and kind not in {"pocket", "post", "slot", "steps"}:
            return f"reference_object is not an AI-configurable field for {kind}"
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
