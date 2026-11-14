# Wavefinity AI Feature Reference

Browser AI Help supports optional direct chat with the person's own session
key for OpenAI-compatible, Anthropic or Gemini providers that permit browser
access. Manual copy/paste is always available. Invoking AI shares the prompt
and design/Space descriptors with the chosen provider; geometry, meshes and
folder files remain on the PC. Never request or return credentials in an AI
design response. Unsupported browsers have temporary previews/downloads
only, with no Space autosave. Recovery means opening the same site in Windows
desktop Chrome/Edge and selecting the original folder, or importing a saved
Space/preferences export there; no automatic cross-browser transfer exists.
B14 still owns final route assembly. See
[browser capabilities](docs/static-capability-differences.md).

Ordinary Gridfinity bins may set `box.corner_feet` to `true` (default `false`)
to use only corner-cell feet (the UI's Feet: Corners only). Built-in wavy
supports, trimmed to the standard foot outline, carry the floor of the other
cells, so the bin still seats in a baseplate and needs no slicer supports.
Magnet pockets then occur only in the corner feet. `box.hollow_base` controls
whether the feet are hollow. Wavefinity bins ignore this option. Include it
only when requested.

Browser ordinary-output adapters use the same bin design schema and geometry
rules. Export prepares files locally for the person's chosen folder or a
download; multiple downloaded files travel together in a ZIP. Do not return
export URLs or claim files have been saved. Final browser route assembly is
a later migration package.

Browser drawer Print prepares a local 3MF for the person to open in Bambu
Studio. Printed changes only after their explicit confirmation for the same
Space and unchanged design/inventory; saving or downloading alone is not
confirmation. There is no persistent Prepared state. Never claim automatic
slicer launch or set inventory print status in an AI design response.

Browser structural adapters use the same rule for Storage Box, Storage
Drawers and Surface Print, including combined container/bin Print. They build
from the selected Space; cabinet structure is never an ordinary bin design
or inventory row. Container floors and all existing Gridfinity options retain
the canonical geometry and fit limits. External baseplate clearance remains
provisional; do not claim verified physical fit. Final browser route assembly
remains B14 work.

An ordinary bin on any supported grid may set `box.accent_band` to `true` for
a top 1 mm accent (default `false`). `box.accent_color` defaults to `"blue"`;
choices are blue, red, green, yellow, orange, purple, white and black. Include
the option only when requested. The color is nominal: the 3MF band's named
parts use filament slot 2 and the actual loaded filament determines the print.
The remaining body uses slot 1. An open stacking rim is part of the body's top;
the split preserves fit. Lids and removable inserts are unchanged. STL retains
the complete body without color separation. There is no adjustable band depth
or partial-band setting.

> **Audience:** External AI systems helping a person design one ordinary Wavefinity bin.
>
> **Purpose:** Public, compact background reference for Wavefinity AI Design. The AI Design prompt may link here instead of repeating every explanatory detail.
>
> **Authority rule:** The **request-specific prompt embedded by the running Wavefinity app wins** over this file whenever they differ. The prompt contains the exact current design, Space constraints, request/fingerprint, legal machine-readable values, and response contract needed for that request.
>
> **Maintenance rule:** Any change that adds, removes, or alters a design option must update this file in the same change. The embedded prompt and this reference must never disagree; if they do, the change is not finished.
>
> For the broader human product catalog, see `features.md`.

---

## Universal wave connections

Bins on the 7 mm placement grid can mate any compatible sides after a quarter,
half or three-quarter turn, including partial seams between different sizes.
The global-phase circular-arc walls and snap connectors share one profile.
Keep wall thicknesses compatible and allow enough common wall for a connector;
existing lid and height restrictions still apply. Arbitrary angles or off-grid
placement do not promise a mating fit. Regenerate neighbouring bins and clips
together: older sine-wave prints use a different profile. Walls follow the
same uninterrupted wave, with rounded, set-back corners and a small opening
where four bins meet. The corner-tightening wall recesses have been removed;
regenerate bins and side clips made with that profile as a set.

# 1. What the external AI is designing

AI Design designs **one ordinary Wavefinity Bin**.

In the browser edition, the person selects the writable folder. AI responses
must not supply local paths, folder handles or preferences, or promise that a
design has been saved. Folderless design and imported recovery data require an
explicit export to keep a portable copy; autosave requires granted folder access.

It does **not** design these Space-owned structural outputs:

- Storage Box case.
- Surface Base Trim.

The final answer is design **data**, not mesh/geometry. Wavefinity validates the data and builds the real geometry.

The outside AI may ask follow-up questions before giving the final JSON. It should ask whenever a critical size, fit, orientation, unit, or other necessary fact is missing or suspicious.

All Wavefinity design dimensions are in **millimetres**.

---

# 2. Request-specific information always supplied by Wavefinity

The generated AI Design prompt supplies the current authoritative values for the active request, including:

- user description;
- request ID;
- context fingerprint;
- current ordinary-bin design;
- current typed-Space context, when any;
- Space-controlled fields that must be preserved;
- legal option values/ranges/defaults from the running build;
- canonical design examples/shape;
- exact final JSON response contract.

This file is supplemental explanation. Do not substitute values from this file for different values explicitly supplied in the generated prompt.

---

# 3. Space context

Design data carries `grid`: `wavefinity` (7 mm), `gridfinity_half` (21 mm), or
`gridfinity` (42 mm). Keep it equal to the supplied Space/editor context. A
missing AI candidate grid inherits that context; an explicit conflict is refused.
The No-Space Designer offers a Grid selector with those three choices, defaulting
to Wavefinity. Select the grid before requesting AI Design; AI keeps that context.
Changing grid preserves millimetres and refuses dimensions that do not fit whole
cells. Width/Depth parse only on commit: `6u` means six cells, `6mm` is millimetres;
a bare positive number below the pitch means units, otherwise millimetres.
Units must be whole cells; millimetres snap to the nearest cell. Range errors
are refused, never clamped, and say how the input was read. The settled field shows
millimetres and unit count. AI design dimensions are validated as supplied:
off-pitch Gridfinity width or depth is refused with the nearest whole-cell sizes,
not snapped. Gridfinity height treats bare numbers as 7 mm units;
`mm` explicitly enters millimetres. Gridfinity bins have a 14 mm minimum; the model's floor, rim and lid minimums also apply;
Wavefinity height keeps plain millimetres. Space forms
keep their existing millimetre entry.
Gridfinity offers a Stackable rim (`box.stack.mode` direct; none is off), a loose Gridfinity Lid or a lid with a stacking
socket (`box.lid.enabled`, `box.lid.stack_rim`) on both pitches. Closed Z stays nominal in whole 7 mm units; the body and
interior shorten by the lid rise. A grid lid needs at least two height units and
enough body clearance for its floor and lid. Use the same footprint and pitch
when stacking on a grid lid; lid-on-lid uses the standard rim seat descent.
Label and handle lids and side connectors are Wavefinity options, hidden on
grid bodies. The Hinged lid is refused on both Gridfinity pitches (its open swing overruns the one-cell envelope and neighbour gap; nominal,
unverified), so it is not a Gridfinity Lid choice and each grid row carries a
`hinged_lid_refusal` message. A hinged lid is never also a Lid for stacking. The capability manifest filters lid choices by the
selected grid, using the same catalog as the editor.
Physical grid-lid fit is not yet print-confirmed.
Grid selection is available for No-Space bins, Plain Drawers, Storage Box and Storage Drawers only. Gridfinity Side Openings are available on both pitches subject to the protected zones below. Edge Mount is excluded because it projects beyond the cell envelope; only Andrew may approve a separate inside-envelope replacement.
A Space's grid is fixed when created. Bins cannot enter a Space
with a different grid. An external older design without a grid means Wavefinity;
a saved bin inside a Space inherits that source Space's grid.

Wavefinity may be used without a typed Space or inside one of these typed Spaces.

## Hard object-height cap

Drawer, Storage Box and the selected Storage Drawer are a hard vertical ceiling: the full physical envelope of a Bore-held object, including its width/profile and tilt, must remain below the Space's own height. Surface and Pegboard have no such cap, and neither does an ordinary Design with no active Space. The generated prompt always states which applies and, when capped, the exact height. This is a legality rule enforced by Wavefinity's own candidate check, not merely a style preference. Manual Design shows an advisory warning rather than blocking generation.

## Drawer

- Real usable drawer width, depth, and height.
- Returned bins must fit the active drawer constraints.
- Bin placement in the drawer happens later in Wavefinity.
- Hard object-height cap: the Drawer's own height.

## Surface

- Open-surface organization using a Space-owned Base Trim.
- Surface bin base behavior may be Space-controlled.
- Preserve any fields the generated prompt marks as Space-controlled.
- No hard object-height cap.
- Surface setup chooses maximum width and length and a Base Trim size; the usable field resolves to whole 7 mm units. Surface bins can use Auto base height (matching the trim edge) or Custom, a lightweight base, and a planning-only object height. The Space owns its Base Trim, which may be split to fit the printer.

## Storage Box

- The structural case's `storage_box.grid_stacking` (saved design: `box.b4b.grid_stacking`, default false) adds Gridfinity feet and a lid receiving ridge at 21 or 42 mm pitch. Lid Only starts at 1×1; latched lids need one or two screw hinges and one or two latches, from 2×2 at 42 mm or 3×3 at 21 mm. Piano hinges, zero-latch latched lids, top labels and the peg stacking option are refused. Set label location to Front or None explicitly. Both floor modes remain available; headroom and skin datums stay unchanged. Fit, closure, mating and flipped-lid barrel print quality remain unverified pending Andrew's recorded prints. Open only with nothing seated on the lid. These are structural Space settings; an AI bin result must not set them or return the case.
- Ordinary bins may be designed to fit inside a Storage Box Space.
- The AI result is still an ordinary bin, not the Storage Box case itself.
- Generating or printing a bin in a Storage Box Space requires the bin or closed design to fit the interior height, including its foot, handle and raised lettering. Unverifiable height blocks generation. Lid snugness does not add capacity; designs without a Space are unaffected.
- Hard object-height cap: the Storage Box Space's own height.
- Gridfinity Storage Box creation offers 21 or 42 mm pitch and immutable Floor or None. Floor builds the raised socket floor; None leaves a plain cavity for an owner-supplied baseplate. Nominal grid cells and printed cavity sizes are distinct. Optional measured seated lift is the height added by the seated baseplate, not total thickness; zero is measured, missing lift is not recorded. The full seated stack includes measured lift and must fit the usable height. These settings stay in the Space; AI returns only an ordinary bin on its grid.
- Gridfinity Plain Drawers and Storage Boxes with Floor None can record and later edit the measured seated lift. Blank means not recorded and zero is measured; layout heights include the lift.
- The case is configured in its Space: interior width and depth, usable inside height, Latched Lid or Lid Only and lid snugness, stacking on/off, carrying handle on/off, and no label or a front label in Flat or Wavy style. Number of latches offers None or 1 at every width, and 2 only above 96 mm of interior child-bin field width; new cases start with 2 above that width, otherwise 1. User selections and saved counts are kept. Latch tightness is Loose / Default / Tight (0.35 / 0.40 / 0.45 mm snap grip). Wall and Base/Lid thickness share these choices: 0.8 mm Very thin, 1.2 mm Thin, 1.6 mm Default, 2.0 mm Strong, 2.4 mm Very strong and 3.0 mm Heavy duty. New cases default to 1.6 mm for both. These are case settings, not bin fields.

## Storage Drawers

- The Space context is the selected physical drawer's usable width, depth and height (usable height includes the cabinet's Drawer fit).
- Returned bins must fit inside that one drawer.
- The AI result is still an ordinary bin. It must not invent or return cabinet structure (drawer count, frame, rails or cabinet settings).
- Hard object-height cap: the selected drawer's usable height.
- The Space owns the cabinet: width/depth, drawer count and usable heights, drawer fit (Tight, Standard, Loose), cabinet and drawer material, handles, labels and stacking. Changing drawer fit affects the entire cabinet.
- Creation offers one grid for the whole cabinet: Wavefinity 7 mm (default), Gridfinity half 21 mm, or Gridfinity 42 mm. Gridfinity offers Floor (built-in raised pocket grid) or None (flat floor, cavity clearanced for an owner-supplied baseplate). Grid and Floor are immutable after creation.
- Wavefinity starts at 210 × 119 mm with three drawers at 40 mm usable height. Both Gridfinity pitches derive a 210 × 126 mm field and 42 mm usable height (six 7 mm height units); stored heights remain net of Drawer fit.
- Gridfinity placement uses pitch cells, including 1×1 and 2×3 bins. Bins of another grid are refused naming both grids. No side connectors or bin spacers are available in Gridfinity drawers.
- Nominal grid area and printed cavity are separate readouts. None uses the shared provisional per-side baseplate clearance. Optional measured seated lift means height added by the seated baseplate, not its total thickness; a recorded zero is measured. Stacks include that lift and are refused when overheight. Missing lift is shown as not recorded; physical fit remains unconfirmed.
- Save/reload and cabinet print/export retain the selected pitch and floor configuration. AI returns only an ordinary bin; it must preserve the context grid and fit the selected drawer including any measured seated lift.

