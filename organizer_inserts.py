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
from shapely.geometry import Polygon, box as shapely_box

from organizer_engine import (
    BoxSpec,
    ConnectorSpec,
    _extrude_polygon,
    _rounded,
    difference,
    intersection,
    union,
)

# --- how much room to leave ---------------------------------------------------

ITEM_CLEARANCE = 0.4       # slack around a stored object, on the diameter
RIB_THICKNESS = 1.6        # four perimeters at 0.4
RIB_SPACING = 1.2          # material left between two neighbouring cradles
BASE_PLATE = 1.2           # floor of a standalone insert
CRADLE_FLOOR_GAP = 2.0     # gap under the widest part of a lying object
BORE_WALL = 1.6            # material around a bore
INSERT_CLEARANCE = 0.4     # slack around a standalone insert, per side
MIN_FEATURE_GAP = 0.8      # material between two features
CONNECTOR_EDGE_KEEP_OUT = 2.0  # interior strip kept low for connector arms
EDITOR_SNAP = 1.0          # normal editor movement; effectively no floor loss
CARTRIDGE_PITCH = 8.0      # optional interchangeable standalone-insert grid
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

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a feature needs a kind")
        if self.along not in {"x", "y"}:
            raise ValueError("feature orientation must be 'x' or 'y'")
        if self.count is not None and self.count < 1:
            raise ValueError("feature count must be positive or automatic")


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
    options = spec_feature.options
    if along not in {"x", "y"}:
        raise ValueError("cradle orientation must be 'x' or 'y'")

    rib_thickness = options.get("rib_thickness", RIB_THICKNESS)
    spacing = options.get("spacing", RIB_SPACING)
    floor_gap = options.get("floor_gap", CRADLE_FLOOR_GAP)

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


# --- bores --------------------------------------------------------------------


@feature("bore")
def build_bore(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A block of holes for objects stood on end."""
    item = _need_item(spec_feature)
    zone = spec_feature.zone
    options = spec_feature.options

    held = item.held(item.widest)
    depth = options.get("depth", min(item.length * 0.4, box.z - base_z - 2.0))
    wall = options.get("wall", BORE_WALL)
    height = options.get("height", depth + 2.0)
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


# --- plain shapes -------------------------------------------------------------


@feature("divider")
def build_divider(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A plain wall subdividing the bin."""
    zone = spec_feature.zone
    options = spec_feature.options
    thickness = options.get("thickness", RIB_THICKNESS)
    height = options.get("height", connector_keep_out(box) - base_z)
    if thickness <= 0.0 or height <= 0.0 or base_z + height > box.z + 1e-9:
        raise ValueError("divider thickness and height must fit inside the bin")
    centre_x, centre_y = zone.centre
    if spec_feature.along == "x":
        extents = (zone.width, thickness, height)
    else:
        extents = (thickness, zone.depth, height)
    wall = trimesh.creation.box(extents=extents)
    wall.apply_translation((centre_x, centre_y, base_z + height / 2.0))
    return [wall]


@feature("pocket")
def build_pocket(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """A raised block with a rectangular recess in it."""
    zone = spec_feature.zone
    options = spec_feature.options
    height = options.get("height", 12.0)
    wall = options.get("wall", 1.6)
    depth = options.get("depth", height - 1.2)
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


@feature("slot")
def build_slot(box: BoxSpec, spec_feature: Feature, base_z: float) -> list[trimesh.Trimesh]:
    """Parallel straight slots for flat things."""
    zone = spec_feature.zone
    options = spec_feature.options
    width = options.get("width", 2.0)
    height = options.get("height", 12.0)
    depth = options.get("depth", height - 2.0)
    wall = options.get("wall", 1.6)
    if (width <= 0.0 or wall <= 0.0 or height <= 0.0 or depth <= 0.0
            or depth >= height):
        raise ValueError("slot dimensions must leave a positive base")
    pitch = width + wall
    across = zone.depth if spec_feature.along == "x" else zone.width
    count = spec_feature.count or _fit_count(across, pitch, width + wall)
    if count < 1:
        raise ValueError("no room for a slot")
    needed = (count - 1) * pitch + width + wall
    if needed > across + 1e-9:
        raise ValueError(
            f"{count} slots need {needed:.1f} mm across but the zone gives {across:.1f} mm"
        )
    centre_x, centre_y = zone.centre
    block = trimesh.creation.box(extents=(zone.width, zone.depth, height))
    block.apply_translation((centre_x, centre_y, base_z + height / 2.0))
    cuts = []
    for index in range(count):
        offset = (index - (count - 1) / 2.0) * pitch
        if spec_feature.along == "x":
            extents, position = ((zone.width * 2.0, width, depth * 2.0),
                                 (centre_x, centre_y + offset, base_z + height))
        else:
            extents, position = ((width, zone.depth * 2.0, depth * 2.0),
                                 (centre_x + offset, centre_y, base_z + height))
        cut = trimesh.creation.box(extents=extents)
        cut.apply_translation(position)
        cuts.append(cut)
    return [difference([block, union(cuts)])]


# --- putting an insert together ----------------------------------------------


def connector_keep_out(box: BoxSpec, connector: ConnectorSpec | None = None) -> float:
    """Height above which an insert would foul a seated connector's arms."""
    connector = connector or ConnectorSpec()
    return box.z - connector.arm_depth


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
            if one.zone.overlaps(other.zone, -MIN_FEATURE_GAP):
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


def make_fitted_insert(
    box: BoxSpec, features: Iterable[Feature]
) -> trimesh.Trimesh:
    """A standalone insert that drops into this bin.

    It gets its own base plate and is pulled in by ``INSERT_CLEARANCE`` all
    round so it actually goes in, which is the cost of being able to lift it
    out and swap it.
    """
    whole = Zone.whole(box)
    footprint = _rounded(
        shapely_box(
            whole.x0 + INSERT_CLEARANCE, whole.y0 + INSERT_CLEARANCE,
            whole.x1 - INSERT_CLEARANCE, whole.y1 - INSERT_CLEARANCE,
        ),
        1.0,
    )
    plate = _extrude_polygon(footprint, BASE_PLATE)
    parts = build_features(box, features, BASE_PLATE)
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
    footprint = _rounded(
        shapely_box(
            bounds.x0 + INSERT_CLEARANCE, bounds.y0 + INSERT_CLEARANCE,
            bounds.x1 - INSERT_CLEARANCE, bounds.y1 - INSERT_CLEARANCE,
        ),
        1.0,
    )
    plate = _extrude_polygon(footprint, BASE_PLATE)
    parts = build_features(box, features, BASE_PLATE, bounds)
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
