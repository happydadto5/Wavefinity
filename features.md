# Wavefinity Feature Catalog

> **Purpose:** Keep one readable inventory of Wavefinity's important user-facing capabilities.
>
> This file describes **what the product can do**. It is not the authoritative source for geometry constants, numeric validation limits, schemas, or implementation details. Those remain in the code/catalog/rule owners.
>
> **Maintenance rule:** Any fix that adds, removes, renames, or materially changes a user-facing feature or option must update this file before the work is considered complete. If the change affects something an outside AI could legally choose, configure, return, or must avoid, the same fix must also update `ai-features.md`.
>
> Last reviewed: **2026-09-26**

---

## Status

- **Current** — accepted on `main`.
- **In review** — implemented on a fix branch but not yet accepted into `main`.
- **Legacy/internal** — still understood by the code where necessary, but not offered as a normal current UI feature.

### In-review feature

- **AI Design — Current (Fix 073):** accepted and integrated into `main`.

---

# 1. Product model

Wavefinity has two top-level work areas:

- **Design** — design one ordinary Wavefinity Bin.
- **Space** — arrange and manage bins inside a real physical area.

A **Space** owns the real-world context and inventory. The Designer owns one ordinary bin at a time.

Structural Space outputs are not ordinary Designer bins:

- **Storage Box** creates its own Storage Box case.
- **Surface** creates its own Base Trim.
- These structural outputs are saved/printed from the Space, not stored as ordinary Inventory bins.

Wavefinity's core physical system is based on modular bins with **interlocking wavy exterior walls** and optional connectors, interior holders, labels, openings, mounts, lids, stacking, and Space-specific behavior.

---

# 2. Space types

Wavefinity currently has five typed Space types.

| Space | Main purpose | Key configuration | Space-owned output / special behavior |
| --- | --- | --- | --- |
| **Drawer** | Organize bins inside a drawer or enclosed area | Usable inside width, depth, height | 3D arrangement, placement validation, stacking, unplaced-bin rail |
| **Surface** | Organize bins on an open shelf/counter/other surface | Maximum outside width/length, trim size | **Base Trim** plus Surface-specific bin base controls |
| **Storage Box** | Put Wavefinity bins inside a printable carrying/storage case | Outside width/length, usable inside height, case settings | **Storage Box case** with lid/stacking/handle/label/material options |
| **Storage Drawers** | A printable multi-drawer mini cabinet for Wavefinity bins | Whole-unit width/depth, drawer count, per-drawer usable height, cabinet/drawer material, fit, handles, labels, stacking | **Cabinet** structural files (frame, drawers, fronts, rails) saved/printed from the cabinet panel |
| **Pegboard** | Hang Wavefinity bins on a pegboard | Board standard, physical size or hole/slot count | Pegboard receivers/cleats on bins and board-grid-aware placement |

Wavefinity can also be used **without a typed Space**, in which case the user can design ordinary bins in a regular folder without Space placement rules.

---

## 2.1 Drawer Space

### Setup

- Space name.
- Usable inside width.
- Usable inside depth.
- Usable height.
- Wavefinity unit/grid capacity readout.

### Layout

- Ordinary bins can be dragged into the drawer.
- Every ordinary bin is placed at most once.
- Unplaced bins remain in the **Unplaced bins** rail.
- Dragging a placed bin out of the Space unplaces it.
- Bins can be stacked when their mode, footprint, and wall mating geometry are compatible.
  - Same-footprint stacking works for every stacking mode (lid, direct bin-on-bin, Storage Box).
  - A **Stackable bin on lid** can also carry one or more smaller bins: each must be compatible, sit on the 8 mm grid, fit fully inside that lid, and not overlap another bin on the same lid. Covering only part of the lid is fine, and no advance arrangement planning, custom lid, or reprint is needed — for example, a 10×10 lid-stack bin printed today can later take four 5×5 lid-stack bins, one per quadrant.
  - A bin stacked on a bin can itself carry bins, and moving or taking out a bin moves or removes only it and what stands on it, never its neighbours on the same lid.
  - Direct bin-on-bin stacking still needs the same footprint.
- Placement checks include:
  - overlap;
  - outside-the-Space placement;
  - excessive height;
  - invalid stacks;
  - height-order warnings where applicable.

### Space view

- Perspective 3D view.
- Camera remains oriented as a view into the drawer rather than a free orbit.
- Camera controls include view presets, angle, limited turn, pan, zoom, and Fit.
- Bin color communicates relative height.
- Selected Space bins and Inventory rows remain linked.

---

## 2.2 Surface Space

### Setup

- Surface name.
- **Maximum width** and **Maximum length** (mm): the largest rectangle the whole organizer, including its Base Trim, may occupy.
  - The inputs keep exactly what was entered; they are never replaced by the smaller rounded result. Changing trim size always re-resolves from the same maximum.
  - The largest whole-Wavefinity-unit field that fits inside that rectangle is used; the readout shows the resolved field and the actual finished outside size.
  - The maximum is saved with the Space. A Surface saved before this existed is seeded from its current finished size, so it never grows.
- Trim size/preset.
- Computed usable Wavefinity field.
- Finished outside size and remaining/border space readouts.

### Changing a Surface's size or trim

- The proposed Surface is checked against every placed bin before anything is saved. If a bin (including a projecting Edge Mount label) would no longer fit, the change is refused with the affected bins named. Nothing is moved, unplaced, deleted, or resized.
- Changing the trim edge height while some **Printed** bins still follow the Surface edge (Auto base) asks first: **Printed bins will keep their current base height** — Continue or Cancel. Continue freezes those printed bins at their existing base height; bins not yet printed follow the new edge.

