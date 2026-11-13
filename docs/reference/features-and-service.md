# Wavefinity features, data and browser service — detailed reference

For product feature options, data ownership and the browser service. See the [overview](../../README.md) for the document map.

## Parts and variables

Wavefinity separates reusable **bin/shell intent** from **content placed inside
the bin**. A future setting belongs in the reusable bin category when it changes
the shell itself: mounting holes, exterior mounting, wall/base construction,
lid/stacking, shell scoop, Inside Grip, or bin-level label construction.
A future ordinary `layout.feature` is interior content and does not belong.

| Variable / feature | Space default? |
|---|---|
| Bin X/Y footprint | Yes |
| Bin Z / height | Yes |
| Wall thickness / Standard Walls | Yes |
| Base thickness / Standard Base | Yes |
| Bin/container type | Yes |
| Stacking | Yes |
| Lid configuration | Yes |
| Inside Grip / shell options | Yes |
| Scoop on/off (presence of a shell modification) | **No** |
| Storage Box container configuration | Yes |
| Label enabled/type/location/style | Yes |
| Actual label text | **No — blank** |
| Edge Mount side/projection/thickness/screw settings | Yes |
| Edge Mount label text | **No — blank** |
| Part/Bin name | **No — blank** |
| Interior print/layout mode | Yes |
| Interior part instance / X-Y placement | **No — never auto-copied** |
| Safe last-used interior-part editor settings by kind | **Yes** |
| Actual interior text / division-label wording | **No — blank** |
| Photo/image/contour source geometry | **No** |
| Camera/view/editor/session state | No |
| Connector-generation/session UI state | No |

For Stacking, Lid, Inside Grip, Edge Mount and Side Openings, "Yes" means the
*settings* are remembered per kind and seed the option when it is explicitly
added; the option merely being present on the last bin never carries into New
Bin.

**A typed Space remembers preferences; each bin remembers its exact design.**
These are two separate stores and both always apply. A bin's full design
(names, text, every part and option) is saved exactly in `design_specs[row_id]`
on every valid autosave and is never sanitized. Separately, every successful
exact bin save also updates the Space's remembered *preferences*, with no
dependence on Generate, Print or file creation. There is no "Keep bin
defaults" toggle; `keep_bin_defaults: false` in older metadata is tolerated
and ignored.

The rule is exclusion-based: every user-configurable value is remembered
unless it is **identity/text** (part name, rim/Edge Mount/Lid label text, lid
division labels, Text-part wording, any `*_text` field), **presence** (which
parts, modifiers or the Scoop the previous bin happened to contain) or
**placement/session/trace state** (feature X/Y, Inventory placement, photos,
contours). A part's *size* is a preference even though its position is not.
Where a value is Auto, the Auto mode is remembered, not the numbers it
derived. A future setting therefore participates automatically.

New Bin starts from the catalog starter plus the remembered bin-level values
(X/Y/Z, wall, base, Fused/Removable, Surface base choices, pegboard cleat
counts...), then the active Space's own limits clamp them (a remembered size
that no longer fits is reduced, never left invalid). It never copies the last
bin's parts or modifiers. Explicitly adding a part or modifier (Bore, Edge
Mount, Lid & Stacking, Inside Grip, Side Openings...) seeds it from the
remembered settings for that kind, with text blank and a fresh placement;
reopening an existing part or modifier always shows that bin's own exact
values. Deleting a part or modifier from one bin does not erase the remembered
settings for its kind. A kind's remembered entry changes only when a save
actually changed that kind's settings.

Preferences live in the Space's `.wavefinity.json` metadata: `bin_defaults`
(the sanitized bin snapshot, with no parts, modifiers or text) and
`part_defaults` (one entry per part kind; per modifier kind as
`{kind, settings}`). Writes are serialized, name the Space they were queued
for (`expectedSpaceId` hosted, `space_id` on `/api/space/defaults` locally) and
preserve all unrelated metadata, so a late write can never land in a Space the
user has left. Older `bin_defaults` / `part_defaults` shapes that contain
text, features or modifier presence are sanitized when read and are replaced
by the next preference write; they can never add a part or copy text. If the
preference write fails after the bin saved, the bin is not rolled back and a
warning says so.

### Using the browser editor

