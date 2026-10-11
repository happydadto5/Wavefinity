"""Wavefinity interior-part summaries, inventory records and design (de)serialization."""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
from typing import Iterable
from organizer_engine import (
    B4BSpec,
    BoxSpec,
    EdgeMountSpec,
    EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM,
    LidSpec,
    StackSpec,
    LiftGrabberSpec,
    SideOpeningSpec,
    DEFAULT_WALL,
    B4B_DEFAULT_BASE,
    B4B_DEFAULT_WALL,
    GRID_PITCH,
    MAX_WALL,
    MIN_WALL,
    TEXT_CAP_HEIGHT_IDEAL,
    TEXT_DEPTH,
    WAVE_AMPLITUDE,
    WAVE_MATING_GAP,
    lid_enabled,
    lid_label_relief_mm,
    lid_spec,
    lid_stackable,
    max_wave_slope,
)
from organizer_side_openings import SIDE_OPENING_TOP_BRIDGE_MM, validate_side_openings
from organizer_pegboard import normalise_mount_spec, receiver_layout
from organizer_b4b import b4b_effective_box, b4b_summary, validate_b4b_design
from organizer_stack import (
    normalize_stack_settings,
    stack_closed_height,
    stack_effective_box,
    stack_enabled,
    stack_step_depth,
)
from organizer_inserts import (
    BASE_PLATE,
    CARTRIDGE_PITCH,
    CONNECTOR_EDGE_KEEP_OUT,
    EDITOR_SNAP,
    FEATURE_BUILDERS,
    HEX_BIT_HOLD,
    TEXT_KIND,
    _cradle_rib_thickness,
    LIBRARY,
    MIN_FEATURE_GAP,
    Feature,
    Item,
    Layout,
    Zone,
    normalize_bore_modes,
    build_features,
    is_text,
    layout_from_dict,
    layout_to_dict,
    layout_zone,
    fitted_nest_feature,
    normalize_divider_scoop,
    resolve_text_features,
    resolved_options,
    snapped_zone,
    scoop_zone,
    text_fitted,
    text_of,
)

from ._common import label_position, clean_label, base_height, _canonical_rim_label
from ._preview import _customization_zones
from ._filenames import box_filename


def _b4b_log_note(summary: dict) -> str:
    cx, cy = summary["capacity_units"]
    bits = [f"Storage Box {cx}x{cy} units"]
    if summary["lid"]:
        bits.append("secure lid" if summary["secure_lid"] else "passive lid")
    else:
        bits.append("no lid")
    if summary["secure_lid"]:
        # Latch count and hardware family are both derived from the case now,
        # so report what was resolved rather than a setting nobody chose.
        count = summary["latch_count"]
        bits.append(
            f"{count} latch" if count == 1 else f"{count} latches"
        )
        family = summary.get("hardware_family")
        if family:
            bits.append(f"{family} hardware")
        bom = summary.get("hardware_bom", [])
        if bom:
            bits.append("; ".join(bom))
    if summary["stacking"]:
        bits.append("stacking")
    if summary["label_location"] != "none":
        bits.append(f"{summary['label_location']} label")
    return ", ".join(bits)


def summarize_interior_parts(layout: Layout, scoop: bool = False) -> str:
    """Return a short human-readable description of interior parts for logging."""
    counts: dict[str, int] = {}
    for feature in layout.features:
        kind = getattr(feature, "kind", "part")
        if kind == "divider":
            name = "Full-span Divider" if getattr(feature, "full_span", False) else "Divider"
        elif kind == "cradle":
            item = getattr(feature, "item", None)
            name = f"Cradle ({item.name})" if item and getattr(item, "name", None) else "Cradle"
        elif kind == "nest":
            opts = getattr(feature, "options", {}) or {}
            is_photo = bool(opts.get("photo") or getattr(feature, "contour", None) is not None)
            name = "Photo Nest" if is_photo else "Nest"
        elif kind == "pocket":
            name = "Pocket"
        elif kind == "bore":
            name = "Bore"
        elif kind == "slot":
            name = "Slot"
        elif kind == "steps":
            name = "Steps"
        elif kind == "post":
            name = "Post"
        elif kind == "text":
            opts = getattr(feature, "options", {}) or {}
            txt = str(opts.get("text", "")).strip()
            if opts.get("level") == "rim":
                continue  # Shell lettering, not part of the removable insert.
            name = f'Text ("{txt}")' if txt else "Text"
        else:
            name = kind.capitalize()
        counts[name] = counts.get(name, 0) + 1

    parts: list[str] = []
    for name, cnt in counts.items():
        if cnt > 1:
            parts.append(f"{cnt}x {name}")
        else:
            parts.append(name)
    if scoop:
        parts.append("Scoop")

    return ", ".join(parts) if parts else "None"


