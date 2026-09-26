---
title: Wavefinity
emoji: 🌊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Wavefinity — wavy drawer organizer generator

Parametric Python generator for a 3D-printable modular drawer organizer with
**wavy walls that interlock** and configurable holders inside. The local browser
UI, command-line interface, fit sampler and tests share the same Python box,
insert and export engines.

The basic system has a box and **connectors**. The normal **Side connector** is a
small staple that joins two boxes across their shared seam and supports same or
different bin heights. Holders can be fused into the box, printed as a
removable fitted insert, or printed on an optional 8 mm cartridge footprint.

Connector fit always comes automatically from the active bin's wall thickness;
there is no separate connector wall setting. Two compact top/rim connectors
join bins around one grid corner: the **3-Way Corner** joins three bins (its open
quadrant is chosen by rotating the printed part) and the **4-Way Corner** joins
four. Corner connectors need equal-height, equal-wall bins, do not support
different heights, and need at least 16 mm (2 Wavefinity units) in both X and Y.
Corner Quantity (1–20) prints separate copies on one plate. A Space may mix wall
thicknesses, but a connector never bridges different walls; Wavefinity shows a
non-blocking warning when you change Wall in a Space that already has an
ordinary bin with a different known wall.

Everything below is millimetres. This is the whole documentation for the
project: design, rationale, measured evidence, and the traps.

See [changelog.md](changelog.md) for dated implementation changes.
(The historical test log has been moved to an untracked `archive/` folder; keeping a testing log is no longer needed or maintained.)

---

## UI design elements

The control panel is ordered by **blast radius**: a setting sits above
everything whose meaning it can change.

**The Designer designs a Bin.** The Designer always means an ordinary **Bin**. A **Storage Box** and a **Base Trim** are
*structural outputs of their Space*, never Designer objects and never Inventory
rows: a Storage Box Space saves or prints its own case (settings live on the
Space and are edited in **Edit Space**), and a Surface Space saves or prints its
own Base Trim, both from **Space Actions** in the Space header. Lid & Stacking is
a bin-level option. The selected wall/base values are shown and saved; they are
never silent generation-only overrides.

**Lid & Stacking** offers three ordinary-bin configurations: **Stackable Bin**
stacks directly with no lid, **Stackable Lid** closes the bin and keeps a flat
seat for the next bin, and **Handled Lid** adds a knob or pull but does not
stack. Lid labels may be flush or raised; stackable lids use flush labels only.
A Divider can supply one lid label per compartment. Once any compartment lid
label contains text, clear those labels before changing the Divider layout.
Side connectors are unavailable while a lid is fitted.

**Controls follow their meaning, not their mechanism.**

- A **select** is for choosing one of several named states —
  *Lid type*, *Lid snugness*, *Show*, *Orientation*, *Base*, *Walls*, and the Storage Box case's
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
and *Material*, and the ordinary bin's Lid & Stacking editor groups *Configuration*,
*Lid*, *Handle* and *Label* the same way.

**Automatic changes are shown, never silent.** When the app overrides what was
typed — stacking raising the wall and floor — it
says so in plain language in a note under the control that caused it, and it
never writes the new value back into the field the user is typing in.

**The right side has three primary views: *3D*, *2D* and optional *Space*.** 3D and 2D
show the bin being designed (2D is where its interior parts are laid out).
**Space is a mode, not a panel**: it swaps the whole screen: the inventory and
its tools take the sidebar, the Space takes the workspace, and the bin editor's
chrome (placed parts, the design file buttons) steps aside. Undo, Redo and
Ctrl+Z act on the Space while it is showing. A Space has only two mental
objects: **the Space** and **the bins inside it**. The left mode switch reads
**Space | Design**. In Design, the main build fields, **Parts & Options**, and
**Connectors** appear in separate cards.

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

**Bins are placed by hand.** Every ordinary bin is one Inventory row and is placed at most once. A bin that is
not placed waits in the **Unplaced bins** rail beside the Space (a derived view of
Inventory, in Inventory order - never stored coordinates). Drag it into the
Space; drag a placed bin off the Space to unplace it again.

---

## Quick start

Double-click `Launch_Organizer_UI.vbs`. It starts Wavefinity without showing a
command window. On its first run it creates a private `.venv` beside the app,
installs the pinned geometry packages, starts the local Wavefinity service, and
opens the browser interface. Later launches reuse that environment. The service
listens only on `127.0.0.1`; it is not hosted on the internet and the browser
never replaces the Python geometry engine. Use `Launch_Organizer_UI.bat` only
when diagnosing a startup problem, because Windows must show a command window
for a batch file run directly.

Manual setup instead:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install opencv-python-headless==5.0.0.93 lib3mf==2.5.0 lxml==6.1.2 manifold3d==3.5.2 mapbox-earcut==2.0.0 matplotlib==3.11.1 networkx==3.6.1 numpy==2.5.2 shapely==2.1.2 trimesh==5.0.0
.venv\Scripts\python.exe wavefinity_web.py
```

Those ten pins are the whole dependency list. `matplotlib` is not optional — it
supplies the font outlines for floor labels.

## Developer & AI coding guidelines

All instructions for coding agents (OpenAI, Anthropic, Google) and human contributors are centralized here. Do not create tool-specific instructions elsewhere.


### Development handoff workflow

> **CODING LLM — STOP BEFORE SEARCHING THIS REPO FOR A FIX FILE.**
> Help Code plans intentionally do **not** exist in the Wavefinity checkout. For any “implement/read/check fix N” request, first fetch the authoritative plan from the private helper repo `happydadto5/Wavefinity-Help-Code` on its current `main`. For lettered work, e.g. Fix 35A, the path is `fixes/fix-035a.md`. If that private repo cannot be read with your authenticated GitHub access, report **HELPER REPO ACCESS FAILED**. Do not report “fix missing” merely because it is absent from Wavefinity, and do not ask the human to paste a plan that exists in the helper repo.

> **WHERE THE FIXES LIVE:** all fix plans (fix 1, fix 27, etc.) are in the separate private GitHub repo **`happydadto5/Wavefinity-Help-Code`**, in its `fixes/` folder. They are NOT in this repo. When told "implement fix N" or "read fix N", read `fixes/fix-00N.md` from that repo first (use `gh api`, see below). Never say a fix is missing without checking there.

Wavefinity is developed through handoffs between **chat/planning LLMs** and **coding LLMs**. Project-wide rules and architecture live in this `README.md`.

**Help Code task records do not live in this repository.** The only authoritative Help Code store is the private GitHub repository `happydadto5/Wavefinity-Help-Code`.

- `happydadto5/Wavefinity-Help-Code/fixes/Fix Master.md` is the permanent ledger.
- `happydadto5/Wavefinity-Help-Code/fixes/fix-###.md` is the active specification.
- Completed specifications are archived there as `fix-### archive.md`.
- This Wavefinity repository must not contain, restore, clone, or commit a local `/fixes` directory.

If the human says **"read fix4"**, **"read fix 4"**, or equivalent shorthand, read the corresponding zero-padded file directly from the private Help Code repository's current `main`, for example `fixes/fix-004.md`. Do not ask the human to paste the plan when authenticated GitHub access is available.

**Help Code planning quality gate:** Every implementation plan must be comprehensive enough that a junior coding LLM can execute it without rediscovering architecture, product decisions, affected code paths, edge cases, or completion criteria. Name relevant files/functions and give exact implementation direction or code-level structure whenever current code makes that reasonably possible. After drafting, re-read the plan against current code and requirements and revise until a complete pass finds no material issue.

### 1. User communication preferences
- **Operate in "caveman mode"**: keep messages simple, plain, and short.
- **User is NOT a programmer**: avoid code jargon and long technical explanations unless asked.
- **Show progress**: give a clear, general sense of progress in layman's terms.

### 2. Branch, commit & push workflow

Starting with Fix 6, non-trivial Help Code work uses one temporary implementation branch per fix in this Wavefinity repository. The **code branch is local/remote Git work; the fix specification and ledger remain cloud-only in `Wavefinity-Help-Code`.**

#### Mandatory cloud + code remote-state gate

A coding agent must **never trust a local fix file, local Fix Master, chat memory, a copied plan, or an old branch** as the authoritative Help Code state.

Before reading or implementing every Help Code fix:

1. Read this current Wavefinity `README.md` from current `origin/main`.
2. Read the requested fix directly from the private Help Code repository's current `main` using authenticated GitHub access. Example:
   `gh api -H "Accept: application/vnd.github.raw+json" repos/happydadto5/Wavefinity-Help-Code/contents/fixes/fix-012.md`
3. Read cloud Fix Master directly:
   `gh api -H "Accept: application/vnd.github.raw+json" repos/happydadto5/Wavefinity-Help-Code/contents/fixes/Fix%20Master.md`
4. Record the exact Help Code repository `main` commit SHA used:
   `gh api repos/happydadto5/Wavefinity-Help-Code/commits/main --jq .sha`
5. Confirm the requested fix exists and Fix Master says it is ready/active for implementation. If the two cloud files disagree, or authenticated access fails, **STOP**. Do not fall back to a cached or local copy.
6. Sync the Wavefinity code checkout separately: run `git fetch --prune origin`, switch to local `main`, then `git merge --ff-only origin/main`.
7. Prove local Wavefinity `HEAD` equals `origin/main`. If not, **STOP**.
8. Only then create/switch to the exact assigned `fixN` branch from current `origin/main` and begin implementation.
9. Never create, restore, or commit a Wavefinity `/fixes` directory.

The cloud Help Code repository is the authority even if an old Wavefinity commit or branch historically contains a `/fixes` folder.

Planner-side handoff rule: before telling the coding agent to implement a fix, the outside ChatGPT planner verifies in `happydadto5/Wavefinity-Help-Code` current `main` that the active fix file exists, Fix Master has the intended ready/active status, and the cloud file contains the final rechecked plan.