### Base Trim

A Surface owns a printable **Base Trim**.

- Saved from the Space (**Save Base Trim**).
- Printed with the Surface's bins from the Space (**Print Surface + Bins**).
- Not an ordinary Inventory row.
- Can be split/joined as needed for the selected printer-bed size.
- Uses Wavefinity mating geometry to hold the Surface layout.
- Friction-only: it makes no fastening guarantee.
- A quiet line near the buttons shows current-printer readiness, e.g. **Base Trim · 3 pieces for current printer · Needs save**, or the fit reason if it cannot be planned for the printer.
- Saved files are tracked in the Space's metadata. The status is **Current**, **Needs save** (missing, or the Surface, trim, name or printer no longer matches), or **Saved file changed outside Wavefinity**. Saving replaces or removes only files Wavefinity can prove it made; an unowned or changed same-name file is never overwritten or deleted.
- Hosted Wavefinity writes the pieces to the chosen folder first and records the manifest only after every write succeeded.

### Print Surface + Bins

One action sends to the slicer, once: the current-printer Base Trim, every placed **Not Printed** ordinary bin (including bins in valid stacks), and the required connectors. Unplaced, already-Printed and spacer/manual rows are left out. Hard placement, boundary, overlap and stack problems stop the print before the slicer opens; reach, unverified-contents and interior-group advisories never do. Rows become Printed only after the slicer opens.

### Surface-bin options

Bins designed in a Surface Space can use Surface-specific base controls:

- **Base height**
  - Auto — match Surface edge.
  - Custom.
- **Lightweight base**
  - Removes hidden underside material with support-free cavities.
- **Object height**
  - Planning-only physical object height.
  - Used for Space planning; does not change the bin geometry by itself.
- Helper text: Auto matches the Base Trim edge. If you are not using the Base Trim, choose Custom.

### Object planning and stacking

- The Object-height prompt offers **Save Object height**, **Continue without one**, or **Cancel** (same as Escape: nothing is set or saved).
- **Object planning** in the Surface layout controls holds the per-Space "Ask for missing Object height" setting (still available after "Don't ask again for this Space") and a quiet **N placed bins missing Object height** count.
- Stacking respects installed objects: a known object that reaches above the next stack seating plane (direct or lid stacking) blocks the stack. An unknown Object height still allows the stack with the advisory **Contents clearance not verified — Object height is not set for <bin>.**
- A group of placed bins with no shared edge against the Base Trim gets an advisory that it may slide within the open Surface. This is never a blocker, and edge contact is not a claim that anything is anchored or secured.
- Tall planned objects widen the camera framing, but the Surface stays visually open: its rim is drawn at the real Base Trim edge height.

---

## 2.3 Storage Box Space

A Storage Box is a printable outer case designed to contain ordinary Wavefinity bins.

### Space dimensions

- Outside width.
- Outside length.
- Usable inside height.

### Case lid

- **Latched Lid**.
- **Lid Only**.
- Lid snugness / clearance choices.
- Automatic or allowed latch count behavior based on the case.

### Case options

- **Case stacking**
  - Not stackable.
  - Stackable.
- **Carrying handle**
  - No handle.
  - Add handle.

### Case label

- No label or front label.
- Front-label style:
  - Flat.
  - Wavy.

### Material

- Storage Box-specific wall thickness choices.
- Storage Box-specific base thickness choices.
- Lid geometry follows the effective case material rules.

### Storage Box interiors

- Storage Box itself can contain **Dividers**.
- **Make Inside Bin** confirms before starting one ordinary bin sized to fill the Storage Box interior.
- Designer gives an advisory physical-height warning for a bin, or for two identical stackable bins, when they exceed the case's closed-height allowance.
- The existing Space arrangement determines which bins are inside the case and validates their physical stack height.

### Ownership

- The Storage Box case is a Space-owned structural output.
- **Save Storage Box** saves the case from the Space header.
- **Print Storage Box + Bins** opens the case, placed Not Printed bins, and required Space connectors together in the slicer after file and printer-fit checks. Unplaced or already-Printed bins remain on their existing Inventory paths.
- It is not an ordinary Designer Inventory row.

---

## 2.3a Storage Drawers Space

- One shared Inventory and parking lot for the whole cabinet; every drawer is a physical drawer with its own stable identity and usable height.
- Create/Edit options are grouped like Storage Box: Name, Size (whole Wavefinity units), Drawers, Cabinet, Labels, Material (cabinet wall/base/top and drawer wall/base), and a live Summary that checks fit against the printer volume.
- A right-side navigator lists the drawers proportionally, marks the active one, and offers Add Drawer, per-drawer Delete (only an empty drawer, and never the last), Save Cabinet and Print Cabinet. Switching drawers is not an undo step.
- Inventory rows show where they are placed as `Placed · Drawer N`; choosing a row placed in another drawer switches to that drawer and keeps the row selected.
- New bins are sized to the active drawer's usable X/Y/height.
- Save/Print Cabinet writes every cabinet component together; Wavefinity only replaces cabinet files it wrote (verified by content), never unrelated files.
- Setup shows a labelled Summary (finished outside size, effective base/top, fit verdict naming any part that does not fit) and blocks Create when the cabinet cannot print on the current printer. Printer Settings opens from setup and from the cabinet panel. Drawer fit (Tight/Standard/Loose) changes only drawer-to-cabinet clearance.
- Save Cabinet exports each part in the orientation chosen by the printer fit check, and a one-page assembly & print guide is linked from setup and the cabinet panel. A saved cabinet is a transaction: a failed or interrupted save is rolled back, and Saved status checks file contents.
- Damaged cabinet settings keep Inventory and designs available and offer **Reset cabinet settings**. An existing folder cannot be converted into a Storage Drawers Space.
- Add/Delete/Edit go through one serialized cabinet change, so an older queued layout save can never bring back a removed drawer.
- One global printer build volume (X/Y/Z) sits beside the Wavefinity Folder on Welcome and is also used by Base Trim (which keeps its 10 mm printable-edge margin).
- Recents show `N drawers · X × Y units each`, never the compatibility height total.