def inventory_bin_record(
    box: BoxSpec,
    layout: Layout,
    generated_files: list[Path] | None = None,
    label: str = "",
    part_name: str = "",
    scoop: bool = False,
    b4b_note: str = "",
    physical_size_mm: tuple[float, float, float] | None = None,
) -> dict[str, object]:
    """Build the one inventory row used by local and browser-owned folders.

    ``physical_size_mm`` lets a caller override the printed physical
    footprint reported for space/drawer planning - a Storage Box case's real
    assembled envelope, not its child-bin field - without touching ``box``.
    Ordinary bins continue using ``box.x/y/z`` when no override is supplied.
    """
    b4b_stack_mode = None
    if box.b4b.enabled:
        b4b_stack_mode = "b4b" if box.b4b.stacking else "none"
        if not b4b_note:
            b4b_summary_data = b4b_summary(box)
            b4b_note = _b4b_log_note(b4b_summary_data)
            if physical_size_mm is None:
                envelope = b4b_summary_data["assembled_envelope_mm"]
                physical_size_mm = (envelope[0], envelope[1], envelope[2])
            box = b4b_effective_box(box)
            layout = Layout((), "fused", EDITOR_SNAP)
    if generated_files:
        file_names = ", ".join(dict.fromkeys(p.name for p in generated_files))
    else:
        file_names = box_filename(box, part_name)

    tidy_label = clean_label(label)
    text_labels = [
        f"{str(f.options.get('text')).strip()} ({'rim ' + str(f.options.get('rim_side') or 'back') if f.options.get('level') == 'rim' else 'base'})"
        for f in layout.features
        if getattr(f, "kind", "") == "text" and str(f.options.get("text", "")).strip()
    ]
    if tidy_label and not any(f.options.get("level") == "rim" for f in layout.features if f.kind == "text"):
        # An old top-level rim label: plain when alone, tagged beside other Text.
        text_labels.insert(0, f"{tidy_label} (rim)" if text_labels else tidy_label)
    label_text = ", ".join(text_labels) if text_labels else "-"

    interior_text = b4b_note or summarize_interior_parts(layout, scoop=scoop)

    if physical_size_mm is not None:
        phys_x, phys_y, phys_z = physical_size_mm
    else:
        phys_x, phys_y, phys_z = box.x, box.y, box.z
        if lid_enabled(box) and not lid_stackable(box):
            phys_z = stack_closed_height(box)

    if stack_enabled(box) or lid_enabled(box):
        wall = stack_effective_box(box).wall
    else:
        wall = box.wall

    return {
        "file": file_names,
        "x": phys_x, "y": phys_y, "z": phys_z,
        "label": "" if label_text == "-" else label_text,
        "interior": interior_text,
        "name": clean_label(part_name) or tidy_label or next(
            (text_of(one) for one in layout.features if is_text(one) and text_of(one)), ""),
        "kind": "b4b" if b4b_note else "bin",
        "stack": (
            b4b_stack_mode
            if b4b_stack_mode is not None
            else (
                "lid" if lid_stackable(box)
                else getattr(getattr(box, "stack", None), "mode", "none")
            )
        ),
        "wall": wall,
        "object_height_mm": layout.object_height_mm,
        "pegboard_standard": box.pegboard.standard if box.pegboard.enabled else "",
        "cleat_x": box.pegboard.cleat_x if box.pegboard.enabled else "auto",
        "cleat_y": box.pegboard.cleat_y if box.pegboard.enabled else "auto",
    }


def object_height_plan(design: dict | None, object_height_mm: float | None) -> dict[str, object]:
    """Installed top of an object above its bin's seating datum, for planning only."""
    if object_height_mm is None:
        return {"object_height_mm": None, "object_top_mm": None,
                "estimated": False, "source": "missing"}
    height = float(object_height_mm)
    if not math.isfinite(height) or height <= 0:
        raise ValueError("Object height must be positive and finite")
    fallback = {"object_height_mm": height, "object_top_mm": height,
                "estimated": True, "source": "estimate"}
    if not isinstance(design, dict):
        return fallback
    try:
        box, layout, *_ = design_from_dict(design, validate_layout=False)
        holders = [one for one in layout.features if not is_text(one)]
        if not holders or any(one.kind != "bore" for one in holders):
            return fallback
        base_z = base_height(box, layout.mode)
        tops = []
        for bore in holders:
            options = resolved_options(box, bore, base_z)
            mouth_z = base_z + float(options["height"])
            exposed = height - float(options["depth"])
            angle = math.radians(float(options.get("angle", 0.0)))
            tops.append(max(0.0, mouth_z + exposed * math.cos(angle)))
        return {"object_height_mm": height, "object_top_mm": max(tops),
                "estimated": False, "source": "bore"}
    except (ValueError, TypeError, KeyError, OverflowError):
        return fallback


def _starter_span(
    available: float, wanted: float, mode: str = "fused", snap: float = EDITOR_SNAP
) -> float:
    """Largest starter span that keeps a new holder out of the connector strip.

    A starter sized to fill a small bin lands in the edge strip a side
    connector's arms need, and the draft then fails the instant the part is
    added - the user gets an error for doing nothing but clicking Add, on a bin
    the app itself called valid.  Backing the starter off to the connector-safe
    span keeps it buildable; dragging it out to the wall afterwards is a
    deliberate act and still earns the same explanatory error.

    Cartridge mode is left alone: its grid is already inset clear of the strip,
    so insetting again would only shrink the cell the part is meant to fill.

    Bins too small for a useful connector-safe span are left alone too, so they
    still report why rather than starting with a part too small to see.
    """
    span = min(wanted, available)
    if mode == "cartridge":
        return span
    safe = available - 2.0 * CONNECTOR_EDGE_KEEP_OUT
    if span < safe - 1e-9:      # strictly clear, never sitting on the line
        return span
    stepped = math.floor(safe / snap) * snap
    if stepped >= safe - 1e-9:          # strictly inside, never on the line
        stepped -= snap
    return stepped if stepped >= 4.0 else span