- `main` is the accepted Wavefinity implementation line. Do not implement Help Code work directly on `main`.
- Each fix uses branch `fixN`, using the unpadded number: `fix6`, `fix9`, `fix12`, etc.
- Old unrelated branches are not blockers. Stop only when the exact assigned branch already exists and its ownership/state is unclear.
- Coding agents work only on the assigned Wavefinity `fixN` branch. Never force-push/rewrite `main` or merge the fix to `main` before outside review authorizes it.
- Make the coherent implementation, inspect the diff, perform the verification explicitly required by the active cloud fix, commit coherently, and push `origin/fixN`.
- At implementation completion, put the outbrief in the **cloud active fix file in `Wavefinity-Help-Code`**, including the Help Code specification SHA used, implementation commit SHA, files changed, tests/results, deviations, and environment limitations. Do not put the outbrief in a Wavefinity `/fixes` directory.
- Coding agents must never edit cloud `Fix Master.md`. If the coding environment can read but cannot write the private Help Code repository, include the full outbrief in the completion message and do not create a local fix file; the outside ChatGPT reviewer will write it to the cloud record.
- ChatGPT's outside completion review compares `fixN` against current Wavefinity `main` and the exact cloud fix specification.
- If review returns **NO — NOT FULLY DONE**, corrections continue on the same `fixN` branch.
- If review returns **YES — DONE**, the outside ChatGPT reviewer owns finalization when repository write/merge capability is available: integrate the accepted code into Wavefinity `main`, archive the active fix in `Wavefinity-Help-Code`, update cloud Fix Master there, verify both repositories, and release any downstream fixes whose prerequisites are now satisfied.
- If two active fixes overlap implementation files, prefer sequencing. If work already overlaps, the later branch must incorporate current `origin/main` after the earlier fix merges and be reviewed again against the new base.
- If another accepted fix lands on `main` while a branch is active, incorporate current `origin/main` before final review whenever the new change overlaps, affects a dependency, or changes assumptions.
- If multiple coding agents are active at once, use separate clones/worktrees rather than one working directory that switches branches.

The hosted app tracks `main`; fix branches remain isolated until outside review accepts them.

### 3. Fast vibe-coding & testing policy

#### Purpose & Core Rule

> **Help Code override:** The generic testing guidance below is for work without an active Help Code implementation contract. For a Help Code Fix/correction, the active cloud fix is the sole task-specific authority for testing. If it says not to write, update, or run automated tests, do not do so regardless of the generic Class A/B/C guidance below.

> **MAXIMIZE CONFIDENCE PER TOKEN.**
> Use cheap automated tests when they materially improve confidence.
> Browser-driven tests are retired by user decision as of 2026-09-25. Do not add,
> update, repair, run, or use them as completion evidence unless the user explicitly
> reverses this policy. Keep non-browser tests for frontend/web logic active.

Wavefinity should avoid both extremes: skipping useful automated verification and wasting time/tokens on ceremonial testing. The computer running a test does not meaningfully consume LLM tokens; token cost mostly comes from the agent reading output, diagnosing failures, or writing tests. Therefore prefer quiet, high-signal automated checks and concise output.

> **Implement carefully, inspect the diff, run the cheapest useful automated checks, and stop when the meaningful risks are covered.**

Existing tests are a safety net. Reuse them freely when they fit. Do not build a large new testing program merely because a change exists.

#### Change classification

**Class A — Small/localized change: TESTING OPTIONAL**
- *Examples:* wording, labels, tooltips, CSS/layout/spacing, moving or hiding one control, documentation, a clear one-line/local bug fix, a small local refactor, renaming, or a contained default/range change.
- *Action:* implement and inspect the changed path/diff. Skip tests when they add no meaningful signal. If a relevant existing automated test is cheap to run, it is fine to run it.

**Class B — Moderate/bounded change: AUTOMATED TESTING ENCOURAGED**
- *Examples:* one feature plus paired UI/API wiring; contained serialization; several files in one coherent path; a new local interaction/state flow; a meaningful bug fix spanning multiple functions.
- Prefer an existing targeted automated test or small related test group.
- A broader/full existing automated suite is also acceptable when it is fast, produces concise output, and can cheaply catch regressions outside the immediate path.
- Do not write a new test unless it is likely to protect an important behavior at reasonable maintenance/token cost.

**Class C — Major / Heavy-Lift / High-Blast-Radius change: AUTOMATED TESTING EXPECTED**
Testing is expected when the change can realistically break significant portions of Wavefinity outside the immediate feature.
- *Qualifying criteria:* shared box/wave/grid geometry; global mating/interlock rules; central data models; saved-design schema/versioning; broad save/load/generation paths; shared layout/assembly/registry infrastructure; major subsystem replacement; security/request boundaries; global browser state synchronization; common 3MF/export logic; versioned serialization.
- Use the relevant targeted tests and normally the existing broader/full automated suite when it is practical and reasonably fast.
- A large line count alone does not make work Class C; a tiny shared-contract edit can.

#### Browser-test retirement

Existing browser-driven tests and browser-only harness material are historical
reference under `retired-tests/browser/`. They are not part of active testing:
do not run, repair, modernize, or use them as completion evidence. Reactivation
requires an explicit later user decision. This does not retire ordinary
non-browser tests of frontend or web-service logic.

#### Correction-escalation rule

Repeated correction cycles are evidence that more real verification may be worthwhile.

- After **2 correction passes** on the same fix, reconsider whether additional automated coverage would cheaply catch the remaining issue.
- After **3 correction passes**, or after any runtime/integration failure escapes review, run relevant automated verification unless the environment truly cannot run it.
- A fix spanning multiple subsystems, migration, frontend/backend state, or persistence should normally receive automated verification before repeated corrections accumulate.

The Help Code fix file should state the testing approach for that fix, choosing from:
- **No testing needed**
- **Existing targeted automated tests**
- **Existing broader/full automated suite**

Name exact commands/checks when known, but do not turn the fix file into a testing plan.

#### Testing rules

- **Prefer existing tests.** Reuse them before writing new ones.
- **Targeted first when obvious.** If one small test group directly covers the change, start there.
- **Full suites are allowed.** A full existing automated suite is reasonable whenever it is fast enough, output is concise, and the extra regression coverage is worth the small token cost.
- **Use quiet/concise output.** Avoid verbose logs unless diagnosing a failure. Run the suite through
  `python3 run_tests.py` (whole suite) or `python3 run_tests.py test_foo test_bar` (a subset) — it
  prints one `PASS: N/N passed in Ys` line when everything passes, and only the failing test IDs plus
  their tracebacks otherwise. A green run costs one line of output no matter how large the suite is;
  `python -m unittest` directly is for when you need its own `-v`/`-k` flags while diagnosing a failure.
- **New tests are optional, not automatic.** Add one only when it protects an important stable invariant and is worth the implementation/maintenance cost.
- **Syntax/import checks are cheap** and encouraged when relevant.
- **Browser automation is retired.** Use static review and active non-browser checks.
- **Rerun failures, not reassurance.** After fixing a failure, rerun the failed/relevant checks. Do not repeatedly rerun already-passing suites without a reason.
- **No exhaustive matrices or random sweeps** unless the changed algorithm genuinely requires them.
- **No screenshot QA** for routine styling; inspect visuals only when visual behavior is itself the risk.
- If testing cannot run because the environment/tooling is unavailable, say so clearly and use the strongest available static review.

#### What still should NOT happen

Do not create testing bureaucracy:
- no `TESTING.md`;
- no per-session testing logs;
- no giant acceptance matrices;
- no dozens of near-duplicate cases;
- no “one more verification” loops after the named risks are covered;
- no retired browser-driven test;
- no new test merely to increase confidence cosmetically.

#### Fast implementation workflow

1. Read the affected implementation and direct callers.
2. Make the smallest correct change.
3. Inspect the changed code and diff.
4. Choose the cheapest high-signal verification appropriate to the blast radius.
5. Run relevant existing automated tests when they materially improve confidence.
6. Fix real failures and rerun only the affected checks.
7. Commit/push the coherent completed work.
8. Stop.

#### Quick decision rule

Before spending testing tokens, ask:

> **Which check gives the most confidence for the least agent interaction/output?**

- Tiny/local change with no meaningful runtime risk → testing may be skipped.
- Relevant existing targeted test → usually run it.
- Fast, concise full suite with useful regression coverage → running it is allowed and often worthwhile.
- Browser-specific behavior → use active non-browser checks and static review; browser automation is retired.
- Repeated corrections or escaped runtime failures → increase automated verification.

#### Definition of done

- **Class A:** requested behavior implemented, code path reasoned through, diff verified; cheap relevant automated checks may be run but are not mandatory.
- **Class B:** Class A plus useful existing automated verification when available; targeted is preferred, but a fast full suite is acceptable.
- **Class C:** implementation plus relevant non-browser automated verification; broader/full suite is normally appropriate when practical.

### Using the browser UI

The page is split between intent-based controls and a large responsive
workspace. The top design controls contain the dimensions, print mode and interior
interior-part editor. **Parts & options** below them holds the interior-part
palette and the bin-level options (Lid & Stacking, Inside Grip, Side Openings,
Edge Mount). The bin's name is the *Bin Name* field at the top, before the
dimensions.

**Base** and **Walls** are named preset selects sitting side by side. *Standard*
walls keep the original 0.8 mm wall; the other presets run from very thin
(0.4 mm) up to a 2.4 mm maximum. Only the cavity moves, while the exterior wave
and 8 mm grid stay fixed. Custom-wall connectors are generated for that wall
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
bin field in whole 8 mm units, independently of ordinary-bin wall thickness.
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
**Print Base Trim** in Space Actions sends a small ~50 mm two-piece
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
**Save Base Trim** / **Print Base Trim** in Space Actions build it from the
Surface definition (with the printer-bed size used to split it) and never create
an Inventory row. A bin you design saves itself into Inventory as you go and
reopening the Space later restores the design you were editing (resume is
recovery, not an Inventory identity). Each Inventory row has **Duplicate**.

A folder is either an untyped Design folder, or a typed **Space** - a
**Drawer**, a **Storage Box**, a **Surface**, or a **Pegboard**. *Create New Space*
configures the Space's type and dimensions first and chooses the save folder
last; *Open Existing* can instead turn an already-selected folder into a
Space, or use it without a type. The **Space** tab (beside *3D* and *2D*)
then lays out that Space's inventory. A folder can already hold a full
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
Space view or Inventory points to **Design first bin** (or adding an existing
bin), and spacer/connector actions stay disabled until there is something to
work on.

