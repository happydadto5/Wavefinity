"use strict";
async function init() {
  wireAboutDialog();
  wireBinNameDialog();
  wireSafeDialogBackdrops();
  try {
    const catalog = await api("/api/catalog");
    state.catalog = catalog;
    if (typeof StorageDrawers !== "undefined") {
      // Missing catalog rules must not stop startup; Storage Drawers setup then
      // fails closed with its own "catalog rules are unavailable" message.
      try { StorageDrawers.configureRules(state.catalog); } catch (_error) { /* reported when a cabinet is used */ }
    }
    state.runtime = catalog.runtime || { hosted: false, filesystem: "server" };
    state.serverInstance = catalog.instance;
    state.apiCompat = catalog.api_compat;
    state.design = clone(catalog.defaults.design);
    resetNestPhotoSession();
    state.cleanDesign = clone(state.design);
    state.output = state.runtime.hosted ? "" : (catalog.preferences?.output || catalog.defaults.output);
    setFolderState("design");
    state.connector = clone(catalog.defaults.connector);
    restoreConnectorSettings();
    state.slicer = catalog.slicer || { available: false, path: null, name: "Bambu Studio" };
    updateSlicerUI();
    renderCatalog();
    wireControls();
    bindLidMemoryForDesign();
    syncForm();
    watchServerVersion();
    clearDraftSelection();

    // Space startup owns the first preview. Catalog/UI initialization is
    // enough to begin onboarding, so Welcome/Resume no longer waits behind
    // preview generation.
    state.ready = true;
    window.dispatchEvent(new Event("wavefinity:ready"));
  } catch (error) {
    // A startup failure must never leave an infinite "Opening Wavefinity..."
    // cover over the actual error.
    document.getElementById("startup-cover")?.setAttribute("hidden", "");
    setError(error.message);
    toast(error.message, true, 8000);
  }
}

init();