def default_feature(
    box: BoxSpec,
    kind: str,
    item_key: str = "nozzle",
    along: str = "x",
    mode: str = "fused",
    item: Item | None = None,
) -> Feature:
    """A useful, valid starting rectangle for a newly-added holder.

    ``item`` describes the stored tool directly; when omitted, item-holding
    kinds fall back to a starter from ``LIBRARY[item_key]``.
    """
    if kind not in FEATURE_BUILDERS:
        raise ValueError(f"unknown holder {kind!r}")
    bounds = layout_zone(box, mode)
    if kind in {"cradle", "bore"}:
        item = item if item is not None else LIBRARY[item_key]
    else:
        item = None
    feature_options = {}
    if item is not None and kind == "cradle":
        required_length = item.length
        pitch = CARTRIDGE_PITCH if mode == "cartridge" else EDITOR_SNAP
        required_length = math.ceil((required_length - 1e-9) / pitch) * pitch
        if along == "x" and required_length > bounds.width:
            along = "y"
        if along == "y" and required_length > bounds.depth:
            along = "x"
        run = bounds.width if along == "x" else bounds.depth
        if required_length > run:
            # Fix 109 A2: never throw before an editable draft exists. Hand back
            # a starter clamped to the container instead. It is not sizing
            # authority - cradle_min_footprint() still decides the real minimum,
            # and the client's auto-grow trial takes it from here.
            required_length = max(math.floor((run + 1e-9) / pitch) * pitch, min(run, pitch))
        available_across = bounds.depth if along == "x" else bounds.width
        cradle_across = item.widest + _cradle_rib_thickness(item.widest)
        wanted_across = max(
            8.0,
            cradle_across,
        )
        across = min(
            available_across,
            math.ceil((wanted_across - 1e-9) / pitch) * pitch,
        )
        width, depth = ((required_length, across) if along == "x"
                        else (across, required_length))
    elif kind == "nest":
        width, depth = min(8.0, bounds.width), min(8.0, bounds.depth)
        # A brand-new (not yet photographed) Photo Nest must show the new-
        # scan defaults immediately - Recessed, Auto-size, Automatic finger
        # access - so the editor never displays a holder style the upload it
        # is about to trigger will not actually build. Tool thickness is
        # deliberately left unset here: it is the one measurement the user
        # has to supply, and must never be shown as though already measured.
        feature_options = {
            "holder_style": "recessed",
            "cavity_depth_mode": "auto",
            "auto_size": True,
            "lift_assist": "auto",
        }
    elif kind == "divider":
        # Wall to wall on its own run axis by default, and spread across
        # the bin's whole other axis too - room for count > 1 to divide the
        # bin evenly without the user having to widen it by hand first.
        width, depth = bounds.width, bounds.depth
        # New Dividers start with one wall on X and none on Y (X=1, Y=0). Older saved
        # Dividers have neither key and continue through the legacy one-axis
        # path in divider_defaults().
        feature_options = {"count_x": 1, "count_y": 0, "wall_style": "wavy", "thickness": 0.8}
    elif kind == "post":
        # A one-cell-wide cartridge cannot hold the normal 12 mm starter peg.
        # Size the starter diameter to both axes, then give it as much of the
        # usual 16 mm editing footprint as the layout has. Wider bins retain
        # the established 12 mm default unchanged.
        run_limit = bounds.width if along == "x" else bounds.depth
        across_limit = bounds.depth if along == "x" else bounds.width
        run = _starter_span(run_limit, 16.0, mode)
        across = _starter_span(across_limit, 16.0, mode)
        # The peg has to fit the zone it actually got, not the bin, and needs
        # material around it - sizing it to the bare span left a 12 mm peg in a
        # 12 mm zone, or worse, a peg wider than the zone once that snapped
        # down.  A cartridge peg is meant to fill its cell, so it keeps the
        # bare span.
        margin = 0.0 if mode == "cartridge" else MIN_FEATURE_GAP
        diameter = min(12.0, run - margin, across - margin)
        width, depth = ((run, across) if along == "x" else (across, run))
        if mode == "fused":
            # A Fused Post may legally rise above a shallow bin's rim (spec:
            # shallow-fused-above-rim), so the natural 16 mm default is never
            # shrunk here - build_features()'s central policy is what still
            # bounds it in every other mode.
            height = 16.0
        else:
            # A short bin cannot take the usual 16 mm peg either, in a mode
            # that stays height-bound - the same "valid bin, instant error on
            # Add" trap the width/depth clamp above already guards against,
            # just along Z instead of X/Y.
            usable_height = box.z - base_height(box, mode)
            height = min(16.0, usable_height - MIN_FEATURE_GAP)
        feature_options = {"diameter": diameter, "height": height, "taper": 0.0}
    elif kind == "bore":
        # Same starter X/Y footprint a Bore always got falling through the
        # generic branch below - only the fused-shallow-bin depth seeding is
        # new here.
        width = _starter_span(bounds.width, 16.0, mode)
        depth = _starter_span(bounds.depth, 16.0, mode)
        if mode == "fused":
            base_z = box.base_thickness
            available = box.z - base_z
            if item.profile in HEX_BIT_HOLD:
                natural_depth = HEX_BIT_HOLD[item.profile]
            else:
                natural_depth = item.length * 0.4
            # The historical resolver would clamp Depth to (available - 2 mm);
            # only step in when a shallow fused bin would actually shorten the
            # bore's natural depth. Height is never stored here - it must keep
            # deriving from Depth so angled-bore auto-growth still works.
            if natural_depth > available - 2.0 + 1e-9:
                feature_options["depth"] = natural_depth
    elif kind == "pocket":
        # Same generic starter footprint a Pocket always got - only the
        # fused-shallow-bin height seeding is new here.
        width = _starter_span(bounds.width, 16.0, mode)
        depth = _starter_span(bounds.depth, 16.0, mode)
        feature_options["wall_style"] = "wavy"
        if mode == "fused":
            base_z = box.base_thickness
            available = box.z - base_z
            natural_height = max(20.0, round(0.40 * box.z, 1))
            if available + 1e-9 < natural_height:
                feature_options["height"] = natural_height
    elif kind == "slot":
        feature_options["wall_style"] = "wavy"
        if mode == "cartridge":
            # One 8 mm cell still fits a useful starter opening after the
            # required 0.4 mm wave margin on each outside wall.
            feature_options["thickness"] = 3.7
        run = _starter_span(bounds.width if along == "x" else bounds.depth, 32.0, mode)
        # One explicit starter slot, with the extra wave excursion reserved.
        # Raising Quantity in
        # the editor grows this axis automatically.
        across = _starter_span(bounds.depth if along == "x" else bounds.width, 9.0, mode)
        width, depth = ((run, across) if along == "x" else (across, run))
        if mode == "fused":
            base_z = box.base_thickness
            available = box.z - base_z
            # The historical resolver clamps Depth to (available - 4 mm); only
            # step in when a shallow fused bin would shorten the natural
            # 14 mm depth. Height is never stored - it keeps deriving as
            # Depth + 2 mm.
            if available - 4.0 + 1e-9 < 14.0:
                feature_options["depth"] = 14.0
    elif kind == "steps":
        run = _starter_span(bounds.width if along == "x" else bounds.depth, 32.0, mode)
        across = _starter_span(bounds.depth if along == "x" else bounds.width, 32.0, mode)
        width, depth = ((run, across) if along == "x" else (across, run))
        if mode == "fused":
            base_z = box.base_thickness
            available = box.z - base_z
            # The historical resolver clamps Height to (available - 2 mm);
            # only step in when a shallow fused bin would shorten the
            # natural 16 mm height.
            if available - 2.0 + 1e-9 < 16.0:
                feature_options["height"] = 16.0
    elif kind == "scoop":
        along = "x"
        scoop_height = (box.z - box.base_thickness) * 0.6
        width, depth = bounds.width, min(scoop_height, bounds.depth / 2.0)
    elif kind == TEXT_KIND:
        # The starting zone is only an interaction aid; the glyph determines
        # its canonical bounds after fitting into the usable base.
        width, depth = bounds.width, bounds.depth
        feature_options = {"text": "", "level": "base", "quarter_turns": 0,
                           "raised": False, "depth": TEXT_DEPTH,
                           "cap_height": TEXT_CAP_HEIGHT_IDEAL}
    else:
        width = _starter_span(bounds.width, 16.0, mode)
        depth = _starter_span(bounds.depth, 16.0, mode)
    raw = Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)
    # Browser Dividers have no user-sized footprint: their zone is the exact
    # bin floor and must keep following it when Width, Length, or wall depth
    # changes. Snapping this derived zone can leave it stale or slightly
    # short; ordinary parts still use the editor grid below.
    one_zone = bounds if kind in {"divider", TEXT_KIND} else snapped_zone(raw, box, mode)
    if kind == "scoop":
        one = Feature(kind, one_zone, along=along, options=feature_options)
        one_zone = scoop_zone(
            box, one,
            box.base_thickness if mode == "fused" else box.base_thickness + BASE_PLATE,
            mode,
        )
    result = Feature(
        kind,
        one_zone,
        item=item,
        # A cradle, like a post, starts as a single holder - Quantity "auto"
        # then fills the zone with lanes only when the user asks for it.
        count=3 if kind == "steps" else (1 if kind in {"post", "cradle", "slot", "nest"} else None),
        along=along,
        options=feature_options,
        full_span=(kind == "divider"),
    )
    if kind == TEXT_KIND:
        from organizer_inserts._text import canonical_text_feature
        try:
            fitted_cap = text_fitted(result)[0]
            result = replace(result, options={**result.options, "cap_height": fitted_cap})
        except ValueError:
            pass
        return canonical_text_feature(result)
    return result