**The four Space types** are exactly **Drawer**, **Storage Box**, **Surface** and
**Pegboard**. A Storage Box's internal kind is `portable` (a legacy `box` kind
still normalizes to it). Its Space X/Y/Z are the usable child-bin field width,
depth and height; the outer case is derived. The case settings live on the Space
as `space.storage_box` (`secure_lid`, `latch_count`, `latch_strength`,
`lid_headroom_mm`, `label_enabled`, `label_text`, `label_location`,
`front_label_style`, `stacking`, `handle`, `wall_mm`, `base_mm`), round-trip
through `.wavefinity.json`, `layout.space` and hosted Inventory text, and default to
the established B4B values when a legacy Space has no block. **Space Actions**
owns the Space-level buttons - *Open Space…*, *Edit Space*, *Show Folder*, *New
Space* - plus the structural output: *Save Storage Box* / *Print Storage Box* for a
Storage Box and *Save Base Trim* / *Print Base Trim* for a Surface. Those outputs
are built by `organizer_space_outputs.py` as a transient empty-layout B4B (or Base
Trim) design from the Space definition and go through `/api/space/structural-*`,
which suppress Inventory logging entirely.

- **Space identity.** A typed Space carries a permanent `space_id` (UUID) in
  its `.wavefinity.json` (metadata version 8; identity required since version 5). The per-user profile keeps a
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
  **In Space** (editable design saved in the Space), **Saved** (current files exist),
  or **Printed**. There
  is no user-facing quantity: a row is one bin, and `Qty` survives only as a
  0/1 compatibility field derived from Status. Saving files is not printing. Print
  (direct, or in Space Inventory) marks each bin Printed exactly once, and only
  after Wavefinity handed it to Bambu Studio and the slicer opened
  successfully - it does not claim the physical printer finished the part.
  **Batch Save / Print** (Space Inventory): with nothing ticked the two buttons
  are whole-Space quick actions - *Save All Needed (N)* and *Print All Not
  Printed (N)*; with rows ticked (or via *Select all not printed* / *Select
  all*) they become *Save Selected (N)* and *Print Selected to Bambu Studio (N)*.
  Both use one preparation step: it re-reads the Inventory, reuses a row's
  current files, and generates only rows without current files (each becomes
  Saved as soon as it is made). Save stops there; Print then opens the files in
  Bambu Studio. Applicable Space connectors are included automatically.
  If a bin fails part-way, the
  bins already saved stay Saved, Bambu Studio is not opened, and the unfinished
  rows stay selected to retry.
  **Editing a saved bin.** Changing the design of a bin that already has saved
  files makes those files stale (the row shows *In Space*). When focus leaves
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
- **Space workspace.** A typed Space opens as one workspace with a **Space |
  Design** switch at the top left, under the Space's name, type (Drawer,
  Storage Box, Surface or Pegboard) and size, and its **Space Actions**. The
  switch decides what the left panel edits: *Space* is the layout tools, *Design*
  is the current bin. The 3D and 2D tabs select Design; the Space tab selects
  Space. Opening an existing Space with a bin (or a legacy hand-added row) in Inventory
  starts in *Space*. An empty or spacer-only Space starts in *Design / 3D*. The
  workspace stays open until the folder stops being that Space. The name, type and
  size are shown read-only; **Edit Space** opens the same fields in place with
  **Save Changes** and **Cancel** (never the New Space buttons).
- **Drawers.** A drawer's inside width, depth and **max height** come from its
  Space. The layout has one fixed rule set, not choices: an **8 mm** whole-unit
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
- **Stacking.** A bin printed stackable (a snap-on lid, or direct snap) shows
  a ⇅ on its swatch and its style under its name. Drop it on a bin of the same
  size that stacks the same way and it snaps on top, sides aligned. Anything
  else is refused with the reason: a different size, a different style, a bin
  not printed to stack, or a stack taller than the drawer's max height. Lid and
  direct interfaces are intentionally same-mode only. The Height field is the
  module contribution: a 50 mm bin adds exactly 50 mm. Its detached physical
  envelope also includes the exposed interlock (1 mm on a lid, 3 mm for a
  direct snap), which the drawer clearance check includes. Dragging a bin in a
  stack takes it and everything above it; dragging the bottom bin moves the
  whole stack.
- **Inventory is the primary Space control.** Each ordinary row shows a
  general selection tick, **Bin N**, name, dimensions and exactly one lifecycle
  label (**In Space**, **Saved** or **Printed**). Click an editable row to open it
  in Designer. Row actions include **Duplicate**, **Print**, and **Mark Printed**
  (or **Mark Not Printed**). Selection survives filtering and sorting; one
  Inventory **Delete** button removes selected ordinary bins. Spacers remain
  visible below ordinary bins. *Clear selection* is disabled while nothing is ticked.
- **Placing.** Drag a bin from **Unplaced bins** (or its Inventory row) onto the
  Space. Drag placed bins to move them: they snap to the 8 mm grid and refuse
  overlaps and the Space edge. Drag one off the Space, or select it and press
  **Delete**, to unplace it - it returns to Unplaced bins and stays in Inventory.
  Keys: the arrows move one unit, **Delete** unplaces, **F** fits the view, **Esc**
  deselects. An ordinary bin is placed at most once; a legacy layout that holds
  several copies of one row keeps one deterministically when it loads.
- **Space & spacers.** The drawer view itself shows the one or two biggest
  open rectangles a bin could still go into, each as both a millimetre size
  and a Wavefinity-unit size; the left panel covers connector and layout problems
  instead of restating those as a summary. The **Spacers** section (below
  Inventory, collapsed until opened) fills the drawer,
  15 mm tall by default (*Height*). There is one filler part, the **Spacer**.
  Spacers are repeated filler parts, so they keep their own placement counts.
  Empty grid cells become **X spacers**: open frames whose outside is exactly
  a bin's wavy wall, so they nest with the bins around them and take a
  connector (the lock bumps are kept) - inside, they have no floor, just one
  big X brace, or a row of X's when the patch is long and thin. The strips
  between the grid and the drawer walls become **edge-facing spacers**, cut
  from a virtual bin standing just outside the grid: wavy and interlocking on
  the bin-facing side, flat on the wall side, and sized to the drawer's real
  leftover millimetres. Neither kind of spacer is forced onto the whole 8 mm
  grid a normal bin's own size must be - a genuine 4 mm-wide leftover, edge or
  interior, is filled at its real size.
  Only a genuine manufacturability floor - is there still room for a cavity
  once both walls are subtracted? - rejects a spacer as too narrow to print.
  A long edge is still split into pieces no longer than *Longest piece*,
  each covering its own real share of the run exactly (the last piece can be
  a genuine leftover shorter than a full grid cell), built oversized enough
  to satisfy the wave engine's own grid requirement and trimmed back down to
  its true length, so the piece ends still nest correctly. Files go to the
  save location and rows go into
  the inventory as the one Spacer kind; a folder saved before this
  distinction existed still loads its old edge-shim rows and quietly
  rewrites them as spacers the next time it saves. Spare copies of a matching
  spacer already in the inventory are used first. *Keep gaps open from*
  leaves any gap at least that wide both ways empty, for a bin you will print
  later. **Save Selected Spacers**
  also saves one connector file for each pair of rim heights the layout needs,
  and says how many of each to print. Stacks join at their top bins; X spacers
  need none, since their waves hold them. **Print Spacers…** selects spacer
  copies for Bambu Studio. **Create Spacers** plans candidates before **Save Selected Spacers**.
- **Surface Fill** (Surface only) turns free Surface cells into ordinary editable
  bins. It first settles the Designer's autosave, then works from the authoritative
  Inventory and layout.
- **Saving.** Space layout autosave is always on - there is no off state and no
  manual Save button. Layout changes and each bin's design source save as you
  work; names and status save straight away, because they are the inventory.
  The layout is recalled automatically every time you open the tab. **Save
  location** shows the current folder and opens the folder picker, the same
  as the main editor's.

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
length grows on the 8 mm grid. Shrinking a bin below any existing Pocket,
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
**Fill the bin** remains for free-size parts. Divider and Curved Scoop
footprints continue to follow the bin because full-span behavior is their
purpose.

### Insert types

The browser UI offers two: **Fused**, where holders print as one solid part
with the bin — strongest, uses the most floor area, but the parts are
permanent — and **Removable**, where holders print separately on a thin
0.6 mm base plate that drops into the bin, so the interior can be swapped
while the bin stays put.

A third mode, **8 mm cartridge**, exists at the engine and CLI level
(`--mode cartridge`): a removable insert constrained to whole 8 mm cells, so
it is repeatable and interchangeable between matching bins at the cost of
some usable edge area (on the 128 x 88 comparison bin that is 120 x 80 mm,
9.8% less floor). The browser UI does not expose it as a choice — reusable
coordinate footprints across bins are a scripting concern, and picking it by
mistake in the editor just produced a confusing revert once an already-placed
interior part did not land on an 8 mm cell.

Tall holders may use the middle of the bin, but anything entering the 2 mm strip
beside a wall is capped below the connector arms. The editor's default divider
height follows that limit; an explicit unsafe height is refused at generation.

**Fused** is the default and gives the most usable floor.

