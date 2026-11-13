# Wavefinity CLI, code layout and service operations — detailed reference

Only consult the relevant CLI, code-layout or service section for the current task.

## Command line

```powershell
python organizer_app.py box --x 40 --y 32 --z 55 --output box_40x32x55.3mf
python organizer_app.py box --x 48 --y 48 --z 40 --label BOLTS --output "Box 48 x 48 x 40 BOLTS.3mf"
python organizer_app.py box --x 48 --y 48 --z 40 --label M3 --label-position top --scoop --output custom.3mf
python organizer_app.py box --x 32 --y 32 --z 40 --flat-inside 1.0 --output flat.3mf
python organizer_app.py side --box-x 40 --box-y 32 --box-z 55 --along y --output side_y.3mf
python organizer_app.py kit --x 40 --y 32 --z 55 --output-dir generated_40x32
python organizer_app.py sampler --boxes 2x6,4x6,6x6 --output WAVY_SAMPLE_SET.3mf
python organizer_app.py organizer --layout drivers.wavefinity.json --output-dir generated
python organizer_app.py organizer --layout drivers.wavefinity.json --mode cartridge --label HEX --part-name "Driver rack" --output-dir generated
```

X and Y must be multiples of 7 mm (minimum 7); Z and wall are free. `--boxes`
takes units (`2x6`), or millimetres with an explicit suffix (`14x42mm`).

Generated box files are named for their size, plus the part name if there is
one: `Box 16 x 48 x 40.3mf` or `Box 16 x 48 x 40 Driver rack.3mf`. Lettering
does not appear in a filename — a bin may carry several labels. Default connectors
save as `Connector - Same height.3mf`, or reflect any customized variables (e.g.
`Connector - 40mm to 20mm Tol 0.05mm.3mf`).

On the `organizer` command, `--label` is sugar for a **text interior part that
places itself**, and seeds a blank `--part-name` from it; `--label-position top`
puts it on the rim ledge instead. On the plain `box` command (which has no
layout) `--label` remains a single centred floor label.

The `organizer` command reads either a complete saved UI design or a bare layout
object. A complete design supplies its box, rim label, scoop choice and part
name; explicit CLI values override any of them. `--mode` overrides the saved
fused/separate/cartridge mode.
Fused export writes one box file. Removable modes write a plain box and a
separate `Insert ...3mf` or `Cartridge ...3mf`. A lettered file is a strict 3MF
**assembly** — the body and every piece of lettering as named parts of one
object, one build item — with a `model_settings.config` sidecar opening the
lettering on filament 2. Both `.3mf` and `.stl` continue to work for legacy
individual-part commands.

## Generate the sample print file

Run the sampler command above to create `WAVY_SAMPLE_SET.3mf` with eight
separately selectable objects:

- **2 x 6 (14 x 42 mm)**, **4 x 6 (28 x 42 mm)** and **6 x 6 (42 x 42 mm)** boxes
- **Five identical connectors** at the locked 0.02 mm tolerance

Print the boxes open side up and the connectors cap side down; no supports either
way. The three sizes are deliberately different so you can check that mixed sizes
really do interlock and take a clip at every seam.

## Code layout

The old Tkinter desktop UI is gone. The browser, CLI, and exporters share this
layered implementation:

| File | Role | Entry point? |
|---|---|---|
| `organizer_geometry/` | Feature-neutral booleans, extrusion, sweep, ring alignment and loft helpers. | No. |
| `organizer_engine/` | Wavy boxes, connectors, labels, mesh validation, product rules and 3MF/STL export. It re-exports established geometry helper names for compatibility. | No. |
| `organizer_base_trim/` | Isolated Base Trim validation, global-phase ring geometry, bed-aware splitting, section joints and export. | No. |
| `organizer_inserts/` | Item/layout model, authoritative feature registry, per-feature builders, Divider compartments, and fused/removable assembly. | No. |
| `organizer_app.py` | CLI, exporters and design persistence. Legacy palette constants are generated from the feature registry. | Yes, for CLI subcommands. |
| `wavefinity_web.py` | The local HTTP service — see [The browser service](features-and-service.md#the-browser-service). | Yes, the default UI launch target. |
| `organizer_inventory/` | The drawer inventory file (`Wavefinity bins.md`): parsing, legacy upgrade, merge-saves and bin logging. | No. |
| `organizer_drawer/` | Drawer layout: grid fit, drawer report, spacer planning/export and its `/api/drawer/*` routes. | No. |
| `organizer_features/` | Edge Mount, Side Openings, Lid & Stacking, and Pegboard standards/geometry. | No. |
| `organizer_storage/` | Storage location handling and Storage Drawers schema, geometry, output planning and recovery. | No. |
| `organizer_outputs/` | Printer build-volume/profile ownership, slicer handoff and structural Space output helpers. | No. |
| `web/storage-drawers.js`, `web/storage-drawers-form.js`, `web/storage-drawers-workspace.js` | Cabinet rules from the published catalog, the Create/Edit form and live summary (usable height = stored height + Drawer fit, computed locally), and the drawer navigator and recovery (Save/Print Cabinet live in the left controls); Add/Delete Drawer live only in Design. `web/storage-drawers-guide.html` is the one app-level assembly and print guide. | No. |
| `web/storage-box-form.js`, `web/structural-design.js` | Structural Space objects in Design (Fix 103): the Storage Box case editor, and the controller that mounts the cabinet/case editor as the Design target, keeps one debounced draft preview in `state.structuralPreview`, draws the Interior Width/Depth/Height 3D handles, shows the Space canvas view-only as the 2D view, and owns Save Changes plus the one structural dirty/leave check. | No. |
| `web/workspace.js`, `web/workspace.css` | The one-focus interface (Story 2674, replacing the 2671 split view): exactly one full-width task on screen - Spaces picker, Space Overview, Space Settings, container editor, Bin editor, Print Space, or My Bins - under one slim header (Spaces, place name, New, and the single `Temp only Roll back` button). Overview selection, scroll and zoom are restored on every Back. The sidebar forms and canvases are the existing ones; it only drives the existing Space/Design machinery and adds no file format. The header button (`Temp only Roll back` in the new UI, `Back to the new UI` in Classic; remembered in this browser as `wavefinity-interface`) switches to the classic Bins and Spaces screens, which show nothing of it. | No. |
| `web/printer-profile.js` | The browser's printer build-volume owner and the Printer Settings control. | No. |
| `web/spaces.js` | Typed Space setup and opening, folder and Space activation, resume and startup handoff, and Space setup lifecycle. | No. |
| `web/browser-files.js` | Hosted-browser writable-folder permission and handle persistence, plus browser-owned file operations; Python receives no fake client path. | No. |
| `web/preview3d-webgl.js` | Shared depth-buffered WebGL renderer for solid 3D preview geometry; `app.js` owns 2D overlay annotations. | No. |
| Historical `tests/` and `run_tests.py` | Legacy automated test artifacts: coders must not run, modify, repair or expand them under the current owner policy. | Not part of coder workflow. |

`web/index.html`, `web/styles.css`, `web/feature-icons.js` and `web/app.js` are
plain dependency-free frontend files with no build step. Icon artwork lives in
`feature-icons.js`; the feature registry supplies stable icon identifiers.
`app.js` holds the stateful editor, preview coordination, and typed-Space
ordinary-bin autosave and status handoffs. In the current legacy runtime printable geometry comes from the Python service; the planned browser-only migration retains canonical Python geometry through Pyodide/WASM and removes that server dependency. Drawer layout mode lives in `web/drawer-model.js`
(data, saving), `web/drawer-view.js` (the canvas) and
`web/drawer-panel.js` (its sidebar), styled by `web/drawer.css`. These files
share helpers and Space identity with `app.js`. The page's content-security
policy refuses inline `style=""` attributes, so the drawer files set colours
through the DOM.

`TESTING.md` was the historical test log, now moved to the untracked `archive/`
folder. We no longer maintain or keep this testing log updated.

Dependencies run one way: shared geometry sits at the bottom; the engine and
insert package consume it; the app consumes both; the web
service consumes the app. Nothing imports back upward.

### State, persistence, and async ownership

The Designer has two layers of state. `state.design` is the canonical committed
design; `state.draft` and queued visible edits may be newer. Save, Generate,
Print/export, Load/Open/New, and design-replacement paths must use the existing
Designer freshness/mutation owner before persisting or replacing state. Use
`commitVisibleDraft()` and/or `visibleDesignSnapshot()` where the established
path requires them; never clone `state.design` as a substitute for resolving
pending visible edits.

Multi-await Designer replacement or persistence actions use
`beginDesignMutation()` and `finishDesignMutation()`, backed by
`state.designMutationBusy`. This is the single mutation owner: do not invent a
second busy or ownership system. Space/folder switches are blocked or
serialized while it is held.

Space async work uses `DL.spaceContext()`,
`DL.spaceContextCurrent()`/`DL.requireSpaceContext()`, context-aware
`DL.busyWith()`, `DL.inventoryCall()`, and `DL.editBins()`. Capture one context
before the first relevant `await` and carry it through every result that can
mutate live Space, Inventory, or layout state. A stale completion must never
mutate the newly active Space. External file or slicer effects may already have
happened, so report partial success truthfully when required. Serialized Space
saves use `DL.savePromise`/`DL.saveAgain` inside `DL.save()`; do not add polling
or parallel save ownership.

For spec-backed Inventory rows, `layout.design_specs[row_id]` is the canonical
editable design source. Qty, placement, layout, and source changes that form
one logical action belong in one authoritative transaction. Local filesystem
and hosted browser-text implementations must preserve that same logical
atomicity through `organizer_inventory.design_specs()`,
`save_design_source()`/`save_design_source_text()`, and `_merge_inventory()`
under `INVENTORY_LOCK`.

In a typed Space, each ordinary bin has one canonical Inventory row and one
`layout.design_specs[row_id]` source through its `in_design`, `saved`, and
`printed` statuses. `app.js` debounces Designer autosave and serializes writes
through `spaceAutosaveChain`; it flushes visible edits before replacement,
Save, Print, or a folder/Space switch. `DL.spaceContext()` guards those writes
and their completions against a changed Space. Save and Print update that same
row. An ordinary row is one placement identity (at most one placement, copy 0);
its unplaced state is derived from Inventory for the staging rail and is never
persisted. `Qty` is only a 0/1 compatibility bridge under Status.
Standalone Design keeps its separate `.wavefinity.json` file workflow and is
not owned by typed-Space autosave.

`Layout` metadata is additive. Current examples include `object_height_mm`,
`surface_base_mode`, and `surface_lightweight_base`. When transforming an
existing ordinary layout, use `dataclasses.replace(layout, ...)` or another
full-preservation path so every metadata field survives. Direct `Layout(...)`
construction is for a genuinely fresh, default, transient, or B4B-specific
layout, not a shortcut for modifying an existing design. Future additive fields
must not be lost because every transform was not found and rewritten.

When adding a new Space/Inventory async write, use the existing DL context and
transaction owner. When adding a persistence or replacement action, use the
existing Designer commit/mutation owner. When transforming a Layout, preserve
all additive metadata.

Two things worth knowing before tidying anything up:

- The `*Tests` classes look unreferenced, because
  nothing calls them by name - `unittest` discovers them. They are not dead.
- Registered holder builders look unreferenced because the registry calls them.
  Check the tests before deleting apparently orphaned definitions.

### Adding or changing an interior feature

1. Keep its builder, defaults, automatic-setting declarations and
   `@feature(...)` metadata in its `organizer_inserts/_*.py` module.
2. Put every option's type in an `OptionDefinition`; do not add another parser
   list in the browser or app.
3. Declare automatic source/target/effect/owner/reason relationships with
   `register_setting_interactions()` and keep one owner for each automatic result.
4. Reuse `organizer_geometry.py` operations and existing capability modules;
   do not copy profile or boolean math into a feature.
5. Give new artwork an icon identifier in feature metadata and place the SVG
   fragment in `web/feature-icons.js`.

`Make_Wave_Zip.bat` creates `wave.zip` with repository-relative entry names, so
package folders such as `organizer_inserts/` remain intact after extraction.

Non-Python files:

| File | What |
|---|---|
| `Launch_Organizer_UI.bat` | normal launcher; silent unless something is wrong |
| `Launch_Wavefinity_Clean.bat` | clean launcher; wipes saved data first |
| `launch_wavefinity.ps1` | the launch logic both `.bat` files call |
| `generated/WAVY_SAMPLE_SET.3mf` | regenerable local sample print plate; intentionally gitignored |

## Working on this

Working rules for developing this project — committing and pushing, more than one person in the repo, and the no-testing policy — live in [AGENTS.md](../../AGENTS.md). The notes below stay here because they describe how the local service itself behaves.

**Relaunching replaces whatever is already running on the port.** If a
relaunch finds the port taken, it first confirms a genuine Wavefinity
service - not some unrelated program - answers there (a real `/api/health`
response, not just something listening), then asks the operating system
which process currently owns that port (`netstat` on Windows, `lsof` on
macOS/Linux). It does not trust `wavefinity.pid` for this: a stale PID can
be reused by an unrelated program. It then kills that verified port owner
and rebinds. Only if a genuine service answers but no current port owner
can be found, or killing it fails, is it left alone and reported as already running - close
that window by hand and relaunch. A browser tab has no way to tell it is
talking to code from before your last edit, so silently reattaching to an
old process would serve stale code with no visible sign anything was wrong.

**A page reloads only for an incompatible API change.** `/api/health` returns
the random process instance, build, and `API_COMPAT_VERSION`. The browser polls
every 5 seconds. A routine restart or compatible Render deployment silently
adopts the new instance. Only a changed API compatibility version shows the
reload banner; increase it deliberately when an older loaded frontend cannot
safely use the new backend.

Render Auto-Deploy may be disabled in the Render dashboard when GitHub pushes
should not immediately change the live site. Manual deployment needs no special
session-pinning system because compatible open pages continue working.

---
