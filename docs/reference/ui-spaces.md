# Wavefinity UI and Spaces — detailed reference

Read only the sections relevant to the current UI or Space task; [README.md](../../README.md) is the short product overview.

## UI design elements

The control panel is ordered by **blast radius**: a setting sits above
everything whose meaning it can change.

**The Designer designs a Bin.** The Designer always means an ordinary **Bin**. A **Storage Box** and a **Base Trim** are
*structural outputs of their Space*, never Designer objects and never Inventory
rows: a Storage Box Space saves or prints its own case (settings live on the
Space and are edited in **Edit Space**), and a Surface Space saves or prints its
own Base Trim, both from the Space header controls. Lid & Stacking is
always available in the bin Specification area. The selected wall/base values are shown and saved; they are
never silent generation-only overrides.

**Lid & Stacking** offers three ordinary-bin **Stacking Methods**: **Stackable
bin on bin** stacks directly with no lid, **Stackable bin on lid** closes the bin
and keeps a flat seat for the next bin, and **Lid with handle — non-stackable**
adds a knob but does not stack. The Specification row shows the lid state and opens these controls in place. Controls follow the method: bin on bin shows no
lid controls; bin on lid shows Lid thickness, Lid fit and the label controls;
lid with handle also shows Handle type, size and position and full label
choices. Choices you set under one method are remembered when you switch away
and back, but hidden ones never change what is generated.

The lid closes **flush**: its exterior meets the bin outside wall at the rim with
no step or gap, and its underside rests on the rim. Only the plug that enters
the bin mouth has running clearance, set by **Lid fit** — **Tight 0.15**,
**Standard 0.25** (default, and the fit older designs always had) or **Loose
0.35 mm per side**. Lid fit changes only that plug; the direct bin-on-bin foot
and a lid's stack rim keep the accepted 0.25 mm stack fit, and the
lid's lock bumps keep the same interference at every fit. **Lid thickness** shows
each choice as a measurement first — for example `2.8 mm — Medium` — resolved
for the current bin by the same geometry that builds the lid. **Lid labels** are
**Inlaid** or **Raised**, with **Inlay depth** or **Raised height** of 0.2, 0.4,
0.6 or 0.8 mm (new labels start at 0.4 mm; older files keep their 0.4 mm inlaid
and 0.6 mm raised). Inlay never cuts into the lid's required floor or seat, and
a lid with Raised lettering cannot receive a stack. The **Lid for stacking** lid type has a rim about 2 mm tall standing on its top face, which the Stackable Base of the bin above sits into (the lid counts once in stack heights as its thickness plus the 2 mm rim). A Hinged lid never receives a stack, and a lid with the Knob or Raised lettering cannot receive one either. The only handle is the **Knob**: a square post with a diamond head
(flared at 45 degrees, tapered back to a small flat top, printable without supports); a handle too large for
a very small lid is refused with a message to choose a smaller size or a larger
lid, never shrunk. The reported closed height is the tallest point of the whole
lid, handle and lettering included. Storage Box (B4B) lids are a separate system
and are not changed by any of this.
A Divider can supply one lid label per compartment. Once any compartment lid
label contains text, clear those labels before changing the Divider layout.
Side connectors are unavailable while a lid is fitted.

**Controls follow their meaning, not their mechanism.**

- A **select** is for choosing one of several named states —
  *Lid type*, *Lid head-room*, *Show*, *Orientation*, *Base*, *Walls*, and the Storage Box case's
  *Stacking* and *Carrying handle*. This holds even at two
  options: a row of big buttons for a two-state setting reads as two actions,
  and gives no clue the two are exclusive.
- A **checkbox** is for a genuine on/off with no second state worth naming —
  *Lightweight base* on a Surface bin, *Flip text* on an Edge Mount label and
  *Screw Mounting*.
- A **button** is for something that *happens* — *Save*, *Reset*, *Top*,
  *Show Log*. Nothing that merely records a preference is a button.

Checkbox rows put the label first and the box on the right, everywhere.