## 2.4 Pegboard Space

### Board standards

- **Standard Pegboard**.
- **IKEA SKÅDIS**.

### Board sizing

Define the board by either:

- **Physical size**
  - width;
  - height.
- **Hole / slot count**
  - positions across;
  - positions high.

Wavefinity reports usable board dimensions and any residual border space.

### Bin mounting

Pegboard bins use a Space-controlled mounting system.

- **Cleat Count X**
  - Auto or explicit count.
- **Cleat Count Y**
  - Auto or explicit count.
- Receiver positions align to the selected board standard.
- Auto mode can choose fewer receivers when needed to keep a legal fit.
- Rear support ribs are added where needed to prevent unsupported spans.
- Standard Pegboard and SKÅDIS use different board-side adapter geometry while sharing the bin-side receiver concept.

Pegboard mounting metadata is controlled by the Space and should not be casually overwritten by unrelated bin edits.

---

# 3. Space lifecycle and Inventory

## 3.1 Space actions

- Open Space.
- Edit Space.
- Show Folder.
- New Space.
- Save Storage Box / Print Storage Box + Bins when in a Storage Box Space.
- Save Base Trim / Print Surface + Bins when in a Surface Space.

## 3.2 Inventory

Every ordinary bin in a typed Space is represented by one Inventory row.

Inventory distinguishes:

### Placement state

- Placed in Space.
- Unplaced.

### Design/file state

- In Design.
- Saved.
- Printed.

### Row actions

Depending on state, Inventory supports actions such as:

- Edit.
- Duplicate.
- Save/generate.
- Print.
- Mark Printed.
- Mark Not Printed.
- Delete.

### Bulk actions

Inventory supports multi-select and bulk operations such as:

- Select all.
- Select all not printed.
- Clear selection.
- Save needed files.
- Print not-printed bins.
- Delete selected bins.

Required Space connectors are included automatically where the Space workflow calls for them.

## 3.3 Space memory

A typed Space remembers safe defaults for future bins, including appropriate values such as:

- bin size;
- wall/base selection;
- Fused/Removable mode;
- per-part settings;
- per-option settings.

It does **not** use those defaults to copy identity-specific content such as:

- bin name;
- label text;
- photos;
- traced contours;
- exact part positions.

Each Inventory bin still keeps its own exact editable design.

## 3.4 Autosave and resume

- Editable Space designs autosave.
- Reopening a Space can restore the last design state.
- Switching bins or leaving Design preserves the latest valid visible edit.
- If a bin already has generated files and is edited, Wavefinity can ask whether those files should be regenerated, with an option to remember the behavior.
- Generated-file status is kept separate from editable design persistence.

---

# 4. Ordinary Bin — core shell

## 4.1 Bin identity and lifecycle

- Bin Name.
- New Bin.
- Duplicate Bin.
- Edit an existing Inventory bin.
- Save/Open standalone design files when outside a typed Space.

## 4.2 Dimensions

- Width.
- Depth.
- Height.
- Wavefinity unit/grid-aware sizing.
- Inside-size readout based on the actual wavy-wall cavity.

## 4.3 Interior print mode

Current browser modes:

- **Fused into box**
  - Interior parts become part of the bin body.
- **Removable insert**
  - Interior parts print as a separate drop-in insert.

Some shell options that physically require the bin wall, such as Inside Grip, are not legal in Removable insert mode.

## 4.4 Base thickness

- Standard/default base behavior.
- Current base-thickness presets.
- Compatibility rules can raise the minimum base thickness for features such as stacking.
- Legacy saved non-preset values can still be preserved where supported.

## 4.5 Wall thickness

- Standard/default wall behavior.
- Current wall-thickness presets from very thin/prototype through heavier wall choices.
- Stacking/lids can require stronger walls.
- Very thin walls receive a printability warning.
- Connector fit follows the active bin's wall thickness; there is no separate connector-wall setting.

## 4.6 Wavefinity wall geometry

The ordinary bin's exterior wall is the Wavefinity mating system.

- Wavy walls allow neighboring bins to interlock.
- Wall thickness changes the mating geometry.
- Wave amplitude/mating rules are geometry-owned constants, not document-owned values.
- Different bins in one Space may use different walls, but connectors cannot bridge incompatible wall thicknesses.

---

# 5. Parts & Options palette

User-facing capabilities are divided into:

1. **Interior parts** — holders/features placed inside the bin.
2. **Box modifiers** — options that modify the bin shell.

Current palette-visible families are listed below.

---

# 6. Interior parts

Pocket, Post, Slot, Steps and Photo Nest can carry an optional **Reference object** with measured Width (X), Depth (Y) and Height (Z). It appears as a translucent, non-selectable object in 3D Preview and follows the holder when moved. It does not resize the holder or change printed geometry. Photo Nest offers it after a contour and tool thickness are accepted. Bore and Cradle instead show their existing measured items in 3D Preview, including their physical profiles and placement.

In a Drawer or Storage Box, a Bore-held object's full physical envelope crossing the Space ceiling produces an amber warning in manual Design. The warning does not block generation. Surface, Pegboard and Design without a typed Space have no ceiling warning.

## 6.1 Cradle

**Purpose:** Hold a tool horizontally in a half-round/contoured support.

Key options include:

