"""Holders that go inside a bin.

The idea here is to describe **the object being stored**, not the holder. An
``Item`` is a list of ``Segment``s - a length and a diameter each - so a plain
glue stick is one segment and a hex driver is two, shaft then handle. From that
one description the builders work out the geometry for either posture: lying in
a cradle, or standing in a bore.

Adding a new kind of holder means writing one function and registering it with
``@feature``. Nothing else in the module needs to know about it, and removing a
holder is deleting its function.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Iterable

import trimesh
from shapely.geometry import MultiPolygon, Polygon, box as shapely_box
from shapely.ops import unary_union

from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    WAVE_AMPLITUDE,
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    _rounded,
    difference,
    flat_cavity_polygon,
    intersection,
    union,
    wavy_cavity_polygon,
)

# --- how much room to leave ---------------------------------------------------

ITEM_CLEARANCE = 0.4       # slack around a stored object, on the diameter
RIB_THICKNESS = 1.6        # four perimeters at 0.4
RIB_SPACING = 1.2          # material left between two neighbouring cradles
BASE_PLATE = 0.6           # floor of a standalone insert
CRADLE_FLOOR_GAP = 2.0     # gap under the widest part of a lying object
BORE_WALL = 1.6            # material around a bore
INSERT_CLEARANCE = 0.4     # slack around a standalone insert, per side
MIN_FEATURE_GAP = 0.8      # material between two features
CONNECTOR_EDGE_KEEP_OUT = 2.0  # interior strip kept low for connector arms
EDITOR_SNAP = 1.0          # normal editor movement; effectively no floor loss
CARTRIDGE_PITCH = 8.0      # optional interchangeable standalone-insert grid
MAX_DIVIDER_ANGLE = 45.0   # steepest lean an FDM overhang prints support-free
MIN_WEDGE_EDGE = 0.4       # thinnest a wedge's tapered top may print
DIVIDER_CHAMFER = 1.0      # 45-degree foot flare where a divider meets the floor
LAYOUT_MODES = ("fused", "separate", "cartridge")

# A cradle notch is a half circle: any deeper and the object cannot be dropped
# in, because the opening would be narrower than the object.
MAX_NOTCH_FRACTION = 0.5


@dataclass(frozen=True)
class Segment:
    """One length of a stored object at one diameter."""

    length: float
    diameter: float

    def __post_init__(self) -> None:
        if (not math.isfinite(self.length) or not math.isfinite(self.diameter)
                or self.length <= 0.0 or self.diameter <= 0.0):
            raise ValueError("segment length and diameter must be positive finite numbers")


@dataclass(frozen=True)
class Item:
    """Something you want to store, described end to end.

    ``segments`` run along the object's own axis, so a hex driver is
    ``(Segment(50, 6), Segment(30, 18))`` - shaft then handle. That is enough
    for a cradle to give each part its own radius, which is what makes a
    handled tool sit level instead of see-sawing on one rib.
    """

    name: str
    segments: tuple[Segment, ...]
    profile: str = "round"          # round | hex | square
    clearance: float = ITEM_CLEARANCE

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("an item needs a name")
        if not self.segments:
            raise ValueError(f"{self.name}: an item needs at least one segment")
        if self.profile not in {"round", "hex", "square"}:
            raise ValueError(f"{self.name}: unknown profile {self.profile!r}")
        if not math.isfinite(self.clearance) or self.clearance < 0.0:
            raise ValueError(f"{self.name}: clearance must be a non-negative finite number")

    @classmethod
    def simple(cls, name: str, length: float, diameter: float, **kwargs) -> "Item":
        """A plain uniform object - a glue stick, a pencil, a dowel."""
        return cls(name, (Segment(length, diameter),), **kwargs)

    @property
    def length(self) -> float:
        return sum(s.length for s in self.segments)

    @property
    def widest(self) -> float:
        return max(s.diameter for s in self.segments)

    def held(self, diameter: float) -> float:
        """A diameter with the fit slack added."""
        return diameter + self.clearance

    def segment_centres(self) -> list[tuple[float, Segment]]:
        """Each segment's midpoint measured from the object's near end."""
        out, run = [], 0.0
        for segment in self.segments:
            out.append((run + segment.length / 2.0, segment))
            run += segment.length
        return out


@dataclass(frozen=True)
class Zone:
    """A rectangle of bin floor, in mm from the bin's centre.

    Features own a zone and never reach outside it, which is what makes "these
    at one end, nothing at the other" simply a matter of giving the feature a
    short zone.
    """

    x0: float
    y0: float
    x1: float
    y1: float

    def __post_init__(self) -> None:
        if (not all(math.isfinite(value) for value in (self.x0, self.y0, self.x1, self.y1))
                or self.x1 <= self.x0 or self.y1 <= self.y0):
            raise ValueError("a zone needs positive finite width and depth")

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def depth(self) -> float:
        return self.y1 - self.y0

    @property
    def centre(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0

    @property
    def polygon(self) -> Polygon:
        return shapely_box(self.x0, self.y0, self.x1, self.y1)

    def overlaps(self, other: "Zone", gap: float = 0.0) -> bool:
        return not (
            self.x1 + gap <= other.x0 or other.x1 + gap <= self.x0
            or self.y1 + gap <= other.y0 or other.y1 + gap <= self.y0
        )

    @staticmethod
    def whole(spec: BoxSpec) -> "Zone":
        """Everything a straight-sided insert can occupy in this bin."""
        clear_x, clear_y = spec.usable_inside
        return Zone(-clear_x / 2.0, -clear_y / 2.0, clear_x / 2.0, clear_y / 2.0)

    @staticmethod
    def end(spec: BoxSpec, along: str, span: float, at: str = "low") -> "Zone":
        """A slice at one end of the bin, leaving the rest of it empty."""
        whole = Zone.whole(spec)
        if along == "x":
            if span > whole.width:
                raise ValueError(f"{span:g} mm does not fit along x")
            return (Zone(whole.x0, whole.y0, whole.x0 + span, whole.y1)
                    if at == "low" else
                    Zone(whole.x1 - span, whole.y0, whole.x1, whole.y1))
        if span > whole.depth:
            raise ValueError(f"{span:g} mm does not fit along y")
        return (Zone(whole.x0, whole.y0, whole.x1, whole.y0 + span)
                if at == "low" else
                Zone(whole.x0, whole.y1 - span, whole.x1, whole.y1))


@dataclass(frozen=True)
class Feature:
    """One holder, of one kind, occupying one zone."""

    kind: str
    zone: Zone
    item: Item | None = None
    count: int | None = None            # None means as many as fit
    along: str = "x"                    # axis the stored object lies along
    options: dict = field(default_factory=dict)
    # A divider that runs edge to edge, hugging the box's true wavy wall
    # instead of the straight-sided rectangle every other zone is confined
    # to. Nothing else reads this - see ``build_divider``.
    full_span: bool = False
    # A leaning divider's cross-section: a wedge, thick at the floor and
    # tapering as it rises, or (False) a uniform-thickness sloped wall - see
    # ``build_divider``. Meaningless at zero angle; only a divider sets it.
    wedge: bool = True

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a feature needs a kind")
        if self.along not in {"x", "y"}:
            raise ValueError("feature orientation must be 'x' or 'y'")
        if self.count is not None and self.count < 1:
            raise ValueError("feature count must be positive or automatic")
        if self.full_span and self.kind != "divider":
            raise ValueError("only a divider can span the full wall")


@dataclass(frozen=True)
class Layout:
    """A durable editor layout shared by preview, CLI and export.

    ``fused`` grows holders from the bin floor. ``separate`` makes a fitted,
    removable full-floor insert. ``cartridge`` is the same removable form but
    restricts the useful area to centred 8 mm cells so layouts can be reused in
    another bin with the same cell footprint. Normal editing snaps to 1 mm.
    """

    features: tuple[Feature, ...] = ()
    mode: str = "fused"
    snap: float = EDITOR_SNAP

    def __post_init__(self) -> None:
        if self.mode not in LAYOUT_MODES:
            raise ValueError(
                f"layout mode must be one of {', '.join(LAYOUT_MODES)}"
            )
        if not math.isfinite(self.snap) or self.snap <= 0.0:
            raise ValueError("layout snap must be positive and finite")

    def validate(self, box: BoxSpec) -> None:
        bounds = layout_zone(box, self.mode)
        check_layout(box, self.features, bounds)
        if self.mode == "cartridge":
            for one in self.features:
                values = (
                    one.zone.x0 - bounds.x0,
                    one.zone.y0 - bounds.y0,
                    one.zone.width,
                    one.zone.depth,
                )
                if any(
                    abs(value / CARTRIDGE_PITCH - round(value / CARTRIDGE_PITCH)) > 1e-6
                    for value in values
                ):
                    raise ValueError(
                        "cartridge feature positions and sizes must use 8 mm cells"
                    )


def snap_value(value: float, pitch: float = EDITOR_SNAP) -> float:
    """Round to the nearest pitch, symmetrically on either side of zero."""
    if pitch <= 0.0:
        raise ValueError("snap pitch must be positive")
    sign = -1.0 if value < 0.0 else 1.0
    return sign * math.floor(abs(value) / pitch + 0.5) * pitch


def cartridge_zone(box: BoxSpec) -> Zone:
    """Largest centred whole-cell rectangle that fits on this bin's floor."""
    whole = Zone.whole(box)
    width = math.floor((whole.width + 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
    depth = math.floor((whole.depth + 1e-9) / CARTRIDGE_PITCH) * CARTRIDGE_PITCH
    if width < CARTRIDGE_PITCH or depth < CARTRIDGE_PITCH:
        raise ValueError("this bin is too small for one 8 mm cartridge cell")
    return Zone(-width / 2.0, -depth / 2.0, width / 2.0, depth / 2.0)


def layout_zone(box: BoxSpec, mode: str = "fused") -> Zone:
    if mode not in LAYOUT_MODES:
        raise ValueError(f"unknown layout mode {mode!r}")
    return cartridge_zone(box) if mode == "cartridge" else Zone.whole(box)


def snapped_zone(
    zone: Zone,
    box: BoxSpec,
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Zone:
    """Snap a zone's centre and size, then clamp it inside the usable floor."""
    bounds = layout_zone(box, mode)
    pitch = CARTRIDGE_PITCH if mode == "cartridge" else snap
    width = max(pitch, snap_value(zone.width, pitch))
    depth = max(pitch, snap_value(zone.depth, pitch))
    if width > bounds.width + 1e-9 or depth > bounds.depth + 1e-9:
        raise ValueError(
            f"{width:g} x {depth:g} mm does not fit in the "
            f"{bounds.width:g} x {bounds.depth:g} mm layout area"
        )
    if mode == "cartridge":
        # Cell edges are measured from the cartridge's lower-left corner. On
        # an even number of cells the legal centres sit half a cell off world
        # zero, so snapping the centre itself would produce an invalid layout.
        x0 = bounds.x0 + snap_value(zone.x0 - bounds.x0, pitch)
        y0 = bounds.y0 + snap_value(zone.y0 - bounds.y0, pitch)
        x0 = min(max(x0, bounds.x0), bounds.x1 - width)
        y0 = min(max(y0, bounds.y0), bounds.y1 - depth)
        cx, cy = x0 + width / 2.0, y0 + depth / 2.0
    else:
        cx, cy = zone.centre
        cx, cy = snap_value(cx, pitch), snap_value(cy, pitch)
        cx = min(max(cx, bounds.x0 + width / 2.0), bounds.x1 - width / 2.0)
        cy = min(max(cy, bounds.y0 + depth / 2.0), bounds.y1 - depth / 2.0)
    return Zone(cx - width / 2.0, cy - depth / 2.0,
                cx + width / 2.0, cy + depth / 2.0)


def moved_feature(
    one: Feature,
    box: BoxSpec,
    centre: tuple[float, float],
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Feature:
    width, depth = one.zone.width, one.zone.depth
    cx, cy = centre
    zone = Zone(cx - width / 2.0, cy - depth / 2.0,
                cx + width / 2.0, cy + depth / 2.0)
    return replace(one, zone=snapped_zone(zone, box, mode, snap))


def resized_feature(
    one: Feature,
    box: BoxSpec,
    size: tuple[float, float],
    mode: str = "fused",
    snap: float = EDITOR_SNAP,
) -> Feature:
    width, depth = size
    if width <= 0.0 or depth <= 0.0:
        raise ValueError("feature width and depth must be positive")
    cx, cy = one.zone.centre
    zone = Zone(cx - width / 2.0, cy - depth / 2.0,
                cx + width / 2.0, cy + depth / 2.0)
    return replace(one, zone=snapped_zone(zone, box, mode, snap))


def _item_dict(item: Item | None) -> dict | None:
    if item is None:
        return None
    return {
        "name": item.name,
        "profile": item.profile,
        "clearance": item.clearance,
        "segments": [
            {"length": segment.length, "diameter": segment.diameter}
            for segment in item.segments
        ],
    }


def layout_to_dict(layout: Layout) -> dict:
    return {
        "version": 1,
        "mode": layout.mode,
        "snap": layout.snap,
        "features": [
            {
                "kind": one.kind,
                "zone": [one.zone.x0, one.zone.y0, one.zone.x1, one.zone.y1],
                "item": _item_dict(one.item),
                "count": one.count,
                "along": one.along,
                "options": dict(one.options),
                "full_span": one.full_span,
                "wedge": one.wedge,
            }
            for one in layout.features
        ],
    }


def layout_from_dict(data: dict) -> Layout:
    if data.get("version", 1) != 1:
        raise ValueError(f"unsupported layout version {data.get('version')!r}")
    made = []
    for raw in data.get("features", []):
        item_data = raw.get("item")
        item = None
        if item_data:
            item = Item(
                str(item_data["name"]),
                tuple(Segment(float(s["length"]), float(s["diameter"]))
                      for s in item_data["segments"]),
                str(item_data.get("profile", "round")),
                float(item_data.get("clearance", ITEM_CLEARANCE)),
            )
        coords = [float(value) for value in raw["zone"]]
        if len(coords) != 4:
            raise ValueError("a saved feature zone needs four coordinates")
        made.append(Feature(
            str(raw["kind"]), Zone(*coords), item,
            None if raw.get("count") is None else int(raw["count"]),
            str(raw.get("along", "x")), dict(raw.get("options", {})),
            bool(raw.get("full_span", False)),
            bool(raw.get("wedge", True)),
        ))
    return Layout(tuple(made), str(data.get("mode", "fused")),
                  float(data.get("snap", EDITOR_SNAP)))


def save_layout(layout: Layout, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(layout_to_dict(layout), indent=2) + "\n", encoding="utf-8")


def load_layout(path: Path) -> Layout:
    return layout_from_dict(json.loads(path.read_text(encoding="utf-8")))


# --- the registry -------------------------------------------------------------
#
# One function per kind of holder. A builder gets the bin, the feature and the
# height its base sits at, and returns solids to add. That is the whole
# contract, so a new holder is a new function and nothing else.

Builder = Callable[[BoxSpec, Feature, float], list[trimesh.Trimesh]]
FEATURE_BUILDERS: dict[str, Builder] = {}


def feature(kind: str) -> Callable[[Builder], Builder]:
    def register(function: Builder) -> Builder:
        FEATURE_BUILDERS[kind] = function
        return function
    return register


# A holder may leave an option unset, meaning "work it out from the bin, the
# zone or the stored item".  That was fine while only the builders needed the
# number, but the editor has to show it too: a parameter box that sits blank
# cannot be reasoned about or edited.  So each kind registers how it resolves
# its own defaults, once, and both the builder and the editor read them here.
Defaults = Callable[[BoxSpec, "Feature", float], dict[str, float]]
FEATURE_DEFAULTS: dict[str, Defaults] = {}


def defaults(kind: str) -> Callable[[Defaults], Defaults]:
    def register(function: Defaults) -> Defaults:
        FEATURE_DEFAULTS[kind] = function
        return function
    return register


def resolved_options(
    box: BoxSpec, spec_feature: "Feature", base_z: float = 0.0
) -> dict[str, float]:
    """Every option of a holder as a concrete number.

    Defaults first, then whatever the holder actually sets on top.  A default
    may read the options already chosen - a pocket's recess follows its height
    - so the two cascade the same way they did when each builder worked its
    own defaults out inline.
    """
    resolve = FEATURE_DEFAULTS.get(spec_feature.kind)
    resolved = dict(resolve(box, spec_feature, base_z)) if resolve else {}
    resolved.update({
        name: value for name, value in spec_feature.options.items()
        if value is not None
    })
    return resolved


def _need_item(spec_feature: Feature) -> Item:
    if spec_feature.item is None:
        raise ValueError(f"a {spec_feature.kind} needs an item to hold")
    return spec_feature.item


def _fit_count(available: float, pitch: float, body: float) -> int:
    """How many bodies of ``body`` fit at ``pitch``, given the run available."""
    if available < body:
        return 0
    return int((available - body) // pitch) + 1


# --- cradles ------------------------------------------------------------------


@defaults("cradle")
def cradle_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {
        "rib_thickness": RIB_THICKNESS,
        "spacing": RIB_SPACING,
        "floor_gap": CRADLE_FLOOR_GAP,
    }


@feature("cradle")
def build_cradle(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """Scalloped ribs holding objects lying on their side.

    One rib per segment of the item, each scalloped to that segment's own
    radius, so a handled tool rests level. Every notch is a half circle centred
    on the rib's top edge: the object drops straight in, and there is no
    overhang anywhere for the printer to bridge.
    """
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    along = spec_feature.along
    options = resolved_options(box, spec_feature, base_z)
    if along not in {"x", "y"}:
        raise ValueError("cradle orientation must be 'x' or 'y'")

    rib_thickness = options["rib_thickness"]
    spacing = options["spacing"]
    floor_gap = options["floor_gap"]

    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width
    if item.length > run:
        raise ValueError(
            f"{item.name} is {item.length:g} mm long but its zone only runs "
            f"{run:.1f} mm along {along}"
        )

    # every object is cradled on its centreline, so they share one axis height
    widest = item.held(item.widest)
    axis_z = base_z + floor_gap + widest / 2.0

    pitch = widest + spacing + rib_thickness
    count = spec_feature.count
    if count is None:
        count = _fit_count(across, pitch, widest + rib_thickness)
    if count < 1:
        raise ValueError(
            f"no room for {item.name}: {across:.1f} mm across needs at least "
            f"{widest + rib_thickness:.1f} mm"
        )
    used = (count - 1) * pitch + widest + rib_thickness
    if used > across + 1e-9:
        raise ValueError(
            f"{count} x {item.name} needs {used:.1f} mm across but the zone "
            f"gives {across:.1f} mm"
        )

    # centre the row of objects in the zone
    centre_along, centre_across = zone.centre
    if along != "x":
        centre_along, centre_across = centre_across, centre_along
    first = centre_across - (count - 1) * pitch / 2.0
    start = centre_along - item.length / 2.0

    solids: list[trimesh.Trimesh] = []
    for offset, segment in item.segment_centres():
        radius = item.held(segment.diameter) / 2.0
        rib_height = axis_z - base_z
        if radius >= rib_height:
            raise ValueError(
                f"{item.name}: a {segment.diameter:g} mm section needs more than "
                f"{floor_gap:g} mm of clearance under it to leave material below"
            )
        rib = trimesh.creation.box(
            extents=(
                rib_thickness if along == "x" else across,
                across if along == "x" else rib_thickness,
                rib_height,
            )
        )
        here = start + offset
        rib.apply_translation(
            (here, centre_across, base_z + rib_height / 2.0) if along == "x"
            else (centre_across, here, base_z + rib_height / 2.0)
        )
        notches = []
        for index in range(count):
            seat = first + index * pitch
            notch = trimesh.creation.cylinder(
                radius=radius, height=rib_thickness * 3.0, sections=48
            )
            # lay the notch along the object's axis
            notch.apply_transform(
                trimesh.transformations.rotation_matrix(
                    math.pi / 2.0, (0, 1, 0) if along == "x" else (1, 0, 0)
                )
            )
            notch.apply_translation(
                (here, seat, axis_z) if along == "x" else (seat, here, axis_z)
            )
            notches.append(notch)
        solids.append(difference([rib, union(notches)]))
    return solids


# --- contour nests ------------------------------------------------------------


def _item_plan_outline(
    item: Item, along: str, centre_along: float, centre_across: float
) -> Polygon:
    """Top-down stepped outline of an item, kept inside its stated length."""
    start = centre_along - item.length / 2.0 - item.clearance / 2.0
    pieces = []
    run = start
    for index, segment in enumerate(item.segments):
        radius = item.held(segment.diameter) / 2.0
        length = segment.length
        if index == 0:
            length += item.clearance / 2.0
        if index == len(item.segments) - 1:
            length += item.clearance / 2.0
        if along == "x":
            pieces.append(shapely_box(
                run, centre_across - radius,
                run + length, centre_across + radius,
            ))
        else:
            pieces.append(shapely_box(
                centre_across - radius, run,
                centre_across + radius, run + length,
            ))
        run += length
    outline = unary_union(pieces)
    if not isinstance(outline, Polygon):
        raise ValueError(f"{item.name}: its segments do not make one contour")
    return outline


@defaults("nest")
def nest_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    # Deep enough to hold the tool without swallowing it, and never so deep
    # that the recess turns into a well you cannot get a fingernail into.
    recess = min(max(item.held(item.widest) * 0.3, 2.0), 8.0)
    return {
        "wall": BORE_WALL,
        "depth": recess,
        "height": one.options.get("depth", recess) + BASE_PLATE,
    }


@feature("nest")
def build_nest(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A shallow, snug top-down recess following an item's stepped outline.

    Unlike a cradle this supports the whole item. The recess is cut straight
    down, so it has no hidden undercut and remains support-free to print.
    """
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    wall = options["wall"]
    recess_depth = options["depth"]
    height = options["height"]
    if (
        not all(math.isfinite(value) for value in (wall, recess_depth, height))
        or wall <= 0.0
        or recess_depth <= 0.0
        or height <= recess_depth
    ):
        raise ValueError(
            f"a nest {recess_depth:g} mm deep needs a height above {recess_depth:g} mm "
            f"to leave a printable base, but its height is {height:g} mm"
        )

    along = spec_feature.along
    run = zone.width if along == "x" else zone.depth
    across = zone.depth if along == "x" else zone.width
    widest = item.held(item.widest)
    required_run = item.length + item.clearance + 2.0 * wall
    if required_run > run + 1e-9:
        raise ValueError(
            f"{item.name} needs {required_run:.1f} mm along {along} "
            f"including the nest walls but the zone gives {run:.1f} mm"
        )

    count = spec_feature.count
    if count is None:
        count = max(0, int((across - wall) // (widest + wall)))
    if count < 1:
        raise ValueError(f"no room for {item.name}: the nest zone is too narrow")
    used = count * widest + (count + 1) * wall
    if used > across + 1e-9:
        raise ValueError(
            f"{count} x {item.name} nests need {used:.1f} mm across but the zone "
            f"gives {across:.1f} mm"
        )

    centre_along, centre_across = zone.centre
    if along != "x":
        centre_along, centre_across = centre_across, centre_along
    pitch = widest + wall
    first = centre_across - (count - 1) * pitch / 2.0
    cuts = []
    for index in range(count):
        outline = _item_plan_outline(item, along, centre_along, first + index * pitch)
        cut = _extrude_polygon(outline, recess_depth * 2.0)
        cut.apply_translation((0.0, 0.0, base_z + height - recess_depth))
        cuts.append(cut)

    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((*zone.centre, base_z + height / 2.0))
    return [difference([block, union(cuts)])]


# --- bores --------------------------------------------------------------------


@defaults("bore")
def bore_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    item = _need_item(one)
    hole = min(item.length * 0.4, box.z - base_z - 2.0)
    return {
        "depth": hole,
        "wall": BORE_WALL,
        "height": one.options.get("depth", hole) + 2.0,
    }


@feature("bore")
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)

    held = item.held(item.widest)
    depth = options["depth"]
    wall = options["wall"]
    height = options["height"]
    if depth <= 0.0 or height <= 0.0 or wall <= 0.0 or depth >= height:
        raise ValueError(
            f"{item.name}: bore depth must be below its positive height and wall"
        )

    pitch = held + wall
    raw_columns = options.get("columns")
    raw_rows = options.get("rows")
    columns = int(raw_columns) if raw_columns is not None else _fit_count(
        zone.width, pitch, held + wall
    )
    rows = int(raw_rows) if raw_rows is not None else _fit_count(
        zone.depth, pitch, held + wall
    )
    if ((raw_columns is not None and abs(float(raw_columns) - columns) > 1e-9)
            or (raw_rows is not None and abs(float(raw_rows) - rows) > 1e-9)):
        raise ValueError("bore columns and rows must be whole numbers")
    if spec_feature.count is not None:
        columns = min(columns, spec_feature.count)
        rows = max(1, math.ceil(spec_feature.count / max(columns, 1)))
    if columns < 1 or rows < 1:
        raise ValueError(f"no room for {item.name}: zone is too small for a bore")
    needed_x = (columns - 1) * pitch + held + wall
    needed_y = (rows - 1) * pitch + held + wall
    if needed_x > zone.width + 1e-9 or needed_y > zone.depth + 1e-9:
        raise ValueError(
            f"{columns} x {rows} bores need {needed_x:.1f} x {needed_y:.1f} mm "
            f"but the zone gives {zone.width:.1f} x {zone.depth:.1f} mm"
        )

    centre_x, centre_y = zone.centre
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))

    holes = []
    made = 0
    for row in range(rows):
        for column in range(columns):
            if spec_feature.count is not None and made >= spec_feature.count:
                break
            x = centre_x + (column - (columns - 1) / 2.0) * pitch
            y = centre_y + (row - (rows - 1) / 2.0) * pitch
            sections = {"round": 48, "hex": 6, "square": 4}[item.profile]
            hole = trimesh.creation.cylinder(
                radius=held / 2.0 / (math.cos(math.pi / sections) if sections < 8 else 1.0),
                height=depth * 2.0,
                sections=sections,
            )
            hole.apply_translation((x, y, base_z + height + depth - depth))
            holes.append(hole)
            made += 1
    return [difference([block, union(holes)])]


# --- posts --------------------------------------------------------------------


@defaults("post")
def post_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {"diameter": 12.0, "height": 16.0, "spacing": 4.0, "taper": 0.4}


@feature("post")
def build_post(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """One or more lightly tapered pegs for rolls, spools, rings and sockets."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    diameter = options["diameter"]
    height = options["height"]
    spacing = options["spacing"]
    taper = options["taper"]
    if (
        not all(math.isfinite(value) for value in (diameter, height, spacing, taper))
        or diameter <= 0.0
        or height <= 0.0
        or spacing < 0.0
        or taper < 0.0
        or taper >= diameter
    ):
        raise ValueError(
            "post diameter and height must be positive; spacing and taper must "
            "be non-negative, with taper smaller than the diameter"
        )

    run = zone.width if spec_feature.along == "x" else zone.depth
    across = zone.depth if spec_feature.along == "x" else zone.width
    count = spec_feature.count or 1
    used = count * diameter + (count - 1) * spacing
    if diameter > across + 1e-9 or used > run + 1e-9:
        raise ValueError(
            f"{count} posts need {used:.1f} x {diameter:.1f} mm but the zone "
            f"gives {run:.1f} x {across:.1f} mm"
        )

    centre_x, centre_y = zone.centre
    first = -(count - 1) * (diameter + spacing) / 2.0
    posts = []
    for index in range(count):
        offset = first + index * (diameter + spacing)
        post = trimesh.creation.revolve(
            [
                (0.0, 0.0),
                (diameter / 2.0, 0.0),
                ((diameter - taper) / 2.0, height),
                (0.0, height),
            ],
            sections=48,
        )
        post.apply_translation(
            (centre_x + offset, centre_y, base_z)
            if spec_feature.along == "x"
            else (centre_x, centre_y + offset, base_z)
        )
        posts.append(post)
    return posts


# --- plain shapes -------------------------------------------------------------


@defaults("divider")
def divider_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {
        "thickness": RIB_THICKNESS,
        "height": connector_keep_out(box) - base_z,
        "angle": 0.0,
    }


def _divider_cross_centres(zone: Zone, along: str, count: int) -> list[float]:
    """``count`` positions evenly spaced across the zone's cross axis.

    Fence-post spacing: ``count`` dividers split the span into ``count + 1``
    equal gaps, so at ``count == 1`` the one divider lands exactly on the
    zone's own centre - identical to the plain single-divider case this
    generalises.
    """
    low, high = (zone.y0, zone.y1) if along == "x" else (zone.x0, zone.x1)
    span = high - low
    return [low + (index + 1) * span / (count + 1) for index in range(count)]


@feature("divider")
def build_divider(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """One or more evenly spaced parallel walls subdividing the bin."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    thickness = options["thickness"]
    height = options["height"]
    angle = options.get("angle", 0.0)
    if thickness <= 0.0 or height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("divider thickness and height must fit inside the bin")
    along = spec_feature.along
    count = spec_feature.count or 1
    if count < 1:
        raise ValueError("divider count must be positive or automatic")
    centres = _divider_cross_centres(zone, along, count)
    if count > 1:
        span = (zone.y1 - zone.y0) if along == "x" else (zone.x1 - zone.x0)
        lean = height * math.tan(math.radians(angle)) if angle else 0.0
        spacing = centres[1] - centres[0]
        needed = thickness + 2.0 * abs(lean)
        if spacing < needed:
            raise ValueError(
                f"{count} dividers need at least {needed * (count + 1):.1f} mm "
                f"across but the zone gives {span:.1f} mm"
            )
    solids: list[trimesh.Trimesh] = []
    for cross_centre in centres:
        shift = cross_centre - (zone.centre[1] if along == "x" else zone.centre[0])
        one_zone = (
            Zone(zone.x0, zone.y0 + shift, zone.x1, zone.y1 + shift) if along == "x"
            else Zone(zone.x0 + shift, zone.y0, zone.x1 + shift, zone.y1)
        )
        one = replace(spec_feature, zone=one_zone)
        if angle != 0.0 and one.full_span:
            solids.extend(_full_span_leaning_divider(box, one, thickness, height, angle, base_z))
        elif one.full_span:
            solids.extend(_full_span_divider(box, along, cross_centre, thickness, base_z, height))
        else:
            solids.extend(_divider_wall(box, one, thickness, height, angle, base_z))
    return solids


def _divider_wall(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """A straight or leaning divider, up to ``MAX_DIVIDER_ANGLE`` off vertical.

    A thin wall sheared over bodily at an angle is an unsupported FDM
    overhang with no more material at its base than anywhere else along its
    height - exactly the shape that snaps off under the sideways load of
    whatever is leaning against it. The default instead builds a wedge: the
    back face stays vertical and only the leaning face slopes, so the wall
    is thickest right where that load actually bears - at the floor - and
    tapers away toward the top, the shape a physical gusset or bracket would
    use. ``wedge=False`` gets the plain sheared wall instead: uniform
    thickness throughout, for the rare case that is genuinely wanted.

    Every divider - wedge, straight or plain vertical - also gets a
    ``DIVIDER_CHAMFER`` 45-degree foot where it meets the floor: the two
    long faces flare out by that much at ``base_z`` and taper back to the
    wall's own line by ``DIVIDER_CHAMFER`` above it. It is a pure addition
    below the wall's nominal profile, not a substitute for any of it, so
    the lean and thickness above that point are exactly what was asked for.
    """
    if not math.isfinite(angle) or abs(angle) > MAX_DIVIDER_ANGLE:
        raise ValueError(
            f"a divider's angle must be within {MAX_DIVIDER_ANGLE:g} degrees of vertical"
        )
    if height <= DIVIDER_CHAMFER:
        raise ValueError(
            f"a divider must stand taller than its {DIVIDER_CHAMFER:g} mm base chamfer"
        )
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
    along = spec_feature.along
    cross_centre = centre_y if along == "x" else centre_x
    lean = height * math.tan(math.radians(angle))
    half_t = thickness / 2.0
    base_low, base_high = cross_centre - half_t, cross_centre + half_t
    if spec_feature.wedge:
        if lean >= 0.0:
            top_low, top_high = base_low, base_high - lean
        else:
            top_low, top_high = base_low - lean, base_high
        if top_high - top_low < MIN_WEDGE_EDGE:
            raise ValueError(
                f"that angle and height taper the divider to less than "
                f"{MIN_WEDGE_EDGE:g} mm at the top; reduce the angle or "
                "increase the thickness"
            )
    else:
        top_low, top_high = base_low + lean, base_high + lean
    # Where the wall's own (un-chamfered) line would sit at chamfer height -
    # the chamfer's inner edge lands exactly here, so the taper above it is
    # untouched.
    frac = DIVIDER_CHAMFER / height
    chamfer_low = base_low + frac * (top_low - base_low)
    chamfer_high = base_high + frac * (top_high - base_high)
    chamfer_z = base_z + DIVIDER_CHAMFER
    profile = Polygon([
        (base_low - DIVIDER_CHAMFER, base_z), (base_high + DIVIDER_CHAMFER, base_z),
        (chamfer_high, chamfer_z), (top_high, base_z + height),
        (top_low, base_z + height), (chamfer_low, chamfer_z),
    ])
    if not profile.is_valid:
        raise ValueError("that divider angle and thickness do not form a valid wall")
    run = zone.width if along == "x" else zone.depth
    if along == "x":
        wall = _extrude_yz_profile(profile, run)
        wall.apply_translation((centre_x, 0.0, 0.0))
    else:
        wall = _extrude_xz_profile(profile, run)
        wall.apply_translation((0.0, centre_y, 0.0))
    return [wall]


def _full_span_leaning_divider(
    box: BoxSpec, spec_feature: Feature, thickness: float, height: float,
    angle: float, base_z: float,
) -> list[trimesh.Trimesh]:
    """A leaning divider that also reaches the box's true wavy wall.

    Full span and a lean each bend one of the same assumption in a
    different place: a full-span divider's run-axis reach is the wave, not
    the safe rectangle; a leaning divider's cross-axis position shifts with
    height instead of staying put. Together, the divider's own end face is
    no longer flat, or even the same shape at every height, so the 2D
    polygon-clip the plain full-span divider uses no longer applies on its
    own. This instead builds the oversized leaning wedge as a real 3D solid
    - exactly what ``_divider_wall`` already builds (base chamfer included),
    just wider - and intersects it against the box's actual interior
    volume, the same boolean a standalone insert is already trimmed to its
    footprint with.
    """
    along = spec_feature.along
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    zone = spec_feature.zone
    centre_x, centre_y = zone.centre
    oversized_zone = (
        Zone(centre_x - half_run, zone.y0, centre_x + half_run, zone.y1)
        if along == "x" else
        Zone(zone.x0, centre_y - half_run, zone.x1, centre_y + half_run)
    )
    wedge = _divider_wall(
        box, replace(spec_feature, zone=oversized_zone), thickness, height,
        angle, base_z,
    )[0]

    z0, z1 = base_z, base_z + height
    flat_top = box.wall + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        band = _extrude_polygon(flat_cavity_polygon(box), min(z1, flat_top) - z0)
        band.apply_translation((0.0, 0.0, z0))
        pieces.append(intersection([wedge, band]))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        above = _extrude_polygon(wavy_cavity_polygon(box), z1 - wavy_z0)
        above.apply_translation((0.0, 0.0, wavy_z0))
        pieces.append(intersection([wedge, above]))
    if not pieces or any(len(piece.faces) == 0 for piece in pieces):
        raise ValueError("no room for a leaning full-width divider at this position")
    return pieces


def _trimmed_prism(strip: Polygon, cavity: Polygon, z0: float, z1: float) -> trimesh.Trimesh:
    """``strip`` cut back to wherever ``cavity`` actually allows it, then extruded."""
    trimmed = strip.intersection(cavity)
    if trimmed.is_empty:
        raise ValueError("no room for a full-width divider at this position")
    if isinstance(trimmed, MultiPolygon):
        trimmed = max(trimmed.geoms, key=lambda item: item.area)
    prism = _extrude_polygon(trimmed, z1 - z0)
    prism.apply_translation((0.0, 0.0, z0))
    return prism


def _full_span_divider(
    box: BoxSpec, along: str, cross_centre: float, thickness: float,
    base_z: float, height: float,
) -> list[trimesh.Trimesh]:
    """A divider that runs edge to edge, hugging the box's true interior wall.

    A straight rib sized to the safe usable rectangle - the only rectangle
    guaranteed to clear the wave at *every* position - still leaves the
    wave's own swing as a gap at most positions, because that rectangle is
    pulled in by a full amplitude just to stay valid everywhere. A divider
    only has to be right at its own position, so instead it is built
    oversized and trimmed back against the box's real interior outline: the
    flat, straight-sided band near the floor if the box has one, the wavy
    profile above it - exactly the same outlines the wall itself is built
    from, so the two can never disagree.
    """
    half_run = (box.half_x if along == "x" else box.half_y) + 2.0 * WAVE_AMPLITUDE
    half_thick = thickness / 2.0
    strip = (
        shapely_box(-half_run, cross_centre - half_thick, half_run, cross_centre + half_thick)
        if along == "x" else
        shapely_box(cross_centre - half_thick, -half_run, cross_centre + half_thick, half_run)
    )
    z0, z1 = base_z, base_z + height
    flat_top = box.wall + box.flat_inside
    pieces: list[trimesh.Trimesh] = []
    if box.flat_inside > 0.0 and z0 < flat_top:
        pieces.append(_trimmed_prism(strip, flat_cavity_polygon(box), z0, min(z1, flat_top)))
    wavy_z0 = max(z0, flat_top) if box.flat_inside > 0.0 else z0
    if wavy_z0 < z1:
        pieces.append(_trimmed_prism(strip, wavy_cavity_polygon(box), wavy_z0, z1))
    if not pieces:
        raise ValueError("divider height leaves nothing to build")
    return pieces


@defaults("pocket")
def pocket_defaults(box: BoxSpec, one: "Feature", base_z: float) -> dict[str, float]:
    return {
        "height": 12.0,
        "wall": 1.6,
        "depth": one.options.get("height", 12.0) - 1.2,
    }


@feature("pocket")
def build_pocket(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A raised block with a rectangular recess in it."""
    zone = spec_feature.zone
    options = resolved_options(box, spec_feature, base_z)
    height = options["height"]
    wall = options["wall"]
    depth = options["depth"]
    if (height <= 0.0 or wall <= 0.0 or depth <= 0.0 or depth >= height
            or 2 * wall >= zone.width or 2 * wall >= zone.depth):
        raise ValueError("pocket wall and depth must leave a positive shell")
    centre_x, centre_y = zone.centre
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))
    inner = trimesh.creation.box(
        extents=(zone.width - 2 * wall, zone.depth - 2 * wall, depth * 2.0)
    )
    inner.apply_translation((centre_x, centre_y, base_z + height + depth - depth))
    return [difference([block, inner])]


# --- putting an insert together ----------------------------------------------


def connector_keep_out(box: BoxSpec, connector: ConnectorSpec | None = None) -> float:
    """Height above which an insert would foul a seated connector's arms."""
    connector = connector or ConnectorSpec()
    return box.z - connector.arm_depth


def _feature_reach(box: BoxSpec, one: Feature, base_z: float) -> Zone:
    """How far a feature's own built geometry may legitimately extend.

    For an ordinary feature this is simply its stored zone - the builder is
    never allowed to produce anything bigger than what the editor placed. A
    divider is built from its own ``thickness`` option on the cross axis,
    not from the zone's stored footprint there (see ``build_divider``), so
    the two can disagree - typing a thicker wall than the zone happened to
    be does not, on its own, mean anything is actually wrong. The reach
    widens on the cross axis to whichever is bigger. Two more deliberate
    divider exceptions stack on top (see ``build_divider``): full-span
    reaches past its stored zone along its run axis, all the way to the
    box's true wavy wall, so its reach widens there to the box's own
    physical envelope - the one bound nothing can legitimately cross; a
    leaning divider reaches further still on the cross axis, by however far
    its own lean carries it.
    """
    if one.kind != "divider":
        return one.zone
    zone = one.zone
    if one.full_span:
        if one.along == "x":
            zone = Zone(-box.half_x, zone.y0, box.half_x, zone.y1)
        else:
            zone = Zone(zone.x0, -box.half_y, zone.x1, box.half_y)
    options = resolved_options(box, one, base_z)
    thickness = options.get("thickness", 0.0)
    angle = options.get("angle", 0.0)
    lean = abs(options["height"] * math.tan(math.radians(angle))) if angle else 0.0
    # The base chamfer comes from _divider_wall, used by every divider except
    # a straight (non-leaning) full-span one, which is built by a separate,
    # simpler clip-and-extrude path with no chamfer (see build_divider).
    chamfer = 0.0 if (one.full_span and angle == 0.0) else DIVIDER_CHAMFER
    # Margin each individual wall may reach past its own centre line. With
    # more than one (see build_divider), every centre sits strictly inside
    # the zone's own cross span, so widening that span by this margin on
    # each side always covers every wall - not the tightest possible bound,
    # but a safe one that does not need each wall's exact position redone
    # here too.
    margin = thickness / 2.0 + lean + chamfer
    if one.along == "x":
        zone = Zone(zone.x0, zone.y0 - margin, zone.x1, zone.y1 + margin)
    else:
        zone = Zone(zone.x0 - margin, zone.y0, zone.x1 + margin, zone.y1)
    return zone


def check_layout(
    box: BoxSpec, features: Iterable[Feature], bounds: Zone | None = None
) -> None:
    """Catch the mistakes that produce quietly wrong parts."""
    features = list(features)
    whole = bounds or Zone.whole(box)
    for one in features:
        if one.kind not in FEATURE_BUILDERS:
            raise ValueError(
                f"unknown holder {one.kind!r}; have "
                f"{', '.join(sorted(FEATURE_BUILDERS))}"
            )
        if (one.zone.x0 < whole.x0 - 1e-6 or one.zone.x1 > whole.x1 + 1e-6
                or one.zone.y0 < whole.y0 - 1e-6 or one.zone.y1 > whole.y1 + 1e-6):
            raise ValueError(
                f"a {one.kind} reaches outside the bin: its zone is "
                f"{one.zone.width:.1f} x {one.zone.depth:.1f} mm at "
                f"({one.zone.x0:.1f}, {one.zone.y0:.1f}) but the bin gives "
                f"{whole.width:.1f} x {whole.depth:.1f} mm"
            )
    for index, one in enumerate(features):
        for other in features[index + 1:]:
            if one.zone.overlaps(other.zone, MIN_FEATURE_GAP):
                raise ValueError(
                    f"a {one.kind} and a {other.kind} overlap; leave at least "
                    f"{MIN_FEATURE_GAP:g} mm between features"
                )


def build_features(
    box: BoxSpec, features: Iterable[Feature], base_z: float,
    bounds: Zone | None = None,
) -> list[trimesh.Trimesh]:
    features = list(features)
    check_layout(box, features, bounds)
    solids: list[trimesh.Trimesh] = []
    for one in features:
        made = FEATURE_BUILDERS[one.kind](box, one, base_z)
        reach = _feature_reach(box, one, base_z)
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
        whole = Zone.whole(box)
        touches_wall = (
            one.zone.x0 <= whole.x0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.x1 >= whole.x1 - CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y0 <= whole.y0 + CONNECTOR_EDGE_KEEP_OUT
            or one.zone.y1 >= whole.y1 - CONNECTOR_EDGE_KEEP_OUT
        )
        if touches_wall and any(
            solid.bounds[1][2] > connector_keep_out(box) + 1e-6 for solid in made
        ):
            raise ValueError(
                f"a {one.kind} touching the wall must stay below "
                f"{connector_keep_out(box):.1f} mm so a connector can seat"
            )
        solids.extend(made)
    return solids


def insert_footprint(box: BoxSpec, mode: str = "separate") -> Polygon:
    """The floor outline of a standalone insert.

    The layout area pulled in by ``INSERT_CLEARANCE`` all round with softened
    corners.  That clearance is the whole reason a removable insert can go in
    and come back out, so the preview draws this same outline rather than the
    bare layout rectangle.
    """
    bounds = layout_zone(box, mode)
    return _rounded(
        shapely_box(
            bounds.x0 + INSERT_CLEARANCE, bounds.y0 + INSERT_CLEARANCE,
            bounds.x1 - INSERT_CLEARANCE, bounds.y1 - INSERT_CLEARANCE,
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
    plate = _extrude_polygon(footprint, BASE_PLATE)
    # Validate and size holders at their installed height, then lower them by
    # the bin floor thickness so the removable insert still exports on z=0.
    parts = build_features(box, features, BASE_PLATE + box.wall)
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.wall))
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
    plate = _extrude_polygon(footprint, BASE_PLATE)
    parts = build_features(box, features, BASE_PLATE + box.wall, bounds)
    for part in parts:
        part.apply_translation((0.0, 0.0, -box.wall))
    body = union([plate] + parts) if parts else plate
    limit = _extrude_polygon(footprint, box.z * 2.0)
    return intersection([body, limit])


def make_fused_box(
    box: BoxSpec, features: Iterable[Feature], box_mesh: trimesh.Trimesh
) -> trimesh.Trimesh:
    """The bin with its holders grown straight out of the floor."""
    parts = build_features(box, features, box.wall)
    if not parts:
        return box_mesh
    return union([box_mesh, *parts])


def insert_report(name: str, features: Iterable[Feature], mesh: trimesh.Trimesh) -> dict:
    features = list(features)
    return {
        "name": name,
        "features": len(features),
        "kinds": sorted({f.kind for f in features}),
        "volume_cc": round(float(mesh.volume) / 1000.0, 3),
        "watertight": bool(mesh.is_watertight),
    }


# --- a starter library --------------------------------------------------------
#
# Measured nominal sizes. Extend freely; nothing here is special.

LIBRARY: dict[str, Item] = {
    "pencil": Item.simple("Pencil", 175.0, 7.5),
    "sharpie": Item.simple("Sharpie", 140.0, 14.0),
    "glue_stick": Item.simple("Glue stick", 100.0, 11.0),
    "hex_driver": Item(
        "Hex driver", (Segment(50.0, 6.0), Segment(30.0, 18.0))
    ),
    "screwdriver": Item(
        "Screwdriver", (Segment(90.0, 5.0), Segment(80.0, 22.0))
    ),
    "deburr_tool": Item("Deburring tool", (Segment(40.0, 6.0), Segment(60.0, 12.0))),
    "tweezers": Item.simple("Tweezers", 120.0, 8.0),
    "nozzle": Item.simple("Printer nozzle", 13.0, 6.0),
}
