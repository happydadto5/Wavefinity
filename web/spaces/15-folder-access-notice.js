"use strict";

// ------------------------------------------------ Folder access launch notice (Fix 116)
// A hosted browser session can only save inventory and Spaces into a folder
// the person has granted. When that access is missing at launch, say so with a
// non-blocking banner. It reuses the Welcome folder-picking flow and the same
// persistence check as Inventory and Spaces.

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
  document.querySelectorAll("[data-folder-notice-inert]").forEach(el => {
    el.inert = false;
    el.removeAttribute("data-folder-notice-inert");
  });
  if (notice) {
    if (notice.open) notice.close();
    notice.hidden = true;
  }
};

SP.wireFolderAccessNotice = () => {
  const notice = document.getElementById("folder-access-notice");
  if (!notice || notice.dataset.wired) return;
  notice.dataset.wired = "1";
  document.getElementById("folder-access-choose")?.addEventListener("click", async () => {
    // Close the modal first so the flow opened below is not rendered behind an inert page.
    SP.hideFolderAccessNotice();
    if (SP.pendingReconnect) SP.reconnectSavedFolder();
    else {
      const opened = await SP.openExisting();
      const accessNeeded = SP.dialog().open && !document.getElementById("space-unsupported").hidden;
      if (!opened && !accessNeeded) SP.showFolderAccessNoticeIfNeeded();
    }
  });
  // "Design bins only": record the existing suppression key, then close.
  document.getElementById("folder-access-dismiss")?.addEventListener("click", () => {
    SP.setFolderNoticeSuppressed(true);
    SP.hideFolderAccessNotice();
  });
  // Escape must not dismiss the modal.
  notice.addEventListener("cancel", event => event.preventDefault());
  // Trap Tab between the two buttons while open.
  notice.addEventListener("keydown", event => {
    if (event.key !== "Tab") return;
    const first = document.getElementById("folder-access-choose");
    const last = document.getElementById("folder-access-dismiss");
    if (!first || !last) return;
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    else if (document.activeElement !== first && document.activeElement !== last) { event.preventDefault(); first.focus(); }
  });
};

// Called once, after launch routing has finished, so a saved folder that
// resumed silently never triggers the notice.
SP.showFolderAccessNoticeIfNeeded = () => {
  const notice = document.getElementById("folder-access-notice");
  if (!notice || !state.runtime?.hosted) return;
  if (SP.canPersistSpace() || SP.folderNoticeSuppressed()) return;
  SP.wireFolderAccessNotice();
  const choose = document.getElementById("folder-access-choose");
  if (choose) choose.textContent = SP.pendingReconnect ? "Reconnect folder" : "Choose folder";
  const homeHelp = document.getElementById("folder-access-home-help");
  if (homeHelp) homeHelp.hidden = !SP.pendingReconnect?.homeReconnect;
  notice.hidden = false;
  // Make the dialog the only interactive surface: inert every other top-level
  // element (app shell, welcome dialog, ...) and focus Choose folder.
  Array.from(document.body.children).forEach(el => {
    if (el === notice || el.tagName === "SCRIPT" || el.inert) return;
    el.inert = true;
    el.setAttribute("data-folder-notice-inert", "1");
  });
  if (!notice.open && typeof notice.showModal === "function") notice.showModal();
  choose?.focus();
  // Choosing a folder happens elsewhere (Welcome / Spaces); drop the dialog as
  // soon as access exists, without touching the suppression preference.
  if (!SP.folderNoticeTimer) {
    SP.folderNoticeTimer = setInterval(() => {
      if (SP.canPersistSpace()) SP.hideFolderAccessNotice();
    }, 500);
  }
};