- stored-item size/profile inputs;
- quantity;
- layout direction/orientation;
- alternating arrangement;
- spacing;
- percent from ends;
- automatic placement/fit behavior.

Cradle is intended for tools laid down rather than upright.

---

## 6.2 Photo Nest

**Purpose:** Create a custom fitted holder from a photograph.

### Photo workflow

- Load JPG/JPEG/PNG/WEBP.
- Detect/rectify the reference sheet.
- Manual paper-corner fallback when automatic detection is not sufficient.
- Trace the object outline.
- 2D outline editor:
  - select/edit;
  - add point;
  - delete point;
  - reset outline;
  - finish editing.
- Restore scan defaults.

### Holder controls

- Tool thickness.
- Fit clearance.
- Outline smoothing / soften outline.
- Holder style, including:
  - Raised Wall;
  - Recessed Cavity.
- Cavity depth:
  - automatic;
  - manual where applicable.
- Automatic footprint sizing.
- Finger/lift access:
  - automatic or selected behavior;
  - finger locations;
  - finger width where applicable.
- Push access:
  - position;
  - area;
  - depth.

### Repeats

- Multiple copies in a straight row.
- 90° orientation choices.
- Optional end-for-end alternation.
- Safe repeat-spacing choices.
- Duplicate can create an independent Photo Nest that can be moved, rotated, or have its photo replaced.
- Multiple recessed Photo Nests can share a common deck while retaining individual cavity depths.

### AI limitation

Photo Nest is a **media-derived feature**. AI Design may recommend it, but text AI is not allowed to fabricate a photo contour.

---

## 6.3 Bore

**Purpose:** Hold upright tools/items in one or more fitted holes.

### Four Bore styles

- **Base - Straight Walls**
- **Base - Wavy Walls**
- **Straight Walls Only**
- **Wavy Walls Only**

### Main Bore options

- held-item/profile dimensions;
- height;
- hole depth (Base styles) or Depth (Walls Only styles — see below);
- wall thickness;
- X quantity;
- Y quantity;
- **Bore angle** (labeled this way in the Designer — 90° upright down to 20°, the steepest lean);
- angle direction (**Angle towards**);
- footprint sizing behavior;
- height sizing behavior.

The Type / Hole editor groups no longer label the middle sizing group "Base",
since a Walls Only Bore's middle controls are not a base block.

### Walls Only Depth (Fix 078)

Both Walls Only styles show a **Depth** field in the Hole group: how far the
held object can insert downward from the Bore mouth before it hits its stop.
An explicit Depth shorter than the Bore's Height creates a raised local stop
so the object's grippable top stays higher; a blank Depth (including every
older Walls Only design saved before this Fix) keeps the original
through-to-the-floor behavior. Base styles keep their existing hole-depth
field and behavior unchanged.

### Sizing relationships

Depending on the selected style:

- manual sizing;
- size the Bore/base to the bin;
- size the bin to the Bore;
- automatic height relationships where applicable.

Walls-only styles omit base-only controls.

### Wall behavior

- Straight-wall or wavy-wall Bore geometry.
- Wavy Bore walls can blend into bin walls they reach.
- A **Fused into box** Base - Straight or Base - Wavy Bore that touches or is
  auto-sized to the bin now follows the bin's actual interior wall contour on
  every touched side, with no printable sliver gap between the Base and the
  shell — Base - Straight was previously excluded from this wall-join
  behavior. Removable inserts are unaffected and never fuse to the shell.
- Gap supports use thin straight/wavy webs where required.
- Upright profiles include current supported shape/orientation behavior such as square/diamond cases where applicable.

### Bore angle entry

Typing directly into **Bore angle** (for example replacing 20 with 90) works
normally and is never interrupted mid-keystroke; the dependent **Angle
towards** control only updates once a typed value is committed (Enter, Tab,
or clicking away). A first lean with no direction chosen yet defaults to
**Back**, or the side opposite the bin's one rim Text if it has one; picking
a direction by hand always wins after that. If a committed angle or
direction change would require a bigger bin, Wavefinity asks
**"Angled option will require a bigger bin. OK to size bin?"** before
resizing anything; Cancel leaves the design exactly as it was.

---

## 6.4 Post

**Purpose:** Center peg for rolls, rings, spools, sockets, and similar objects.

Options include:

- height;
- diameter;
- taper;
- spacing;
- X quantity;
- Y quantity;
- layout direction/orientation.

---

## 6.5 Dividers

**Purpose:** Split the bin into compartments.

### Divider geometry

- divider thickness;
- divider height;
- straight or wavy divider walls;
- X/Y divider quantity/layout;
- spacing;
- 2D editing of divider arrangement;
- compartment merging/removal through the divider editor where applicable.

### Divider bottoms

Divider bottoms support configurable bottom construction, including sloped/curved/minimal-style behaviors where applicable.

Controls include geometry such as:

- bottom angle/depth;
- support/crossbar behavior;
- reverse/alternate behavior where supported.

### Divider labels

See the dedicated **Labels** section below.

### Compartment Scoop

Divider compartments can use scoop/ramp behavior to improve access to contents.

---

## 6.6 Slot Rack

**Purpose:** Hold cards, bits, tools, or similar items in angled slots.

Options include:

- height;
- depth;
- slot/material thickness;
- angle;
- wall thickness;
- **Straight Walls** or **Wavy Walls**;
- quantity;
- sizing;
- layout direction/orientation.

---

## 6.7 Steps

**Purpose:** Create tiered shelves/riser levels.

Options include:

- total height;
- lip;
- step count;
- quantity/layout;
- sizing;
- layout direction/orientation.

---

## 6.8 Curved Scoop

