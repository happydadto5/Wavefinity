# Gridfinity Stage 1 specification — v1.0

Recorded 2026-11-12 against Wavefinity `cb26576bdd74d037bd12fcbc64bf45bbd6a7def4`. Dimensions are millimetres. This is a design reference, not a claim that Wavefinity already makes Gridfinity or that a printed part fits. The community [design reference](https://gridfinity.xyz/specification/) calls itself a draft. This document fixes the following named profiles for subsequent Stage 1 design; physical confirmation remains outstanding.

## 1. 42 mm profile

Reference profile: [Gridfinity Builder specification](https://gridfinity-docs.securedev.codes/reference/specification.html), as published on 2026-11-12, which identifies its community and Gridfinity Rebuilt sources. Coordinates below are Z up. Its particular trimmed rim is selected here; implementations with other crown finishes need separate confirmation.

| Interface | Nominal geometry | Source |
|---|---|---|
| Grid and height | 42 × 42 pitch; 7 per height unit, measured from foot bottom to nominal rim, foot included. Whole bin XY = 42 × count − 0.5, not minus 0.5 per cell; 1×1 41.5 square, 2×3 83.5 × 125.5. | [Core dimensions and formula](https://gridfinity-docs.securedev.codes/reference/specification.html#core-dimensions) |
| Foot | Each cell at 42 pitch: z 0–0.8, 45° widening 35.6 to 37.2; z 0.8–2.6 vertical at 37.2; z 2.6–4.75, 45° widening to 41.5. Concentric corner radius 0.8 at bottom, 1.6 at straight band, 3.75 at top. | [Z-profile base](https://gridfinity-docs.securedev.codes/reference/specification.html#z-profile-base) |
| Baseplate socket | 5 thick, opening widths 36.3 at z 0–0.35, 37.7 at z 1.05–2.85, 42 at z 5; chamfer / straight / chamfer heights 0.7 / 1.8 / 2.15, over **0.35 vertical relief**. Plate is 42 × count, outer corner R4. Foot datum at z 0.35. | [Baseplate socket](https://gridfinity-docs.securedev.codes/reference/specification.html#baseplate-socket) |
| Stacking rim | Female opening at nominal rim z 0: width 36.3/R1.15; z 0.7 and 2.5: 37.7/R1.85; z 3.8: 40.3/R3.15. The theoretical 4.4 tip is 41.5/R3.75; this reference trims 0.6 from it. Straight-band clearance 0.25 per side; chamfer clearance 0.35 at nominal datum, allowing 0.35 descent onto seat. | [Stacking lip](https://gridfinity-docs.securedev.codes/reference/specification.html#stacking-lip) |
| Stacking grid lid | Its upper receiving grid needs the same 42 pitch and socket profile, with its own lower closure interface independently specified and confirmed. The published reference above specifies the socket, not a universal lid thickness, latch, or lower plug. Do not infer those dimensions or treat a flat lid as a grid lid. | [Baseplate socket](https://gridfinity-docs.securedev.codes/reference/specification.html#baseplate-socket) |

## 2. 21 mm reference

The selected community implementation is [Will Adams, Gridfinity-2, `Gridfinity_2.scad`](https://github.com/WillAdams/Gridfinity-2/blob/main/Gridfinity_2.scad), source as displayed 2026-11-12. Its `makebase` and `makerecess` define the reference; its generated cup and baseplate place them at 21 pitch. This is a distinct 21 mm interface, not a universal half-grid standard or proof of interchangeability with every 42 mm plate. The source page was readable through the public indexed view, but direct raw download returned HTTP 404; obtain and pin an accessible copy before using it as a reproducible fabrication reference.

- Foot: four corner centres at (±6.5, ±6.5); radii 0.8→1.6 over z 0→0.8, 1.6 through z 2.6, then 1.6→3.75 through z 4.75. Thus widths 14.6, 16.2, 20.5; body R3.75 and 20.5 for 1×1. Source: [`makebase`](https://github.com/WillAdams/Gridfinity-2/blob/main/Gridfinity_2.scad).
- Pocket: same centres; lower cutter z −0.25→0.8, radius 0.8→1.85; straight z 0.8→2.6 R1.85; upper z 2.6→4.75 radius 1.85→4.1. Widths at z 0.8, 2.6 and 4.75 are 16.7, 16.7 and 21.2 respectively. The source plate is 4.7 high, so the actual cut is clipped at its top. [Source](https://github.com/WillAdams/Gridfinity-2/blob/main/Gridfinity_2.scad).
- Clearance derived at matching Z: 0.25 per side in the straight band; lower band 0.25 per side at z 0–0.8; upper band grows from 0.25 to 0.35 per side at z 4.75. This reference uses a −0.25 cutter extension, not the 42 mm reference's 0.35 vertical relief. Confirm the actual seating datum and plate clipping in plastic. The cup's top cutter is a separate construction and must not be silently equated with its plate pocket. [Source](https://github.com/WillAdams/Gridfinity-2/blob/main/Gridfinity_2.scad).

## 3. Physical confirmation gates

Before a later stage promises fit, confirm on the intended printer, material and slicer: (confirm) pitch and accumulated spacing; 0.5 total perimeter gap and corner radii; foot and socket widths, slopes and depths at each transition; 0.25 side and 0.35 chamfer clearances; 42 socket's 0.35 vertical relief and seated height; 21 pocket's cutter extension, top clipping and seated height; insertion, removal and wobble; rim crown and stack height; lid plug, grid spacing and closure clearance; elephant-foot, shrinkage, warping and orientation effects; magnet/screw fit if offered. Record machine, material, slicer settings, measurements and pass/fail for every pairing. Nominal geometry is not physical evidence.

## 4. Reference parts and compatibility matrix

Use separately sourced/generated reference bin and baseplate for each pitch, 1×1 and 2×3, plus a stackable bin and grid lid for each footprint. Preserve source revision, generation parameters and files with the results. Compare Wavefinity foot into reference socket and reference foot into Wavefinity socket; also Wavefinity on reference rim/lid and reference on Wavefinity rim/lid. Check all rotations and seated height. Every cell below is **not yet printed / not confirmed**; no third-party compatibility is asserted.

| Pitch | Footprint | Wavefinity above reference | Reference above Wavefinity |
|---|---|---|---|
| 42 | 1×1 | plate, rim and grid lid: pending | socket, rim and grid lid: pending |
| 42 | 2×3 | plate, rim and grid lid: pending | socket, rim and grid lid: pending |
| 21 | 1×1 | reference plate, rim and grid lid: pending | socket, rim and grid lid: pending |
| 21 | 2×3 | reference plate, rim and grid lid: pending | socket, rim and grid lid: pending |

The selected 21 source supplies cup and plate, not an independently specified grid lid; obtain a named matching third-party lid or record that pairing as unavailable, not passed. Cross-pitch mating is outside this matrix and is not assumed.

## 5. Shipping defaults

Nearest equivalents below are nominal whole pitch lengths, rounded to nearest positive whole cell (ties shown both); they are comparisons, not proposed defaults or outside dimensions. Height uses the 7 mm unit rather than XY pitch.

| Setting and source | Shipping value | Nearest 42 | Nearest 21 |
|---|---:|---:|---:|
| Engine `BoxSpec.x`, `.y`, `organizer_engine/_specs.py:808` | 21 × 21 | 42 × 42 (0 is not a bin) | 21 × 21 |
| Browser `default_design`, `wavefinity_web_impl/_runtime.py:363` | 14 × 42 | 42 × 42 | 21 × 42 |
| Both Z, same sources | 40 | 42 (6 height units) | 42 (6 height units) |
| Engine wall and base, `_specs.py` `DEFAULT_WALL`, `DEFAULT_BASE_THICKNESS` | 0.8 each | not applicable | not applicable |
| Engine XY grid, `_specs.py` `GRID_PITCH` | 7 | 42 = 6 current units | 21 = 3 current units |
| Stack / lid, `_specs.py` `StackSpec`, `LidSpec` | none / disabled | not applicable | not applicable |

Per-Space saved bin defaults can override the browser starter; see `README.md` Keep Defaults and `wavefinity_web.py` catalog. The engine enforces X/Y 7–350 in whole 7 mm units (`BoxSpec.__post_init__`); Z is not an XY pitch. Wavefinity's nominal XY is not the Gridfinity outer-width formula.

## 6. Entry and generation paths

| Entry | Current path and boundary |
|---|---|
| New browser Designer bin | `wavefinity_web.py:catalog_payload` → `wavefinity_web_impl/_runtime.py:default_design` → `BoxSpec` and empty fused layout. Space preferences can supply saved defaults. |
| Saved/imported design, reopen/edit | `/api/design/validate` → `_validate_design_open_guard`; design deserialization produces the same `BoxSpec`. Space data and inventory preserve existing design intent; do not reinterpret saved sizes. |
| AI Design | `ai_prompt_payload` / `ai_candidate_payload` in `wavefinity_web.py`; `wavefinity_web_impl/_ai.py` canonicalizes candidate; candidate goes through `preview_payload` and ordinary validation before use. |
| Browser preview | `preview_payload` / `_preview_payload` resolves design and builds preview. |
| Browser Save/Export | `/api/generate` → `generate_payload` → `_generate_payload` → `_design` → organizer generation. Local and hosted differ in file handling; the design still goes through the common generator. |
| Browser Print | `/api/print` → `print_payload`, checks slicer and printer; generated bins use the ordinary generation path. Saved file reuse is a separate route and must not be mistaken for regeneration. |
| Inventory / Space batch | `_generate_bin_from_design_spec` deserializes a spec-only row and calls `generate_organizer_files_transactional`; previously generated files can be reused. `organizer_inventory/_space.py:normalise_space_definition` validates Space dimensions separately; drawer, portable, surface and pegboard are not a new bin profile. |
| CLI | `organizer_app.py:run_command`: `box`, `kit`, `sampler`, and `organizer`; the latter loads design or layout JSON, applies CLI overrides and calls transactional organizer generation. |
| Engine | `organizer_engine/_specs.py:BoxSpec` validates; `_boxes.py:make_box` makes the wavy shell and delegates existing stacking/lid operations; rejects Storage Box specs. `_fit.py:installed_boxes` and `validate_side_fit` address current Wavefinity side-connector fit, not Gridfinity. |

Structural Storage Box, Storage Drawers and Surface Base Trim have separate builders (`wavefinity_web.py` structural routes); they are not ordinary bin entry routes. Any later change must account for them without silently converting existing outputs.

## 7. Printer build volume

`organizer_outputs/printer_profile.py:8` sets 256 × 256 × 256 as the fallback; preferences may override all three axes. `wavefinity_web.py:_printer_profile_for` uses the browser-supplied profile when hosted and local preferences otherwise; `component_fit` checks allowed orientations and each axis. The 350 mm engine XY ceiling is a resource limit, not a printer bed. README's 10 mm per-edge reservation and 236 × 236 effective area apply to the Base Trim ring workflow, not a blanket reduction of every printer check. Profile does not set slicer printer or material.

## 8. Wavefinity regression baselines

Preserve existing wavy bin geometry, 7 mm grid, 0.25 neighbour gap, connectors, direct stacking, lids, saved designs and Space behavior; no Gridfinity output is present in this snapshot. `README.md` Export progress benchmark records height 40 for 98×98, 203×147, 350×350 and 350×350 with lid, and the associated timing table. These are historical observations, not new measurements. README notes 3MF hashes vary with export UUID; STL fingerprints are the meaningful geometry comparison. Its historical sine-wave measurements are explicitly not acceptance evidence for current arc walls. No physical-fit or current benchmark claim is introduced here.
