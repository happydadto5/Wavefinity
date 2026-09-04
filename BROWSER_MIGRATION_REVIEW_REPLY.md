# Reply to the browser migration review brief

- **Reviewed by:** Claude
- **Date:** 2026-09-04
- **Against:** commit `4401dac` ("Add local browser organizer app"), confirmed
  current at `6e951ae` (working tree clean, no drift since your handoff)
- **Method:** re-ran your reproduction commands, re-read the diffed files, and
  hit the live server directly over HTTP for the claims that needed evidence
  rather than inspection.

Short version: the claims I could independently verify all check out exactly
as stated. Two things you should confirm or fix before this replaces the
desktop app for real use, one thing to verify on your side that I could only
read code for, and one pre-existing engine bug (not yours) that's easy to hit
through the mode you added.

## What checked out

Re-run, not re-read, and matched your numbers exactly:

- `python -m unittest test_wavefinity_web` — 8/8 pass.
- `node --check web/app.js` — clean.
- `Launch_Organizer_UI.bat --check` — exit 0, imports both `organizer_app`
  and `wavefinity_web`.
- `generated/Box 40 x 48 x 40 DRIVERS.3mf` — 848,974 bytes, exact byte match.
- `generated/Insert 40 x 48.3mf` — 12,489 bytes, exact byte match.
- Both canvases really do use one `Math.min(width/spanX, height/spanY)`
  scale (`web/app.js:596` and `:668`) — confirmed, no independent-axis
  stretch.
- Commit `4401dac` is real, on `main`, and matches your stated diff shape.

- `python -m unittest` — 190/190 pass in 153s here (your 169.7s is just
  machine-load noise, not a discrepancy).

## Please confirm — item 1: default values get frozen into the design the moment a part is placed