**Purpose:** Curved retrieval ramp that makes small items easier to remove.

Options include:

- scoop depth.

Compatibility logic protects nearby shell features such as front Inside Grips.

---

## 6.9 Text

**Purpose:** Add centered lettering to the bin base or rim.

A new Text always starts blank: no placeholder word is ever pre-filled, and
opening the editor with nothing typed yet creates no Inventory row and shows
no error — it becomes a real part of the design only once real lettering is
entered. A brand-new Text also always starts **On base — Inlaid** at **0°**,
regardless of what style or rotation the last Text in this Space used.

### Text editor fields

- **Words** — the lettering itself;
- **Style** — one of the four choices below;
- **Letter height** (mm, whole numbers);
- **Inlay depth** / **Raised height** (label follows Style);
- **Rotate** — a dropdown of **0°, 90°, 180°, 270°** (base Text only; 0° is
  straight across/unrotated); rim Text has no Rotate control since its
  orientation always follows its rim side.

### Style

- **On base — Inlaid**
- **On base — Raised**
- **At rim — Inlaid**
- **At rim — Raised**

### Text rules

- Text is centered automatically.
- One On-base Text can be used per bin.
- A bin may contain **at most one rim Text total** (Fix 078), not one per rim side. Once a rim Text exists, every other Text's At-rim choices are unavailable; the existing rim Text can still change its own side. A legacy design saved with more than one rim Text remains loadable so it can be corrected, but Preview/Generate reports it invalid until only one remains. Text no longer offers its own Duplicate action (Fix 082); Photo Nest's separate Duplicate is unaffected.
- Current relief choices are 0.2, 0.4, 0.6, and 0.8 mm.
- Inlaid text is represented in the preview without changing the visible exterior envelope incorrectly.
- **Letter height auto-fits down to 5 mm without asking.** Below 5 mm is a recommendation, not a hard limit (Fix 082): if the text only fits smaller than that, a one-time-per-Space dialog reads exactly "Text below 5mm isn't recommended" with an OK to proceed; once acknowledged, that Space does not ask again, and the smaller size stays valid through Preview, Save/Reopen and Generate/Export. Outside a typed Space, OK permits only that one action.

---

## 6.10 Pocket — Legacy/internal

A Pocket feature remains understood internally for compatibility but is **not currently palette-visible** as a normal user-facing feature.

Do not treat it as a current advertised feature unless it is deliberately restored to the palette.

---

# 7. Box modifiers

These appear in the same Parts & Options workflow but modify the bin shell rather than behaving like ordinary interior parts.

---

## 7.1 Lid & Stacking

One Lid & Stacking option can be active on a bin.

### Stacking Method

- **Stackable bin on bin**
  - Direct bin-on-bin stacking.
  - No lid.
- **Stackable bin on lid**
  - Bin closes with a lid and keeps a top seat/recess for another bin with compatible stacking geometry: one of the same footprint, or one or more smaller lid-stack bins that fit fully inside the lid (partial coverage is allowed).
- **Lid with handle — non-stackable**
  - Removable handled lid.
  - Not stackable.

Removing the option returns the bin to no lid/no stacking.

### Lid thickness

- Thin.
- Medium.
- Thick.

The UI resolves these to real geometry for the current bin.

### Lid fit

- Tight.
- Standard.
- Loose.

Fit changes the lid plug clearance without changing the accepted direct-stack fit system.

### Handle

Handled lids support:

- Knob.
- Pull.

Handle size:

- Small.
- Medium.
- Large.

Handle position:

- Left.
- Right.
- Front.
- Back.
- Middle.

If a requested handle cannot physically fit, Wavefinity rejects it rather than silently shrinking it.

### Lid label

Lid labels support:

- Off / On.
- Text.
- Horizontal / Vertical.
- Inlaid / Raised.
- Relief depth/height presets.

A Divider can supply one lid label per compartment when that layout is being used.

### Compatibility

- Side connectors are unavailable while a lid is fitted.
- Raised lid labels are restricted where stacking would make them incompatible.
- Lid/stack geometry can require stronger walls and/or thicker base geometry.
- Closed-height calculations include raised lettering and handles.

---

## 7.2 Inside Grip

**Purpose:** Finger grip inside the bin wall to make the bin easier to lift.

Options include:

- grip size;
- grip location.

Rules include:

- built into the bin wall;
- unavailable in Removable insert mode;
- must not collide with Side Openings, screw access, scoop geometry, or other conflicting shell features;
- lid/stacking geometry can alter the available upper-wall area.

---

## 7.3 Side Openings

**Purpose:** Finger-access openings through selected bin walls.

### Shape

- Curved.
- Square.

### Size

- Current opening-size choices from the authoritative catalog.

### Opening Height