Third-party stand-ins are external bins recorded in the Space Inventory for layout only. AI Design does not create or change stand-ins; it returns ordinary bins.

## Pegboard

- Supports Standard Pegboard and IKEA SKÅDIS Space types.
- Pegboard mount metadata is Space-controlled.
- Preserve the current mount data exactly unless the generated prompt explicitly says otherwise.
- The returned bin must satisfy the current board/minimum-size rules supplied in the generated prompt.
- No hard object-height cap.
- Choose Standard Pegboard or IKEA SKÅDIS, and specify physical board width/height or hole/slot counts. Cleat counts X and Y may be Auto or explicit.

## Spacers and placement

Spacers brace placed bins; they are Space filler, not AI-designed bins. Choose Rigid or Flexible (default; 2 mm oversized), manual height (at least 6 mm) or Auto height (default: full height of the tallest placed bin, rounded and bounded by the Space height; 15 mm fallback when none is placed). Left, Back and Right walls default on; there is no front-wall spacer. Plan and select candidates, place or refresh them, and choose quantities to print.

Bins can stack when their modes, footprints and wall geometry match. Direct stacking requires the same footprint. A "Lid for stacking" (resting lid with the 2 mm rim) carries a 2 mm rim that a same-footprint stackable bin sits into; hinged lids, resting lids without the rim, lids with the knob and lids with raised lettering take no stack.

