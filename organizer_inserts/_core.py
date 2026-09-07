"""Shared data, serialization, snapping, and foundation helpers."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path

from shapely.geometry import Polygon, box as shapely_box

from organizer_engine import BoxSpec, ConnectorSpec


ITEM_CLEARANCE = 0.4       # slack around a stored object, on the diameter
BASE_PLATE = 0.6           # floor of a standalone insert
INSERT_CLEARANCE = 0.2     # slack around a standalone insert, per side
MIN_FEATURE_GAP = 0.8      # material between two features
CONNECTOR_EDGE_KEEP_OUT = 2.0  # interior strip kept low for connector arms
EDITOR_SNAP = 1.0          # normal editor movement; effectively no floor loss
CARTRIDGE_PITCH = 8.0      # optional interchangeable standalone-insert grid
LAYOUT_MODES = ("fused", "separate", "cartridge")


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
    ``(Segment(50, 6), Segment(30, 18))`` - shaft then handle. A bore and a
    cradle use the relevant overall dimensions; Photo Nest uses its own polygon.
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
        if self.profile not in {
            "round", "hex", "square", "hex_bit_short", "hex_bit_long"
        }:
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

    def segment_centres(self, reversed_end: bool = False) -> list[tuple[float, Segment]]:
        """Each segment's midpoint measured from the selected near end."""
        out, run = [], 0.0
        segments = reversed(self.segments) if reversed_end else self.segments
        for segment in segments:
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
    # For repeated cradles, turn every second stored item end-for-end so
    # neighbouring handles and shafts interleave.
    alternate_ends: bool = False
    # Photo Nest stores only its cleaned, millimetre-based local outline plus
    # reversible editor transforms. The source image never enters a design.
    contour: tuple[tuple[float, float], ...] | None = None
    rotation: float = 0.0
    scale: float = 1.0

    def __post_init__(self) -> None:
        if not self.kind:
            raise ValueError("a feature needs a kind")
        if self.along not in {"x", "y"}:
            raise ValueError("feature orientation must be 'x' or 'y'")
        if self.count is not None and self.count < 1:
            raise ValueError("feature count must be positive or automatic")
        if self.full_span and self.kind != "divider":
            raise ValueError("only a divider can span the full wall")
        if self.alternate_ends and self.kind != "cradle":
            raise ValueError("only a cradle can alternate item ends")
        if not math.isfinite(self.rotation):
            raise ValueError("feature rotation must be finite")
        if not math.isfinite(self.scale) or self.scale <= 0.0:
            raise ValueError("feature scale must be positive and finite")
        if self.contour is not None:
            polygon = Polygon(self.contour)
            if (len(self.contour) < 3 or not polygon.is_valid
                    or polygon.is_empty or polygon.area <= 0.0):
                raise ValueError("a photo nest needs one valid closed contour")


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
        # Import locally to keep the shared core independent at module load time.
        from ._layout import check_layout

        bounds = layout_zone(box, self.mode)
        # Fused holders stand on the bin floor; that is the only mode whose
        # Spacing is judged on real footprints at the top of the bin floor.
        check_layout(box, self.features, bounds, box.base_thickness, self.mode)
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
                "alternate_ends": one.alternate_ends,
                "contour": [list(point) for point in one.contour] if one.contour else None,
                "rotation": one.rotation,
                "scale": one.scale,
            }
            for one in layout.features
        ],
    }


def layout_from_dict(data: dict) -> Layout:
    if data.get("version", 1) != 1:
        raise ValueError(f"unsupported layout version {data.get('version')!r}")
    made = []
    for raw in data.get("features", []):
        if raw.get("kind") == "nest" and not raw.get("contour"):
            raise ValueError(
                "this design uses the retired measured Nest; upload a part photo to create a new Photo Nest"
            )
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
            bool(raw.get("alternate_ends", False)),
            (tuple((float(point[0]), float(point[1])) for point in raw["contour"])
             if raw.get("contour") else None),
            float(raw.get("rotation", 0.0)),
            float(raw.get("scale", 1.0)),
        ))
    return Layout(tuple(made), str(data.get("mode", "fused")),
                  float(data.get("snap", EDITOR_SNAP)))


def save_layout(layout: Layout, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(layout_to_dict(layout), indent=2) + "\n", encoding="utf-8")


def load_layout(path: Path) -> Layout:
    return layout_from_dict(json.loads(path.read_text(encoding="utf-8")))


def _need_item(spec_feature: Feature) -> Item:
    if spec_feature.item is None:
        raise ValueError(f"a {spec_feature.kind} needs an item to hold")
    return spec_feature.item


def _fit_count(available: float, pitch: float, body: float) -> int:
    """How many bodies of ``body`` fit at ``pitch``, given the run available."""
    if available < body:
        return 0
    return int((available - body) // pitch) + 1


def connector_keep_out(box: BoxSpec, connector: ConnectorSpec | None = None) -> float:
    """Height above which an insert would foul a seated connector's arms."""
    connector = connector or ConnectorSpec()
    return box.z - connector.arm_depth


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
