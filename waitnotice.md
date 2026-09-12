# waitnotice — 3D recalculation indicator plan

## Goal
Give the user a clear visual indication on the 3D preview whenever a design change is still being recalculated, without blanking the preview or making fast updates feel slower.

## Final UX decision
Use a small overlay pill in the upper-right of the 3D canvas.

Default text:

`⟳ Updating design…`

Behavior:
- Keep the existing 3D model visible while recalculation runs.
- Slightly dim the existing preview while the notice is visible; do not clear or replace the canvas.
- Delay showing the notice by about 175 ms so very fast updates do not flash a spinner.
- If recalculation is still running after about 1.5 seconds, change the text to `Rebuilding geometry…`.
- Remove the notice immediately when the newest preview request finishes successfully or fails.
- If another design change starts while an earlier request is still running, keep the notice active until the newest request finishes. An older/stale response must never hide the notice for a newer request.
- This is only a recalculation/status indicator. Do not disable the UI, add a modal, clear the model, or block additional edits.

## Existing architecture to reuse
`web/app.js` already tracks preview generations with `state.previewRequest` and ignores stale preview responses. Use that same request identity as the authority for the wait notice. Do not create an independent busy counter that can drift out of sync with preview requests.

The current preview flow also already has `#preview-state`; leave that existing status text alone unless it is currently duplicating the new message. The new indicator belongs directly over the 3D canvas because that is what the user is waiting to update.

## Files to change

### 1. `web/index.html`
Inside the existing 3D `.canvas-wrap` (`data-canvas="3d"`), add one overlay element near the canvas so it can be absolutely positioned over the preview.

Suggested structure:

```html
<div id="preview-wait" class="preview-wait" hidden aria-live="polite">
  <span class="preview-wait-spinner" aria-hidden="true"></span>
  <span id="preview-wait-text">Updating design…</span>
</div>
```

Do not put it in the toolbar; it should visually belong to the 3D model.

### 2. `web/styles.css`
Add compact styling for the overlay.

Requirements:
- upper-right corner of the 3D canvas area
- visually above the canvas and below any full-screen/modal UI
- small pill/card, not a large banner
- readable against both light and dark geometry
- spinner uses CSS animation only
- respect `prefers-reduced-motion`; in reduced-motion mode show a static icon/dot instead of rotation
- pointer-events disabled so it never blocks rotation, zoom, or buttons

Also add a class on the 3D canvas wrapper such as `.preview-recalculating` that slightly reduces canvas opacity (roughly 0.85–0.9). Do not blur the model.

### 3. `web/app.js`
Add a tiny set of helpers near the preview logic, for example:

- `beginPreviewWait(requestId)`
- `endPreviewWait(requestId)`
- `clearPreviewWaitTimers()`

Implementation rules:

#### On preview start
At the point where a new `request = ++state.previewRequest` is created:
- cancel any timers belonging to the previous request
- schedule the wait overlay to appear after ~175 ms
- schedule the long-running text change after ~1500 ms
- both timer callbacks must confirm `request === state.previewRequest` before changing the UI

#### On preview completion
In the success path, after confirming the returned request is still current, hide the overlay and remove the dimming class.

#### On preview failure
Do the same cleanup in the error path, but only if that failed request is still the current request.

#### Stale responses
If `request !== state.previewRequest`, return exactly as the code does today. A stale request must not clear the notice, cancel the current request's timers, or restore canvas opacity.

This stale-request rule is the most important implementation detail.

## Suggested state
Keep only the timer handles needed for cleanup, either as module-level variables or small fields on `state`, e.g.:

```js
previewWaitTimer: null,
previewSlowTimer: null,
```

Do not add a second request sequence number. `state.previewRequest` remains the source of truth.

## Exact visual states

### Under 175 ms
No notice. Existing model remains unchanged.

### 175 ms–1.5 s
Show:

`⟳ Updating design…`

and dim the old model slightly.

### Over 1.5 s
Keep the same spinner and change only the wording to:

`⟳ Rebuilding geometry…`

### Finished / error
Hide the overlay and restore normal opacity immediately.

The normal error UI remains responsible for explaining errors; the wait notice must not become an error message.

## Scope boundaries
Do not:
- change Python geometry code
- change preview API behavior
- add progress percentages; the backend provides no meaningful percentage
- disable controls during recalculation
- debounce design editing differently
- alter the existing stale-response protection
- create a general global loading framework

This is a small UI enhancement around the existing preview request lifecycle.

## Focused verification
No broad test suite is needed.

Add/update only a small browser contract test if there is an existing pattern for checking UI markup/source. Verify:
1. `index.html` contains the `preview-wait` overlay.
2. `app.js` ties show/hide behavior to `state.previewRequest`.
3. A stale request cannot call the final hide path for a newer request.
4. Reduced-motion CSS exists for the spinner.

Manual sanity check:
- change a simple dimension that recalculates quickly: indicator normally should not flash
- make a slower B4B/geometry change: indicator appears while the old model remains visible
- change values quickly several times: indicator stays until the final preview completes
- force a preview error: indicator clears and the normal error message remains visible

## Acceptance criteria
- User can always tell when the visible 3D model is stale because a newer design is being calculated.
- Fast recalculations do not produce distracting spinner flashes.
- Old geometry remains visible and usable as visual context while waiting.
- Only the newest preview request controls when the notice disappears.
- No geometry, saved-design, or generation behavior changes.