---

# 4. Ordinary-bin shell controls

## Size

- Width.
- Depth.
- Height.
- Width/depth are Wavefinity-grid aware.
- The outside AI may resize the bin when that is legal for the active Space.
- Interior feature zones must fit the **returned** bin, not merely the original bin.

## Interior print mode

- **Fused into box** — interior parts become part of the bin.
- **Removable insert** — interior parts print as a separate drop-in insert.

Some shell features require Fused mode because they physically modify the bin wall.

## Wall thickness

Wavefinity exposes current legal wall choices in the generated prompt.

General behavior:

- wall choice changes the physical Wavefinity wall/mating geometry;
- lids/stacking can require stronger walls;
- connector fit follows the bin's actual wall thickness.

## Base thickness

Wavefinity exposes current legal base choices in the generated prompt.

General behavior:

- stacking/lids can require a thicker minimum base;
- Surface Spaces can control base behavior.

---

# 5. Interior parts

The generated prompt contains the exact legal fields, values, ranges, defaults, and canonical JSON for the running build. The descriptions below explain intent.

## Cradle

For tools laid horizontally.

Typical controls:

- stored-item dimensions/profile;
- quantity;
- run direction;
- alternate ends where supported;
- spacing;
- distance from ends;
- placement/fit.

## Photo Nest

