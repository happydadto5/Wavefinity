# Gridfinity — future plan

**Status: plan only. No stories are filed from this document.**
Debate 2544 assessed adding Gridfinity to Wavefinity and concluded on 2026-11-04.
Andrew gave his rulings the same day, then ordered the debate cancelled and the
plan parked here. When this work resumes, stories are designed from this document.

## First-pass scope (from the debate)

- Bins can sit on a Gridfinity base.
- Drawers and storage boxes can have the Gridfinity locating grid built into
  their floors, so standard Gridfinity bins seat securely.

## Andrew's rulings (2026-11-04)

- A Space is created either as a **standard base** or a **Gridfinity base**.
  The base is fixed at creation — an existing space is never converted later.
- A Gridfinity space locks sizes to 42 mm units and heights to Gridfinity
  height units.
- A storage box locks its usable interior height to Gridfinity heights.
  Drawers get the same standard-or-Gridfinity creation choice as storage boxes.
- Bins are either Gridfinity or Wavefinity, never both:
  Wavefinity bins use 7 mm units and any height; Gridfinity bins use 42 mm
  units and fixed Gridfinity heights.
- A space holds only its own kind of bin — no mixing Wavefinity bins into a
  Gridfinity space.
- Connectors are not part of a Gridfinity space.
- Magnets and screw holes are tackled up front, in the first pass.
- Keep-dimensions is the default (confirmed): containers keep their size and
  any leftover partial strip stays solid.
- A grid floor keeps the container's own base thickness — the floor only — and
  the grid is added on top of it, not carved out of it.

Recorded as Velexa's reading of Andrew's answers, not separately confirmed:
true Gridfinity interop in both directions (off-the-shelf Gridfinity bins seat
in Wavefinity containers, and Wavefinity Gridfinity bins seat on standard
Gridfinity baseplates), and magnet/screw holes as part of every Gridfinity
base rather than a per-bin switch.

## Debate feedback (reviewers, unanimous convergence)

- **Difficulty:** bin bases are MODERATE if the published 42 mm base profile
  and clearances integrate cleanly — higher if keeping Wavefinity side
  connections demands redesign. Integrated grid floors in drawers and boxes
  are HARD (floor/wall geometry, margins, thickness and strength, print
  validation) and should be estimated separately from the bases.
- **UI:** bins get a Base style selector (Wavefinity default / Gridfinity)
  with integer 42 mm width/depth units and a mm readout. Containers get a
  Floor selector (Plain default / Integrated Gridfinity) showing the full
  usable cells, the chosen grid origin (corner or centre), and the actual
  margins.
- **Cautions:** a 7 mm wave pitch dividing into 42 mm does not by itself
  establish Gridfinity fit — hybrid side mating must be geometry-verified
  before it is promised. A container is never silently resized: any resize is
  user-initiated, previews the inside and outside consequences, and requires
  confirmation. A grid that cannot fit one full cell is disabled.