**Settings that belong together live together.** A dependent control sits
directly under the control that reveals it (*Walls* → the thin-wall warning; a
lid's *Label* choice → its label text). One setting has exactly one control.
Anything naming the output file — the *Bin Name* — sits at the top of the
Designer, before the dimensions, not in the middle of the build form. The
Storage Box case settings group their selects as *Lid*, *Case options*, *Label*
and *Material*, and the ordinary bin's Lid & Stacking editor groups *Stacking Method*,
*Lid*, *Handle* and *Label* the same way.

**Automatic changes are shown, never silent.** When the app overrides what was
typed — stacking raising the wall and floor — it
says so in plain language in a note under the control that caused it, and it
never writes the new value back into the field the user is typing in.

Width and Depth fields show only the physical size. Their inside dimension
(or updating status) and whole-unit count wrap below each input. Formatting
leaves focused Width and Depth values alone; blur commits and reformats them.

**One screen, two sides.** The left side edits, the right side shows. At the
top of the left side is the **selection tree** for the open Space: the
**Layout or print your space** line, then the container (Storage box, Drawers
cabinet or Base Trim) when the Space has one, then its bins. Whatever is
selected in the tree decides what both sides show. There is no undo/redo
anywhere in the app (Fix 1137): every change commits immediately. A Space has
only two mental objects: **the Space** and **the bins inside it**. In a bin's
editor the main build fields, **Options** and **Connectors** appear in
separate cards. **Manage Spaces** in the top bar goes back to the open screen
(your Spaces, *My Bins / No Space*, and the New Space choices).

**The drawer is seen through a camera looking into it.** It is a real 3D
view: bins are boxes in perspective, showing their tops, their fronts and the
sides that face you. But it is not a free orbit. The camera always stands in
front of the drawer and above it. You get presets (*Look in*, *Overhead*,
*Low*), an *Angle* slider for how steeply you look down, a *Turn* of up to 30°
to either side, pan (drag the floor, or right-drag) and zoom (wheel, −/+,
*Fit*). It never spins round or looks from underneath, so the front of the
drawer is always nearest you. That is what makes "a short bin behind a tall
one" visible, and it means dragging a bin away from you always moves it back.

**Colour means height.** Bins run from light (short) to dark (tall) teal, Storage Box
cases purple, spacers sand. A bin shows its name, or its size when it
has none. Red is a real fault (overlap, sticking out, too tall for the drawer);
a dashed orange outline is the softer height-order warning.

**Stacks read at a glance.** A stack is drawn as its bins standing
on each other, each foot sunk into the bin below. A stackable bin's swatch
carries a ⇅. Dropping a bin on a same-size bin that stacks the same way snaps it
on top with the sides aligned; anything else is refused, and the refusal says why.

**Bins are placed by hand, from the tree.** Every ordinary bin is one Inventory
row and is placed at most once. The tree lists every bin in two groups,
**Not placed** first and **Placed** below (a Storage Drawers Space groups placed
bins by drawer); it is never filtered. Drag a bin from the tree into the
layout to place it; drag a placed bin back onto the tree to unplace it
(Story 2855).

**Field labels stand alone.** No section or group label may merely name the
fields below it: every field label must stand alone without a group heading.
When a field only makes sense under a heading, the heading's words fold into
the field's label instead (*Label mode* and *Opening shape*, not *Mode* and
*Shape* under a *Label* or *Opening* heading). Headings that carry a working
control, screen and dialog titles, and list headings that do not explain
themselves are not group labels and stay.


### How the screen behaves (Andrew's UI/UX rules)

These are the product owner's rules for the whole app. New work follows them;
when a change would break one, ask first. Items marked *(planned, Story N)* are
filed but not built yet.

- **The tree dictates both sides.** Only one tree row is ever selected.
  Selecting the Layout line, the container or a bin shows that thing on the
  left and its view on the right. Selecting the Space line or the container
  deselects any bin. Clicking a bin in the layout highlights that same bin in
  the tree (Story 2849).
- **One Manage screen.** The Layout line (its click and its one **Manage**
  button go to the same place) is where you lay out *and* print: the layout on
  the right, the print list on the left. The Space's name and size are shown
  there with editable name and usable size for every Space type. Copy Space
  makes a separate Space and leaves the original open. Delete Space asks in
  place before removing the Space and all its bins; there is no undo. A size
  change that strands a placed bin is refused and names the bins in the way.
  Container construction settings stay on the container row (Story 2933).
- **Peek without leaving the layout.** Clicking a bin in the layout opens its
  details on the left while the layout stays on the right; change its height
  or stacking and the layout updates in place. Click empty floor or press Esc
  to go back to the print list. Clicking the bin's row in the tree, or the
  **3D view** button, opens it fully (Story 2855).
- **After Delete nothing is selected.** A bin's **Delete** (on its selected tree
  row) acts at once, with no confirmation, removes the bin and its files for
  good, and leaves nothing selected (Stories 2836, 2846, 2847).