Custom holder created from a photograph and traced contour.

**AI rule:** recommend-only for text AI.

An outside text AI must **not fabricate**:

- photo data;
- traced contour;
- source contour.

The user can add Photo Nest in Wavefinity after the AI-designed bin is created.

## Bore

For upright tools/items held in one or more fitted holes.

Current style families:

- **Base - Straight Walls**
- **Base - Wavy Walls**
- **Straight Walls Only**
- **Wavy Walls Only**

Typical controls include:

- held-item profile/measurements;
- insertion depth — `options.depth` for the two Base styles; `options.walls_depth` for the two Walls Only styles (never the other field for the wrong family; a legacy design with no `walls_depth` reaches the normal bin floor, but a new AI answer should choose it deliberately);
- Bore height;
- Bore wall thickness;
- X/Y quantity;
- angle and angle direction — see below;
- footprint sizing relationship;
- height sizing relationship.

Current item-profile choices and any special fixed-profile dimensions are supplied in the generated prompt. Do not invent a profile value.

### Wavy preference

When a Base or Walls Only Bore is otherwise equally suitable straight or wavy, prefer the wavy variant of the *same* structural family: Base - Wavy Walls over Base - Straight Walls, or Wavy Walls Only over Straight Walls Only. Choose the correct family (Base vs. Walls Only) for the request first; never switch families merely to get "wavy".

### Retrieval depth vs. object length