The browser editor is a two-step flow: **1. pick a shape** from the
interior-part palette, reading its one-line description, which both creates it
and adds it straight into the **Added to this bin** list below; **2. set
parameters** in the editor that opens for it, then click **Done** to confirm
(or **Delete** to remove it instead). Added parts can be selected in the
**Added to this bin** list or on the 2D layout, then moved or resized there,
or edited with exact numeric size fields, by reopening the same editor. Normal
layouts snap to **1 mm**. Overlaps and out-of-bounds features are refused at
export.

A **divider** is a special case with no manually-sized footprint at all: it
defaults to full-span (wall to wall) and centres itself, so there is nothing
for Center X/Y or a footprint Width/Depth to describe, and no separate
"fit it to the bin" action either - it already is. Its whole field set is
just **Width mm** (the wall's own thickness), **Height mm** (blank by
default, reading "height of box" until you type one), **Angle °**,
**Quantity**, **Spacing mm** (blank - "fills evenly" - until overridden with
an exact gap), **Leaning shape**, and **Walls**. Its current grid controls,
**X count** and **Y count**, place that many walls left-to-right and
front-to-back respectively (0 means none on that axis) to build a full rows ×
columns grid of compartments; entering either one retires the legacy
single-axis Quantity, and the grid resets any custom compartment merges when
its wall counts change. Every other kind keeps manual sizing
and the ordinary per-kind **Auto** button next to Quantity, since their
quantity means repeated elements inside one footprint, not sections of the
bin.

### Automatic sizing: grow when needed, respect what the user chose

Wavefinity's automatic sizing is deliberately one-way during normal editing:
it may **grow** an interior part or the bin to keep the design valid, but it
does not silently shrink a size the user entered, dragged, or reopened from a
saved design. A larger-than-required part or bin is therefore treated as an
intentional choice, not an error to correct.

New Bores, Cradles, Posts, and Slot Racks begin with a contents-driven
footprint. Increasing a hole grid, tool size, quantity, spacing, or lean grows
that part automatically. If the part no longer fits, the bin's width and/or
length grows on the 7 mm grid. Shrinking a bin below any existing Pocket,
Steps, rack, or holder grows the bin back around the part instead of trimming
the part. When growth creates a collision, the part being edited stays put and
the other parts move outward only as much as needed.

Pocket, Slot Rack, and Divider each carry a **Walls** option: **Straight**
(the default) or **Wavy**, the same globally phased mating wave used
elsewhere (Bore Wall Only, Base Trim). Choosing Wavy changes how much shell
each part needs - Pocket's outward reach grows to clear the wave while its
entered inside Width/Length stay exactly what was typed; Slot Rack's required
bank footprint grows to clear it; Divider's wall path and thickness
compensation follow it while its logical compartments stay the same. The
browser and the backend read the same catalog wave amplitude and depth
factor, so this reach can never drift out of sync with the printed geometry.

Typing a part Width/Length or resizing it in 2D makes that size the new minimum;
later automatic changes can grow it but cannot pull it smaller. Reopening any
placed or saved part protects its existing footprint the same way. Bin
Width and Length entered by the user are also floors. Slot Rack Quantity grows
its Base automatically; increasing Quantity is also how the user fills more of
the bin. The explicit **Fit to pegs** action remains for Post Racks, while
**Fill the bin** remains for free-size parts. Divider and Scoop
footprints continue to follow the bin because full-span behavior is their
purpose.

### Insert types

The browser UI offers two: **Fused**, where holders print as one solid part
with the bin — strongest, uses the most floor area, but the parts are
permanent — and **Removable**, where holders print separately on a thin
0.6 mm base plate that drops into the bin, so the interior can be swapped
while the bin stays put.

A third mode, **7 mm cartridge**, exists at the engine and CLI level
(`--mode cartridge`): a removable insert constrained to whole 7 mm cells, so
it is repeatable and interchangeable between matching bins at the cost of
some usable edge area (on the 128 x 88 comparison bin that is 120 x 80 mm,
9.8% less floor). The browser UI does not expose it as a choice — reusable
coordinate footprints across bins are a scripting concern, and picking it by
mistake in the editor just produced a confusing revert once an already-placed
interior part did not land on a 7 mm cell.

Tall holders may use the middle of the bin, but anything entering the 2 mm strip
beside a wall is capped below the connector arms. The editor's default divider
height follows that limit; an explicit unsafe height is refused at generation.

**Fused** is the default and gives the most usable floor.

