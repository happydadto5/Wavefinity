"use strict";

// ------------------------------------------------ Folder access launch notice (Fix 116)
// A hosted browser session can only save inventory and Spaces into a folder
// the person has granted. When that access is missing at launch, say so with a
// non-blocking banner. This is notification only: it reuses SP.canPersistSpace
// (the same check the Inventory/Spaces actions use) and SP.open (the same path
// as the "Select a folder..." button); it never changes folder access itself.

SP.FOLDER_NOTICE_SUPPRESS_KEY = "wavefinity.suppressFolderAccessNotice";

SP.folderNoticeSuppressed = () => {
  try { return localStorage.getItem(SP.FOLDER_NOTICE_SUPPRESS_KEY) === "1"; }
  catch (_error) { return false; }
};

SP.setFolderNoticeSuppressed = suppressed => {
  try {
    if (suppressed) localStorage.setItem(SP.FOLDER_NOTICE_SUPPRESS_KEY, "1");
    else localStorage.removeItem(SP.FOLDER_NOTICE_SUPPRESS_KEY);
  } catch (_error) { /* a blocked store only means the notice may show again */ }
};

SP.folderNoticeTimer = null;

SP.hideFolderAccessNotice = () => {
  if (SP.folderNoticeTimer) {
    clearInterval(SP.folderNoticeTimer);
    SP.folderNoticeTimer = null;
  }
  const notice = document.getElementById("folder-access-notice");
  if (notice) notice.hidden = true;
};

SP.wireFolderAccessNotice = () => {
  const notice = document.getElementById("folder-access-notice");
  if (!notice || notice.dataset.wired) return;
  notice.dataset.wired = "1";
  document.getElementById("folder-access-choose")?.addEventListener("click", () => SP.open());
  document.getElementById("folder-access-dismiss")?.addEventListener("click", SP.hideFolderAccessNotice);
  document.getElementById("folder-access-suppress")?.addEventListener("change", event => {
    SP.setFolderNoticeSuppressed(event.target.checked);
  });
};

// Called once, after launch routing has finished, so a saved folder that
// resumed silently never triggers the notice.
SP.showFolderAccessNoticeIfNeeded = () => {
  const notice = document.getElementById("folder-access-notice");
  if (!notice || !state.runtime?.hosted) return;
  if (SP.canPersistSpace() || SP.folderNoticeSuppressed()) return;
  SP.wireFolderAccessNotice();
  const checkbox = document.getElementById("folder-access-suppress");
  if (checkbox) checkbox.checked = false;
  notice.hidden = false;
  // Choosing a folder happens elsewhere (Welcome / Spaces); drop the banner as
  // soon as access exists, without touching the suppression preference.
  if (!SP.folderNoticeTimer) {
    SP.folderNoticeTimer = setInterval(() => {
      if (SP.canPersistSpace()) SP.hideFolderAccessNotice();
    }, 500);
  }
};