An object's own length, its insertion depth, and the bin's height are three different numbers. Do not set the insertion depth equal to the object's full length just because that is the length supplied. For an upright hand-retrieved object, plan its final top relative to the bin rim, aiming for roughly 30 mm of it to remain grippable above the rim. In a Space with a hard object-height cap (see Space context, above), this preference is always subordinate to that cap: no part of the object may end up above it, even if that means a shorter bin or a shallower insertion depth than 30 mm of grip would otherwise call for. In an uncapped Space (or no Space), the object protruding above the bin rim is normal and expected.

### Bore angle terminology

The generated prompt's `options.angle` is the canonical, persisted value: degrees of lean **away from vertical**, 0 = upright, up to a current maximum around 70. The Wavefinity Designer itself shows a different, human-facing **"Bore angle"** field running 90 (upright) down to 20 (steepest lean), where `displayed_bore_angle = 90 - options.angle`. Always return the canonical `options.angle` value, not the displayed one. When leaning a Bore with no object-specific reason for a direction, prefer `options.angle_towards` "back", or the side opposite the design's one allowed rim Label's `rim_side` if the design has one.

## Post

Center peg for rolls, rings, spools, sockets, and similar objects.

Typical controls:

- height;
- diameter;
- taper;
- spacing;
- quantity/layout.

## Dividers

Interior walls that split the bin into compartments.

Typical controls:

- divider thickness;
- divider height;
- straight/wavy divider walls;
- X/Y layout;
- spacing;
- bottom construction/slope behavior;
- compartment merging/spans;
- per-compartment Scoop behavior;
- Divider labels.

## Slot Rack

Angled slots for bits, cards, small tools, and similar objects.

Typical controls:

- height;
- depth;
- thickness;
- angle;
- wall thickness;
- Straight/Wavy Walls;
- quantity/layout.

## Steps

Tiered shelves/riser.

Typical controls:

- height;
- number of steps;
- quantity/layout.

## Scoop

Curved retrieval ramp to make small contents easier to remove.

Typical control:

- scoop depth.

Wavefinity enforces compatibility with nearby shell features.

## Label

Lettering on the base or rim. (User-facing name; the internal feature
kind remains `text` and the words option key remains `options.text`.)

Current Label Types:

- **On base — Inlaid**
- **On base — Raised**
- **At rim — Inlaid**
- **At rim — Raised**

Typical controls:

- label name;
- letter height;
- inlay depth / raised height;
- quarter-turn rotation;
- rim side.

The generated prompt supplies the exact legal relief values.

Lettering is automatically centered. Internal transport/editor fields that are not user choices must not be invented.

**A design may contain at most one rim Label in total, not one per rim side.** A returned design with more than one rim Label is a semantic-answer defect and is rejected before it can be applied, the same as any other repairable defect.

---

# 6. Shared interior-part fields

Many interior parts use common canonical fields outside their feature-specific option block. The exact machine contract is in the generated prompt.

Common concepts include:

## Zone / footprint

- `[x0, y0, x1, y1]` in millimetres relative to bin center.
- `x1 > x0` and `y1 > y0`.
- Must fit the returned design's legal interior.

## Quantity

- Explicit positive whole-number quantity where supported.
- Some features support Auto through the canonical null/omitted behavior described by the generated prompt.

## Run direction

- X or Y where the feature supports directional runs.

## Alternate ends

- Boolean behavior only on features that support it.

## Item

Held-object description for features such as Bore or Cradle.

The prompt supplies the legal structure, including:

- length;
- diameter/thickness;
- fit clearance;
- profile/shape;
- any profile-specific fixed dimensions.

Never transfer Bore-only profiles to Cradle or vice versa.

---

# 7. Box modifiers

These alter the ordinary bin shell rather than acting like independent interior parts.

## Lid & Stacking

The Wavefinity bin Specification area has Stackable (Not Stackable / Stackable)
and Lid (No lid / Lid / Lid for stacking / Hinged lid). Width and Depth use the
selected pitch on commit and display millimetres and unit count. Gridfinity
Height uses independent 7 mm units; Wavefinity Height stays in millimetres.
The options below describe Wavefinity; Gridfinity also exposes Side Openings with the protected zones below, magnet holes on ordinary 42 mm bins, and the rim and
Gridfinity Lid choices described above (no Hinged lid or Edge Mount).