def auto_text_feature(box: BoxSpec, label: str, mode: str = "fused") -> Feature:
    """A centered base Text from the command-line label shortcut."""
    one = default_feature(box, TEXT_KIND, mode=mode)
    options = dict(one.options)
    options["text"] = str(label).strip()
    options.pop("cap_height", None)
    options.pop("text_v2", None)
    from organizer_inserts._text import canonical_text_feature
    return canonical_text_feature(replace(one, options=options))


def convert_layout_mode(
    box: BoxSpec, features: Iterable[Feature], mode: str,
    source_layout: Layout | None = None,
) -> Layout:
    """Snap every interior part onto a new mode's grid and validate the result."""
    converted_items = []
    for one in features:
        # Auto Bores follow the new mode's usable area, not the old cache.
        one = normalize_bore_modes(box, one, base_height(box, mode), mode)
        if one.kind == "nest" and one.contour:
            converted_items.append(fitted_nest_feature(one))
            continue
        zone = one.zone
        if mode == "cartridge":
            width = math.ceil((zone.width - 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            depth = math.ceil((zone.depth - 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
            cx, cy = zone.centre
            zone = Zone(
                cx - width / 2.0, cy - depth / 2.0,
                cx + width / 2.0, cy + depth / 2.0,
            )
        if one.kind == "bore" and one.options.get("xy_size_mode") == "bore_to_bin":
            # Its zone is the exact derived usable area; snapping would shrink it.
            converted_items.append(one)
            continue
        converted_items.append(replace(one, zone=snapped_zone(zone, box, mode)))
    converted = tuple(converted_items)
    layout = (replace(source_layout, features=converted, mode=mode, snap=EDITOR_SNAP)
              if source_layout is not None else Layout(converted, mode, EDITOR_SNAP))
    layout.validate(box)
    base_z = base_height(box, mode)
    build_features(box, converted, base_z, layout_zone(box, mode), mode=mode)
    return layout


def design_to_dict(
    box: BoxSpec,
    layout: Layout,
    label: str = "",
    part_name: str = "",
    label_location: str = "bottom",
    scoop: bool = False,
) -> dict:
    """The saved design.

    ``label`` is the rim-ledge label and means something only when
    ``label_position`` names a rim side. Floor lettering lives in the layout as
    ``text`` interior parts - one per label, any number of them - so there is
    nothing for it here.
    """
    # Canonicalize the former stack.mode="lid" representation. It remains
    # readable, but new files always carry a dedicated lid block.
    legacy_lid = lid_spec(box)
    if getattr(box.stack, "mode", "none") == "lid":
        box = replace(box, stack=StackSpec(), lid=legacy_lid)
    layout, label, label_location = _canonical_rim_label(box, layout, label, label_location)
    if not box.b4b.enabled:
        layout = replace(layout, features=resolve_text_features(
            box, layout.features, base_z=base_height(box, layout.mode), mode=layout.mode,
        ))
    box = normalize_stack_settings(box)
    if box.pegboard.enabled:
        if box.b4b.enabled:
            raise ValueError("Pegboard mounting is available only for ordinary bins")
        receiver_layout(box)  # validates Auto/manual counts and minimum height
    b4b = box.b4b.normalised()
    box_block = {
        "x": box.x,
        "y": box.y,
        "z": box.z,
        "wall": box.wall,
        "base_thickness": box.base_thickness,
        "corner_fillet": box.corner_fillet,
        "flat_inside": box.flat_inside,
        "standard_base": box.standard_base,
        "standard_walls": bool(box.standard_walls) and math.isclose(
            box.wall, DEFAULT_WALL, abs_tol=1e-9
        ),
    }
    if b4b.enabled:
        box_block["b4b"] = {
            "enabled": True,
            "lid": b4b.lid,
            "secure_lid": b4b.secure_lid,
            "latch_count": b4b.latch_count,
            "lid_headroom_mm": b4b.lid_headroom_mm,
            "label_enabled": b4b.label_enabled or bool(b4b.label_text.strip()),
            "label_text": b4b.label_text,
            "label_location": b4b.label_location,
            "front_label_style": b4b.front_label_style,
            "stacking": b4b.stacking,
            "handle": b4b.handle,
            "version": b4b.version,
        }
    stack = getattr(box, "stack", None) or StackSpec()
    if stack.mode == "direct":
        box_block["stack"] = {"mode": stack.mode}
    lid = lid_spec(box)
    if lid.enabled:
        box_block["lid"] = {
            "enabled": True,
            "stackable": lid.stackable,
            "thickness": lid.thickness,
            "label_enabled": lid.label_enabled,
            "label_style": lid.label_style,
            "label_orientation": lid.label_orientation,
            "label_text": lid.label_text,
            "division_labels": list(lid.division_labels),
            "handle_type": lid.handle_type,
            "handle_size": lid.handle_size,
            "handle_position": lid.handle_position,
            # Written explicitly so a missing value only ever means a legacy file.
            "fit": lid.fit,
            "label_depth_mm": lid_label_relief_mm(lid),
        }
    grabbers = getattr(box, "lift_grabbers", None) or LiftGrabberSpec()
    if grabbers.enabled:
        box_block["lift_grabbers"] = {
            "enabled": True,
            "size": grabbers.size,
            "location": grabbers.location,
        }
    edge_mount = getattr(box, "edge_mount", None) or EdgeMountSpec()
    if edge_mount.active:
        box_block["edge_mount"] = {
            "side": edge_mount.side,
            "label_enabled": edge_mount.label_enabled,
            "label_text": edge_mount.label_text,
            "label_type": edge_mount.label_type,
            "label_projection_mm": edge_mount.label_projection_mm,
            "label_length_mode": edge_mount.label_length_mode,
            "label_thickness_mm": edge_mount.label_thickness_mm,
            "label_raised": edge_mount.label_raised,
            "label_text_depth_mm": edge_mount.label_text_depth_mm,
            "label_flip": edge_mount.label_flip,
            "standoff_ribs_enabled": edge_mount.standoff_ribs_enabled,
            "standoff_rib_count": edge_mount.standoff_rib_count,
            "holes_enabled": edge_mount.holes_enabled,
            "hole_count": edge_mount.hole_count,
            "hole_orientation": edge_mount.hole_orientation,
            "screw_diameter_mm": edge_mount.screw_diameter_mm,
            "access_diameter_mm": edge_mount.access_diameter_mm,
            "top_offset_mm": edge_mount.top_offset_mm,
            "hole_spacing_mm": edge_mount.hole_spacing_mm,
        }
    side_openings = getattr(box, "side_openings", None) or SideOpeningSpec()
    if side_openings.enabled:
        box_block["side_openings"] = {
            "enabled": True,
            "shape": side_openings.shape,
            "sides": list(side_openings.sides),
            "size": side_openings.size,
            "from_bottom_percent": side_openings.from_bottom_percent,
            "from_top_percent": side_openings.from_top_percent,
            "percent_mode": "inset_v2",
        }
    pegboard = normalise_mount_spec(getattr(box, "pegboard", None))
    if pegboard.enabled:
        box_block["pegboard"] = {
            "enabled": True,
            "standard": pegboard.standard,
            "cleat_x": pegboard.cleat_x,
            "cleat_y": pegboard.cleat_y,
        }
    return {
        # Version 3 only when B4B is on. Version 3 changes B4B x/y from the
        # physical outside to the exact requested child field, so older builds
        # reject a B4B design instead of silently loading it as an ordinary bin.
        # Version 4 carried stacking with Z as detached closed height. Version
        # 5 makes Z the authoritative stack-module/pitch height. Version 6
        # separates ordinary lids from direct vertical stacking. Version 7 is
        # written only with an ordinary lid: it adds the lid fit preset and
        # the explicit lid label Inlay depth / Raised height.
        "version": 7 if lid.enabled else (
            6 if stack.mode == "direct" else (3 if b4b.enabled else 1)),
        "box": box_block,
        "label": label,
        "label_position": label_position(label_location),
        "scoop": bool(scoop),
        "part_name": part_name,
        "layout": layout_to_dict(layout),
    }


def design_from_dict(
    data: dict, *, validate_layout: bool = True
) -> tuple[BoxSpec, Layout, str, str, str, bool]:
    design_version = data.get("version", 1)
    if design_version not in (1, 2, 3, 4, 5, 6, 7):
        raise ValueError(f"unsupported design version {data.get('version')!r}")
    raw = data["box"]
    stack_raw = raw.get("stack")
    stack = StackSpec()
    legacy_stack_mode = "none"
    if isinstance(stack_raw, dict) and stack_raw.get("mode"):
        legacy_stack_mode = str(stack_raw["mode"])
        if legacy_stack_mode != "lid":
            stack = StackSpec(mode=legacy_stack_mode)
    lid_raw = raw.get("lid")
    lid = LidSpec(enabled=True, stackable=True) if legacy_stack_mode == "lid" else LidSpec()
    if isinstance(lid_raw, dict) and bool(lid_raw.get("enabled", False)):
        raw_labels = lid_raw.get("division_labels", ())
        if not isinstance(raw_labels, (list, tuple)):
            raise ValueError("lid division labels must be a list")
        lid = LidSpec(
            enabled=True,
            stackable=bool(lid_raw.get("stackable", False)),
            thickness=str(lid_raw.get("thickness", "thin")),
            label_enabled=bool(lid_raw.get("label_enabled", False)),
            label_style=str(lid_raw.get("label_style", "flush")),
            label_orientation=str(lid_raw.get("label_orientation", "horizontal")),
            label_text=str(lid_raw.get("label_text", "")),
            division_labels=tuple(str(value or "") for value in raw_labels),
            handle_type=str(lid_raw.get("handle_type", "knob")),
            handle_size=str(lid_raw.get("handle_size", "medium")),
            handle_position=str(lid_raw.get("handle_position", "middle")),
            # A missing fit is an older file: Standard, the exact old plug fit.
            fit=str(lid_raw.get("fit", "standard")),
            # A missing depth is an older file: 0.4 mm inlaid, 0.6 mm raised.
            label_depth_mm=(None if lid_raw.get("label_depth_mm") in (None, "")
                            else float(lid_raw["label_depth_mm"])),
        )
    grabbers_raw = raw.get("lift_grabbers")
    lift_grabbers = LiftGrabberSpec()
    if isinstance(grabbers_raw, dict) and bool(grabbers_raw.get("enabled", False)):
        lift_grabbers = LiftGrabberSpec(
            enabled=True,
            size=str(grabbers_raw.get("size", "medium")),
            location=str(grabbers_raw.get("location", "sides")),
        )
    edge_mount_raw = raw.get("edge_mount")
    edge_mount = EdgeMountSpec()
    if isinstance(edge_mount_raw, dict):
        access_raw = edge_mount_raw.get("access_diameter_mm")
        spacing_raw = edge_mount_raw.get("hole_spacing_mm")
        # Fix-025 Separate labels predate ribs. Keep their printed body exactly
        # as saved, while older integrated labels gain the new default when a
        # user later chooses a Separate part.
        if "standoff_ribs_enabled" in edge_mount_raw:
            standoff_ribs_enabled = bool(edge_mount_raw["standoff_ribs_enabled"])
        else:
            standoff_ribs_enabled = str(edge_mount_raw.get("label_type", "integrated")) != "separate"
        rib_count_raw = edge_mount_raw.get("standoff_rib_count")
        standoff_rib_count = int(rib_count_raw) if rib_count_raw is not None else None
        edge_mount = EdgeMountSpec(
            side=str(edge_mount_raw.get("side", "front")),
            label_enabled=bool(edge_mount_raw.get("label_enabled", False)),
            label_text=str(edge_mount_raw.get("label_text", "")),
            label_type=str(edge_mount_raw.get("label_type", "integrated")),
            label_projection_mm=float(edge_mount_raw.get("label_projection_mm", 50.0)),
            label_length_mode=str(edge_mount_raw.get("label_length_mode", "full")),
            label_thickness_mm=float(edge_mount_raw.get("label_thickness_mm", 2.0)),
            label_raised=bool(edge_mount_raw.get("label_raised", False)),
            # Fix 058 Correction 1, C1.4D: a missing/new Edge Mount value uses
            # the Edge-Mount-only 0.6 mm default, never the global floor-label
            # TEXT_DEPTH; an explicitly saved value (including an old 0.4 mm
            # design) is preserved exactly as saved.
            label_text_depth_mm=float(edge_mount_raw.get("label_text_depth_mm", EDGE_MOUNT_TEXT_DEPTH_DEFAULT_MM)),
            label_flip=bool(edge_mount_raw.get("label_flip", False)),
            standoff_ribs_enabled=standoff_ribs_enabled,
            standoff_rib_count=standoff_rib_count,
            holes_enabled=bool(edge_mount_raw.get("holes_enabled", False)),
            hole_count=int(edge_mount_raw.get("hole_count", 2)),
            hole_orientation=str(edge_mount_raw.get("hole_orientation", "horizontal")),
            screw_diameter_mm=float(edge_mount_raw.get("screw_diameter_mm", 4.0)),
            access_diameter_mm=(float(access_raw) if access_raw is not None else None),
            top_offset_mm=float(edge_mount_raw.get("top_offset_mm", 12.7)),
            hole_spacing_mm=(float(spacing_raw) if spacing_raw is not None else None),
        )
    side_openings_raw = raw.get("side_openings")
    side_openings = SideOpeningSpec()
    legacy_top_support = False
    if isinstance(side_openings_raw, dict) and bool(side_openings_raw.get("enabled", False)):
        raw_sides = side_openings_raw.get("sides", ())
        if not isinstance(raw_sides, (list, tuple)):
            raise ValueError("side opening sides must be a list")
        if side_openings_raw.get("percent_mode") == "inset_v2":
            from_bottom = float(side_openings_raw.get("from_bottom_percent", 0.0))
            from_top = float(side_openings_raw.get("from_top_percent", 0.0))
        else:
            # Fix 034 H: pre-inset_v2 saves used reach semantics (higher meant
            # "reaches further"; 100 meant "reaches that edge"). Convert to
            # the new inset meaning (0 reaches that edge) without changing
            # the physical geometry: new = 100 - old.
            old_bottom = float(side_openings_raw.get(
                "from_bottom_percent", side_openings_raw.get("depth_percent", 100.0)
            ))
            explicit_old_top = (
                float(side_openings_raw["from_top_percent"])
                if "from_top_percent" in side_openings_raw else None
            )
            legacy_top_support = (
                explicit_old_top is None
                and bool(side_openings_raw.get("top_support", False))
            )
            from_bottom = 100.0 - old_bottom
            # A legacy Top Support bridge becomes the new minimum top inset,
            # derived below from the final normalised box, never from raw
            # JSON - 0.0 here is only a placeholder pending that.
            from_top = 0.0 if legacy_top_support else 100.0 - (
                100.0 if explicit_old_top is None else explicit_old_top
            )
        side_openings = SideOpeningSpec(
            enabled=True,
            shape=str(side_openings_raw.get("shape", "curved")),
            sides=tuple(str(side) for side in raw_sides),
            size=str(side_openings_raw.get("size", "medium")),
            from_bottom_percent=from_bottom,
            from_top_percent=from_top,
        )
    pegboard = normalise_mount_spec(raw.get("pegboard"))
    b4b_raw = raw.get("b4b")
    b4b = B4BSpec()
    if isinstance(b4b_raw, dict) and bool(b4b_raw.get("enabled", False)):
        # Build the spec exactly as supplied - do NOT normalise yet.  Saved and
        # imported v2 JSON is authoritative user data: validate_b4b_design must
        # see any impossible combination before normalised() would rewrite it.
        label_text = str(b4b_raw.get("label_text", ""))
        b4b = B4BSpec(
            enabled=True,
            lid=bool(b4b_raw.get("lid", True)),
            secure_lid=bool(b4b_raw.get("secure_lid", True)),
            latch_count=str(b4b_raw.get("latch_count", "auto")),
            latch_strength=str(b4b_raw.get("latch_strength", "standard")),
            lid_headroom_mm=float(b4b_raw.get("lid_headroom_mm", 1.0)),
            label_enabled=bool(b4b_raw.get("label_enabled", bool(label_text.strip()))),
            label_text=label_text,
            label_location=str(b4b_raw.get("label_location", "top")),
            front_label_style=str(b4b_raw.get("front_label_style", "flat")),
            stacking=bool(b4b_raw.get("stacking", False)),
            # A pre-v2 ``handle`` meant a fixed arch on the lid top, and it was
            # on by default.  The bail that replaced it is body hardware with
            # real size requirements, so an old file carries the *intent*
            # forward and validation decides whether this case can keep it -
            # never inferred from the dimensions themselves.
            handle=bool(b4b_raw.get("handle", False)),
            version=int(b4b_raw.get("version", 1)),
        )
    x, y = float(raw["x"]), float(raw["y"])
    if b4b.enabled and design_version == 2:
        # Deterministic schema migration: v2 stored physical case X/Y and used
        # the reduced old rail capacity.  v3 stores that exact old capacity as
        # the requested child field.  Never guess semantics from dimensions.
        old_wall = float(raw.get("wall", DEFAULT_WALL))
        old_wall_depth = old_wall * math.sqrt(1.0 + max_wave_slope() ** 2)
        old_slack = 2.0 * (WAVE_MATING_GAP + old_wall_depth) / GRID_PITCH
        x = max(
            GRID_PITCH,
            math.floor(round(x / GRID_PITCH) - old_slack + 1e-6) * GRID_PITCH,
        )
        y = max(
            GRID_PITCH,
            math.floor(round(y / GRID_PITCH) - old_slack + 1e-6) * GRID_PITCH,
        )
    # Brief browser builds stored a requested usable size plus the wall
    # allowance. Recover the user's 8 mm modular choice when those designs are
    # reopened; every BoxSpec remains grid-locked after migration.
    if bool(raw.get("interior_sizing", False)):
        wall = float(raw.get("wall", DEFAULT_WALL))
        wall_depth = wall * math.sqrt(1.0 + max_wave_slope() ** 2)
        allowance = WAVE_MATING_GAP + 2.0 * wall_depth + 2.0 * WAVE_AMPLITUDE
        x = max(GRID_PITCH, round((x - allowance) / GRID_PITCH) * GRID_PITCH)
        y = max(GRID_PITCH, round((y - allowance) / GRID_PITCH) * GRID_PITCH)
    raw_wall = float(raw.get("wall", DEFAULT_WALL))
    if not math.isfinite(raw_wall) or not MIN_WALL <= raw_wall <= MAX_WALL:
        raise ValueError(
            f"wall thickness must be between {MIN_WALL:g} and {MAX_WALL:g} mm"
        )
    standard_walls = (
        bool(raw["standard_walls"])
        if "standard_walls" in raw
        else math.isclose(raw_wall, DEFAULT_WALL, abs_tol=1e-9)
    )
    wall = DEFAULT_WALL if standard_walls else raw_wall
    requested_z = float(raw["z"])
    # Preserve v4 physical geometry exactly: its Z was the detached closed
    # height, which equals the v5 module height plus the engagement depth.
    if design_version == 4 and (stack.enabled or lid.stackable):
        requested_z -= stack_step_depth(BoxSpec(stack=stack, lid=lid))
    box = BoxSpec(
        x, y, requested_z,
        wall,
        float(raw.get("corner_fillet", 0.6)),
        flat_inside=float(raw.get("flat_inside", 0.0)),
        base_thickness=float(raw.get("base_thickness", raw.get("wall", DEFAULT_WALL))),
        standard_base=bool(raw.get("standard_base", True)),
        standard_walls=standard_walls,
        b4b=b4b,
        stack=stack,
        lift_grabbers=lift_grabbers,
        lid=lid,
        edge_mount=edge_mount,
        side_openings=side_openings,
        pegboard=pegboard,
    )
    box = normalize_stack_settings(box)
    if box.pegboard.enabled:
        if box.b4b.enabled:
            raise ValueError("Pegboard mounting is available only for ordinary bins")
        receiver_layout(box)
    if legacy_top_support:
        usable_h = box.z - box.base_thickness
        if not usable_h > 0:
            raise ValueError("side openings need usable wall height above the base")
        from_top = 100.0 * SIDE_OPENING_TOP_BRIDGE_MM / usable_h
        box = replace(box, side_openings=replace(
            box.side_openings, from_top_percent=from_top,
        ))
    if not b4b.enabled:
        # Authoritative even for saved/imported JSON: an impossible Side
        # Opening combination must fail loudly at load time, never load
        # silently as something else.
        validate_side_openings(box)
    if b4b.enabled:
        if box.standard_walls:
            box = replace(
                box,
                wall=B4B_DEFAULT_WALL,
                standard_walls=False,
            )
        if box.standard_base:
            box = replace(
                box,
                base_thickness=B4B_DEFAULT_BASE,
                standard_base=False,
            )
        if lid.enabled or stack.enabled:
            raise ValueError("Storage Box cannot use the ordinary Lid & Stacking part")
        raw_layout = data.get("layout", {}) or {}
        layout = layout_from_dict(raw_layout)
        if layout.mode != "fused":
            raise ValueError("a Storage Box layout mode must be 'fused'")
        validate_b4b_design(
            box,
            layout_feature_kinds=tuple(one.kind for one in layout.features),
            layout_mode=layout.mode,
            flat_inside=float(raw.get("flat_inside", 0.0) or 0.0),
        )
        # Normalize legacy no-lid data and adopt any required child-field growth
        # so reopened and saved designs show the exact capacity that will print.
        box = replace(box, flat_inside=0.0, b4b=box.b4b.normalised())
        from organizer_b4b import b4b_effective_box, normalize_b4b_divider
        box = b4b_effective_box(box)
        normalized = [normalize_b4b_divider(box, one) for one in layout.features]
        layout = Layout(tuple(normalized), "fused", layout.snap)
        label = str(data.get("label", ""))
        location = label_position(data.get("label_position", "bottom"))
        return (box, layout, label, str(data.get("part_name", "")), location, False)
    layout = layout_from_dict(data.get("layout", {}))
    if layout.surface_lightweight_base and (stack_enabled(box) or lid_stackable(box)):
        raise ValueError("Lightweight base is unavailable with vertical stacking")
    base_z = base_height(box, layout.mode)
    layout = replace(layout, features=tuple(
        replace(
            normalize_divider_scoop(box, one, base_z),
            zone=layout_zone(box, layout.mode),
        )
        if one.kind == "divider" and one.full_span else
        normalize_divider_scoop(box, one, base_z)
        if one.kind == "divider" else
        replace(
            one,
            zone=scoop_zone(box, one, base_z, layout.mode, layout.snap),
        )
        if one.kind == "scoop" else
        normalize_bore_modes(box, one, base_z, layout.mode)
        for one in layout.features
    ))
    label = str(data.get("label", ""))
    location = label_position(data.get("label_position", "bottom"))
    layout, label, location = _canonical_rim_label(box, layout, label, location)
    scoop = bool(data.get("scoop", False))
    # The retired scoop checkbox made a real ramp but was not represented in
    # the interior-parts list. Turn it into the equivalent editable feature
    # when an older design is reopened, then retire the hidden flag.
    if scoop:
        if (not any(one.kind == "scoop" for one in layout.features)
                and not any(one.kind == "nest" and one.contour for one in layout.features)):
            # Seed the migrated Feature's zone the same way scoop_zone()
            # normalizes every scoop on every later load (the loop above),
            # not the unrelated physical-footprint math scoop_floor_zone()
            # uses elsewhere - otherwise the two disagree and a design that
            # migrates once keeps drifting a fraction of a millimetre on
            # every subsequent save/reopen instead of landing on a fixed point.
            legacy_zone = scoop_zone(
                box, Feature("scoop", Zone(-1.0, -1.0, 1.0, 1.0)),
                base_z, layout.mode, layout.snap,
            )
            layout = replace(
                layout,
                features=layout.features + (Feature("scoop", legacy_zone),),
            )
        scoop = False
    if validate_layout:
        # An auto text's stored zone is a cache of where it last landed, not
        # the authority - the resolver is. Re-run it before validating, so a
        # design saved with a holder since moved onto that spot still opens:
        # the lettering simply finds somewhere else, exactly as it would have
        # on screen.
        layout = replace(
            layout,
            features=resolve_text_features(
                box, layout.features,
                reserved=[
                    zone.polygon for _name, zone in _customization_zones(
                        box, clean_label(label), location, scoop, layout.mode
                    )
                ],
                base_z=base_height(box, layout.mode), mode=layout.mode,
            ),
        )
        try:
            layout.validate(box)
        except ValueError as error:
            # Old designs could contain independently placed duplicate Text.
            # Let them open for editing; preview/generation still reports the
            # destination conflict until the extra Text is removed.
            legacy_text = any(raw.get("kind") == "text"
                              and not raw.get("options", {}).get("text_v2")
                              for raw in data.get("layout", {}).get("features", ()))
            if not (str(error).startswith("Only one Text is allowed")
                    or (legacy_text and "will not fit the bin" in str(error))):
                raise
    return (box, layout, label, str(data.get("part_name", "")), location, scoop)


def design_source_payload(raw: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Canonicalize *raw* and derive its Inventory source-row fields.

    Used by Save-to-Space and by Generate/Print's on-demand source
    attachment: the design is validated/normalised exactly as it would be for
    preview or generation, so a saved source can never hold an invalid or
    stale-shaped design. The returned record's ``file`` is always blank - a
    design source is editable design data, not a generated file.
    """
    if isinstance(raw, dict) and raw.get("design_kind") == "base_trim":
        raise ValueError("a Base Trim is never an Inventory design source")
    box, layout, label, part_name, label_location, scoop = design_from_dict(raw)
    canonical = design_to_dict(box, layout, label, part_name, label_location, scoop)
    record = inventory_bin_record(box, layout, None, label, part_name, scoop)
    record["file"] = ""
    return canonical, record