Floor lettering is a **text** interior part, placed and checked like every other
one — see [Text on the floor, and the rim label](#text-on-the-floor-and-the-rim-label).
A bin may carry several. In removable modes each is inlaid into the insert plate
rather than hidden under it. The **rim label** is separate: 5 mm letters when
they fit, otherwise automatically smaller, inlaid flush into a 7 mm-deep rear
ledge just below the rim. Its underside rises at 45 degrees and prints without
supports.

The optional **curved scoop** spans the usable width at the front of the bin and
rises 60% up the usable wall height, so a part sweeps forward and lifts out
over the low front lip — the opposite wall from the rim-label ledge. In
removable modes it is part of the insert; in fused mode it is part of the box.
An auto-placed text moves clear of the scoop strip, and the 2D editor shades the
space reserved by a scoop or rim-label ledge and refuses overlapping parts.

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
path — that is application function, not a sandbox escape. Mesh boolean
operations run behind a process-wide lock, serializing geometry work rather
than risking concurrent calls into the mesh backend. Hosted exports use isolated
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

**Verification:** browser-driven tests are retired and are not part of the
active verification contract. Python API contracts and JavaScript syntax are
covered by `test_wavefinity_web.py` and `node --check`. A very dense design (many
cradle/bore parts at once) serializes a large triangle payload to
the browser; camera motion stays client-side and fast regardless, but the
initial load is heavier. **Save design** relies on the browser's own
download prompt. Photo Nest's automatic finger-access search and its 2D access
indicators are interactive UI behavior; their active automated checks remain
non-browser tests.

---

## The design

### Holder primitives

Every holder owns a floor zone. Item-based holders (`cradle`, `bore`) describe
the stored tool with measured dimensions. `cradle` is deliberately just
**Length** and **Diameter** — it
beds the whole tool, shaft and handle, into one continuous half-round trough,
so the fatter handle needs no separate number. The trough is an open channel
the tool simply drops into, so it takes the tool at its **true diameter — no
fit clearance** — and has no fit-clearance field. The trough walls are sized
automatically, proportional to the tool diameter (about a quarter of it,
floored at the thinnest printable wall and capped so a fat handle never grows a
slab), so there is no wall setting to expose either. There are no fixed tool
presets, since every bin is cut for one specific tool.

A cradle starts as a single trough (**Quantity 1**, like a post). **Quantity =
N** places N troughs across the zone, **Quantity = auto** fits as many as the
zone holds. **Spacing** controls how a row relates: `0` (the default) joins the
row into **one continuous body**, with each pair of facing side walls fully
overlapping so the middle joint is no thicker than either outer side. Raising
it separates those walls; once they no longer touch, a real air gap opens and
the row splits into separate pieces. For ordinary cradles, its footprint tracks
what it holds: the run axis (the tool lies along it) is the tool length; the across axis is N
channels at `diameter + half wall + spacing` pitch. **X direction / Y direction** chooses which bin axis the tool
lies along — a 40 mm tool needs 40+ mm that way, so in a long narrow bin only
one direction fits, and the editor says which when it doesn't: *"40 mm long but
its zone only runs 13 mm along x"* rather than a raw overflow. Every
auto-computed edge rounds up to the 1 mm editor grid so the pipeline's snap
can't trim a trough below what the tool needs.

When an interior part does not fit, its editor offers **Grow the bin** and the
same growth normally happens automatically. The bin grows on the 8 mm grid to
hold every part at its real footprint. It never shrinks an already-large bin.

**Bin Height means wall height, not interior part height.** A shallow bin -
a 10 mm vanity-top organizer, say - can still carry useful interior geometry
that rises above its own wall, but only under narrow conditions. In **Fused**
mode, with no active stacking interface and no enabled lid, **Cradle**,
**Bore**, **Post**, **Pocket**, **Slot Rack**, **Steps**, and a **Raised-Wall**
Photo Nest may extend above the rim - a 30 mm post can stand as a ring holder
on a 10 mm wall, for example. **Divider**, **Curved Scoop**, **Text**, and a
**Recessed** Photo Nest always stay bounded by the bin, in every mode, because
their geometry genuinely depends on the material above them. Every part in
**Separate** or **Cartridge** mode stays height-bound too. Stacking, a lid,
and the existing wall-touching connector clearance always win regardless of
this policy - a tall holder that would collide with any of them is refused,
never silently shrunk or clipped, and the bin is never made taller
automatically to accommodate it. The 3D editor shows a plain informational
note ("Extends N mm above rim") when the part being edited legally does so;
there is no separate "allow above rim" setting.

**Photo Nest — a custom holder built from your photo.** Put one flat tool on a
US Letter (8.5 × 11 in) sheet, keep all four paper corners visible, photograph
it directly overhead, and upload the photo. Wavefinity corrects the paper to its
true size, traces the tool's outline, and asks for one number: **Tool
thickness**. As soon as both are ready it builds a complete, practical,
printable bin in seconds — no other choice is required. Missing paper, severe
perspective, an edge-touching part, multiple parts, and unusably small/noisy
outlines are rejected with a specific correction. If automatic paper detection
fails, Wavefinity switches to the 2D view and shows the original photo. Click
all four paper corners in any order; Wavefinity orders and validates them
automatically and retries the same photo without requiring another upload.
The retired measured/segment
Nest format is rejected explicitly rather than silently reinterpreted.

A new scan defaults to **Recessed Cavity**: a solid deck fills the fitted area
and the tool's own shape is cut down to the ordinary printable floor, with a
small automatic lead-in so the tool drops in without catching an edge. Cavity
depth defaults to **60% of Tool thickness** and stays in that Auto mode -
recalculating whenever Tool thickness changes - until it is hand-edited, which
switches it to Manual (with a **Reset to 60%** button to switch back); a
Manual depth is clamped to Tool thickness if that later gets thinner.
**Raised Wall** remains available: a contour-following wall grows from the
floor, with an adaptive exterior buttress sized to its own height (rather than
one fixed foot) and a gentle top round, broader outside than in.

**Finger access** defaults to **Automatic**: one Python search finds a safe
pair of opposing openings (or falls back to one, or to none with a warning) -
spherical scoops cut into a Recessed deck, rounded U-notches cut into a
Raised Wall. **Off** leaves the holder plain. **Custom** exposes Sides / Ends
/ Both and a 12-40 mm opening width. **Push Out**, raising the tool on a
shaped floor with one end left low to press up, remains an advanced
Raised-Wall-only option; switching to Recessed while it is active turns
Finger access back to Automatic instead.

**Automatic footprint sizing** is on by default: the bin's Width and Length
grow or shrink to the smallest footprint that fits the holder, centred, every
time the outline, Tool thickness, Holder or Finger access changes. It owns
Width/Length only — Bin Height is always the height the user set, and a
manual Height edit never turns it off. Typing a Width or Length, or dragging
the Nest off-centre, turns it off for that design ("Fit footprint to tool"
then does the same X/Y fit as a one-off); turning it back on recentres and
resizes again. A design saved before Auto-size existed keeps its old
grow-only behaviour unchanged, including its historical Z growth.

The 2D layout draws the softened silhouette - the same one the printed part
gets - with move, proportional-resize and rotation handles, plus an outline
editor: drag a point directly, **Add Point** (click near an edge) and
**Delete Point** (click a point, minimum three left), and **Reset outline**
to return to the most recently accepted scan. **Photo opacity**, **Object
sensitivity** and **Edge cleanup** are available in the 2D **Scan controls**
panel (the scan settings default to reproducing the original trace); a slider shows
its retraced candidate dashed over the accepted outline without changing
anything until **Apply adjusted outline** accepts it, and a tuning attempt that fails
to produce a valid outline leaves the accepted one untouched. **Fit
clearance** sets the gap between the holder and the part, and **Soften
outline** rounds off small inward and outward details - a separate pass from
Edge cleanup, which affects tracing itself. Photo opacity dims the reference
photo behind the outline in the browser only; it disappears, along
with the tuning and paper-corner tools, once a design is reopened without its
original photo, since the photo itself is never saved.

Cradle holders also offer **Alternate ends** (off by default): when enabled,
every second repeated tool sits near the opposite end of the run axis, leaving
about 10% of that axis clear at each end. Each trough becomes its own separate
solid body. Alternating needs a run axis at least 1.25× the tool length; turn
it off, or rotate, if the run axis runs short. Saved as `alternate_ends`; no
effect when only one tool fits.

| Holder | Purpose | Optional `key=value` settings |
|---|---|---|
| `cradle` | Half-round troughs along X or Y - `spacing` 0 joins the row into one shared body, higher values split it. No fit clearance; wall thickness auto-scales with the tool | `spacing`, `floor_gap` |
| `nest` | Photo-traced Photo Nest: a Recessed Cavity deck (default) or a Raised Wall, on the bin floor or removable insert, with Automatic (default), Off, or Custom finger access, or Push Out (Raised Wall only). `rim` (thickness) is fixed | `clearance`, `smoothing`, `tool_thickness`, `holder_style`, `cavity_depth`, `cavity_depth_mode`, `auto_size`, `lift_assist`, `finger_position`, `finger_width`, `push_position`, `push_area`, `push_depth` |
| `bore` | Round, hex or square holes for items standing up. One `bore_style`: `base_straight` (default), `base_wavy`, `walls_straight`, `walls_wavy`. Sizing is persistent: `xy_size_mode` (`manual` / `bore_to_bin` / `bin_to_bore`; Walls Only offers only `manual` and `bin_to_bore`, default `bin_to_bore`) and `height_size_mode` (`manual` / `bore_to_bin` / `bin_to_bore`). X/Y counts are always explicit. Auto Height under an Edge Mount screwdriver-access hole stops 2 mm below the lowest cutter. A Base cavity may be as deep as the Bore is tall (`depth == height`) | `bore_style`, `depth`, `height`, `wall` (Walls Only only), `columns`, `rows`, `xy_size_mode`, `height_size_mode` |
| `post` | Lightly tapered pegs for rolls, spools, sockets and ring-shaped parts | `diameter`, `height`, `spacing`, `taper` |
| `divider` | One or more straight or leaning subdividing walls along X or Y, with optional sloped tool-slot bottoms | `height`, `thickness`, `angle`, `spacing`, `bottom_angle`, `reverse_bottom`, `alternate_bottom`, `minimal_bottom`, `bottom_supports` |
| `pocket` | Raised rectangular tray with a recessed centre and 0.5 mm chamfered edges | `height`, `wall` |
| `text` | Lettering sunk flush into the floor (or standing proud), one 3MF object each, any number per bin | `text`, `cap_height`, `quarter_turns`, `depth`, `raised`, `auto` |

There is no separate "slot" kind - a divider covers it. A slot's one real
extra, a shallow groove with a solid floor left under it, was a narrower need
than a full separator wall; the browser now defaults a new divider to run
wall to wall and lets `count` place several of them, which covers dividing
a bin into compartments in one action instead.

A divider can lean up to **45 degrees** off vertical — the standard
support-free FDM overhang limit — for holding what it stores at an angle
instead of straight up. `angle` is signed (negative leans the other way). A
second flag, `wedge` (default **on**), picks the cross-section: a wedge
keeps its back face vertical and only the leaning face slopes, so the wall
stays thickest at the floor — where the sideways push of whatever leans
against it actually bears — and tapers as it rises, the shape a physical
gusset uses. Turning `wedge` off gets a uniform-thickness sheared wall
instead: the same lean, thinner at the base, and the shape that snaps.
In the browser this control is now labelled **Wall lean** so it is not
confused with **Bottom slope** below; `wedge` / straight still applies only
to the wall lean.

A divider can also tilt the **bottoms of the tool slots** it forms, so a
tool rests at an angle without the wall itself leaning. `bottom_angle`
(0–75°, default 0 — a plain flat bin bottom, so older designs are
unchanged) sets the rise, measured along the divider/tool direction: +X
(toward the right) for a divider that runs along X, +Y (toward the back)
along Y. `reverse_bottom` sends the rise the other way; `alternate_bottom`
flips every second slot, ordered across the divider zone, and
`reverse_bottom` then flips that whole alternating pattern. `count`
dividers make `count + 1` supported slots, each rising `slot_length ×
tan(bottom_angle)` from the existing floor. A combination whose high end
clears the divider height or the bin is refused with a plain "reduce the
bottom slope, shorten the run, or increase the bin height". By default the
slope material is one solid wedge per slot; `minimal_bottom` replaces it
with `bottom_supports` (default 3, a positive whole number) evenly spaced
crossbars that touch the same theoretical sloped plane, print support-free
(vertical stems, 45° gussets to the floor), and use materially less
plastic. Either way the normal structural bin floor or removable-insert
plate is untouched — this is only the material added above it.

Every divider - wedge, straight-leaning or plain vertical - also gets a
1 mm, 45-degree chamfer where its two long faces meet the floor
(`DIVIDER_CHAMFER`). It is a pure addition below the wall's stated profile,
not a substitute for any of it: the lean and thickness the fields describe
are exactly what is built above that first millimetre. A straight
(non-leaning) full-span divider does not get one yet - it is built by a
separate, simpler path that has not been extended to match.

A divider can also be told to run the full width or depth of the bin and
hug the box's true wavy wall exactly — not the safe straight-sided
rectangle every other holder is confined to, which would leave a visible
gap at most points along the wall. This `full_span` flag works together with
a lean: the two combine into one 3D boolean intersection against the bin's
real interior volume, so a leaning full-span divider hugs the wave in both
directions at once. The browser sets it by default for every new divider -
"wall to wall" is the normal case, and there is no manual toggle for it yet
(saving a design still preserves whatever a script or an older save set it
to, `full_span` or not).

A divider is also the one kind whose `along` is a direct browser choice
("Runs along" X/Y) rather than inferred from its footprint, and whose
`count` places several parallel walls instead of repeating some other
element: `count` dividers split the cross axis into `count + 1` equal gaps -
fence-post spacing, so `count = 1` (the default) lands exactly where a
single centred divider always has. `spacing` overrides that computed gap
with an exact one instead (blank keeps it automatic); since it is used as
the gap as-is, an override only keeps the group centred if it happens to
equal the auto value. Height, angle, thickness and spacing apply to every
wall the count places, not just one.

Builder options are intentionally generic. The editor passes them to the
registered builder, so a future `@feature` function can add its own settings
without changing the layout file format or editor data model.

### The wave

Every straight wall carries the same fixed-pitch wave:

- **4.0 mm per full cycle** — 2 out, 2 back
- **0.4 mm deviation each way**, 0.8 mm peak to peak
- **Odd about the wall's centre** — it leaves the middle at zero and comes back
  inverted
- **Full amplitude the whole way into the corners**; there is no corner blend

Changing X or Y reveals more or fewer whole cycles; it never stretches the wave.

Bins have an assembly orientation: **left mates with right, and top mates with
bottom**. Same-side seams are not part of the supported layout. The odd wave
keeps each opposing pair on the same global phase lattice.

Turning a bin 180 degrees is still fine, and that is what the odd wave buys.
Spun, a bin's +X wall lands where its —X wall was, and an odd wave means the two
carry the same shape, so the turned bin tiles exactly as before
(`test_a_box_still_tiles_when_it_is_turned_round`). The orientation rule above
is about which *faces* meet, not about keeping every bin the same way up.

### The 8 mm size grid

**Box X and Y must be whole multiples of 8 mm, from 8 mm up.** X and Y are
independent, so 16x16, 16x48, 40x56 and so on are all fine — nothing has to
scale proportionally.

**One unit is 8 mm** — the grid step itself — so every legal size is a whole
number of units and no decimals are needed: 1, 2, 3, 4, 5, 6 = 8, 16, 24, 32,
40, 48 mm. The browser UI takes the modular drawer footprint in millimetres and
snaps it to the nearest 8 mm step. Usable interior is a derived measurement;
making it the input would add the wall allowance once per bin and break mixed-size
tiling.

**16 mm (2 units)** is the smallest box that takes a connector on both sides. A
1-unit side is still legal and useful: an 8 mm wall is too short for a connector
and too short to seat a lock bump, so a narrow bin joins on its long sides only
— put the clips where clips work. Asking for a connector on a wall that cannot
hold it gives a clear error rather than bad geometry.

The rule falls out of wanting to drop boxes of any size into a drawer and have
every seam work. Pack boxes edge to edge and a box of size `S` sits with its
centre half a size in from its edge. Sizes that are multiples of `2 × 4 mm` put
every box centre on a multiple of the wave, and once that holds,
`sin(2π(y − centre)/4)` collapses to `sin(2πy/4)`: **the wave stops depending on
which box it belongs to and becomes one global function of position in the
drawer.** Any two walls that meet then nest, whatever the boxes measure.

Off-grid sizes still tile with their own clones but foul the moment they meet a
different size — a half-wave shift puts crest against crest, a 0.55 mm
interference. They are rejected with the nearest legal size named.

### What a size actually measures

The UI shows this live as you change the size:

| X units | Grid footprint | Outside (crest to crest) | Usable inside | Joins on |
|---:|---:|---:|---:|---|
| 1 | 8 x 48 | 8.55 x 48.55 | 5.06 x 45.06 | long sides only |
| 2 | 16 x 48 | 16.55 x 48.55 | 13.06 x 45.06 | both |
| 4 | 32 x 48 | 32.55 x 48.55 | 29.06 x 45.06 | both |
| 6 | 48 x 48 | 48.55 x 48.55 | 45.06 x 45.06 | both |

(All 6 units deep, so 48 mm in Y.)

**Grid footprint** is what the box occupies in the drawer. **Outside** is the
real bounding box — the wave crests stand one amplitude proud of the footprint
on each side, and the mating gap pulls it back a little. **Usable inside** is the
largest straight-sided object that fits: both faces of a wall carry the same
wave, so the cavity is a constant-width channel that **weaves** side to side, and
anything straight has to clear the full swing. That costs one amplitude at each
end on top of the two walls.

### Grid and mating

Boxes tile on a plain X by Y pitch. The solid outline is smaller than that pitch
by a **0.25 mm mating gap**, so two boxes placed one pitch apart have their waves
nested with a constant 0.25 mm clearance and never touch. Measured perpendicular
to the leaning wall rather than straight across the seam that is **0.21 mm**
— `nested_clearance()`, and the figure a slicer actually sees.

Where two wavy walls meet, the corner is a short chamfer eased to a **0.6 mm
fillet**. The rounding is a morphological opening, which only affects convex
corners sharper than that radius — the wave's own crests are far blunter, so they
come through untouched.

**Two of the four corners look flatter than the other two, and that is correct.**
Walls stop `CORNER_INSET` = 1.0 mm short of the nominal corner, wherever the wave
happens to be at that point. Because the wave is odd, one diagonal's walls end on
a crest and the other's on a trough, so the chamfer joining them comes out about
**1.97 mm** on one pair of corners and **0.86 mm** on the other. The 0.6 mm
fillet eases the ends of each chord but does not remove it, leaving roughly
**1.26 mm** and **0.50 mm** of flat in the exported solid. This is real geometry,
not a preview artefact.

It is also not a mating surface. A corner is a chord across the wave, and a
chord cuts *inward* from the envelope the walls sweep — so a corner can only
ever add clearance, never take it away. Two bins sharing a wall clear each other
by 0.21 mm the whole length of that wall, matched sizes and mixed sizes alike;
two meeting only at a corner clear each other by about **1.2 mm**.
`mating_clearance()` measures exactly this, and the suite pins it for a packed
drawer of seven different sizes.

### Lock detent

Each wall carries a row of **small chamfered bumps** on its **interior face**,
and each connector arm has **matching notches**:

- **0.35 mm** protrusion, 1.0 mm tall, 1.2 mm long
- One on **every** wave extremum the wall can carry — crests as well as troughs,
  so every 2 mm — kept clear of the corners. A 16 mm wall gets four, a 48 mm wall
  gets twenty, an 8 mm wall gets none
- Both faces run at exactly **45 degrees** from the buried root right out to the
  tip, so there is no horizontal face anywhere on the feature: it prints
  **without supports** in either orientation
- Top of the feature sits 4.0 mm below the rim

Push the connector down and the arms ride over the bumps, then the notches drop
over them. Seated, the clip is free (0.0 mm³ interference); lifting it drives the
notches onto the bumps, and that is the lock.

Because every box centre lands on a multiple of the wave, these bump positions
form **one lattice shared by every box in the drawer**. That is what lets a
connector engage *both* neighbours even when they are different sizes.

### Connector

A staple that drops over the seam between two boxes; its two arms descend inside
both. Arms are **1.0 mm** thick (two 0.5 mm perimeters), the cap is 1.2 mm, total
height 9.6 mm, default length 12 mm.

Set the two rim heights in **Connect bins**. When they differ, the arm over the
shorter bin is extended by the height difference, so both sides still lock. The
generated file is flipped with its flat cap down for support-free printing.

Across that extension the shorter bin's wall has not started yet, so the arm has
nothing bracing it. Past a 2 mm difference the extended arm is fattened into a
**tapered web** over the unbraced span — up to 3.0 mm thick at a 30 mm
difference (a 50→20 mm pair), ramped back to a plain arm over the last 6 mm
before it enters the bin, with a brace in the corner under the cap — and the
whole part is made up to **50% longer** so more bumps share the load. Equal-rim
connectors are unchanged. Handles differences of roughly 30–40 mm; see the
`DIFFERING_*` constants in `organizer_engine.py`.

The 0.02 mm tolerance, 12 mm length and 9.6 mm base connector height were
chosen from a printed five-clip fit plate. **Connect bins** shows the resulting
printed height, including any extension for a shorter bin.

For equal-height bins it is one universal part and goes on either way round.
For unequal-height bins, generate the connector with the two actual rim heights.
Its centre has to land on a **whole wave**, so `--position` must be a whole
multiple of **4 mm**; anything else is rejected.

Whole waves, not half waves. The corridor between the arms is cut to the wall's
wave, and that wave *inverts* every half cycle. A clip made a half-wave along is
therefore the printed one **mirrored** — identical volume, and a shape no amount
of turning a part over will produce. Slide the real part half a wave onto a seam
and it meets the wall crest to crest, jamming by about 48 mm3. The rule used to
accept 2 mm, and every fixed position the tests exercised happened to land on a
whole wave, so nothing caught it.

A clip also needs open cavity on **both** sides of the seam. Where two short bins
butt end to end, the far side of the seam at that joint is their end walls, full
height — so the clip has to clear the joint by half its own length, which on the
4 mm lattice makes the first usable spot 8 mm away.

Reversibility is why the bumps sit on **every** extremum rather than every other
one. Two things have to line up when you spin a connector: the wall it hugs must
look the same upside down about the connector's centre, which needs the centre on
an **even** millimetre, and the notches must mirror about that centre, which with
bumps every 2 mm they do. With bumps on alternate extrema the two requirements
landed on odd and even millimetres and could never both hold — **no length or
position could fix that**, which is why the wave shape had to change instead.

Note that spinning the part and *moving* it are two different requirements.
Turning it over needs an even millimetre; being the same part at all needs a
whole wave. Whole waves satisfy both, which is why 4 mm is the rule.

### Flat wall band at the base (optional)

The wave runs on both faces of a wall, so the inside is wavy too, right down to
the floor. An advanced setting, **0 to 1 mm**, gives the bottom of the bin a
band of **flat** wall rising from the floor:

| Setting | What you get |
|---:|---|
| 0.0 | wavy all the way down (default) |
| 0.5 | the first 0.5 mm above the floor has flat walls |
| 1.0 | the first 1 mm above the floor has flat walls |

It is a **height**, not a strength: the wave above the band is completely
unchanged. The cavity becomes two stacked shapes - a straight-sided one sitting
on the floor, and the usual wavy one above it.

The band is sized to the innermost point the wave ever reaches, so it only ever
**adds** material against the wall and can never cut into it. That is also why
**usable interior does not change**: the band is exactly the rectangle
`usable_inside` already reported.

The outside profile, the grid and the mating are untouched. The band sits on the
floor and the connector arms hang from the rim, so on any normal bin they are
nowhere near each other; on a very shallow one they would meet, and asking for a
connector then gives an error saying how tall the box needs to be.

### Text on the floor, and the rim label

Floor lettering is an **interior part**, not a property of the bin — so a bin can
carry **as many labels as it needs**: a size over each bore cluster, a name along
the front. Pick **Text** from the palette, type what it should say, and it moves,
resizes, turns and is checked against its neighbours through exactly the same
editor path as a cradle or a divider.

Each text is **sunk into the surface it sits on**: that surface gets a pocket and
the lettering is the solid that fills it flush, exported as **its own part of the
3MF**. The `.3mf` is written as one assembly object with the body and every piece
of lettering as named parts, so Bambu Studio / OrcaSlicer opens it directly — no
"load as a single object with multiple parts?" prompt — and a
`Metadata/model_settings.config` sidecar opens the body on **filament 1** and all
lettering on **filament 2**, so the two-colour intent is already set. No print
profile is embedded, so an opened file still uses the slicer's current printer
and process. (A generic 3MF from a non-slicer tool: recent Bambu Studio may still
note it "only contains geometry" — nothing is lost, and slicing is unaffected.)

- **Its zone is its size.** Drag a corner and the lettering scales to fill it.
  **Letter height** overrides that but is never allowed to overflow the box; a
  box too small to hold the text at the **5 mm** minimum is refused, saying what
  it needs.
- **Place it for me** hands positioning back to the engine: stay centred where it
  fits, otherwise move beside whatever is in the way, then turn, then shrink (no
  smaller than **5 mm** on that path). Dragging, resizing or turning it by hand
  switches that off, so it stays where you put it.
- **Stand proud** puts the letters on top of the floor instead of sunk into it.
  Either way they remain their own part on filament 2.
- Sunk **0.4 mm** into the default 0.6 mm floor, leaving 0.2 mm beneath, and
  reads correctly looking into the open box, which is the way the box prints.
  The pocket and the inlay are exact complements: put them back together and you
  get the plain box, to the last cubic micron.
- In removable modes the lettering is inlaid into the **0.6 mm insert plate**
  rather than hidden under it. Text that would hang over that plate's edge is
  refused rather than clipped mid-letter.
- Two texts reading the same thing get distinct part names (`M3`, `M3 2`) — a
  3MF object name has to be unique or the second silently replaces the first.

The **rim label** is the one piece of lettering that is not an interior part: it
sits on a shelf just below the rear rim, so it has no floor zone to drag. It
targets **5 mm** letters on a **7 mm** front-to-back shelf, automatically
shrinking only when needed; a warning appears below **4 mm**. It remains a
0.4 mm-deep flush inlay and its own part on filament 2; the shelf's underside
rises 7 mm over its 7 mm run, an exact 45-degree self-supporting slope. Its
3.4 mm rim clearance leaves room for the stacking foot or lid. Leave **Rim
label** empty for none.

**The part name alone names the file**: `Box 48 x 48 x 40 Driver rack.3mf`.
Lettering does not appear in it — with several labels there is no answer to which
one would stand for the whole file. The first label you actually type seeds a
blank **Part Name** once (a bare size like `8` or `12mm` never does); after that
the two are independent, so a bin can say `M3` on the floor and still save as
`Driver rack`. Characters a filesystem would object to are stripped.

### Edge Mount

**Edge Mount modifies an ordinary bin; it is not a bin type, an interior
part, or a second bin-generation path.** It is available for a normal Bin
and for both Stacked Bin-to-Bin and Stacked Lid-to-Bin, and it is hidden (but
preserved in the saved design) while Storage Box is selected, since Storage Box uses a
separate body architecture. It lets a normal bin hang vertically outside a
cart, table, shelf or workbench: one selected wall (**Front** `-Y`, **Back**
`+Y`, **Left** `-X`, **Right** `+X` - the same convention the rim label
uses) faces the support. That one **side** setting controls both
subsections at once - there are no separate mounting-side and label-side
choices.

The editor reads in a fixed order: **Mounting side** is the only field above
both sections; **Label** and **Screw Mounting** are always-visible sections
below it, each owning its own enable control - Label's is a **Label: None /
Separate Part / Integrated** selector (its first control), Screw Mounting's
is a checkbox in its own section header. A brand-new Edge Mount opens at
Label **None** with Screw Mounting off; turning Label to **None** hides its
detail fields without erasing their stored values, so re-enabling Label
later restores the same text/dimensions. Saving still needs at least one of
the two switched on.

- **Label** - choosing **Separate Part** prints the projecting plate as its
  own **Edge Mount Label** file on one continuous shallow snap/slide saddle
  that follows the selected wall's real wavy shape; it is shown installed in
  preview. Separate labels also use vertical **Standoff Ribs** on the bin
  body by default: they match the clip's outer thickness so the bin sits
  flat on its mounting surface. Auto spaces the ribs across the selected
  wall, or you can choose 1-20 manually. Existing saved Separate labels keep
  ribs Off until you enable them. A Separate Part label is always
  Inlaid/Flush - it is exported and rotated for print with its text face
  down, so Raised is not a valid state for it, and the Label style control
  is hidden entirely while Separate Part is selected; this is enforced both
  in the editor and, so a legacy save or any non-UI input cannot bypass it,
  by the saved-shape data itself. **Integrated** keeps the original fused
  plate and can still choose **Inlaid/Flush** or **Raised**; old saved
  labels without a label type reopen as Integrated. **Length** is either
  Full Side (the wall's real wavy-envelope span) or Text Length (the fitted
  text plus a 2 mm margin on every side, never wider than Full Side).
  Projection is one exact 5-200 mm field; a new Edge Mount starts at
  one-third of the mount-normal bin dimension, clamped to that range.
  Thickness (0.8-6.0 mm) keeps its named choices. The two free Label corners
  have a fixed ~1 mm 45-degree shave. Lettering reuses the ordinary text
  engine, sunk to a text depth that defaults to 0.6 mm for a new or missing
  Edge Mount (an explicit saved 0.4 mm design stays 0.4 mm - this default is
  Edge Mount's own and never touches the floor-label text-depth default used
  elsewhere), needing the usual minimum backing when flush. Text targets a
  12 mm cap height and only shrinks - never below 6 mm - to fit the plate;
  if it still will not fit at 6 mm, generation refuses with a plain
  explanation rather than truncating or enlarging the plate. **Flip text**
  (next to the Text field) turns the reading direction 180 degrees for
  mounting on the underside of a surface.
- **Screw Mounting** - its section-header checkbox reveals 1-4 round screw
  holes through the selected wall (default 2, arranged Horizontal or
  Vertical, default Horizontal), each paired with a larger round
  Screwdriver access passage that opens from the *opposite* wall and crosses
  the cavity to reach it - so a screwdriver can follow the screw in from the
  far side; that explanation lives as hover/title help on the checkbox
  itself rather than as permanent page text. Both holes are always round;
  there are no teardrops, countersinks or counterbores. Default screw
  diameter is 4 mm; new Screwdriver access choices are Small (6 mm),
  Default (8 mm), or Large (10 mm). Legacy exact access values reopen
  unchanged when relevant. The first (or only) hole centres 12.7 mm (1/2 in)
  below the top rim by default (**From top**); additional holes use Auto
  spacing (evenly fit, up to 20 mm apart) or an exact custom spacing. A
  pattern that cannot fit - too close to a corner, too close to the floor,
  or two access holes too close together - is refused with the reason,
  never silently shrunk, reduced or repositioned. Screw Mounting cannot
  share its mounting or opposite wall with Inside Handles; enabling both on
  conflicting walls is refused.

The plate's projection is real geometry but is not part of the bin's
nominal X/Y footprint, inventory dimensions or Space sizing/layout - those
keep using the ordinary bin size. A removable/cartridge insert is never drilled,
since it can simply be lifted out before the bin is mounted; the fused
access passage does clear any fused interior holder material blocking its
path, since that material cannot be removed. Edge Mount's own label is
independent of floor Text parts, the rim label, and Storage Box/divider labels -
none of those are migrated or replaced.

### Side Openings

**Side Openings modifies an ordinary bin; it is not an interior part.**
It is a normal **Parts & options** palette option. It cuts centered finger-access
notches through selected bin walls - built by making the normal Wavefinity
bin first, then subtracting negative cutter solids through the selected
wall(s), so the ordinary shell, cavity, wave, lock and connector geometry
never change. Default is off.

- **Shape** - Curved (a rounded finger slot) or Square (a rectangular
  notch).
- **Cutout on:** Front, Back, Left and Right are independent toggle buttons,
  not a single choice; any combination can be selected together. A new opening
  prefers Left + Right when both are legal.
- **Opening size** - Small (8 mm), Medium (10 mm, default), Large (15 mm)
  or XL (20 mm).
- **% from bottom** - defaults to 100%. It sets how far down the opening
  reaches; 100% reaches the top of the base but never cuts into it.
- **% from top** - defaults to 100%. Lowering it leaves progressively more
  material above the opening.

A wall needs to be at least **2 Wavefinity units (16 mm)** long to take a
Side Opening at all, with a 4 mm solid corner shoulder kept at each end of
the opening. That modular rule means a 2-unit wall only offers Small, a
3-unit wall offers up to Large, and a 4-unit-or-larger wall offers every
size including XL. The browser only offers sizes that fit every currently
selected side and the current Shape and percentage combination; Python
re-validates the same rule and refuses an impossible saved or imported
combination outright.

Side Openings are for **ordinary bins only** - hidden for Storage Box and Base
Trim. Lid & Stacking clamps **% from top** as needed to keep its required
bridge. Curved supported openings use a pointed supportless arch with a
minimum 45-degree underside, rather than the old fixed arch.
A rim label, an Edge Mount
mounting wall, or an Inside Grip may not share a wall with a Side Opening -
different walls are fine for all three. The scoop and other interior parts
are never globally blocked; the cutter is authoritative wherever a Side
Opening's wall intersects other body geometry, and it is re-applied to the
finished body right before export so a later fused feature can never
quietly fill an opening back in.

---

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

X and Y must be multiples of 8 mm (minimum 8); Z and wall are free. `--boxes`
takes units (`2x6`), or millimetres with an explicit suffix (`16x48mm`).

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

- **2 x 6 (16 x 48 mm)**, **4 x 6 (32 x 48 mm)** and **6 x 6 (48 x 48 mm)** boxes
- **Five identical connectors** at the locked 0.02 mm tolerance

Print the boxes open side up and the connectors cap side down; no supports either
way. The three sizes are deliberately different so you can check that mixed sizes
really do interlock and take a clip at every seam.

## Code layout

The old Tkinter desktop UI is gone. The browser, CLI, and exporters share this
layered implementation:

| File | Role | Entry point? |
|---|---|---|
| `organizer_geometry.py` | Feature-neutral booleans, extrusion, sweep, ring alignment and loft helpers. | No. |
| `organizer_engine.py` | Wavy boxes, connectors, labels, mesh validation and 3MF/STL export. It re-exports established geometry helper names for compatibility. | No. |
| `organizer_base_trim.py` | Isolated Base Trim validation, global-phase ring geometry, bed-aware splitting, section joints and export. | No. |
| `organizer_inserts/` | Item/layout model, authoritative feature registry, per-feature builders, Divider compartments, and fused/removable assembly. | No. |
| `organizer_app.py` | CLI, exporters and design persistence. Legacy palette constants are generated from the feature registry. | Yes, for CLI subcommands. |
| `wavefinity_web.py` | The local HTTP service — see [The browser service](#the-browser-service). | Yes, the default UI launch target. |
| `organizer_inventory.py` | The drawer inventory file (`Wavefinity bins.md`): parsing, legacy upgrade, merge-saves, bin logging. | No. |
| `organizer_drawer.py` | Drawer layout: grid fit, drawer report, spacer planning and export, and its `/api/drawer/*` routes. | No. |
| `organizer_pegboard.py` | Pegboard standards, size derivation, receiver layout/geometry, standard-specific adapters, and mount footprints. | No. |
| `test_organizer_app.py` | Box, connector, label, preview, CLI and export regressions. | Only via `python -m unittest`. |
| `test_organizer_inserts.py` | Items, layout, registry, primitive and insert regressions. | Only via `python -m unittest`. |
| `test_wavefinity_web.py` | Browser-service API contract, security boundary and static-file regressions. | Only via `python -m unittest`. |
| `test_drawer.py` | Inventory file, one-placement layout, report and spacer regressions. | Only via `python -m unittest`. |
| `test_pegboard.py` | Pegboard sizing, persistence, mount geometry and placement regressions. | Only via `python -m unittest`. |
| `run_tests.py` | Compact test runner: one pass/fail summary line, full tracebacks only on failure. See [Testing rules](#testing-rules). | Yes — `python3 run_tests.py [module ...]`. |

`web/index.html`, `web/styles.css`, `web/feature-icons.js` and `web/app.js` are
plain dependency-free frontend files with no build step. Icon artwork lives in
`feature-icons.js`; the feature registry supplies stable icon identifiers.
`app.js` holds the stateful editor, preview coordination, and typed-Space
ordinary-bin autosave and status handoffs. All printable geometry still comes
from the Python service. Drawer layout mode lives in `web/drawer-model.js`
(data, saving, undo), `web/drawer-view.js` (the canvas) and
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
| `Launch_Organizer_UI.vbs` | normal windowless application launcher |
| `Launch_Organizer_UI.bat` | bootstrapper and diagnostic launcher; starts the local service windowlessly |
| `generated/WAVY_SAMPLE_SET.3mf` | regenerable local sample print plate; intentionally gitignored |

## Working on this

This project is developed locally, mostly by prompting an LLM. GitHub is a
**backup, public contribution point, and record of what changed**. Outside
contributions use pull requests; the repository owner gives final approval.

Project moderators are **@happydadto5** and trusted collaborator
**@xdkaplan (adkaplan)**. The protected `main` rules keep @happydadto5 as the
final approval authority.

**After completing an implementation, commit all changes and push them to
GitHub before reporting that the work is finished.** For Help Code, push the
assigned `fixN` branch; explicitly non-Help-Code work follows the local
workflow below.

**When given an implementation plan, review it first.** Understand what it
does and confirm that the execution is sound before beginning. If it is sound,
implement the plan and commit the completed code.

**One prompt may become one cohesive commit.** Keep all code, tests, and
documentation needed to complete that prompt together; do not split a single
request into artificial commits just to make the history look smaller. When a
prompt is complete, commit and push it so the history has a clear entry and the
work is backed up. For a Help Code fix, verification is exactly what the active
cloud fix requires. For explicitly non-Help-Code work, the generic Class A/B/C
testing guidance above applies. Separate unrelated prompts into separate
commits when practical. No feature branches or pull requests are needed for
explicitly non-Help-Code local work; Help Code always uses its assigned `fixN`
branch and outside completion review:

```powershell
git add -A
git commit -m "short description of what changed"
git push
```

Add a dated entry to [changelog.md](changelog.md) for user-facing changes.
Do NOT log to `TESTING.md` — that file is retired and archived.

For explicitly non-Help-Code work, **do not be obsessed with testing** (see the
proportional testing policy near the top). Short version: small/local work
usually needs no tests; bounded runtime/integration work may use a few
high-signal checks; broad shared-contract work and repeatedly corrected fixes
require targeted verification. Never run the full suite or browser for routine
work merely for reassurance. Help Code testing follows the active cloud fix
only.

**Write commit messages that say why.** The history is the record. A message
that explains the reasoning is worth more here than a tidy branch structure.

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

### If more than one person is working in the repo

For explicitly non-Help-Code work, everyone commits to `main`, so the only rule
that matters is: **pull before you start, push as soon as you are done.** Help
Code work stays on its assigned `fixN` branch and follows the outside review
workflow above.

```powershell
git pull --rebase        # before starting
git push                 # right after committing
```

Long-lived uncommitted work is the thing to avoid — two sessions editing
`organizer_engine.py` for a day will conflict, and geometry conflicts are
unpleasant to resolve by hand. Small, frequent, pushed commits keep that from
happening.

If a non-Help-Code push is rejected because someone else pushed first, `git pull
--rebase` then push again. If that surfaces a real conflict, resolve it, inspect
the merged diff, and continue under the same Class A/B/C testing rule. Do not
automatically run the full suite just because a rebase occurred. Help Code
corrections continue on the assigned `fixN` branch under the active cloud fix.

Also worth knowing before editing: the **traps** section below, and that
`.venv/`, `__pycache__/` and `generated/` are gitignored and should stay that
way.

---

# Design notes

Everything from here down is for whoever changes the geometry next. Several of
these numbers look arbitrary and are not.

## The settled numbers

| | Value | Notes |
|---|---:|---|
| Wave cycle | **4.0** | 2 out, 2 back |
| Wave amplitude | **0.4** | 0.8 peak to peak |
| Wave shape | **odd sine** about each wall centre | load-bearing |
| Mating gap | **0.25** | between two neighbouring walls |
| Size grid | **8.0** | box X and Y must be whole multiples |
| Minimum box | **8.0** | one grid step |
| Maximum requested X/Y | **350.0** | the 8 mm grid makes 344 mm the largest valid size |
| One "unit" | **8.0** | so 1, 2, 3 units = 8, 16, 24 mm |
| Smallest box that clips on both sides | **16.0** | derived, not hard-coded |
| Wall | **0.8** | independent of the floor |
| Base thickness | **0.6** default, **0.4** minimum | shown under Advanced in Build your bin |
| Flat wall band | **0–1.0**, default 0 | height above the floor, not a fill depth |
| Corner fillet | **0.6** | walls stop `CORNER_INSET` = 1.0 short of the nominal corner |
| **Connector tolerance** | **0.02** | **locked** by a physical print |
| **Connector length** | **12.0** | **locked** |
| **Connector height** | **9.6** | **locked**; cap 1.2, arms 1.0 thick |
| Connector position step | **4.0** | one whole wave; half a wave wants a mirrored part |
| Base Trim field range | **8–1200** | whole 8 mm units on each axis |
| Base Trim unit | **8.0** | enclosed field step |
| Base Trim size presets | **Small 6.5, Medium 7.5 (default), Large 10, XL 15, XXL 20** | square width = height |
| Base Trim width / height range / step | **4–20 / 0.5** | millimetres; presets are the normal path, legacy values still load |
| Base Trim default bed / effective area | **256 × 256 / 236 × 236** | 10 mm is reserved at each edge |
| Base Trim joint length / clearance | **0.55 × min(width, height) / 0.20** | one scaled drop-in dovetail; only used when the ring must split |
| Base Trim split-joint structural skin | **1.0 mm minimum** | between cleared joint and each physical face |
| Base Trim outer taper | **1.0 per side** | outside only |
| Mated wall clearance | **0.21** | 0.25 across the seam, measured perpendicular |
| Lock bump | **0.35** proud, 1.0 tall, **1.2** long | on every wave extremum, so every **2.0** |
| Bump corner clearance | **2.0** | keeps two walls' bumps apart at a corner |
| Bump band | top **4.0** below the rim | |
| Text letters | **15.0** ideal, **5.0** auto minimum, **5.0** floor | sunk **0.4**; a zone sizes it, a hand-set height is capped by that zone |
| Rim label | **5.0** target letters, **7.0** ledge | auto-shrinks; warns below 4.0 mm; 45-degree underside |
| Scoop | **60%** of usable wall height | full usable width at front |

Connector tolerance, length and height were chosen from a **printed five-clip fit
plate** — the leftmost clip, read back from that 3MF as `side_clip_tol_0p020`.

## Already tried and rejected

Do not re-derive these.

| Tried | Outcome |
|---|---|
| Four-box corner connector | Removed. Over-constrained four independently printed corners; also produced unprintable slivers along the seams. |
| Shortening the connector to make it reversible | Provably useless — it is a parity clash, not a size problem. |
| Bumps on alternate troughs only | Locked one side of a mixed-size seam, and blocked reversibility. |
| Even (cosine) wave | Replaced with odd sine so boxes can be turned round. |
| Raised (proud) floor labels *as the only option* | Replaced with a sunk inlay by default; **Stand proud** is now a per-text choice. |
| One label per bin, owned by the design | Replaced by `text` interior parts, any number of them. One label meant no answer to "which compartment is this size for", and the label already had bespoke move/rotate/resize code duplicating the feature editor. |
| Reading "flat inside walls" as a horizontal fill depth | Wrong. It is a **height**: a flat-walled band rising from the floor, with the wave unchanged above it. |
| 16 mm "bin" as the unit | Replaced with 8 mm so whole numbers reach 8/16/24/32/40/48. |
| Success dialog after generating | Removed; the status line reports instead. Failures still get a dialog. |
| Connector-fit line in the size readout | Removed. |
| Native `.f3d` export | Impossible outside Fusion. A build script was written and is now stale — it predates the 4 mm wave and the removal of the corner connector. |

## Three claims this project got wrong

Both were stated as done and later found false. Tests now exist for each.

1. **"A box is the same whichever way round you turn it."** False while the wave
   was even. The test behind it checked that a *wall* is symmetric about its own
   midpoint, which is a different property from the whole box being invariant
   under rotation. Measured: a box turned 180 degrees clashed with its neighbour
   by **159 mm³** and overlapped its own footprint by only **54%**. Fixed by
   making the wave odd.
2. **A readout line naming which sides take a connector.** Documented as
   working; the edit had silently failed to apply and the line never existed.
   The line was later removed at the user's request anyway, but a test now
   asserts the readout and preview actually have content.
3. **"One connector part fits every seam, at any half-wave position."** False by
   a factor of two. The wave inverts every half cycle, so the clip a half-wave
   along is the printed one **mirrored** — identical volume, 58% shape overlap,
   and not obtainable by turning a part over. Measured: the real part slid 2 mm
   along a seam jams by **48 mm3**. The tests that looked universal all
   regenerated the clip for the position they were checking, and every fixed
   position they used happened to land on a whole wave. Positions are now whole
   multiples of `WAVE_LENGTH`, and
   `test_the_printed_clip_still_seats_when_slid_to_another_lattice_step` prints
   one part and slides it, which is what the claim was actually about.

## Traps

- **Fingerprints.** `test_organizer_app.py` pins STL hashes for the default box
  and connector. Any geometry change moves them; re-pin deliberately, never by
  reflex.
- **3MF hashes are not reproducible.** `lib3mf` writes a fresh build UUID each
  export, so identical code gives a different `.3mf` hash every run. The STL
  fingerprints are the real regression guard.
- **`mesh_report` demands a single component.** Right for boxes and connectors,
  wrong for labels — a label is legitimately one solid per letter, so it uses
  `label_mesh_report` and `validate_3mf(..., multipart=(...))`.
- **A non-empty `multipart` also means "assembly".** `export_text_body_3mf`
  groups the body and every text into one components object with a single build
  item, so `validate_3mf` then expects `expected_objects + 1` strict objects and
  1 build item, and reports `filaments`. A plain `export_mesh` file is still
  N objects / N build items. Bambu opens the assembly with no multi-part prompt;
  the filament split lives in `Metadata/model_settings.config`, not the mesh.
- **Glyph contours arrive unnested.** Ring-containment depth decides shell from
  hole, or every `O` fills in.
- **Label sizes are cap height, not font size.** A 10 mm font size gives 7.29 mm
  letters in DejaVu Sans; everything converts through the font's measured ratio.
- **Bumps on adjacent walls can collide at a corner.** `LOCK_CORNER_CLEAR` = 2.0
  exists for that; it broke a 20x40 box's boolean before it was added.
- **The preview needs back-face culling, not just a depth sort.** From above, the
  far outside wall's top edge is genuinely nearer the camera than the floor, so
  painting order alone draws it over the interior. Label faces are pinned just in
  front of the floor's depth rather than given their own, or far-side letters
  sort behind the floor and vanish. The 76-degree elevation was calculated: for a
  40 mm bin the floor only clears the near rim past about 88 degrees, so a low
  dramatic angle hides the floor and the label with it.
- **Cartridge cells are anchored at the cartridge corner, not world zero.** An
  even cell count puts legal feature centres half a cell from zero; snapping the
  centre itself creates layouts that look aligned but are not reusable.
- **Text is built by `build_features` but kept out of its returned solids.** A
  recessed inlay has to be *subtracted* from the body, not added to it, so the
  builder runs (its errors surface with every other interior part's) while the
  exporter collects the solids separately through `build_texts`. Pass
  `include_text=True` to get them, as the preview does.
- **Lettering flush with the floor needs a painter *layer*, not just a depth.**
  Text sunk into the floor shares the floor's face exactly, so pinning it to the
  floor's sort depth leaves only the layer to break the tie — and an interior
  part arrives on layer 0, under the floor's own layer 1. Without lifting it the
  lettering is painted over and renders nothing at all. No Python test can see
  this; it was found by reading pixels out of the real canvas.
- **Option types come from feature metadata.** `OptionDefinition.value_type`
  drives browser/API coercion for numbers, whole numbers, booleans, enums,
  strings and nested JSON. Do not maintain a second key-based type list.
- **A tall feature at the wall can block a connector even when the 2D zones are
  valid.** Builders check the 2 mm edge strip against the connector-arm bottom;
  the default divider stops exactly at that safe height.
- **The `.venv` here is the only Python that works.** Use
  `.venv\Scripts\python.exe`, not the system interpreter.

## Verified behaviour

Measured and regression-tested; run the suite for the current exact count.

**Mating and the grid**
- Boxes one pitch apart: **0.0 mm³** interference, constant 0.25 mm clearance
- Off-grid sizes against a different size: **>10 mm³** interference — rejected
- One connector across 4 box sizes × 4 positions: **100.000%** volume match, so
  it really is one universal part

**Turning things round**
- Connector spun 180 degrees: seats at **<0.001 mm³**, locks at **>0.1 mm³** —
  identical to unspun, on 32x32, 16x48, 24x48 at +4 and 48x48x24 at −6
- Box spun 180 degrees: **100.0%** self-overlap, **0.0 mm³** against an unturned
  neighbour
- Before the fix: connector **48.5 mm³**, box **159.0 mm³**

**Lock**
- Seated: **0.0 mm³**. At 0.5 mm lift: **1.70 mm³**. Rose from 1.41 when bumps
  went to every extremum — shorter bumps, twice as many under a clip

**Flat wall band**
- Cavity cross-section is the straight profile (**844.47 mm²**) throughout the
  band and the wavy one (**892.01 mm²**) immediately above it, on a 32x32x40
  box with a 1 mm band
- The band's height tracks the setting continuously; it is not on/off
- The straight profile is fully contained by the wavy one, so the band cannot
  cut into the wall
- Outer profile area identical to 6 places, so grid and mating are unaffected
- Connector still seats and locks with the band at 0, 0.5 and 1.0

**Text and labels**
- Pocket volume removed == inlay volume; the two intersect by **<0.01 mm³**;
  union restores the plain box exactly. Checked on 48x48, 16x48 and 24x40
- Strict 3MF, **zero warnings**; one assembly object, one build item, the body
  and every piece of lettering as named parts — verified with three floor texts
  and with a rim label alongside floor text. `model_settings.config` opens the
  body on filament 1 and all lettering on filament 2
- A raised text takes nothing out of the body; a recessed one is its exact
  complement
- An auto-placed text moves around holders, reserved scoop/ledge space and other
  auto texts with a 1 mm clearance; the same placement is used by the 2D editor,
  3D preview, mesh pocket and export report
- Neighbours are judged on the lettering's **ink**, not the box it was dragged
  out to, so a short word in a wide box does not push a holder away

**Insert layouts**
- Nine registered builders: cradle, Snug Holder, bore, center post, divider,
  pocket, slot rack, steps and text
- Fused outputs remain one watertight solid; fitted and cartridge inserts clear
  the bin walls and stand on their own 0.6 mm print-flat plate
- Normal moves and resizes snap to 1 mm. Cartridge coordinates and sizes are
  validated on 8 mm cell edges and survive a JSON round trip
- All three production modes were exported as strict, zero-warning 3MF files;
  a lettered output is a one-build-item assembly of the body and every piece of
  lettering as named parts, and two texts reading the same thing stay distinct

**Usable inside**
- The exact reported rectangle fits; **+0.3 mm does not**

## Where it stands

Working and verified: box, connector, lock, insert registry and primitives,
fused/removable/cartridge exports, multi-label text parts, flat-inside fill,
interactive 3D preview, 2D drag editor, saved layouts, CLI, UI and sample plate.

Physically printed so far: **test pieces only** — the five-clip tolerance plate
that set the connector fit. That plate predates the 4 mm wave, so **nothing in
the current design is confirmed in plastic yet.**

Remaining physical next steps:

- Print `WAVY_SAMPLE_SET.3mf` and check the lock feel, the label colour change,
  and that a connector really does drop on either way round.
- Nothing enforces that all boxes in a drawer share a `flat_inside` value; a
  connector made for one fill depth is only guaranteed against boxes with the
  same fill.
