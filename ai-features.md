# Wavefinity AI Feature Reference

> **Audience:** External AI systems helping a person design one ordinary Wavefinity bin.
>
> **Purpose:** Public, compact background reference for Wavefinity AI Design. The AI Design prompt may link here instead of repeating every explanatory detail.
>
> **Authority rule:** The **request-specific prompt embedded by the running Wavefinity app wins** over this file whenever they differ. The prompt contains the exact current design, Space constraints, request/fingerprint, legal machine-readable values, and response contract needed for that request.
>
> **Maintenance rule:** Any Wavefinity fix that adds, removes, renames, or materially changes a user-facing feature, option, legal choice, compatibility rule, or design field that an outside AI could use must update this file in the same fix.
>
> For the broader human product catalog, see `features.md`.

---

# 1. What the external AI is designing

AI Design designs **one ordinary Wavefinity Bin**.

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

Wavefinity may be used without a typed Space or inside one of these typed Spaces.

## Hard object-height cap

Drawer and Storage Box are a hard vertical ceiling: the full physical envelope of a Bore-held object, including its width/profile and tilt, must remain below the Space's own height. Surface and Pegboard have no such cap, and neither does an ordinary Design with no active Space. The generated prompt always states which applies and, when capped, the exact height. This is a legality rule enforced by Wavefinity's own candidate check, not merely a style preference. Manual Design shows an advisory warning rather than blocking generation.

Pocket, Post, Slot and Steps may include an optional `reference_object` with positive finite `width`, `depth` and `height` in millimetres. It is a 3D Preview/planning envelope only; it does not alter the holder or print. Include it only when the person supplies or confirms all three measurements. Bore and Cradle use their existing measured `item` instead. Photo Nest is recommend-only for AI Design.

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

## Storage Box

- Ordinary bins may be designed to fit inside a Storage Box Space.
- The AI result is still an ordinary bin, not the Storage Box case itself.
- Hard object-height cap: the Storage Box Space's own height.

## Storage Drawers

- The Space context is the selected physical drawer's usable width, depth and height.
- Returned bins must fit inside that one drawer.
- The AI result is still an ordinary bin. It must not invent or return cabinet structure (drawer count, frame, rails or cabinet settings).
- Hard object-height cap: the selected drawer's usable height.

## Pegboard

- Supports Standard Pegboard and IKEA SKÅDIS Space types.
- Pegboard mount metadata is Space-controlled.
- Preserve the current mount data exactly unless the generated prompt explicitly says otherwise.
- The returned bin must satisfy the current board/minimum-size rules supplied in the generated prompt.
- No hard object-height cap.

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

The generated prompt's `options.angle` is the canonical, persisted value: degrees of lean **away from vertical**, 0 = upright, up to a current maximum around 70. The Wavefinity Designer itself shows a different, human-facing **"Bore angle"** field running 90 (upright) down to 20 (steepest lean), where `displayed_bore_angle = 90 - options.angle`. Always return the canonical `options.angle` value, not the displayed one. When leaning a Bore with no object-specific reason for a direction, prefer `options.angle_towards` "back", or the side opposite the design's one allowed rim Text's `rim_side` if the design has one.

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
- lip;
- number of steps;
- quantity/layout.

## Curved Scoop

Curved retrieval ramp to make small contents easier to remove.

Typical control:

- scoop depth.

Wavefinity enforces compatibility with nearby shell features.

## Text

Centered lettering on the base or rim.

Current Text Types:

- **On base — Inlaid**
- **On base — Raised**
- **At rim — Inlaid**
- **At rim — Raised**

Typical controls:

- text;
- letter height;
- inlay depth / raised height;
- quarter-turn rotation;
- rim side.

The generated prompt supplies the exact legal relief values.

Text is automatically centered. Internal transport/editor fields that are not user choices must not be invented.

**A design may contain at most one rim Text feature in total, not one per rim side.** A returned design with more than one rim Text is a semantic-answer defect and is rejected before it can be applied, the same as any other repairable defect.

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

Current user-facing configurations:

- **Stackable bin on bin**
- **Stackable bin on lid**
- **Lid with handle — non-stackable**

When a lid is present, current prompt metadata supplies:

- legal lid thickness choices;
- legal lid-fit choices;
- handle types/sizes/positions;
- label choices and relief values;
- stacking compatibility.

General rules:

- direct bin-on-bin stacking uses no lid;
- stackable lid keeps a seat/recess for another bin;
- handled lid is non-stackable;
- Wavefinity may require stronger wall/base values;
- raised lid text cannot interfere with stacking contact;
- a handle that does not fit is rejected rather than silently shrunk.

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

Wavefinity checks Edge Mount against lids, direct stacking, rim Text, Side Openings, Inside Grip, and other incompatible wall use.

---

# 8. Label systems

Wavefinity has multiple distinct label systems. Do not merge them into one generic label concept.

## Text feature

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

## 3-Way Corner Connector

- Joins three compatible bins around a grid corner.
- Equal-height/equal-wall requirements apply.

## 4-Way Corner Connector

- Joins four compatible bins around a grid corner.
- Equal-height/equal-wall requirements apply.

The AI generally designs the bin; Wavefinity determines which connector outputs are legal for the final arrangement.

---

# 11. Important compatibility rules

The running Wavefinity validator is authoritative. Important classes of conflict include:

- Removable insert vs shell features that must be built into the bin wall.
- Side Openings vs Inside Grip.
- Side Openings vs rim Text.
- Side Openings vs Edge Mount.
- Edge Mount vs rim Text on the same wall.
- Separate Edge Mount label vs lid.
- Separate Edge Mount label vs direct stacking.
- Edge Mount screw access vs Inside Grip.
- Scoop vs conflicting front Inside Grip geometry.
- Lid/stacking vs insufficient wall/base strength.
- Raised lid label vs stacking contact.
- Lid vs Side connector rim geometry.
- Corner connectors vs unequal-height or unequal-wall bins.
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
