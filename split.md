# Plan: Split organizer_inserts.py into Multiple Files

## Why

[organizer_inserts.py](file:///c:/Users/happy/Projects/Wavefinity/organizer_inserts.py) is **3,038 lines** and growing.
Working on it in multiple AI sessions at the same time is risky — sessions can overwrite each other or get confused by the sheer size.
Splitting it into focused files lets each session work on exactly the piece it needs, without touching anything else.

---

## Proposed File Structure

The current one file becomes **one shared foundation file** + **one file per insert type** + **one master file** that ties everything together.

```
organizer_inserts/
│
├── __init__.py          ← NEW master file (replaces the old single file)
│
├── _core.py             ← Shared stuff every insert type needs
│
├── _cradle.py           ← Cradle insert
├── _nest.py             ← Nest (photo/phone nest) insert
├── _bore.py             ← Bore (drill-hole) insert
├── _post.py             ← Post insert
├── _divider.py          ← Divider insert
├── _pocket.py           ← Pocket insert
├── _slot.py             ← Slot insert
├── _steps.py            ← Steps insert
├── _scoop.py            ← Scoop insert
└── _text.py             ← Text label insert
```

---

## What Goes Where

### `_core.py` — Shared Foundation (~lines 1–560)
Everything every insert type depends on:
- All the **constants** (wall thicknesses, clearances, bit sizes, etc.)
- The **data classes** — `Segment`, `Item`, `Zone`, `Feature`, `Layout`
- The **@feature** and **@defaults** decorator system that registers insert types
- Layout helpers — save/load, to/from dict
- Zone helpers — snap, cartridge zone, layout zone

### `_cradle.py` — Cradle Insert (~lines 561–836)
Holds lying-down tools in a trough.

### `_nest.py` — Nest Insert (~lines 837–1163)
Holds phones, cameras, or similar flat objects upright with a contoured pocket.

### `_bore.py` — Bore Insert (~lines 1164–1342)
Drill-hole style holder — hex bits, round bits, etc.

### `_post.py` — Post Insert (~lines 1343–1407)
A simple post/peg holder.

### `_divider.py` — Divider Insert (~lines 1408–1879)
Walls and ramps that divide a bin into sections.

### `_pocket.py` — Pocket Insert (~lines 1880–1984)
Open rectangular pockets.

### `_slot.py` — Slot Insert (~lines 1985–2060)
Narrow slot holders.

### `_steps.py` — Steps Insert (~lines 2061–2129)
Stepped risers inside a bin.

### `_scoop.py` — Scoop Insert (~lines 2130–2225)
Wavy scoop-style trough.

### `_text.py` — Text Label Insert (~lines 2226–2439)
Raised or recessed text labels printed into the insert.

### `__init__.py` — Master File (~lines 2440–3038)
- Imports everything from `_core.py` and all the insert files
- Contains the top-level assembly functions — `build_features`, `build_texts`, `make_insert_plate`, `make_fitted_insert`, `make_cartridge_insert`, `make_fused_box`, etc.
- Re-exports everything so the rest of the app (`organizer_app.py`, `wavefinity_web.py`, tests) keeps working with **zero changes** — they still do `from organizer_inserts import ...` and it just works.

---

## What Changes for the Rest of the App

**Nothing visible.** The outside world still imports from `organizer_inserts` exactly as before.
Only the internals are reorganized.

---

## Benefits

| Benefit | Detail |
|---|---|
| Smaller files | Each file is ~100–250 lines — easy to read and edit |
| Parallel AI sessions | Each session can own one insert type file safely |
| Easier to find things | Looking for Nest code? Open `_nest.py`. Done. |
| Safer changes | A bug in `_bore.py` can't accidentally break `_cradle.py` |
| Easier to add new types | New insert = new file, register with `@feature`, done |

---

## Risks

| Risk | Level | Notes |
|---|---|---|
| Import chain breaks | Medium | Must import `_core.py` before insert files, and insert files before `__init__.py` |
| Circular imports | Low | As long as insert files don't import each other, this won't happen |
| Tests break | Low | Tests import from `organizer_inserts` — if `__init__.py` re-exports correctly, tests need no changes |

---

## Order of Work (when ready to execute)

1. Create the new folder structure
2. Move `_core.py` content first (shared by everything)
3. Move each insert type one at a time, running tests after each
4. Wire up `__init__.py` to re-export everything
5. Run full test suite — fix any broken import paths
6. Commit and push

---

> [!NOTE]
> No code changes are made in this document. This is a planning artifact only.
