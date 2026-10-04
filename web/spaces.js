"use strict";

// Startup must come after every SP.* helper it (transitively) depends on -
// SP.wire, wireInfoButtons, SP.updateReadouts, SP.renderSpaceInfo,
// and everything SP.launch()/SP.wire() call - is defined,
// so this stays the very last thing in the file. state.ready can already be
// true by the time this script runs, which would otherwise call SP.wire()
// before it exists - see Fix 004 Correction 8.A.
const startSpaces = async () => {
  try {
    try { SP.ensureStorageDrawersRules(); } catch (_error) { /* catalog unavailable: validated lazily */ }
    await SP.initPrinterProfile();
    SP.wire();
    // The routing decision - saved folder / Welcome / Resume / setup - is
    // made first, behind the startup cover the initial HTML already shows.
    await SP.launch();
    // Fix 116: launch routing is settled, so folder access is now known.
    try { SP.showFolderAccessNoticeIfNeeded(); } catch (_error) { /* the notice is optional */ }
  } finally {
    // Single owner of successful cover dismissal, so the bare Design UI never
    // flashes between routing states - and an unexpected startup error can
    // never leave "Opening Wavefinity..." on screen forever.
    const cover = document.getElementById("startup-cover");
    if (cover) cover.hidden = true;
  }

  // Only now does the first preview begin, behind the correct screen -
  // unless Space activation during SP.launch() already started one for the
  // design it just installed (Fix 032 Correction 3, C3.2); firing this one
  // too would be a redundant duplicate of the same design/generation.
  // refreshPreview() discards stale responses, so a later user action wins.
  if (!SP._activationPreviewRequested) await refreshPreview();
};

// A Base Trim file changed outside Wavefinity is noticed when the window is used again.
window.addEventListener("focus", () => {
  if (SP.structuralKind() === "base_trim" && !SP.structuralBusy) SP.invalidateBaseTrimSummary();
});

if (state.ready) {
  startSpaces();
} else {
  window.addEventListener("wavefinity:ready", startSpaces, { once: true });
}
