# Storage Drawers end-to-end audit (2026-10-12)

Audience: reviewer/coder LLMs. Scope: Storage Drawers cabinet + bins in it, from
Create Space → bin design → layout → Save/Print → assembly guide.
Method: code read of `organizer_storage/*`, `organizer_drawer/_report.py`,
`web/storage-drawers*.js`, `web/spaces/14-drawers-cabinet.js`,
`web/app/01-runtime-state.js`, `web/storage-drawers-guide.html`; plus real-mesh
interference runs (trimesh/manifold) on an assembled 24×20-unit, 3-drawer
cabinet at fit 0.30 / 0.40 and 0.60 (Open + solid rear + keyholes + stacking).
Drawers were tested nominal, resting (−fit Z), lifted (+fit Z), shifted ±fit X,
yawed, and pulled out 5–150 mm.

Baseline good news: every component builds watertight; nominal assembly has
no interference (only ~0.005 mm³ numeric contact); drawers clear each other in
all tested states; closed-position stop lug works; stack pegs press-fit as
designed.

Status keys: CONFIRMED = reproduced by geometry or exact code path.
PLAUSIBLE = derived from geometry, needs a physical print to settle.

---

## HIGH

### H1 — New bins default to the full usable height → 0.0 mm clearance to the drawer above (CONFIRMED)
- `organizer_storage/drawer_geometry.py:370` usable = `height_mm + fit` = exact
  gap from drawer floor to the underside of the drawer/top above (both resting).
- `web/app/01-runtime-state.js:851-856` New Bin for `storage_drawers` sets
  `box.z = Math.floor(space.z)`. Default Standard: usable 40.0 → bin 40 mm →
  clearance 0.0. Loose: 0.2 mm. Tight: 0.9 mm.
- `organizer_drawer/_report.py:364-366` `too_tall` fires only when
  `h > cap + 1e-6`, so a zero-clearance bin is reported OK.
- Contrast: Drawer Space kind uses `space.z - 3` "so the drawer closes"
  (same file, line 828). Storage Drawers has no equivalent margin.
- Effect: any Z over-size (first-layer squish, top-surface ironing, label
  emboss, stacking lip tolerances) makes the bin drag on the drawer above or
  jam the drawer. First-print users will hit this.
- Fix direction: reserve a running clearance (≥1–2 mm) once, in one owner
  (either usable height published to bins, or New Bin default + report check
  with margin). Keep README/guide wording consistent.

### H2 — 0.25 mm square step in every drawer runner's path (CONFIRMED)
- `drawer_geometry.py:682-684` stop-root box spans X `inner-0.2 … body_edge-0.2`
  and Z up to `floor+0.25-fit`, i.e. 0.25 mm above the ledge top. Its X range
  fully covers the drawer runner (`main_a … main_b`, lines 841-844), not just
  the catch bump (`stop_x0 … stop_x1`).
- Geometry: resting drawer runner ∩ side = 1.0 × 8.0 × 0.25 mm (2.0 mm³) at
  Y 11.8–19.8, every drawer, every fit, Full and Open, at all pull distances.
- The step has a vertical front face; the runner's leading (rear) end is
  square (lead-in chamfer at lines 131-134 is in plan only, not in Z).
  Insertion must lift the drawer over a hard 0.25 mm edge; when closed the
  drawer rides on an 8 mm pad 0.25 mm above the ledge, so it rocks/pivots.
