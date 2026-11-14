"use strict";
const MASCOT_HIDDEN_KEY = "wavefinity-mascot-hidden";

function isMascotHidden() {
  try {
    return localStorage.getItem(MASCOT_HIDDEN_KEY) === "1";
  } catch (_error) {
    return false;
  }
}

function setMascotHiddenPreference(hidden) {
  try {
    if (hidden) localStorage.setItem(MASCOT_HIDDEN_KEY, "1");
    else localStorage.removeItem(MASCOT_HIDDEN_KEY);
  } catch (_error) { /* storage unavailable */ }
}

function wirePreviewMascot() {
  const container = document.getElementById("preview-mascot");
  const trigger = document.getElementById("preview-mascot-trigger");
  const menu = document.getElementById("preview-mascot-menu");
  const hideBtn = document.getElementById("preview-mascot-hide");
  const settingsToggle = document.getElementById("settings-show-mascot");
  if (!container || !trigger || !menu || !hideBtn) return;

  function closeMenu() {
    menu.hidden = true;
    trigger.setAttribute("aria-expanded", "false");
  }

  function unmountVideo() {
    const video = trigger.querySelector("video");
    if (video) {
      video.pause();
      video.remove();
    }
  }

  function mountVideo() {
    if (trigger.querySelector("video")) return;
    const video = document.createElement("video");
    video.className = "preview-mascot-video";
    video.src = "/images/mascot-loop.webm";
    video.autoplay = true;
    video.loop = true;
    video.muted = true;
    video.playsInline = true;
    video.setAttribute("aria-hidden", "true");
    trigger.appendChild(video);
    video.play().catch(() => {});
  }

  function applyVisibility(hidden) {
    closeMenu();
    if (settingsToggle) settingsToggle.checked = !hidden;
    if (hidden) {
      unmountVideo();
      container.hidden = true;
    } else {
      mountVideo();
      container.hidden = false;
    }
  }

  applyVisibility(isMascotHidden());

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const opening = menu.hidden;
    menu.hidden = !opening;
    trigger.setAttribute("aria-expanded", opening ? "true" : "false");
  });

  hideBtn.addEventListener("click", () => {
    setMascotHiddenPreference(true);
    applyVisibility(true);
  });

  if (settingsToggle) {
    settingsToggle.addEventListener("change", () => {
      const hidden = !settingsToggle.checked;
      setMascotHiddenPreference(hidden);
      applyVisibility(hidden);
    });
  }

  document.addEventListener("pointerdown", (event) => {
    if (!menu.hidden && !container.contains(event.target)) closeMenu();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) closeMenu();
  });
}

async function init() {
  wirePreviewMascot();
  wireAboutDialog();
  wireBinNameDialog();
  wireSafeDialogBackdrops();
  try {
    await WFBrowserCore.init();
    const catalog = await api("/api/catalog");
    const savedPreferences = await api("/api/preferences", {});
    catalog.preferences = savedPreferences.preferences;
    if (catalog.preferences?.preference_warning) toast(catalog.preferences.preference_warning, true, 6000);
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

// Fix 1121 (hopper #89 item 1): shared helper — suppress browser autocomplete
// on all data-entry controls. Supersedes the Fix 124 inline sweep: now a named
// shared helper (callable on the whole document or on a single dynamic root),
// and covers eligible text/number-like inputs AND textareas. An explicitly set
// autocomplete attribute is always respected (opt-out).
const AUTOCOMPLETE_SUPPRESS_SELECTOR = 'input[type="text"], input[type="number"], input:not([type]), textarea';
function suppressBrowserAutocomplete(root) {
  const scope = root || document;
  const targets = [];
  if (scope.matches && scope.matches(AUTOCOMPLETE_SUPPRESS_SELECTOR)) targets.push(scope);
  scope.querySelectorAll(AUTOCOMPLETE_SUPPRESS_SELECTOR).forEach(el => targets.push(el));
  targets.forEach(el => {
    if (!el.hasAttribute('autocomplete')) {
      el.setAttribute('autocomplete', 'off');
    }
  });
}
// Run on initial load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => suppressBrowserAutocomplete());
} else {
  suppressBrowserAutocomplete();
}
// Re-run when dynamic content is added (MutationObserver for modals/editors)
// NOTE: wrapped in an arrow function — the observer invokes its callback with
// (mutations, observer), which must NOT be passed through as the helper's root.
new MutationObserver(() => suppressBrowserAutocomplete()).observe(document.body, {
  childList: true,
  subtree: true
});