- **Messages appear where the action happened.** A refused drop ("can't stack
  here") shows at the drop point, not at the top of the screen (Story 2850).
  A note about a field sits under that field. If the action already shows its
  result (a bin visibly moving into *Not placed*), no message is needed
  *(planned, Story 2859)*.
- **Hints in place, not pop-ups.** Help is a quiet line or a placeholder in the
  spot where the user is looking, and it disappears the moment they act. There
  is nothing to acknowledge or dismiss. Examples:
  - an empty layout shows a centred note, *Drag bins to place / Drag onto a
    bin to stack*, that vanishes as soon as a drag starts or a bin is placed
    (Story 2854); a Space with no bins at all says *No bins yet / Choose New
    Bin to make one*, each empty drawer of a Storage Drawers Space gets its own
    note, and a Pegboard never mentions stacking *(planned, Story 2859)*;
  - a Space with no bins shows *No bins yet. New Bin makes your first one.* in
    the tree until a new bin editor opens; its selected temporary row follows the
    typed name and disappears if the unsaved editor is abandoned (Story 3100);
  - the bin's Height field says how tall a bin the Space takes, and turns red
    when the bin is taller *(planned, Story 2861)*;
  - with no slicer found, a line under Print says so and links to Printer
    Settings *(planned, Story 2860)*;
  - the Spacers section says *N gaps could use spacers* or *Some spacers no
    longer fit your bins* under Refresh Spacers, and says nothing once the
    spacers match *(planned, Story 2865)*;
  - the very first launch, with no Spaces, says *No spaces yet - pick what
    you're organizing below* *(planned, Story 2862)*.
- **Keep questions and choices to a minimum.** Prefer one sensible default
  over a question; offer a choice only when the user really decides something.
- **Two dynamic batch buttons.** Under the print list: with nothing ticked they
  read **Print whole space** and **Export whole space**; tick one bin and they
  read **Print bin** / **Export bin**; tick several, **Print N bins** /
  **Export N bins** (Story 2851). Export went away once files built themselves
  (Story 2857), leaving Print as the one batch button. The container gets its
  own tick row in that list, and Spacers / Fill Empty Space sit under it
  (Story 2858).
- **Height colours with an always-on guide.** In the layout a bin at the
  Space's full height has no rim colour, a shorter bin has a yellow rim, and a
  bin taller than the Space has a red rim. A small guide under the layout
  always explains the colours and the stacking icon (Story 2852).
- **One stacking icon.** A stackable bin carries one icon with an up arrow
  (it can take a bin on top) and/or a down arrow (it can sit on a bin), the
  same icon in the layout and in the lists, kept inside the bin's outline
  (Story 2852).
- **Files are built in the background, so Print is fast.** A bin's 3MF is
  rebuilt a few seconds after its design changes; Print only waits
  (*Finishing files…*) when a build is still running *(planned, Story 2857)*.
- **Per-bin files are kept, plus one combined print file.** Each bin keeps its
  own 3MF in the Space folder. Printing to Bambu Studio hands it one combined,
  pre-spaced file, *Last Printed.3mf*, overwritten on every print, so parts
  never land on top of each other *(planned, Story 2856)*.

**UI reviews:** The owner tests and judges actual screens. Coders do not run scripted browser sessions, take automated test screenshots, or produce manual user-testing plans.

### The flow, start to print (every Space type)

1. **Open screen.** Launch shows your Spaces, *My Bins / No Space* (bins with no
   Space) and the five New Space choices: **Storage Box**, **Storage Drawers**,
   **Surface**, **Drawer** and **Pegboard**.
2. **New Space.** Choosing a type opens its setup on the left (name and size;
   Pegboard also picks its board standard; Storage Drawers configures its
   cabinet and drawers). **Create Space** makes the folder under
   `Documents/Wavefinity/<Space Name>/` and opens the Space.
3. **Where it lands.** A Space with a container (Storage Box, Storage Drawers,
   Surface) opens with the container selected, showing its design. A Drawer or
   Pegboard Space opens on its first bin, or on the Layout line when it has no
   bins yet.
4. **Make bins.** **New Bin** (top of the tree) adds a bin and opens its
   editor; it appears in the tree under *Not placed*. Its design saves as you
   work.
5. **Lay out.** Select the Layout line. Drag bins from *Not placed* into the
   layout; they snap to the 7 mm grid (or to the holes on a Pegboard) and
   refuse overlaps and the Space edge. Drop a bin on a compatible bin to stack
   it. Click a bin to peek and adjust it; the layout updates in place. In a
   Storage Drawers Space the small 1 / 2 / 3 buttons on the Layout line switch
   drawers.
6. **Fill gaps (optional).** On the Manage screen, Drawer, Storage Box and
   Storage Drawers Spaces use **Refresh Spacers** to brace the placed bins
   against the side and back walls (see *Spacers* below); a Surface turns free
   cells into Fill bins instead. Pegboards have neither.
7. **Print.** On the Manage screen tick bins (or nothing, for the whole Space)
   and press Print. The container prints from its own tree row, or from the
   print list *(planned, Story 2858)*. Bambu Studio opens with the parts; a bin
   is marked *Printed* once the slicer has opened. Changing a printed bin
   makes it not printed again.

---

### Using the browser UI

The page is split between intent-based controls and a large responsive
workspace. The top design controls contain the dimensions, print mode and interior
interior-part editor. **Options** below them holds the interior-part
palette and the bin-level options (Lid & Stacking, Inside Grip, Side Openings,
Edge Mount). The bin's name is the *Bin Name* field at the top, before the
dimensions.

**Base** and **Walls** are named preset selects sitting side by side. *Standard*
walls keep the original 0.8 mm wall; the other presets run from very thin
(0.4 mm) up to a 2.4 mm maximum. Only the cavity moves, while the exterior wave
and 7 mm grid stay fixed. Custom-wall connectors are generated for that wall
thickness and include it in their filename. Use a connector only with bins of
the same wall thickness.

The 3D preview is real camera-independent geometry returned by Python and drawn
locally by the browser. Drag to rotate, use the wheel to zoom, and double-click
to reset. Click an interior part to open the 2D layout for adjustment. A single pixels-per-millimetre scale is chosen from the available
width and height, so enlarging the browser makes the model larger without
stretching it. The 2D tab uses the same rule and supports click-to-select,
drag-to-move and blue-corner resize. It draws the bin's true wavy interior,
not the flat placement rectangle - that rectangle still shows as a dashed
reference line, since every non-full-span interior part has to stay inside it, but
the wavy outline is what answers "does this actually reach the wall."

Selecting an interior part immediately builds its actual mesh and shows it
live, highlighted, right inside the main 3D and 2D bin views - at the bin's
own scale, alongside whatever is already placed, not on a separate isolated
canvas with its own camera. Parameter changes rebuild that draft after a
short typing pause, before it is added to the layout; a draft that is
currently invalid falls back to a red placeholder shape in the same spot, so
a rejected edit is never mistaken for no change happening. Choosing a part in
the **palette** adds it (finding open floor space); selecting a placed one
loads it back into the same editor for exact changes. There is no separate
*Add interior part* button. Invalid dimensions, overlaps, reserved
scoop/rim-label space, and lettering that cannot fit are reported beside the
preview and refused at export.

**Save design** downloads the existing `.wavefinity.json` format, and **Open
design** validates that format through Python before using it. Generated `.3mf`
files are written to the shown output folder, which is sticky — the server
saves it to `wavefinity_prefs.json` in the current user's profile (`%APPDATA%\Wavefinity` on Windows, `~/Library/Application Support/Wavefinity` on macOS, `~/.config/Wavefinity` on Linux; an old app-adjacent file is read once as a starting point and never deleted), so it survives a reload
or a different browser rather than resetting every launch. The browser API is
same-origin only, accepts JSON only, and applies a restrictive
content-security policy so an unrelated web page cannot invoke local file
generation.

### Base Trim

**Base Trim** is an open-centre rectangular perimeter ring, not a tray: there
is no bottom beneath the bins. Its X/Y values describe the enclosed Wavefinity
bin field in whole 7 mm units, independently of ordinary-bin wall thickness.
The inner wall is the existing globally phased Wavefinity mating wave; internal
bin seams are not encoded into the trim, so bins may be rearranged later as
long as they still fill that same rectangular field. The clean outer wall is
rectangular and tapers inward by 1 mm per side from bottom to top.

A new trim defaults to a square **Medium — 7.5 × 7.5 mm** size. Trim size is
chosen from five named square presets, not free-form width/height fields:

| Preset | Size |
|---|---|
| Small | 6.5 × 6.5 mm |
| Medium (default) | 7.5 × 7.5 mm |
| Large | 10 × 10 mm |
| XL | 15 × 15 mm |
| XXL | 20 × 20 mm |

The default printer bed is 256 × 256 mm; Wavefinity reserves 10 mm from each
edge, leaving a 236 × 236 mm effective area. Bed X/Y remain machine
preferences.

A ring that fits the effective bed in either orientation prints as one piece
with no joints. Larger rings split automatically: all four corners remain
integral and only straight rails split as needed. There is one section joint,
support-free and printed flat: the **Drop-in dovetail**. It is a full-height
vertical dovetail key that scales with trim size — split sections join by
lifting one section, aligning the key over the mating opening, and lowering
it straight down; once both pieces lie flat, the wider head resists
horizontal pull-apart, so vertical removal is the only way apart. *Auto size
from Space* accepts one completely filled rectangular block and uses its
dimensions only. A Base Trim is never inventory, and choosing Base Trim
joining suppresses separate side connector generation; ordinary bins retain
side connectors when *Side connectors* is selected. A Base Trim name is
optional.

A design saved with an older Snap tabs / Sliding dovetail / Puzzle joint
choice, or with non-preset or non-square width/height, still loads: the old
join value normalizes in memory to Drop-in dovetail, and the size selector
shows a temporary *Legacy — W × H mm* option until a preset is picked. It is
never rewritten on disk just by opening it.

**Maintainer note:** for a local Surface Space, Ctrl+Shift+click
**Print Base Trim** in the Space header sends a small ~50 mm two-piece
drop-in-joint sample instead of the normal trim, to physically check the fit
before a full print. It is not a normal UI control; an ordinary click still
prints the normal Base Trim, and the same chord on Storage Box's Print has no
special behavior.

Base Trim deliberately does **not** use `BoxSpec`. It saves as version 6 with
`design_kind: "base_trim"`: `box.x` and `box.y` are enclosed field dimensions,
and `box.z` is trim height. `base_trim` stores the perimeter settings. The empty
fused `layout` block is structural saved-design compatibility only—Base Trim
does not accept interior parts.

```json
{
  "version": 6,
  "design_kind": "base_trim",
  "box": {"x": 16, "y": 48, "z": 7.5},
  "base_trim": {
    "version": 1,
    "width_mm": 7.5,
    "join_type": "drop_in",
    "bed_x_mm": 256,
    "bed_y_mm": 256,
    "auto_size": false
  },
  "part_name": "",
  "layout": {"version": 1, "mode": "fused", "snap": 1, "features": []}
}
```

### Inventory, and Spaces

Every selected save folder keeps an inventory by default: generating a bin
or Storage Box adds it to `Wavefinity bins.md` (the same name in every folder, so renaming the folder never orphans it; one old `<name> bins.md` is adopted automatically). A checkbox
beside the save folder, *Keep inventory for this folder*, lets a user turn
that off for a normal, untyped **Design** folder - files still save
normally, but nothing new is logged. Turning it off never deletes an
existing inventory file, and turning it back on resumes logging to the same
file.

**Surface size** is entered as the maximum finished *outside* width and
length in mm. Wavefinity rounds down to the largest whole-unit interior field
that fits (`outside = field + mating gap + 2 × trim width`); Space data still
stores the interior field and the trim size. The Surface owns its **Base Trim**:
**Save Base Trim** / **Print Base Trim** in the Space header build it from the
Surface definition (with the printer-bed size used to split it) and never create
an Inventory row. A bin you design saves itself into Inventory as you go and
reopening the Space later restores the design you were editing (resume is
recovery, not an Inventory identity). Each Inventory row has **Duplicate**.

A folder is either an untyped Design folder, or a typed **Space** - a
**Drawer**, a **Storage Box**, a **Surface**, or a **Pegboard**. *Create New Space*
configures the Space's type and dimensions first and chooses the save folder
last; *Open Existing* can instead turn an already-selected folder into a
Space, or use it without a type. The top-level **Space** button then shows
that Space's inventory. A folder can already hold a full
inventory of bins before it becomes a Space - configuring one adds layout
information to that same inventory file rather than starting a second one,
so nothing already generated is lost or needs re-adding. Because a Space's
layout depends on the inventory it places, a typed Space always keeps
inventory on and the checkbox is disabled while one is active. An older
folder's legacy "Box" identity is migration-only: setting it up recovers it
as a Storage Box, never as a current Box. A legacy folder's older,
multiple-drawer layout is preserved as a compatibility exception - a new
Drawer Space otherwise represents exactly one physical drawer.

**Local Space storage location (Fix 058 K).** In the local app, *Create New
Space*'s automatic folder lives under `<space parent>/Wavefinity/<Space
Name>/`, with the user's Documents folder as the default parent - so the
default root is `Documents/Wavefinity/`. The parent is a single preference
(`space_parent`), resolved fresh from current preferences at every
auto-create so a change takes effect immediately, with no restart. The first
time Wavefinity runs with no saved parent and no already-established
`Documents/Wavefinity`, Welcome shows a small, non-blocking storage card with
the resolved default path and a **Change…** button; merely reaching Welcome,
opening the folder chooser, or cancelling it never creates
`Documents/Wavefinity` or any custom root - only an actual Create New Space
does. Choosing a different parent there (or an unavailable saved parent being
repaired) validates that the folder already exists and saves its absolute
path, without creating its `Wavefinity` child. If an explicit saved
`space_parent` is no longer usable, automatic *Create New Space* refuses to
create (with a concise, actionable error) rather than silently falling back
to Documents - the saved preference is left untouched, and the user repairs
the location with **Change…** on Welcome; the very next Create then succeeds
under the newly chosen parent, no restart needed. A brand-new user with no
explicit `space_parent` is unaffected and still gets the ordinary
non-blocking Documents default. Opening or recovering an existing/recent
Space remains independent of this guard. Hosted Wavefinity is
unaffected - it keeps its existing per-folder browser File System Access
behavior.

**Pegboard Space** supports standard 1-inch pegboard and IKEA SKÅDIS. Enter a
physical board size or a hole/slot count; Wavefinity derives the other value
and shows the centred residual border. The Space view draws the real round
holes or rounded slots and snaps bins to them. A bin occupies both its visible
front-view footprint and its exact receiver openings, so either kind of clash
is refused. The bin-side receiver is universal; generation also writes the
selected board standard's removable adapters. Cleat Count X (Auto or 1–5) and
Y (Auto or 1–3) control the receiver grid. Multi-cleat receivers stay
grid-aligned and side-biased, impossible counts are disabled or rejected, and
vertical ribs appear only across unsupported spans over 40 mm. Pegboard bins
do not use drawer stacking, spacers, or Base Trim.
Standard-pegboard bins need at least 48 mm height for the paired-hole adapter
to stay hidden behind them. Adapters are exported flat on a separate
print plate with board pegs pointing up; check physical fit on your actual
board before a full print.

Creating a new Space lands directly in the normal Bin editor with every
ordinary option (Interior print mode, Base, Walls, Inside Grip) still
visible; there is no tutorial or first-run card. A one-drawer Drawer Space's
name, width, depth and usable height belong to the Space: the Space header shows
them read-only with **Edit Space** (the Space Edit form), and an edit
there updates the loaded layout through the normal Drawer save path. An empty
Space view points to **New Bin** (see *How the screen behaves* above), and
spacer/connector actions stay disabled until there is something to work on.

**The four Space types** are exactly **Drawer**, **Storage Box**, **Surface** and
**Pegboard**. A Storage Box's internal kind is `portable` (a legacy `box` kind
still normalizes to it). Its Space X/Y/Z are the usable child-bin field width,
depth and height; the outer case is derived. The case settings live on the Space
as `space.storage_box` (`secure_lid`, `latch_count`, `latch_strength`,
`lid_headroom_mm`, `label_enabled`, `label_text`, `label_location`,
`front_label_style`, `stacking`, `handle`, `wall_mm`, `base_mm`), round-trip
through `.wavefinity.json`, `layout.space` and hosted Inventory text, and default to
the established B4B values when a legacy Space has no block. The Space header
owns the Space-level buttons - *Open Space…*, *Edit Space*, *Show Folder*, *New
Space* - plus the structural output: *Save Storage Box* / *Print Storage Box* for a
Storage Box and *Save Base Trim* / *Print Base Trim* for a Surface. Those outputs
are built by `organizer_outputs/space.py` as a transient empty-layout B4B (or Base
Trim) design from the Space definition and go through `/api/space/structural-*`,
which suppress Inventory logging entirely.

- **Space identity.** A typed Space carries a permanent `space_id` (UUID) in
  its `.wavefinity.json` (metadata version 9; identity required since version 5). The per-user profile keeps a
  registry of known Spaces (id, name, kind, last folder) as an index only.
  Renaming the folder within the same parent is recovered automatically by
  that ID; a folder moved elsewhere is recognised when you Open Existing it.
  A second folder copy carrying the same ID is refused, not merged. The same
  metadata file also holds the Space's exact resume design: closing the app
  mid-edit and reopening the Space later restores that same design, not a
  fresh starter - generating or printing it keeps it as the resume target,
  and a later edit replaces it again.
- **The inventory file** is a Markdown table, one row per bin design, with an
  **ID**, a **Kind** (bin, Storage Box, spacer, or a legacy hand-added row), a **Name**,
  a **Stack** (blank, `lid` or `direct` - how the bin was printed to stack)
  and a persisted **Status** of `in_design`, `saved`, or `printed`, displayed as
  **In Design** (editable design saved in the Space), **Saved** (current files exist),
  or **Printed**. There
  is no user-facing quantity: a row is one bin, and `Qty` survives only as a
  0/1 compatibility field derived from Status. Saving files is not printing. Print
  (direct, or in Space Inventory) marks each bin Printed exactly once, and only
  after Wavefinity handed it to Bambu Studio and the slicer opened
  successfully - it does not claim the physical printer finished the part.
  **Batch Export / Print** (the print list on the Manage screen): two buttons
  whose labels follow the ticks - *Print whole space* / *Export whole space*
  with nothing ticked, *Print bin* / *Export bin* for one, *Print N bins* /
  *Export N bins* for several (Story 2851).
  Both use one preparation step: it re-reads the Inventory, reuses a row's
  current files, and generates only rows without current files (each becomes
  Saved as soon as it is made). Export stops there; Print then opens the files in
  Bambu Studio. Applicable Space connectors are included automatically.
  If a bin fails part-way, the
  bins already saved stay Saved, Bambu Studio is not opened, and the unfinished
  rows stay selected to retry.
  **Editing a saved bin.** Changing the design of a bin that already has saved
  files makes those files stale (the row shows *In Design*). When focus leaves
  that bin, Wavefinity asks whether to update its saved files; the dialog can
  remember automatic updates for that Space through
  `layout.settings.auto_update_changed_files` (default off).
  Superseded files are removed only when they were tracked to that row and no
  other row uses them. **Mark Printed** / **Mark Not Printed** on a row change the
  status for external or failed prints. The Inventory **Delete** action removes
  all selected ordinary bins in one transaction (placements and design sources go with them);
  dragging a bin off the Space only unplaces it. Under the table, a `## Drawer
  layout` JSON block holds the drawers and where each bin sits. Rows stay
  hand-editable; keep the IDs. An older seven-column log is upgraded the first
  time it is saved, and a one-off `.bak` copy is left beside it. Every save
  re-reads the file and merges, so a bin saved while the layout is open is never
  lost.
- **Space workspace.** The top-level **Space | Design** buttons choose the work
  area. *Space* shows layout tools and Inventory; *Design* shows the current bin
  with its 3D and 2D views. Choosing Space without an active Space opens the
  existing Open/New Space flow. Opening an existing Space with a bin (or a legacy hand-added row) in Inventory
  starts in *Space*. An empty or spacer-only Space starts in *Design / 3D*. The
  workspace stays open until the folder stops being that Space. The name, type and
  size are shown read-only; **Edit Space** opens the same fields in place with
  **Save Changes** and **Cancel** (never the New Space buttons).
- **Drawers.** A drawer's inside width, depth and **max height** come from its
  Space. The layout has one fixed rule set, not choices: a **7 mm** whole-unit
  grid, width running left to right, the grid against the front-left corner, and the
  catalog's hard-wall allowance (none against a Storage Box's own mating
  boundary) with spacers taking up the rest. Older saves are normalised on
  load: a 4 mm layout rounds each bin to whole units (the report flags any
  overlap that makes), and any other axis, corner or clearance goes back to
  these rules. Only a legacy Space that still holds several drawers keeps a
  name and Delete under *Drawer details*; the drawers share one inventory, and
  a bin placed in one drawer is not available to another.
- **Bins never turn a quarter turn on their own.** Left walls mate with right,
  and front with back; a bin turned 90 degrees meets its neighbours crest to
  crest, so there is no sideways option.
- **Stacking.** A bin printed stackable (a lid, or a direct locating skirt) shows
  a ⇅ on its swatch and its style under its name. Drop it on a bin of the same
  size that stacks the same way and it seats on top, sides aligned. Anything
  else is refused with the reason: a different size, a different style, a bin
  not printed to stack, or a stack taller than the drawer's max height. Lid and
  direct interfaces are intentionally same-mode only. The Height field is the
  module contribution: a 50 mm lid bin adds exactly 50 mm. Its detached physical
  envelope also includes the exposed interlock (1 mm on a lid), which the drawer
  clearance check includes. A direct bin measures exactly its Height; its 2 mm
  skirt sits inside that, so each bin added adds the Height less 2 mm. Dragging a bin in a
  stack takes it and everything above it; dragging the bottom bin moves the
  whole stack.
- **Inventory is the primary Space control.** Each ordinary row shows a
  general selection tick, a number badge, name, dimensions, physical placement
  (**Placed** or **Unplaced**) and file lifecycle (**In Design**, **Saved** or
  **Printed**). Click a row to select it; use its explicit **Edit** button to
  open that bin in Design. Row actions include **Delete**, **Duplicate**, **Print**,
  and **Mark Printed** (or **Mark Not Printed**). Filter starts on All for each
  Space in a fresh session and stays selected while switching work areas;
  Sort remains a saved preference. Selection survives filtering and sorting; one
  Inventory **Delete** button removes selected ordinary bins. Spacers remain
  visible below ordinary bins. *Clear selection* is disabled while nothing is ticked.
- **Placing.** Drag a bin from the tree's **Not placed** group onto the
  Space. Drag placed bins to move them: they snap to the 7 mm grid and refuse
  overlaps and the Space edge. Drag one back onto the tree, or select it and press
  **Delete**, to unplace it - it returns to **Not placed** and stays in Inventory.
  Keys: the arrows move one unit, **Delete** unplaces, **F** fits the view, **Esc**
  deselects. An ordinary bin is placed at most once; a legacy layout that holds
  several copies of one row keeps one deterministically when it loads.
- **Space & spacers.** The drawer view itself shows the one or two biggest
  open rectangles a bin could still go into, each as both a millimetre size
  and a Wavefinity-unit size; the left panel covers connector and layout problems
  instead of restating those as a summary.
- **Spacers** (Drawer, Storage Box and Storage Drawers Spaces; never Surface or
  Pegboard). A spacer is a filler part, not a bin: it braces the placed bins
  against the Left, Back and Right walls so nothing slides. There is no
  front-wall spacer, because bins are pulled toward you when the drawer opens.
  The Spacers section on the Manage screen holds everything:
  - *Spacer type*: **Flexible** (default) prints a zigzag 2 mm oversized so it
    wedges in (PLA or PETG); **Rigid** is a solid block with 0.4 mm of play. A gap
    too small for the zigzag (under 9 mm, or under 6 mm of bin edge to push on)
    quietly gets a rigid spacer and says why.
  - *Height*: Auto (default) is the full height of the tallest bin placed in
    that drawer, kept between 6 mm and the drawer height; untick Auto to type one.
  - *Spacer locations*: Left, Back and Right tick boxes, all on by default.
  - **Refresh Spacers** is the one action. It removes the drawer's placed
    spacers and makes new ones for the current bins: for each stretch of bin
    edge facing a ticked wall, about one 28 mm-wide spacer per 100 mm of edge,
    reaching from the bins to the wall at the real leftover millimetres. Gaps
    over 200 mm are skipped with a note; at most 8 spacers are made per Refresh.
    Each spacer is its own Inventory row (Kind *spacer*) with its 3MF in the
    Space folder, and shows sand-coloured in the layout with a *Spacer* label.
    Refresh is disabled until a bin is placed.
  - **Print Spacers…** lists the placed spacers grouped by size and type and
    sends the chosen ones (and quantities) to Bambu Studio. **Print whole
    space** also sends the placed spacers with the bins and connectors.
  - Spacers are not in the selection tree and cannot be dragged; a spacer row in
    the Manage list has only **Delete**. Spacers do not take connectors.
  - A spacer that later collides with a moved bin or sticks out of a resized
    drawer is shown as a problem; Refresh Spacers remakes it.
  - *(planned)* New spacers start as not printed, and Print whole space sends a
    spacer only until it is printed (Story 2863); Print whole space covers every
    drawer of a Storage Drawers Space (Story 2864); the section always says when
    gaps could use spacers or spacers no longer fit, and print leaves out
    spacers that no longer fit (Story 2865); Refresh and a spacer's Delete act
    with no pop-up, and the spacer row shows only size, type and printed state
    (Story 2866).
- **Surface Fill** (Surface only) turns free Surface cells into ordinary editable
  bins. It first settles the Designer's autosave, then works from the authoritative
  Inventory and layout.
- **Saving.** Space layout autosave is always on - there is no off state and no
  manual Save button. Layout changes and each bin's design source save as you
  work; names and status save straight away, because they are the inventory.
  The layout is recalled automatically every time you open the tab. **Save
  location** shows the current folder and opens the folder picker, the same
  as the main editor's.