Choosing Lid, Lid for stacking, or Hinged lid includes a lid and shows the lid options. A hinged lid also has Alignment (Off by default, saved as `box.lid.alignment`: off / thin 1 mm / standard 2 mm / thick 3 mm): L-shaped tabs under the two front corners. A hinged lid with Alignment on needs support for these tabs; that is expected and fine. Lid thickness, an optional Knob (the only handle), and label text are available. Older saved Pull handles open as a Knob. Editing non-empty label text enables its options; clearing it disables the label. A saved off label stays off until its text is edited, and division labels retain their editor.

General rules:

- direct bin-on-bin stacking uses no lid: a straight 3 mm locating skirt under the base, beveled and support-free, drops into the mouth of a same-size bin below. It only locates (nothing snaps), sits inside the typed Height, and needs no extra wall thickness;
- "Lid for stacking" is a lid type with a rim (about 2 mm tall, on its top face) for another bin; there is no separate stackable-lid print choice;
- a hinged lid, a resting lid without the rim, or a lid with the knob or raised lettering takes no stack;
- Wavefinity may require stronger wall/base values (a lid needs the stronger wall; a direct skirt needs only a thicker base);
- raised lid lettering means the lid takes no stack; a Divider can provide one lid label per compartment;
- a handle that does not fit is rejected rather than silently shrunk;
- a flip lid keeps the closed outside size: a full-width piano hinge in the back-top corner, flush with the wavy back face and the lid top, on a 1.75 mm filament pin in a 2.3 mm bore open at one side wall and closed by a 2 mm end stop at the other. Bin-side knuckles grow from the wall on 45 degree underside bevels; the preview and export both include them. It cuts into the back top corner, keeps any stacking recess, and opens to a 110 degree stop. Continuous below-rim arc clearance may increase the closed plug gap beyond the selected fit minimum. It has no snap-fit lock bumps and is rejected when the bin is too narrow or short to hinge.

## Inside Grip

Finger grip built into the bin wall.

Typical controls:

- size;
- location.

General rules:

- requires shell geometry;
- incompatible with Removable insert;
- may conflict with Side Openings, Edge Mount screw access, Scoop, or other wall occupancy.

## Side Openings

Finger-access cutouts through selected bin walls.
Gridfinity percentages span the effective cavity floor to the body rim (shortened
for a lid). A zero lower inset reaches the floor; any positive strip left above
that floor must be at least the selected wall thickness. A supported opening
leaves at least that thickness below the protected stacking rim, or below the
plain top when no open-bin rim is present. At each end the shoulder must cover
both the corner-radius region and the selected wall thickness. Use the active
grid's catalog dimensions; invalid choices are refused, never resized.

Side Openings are available on ordinary flat 21 mm and 42 mm Gridfinity bins.
The requested cut is refused before geometry is built if it enters the 4.75 mm
foot plus its base, the optional open-bin stacking rim, the foot-carrying corner
radii, or leaves a remaining wall strip thinner than the selected wall thickness.
The largest existing opening size that meets those limits is supported; invalid
choices are never clipped or shrunk. Cuts remove flat wall material only, keeping
the outside envelope, rim support, feet and neighbour clearance by construction.
Third-party baseplate and printed fit remain **unverified** until Andrew records
his own fit prints. Edge Mount stays unavailable on both Gridfinity pitches:
it projects beyond the cell; only Andrew may approve a separate inside-envelope
replacement. Wavefinity Side Openings keep their existing behaviour.

Typical controls:

- shape: Curved or Square;
- opening size;
- vertical lower/upper position;
- selected wall(s): Front, Back, Left, Right.

Wavefinity prevents collisions with other wall/rim features.

## Edge Mount

External label and/or screw mounting on one bin edge.

Mounting side:

- Front.
- Back.
- Left.
- Right.

Label type:

- None.
- Separate Part.
- Integrated.

Typical label controls:

- text;
- flip text;
- Full Side vs Text Length;
- text depth/style;
- projection;
- thickness;
- standoff-rib behavior.

Typical screw-mount controls:

- enabled/disabled;
- screw count;
- pattern/orientation;
- screw diameter;
- access diameter;
- distance from top;
- automatic/custom spacing.

Wavefinity checks Edge Mount against lids, direct stacking, rim Label, Side Openings, Inside Grip, and other incompatible wall use.

---

# 8. Label systems

Wavefinity has multiple distinct label systems. Do not merge them into one generic label concept.

## Label feature

- Ordinary bin base or rim.
- Inlaid or Raised.

