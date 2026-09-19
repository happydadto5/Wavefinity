# Fix 002 — Edge Trim Print-Bed Splitting

## Correction 1 — Perimeter pieces must be exact, not rectangular approximations

Current implementation reviewed on `main`, including commit `97bd84ff63c05cb7734b18cc1fff9c9cc9373ab2`.

The 10 mm-per-edge printable-area rule is correct: `BaseTrimSpec.effective_bed` subtracts 20 mm total from each bed axis, and the final generated mesh is checked against that usable area. Keep that behavior.

Two material issues remain in `organizer_base_trim.py`.

### A. A single rectangular clip does not represent an arbitrary contiguous perimeter arc

Current code:

- `_perimeter_piece()` reduces the requested perimeter arc to one rectangular `clip_bounds`.
- `_piece_clip()` intersects the ring with that one rectangle.

That is only geometrically exact when the arc can be represented by one rectangle, such as a simple one-corner L-shaped section with compatible endpoints.

For an arc that spans multiple corners, or an arc whose start/end positions on parallel sides are not aligned, the bounding rectangle can include trim that is **not part of that perimeter arc**. That creates duplicated/overlapping trim between neighboring pieces even though each individual mesh may still fit the bed.

Example geometry: an arc can legitimately contain part of the front, the entire right side, and part of the back. If the front and back seam coordinates differ, one rectangle extending to the minimum X coordinate captures extra front or back trim beyond one of the intended seams.

#### Required implementation correction

Keep the tight perimeter-point bounds for fit estimation if useful, but stop using one rectangle as the actual clipping geometry for a multi-side arc.

Implement the piece clip as the **union of the exact side runs traversed by that arc**.

A small implementation is sufficient:

1. Add a helper such as:

       _perimeter_runs(start, end, outer_x, outer_y)

   It should walk clockwise from `start` to `end` and return the ordered straight-side intervals actually traversed, split at each corner.

2. Represent the actual clip for a planned piece as multiple side-run clip rectangles rather than one global bounding rectangle. Keep this separate from any tight XY bounds used only for fit calculation.

   A minimal data change is acceptable, for example adding a field such as:

       clip_regions: tuple[tuple[float, float, float, float], ...] | None

   to `BaseTrimPiece`.

3. Build each side-run region using the same safe half-ring approach the old splitter already used:

   - front run: X limited to the run interval, Y from the outer front edge inward only to the center line;
   - right run: Y limited to the run interval, X from the center line to the outer right edge;
   - back run: X limited to the run interval, Y from the center line to the outer back edge;
   - left run: Y limited to the run interval, X from the outer left edge inward only to the center line.

   Preserve the small clipping overrun/margin needed for reliable boolean intersection.

4. Change `_piece_clip()` to union those side-run regions and extrude that union before intersecting it with the ring.

5. The resulting mesh for one planned piece must contain exactly the requested contiguous perimeter arc—no duplicated neighboring run and no missing run.

6. Keep the existing final actual-mesh `_fits(size, spec.effective_bed)` check.

Do **not** revert to independent edge pieces. Multi-side corner pieces are still required.

### B. The minimum-piece search is currently restricted to equal-length arcs

Current `plan_base_trim_pieces()` only evaluates partitions of this form:

    cuts = phase + perimeter * index / count

That means every candidate for a given `count` has equal perimeter length, and all cuts move together under one common 32-step phase.

This does not fully implement the requirement to find the fewest practical printable pieces. A valid lower-count partition may require unequal arc lengths because X/Y bed limits and rectangular trim proportions are asymmetric.

#### Required implementation correction

Keep the outer loop that tries `count = 2, 3, 4, ...` in order.

Within each count, allow cut positions to vary **independently** on straight runs.

Use a bounded deterministic search over straight-run seam positions. Do not use a heavyweight optimizer and do not restore edge-by-edge fixed-length chopping.

A suitable implementation is:

1. Treat corners as breakpoints in perimeter distance.
2. Starting from a candidate seam on a straight run, walk forward and determine the furthest valid next seam on each subsequent straight run while the candidate piece remains within `spec.effective_bed`.
3. Between corners, fit changes monotonically as the end seam moves farther away, so use the bed-limit crossing and the straight-run endpoints/corners as the meaningful candidate positions rather than sampling a global 32-phase grid.
4. Recursively/iteratively build `count` contiguous arcs from those candidate seam positions.
5. Reject a candidate immediately when any arc cannot fit.
6. For the first piece count that has at least one valid partition, score valid partitions using the existing priorities:
   - preserve corners;
   - cuts on straight runs and away from corners;
   - avoid tiny pieces;
   - prefer balanced/larger pieces.