- The code comment at 685-686 ("catch rises only 0.25 mm … less than every
  fit") describes the bump, not this pad.
- Fix direction: clip the root to the bump footprint (`stop_x0 … stop_x1`) or
  keep root top ≤ ledge top; if a pad must stay, give it Z ramps both ends.

### H3 — Runner/ledge bearing is 0.4 mm and the drawer has no rear lateral guide (PLAUSIBLE, high impact)
- Bearing overlap per side = `0.8 - fit` (+makeup) → 0.40 mm (Std/Loose),
  0.50 (Tight). Comment at `drawer_geometry.py:834-839`.
- Lateral location: when closed, fascia reveal + fascia back face; once pulled
  out, only the two 8 mm catch bumps near the cabinet front (0.2 mm
  clearance). Geometry: pure X shift first meets the rail-root face at ≈2.0 mm.
- Yaw about the bumps is effectively free (bumps are 8 mm long). ~0.003 rad
  yaw moves the drawer rear >0.4 mm → the opposite runner leaves its ledge at
  the rear. Middle/top drawers then drop ~fit onto the drawer below; the
  bottom drawer drops ≈4 mm (lift above base).
- Fix direction: add a continuous lateral guide along the rail (e.g. runner
  outer face vs rail root at ≈fit clearance), and/or raise bearing to ≥1.2 mm.
  Verify with a printed 2-drawer test before claiming.

### H4 — Drawer wall can drop to 0.28 mm at wave crests (CONFIRMED math)
- Drawer cavity = `wavy_rect_cavity(field/2 + 0.125, …)`; measured extent is
  field/2 + 0.524 mm. Outer box is field/2 + `drawer_wall`.
- Crest thickness = `drawer_wall − 0.524`. Presets offered: 0.8 → 0.276 mm,
  1.2 → 0.676 mm. Backend floor is 0.4 → negative (wall breaks through).
- `_cosmetic_side_shell` only thickens side walls for Y 8 … field_y−8 and
  Z floor+3.2+fit … floor+height−2. Rear wall, the 8 mm side ends, the bottom
  band and top 2 mm stay thin.
- Fix direction: minimum drawer wall ≥ 0.525 + 2 extrusion widths (≈1.4–1.6),
  or hide 0.8/1.2 for `drawer_wall_mm`, or thicken all walls like the shell.

---

## MEDIUM

### M1 — Rear panel has zero vertical clearance; the Top slides across its top edge (CONFIRMED)
- Rear panel spans Z `base/2 … outer_z − top` (lines 736-744); its bottom tab
  rests on the base pocket floor at `base/2` (lines 598-602); top plate
  underside is `outer_z − top`. Gap = 0.0 both ends.
- Assembly order is Rear before Top, and the Top slides ~body depth over the
  rear edge. Any +0.1 mm (rear printed flat, height lies in XY) → scraping or
  no seat. Fix: lower rear top edge 0.3–0.4 mm.

### M2 — Top detent interferes along almost the whole slide (CONFIRMED by code)
- Bump on each side's top dovetail stands 0.2 mm into the groove roof
  (`SD_TOP_DETENT_INTERFERENCE_MM`); relief pocket exists only at the seated
  position (lines 586-596, 699-705). Top enters from the back, so the bump
  scrapes ~full body depth on both rails before it clicks.
- Guide says "Push firmly"; with a 1.6 mm top this may bow the plate, shave the
  bump, or need real force. Fix: open relief channel from the entry end up to
  a short ramp before the seat.

### M3 — Wall-mount keyholes: screw-head clearance and missing instructions (PLAUSIBLE + CONFIRMED gap)
- Head hole and slot go through the 4 mm reinforcement (lines 211-232), so the
  screw head ends up inside the cabinet. Space between reinforcement face and
  drawer back = `fit + track_reach − 4` = 2.0 mm at Standard. Most pan/round
  heads are 2.5–3.5 mm tall → drawers hit screws or will not close.
- Load path: side grooves are open at the top; the hung cabinet is carried by
  the top plate resting on the rear panel top edge (see M1) + top dovetails.
- `web/storage-drawers-guide.html` never mentions wall mounting: no screw
  size (shank < 5.2, head < 10), stand-off, anchors, or that keyholes need
  top-drawer removal. Fix: model a head pocket or enforce head clearance,
  and add a guide section.

### M4 — Cosmetic side wave bulge runs into the upper level's stop root (CONFIRMED, small)
- Shell crest stands up to 0.52 mm outside the drawer wall plane up to
  `floor+height−2`; the next level's stop root/bump reaches to
  `body_edge − 0.2` from `floor+height−2.4`. Lifting a closed middle drawer
  by fit gives contacts (0.12 mm³); lateral shift at rest also contacts.
- Fix: end the shell ≥ (2.4 + fit + 0.3) mm below the rim, or clip its outward
  bulge to the wall plane in that band.

### M5 — Print flow: all parts dumped into one slicer session, no plate plan (CONFIRMED)
- `bambu_handoff.py` opens files with no `--arrange`; Print Cabinet sends ~8+
  large parts (+4 separate Stack Peg files) together. Default cabinet needs
  several plates. Guide section 5 gives no plate grouping, count, or order.
- Suggest: guide table of plates; optionally merge the 4 pegs into one file.

---

## LOW

- **L1 UI bug (CONFIRMED):** `web/spaces/14-drawers-cabinet.js:445,469` use
  `"\\n"` in Print Cabinet + Bins toast → literal `\n` shown. Sibling path
  (line 507) uses `"\n"`.
- **L2 Tight fit margin:** from rest the catch wing climbs `fit + 0.25` within
  `2·fit` play → 0.05 mm spare at Tight. Guide warns; the form only says so in a
  hover `title`. Consider hiding Tight or showing inline text.
- **L3 Runner web:** drawer load hangs on a 0.6 mm (Z +1.0…+1.6) web to a 1.0 mm
  runner (lines 841-851) ≈ 3 layers. Check with a loaded drawer.
- **L4 No pull-out stop:** the catch is a 0.25 mm detent; a loaded drawer pulls
  fully out. Guide should say so.
- **L5 Stacking:** pegs only align for identical X/Y cabinets (centres from
  outer size); guide does not say. 0.08 mm radial press fit may be too tight
  on many printers.
- **L6 First print advice missing:** guide should recommend printing one
  drawer + one short side/base test before the whole set (Drawer fit change
  forces reprinting every part, per guide section 4).

---

## Suggested fix order
H1 → H2 → H4 → M1 → M2 → H3 (needs design + physical test) → M3 → rest.
Add a geometry regression that assembles the cabinet and checks
resting/lifted/±fit/pulled states (the method above) so H2/M1/M4 cannot return.