Two-handle vertical-range control, labeled **Top of bin** above the slider
and **Base / bottom of bin** below it (Fix 078; formerly "Vertical
position"). The visible control no longer shows a percent-from-top/bottom
readout or a bin silhouette; the underlying stored percentages and their
geometry/validation are unchanged, and exact values remain available to
assistive technology.

### Wall selection

- Front.
- Back.
- Left.
- Right.

Multiple selected walls can receive openings where legal.

### Compatibility

Wavefinity prevents Side Openings from occupying wall regions needed by incompatible features such as:

- Inside Grip;
- rim Text;
- Edge Mount;
- lid/stack bridges.

---

## 7.4 Edge Mount

**Purpose:** Add an external label and/or screw mounting to one bin edge.

### Mounting side

- Front.
- Back.
- Left.
- Right.

### Label type

- **None**
- **Separate Part**
- **Integrated**

Separate Part is the replaceable support-friendly label system. Integrated fuses the label structure into the bin.

### Label controls

- label text;
- flip text;
- length:
  - Full Side;
  - Text Length;
- text depth;
- label style where applicable;
- projection;
- plate thickness.

### Separate-label support

- locking/saddle behavior for the replaceable label;
- standoff ribs;
- automatic or manual rib quantity where applicable;
- permanent bin-side support geometry where required.

### Screw mounting

- Screw Mounting on/off.
- Screw count.
- Pattern/orientation.
- Screw-hole diameter.
- Screwdriver access diameter.
- Distance from top.
- Automatic or custom spacing.
- Printable pointed/self-supporting access-roof geometry.

### Compatibility

Wavefinity checks conflicts between Edge Mount and:

- rim labels/Text;
- Separate Edge Mount labels and lids;
- Separate Edge Mount labels and direct stacking;
- Side Openings;
- Inside Grip / screwdriver access;
- other wall occupancy.

---

# 8. Labels and text systems

Wavefinity has several distinct label systems. They should remain separate in this document because they serve different physical parts.

| Label system | Where it appears | Main choices |
| --- | --- | --- |
| **Text feature** | Ordinary bin base or rim | Base/Rim, Inlaid/Raised, depth/height, letter height, rotation, rim side |
| **Divider labels** | Individual Divider compartments | No label / On base / Rim level; per-compartment text |
| **Lid label** | Ordinary-bin lid | On/Off, text, horizontal/vertical, Inlaid/Raised, relief |
| **Edge Mount label** | Outside edge of ordinary bin | None / Separate Part / Integrated, text, flip, length, depth/style, projection/thickness |
| **Storage Box label** | Storage Box case front | No label / front label, Flat/Wavy front-label style |

## 8.1 Divider labels

Divider labeling supports:

- **No label**.
- **On base**.
- **Rim level**.
- Per-compartment label text.
- Coordinate/placeholders while editing compartment layouts.
- Exported base/rim lettering as real geometry.

## 8.2 Label conflict rules

Because multiple label systems can occupy the same wall/rim, Wavefinity explicitly guards incompatible combinations instead of allowing intersecting geometry.

Examples include:

- rim Text vs Side Opening;
- rim Text vs Separate Edge Mount label on the same side;
- Separate Edge Mount label vs lid;
- Separate Edge Mount label vs direct stacking.

---

# 9. Straight and wavy interior-wall choices

The Wavefinity outer shell is itself wavy/interlocking, but several interior-holder systems independently support straight or wavy walls.

Important user-facing choices include:

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

Other feature families may use wavy geometry automatically when blending into the Wavefinity shell. The exact wave shape and print-clearance constants remain code-owned.

---

# 10. Connectors

Connectors join neighboring Wavefinity bins.

## 10.1 Side Connector

The normal connector joins two bins across a shared seam.

### Bin heights

- Same.
- Different.

For different-height connections:

- A height.
- B height.

### Connector controls

- tolerance;
- length;
- arm thickness.

Connector wall fit derives from the bin wall; the user does not set a second connector wall thickness.

---

## 10.2 3-Way Corner Connector

- Joins three bins around one grid corner.
- Open quadrant is chosen by rotating the printed connector.
- Requires compatible equal-height/equal-wall bins.
- Uses a T-shaped top/cap layout around the open quadrant.

---

## 10.3 4-Way Corner Connector

- Joins four bins around one grid corner.
- Requires compatible equal-height/equal-wall bins.
- Uses the full four-way cross geometry.

---

## 10.4 Corner-connector rules

- Corner connectors do not support different bin heights.
- Corner connectors need enough X/Y footprint for the connector geometry.
- Corner quantity can create multiple separate copies on a plate.
- If the current bin combination cannot support corner connectors, Wavefinity falls back to Side-connector-only behavior and explains why.

---

# 11. 2D design tools

Design has a dedicated 2D work area for editing interior layout.

Capabilities include:

- select interior parts;
- move/reposition interior parts;
- edit part footprint/layout;
- Divider editing;
- remove Divider segments / create compartment spans;
- Photo Nest outline editing;
- keep the 2D layout synchronized with the real 3D design.

The 2D editor is for interior layout. Space placement is handled in the Space work area.

---

# 12. 3D preview

The Designer includes a real geometry preview.

## Views and display

- 3D.
- 2D.
- Top.
- Side.
- Bin / Interior display controls.
- X-ray behavior where applicable.
- Zoom / Fit / reset-style controls.

## Interaction

- Clicking visible geometry can select the corresponding exact part/option.
- Selected geometry can open its editor.
- FRONT orientation tracks the physical bin front.

## Validation

The preview is also part of the product validation loop:

- fit failures;
- feature collisions;
- illegal geometry;
- bin-size requirements;
- feature-specific errors.

A design that cannot pass real geometry validation should not be treated as printable.

### Invalid-settings overlay (Fix 078)

When the current design is invalid, the active Design preview (2D or 3D,
whichever is showing) overlays a prominent red **Invalid settings** heading
with the actual problem underneath, so the message sits where the user is
already looking rather than only in a footer strip. A hard preview build
failure shows the same overlay. Switching between the 2D and 3D views
carries the same invalid state with it; the overlay never appears over the
Space/Drawer view, and only the latest preview request may show, update, or
clear it. The existing error panel below the preview remains for additional
actionable detail (for example a clickable jump to the offending part) and
is secondary to the overlay.

---

# 13. Printing, saving, and generated files

## 13.1 Ordinary-bin output

Depending on current features, Wavefinity can produce:

- bin;
- removable insert;
- lid;
- separate Edge Mount label;
- Side connector;
- 3-Way Corner connector;
- 4-Way Corner connector;
- other printable parts belonging to the design.

## 13.2 Save choices

Current Designer save/output choices include combinations such as:

- Save Bin.
- Save Bin + Connectors.
- Save Connectors.
- Save Bin + Lid where applicable.

The visible action set changes to match the current design.

## 13.3 Print choices

The main print workflow explicitly supports:

- **Print with Connectors**.
- **Print without Connectors**.

This prevents connector generation from being an invisible print-side choice.

## 13.4 Bambu Studio handoff

- Local Wavefinity can hand generated parts to Bambu Studio.
- The handoff should preserve slicer settings rather than overwrite them with unwanted Wavefinity profiles.
- The user can change the selected slicer.
- Space bulk printing can send multiple eligible bins/parts through the print workflow.

---

# 14. Spacers

Spaces can use **Spacers** to fill leftover physical area.

- Shown separately from ordinary bin Inventory rows.
- Can have their own counts.
- Can be printed in bulk.
- Used to stabilize/fill Space layouts rather than store objects.

---

# 15. Undo, redo, and design history

- Undo.
- Redo.
- Ctrl+Z behavior.
- Design changes and Space-layout changes are owned by the active work area.
- Design mutation guards prevent conflicting operations from racing each other.

---

# 16. AI Design — Fix 073, revised Fix 078

**Status: Current — accepted and integrated into `main`.**

AI Design is a Designer workflow for turning a natural-language object description into a legal Wavefinity bin design **without Wavefinity directly calling an AI provider**.

## 16.1 User flow

1. Click **AI Design**, a persistent major action in the Options area (moved off the cramped Bin Name row in Fix 078; it stays visible even while an option is being edited).
2. Describe one object in a multiline text field, or pick a saved entry from **Recent descriptions** (this Space's last 10 successful descriptions; selecting one only fills the field, it never generates by itself). (If you have an unsaved interior part open, Wavefinity saves it into the design first so the prompt matches exactly what you see.)
3. Optionally use **Dictate** when the browser supports speech recognition.
4. Click **Generate Prompt** (disabled until the description is non-blank, and again once a prompt has been generated for the exact current text).
5. Click **Copy Prompt** (the button itself reads **Copied** after a successful copy, and resets whenever a new prompt is generated).
6. Paste it into any external AI.
7. Let that AI ask follow-up questions when measurements or intent are unclear.
8. Paste the final JSON response back into Wavefinity.
9. Click **Modify Current Bin** to apply the result to the bin you have open, or **Generate as New Bin** to keep the current bin and create a new one from the result.
10. Wavefinity proves the result (schema, request/context identity, canonical validation, real geometry, Space rules) and, if valid, adopts it exactly as the chosen button describes; an invalid result changes nothing and can be repaired (16.6).

Every time the dialog is opened it starts a fresh transaction: description, prompt, pasted answer and status all clear (Recent descriptions does not). The dialog is sized for reading a real prompt (about 840 px wide on desktop) and opens on a compact six-step guide — Describe object → Generate Prompt → Give prompt to AI → Copy response → Paste answer → Generate Bin — instead of a paragraph of instructions.

## 16.2 What the AI is told

The prompt contains:

- the user's object description;
- current bin context;
- current typed-Space constraints when applicable;
- an authoritative capability manifest naming, for every current palette-visible part, the exact current Designer control for each field the AI may set (not merely that a capability exists) -- footprint zone, quantity (and what Auto means), run direction, alternate ends, and the stored item's shape/length/diameter/fit (Bore offers all six shapes including the fixed hex-bit sizes; Cradle is always round) -- with legacy/derived fields (for example Bore's older orientation field, Divider's older single-axis quantity, Post's engine-only grid override, Cradle's derived floor gap/rib thickness, Text's unused font field) explained as structure to preserve, never offered as a second control for the same behavior;
- legal modifier families, with a canonical example of each Lid & Stacking configuration (Stackable Bin, Stackable Lid, Lid with Handle);
- important compatibility rules;
- the current bin's interior bounds as a reference only: if the AI changes the bin size, every part must fit the interior of the design it returns;
- a complete canonical design example;
- the required response schema;
- an optional link to Wavefinity's public `ai-features.md` reference, for background only -- the AI is told the data above always wins and the link is never required.

The AI can choose any legal user-facing Wavefinity feature that helps solve the request.

## 16.3 Safety/validity model

Wavefinity, not the outside AI, remains authoritative.

The AI returns design data, not geometry.

Before applying an answer, Wavefinity checks:

- response schema;
- request identity;
- context identity;
- canonical design parsing;
- structural-design rejection;
- actual geometry preview;
- fit/errors;
- active Space constraints, including the Pegboard minimum bin sizes New Bin already uses;
- the manifest's own public-control rules: an item shape not legal for that part, a Cradle item that is not plain round, a Bore item with the wrong fit clearance, a hex-bit item that is not exactly the fixed preset or is leaned, or an answer that tries to set a part's layout through a legacy/derived field instead of its current control;
- (Fix 078) a non-blank, 1–80 character `part_name`;
- (Fix 078) at most one rim Text feature in the returned design;
- (Fix 078) in a capped Space (Drawer, Storage Box), that no Bore-held object's computed top exceeds the Space's height — Surface and Pegboard have no such cap.

Both **Modify Current Bin** and **Generate as New Bin** run this identical proof before either may change anything; the button clicked is only the adoption choice, never a shortcut around validation.

Invalid designs do not modify the current design.

## 16.4 Stale-response protection

An AI answer is rejected if the user changed the relevant:

- design (including the bin name);
- Space;
- Space dimensions/rules;
- Inventory identity/binding;
- structural context

after the prompt was created.

The user must then generate a fresh prompt rather than applying stale AI output.

## 16.5 Adoption and naming (Fix 078)

There is no "clean vs. edited" auto-chooser any more. Every AI Design dialog for an ordinary bin always offers the same two adoption buttons, and the person's click is the only thing that decides what happens:

- **Modify Current Bin** replaces the open bin's design with the proven result, keeping its current Inventory identity. If the bin already has a non-blank name, that name is kept exactly even when the AI proposed a different one; only a blank current name may adopt the AI's proposed name.
- **Generate as New Bin** keeps the current bin (saving it first in a typed Space) and installs the proven result as a new bin, using the AI's proposed name.

Either way, Wavefinity — never the outside AI — has the final say on the name: trimmed, case-insensitive comparison against every other surviving ordinary-bin Inventory row, with a colliding name suffixed `Name (2)`, `Name (3)`, and so on (one existing ` (N)` suffix is stripped first so renumbering doesn't stack). The AI is asked for a short, descriptive name and may see existing Inventory names as an advisory hint to avoid an obvious duplicate, but it never has to invent its own numbering.

## 16.6 Repair prompt

If the external AI returns invalid JSON or an invalid design, Wavefinity can create a **Make AI Fix Its Answer** repair prompt containing:

- the required schema;
- the same request/context identity;
- the previous AI response;
- a safe validation error;
- instructions to return one corrected JSON object.

The repair prompt is shown, never auto-copied; **Copy Prompt** owns copying it the same way it owns the initial prompt. Only a problem in the AI's answer is repairable this way. If the answer was fine but Wavefinity itself failed afterward (service, save or apply), no repair prompt is offered and Wavefinity says whether the design was already applied.

## 16.7 Space object-height cap (Fix 078)

The generated prompt states the active Space type and either a hard cap (Drawer and Storage Box: the Space's own height) or "no hard vertical cap" (Surface, Pegboard, or no active Space). AI Design distinguishes an object's own length from how far it inserts into a Bore and from the bin's height, and targets roughly 30 mm of a hand-retrieved object staying grippable above the bin rim — but in a capped Space that preference never overrides the hard cap: the full object envelope, including width and tilt, must stay below it. AI Design also prefers a wavy Bore variant over its straight counterpart when the two are otherwise equally suitable, without switching between the Base and Walls Only families just to get "wavy".

## 16.8 AI limitations

- One object per AI request in V1.
- No built-in OpenAI/Anthropic/Gemini account, API key, SDK, or direct provider call.
- Speech dictation is optional browser progressive enhancement.
- Photo Nest can be recommended but its contour cannot be fabricated from text.
- AI cannot return a Storage Box case or Base Trim as the ordinary-bin result.
- Critical missing measurements should be asked about rather than guessed.

---

# 17. Important compatibility rules

This is a high-level checklist, not a replacement for the real validator.

- **Removable insert** is incompatible with shell features that must be physically built into the bin wall, such as Inside Grip.
- **Side Openings**, **Inside Grip**, **rim Text**, and **Edge Mount** can conflict when they need the same wall area.
- **Separate Edge Mount labels** can conflict with lids and direct stacking.
- **Lids/stacking** can require minimum wall/base strength.
- **Raised lid labels** cannot occupy stacking contact areas.
- **Side connectors** are unavailable when a lid occupies the required rim geometry.
- **Corner connectors** require compatible equal-height/equal-wall bins.
- **Pegboard** mounting fields are Space-controlled.
- **Surface** base behavior is Space-controlled.
- **Storage Box/Base Trim** are structural Space outputs, not ordinary Designer bins.
- **Photo Nest** contour data is media-derived and should never be synthesized as ordinary text settings.
- User-visible automatic changes should be explained rather than silently rewriting typed values.

---

# 18. Feature-document maintenance checklist

When a fix changes the product, update this file if it changes any of the following:

- Space type or Space behavior.
- Space setup field.
- Structural Space output.
- Inventory lifecycle/action.
- Bin shell setting.
- Interior print mode.
- Wall/base option.
- Interior part.
- Interior-part setting.
- Straight/wavy wall behavior.
- Label system.
- Lid/stacking behavior.
- Grip/opening/mount option.
- Connector type or rule.
- 2D/3D editing behavior.
- Save/Print output.
- AI Design capability.
- User-visible compatibility/conflict rule.

### Documentation rule for future fixes

A feature-changing fix should answer:

1. **What user-facing capability changed?**
2. **Which section of `features.md` must change?**
3. **Did an option get added/removed/renamed?**
4. **Did compatibility with another feature change?**
5. **Did the Space, preview, save, print, or inventory behavior change?**

If the answer to any of those is yes, update this catalog as part of the fix.

---

# 19. AI-facing documentation

`ai-features.md` is the compact public reference intended for outside AI systems used with AI Design. It supplements the request-specific machine-readable prompt; it does not replace the live catalog/rules embedded by the running app.

When a product change affects what an outside AI can legally select, configure, return, or must avoid, update both this catalog and `ai-features.md` in the same fix.

---

# 20. Source-of-truth boundaries

Use this document to learn **which features exist** and how they relate.

Do not use this document as the sole authority for exact numeric geometry rules.

Authoritative implementation details live in the owning code, including areas such as:

- `wavefinity_web.py` catalog/rule payloads;
- `organizer_inserts/_registry.py` and feature modules;
- `organizer_product_rules.py`;
- `organizer_spaces.py`;
- `organizer_pegboard.py`;
- `organizer_edge_mount.py`;
- `organizer_lid_handle.py`;
- `organizer_stack.py`;
- browser UI/state logic under `web/`.

When this file disagrees with the current accepted code, fix the document.