The key requirement is that the search must not assume all pieces have equal perimeter length and must not couple every cut to one shared phase.

### Leave unchanged

Do not change:

- `BASE_TRIM_BED_EDGE_MARGIN = 10.0`;
- `BaseTrimSpec.effective_bed`;
- trim profile or corner geometry;
- joint geometry unless needed only to preserve the existing seam behavior;
- unrelated parts or printer behavior.

### Static completion check

Before committing, inspect the code/diff and confirm:

- an arbitrary planned perimeter arc clips only its own side runs;
- neighboring generated pieces cannot contain duplicated perimeter sections merely because their rectangular envelopes overlap;
- the partition search can produce unequal-length pieces when that reduces total piece count;
- candidate counts are still considered from smallest upward;
- final generated meshes are still checked against the 10 mm-per-edge effective bed;
- no additional tests are written, existing tests are not modified, and no tests are run.

Implement this as a correction to Fix 002, commit once, push `main`, and then stop for outside review.


## Problem

When edge trim is larger than the printable bed area, the current splitter creates too many pieces, including unnecessary small pieces around corners.

For example, a roughly:

    300 × 300 mm

trim on a:

    256 × 255 mm

bed can reasonably be printed as approximately four large corner pieces.

Instead, the existing algorithm is breaking too many individual edges/corners and producing a mixture of large and small fragments.

The goal is:

> Produce the fewest practical pieces, make those pieces as large as practical, preserve corners whenever possible, and guarantee that every piece fits safely inside the usable print area.

## Printable-area rule

Edge-trim pieces must stay at least **10 mm away from every edge of the printer bed**.

Therefore the raw printer-bed dimensions are not the allowable part dimensions.

Use:

    usableWidth  = bedWidth  - 20 mm
    usableDepth  = bedDepth  - 20 mm

For a 256 × 255 mm bed:

    usableWidth  = 236 mm
    usableDepth  = 235 mm

If the codebase already has an authoritative helper or configuration for this 10 mm safety margin, reuse it.

Do not create a competing definition of printable area.

Do not globally change printer-bed dimensions or unrelated part behavior.

## Scope

This is a **partitioning fix only**.

Keep the existing edge-trim geometry generation unchanged.

Do not change:

- trim profile geometry;
- trim thickness;
- corner geometry;
- trim offsets;
- clearances;
- placement;
- printer settings UI;
- global bed dimensions;
- unrelated parts;
- unrelated splitting behavior.

Modify only the edge-trim logic responsible for dividing oversized trim into printable pieces, plus the minimum helper logic necessary to support that change.

## Required behavior

### 1. Keep trim intact when it fits

Calculate the completed trim's actual XY bounding box.

If:

    bounds.width <= usableWidth
    &&
    bounds.depth <= usableDepth

return the trim unchanged as one piece.

Do not introduce seams when the complete trim already fits.

### 2. Do not treat corners as mandatory split locations

Corners should remain intact whenever possible.

The existing behavior that effectively divides individual straight edges and/or corners independently is what this fix is intended to replace.

Treat the trim as a continuous perimeter.

A valid output piece can contain:

    part of side A
    + a complete corner
    + part of side B

This is intentional.

Cuts should preferentially be made along straight trim runs.

### 3. Use actual candidate-piece XY bounds

Do not determine printability from trim-path length or the length of an individual edge.

For every proposed piece, calculate the actual resulting XY bounding box.

A piece is printable only when:

    pieceWidth <= usableWidth
    &&
    pieceDepth <= usableDepth

An L-shaped corner piece can contain substantially more than 236 mm of total trim path while still occupy only approximately 150 × 150 mm in XY.

That piece must be considered printable.

### 4. Minimize piece count first

The primary optimization goal is:

    minimum number of printable pieces

After that, prefer:

1. intact corners;
2. large pieces;
3. straight-run cuts;
4. cuts away from corners;
5. balanced piece sizes;
6. avoidance of tiny remainder fragments.

Do not solve this by assigning a fixed maximum length to each individual straight edge and repeatedly chopping edges into independent segments.

Instead, determine whether the continuous perimeter can be represented as:

    1 piece
    2 pieces
    3 pieces
    4 pieces
    ...

and use the smallest valid piece count.

Use a small deterministic search appropriate to the existing trim representation.

Do not introduce a general-purpose bin-packing or optimization framework.

## 300 × 300 reference case