## Divider labels

- No label.
- On base.
- Rim level.
- Per-compartment text.

## Lid label

- On/off.
- Text.
- Horizontal/Vertical.
- Inlaid/Raised.
- Relief depth/height.

## Edge Mount label

- None.
- Separate Part.
- Integrated.
- Own text/size/projection/support settings.

## Storage Box label

- Belongs to the Storage Box structural case, not an ordinary AI-designed bin.

---

# 9. Straight and wavy choices

Several interior systems independently support straight or wavy walls.

Current important families include:

## Bore

- Base - Straight Walls.
- Base - Wavy Walls.
- Straight Walls Only.
- Wavy Walls Only.

## Dividers

- Straight Walls.
- Wavy Walls.

## Slot Rack

- Straight Walls.
- Wavy Walls.

The exact wave geometry is owned by Wavefinity and must not be recreated by the outside AI.

---

# 10. Connectors

Connectors are generated by Wavefinity from bin geometry.

## Side Connector

Joins two neighboring bins across a shared seam.

Supports:

- same-height bins;
- different-height bins.

Current request/build data can include connector settings such as:

- tolerance;
- length;
- arm thickness;
- A/B heights where needed.

Connector wall fit follows actual bin wall thickness.

The AI generally designs the bin; Wavefinity determines which connector outputs are legal for the final arrangement.

---

# 11. Important compatibility rules

The running Wavefinity validator is authoritative. Important classes of conflict include:

- Removable insert vs shell features that must be built into the bin wall.
- Side Openings vs Inside Grip.
- Side Openings vs rim Label.
- Side Openings vs Edge Mount.
- Edge Mount vs rim Label on the same wall.
- Separate Edge Mount label vs lid.
- Separate Edge Mount label vs direct stacking.
- Edge Mount screw access vs Inside Grip.
- Scoop vs conflicting front Inside Grip geometry.
- Lid/stacking vs insufficient wall/base strength.
- Raised lid label vs stacking contact.
- Lid vs Side connector rim geometry.
- Pegboard mounting fields vs non-Space ownership.
- Surface base fields vs non-Space ownership.
- Photo Nest contour data vs text-AI synthesis.

When unsure, prefer a simpler legal design or ask the user a question.

---

# 12. Final-answer behavior

The generated Wavefinity prompt contains the exact response envelope and IDs.

General rules:

- final answer is one JSON object;
- no prose before or after the final object;
- return a **complete** ordinary-bin design, not a patch;
- echo the exact request ID and context fingerprint;
- harmless assumptions may be listed;
- critical dimensions may not be guessed;
- no fabricated Photo Nest contour;
- preserve all Space-controlled fields;
- `design.part_name` is a short, descriptive, non-blank name (1–80 characters) for what the bin holds — for example "Lipstick" or "Hex Drivers", never a generic "Bin" or dimensions-only text; existing Inventory names, when supplied, are advisory only, so do not invent a numbering suffix — Wavefinity enforces final uniqueness itself.

Wavefinity will run canonical validation, real geometry validation, and active-Space checks before adopting the design.

---

# 13. Maintenance checklist for Wavefinity fixes

Update this file whenever a fix changes anything an outside AI could reasonably need to choose or describe, including:

- new/removed/renamed interior part;
- new/removed/renamed box modifier;
- new option or enum choice;
- changed legal range/default/step that affects AI design;
- new item profile/shape;
- changed straight/wavy behavior;
- changed label type or label rule;
- changed Lid/Stacking configuration;
- changed Side Opening / Inside Grip / Edge Mount behavior;
- changed Space restriction or Space-controlled field;
- changed compatibility/conflict rule;
- changed canonical design field that the outside AI must return;
- changed AI recommend-only restriction.

If a change is implementation-only and does not affect what the outside AI may legally choose or return, this file does not need a cosmetic update.


Ordinary 42 mm Gridfinity bins may set `box.magnet_holes` to `"6x2"` for magnet pockets or `"none"` (default). Never use `"6x2"` on Wavefinity, 21 mm Gridfinity, or container floors. The 6.5 mm diameter and 2.4 mm depth are unconfirmed starting values, not verified fit.

Ordinary Gridfinity bins at either pitch have `box.hollow_base` on by default
(the UI's Base: Hollow); set it to false for solid feet and base when requested. It has no effect on
Wavefinity bins or container floors. Physical print performance is unverified.