Lettering is a **Text** part with one Text Type (On base or At rim, Inlaid or
Raised) — see [Text — centered lettering on the base or at a rim wall](geometry-and-options.md#text--centered-lettering-on-the-base-or-at-a-rim-wall).
A bin carries one On-base Text and up to one At-rim Text per rim side. In
removable modes On-base Text is inlaid into the insert plate rather than hidden
under it, while At-rim Text stays on the bin shell: 5 mm letters when they fit,
otherwise automatically smaller, on a 7 mm-deep ledge just below the rim whose
underside rises at 45 degrees and prints without supports.

The optional **curved scoop** spans the usable width at the front of the bin and
rises 60% up the usable wall height, so a part sweeps forward and lifts out
over the low front lip — the opposite wall from the rim-label ledge. In
removable modes it is part of the insert; in fused mode it is part of the box.
The 2D editor shades the space reserved by a scoop. Fused-layout clearance
against base Text uses the actual letter shapes; rim Text reserves no floor.

What a scoop reserves is not its whole run. The curve meets the floor
tangentially, so its innermost millimetres are only microns proud of it — on a
40 mm bin the ramp stands 0.03 mm off the floor one millimetre in from where it
lands. Reserving that lip called a divider across the middle of the bin
"invalid" when it was in fact sitting flat, so the keep-out stops where
the curve has risen `SCOOP_FLOOR_TOLERANCE` (0.4 mm, about one layer) instead.
`scoop_floor_zone` is still the true footprint, used where the real extent
matters; `scoop_keep_out` is the smaller strip an interior part has to avoid.

Bin wall, floor, and mating geometry use the tested printable defaults. The
editor exposes only the dimensions and interior-part settings that affect the part.

Save and Print are separate pairs of buttons, not a sampler-style generator
bank. **Save Bin** writes just the bin (including its current insert layout);
**Save Bin + Connectors** adds its automatic connector bundle (a Side
connector, plus 3-Way and 4-Way corners when the bin is eligible — never for a
B4B, a lidded bin, or a Base Trim). Locally, **Print without Connectors** and
**Print with Connectors** do the same pair of things but hand the files
straight to Bambu Studio instead of only saving them; in hosted Wavefinity,
where there is no local slicer, those same two buttons read **Save without
Connectors** / **Save with Connectors** and behave exactly like the Save
pair. There is no status bar — a button reports on itself, briefly reading
*Saved* (or *Sending to Bambu Studio…*) while it works, so nothing takes up a
line saying "Ready" for the 99% of the time it has nothing to report. A
failure still raises a dialog, because it needs acting on; a Print that saved
its files but could not finish (connectors failed, or the slicer did not
open) says so truthfully instead of claiming nothing happened.

**Bambu handoff stays settings-sovereign (Fix 058).** Wavefinity hands Bambu
Studio profile-free model 3MFs only — never a manufactured Bambu *project*.
Each requested physical occurrence (repeated copies are real, separate physical
prints, never deduplicated) is copied into its own file in a persistent
per-launch handoff folder (`bambu_handoff.stage_bambu_inputs`, under
`%TEMP%/Wavefinity/Bambu Handoffs/<uuid>/`, pruned opportunistically after at
least 24 hours and never while still the newest) and opened directly with
`Popen([BambuStudio.exe, staged1, staged2, ...])` — no `--export-3mf`,
`--arrange`, `--slice`, `--load-settings` or `--load-filaments`. Wavefinity
preserves only model geometry, object/part names, and a deliberate per-part
extruder-slot assignment (`Metadata/model_settings.config`); Bambu Studio and
the user remain entirely authoritative for the printer, process, filament,
plate and AMS settings. A source 3MF carrying an embedded
`project_settings.config`/`print_profile.config`/`print_setting_*`/
`process_settings_*.config`/`filament_settings_*.config`/
`machine_settings_*.config` member is refused before handoff with a clear
error, never silently stripped. After copying a safe source, if it carries
one or more non-default (not slot 1) extruder-slot assignments,
`stage_bambu_inputs` compares the staged copy's assignment count against the
source's before Bambu is ever launched; a mismatch fails the handoff and
removes the incomplete handoff directory rather than launching Bambu or
"fixing" either file. For a multi-file Bambu batch, if direct GUI
import does not already arrange the plate, use Bambu Studio's own **Arrange**
command (keyboard **A** where supported) — Wavefinity does not fall back to
`--arrange --export-3mf` and has no plate-packing engine of its own. Custom
slicers (OrcaSlicer, etc.) keep opening the requested files directly, as
before.

### The browser service

`wavefinity_web.py` is a dependency-free `http.server` wrapper, nothing more:

```text
Browser UI (HTML/CSS/JavaScript)
              |
       same-origin JSON
              |
Local loopback service (Python standard library)
              |
Existing design, validation, mesh and 3MF export modules
```

It is a stateless translation layer — every request carries the complete
design, every response uses the same versioned `.wavefinity.json` schema the
CLI and saved files already use. Nothing about the geometry, validation or
export changed to add it; the browser is a new consumer of the existing
engine, not a reimplementation of it. It binds to `127.0.0.1:8765` by
default and is never exposed to the network.

| Route | Purpose |
|---|---|
| `GET /api/health` | Identify an existing Wavefinity server. |
| `GET /api/catalog` | Registered interior parts, modes and initial values. |
| `POST /api/preview` | Validate a design and return camera-independent geometry, plus an optional live-highlighted draft. |
| `POST /api/design/validate` | Validate and normalize a saved design. |
| `POST /api/feature/default` | Create an engine-derived interior-part draft. |
| `POST /api/feature/draft` | Build one interior part's own mesh faces to validate it and resolve its blank options. |
| `POST /api/feature/apply` | Snap, validate, add or update an interior part. |
| `POST /api/feature/delete` | Remove an interior part. |
| `POST /api/layout/mode` | Convert a layout between print modes. |
| `POST /api/generate` | Generate the organizer parts. |
| `POST /api/connector` | Generate a connector. |
| `POST /api/sampler` | Generate the fit sampler. |
| `POST /api/preferences` | Persist sticky per-machine settings (currently the output folder) to `wavefinity_prefs.json` in the user profile. |
| `POST /api/space/startup` | Local startup: resolve the active Space by its ID (recovering a renamed folder in the same parent) and open it. |
| `POST /api/folder/use` | Select or restore a local design folder, its inventory setting and optional Space metadata. |
| `POST /api/folder/inventory` | Explicitly turn a local folder's inventory logging on or off. |
| `POST /api/space/defaults` | Update a Space's Keep Defaults flag and/or sanitized bin snapshot. |
| `POST /api/drawer/load`, `/api/drawer/save` | Read and update inventory/layout from a local path or browser-supplied text. |
| `POST /api/space/create-text` | Let hosted browsers initialize Space inventory without giving the server a client path. |

**Security boundary**, since the service writes files: loopback binding
only; POST routes require `application/json` and reject a foreign `Origin`;
static file paths resolve beneath `web/`, blocking traversal; every response
carries `nosniff` and same-origin resource policy, the static page also gets
`no-referrer` and a same-origin-only content-security-policy; request bodies
are capped at 25 MB; no cookies, accounts, credentials or telemetry. The
output-folder field intentionally lets the local user pick any writable
path — that is application function, not a sandbox escape. Print/export geometry
builds run behind a process-wide lock (`GEOMETRY_LOCK`, build stages only;
see the 2026-11-11 note below); previews use per-view locks. Hosted exports use isolated
temporary folders and never expose the server filesystem; the browser owns its
chosen save folder and supplies inventory text to the same Python inventory
engine used locally.

**Save folders, inventory and Spaces are three separate ideas.** Every chosen
folder gets an additive `.wavefinity.json` marker holding its folder mode,
inventory choice, optional Space identity, and per-Space Keep Defaults state.
`inventory` (default `true`) controls whether generated bins/Storage Boxes are logged;
`folder_mode` (`"design"` or `"space"`) says whether the folder also represents
one typed Drawer, Storage Box, Surface, or Pegboard Space. `folder_mode: "space"` always
implies `inventory: true` - a Space's layout depends on the inventory it
places. A normal `"design"` folder can have inventory on (the default for a
new folder) or explicitly off (`/api/folder/inventory`, mirrored by the
frontend's *Keep inventory for this folder* checkbox). Legacy inventory,
`.wavefinity-space.json`, `kind: "none"`, and the historical
`no_inventory_folders` preference remain migration inputs - read once to
decide a folder's first `inventory` value, then superseded by the explicit
field - and are not deleted.

**Development policy:** Wavefinity is user-tested. Coders inspect their logic and code; they do not run or author automated tests, perform manual UI testing, or create manual test plans for users. A very dense design (many cradle/bore parts at once) serializes a large triangle payload to the browser, making initial load heavier. **Save design** uses the browser's download prompt. Photo Nest's automatic finger-access search and 2D indicators are application behaviors.

---