For approximately:

    trim = 300 × 300 mm
    bed = 256 × 255 mm
    edge safety margin = 10 mm
    usable area = 236 × 235 mm

the desired result is approximately **four large L-shaped corner pieces**.

Conceptually, cuts near the midpoint of each straight side would create four pieces with footprints around:

    150 × 150 mm

Each piece fits comfortably inside the 236 × 235 mm usable area.

The implementation must not hard-code the 300 × 300 case.

The general partitioning logic should naturally produce this result, or an equivalent minimum-piece result.

It should not create numerous separate straight sections and corner fragments.

## Larger edge trim

If the trim is sufficiently large that four intact corner pieces cannot fit, introduce additional cuts only where necessary.

Continue following these priorities:

1. every piece must fit;
2. fewest pieces possible;
3. preserve as many complete corners as possible;
4. prefer straight-run cuts;
5. avoid tiny remainder pieces.

A corner may be split only when retaining it would prevent a valid printable partition.

Never emit an oversized piece simply to preserve a corner.

## Implementation approach

Inspect the current edge-trim generation and splitting implementation and identify:

- where the complete trim is generated;
- where oversized trim is detected;
- where split positions are currently selected;
- how straight sections and corners are represented;
- how split geometry is currently produced;
- how XY bounds are calculated;
- where printer-bed dimensions are obtained;
- whether an existing printable-area or safety-margin helper exists.

Implement the fix at the narrowest existing partitioning layer.

Reuse the project's existing:

- ordered perimeter representation;
- straight/corner segment information;
- geometry cutting/splitting functions;
- bounding-box calculations;
- printer-bed configuration;
- printable-area helpers.

Do not rebuild edge-trim geometry in a parallel system.

## Preferred algorithm

The implementation should conceptually follow this flow:

    usableWidth  = bedWidth  - 20
    usableDepth  = bedDepth  - 20

    if completeTrimFits(usableWidth, usableDepth):
        return [completeTrim]

    determine valid cut locations on straight runs

    for candidatePieceCount from smallest upward:
        create candidate contiguous perimeter partitions

        reject any partition where a piece exceeds:
            usableWidth × usableDepth

        if one or more valid partitions exist:
            choose the best valid partition
            return it

For partitions having the same number of pieces, prefer the candidate that:

1. splits the fewest corners;
2. keeps cuts farthest from corners;
3. avoids very small pieces;
4. produces larger and more balanced pieces.

Keep this search simple and deterministic.

For ordinary rectangular/polygonal trim, the number of sides and meaningful cut locations should be small enough that no heavyweight solver is necessary.

## Rotation

Respect whatever rotation behavior the existing edge-trim printability code already supports.

If an existing shared fit helper already handles 90-degree rotation, reuse it.

Do not create a new rotation or bed-placement subsystem as part of Fix 002.

## Hard invariant

Every edge-trim piece returned by the splitter must satisfy the usable bed dimensions.

Conceptually:

    piece.bounds.width <= bedWidth - 20
    &&
    piece.bounds.depth <= bedDepth - 20

Use the project's normal numerical tolerance convention where appropriate.

This requirement takes priority over corner preservation and all other optimization preferences.

## Risk-control principle

Keep this change small.

Prefer changing the current partition-selection logic rather than replacing the edge-trim generation pipeline.

Do not introduce new abstractions unless they are genuinely required by the existing implementation.

After implementation, inspect the diff specifically for:

- unintended edge-trim geometry changes;
- duplicated 10 mm margin logic;
- continued edge-by-edge fragmentation;
- unnecessary architectural changes;
- changes outside the edge-trim splitting path.

## Testing

Do not write additional tests.

Do not modify existing tests.

Do not run tests.

Do not run browser automation, screenshots, servers, or other test/verification work as part of this fix.

Testing is intentionally outside the scope of Fix 002.

Review the affected code path and final diff instead.

## Completion requirements

Fix 002 is complete when:

- edge trim that already fits remains one piece;
- the 10 mm-per-edge safety margin is respected;
- usable dimensions are based on bed dimensions minus 20 mm total per axis;
- oversized trim is no longer automatically fragmented at every corner;
- a generated piece may contain a complete corner and portions of both adjoining sides;
- actual XY bounding boxes determine printability;
- the splitter seeks the minimum practical number of pieces;
- straight-run cuts are preferred;
- unnecessary tiny fragments are avoided;
- every emitted piece fits within the usable bed area;
- unrelated edge-trim geometry remains unchanged;
- unrelated splitting behavior remains unchanged;
- no tests are written, modified, or run.

Implement this directly in the existing edge-trim splitting path.