This is squarely your requested-focus item 1 ("flag any geometry rule
duplicated in JavaScript") — it's not duplicated math, but it is a case
where the JSON round-trip silently changes what a value *means*.

On the desktop, a holder can leave an option unset — `default_feature()`
returns `options={}` — meaning "recompute this from the item and the bin,
every rebuild." That's how a nest's recess is supposed to keep tracking the
stored tool if it changes later.

`default_feature_payload` (`wavefinity_web.py:276`) resolves those numbers
before sending the feature to the browser so the form isn't blank — right
call. But it writes the resolved number into `options`, and nothing
downstream ever clears it back out. Live check against the running server:

```
fresh default nest options: {'wall': 1.6, 'depth': 2.0, 'height': 3.2}
after apply, stored options:   {'wall': 1.6, 'depth': 2.0, 'height': 3.2}   ← should be {}
```

Consequence, also reproduced live: place that nest, then edit it to hold a
much thicker tool. A genuinely-auto recess would grow to ~6.1 mm on its own;
instead the 2.0 mm from placement time stays frozen, and the edit is
rejected outright with a message that reads as unrelated to what was
actually changed:

```
after swapping to a d=20 tool: SERVER REJECTED IT -> no room for c: the nest zone is too narrow
```

Affects every kind whose default depends on the item or the bin — divider,
pocket, slot, bore, nest. Harmless for post/cradle, whose defaults are
constants. None of the 8 contract tests catch it because every one of them
builds features with options already explicit.

**Suggested fix:** keep resolving for display, stop persisting it. The
desktop keeps the two genuinely separate (`one.options` stays empty;
`resolved_options()` only ever fills the on-screen field) — the browser form
needs the same split: show the resolved number, but only write a key into
`state.draft.options` for the field the user actually edited, not for every
field `renderDraftFields()` happened to render a number into.

## Please confirm — item 2: the fused/removable holder color distinction doesn't reach the browser canvas

A holder standing on a removable or cartridge insert is supposed to render
in a visibly different tint from the same holder fused to the bin — that's
existing, intentional behavior, and the server still emits it correctly
(`preview_geometry` tags geometry `feature_<kind>` vs `insert_<kind>`,
unchanged code). `web/app.js:528` throws the distinction away before it
reaches the palette:

```js
function kindColor(kind) {
  if (COLORS[kind]) return COLORS[kind];
  const base = kind.replace(/^insert_/, "").replace(/^feature_/, "");  // ← tint tag dropped here
  ...
  return COLORS[base] || "#7896a0";
}
```

`COLORS` (`web/app.js:25`) has no `insert_*` entries, so every holder on a
removable insert renders in the exact same hue as if it were fused. The
plate itself is fine — `insert_base: "#c5ab83"` is a real, distinct color —
it's only the holders standing on it that lose the distinction. A second
spot needing the same fix: `/api/feature/draft`'s single-part live preview
tags its geometry with the bare kind name regardless of mode, so the small
editor canvas can't show the distinction even after `kindColor` is fixed.

**Suggested fix:** add tinted `insert_<kind>` entries to `COLORS` (a fixed
blend toward one warm tone works fine, doesn't need to be exact), and
prefix `draft_payload`'s geometry the same way the main preview already
does.

## Worth a look — item 3: state-mutating requests don't share the stale-response guard the preview/draft requests use

You specifically asked for this check ("verify all state-changing paths
preserve that rule"), and I think it's a real gap, though I haven't
reproduced actual corruption — just the missing invariant.

`refreshPreview`/`refreshDraft` correctly discard a response that arrives
after a newer request was already sent (`previewRequest`/`draftRequest`
counters). `applySupport`, `deleteSupport`
(`web/app.js:432`, `:457`), and the mode-change handler
(`web/app.js:117-133`) all mutate `state.design` from their response with no
equivalent guard — only `applySupport`'s own button gets disabled mid-flight,
which stops a double-click on *that* button but not a race between two
*different* controls (e.g. add a support, then flip the mode radio before
the add resolves). Whichever response lands second wins and silently
overwrites `state.design`, discarding the other mutation with no error.
Given typical loopback latency this is a narrow window, not something I'd
block on, but it's exactly the class of bug that request-counters exist to
close everywhere else in this file — worth either the same guard or an
explicit "one mutation in flight at a time" lock across all of them, your
call on which fits the rest of the pattern better.

## FYI, not yours to fix: "Post" + 8 mm cartridge fails on the default starter bin

Reproduces identically through the desktop's own `default_feature()` +
`build_features()` — pre-existing, in the engine you deliberately didn't
touch, not introduced by this migration. Flagging because it's trivially
reachable and your own QA pass didn't happen to hit this exact combination:
switch "Insert form" to 8 mm cartridge, pick "Post," nothing else changed:

```
default post zone (cartridge): 8.0 x 16.0  options: {'diameter': 12.0, ...}
BUILD FAILS: 1 posts need 12.0 x 12.0 mm but the zone gives 8.0 x 16.0 mm
```

`default_feature()`'s generic sizing rule for a plain shape
(`min(16.0, bounds.width)`) doesn't know post's own default diameter is
12 mm, so on an 8 mm-wide cartridge cell it hands the builder a footprint too
narrow for even one post at default size, before the user touches anything.
Might be worth a line in your "Known limitations" section even though it's
out of this PR's stated scope — a fresh install hitting this on the very
first "try cartridge mode" click is a bad first impression regardless of
whose commit it belongs to.

## One clarification on the security boundary, no action needed

Your Origin check (`wavefinity_web.py`) only rejects when an Origin header
is present and mismatched — a request with no Origin header at all is
waved through on that check alone. I want to flag this precisely because I
don't think it's exploitable against the threat model you stated: a
browser's `fetch`/XHR to another origin cannot omit the Origin header, that
header is spec-enforced and not something page JS can suppress, and the
content-type gate (`application/json`) independently blocks plain `<form>`
CSRF since forms can't set that content type. The gap only matters against a
non-browser local process calling the API directly (curl, another local
app) — which Origin-checking can't meaningfully stop for *any*
unauthenticated loopback service, since Origin is a browser-side promise,
not a server-verifiable credential. That matches your own framing ("a local
application, not a hosted service") rather than contradicting it. No fix
requested — just didn't want you to read "Origin check" as stronger than it
is if this doc gets reused as a security summary later.

## What I didn't verify — still open per your own list

- Real mouse-driven drag/resize at all four layout boundaries and against
  scoop/label keep-outs in all three modes (your item 4) — I checked the
  resize-handle math matches the desktop's byte-for-byte, but did not drive
  a browser.
- Edge smoke test (your item 6, your own limitation 1).
- Screen-reader names and keyboard operability beyond static markup review
  (your item 7). One thing worth a deliberate decision either way: the 2D
  layout's drag-to-move/resize and the 3D camera's drag-to-rotate are
  pointer-only with no keyboard path on the canvas itself — the numeric
  Center X/Y/Width/Depth fields do cover the same ground for a placed
  support, so there's an accessible equivalent, just not on the canvas.
- The standalone DOM test suite you already flagged as missing (your
  limitation 3) — agreed, and finding 3 above is exactly the kind of bug
  that suite would have needed to catch.
